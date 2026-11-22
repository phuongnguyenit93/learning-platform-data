# Phân quyền theo chủ sở hữu để ngăn truy cập trực tiếp đối tượng không được phép

> **Ngữ cảnh:** Spring Security — fundamentals / Bảo vệ dữ liệu. Bài học tập trung vào **object-level authorization** (kiểm tra quyền đối với **từng đối tượng dữ liệu**) trong ứng dụng Java 17+, Spring Boot 3.x và Spring Security 6.x (Servlet). Phân quyền theo chủ sở hữu giúp ngăn **IDOR** (*Insecure Direct Object References*) và **BOLA** (*Broken Object Level Authorization*) khi client thay đổi ID để xem, sửa hoặc xóa dữ liệu của người khác.

## 1. Vấn đề: đăng nhập thành công vẫn có thể đọc nhầm dữ liệu của người khác

Giả sử ứng dụng lưu các tài liệu riêng tư:

| ID tài liệu | Chủ sở hữu | Nội dung |
|---|---|---|
| `101` | `alice` | Ghi chú riêng của Alice |
| `202` | `bob` | Ghi chú riêng của Bob |

Alice đã đăng nhập và được gọi `GET /api/documents/101`. Nếu code ở backend chỉ kiểm tra “đã đăng nhập” mà truy vấn theo `id`, Alice có thể sửa URL thành `GET /api/documents/202` và nhận tài liệu của Bob.

Ví dụ code **có lỗ hổng**:

~~~java
// Sai: chỉ kiểm tra request đã đăng nhập ở SecurityFilterChain.
@GetMapping("/api/documents/{id}")
DocumentEntity get(@PathVariable Long id) {
    return documentRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));
}
~~~

Nếu route chỉ có `.authenticated()`, Spring Security đã biết **ai gọi** nhưng chưa xác minh **họ được truy cập bản ghi nào**. Chính sách phân quyền theo vai trò như `hasRole("USER")` cũng chưa đủ: Alice và Bob đều có thể mang `ROLE_USER`.

**BOLA** xảy ra khi API cho người dùng gọi một chức năng hợp lệ nhưng không kiểm tra quyền trên **đối tượng cụ thể** đang được tham chiếu. **IDOR** là biểu hiện phổ biến của lỗi này khi ID/đường dẫn cho phép truy cập trực tiếp tài nguyên không được phép. Tham chiếu có thể là số tăng dần, UUID, slug, tên file, object-storage key, ID trong JSON, query string, header hoặc quan hệ lồng nhau.

Ví dụ:

~~~http
GET /api/documents/202 HTTP/1.1
Authorization: Basic <credentials-of-alice>
~~~

Attacker **không nhất thiết phải phá xác thực**. Một người dùng hợp lệ có thể đoán/nhận ID từ log, URL, chia sẻ nhầm, API khác hoặc chính kết quả hiển thị rồi thử truy cập tài nguyên khác.

**Nguyên tắc chính:** server phải kiểm tra `người đang được xác thực + đối tượng thực tế + hành động cần thực hiện + phạm vi dữ liệu (ví dụ tenant)` ở **mỗi** đường đọc và ghi. Không coi việc client biết ID là bằng chứng được phép truy cập.

## 2. Authentication, authorization và ownership khác nhau ra sao?

- **Authentication (xác thực):** Alice đã cung cấp bằng chứng hợp lệ; `SecurityContext` có `Authentication` đáng tin, ví dụ `authentication.getName() == "alice"`.
- **Route/function authorization:** người dùng đã đăng nhập hoặc có role phù hợp thì được gọi loại endpoint nào; ví dụ `GET /api/documents/{id}` cần `authenticated()`.
- **Object-level authorization:** với chính tài liệu `id=202`, liệu Alice được **đọc** hay **sửa** không? Quyền có thể dựa trên owner, tenant, chia sẻ, membership, ACL, vai trò trong dự án, trạng thái tài nguyên...
- **Data access:** repository/query chỉ trả bản ghi nằm trong phạm vi cho phép. Đây là cách bảo vệ hiệu quả vì cả truy xuất lẫn lọc kết quả đều tôn trọng chính sách.

Bảng quyết định trong một ứng dụng “chủ sở hữu duy nhất được đọc”:

| Người gọi | URL | Kết quả | Lý do |
|---|---|---|---|
| Chưa đăng nhập | `GET /api/documents/101` | `401` với Basic API demo | Chưa có danh tính hợp lệ |
| `alice` | `GET /api/documents/101` | `200` | Alice sở hữu tài liệu |
| `alice` | `GET /api/documents/202` | `404` trong demo | Không có tài liệu **được phép thấy** với ID đó |
| `bob` | `GET /api/documents/202` | `200` | Bob sở hữu tài liệu |
| `bob` | `GET /api/documents/101` | `404` trong demo | Bob không được thấy tài liệu của Alice |
| `alice` | `GET /api/documents/999` | `404` | Tài liệu không tồn tại |

