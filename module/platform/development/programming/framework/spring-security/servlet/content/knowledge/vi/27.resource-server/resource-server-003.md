# BearerTokenResolver và lựa chọn nguồn nhận token an toàn trong Spring Security Servlet Resource Server

## 1. Bài toán: nhận token từ đâu và tin cậy đến mức nào?

Một OAuth 2.0 Resource Server bảo vệ API bằng access token do Authorization Server phát hành. Client gửi token kèm request; Resource Server phải **tìm đúng token**, **xác minh token** rồi **kiểm tra quyền** trước khi chạy nghiệp vụ. Ba bước có trách nhiệm khác nhau:

1. **Trích xuất token:** `BearerTokenResolver` đọc token ứng viên từ HTTP request, mặc định là header `Authorization: Bearer ...`.
2. **Xác thực token:** `BearerTokenAuthenticationFilter` chuyển token cho cơ chế xác thực, chẳng hạn `JwtAuthenticationProvider` và `JwtDecoder` khi dùng JWT, hoặc cơ chế introspection khi dùng opaque token.
3. **Phân quyền:** các rule `authorizeHttpRequests`, method security hoặc business authorization quyết định request đã xác thực có được thực hiện thao tác đó không.

**`BearerTokenResolver` chỉ quyết định nguồn/chuỗi token được nhận, không xác minh chữ ký, hạn dùng, issuer, audience, scope hoặc quyền.** Một resolver trả được chuỗi không có nghĩa token hợp lệ.

Mục tiêu của bài:
- Hiểu vai trò `BearerTokenResolver` trong Servlet filter chain và hành vi mặc định của `DefaultBearerTokenResolver`.
- Chọn nguồn nhận token an toàn: header chuẩn, form body, query string, header do gateway cung cấp và cookie.
- Biết khi nào mới cấu hình các tùy chọn `setAllowFormEncodedBodyParameter`, `setAllowUriQueryParameter` hoặc header thay thế.
- Thiết lập và kiểm thử Resource Server Java 17+/Spring Boot 3 với JWT; hiểu thông báo lỗi 401/403 và `WWW-Authenticate`.
- Tránh rò rỉ bearer token qua URL, log, referrer, cache, CDN hay trust boundary.

## 2. Vì sao bearer token cần được bảo vệ như một bí mật?

Bearer token mang ý nghĩa **ai sở hữu token có thể sử dụng token** theo phạm vi và điều kiện xác thực của hệ thống. Client gửi token từ đúng nguồn nhưng nếu token bị sao chép từ log, lịch sử URL hoặc trình duyệt thì kẻ khác vẫn có thể dùng nó trong thời gian token còn hiệu lực.

Điều kiện an toàn tối thiểu:

- Chỉ truyền access token qua **HTTPS/TLS** từ client đến endpoint tin cậy; nếu proxy kết thúc TLS, bảo vệ kết nối phía sau và giới hạn đường truy cập tới service.
- Không đặt token vào URL, query parameter, bookmark, redirect URL hoặc đường dẫn tài nguyên.
- Không đưa token vào log HTTP, APM traces, analytics, error response, crash reports hoặc ảnh chụp DevTools được chia sẻ.
- Thiết lập thời gian sống, scopes/authorities tối thiểu; kiểm tra issuer, chữ ký, thời gian và audience phù hợp tại Resource Server.
- Khi có nhiều lớp gateway/proxy/service, quy định rõ lớp nào tiếp nhận credential, lớp nào kiểm tra, lớp nào chuyển tiếp, và cách chống header giả mạo.
- Hạn chế XSS và bảo vệ token ở client; `HttpOnly` cookie có tính chất khác với JavaScript-held bearer token và kéo theo cân nhắc CSRF.

## 3. Cơ chế của BearerTokenResolver trong Servlet filter chain

Luồng điển hình khi client gọi `GET /api/me`:

