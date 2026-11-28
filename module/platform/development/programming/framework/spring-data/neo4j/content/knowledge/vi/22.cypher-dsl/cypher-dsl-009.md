# Phân biệt Cypher-DSL với Querydsl hoặc JPA Criteria

Bài học này thuộc chương **Cypher-DSL** của module **SPRING_DATA_NEO4J**. Khi cần tạo truy vấn động trong Java, có nhiều API dạng fluent hoặc builder trông khá giống nhau: Neo4j Cypher-DSL, Querydsl và JPA Criteria. Tuy nhiên, chúng được thiết kế cho những mô hình truy vấn và hệ sinh thái persistence khác nhau. Chọn đúng API giúp tận dụng được khả năng của Neo4j, tránh mang các giả định từ cơ sở dữ liệu quan hệ sang graph database.

**Cypher-DSL là DSL chuyên biệt để xây dựng câu lệnh Cypher.** Querydsl là một framework truy vấn tổng quát hơn, có tích hợp với Spring Data Neo4j nhưng bị giới hạn trong phần điều kiện động. JPA Criteria là API chuẩn của Jakarta Persistence để tạo truy vấn cho JPA provider; nó không phải API truy vấn của Spring Data Neo4j.

## 1. Cypher-DSL là gì?

Neo4j Cypher-DSL cung cấp API Java để xây dựng câu lệnh Cypher bằng các đối tượng như `Node`, `Relationship`, `Property`, `Condition`, `Statement` và các bước builder. Thay vì ghép chuỗi Cypher bằng phép nối string, ứng dụng xây dựng một cấu trúc cú pháp (Abstract Syntax Tree - AST), sau đó có thể render AST thành câu Cypher.

Ví dụ truy vấn tìm người sống tại Hà Nội:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;
import org.neo4j.cypherdsl.core.renderer.Renderer;

Node person = Cypher.node("Person").named("person");

Statement statement = Cypher.match(person)
    .where(person.property("city")
        .isEqualTo(Cypher.parameter("city", "Hà Nội")))
    .returning(person)
    .build();

String cypher = Renderer.getDefaultRenderer().render(statement);
```

Statement được tạo ra tương ứng với câu Cypher có dạng:

```cypher
MATCH (person:`Person`)
WHERE person.city = $city
RETURN person
```

Tên tham số `city` được khai báo rõ trong ví dụ. Giá trị `Hà Nội` được giữ riêng như parameter của statement, không cần nối trực tiếp vào chuỗi truy vấn. Nếu dùng `Cypher.anonParameter(value)`, renderer sẽ tự sinh tên parameter; không nên phụ thuộc vào tên nội bộ đó.

### AST và renderer

Cypher-DSL xây dựng AST trước khi sinh câu Cypher. Điều này mang lại một số lợi ích:

- Các bước builder giới hạn cách ghép cú pháp, giúp phát hiện nhiều lỗi cấu trúc ngay khi biên dịch.
- Các thành phần AST và bước trung gian là immutable; mỗi thao tác builder trả về một bước mới.
- Statement có thể được render thành chuỗi hoặc truyền trực tiếp cho API Spring Data Neo4j hỗ trợ `Statement`.
- Parameter được quản lý riêng với cú pháp truy vấn, giảm nhu cầu ghép dữ liệu đầu vào vào câu lệnh.
- Có thể biểu diễn node, relationship, direction, path, `WHERE`, `WITH`, `RETURN`, aggregation và các cấu trúc Cypher khác.

Cypher-DSL giúp xây dựng câu lệnh đúng hình dạng cú pháp, nhưng không tự chứng minh rằng label, relationship type, property name hay logic nghiệp vụ tồn tại trong database. Nếu truyền tên label hoặc property bằng chuỗi, lỗi chính tả vẫn có thể chỉ được phát hiện khi chạy truy vấn. Annotation processor tạo static metamodel có thể giảm rủi ro này.

## 2. Cypher-DSL được dùng ở đâu trong Spring Data Neo4j?

SDN sử dụng Cypher-DSL trong hạ tầng tạo truy vấn. Ứng dụng có thể sử dụng statement được xây dựng trực tiếp với `Neo4jTemplate`, hoặc thêm repository mixin để tạo điều kiện động hay toàn bộ câu truy vấn.

Có ba cách tích hợp đáng chú ý:

| API | Vai trò | Phạm vi tùy biến |
|---|---|---|
| `Neo4jTemplate` với `Statement` | Thực thi statement do ứng dụng tạo | Truy vấn đầy đủ; kết quả có thể ánh xạ thành entity |
| `CypherdslConditionExecutor` | Thêm điều kiện Cypher-DSL vào truy vấn SDN tự sinh | Điều kiện, sắp xếp, phân trang, đếm và tồn tại |
| `CypherdslStatementExecutor` | Thực thi statement Cypher-DSL hoàn chỉnh qua repository | Toàn bộ cấu trúc truy vấn, bao gồm traversal và projection |

Hai executor là repository mixin độc lập. Có thể thêm một hoặc cả hai vào repository tùy nhu cầu. Với repository reactive, dùng các biến thể `ReactiveCypherdslConditionExecutor` và `ReactiveCypherdslStatementExecutor` tương ứng.

## 3. Cypher-DSL Condition Executor: chỉ thêm điều kiện vào truy vấn sinh sẵn

`CypherdslConditionExecutor` phù hợp khi cấu trúc truy vấn cơ bản vẫn do Spring Data Neo4j tạo, nhưng điều kiện lọc thay đổi theo đầu vào.

Khai báo repository:

```java
import com.example.graph.domain.Person;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslConditionExecutor;

