# Ưu tiên ca phủ định bên cạnh ca truy cập thành công

Một test xác nhận Alice gọi `GET /api/documents/a-1` và nhận `200 OK` là cần thiết, nhưng nó **chưa chứng minh API được bảo vệ**. Endpoint có thể vẫn trả 200 cho người chưa đăng nhập, Bob xem được tài liệu của Alice, tài khoản không có quyền admin gọi được lệnh quản trị, hoặc request thay đổi dữ liệu thiếu CSRF token vẫn được chấp nhận.

Trong chương **Bộ kiểm thử và CI** của module **`SPRING_SECURITY_TESTING`**, mục tiêu là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên Servlet/MockMvc và Reactive/WebTestClient. Các helper như `@WithMockUser`, `SecurityContext`, `jwt()`, `opaqueToken()`, `oauth2Login()` hay `oidcLogin()` giúp chuẩn bị danh tính thử nghiệm. Tuy nhiên, **bộ test chỉ có ca truy cập thành công sẽ bỏ sót đúng những ranh giới cần từ chối truy cập**. Bài này trình bày cách ưu tiên, thiết kế, chứng minh và đưa các ca phủ định vào CI bên cạnh happy path.

Sau bài học, bạn sẽ:

- Chuyển chính sách quyền thành **cặp ca được phép và bị từ chối**, có ít nhất một phản ví dụ cho mỗi ranh giới quan trọng.
- Phân biệt `401 Unauthorized`, `403 Forbidden`, redirect login `302`, lỗi CSRF và tài nguyên không tồn tại.
- Kiểm tra thiếu Authentication, thiếu role/scope, truy cập sai chủ sở hữu (IDOR/BOLA), sai tenant, CSRF và đường đi xác thực JWT/OAuth2/OIDC ở **đúng lớp**.
- Viết `MockMvc` và `WebTestClient` tests đi qua security filter chain thật; tránh test pass vì `@WithMockUser` hoặc `jwt()` đã bỏ qua bước đang cần kiểm chứng.
- Xây dựng test có dữ liệu ổn định, không làm rò session/user/token giữa các case và xác nhận **không có side effect khi bị chặn**.
- Ưu tiên P0 negative regressions trong pipeline CI, nhưng vẫn giữ positive controls để tránh hệ thống “chặn tất cả” mà bộ test vẫn xanh.

## 1. Vì sao happy path xanh chưa nói lên tính an toàn?

Giả sử quy tắc nghiệp vụ là:

> Người dùng đã đăng nhập được xem tài liệu của mình. Người có `DOCUMENT_AUDIT` xem được tài liệu của người khác. Chỉ `ROLE_ADMIN` được xem báo cáo quản trị. Request thay đổi dữ liệu từ browser phải đi qua bảo vệ CSRF thích hợp.

Một test “Alice đọc tài liệu Alice → 200” có thể xanh ngay cả khi:

1. Developer bỏ `.authenticated()` và anonymous cũng xem được dữ liệu.
2. Service đọc theo ID nhưng quên kiểm tra chủ tài liệu; Bob xem được dữ liệu Alice (**Broken Object Level Authorization**, thường gọi IDOR).
3. Điều kiện `hasRole("ADMIN")` vô tình thành `authenticated()`.
4. CSRF bị vô hiệu hóa trên endpoint dùng cookie/session mà vẫn cho POST thay đổi trạng thái.
5. Test tạo một `Authentication` giả nên không phát hiện token header bị bỏ qua hoặc decoder không chạy.

Do đó, mỗi hành vi bảo mật nên có **bất biến được phép** và **bất biến từ chối**:

```text
CHO PHÉP:
  Alice đã xác thực + tài liệu của Alice         -> 200 và đúng nội dung
  Admin + ROLE_ADMIN                             -> 200 với route admin

TỪ CHỐI:
  Anonymous + endpoint riêng                     -> 401 / redirect login
  Bob + tài liệu Alice                           -> 403 hoặc 404 theo policy
  Alice thiếu ROLE_ADMIN + route admin           -> 403
  Alice + POST thiếu CSRF trong flow cần CSRF    -> 403
  Bearer hợp lệ nhưng thiếu scope cần thiết       -> 403
  Bearer không hợp lệ                            -> 401
```

**Negative test không chỉ là một phép thử status 4xx.** Nó phải kiểm chứng rằng hành động bị cấm **không xảy ra**. Nếu DELETE trả 403 nhưng record vẫn bị xóa, test chỉ assert status đã bỏ sót lỗi rất nghiêm trọng.

### Không nhất thiết một ca dương tương ứng đúng một ca âm

Một route có thể đi qua nhiều ranh giới: authentication, role, tenant, object owner, CSRF, request validation, method security và token expiry. Vì vậy một ca 200 thường cần **nhiều ca phủ định**. Ưu tiên theo rủi ro và theo nơi ra quyết định, không chạy theo tỷ lệ số test dương/âm cố định.

