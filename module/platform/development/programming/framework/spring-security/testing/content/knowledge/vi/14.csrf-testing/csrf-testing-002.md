# Ca không có token, token hợp lệ và token không hợp lệ

Khi kiểm thử CSRF trong **Spring Security Testing**, ba ca nền tảng cần đi cùng nhau là **không gửi CSRF token**, **gửi CSRF token hợp lệ** và **gửi CSRF token không hợp lệ**. Chúng chứng minh hai chiều của cơ chế bảo vệ: server từ chối yêu cầu thay đổi trạng thái không có bằng chứng CSRF hợp lệ, đồng thời cho phép yêu cầu có token đúng đi tiếp tới bước xác thực, phân quyền và xử lý nghiệp vụ.

Trong module này, ta sử dụng `spring-security-test` để kiểm chứng hành vi HTTP với **MockMvc trên Servlet** và **WebTestClient trên Reactive**. Danh tính giả lập (`@WithMockUser`, `mockUser()`, `jwt()`, `oauth2Login()`...) phục vụ một mục tiêu khác với CSRF token: *được xác thực* không đồng nghĩa với *đã vượt qua kiểm tra CSRF*.

## 1. Ba ca thử thực sự chứng minh điều gì?

Giả sử `POST /demo/change-email` được xử lý bởi một security chain **bật CSRF**, matcher yêu cầu token với `POST`, endpoint có tồn tại và tài khoản thử nghiệm có quyền cập nhật.

| Ca thử | Trạng thái token gửi kèm | Kết quả CSRF kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- |
| Không có token | Không có form parameter hoặc header chứa CSRF token | Từ chối, thông thường **403 Forbidden** | Request thuộc diện bảo vệ không được đi qua khi thiếu token. |
| Token hợp lệ | Có token khớp với giá trị mong đợi trong ngữ cảnh request/session | Đi qua bước kiểm tra CSRF | Sau đó vẫn phải qua phân quyền và xử lý nghiệp vụ; ví dụ trả **204 No Content** khi cập nhật thành công. |
| Token không hợp lệ | Có token nhưng sai giá trị, không khớp token mong đợi hoặc không dùng đúng ngữ cảnh | Từ chối, thông thường **403 Forbidden** | Chỉ có sự hiện diện của một chuỗi trong header/parameter là chưa đủ. |

Mã trạng thái trên mô tả tình huống kiểm thử chuẩn với `CsrfFilter`/bộ xử lý từ chối mặc định của Spring Security. Ứng dụng có thể tùy chỉnh cách xử lý lỗi. Khi đó, hãy kiểm chứng thêm response hoặc hành vi cụ thể của dự án, và xác minh rằng controller/service không thực hiện thay đổi dữ liệu.

Điểm dễ nhầm nhất là **403 không tự chứng minh nguyên nhân là CSRF**. Request còn có thể bị từ chối do thiếu quyền, thiếu đăng nhập hoặc một filter khác. Vì vậy, ba ca thử cần dùng **cùng HTTP method, path, quyền truy cập và dữ liệu đầu vào**; chỉ thay đổi trạng thái của CSRF token. Nếu ca token hợp lệ thành công trong cùng điều kiện, hai ca âm tính mới là bằng chứng đối chứng đáng tin cậy.

## 2. Tiền đề: môi trường kiểm thử phải thực sự bật CSRF

Ví dụ Servlet sau có endpoint trả `204` khi cập nhật thành công. Chính sách yêu cầu người dùng đăng nhập và giữ CSRF bật theo cấu hình mặc định.

```java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/demo/change-email").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}

@RestController
class DemoProfileController {

    @PostMapping("/demo/change-email")
    ResponseEntity<Void> changeEmail() {
        // Trong ứng dụng thật: kiểm tra input và lưu thay đổi.
        return ResponseEntity.noContent().build();
    }
}
```

Để mã kiểm thử phản ánh cấu hình trên, giả định các bean này nằm trong ứng dụng được nạp bởi `@SpringBootTest` và `MockMvc` có đăng ký các filter bảo mật thông qua `@AutoConfigureMockMvc`. Ví dụ lược bỏ `import` của phần cấu hình/controller cho dễ đọc.

Trước khi thử, xác nhận bốn điều kiện:

