# OpaqueTokenAuthenticationProvider và OAuth 2.0 Token Introspection trong Spring Security

## 1. Mục tiêu học tập và vấn đề cần giải quyết

Một Resource Server (RS) nhận HTTP request chứa `Authorization: Bearer <access-token>` cần biết token có còn hiệu lực và cấp được những quyền nào. Với **opaque token**, nội dung token không được ứng dụng phân tích trực tiếp; RS thường hỏi Authorization Server (AS) qua **OAuth 2.0 Token Introspection** theo [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662). Spring Security cung cấp `OpaqueTokenAuthenticationProvider` trong kiến trúc **Servlet** để thực hiện xác thực này bằng một `OpaqueTokenIntrospector`.

Sau bài học, bạn cần làm rõ được:

1. Opaque access token, Bearer token, token introspection khác nhau ra sao; vì sao “opaque” mô tả cách RS đối xử với giá trị token, không phải một thuật toán mã hóa.
2. Đường đi từ `BearerTokenAuthenticationFilter` → `BearerTokenAuthenticationToken` → `ProviderManager` → `OpaqueTokenAuthenticationProvider` → `OpaqueTokenIntrospector` → `BearerTokenAuthentication` trong Spring Security Servlet.
3. Nội dung yêu cầu/phản hồi của RFC 7662, đặc biệt sự khác biệt giữa `{"active":true}`, `{"active":false}` và lỗi HTTP 401 do **client gọi introspection endpoint** chưa được AS cho phép.
4. Cách Spring Boot cấu hình introspection URI, client credential, scope-to-authority và chính sách bảo vệ endpoint; cách đọc thông tin principal sau khi xác thực.
5. Ranh giới giữa xác thực token và phân quyền theo `scope`, `aud`, `client_id`, `sub` hoặc tenant; vì sao không nên coi chỉ có `active=true` là đủ cho mọi API.
6. Khác biệt giữa Servlet `OpaqueTokenAuthenticationProvider` và WebFlux `OpaqueTokenReactiveAuthenticationManager`/`ReactiveOpaqueTokenIntrospector`.
7. Thiết kế timeout, lỗi AS, cache và revocation; kiểm thử bằng Java/JUnit và HTTP thật mà không làm lộ access token hoặc introspection credential.

**Bối cảnh kỹ thuật:** Spring Security 6.x, Spring Boot 3.x, Java 17+; API chính có thể tiếp tục tồn tại ở các dòng Spring Security mới. Một vài builder và mặc định thay đổi theo phiên bản, vì thế luôn kiểm tra javadoc của dependency mà project đang dùng. Bài tập trung vào **Bearer token authentication tại Resource Server**, không triển khai Authorization Server phát hành token và không trộn với OIDC `oauth2Login()`.

## 2. Từ Bearer token đến opaque token

### 2.1. Bearer nói về cách sử dụng; opaque nói về cách hiểu token

Một Bearer token là credential: ai sở hữu và đưa được token hợp lệ tới endpoint có thể được chấp nhận theo điều kiện và phạm vi ủy quyền của token. Ví dụ:

```http
GET /api/messages HTTP/1.1
Host: api.example.org
Authorization: Bearer N6E9XyGd7xq...redacted
```

Header `Authorization: Bearer` thuộc lớp OAuth 2.0 Bearer Token Usage [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750). **Bearer không đồng nghĩa JWT.** Access token có thể là chuỗi ngẫu nhiên opaque, JWT tự chứa claims, hoặc định dạng khác do AS định nghĩa.

Opaque token thường nhìn như một chuỗi không có cấu trúc hữu ích với RS:

```text
qL8rX9vP2... (chuỗi giả định, không phải token thật)
```

RS không được tùy tiện cắt chuỗi, base64-decode hay tự suy ra user/scope. Nó phải áp dụng giao thức hoặc cơ chế xác minh AS đã công bố. Giá trị opaque có thể là khóa tra cứu một bản ghi server-side, nhưng điều đó không phải điều kiện bắt buộc của RFC 7662.

Một JWT access token cũng **có thể đi qua introspection**. Cấu hình `opaquetoken` của Spring Security đặt tên theo **chiến lược kiểm tra qua AS**, không ép token phải là chuỗi ngẫu nhiên không giống JWT. Nếu chọn introspection đối với JWT, RS đang tin kết quả AS thay cho việc chỉ xác minh offline ở `JwtDecoder`.

### 2.2. Ai tham gia?

| Thành phần | Chức năng |
| --- | --- |
| Client | Nhận access token đúng grant, gửi token trong `Authorization: Bearer` tới RS |
| Authorization Server (AS) | Cấp token, giữ chính sách active/revoked/expired, công bố introspection endpoint cho bên được phép |
| Resource Server (RS) | Xác thực Bearer token và thực thi phân quyền trên API của mình |
| Introspection client | Danh tính/credential mà RS dùng để gọi AS introspection endpoint; **khác** Bearer token do caller đưa vào |
| Spring Security | Đọc Bearer header, gọi introspector, tạo `Authentication` và quyết định quyền theo chính sách ứng dụng |

```text
Client                    API / Resource Server                      Authorization Server
  |                              |                                           |
  | GET /api/messages            |                                           |
  | Authorization: Bearer T      |                                           |
  |----------------------------->|                                           |
  |                              | POST /introspect                          |
  |                              | Basic <RS client credentials>            |
  |                              | form token=T                              |
  |                              |------------------------------------------>|
  |                              |             {active:true,scope:...,sub:...}|
  |                              |<------------------------------------------|
  |                              | Tạo Authentication, kiểm tra quyền         |
  |<-----------------------------| 200 / 401 / 403 theo kết quả              |
```

Client của API **không** cần biết introspection client secret. RS không gửi client secret này cho browser/mobile. Một request token không hợp lệ không được tự động retry sang endpoint introspection khác hoặc bỏ qua validation.

## 3. RFC 7662: Request, response và semantics

### 3.1. Request introspection