```mermaid
flowchart TD
    A["Một quy tắc quyền"] --> B["Đúng user + action + object: allow"]
    A --> C["Anonymous: deny"]
    A --> D["User thiếu role/scope: deny"]
    A --> E["Sai owner hoặc tenant: deny"]
    A --> F["Thiếu CSRF/token hợp lệ: deny"]
    B --> G["CI regression gate"]
    C --> G
    D --> G
    E --> G
    F --> G
```

## 2. Đọc đúng 401, 403, 302 và lỗi ở các tầng khác nhau

HTTP status có ý nghĩa **trong ngữ cảnh cấu hình security hiện tại**, không phải theo một bảng cố định áp dụng cho mọi hệ thống.

| Tình huống | Phản hồi thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Anonymous gọi API Basic/Bearer được bảo vệ | `401 Unauthorized` | Authentication entry point, có thể có `WWW-Authenticate` |
| Anonymous gọi trang có form login | `302` đến trang login | Assert `Location`/redirect thay vì ép 401 |
| Đã authenticated nhưng thiếu role/authority | `403 Forbidden` | Authorization thực sự chặn |
| Browser POST thiếu/sai CSRF token | `403 Forbidden` | CSRF filter có thể chặn **trước** kiểm tra Authentication |
| Object không tồn tại | `404 Not Found` | Khác với không đủ quyền, trừ khi chính sách cố ý che giấu |
| Cross-user/tenant object | `403` hoặc `404` | Thống nhất contract, kiểm tra fixture tồn tại |
| Bearer token sai/hết hạn | Thường `401` từ Resource Server | Cần test decoder/introspector, không chỉ mock principal |
| OAuth2 login callback lỗi | Có thể `302 /login?error` | Failure handler theo cấu hình, không phải HTTP code của IdP |

**Lưu ý về thứ tự filter:** nếu muốn kiểm tra “anonymous bị từ chối vì chưa đăng nhập” ở `POST` có bật CSRF, hãy đưa **CSRF token hợp lệ** vào request. Nếu không, `CsrfFilter` có thể trả 403 trước, khiến bạn không biết authentication entry point sẽ hoạt động ra sao.

Với browser session, một `302` có thể là redirect sau đăng nhập thành công **hoặc** redirect về màn hình login khi lỗi. Do đó chỉ `status().is3xxRedirection()` không đủ; cần assert `redirectedUrl(...)` và trạng thái được phép/bị chặn ở request tiếp theo.

## 3. Xếp hạng ca phủ định theo rủi ro

Một nhóm P0 nên chạy ở mọi pull request, đặc biệt với thay đổi liên quan xác thực, phân quyền hoặc bảo vệ tài nguyên:

| Mức | Ví dụ kiểm thử | Mục tiêu |
| --- | --- | --- |
| **P0 — bắt buộc** | Anonymous không xem dữ liệu riêng; user thường không vào admin; khác owner/tenant không xem được record; CSRF của browser action; token không hợp lệ không được nhận | Chặn regression cấp quyền trái phép |
| **P1 — thường xuyên** | Scope/role mapping, method security, logout/session replay, refresh/introspection error, OAuth2 state mismatch | Chứng minh các boundary vận hành đúng |
| **P2 — tích hợp chuyên sâu** | mTLS handshake, CRL/OCSP, timeout IdP, Redis session, race condition, key rotation, proxy forwarding | Kiểm tra hệ thống và phụ thuộc bên ngoài |

Đây là **khung ưu tiên gợi ý**, không phải xếp hạng mức nguy hiểm cố định. Nếu một hệ thống lấy mTLS làm boundary chính, các test handshake bị từ chối có thể là P0; nếu doanh nghiệp lưu dữ liệu tài chính đa tenant, IDOR/cross-tenant phải thuộc nhóm blocker.

Cách chọn thực dụng cho một endpoint mới:

1. Viết một **positive control** với principal và dữ liệu đúng.
2. Thêm negative case cho **anonymous** hoặc thiếu chứng thực.
3. Thêm case **authenticated nhưng thiếu quyền**; với dữ liệu cá nhân, thêm **sai owner/tenant**.
4. Nếu có side effect, kiểm chứng data store/outbound call **không đổi** khi bị chặn.
5. Với browser state-changing request, kiểm tra CSRF có/không hợp lệ theo threat model.
6. Với Bearer/OAuth2/OIDC, bổ sung negative test ở đúng tầng decoder/introspector/callback khi cần xác minh cơ chế thật.

## 4. Ứng dụng Servlet mẫu có cả đường được phép và bị chặn

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Security 6.x với:

```text
Implementation:
  spring-boot-starter-web
  spring-boot-starter-security

Test:
  spring-boot-starter-test
  spring-security-test
```

Để có response dễ assert, API mẫu dùng HTTP Basic cho Authentication; **CSRF vẫn bật** để minh họa endpoint thay đổi dữ liệu.

### 4.1. Application và SecurityFilterChain

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NegativeSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                NegativeSecurityDemoApplication.class, args);
    }
}
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders
        .HttpSecurity;
