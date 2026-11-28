# Khai báo node, relationship, condition và parameter bằng Java

Neo4j Cypher-DSL cho phép xây dựng truy vấn Cypher bằng API Java có kiểu thay vì ghép chuỗi thủ công. Ta khai báo node, relationship, property, điều kiện và tham số bằng các builder; kết quả là một `Statement` biểu diễn cây cú pháp truy vấn (AST). Sau đó có thể render statement thành chuỗi Cypher hoặc đưa trực tiếp cho các API Spring Data Neo4j (SDN) hỗ trợ Cypher-DSL.

Cách làm này hữu ích khi truy vấn có nhiều nhánh điều kiện, relationship hoặc được lắp ghép theo yêu cầu tại runtime. Nó giúp tái sử dụng các thành phần query, giảm lỗi chính tả trong cấu trúc và giữ dữ liệu đầu vào ở dạng parameter. Tuy vậy, Cypher-DSL không tự đọc schema Neo4j để sinh lớp Java cho mọi label; việc ánh xạ node entity vẫn thuộc trách nhiệm của SDN.

## 1. Cypher-DSL hoạt động như thế nào?

Thay vì viết một chuỗi:

```java
String query = "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) "
    + "WHERE p.name = 'An' RETURN p";
```

ta xây dựng từng phần của câu lệnh bằng Java:

```java
String personName = "An";
Node person = Cypher.node("Person").named("p");
Node movie = Cypher.node("Movie").named("m");
Relationship actedIn = person.relationshipTo(movie, "ACTED_IN");

Statement statement = Cypher.match(actedIn)
    .where(person.property("name").isEqualTo(Cypher.literalOf("An")))
    .returning(person)
    .build();
```

Các bước chính:

1. Khai báo những node và relationship tham gia truy vấn.
2. Lấy property từ node hoặc relationship để tạo điều kiện.
3. Kết hợp điều kiện bằng `and`, `or`, `not`.
4. Khai báo phần `RETURN`, thứ tự, giới hạn hoặc các mệnh đề cần thiết.
5. Gọi `build()` để tạo `Statement` hoàn chỉnh.
6. Render hoặc chuyển `Statement` cho API thực thi tương thích.

Các bước trung gian của DSL là immutable: mỗi lời gọi builder trả về một bước mới. Hãy tiếp tục sử dụng giá trị trả về thay vì giả định object bước trước bị thay đổi tại chỗ.

## 2. Chuẩn bị dependency

Cypher-DSL có artifact Maven `org.neo4j:neo4j-cypher-dsl`. Nếu dự án dùng Spring Boot hoặc dependency management của Spring Data, hãy ưu tiên phiên bản được BOM quản lý hoặc chọn phiên bản tương thích với SDN và Neo4j đang sử dụng.

Ví dụ dependency Maven khi dự án tự quản lý version:

```xml
<dependency>
    <groupId>org.neo4j</groupId>
    <artifactId>neo4j-cypher-dsl</artifactId>
    <version>${cypher-dsl.version}</version>
</dependency>
```

Tài liệu Cypher-DSL hiện hành được dùng trong bài là 2025.3.3. Từ dòng 2023.x, Cypher-DSL yêu cầu Java 17 trở lên. Một số API công khai vẫn được đánh dấu experimental và có thể thay đổi giữa các dòng release. Hãy kiểm tra Java baseline, dependency tree và manual đúng version trước khi nâng cấp; không nên chép một version mới nhất vào dự án cũ mà không đối chiếu tương thích.

Các ví dụ dưới đây dùng package `org.neo4j.cypherdsl.core`. Có thể dùng static import để code gọn hơn, nhưng các ví dụ chính giữ tiền tố `Cypher` để thấy rõ API tạo từng thành phần.

## 3. Khai báo node bằng `Cypher.node()` và `Cypher.anyNode()`

Node trong Cypher-DSL là biểu thức đại diện cho một node pattern trong truy vấn, không phải một node đã được tải từ database.

`Cypher.node("Person")` khai báo node có label `Person`. `named("p")` đặt symbolic name để tái sử dụng node ở các phần `MATCH`, `WHERE` và `RETURN`:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;

Node person = Cypher.node("Person").named("p");