RS gọi HTTPS endpoint do AS cung cấp. RFC 7662 dùng `application/x-www-form-urlencoded`, thường là `POST`:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.org
Authorization: Basic <base64-of-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<bearer-token-presented-to-api>&token_type_hint=access_token
```

Trong mẫu này có **hai nhóm credential khác nhau**:

- `Authorization: Basic ...`: RS chứng minh với AS rằng mình được quyền introspect token. AS có thể dùng phương thức client authentication khác theo cấu hình.
- `token=...`: access token mà client ngoài gửi cho RS, cần kiểm tra. Token không được đi vào URL query hoặc log.
- `token_type_hint=access_token`: tùy chọn, chỉ là gợi ý cho AS; không biến giá trị gửi lên thành access token và không thay thế kiểm tra AS.

Không gửi `client-secret` qua HTTP không mã hóa. Không dùng lại token client đưa vào làm authentication credential của RS tới introspection endpoint, trừ khi AS có một mô hình authorization có kiểm soát yêu cầu như vậy.

### 3.2. Phản hồi khi token đang active

Một phản hồi minh họa:

```json
{
  "active": true,
  "scope": "messages:read messages:write",
  "client_id": "web-client",
  "sub": "user-42",
  "username": "alice",
  "token_type": "Bearer",
  "exp": 1900000000,
  "iat": 1899990000,
  "aud": "messages-api",
  "iss": "https://auth.example.org"
}
```

Đây là dữ liệu **minh họa**. `exp`/`iat` là Unix timestamps (giây kể từ epoch); giá trị thực do AS quyết định, và AS không bắt buộc phải trả tất cả thuộc tính trong ví dụ. Các claims quan trọng:

| Thuộc tính | Vai trò | Điều cần tránh |
| --- | --- | --- |
| `active` | Boolean **bắt buộc** theo RFC 7662, thể hiện AS coi token có đang active tại ngữ cảnh truy vấn | Không suy ra rằng token có quyền truy cập mọi resource |
| `scope` | Danh sách scope dạng chuỗi phân tách bằng dấu cách | Không gán tự động thành role nghiệp vụ ngoài policy |
| `client_id` | OAuth client đã được cấp token | Không nhầm với introspection client's `client_id` |
| `sub` | Subject nếu token gắn với người dùng hoặc principal | Không mặc định là email/username; client credentials grant có thể khác |
| `username` | Tên có thể đọc được nếu AS cung cấp | Không nên coi là định danh duy nhất xuyên tenant/issuer |
| `aud` | Đích dự kiến sử dụng token, nếu được AS cung cấp | Phải xác định policy audience của API |
| `iss` | Issuer, nếu AS cung cấp | Phải đối chiếu nguồn phát hành theo hợp đồng trust |
| `exp`, `iat`, `nbf` | Hết hạn, thời điểm cấp, chưa có hiệu lực (khi có) | Không nhầm giây epoch với milliseconds |
| `token_type` | Loại token | Đừng tự diễn giải loại token qua độ dài/ký tự |
| `jti` | Định danh token khi có | Không cần log toàn bộ token để correlation |

AS có thể cố tình chỉ trả một tập thông tin tối thiểu cho RS cụ thể để bảo vệ riêng tư. RS không được giả định `email`, `groups`, `roles`, `aud` luôn hiện diện. Nếu policy bắt buộc một claim mà AS không trả, lựa chọn đúng là **fail closed** hoặc điều chỉnh hợp đồng AS/RS, thay vì tự suy đoán.

### 3.3. Token inactive hoặc không được phép tiết lộ

Phản hồi theo chuẩn:

```json
{
  "active": false
}
```

AS có thể trả như vậy khi token hết hạn, bị thu hồi, không tồn tại, hoặc RS **không được biết thông tin** về token. RS không nên phân biệt chi tiết các nguyên nhân này ở response trả cho caller, vì có thể giúp dò token.

Điểm rất quan trọng: **HTTP 200 với `{"active":false}` là phản hồi introspection hợp lệ**, không phải lỗi giao thức. Introspector phải từ chối xác thực token; không được đọc status 200 rồi cho phép request.

### 3.4. Lỗi khi gọi introspection endpoint

Một RS cấu hình sai introspection client credentials có thể gặp:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="..."
```

Đây là **HTTP 401 từ AS gửi cho RS**, không đồng nghĩa với HTTP 401 mà API trả cho caller Bearer token. Nếu AS timeout/5xx, RS đang không biết token active hay không. Chính sách an toàn là **không tự coi token active**; theo nhu cầu availability có thể trả 503/5xx với xử lý lỗi được kiểm soát. Không ẩn lỗi mạng bằng cách trả một `OAuth2AuthenticatedPrincipal` mặc định có quyền.

**Phân biệt ba kết quả:**

1. Introspection HTTP 200, `active=true`, metadata hợp lệ → có thể tạo authentication, sau đó vẫn kiểm tra authorization.
2. Introspection HTTP 200, `active=false` → authentication bị từ chối (thường API 401).
3. Introspection endpoint 401/403/5xx/timeout/malformed response → lỗi giao tiếp/xác thực client/hợp đồng AS; fail closed, log an toàn và theo dõi vận hành, tránh cho qua.

## 4. Spring Security Servlet: OpaqueTokenAuthenticationProvider làm gì?

Trong Spring Security Servlet, tầng xác thực Bearer token thường có chuỗi:

```text
HTTP Servlet request
   |
   v
BearerTokenAuthenticationFilter
   |  BearerTokenResolver lấy token từ Authorization header
   v
BearerTokenAuthenticationToken (yêu cầu xác thực, chưa được tin)
   |
   v
AuthenticationManager / ProviderManager
   |
   v
OpaqueTokenAuthenticationProvider
   |  supports(BearerTokenAuthenticationToken)
   |  gọi introspector.introspect(rawToken)
   v
OpaqueTokenIntrospector
   |  HTTPS tới AS introspection
   |  kiểm tra response theo hợp đồng RFC 7662
   v
OAuth2AuthenticatedPrincipal + attributes/authorities
   |
   v
OpaqueTokenAuthenticationConverter (mặc định hoặc custom)
   |
   v
BearerTokenAuthentication (đã xác thực)
   |
   v
SecurityContextHolder của Servlet request
   |
   v
authorizeHttpRequests / method security / controller
```

`OpaqueTokenAuthenticationProvider` là `AuthenticationProvider` ở package:

```java
org.springframework.security.oauth2.server.resource.authentication
    .OpaqueTokenAuthenticationProvider
```

Nó nhận một `OpaqueTokenIntrospector` và dùng kết quả introspection để tạo `Authentication`. Trong cách cấu hình tiêu chuẩn, bạn **không cần tự khởi tạo provider**: `oauth2ResourceServer(...opaqueToken(...))` để Spring Security nối filter, manager, provider, introspector và converter.

Các trách nhiệm tách biệt:

- **BearerTokenAuthenticationFilter:** xác định credential Bearer từ request; thiết lập `SecurityContext` khi authentication thành công.
- **ProviderManager:** chọn một provider hỗ trợ loại authentication request.
- **OpaqueTokenAuthenticationProvider:** xác thực token dựa trên introspector, chuyển principal/attributes thành authentication.
- **OpaqueTokenIntrospector:** giao diện `introspect(String token)`; triển khai có thể gọi AS, cache, kiểm tra audience và map authorities.
- **OpaqueTokenAuthenticationConverter:** biến kết quả introspection thành token authentication. Đừng tùy tiện đặt tất cả kết quả thành authenticated mà không xác thực.
- **Authorization layer:** so scope/roles/attributes với quyền tài nguyên, hoàn toàn tách khỏi việc xác định token active.

API provider công khai còn có `supports(Class<?>)`, `authenticate(Authentication)` và `setAuthenticationConverter(...)`. Dòng Spring Security 6.x hỗ trợ cấu trúc này; thay đổi về authorities bổ sung hoặc builder giữa các phiên bản không làm thay đổi nguyên tắc: **introspection trước, authorization sau**.

### Chú ý với tên gọi “opaque”

Tên `OpaqueTokenAuthenticationProvider` **không** có nghĩa provider tự giải mã token hoặc có một thuật toán validate chuỗi opaque. Nó **ủy quyền cho introspector**. Việc AS trả về token active mới là tín hiệu kiểm tra chính; nội dung scope/claim được truyền cho authorization.

## 5. Mapping từ introspection response đến Authentication và authorities

Giả sử AS trả:

```json
{
  "active": true,
  "sub": "alice-id-42",
  "scope": "messages:read messages:write",
  "client_id": "reader-client"
}
```

Với cấu hình mặc định, Spring Security chuyển các scope thành `GrantedAuthority` có tiền tố `SCOPE_`:

```text
messages:read  -> SCOPE_messages:read
messages:write -> SCOPE_messages:write
```

Do đó endpoint yêu cầu `hasAuthority("SCOPE_messages:read")` không nên viết thành `hasAuthority("messages:read")`, trừ khi đã cấu hình một converter riêng cố ý bỏ tiền tố.

Thông tin sau xác thực có thể truy cập qua:

- `BearerTokenAuthentication`: một implementation `Authentication` cho Bearer token đã kiểm tra; `getTokenAttributes()` cung cấp claims introspection.
- `OAuth2AuthenticatedPrincipal`: principal chứa `getName()`, `getAttributes()` và `getAuthorities()`; có thể inject bằng `@AuthenticationPrincipal`.
- `Authentication#getName()`: thường được ánh xạ theo `sub` nếu AS trả. Không chắc là email/tên hiển thị.
- `SecurityContextHolder`: chứa authentication ở Servlet request; trong WebFlux dùng reactive context.

Ví dụ controller Servlet, **trích đoạn** trong `@RestController`:

```java
@GetMapping("/api/subject")
String subject(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return principal.getAttribute("sub") == null
            ? "subject-not-provided"
            : String.valueOf(principal.getAttribute("sub"));
}
```

Nó chỉ minh họa cách đọc attribute từ principal; thông tin subject có thể thiếu nếu AS không trả, khi đó policy bảo mật cần quyết định có được chấp nhận hay không. Không dùng `username`/email mà AS không bảo đảm là duy nhất để tự cấp quyền đối tượng người dùng.

**Authentication không bằng authorization.** Một introspection response có `active=true` và scope `profile:read` không nên mở endpoint `/api/admin/delete`. Vai trò nghiệp vụ như `ROLE_ADMIN`, resource ownership, tenant boundary phải đến từ dữ liệu đáng tin và được kiểm tra đúng nơi.

## 6. Cấu hình Spring Boot Resource Server dùng introspection

### 6.1. Dependencies

Trong **project Spring Boot 3.x Java 17+ đã cấu hình plugin Spring Boot/Dependency Management**, dùng Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

`spring-boot-starter-web` chọn mô hình **Servlet**; phần WebFlux ở mục 10 có dependency thay thế. Đừng đưa cả hai starter vào cùng một ứng dụng chỉ vì muốn thử code, vì Spring Boot sẽ chọn web application type theo quy tắc auto-configuration.

### 6.2. application.yml

Lưu vào `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "${INTROSPECTION_URI}"
          client-id: "${INTROSPECTION_CLIENT_ID}"
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Dùng biến môi trường thật cho URI/client ID/secret. Ví dụ URI thường theo provider: `https://auth.example.org/oauth2/introspect`. **Không** commit client secret hoặc access token thật vào repository. URI phải là HTTPS có certificate/host được xác minh; dùng network policy để RS chỉ gọi endpoint được phép.

Ba property `spring.security.oauth2.resourceserver.opaquetoken.*` là cấu hình Spring Boot tiêu chuẩn. Chúng phục vụ Resource Server nội bộ, **khác** `spring.security.oauth2.client.registration.*` dùng khi ứng dụng đóng vai OAuth client/`oauth2Login()`.

### 6.3. Java class hoàn chỉnh trong Spring Boot Servlet

Đặt file `src/main/java/example/opaque/OpaqueResourceServerApplication.java`:

```java
package example.opaque;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OpaqueResourceServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueResourceServerApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/messages")
                        .hasAuthority("SCOPE_messages:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/me")
        Map<String, Object> me(BearerTokenAuthentication authentication) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("name", authentication.getName());
            result.put("authorities", authentication.getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
            return result;
        }

        @GetMapping("/api/messages")
        String messages() {
            return "You may read messages";
        }
    }
}
```

**Tính chất của ví dụ:**

- Có `main`, `@SpringBootApplication` và controller; biên dịch được khi project có dependencies nêu trên và JDK 17+.
- `HttpSecurity` tạo Servlet `SecurityFilterChain`. `oauth2ResourceServer(...opaqueToken(...))` dùng introspector mà Boot tạo từ `application.yml`.
- `/api/me` yêu cầu authenticated; `/api/messages` còn yêu cầu `SCOPE_messages:read`.
- Không cấu hình login form, session login hoặc phát hành token. Caller phải có access token do **AS thật** cấp.
- Controller không trả raw token, client secret hoặc toàn bộ introspection claims. Đây là cách giảm nguy cơ lộ dữ liệu trong bài học.
- Trong API stateless, bearer authentication được thiết lập theo từng request; việc gọi `POST /logout` ở API không mặc định làm opaque token mất hiệu lực tại AS.

Chạy bằng Gradle wrapper của project:

```bash
./gradlew bootRun
```

Windows: `gradlew.bat bootRun`. Application chỉ khởi chạy thành công khi có dependencies, cấu hình và môi trường thích hợp; kết quả xác thực chỉ có thể kiểm tra với AS/introspection endpoint thật.