`403 Forbidden` cũng có thể phù hợp khi chính sách cho phép người dùng biết tài nguyên tồn tại nhưng cấm hành động đang yêu cầu. **`404 Not Found` là lựa chọn có chủ đích** để không tiết lộ sự tồn tại của tài nguyên người khác; dùng thống nhất cho “không tồn tại” và “không nằm trong phạm vi được truy cập”. Việc lựa chọn status phải nhất quán với hợp đồng API và mục tiêu chống lộ thông tin.

Số `101` hay UUID đều chỉ là **định danh**, không phải capability token tự động cấp quyền. Đổi ID tuần tự thành UUID làm việc đoán khó hơn, nhưng **không sửa** lỗ hổng nếu backend vẫn cho người biết ID đọc nội dung.

## 3. Quy trình bảo vệ dữ liệu theo chủ sở hữu

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant A as Controller
    participant V as Service
    participant R as Repository/DB
    C->>S: GET /api/documents/202 + credentials của Alice
    S->>S: Authentication = Alice
    S->>A: Cho gọi endpoint đã xác thực
    A->>V: getOwned(202)
    V->>S: Lấy principal đã xác minh từ SecurityContext
    S-->>V: alice
    V->>R: findByIdAndOwnerUsername(202, "alice")
    R-->>V: Không có kết quả trong phạm vi Alice
    V-->>A: 404
    A-->>C: 404 (không trả tài liệu Bob)
~~~

Có **hai tầng kiểm soát** trong ví dụ:

1. Spring Security chặn request chưa đăng nhập bằng cấu hình `SecurityFilterChain` và `@PreAuthorize("isAuthenticated()")`.
2. Service/repository chỉ đọc bản ghi có **ID yêu cầu và chủ sở hữu khớp danh tính đã xác thực**. Đó mới là kiểm tra chống BOLA ở mức đối tượng.

Biểu thức dữ liệu:

~~~sql
-- Sai: kiểm tra ID, bỏ qua chủ sở hữu.
SELECT id, owner_username, title, content
FROM documents
WHERE id = :requestedId;

-- Đúng trong mô hình "owner-only":
SELECT id, owner_username, title, content
FROM documents
WHERE id = :requestedId
  AND owner_username = :authenticatedUsername;
~~~

`:requestedId` là dữ liệu từ URL **không đáng tin về quyền**. `:authenticatedUsername` phải lấy từ `Authentication` đã xác minh hoặc một nguồn server đáng tin; không lấy từ `?owner=alice`, header `X-User` tự khai hoặc trường `ownerId` trong JSON của client.

Một policy phức tạp có thể thay điều kiện owner bằng `owner OR shared_access OR authorized_project_membership`, nhưng **vẫn phải ràng buộc hành động và tài nguyên cụ thể**.

## 4. Ví dụ chạy được với Spring Boot, Spring Security và H2

Ví dụ sau tạo API GET đọc danh sách và từng tài liệu. H2 là cơ sở dữ liệu **in-memory** để chạy độc lập, không cần server DB ngoài. Có hai tài khoản mẫu `alice` và `bob`; mỗi người có một bản ghi. `/api/documents/{id}` chỉ tìm theo cả `id` và chủ sở hữu.

**Môi trường:** JDK 17+, Maven 3.9+, Spring Boot **3.5.0** (Spring Security 6.x, Jakarta Servlet). Credentials trong demo chỉ dùng tại máy học tập. Mẫu chỉ có các endpoint `GET` để giữ **CSRF protection mặc định**; phần cập nhật/xóa được hướng dẫn riêng ở mục 7.

Cấu trúc dự án:

~~~text
ownership-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/ownership/
│   ├── OwnershipDemoApplication.java
│   ├── SecurityConfig.java
│   ├── DocumentEntity.java
│   ├── DocumentRepository.java
│   ├── DocumentService.java
│   └── DocumentController.java
└── src/test/java/com/example/ownership/
    └── OwnershipAuthorizationTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ownership-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:ownership;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

`create-drop` tái tạo dữ liệu học tập theo vòng đời ứng dụng; không dùng tùy tiện với database chứa dữ liệu thật. `open-in-view=false` khiến service phải hoàn thành đọc dữ liệu trong transaction thay vì dựa vào session JPA mở sang tầng HTTP.

### 4.3. OwnershipDemoApplication.java

~~~java
package com.example.ownership;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OwnershipDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner seedDocuments(DocumentRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                new DocumentEntity(
                    101L, "alice", "Alice private", "Only Alice sees this"),
                new DocumentEntity(
                    202L, "bob", "Bob private", "Only Bob sees this")
            ));
        };
    }
}
~~~

Hai bản ghi có ID cố định để dễ tái hiện phép thử. `saveAll` chỉ được chạy lúc khởi động demo; database H2 trong bộ nhớ sẽ được dựng lại khi chạy app.

### 4.4. SecurityConfig.java

~~~java
package com.example.ownership;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(
                    "/api/documents", "/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}alice123")
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password("{noop}bob123")
                .roles("USER")
                .build()
        );
    }
}
~~~

Giải thích:

- `authenticated()` chỉ xác minh rằng request mang danh tính đã đăng nhập. Điều kiện này **không tự chứng minh** user là chủ sở hữu tài liệu.
- `@EnableMethodSecurity` bật `@PreAuthorize` tại service. Spring Boot Starter Security không tự bật phương thức này.
- `SessionCreationPolicy.STATELESS` phù hợp với các lượt HTTP Basic độc lập trong demo.
- `DispatcherType.ERROR` và `FORWARD` được cho phép để cơ chế trả lỗi 404 của Spring MVC không bị quy tắc `anyRequest().denyAll()` chặn trong lượt dispatch nội bộ. Không mở thêm API dữ liệu công khai.
- `{noop}` lưu mật khẩu plaintext **chỉ trong demo**. Hệ thống thật cần password encoder an toàn, bí mật được quản lý phù hợp và HTTPS.
- Không có `csrf().disable()`: toàn bộ request mẫu ở đây là `GET`. Với API ghi dữ liệu, đánh giá CSRF theo cơ chế xác thực và loại client trước khi quyết định cấu hình.

### 4.5. DocumentEntity.java

~~~java
package com.example.ownership;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String content;

    protected DocumentEntity() {
        // JPA requires a no-argument constructor.
    }

    public DocumentEntity(
            Long id, String ownerUsername, String title, String content) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
        this.content = content;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public String getContent() {
        return content;
    }
}
~~~

Đây là bản ghi database. `ownerUsername` được gán phía server lúc tạo dữ liệu demo. Trong hệ thống thật nên dùng **ID principal bất biến**, ví dụ user ID từ hệ thống danh tính, bởi username/email có thể thay đổi. Với nhiều tenant, thêm `tenantId` vào model và ràng buộc tenant khi truy vấn.

### 4.6. DocumentRepository.java

~~~java
package com.example.ownership;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    Optional<DocumentEntity> findByIdAndOwnerUsername(
            Long id, String ownerUsername);

    List<DocumentEntity> findAllByOwnerUsernameOrderByIdAsc(
            String ownerUsername);
}
~~~

**Đây là điểm bảo vệ quan trọng nhất trong ví dụ.** Repository yêu cầu **cả hai điều kiện**: ID do client muốn đọc và danh tính chủ sở hữu do backend xác minh. `findAllByOwnerUsernameOrderByIdAsc` bảo vệ cả **danh sách**, tránh tình trạng API chi tiết an toàn nhưng API list lại trả toàn bộ dữ liệu.

Nếu tài liệu tồn tại nhưng thuộc user khác, phương thức `findByIdAndOwnerUsername` trả `Optional.empty()`, tương tự một ID không tồn tại trong phạm vi user đó.

### 4.7. DocumentService.java

~~~java
package com.example.ownership;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public DocumentView getOwned(Long documentId) {
        String username = currentUsername();

        DocumentEntity document = repository
            .findByIdAndOwnerUsername(documentId, username)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));

        return toView(document);
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public List<DocumentView> listOwned() {
        String username = currentUsername();

        return repository
            .findAllByOwnerUsernameOrderByIdAsc(username)
            .stream()
            .map(DocumentService::toView)
            .toList();
    }

    private static String currentUsername() {
        return SecurityContextHolder.getContext()
            .getAuthentication()
            .getName();
    }

    private static DocumentView toView(DocumentEntity document) {
        return new DocumentView(
            document.getId(),
            document.getTitle(),
            document.getContent());
    }

    public record DocumentView(
            Long id,
            String title,
            String content) {
    }
}
~~~

Lưu ý:

1. `@PreAuthorize("isAuthenticated()")` đảm bảo chỉ người đã xác thực mới gọi được **public service method** qua proxy Spring. `Authentication` trong `SecurityContextHolder` là kết quả được Spring Security thiết lập sau khi xác thực; trong demo username của nó khớp `ownerUsername`.
2. `currentUsername()` đọc danh tính tại **tầng service**, tránh phải nhận một tham số `ownerUsername` tùy ý do controller hoặc caller truyền vào. Không cung cấp endpoint cho client tự đặt lại identity dùng làm bộ lọc.
3. Chính câu lệnh `findByIdAndOwnerUsername(documentId, username)` thực hiện object-level authorization. `@PreAuthorize("isAuthenticated()")` **một mình không đủ** bảo vệ quyền sở hữu.
4. `DocumentView` là DTO trả về HTTP; không tự serialize toàn bộ entity. Nhờ vậy không vô tình đưa các trường nội bộ/nhạy cảm khác ra ngoài khi entity phát triển.
5. `@Transactional(readOnly = true)` quy định vòng đời giao dịch cho thao tác đọc JPA. Việc chuyển entity sang DTO được thực hiện ngay trong service.
6. Phương thức có `@PreAuthorize` phải được gọi qua **Spring bean proxy**. Tự gọi `this.getOwned(...)` từ một method khác trong cùng class có thể bỏ qua method interceptor; khi đó phải bảo đảm policy vẫn được thực thi trong logic service/repository.
7. Ở thiết kế nhiều tenant, một `ownerUsername` không đủ bảo đảm cách ly tenant nếu danh tính/ID không unique toàn hệ thống; thêm khóa `tenantId` lấy từ ngữ cảnh tin cậy vào truy vấn.

