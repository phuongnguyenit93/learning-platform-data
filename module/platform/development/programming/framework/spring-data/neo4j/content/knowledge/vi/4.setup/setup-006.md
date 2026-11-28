# Tạo node entity và Neo4jRepository đầu tiên

## Mục tiêu bài học

Spring Data Neo4j (SDN) giúp ứng dụng Java làm việc với dữ liệu graph bằng các node entity, relationship và repository. Trong bài đầu tiên của chương Khởi tạo, chúng ta sẽ kết nối một ứng dụng Spring Boot với Neo4j, định nghĩa node `Person`, tạo `PersonRepository` và thực hiện thao tác lưu, tìm kiếm dữ liệu.

Sau bài học, bạn có thể:

- Thêm dependency Spring Data Neo4j vào dự án.
- Cấu hình kết nối tới Neo4j bằng URI và thông tin xác thực.
- Ánh xạ một lớp Java thành node bằng `@Node`.
- Khai báo định danh bằng `@Id` và hiểu vai trò của `@Version`.
- Tạo repository kế thừa `Neo4jRepository` để dùng các thao tác CRUD và truy vấn theo tên phương thức.
- Kiểm tra dữ liệu đã được lưu trong graph.

## 1. Chuẩn bị Neo4j và dự án Spring Boot

Ứng dụng cần một Neo4j instance đang hoạt động và có thể truy cập qua Bolt. Có thể dùng Neo4j Desktop, Neo4j Aura hoặc một instance chạy trong môi trường phát triển. Với cài đặt local thông thường, Bolt sử dụng cổng `7687`, còn Neo4j Browser thường truy cập qua cổng `7474`.

Nếu dùng Docker để chạy Neo4j 5 trong môi trường phát triển, có thể khởi động một instance như sau:

```bash
docker run --name neo4j-dev \
  --publish 7474:7474 \
  --publish 7687:7687 \
  --env NEO4J_AUTH='neo4j/replace-with-local-password' \
  neo4j:5
```

Thay `replace-with-local-password` bằng mật khẩu phù hợp với môi trường local. Mật khẩu trong ví dụ chỉ dành cho phát triển; không ghi mật khẩu thật vào source code hoặc đưa cấu hình bí mật lên hệ thống quản lý phiên bản. Nếu đã có database, hãy dùng URI, username và password do môi trường đó cung cấp.

### Thêm dependency

Với Gradle, thêm Spring Data Neo4j starter vào phần dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'
}
```

Với Maven, khai báo dependency tương ứng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-neo4j</artifactId>
</dependency>
```

Khi dự án dùng Spring Boot dependency management, phiên bản starter thường được quản lý theo phiên bản Spring Boot của dự án. Hãy giữ các dependency Spring Boot cùng một bộ phiên bản tương thích thay vì tự chọn một phiên bản SDN rời rạc.

Starter cung cấp tích hợp Neo4j Driver, Spring Data Neo4j và cơ chế cấu hình repository. Với cấu hình Spring Boot thông thường, ứng dụng không cần tự tạo driver hoặc transaction manager bằng tay.

## 2. Cấu hình kết nối tới Neo4j

Trong `src/main/resources/application.properties`, khai báo URI và thông tin xác thực:

```properties
spring.neo4j.uri=${NEO4J_URI:bolt://localhost:7687}
spring.neo4j.authentication.username=${NEO4J_USERNAME:neo4j}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
```

Các thuộc tính này có ý nghĩa:

| Thuộc tính | Vai trò |
|---|---|
| `spring.neo4j.uri` | Địa chỉ kết nối Bolt hoặc URI do dịch vụ Neo4j cung cấp |
| `spring.neo4j.authentication.username` | Tài khoản dùng để xác thực |
| `spring.neo4j.authentication.password` | Mật khẩu của tài khoản |

