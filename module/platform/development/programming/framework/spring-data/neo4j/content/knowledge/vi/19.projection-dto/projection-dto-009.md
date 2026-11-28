# Phạm vi thuộc tính và relationship được cập nhật khi lưu projection

Projection trong Spring Data Neo4j (SDN) không chỉ giúp đọc một phần dữ liệu. Nó còn có thể đóng vai trò như một bản thiết kế (blueprint) xác định những thuộc tính và relationship nào được phép tham gia vào thao tác lưu. Cơ chế này hữu ích khi một màn hình chỉ chỉnh sửa thông tin liên hệ của người dùng, trong khi node còn có nhiều thuộc tính và quan hệ khác được quản lý bởi các nghiệp vụ riêng.

Nếu dùng thao tác lưu entity thông thường cho một object chỉ được nạp một phần, các relationship chưa được nạp có thể bị hiểu như dữ liệu đã bị loại bỏ. `Neo4jTemplate` cung cấp `saveAs(...)` và fluent save API để giới hạn phạm vi ghi bằng projection. Muốn dùng đúng cơ chế này, cần hiểu rõ field nào nằm trong projection, relationship lồng nhau được mở rộng tới đâu và vì sao phải nạp đủ dữ liệu của những quan hệ dự định lưu lại.

## 1. Projection như một bản thiết kế cho thao tác lưu

Giả sử ứng dụng quản lý `Person` với các thông tin:

- Thuộc tính của node: `code`, `name`, `email`, `phone`, `status`.
- Relationship tới `Team`: một người có thể tham gia nhiều nhóm.
- Thuộc tính của relationship `MEMBER_OF`: `role` và `joinedAt`.

Một trang hồ sơ chỉ cho phép sửa `name` và `email`. Nếu tải toàn bộ graph chỉ để cập nhật hai trường này, ứng dụng phải đọc và quản lý nhiều dữ liệu hơn nhu cầu. Nếu tạo một entity mới chỉ chứa `id`, `name`, `email` rồi gọi `repository.save(...)`, entity đó không còn phản ánh đầy đủ trạng thái các quan hệ đã tồn tại.

Projection cho phép nói rõ: thao tác này chỉ làm việc với `id`, `name` và `email`. Khi lưu với projection đó, SDN chỉ cập nhật những thuộc tính và relationship được khai báo trong projection. Những thuộc tính và relationship không thuộc projection nằm ngoài phạm vi của thao tác lưu.

Phân biệt hai khái niệm:

- **Projection khi đọc:** giới hạn dữ liệu được lấy từ Neo4j và đưa vào kết quả.
- **Projection khi lưu:** giới hạn thuộc tính và relationship được SDN xem xét trong thao tác ghi.

Một projection có thể dùng cho cả hai mục đích, nhưng việc trả về projection từ repository không tự động làm cho mọi thao tác `save` tiếp theo bị giới hạn theo projection đó. Muốn giới hạn thao tác lưu, hãy dùng API lưu projection của `Neo4jTemplate`.

## 2. Mô hình entity minh họa

Entity `Person` có cả property đơn giản và collection relationship:

```java
import java.time.LocalDate;
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String name;
    private String email;
    private String phone;
    private String status;

    @Relationship(
        type = "MEMBER_OF",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Membership> memberships = new HashSet<>();

    protected Person() {
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
    public String getStatus() { return status; }
    public Set<Membership> getMemberships() { return memberships; }

    public void setName(String name) { this.name = name; }
    public void setEmail(String email) { this.email = email; }
}
```

Node `Team`:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Team")
public class Team {
    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String name;