### 6.4. Thử gọi API bằng curl

Ví dụ POSIX shell, với `ACCESS_TOKEN` đã lấy hợp lệ từ AS:

```bash
curl -i http://localhost:8080/api/me

curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me

curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/messages
```

Kỳ vọng theo cấu hình chuẩn:

| Request | Kết quả cần quan sát |
| --- | --- |
| Không có Bearer token | Thường HTTP **401 Unauthorized**; có `WWW-Authenticate: Bearer` |
| Token active, metadata hợp lệ | `/api/me` trả 200 cùng principal name/authorities |
| Token active nhưng thiếu `messages:read` | `/api/messages` trả **403 Forbidden** |
| Token active có scope `messages:read` | `/api/messages` trả 200, body `You may read messages` |
| Token inactive/invalid | Thường HTTP **401 Unauthorized** |
| AS introspection timeout/5xx | Không được coi token hợp lệ; HTTP status phụ thuộc error handling, cần quan sát và có chính sách fail closed |

Nếu chạy curl từ trình duyệt hoặc dùng Postman, luôn bảo vệ token. Không gửi token thật vào issue tracker, screenshot log, URL query hoặc paste công khai.

## 7. Tạo OpaqueTokenAuthenticationProvider trực tiếp để hiểu cơ chế

Trong ứng dụng thật nên ưu tiên DSL của mục 6. Nhưng khi học hoặc unit-test provider, ta có thể tự tạo `OpaqueTokenIntrospector` giả lập để kiểm chứng cách provider chuyển một Bearer credential thành `Authentication`.

**Lưu ý:** introspector giả lập bên dưới chỉ dành cho test. Nó **không gọi AS**, và vì vậy không được copy vào production để chấp nhận token dựa trên phép so chuỗi.

Tệp `src/test/java/example/opaque/OpaqueTokenProviderTest.java`; thêm dependency JUnit thông qua `spring-boot-starter-test`:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Java test:

```java
package example.opaque;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.junit.jupiter.api.Assertions.*;

class OpaqueTokenProviderTest {

    @Test
    void convertsIntrospectionPrincipalToBearerAuthentication() {
        OpaqueTokenIntrospector fakeIntrospector = token -> {
            assertEquals("test-opaque-token", token);

            return new DefaultOAuth2AuthenticatedPrincipal(
                    "alice",
                    Map.of(
                            "sub", "alice",
                            "scope", List.of("messages:read")),
                    List.of(
                            new SimpleGrantedAuthority(
                                    "SCOPE_messages:read")));
        };

        OpaqueTokenAuthenticationProvider provider =
                new OpaqueTokenAuthenticationProvider(fakeIntrospector);

        Authentication result = provider.authenticate(
                new BearerTokenAuthenticationToken("test-opaque-token"));

        assertNotNull(result);
        assertInstanceOf(BearerTokenAuthentication.class, result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(authority -> authority.getAuthority()
                        .equals("SCOPE_messages:read")));
    }
}
```

Với JDK 17 và Gradle project có test dependency, chạy:

```bash
./gradlew test
```

Mục tiêu: một test **PASS** khi fake introspector trả `OAuth2AuthenticatedPrincipal` cho token được kiểm soát. Kết quả xác minh provider/converter **không chứng minh** RFC 7662 HTTP exchange hoạt động, không kiểm chứng chứng thực client của RS ở AS và không kiểm tra tính hiệu lực của một token thật. Phải có integration test riêng với AS hoặc HTTP mock server.

**Có nên tự tạo `ProviderManager` bằng tay?** Thông thường không. Spring Security DSL tự đăng ký manager/provider thích hợp. Tạo thủ công filter/provider có thể vô tình bỏ qua token resolver, exception translation, SecurityContext setup và request matcher.

## 8. Đổi claims thành quyền nghiệp vụ: mapper và audience validation

`active=true` trả lời câu hỏi “AS cho rằng token đang active ở ngữ cảnh truy vấn này”. Nó **không đủ** để một RS cho phép mọi request. Ít nhất cần xác định resource/audience của token và quyền phù hợp endpoint.

### 8.1. Chỉ dùng scope được AS xác nhận

Nếu response có `scope="messages:read"`, Spring mặc định cho authority `SCOPE_messages:read`. Khi cần ánh xạ claims tổ chức thành authorities tùy chỉnh, đặt logic ở một `OpaqueTokenIntrospector` wrapper hoặc `OpaqueTokenAuthenticationConverter` theo API phiên bản đang dùng.

Ví dụ **trích đoạn trong class cấu hình Java 17**, ánh xạ không mở rộng quyền:

```java
@Bean
OpaqueTokenIntrospector validatingIntrospector(
        @Value("${app.security.expected-audience}") String expectedAudience,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
        String uri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
        String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
        String clientSecret) {

    OpaqueTokenIntrospector delegate =
            new SpringOpaqueTokenIntrospector(uri, clientId, clientSecret);

    return token -> {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object audiences = principal.getAttribute("aud");

        boolean allowed = expectedAudience.equals(audiences);
        if (audiences instanceof java.util.Collection<?> values) {
            allowed = values.contains(expectedAudience);
        }

        if (!allowed) {
            throw new BadOpaqueTokenException("Token audience rejected");
        }

        return principal;
    };
}
```

Đoạn trên là **trích đoạn cần đặt trong `@Configuration` và import `@Bean`, `@Value`, `OpaqueTokenIntrospector`, `SpringOpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, `BadOpaqueTokenException`**. Nó minh họa fail-closed theo `aud`; chỉ dùng khi AS bảo đảm phản hồi `aud` theo hợp đồng. Trong dự án dùng phiên bản mới hơn, constructor ba đối số của `SpringOpaqueTokenIntrospector` có thể deprecated; thay bằng builder do tài liệu phiên bản khuyến nghị. Nếu AS không trả `aud`, wrapper này sẽ **từ chối mọi token**, và bạn phải sửa hợp đồng AS/RS thay vì tự cho phép.

Đối với ứng dụng nhiều AS/tenant, cần giới hạn expected issuer và audience theo routing/trust policy. Không lấy `expectedAudience` từ request header hoặc query do client tùy ý truyền lên.

### 8.2. Role và ownership là cấp độ khác scope

Một token có `scope=orders:read` chỉ chứng minh quyền ứng dụng được đọc loại resource theo policy AS. Nếu API nhận `GET /orders/123`, nó còn phải kiểm tra tài nguyên 123 thuộc tenant/chủ sở hữu mà principal được phép xem.

Ví dụ service:

```java
// Trích đoạn minh họa: repository trả Optional<Order>.
Order order = repository.findById(orderId)
        .orElseThrow(NotFoundException::new);