import org.springframework.security.config.annotation.web.configurers
        .AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class NegativeSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                // Giữ CSRF mặc định cho ví dụ POST bên dưới.
                .build();
    }
}
```

`hasRole("ADMIN")` tìm authority `ROLE_ADMIN`; `authenticated()` chỉ bảo đảm request có principal đã xác thực, **không tự biết bản ghi thuộc ai**. Vì vậy, owner check cần đặt ở tầng dữ liệu/service.

Việc giữ CSRF trong ví dụ không có nghĩa mọi API Bearer stateless đều phải bảo vệ CSRF giống browser: chính sách thực tế phụ thuộc cách client gửi credential và khả năng trình duyệt tự đính kèm credential. Không sao chép cấu hình này mà không đánh giá threat model.

### 4.2. DocumentView và method-level ownership

```java
public class DocumentView {
    private final String id;
    private final String owner;
    private final String content;

    public DocumentView(String id, String owner, String content) {
        this.id = id;
        this.owner = owner;
        this.content = content;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getContent() {
        return content;
    }
}
```

```java
import java.util.Map;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
class DocumentService {
    private final Map<String, DocumentView> documents = Map.of(
            "a-1", new DocumentView(
                    "a-1", "alice", "Alice private content"),
            "b-1", new DocumentView(
                    "b-1", "bob", "Bob private content"));

