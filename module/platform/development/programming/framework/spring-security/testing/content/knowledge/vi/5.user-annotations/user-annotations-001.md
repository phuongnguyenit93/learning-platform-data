# `@WithMockUser` ở phương thức và ở lớp kiểm thử

## 1. Mục tiêu và phạm vi

Khi kiểm thử Spring Security, nhiều tình huống cần trả lời một câu hỏi cụ thể: **người dùng đã đăng nhập với một tập quyền nhất định có được phép gọi chức năng này không?** Việc thực hiện luồng đăng nhập thật cho mọi ca kiểm thử sẽ khiến bài test dài, khó cô lập và phụ thuộc vào cơ sở dữ liệu hoặc nhà cung cấp danh tính. `@WithMockUser`, thuộc thư viện `spring-security-test`, tạo một người dùng đã xác thực trong ngữ cảnh bảo mật của bài test, giúp tập trung kiểm chứng **phân quyền**.

Trong module **SPRING_SECURITY_TESTING**, kỹ thuật này là nền tảng để kiểm chứng HTTP trên ứng dụng Servlet với `MockMvc` và trên ứng dụng Reactive với `WebTestClient`. Bài học tập trung vào hai vị trí đặt annotation: **trên từng phương thức kiểm thử** và **trên lớp kiểm thử**; đồng thời giải thích cách cấu hình được kế thừa, ghi đè và sử dụng trong các ca được phép/bị từ chối.

Sau bài học, bạn có thể:

- Tạo danh tính giả lập bằng `@WithMockUser` mà không cần gửi thông tin đăng nhập.
- Chọn phạm vi áp dụng cho một phương thức hoặc toàn bộ lớp kiểm thử.
- Phân biệt `roles` và `authorities` để kiểm tra đúng quy tắc `hasRole`/`hasAuthority`.
- Viết các ca `200`/`204`, `401` và `403` có ý nghĩa, đồng thời tránh nhầm lỗi CSRF với lỗi phân quyền.
- Biết lúc nào cần chuyển sang kiểm thử JWT, OAuth2/OIDC hoặc quá trình xác thực thực tế.

## 2. `@WithMockUser` thực sự làm gì?

`@WithMockUser` được xử lý bởi hạ tầng Spring Test và `WithSecurityContextTestExecutionListener`. Trước khi thực thi bài test, listener tạo một `SecurityContext` chứa `Authentication` đã được đánh dấu xác thực. Với annotation này, đối tượng xác thực thông thường là `UsernamePasswordAuthenticationToken`; principal là một `org.springframework.security.core.userdetails.User` được tạo cho bài test.

Ví dụ:

```java
@Test
@WithMockUser(username = "linh", roles = "READER")
void contextContainsReader() {
    Authentication authentication = SecurityContextHolder.getContext()
            .getAuthentication();

    assertThat(authentication.isAuthenticated()).isTrue();
    assertThat(authentication.getName()).isEqualTo("linh");
    assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("ROLE_READER");
}
```

Các kiểu và phương thức liên quan trong ví dụ là `Authentication`, `GrantedAuthority`, `SecurityContextHolder` của Spring Security và `assertThat` của AssertJ. Để annotation có hiệu lực, bài test phải chạy với hạ tầng Spring Test, chẳng hạn `@SpringBootTest`, `@WebMvcTest`, `@WebFluxTest` hoặc `@ExtendWith(SpringExtension.class)` với cấu hình thích hợp.

Điều cần phân biệt: **đây là người dùng được dựng sẵn để kiểm thử**. Annotation không gọi `UserDetailsService`, không kiểm tra mật khẩu, không trao đổi token với nhà cung cấp OAuth2 và không chứng minh cơ chế đăng nhập hoạt động. Nó phù hợp khi đối tượng cần kiểm chứng là hành vi của ứng dụng *sau khi* đã có danh tính và quyền truy cập.

### Các thuộc tính cần nhớ

