# Giới hạn chi tiết lỗi để không làm lộ token, khóa hoặc cấu hình nội bộ

## 1. Vì sao lỗi bảo mật cũng là một phần của bề mặt tấn công?

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, ứng dụng nhận Bearer access token, xác thực credential, rồi quyết định quyền truy cập API. Khi gặp lỗi, phản hồi HTTP vừa cần đủ thông tin để client xử lý đúng, vừa **không được biến thành kênh tiết lộ token, khóa, secret, cấu trúc nội bộ hoặc dữ liệu người dùng**.

Hãy hình dung client gửi:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

Nếu chữ ký JWT sai, Resource Server cần từ chối. Nhưng phản hồi không nên là:

```json
{
  "error": "JWT signature verification failed",
  "rawToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
  "issuerJwksUri": "https://internal-idp.svc.cluster.local/keys",
  "expectedKid": "prod-signing-2026-11",
  "stackTrace": "com.example.security.JwtVerifier..."
}
```

Đoạn trên là **ví dụ cố ý không an toàn**: một lỗi authentication đã làm lộ credential của caller, topology triển khai, thông tin key management và các lớp Java nội bộ.

Phản hồi phù hợp hơn cho một Bearer token không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
```

Thông tin công khai chỉ xác nhận **token không được chấp nhận**. Lý do cụ thể như chữ ký sai, token đã hết hạn, sai issuer hoặc không tìm thấy key có thể được xử lý trong **log bảo mật nội bộ đã được bảo vệ và làm sạch**, thay vì công khai qua `error_description` hay body.

> **Mục tiêu kép:** tuân thủ giao thức Bearer để client biết cách phản ứng, nhưng giới hạn dữ liệu lỗi theo nguyên tắc **minimum necessary disclosure**. Client không cần biết private key, JWKS URL nội bộ, cấu hình issuer, token payload hay stack trace để xử lý một HTTP 401.

## 2. Phân loại đối tượng nhận thông tin lỗi

Một lỗi có thể được quan sát ở nhiều nơi; mỗi nơi có giới hạn khác nhau:

| Nơi nhận | Thông tin phù hợp | Thông tin cần loại bỏ hoặc kiểm soát |
| --- | --- | --- |
| **OAuth client** | HTTP status, Bearer challenge, mã lỗi chuẩn, request/correlation ID không nhạy cảm. | Raw access token, refresh token, client secret, private key, token payload, stack trace. |
| **Người dùng cuối** | “Phiên không hợp lệ hoặc đã hết hạn” hoặc “Bạn không có quyền thực hiện thao tác”. | Địa chỉ JWKS, `kid` nội bộ, nhóm policy, chi tiết token introspection. |
| **API gateway / reverse proxy** | Status, route ID công khai, correlation ID và thông tin chẩn đoán được phép. | Header `Authorization`, cookie, query token, exception body nhạy cảm. |
| **Application logs nội bộ** | Mã lỗi đã chuẩn hóa, phase, request ID, issuer identifier được cho phép, latency. | Token nguyên văn, secret, khóa hoặc claim PII không cần thiết. |
| **Security audit hệ thống** | Event type, actor/issuer *đã được xác thực*, source/context phù hợp, quyết định deny/allow. | Dữ liệu chưa được xác thực bị coi là danh tính thật, secret, token đầy đủ. |
| **Metrics/tracing** | Số lần 401/403, loại lỗi có cardinality thấp, thời gian xác thực, kết quả introspection. | Raw token, email, subject tùy ý, `kid` chưa xác thực hoặc exception message làm nhãn metric. |
| **Kênh hỗ trợ người dùng** | Mã tham chiếu sự cố, thời điểm và endpoint chung. | Đề nghị khách hàng dán access token/private key vào ticket hoặc chat. |

**Một lỗi có thể cần điều tra kỹ ở phía server nhưng chỉ cần một phản hồi ngắn ở phía client.** Đừng biến HTTP response thành bản sao của debug log.

## 3. RFC 6750: Bearer challenge và các mã lỗi chuẩn

**RFC 6750 — OAuth 2.0 Bearer Token Usage** định nghĩa cách sử dụng Bearer token và cấu trúc `WWW-Authenticate` khi Resource Server yêu cầu/không chấp nhận credential.

Ba lỗi thường gặp:

| Error code | Ý nghĩa điển hình | HTTP status theo RFC 6750 |
| --- | --- | --- |
| `invalid_request` | Cách truyền token/request sai giao thức: malformed credential, nhiều phương thức truyền token mâu thuẫn hoặc lỗi cú pháp. | Thường **400 Bad Request**. |
| `invalid_token` | Access token bị từ chối: hết hạn, bị thu hồi, malformed, sai chữ ký, sai issuer/audience hoặc không hợp lệ theo hợp đồng. | **401 Unauthorized**. |
| `insufficient_scope` | Token hợp lệ nhưng không có quyền cần thiết cho resource/hành động. | **403 Forbidden**. |

Một API cũng có thể trả **401 khi không gửi credential**, thường với Bearer challenge **không có mã `error`**.

### 3.1. Không gửi Bearer credential

```http
GET /api/orders HTTP/1.1
Host: api.example.test
```

Phản hồi điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Theo RFC 6750, khi request **không chứa thông tin xác thực**, Resource Server không nên thêm mã lỗi chi tiết khiến client tưởng đã gửi một token nhưng token bị xác minh thất bại.

### 3.2. Có Bearer token nhưng token bị từ chối

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

Client có thể hiểu rằng credential đã cung cấp không được chấp nhận; tùy flow, nó có thể xin access token mới, điều hướng đăng nhập lại hoặc dừng gọi API. **Không cần** biết khóa nào sai hoặc claim `exp` cụ thể trong response.

### 3.3. Token hợp lệ nhưng thiếu quyền

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

Đây không phải tình huống yêu cầu client chỉ thử lại **cùng token** nhiều lần. Cần một access token có quyền hợp lệ theo chính sách cấp phép hoặc người dùng/client không có quyền đó.

### 3.4. Request Bearer sai cú pháp

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Ví dụ cụ thể phụ thuộc `BearerTokenResolver` và cấu hình sử dụng token qua header/form/query. Trong mô hình an toàn, nên ưu tiên `Authorization: Bearer` và không bật query-string token chỉ để tiện kiểm thử.

### 3.5. Không có nghĩa mọi 403 đều phải là insufficient_scope

API có thể từ chối quyền sở hữu bản ghi, tenant membership hoặc business policy sau khi authentication thành công. Những lỗi này thường là **403**, đôi khi **404** để hạn chế lộ sự tồn tại tài nguyên, nhưng không nhất thiết được biểu diễn bằng một Bearer challenge `insufficient_scope`. Chỉ dùng mã giao thức khi phản ánh đúng nguyên nhân và handler đang áp dụng.

## 4. Cấu trúc WWW-Authenticate và giới hạn thông tin

Bearer challenge có thể mang các tham số:

| Tham số | Vai trò | Chính sách công khai an toàn |
| --- | --- | --- |
| `realm` | Miền tài nguyên được bảo vệ, hỗ trợ client phân biệt vùng xác thực. | Dùng tên **ổn định, không nhạy cảm**, ví dụ `orders-api`. |
| `error` | Mã lỗi máy có thể xử lý theo RFC 6750. | Dùng enum đã định nghĩa; không lấy chuỗi exception làm error code. |
| `error_description` | Mô tả ngắn, tùy chọn. | Có thể **bỏ hẳn** hoặc dùng text tổng quát cố định. |
| `error_uri` | URL giải thích mã lỗi, tùy chọn. | Chỉ trỏ đến tài liệu **công khai**, không tới console hay đường dẫn nội bộ. |
| `scope` | Scope cần thiết khi từ chối do thiếu quyền, tùy chọn. | Chỉ công bố nếu policy cho phép và client thực sự cần; tránh tiết lộ quyền nội bộ. |

Ví dụ an toàn khi muốn hướng dẫn client mà không lộ hạ tầng:

```http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token is invalid"
```

Ví dụ **không an toàn**:

```http
WWW-Authenticate: Bearer error="invalid_token", error_description="The RSA key kid=prod-2026-11 was not found at https://idp-internal.svc.cluster.local/realms/a/certs; token=eyJ..."
```

**`error_description` là dữ liệu được client nhìn thấy.** Không điền trực tiếp `exception.getMessage()` vào đó, vì lỗi từ decoder/introspection/HTTP client có thể chứa dữ liệu không dành cho caller.

### 4.1. Realm không phải endpoint cấu hình

`realm="orders-api"` không bắt buộc phải là `issuer-uri`, JWKS URI hoặc URL của authorization server. Không được lộ các endpoint nội bộ chỉ vì muốn challenge “có ích hơn”.

Nếu client cần thông tin login/authorization server, hãy cấp qua **tài liệu API hoặc discovery được phép công khai**; không bơm toàn bộ cấu hình runtime vào lỗi.

### 4.2. error_uri không phải nơi chở thông tin lỗi động

Một `error_uri` phù hợp có thể là trang tài liệu:

```text
https://docs.example.test/api/errors#invalid-token
```

Không dùng:

```text
https://debug.internal.example.test/?token=<raw-access-token>&secret=<client-secret>
```

URL có thể bị ghi vào lịch sử, proxy, access logs, referrer hoặc công cụ giám sát. Query string chứa token/secret là đường rò rỉ rõ ràng.

### 4.3. Quy tắc encoding và header injection

`WWW-Authenticate` là một HTTP header có cấu trúc. Không nối bất kỳ message do client kiểm soát vào giá trị header nếu chưa được validate/escape đúng:

```java
// SAI: thông điệp lỗi có thể do thư viện hoặc input không tin cậy sinh ra.
response.setHeader(
        "WWW-Authenticate",
        "Bearer error_description=\"" + exception.getMessage() + "\"");
