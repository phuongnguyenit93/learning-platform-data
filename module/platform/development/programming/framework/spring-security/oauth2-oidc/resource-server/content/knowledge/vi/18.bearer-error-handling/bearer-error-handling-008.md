# Phối hợp nội dung lỗi JSON với header, mã trạng thái đúng ngữ nghĩa

## 1. Mục tiêu: một phản hồi Bearer phải nhất quán từ HTTP đến JSON

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, client thường gửi OAuth 2.0 access token dưới dạng Bearer:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Khi request không được chấp nhận, API có ít nhất **ba lớp thông tin** cần phối hợp:

1. **HTTP status code:** kết quả theo HTTP, như `400`, `401`, `403`, `429` hoặc `503`.
2. **Response header `WWW-Authenticate`:** Bearer challenge và OAuth error parameters theo **RFC 6750** khi tình huống liên quan authentication/authorization của Bearer token.
3. **JSON response body:** giúp frontend, SDK và người vận hành hiểu lỗi, thường ở dạng JSON tùy chỉnh hoặc **Problem Details RFC 9457**.

Ví dụ một JWT sai chữ ký hoặc hết hạn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or the access token is invalid.",
  "code": "invalid_token"
}
~~~

Ví dụ cho thấy ba thành phần cùng chỉ ra authentication failure. Nếu một API trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status": 401, "error": "invalid_token"}
~~~

thì JSON nói lỗi nhưng status HTTP vẫn là **thành công**; browser, SDK, monitoring và proxy có thể xử lý sai. Không dùng `200 OK` cho authentication error chỉ để chuẩn hóa schema body.

**Phạm vi:** Spring MVC/Servlet Resource Server nhận JWT hoặc opaque access token, dùng `AuthenticationEntryPoint` và `AccessDeniedHandler` để tạo phản hồi bảo mật. OIDC login/session có response contract riêng, không nên gộp tự động.

## 2. RFC 6750: đúng lỗi phải đúng HTTP status

### 2.1. Ba mã Bearer error quan trọng

Theo **RFC 6750, mục 3.1**, ba Bearer error codes cốt lõi là:

| Bearer `error` | Khi nào? | HTTP status thường dùng | Hành động của client |
|---|---|---|---|
| `invalid_request` | Cách gửi Bearer token/request sai cấu trúc, lặp tham số hoặc dùng đồng thời nhiều cách truyền token | **400 Bad Request** | Sửa request |
| `invalid_token` | Token hết hạn, bị thu hồi, malformed hoặc không vượt qua authentication | **401 Unauthorized** | Lấy token hợp lệ mới hoặc xác thực lại |
| `insufficient_scope` | Token hợp lệ nhưng thiếu phạm vi quyền cần thiết | **403 Forbidden** | Xin quyền/scope đúng quy trình, không retry cùng token mãi |

Các status là khuyến nghị `SHOULD` theo RFC 6750, cần đọc cùng ngữ cảnh. Không đổi mọi `AccessDeniedException` hoặc mọi lỗi hệ thống thành `invalid_token`.

### 2.2. Request không có token

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

Response tiêu biểu:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required.",
  "code": "authentication_required"
}
~~~

**Lưu ý quan trọng:** `authentication_required` trong body là **mã lỗi do ứng dụng định nghĩa**, không phải một Bearer `error` được đăng ký trong RFC 6750.

Khi request không có bất kỳ thông tin authentication nào, RFC 6750 khuyến nghị Resource Server **không thêm `error` hay thông tin lỗi bổ sung vào challenge**. Vì vậy không mặc định trả:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

chỉ vì token bị thiếu.

### 2.3. Token sai hoặc hết hạn

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <INVALID_OR_EXPIRED_ACCESS_TOKEN>
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The access token could not be accepted.",
  "code": "invalid_token"
}
~~~

Những nguyên nhân có thể dẫn đến authentication failure của JWT Resource Server:

- Chữ ký JWS sai hoặc thuật toán `alg` không được cho phép.
- Token đã qua `exp` hoặc chưa đạt `nbf`.
- `iss` không khớp issuer tin cậy.
- `aud` không dành cho API này.
- Token không đạt profile/claim validators.
- JWKS không có khóa tin cậy để xác minh token.

Với opaque-token introspection, token bị AS trả `active:false` cũng thường bị từ chối. **Không phải mọi sự cố mạng khi tải JWKS/introspection đều là token sai**; cần phân biệt lỗi infrastructure khi map response.

Mô tả công khai nên tổng quát, tránh xuất nguyên exception message, token, issuer allowlist, thông tin khóa hoặc dữ liệu nội bộ.

### 2.4. Bearer request sai cấu trúc

Ví dụ client gửi token qua cả header và query trong khi resolver/hợp đồng không cho phép:

~~~http
GET /api/orders?access_token=abc HTTP/1.1
Authorization: Bearer def
~~~

Response hợp lý:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "The Bearer authentication request is malformed.",
  "code": "invalid_request"
}
~~~

Cần phân biệt **cách trình bày Bearer token/request sai** (`invalid_request`, 400) với **token đã được gửi nhưng không hợp lệ** (`invalid_token`, 401). Spring Security phân loại dựa trên `BearerTokenResolver` và các authentication exceptions.

### 2.5. Token hợp lệ nhưng thiếu scope

Giả sử Orders API yêu cầu:

~~~java
.hasAuthority("SCOPE_orders.write")
~~~