```text
Client
  |
  | GET /api/me
  | Authorization: Bearer <access_token>
  v
Servlet container
  |
  v
Spring Security FilterChainProxy
  |
  v
BearerTokenAuthenticationFilter
  |
  +-- BearerTokenResolver.resolve(HttpServletRequest)
  |      |
  |      +-- không có token --> tiếp tục filter chain
  |      |                      (protected endpoint có thể trả 401)
  |      |
  |      +-- request lỗi về bearer source/syntax
  |      |      --> OAuth2AuthenticationException / lỗi HTTP phù hợp
  |      |
  |      +-- trích được chuỗi token
  |             |
  |             v
  |      BearerTokenAuthenticationToken
  |             |
  |             v
  |      AuthenticationManager
  |        JWT decoder / opaque token introspector
  |             |
  |             +-- token không hợp lệ --> 401, invalid_token
  |             |
  |             +-- token hợp lệ --> SecurityContext
  |                                      |
  v                                      v
authorizeHttpRequests / method authorization
  |
  +-- đủ quyền --> controller
  +-- thiếu quyền --> 403
```

Interface chính trong Servlet stack:

```java
package org.springframework.security.oauth2.server.resource.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.AuthenticationException;

public interface BearerTokenResolver {
    String resolve(HttpServletRequest request);
}
```

Đoạn trên chỉ mô tả **hình dạng API**, không phải file nguồn bạn cần tự tạo trong ứng dụng. Trong Spring Security thực tế, `resolve` có thể trả `null` khi không tìm được token, trả chuỗi token khi nhận được, hoặc ném `OAuth2AuthenticationException` (một dạng `AuthenticationException`) khi định dạng/nguồn token không hợp lệ.

Khi resolver không tìm thấy token, điều đó **không tự đồng nghĩa request được phép**. Request vẫn phải qua các rule bảo vệ; một endpoint `permitAll` có thể trả thành công dù không token, còn `authenticated()` thường dẫn tới authentication entry point trả 401. Vì vậy không thiết kế `BearerTokenResolver` để phân quyền.

## 4. DefaultBearerTokenResolver: mặc định nhận header Authorization

`DefaultBearerTokenResolver` là triển khai thường dùng của Spring Security OAuth2 Resource Server Servlet. Mặc định, nó tìm token từ:

```http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
```

Tên header `Authorization` là chuẩn. Phần `Bearer` là authentication scheme; phía sau là token. Tài liệu OAuth 2.0 Bearer Token Usage (RFC 6750) xác định kiểu sử dụng bearer trong header; đây là **cách ưu tiên** cho API.

Đặc điểm:
- Mặc định **không cho nhận `access_token` ở URL query parameter**.
- Mặc định **không cho nhận `access_token` từ form-urlencoded body**.
- Header `Authorization` là đường nhận token chuẩn; các tùy chọn nhận token từ nguồn khác phải được bật một cách chủ động.
- Với header mang Bearer scheme nhưng sai cú pháp hoặc nhiều nguồn bearer cạnh tranh khi bật các phương thức khác, resolver có thể từ chối request và ném exception, thay vì tùy tiện chọn một giá trị.

Ví dụ hợp lệ ở mức **trích xuất** (không có nghĩa JWT đã xác thực):

```http
GET /api/me HTTP/1.1
Authorization: Bearer demo-token.abc_123
```

Ví dụ không được xem là token trong cấu hình mặc định:

```http
GET /api/me?access_token=demo-token HTTP/1.1
Host: api.example.test
```

Khi không có header Bearer, resolver mặc định không dùng query token nói trên. Tùy rule bảo vệ, Resource Server có thể trả 401 vì thiếu thông tin xác thực. Đây là **hành vi mong muốn**, không phải lỗi client được “chữa” bằng cách mở query token.

## 5. So sánh các nguồn nhận token

