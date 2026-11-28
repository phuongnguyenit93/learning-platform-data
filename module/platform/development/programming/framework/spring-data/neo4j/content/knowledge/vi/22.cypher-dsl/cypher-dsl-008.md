# Render Cypher, truyền tham số và kiểm tra tương thích dialect

Cypher-DSL cho phép xây dựng truy vấn Neo4j bằng Java API có kiểu thay vì nối chuỗi Cypher thủ công. Sau khi tạo cây biểu thức và hoàn thiện `Statement`, ứng dụng dùng `Renderer` để chuyển statement thành câu Cypher. Các tham số được giữ riêng với câu lệnh và bind khi thực thi qua Neo4j Java Driver hoặc `Neo4jClient`.

Một truy vấn được render thành công chưa có nghĩa là máy chủ Neo4j đích chắc chắn hỗ trợ mọi cú pháp trong truy vấn. Cần chọn dialect phù hợp với phiên bản máy chủ, kiểm tra chuỗi Cypher được sinh ra và chạy integration test trên đúng phiên bản Neo4j mà ứng dụng triển khai.

## 1. Vai trò của Statement, Renderer và Dialect

Quy trình làm việc cơ bản với Cypher-DSL gồm ba phần:

1. **Xây dựng Statement:** mô tả node, relationship, điều kiện, projection và thứ tự kết quả bằng Java API.
2. **Render:** dùng `Renderer` chuyển statement thành chuỗi Cypher và giữ nguyên các placeholder tham số.
3. **Thực thi:** bind giá trị vào placeholder rồi gửi câu lệnh đến Neo4j.

`Statement` biểu diễn cấu trúc truy vấn. `Renderer` quyết định cách biểu diễn cấu trúc đó thành văn bản Cypher. `Dialect` cho renderer biết phiên bản hoặc họ cú pháp Neo4j mục tiêu để lựa chọn cách render tương thích.

Renderer chỉ tạo câu truy vấn. Nó không kết nối máy chủ, không xác nhận quyền truy cập, không kiểm tra dữ liệu và không đảm bảo truy vấn sẽ chạy thành công trên database.

## 2. Khai báo dependency

Nếu ứng dụng sử dụng Cypher-DSL trực tiếp, khai báo thư viện `org.neo4j:neo4j-cypher-dsl` trong build. Ví dụ Maven:

```xml
<dependency>
    <groupId>org.neo4j</groupId>
    <artifactId>neo4j-cypher-dsl</artifactId>
    <version>${neo4j-cypher-dsl.version}</version>
</dependency>
```

`neo4j-cypher-dsl.version` là property do dự án quản lý; hãy chọn phiên bản tương thích với Java, Spring Data Neo4j và Neo4j Java Driver đang dùng. Nếu dự án sử dụng dependency management hoặc BOM, hãy theo cấu hình phiên bản đã được tổ chức kiểm soát thay vì tự nâng riêng một dependency.

Cypher-DSL và Spring Data Neo4j có vòng đời phát hành riêng. Việc starter SDN đã có một phiên bản thư viện gián tiếp không đồng nghĩa ứng dụng có thể gọi trực tiếp mọi API Cypher-DSL mà không khai báo dependency phù hợp.

## 3. Xây dựng Statement bằng Java API

Ví dụ truy vấn tìm một người theo tên. Ta khai báo node `Person`, đặt symbolic name là `p`, tạo điều kiện so sánh với named parameter `name`, rồi trả về node:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;

Node person = Cypher.node("Person").named("p");

Statement statement = Cypher.match(person)
        .where(person.property("name")
                .isEqualTo(Cypher.parameter("name")))
        .returning(person)
        .build();
```

Statement biểu diễn truy vấn tương đương về mặt ý nghĩa với Cypher:

```cypher
MATCH (p:Person)
WHERE p.name = $name
RETURN p
```

Điểm quan trọng là `Cypher.parameter("name")` tạo placeholder `$name`. Giá trị thực tế chưa được ghép vào câu lệnh ở bước xây dựng statement. Nhờ đó, cùng một statement có thể được dùng với nhiều tên khác nhau.

Cypher-DSL cung cấp API cho node, relationship, property, điều kiện và nhiều biểu thức Cypher. Nên chia nhỏ việc tạo statement thành các phương thức có tên theo nghiệp vụ khi truy vấn dài, để phần code Java vẫn thể hiện rõ mục đích của truy vấn.

## 4. Render Statement thành Cypher

`Renderer` chuyển `Statement` thành văn bản. Có thể dùng renderer mặc định hoặc cấu hình renderer tường minh:

```java
import org.neo4j.cypherdsl.core.renderer.Configuration;
import org.neo4j.cypherdsl.core.renderer.Dialect;
import org.neo4j.cypherdsl.core.renderer.Renderer;