1. `POST /demo/change-email` khớp `SecurityFilterChain` có CSRF bật; nó không nằm trong `ignoringRequestMatchers(...)` hoặc matcher miễn trừ.
2. `POST` là method cần token trong cấu hình này. Mặc định Spring Security miễn CSRF cho `GET`, `HEAD`, `OPTIONS`, `TRACE`, nhưng yêu cầu cho các method còn lại.
3. Người dùng thử nghiệm đã đăng nhập và có quyền thực hiện thao tác. `@WithMockUser` giúp giữ điều kiện này cố định.
4. Endpoint trả trạng thái thành công xác định, ở đây là `204`, để phân biệt request đã qua bảo mật với request bị filter chặn.

Nếu CSRF đã bị tắt hoặc endpoint được miễn CSRF, một request không có token có thể đi tiếp bình thường. Khi đó, `403` không phải là kỳ vọng đúng; cần điều chỉnh bài kiểm thử dựa trên chính sách thật.

## 3. Servlet: ba ca đối chứng với MockMvc

Trong test dependency phải có `spring-security-test`. Với Maven, dependency tương ứng là:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với Gradle:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

Kiểm thử sau sử dụng các request post-processor của Spring Security:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfTokenCasesTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void withoutToken_isForbidden() throws Exception {
        mvc.perform(post("/demo/change-email"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void withValidToken_succeeds() throws Exception {
        mvc.perform(post("/demo/change-email").with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void withInvalidToken_isForbidden() throws Exception {
        mvc.perform(post("/demo/change-email")
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }
}
```

### Ca A — Không có token

```java
mvc.perform(post("/demo/change-email"))
    .andExpect(status().isForbidden());
```

Request có người dùng giả lập nhờ `@WithMockUser` nhưng **không có** `_csrf` hoặc CSRF header. `CsrfFilter` kiểm tra matcher, tìm token trong request và từ chối khi không tìm được giá trị hợp lệ.

Trong một bài thử khác, nếu cố tình không tạo người dùng đăng nhập, ứng dụng có thể trả `401` hoặc redirect đăng nhập, tùy entry point và thứ tự xử lý. Điều đó khiến nguyên nhân thất bại khó phân biệt hơn. Hãy cố định danh tính khi cần tập trung vào cơ chế CSRF.

### Ca B — Token hợp lệ

```java
mvc.perform(post("/demo/change-email").with(csrf()))
    .andExpect(status().isNoContent());
```

`csrf()` tạo/gắn token phù hợp với cơ chế kiểm thử của Spring Security Test. Khi request có token hợp lệ, bộ lọc CSRF cho đi tiếp. `204` đến từ controller minh họa; `csrf()` **không tự trả về `204`** và không bảo đảm người dùng đủ quyền. Nếu authorization rule là `hasRole("ADMIN")` mà mock user chỉ có `USER`, request mang token hợp lệ vẫn có thể trả `403` do phân quyền.

Đây là ca quan trọng để đối chiếu: nó xác nhận endpoint tồn tại, được gọi bằng cùng method và danh tính, đồng thời có thể chạy sau khi vượt qua CSRF. Trong ứng dụng thật, nên kiểm tra thêm thay đổi dữ liệu hoặc lần gọi service dự kiến.

### Ca C — Token không hợp lệ

```java
mvc.perform(post("/demo/change-email")
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
```

`csrf().useInvalidToken()` chủ động gửi token sai. Ca này mô phỏng request **có dữ liệu giống CSRF token nhưng không hợp lệ**; nó khác với ca không gửi token. Nó kiểm chứng rằng server không chỉ kiểm tra sự hiện diện của header/parameter.

Không cần tự chọn một chuỗi ngẫu nhiên rồi đoán tên CSRF header để viết ca âm tính cho MockMvc; post-processor trên xử lý phần chuẩn bị request giúp test có mục đích rõ ràng.

## 4. Gửi token bằng parameter và header

Mặc định, `csrf()` của MockMvc gắn token dưới dạng request parameter. Có thể thử luồng gửi header bằng `asHeader()`:

```java
@Test
@WithMockUser
void validHeader_isAccepted() throws Exception {
    mvc.perform(post("/demo/change-email")
            .with(csrf().asHeader()))
        .andExpect(status().isNoContent());
}

@Test
@WithMockUser
void invalidHeader_isRejected() throws Exception {
    mvc.perform(post("/demo/change-email")
            .with(csrf().asHeader().useInvalidToken()))
        .andExpect(status().isForbidden());
}
```

Trên ứng dụng web, form HTML thường gửi CSRF token qua hidden input, còn JavaScript client thường gửi qua header. Hai cách này không làm thay đổi điều kiện *token phải khớp giá trị mà server mong đợi*. Tên parameter/header và việc lưu token phụ thuộc `CsrfTokenRepository` và cấu hình request handler: ví dụ `HttpSessionCsrfTokenRepository` và `CookieCsrfTokenRepository` không có cùng mô hình lưu trữ.

Các post-processor phục vụ **kiểm thử phía server**. Chúng không thay thế phép thử trình duyệt thực sự lấy token từ server, lưu cookie/session, rồi gửi token trong request tiếp theo. Với giao diện dùng cookie `XSRF-TOKEN`, header `X-XSRF-TOKEN` có thể cần xử lý tương ứng; không nên giả định sao chép giá trị cookie sang header luôn hoạt động trong mọi cách cấu hình Spring Security, nhất là khi request handler có cơ chế mã hóa/giải mã giá trị token.

## 5. Kiểm thử qua HTTP thực: giữ đúng phiên và thay đổi một biến

Khi kiểm thử qua HTTP, Playwright, RestAssured, hoặc một `WebTestClient` kết nối tới server thật, cần mô phỏng đủ quy trình cấp token để khẳng định trường hợp **sai token** một cách chính xác.

Ví dụ ứng dụng có một trang/form hoặc endpoint cung cấp token CSRF, và người dùng đăng nhập bằng session cookie:

1. Đăng nhập hoặc tạo session theo cách ứng dụng hỗ trợ; giữ cookie jar.
2. Gọi trang/form hoặc endpoint hợp lệ để lấy CSRF token của **chính session đó**. Lưu token và cookie.
3. Gửi `POST` với cookie/session đã xác thực nhưng **không gửi** CSRF token: kỳ vọng bị từ chối.
4. Gửi `POST` với cùng ngữ cảnh, gửi **token thật** bằng parameter/header được cấu hình: kỳ vọng request vượt qua CSRF và đi tới controller.
5. Gửi `POST` với cùng ngữ cảnh, gửi **token đã bị thay đổi** (ví dụ thay một ký tự) bằng đúng tên parameter/header: kỳ vọng bị từ chối.

Nếu ứng dụng thay/rotate token trong một số tình huống, cần lấy lại token trước phép thử tương ứng. Không sử dụng token từ phiên A để chứng minh luồng hợp lệ của phiên B. Trường hợp khác phiên có thể là một **ca âm tính bổ sung**, nhưng không nên trộn vào phép đối chứng sai giá trị token.

Một bộ request minh họa về mặt ý tưởng:

```text
Session đã đăng nhập: Cookie: SESSION=<cùng-một-phiên>
Token thực tế đã lấy từ ứng dụng: <valid-csrf-token>

A. POST /demo/change-email
   Cookie: SESSION=<cùng-một-phiên>
   [không có header/parameter CSRF]       -> bị từ chối

B. POST /demo/change-email
   Cookie: SESSION=<cùng-một-phiên>
   X-CSRF-TOKEN: <valid-csrf-token>      -> đi tiếp

C. POST /demo/change-email
   Cookie: SESSION=<cùng-một-phiên>
   X-CSRF-TOKEN: <altered-csrf-token>    -> bị từ chối
```

Tên cookie, tên header và cách lấy token trong ví dụ là ký hiệu minh họa; khi chạy phải thay bằng cấu hình thực tế. Nếu endpoint dùng `Authorization: Bearer ...` thì vẫn phải kiểm tra CSRF có bật trong chain hay không; việc sử dụng JWT/OAuth2/OIDC không tự động khẳng định CSRF bị tắt.

## 6. Reactive: đối chứng với WebTestClient

Ứng dụng WebFlux sử dụng `SecurityWebFilterChain` và `ServerHttpSecurity`. Trong phép thử bind trực tiếp tới Spring application context, `SecurityMockServerConfigurers.springSecurity()` gắn phần xử lý bảo mật, `mockUser()` giả lập danh tính, còn `csrf()` gắn token hợp lệ.

Giả sử ứng dụng **Reactive** có cùng đường dẫn `POST /demo/change-email`, chain bật CSRF và controller trả `204`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveCsrfTokenCasesTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void missingToken_isForbidden() {
        client.mutateWith(mockUser("alice"))
            .post().uri("/demo/change-email")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validToken_succeeds() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/demo/change-email")
            .exchange()
            .expectStatus().isNoContent();
    }
}
```

Khi cần kiểm thử **token sai trên WebFlux**, nên thực hiện một ca kiểm thử với repository và session thực tế của ứng dụng: lấy token do ứng dụng cấp cho phiên hiện tại, gửi request với cùng session nhưng thay giá trị token trong đúng header/parameter, rồi xác minh request bị từ chối. Cách này làm rõ trường hợp *sai giá trị* thay vì vô tình chỉ kiểm tra *chưa từng có token*. Các helper của Servlet như `csrf().useInvalidToken()` trong `SecurityMockMvcRequestPostProcessors` không được dùng cho `WebTestClient`; hai bộ công cụ có API khác nhau.

Nếu WebTestClient kết nối qua HTTP đến một server đang chạy thay vì bind tới application context, không nên giả định `mutateWith(csrf())` tự cung cấp được toàn bộ quy trình cookie/session và lấy token cho trình duyệt. Hãy kiểm thử theo luồng HTTP thực trong mục trước.

## 7. Khi kết quả khác kỳ vọng: xác định nguyên nhân trước khi sửa test

| Hiện tượng | Khả năng cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| Không có token mà nhận `204` | CSRF bị tắt, request không khớp matcher CSRF, chain khác được chọn hoặc filter không chạy trong test | Kiểm tra `SecurityFilterChain`/`SecurityWebFilterChain`, `csrf.disable()`, matcher và cách dựng client. |
| Không có token mà nhận `401` hoặc redirect | Request chưa được xác thực, hoặc cơ chế entry point can thiệp | Cố định danh tính bằng `@WithMockUser`/`mockUser()`; xác minh thứ tự filter và mã trạng thái trong ứng dụng thật. |
| Có token hợp lệ nhưng vẫn `403` | Thiếu quyền, token không khớp session/repository, mismatch header/parameter hoặc rule khác từ chối | Kiểm tra quyền user, session, tên trường, token repository và security filter chain. |
| Token sai vẫn được chấp nhận | Endpoint được miễn CSRF; request đến chain khác; test bỏ qua security filter | Thử cùng request thiếu token, kiểm tra ngoại lệ, `@AutoConfigureMockMvc` và cấu hình security. |
| Kiểm thử MockMvc luôn cho `200/204` dù không có token | Đã dùng `standaloneSetup` không gắn Spring Security, hoặc `addFilters = false` | Dùng cấu hình MockMvc có `springSecurity()` hoặc integration test nạp filter thật. |
| Các ca fail ngẫu nhiên theo thứ tự chạy | Trộn session/token giữa các test, phụ thuộc dữ liệu chung hoặc có rotate token | Tạo ngữ cảnh riêng cho từng test; giữ cookie/token đồng bộ và reset dữ liệu phù hợp. |

Đối với một ứng dụng có nhiều chain, hãy kiểm tra chain **được chọn cho chính request đang thử**. Endpoint `/api/**` có thể có chính sách CSRF khác `/web/**`; việc gọi `csrf.disable()` trong một chain không nói gì về chain còn lại. Với request dùng `permitAll()`, chỉ quy tắc **phân quyền** được nới; CSRF vẫn có thể yêu cầu token.

## 8. Nâng chất lượng phép thử: bảo vệ dữ liệu, không chỉ so mã trạng thái

Một bộ test đáng tin cậy thường xác minh thêm rằng **request bị từ chối không tạo tác dụng phụ**. Ví dụ với chức năng đổi email:

- Ghi nhận email ban đầu của tài khoản thử nghiệm.
- Gửi request không có token rồi đọc lại email: phải giữ nguyên.
- Gửi request có token sai rồi đọc lại email: phải giữ nguyên.
- Gửi request có token hợp lệ, đủ quyền và input hợp lệ rồi đọc lại email: phải thay đổi đúng như mong đợi.

Nếu viết unit/integration test với service giả lập, có thể dùng Mockito để xác minh service **không được gọi** ở hai ca âm tính và **được gọi đúng một lần** ở ca dương tính; với test tích hợp thật, ưu tiên kiểm tra trạng thái dữ liệu. Điều này bảo vệ khỏi trường hợp controller đã xử lý một phần thao tác rồi hệ thống mới trả response lỗi.

Ngoài bộ ba chính, nên bổ sung các biến thể có ý nghĩa đối với cấu hình cụ thể:

| Biến thể | Mục tiêu |
| --- | --- |
| Valid token trong header và valid token trong form parameter | Xác nhận các đường gửi token mà ứng dụng thực sự hỗ trợ. |
| Token thuộc phiên khác | Phát hiện việc chấp nhận token sai ngữ cảnh session. |
| Token bị thiếu nhưng request dùng method an toàn `GET` | Chứng minh `GET` không bị CSRF chặn theo matcher mặc định, nếu endpoint có handler GET. |
| Token hợp lệ nhưng người dùng thiếu quyền | Xác minh CSRF và phân quyền là hai lớp kiểm tra độc lập. |
| `POST` đến endpoint cố ý miễn CSRF | Xác minh ngoại lệ khớp đúng path; vẫn kiểm tra xác thực webhook/signature hoặc cơ chế bảo vệ phù hợp khác. |
| Gửi token sai trên request có JWT/OAuth2/OIDC giả lập | Xác minh CSRF theo cấu hình chain thực tế, không suy ra kết quả chỉ từ loại authentication. |

Với `jwt()`, `oauth2Login()`, `oidcLogin()` hay `@WithMockUser`, quy tắc vẫn là: **authentication mutator tạo ngữ cảnh xác thực; CSRF token phải được cung cấp riêng nếu chain yêu cầu**. Ứng dụng có thể thiết kế các API Bearer token không cần CSRF vì không dựa vào credential do trình duyệt tự gửi, nhưng phải nhìn vào cấu hình thật và mô hình nguy cơ thực tế trước khi đưa ra kỳ vọng cho test.

## 9. Bài luyện tập tự kiểm tra

Một ứng dụng Servlet có `POST /account/avatar`, `POST /integrations/webhook` và `GET /account/avatar`. CSRF bật mặc định, riêng `/integrations/webhook` được khai báo trong `ignoringRequestMatchers`. Endpoint avatar yêu cầu đăng nhập.

Hãy dự đoán kết quả của năm request sau **khi đã có handler tương ứng**:

1. Người dùng đăng nhập, `POST /account/avatar`, không có token.
2. Người dùng đăng nhập, `POST /account/avatar`, `.with(csrf())`.
3. Người dùng đăng nhập, `POST /account/avatar`, `.with(csrf().useInvalidToken())`.
4. Người dùng đăng nhập, `GET /account/avatar`, không có token.
5. `POST /integrations/webhook`, không có token nhưng được phép truy cập theo cấu hình phân quyền.

**Đáp án:** (1) bị CSRF từ chối; (2) vượt qua CSRF và đi tiếp đến xử lý avatar; (3) bị CSRF từ chối; (4) không cần CSRF token theo matcher mặc định; (5) không bị CSRF chặn do ngoại lệ đã cấu hình. Chỉ có thể khẳng định trạng thái HTTP thành công cụ thể ở các ca (2), (4), (5) sau khi biết thêm controller và các chính sách khác.

## Ghi nhớ

Ba ca **thiếu token – token hợp lệ – token sai** tạo thành bộ đối chứng tối thiểu để chứng minh CSRF đang hoạt động trên một endpoint cụ thể. Giữ nguyên method, path, danh tính, quyền và session khi so sánh; dùng `csrf()`/`csrf().useInvalidToken()` của MockMvc hoặc `csrf()` của WebTestClient đúng theo loại ứng dụng; kiểm tra cả kết quả HTTP lẫn tác dụng phụ. Khi kết quả bất thường, bắt đầu từ chain, matcher, repository và cơ chế xác thực thực tế trước khi thay đổi kỳ vọng của test.
