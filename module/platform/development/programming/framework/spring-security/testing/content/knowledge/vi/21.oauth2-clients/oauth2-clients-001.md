# oauth2Client trong MockMvc và OAuth2AuthorizedClient

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Chương **Ứng dụng khách OAuth2** tập trung vào ứng dụng Servlet/Spring MVC: cách dùng `oauth2Client(...)` trong MockMvc để cung cấp một `OAuth2AuthorizedClient` giả lập cho request và kiểm tra controller nhận đúng client đã được ủy quyền.

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa `ClientRegistration`, `OAuth2AccessToken` và `OAuth2AuthorizedClient`.
2. Dùng `oauth2Client("registration-id")` để thiết lập authorized client trong một request MockMvc.
3. Tùy chỉnh registration, access token, scope và principal name.
4. Kiểm thử tham số controller `@RegisteredOAuth2AuthorizedClient`.
5. Phân biệt `oauth2Client()` với `oauth2Login()`, `oidcLogin()` và `@WithMockUser`.
6. Xác định giới hạn của token giả lập và biết khi nào cần test authorization server hoặc outbound HTTP riêng.

## 1. OAuth2AuthorizedClient là gì?

Một ứng dụng OAuth2 Client có thể nhận access token để gọi protected resource. Spring Security biểu diễn thông tin này bằng `OAuth2AuthorizedClient`. Đối tượng này gắn một client registration với token đã được cấp và principal name dùng để lưu/tra cứu client.

| Thành phần | Vai trò |
| --- | --- |
| `ClientRegistration` | Cấu hình một OAuth2 client: registration id, client id/secret, grant type, token URI, scope và phương thức xác thực client |
| `OAuth2AccessToken` | Access token, token type, thời điểm phát hành/hết hạn và các scope |
| `OAuth2RefreshToken` | Refresh token nếu authorization server cấp và ứng dụng lưu giữ |
| `OAuth2AuthorizedClient` | Kết hợp `ClientRegistration`, principal name và access token (cùng refresh token nếu có) |
| `OAuth2AuthorizedClientRepository` | Lưu/đọc authorized client gắn với request và principal, thường qua HTTP session |
| `OAuth2AuthorizedClientService` | Lưu/đọc authorized client theo principal và registration ở tầng service |

Ví dụ luồng dùng client credentials:

~~~mermaid
flowchart LR
    A["Ứng dụng Spring MVC"] --> B["OAuth2AuthorizedClientManager"]
    B --> C["ClientRegistration<br/>my-app"]
    C --> D["Token Endpoint"]
    D --> E["OAuth2AccessToken"]
    E --> F["OAuth2AuthorizedClient"]
    F --> G["Protected Resource"]
~~~

Trong một luồng thật, manager có thể yêu cầu token từ token endpoint, tạo hoặc cập nhật authorized client rồi lưu qua repository/service. Nhưng khi kiểm thử controller hoặc logic sử dụng authorized client, việc chạy authorization server thật thường không cần thiết. Spring Security Test cung cấp request post-processor `oauth2Client(...)` để đặt một client đã được ủy quyền giả lập vào request.

## 2. oauth2Client(...) làm gì trong MockMvc?

Static method `SecurityMockMvcRequestPostProcessors.oauth2Client(...)` tạo một `OAuth2AuthorizedClient` và liên kết nó với request thông qua `OAuth2AuthorizedClientRepository`. Controller có thể lấy client bằng `@RegisteredOAuth2AuthorizedClient` như trong ứng dụng.

Ví dụ tối thiểu:

~~~java
mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")))
    .andExpect(status().isOk());
~~~

Giá trị `"my-app"` là **registration id**. Request post-processor tạo một registration, access token và principal name mặc định để test có thể chạy mà không gọi authorization server. Theo cấu hình mặc định của test support, client có client id `test-client`, client secret `test-secret`, principal name `user` và access token có scope `read`.

Bạn có thể tùy chỉnh từng phần:

- `clientRegistration(ClientRegistration)`: dùng một registration cụ thể.
- `clientRegistration(Consumer<ClientRegistration.Builder>)`: tùy chỉnh registration builder.
- `accessToken(OAuth2AccessToken)`: thay token và scopes.
- `principalName(String)`: đặt principal name gắn với authorized client.