| Cách khai báo | Ý nghĩa | Kết quả điển hình |
| --- | --- | --- |
| `@WithMockUser` | Dùng các giá trị mặc định | Tên `user`, mật khẩu giả `password`, quyền `ROLE_USER` |
| `@WithMockUser("mai")` | Đặt tên người dùng qua `value` | `authentication.getName()` là `mai` |
| `@WithMockUser(username = "mai")` | Đặt tên bằng thuộc tính tường minh | Tương đương dùng `value = "mai"` |
| `@WithMockUser(roles = "ADMIN")` | Khai báo vai trò, tự thêm tiền tố `ROLE_` | Authority `ROLE_ADMIN` |
| `@WithMockUser(roles = {"READER", "EDITOR"})` | Khai báo nhiều vai trò | `ROLE_READER`, `ROLE_EDITOR` |
| `@WithMockUser(authorities = "document:read")` | Khai báo trực tiếp authority | Chính xác `document:read` |
| `@WithMockUser(password = "test-password")` | Đặt mật khẩu cho principal giả | Không thực hiện xác thực mật khẩu |

Hai quy tắc dễ nhầm:

1. Với `roles`, hãy viết `"ADMIN"`, **không** viết `"ROLE_ADMIN"`; Spring Security sẽ thêm `ROLE_` và từ chối tên role vốn đã có tiền tố đó.
2. Khi khai báo `authorities`, Spring sử dụng danh sách authority tường minh thay vì chuyển `roles` thành authority. Ví dụ `authorities = "ADMIN"` **không** thỏa mãn `hasRole("ADMIN")` vì quy tắc này thường tìm `ROLE_ADMIN`.

```java
@WithMockUser(roles = "ADMIN")
// Phù hợp với: .hasRole("ADMIN") hoặc @PreAuthorize("hasRole('ADMIN')")

@WithMockUser(authorities = "document:publish")
// Phù hợp với: .hasAuthority("document:publish")
// hoặc @PreAuthorize("hasAuthority('document:publish')")
```

## 3. Đặt annotation trên phương thức kiểm thử

Khi mỗi ca kiểm thử cần một danh tính khác nhau, đặt `@WithMockUser` ngay trên `@Test` giúp người đọc biết rõ **ai đang gọi** và **được cấp quyền gì**. Các thông tin này chỉ áp dụng cho ca kiểm thử tương ứng; Spring Test dọn `SecurityContext` khi kết thúc để tránh rò rỉ sang ca khác.

```java
@Test
@WithMockUser(username = "an", roles = "READER")
void readerCanViewDocument() throws Exception {
    mockMvc.perform(get("/documents/42"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(username = "binh", roles = "ADMIN")
void adminCanPublishDocument() throws Exception {
    mockMvc.perform(post("/documents/42/publish").with(csrf()))
            .andExpect(status().isNoContent());
}
```

Đoạn trên giả định ứng dụng có hai endpoint và cấu hình `SecurityFilterChain` tương ứng: `GET /documents/{id}` cho `READER`, `POST /documents/{id}/publish` cho `ADMIN`. Để thấy đầy đủ cấu hình và kết quả của các ca bị từ chối, hãy xem ví dụ chạy xuyên suốt ở phần 5.

## 4. Đặt annotation trên lớp kiểm thử

Nếu phần lớn phương thức cùng cần một người dùng mặc định, có thể đặt `@WithMockUser` ngay trên lớp. Mỗi phương thức sẽ nhận ngữ cảnh bảo mật tương ứng **khi thực thi**; các bài test không chia sẻ cùng một phiên đăng nhập thật.

```java
@WithMockUser(username = "linh", roles = "READER")
class DocumentAccessTest {

    @Test
    void readerCanView() {
        // Dùng người dùng linh với authority ROLE_READER.
    }

    @Test
    @WithMockUser(username = "quynh", roles = "ADMIN")
    void adminCanPublish() {
        // Annotation ở phương thức ghi đè annotation ở lớp.
    }

    @Test
    @WithAnonymousUser
    void guestCannotView() {
        // Ghi đè bằng ngữ cảnh người dùng ẩn danh.
    }
}
```

