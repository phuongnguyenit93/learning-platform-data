# Tùy chỉnh token resolver mà vẫn giữ kiểm tra đầu vào thống nhất

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một HTTP request có thể mang nhiều loại credential: **Bearer access token**, HTTP Basic, API key, session cookie, client certificate hoặc credential do reverse proxy chuyển tiếp. Khi ứng dụng bắt đầu hỗ trợ **nhiều cơ chế xác thực**, việc “tìm access token ở đâu” dễ trở thành một điểm yếu: hai nơi truyền token có thể mâu thuẫn, một credential không hợp lệ bị bỏ qua để thử cơ chế yếu hơn, hoặc một custom resolver vô tình bỏ qua những kiểm tra cú pháp mà Spring Security vốn thực hiện.

Bài học tập trung vào **tùy chỉnh token resolver** nhưng giữ **một hợp đồng kiểm tra đầu vào nhất quán**. Trọng tâm là `BearerTokenResolver` và `DefaultBearerTokenResolver` ở **Servlet stack**; với **Spring WebFlux**, vai trò tương ứng thường được thực hiện qua `ServerAuthenticationConverter` và `ServerBearerTokenAuthenticationConverter`.

Một thiết kế tốt có ba tầng độc lập:

1. **Credential resolution:** Có Bearer token không? Được gửi bằng phương thức nào? Có nhiều giá trị, mâu thuẫn, sai cú pháp hoặc bị cấm không?
2. **Token authentication:** Token đã trích ra có chữ ký, issuer, audience, thời hạn đúng, hoặc có `active=true` khi introspect không?
3. **Authorization:** Token hợp lệ có scope/quyền đối với endpoint, tenant và tài nguyên cụ thể không?

**Nguyên tắc xuyên suốt:** tùy chỉnh nơi lấy token **không được** biến thành tùy chỉnh cách tin token; tất cả đường nhận credential hợp lệ phải đi qua **cùng chính sách nhận đầu vào** và **cùng cơ chế xác thực bắt buộc**.

> **Ví dụ trong bài:** Orders API chạy Spring Boot 3.x / Spring Security 6.x, nhận access token theo `Authorization: Bearer ...`, dùng JWT do issuer `https://login.example.com` ký. Một số endpoint legacy có thể dùng HTTP Basic hoặc API key theo chính sách riêng. Cấu hình và code minh họa dành cho các phiên bản Spring Security có API tương ứng; cần đối chiếu Javadoc của phiên bản thực tế trước khi tích hợp.

## 1. Vì sao vấn đề xuất hiện khi có nhiều cơ chế xác thực?

Với một API chỉ nhận Bearer token:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Luồng tương đối rõ:

```text
Authorization header
      |
      v
BearerTokenResolver
      |
      v
BearerTokenAuthenticationFilter
      |
      v
AuthenticationManager
      |
      v
JwtDecoder hoặc OpaqueTokenIntrospector
      |
      v
Authentication + authorities
      |
      v
Authorization + business policy
```

Nhưng khi hỗ trợ thêm HTTP Basic, API key hoặc proxy token, các câu hỏi xuất hiện:

- Nếu client gửi **Bearer sai cú pháp** và **API key đúng**, API nên từ chối hay bỏ qua Bearer để xác thực bằng API key?
- Nếu hai header `Authorization` xuất hiện, chọn header thứ nhất hay thứ hai?
- Nếu Bearer token có trong **header lẫn query parameter**, token nào là nguồn chính?
- Nếu proxy gắn header `X-Forwarded-Access-Token`, backend có tin header đó từ client ngoài Internet không?
- Nếu một token vừa có dạng JWT vừa được AS cho phép introspect, có được fallback từ JWT validation thất bại sang opaque introspection không?
- Nếu một endpoint có thể được gọi bằng cookie hoặc Bearer, quy tắc CSRF, session, lỗi 401/403 và credential precedence được thiết kế thế nào?

**Không được trả lời các câu hỏi đó bằng một loạt `if/else` tùy hứng trong resolver.** Cần viết rõ **credential contract** và gắn nó vào security chain, resolver, manager, gateway và các bài test.

## 2. Token resolver làm gì — và không làm gì?

Trong Servlet stack, interface:

```java
package org.springframework.security.oauth2.server.resource.web;

public interface BearerTokenResolver {
    String resolve(HttpServletRequest request);
}
```

`resolve(...)` được dùng để lấy raw bearer token từ request. Về mặt ngữ nghĩa:

- **Trả về token string** nếu request có một Bearer credential phù hợp chính sách.
- **Trả `null`** khi không tìm thấy Bearer credential để xử lý.
- **Ném `OAuth2AuthenticationException`** cho request Bearer sai hoặc không hợp lệ ở tầng input, theo cách Spring Security có thể chuyển thành Bearer error.

Resolver **không** tự xác minh chữ ký JWT, không gọi introspection để kiểm tra `active` và không tự xác định scope/ownership.

### 2.1. Các thành phần liên quan

| Thành phần | Trách nhiệm |
|---|---|
| `BearerTokenResolver` | Tìm và trích raw Bearer credential từ request Servlet |
| `DefaultBearerTokenResolver` | Thực hiện quy tắc Bearer extraction thông thường |
| `BearerTokenAuthenticationFilter` | Gọi resolver và kích hoạt authentication |
| `BearerTokenAuthenticationToken` | Mang raw token như một authentication request chưa được xác minh |
| `AuthenticationManager` | Chọn authentication provider |
| `JwtAuthenticationProvider` / `JwtDecoder` | Xác minh JWT signature/claims |
| `OpaqueTokenAuthenticationProvider` / `OpaqueTokenIntrospector` | Xác thực opaque token qua introspection |
| `BearerTokenAuthenticationEntryPoint` | Tạo phản hồi/challenge lỗi Bearer |
| `BearerTokenAccessDeniedHandler` | Xử lý thiếu quyền sau xác thực |
| `SecurityFilterChain` | Xác định những cơ chế và luật authz áp dụng cho URL |
| Domain authorization | Kiểm tra tenant, ownership, trạng thái nghiệp vụ |

Trong WebFlux, các vai trò tương ứng liên quan tới `ServerAuthenticationConverter`, `ServerBearerTokenAuthenticationConverter`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager` và `SecurityWebFilterChain`.

### 2.2. Không nhầm extraction với verification

Đoạn này chỉ trích chuỗi:

```java
String token = bearerTokenResolver.resolve(request);
```

Kể cả khi `token` trông như:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0...
```

nó vẫn **chưa đáng tin**. Chỉ khi `JwtDecoder` xác minh chữ ký, issuer, audience, thời hạn, loại access token và các validator liên quan thì Resource Server mới được dùng claims để tạo authentication và phân quyền.

Một anti-pattern nghiêm trọng:

```java
// CỐ Ý SAI: quyết định quyền ngay sau khi đọc payload chưa verified.
String rawToken = resolver.resolve(request);
String scope = parseUnverifiedJwtPayload(rawToken).get("scope");
if (scope.contains("orders.admin")) {
    grantAdminAccess();
}
```

**Resolver không được biến dữ liệu client gửi thành identity hoặc authority trước khi có xác minh.**

## 3. RFC 6750: hợp đồng chuẩn để nhận Bearer token

**RFC 6750** mô tả cách sử dụng OAuth 2.0 Bearer token với HTTP. Phương thức được khuyến nghị là **Authorization request header**:

```http
Authorization: Bearer ACCESS_TOKEN
```

Chuẩn cũng mô tả **form-encoded body parameter** và **URI query parameter** trong những điều kiện cụ thể; tuy nhiên mỗi request **không được sử dụng hơn một phương thức truyền token**. Trong triển khai API hiện đại, header thường là lựa chọn an toàn và ổn định nhất.

### 3.1. Các phương thức truyền token

| Phương thức | Ví dụ | Khuyến nghị cho API thông thường |
|---|---|---|
| Authorization header | `Authorization: Bearer abc` | **Ưu tiên và dùng mặc định** |
| Form body | `access_token=abc` trong `application/x-www-form-urlencoded` | Chỉ khi hợp đồng thực sự cần và đáp ứng điều kiện chuẩn |
| URI query | `GET /api?access_token=abc` | **Tránh** vì rủi ro URL logging/history/cache |
| Cookie | `Cookie: access_token=abc` | Không tự nhận làm Bearer; cần mô hình browser/CSRF riêng |
| Custom header | `X-Internal-Access-Token: abc` | Chỉ khi có gateway trust boundary và quy tắc rõ |
| WebSocket subprotocol/other | Theo giao thức riêng | Không tự suy rộng resolver HTTP mặc định |