### 4.8. DocumentController.java

~~~java
package com.example.ownership;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping
    public List<DocumentService.DocumentView> list() {
        return service.listOwned();
    }

    @GetMapping("/{id}")
    public DocumentService.DocumentView get(@PathVariable Long id) {
        return service.getOwned(id);
    }
}
~~~

Controller chỉ nhận `id` rồi chuyển xuống service. Controller **không tự quyết định owner**, không lấy `owner` từ query string và không trả entity lấy trực tiếp qua `findById(id)`.

### 4.9. Kiểm thử tự động: OwnershipAuthorizationTest.java

~~~java
package com.example.ownership;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void aliceCanReadHerDocument() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.title").value("Alice private"));
    }

    @Test
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/documents/202")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void bobCannotReadAlicesDocument() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void nonExistingIdIsNotFound() throws Exception {
        mvc.perform(get("/api/documents/999")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void anonymousMustAuthenticate() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceOnlyListsHerDocuments() throws Exception {
        mvc.perform(get("/api/documents")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(101));
    }

    @Test
    void bobOnlyListsHisDocuments() throws Exception {
        mvc.perform(get("/api/documents")
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(202));
    }
}
~~~

Test đặt cả **người được phép**, **người khác chủ sở hữu**, **anonymous**, **ID không tồn tại** và **API danh sách** trong cùng bài; không chỉ test “Alice được xem bản ghi Alice”.

### 4.10. Chạy app và quan sát

Trong thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` cần tải dependencies Maven lần đầu (nếu chưa có cache). Với `mvn spring-boot:run`, server mặc định nghe ở `http://localhost:8080` nếu port trống và không có cấu hình khác.

Tại terminal khác, thử:

~~~bash
# Alice xem đúng tài liệu của Alice
curl -i -u alice:alice123 http://localhost:8080/api/documents/101

# Alice thử đổi ID sang tài liệu Bob
curl -i -u alice:alice123 http://localhost:8080/api/documents/202

# Bob xem đúng tài liệu của Bob
curl -i -u bob:bob123 http://localhost:8080/api/documents/202

# Chưa đăng nhập
curl -i http://localhost:8080/api/documents/101

# Alice xem danh sách (phải có đúng ID 101)
curl -i -u alice:alice123 http://localhost:8080/api/documents

# Bob xem danh sách (phải có đúng ID 202)
curl -i -u bob:bob123 http://localhost:8080/api/documents
~~~

Trên PowerShell, nếu `curl` là alias của `Invoke-WebRequest`, hãy dùng `curl.exe` với cùng tham số.

Kết quả cần kiểm tra:

| Request | HTTP status dự kiến | Dữ liệu được phép trả |
|---|---|---|
| Alice → `/api/documents/101` | `200` | `id=101`, title `Alice private`, content `Only Alice sees this` |
| Alice → `/api/documents/202` | `404` | **Không trả nội dung của Bob** |
| Bob → `/api/documents/202` | `200` | `id=202`, title `Bob private`, content `Only Bob sees this` |
| Anonymous → `/api/documents/101` | `401` | Không có tài liệu; Basic challenge |
| Alice → `/api/documents` | `200` | Danh sách chỉ chứa tài liệu `101` |
| Bob → `/api/documents` | `200` | Danh sách chỉ chứa tài liệu `202` |
| Alice → `/api/documents/999` | `404` | Không phân biệt với ID thuộc người khác |

JSON trả về khi Alice đọc được tài liệu của mình về mặt dữ liệu là:

~~~json
{
  "id": 101,
  "title": "Alice private",
  "content": "Only Alice sees this"
}
~~~

Thứ tự JSON fields, HTTP headers mặc định và JSON lỗi do Spring Boot/Servlet container tạo có thể khác; **đừng chấm test dựa vào chuỗi body lỗi mặc định**. Trong ví dụ, mục tiêu QA là status và không rò rỉ dữ liệu của chủ sở hữu khác.

## 5. Tại sao phải lọc ngay tại truy vấn và tại tầng service?

Một cách “vá” đơn giản là gọi `findById(id)`, sau đó kiểm tra:

~~~java
DocumentEntity document = repository.findById(documentId)
    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

if (!document.getOwnerUsername().equals(authenticatedUsername)) {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND);
}
return toView(document);
~~~

Đoạn này **có thể ngăn đọc trái phép khi được triển khai đầy đủ và đúng mọi đường gọi**, nhưng có các rủi ro về việc quên kiểm tra, lặp logic, lộ thông tin trước bước kiểm tra, khó áp dụng với danh sách, và tình huống kiểm tra rồi ghi qua hai bước tách rời.

Trong mô hình owner-only, đưa điều kiện quyền vào truy vấn:

~~~java
repository.findByIdAndOwnerUsername(documentId, authenticatedUsername)
~~~