Quy tắc chọn danh tính là:

| Trên lớp | Trên phương thức | Danh tính dùng cho phương thức |
| --- | --- | --- |
| `@WithMockUser(roles = "READER")` | Không có annotation riêng | Người dùng `READER` của lớp |
| `@WithMockUser(roles = "READER")` | `@WithMockUser(roles = "ADMIN")` | Người dùng `ADMIN` của phương thức |
| `@WithMockUser(roles = "READER")` | `@WithAnonymousUser` | Người dùng ẩn danh |
| Không có annotation trên lớp | `@WithMockUser(roles = "ADMIN")` | Người dùng `ADMIN` của phương thức |

Điểm quan trọng là **annotation ở phương thức thay thế cấu hình của lớp**, không cộng dồn roles. Ví dụ, phương thức khai báo `roles = "ADMIN"` chỉ nhận `ROLE_ADMIN` từ annotation đó, không tự nhận thêm `ROLE_READER` từ lớp. Nếu muốn cả hai, khai báo rõ `roles = {"READER", "ADMIN"}`.

Với một lớp có mặc định `@WithMockUser`, chỉ bỏ annotation khỏi phương thức **không thể** tạo ca kiểm thử chưa đăng nhập. Hãy dùng `@WithAnonymousUser` cho ca âm tính hoặc tách ca không có đăng nhập sang lớp không đặt `@WithMockUser`.

## 5. Ví dụ hoàn chỉnh: kiểm chứng phân quyền HTTP bằng `MockMvc`

Giả sử yêu cầu nghiệp vụ là: người mang role `READER` được đọc tài liệu; chỉ `ADMIN` được xuất bản tài liệu; khách chưa xác thực không được đọc. Ta cần kiểm chứng cả **HTTP status thực tế** và các lớp bảo vệ liên quan, thay vì chỉ kiểm tra một lời gọi service.

### 5.1. Các phụ thuộc kiểm thử

Một dự án Spring Boot dùng Spring MVC, Spring Security, JUnit 5 và `MockMvc` cần thư viện kiểm thử Spring Security. Ví dụ với Gradle (để Spring Boot quản lý phiên bản):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Với Maven, thêm `org.springframework.security:spring-security-test` có `scope` là `test` vào dự án đã có các starter tương ứng. Tên starter web có thể khác theo thế hệ Spring Boot, nhưng tọa độ thư viện `spring-security-test` vẫn là phần cốt lõi của ví dụ.

### 5.2. Endpoint và quy tắc bảo mật

Các đoạn dưới đây giả định lớp controller, lớp cấu hình bảo mật và lớp test cùng thuộc một package trong dự án Spring Boot. Có thể tách thành các file Java cùng tên lớp; các `import` tiêu chuẩn được liệt kê ở mỗi khối.

```java
// DocumentController.java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/documents")
class DocumentController {

    @GetMapping("/{id}")
    String getDocument(@PathVariable long id) {
        return "document-" + id;
    }

    @PostMapping("/{id}/publish")
    ResponseEntity<Void> publishDocument(@PathVariable long id) {
        return ResponseEntity.noContent().build();
    }
}
```

```java
// DocumentSecurityConfig.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentSecurityConfig {

    @Bean
    SecurityFilterChain documentFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/documents/{id}")
                    .hasAnyRole("READER", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/documents/{id}/publish")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        // Không tắt CSRF: POST phải có token CSRF hợp lệ.
        return http.build();
    }
}
```

Ở đây phương thức `GET` cho phép cả `READER` lẫn `ADMIN`; phương thức `POST` chỉ cho `ADMIN`. `httpBasic()` cho phép trả `401 Unauthorized` khi khách chưa đăng nhập yêu cầu tài nguyên bảo vệ. Nếu ứng dụng dùng cơ chế đăng nhập khác, ví dụ form login, phản hồi cho khách chưa xác thực có thể là chuyển hướng thay vì `401`.