Các overload `oauth2Client()` và `oauth2Client(String registrationId)` có từ Spring Security 5.3. Dùng đúng phiên bản `spring-security-test` tương thích với Spring Security đang có trong ứng dụng.

**Điểm cần phân biệt:** `oauth2Client(...)` thiết lập một **authorized client**; nó không tự tạo người dùng đã đăng nhập trong `SecurityContext`. Nếu endpoint còn yêu cầu authentication, hãy cung cấp danh tính bằng `@WithMockUser`, `with(user(...))`, `oauth2Login()` hoặc cơ chế phù hợp khác.

## 3. Phụ thuộc và cấu hình ứng dụng

Với Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

`spring-boot-starter-oauth2-client` cung cấp OAuth2 Client support cho ứng dụng; `spring-security-test` cung cấp `oauth2Client(...)` và các tiện ích MockMvc.

### 3.1. Client registration

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          my-app:
            provider: test-idp
            client-id: app-client
            client-secret: test-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - message:read
        provider:
          test-idp:
            token-uri: https://idp.example.test/oauth2/token
~~~

Registration id ở đây là `my-app`. Token URI là endpoint cấu hình cho ứng dụng thật; các test dùng `oauth2Client(...)` để cung cấp authorized client giả lập nên không cần gọi token endpoint này. Không đặt secret thật trong file cấu hình được commit; dùng secret store hoặc biến môi trường cho môi trường chạy thật.

### 3.2. SecurityFilterChain

Tệp `SecurityConfiguration.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/outbound").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Client(Customizer.withDefaults())` bật hỗ trợ OAuth2 Client trong security configuration. Rule `authenticated()` yêu cầu người gọi endpoint đã xác thực; authorized client được gắn vào request là một thông tin riêng. Hai điều kiện này không thay thế nhau.

Nếu tự dựng MockMvc bằng `webAppContextSetup(...)`, tích hợp Spring Security:

~~~java
MockMvc mockMvc = webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Với `@AutoConfigureMockMvc` của Spring Boot, dùng instance MockMvc được inject và giữ filter registration mặc định.

## 4. Nhận OAuth2AuthorizedClient trong controller

Spring MVC có thể resolve một tham số `OAuth2AuthorizedClient` bằng annotation `@RegisteredOAuth2AuthorizedClient`. Registration id trong annotation phải trùng registration mà request test cung cấp.

Tệp `OutboundController.java`:

~~~java
package example;

import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OutboundController {
    @GetMapping("/api/outbound")
    public ResponseEntity<String> outbound(
            @RegisteredOAuth2AuthorizedClient("my-app")
            OAuth2AuthorizedClient authorizedClient) {
        if (!authorizedClient.getAccessToken().getScopes().contains("message:read")) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body("missing scope");
        }

        String scopes = authorizedClient.getAccessToken().getScopes().stream()
            .sorted()
            .collect(Collectors.joining(","));

        String result = authorizedClient.getClientRegistration().getRegistrationId()
            + "|" + authorizedClient.getPrincipalName()
            + "|" + authorizedClient.getAccessToken().getTokenType().getValue()
            + "|" + scopes;
        return ResponseEntity.ok(result);
    }
}
~~~

Ví dụ trả về metadata cần thiết để kiểm tra request. Trong ứng dụng thực tế, không trả access token hoặc client secret về cho caller; controller thường chuyển authorized client cho service hoặc HTTP client dùng để gọi protected resource.

## 5. Kiểm thử với oauth2Client mặc định