| Nguồn token | Minh họa | Mặc định `DefaultBearerTokenResolver` | Đánh giá / hướng xử lý |
| --- | --- | --- | --- |
| HTTP `Authorization` header | `Authorization: Bearer TOKEN` | **Cho phép** | **Ưu tiên** cho API/SDK/service-to-service với HTTPS |
| Form-urlencoded body | `access_token=TOKEN` trong body `POST` | **Tắt** | Chỉ dùng nếu giao thức thật sự cần và các điều kiện RFC 6750 được đáp ứng |
| URI query parameter | `/api/me?access_token=TOKEN` | **Tắt** | **Tránh** do log, lịch sử, analytics, referrer, caches, sao chép URL |
| Header tùy chỉnh do gateway gắn | `Proxy-Authorization: Bearer TOKEN` | Phải cấu hình | Chỉ chấp nhận khi gateway xóa header từ client và tạo header đáng tin; giới hạn truy cập service |
| Cookie chứa token | `Cookie: access_token=TOKEN` | **Không tự đọc** | Browser tự gửi cookie; tăng rủi ro CSRF và cần thiết kế khác (BFF/session hoặc cơ chế kiểm soát cụ thể) |
| WebSocket/SSE với hạn chế client header | Một số client API không thêm được Authorization header | Không tự chuyển sang URL | Cân nhắc BFF/session, fetch streaming hay vé dùng một lần giới hạn; tránh token truy cập dài hạn trong URL |

Lưu ý: hỗ trợ nhiều hình thức truyền credential cùng lúc làm tăng khả năng nhầm lẫn. **Không nên** tự tạo logic “header không có thì thử query, rồi thử cookie” cho toàn bộ API. Mỗi nguồn phải có threat model và phạm vi rõ ràng, có xử lý request gửi nhiều token xung đột.

### 5.1. Vì sao header là ưu tiên?

- Access token không thành phần của URL nên ít bị đưa vào history, referrer hay link chia sẻ.
- HTTP libraries và client SDK thông dụng hỗ trợ `Authorization: Bearer` trực tiếp.
- Cách biểu diễn tách biệt path/query nghiệp vụ khỏi credential.
- Browser không tự đính kèm một giá trị `Authorization: Bearer` do JavaScript quản lý vào request cross-site của trang khác; khác với cookie tự động gửi. Tuy nhiên **XSS vẫn có thể làm lộ token hoặc tạo request**; header không thay thế bảo vệ frontend.
- Reverse proxy/API gateway thường có cơ chế chuẩn để ẩn hoặc không ghi log `Authorization`; vẫn phải **cấu hình/kiểm tra** chứ không mặc định mọi log đều an toàn.

### 5.2. Khi nào form body có thể được dùng?

RFC 6750 cho phép form-encoded body trong một số điều kiện chặt chẽ; không phải mọi `POST` JSON hay multipart upload đều được coi là nguồn bearer hợp lệ. Khi bật resolver, với các request có `Content-Type: application/x-www-form-urlencoded`, token có thể ở trường `access_token`. Không nên mở tùy chọn chỉ để client cũ “dễ làm”, đặc biệt nếu hệ thống sẵn có header chuẩn.

Ví dụ minh họa:

```http
POST /api/legacy-action HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN&action=preview
```

Ngay cả khi endpoint chỉ POST form, token vẫn là secret; phải tránh body logging, APM request capture, retry logging và các bản sao request. Nếu resource server có phân quyền/CSRF khác, chúng vẫn phải được xét riêng. Chỉ áp dụng khi phía client không thể dùng header và đã kiểm soát đủ mọi hệ quả.

### 5.3. Tại sao query parameter nguy hiểm hơn?

```http
GET /api/me?access_token=SECRET HTTP/1.1
```

URL có thể xuất hiện trong access log của load balancer, reverse proxy, origin, CDN, browser history, bookmark, màn hình chia sẻ, monitoring dashboard, analytics và đôi khi trong ngữ cảnh referrer. Token trong query cũng dễ bị sao chép cùng đường link và khó đảm bảo toàn bộ trung gian sẽ redact.

