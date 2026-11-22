# Kiểm thử thiếu token, token sai cú pháp và phản hồi WWW-Authenticate

Trong một **Spring Security OAuth 2.0 Resource Server dùng Servlet**, ba tình huống cần được kiểm thử riêng:

1. Request đi vào endpoint được bảo vệ nhưng **không gửi access token**.
2. Request gửi `Authorization: Bearer ...` nhưng **header hoặc token sai cú pháp/không hợp lệ**.
3. Resource Server từ chối request và phải trả **HTTP status cùng `WWW-Authenticate` challenge** đúng ngữ nghĩa.

Những tình huống này nhìn qua đều có thể trả 401, nhưng ý nghĩa khác nhau. Client cần biết khi nào chưa gửi credential, khi nào token không thể xác thực và khi nào token đã hợp lệ nhưng thiếu quyền.

**RFC 6750** định nghĩa ba error code quan trọng cho bearer access token:

- `invalid_request`: request mang token sai cách hoặc cấu trúc request không hợp lệ; Resource Server thường trả **400 Bad Request**.
- `invalid_token`: token hết hạn, bị revoke, malformed hoặc không hợp lệ vì lý do khác; Resource Server thường trả **401 Unauthorized**.
- `insufficient_scope`: token hợp lệ nhưng không có quyền đủ cho tài nguyên; Resource Server thường trả **403 Forbidden**.

Khi request không chứa thông tin xác thực, RFC yêu cầu Resource Server gửi `WWW-Authenticate`, nhưng **không nên gửi error code hoặc thông tin lỗi chi tiết** trong challenge đó.

> **Nguyên tắc kiểm thử:** assert cả status và header `WWW-Authenticate`. Một test chỉ kiểm tra `status().isUnauthorized()` không chứng minh server phân biệt đúng missing credentials, malformed bearer header và invalid token.

Bài này sử dụng Spring Security Servlet, Spring MVC Test và **MockMvc có filter chain thật**. Các ví dụ giả định Spring Boot và Spring Security hiện đại, Java 17+, JUnit 5. WebFlux dùng `WebTestClient` và các server-side handlers reactive tương ứng.

## 1. Phân biệt ba loại lỗi trước khi viết test

### 1.1. Không có bearer credential

Request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

Endpoint yêu cầu authentication, nhưng request không có `Authorization: Bearer ...`.

Kết quả điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Nếu cấu hình realm:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Không có `error="invalid_token"` vì client chưa gửi token để Resource Server kiểm tra. RFC 6750 nói rằng khi request thiếu thông tin xác thực, Resource Server **SHOULD NOT** thêm error code hoặc thông tin lỗi khác.

### 1.2. Token malformed hoặc invalid

Request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJub25lIn0.invalid.signature
~~~

Client đã cố xác thực bằng bearer token, nhưng token không hợp lệ. Ví dụ:

- Header không đúng cú pháp bearer.
- Token không parse được.
- JWT có chữ ký sai.
- JWT dùng thuật toán không được chấp nhận.
- `iss` hoặc `aud` không đúng.
- Token hết hạn hoặc chưa tới `nbf`.
- Opaque token được introspection xác định là inactive.

Kết quả điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Spring có thể thêm `error_description` hoặc `error_uri` theo lỗi và cấu hình. Giá trị mô tả cụ thể không nên được xem là chuỗi ổn định cho mọi version.

### 1.3. Request sai cách truyền token

Ví dụ client gửi cùng một access token qua nhiều phương thức:

~~~http
GET /api/orders?access_token=query-token HTTP/1.1
Host: api.example.com
Authorization: Bearer header-token
~~~

RFC 6750 yêu cầu client chỉ dùng **một phương thức truyền bearer token trong mỗi request**. Khi Resource Server nhận thấy nhiều nguồn token hoặc tham số token lặp/sai cấu trúc, error phù hợp là `invalid_request`, thường kèm HTTP 400:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

Spring Security `DefaultBearerTokenResolver` mặc định chỉ đọc `Authorization` header. Query parameter và form body token transport bị tắt mặc định. Nếu ứng dụng bật các cơ chế này, resolver có thể phát hiện token ở nhiều nơi và từ chối request.

### 1.4. Token hợp lệ nhưng không đủ quyền

Request:

~~~http
GET /api/orders/export HTTP/1.1
Host: api.example.com
Authorization: Bearer <valid-access-token>
~~~

Giả sử token đã được xác thực nhưng chỉ có `SCOPE_orders.read`, trong khi endpoint yêu cầu `SCOPE_orders.export`.

Kết quả điển hình:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Đây là authorization failure. Token đã qua authentication; Resource Server từ chối vì caller không đủ quyền.

## 2. Bảng phân loại lỗi theo RFC 6750

| Tình huống | Error code | HTTP status thường dùng | Ý nghĩa |
|---|---|---:|---|
| Không gửi token | Không có error code | 401 | Client cần biết endpoint yêu cầu Bearer authentication |
| Gửi sai authentication scheme, ví dụ `Basic` vào API chỉ hỗ trợ Bearer | Thường không có error code | 401 | Resource Server không nhận được Bearer credential |
| Bearer header malformed | `invalid_token` trong Spring mặc định khi resolver nhận diện scheme Bearer nhưng cú pháp sai | 401 | Không trích xuất được token hợp lệ |
| Token parse/verify thất bại | `invalid_token` | 401 | Credential đã gửi nhưng không hợp lệ |
| Token expired/revoked | `invalid_token` | 401 | Token không còn dùng được |
| Truyền token bằng nhiều phương thức | `invalid_request` | 400 | Request không tuân thủ cách truyền bearer token |
| Token parameter lặp hoặc rỗng khi resolver hỗ trợ transport đó | `invalid_request` | 400 | Request parameters không hợp lệ |
| Token hợp lệ nhưng thiếu scope/privilege | `insufficient_scope` | 403 | Authentication thành công, authorization bị từ chối |
| Thiếu CSRF token khi CSRF được bật | Không nhất thiết là Bearer error | 403 | CSRF filter từ chối request |
| Introspection/JWKS dependency lỗi | Phụ thuộc exception handling | Có thể 5xx hoặc authentication error | Không thể xác minh token do dependency lỗi |

