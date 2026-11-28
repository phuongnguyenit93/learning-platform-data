# Tìm entity bằng Cypher và tham số

Khi truy vấn của ứng dụng vượt quá khả năng của các phương thức repository được suy diễn từ tên, bạn có thể viết Cypher trực tiếp để mô tả chính xác đường đi trong đồ thị, điều kiện lọc và dữ liệu cần trả về. **Neo4jTemplate** là API của Spring Data Neo4j (SDN) dành cho trường hợp này: bạn cung cấp câu Cypher, map tham số và kiểu entity đích; SDN thực thi truy vấn rồi ánh xạ các node và relationship về object graph Java.

Thay vì nối giá trị người dùng vào chuỗi truy vấn, hãy đặt placeholder như **$city** hoặc **$email** và truyền giá trị qua **Map<String, Object>**. Cách này tách cấu trúc truy vấn khỏi dữ liệu đầu vào, giúp tránh lỗi dấu nháy, hỗ trợ tái sử dụng truy vấn và ngăn dữ liệu đầu vào làm thay đổi cú pháp Cypher.

Sau bài học, bạn có thể:

- Inject và sử dụng **Neo4jTemplate** trong service hoặc repository tùy chỉnh.
- Tìm một entity hoặc nhiều entity bằng **findOne()** và **findAll()**.
- Truyền tham số Cypher bằng map có tên.
- Ánh xạ node và relationship về entity theo metadata SDN.
- Gom relationship và node liên quan để mỗi root entity có một record.
- Chọn **Neo4jTemplate**, fluent find API hoặc **Neo4jClient** theo hình dạng kết quả.
- Phân trang truy vấn Cypher và xử lý các lỗi mapping, tham số, số lượng kết quả.

## 1. Neo4jTemplate trong tầng truy cập dữ liệu

**Neo4jTemplate** triển khai **Neo4jOperations** và cung cấp API làm việc với entity đã được SDN ánh xạ. Các repository đơn giản của SDN cũng ủy quyền nhiều thao tác cho template. Vì vậy, template là lựa chọn hữu ích khi bạn muốn kiểm soát câu Cypher mà vẫn nhận lại entity và relationship theo mapping đã khai báo.

Luồng xử lý cơ bản:

1. Service nhận tiêu chí tìm kiếm từ tầng gọi.
2. Service tạo câu Cypher có placeholder cho các giá trị.
3. Service tạo map tham số tương ứng với tên placeholder.
4. **Neo4jTemplate** gửi truy vấn và tham số đến Neo4j Java Driver.
5. SDN đọc các node và relationship trong record, sau đó ánh xạ chúng theo metadata entity.
6. Kết quả được trả về dưới dạng **Optional<T>** hoặc **List<T>**.

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| **findOne(cypher, parameters, domainType)** | **Optional<T>** | Đọc một entity |
| **findAll(cypher, parameters, domainType)** | **List<T>** | Đọc nhiều entity |
| **findById(id, domainType)** | **Optional<T>** | Đọc entity theo ID đã ánh xạ |
| **findAllById(ids, domainType)** | **List<T>** | Đọc nhiều entity theo ID |
| **find(domainType)** | Fluent find operation | Xây dựng truy vấn tìm kiếm theo từng bước |

Trong bài này, trọng tâm là hai phương thức nhận Cypher và map tham số: **findOne** và **findAll**.

## 2. Chuẩn bị entity và inject template

Giả sử ứng dụng quản lý người dùng:

~~~java
package com.acme.graph.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personCode;
    private String name;
    private String email;
    private String city;
    private Integer age;

    public Long getId() {
        return id;
    }

    public String getPersonCode() {
        return personCode;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getCity() {
        return city;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

**@Node("Person")** xác định label mà SDN dùng để ánh xạ lớp. **@Id** đánh dấu property định danh của entity; **@GeneratedValue** cho phép SDN nhận ID do Neo4j sinh theo cấu hình. Các property còn lại như **name**, **email**, **city** và **age** được ánh xạ từ thuộc tính node.

Inject **Neo4jTemplate** bằng constructor injection:

~~~java
package com.acme.graph.service;

import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonSearchService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }
}
~~~

Trong ứng dụng Spring Boot có starter SDN hoặc Spring context đã cấu hình SDN đúng cách, **Neo4jTemplate** được đăng ký như một bean. Không tự tạo một template mới cho từng lần gọi; hãy dùng bean do Spring quản lý để chia sẻ cấu hình Driver, mapping context, callback và transaction manager.