    protected Team() {
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
}
```

Relationship có thuộc tính:

```java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {
    @RelationshipId
    private Long id;

    private String role;
    private LocalDate joinedAt;

    @TargetNode
    private Team team;

    protected Membership() {
    }

    public String getRole() { return role; }
    public LocalDate getJoinedAt() { return joinedAt; }
    public Team getTeam() { return team; }
}
```

Đồ thị có dạng:

```text
(Person)-[MEMBER_OF {role, joinedAt}]->(Team)
```

`Membership` là relationship entity vì bản thân mối quan hệ có thuộc tính. Khi xây dựng projection nhiều cấp, cần tính cả `Membership` và `Team` vào phạm vi ánh xạ; projection không dừng ở node gốc.

## 3. Projection chỉ cập nhật một số property của node

Khai báo interface projection cho màn hình chỉnh sửa thông tin liên hệ:

```java
public interface PersonContactProjection {
    Long getId();
    String getName();
    String getEmail();
}
```

Projection này chỉ mô tả ba property của `Person`. Không có `phone`, `status` hoặc `memberships`, nên các trường đó nằm ngoài phạm vi của thao tác lưu dùng projection này.

Inject `Neo4jTemplate` và repository trong service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.neo4j.core.Neo4jTemplate;

@Service
public class PersonProfileService {
    private final PersonRepository personRepository;
    private final Neo4jTemplate neo4jTemplate;

    public PersonProfileService(
            PersonRepository personRepository,
            Neo4jTemplate neo4jTemplate) {
        this.personRepository = personRepository;
        this.neo4jTemplate = neo4jTemplate;
    }

    @Transactional
    public PersonContactProjection updateContact(
            Long personId,
            String newName,
            String newEmail) {

        Person person = personRepository.findById(personId)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));

        person.setName(newName);
        person.setEmail(newEmail);

        return neo4jTemplate.saveAs(
            person,
            PersonContactProjection.class
        );
    }
}
```

`saveAs(person, PersonContactProjection.class)` dùng projection như một mask cho thao tác lưu. SDN cập nhật `name` và `email` theo object truyền vào, đồng thời giữ các property và relationship nằm ngoài projection. Kết quả trả về là object theo kiểu projection; hãy dùng giá trị được trả về nếu cần tiếp tục làm việc với kết quả save.

Đây là điểm khác biệt quan trọng so với `neo4jTemplate.save(person)` hoặc `personRepository.save(person)`: thao tác save thông thường làm việc theo entity và các quan hệ được ánh xạ của nó, còn `saveAs` giới hạn phạm vi bằng projection được chỉ định.

## 4. Lưu DTO projection trực tiếp theo domain type

Ngoài cách truyền một entity cùng projection làm mask, SDN cho phép lưu một object projection cho domain class đã chỉ định bằng fluent API:

```java
public class PersonContactDto {
    private Long id;
    private String name;
    private String email;

    public PersonContactDto() {
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Khi đã có DTO chứa `id`, `name` và `email`, có thể lưu như sau:

```java
PersonContactDto saved = neo4jTemplate
    .save(Person.class)
    .one(contactDto);
```

`save(Person.class)` xác định domain type mà projection đại diện. `one(contactDto)` thực hiện lưu một object projection của domain type đó và trả lại object đã lưu. Fluent save API cũng có `all(...)` cho một tập instance.

Các property trong DTO cần khớp với property của domain type mà chúng đại diện. Đối với entity đã tồn tại, DTO cần mang định danh của entity để SDN xác định node cần cập nhật. Không dùng DTO của một domain type không liên quan với kiểu được truyền vào `save(...)`.

DTO class có thể sửa giá trị bằng setter trước khi lưu. Record cũng có thể phù hợp khi dữ liệu đã được tạo thành một giá trị bất biến; khi cần thay đổi, tạo một instance mới với các giá trị cập nhật.

## 5. Interface projection và DTO projection khi cập nhật

Interface projection do SDN tạo thường là dynamic proxy trỏ tới entity đích. Nó cung cấp getter cho các property được công bố; không nên xem nó như một object mutable có thể gọi setter để cập nhật dữ liệu.

Nếu đã đọc một interface projection và muốn dùng nó để cập nhật entity, hãy tạo hoặc nạp domain object rồi sao chép các giá trị cần thay đổi:

```java
public void applyContact(PersonContactProjection source) {
    this.name = source.getName();
    this.email = source.getEmail();
}
```

Sau đó lưu domain object với cùng projection làm mask:

```java
Person person = personRepository.findById(personId)
    .orElseThrow(() -> new IllegalArgumentException("Person not found"));

person.applyContact(contactProjection);

PersonContactProjection saved = neo4jTemplate.saveAs(
    person,
    PersonContactProjection.class
);
```

Nếu cần chỉnh sửa trực tiếp dữ liệu trả về, DTO projection thường thuận tiện hơn vì nó là object riêng có thể có setter. Dù dùng interface hay DTO, projection chỉ là cách biểu diễn phạm vi dữ liệu; quy tắc cập nhật và kiểm tra hợp lệ vẫn nên nằm trong service/domain logic.

## 6. Phạm vi cập nhật khi có relationship lồng nhau

Giả sử màn hình quản trị cần đổi tên người và vai trò của người đó trong các nhóm. Khi đó projection phải khai báo relationship `memberships` và các property lồng nhau cần cập nhật.

```java
import java.time.LocalDate;
import java.util.Set;

public interface PersonMembershipProjection {
    Long getId();
    String getName();
    Set<MembershipProjection> getMemberships();