**Không gộp mọi lỗi thành 401.** Với API client, phân loại đúng giúp quyết định có nên lấy token mới, sửa request hay xin thêm quyền.

## 3. `WWW-Authenticate` là protocol header, không phải JSON error body

`WWW-Authenticate` là HTTP response header cho biết server chấp nhận authentication scheme nào và có thể cung cấp thêm thông tin về lỗi.

Bearer challenge có dạng:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Hoặc kèm error parameters:

~~~http
WWW-Authenticate: Bearer realm="orders-api",
                  error="invalid_token",
                  error_description="The access token expired"
~~~

Các thành phần phổ biến:

| Attribute | Ý nghĩa | Ghi chú |
|---|---|---|
| `Bearer` | Authentication scheme | Bắt buộc trong challenge theo RFC 6750 |
| `realm` | Vùng bảo vệ/tên miền bảo vệ | Optional |
| `error` | Mã lỗi OAuth bearer | Optional; dùng khi có lỗi xác thực/ủy quyền tương ứng |
| `error_description` | Giải thích cho developer | Optional, không dành để hiển thị trực tiếp cho end-user |
| `error_uri` | URI tài liệu giải thích lỗi | Optional |
| `scope` | Scope cần thiết cho resource | Optional, chỉ nên gửi giá trị có ý nghĩa theo contract |

### 3.1. Missing token không nên có `invalid_token`

Đúng:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Không nên:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token",
                  error_description="Token is invalid"
~~~

Trong ví dụ thứ hai, client chưa gửi token. Server không có token nào để kết luận token invalid.

### 3.2. Token invalid nên có `invalid_token`

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Client có thể xin access token mới nếu grant/refresh policy cho phép, sau đó gửi request lại.

Không nên đưa raw token, toàn bộ JWT payload, signing key, introspection response nhạy cảm hoặc stack trace vào `error_description`.

### 3.3. `insufficient_scope` thuộc 403

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

RFC cho phép server thêm `scope` để chỉ ra quyền cần thiết. Tuy nhiên, không phải mọi authorization failure đều chỉ do OAuth scope; ứng dụng còn có role, tenant membership, ownership và business policy. Hãy chọn error description phù hợp và tránh tiết lộ chi tiết policy nội bộ.

### 3.4. Không mặc định response body phải có JSON

RFC 6750 quy định status và `WWW-Authenticate`; nó không yêu cầu một JSON error body cụ thể.

Spring Security mặc định thường trả status và challenge header, không tự tạo một body JSON theo schema riêng của ứng dụng. Nếu API cần body như:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A bearer access token is required"
}
~~~

thì ứng dụng có thể triển khai `AuthenticationEntryPoint`/`AccessDeniedHandler` tùy chỉnh. Khi làm vậy, vẫn phải giữ `WWW-Authenticate` theo RFC; không thay protocol header bằng JSON body.

## 4. Spring Security xử lý request như thế nào?

Với Servlet Resource Server, đường đi cơ bản:

~~~text
HTTP request
     |
     v
FilterChainProxy
     |
     v
SecurityFilterChain
     |
     v
BearerTokenAuthenticationFilter
     |
     +-- BearerTokenResolver
     |      |
     |      +-- Không tìm thấy token -> tiếp tục filter chain
     |      |
     |      +-- Header malformed -> AuthenticationException
     |      |
     |      +-- Tìm thấy token -> BearerTokenAuthenticationToken
     |
     v
AuthenticationManager / AuthenticationProvider
     |
     +-- JWT -> JwtAuthenticationProvider -> JwtDecoder
     |
     +-- Opaque -> OpaqueTokenAuthenticationProvider -> Introspector
     |
     v
SecurityContextHolder
     |
     v
AuthorizationFilter
     |
     +-- Permit/authority đủ -> controller
     |
     +-- Anonymous/unauthenticated -> ExceptionTranslationFilter
     |                                  |
     |                                  v
     |                           AuthenticationEntryPoint
     |
     +-- Authenticated nhưng bị từ chối -> AccessDeniedHandler
~~~

Các chi tiết quan trọng:

- `BearerTokenResolver` tìm token từ request.
- `BearerTokenAuthenticationFilter` tạo authentication request và gọi `AuthenticationManager`.
- JWT provider xác minh bằng `JwtDecoder`.
- Opaque provider gọi `OpaqueTokenIntrospector`.
- `BearerTokenAuthenticationEntryPoint` chuyển lỗi authentication thành status và `WWW-Authenticate`.
- `BearerTokenAccessDeniedHandler` chuyển lỗi authorization thành 403 và Bearer challenge khi request có OAuth authentication hợp lệ.

### 4.1. `DefaultBearerTokenResolver` mặc định đọc từ đâu?

Mặc định Spring Security đọc:

~~~http
Authorization: Bearer <access-token>
~~~

`DefaultBearerTokenResolver` có thể được cấu hình để đọc token từ custom header, form body hoặc query parameter. Tuy nhiên:

- Form body token parameter mặc định tắt.
- Query parameter token mặc định tắt.
- RFC 6750 khuyến nghị tránh query parameter vì URL có thể bị lưu trong logs, browser history, proxy và monitoring.
- Client không nên gửi cùng token qua nhiều phương thức.

Nếu ứng dụng chỉ chấp nhận `Authorization` header, test query parameter không nên bị nhầm với một bearer token hợp lệ.

### 4.2. Header sai cú pháp và token sai nội dung là hai điểm thất bại khác nhau