Không nên xem việc thêm `Cache-Control: no-store` là cách khắc phục đầy đủ: header cache không xóa URL khỏi log hay lịch sử. Nếu một client không hỗ trợ custom header, hãy sửa client, dùng BFF hoặc thiết kế giao thức khác trước khi cân nhắc bật `setAllowUriQueryParameter(true)`.

### 5.4. Cookie và CSRF là một thiết kế khác

`DefaultBearerTokenResolver` không mặc định đọc cookie làm bearer token. Nếu ứng dụng tự viết resolver đọc token từ cookie, browser có thể tự động gửi credential trong các request, làm thay đổi bề mặt **CSRF**. `SameSite` có ích nhưng không thay thế toàn bộ threat model, nhất là với nhiều subdomain, ứng dụng nhúng hoặc cấu hình CORS đặc biệt.

Một mô hình phổ biến cho browser là **Backend-for-Frontend (BFF)**: trình duyệt giữ session cookie `HttpOnly; Secure; SameSite` phù hợp và gửi request tới BFF; BFF giữ access token phía server rồi gọi Resource Server qua `Authorization: Bearer`. Browser dùng cookie cần chính sách CSRF phù hợp. Không tự “hỗ trợ tiện ích” bằng cách đọc access token từ mọi cookie của mọi request.

## 6. Cấu hình an toàn: Spring Boot 3 / Spring Security 6 / Java 17+

Ví dụ sau dùng **Spring Security Servlet**, gồm các dependency Maven/Gradle tương đương:
- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-oauth2-resource-server`

Ví dụ là các file **bên trong ứng dụng Spring Boot** đã có `@SpringBootApplication`; không phải Java độc lập chạy bằng `javac` đơn thuần. JWT issuer bên dưới là placeholder dùng để giải thích cấu hình; muốn chạy tích hợp phải thay bằng URL issuer thật có thể truy cập, với JWK/signing keys và token hợp lệ.

### 6.1. JWT Resource Server, chỉ đọc Authorization header

File `ResourceServerSecurityConfig.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver =
            new DefaultBearerTokenResolver();

        // Các giá trị này đã là mặc định; ghi ra để nhấn mạnh
        // hợp đồng chỉ nhận bearer từ Authorization header.
        resolver.setAllowFormEncodedBodyParameter(false);
        resolver.setAllowUriQueryParameter(false);
        return resolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

Cấu hình này chủ động gắn bean resolver vào `oauth2ResourceServer(...).bearerTokenResolver(...)`, tránh giả định bean bất kỳ sẽ luôn được tự động chọn nếu ứng dụng có nhiều chain hoặc cấu hình tùy biến. Với ứng dụng không cần tùy biến nguồn token, có thể **bỏ bean và lời gọi `bearerTokenResolver(...)`**; cấu hình Resource Server thông thường đã dùng resolver mặc định chỉ nhận header.

File `application.yml` (ví dụ):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/training
```

`issuer-uri` phải là issuer thực của Authorization Server; Resource Server có thể dùng thông tin discovery/JWKS để xác thực chữ ký và kiểm tra issuer, thời gian hiệu lực. Cấu hình issuer đúng **không tự bảo đảm kiểm tra audience mong muốn**: nếu API yêu cầu audience riêng, cần cấu hình validation audience phù hợp. Nguồn nhận token và việc kiểm tra claim là hai bước độc lập.

**Về CSRF:** cấu hình trên không tắt CSRF. Với API chỉ nhận Bearer trong header và **không** dựa trên credential mà browser tự gửi, có thể xem xét chính sách CSRF phù hợp threat model; còn nếu ứng dụng vẫn hỗ trợ session/cookie authentication, không được tắt `csrf` toàn cục theo thói quen. Các ví dụ GET dưới đây không cần gửi CSRF token mặc định.

### 6.2. Endpoint ví dụ cần JWT đã xác thực

File `MeController.java`:

```java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    Map<String, String> me(JwtAuthenticationToken authentication) {
        return Map.of("subject", authentication.getToken().getSubject());
    }
}
```

Với JWT hợp lệ, endpoint trả JSON dạng:

```json
{"subject":"alice"}
```

Đây là **ví dụ body** nếu JWT có `sub=alice`; không phải output từ token placeholder. Endpoint này đang được yêu cầu `authenticated()` theo cấu hình ở trên. Trong ứng dụng thực, phải kiểm tra thêm quyền, scopes và audience theo nghiệp vụ; **xác thực được JWT không có nghĩa người gọi được truy cập mọi dữ liệu**.

### 6.3. Khi gateway buộc dùng header thay thế

Trong hệ thống có API gateway tin cậy, có trường hợp gateway gửi bearer token tới Resource Server bằng một tên header khác. `DefaultBearerTokenResolver` cho phép đổi tên header đọc bằng `setBearerTokenHeaderName(...)`:

```java
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