public interface PersonRepository
        extends Neo4jRepository<Person, String>,
                CypherdslConditionExecutor<Person> {
}
```

Tạo điều kiện và dùng lại cho các thao tác:

```java
import java.util.Collection;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;

import org.neo4j.cypherdsl.core.Condition;
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;

Node person = Cypher.node("Person").named("person");
Condition cityIsHanoi = person.property("city")
    .isEqualTo(Cypher.anonParameter("Hà Nội"));

Collection<Person> people = personRepository.findAll(cityIsHanoi);
long total = personRepository.count(cityIsHanoi);
boolean exists = personRepository.exists(cityIsHanoi);
```

Executor sẽ bổ sung `Condition` vào truy vấn được SDN tạo cho entity gốc. Các thao tác như `findAll`, `findOne`, `count`, `exists`, sắp xếp và phân trang có thể sử dụng điều kiện này.

Điểm quan trọng là `CypherdslConditionExecutor` chỉ nhận một `Condition`; nó không thay thế toàn bộ câu truy vấn. Khi cần tự khai báo nhiều `MATCH`, traversal qua relationship, `WITH`, `UNWIND`, aggregation hoặc cách gom kết quả đặc thù, hãy dùng `CypherdslStatementExecutor` hay `Neo4jTemplate` với một `Statement` đầy đủ.

## 4. Cypher-DSL Statement Executor: xây dựng toàn bộ truy vấn

Khi cần kiểm soát graph traversal, ứng dụng có thể khai báo `CypherdslStatementExecutor`:

```java
import com.example.graph.domain.Person;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslStatementExecutor;

public interface PersonGraphRepository
        extends Neo4jRepository<Person, String>,
                CypherdslStatementExecutor<Person> {
}
```

Ví dụ tìm người sống tại một thành phố. Truy vấn trả node gốc, relationship `LIVES_AT` và node `Address` ở đầu còn lại:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Relationship;
import org.neo4j.cypherdsl.core.Statement;

static Statement peopleLivingIn(String city) {
    Node person = Cypher.node("Person").named("person");
    Node address = Cypher.node("Address").named("address");
    Relationship livesAt = person.relationshipTo(address, "LIVES_AT");

    return Cypher.match(livesAt)
        .where(address.property("city")
            .isEqualTo(Cypher.parameter("city", city)))
        .returning(
            person.getRequiredSymbolicName(),
            Cypher.collect(livesAt),
            Cypher.collect(address)
        )
        .build();
}
```

Gọi repository:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonGraphRepository;

