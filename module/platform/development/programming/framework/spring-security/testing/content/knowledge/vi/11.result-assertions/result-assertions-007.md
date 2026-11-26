# Khẳng định Location, WWW-Authenticate và nội dung lỗi

## 1. Vì sao phải kiểm tra response headers và error body?

Một request bị từ chối có thể trả status đúng nhưng vẫn vi phạm hợp đồng HTTP mà client đang dựa vào. Ví dụ, API trả 401 nhưng thiếu header WWW-Authenticate để client biết cơ chế xác thực; form login trả 302 nhưng Location trỏ sai trang; hoặc API trả 403 nhưng body JSON không có mã lỗi mà frontend cần để hiển thị thông báo phù hợp.

Trong module **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên Servlet và Reactive. Chương **Khẳng định kết quả** tập trung vào bằng chứng sau request. Bài này hướng dẫn cách kiểm tra ba nhóm thông tin của response trong Spring MVC với MockMvc:

- **Location**: đích chuyển hướng sau khi chưa đăng nhập, đăng nhập thành công/thất bại, hoặc URI của tài nguyên mới được tạo.
- **WWW-Authenticate**: challenge cho client khi server yêu cầu xác thực, thường gặp với HTTP Basic và Bearer token.
- **Nội dung lỗi**: JSON hoặc Problem Details do ứng dụng quy định, cùng status và content type tương ứng.

Các header và body này bổ sung cho status assertion và security matcher. Chúng giúp xác nhận **client thực sự nhận được chỉ dẫn hoặc thông tin lỗi đúng như hợp đồng**.

## 2. Chuẩn bị MockMvc và các matcher

Với ứng dụng Spring Boot Servlet, dependency kiểm thử bảo mật là:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Cấu hình test tích hợp:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityResponseContractTest {

    @Autowired
    MockMvc mockMvc;
}
```

@AutoConfigureMockMvc tích hợp các servlet filter của ứng dụng. Nếu tự dựng MockMvc từ WebApplicationContext, hãy áp dụng springSecurity() để request đi qua Spring Security filter chain.

Các matcher thường dùng:

| Matcher | Mục đích |
| --- | --- |
| header().exists(name) | Header phải xuất hiện |
| header().doesNotExist(name) | Header không được xuất hiện |
| header().string(name, value) | So sánh giá trị header |
| header().string(name, matcher) | So sánh header bằng Hamcrest matcher |
| header().stringValues(name, values...) | So sánh danh sách giá trị header |
| redirectedUrl(url) | Kiểm tra URL chuyển hướng |
| redirectedUrlPattern(pattern) | Kiểm tra URL chuyển hướng theo pattern |
| content().contentTypeCompatibleWith(type) | Kiểm tra media type tương thích |
| content().json(json) | Kiểm tra JSON response |
| jsonPath(expression).value(value) | Kiểm tra một trường JSON |

Import tĩnh thường dùng:

```java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Các ví dụ lược bớt import thông thường để tập trung vào matcher. Tùy đoạn mã, cần bổ sung các lớp như `HttpHeaders`, `MediaType`, `URI`, `UriComponents`, `UriComponentsBuilder`, `MultiValueMap`, `MvcResult`, `Authentication`, `SimpleGrantedAuthority` và các API Spring Security tương ứng.

Header name không phân biệt chữ hoa/chữ thường theo HTTP. Tuy vậy, giá trị header như scheme hoặc mã lỗi cần được kiểm tra theo giao thức và hợp đồng của ứng dụng.

## 3. Kiểm tra Location khi chuyển hướng đăng nhập

### 3.1. Anonymous được chuyển tới login page

Với ứng dụng web bật form login:

```java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Một request anonymous truy cập trang được bảo vệ thường được chuyển hướng tới trang login mặc định:

```java
@Test
void anonymousIsRedirectedToLogin() throws Exception {
    mockMvc.perform(get("/account/profile"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/login"))
           .andExpect(header().string(
                   HttpHeaders.LOCATION, "/login"))
           .andExpect(unauthenticated());
}
```

redirectedUrl(...) là matcher chuyên biệt cho redirect; kiểm tra trực tiếp Location giúp thể hiện rõ header mà client sẽ nhận. Không nhất thiết phải dùng cả hai trong mọi test, nhưng có thể kết hợp khi muốn xác nhận cả trạng thái chuyển hướng và giá trị header.

Nếu login page được cấu hình riêng:

```java
.formLogin(form -> form
    .loginPage("/signin")
    .permitAll()
)
```

thì đích chuyển hướng mong đợi cũng phải đổi thành /signin:

```java
mockMvc.perform(get("/account/profile"))
       .andExpect(status().is3xxRedirection())
       .andExpect(redirectedUrl("/signin"));
```

Nếu ứng dụng có nhiều SecurityFilterChain hoặc AuthenticationEntryPoint theo content negotiation, cần gửi đúng URL và header Accept như client thực tế. API JSON có thể trả 401 trong khi trang HTML được chuyển tới login page.

### 3.2. URL chuyển hướng có query string hoặc biến động

Một số ứng dụng gắn query string vào URL đích, ví dụ /signin?continue=/account/profile. Có thể dùng redirectedUrlPattern(...) nếu pattern đủ rõ:

```java
mockMvc.perform(get("/account/profile"))
       .andExpect(status().is3xxRedirection())
       .andExpect(redirectedUrlPattern("/signin*"));
```

Khi cần kiểm tra chính xác query parameter, lấy response rồi phân tích URI thay vì so sánh chuỗi URL dài:

```java
MvcResult result = mockMvc.perform(get("/account/profile"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

String location = result.getResponse().getHeader(HttpHeaders.LOCATION);
URI uri = URI.create(location);
UriComponents components = UriComponentsBuilder.fromUri(uri).build();

assertThat(components.getPath()).isEqualTo("/signin");
assertThat(components.getQueryParams().getFirst("continue"))
        .isEqualTo("/account/profile");
```

Ví dụ giả định ứng dụng thực sự tạo query parameter continue. Hãy thay tên và giá trị theo hợp đồng của mình. Location có thể là URL tương đối hoặc tuyệt đối tùy cách response được tạo; phân tích bằng URI giúp tránh phụ thuộc vào host/port nếu chúng không phải điều cần kiểm tra.

### 3.3. Request cache ảnh hưởng redirect sau đăng nhập

Spring Security có thể lưu request ban đầu để đưa người dùng trở lại trang vừa yêu cầu sau khi đăng nhập. Vì vậy, redirect sau login không phải lúc nào cũng là /. Nó có thể là URL được lưu trong request cache.

Khi viết test, xác định rõ mục tiêu:

- Nếu chỉ kiểm tra đăng nhập thành công, dùng status().is3xxRedirection() và authenticated().withUsername(...).
- Nếu kiểm tra đích sau đăng nhập, cần duy trì cùng session/request cache giữa request ban đầu và request login, sau đó mới khẳng định Location.
- Nếu success handler tùy chỉnh luôn chuyển tới dashboard, kiểm tra đúng URL dashboard theo hợp đồng ứng dụng.

Không nên kiểm tra một redirect mặc định khi ứng dụng đã cấu hình SavedRequestAwareAuthenticationSuccessHandler hoặc success handler riêng.

## 4. Kiểm tra WWW-Authenticate với HTTP Basic

### 4.1. Request thiếu credentials

Với HTTP Basic, server thường trả 401 kèm challenge WWW-Authenticate. Một ví dụ test:

```java
@Test
void basicApiChallengesAnonymousRequest() throws Exception {
    mockMvc.perform(get("/api/me"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().exists(HttpHeaders.WWW_AUTHENTICATE))
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Basic")));
}
```

Challenge thường có dạng Basic realm="...". Realm có thể thay đổi theo cấu hình, do đó kiểm tra scheme bằng startsWith("Basic") thường ổn định hơn so sánh toàn bộ chuỗi.

Nếu API cam kết một realm cụ thể và đó là một phần hợp đồng, có thể kiểm tra chính xác hơn:

```java
.andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        "Basic realm=\"api\""))
```

Chỉ dùng giá trị cụ thể sau khi cấu hình BasicAuthenticationEntryPoint đã cố định realm đó.

### 4.2. Credentials sai

Credentials Basic sai cũng thường dẫn tới 401 và challenge:

```java
@Test
void invalidBasicCredentialsAreRejectedWithChallenge() throws Exception {
    mockMvc.perform(get("/api/me")
                .with(httpBasic("mai", "wrong")))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Basic")));
}
```

Phép kiểm tra unauthenticated() xác nhận không có danh tính hợp lệ sau request. Header challenge giúp client hiểu server vẫn yêu cầu xác thực Basic.

### 4.3. Không phải mọi 401 đều có cùng challenge

WWW-Authenticate mô tả scheme mà server chấp nhận. API có thể hỗ trợ nhiều scheme hoặc có handler tùy chỉnh. Vì thế:

- Kiểm tra Basic khi endpoint được cấu hình HTTP Basic.
- Kiểm tra Bearer khi endpoint là OAuth2 Resource Server.
- Nếu hỗ trợ nhiều challenge, dùng header().stringValues(...) hoặc kiểm tra các giá trị phù hợp thay vì giả định chỉ có một header.
- Nếu handler tùy chỉnh không gửi challenge, hãy xác định đó có phải hợp đồng chủ ý của ứng dụng hay không. Với HTTP authentication chuẩn, challenge là một phần quan trọng của phản hồi 401.

Không nên kỳ vọng header Basic trên endpoint chỉ cấu hình Bearer, hoặc ngược lại.

## 5. Kiểm tra WWW-Authenticate với Bearer token

Resource server thường trả challenge Bearer khi không thể xác thực request:

```java
@Test
void resourceServerChallengesMissingBearerToken() throws Exception {
    mockMvc.perform(get("/api/reports"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Bearer")));
}
```

Với token không hợp lệ, response Bearer có thể chứa tham số lỗi theo RFC 6750, chẳng hạn error="invalid_token". Không phải mọi lỗi đều phải trả cùng nội dung chi tiết; cần dựa vào loại lỗi và handler thực tế.

Một trường hợp khác là token hợp lệ nhưng thiếu scope. Khi đó, resource server thường trả 403. Với BearerTokenAccessDeniedHandler mặc định, challenge có thể nêu error="insufficient_scope" và scope cần thiết:

```java
@Test
void validJwtWithoutRequiredScopeReturnsInsufficientScope() throws Exception {
    mockMvc.perform(get("/api/reports")
                .with(jwt()
                    .jwt(token -> token.subject("account-42"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_report:write"))))
           .andExpect(status().isForbidden())
           .andExpect(authenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   containsString("Bearer")));
}
```

Assertion trên kiểm tra scheme Bearer. Nếu ứng dụng cố định handler theo RFC và muốn kiểm tra lỗi insufficient scope, có thể thêm:

```java
.andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("error=\"insufficient_scope\"")))
```

Chỉ thêm assertion này nếu response hiện tại thực sự dùng handler phát ra tham số đó. jwt() tạo token giả lập và không kiểm tra chữ ký, issuer, audience hay thời hạn JWT; test này kiểm tra việc phân quyền sau khi có danh tính JWT giả lập.

## 6. Kiểm tra nội dung lỗi JSON

### 6.1. Vì sao cần kiểm tra body?

Status và header cho biết giao thức xử lý request, nhưng client thường còn cần một mã lỗi ổn định để quyết định hành động. Ví dụ:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Vui lòng đăng nhập để tiếp tục"
}
```

Frontend có thể dựa vào code để hiển thị thông báo hoặc điều hướng. Test nên xác minh trường dữ liệu ổn định, thay vì phụ thuộc toàn bộ câu chữ có thể thay đổi theo ngôn ngữ.

Một test response JSON giả định API đã cấu hình AuthenticationEntryPoint tùy chỉnh:

```java
@Test
void unauthenticatedApiReturnsStructuredError() throws Exception {
    mockMvc.perform(get("/api/me")
                .accept(MediaType.APPLICATION_JSON))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(content().contentTypeCompatibleWith(
                   MediaType.APPLICATION_JSON))
           .andExpect(jsonPath("$.code")
                   .value("AUTHENTICATION_REQUIRED"))
           .andExpect(jsonPath("$.message").isNotEmpty());
}
```

Ví dụ giả định entry point ghi JSON body có hai trường trên. BasicAuthenticationEntryPoint mặc định không có nghĩa vụ trả JSON theo cấu trúc này. Nếu chưa có error handler riêng, hãy kiểm tra response thực tế của ứng dụng và không tự thêm expectation không thuộc hợp đồng.

### 6.2. Kiểm tra error body khi thiếu quyền

Với người dùng đã xác thực nhưng thiếu role, ứng dụng có thể trả:

```json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền thực hiện thao tác này"
}
```

Test:

```java
@Test
void forbiddenApiReturnsAccessDeniedError() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .with(user("mai").roles("USER"))
                .accept(MediaType.APPLICATION_JSON))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withUsername("mai"))
           .andExpect(content().contentTypeCompatibleWith(
                   MediaType.APPLICATION_JSON))
           .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
}
```

Matcher authenticated() rất quan trọng ở đây: nó giúp chứng minh request bị từ chối trong khi đã có danh tính. Nếu body lỗi dùng cùng một mã cho cả 401 và 403, test nên kiểm tra thêm status để phân biệt hai tình huống.

### 6.3. Kiểm tra JSON bằng jsonPath hoặc content().json()

Dùng jsonPath khi chỉ cần xác nhận một vài trường:

```java
.andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
.andExpect(jsonPath("$.details.reason").value("MISSING_ROLE"))
```

Dùng content().json(...) khi cần so sánh cấu trúc JSON lớn hơn:

```java
.andExpect(content().json("""
    {
      "code": "ACCESS_DENIED",
      "details": {
        "reason": "MISSING_ROLE"
      }
    }
    """, false))
```

Tham số false cho phép so sánh không strict theo overload tương ứng, phù hợp khi body có thêm trường không cần kiểm tra. Nếu dự án dùng phiên bản Spring Test không hỗ trợ text block Java, có thể truyền JSON dưới dạng chuỗi thông thường.

Không nên so sánh toàn bộ JSON khi body có timestamp, trace id hoặc thông tin biến động; hãy assert các trường hợp đồng ổn định.

## 7. Problem Details và application/problem+json

Spring Framework hỗ trợ ProblemDetail để biểu diễn lỗi theo định dạng Problem Details. Response thường dùng media type application/problem+json và các trường chuẩn như type, title, status, detail, instance. Ứng dụng có thể thêm extension field, ví dụ code.

Ví dụ body:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required",
  "code": "AUTHENTICATION_REQUIRED"
}
```

Test:

```java
@Test
void authenticationFailureUsesProblemDetails() throws Exception {
    mockMvc.perform(get("/api/me")
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
           .andExpect(status().isUnauthorized())
           .andExpect(content().contentTypeCompatibleWith(
                   MediaType.APPLICATION_PROBLEM_JSON))
           .andExpect(jsonPath("$.title").value("Unauthorized"))
           .andExpect(jsonPath("$.status").value(401))
           .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
}
```

Đây là hợp đồng do ứng dụng lựa chọn. Spring Security filter xử lý authentication failure nằm ngoài luồng controller thông thường; không mặc định mọi AuthenticationEntryPoint hay AccessDeniedHandler sẽ tự sinh ProblemDetail. Cần cấu hình handler để ghi body và content type này, rồi mới viết assertion tương ứng.

Với 403, title/status/code phải phản ánh access denied. Không nên trả status 401 bên trong body nếu HTTP response thực tế là 403; hai lớp thông tin phải nhất quán.

## 8. Location còn có thể chỉ tài nguyên vừa được tạo

Location không chỉ xuất hiện trong redirect. Theo quy ước HTTP, response 201 Created có thể dùng Location để chỉ URI của tài nguyên mới.

Ví dụ controller:

```java
@PostMapping("/api/documents")
ResponseEntity<Void> createDocument() {
    URI location = URI.create("/api/documents/42");
    return ResponseEntity.created(location).build();
}
```

Test:

```java
@Test
void createdDocumentReturnsItsLocation() throws Exception {
    mockMvc.perform(post("/api/documents")
                .with(user("mai").roles("USER"))
                .with(csrf()))
           .andExpect(status().isCreated())
           .andExpect(header().string(
                   HttpHeaders.LOCATION, "/api/documents/42"));
}
```

Đây là response thành công, không phải redirect đăng nhập. Vì thế nên kết hợp status 201 với Location thay vì dùng redirectedUrl(...). Nếu API trả URI tuyệt đối hoặc có context path, hãy kiểm tra đúng dạng URI mà hợp đồng công khai cam kết.

## 9. Kiểm tra Location của OAuth2 authorization redirect

Khi ứng dụng bật OAuth2 Login, request tới /oauth2/authorization/{registrationId} thường được chuyển hướng tới authorization endpoint của identity provider. Location có thể chứa các query parameter như client_id, redirect_uri, response_type, scope, state và code_challenge.

Không nên hard-code giá trị state hoặc PKCE code challenge vì chúng được sinh động cho từng request. Có thể kiểm tra host/path và các tham số ổn định:

```java
MvcResult result = mockMvc.perform(get("/oauth2/authorization/acme"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

String location = result.getResponse().getHeader(HttpHeaders.LOCATION);
URI authorizationUri = URI.create(location);

assertThat(authorizationUri.getHost()).isEqualTo("idp.example.test");
assertThat(authorizationUri.getPath()).isEqualTo("/authorize");

MultiValueMap<String, String> query =
        UriComponentsBuilder.fromUri(authorizationUri)
                .build()
                .getQueryParams();

assertThat(query.getFirst("client_id")).isEqualTo("web-client");
assertThat(query.getFirst("response_type")).isEqualTo("code");
assertThat(query.getFirst("state")).isNotBlank();
```

Ví dụ giả định registration acme được cấu hình với authorization endpoint https://idp.example.test/authorize và client id web-client. Thay các giá trị bằng cấu hình test thực tế. Nếu provider thêm tham số hoặc mã hóa query khác, nên kiểm tra những trường thuộc hợp đồng thay vì so sánh toàn bộ URL.

Test này kiểm tra **bước bắt đầu authorization redirect**. Nó không chứng minh callback, xác minh state/nonce, đổi authorization code hoặc xác minh ID Token đã thành công; những bước đó cần các ca kiểm thử riêng.

## 10. Kết hợp headers, body và trạng thái xác thực

Một test response từ chối có thể được thiết kế theo nhiều lớp:

```java
@Test
void forbiddenResponseMatchesApiContract() throws Exception {
    mockMvc.perform(get("/api/admin/report")
                .with(user("mai").roles("USER"))
                .accept(MediaType.APPLICATION_JSON))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withUsername("mai"))
           .andExpect(content().contentTypeCompatibleWith(
                   MediaType.APPLICATION_JSON))
           .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
}
```

Ý nghĩa:

1. status().isForbidden() khẳng định kết quả HTTP là 403.
2. authenticated().withUsername("mai") xác nhận danh tính request.
3. contentTypeCompatibleWith(...) xác nhận client nhận định dạng JSON.
4. jsonPath(...) xác nhận mã lỗi mà client dựa vào.

Đối với request anonymous dùng Basic, test tương ứng có thể là:

```java
mockMvc.perform(get("/api/me")
            .accept(MediaType.APPLICATION_JSON))
       .andExpect(status().isUnauthorized())
       .andExpect(unauthenticated())
       .andExpect(header().string(
               HttpHeaders.WWW_AUTHENTICATE, startsWith("Basic")))
       .andExpect(content().contentTypeCompatibleWith(
               MediaType.APPLICATION_JSON))
       .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
```

Đoạn thứ hai giả định custom entry point vừa ghi JSON vừa giữ challenge Basic. Nếu handler hiện tại chỉ trả challenge mà không có body, bỏ các assertion JSON hoặc cấu hình response contract trước.

## 11. WebTestClient trên Reactive

Các matcher MockMvcResultMatchers không dùng trực tiếp trên WebTestClient. Với WebFlux, kiểm tra header và body qua API của WebTestClient:

```java
webTestClient.get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "^Bearer.*")
        .expectBody()
        .jsonPath("$.code").isEqualTo("AUTHENTICATION_REQUIRED");
```

Ví dụ giả định ứng dụng Reactive cấu hình Bearer authentication, custom error body JSON và response challenge. Tên phương thức matcher header có thể dùng valueEquals, valueMatches hoặc value tùy kiểu kiểm tra; chọn API theo phiên bản Spring Test đang sử dụng.

Với redirect, có thể dùng expectStatus().is3xxRedirection() và expectHeader().valueEquals(HttpHeaders.LOCATION, "/signin"). Với JSON error, expectBody().jsonPath(...) xác minh các trường tương ứng. Nếu cần kiểm tra principal Reactive cụ thể, kết hợp test của security context ở tầng reactive; không chuyển matcher Servlet sang WebFlux.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Status 401 đúng nhưng thiếu WWW-Authenticate | Entry point tùy chỉnh không ghi challenge hoặc dùng scheme khác | Xem lại authentication scheme và handler; xác định challenge có thuộc hợp đồng không |
| Header Basic bị test với Bearer | Endpoint đang dùng resource server, không phải HTTP Basic | Assert đúng scheme theo SecurityFilterChain |
| Redirect đúng status nhưng Location sai | Login page, context path, request cache hoặc success handler khác kỳ vọng | Kiểm tra cấu hình login và request đã lưu |
| URL redirect có query động làm test fail | State, nonce, code challenge hoặc tham số tiếp tục thay đổi | Parse URI và assert các tham số ổn định |
| JSON path không tìm thấy | Handler trả body rỗng, HTML hoặc media type khác | Kiểm tra response thực tế và cấu hình error handler |
| Test mặc định mong ProblemDetail | Spring Security entry point/handler không tự sinh body này trong mọi cấu hình | Cấu hình custom handler rồi mới assert Problem Details |
| Header có nhiều challenge nhưng test chỉ đọc một giá trị | Response có nhiều giá trị cùng tên header | Dùng matcher stringValues hoặc kiểm tra từng giá trị |
| Mock JWT có body lỗi nhưng không test được decoder | Request post-processor bỏ qua việc xác minh token thật | Viết test Bearer token qua decoder/filter chain |

Các lỗi về header/body thường không nằm ở controller. Với response bảo mật, cần xác định filter hoặc handler nào tạo response trước khi thay đổi code ứng dụng.

## 13. Bài tập thực hành

Dùng ứng dụng Spring Security có API Basic, form login và resource server để thực hiện:

1. Viết test anonymous gọi API Basic: xác nhận 401, unauthenticated() và WWW-Authenticate bắt đầu bằng Basic.
2. Cấu hình login page /signin; viết test request HTML được chuyển hướng tới URL này và khẳng định Location.
3. Viết test API Bearer thiếu token: xác nhận 401 và challenge Bearer. Sau đó tạo JWT giả lập thiếu scope và xác nhận 403.
4. Tạo custom authentication entry point trả JSON có code và message; viết test kiểm tra status, content type và hai trường JSON.
5. Nếu dùng Problem Details, kiểm tra application/problem+json, title, status và extension field code.
6. Tạo endpoint tạo tài liệu trả 201 và Location; phân biệt assertion này với redirect 302.
7. Nếu bật OAuth2 Login, kiểm tra authorization redirect bằng cách phân tích URI và xác minh client_id, response_type, state mà không hard-code state.

**Tiêu chí hoàn thành:** Người học chọn đúng matcher cho Location, WWW-Authenticate và body; giải thích được vì sao các giá trị có thể thay đổi theo handler; và viết test phản ánh đúng hợp đồng HTTP mà client sử dụng.

## Tài liệu tham khảo chính thức

- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