// Chỉ thay bean ở mục 6.1 bằng phiên bản này khi có
// hợp đồng gateway đáng tin và đã kiểm tra trust boundary.
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setBearerTokenHeaderName("Proxy-Authorization");
    return resolver;
}
```

Đây là **đoạn minh họa phương thức bean bên trong class cấu hình**, không phải một file Java độc lập: import `Bean` nếu đặt vào class thực. Vì vẫn sử dụng `DefaultBearerTokenResolver`, header thay thế phải mang cú pháp kiểu `Bearer TOKEN`:

```http
GET /api/me HTTP/1.1
Proxy-Authorization: Bearer eyJhbGciOi...
```

**Điều kiện bảo mật bắt buộc:** client bên ngoài không được trực tiếp kiểm soát header mà backend coi là thông tin do gateway cấp. Gateway phải **loại bỏ mọi giá trị cùng tên do client gửi** rồi tạo lại giá trị cần thiết theo chính sách của mình; Resource Server không được phơi trực tiếp ra mạng không tin cậy; kết nối gateway → backend phải được bảo vệ. Nếu không, attacker chỉ cần tự gửi `Proxy-Authorization` để giả danh “gateway đã duyệt”.

Đổi tên header **không đồng nghĩa token đã được kiểm tra**. JWT/opaque token vẫn phải được Resource Server xác thực; đừng dùng resolver để tin cậy chuỗi nhận được chỉ vì header có tên “Trusted”.

## 7. Các tùy chọn cần tránh bật tùy tiện

### 7.1. setAllowFormEncodedBodyParameter(true)

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(true);
```

Đoạn mã là một phần bean/cấu hình, không phải class độc lập. Khi bật, resolver có thể nhận `access_token` từ form body **đúng loại request mà triển khai hỗ trợ** (thường là POST `application/x-www-form-urlencoded`). Rủi ro là token đi vào body logs và pipeline xử lý form. Nếu request đồng thời có token từ header và form, không nên tự chọn giá trị bằng thứ tự ưu tiên; phải xử lý request mơ hồ như lỗi.

### 7.2. setAllowUriQueryParameter(true)

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowUriQueryParameter(true);
```

Bật lựa chọn này cho phép nguồn query `access_token` khi thỏa điều kiện của resolver, nhưng làm gia tăng nguy cơ rò rỉ. Chỉ xem xét nếu có yêu cầu giao thức không thể giải quyết bằng header và đã có đánh giá rủi ro cùng biện pháp hạn chế cụ thể; trong hệ thống hiện đại **nên giữ false**.

### 7.3. Không tự viết resolver có fallback ngầm

Một resolver tự viết như pseudocode dưới đây là **anti-pattern**, không nên triển khai:

```text
if Authorization header exists:
    use header token
else if query.access_token exists:
    use query token
else if Cookie.access_token exists:
    use cookie token
