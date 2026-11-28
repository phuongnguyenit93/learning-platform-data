# Vai trò của `@Id` khi nhận diện cùng một entity

Trong Spring Data Neo4j (SDN), `@Id` đánh dấu thuộc tính mà SDN dùng làm định danh của một entity. Định danh này giúp tầng ánh xạ xác định node nào tương ứng với đối tượng Java, hỗ trợ các thao tác như tìm, cập nhật và xóa qua repository. Khi hai lần đọc cùng một node, giá trị định danh là căn cứ để SDN liên hệ dữ liệu đồ thị với cùng một entity theo mô hình persistence.

Neo4j là cơ sở dữ liệu đồ thị, không phải cơ sở dữ liệu quan hệ có cột khóa chính bắt buộc trên mỗi bảng. Vì vậy, cần phân biệt định danh nội bộ của node trong Neo4j với một property định danh do ứng dụng quản lý. `@Id` cho biết SDN sử dụng thuộc tính nào làm định danh; cách tạo giá trị đó phụ thuộc vào việc bạn dùng `@GeneratedValue` hay tự cấp ID.

## 1. `@Id` xác định điều gì?

Một node Neo4j có thể có label và nhiều property. Ví dụ, node `Person` có các property `name`, `email` và `active`. Trong Java, SDN cần biết thuộc tính nào là định danh để thực hiện các thao tác persistence một cách nhất quán.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String email;
    private boolean active;

    protected Person() {
    }

    public Person(String name, String email) {
        this.name = name;
        this.email = email;
        this.active = true;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

Trong ví dụ:

- `@Node("Person")` xác định label của node.
- `@Id` đánh dấu `id` là thuộc tính định danh của entity.
- `@GeneratedValue` yêu cầu SDN tạo giá trị định danh theo cơ chế sinh ID mặc định.
- `name`, `email` và `active` là dữ liệu nghiệp vụ, không phải định danh của entity trong mapping này.

`@Id` không tự tạo node và cũng không tạo unique constraint cho một property nghiệp vụ bất kỳ. Nó là metadata để SDN biết thuộc tính nào đại diện cho định danh của entity.

## 2. Định danh được dùng trong các thao tác repository

Kiểu ID khai báo ở tham số thứ hai của `Neo4jRepository` phải tương thích với kiểu của thuộc tính được đánh dấu `@Id`.

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    Optional<Person> findByEmail(String email);
}
```

Với repository này, `Long` là kiểu định danh của `Person`. Các thao tác kế thừa như `findById`, `existsById` và `deleteById` nhận giá trị ID theo kiểu đó. Chúng làm việc với định danh của entity, trong khi `findByEmail` là truy vấn theo thuộc tính nghiệp vụ `email`.

Ví dụ sử dụng:

```java
import org.springframework.stereotype.Service;

@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    public Person getRequiredPerson(Long id) {
        return people.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));
    }
}
```

Nếu khai báo entity dùng `String id` nhưng repository lại kế thừa `Neo4jRepository<Person, Long>`, kiểu ID không nhất quán và cần được sửa. Hãy kiểm tra cả kiểu thuộc tính `@Id`, kiểu ID trong repository và kiểu tham số của service.

## 3. ID do Neo4j sinh và ID do ứng dụng quản lý

Có hai cách tiếp cận phổ biến. Chúng phục vụ những mục đích khác nhau và không nên bị nhầm lẫn.

### Dùng `@GeneratedValue`

```java
@Id
@GeneratedValue
private Long id;
```

Với cấu hình mặc định, SDN dùng định danh nội bộ do Neo4j cấp cho node. Ứng dụng không cần tự gán giá trị trước khi lưu. Cách này thuận tiện khi ID chỉ phục vụ việc nhận diện node bên trong tầng persistence.

Tuy nhiên, internal ID của Neo4j là chi tiết triển khai của cơ sở dữ liệu. Nó không phải mã nghiệp vụ ổn định để lưu vào hệ thống bên ngoài, đưa vào URL lâu dài, đồng bộ giữa các môi trường hoặc dùng làm khóa tham chiếu độc lập. Internal ID có thể được tái sử dụng sau khi node bị xóa; không nên xem nó là định danh toàn cục, vĩnh viễn.

### Tự cấp ID từ ứng dụng

Nếu định danh cần tồn tại ổn định ngoài phạm vi một node trong Neo4j, ứng dụng có thể tạo ID và đánh dấu bằng `@Id` mà không dùng `@GeneratedValue`:

```java
import java.util.UUID;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    protected Person() {
    }

    public Person(String name) {
        this.id = UUID.randomUUID().toString();
        this.name = name;
    }

    public String getId() {
        return id;
    }
}
```

Trong cách này, `id` là property do ứng dụng quản lý và được lưu cùng node. Bạn có thể dùng UUID để giảm nguy cơ trùng ID khi nhiều instance ứng dụng cùng tạo dữ liệu hoặc khi dữ liệu được nhập từ nhiều nguồn. Repository tương ứng phải khai báo `Neo4jRepository<Person, String>`.

Vì ID do ứng dụng cấp là property trong đồ thị, cần bảo đảm tính duy nhất ở cấp cơ sở dữ liệu. Ví dụ, tạo uniqueness constraint cho label `Person` và property `id`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.id IS UNIQUE;
```

