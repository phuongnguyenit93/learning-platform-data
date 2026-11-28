# Truy vấn đầy đủ bằng CypherdslStatementExecutor

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của CypherdslStatementExecutor trong Spring Data Neo4j.
- Kết hợp executor với Neo4jRepository để chạy truy vấn được xây dựng bằng Cypher-DSL.
- Tạo một Statement đầy đủ gồm MATCH, WHERE và RETURN.
- Bind tham số ngay trong Cypher-DSL mà không ghép chuỗi dữ liệu đầu vào.
- Trả về entity hoặc projection và cung cấp đủ node, relationship để SDN ánh xạ.
- Sử dụng findOne, findAll và overload phân trang.
- Phân biệt truy vấn đầy đủ với cách chỉ bổ sung điều kiện vào truy vấn do SDN sinh.

## 1. Khi nào cần CypherdslStatementExecutor?

Spring Data Neo4j (SDN) cung cấp nhiều cách tạo truy vấn:

- Derived query tạo Cypher từ tên phương thức repository.
- @Query cho phép viết Cypher tường minh dưới dạng chuỗi.
- CypherdslConditionExecutor cho phép thêm điều kiện Cypher-DSL vào truy vấn mà SDN tự xây dựng.
- CypherdslStatementExecutor cho phép ứng dụng tự xây dựng toàn bộ câu truy vấn bằng Cypher-DSL rồi chuyển trực tiếp cho repository thực thi.

Cypher-DSL là API Java kiểu builder để mô tả cấu trúc Cypher. Thay vì ghép chuỗi, ta tạo các đối tượng đại diện cho node, relationship, property, condition và statement. Kết quả cuối cùng là một Statement chứa cây cú pháp của truy vấn.

CypherdslStatementExecutor phù hợp khi cấu trúc truy vấn thay đổi theo yêu cầu nghiệp vụ, ví dụ:

- Bộ lọc có thể xuất hiện hoặc biến mất tùy tham số.
- Ứng dụng chọn loại relationship hoặc đường đi theo lựa chọn được kiểm soát.
- Truy vấn cần nhiều nhánh, điều kiện hoặc phép tổng hợp.
- Cùng một repository cần trả entity hoặc projection từ các statement được tạo lúc chạy.

Nếu chỉ cần một điều kiện động trên truy vấn CRUD chuẩn do SDN tạo, CypherdslConditionExecutor thường đơn giản hơn. Nếu truy vấn ổn định và dễ đọc dưới dạng Cypher, @Query vẫn là lựa chọn phù hợp.

## 2. Khai báo repository với CypherdslStatementExecutor

CypherdslStatementExecutor nằm trong package:

~~~java
import org.springframework.data.neo4j.repository.support.CypherdslStatementExecutor;
~~~

Có thể thêm interface này cùng Neo4jRepository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslStatementExecutor;

public interface PersonRepository
        extends Neo4jRepository<Person, String>,
                CypherdslStatementExecutor<Person> {
}
~~~

Tham số generic Person là domain type mà repository quản lý. Spring Data repository infrastructure cung cấp implementation cho mixin này; thông thường không cần tự viết class triển khai CypherdslStatementExecutor.

Đây là API imperative. Với repository reactive, dùng ReactiveCypherdslStatementExecutor<Person> cùng ReactiveNeo4jRepository:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import org.springframework.data.neo4j.repository.support.ReactiveCypherdslStatementExecutor;

public interface ReactivePersonRepository
        extends ReactiveNeo4jRepository<Person, String>,
                ReactiveCypherdslStatementExecutor<Person> {
}
~~~

Không trộn lẫn hai kiểu lập trình trong cùng luồng xử lý. Bài này tập trung vào imperative repository và các kiểu kết quả như Optional, Collection và Page.

## 3. Tạo mô hình node và relationship

