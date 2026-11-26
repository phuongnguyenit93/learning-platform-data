# Kiểm thử một service có @PreAuthorize theo chủ sở hữu tài nguyên

Trong một API quản lý tài liệu, **đã đăng nhập** không đồng nghĩa **được đọc hoặc sửa mọi tài liệu**. Alice sở hữu `doc-a`; Bob sở hữu `doc-b`. Cả hai có thể có `ROLE_USER`, nhưng Bob phải bị từ chối khi đọc `doc-a`. Khi cập nhật, chủ sở hữu còn phải có `ROLE_EDITOR`. Lỗi không kiểm tra quan hệ giữa principal và tài nguyên thường được gọi là **Broken Object Level Authorization (BOLA)** hoặc **Insecure Direct Object Reference (IDOR)**.

Đây là bài **Thực hành tổng hợp** của module **SPRING_SECURITY_TESTING**. Chúng ta sẽ xây một ví dụ Servlet có `@PreAuthorize` trên **Spring-managed service**, rồi kiểm thử bằng JUnit, Mockito, `@WithMockUser` và `MockMvc`; sau đó chuyển ý tưởng sang ứng dụng Reactive với `WebTestClient` và `StepVerifier`. Kết quả cần chứng minh đủ các trường hợp **được phép**, **thiếu đăng nhập**, **khác chủ sở hữu**, **thiếu quyền biên tập** và **được phép biên tập**. Các fixture `mockJwt()`, OAuth2/OIDC cũng được đặt đúng phạm vi: kiểm tra authorization đã có identity, không tự chứng minh authentication protocol thật.

## 1. Đề bài và tiêu chí hoàn thành

Ứng dụng giả định có hai bản ghi:

| Document ID | Chủ sở hữu | Tiêu đề ban đầu |
| --- | --- | --- |
| `doc-a` | `alice` | `Kế hoạch A` |
| `doc-b` | `bob` | `Kế hoạch B` |

Chính sách nghiệp vụ:

1. `GET /api/documents/{id}`: chỉ người đã đăng nhập **và là owner** được đọc.
2. `PUT /api/documents/{id}`: chỉ người đã đăng nhập, có `ROLE_EDITOR` **và là owner** được đổi tiêu đề.
3. Các HTTP method và endpoint chưa được khai báo: không tự động được phép.
4. `GET /api/health`: công khai.
5. User ID của người gọi phải lấy từ `Authentication` do Spring Security thiết lập, còn chủ sở hữu phải tra từ **repository do server quản lý**. Không tin trường `owner` hoặc `X-User` do client tự gửi.

Ma trận acceptance:

| Request | Principal | Authorities | Kết quả mong đợi |
| --- | --- | --- | --- |
| GET doc-a | Alice | ROLE_USER | `200 OK` |
| GET doc-a | Bob | ROLE_USER | `403 Forbidden` |
| GET doc-a | Anonymous | Không có | `401 Unauthorized` trong cấu hình Basic mẫu |
| GET doc-b | Bob | ROLE_USER | `200 OK` |
| PUT doc-a | Alice | ROLE_USER, ROLE_EDITOR | `200 OK` |
| PUT doc-a | Alice | ROLE_USER | `403 Forbidden` |
| PUT doc-a | Bob | ROLE_EDITOR | `403 Forbidden` |
| PUT doc-b | Bob | ROLE_EDITOR | `200 OK` |

Đối với request PUT, cần gửi **CSRF token hợp lệ** vì cấu hình Servlet mẫu vẫn bật CSRF. Nếu thiếu token, `403` có thể do `CsrfFilter` chặn **trước** khi chạy `@PreAuthorize`; một test âm tính sẽ xanh sai nguyên nhân.

~~~mermaid
flowchart TD
    A["GET/PUT /api/documents/{id}"] --> B["SecurityFilterChain"]
    B --> C{"Đã xác thực?"}
    C -->|Không| U["401 với HTTP Basic"]
    C -->|Có| D["DocumentController"]
    D --> E["Spring proxy của DocumentService"]
    E --> F{"@PreAuthorize"}
    F --> G["DocumentPolicy"]
    G --> H["Repository tìm chủ sở hữu theo ID"]
    H --> I{"ownerId trùng Authentication.getName()?"}
    I -->|Không| X["AccessDeniedException -> HTTP 403"]
    I -->|Có| R{"PUT có ROLE_EDITOR?"}
    R -->|Không| X
    R -->|Có hoặc GET| J["Service thực thi, trả dữ liệu"]
~~~

Hình minh họa logic quyền; filter còn xử lý CSRF, exception translation và authentication entry point theo cấu hình. Đối với PUT có CSRF bật, request phải vượt qua CSRF trước khi gọi controller.

## 2. Chọn ranh giới bảo mật: URL không thay thế service

Một `SecurityFilterChain` có thể yêu cầu `authenticated()` với tất cả `/api/documents/**`. Quy tắc đó chỉ trả lời **ai được vào khu vực API**; nó không biết `doc-a` thuộc Alice hay Bob nếu không tra dữ liệu. `@PreAuthorize` trên service có lợi khi cùng service được gọi từ HTTP controller, một service khác hoặc tác vụ nội bộ.

| Lớp bảo vệ | Ví dụ | Điều được chứng minh khi test |
| --- | --- | --- |
| Servlet HTTP filter | `requestMatchers("/api/documents/**").authenticated()` | Request ẩn danh không đi vào service |
| Method security | `@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")` | Lời gọi Spring bean bị chặn theo policy |
| Domain policy | So sánh owner tra từ repository và principal | Bob không thể đọc doc-a dù đã đăng nhập |
| Data write | Update có điều kiện owner/version | Không ghi sai bản ghi khi ownership thay đổi đồng thời |

Không nên chỉ bảo vệ tại controller rồi cho rằng service sẽ luôn được gọi từ controller đó. Ngược lại, không nên bỏ test HTTP chỉ vì service có `@PreAuthorize`: một route công khai, chain sai thứ tự hoặc CSRF cấu hình không đúng vẫn tạo rủi ro.

Trong Spring Security Servlet, `@EnableMethodSecurity` kích hoạt các method interceptor hiện đại. Đối với ứng dụng WebFlux, cấu hình tương ứng là `@EnableReactiveMethodSecurity` và biểu thức policy có thể dựa vào Reactor SecurityContext; **không dùng cùng cách đọc ThreadLocal trong Reactive pipeline**.

## 3. Mô hình dữ liệu và repository: owner thuộc về server

Để tập trung vào security, ví dụ dùng một domain record và repository interface; test có thể override repository bằng Mockito:

~~~java
package example.documents;

import java.util.Optional;

public record Document(
        String id,
        String ownerId,
        String title) {}

public interface DocumentRepository {
    Optional<Document> findById(String documentId);
    Document save(Document document);
}
~~~

Ví dụ tài liệu:

~~~java
Document aliceDoc =
    new Document("doc-a", "alice", "Kế hoạch A");
Document bobDoc =
    new Document("doc-b", "bob", "Kế hoạch B");
~~~