nhưng token chỉ được cấp `scope=orders.read`.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "The access token has insufficient privileges.",
  "code": "insufficient_scope"
}
~~~

Tham số `scope="orders.write"` là **tùy chọn** theo RFC 6750. Chỉ gửi required scope nếu server thật sự biết nó và chính sách cho phép tiết lộ.

`401` khác `403`: với 401, authentication thiếu hoặc thất bại; với 403, principal đã xác thực nhưng không được thực hiện thao tác. Frontend không nên liên tục refresh token trên một 403.

### 2.6. Không có quyền đối với tài nguyên cụ thể

Caller có `SCOPE_orders.read` nhưng order 42 thuộc tenant khác:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access to this order is not permitted.",
  "code": "resource_access_denied"
}
~~~

Một API cũng có thể chọn `404 Not Found` để che sự tồn tại của tài nguyên, khi chính sách yêu cầu. **Không tự đổi mọi lỗi ACL/owner/tenant thành `insufficient_scope`**, vì xin thêm OAuth scope không nhất thiết giải quyết vấn đề.

## 3. Bảng lựa chọn response theo ngữ nghĩa

| Tình huống | Status | Bearer header | JSON code ví dụ |
|---|---|---|---|
| Thiếu Bearer ở endpoint protected | 401 | Bearer challenge, thường không có `error` | `authentication_required` |
| JWT hết hạn/sai signature/issuer | 401 | `invalid_token` khi đúng branch | `invalid_token` |
| Opaque token inactive | 401 | `invalid_token` khi đúng branch | `invalid_token` |
| Header/request Bearer malformed | 400 | `invalid_request` | `invalid_request` |
| Token hợp lệ thiếu OAuth scope | 403 | `insufficient_scope` khi phù hợp | `insufficient_scope` |
| Token hợp lệ thiếu local role/ACL | 403 | Theo policy, không tự giả thiếu scope | `resource_access_denied` |
| Không tìm thấy hoặc không công bố resource | 404 | Không phải Bearer error | `resource_not_found` |
| Business request body sai schema | 400/422 theo policy | Không phải Bearer error | `invalid_body` |
| HTTP method không được hỗ trợ | 405 | Không phải Bearer error; có `Allow` | `method_not_allowed` |
| Bị quota/rate limit | 429 | Không phải `invalid_token`; có thể có `Retry-After` | `rate_limited` |
| JWKS/introspection service outage | 5xx hoặc xử lý hạ tầng phù hợp | Không tạo Bearer error giả | `dependency_unavailable` |
| Lỗi server không mong đợi | 500 | Không phải Bearer error | `internal_error` |

**Không phải mọi 400 đều là `invalid_request` của Bearer**. JSON body validation fail cũng có thể là 400 nhưng không liên quan `WWW-Authenticate`.

Đặc biệt, AS trả HTTP 401 **trong cuộc gọi introspection** có thể là vì client credentials của Resource Server sai; không có nghĩa bearer token của người gọi đã bị revoke.

## 4. Sơ đồ ra quyết định 400/401/403

~~~mermaid
flowchart TD
    A["Request đến protected API"] --> B{"Bearer request đúng cấu trúc?"}
    B -->|Không| C["400 invalid_request"]
    B -->|Có| D{"Có Bearer token?"}
    D -->|Không| E["401 Bearer challenge, không error"]
    D -->|Có| F{"Xác thực token thành công?"}
    F -->|Không| G["401 invalid_token khi phù hợp"]
    F -->|Có| H{"Đủ scope hành động?"}
    H -->|Không| I["403 insufficient_scope"]
    H -->|Có| J{"Tenant/owner/ACL cho phép?"}
    J -->|Không| K["403 hoặc 404 theo resource policy"]
    J -->|Có| L["Controller xử lý nghiệp vụ"]
    L --> M{"Nghiệp vụ bị lỗi?"}
    M -->|Có| N["4xx/5xx đúng ngữ nghĩa, không giả Bearer"]
    M -->|Không| O["Success response"]
~~~

Sơ đồ mô tả các đường đi chính, không bao quát toàn bộ ngoại lệ, CORS, rate limit hoặc nhiều authentication schemes. Mấu chốt: **status line phải đúng** trước khi thiết kế JSON.

## 5. `WWW-Authenticate`: giữ chuẩn RFC 6750

### 5.1. Request `Authorization` khác response `WWW-Authenticate`

Client gửi:

~~~http
Authorization: Bearer <token>
~~~

Server challenge:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Bearer challenge có thể chứa:

| Parameter | Vai trò |
|---|---|
| `realm` | Tên vùng resource protection |
| `error` | `invalid_request`, `invalid_token` hoặc `insufficient_scope` |
| `error_description` | Mô tả lỗi hợp lệ về cú pháp và an toàn |
| `error_uri` | URI giải thích lỗi |
| `scope` | Scope cần thêm khi thiếu privilege, nếu phù hợp |

Không phải mọi response cần mọi parameter. Không nhét raw token, refresh token, client secret hoặc stack trace vào header.

### 5.2. Không tự ghép giá trị chưa kiểm soát

Một cách dễ bị lỗi:

~~~java
response.setHeader(
    "WWW-Authenticate",
    "Bearer error_description=\"" + exception.getMessage() + "\""
);
~~~

Exception message có thể chứa ký tự điều khiển, thông tin khóa/issuer hoặc dữ liệu nhạy cảm. Việc ghép chuỗi thủ công còn có thể vi phạm cách quote/escape của challenge.