Ví dụ header sai cú pháp:

~~~http
Authorization: Bearer bad"token
~~~

`DefaultBearerTokenResolver` nhận diện Bearer scheme nhưng token không khớp grammar mà resolver chấp nhận. Trong implementation mặc định hiện hành, resolver ném lỗi `invalid_token` trước khi decoder được gọi.

Ví dụ token string đúng grammar nhưng không phải JWT hợp lệ:

~~~http
Authorization: Bearer not-a-jwt
~~~

Chuỗi này có thể qua bước trích xuất bearer token nhưng decoder sẽ không parse được JWT. Kết quả cũng là `invalid_token`, nhưng lỗi phát sinh ở bước decode/verification.

Vì vậy, test nên tách:

1. Header malformed — kiểm tra `BearerTokenResolver`.
2. Token malformed/invalid — kiểm tra `AuthenticationProvider` và decoder/introspector.

### 4.3. Sai scheme không giống malformed Bearer

Request:

~~~http
Authorization: Basic dXNlcjpwYXNz
~~~

Nếu API chỉ cấu hình Resource Server Bearer, resolver mặc định không coi đây là Bearer token. Với endpoint private, request thường bị từ chối như **missing Bearer credentials** và challenge `WWW-Authenticate: Bearer` không có `invalid_token`.

Điều này khác với:

~~~http
Authorization: Bearer bad"token
~~~

Header thứ hai đã cố dùng Bearer scheme nhưng cú pháp token sai.

## 5. Cấu hình Resource Server cho các test

Một API JWT-only đơn giản:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/export")
                    .hasAuthority("SCOPE_orders.export")
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ này giả định:

- API chỉ dùng Bearer header để authentication.
- JWT decoder được cấu hình bằng `issuer-uri`, `jwk-set-uri` hoặc một `JwtDecoder` bean.
- `SCOPE_orders.read` và `SCOPE_orders.export` được ánh xạ từ claims theo contract.
- API không dùng cookie/session để tự động gửi credential.

Nếu ứng dụng là bearer-only API, có thể cân nhắc tắt CSRF sau khi xác nhận credential model:

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

Không tắt CSRF chỉ vì ứng dụng dùng JWT hoặc `SessionCreationPolicy.STATELESS`. Nếu browser tự gửi cookie để authentication, CSRF vẫn cần được đánh giá.

### 5.1. Dependency test

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot BOM quản lý version tương ứng. Không ghép `spring-security-test` từ một minor version khác với runtime đang chạy.

## 6. Dùng MockMvc với SecurityFilterChain thực tế

### 6.1. Spring Boot test

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BearerChallengeIntegrationTests {

    @Autowired
    MockMvc mvc;
}
~~~

`@AutoConfigureMockMvc` mặc định đăng ký servlet filters từ application context. Để test Spring Security, không cấu hình:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

vì lựa chọn này bỏ qua filters và làm mất đường xử lý Bearer token.

### 6.2. Tự tạo MockMvc từ WebApplicationContext

Nếu không dùng Boot auto-configuration:

~~~java
@BeforeEach
void setUp() {
    mvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
}
~~~

`springSecurity()` gắn bean `springSecurityFilterChain` vào MockMvc và tích hợp các test security context helpers. Nếu thiếu bước này, test có thể đi thẳng tới MVC mà không chạy `FilterChainProxy`.

### 6.3. Đừng dùng `standaloneSetup` để kết luận filter chain đã chạy

~~~java
MockMvcBuilders
    .standaloneSetup(new OrdersController(service))
    .build();
~~~

Cách này hữu ích cho controller unit test, nhưng không tự tải toàn bộ application security configuration. Nếu cần test filter chain thật, ưu tiên `@SpringBootTest` hoặc `webAppContextSetup(...).apply(springSecurity())`.

## 7. Test endpoint private khi không có token

Test cơ bản:

~~~java
@Test
void protectedEndpointWithoutTokenReturns401AndBearerChallenge()
        throws Exception {

    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ));
}
~~~

Để khẳng định missing credentials không bị gán nhầm `invalid_token`:

~~~java
@Test
void missingTokenDoesNotReturnInvalidTokenError()
        throws Exception {

    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            allOf(
                startsWith("Bearer"),
                not(containsString("error="))
            )
        ));
}
~~~

Imports static:

~~~java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Imports thường dùng:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
~~~

### 7.1. Kiểm tra public endpoint không yêu cầu token

~~~java
@Test
void publicEndpointDoesNotRequireToken() throws Exception {
    mvc.perform(get("/api/public/health"))
        .andExpect(status().isOk());
}
~~~

Endpoint public không bị từ chối chỉ vì không có Bearer token. Nếu client gửi Bearer token malformed, Bearer filter vẫn có thể xử lý credential đã gửi và trả lỗi authentication trước khi authorization tới controller. `permitAll()` không phải lệnh bỏ qua việc xử lý Bearer header.

### 7.2. Kiểm tra sai authentication scheme

~~~java
@Test
void basicSchemeIsNotAcceptedAsBearerAuthentication()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Basic dXNlcjpwYXNz"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ))
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            not(containsString("error="))
        ));
}
~~~

Test này giả định SecurityFilterChain chỉ cấu hình OAuth2 Resource Server Bearer, không bật HTTP Basic song song.

## 8. Test Bearer header sai cú pháp

### 8.1. Token chứa ký tự không được resolver chấp nhận

~~~java
@Test
void malformedBearerHeaderReturnsInvalidToken()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer bad\"token"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

Trong implementation mặc định hiện hành, `DefaultBearerTokenResolver` dùng grammar cho bearer token. Header đã bắt đầu bằng Bearer nhưng token chứa dấu nháy kép không khớp grammar, nên resolver tạo `invalid_token`.

Không assert nguyên văn toàn bộ `error_description`; nó có thể thay đổi giữa version hoặc implementation.