Configuration configuration = Configuration.newConfig()
        .withDialect(Dialect.NEO4J_5)
        .build();

Renderer renderer = Renderer.getRenderer(configuration);
String cypher = renderer.render(statement).getCypher();
```

`cypher` là câu lệnh văn bản có placeholder `$name`. Việc render không thay thế placeholder bằng dữ liệu đầu vào. Các giá trị sẽ được bind khi thực thi.

Trong một ứng dụng, có thể cấu hình renderer một lần theo dialect của môi trường triển khai và tái sử dụng. Tránh tạo cấu hình renderer khác nhau rải rác trong nhiều service, vì các truy vấn cùng ứng dụng có thể được render theo cú pháp không nhất quán.

### Render mặc định và render tường minh

`Renderer.getDefaultRenderer()` phù hợp khi dialect mặc định của phiên bản Cypher-DSL khớp với môi trường mục tiêu và ứng dụng không cần chọn cấu hình riêng. Khi cần hỗ trợ một phiên bản Neo4j xác định, nên tạo `Configuration` với dialect tường minh.

Không dựa vào renderer mặc định nếu hệ thống có nhiều môi trường Neo4j với phiên bản khác nhau. Cấu hình rõ ràng giúp reviewer nhìn thấy phiên bản cú pháp mà ứng dụng hướng tới.

## 5. Bind named parameter khi thực thi

Sau khi render, truyền giá trị vào placeholder bằng `Neo4jClient`. Tên trong `.to("name")` phải trùng với tên trong `Cypher.parameter("name")`; không thêm dấu `$` vào chuỗi tên bind.

```java
import java.util.List;

import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;
import org.neo4j.cypherdsl.core.renderer.Renderer;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonSearchRepository {

    private final Neo4jClient neo4jClient;
    private final Renderer renderer;

    public PersonSearchRepository(Neo4jClient neo4jClient, Renderer renderer) {
        this.neo4jClient = neo4jClient;
        this.renderer = renderer;
    }

    public List<String> findPersonIdsByName(String name) {
        Node person = Cypher.node("Person").named("p");
        Statement statement = Cypher.match(person)
                .where(person.property("name")
                        .isEqualTo(Cypher.parameter("name")))
                .returning(person)
                .build();

        String cypher = renderer.render(statement).getCypher();

        return neo4jClient.query(cypher)
                .bind(name).to("name")
                .fetchAs(String.class)
                .mappedBy((typeSystem, record) -> record.get("p")
                        .asNode()
                        .get("personId")
                        .asString())
                .all();
    }
}
```

Ví dụ minh họa toàn bộ luồng: tạo statement, render thành Cypher, bind `name` và ánh xạ kết quả. Trong dự án thực tế, hãy đưa renderer thành bean dùng chung thay vì tạo lại trong từng repository, đồng thời dùng entity hoặc projection phù hợp với use case. Đoạn mapping trên giả định mỗi node `Person` có property `personId` kiểu chuỗi.

Nếu statement cũng khai báo các placeholder `$name` và `$minimumAge`, bind từng tham số với tên tương ứng:

```java
neo4jClient.query(cypher)
        .bind(name).to("name")
        .bind(minimumAge).to("minimumAge")
        .fetchAs(String.class)
        .mappedBy((typeSystem, record) -> record.get("p")
                .asNode().get("personId").asString())
        .all();
```

Giữ tham số tách biệt với câu Cypher giúp giá trị người dùng không bị diễn giải như cú pháp truy vấn. Không nối chuỗi tên, email hoặc dữ liệu request vào nội dung Cypher đã render.

## 6. Named parameter và giá trị literal

Với dữ liệu đến từ request hoặc nguồn bên ngoài, ưu tiên parameter:

```java
person.property("name").isEqualTo(Cypher.parameter("name"))
```

Parameter cho phép cùng một statement được tái sử dụng với các giá trị khác nhau. Nó cũng giúp query plan cache có cơ hội tái sử dụng kế hoạch khi cấu trúc truy vấn không đổi.

Literal phù hợp với hằng số do ứng dụng kiểm soát và thực sự là một phần cố định của cấu trúc truy vấn. Không dùng literal để nhúng dữ liệu người dùng vào câu Cypher. Nếu cần tạo label, relationship type hoặc property key động, hãy chọn từ danh sách identifier được whitelist trong code; parameter thông thường dùng cho giá trị chứ không thay thế tùy ý cấu trúc Cypher.

## 7. Chọn dialect phù hợp với Neo4j mục tiêu

Dialect mô tả tập cú pháp mà renderer hướng tới. Ví dụ, khi ứng dụng triển khai trên Neo4j 5, có thể cấu hình `Dialect.NEO4J_5`:

```java
Configuration neo4j5Configuration = Configuration.newConfig()
        .withDialect(Dialect.NEO4J_5)
        .build();

