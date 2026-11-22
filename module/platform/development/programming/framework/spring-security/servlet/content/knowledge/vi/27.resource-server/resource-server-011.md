# Phản hồi lỗi Bearer, WWW-Authenticate và giới hạn tiết lộ thông tin trong Spring Security Servlet Resource Server

## 1. Tình huống: API nhận Bearer access token

Khi Spring Security Servlet đóng vai trò **OAuth 2.0 Resource Server**, ứng dụng nhận request từ client mang access token, thông thường qua header:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<chuoi-token-minh-hoa>
~~~

Resource Server cần xác thực token, kiểm tra token có được chấp nhận cho API này hay không và xác định caller có đủ quyền. Các trường hợp lỗi không giống nhau:

- Client **chưa cung cấp** thông tin xác thực cho endpoint bắt buộc đăng nhập.
- Client gửi token **hết hạn, bị thu hồi, sai chữ ký hoặc không hợp lệ**.
- Client gửi request Bearer **sai cú pháp** hoặc cố chuyển token qua nhiều phương thức xung đột.
- Token **đã xác thực hợp lệ** nhưng thiếu scope/quyền cho hành động cụ thể.
- Tầng gateway, application hoặc downstream gặp **lỗi hệ thống** không liên quan token.

Phản hồi nên vừa giúp client xử lý đúng, vừa tránh biến API thành nguồn rò rỉ thông tin về token, tài khoản, policy và cấu trúc hạ tầng.

**Hai tín hiệu quan trọng nhất** là HTTP status (400/401/403) và header phản hồi `WWW-Authenticate`. Chuẩn OAuth 2.0 Bearer Token Usage (RFC 6750) quy định các tham số lỗi Bearer. HTTP authentication semantics còn quy định vai trò của `401 Unauthorized` và lời thách thức xác thực (challenge) ở `WWW-Authenticate`.

> `401 Unauthorized` theo tên gọi lịch sử thực chất thường có nghĩa “chưa được xác thực phù hợp”, không phải “đã xác thực nhưng thiếu quyền”; trường hợp sau thông thường là `403 Forbidden`.

## 2. WWW-Authenticate là header gì?

`WWW-Authenticate` là **response header** do server gửi nhằm chỉ ra cơ chế xác thực áp dụng cho tài nguyên. Khi một endpoint chỉ chấp nhận OAuth 2.0 Bearer, challenge có dạng:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Cache-Control: no-store
~~~

Các thành phần:

- **`Bearer`**: tên authentication scheme. Đây là *challenge*, khác với `Authorization: Bearer <token>` mà client gửi trong request.
- **`realm="api"`**: tên phạm vi bảo vệ do server chọn. Realm dùng để gợi ý phạm vi credentials; **không phải** issuer, tenant ID, OAuth scope hay URL token endpoint. Có thể đặt giá trị cố định, không chứa bí mật.
- **`error="..."`**: mã lỗi Bearer đã được chuẩn hóa, chẳng hạn `invalid_request`, `invalid_token` hoặc `insufficient_scope`.
- **`error_description="..."`**: câu mô tả lỗi dễ đọc; *tùy chọn* và thường nên bỏ hoặc rút gọn để tránh lộ chi tiết.
- **`error_uri="..."`**: URL tài liệu công khai mô tả lỗi; *tùy chọn*, chỉ dùng URL cố định đáng tin.
- **`scope="reports.read"`**: gợi ý scope cần thiết trong ngữ cảnh `insufficient_scope`; *tùy chọn*. Giá trị có thể chứa nhiều scope phân tách bằng dấu cách, nhưng công bố scope đôi khi tiết lộ thông tin policy.

Ví dụ challenge có mã lỗi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api", error="invalid_token"
Cache-Control: no-store
~~~

Hoặc với scope không đủ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="api", error="insufficient_scope"
Cache-Control: no-store
~~~

Tên header trong HTTP **không phân biệt chữ hoa/chữ thường**; các tham số ví dụ được ghi theo cách quen thuộc của Bearer. Server cần xuất header hợp lệ, không nối trực tiếp chuỗi do người dùng kiểm soát vào `realm`, `error_description` hoặc `error_uri`.

**Không phải mọi `403` đều phải có `error="insufficient_scope"`.** Một người dùng bị từ chối bởi chính sách nghiệp vụ, trạng thái tài khoản hoặc ACL không nhất thiết thiếu OAuth scope. Nếu ứng dụng biết chắc caller có token OAuth hợp lệ nhưng thiếu quyền phù hợp, mã này mới mang ý nghĩa chính xác.