Ví dụ quản lý Person và địa chỉ. Một Person có thể có nhiều địa chỉ:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String firstName;
    private boolean active;

    @Relationship(
        type = "LIVES_AT",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Address> addresses = new LinkedHashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Node địa chỉ:

~~~java
@Node("Address")
public class Address {

    @Id
    private String addressId;

    private String city;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Trong Neo4j, một Person có thể được nối đến nhiều Address:

~~~text
(p:Person)-[:LIVES_AT]->(a1:Address)
(p:Person)-[:LIVES_AT]->(a2:Address)
~~~

Khi truy vấn để ánh xạ đầy đủ Person, statement cần trả về node gốc cùng các relationship và node đích mà domain model yêu cầu. Chỉ trả về node Person có thể không đủ để dựng collection addresses từ custom query.

## 4. Xây dựng Statement bằng Cypher-DSL

Các thành phần thường dùng nằm trong package org.neo4j.cypherdsl.core:

- Cypher: điểm bắt đầu để tạo node, relationship và statement.
- Node: đại diện cho một node pattern.
- Relationship: đại diện cho relationship pattern.
- Condition: biểu diễn điều kiện WHERE.
- Statement: kết quả của quá trình xây dựng câu truy vấn.
- Functions: cung cấp các hàm Cypher như collect.

Ví dụ tạo truy vấn tìm Person theo personId và lấy cả các địa chỉ:

~~~java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Functions;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Relationship;
import org.neo4j.cypherdsl.core.Statement;

public final class PersonStatements {

    private PersonStatements() {
    }

    public static Statement byPersonId(String personId) {

        Node person = Cypher.node("Person").named("p");
        Node address = Cypher.node("Address").named("a");

        Relationship livesAt =
            person.relationshipTo(address, "LIVES_AT");

        return Cypher.match(livesAt)
            .where(
                person.property("personId")
                    .isEqualTo(Cypher.anonParameter(personId))
            )
            .returning(
                person.getRequiredSymbolicName(),
                Functions.collect(livesAt),
                Functions.collect(address)
            )
            .build();
    }
}
~~~

Có thể đọc truy vấn theo từng bước:

1. Cypher.node("Person").named("p") tạo node có label Person và bí danh p.
2. Cypher.node("Address").named("a") tạo node đích có label Address và bí danh a.
3. person.relationshipTo(address, "LIVES_AT") mô tả relationship đi từ Person đến Address.
4. Cypher.match(livesAt) bắt đầu phần MATCH bằng relationship pattern.
5. where(...) lọc Person theo personId.
6. returning(...) trả node gốc, collection relationship và collection node đích.
7. build() hoàn tất statement.

Functions.collect gom các relationship và node đích thành collection. Cách trả kết quả này giúp SDN ánh xạ một Person cùng các Address liên quan trong một record.

Truy vấn được tạo ra tương đương về ý nghĩa với Cypher:

~~~cypher
MATCH (p:Person)-[r:LIVES_AT]->(a:Address)
WHERE p.personId = $personId
RETURN p, collect(r), collect(a)
~~~

Tên biến và cách escape label có thể khác khi renderer tạo chuỗi, nhưng cấu trúc truy vấn và tham số vẫn giữ nguyên.

## 5. Bind tham số ngay trong Cypher-DSL

Một điểm quan trọng của CypherdslStatementExecutor là tham số phải được khai báo trong statement bằng Cypher-DSL. Executor nhận Statement, không nhận một Map tham số riêng như một số API truy vấn khác.

Có hai cách phổ biến.

### Tham số ẩn danh

~~~java
Cypher.anonParameter(personId)
~~~

Cypher-DSL tự tạo tên tham số và gắn giá trị personId vào statement. Đây là cách ngắn gọn khi không cần tên tham số ổn định trong chuỗi Cypher.

### Tham số có tên

~~~java
Cypher.parameter("personId", personId)
~~~

Tham số có tên tạo placeholder $personId và giữ giá trị tương ứng trong catalog của statement. Cách này hữu ích khi cần đọc Cypher được sinh ra hoặc kiểm tra danh sách tham số trong lúc debug.

Ví dụ:

~~~java
Node person = Cypher.node("Person").named("p");

Statement statement = Cypher.match(person)
    .where(
        person.property("personId")
            .isEqualTo(Cypher.parameter("personId", personId))
    )
    .returning(person)
    .build();
~~~

Không nối trực tiếp personId vào chuỗi Cypher. Tham số giữ dữ liệu tách biệt khỏi cấu trúc truy vấn và tránh lỗi cú pháp hoặc Cypher injection.

Label và relationship type là thành phần cấu trúc của pattern. Chúng không phải giá trị property để bind như $personId. Nếu cần chọn label hoặc relationship type động, hãy ánh xạ lựa chọn đầu vào qua danh sách giá trị được ứng dụng kiểm soát rồi mới tạo node/relationship pattern tương ứng.

## 6. Thực thi bằng findOne

Sau khi có Statement, truyền trực tiếp nó cho repository:

~~~java
Optional<Person> person =
    personRepository.findOne(
        PersonStatements.byPersonId("person-101")
    );
~~~

findOne trả về Optional<T>:

- Optional.empty() nếu không có record phù hợp.
- Optional.of(entity) nếu có đúng một record có thể ánh xạ.

Statement dùng với findOne phải trả về không quá một record mappable. Nếu query có thể khớp nhiều Person, hãy dùng findAll hoặc điều chỉnh điều kiện để xác định duy nhất một node. Không dựa vào findOne để tự chọn ngẫu nhiên một record trong nhiều kết quả.

Với ví dụ trên, personId nên là khóa duy nhất của Person. Có thể bảo đảm điều đó bằng constraint phù hợp trong Neo4j.

## 7. Thực thi bằng findAll

Nếu truy vấn có thể trả về nhiều Person, dùng findAll:

~~~java
Statement statement =
    PersonStatements.peopleWithFirstName("An");

Collection<Person> people =
    personRepository.findAll(statement);
~~~

findAll(Statement) trả về Collection<T> chứa các domain object được ánh xạ từ kết quả truy vấn.

Có thể viết helper tương ứng:

~~~java
public static Statement peopleWithFirstName(String firstName) {

    Node person = Cypher.node("Person").named("p");
    Node address = Cypher.node("Address").named("a");
    Relationship livesAt =
        person.relationshipTo(address, "LIVES_AT");

    return Cypher.match(livesAt)
        .where(
            person.property("firstName")
                .isEqualTo(Cypher.anonParameter(firstName))
        )
        .returning(
            person.getRequiredSymbolicName(),
            Functions.collect(livesAt),
            Functions.collect(address)
        )
        .build();
}
~~~

Nếu Person không có Address vẫn cần xuất hiện trong kết quả, truy vấn cần dùng OPTIONAL MATCH thay cho MATCH bắt buộc. Hãy chọn loại pattern theo quy tắc nghiệp vụ: MATCH chỉ trả Person có Address; OPTIONAL MATCH giữ Person kể cả khi không có Address.

## 8. Truy vấn động với nhiều điều kiện tùy chọn

Cypher-DSL hữu ích khi các điều kiện WHERE thay đổi theo tham số đầu vào.

Ví dụ, ứng dụng luôn lọc Person đang hoạt động, nhưng chỉ lọc thêm firstName khi người dùng cung cấp giá trị:

~~~java
import org.neo4j.cypherdsl.core.Condition;

public static Statement activePeople(String firstName) {

    Node person = Cypher.node("Person").named("p");

    Condition condition =
        person.property("active")
            .isEqualTo(Cypher.literalOf(true));

    if (firstName != null && !firstName.isBlank()) {
        condition = condition.and(
            person.property("firstName")
                .isEqualTo(Cypher.anonParameter(firstName))
        );
    }

    return Cypher.match(person)
        .where(condition)
        .returning(person)
        .build();
}
~~~

Cách xây dựng này có một cấu trúc query thống nhất:

- Điều kiện active luôn tồn tại.
- Điều kiện firstName chỉ được thêm khi có dữ liệu.
- Giá trị firstName vẫn được bind thành parameter.
- returning(person) xác định node cần ánh xạ.

Nếu domain entity có relationship cần tải, phần RETURN phải mở rộng thêm các relationship và node tương ứng như ví dụ ở phần trước. Đừng trả một node đơn giản rồi giả định SDN sẽ tự bổ sung mọi nhánh mà statement không truy vấn.

## 9. Trả về projection thay cho domain entity

Executor hỗ trợ projection thông qua overload nhận Class<PT>.

Ví dụ projection:

~~~java
public interface PersonNameView {

    String getPersonId();

    String getFirstName();
}
~~~

Thực thi:

~~~java
Collection<PersonNameView> names =
    personRepository.findAll(
        activePeople(null),
        PersonNameView.class
    );
~~~

Hoặc lấy một projection:

~~~java
Optional<PersonNameView> name =
    personRepository.findOne(
        PersonStatements.byPersonId("person-101"),
        PersonNameView.class
    );
~~~

Projection giúp giới hạn dữ liệu trả về theo nhu cầu đọc. Nó hữu ích khi màn hình chỉ cần một số property, không cần đưa toàn bộ entity và relationship ra ngoài.

Có thể dùng DTO class hoặc record làm projection nếu kiểu dữ liệu và mapping phù hợp với quy tắc projection của Spring Data. Hãy bảo đảm statement trả về các property cần cho projection và tên property có thể được ánh xạ đúng.

## 10. Phân trang bằng CypherdslStatementExecutor

Executor có overload trả về Page<T> hoặc Page<PT>. Khác với findAll(Statement) thông thường, overload phân trang nhận một phần statement kiểu StatementBuilder.OngoingReadingAndReturn, một countQuery và Pageable.

Ví dụ tạo phần query tìm Person đang hoạt động:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.neo4j.cypherdsl.core.StatementBuilder;

public static StatementBuilder.OngoingReadingAndReturn activePeopleForPage() {

    Node person = Cypher.node("Person").named("p");

    return Cypher.match(person)
        .where(
            person.property("active")
                .isEqualTo(Cypher.literalOf(true))
        )
        .returning(person);
}
~~~

Count query:

~~~java
public static Statement countActivePeople() {

    Node person = Cypher.node("Person").named("p");

    return Cypher.match(person)
        .where(
            person.property("active")
                .isEqualTo(Cypher.literalOf(true))
        )
        .returning(Cypher.count(person))
        .build();
}
~~~

Gọi repository:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("firstName"),
        Sort.Order.asc("personId")
    )
);