```

Những vấn đề: không minh bạch nguồn token được chấp nhận, khó xử lý hai token xung đột, vô tình bật credential tự động từ browser và tạo cơ hội cho parameter pollution hoặc lỗi proxy normalization. Nếu nghiệp vụ thật sự cần nhiều nguồn, phải đặc tả request nào được dùng nguồn nào, từ chối trường hợp mâu thuẫn và kiểm thử toàn bộ các tầng.

## 8. Mã HTTP và lỗi đúng tầng

Nguồn token và tính hợp lệ của token là hai chiều khác nhau. Một vài tình huống:

| Request | Resolver quan sát | Bước tiếp theo / phản hồi thường gặp |
| --- | --- | --- |
| Không có `Authorization` trên endpoint `permitAll` | Không có bearer token | Endpoint có thể được phục vụ bình thường |
| Không có `Authorization` trên endpoint `authenticated()` | Trả `null` | Authentication entry point; thường **401** với `WWW-Authenticate: Bearer` |
| Header `Authorization: Bearer` thiếu token hoặc sai cú pháp | Bearer scheme không hợp lệ | Thường **401**, mô tả lỗi bearer phù hợp theo xử lý Spring Security |
| Header có token nhưng chữ ký sai / hết hạn / issuer sai | Resolver trích được chuỗi | Authentication từ chối; thường **401**, `invalid_token` |
| JWT hợp lệ nhưng không đủ scope/authority | Resolver và Authentication đều thành công | Authorization từ chối; thường **403**; có thể kèm `insufficient_scope` |
| Client gửi token trong query khi chỉ bật header | Resolver không nhận query là nguồn token | Endpoint bảo vệ có thể **401** vì chưa xác thực |
| Token ở header và nguồn khác cùng được bật | Request mang nhiều nguồn mâu thuẫn | Resolver có thể từ chối theo xử lý `invalid_request` |
| Gateway gắn custom header nhưng backend vẫn chỉ đọc Authorization | Resolver không tìm thấy bearer | Request bị xử lý như không token nếu không có cơ chế xác thực khác |

Một response chuẩn khi thiếu token tại API được bảo vệ có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Khi token thực sự không hợp lệ, response có thể có dạng:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Đây là ví dụ minh họa: chi tiết header, `error_description`, `realm`, body và status phụ thuộc lỗi cụ thể cùng cấu hình entry point. Không tiết lộ nguyên chuỗi access token, decoded private claims, khóa bí mật hoặc stack trace trong error response. Với lỗi thiếu quyền, đừng trả `401 invalid_token` nếu JWT đã được xác thực thành công; trả `403` theo cơ chế authorization.

## 9. Kiểm thử trực tiếp DefaultBearerTokenResolver

Đây là lớp unit test Java 17+ dùng JUnit 5 và Spring Test trong project có `spring-boot-starter-test`, `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`. File `BearerTokenResolverTest.java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BearerTokenResolverTest {
    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void readsAuthorizationHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");
        request.addHeader(HttpHeaders.AUTHORIZATION,
            "Bearer abc.def_ghi");

        assertEquals("abc.def_ghi", resolver.resolve(request));
    }

    @Test
    void missingHeaderReturnsNull() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");

        assertNull(resolver.resolve(request));
    }

    @Test
    void ignoresQueryParameterByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");
        request.addParameter("access_token", "query-token");

        assertNull(resolver.resolve(request));
    }

    @Test
    void rejectsMalformedBearerHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/me");
        request.addHeader(HttpHeaders.AUTHORIZATION,
            "Bearer not a token");

        assertThrows(OAuth2AuthenticationException.class,
            () -> resolver.resolve(request));
    }

    @Test
    void formBodyMustBeEnabledExplicitly() {
        DefaultBearerTokenResolver formResolver =
            new DefaultBearerTokenResolver();
        formResolver.setAllowFormEncodedBodyParameter(true);

        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/api/legacy-action");
        request.setContentType(MediaType.APPLICATION_FORM_URLENCODED_VALUE);
        request.addParameter("access_token", "body-token");

        assertEquals("body-token", formResolver.resolve(request));
    }
}
```

Các kiểm thử trên xác minh **đầu ra của resolver**, không xác minh chữ ký JWT hoặc quyền truy cập API. Các chuỗi `abc.def_ghi` và `body-token` chỉ là test token theo cú pháp; chúng **không phải JWT có thể xác thực**. Đây là điểm rất quan trọng khi phân tích trường hợp resolver “lấy được token” nhưng endpoint vẫn trả 401.

Nếu đang sử dụng Maven:

```bash
mvn -Dtest=BearerTokenResolverTest test
```

Hoặc Gradle trong project tương ứng:

```bash
./gradlew test --tests BearerTokenResolverTest
```

Lệnh và tên task có thể khác nếu project có custom build logic hoặc test không nằm ở module gốc. Năm test dự kiến **PASS** trong project Spring Security 6 với dependencies trên; không có stdout nghiệp vụ riêng.

### 9.1. Kiểm thử end-to-end qua Resource Server

Unit test resolver chưa đủ. Cần các scenario chạy qua `BearerTokenAuthenticationFilter`, JWT verification, authorization và proxy:

| Scenario | Bằng chứng cần kiểm tra |
| --- | --- |
| Không token trên route được bảo vệ | 401, không chạy controller, `WWW-Authenticate` phù hợp |
| JWT hợp lệ gửi trong Authorization | Resolver thấy đúng token, decoder xác minh và endpoint 2xx nếu đủ quyền |
| JWT hết hạn / chữ ký sai | 401 `invalid_token`, không vào controller |
| Bearer header sai định dạng | Lỗi bearer có cấu trúc, không ghi raw token vào log |
| Token chỉ ở query | Không được xác thực qua nguồn query khi mặc định off |
| Token chỉ ở form | Không được xác thực qua form khi mặc định off |
| Header + query/form khi nguồn phụ được bật | Phân loại request mơ hồ, từ chối khi chính sách không cho phép |
| Gateway header giả mạo từ Internet | Gateway loại bỏ giá trị do client gửi; backend không tin cậy tự do |
| JWT hợp lệ nhưng thiếu scope | 403 từ authorization, không bị nhầm là lỗi resolver |
| CORS preflight từ browser | `OPTIONS`/CORS được xử lý đúng; client được phép gửi header Authorization tới origin cho phép |
| Log, tracing, reverse proxy/CDN | Không có token trong URL, query log, request log hoặc trace export |

HTTP thử thủ công bằng cURL (thay `TOKEN_HOP_LE` bằng token thực trong môi trường test và tránh đưa lệnh chứa secret vào lịch sử shell/log):

```bash
# Thiếu token tại protected endpoint: thường 401.
curl -i https://api.example.test/api/me