Trong ứng dụng thật, `DocumentRepository` có thể được hiện thực bằng Spring Data JPA/JDBC, MongoDB hoặc repository khác. **Không dùng các object trong HTTP body làm nguồn quyết định owner**. Client chỉ cung cấp ID để định vị, còn `ownerId` phải đến từ dữ liệu đã được kiểm soát bởi server.

Để giữ tài liệu mẫu tự chứa, chưa dùng database thật trong các test nhanh. Một integration test về policy cuối cùng vẫn cần chứng minh query thực trả đúng owner, filter tenant và isolation của dữ liệu đã lưu.

## 4. DocumentPolicy: phối hợp owner và authority

Tạo một Spring component chuyên quyết định quyền. Để tránh lỗi phân quyền, code phải từ chối khi authentication rỗng, là anonymous token, ID không hợp lệ hoặc repository không tìm thấy bản ghi:

~~~java
package example.documents;

import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication auth, String documentId) {
        return isOwner(auth, documentId);
    }

    public boolean canRename(Authentication auth, String documentId) {
        return hasAuthority(auth, "ROLE_EDITOR")
            && isOwner(auth, documentId);
    }

    private boolean isOwner(Authentication auth, String documentId) {
        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || documentId == null
                || documentId.isBlank()) {
            return false;
        }

        return repository.findById(documentId)
            .map(document -> document.ownerId().equals(auth.getName()))
            .orElse(false);
    }

    private boolean hasAuthority(Authentication auth, String required) {
        if (auth == null) {
            return false;
        }
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(required::equals);
    }
}
~~~

Một số điểm kỹ thuật:

- `Authentication.getName()` là tên principal sau xác thực. Ở ví dụ nó trùng `ownerId` trong database. Trong production, nên ưu tiên **user ID ổn định, không thể giả mạo và đã được ánh xạ**, thay vì display name/email có thể thay đổi.
- `AnonymousAuthenticationToken` có thể báo `isAuthenticated() == true`, nên không chỉ kiểm tra một mình cờ `isAuthenticated()` nếu tự viết policy.
- `findById(...).orElse(false)` từ chối tài liệu không tìm thấy. Với API yêu cầu che giấu sự tồn tại của tài nguyên, `403` khi sai owner/không tồn tại có thể là lựa chọn. Nếu sản phẩm muốn trả `404`, cần thiết kế đường kiểm tra/exception nhất quán; không tự suy rằng mọi ứng dụng phải dùng một mã.
- `canRename` kiểm tra authority **trước** khi tra repository. Alice chỉ có USER sẽ bị từ chối ngay cả khi sở hữu tài liệu. Điều đó không làm mất yêu cầu ownership: người có ROLE_EDITOR nhưng sai owner vẫn bị từ chối sau lookup.
- Spring Security `hasRole("EDITOR")` mặc định kiểm tra `ROLE_EDITOR`; `hasAuthority("ROLE_EDITOR")` kiểm tra đúng chuỗi. Một JWT có `scope=documents.write` thường được ánh xạ thành `SCOPE_documents.write`, **không tự biến thành `ROLE_EDITOR`**.

Với các policy đòi tra tenant hoặc tổ chức, nên kiểm tra đồng thời immutable principal ID và tenant ID từ nguồn đáng tin. Một user có role ADMIN trong tenant B không mặc nhiên được sửa tài liệu tenant A.

## 5. DocumentService và @PreAuthorize

Đặt annotation ngay tại **phương thức nghiệp vụ**. Sử dụng `#p0` (tham số thứ nhất) trong SpEL để không phụ thuộc vào việc mã được biên dịch có lưu metadata tên tham số hay không:

~~~java
package example.documents;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public Document read(String id) {
        return repository.findById(id).orElseThrow(() ->
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));
    }

    @PreAuthorize("@documentPolicy.canRename(authentication, #p0)")
    public Document rename(String id, String newTitle) {
        Document current = repository.findById(id).orElseThrow(() ->
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));

        Document modified = new Document(
            current.id(), current.ownerId(), newTitle);
        return repository.save(modified);
    }
}
~~~

`@PreAuthorize` không được thực thi bởi Java compiler. Nó được áp dụng qua **method security interceptor/proxy của Spring**. Vì vậy:

1. Cần bật `@EnableMethodSecurity`.
2. Test phải inject **Spring-managed `DocumentService` bean** thay vì `new DocumentService(...)` nếu muốn kiểm tra annotation.
3. Self-invocation như `this.rename(...)` từ một phương thức trong cùng class có thể **không đi qua proxy**; hãy tổ chức các service boundary phù hợp.
4. Một test trực tiếp gọi `DocumentPolicy.canRead(...)` kiểm tra logic quyền, **nhưng chưa chứng minh annotation trên service có hoạt động**.

Trước khi `read` hoặc `rename` chạy, Spring Security sẽ đánh giá expression. Nếu policy trả `false`, một `AccessDeniedException` được phát ra; trong luồng HTTP Servlet có SecurityFilterChain, framework thường chuyển thành `403 Forbidden` cho user đã xác thực.

**Lưu ý race condition:** `canRename` tra owner, sau đó `rename` lại đọc tài liệu và lưu. Nếu owner bị thay đổi giữa hai thời điểm (time-of-check/time-of-use), đoạn mã mẫu chưa ngăn thao tác ghi sai. Với dữ liệu nhạy cảm, dùng transaction phù hợp và/hoặc câu lệnh `UPDATE ... WHERE id = ? AND owner_id = ?`, optimistic locking, tenant constraint. Test đơn vị không chứng minh tính nguyên tử của database.

## 6. Cấu hình ứng dụng Servlet có method security

Ví dụ dưới đây dùng Spring Boot Servlet, HTTP Basic và user store in-memory để tập trung vào phân quyền. Mật khẩu `{noop}secret` **chỉ dành cho demo và test**; hệ thống thật cần password encoder, IdP hoặc user store thực tế.

~~~java
package example.documents;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableMethodSecurity
public class DocumentSecurityApplication {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/health").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}secret")
                .roles("USER", "EDITOR")
                .build(),
            User.withUsername("bob")
                .password("{noop}secret")
                .roles("USER")
                .build());
    }
}
~~~

Controller chỉ định tuyến và gọi service:

~~~java
package example.documents;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record RenameRequest(String title) {}

@RestController
@RequestMapping("/api")
public class DocumentController {
    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/documents/{id}")
    Document read(@PathVariable String id) {
        return documents.read(id);
    }

    @PutMapping("/documents/{id}")
    Document rename(
            @PathVariable String id,
            @RequestBody RenameRequest body) {
        return documents.rename(id, body.title());
    }
}
~~~

Ở đây controller không lặp lại owner policy. Bộ lọc HTTP chặn request anonymous, `DocumentService` bảo vệ domain access, và repository cung cấp owner đáng tin. Với ứng dụng production, còn cần validation `title`, error representation và giới hạn độ dài/path ID.