Page<PersonNameView> page = personRepository.findAll(
    PersonStatements.activePeopleForPage(),
    PersonStatements.countActivePeople(),
    pageable,
    PersonNameView.class
);
~~~

Executor sử dụng Pageable để thêm thứ tự, offset và giới hạn kết quả. Vì vậy, phần statement chính là một phần đọc có RETURN; không tự thêm SKIP và LIMIT nếu muốn executor quản lý phân trang.

countQuery được chạy riêng để tính tổng số kết quả, từ đó tạo totalElements và totalPages. Điều kiện trong count query phải khớp với điều kiện lọc của query chính. Nếu query chính lọc active Person nhưng count query đếm tất cả Person, thông tin phân trang sẽ sai.

### Khi nào dùng overload Page?

Dùng overload Page khi giao diện cần:

- Tổng số phần tử.
- Tổng số trang.
- Số trang hiện tại.
- Điều hướng đến một trang cụ thể.

Nếu không cần tổng số trang, hãy cân nhắc thiết kế query trả về collection hoặc dùng cơ chế phân trang khác phù hợp với use case. API CypherdslStatementExecutor được mô tả ở đây cung cấp overload Page cho statement builder cùng count query.

## 11. Transaction và phạm vi sử dụng

Các phương thức executor chạy qua Spring Data repository infrastructure, vì vậy có thể tham gia transaction do Spring quản lý. Nếu một use case cần nhiều thao tác đọc cùng nhìn thấy một trạng thái nhất quán, hãy đặt ranh giới transaction ở service:

~~~java
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonSearchService {

    private final PersonRepository people;

    public PersonSearchService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public Optional<Person> findWithAddresses(String personId) {
        return people.findOne(
            PersonStatements.byPersonId(personId)
        );
    }
}
~~~

CypherdslStatementExecutor cung cấp các phương thức findOne và findAll để đọc entity hoặc projection. Nếu cần thực hiện command ghi dữ liệu bằng Cypher động, hãy cân nhắc Neo4jClient, Neo4jTemplate hoặc custom repository fragment phù hợp với thao tác ghi. Không dùng một query chỉ trả graph một phần làm nguồn để ghi lại toàn bộ entity.

## 12. Phân biệt CypherdslStatementExecutor và CypherdslConditionExecutor

Hai mixin đều dùng Cypher-DSL nhưng mức độ kiểm soát khác nhau:

| Tiêu chí | CypherdslConditionExecutor | CypherdslStatementExecutor |
|---|---|---|
| Phạm vi tùy chỉnh | Bổ sung điều kiện vào query SDN tạo | Tự tạo toàn bộ statement |
| MATCH và RETURN | SDN quản lý theo domain metadata | Người viết statement quyết định |
| Phù hợp khi | Chỉ cần điều kiện động | Cần pattern, relationship, return hoặc cấu trúc query động |
| Kiểu đầu vào | Condition và có thể có Sort | Statement hoặc phần statement dùng cho Page |
| Ánh xạ | Query được tạo theo domain | Statement phải trả đủ dữ liệu để ánh xạ entity/projection |