### 8.2. Bearer scheme không có token

~~~java
@Test
void bearerSchemeWithoutTokenIsRejected()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

Với `DefaultBearerTokenResolver` hiện hành, header bắt đầu bằng Bearer nhưng không khớp cú pháp `Bearer <token>` được xem là malformed Bearer credential. Đây là một chi tiết implementation của Spring; hãy xác nhận lại nếu thay resolver hoặc nâng version.

### 8.3. Không nhầm token syntax hợp lệ với token hợp lệ về bảo mật

Một token có thể là chuỗi hợp lệ theo grammar bearer nhưng vẫn không phải JWT hợp lệ:

~~~http
Authorization: Bearer not-a-jwt
~~~

Resolver có thể trích xuất `not-a-jwt`, sau đó `JwtDecoder` thất bại khi parse. Cả hai trường hợp malformed header và invalid JWT đều có thể dẫn tới:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nhưng test ở tầng khác nhau:

- Header malformed: decoder chưa được gọi.
- Token syntax hợp lệ nhưng JWT invalid: decoder được gọi và ném lỗi.

## 9. Test JWT không parse/verify được

Nếu dùng decoder thật, gửi token có grammar bearer hợp lệ nhưng không phải compact JWT:

~~~java
@Test
void bearerValueThatIsNotJwtReturnsInvalidToken()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer not-a-jwt"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

Để test các lý do invalid khác, dùng token đã ký bằng test key hoặc decoder stub theo từng tình huống:

| Test token | Kết quả mong đợi |
|---|---|
| JWT malformed payload | 401 `invalid_token` |
| JWT signature sai | 401 `invalid_token` |
| `alg=none` khi không được cho phép | 401 `invalid_token` |
| `iss` sai | 401 `invalid_token` |
| `aud` sai | 401 `invalid_token` |
| `exp` đã qua | 401 `invalid_token` |
| `nbf` ở tương lai ngoài clock skew | 401 `invalid_token` |
| Token hợp lệ | Authentication thành công, tiếp tục authorization |

Không cần một Authorization Server production để test mọi lỗi JWT. Có thể dùng RSA test key, public key test và decoder thật; nếu chỉ test mapping exception/status thì dùng decoder stub, nhưng phải ghi rõ test đó không chứng minh chữ ký mật mã.

### 9.1. Test decoder được gọi hay không

Nếu muốn phân biệt lỗi xảy ra ở resolver hay decoder, có thể dùng mock `JwtDecoder`:

~~~java
@MockitoBean
JwtDecoder jwtDecoder;
~~~

Với Spring Framework hiện đại có `@MockitoBean`; một số dự án Spring Boot cũ dùng `@MockBean`.

Test malformed header:

~~~java
@Test
void malformedHeaderIsRejectedBeforeJwtDecoder()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer bad\"token"
            ))
        .andExpect(status().isUnauthorized());

    verifyNoInteractions(jwtDecoder);
}
~~~

Test token có grammar hợp lệ nhưng decoder báo invalid:

~~~java
@Test
void invalidJwtValueReachesDecoder() throws Exception {
    given(jwtDecoder.decode("not-a-jwt"))
        .willThrow(new BadJwtException("Malformed JWT"));

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer not-a-jwt"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));

    verify(jwtDecoder).decode("not-a-jwt");
}
~~~

`@MockitoBean`/`@MockBean` thay decoder trong test context, vì vậy test này kiểm tra filter/provider wiring và error translation. Nó không xác minh JWS signature thực.

## 10. Test `invalid_request` khi client truyền token sai cách

### 10.1. Query parameter và form body mặc định bị tắt

`DefaultBearerTokenResolver` mặc định:

~~~java
DefaultBearerTokenResolver resolver =
    new DefaultBearerTokenResolver();

resolver.setAllowUriQueryParameter(false);
resolver.setAllowFormEncodedBodyParameter(false);
~~~

Hai giá trị mặc định là `false`; không cần gọi setter trong production nếu muốn giữ mặc định.

Request chỉ có query token:

~~~http
GET /api/orders?access_token=query-token HTTP/1.1
Host: api.example.com
~~~

Với resolver mặc định, query token bị bỏ qua. Endpoint private sẽ xử lý như không có Bearer credentials và trả 401 challenge không có `invalid_token`.

Điều này khác với request gửi header Bearer malformed.

### 10.2. Bật query parameter trong một test cấu hình riêng

Để kiểm tra tình huống gửi token qua hai phương thức, cấu hình resolver test:

~~~java
@Bean
BearerTokenResolver testBearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    resolver.setAllowUriQueryParameter(true);

    return resolver;
}
~~~

Gắn resolver vào Resource Server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(testBearerTokenResolver)
    .jwt(Customizer.withDefaults())
)
~~~

Test:

~~~java
@Test
void tokenInHeaderAndQueryParameterReturnsInvalidRequest()
        throws Exception {

    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer header-token"
            )
            .param("access_token", "query-token"))
        .andExpect(status().isBadRequest())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_request\"")
        ));
}
~~~

Resolver phát hiện hai token sources và từ chối trước khi decoder chạy.

**Không bật query parameter token trong production chỉ để test này pass.** Query token dễ bị lộ qua URL logs, browser history, analytics, proxy và monitoring.

### 10.3. Token parameter rỗng hoặc lặp

Khi query parameter support được bật, các trường hợp như:

~~~text
?access_token=
?access_token=one&access_token=two
~~~

có thể được resolver phân loại là `invalid_request`.

Tương tự, nếu form body support được bật và request truyền token trong header lẫn form body, resolver có thể phát hiện nhiều token methods và từ chối.

### 10.4. Bảng phân biệt `invalid_request` và `invalid_token` trong Spring