Collection<Person> people = personGraphRepository.findAll(
    peopleLivingIn("Hà Nội")
);
```

Ở đây, truy vấn hoàn chỉnh do ứng dụng tạo. `collect(livesAt)` và `collect(address)` gom các relationship và node liên quan để có một record cho mỗi `Person` gốc. Điều này quan trọng khi ánh xạ collection relationship vào entity. Nếu truy vấn trả một record cho mỗi cạnh với cùng root node, SDN không tự động hợp nhất các record đó thành một graph hoàn chỉnh.

`CypherdslStatementExecutor` cung cấp các overload `findOne`, `findAll` và các biến thể projection. Statement phải trả dữ liệu đủ để ánh xạ domain type: node gốc, relationship và các node liên quan cần thiết. Với `findOne`, statement phải trả không quá một record có thể ánh xạ.

## 5. Dùng Statement trực tiếp với Neo4jTemplate

Không nhất thiết phải thêm repository mixin nếu use case phù hợp với template:

```java
import java.util.Collection;

import com.example.graph.domain.Person;

import org.neo4j.cypherdsl.core.Statement;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonGraphService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonGraphService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public Collection<Person> findPeopleLivingIn(String city) {
        Statement statement = peopleLivingIn(city);
        return neo4jTemplate.findAll(statement, Person.class);
    }
}
```

Statement có thể được truyền trực tiếp vào các API template hỗ trợ Cypher-DSL. Không cần render thành chuỗi trước khi gọi. Nếu cần dùng Neo4j Java Driver hoặc API chỉ nhận chuỗi Cypher, có thể render bằng `Renderer` và truyền các parameter do statement cung cấp.

## 6. Cypher-DSL khác Querydsl ở đâu?

Querydsl là framework xây dựng truy vấn bằng Java fluent API, thường dùng các kiểu metamodel được sinh ra như `QPerson`. Nó hỗ trợ nhiều backend và có thể được tích hợp vào Spring Data thông qua `QuerydslPredicateExecutor`.

Spring Data Neo4j hỗ trợ cả `QuerydslPredicateExecutor` và `CypherdslConditionExecutor`. Hai executor có mục tiêu tương tự: SDN tạo truy vấn cơ bản, ứng dụng cung cấp predicate hoặc condition để bổ sung điều kiện.

Ví dụ repository dùng Querydsl:

```java
import com.example.graph.domain.Person;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface PersonQuerydslRepository
        extends Neo4jRepository<Person, String>,
                QuerydslPredicateExecutor<Person> {
}
```

Giả sử Querydsl đã tạo `QPerson` cho entity:

```java
import com.querydsl.core.types.Predicate;
import com.example.graph.domain.Person;
import com.example.graph.domain.QPerson;
import com.example.graph.repository.PersonQuerydslRepository;

QPerson person = QPerson.person;
Predicate predicate = person.city.eq("Hà Nội")
    .and(person.active.isTrue());

Iterable<Person> people = personQuerydslRepository.findAll(predicate);
```

Querydsl có thể phù hợp khi đội ngũ đã quen API này hoặc đang dùng cùng một phong cách predicate ở nhiều Spring Data store. Tuy nhiên, tài liệu Spring Data Neo4j nêu rõ một số giới hạn trong tích hợp:

- Cần thêm thư viện Querydsl vào classpath; đây không phải DSL mà SDN dùng làm nền tảng truy vấn.
- Predicate của Querydsl trong tích hợp này không hỗ trợ traversal qua relationship của graph.
- API predicate không cung cấp cách truyền parameter vào truy vấn được tạo, dù bản thân Querydsl có khái niệm parameter.
- Querydsl phù hợp hơn với điều kiện trên các thuộc tính của entity gốc; truy vấn graph phức tạp cần Cypher-DSL hoặc Cypher trực tiếp.

Cypher-DSL được SDN khuyến nghị cho điều kiện động vì nó là công cụ mà SDN sử dụng tự nhiên. Nó hỗ trợ tham số Cypher và mô hình hóa relationship/path, đồng thời có thể mở rộng từ một `Condition` tới một `Statement` hoàn chỉnh.

Hai hệ sinh thái cũng có thể phối hợp: Cypher-DSL cung cấp `Cypher.adapt(...)` để chuyển một số `Querydsl Predicate` hoặc `Expression` thành `Condition`/`Expression` của Cypher-DSL. Đây là adapter tùy chọn cần `querydsl-core`; nó cho phép tái sử dụng Q-type trong lúc xây dựng một `Statement`. Cách này khác với việc chỉ thêm `QuerydslPredicateExecutor` vào repository, và truy vấn cuối cùng vẫn được biểu diễn bằng Cypher-DSL.

## 7. Cypher-DSL khác JPA Criteria ở đâu?

JPA Criteria là API chuẩn của Jakarta Persistence. Nó xây dựng truy vấn thông qua `CriteriaBuilder`, `CriteriaQuery`, `Root`, `Join` và `Predicate`, sau đó được thực thi bởi JPA provider thông qua `EntityManager`.

Ví dụ truy vấn một entity quan hệ bằng JPA Criteria:

Giả sử `entityManager` được inject và `PersonEntity` là một lớp được đánh dấu `@Entity` trong ứng dụng JPA:

```java
import java.util.List;