Ví dụ trên cho phép ghi đè URI và username qua biến môi trường. Biến `NEO4J_PASSWORD` cần được thiết lập trong môi trường chạy ứng dụng. Nếu dùng Neo4j Aura hoặc máy chủ từ xa, hãy thay URI local bằng URI kết nối được cấp; các dịch vụ từ xa có thể yêu cầu scheme bảo mật như `neo4j+s`.

Không commit password vào `application.properties`. Trong môi trường triển khai, lấy thông tin xác thực từ secret manager hoặc cơ chế quản lý biến môi trường của nền tảng. Nếu ứng dụng khởi động nhưng không kết nối được, kiểm tra URI, cổng Bolt, trạng thái server, firewall và thông tin xác thực.

Có thể thử kết nối trực tiếp trong Neo4j Browser bằng một câu lệnh đơn giản:

```cypher
RETURN 1 AS connected;
```

Khi nhận được kết quả `connected = 1`, kết nối tới database đang hoạt động. Bước này giúp tách lỗi kết nối database khỏi lỗi ánh xạ entity trong ứng dụng.

## 3. Tạo node entity đầu tiên với @Node

Trong Neo4j, node là một thực thể trong graph và có thể mang một hoặc nhiều label. Trong SDN, annotation `@Node` đánh dấu một lớp Java là node entity. Tên trong annotation là label được dùng trong graph.

Ví dụ, hệ thống quản lý người dùng cần node `Person` với mã định danh, tên và email:

```java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;

    private String email;

    protected Person() {
        // Constructor dùng cho cơ chế ánh xạ.
    }

    public Person(String name, String email) {
        this.id = UUID.randomUUID().toString();
        this.name = name;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public void changeEmail(String email) {
        this.email = email;
    }
}
```

Một số điểm cần hiểu:

- `@Node("Person")` khai báo label `Person`. Khi lưu entity, SDN ánh xạ nó thành node mang label này.
- `@Id` đánh dấu trường định danh của node. Trong ví dụ, mã được tạo ở phía ứng dụng bằng UUID nên có thể dùng ổn định ngoài database.
- `@Version` bật cơ chế optimistic locking và giúp SDN nhận biết entity mới khi dùng định danh được gán từ ứng dụng. Để trường version ở `null` khi tạo entity mới; SDN quản lý giá trị version trong quá trình lưu.
- Các trường `name` và `email` được ánh xạ thành thuộc tính node theo tên trường.
- Constructor không tham số được để ở mức `protected` cho cơ chế ánh xạ. Các constructor và phương thức truy cập còn lại tùy theo quy ước của dự án.

### Chọn chiến lược định danh

Định danh là phần quan trọng của entity. Với ví dụ trên, ứng dụng tự sinh UUID và gán vào `id`. Cách này thuận tiện khi mã cần được sử dụng trong API hoặc trao đổi giữa các dịch vụ.

Khi dùng ID do ứng dụng gán, nên khai báo `@Version` như ví dụ để SDN có thể phân biệt entity mới với entity đã tồn tại và kiểm soát cập nhật đồng thời. Không tự gán hoặc sửa version bằng logic nghiệp vụ.

SDN cũng hỗ trợ `@GeneratedValue` để dùng cơ chế sinh ID của Neo4j. Cần hiểu rõ loại ID được sinh và giới hạn của nó trước khi chọn. ID nội bộ của database không nên mặc định trở thành mã công khai hoặc mã nghiệp vụ của ứng dụng. Dù chọn chiến lược nào, kiểu ID của entity phải khớp với kiểu ID khai báo ở repository.

### Ràng buộc dữ liệu cho node

Nếu `id` phải duy nhất trong label `Person`, tạo uniqueness constraint trong Neo4j:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;
```

Nếu email cũng là duy nhất theo quy tắc nghiệp vụ, có thể tạo thêm constraint:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.email IS UNIQUE;
```

Constraint bảo vệ tính duy nhất ngay tại database, kể cả khi có nhiều ứng dụng hoặc nhiều luồng cùng ghi. Chỉ tạo constraint email khi nghiệp vụ thực sự yêu cầu email duy nhất và dữ liệu hiện có đáp ứng điều kiện đó.