Statement statement = Cypher.match(person)
    .returning(person)
    .build();
```

Statement này được render thành Cypher tương đương:

```cypher
MATCH (p:`Person`) RETURN p
```

Khi không cần chỉ định label, dùng `Cypher.anyNode()` hoặc `Cypher.anyNode("alias")`:

```java
Node source = Cypher.anyNode("source");
Node target = Cypher.anyNode("target");
```

Điều này tạo pattern tổng quát `(source)` và `(target)`. `anyNode()` hữu ích khi truy vấn cần duyệt qua node chưa biết label hoặc khi cấu trúc query được xây dựng tổng quát.

Tên node nên được đặt rõ ràng bằng `named(...)` nếu cần tham chiếu property hoặc dùng lại trong nhiều mệnh đề. Nếu không đặt tên, renderer có thể tự sinh symbolic name; tên tự sinh khó đọc và không nên được dùng như một phần hợp đồng của ứng dụng.

## 4. Khai báo relationship và hướng duyệt

Cypher-DSL cung cấp các phương thức trên node để mô tả hướng relationship:

- `relationshipTo(other, "TYPE")`: relationship đi từ node hiện tại đến node đích, tạo dạng `()-[:TYPE]->()`.
- `relationshipFrom(other, "TYPE")`: relationship đi từ node nguồn khác vào node hiện tại, tạo dạng `()<-[:TYPE]-()`.
- `relationshipBetween(other, "TYPE")`: relationship không chỉ định hướng, tạo dạng `()-[:TYPE]-()`.

Ví dụ người tham gia phim:

```java
String personName = "An";
Node person = Cypher.node("Person").named("p");
Node movie = Cypher.node("Movie").named("m");

Relationship actedIn = person
    .relationshipTo(movie, "ACTED_IN")
    .named("r");

Statement statement = Cypher.match(actedIn)
    .returning(person, movie, actedIn)
    .build();
```

Cypher được tạo có dạng:

```cypher
MATCH (p:`Person`)-[r:`ACTED_IN`]->(m:`Movie`)
RETURN p, m, r
```

Nếu bắt đầu từ phim và cần tìm đạo diễn, relationship `DIRECTED` trong graph có hướng từ `Person` đến `Movie`. Ta có thể khai báo:

```java
Node movie = Cypher.node("Movie").named("m");
Node director = Cypher.node("Person").named("director");

Relationship directed = movie.relationshipFrom(director, "DIRECTED");

Statement statement = Cypher.match(directed)
    .returning(director.property("name"))
    .build();
```

Kết quả có dạng `(m:Movie)<-[:DIRECTED]-(director:Person)`. Chọn `relationshipTo` hay `relationshipFrom` theo hướng thật của relationship trong graph, không dựa vào tên field Java.

Có thể đặt tên relationship và đọc property trên nó:

```java
Node person = Cypher.node("Person").named("p");
Node movie = Cypher.node("Movie").named("m");

Relationship rated = person.relationshipTo(movie, "RATED").named("r");

Statement statement = Cypher.match(rated)
    .returning(person.property("name"), rated.property("rating"))
    .build();
```

`rated.property("rating")` tham chiếu property trên relationship `r`; `person.property("name")` tham chiếu property trên node `p`.

## 5. Đọc property và tạo condition

Gọi `property("name")` trên node hoặc relationship để lấy biểu thức property. Sau đó có thể dùng các phép so sánh như `isEqualTo`, `gt`, `gte`, `lt`, `lte`, `isNotEqualTo` để tạo condition.

Ví dụ tìm phim phát hành trong thập niên 1990:

```java
Node movie = Cypher.node("Movie").named("m");
var released = movie.property("released");

Statement statement = Cypher.match(movie)
    .where(released.gte(Cypher.literalOf(1990))
        .and(released.lt(Cypher.literalOf(2000)))
    )
    .returning(movie.property("title"))
    .build();
```

Điều kiện tương ứng:

```cypher
WHERE m.released >= 1990 AND m.released < 2000
```

Các condition có thể được kết hợp bằng `.and(...)`, `.or(...)` hoặc bọc bằng `Cypher.not(...)`:

```java
Node person = Cypher.node("Person").named("p");