Renderer neo4j5Renderer = Renderer.getRenderer(neo4j5Configuration);
```

Nếu ứng dụng cần tương thích với một phiên bản Neo4j 4.x và phiên bản Cypher-DSL đang dùng cung cấp dialect tương ứng, có thể cấu hình dialect Neo4j 4:

```java
Configuration neo4j4Configuration = Configuration.newConfig()
        .withDialect(Dialect.NEO4J_4)
        .build();

Renderer neo4j4Renderer = Renderer.getRenderer(neo4j4Configuration);
```

Tên dialect và các tính năng renderer có thể thay đổi theo phiên bản Cypher-DSL. Hãy kiểm tra enum và tài liệu của đúng phiên bản dependency đã khóa trong dự án. Không sao chép một tên dialect từ ví dụ của phiên bản khác mà chưa xác minh nó tồn tại trong dependency hiện tại.

Chọn dialect cũ không làm cho mọi cú pháp mới tự động trở nên tương thích. Nếu statement sử dụng một tính năng mà máy chủ đích không hỗ trợ, truy vấn vẫn có thể thất bại. Dialect là hướng dẫn render, không phải bộ giả lập toàn bộ khả năng của Neo4j server.

## 8. Kiểm tra đầu ra render

Nên kiểm tra statement sau khi render để phát hiện lỗi cấu trúc trước khi gửi đến database. Với truy vấn ví dụ, có thể kiểm tra các thành phần chính:

```java
String cypher = renderer.render(statement).getCypher();

assertThat(cypher).contains("MATCH");
assertThat(cypher).contains("Person");
assertThat(cypher).contains("$name");
assertThat(cypher).contains("RETURN");
assertThat(cypher).doesNotContain("Lan");
```

Kiểm tra nên tập trung vào ý nghĩa và các placeholder quan trọng, tránh phụ thuộc quá mức vào khoảng trắng hoặc cách xuống dòng do renderer định dạng. Nếu dự án cần snapshot của Cypher, hãy cố định phiên bản Cypher-DSL và chủ động cập nhật snapshot khi nâng cấp thư viện.

Kiểm tra chuỗi render không xác nhận được rằng Neo4j server chấp nhận truy vấn. Nó chỉ xác nhận phần Java tạo ra văn bản như mong đợi.

## 9. Kiểm thử tương thích dialect theo nhiều lớp

Để giảm rủi ro khác biệt giữa môi trường phát triển và production, chia kiểm tra thành các lớp:

1. **Unit test cho statement:** xác nhận cấu trúc statement được xây dựng đúng từ Java API.
2. **Render test:** render bằng dialect mục tiêu và kiểm tra placeholder, label, relationship type, biểu thức cùng thứ tự các mệnh đề quan trọng.
3. **Integration test:** chạy câu Cypher đã render trên đúng phiên bản Neo4j mà ứng dụng hỗ trợ.
4. **Compatibility test khi nâng cấp:** chạy lại tập truy vấn đại diện khi thay phiên bản Neo4j hoặc Cypher-DSL.

Ví dụ unit test cho renderer:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;
import org.neo4j.cypherdsl.core.renderer.Configuration;
import org.neo4j.cypherdsl.core.renderer.Dialect;
import org.neo4j.cypherdsl.core.renderer.Renderer;

class PersonStatementTest {

    @Test
    void rendersNamedParameterForNeo4j5() {
        Node person = Cypher.node("Person").named("p");
        Statement statement = Cypher.match(person)
                .where(person.property("name")
                        .isEqualTo(Cypher.parameter("name")))
                .returning(person)
                .build();

        Renderer renderer = Renderer.getRenderer(
                Configuration.newConfig()
                        .withDialect(Dialect.NEO4J_5)
                        .build());

        String cypher = renderer.render(statement).getCypher();

        assertThat(cypher).contains("MATCH", "Person", "$name", "RETURN");
    }
}
```

Unit test này xác nhận renderer tạo được named parameter theo dialect đã chọn. Nó không khởi động Neo4j và không chứng minh truy vấn hợp lệ ở runtime.

Integration test cần gửi đúng câu Cypher cùng tham số đến một Neo4j server có phiên bản nằm trong ma trận hỗ trợ của ứng dụng. Có thể dùng Neo4j Testcontainers hoặc môi trường test chuyên biệt. Dữ liệu test nên bao gồm node có và không có property tùy chọn, relationship cần duyệt và các trường hợp biên mà truy vấn thực tế gặp phải.