    @PostAuthorize(
            "returnObject == null or "
            + "returnObject.owner == authentication.name "
            + "or hasAuthority('DOCUMENT_AUDIT')")
    public DocumentView findById(String id) {
        return documents.get(id);
    }
}
```

`@PostAuthorize` được sử dụng **chỉ cho truy vấn đọc**. Với lệnh cập nhật/xóa, kiểm tra sau lời gọi có thể quá muộn vì side effect đã xảy ra. Các hệ thống lớn nên giới hạn dữ liệu theo owner/tenant ngay từ query, kết hợp method security khi phù hợp.

### 4.3. Controller

```java
import java.security.Principal;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class NegativeSecurityDemoController {
    private final DocumentService documents;

    NegativeSecurityDemoController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/api/me")
    String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/admin/report")
    String report() {
        return "admin-report";
    }

    @GetMapping("/api/docs/{id}")
    ResponseEntity<DocumentView> document(@PathVariable String id) {
        DocumentView found = documents.findById(id);
        return found == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(found);
    }

    @PostMapping("/api/actions")
    String performAction() {
        return "created-for-test";
    }
}
```

Controller gọi `DocumentService` qua Spring bean (AOP proxy), để `@PostAuthorize` thực sự có hiệu lực. Không tạo `new DocumentService()` trong test rồi kết luận method security đã chạy.

## 5. Bộ test MockMvc: positive controls bên cạnh negative cases

`@SpringBootTest` và `@AutoConfigureMockMvc` sử dụng security filter chain của ứng dụng. `SecurityMockMvcRequestPostProcessors.user(...)` tạo Authentication test cho request; `csrf()` mô phỏng CSRF token hợp lệ.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest(classes = NegativeSecurityDemoApplication.class)
@AutoConfigureMockMvc
class SecurityPolicyMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotAccessProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanAccessHerProfile() throws Exception {
        mvc.perform(get("/api/me")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void userCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                    .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-report"));
    }

    @Test
    void aliceCanReadHerDocument() throws Exception {
        mvc.perform(get("/api/docs/a-1")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("a-1"))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void bobCannotReadAlicesDocument() throws Exception {
        mvc.perform(get("/api/docs/a-1")
                    .with(user("bob").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorMayReadAcrossOwners() throws Exception {
        mvc.perform(get("/api/docs/a-1")
                    .with(user("auditor").authorities(
                            new SimpleGrantedAuthority(
                                    "DOCUMENT_AUDIT"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/api/actions")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithInvalidCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/api/actions")
                    .with(user("alice").roles("USER"))
                    .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/api/actions")
                    .with(user("alice").roles("USER"))
                    .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("created-for-test"));
    }

    @Test
    void anonymousPostWithValidCsrfStillNeedsLogin()
            throws Exception {
        mvc.perform(post("/api/actions").with(csrf()))
                .andExpect(status().isUnauthorized());
    }
}
```

Ở đây **cùng URL** nhưng input bảo mật khác nhau dẫn đến kết quả đối lập:

- `Alice → /api/docs/a-1` trả 200, trong khi `Bob → /api/docs/a-1` trả 403. Đây là test object-level authorization, không chỉ route authorization.
- `Root + ROLE_ADMIN` được 200, `Alice + ROLE_USER` bị 403. Nó cho thấy rule `hasRole` được thực thi.
- POST có CSRF hợp lệ được chấp nhận; POST có thiếu/sai CSRF bị 403.
- Anonymous với CSRF hợp lệ vẫn bị 401 — vì đã **tách** điều kiện CSRF khỏi điều kiện Authentication trong test.

**Giới hạn của `user("alice")`:** post-processor không kiểm tra password, HTTP Basic header hay form login. Nếu bài test cần chứng minh user/password thực sự được chấp nhận hoặc từ chối, phải tạo request qua cơ chế credential của ứng dụng; helper ở đây chỉ kiểm tra authorization sau khi có Authentication.

### Positive control ngăn test âm “xanh giả”

Nếu fixture a-1 không tồn tại, một test kỳ vọng Bob nhận 404 có thể PASS dù code **không kiểm tra owner**. Vì vậy phải có control test Alice đọc **cùng bản ghi** thành công. Tương tự, một test “danh sách không có bản ghi tenant B” có thể PASS nếu API luôn trả danh sách rỗng; cần khẳng định bản ghi tenant A vẫn hiện diện.

## 6. Matrix cho role, authority và scope

Spring Security phân biệt chuỗi authority nguyên văn. `roles("ADMIN")` tạo `ROLE_ADMIN`; `authorities("ADMIN")` giữ `ADMIN`, không tự đổi tiền tố. JWT scope thường được quy ước thành `SCOPE_...` khi có converter tương ứng.

| Danh tính | Granted authorities | Rule `hasRole("ADMIN")` | Kết quả |
| --- | --- | --- | --- |
| Root | `ROLE_ADMIN` | Đạt | 200 |
| Alice | `ROLE_USER` | Không đạt | 403 |
| Bob | `ADMIN` | Không đạt | 403 |
| Service | `SCOPE_admin` | Không đạt | 403 |
| Anonymous | Không có Authentication | Không đạt | 401 với HTTP Basic |

Khi có nhiều kiểu quyền gần giống nhau, dùng `@ParameterizedTest` với dữ liệu rõ ràng:

```java
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.params.provider.Arguments.arguments;

static Stream<Arguments> deniedAdminCases() {
    return Stream.of(
            arguments("alice", "ROLE_USER"),
            arguments("bob", "ADMIN"),
            arguments("service", "SCOPE_admin"));
}

@ParameterizedTest(name = "{0} with {1} is not admin")
@MethodSource("deniedAdminCases")
void nonAdminAuthoritiesAreDenied(
        String username, String authority) throws Exception {
    mvc.perform(get("/api/admin/report")
                .with(user(username).authorities(
                        new SimpleGrantedAuthority(authority))))
            .andExpect(status().isForbidden());
}
```

Đặt `deniedAdminCases()` và `nonAdminAuthoritiesAreDenied(...)` trong `SecurityPolicyMvcTest` ở mục 5. Test dương `ROLE_ADMIN → 200` vẫn phải tồn tại: một endpoint bị khóa hoàn toàn sẽ có thể làm tất cả parameterized negative cases xanh.

### “Chỉ sai một điều kiện” là nguyên tắc quan trọng

Khi test một kiểm tra quyền, hãy làm **các tiền điều kiện trước đó hợp lệ**:

| Điều muốn kiểm tra | Phần đầu vào phải hợp lệ | Điều duy nhất cố tình sai |
| --- | --- | --- |
| Authentication | Route/method và CSRF phù hợp | Không có principal |
| Admin role | Đã xác thực | Không có `ROLE_ADMIN` |
| Object ownership | Đã xác thực và có quyền vào route, CSRF đúng nếu cần | ID thuộc user khác |
| CSRF | User có đủ quyền thực thi | Token CSRF thiếu/sai |
| JWT decoder | Bearer header và route phù hợp | Token invalid/expired |
| OAuth2 callback | Authorization request/session đúng | State khác/code lặp/token exchange fail |

Một test `DELETE` dùng Bob mà thiếu CSRF nhận 403 **không chứng minh** owner check đã chạy; `CsrfFilter` có thể chặn trước. Khi muốn test owner, hãy cung cấp CSRF hợp lệ.

## 7. Ca phủ định còn phải chứng minh không có side effect

Một response `403` không đủ an toàn nếu server **đã thay đổi trạng thái trước khi từ chối**. Với các hành động DELETE, cập nhật quyền, chuyển tiền, gửi email hoặc phát sự kiện, hãy quan sát cả hệ quả nghiệp vụ.

Ví dụ nếu project có `DELETE /api/docs/{id}` và một repository lưu trữ thật:

```java
@Test
void deniedDeleteLeavesDocumentUnchanged() throws Exception {
    DocumentView before = repository.findById("a-1")
            .orElseThrow();

    mvc.perform(delete("/api/docs/a-1")
                    .with(user("bob").roles("USER"))
                    .with(csrf()))
            .andExpect(status().isForbidden());

    DocumentView after = repository.findById("a-1")
            .orElseThrow();
    assertThat(after.getOwner()).isEqualTo(before.getOwner());
    assertThat(after.getContent()).isEqualTo(before.getContent());
}
```

Đây là **bài tập mở rộng**, chưa chạy nguyên xi với ứng dụng mẫu `Map` ở mục 4: cần bổ sung DELETE endpoint, repository có `findById(...)`, rule kiểm tra quyền trước khi xóa và fixture thực. Test chỉ đáng tin khi controller và repository trong assertion sử dụng **cùng data store**.

Với một outbound gateway có thể dùng mock trong Spring test context:

```java
mvc.perform(post("/api/payments")
                .with(user("bob").roles("USER"))
                .with(csrf())
                .contentType("application/json")
                .content("{\"accountId\":\"alice-account\","
                        + "\"amount\":1000}"))
        .andExpect(status().isForbidden());

// paymentGateway là mock được inject vào application context.
verifyNoInteractions(paymentGateway);
```

Snipet này giả định app có POST payments, một ownership policy từ chối Bob và một gateway test mock phù hợp. Nó không thay thế test cổng thanh toán thật, nhưng chứng minh request bị từ chối **không khởi phát outbound call**.

Một bộ kiểm thử lệnh nhạy cảm nên kiểm tra: không thay đổi record, không gửi event/email, không làm lộ thông tin trong body lỗi, không phát token/session mới, và không lưu trạng thái giúp request tiếp theo vượt qua policy.

**Cảnh báo:** đừng dùng `@PostAuthorize` làm kiểm tra quyền duy nhất cho thao tác ghi. Khi method đã gây side effect rồi mới có quyết định “deny”, phản hồi 403 không cứu được dữ liệu. Phải kiểm tra quyền trước thao tác, hoặc dùng transaction và điều kiện owner/tenant bảo đảm nguyên tử.

## 8. Phủ định JWT, opaque token và OAuth2/OIDC ở đúng tầng

Các helper của `spring-security-test` giúp tạo `Authentication` nhanh. Nhưng test chỉ có ý nghĩa nếu nó chạy qua đúng **boundary cần kiểm chứng**.

### 8.1. JWT: token đã được chấp nhận nhưng thiếu scope

Giả định một Servlet Resource Server có route `GET /api/reports` yêu cầu `SCOPE_reports.read`, cấu hình `oauth2ResourceServer().jwt()` và controller trả 200 khi được phép:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

// Positive control: có quyền truy cập.
mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                            "SCOPE_reports.read"))))
        .andExpect(status().isOk());

