# Điều kiện chọn thuộc tính động khi lưu theo phiên bản

Khi lưu một entity bằng Spring Data Neo4j (SDN), thao tác `save(entity)` thông thường làm việc với entity và các relationship được ánh xạ của nó. Tuy nhiên, nhiều use case chỉ muốn cập nhật một phần graph: ví dụ chỉ đổi tên và email của `Person`, hoặc chỉ cập nhật vai trò trong một relationship mà không đụng tới những thuộc tính khác.

`Neo4jTemplate` hỗ trợ giới hạn phạm vi lưu bằng projection. Từ SDN 6.1, có thể dùng projection class để xác định trước các property cần lưu. Từ SDN 6.3, có thêm overload nhận `BiPredicate<PropertyPath, Neo4jPersistentProperty>` để quyết định động từng property dựa trên đường dẫn và metadata mapping. Vì API này phụ thuộc phiên bản thư viện, cần kiểm tra phiên bản SDN mà ứng dụng thực sự sử dụng trước khi chọn cách triển khai.

## 1. Bài toán chọn một phần property khi lưu

Giả sử node `Person` có các thuộc tính `name`, `email`, `phone`, `status` và relationship `MEMBER_OF` tới `Team`. Relationship có thuộc tính `role` và `joinedAt`.

Một màn hình hồ sơ chỉ cho phép người dùng sửa `name` và `email`. Nếu tải entity không đầy đủ rồi gọi `save(person)`, ứng dụng có thể vô tình đồng bộ một graph không phản ánh đủ các relationship đang tồn tại. Nếu tải toàn bộ graph chỉ để sửa hai field, ứng dụng phải đọc nhiều dữ liệu hơn nhu cầu.

Mục tiêu là giới hạn thao tác lưu theo một tập property rõ ràng:

| Property | Cập nhật trong thao tác sửa hồ sơ? |
|---|---|
| `name` | Có |
| `email` | Có |
| `phone` | Không |
| `status` | Không |
| `memberships` | Không |
| `memberships.role` | Không |

Projection khi lưu hoạt động như một mask: property được đưa vào mask thuộc phạm vi lưu; property bị loại khỏi mask nằm ngoài phạm vi của lần lưu đó. Khi có nhiều quy tắc nghiệp vụ hoặc quyền truy cập khác nhau, predicate động giúp tạo mask ngay tại thời điểm gọi.

## 2. Mô hình entity ví dụ

Entity `Person`:

```java
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

    private String name;
    private String code;
    private String email;
    private String phone;
    private String status;
    private Integer schemaVersion;
    private String legacyCode;

    @Relationship(type = "MEMBER_OF", direction = Relationship.Direction.OUTGOING)
    private Set<Membership> memberships = new HashSet<>();

    protected Person() {
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
    public String getStatus() { return status; }
    public Integer getSchemaVersion() { return schemaVersion; }
    public Set<Membership> getMemberships() { return memberships; }

    public void setName(String name) { this.name = name; }
    public void setEmail(String email) { this.email = email; }
}
```