## 4. Tạo Neo4jRepository đầu tiên

Spring Data Neo4j cung cấp `Neo4jRepository` để xây dựng repository cho node entity. Tạo interface `PersonRepository`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmail(String email);

    boolean existsByEmail(String email);
}
```

Hai tham số kiểu của `Neo4jRepository` là:

- `Person`: entity mà repository quản lý.
- `String`: kiểu của trường `@Id` trong entity.

Kế thừa `Neo4jRepository` cung cấp sẵn các thao tác thông dụng như:

| Phương thức | Công dụng |
|---|---|
| `save(entity)` | Lưu entity mới hoặc cập nhật entity đã tồn tại |
| `findById(id)` | Tìm entity theo ID, kết quả là `Optional` |
| `findAll()` | Lấy các entity phù hợp với repository |
| `existsById(id)` | Kiểm tra entity có tồn tại theo ID |
| `deleteById(id)` | Xóa entity theo ID |
| `count()` | Đếm số entity |

Ngoài các phương thức có sẵn, SDN hỗ trợ tạo truy vấn từ tên phương thức. Ví dụ `findByEmail` được phân tích để tìm node `Person` có thuộc tính `email` khớp với tham số. `existsByEmail` trả về kết quả tồn tại mà không cần viết câu Cypher thủ công.

Tên phương thức phải dùng thuộc tính Java đã được ánh xạ và tuân theo quy tắc đặt tên truy vấn của Spring Data. Với truy vấn phức tạp, điều kiện trên relationship hoặc kết quả tùy chỉnh, có thể khai báo Cypher bằng `@Query` ở repository trong các bài tiếp theo.

## 5. Gọi repository từ service

Repository là thành phần truy cập dữ liệu. Tầng service nên đảm nhận quy tắc nghiệp vụ và xác định ranh giới transaction. Ví dụ dưới đây minh họa đăng ký một người dùng và tìm người dùng theo email:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository personRepository;

    public PersonService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public Person register(String name, String email) {
        if (personRepository.existsByEmail(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        Person person = new Person(name, email);
        return personRepository.save(person);
    }

    @Transactional(readOnly = true)
    public Person getByEmail(String email) {
        return personRepository.findByEmail(email)
                .orElseThrow(() ->
                        new IllegalArgumentException("Person not found"));
    }
}
```

Trong ví dụ:

1. Spring inject `PersonRepository` qua constructor.
2. Service kiểm tra email theo quy tắc nghiệp vụ.
3. Service tạo entity `Person` với UUID mới và version ban đầu là `null`.
4. `save` gửi thao tác ghi tới Neo4j và trả về entity sau khi lưu.
5. Phương thức đọc tìm theo email và xử lý trường hợp không có kết quả.

Kiểm tra tồn tại trước khi lưu giúp thông báo lỗi thân thiện hơn, nhưng không thay thế uniqueness constraint. Hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra; constraint ở database mới là lớp bảo vệ cuối cùng. Ứng dụng nên xử lý lỗi vi phạm constraint thành phản hồi phù hợp.

Với nghiệp vụ gồm nhiều lần đọc và ghi cần thành công hoặc rollback cùng nhau, đặt `@Transactional` ở service method bao quanh toàn bộ quy trình. Spring Boot cùng starter Data Neo4j cấu hình hạ tầng transaction cho ứng dụng thông thường. Các thao tác repository riêng lẻ cũng được thực hiện trong transaction theo cơ chế của Spring Data.

## 6. Để Spring Boot tìm thấy repository

Spring Boot tự động cấu hình repository khi interface nằm trong phạm vi package scan của lớp có `@SpringBootApplication`. Một cấu trúc package đơn giản có thể như sau:

```text
com.example.graphapp
├── GraphApplication.java
├── person
│   ├── Person.java
│   ├── PersonRepository.java
│   └── PersonService.java
└── config
```