Tệp `OutboundControllerTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Client;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OutboundControllerTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "user", roles = "USER")
    void resolvesDefaultAuthorizedClient() throws Exception {
        mockMvc.perform(get("/api/outbound")
                .with(oauth2Client("my-app")))
            .andExpect(status().isOk())
            .andExpect(content().string("my-app|user|Bearer|read"));
    }
}
~~~

Trong test này:

1. `@WithMockUser(username = "user")` tạo Authentication để đáp ứng rule `authenticated()`.
2. `oauth2Client("my-app")` thêm authorized client có registration id `my-app` vào request/repository test.
3. `@RegisteredOAuth2AuthorizedClient("my-app")` resolve client và truyền vào controller.
4. Controller đọc registration id, principal name, token type và scope.

Nếu bỏ `@WithMockUser`, endpoint vẫn có thể bị từ chối vì chưa đăng nhập, dù request post-processor đã cung cấp authorized client. Ngược lại, chỉ có `@WithMockUser` mà không có authorized client thì không chứng minh controller nhận được OAuth2 client cần thiết.

## 6. Tùy chỉnh ClientRegistration, principal và access token

Khi logic ứng dụng kiểm tra grant type, client id hoặc scope cụ thể, hãy cung cấp dữ liệu có chủ ý thay vì phụ thuộc giá trị mặc định.

### 6.1. Tạo registration cho client credentials

~~~java
private ClientRegistration serviceClientRegistration() {
    return ClientRegistration.withRegistrationId("my-app")
        .clientId("test-service-client")
        .clientSecret("test-service-secret")
        .clientName("Service client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("message:read")
        .tokenUri("https://idp.example.test/oauth2/token")
        .build();
}
~~~

Đoạn code cần import `ClientRegistration` từ `org.springframework.security.oauth2.client.registration`, cùng `ClientAuthenticationMethod` và `AuthorizationGrantType` từ `org.springframework.security.oauth2.core`.

Đoạn helper trên cũng cần import `OAuth2AccessToken` từ `org.springframework.security.oauth2.core`, `Instant` từ `java.time` và `Set` từ `java.util`.

### 6.2. Cung cấp token và principal name

~~~java
OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "test-access-token",
    Instant.parse("2030-01-01T00:00:00Z"),
    Instant.parse("2030-01-01T00:05:00Z"),
    Set.of("message:read")
);

mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")
            .clientRegistration(serviceClientRegistration())
            .principalName("user")
            .accessToken(accessToken)))
    .andExpect(status().isOk())
    .andExpect(content().string("my-app|user|Bearer|message:read"));
~~~

Ví dụ cần import `OAuth2AccessToken`, `Instant` và `Set`. Trong test đi kèm `@WithMockUser(username = "user")`, principal name được đặt thành `user` để khớp người dùng mà repository dùng làm khóa tra cứu authorized client. Với client credentials, principal name thường đại diện cho danh tính ứng dụng/service account trong kho lưu trữ; nó không có nghĩa grant này đã xác thực một end user.

Bạn cũng có thể cấu hình registration ngay trên request post-processor:

~~~java
mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")
            .clientRegistration(builder -> builder
                .clientId("test-service-client")
                .clientSecret("test-service-secret")
                .clientName("Service client")
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("message:read")
                .tokenUri("https://idp.example.test/oauth2/token"))
            .principalName("user")))
    .andExpect(status().isOk());
~~~

Khi registration đã được định nghĩa trong ứng dụng, có thể lấy từ `ClientRegistrationRepository` thay vì tạo lại:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Autowired
ClientRegistrationRepository clientRegistrationRepository;

mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")
            .clientRegistration(
                clientRegistrationRepository.findByRegistrationId("my-app"))))
    .andExpect(status().isOk());
~~~

Đảm bảo repository trả về registration không null và registration id trùng với annotation trên controller.

## 7. oauth2Client khác oauth2Login và oidcLogin thế nào?

Các request post-processor này giải quyết những nhu cầu khác nhau:

| Công cụ | Thiết lập chính | Khi nên dùng |
| --- | --- | --- |
| `oauth2Client("my-app")` | Một `OAuth2AuthorizedClient` trong repository/session của request | Controller cần token của client để gọi dịch vụ khác |
| `oauth2Login()` | `OAuth2AuthenticationToken`, `OAuth2User` và authorized client liên quan | Kiểm tra ứng dụng đăng nhập bằng OAuth2 Login |
| `oidcLogin()` | `OAuth2AuthenticationToken`, `OidcUser`, ID token/user info và authorized client liên quan | Kiểm tra OIDC principal/claims |
| `@WithMockUser` | Authentication username/password giả lập với authorities | Kiểm tra URL/method authorization thông thường |

Một request có thể cần cả người dùng đăng nhập và một client token độc lập:

~~~java
mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")))
    .andExpect(status().isOk());
~~~

Nếu endpoint yêu cầu authentication, đặt `@WithMockUser` trên test method hoặc thêm `.with(user("operator"))` vào request. Nếu muốn kiểm thử OAuth2 Login, dùng `oauth2Login()` thay vì cho rằng `oauth2Client()` đã tạo một `OAuth2AuthenticationToken`.

Trong tình huống một người dùng đăng nhập bằng OAuth2 và controller cũng nhận authorized client gắn với login đó, `oauth2Login()` có thể là lựa chọn phù hợp: test support liên kết OAuth2User với một authorized client trong repository giả lập. Với client credentials grant không gắn với người dùng, `oauth2Client()` thể hiện ý định rõ hơn.

## 8. Kiểm tra scope và hành vi phụ thuộc token

Một controller/service có thể kiểm tra scope trước khi gọi protected resource. Hãy tạo token với scope đủ hoặc thiếu để kiểm tra nhánh xử lý.

~~~java
private OAuth2AccessToken tokenWithScopes(String... scopes) {
    return new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-access-token",
        Instant.parse("2030-01-01T00:00:00Z"),
        Instant.parse("2030-01-01T00:05:00Z"),
        Set.of(scopes)
    );
}
~~~

Request có scope:

~~~java
mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")
            .principalName("user")
            .accessToken(tokenWithScopes("message:read"))))
    .andExpect(status().isOk());
~~~

Request thiếu scope:

~~~java
mockMvc.perform(get("/api/outbound")
        .with(oauth2Client("my-app")
            .principalName("user")
            .accessToken(tokenWithScopes("message:write"))))
    .andExpect(status().isForbidden())
    .andExpect(content().string("missing scope"));
~~~

Controller ở mục 4 chủ động yêu cầu scope `message:read`, nên token chỉ có `message:write` nhận 403. Nếu controller chỉ đọc token rồi trả metadata, request vẫn có thể nhận 200; khi đó test nên assert nội dung scope thay vì status 403.

## 9. OAuth2AuthorizedClientRepository và nơi lưu trữ

`oauth2Client(...)` đưa authorized client vào cơ chế repository của request để controller có thể resolve nó. `@RegisteredOAuth2AuthorizedClient` được xử lý bởi `OAuth2AuthorizedClientArgumentResolver`, thông qua cơ chế quản lý authorized client của Spring Security.

Trong ứng dụng Servlet, authorized client thường được lưu theo registration id và principal name. Với client credentials, principal name vẫn hữu ích làm khóa lưu trữ dù token đại diện cho service client thay vì một end user.

Nếu ứng dụng dùng repository tùy chỉnh, hãy bảo đảm request post-processor và argument resolver/manager cùng đọc được authorized client. Nếu cần cấu hình test repository riêng, có thể dùng `HttpSessionOAuth2AuthorizedClientRepository` trong test configuration:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@TestConfiguration
class OAuth2ClientTestRepositoryConfiguration {
    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }
}
~~~

Đây là cấu hình test hỗ trợ lưu authorized client trong session. Chỉ thêm khi cấu hình ứng dụng hoặc phiên bản Spring Security của dự án cần repository này; không tạo thêm repository thứ hai nếu auto-configuration đã cung cấp một bean phù hợp. Nếu có nhiều repository, hãy xác định rõ bean mà security config và argument resolver đang sử dụng.

Nếu lớp `@TestConfiguration` là top-level, hãy import nó vào test bằng `@Import(OAuth2ClientTestRepositoryConfiguration.class)`; nếu khai báo nó dưới dạng nested static class trong test, Spring Boot Test có thể nhận diện theo quy tắc test configuration. Chỉ dùng một cách cung cấp repository cho mỗi test context.

## 10. Những gì oauth2Client không kiểm thử

Thông tin do `oauth2Client(...)` tạo ra là dữ liệu khai báo dành cho test. Token không cần được authorization server cấp hoặc xác minh. Do đó, test này không chứng minh:

- Client id/secret thực sự được authorization server chấp nhận.
- Client credentials grant gọi token endpoint thành công.
- Client authentication method (ví dụ `client_secret_basic` hoặc `private_key_jwt`) hoạt động với server thật.
- Chữ ký, issuer, audience, thời hạn hoặc scope của token được authorization server xác minh.
- Refresh token được sử dụng để làm mới access token.
- Outbound HTTP request đã thực sự gửi bearer token tới protected resource.

Nếu cần kiểm tra token acquisition, hãy test `OAuth2AuthorizedClientManager` cùng `OAuth2AccessTokenResponseClient` bằng mock server hoặc HTTP stub cho token endpoint. Nếu cần kiểm tra outbound call, dùng mock HTTP server để xác minh request có header `Authorization: Bearer ...`. Tách hai luồng này khỏi test MVC chỉ nhằm xác minh controller nhận đúng `OAuth2AuthorizedClient`.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Controller không nhận được authorized client | Registration id trong annotation và request không trùng | So sánh `@RegisteredOAuth2AuthorizedClient("my-app")` với `oauth2Client("my-app")` |
| Endpoint trả 401 dù đã gọi oauth2Client | Authorized client không tự tạo Authentication | Thêm `@WithMockUser` hoặc cơ chế đăng nhập phù hợp nếu endpoint yêu cầu |
| Không tìm thấy registration | Thiếu `ClientRegistrationRepository` hoặc registration id không được cấu hình | Kiểm tra OAuth2 Client starter và registration |
| Scope không đúng | Đang dùng token mặc định có scope `read` | Dùng `.accessToken(...)` để thiết lập scope rõ ràng |
| Authorized client không được resolve | Repository của test không tương thích với repository ứng dụng | Kiểm tra `OAuth2AuthorizedClientRepository` và cấu hình test |
| Test cho rằng token hợp lệ | Token giả lập không được authorization server xác minh | Viết test riêng cho token endpoint/decoder và outbound HTTP |
| Test client credentials phụ thuộc user không mong muốn | Principal name dùng để lưu client chưa khớp Authentication/repository key | Đặt `.principalName(...)` phù hợp với fixture xác thực |
| Dùng oauth2Client để test OAuth2 Login | Nhầm authorized client với OAuth2 Authentication | Dùng `oauth2Login()` hoặc `oidcLogin()` cho login principal |

Checklist khi review:

1. Registration id có trùng giữa annotation, post-processor và repository không?
2. Endpoint có yêu cầu người dùng đăng nhập riêng với authorized client không?
3. Test đã đặt principal name và scopes rõ ràng chưa?
4. Repository được dùng để lưu và resolve client có tương thích không?
5. Assertion đang kiểm tra controller sử dụng client hay vô tình tuyên bố đã kiểm tra token endpoint thật?
6. Nếu outbound call là mục tiêu, test có xác minh header bearer token trên HTTP request không?

## 12. Bài tập thực hành

**Bài 1 — Authorized client mặc định.** Dùng `oauth2Client("my-app")` với endpoint có tham số `@RegisteredOAuth2AuthorizedClient("my-app")`. Kiểm tra registration id, principal name và scope mặc định.

**Bài 2 — Tách authentication và authorized client.** Bỏ `@WithMockUser` khỏi endpoint yêu cầu `authenticated()`, giữ `oauth2Client(...)` và quan sát request bị từ chối. Thêm lại user fixture và giải thích hai vai trò khác nhau.

**Bài 3 — Client credentials.** Tạo `ClientRegistration` với grant type `client_credentials`, principal name `batch-service` và scope `message:read`. Kiểm tra controller nhận đúng dữ liệu mà không gọi token endpoint.

**Bài 4 — Scope.** Tạo hai access token giả lập: một có `message:read`, một chỉ có `message:write`. Viết assertion cho nhánh được phép và bị từ chối.

**Bài 5 — Phân biệt test giả lập và test tích hợp.** Giữ test MockMvc dùng `oauth2Client()`, sau đó tạo test riêng cho `OAuth2AuthorizedClientManager` với token endpoint giả lập. Ghi rõ mỗi test chứng minh phần nào của luồng OAuth2.

## 13. Ghi nhớ

**`oauth2Client(...)` cung cấp một `OAuth2AuthorizedClient` giả lập cho request MockMvc để kiểm tra controller và logic sử dụng token.** Registration id phải khớp với `@RegisteredOAuth2AuthorizedClient`; access token, scope và principal name có thể tùy chỉnh để kiểm tra các nhánh nghiệp vụ.

Authorized client không đồng nghĩa với người dùng đã đăng nhập. Hãy kết hợp `@WithMockUser` hoặc `oauth2Login()` khi endpoint yêu cầu Authentication. Dùng test riêng cho token acquisition, refresh và outbound HTTP khi cần xác minh giao tiếp OAuth2 thật.

## Tài liệu tham khảo

- [Spring Security Reference — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [SecurityMockMvcRequestPostProcessors API — oauth2Client](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [OAuth2ClientRequestPostProcessor API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.OAuth2ClientRequestPostProcessor.html)