| Request | Resolver behavior thường gặp | Status/error |
|---|---|---|
| Không có Authorization | Không tìm thấy token | 401, challenge Bearer không error |
| `Authorization: Basic ...` | Không phải Bearer | 401, challenge Bearer không error |
| `Authorization: Bearer bad"token` | Bearer header malformed | 401 `invalid_token` |
| `Authorization: Bearer not-a-jwt` | Trích xuất token, decoder không parse được | 401 `invalid_token` |
| Header + query token khi query support bật | Nhiều token sources | 400 `invalid_request` |
| Header + form token khi form support bật | Nhiều token sources | 400 `invalid_request` |
| Query token khi query support tắt | Bị bỏ qua | 401 nếu route private, challenge không error |
| Token expired | Decoder/introspector từ chối | 401 `invalid_token` |

Điểm dễ nhầm: **malformed Bearer token không tự động có nghĩa `invalid_request`**. RFC định nghĩa `invalid_token` cho access token malformed; Spring mặc định dùng mã này khi Bearer header đã nhận diện nhưng cú pháp token sai.

## 11. Kiểm thử `WWW-Authenticate` với realm tùy chỉnh

Spring Security cung cấp `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`.

Có thể đặt realm:

~~~java
@Bean
BearerTokenAuthenticationEntryPoint bearerAuthenticationEntryPoint() {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    entryPoint.setRealmName("orders-api");

    return entryPoint;
}

@Bean
BearerTokenAccessDeniedHandler bearerAccessDeniedHandler() {
    BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();

    handler.setRealmName("orders-api");

    return handler;
}
~~~

Đăng ký trong Resource Server configurer:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        BearerTokenAuthenticationEntryPoint entryPoint,
        BearerTokenAccessDeniedHandler deniedHandler)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
            .authenticationEntryPoint(entryPoint)
            .accessDeniedHandler(deniedHandler))
        .build();
}
~~~

Khi thiếu token:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Khi token invalid:

~~~http
WWW-Authenticate: Bearer realm="orders-api",
                  error="invalid_token"
~~~

Khi authenticated nhưng bị từ chối:

~~~http
WWW-Authenticate: Bearer realm="orders-api",
                  error="insufficient_scope"
~~~

`BearerTokenAuthenticationEntryPoint` lấy status/error details từ `BearerTokenError` và định dạng challenge theo RFC 6750. `BearerTokenAccessDeniedHandler` xử lý access denial; khi có OAuth `Authentication` hợp lệ, handler dùng `insufficient_scope` theo bearer-token semantics.

### 11.1. Realm là optional

Không bắt buộc phải cấu hình realm. Nếu không set, challenge mặc định có thể chỉ là:

~~~http
WWW-Authenticate: Bearer
~~~

Test không nên phụ thuộc realm nếu ứng dụng không cam kết realm trong API contract.

### 11.2. Đừng so sánh toàn bộ header bằng chuỗi cố định

Một response có thể chứa `realm`, `error`, `error_description`, `error_uri` và các parameter khác. Version Spring Security cũng có thể bổ sung resource metadata nếu được cấu hình.

Test ổn định hơn:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    startsWith("Bearer")
))
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    containsString("error=\"invalid_token\"")
));
~~~

Chỉ assert toàn bộ header nếu ứng dụng thực sự công bố một chuỗi challenge cố định như contract.

## 12. Test token hợp lệ nhưng thiếu scope

Dùng `jwt()` để kiểm tra authorization nhanh:

~~~java
@Test
void validAuthenticationWithoutExportScopeReturns403()
        throws Exception {

    mvc.perform(get("/api/orders/export")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"insufficient_scope\"")
        ));
}
~~~

Test này có mục tiêu cụ thể:

- Spring Security filter chain vẫn chạy nếu MockMvc đã gắn security filters.
- `jwt()` cung cấp một mock JWT authentication.
- Test không gọi decoder hoặc xác minh chữ ký.
- Authorization rule từ chối vì thiếu `SCOPE_orders.export`.
- Bearer access-denied handler trả 403 và challenge phù hợp.

Đây là cách tốt để test quyền HTTP mà không phải ký JWT trong từng test.

### 12.1. So sánh `401` và `403`

| Assertion | Test đang kiểm tra |
|---|---|
| 401, challenge `Bearer`, không error | Không có Bearer credentials |
| 401, `error="invalid_token"` | Token đã gửi nhưng không xác thực được |
| 400, `error="invalid_request"` | Cách truyền token/request sai cấu trúc |
| 403, `error="insufficient_scope"` | OAuth Authentication hợp lệ nhưng không đủ quyền |
| 403 không có Bearer error | Có thể là CSRF hoặc access-denied path khác |

Một test trả 403 chưa chắc là thiếu scope. Nếu CSRF bật, `CsrfFilter` có thể từ chối POST trước khi authorization rule được đánh giá. Khi cần test insufficient scope, dùng một request method an toàn như GET hoặc gửi CSRF token hợp lệ nếu POST bắt buộc.

## 13. Kiểm thử Opaque Token tương tự

Với opaque token, `BearerTokenResolver` vẫn trích xuất token từ header. Khác biệt là provider gọi `OpaqueTokenIntrospector` thay vì `JwtDecoder`.

Cấu hình:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

Các trường hợp:

| Request | Kết quả |
|---|---|
| Không có token | 401 challenge Bearer |
| Bearer header malformed | 401 `invalid_token` |
| Opaque token inactive | 401 `invalid_token` |
| Introspection response active nhưng thiếu authority | 403 `insufficient_scope` |
| Introspection endpoint lỗi | Không cấp authentication; response tùy exception handling |
| Header + query token khi query support bật | 400 `invalid_request` |

Test opaque authorization bằng `opaqueToken()`:

~~~java
@Test
void opaqueAuthenticationWithoutRequiredAuthorityIsForbidden()
        throws Exception {

    mvc.perform(get("/api/orders/export")
            .with(opaqueToken()
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"insufficient_scope\"")
        ));
}
~~~