## 3. Tìm nhiều entity bằng findAll()

**findAll()** nhận ba đối số:

~~~java
findAll(String cypherQuery,
        Map<String, Object> parameters,
        Class<T> domainType)
~~~

- **cypherQuery**: câu Cypher cần chạy.
- **parameters**: map chứa giá trị cho các placeholder trong Cypher.
- **domainType**: lớp entity mà SDN sẽ ánh xạ kết quả.

Ví dụ tìm người ở một thành phố và có tuổi từ một ngưỡng trở lên:

~~~java
import java.util.List;
import java.util.Map;

import com.acme.graph.domain.Person;

public List<Person> findAdultsInCity(String city, int minAge) {
    String cypher = """
        MATCH (p:Person)
        WHERE p.city = $city
          AND p.age >= $minAge
        RETURN p
        ORDER BY p.name
        """;

    Map<String, Object> parameters = Map.of(
        "city", city,
        "minAge", minAge
    );

    return neo4jTemplate.findAll(
        cypher,
        parameters,
        Person.class
    );
}
~~~

Placeholder trong Cypher bắt đầu bằng **$**. Tên trong map không có ký tự **$**: truy vấn dùng **$city** thì map phải có key **"city"**. Giá trị của **domainType** là **Person.class**, vì truy vấn trả về node **p** cần được ánh xạ thành **Person**.

Kết quả của **findAll()** là **List<Person>**. Nếu không có node phù hợp, phương thức trả về danh sách rỗng, không phải **null**.

### Truy vấn với danh sách tham số

Cypher cũng có thể nhận một collection làm tham số. Ví dụ, tìm người có mã nghiệp vụ nằm trong danh sách:

~~~java
import java.util.List;
import java.util.Map;

public List<Person> findByPersonCodes(List<String> personCodes) {
    String cypher = """
        MATCH (p:Person)
        WHERE p.personCode IN $personCodes
        RETURN p
        ORDER BY p.personCode
        """;

    return neo4jTemplate.findAll(
        cypher,
        Map.of("personCodes", personCodes),
        Person.class
    );
}
~~~

Toán tử **IN** kiểm tra giá trị property có nằm trong collection hay không. Nếu danh sách đầu vào rỗng, hãy xác định trước hành vi nghiệp vụ mong muốn; thông thường service nên trả danh sách rỗng sớm thay vì gửi một truy vấn không cần thiết.

## 4. Tìm một entity bằng findOne()

**findOne()** có cùng cách truyền truy vấn và tham số, nhưng trả về **Optional<T>**:

~~~java
findOne(String cypherQuery,
        Map<String, Object> parameters,
        Class<T> domainType)
~~~

Ví dụ tìm một người theo email:

~~~java
import java.util.Map;
import java.util.Optional;

public Optional<Person> findByEmail(String email) {
    String cypher = """
        MATCH (p:Person {email: $email})
        RETURN p
        """;

    return neo4jTemplate.findOne(
        cypher,
        Map.of("email", email),
        Person.class
    );
}
~~~

**Optional.empty()** cho biết không tìm thấy entity. Ở tầng service, có thể chuyển trường hợp này thành lỗi nghiệp vụ hoặc phản hồi phù hợp:

~~~java
Person person = findByEmail(email)
    .orElseThrow(() ->
        new PersonNotFoundException(email)
    );
~~~

Nếu email phải nhận diện duy nhất một người, hãy tạo uniqueness constraint trên property đó:

~~~cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE
~~~

Điều kiện truy vấn của **findOne()** nên xác định tối đa một entity. Nếu cần kiểm tra nghiêm ngặt rằng truy vấn có không quá một kết quả, fluent API **one()** sẽ ném **IncorrectResultSizeDataAccessException** khi có nhiều hơn một kết quả.

## 5. Truyền tham số an toàn

Hãy luôn tách giá trị khỏi cấu trúc truy vấn:

~~~java
String cypher = """
    MATCH (p:Person)
    WHERE p.name = $name
    RETURN p
    """;

Map<String, Object> parameters = Map.of("name", userInput);
~~~

Không ghép trực tiếp dữ liệu đầu vào vào Cypher:

~~~java
// Không nên: dữ liệu đầu vào trở thành một phần của câu truy vấn.
String cypher = "MATCH (p:Person {name: '" + userInput + "'}) RETURN p";
~~~