if (!order.tenantId().equals(currentTenantId)) {
    throw new AccessDeniedException("Forbidden");
}
return order;
```

Đoạn này không phải file runnable (các kiểu repository, Order, exception là nghiệp vụ giả định); nó nhấn mạnh phân quyền dữ liệu. Không giải quyết bằng cách tự thêm `ROLE_ADMIN` chỉ vì introspection `active=true`.

### 8.3. Tránh lẫn tên subject

`sub` là subject do AS định nghĩa; `client_id` là OAuth client đã nhận token; `username`/`email` nếu có thường dùng hiển thị hoặc nghiệp vụ có điều kiện. Client credentials grant có thể không gắn với một người dùng. Không biến `client_id` hay email thành “người dùng đang đăng nhập” trong mọi mô hình.

## 9. Reactive WebFlux: OpaqueTokenReactiveAuthenticationManager

WebFlux không chạy `BearerTokenAuthenticationFilter` Servlet. Trong chuỗi Reactive, Spring Security xử lý credential qua WebFilter và `ReactiveAuthenticationManager`, thường dùng:

- `OpaqueTokenReactiveAuthenticationManager`, không phải Servlet `OpaqueTokenAuthenticationProvider`.
- `ReactiveOpaqueTokenIntrospector`, với method `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)`.
- `SpringReactiveOpaqueTokenIntrospector` làm việc qua non-blocking WebClient, hoặc implementation reactive riêng đã kiểm tra.
- `ReactiveSecurityContextHolder`/Reactor Context thay cho thread-local `SecurityContextHolder` để đọc authentication trong service reactive.

Pipeline khái quát:

```text
WebFlux ServerWebExchange
    |
    v
SecurityWebFilterChain -> authentication WebFilter
    |
    v
BearerTokenAuthenticationToken
    |
    v
OpaqueTokenReactiveAuthenticationManager
    |
    v
ReactiveOpaqueTokenIntrospector.introspect(token)
    |
    v
Mono<OAuth2AuthenticatedPrincipal> + authorities
    |
    v
Mono<Authentication> -> Reactor SecurityContext
    |
    v
