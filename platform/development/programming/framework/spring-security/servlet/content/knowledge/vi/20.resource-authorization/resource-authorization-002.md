# Đối chiếu người dùng hiện tại với chủ sở hữu bản ghi trong Spring Security Servlet

> **Module:** Spring Security - servlet. **Nhóm:** Quyền tài nguyên. **Đối tượng:** Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC, Spring Data JPA, H2 và MockMvc. Trọng tâm là kiểm tra người dùng đã được xác thực có thực sự được phép đọc, sửa hoặc xóa **một bản ghi cụ thể**, thay vì chỉ kiểm tra đăng nhập hoặc vai trò chung.

## 1. Bài toán: chỉ đăng nhập chưa đủ để xem dữ liệu người khác

Alice và Bob đều là người dùng hợp lệ:

```text
Alice: userId=101
Bob:   userId=202

Tài liệu:
  document 1 -> ownerUserId=101 (Alice)
  document 2 -> ownerUserId=202 (Bob)
```

Với Spring Security, ta dễ viết HTTP rule:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").authenticated()
    .anyRequest().denyAll()
)
```

Điều kiện trên chỉ xác nhận request thuộc một người đã đăng nhập. Nếu controller lấy tài liệu trực tiếp bằng ID:

```java
@GetMapping("/api/documents/{id}")
Document get(@PathVariable Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

thì Bob chỉ cần thay `/api/documents/2` bằng `/api/documents/1` đã có thể nhận dữ liệu Alice. Đây là **Broken Object Level Authorization (BOLA)**, thường được gọi **Insecure Direct Object Reference (IDOR)**.

**Nguyên tắc:** ID trong URL chỉ định danh tài nguyên, **không chứng minh quyền sở hữu**. Mỗi request phải được đối chiếu với danh tính server đã xác minh và quyền trên **đúng bản ghi**.

```text
GET /api/documents/1
       |
       v
Spring Security xác thực actor (Bob)
       |
       v
Ứng dụng xác định trusted actorId=202
       |
       v
Tra document theo cả id=1 và ownerUserId=202
       |
       +--> Không có kết quả được phép:
       |      không trả dữ liệu của Alice
       |
       +--> Có kết quả được phép:
              chỉ trả DTO cần thiết
```

Không được thay bước đối chiếu bằng UUID khó đoán, nút Edit bị ẩn trên frontend, hay một authority chung như `ROLE_USER`.

## 2. Authentication, URL authorization và ownership là ba câu hỏi khác nhau

| Lớp | Câu hỏi | Thành phần liên quan |
| --- | --- | --- |
| Authentication | Request là ai? | `Authentication`, `SecurityContext`, authentication filter |
| HTTP authorization | Actor được vào loại URL nào? | `SecurityFilterChain`, `authorizeHttpRequests` |
| Role/authority | Actor có loại quyền thao tác này không? | `hasRole`, `hasAuthority`, `GrantedAuthority` |
| Object authorization | Actor có quyền với **record ID này** không? | Service policy, repository query, `@PreAuthorize` |
| Tenant authorization | Record có thuộc tenant actor được phép không? | Tenant membership + data predicate |
| Business rule | Có được sửa trong trạng thái hiện tại không? | Domain service, transaction |

Một principal có `ROLE_EDITOR` không có nghĩa được sửa tất cả documents trên hệ thống. Việc người dùng có `DOCUMENT_READ` cũng chưa chứng minh họ được đọc tài liệu của tenant khác.

### Ma trận quyền tối thiểu

| Request | Actor | Owner | Kết quả |
| --- | --- | --- | --- |
| GET document A | Alice | Alice | Cho phép |
| GET document B | Alice | Bob | Từ chối, không lộ nội dung |
| PATCH document A | Alice | Alice | Cho phép nếu bản ghi cho sửa |
| PATCH document B | Alice | Bob | Từ chối |
| GET document A | Anonymous | Alice | Yêu cầu đăng nhập |
| GET ID không tồn tại | Alice | Không có | 404 |
| GET danh sách documents | Alice | Nhiều owner | Chỉ liệt kê tài liệu được xem |

Trả HTTP 403 hay 404 khi document tồn tại nhưng không thuộc quyền là lựa chọn API policy. Điểm không thể thỏa hiệp là response không được trả private payload cho actor không có quyền.

## 3. Lấy người dùng hiện tại từ nguồn tin cậy

Spring Security Servlet cung cấp `Authentication` được xây từ quy trình xác thực đã cấu hình. Trong MVC controller, có thể yêu cầu inject:

```java
@GetMapping("/me")
String me(Authentication authentication) {
    return authentication.getName();
}
```

Hoặc một principal tương ứng với authentication mechanism:

```java
@GetMapping("/me")
String me(@AuthenticationPrincipal UserDetails principal) {
    return principal.getUsername();
}
```

Các snippets là fragments; import `Authentication`, `AuthenticationPrincipal` và `UserDetails` khi sử dụng. `@AuthenticationPrincipal UserDetails` chỉ phù hợp nếu principal thực sự là `UserDetails`; JWT/OIDC/SSO có thể cung cấp loại principal khác.

Trong service/background code cũng có thể lấy `Authentication` từ `SecurityContextHolder`:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

Nhưng cần xử lý context không có user, anonymous, async/background thread không tự kế thừa context và service-to-service identity. Với HTTP endpoints đã được rule `authenticated()` bảo vệ, tham số `Authentication` được inject an toàn hơn việc tự đọc nhiều lần ở business service.

### Không dùng actor ID do client khai báo

Đây là lỗi bảo mật:

```java
// SAI: cho request chọn chủ sở hữu dùng để kiểm tra.
Document document = repository.findByIdAndOwnerId(
    id, request.getParameter("ownerId"));
```

Client có thể sửa `ownerId` và mạo danh Alice. Giá trị `X-User-Id` trong một HTTP header cũng không tự đáng tin nếu gateway chưa xác thực/chuyển tiếp có ký và backend không kiểm chứng đường trust boundary. Dữ liệu được dùng làm actor phải xuất phát từ **verified authentication**, rồi ánh xạ sang ID nội bộ.

### Tên đăng nhập không phải khóa sở hữu lâu dài lý tưởng

Ví dụ runnable ở phần sau dùng `Authentication.getName()` (Alice/Bob) làm owner key cho dễ học. **Production nên dùng internal user ID ổn định** như UUID hoặc khóa DB. Username/email có thể đổi, được tái cấp hoặc không duy nhất khi nhiều IdP.

Với OIDC, nên ánh xạ **issuer + subject** sang user ID nội bộ, đồng thời kiểm tra signature, issuer, audience, expiration và tenant membership. `sub` của hai issuer khác nhau không mặc nhiên cùng một user.

## 4. Owner, creator, assignee và người được chia sẻ có thể khác nhau

Một bảng nghiệp vụ có thể gồm:

```text
document.ownerUserId       // chủ sở hữu hiện tại
document.createdByUserId   // người tạo ban đầu
document.assigneeUserId    // người được giao xử lý
document.tenantId          // tổ chức/vùng dữ liệu
document.sharedWith        // quyền được chia sẻ
```

Nếu owner đổi từ Alice sang Bob, Alice không còn là owner chỉ vì `createdByUserId` vẫn là Alice. Tương tự, một assignee được phép xử lý công việc không tự trở thành owner của tất cả file đính kèm.

Cần định nghĩa rõ:

- Owner được đọc, sửa, xóa, share, export hay chuyển ownership?
- Người được chia sẻ được xem, comment hay thay đổi nội dung?
- Admin được xem trong tenant của mình hay xuyên tenant?
- Record đã khóa/đã duyệt có cho owner sửa tiếp không?
- Khi account mất quyền, active sessions và tokens bị xử lý thế nào?

Một helper tên `isOwner` nên thực sự đối chiếu owner, không âm thầm chấp nhận `createdBy` nếu nghiệp vụ không yêu cầu.

## 5. Các mẫu triển khai và rủi ro

| Kiểu | Ưu điểm | Nhược điểm cần kiểm soát |
| --- | --- | --- |
| Controller load rồi so owner | Dễ thấy trong endpoint nhỏ | Dễ quên ở endpoint khác |
| Service policy | Tập trung logic, dùng lại giữa REST và job | Phải kiểm soát check-then-write race |
| `@PreAuthorize` với policy bean | Rule khai báo rõ trên service method | AOP proxy, query lặp, parameter naming |
| Repository query có owner predicate | Chặn dữ liệu ngoài phạm vi ngay tại DB | Phải dùng nhất quán trong mọi read/list/write |
| DB Row-Level Security | Lớp phòng thủ ở database | Cần quản lý per-request DB identity/tenant context đúng |

Không có một annotation duy nhất tự làm an toàn mọi resource endpoint. Với quyền sở hữu đơn giản, **query kèm owner predicate** là cách rất dễ kiểm thử; method security có thể bổ sung khi policy đa điều kiện.

## 6. Mẫu không an toàn: `findById` sau khi chỉ check login

```java
@GetMapping("/documents/{id}")
Document get(@PathVariable Long id) {
    return repository.findById(id)
        .orElseThrow();
}
```

Nếu SecurityFilterChain chỉ yêu cầu `authenticated()`, mọi user đã login có thể thử từng ID. Đổi ID từ số liên tiếp sang UUID chỉ làm khó việc đoán, không tạo authorization.

Một bản kiểm tra thủ công có thể được viết:

```java
Document d = repository.findById(id).orElseThrow();
if (!d.getOwnerUserId().equals(currentUserId)) {
    throw new AccessDeniedException("Forbidden");
}
return toDto(d);
```

Đây là fragment minh họa, phụ thuộc kiểu document/actor và imports. Nó tốt hơn hoàn toàn không check, nhưng vẫn **tải entity trước** rồi mới phân quyền, có nguy cơ quên check trong nhánh logic khác. Query đã giới hạn theo owner thường đơn giản hơn.

## 7. Đưa owner predicate vào câu truy vấn đọc

Một Spring Data JPA repository có thể cung cấp:

```java
Optional<OwnedDocument> findByIdAndOwnerUsername(
    Long id, String ownerUsername);
```

Lệnh này giới hạn tài liệu theo cả ID và actor trusted. Về ý nghĩa SQL:

```sql
SELECT id, owner_username, title
FROM owned_documents
WHERE id = :id
  AND owner_username = :trustedActorUsername;
```

SQL thực tế do JPA provider sinh ra có thể khác đôi chút. Nhưng ý nghĩa là **không có record khớp cả hai điều kiện thì không được trả data**.

Tương tự, list của một user dùng:

```java
List<OwnedDocument> findByOwnerUsernameOrderByIdAsc(
    String ownerUsername);
```

Không dùng `findAll()` rồi để frontend lọc hoặc ẩn dòng. Nếu server đã gửi bản ghi của Bob tới browser Alice, dù UI không hiển thị, dữ liệu đã rò rỉ.

Ở hệ thống lớn, dùng `Pageable` và index thích hợp, tránh load tất cả record vào memory rồi lọc. Nếu multi-tenant, thêm `tenantId` từ trusted tenant context.

## 8. Mutation có điều kiện để tránh kiểm tra quyền quá sớm

Một kiểm tra trước thao tác có thể trở nên cũ:

```text
t0: Alice kiểm tra document 101 có owner Alice.
t1: Transaction khác chuyển document 101 sang Bob.
t2: Alice vẫn update document 101 theo ID mà không check owner nữa.
```

Nếu quy tắc nghiệp vụ yêu cầu actor là owner **ở thời điểm ghi**, hãy đưa predicate quyền ngay vào lệnh mutation:

```java
@Modifying
@Query("""
    update OwnedDocument d
       set d.title = :title
     where d.id = :id
       and d.ownerUsername = :owner
    """)
int renameIfOwner(Long id, String owner, String title);
```

Lệnh update thành công khi record vẫn thỏa `id AND owner` trong database. Kiểm tra affected rows: nếu 0, có thể trả 404/403 theo policy. Không fallback sang `findById` rồi update bằng quyền vượt mức để "cứu" request.

**Giới hạn JPA:** `@Modifying` bulk JPQL update có thể bỏ qua entity callbacks, dirty checking và optimistic lock/version tự động. Nếu app có `@Version`, cần thiết kế version predicate/increment hoặc optimistic-lock flow thích hợp. Đây là một chiến thuật giảm TOCTOU, không phải bảo đảm tuyệt đối cho mọi transaction và distributed workflow.

## 9. Ví dụ chạy được: Spring Boot 3, Java 17, JPA và H2

Ví dụ có hai tài khoản `alice` / `bob`, mỗi người sở hữu một document. HTTP yêu cầu login, còn service/repository giới hạn từng document theo authenticated username. Bài dùng username vì đơn giản; hệ thống production nên dùng internal immutable user ID.

### 9.1. Gradle dependencies

Tạo một Spring Boot 3.x Gradle project Java 17 đã có Spring Boot plugin và dependency management, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 9.2. Cấu hình database

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:ownershipdemo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
```

H2 và `create-drop` chỉ dành cho demo/test. Không dùng `create-drop` để quản lý schema production; dùng migrations và DB credentials an toàn.

### 9.3. Source ứng dụng đầy đủ

Tạo `src/main/java/example/ownership/OwnershipApplication.java`:

```java
package example.ownership;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(OwnedDocumentRepository repository) {
        return args -> repository.saveAll(List.of(
            new OwnedDocument("alice", "Alice private note"),
            new OwnedDocument("bob", "Bob private note")
        ));
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain filter(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/api/documents", "/api/documents/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            // Browser session: CSRF protection vẫn bật.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}

@Entity
@Table(name = "owned_documents")
class OwnedDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected OwnedDocument() { }

    OwnedDocument(String ownerUsername, String title) {
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }
}

interface OwnedDocumentRepository
        extends JpaRepository<OwnedDocument, Long> {

    List<OwnedDocument> findByOwnerUsernameOrderByIdAsc(
        String ownerUsername);

    Optional<OwnedDocument> findByIdAndOwnerUsername(
        Long id, String ownerUsername);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update OwnedDocument d
           set d.title = :title
         where d.id = :id
           and d.ownerUsername = :ownerUsername
        """)
    int renameIfOwner(
        @Param("id") Long id,
        @Param("ownerUsername") String ownerUsername,
        @Param("title") String title);
}

record DocumentView(Long id, String title) {
    static DocumentView from(OwnedDocument d) {
        return new DocumentView(d.getId(), d.getTitle());
    }
}

record RenameDocumentRequest(String title) { }

@Service
class DocumentService {

    private final OwnedDocumentRepository repository;

    DocumentService(OwnedDocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<DocumentView> listMine(String actorUsername) {
        return repository.findByOwnerUsernameOrderByIdAsc(
                actorUsername)
            .stream()
            .map(DocumentView::from)
            .toList();
    }

    @Transactional(readOnly = true)
    public DocumentView readMine(
            Long id, String actorUsername) {
        return repository.findByIdAndOwnerUsername(
                id, actorUsername)
            .map(DocumentView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @Transactional
    public void renameMine(
            Long id, String actorUsername, String title) {
        int changed = repository.renameIfOwner(
            id, actorUsername, title);
        if (changed != 1) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping
    List<DocumentView> list(Authentication authentication) {
        return service.listMine(authentication.getName());
    }

    @GetMapping("/{id}")
    DocumentView read(
            @PathVariable Long id,
            Authentication authentication) {
        return service.readMine(id, authentication.getName());
    }

    @PatchMapping("/{id}")
    ResponseEntity<Void> rename(
            @PathVariable Long id,
            @RequestBody RenameDocumentRequest request,
            Authentication authentication) {

        String title = request.title();
        if (title == null || title.isBlank() ||
                title.length() > 120) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid title");
        }

        service.renameMine(
            id, authentication.getName(), title.trim());
        return ResponseEntity.noContent().build();
    }
}
```

Với Java 17, một public top-level class `OwnershipApplication` trùng tên file, còn các top-level class package-private trong cùng file là hợp lệ. Spring Boot scan package `example.ownership`, nhận config, service, JPA entity/repository và controller.

### 9.4. Cơ chế quyền ở từng đường

- `GET /api/documents` truy vấn theo `ownerUsername=authentication.getName()`, không sử dụng `findAll()`.
- `GET /api/documents/{id}` truy vấn theo **cả** ID và owner; nếu không match thì trả 404, không xác nhận bản ghi tồn tại nhưng thuộc Bob.
- `PATCH /api/documents/{id}` nhận DTO chỉ có `title`, không bind nguyên JPA entity từ body. Client không thể chọn actor.
- Phương thức `renameIfOwner` nằm trong transaction và có điều kiện owner ngay khi DB update; 0 dòng affected nghĩa là không có bản ghi được phép cập nhật.
- `DocumentView` chỉ có ID và title, hạn chế serialization field nội bộ.
- Hai tài khoản dùng encoder cho password, chỉ là credential demo local.
- `formLogin(form -> form.permitAll())` cho login page/default login processing; API protected vẫn phải xác thực.
- CSRF vẫn bật vì dùng browser session. PATCH hợp lệ phải mang CSRF token. Không nên tắt CSRF chỉ để làm bài test "xanh".

**Không dùng code này làm production template nguyên vẹn.** Production cần stable owner IDs, tenant scope, migration, rate controls, audit, data retention và tùy chọn optimistic locking. JPQL bulk update không tự áp entity callbacks/version.

### 9.5. Chạy demo

Trong project Gradle có wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell dùng `./gradlew.bat bootRun`.

Mở `http://localhost:8080/api/documents`, đăng nhập `alice` / `alice-pass`. Response JSON **dự kiến**, với ID chỉ để minh họa:

```json
[
  {
    "id": 1,
    "title": "Alice private note"
  }
]
```

ID thực tế có thể khác do `GenerationType.IDENTITY` và thứ tự dữ liệu, không được hardcode ID số 1 trong test. Alice không được thấy `Bob private note`; Bob vào từ browser profile khác chỉ thấy tài liệu của Bob.

Nếu Alice tự thay ID trên URL thành ID tài liệu Bob, câu truy vấn không tìm thấy kết quả thuộc Alice và trả 404. **Kết quả được mô tả theo code, không phải output đã chạy thực tế khi viết bài.**

## 10. MockMvc: phải có negative tests cho quyền theo bản ghi

Chỉ test "Alice đọc Alice thành công" chưa phát hiện BOLA. Cần test "Bob đọc/sửa Alice thất bại" và xác minh nội dung Alice không đổi.

Tạo `src/test/java/example/ownership/OwnershipSecurityTest.java`:

```java
package example.ownership;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OwnedDocumentRepository repository;

    @BeforeEach
    void resetDocuments() {
        repository.deleteAll();
        repository.saveAll(List.of(
            new OwnedDocument("alice", "Alice private note"),
            new OwnedDocument("bob", "Bob private note")
        ));
    }

    private Long aliceDocumentId() {
        return repository.findByOwnerUsernameOrderByIdAsc("alice")
            .get(0).getId();
    }

    private Long bobDocumentId() {
        return repository.findByOwnerUsernameOrderByIdAsc("bob")
            .get(0).getId();
    }

    @Test
    void aliceOnlyListsHerDocument() throws Exception {
        mvc.perform(get("/api/documents")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("Alice private note"));
    }

    @Test
    void aliceReadsHerOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId())
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Alice private note"));
    }

    @Test
    void aliceCannotReadBobsDocumentByChangingId()
            throws Exception {
        mvc.perform(get("/api/documents/{id}", bobDocumentId())
                .with(user("alice").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void bobCannotReadAlicesDocumentByChangingId()
            throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId())
                .with(user("bob").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void unknownIdDoesNotReturnPrivateData() throws Exception {
        mvc.perform(get("/api/documents/{id}", -1L)
                .with(user("alice").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void aliceCanRenameOnlyHerOwnDocument() throws Exception {
        Long id = aliceDocumentId();

        mvc.perform(patch("/api/documents/{id}", id)
                .with(user("alice").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Alice updated note\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/documents/{id}", id)
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Alice updated note"));
    }

    @Test
    void bobCannotRenameAlicesDocument() throws Exception {
        Long id = aliceDocumentId();

        mvc.perform(patch("/api/documents/{id}", id)
                .with(user("bob").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Hijacked\"}"))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/documents/{id}", id)
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Alice private note"));
    }

    @Test
    void missingCsrfCannotMutateOwnedDocument()
            throws Exception {
        Long id = aliceDocumentId();

        mvc.perform(patch("/api/documents/{id}", id)
                .with(user("alice").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No Csrf\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/{id}", id)
                .with(user("alice").roles("USER")))
            .andExpect(jsonPath("$.title")
                .value("Alice private note"));
    }

    @Test
    void blankTitleIsRejected() throws Exception {
        mvc.perform(patch("/api/documents/{id}", aliceDocumentId())
                .with(user("alice").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void anonymousCannotListPrivateData() throws Exception {
        mvc.perform(get("/api/documents"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void bobOnlyListsHisDocument() throws Exception {
        mvc.perform(get("/api/documents")
                .with(user("bob").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("Bob private note"));
    }
}
```

Chạy:

```bash
./gradlew test
```

**Mức độ xác minh:** test và kết quả trên là **dự kiến**, chưa được compile/chạy thực tế khi soạn bài. `SecurityMockMvcRequestPostProcessors.user` dựng principal authenticated để test authorization; nó không thực hiện login/password verification qua `UserDetailsService`. Cần các integration tests với authentication thực, proxy và DB thật trước production.

### Phân tích bài test

- Test quan trọng nhất là `bobCannotRenameAlicesDocument`: Bob có authenticated principal và có CSRF token hợp lệ, nhưng vẫn bị từ chối vì không phải owner.
- Test đọc chéo ID cho cả hai chiều giúp phát hiện việc một query bỏ qua owner.
- Test danh sách chứng minh list endpoint không gửi lẫn dữ liệu user khác.
- Test thiếu CSRF kiểm tra một cơ chế độc lập với ownership; CSRF 403 không có nghĩa owner check đã chạy.
- DB fixture reset trước mỗi test, ID được lấy từ repository nên không phụ thuộc IDENTITY counter.
- Test không dùng tên role để giả định owner: cả Alice và Bob đều `ROLE_USER` nhưng quyền trên document khác nhau.

## 11. Method security với `@PreAuthorize` và policy bean

Spring Security có thể bảo vệ service method bằng một policy bean, phù hợp khi nhiều entrypoints gọi cùng nghiệp vụ.

Ví dụ cấu hình method security (fragment bổ sung, không thay main application một cách tự động):

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Policy component minh họa:

```java
@Component("documentPolicy")
class DocumentPolicy {

    private final OwnedDocumentRepository repository;

    DocumentPolicy(OwnedDocumentRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(Long documentId,
                           Authentication authentication) {
        if (authentication == null ||
            !authentication.isAuthenticated() ||
            authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        return repository.existsByIdAndOwnerUsername(
            documentId, authentication.getName());
    }
}
```

Repository cần thêm:

```java
boolean existsByIdAndOwnerUsername(
    Long documentId, String ownerUsername);
```

Sau đó service được Spring quản lý có thể dùng:

```java
@PreAuthorize("@documentPolicy.isOwner(#documentId, authentication)")
public DocumentView readAllowed(
        @P("documentId") Long documentId) {
    return repository.findByIdAndOwnerUsername(
            documentId, currentUserName())
        .map(DocumentView::from)
        .orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND));
}
```

Đây là **fragment tùy chọn**, không phải file runnable độc lập: cần định nghĩa `repository`, `currentUserName()`, imports Spring, bean wiring, và `@P` từ `org.springframework.security.core.parameters.P`. `@P` giúp SpEL lấy đúng tên argument khi build không có Java `-parameters` metadata.

**Bẫy quan trọng:** method security theo Spring AOP proxy có thể **không chạy trên self-invocation**. Nếu một method trong service tự gọi `this.readAllowed(...)`, invocation có thể không đi qua proxy. Đưa guard ở service boundary được gọi từ bean khác và kiểm thử thực tế.

### Có nên dùng `@PostAuthorize`?

Ví dụ expression:

```java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
```

chỉ minh họa cách kiểm tra kết quả trả về nếu object có property `ownerUsername`. Nó kiểm tra **sau khi method đã chạy**; không phù hợp để bảo vệ method đã ghi dữ liệu, gửi email, xóa tệp hoặc gọi service ngoài. Với dữ liệu nhạy cảm, owner predicate tại query trước khi fetch thường giảm nguy cơ xử lý dữ liệu trái quyền.

Nếu muốn 403 thay vì 404 khi method guard deny, có thể dùng `AccessDeniedException` qua method security, nhưng response policy phải nhất quán; tránh lộ existence thông qua đường khác.

## 12. Multi-tenant: owner hợp lệ vẫn có thể sai tenant

Một truy vấn theo owner đơn thuần chưa đủ khi người dùng thuộc nhiều organizations hoặc tenants.

```sql
SELECT id, title
FROM documents
WHERE id = :documentId
  AND owner_user_id = :trustedActorId
  AND tenant_id = :trustedTenantId;
```

`trustedTenantId` không nên lấy trực tiếp từ một `X-Tenant-Id` header mà không kiểm tra membership. Nếu user được chuyển tenant qua UI, backend phải xác minh user thực sự được phép hoạt động trong tenant đó.

Thứ tự tư duy:

1. Xác minh authentication.
2. Ánh xạ actor sang internal immutable ID.
3. Xác định tenant context qua membership đã xác minh.
4. Kiểm tra permission loại thao tác (đọc/sửa/xóa).
5. Truy vấn bản ghi có ID + owner + tenant predicate.
6. Áp business state/locking nếu mutation nhạy cảm.

Một `ROLE_ADMIN` trong tenant A không tự cho phép đọc mọi tài liệu tenant B. Admin override phải được thiết kế explicit, audit và test chéo tenant.

### Database Row-Level Security

Với database có RLS, có thể thêm chính sách hạn chế row ở tầng DB. Nhưng RLS không tự biết Spring `Authentication`; ứng dụng phải gắn trusted user/tenant context vào DB connection/transaction, dọn context khi connection được tái sử dụng trong pool, và tránh dùng DB role bypass RLS. Nên coi RLS là một lớp phòng thủ, không thay toàn bộ authorization trong service.

## 13. Create, transfer, delete và batch operations

### Create document

Không chấp nhận owner do client tự khai như bằng chứng:

```java
// SAI: client tự chọn owner.
new Document(request.ownerUserId(), request.title());
```

Server phải lấy actor từ verified principal và gán owner theo business rule. Nếu tạo thay người khác là tính năng hỗ trợ, nó cần quyền cụ thể và audit.

### Delete document

Một owner-only delete có thể dùng lệnh DB với `WHERE id=:id AND owner_user_id=:actorId` và kiểm tra affected count, thay vì `deleteById(id)` trần sau khi authentication.

### Bulk delete / export

Đối với danh sách ID, cần kiểm tra **từng ID** hoặc dùng query có owner+tenant predicate và so affected rows với policy. Nếu request gồm một tài liệu Alice và một tài liệu Bob, không được vô tình xóa cả hai. Quy định rõ atomic failure hay partial success, và test.

### Transfer ownership

Chuyển owner là thao tác nhạy cảm: kiểm tra actor hiện có quyền chuyển, recipient hợp lệ trong tenant, trạng thái document, điều kiện đồng ý, audit và concurrency. Sau transfer, cache/search index/old share links có thể cần cập nhật hoặc thu hồi. Không chỉ set `ownerUserId` từ request một cách vô điều kiện.

## 14. 403, 404 và không tiết lộ tồn tại tài nguyên

| Trường hợp | Response có thể phù hợp |
| --- | --- |
| Chưa đăng nhập | 401 với API entry point hoặc 302 tới login trong form-login |
| Đã login, thiếu role/permission tổng quát | 403 |
| Document không tồn tại | 404 |
| Document tồn tại nhưng thuộc user khác | 403 **hoặc** 404 theo policy |
| Mutation thiếu CSRF | Thường 403 trước controller |
| Document bị khóa | 403/409 tùy business contract |

Ví dụ JPA chọn **404 cho cả "ID không tồn tại" và "ID thuộc người khác"**, giảm việc xác nhận sự tồn tại của tài liệu riêng tư. Nếu chọn 403, cũng cần tránh lộ title, owner, tenant và các field nhạy cảm trong response.

Không được trả HTTP 200 kèm private data rồi thêm field `canEdit=false`. Quyền xem và quyền sửa là hai điều kiện khác nhau; một actor không có quyền xem không nên nhận nội dung chỉ để UI ẩn nút sửa.

## 15. Caching, search, files và những đường vòng dễ bị bỏ sót

Các đường truy cập khác có thể làm vô hiệu một owner check đúng ở endpoint GET chính:

- **List/search:** `findAll()` và search index không lọc theo tenant/owner có thể lộ record.
- **Cache:** cache key chỉ theo document ID có thể phục vụ cached response của Alice cho Bob. Cache key và privacy policy phải xét actor/tenant.
- **CDN:** không cache public dữ liệu riêng tư dưới URL có thể bị dùng bởi user khác.
- **File attachments:** `/documents/{id}/files/{fileId}` phải kiểm tra quan hệ file→document và owner của document, không chỉ ID file.
- **Export/download:** CSV/PDF report phải dùng cùng authorization policy, không bypass vì xử lý async.
- **WebSocket/SSE:** private events phải gửi đúng user/tenant subscriptions.
- **Background job:** cần explicit service identity/delegation policy, không mặc nhiên chạy quyền admin rồi phát ra mọi dữ liệu.
- **Share links:** URL ký số có thể là capability credential nhưng phải được cấp, giới hạn scope/TTL và thu hồi theo chính sách; không phải lý do bỏ kiểm tra các API còn lại.

Một bài test chỉ cho `GET /api/documents/{id}` không chứng minh đã bảo vệ attachment thumbnail, version history hoặc audit trails.

## 16. Concurrency, quyền bị thu hồi và session cũ

Owner có thể đổi khi request đang chạy; role/tenant membership cũng có thể bị thu hồi. Cần định nghĩa:

- **Read consistency:** query DB phản ánh owner tại thời điểm phù hợp.
- **Write consistency:** update tại DB phải kiểm tra owner/tenant vẫn hợp lệ theo transaction.
- **Optimistic locking:** khi dùng `@Version`, kiểm tra version và tránh bypass qua bulk update.
- **Retry:** sau conflict không tự retry bằng quyền rộng hơn.
- **Revocation:** session hoặc JWT có thể mang role snapshot cũ; với quyền owner lưu trong DB, request phải kiểm tra trạng thái hiện hành nếu policy yêu cầu.
- **Distributed cache/index:** quyền thay đổi ở node A cần được phản ánh trên B theo SLA được xác định.
- **Request đã bắt đầu:** một thao tác đã vượt qua authorization trước revocation có thể commit sau revocation; với nghiệp vụ nhạy cảm có thể cần recheck tại commit.

Không tuyên bố "logout hoặc đổi owner sẽ hủy mọi JWT và transactions" trừ khi đã có cơ chế và integration tests chứng minh điều đó.

## 17. Checklist regression test theo resource-level authorization

| Test | Điều cần chứng minh |
| --- | --- |
| Owner đọc bản ghi của mình | Thành công, DTO đúng |
| User khác đổi ID URL | Không đọc được dữ liệu |
| User khác gọi PATCH với CSRF hợp lệ | Không sửa được |
| ID không tồn tại | Trả 404 hợp lệ |
| Anonymous request | Challenge login, không lộ nội dung |
| Client gửi ownerId giả mạo | Không đổi actor/owner nếu không có transfer permission |
| List/search/export | Chỉ data trong scope |
| File attachment của người khác | Không truy cập qua ID file |
| Role ADMIN ở tenant khác | Chỉ được truy cập nếu policy cho phép |
| Create record | Owner được gán từ trusted principal |
| Transfer owner trong lúc update | Không vượt quyền do TOCTOU |
| Token/session có role stale | Tuân thủ SLA và policy revoke |
| Caching theo document ID | Không lộ dữ liệu giữa principals |
| Bulk IDs lẫn owned/unowned | Không xóa hoặc export quá phạm vi |
| Delete/restore/version endpoints | Owner/tenant rules nhất quán |

MockMvc thích hợp để kiểm tra controller/filter/service behavior khi fixture gắn identity đúng. Cần HTTP integration tests với authentication thực, session/token, network/proxy và DB thật cho các yêu cầu vượt phạm vi mock.

## 18. Câu hỏi ôn tập có đáp án

**Câu 1.** Tại sao `authenticated()` không bảo vệ được document ID thuộc người khác?

**Đáp án:** Nó chỉ đảm bảo request đã có danh tính đăng nhập, không đối chiếu danh tính ấy với owner của record cụ thể.

**Câu 2.** Client gửi `ownerId=101`. Backend có thể coi đó là current user ID không?

**Đáp án:** Không. Actor phải lấy từ verified principal hoặc identity mapping server-side.

**Câu 3.** UUID có thay thế owner check không?

**Đáp án:** Không. UUID giảm khả năng đoán nhưng không ngăn ID bị chia sẻ/lộ và không chứng minh quyền truy cập.

**Câu 4.** `findByIdAndOwnerUsername` giúp gì so với `findById`?

**Đáp án:** Chỉ trả bản ghi khớp cả resource ID và actor; giảm rủi ro tải nhầm dữ liệu người khác và quên check.

**Câu 5.** Vì sao không nên check owner rồi cập nhật bằng `UPDATE ... WHERE id=:id` ở thời điểm khác?

**Đáp án:** Owner có thể thay đổi giữa check và update. Lệnh update có owner predicate/locking/version bảo vệ tốt hơn theo transaction policy.

**Câu 6.** Bob có CSRF token hợp lệ có sửa được document của Alice không?

**Đáp án:** Không. CSRF chỉ là một lớp bảo vệ request, không cấp object-level permission.

**Câu 7.** `@PreAuthorize` có tự chạy khi bean tự gọi method của chính nó không?

**Đáp án:** Spring AOP proxy có thể không intercept self-invocation; cần thiết kế service boundary và test.

**Câu 8.** Vì sao dùng `@PostAuthorize` cho method đã xóa file là nguy hiểm?

**Đáp án:** Authorization được kiểm tra sau khi method thực thi, khi side effect có thể đã xảy ra.

**Câu 9.** Chủ sở hữu tài liệu có email bị đổi. Điều gì cần bảo đảm?

**Đáp án:** Ownership mapping nên dựa trên internal stable user ID, không để đổi email làm mất/quyền nhầm.

**Câu 10.** User `ROLE_ADMIN` có mặc nhiên được đọc tài liệu của tenant khác không?

**Đáp án:** Không. Phải có cross-tenant policy explicit, least privilege và audit.

**Câu 11.** Khi record không thuộc actor, trả 404 được không?

**Đáp án:** Có thể, giúp giảm tiết lộ resource existence; nhưng cần nhất quán toàn bộ API.

**Câu 12.** Một search endpoint trả dữ liệu Bob rồi frontend ẩn dòng. Có an toàn không?

**Đáp án:** Không. Dữ liệu đã bị gửi cho client trái quyền.

**Câu 13.** Vì sao `ownerUserId` và `createdByUserId` không nên bị dùng lẫn?

**Đáp án:** Chúng biểu diễn quan hệ khác nhau; người tạo không nhất thiết là chủ sở hữu hiện tại.

**Câu 14.** Test MockMvc `user("alice")` đã kiểm tra mật khẩu Alice chưa?

**Đáp án:** Chưa. Đó là mock authentication phục vụ authorization test; test login phải thực hiện riêng.

## 19. Checklist nghiệm thu trước khi đưa vào sản phẩm

- [ ] Xác định identity và trusted internal user ID từ Authentication.
- [ ] Không nhận current user/owner identity từ body/query/header không đáng tin.
- [ ] Tách rõ owner, creator, assignee, shared access và tenant boundary.
- [ ] HTTP authorization và object authorization được áp cả hai.
- [ ] Read/list/search/export sử dụng owner/tenant predicate trong query.
- [ ] Update/delete có check quyền tại thời điểm mutation và xử lý affected rows.
- [ ] Không bind trực tiếp JPA entity từ dữ liệu client khi có field owner.
- [ ] DTO output chỉ chứa field actor được phép xem.
- [ ] Chức năng create gán owner từ trusted principal.
- [ ] Transfer/share/restore/version/attachment/bulk actions có policy riêng.
- [ ] `@PreAuthorize` nếu dùng được chạy qua Spring-managed proxy.
- [ ] Không dùng `@PostAuthorize` để bảo vệ method có side effects.
- [ ] CSRF vẫn được kiểm tra khi browser session có thể tự gửi credential.
- [ ] Xác định rõ 401/302, 403 và 404 trong API contract.
- [ ] Admin/support override có giới hạn tenant và được audit.
- [ ] Cache, search index, CDN và event channels không lộ data khác owner.
- [ ] Race/locking/version được kiểm thử trên DB phù hợp.
- [ ] Test cả own ID, foreign ID, missing ID, list, update và invalid CSRF.
- [ ] Kiểm thử auth thật và token/session revocation theo deployment.
- [ ] Không log raw tokens, private payload, password hoặc session secrets.

## Kết luận

**Đối chiếu người dùng hiện tại với chủ sở hữu bản ghi là authorization theo đối tượng**, không phải một bước authentication hay kiểm tra role chung. Trong Spring Security Servlet, lấy actor từ `Authentication` đã xác minh, ánh xạ sang owner ID đáng tin và đối chiếu với **dữ liệu thật**.

Với Spring Data JPA, giải pháp rõ ràng là **đọc theo ID + owner** và **ghi có điều kiện theo ID + owner**, bổ sung tenant và business rules khi cần. Test quan trọng nhất không phải "Alice đọc Alice được", mà là **"Alice không thể đọc hoặc sửa tài liệu Bob dù đã đăng nhập và có CSRF token hợp lệ"**. Đó là ranh giới bảo vệ tài nguyên trước BOLA/IDOR.