## 3. Phân loại lỗi theo RFC 6750 và HTTP

| Tình huống | HTTP status thường phù hợp | Bearer challenge | Điều client nên làm |
| --- | --- | --- | --- |
| Thiếu Bearer token ở endpoint được bảo vệ | `401` | `Bearer realm="api"` (thường **không kèm `error`**) | Thực hiện xác thực/ủy quyền để lấy token |
| Token hết hạn, không xác thực được, bị từ chối | `401` | `error="invalid_token"` | Lấy token mới/đăng nhập lại nếu được phép; không retry vô hạn |
| Request dùng Bearer sai cú pháp hoặc nhiều cách cung cấp token xung đột | `400` | `error="invalid_request"` nếu lỗi do xử lý Bearer | Sửa cú pháp request; không coi đây là lỗi scope |
| Token OAuth hợp lệ nhưng thiếu scope cho tài nguyên | `403` | `error="insufficient_scope"`; có thể có `scope` | Xin quyền phù hợp hoặc ngừng yêu cầu |
| Caller hợp lệ nhưng bị business authorization/ACL từ chối | `403` | Không nhất thiết phải công bố mã lỗi/scope Bearer | Xử lý quyền tài nguyên, không đoán thiếu scope |
| Tài nguyên không tồn tại | `404` (sau xác thực/phân quyền nếu cần) | Thường không phải lỗi Bearer | Kiểm tra resource/path theo quyền |
| Authorization server/JWK endpoint gặp sự cố hoặc API lỗi nội bộ | `5xx` tùy tình huống | Không nên giả làm `invalid_token` khi chưa xác minh token | Retry có giới hạn, quan sát sự cố |

### 3.1. Không có token — challenge tối giản

Một request tới `/api/reports` thiếu `Authorization` thường nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
~~~

RFC 6750 khuyến nghị **không kèm `error` hoặc mô tả lỗi** nếu request đơn giản là không có thông tin xác thực. Client chỉ cần biết cơ chế Bearer được yêu cầu. Không cần trả “user unknown”, “token missing for admin” hay danh sách policy nội bộ.

Nếu route được `permitAll()`, request không token có thể trả 200; không phải API nào cũng bắt buộc challenge. Khi request gửi một token **không hợp lệ** tới route public, filter Resource Server có thể vẫn thử xác thực token rồi trả lỗi: `permitAll()` điều chỉnh **authorization**, không nhất thiết bỏ qua **authentication filter**.

### 3.2. Token không hợp lệ — invalid_token

Các lý do có thể gồm token bị sửa, hết hạn, issuer không hợp lệ, không thể xác minh chữ ký, token bị thu hồi hoặc không dành cho resource này. Với token không được chấp nhận, response thường là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api", error="invalid_token"
~~~

Không nhất thiết phân biệt nguyên nhân công khai. Các chuỗi sau dễ gây rò rỉ nếu trả nguyên văn: `signature verification failed for key id=...`, `unknown tenant xxx`, `token for user alice@example.test revoked at 12:03` hoặc stack trace từ decoder.

**Không tự động coi mọi lỗi `JwtDecoder` là token sai.** Sự cố JWK discovery/cache/authorization server hoặc timeout mạng có thể là lỗi hạ tầng. Tầng quan sát nội bộ cần phân biệt lỗi vận hành và lỗi xác thực; không biến mọi exception thành “invalid token” rồi buộc người dùng đăng nhập lại.

### 3.3. Bearer request không hợp lệ — invalid_request

RFC 6750 sử dụng `invalid_request` cho lỗi cấu trúc yêu cầu chứa access token, ví dụ request thiếu tham số cần thiết của một cách gửi token, tên tham số lặp, hoặc gửi token qua nhiều phương thức trong cùng request. Status được khuyến nghị là **`400 Bad Request`**.

Không phải mọi header Authorization sai đều luôn rơi vào chính xác cùng exception hoặc status ở mọi phiên bản server/proxy. Servlet container có thể từ chối trước; `BearerTokenResolver` có thể phát hiện hoặc không phát hiện một số dạng sai cú pháp. Khi làm kiểm thử, phải quan sát **lỗi thật phát sinh tại tầng nào**, thay vì hứa rằng mọi chuỗi bất thường đều trả `400 invalid_request`.

Không khuyến khích gửi bearer token trong query string vì có thể rò qua logs, history, referer và analytics. Spring Security `DefaultBearerTokenResolver` thường ưu tiên header `Authorization` và không chấp nhận URI query parameter nếu không bật tường minh; đừng nới các tùy chọn này chỉ để hợp thức hóa client cấu hình sai.