Khi đó query chỉ tìm **trong phạm vi user được phép**. Với API list, dùng `findAllByOwnerUsername...` ngay từ database, không lấy toàn bộ rồi lọc `stream().filter(...)` trong memory. Lọc sau query làm tăng nguy cơ rò dữ liệu qua logs, bộ nhớ đệm, phân trang, tổng số bản ghi, export hoặc query kết hợp.

**Không phải lúc nào cũng chỉ có một cột `owner_username`.** Dự án thực tế có thể có owner nhóm, project member, người được chia sẻ, quyền theo action và tenant. Policy nên được biểu diễn rõ ràng (query predicate, policy service, ACL/permission evaluator, database row-level security, hoặc phối hợp), và phải áp dụng cho từng truy vấn/đường ghi.

Spring Security bảo vệ endpoint và service bằng các cấu trúc như `authorizeHttpRequests`, `@PreAuthorize`, `@PostAuthorize`. Tuy nhiên framework không thể tự đoán quan hệ “Alice được đọc document 101 nhưng không được đọc document 202”; domain phải cung cấp điều kiện hoặc policy check.

### @PreAuthorize cho quyền trên đối tượng

Nếu muốn biểu diễn policy qua method security, một tùy chọn **minh họa** là:

~~~java
@PreAuthorize("@documentPolicy.canRead(#documentId, authentication)")
public DocumentView loadDocument(Long documentId) {
    // Chỉ chạy khi policy bean cho phép.
}
~~~

Đây là snippet **không độc lập**: phải có `@EnableMethodSecurity`, một bean tên `documentPolicy` với method `canRead(...)`, service là Spring-managed bean và cách truy cập dữ liệu thực tế. `@PreAuthorize("hasRole('USER')")` chỉ kiểm tra vai trò chung; nó chưa kiểm tra ownership. Nếu dùng `@PostAuthorize("returnObject.ownerId == authentication.name")` thì object đã được tải trước khi quyết định quyền, cần cân nhắc rủi ro dữ liệu nhạy cảm trong memory/side effects và cách xử lý 403. Trong ví dụ chạy được, truy vấn giới hạn theo owner giúp tự nhiên trả 404.

## 6. Phân quyền phải áp dụng cho *hành động*, không chỉ cho GET

Chống BOLA bao gồm mọi đường có ID:

- **Đọc:** `GET /api/documents/{id}`, download attachment, preview file, lấy trạng thái.
- **Sửa:** `PATCH/PUT /api/documents/{id}`, thay title/content/visibility.
- **Xóa:** `DELETE /api/documents/{id}`.
- **Thêm quan hệ:** chia sẻ tài liệu, chuyển tài liệu sang project, gắn file, đổi owner.
- **Hàng loạt:** bulk delete/export/update với danh sách IDs; phải kiểm từng ID hoặc áp dụng filter quyền vào câu lệnh bulk.
- **Danh sách/tìm kiếm:** paging, search, filter, count, export, báo cáo; luôn ràng buộc phạm vi dữ liệu ở nguồn.

Ví dụ cho write **ở mức database** (minh họa mở rộng, chưa thuộc API GET chạy được ở mục 4):

~~~java
// Thêm vào DocumentRepository; cần imports @Modifying, @Query, @Param.
@Modifying
@Query("update DocumentEntity d set d.title = :title " +
       "where d.id = :id and d.ownerUsername = :owner")
int renameIfOwned(
    @Param("id") Long id,
    @Param("owner") String owner,
    @Param("title") String title);

// Thêm vào DocumentService; cần @Transactional và principal tin cậy.
@PreAuthorize("isAuthenticated()")
@Transactional
public void renameOwned(Long id, String title) {
    String username = currentUsername();
    int modified = repository.renameIfOwned(id, username, title);
    if (modified == 0) {
        throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found");
    }
}
~~~

Các snippet trên là **mảnh mở rộng** trong hai class đã giới thiệu; nếu tích hợp cần thêm import tương ứng, khai báo method ở đúng class, validation input và endpoint phù hợp. `UPDATE ... WHERE id = ? AND owner = ?` vừa kiểm tra ownership **vừa thực hiện mutation trong một câu lệnh**. Nếu thay bằng “đọc theo ID → kiểm owner → cập nhật theo ID” ở những bước tách rời, cần lưu ý cạnh tranh thay đổi owner/quyền (TOCTOU: *time of check to time of use*). Với optimistic locking/version, yêu cầu phiên bản đúng cũng có thể nằm trong predicate của update.

Khi làm `DELETE`, áp dụng tương tự:

~~~sql
DELETE FROM documents
WHERE id = :requestedId
  AND owner_username = :authenticatedUsername;
~~~

Kiểm tra số dòng ảnh hưởng để quyết định `404`/kết quả tương ứng. Đừng làm `deleteById(requestedId)` chỉ dựa trên route đã `authenticated()`.