var name = person.property("name");
var age = person.property("age");

var condition = name.isEqualTo(Cypher.literalOf("An"))
    .or(age.gte(Cypher.literalOf(30)));

Statement statement = Cypher.match(person)
    .where(Cypher.not(condition))
    .returning(person)
    .build();
```

Nên tách các biểu thức con thành biến khi điều kiện dài hoặc được tái sử dụng. Điều đó giúp code Java phản ánh cấu trúc logic của truy vấn và dễ kiểm tra từng nhánh hơn.

## 6. Kết hợp nhiều node và relationship trong một pattern

Một truy vấn đồ thị thường cần nhiều relationship nối tiếp. Có thể tạo pattern bằng cách nối builder relationship:

```java
Node person = Cypher.node("Person").named("p");
Node movie = Cypher.anyNode("m");
Node coActor = Cypher.anyNode("coActor");

var path = person.relationshipTo(movie, "ACTED_IN")
    .relationshipFrom(coActor, "ACTED_IN");

Statement statement = Cypher.match(path)
    .where(person.property("name").isEqualTo(Cypher.literalOf("An")))
    .returning(coActor.property("name"))
    .build();
```

Pattern được tạo có dạng:

```cypher
MATCH (p:`Person`)-[:`ACTED_IN`]->(m)<-[:`ACTED_IN`]-(coActor)
WHERE p.name = 'An'
RETURN coActor.name
```

Khi một query có nhiều pattern độc lập, truyền các pattern vào `Cypher.match(...)` theo API builder. Hãy đặt tên symbolic cho các node được dùng trong điều kiện hoặc phần trả về để tránh nhầm lẫn giữa các biến trong graph pattern.

## 7. Dùng parameter thay cho literal động

Đối với dữ liệu đầu vào như tên, ID, năm, trạng thái hoặc từ khóa tìm kiếm, hãy dùng Cypher parameter. Cypher-DSL có hai cách thường gặp:

- `Cypher.parameter("name")`: tạo placeholder có tên, được render thành `$name`.
- `Cypher.parameter("name", value)` hoặc `.withValue(value)`: tạo placeholder và gắn giá trị để DSL thu thập vào parameter catalog.
- `Cypher.anonParameter(value)`: tạo parameter ẩn danh với tên do DSL sinh.

Ví dụ parameter có tên:

```java
String personName = "An";
Node person = Cypher.node("Person").named("p");

Statement statement = Cypher.match(person)
    .where(person.property("name")
        .isEqualTo(Cypher.parameter("personName", personName)))
    .returning(person)
    .build();
```

Query được render với `$personName`; giá trị không bị nối vào chuỗi Cypher:

```cypher
MATCH (p:`Person`) WHERE p.name = $personName RETURN p
```

Sau khi build, statement cung cấp thông tin parameter:

```java
import java.util.Collection;
import java.util.Map;

import org.neo4j.cypherdsl.core.Statement;

String cypher = statement.getCypher();
Collection<String> parameterNames = statement.getCatalog().getParameterNames();
Map<String, Object> parameterValues = statement.getCatalog().getParameters();
```

`getParameterNames()` liệt kê các placeholder có trong statement, kể cả placeholder chưa gắn giá trị. `getParameters()` chỉ chứa các parameter đã có value. Khi chạy statement, phải bảo đảm tất cả placeholder cần thiết đã được cấp giá trị theo API thực thi đang dùng.

Với giá trị được tạo từ một biến Java nhưng không cần đặt tên cố định, có thể dùng parameter ẩn danh:

```java
String personName = "An";
Node person = Cypher.node("Person").named("p");

var condition = person.property("name")
    .isEqualTo(Cypher.anonParameter(personName));