Nếu chỉ muốn thêm điều kiện firstName vào truy vấn tìm Person chuẩn, ConditionExecutor có thể đủ. Nếu muốn tự chọn pattern Person-[:LIVES_AT]->Address, gom relationship và quyết định dữ liệu trả về, StatementExecutor phù hợp hơn.

Hai mixin có thể cùng được khai báo trên một repository khi ứng dụng thật sự cần cả hai cách truy vấn.

## 13. Lưu ý về record và mapping graph

CypherdslStatementExecutor không tự suy đoán toàn bộ graph mà ứng dụng muốn đọc. Statement phải trả về các node, relationship và property cần thiết cho kiểu kết quả.

Ví dụ Person có collection Address:

~~~cypher
MATCH (p:Person)-[r:LIVES_AT]->(a:Address)
WHERE p.personId = $personId
RETURN p, collect(r), collect(a)
~~~

Nếu chỉ trả về p, phần addresses có thể không được hydrate như mong đợi từ custom statement.

Khi có nhiều nhánh relationship, hãy chú ý Cartesian product. Nếu một Person có nhiều Address và nhiều Project, MATCH cả hai nhánh cùng lúc có thể tạo nhiều record cho cùng một Person. Hãy gom từng nhánh bằng collect hoặc subquery để giữ một record cho root cùng các collection tương ứng.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy phương thức findOne/findAll | Repository chưa extends CypherdslStatementExecutor | Thêm mixin với đúng domain type |
| Statement chạy nhưng thiếu relationship | RETURN chỉ có node gốc | Trả thêm relationship và node đích cần hydrate |
| findOne phát sinh lỗi nhiều kết quả | Query khớp nhiều record | Dùng findAll hoặc lọc bằng định danh duy nhất |
| Giá trị đầu vào làm hỏng query | Ghép chuỗi vào Cypher | Dùng anonParameter hoặc parameter có tên |
| Projection thiếu property | Statement không trả property mà projection yêu cầu | Bổ sung property vào RETURN |
| Page có tổng số sai | countQuery khác điều kiện query chính | Đồng bộ điều kiện lọc và cách đếm |
| Page có thứ tự không ổn định | Pageable không có Sort hoặc sort thiếu tie-breaker | Cung cấp Sort xác định |
| Relationship bị nhân bản | Nhiều nhánh MATCH tạo Cartesian product | Gom từng nhánh trước khi kết hợp |
| Không dùng được executor trong reactive repository | Dùng mixin imperative | Dùng ReactiveCypherdslStatementExecutor |