```

Ngoài thông tin nội bộ, chuỗi có ký tự quote, xuống dòng hoặc control characters có thể phá cấu trúc header hay tạo log/header injection nếu implementation xử lý sai.

Giải pháp đơn giản nhất là **giá trị cố định từ allowlist**, giao việc format challenge cho Spring Security handler được thiết kế cho Bearer.

## 5. Thông tin nào tuyệt đối không nên xuất hiện trong lỗi?

### 5.1. Token và credential

Không xuất qua response, header, log, trace hoặc exception message công khai:

- **Access token**, kể cả chuỗi JWT đã hết hạn hoặc signature sai.
- **Refresh token**, authorization code, device code và session credential.
- `Authorization` header đầy đủ, HTTP Basic credentials và cookies.
- Introspection **client secret**, client assertion private key hoặc mTLS private key.
- Client secret của OAuth client khác nếu có trong cấu hình.
- KMS/HSM key material, JWK private fields như RSA `d`, EC private `d`, secret HMAC `k`.

JWT đã hết hạn **vẫn là thông tin nhạy cảm**: payload có thể chứa claim, subject, tenant, audience và dữ liệu cá nhân; token có thể bị replay trong cửa sổ lỗi clock skew hoặc bị dùng để phân tích hệ thống.

### 5.2. Cấu hình và topology không cần tiết lộ

Ví dụ:

- `issuer-uri` nội bộ, JWKS URI, introspection URI và service discovery host.
- Kubernetes namespace, cluster URL, pod/host name và port nội bộ.
- Đường dẫn key store, secret mount hoặc file cấu hình.
- Tên biến môi trường có giá trị nhạy cảm, stack trace và tên class implementation.
- `kid`/`alg`/trust policy chi tiết khi chưa cần công bố cho client.
- Danh sách tenant, internal role/group mappings và rule chính sách.

Không phải mọi issuer URL hay `kid` đều bí mật theo chuẩn: public JWKS và issuer metadata có thể được công bố hợp pháp. Nhưng **HTTP authentication error không nên tự ý tiết lộ thêm topology hoặc quyết định mật mã nội bộ** ngoài những gì API contract cho phép.

### 5.3. Dữ liệu cá nhân và claim từ token

Không đưa vào response lỗi:

```text
sub=user-123; email=linh@example.test; tenant_id=tenant-secret;
preferred_username=linh; roles=[finance-admin]
```

Đặc biệt, claim lấy từ **token chưa được xác minh** chỉ là dữ liệu do caller cung cấp. Không nên phản hồi “user linh@example.test không tồn tại” dựa trên payload JWT sai chữ ký. Điều đó dễ tạo kênh dò tìm người dùng và phân biệt tình trạng tài khoản.

## 6. Lỗi ở tầng nào? Không phải chi tiết nào cũng nên đi ra ngoài

Chuỗi xác thực/ủy quyền Resource Server có nhiều bước:

```mermaid
flowchart TD
    C["HTTP request"] --> B["BearerTokenResolver"]
    B -->|"Không có credential"| N["401 + Bearer challenge tối giản"]
    B -->|"Sai cấu trúc request"| BR["400 invalid_request"]
    B -->|"Bearer token string"| A["AuthenticationManager"]
    A --> D["JwtDecoder hoặc OpaqueTokenIntrospector"]
    D -->|"Chữ ký/issuer/aud/exp sai hoặc inactive"| E["401 invalid_token"]
    D -->|"Xác thực thành công"| AU["GrantedAuthorities + Authorization"]
    AU -->|"Thiếu scope"| F["403 / insufficient_scope nếu phù hợp"]
    AU -->|"Object/tenant deny"| G["403 hoặc domain 404 theo policy"]
    AU -->|"Đủ quyền"| OK["Controller + domain logic"]