`opaqueToken()` tạo authentication mẫu. Nó không gọi introspection endpoint. Muốn kiểm tra `active=false`, credentials hoặc timeout, phải gửi `Authorization: Bearer ...` qua filter chain với `OpaqueTokenIntrospector` thật trỏ tới test server/stub.

## 14. Custom AuthenticationEntryPoint: giữ đúng protocol header

Một số API cần JSON body cho client:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A bearer access token is required"
}
~~~

Có thể tạo `AuthenticationEntryPoint` tùy chỉnh, nhưng phải gọi hoặc tái sử dụng logic Bearer challenge:

~~~java
public final class JsonBearerAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.delegate.setRealmName("orders-api");
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        delegate.commence(request, response, exception);

        response.setContentType(MediaType.APPLICATION_JSON_VALUE);

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "code", "AUTHENTICATION_REQUIRED",
                "message", "A bearer access token is required"
            )
        );
    }
}
~~~

Imports cần thiết:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
~~~

Đây là skeleton minh họa. Production implementation cần phân loại exception để body code/message phù hợp cho `invalid_token`, `invalid_request` và missing credentials; đồng thời không ghi đè status do delegate đã đặt. Nếu muốn trả body cho 400/401/403, cần cấu hình cả `AccessDeniedHandler` khi phù hợp.

**Không dùng `@ControllerAdvice` như giải pháp duy nhất** cho lỗi Bearer filter. Authentication failure xảy ra trong Servlet filter chain, trước khi controller được gọi; MVC exception advice thường không bắt các lỗi này như exception từ controller.

## 15. Custom error response không được làm mất WWW-Authenticate

Một lỗi phổ biến là custom entry point chỉ ghi JSON:

~~~java
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
~~~

Nếu không thêm challenge header, client không nhận được thông tin Bearer authentication theo RFC 6750.

Khi custom handler:

- Giữ status phù hợp với `BearerTokenError`.
- Luôn gửi `WWW-Authenticate` trong trường hợp protected resource thiếu hoặc không có access token cho phép.
- Không thêm `invalid_token` khi request chưa gửi token.
- Không trả `invalid_request` cho mọi JWT signature failure.
- Không biến 403 thành 401 chỉ để client tự refresh token.
- Không ghi raw access token hoặc secret vào body/header.
- Không để error description lộ internal hostname, issuer discovery URL hoặc stack trace.

## 16. Test AuthenticationEntryPoint và AccessDeniedHandler riêng

Nếu ứng dụng có custom handlers, nên có tests riêng.

### 16.1. Entry point cho missing credentials

~~~java
@Test
void missingCredentialsUsesBearerEntryPoint() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ));
}
~~~

### 16.2. Entry point cho invalid token

~~~java
@Test
void invalidTokenUsesInvalidTokenChallenge() throws Exception {
    mvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer not-a-jwt"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"invalid_token\"")
        ));
}
~~~

### 16.3. Access denied handler cho authenticated caller

~~~java
@Test
void insufficientAuthorityUsesBearerAccessDeniedHandler()
        throws Exception {

    mvc.perform(get("/api/orders/export")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("error=\"insufficient_scope\"")
        ));
}
~~~

Những test này xác nhận handler được gắn đúng vào chain. Nếu test custom JSON body, assert `Content-Type`, response code và `WWW-Authenticate` riêng biệt.

## 17. Test resolver trực tiếp khi cần cô lập cú pháp

Không phải mọi trường hợp đều cần khởi động Spring context. `DefaultBearerTokenResolver` có thể được test unit bằng `MockHttpServletRequest`.

Ví dụ:

~~~java
class DefaultBearerTokenResolverTests {

    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void noAuthorizationHeaderReturnsNull() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        assertThat(resolver.resolve(request)).isNull();
    }

    @Test
    void validBearerHeaderReturnsToken() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer abc.def-123"
        );

        assertThat(resolver.resolve(request))
            .isEqualTo("abc.def-123");
    }

    @Test
    void malformedBearerHeaderThrowsInvalidToken() {
        MockHttpServletRequest request =
            new MockHttpServletRequest();

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer bad\"token"
        );

        assertThatThrownBy(() -> resolver.resolve(request))
            .isInstanceOf(OAuth2AuthenticationException.class)
            .extracting(ex ->
                ((OAuth2AuthenticationException) ex)
                    .getError().getErrorCode())
            .isEqualTo(BearerTokenErrorCodes.INVALID_TOKEN);
    }
}
~~~

Imports quan trọng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrorCodes;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

Unit test này xác nhận resolver behavior độc lập. Nó không chứng minh `BearerTokenAuthenticationFilter` đã biến exception thành status/header đúng. Đó là lý do cần MockMvc integration tests ở các phần trước.

## 18. Ma trận test tối thiểu nên duy trì

| Test | Request setup | Expected status | Header cần assert |
|---|---|---:|---|
| Public endpoint | Không token | 200 | Không bắt buộc Bearer challenge |
| Private endpoint thiếu token | Không Authorization | 401 | `Bearer`, không có `error` |
| Wrong scheme | `Authorization: Basic ...` | 401 | `Bearer`, không có `error` |
| Bearer header malformed | Token có ký tự không hợp lệ | 401 | `error="invalid_token"` |
| Token string không phải JWT | Bearer value parse thất bại | 401 | `error="invalid_token"` |
| JWT signature sai | JWT ký bằng key khác | 401 | `error="invalid_token"` |
| JWT issuer/audience sai | Claims validation thất bại | 401 | `error="invalid_token"` |
| JWT expired | `exp` quá khứ | 401 | `error="invalid_token"` |
| Token truyền hai nơi | Header + query/form khi support bật | 400 | `error="invalid_request"` |
| Query token khi support tắt | Chỉ có `access_token` query | 401 | `Bearer`, không có `error` |
| Valid token thiếu scope | Mock hoặc signed JWT với authority thiếu | 403 | `error="insufficient_scope"` |
| Opaque inactive | Introspection `active=false` | 401 | `error="invalid_token"` |
| Opaque active thiếu scope | Introspection active, scope thiếu | 403 | `error="insufficient_scope"` |
| CSRF thiếu | POST khi CSRF bật | 403 | Có thể không có Bearer `insufficient_scope` |
| Custom entry point | Missing/invalid token | 401 | Header giữ nguyên + JSON contract |
| Custom access denied handler | Authentication hợp lệ, quyền thiếu | 403 | Header giữ nguyên + body contract |