# Token hợp lệ qua header chuẩn: có thể 200 nếu audience/quyền đúng.
curl -i https://api.example.test/api/me \
  -H 'Authorization: Bearer TOKEN_HOP_LE'

# Token lỗi chữ ký/hết hạn/không hợp lệ: thường 401.
curl -i https://api.example.test/api/me \
  -H 'Authorization: Bearer invalid-token'

# Query token không được nhận theo mặc định: thường 401.
curl -i 'https://api.example.test/api/me?access_token=invalid-token'
```

**Không chạy ví dụ query với access token thật** vì sẽ đưa token vào URL. Với test tích hợp, dùng token giả ở những case lỗi, bảo vệ secret của test ở secret store/fixture phù hợp, và xóa/redact mọi dữ liệu nhạy cảm trong CI logs. Cú pháp cURL trên chỉ minh họa luồng, không cho biết response thực của một issuer/host giả.

## 10. Quy trình điều tra lỗi nhận bearer token

1. **Đọc request tại client trước:** header `Authorization` có đúng scheme `Bearer` và có token không; đang dùng URL/query/form/cookie thay vì header chuẩn?
2. **Kiểm tra CORS và trình duyệt:** request có thực sự gửi custom header tới API không, preflight `OPTIONS` có qua proxy/config CORS không, frontend có chuyển nhầm token sang cookie/query không?
3. **Xác định SecurityFilterChain:** request có đi vào chain cấu hình `oauth2ResourceServer` không; resolver nào được gắn vào chain đó? Một ứng dụng có nhiều chain không nên mặc định một bean sẽ áp cho tất cả.
4. **Phân biệt resolution và verification:** resolver trả `null`, ném exception hay trả chuỗi? Nếu trả chuỗi, decoder/introspection có từ chối token vì signature, issuer, expiry, audience hoặc network introspection không?
5. **Đối chiếu error contract:** 401 vì không hoặc sai xác thực; 403 vì authenticated nhưng không đủ quyền. Quan sát `WWW-Authenticate` trước khi đoán từ response body.
6. **Kiểm tra từng trust boundary:** gateway có xóa/ghi lại header tùy biến không? Backend có thể bị gọi trực tiếp không? Logging có che `Authorization` và các header token khác?
7. **Chạy regression:** header hợp lệ, token lỗi, query/form bị tắt, header giả mạo, token hết hạn, thiếu quyền, API browser/CORS. Xác nhận request thất bại không thực hiện side effect.

### Lỗi triển khai thường gặp

- Cho rằng `BearerTokenResolver` xác thực JWT; thực tế nó chỉ trích chuỗi.
- Bật `setAllowUriQueryParameter(true)` vì một client thiếu khả năng gửi header.
- Tự đọc token từ cookie rồi bỏ qua CSRF hoặc mặc định coi cookie là header.
- Ghi cả `Authorization`, `Proxy-Authorization`, URL chứa `access_token` vào log để debug.
- Chuyển sang header “nội bộ” nhưng không để gateway strip header do client cung cấp.
- Bật form-urlencoded token trên mọi POST, không xét body logging hoặc request gửi cả header + form.
- Không kiểm tra claim `aud` vì issuer/JWKS đã hợp lệ.
- Nhầm 401 token hết hạn với 403 thiếu scope/authority.
- Tin rằng token ở header an toàn trước XSS hoặc mạng không dùng TLS.
- Dùng mã resolver tự viết tự động fallback query/cookie mà không có hợp đồng bảo mật.

## 11. Checklist quyết định nguồn token

- [ ] Với API thông thường, nhận `Authorization: Bearer TOKEN` qua HTTPS và giữ query/form options ở mặc định false.
- [ ] Chỉ cho phép nguồn khác khi có lý do giao thức rõ ràng, phạm vi endpoint/client cụ thể và test.
- [ ] Nếu dùng gateway custom header, gateway xóa header do client đặt và backend chỉ tin request đến từ gateway đã được bảo vệ.
- [ ] Nếu browser dùng cookie làm credential, xem lại CSRF, SameSite, Secure, HttpOnly và kiến trúc BFF/session.
- [ ] Resource Server kiểm tra chữ ký/introspection, issuer, expiry, audience, scopes/quyền độc lập với bước nhận token.
- [ ] CORS, reverse proxy, logs, APM, metrics, cache và CI không làm lộ bearer token.
- [ ] Có unit test resolver và integration test filter chain/HTTP 401/403 với cả các nguồn bị cấm.
- [ ] Không dùng access token dài hạn trong URL hoặc response lỗi.

**Ghi nhớ:** Trong Spring Security Servlet Resource Server, `DefaultBearerTokenResolver` **mặc định nhận bearer token từ header `Authorization`**, còn nguồn form body/query được tắt. Hãy giữ lựa chọn an toàn này, chỉ nới nguồn nhận token khi thật sự cần, và kiểm chứng trust boundary trước khi thay header. Dù resolver nhận thành công, JWT/opaque token vẫn phải được **xác thực và phân quyền** ở các bước sau.
