# Chọn AuthenticationManager dựa trên yêu cầu và cấu hình được quản lý

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một ứng dụng có thể bảo vệ nhiều nhóm API, với nhiều loại credential và nhiều nguồn xác thực khác nhau. Ví dụ cùng một ứng dụng nhận **JWT access token** do một Authorization Server phát hành cho đối tác, nhận **opaque access token** cần introspection cho API nội bộ, đồng thời cung cấp giao diện web dùng session hoặc một nhóm endpoint quản trị yêu cầu mTLS.

Ở đây có hai vấn đề riêng: **cơ chế nào phải xử lý request này?** và **sau khi chọn cơ chế đó, credential có thực sự hợp lệ và được phép dùng ở resource này không?** Spring Security có các điểm mở rộng như `AuthenticationManagerResolver<HttpServletRequest>` và, trong WebFlux, `ReactiveAuthenticationManagerResolver<ServerWebExchange>` để chọn manager phù hợp với từng request. Nhưng resolver **không phải** bộ xác thực độc lập; nó chỉ trả về thành phần sẽ thực hiện authentication.

Nguyên tắc bảo mật xuyên suốt:

> **Request cung cấp dữ liệu để chọn một AuthenticationManager trong tập cấu hình được quản lý; AuthenticationManager được chọn phải tự xác minh credential theo toàn bộ hợp đồng của cơ chế đó. Khi thất bại, không fallback sang một cơ chế lỏng hơn để thử vận may.**

Điều này khác rất xa cách triển khai nguy hiểm: “Đọc `iss` hoặc `alg` từ JWT chưa xác minh, tạo decoder/JWKS URL ngay từ chuỗi ấy; nếu JWT không hợp lệ thì thử introspection; nếu vẫn lỗi thì đọc cookie hoặc header `X-User`”.

Bài học giải thích chi tiết cách chọn manager theo **HTTP request**, cấu hình tin cậy cho JWT/opaque/BASIC/session, mối quan hệ với nhiều `SecurityFilterChain`, ranh giới giữa **resolver / manager / provider**, cơ chế fail-closed, WebFlux, multi-tenant, kiểm thử và vận hành.

## 1. Vì sao một Resource Server cần nhiều cơ chế xác thực?

Xét hệ thống Orders Platform:

| Vùng tài nguyên | Credential mong đợi | Nguồn xác thực | Chính sách ví dụ |
|---|---|---|---|
| `/api/partners/**` | `Authorization: Bearer <JWT>` | JWT decoder cho issuer đối tác đã đăng ký | `aud=orders-partner-api`, scopes `orders.read`/`orders.write` |
| `/api/internal/**` | `Authorization: Bearer <opaque-token>` | Introspection endpoint nội bộ | `aud=orders-internal-api`, introspection `active=true` |
| `/admin/**` | Phiên browser sau login hoặc mTLS theo kiến trúc | Web login provider / certificate validation | Vai trò quản trị, session/CSRF hoặc client certificate policy |
| `/actuator/health` | Không cần Bearer token nếu chỉ lộ health tối thiểu | `permitAll` theo deployment | Không tiết lộ dữ liệu nhạy cảm |

Các credential đều có thể biểu diễn một danh tính, nhưng **không có nghĩa** một token của `/api/partners/**` được dùng ở `/api/internal/**`. Hai API có thể cùng tên scope `orders.read` nhưng audience, issuer, client và ranh giới tenant khác nhau.

### 1.1. Bốn việc không được trộn thành một

```mermaid
flowchart TD
    R["HTTP request + credential"] --> S["SecurityFilterChain selection<br/>theo đường dẫn/điều kiện"]
    S --> T["Authentication mechanism/filter<br/>trích xuất credential"]
    T --> U["AuthenticationManagerResolver<br/>chọn manager từ registry"]
    U --> V["AuthenticationManager / Provider<br/>xác minh credential"]
    V --> W{"Token/credential hợp lệ?"}
    W -->|"Không"| X["Authentication failure<br/>không thử cơ chế kém an toàn"]
    W -->|"Có"| A["Authentication + authorities"]
    A --> B{"HTTP/method rule được phép?"}
    B -->|"Không"| C["403 / access denied"]
    B -->|"Có"| D["Domain authorization<br/>owner/tenant/state"]
    D --> E["Thao tác nghiệp vụ nếu được phép"]
```

Vai trò:

- **`SecurityFilterChain`:** quyết định filter nào áp dụng cho request; khi có nhiều chains, Spring Security chọn chain phù hợp theo thứ tự.
- **Authentication filter:** lấy credential từ HTTP request, ví dụ Bearer token từ `Authorization`.
- **`AuthenticationManagerResolver`:** chọn **manager** từ một request/context đáng tin cậy theo policy.
- **`AuthenticationManager`:** xác thực Authentication request; có thể ủy quyền cho `AuthenticationProvider`.
- **`AuthorizationManager` hoặc method security:** quyết định truy cập sau khi Authentication đã được xác minh.
- **Domain policy:** kiểm tra owner, tenant, trạng thái đơn hàng và quyền trên đối tượng.

Một `AuthenticationManagerResolver` chọn đúng manager không tự tạo ra `200 OK`. Credential còn phải vượt qua chữ ký/introspection, issuer/audience, scope và quy tắc nghiệp vụ.

## 2. `AuthenticationManager`, `AuthenticationProvider` và `AuthenticationManagerResolver`

### 2.1. `AuthenticationManager` thực hiện xác thực

API Servlet:

```java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;

public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
}
```

Đây là chữ ký minh họa; hãy import interface do Spring Security cung cấp, không định nghĩa lại. Đầu vào là một `Authentication` **chưa được xác minh**, ví dụ `BearerTokenAuthenticationToken`. Đầu ra là `Authentication` đã được xác thực hoặc một `AuthenticationException` tương ứng khi thất bại.

Các implementation thường gặp:

- `ProviderManager`: quản lý danh sách `AuthenticationProvider`.
- Một lambda/adapter chuyển lời gọi `authenticate` đến một provider cụ thể.
- Một manager do framework cấu hình cho form login, HTTP Basic hoặc cơ chế riêng.

### 2.2. `AuthenticationProvider` xử lý một loại Authentication

Ví dụ:

| Provider | Đầu vào thường gặp | Cách chứng minh |
|---|---|---|
| `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | `JwtDecoder` xác minh chữ ký và validators |
| `OpaqueTokenAuthenticationProvider` | `BearerTokenAuthenticationToken` | `OpaqueTokenIntrospector` hỏi Authorization Server |
| `DaoAuthenticationProvider` | `UsernamePasswordAuthenticationToken` | UserDetails/PasswordEncoder |
| Provider tùy chỉnh có kiểm soát | Loại Authentication riêng | Hợp đồng xác thực riêng, không tin caller tự khai |

Không nên nhầm **“provider hỗ trợ loại Authentication”** với **“provider chịu trách nhiệm xác thực token profile của endpoint”**. JWT và opaque provider đều có thể cùng xử lý `BearerTokenAuthenticationToken`, nhưng không có lý do an toàn để tùy tiện thử cả hai cho mỗi Bearer string.

### 2.3. `AuthenticationManagerResolver` chọn manager

Interface Servlet tổng quát:

```java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import jakarta.servlet.http.HttpServletRequest;

AuthenticationManagerResolver<HttpServletRequest> resolver =
    request -> {
        // Chọn một manager được cấu hình sẵn.
        return selectTrustedManager(request);
    };
```

`AuthenticationManagerResolver<C>` về bản chất có phương thức `resolve(C context)` trả về một `AuthenticationManager`. Nó không nhận password/JWT rồi tự kiểm chữ ký. Nó quyết định **nên gọi manager nào** trên request đó.

Trong WebFlux có interface tương đương về ý nghĩa nhưng bất đồng bộ:

```java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> Mono.just(selectedReactiveManager);
```

`resolve(...)` trả một `Mono<ReactiveAuthenticationManager>`, cho phép lựa chọn manager từ nguồn bất đồng bộ nếu kiến trúc yêu cầu, nhưng **không** cho phép sử dụng dữ liệu chưa xác thực như một bằng chứng cấp quyền.

### 2.4. Manager resolver khác `ProviderManager` nhiều providers

`ProviderManager` có thể chứa nhiều providers và lần lượt tìm provider phù hợp với một Authentication token. Trong khi đó resolver lựa chọn **một manager theo request context**.

```text
ProviderManager([Provider A, Provider B]):
  Cùng Authentication đầu vào được xử lý theo chuỗi provider.

AuthenticationManagerResolver(request):
  Chọn Manager A cho route A.
  Chọn Manager B cho route B.
  Mỗi manager kiểm tra đúng credential theo contract của nó.