### 3.2. Tại sao query token nguy hiểm?

Ví dụ:

```http
GET /api/orders/42?access_token=secret-token HTTP/1.1
```

Token có thể bị đưa vào:

- Browser history và bookmark.
- Reverse proxy/CDN access logs.
- Server request logs.
- Monitoring/tracing URL attributes.
- Link được copy/chia sẻ.
- Referer hoặc các hệ thống phân tích URL khi cấu hình không an toàn.
- Cache keys và audit records.

Do đó **không bật nhận Bearer từ query chỉ để “hỗ trợ thêm client”** nếu ứng dụng không có một ngoại lệ đã được phân tích rủi ro.

### 3.3. Một credential, một nguồn, một ý nghĩa

Chính sách dễ bảo vệ nhất:

```text
Bearer accepted source = Authorization header only

If missing:
    leave request unauthenticated
If malformed/duplicated:
    reject with Bearer input error
If syntactically acceptable:
    pass token to standard authentication manager
```

Không dùng tham số query để cứu một request có Bearer header malformed. Không dùng API key để hợp thức hóa một request Bearer không hợp lệ nếu hợp đồng không cho phép.

## 4. DefaultBearerTokenResolver và hành vi cơ bản

Spring Security cung cấp `DefaultBearerTokenResolver` cho Servlet. Theo mặc định, nó nhận Bearer token qua **Authorization header**; các phương thức form body và URI query không được mở chỉ vì client gửi chúng.

Ví dụ:

```java
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);

    return resolver;
}
```

Ở đây hai setter được ghi rõ để chính sách người đọc dễ thấy. Giá trị mặc định cụ thể và API được bảo đảm theo Javadoc của phiên bản dùng trong dự án; không tự giả định những setter đó sẽ làm validation cryptographic.

### 4.1. Những API cấu hình hữu ích

| API | Mục đích |
|---|---|
| `setAllowFormEncodedBodyParameter(boolean)` | Cho phép/không cho phép lấy token từ form body |
| `setAllowUriQueryParameter(boolean)` | Cho phép/không cho phép lấy token từ query parameter |
| `setBearerTokenHeaderName(String)` | Đổi tên header được dùng để nhận Bearer token trong mô hình có proxy/gateway kiểm soát |

**Chú ý:** `setBearerTokenHeaderName` thay đổi **header nguồn**, không phải một giải pháp tự động xác thực độ tin cậy của gateway hoặc chấp nhận nhiều header theo thứ tự ưu tiên.

### 4.2. Những điều không nên viết lại bằng tay

Thay vì tự làm:

```java
// KHÔNG NÊN: có thể bỏ qua cú pháp sai, duplicate và scheme.
String authorization = request.getHeader("Authorization");
if (authorization != null) {
    return authorization.substring(7).trim();
}
return null;
```

nên tận dụng `DefaultBearerTokenResolver` để xử lý Bearer syntax theo hành vi được Spring Security quản lý, rồi **bọc thêm những ràng buộc đặc thù** nếu cần.

Đoạn tự cắt chuỗi phía trên có lỗi tiềm ẩn:

- Header ngắn hơn 7 ký tự gây exception khác hợp đồng.
- `Basic ...` bị cắt thành token giả.
- `Bearer` không có giá trị nhưng lại có thể bị xử lý tùy ý.
- Token chứa khoảng trắng/ký tự không hợp lệ bị `trim()` che mất sai phạm.
- Không xử lý duplicate Authorization headers.
- Không xét case-insensitive auth scheme hay định dạng RFC 6750 đúng.
- Không giữ semantics phân biệt credential thiếu với credential malformed.

**Không dùng `trim()`, `split(" ")` rồi tự cho qua theo cảm tính.** Mỗi chuẩn auth scheme có grammar riêng.

## 5. Kiểm tra đầu vào thống nhất có nghĩa là gì?

Với một API nhận nhiều credential, “thống nhất” không có nghĩa mọi cơ chế auth phải dùng cùng parser. Nó nghĩa là **mỗi cơ chế có hợp đồng rõ**, mọi đường đi đến cùng cơ chế đều chịu **các quy tắc giống nhau**:

1. Nguồn nào được chấp nhận?
2. Credential có được gửi đồng thời từ nhiều nguồn không?
3. Header có được lặp lại không?
4. Cú pháp scheme và token có hợp lệ không?
5. Khi sai, trả lỗi hay thử phương án khác?
6. Ai thực hiện xác minh cryptographic/introspection?
7. Những thuộc tính nào trở thành principal/authority?
8. Authentication thất bại có được phép chạy cơ chế yếu hơn không?
9. Status 401/403 và `WWW-Authenticate` nào được trả?
10. Logger, gateway, proxy và test có cùng hiểu một credential policy không?

### 5.1. Một bảng phân loại đầu vào

| Request | Tình huống | Hành vi Bearer-only API mong đợi |
|---|---|---|
| Không `Authorization` | Không có credential | Chưa authenticated; endpoint bảo vệ trả 401 |
| `Authorization: Bearer abc` | Có một token đúng cú pháp | Chuyển sang decoder/introspector |
| `Authorization: bearer abc` | Scheme không phân biệt hoa/thường theo HTTP | Dùng hành vi resolver chuẩn |
| `Authorization: Bearer` | Thiếu token | Lỗi cú pháp, không tự nhận token rỗng |
| `Authorization: Bearer a b` | Chứa whitespace không hợp lệ | Từ chối, không trim/split để sửa |
| `Authorization: Basic ...` | Credential của cơ chế khác | Bearer resolver không coi là Bearer; chain quyết định |
| Hai dòng `Authorization` | Mơ hồ | **Từ chối theo strict policy** |
| Bearer header + token trong query | Nhiều nguồn | Không chấp nhận query; có thể từ chối rõ theo strict policy |
| `?access_token=abc` không header | Query-only credential | Không coi là Bearer với header-only policy |
| `X-API-Key` ở bearer-only route | Credential ngoài hợp đồng | Không được dùng để bỏ qua Bearer |
| Token đúng cú pháp nhưng sai chữ ký | Input extraction thành công; authn thất bại | **401 invalid_token**, không fallback |
| Token hợp lệ thiếu `orders.read` | Authentication thành công; authz thất bại | **403** theo hợp đồng |

Một số status cho malformed input có thể là `400 invalid_request` thay vì 401 tùy trường hợp RFC 6750 và Spring Security handler. **Điều không đổi** là request không được xác thực thành công khi credential mơ hồ/sai.

### 5.2. Vì sao phải phân biệt `null` và exception?

Đây là một trong những quy tắc quan trọng nhất khi tùy chỉnh resolver:

```text
resolve(...) == null
    -> Không có Bearer credential để resolver xử lý

resolve(...) throws OAuth2AuthenticationException
    -> Request có lỗi Bearer input; phải báo lỗi

resolve(...) == "token"
    -> Có chuỗi candidate; còn phải authenticate
```

Nếu custom resolver trả `null` khi thấy `Authorization: Bearer ???` sai cú pháp, filter có thể cho các cơ chế authentication khác tiếp tục. Như vậy lỗi input Bearer bị **downgrade** thành “không có Bearer”.

**Không chuyển malformed Bearer thành `null` để được thử API key hoặc cookie.** Nếu muốn hỗ trợ nhiều credential, phải có chính sách explicit cho cạnh tranh và lỗi của từng cơ chế.

## 6. Ví dụ Servlet: wrapper giữ parser chuẩn và từ chối ambiguity

Một cách tùy chỉnh bảo thủ là **giữ `DefaultBearerTokenResolver` làm delegate** và thêm kiểm tra **duplicate Authorization** cùng **query parameter bị cấm** ở trước.

### 6.1. Class StrictHeaderBearerTokenResolver