Constraint giúp Neo4j từ chối các node `Person` có cùng giá trị `id`, kể cả khi dữ liệu được ghi từ nhiều instance hoặc từ một công cụ khác ngoài ứng dụng Spring.

| Tiêu chí | ID nội bộ với `@GeneratedValue` | ID do ứng dụng cấp với `@Id` |
|---|---|---|
| Nơi tạo ID | Neo4j thông qua cơ chế sinh mặc định của SDN | Ứng dụng hoặc hệ thống định danh được chọn |
| Dữ liệu được lưu | Định danh nội bộ của node, không phải property nghiệp vụ thông thường | Property định danh trên node |
| Phạm vi sử dụng phù hợp | Nội bộ tầng persistence | Có thể dùng làm mã tham chiếu ổn định giữa các hệ thống |
| Ràng buộc duy nhất | Do cơ chế ID nội bộ của Neo4j quản lý | Nên tạo uniqueness constraint cho label và property |
| Ví dụ kiểu Java | `Long` | `String` chứa UUID |

Chọn cách tiếp cận dựa trên vòng đời và phạm vi sử dụng ID. Nếu ID sẽ được trao đổi với dịch vụ khác, xuất hiện trong sự kiện hoặc được lưu ở hệ thống ngoài Neo4j, ID do ứng dụng quản lý thường là lựa chọn rõ ràng hơn.

## 4. Phân biệt ID với thuộc tính nghiệp vụ

Một thuộc tính có vẻ duy nhất như email, mã nhân viên hoặc số tài khoản không tự động trở thành định danh của entity. Nếu dùng một trong các giá trị đó làm `@Id`, bạn đang chọn nó làm định danh persistence và phải xử lý các yêu cầu về tính ổn định, tính duy nhất và thay đổi giá trị.

Ví dụ, email có thể thay đổi khi người dùng đổi địa chỉ. Nếu email là `@Id`, việc thay đổi email đồng nghĩa với thay đổi định danh mà SDN sử dụng để nhận diện entity. Điều này có thể làm phức tạp thao tác cập nhật, liên kết từ hệ thống khác và dữ liệu đã tham chiếu đến người dùng.

Một mô hình thường dễ quản lý hơn là giữ một ID ổn định riêng và đặt email làm thuộc tính nghiệp vụ:

```java
@Node("Person")
public class Person {

    @Id
    private String id;

    private String email;
    private String displayName;
}
```

Khi cần email duy nhất, tạo constraint riêng cho email:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Như vậy, ID nhận diện entity trong tầng persistence, còn email được bảo vệ bởi quy tắc nghiệp vụ. Hai mục đích có liên quan nhưng không đồng nhất.

## 5. `@Id` không đồng nghĩa với `equals()` và `hashCode()`

`@Id` cung cấp metadata định danh cho SDN. Nó không tự động quyết định cách Java so sánh hai object bằng `equals()` hoặc cách tính `hashCode()`.

Nếu ứng dụng tự triển khai equality dựa trên ID, hãy xác định hành vi của entity mới chưa được lưu. Với ID được sinh khi lưu, hai object mới có thể cùng có ID `null`; nếu xem hai giá trị `null` là bằng nhau, các entity mới không liên quan có thể bị coi là cùng một đối tượng. Nếu ID được tạo trước khi lưu, UUID có thể cung cấp một giá trị ổn định ngay từ lúc khởi tạo.

Đối với entity có thể được đưa vào `HashSet` hoặc dùng làm key trong `HashMap`, cũng cần bảo đảm `hashCode()` không thay đổi theo cách làm hỏng cấu trúc collection trong suốt vòng đời của object. Hãy chọn chiến lược equality phù hợp với miền nghiệp vụ và vòng đời entity; đừng cho rằng chỉ thêm `@Id` là đủ.