### 3.4. Token hợp lệ nhưng thiếu quyền — insufficient_scope

Nếu JWT hợp lệ có scope `profile.read` nhưng endpoint `/api/reports` yêu cầu `reports.read`, response có thể là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="api", error="insufficient_scope"
~~~

Một triển khai cũng có thể gợi ý `scope="reports.read"` nếu đó là thông tin công khai có ích. Tuy nhiên các scope như `billing.admin` hoặc tên vai trò nội bộ có thể tiết lộ cấu trúc phân quyền; cân nhắc không công bố chúng. **Đừng trả nguyên bản `Authentication.getAuthorities()` hoặc toàn bộ danh sách scope người dùng có/thiếu.**

`403` thường không được sửa bằng việc refresh lại **cùng scope**; client cần quyền hoặc consent bổ sung qua quy trình hợp lệ, hoặc phải dừng thao tác. Client không tự ý leo quyền chỉ vì server gợi ý tên scope.

## 4. Phân biệt OAuth Bearer error với lỗi khác

### 4.1. Access token khác refresh token và ID token

Resource Server thông thường xác thực **access token** nhận qua `Authorization: Bearer ...`. Endpoint `/token` của Authorization Server xử lý các yêu cầu lấy/refresh token và có **mô hình lỗi OAuth riêng** (ví dụ `invalid_grant`, `invalid_client`). Đừng nhầm response lỗi của token endpoint với challenge của Resource Server.

Với OIDC, **ID token** phục vụ xác thực người dùng tới client. Nó không tự là access token được phép gọi mọi Resource Server. Đưa ID token vào Bearer header có thể gây `invalid_token` nếu issuer/audience/chính sách không phù hợp.

### 4.2. 401 khác 403, 400, 404 và 5xx

Một request lỗi authentication, error parsing, missing scope, URL không tồn tại và lỗi database có thể dẫn đến status khác nhau. Chỉ gắn Bearer challenge khi nó đúng với cơ chế từ chối request, không biến mọi HTTP error thành `401 invalid_token`.

Trong ứng dụng có nhiều `SecurityFilterChain` hoặc hỗ trợ **Basic + Bearer + session**, endpoint cụ thể phải công bố challenge tương ứng chính sách thực tế. Header `WWW-Authenticate: Basic ...` không thể thay thế một challenge Bearer đối với API Bearer-only. Khi server hỗ trợ nhiều scheme, challenge có thể xuất hiện nhiều lần; client cần xử lý theo cú pháp HTTP, không tự coi toàn bộ chuỗi header là một cặp key/value.

### 4.3. Không dùng error message để xác nhận sự tồn tại của account

Nếu lỗi nêu rõ “user tồn tại nhưng token hết hạn”, “client ID không tồn tại”, “tenant có quyền reports.admin” hay “resource ID hợp lệ nhưng bị khóa”, kẻ tấn công có thể thực hiện **enumeration**. Thiết kế phản hồi đủ để client đưa ra bước tiếp theo nhưng không làm lộ danh tính, policy hoặc dữ liệu truy cập trái phép.

Với tài nguyên nhạy cảm, đôi khi một `404` được sử dụng thay vì `403` để không xác nhận tài nguyên tồn tại; quyết định này thuộc **chính sách authorization**, không phải thủ thuật chỉ thay số status trong mọi trường hợp. Hãy giữ hành vi nhất quán để tránh side channel.

## 5. Spring Security Servlet xử lý lỗi Bearer ở lớp nào?

Với `spring-boot-starter-oauth2-resource-server` và security chain bật JWT Resource Server, các thành phần tiêu biểu là:

1. **`BearerTokenAuthenticationFilter`** tìm Bearer token bằng `BearerTokenResolver` rồi yêu cầu authentication nếu có token.
2. **`AuthenticationManager` / `JwtAuthenticationProvider` và `JwtDecoder`** (JWT case) kiểm tra và chuyển token thành `Authentication`; nếu dùng opaque token, tích hợp **introspection** thay cho JWT decoder.
3. **`BearerTokenAuthenticationEntryPoint`** tạo response khi cần bắt đầu Bearer authentication hoặc xảy ra một số lỗi authentication; thường đặt HTTP 401, hoặc status tương ứng của `BearerTokenError` khi có, và xây `WWW-Authenticate`.
4. **`BearerTokenAccessDeniedHandler`** xử lý access denied; nếu chứng minh được authentication là OAuth2 token hợp lệ, handler có thể trả `403` kèm `insufficient_scope`.
5. **`ExceptionTranslationFilter`** liên kết authentication failures/access denied từ các filter phía sau với `AuthenticationEntryPoint` và `AccessDeniedHandler`; luồng lỗi phát sinh trực tiếp trong bearer authentication filter có điểm xử lý riêng.