Ưu tiên **`BearerTokenAuthenticationEntryPoint`** và **`BearerTokenAccessDeniedHandler`** mà Spring Security cung cấp. Chúng có trách nhiệm dựng Bearer header và status theo OAuth2 errors/framework.

### 5.3. Phân biệt `error_description` và JSON `detail`

Không bắt buộc hai trường giống nhau. `error_description` là tham số trên HTTP authentication challenge, có quy tắc ký tự và độ dài cần xem xét. JSON `detail` hướng đến con người, có thể dùng câu chung.

Một chính sách bảo mật:

~~~text
Header:
  error="invalid_token"

Body:
  detail="The access token could not be accepted."

Internal logs:
  jwt_expired / issuer_mismatch / aud_missing
  correlationId=req-729e
~~~

Client nhận thông tin cần thiết, còn server giữ chi tiết chẩn đoán trong log có quyền truy cập hạn chế. Không dựa vào nội dung `detail` để điều khiển logic bảo mật.

### 5.4. Không làm mất các authentication challenges khác

HTTP có thể hỗ trợ nhiều authentication schemes trên cùng hệ thống. Một ứng dụng web có OIDC login/session, một API có Bearer Resource Server, hoặc còn Basic authentication. Không dùng một handler ghi đè mọi response thành `Bearer` mà không biết client đang ở security chain nào.

Khi cần tách UI và API:

~~~text
/api/**   -> Bearer + 401/403 + JSON
/web/**   -> Browser OIDC login + redirect/page
~~~

Dùng `securityMatcher` và thứ tự `SecurityFilterChain` có chủ đích, không để chain browser chặn API rồi trả HTML 302 login.

## 6. RFC 9457 Problem Details làm JSON response body

### 6.1. Những trường chuẩn

**RFC 9457** định nghĩa **Problem Details** với media type:

~~~http
Content-Type: application/problem+json
~~~

Một body:

~~~json
{
  "type": "https://api.example.test/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action.",
  "instance": "/api/orders/42",
  "code": "resource_access_denied",
  "traceId": "req-729e"
}
~~~

Trong đó:

- `type` định danh loại problem, ví dụ URI public có tài liệu; nếu vắng, mặc định là `about:blank`.
- `title` là câu ngắn ổn định của loại lỗi.
- `status` là HTTP status của response khi được tạo.
- `detail` là mô tả cho occurrence, không chứa chi tiết nhạy cảm.
- `instance` định danh occurrence nếu hữu ích, không nhất thiết phải đưa đường dẫn chứa PII.
- `code` và `traceId` là **extensions do API định nghĩa**, không phải trường RFC 9457 bắt buộc.

### 6.2. Actual HTTP status là nguồn chân lý

Theo RFC 9457, nếu body có `status` thì server phải đặt cùng status trên HTTP response:

~~~text
HTTP status = body.status
~~~

Sai:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json

{"status":403,"title":"Forbidden"}
~~~

Sai hơn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/problem+json

{"status":401,"code":"invalid_token"}
~~~

Hãy thiết lập status một lần theo kết quả xử lý bảo mật rồi tạo body dựa trên status đó. Nếu API gateway đổi status nhưng giữ JSON nguyên, cần sửa cách proxy xử lý chứ không bắt client chọn một giá trị tùy ý.

### 6.3. `code` JSON có bắt buộc bằng Bearer `error` không?

Không. Chúng thuộc hai lớp hợp đồng:

- `WWW-Authenticate` có **OAuth Bearer error** chuẩn theo RFC 6750.
- JSON `code` có thể là **mã ứng dụng**, ví dụ `authentication_required`, `invalid_token`, `forbidden`, `resource_access_denied`.

Một body `code="forbidden"` là một phân loại tổng quát, trong khi header có `error="insufficient_scope"` nêu chi tiết Bearer. Điều đó có thể chấp nhận nếu hợp đồng client nói rõ. Nếu muốn cùng `insufficient_scope` ở cả hai, hãy phân loại **đúng nguồn policy thiếu scope**, thay vì đoán bằng cách parse exception message.

### 6.4. Không bắt buộc sử dụng Problem Details

Một API đã có error envelope:

~~~json
{
  "error": {
    "code": "invalid_token",
    "message": "Authentication failed",
    "requestId": "req-729e"
  }
}
~~~

vẫn có thể dùng `application/json`. Nó cần đúng HTTP status và Bearer header. Không dùng `application/problem+json` cho JSON không tuân schema Problem Details.

## 7. Đường đi security filters khác Spring MVC controller

Spring Security xử lý Bearer authentication trong **Servlet filter chain**, trước controller:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["AuthenticationEntryPoint khi token sai"]
    B --> E["ExceptionTranslationFilter / AuthorizationFilter"]
    E --> F["AccessDeniedHandler khi thiếu quyền"]
    B --> G["DispatcherServlet"]
    G --> H["Controller / Service"]
    H --> I["@RestControllerAdvice cho MVC exceptions"]
~~~

Vì vậy chỉ viết:

~~~java
@RestControllerAdvice
public class GlobalErrors {
    @ExceptionHandler(Exception.class)
    public ProblemDetail error(Exception ex) {
        // ...
    }
}
~~~

**không đủ** để bắt tất cả authentication failures trong Bearer filter. `@RestControllerAdvice` thường xử lý exceptions do MVC đưa tới exception resolvers; filter có thể đã gửi 401/403 trước khi vào MVC.

Tệ hơn, nếu advice chung bắt mọi security exception và trả 200/500, nó có thể phá ngữ nghĩa mà Resource Server muốn áp dụng.

### 7.1. `AuthenticationEntryPoint`

Interface `org.springframework.security.web.AuthenticationEntryPoint` phụ trách response khi cần bắt đầu/challenge authentication. Resource Server có:

~~~java
org.springframework.security.oauth2.server.resource.web
    .BearerTokenAuthenticationEntryPoint
~~~

Implementation này dựa trên `BearerTokenError`, đặt HTTP status và `WWW-Authenticate`.

### 7.2. `AccessDeniedHandler`

Interface `org.springframework.security.web.access.AccessDeniedHandler` được dùng khi access denied.

Resource Server có:

~~~java
org.springframework.security.oauth2.server.resource.web.access
    .BearerTokenAccessDeniedHandler
~~~

Handler này tạo response RFC 6750 theo trạng thái authentication/security context. Nhưng không phải mọi `AccessDeniedException` ở domain layer nhất thiết là thiếu OAuth scope.

### 7.3. Vì sao nên cấu hình ở hai nơi?

`BearerTokenAuthenticationFilter` có thể gọi entry point trực tiếp trên authentication failure. Một số authorization failures được `ExceptionTranslationFilter` xử lý. Khi muốn đồng bộ JSON, cần chú ý **Resource Server configuration** và **`exceptionHandling(...)`**, tránh một đường trả body JSON còn một đường chỉ có header.

Trong Spring Security, mọi đường gọi có thể phụ thuộc version, filter chain và authentication mechanism. Test ở version thực tế để biết handler nào đã được gọi.

## 8. Cấu hình Spring Boot Resource Server cơ bản

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml` minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Issuer/audience là ví dụ và phải khớp hợp đồng Authorization Server. Để được xác thực, JWT phải vượt qua signature, issuer, audience, time và profile validation.

Một chain đơn giản:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Spring Security đã có Bearer error/challenge defaults. **Đừng tự xây challenge bằng chuỗi trước khi xác định default đã đáp ứng hợp đồng chưa.** Bổ sung JSON là một yêu cầu representation, không phải lý do thay đổi logic authentication.

## 9. Ví dụ Java: bọc Bearer handlers để thêm Problem JSON

Ví dụ dành cho **Spring Boot 3.x / Spring Security 6.x** với Servlet `jakarta.servlet.*` và Jackson `com.fasterxml.jackson.databind.ObjectMapper`. Nếu dùng Spring Boot 4.x hoặc Jackson 3, cần đối chiếu package JSON mapper thực tế.

Thiết kế:

1. Để `BearerTokenAuthenticationEntryPoint` đặt status/challenge cho authentication error.
2. Để `BearerTokenAccessDeniedHandler` đặt status/challenge cho access denied.
3. Chỉ bổ sung JSON khi response chưa committed.
4. Không ghi đè `WWW-Authenticate`, không gọi `sendError`, không phản chiếu exception message nhạy cảm.

### 9.1. Handler gộp hai interface

~~~java
package com.example.orders.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;

public final class BearerProblemHandlers
        implements AuthenticationEntryPoint, AccessDeniedHandler {

    private final ObjectMapper mapper;

    private final BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    private final BearerTokenAccessDeniedHandler deniedHandler =
        new BearerTokenAccessDeniedHandler();

    public BearerProblemHandlers(ObjectMapper mapper) {
        this.mapper = mapper;

        entryPoint.setRealmName("orders-api");
        deniedHandler.setRealmName("orders-api");
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        // Để Spring Security quyết định status và Bearer challenge.
        entryPoint.commence(request, response, exception);

        String code = "authentication_required";
        String detail = "Authentication is required.";

        if (exception instanceof OAuth2AuthenticationException oauth) {
            code = oauth.getError().getErrorCode();
            detail = "Authentication failed or the Bearer request is invalid.";
        }

        writeProblem(response, code, detail);
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException, ServletException {

        deniedHandler.handle(request, response, exception);

        // App code tổng quát: không giả định mọi deny là thiếu scope.
        writeProblem(
            response,
            "forbidden",
            "You do not have permission to perform this action."
        );
    }

    private void writeProblem(
            HttpServletResponse response,
            String code,
            String detail) throws IOException {

        if (response.isCommitted()) {
            return;
        }

        int status = response.getStatus();

        // Không thay status/challenge do delegate vừa thiết lập.
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("type", "about:blank");
        body.put(
            "title",
            HttpStatus.valueOf(status).getReasonPhrase()
        );
        body.put("status", status);
        body.put("detail", detail);
        body.put("code", code);

        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

**Những quyết định quan trọng:**

- **Missing token:** `AuthenticationException` không nhất thiết là `OAuth2AuthenticationException`; body có thể mang app code `authentication_required`, còn Bearer challenge không chứa `error` nếu framework xác định thiếu credentials.
- **Invalid token/request:** nếu Spring Security cung cấp `OAuth2AuthenticationException` và error code chuẩn, body dùng mã đó. Status vẫn do delegate đặt, có thể là 401 hoặc 400 tùy `BearerTokenError`.
- **Access denied:** body dùng app code `forbidden`; header do `BearerTokenAccessDeniedHandler` quản lý. Trong chain chủ yếu bảo vệ OAuth scopes, handler có thể nêu `insufficient_scope`. Nếu cần phân loại 403 domain-level, thiết kế policy và handler riêng, không suy đoán từ exception message.
- **`response.isCommitted()`:** tránh ghi lần thứ hai; nếu response đã committed quá sớm, phải chẩn đoán filter/handler đã ghi response trước đó.
- **`setStatus` thay vì `sendError`:** delegate đã thiết lập status, JSON writer không gọi `sendError` để tránh servlet container thay body bằng trang lỗi.
- **Không xuất raw lỗi nội bộ:** không thêm stack trace, nguyên nhân decoder, token string, issuer list hoặc client secret vào body.

Đoạn code không thực hiện Content Negotiation đầy đủ theo `Accept`; API đã xác định error representation cố định `application/problem+json`. Nếu có client chỉ chấp nhận định dạng khác, cần thiết kế content negotiation có chủ đích, nhưng không làm mất status/challenge.

### 9.2. Đăng ký handler trong API chain

~~~java
package com.example.orders.security;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    BearerProblemHandlers bearerProblems(ObjectMapper mapper) {
        return new BearerProblemHandlers(mapper);
    }

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            BearerProblemHandlers problems)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(problems)
                .accessDeniedHandler(problems)
                .jwt(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(problems)
                .accessDeniedHandler(problems)
            );

        return http.build();
    }
}
~~~

Cấu hình cùng handler ở **`oauth2ResourceServer(...)`** và **`exceptionHandling(...)`** giúp đi qua hai đường xử lý security đều có chance ghi Problem JSON. Với một ứng dụng có nhiều auth schemes, không áp dụng một Bearer handler này cho mọi security chain.

Nếu trộn `oauth2Login`/form login vào API chain, một challenge/redirect có thể bị đè. Nên tách `/api/**` và `/web/**` bằng các chain rõ ràng, đồng thời test thứ tự matching.

### 9.3. Vì sao không tự ghi `WWW-Authenticate` từ đầu?

Tự ghép:

~~~java
response.setHeader(
    "WWW-Authenticate",
    "Bearer realm=\"orders-api\", error=\"invalid_token\""
);
~~~

có thể bỏ quên:

- Missing-token challenge không nên có `invalid_token`.
- `invalid_request` có thể dùng status 400, không phải 401.
- `insufficient_scope` thường 403 và `scope` có thể tùy chọn.
- Encoding/escaping của `error_description`.
- Các authentication schemes/challenges khác.
- Những thay đổi/framework extensions theo phiên bản.

Dùng delegate sẵn có giảm nguy cơ làm sai giao thức khi mục đích chỉ là thêm body JSON.

## 10. Domain authorization: 403 không phải luôn thiếu OAuth scope

### 10.1. Scope-based denial

Một method:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(long id) {
    return repository.findOrderDto(id);
}
~~~

Nếu principal hợp lệ thiếu scope, trả 403 là thích hợp. `insufficient_scope` mô tả được nguyên nhân theo RFC 6750.

### 10.2. Owner/tenant denial

Một service có thể kiểm tra:

~~~java
if (!order.getTenantId().equals(caller.tenantId())) {
    throw new AccessDeniedException("Tenant access denied");
}
~~~

Lỗi này không nhất thiết giải quyết bằng việc xin OAuth scope mới. Nếu tất cả `AccessDeniedException` dùng chung một Bearer `insufficient_scope` handler, client có thể hiểu nhầm.

Có thể lựa chọn:

- Tạo **policy-specific exception/result** để map sang `resource_access_denied`.
- Dùng service/controller authorization manager được tổ chức rõ.
- Trả 403 hoặc 404 theo hợp đồng dữ liệu và không tự khai required scope sai.
- Giữ Bearer default handler cho các URL/method scopes, còn object policy dùng một đường xử lý được tài liệu hóa riêng.

Không parse exception message như `"Access denied"` để đoán nguồn lỗi. Mã lỗi ứng dụng nên đến từ **loại policy/exception có cấu trúc**.

### 10.3. `@PreAuthorize` và Spring MVC exception handling

`AccessDeniedException` từ method security có thể đi qua các thành phần khác nhau tùy proxy/MVC/ExceptionTranslationFilter. Nếu `@RestControllerAdvice(Exception.class)` bắt hết rồi trả `500` hoặc `200`, nó có thể che security denial.

Hãy thiết kế exception handling sao cho security exception không bị nuốt hoặc ánh xạ sai. Đồng thời nhớ rằng `@PreAuthorize` trong proxy mode chỉ được thực thi khi lời gọi qua AOP proxy; self-invocation không nên là đường đi duy nhất bảo vệ hành động nhạy cảm.

## 11. `@RestControllerAdvice` vẫn cần cho lỗi MVC

Lỗi validation request body không thuộc Bearer authentication:

~~~java
@PostMapping("/api/orders")
public OrderDto create(
        @Valid @RequestBody CreateOrderRequest request) {
    return service.create(request);
}
~~~

Có thể xử lý bằng `ProblemDetail` của Spring Framework:

~~~java
package com.example.orders.api;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail invalidBody(
            MethodArgumentNotValidException exception) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

        problem.setType(
            URI.create("https://api.example.test/problems/invalid-body")
        );
        problem.setTitle("Bad Request");
        problem.setDetail("The request body is invalid.");
        problem.setProperty("code", "invalid_body");

        return problem;
    }
}
~~~

Dù Bearer `invalid_request` và JSON body `invalid_body` đều có thể dùng HTTP 400, chúng **khác tầng lỗi**:

- Bearer request malformed: RFC 6750 header `invalid_request`.
- MVC request body sai schema: Problem Details `invalid_body`, không thêm Bearer error.

`ProblemDetail` hỗ trợ mô hình RFC 9457 trong Spring MVC, nhưng **không tự giải quyết security filter failures**. Cần cùng một response contract với các extension points phù hợp.

## 12. Đừng biến lỗi nghiệp vụ/hạ tầng thành Bearer error

Một API cần giữ semantics:

### 12.1. Validation lỗi

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-body",
  "title": "Bad Request",
  "status": 400,
  "code": "invalid_body"
}
~~~

Không thêm `WWW-Authenticate: Bearer error="invalid_token"` khi token vẫn đúng.

### 12.2. Method không hỗ trợ

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, PUT
Content-Type: application/problem+json
~~~

`Allow` là header phù hợp cho 405. Không đổi status thành 401 chỉ vì endpoint nằm dưới `/api/**`.

### 12.3. Rate limiting

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json
~~~

Đây không phải `invalid_token`. Client nên backoff theo policy, không refresh token liên tục.

### 12.4. JWKS hoặc opaque introspection outage

Nếu Resource Server không xác minh được token vì JWKS endpoint/introspection không sẵn sàng, **không fail open**. Nhưng cũng không tự giả token sai. Tùy cách exception mapping, API có thể trả lỗi hạ tầng phù hợp; metrics phải phân biệt:

~~~text
invalid_token
jwks_unavailable
introspection_timeout
introspection_client_auth_failed
authorization_denied
business_validation_failed
~~~

Các giá trị trên là ví dụ mã giám sát nội bộ, **không phải tất cả Bearer error codes RFC 6750**.

## 13. CORS: frontend có đọc được Bearer challenge không?

Nếu frontend tại `https://app.example.test` gọi API tại `https://api.example.test`, request chứa header `Authorization` có thể kích hoạt **CORS preflight**.

Dù response có:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

browser JavaScript có thể không đọc được header đó nếu API không expose:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

Cần cấu hình CORS trước khi security chặn preflight hợp lệ.

### 13.1. Ví dụ CORS configuration

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type")
        );
        cors.setExposedHeaders(
            List.of("WWW-Authenticate", "X-Request-Id")
        );

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Trong API `SecurityFilterChain`, bật:

~~~java
http.cors(Customizer.withDefaults());
~~~

Nếu dùng cookie/credentials, phải đánh giá cấu hình `allowCredentials` và allowed origins. Không dùng wildcard origins vô điều kiện cùng credentials. CORS là bảo vệ browser; nó **không thay thế OAuth access token validation**.

### 13.2. `permitAll` không có nghĩa Bearer filter bị tắt

Một endpoint public `/api/public/info` có thể cho phép request **không gửi token**. Nhưng nếu client gửi **token không hợp lệ**, Bearer filter vẫn có thể cố xác thực và trả 401 trước khi controller chạy.

Không “sửa” bằng cách bỏ authentication validation cho mọi endpoint public nếu security architecture cần xử lý credentials nhất quán.

## 14. Cache-Control, Vary và correlation ID

### 14.1. Tránh cache response lỗi mang thông tin nhạy cảm

Có thể đặt:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

cho các lỗi authentication/authorization. `Pragma` chủ yếu vì tương thích lịch sử; `Cache-Control` là cơ chế quan trọng hơn.

Không nhầm cache error body với:

- JWKS cache public keys.
- Cache kết quả introspection.
- Cache data response theo principal.
- Browser OAuth token storage.

### 14.2. CORS và Vary

Khi CORS thay đổi response theo `Origin`, framework có thể thêm `Vary: Origin` và những field liên quan. Không bỏ `Vary` khi custom security response để tránh proxy/cache dùng lẫn response của origins khác nhau.

### 14.3. Correlation ID thay cho raw token

Response:

~~~json
{
  "status": 401,
  "code": "invalid_token",
  "traceId": "req-a19e"
}
~~~

là hữu ích nếu logs/trace nội bộ có cùng ID. Nhưng `traceId` phải là identifier được kiểm soát; không tự tin một request header dài/độc hại mà client gửi làm mã bảo mật.

Không trả raw Bearer token, private JWKS keys, refresh token, stack trace hoặc chi tiết cấu hình validator trong body.

## 15. Gateway và proxy có thể phá hợp đồng HTTP

Một Spring Boot service trả 401 chuẩn nhưng proxy phía trước có thể:

- Đổi 401 thành 302 redirect login.
- Thay 403 bằng HTML error page.
- Bỏ `WWW-Authenticate`.
- Thay `Content-Type` thành `text/html`.
- Không gắn CORS headers cho lỗi.
- Biến backend 503 thành 200 chứa JSON tùy biến.
- Cache sai response theo authorization header.

Vì vậy phải test qua **public entrypoint thực tế**, không chỉ trực tiếp localhost.

Ví dụ:

~~~bash
curl -i https://api.example.test/api/orders
~~~

~~~bash
curl -i \
  -H "Authorization: Bearer <INVALID_TEST_TOKEN>" \
  https://api.example.test/api/orders
~~~

Quan sát status, headers, content type và body cùng lúc. Dùng token test, không dán token production vào log hoặc bug report.

## 16. Client nên xử lý status trước JSON

Ví dụ JavaScript frontend:

~~~js
async function loadOrders(token) {
  const response = await fetch(
    "https://api.example.test/api/orders",
    {
      headers: { Authorization: "Bearer " + token }
    }
  );

  const challenge =
    response.headers.get("WWW-Authenticate");

  const contentType =
    response.headers.get("Content-Type") || "";

  const problem = contentType.includes("application/problem+json")
    ? await response.json()
    : null;

  if (response.status === 401) {
    // Token hết hạn/sai hoặc caller chưa authenticated.
    // Có thể refresh theo chính sách OAuth client, không retry vô hạn.
    throw new Error(problem?.code || "authentication_required");
  }

  if (response.status === 403) {
    // Cần quyền hợp lệ; không tự refresh mãi cùng một scope.
    throw new Error(problem?.code || "forbidden");
  }

  if (!response.ok) {
    throw new Error(problem?.detail || "API request failed");
  }

  return response.json();
}
~~~

Biến `challenge` được đọc để minh họa; khi cần phân tích Bearer parameters, sử dụng parser HTTP challenge tương thích RFC thay vì cắt chuỗi tùy tiện.

Khi muốn JavaScript đọc `WWW-Authenticate` ở cross-origin, API phải cấu hình CORS expose header như phần trước. Frontend cũng cần xử lý các response không có JSON hoặc status 204 theo hợp đồng thực tế.

## 17. Kiểm thử phải kiểm tra cả status, header và body

### 17.1. Ba phạm vi test

- **Unit test handler:** kiểm tra delegate giữ nguyên header/status và writer tạo JSON phù hợp.
- **MockMvc/Spring Security integration test:** kiểm tra request đi qua đúng filter chain, entry point và access-denied handler.
- **End-to-end test qua proxy/gateway:** kiểm tra status/challenge/body/CORS không bị lớp trung gian sửa.

Spring Security Test `jwt()` tạo mock JWT authentication tiện cho authorization test, **không tự chứng minh JwtDecoder đã xác minh chữ ký/issuer/audience/JWKS**.

### 17.2. Missing Bearer token

Ví dụ test với `MockMvc mvc` đã được cấu hình và URL protected:

~~~java
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@Test
void missingTokenReturnsBearerChallengeAndJson() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "WWW-Authenticate",
            startsWith("Bearer")
        ))
        .andExpect(content().contentTypeCompatibleWith(
            "application/problem+json"
        ))
        .andExpect(jsonPath("$.status").value(401))
        .andExpect(jsonPath("$.code")
            .value("authentication_required"));
}
~~~

Với missing token, cần xác nhận Bearer challenge **không** chứa `error="invalid_token"` nếu request thật sự không có authentication information.

### 17.3. JWT principal hợp lệ nhưng thiếu scope

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void authenticatedWithoutReadScopeGetsForbidden() throws Exception {
    mvc.perform(
        get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            ))
    )
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.status").value(403))
        .andExpect(jsonPath("$.code").value("forbidden"));
}
~~~

Test trên kiểm tra **authorization rule và body của handler**, không phải JWT signature. Nếu Bearer default handler tạo `insufficient_scope` ở header, kiểm tra thêm theo implementation/version.

### 17.4. Test invalid JWT bằng decoder thật hoặc stub

Để test đúng `invalid_token`, có thể:

- Gửi JWT test thực được ký bằng key test, cố ý sai `exp`/`aud`/signature và cấu hình decoder/JWKS test.
- Dùng stub `JwtDecoder` ném exception authentication tương ứng trong Spring test context, xác nhận Bearer filter xử lý và entry point được gọi.

Kỳ vọng:

~~~text
HTTP status = 401
WWW-Authenticate: Bearer ... error="invalid_token"
Content-Type: application/problem+json
JSON status = 401
JSON code = invalid_token
~~~

Không dùng `jwt()` mock rồi kết luận đã test JWT validator; helper này thường bỏ qua luồng xác minh token thật.

### 17.5. Test Bearer request malformed

Với resolver hỗ trợ phát hiện trường hợp truyền token lặp/sai định dạng, test:

~~~text
HTTP status = 400
WWW-Authenticate includes error="invalid_request"
JSON status = 400
JSON code = invalid_request
~~~

Default `BearerTokenResolver` có những giới hạn cho query/form parameters. Không mặc định nó sẽ đọc mọi `access_token` trong URL nếu chưa bật cách truyền đó.

### 17.6. Ma trận test hợp đồng phản hồi

| Test | HTTP | Header | Body |
|---|---|---|---|
| Không token, endpoint protected | 401 | Bearer challenge, không error theo missing credentials | `status=401` |
| JWT sai chữ ký/hết hạn | 401 | `invalid_token` | `status=401`, code đúng |
| Bearer header sai cấu trúc | 400 | `invalid_request` | `status=400` |
| Principal hợp lệ thiếu `orders.read` | 403 | `insufficient_scope` khi là scope denial | `status=403` |
| Tenant/owner policy deny | 403/404 | Không tự giả lỗi scope | Body đúng status |
| Request body validation sai | 400 | Không có Bearer error giả | `invalid_body` |
| Sai HTTP method | 405 | `Allow` hợp lệ | `status=405` |
| Rate limit | 429 | `Retry-After` nếu phù hợp | `status=429` |
| JWKS/introspection outage | Lỗi hạ tầng theo config | Không fail open | Không lộ secrets |
| `permitAll` không token | Theo endpoint | Không cần challenge | Data response |
| `permitAll` có Bearer invalid | Có thể 401 | Bearer challenge | Authentication error |
| CORS OPTIONS preflight | Theo CORS config | Không ép Bearer token | CORS headers hợp lệ |
| Browser đọc challenge | Giữ status gốc | Expose `WWW-Authenticate` | Body parse được |
| API gateway | Giữ status gốc | Không drop challenge | Đúng media type/status |

### 17.7. Assert actual HTTP status và JSON status bằng nhau

Không chỉ kiểm tra một trong hai. Một test có thể thành công khi body `status` là 401 dù actual HTTP status là 200. Đây là lỗi nghiêm trọng về ngữ nghĩa HTTP.

Nếu reverse proxy thay body hoặc status, test end-to-end phải phát hiện, không chỉ dựa trên MockMvc chạy trực tiếp application.

## 18. Những lỗi phổ biến và cách tránh

### “401 có JSON body là đủ, không cần `WWW-Authenticate`”

Sai. Bearer clients cần HTTP authentication challenge theo RFC 6750. Dùng handler chuẩn hoặc bảo toàn challenge khi thêm JSON.

### “Không gửi token tương đương `invalid_token`”

Không hoàn toàn. RFC 6750 khuyến nghị với request thiếu thông tin authentication thì **không** thêm error code vào challenge.

### “Token không đủ scope thì trả 401”

Thường sai. Token hợp lệ nhưng thiếu privilege là `403`, có thể `insufficient_scope` theo RFC 6750.

### “Mọi 403 đều phải có `insufficient_scope`”

Sai nếu lý do là ACL/tenant/owner hoặc business policy; cần phân loại nguồn từ chối.

### “Mọi 400 đều là OAuth `invalid_request`”

Sai. JSON request body sai schema có thể là 400 nhưng không liên quan Bearer.

### “Trả 200 với JSON error cho dễ xử lý frontend”

Sai. Làm hỏng semantics ở HTTP client, caches, gateways và monitoring.

### “Chỉ cần `@RestControllerAdvice` cho cả lỗi Bearer”

Sai. Bearer filter có thể trả lỗi trước MVC. Dùng `AuthenticationEntryPoint` và `AccessDeniedHandler`.

### “Ghi exception message vào `error_description` là an toàn”

Không. Có rủi ro lộ thông tin nội bộ, ký tự không phù hợp với header và dữ liệu chưa kiểm soát.

### “Gọi `sendError` rồi viết JSON body vẫn ổn”

Không nên dựa vào đó. Container/error handling có thể thay hoặc commit response. Đặt status/header/body trong một đường xử lý rõ.

### “CORS chỉ cần allow origin”

Frontend còn cần preflight đúng và `Access-Control-Expose-Headers` để đọc `WWW-Authenticate` trong JavaScript.

### “API gateway không thể sửa auth response”

Gateway có thể strip header, đổi status hoặc trả trang HTML. Phải test qua đường client thật sử dụng.

### “AS introspection trả 401 nghĩa Bearer token caller invalid”

Không nhất thiết. Có thể introspection client credential của Resource Server bị sai.

## 19. Nguyên tắc triển khai

1. **Đúng HTTP status trước:** 400 malformed Bearer request, 401 authentication failure, 403 insufficient privilege, các lỗi khác giữ semantics riêng.
2. **Giữ `WWW-Authenticate` đúng RFC 6750:** missing credentials thường không có Bearer `error`; token invalid có `invalid_token`; thiếu scope có `insufficient_scope` khi phù hợp.
3. **JSON bổ sung chứ không thay header:** dùng Problem Details RFC 9457 hoặc schema ứng dụng thống nhất; body `status` khớp actual HTTP status.
4. **Dùng đúng Spring extension point:** `AuthenticationEntryPoint` cho authentication, `AccessDeniedHandler` cho denied security, `@RestControllerAdvice` cho MVC/business errors.
5. **Ưu tiên Bearer handlers có sẵn:** giữ status/header chuẩn rồi chỉ viết JSON an toàn, tránh tự nối challenge thủ công.
6. **Không tiết lộ token/secrets/internal errors:** mô tả công khai gọn; correlation ID và logs riêng cho vận hành.
7. **Tách HTTP API và browser login flows:** không dùng một Bearer JSON handler cho mọi URL nếu có OIDC login/session.
8. **Test toàn bộ response contract:** status + header + body + CORS + gateway, bao gồm negative cases.

## 20. Tóm lược

Một lỗi từ OAuth 2.0 Resource Server phải có **ngữ nghĩa nhất quán xuyên ba lớp**:

~~~text
HTTP status
  + WWW-Authenticate Bearer challenge / error
  + JSON body theo hợp đồng API
~~~

Bốn tình huống cần nhớ:

- **Không token:** `401`, Bearer challenge thường không có `error`.
- **Token không hợp lệ:** `401`, `invalid_token` khi được phân loại đúng.
- **Bearer request sai:** `400`, `invalid_request` khi áp dụng RFC 6750.
- **Token hợp lệ thiếu scope:** `403`, `insufficient_scope` khi là scope denial.

Trong Spring Security Servlet, **`BearerTokenAuthenticationEntryPoint`** và **`BearerTokenAccessDeniedHandler`** đã xử lý phần lớn status/challenge. Khi cần JSON, hãy bọc hoặc tùy chỉnh handlers này mà **không làm mất RFC 6750 header**, dùng RFC 9457 Problem Details nếu phù hợp, và giữ body status trùng HTTP status.

### Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [Spring Security Reference — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [Spring Security API — OAuth2ResourceServerConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html)
- [Spring Framework Reference — Error Responses and Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)