    interface MembershipProjection {
        String getRole();
        LocalDate getJoinedAt();
        TeamProjection getTeam();
    }

    interface TeamProjection {
        Long getId();
        String getName();
    }
}
```

Với projection này, phạm vi lưu gồm:

- `Person.name` ở node gốc.
- Relationship collection `Person.memberships`.
- Các property `role`, `joinedAt` của relationship `Membership`.
- Node đích `Team` và property `Team.name` được khai báo trong projection lồng nhau.

Lưu domain object theo projection:

```java
PersonMembershipProjection saved = neo4jTemplate.saveAs(
    person,
    PersonMembershipProjection.class
);
```

Nếu bỏ `getMemberships()` khỏi projection, thao tác lưu này không yêu cầu SDN cập nhật collection relationship đó. Nếu giữ `getMemberships()` nhưng bỏ `TeamProjection.getName()`, projection không yêu cầu cập nhật tên của Team thông qua đường dẫn này. Muốn cập nhật property của node liên quan, phải đưa association tương ứng vào projection và khai báo property đích cần lưu.

Với `@RelationshipProperties`, các field của relationship cũng tuân theo projection boundary. Nếu cần cập nhật `role`, phải khai báo `getRole()` trong `MembershipProjection`. Nếu cần cập nhật thuộc tính node đích, khai báo projection cho `team` với đúng property cần dùng.

## 7. Quan hệ bị thiếu trong collection có thể bị xóa

Đây là điểm cần cẩn thận nhất khi lưu projection nhiều cấp.

Giả sử database đang có:

```text
Person P-100
  ├── MEMBER_OF -> Team A (role = MEMBER)
  ├── MEMBER_OF -> Team B (role = LEAD)
  └── MEMBER_OF -> Team C (role = REVIEWER)
```

Nếu projection có khai báo `memberships` và object đem lưu chỉ chứa Team A, SDN xem collection được cung cấp là dữ liệu relationship thuộc phạm vi projection. Những relationship không có trong collection đó có thể bị loại bỏ trong quá trình đồng bộ. Vì vậy, một collection được nạp thiếu có thể làm mất các liên kết Team B và Team C.

Có hai tình huống khác nhau:

| Projection | Dữ liệu truyền vào | Phạm vi tác động |
|---|---|---|
| Không khai báo `memberships` | Không mang collection | Relationship `MEMBER_OF` nằm ngoài mask, không được yêu cầu cập nhật |
| Có khai báo `memberships` | Chứa đầy đủ Team A, B, C | SDN có đủ dữ liệu để giữ và cập nhật các quan hệ cần thiết |
| Có khai báo `memberships` | Chỉ chứa Team A | Những quan hệ khác không có trong collection có thể bị xem là đã bị loại bỏ |
| Có khai báo `memberships` | Collection rỗng | Có thể được hiểu là yêu cầu không còn membership nào trong phạm vi đó |

Vì vậy, nếu muốn lưu một relationship collection, hãy nạp đầy đủ các quan hệ mà ứng dụng muốn giữ lại trước khi lưu. Nếu use case chỉ thay đổi một thuộc tính đơn lẻ trên một relationship, hãy cân nhắc query Cypher cập nhật trực tiếp relationship đó thay vì gửi lại một collection không đầy đủ.

Quy tắc này cũng áp dụng cho projection nhiều cấp: một collection ở node liên quan hoặc relationship properties nếu được đưa vào phạm vi lưu thì phải chứa đủ dữ liệu cần bảo toàn trong phạm vi đó.

## 8. Null, collection rỗng và property không được khai báo

Ba trạng thái sau cần được phân biệt trong thiết kế projection:

1. **Property không nằm trong projection:** field nằm ngoài mask và không được yêu cầu cập nhật.
2. **Property nằm trong projection nhưng giá trị là `null`:** đây là một giá trị được truyền trong phạm vi lưu. Trong Neo4j, gán property bằng `null` sẽ loại bỏ property khỏi node hoặc relationship.
3. **Relationship collection nằm trong projection nhưng rỗng:** collection rỗng có thể biểu thị trạng thái không còn quan hệ nào trong collection đó.

Không dùng `null` như một cách nói “đừng cập nhật field này” nếu field đã nằm trong projection. Muốn giữ nguyên field, hãy loại field đó khỏi projection được dùng cho lần lưu hiện tại. Nếu API PATCH cần phân biệt “không gửi field” và “yêu cầu xóa field”, service phải giữ thông tin field có xuất hiện trong request trước khi dựng DTO hoặc entity để lưu.

Đối với relationship collection, không chuyển một giá trị `null` hoặc collection chưa được nạp thành collection rỗng một cách tùy tiện. Hãy xác định rõ ý nghĩa nghiệp vụ và cách mapping trong phiên bản SDN đang dùng, sau đó kiểm tra bằng integration test.

## 9. Phạm vi của projection nhiều cấp

Projection lồng nhau xác định phạm vi ở từng entity trong đường đi:

```text
Person
  └── memberships: Membership
        └── team: Team
```

Ví dụ:

```java
public interface PersonTeamNameProjection {
    Long getId();
    Set<MembershipView> getMemberships();