### Dependency ví dụ

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Ví dụ test sử dụng `@MockitoBean`, API Spring Framework Test **6.2+** (và Spring Boot tương ứng, ví dụ Boot 3.4+). Nếu dự án ở Spring Boot cũ hơn, có thể dùng `@MockBean` theo phiên bản đang chạy; không trộn hai cơ chế chỉ để làm code test biên dịch.

Trong ứng dụng Java thật, đặt các public type vào những file riêng như `Document.java`, `DocumentRepository.java`, `DocumentPolicy.java`, `DocumentService.java`, `DocumentController.java` và `DocumentSecurityApplication.java`; các snippet được ghép theo thứ tự để học, không phải một file Java chứa nhiều public class. Cấu trúc test ví dụ:

~~~text
src/main/java/example/documents/
  Document.java
  DocumentRepository.java
  DocumentPolicy.java
  DocumentService.java
  DocumentController.java
  DocumentSecurityApplication.java

src/test/java/example/documents/
  DocumentPolicyUnitTest.java
  DocumentMethodSecurityTest.java
  DocumentHttpAuthorizationTest.java
~~~

## 7. Bước thứ nhất: unit test thuần cho DocumentPolicy

Khi muốn kiểm tra riêng quy tắc owner, **không cần khởi động cả Spring context**. Tạo một `DocumentPolicy` bình thường và mock repository bằng Mockito. Test này kiểm tra thuật toán quyền, **chưa chứng minh @PreAuthorize được Spring thực thi**.

~~~java
package example.documents;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class DocumentPolicyUnitTest {
    @Mock
    DocumentRepository repository;

    DocumentPolicy policy;

    @BeforeEach
    void init() {
        policy = new DocumentPolicy(repository);
    }

    private Authentication auth(String name, String... authorities) {
        var granted = java.util.Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();
        return UsernamePasswordAuthenticationToken.authenticated(
            name, "N/A", granted);
    }

    @Test
    void ownerMayReadTheirDocument() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(
                new Document("doc-a", "alice", "Kế hoạch A")));

        assertThat(policy.canRead(
            auth("alice", "ROLE_USER"), "doc-a")).isTrue();
    }

    @Test
    void anotherUserCannotReadTheDocument() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(
                new Document("doc-a", "alice", "Kế hoạch A")));

        assertThat(policy.canRead(
            auth("bob", "ROLE_USER"), "doc-a")).isFalse();
    }

    @Test
    void missingDocumentNeverGrantsAccess() {
        when(repository.findById("unknown"))
            .thenReturn(Optional.empty());

        assertThat(policy.canRead(
            auth("alice", "ROLE_USER"), "unknown")).isFalse();
    }

    @Test
    void nullAuthenticationIsNotAnOwner() {
        assertThat(policy.canRead(null, "doc-a")).isFalse();
        verifyNoInteractions(repository);
    }

    @Test
    void ownerWithoutEditorRoleCannotRename() {
        assertThat(policy.canRename(
            auth("alice", "ROLE_USER"), "doc-a")).isFalse();
        verifyNoInteractions(repository);
    }

    @Test
    void editorMustAlsoBeTheOwner() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(
                new Document("doc-a", "alice", "Kế hoạch A")));

        assertThat(policy.canRename(
            auth("bob", "ROLE_EDITOR"), "doc-a")).isFalse();
    }

    @Test
    void editorWhoOwnsDocumentCanRename() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(
                new Document("doc-a", "alice", "Kế hoạch A")));

        assertThat(policy.canRename(
            auth("alice", "ROLE_EDITOR"), "doc-a")).isTrue();
    }
}
~~~

Chú ý `auth(...)` tạo `Authentication` **mới theo mỗi lần gọi**, không dùng một principal mutable static cho mọi test. `verifyNoInteractions(repository)` trong ca thiếu role chứng minh policy có short-circuit trước khi tra dữ liệu. Unit test này chạy nhanh và báo nguyên nhân sai quyền rõ ràng, nhưng nếu xóa annotation `@PreAuthorize` khỏi `DocumentService`, toàn bộ unit test trên vẫn có thể xanh.

## 8. Bước thứ hai: kiểm thử interceptor trên Spring-managed service

Đây là **bài kiểm tra trọng tâm**. Ta inject `DocumentService` từ Spring và gọi trực tiếp method có `@PreAuthorize`. `@WithMockUser` của Spring Security Test cung cấp `SecurityContext` cho từng test; `@MockitoBean` thay `DocumentRepository` bằng stub có dữ liệu chủ sở hữu độc lập.

~~~java
package example.documents;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SpringBootTest(classes = DocumentSecurityApplication.class)
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService documents; // Spring bean, không phải new.

    @MockitoBean
    DocumentRepository repository;

    private final Document aliceDoc =
        new Document("doc-a", "alice", "Kế hoạch A");

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadThroughSecuredService() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        assertThat(documents.read("doc-a")).isEqualTo(aliceDoc);
        // Lần 1: policy, lần 2: service lấy dữ liệu để trả.
        verify(repository, times(2)).findById("doc-a");
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void otherUserIsDeniedBeforeServiceBodyRuns() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        assertThatThrownBy(() -> documents.read("doc-a"))
            .isInstanceOf(AccessDeniedException.class);

        // Policy đọc owner; thân service KHÔNG được chạy.
        verify(repository, times(1)).findById("doc-a");
        verify(repository, never()).save(any(Document.class));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerWithoutEditorRoleCannotRename() {
        assertThatThrownBy(() ->
            documents.rename("doc-a", "Tiêu đề mới"))
            .isInstanceOf(AccessDeniedException.class);

        verifyNoInteractions(repository);
    }

    @Test
    @WithMockUser(username = "bob", roles = "EDITOR")
    void editorWhoIsNotOwnerCannotRename() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        assertThatThrownBy(() ->
            documents.rename("doc-a", "Tiêu đề trái phép"))
            .isInstanceOf(AccessDeniedException.class);

        verify(repository, times(1)).findById("doc-a");
        verify(repository, never()).save(any(Document.class));
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER", "EDITOR"})
    void ownerWithEditorRoleCanRename() {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));
        when(repository.save(any(Document.class)))
            .thenAnswer(call -> call.getArgument(0));

        Document result = documents.rename("doc-a", "Đã duyệt");

        assertThat(result.ownerId()).isEqualTo("alice");
        assertThat(result.title()).isEqualTo("Đã duyệt");
        verify(repository).save(argThat(doc ->
            doc.id().equals("doc-a")
                && doc.ownerId().equals("alice")
                && doc.title().equals("Đã duyệt")));
    }
}
~~~

### Vì sao đây là test của @PreAuthorize chứ không chỉ của DocumentPolicy?

Khi `documents.read("doc-a")` được gọi, đối tượng `documents` là **bean có interceptor của Spring Method Security**, nên biểu thức `@documentPolicy.canRead(authentication, #p0)` được đánh giá trước khi thân phương thức chạy. Với Bob, `AccessDeniedException` xuất hiện dù `DocumentService.read(...)` tự nó không hề có câu lệnh `if(owner != currentUser)`.

Nếu vô tình:

~~~java
DocumentService raw = new DocumentService(repository);
raw.read("doc-a"); // Bỏ qua proxy: KHÔNG test được @PreAuthorize.
~~~