### 5.3. Kiểm thử quyền ở lớp và ghi đè ở phương thức

```java
// DocumentControllerSecurityTest.java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DocumentController.class)
@Import(DocumentSecurityConfig.class)
@WithMockUser(username = "reader01", roles = "READER")
class DocumentControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerCanGetDocument_usingClassAnnotation() throws Exception {
        mockMvc.perform(get("/documents/42"))
                .andExpect(status().isOk())
                .andExpect(content().string("document-42"))
                .andExpect(authenticated().withUsername("reader01"));
    }

    @Test
    void readerCannotPublish_evenWithValidCsrf() throws Exception {
        mockMvc.perform(post("/documents/42/publish").with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin01", roles = "ADMIN")
    void adminCanPublish_usingMethodOverride() throws Exception {
        mockMvc.perform(post("/documents/42/publish").with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotGetDocument() throws Exception {
        mockMvc.perform(get("/documents/42"))
                .andExpect(status().isUnauthorized());
    }
}
```

`@WebMvcTest` tạo ngữ cảnh kiểm thử MVC, `@Import(DocumentSecurityConfig.class)` nạp chính sách HTTP đang được kiểm chứng và `MockMvc` thực thi request qua hệ thống filter được tích hợp Spring Security. Việc dùng `@WithMockUser` ở lớp áp dụng cho hai ca đầu; annotation ở hai phương thức sau ghi đè để mô phỏng quản trị viên và khách ẩn danh.

| Ca kiểm thử | Danh tính hiệu lực | Hành động | Kết quả cần thấy |
| --- | --- | --- | --- |
| `readerCanGetDocument` | `reader01`, `ROLE_READER` | `GET /documents/42` | `200 OK` và nội dung tài liệu |
| `readerCannotPublish` | `reader01`, `ROLE_READER` | `POST /documents/42/publish` với CSRF | `403 Forbidden` |
| `adminCanPublish` | `admin01`, `ROLE_ADMIN` | `POST /documents/42/publish` với CSRF | `204 No Content` |
| `anonymousCannotGetDocument` | Ẩn danh | `GET /documents/42` | `401 Unauthorized` trong cấu hình HTTP Basic này |

**Vì sao phải gọi `.with(csrf())` ở hai ca POST?** Khi CSRF đang bật, request POST thiếu token có thể bị từ chối `403` **trước khi** việc kiểm tra role thể hiện đúng hành vi mong muốn. Trong ca `readerCannotPublish`, việc cung cấp CSRF hợp lệ giúp kết quả `403` có ý nghĩa phân quyền. Trong ca `adminCanPublish`, CSRF hợp lệ là một phần điều kiện để request được phép thực hiện. `@WithMockUser` **không tự tạo CSRF token**.

Nếu cấu hình test bỏ các security filter (ví dụ tắt filter của `MockMvc`) hoặc dùng một `SecurityFilterChain` khác production, các kết quả có thể đánh lừa. Hãy bảo đảm chính sách cần kiểm thử thực sự được nạp và xử lý trong request.

## 6. Thứ tự thiết lập `SecurityContext` và vòng đời kiểm thử

Mặc định, `@WithMockUser` thiết lập `SecurityContext` ở thời điểm `TEST_METHOD`, tức là trước bước chạy phương thức test của Spring Test. Với JUnit 5 và `SpringExtension`, điều này thường cho phép đọc context trong `@BeforeEach`. Trong trường hợp muốn lùi thời điểm thiết lập đến ngay trước khi thân `@Test` bắt đầu, dùng `setupBefore = TestExecutionEvent.TEST_EXECUTION`:

```java
import org.springframework.security.test.context.support.TestExecutionEvent;

@Test
@WithMockUser(
        username = "admin01",
        roles = "ADMIN",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
)
void testWithContextSetJustBeforeExecution() {
    // SecurityContext được thiết lập sau giai đoạn @BeforeEach.
}
```