import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;

CriteriaBuilder builder = entityManager.getCriteriaBuilder();
CriteriaQuery<PersonEntity> query =
    builder.createQuery(PersonEntity.class);

Root<PersonEntity> person = query.from(PersonEntity.class);
query.select(person)
    .where(builder.equal(person.get("city"), "Hà Nội"));

List<PersonEntity> result = entityManager.createQuery(query)
    .getResultList();
```

Đoạn mã này thuộc hệ sinh thái JPA: nó cần `EntityManager`, entity được quản lý bởi JPA và một JPA provider. Spring Data Neo4j không cung cấp `EntityManager` hoặc triển khai `CriteriaQuery` cho Neo4j repository. Không thể truyền một `CriteriaQuery` vào `Neo4jRepository` để thực thi Cypher.

Hai API có điểm giống nhau ở cách tạo predicate và query bằng object thay vì nối chuỗi, nhưng ngôn ngữ đích và mô hình dữ liệu khác nhau:

- JPA Criteria mô tả truy vấn trên entity và association của mô hình persistence JPA.
- Cypher-DSL mô tả pattern node, relationship, path và clause của ngôn ngữ Cypher.
- JPA Criteria được thực thi qua `EntityManager` và JPA provider.
- Cypher-DSL được render hoặc chuyển thành `Statement` cho Neo4j Java Driver, `Neo4jClient`, `Neo4jTemplate` hay SDN repository executor.

Nếu một ứng dụng dùng cả PostgreSQL qua Spring Data JPA và Neo4j qua Spring Data Neo4j, có thể dùng JPA Criteria cho phần dữ liệu quan hệ và Cypher-DSL cho phần graph. Hai API tồn tại song song ở hai persistence boundary khác nhau; không thay thế lẫn nhau.

## 8. Bảng so sánh tổng hợp

| Tiêu chí | Cypher-DSL | Querydsl trong SDN | JPA Criteria |
|---|---|---|---|
| Ngôn ngữ đích | Cypher | Predicate được SDN chuyển thành điều kiện Cypher | Criteria query được JPA provider chuyển thành SQL |
| Mô hình chính | Node, relationship, path, clause | Predicate trên metamodel entity | Root, path, join, predicate trên JPA entity |
| Kiểu an toàn | API builder kiểm tra cấu trúc Cypher; static metamodel là tùy chọn | Q-type/metamodel được sinh | Generic API và metamodel JPA |
| Traversal graph | Có | Hạn chế trong tích hợp SDN; không hỗ trợ traversal relationship | Join association của mô hình JPA, không phải Cypher graph traversal |
| Parameter | Hỗ trợ parameter Cypher trong statement/condition | Không có API binding parameter trong predicate của tích hợp SDN | Hỗ trợ parameter expression qua Criteria API |
| Tích hợp SDN | Native; condition executor, statement executor, template | Có `QuerydslPredicateExecutor`, cần dependency thêm | Không được SDN hỗ trợ |
| Trường hợp phù hợp | Điều kiện động, traversal và truy vấn graph tùy biến | Điều kiện đơn giản trên entity gốc, khi đã quen Querydsl | Ứng dụng JPA với truy vấn động trên mô hình quan hệ |

## 9. Static metamodel của Cypher-DSL

Cypher-DSL có thể dùng trực tiếp với tên label và property dạng chuỗi:

```java
Node person = Cypher.node("Person").named("person");
person.property("firstName");
```

Để giảm lỗi tên field, dự án cung cấp annotation processor cho Spring Data Neo4j. Processor đọc các entity được đánh dấu `@Node` và `@RelationshipProperties`, cùng metadata `@Relationship` và `@Property`, rồi tạo static metamodel trong source build.

Ví dụ entity `Person` có thể sinh ra lớp metamodel `Person_`. Các API Cypher-DSL có thể sử dụng thông tin này để tham chiếu label và property mà không phải lặp lại mọi tên dưới dạng chuỗi.

Một cấu hình Gradle có dạng:

```groovy
dependencies {
    annotationProcessor "org.neo4j:neo4j-cypher-dsl-codegen-sdn6:${cypherDslVersion}"
}
```

`cypherDslVersion` cần được đặt theo phiên bản Cypher-DSL tương thích với Spring Data Neo4j đang dùng. Nên đặt processor trên annotation processor path riêng, không thêm nó vào runtime artifact nếu ứng dụng không cần processor khi chạy.

Static metamodel được sinh từ domain classes trong mã nguồn, không phải từ việc kết nối và introspect schema database. Nó giúp đồng bộ tên property giữa Java và truy vấn, nhưng không thay thế migration, index, constraint hay kiểm tra dữ liệu thực tế.

## 10. Chọn dialect phù hợp với phiên bản Neo4j

Cypher-DSL có cấu hình dialect để điều chỉnh cú pháp được render theo phiên bản Neo4j đích. Tài liệu Spring Data Neo4j 8.1.x cho biết dialect mặc định hướng tới Neo4j 5 LTS và tương thích Neo4j 5.23+ cùng Neo4j 2025.x. Nếu chạy phiên bản cũ hơn, cần cấu hình dialect phù hợp.

Ví dụ dùng dialect Neo4j 4:

```java
import org.neo4j.cypherdsl.core.renderer.Dialect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CypherDslConfiguration {

    @Bean
    org.neo4j.cypherdsl.core.renderer.Configuration cypherDslConfiguration() {
        return org.neo4j.cypherdsl.core.renderer.Configuration.newConfig()
            .withDialect(Dialect.NEO4J_4)
            .build();
    }
}
```

Khi chạy Neo4j 5 hoặc phiên bản mới hơn được dialect mặc định hỗ trợ, hãy giữ cấu hình phù hợp với phiên bản server. Dialect ảnh hưởng cú pháp được render; nó không tự nâng cấp server hoặc làm cho một tính năng chưa được server hỗ trợ trở nên khả dụng.

## 11. Chọn API theo nhu cầu

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| CRUD và finder đơn giản theo mapping entity | `Neo4jRepository` và derived query |
| Truy vấn cố định, muốn khai báo bằng chuỗi Cypher | `@Query` |
| Điều kiện động trên truy vấn SDN tự sinh | `CypherdslConditionExecutor` |
| Điều kiện động đơn giản, đội ngũ đã dùng Querydsl và chấp nhận giới hạn | `QuerydslPredicateExecutor` |
| Tự xây dựng `MATCH`, relationship traversal, aggregation hoặc projection | `CypherdslStatementExecutor` |
| Tạo statement rồi thực thi trong service hoặc component riêng | `Neo4jTemplate` với `Statement` |
| Truy vấn JPA trên database quan hệ | JPA Criteria qua `EntityManager` |

Không cần dùng Cypher-DSL cho mọi truy vấn. Derived query và `@Query` vẫn rõ ràng cho các trường hợp đơn giản hoặc truy vấn tĩnh. Cypher-DSL phát huy giá trị khi cấu trúc query hoặc điều kiện được tạo động, cần tham chiếu nhiều node/relationship hoặc muốn tái sử dụng các mảnh truy vấn an toàn hơn.

## 12. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ Cypher-DSL là JPA Criteria phiên bản graph | Chỉ nhìn thấy cú pháp builder giống nhau | Xác định ngôn ngữ đích: Cypher hay JPA Criteria/JPQL |
| Dùng Querydsl để duyệt nhiều relationship trong SDN | Querydsl integration chỉ bổ sung predicate cho query sinh sẵn | Dùng `CypherdslStatementExecutor` hoặc `Neo4jTemplate` |
| Ghép giá trị đầu vào vào chuỗi Cypher | Không dùng parameter của Cypher-DSL | Dùng `Cypher.parameter` hoặc `Cypher.anonParameter` |
| Cho rằng tên property được kiểm tra theo schema database khi biên dịch | DSL mặc định có thể nhận tên label/property dạng chuỗi | Dùng static metamodel và integration test |
| Dùng Condition Executor cho một truy vấn graph hoàn chỉnh | Nhầm condition với statement | Dùng Statement Executor khi cần tự tạo toàn bộ query |
| Statement trả thiếu dữ liệu để hydrate entity | Chỉ trả root node hoặc một phần relationship | Trả các node/cạnh cần thiết; gom relationship bằng `collect()` để có một record cho mỗi root |
| Render cú pháp không tương thích server | Chọn dialect sai phiên bản | Cấu hình dialect phù hợp với Neo4j đang chạy |
| Tái sử dụng bước builder cũ | Các bước AST là immutable | Gán và tiếp tục dùng giá trị được trả về từ mỗi thao tác builder |

## 13. Kiểm thử và xác nhận truy vấn

Vì Cypher-DSL tạo AST trước khi render, có thể kiểm tra đầu ra truy vấn mà không cần kết nối database:

```java
Statement statement = peopleLivingIn("Hà Nội");
String cypher = Renderer.getDefaultRenderer().render(statement);