Không phải mọi exception ở controller đều đi qua các handler Bearer. Một `IllegalArgumentException` nghiệp vụ không tự chuyển thành `invalid_request` OAuth; lỗi đó cần error handling application riêng. Nếu custom `@ControllerAdvice` hoặc reverse proxy thay response, kiểm tra rằng các header bảo mật cần thiết không bị mất.

### Từ request đến quyết định

~~~text
Client
  │
  ├─ Không có token ───────────────┐
  ├─ Token sai / expired ──────────┤
  └─ Token hợp lệ ─────────────────┤
                                  ▼
                  Spring Security Servlet FilterChain
                                  │
                                  ├─ BearerTokenResolver
                                  ├─ JWT validation / introspection
                                  ├─ AuthenticationEntryPoint
                                  └─ Authorization / AccessDeniedHandler
                                  │
                   ┌──────────────┼───────────────────┐
                   ▼              ▼                   ▼
             Thiếu/sai token   Thiếu quyền       Token + quyền hợp lệ
                   │              │                   │
            401 Bearer        403 insufficient_scope  Controller
            hoặc 400 error    (khi phù hợp)           trả nghiệp vụ
~~~

Sơ đồ là mô hình hóa. Với request không token, các filter có thể cho đi tiếp đến authorization rồi mới cần entry point; với token sai, authentication filter có thể xử lý lỗi ngay.

## 6. Cấu hình Resource Server JWT tối thiểu

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x**, thư viện Servlet MVC. Các URI là **minh họa**, không phải identity provider thật.

Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`application.yml` khi sử dụng issuer có discovery metadata tương thích:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

Ứng dụng thực tế cần metadata/JWKS khả dụng và kiểm tra **issuer, chữ ký, hạn sử dụng, audience phù hợp**, cùng các yêu cầu tenant/claims nếu có. Việc cấu hình `issuer-uri` hỗ trợ xác thực issuer qua Spring Security; không được tự suy ra mọi audience và policy của API đã được xác thực nếu chưa cấu hình.

File `SecurityConfig.java` minh họa một security chain:

~~~java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đoạn trên là **Spring configuration class**, chạy trong ứng dụng Boot với dependency và IdP thật; không phải file độc lập có thể chạy chỉ với lệnh `javac SecurityConfig.java` của JDK thuần. Mặc định, khi resource server hỗ trợ Bearer, Spring Security dùng các handler Bearer phù hợp cho authentication và access denied. Phản hồi cụ thể phụ thuộc version/config, filter chain, cách JWT lỗi và container.

`hasAuthority("SCOPE_reports.read")` dùng convention mapping OAuth2 scope thành `SCOPE_...` của JWT resource server thông thường. Nếu hệ thống dùng custom `JwtAuthenticationConverter`, cách ánh xạ authority có thể khác; cần test theo mapping thực tế.

Một controller tối giản trong file `ApiController.java` cùng package:

~~~java
package com.example.api;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicStatus() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/reports")
    public Map<String, String> report() {
        return Map.of("status", "available");
    }
}
~~~

Lưu ý: các ví dụ security chỉ kiểm tra scope cho `/api/reports`; production còn cần phân quyền theo tổ chức, người dùng và tài nguyên. Một JWT có scope phù hợp **không chứng minh** client có quyền xem mọi báo cáo thuộc mọi tenant.

## 7. Kiểm soát thông tin tiết lộ trong lỗi

### 7.1. Chính xác nhưng tối thiểu