Lớp ứng dụng chính:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphApplication {

    public static void main(String[] args) {
        SpringApplication.run(GraphApplication.class, args);
    }
}
```

Đặt lớp chính ở package gốc để component scan và repository scan bao phủ các package con. Nếu repository nằm ngoài phạm vi scan mặc định, cần cấu hình package scan phù hợp, chẳng hạn bằng `@EnableNeo4jRepositories`. Không thêm annotation này nếu cấu trúc package đã được Spring Boot tự động phát hiện.

Khi ứng dụng khởi động, Spring tạo bean cho repository và inject nó vào service. Nếu nhận lỗi không tìm thấy bean repository, hãy kiểm tra package của lớp ứng dụng, package repository và dependency starter trước khi viết cấu hình thủ công.

## 7. Kiểm tra node đã được lưu

Sau khi gọi `PersonService.register`, mở Neo4j Browser và chạy:

```cypher
MATCH (p:Person)
RETURN p.id AS id, p.name AS name, p.email AS email
ORDER BY p.name;
```

Kết quả cần có node mang label `Person` cùng các thuộc tính tương ứng. Có thể kiểm tra một bản ghi cụ thể bằng ID:

```cypher
MATCH (p:Person {id: $personId})
RETURN p;
```

Trong Neo4j Browser, thay `$personId` bằng giá trị thực hoặc truyền parameter theo giao diện của Browser. Nếu truy vấn không trả về node, kiểm tra service đã được gọi thành công, transaction đã hoàn tất và ứng dụng đang kết nối đúng database.

Có thể kiểm tra số lượng node:

```cypher
MATCH (p:Person)
RETURN count(p) AS personCount;
```

Không nên dùng `findAll()` để tải toàn bộ node khi dữ liệu đã lớn. Với danh sách có quy mô lớn, hãy thiết kế phân trang hoặc truy vấn có điều kiện để giới hạn dữ liệu trả về.

## 8. Các lỗi thường gặp khi khởi tạo

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Connection refused hoặc timeout | Neo4j chưa chạy, sai URI hoặc cổng Bolt bị chặn | Kiểm tra trạng thái server, URI và cổng `7687` |
| Authentication failed | Username hoặc password không đúng | Kiểm tra thông tin xác thực của database |
| Không tìm thấy bean `PersonRepository` | Repository nằm ngoài package scan hoặc thiếu starter | Kiểm tra dependency và vị trí package |
| Entity không lưu được | Thiếu `@Id`, kiểu ID không khớp hoặc cấu hình entity sai | Kiểm tra entity và log ánh xạ |
| Tạo node trùng mã | Không có uniqueness constraint hoặc chiến lược ID không nhất quán | Tạo constraint và kiểm tra quy tắc sinh ID |
| Lỗi optimistic locking | Version cũ hoặc entity được cập nhật đồng thời | Đọc lại entity mới nhất và xử lý xung đột theo nghiệp vụ |
| Tìm theo email không có kết quả | Giá trị lưu và giá trị tìm kiếm khác nhau | Kiểm tra dữ liệu, chuẩn hóa email nhất quán ở tầng ứng dụng |

## 9. Tự kiểm tra

1. `@Node("Person")` có vai trò gì trong quá trình SDN ánh xạ dữ liệu?
2. Vì sao kiểu ID ở `Neo4jRepository<Person, String>` phải khớp với kiểu trường `@Id`?
3. Khi tự gán UUID cho entity, `@Version` hỗ trợ SDN như thế nào?
4. `findByEmail` được Spring Data xử lý ra sao dù repository không viết Cypher?
5. Vì sao kiểm tra `existsByEmail` trước khi lưu không thể thay thế uniqueness constraint?
6. Khi nào nên đặt `@Transactional` ở service thay vì chỉ gọi repository trực tiếp?

Hãy thử tạo một node `Person`, lưu bằng `PersonRepository`, tìm lại bằng email và xác nhận node trong Neo4j Browser. Sau đó thay đổi email, lưu lại entity và quan sát dữ liệu đã cập nhật trong graph.