    interface MembershipView {
        String getRole();
        TeamView getTeam();
    }

    interface TeamView {
        Long getId();
        String getName();
    }
}
```

Projection này đi qua `Person.memberships`, lấy thuộc tính `Membership.role`, rồi đi tiếp tới `Team.name`. `RelationshipProperties` được xem như entity trong quá trình áp dụng projection; vì vậy `MembershipView` cũng tạo một boundary riêng. Projection không tự mở rộng vô hạn qua toàn bộ graph và SDN tạo truy vấn tránh chu trình projection.

Không khai báo các relationship sâu hơn nếu nghiệp vụ không cần cập nhật chúng. Projection càng rộng thì lượng dữ liệu cần nạp và phạm vi có thể bị tác động càng lớn.

## 10. So sánh các cách lưu

| API | Đầu vào | Cách xác định phạm vi |
|---|---|---|
| `repository.save(entity)` | Domain entity | Theo entity và mapping relationship của nó |
| `neo4jTemplate.save(entity)` | Domain entity | Lưu entity cùng các related entity theo mapping |
| `neo4jTemplate.saveAs(entity, Projection.class)` | Domain entity và projection class | Chỉ các field/relationship được định nghĩa trong projection |
| `neo4jTemplate.save(Domain.class).one(projection)` | Projection object và domain class | Projection object được lưu theo domain type đã chỉ định |
| `neo4jTemplate.save(Domain.class).all(projections)` | Collection projection object | Lưu nhiều projection theo cùng domain type |

`saveAs` phù hợp khi service đã có domain object và muốn giới hạn những phần được ghi. Fluent `save(...).one(...)` phù hợp khi dữ liệu đầu vào đã là DTO projection và không cần tạo một entity đầy đủ trước đó.

Với cả hai cách, hãy sử dụng object được trả về từ thao tác lưu. API có thể trả về một instance mới và instance đó không nhất thiết được hydrate đầy đủ mọi property hoặc relationship ngoài projection.

## 11. Quy trình cập nhật an toàn

Khi xây dựng chức năng cập nhật một phần graph, hãy làm theo quy trình:

1. Xác định chính xác node gốc và các property cần thay đổi.
2. Xác định relationship nào thực sự cần cập nhật; bỏ các relationship không liên quan khỏi projection.
3. Nếu projection có relationship collection, nạp đầy đủ các quan hệ cần giữ trong lần lưu.
4. Tạo projection hoặc domain object chứa ID và dữ liệu hợp lệ.
5. Dùng `saveAs` hoặc fluent save API với đúng domain type.
6. Dùng object được trả về từ thao tác save nếu cần tiếp tục xử lý.
7. Đọc lại graph hoặc chạy query kiểm tra để xác nhận property và relationship ngoài phạm vi vẫn được giữ nguyên.
8. Đặt transaction ở ranh giới nghiệp vụ nếu quy trình gồm nhiều lần đọc/ghi cần nguyên tử.

Nếu chỉ cần cập nhật một property đơn giản mà không cần thao tác với graph object, một custom Cypher query dùng `MATCH` và `SET` có thể rõ ràng hơn. Projection phù hợp khi muốn lưu một phần mô hình entity theo cấu trúc Java và kiểm soát chính xác mask của lần ghi.

## 12. Kiểm tra dữ liệu trước và sau khi lưu

Truy vấn trước khi cập nhật để xem đầy đủ property và membership:

```cypher
MATCH (p:Person {code: $personCode})
OPTIONAL MATCH (p)-[r:MEMBER_OF]->(t:Team)
RETURN p.code AS personCode,
       p.name AS name,
       p.email AS email,
       p.phone AS phone,
       p.status AS status,
       collect({team: t.code, role: r.role}) AS memberships;
```

Sau khi lưu contact projection, chạy lại truy vấn. `name` và `email` có thể thay đổi; `phone`, `status` và danh sách `memberships` phải giữ nguyên vì chúng không nằm trong projection.

Sau khi lưu projection có `memberships`, hãy kiểm tra từng quan hệ:

```cypher
MATCH (p:Person {code: $personCode})-[r:MEMBER_OF]->(t:Team)
RETURN t.code AS teamCode,
       t.name AS teamName,
       r.role AS role,
       r.joinedAt AS joinedAt
ORDER BY teamCode;
```

Nếu số relationship giảm ngoài dự kiến, kiểm tra projection collection có bị thiếu dữ liệu khi nạp hoặc chuyển đổi DTO hay không.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lưu contact làm mất relationship | Dùng save thông thường với entity chỉ được nạp một phần | Dùng projection mask và chỉ đưa field cần cập nhật vào projection |
| Relationship khác bị xóa sau khi lưu | Projection có khai báo collection nhưng collection đầu vào không đầy đủ | Nạp đủ relationship cần giữ trước khi save |
| Đổi `Team.name` nhưng không được lưu | Projection chỉ có `memberships` hoặc `team` mà không khai báo property `Team.name` | Thêm nested projection chứa `getName()` |
| Đổi `Membership.role` nhưng không được lưu | Projection lồng nhau không khai báo `role` trên relationship properties | Thêm `getRole()` vào nested relationship projection |
| Interface projection không thể sửa bằng setter | Interface projection là proxy để đọc dữ liệu | Sao chép giá trị sang entity/DTO mutable rồi lưu với projection mask |
| Property bị xóa ngoài ý muốn | Property có trong projection nhưng giá trị là `null` | Phân biệt field omitted với explicit null trước khi lưu |
| Dữ liệu trả về sau save thiếu field | Kết quả được hydrate theo projection | Dùng kết quả theo đúng projection hoặc đọc lại entity đầy đủ trước lần lưu khác |

## 14. Tự kiểm tra

1. Projection dùng khi đọc khác projection dùng khi lưu ở điểm nào?
2. `neo4jTemplate.saveAs(person, PersonContactProjection.class)` giới hạn thao tác ghi như thế nào?
3. Vì sao `repository.save(entity)` không tự hiểu một object thiếu field là yêu cầu cập nhật một phần?
4. Nếu projection không khai báo `memberships`, collection relationship đó có thuộc phạm vi cập nhật không?
5. Vì sao collection relationship được khai báo trong projection cần được nạp đầy đủ trước khi lưu?
6. Muốn cập nhật `Membership.role` và `Team.name`, cần khai báo những nested projection nào?
7. Khác biệt giữa property không được khai báo trong projection và property có trong projection nhưng mang `null` là gì?
8. Khi nào nên dùng fluent API `save(Domain.class).one(dto)` thay vì `saveAs(entity, Projection.class)`?

## Tài liệu tham khảo

- [Spring Data Neo4j — Projections, mục Data manipulation và Persistence of projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j — Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j — FluentSaveOperation API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/FluentSaveOperation.html)