```java
package com.example.orders.security;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class StrictHeaderBearerTokenResolver
        implements BearerTokenResolver {

    private final DefaultBearerTokenResolver delegate;

    public StrictHeaderBearerTokenResolver() {
        this.delegate = new DefaultBearerTokenResolver();
        this.delegate.setAllowFormEncodedBodyParameter(false);
        this.delegate.setAllowUriQueryParameter(false);
    }

    @Override
    public String resolve(HttpServletRequest request) {
        rejectRepeatedAuthorizationHeaders(request);
        rejectBearerInQuery(request.getQueryString());

        // Spring Security tiếp tục chịu trách nhiệm parse Bearer grammar.
        return delegate.resolve(request);
    }

    private static void rejectRepeatedAuthorizationHeaders(
            HttpServletRequest request) {

        Enumeration<String> values =
            request.getHeaders(HttpHeaders.AUTHORIZATION);

        int count = 0;
        while (values != null && values.hasMoreElements()) {
            values.nextElement();
            if (++count > 1) {
                throw invalidRequest(
                    "Multiple Authorization headers are not allowed"
                );
            }
        }
    }

    private static void rejectBearerInQuery(String rawQuery) {
        if (rawQuery == null || rawQuery.isEmpty()) {
            return;
        }

        for (String pair : rawQuery.split("&", -1)) {
            int equals = pair.indexOf('=');
            String encodedName =
                equals < 0 ? pair : pair.substring(0, equals);

            final String parameterName;
            try {
                parameterName = URLDecoder.decode(
                    encodedName,
                    StandardCharsets.UTF_8
                );
            } catch (IllegalArgumentException ex) {
                throw invalidRequest(
                    "Malformed query parameter encoding"
                );
            }

            if ("access_token".equals(parameterName)) {
                throw invalidRequest(
                    "Bearer token in URI query is not allowed"
                );
            }
        }
    }

    private static OAuth2AuthenticationException invalidRequest(
            String description) {
        return new OAuth2AuthenticationException(
            BearerTokenErrors.invalidRequest(description)
        );
    }
}
```

**Vai trò của wrapper:**

- Nếu có nhiều dòng `Authorization`, reject thay vì để HTTP container/proxy chọn một giá trị bất kỳ.
- Nếu URL chứa `access_token`, reject theo **policy nghiêm ngặt** của API; không khuyến khích token nằm trong URL.
- Nếu không có lỗi bổ sung, dùng **`DefaultBearerTokenResolver`** thực hiện parse Bearer.
- Nếu Bearer token malformed, delegate có thể ném lỗi chuẩn; wrapper **không nuốt exception**.
- Token hợp lệ về **cú pháp** vẫn còn phải qua `JwtDecoder` hoặc `OpaqueTokenIntrospector`.

### 6.2. Giới hạn của lớp wrapper

Đây là một **policy minh họa**, không phải parser URL/security gateway hoàn chỉnh. Việc reject query names bằng `URLDecoder` phù hợp cách form-style query được diễn giải trong ví dụ; môi trường thực cần thống nhất URL decoding giữa proxy, Servlet container và application, giới hạn độ dài/encoding từ edge, và kiểm thử những biến thể percent-encoding.

Ngoài ra:

- Servlet có thể đã bị gateway **gộp** nhiều header thành một dòng trước khi tới backend; wrapper không nhìn thấy thông tin đã bị mất.
- Không nên tự phân tích entire request body chỉ để tìm form `access_token` nếu điều đó khiến input stream bị tiêu thụ trước controller; mặc định delegate **không nhận Bearer từ form**.
- Nếu endpoint thật sự cho phép form body token, cần thiết kế theo RFC 6750, content-type/method, ưu tiên, duplicate sources và test riêng thay vì bật flag toàn API.
- Nếu request có query parameter khác trùng tên sau các bước normalization đặc thù của proxy, cần áp cùng chính sách normalization ở edge và app.
- Nếu API không muốn từ chối một query `access_token` vốn là dữ liệu nghiệp vụ không dùng làm Bearer, phải đặt tên tham số khác rõ ràng; không nên tạo một policy mơ hồ.

### 6.3. Vì sao không tự kiểm tra chữ ký JWT trong resolver?

Resolver cần xử lý nguồn credential. JWT verification là trách nhiệm của `JwtDecoder` và authentication provider. Tự tạo `JwtDecoder` trong `resolve(...)` có thể:

- Xác minh lại token nhiều lần.
- Làm rối exception handling 401/403.
- Dùng decoder/issuer sai khi nhiều tenant.
- Tạo network JWKS discovery khi parse input.
- Đẩy dữ liệu chưa verify vào cache/context.
- Kết hợp extraction và authorization khó kiểm thử.

**Tách trách nhiệm là một biện pháp bảo mật**, không chỉ là thói quen clean code.

## 7. Gắn custom resolver vào Spring Security Resource Server

### 7.1. Dependencies

Ví dụ Gradle Groovy DSL cho Servlet MVC:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cấu hình issuer và audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

`audiences` là property hỗ trợ ở các phiên bản Spring Boot phù hợp; với custom decoder hoặc phiên bản khác, phải gắn audience validator riêng.