Việc ghép chuỗi có thể làm hỏng cú pháp khi giá trị chứa dấu nháy, đồng thời mở ra nguy cơ Cypher injection. Dùng placeholder giúp Neo4j xử lý dữ liệu như giá trị tham số thay vì cú pháp truy vấn.

Một số lưu ý khi xây dựng map:

- Tên key phải khớp với placeholder trong Cypher.
- Kiểu giá trị phải được Neo4j Java Driver hỗ trợ hoặc có converter tương ứng trong SDN.
- Collection có thể được truyền làm tham số cho **IN**.
- Các kiểu số, chuỗi, boolean, ngày giờ và point có thể được truyền theo kiểu tương thích với Driver.
- **Map.of()** không chấp nhận key hoặc value là **null**; nếu tiêu chí có thể null, hãy xử lý nhánh truy vấn hoặc tạo map phù hợp và xác định rõ ngữ nghĩa của điều kiện null.

### Lọc tùy chọn với tham số null

Nếu **city** là bộ lọc tùy chọn, có thể viết điều kiện:

~~~cypher
MATCH (p:Person)
WHERE ($city IS NULL OR p.city = $city)
RETURN p
~~~

Khi **city** là **null**, vế đầu đúng nên không lọc theo thành phố. Khi có giá trị, vế thứ hai giới hạn kết quả. Có thể tạo **HashMap** để chứa tham số nullable:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

Map<String, Object> parameters = new HashMap<>();
parameters.put("city", city);

List<Person> people = neo4jTemplate.findAll(
    cypher,
    parameters,
    Person.class
);
~~~

Hãy phân biệt hai ý nghĩa: tham số null dùng để bỏ qua bộ lọc và yêu cầu tìm các node không có property. Với trường hợp thứ hai, có thể dùng **WHERE p.city IS NULL** trong một truy vấn riêng hoặc biểu thức điều kiện được thiết kế rõ ràng.

### Không thể bind tên label hoặc relationship type như một giá trị thông thường

Tham số Cypher dùng để truyền giá trị như email, tuổi hoặc danh sách mã. Không thể thay label hay relationship type bằng placeholder thông thường theo cách **MATCH (n:$label)**. Nếu ứng dụng cần lựa chọn cấu trúc truy vấn động, hãy giới hạn lựa chọn bằng danh sách giá trị được kiểm soát và chọn một câu truy vấn cố định tương ứng. Không đưa trực tiếp tên label hoặc relationship type do người dùng nhập vào chuỗi Cypher.

## 6. Ánh xạ entity có relationship

Nếu truy vấn chỉ trả về một node:

~~~cypher
MATCH (p:Person {email: $email})
RETURN p
~~~

SDN có thể ánh xạ node đó thành **Person**. Nếu muốn nạp thêm các relationship được khai báo trong entity, kết quả Cypher cần chứa root node, relationship và node đích tương ứng.

Ví dụ mô hình người tham gia phim:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String email;

    @Relationship(
        type = "ACTED_IN",
        direction = Relationship.Direction.OUTGOING
    )
    private List<ActingRole> actedIn;
}

@RelationshipProperties
public class ActingRole {

    @RelationshipId
    private Long id;

    private List<String> roles;

    @TargetNode
    private Movie movie;
}

@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
}
~~~

Truy vấn tìm một người và các phim người đó tham gia:

~~~cypher
MATCH (p:Person {email: $email})
OPTIONAL MATCH (p)-[r:ACTED_IN]->(m:Movie)
RETURN p,
       collect(r) AS actingRelationships,
       collect(m) AS movies
~~~

**OPTIONAL MATCH** giữ lại người ngay cả khi người đó chưa tham gia phim nào. **collect(r)** gom các relationship và **collect(m)** gom node đích. Kết quả có một record cho root **Person**, nhờ đó SDN có thể dựng danh sách **ActingRole** và node **Movie** tương ứng.

### Tránh nhiều record cho cùng root entity

Nếu truy vấn trả về:

~~~cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p, r, m
~~~

mỗi phim tạo một record. Khi một người tham gia nhiều phim, cùng một root **Person** xuất hiện ở nhiều record. Với custom query ánh xạ entity graph, hãy gom các relationship và node liên quan bằng **collect()** để có một record cho mỗi root entity:

~~~cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p, collect(r) AS actingRelationships, collect(m) AS movies
~~~