**Với API chỉnh sửa dữ liệu, CSRF là chủ đề riêng cần xử lý đúng:** mẫu chạy được sử dụng HTTP Basic và giữ CSRF bảo vệ mặc định, vì trình duyệt có thể tự gửi Basic credentials. Nếu bổ sung `PATCH/DELETE`, cần hỗ trợ CSRF token cho client dùng cookie/browser, hoặc xác lập mô hình stateless và cách đưa credentials không bị trình duyệt tự đính kèm trước khi xem xét cấu hình CSRF. Không “sửa lỗi 403” bằng cách tắt CSRF tùy tiện.

## 7. Phân biệt 401, 403 và 404 trong bảo vệ đối tượng

| Status | Ý nghĩa thực tế | Nên áp dụng khi nào |
|---|---|---|
| `401 Unauthorized` | Client chưa có credentials hợp lệ theo scheme | Anonymous hoặc sai HTTP Basic/token; thường cần challenge thích hợp |
| `403 Forbidden` | Caller được nhận diện nhưng không được thực hiện action | Ví dụ người dùng biết tài liệu có tồn tại/được chia sẻ ở quyền đọc nhưng không được sửa |
| `404 Not Found` | Tài nguyên không có trong **phạm vi được phép truy cập** | Ví dụ tài liệu người khác hoặc ID không tồn tại, khi muốn tránh tiết lộ sự tồn tại |

Không áp dụng một công thức status cứng cho mọi cơ chế. Với API chỉ đọc tài liệu riêng tư, việc trả 404 giống nhau cho ID không tồn tại và ID người khác là lựa chọn rõ ràng. Nhưng API cộng tác có thể chủ động cho biết “bạn thấy tài liệu này nhưng không được chỉnh sửa” và trả 403 cho PATCH.

Cũng cần tránh **side channel**: dù cả hai trường hợp đều trả 404, response body, header, thời gian xử lý, cache key hoặc log phía client có thể vô tình khác nhau và tiết lộ sự tồn tại của tài nguyên. Không đưa tên owner, document title hoặc lời giải thích nội bộ vào lỗi trả cho người không có quyền.

Một bộ lọc phân quyền đúng nhưng API trả `200` cùng body `null` cho ID người khác không nhất thiết là lỗi bảo mật, song có thể làm hợp đồng API mơ hồ. Xác định rõ thiết kế response, kiểm thử và giữ hành vi nhất quán.

## 8. Trường hợp quyền sở hữu phức tạp hơn một username

### 8.1. Nhiều tenant hoặc nhiều tổ chức

Trong SaaS, một document có thể có `tenant_id` và `owner_user_id`. Cần ràng buộc cả hai:

~~~sql
SELECT id, title, content
FROM documents
WHERE id = :documentId
  AND tenant_id = :currentTenantId
  AND owner_user_id = :currentUserId;
~~~

`currentTenantId` và `currentUserId` phải suy ra từ ngữ cảnh server đã xác minh, không tin `X-Tenant-ID` tự khai nếu chưa có cơ chế ánh xạ/kiểm chứng tenant. Nếu một người dùng chuyển tenant, backend phải xác định tenant nào đang hoạt động và membership/quyền tương ứng. Cần kiểm tra cả **truy cập xuyên tenant**, dù document ID là UUID khó đoán.

### 8.2. Chủ sở hữu, người được chia sẻ và quyền theo thao tác

Đôi khi người được chia sẻ có quyền `READ` nhưng không được `WRITE`. Một policy minh họa:

~~~text
canRead(user, doc) =
    sameTenant(user, doc)
    AND (isOwner(user, doc) OR hasShareGrant(user, doc, READ))

canEdit(user, doc) =
    sameTenant(user, doc)
    AND (isOwner(user, doc) OR hasShareGrant(user, doc, WRITE))

canDelete(user, doc) =
    sameTenant(user, doc)
    AND (isOwner(user, doc) OR hasProjectAdminPermission(user, doc))
~~~

`hasRole("ADMIN")` không tự có nghĩa được đọc tài liệu của **mọi tenant**. Nếu có nhân viên hỗ trợ cần “break glass”, phải có policy riêng, ghi audit và giới hạn phạm vi. Không diễn giải `ROLE_USER` thành “đọc được tất cả tài liệu”.

### 8.3. Quan hệ cha-con / nested ID

Với endpoint `/api/projects/{projectId}/documents/{documentId}`, đừng chỉ kiểm quyền trên `projectId` rồi tải một `documentId` bất kỳ. Bản ghi phải thực sự thuộc project đó **và** người gọi có quyền trên project/tài liệu.

~~~sql
SELECT d.*
FROM documents d
JOIN project_members m ON m.project_id = d.project_id
WHERE d.id = :documentId
  AND d.project_id = :projectId
  AND m.user_id = :authenticatedUserId
  AND m.can_read = TRUE;
~~~

Đây là SQL mô tả ý tưởng, cần điều chỉnh tên cột, phép nối và policy thực tế. Một số quyền yêu cầu cả thành viên project và ACL riêng của document; phải biểu diễn đầy đủ policy đó, không mặc định query minh họa đủ cho mọi hệ thống.

### 8.4. File download và đường dẫn ngoài