assertThat(cypher).contains("MATCH");
assertThat(cypher).contains("LIVES_AT");
assertThat(statement.getCatalog().getParameters()).containsEntry("city", "Hà Nội");
```

Kiểm tra render hữu ích để phát hiện lỗi cấu trúc, alias hoặc parameter. Tuy nhiên, nó không xác nhận rằng label/property tồn tại hoặc query plan hiệu quả. Cần bổ sung integration test với Neo4j để xác nhận:

1. Query chạy được trên đúng phiên bản server và dialect.
2. Parameter được bind đúng, kể cả dữ liệu có dấu nháy hoặc ký tự đặc biệt.
3. Relationship traversal dùng đúng type và direction.
4. Kết quả có đủ node, relationship và property để SDN hydrate entity/projection.
5. Mỗi root chỉ xuất hiện trong một record nếu truy vấn hydrate collection relationship.
6. Index/constraint và `EXPLAIN`/`PROFILE` đáp ứng yêu cầu hiệu năng.

## 14. Nguyên tắc cần nhớ

- Cypher-DSL là DSL chuyên biệt cho Cypher, xây dựng AST và tạo `Statement` có thể render hoặc truyền trực tiếp cho API SDN hỗ trợ.
- `CypherdslConditionExecutor` thêm điều kiện vào query SDN tự sinh; `CypherdslStatementExecutor` nhận toàn bộ statement do ứng dụng xây dựng.
- Querydsl được SDN hỗ trợ như một lựa chọn predicate, nhưng thiếu relationship traversal và API binding parameter trong tích hợp này.
- JPA Criteria thuộc Jakarta Persistence và không phải API truy vấn cho `Neo4jRepository`.
- Static metamodel của Cypher-DSL là tùy chọn, được sinh từ entity SDN chứ không phải từ schema database.
- Chọn dialect theo phiên bản Neo4j đích và kiểm thử query trên server thật.
- Dùng parameter thay cho ghép chuỗi, và kiểm tra cả cấu trúc query lẫn kết quả mapping.

Khi làm việc với Spring Data Neo4j, hãy ưu tiên Cypher-DSL cho các truy vấn động cần hiểu cấu trúc graph. Querydsl có thể hữu ích cho điều kiện đơn giản nếu đội ngũ đã sử dụng nó, còn JPA Criteria dành cho phần ứng dụng dùng JPA. Phân biệt được ngôn ngữ đích, mức độ tùy biến và cơ chế thực thi giúp chọn đúng công cụ cho từng persistence boundary.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.1 – Spring Data Neo4j Extensions](https://docs.spring.io/spring-data/neo4j/reference/repositories/sdn-extension.html)
- [Spring Data Neo4j 8.1.2 – Getting started and Cypher-DSL dialect](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
- [Neo4j Cypher-DSL 2025.3.3 – Manual](https://neo4j.github.io/cypher-dsl/2025.3.3/)
- [Spring Data Neo4j 8.1.1 – CypherdslConditionExecutor API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/CypherdslConditionExecutor.html)
- [Jakarta Persistence – CriteriaBuilder API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/persistence/criteria/CriteriaBuilder.html)