Nếu có nhiều nhánh relationship độc lập, việc nối tất cả trong một **MATCH** có thể tạo tích Descartes và làm các phần tử lặp lại. Hãy gom từng nhánh bằng subquery hoặc cấu trúc truy vấn riêng; chỉ dùng **collect(DISTINCT ...)** để loại phần tử trùng khi đã hiểu nguyên nhân tạo trùng.

## 7. Dùng fluent find API khi cần biểu đạt theo từng bước

Ngoài **findAll()** và **findOne()**, **Neo4jTemplate** cung cấp fluent find API. API này bắt đầu từ kiểu entity, nhận câu truy vấn và map tham số, sau đó kết thúc bằng thao tác lấy kết quả:

~~~java
List<Person> people = neo4jTemplate
    .find(Person.class)
    .matching(cypher, parameters)
    .all();
~~~

Khi muốn truy vấn phải trả về tối đa một entity:

~~~java
Optional<Person> person = neo4jTemplate
    .find(Person.class)
    .matching(cypher, parameters)
    .one();
~~~

**one()** trả về **Optional.empty()** nếu không có kết quả và ném **IncorrectResultSizeDataAccessException** nếu có nhiều hơn một kết quả. Đây là cách hữu ích để phát hiện điều kiện tìm kiếm không đủ chọn lọc thay vì âm thầm lấy một entity bất kỳ.

Fluent find API cũng có thể nhận **org.neo4j.cypherdsl.core.Statement** thay cho chuỗi Cypher. Khi dự án đã dùng Cypher-DSL, bạn có thể tạo statement bằng API Java có kiểu và truyền cùng map tham số. Cả hai cách đều kết thúc bằng **all()** hoặc **one()** để thực thi.

## 8. Phân trang và giới hạn kết quả trong Cypher

Các overload **findAll(cypher, parameters, domainType)** trả về **List<T>**, không tự nhận **Pageable**. Khi cần phân trang với Cypher tùy chỉnh, hãy đưa **SKIP** và **LIMIT** vào câu truy vấn và truyền chúng như tham số:

~~~java
public List<Person> findPeoplePage(
        String city,
        int page,
        int pageSize) {

    if (page < 0 || pageSize <= 0) {
        throw new IllegalArgumentException(
            "page phải >= 0 và pageSize phải > 0"
        );
    }

    String cypher = """
        MATCH (p:Person)
        WHERE p.city = $city
        RETURN p
        ORDER BY p.name, p.personCode
        SKIP $skip
        LIMIT $limit
        """;

    Map<String, Object> parameters = Map.of(
        "city", city,
        "skip", page * pageSize,
        "limit", pageSize
    );

    return neo4jTemplate.findAll(
        cypher,
        parameters,
        Person.class
    );
}
~~~

**ORDER BY** cần có thứ tự ổn định. Nếu chỉ sắp xếp theo tên và nhiều người có cùng tên, kết quả giữa các trang có thể thay đổi thứ tự; thêm một khóa phân biệt như **personCode** để ổn định hơn.

Nếu API cần tổng số bản ghi để hiển thị số trang, hãy chạy thêm truy vấn **count()** với cùng điều kiện lọc:

~~~cypher
MATCH (p:Person)
WHERE p.city = $city
RETURN count(p)
~~~

Gọi overload **count(String, Map<String, Object>)** của template:

~~~java
String countCypher = """
    MATCH (p:Person)
    WHERE p.city = $city
    RETURN count(p)
    """;

long total = neo4jTemplate.count(
    countCypher,
    Map.of("city", city)
);
~~~

Kết quả phân trang và tổng số là hai truy vấn riêng. Nếu dữ liệu thay đổi giữa hai lần chạy, tổng số và trang có thể phản ánh hai thời điểm khác nhau; cân nhắc transaction hoặc thiết kế API theo Slice/cursor khi không cần tổng số chính xác.

## 9. Chọn Neo4jTemplate hay Neo4jClient?

Hai API đều có thể chạy Cypher với tham số, nhưng mục tiêu mapping khác nhau:

| Nhu cầu | Nên dùng |
|---|---|
| Chạy Cypher và nhận **@Node** entity cùng relationship đã ánh xạ | **Neo4jTemplate** |
| Đọc một hoặc nhiều entity theo query tùy chỉnh | **Neo4jTemplate.findOne() / findAll()** |
| Trả về record, map hoặc giá trị tổng hợp tùy chỉnh | **Neo4jClient** |
| Tự định nghĩa mapping từ **Record** sang DTO | **Neo4jClient.fetchAs(...).mappedBy(...)** |
| Thao tác CRUD đơn giản theo ID hoặc derived finder | Repository |