| Thông tin | Có thể trả công khai? | Lý do |
| --- | --- | --- |
| HTTP 401/403/400 | Có, khi đúng ngữ nghĩa | Client cần quyết định login, xin quyền hay sửa request |
| `Bearer` challenge | Có, khi endpoint dùng Bearer | Cho client biết loại credentials cần dùng |
| `error="invalid_token"` | Có thể | Chuẩn hóa lỗi; không nói cụ thể token hỏng ở đâu |
| `error="insufficient_scope"` | Có thể nếu đúng điều kiện | Cho client biết cần quyền phù hợp |
| `scope="..."` | Cân nhắc | Có thể công bố tên capability/policy của API |
| `error_description` chi tiết từ JWT decoder | **Tránh** | Có thể lộ issuer, key ID, claim, signature, thời gian, stack |
| Access token/refresh token/ID token, Authorization header | **Tuyệt đối không** | Là credentials hoặc chứa dữ liệu nhạy cảm |
| Toàn bộ claims, authorities, subject, email, tenant, ACL | Không mặc định | Lộ danh tính, policy và bề mặt enumeration |
| Correlation ID ngẫu nhiên không chứa PII | Thường có | Giúp hỗ trợ truy vết mà không lộ nguyên nhân nhạy cảm |
| Link tới trang hướng dẫn public cố định | Có thể | Hỗ trợ client mà không tiết lộ hạ tầng nội bộ |

**Giới hạn lộ thông tin không có nghĩa nói dối về HTTP status.** Trả cùng một `401` cho mọi lỗi làm client refresh token khi thực ra thiếu scope, hoặc che một `5xx` của IdP thành credential lỗi. Nên giữ **loại lỗi cần thiết** và loại bỏ **nguyên nhân kỹ thuật nhạy cảm**.

### 7.2. Không phản chiếu nội dung attacker-controlled

Không ghép trực tiếp `request.getHeader("Authorization")`, chuỗi token lỗi, `exception.getMessage()` hoặc claim value vào:

- `WWW-Authenticate: ... error_description="..."`,
- JSON error body,
- thông báo lỗi HTML,
- URL của `error_uri`,
- redirect location,
- log HTTP access hoặc tracing tags.

Header values có quy tắc cú pháp riêng; phản chiếu ký tự điều khiển, dấu ngoặc kép hoặc chuỗi attacker-controlled còn có thể gây header injection nếu server không chặn. Sử dụng **hằng số đã chọn trước**, escape/canonicalize đúng chuẩn khi bắt buộc phải tạo tham số động.

Nếu gateway/tracing tự ghi cả request headers, hãy cấu hình **redact** `Authorization`, `Cookie` và secret. Vấn đề rò rỉ thường xảy ra ở infrastructure logs/APM chứ không chỉ ở HTTP body do controller tạo ra.

### 7.3. Thông tin nội bộ được phép chi tiết hơn, nhưng phải an toàn

Cần phân loại lỗi để vận hành, ví dụ:

- `bearer_auth.missing`,
- `bearer_auth.invalid_token`,
- `bearer_auth.invalid_request`,
- `bearer_auth.insufficient_scope`,
- `jwks.fetch.timeout`.

Lưu **error category, request ID ngẫu nhiên, route template, timestamp, status**; dùng metrics/tracing. Đừng log raw token, nguyên vẹn Authorization header, refresh token hoặc decoder exception chứa token/claims. Quyền xem logs phải được giới hạn. Giới hạn rate log/sampling để tránh attacker flood.

Với lỗi có khả năng liên quan tài khoản, tránh các phản hồi có khác biệt không cần thiết về latency/body/header giữa “user tồn tại” và “user không tồn tại” nếu chúng trở thành kênh suy đoán. Không thể loại bỏ mọi side channel chỉ với việc bỏ `error_description`.

## 8. Tùy biến entry point để giảm rò rỉ, không phá giao thức

Phần lớn API nên bắt đầu bằng **mặc định của Spring Security**, sau đó đo thử dữ liệu thực tế. Khi policy yêu cầu loại bỏ hoàn toàn lời mô tả lỗi kỹ thuật từ challenge, có thể tùy biến `AuthenticationEntryPoint` để chỉ xuất **mã lỗi chuẩn**.

Ví dụ tiếp theo là **phiên bản thay thế** của `SecurityConfig.java` ở mục 6 (không tạo thêm một `SecurityFilterChain` thứ hai với cùng matcher). Bài sử dụng response body trống và realm cố định; lỗi application nghiệp vụ phải xử lý riêng.