```

Lỗi nội bộ cần gắn **phase** để đội vận hành điều tra chính xác:

| Phase nội bộ | Ví dụ lỗi | Phản hồi công khai thường đủ |
| --- | --- | --- |
| `bearer-extraction` | Header thiếu scheme, Bearer credential malformed, truyền nhiều kiểu token mâu thuẫn. | 400 `invalid_request` hoặc 401 challenge tùy tình huống giao thức. |
| `jwt-parse` | JWT thiếu segments, Base64URL sai, JSON sai. | 401 `invalid_token`. |
| `jws-verification` | Signature không khớp, `alg` không được cho phép, `kid` không tìm thấy candidate key. | 401 `invalid_token`. |
| `claim-validation` | Token hết hạn, sai issuer/audience, token profile không đúng. | 401 `invalid_token`. |
| `opaque-introspection` | AS trả `active:false`. | 401 `invalid_token`. |
| `introspection-dependency` | Timeout, TLS, AS HTTP 5xx hoặc Resource Server client secret sai. | Fail-closed; phản hồi lỗi vận hành an toàn phù hợp, có thể 5xx/503 theo handler. |
| `scope-authorization` | Token hợp lệ nhưng không có quyền endpoint. | 403; `insufficient_scope` khi đúng ngữ nghĩa. |
| `object-authorization` | Actor không sở hữu bản ghi hoặc không thuộc tenant. | 403/404 theo API policy; không lộ chủ sở hữu thật. |
| `application-failure` | NullPointerException, database down, serialization lỗi. | 5xx tổng quát; không stack trace/SQL. |

Những phase name này là **ví dụ về taxonomy nội bộ**, không phải các HTTP Bearer error code mới. Đừng trả `"jws-verification"` hay `"introspection-dependency"` cho client như một mã OAuth 2.0 chuẩn.

### 6.1. Lỗi do dependency không phải token invalid

Khi Resource Server không gọi được introspection endpoint hoặc không tải được JWKS vì lỗi mạng, **không có đủ bằng chứng để chấp nhận token**. Phải fail-closed. Nhưng trong vận hành, nguyên nhân là dependency unavailable, không nên tự ghi audit là “người dùng gửi token giả”.

Phản hồi 5xx/503 tổng quát có thể hợp lý khi thiết kế exception handling phân biệt được lỗi hạ tầng; một số cấu hình framework có thể chuyển lỗi trong authentication thành 401. Quan trọng là **không làm rò thông tin nội bộ**, **không tạo principal giả** và **không nhầm nguyên nhân trong telemetry**.

## 7. Spring Security xử lý Bearer authentication error như thế nào?

Trong Servlet Resource Server, các thành phần thường gặp:

| Thành phần | Trách nhiệm |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Trích token, gọi AuthenticationManager và xử lý một số lỗi authentication ngay tại filter. |
| `DefaultBearerTokenResolver` | Xác định Bearer token trong request theo chính sách. |
| `JwtAuthenticationProvider` / `OpaqueTokenAuthenticationProvider` | Xác thực credential bằng decoder hoặc introspection. |
| `JwtDecoder` / `OpaqueTokenIntrospector` | Xác minh token và metadata theo trust contract. |
| `BearerTokenAuthenticationEntryPoint` | Tạo Bearer challenge khi cần xác thực hoặc authentication thất bại. |
| `BearerTokenAccessDeniedHandler` | Xử lý access denied cho Bearer resource và challenge phù hợp. |
| `ExceptionTranslationFilter` | Chuyển một số `AuthenticationException`/`AccessDeniedException` ở phần sau của filter chain sang phản hồi HTTP. |
| `AuthorizationFilter` / Method Security | Đưa ra quyết định phân quyền sau authentication. |

Một số exception liên quan:

- `OAuth2AuthenticationException`: lỗi OAuth 2.0 có `OAuth2Error`.
- `InvalidBearerTokenException`: Bearer token bị từ chối.
- `BadJwtException`, `JwtValidationException` và các loại `JwtException`: lỗi parsing/chữ ký/claims của JWT.
- `BadOpaqueTokenException`: token opaque bị từ chối.
- `OAuth2IntrospectionException`: sự cố introspection hoặc protocol.
- `AccessDeniedException`: principal không được phép thực hiện hành động.

**Không forward nguyên exception message.** Message từ parser có thể chứa fragment của JWT, claim, `kid` hoặc endpoint; message từ HTTP client có thể chứa status/body của AS hoặc request URI. Những chuỗi này chỉ nên được xử lý trong telemetry đã làm sạch.

### 7.1. BearerTokenAuthenticationEntryPoint

Handler tiêu chuẩn:

```java
BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();
entryPoint.setRealmName("orders-api");
```

`setRealmName` cho phép đặt realm ổn định, không chứa secret. Handler diễn giải `OAuth2AuthenticationException` có `BearerTokenError` để đặt HTTP status và Bearer challenge.

Nếu ứng dụng tự ném:

```java
throw new OAuth2AuthenticationException(
        BearerTokenErrors.invalidToken(
                "JWT failed to validate: issuer=https://internal..."));
```

thì chi tiết đã bị đưa vào `OAuth2Error.description` và có thể xuất hiện trong `error_description`. **Vì vậy, ngay từ nơi tạo lỗi, phải tránh dùng thông tin nhạy cảm làm description công khai**.

## 8. Cấu hình mặc định tối thiểu và phân biệt 401/403

Ví dụ cấu hình Servlet JWT Resource Server:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
                new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler denied =
                new BearerTokenAccessDeniedHandler();
        denied.setRealmName("orders-api");

        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(denied)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là ví dụ dùng API quen thuộc của Spring Security Servlet hiện đại. Để chạy trong dự án thật, còn phải cấu hình **`JwtDecoder` tin issuer/JWKS, xác minh audience và token profile**, các dependencies tương ứng và CSRF policy phù hợp.

Nếu API sử dụng opaque token, thay `.jwt(...)` bằng `.opaqueToken(...)` và cấu hình introspection đúng contract. Nguyên tắc **không tiết lộ lỗi** là như nhau.

Lưu ý: cấu hình entry point/denied handler **không tự bảo đảm mọi error description đều vô hại** nếu upstream exception mang nội dung nhạy cảm. Khi cần giới hạn tuyệt đối, phải **sanitise giá trị `OAuth2Error` trước khi giao cho handler** hoặc chỉ trả các trường được cho phép.

## 9. Tạo một AuthenticationEntryPoint phát Bearer challenge an toàn

Một chính sách thực tế có thể quyết định:

- Request không có credential: chỉ trả `Bearer realm="orders-api"`.
- Bearer request malformed: trả `invalid_request` với description cố định.
- Có token nhưng authentication thất bại: trả `invalid_token` với description cố định.
- Không bao giờ trả raw `exception.getMessage()`, stack trace, token, `kid`, JWKS hay introspection URI.

Ví dụ wrapper sử dụng Spring Security Bearer handler để format challenge:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrorCodes;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;

@Bean
AuthenticationEntryPoint safeBearerEntryPoint() {
    BearerTokenAuthenticationEntryPoint delegate =
            new BearerTokenAuthenticationEntryPoint();
    delegate.setRealmName("orders-api");

    return (request, response, exception) -> {
        if (exception instanceof OAuth2AuthenticationException oauth) {
            // Chỉ dùng error code thuộc allowlist; bỏ message/description gốc.
            String code = oauth.getError().getErrorCode();

            OAuth2AuthenticationException safe =
                    BearerTokenErrorCodes.INVALID_REQUEST.equals(code)
                            ? new OAuth2AuthenticationException(
                                    BearerTokenErrors.invalidRequest(
                                            "Invalid Bearer request"))
                            : new OAuth2AuthenticationException(
                                    BearerTokenErrors.invalidToken(
                                            "Invalid access token"));

            delegate.commence(request, response, safe);
            return;
        }

        // Ví dụ: request không có credential, giữ Bearer challenge tổng quát.
        delegate.commence(request, response, exception);
    };
}
```

Mẫu này chủ động **thay mọi description phát sinh từ `OAuth2AuthenticationException`** bằng chuỗi cố định. Nó tập trung vào quy tắc 400 `invalid_request` và 401 `invalid_token`; nếu hệ thống có thêm loại OAuth2 error được công khai theo hợp đồng, hãy thiết kế allowlist cụ thể và test chính xác.

**Điểm quan trọng khi tùy biến:**

1. Đừng trả mọi exception thành `invalid_token` mà bỏ qua nghĩa `invalid_request` của Bearer resolver.
2. Đừng sửa handler khiến request **không có token** bị mô tả là “token invalid”.
3. Đừng để `exception.getMessage()` lọt vào description hoặc body.
4. Đừng dùng `sendError(status, exception.getMessage())` vì servlet container có thể render message trong HTML error page.
5. Nếu dùng handler riêng cho 503 dependency unavailable, cần định tuyến loại lỗi rõ ràng và vẫn fail-closed.
6. Giữ challenge đúng RFC và kiểm thử với các client/framework đang sử dụng.

### 9.1. Kết nối handler vào Resource Server