Entity `Team`:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Team")
public class Team {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Team() {
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

Relationship entity `Membership`:

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

Mô hình đồ thị:

```text
(Person)-[MEMBER_OF {role, joinedAt}]->(Team)
```

`Membership` chứa dữ liệu của relationship, còn `Team` là node đích. Khi chọn property lồng nhau, cần xem cả node gốc, relationship entity và node đích là các phần riêng của đường dẫn.

## 3. Phiên bản SDN quyết định overload có thể sử dụng

Các overload lưu theo projection được bổ sung theo từng phiên bản:

| Phiên bản Spring Data Neo4j | API liên quan | Ý nghĩa |
|---|---|---|
| 6.0 | `save(entity)` | Lưu entity theo mapping thông thường và các related entity |
| 6.1 trở lên | `saveAs(entity, Projection.class)` | Dùng projection class cố định làm blueprint cho thao tác lưu |
| 6.1 trở lên | `save(Domain.class).one(projectionValue)` | Lưu một projection object theo domain type đã chỉ định |
| 6.3 trở lên | `saveAs(entity, BiPredicate<PropertyPath, Neo4jPersistentProperty>)` | Chọn property động bằng predicate |
| 6.3 trở lên | `saveAllAs(instances, predicate)` | Lưu nhiều entity với cùng quy tắc chọn property động |
| 7.x và 8.x | Các overload trên tiếp tục được cung cấp | Kiểm tra Javadoc đúng phiên bản dependency của ứng dụng |

Điểm cần nhớ:

- `saveAs(entity, Projection.class)` có từ SDN 6.1; không cần predicate động nếu phạm vi lưu luôn cố định.
- Overload `saveAs(entity, predicate)` và `saveAllAs(instances, predicate)` được đánh dấu `Since: 6.3` trong API. Dự án dùng SDN 6.1 hoặc 6.2 không thể gọi overload này.
- Trong SDN 7.x và 8.x, kiểu predicate vẫn là `BiPredicate<PropertyPath, Neo4jPersistentProperty>`.
- Với ứng dụng reactive, `ReactiveNeo4jTemplate.saveAs(entity, predicate)` trả về `Mono<T>` và `saveAllAs(...)` trả về `Flux<T>`.

Ở đây, “phiên bản” nói tới phiên bản thư viện SDN. Annotation `@Version` trên entity phục vụ optimistic locking, là một cơ chế khác và không phải tham số đầu vào của predicate.

## 4. Static projection: cách dùng từ SDN 6.1

Nếu use case luôn chỉ cập nhật `name` và `email`, có thể khai báo projection cố định:

```java
public interface PersonContactProjection {
    Long getId();
    String getName();
    String getEmail();
}
```

Sau khi nạp và sửa entity, gọi `saveAs`:

```java
Person person = personRepository.findById(personId)
    .orElseThrow(() -> new IllegalArgumentException("Person not found"));

person.setName(newName);
person.setEmail(newEmail);

PersonContactProjection saved = neo4jTemplate.saveAs(
    person,
    PersonContactProjection.class
);
```

Projection cố định là lựa chọn dễ đọc khi phạm vi property không thay đổi theo request hoặc quyền người dùng. `save(Domain.class).one(projectionValue)` là cách khác nếu đầu vào đã là projection object và muốn lưu theo domain type tương ứng.

## 5. Dynamic property selection từ SDN 6.3

Từ SDN 6.3, `saveAs` có overload nhận `BiPredicate`:

```java
<T> T saveAs(
    T instance,
    BiPredicate<PropertyPath, Neo4jPersistentProperty> includeProperty
)
```

Đây là dynamic selection ở bước persistence. Nó khác với dynamic projection của repository query, nơi method nhận `Class<T>` để chọn kiểu kết quả đọc.

Predicate được gọi để quyết định property có thuộc phạm vi lưu hay không:

- `PropertyPath` mô tả đường dẫn property. Dùng `toDotPath()` để lấy đường dẫn dạng `name`, `memberships.role` hoặc `memberships.team.name`.
- `Neo4jPersistentProperty` cung cấp metadata mapping của property, chẳng hạn tên, kiểu, property có phải association hay không, có phải ID hoặc version property hay không.
- Trả về `true` để đưa property vào phạm vi lưu; trả về `false` để loại property đó khỏi phạm vi.

Predicate không nhận trực tiếp giá trị hiện tại của field. Nếu quyết định còn phụ thuộc vào ngữ cảnh request hoặc dữ liệu nghiệp vụ, hãy chuẩn bị biến điều kiện bên ngoài rồi capture chúng trong lambda.

Ví dụ chỉ lưu `name` và `email`:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.function.BiPredicate;

import org.springframework.data.mapping.PropertyPath;
import org.springframework.data.neo4j.core.mapping.Neo4jPersistentProperty;

Set<String> includedPaths = new HashSet<>(Arrays.asList("name", "email"));

BiPredicate<PropertyPath, Neo4jPersistentProperty> includeContact =
    (path, property) -> includedPaths.contains(path.toDotPath());

Person saved = neo4jTemplate.saveAs(person, includeContact);
```

`includedPaths` là allowlist. Cách này giúp phạm vi ghi rõ ràng và tránh vô tình thêm property mới vào thao tác lưu chỉ vì entity được mở rộng sau này.

## 6. Dùng metadata để phân biệt property và association

Tham số thứ hai của predicate cho phép áp dụng quy tắc khác nhau cho property đơn giản và association. `Neo4jPersistentProperty.isAssociation()` cho biết property có được ánh xạ thành quan hệ tới entity khác hay không.

Ví dụ chỉ cho phép lưu thông tin hồ sơ; association luôn bị loại:

```java
import java.util.Arrays;
import java.util.function.BiPredicate;

import org.springframework.data.mapping.PropertyPath;
import org.springframework.data.neo4j.core.mapping.Neo4jPersistentProperty;

BiPredicate<PropertyPath, Neo4jPersistentProperty> includeProfileOnly =
    (path, property) -> {
        if (property.isAssociation()) {
            return false;
        }

        return Arrays.asList("name", "email", "phone")
            .contains(path.toDotPath());
    };

Person saved = neo4jTemplate.saveAs(person, includeProfileOnly);
```

Metadata cũng có thể dùng để nhận diện ID hoặc version property:

```java
import java.util.Arrays;
import java.util.function.BiPredicate;

import org.springframework.data.mapping.PropertyPath;
import org.springframework.data.neo4j.core.mapping.Neo4jPersistentProperty;

BiPredicate<PropertyPath, Neo4jPersistentProperty> includeBusinessFields =
    (path, property) -> {
        if (property.isIdProperty() || property.isVersionProperty()) {
            return true;
        }

        return Arrays.asList("name", "email")
            .contains(path.toDotPath());
    };
```

Đoạn thứ hai chỉ minh họa cách kiểm tra metadata. Trong ứng dụng thật, hãy xác nhận quy tắc ID và optimistic locking phù hợp với mapping và phiên bản SDN đang dùng; không tự ý đưa hoặc loại trường hệ thống chỉ vì muốn đơn giản hóa predicate.

## 7. Chọn property lồng nhau qua relationship

Nếu nghiệp vụ cần cập nhật vai trò trong `Membership` và tên của `Team`, chỉ đưa `memberships.role` vào allowlist là chưa đủ. Để đi tới property của entity liên quan, predicate phải chấp nhận cả association dẫn tới entity đó.

Ví dụ đường dẫn cần lưu:

```text
Person.name
Person.memberships
Person.memberships.role
Person.memberships.team
Person.memberships.team.name
```

Predicate có thể viết bằng allowlist:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.function.BiPredicate;

import org.springframework.data.mapping.PropertyPath;
import org.springframework.data.neo4j.core.mapping.Neo4jPersistentProperty;

Set<String> includedPaths = new HashSet<>(Arrays.asList(
    "name",
    "memberships",
    "memberships.role",
    "memberships.team",
    "memberships.team.name"
));

BiPredicate<PropertyPath, Neo4jPersistentProperty> includeMembershipDetails =
    (path, property) -> includedPaths.contains(path.toDotPath());
```

Trong ví dụ này:

- `memberships` cho phép SDN đi qua association từ `Person` tới relationship entity.
- `memberships.role` chọn thuộc tính của relationship.
- `memberships.team` cho phép đi tiếp tới node `Team`.
- `memberships.team.name` chọn thuộc tính cần cập nhật trên node `Team`.

Nếu bỏ một association trung gian khỏi predicate, các property sâu hơn trên đường dẫn đó không thể được xử lý như một phần của graph được chọn. Quy tắc này đặc biệt quan trọng với `@RelationshipProperties`, vì relationship entity cũng có các property và association riêng.

## 8. Điều kiện động theo request hoặc phiên bản dữ liệu nghiệp vụ

Predicate có thể được tạo theo quyền người dùng hoặc ngữ cảnh nghiệp vụ. Ví dụ, người dùng thường chỉ sửa hồ sơ; quản trị viên có thể sửa cả membership.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.function.BiPredicate;

import org.springframework.data.mapping.PropertyPath;
import org.springframework.data.neo4j.core.mapping.Neo4jPersistentProperty;

boolean canEditMemberships = currentUser.hasRole("ADMIN");

Set<String> profilePaths = new HashSet<>(Arrays.asList("name", "email"));
Set<String> membershipPaths = new HashSet<>(Arrays.asList(
    "memberships",
    "memberships.role",
    "memberships.team",
    "memberships.team.name"
));

BiPredicate<PropertyPath, Neo4jPersistentProperty> includeByPermission =
    (path, property) -> profilePaths.contains(path.toDotPath())
        || (canEditMemberships && membershipPaths.contains(path.toDotPath()));

Person saved = neo4jTemplate.saveAs(person, includeByPermission);
```

Một trường hợp khác là tương thích dữ liệu qua phiên bản schema nghiệp vụ. Giả sử `schemaVersion` là thuộc tính do ứng dụng quản lý và dữ liệu cũ còn có `legacyCode`:

```java
import java.util.Arrays;
import java.util.function.BiPredicate;

import org.springframework.data.mapping.PropertyPath;
import org.springframework.data.neo4j.core.mapping.Neo4jPersistentProperty;

Integer schemaVersion = person.getSchemaVersion();

BiPredicate<PropertyPath, Neo4jPersistentProperty> includeBySchemaVersion =
    (path, property) -> {
        String dotPath = path.toDotPath();

        if ("legacyCode".equals(dotPath)) {
            return schemaVersion != null && schemaVersion < 2;
        }

        return Arrays.asList("name", "email", "schemaVersion")
            .contains(dotPath);
    };

Person saved = neo4jTemplate.saveAs(person, includeBySchemaVersion);
```

Predicate không tự đọc `schemaVersion` từ entity. Lambda sử dụng biến `schemaVersion` đã được lấy trước khi gọi `saveAs`. Nếu quy tắc dựa trên phiên bản schema, nên đặt tên rõ như `schemaVersion` hoặc `dataFormatVersion`; đừng nhầm với `@Version`, vốn được SDN dùng cho optimistic locking.

## 9. Lưu nhiều entity với cùng predicate

Từ SDN 6.3, có thể dùng `saveAllAs` để áp dụng cùng điều kiện cho một nhóm entity:

```java
import java.util.List;

List<Person> savedPeople = neo4jTemplate.saveAllAs(
    people,
    includeContact
);
```

`includeContact` là predicate đã định nghĩa ở phần trước. Mọi entity trong `people` sẽ được lưu theo cùng allowlist. Nếu từng entity cần phạm vi khác nhau, hãy chia batch theo quy tắc lưu hoặc thực hiện các lời gọi riêng với predicate được tạo theo từng ngữ cảnh.

Không nên tạo một predicate thay đổi trạng thái trong khi `saveAllAs` đang chạy. Predicate nên ổn định trong suốt một lần lưu batch để tất cả entity được xử lý theo cùng một quy tắc có thể dự đoán.

## 10. Reactive API

Trong ứng dụng reactive, `ReactiveNeo4jTemplate` cung cấp overload tương ứng. Predicate có cùng ý nghĩa nhưng kết quả là publisher:

```java
import reactor.core.publisher.Mono;

Mono<Person> saveContact(Person person) {
    return reactiveNeo4jTemplate.saveAs(person, includeContact);
}
```

Với nhiều entity:

```java
import reactor.core.publisher.Flux;

Flux<Person> savePeople(Iterable<Person> people) {
    return reactiveNeo4jTemplate.saveAllAs(people, includeContact);
}
```

Hãy giữ các thao tác reactive trong cùng Reactor chain và dùng reactive transaction manager nếu nhiều bước cần tính nguyên tử. Không gọi `block()` chỉ để lấy kết quả trong một service reactive.

## 11. Khác biệt giữa property bị loại, null và collection thiếu

Predicate chỉ quyết định property có thuộc phạm vi lưu hay không. Nó không thay thế quy tắc về giá trị của property.

| Trường hợp | Ý nghĩa |
|---|---|
| Predicate trả `false` cho property | Property nằm ngoài phạm vi của thao tác lưu |
| Predicate trả `true`, giá trị scalar là `null` | Property thuộc phạm vi lưu; trong Neo4j, gán `null` sẽ xóa property đó |
| Predicate trả `true` cho association collection nhưng collection đầu vào thiếu phần tử | Các relationship không có trong collection được cung cấp có thể bị loại bỏ khi đồng bộ |
| Predicate trả `true` cho association collection rỗng | Có thể được hiểu là collection cần lưu không còn relationship nào |

Nếu chỉ muốn giữ nguyên một property, hãy loại property đó khỏi predicate. Nếu muốn xóa property, hãy đưa nó vào phạm vi lưu và truyền giá trị `null` theo đúng quy tắc nghiệp vụ. Nếu muốn cập nhật relationship collection, hãy nạp đầy đủ các relationship cần giữ trước khi lưu.

## 12. Giá trị trả về và nguy cơ lưu tiếp gây mất dữ liệu

`saveAs` trả về entity đã lưu theo phạm vi được chọn; với dynamic predicate, object trả về có thể không được hydrate đầy đủ các property và relationship bị loại khỏi predicate. API hiện tại đánh dấu kết quả `saveAs` là nullable.

Không nên lấy object trả về từ một lần lưu giới hạn rồi dùng nó cho một lần `save(entity)` thông thường. Ví dụ, lần đầu chỉ lưu `name` và `email`; object trả về có thể không chứa `memberships`. Nếu lần sau lưu toàn bộ entity theo mapping mặc định, collection thiếu có thể làm mất relationship trong database.

Khi cần tiếp tục xử lý với graph đầy đủ:

1. Dùng object trả về trong đúng phạm vi projection đã chọn; hoặc
2. Đọc lại entity đầy đủ bằng repository/`Neo4jTemplate` trước lần lưu toàn phần tiếp theo.

## 13. Chọn phương án theo phiên bản và use case

| Điều kiện | Nên chọn |
|---|---|
| Dự án dùng SDN 6.1 hoặc 6.2, phạm vi lưu cố định | `saveAs(entity, Projection.class)` |
| Dự án dùng SDN 6.1 hoặc 6.2, đầu vào đã là projection DTO | `save(Domain.class).one(dto)` |
| Dự án dùng SDN 6.3+ và phạm vi thay đổi theo quyền/ngữ cảnh | `saveAs(entity, BiPredicate)` |
| Dự án dùng SDN 6.3+ và lưu batch cùng quy tắc | `saveAllAs(instances, BiPredicate)` |
| Cần truy vấn ghi đặc thù hoặc thay đổi một property/relationship chính xác | Cân nhắc Cypher tường minh qua `@Query` hoặc `Neo4jClient` |

Không kiểm tra phiên bản thư viện bằng cách gọi overload rồi bắt lỗi runtime. Hãy xác định version được Spring Boot BOM hoặc dependency management chọn, sau đó biên dịch với API tương ứng. Nếu cần hỗ trợ nhiều nhánh ứng dụng, có thể đóng gói phần lưu trong adapter riêng cho từng dòng SDN.

## 14. Kiểm thử điều kiện chọn property

Một integration test nên kiểm tra cả property được chọn và property bị loại. Ví dụ, database ban đầu có `name`, `email`, `phone` và một vài membership. Sau khi lưu bằng `includeContact`, xác minh:

1. `name` và `email` nhận giá trị mới.
2. `phone` vẫn giữ giá trị cũ.
3. `status` vẫn giữ giá trị cũ.
4. Tất cả relationship `MEMBER_OF` vẫn tồn tại.
5. Nếu predicate có chọn association, chỉ những property/relationship nằm trong phạm vi dự định mới thay đổi.
6. Nếu predicate loại property có giá trị `null`, property đó vẫn được giữ nguyên; nếu predicate nhận property với giá trị `null`, xác nhận property bị xóa đúng theo yêu cầu.

Có thể dùng Cypher để kiểm tra trạng thái sau lưu:

```cypher
MATCH (p:Person {code: $personCode})
OPTIONAL MATCH (p)-[r:MEMBER_OF]->(t:Team)
RETURN p.name AS name,
       p.email AS email,
       p.phone AS phone,
       p.status AS status,
       collect({team: t.name, role: r.role}) AS memberships;
```

Nên có test riêng cho predicate có nhánh quyền quản trị và predicate phụ thuộc `schemaVersion`, tránh để điều kiện động chỉ được xác nhận bằng một trường hợp thành công.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không biên dịch được `saveAs(entity, predicate)` | Dự án đang dùng SDN trước 6.3 | Dùng projection class từ 6.1 hoặc nâng cấp dependency có kiểm soát |
| Predicate không chọn property lồng nhau | So sánh tên leaf thay vì full path | Dùng `path.toDotPath()` và kiểm tra chuỗi đường dẫn |
| Cập nhật property của related node không có tác dụng | Chưa include association dẫn tới related node | Include association property và các property lồng nhau cần cập nhật |
| Relationship biến mất sau khi lưu | Collection trong entity đầu vào không đầy đủ nhưng association đã được include | Nạp đủ relationship cần giữ hoặc loại association khỏi predicate |
| Property bị xóa ngoài ý muốn | Property được include nhưng giá trị là `null` | Phân biệt omitted với explicit null trước khi tạo entity/DTO |
| Lần save tiếp theo làm mất dữ liệu | Dùng lại entity trả về từ saveAs như entity đầy đủ | Đọc lại graph đầy đủ hoặc tiếp tục lưu bằng cùng projection |
| Predicate chọn sai field khi đổi tên Java property | Allowlist dùng đường dẫn cũ | Cập nhật path và test mapping khi refactor entity |
| Nhầm `@Version` với phiên bản API | Dùng optimistic-lock version để suy luận overload có sẵn | Kiểm tra version SDN trong dependency management; `@Version` là cơ chế riêng |

## 16. Quy trình triển khai

1. Xác định phiên bản SDN thực tế từ dependency management.
2. Nếu dùng SDN 6.1/6.2, chọn static projection; nếu dùng 6.3+, có thể chọn dynamic predicate.
3. Liệt kê full property path cần lưu, bao gồm association trung gian.
4. Tạo allowlist hoặc predicate theo quyền và ngữ cảnh nghiệp vụ.
5. Không để predicate phụ thuộc trạng thái thay đổi trong khi một batch đang chạy.
6. Nếu có relationship collection, nạp đủ dữ liệu cần bảo toàn trước khi lưu.
7. Dùng `saveAs` hoặc `saveAllAs` và giữ đúng transaction boundary.
8. Không dùng object trả về của projection-limited save như một entity đã hydrate đầy đủ.
9. Kiểm thử property được cập nhật, property bị loại, null, collection và các nhánh phiên bản schema.

## 17. Tự kiểm tra

1. `saveAs(entity, Projection.class)` được hỗ trợ từ phiên bản SDN nào?
2. Overload `saveAs(entity, BiPredicate<PropertyPath, Neo4jPersistentProperty>)` xuất hiện từ phiên bản nào?
3. `PropertyPath.toDotPath()` giúp gì khi chọn property lồng nhau?
4. Vì sao phải include association property khi muốn cập nhật một related node?
5. Predicate có nhận trực tiếp giá trị hiện tại của field không? Nếu điều kiện phụ thuộc quyền người dùng, cần tổ chức code thế nào?
6. Khác biệt giữa property bị predicate loại và property được include nhưng có giá trị `null` là gì?
7. Vì sao một relationship collection không đầy đủ có thể làm mất quan hệ khi lưu?
8. `@Version` có phải là cơ chế chọn overload theo phiên bản SDN không? Giải thích.
9. Vì sao không nên tái sử dụng entity trả về từ `saveAs` cho một lần `save` toàn phần?
10. Khi nào static projection phù hợp hơn dynamic predicate?

## Tài liệu tham khảo

- [Spring Data Neo4j 6.1 — Persistence of projections](https://docs.spring.io/spring-data/neo4j/docs/6.1.6/reference/html/#projections.persistence)
- [Spring Data Neo4j — Neo4jOperations API: saveAs và saveAllAs](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/Neo4jOperations.html)
- [Spring Data Neo4j — Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Commons — PropertyPath API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PropertyPath.html)
- [Spring Data Neo4j — Neo4jPersistentProperty API](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/mapping/Neo4jPersistentProperty.html)