```

Cypher-DSL sinh tên parameter và lưu giá trị tương ứng trong catalog. Cách này hữu ích khi ghép nhiều điều kiện động mà không muốn tự quản lý tên parameter.

## 8. Phân biệt `parameter(...)` và `literalOf(...)`

Hai API này có mục đích khác nhau:

| API | Cách render | Dùng khi |
| --- | --- | --- |
| `Cypher.parameter("name", value)` | Placeholder `$name` và giá trị nằm trong parameter catalog | Dữ liệu đầu vào hoặc giá trị thay đổi theo lần gọi |
| `Cypher.anonParameter(value)` | Placeholder tự sinh và giá trị trong catalog | Dữ liệu đầu vào khi không cần tự đặt tên |
| `Cypher.literalOf(value)` | Literal được ghi trực tiếp trong câu Cypher | Hằng số cố định trong cấu trúc query hoặc ví dụ minh họa |

Không dùng `literalOf` để nhúng chuỗi do người dùng nhập vào query. Parameter giúp tách câu lệnh khỏi dữ liệu, giảm rủi ro injection và cho phép Neo4j tái sử dụng execution plan tốt hơn.

Parameter Cypher áp dụng cho giá trị. Một số phần cấu trúc của query như tên property không thể thay bằng parameter thông thường. Nếu cần cấu trúc động, hãy dùng API DSL phù hợp hoặc giới hạn đầu vào bằng allow-list; không nối chuỗi Cypher tùy tiện.

## 9. Ví dụ hoàn chỉnh: tìm người tham gia phim theo điều kiện

Ví dụ sau kết hợp node, relationship, property, condition và parameter. Truy vấn tìm những người tham gia phim có năm phát hành từ một mốc trở lên, đồng thời lọc theo tên người:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Relationship;
import org.neo4j.cypherdsl.core.Statement;

public class MovieStatements {

    public static Statement findActors(String personName, int minYear) {
        Node person = Cypher.node("Person").named("p");
        Node movie = Cypher.node("Movie").named("m");
        Relationship actedIn = person
            .relationshipTo(movie, "ACTED_IN")
            .named("r");

        return Cypher.match(actedIn)
            .where(person.property("name")
                    .isEqualTo(Cypher.parameter("personName", personName))
                .and(movie.property("released")
                    .gte(Cypher.parameter("minYear", minYear)))
            )
            .returningDistinct(person)
            .build();
    }
}
```

Kết quả Cypher có dạng:

```cypher
MATCH (p:`Person`)-[r:`ACTED_IN`]->(m:`Movie`)
WHERE (p.name = $personName AND m.released >= $minYear)
RETURN DISTINCT p
```

Các parameter được lấy từ statement:

```java
import java.util.Map;

Statement statement = MovieStatements.findActors("An", 2000);

String cypher = statement.getCypher();
Map<String, Object> parameters = statement.getCatalog().getParameters();
```

`cypher` chứa placeholder, còn `parameters` có các cặp `personName = "An"` và `minYear = 2000`. Không cần nối giá trị vào câu query.

## 10. Render statement thành chuỗi Cypher

Cypher-DSL tạo AST; `Renderer` chuyển AST thành chuỗi:

```java
import org.neo4j.cypherdsl.renderer.Renderer;
import org.neo4j.cypherdsl.core.Statement;

Statement statement = MovieStatements.findActors("An", 2000);
Renderer renderer = Renderer.getDefaultRenderer();
String cypher = renderer.render(statement);
```

Renderer mặc định escape label và relationship type bằng backtick, ví dụ `Person` thành `` `Person` ``. Đây là hành vi có chủ đích giúp tên được xử lý nhất quán. Có thể cấu hình renderer khác, nhưng chỉ nên tắt escaping khi có lý do và đã kiểm soát tên label/type.

Render chỉ tạo chuỗi Cypher; nó không kết nối hoặc chạy truy vấn. Để thực thi, truyền statement cho `Neo4jTemplate` hoặc executor của SDN, hoặc truyền chuỗi cùng parameter map cho Neo4j Java Driver/Neo4jClient.

### Chọn dialect theo phiên bản Neo4j

Cypher-DSL có dialect để điều chỉnh cách render một số hàm và cú pháp theo phiên bản server. Manual 2025.3.3 mô tả dialect mặc định hướng tới Neo4j 4.4 trở xuống và `Dialect.NEO4J_5` dành cho Neo4j 5. Với ứng dụng SDN, tài liệu getting-started khuyến nghị cấu hình dialect rõ ràng thay vì phụ thuộc mặc định:

```java
import org.neo4j.cypherdsl.core.renderer.Configuration;
import org.neo4j.cypherdsl.core.renderer.Dialect;
import org.springframework.context.annotation.Bean;

@Bean
Configuration cypherDslConfiguration() {
    return Configuration.newConfig()
        .withDialect(Dialect.NEO4J_5)
        .build();
}
```

Chọn dialect khớp phiên bản Neo4j thực tế. Nếu dự án còn hỗ trợ Neo4j 4, kiểm tra lại cú pháp được sinh trên cả hai môi trường trước khi thay đổi cấu hình.

## 11. Tích hợp `Statement` với Spring Data Neo4j

Từ SDN 6 trở lên, `Statement` có thể được dùng trực tiếp với `Neo4jTemplate` và `ReactiveNeo4jTemplate`. Ví dụ imperative:

```java
import java.util.Collection;

import org.neo4j.cypherdsl.core.Statement;
import org.springframework.data.neo4j.core.Neo4jTemplate;

public class PersonSearchService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonSearchService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public Collection<Person> findActors(String name, int minYear) {
        Statement statement = MovieStatements.findActors(name, minYear);
        return neo4jTemplate.findAll(statement, Person.class);
    }
}
```

`Neo4jTemplate` dùng mapping metadata của SDN để chuyển node trả về thành entity `Person`. Parameter values được khai báo trong statement bằng Cypher-DSL và đi cùng statement khi thực thi.

Nếu dùng repository, có thể thêm `CypherdslStatementExecutor<T>` để thực thi statement động:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslConditionExecutor;
import org.springframework.data.neo4j.repository.support.CypherdslStatementExecutor;

public interface PersonRepository extends
        Neo4jRepository<Person, String>,
        CypherdslConditionExecutor<Person>,
        CypherdslStatementExecutor<Person> {
}
```

Hai executor là hai fragment độc lập; chỉ cần kế thừa fragment phù hợp với nhu cầu. Ví dụ trên kế thừa cả hai để minh họa đầy đủ hai khả năng.

Executor cung cấp các phương thức như `findOne` và `findAll` nhận `Statement` hoặc phần builder tương ứng; các overload projection nhận thêm kiểu projection. Nếu chỉ cần thêm điều kiện động vào query do SDN sinh, có thể dùng `CypherdslConditionExecutor<T>`. Với repository reactive, dùng `ReactiveCypherdslStatementExecutor<T>` hoặc `ReactiveCypherdslConditionExecutor<T>` tương ứng.

Hai cách tích hợp có ý định khác nhau:

- `CypherdslConditionExecutor`: SDN vẫn tạo query theo mapping/repository; điều kiện Cypher-DSL được bổ sung vào query đó.
- `CypherdslStatementExecutor`: ứng dụng cung cấp một statement hoàn chỉnh và executor ánh xạ kết quả theo domain type hoặc projection được yêu cầu.

## 12. Tạo điều kiện động theo đầu vào

Một lợi ích lớn của DSL là có thể thêm điều kiện khi tham số có giá trị. Ví dụ bộ lọc tìm người theo tên và trạng thái tùy chọn:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Condition;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;

public class DynamicPersonQueries {

    public static Statement findPeople(String term, String status) {
        Node person = Cypher.node("Person").named("p");
        Condition condition = person.property("name")
            .contains(Cypher.parameter("term", term));

        if (status != null) {
            condition = condition.and(
                person.property("status")
                    .isEqualTo(Cypher.parameter("status", status))
            );
        }

        return Cypher.match(person)
            .where(condition)
            .returning(person)
            .build();
    }
}
```

Khi `status` null, query không chứa điều kiện status và cũng không có parameter `status`. Khi có giá trị, cả điều kiện lẫn parameter được thêm vào statement. Điều này thường rõ ràng hơn việc tạo một điều kiện kiểu `status IS NULL OR ...` nếu ý định thực sự là bỏ qua bộ lọc khi đầu vào không được cung cấp.

Nếu nhiều bộ lọc có thể bật/tắt, hãy tách việc tạo condition thành các hàm nhỏ và chỉ ghép những điều kiện được phép. Đừng dùng tên property hoặc relationship type trực tiếp từ request mà chưa xác thực.