thì lời gọi không đi qua method-security interceptor. Dù vậy, body `read` có thể chạy và truy vấn repository. Đây là một anti-pattern trong bài kiểm tra annotation: tạo instance thủ công khiến test không chứng minh chính sách trên method được áp dụng.

Một điểm quan trọng khác là `@WithMockUser` **không kiểm tra mật khẩu**; nó tạo `Authentication` trực tiếp trong test. Với mục tiêu method-level authorization, đó là cách cô lập phù hợp. Muốn kiểm tra HTTP authentication, thêm test request Basic/Bearer thật ở mục kế tiếp.

### Không có tài liệu hoặc repository lỗi

Trong policy mẫu, tài liệu không tồn tại khiến `canRead(...)` trả `false`, dẫn tới `AccessDeniedException`. Đó là một lựa chọn **fail-closed**, nhưng có thể khác contract của API muốn phân biệt `404` với `403`. Khi repository ném exception, policy không trả `true`: phương thức bị ngắt bởi lỗi truy vấn; HTTP status lúc đó phụ thuộc error handling của ứng dụng, không mặc định `403`.

Các test bổ sung nên xác minh:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void unknownIdIsNotAccessible() {
    when(repository.findById("does-not-exist"))
        .thenReturn(Optional.empty());

    assertThatThrownBy(() -> documents.read("does-not-exist"))
        .isInstanceOf(AccessDeniedException.class);
}
~~~

Đặt phương thức trên trong `DocumentMethodSecurityTest`. Đừng tự thay kết quả `403` thành `404` trong test khi chưa xác định chính sách tiết lộ sự tồn tại của tài nguyên.

## 9. Bước thứ ba: MockMvc kiểm tra đường HTTP thực tế

Một service có method security đúng vẫn chưa chứng minh request HTTP ẩn danh được chặn, CSRF hoạt động hoặc lỗi bảo mật được ánh xạ thành status chuẩn. Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để nạp controller, `SecurityFilterChain`, method interceptor và Spring Security Test.