### 18.1. Kiểm tra side effects

Ngoài status/header, xác nhận controller hoặc service không được gọi khi authentication thất bại:

~~~java
verifyNoInteractions(ordersService);
~~~

Điều này giúp phát hiện những lỗi mà response cuối cùng bị từ chối nhưng business code đã chạy trước đó.

### 18.2. Không overfit `error_description`

Nên assert:

~~~java
containsString("error=\"invalid_token\"")
~~~

thay vì:

~~~java
equalTo(
    "Bearer error=\"invalid_token\", error_description=\"An error occurred while attempting to decode the Jwt: ...\""
)
~~~

Message phụ thuộc decoder, version và exception chain. Chỉ test message nếu API có contract rõ ràng và nội dung không chứa thông tin nhạy cảm.

## 19. Những anti-pattern thường gặp

### 19.1. Mọi 401 đều bị xem là token invalid

Missing token và invalid token có ý nghĩa khác nhau. Client không nên refresh token chỉ vì endpoint trả 401 nếu request chưa gửi credential.

### 19.2. Mọi lỗi Bearer đều trả 400

JWT signature sai là `invalid_token`, thường 401. `invalid_request`/400 dành cho request structure hoặc token transport sai.

### 19.3. Missing token trả `error="invalid_token"`

Không có token thì không thể kết luận token invalid. Challenge chỉ nên cho biết Bearer scheme được hỗ trợ.

### 19.4. Chỉ assert status code

Hai response đều 401 nhưng một response có `invalid_token`, response kia không có error. Client xử lý khác nhau; test phải assert header.

### 19.5. Test `jwt()` để kiểm tra token malformed

`jwt()` tạo mock authentication. Nó không gọi Bearer resolver hoặc decoder. Dùng Bearer header thật cho test authentication failure.

### 19.6. Test `opaqueToken()` để kiểm tra `active=false`

`opaqueToken()` tạo authentication mẫu. Nó không gọi introspection endpoint. Dùng `Authorization: Bearer ...` qua filter chain và introspector thật/stub.

### 19.7. Tắt filters để test 401/403

`@AutoConfigureMockMvc(addFilters = false)` bỏ qua security filters. Kết quả test không còn chứng minh behavior Resource Server.

### 19.8. Dùng `@ControllerAdvice` thay entry point