// Negative control: có Authentication nhưng thiếu quyền.
mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_other"))))
        .andExpect(status().isForbidden());
```

Đây là **mẫu cho ứng dụng Resource Server**, không chạy trực tiếp với HTTP Basic application ở mục 4. `jwt()` tạo `JwtAuthenticationToken` thử nghiệm, **không gọi `JwtDecoder`** và không kiểm tra chữ ký/issuer/expiration. Nó phù hợp để kiểm tra authorization **sau khi xác thực**.

### 8.2. JWT hỏng: gửi Authorization header thật qua filter

Nếu muốn kiểm tra đường nhận bearer sai, request phải vào filter và decoder thực tế của ứng dụng. Ví dụ với `JwtDecoder` đã được mock trong test context:

```java
// Giả định app có resource-server chain, route /api/reports
// và @MockitoBean JwtDecoder jwtDecoder trong test class.
when(jwtDecoder.decode("malformed-test-token"))
        .thenThrow(new BadJwtException("invalid test token"));

mvc.perform(get("/api/reports")
            .header(HttpHeaders.AUTHORIZATION,
                    "Bearer malformed-test-token"))
        .andExpect(status().isUnauthorized());

verify(jwtDecoder).decode("malformed-test-token");
```

Các import cần có là `org.springframework.security.oauth2.jwt.BadJwtException`, `org.springframework.http.HttpHeaders`, Mockito `when/verify` và `JwtDecoder`. `@MockitoBean` có trên Spring Framework 6.2+; nếu dùng phiên bản cũ hơn, chọn cơ chế test bean override tương thích.

Test này chứng minh **bearer filter đưa chuỗi token tới decoder và từ chối khi decoder báo lỗi**. Để chứng minh validation mật mã, dùng decoder thật cùng test keys, issuer/audience/clock validators; không gọi mock decoder test là “đã kiểm chữ ký”.

**Bộ ba quan trọng cho Resource Server:**
- Bearer thiếu/hỏng/hết hạn → 401.
- Bearer được chấp nhận nhưng thiếu authority → 403.
- Bearer được chấp nhận và đủ authority → 200.

Nếu chỉ có 401 cho token hỏng và 200 cho token tốt, bạn chưa chứng minh API chặn **token hợp lệ nhưng ít quyền**.

### 8.3. Opaque token và introspection

`opaqueToken()` / `mockOpaqueToken()` tạo principal từ introspection giả lập và thường không gọi endpoint introspection thật. Dùng chúng cho positive/negative scope sau khi có Authentication.

Để test token inactive/không hợp lệ, gửi `Authorization: Bearer ...` qua Resource Server và điều khiển `OpaqueTokenIntrospector` hoặc `ReactiveOpaqueTokenIntrospector` trong test. Kiểm tra introspector được gọi và response 401/403 theo chính sách; lỗi hạ tầng introspection cần contract riêng, không mặc định mọi failure đều giống token invalid.

### 8.4. OAuth2/OIDC Login

| Mục tiêu | Công cụ phù hợp | Ca phủ định |
| --- | --- | --- |
| Endpoint sau OAuth2 Login | `oauth2Login()` / `mockOAuth2Login()` | User đã login nhưng thiếu authority |
| Endpoint sau OIDC Login | `oidcLogin()` / `mockOidcLogin()` | OidcUser đúng nhưng không có quyền nghiệp vụ |
| Authorization-code callback thật | MockMvc/WebTestClient + IdP stub | `access_denied`, `invalid_grant`, callback replay |
| OIDC state/nonce validation | Authorization request/session và token validation thật | State mismatch, nonce sai |
| OAuth2 client outbound | Authorized client manager/repository + HTTP stub | Thiếu token/scope, token endpoint fail |

`oidcLogin()` không thực hiện redirect, token exchange hay ID token validation. Nếu yêu cầu “callback lặp không tạo login mới” là ca P0, phải tạo authorization request, giữ state và session rồi mô phỏng callback/token endpoint. Mock principal test trả lời câu hỏi khác.

### 8.5. Không quên object authorization sau khi có scope

Token `SCOPE_documents.read` có thể cho phép đọc tài liệu **của tenant hiện tại**, không phải tài liệu thuộc mọi tenant. Hãy thêm ca token hợp lệ/đủ scope nhưng truy cập sai owner hoặc tenant; đọc claim ID từ principal đáng tin và đối chiếu với resource thật ở service/query.

## 9. WebFlux: cùng tư duy, dùng WebTestClient

Spring WebFlux dùng `SecurityWebFilterChain` và Reactor Context, không dùng Servlet `MockMvc`. Một cấu hình tối thiểu để test role:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveNegativeSecurityConfig {
    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Giả định một WebFlux application có controller `GET /api/me` trả `Mono<String>` là principal name và `GET /api/admin` trả nội dung cho admin. Test:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityNegativeTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousCannotReadProfile() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadProfile() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void ordinaryUserCannotReadAdmin() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get()
                .uri("/api/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdmin() {
        client.mutateWith(mockUser("root").roles("ADMIN"))
                .get()
                .uri("/api/admin")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Mẫu test yêu cầu **Spring Boot WebFlux context** chứa cấu hình/2 controller endpoints tương ứng; không trộn Servlet application sample vào cùng context. `bindToApplicationContext(...)` và `apply(springSecurity())` tích hợp WebFlux security chain; `bindToController(...)` trần không tự chứng minh Spring Security filters được chạy.

Với API WebFlux thay đổi state và CSRF được bật:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

// Giả định POST /api/actions đã tồn tại.
client.mutateWith(mockUser("alice"))
        .post().uri("/api/actions")
        .exchange().expectStatus().isForbidden();

client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/api/actions")
        .exchange().expectStatus().isOk();
```