## 6. `@Id` và `@Version` giải quyết hai vấn đề khác nhau

Định danh trả lời câu hỏi “đây là entity nào?”. Version trả lời câu hỏi “entity này đang ở phiên bản dữ liệu nào?”. Trong SDN, `@Version` được dùng cho optimistic locking để phát hiện cập nhật cạnh tranh.

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Account")
public class Account {

    @Id
    private String id;

    @Version
    private Long version;

    private String owner;
}
```

Khi hai transaction cùng đọc một entity, cả hai có thể nhìn thấy cùng một version. Nếu transaction thứ nhất cập nhật thành công, version được tăng. Transaction thứ hai cập nhật dựa trên version cũ sẽ bị phát hiện là xung đột thay vì âm thầm ghi đè thay đổi mới.

`@Version` không thay thế `@Id`: một entity vẫn cần định danh để SDN biết node nào được cập nhật. Tương tự, `@Id` không tự ngăn hai người dùng cùng cập nhật một entity và ghi đè dữ liệu của nhau.

## 7. Những lỗi thường gặp khi thiết kế định danh

| Lỗi | Vì sao có vấn đề | Cách xử lý |
|---|---|---|
| Dùng internal ID như mã khách hàng công khai | Internal ID là chi tiết triển khai và có thể được tái sử dụng | Tạo ID nghiệp vụ riêng, chẳng hạn UUID |
| Kiểu ID trong repository khác kiểu field `@Id` | Hợp đồng repository không khớp với entity | Đồng bộ kiểu ID ở entity, repository và service |
| Dùng email làm ID dù email có thể đổi | Thay đổi thuộc tính nghiệp vụ làm thay đổi định danh | Dùng ID ổn định riêng và đặt unique constraint cho email |
| Dùng `@GeneratedValue` nhưng vẫn tự gán ID | Hai cơ chế tạo ID xung đột về ý nghĩa và vòng đời | Chọn một cơ chế: để Neo4j sinh hoặc để ứng dụng cấp |
| Cho rằng `@Id` tự tạo uniqueness constraint cho property tùy chỉnh | Metadata mapping không thay thế schema constraint | Tạo constraint Neo4j cho property ID do ứng dụng quản lý |
| Cho rằng `@Id` tự định nghĩa equality Java | Định danh persistence và equality object là hai cơ chế riêng | Thiết kế `equals()` và `hashCode()` theo vòng đời entity |

## 8. Quy trình chọn và kiểm tra ID

Khi thiết kế một entity mới, hãy làm rõ các câu hỏi sau:

1. Entity cần một định danh chỉ dùng bên trong Neo4j hay cần chia sẻ với hệ thống khác?
2. Giá trị ID được tạo ở Neo4j hay ở ứng dụng? Tránh đồng thời sử dụng hai cơ chế.
3. Kiểu của thuộc tính `@Id` có khớp với kiểu ID trong `Neo4jRepository` và các API service không?
4. Nếu dùng ID do ứng dụng cấp, đã có uniqueness constraint trên đúng label và property chưa?
5. ID có ổn định khi các thuộc tính nghiệp vụ như email hoặc tên thay đổi không?
6. Nếu nhiều transaction có thể cập nhật cùng entity, có cần `@Version` để phát hiện xung đột không?
7. Nếu entity mới được đưa vào collection, chiến lược `equals()` và `hashCode()` có xử lý đúng trạng thái chưa có ID không?

## 9. Tự kiểm tra

1. `@Id` cho SDN biết điều gì khi ánh xạ một entity?
2. `@GeneratedValue` mặc định khác gì với việc ứng dụng tự gán UUID?
3. Vì sao internal ID của Neo4j không nên được dùng làm mã tham chiếu công khai lâu dài?
4. Nếu entity dùng `String id`, kiểu ID trong `Neo4jRepository` phải khai báo thế nào?
5. Vì sao email có thể là thuộc tính unique nhưng không nhất thiết nên là `@Id`?
6. `@Id` và `@Version` lần lượt giải quyết vấn đề nào?

Khi chọn được định danh ổn định và khai báo `@Id` đúng cách, SDN có thể nhận diện entity nhất quán trong các thao tác đọc, ghi và xóa. Việc tách định danh persistence khỏi thuộc tính nghiệp vụ cũng giúp mô hình đồ thị dễ thay đổi và tích hợp với các hệ thống khác hơn.