### 7.2. SecurityFilterChain Bearer-only

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BearerApiSecurityConfiguration {

    @Bean
    StrictHeaderBearerTokenResolver strictBearerResolver() {
        return new StrictHeaderBearerTokenResolver();
    }

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(
            HttpSecurity http,
            StrictHeaderBearerTokenResolver resolver) throws Exception {

        return http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            .requestCache(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(resolver)
                .jwt(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new BearerTokenAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenAccessDeniedHandler()
                )
            )
            .build();
    }
}
```

**Đọc cấu hình theo thứ tự trách nhiệm:**

1. `securityMatcher` áp chain này lên `/api` và `/api/**`, không tự áp cho mọi đường dẫn.
2. `oauth2ResourceServer` tạo đường xử lý Bearer token.
3. `bearerTokenResolver(resolver)` thay **nguồn/cách trích token**, không thay decoder/manager.
4. `jwt(...)` vẫn bắt buộc xác minh signature, issuer, expiration, audience và validators cấu hình.
5. `hasAuthority("SCOPE_orders.read")` kiểm tra scope sau authentication.
6. `formLogin` và `httpBasic` bị tắt **trong chain Bearer API** để tránh cơ chế không chủ định.
7. `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` giữ lỗi Bearer 401/403.

**CSRF:** đoạn code minh họa chưa tắt CSRF. Nếu API chỉ dùng Bearer header và không nhận cookie/session credentials, có thể thiết kế chính sách CSRF riêng theo threat model; không tự tắt CSRF cho mọi endpoint khi hệ thống còn cookie-based authentication.

### 7.3. Khi dùng opaque token

Thay phần JWT:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .opaqueToken(Customizer.withDefaults())
)
```

Cấu hình thêm `opaquetoken.introspection-uri/client-id/client-secret` của Spring Boot. **Cùng một resolver có thể phục vụ JWT hoặc opaque**, vì nó chỉ trích Bearer token. Cơ chế provider/decoder mới quyết định cách xác thực.

Không tự xác định “chuỗi có dấu chấm thì JWT, không có dấu chấm thì opaque rồi cho qua”. Định dạng có thể hỗ trợ routing theo hợp đồng, nhưng không thay được cryptographic validation/introspection.

## 8. Nhiều cơ chế xác thực: ưu tiên tách theo SecurityFilterChain

Khi một application có cả REST Bearer API và API legacy dùng HTTP Basic, cách dễ hiểu nhất là **phân tách route rõ ràng**:

```text
/api/**           -> Bearer access token
/legacy/**        -> HTTP Basic, chỉ khi còn cần
/web/**           -> Session/OIDC Login nếu có
remaining routes  -> deny hoặc chain phù hợp
```

### 8.1. Ví dụ Basic-only chain cho đường legacy

```java
@Bean
@Order(2)
SecurityFilterChain legacyBasicApi(HttpSecurity http)
        throws Exception {
    return http
        .securityMatcher("/legacy/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .sessionManagement(session ->
            session.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS
            )
        )
        .formLogin(AbstractHttpConfigurer::disable)
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **một chain khác** với bearer chain ở phần trước. Authentication provider/UserDetailsService thực tế cho HTTP Basic phải được cấu hình an toàn; đây không phải chỉ dẫn dùng HTTP Basic cho một API mới nếu OAuth Bearer đã phù hợp.

### 8.2. Fallback cho URL chưa được phân loại

```java
@Bean
@Order(99)
SecurityFilterChain fallbackDenyAll(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
```

Một chain có `securityMatcher` hẹp **không bảo vệ** URL ngoài matcher. Fallback giúp tránh endpoint mới vô tình không nằm trong chain bảo vệ.

Nếu ứng dụng có actuator, OAuth2 login callbacks hoặc web UI, cần cấu hình chain/matcher phù hợp trước fallback; không copy `denyAll` mà quên những endpoint hợp lệ.

### 8.3. Thứ tự @Order quan trọng

Spring Security chọn **chain đầu tiên khớp request**. Nếu web chain có matcher bao trùm trước API chain, request `/api/orders` có thể rơi vào `formLogin` và nhận 302 HTML login thay vì 401 Bearer.

Nguyên tắc:

- Bearer API chain có matcher rõ và order ưu tiên.
- Basic/API-key/web chains có URL scope riêng.
- Fallback chain xử lý phần còn lại.
- Không dựa vào `Accept: application/json` để chọn authentication mechanism.
- Test URL có và không có dấu slash, context path và reverse proxy path rewrites.

## 9. Nếu bắt buộc hỗ trợ nhiều credential trên cùng endpoint

Đôi khi một endpoint phải phục vụ cả client cũ và mới trong giai đoạn migration. Đây là tình huống nhạy cảm vì **credential precedence** trở thành một phần của security contract.

### 9.1. Tránh chính sách “credential nào đúng thì dùng”

Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer EXPIRED_TOKEN
X-API-Key: VALID_LEGACY_KEY
```

Một thiết kế không nên là:

```text
Thử Bearer
  -> lỗi invalid_token
  -> bỏ qua
Thử API key
  -> hợp lệ
  -> cho phép
```

Hậu quả: client đang gửi Bearer credential sai vẫn được coi là đã xác thực bằng cơ chế khác, khó audit và dễ tạo **downgrade/fallback** ngoài dự kiến.

### 9.2. Chính sách rõ ràng hơn

Có thể quy định:

| Credentials trên một request | Hành vi |
|---|---|
| Chỉ Bearer | Xác thực theo Bearer |
| Chỉ API key | Xác thực theo API key khi route/hợp đồng cho phép |
| Không có credential | 401 |
| Bearer sai cú pháp | Từ chối ngay; không fallback |
| Bearer sai chữ ký/expired | Từ chối; không fallback |
| Bearer và API key cùng có | **Từ chối do xung đột credential** |
| Hai Bearer headers | Từ chối |
| Hai API key headers | Từ chối |
| Cookie và Bearer cùng có | Có policy explicit, ưu tiên tách routes hơn |
| Bearer đúng nhưng thiếu scope, API key mạnh hơn | Không fallback sau 403 |

Nếu phải cho phép nhiều cơ chế trên cùng route, cần **một lớp kiểm soát xung đột credential trước các authentication filters** hoặc một single authentication gateway/filter được thiết kế rõ ràng. Không đặt hai filter độc lập rồi hy vọng thứ tự thực thi tự giải quyết mọi trường hợp.

### 9.3. Mâu thuẫn phải được xử lý trước authentication

Nguyên tắc tốt:

```text
Inspect credential sources (bounded, no secret logging)
     |
     +-- 0 credentials -> unauthenticated
     +-- 1 supported scheme -> authenticate with its provider
     +-- >1 conflicting sources -> reject
     +-- malformed scheme -> reject
```

Nếu dùng custom pre-auth filter để kiểm tra conflict, nó chỉ nên **phân loại nguồn**, không tự xác thực token hoặc cấp roles. Phải xử lý error response nhất quán (status/body/`WWW-Authenticate`) và được chèn đúng thứ tự; nếu không, lựa chọn đơn giản hơn vẫn là **tách route**.

## 10. Không để lỗi Bearer rơi sang Basic, API key hoặc session

### 10.1. Phân biệt không có Bearer với Bearer invalid

Ví dụ:

```http
Authorization: Basic BASE64_USER_PASSWORD
```

`DefaultBearerTokenResolver` có thể trả `null` vì đây không phải Bearer credential. Nếu chain hỗ trợ HTTP Basic, Basic filter sẽ quyết định xử lý theo hợp đồng.

Nhưng:

```http
Authorization: Bearer INVALID!! TOKEN
```

là một **lỗi Bearer input**. Custom resolver không được trả `null` chỉ vì muốn request đi qua Basic filter, session cookie hoặc API key filter.

### 10.2. Không fallback sau JWT validation failure

Nếu hệ thống nhận JWT và opaque tokens, một cách nguy hiểm:

```text
Thử xác minh JWT
   |
   +-- signature/issuer/audience sai
   |
   v
Thử introspect raw token ở một endpoint khác
   |
   +-- active=true -> cho qua
```

Điều này có thể tạo **confused deputy** hoặc **downgrade path** nếu hai cơ chế có trust/policy khác nhau. Nếu phải chấp nhận cả JWT và opaque, cần:

- Hợp đồng token classes rõ từ AS.
- Manager/decoder routing được phê duyệt và không dựa vào issuer/JWKS URL do token tự cung cấp.
- Không “thử tất cả Authorization Servers” cho một bearer token.
- Không gửi token cho introspection endpoint ngoài trust boundary.
- Xác minh audience, issuer/resource, scopes, thời hạn và token type trong **từng nhánh**.
- Xem authentication failure là failure, không phải tín hiệu tự mở nhánh yếu hơn.

**Token resolver chỉ chọn nguồn input; quyết định JWT hay opaque thuộc architecture của authentication manager/provider.**

## 11. Custom header từ reverse proxy: rủi ro và cách hạn chế

Trong một số kiến trúc, gateway hoặc service mesh có thể chuyển Bearer token qua header riêng:

```http
X-Internal-Access-Token: ACCESS_TOKEN
```

Nếu backend chấp nhận header đó từ bất kỳ client nào, kẻ tấn công có thể tự tạo header để mạo danh gateway.

### 11.1. Trust boundary phải nằm ngoài header

Một header không thể tự chứng minh:

- Request đến từ gateway được phép.
- Gateway đã xác thực caller.
- Header không bị client tự gửi và proxy chỉ chuyển tiếp.
- Header mang access token đúng audience.
- Header không bị sửa bởi intermediate proxies.

Muốn dùng custom header, cần kết hợp **trusted network/identity boundary** như mTLS giữa gateway và service, inbound firewall/ingress policy, strip/overwrite header tại edge và một cấu hình backend chỉ nhận traffic từ gateway đã xác thực.

**Không dùng** `X-Forwarded-For`, `X-Real-IP` hoặc một custom `X-Gateway-Trusted: true` do caller tự gửi làm bằng chứng duy nhất rằng request đến từ gateway.

### 11.2. Cách dùng setBearerTokenHeaderName

Trong hệ thống đã có trust boundary ở trước backend, có thể cấu hình resolver chỉ đọc header do proxy quản lý:

```java
@Bean
BearerTokenResolver gatewayBearerTokenResolver() {
    DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    // Chỉ dành cho một proxy protocol được bảo vệ rõ ràng.
    resolver.setBearerTokenHeaderName(
        "X-Internal-Access-Token"
    );
    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);
    return resolver;
}
```

**Điều kiện tiên quyết:** header này phải được gateway **strip khỏi request bên ngoài rồi overwrite bằng giá trị do hệ thống quản lý**, đường kết nối gateway–backend được xác thực và backend không nhận direct untrusted traffic. `setBearerTokenHeaderName` chỉ đổi nguồn đọc token, **không kiểm chứng những tiền đề trên**.

Vì dùng resolver chuẩn với header tùy chỉnh, hãy đảm bảo gateway truyền **định dạng Bearer theo yêu cầu của resolver** (không giả định raw token không có `Bearer ` prefix sẽ được chấp nhận). Test tích hợp giữa edge và backend cần xác nhận header value thực tế.

### 11.3. Ưu tiên giữ Authorization: Bearer ở mỗi hop khi có thể

Nếu gateway chỉ làm reverse proxy bình thường và backend vẫn xác minh access token, giải pháp đơn giản thường là **chuyển tiếp `Authorization: Bearer` với chính sách chống lộ secret đúng** thay vì nghĩ ra một header mới.

Custom header nên được dùng khi có một giao thức proxy nội bộ được phê duyệt, không phải cách chữa một client gửi sai Bearer header.

### 11.4. Không bật đồng thời hai header không có conflict rule

Nếu một resolver đọc cả:

```http
Authorization: Bearer TOKEN_A
X-Internal-Access-Token: Bearer TOKEN_B
```

và chọn tùy tiện, client/gateway có thể hiểu khác nhau. Nếu thực sự có hai nguồn, hợp đồng phải xác định:

- Request có được gửi cả hai không?
- Nếu cả hai cùng có, **reject** hay có migration policy cụ thể?
- Header nào chỉ được chấp nhận từ gateway đã được chứng thực?
- Những nguồn nào bắt buộc được strip ở ingress?
- Lỗi được trả ra sao và log/tracing có tránh token không?

Không dùng logic “lấy cái đầu tiên không rỗng” mà thiếu chính sách chống xung đột.

## 12. Nhiều tenant và nhiều issuer: resolver không được mở trust tùy ý

Một Bearer token có thể là JWT chứa:

```json
{
  "iss": "https://id.tenant-a.example",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Nhưng claim `iss` chưa được xác minh. Nếu custom resolver tự đọc `iss` rồi gọi metadata/JWKS từ issuer URL bất kỳ, Resource Server có thể gặp **SSRF và issuer confusion**.

**Thiết kế đúng:**

1. Resolver trích Bearer token theo contract HTTP.
2. Authentication manager resolver (nếu multi-issuer) chỉ chọn trong **trusted issuer allowlist**.
3. Decoder của issuer đã chọn xác minh signature, exact issuer, audience, timestamp, allowed algorithm và token profile.
4. Scope/tenant/business authorization thực hiện sau authentication.
5. Issuer lạ bị từ chối **trước** khi thực hiện discovery hoặc network calls tới host lạ.

Đừng coi claim `iss`, header `kid`, `jku` hoặc URL từ token chưa verify là nguồn cấu hình network.

### 12.1. Vì sao đây là việc của authentication manager, không phải token resolver?

Resolver biết **Bearer token nằm ở đâu**; manager quyết định **token có đáng tin hay không**. Tự gộp hai bước vào resolver khiến hệ thống khó bảo đảm tất cả cơ chế vẫn thực hiện cùng validators.

Trong Spring Security Servlet có thể dùng `JwtIssuerAuthenticationManagerResolver` với trusted issuers, nhưng không thay bằng `JwtDecoders.fromIssuerLocation(unverifiedIssuer)` cho mọi request.

### 12.2. Ngay cả một issuer cũng có nhiều audience

Một JWT có chữ ký đúng của `https://login.example.com` nhưng `aud=billing-api` không nên được Orders API chấp nhận. Custom resolver không được “sửa” audience bằng cách thay thông tin ở payload hoặc bỏ validator để tăng tương thích.

## 13. WebFlux: ServerBearerTokenAuthenticationConverter tương ứng với resolver

Trong **Spring WebFlux**, interface thường sử dụng để chuyển request thành authentication request là:

```java
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
```

Spring Security có `ServerBearerTokenAuthenticationConverter` để đọc Bearer credential và tạo `BearerTokenAuthenticationToken` trong reactive chain.

### 13.1. Không dùng Servlet resolver cho WebFlux

| Servlet | WebFlux |
|---|---|
| `HttpServletRequest` | `ServerWebExchange` |
| `BearerTokenResolver` | `ServerAuthenticationConverter` |
| `DefaultBearerTokenResolver` | `ServerBearerTokenAuthenticationConverter` |
| `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` cho Bearer Resource Server |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

**Không gắn `BearerTokenResolver` Servlet vào `ServerHttpSecurity` và kỳ vọng WebFlux sẽ gọi nó.** Cả kiểu request và authentication pipeline khác nhau.

### 13.2. WebFlux converter mặc định

```java
import org.springframework.security.oauth2.server.resource.web.server
    .ServerBearerTokenAuthenticationConverter;

ServerBearerTokenAuthenticationConverter converter =
    new ServerBearerTokenAuthenticationConverter();

converter.setAllowUriQueryParameter(false);
```

API cấu hình cụ thể tùy phiên bản Spring Security, nhưng nguyên tắc vẫn là **ưu tiên Authorization header, không chủ động mở nguồn query token**.

### 13.3. Wrapper converter kiểm tra một nguồn duy nhất

Một custom converter có thể kiểm tra duplicate headers/query và **ủy quyền parsing cho converter chuẩn**:

```java
package com.example.orders.security;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.server.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.ServerWebExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;

import reactor.core.publisher.Mono;

public final class StrictReactiveBearerConverter
        implements ServerAuthenticationConverter {

    private final ServerBearerTokenAuthenticationConverter delegate =
        new ServerBearerTokenAuthenticationConverter();

    public StrictReactiveBearerConverter() {
        delegate.setAllowUriQueryParameter(false);
    }

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> authorizationValues =
            exchange.getRequest().getHeaders()
                .getOrEmpty(HttpHeaders.AUTHORIZATION);

        if (authorizationValues.size() > 1) {
            return Mono.error(
                new OAuth2AuthenticationException(
                    BearerTokenErrors.invalidRequest(
                        "Multiple Authorization headers"
                    )
                )
            );
        }

        if (exchange.getRequest().getQueryParams()
                .containsKey("access_token")) {
            return Mono.error(
                new OAuth2AuthenticationException(
                    BearerTokenErrors.invalidRequest(
                        "Bearer token in URI query is not allowed"
                    )
                )
            );
        }

        // Không tự parse Bearer grammar, không cấp Authentication.
        return delegate.convert(exchange);
    }
}
```

Lớp này mô tả **cùng chính sách cơ bản** với Servlet wrapper:

- Chỉ một Authorization header.
- Cấm token trong query.
- Converter chuẩn xử lý Bearer syntax.
- Không có credential → publisher rỗng theo hợp đồng converter.
- Credential sai → lỗi, không tự fallback sang một scheme khác.
- Credential nhận được → chỉ là authentication request, vẫn cần manager reactive xác minh.

### 13.4. Gắn converter vào ServerHttpSecurity

Ví dụ trên phiên bản có setter `bearerTokenConverter(...)` ở DSL Resource Server WebFlux:

```java
@Bean
SecurityWebFilterChain apiWebFlux(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(form -> form.disable())
        .httpBasic(basic -> basic.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .bearerTokenConverter(
                new StrictReactiveBearerConverter()
            )
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Đây là **một biến thể WebFlux**, không đặt bên cạnh `SecurityFilterChain` của Servlet trong cùng ứng dụng mà không xác định đúng web application type.

Nếu minor version của Spring Security có tên API khác hoặc cần cấu hình `AuthenticationWebFilter` trực tiếp, đối chiếu Javadoc và giữ nguyên mục tiêu: **strict conversion + reactive authentication manager chuẩn**, không nhân đôi filter Bearer trên cùng chain.

### 13.5. Không `block()` hoặc `subscribe()` bên trong converter

`ServerAuthenticationConverter.convert(...)` trả `Mono<Authentication>`. Không dùng:

```java
Authentication authentication =
    someReactiveDecoder.decode(token).block();
```

bên trong converter để “kiểm tra token trước”. WebFlux cần giữ authentication trong reactive pipeline, tránh chặn event loop, mất Reactor Context và tạo xác minh lặp.

## 14. Nhiều cơ chế trong WebFlux cũng cần SecurityWebFilterChain tách biệt

Ví dụ:

```java
@Bean
@Order(1)
SecurityWebFilterChain bearerRoutes(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .bearerTokenConverter(
                new StrictReactiveBearerConverter()
            )
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Legacy route nếu cần Basic:

```java
@Bean
@Order(2)
SecurityWebFilterChain basicRoutes(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/legacy/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Các ví dụ này là fragments cần imports từ Spring Security WebFlux và `@Order`. Cần thêm fallback chain bảo vệ các route khác theo application contract.

**Không nhầm hai loại matcher:**

- `securityMatcher(...)` chọn **SecurityWebFilterChain**.
- `authorizeExchange().pathMatchers(...)` chọn **authorization rule** bên trong chain đã được chọn.

Nếu request rơi nhầm vào chain web-login, chỉ sửa converter Bearer có thể không giải quyết được redirect HTML login.

## 15. HTTP Basic khác introspection client authentication

Trong Resource Server dùng opaque token có thể tồn tại hai header HTTP Basic/Bearer ở **hai kết nối khác nhau**:

```text
API caller -> Orders API:
    Authorization: Bearer ACCESS_TOKEN

Orders API -> Authorization Server introspection:
    Authorization: Basic CLIENT_ID:CLIENT_SECRET
    body: token=ACCESS_TOKEN
```

Đừng nhầm HTTP Basic mà Resource Server dùng **outbound** để gọi introspection với cơ chế HTTP Basic **inbound** cho caller.

Vì vậy, để dùng opaque token, API **không cần bật `httpBasic()`** trong Bearer security chain. Việc bật `httpBasic` inbound chỉ vì introspection dùng client secret là sai trách nhiệm.

### 15.1. Vì sao Basic inbound có thể tạo UI ngoài mong đợi?

HTTP Basic challenge trên API Bearer có thể khiến browser hiển thị dialog username/password, trong khi OAuth client mong đợi:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Tương tự, form login có thể sinh `302 Location: /login`. Với Bearer-only routes, tránh bật các entry points không thuộc hợp đồng API.

## 16. CORS, CSRF và cookie khi có nhiều cơ chế

Một frontend cross-origin có thể gửi preflight:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight không nhất thiết mang Bearer access token. Cần cấu hình CORS để preflight đi qua trước authentication khi phù hợp; không tự biến mọi OPTIONS request thành token malformed.

### 16.1. CORS không thay authentication

Nếu cấu hình CORS cho phép origin cụ thể, điều đó **không chứng minh** Bearer token hợp lệ. Origin header do browser tạo trong một số ngữ cảnh nhưng không thể dùng làm bằng chứng authentication cho API clients.

### 16.2. CSRF phụ thuộc loại credential

- API **chỉ nhận Bearer từ Authorization header** và không dựa vào cookie tự gửi có mô hình CSRF khác với session-based web app.
- Nếu API cũng cho **cookie session authentication**, browser có thể tự đính kèm cookie → phải thiết kế CSRF protection phù hợp.
- Nếu một endpoint nhận cả cookie và Bearer, cần quy tắc rõ khi cả hai có mặt, và tránh “Bearer sai nhưng cookie được dùng” ngoài hợp đồng.
- Tắt CSRF toàn ứng dụng không phải cách chữa lỗi credential resolver.

### 16.3. Đừng chuyển token vào cookie để né Authorization header

Nếu application muốn BFF/session architecture, phải thiết kế nó như **một boundary xác thực riêng**, không đơn thuần đổi Bearer token sang Cookie rồi mặc định an toàn hơn. Các vấn đề SameSite, HttpOnly, Secure, CSRF, session fixation và refresh token handling vẫn tồn tại.

## 17. Kiểm soát header ambiguity ở proxy/gateway

Không phải mọi HTTP intermediary đều bảo toàn headers theo cùng cách. Ví dụ:

```http
Authorization: Bearer TOKEN_A
authorization: Bearer TOKEN_B
```

Tên HTTP header **không phân biệt hoa/thường**. Một proxy có thể gộp, chọn một dòng, từ chối hoặc chuyển tiếp theo implementation. Nếu edge và backend hiểu khác nhau, có nguy cơ **request smuggling/credential confusion**.

### 17.1. Chính sách nên áp từ ingress đến application

- Reject duplicate `Authorization` ngay tại ingress nếu hạ tầng hỗ trợ.
- Không gộp nhiều Bearer values thành một giá trị hợp lệ.
- Không tự chọn “last header wins” trong một hop và “first header wins” ở hop khác.
- Hạn chế kích thước Authorization header/token.
- Xác định rõ có chấp nhận custom proxy header hay không.
- Strip/overwrite những headers được gateway sở hữu.
- Bảo đảm logs/traces redact cả Bearer và API keys.
- Test qua đúng reverse proxy/ingress đang dùng, không chỉ unit test servlet mock.

Một `StrictHeaderBearerTokenResolver` ở backend là **defense in depth**; nó không thể khôi phục các duplicate values đã bị một proxy gộp trước khi forwarding.

### 17.2. HTTP request smuggling và cache

Nếu proxy, gateway và backend parse header khác nhau, người dùng có thể thấy những phản hồi không nhất quán, đặc biệt khi có caching/CDN. Không cache private API response thiếu đúng `Cache-Control`/`Vary`/identity isolation và không biến token thành URL cache key.

### 17.3. Đừng gửi raw credentials sang observability

Các trường nên redact:

```text
Authorization
Proxy-Authorization
X-API-Key
X-Internal-Access-Token
Cookie
Set-Cookie (khi chứa session token)
access_token query/body
```

Chỉ logging status, error class, latency, route, request correlation ID và mechanism **đã được nhận diện hợp lệ**. Không dùng raw token hoặc token hash có cardinality cao làm metric label.

## 18. 401, 400, 403 và lỗi auth mechanism

Theo RFC 6750, Bearer Resource Server có thể phản hồi challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Khi token không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Khi request Bearer sai về cấu trúc:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
```

Khi token hợp lệ nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

**Trạng thái cụ thể tùy bối cảnh lỗi và Spring Security handler**; không phải mọi malformed header đều phải luôn có cùng một status nếu không gian lỗi/phần mở rộng khác nhau. Nhưng API phải tránh redirect HTML login, 200 giả thành công và fallback âm thầm.

### 18.1. Bảng nguyên nhân → handler

| Vấn đề | Tầng chịu trách nhiệm | Hành vi |
|---|---|---|
| Không có credential | Resolver + authorization | 401 khi endpoint yêu cầu auth |
| Authorization header lặp | Resolver/ingress strict policy | Reject input |
| Bearer sai grammar | Resolver chuẩn | Authentication error, không fallback |
| JWT hết hạn/sai signature | JwtDecoder/provider | 401 invalid_token |
| Opaque introspection `active=false` | Introspector/provider | 401 invalid_token |
| Token hợp lệ thiếu `orders.write` | Authorization | 403 insufficient_scope |
| Token đủ scope nhưng sai owner | Domain policy | 403/404 theo contract |
| Introspection/JWKS timeout | Dependency/decoder | Fail closed; error mapping theo config |
| API key không hợp lệ trên API-key route | API-key authentication provider | 401 theo contract API key |
| Login cookie hết hạn trên web route | Web session mechanism | Có thể redirect login theo UX |

### 18.2. Không biến infrastructure outage thành “Bearer token rỗng”

Nếu `JwtDecoder` hoặc `OpaqueTokenIntrospector` gặp lỗi hạ tầng, resolver **vẫn đã tìm thấy token**. Không viết catch-all ở resolver hoặc manager trả `null` rồi cho request đi qua Basic/API key.

Phân loại lỗi network, TLS, timeout và client authentication outbound để giám sát, nhưng không cấp quyền khi không xác minh được Bearer token.

## 19. Test riêng resolver trước khi test authentication

Một test tốt tách ba lớp:

1. **Resolver test:** input HTTP request → token, null hoặc exception.
2. **Authentication test:** token candidate → valid/invalid sau JWT/opaque verification.
3. **Authorization test:** Authentication hợp lệ → scope, tenant và object permissions.

Dùng test chỉ ở lớp 2/3 sẽ không nhất thiết phát hiện duplicate input hoặc fallback sai.

### 19.1. Unit test Servlet resolver

Ví dụ với Spring `MockHttpServletRequest`:

```java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

import static org.junit.jupiter.api.Assertions.*;

class StrictHeaderBearerTokenResolverTest {

    private final StrictHeaderBearerTokenResolver resolver =
        new StrictHeaderBearerTokenResolver();

    @Test
    void extractsSingleBearerHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer test-token"
        );

        assertEquals("test-token", resolver.resolve(request));
    }

    @Test
    void returnsNullWhenBearerIsAbsent() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        assertNull(resolver.resolve(request));
    }

    @Test
    void doesNotTreatBasicAsBearer() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Basic dXNlcjpwYXNzd29yZA=="
        );

        assertNull(resolver.resolve(request));
    }

    @Test
    void rejectsMultipleAuthorizationHeaderValues() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer first-token"
        );
        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer second-token"
        );

        assertThrows(
            OAuth2AuthenticationException.class,
            () -> resolver.resolve(request)
        );
    }

    @Test
    void rejectsTokenInQuery() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.setQueryString("access_token=secret");
        assertThrows(
            OAuth2AuthenticationException.class,
            () -> resolver.resolve(request)
        );
    }

    @Test
    void rejectsMalformedBearerHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        request.addHeader(
            HttpHeaders.AUTHORIZATION,
            "Bearer token with whitespace"
        );

        assertThrows(
            OAuth2AuthenticationException.class,
            () -> resolver.resolve(request)
        );
    }
}
```

Các test này **không xác minh chữ ký JWT hoặc introspection**. Chúng chỉ chứng minh strict resolver trích/đánh giá input theo hợp đồng.

### 19.2. Test những biến thể dễ bị bỏ sót

| Input | Điều cần kiểm tra |
|---|---|
| `Authorization: bearer token` | Scheme case-insensitivity theo resolver chuẩn |
| `Authorization: BEARER token` | Quy tắc scheme và parser |
| `Authorization: Bearer` | Thiếu token phải lỗi |
| `Authorization: Bearer   token` | Không tự normalize ngoài grammar |
| `Authorization: Bearer token, Bearer other` | Không chọn một token tùy ý |
| Hai header với casing khác nhau | Header names case-insensitive |
| Header rất dài | Bị giới hạn ở edge/container trước tốn tài nguyên |
| `?access_token=abc` | Query bị chặn theo strict policy |
| `?access%5Ftoken=abc` | Encoded name không bypass policy |
| Token trong form body | Không được dùng mặc định |
| Cookie + Bearer | Chính sách multi-credential được thực thi |
| API key + Bearer | Không tự chuyển sang API key |
| JWT-like string không có signature đúng | Resolver chỉ extract, decoder reject |
| Opaque string với dấu chấm | Không dùng hình thức token để tự skip validation |

### 19.3. Test lỗi parser không được bị swallow

Một custom resolver sai có thể làm:

```java
try {
    return delegate.resolve(request);
} catch (OAuth2AuthenticationException ex) {
    return null; // KHÔNG DÙNG
}
```

Test cần chứng minh malformed Bearer sinh **lỗi**, không biến thành request anonymous để một cơ chế khác tiếp tục. Đây là kiểm tra chống downgrade thiết yếu.

## 20. MockMvc integration test: API có Bearer lỗi không thành login HTML

Các unit tests chưa chứng minh security chain/entry point đúng. Dùng `MockMvc` qua ứng dụng Spring Security:

```java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerApiContractTest {

    @Autowired MockMvc mvc;

    @Test
    void missingBearerIsNotHtmlLogin() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")
            ))
            .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }
}
```

Đây là một mẫu kiểm tra entry point/chain; cần endpoint/bean dependencies thực tế để chạy. Với malformed Bearer, test thêm status tương ứng RFC/framework và **không có redirect**. Với JWT sai signature, cần fake JWKS/test-signed token hoặc mock decoder được kiểm soát.

### 20.1. Kiểm tra không fallback sang API key

Nếu một endpoint phải nhận cả hai scheme theo migration contract, integration test nên gửi:

```http
Authorization: Bearer INVALID_TOKEN
X-API-Key: VALID_TEST_API_KEY
```

và xác nhận **request bị từ chối theo conflict rule**, không được vào controller. Ngoài status, assert backend **không gọi API-key authentication provider như một fallback** sau khi Bearer đã thất bại.

### 20.2. Kiểm tra 403 không fallback thành 200

Một JWT hợp lệ có `SCOPE_orders.read` nhưng request POST cần `SCOPE_orders.write` phải nhận 403. Không thử credential khác để “nâng quyền” cho request đã có một Bearer token được xác thực nhưng thiếu scope.

## 21. WebTestClient: test converter reactive và route

Với WebFlux, có thể dùng `MockServerWebExchange` và `MockServerHttpRequest` để kiểm tra converter:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import reactor.test.StepVerifier;

class StrictReactiveBearerConverterTest {

    private final StrictReactiveBearerConverter converter =
        new StrictReactiveBearerConverter();

    @Test
    void extractsBearerFromHeader() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer test-token"
                )
        );

        StepVerifier.create(converter.convert(exchange))
            .assertNext(authenticationRequest ->
                org.junit.jupiter.api.Assertions.assertEquals(
                    "test-token",
                    authenticationRequest.getCredentials()
                )
            )
            .verifyComplete();
    }

    @Test
    void rejectsQueryToken() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get(
                "/api/orders?access_token=unwanted"
            )
        );

        StepVerifier.create(converter.convert(exchange))
            .expectError()
            .verify();
    }
}
```

Trong các bản Spring Security tiêu biểu, `BearerTokenAuthenticationToken` giữ raw token trong credentials. Nếu contract/internal API thay đổi, test nên kiểm tra **loại authentication request và token value** theo API version thực tế.

### 21.1. WebTestClient integration khác converter unit test

`mockJwt()` hoặc `mockOpaqueToken()` trong Spring Security Test thường cài Authentication **thử nghiệm** để kiểm tra authorization; chúng **không kiểm tra converter đọc Bearer header** và không xác minh signature/introspection.

Để test toàn tuyến:

1. Gửi HTTP Bearer header thực qua `WebTestClient`.
2. Cho `AuthenticationWebFilter` và custom converter chạy.
3. Dùng fake issuer/JWKS hoặc fake introspection endpoint.
4. Test token hợp lệ, sai, thiếu và duplicate.
5. Xác nhận 401/403 và `WWW-Authenticate`.
6. Nếu có hai chains, kiểm tra API không rơi vào login chain.
7. Khi dùng nhiều mechanism, gửi credential xung đột và xác nhận không fallback.
8. Đảm bảo request malformed không gọi controller/business service.

## 22. Bộ test tổng hợp nhiều cơ chế xác thực

| Test | Nguồn credential | Kỳ vọng |
|---|---|---|
| Bearer only, token đúng | Authorization header | Verify token, áp scope |
| Bearer only, token hết hạn | Authorization header | 401, không fallback |
| Bearer header malformed | Authorization header | Lỗi input, không fallback |
| Không Bearer ở route bảo vệ | Không credential | 401 Bearer |
| Basic ở Bearer-only route | Authorization: Basic | Không trở thành Bearer; route từ chối |
| Basic đúng ở Basic-only route | Authorization: Basic | Authn theo Basic provider |
| Bearer ở Basic-only route | Authorization: Bearer | Không được tự cấp quyền |
| API key đúng ở API-key route | X-API-Key | Theo provider của route |
| Bearer + API key trên shared route | Hai nguồn | Reject conflict theo chính sách |
| Bearer + cookie trên shared route | Hai nguồn | Áp contract explicit, không âm thầm chọn |
| Hai Authorization headers | Duplicated headers | Reject |
| Header + query token | Nhiều nguồn | Reject strict policy |
| Query-only token | URL | Không được dùng làm Bearer |
| Custom gateway header từ Internet | Untrusted header | Reject/strip tại edge, không tin |
| Gateway mTLS + managed header | Trusted channel | Authn theo Bearer decoder sau extraction |
| Token có `aud=billing-api` | Bearer đúng cú pháp | 401 invalid_token của Orders API |
| JWT sai `iss` | Bearer đúng cú pháp | Không tự discovery issuer lạ |
| Token hợp lệ, thiếu scope | Bearer | 403 |
| Token đủ scope, sai tenant | Bearer | 403/404 theo domain |
| Opaque `active=false` | Bearer | 401 |
| Introspection timeout | Bearer | Fail closed, không chuyển sang API key |
| API gateway rewrite Authorization | Proxy path | Backend nhận đúng/không nhận theo contract |
| Trình duyệt gửi Accept HTML | Bearer-only API | 401 Bearer, không redirect login |

### 22.1. Test dưới đúng reverse proxy

Nếu chỉ test trực tiếp bằng MockMvc, nhiều behavior tại ingress sẽ không được quan sát:

- Gộp duplicate headers.
- Xóa hoặc overwrite Authorization.
- Chuyển tiếp custom header.
- Đổi request path và chọn sai security chain.
- Proxy tự trả 302/HTML login.
- CORS preflight bị từ chối.
- Token trong URL bị ghi access log.

Cần một số integration/e2e tests đi qua **cấu hình proxy tương đương production**, đặc biệt khi custom resolver sử dụng internal header.

## 23. Giám sát và chẩn đoán

Nếu sau khi đổi resolver có spike 401, cần phân biệt:

- Client thật sự ngừng gửi `Authorization`?
- Proxy xóa header?
- Resolver chuyển sang đọc custom header không có ở môi trường này?
- Có duplicate header bị strict policy từ chối?
- Request có thêm `access_token` query vô tình?
- JWT signature/issuer/audience không hợp lệ?
- Introspection endpoint lỗi?
- Scope mapping/authorization đổi?
- Request rơi vào chain Basic/web khác?

### 23.1. Metric gợi ý

| Metric | Mục đích |
|---|---|
| `credential.source=authorization_header` | Nguồn Bearer hợp lệ được chọn, không ghi token |
| `credential.error=duplicate_header` | Phát hiện ambiguity/proxy misconfiguration |
| `credential.error=query_token_rejected` | Phát hiện nguồn token bị cấm |
| `credential.error=malformed_bearer` | Theo dõi client sai chuẩn |
| `authentication.mechanism=bearer/basic/api_key` | Tỷ lệ sử dụng từng cơ chế ở route được phép |
| `authentication.outcome=success/invalid/error` | Phân biệt loại kết quả |
| `authorization.outcome=granted/denied` | Đo 403 và object policy |
| `jwt.decoder.failure` | Chữ ký, issuer, audience, exp |
| `introspection.failure` | AS lỗi/client authentication |
| `gateway.auth_header_rewrite` | Quan sát thay đổi nguồn credential |
| `request.route_group` | Phân tích theo nhóm endpoint |

Tên metrics là **gợi ý**, không phải mọi metric Spring Security đã cung cấp sẵn. Nên dùng low-cardinality tags, không đưa raw token, `sub`, URL tùy ý hay API key vào label.

### 23.2. Log an toàn

Ví dụ:

```text
WARN credential_rejected
  requestId=...
  route=/api/orders/*
  source=authorization_header
  reason=multiple_headers
  mechanism=bearer
```

Không log:

```text
Authorization: Bearer <raw-token>
X-API-Key: <raw-api-key>
X-Internal-Access-Token: <raw-token>
Cookie: SESSION=<raw-session>
```

Bearer token là credential có thể bị replay. Dù chỉ debug, không ghi nó vào issue tracker, traces hoặc test reports.

## 24. Những anti-pattern thường gặp

### 24.1. Dùng substring(7) thay resolver chuẩn

Không xử lý đủ cú pháp Bearer và dễ nhận nhầm Basic/empty/malformed token.

### 24.2. Catch exception rồi return null

Biến lỗi Bearer thành “không có credential”, mở đường fallback sang cơ chế khác.

### 24.3. Tự parse JWT trong resolver và tạo authorities

Payload chưa verify không được dùng làm bằng chứng quyền.

### 24.4. Chấp nhận token từ header, query và form mà không có quy tắc

Dẫn tới credential ambiguity, URL leaks và sự khác biệt giữa proxy/backend.

### 24.5. Chọn token bằng “nguồn nào xuất hiện trước”

Nếu hai nguồn mâu thuẫn, chọn tùy ý làm behavior không nhất quán. Ưu tiên reject conflict.

### 24.6. Cho API key cứu Bearer token hết hạn

Đây là downgrade ngầm; chỉ hỗ trợ migration bằng policy rõ ràng và test conflict.

### 24.7. Tin proxy header từ bất kỳ IP/client

Dẫn tới spoofing. Proxy-owned header phải được strip/overwrite và đi trên trusted channel.

### 24.8. Dùng Host/X-Forwarded-Host tạo issuer URL

Đây là rủi ro SSRF/trust confusion; dùng trusted issuer registry.

### 24.9. Bật Basic chỉ vì opaque introspection dùng client-secret

Basic introspection là outbound Resource Server → AS, không phải inbound API caller.

### 24.10. Chỉ sửa AuthenticationEntryPoint mà không sửa chain matcher

Nếu API rơi nhầm vào form/OIDC login chain, vẫn có thể nhận HTML redirect.

### 24.11. Biến WebFlux converter thành blocking JwtDecoder

Có thể chặn event-loop, mất Reactor context và xác minh lặp. Giữ converter chỉ trích credential.

### 24.12. Dùng mockJwt() coi như đã test resolver

Mock auth thường bỏ qua header resolution, nên cần test độc lập converter/resolver.

### 24.13. Coi `Authorization: Bearer` là token rỗng chấp nhận được

Thiếu token là lỗi input; không tự tạo anonymous principal có quyền.

### 24.14. Thấy API trả 200 là coi đã xác thực

Controller có thể public hoặc redirect HTML đã được follow. Kiểm tra Authentication và scope/route contract, không suy đoán qua status đơn lẻ.

## 25. Quy trình triển khai cho một hệ thống đa cơ chế

**Bước 1 — Lập bảng route và credential.**

```text
/api/**       Bearer only
/legacy/**    Basic only, thời gian deprecation cụ thể
/web/**       Session/OIDC Login
/internal/**  mTLS/workload identity theo network contract
```

Nếu route cần nhiều mechanism, phải nêu rõ thời hạn migration, conflict handling và chính sách fallback.

**Bước 2 — Chọn một nguồn Bearer mặc định.**

Ưu tiên `Authorization: Bearer`. Đánh giá kỹ trước khi dùng form/query/custom header. Không cho phép nguồn token khác chỉ vì dễ code.

**Bước 3 — Dùng resolver/converter chuẩn làm delegate.**

Ở Servlet dùng `DefaultBearerTokenResolver`; ở WebFlux dùng `ServerBearerTokenAuthenticationConverter`. Thêm strict validation cho duplicate/query hoặc policy riêng nhưng không tự viết lại grammar thiếu kiểm soát.

**Bước 4 — Giữ error semantics.**

`null` nghĩa không có Bearer; malformed credential nghĩa lỗi; token sai validation trả 401; thiếu scope trả 403. Không convert lỗi thành `null`.

**Bước 5 — Cấu hình SecurityFilterChain theo route.**

Đặt Bearer API chain ưu tiên, tắt các cơ chế không chủ định trong chain đó, có fallback cho routes khác.

**Bước 6 — Xác minh token bằng provider đúng.**

JWT phải check signature, issuer, audience, exp/nbf/algorithm/profile. Opaque token phải check introspection `active` và policy AS. Không tự khai authenticated principal trong resolver.

**Bước 7 — Phân quyền nghiệp vụ.**

Scope không đủ để đọc mọi order: kiểm tra tenant, subject/client, owner và trạng thái tài nguyên.

**Bước 8 — Gia cố gateway.**

Reject duplicated/ambiguous headers, strip custom headers, bảo vệ mTLS/egress khi cần, giới hạn kích thước header và redact logs.

**Bước 9 — Kiểm thử ba tầng.**

Unit resolver/converter; integration authentication; end-to-end qua gateway và domain authorization. Test đầy đủ các xung đột source và fail-closed.

**Bước 10 — Đo và loại bỏ cơ chế legacy.**

Theo dõi số request theo mechanism, deprecation timeline và lỗi migration. Không giữ API key/Basic fallback mãi mãi nếu không còn được phê duyệt.

## 26. Những quyết định cần được ghi thành hợp đồng

| Quyết định | Giá trị ví dụ |
|---|---|
| Bearer source | `Authorization` header duy nhất |
| Query/body Bearer | Không chấp nhận |
| Duplicate Authorization | Reject |
| Bearer malformed | Reject, không fallback |
| JWT/opaque validation | Đúng provider và issuer/resource contract |
| Multiple credential classes trên cùng route | Không, trừ migration contract |
| Nếu Bearer + API key cùng có | Reject conflict |
| Nếu Bearer invalid nhưng API key đúng | Không fallback |
| Proxy-managed token header | Chỉ qua authenticated gateway path |
| Error response | 401/403 Bearer, không login HTML |
| Logging | Redact raw tokens/keys/cookies |
| Rate limiting | Gateway + per-route + auth dependency limits |
| Tenant binding | Theo issuer/tenant policy đã verify |
| Migration ownership | Đội API + Security + Identity |
| Test bắt buộc | Duplicate, wrong scheme, invalid signature, ambiguity, proxy rewriting |

Đây là một **contract ví dụ**; cơ chế xác thực và lỗi phải được điều chỉnh theo sản phẩm, khách hàng và chuẩn liên quan. Điểm không thay đổi là **không có nhánh nào được cấp quyền dựa trên một credential chưa xác minh hoặc một nguồn không được phép**.

## 27. Nguồn tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer header, form/query alternatives, một nguồn token trên một request, `invalid_request`, `invalid_token`, `insufficient_scope`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `Authorization`, authentication challenge, 401/403 và HTTP headers.
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer filter, authentication và cấu hình Resource Server.
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): nguồn Bearer và cấu hình form/query/header.
- [Spring Security — WebFlux OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): reactive Bearer authentication.
- [Spring Security API — ServerBearerTokenAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/server/ServerBearerTokenAuthenticationConverter.html): reactive token conversion.
- [Spring Security — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): nhiều `SecurityFilterChain` và thứ tự matchers.
- [Spring Security — WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`/`ServerHttpSecurity`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token profile và phân biệt access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cách xác thực opaque access token, `active` và metadata.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): các rủi ro authorization và credential handling.
- [OWASP HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): các header bảo vệ HTTP liên quan đến triển khai web.

**Kết luận:** Một custom token resolver tốt không phải resolver “tìm ra token trong càng nhiều nơi càng tốt”, mà là resolver **chỉ chấp nhận nguồn credential được phê duyệt, phát hiện ambiguity, giữ parser/challenge chuẩn và không nuốt lỗi Bearer**. Khi có nhiều cơ chế xác thực, nên **tách SecurityFilterChain theo route**; nếu bắt buộc cùng endpoint, phải có **conflict policy và không fallback sau credential thất bại**. Dù token được lấy từ header chuẩn hay từ một gateway header được bảo vệ, **`JwtDecoder`/`OpaqueTokenIntrospector` và authorization policy vẫn là các bước bắt buộc**. Giữ ranh giới rõ giữa *trích credential*, *xác minh credential* và *kiểm tra quyền tài nguyên* là cách giữ đầu vào thống nhất mà không giảm an toàn hệ thống.