```

Với JWT và opaque cùng xuất phát từ Bearer, dùng resolver theo route/hợp đồng có thể giúp tránh logic “JWT failed → opaque fallback” không mong muốn. Nếu cố dùng một `ProviderManager` với cả `JwtAuthenticationProvider` và `OpaqueTokenAuthenticationProvider`, phải hiểu chính xác thứ tự, `supports` và cách exception/parent manager hoạt động; không mặc định mọi token sẽ được định tuyến an toàn theo kiểu của nó.

## 3. Chọn manager dựa trên cái gì?

Một resolver có thể quan sát HTTP request, nhưng **mọi dữ liệu của request không có cùng mức tin cậy**.

| Dữ liệu dùng chọn manager | Có thể sử dụng? | Điều kiện |
|---|---|---|
| **Route/path đã match** | Thường phù hợp | Dùng matching/normalization nhất quán với security chain, map tới cấu hình được quản lý |
| HTTP method + route | Có | Endpoint policy phải rõ; không chọn auth nhẹ hơn chỉ vì GET |
| Server-defined endpoint group | Rất phù hợp | Được xác định từ cấu hình/routing bên server |
| Host/subdomain | Có nhưng cần thận trọng | Phải kiểm soát Host/forwarded headers và trusted proxy |
| Tenant từ URL | Có để chọn từ registry | Tenant slug không tự chứng minh quyền của caller |
| `iss` trong JWT chưa verify | Chỉ là **hint** | Allowlist issuer; decoder cuối phải xác minh chữ ký + `iss` + audience |
| `kid`, `alg`, `jku` trong JWT header | Không đủ làm trust decision | Không tải key tùy ý; ràng buộc key/alg với issuer được chọn |
| Header `X-Auth-Mechanism: opaque` từ client | Không đáng tin làm policy duy nhất | Dễ bị client tùy ý thay đổi |
| Cookie session | Có trong browser chain | Không cho API bearer thuần vô tình sử dụng session |
| mTLS client identity đã được TLS terminator xác thực | Có theo hợp đồng | Phải có ranh giới proxy đáng tin; không tin header certificate do client tự gửi |

### 3.1. Selection là định tuyến, không phải chứng minh credential

Ví dụ:

```http
GET /api/partners/orders/123 HTTP/1.1
Authorization: Bearer attacker-controlled-string
```

Resolver có thể chọn **partner JWT manager** vì path bắt đầu bằng `/api/partners/`. Nhưng điều đó **không có nghĩa** token là JWT hợp lệ, được cấp bởi partner issuer hoặc có scope read. JWT manager phải tự xác minh mọi điều kiện.

Ngược lại, nếu request gọi `/api/internal/orders/123`, resolver chọn **internal opaque manager**. Một JWT đối tác dù chữ ký hợp lệ ở issuer đối tác cũng không mặc nhiên được thử ở internal AS.

### 3.2. Không cho client tự chọn chính sách xác thực yếu hơn

Anti-pattern:

```java
// KHÔNG LÀM: caller quyết định dùng manager nào.
String mode = request.getHeader("X-Auth-Mode");
if ("legacy".equals(mode)) {
    return permissiveLegacyManager;
}
return strictJwtManager;
```

Attacker chỉ cần gửi `X-Auth-Mode: legacy` để đi vào cơ chế ít ràng buộc hơn. Nếu nhiều cơ chế là yêu cầu hợp lệ, việc lựa chọn cần dựa vào **tập route/chính sách do server kiểm soát**, hoặc một ràng buộc token profile đáng tin đã được xác minh bởi manager tương ứng.

### 3.3. Không tạo AuthenticationManager từ input chưa tin cậy

Anti-pattern:

```java
String issuer = request.getParameter("issuer");
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
return new JwtAuthenticationProvider(decoder)::authenticate;
```

Điều này có thể khiến server thực hiện metadata/JWKS discovery đến URL attacker cung cấp, tạo nguy cơ **SSRF, DoS và trust injection**. Trusted manager phải lấy từ **issuer/endpoint đã được quản lý**, không khởi tạo cấu hình tin cậy theo URL tùy ý trên mỗi request.

## 4. Hai chiến lược kiến trúc: nhiều chains hay một resolver?

Có hai cách tổ chức phổ biến. Cả hai có thể phù hợp; chọn theo số nhóm tài nguyên và mức độ tách biệt authentication policy.

### 4.1. Nhiều `SecurityFilterChain` cho các vùng độc lập

```text
/api/partners/**  -> chain A -> JWT resource server
/api/internal/**  -> chain B -> opaque token resource server
/admin/**         -> chain C -> browser form login / session
/...              -> fallback chain -> deny
```

Ưu điểm:

- Mỗi chain có bộ filters, CSRF/session policy, entry point và authentication rõ.
- Dễ phân tách browser session với stateless Bearer API.
- Không cần tự viết resolver nếu mỗi route group chỉ dùng một cơ chế.

Nhược điểm:

- Nhiều chains cần quản lý thứ tự `@Order` và `securityMatcher` chính xác.
- Route mới có thể rơi vào chain khác hoặc không được bảo vệ nếu thiếu fallback.
- Cấu hình lặp nếu các vùng API có chung phần lớn rules.

### 4.2. Một Bearer chain với `AuthenticationManagerResolver`

```text
/api/** -> một SecurityFilterChain
            |
            v
       BearerTokenAuthenticationFilter
            |
            v
       AuthenticationManagerResolver
         /                     \
        /                       \
   /api/partners/**       /api/internal/**
     JWT manager           Opaque manager
        \                       /
         \                     /
          v                   v
             Authentication
                   |
                   v
       HTTP/method/domain authorization
```

Ưu điểm:

- Một khu vực API stateless sử dụng chung Bearer filter.
- Route chọn manager từ registry có kiểm soát.
- Phù hợp khi nhiều issuers/tenants/cơ chế Bearer dùng chung endpoint surface nhưng có điều kiện chọn rõ.

Nhược điểm:

- Resolver trở thành phần cấu hình nhạy cảm; route coverage phải đầy đủ.
- Lỗi chọn manager có thể làm credential được xác minh sai context.
- Các cơ chế **không phải Bearer** (Basic, form login, mTLS) vẫn cần filters/chain phù hợp; resolver Bearer không tự hỗ trợ mọi loại credential.

### 4.3. Quy tắc quyết định

| Nhu cầu | Hướng thường hợp lý |
|---|---|
Browser session và API Bearer | **Tách SecurityFilterChain** vì session/CSRF/entry points khác nhau |
| Hai nhóm API đều dùng Bearer nhưng JWT và opaque khác nhau | Nhiều chains **hoặc** Bearer resolver theo route |
| Nhiều issuer JWT trong cùng API | `JwtIssuerAuthenticationManagerResolver` hoặc trusted manager registry |
| Nhiều tenant với policy chọn dựa route | Custom resolver đọc route → trusted registry |
| Một route cho phép Basic hoặc Bearer theo hợp đồng | Thiết kế nhiều authentication filters rõ ràng; không mặc định Bearer resolver sẽ xử lý Basic |
| Tất cả requests dùng cùng một JWT issuer | Một `JwtDecoder`/chain thường đủ, không cần resolver phức tạp |

**Không dùng nhiều cơ chế chỉ vì framework hỗ trợ.** Càng nhiều đường xác thực, càng khó chứng minh không có fallback/downgrade.

## 5. Cấu hình được quản lý: nguồn chân lý cho manager selection

Giả sử policy của Orders Platform được quản lý tập trung:

```yaml
# application.yml - ví dụ cấu hình, không chứa credential thật
security:
  partner:
    issuer: https://partner-idp.example.com/realms/partners
    jwk-set-uri: https://partner-idp.example.com/realms/partners/jwks
    audience: orders-partner-api
  internal:
    introspection-uri: https://identity.example.com/oauth2/introspect
    client-id: orders-internal-resource-server
    client-secret: "${INTERNAL_INTROSPECTION_CLIENT_SECRET}"
    audience: orders-internal-api
```

Các URL chỉ là minh họa. Trong thực tế phải dùng endpoint do nhà phát hành công bố và được thẩm định; không tự suy đoán JWKS URL bằng cách nối chuỗi bất kỳ từ issuer.

Một registry được quản lý phải mô tả:

1. **Resource group/route matcher** áp dụng manager nào.
2. **Cơ chế xác thực**: JWT, opaque introspection, Basic/session/mTLS.
3. **Nguồn tin cậy**: exact issuer, JWKS URI, introspection URL, client credentials.
4. **Token profile**: thuật toán ký, audience, expiry/not-before, loại token, scope catalog.
5. **Tenant binding**: tenant nào được map đến issuer/manager nào.
6. **Chính sách lỗi**: unknown route/issuer, missing token, token invalid, AS unavailable.
7. **Lifecycle**: onboarding, revocation/offboarding, key/secret rotation, cache invalidation.

### 5.1. Quản lý nghĩa là ai được phép sửa?

Một file cấu hình nằm trong Git hoặc database **không tự nhiên trở thành tin cậy**. Cần biết:

- Ai có quyền thêm issuer/URL introspection mới?
- Tenant admin có thể tự đưa issuer do họ quản lý vào trusted set của tenant khác không?
- Cấu hình có được review/validate trước deploy không?
- Có cơ chế phân phối nhất quán tới mọi replica không?
- Khi tenant bị khóa/offboard, manager cached có được loại khỏi trust set không?

Đặc biệt, nếu một khách hàng được phép tự khai endpoint JWKS tùy ý và API dùng nó để xác minh token có quyền toàn hệ thống, họ có thể tự ký credential được chấp nhận. **Registration** phải ràng buộc phạm vi quyền với tenant, issuer và resource cụ thể, không thể chỉ lưu một URL rồi coi là an toàn.

### 5.2. Không hard-code secret

```yaml
client-secret: "${INTERNAL_INTROSPECTION_CLIENT_SECRET}"
```

đọc từ cấu hình môi trường/secret manager. Không commit secret thật, không ghi nó vào error response/log, không truyền vào query string. Khi xoay vòng credentials, resource server phải làm mới manager/introspector đúng cách theo phiên bản và deployment.

### 5.3. Cấu hình route cần nguyên tắc deny-by-default

Ví dụ:

```text
KNOWN:
  /api/partners/**
  /api/internal/**

UNKNOWN:
  /api/experimental/**
```

Route mới **không** được tự rơi vào “manager dễ dãi mặc định”. Với một resolver, unknown route phải dẫn tới từ chối hoặc manager có policy từ chối rõ ràng; đồng thời HTTP authorization rule nên có `anyRequest().denyAll()`. Không để thiếu mapping trở thành lý do dùng admin/service fallback.

## 6. Xây JWT AuthenticationManager cho vùng đối tác

Trong Servlet Spring Security 6.x, có thể tạo `JwtAuthenticationProvider` với `NimbusJwtDecoder` được cấu hình từ **trusted settings**.

### 6.1. JWT decoder xác minh issuer và audience

```java
import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationProvider;

public final class PartnerJwtManagers {

    public static AuthenticationManager create(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            // Chỉ đúng nếu partner AS ký bằng RS256 theo hợp đồng.
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> defaultsAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected JWT audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultsAndIssuer,
                audienceValidator));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        return provider::authenticate;
    }
}
```

Giải thích:

- `withJwkSetUri` nhận URL **đã được quản trị**, không từ `iss` hoặc `jku` của token chưa xác minh.
- `jwsAlgorithm(RS256)` là policy minh họa, phải đổi theo thuật toán thật đã được AS thỏa thuận. Không nhận `alg=none` hoặc algorithm không được duyệt.
- `createDefaultWithIssuer(issuer)` áp các validators mặc định phù hợp phiên bản, gồm kiểm tra issuer và thời gian theo contract của Spring Security.
- Audience validator chứng minh token dành cho `orders-partner-api`.
- `setJwtValidator(...)` **thay tập validator hiện tại**; ví dụ cố ý gộp default+issuer+audience để không vô tình chỉ giữ audience.
- `JwtAuthenticationProvider` chỉ trả authenticated result sau khi decoder xác minh token. Authorities như `SCOPE_orders.read` được map từ token đã được kiểm tra, theo converter của provider.

Các import không dùng trong ví dụ có thể bỏ ở project thực tế. Với token profile theo **RFC 9068**, có thể cần validator `typ`/token-use và các thuộc tính bắt buộc khác. Không coi signature + issuer + audience là toàn bộ mọi chính sách của một AS.

### 6.2. Vì sao cần issuer validator ngay cả khi resolver đã chọn partner manager?

Resolver chọn manager vì request gọi `/api/partners/**`. Điều đó không chứng minh JWT thật do partner phát hành. Một JWT của issuer khác có thể có `aud` và `scope` giống, hoặc dùng key material bị cấu hình lẫn. **Mỗi manager phải xác minh issuer cuối cùng**, không dựa vào quyết định chọn manager.

```text
request path = /api/partners/orders/123
   |
   v
choose partnerJwtManager
   |
   v
partner decoder:
  signature hợp lệ với keys partner?
  verified iss == configured partner issuer?
  aud contains orders-partner-api?
  exp/nbf hợp lệ?
   |
   v
JwtAuthenticationToken khi mọi điều kiện đúng
```

Nếu bất kỳ điều kiện bắt buộc nào sai, manager phải **từ chối authentication**. Không gửi token thất bại đến opaque manager rồi xem liệu AS nội bộ có chấp nhận nó không.

## 7. Xây opaque AuthenticationManager cho API nội bộ

Opaque access token được xác thực qua **RFC 7662 Token Introspection**. Spring Security Servlet cung cấp `OpaqueTokenAuthenticationProvider` dùng `OpaqueTokenIntrospector`.

Ví dụ cho dòng Spring Security 6.x có constructor tương ứng của `NimbusOpaqueTokenIntrospector`:

```java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication
    .OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection
    .NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

public final class InternalOpaqueManagers {

    public static AuthenticationManager create(
            String introspectionUri,
            String clientId,
            String clientSecret) {

        OpaqueTokenIntrospector introspector =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri,
                clientId,
                clientSecret);

        OpaqueTokenAuthenticationProvider provider =
            new OpaqueTokenAuthenticationProvider(introspector);

        return provider::authenticate;
    }
}
```

Ở các dòng Spring Security mới hơn, `SpringOpaqueTokenIntrospector` và builder tương ứng có thể được ưu tiên; chọn API **đúng version của project**, không cố dùng constructor đã bị deprecated hoặc removed. Kiến trúc vẫn là **introspection delegate đáng tin → provider → manager**.

### 7.1. Một token active chưa đủ

Ví dụ response introspection:

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "iss": "https://identity.example.com",
  "aud": ["orders-internal-api"],
  "sub": "service-order-worker",
  "client_id": "order-worker"
}
```

`active=true` chỉ nói AS coi token đang active. API còn cần policy về:

- `aud=orders-internal-api` hoặc resource binding tương đương.
- `iss` (nếu AS trả) hoặc một ràng buộc source-of-truth khác từ introspection service.
- Token type/client identity và tenant theo hợp đồng.
- Authorities được mapping từ `scope`, mặc định `orders.read` thành `SCOPE_orders.read`.
- Permission nghiệp vụ trên từng đối tượng.

**Không mặc định** `OpaqueTokenIntrospector` của mọi version tự kiểm mọi extension `aud`/`iss` do ứng dụng yêu cầu. Nếu cần, bọc delegate bằng một introspector policy **sau khi delegate đã xác thực token**.

### 7.2. Decorator kiểm tra audience khi AS trả metadata

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String requiredAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String requiredAudience) {
        this.delegate = delegate;
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Xác minh credential qua AS trước.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object raw = principal.getAttribute("aud");
        boolean allowed =
            (raw instanceof String value
                && requiredAudience.equals(value))
            || (raw instanceof Collection<?> values
                && values.contains(requiredAudience));

        if (!allowed) {
            throw new BadOpaqueTokenException(
                "Token audience is not accepted");
        }

        return principal; // Giữ SCOPE_... authorities của delegate.
    }
}
```

Trong cấu hình manager, wrap:

```java
OpaqueTokenIntrospector remote =
    new NimbusOpaqueTokenIntrospector(uri, clientId, secret);

OpaqueTokenIntrospector checked =
    new AudienceCheckingIntrospector(
        remote, "orders-internal-api");

return new OpaqueTokenAuthenticationProvider(checked)::authenticate;
```

`uri`, `clientId`, `secret` phải đến từ trusted configuration. `aud` không phải field bắt buộc được mọi AS trả theo RFC 7662. Nếu AS không trả audience mà API yêu cầu token-resource binding, phải có **hợp đồng bảo đảm tương đương** (ví dụ endpoint chỉ active cho đúng resource/client); không đơn giản bỏ kiểm tra vì provider thiếu field.

### 7.3. Timeout introspection khác token không hợp lệ

| Trường hợp | Ý nghĩa | Xử lý |
|---|---|---|
| `active:false` | AS từ chối token | Authentication thất bại |
| `active:true` nhưng audience sai | Token không dành cho API | Authentication/policy thất bại |
| AS DNS/TLS/timeout/5xx | Không có bằng chứng xác thực đáng tin | **Fail closed**, không tạo principal dự phòng |
| AS trả metadata scope nhưng token thiếu quyền endpoint | Authentication có thể đúng, authorization sai | Thường HTTP 403 |

Không viết `catch(Exception) -> new SimpleGrantedAuthority("SCOPE_orders.read")`. Việc API hoạt động khi AS down không quan trọng hơn việc nhận token giả hoặc token đã thu hồi.

## 8. Tạo resolver Servlet theo route đã được quản lý

Sau khi có **partner JWT manager** và **internal opaque manager**, nối chúng bằng `AuthenticationManagerResolver<HttpServletRequest>`.

Một cách viết cho Spring Security 6.x là dùng `RequestMatcher`:

```java
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class ManagedBearerResolverConfiguration {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            managedBearerResolver(
                @Qualifier("partnerJwtManager")
                AuthenticationManager partnerJwtManager,
                @Qualifier("internalOpaqueManager")
                AuthenticationManager internalOpaqueManager) {

        // Với Spring Security 6.x. Dòng mới hơn có thể
        // khuyến nghị PathPatternRequestMatcher thay thế.
        RequestMatcher partner =
            new AntPathRequestMatcher("/api/partners/**");
        RequestMatcher internal =
            new AntPathRequestMatcher("/api/internal/**");

        return request -> {
            if (partner.matches(request)) {
                return partnerJwtManager;
            }
            if (internal.matches(request)) {
                return internalOpaqueManager;
            }

            // Không có fallback sang manager rộng quyền hơn.
            throw new BadCredentialsException(
                "No authentication manager for protected resource");
        };
    }
}
```

**Lưu ý version:** `AntPathRequestMatcher` đã có hướng chuyển sang các path-pattern matchers trong những phiên bản mới. Để giữ match semantics nhất quán, dùng loại matcher được **Spring Security version của project** hỗ trợ và phù hợp với `securityMatcher`/routing thực tế. Không xây regex/`startsWith` rời rạc khi ứng dụng có context path, servlet mapping hoặc encoded path phức tạp.

### 8.1. Manager bean được tạo từ managed settings

Ví dụ các bean cho code trên:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;

@Configuration
public class ManagedAuthenticationManagers {

    @Bean("partnerJwtManager")
    AuthenticationManager partnerJwtManager(
            @Value("${security.partner.issuer}") String issuer,
            @Value("${security.partner.jwk-set-uri}") String jwks,
            @Value("${security.partner.audience}") String audience) {

        return PartnerJwtManagers.create(
            issuer, jwks, audience);
    }

    @Bean("internalOpaqueManager")
    AuthenticationManager internalOpaqueManager(
            @Value("${security.internal.introspection-uri}") String uri,
            @Value("${security.internal.client-id}") String clientId,
            @Value("${security.internal.client-secret}") String secret,
            @Value("${security.internal.audience}") String audience) {

        OpaqueTokenIntrospector remote =
            new NimbusOpaqueTokenIntrospector(
                uri, clientId, secret);
        OpaqueTokenIntrospector checked =
            new AudienceCheckingIntrospector(remote, audience);

        return new OpaqueTokenAuthenticationProvider(
            checked)::authenticate;
    }
}
```

Các import `OpaqueTokenIntrospector`, `NimbusOpaqueTokenIntrospector` và `OpaqueTokenAuthenticationProvider` như ví dụ ở phần trước. Đây là các class minh họa được kết hợp vào một project có cấu hình phụ thuộc phù hợp; khi dùng Spring Security 7.x phải đối chiếu API mới nếu implementation cũ bị thay thế.

**Không** lấy issuer/audience/client secret từ form body của request để tạo manager. Các `@Value` trong ví dụ lấy từ cấu hình server đã được quản lý.

### 8.2. Nối resolver với Resource Server DSL

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurityChain(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest>
                managedBearerResolver)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/partners/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/partners/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(
                    HttpMethod.GET, "/api/internal/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.PUT, "/api/internal/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(
                    managedBearerResolver))
            .build();
    }
}
```

Các điểm cần nhớ:

1. `securityMatcher("/api/**")` quyết định request được chain API xử lý.
2. `oauth2ResourceServer(...authenticationManagerResolver...)` cấu hình **Bearer filter** chọn manager cho request.
3. `authorizeHttpRequests` kiểm tra **authorities sau xác thực**, không dùng resolver để quyết định luôn quyền nghiệp vụ.
4. `SessionCreationPolicy.STATELESS` thể hiện ý định không lấy SecurityContext của HTTP session cũ để xác thực API Bearer.
5. `anyRequest().denyAll()` chặn route chưa có rule; resolver cũng không có fallback.
6. Các endpoints khác của ứng dụng cần chain riêng hoặc fallback chain; nếu không có chain match, request có thể không được Spring Security bảo vệ như dự kiến.

CSRF được disable ở ví dụ vì giả định API chỉ dùng Bearer header không tự động được trình duyệt gửi. Nếu ứng dụng còn cookie/session/basic-browser credential cho request ghi, phải xét riêng CSRF; không sao chép cấu hình này cho web login.

### 8.3. Điều gì xảy ra khi client gửi sai loại Bearer token?

Ví dụ:

```text
Request: GET /api/partners/orders/123
Token: opaque token dùng cho internal API

Resolver -> partner JWT manager
JWT decoder -> token không hợp lệ / không đúng profile
Response -> authentication failure
Không thử internal opaque manager.
```

Và:

```text
Request: GET /api/internal/orders/123
Token: JWT dùng cho partner API

Resolver -> internal opaque manager
Introspection endpoint -> active=false hoặc
token-resource policy từ chối
Response -> authentication failure
Không thử partner JWT manager.
```

Nếu AS nội bộ **cũng** chấp nhận JWT partner là active mà không ràng buộc audience, vấn đề nằm ở **introspection/token resource contract**. Không được dựa vào việc JWT “không phải opaque” để tự suy luận token chắc chắn sẽ bị từ chối.

## 9. Không thể xử lý mọi cơ chế chỉ bằng Bearer manager resolver

`BearerTokenAuthenticationFilter` (Servlet) hoặc đường Bearer authentication WebFlux được kích hoạt khi request có Bearer credential theo cấu hình. Resolver trong `oauth2ResourceServer` **không tự trích xuất**:

- `Authorization: Basic ...`;
- Form username/password;
- HTTP session cookie;
- mTLS client certificate;
- API key từ custom header;
- OIDC login authorization code callback.

Các cơ chế trên cần **authentication filter/flow tương ứng**, có thể có `AuthenticationManager` riêng và một cách resolve khác nếu framework/extension hỗ trợ.

### 9.1. Phân tách browser form login và stateless API

Một thiết kế:

```text
@Order(1) /api/**  -> Bearer Resource Server + managed resolver
@Order(2) /web/**  -> formLogin + HTTP session + CSRF
@Order(3) /**      -> deny-by-default hoặc policy rõ
```

Trên browser:

```http
GET /web/account
Cookie: JSESSIONID=...
```

Server có thể khôi phục Authentication từ session.

Trên API:

```http
GET /api/partners/orders/123
Authorization: Bearer eyJ...
```

API xác thực token **của request hiện tại**. Không cho một `JSESSIONID` từ web session vô tình đáp ứng yêu cầu Bearer của API chỉ vì cùng host.

### 9.2. Basic và Bearer có thể cùng hiện diện nhưng phải có policy

Trong một ứng dụng có `httpBasic()` và `oauth2ResourceServer()` cùng chain, các filters có thể nhận những scheme `Authorization` khác nhau. Nhưng điều đó **không cho phép** tùy tiện hạ chính sách khi JWT invalid:

```text
Authorization: Bearer invalid-jwt
    -> Bearer filter từ chối
    -> KHÔNG tự chuyển thành Basic/anonymous có quyền.
```

Nếu một endpoint chỉ dành cho service-to-service Bearer, không bật Basic chỉ để “truy cập thử” mà không có lý do. Nếu một endpoint chấp nhận hai cơ chế hợp pháp, phải định nghĩa rõ **hai cơ chế có tương đương quyền hay không**, principal mapping và audit ra sao.

### 9.3. mTLS và forwarded certificate header

mTLS authentication thường gắn với TLS client authentication và cơ chế X.509, không chỉ một `AuthenticationManagerResolver` cho Bearer. Nếu TLS terminate ở proxy, application phải có **hợp đồng tin cậy** về client certificate/identity từ proxy và ngăn client tự gửi header giả. Không lấy một header `X-Client-Cert` bất kỳ rồi tạo Authentication có quyền admin.

### 9.4. API key cần token type/credential store riêng

API key trong `X-API-Key` là một cơ chế riêng. Một custom filter có thể chuyển nó thành Authentication token chuyên biệt để một manager kiểm tra key hash/expiry/owner. Không lấy chuỗi API key đó cho vào `BearerTokenAuthenticationToken` và hy vọng JWT/opaque provider biết xử lý; cũng không cấp mọi scopes chỉ vì key tồn tại.

## 10. Nhiều issuers JWT: dùng resolver chuyên biệt khi phù hợp

Một nhóm route có thể chấp nhận JWT từ nhiều issuers đã được tin cậy:

```text
/api/partners/**
   -> Partner A issuer
   -> Partner B issuer
   -> Partner C issuer
```

Khi đó, cách chọn không nhất thiết là JWT/opaque theo path. Trong **cùng nhóm JWT**, có thể dùng `JwtIssuerAuthenticationManagerResolver` của Servlet:

```java
import org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://partner-a.example.com/issuer",
        "https://partner-b.example.com/issuer"
    );
```

Resolver có thể đọc claim `iss` chưa xác minh như một **gợi ý định tuyến**. Điều kiện bắt buộc:

- Giá trị issuer phải match **trusted list** của ứng dụng.
- Manager/decoder được chọn phải xác minh chữ ký và kiểm tra **issuer cuối cùng**.
- Audience/token profile của API vẫn phải được kiểm chứng.
- Không tạo decoder theo URL issuer tùy ý trong bearer token.
- Tenant requested phải được ràng buộc với issuer/actor đã xác minh.

### 10.1. Định tuyến theo issuer chưa xác thực không phải “tin issuer”

Giả sử attacker tạo JWT tự khai:

```json
{
  "iss": "https://partner-a.example.com/issuer",
  "sub": "admin",
  "scope": "orders.delete"
}
```

Ngay cả khi router chọn manager A, A vẫn phải kiểm chữ ký với JWKS A và validation issuer/audience. Nếu attacker không có signing key đúng, token bị từ chối. Một resolver chỉ so chuỗi `iss` mà tự tạo Authentication từ claims **là lỗi nghiêm trọng**.

### 10.2. Cùng `kid` không có nghĩa cùng issuer

JWT header `kid` chỉ là một gợi ý chọn key **trong key set được tin cậy**. Hai issuers có thể dùng cùng tên `kid=key-1`. Không dùng `kid` để tìm bất kỳ key nào trong một map toàn cục rồi chấp nhận chữ ký mà không kiểm issuer. Chỉ tìm key trong JWKS nguồn tin cậy của manager đã chọn.

### 10.3. Audience validator phải được áp ở từng issuer

Nếu custom multi-issuer resolver tự tạo `JwtAuthenticationProvider` từ các decoder riêng, **mỗi decoder** phải có issuer/time/audience validators. Không mặc định `spring.security.oauth2.resourceserver.jwt.audiences` của Boot luôn tự gắn vào mọi decoder bạn tự khởi tạo.

Một JWT hợp lệ dành cho `billing-api` không được chấp nhận ở `orders-api` chỉ vì cùng issuer và có chuỗi scope giống nhau.

## 11. Nhiều tenant: route, issuer, principal và business tenant

Xét request:

```http
GET /api/tenants/alpha/orders/123
Authorization: Bearer JWT_FROM_BETA
```

Có thể có:

- Route tenant: `alpha`.
- Issuer hint của JWT: `beta` (chưa được tin khi mới đọc).
- Verified issuer: `beta` (sau khi decoder đúng xác minh).
- Claim `tenant_id=beta` hoặc membership riêng trong domain.

Nếu hệ thống áp mô hình issuer beta chỉ phục vụ tenant beta, **JWT beta hợp lệ cũng không được đọc tenant alpha**.

### 11.1. Authentication success không đủ để access tenant

```text
JWT beta:
  signature valid
  issuer beta valid
  audience orders-api valid
  scope orders.read present

Request:
  tenant alpha

Result:
  Authentication có thể thành công
  Tenant authorization phải DENY nếu beta không có quyền alpha
```

Điều này khác lỗi chọn manager. Resolver chỉ quyết định manager; **business tenant** phải được kiểm tra bằng principal đã được xác minh và dữ liệu nghiệp vụ có thẩm quyền.

### 11.2. Identity key cần issuer

Hai issuers khác nhau có thể phát token cùng `sub=user-842`. Hệ thống không nên coi đây là cùng một danh tính chỉ vì subject trùng. Một khóa identity an toàn thường bắt đầu:

```text
IdentityKey = (verifiedIssuer, subject)
```

Tiếp đó:

```text
Permission = IdentityKey + tenant membership
             + scopes/roles + object state
```

Khi một issuer phục vụ nhiều tenant, phải kiểm `tenant_id`/membership theo hợp đồng. Khi một user được liên kết nhiều issuers, việc account linking là quy trình có kiểm soát, không suy từ email trùng nhau.

### 11.3. Registry tenant được quyền thay đổi?

Một tenant admin có thể được phép yêu cầu thay đổi thông tin IdP của **tenant họ quản lý**, nhưng không có nghĩa họ được thêm một issuer đủ quyền ở mọi tenant. Chọn manager theo tenant slug phải:

- Lấy config từ registry có phân quyền quản trị.
- Giới hạn manager tạo ra với resource/tenant tương ứng.
- Kiểm tra audience, issuer và policy object.
- Có audit/onboarding/offboarding và rollback.

“Config được lưu trong database” không thay thế kiểm tra **ai có quyền sửa config**.

## 12. Fail-closed và cấm downgrade/fallback

Trong hệ thống nhiều cơ chế, lỗi lớn nhất không hẳn là “không xác thực được token”, mà là **một token bị cơ chế mạnh từ chối nhưng lại được cơ chế khác chấp nhận không đúng mục đích**.

### 12.1. Anti-pattern: JWT failed → introspection fallback

```java
// KHÔNG LÀM như chính sách mặc định.
try {
    return jwtManager.authenticate(bearer);
} catch (AuthenticationException invalidJwt) {
    return opaqueManager.authenticate(bearer);
}
```

Nguy cơ:

- Token JWT bị từ chối do sai issuer/audience/expiry có thể được một introspection endpoint cấu hình lỏng chấp nhận.
- Một token có thể vô tình hợp lệ ở hai cơ chế với semantics khác nhau.
- Caller có thể chủ động tạo token để kích hoạt nhánh yếu hơn.
- Log/metrics trở nên khó xác định cơ chế nào đã cấp quyền.

Nếu hệ thống thực sự hỗ trợ **hai token profiles trên cùng endpoint**, phải có một **hợp đồng định tuyến an toàn**: cách phân biệt credential profile, nguồn trust, per-profile audience, kết quả xác minh cuối và các negative tests. Không biến exception fallback thành bộ định tuyến.

### 12.2. Anti-pattern: thiếu mapping thì chọn manager admin

```java
return request -> {
    AuthenticationManager manager =
        managedRoutes.get(extractRouteKey(request));
    return manager != null ? manager : adminManager;
};
```

Nếu người dùng truy cập route mới hoặc cố tình tạo path lạ, họ có thể vào manager không dành cho route ấy. Unknown routing condition phải **từ chối**, không chọn quyền cao hơn.

### 12.3. Anti-pattern: introspection lỗi thì tạo guest có scope

```java
// KHÔNG LÀM:
try {
    return opaqueIntrospector.introspect(token);
} catch (Exception upstreamFailure) {
    return guestPrincipalWithScope("orders.read");
}
```

AS không phản hồi không phải bằng chứng token active. Muốn giảm latency/giảm phụ thuộc AS cần cache với TTL, revocation và resource-binding rõ, chứ không cấp quyền từ một lỗi hạ tầng.

### 12.4. Manager resolver không tạo Authentication trực tiếp

Đây là ranh giới tin cậy lý tưởng:

```text
resolver:
  request -> manager (chỉ chọn)

manager:
  credential -> verified Authentication hoặc failure

authorization:
  verified Authentication + resource -> allow/deny
```

Không trộn cả ba thành một lambda đọc header rồi trả `JwtAuthenticationToken` có `ROLE_ADMIN` để “tối ưu” bỏ decoder.

## 13. HTTP status và nơi xảy ra lỗi

| Tình huống | Thành phần từ chối | HTTP status thường gặp |
|---|---|---|
| Route protected không có Bearer token | Authentication entry point | 401 |
| Bearer token malformed | Bearer resolver/filter | 401 |
| Resolver không có manager cho route bắt buộc | Authentication/routing | 401 hoặc lỗi do handler, **không allow** |
| Partner JWT sai chữ ký/issuer/audience | JWT manager/decoder | 401 |
| Internal opaque token `active=false` | Opaque manager/introspector | 401 |
| Introspection AS timeout/5xx | Hạ tầng xác thực không khả dụng | Không cấp quyền; status tùy exception mapping |
| Token hợp lệ nhưng thiếu `SCOPE_orders.read` | HTTP/method authorization | 403 |
| Token hợp lệ nhưng khác tenant/owner | Domain authorization | 403/404 theo chính sách |
| Client gửi Basic đến Bearer-only route | Bearer-only authentication không nhận credential | Thường 401 |
| Browser session từ `/web/**` dùng ở API Bearer-only | API chain không dựa session | Phải từ chối nếu không có Bearer token |

**Đừng giả định** mọi lỗi hạ tầng introspection đều mặc định là 401; một số exception loại service unavailable có thể đi qua handler khác. Điều bắt buộc là không tạo authenticated principal khi thiếu bằng chứng.

### 13.1. Không để handler “cứu” lỗi bảo mật

Một global exception handler có thể tùy biến body/status, nhưng không được:

```text
JwtValidationException
  -> return 200 with fallback user

AccessDeniedException
  -> call controller anyway
```

Khi Authentication thất bại, request không được vượt qua security boundary tới thao tác nhạy cảm. Hãy phân biệt trạng thái HTTP với quyết định deny thật sự.

## 14. WebFlux: `ReactiveAuthenticationManagerResolver<ServerWebExchange>`

Trong ứng dụng phản ứng, resolver trả một **`Mono<ReactiveAuthenticationManager>`** thay vì một manager trực tiếp.

Ví dụ một API WebFlux có hai vùng:

```text
/api/partners/** -> ReactiveJwtAuthenticationManager
/api/internal/** -> OpaqueTokenReactiveAuthenticationManager
```

### 14.1. Cấu hình hai managers được quản lý

```java
import java.util.List;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication
    .OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;

public final class ReactiveManagerFactory {

    public static ReactiveAuthenticationManager jwt(
            String issuer, String jwks, String audience) {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwks).build();

        OAuth2TokenValidator<Jwt> audValidator = token ->
            token.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Wrong audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audValidator));

        return new JwtReactiveAuthenticationManager(decoder);
    }

    public static ReactiveAuthenticationManager opaque(
            ReactiveOpaqueTokenIntrospector introspector) {
        return new OpaqueTokenReactiveAuthenticationManager(
            introspector);
    }
}
```

Đường JWT reactive cũng phải giới hạn thuật toán theo AS contract nếu cần; ví dụ dùng builder mặc định của Spring Security và các token validators, không mặc định mọi thuật toán/claim profile đã được chính sách của API kiểm đầy đủ. `ReactiveOpaqueTokenIntrospector` phải là implementation non-blocking/thực sự xác minh token qua AS.

### 14.2. Resolver dựa path trong WebFlux

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Bean
ReactiveAuthenticationManagerResolver<ServerWebExchange>
    managedReactiveResolver(
        @Qualifier("reactivePartnerJwtManager")
        ReactiveAuthenticationManager partner,
        @Qualifier("reactiveInternalOpaqueManager")
        ReactiveAuthenticationManager internal) {

    return exchange -> {
        String path =
            exchange.getRequest().getPath().pathWithinApplication().value();

        // Ví dụ minh họa; production nên dùng matcher thống nhất
        // với các pathMatchers của SecurityWebFilterChain.
        if (path.equals("/api/partners")
                || path.startsWith("/api/partners/")) {
            return Mono.just(partner);
        }
        if (path.equals("/api/internal")
                || path.startsWith("/api/internal/")) {
            return Mono.just(internal);
        }
        return Mono.error(new BadCredentialsException(
            "No configured manager for requested resource"));
    };
}
```

`@Qualifier` cần import từ `org.springframework.beans.factory.annotation`. Các beans `reactivePartnerJwtManager`/`reactiveInternalOpaqueManager` được tạo bằng `ReactiveManagerFactory` và cấu hình đáng tin ở môi trường server.

**Chú ý:** `startsWith("/api/internal/")` trong ví dụ đã có slash-boundary để không match `/api/internal-admin`. Tuy nhiên, hệ thống thực tế cần đảm bảo xử lý URL normalization, encoding, context path và matcher semantics khớp với security framework. Nếu không, cùng một URL có thể được resolver và authorization matcher diễn giải khác nhau.

### 14.3. Nối resolver vào WebFlux Resource Server

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.reactive
    .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange>
                managedReactiveResolver) {

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/partners/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.GET, "/api/internal/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(
                    managedReactiveResolver))
            .build();
    }
}
```

`PathPatternParserServerWebExchangeMatcher` nằm trong `org.springframework.security.web.server.util.matcher` ở các phiên bản WebFlux Security 6.x phổ biến; thêm import tương ứng. Khi dùng version khác, đối chiếu DSL/matcher API. Ví dụ chỉ thể hiện wiring và read endpoints; các thao tác ghi cần scope/tenant policy riêng.

### 14.4. Reactor Context không thay đổi trust boundary

Sau authentication thành công, Spring Security WebFlux truyền Authentication qua `ReactiveSecurityContextHolder`/Reactor Context. Manager đã được chọn và token phải được xác minh **trước khi** cấp principal cho service.

Không dùng `SecurityContextHolder.MODE_GLOBAL` để “chia sẻ user” giữa các reactive requests. Với policy cần I/O, dùng `Mono`/`Flux` và kết hợp operators, không gọi `block()` trên event loop.

## 15. Nhiều AuthenticationManagers nhưng cùng loại Bearer

Một tình huống hay gặp là **cả hai managers đều xử lý `BearerTokenAuthenticationToken`**:

```text
JwtAuthenticationProvider.supports(BearerTokenAuthenticationToken)
OpaqueTokenAuthenticationProvider.supports(BearerTokenAuthenticationToken)
```

Điều đó không định nghĩa token type một cách an toàn. Việc một chuỗi chứa hai dấu chấm không chứng minh nó là JWT access token đúng issuer; opaque token có thể dùng định dạng bất kỳ, kể cả trông giống JWT.

### 15.1. Không chỉ dựa vào token shape

Anti-pattern:

```java
if (token.split("\\.").length == 3) {
    return jwtManager;
}
return opaqueManager;
```

Attacker có thể tự tạo chuỗi có ba phần để ép chọn nhánh JWT, hoặc một opaque token hợp lệ có định dạng ba phần dẫn đến nhánh không đúng. Nếu cần chọn theo token profile, việc chọn chỉ là **routing hint** và manager được chọn phải xác minh issuer/audience/token type; không chấp nhận token ở nhánh khác chỉ vì parser của nhánh này lỗi.

### 15.2. `typ`/`alg` chưa xác minh chỉ là metadata

JWT header có thể chứa `typ=at+jwt`, `alg=RS256`, `kid=key-a`. Những trường này nằm trong token do caller cung cấp; chỉ được dùng theo chính sách kiểm tra phù hợp của verifier. Không tin `alg` để tự bật thuật toán yếu, và không tải `jku` từ header như một JWKS URI mới.

### 15.3. Nếu cùng endpoint bắt buộc nhận cả JWT và opaque?

Cần thiết kế một hợp đồng rõ hơn:

- Client/token issuer nào được cấp profile nào?
- Có namespace/prefix đáng tin để định tuyến hay không?
- Nếu chọn sai nhánh, kết quả xử lý là gì?
- JWT decoder và introspection endpoint có cùng resource audience không?
- Có tồn tại cùng một credential có thể được chấp nhận bởi cả hai nhánh không?
- Token profile mismatch phải là authentication failure, không tạo đường lách policy.
- Các negative tests có chứng minh không downgrade, không cross-issuer confusion không?

Có thể dùng một **token-format-aware resolver** được thiết kế có kiểm soát nếu yêu cầu thực sự bắt buộc, nhưng **không mặc định fallback trên `AuthenticationException`**. Nếu an toàn hơn, tách endpoint/host cho hai cơ chế để giảm ambiguity.

## 16. Chọn AuthenticationManager và chọn AuthorizationManager khác nhau

Hai interface có chữ “Manager” nhưng trách nhiệm khác nhau:

| Thành phần | Câu hỏi | Đầu vào/đầu ra khái quát |
|---|---|---|
| `AuthenticationManager` | Credential có chứng minh được danh tính không? | Authentication request → authenticated Authentication hoặc lỗi |
| `AuthenticationManagerResolver` | Request này nên được kiểm bằng manager nào? | Request context → manager |
| `AuthorizationManager` | Authenticated principal có quyền vào tài nguyên không? | Authentication + secure object → allow/deny |
| `OpaqueTokenIntrospector` | AS xác nhận token này thế nào? | Token → verified principal/metadata |
| `JwtDecoder` | JWT này có chữ ký/claims hợp lệ không? | Compact JWT → verified Jwt |

Ví dụ một API có:

```text
1. /api/internal/orders/123 -> resolver chọn opaque manager
2. Opaque introspection -> active=true, scope=orders.read
3. Authentication -> SCOPE_orders.read
4. Authorization -> HTTP GET cần SCOPE_orders.read
5. Domain -> order 123 có thuộc actor/tenant không?
```

Bước 1–3 **chưa cấp quyền đối tượng**. Bước 4 chỉ kiểm loại thao tác. Bước 5 mới xử lý quyền trên resource cụ thể.

### 16.1. Dùng `hasAuthority` đúng prefix

OAuth scope `orders.read` thường được map thành `SCOPE_orders.read`.

```java
.hasAuthority("SCOPE_orders.read")
```

khác với:

```java
.hasRole("orders.read") // mặc định tìm ROLE_orders.read
```

Nếu một manager JWT và một manager opaque tạo authorities khác prefix, HTTP rules có thể cho/deny không nhất quán. Cần có hợp đồng rõ về `GrantedAuthority` được tạo từ mỗi source và test kết quả, không sửa policy thành `authenticated()` chỉ để tránh 403.

### 16.2. Cùng tên authority không có nghĩa cùng độ tin cậy

Một internal service token và một partner user token đều có thể có `SCOPE_orders.read`. Không nên mặc định hai token được xem dữ liệu giống nhau. Có thể cần:

- HTTP route isolation.
- Audience/resource binding.
- Principal type: user vs client credentials.
- Verified issuer/client ID.
- Tenant/owner/membership.
- Data sensitivity và nghiệp vụ.

Manager selection giúp giới hạn **nguồn xác thực**; domain authorization giúp giới hạn **quyền sử dụng kết quả xác thực**.

## 17. Bảo đảm tính nhất quán của route matching

Một rủi ro ít thấy là **resolver và security matcher không cùng hiểu một URL**.

Ví dụ:

```text
securityMatcher:
  /api/partner/**

resolver:
  startsWith("/api/partners")
```

Sự khác nhau số nhiều/số ít có thể khiến request vào chain nhưng không có manager, hoặc manager xử lý một endpoint mà rule authorization không dự kiến. Tương tự, context path, servlet path, path encoding, trailing slash và proxy rewrite có thể tạo sai lệch.

### 17.1. Không tự dùng `contains` cho route security

```java
// KHÔNG LÀM:
if (request.getRequestURI().contains("internal")) {
    return internalOpaqueManager;
}
```

URL như `/api/partners/internal-preview` có thể bị match sai. Một route matcher phải:

- Hiểu rõ path segment boundary.
- Có phạm vi URL được định nghĩa chính xác.
- Phù hợp security filter chain matcher.
- Không tin raw forwarded path chưa được proxy xác thực.
- Có test cho trailing slash, encoded characters, case sensitivity, servlet mapping và URL normalization.

### 17.2. Route không match không được rơi ra ngoài security

Với nhiều chains, Spring Security chọn chain match đầu tiên. Nếu không chain nào match, request có thể đi qua mà không có các Spring Security filters tương ứng. Đối với ứng dụng public-facing, nên có **fallback SecurityFilterChain** với chính sách explicit, thường deny-by-default hoặc chỉ cho các public resources đã định nghĩa.

Một cách tổ chức:

```java
@Bean
@Order(99)
SecurityFilterChain fallbackSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().denyAll())
        .build();
}
```

Đoạn này cần những imports thông thường của `@Bean`, `@Order`, `SecurityFilterChain` và `HttpSecurity`. Với ứng dụng có endpoint public, khai báo rõ các matcher cần `permitAll` trong chain thích hợp, không mở toàn bộ fallback.

### 17.3. Nếu resolver được gọi trên route denied

Filter authentication có thể chạy trước HTTP authorization. Với request có Bearer token trên route mà `anyRequest().denyAll()`, resolver có thể đã được gọi và từ chối do unknown manager. Đây là hành vi không tự mở quyền; HTTP response có thể phản ánh authentication failure thay vì 403. Đừng cố sửa bằng cách chọn manager permissive để mọi route trả “đúng” status.

## 18. Kịch bản kiểm thử cho resolver

Tách kiểm thử thành **unit test selection**, **authentication provider tests** và **HTTP integration tests**. Mỗi lớp chứng minh một ranh giới khác nhau.

### 18.1. Unit test request → manager

Đầu tiên cần chứng minh resolver không chọn nhầm:

| Request path | Manager kỳ vọng |
|---|---|
| `/api/partners/orders/123` | partner JWT |
| `/api/partners/orders` | partner JWT |
| `/api/internal/orders/123` | internal opaque |
| `/api/internal/orders` | internal opaque |
| `/api/partners-admin/orders` | Không tự match partner |
| `/api/internal-preview/orders` | Không tự match internal |
| `/api/unmanaged/orders` | Từ chối |

Ví dụ unit test gọi chính resolver bean bằng mock request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class ManagedBearerResolverTest {

    private final AuthenticationManager partner =
        mock(AuthenticationManager.class);
    private final AuthenticationManager internal =
        mock(AuthenticationManager.class);

    private final AuthenticationManagerResolver<HttpServletRequest>
        resolver = new ManagedBearerResolverConfiguration()
            .managedBearerResolver(partner, internal);

    @Test
    void partnerPathSelectsPartnerManager() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET",
                "/api/partners/orders/123");
        request.setServletPath("/api/partners/orders/123");

        assertThat(resolver.resolve(request)).isSameAs(partner);
    }

    @Test
    void internalPathSelectsOpaqueManager() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET",
                "/api/internal/orders/123");
        request.setServletPath("/api/internal/orders/123");

        assertThat(resolver.resolve(request)).isSameAs(internal);
    }

    @Test
    void unknownPathCannotChoosePermissiveFallback() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET",
                "/api/unknown/orders");
        request.setServletPath("/api/unknown/orders");

        assertThatThrownBy(() -> resolver.resolve(request))
            .isInstanceOf(BadCredentialsException.class);
    }
}
```

Trong code minh họa, class tên `ManagedBearerResolverConfiguration` cần đồng nhất với class configuration ở mục 8 (`ManagedBearerResolverConfiguration` hoặc đổi theo project); snippet chỉ tập trung vào logic selection. `HttpServletRequest` cần import từ Jakarta Servlet. Các test matcher cần xác nhận behavior phiên bản đang chạy.

**Giới hạn:** test này không gửi Bearer token và **không kiểm JWT signature hoặc HTTP introspection**. Nó chỉ chứng minh manager được chọn đúng theo route.

### 18.2. Test manager JWT

Với JWT, test nên có:

- Token ký bằng test key của partner issuer và `aud=orders-partner-api`.
- Token đúng chữ ký nhưng sai issuer.
- Token đúng issuer nhưng `aud=payments-api`.
- Token hết hạn hoặc `nbf` tương lai.
- Token dùng thuật toán không được policy chấp nhận.
- Token có claim `scope=orders.read` được map thành `SCOPE_orders.read`.
- Token đã được parse nhưng signature invalid **không** tạo Authentication.

Không dùng `Jwt.withTokenValue(...).build()` như bằng chứng signature verification: nó chỉ dựng một object Jwt test. Nếu muốn kiểm decoder thật, ký JWT bằng private key test và cung cấp JWKS public key tương ứng.

### 18.3. Test manager opaque

Mock introspection endpoint nên trả:

```json
{"active":true,"scope":"orders.read","aud":["orders-internal-api"]}
```

và:

```json
{"active":false}
```

Những tests cần chứng minh:

| Response/Upstream | Kết quả |
|---|---|
| `active=true`, audience đúng, scope read | Authenticated principal có `SCOPE_orders.read` |
| `active=false` | Authentication thất bại |
| `active=true`, audience sai | Policy từ chối |
| `active=true`, scope thiếu | Không tự thêm `SCOPE_orders.read` |
| HTTP 401 từ AS vì client credential sai | Không fallback |
| Timeout/5xx | Không tạo principal mang quyền |

Đây là test **introspection adapter**, khác unit test của request resolver.

### 18.4. MockMvc integration qua Bearer filter

Ở tầng HTTP, không chỉ gọi `resolver.resolve(request)`, mà phải kiểm:

```text
GET /api/partners/orders/123
Authorization: Bearer valid-partner-jwt
  -> partner manager được gọi
  -> internal opaque manager không được gọi
  -> HTTP rule read scope được áp

GET /api/internal/orders/123
Authorization: Bearer active-internal-opaque-token
  -> internal opaque manager được gọi
  -> partner JWT manager không được gọi

GET /api/partners/orders/123
Authorization: Bearer invalid-partner-jwt
  -> authentication thất bại
  -> internal manager KHÔNG được gọi thử tiếp
```

Có thể dùng `MockMvc` với các test managers/mock introspection server đúng boundary. Nếu một test sử dụng:

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
```

thì đó là **mock Authentication**; nó có thể bỏ qua Bearer filter và resolver, **không chứng minh manager selection**. Để test routing end-to-end, gửi Bearer header và xác minh spy/fake managers hoặc decoder/introspection endpoint nhận request đúng.

### 18.5. WebFlux test với `WebTestClient`

Với WebFlux, dùng:

```java
client.get().uri("/api/internal/orders/123")
    .headers(headers ->
        headers.setBearerAuth("opaque-test-token"))
    .exchange()
    .expectStatus().isOk();
```

Test trên giả định fixture có controller, token hợp lệ và scope/domain policy cho phép. `mockJwt()`/`mockOpaqueToken()` thích hợp để test authorization với Authentication giả lập, nhưng không chứng minh reactive resolver đã chọn manager thật. Cần test riêng pipeline với Bearer header thực và managers được inject.

### 18.6. Negative matrix phải có

| Request và credential | Kỳ vọng |
|---|---|
| Partner route + partner JWT hợp lệ | Qua authentication, scope/domain policy tiếp tục |
| Internal route + opaque token active đúng audience | Qua authentication, scope/domain policy tiếp tục |
| Partner route + opaque token internal | Partner JWT manager từ chối; không fallback |
| Internal route + partner JWT | Internal opaque policy từ chối; không fallback |
| Partner JWT sai chữ ký | 401; không call introspection |
| Partner JWT đúng issuer nhưng sai audience | 401 |
| Opaque `active=false` | 401 |
| Opaque AS timeout | Fail closed; HTTP status theo handler |
| Token active nhưng thiếu scope cần thiết | 403 |
| Token đủ scope nhưng truy cập tenant khác | 403/404 theo business policy |
| Unknown route `/api/new/**` | Không tự chọn manager mặc định có quyền |
| Basic credential trên Bearer-only route | Không được nhận như Bearer |
| Có cookie session web nhưng thiếu Bearer token API | API không được xác thực từ session cũ |
| Header `X-Auth-Mode: legacy` | Không thay đổi manager nếu không thuộc trusted policy |
| JWT header `jku` trỏ attacker URL | Không tải key từ header |
| Manager config vừa bị offboard | Token/route không được accept sau khi policy có hiệu lực |

## 19. Tenant onboarding, secret rotation và manager cache

Với vài resource groups tĩnh, có thể tạo managers khi startup và giữ trong Spring beans. Với hàng trăm tenants, cần registry động/caching — nhưng đó là **security configuration lifecycle**, không phải cache tùy ý mọi issuer chưa xác minh.

### 19.1. Chỉ cache manager theo trusted key

Ví dụ cấu trúc:

```text
ManagedRegistry
  alpha:
    trusted issuer
    validated JWKS metadata
    audience and scopes
    active version

  beta:
    trusted issuer
    introspection endpoint credentials
    audience and scopes
    active version

ManagerCache:
  key = (tenantKey, configVersion, mechanism)
  value = preconfigured manager
```

Không dùng:

```text
cacheKey = unverified JWT iss (không allowlist)
manager = dynamically discover arbitrary issuer
```

vì attacker có thể tạo vô số `iss`, khiến server thực hiện network discovery và tạo managers không giới hạn.

### 19.2. Offboarding phải làm mất hiệu lực trust

Khi xóa một issuer/tenant khỏi registry, cần kiểm tra:

- Resolver có còn trả manager cached cho issuer đó không?
- Các replica đã nhận cấu hình mới chưa?
- JWKS cache có làm token được accept bởi manager cũ không?
- Introspection cache có giữ principal của token đã bị thu hồi không?
- Có session Authentication nào vẫn tồn tại trong browser chain không?
- Gateway có tiếp tục route request tới vùng cũ không?

Một cached decoder còn sống không nhất thiết là lỗ hổng nếu resolver **không còn cho phép chọn nó**. Nhưng nếu manager vẫn reachable qua stale registry, offboarding chưa có hiệu lực.

### 19.3. Secret rotation cho introspection

Nếu AS đổi client secret, cần làm mới introspector/HTTP client phù hợp. Không log `client_secret`, không đặt nó trong URL. Thử nhiều secrets cũ/vừa đổi có thể là yêu cầu migration tạm thời, nhưng phải có **chính sách thời gian và audit**, không tạo fallback vô hạn sang credentials kém an toàn.

### 19.4. JWKS rotation khác thay issuer

Issuer có thể xoay khóa ký JWT; decoder cần lấy key mới từ JWKS **đúng issuer**. Key rotation không có nghĩa được phép nhận token từ issuer khác; và trùng `kid` giữa hai issuers không đồng nghĩa hai khóa cùng danh tính.

## 20. Observability: biết manager nào đã chọn mà không lộ token

Với nhiều cơ chế xác thực, metrics/log nên cho biết **route nào chọn manager nào**, nhưng tránh log raw credential:

```text
requestCorrelationId
routePolicyId = partner-api-v1
selectedMechanism = JWT
selectedManagerId = partner-jwt-manager
authenticationOutcome = success / invalid_signature / invalid_audience
authorizationOutcome = allow / deny
tenantPolicyId = tenant-alpha
issuerRegistryKey = trusted-partner-id (nếu cần)
durationMs
```

Không log:

```text
Authorization: Bearer eyJ...
Authorization: Basic base64-credentials
client_secret=...
opaque_token=...
raw unverified claims/header tràn lan
full introspection response chứa PII
```

Đặc biệt không dùng issuer chưa xác minh/tenant header tự do làm metric label: attacker có thể tạo vô số giá trị gây **high cardinality** hoặc log injection. Nên dùng **ID cấu hình được quản lý** như `partner-jwt-manager`/`internal-opaque-manager`.

### 20.1. Phân biệt authentication failure với authorization failure

Một trace hữu ích:

```text
request:
  pathPolicy = /api/internal/orders/**
selection:
  mechanism = opaque
  managerId = internal-opaque
authentication:
  introspection = active
  audience = correct
  scopeAuthorities = [SCOPE_orders.read] (đã lọc khi log)
authorization:
  required = SCOPE_orders.update
  outcome = denied
http:
  status = 403
```

Đây khác:

```text
selection:
  mechanism = JWT
authentication:
  signature = invalid
  outcome = failed
http:
  status = 401
```

Không cần ghi toàn bộ token hoặc principal attributes để biết lỗi ở đâu.

## 21. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| JWT hợp lệ ở partner route nhưng 401 | Sai manager, issuer, JWKS, audience hoặc thuật toán | Trace managerId, decoder validator |
| Opaque token active nhưng API 401 | Introspection credentials/URI sai, audience policy không khớp | Test AS contract với fake response |
| API trả 403 dù token active | Thiếu `SCOPE_` authority, role prefix sai, owner/tenant deny | Xác định authorization rule/domain policy |
| Unknown route được 200 | Missing fallback chain/manager hoặc `permitAll` rộng | Kiểm tra chain matching và deny-by-default |
| Cùng URL nhưng đôi khi JWT manager, đôi khi opaque | Header do client được dùng chọn mode | Dựa vào route/server policy được quản lý |
| Bearer invalid vẫn vào controller | Exception handler/filter fallback sai | Test “no side effects on denied auth” |
| Token issuer lạ gây outbound requests | Tạo decoder/discovery từ `iss` chưa allowlist | Trusted registry + egress controls |
| Manager cache tăng vô hạn | Key do attacker điều khiển | Bounded cache theo trusted config key |
| Token beta dùng được tenant alpha | Chỉ kiểm token, bỏ tenant authorization | Bind verified issuer + membership/object |
| Partner JWT đi qua internal opaque manager | Matchers bị overlap, path interpretation khác nhau | Test route boundary và filter order |
| Basic credentials được nhận ở Bearer-only API | Có HTTP Basic filter trong cùng chain hoặc fallback | Tách chains/loại cơ chế không cần |
| Browser cookie cho API Bearer quyền truy cập | Session persistence/chain bị trộn | Stateless API chain, kiểm tra cookie-only requests |
| Unit test resolver xanh nhưng token thật vẫn fail | Test chưa chạy decoder/introspection/wiring | MockMvc/WebTestClient Bearer tests |
| Mock JWT test xanh nhưng signature sai vẫn vào | Dùng `jwt()` fixture thay pipeline thật | Signed compact JWT tests |
| Thay đổi config không có hiệu lực | Resolver/manager cache stale hoặc replica lag | Config version/invalidation |
| AS down làm mọi request quá chậm | Timeout/retry không giới hạn | Bound network timeout, fail-closed policy |

### 21.1. Một câu hỏi chẩn đoán hữu ích

Khi request bị từ chối, hỏi theo thứ tự:

1. Request đã đi vào **SecurityFilterChain** nào?
2. Filter nào nhận **credential scheme**?
3. Resolver đã chọn manager nào và **dựa trên policy nào**?
4. Manager dùng **key/AS/issuer/audience** nào?
5. Authentication có được tạo từ credential **đã xác minh** không?
6. `GrantedAuthority` sau mapping là gì?
7. HTTP/method authorization rule nào từ chối?
8. Business policy owner/tenant/state nào từ chối?

Không giải quyết mọi 401/403 bằng cách mở `permitAll()`, bỏ audience validator hoặc chuyển sang manager dễ dãi hơn.

## 22. Quy trình triển khai an toàn từ đầu

Một dự án cần nhiều cơ chế xác thực có thể thực hiện theo thứ tự:

1. **Liệt kê bề mặt API** và loại credential được phép trên từng vùng.
2. **Chọn separation strategy:** nhiều `SecurityFilterChain`, một Bearer manager resolver, hoặc kết hợp cả hai.
3. **Thiết lập managed config:** trusted issuers, JWKS, introspection endpoint, audiences, algorithms, tenant mapping, secrets.
4. **Tạo managers độc lập:** JWT phải verify signature/issuer/audience/time; opaque phải introspect và kiểm metadata/resource theo contract.
5. **Viết resolver thuần chọn manager:** route/request context → trusted manager; unknown → reject.
6. **Nối resolver vào filter chain đúng:** `oauth2ResourceServer().authenticationManagerResolver(...)` ở Servlet/WebFlux phù hợp.
7. **Đặt HTTP authorization rules:** `hasAuthority("SCOPE_...")`, deny-by-default, method-specific permissions.
8. **Bảo vệ domain:** actor issuer + subject + tenant + object permissions; không tin request parameters làm identity.
9. **Cấm downgrade/fallback:** token bị cơ chế được chọn từ chối thì không thử cơ chế khác chỉ vì exception.
10. **Kiểm soát lifecycle:** secret/key rotation, tenant onboarding/offboarding, config version và cache invalidation.
11. **Kiểm thử selection riêng:** route boundary, malformed paths, unknown route, không manager rộng quyền.
12. **Kiểm thử token validation riêng:** JWT signed keys, opaque RFC 7662, invalid audience/issuer/expiry, AS timeout.
13. **Kiểm thử HTTP thật:** Bearer header đi qua filter/manager đã cấu hình; 401/403/domain denial không có side effects.
14. **Giám sát:** routePolicyId, selectedManagerId, outcomes và latency; tuyệt đối không log secrets.

### 22.1. Sơ đồ quyết định

```mermaid
flowchart TD
    A["Nhận request"] --> B{"Route thuộc policy đã quản lý?"}
    B -->|"Không"| X["Deny / fallback secure chain"]
    B -->|"Có"| C{"Credential scheme được route cho phép?"}
    C -->|"Không"| Y["Authentication required / reject"]
    C -->|"Có"| D["Resolver lấy manager từ trusted registry"]
    D --> E{"Manager tồn tại và cấu hình active?"}
    E -->|"Không"| X
    E -->|"Có"| F{"JWT / opaque / cơ chế đã khai?"}
    F -->|"JWT"| G["Verify signature + iss + aud + exp + profile"]
    F -->|"Opaque"| H["Trusted introspection + active + aud + issuer contract"]
    F -->|"Cơ chế khác"| I["Provider/filter đặc thù có trust checks"]
    G --> J{"Authentication thành công?"}
    H --> J
    I --> J
    J -->|"Không"| Z["Fail closed; không fallback sang manager yếu"]
    J -->|"Có"| K["Authentication / authorities"]
    K --> L{"Scope / method authorization?"}
    L -->|"Không"| M["403 / deny"]
    L -->|"Có"| N{"Tenant + object policy?"}
    N -->|"Không"| M
    N -->|"Có"| O["Cho thực thi"]
```

## 23. Tổng kết

```text
MANAGED MULTI-MECHANISM AUTHENTICATION

HTTP request
   |
   v
SecurityFilterChain / credential filter
   |
   v
AuthenticationManagerResolver
   |  route / trusted context
   |  known key -> managed manager
   |  unknown   -> reject
   |
   +---- partner JWT manager
   |        JwtDecoder:
   |          signature + issuer + audience + time
   |
   +---- internal opaque manager
   |        OpaqueTokenIntrospector:
   |          active + audience + token contract
   |
   +---- other mechanisms
            only via matching trusted filters/chains
   |
   v
Authenticated Authentication
   |
   v
SCOPE_ authorities / HTTP-method rules
   |
   v
Tenant, owner, object state policy
   |
   v
Business operation

NEVER:
  untrusted URL -> dynamic JWT verifier
  invalid JWT -> try loose opaque fallback
  AS timeout -> allow default scope
  unknown path -> permissive manager
  browser session -> Bearer API auth without explicit design
```

**`AuthenticationManagerResolver` là bộ định tuyến đến cơ chế xác thực, không phải bằng chứng token hợp lệ.** Khi API có nhiều cơ chế, hãy chọn manager từ **route/context và registry cấu hình được quản lý**. Mỗi manager phải chứng minh credential đúng nguồn phát hành, audience và token profile. Token bị từ chối không được tự chuyển sang nhánh xác thực yếu hơn.

Trong **Servlet**, điểm mở rộng phù hợp là `AuthenticationManagerResolver<HttpServletRequest>` kết nối với `oauth2ResourceServer().authenticationManagerResolver(...)`. Trong **WebFlux**, dùng `ReactiveAuthenticationManagerResolver<ServerWebExchange>`, trả `Mono<ReactiveAuthenticationManager>` và giữ I/O non-blocking. Với các cơ chế hoàn toàn khác Bearer như form login, Basic, mTLS hay API key, phải thiết kế **đúng filter/chain của cơ chế đó**, không kỳ vọng Bearer resolver tự xử lý mọi thứ.

Cuối cùng, hãy giữ ba tầng tách biệt: **chọn manager**, **xác thực token**, **phân quyền endpoint/tenant/object**. Chỉ như vậy một hệ thống nhiều issuers, nhiều token types và nhiều tenants mới tránh được nhầm lẫn giữa “request chọn đường đi nào” với “credential thực sự được cấp quyền gì”.

## Tài liệu tham khảo

- [Spring Security Reference — Authentication Architecture (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`.
- [Spring Security Reference — OAuth 2.0 Resource Server Multitenancy (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): `AuthenticationManagerResolver` và `JwtIssuerAuthenticationManagerResolver`.
- [Spring Security Reference — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, filter-chain matching và thứ tự.
- [Spring Security Reference — JWT Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, issuer, audience, JWT authorities.
- [Spring Security Reference — Opaque Token Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và `OpaqueTokenIntrospector`.
- [Spring Security Reference — Reactive Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): `JwtIssuerReactiveAuthenticationManagerResolver` và WebFlux multi-tenant.
- [Spring Security Reference — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` và WebFlux JWT.
- [Spring Security Reference — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`.
- [Spring Security API — AuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManagerResolver.html): interface chọn `AuthenticationManager`.
- [Spring Security API — ReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html): interface reactive resolver.
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): chọn JWT issuer từ trusted list.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token và scope.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials, `invalid_token`, `insufficient_scope`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` và metadata opaque token.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer/discovery metadata.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, key confusion và cross-JWT validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token issuer/audience/type profile.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): quyền trên từng object/tenant ngoài OAuth scope.
