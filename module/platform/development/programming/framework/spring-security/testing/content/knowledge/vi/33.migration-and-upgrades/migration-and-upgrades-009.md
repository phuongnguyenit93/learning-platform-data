# Đối chiếu helper Servlet và Reactive với Javadoc đúng nhánh

## 1. Vì sao lỗi nâng cấp thường bắt đầu từ một static import?

Khi chuyển một bài kiểm thử Spring Security từ `MockMvc` (Servlet) sang `WebTestClient` (WebFlux), người học có thể viết:

~~~java
// Cú pháp của MockMvc, KHÔNG dùng nguyên xi với WebTestClient.
mockMvc.perform(get("/api/admin")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

rồi cố dùng `user()`, `with(...)` và `andExpect(...)` trong một test WebFlux. Kết quả thường là lỗi compile, hoặc tệ hơn: test chạy qua một **loại client/stack khác** với điều người viết tưởng đang kiểm tra.

Trong WebFlux, cú pháp gần với ý định trên là:

~~~java
webTestClient
    .mutateWith(mockUser("alice").roles("ADMIN"))
    .get()
    .uri("/api/admin")
    .exchange()
    .expectStatus().isOk();
~~~

Hai helper này có mục tiêu tương tự: **giả lập một principal đã xác thực**. Nhưng chúng thuộc **hai package**, hai cơ chế gắn request và hai kiểu assertions khác nhau.

Trong chương **Di chuyển và nâng cấp** của module `SPRING_SECURITY_TESTING`, bài học này hướng dẫn đối chiếu Spring Security Test helpers với **Javadoc của đúng nhánh phiên bản** trước khi sửa code. Mục tiêu của module là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế với `spring-security-test` trên Servlet và Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập.

Sau bài này, bạn sẽ biết:

1. Xác định Spring Security Test version thực tế qua dependency resolution mà **không đoán theo tên Spring Boot**.
2. Tìm đúng Javadoc cho `SecurityMockMvcRequestPostProcessors` và `SecurityMockServerConfigurers`.
3. Chuyển các helper `user`, `csrf`, `jwt`, `opaqueToken`, `oauth2Login`, `oidcLogin` và `oauth2Client` đúng stack.
4. Hiểu các trường hợp **không có cặp helper tương đương một-một**.
5. Phân biệt mock principal với việc xác minh HTTP Basic, Bearer JWT hoặc OAuth2/OIDC thực.
6. Kiểm tra compiler, security filters, assertions, negative cases và dependency conflicts sau nâng cấp.

## 2. Ba thứ không nên trộn lẫn

### 2.1. Servlet và Reactive là hai đường request khác nhau

| Thành phần | Servlet | Reactive |
| --- | --- | --- |
| Web framework | Spring MVC | Spring WebFlux |
| Security filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Test HTTP không mở socket | `MockMvc` | `WebTestClient.bindToApplicationContext(...)` |
| Gắn test principal vào request | `RequestPostProcessor` | `WebTestClientConfigurer` / mock-server mutator |
| Context bảo mật | `SecurityContextHolder` cho Servlet processing | `ReactiveSecurityContextHolder` qua Reactor Context |
| HTTP thật | Embedded Servlet server + HTTP client | Embedded Reactive server + HTTP client |

`WebTestClient` có thể **gửi HTTP thật tới Servlet server** khi sử dụng `bindToServer()`. Vì thế, sự có mặt của `WebTestClient` trong test **không tự chứng minh ứng dụng đang chạy WebFlux**. Muốn dùng các mutator Reactive mock server, cần setup WebFlux mock phù hợp, không chỉ đổi kiểu client.

### 2.2. Dependency `spring-security-test` là một phần của Spring Security

Những helper trong bài đến từ artifact:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

Trong dự án Spring Boot, dependency management thường quyết định phiên bản thực tế. Tuy nhiên, một project có thể khai báo override hoặc dùng dependency platform khác; **không suy luận** rằng một snippet trong tài liệu Spring Security 7.x tự động phù hợp với classpath hiện tại.

Nếu cần kiểm tra version đã resolve trong dự án dùng Gradle, một lệnh hữu ích là:

~~~bash
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
~~~

Hoặc:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Các lệnh trên là **ví dụ để người học chạy trong dự án của họ**; chúng không được chạy trong bước viết Markdown này. Với Maven, có thể dùng `mvn dependency:tree -Dincludes=org.springframework.security`. Đích cần tìm là **phiên bản artifact đã resolve**, không chỉ một version được khai báo ở file build.

### 2.3. Javadoc không đồng nghĩa reference guide

- **Javadoc**: có class, package, method signatures, overloads, return types, `Since` và `Deprecated`.
- **Reference guide**: giải thích cấu hình và luồng sử dụng, thường có ví dụ hoàn chỉnh.
- **Release notes / migration guide**: nêu những khác biệt khi đổi major/minor, phương thức đã đổi hoặc bị loại bỏ.

Một ví dụ trên website thuộc nhánh `7.2` không nhất thiết compile với `6.5`. Ngược lại, tìm thấy một method trong Javadoc cũ không chứng minh method đó chưa bị deprecated hoặc thay đổi cách dùng ở bản mới.

## 3. Chọn URL Javadoc đúng phiên bản

Giả sử project đang dùng Spring Security `6.5.x`, nên đọc đường dẫn gắn nhánh `6.5`:

| Chủ đề | Javadoc gắn nhánh 6.5 |
| --- | --- |
| Servlet RequestPostProcessors | [SecurityMockMvcRequestPostProcessors — 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html) |
| Servlet test setup | [SecurityMockMvcConfigurers — 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/setup/SecurityMockMvcConfigurers.html) |
| Servlet result matchers | [SecurityMockMvcResultMatchers — 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/response/SecurityMockMvcResultMatchers.html) |
| Reactive test configurers | [SecurityMockServerConfigurers — 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html) |

Nếu dự án dùng Spring Security `7.2.x`, đọc nhánh `7.2`:

| Chủ đề | Javadoc gắn nhánh 7.2 |
| --- | --- |
| Servlet RequestPostProcessors | [SecurityMockMvcRequestPostProcessors — 7.2](https://docs.spring.io/spring-security/reference/7.2/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html) |
| Servlet test setup | [SecurityMockMvcConfigurers — 7.2](https://docs.spring.io/spring-security/reference/7.2/api/java/org/springframework/security/test/web/servlet/setup/SecurityMockMvcConfigurers.html) |
| Servlet result matchers | [SecurityMockMvcResultMatchers — 7.2](https://docs.spring.io/spring-security/reference/7.2/api/java/org/springframework/security/test/web/servlet/response/SecurityMockMvcResultMatchers.html) |
| Reactive test configurers | [SecurityMockServerConfigurers — 7.2](https://docs.spring.io/spring-security/reference/7.2/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html) |

**Lưu ý về URL:** các website tài liệu có thể chuyển hướng URL của bản chính sang `/reference/api/java/...`. Khi cần kiểm chứng một **phiên bản cố định**, hãy xem **version ghi trên trang thực tế sau chuyển hướng**. Các nhánh cũ thường được lưu riêng, còn `current` hoặc đường dẫn không có version có thể thay đổi theo thời gian.

Nếu project ở `6.5.3`, một trang Javadoc của nhánh `6.5` hiện đã cập nhật sang `6.5.11` vẫn chỉ cho biết API của patch release được xuất bản đó; nếu method hoặc behavior quan trọng có thể thay đổi ở patch cụ thể, tìm Javadoc của **đúng patch** hoặc kiểm tra trực tiếp classpath/source jar tương ứng.

### 3.1. Quy trình kiểm tra một helper

Với mỗi helper định chuyển:

1. **Tìm artifact và version:** `spring-security-test` đã resolve phiên bản nào?
2. **Tìm class sở hữu:** `SecurityMockMvcRequestPostProcessors` hay `SecurityMockServerConfigurers`?
3. **Đọc Method Summary:** tên method, static hay instance, overload nào và kiểu trả về.
4. **Đọc Method Details:** ý nghĩa, `Since`, `Deprecated` và mọi yêu cầu setup.
5. **Đọc ví dụ cùng nhánh:** dùng `MockMvc.perform(...).with(...)` hay `WebTestClient.mutateWith(...)`?
6. **Viết test âm/dương:** yêu cầu đủ quyền phải chạy, thiếu quyền phải bị chặn.
7. **Biên dịch trong dự án:** nếu không compile, xử lý dependency/sai stack trước khi đổi API theo trí nhớ.

Không sửa import bằng cách chọn gợi ý IDE đầu tiên nếu IDE đưa cả Servlet và Reactive classes có tên gần nhau.

## 4. Hai class trung tâm phải nhớ

### 4.1. Servlet: `SecurityMockMvcRequestPostProcessors`

Package:

~~~java
org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors
~~~

Static imports phổ biến:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

Cách dùng:

~~~java
mockMvc.perform(get("/api/private")
        .with(user("alice").roles("USER")))
    .andExpect(status().isOk());
~~~

`.with(...)` nhận `RequestPostProcessor` để chỉnh `MockHttpServletRequest`. `status()` ở đây là `MockMvcResultMatchers.status()`, không thuộc `SecurityMockMvcRequestPostProcessors`.

### 4.2. Reactive: `SecurityMockServerConfigurers`

Package:

~~~java
org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers
~~~

Static imports:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
~~~

Cách dùng:

~~~java
webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/private")
    .exchange()
    .expectStatus().isOk();
~~~

`.mutateWith(...)` cung cấp configurer/mutator cho client mock. Nó không nhận Servlet `RequestPostProcessor`. `expectStatus()` thuộc `WebTestClient.ResponseSpec`, không phải `MockMvcResultMatchers`.

### 4.3. Đừng để tên `springSecurity()` trùng gây nhầm

Hai helper setup có cùng tên nhưng **class sở hữu khác nhau**:

~~~java
// MockMvc
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
~~~

~~~java
// WebTestClient (Reactive)
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Hai static imports có tên `springSecurity` không nên được đặt cùng trong một file rồi gọi `springSecurity()` mơ hồ. Nếu thật sự có một lớp test tích hợp cả hai stack (hiếm và cần cân nhắc), dùng tên class đầy đủ ở điểm gọi.

## 5. Bảng đối chiếu helper theo nhiệm vụ

| Mục đích | Servlet / MockMvc | Reactive / WebTestClient |
| --- | --- | --- |
| Giả lập user | `.with(user("alice").roles("USER"))` | `.mutateWith(mockUser("alice").roles("USER"))` |
| Gắn `Authentication` tùy chỉnh | `.with(authentication(auth))` | `.mutateWith(mockAuthentication(auth))` |
| Giả lập CSRF hợp lệ | `.with(csrf())` | `.mutateWith(csrf())` |
| Giả lập JWT principal | `.with(jwt())` | `.mutateWith(mockJwt())` |
| Giả lập opaque bearer principal | `.with(opaqueToken())` | `.mutateWith(mockOpaqueToken())` |
| Giả lập OAuth2 login | `.with(oauth2Login())` | `.mutateWith(mockOAuth2Login())` |
| Giả lập OIDC login | `.with(oidcLogin())` | `.mutateWith(mockOidcLogin())` |
| Giả lập authorized OAuth2 client | `.with(oauth2Client("reports"))` | `.mutateWith(mockOAuth2Client("reports"))` |
| Gửi HTTP Basic credentials | `.with(httpBasic("alice", "password"))` | `.headers(h -> h.setBasicAuth("alice", "password"))` |
| Gửi Bearer token thật | `.header("Authorization", "Bearer " + token)` | `.headers(h -> h.setBearerAuth(token))` |
| Giả lập anonymous | `.with(anonymous())` (khi cần) | Thường gửi request không có mock auth/credentials |
| Form login request helper | `formLogin()` từ `SecurityMockMvcRequestBuilders` | Tạo `POST` form với WebTestClient theo route/CSRF thực |
| Xác nhận authenticated principal | `SecurityMockMvcResultMatchers.authenticated()` | Assert HTTP status/body hoặc lấy principal từ ứng dụng theo test context |
| Kiểm tra HTTP status | `.andExpect(status().isForbidden())` | `.expectStatus().isForbidden()` |

Đây là **bảng tương ứng về ý định kiểm thử**, không phải cam kết mọi overload, extension method hay cách tích hợp vào security chain hoàn toàn giống nhau. Cần kiểm tra Javadoc **đúng nhánh** để xác nhận method cụ thể và loại tham số của version đang dùng.

### 5.1. Những điểm không có cặp một-một

1. `SecurityMockMvcRequestBuilders.formLogin()` và `logout()` hỗ trợ xây request Servlet; không giả định có `mockFormLogin()`/`mockLogout()` tương ứng trong `SecurityMockServerConfigurers`.
2. `SecurityMockMvcResultMatchers.authenticated()` là result matcher Servlet; trong WebFlux thường assert status/body hoặc truy xuất principal trong handler/test phù hợp, không chuyển nguyên xi.
3. `@WithUserDetails` tải `UserDetails` qua `UserDetailsService`; nó **không đồng nghĩa** với `ReactiveUserDetailsService.findByUsername(...)`.
4. Servlet `SecurityContextHolder` và Reactive `ReactiveSecurityContextHolder` khác nhau về cách mang context; không thay mỗi import rồi cho rằng behavior giống nhau.
5. `MockMvc` có Servlet `HttpSession`; WebFlux dùng `WebSession`. Một authorized client giả có thể được lưu thông qua repository khác nhau.
6. `WebTestClient.bindToServer()` gửi HTTP qua socket tới bất kỳ server hỗ trợ HTTP; mock-user mutators không tự truyền một authentication từ test thread qua socket.

## 6. Ví dụ chuyển test role từ Servlet sang Reactive

Giả sử ứng dụng có endpoint `GET /api/admin` yêu cầu role `ADMIN` và trả chuỗi `admin` khi được phép. Ở hai stack, security configuration khác nhau nhưng **hợp đồng HTTP** giống nhau.

### 6.1. Servlet: MockMvc

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AdminServletTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void userIsForbidden() throws Exception {
        mockMvc.perform(get("/api/admin")
                    .with(user("alice").roles("USER")))
               .andExpect(status().isForbidden());
    }

    @Test
    void adminIsAllowed() throws Exception {
        mockMvc.perform(get("/api/admin")
                    .with(user("bob").roles("ADMIN")))
               .andExpect(status().isOk())
               .andExpect(content().string("admin"));
    }
}
~~~

Để kết quả phản ánh security behavior, test context phải nạp `SecurityFilterChain` có rule `hasRole("ADMIN")` và không vô hiệu hóa filters. Một test chỉ có `.with(user(...))` không kiểm tra password thật.

### 6.2. Reactive: WebTestClient mock context

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class AdminReactiveTests {

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
    void userIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void adminIsAllowed() {
        client.mutateWith(mockUser("bob").roles("ADMIN"))
              .get()
              .uri("/api/admin")
              .exchange()
              .expectStatus().isOk()
              .expectBody(String.class).isEqualTo("admin");
    }
}
~~~

Test này **chỉ hợp lệ khi `ApplicationContext` là WebFlux**, nạp `SecurityWebFilterChain` có `hasRole("ADMIN")` và endpoint tương ứng. `@SpringBootTest(MOCK)` không tự biến một ứng dụng Servlet thành Reactive; nếu dependencies chứa cả Spring MVC và WebFlux, cần xác định web application type thực.

### 6.3. Đối chiếu từng dòng thay vì search-and-replace

| Servlet | Reactive | Vì sao đổi? |
| --- | --- | --- |
| `MockMvc` | `WebTestClient` | API client/test transport khác |
| `.perform(get(...))` | `.get().uri(...).exchange()` | Cách tạo và chạy request khác |
| `.with(user(...))` | `.mutateWith(mockUser(...))` | Post-processor Servlet vs mutator Reactive |
| `.andExpect(status().isOk())` | `.expectStatus().isOk()` | Kiểu assertion khác |
| `.andExpect(content().string(...))` | `.expectBody(String.class).isEqualTo(...)` | Cách kiểm body |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Không dùng lại cấu hình Servlet |
| `@AutoConfigureMockMvc` | WebFlux test setup/binding phù hợp | Không có `MockMvc` trong WebFlux mock |

Một test “chuyển đổi” mới chỉ thay syntax mà không tải đúng WebFlux security chain sẽ **không** chứng minh policy được di chuyển đúng.

## 7. CSRF và các phương thức ghi: cùng tên helper nhưng khác package

Với một `POST /api/notes` yêu cầu authentication và bật CSRF, Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mockMvc.perform(post("/api/notes")
        .with(user("alice").roles("USER"))
        .with(csrf()))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

client.mutateWith(mockUser("alice").roles("USER"))
      .mutateWith(csrf())
      .post()
      .uri("/api/notes")
      .exchange()
      .expectStatus().isOk();
~~~

Kết quả `200` là minh họa cho controller trả `200` và chính sách cho phép. Nếu API trả `201 Created` hoặc `204 No Content`, assertion phải thay theo contract thực.

Nên bổ sung ca **thiếu CSRF nhận `403`** và ca **đủ CSRF nhưng thiếu quyền nhận `403`**. Nếu một test muốn kiểm tra thiếu role nhưng lại quên CSRF, nó có thể xanh vì CSRF filter từ chối **trước khi** authorization policy được thực thi.

**Lưu ý:** `csrf()` của hai stack tạo token thử nghiệm cho mock HTTP; nó không chứng minh trình duyệt thật đã nhận cookie/token và gửi lại đúng session. Với `RANDOM_PORT`, hãy thực hiện HTTP flow thật để lấy/gửi token.

## 8. JWT: `jwt()` khác `mockJwt()`, nhưng cùng giới hạn

Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get()
      .uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Hai test kiểm tra **quyền đối với principal giả đã có authority**. Chúng không chạy `JwtDecoder`/`ReactiveJwtDecoder` để xác minh chữ ký. Một claim `exp` giả đã hết hạn cũng không làm hai helper tự phát huy tác dụng của timestamp validator.

### 8.1. Giữ đúng converter khi chuyển JWT tests

Một mã nguồn có thể ánh xạ JWT claims sang authorities bằng converter tùy biến. Nếu test luôn gọi `.authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))`, nó **bỏ qua việc kiểm tra converter**. Tách hai câu hỏi:

- **Policy test:** cấp thẳng authority qua helper và kiểm tra `200`/`403`.
- **Converter test:** cho converter thật xử lý JWT claims và kiểm tra authorities thu được.
- **Decoder integration test:** gửi JWS đã ký đến endpoint để xác minh signature, issuer, audience, expiry và policy.

Không đổi `mockJwt()` thành `headers.setBearerAuth("fake")` rồi mong request được xác thực như cũ: khi gửi Bearer header, resource server thực cần decoder/validator chấp nhận token, trừ khi test cố tình mock decoder.

### 8.2. Opaque token cũng tương tự

Servlet `opaqueToken()` và Reactive `mockOpaqueToken()` tạo principal opaque-token giả để test authorization. Nếu mục tiêu là introspection thật, cần dùng `OpaqueTokenIntrospector` hoặc Reactive counterpart phù hợp với bản Spring Security đang dùng và quan sát HTTP introspection endpoint; không kết luận từ helper giả.

## 9. OAuth2/OIDC Login: chọn helper theo loại principal cần dùng

### 9.1. OAuth2 user giả

Servlet:

~~~java
mockMvc.perform(get("/api/me")
        .with(oauth2Login()
            .attributes(attributes ->
                attributes.put("user_id", "user-42"))))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
client.mutateWith(mockOAuth2Login())
      .get()
      .uri("/api/me")
      .exchange()
      .expectStatus().isOk();
~~~

Với Reactive, tùy thuộc custom attributes cần mô phỏng, dùng các tùy chỉnh được Javadoc của `OAuth2LoginMutator` trong **nhánh hiện tại** hỗ trợ. Không tự giả định `.attributes(...)` có cùng overload chính xác như Servlet `OAuth2LoginRequestPostProcessor`.

### 9.2. OIDC principal giả

Servlet:

~~~java
mockMvc.perform(get("/api/me")
        .with(oidcLogin()))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
client.mutateWith(mockOidcLogin())
      .get()
      .uri("/api/me")
      .exchange()
      .expectStatus().isOk();
~~~

Các đoạn này chỉ có ý nghĩa nếu ứng dụng có endpoint `/api/me` được thiết kế để chấp nhận và xử lý principal tương ứng; cần thêm assertions cho body/claims/authorities nếu đó là mục tiêu.

`oauth2Login()`/`mockOAuth2Login()` thiết lập OAuth2-authenticated principal giả; `oidcLogin()`/`mockOidcLogin()` thiết lập OIDC principal giả. Chúng không tự kiểm chứng authorization code, PKCE, token endpoint, ID token signature hoặc nonce. Khi nâng cấp, không coi “cùng trả 200” là bằng chứng luồng giao thức tương đương.

### 9.3. `@WithMockUser` không thay thế `OidcUser`

Nếu handler nhận `@AuthenticationPrincipal OidcUser` rồi gọi `getIdToken()`, một `@WithMockUser` tạo `UserDetails` thông thường không cung cấp cùng kiểu principal. Dùng `oidcLogin()` hoặc `mockOidcLogin()` theo stack, hoặc tạo authentication phù hợp khi mục tiêu là logic trực tiếp.

## 10. OAuth2 Client: test fake authorized client không chứng minh token endpoint

Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Client;

mockMvc.perform(get("/api/client-info")
        .with(oauth2Client("reports-client")))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

client.mutateWith(mockOAuth2Client("reports-client"))
      .get()
      .uri("/api/client-info")
      .exchange()
      .expectStatus().isOk();
~~~

Hai helper giả lập `OAuth2AuthorizedClient` để controller/filter có thể dùng token đã được cung cấp. Tại Servlet, repository thường liên quan `OAuth2AuthorizedClientRepository`; tại Reactive, `ServerOAuth2AuthorizedClientRepository`. Cách lưu/truy xuất và tên class khác nhau, vì vậy không chuyển package/service injection một cách cơ học.

Nếu yêu cầu kiểm thử là “OAuth2 Client đã gửi `POST` đến token endpoint với `grant_type=client_credentials` hoặc `authorization_code` đúng”, thì **cả hai helper trên đều không phải bằng chứng**. Cần kích hoạt `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager` thực với token server thử nghiệm và kiểm tra HTTP request nhận được.

## 11. `@WithMockUser` và `@WithUserDetails`: chú ý vòng đời và stack

`@WithMockUser` là annotation trong package:

~~~java
org.springframework.security.test.context.support.WithMockUser
~~~

Nó được dùng trong cả Servlet và Reactive tests với Spring Test integration phù hợp. Ví dụ:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void canReadPrivateResource() {
    // ...
}
~~~

Nhưng annotation này **không** tạo một HTTP Basic header hoặc đăng nhập thật. Với `WebTestClient.bindToServer()` qua socket, authentication của test thread không tự đi theo HTTP request.

`@WithUserDetails` cũng nằm trong `org.springframework.security.test.context.support` nhưng tra cứu một `UserDetails` từ `UserDetailsService` đồng bộ. Nếu fixture tạo trong `@BeforeEach`, cần cân nhắc:

~~~java
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

Khi có `ReactiveUserDetailsService` thuần túy, không mặc định `@WithUserDetails` tự gọi `findByUsername(...)`. Để kiểm tra policy WebFlux, dùng `mockUser()` hoặc tạo authentication phù hợp. Để kiểm tra cơ chế xác thực reactive thật, gửi HTTP Basic credentials cho `ReactiveAuthenticationManager` và user-details service thực.

## 12. Setup sai có thể khiến helper “không tác dụng”

### 12.1. MockMvc phải có Spring Security filters

Khi tự tạo MockMvc:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(SecurityMockMvcConfigurers.springSecurity())
        .build();
~~~

Ở đây `SecurityMockMvcConfigurers.springSecurity()` là **Servlet**. Nếu dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc` trong Spring Boot, auto-configuration thường đã cấu hình Spring Security filters cho MockMvc.

Một test `@AutoConfigureMockMvc(addFilters = false)` không kiểm tra HTTP security filter chain theo cách bình thường. Đừng chữa một test authorization thất bại bằng việc tắt filters rồi ghi nhận `200` là thành công.

### 12.2. WebTestClient mock phải gắn WebFlux Spring Security

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
~~~

`context` phải là `ApplicationContext` WebFlux với `SecurityWebFilterChain` phù hợp. `SecurityMockServerConfigurers.springSecurity()` không thay thế `SecurityMockMvcConfigurers.springSecurity()` và ngược lại.

Khi test qua `WebTestClient.bindToServer()` với `RANDOM_PORT`, không gắn `mockUser()` để truyền identity sang server; dùng HTTP Basic, Bearer, cookie và flow HTTP phù hợp.

### 12.3. Trộn hai servlet/reactive starters

Một dự án có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` có thể được Spring Boot chọn chạy **Servlet** nếu không chỉ định web application type khác. Trước khi sửa test để dùng Reactive helper, kiểm tra app có thật sự có `SecurityWebFilterChain` và WebFlux handlers không. Việc có `WebTestClient` trên test classpath không đổi bản chất server.

## 13. Migration từ Spring Security cũ: những khác biệt rộng hơn helper

Ngoài Test helpers, nâng cấp major framework có thể ảnh hưởng:

| Vùng | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| `javax.*` → `jakarta.*` | Type imports không compile khi sang Spring Framework 6 / Security 6 ecosystem | Dùng Jakarta APIs tương thích cho Servlet project theo nền tảng đang dùng |
| Cấu hình web security | DSL/cấu hình cũ không còn hoặc đã deprecated | Kiểm tra reference guide cùng major; dùng `SecurityFilterChain`/`SecurityWebFilterChain` |
| API validation token | Constructor, converter, matcher hoặc response client thay đổi | So sánh Javadoc API cụ thể giữa nhánh cũ/mới |
| Authentication principal types | Controller cast `JwtAuthenticationToken`/`OidcUser` không đúng với mock user | Dùng helper đúng loại principal |
| Test context | Sự khác biệt Boot auto-config, slicing, bean loading | Kiểm tra test context và filter chain thật |
| Spring Test/JUnit | Version JUnit Jupiter, Spring Test extension khác | Xác nhận `useJUnitPlatform()`, dependency alignment |
| SecurityContext lifecycle | Servlet thread-bound vs Reactor Context | Thay đổi cách test reactive pipeline, không chỉ đổi import |
| CSRF/session | Default policies hoặc hành vi chain được cấu hình khác | Có cả ca thiếu/đủ CSRF và login/session |

Ví dụ `WebSecurityConfigurerAdapter` đã không còn là cách cấu hình chuẩn của Spring Security 6; khi di chuyển từ những dòng cũ, hãy dùng bean `SecurityFilterChain` (Servlet) hoặc `SecurityWebFilterChain` (Reactive) theo tài liệu của bản đích. Không lấy một đoạn DSL cũ và chỉ sửa import.

**Không đọc một bảng migration chung rồi mặc định mỗi phiên bản có cùng khác biệt.** Hãy xác định **nhánh nguồn, nhánh đích** và đọc migration guide tương ứng.

## 14. Khi helper biến mất hoặc method signature thay đổi

Không đoán tên method thay thế theo pattern `mockXxx`. Dùng quy trình:

1. Tìm Javadoc class **cũ** và **mới** của đúng nhánh.
2. So sánh method summary/overloads và `Since`/`Deprecated`.
3. Kiểm tra **nested class** trả về từ helper (ví dụ `JwtMutator` hoặc `JwtRequestPostProcessor`).
4. Đối chiếu public methods của nested type, không chỉ helper ở class cha.
5. Nếu chưa có tương đương Reactive, viết request HTTP hoặc authentication fixture phù hợp, không tạo tên API tưởng tượng.
6. Giữ các assertions về HTTP status, principal và quyền; chúng mới là hợp đồng cần bảo vệ.

Ví dụ về nested classes:

| Servlet nested type | Reactive nested type |
| --- | --- |
| `SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor` | `SecurityMockServerConfigurers.JwtMutator` |
| `SecurityMockMvcRequestPostProcessors.UserRequestPostProcessor` | `SecurityMockServerConfigurers.UserExchangeMutator` |
| `SecurityMockMvcRequestPostProcessors.OAuth2LoginRequestPostProcessor` | `SecurityMockServerConfigurers.OAuth2LoginMutator` |
| `SecurityMockMvcRequestPostProcessors.OidcLoginRequestPostProcessor` | `SecurityMockServerConfigurers.OidcLoginMutator` |
| `SecurityMockMvcRequestPostProcessors.OAuth2ClientRequestPostProcessor` | `SecurityMockServerConfigurers.OAuth2ClientMutator` |

Các nested types có public methods **không hoàn toàn giống nhau**; khi muốn đặt claims, principal tùy chỉnh, registration ID hoặc access token, kiểm tra đúng nested Javadoc trước khi viết chain.

### 14.1. Cẩn thận với “API nhìn có vẻ giống”

Một người có thể viết:

~~~java
// Sai stack: Servlet request post-processor.
client.mutateWith(jwt());
~~~

Hoặc:

~~~java
// Sai stack: Reactive WebTestClient mutator.
mockMvc.perform(get("/api/reports").with(mockJwt()));
~~~

Đây là lỗi *type mismatch*, không phải lỗi token. Hãy xem **package và return type** thay vì thay đổi các assertions hoặc tắt security để sửa compile.

## 15. Khi nào phải dùng credentials thật thay vì mock helper?

Khi nâng cấp, một test chuyển cú pháp thành công chưa đảm bảo ứng dụng còn xác thực thực tế như trước.

### 15.1. HTTP Basic

Servlet:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;

mockMvc.perform(get("/api/private")
        .with(httpBasic("alice", "correct-password")))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
client.get()
    .uri("/api/private")
    .headers(headers -> headers.setBasicAuth(
        "alice", "correct-password"))
    .exchange()
    .expectStatus().isOk();
~~~

Các test trên chỉ chứng minh password authentication nếu **security filters, authentication manager/provider và user store thật của test context** được nạp; phải có ca wrong password nhận `401` để tránh trường hợp mọi request luôn được chấp nhận.

### 15.2. JWT Bearer

Servlet:

~~~java
mockMvc.perform(get("/api/reports")
        .header("Authorization", "Bearer " + signedJws))
    .andExpect(status().isOk());
~~~

Reactive:

~~~java
client.get()
    .uri("/api/reports")
    .headers(headers -> headers.setBearerAuth(signedJws))
    .exchange()
    .expectStatus().isOk();
~~~

`signedJws` phải là JWT đã ký bằng khóa test mà decoder trong application context tin cậy, nếu mục tiêu là kiểm tra chữ ký. Cần thêm ca sai chữ ký, hết hạn hoặc issuer sai nhận `401`; token hợp lệ nhưng thiếu scope nên nhận `403` khi rule yêu cầu scope.

`jwt()`/`mockJwt()` vẫn nên được giữ trong các **policy tests** để bao phủ nhiều tổ hợp authorities mà không phải ký token mỗi lần.

### 15.3. OAuth2/OIDC integration

Muốn chứng minh token endpoint hoặc ID token validator vẫn hoạt động sau nâng cấp, dùng authorization server/IdP thử nghiệm và đi qua callback, token exchange, `state`, PKCE, issuer, audience, signature và nonce theo chính sách. Không dựa vào `oauth2Login()`/`mockOidcLogin()` rồi ghi nhận flow production đã được xác minh.

## 16. Đối chiếu assertion và status giữa hai nhánh

Một test Servlet với matcher của Spring Security:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;

mockMvc.perform(get("/api/private")
        .with(user("alice")))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("alice"));
~~~

Reactive:

~~~java
client.mutateWith(mockUser("alice"))
      .get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.username").isEqualTo("alice");
~~~

Reactive ví dụ giả định controller trả body JSON chứa `username`; nếu endpoint không trả JSON, hãy assert một tín hiệu có ý nghĩa khác (status, body hoặc service effect). Không chuyển `authenticated().withUsername(...)` nguyên xi sang WebTestClient vì `SecurityMockMvcResultMatchers` được thiết kế cho Servlet `MvcResult`.

### 16.1. `401`, `403` và `302` không phải version-independent constants

- Với HTTP Basic, guest vào endpoint bảo vệ thường nhận `401 Unauthorized`.
- Với form login, guest có thể nhận `302` về trang login.
- Với authentication hợp lệ nhưng thiếu quyền, thường `403 Forbidden`.
- Với `POST` thiếu CSRF, thường `403` kể cả khi role đúng.

Khi chuyển test, một assertion `401` bỗng thành `302` có thể do **entry point/filter chain khác**, không nhất thiết do helper lỗi. Hãy xem security configuration và actual response trước khi đổi expected status.

## 17. Một quy trình migration có thể áp dụng cho nhóm phát triển

~~~mermaid
flowchart TD
    A["Ghi nhận dependencies và test hiện tại"] --> B["Resolve spring-security-test version"]
    B --> C["Chọn Javadoc đúng major/minor/patch"]
    C --> D["Xác định Servlet hay Reactive test"]
    D --> E["Đối chiếu method + return type"]
    E --> F["Sửa imports / setup / syntax"]
    F --> G["Compile + chạy test được phép"]
    G --> H{"Có ca âm/dương đúng?"}
    H -- "Không" --> I["Bổ sung 401/403/200, CSRF, JWT negative cases"]
    I --> G
    H -- "Có" --> J["Kiểm tra authentication boundaries không bị mock"]
    J --> K["CI và review kết quả nâng cấp"]
~~~

Thực hành từng bước:

1. **Baseline:** trước khi nâng cấp, ghi nhận tests pass/fail, số test bị skip và hành vi HTTP quan trọng.
2. **Align dependencies:** để Spring Boot BOM hoặc dependency management phù hợp thống nhất các Spring Security artifacts, đặc biệt `spring-security-test` và modules dùng ở runtime.
3. **Chọn documentation branch:** chọn đúng major/minor (và patch khi cần), ghi lại link cho reviewer.
4. **Sửa imports trước:** xác định MockMvc/WebTestClient, method owners và return types.
5. **Sửa setup:** MockMvc có `springSecurity()` Servlet; WebFlux bind application context và apply `springSecurity()` Reactive.
6. **Giữ semantic của test:** mock principal cho policy; HTTP credentials/token thật cho authentication.
7. **Chạy positive và negative tests:** USER/ADMIN, CSRF thiếu/đủ, JWT valid/invalid.
8. **Kiểm tra CI:** đảm bảo không có test bị vô hiệu hóa vì không compile hoặc đổi profile.
9. **Review security regressions:** tránh `permitAll`, `anyRequest().permitAll()` hoặc tắt CSRF/filters chỉ để test xanh.
10. **Ghi giới hạn:** mock context không kiểm tra TCP; fake JWT/OIDC không kiểm tra protocol.

**Tài liệu đang được viết trong STEP 4 không chạy Gradle/Python**. Trong dự án thực, các bước compile/test ở trên phải được thực hiện ở workflow build/CI phù hợp, không chỉ kiểm tra văn bản.

## 18. Bảng chẩn đoán sự cố sau nâng cấp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy `mockUser()` | Import Servlet class hoặc `spring-security-test` sai version | Kiểm tra Reactive `SecurityMockServerConfigurers` Javadoc |
| Không tìm thấy `user()` | Import Reactive class hoặc thiếu dependency | Kiểm tra Servlet `SecurityMockMvcRequestPostProcessors` |
| `.with(mockJwt())` không compile | Dùng WebFlux mutator với MockMvc | Dùng `.with(jwt())` của Servlet |
| `.mutateWith(jwt())` không compile | Dùng Servlet RequestPostProcessor với WebTestClient | Dùng `.mutateWith(mockJwt())` |
| `springSecurity()` bị ambiguous | Hai static imports cùng tên | Chọn đúng class setup, dùng tên đầy đủ |
| `@WithMockUser` không có tác dụng | Test listeners/security setup chưa đúng | Kiểm tra Spring Test integration của stack |
| WebTestClient không inject được | Project Servlet hoặc thiếu auto-config/dependency | Dùng `MockMvc` hoặc `WebTestClient.bindToServer()` |
| Reactive test thiếu principal | Không áp dụng `springSecurity()`, context không phải WebFlux | Kiểm tra binding và security chain |
| Auth HTTP thật vẫn `401` dù có `@WithMockUser` | Test principal không truyền qua socket | Gửi Basic/Bearer/cookie thật |
| JWT giả được `200` dù `exp` quá khứ | `mockJwt()` không gọi decoder | Gửi JWS ký thật qua decoder |
| User bị `403` trên POST dù role đúng | Thiếu CSRF | Thêm `csrf()` hoặc kiểm tra chính sách CSRF |
| Guest nhận `302` thay vì `401` | Đổi entry point sang form login | Assert redirect hợp đồng hoặc điều chỉnh auth config |
| `@WithUserDetails` không tìm thấy user | User được tạo sau listener hoặc dùng ReactiveUserDetailsService | Chọn `setupBefore` phù hợp hoặc test Reactive riêng |
| Test role ADMIN xanh dù security chain tắt | Chỉ có test positive | Thêm USER/guest negative tests |
| Nâng cấp Boot làm imports test thay đổi | Boot test annotations được tổ chức lại | Đối chiếu **Spring Boot Javadoc** cùng version, không chỉ Security Javadoc |

## 19. Bộ test tối thiểu để chứng minh migration đúng ý nghĩa

| Kịch bản | Servlet/MockMvc | Reactive/WebTestClient | Giá trị |
| --- | --- | --- | --- |
| Guest truy cập private | `get(...)` không `user()` | `get(...).exchange()` không `mockUser()` | Xác nhận endpoint không mở |
| USER thiếu quyền | `with(user("alice").roles("USER"))` → `403` | `mutateWith(mockUser("alice").roles("USER"))` → `403` | Xác nhận policy |
| ADMIN đủ quyền | `with(user("bob").roles("ADMIN"))` → `200` | `mutateWith(mockUser("bob").roles("ADMIN"))` → `200` | Xác nhận đường cho phép |
| POST thiếu CSRF | Không `with(csrf())` → `403` | Không `mutateWith(csrf())` → `403` | Xác nhận CSRF |
| POST có CSRF | Thêm `with(csrf())` | Thêm `mutateWith(csrf())` | Xác nhận request hợp lệ |
| Password sai | `with(httpBasic(...))` → `401` | HTTP Basic header → `401` | Authentication provider |
| JWT thiếu scope | `with(jwt().authorities(...))` → `403` | `mockJwt().authorities(...)` → `403` | JWT principal policy |
| JWS sai chữ ký | Bearer token qua decoder thật → `401` | Bearer token qua decoder thật → `401` | JWT validation |
| OIDC principal giả | `oidcLogin()` + assertion | `mockOidcLogin()` + assertion | Logic sau login |
| OAuth2 token endpoint | Grant thật, HTTP server ghi request | Reactive grant thật, HTTP server ghi request | Protocol chứ không phải fake client |

Đây là ma trận mục tiêu, **không phải một test class có thể biên dịch nguyên xi cho mọi dự án**. Chọn những ca mà cơ chế thật có hỗ trợ, dùng đúng API của Javadoc nhánh được resolve, và assert theo status contract thực tế.

## 20. Bài tập thực hành

### Bài 1. Nhận diện sai stack từ import

Một test WebFlux có:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

client.mutateWith(jwt());
~~~

Hãy sửa thành helper Reactive đúng. Giải thích vì sao một tên `jwt` ngắn hơn không đồng nghĩa API có thể thay thế cho `mockJwt`.

### Bài 2. Đối chiếu Javadoc 6.5 và 7.2

Mở hai Javadoc đã gắn nhánh trong mục 3, tìm `mockOAuth2Client(String registrationId)` ở Reactive và `oauth2Client(String registrationId)` ở Servlet. Ghi lại class, package, method return type, `Since` và kiểu repository mà chúng tương tác. Phân biệt việc tạo authorized client giả với token exchange thật.

### Bài 3. Di chuyển test role

Viết một test Servlet MockMvc cho USER `403` và ADMIN `200`. Chuyển sang WebFlux WebTestClient với security chain tương ứng. Nêu khác biệt giữa `RequestPostProcessor` và `WebTestClientConfigurer`, cũng như cách assert HTTP status.

### Bài 4. CSRF

Chuyển một test `POST /api/notes` Servlet có `with(csrf())` sang Reactive có `mutateWith(csrf())`. Viết cả ca thiếu token và đủ token; chứng minh không nhầm `403` do CSRF với `403` do thiếu role.

### Bài 5. JWT mock và Bearer thật

Viết một policy test Servlet với `jwt()` và Reactive với `mockJwt()`, cả hai thiếu scope bị `403`. Sau đó thiết kế test gửi Bearer JWS ký sai qua decoder thật; giải thích vì sao không dùng hai helper mock để kết luận chữ ký đã được kiểm tra.

### Bài 6. Chẩn đoán lỗi Javadoc

Trong một dự án đã nâng cấp, IDE báo không có method `authorities(...)` trên mutator OAuth2 login. Hãy truy Javadoc **nested type** của đúng version thay vì copy tùy chọn từ Servlet. Nếu API tương ứng không tồn tại, đề xuất cách tạo principal/authorized client phù hợp mà không bịa method.

### Bài 7. Thiết kế CI gate cho migration

Lập checklist cho pipeline: dependency alignment, compile, test discovery, security filters bật, ca guest/USER/ADMIN, JWT signature, CSRF và test không bị skip. Giải thích vì sao chỉ có “BUILD SUCCESSFUL” không chứng minh không có regression bảo mật.

## 21. Checklist tổng kết

- [ ] Đã biết `spring-security-test` version **được resolve**, không chỉ version dự kiến.
- [ ] Đã chọn Javadoc theo **nhánh Spring Security** tương ứng.
- [ ] Đã phân biệt `SecurityMockMvcRequestPostProcessors` và `SecurityMockServerConfigurers`.
- [ ] Không dùng Servlet `RequestPostProcessor` với WebTestClient mutator hoặc ngược lại.
- [ ] `springSecurity()` setup đến từ đúng package cho MockMvc hoặc WebTestClient.
- [ ] Đã xác minh ứng dụng thật sự là Servlet hay WebFlux, không suy luận từ test client.
- [ ] Đã kiểm tra Javadoc của nested helper khi tùy chỉnh JWT, OAuth2/OIDC hoặc authorized client.
- [ ] `@WithMockUser`/`@WithUserDetails` được dùng đúng nguồn identity và vòng đời.
- [ ] `mockJwt()`, `oidcLogin()` và các helpers khác được phân loại là **policy test**, không phải validation thật.
- [ ] Khi muốn test password/JWT/token exchange, đã gửi credentials/token thật qua thành phần cần kiểm chứng.
- [ ] Cả ca được phép và ca bị từ chối đều còn hoạt động sau migration.
- [ ] Ca CSRF được kiểm tra riêng, không nhầm nguyên nhân `403`.
- [ ] Test không bị tắt filters hoặc `@Disabled` chỉ để vượt qua compile/upgrade.
- [ ] Kết quả CI có số tests chạy, thất bại, bị skip và có giới hạn được ghi rõ.

## 22. Kết luận

**Đối chiếu Javadoc đúng nhánh là một bước kỹ thuật bắt buộc khi di chuyển Spring Security Test**, không phải việc trang trí phần tài liệu tham khảo. Hai API có nhiệm vụ tương tự nhưng không hoán đổi nhau:

- Servlet: `SecurityMockMvcRequestPostProcessors`, `MockMvc.perform(...).with(...)`, `SecurityMockMvcConfigurers.springSecurity()`.
- Reactive: `SecurityMockServerConfigurers`, `WebTestClient.mutateWith(...)`, `SecurityMockServerConfigurers.springSecurity()`.

Không có “rename tự động” đáng tin cho mọi helper: `formLogin`, `authenticated`, HTTP Basic, session, authorized client và principal types có khác biệt thực chất. Khi nâng cấp, hãy xác định đúng **version → class → method signature → setup → hành vi được assert**.

Một migration chỉ thật sự thành công khi không chỉ **compile** mà còn giữ được các kiểm thử **401/403/200, CSRF, password, JWT và OAuth2/OIDC** theo đúng ranh giới đã công bố, phân biệt rõ principal giả với giao thức xác thực thật.

## 23. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet RequestPostProcessors Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html).
- [Spring Security 6.5 — Reactive SecurityMockServerConfigurers Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html).
- [Spring Security 7.2 — Servlet RequestPostProcessors Javadoc](https://docs.spring.io/spring-security/reference/7.2/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html).
- [Spring Security 7.2 — Reactive SecurityMockServerConfigurers Javadoc](https://docs.spring.io/spring-security/reference/7.2/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html).
- [Spring Security — Servlet MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): mô phỏng request Servlet, setup và assertions.
- [Spring Security — Servlet OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt`, `oauth2Login`, `oidcLogin` và `oauth2Client`.
- [Spring Security — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext` và `springSecurity()`.
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, `mockOAuth2Login`, `mockOidcLogin`.
- [Spring Security — Reference documentation versions](https://docs.spring.io/spring-security/reference/index.html): chọn nhánh phù hợp và tra migration guidance.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): các kiểu binding và assertions.