Chọn mặc định trong phần lớn tình huống. Chỉ đổi `setupBefore` khi logic thiết lập fixture có nhu cầu cụ thể về thời điểm người dùng xuất hiện. Nếu code được kiểm thử chuyển sang thread khác, `SecurityContext` dựa trên `ThreadLocal` không tự bảo đảm được truyền sang thread đó; cần cấu hình chiến lược truyền context phù hợp thay vì cho rằng annotation áp dụng toàn bộ thread bất đồng bộ.

## 7. Liên hệ với `WebTestClient` trong ứng dụng Reactive

Với Spring WebFlux, `@WithMockUser` vẫn có thể đặt trên phương thức hoặc lớp. Hạ tầng `spring-security-test` phối hợp với `ReactorContextTestExecutionListener` để đưa danh tính kiểm thử vào Reactor Context, nơi Spring Security Reactive lấy thông tin xác thực. Khi kiểm thử HTTP bằng `WebTestClient`, cần cấu hình client và security chain Reactive để request thực sự đi qua cơ chế bảo vệ.

```java
@WebFluxTest(ReactiveDocumentController.class)
@Import(ReactiveDocumentSecurityConfig.class)
@WithMockUser(roles = "READER")
class ReactiveDocumentSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanViewDocument() {
        webTestClient.get().uri("/documents/42")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Đây là **phác thảo cấu trúc test**: `ReactiveDocumentController` và `ReactiveDocumentSecurityConfig` là các lớp WebFlux của ứng dụng, cần được định nghĩa với `SecurityWebFilterChain` phù hợp. Khi cần dùng nhiều danh tính trong **cùng một phương thức**, có thể thay thế hoặc bổ sung bằng bộ cấu hình request của `WebTestClient`, chẳng hạn `mutateWith(mockUser("admin01").roles("ADMIN"))` trong môi trường đã tích hợp `springSecurity()`.

Điểm khác nhau nằm ở cách Spring Security mang context qua luồng thực thi (Servlet `SecurityContextHolder` so với Reactor Context). Quy tắc đặt `@WithMockUser` trên lớp, ghi đè ở phương thức, phân biệt `roles`/`authorities` và giới hạn mô phỏng danh tính vẫn giữ nguyên.

## 8. Khi nào cần công cụ khác?

| Mục đích kiểm thử | Công cụ gợi ý | Lý do |
| --- | --- | --- |
| Một người dùng giả cho hầu hết test trong lớp | `@WithMockUser` trên lớp | Giảm lặp và cho phép ghi đè từng phương thức |
| Mỗi test là một danh tính khác nhau | `@WithMockUser` trên phương thức | Ý đồ phân quyền rõ ngay tại chỗ |
| Kiểm tra truy cập khi chưa xác thực trong lớp đã có mặc định | `@WithAnonymousUser` trên phương thức | Ghi đè danh tính của lớp |
| Tạo người dùng qua `UserDetailsService` thật của ngữ cảnh test | `@WithUserDetails` | Dùng chi tiết người dùng được tải từ dịch vụ |
| Quyền hoặc principal có kiểu riêng | `@WithSecurityContext` | Tự xây dựng security context theo mô hình ứng dụng |
| Mỗi request `MockMvc` cần người dùng riêng | `.with(user("name").roles("ADMIN"))` | Cấu hình theo từng request |
| Kiểm chứng endpoint JWT/OAuth2/OIDC với token hoặc principal giả lập | `.with(jwt())`, `.with(oauth2Login())`, `.with(oidcLogin())` cùng các cấu hình phù hợp | Mô phỏng kiểu xác thực mà ứng dụng sử dụng |
| Kiểm tra việc đăng nhập, xác minh mật khẩu, chữ ký JWT, issuer/audience hoặc handshake OIDC | Test tích hợp chuyên biệt với bộ xác thực tương ứng | `@WithMockUser` không chạy các bước xác thực đó |

**Không dùng `@WithMockUser` làm bằng chứng rằng JWT hoặc đăng nhập thật hợp lệ.** Một endpoint được phép truy cập với principal mô phỏng chỉ chứng minh kết quả phân quyền trong bối cảnh đó; nó không chứng minh việc parse token, xác minh chữ ký, chuyển claim thành authority hay xử lý lỗi token của hệ thống.

## 9. Lỗi thường gặp và cách tự kiểm tra

1. **Đặt `roles = "ROLE_ADMIN"`**: bỏ tiền tố và dùng `roles = "ADMIN"`; hoặc khai báo chính xác `authorities = "ROLE_ADMIN"` nếu cần authority tường minh.
2. **Dùng `authorities = "ADMIN"` rồi kỳ vọng `hasRole("ADMIN")` thành công**: `hasRole` mặc định tìm `ROLE_ADMIN`, trong khi `authorities` không tự thêm tiền tố.
3. **Cho rằng annotation ở lớp và phương thức cộng quyền**: phương thức ghi đè lớp; liệt kê đủ các role cần thiết trong phương thức.
4. **Ca kiểm thử khách ẩn danh vẫn đăng nhập**: khi lớp có `@WithMockUser`, hãy ghi đè phương thức bằng `@WithAnonymousUser`.
5. **POST của quản trị viên trả `403`**: kiểm tra CSRF trước, sau đó mới xét role và cấu hình matcher; request cần `.with(csrf())` nếu CSRF được bật.
6. **Test trả `200` dù cấu hình bảo mật sai**: kiểm tra `SecurityFilterChain`/`SecurityWebFilterChain` đã được nạp và security filter thực sự chạy trong `MockMvc`/`WebTestClient`.
7. **Dùng `@WithMockUser` nhưng muốn lấy principal OAuth2 hoặc JWT**: annotation tạo principal dạng `User` thông thường, nên code yêu cầu `Jwt` hay `OidcUser` có thể không phù hợp. Chọn mock JWT/OAuth2/OIDC hoặc custom security context tương ứng.
8. **Annotation không có tác dụng với test thuần JUnit**: bổ sung tích hợp Spring Test và listener cần thiết, thông thường thông qua slice test hoặc `SpringExtension`.

## 10. Bài tập vận dụng

Cho API với chính sách: `GET /reports/{id}` cho `ANALYST` hoặc `ADMIN`; `DELETE /reports/{id}` chỉ cho `ADMIN`; yêu cầu CSRF khi dùng HTTP DELETE. Hãy tạo một lớp kiểm thử có `@WithMockUser(username = "analyst01", roles = "ANALYST")` và viết bốn ca:

1. Analyst đọc báo cáo: kỳ vọng `200`.
2. Analyst xóa báo cáo với token CSRF hợp lệ: kỳ vọng `403` vì thiếu role.
3. Ghi đè ở phương thức thành `@WithMockUser(roles = "ADMIN")` để xóa với CSRF: kỳ vọng phản hồi thành công theo hợp đồng API.
4. Ghi đè bằng `@WithAnonymousUser` và gọi `GET`: kiểm tra phản hồi chưa xác thực theo cơ chế đăng nhập của ứng dụng.

Sau đó thay role `ANALYST` bằng `authorities = "ANALYST"` trong một ca và giải thích vì sao `hasRole("ANALYST")` không còn khớp. Đây là phép thử trực tiếp để xác nhận bạn đã phân biệt **tên vai trò**, **authority thực tế**, **phạm vi annotation** và **tầng HTTP**.

### Ghi nhớ

`@WithMockUser` tạo danh tính *đã xác thực* phục vụ kiểm tra phân quyền; đặt ở lớp để dùng chung, ở phương thức để chỉ định hoặc ghi đè. `roles` sinh authority có tiền tố `ROLE_`, còn `authorities` dùng nguyên giá trị khai báo. Muốn kết luận một endpoint được bảo vệ đúng, hãy kiểm chứng cả ca được phép và bị từ chối thông qua security chain thật của ngữ cảnh test, đồng thời tách bạch phân quyền với CSRF và quá trình xác thực token/đăng nhập.