authorizeExchange -> Handler trả Mono/Flux
```

### 9.1. Gradle và YAML

Trong ứng dụng WebFlux, dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Các property `spring.security.oauth2.resourceserver.opaquetoken.*` trong mục 6 có thể dùng tương tự. Boot sẽ cung cấp reactive introspector khi cấu hình WebFlux/Reactive Resource Server phù hợp.

### 9.2. Java 17 WebFlux security chain

Đây là **file cấu hình** của một ứng dụng WebFlux đã có `@SpringBootApplication`, tên file `src/main/java/example/opaque/ReactiveOpaqueSecurityConfig.java`:

```java
package example.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOpaqueSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/messages")
                        .hasAuthority("SCOPE_messages:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

Controller reactive có thể đọc `BearerTokenAuthentication` được framework inject và trả publisher:

```java
// Trích đoạn bên trong @RestController của ứng dụng WebFlux.
@GetMapping("/api/me")
Mono<String> me(BearerTokenAuthentication authentication) {
    return Mono.just(authentication.getName());
}
```

Với reactive service không ở biên HTTP, đọc context theo cách:

```java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

Hai đoạn ngắn trên là **trích đoạn** cần import đúng Reactor và Spring Security, không phải chương trình độc lập. Đừng gọi `.block()` hoặc `.subscribe()` thủ công chỉ để lấy principal, và đừng chuyển sang `ThreadLocal` sau khi đã chọn WebFlux.

### 9.3. Hiệu năng của introspection trong Reactive

`ReactiveOpaqueTokenIntrospector` cần dùng non-blocking API đúng nghĩa. Nếu bạn bọc một HTTP client blocking trong `Mono.just(blockingCall())` thì lời gọi vẫn thực thi ngay trên thread hiện tại; điều đó có thể chặn Netty event loop. Với legacy blocking bất khả kháng, cô lập ở `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` như giải pháp chuyển tiếp và giám sát timeout/concurrency. Trong ứng dụng mới, ưu tiên `SpringReactiveOpaqueTokenIntrospector`.

Việc WebFlux dùng non-blocking I/O **không làm introspection endpoint nhanh hơn**; mỗi request vẫn có network latency, timeouts và chi phí phía AS. Đánh giá nhu cầu cache và revoke gần thời gian thực ở mục 11.

## 10. So sánh introspection với JWT offline validation

| Tiêu chí | Opaque token / introspection | JWT offline signature validation |
| --- | --- | --- |
| RS hiểu cấu trúc token? | Không cần, chỉ chuyển tới AS | Có thể đọc signed claims theo JWT/JWS |
| Nguồn chân lý token active | AS qua introspection endpoint | Thường signature, issuer, audience, time claims tại RS |
| Revocation gần tức thời | Có thể biết ở lần introspection kế tiếp, trừ cache/AS propagation | Cần denylist/introspection/token ngắn hạn hoặc cơ chế bổ sung |
| Phụ thuộc AS trên request | Thường có, nếu không cache | Thường không, trừ khi cần JWKS refresh |
| Network latency | Thêm round trip tới AS | Thấp, không gọi AS mỗi request |
| Scalability | Phải tính capacity/cache/timeout của AS | Giảm tải AS nhưng chịu chi phí quản lý khóa/chính sách |
| Metadata thực tế | Do AS quyết định những claims nào được tiết lộ | Claims nằm trong token, có thể bị client nhìn thấy |
| Rủi ro chính | AS outage, cache stale, introspection credential | Token chưa hết hạn vẫn dùng sau thu hồi nếu RS không biết |

**Hình dạng token không bắt buộc chiến lược validation.** Một JWT vẫn có thể được gửi tới endpoint introspection. Khi đó `OpaqueTokenAuthenticationProvider` không còn “cố giải mã” JWT; AS vẫn trả trạng thái và attributes. Chính sách bảo mật phụ thuộc cách AS/RS phối hợp.

Về caching: với introspection không cache, thay đổi trạng thái token ở AS có thể phản ánh ở yêu cầu API sau. Nhưng nếu AS có replication delay, RS có cache positive hoặc gateway cache, thời điểm từ chối thực tế sẽ phụ thuộc TTL và cơ chế invalidation. Đừng tuyên bố “revoke ngay lập tức” chỉ vì có introspection.

## 11. Thiết kế timeout, cache, revocation và độ tin cậy

### 11.1. Timeout là một phần bảo mật và độ trễ

Mỗi inbound HTTP request có thể cần một outbound introspection HTTP call. Nếu AS chậm, latency của API bị tăng theo và thread/connection resources có thể cạn.

- Đặt connection timeout, response timeout và tổng deadline theo latency budget của API.
- Giới hạn concurrency, kích thước connection pool, request queue và retry; một lỗi AS không nên làm tài nguyên RS tăng vô hạn.
- Không retry mọi lỗi theo cách khuếch đại tải khi AS đang gặp sự cố; cân nhắc backoff/jitter và circuit breaker có xử lý fail closed.
- Log request correlation, status/latency/timeout của introspection nhưng **không log raw token** hoặc Authorization header.
- Bật TLS hostname verification và truststore/CA đúng. Không cấu hình “trust all certificates” chỉ để test chạy được.

Spring Security hỗ trợ thay introspector/HTTP client để điều chỉnh timeout; đường cấu hình cụ thể phụ thuộc version và việc dùng `RestClient`, `RestTemplate` hay `WebClient`. Nếu muốn mức timeout khác, đọc tài liệu `SpringOpaqueTokenIntrospector` / `RestClientOpaqueTokenIntrospector` hoặc `SpringReactiveOpaqueTokenIntrospector` phù hợp dependency thay vì giả định có một YAML property chung cho mọi implementation.

### 11.2. Cache introspection result

Cache positive là một tối ưu có đánh đổi: RS tránh gọi AS trên mọi request nhưng **token bị revoke có thể tiếp tục được chấp nhận trong thời gian cache còn hiệu lực**. Một chiến lược cần quyết định:

- Cache key không chứa raw token trong log/metrics; trong bộ nhớ hạn chế truy cập, tránh lộ token khi tạo key. Có thể dùng digest có khóa phù hợp nếu cache được chia sẻ.
- TTL positive ≤ thời gian hết hạn token và ≤ cửa sổ revoke latency mà sản phẩm chấp nhận; không bao giờ cache vô hạn.
- Cache negative nếu cần với TTL rất ngắn và khả năng chống đoán token. Không cache lỗi 5xx/timeout thành active.
- Tránh stampede: nhiều request cùng một token bị cache miss có thể dồn tải lên AS; coalescing/single-flight khi phù hợp.
- Không coi cache của introspector có thể tự biết token mới bị revoke; muốn cập nhật sớm cần event/invalidation hoặc rút ngắn TTL.

Theo RFC 7662, RS **có thể** cache introspection response theo chính sách; cần đánh giá token sensitivity, revocation requirement và privacy. Giới hạn TTL phải áp dụng nhất quán cả nơi sử dụng metadata sau authentication.

### 11.3. Fail closed khi AS không phản hồi

Lỗi timeout, DNS, TLS trust hoặc AS trả 5xx không chứng minh token inactive, nhưng cũng **không chứng minh token active**. Không dùng fallback:

```java
// SAI: tuyệt đối không dùng trong production.
return new DefaultOAuth2AuthenticatedPrincipal(
        "guest", Map.of("active", true),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
```

Đây là một **trích đoạn chống mẫu** (không phải file runnable). Bất kỳ cách “mặc định cho qua” nào khi hệ thống authentication bị lỗi đều có thể phá bảo mật. Với kiến trúc yêu cầu availability cao, bạn phải thiết kế chính sách rõ cho cache kết quả đã xác thực trước đó và giới hạn TTL, đối tượng API phù hợp, cơ chế audit; không dùng lỗi AS để nâng quyền.

### 11.4. Revocation và active state

AS có thể đánh dấu token revoked theo RFC 7009. RS sẽ biết ở lần introspection thành công tiếp theo nếu AS đã cập nhật trạng thái và cache không giữ phản hồi cũ. Nhưng revoke refresh token và revoke access token là những hành động khác nhau; local logout của ứng dụng browser cũng không tự revoke Bearer token được cấp cho API.

Nếu một yêu cầu đòi “đăng xuất ngay lập tức khỏi tất cả API”, thiết kế phải bao gồm vòng đời access token, revocation propagation, cache TTL, client session, AS policy và RS enforcement. `OpaqueTokenAuthenticationProvider` chỉ thực hiện xác thực tại thời điểm nhận request theo thông tin introspector trả.

## 12. Lỗi 401 và 403: phân biệt nguyên nhân

Một REST API sử dụng introspection nên có hành vi nhất quán:

| Trạng thái | Tầng xử lý | Hành vi mong đợi |
| --- | --- | --- |
| Không có Bearer header | Resource Server authentication entry point | 401 |
| Bearer header sai cú pháp | Token resolver/filter | 400 hoặc 401 theo trường hợp và RFC 6750 |
| Token active=false | Introspector/AuthenticationProvider | 401 |
| Token active=true, thiếu scope yêu cầu | Authorization filter | 403 |
| Token active=true nhưng không đúng audience | Custom validation fail closed | 401 hoặc error mapping tương ứng |
| AS trả 401 cho RS introspection client | Lỗi cấu hình/kết nối AS-RS | RS không cho qua, log lỗi credentials an toàn |
| AS timeout/5xx | Lỗi dependency | Fail closed; 5xx/503 có thể phù hợp sau xử lý lỗi |
| AS trả JSON không hợp lệ hoặc thiếu `active` | Introspection protocol validation | Từ chối/throw; không mặc định active |

Mã HTTP cụ thể ở tình huống lỗi AS phụ thuộc implementation exception translation và custom handler; đừng hard-code 401 cho tất cả outages nếu như vậy làm mất khả năng phát hiện lỗi vận hành. Khi Bearer token hợp lệ nhưng thiếu scope, tiêu chuẩn Bearer challenge có thể kèm `insufficient_scope`; không hiển thị claims nhạy cảm.

### 12.1. Tại sao một token “active” vẫn nhận 403?

Quy trình:

```text
AS: active = true; scope = "profile:read"
             |
             v
Spring: authenticated=true; authorities=[SCOPE_profile:read]
             |
             v
Rule: /api/messages needs SCOPE_messages:read
             |
             v
HTTP 403
```

Không sửa bằng cách chuyển `hasAuthority` thành `authenticated()` chỉ để request trả 200. Đó là bỏ đi phân quyền theo scope, không phải sửa xác thực token.

### 12.2. Tại sao RS thấy 401 dù AS đang trả HTTP 200?

Vì body AS là `{"active":false}`. RFC 7662 chủ ý dùng HTTP 200 để trả kết quả truy vấn hợp lệ về **một token không hợp lệ**. RS phải xét JSON `active`, không được xét riêng HTTP status.

## 13. Kiểm thử đúng tầng: unit, slice và integration

### 13.1. Unit test provider/introspector

Test `OpaqueTokenAuthenticationProvider` với stub introspector ở mục 7 để xác nhận loại authentication và authorities. Bổ sung test stub báo lỗi token inactive, kiểm tra ứng dụng không tạo authenticated principal, và test custom mapper/audience rejection.

### 13.2. Spring MVC security test

Có thể dùng `spring-security-test` với `MockMvc` để kiểm tra authorization rule. Ví dụ `SecurityMockMvcRequestPostProcessors.opaqueToken()` đưa authentication fixture vào test request:

```java
// Trích đoạn trong test có MockMvc và static import phù hợp.
mockMvc.perform(get("/api/messages")
                .with(opaqueToken().authorities(
                        new SimpleGrantedAuthority(
                                "SCOPE_messages:read"))))
        .andExpect(status().isOk());
```

**Lưu ý:** `opaqueToken()` trong Spring Security Test thường **bỏ qua HTTP introspection thực tế** để mô phỏng authentication; test này xác minh rule của ứng dụng, **không chứng minh AS client credentials/URI hoặc RFC 7662 response được xử lý đúng**.

### 13.3. Integration test với mock AS hoặc test AS thật

Đối với end-to-end xác thực, dựng một test introspection HTTP endpoint hoặc dùng AS đã cấu hình để kiểm tra:

1. RS gửi POST đúng URI, form field `token` và auth credential tới AS.
2. `active=true` với scope phù hợp → authenticated và 200 ở endpoint có quyền.
3. `active=true` thiếu scope → 403 ở endpoint bị bảo vệ.
4. `active=false` → 401, không có principal nào được trao quyền.
5. AS 401 do sai client secret → RS fail closed và ghi nhận lỗi vận hành.
6. AS timeout/TLS failure/invalid JSON → không cho qua; không retry vô hạn.
7. Audience không đúng hoặc tenant không đúng → từ chối dù `active=true`.
8. Revoke token ở AS, request trước/sau revoke và trước/sau cache TTL để đo độ trễ hiệu lực.
9. Nhiều request đồng thời và nhiều token để đo số lần gọi introspection, tải AS và tránh lẫn principal.

Có thể dùng WireMock, MockWebServer hoặc HTTP server giả lập có giới hạn chỉ trong test. Tránh mock cả authentication provider và introspection cùng lúc rồi kết luận đã thử xong giao thức.

### 13.4. Test WebFlux

Trong WebFlux, dùng `WebTestClient` + `spring-security-test` reactive support cho authorization unit tests. Khi cần kiểm chứng introspection thật, mock HTTP endpoint và giữ `SpringReactiveOpaqueTokenIntrospector` trong pipeline test. Kiểm tra hai request với hai Bearer tokens khác nhau song song, không để principal rơi vào `ThreadLocal` hoặc bị mix giữa Reactor contexts.

## 14. Bài tập Java 17 độc lập: mô hình quyết định sau introspection

Ví dụ sau **không thay thế introspector thật**; nó mô phỏng bước quyết định đơn giản để bạn nhìn thấy `active`, `aud`, `exp` và scope đóng vai trò độc lập. Không có dependency Spring Security; biên dịch bằng JDK 17+. Lưu thành `IntrospectionDecisionDemo.java`:

```java
import java.util.Set;

public class IntrospectionDecisionDemo {

    record Claims(boolean active, long exp, String audience,
                  Set<String> scopes) {}

    static boolean canReadMessages(Claims claims, long nowEpochSeconds) {
        return claims.active()
                && claims.exp() > nowEpochSeconds
                && "messages-api".equals(claims.audience())
                && claims.scopes().contains("messages:read");
    }

    public static void main(String[] args) {
        long now = 1000L;

        Claims allowed = new Claims(
                true, 1200L, "messages-api", Set.of("messages:read"));
        Claims revoked = new Claims(
                false, 1200L, "messages-api", Set.of("messages:read"));
        Claims wrongAudience = new Claims(
                true, 1200L, "other-api", Set.of("messages:read"));
        Claims expired = new Claims(
                true, 900L, "messages-api", Set.of("messages:read"));
        Claims missingScope = new Claims(
                true, 1200L, "messages-api", Set.of("profile:read"));

        System.out.println("allowed: " + canReadMessages(allowed, now));
        System.out.println("revoked: " + canReadMessages(revoked, now));
        System.out.println("wrong audience: "
                + canReadMessages(wrongAudience, now));
        System.out.println("expired: " + canReadMessages(expired, now));
        System.out.println("missing scope: "
                + canReadMessages(missingScope, now));
    }
}
```

Biên dịch và chạy:

```bash
javac IntrospectionDecisionDemo.java
java IntrospectionDecisionDemo
```

Stdout kỳ vọng **chính xác**:

```text
allowed: true
revoked: false
wrong audience: false
expired: false
missing scope: false
```

Những giá trị `now=1000` và `exp=1200` chỉ là dữ liệu giả định để test, không phải timestamp token thật. Trong môi trường thực, RS phải dựa vào introspector và chính sách đã thiết kế, không parse token opaque rồi tự tạo `Claims` như ví dụ. Bài tập chỉ minh họa rằng **valid token khác authorized request**.

## 15. Dùng curl để phân biệt introspection server và Resource Server

Thử nghiệm này giả định bạn có một AS thử nghiệm cấp token thật, và đã được cấp quyền gọi introspection endpoint. Đặt biến môi trường theo shell bạn đang dùng; ví dụ Bash:

```bash
# Các biến này được cấp bởi môi trường thử nghiệm, không đưa secret vào Git.
# INTROSPECTION_URI=https://auth.example.org/oauth2/introspect
# INTROSPECTION_CLIENT_ID=...
# INTROSPECTION_CLIENT_SECRET=...
# ACCESS_TOKEN=...

curl --silent --show-error \
  --request POST "$INTROSPECTION_URI" \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token"
```

Với AS hỗ trợ RFC 7662 và credential đúng, câu trả lời có thể là `{"active":true,...}` hoặc `{"active":false}`. Không có JSON/stdout cố định vì tình trạng token do AS quyết định. Nếu lệnh cho ra lỗi TLS, 401 hoặc kết nối thất bại, đó là tín hiệu khác với `active:false`.

Sau đó gọi RS:

```bash
curl --silent --show-error --include \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/messages
```

So sánh:

- AS báo active=true với `messages:read` và RS có quyền đúng → kỳ vọng 200.
- AS báo active=true nhưng không có scope → kỳ vọng 403.
- AS báo active=false → kỳ vọng 401.
- AS endpoint không phản hồi → RS không được cho qua.

Không echo token hoặc ghi cả command chứa secret vào log CI. Nếu môi trường shell lưu history, cân nhắc cung cấp biến qua secret manager và tài khoản test; không quay màn hình hiển thị raw token.

## 16. Troubleshooting theo dấu vết kỹ thuật

### Lỗi “InvalidBearerTokenException” hoặc API luôn 401

Kiểm tra có Bearer token đúng format không, token có thuộc AS đã cấu hình không, AS response có `active=true` không. Nếu AS trả `active=false`, đừng tìm cách ép provider trả true; cần xem token có hết hạn/revoked/sai môi trường hoặc RS không có quyền introspect token đó.

### Lỗi 401 từ AS khi introspection

Kiểm tra `client-id`/`client-secret` của **RS introspection client**, cấu hình Basic authentication, TLS, quyền gọi endpoint, secret rotation và cách encode ký tự đặc biệt theo Spring Security version. Từ 6.5 sang 7.x có thay đổi hướng dẫn xử lý encoding credential; nên ưu tiên builder/implementation khuyến nghị của phiên bản hiện dùng.

### Có authentication nhưng luôn 403

Đọc danh sách `GrantedAuthority` an toàn trong môi trường test; xem `scope` AS gửi có được phân tích thành `SCOPE_messages:read` không. Nếu dùng custom converter, kiểm tra không vô tình bỏ tiền tố, đổi kiểu dữ liệu hoặc làm mất authorities. Tiếp tục đối chiếu path matcher/role/tenant policy; không biến mọi endpoint thành `authenticated()` để “sửa” lỗi.

### Thời gian response tăng mạnh

Đo latency của introspection HTTP call, DNS/TLS handshake, pool và thread saturation. Dùng client có pooling/timeouts, hạn chế concurrency, xem cache policy và kiểm tra AS scalability. Với WebFlux, không dùng blocking HTTP client trên event loop.

### Revoke token rồi API vẫn trả 200

Xem RS có cache introspection kết quả active=true hay không, TTL bao lâu, AS có thực sự đánh dấu access token revoked không, AS replication delay và các tầng proxy. Nếu RS tự xác minh JWT offline, cấu hình đó **không dùng** chiến lược opaque introspection của bài này.

### Token active=true nhưng trỏ sai API

Kiểm tra `aud` / resource indicator / issuer / tenant và policy AS. Không dựa mỗi `active=true` khi token được dùng giữa nhiều APIs. Nếu AS không trả audience, phải mở rộng hợp đồng hoặc chọn chính sách fail closed phù hợp.

### Trả lỗi 500 khi AS down nhưng muốn 401

Đó là khác biệt giữa “credential chắc chắn không hợp lệ” và “dependency không xác định được trạng thái”. Không phải mọi lỗi AS nên bị che bằng 401; cấu hình error handling có chủ ý để không lộ secret nhưng vẫn quan sát được outage, dùng HTTP status được tài liệu hóa.

## 17. Checklist đưa vào hệ thống thật

1. **Ranh giới tin cậy:** RS chỉ tin introspection endpoint của AS được cấu hình; dùng HTTPS có hostname verification. Endpoint và secret do server quản lý.
2. **Hợp đồng token:** xác định issuer, audience/resource, scope, client identity, subject/tenant và claims nào RS phải có. Không suy đoán khi claim bị thiếu.
3. **Bật đúng stack:** Servlet dùng `OpaqueTokenAuthenticationProvider` qua `HttpSecurity.oauth2ResourceServer().opaqueToken()`; WebFlux dùng `OpaqueTokenReactiveAuthenticationManager` qua `ServerHttpSecurity`.
4. **Chính sách phân quyền:** `active` là bước authentication; cần scope/role/resource ownership. Không tự cấp quyền admin từ dữ liệu không tin cậy.
5. **Credential hygiene:** không log token/client secret, không gửi token trong query parameter, không lộ nội dung introspection ngoài yêu cầu.
6. **Lỗi AS:** fail closed với timeout, HTTP 401, 5xx và JSON không hợp lệ; có giám sát và xử lý lỗi vận hành.
7. **Hiệu năng:** timeout, connection pool, concurrency, cache TTL và circuit breaker phải phù hợp latency/revocation SLA.
8. **Revocation:** test AS revoke thật và đo thời điểm RS từ chối; nếu cache thì công bố độ trễ tối đa chấp nhận được.
9. **Kiểm thử:** tách unit provider/converter, authorization tests, integration RFC 7662, invalid token, wrong audience, AS outage và traffic concurrent.
10. **Phiên bản:** kiểm tra javadoc Spring Security đang dùng trước khi thay `SpringOpaqueTokenIntrospector` constructor/builder hoặc custom converter; tránh copy code 7.x vào 6.x mà chưa xác minh.

Ý chính cần ghi nhớ: **`OpaqueTokenAuthenticationProvider` không tự quyết định token có hợp lệ dựa trên chuỗi ký tự; nó dùng `OpaqueTokenIntrospector` để hỏi nguồn tin cậy, tạo `Authentication` rồi để Spring Security và nghiệp vụ thực hiện phân quyền.** Một token có `active=true` chỉ là điểm bắt đầu của quyết định truy cập.

## 18. Tài liệu chính thức

- [Spring Security 6.5 — Servlet OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): cấu hình, provider, introspector, scope mapping và tùy chỉnh.
- [Spring Security — OpaqueTokenAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html): constructor, `authenticate`, `supports` và converter.
- [Spring Security — OpaqueTokenReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html): reactive manager và `ReactiveOpaqueTokenIntrospector`.
- [Spring Security — WebFlux Opaque Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): reactive DSL, principal, authorities và introspection.
- [Spring Security — Migrating OAuth2 to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html): thay đổi khi chuyển phiên bản, xử lý client credential encoding.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cấu trúc request/response, `active` và security considerations.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền Bearer credential và mã lỗi.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): mô hình thu hồi token và quan hệ với introspection.
- [Spring Boot OAuth2 Resource Server Properties](https://docs.spring.io/spring-boot/reference/web/spring-security.html): cấu hình theo Boot và dependency.