## 14. Debug statement được tạo

Cypher-DSL cho phép lấy chuỗi Cypher đã render từ Statement để kiểm tra cấu trúc:

~~~java
import java.util.Map;

Statement statement =
    PersonStatements.byPersonId("person-101");

String cypher = statement.getCypher();
~~~

Có thể xem thêm tên và giá trị tham số trong catalog của statement:

~~~java
Map<String, Object> parameters =
    statement.getCatalog().getParameters();
~~~

Đây là cách kiểm tra query được tạo từ nhánh điều kiện động nào. Trong log ứng dụng, tránh ghi dữ liệu nhạy cảm từ tham số nếu query chứa thông tin cá nhân hoặc bí mật.

Khi cần so sánh với Cypher chạy trực tiếp trong Neo4j Browser, có thể dùng chuỗi statement.getCypher() và kiểm tra các placeholder $.... Hãy bảo đảm các giá trị tham số tương ứng được bind trong statement.

## 15. Bài tập thực hành

Tạo một repository:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, String>,
                CypherdslStatementExecutor<Person> {
}
~~~

Tạo các yêu cầu:

1. Dùng Cypher.node("Person").named("p") để tạo node Person.
2. Viết statement tìm Person theo personId bằng Cypher.anonParameter.
3. Trả về một Person bằng findOne.
4. Viết statement tìm Person active và trả về collection bằng findAll.
5. Tạo projection PersonNameView và gọi overload findAll(statement, PersonNameView.class).
6. Tạo query có điều kiện firstName tùy chọn.
7. Tạo count statement và gọi overload Page cùng Pageable.
8. Thêm relationship LIVES_AT và trả về root node, collection relationship và Address node.
9. Thử viết query có hai nhánh relationship rồi kiểm tra số record trung gian; sau đó gom từng nhánh để tránh nhân bản root.

Các câu hỏi tự kiểm tra:

- CypherdslStatementExecutor khác CypherdslConditionExecutor ở đâu?
- Vì sao tham số cần được tạo ngay trong Cypher-DSL?
- findOne yêu cầu số record như thế nào?
- Vì sao custom statement phải trả cả relationship và node đích?
- Overload Page cần thêm những đối số nào?
- Nếu countQuery không dùng cùng điều kiện lọc với query chính thì điều gì xảy ra?

## Kết luận

CypherdslStatementExecutor là repository mixin cho phép ứng dụng tự tạo toàn bộ câu truy vấn bằng Cypher-DSL rồi chuyển Statement trực tiếp cho Spring Data Neo4j. Đây là lựa chọn phù hợp khi query có cấu trúc động, nhiều relationship hoặc cần kiểm soát chính xác phần dữ liệu trả về.

Hãy xây dựng node, relationship, điều kiện và RETURN bằng API Cypher-DSL; bind giá trị qua anonParameter hoặc parameter; và bảo đảm statement trả đủ dữ liệu cho entity hoặc projection. Dùng findOne khi query có tối đa một record, findAll cho nhiều kết quả, và overload Page khi cần count query cùng Pageable. Với repository reactive, dùng ReactiveCypherdslStatementExecutor.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 API: CypherdslStatementExecutor](https://docs.spring.io/spring-data/data-neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/CypherdslStatementExecutor.html)
- [Spring Data Neo4j FAQ: Các lựa chọn cho custom query động](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Cypher-DSL Manual](https://neo4j.github.io/cypher-dsl/)