~~~java
package com.example.api;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.AuthenticationEntryPoint;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.authentication.AbstractOAuth2TokenAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        AuthenticationEntryPoint safeBearerEntryPoint =
            (request, response, failure) -> {
                String errorCode = failure
                    instanceof OAuth2AuthenticationException oauthFailure
                    ? oauthFailure.getError().getErrorCode()
                    : "";

                String challenge = "Bearer realm=\"api\"";

                if ("invalid_request".equals(errorCode)) {
                    response.setStatus(
                        HttpServletResponse.SC_BAD_REQUEST);
                    challenge += ", error=\"invalid_request\"";
                } else {
                    response.setStatus(
                        HttpServletResponse.SC_UNAUTHORIZED);
                    if ("invalid_token".equals(errorCode)) {
                        challenge += ", error=\"invalid_token\"";
                    }
                }

                response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE, challenge);
                response.setHeader(
                    HttpHeaders.CACHE_CONTROL, "no-store");
                // Không gửi exception message, token hoặc stack trace.
            };

        AccessDeniedHandler safeBearerDenied =
            (request, response, denied) -> {
                Authentication current = SecurityContextHolder
                    .getContext().getAuthentication();

                response.setStatus(
                    HttpServletResponse.SC_FORBIDDEN);

                // Chỉ gắn mã lỗi OAuth scope khi authentication
                // thực sự là token OAuth đã được Spring xác thực.
                if (current
                    instanceof AbstractOAuth2TokenAuthenticationToken<?>) {
                    response.setHeader(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Bearer realm=\"api\", error=\"insufficient_scope\"");
                }

                response.setHeader(
                    HttpHeaders.CACHE_CONTROL, "no-store");
            };

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
                .authenticationEntryPoint(safeBearerEntryPoint)
                .accessDeniedHandler(safeBearerDenied));

        return http.build();
    }
}
~~~

**Vì sao thiết kế như vậy?**

- **Request thiếu token** thường không có `OAuth2AuthenticationException` chứa `invalid_token`; entry point trả `401` với `Bearer realm="api"` **không tự bịa mã lỗi**.
- **Token không hợp lệ** có `OAuth2AuthenticationException` với `errorCode = "invalid_token"` sẽ trả `401` và mã lỗi, **không xuất `error_description`** từ decoder.
- **Bearer request sai** phát sinh `invalid_request` ở layer xử lý Bearer sẽ trả `400` và challenge tương ứng. Nhưng một error khác từ proxy/container có thể không đi qua entry point này.
- **Access denied** có OAuth2 token auth sẽ trả `403` với `insufficient_scope` theo policy minh họa cho `/api/reports`; với authentication khác thì không khẳng định scope nào thiếu.
- `response.setStatus(...)` không tự sinh nội dung HTML có stack trace; trong ví dụ response body để trống. `Cache-Control: no-store` giúp tránh cache các phản hồi xác thực nhạy cảm ở tầng tuân thủ chính sách cache; vẫn phải cấu hình proxy và caching cho cả dữ liệu thành công.

**Giới hạn của ví dụ:** cách xác định `AbstractOAuth2TokenAuthenticationToken<?>` chỉ chứng minh có OAuth token authentication trong SecurityContext, **không chứng minh mọi lỗi 403 trong mọi ứng dụng là thiếu OAuth scope**. Nếu có ACL/tenant policy, hãy phân loại theo ngoại lệ và quyền nghiệp vụ trước khi gắn `insufficient_scope`. Trong hệ thống có nhiều chain hoặc custom error handlers, test đúng route và error propagation. Giữ một điểm chịu trách nhiệm định nghĩa header để tránh nhiều handler/proxy ghi đè `WWW-Authenticate`.

### Khi nào nên giữ handler mặc định?

Dùng `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` mặc định nếu ứng dụng không có yêu cầu hạn chế description đặc biệt, và response thực tế đã đạt chính sách. Có thể cấu hình `realm` cố định cho các handler tương ứng bằng API `setRealmName(...)`. Không cần viết lại framework nếu không có nhu cầu; code custom phải được test kỹ khi Spring Security hoặc OAuth2 provider thay đổi.

Nếu áp dụng một **global `@ControllerAdvice`** để trả JSON `ProblemDetail`, lưu ý lỗi Spring Security filter có thể xảy ra trước controller nên không tự được chuyển qua advice. Muốn body lỗi nhất quán, phải phối hợp exception handling **đúng tầng** mà vẫn giữ status và `WWW-Authenticate`. Không viết body JSON trùng với một body HTML/error page từ servlet container.

## 9. Kiểm thử tự động: 401, 403, challenge, và không rò rỉ

### 9.1. Test ma trận cơ bản

| Test request | Kỳ vọng từ cấu hình an toàn mục 8 |
| --- | --- |
| `GET /api/reports` không Authorization | `401`, `WWW-Authenticate: Bearer realm="api"`, không có body |
| Bearer token sai được JwtDecoder từ chối với `invalid_token` | `401`, challenge thêm `error="invalid_token"`, không rò decoder message |
| Bearer request bị resolver từ chối với `invalid_request` | `400`, challenge thêm `error="invalid_request"` nếu đi qua entry point |
| JWT hợp lệ có `SCOPE_profile.read` nhưng không có `SCOPE_reports.read` | `403`, challenge có `error="insufficient_scope"` |
| JWT hợp lệ có `SCOPE_reports.read` | Controller được chạy, có thể trả `200` |
| Request tới `/api/public` không token | `200` |
| Resource server/Gateway gặp lỗi hệ thống | Không ngụy trang toàn bộ thành token sai; status phù hợp, logs an toàn |