Đây là snippet mở rộng cần endpoint POST có rule phù hợp. Với API Bearer stateless không dựa vào cookie, chính sách CSRF có thể khác; không đặt “thiếu CSRF luôn phải 403” thành một quy tắc áp dụng mọi HTTP service.

Với Reactive method security, dùng Spring bean đã được proxy và `StepVerifier` với `ReactiveSecurityContextHolder.withAuthentication(...)` để kiểm tra `AccessDeniedException`. Các helper `mockJwt()`/`mockOidcLogin()` không thay thế test decoder/token exchange.

## 10. Negative test phải đi tới đúng lớp từ chối

Một 403 có thể **đúng mã nhưng sai nguyên nhân**:

```text
Request -> CSRF -> Authentication -> HTTP authorization
        -> Controller -> Method authorization -> Repository/Side effect
```

Nếu Bob gọi DELETE mà thiếu CSRF, `CsrfFilter` chặn trước và test vẫn xanh dù owner check bị xóa. Hãy **chỉ cố ý làm sai một điều kiện tại một thời điểm**, giữ các tiền điều kiện trước đó hợp lệ.

| Boundary muốn kiểm tra | Thiết lập bắt buộc | Bằng chứng |
| --- | --- | --- |
| Authentication | HTTP method và CSRF phù hợp | 401/redirect; không tạo Authentication |
| Role | Authenticated, CSRF hợp lệ nếu cần | Thiếu đúng authority → 403 |
| Ownership | Route đủ quyền, fixture tồn tại | Sai owner → 403/404 đúng policy |
| CSRF | Principal đủ quyền | Token thiếu/sai → 403 |
| Bearer decoding | Route và Authorization header đúng | Decoder/introspector được gọi, bad token → 401 |
| OAuth2 callback | Session/authorization request thật | State invalid/replay bị từ chối; không gọi token endpoint ngoài ý muốn |
| Denied write | Repository và gateway được kiểm soát | 403 + không thay đổi dữ liệu/outbound |