~~~java
package example.documents;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SpringBootTest(classes = DocumentSecurityApplication.class)
@AutoConfigureMockMvc
class DocumentHttpAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    DocumentRepository repository;

    private final Document aliceDoc =
        new Document("doc-a", "alice", "Kế hoạch A");

    @Test
    void anonymousRequestIsRejectedByHttpFilter() throws Exception {
        mvc.perform(get("/api/documents/doc-a"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(repository);
    }

    @Test
    void ownerCanReadViaHttp() throws Exception {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        mvc.perform(get("/api/documents/doc-a")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("doc-a"))
            .andExpect(jsonPath("$.ownerId").value("alice"));
    }

    @Test
    void otherUserCannotReadViaHttp() throws Exception {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        mvc.perform(get("/api/documents/doc-a")
                .with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerWithEditorRoleCanRenameViaHttp() throws Exception {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));
        when(repository.save(any(Document.class)))
            .thenAnswer(call -> call.getArgument(0));

        mvc.perform(put("/api/documents/doc-a")
                .with(user("alice").roles("USER", "EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Mới\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Mới"));

        verify(repository).save(any(Document.class));
    }

    @Test
    void ownerWithoutEditorRoleCannotRenameViaHttp()
            throws Exception {
        mvc.perform(put("/api/documents/doc-a")
                .with(user("alice").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Không được sửa\"}"))
            .andExpect(status().isForbidden());

        verify(repository, never()).save(any(Document.class));
    }

    @Test
    void editorCannotRenameAnotherUsersDocument()
            throws Exception {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        mvc.perform(put("/api/documents/doc-a")
                .with(user("bob").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Sửa trái phép\"}"))
            .andExpect(status().isForbidden());

        verify(repository, never()).save(any(Document.class));
    }

    @Test
    void missingCsrfPreventsWriteEvenForOwner() throws Exception {
        mvc.perform(put("/api/documents/doc-a")
                .with(user("alice").roles("USER", "EDITOR"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Mới\"}"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(repository);
    }

    @Test
    void realBasicCredentialsStillRequireOwnership()
            throws Exception {
        when(repository.findById("doc-a"))
            .thenReturn(Optional.of(aliceDoc));

        mvc.perform(get("/api/documents/doc-a")
                .with(httpBasic("bob", "secret")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/doc-a")
                .with(httpBasic("alice", "secret")))
            .andExpect(status().isOk());
    }

    @Test
    void incorrectBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/documents/doc-a")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Test `httpBasic(...)` gửi **credentials tới filter xác thực** và dùng `UserDetailsService` demo; `user(...)` đặt authentication giả trong request và không kiểm tra mật khẩu. Hai nhóm test giải quyết các câu hỏi khác nhau. Với form login, một user chưa xác thực có thể nhận `302` redirect thay vì `401`, tùy authentication entry point. Không ép status từ cấu hình Basic mẫu lên mọi ứng dụng.

`@AutoConfigureMockMvc` của Spring Boot mặc định áp dụng filters của context. Tránh `@AutoConfigureMockMvc(addFilters = false)` khi muốn chứng minh `SecurityFilterChain` hoạt động; cấu hình đó có thể làm request ẩn danh đi thẳng tới controller. Nếu tự dựng `MockMvcBuilders`, dùng `springSecurity()` với web application context phù hợp.

## 10. Đọc đúng ý nghĩa 401, 403 và 404

| Kết quả | Nguyên nhân trong mẫu | Không được kết luận vội |
| --- | --- | --- |
| `200 OK` | Đã vượt qua filter, method policy, service xử lý thành công | Không chứng minh JWT/SAML/OIDC protocol thật |
| `401 Unauthorized` | Anonymous request hoặc Basic credentials sai | Không có nghĩa chủ sở hữu sai; policy service có thể chưa chạy |
| `403 Forbidden` | User đã xác thực sai owner, thiếu EDITOR, hoặc thiếu CSRF trên PUT | Không đủ xác định nguyên nhân nếu thiếu test đối chứng |
| `404 Not Found` | Nếu ứng dụng chủ động trả 404 cho ID không có hoặc che sự tồn tại | Không phải lựa chọn bắt buộc của `@PreAuthorize` |
| `5xx` | Lỗi repository hoặc bug chưa được map | Không được biến exception thành “cho phép truy cập” |

Một test mạnh không chỉ assert `403` mà còn xác minh **thân method không thực thi**: trong bài, `verify(repository, never()).save(...)` chứng minh thao tác ghi chưa xảy ra khi người gọi thiếu quyền. Với DELETE/UPDATE ở hệ thống thật, kiểm tra cả trạng thái database sau request vì đôi khi code đã ghi rồi mới ném lỗi.

## 11. Bước thứ tư: test thật với database và dữ liệu độc lập

Khi `DocumentRepository` được mock, unit test chỉ chứng minh policy xử lý **đầu ra được stub**. Nó chưa chứng minh query thực lấy đúng owner, điều kiện tenant không bị bỏ sót, hay thao tác UPDATE thực sự không sửa dữ liệu trái quyền.

Một suite tích hợp nên sử dụng database dành riêng cho test, ví dụ Testcontainers với PostgreSQL:

~~~text
test setup:
  INSERT (doc-a, owner=alice)
  INSERT (doc-b, owner=bob)

case A:
  login as alice
  GET doc-a -> 200

case B:
  login as bob
  GET doc-a -> 403

case C:
  login as bob + EDITOR
  PUT doc-a -> 403
  SELECT doc-a -> title không đổi

case D:
  login as alice + EDITOR
  PUT doc-a -> 200
  SELECT doc-a -> title mới
~~~

Để dữ liệu ổn định khi chạy song song, không cho nhiều test cập nhật chung `doc-a` nếu không có cơ chế khóa/namespace/reset. Có thể tạo ID riêng cho mỗi test, transaction/cleanup phù hợp, hoặc reset schema bằng công cụ chuyên dụng. Một `@Transactional` trên test method **không chắc rollback** các thay đổi từ HTTP request thực chạy ở transaction khác.

### Kiểm thử tính nguyên tử của update

Policy ở mục 4 kiểm tra owner trước khi service làm việc. Nếu quyền sở hữu có thể thay đổi đồng thời, một cách bảo vệ thêm ở tầng dữ liệu là:

~~~sql
UPDATE documents
SET title = :newTitle
WHERE id = :documentId
  AND owner_id = :currentPrincipalId;
~~~

Sau đó assert **số dòng cập nhật bằng 1** với owner hợp lệ, **bằng 0** nếu owner không khớp. Nếu nghiệp vụ có tenant, thêm điều kiện tenant và có thể optimistic version. Đây là phần bảo vệ dữ liệu ở thời điểm commit, bổ sung cho `@PreAuthorize`, không thay thế permission tests ở service.

## 12. Custom principal: ownerId không nhất thiết bằng username

Trong ví dụ, `Authentication.getName()` trả `alice`/`bob`, giống `Document.ownerId()`. Một ứng dụng sản xuất thường lưu **internal user ID** ổn định (ví dụ `user-173`) thay vì email/display name. Nếu dùng OAuth2/OIDC/SAML, subject từ IdP cũng có thể cần được ánh xạ với user ID nội bộ.

Một principal riêng cho domain:

~~~java
import org.springframework.security.core.AuthenticatedPrincipal;

public record AccountPrincipal(
        String id,
        String displayName,
        String tenantId) implements AuthenticatedPrincipal {

    @Override
    public String getName() {
        return id;
    }
}
~~~

Khi đó `Authentication.getName()` có thể đại diện cho `id` nội bộ nếu Authentication thực sự sử dụng `AccountPrincipal` làm principal và triển khai `getName()` theo hợp đồng tương ứng. **Không mặc định mọi authentication provider đều dùng quy tắc trên**: kiểm tra adapter/converter của dự án và viết test xác minh trường nào dùng làm owner key.

Với `@WithMockUser(username="alice")`, principal mặc định không phải `AccountPrincipal`. Nếu policy yêu cầu thêm `tenantId`, test phải tạo authentication/principal phù hợp, chẳng hạn `@WithSecurityContext` tùy biến:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithAccountFactory.class)
public @interface WithAccount {
    String id();
    String tenant();
    String[] roles() default {"USER"};
}

public final class WithAccountFactory
        implements WithSecurityContextFactory<WithAccount> {

    @Override
    public SecurityContext createSecurityContext(WithAccount data) {
        AccountPrincipal principal = new AccountPrincipal(
            data.id(), data.id(), data.tenant());

        var authorities = java.util.Arrays.stream(data.roles())
            .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
            .toList();

        Authentication authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                principal, "N/A", authorities);

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Các import cần dùng: `java.lang.annotation.*`, `WithSecurityContext`, `WithSecurityContextFactory`, `SecurityContext`, `SecurityContextHolder`, `Authentication`, `UsernamePasswordAuthenticationToken` và `SimpleGrantedAuthority`. Trong Java, đặt các public annotation/class thành file riêng. Factory **phải tạo SecurityContext mới**, không dùng một static shared context rồi sửa Authentication khi test chạy song song.

Test với principal nội bộ có thể viết:

~~~java
@Test
@WithAccount(id = "user-173", tenant = "tenant-a",
             roles = {"USER"})
void methodReceivesStableInternalPrincipalId() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    assertThat(auth.getName()).isEqualTo("user-173");
    assertThat(auth.getPrincipal())
        .isInstanceOf(AccountPrincipal.class);
}
~~~

Đây mới là bài test về **identity mapping fixture**. Để kiểm tra owner thực sự, phải tạo document có `ownerId = "user-173"`, stub repository và gọi `DocumentService.read(...)` qua Spring proxy. Một test chỉ assert tên user không chứng minh quyền truy cập tài nguyên.

## 13. JWT Resource Server: giả lập authorization đúng cách

Nếu API dùng Bearer JWT thay HTTP Basic, security filter có thể xác thực bằng `JwtDecoder` rồi tạo `JwtAuthenticationToken`. Với một test **chỉ quan tâm owner + scope/role**, Spring Security Test hỗ trợ `jwt()` cho Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

@Test
void jwtSubjectMatchingOwnerCanRead() throws Exception {
    when(repository.findById("doc-a"))
        .thenReturn(Optional.of(
            new Document("doc-a", "alice", "Kế hoạch A")));

    mvc.perform(get("/api/documents/doc-a")
            .with(jwt().jwt(token -> token.subject("alice"))
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_documents.read"))))
        .andExpect(status().isOk());
}
~~~

Đoạn này dùng `Authentication.getName()` từ `JwtAuthenticationToken` để khớp owner Alice. Nó **không** gửi một bearer string đã ký tới decoder, nên test không xác minh chữ ký JWT, issuer, audience hoặc expiration. Và nó chỉ đúng khi API policy cho phép `JwtAuthenticationToken` hoặc mapping sang domain principal tương đương.

Trong ví dụ service mục 4, `canRead` chỉ yêu cầu owner; scope `SCOPE_documents.read` được đưa vào fixture để minh họa identity thực tế, **chưa phải điều kiện bắt buộc của chính sách mẫu**. Nếu nghiệp vụ yêu cầu scope, phải **thêm kiểm tra scope trong policy hoặc HTTP chain** và viết cả test thiếu scope. Tránh viết một test có scope rồi tuyên bố scope đã được kiểm chứng nếu code chưa kiểm tra.

Đối với rename, policy mẫu cần `ROLE_EDITOR`. Một token có `scope=documents.write` theo converter mặc định thường có `SCOPE_documents.write`, **không tự trở thành `ROLE_EDITOR`**. Nếu muốn cho phép JWT scope này thực hiện PUT, cần sửa policy/authority converter có chủ đích và test cả hai nhánh.

Khi mục tiêu là xác minh authentication thực tế:

1. Cấu hình JWT Resource Server với issuer/JWK/test signing key riêng.
2. Gửi `Authorization: Bearer ...` thực qua `MockMvc` hoặc HTTP client.
3. Assert JWT sai chữ ký/hết hạn/sai issuer bị `401`.
4. Assert JWT hợp lệ của Bob vẫn bị `403` khi truy cập tài liệu Alice.
5. Assert JWT hợp lệ của Alice đủ quyền được `200`.

Đó là lớp integration test khác với `jwt()` giả lập. Không mock `JwtDecoder` rồi kết luận validation chữ ký đã đạt.

### OAuth2/OIDC/SAML Login hậu đăng nhập

Với OAuth2 Login/OIDC Login, `oauth2Login()` hoặc `oidcLogin()` của Spring Security Test có thể dựng authentication hậu callback để kiểm tra downstream authorization. Đối với SAML2 Servlet, có thể truyền một `Saml2Authentication` phù hợp qua `authentication(...)` khi ứng dụng yêu cầu principal SAML.

Những fixture này giúp kiểm tra owner/role **sau khi đăng nhập**, nhưng không chạy redirect, authorization code/PKCE, ID token validation, SAML assertion verification hoặc session persistence thật. Khi subject bên ngoài khác internal user ID, cần test **cơ chế ánh xạ identity** riêng; một fixture ghi tên Alice trực tiếp có thể bỏ qua lỗi mapping trong production.

## 14. Ứng dụng Reactive: phương thức trả Mono và policy bất đồng bộ

Với WebFlux, SecurityContext đi qua **Reactor Context**, không đọc bằng ThreadLocal thông thường. Nếu repository dùng R2DBC hoặc Reactive Mongo, quyền sở hữu nên được kiểm tra bất đồng bộ, tránh gọi `.block()` trong event loop.

Ví dụ song song của bài toán Servlet, nhưng dành cho **một ứng dụng WebFlux riêng**, không đặt đồng thời với `DocumentSecurityApplication` Servlet trong cùng test context:

~~~java
public interface ReactiveDocumentRepository {
    Mono<Document> findById(String id);
}

@Component("reactiveDocumentPolicy")
public class ReactiveDocumentPolicy {
    private final ReactiveDocumentRepository repository;

    public ReactiveDocumentPolicy(ReactiveDocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(Authentication auth, String id) {
        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || id == null || id.isBlank()) {
            return Mono.just(false);
        }

        return repository.findById(id)
            .map(doc -> doc.ownerId().equals(auth.getName()))
            .defaultIfEmpty(false);
    }
}

@Service
public class ReactiveDocumentService {
    private final ReactiveDocumentRepository repository;

    public ReactiveDocumentService(ReactiveDocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@reactiveDocumentPolicy.canRead(authentication, #p0)")
    public Mono<Document> read(String id) {
        return repository.findById(id);
    }
}
~~~

Đây là các kiểu Java đặt ở **những file riêng**; các import gồm `Mono`, `Authentication`, `AnonymousAuthenticationToken`, `@Component`, `@Service` và `@PreAuthorize`. Với Spring Security Reactive hiện đại, method-security expression có thể trả `Mono<Boolean>` và được đánh giá khi reactive chain được subscribe. Cần bật `@EnableReactiveMethodSecurity` trong cấu hình của ứng dụng WebFlux.

Ví dụ security chain:

~~~java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class ReactiveDocumentSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/documents/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }
}
~~~

Khác với Servlet `@EnableMethodSecurity`, WebFlux dùng `@EnableReactiveMethodSecurity`. `ReactiveDocumentPolicy` cũng không gọi `SecurityContextHolder.getContext()`; Spring Security cung cấp authentication qua reactive method security expression. Nếu service cần đọc identity trực tiếp trong pipeline, dùng `ReactiveSecurityContextHolder.getContext()`.

### StepVerifier: kiểm tra method security của Reactive service

~~~java
@SpringBootTest(
    classes = ReactiveDocumentApplication.class,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveDocumentMethodTest {
    @Autowired
    ReactiveDocumentService documents;

    @MockitoBean
    ReactiveDocumentRepository repository;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerMayRead() {
        Document doc =
            new Document("doc-a", "alice", "Kế hoạch A");
        when(repository.findById("doc-a"))
            .thenReturn(Mono.just(doc));

        StepVerifier.create(documents.read("doc-a"))
            .expectNext(doc)
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void otherUserIsDeniedByReactiveMethodSecurity() {
        when(repository.findById("doc-a"))
            .thenReturn(Mono.just(
                new Document("doc-a", "alice", "Kế hoạch A")));

        StepVerifier.create(documents.read("doc-a"))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Ví dụ yêu cầu một `ReactiveDocumentApplication` là Spring Boot WebFlux application có scan `ReactiveDocumentSecurity`, `ReactiveDocumentService` và `ReactiveDocumentPolicy`; có thể tạo `@SpringBootApplication` riêng cho nhánh Reactive. Các import gồm `reactor.test.StepVerifier`, `@WithMockUser`, `@MockitoBean`, `Mono` và Mockito stubbing. Test không chạy trong project Servlet đang có cùng các class SecurityFilterChain.

**Khác biệt then chốt:** với Reactive method security, một publisher có thể chưa thực thi cho đến khi được subscribe. `StepVerifier` vừa subscribe vừa kiểm chứng completion/error; một test chỉ gọi `documents.read("doc-a")` mà không subscribe **chưa đủ chứng minh** policy đã chạy.

### WebTestClient: bảo vệ HTTP Reactive

Nếu ứng dụng WebFlux có controller `GET /api/documents/{id}` gọi `ReactiveDocumentService.read`, test HTTP có thể viết:

~~~java
@Test
void aliceCanReadDocumentThroughWebFluxSecurity() {
    when(repository.findById("doc-a"))
        .thenReturn(Mono.just(
            new Document("doc-a", "alice", "Kế hoạch A")));

    webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/documents/doc-a")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.ownerId").isEqualTo("alice");
}

@Test
void bobIsDeniedByReactiveService() {
    when(repository.findById("doc-a"))
        .thenReturn(Mono.just(
            new Document("doc-a", "alice", "Kế hoạch A")));

    webTestClient.mutateWith(mockUser("bob").roles("USER"))
        .get().uri("/api/documents/doc-a")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Đặt các phương thức trên trong một lớp dùng `@SpringBootTest(webEnvironment = MOCK, properties = "spring.main.web-application-type=reactive")`, `@AutoConfigureWebTestClient`, `@Autowired WebTestClient webTestClient` và `@MockitoBean ReactiveDocumentRepository repository`. WebFlux test support cần gắn `SecurityWebFilterChain`; một client dựng chỉ từ controller mà bỏ filter không chứng minh HTTP security hoạt động.

`mockUser()` và `mockJwt()` cho WebTestClient giúp kiểm tra authorization của principal giả lập trong Reactor Context. Nếu cần kiểm tra JWT thật, dùng Bearer string qua `ReactiveJwtDecoder`; nếu cần kiểm tra CSRF trên POST/PUT, áp dụng `csrf()` đúng cấu hình WebFlux và có test dương/âm riêng.

## 15. Các lỗi khiến test @PreAuthorize xanh sai

### Chỉ test DocumentPolicy rồi bỏ qua interceptor

Một phép gọi:

~~~java
assertThat(policy.canRead(alice, "doc-a")).isTrue();
~~~

kiểm chứng thuật toán kiểm tra owner, nhưng **không** chứng minh `@PreAuthorize` đang tồn tại trên method hoặc đã được kích hoạt. Vì thế phải duy trì ít nhất một test gọi **Spring-managed service** bằng `@WithMockUser` và kỳ vọng `AccessDeniedException` khi không đủ quyền. Nếu xóa `@EnableMethodSecurity`, test direct bean cần phát hiện thay đổi đó.

### Tạo đối tượng bằng new hoặc self-invocation

~~~java
// Không đi qua Spring proxy.
DocumentService service = new DocumentService(repository);
service.rename("doc-a", "bypass");
~~~

Nếu gọi như vậy, annotation `@PreAuthorize` không tự chạy. Self-invocation `this.rename(...)` bên trong `DocumentService` cũng có thể bỏ qua proxy. Với Spring AOP kiểu proxy, nên kiểm tra security ở ranh giới một **bean được inject** và tránh thiết kế dựa vào self-invocation để chặn quyền.

### Mock chính policy đang được kiểm chứng

~~~java
@MockitoBean
DocumentPolicy documentPolicy;

// Nếu stub canRead thành true cho mọi ID:
when(documentPolicy.canRead(any(), anyString()))
    .thenReturn(true);
~~~

Cách này có thể phù hợp trong một test **chỉ nhằm kiểm tra controller mapping**, nhưng là **sai mục tiêu** nếu test mang tên “Bob không được đọc tài liệu Alice”. Nó vô hiệu hóa logic chủ sở hữu thực sự mà test muốn chứng minh. Trong các ví dụ chính của bài, chỉ mock repository; `DocumentPolicy` và `DocumentService` vẫn là bean thật.

### Chỉ kiểm tra status 403

Một `PUT` thiếu CSRF sẽ nhận `403` ngay cả khi người dùng có quyền. Nếu muốn chứng minh **thiếu EDITOR**, hãy cung cấp `csrf()` hợp lệ. Nếu muốn chứng minh **sai owner**, người gọi nên có đủ EDITOR để không bị chặn bởi điều kiện role. Cách dựng test này cô lập đúng nguyên nhân từ chối.

### Đặt tất cả quyền ở filter nhưng quên service

Một `GET /api/documents/{id}` chỉ yêu cầu `authenticated()` cho phép Alice/Bob đến controller. Nếu service không có annotation hoặc policy, user có thể thử các ID của người khác. Test trực tiếp service với Bob là bằng chứng bổ sung rằng **business boundary** vẫn có bảo vệ khi có một caller không đi qua URL.

### Chỉ kiểm tra owner trên body gửi lên

Client có thể gửi:

~~~json
{
  "documentId": "doc-a",
  "ownerId": "bob",
  "title": "Sửa trái phép"
}
~~~

Việc dữ liệu gửi lên tự tuyên bố `ownerId` không làm Bob thành chủ sở hữu. Policy phải tra `DocumentRepository.findById("doc-a")` và so sánh với Authentication đã xác minh. Trong demo, request PUT chỉ nhận `title` nên không có trường owner để client thay đổi.

### Không kiểm tra thao tác ghi có bị ngăn hay không

Nếu `@PreAuthorize` sai thứ tự hoặc annotation bị bỏ qua, một test chỉ quan sát HTTP status có thể bỏ sót tác dụng phụ. Hãy dùng:

~~~java
verify(repository, never()).save(any(Document.class));
~~~

cho các ca bị từ chối. Với integration test database, truy vấn lại bản ghi và khẳng định `title`, `ownerId`, version/audit không bị thay đổi khi user thiếu quyền.

### Dùng chung Authentication, mock hoặc dữ liệu giữa các test

Không tạo một `static SecurityContext` hoặc principal khả biến rồi thay role trước mỗi test. Dùng `@WithMockUser` cho từng method hoặc fixture tạo mới. Với `@MockitoBean` trong cached Spring context, stub theo từng test và không cho test song song sửa cùng mock khi chưa đồng bộ. Nếu repository thật dùng chung database, tạo tài liệu theo ID/tenant test riêng.

### Nhầm 403 do owner với tài liệu không tồn tại

Policy `isOwner(...)` hiện trả `false` khi không tìm thấy ID, nên user đã authenticated có thể nhận `403` cho ID không tồn tại. Điều đó không làm Spring Data tự phát `404`; nếu sản phẩm có contract khác, thiết kế policy và exception strategy theo contract rồi test riêng. Tránh tiết lộ sự tồn tại của tài liệu người khác qua khác biệt status, thời gian hoặc message ngoài ý muốn.

### Chỉ so username mà không xét tenant

Nếu hệ thống có nhiều tenant hoặc nhiều IdP, hai user khác nhau có thể cùng tên hiển thị. Dùng stable internal principal ID và tenant từ nguồn đáng tin. Khi thêm tenant vào Document, phải test một editor tenant A **không sửa được** tài liệu tenant B dù ID người dùng hiển thị trùng nhau.

### Ownership thay đổi giữa lúc kiểm tra và lúc ghi

`@PreAuthorize` giúp kiểm tra permission **trước lời gọi**, nhưng không tự biến nhiều thao tác repository thành một transaction nguyên tử. Test data-race/optimistic locking ở tầng database và chính sách update có điều kiện owner nếu tài nguyên có thể chuyển chủ.

## 16. Ma trận test tổng hợp cho CI

| Ca kiểm thử | Spring context? | Công cụ | Bằng chứng chính |
| --- | --- | --- | --- |
| Policy: owner đúng | Không | JUnit + Mockito | `canRead` trả true |
| Policy: owner sai | Không | JUnit + Mockito | `canRead` trả false |
| Policy: thiếu role | Không | JUnit + Mockito | `canRename` false, không tra repo |
| Method: owner đọc | Có | `@WithMockUser` + Spring bean | Method interceptor cho phép |
| Method: Bob đọc doc-a | Có | `@WithMockUser` + AssertJ | `AccessDeniedException` |
| Method: EDITOR khác owner | Có | `@WithMockUser` + Mockito verify | `save` không được gọi |
| HTTP: anonymous GET | Có | MockMvc | `401` trong Basic demo |
| HTTP: owner GET | Có | MockMvc + `user()` | `200` và body đúng |
| HTTP: Bob GET doc-a | Có | MockMvc + `user()` | `403` do method policy |
| HTTP: Alice PUT hợp lệ | Có | MockMvc + `csrf()` | `200`, save đúng dữ liệu |
| HTTP: thiếu EDITOR | Có | MockMvc + `csrf()` | `403`, không save |
| HTTP: thiếu CSRF | Có | MockMvc | `403` trước service |
| HTTP: Basic sai mật khẩu | Có | MockMvc + `httpBasic()` | `401` từ authentication |
| JWT mocked | Có | MockMvc `jwt()` | Permission theo JWT principal giả |
| JWT signed thật | Có | Bearer HTTP + `JwtDecoder` | Chữ ký/issuer/expiry và permission |
| Reactive method: owner sai | Có | `@WithMockUser` + `StepVerifier` | Reactive `AccessDeniedException` |
| Reactive HTTP: Bob GET doc-a | Có | `WebTestClient` + `mockUser()` | `403` qua WebFlux chain |
| Real database: UPDATE sai owner | Có | Integration test | Row count bằng 0, data không đổi |

Không phải mọi thay đổi code đều phải chạy toàn bộ E2E trên cùng JVM. Với CI, có thể giữ unit + method + HTTP policy tests trong pipeline nhanh, còn database/auth protocol tests dùng môi trường tích hợp riêng. Tuy nhiên, **các negative test về quyền** nên chạy thường xuyên để phát hiện regression BOLA/IDOR sớm.

## 17. Quy trình làm bài theo từng chặng

### Chặng A — Xác minh chính sách bằng unit test

1. Tạo `Document` và `DocumentRepository`.
2. Viết `DocumentPolicy.canRead(...)` và `canRename(...)`.
3. Test owner đúng, owner sai, ID không có, anonymous, thiếu EDITOR, đủ EDITOR.
4. Duy trì test “owner đúng nhưng thiếu role” **và** “role đúng nhưng sai owner”.

Tiêu chí đạt: tất cả điều kiện được kiểm tra bằng fixture repository và Authentication độc lập; test có lỗi rõ khi đổi một điều kiện.

### Chặng B — Xác minh method security

1. Kích hoạt `@EnableMethodSecurity`.
2. Đưa `@PreAuthorize` lên `DocumentService.read` và `rename`.
3. Inject service bean trong `@SpringBootTest`, thay repository bằng `@MockitoBean`.
4. Dùng `@WithMockUser` và assert `AccessDeniedException` khi vi phạm.
5. Verify `repository.save(...)` không chạy trong các trường hợp bị từ chối.

Tiêu chí đạt: tạm thời bỏ annotation hoặc tắt method security **phải khiến ít nhất một negative test bị fail**, giúp phát hiện việc security interceptor không được áp dụng.

### Chặng C — Xác minh HTTP

1. Dùng `@AutoConfigureMockMvc` với filters đang bật.
2. Gửi anonymous GET: `401` theo Basic demo.
3. Gửi Alice/Bob bằng `user(...)`: `200`/`403` đúng owner.
4. Gửi PUT với CSRF hợp lệ: đủ role + đúng owner mới được lưu.
5. Gửi PUT thiếu CSRF: `403` nhưng xác định nguyên nhân là CSRF, không nhầm với ownership.
6. Gửi Basic header sai và đúng: kiểm tra authentication provider thật của demo.

Tiêu chí đạt: test chứng minh **HTTP filter + method security + repository lookup** phối hợp chính xác. Không thêm `@WithMockUser` vào request mong đợi anonymous.

### Chặng D — Xác minh dữ liệu và cơ chế thật

1. Thay mock repository bằng database test có dữ liệu độc lập.
2. Kiểm tra ID không tồn tại và chính sách 403/404.
3. Gửi thao tác UPDATE sai owner và xác minh không có row thay đổi.
4. Bổ sung tenant ID, stable principal ID và khả năng đổi owner.
5. Nếu sử dụng OAuth2/OIDC/JWT, kiểm tra mapper identity và flow/token thật trong suite phù hợp.

Tiêu chí đạt: không chỉ “HTTP trả đúng status”, mà dữ liệu sau request vẫn đúng và không bị rò chéo chủ sở hữu/tenant.

## 18. Bài tập mở rộng

1. **Giữ nguyên role, đổi owner:** cho Bob có `ROLE_EDITOR`, kiểm tra Bob không thể sửa `doc-a` của Alice nhưng sửa được `doc-b` của mình. Vì sao chỉ `hasRole("EDITOR")` không đủ?
2. **Giữ nguyên owner, đổi role:** cho Alice chỉ `ROLE_USER`, kiểm tra Alice đọc `doc-a` thành công nhưng đổi tiêu đề bị `403`.
3. **Kiểm tra controller không thay policy:** thêm một endpoint mới gọi `DocumentService.read`. Dùng MockMvc và direct service test chứng minh vẫn bị `403` khi sai owner.
4. **Bỏ @EnableMethodSecurity:** thực hiện trong nhánh test có kiểm soát, xem negative service test nào không còn bắt lỗi và tại sao.
5. **Self-invocation:** thêm một phương thức trong `DocumentService` gọi `this.rename(...)`; chứng minh nguy cơ bỏ qua proxy và thiết kế lại bean boundary.
6. **Không tồn tại:** yêu cầu `doc-unknown`. So sánh policy fail-closed 403 với thiết kế API 404 che giấu tài nguyên và chọn một contract thống nhất.
7. **Tạo principal theo internal ID:** thay `alice` bằng `user-173` trong `ownerId` và viết `@WithSecurityContext` để mang `AccountPrincipal` tương ứng.
8. **Thêm tenant:** mở rộng `Document` và policy kiểm tra cùng tenant. Test user có cùng display name nhưng khác tenant không được đọc chéo.
9. **Lỗi repository:** cho `findById` ném exception; xác minh request không được `200` và không có side effect ghi. Tách lỗi hạ tầng khỏi lỗi thiếu quyền.
10. **CSRF:** cho owner/EDITOR gọi PUT thiếu token, thấy `403`; thêm `csrf()` và có `200`. Giải thích vì sao chỉ một test `403` là chưa đủ.
11. **Bearer JWT:** dùng `jwt()` tạo subject Alice/Bob và authorities. Sau đó tạo JWT ký bằng key test, gửi Bearer thật và kiểm tra invalid signature nhận `401`.
12. **WebFlux:** chuyển owner lookup sang `Mono<Boolean>` và service sang `Mono<Document>`. Dùng `StepVerifier` xác minh reactive method interceptor, `WebTestClient` xác minh HTTP policy.
13. **Database race:** cho owner của doc-a đổi sau phép kiểm tra; áp dụng update có điều kiện owner/version để request cũ không ghi được.
14. **CI mutation:** thử bỏ `@PreAuthorize` hoặc sửa `document.ownerId().equals(auth.getName())` thành luôn true. Bộ test nào thất bại? Nếu không có test nào thất bại, hãy bổ sung một negative test phù hợp.

### Kết quả cần đạt

Sau bài thực hành, người học phải chứng minh được **service Spring bean có `@PreAuthorize` thực sự được Spring Security chặn trước khi thao tác dữ liệu**, không chỉ chứng minh một hàm `canRead` trả đúng kết quả. Bộ test cần bao phủ **owner đúng/sai, role đủ/thiếu, anonymous, CSRF, HTTP Basic/JWT giả lập theo đúng mục tiêu**, đồng thời có kiểm tra **không xảy ra thao tác ghi trái phép**. Với WebFlux, cần biết chuyển sang Reactor Context và kiểm tra publisher bằng `StepVerifier`/`WebTestClient`. Khi dùng token/IdP thật, cần suite xác minh authentication protocol riêng thay vì suy ra từ mock identity.

### Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive WebTestClient Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