Nếu truy vấn trả về các property riêng như **p.name**, **count(r)** hoặc map tổng hợp, **Person.class** không phải kiểu kết quả phù hợp. Hãy dùng **Neo4jClient** để đọc record hoặc ánh xạ DTO. **Neo4jTemplate** hữu ích nhất khi kết quả truy vấn là node và relationship cần được SDN dựng thành entity graph.

## 10. Những lỗi thường gặp

**Tên placeholder không khớp key trong map.** Cypher dùng **$personCode** nhưng map lại chứa **"code"**. Hãy kiểm tra tên tham số ở cả hai nơi.

**Nối dữ liệu đầu vào vào chuỗi Cypher.** Cách này dễ gây lỗi cú pháp và Cypher injection. Dùng placeholder và map tham số.

**Trả về property thay vì node nhưng yêu cầu ánh xạ entity.** **RETURN p.name** trả về chuỗi, không phải node **Person**. Hãy trả về **p** hoặc dùng **Neo4jClient** cho kết quả scalar.

**Thiếu relationship hoặc node đích trong kết quả.** Nếu cần dựng object graph, hãy trả về root, relationship và node đích tương ứng. Dùng **collect()** để gom các nhánh vào một record cho mỗi root.

**Tạo nhiều record cho cùng root.** Truy vấn nhiều nhánh có thể lặp root và nhân bản relationship. Gom từng nhánh, tránh tích Descartes và kiểm tra dữ liệu trùng.

**Dùng findOne() cho điều kiện không duy nhất.** Hãy bảo đảm điều kiện có tính duy nhất bằng constraint hoặc dùng **findAll()** nếu nghiệp vụ cho phép nhiều kết quả. Fluent **one()** giúp phát hiện trường hợp có nhiều hơn một kết quả.

**Bỏ qua kết quả Optional.** **findOne()** không bảo đảm luôn có entity. Xử lý **Optional.empty()** rõ ràng trong service.

**Dùng tham số để thay label hoặc relationship type.** Placeholder thông thường chỉ đại diện cho giá trị. Hãy giữ cấu trúc Cypher cố định hoặc kiểm soát lựa chọn cấu trúc bằng whitelist.

**Truy vấn quá rộng.** **findAll()** có thể tải lượng entity lớn. Hãy lọc root, tạo index cho property tìm kiếm thường dùng, giới hạn kết quả và kiểm tra kế hoạch bằng **EXPLAIN** hoặc **PROFILE**.

## 11. Tự kiểm tra

1. **Neo4jTemplate.findAll()** nhận những đối số nào và trả về kiểu gì?
2. **findOne()** khác **findAll()** ở kiểu kết quả và cách xử lý khi không tìm thấy entity như thế nào?
3. Vì sao nên truyền giá trị qua **Map<String, Object>** thay vì nối chuỗi Cypher?
4. Vì sao truy vấn ánh xạ entity cần trả về node thay vì chỉ trả về property của node?
5. Khi entity có relationship, vì sao cần trả về root, relationship và node đích?
6. Vì sao cần gom relationship bằng **collect()** để có một record cho mỗi root entity?
7. Khi nào nên dùng **Neo4jClient** thay cho **Neo4jTemplate**?
8. Vì sao truy vấn phân trang nên có thứ tự ổn định?

**Bài tập thực hành:** Tạo **PersonSearchService** dùng **Neo4jTemplate**. Viết phương thức tìm nhiều người theo thành phố và tuổi tối thiểu bằng **findAll()**, phương thức tìm một người theo email bằng **findOne()**, và phương thức tìm theo danh sách **personCode** với toán tử **IN**. Bổ sung truy vấn phân trang có **ORDER BY**, **SKIP**, **LIMIT**. Sau đó mở rộng mô hình **Person** có relationship **ACTED_IN** đến **Movie**, viết Cypher dùng **OPTIONAL MATCH** và **collect()** để trả về một record cho mỗi người cùng các phim liên quan. Kiểm tra trường hợp người chưa có relationship và trường hợp truy vấn trả về nhiều record cho cùng root.

## Tài liệu tham khảo

- [Spring Data Neo4j API — Neo4jTemplate](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j API — Neo4jOperations](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/Neo4jOperations.html)
- [Spring Data Neo4j — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j — Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Cypher Manual — Parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)