**Gợi ý test review:** nếu ai đó loại bỏ `hasRole("ADMIN")` hoặc `@PostAuthorize`, negative case tương ứng **phải thất bại**. Đây là cách suy nghĩ tương tự mutation testing, giúp đánh giá liệu test thật sự bảo vệ bất biến, không chỉ thực thi một đoạn code.

Đừng dùng `@AutoConfigureMockMvc(addFilters = false)` cho security regression. Với MockMvc tự cấu hình, phải áp dụng `springSecurity()` hoặc security filter chain tương ứng. Một standalone controller test không chứng minh khả năng chặn của filter.

## 11. Đưa ca phủ định bắt buộc vào CI

Không cần chạy toàn bộ TLS/IdP/Redis integration suite nặng tại mỗi lần commit, nhưng **ca phủ định P0 phải có đường chạy đáng tin và không bị bỏ qua khi merge**.

| Test layer | Ví dụ | Nhịp chạy |
| --- | --- | --- |
| Unit/security policy | Role/tenant policy, authority conversion | Mọi PR |
| Servlet/Reactive integration | 200/401/403, IDOR, CSRF, filter/method chain | Mọi PR |
| Authentication integration | JWT decoder, opaque introspector, OAuth2 stub callback | PR liên quan và CI thường xuyên |
| External store | Session, remember-me, authorized client trong Redis/JDBC | CI có hạ tầng phù hợp |
| End-to-end/transport | mTLS, proxy trust, browser OAuth2 login | CI chuyên sâu/theo rủi ro |