Lỗi từ `BearerTokenAuthenticationFilter` xảy ra trước MVC controller. Hãy cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` cho filter chain.

### 19.9. Đưa raw token vào `error_description`

Response header có thể được client, proxy hoặc monitoring ghi lại. Không phản hồi raw token, payload đầy đủ hoặc thông tin nhạy cảm.

### 19.10. Bật query token transport không có lý do

Token trong URL có nguy cơ xuất hiện trong access logs, browser history, analytics và referrer. Giữ default header transport trừ khi có yêu cầu legacy cụ thể.

### 19.11. Xem mọi 403 là insufficient scope

CSRF, tenant ACL, ownership hoặc custom policy cũng có thể tạo 403. Xác định handler/filter gây từ chối trước khi kết luận scope thiếu.

### 19.12. Hardcode toàn bộ WWW-Authenticate header vào test

Realm, `error_description`, `error_uri` và metadata parameters có thể thay đổi. Assert scheme và error code quan trọng theo contract.

## 20. Debug khi response khác mong đợi

### Trường hợp A: Không token nhưng server trả 200

Kiểm tra:

- Route có `permitAll()` không?
- Request có khớp `SecurityFilterChain` nào không?
- Có fallback chain không?
- MockMvc có đang dùng `addFilters=false` không?
- Có gọi `.with(jwt())`, `.with(user())` hoặc `@WithMockUser` trong test không?
- Có security test configuration thay chain production không?

### Trường hợp B: Không token nhưng response 401 không có WWW-Authenticate

Kiểm tra:

- Chain có dùng OAuth2 Resource Server không?
- `AuthenticationEntryPoint` có bị custom thay thế không?
- Custom entry point có ghi header không?
- Có proxy/gateway xóa response header không?
- Test có kiểm tra đúng response của filter chain hay response do một layer khác tạo?

### Trường hợp C: Token malformed trả 400

Kiểm tra:

- Resolver đang dùng có phải `DefaultBearerTokenResolver` không?
- Request có truyền token ở nhiều nơi không?
- Query/form token support có được bật không?
- Có custom `BearerTokenResolver` phân loại lỗi khác không?
- Exception có thực sự là `BearerTokenErrorCodes.INVALID_REQUEST` không?

Header Bearer sai grammar trong implementation mặc định hiện hành thường map thành `invalid_token`/401; request dùng nhiều token sources có thể map `invalid_request`/400.

### Trường hợp D: Token invalid nhưng response 403

Kiểm tra:

- Decoder có thực sự được gọi không?
- Test có dùng `.with(jwt())` khiến decoder bị bỏ qua không?
- Principal đã được set bởi session/other authentication mechanism không?
- Token validation có bị bỏ qua ở chain đang chạy không?
- Lỗi thực tế có phải authorization/CSRF thay vì authentication không?

### Trường hợp E: Thiếu scope nhưng response 401

Kiểm tra:

- Authentication có thành công không?
- Converter có map scope đúng prefix `SCOPE_` không?
- `AuthenticationEntryPoint` có được gọi do decoder/issuer/audience failure không?
- `AuthorizationManager` có ném lỗi authentication thay vì access denied không?
- Có custom handler thay status không?

## 21. Bảo mật và vận hành response header

### 21.1. Không để error message tiết lộ nội bộ

`error_description` dành cho developer. Không đưa vào đó:

- Raw JWT hoặc opaque token.
- Private signing key, client secret.
- Nội dung đầy đủ của claims nhạy cảm.
- Internal hostnames hoặc đường dẫn mạng.
- Stack trace.
- Database errors hoặc tên bảng.
- Chi tiết tenant/customer không liên quan.

Có thể log nguyên nhân chi tiết nội bộ theo policy, nhưng log phải redact `Authorization` header và không ghi raw token.

### 21.2. `WWW-Authenticate` cần được giữ qua proxy

Nếu API nằm sau reverse proxy/API gateway, kiểm tra proxy không xóa header:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

Client cần header này để phân biệt missing credentials, invalid token và insufficient privileges. Nếu browser SPA cần đọc header qua CORS, có thể cần expose:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

CORS exposure chỉ cho phép JavaScript đọc header; nó không thay authentication.

### 21.3. Header có thể chứa nhiều challenges

HTTP cho phép server quảng bá nhiều authentication schemes. Không giả định `WWW-Authenticate` luôn chỉ có một chuỗi Bearer nếu ứng dụng kết hợp Basic, Negotiate hoặc cơ chế khác.

Trong test, hãy assert challenge Bearer hiện diện và chứa error code cần thiết, thay vì giả định toàn bộ header là một giá trị cố định.

## 22. Câu hỏi tự kiểm tra

**1.** Request vào endpoint private không có Bearer token nên trả gì?

> Thường là 401 với `WWW-Authenticate: Bearer`; theo RFC 6750, không nên kèm error code khi thiếu authentication information.

**2.** Token hết hạn dùng error code nào?

> `invalid_token`, thường trả 401.

**3.** Bearer header sai grammar có nhất thiết trả `invalid_request` không?

> Không. Spring Security `DefaultBearerTokenResolver` hiện hành phân loại Bearer header malformed thành `invalid_token`/401.

**4.** `invalid_request` thường dùng cho trường hợp nào?

> Request sai cấu trúc hoặc truyền token bằng nhiều phương thức, tham số token lặp/rỗng khi transport tương ứng được bật.

**5.** `insufficient_scope` có status nào?

> 403 Forbidden.

**6.** Missing token và invalid token khác nhau thế nào?

> Missing token nghĩa là chưa có credential để kiểm tra; invalid token nghĩa là client đã gửi credential nhưng token không hợp lệ.

**7.** `WWW-Authenticate` là response body hay response header?

> Response header theo HTTP authentication framework.

**8.** `realm` có bắt buộc không?

> Không. Đây là một authentication challenge parameter optional.

**9.** `error_description` có bắt buộc không?

> Không. Nó optional và dành cho developer, không nên chứa thông tin nhạy cảm.

**10.** Spring class nào tạo Bearer challenge cho authentication failure?

> `BearerTokenAuthenticationEntryPoint`.

**11.** Spring class nào xử lý access denied cho OAuth Bearer authentication?

> `BearerTokenAccessDeniedHandler`.

**12.** `.with(jwt())` có kiểm tra Bearer header parser không?

> Không. Nó tạo mock JWT authentication để kiểm tra authorization.

**13.** Muốn kiểm tra token malformed qua filter chain cần làm gì?

> Gửi `Authorization: Bearer ...` trực tiếp qua MockMvc, không dùng `.with(jwt())`.

**14.** Query token có được `DefaultBearerTokenResolver` đọc mặc định không?

> Không. Query và form body token transports mặc định bị tắt.

**15.** Có nên bật token trong query string cho API mới không?

> Không nên. URL có thể bị ghi vào logs, browser history, proxy và monitoring.

**16.** Một response 403 có luôn nghĩa thiếu scope không?

> Không. Có thể do CSRF, role, tenant membership, ownership hoặc business policy.

**17.** Vì sao test phải assert `WWW-Authenticate` cùng status?

> Vì status không đủ để phân biệt missing credentials, invalid token và insufficient scope.

**18.** Vì sao custom `AuthenticationEntryPoint` phải giữ Bearer challenge?

> Vì client cần protocol signal để biết server yêu cầu Bearer authentication và hiểu lỗi credential.

## 23. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer request syntax, `WWW-Authenticate`, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer filter, authentication entry point và access denied flow.
- [Spring Security — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): token extraction và custom `BearerTokenResolver`.
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): chuyển `BearerTokenError` thành HTTP status và `WWW-Authenticate`.
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): RFC 6750 access-denied response.
- [Spring Security — DefaultBearerTokenResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): đọc Authorization header, form/query parameters và syntax validation.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()` và `opaqueToken()` test helpers.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `springSecurity()` và `FilterChainProxy`.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers, authorities và `denyAll`.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): `webAppContextSetup` và MVC test support.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` và `@AutoConfigureMockMvc`.

**Kết luận:** Khi kiểm thử Spring Security Resource Server, hãy tách rõ **không có token**, **Bearer header/token sai**, **request truyền token sai cách** và **token hợp lệ nhưng thiếu quyền**. RFC 6750 quy định challenge `WWW-Authenticate` là tín hiệu giao thức quan trọng: missing credentials thường là 401 không kèm error; `invalid_token` là 401; `invalid_request` thường là 400; `insufficient_scope` là 403. Dùng MockMvc với `FilterChainProxy` thật để xác nhận status/header, và dùng request Bearer thực khi cần kiểm tra resolver/decoder; `.with(jwt())` chỉ phù hợp để kiểm tra authorization với authentication giả lập.