Nếu ứng dụng hỗ trợ nhiều phiên bản Neo4j, chạy cùng tập integration test trên từng phiên bản được hỗ trợ. Không suy ra tương thích với Neo4j 4 chỉ từ việc truy vấn đã chạy thành công trên Neo4j 5.

## 10. Quản lý renderer như cấu hình ứng dụng

Trong ứng dụng Spring, có thể khai báo renderer thành bean để mọi repository hoặc component sử dụng cùng dialect:

```java
import org.neo4j.cypherdsl.core.renderer.Configuration;
import org.neo4j.cypherdsl.core.renderer.Dialect;
import org.neo4j.cypherdsl.core.renderer.Renderer;
import org.springframework.context.annotation.Bean;

@org.springframework.context.annotation.Configuration
public class CypherDslConfiguration {

    @Bean
    Renderer cypherRenderer() {
        Configuration configuration = Configuration.newConfig()
                .withDialect(Dialect.NEO4J_5)
                .build();
        return Renderer.getRenderer(configuration);
    }
}
```

Nếu dự án cần hỗ trợ nhiều dialect, có thể tạo renderer riêng theo cấu hình môi trường hoặc inject một factory quản lý renderer. Tránh chọn dialect từ một giá trị request tùy ý; dialect là quyết định triển khai và cần được kiểm soát như một phần cấu hình hệ thống.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ render đồng nghĩa với execute | Không có truy vấn nào được gửi đến Neo4j | Gọi `Neo4jClient` hoặc Driver sau khi render |
| Quên bind một named parameter | Neo4j nhận truy vấn thiếu tham số và báo lỗi | Đối chiếu `Cypher.parameter("name")` với `.to("name")` |
| Bind tên có dấu `$` | Tên bind không khớp quy ước API | Dùng `.to("name")`, giữ `$name` trong Cypher |
| Nối dữ liệu người dùng vào Cypher | Có nguy cơ injection và lỗi escape | Dùng named parameter |
| Dùng dialect không đúng phiên bản server | Câu Cypher có thể dùng cú pháp không được hỗ trợ | Chọn dialect mục tiêu và chạy integration test trên đúng server |
| Nghĩ dialect bảo đảm tương thích tuyệt đối | Tính năng không được server hỗ trợ vẫn có thể lỗi | Xác minh cú pháp bằng test thực tế trên phiên bản Neo4j đích |
| Dùng API Cypher-DSL không có trong dependency hiện tại | Lỗi biên dịch hoặc khác biệt hành vi | Khóa phiên bản và đối chiếu API của đúng release |
| So sánh chuỗi render quá cứng | Test hỏng vì khác format dù ý nghĩa không đổi | Kiểm tra thành phần quan trọng hoặc snapshot có kiểm soát |
| Cho phép request quyết định label hoặc relationship type tùy ý | Cấu trúc truy vấn có thể bị thao túng | Dùng danh sách identifier được whitelist |

## 12. Bài tập thực hành

Xây dựng một truy vấn tìm người theo tên bằng Cypher-DSL:

1. Tạo `Node` có label `Person` và symbolic name `p`.
2. Tạo điều kiện `p.name = $name` bằng `Cypher.parameter("name")`.
3. Hoàn thiện `Statement` và render bằng `Renderer`.
4. Chọn `Dialect.NEO4J_5` nếu môi trường test sử dụng Neo4j 5 và phiên bản DSL hỗ trợ dialect đó.
5. Kiểm tra chuỗi render có `MATCH`, `WHERE`, `$name` và `RETURN`.
6. Thực thi bằng `Neo4jClient`, bind giá trị qua `.bind(value).to("name")`.
7. Viết integration test trên đúng phiên bản Neo4j mục tiêu.
8. Nếu ứng dụng cần hỗ trợ một phiên bản Neo4j khác, tạo renderer tương ứng và chạy lại bộ kiểm thử tương thích.

Sau bài tập, cần giải thích được vai trò của `Statement`, `Renderer`, `Dialect`, vì sao parameter được bind sau khi render và vì sao unit render test chưa đủ để kết luận truy vấn tương thích với server.

## Kết luận

Cypher-DSL xây dựng truy vấn dưới dạng `Statement`, `Renderer` chuyển statement thành Cypher và named parameter giữ dữ liệu đầu vào tách khỏi cấu trúc câu lệnh. Chọn dialect tường minh theo phiên bản Neo4j mục tiêu, bind placeholder bằng `Neo4jClient` hoặc Driver và kiểm tra cả đầu ra render lẫn truy vấn thực tế. Unit test xác nhận cách render; integration test trên đúng phiên bản Neo4j mới xác nhận khả năng thực thi. Kết hợp các lớp kiểm tra này giúp truy vấn dễ bảo trì và giảm lỗi khi nâng cấp Cypher-DSL hoặc Neo4j.