### 9.2. MockMvc với Java 17+ và Spring Boot 3.x

Ví dụ file `SecurityErrorTest.java` trong cùng package `com.example.api` của ứng dụng có `SecurityConfig` mục 8 và controller mục 6. Cần `spring-boot-starter-test`, `spring-security-test`. Trong Boot 3.x, `@MockBean` có thể thay decoder thật cho integration test; annotation này bị deprecate ở Boot 3.4 và các dự án mới hơn có thể dùng cơ chế Mockito bean override tương ứng.

~~~java
package com.example.api;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityErrorTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    @Test
    void missingTokenHasPlainBearerChallenge() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\""))
            .andExpect(content().string(""));
    }

    @Test
    void invalidTokenDoesNotLeakDecoderMessage() throws Exception {
        when(decoder.decode("bad-token"))
            .thenThrow(new BadJwtException(
                "SECRET_INTERNAL_DECODER_DIAGNOSTIC"));

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer bad-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\", error=\"invalid_token\""))
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                not(containsString("SECRET_INTERNAL_DECODER_DIAGNOSTIC"))))
            .andExpect(content().string(""));
    }

    @Test
    void insufficientScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\", error=\"insufficient_scope\""))
            .andExpect(content().string(""));
    }

    @Test
    void expectedScopeAllowsRequest() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk());
    }
}
~~~

**Phạm vi test:** các snippet phụ thuộc Spring Boot application context có `JwtDecoder` và cấu hình ví dụ. `jwt()` của Spring Security Test tạo xác thực giả lập để kiểm tra authorization/handler, không chứng minh chữ ký JWT thật được verify. Test token sai với mocked `JwtDecoder` kiểm tra error response trên đường xác thực. Với môi trường thật, cần test token ký bằng khóa đúng/sai, issuer, audience, expiry và tích hợp IdP/JWK/introspection.

**Lưu ý cú pháp Java ở ví dụ test:** cách tách dòng của `import static` ở trên có thể không phù hợp các bộ định dạng/biên dịch trong dự án khi có dòng xuống sau tên package; nếu sao chép vào IDE, nên giữ toàn bộ qualified import trên một dòng như thông lệ. Class/method test cần nằm trong project Boot với Maven/Gradle, không phải chương trình Java thuần có thể chạy bằng `java SecurityErrorTest`.

### 9.3. Quan sát phản hồi HTTP thực tế

Giả định ứng dụng thực tế đã chạy và đang dùng issuer/endpoint của môi trường thử nghiệm:

~~~bash
# Không mang credentials:
curl -i https://api.example.test/api/reports

# Bearer token không hợp lệ (chỉ là chuỗi ví dụ):
curl -i -H 'Authorization: Bearer bad-token' \
  https://api.example.test/api/reports

# Với token thử nghiệm được cấp hợp lệ và đủ scope:
curl -i -H 'Authorization: Bearer <test-access-token>' \
  https://api.example.test/api/reports
~~~

Không đưa token thật vào shell history, CI logs hoặc ticket; trong test CI dùng secret injection an toàn và cấu hình redaction. Lệnh `curl` chỉ quan sát status/headers/body; không thay được kiểm thử bảo mật cả chuỗi proxy, TLS, token validation, scope và ACL.

Đọc cả `WWW-Authenticate` nếu request lỗi. Không kết luận chỉ từ status: một `401` do reverse proxy Basic authentication khác với `401` từ Resource Server Bearer; header và logs an toàn ở tầng phát sinh quyết định.

### 9.4. Test các tình huống bất lợi

Ngoài happy path, cần thử:

- Không token; Authorization scheme không phải Bearer; header trống, thừa khoảng trắng, sai cú pháp; nhiều nơi gửi token cùng lúc nếu hệ thống hỗ trợ nhiều phương thức.
- Access token hết hạn, chữ ký sai, issuer sai, audience không phù hợp, `nbf` chưa tới, key rotation và lỗi JWK lookup.
- Bearer token hợp lệ nhưng thiếu scope, scope đủ nhưng không thuộc tenant/resource; không biến mọi 403 thành missing scope.
- Error từ authorization server/JWKS timeout; response 5xx hoặc xử lý tạm thời không tiết lộ thông tin nội bộ.
- Request qua gateway/CDN, HTTP/2 và các error-page/filter tùy biến; kiểm tra header có bị loại/ghi đè hoặc cache không mong muốn.
- Response body, logs, tracing, APM, metrics và reverse proxy access logs **không chứa access token/refresh token/Authorization header**, kể cả khi lỗi.
- Đường vào nhiều SecurityFilterChain; các API Bearer cần đúng chain, đúng entry point/denied handler.

## 10. Lỗi triển khai thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không token nhưng server trả `403` thay vì `401` | Entry point hoặc chain bị thay thế; route không được nhận là bearer-only | Kiểm tra security matchers, authentication entry point và exception translation |
| Token hết hạn bị trả HTML login page | API Bearer đang đi qua formLogin/session chain | Tách chính sách chain/API rõ ràng, bảo đảm Bearer entry point áp dụng |
| `401` thiếu `WWW-Authenticate` | Handler custom hoặc proxy xóa challenge | Phục hồi Bearer challenge hợp lệ và integration test ở edge |
| Token sai nhưng response chứa stack trace/JWT claims | Phản chiếu exception message vào header/body | Dùng error code cố định, giấu mô tả, giữ chi tiết ở telemetry đã sanitize |
| Token hợp lệ thiếu scope nhưng trả `401` | Xử lý access denied như authentication failure | Dùng AccessDeniedHandler phù hợp, phân biệt 401 và 403 |
| Mọi lỗi `403` đều gắn `insufficient_scope` | Custom handler không phân loại ACL/tenant/business denial | Gắn insufficient_scope khi thực sự liên quan OAuth permission |
| API trả `400 invalid_request` cho mọi JSON validation lỗi | Nhầm OAuth Bearer invalid_request với payload invalid | Tách xử lý MVC validation và Bearer request |
| Client refresh token vô hạn khi API trả `403` | Client suy luận 403 là token expired | Chỉ refresh khi có điều kiện/flow hợp lệ; xử lý thiếu quyền riêng |
| Header có `scope` chứa quyền nội bộ | Trả quá nhiều thông tin cho client | Bỏ scope hoặc công bố chỉ scope ổn định công khai |
| Token/secret xuất hiện trong log | Logging cả request headers, Authorization hoặc exception | Redact tại app/gateway/APM, quản lý access log nghiêm ngặt |
| JWT hợp lệ với issuer nhưng không đúng audience vẫn được dùng | Thiếu audience validation hoặc policy tenant | Cấu hình xác thực audience/claims đúng với API |
| Gateway trả status khác server Spring Security | Có tầng upstream reject/transform | Kiểm tra trace có kiểm soát, status và header tại client thật |

### Checklist production

- [ ] Phân biệt **thiếu credentials → 401**, **invalid token → 401 invalid_token**, **request Bearer lỗi → 400 invalid_request khi phù hợp**, **token hợp lệ nhưng thiếu scope → 403 insufficient_scope**.
- [ ] Endpoint Bearer trả `WWW-Authenticate` đúng kiểu và không bị gateway/error handler loại bỏ.
- [ ] Không cần mô tả chi tiết thì **bỏ `error_description`**, và chỉ công bố `scope` nếu thật sự an toàn/ổn định.
- [ ] Không rò token, Authorization header, key ID, JWT claims, user/tenant, client secret, stack trace trong error body, headers, logs và APM.
- [ ] Có xử lý lỗi hệ thống/JWKS riêng; không giả mọi lỗi là `invalid_token`.
- [ ] Có test thiếu token, token lỗi, token đúng nhưng thiếu scope, token đủ scope và resource bị ACL chặn.
- [ ] Đã kiểm tra headers/status ở Servlet filter chain và qua reverse proxy/CDN thực tế.
- [ ] Xác thực JWT/introspection đầy đủ theo issuer, expiry, audience, scope/authority và chính sách tài nguyên.

**Kết luận:** `WWW-Authenticate: Bearer` là giao diện lỗi xác thực theo chuẩn HTTP/OAuth2 của Resource Server. Spring Security Servlet đã cung cấp `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`; có thể tùy biến để chỉ công bố **status + mã lỗi tiêu chuẩn** mà không rò decoder exception hay token. Khả năng chẩn đoán phải đến từ metrics/logs đã làm sạch và correlation ID, không phải từ việc trả thông tin nhạy cảm cho người gọi API.