Nếu controller xác minh quyền rồi tạo **signed URL** tải file, URL đó phải giới hạn đối tượng, thời hạn và phạm vi hành động. Tránh trả storage key/URL công khai vĩnh viễn hoặc để endpoint `/download/{fileId}` bypass policy của document cha. Với background job, message queue, GraphQL resolver, WebSocket, scheduled export và batch processor, phải truyền principal/tenant context đáng tin hoặc service identity cùng policy được xác định; không giả định request HTTP chính là điểm vào duy nhất.

## 9. Các anti-pattern và cách sửa

### 9.1. Chỉ kiểm tra đăng nhập

~~~java
// Không đủ: bất kỳ user nào cũng có thể tải bất kỳ ID.
.requestMatchers("/api/documents/**").authenticated()
~~~

Đây là **cổng vào**, cần thêm kiểm tra resource trong service/repository.

### 9.2. Tin ownerId client gửi

~~~json
{
  "title": "My secret",
  "ownerUsername": "bob"
}
~~~

Nếu server tin thuộc tính `ownerUsername` để tạo hoặc sửa bản ghi, người dùng có thể giả mạo người sở hữu hoặc chuyển quyền trái phép. Dùng DTO cho phép nhập đúng trường được phép, server tự gán owner từ principal; nếu sản phẩm hỗ trợ chuyển ownership, cần endpoint riêng với policy mạnh hơn.

### 9.3. Lấy tất cả rồi lọc ở Java

~~~java
// Sai cho API list: dữ liệu ngoài phạm vi đã bị tải vào memory.
return repository.findAll().stream()
    .filter(doc -> doc.getOwnerUsername().equals(username))
    .toList();
~~~

Ngoài rủi ro rò dữ liệu, cách này còn sai với **paging, count, sorting** khi lọc sau database. Dùng query ngay từ đầu với predicate quyền; pagination/count phải dựa trên cùng phạm vi.

### 9.4. Kiểm ownership một lần rồi tái sử dụng dữ liệu ở đường khác

Ví dụ route GET đã có `findByIdAndOwnerUsername` nhưng DELETE dùng `deleteById`, hoặc export dùng `findAll`. Chính sách phải được kiểm tra cho **từng thao tác**. Để tránh bỏ sót, ưu tiên các method repository/service có tên phản ánh phạm vi như `findOwned`, `updateOwned`, `deleteOwned`, test theo ma trận nhiều người dùng và code review những lời gọi `findById`/bulk operations nhạy cảm.

### 9.5. Dùng UUID hoặc che nút Edit làm kiểm soát chính

Ẩn nút trên frontend chỉ cải thiện UX. Attacker vẫn có thể gửi HTTP request trực tiếp; UUID không ngăn truy cập nếu đã bị lộ. **Backend** mới phải thực thi quyền.

### 9.6. Cache chỉ theo document ID

Nếu cache `GET /api/documents/101` theo ID mà bỏ qua user/tenant/policy, kết quả được lưu cho người được phép có thể bị phục vụ lại cho người không có quyền. Cần kiểm tra quyền trước khi trả cache, dùng cache key/scope phù hợp, và thiết kế invalidation khi ownership hoặc ACL thay đổi. CDN/reverse proxy cũng không được chia sẻ response riêng tư giữa các principal; cân nhắc header `Cache-Control: private, no-store` theo yêu cầu sản phẩm.

### 9.7. Method security không được kích hoạt hoặc bị gọi vòng trong cùng bean

`@PreAuthorize` cần `@EnableMethodSecurity` và thông thường hoạt động qua Spring AOP proxy. Nếu quên bật, annotation không bảo vệ; tự gọi `this.someSecuredMethod()` có thể bỏ qua interceptor. Đặt policy cốt lõi tại service/repository có gọi qua proxy đúng, kết hợp kiểm thử request/service.

### 9.8. Chỉ kiểm một ID trong batch

Với request chứa `[101, 202]`, không được suy ra toàn bộ danh sách hợp lệ chỉ vì user sở hữu `101`. Chỉ trả hoặc sửa các bản ghi được phép theo chính sách công khai; nếu hợp đồng yêu cầu **tất cả** IDs phải hợp lệ thì kiểm đủ và từ chối toàn bộ khi có ID trái phép. Chú ý transaction để tránh thành công một phần ngoài ý muốn.

## 10. Ma trận kiểm thử chống BOLA/IDOR

Khi kiểm thử ownership, ít nhất cần **hai tài khoản khác nhau**, mỗi tài khoản có một tài nguyên, cộng với một request anonymous. Các biến thể nên có:

| Phép thử | Kết quả cần bảo đảm |
|---|---|
| Alice đọc ID thuộc Alice | Thành công; dữ liệu đúng và không vượt quyền |
| Alice thay ID sang tài liệu Bob | Bị từ chối; không tiết lộ dữ liệu Bob |
| Bob thử ID thuộc Alice | Bị từ chối theo cùng policy |
| Alice thử ID không tồn tại | Kết quả không làm lộ sự tồn tại của ID bị cấm |
| Anonymous thử ID hợp lệ | Không nhận được dữ liệu |
| Alice gọi list/search/pagination | Chỉ nhận tài nguyên trong phạm vi cho phép |
| Alice thử PATCH/DELETE tài liệu Bob | Không đổi dữ liệu; trạng thái DB vẫn giữ nguyên |
| Alice thử batch với ID của cả Alice và Bob | Không thể đọc/ghi trái phép vào phần của Bob |
| Người dùng thay owner/tenant/role trong body/header | Server không tin dữ liệu tự khai để mở quyền |
| Người dùng ở tenant A thử ID tenant B | Không vượt ranh giới tenant |
| Người có quyền READ thử thao tác WRITE/DELETE | Không được cấp quyền ghi vì đã được đọc |

Khi dùng MockMvc có thể dựa trên `httpBasic` như ví dụ hoặc sử dụng `@WithMockUser`/JWT test support tùy cơ chế xác thực. Với hệ thống thật, nên có **integration test với repository/database** để chứng minh query thực hiện giới hạn dữ liệu, không chỉ mock policy trả `true/false`. Phép thử cho write phải kiểm lại database sau HTTP response, vì `403` sau một side effect đã xảy ra vẫn là lỗi nghiêm trọng.

Ví dụ JUnit trong mục 4 chứng minh: Alice và Bob đều đăng nhập hợp lệ nhưng không xem được tài liệu của nhau; endpoint list cũng không lộ bản ghi khác. Đây là tính chất mà test chỉ kiểm status `401` cho anonymous không thể phát hiện.

## 11. Checklist thiết kế trước khi đưa vào production

1. **Tài nguyên:** Endpoint nào nhận ID? Có trường ID lồng trong payload, quan hệ con, file đính kèm, export hoặc batch không?
2. **Chủ thể:** Lấy user ID, tenant ID, roles và grants từ `Authentication`/session/token đã được xác minh, không từ giá trị client tự khai.
3. **Chính sách:** Ai được READ, CREATE, UPDATE, DELETE, SHARE? Owner có thể bị đổi không, có đại diện/nhóm/quyền ủy nhiệm không?
4. **Thực thi:** Kiểm tại service và ràng buộc query/mutation theo principal, tenant và action; đừng chỉ bảo vệ controller.
5. **Phản hồi:** Xác định khi nào dùng `401`, `403`, `404`; không rò dữ liệu hoặc sự tồn tại ngoài phạm vi.
6. **Đồng thời và cache:** Xử lý check-then-act, giao dịch, version, invalidation và các cache có người dùng/tenant.
7. **Kiểm thử:** Dùng ít nhất hai principal và nhiều bản ghi; kiểm cả list, read, mutation, bulk, file access, nested-resource ID và multi-tenant.
8. **Vận hành:** Audit các truy cập bị từ chối ở mức phù hợp, cảnh báo thử nhiều ID, giảm dữ liệu nhạy cảm trong log, áp dụng rate limiting; log không thay thế cơ chế authorization.
9. **Bảo vệ dữ liệu:** DTO tránh lộ field nội bộ, phân loại dữ liệu, dùng HTTPS, ngăn lộ qua search/index/log/debug endpoint, và dùng least privilege cho tài khoản dịch vụ.

**Ghi nhớ:** object-level authorization là một quy tắc nghiệp vụ được thực thi tại backend cho **mỗi đối tượng và mỗi hành động**. Authentication cho biết “ai đang gọi”; ownership/ACL/tenant policy mới cho biết “người đó được làm gì với bản ghi này”.

## 12. Câu hỏi tự kiểm tra

1. Alice có `ROLE_USER` và đã đăng nhập. Vì sao `.hasRole("USER")` không đủ bảo vệ `/api/documents/202`?
2. Tại sao dùng UUID khó đoán vẫn không thể thay thế `WHERE owner_username = :principal`?
3. Nếu `findByIdAndOwnerUsername(202, "alice")` trả empty, vì sao trả 404 trong bài demo? Khi nào 403 hợp lý hơn?
4. Tại sao API danh sách cần lọc owner ngay trong database và không thể chỉ bảo vệ API chi tiết?
5. Với `PATCH /api/documents/202`, làm thế nào bảo đảm **kiểm owner và update** không bị tách khỏi nhau khi quyền thay đổi đồng thời?
6. Nếu một tài liệu được chia sẻ cho Bob quyền đọc nhưng không được sửa, policy nên thay đổi như thế nào cho hai action?
7. Tại sao tham số `tenantId` từ header hoặc JSON không thể tự trở thành phạm vi tin cậy?
8. Nếu Spring MVC controller kiểm tra owner nhưng một background job gọi thẳng repository theo ID, đường nào có nguy cơ bypass?
9. Trong bài demo, `@PreAuthorize("isAuthenticated()")` bảo vệ phần nào, và `findByIdAndOwnerUsername` bảo vệ phần nào?
10. Bạn sẽ viết test nào để chứng minh DELETE trả lỗi **và không làm biến mất** tài liệu của Bob?

## Tài liệu tham khảo

- [OWASP API Security Top 10 2023 — API1 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html)
- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