```java
@Bean
SecurityFilterChain api(
        HttpSecurity http,
        AuthenticationEntryPoint safeBearerEntryPoint)
        throws Exception {

    BearerTokenAccessDeniedHandler denied =
            new BearerTokenAccessDeniedHandler();
    denied.setRealmName("orders-api");

    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .authenticationEntryPoint(safeBearerEntryPoint)
                    .accessDeniedHandler(denied)
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

Ví dụ là **phương án thay thế** cho bean `SecurityFilterChain` ở mục trước, không phải định nghĩa hai bean cùng matcher `/api/**` song song trong một ứng dụng. Với nhiều security chains, hãy bảo đảm request thực sự đi qua chain và handler được kỳ vọng.

### 9.2. Vì sao ưu tiên Spring handler hơn tự ghép chuỗi header?

Bearer challenge có cú pháp và quy ước status riêng. Spring handler giảm nguy cơ viết sai `WWW-Authenticate`, nhưng **ứng dụng vẫn có trách nhiệm kiểm soát dữ liệu truyền vào handler**. Giải pháp tốt thường là **sanitise OAuth2Error** rồi để Spring tạo challenge, thay vì tự tạo chuỗi nối exception.

## 10. AccessDeniedHandler: lỗi thiếu quyền không phải lỗi token

Sau khi authentication thành công, Spring Security có thể từ chối vì thiếu scope hoặc quyền nghiệp vụ. `BearerTokenAccessDeniedHandler` là lựa chọn chuẩn cho Bearer Resource Server:

```java
BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();
handler.setRealmName("orders-api");
```

Một response điển hình:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

Không nên xây response:

```json
{
  "error": "insufficient_scope",
  "requiredScopes": ["orders:admin", "tenant:root", "finance:write"],
  "currentScopes": ["orders:read", "profile:read"],
  "ownerUserId": "user-456",
  "actualTenant": "tenant-secret"
}
```

Response trên có thể tiết lộ quyền nội bộ, phạm vi quyền của principal, và danh tính chủ sở hữu tài nguyên. Nếu muốn client biết thiếu quyền, thường chỉ cần `403` và `insufficient_scope`, hoặc một scope tổng quát đã được công bố trong API contract.

### 10.1. Có nên trả tham số scope trong challenge?

RFC 6750 cho phép `scope` với `insufficient_scope` để mô tả phạm vi cần thiết. Nhưng đó là **tùy chọn**, không phải nghĩa vụ tiết lộ toàn bộ policy.

Chỉ nên công bố những scope có tính **public API contract**, ví dụ:

```http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:read"
```

Không nên công bố rule nội bộ như `ROLE_SUPER_ADMIN_INTERNAL` hoặc condition tenant của một bản ghi riêng. Nếu API không muốn tiết lộ scope, có thể bỏ tham số này.

### 10.2. Đừng phản ánh thông tin user/tenant trong 403

Thay vì:

```text
User alice@example.test is not a member of tenant "company-acquisition-2026"
```

trả:

```text
Access denied.
```

Có thể ghi **policy ID đã định nghĩa trước**, actor internal ID (đã xác thực) và decision vào audit log được bảo vệ nếu chính sách cho phép. Không ghi email không cần thiết, token đầy đủ hoặc tên tenant nhạy cảm trong client response.

## 11. Khi dùng @ControllerAdvice, không để lỗi nội bộ phủ qua Bearer handler

Một số ứng dụng triển khai global exception handler:

```java
@RestControllerAdvice
class GlobalErrorHandler {

    @ExceptionHandler(Exception.class)
    ResponseEntity<?> handle(Exception ex) {
        return ResponseEntity.status(500)
                .body(Map.of("message", ex.getMessage())); // SAI
    }
}
```

Lỗi ở đây là đưa trực tiếp message của exception vào JSON response. Nội dung có thể là:

- `Authorization` header bị lộ từ HTTP client.
- JWK/JWKS URI, key ID hoặc key material.
- Database SQL, tên bảng/cột, tên class, file path.
- Introspection URI và phản hồi lỗi của AS.
- Dữ liệu tenant/user trong policy exceptions.

Phần lớn authentication failures xảy ra trong **security filter chain trước controller**, nên `@ControllerAdvice` không phải cơ chế duy nhất hoặc phù hợp để xử lý chúng. Nhưng exception trong controller/service hoặc một custom handler có thể đi tới MVC exception resolver; vì thế toàn ứng dụng đều cần chính sách an toàn.

Một mẫu tổng quát cho lỗi ứng dụng:

```java
@RestControllerAdvice
class PublicApiErrorHandler {

    @ExceptionHandler(Exception.class)
    ResponseEntity<Map<String, String>> unexpected(Exception ex) {
        // Log server-side theo chính sách redaction, với correlation ID.
        // Không gửi ex.getMessage() hoặc stack trace ra client.
        return ResponseEntity.status(500)
                .body(Map.of(
                        "code", "INTERNAL_ERROR",
                        "message", "Unable to process the request"));
    }
}
```

Đây là **ví dụ giới hạn nội dung lỗi**, chưa phải thiết kế exception hierarchy hoàn chỉnh. Trong ứng dụng thật, cần handler riêng cho validation, not-found, domain access denied và security exceptions, tránh bắt nhầm làm mọi lỗi thành 500 hoặc làm mất Bearer challenge.

## 12. RFC 7807 / RFC 9457 Problem Details: dùng được nhưng phải tối giản

Một số API muốn thống nhất response body theo **Problem Details for HTTP APIs** (RFC 9457, kế thừa RFC 7807). Có thể dùng format này cho lỗi nghiệp vụ và 5xx:

```json
{
  "type": "https://docs.example.test/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "You are not allowed to perform this action",
  "instance": "/api/orders/42",
  "requestId": "req-7a3c"
}
```

Ngay cả khi body theo Problem Details, **Bearer authentication challenge** vẫn cần xử lý `WWW-Authenticate` theo RFC 6750 khi áp dụng. Problem Details **không thay thế giao thức Bearer**.

Những điều phải tránh:

- `detail` không lấy trực tiếp từ `Exception.getMessage()`.
- `instance` không gắn query string chứa `access_token`, `code` hoặc dữ liệu nhạy cảm.
- `type` không trỏ tới internal dashboard/stack trace.
- Extensions không chứa `rawToken`, `jwksUri`, `privateKey`, `claims` hoặc internal config.
- `requestId` là mã ngẫu nhiên/không chứa PII, có thể dùng để tra cứu log nội bộ theo quyền.

Nếu policy yêu cầu **không tiết lộ sự tồn tại tài nguyên**, một body 404 tổng quát cho “không tồn tại hoặc không được phép” phải được áp dụng nhất quán và tránh lộ owner trong những endpoint khác.

## 13. Token có thể bị lộ qua những kênh nào dù response đã an toàn?

Giả sử Resource Server trả đúng:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Nhưng access token vẫn có thể bị lộ nếu các thành phần xung quanh được cấu hình bất cẩn.

### 13.1. Access logs của reverse proxy

Không nên log raw header:

```text
request_headers={"Authorization":"Bearer eyJ..."}
```

Kiểm tra NGINX/Envoy/API gateway/WAF/ingress và APM agent: **đừng capture `Authorization` hoặc `Cookie` đầy đủ**. Nếu cần biểu diễn sự có mặt của credential, log:

```text
authorization_present=true
authorization_scheme=Bearer
```

Không log token value.

### 13.2. Token trong URL/query string

```text
GET /api/orders?access_token=eyJ...
```

Token trong URL dễ xuất hiện ở browser history, proxy logs, referrer, cache hoặc analytics. Theo RFC 6750, query parameter transport được cảnh báo bởi nhiều rủi ro; Resource Server nên ưu tiên **Authorization header** và **không bật URI query token** trừ khi có yêu cầu tương thích được xem xét.

Trong Spring Security, `DefaultBearerTokenResolver` có cơ chế kiểm soát việc chấp nhận URI query parameter và form encoded body. Không nới lỏng chỉ vì client gặp lỗi 401 mà chưa sửa cách gửi token.

### 13.3. Exception message từ HTTP client

Một `RestClientResponseException` hoặc exception từ introspection HTTP client có thể chứa response body/URL gây lộ metadata. Không lấy:

```java
throw new RuntimeException(
        "introspection failed at " + introspectionUri
        + ": " + exception.getMessage());
```

rồi trả ra client. Trong log nội bộ, ưu tiên **error category, upstream status code, duration** và correlation ID; tránh echo request body `token=...`.

### 13.4. Tracing và OpenTelemetry baggage

Tránh đưa access token, Basic header, refresh token hoặc email vào:

- Trace/span attributes.
- `baggage` hoặc HTTP propagation headers.
- Logs tự động ghi full request/response.
- Distributed tracing dashboards.
- HTTP client metrics tags.

Khi cần biết request authentication thất bại, dùng nhãn thấp cardinality như `auth.outcome=denied` và `auth.reason=jwt_expired` (nội bộ), thay vì `auth.token=<raw-token>`.

### 13.5. Test snapshots, CI artifacts và bug reports

Các bài integration tests dễ in lại response body, HTTP request hay full token khi thất bại. Dùng **test credentials riêng**, scrub log/snapshot, và không đưa secret vào assertion failure messages.

Tránh yêu cầu developer “copy nguyên token production để tái hiện” trong issue tracker. Có thể dùng token giả định, token test ký bằng khóa test hoặc log một correlation ID để tra cứu.

## 14. Logging: đủ để chẩn đoán, không thành kênh rò rỉ

Một ví dụ **không nên làm**:

```java
try {
    return jwtDecoder.decode(token);
} catch (JwtException ex) {
    log.error("Could not decode token {}: {}", token, ex.getMessage(), ex);
    throw ex;
}
```

Đoạn code ghi cả raw token và exception/stack trace. Trong môi trường production, nó tạo một kho JWT có thể truy cập bởi nhiều thành phần vận hành, backup hoặc hệ thống log tập trung.

Một cách ghi log tối giản hơn:

```java
try {
    return jwtDecoder.decode(token);
} catch (JwtException ex) {
    log.warn(
            "Authentication denied: phase={}, category={}, requestId={}",
            "jwt-validation",
            "invalid-token",
            requestId);
    throw ex;
}
```

Mẫu trên giả định `requestId` được lấy từ hệ thống correlation ID do server tạo/kiểm soát và đã được validate. Nếu một request ID đến từ header do client gửi, không dùng nguyên chuỗi chưa kiểm tra làm log identifier.

### 14.1. Có nên log stack trace nội bộ?

Không phải “tuyệt đối không log stack trace” cho mọi lỗi. Với một số **lỗi lập trình** hoặc sự cố hạ tầng đã được redaction, stack trace có thể cần thiết cho vận hành. Nhưng:

1. **Không log stack trace cho mọi invalid token**: attacker có thể gửi hàng nghìn token sai để gây log flooding.
2. **Không chắc exception message không chứa bí mật**: cần đánh giá library và cấu hình trước khi ghi.
3. Phân quyền truy cập logs, đặt retention và audit.
4. Gắn correlation ID, low-cardinality category thay vì raw input.
5. Không gắn stack trace vào response body hoặc `WWW-Authenticate`.

### 14.2. Phân biệt lỗi nội bộ mà không trả lý do ra client

Có thể dùng taxonomy:

```text
auth.failure.type = JWT_SIGNATURE_INVALID
auth.failure.type = JWT_EXPIRED
auth.failure.type = JWT_AUDIENCE_INVALID
auth.failure.type = JWKS_UNAVAILABLE
auth.failure.type = INTROSPECTION_INACTIVE
auth.failure.type = INTROSPECTION_DEPENDENCY_ERROR
auth.failure.type = INSUFFICIENT_SCOPE
auth.failure.type = OBJECT_ACCESS_DENIED
```

Những mã trên là **mã quan sát nội bộ**, không phải tên `error` trong Bearer challenge. Ở phía client, nhiều tình huống vẫn chỉ cần `invalid_token`.

### 14.3. Vì sao không dùng kid làm metric label tự do?

`kid` trong JOSE header có thể được đọc trước signature verification để chọn public key, nhưng **chưa được xác thực ở thời điểm đó**. Attacker có thể gửi hàng nghìn giá trị `kid` ngẫu nhiên và làm metric series tăng không giới hạn. Với observability, chỉ dùng key identifiers đã nằm trong **tập khóa tin cậy và được kiểm soát**, hoặc ghi một giá trị category như `key-not-found`.

## 15. JWT signature và JWKS: nên giấu những chi tiết nào?

Các lỗi thường gặp ở JWT:

- JWS không có ba segment đúng định dạng.
- `alg` không được Resource Server cho phép.
- Chữ ký không khớp public key.
- `kid` không tìm thấy candidate key trong trusted JWKS.
- JWKS endpoint không truy cập được hoặc TLS verification lỗi.
- Token khai issuer/audience khác contract.
- `exp`, `nbf` không hợp lệ.
- Token là OIDC ID token nhưng được gửi tới API như access token.

Đối với **caller không đáng tin**, không cần tiết lộ thứ gì ngoài **token không được chấp nhận**. Ví dụ:

| Nguyên nhân nội bộ | Không nên trả | Nên trả công khai |
| --- | --- | --- |
| Signature invalid | Public key parameters và expected signature. | `401 invalid_token`. |
| `kid` lạ | Danh sách toàn bộ key IDs đang active. | `401 invalid_token`. |
| JWKS URI sai | URL nội bộ và stack trace HTTP client. | Lỗi xác thực/dịch vụ tổng quát theo policy. |
| Wrong issuer | Danh sách issuer tin cậy đầy đủ nếu không phải API contract. | `401 invalid_token`. |
| Wrong audience | Tên tenant, API nội bộ hoặc token claims nguyên văn. | `401 invalid_token`. |
| Token hết hạn | Full payload và exact token timestamps không cần thiết. | `401 invalid_token`, mô tả chung nếu muốn. |
| Thuật toán không được cho phép | Cấu hình thuật toán/key policy chi tiết nội bộ. | `401 invalid_token`. |
| Access token nhầm ID token | Subject/email và toàn bộ profile claims. | `401 invalid_token`. |

**Đừng bỏ validator để giảm lỗi 401**. Việc giới hạn chi tiết lỗi là **điều chỉnh thông tin phản hồi**, không thay đổi điều kiện xác thực token.

### 15.1. Chữ ký hợp lệ nhưng sai audience vẫn phải bị từ chối

Một JWT được ký bởi issuer tin cậy có thể dành cho `payments-api`, không phải `orders-api`. Resource Server vẫn trả `invalid_token` nếu token không thuộc resource của mình. Đừng thông báo chi tiết “token này thuộc payments tenant X” cho caller.

## 16. Opaque introspection: không lộ endpoint, credential hoặc metadata

Với opaque access token, Resource Server có thể gọi AS theo RFC 7662:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <introspection-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<caller-access-token>
```

Hai thông tin nhạy cảm xuất hiện **trên cùng một request**:

1. Basic credential xác thực **Resource Server với AS**.
2. Access token của **caller** trong form body.

Ngoài ra response có thể mang `sub`, `client_id`, `aud`, `scope`, `email` và dữ liệu riêng tư. Không ghi full request/response vào log hoặc phản hồi caller.

### 16.1. HTTP 401 từ AS khác HTTP 401 của API

**AS trả 401 cho introspection request** có thể là:

- Client secret của Resource Server sai/hết hạn.
- Client ID không tồn tại hoặc bị thu hồi.
- Basic/client assertion/mTLS cấu hình không khớp.
- URI hoặc quyền introspection sai.

Đây **không đồng nghĩa** “Bearer token của người dùng sai chữ ký”. Resource Server không được cấp quyền nếu không introspect được, nhưng telemetry nội bộ phải phân biệt **client-auth failure** với `active=false`.

Không gửi lại body lỗi AS:

```json
{
  "error": "invalid_client",
  "client_id": "orders-introspector-prod",
  "endpoint": "https://idp-admin.internal/introspect",
  "detail": "client_secret does not match registration secret_version_12"
}
```

cho caller của API. Nó chứa thông tin cấu hình nội bộ của Resource Server.

### 16.2. Token active=false

```json
{"active": false}
```

Phản hồi chuẩn từ AS không nhất thiết tiết lộ token bị thu hồi, hết hạn hay chưa từng tồn tại. Resource Server cũng không nên tự cung cấp chi tiết thêm cho caller khi không có căn cứ hợp đồng; thường chỉ cần `401 invalid_token`.

### 16.3. Lỗi timeout và fail-closed

Khi AS timeout:

```java
// SAI: phụ thuộc lỗi nên tạo principal giả để hệ thống vẫn chạy.
try {
    return introspector.introspect(token);
} catch (Exception ex) {
    return makeAuthenticatedAdminPrincipal();
}
```

Phải **fail-closed**. Nếu triển khai trả 503 cho dependency unavailable, body/challenge phải vẫn an toàn:

```http
HTTP/1.1 503 Service Unavailable
Cache-Control: no-store
Content-Type: application/json

{"code":"AUTH_SERVICE_UNAVAILABLE","message":"Authentication is temporarily unavailable"}
```

Đây là **mẫu response vận hành có thể thiết kế**, không phải mặc định được mọi phiên bản Spring Security sinh ra. Cần handler exception được xây rõ ràng, test không bật fallback authentication và không lộ thông tin endpoint/credential.

## 17. Đừng để Spring Boot error pages và Actuator làm lộ chi tiết

Nếu một ứng dụng có cấu hình error handling mở quá mức trong production, response 500 hoặc 401/403 đi qua MVC layer có thể mang:

- Exception class và message.
- Binding errors chứa giá trị input nhạy cảm.
- Stack trace.
- Debug message hoặc đường dẫn nội bộ.

Các properties Spring Boot thông dụng để giảm tiết lộ response body:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false
```

Tùy phiên bản Boot, các property names/giá trị cấu hình có thể được quản lý khác nhau; cần kiểm tra phiên bản sử dụng. Các cấu hình trên bảo vệ **lớp Boot error response**, không thay thế `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler` hay chính sách log.

Nếu dùng Actuator:

- Chỉ công bố endpoints cần thiết, qua auth/network policies.
- Không công bố toàn bộ `/actuator/env`, `/actuator/configprops` hoặc heap dump cho public Internet.
- Kiểm soát việc sanitize property values trong Actuator và secret references.
- Bảo vệ các endpoint tracing/heapdump/logfile vì chúng có thể chứa credential hoặc request data.

Một ứng dụng không an toàn nếu 401 được che sạch nhưng mọi người vẫn tải được heap dump có access tokens.

## 18. Reverse proxy, API gateway và CORS

Trong kiến trúc có gateway, phản hồi lỗi có thể được **viết lại** hoặc log bởi nhiều lớp:

```mermaid
flowchart LR
    CLIENT["Browser / OAuth client"] --> G["API Gateway"]
    G --> APP["Spring Resource Server"]
    APP --> LOG["App logs / tracing"]
    G --> EDGE["Gateway logs / WAF"]
    APP --> AS["Authorization Server / JWKS / Introspection"]
    APP --> G
    G --> CLIENT
```

### 18.1. Gateway không nên phản chiếu request headers khi lỗi

Một số gateway debug mode trả:

```json
{
  "message": "Upstream rejected request",
  "requestHeaders": {"Authorization": "Bearer ..."}
}
```

Đây là rò rỉ ngay cả khi Spring Security trả 401 tối giản. Cần áp dụng redaction/response policy ở **cả gateway và ứng dụng**.

### 18.2. CORS không cho phép công khai token

`WWW-Authenticate` là response header trong luồng auth. Nếu frontend cross-origin cần quan sát challenge, cấu hình CORS phải có chủ đích, không bật `Access-Control-Expose-Headers: *` hoặc wildcard origins/credentials vô tội vạ. Việc expose một header không tự cấp quyền, nhưng vẫn có thể làm thông tin challenge xuất hiện trong code browser ở origin được cho phép.

**Không** trả access token trong response header/body để “giúp debug CORS”. OAuth client nên quản lý token theo flow của mình và không gửi credential sang origin không đáng tin.

### 18.3. Cache và 401/403 responses

Với lỗi authentication chứa thông tin liên quan request/user, có thể áp dụng:

```http
Cache-Control: no-store
```

để giảm nguy cơ cache/proxy lưu phản hồi nhạy cảm hoặc dùng lại ở request khác. Đây là một phần của chiến lược cache toàn API, không phải một quy tắc làm mất mọi cache hợp lệ. Tránh để shared CDN cache nhầm response có đặc điểm theo user/token mà thiếu cấu hình phân tách phù hợp.

## 19. Chẩn đoán bảo mật mà không phản chiếu credential

Khi client báo “Token không hoạt động”, một quy trình tốt cần tách **nguyên nhân hệ thống** khỏi dữ liệu bí mật.

### 19.1. Thông tin nên hỏi client

- Thời điểm gần đúng và timezone.
- Request/correlation ID do API trả.
- Endpoint/method HTTP (không bao gồm query credential).
- HTTP status và mã lỗi chuẩn.
- Tên OAuth client application hoặc môi trường nếu đó là thông tin được phép chia sẻ.
- Thời điểm token được xin/refresh, **không yêu cầu raw access token**.

### 19.2. Thông tin điều tra ở phía server

- Log phase `bearer-extraction`, `jwt-validation`, `introspection` hoặc `authorization`.
- Error category đã chuẩn hóa.
- Resource audience/issuer được cấu hình qua danh mục nội bộ, không qua giá trị do token tự khai.
- AS/JWKS availability, latency, TLS/certificate state.
- `kid` đã được xác minh là thuộc trusted JWKS nếu thực sự cần chẩn đoán key rotation.
- Scope/authority mapping và policy evaluation, dưới giới hạn quyền truy cập và bảo vệ dữ liệu.

### 19.3. Không tạo token fingerprint một cách tùy tiện

Đôi khi hệ thống muốn gắn một token fingerprint vào log để gom lỗi. **Không** lấy:

```text
token_prefix = first 30 characters
token_suffix = last 30 characters
```

vì các phần này có thể tiết lộ payload/header/signature hoặc đủ thông tin để liên kết hoạt động nhạy cảm.

Nếu thật sự cần correlation theo token, cân nhắc **HMAC-SHA-256 của token với khóa riêng cho observability**, được bảo vệ và có retention/rotation policy. Không dùng hash đó làm authentication credential hay gửi cho client, và phải đánh giá privacy/linkability. Với nhiều API, request ID thường đơn giản và ít nhạy cảm hơn.

## 20. Test bảo đảm không rò rỉ qua HTTP response

Một hệ thống tốt cần test cả **giao thức** và **absence of secrets**, không chỉ assert status code.

### 20.1. Ma trận test cho Bearer failures

| Tình huống | Status kỳ vọng điển hình | WWW-Authenticate | Không được xuất hiện |
| --- | --- | --- | --- |
| Thiếu Bearer token | 401 | `Bearer` (thường không `error`) | Token giả định, issuer/key settings, stack trace. |
| Bearer malformed | 400 hoặc 401 tùy lỗi resolver và cấu hình | Challenge phù hợp | Header input nguyên văn và exception message. |
| Token hết hạn | 401 | `invalid_token` | `exp`/payload toàn bộ, raw JWT. |
| Token sai signature | 401 | `invalid_token` | Public key, signature, JOSE debug details. |
| JWT sai issuer | 401 | `invalid_token` | Trusted issuer allowlist chưa công bố. |
| JWT sai audience | 401 | `invalid_token` | Tên API/tenant nội bộ trong description. |
| `kid` không tìm thấy | 401 | `invalid_token` | Danh sách keys/JWKS endpoint. |
| Opaque token `active=false` | 401 | `invalid_token` | Response body chi tiết của AS. |
| Opaque introspection client secret sai | Không chấp nhận token; status theo handler fail-closed | Không để lộ AS client auth response | Client ID/secret, introspection URI nội bộ. |
| Token hợp lệ nhưng scope thiếu | 403 | Có thể `insufficient_scope` | Role/tenant policy và owner thật. |
| User truy cập đơn hàng người khác | 403/404 theo policy | Không bắt buộc scope challenge | ID chủ sở hữu thật, dữ liệu đơn hàng. |

### 20.2. Kiểm thử bằng MockMvc

Ví dụ sử dụng `spring-security-test` và cấu hình Resource Server thật hoặc test decoder có chủ đích. Để kiểm tra **một authentication failure**, có thể assert:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BearerFailureDisclosureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void failedAuthenticationDoesNotEchoTokenOrInternalData()
            throws Exception {
        String token = "opaque-test-invalid-credential";
        String privateMarker = "internal-jwks-secret-marker";

        // Test decoder/introspector phải từ chối token này.
        MockHttpServletResponse response = mockMvc.perform(
                get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + token))
                .andExpect(status().isUnauthorized())
                .andReturn()
                .getResponse();

        String exposed = response.getContentAsString()
                + String.valueOf(response.getHeader(
                        HttpHeaders.WWW_AUTHENTICATE));

        assertFalse(exposed.contains(token));
        assertFalse(exposed.contains(privateMarker));
        assertTrue(exposed.contains("invalid_token"));
    }
}
```

Ví dụ giả định Spring Security chain được bật, decoder/introspector test **thực sự từ chối token** và entry point phát Bearer challenge. `privateMarker` là giá trị giả để chứng minh cách viết assertion; một test leak mạnh hơn nên **chủ động tạo exception từ dependency có chứa marker đó**, rồi xác nhận response đã scrub.

### 20.3. Test exception có chứa secret marker

Một test bean có thể giả lập dependency ném:

```java
// Giá trị chỉ dùng trong test, không phải private key thật.
String sensitive = "TEST-PRIVATE-KEY-MARKER";

// Fake decoder/introspector ném lỗi chứa marker.
// Đưa request thật qua Resource Server filter chain.
// Assert response body và tất cả response headers không chứa marker.
```

Điều này kiểm tra **cả lỗi do upstream có nội dung nhạy cảm** chứ không chỉ token gửi từ client. Test cũng nên kiểm tra body HTML/JSON được tạo bởi servlet container hoặc `/error` endpoint.

### 20.4. Test 401 khác 403

Hai request nên được phân biệt:

```java
// Token không hợp lệ → authentication failure → 401.
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-test-token"))
        .andExpect(status().isUnauthorized());

// Authentication được giả lập hợp lệ nhưng thiếu authority → 403.
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(new GrantedAuthority[0])))
        .andExpect(status().isForbidden());
```

**`jwt()` của Spring Security Test không tự chạy JWT signature verification.** Dùng nó để kiểm tra authorization/response sau khi có principal mock; không xem nó là bằng chứng authentication error sanitizer hoạt động. Với token thật và JWT decoder, cần test riêng thông qua `Authorization` header.

### 20.5. Test logs và tracing bằng dữ liệu giả

Để kiểm tra không rò rỉ credential trong log:

1. Phát token giả có marker dễ tìm, ví dụ `TEST-TOKEN-LEAK-MARKER`.
2. Tạo một error test có marker trong nested exception message.
3. Gửi request qua gateway/Resource Server/HTTP introspection mock nếu cần.
4. Thu output log/traces của **môi trường test** đã cô lập, theo cơ chế appender/collector giả.
5. Xác nhận marker không xuất hiện trong logs, response body, headers hay tracing attributes.
6. Test thêm `Authorization: Basic ...` và `token=...` của introspection.

Đây là **định hướng kiểm thử**, không phải kết quả test đã chạy trong repository. Chỉ dùng fake tokens/keys/credentials của môi trường test.

## 21. Công cụ giám sát và phản ứng sự cố

Không phải mọi 401 đều là dấu hiệu tấn công; có thể do client hết hạn token. Nhưng nhiều lỗi bất thường liên tiếp có thể phản ánh abuse hoặc cấu hình sai.

### 21.1. Metrics hữu ích

| Metric/nhãn | Giá trị khuyến nghị | Cần tránh |
| --- | --- | --- |
| `auth_result` | `success`, `denied`, `error`. | Raw access token. |
| `auth_phase` | `bearer`, `jwt`, `introspection`, `authorization`. | Exception message. |
| `failure_category` | `expired`, `invalid_signature`, `audience_mismatch`, `upstream_timeout` theo allowlist. | Unverified `iss`/`kid` tùy ý làm nhãn. |
| `http_status` | 400, 401, 403, 5xx. | Email/user name trong tag. |
| `upstream_status` | 2xx, 401, 429, 5xx của AS. | Full introspection response body. |
| `request_id` | Trong log/traces có kiểm soát, giá trị an toàn. | Tự đưa toàn bộ request ID làm metric series cardinality cao. |

### 21.2. Rate limiting và log flooding

Attacker có thể gửi hàng nghìn JWT sai chữ ký để tạo lượng lớn stack traces, JWKS fetches hoặc introspection requests. Ngoài response minimization:

- Áp dụng rate limiting ở gateway/resource phù hợp.
- Có timeout và bounded retries với JWKS/introspection.
- Dùng sampling/aggregation cho các lỗi lặp lại.
- Tránh gọi JWKS URL tùy ý do JOSE `jku`/`x5u` trong token đề nghị.
- Hạn chế thông tin lỗi để tránh biến decoder thành “oracle” giúp attacker suy đoán valid key/claims.

### 21.3. Có nên tiết lộ “token expired” cho client?

Một số client hợp lệ muốn phân biệt hết hạn với sai chữ ký để tự refresh token. Về mặt giao thức, `invalid_token` thường đã đủ cho nhánh refresh/re-authentication; chi tiết “expired” là **tùy chọn thiết kế**, cần cân nhắc khả năng oracle và thông tin bổ sung.

Nếu hệ thống chủ động công bố `error_description="The access token expired"`, phải là **chuỗi cố định**, không nối raw token, timestamps/claims chưa xác thực hay nội bộ verifier. Cách tối thiểu hơn là chỉ trả `invalid_token`, còn client quyết định xin token mới theo OAuth flow của mình.

## 22. Các anti-pattern cụ thể

### Anti-pattern 1 — Trả `exception.getMessage()` cho client

Message có thể chứa token, `kid`, URL hoặc stack trace. Dùng mã lỗi công khai đã định nghĩa và thông điệp cố định.

### Anti-pattern 2 — Đưa raw JWT vào log để debug 401

JWT có thể chứa dữ liệu cá nhân, scope và chữ ký; log dài hạn tạo nơi lưu credential ngoài kiểm soát. Dùng correlation ID và category.

### Anti-pattern 3 — Echo header `Authorization` trong response

Không đưa request headers đầy đủ vào body debug, đặc biệt ở API gateway hoặc `@ControllerAdvice`.

### Anti-pattern 4 — Trả danh sách public keys/kid khi signature fail

Việc `kid` không khớp thuộc nội bộ lựa chọn khóa. Đừng đưa toàn bộ JWKS nội bộ vào `error_description`.

### Anti-pattern 5 — Trả introspection client secret hoặc upstream response

Một HTTP 401 từ AS có thể liên quan client secret của Resource Server, không phải caller token. Không forward upstream body/headers chứa metadata nhạy cảm.

### Anti-pattern 6 — Trả scope/role/tenant policy quá chi tiết khi 403

Cho client biết thiếu quyền theo mã chuẩn, nhưng không xuất group map, owner ID hoặc role admin nội bộ.

### Anti-pattern 7 — Sử dụng error_uri trỏ vào console nội bộ

Chỉ dùng tài liệu công khai. Không gắn token hoặc secret vào query string.

### Anti-pattern 8 — Bật debug/profiling production vô thời hạn

Debug logs, full tracing, heap dumps và Actuator có thể lưu credential. Cần chế độ vận hành, retention và phân quyền.

### Anti-pattern 9 — Tắt authentication validation để không xuất lỗi

Không được chọn “trả 200 cho token sai” như giải pháp giảm thông tin lỗi. Giữ fail-closed; chỉ giảm lượng thông tin đưa ra ngoài.

### Anti-pattern 10 — Mọi lỗi đều trả 401 invalid_token

Lỗi scope thiếu trên token hợp lệ thường là 403; lỗi syntax có thể là 400; lỗi AS unavailable là lỗi dependency. Đừng phá giao thức/giám sát chỉ để có một response đơn giản.

### Anti-pattern 11 — Một body 500 chứa tên SQL/key store

Không chỉ Bearer: mọi error response của ứng dụng phải tránh stack traces, SQL và đường dẫn secrets, kể cả khi lỗi xuất hiện sau authentication.

### Anti-pattern 12 — Xem dữ liệu chưa xác thực là nguồn thông tin audit

`sub`, `email` và `tenant_id` từ JWT chưa xác minh có thể do attacker tạo giả. Nếu ghi để điều tra, phải đánh dấu rõ “unverified input” và giới hạn nội dung; không dùng làm actor identity đã xác thực.

## 23. Tình huống vận hành minh họa

### A. Token hết hạn

Client gọi API với access token đã hết hạn. Resource Server trả **401 invalid_token** mà không tiết lộ payload hoặc expiration timestamp cụ thể. Client dùng OAuth flow hợp lệ để lấy token mới. Server log có thể phân loại `JWT_EXPIRED` theo policy đã định nghĩa.

### B. JWKS cache chưa nhận key mới

Issuer xoay khóa, token có `kid` mới, Resource Server cache cũ chưa thấy public key tương ứng. Client vẫn chỉ nhận phản hồi token không được chấp nhận hoặc lỗi dependency theo chính sách. Server telemetry ghi `JWKS_KEY_NOT_FOUND`/`JWKS_REFRESH_FAILED` có kiểm soát; không trả JWKS URI nội bộ hoặc danh sách keys.

### C. Token từ issuer không được tin cậy

Attacker tự tạo JWT với `iss` giống một URL và `aud=orders-api`. Resource Server không động tải JWK từ issuer chưa cho phép. Phản hồi tổng quát `invalid_token`, không tiết lộ allowlist issuer trong body.

### D. API người dùng thiếu quyền xem đơn hàng

JWT hợp lệ có `orders:read` nhưng actor không sở hữu `orderId`. API áp dụng object-level authorization, trả **403** hoặc 404 theo chính sách che dấu tài nguyên. Không ghi chủ sở hữu thật vào response.

### E. Introspection client secret đã bị rotation

Tất cả opaque tokens đồng loạt lỗi vì Resource Server dùng secret cũ khi gọi AS. AS trả HTTP 401 **cho API**. Server phải fail-closed, cảnh báo và sửa credential version. Không gửi upstream `invalid_client` body chứa client registration/secret details cho caller, và không chẩn đoán nhầm là người dùng hết quyền.

### F. Một lỗi trong `@ControllerAdvice` trả stack trace

Sau khi authentication thành công, controller ném exception do database. Nếu handler đưa `ex.toString()` hoặc stack trace vào JSON, nó có thể lộ cấu trúc DB. Cần handler trả thông điệp cố định `INTERNAL_ERROR` và log nội bộ đã scrub.

### G. Gateway lưu Authorization header khi request 401

Spring Security trả đúng Bearer challenge an toàn, nhưng API gateway debug log vẫn ghi full token. Điều này chứng minh **giới hạn lỗi phải áp dụng end-to-end**, không chỉ ở Spring controller.

### H. Ứng dụng muốn hiển thị nút “Đăng nhập lại”

Frontend thường chỉ cần biết **401 invalid_token** để xin token mới hoặc chuyển về flow login. Không cần nhận raw JWT claims, private key, JWKS URL hay tên IdP tenant nội bộ.

## 24. Câu hỏi tự kiểm tra

**1. Khi thiếu Bearer token, Resource Server có nên trả `error="invalid_token"` không?** Không mặc định. Theo RFC 6750, khi chưa có authentication information, Bearer challenge thường không có error code.

**2. JWT sai chữ ký nên trả gì?** Thường `401 Unauthorized` với `WWW-Authenticate: Bearer error="invalid_token"`, không kèm token hoặc key details.

**3. Access token hợp lệ nhưng thiếu scope endpoint nên trả gì?** Thường `403 Forbidden`; `insufficient_scope` nếu đúng ngữ nghĩa Bearer và handler.

**4. error_description có bắt buộc không?** Không. Có thể bỏ hoặc dùng chuỗi cố định an toàn.

**5. Có được trả `exception.getMessage()` trong `error_description` không?** Không nên. Nó có thể chứa token, issuer URI, JWKS, HTTP response nội bộ và stack trace.

**6. Public key/JWKS có phải luôn bí mật không?** Public keys có thể công khai theo thiết kế, nhưng error response không nên tự tiết lộ topology/key inventory nội bộ; private keys và shared secrets phải được bảo vệ tuyệt đối.

**7. Vì sao HTTP 401 từ AS không đồng nghĩa token của caller invalid?** Vì AS có thể đang từ chối credential của **Resource Server khi introspect**, khác với trạng thái access token đang được hỏi.

**8. Có thể log raw token trong debug log tạm thời không?** Đây là rủi ro cao; nên dùng marker/test token, correlation ID và log category. Nếu phát hiện đã log token thật, xử lý theo quy trình credential exposure.

**9. `@ControllerAdvice` có bắt được mọi lỗi do BearerTokenAuthenticationFilter không?** Không. Nhiều lỗi authentication xảy ra trong security filter chain trước MVC; cần AuthenticationEntryPoint/AccessDeniedHandler và error handlers ở các tầng tương ứng.

**10. Vì sao `WWW-Authenticate` cần được kiểm thử?** Vì đây là contract Bearer cho client, bao gồm mã lỗi, HTTP status và khả năng lộ thông tin qua description/scope.

**11. Có nên đưa tên owner/tenant vào 403 để client debug không?** Không nên; đó có thể là thông tin truy cập trái phép. Dùng mã lỗi tổng quát và correlation ID.

**12. Có thể biến JWKS unavailable thành allow-all để không phát sinh 401 không?** Không. Khi chưa xác minh được token, phải fail-closed và xử lý dependency error đúng chính sách.

**13. Token đã hết hạn thì log nguyên nó có an toàn không?** Không. Token cũ vẫn có thể chứa PII hoặc thông tin hệ thống và gây rủi ro nếu bị thu thập.

**14. Để test leak, chỉ cần assert HTTP status là đủ chưa?** Chưa. Cần assert body, response headers, logs/traces (bằng dữ liệu test) không chứa raw token, secret marker, internal URLs hay exception details.

**15. Có cần bảo vệ gateway/Actuator khi Spring Security đã sanitize 401?** Có. Reverse proxy logs, tracing, heap dumps và Actuator có thể trở thành đường rò rỉ độc lập.

## 25. Tài liệu chuẩn và API tham khảo

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `WWW-Authenticate`, `invalid_request`, `invalid_token`, `insufficient_scope` và hướng dẫn tránh token trong URI. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, quyền truy cập introspection và việc xác thực Resource Server khi gọi endpoint. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc claims; JWT không mã hóa payload mặc định. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh token, ràng buộc issuer/audience và phòng tránh nhầm ngữ cảnh. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9110 — HTTP Semantics:** 401, 403, 404 và cơ chế authentication challenge. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9457 — Problem Details for HTTP APIs:** body lỗi API có cấu trúc và cách giảm thông tin không cần thiết. https://www.rfc-editor.org/rfc/rfc9457
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** `JwtDecoder`, Bearer token handling, entry point và scope authorities. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** `OpaqueTokenIntrospector` và introspection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security API — BearerTokenAuthenticationEntryPoint / BearerTokenAccessDeniedHandler / BearerTokenErrors:** các handler và lỗi chuẩn của Bearer Resource Server; xem Javadoc tương ứng phiên bản.
- **OWASP Cheat Sheet Series — Logging Cheat Sheet:** kiểm soát việc ghi security events, PII và secrets vào log. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **Spring Boot Reference — Error Handling và Actuator Security:** bảo vệ error response và endpoint vận hành, tùy dòng Spring Boot đang dùng.

**Kết luận:** Resource Server cần trả **đúng HTTP status và Bearer error code**, nhưng chỉ với **lượng thông tin tối thiểu**. Dùng `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` theo hợp đồng RFC 6750; loại bỏ raw token, key, secret, issuer/JWKS/introspection config và exception message khỏi `error_description`, body và headers. Giữ chi tiết kỹ thuật trong **log/tracing/audit nội bộ đã scrub và giới hạn quyền**, dùng correlation ID để hỗ trợ điều tra. Khi authentication không thể xác minh, phải **fail-closed**; khi principal hợp lệ nhưng thiếu scope hoặc quyền sở hữu, áp dụng authorization độc lập. **Giấu chi tiết lỗi không có nghĩa giấu sai trạng thái giao thức hoặc nới lỏng xác thực.**