### Gắn nhãn `@Tag` để nhận diện security negatives

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("security-negative")
@Test
void regularUserCannotReadAdminReport() throws Exception {
    mvc.perform(get("/api/admin/report")
                    .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
}
```

Đây là ví dụ tagging, không phải yêu cầu tạo bản sao test trùng với mục 5. Thêm method vào test class có `MockMvc mvc` và imports tương ứng. Đừng dùng tag này để **loại toàn bộ positive tests** khỏi task `test` mặc định.

Ví dụ Gradle Kotlin DSL khi project dùng Java plugin, JUnit Jupiter và source set `test`:

```kotlin
import org.gradle.api.tasks.testing.Test

tasks.register<Test>("securityNegativeTest") {
    description = "Runs mandatory security denial regressions"
    group = "verification"

    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath

    useJUnitPlatform {
        includeTags("security-negative")
    }
}
```

Task riêng hữu ích để chạy nhanh hoặc phân loại reports. Task `test` tổng quát vẫn nên kiểm tra cả positive, negative và các unit tests khác. Với project multi-module hoặc custom source sets, điều chỉnh cấu hình tương ứng.

### Minh họa pipeline GitHub Actions

```yaml
name: Security regression

on:
  pull_request:
  push:
    branches: [main]

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Run mandatory security negatives
        run: ./gradlew securityNegativeTest --no-daemon

      - name: Run all tests
        run: ./gradlew test --no-daemon

      - name: Save JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: security-test-results
          path: '**/build/test-results/**/*.xml'
```

Đây là workflow **minh họa trong bài học**, không tạo file CI thật trong nhiệm vụ này. Để triển khai, cần Gradle wrapper/task, JDK và permissions phù hợp; kiểm tra/pin versions của actions theo chính sách supply chain. Không gắn `continue-on-error: true` lên security test bắt buộc. Có thể tối ưu việc chạy trùng negative cases trong hai task sau khi bảo đảm merge gate không bỏ sót.

## 12. Test isolation, dữ liệu chính xác và lỗi “xanh giả”

Các ca âm chỉ đáng tin nếu fixture và môi trường của chúng được kiểm soát:

- **Session/cookie:** không vô tình tái sử dụng `MockHttpSession`, remember-me cookie hoặc OAuth2 state từ test khác.
- **SecurityContext:** không đặt `@WithMockUser` toàn class nếu cần anonymous tests. Nếu tự đặt context vào thread, dọn theo lifecycle.
- **Authorized clients:** xóa theo `registrationId`/`principalName`; `SecurityContextHolder.clearContext()` không xóa dữ liệu persistent.
- **Database:** dùng fixture owner/tenant riêng và cleanup; `@Transactional` trên test thread không đảm bảo rollback các thao tác từ HTTP server/thread khác.
- **Clock:** kiểm tra token expiry với test `Clock`/thời gian xác định, tránh `Thread.sleep()` và phụ thuộc đồng hồ CI.
- **External systems:** dùng test server/stub hoặc mock đúng boundary, không phụ thuộc IdP production hoặc secrets thật.
- **Parallel tests:** mỗi test có ID/namespace riêng, tránh static mutable sessions/tokens và `deleteAll()` trên shared store.
- **Lỗi hạ tầng:** HTTP 500 do DB lỗi không phải bằng chứng authorization đã làm việc.
- **Data fixture:** nếu Bob nhận 404 cho tài liệu a-1, phải có positive control chứng minh **Alice vẫn đọc a-1 thành công**; nếu không 404 có thể do tài liệu không tồn tại.

Một anti-pattern là nới `status().isForbidden()` thành `status().is4xxClientError()` chỉ để test xanh. Khi đó một response lỗi ở tầng khác có thể bị hiểu nhầm thành bảo vệ đúng.

Những sai lầm khác:
1. Dùng `jwt()` để tuyên bố chữ ký JWT đã được verify.
2. Dùng `opaqueToken()` để tuyên bố introspection HTTP chạy thật.
3. Dùng `oidcLogin()` để tuyên bố OIDC state/nonce/code exchange đã qua kiểm tra.
4. Bỏ CSRF khỏi test negative write rồi nghĩ 403 là do owner rule.
5. Test danh sách rỗng nhưng không chứng minh dữ liệu hợp lệ vẫn hiện diện.
6. Chỉ kiểm tra 403, bỏ qua side effect.
7. Vô tình test endpoint public do matcher/filter chain bị cấu hình sai.
8. Chỉ chạy ca âm thủ công, không đưa vào CI bắt buộc.

## 13. Checklist và bài tập

### Checklist review endpoint mới

- [ ] Có mô tả **ai**, **hành động** gì, **object/tenant** nào và rule áp dụng.
- [ ] Có **positive control** đúng principal, quyền và fixture.
- [ ] Có **anonymous negative** theo entry point thực tế: 401 hoặc redirect.
- [ ] Có ca **authenticated nhưng thiếu role/authority/scope**.
- [ ] Có ca **sai owner/tenant**, với tài liệu thật sự tồn tại.
- [ ] Có valid/invalid/missing CSRF khi endpoint/trình duyệt cần bảo vệ CSRF.
- [ ] Denied writes không thay đổi DB, event, gateway hoặc dữ liệu bên ngoài.
- [ ] Test đi qua đúng `SecurityFilterChain`/`SecurityWebFilterChain` và method proxy.
- [ ] Nếu cần credential/token thật, đã test decoder/introspector/login flow riêng.
- [ ] Dữ liệu, session, clock, stubs và cleanup không phụ thuộc test order.
- [ ] Negative P0 nằm trong **CI gate bắt buộc**.
- [ ] Bỏ thử một rule quan trọng sẽ làm ít nhất một negative test tương ứng đỏ.

### Bài tập 1 — Admin positive/negative

Dùng MockMvc viết `ROLE_ADMIN → 200`, `ROLE_USER → 403`, `ADMIN` không tiền tố → 403, `SCOPE_admin` → 403. Đưa ba ca denied vào một parameterized test và giữ success test riêng.

### Bài tập 2 — IDOR/BOLA

Tạo a-1 của Alice và b-1 của Bob. Viết Alice đọc a-1, Bob đọc b-1, Alice bị từ chối b-1, Bob bị từ chối a-1. Nếu contract chọn 404 để che sự tồn tại, giải thích cách tránh false positive khi fixture không có record.

### Bài tập 3 — CSRF và filter order

Với `POST /api/actions`, viết Alice có CSRF → 200, Alice thiếu CSRF → 403, Alice có CSRF sai → 403, anonymous có CSRF hợp lệ → 401. Giải thích tại sao anonymous thiếu CSRF có thể bị chặn ở CSRF filter trước authentication.

### Bài tập 4 — Denied side effect

Thêm một lệnh DELETE và repository. Khi Bob cố xóa a-1, test vừa assert bị từ chối vừa query lại a-1 chứng minh không đổi. Với outbound action, verify mock gateway chưa được gọi.

### Bài tập 5 — JWT ở hai lớp

Một test dùng `jwt().authorities(...)` cho thiếu `SCOPE_reports.read` → 403. Một test khác gửi `Authorization: Bearer malformed-test-token` qua `JwtDecoder` mock → 401. Phân biệt rõ authentication và authorization boundaries.

### Bài tập 6 — WebFlux và CI

Chuyển cặp admin 200/403 sang WebTestClient có `springSecurity()`. Gắn `@Tag("security-negative")` vào ca P0. Cho CI chạy ca này trước khi merge. Thử loại bỏ rule admin trên một nhánh thực hành: test nào phải fail?

### Tài liệu tham khảo

- [Spring Security — MockMvc Test Support](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html)
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [JUnit 5 — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests)

**Kết luận:** Một security test suite đáng tin không chỉ hỏi “người được phép có nhận 200 không?” mà còn chứng minh **người chưa đăng nhập, thiếu quyền hoặc truy cập sai dữ liệu bị từ chối đúng**, không làm phát sinh side effect. Ca phủ định cần positive control, tiền điều kiện chính xác, assertions ở đúng tầng và dữ liệu cô lập. Đưa các bất biến quan trọng vào **CI bắt buộc** để việc thay đổi code về sau không vô tình mở rộng quyền truy cập.



