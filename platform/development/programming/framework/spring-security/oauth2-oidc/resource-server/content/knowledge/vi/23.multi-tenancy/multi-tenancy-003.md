# JwtIssuerAuthenticationManagerResolver và tập issuer được tin cậy

Trong **Spring Security OAuth 2.0/OIDC Resource Server** phục vụ **nhiều tenant**, một API có thể phải chấp nhận JWT access token do **nhiều Authorization Server hoặc nhiều issuer** phát hành. Ví dụ, tenant A dùng một realm của nhà cung cấp danh tính, tenant B dùng một realm khác; mỗi issuer có metadata, JWK Set, signing keys và chính sách riêng.

Với ứng dụng Spring Security **Servlet/Spring MVC**, `JwtIssuerAuthenticationManagerResolver` giúp chọn `AuthenticationManager` theo claim **`iss`** của JWT để xác minh token với đúng issuer. Tuy nhiên, điều kiện bắt buộc là **issuer được chọn phải thuộc tập nguồn phát hành mà Resource Server tin cậy**. Chỉ đọc `iss` từ payload của token chưa phải xác minh danh tính issuer.

> **Quy tắc nền tảng:** lấy claim `iss` chưa được xác minh chỉ để **định tuyến tới một cơ chế xác minh đã được phê duyệt**; không được dùng nó như bằng chứng token hợp lệ, không được tự kết nối tới một issuer bất kỳ và không được cấp quyền dựa trên những claims khác trước khi chữ ký và các validators thành công.

Bài này giải thích trust boundary, cấu hình `fromTrustedIssuers(...)`, xử lý tập issuer động, xác minh issuer và audience, phân biệt tenant với issuer, rủi ro SSRF/JWKS confusion, cơ chế lazy loading, kiểm thử và vận hành. Mã mẫu dùng **Java 17+, Spring Boot, Spring Security Servlet**; chú ý mốc API khi chạy Spring Security 6.x hoặc 7.x.

## 1. Multi-tenant Resource Server là gì?

Một Resource Server có thể phải xử lý:

~~~text
Tenant A
   |
   +-- Authorization Server A / realm A
   |       issuer = https://idp-a.example.com/realms/shop
   |       JWKS   = https://idp-a.example.com/realms/shop/certs
   |
   v
                    +-------------------------+
                    | Orders Resource Server  |
                    | /api/orders/**          |
                    +-------------------------+
   ^
   |
Tenant B
   |
   +-- Authorization Server B / realm B
           issuer = https://idp-b.example.com/realms/shop
           JWKS   = https://idp-b.example.com/realms/shop/certs
~~~

Hai issuer có thể cùng dùng thuật toán RS256, cùng tên scope `orders.read`, thậm chí có các giá trị `sub` hoặc `kid` trùng nhau. Resource Server vẫn phải:

1. Chọn đúng **nguồn khóa** để xác minh từng token.
2. Kiểm tra JWT có **đúng issuer** tương ứng.
3. Kiểm tra token **dành cho chính API** qua `aud` hoặc ràng buộc resource khác.
4. Kiểm tra thời hạn `exp`, `nbf` và profile token áp dụng.
5. Ánh xạ scope/role theo contract của từng issuer.
6. Chỉ cho phép truy cập tenant và bản ghi mà subject có quyền thực tế.

Spring Security gọi đây là bài toán **resolve tenant** và **propagate tenant**. `JwtIssuerAuthenticationManagerResolver` chủ yếu giải quyết vấn đề **chọn chiến lược xác thực theo issuer**; nó **không tự bảo vệ ownership, tenant membership, data isolation** ở tầng nghiệp vụ.

### 1.1. Issuer không nhất thiết là tenant

Ba hệ thống sau có mô hình khác nhau:

| Mô hình | Issuer | Tenant | Hệ quả |
|---|---|---|---|
| Một issuer cho một tenant | A → issuer A; B → issuer B | Một-một | Có thể dùng issuer để chọn authentication strategy |
| Một issuer cho nhiều tenant | Cả A/B dùng issuer X | Nhiều tenant trong token/DB | Resolver theo `iss` **không tự phân biệt** tenant A và B |
| Một tenant tin nhiều issuers | Tenant A dùng issuer X và Y | Một tenant, nhiều identity providers | Phải xác minh issuer trước rồi map identity/membership tới tenant |

**Không mặc định `tenantId = issuer`.** Trong một số deployment đúng là mỗi tenant có realm/issuer riêng, nhưng đó là **quy ước kiến trúc**, không phải tính chất bắt buộc của OAuth 2.0/OIDC.

### 1.2. Những gì JWT có thể mang

Token từ issuer A:

~~~json
{
  "iss": "https://idp-a.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "exp": 2000000300
}
~~~

Token từ issuer B:

~~~json
{
  "iss": "https://idp-b.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-b",
  "exp": 2000000300
}
~~~

Dù cùng `sub=user-42`, hai principal **không tự là một người**. Khi định danh user trong database đa issuer, có thể dùng khóa `(issuer, subject)` hoặc một canonical internal user ID được ánh xạ từ cặp đó bởi dịch vụ tin cậy.

## 2. Vì sao một JwtDecoder chung có thể chưa đủ?

Cấu hình một issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp-a.example.com/realms/shop
~~~

thường tạo một decoder xác minh token cho issuer A. Đây là lựa chọn hợp lý nếu API chỉ tin A, nhưng khi tenant B dùng issuer B và signing keys khác, một decoder gắn riêng issuer A không đáp ứng yêu cầu.

Một cách tiếp cận sai là lấy token của bất kỳ issuer nào rồi:

~~~text
1. Chỉ decode payload.
2. Lấy issuer mới từ `iss`.
3. Tin payload và cấp quyền.
```

Cách đúng phải có **một tập issuers được phép**, và **một authentication manager/decoder tương ứng** cho từng issuer:

~~~text
JWT chưa được xác minh
        |
        v
Đọc `iss` CHỈ để định tuyến
        |
        v
`iss` thuộc tập trusted issuers?
   |                         |
   Không                      Có
   |                         |
   v                         v
 Reject              Manager của issuer đó
                             |
                       Lấy khóa từ JWK source
                       đã được phê duyệt
                             |
                       Verify signature
                       Validate iss/aud/time
                             |
                       Authentication thành công
                             |
                       Authorization/resource policy
~~~

Cách này giải quyết lựa chọn **manager**, không biến `iss` thành bằng chứng đáng tin ngay từ bước đầu.

## 3. Ranh giới tin cậy: `iss` ban đầu là dữ liệu chưa được xác minh

JWT JWS có cấu trúc:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Các bytes của header và payload được gửi bởi caller; trước khi xác minh chữ ký, caller có thể thay chúng.

Ví dụ payload giả mạo:

~~~json
{
  "iss": "https://attacker.example/oidc",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

Kẻ tấn công có thể dựng một Authorization Server riêng, công bố JWKS với public key do mình kiểm soát, rồi ký token bằng private key tương ứng.

Nếu Resource Server làm:

~~~java
// NGUY HIỂM: tạo decoder dựa vào bất kỳ issuer do caller khai.
AuthenticationManager resolve(String issuer) {
    JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
    return new JwtAuthenticationProvider(decoder)::authenticate;
}
~~~

mà **không kiểm tra allowlist**, token giả vẫn có thể hợp lệ **với chính issuer do attacker lập ra**. Nó không chứng minh issuer ấy được API tin cậy.

Ngoài nguy cơ **authentication bypass/cross-issuer trust**, thiết kế này còn có thể tạo **SSRF** nếu server bị dụ gọi metadata/JWKS URL ngoài ý muốn hoặc địa chỉ nội bộ.

### 3.1. Giá trị `iss` có thể được dùng cho việc gì khi chưa xác minh?

Được phép **định tuyến** đến một manager đã được đăng ký từ nguồn tin cậy:

~~~text
unverified iss -> exact allowlist lookup -> verified manager
```

Không được phép:

~~~text
unverified iss -> arbitrary HTTP metadata fetch -> accept self-signed attacker token
unverified iss -> trusted=true
unverified iss -> ROLE_ADMIN
unverified iss -> authorization to tenant database
```

Sau khi decoder thực sự xác minh chữ ký **và** kiểm tra issuer, `Jwt#getIssuer()` mới là thuộc tính của một **token đã được xác thực**, có thể đưa vào identity mapping.

### 3.2. Danh sách issuer được phép là nguồn quyền ở cấu hình

Một allowlist nên xuất phát từ:

- Cấu hình server do team vận hành/bảo mật quản lý.
- Onboarding tenant đã được duyệt, ghi vào registry đáng tin.
- Control plane nội bộ có xác thực, phân quyền và audit.
- Trusted configuration service có integrity và change control.

Không lấy danh sách từ:

- JWT `iss` chưa verify.
- Query parameter `?issuer=...`.
- `X-Issuer` hoặc `X-Tenant` client tự gửi.
- Email domain, username hoặc host tùy ý.
- Discovery endpoint tự được chọn từ `jku`/`x5u` trong JWT header.

## 4. `JwtIssuerAuthenticationManagerResolver` làm việc gì?

Spring Security Servlet cung cấp class:

~~~java
org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver
~~~

Nó triển khai:

~~~java
AuthenticationManagerResolver<HttpServletRequest>
~~~

Về khái niệm, resolver:

1. Lấy bearer token từ `HttpServletRequest` khi authentication diễn ra.
2. Parse claims để lấy `iss` **cho mục đích lựa chọn manager**.
3. Kiểm tra/tìm một `AuthenticationManager` tương ứng issuer đó.
4. Chuyển bearer token đến manager được chọn.
5. Manager dùng `JwtAuthenticationProvider`/`JwtDecoder` để **xác minh token thật**.
6. Chỉ khi xác thực thành công mới tạo `Authentication` cho authorization.

**Lưu ý kỹ thuật:** `resolve(HttpServletRequest)` trả một `AuthenticationManager` thực hiện việc resolve issuer trong authentication stage; không nhất thiết nghĩa toàn bộ parsing/selection xảy ra ngay tại lời gọi `resolve` ở mọi implementation version.

### 4.1. Vị trí trong Servlet filter chain

~~~text
HTTP Authorization: Bearer token
               |
               v
BearerTokenAuthenticationFilter
               |
               v
JwtIssuerAuthenticationManagerResolver
               |
               v
     Tìm manager theo `iss`
               |
         +-----+-----+
         |           |
      Issuer A    Issuer B
         |           |
         v           v
     JwtAuthenticationProvider A/B
         |
         v
     JwtDecoder đúng issuer/key source
         |
         +-- Verify chữ ký JWS
         +-- Validate `iss`, `aud`, `exp`, `nbf`
         |
         v
     JwtAuthenticationToken
         |
         v
     AuthorizationFilter / Controller
~~~

Trong mô hình này resolver là **authentication routing**, không phải `AuthorizationManager` cho rule `hasAuthority` hoặc ACL.

### 4.2. Vì sao class này thuộc Servlet?

Nó dùng `AuthenticationManagerResolver<HttpServletRequest>` và đi với `HttpSecurity`/`SecurityFilterChain`. Trong WebFlux có counterpart **`JwtIssuerReactiveAuthenticationManagerResolver`** dùng Reactive APIs.

Không đổi tên Java class tùy ý nhưng giữ `HttpServletRequest`/`JwtDecoder` trong WebFlux. Bài học này tập trung vào **Servlet Resource Server** do chính tên API `JwtIssuerAuthenticationManagerResolver`.

## 5. Cấu hình đơn giản nhất: `fromTrustedIssuers(...)`

Với hai issuer tin cậy được biết trước:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-a.example.com/realms/shop",
        "https://idp-b.example.com/realms/shop"
    );
~~~

Đây là hướng trong tài liệu **Spring Security multi-tenancy**: cung cấp rõ những issuer được phép.

### 5.1. Full `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerSecurityConfig {

    @Bean
    JwtIssuerAuthenticationManagerResolver trustedIssuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            "https://idp-a.example.com/realms/shop",
            "https://idp-b.example.com/realms/shop"
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver resolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()

                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

Cấu hình này dùng **`authenticationManagerResolver`** thay vì một decoder JWT cố định trong DSL. Spring Security tự tạo/giữ manager theo issuer trong cơ chế `fromTrustedIssuers` của phiên bản đang chạy.

**Quan trọng:** ví dụ chỉ ràng buộc trusted issuers theo hướng mặc định. Nếu API yêu cầu **audience `orders-api`**, token type hoặc issuer-specific claim policy, phải bổ sung validators bằng resolver/manager strategy thích hợp (xem phần registry). Không được suy ra allowlist issuers tự đảm bảo `aud`.

### 5.2. Dependency Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Phụ thuộc phiên bản Spring Boot BOM/Dependency Management, không hardcode các Spring Security artifacts có version khác nhau.

### 5.3. Spring Security version và API

| API | Ghi chú |
|---|---|
| `JwtIssuerAuthenticationManagerResolver` | Có từ Spring Security 5.3 |
| `fromTrustedIssuers(String...)` | Có từ **6.2** |
| `fromTrustedIssuers(Collection<String>)` | Có từ **6.2** |
| `fromTrustedIssuers(Predicate<String>)` | Có từ **6.2** |
| Constructor nhận `String...` hoặc `Collection<String>` | **Deprecated từ 6.2**, đánh dấu hướng tới loại bỏ |
| Constructor nhận `AuthenticationManagerResolver<String>` | Dùng cho manager registry tùy chỉnh |

Với Spring Security 6.2+/7.x, ưu tiên **`fromTrustedIssuers(...)`** thay cho constructor deprecated. Đối với dự án cũ hơn 6.2, cần đối chiếu đúng Javadoc/API của version đang chạy trước khi chọn cú pháp.

Đừng copy hướng dẫn cũ sử dụng `new JwtIssuerAuthenticationManagerResolver("issuer-a", "issuer-b")` rồi xem cảnh báo deprecation là không liên quan tới quá trình nâng cấp.

## 6. `fromTrustedIssuers` bảo vệ như thế nào?

Với:

~~~java
.fromTrustedIssuers("https://idp-a.example.com/realms/shop")
~~~

token khai:

~~~json
{"iss":"https://attacker.example/oidc"}
~~~

không được manager tự ý fetch discovery từ attacker: issuer không nằm trong tập đã đăng ký.

Token khai **issuer A** nhưng được ký bằng **khóa của attacker** cũng phải thất bại ở bước verification, vì manager A chỉ tin keys của nguồn được cấu hình cho issuer A.

~~~text
Case 1:
iss = attacker.example
-> không match allowlist -> reject trước tạo decoder cho issuer lạ

Case 2:
iss = idp-a.example.com
signature = attacker key
-> chọn manager A
-> chữ ký không verify bằng trusted JWK của A
-> reject

Case 3:
iss = idp-a.example.com
signature = real key của A
aud = api-khác
-> chữ ký đúng, nhưng vẫn phải reject nếu API yêu cầu aud=orders-api

Case 4:
iss = idp-a.example.com
signature = real key A
aud = orders-api
exp đã qua
-> reject vì token expired
```

**Allowlist chỉ xác định ai được phát token mà API xem xét; chữ ký và claims vẫn phải được kiểm tra.**

### 6.1. Exact string matching của issuer

Issuer là một định danh URL (đúng giá trị `iss`), không chỉ hostname. Những chuỗi sau **không tự tương đương**:

~~~text
https://idp-a.example.com/realms/shop
https://idp-a.example.com/realms/shop/
https://IDP-A.example.com/realms/shop
http://idp-a.example.com/realms/shop
https://idp-a.example.com/realms/SHOP
~~~

Đừng tự lower-case toàn chuỗi, bỏ path, cắt trailing slash hoặc chuyển HTTPS thành HTTP để “normalization issuer” một cách tùy tiện. Nếu AS dùng canonical issuer riêng, cấu hình **đúng giá trị issuer đã được công bố**.

Một issuer chỉ được cho phép vì khớp hostname mẹ như `endsWith(".example.com")` có thể mở rộng tập tin cậy tới các service, subdomain hoặc realm ngoài chủ đích.

### 6.2. Dynamic Predicate không được thành `issuer -> true`

Trong một số dự án cần predicate:

~~~java
Set<String> approved = Set.of(
    "https://idp-a.example.com/realms/shop",
    "https://idp-b.example.com/realms/shop"
);

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        approved::contains
    );
~~~

Mẫu này chỉ chấp nhận issuer thuộc tập đã được phê duyệt.

Ngược lại:

~~~java
// NGUY HIỂM: cho phép bất kỳ issuer nào tự khai.
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        issuer -> true
    );
~~~

làm vô hiệu hóa lợi ích của allowlist. Đừng mặc định nghĩ `Predicate` nghĩa là framework tự kiểm chứng domain của issuer.

## 7. Lazy loading: lợi ích và rủi ro vận hành

Với `fromTrustedIssuers`, Spring Security **tạo manager/provider theo issuer khi lần đầu cần dùng issuer đó**; docs mô tả các issuer endpoints được load lazily.

Điểm lợi:

- Ứng dụng có thể start dù một số AS đang tạm thời không truy cập được.
- Không cần tạo decoder và gọi discovery cho mọi issuer ngay lúc khởi động.
- Một tenant ít dùng không bắt buộc có hoạt động mạng tại startup.

Nhưng cần hiểu giới hạn:

~~~text
Application startup
    |
    +-- resolver biết trusted list
    +-- chưa chắc đã gọi mọi JWKS/metadata endpoints
    |
    v
First token của issuer B
    |
    +-- tạo manager/decoder cho B
    +-- có thể cần issuer discovery/JWKS retrieval
    +-- nếu B tạm unavailable -> authentication failure/dependency error
```

**Startup độc lập với AS không đồng nghĩa first request độc lập với AS.**

### 7.1. Cold start và first-request latency

Đo:

- Lần đầu một instance thấy token thuộc issuer mới.
- Độ trễ DNS/TLS/discovery/JWKS.
- Số lượng concurrent requests cùng issuer lúc cold.
- Response khi AS unreachable.
- Cache keys sau khi manager được tạo.
- Key rotation và `kid` mới.

Một deployment 200 replicas với nhiều tenants có thể tạo tải đột biến lên AS khi các instances cùng cold start. Cân nhắc warm-up có giới hạn, JWKS gateway tin cậy, connection timeouts, bounded retry và quan sát tải.

### 7.2. Fail closed khi AS không sẵn sàng

Nếu không có public key đã được tin và không thể lấy metadata/JWKS, token cần key đó **không được xác thực**.

Không viết fallback:

~~~java
// SAI: khi issuer unavailable, tự cho qua.
return authentication -> new JwtAuthenticationToken(unverifiedJwt);
~~~

Gián đoạn AS có thể gây authentication failure hoặc infrastructure error tùy handler, nhưng không được tạo authenticated principal từ token chưa được xác minh.

## 8. Trusted issuers chưa đủ: bắt buộc xét audience

Giả sử AS A cấp hai loại access token:

~~~text
Token 1: aud = orders-api
Token 2: aud = billing-api
```

Cả hai đều do issuer A ký. Nếu Resource Server chỉ kiểm tra chữ ký + issuer mà **không yêu cầu đúng `aud`**, token dùng cho Billing API có thể bị dùng nhầm ở Orders API.

### 8.1. Tách issuer validation và resource audience

| Kiểm tra | Câu hỏi |
|---|---|
| Trusted issuer allowlist | AS này có được phép phát token mà API xem xét? |
| JWS signature | Token thật sự do signing key của AS tương ứng ký? |
| `iss` | Token sau verify có đúng issuer đã chọn không? |
| `aud` | Token này có được cấp cho **API này** không? |
| `exp`/`nbf` | Token còn trong khoảng thời gian hợp lệ? |
| Token profile/`typ` | Có đúng loại JWT access token mà API chấp nhận không? |
| Scope/authority | Caller có quyền gọi thao tác? |
| Tenant/resource policy | Caller có quyền với entity/tenant cụ thể? |

**Không chỉ dùng `sub` và scope** để nhận một token từ nhiều issuers. Phải biết đúng issuer, audience và identity namespace.

### 8.2. Phương án tùy chỉnh per-issuer để áp audience

Nếu cần audience riêng theo issuer, ta có thể đăng ký mỗi `AuthenticationManager` với decoder/validator rõ ràng. Cách này được mô tả ở phần registry bên dưới.

## 9. Tập issuer động: thay đổi tenant không cần restart

Một hệ thống SaaS có thể onboarding tenant mới khi ứng dụng đang chạy:

~~~text
T0: approved issuers = {A, B}
T1: Quản trị viên duyệt tenant C + issuer C
T2: approved issuers = {A, B, C}
T3: Tenant B ngừng hợp tác
T4: approved issuers = {A, C}
~~~

Nếu chỉ dùng danh sách hardcode, phải deploy/restart để thay đổi. Spring Security hỗ trợ constructor:

~~~java
new JwtIssuerAuthenticationManagerResolver(
    AuthenticationManagerResolver<String> issuerManagerResolver
)
~~~

Một repository có thể lưu map **issuer → AuthenticationManager**. Trong tài liệu Spring, `authenticationManagers::get` được dùng làm strategy; issuer không nằm trong map → không có manager.

**Điểm bảo mật:** registry này phải được cập nhật **qua onboarding/control plane đáng tin**, tuyệt đối không tự thêm issuer từ JWT chưa xác minh hoặc một API public `POST /tenants`.

### 9.1. Cấu trúc registry

~~~text
Trusted Issuer Registry
    |
    +-- issuer A -> AuthenticationManager A
    |                 +-- JwtDecoder A
    |                 +-- public JWKS A
    |                 +-- validators iss A, aud orders-api
    |
    +-- issuer B -> AuthenticationManager B
    |                 +-- JwtDecoder B
    |                 +-- public JWKS B
    |                 +-- validators iss B, aud orders-api
    |
    +-- issuer C -> AuthenticationManager C
                      +-- JWT decoder C ...
```

Không map chỉ theo `kid`, bởi hai issuers có thể dùng `kid` giống nhau. **Manager và key source cần được gắn với issuer identity**.

## 10. Ví dụ đầy đủ: registry manager với allowlist do server quản trị

Ví dụ này dùng **JWK Set URI tường minh** cho từng issuer, giúp tránh việc lấy metadata từ URI do token khai. Mỗi entry chứa canonical issuer, URI JWKS đã duyệt và audience đúng API.

Các giá trị được đưa vào registry **chỉ từ nguồn cấu hình đáng tin**. Một controller public không được phép gọi `registerApprovedIssuer`.

### 10.1. Model cấu hình

~~~java
package com.example.orders.security;

// Domain config do server/control plane tin cậy quản lý.
public record TrustedIssuerSpec(
    String issuer,
    String jwkSetUri,
    String audience
) {}
~~~

`TrustedIssuerSpec` là class ví dụ do ứng dụng định nghĩa, không phải API Spring Security.

### 10.2. Registry và per-issuer AuthenticationManager

~~~java
package com.example.orders.security;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

public final class TrustedIssuerManagerRegistry {

    private final ConcurrentMap<String, AuthenticationManager> managers =
        new ConcurrentHashMap<>();

    // CHỈ gọi từ bootstrap/admin control plane đã được phê duyệt.
    public void registerApprovedIssuer(TrustedIssuerSpec spec) {
        // Validate canonical URLs, HTTPS, uniqueness, ownership và
        // endpoint egress allowlist ở onboarding trước khi gọi.
        // Không dùng spec nhận trực tiếp từ untrusted HTTP request.

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(spec.jwkSetUri())
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(spec.audience())
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(spec.issuer()),
                audienceValidator
            )
        );

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        AuthenticationManager manager =
            new ProviderManager(provider);

        managers.put(spec.issuer(), manager);
    }

    public AuthenticationManager resolve(String issuer) {
        // Unknown issuer => null; JwtIssuerAuthenticationManagerResolver
        // từ chối, không tạo một manager tùy ý.
        return managers.get(issuer);
    }

    public void deactivateIssuer(String issuer) {
        // Chỉ control plane có thẩm quyền được gọi.
        managers.remove(issuer);
    }
}
~~~

**Ý nghĩa từng thành phần:**

- `ConcurrentHashMap` cho phép nhiều request đồng thời đọc manager; thay map entry là một thao tác publish atomic.
- Mỗi decoder có **JWKS URI đã đăng ký** và JWS algorithm allowlist.
- `JwtValidators.createDefaultWithIssuer(...)` kiểm tra issuer và các validators mặc định phù hợp, bao gồm thời gian token.
- Audience validator bắt buộc `aud` chứa `orders-api` (hoặc giá trị theo từng issuer).
- Unknown issuer không có manager và **không khởi tạo decoder**.
- `deactivateIssuer` bỏ map entry để các lượt resolve mới không thể dùng manager cũ.

**Giới hạn ví dụ:** method `registerApprovedIssuer` chưa tự triển khai toàn bộ quy trình onboarding an toàn. Trong production cần validation URL/HTTPS, kiểm soát owner của issuer, egress allowlist, audit, hạn chế quyền admin và xử lý concurrency/lifecycle của manager cũ. Không lấy object `TrustedIssuerSpec` từ request public rồi gọi method này.

### 10.3. Gắn registry vào SecurityFilterChain

~~~java
package com.example.orders.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class RegistrySecurityConfig {

    @Bean
    TrustedIssuerManagerRegistry trustedIssuerRegistry() {
        TrustedIssuerManagerRegistry registry =
            new TrustedIssuerManagerRegistry();

        // Các giá trị này minh họa config đã được phê duyệt.
        registry.registerApprovedIssuer(new TrustedIssuerSpec(
            "https://idp-a.example.com/realms/shop",
            "https://idp-a.example.com/realms/shop/certs",
            "orders-api"
        ));

        registry.registerApprovedIssuer(new TrustedIssuerSpec(
            "https://idp-b.example.com/realms/shop",
            "https://idp-b.example.com/realms/shop/certs",
            "orders-api"
        ));

        return registry;
    }

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> issuerResolver(
            TrustedIssuerManagerRegistry registry) {

        return new JwtIssuerAuthenticationManagerResolver(
            registry::resolve
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> issuerResolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(issuerResolver))
            .build();
    }
}
~~~

**Đây là phương án thay thế** cho cấu hình `fromTrustedIssuers` phần 5; trong một ứng dụng không nên đồng thời khai báo nhiều `SecurityFilterChain` cùng phạm vi một cách vô ý.

Nếu dùng `issuer-uri` và `jwk-set-uri` cho mỗi tenant trong control plane, cần đảm bảo cặp đó được **phê duyệt cùng nhau**. Không được tin token từ issuer A nhưng lấy keys từ một URI tự được caller chỉ định.

### 10.4. Tại sao dùng direct `jwkSetUri`?

`NimbusJwtDecoder.withJwkSetUri(...)` cho phép tạo decoder từ một **key source tường minh**, không phải khám phá issuer metadata theo `iss` trong request. Một registry đáng tin giữ:

~~~text
Issuer canonical -> trusted JWKS URL
```

Điều này giúp kiểm soát egress và tránh discovery bất kỳ khi tenant mới chưa được phê duyệt.

Tuy vậy, **trusted key source không thay thế issuer validator**. Vì thế phần 10.2 vẫn đặt `JwtValidators.createDefaultWithIssuer(spec.issuer())`.

### 10.5. Nếu muốn dùng metadata discovery thay direct JWKS

Một manager được tạo từ:

~~~java
JwtAuthenticationProvider provider =
    new JwtAuthenticationProvider(
        JwtDecoders.fromIssuerLocation(approvedIssuer)
    );
~~~

là lựa chọn được Spring Security documentation mô tả cho dynamic tenants, **nếu** `approvedIssuer` đã được lấy từ registry tin cậy. Nó có thể cần discovery/JWKS network call lúc manager được xây hoặc lúc decode tùy version.

Để thêm audience validators và cấu hình timeout/keys riêng, thường cần xây decoder theo API version rồi đặt validators tường minh như phần 10.2.

**Không truyền thẳng bất kỳ `issuer` chưa được approve vào `JwtDecoders.fromIssuerLocation`.**

## 11. Khi disable tenant, request đang chạy và cache xử lý ra sao?

Xóa entry khỏi registry là cách ngăn **lượt resolve mới** tìm manager của issuer đó:

~~~java
registry.deactivateIssuer("https://idp-b.example.com/realms/shop");
~~~

Nhưng hệ thống có thể đang có:

- Request đã chọn manager B và đang xác minh.
- Authentication đã hoàn thành, service đang chạy.
- Nhiều replicas với registry chưa đồng bộ.
- JWT chưa hết hạn trong client.
- Cached JWK Set trong decoder B.
- Database membership/ACL được cache riêng.

Do đó, không được tuyên bố `remove()` đơn thuần bảo đảm **mọi request đang chạy dừng ngay**. Nếu yêu cầu thu hồi tức thời ở mức hệ thống, cần chính sách rõ cho request in-flight, distributed registry consistency, token revocation, object/service authorization checks và cache invalidation.

### 11.1. Tình huống thay đổi tenant

| Sự kiện | Điều nên xảy ra |
|---|---|
| Add tenant C đã duyệt | Sau khi entry C được publish, token C được kiểm tra bằng manager C |
| Issuer D chưa duyệt | Không có manager, không fetch metadata/JWKS D |
| Tenant B bị disable | Lượt resolve tiếp theo không tìm manager B |
| Tenant B được enable lại | Chỉ với cấu hình đáng tin được duyệt mới tạo manager mới |
| JWKS URL tenant A bị đổi | Cập nhật qua control plane, không từ header token |
| Policy audience tenant A thay đổi | Manager/decoder phải được dựng/cập nhật tương ứng |
| Kẻ tấn công gửi hàng nghìn issuers lạ | Từ chối sớm, không tạo manager/cache/network theo mỗi issuer |

### 11.2. Cần kiểm soát quy trình onboarding

Một `POST /admin/tenants` có thể hợp lệ nếu **thật sự là internal control plane** được xác thực mạnh, phân quyền admin, log/audit và validation dữ liệu nguồn. Nhưng không dùng một endpoint public “đăng ký issuer bất kỳ để thử JWT” trực tiếp gọi `registerApprovedIssuer`.

Nên quản lý tenant lifecycle như một workflow có phê duyệt, có rollback và kiểm thử, không như một side effect của request bearer token.

## 12. `fromTrustedIssuers(Predicate)` hay repository động?

| Cách | Ưu điểm | Khi thích hợp |
|---|---|---|
| `fromTrustedIssuers(String...)` | Đơn giản, tập tin cậy tĩnh rõ | Ít issuer, triển khai cố định |
| `fromTrustedIssuers(Collection)` | Dùng collection từ config được quản trị | Danh sách có sẵn lúc startup |
| `fromTrustedIssuers(Predicate)` | Policy trust check linh hoạt | Registry tin cậy có predicate rõ |
| Constructor với `AuthenticationManagerResolver<String>` | Tự quản lý manager, validators và lifecycle | Dynamic onboarding, per-issuer JWKS/audience |
| Nhiều `SecurityFilterChain` | Cô lập API/web/route policy khác nhau | Mỗi nhóm request có contract riêng |

**Không mặc định `Predicate` là dynamic registry đầy đủ.** Nó quyết định issuer nào được tin; implementation có thể cache manager, và yêu cầu lifecycle, thu hồi, metadata hay config mới cần được đánh giá riêng.

Nếu muốn *remove/reconfigure per-issuer manager* rõ ràng ở runtime, repository `issuer -> AuthenticationManager` do ứng dụng kiểm soát thường dễ hiểu hơn, nhưng phải đồng bộ cấu hình across replicas và xử lý race conditions.

## 13. Không chọn issuer bằng header hoặc subdomain một cách mù quáng

Một API có thể dùng subdomain/path để biết tenant mục tiêu:

~~~http
GET /api/tenants/tenant-a/orders HTTP/1.1
Host: api.example.com
X-Tenant-Id: tenant-a
Authorization: Bearer <JWT>
~~~

Nhưng điều đó không bảo đảm bearer JWT thuộc tenant A. Client có thể cố tình gọi:

~~~text
Path tenant = tenant-a
JWT issuer  = issuer-b
```

Chỉ chọn manager dựa trên header/path mà bỏ verify JWT issuer có thể tạo **cross-tenant confusion**.

### 13.1. Hai câu hỏi độc lập

1. **Ai đã phát JWT?** → `iss`, signing keys, issuer validation.
2. **Request muốn truy cập tenant nào và principal có quyền tại đó không?** → path/header target, membership/ACL sau authentication.

Ngay cả khi issuer A gắn cứng với tenant A, cần xác định mapping đó trong registry đáng tin, và khi tenant A thay đổi quan hệ với issuer cần cập nhật có kiểm soát.

### 13.2. Nếu route quyết định issuer?

Một số kiến trúc có hợp đồng “`/tenants/a/**` chỉ chấp nhận issuer A”. Có thể chọn manager theo path nếu routing được thiết kế kỹ, nhưng **phải verify token `iss` là issuer A**, và nên kiểm tra path tenant với membership sau xác thực.

`JwtIssuerAuthenticationManagerResolver` đặc biệt hữu ích khi chọn manager theo **`iss`** thay vì path; hai cách có trade-off, không phải phép thay thế security boundary.

## 14. Audience, scope và issuer-specific authorities

Một tenant có thể dùng scope:

~~~text
orders.read
orders.write
```

và tenant khác dùng:

~~~text
read:orders
manage:orders
```

Không tự quy đổi tất cả thành cùng một quyền mà không có contract.

### 14.1. Scope mapping mặc định

Với JWT có:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security thường chuyển thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
```

Rule:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

chỉ kiểm tra authority đã có, không tự hiểu tenant nào hoặc order nào.

### 14.2. Tùy chỉnh per-issuer converter

Nếu AS B trả `roles` thay `scope`, có thể cấu hình `JwtAuthenticationConverter` riêng trên **`JwtAuthenticationProvider` của B**. Nhưng quyền mới chỉ được sinh từ claim mà AS B **có thẩm quyền cấp cho orders-api**; không map email/username/client tự khai thành admin.

Ví dụ ý tưởng:

~~~java
JwtAuthenticationProvider provider =
    new JwtAuthenticationProvider(decoder);

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

// Chỉ dùng converter nếu mapping claims được kiểm soát.
provider.setJwtAuthenticationConverter(converter);
~~~

`JwtAuthenticationConverter` có defaults phù hợp với OAuth scopes; claim roles/phân quyền riêng cần cấu hình converter/`JwtGrantedAuthoritiesConverter` đúng version. Đừng thay đổi converter để “chữa” token thiếu quyền thực.

### 14.3. Per-issuer role names có thể trùng nhưng nghĩa khác

Issuer A `ROLE_ADMIN` có thể là quản trị realm A; issuer B `ROLE_ADMIN` là quản trị một portal khác. Không được xem hai chuỗi đó như quyền quản trị **toàn Resource Server** nếu không có role catalog/policy cho phép.

Một authority **chỉ có ý nghĩa trong context nguồn đã được tin và application policy**.

## 15. Principal canonical identity trong multi-issuer

Sau khi `JwtDecoder` xác minh thành công, có thể lấy:

~~~java
Jwt jwt = authenticationToken.getToken();

String issuer = jwt.getIssuer().toString();
String subject = jwt.getSubject();
~~~

Nếu business data dùng khóa `user-42` mà bỏ issuer, user `user-42` của issuer B có thể bị nhầm với user `user-42` của issuer A.

Nên tạo domain identity:

~~~java
public record ExternalPrincipalId(
    String issuer,
    String subject
) {}
~~~

và một service nội bộ ánh xạ `(issuer, subject)` tới `InternalUserId` đã kiểm soát.

**Không** dùng email/username làm primary owner key trong multi-issuer trừ khi có quy trình xác minh và liên kết danh tính riêng được phê duyệt.

### 15.1. Cần phân biệt client credentials token

Một JWT từ `client_credentials` có thể đại diện machine application. Nó không tự là human user hoặc tenant admin. Phải có policy cho subject/client type và OAuth grant profile, không mặc định chỉ cần `sub` tồn tại là có quyền user.

### 15.2. `tenant_id` do AS cấp cũng cần contract

Nếu JWT đã verify và chứa `tenant_id`, claim đó có thể đáng tin ở mức **“AS đã phát biểu điều này”**. Nhưng Resource Server phải biết AS có thực sự quản trị membership cho tenant đó không. Nếu tenant entitlement được quản lý tại database riêng, JWT claim chỉ là một tín hiệu, không phải sự cho phép tuyệt đối.

## 16. Quyền trên tài nguyên vẫn phải được kiểm tra sau authentication

Giả sử request:

~~~http
GET /api/tenants/tenant-a/orders/order-9001 HTTP/1.1
Authorization: Bearer <jwt-from-trusted-issuer-a>
~~~

Khi resolver và decoder thành công, Spring Security đã biết token do issuer A hợp lệ phát hành. Nhưng API còn phải hỏi:

~~~text
(issuer A, subject user-42)
       |
       +-- Có SCOPE_orders.read?
       |
       +-- Có membership trong tenant-a?
       |
       +-- order-9001 có thuộc tenant-a?
       |
       +-- Subject có quyền xem order này?
       |
       +-- Order có trạng thái/field access constraints không?
```

Nếu không kiểm tra tenant/owner trong query, user có thể đoán order ID để truy cập order của người khác: lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

### 16.1. Rule HTTP chỉ là lớp đầu

~~~java
.requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Rule này không quyết định user có quyền vào tenant cụ thể. Path matcher và wildcard chỉ mô tả các route cần scope đọc.

### 16.2. Service policy minh họa

~~~java
// Pseudocode: các type/repository thuộc ứng dụng.
Order order = orderRepository
    .findByIdAndTenantId(orderId, requestedTenant)
    .orElseThrow(NotFoundException::new);

ExternalPrincipalId actor =
    new ExternalPrincipalId(
        verifiedJwt.getIssuer().toString(),
        verifiedJwt.getSubject()
    );

if (!orderPolicy.canRead(actor, order)) {
    throw new AccessDeniedException("Forbidden");
}

return toDto(order);
~~~

`Order`, `NotFoundException`, `orderPolicy` và `toDto` là domain abstractions minh họa. `verifiedJwt` là JWT **đã được Resource Server xác minh**, không phải dữ liệu raw decode trước authentication.

## 17. Vấn đề parse JWT hai lần

Spring Security documentation nhắc tới trade-off của resolver theo claim `iss`: JWT có thể được **parse một lần để đọc issuer nhằm chọn manager**, rồi **parse/verify tiếp trong `JwtDecoder`**.

~~~text
JWT
 |
 +-- Parse claims lần 1 để tìm iss (routing, CHƯA VERIFIED)
 |
 +-- Chọn AuthenticationManager cho issuer trusted
 |
 +-- JwtDecoder parse + verify + validate lần 2
```

Đây là điểm chi phí parser bổ sung, **không phải** framework xác minh chữ ký hai lần theo mặc định.

### 17.1. Có nên tự bỏ lần parse đầu?

Đừng vội viết parser/decoder tùy chỉnh chỉ để tiết kiệm vài phép xử lý khi chưa đo latency. So với network JWKS fetch, DB authorization và business processing, overhead parser có thể không là nút thắt chính.

Spring Security docs có hướng nâng cao dùng Nimbus **`JWTClaimsSetAwareJWSKeySelector`**, giúp chọn JWK source theo claim set trong quá trình xử lý JWT. Nhưng thiết kế đó cần:

- Trusted tenant/issuer repository.
- JWK selector theo tenant đã được kiểm soát.
- `JWTProcessor` được cấu hình đúng.
- Tenant-aware issuer validator, ngoài các defaults.
- Kiểm tra chữ ký và token claims chính xác.
- Test parsing, unknown issuer, key rotation và cross-issuer attacks.

**Đây không phải một đoạn code nên copy một nửa.** Nếu đổi key selector mà quên issuer validator hoặc dùng JWKS URL tính trực tiếp từ untrusted `iss`, ta có thể làm giảm bảo mật dù parse ít hơn.

### 17.2. Khi nào dùng giải pháp key selector nâng cao?

Có thể cân nhắc khi:

- Nhiều issuers làm số lần parse trở thành chi phí đo được.
- Cần quản lý JWKS theo registry tập trung.
- Team có khả năng duy trì các cấu phần Nimbus và validators.
- Có integration tests chứng minh trust boundary sau khi tối ưu.

Đối với đa số dự án, **`JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` hoặc registry manager** dễ review và ít rủi ro hơn.

## 18. SSRF và lạm dụng tài nguyên: không chỉ là chữ ký

Issuer discovery có thể tạo HTTP calls tới:

~~~text
https://issuer/.well-known/openid-configuration
https://issuer/.well-known/oauth-authorization-server
https://issuer/jwks
```

Các endpoint và fallback cụ thể tùy decoder và profile; không tự hardcode tất cả đường dẫn cho mọi AS.

Nếu caller có thể điều khiển issuer URL để server gọi mạng, tác động có thể gồm:

- SSRF vào localhost, metadata IP hoặc internal services.
- Scan mạng nội bộ qua timing/errors.
- DNS rebinding, redirect tới host không mong muốn.
- Kéo dài connection timeout, cạn connection pool.
- Fetch JWKS response cực lớn gây resource exhaustion.
- Thundering herd khi nhiều issuers/unknown keys được yêu cầu.
- Token từ một AS tự dựng có chữ ký “hợp lệ” với chính key của attacker.

### 18.1. Các lớp phòng vệ

1. **Allowlist exact issuer** từ nguồn tin cậy.
2. Cấu hình **trusted JWK Set URI** per issuer nếu cần, không derive từ arbitrary caller input.
3. Ưu tiên HTTPS, TLS validation và hostname verification.
4. Kiểm soát DNS/egress/redirect/proxy theo hạ tầng.
5. Timeout và connection pool có giới hạn.
6. Giới hạn số issuers được onboarding, size JWKS, lượng key và refresh.
7. Không log token raw/credential khi lỗi.
8. Test unknown issuer **không tạo network call** tới host của attacker.
9. Tách canonical issuer khỏi hostname kết nối JWKS nội bộ.
10. Không trộn cache public keys giữa issuers.

**Chỉ kiểm tra `issuer.startsWith("https://")` không đủ an toàn.** HTTPS không biến bất kỳ domain nào thành một Authorization Server mà API được phép tin.

## 19. Canonical issuer và reverse proxy

Trong triển khai đa tenant, AS có thể nằm sau ingress hoặc reverse proxy:

~~~text
Issuer trong JWT:
  https://login.example.com/realms/tenant-a

URI JWKS nội bộ:
  https://keys.internal.example/realms/tenant-a/certs
```

Điều đó có thể hợp lệ khi control plane đã quản lý mapping issuer → JWKS URL và TLS/egress được bảo vệ.

Nhưng:

- `iss` cần so khớp **canonical external issuer** theo contract.
- `jwk-set-uri` có thể là network address nội bộ khác host.
- Không lấy issuer mới từ `Host` header của client.
- Không đổi `JwtValidators.createDefaultWithIssuer(...)` sang hostname nội bộ chỉ để tránh lỗi metadata.
- Nếu AS phát `iss` sai do proxy configuration, sửa AS/proxy configuration thay vì bỏ issuer validation.

**Issuer và JWK Set URI phục vụ hai mục đích khác nhau.**

## 20. Token từ issuer đáng tin vẫn có thể không dành cho API

Ví dụ một AS phát:

~~~json
{
  "iss": "https://idp-a.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["frontend-client"],
  "scope": "openid profile"
}
~~~

Token hoặc ID token này có thể hợp lệ trong một flow khác, nhưng **không** phải access token dành cho `orders-api`.

Nếu API chấp nhận nó chỉ vì issuer được allowlist, sẽ mắc lỗi **token substitution/cross-JWT confusion**.

Cần:

- Verify token là access token theo profile contract.
- Check `aud` đúng Resource Server.
- Check `iss` và signature đúng.
- Enforce allowed JWS algorithms/key types.
- Validate `exp`/`nbf`, clock skew hợp lý.
- Không dùng ID token của OIDC Client làm API Bearer credential.
- Nếu token type cần `at+jwt`, cấu hình type/profile validator tương ứng theo framework version.

### 20.1. `JwtValidators.createDefaultWithIssuer(...)` không tự hiểu toàn bộ policy riêng

Validator mặc định giúp kiểm tra các claim cốt lõi như issuer/timestamp theo cấu hình, nhưng **không mặc nhiên biết audience nghiệp vụ** của từng API hoặc tenant-specific role policy.

Với custom decoder, áp dụng `DelegatingOAuth2TokenValidator` để kết hợp issuer defaults với audience và các validators khác do contract quy định.

## 21. `kid` có thể trùng giữa hai issuers

JWT header có:

~~~json
{
  "alg": "RS256",
  "kid": "main-key"
}
~~~

Issuer A và issuer B hoàn toàn có thể cùng dùng `kid=main-key` nhưng public keys khác nhau. `kid` **không phải định danh global duy nhất**.

Sai:

~~~text
Cache key = kid
"main-key" -> public key dùng cho mọi issuer
```

Đúng về ý tưởng:

~~~text
Cache key = trusted issuer / configured JWK source + kid + key metadata
```

Thư viện Nimbus/Spring Security quản lý key selection theo JWK source. Nếu tự viết cache/shared key store, phải gắn tenant/issuer namespace, không để token B được verify bằng key A chỉ vì cùng `kid`.

### 21.1. Không lấy `jku` từ JWT header làm source tin cậy

Header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "x",
  "jku": "https://attacker.example/jwks"
}
~~~

`jku`/`x5u` là dữ liệu bên trong token chưa được tin. Không để chúng tự điều khiển việc gọi JWKS endpoint; dùng key source đã được phê duyệt trong manager registry.

## 22. Kiểm thử: allowlist issuer là một security boundary

Để xác minh nhiều issuer thật sự hoạt động an toàn, hãy tạo **test signing keys riêng** cho A/B và một issuer C chưa được tin.

### 22.1. Ma trận kiểm thử

| Kịch bản | Kỳ vọng |
|---|---|
| Token A có chữ ký A, `iss=A`, `aud=orders-api`, chưa hết hạn | Xác thực thành công; HTTP policy còn quyết định |
| Token B có chữ ký B, `iss=B`, `aud=orders-api` | Xác thực thành công nếu B đã được trust |
| Token C do attacker tự ký, `iss=C` | Bị từ chối, không fetch metadata/JWKS của C |
| Token có `iss=A`, chữ ký bằng key B | Bị từ chối |
| Token có `iss=B`, chữ ký bằng key A | Bị từ chối |
| Token A có chữ ký đúng nhưng `aud=billing-api` | Bị từ chối khi audience validator bật |
| Token A hết hạn | Bị từ chối |
| Token A với `nbf` ở tương lai ngoài skew | Bị từ chối |
| Token A với `alg` không được phép | Bị từ chối |
| JWT malformed không có `iss` | Bị từ chối |
| `iss` khác đúng một trailing slash | Không match nếu không có đúng entry |
| Issuer A đúng, `SCOPE_orders.read` thiếu | Xác thực có thể thành công, HTTP trả 403 |
| Issuer A và B cùng `sub=user-42` | Không được nhập identity |
| Token issuer A gọi tenant B không có membership | Bị business authorization từ chối |
| Issuer B bị deactivate | Lượt resolve mới bị từ chối |
| Key B mới xuất hiện trong JWKS | Rotation được xử lý theo policy/version |
| AS B timeout khi first request | Không được fail open |

Các kết quả HTTP thực tế phụ thuộc entry point, exception handler và service route, nhưng **security decision** phải đúng.

### 22.2. `MockMvc.with(jwt())` chưa kiểm chứng resolver

Spring Security Test hỗ trợ:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Đây là **mock authenticated JWT**. Nó hữu ích để kiểm tra `hasAuthority`/HTTP authorization, nhưng có thể **bỏ qua hoàn toàn** `JwtIssuerAuthenticationManagerResolver`, việc chọn issuer, chữ ký, discovery/JWKS và validators.

Không dựa vào test trên để tuyên bố “untrusted issuer đã bị từ chối”.

### 22.3. Test thực đi qua Bearer filter

Một integration test đúng mục tiêu cần:

1. Tạo RSA/EC key pair riêng cho issuer A/B.
2. Cho một fake JWKS endpoint A/B trả public key tương ứng.
3. Cấu hình registry với JWKS URLs test đã được duyệt.
4. Ký access token thật với private test keys, set `iss`, `aud`, `exp`.
5. Gửi `Authorization: Bearer <signedJwt>` vào `MockMvc` hoặc HTTP test server.
6. Kiểm tra A/B được xác thực, C bị reject.
7. Kiểm tra `iss=A` nhưng ký bằng key B bị reject.
8. Kiểm tra `aud` sai và expired token bị reject.
9. Đếm HTTP requests tới JWKS server để chứng minh C **không** gây outbound request.
10. Kiểm tra khi B bị disable không có manager mới được chọn.

**Không sử dụng private keys thật của production trong test.** JWKS response test chỉ công bố public key material.

### 22.4. Test unit registry mà không cần mạng

Bạn có thể kiểm tra cơ chế `resolve` bằng một registry/manager giả:

~~~java
AuthenticationManager aManager =
    authentication -> authentication; // Test stub only.

Map<String, AuthenticationManager> allowed = Map.of(
    "https://idp-a.example.com/realms/shop",
    aManager
);

JwtIssuerAuthenticationManagerResolver resolver =
    new JwtIssuerAuthenticationManagerResolver(allowed::get);
~~~

Stub này **chỉ dành cho unit test lựa chọn manager**, không phải implementation dùng production: nó trả authentication mà không verify JWT. Khi kiểm tra trust boundary thực, phải dùng decoder/keys thật trong integration test.

### 22.5. Test dynamic disable

Nếu `registry.deactivateIssuer(B)`, các requests mới dùng token B phải không được chọn manager B. Nhưng với yêu cầu thu hồi ngay cho request đã vào service, cần thêm test theo chính sách lifecycle/concurrency — `remove()` không tự abort mọi request đã authenticated.

## 23. Phân biệt 401, 403 và lỗi cấu hình issuer

| Hiện tượng | Lớp nguyên nhân có thể | Cần kiểm tra |
|---|---|---|
| Không có Bearer token vào private API | Authentication thiếu | Trả 401 theo Bearer entry point |
| JWT `iss` không nằm trong allowlist | Resolver không tìm manager | Từ chối token, không auto-onboard issuer |
| JWT `iss` thiếu hoặc malformed | Không xác định issuer | Token không hợp lệ |
| `iss` đúng nhưng signature sai | Decoder của issuer | JWK key source, algorithm |
| `iss` đúng, chữ ký đúng nhưng `aud` sai | JWT audience validator | Ràng buộc API |
| Token hết hạn | Timestamp validator | `exp`, clock skew |
| Issuer A đang downtime | Discovery/JWKS | Timeout, network, cache, TLS |
| JWT hợp lệ nhưng scope thiếu | HTTP authorization | 403 |
| JWT có scope nhưng target tenant khác | Business authorization | Membership/ownership |
| Token A có `sub` giống B và đọc dữ liệu B | Identity mapping | Namespace `(iss, sub)` |
| Issuer mới chưa được trust | Control plane onboarding | Không thay allowlist bằng runtime untrusted data |
| `kid` mới chưa có trong JWKS | Rotation | AS publication, refresh/cache |

**401** thường là authentication failure; **403** thường là authorization failure sau khi principal đã được xác thực. Network outage/discovery lỗi có thể được handler trình bày khác nhau; không khẳng định tất cả đều có một HTTP status cố định trên mọi Spring Security version.

Để chẩn đoán, phân biệt token invalid với source JWKS unavailable, nhưng tránh tiết lộ chi tiết issuer registry hoặc token nội bộ trong response.

## 24. Nhiều SecurityFilterChain và issuer resolver

Một ứng dụng có thể chứa:

- `/api/**` → Resource Server đa issuer.
- `/admin-ui/**` → browser login/session và CSRF.
- `/actuator/**` → endpoint vận hành theo policy riêng.

Có thể dùng nhiều `SecurityFilterChain`, mỗi chain có `securityMatcher` và thứ tự `@Order`. Trong đó `JwtIssuerAuthenticationManagerResolver` chỉ được gắn vào **chain Resource Server** có yêu cầu Bearer token.

Điểm cần kiểm tra:

- Chain của `/api/**` thực sự được chọn.
- Một chain tổng quát đứng trước không vô tình che API chain.
- `anyRequest().denyAll()` của chain có matcher hẹp **không** bảo vệ các URL nằm ngoài phạm vi chain.
- API không dùng session cookie của UI làm authentication nếu contract yêu cầu bearer-only.
- Không tự chọn decoder theo `Host` header không đáng tin.

`JwtIssuerAuthenticationManagerResolver` không thay việc thiết kế `SecurityFilterChain` hợp lý.

## 25. So sánh `JwtIssuerAuthenticationManagerResolver` và giải pháp thay thế

| Nhu cầu | Giải pháp |
|---|---|
| Một issuer duy nhất | `issuer-uri` / một `JwtDecoder` |
| Nhiều issuers cố định | `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` |
| Nhiều issuers thêm/xóa động | `AuthenticationManagerResolver<String>` + trusted manager registry |
| Mỗi issuer có audience/JWKS/policy khác nhau | Registry với per-issuer `JwtAuthenticationProvider` và validators |
| Tenant phân biệt theo path nhưng cùng issuer | Kiểm tra tenant context/authorization riêng; issuer resolver chưa đủ |
| JWT và opaque token cùng tồn tại | `AuthenticationManagerResolver<HttpServletRequest>` chọn token authentication strategy phù hợp |
| Muốn parse JWT claim ít lần hơn | Nimbus `JWTClaimsSetAwareJWSKeySelector` theo tài liệu, với trust registry và issuer validators |
| Dùng Spring WebFlux | `JwtIssuerReactiveAuthenticationManagerResolver`, không phải Servlet class |
| Chỉ cần phân quyền `orders.read` | `hasAuthority("SCOPE_orders.read")` sau authentication |
| Quyền theo từng order/tenant | Domain/service ACL, membership và dữ liệu hiện tại |

Tránh giải pháp phức tạp nếu một allowlist tĩnh đã đáp ứng. Nhưng khi phải quản lý lifecycle tenant, quyền disable, audience khác nhau và nhiều key sources, một registry có governance rõ ràng hữu ích hơn hardcode logic trong controller.

## 26. Checklist triển khai an toàn

Trước khi đưa multi-issuer Resource Server vào production:

- [ ] Tập trusted issuers được cấu hình từ nguồn có thẩm quyền, không từ JWT/header client.
- [ ] Mỗi issuer có canonical URL chính xác, không tin rộng theo host suffix.
- [ ] Resolver từ chối issuer lạ **trước khi tạo manager/JWKS network call**.
- [ ] Decoder verify JWS signature bằng JWK source tương ứng đúng issuer.
- [ ] Allowed JWS algorithms được giới hạn theo AS contract.
- [ ] `iss` được validate lại **sau chữ ký**, không chỉ parse trước.
- [ ] `aud` được kiểm tra cho Resource Server này.
- [ ] `exp`, `nbf`, clock skew và token type/profile có chính sách rõ.
- [ ] Role/scope mapping không tự tạo quyền admin từ username/email/group lạ.
- [ ] Identity mapping dùng issuer + subject hoặc canonical internal ID đáng tin.
- [ ] Business tenant membership, owner và object-level policy được thực thi.
- [ ] Issuer onboarding có xác thực admin, audit, URL validation và egress restrictions.
- [ ] Issuer deactivation có cơ chế cập nhật trên các replicas và test request in-flight.
- [ ] JWKS cache/rotation được monitor, không trộn `kid` giữa issuers.
- [ ] Outbound HTTPS, TLS, timeout, retry limits và metadata URLs được kiểm soát.
- [ ] Test token issuer lạ, sai chữ ký, sai audience, hết hạn, thiếu scope, sai tenant.
- [ ] Test không có outbound call tới issuer attacker.
- [ ] Không ghi raw JWT, private key, Authorization header hoặc secret vào log.
- [ ] Đã biết rõ Servlet hay WebFlux để chọn đúng resolver class.
- [ ] Có fallback SecurityFilterChain cho những paths nằm ngoài API matcher.

## 27. Những hiểu nhầm thường gặp

**“`iss` ở JWT payload là dữ liệu có chữ ký, nên đọc nó trước verify vẫn tin được.”** Sai. Nó chỉ được bảo vệ *sau khi* chữ ký thực sự được xác minh với đúng khóa đáng tin.

**“Nếu issuer cung cấp JWKS HTTPS hợp lệ thì chắc chắn Resource Server phải tin issuer đó.”** Sai. HTTPS đảm bảo kết nối đến domain; không chứng minh domain được tổ chức phê duyệt cấp token cho API.

**“`JwtIssuerAuthenticationManagerResolver` tự tin mọi issuer trong token.”** Sai khi cấu hình đúng; phải có trusted issuer list hoặc strategy chỉ trả managers đã được phê duyệt.

**“Dùng `fromTrustedIssuers(issuer -> true)` vẫn an toàn vì JWT có chữ ký.”** Sai. Kẻ tấn công có thể tự dựng AS và ký token bằng khóa của mình.

**“Cứ có chữ ký hợp lệ là không cần check `aud`.”** Sai. Token có thể dành cho API khác.

**“Hai token cùng `sub` là cùng người.”** Không nếu issuers khác nhau và chưa có identity linking.

**“Issuer và tenant luôn một-một.”** Không. Một issuer có thể phục vụ nhiều tenants; một tenant có thể tin nhiều issuers.

**“`tenant_id` trong URL chứng minh membership.”** Sai. Nó là target do client chọn.

**“Mọi token có `SCOPE_orders.read` đều được xem mọi order.”** Sai. Cần object-level authorization.

**“`kid` là duy nhất toàn cầu.”** Sai. Nó có thể trùng giữa issuers; key lookup phải theo trusted issuer context.

**“JWT header `jku` là nơi Resource Server nên fetch key.”** Không mặc định, vì caller có thể chỉ tới URL attacker.

**“Thêm tenant động nghĩa là đọc issuer từ JWT rồi auto-register.”** Sai. Add/remove phải qua trusted control plane.

**“Disable issuer bằng cách remove map entry lập tức dừng mọi request đã authenticated.”** Không. Còn request in-flight, replicas và caches.

**“Resolver tải tất cả AS ngay khi start ứng dụng.”** Không với cơ chế lazy trusted issuers được tài liệu mô tả. Nhưng request đầu tiên có thể gặp network dependency.

**“Một bài test `MockMvc.with(jwt())` chứng minh untrusted issuer bị reject.”** Không. Nó mock authentication và có thể bỏ qua resolver/decoder.

**“Muốn tránh parse hai lần thì cứ đọc payload và bỏ decoder.”** Sai. Tối ưu parsing không được đánh đổi chữ ký và issuer validation.

**“Đổi issuer validator theo JWK hostname nội bộ là đúng.”** Không. Canonical issuer và đường mạng lấy public key là hai thứ khác nhau.

## 28. Câu hỏi tự kiểm tra

**1.** `JwtIssuerAuthenticationManagerResolver` dùng để làm gì?

> Chọn cơ chế JWT authentication theo claim issuer của bearer token trong Servlet Resource Server đa issuer.

**2.** Vì sao `iss` trước khi verify không đáng tin?

> Vì caller có thể tự thay payload; resolver chỉ nên dùng nó để tra **trusted manager** đã được phê duyệt.

**3.** Nếu JWT khai `iss=https://attacker.example`, Resource Server nên làm gì?

> Từ chối vì issuer không thuộc allowlist, không auto-discover hoặc fetch JWKS của attacker.

**4.** Cách tạo resolver với danh sách tĩnh trên Spring Security 6.2+?

> `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(issuerA, issuerB)`.

**5.** Vì sao các constructor nhận `String...`/`Collection` không còn được ưu tiên?

> Chúng deprecated từ 6.2; factory `fromTrustedIssuers` là cách được khuyến nghị trong version hiện đại.

**6.** Đã kiểm tra `iss`, còn cần `aud` không?

> Có. Issuer nói ai phát token; audience nói token dành cho API nào.

**7.** Token có `iss=A` nhưng signature key B có qua được không?

> Không. Manager A phải xác minh bằng key source của A và reject chữ ký sai.

**8.** Hai issuers đều có `sub=user-42` thì có phải cùng user?

> Không mặc định. Cần namespace issuer hoặc identity mapping có thẩm quyền.

**9.** Có thể dùng một `ConcurrentHashMap<String,AuthenticationManager>` cho tenants động không?

> Có, nếu các entries chỉ được thêm từ trusted onboarding và per-issuer manager/validators được tạo đúng. Không tự đăng ký từ request.

**10.** Nếu remove manager B, mọi hoạt động của B đã dừng ngay chưa?

> Không bảo đảm cho request đang xử lý, cache hoặc replicas khác. Cần lifecycle policy.

**11.** `JwtIssuerAuthenticationManagerResolver` có tự thực thi quyền trên từng order không?

> Không. Nó phục vụ authentication; ownership/tenant phải kiểm tra tại business authorization layer.

**12.** Vì sao không chọn khóa chỉ theo `kid`?

> Vì `kid` không duy nhất toàn cầu và các issuers có thể dùng trùng tên key.

**13.** Tại sao docs nhắc JWT được parse hai lần?

> Lần đầu đọc `iss` để route; lần sau decoder thực hiện xác minh/chuyển thành `Jwt` đã validate.

**14.** Trong WebFlux dùng resolver nào?

> `JwtIssuerReactiveAuthenticationManagerResolver` cùng Reactive security APIs.

**15.** Test nào chứng minh issuer lạ không gây network call?

> Integration test dùng signed JWT của issuer chưa được trust, JWKS/metadata stub đếm requests và real bearer authentication path.

## 29. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuers, dynamic managers, parsing một/hai lần.
- [Spring Security — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): `fromTrustedIssuers`, constructors và `resolve`.
- [Spring Security 6.5 — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): mốc phiên bản `fromTrustedIssuers` và constructor deprecations.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWK discovery, JWT validators, scopes.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): JWK Set builder, algorithms và validator.
- [Spring Security — JwtAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html): `JwtDecoder` và tạo `JwtAuthenticationToken`.
- [Spring Security — JwtDecoders API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoders.html): tạo decoder từ trusted issuer metadata.
- [Spring Security — WebFlux Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): counterpart `JwtIssuerReactiveAuthenticationManagerResolver`.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): scope authorization tại HTTP boundary.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `nbf`.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWK Set.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience/algorithm và cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token profile của OAuth access token JWT.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer authentication, challenge và lỗi.

**Kết luận:** `JwtIssuerAuthenticationManagerResolver` giúp Resource Server **định tuyến JWT authentication theo issuer** khi có nhiều tenant/Authorization Servers. Nhưng `iss` dùng để định tuyến ban đầu vẫn là dữ liệu **chưa được xác minh**; chỉ **tập issuers được phê duyệt trước** mới được phép sinh/tìm manager. Sau khi chọn manager, phải **xác minh chữ ký với JWK source đúng issuer và kiểm tra `iss`, `aud`, thời hạn và token profile**. Cuối cùng, tenant membership, quyền trên từng order và identity namespace là trách nhiệm của business authorization — không được bỏ qua chỉ vì JWT đến từ một issuer nằm trong allowlist.