## 13. Static metamodel và annotation processor

Trong ví dụ cơ bản, label và property được truyền bằng chuỗi như `"Person"`, `"name"` hoặc `"ACTED_IN"`. Điều này dễ bắt đầu nhưng vẫn có thể gõ sai tên khi domain model lớn.

Cypher-DSL có annotation processor cho SDN để sinh static metamodel từ lớp `@Node` và `@RelationshipProperties`. Metamodel cho phép tham chiếu label/property qua các hằng hoặc biểu thức Java được sinh thay vì lặp lại chuỗi. Đây là lựa chọn bổ sung cho dự án lớn; cần cấu hình processor đúng version và lưu ý giới hạn của processor theo tài liệu. Không cần metamodel để dùng Cypher-DSL.

## 14. Những lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query không tham chiếu đúng node | Không đặt tên hoặc dùng nhầm symbolic name | Dùng `named("p")` và tái sử dụng cùng biến Node |
| Relationship đi sai hướng | Nhầm `relationshipTo` với `relationshipFrom` | Đối chiếu hướng relationship thật trong graph |
| Condition không dùng được trong `where` | Ghép nhầm property expression với condition | Tạo condition từ phép so sánh như `isEqualTo`, `gte` |
| Giá trị đầu vào xuất hiện trực tiếp trong query | Dùng `literalOf` cho dữ liệu runtime | Dùng `parameter` hoặc `anonParameter` |
| Query có `$name` nhưng không có giá trị | Tạo placeholder mà không bind parameter | Gắn value bằng `parameter(name, value)` hoặc `.withValue(...)` |
| Chỉ render query nhưng không chạy được | Nhầm `Renderer` là executor | Dùng Neo4jTemplate, repository executor, Neo4jClient hoặc driver |
| Cypher không tương thích server | Dùng dialect mặc định không phù hợp | Cấu hình Cypher-DSL dialect theo phiên bản Neo4j |
| API DSL không có trong dependency | Version Cypher-DSL và SDN không tương thích | Kiểm tra BOM, dependency tree và manual đúng version |

## 15. Checklist khi xây query bằng Cypher-DSL

1. Khai báo node bằng `Cypher.node(label)` hoặc `Cypher.anyNode()`.
2. Đặt symbolic name cho node/relationship cần dùng ở nhiều nơi.
3. Dùng `relationshipTo`, `relationshipFrom` hoặc `relationshipBetween` đúng hướng.
4. Lấy property từ đúng node hoặc relationship.
5. Ghép condition bằng `and`, `or`, `not` theo logic nghiệp vụ.
6. Dùng parameter cho dữ liệu runtime; chỉ dùng literal cho hằng số có chủ đích.
7. Gọi `build()` để tạo `Statement` hoàn chỉnh.
8. Lấy query và parameter catalog từ cùng statement để tránh lệch placeholder/value.
9. Chọn đúng cách thực thi: render + driver/Neo4jClient, Neo4jTemplate hoặc repository executor.
10. Kiểm tra dialect và version compatibility với Neo4j server.

## Kết luận

Cypher-DSL biểu diễn truy vấn bằng các object Java: `Cypher.node()` tạo node pattern, `relationshipTo`/`relationshipFrom`/`relationshipBetween` tạo relationship, `property()` lấy property, các phép so sánh tạo condition và `parameter()` giữ dữ liệu đầu vào ngoài chuỗi query. Sau `build()`, `Statement` chứa AST cùng catalog parameter; có thể render bằng `Renderer` hoặc đưa trực tiếp cho `Neo4jTemplate` và Cypher-DSL repository executor của SDN. Hãy dùng parameter cho dữ liệu runtime, chọn hướng relationship đúng với graph và tách rõ bước xây dựng query với bước thực thi.

## Tài liệu tham khảo

- [The Neo4j Cypher-DSL Manual 2025.3.3](https://neo4j.github.io/cypher-dsl/2025.3.3/)
- [Spring Data Neo4j 8.1.1 — Spring Data Neo4j Extensions](https://docs.spring.io/spring-data/neo4j/reference/repositories/sdn-extension.html)
- [Spring Data Neo4j — Getting Started and Cypher-DSL Configuration](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
