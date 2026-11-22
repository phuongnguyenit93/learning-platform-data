# Chọn nhà phát hành JWT theo danh sách tin cậy

## 1. Bối cảnh và mục tiêu học tập

Bài này thuộc phần **Gateway và nhiều tenant** trong khóa **Spring Security - reactive**. Một API gateway hoặc Resource Server WebFlux có thể tiếp nhận access token từ **nhiều nhà phát hành JWT (issuer)**, ví dụ hệ thống dành cho đối tác A và đối tác B hoặc nhiều realm của một nhà cung cấp danh tính. Thay vì cấu hình duy nhất một `issuer-uri`, server cần xác định **token đến từ issuer nào**, chọn bộ xác minh tương ứng và **chỉ tin các issuer đã được cấu hình rõ ràng**.

Trường `iss` trong JWT cho biết **nhà phát hành mà token tự khai báo**. Nhưng trước khi kiểm tra chữ ký, `iss` chỉ là **dữ liệu chưa tin cậy**. Đọc `iss` để chọn một decoder **không đồng nghĩa** đã xác thực issuer. Thiết kế đúng phải thực hiện:

1. Đọc `iss` như **gợi ý chọn routing**.
2. So sánh **chính xác** `iss` với một **allowlist đáng tin**.
3. Chỉ chọn `ReactiveAuthenticationManager`/`ReactiveJwtDecoder` đã đăng ký từ **cấu hình server**, tuyệt đối không dựng discovery/JWKS URL tùy tiện từ chuỗi `iss` do client đưa vào.
4. Xác minh **chữ ký** bằng key/JWK source dành cho issuer đó, đồng thời xác minh **issuer, thời gian `exp`/`nbf`, audience `aud`, token type và scopes** theo yêu cầu API.
5. Sau authentication, giới hạn **tenant/resource ownership**; một JWT hợp lệ của tenant A không được tự truy cập dữ liệu tenant B chỉ vì gateway chấp nhận cả hai issuer.

Sau bài học, bạn sẽ:
- Hiểu ranh giới giữa **JWT routing**, **authentication** và **authorization** trong hệ thống multi-tenant.
- Dùng đúng `JwtIssuerReactiveAuthenticationManagerResolver` và `ReactiveAuthenticationManagerResolver<ServerWebExchange>` trong Spring Security **reactive**.
- Chọn giữa `fromTrustedIssuers(...)` đơn giản và **registry các managers tường minh** để kiểm tra thêm audience/JWKS.
- Tạo ứng dụng Java 17, Spring Boot 3.3.5, Spring WebFlux có hai issuer mẫu và một route giới hạn tenant.
- Viết test RSA/JWT **ký thật** để xác minh đúng issuer/key/audience/time, không giả vờ `mockJwt()` kiểm chứng chữ ký.
- Kiểm thử phân quyền theo URL tenant bằng `WebTestClient`.
- Biết cách cập nhật danh sách issuer, bảo vệ chống SSRF, key confusion, token substitution và cross-tenant data leakage.
- Phân tích caching/JWKS rotation, failure handling, metrics và rollout cho gateway production.

**Giới hạn:** `issuer-alpha.example.test` và `issuer-beta.example.test` trong mã là **domain minh họa không có OP thật**. App có thể khởi động và chạy public endpoint, các unit/HTTP mock tests không cần network issuer, nhưng muốn thử access token thật qua `curl` cần **hai Authorization Servers/JWKS HTTPS đã cấu hình đúng**. Đừng lấy khóa RSA của bộ test làm khóa của hệ thống production.

## 2. JWT từ nhiều issuer có gì khó?

Một Resource Server duy nhất có thể phục vụ:

```text
                          +------------------------+
                          |  API Gateway / WebFlux |
Client Alpha -- Bearer -->|                        |
                          |     Lấy iss (hint)     |
Client Beta  -- Bearer -->|        |               |
                          |    TRUSTED LIST        |
                          |     /          \       |
                          | Manager A   Manager B  |
                          |   |             |      |
                          | JWKS A        JWKS B    |
                          | Verify sig, iss, aud,  |
                          | exp/nbf, policy        |
                          |          |             |
                          | Tenant/resource guard  |
                          +------------+-----------+
                                       |
                                     API data
```

Ví dụ token của issuer A:

```json
{
  "iss": "https://issuer-alpha.example.test/realm/alpha",
  "sub": "partner-100",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "alpha",
  "iat": 1730000000,
  "exp": 1730000600
}
```

Issuer B có thể phát token dùng **cùng `sub` hoặc `scope`** nhưng thuộc chính sách khác:

```json
{
  "iss": "https://issuer-beta.example.test/realm/beta",
  "sub": "partner-100",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "beta",
  "iat": 1730000000,
  "exp": 1730000600
}
```

Đây là **payload minh họa**, không phải JWT được ký và không có hiệu lực ở thời điểm hiện tại. Một JWT thật là compact JWS `header.payload.signature` và được Resource Server verify qua public keys đã tin cậy.

**`sub=partner-100` ở A không phải mặc định cùng một identity với `sub=partner-100` ở B.** Khi xây dữ liệu principal, audit và caches, cần định danh **(issuer, subject)** hoặc một internal identity mapping đã được chứng minh, không dùng mỗi `sub`.

### Một ví dụ về sai lầm “tin tất cả issuer”

Anti-pattern:

```java
// ANTI-PATTERN: tuyệt đối không dùng iss tùy ý
// để tạo một decoder tin được.
String userSuppliedIssuer = getUnverifiedIssuer(rawJwt);
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(userSuppliedIssuer);
```

Đây là **fragment cảnh báo**, không phải class độc lập. Nếu client có thể đặt `iss=https://attacker.example.test`, hệ thống có thể tự gọi discovery URL của attacker (nguy cơ SSRF/outbound traffic) rồi dùng public key do attacker phát để chấp nhận token do chính attacker ký. Một JWT có chữ ký “đúng với issuer do attacker tự dựng” **không trở thành token đáng tin đối với ứng dụng của bạn**.

**Câu hỏi quan trọng:** Ai quyết định issuer được phép? Câu trả lời phải là **cấu hình đã được quản trị**, không phải tự token và không phải request header như `X-Tenant`.

## 3. Các khái niệm phân biệt

| Trường/đối tượng | Vai trò | Mức tin cậy khi vừa nhận request |
| --- | --- | --- |
| Raw Bearer JWT | Credential nhận từ client | Chưa tin |
| `iss` chưa verify | Gợi ý chọn issuer manager | Chưa tin, phải allowlist |
| `kid` trong JWS header | Gợi ý chọn key **trong JWKS đã gắn với issuer** | Chưa tin, không phải URL |
| `jku`/`x5u` trong header | Có thể chỉ tới key URL | **Không** tự fetch URL do token tùy ý đưa |
| Danh sách trusted issuers | Chính sách server | Nguồn tin đã được quản trị |
| Configured JWK Set URI | Nơi đọc public keys cho một issuer | Chỉ tin nếu lấy từ cấu hình đã duyệt |
| `ReactiveJwtDecoder` | Verify signature và JWT validators | Quyết định acceptance |
| `ReactiveAuthenticationManager` | Chuyển token đã verify thành Authentication | Có thể tạo principal/authorities |
| `aud` | Token này được phát cho API/client nào | Phải verify theo API |
| `scope`/`scp` | Scopes do issuer ký trong token | Dùng sau signature/claim validation |
| `tenant_id` | Claim tenant do issuer phát | Chỉ tin sau verify và phải match business policy |
| Tenant trong URL/path/header | Resource context client muốn truy cập | **Không phải** chứng minh quyền |
| `sub` | Subject trong phạm vi issuer | Không nên dùng làm identity global đơn độc |

**Phân biệt Authentication với Authorization:**
- Authentication: token có được phát bởi issuer tin cậy, đúng khóa, thời gian và audience không?
- Authorization: principal/tenant/scopes đó có được truy cập `/api/tenants/alpha/orders` không? Và có quyền trên đơn hàng cụ thể không?

Một token được issuer Alpha ký thật nhưng thử truy cập `/api/tenants/beta/orders` phải bị **403** do tenant policy nếu token đã authenticated, chứ không phải được phép vì có `orders:read` chung.

## 4. Luồng xử lý đúng trong Spring Security reactive

```text
GET /api/tenants/alpha/orders
Authorization: Bearer <JWS>

     |
     v
BearerToken AuthenticationWebFilter
     |
     v
JwtIssuerReactiveAuthenticationManagerResolver.resolve(exchange)
     |
     +-- Đọc JWT iss để chọn manager [CHƯA VERIFY]
     |
     +-- iss không có trong allowlist -> 401 invalid_token
     |
     +-- iss đã được duyệt -> lấy manager A / B từ registry
                                 |
                                 v
                   JwtReactiveAuthenticationManager
                                 |
                                 v
                   NimbusReactiveJwtDecoder dành cho issuer
                     - khóa của issuer đã cấu hình
                     - chữ ký / algorithm
                     - exact iss
                     - exp, nbf
                     - audience cho API
                                 |
                         failed -> 401
                                 |
                                 v
                   JwtAuthenticationToken + SCOPE_*
                                 |
                                 v
                   ReactiveAuthorizationManager
                     - path tenant có phù hợp issuer?
                     - scope orders:read có đủ?
                     - ownership/policy resource?
                                 |
                         denied -> 403
                                 |
                                 v
                             Controller
```

**Chốt ranh giới tin cậy:** Khai thác `iss` chưa verify như một **index vào map tĩnh đáng tin** là được, vì nó **chưa cấp quyền**; decoder được chọn sau đó bắt buộc validate toàn bộ token. Nếu issuer không có trong map, **không fallback sang một URL issuer tự suy diễn**.

### Kết quả HTTP chuẩn

- Không có Bearer token trên route private: thường **401**.
- Token malformed, issuer lạ, chữ ký sai, expired, audience sai: **401** (JWT authentication thất bại).
- Token hợp lệ nhưng scope không đủ: **403**.
- Token hợp lệ của issuer Alpha dùng truy cập tenant Beta: **403**.
- User/tenant/token hợp lệ nhưng resource ownership sai: **403 hoặc 404** theo chính sách che giấu sự tồn tại của resource.
- Token hợp lệ và đủ policy: **200**.
- Public `/health` hoặc `/public`: **200** không cần Bearer.

Đừng trả chi tiết issuer keys, raw token hoặc internal policy reason trong response lỗi. Ghi audit reason theo mã lỗi nội bộ, không log credential.

## 5. API Spring Security reactive: `JwtIssuerReactiveAuthenticationManagerResolver`

### 5.1. Phương án đơn giản: `fromTrustedIssuers`

Ví dụ từ hướng dẫn chính thức:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp.example.org/issuerOne",
                "https://idp.example.org/issuerTwo");

return http
        .authorizeExchange(exchanges ->
                exchanges.anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(resolver))
        .build();
```

Đây là **fragment cấu hình trong Bean `SecurityWebFilterChain`**, không phải một class độc lập. Nó là API **reactive**; bản Servlet có tên `JwtIssuerAuthenticationManagerResolver` và DSL `HttpSecurity` khác.

**Ưu điểm:**
- Allowlist issuer được chỉ rõ, không lấy URL ngẫu nhiên từ token.
- Spring Security tự chọn `JwtReactiveAuthenticationManager` tương ứng.
- Theo tài liệu, manager/metadata có thể **được tạo/lấy lazily** khi issuer được dùng lần đầu, giảm phụ thuộc startup vào tất cả OP.
- Gọn khi chính sách xác minh giống nhau và chỉ cần issuer allowlist.

**Giới hạn cần xem xét:**
- Nếu mỗi issuer có **audience khác nhau**, JWK Set URI đã kiểm soát khác nhau, allowed algorithms khác nhau hoặc token type policy đặc biệt, nên cung cấp **registry managers/decoders cụ thể**.
- Không mặc định `fromTrustedIssuers` tự thỏa **business tenant isolation** hoặc audience riêng của API.
- Cần kiểm tra hỗ trợ của OP, TLS và metadata, cũng như **phiên bản Spring Security**.
- Số lượng issuer lớn/thiếu kiểm soát sẽ tăng chi phí JWKS/manager cache và khả năng rate abuse.

### 5.2. Phương án kiểm soát đầy đủ: registry manager đã duyệt

Dùng `JwtIssuerReactiveAuthenticationManagerResolver` với `ReactiveAuthenticationManagerResolver<String>` chỉ lấy manager trong map:

```java
Map<String, ReactiveAuthenticationManager> trustedManagers =
        Map.of(
                "https://issuer-a.example.test",
                managerA,
                "https://issuer-b.example.test",
                managerB);

var resolver =
        new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(
                        trustedManagers.get(issuer)));
```

Đoạn trên là **fragment**: `managerA`/`managerB` đã được app khởi tạo bằng decoders **có signature/iss/aud/expiry validators**, không phải managers “accept all”. Unknown issuer trả empty ở bước tìm manager; resolver từ chối token thay vì tạo decoder tùy ý.

**Ưu điểm:** kiểm soát:
- Cặp **issuer → JWK Set URI đáng tin**.
- Các thuật toán ký cho phép (ví dụ chỉ RS256 theo policy).
- Expected audience cho từng issuer.
- Optional token type `typ=at+jwt`/RFC 9068 hoặc `azp`, `client_id`, `tid` tùy token profile đã thống nhất.
- Caching/metrics và lifecycle của từng manager.
- Chức năng disable issuer theo quy trình có kiểm toán.

**Không chấp nhận** bất kỳ manager nào được tạo từ `iss` chưa whitelist; nếu cần dynamic onboarding, cấu hình phải đến từ **control plane có phân quyền**, qua validation & approval.

### 5.3. Vì sao có thể cần đọc `iss` hai lần?

Trong mô hình route-by-claim:
1. Resolver đọc `iss` chưa được verify để chọn manager A/B.
2. Decoder tương ứng lại đọc JWS, verify chữ ký và **xác minh exact `iss` đã ký**.

Đây không phải bug. Bước 1 chỉ quyết định **cách xác minh**; bước 2 quyết định token **có đáng tin hay không**.

**Cảnh báo key confusion:** Không lấy `kid` hoặc `jku` từ JWT rồi fetch key ở một host bất kỳ. `kid` chỉ được dùng để chọn trong **JWKS của issuer được duyệt**; cùng `kid` ở issuer A và B không làm key của A hợp lệ cho B.

## 6. Issuer, JWK Set URI và URL matching

### 6.1. Exact issuer string

Các giá trị sau nên coi là **khác nhau** nếu chính sách đăng ký không nêu rõ việc chuẩn hóa:
- `https://idp.example.test/realm/a`
- `https://idp.example.test/realm/a/`
- `https://IDP.example.test/realm/a`
- `http://idp.example.test/realm/a`
- `https://idp.example.test/realm/b`

Với OIDC, `iss` phải match issuer được tài liệu và metadata khai báo. **Không áp `startsWith("https://idp.example.test")`**; nó có thể chấp nhận sai path hoặc hostname như `https://idp.example.test.attacker.example`. Một hostname hoặc issuer không tự xác định tenant nếu một OP phục vụ nhiều realms.

### 6.2. HTTPS, discovery, JWKS

Cấu hình đáng tin phải gắn một issuer với source public keys. Các lựa chọn:
- Dùng issuer discovery và validate metadata/`jwks_uri`.
- Cấu hình `jwk-set-uri` tường minh từ control plane, không fetch URL từ token.

Trường hợp có JWK URI tĩnh, cần **đặt issuer validator riêng**, vì một decoder tạo bằng `withJwkSetUri(...)` không tự biết issuer mong đợi.

```java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withJwkSetUri("https://idp.example.test/jwks")
                .build();

decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
                "https://idp.example.test/realm/a"));
```

Đây là fragment. Trong demo đầy đủ sẽ **kết hợp cả issuer, timestamp và audience validation**.

**Lưu ý an ninh phiên bản:** Spring đã công bố **CVE-2026-22748** về nguy cơ cấu hình sai issuer validation khi dùng `NimbusReactiveJwtDecoder.withIssuerLocation(...)` trên các bản cũ. Dù dùng discovery, luôn **xác nhận issuer validator đang hoạt động**, nâng cấp lên bản Spring Security được vá và có hỗ trợ. Ví dụ dùng Spring Boot 3.3.5 chỉ để minh họa API lịch sử; bản đó **không phải khuyến nghị phiên bản production vào năm 2026**.

### 6.3. Audience check là bắt buộc theo API contract

JWT có `aud` cho biết token được phát để sử dụng bởi resource server nào. Một token ID của một browser client hay access token dành cho API khác có thể có:
- Chữ ký hợp lệ.
- `iss` thuộc allowlist.
- `exp` chưa hết hạn.

Nhưng **vẫn phải từ chối** nếu `aud` không chứa audience của API hiện tại. Demo yêu cầu `aud=orders-api` cho cả hai tenant; trong thực tế mỗi issuer/tenant có thể dùng audience khác.

Không coi `client_id` hoặc `azp` là thay thế mặc định của `aud`. Token profile OAuth2/JWT được IdP phát hành cần được thống nhất và kiểm thử cụ thể.

### 6.4. Verify algorithm và token type

- Không nhận `alg=none`.
- Không trộn HMAC symmetric secrets với JWK RSA public keys tùy ý.
- Cấu hình allowed JWS algorithms, tránh algorithm confusion.
- Nếu API yêu cầu **JWT access token theo RFC 9068**, xem xét kiểm tra `typ=at+jwt` và các claims profile (issuer/audience/client_id...) theo version/framework. Một ID Token của OIDC **không phải** access token cho Resource Server.
- Trong ví dụ này, decoder mặc định dùng RS256 và validators cho issuer/time/audience; **không tuyên bố đã kiểm tra `typ=at+jwt`**. Production phải thêm kiểm tra type nếu provider/profile yêu cầu, đồng thời cập nhật framework.

## 7. Gateway, tenant và ranh giới authorization

### 7.1. Issuer không nhất thiết bằng tenant

Hai mô hình phổ biến:

**Một issuer cho mỗi tenant:**

```text
issuer A -> tenant alpha
issuer B -> tenant beta
```

Có thể duy trì mapping chính thức trong configuration. Demo dùng mô hình này để minh họa.

**Một issuer phục vụ nhiều tenants:**

```text
issuer shared -> tenant alpha
              -> tenant beta
              -> tenant gamma
```

Khi đó **không thể suy tenant chỉ từ `iss`**. Phải dựa vào verified tenant claim (`tid`/`tenant_id` theo profile của OP) và policy kiểm tra account-to-tenant membership, audience, resource ownership. Một issuer đáng tin **không tự nghĩa mọi subject của issuer được truy cập mọi tenant**.

### 7.2. URL tenant do client chọn không chứng minh quyền

Anti-pattern:

```java
// ANTI-PATTERN: có token hợp lệ là bỏ qua tenant của URL.
@GetMapping("/api/tenants/{tenant}/orders")
public Mono<?> orders(@PathVariable String tenant) {
    return repository.readAllOrdersForTenant(tenant);
}
```

Đây là fragment, không phải class chạy độc lập. Nếu Authenticated A được truyền `tenant=beta`, backend có thể làm lộ dữ liệu B. Cần guard kiểm tra mapping issuer/subject/tenant và quyền trên resource.

Trong demo:
- Issuer alpha chỉ được phép URL tenant `alpha`.
- Issuer beta chỉ được phép URL tenant `beta`.
- Cần `SCOPE_orders:read`.
- Quy tắc nằm trong **ReactiveAuthorizationManager<AuthorizationContext>**, chạy trước Controller.
- Một business service thật còn cần kiểm tra ownership của từng order ở tầng dữ liệu, không chỉ route-level guard.

### 7.3. Key định danh principal

Không xây key cache/audit từ `sub` đơn độc. Dùng composite:
- `(issuer, subject)`;
- thêm tenant ID/partner client ID nếu app cần;
- hoặc mapping nội bộ có đối chiếu và phân quyền.

Nếu hai issuers cùng phát `sub=alice`, đó có thể là hai user khác nhau. Sử dụng subject không namespaced gây cross-tenant identity confusion.

## 8. Dự án runnable: Spring Boot 3.3.5 / Java 17 / WebFlux

Demo dùng **hai issuer cấu hình tĩnh** và kiểm tra **issuer + signature + exp/nbf + audience**, rồi giới hạn tenant ở request path.

Cấu trúc:

```text
trusted-issuer-webflux/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/trustedissuers/
    │   │   ├── TrustedIssuerApplication.java
    │   │   ├── TrustedIssuerProperties.java
    │   │   ├── IssuerRouting.java
    │   │   ├── TenantGuard.java
    │   │   ├── SecurityConfig.java
    │   │   └── OrdersController.java
    │   └── resources/application.yml
    └── test/
        └── java/dev/example/trustedissuers/
            ├── IssuerRoutingTests.java
            └── TenantHttpTests.java
```

### 8.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'trusted-issuer-webflux'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` quản lý JWT/JWS/JOSE dependencies qua Boot BOM. Không thêm `spring-boot-starter-web` (Servlet starter) vào demo WebFlux; khi có cả hai, Spring Boot thường chọn Servlet/MVC.

**Version note:** Boot 3.3.5/Spring Security 6.3.x là mốc API của bài học, không phải lựa chọn bảo mật production mới. Hãy dùng bản được hỗ trợ, đã vá các security advisories và xác minh khác biệt API khi nâng cấp.

### 8.2. `application.yml`: allowlist do server quản lý

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

app:
  security:
    tenants:
      alpha:
        issuer: https://issuer-alpha.example.test/realm/alpha
        jwk-set-uri: https://issuer-alpha.example.test/jwks
        audience: orders-api
      beta:
        issuer: https://issuer-beta.example.test/realm/beta
        jwk-set-uri: https://issuer-beta.example.test/jwks
        audience: orders-api
```

**Vì sao không có `spring.security.oauth2.resourceserver.jwt.issuer-uri` duy nhất?** Vì app nhận **nhiều issuers**. Ta đăng ký một resolver/manager registry tường minh; nếu để một cấu hình JWT đơn mặc định, app có thể chỉ hiểu một issuer hoặc áp validators không đúng theo tenant.

**`.example.test` chỉ là minh họa**: muốn xử lý Bearer access token thật, thay toàn bộ `issuer` và `jwk-set-uri` bằng URLs HTTPS đúng theo OP và tenant của bạn, kiểm tra `audience`. App startup không cần gọi các URL test nhờ config JWKS tĩnh; **request Bearer thật** sẽ cần JWK Set URI truy cập được để verify signature.

Không để user/query/header tự chọn `jwk-set-uri`. Mọi chỉnh sửa danh sách này là **security-sensitive control-plane change**, cần review, audit và rollout.

### 8.3. Main class

`src/main/java/dev/example/trustedissuers/TrustedIssuerApplication.java`:

```java
package dev.example.trustedissuers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TrustedIssuerApplication {
    public static void main(String[] args) {
        SpringApplication.run(TrustedIssuerApplication.class, args);
    }
}
```

### 8.4. Trusted configuration properties + fail-fast validation

`src/main/java/dev/example/trustedissuers/TrustedIssuerProperties.java`:

```java
package dev.example.trustedissuers;

import java.net.URI;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record TrustedIssuerProperties(
        Map<String, Tenant> tenants) {

    public TrustedIssuerProperties {
        if (tenants == null || tenants.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one trusted issuer is required");
        }

        tenants = Map.copyOf(tenants);
        Set<String> seenIssuers = new HashSet<>();

        for (var entry : tenants.entrySet()) {
            String tenantId = entry.getKey();
            Tenant policy = entry.getValue();

            if (tenantId == null || tenantId.isBlank()
                    || policy == null) {
                throw new IllegalArgumentException(
                        "Invalid tenant configuration");
            }

            validateHttpsUrl(policy.issuer());
            validateHttpsUrl(policy.jwkSetUri());

            if (policy.audience() == null
                    || policy.audience().isBlank()) {
                throw new IllegalArgumentException(
                        "Audience must not be empty");
            }

            if (!seenIssuers.add(policy.issuer())) {
                throw new IllegalArgumentException(
                        "Duplicate issuer: one issuer per tenant "
                      + "is required by this example");
            }
        }
    }

    private static void validateHttpsUrl(String url) {
        if (url == null || url.isBlank()) {
            throw new IllegalArgumentException(
                    "Trusted URL must not be empty");
        }

        URI uri = URI.create(url);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "Trusted issuer and JWKS URLs must be HTTPS "
                  + "without user info, query or fragment");
        }
    }

    public record Tenant(
            String issuer,
            String jwkSetUri,
            String audience) {
    }
}
```

**Điểm cần giải thích:**
- `@ConfigurationProperties` bind cấu hình do **server/operator** quản lý, không bind từ incoming user request.
- Không cho trusted-list rỗng: nếu app không có issuer tin cậy, phải fail fast thay vì fallback “cho mọi issuer”.
- Dùng `Map.copyOf(...)` để snapshot danh sách, tránh tự thay đổi giữa requests.
- URI phải HTTPS, có host, không chứa userInfo/query/fragment, giảm nguy cơ vô tình cấu hình một source không phù hợp.
- Không cho duplicate issuer vì demo mô hình **1 issuer → 1 tenant**; nếu issuer chung cho nhiều tenant, thay đổi thiết kế guard theo verified tenant claim, không ép một issuer lặp lại trong map.
- `audience` phải được cấu hình, không dùng `aud` do client đưa làm điều kiện tin cậy.
- **HTTPS và allowlist là cần nhưng chưa đủ để ngăn mọi SSRF** nếu chính cấu hình bị đối tượng không đáng tin ghi. Production còn nên áp network egress policy, kiểm soát private IP/DNS rebinding ở outbound traffic, và giới hạn quyền sửa cấu hình.

**Dữ liệu config cần thêm trong production:** allowed signing algorithms, token profile, `typ`, client/tenant-specific policies, cache timeouts, JWKS update cadence và cơ chế tắt issuer khẩn cấp.

### 8.5. IssuerRouting: manager registry và validators

`src/main/java/dev/example/trustedissuers/IssuerRouting.java`:

```java
package dev.example.trustedissuers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class IssuerRouting {

    private IssuerRouting() {
    }

    public static OAuth2TokenValidator<Jwt> validators(
            String expectedIssuer, String expectedAudience) {

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "JWT audience is not accepted",
                            null));
        };

        return new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(
                        expectedIssuer),
                audience);
    }

    public static ReactiveAuthenticationManagerResolver<ServerWebExchange>
            fromTrustedDecoders(
                    Map<String, ReactiveJwtDecoder> approvedDecoders) {

        if (approvedDecoders == null
                || approvedDecoders.isEmpty()) {
            throw new IllegalArgumentException(
                    "Trusted decoders must not be empty");
        }

        Map<String, ReactiveAuthenticationManager> managers =
                new HashMap<>();

        approvedDecoders.forEach((issuer, decoder) -> {
            if (issuer == null || issuer.isBlank()
                    || decoder == null) {
                throw new IllegalArgumentException(
                        "Invalid trusted issuer mapping");
            }
            managers.put(issuer,
                    new JwtReactiveAuthenticationManager(decoder));
        });

        Map<String, ReactiveAuthenticationManager> trusted =
                Map.copyOf(managers);

        return new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(trusted.get(issuer)));
    }
}
```

**Bảo vệ quan trọng:**
1. `JwtValidators.createDefaultWithIssuer(expectedIssuer)` kiểm tra issuer **và các validators mặc định**, gồm thời gian, sau khi decoder đã xác minh chữ ký.
2. Audience validator kiểm tra `jwt.getAudience().contains(expectedAudience)`, không chấp nhận một audience khác đơn thuần vì issuer đúng.
3. Map được tạo từ **approvedDecoders** của server, không từ dynamic untrusted `iss`.
4. Mỗi manager dùng `JwtReactiveAuthenticationManager(decoder)` nên token phải qua decoder xác minh trước khi thành authenticated principal.
5. Resolver nhìn `iss` chưa verify để chọn **chỉ một manager trong Map.copyOf(managers)**. Unknown issuer không sinh HTTP request discovery/JWKS mới.
6. Các managers không dùng chung public key trừ khi key sharing được thiết kế riêng có chứng cứ; trong demo A/B mỗi issuer có JWKS riêng.
7. `ReactiveJwtDecoder` có thể truyền vào tests để dùng RSA public key tại chỗ, không cần URL network; tests vẫn phải sign token thật để chứng minh decoder từ chối wrong signature.

**Đừng tự viết decoder bằng `Base64.getUrlDecoder` rồi bỏ qua JWS signature**. `iss` là index chưa tin; câu trả lời security đến từ cryptographic verification + validators.

### 8.6. TenantGuard: phân quyền dựa trên issuer đã xác minh

`src/main/java/dev/example/trustedissuers/TenantGuard.java`:

```java
package dev.example.trustedissuers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.authorization.AuthorizationContext;

import reactor.core.publisher.Mono;

public final class TenantGuard
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final Map<String, String> tenantByIssuer;

    public TenantGuard(TrustedIssuerProperties properties) {
        Map<String, String> trusted = new HashMap<>();
        properties.tenants().forEach((tenant, policy) ->
                trusted.put(policy.issuer(), tenant));
        this.tenantByIssuer = Map.copyOf(trusted);
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object pathValue = context.getVariables().get("tenant");
        String requestedTenant =
                (pathValue instanceof String value) ? value : null;

        return authentication
                .map(auth -> {
                    if (!auth.isAuthenticated()
                            || !(auth.getPrincipal()
                                    instanceof Jwt jwt)
                            || jwt.getIssuer() == null
                            || requestedTenant == null) {
                        return new AuthorizationDecision(false);
                    }

                    String verifiedIssuer =
                            jwt.getIssuer().toString();
                    String boundTenant =
                            tenantByIssuer.get(verifiedIssuer);

                    boolean hasScope = auth.getAuthorities().stream()
                            .anyMatch(granted ->
                                    "SCOPE_orders:read".equals(
                                            granted.getAuthority()));

                    boolean allowed = boundTenant != null
                            && boundTenant.equals(requestedTenant)
                            && hasScope;

                    return new AuthorizationDecision(allowed);
                })
                .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
```

**Phân tích:**
- `AuthorizationContext.getVariables().get("tenant")` đến từ path matcher `/api/tenants/{tenant}/orders`.
- URI path tenant **không** phải nguồn xác thực; nó chỉ là tenant client muốn đọc.
- `auth.getPrincipal() instanceof Jwt` chỉ có ý nghĩa an toàn ở runtime **vì JWT Authentication Manager thực tế đã verify token**. Trong `mockJwt()` tests nó chỉ là giả lập.
- `tenantByIssuer` là mapping server-side chỉ với issuer đã duyệt, không dựa vào `tenant_id` tùy ý của request/header.
- Cần authority `SCOPE_orders:read` do Spring Security map từ scope claim của JWT **sau xác minh chữ ký**.
- Thiếu principal, thiếu issuer, thiếu scope, tenant không khớp → quyết định false, không có fallback allow.
- Demo 1 issuer cho 1 tenant; nếu cùng issuer có nhiều tenants, phải kiểm tra tenant claim đã verify **và membership/ownership hiện tại**.
- Với nhiều loại JWT token profiles, hãy cấu hình authentication converter và authorities mapping tương ứng; không giả định mọi OP dùng claim `scope` giống nhau.

### 8.7. SecurityConfig: kết nối danh sách issuer với WebFlux Resource Server

`src/main/java/dev/example/trustedissuers/SecurityConfig.java`:

```java
package dev.example.trustedissuers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.server.ServerWebExchange;

@Configuration
@EnableWebFluxSecurity
@EnableConfigurationProperties(TrustedIssuerProperties.class)
public class SecurityConfig {

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange>
            trustedIssuerResolver(TrustedIssuerProperties properties) {

        Map<String, ReactiveJwtDecoder> approved =
                new HashMap<>();

        properties.tenants().forEach((tenant, policy) -> {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder
                            .withJwkSetUri(policy.jwkSetUri())
                            .build();

            decoder.setJwtValidator(
                    IssuerRouting.validators(
                            policy.issuer(),
                            policy.audience()));

            approved.put(policy.issuer(), decoder);
        });

        return IssuerRouting.fromTrustedDecoders(approved);
    }

    @Bean
    TenantGuard tenantGuard(TrustedIssuerProperties properties) {
        return new TenantGuard(properties);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange>
                    trustedIssuerResolver,
            TenantGuard tenantGuard) {

        return http
                // Bearer-token-only stateless API; see CSRF caveat below.
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/tenants/{tenant}/orders")
                            .access(tenantGuard)
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationManagerResolver(
                                trustedIssuerResolver))
                .build();
    }
}
```

**Các điểm không được bỏ qua:**
1. Mỗi tenant được gắn với **issuer, JWKS, audience đáng tin**.
2. `NimbusReactiveJwtDecoder.withJwkSetUri(...)` được xây từ **server config**, không từ `iss` của JWT.
3. `setJwtValidator(...)` **bắt buộc** chứa issuer/time validators và thêm audience validator.
4. `fromTrustedDecoders(...)` tạo map manager và resolver; request chưa xác minh chỉ được chọn manager đã có trong map.
5. `oauth2ResourceServer(...authenticationManagerResolver(...))` là DSL **reactive**, không phải Servlet DSL.
6. `NoOpServerSecurityContextRepository` tránh persist authentication trong WebSession; mỗi Bearer request cần token riêng.
7. `csrf.disable()` chỉ phù hợp nếu API hoàn toàn **stateless, không dùng cookie/browser credentials được gửi tự động**. Với WebFlux browser login/session, phải giữ CSRF và tách chains; đừng copy disable vào app hỗn hợp.
8. `GET /public` không cần bearer, route tenant private dùng `TenantGuard`, những đường dẫn chưa khai báo bị `denyAll()`.
9. JWT signature validation do decoder đảm nhiệm, không cần trực tiếp parse/verify RSA tại controller.
10. **Không expose một `ReactiveJwtDecoder` bean global mặc định** để tránh nhầm rằng mọi issuer đều dùng cùng bộ validators; resolver đã tự quản các decoders.
11. Vào production, cấu hình trusted issuers là thay đổi security-sensitive: review, change history, monitoring và rollback.
12. App có thể bắt đầu mà không liên hệ .example.test vì decoder lấy JWK Set qua HTTP khi có bearer token cần xác minh. Tuy nhiên **request tới issuer không tồn tại sẽ lỗi**; đây không phải một OP hoạt động được dựng sẵn.

### 8.8. Controller mẫu

`src/main/java/dev/example/trustedissuers/OrdersController.java`:

```java
package dev.example.trustedissuers;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/tenants/{tenant}/orders")
    public Mono<Map<String, String>> orders(
            @PathVariable String tenant,
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.just(Map.of(
                "tenant", tenant,
                "issuer", jwt.getIssuer().toString(),
                "subject", jwt.getSubject(),
                "result", "orders-read-ok"));
    }
}
```

Đây là response demo, không truy cập database. **TenantGuard chạy trước controller**, nên issuer Alpha không được gọi route Beta. Nếu truy xuất đơn hàng thật, service/repository phải **lọc theo tenant/ownership và authorize resource ID**, không chỉ dựa vào endpoint guard.

**Rủi ro dữ liệu:** Response demo hiển thị issuer/subject để người học quan sát. Trong production, chỉ trả những fields được API contract cho phép; không phát raw token, claims không cần thiết hoặc internal issuer metadata.

## 9. Chạy ứng dụng với issuer thật

Với `application.yml` minh họa, chạy:

```bash
gradle bootRun
```

Hoặc `./gradlew bootRun` / `gradlew.bat bootRun` nếu dự án có Gradle Wrapper. Public route có thể gọi:

```bash
curl -i http://localhost:8080/public
```

Dự kiến `200 OK`, body:

```text
public-ok
```

Gọi route bảo vệ mà không có token:

```bash
curl -i http://localhost:8080/api/tenants/alpha/orders
```

Dự kiến `401 Unauthorized`.

**Để thử Bearer JWT thực:**
1. Cấu hình hai issuer/JWKS URLs HTTPS **thật** thay vì .example.test.
2. Mỗi IdP phải phát **signed access token** có `iss` trùng config, `aud=orders-api`, `exp` hợp lệ và `scope=orders:read`.
3. Lưu token test trong một secret store/environment có kiểm soát; không đưa token vào script đã commit, URL hoặc screenshot.
4. Gọi API qua HTTPS trong môi trường thật:

```bash
# ACCESS_TOKEN_ALPHA giả định đã được cấp an toàn ở môi trường test.
curl -i -H "Authorization: Bearer $ACCESS_TOKEN_ALPHA" \
  https://api.example.test/api/tenants/alpha/orders
```

Dự kiến khi token Alpha đúng issuer, chữ ký, thời gian, audience và scope: HTTP **200**. Nếu dùng token Alpha ở URL `/api/tenants/beta/orders`: HTTP **403**. Token từ issuer thứ ba không trong allowlist: **401**. Token issuer đúng nhưng audience của API khác: **401**.

Đây là **kết quả dự kiến theo code và giao thức**; việc kiểm thử access token thật phụ thuộc issuer/JWKS đang hoạt động, certificate/TLS và OP configuration chính xác. Không có dữ liệu token thật trong tài liệu.

## 10. Kiểm thử chữ ký RSA và issuer routing không cần mạng

Một lỗi phổ biến là chỉ viết `mockJwt()` rồi tuyên bố đã test issuer trust. `mockJwt()` tạo Authentication test giả, **bỏ qua signature/decoder**; nó phù hợp kiểm tra quyền nhưng không chứng minh một token được ký bởi đúng issuer.

Ở đây ta viết **unit tests sinh hai cặp RSA key 2048-bit khác nhau**, ký JWT thật bằng `NimbusJwtEncoder`, rồi verify bằng `NimbusReactiveJwtDecoder.withPublicKey(...)` tương ứng issuer. Cách này **không tải JWKS qua HTTP**, nhưng kiểm tra được:
- Chữ ký của issuer A chỉ hợp lệ với public key A.
- Token issuer B hợp lệ với public key B.
- `iss` lạ không có manager trong allowlist.
- Token tự khai `iss=A` nhưng ký bằng key B bị từ chối.
- Audience sai bị từ chối **sau** signature verification.
- Token expired bị từ chối.

Tệp `src/test/java/dev/example/trustedissuers/IssuerRoutingTests.java`:

```java
package dev.example.trustedissuers;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IssuerRoutingTests {

    private static final String ALPHA =
            "https://issuer-alpha.example.test/realm/alpha";
    private static final String BETA =
            "https://issuer-beta.example.test/realm/beta";
    private static final String OTHER =
            "https://untrusted.example.test";

    private static KeyPair alphaKeys;
    private static KeyPair betaKeys;

    @BeforeAll
    static void createKeys() throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        alphaKeys = generator.generateKeyPair();
        betaKeys = generator.generateKeyPair();
    }

    private String sign(
            KeyPair signer,
            String signingKid,
            String claimedIssuer,
            String audience,
            Instant expiresAt) {

        RSAKey signingKey = new RSAKey.Builder(
                (RSAPublicKey) signer.getPublic())
                .privateKey((RSAPrivateKey) signer.getPrivate())
                .keyID(signingKid)
                .build();

        JwtEncoder encoder =
                new NimbusJwtEncoder(
                        new ImmutableJWKSet<SecurityContext>(
                                new JWKSet(signingKey)));

        JwsHeader header =
                JwsHeader.with(SignatureAlgorithm.RS256)
                        .keyId(signingKid)
                        .build();

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(claimedIssuer)
                .subject("test-subject")
                .audience(List.of(audience))
                .issuedAt(Instant.now().minusSeconds(60))
                .expiresAt(expiresAt)
                .claim("scope", "orders:read")
                .build();

        return encoder.encode(
                JwtEncoderParameters.from(header, claims))
                .getTokenValue();
    }

    private ReactiveJwtDecoder decoder(
            RSAPublicKey publicKey,
            String expectedIssuer,
            String expectedAudience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withPublicKey(publicKey)
                        .build();

        decoder.setJwtValidator(
                IssuerRouting.validators(
                        expectedIssuer, expectedAudience));
        return decoder;
    }

    private ReactiveAuthenticationManagerResolver<ServerWebExchange>
            resolver() {

        return IssuerRouting.fromTrustedDecoders(Map.of(
                ALPHA, decoder((RSAPublicKey) alphaKeys.getPublic(),
                        ALPHA, "orders-api"),
                BETA, decoder((RSAPublicKey) betaKeys.getPublic(),
                        BETA, "orders-api")));
    }

    private Mono<Authentication> authenticate(String rawJwt) {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("https://gateway.example.test/api")
                        .header(
                                HttpHeaders.AUTHORIZATION,
                                "Bearer " + rawJwt)
                        .build());

        return resolver().resolve(exchange)
                .flatMap(manager -> manager.authenticate(
                        new BearerTokenAuthenticationToken(rawJwt)));
    }

    private Instant future() {
        return Instant.now().plusSeconds(600);
    }

    @Test
    void alphaTokenSignedByAlphaKeyIsAccepted() {
        String token = sign(alphaKeys, "alpha-key", ALPHA,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertEquals("test-subject", auth.getName());
                    assertTrue(auth.getAuthorities().stream()
                            .anyMatch(granted ->
                                    granted.getAuthority().equals(
                                            "SCOPE_orders:read")));
                })
                .verifyComplete();
    }

    @Test
    void betaTokenSignedByBetaKeyIsAccepted() {
        String token = sign(betaKeys, "beta-key", BETA,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .assertNext(auth ->
                        assertTrue(auth.isAuthenticated()))
                .verifyComplete();
    }

    @Test
    void issuerOutsideAllowlistIsRejected() {
        String token = sign(alphaKeys, "alpha-key", OTHER,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void tokenClaimingAlphaButSignedByBetaIsRejected() {
        String token = sign(betaKeys, "beta-key", ALPHA,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void correctSignatureWrongAudienceIsRejected() {
        String token = sign(alphaKeys, "alpha-key", ALPHA,
                "unrelated-api", future());

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void expiredJwtIsRejected() {
        String token = sign(alphaKeys, "alpha-key", ALPHA,
                "orders-api", Instant.now().minusSeconds(180));

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void malformedBearerValueIsRejected() {
        StepVerifier.create(authenticate("not-a-jws"))
                .expectError()
                .verify();
    }
}
```

Chạy:

```bash
gradle test --tests dev.example.trustedissuers.IssuerRoutingTests
```

**Kết quả dự kiến:** 7 tests thành công với code/dependencies đồng nhất. Chúng dùng RSA signatures thực, không cần HTTP JWKS server. Đây là **kết quả kỳ vọng từ mã**, không phải khẳng định đã chạy Gradle trong workspace của bạn.

### Những giới hạn của suite RSA này

Bộ test sử dụng `withPublicKey(...)` và validators giống production, nhưng **không kiểm tra JWKS URI/TLS/metadata discovery hoặc key rotation của OP thật**, vì không có network. Test production cần issuer/JWKS mock HTTP server được cấu hình đúng, hợp đồng OP thực hoặc E2E gateway.

Nếu một test “unknown issuer” bị từ chối trước khi verify signature, đó là behavior đúng: hệ thống không có manager dành cho issuer lạ. Nếu token khai issuer A nhưng ký bằng key B, resolver phải chọn **manager A** từ allowlist rồi manager A **từ chối signature**. Đây chính là test quan trọng chống key confusion.

## 11. HTTP tests bằng WebTestClient cho tenant isolation

Bộ tests này dùng `mockJwt()` **chỉ để kiểm tra authorization/HTTP behavior** mà không cần hai OP. Nó **bỏ qua resolver và cryptographic decoder**, nên không được dùng để tuyên bố mọi token issuer lạ sẽ nhận 401. Test issuer trust/crypto đã được kiểm tra riêng trong `IssuerRoutingTests` với RSA thật.

Tệp `src/test/java/dev/example/trustedissuers/TenantHttpTests.java`:

```java
package dev.example.trustedissuers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class TenantHttpTests {

    private static final String ALPHA =
            "https://issuer-alpha.example.test/realm/alpha";
    private static final String BETA =
            "https://issuer-beta.example.test/realm/beta";

    @Autowired
    WebTestClient client;

    private WebTestClient authenticated(
            String issuer, String scope) {

        return client.mutateWith(
                mockJwt()
                        .jwt(jwt -> jwt
                                .issuer(issuer)
                                .subject("test-user")
                                .claim("scope", scope))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_" + scope)));
    }

    @Test
    void publicEndpointIsAccessibleWithoutJwt() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateEndpointRequiresAuthentication() {
        client.get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void alphaIssuerCanReadAlphaTenant() {
        authenticated(ALPHA, "orders:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("alpha")
                .jsonPath("$.subject").isEqualTo("test-user");
    }

    @Test
    void betaIssuerCanReadBetaTenant() {
        authenticated(BETA, "orders:read")
                .get().uri("/api/tenants/beta/orders")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("beta");
    }

    @Test
    void alphaIssuerCannotReadBetaTenant() {
        authenticated(ALPHA, "orders:read")
                .get().uri("/api/tenants/beta/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void betaIssuerCannotReadAlphaTenant() {
        authenticated(BETA, "orders:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void correctTenantWithoutRequiredScopeIsForbidden() {
        authenticated(ALPHA, "profile:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unrecognizedIssuerInMockPrincipalDoesNotPassGuard() {
        authenticated("https://unknown.example.test",
                "orders:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        authenticated(ALPHA, "orders:read")
                .get().uri("/api/hidden")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả dự kiến:** 9 HTTP tests cộng với 7 RSA/decoder tests = **16 tests**. Chúng kiểm tra các phạm vi khác nhau:
- `IssuerRoutingTests`: RSA signed JWT, trusted issuer selection, audience, expiration, key confusion.
- `TenantHttpTests`: WebFlux security authorization/path variable, scope và cross-tenant boundaries.
- Test mock `unknown issuer` cho kết quả **403 từ TenantGuard**, không phải 401, vì `mockJwt()` giả lập một Authentication đã thành công. Một **Bearer token thật** với issuer lạ phải bị resolver từ chối ngay trong authentication pipeline và thường nhận 401.

**Không chạy Gradle trong lượt tạo Knowledge này**, nên tất cả test outputs trong tài liệu là dự kiến, không phải actual test report.

### Test bổ sung cần có trước production

1. HTTP integration **không mockJwt**: cung cấp local JWKS HTTP test server/IdP, ký JWT thật, gửi Bearer header qua Gateway.
2. Token issuer A đúng → 200 trên Alpha; issuer B đúng → 200 trên Beta.
3. Issuer ngoài allowlist → 401 và **không có outbound call tới host do token chọn**.
4. Issuer A ký bằng key B → 401.
5. Issuer A nhưng `aud=unrelated-api` → 401.
6. JWT `exp` cũ/`nbf` tương lai → 401.
7. Token A + URL tenant B → 403.
8. Thiếu `scope=orders:read` → 403.
9. Test tải JWKS và rotation `kid`; retry/timeout khi IdP outage.
10. Test duplicate/malformed bearer headers và authorization error normalization.
11. Test resource ownership (order thuộc tenant nào?) ở DB layer.
12. Test rollback khi tắt một issuer, không vô tình mở wildcard trust.

## 12. Security pitfalls của multi-issuer JWT

### 12.1. SSRF qua `iss`

**Tình huống nguy hiểm:** Code gọi issuer discovery cho URL nằm trong token chưa xác minh.

Hậu quả có thể là:
- HTTP requests từ backend tới host attacker.
- Truy cập nhầm metadata nội bộ hoặc cloud metadata endpoints.
- Tin public keys do attacker xuất bản.
- Tạo lượng lớn decoder/HTTP calls để gây cạn tài nguyên.

**Biện pháp:** Allowlist exact `iss` trước khi xây/lấy manager; tốt nhất **pre-register URLs** từ control plane. Không tự lấy `jwks_uri` hay `jku` từ token untrusted. Với dynamic onboarding, cần admin-approved registry, egress allowlist/network policy, URL parsing, DNS and redirect safeguards và quotas.

### 12.2. Algorithm confusion và JWK trust

- Không chấp nhận `alg=none`.
- Không biến JWK RSA public key thành HMAC secret theo header `alg`.
- Không fetch URL `jku` do attacker kiểm soát.
- Chỉ cho phép JWS algorithms phù hợp (trong demo RS256), cùng key use/ID và issuer policy.
- Coi `kid` là **key selector trong JWKS đã chọn**, không phải lựa chọn issuer.
- Validate thư viện JWT, cập nhật khi có CVE.

### 12.3. Token substitution / ID Token dùng như access token

OIDC ID Token có thể mang `iss`, `sub`, `aud` và được ký đúng. Nhưng nó được phát cho **OAuth client**, không phải API resource server. Nếu Resource Server chỉ kiểm tra chữ ký/issuer mà không kiểm tra **audience và token type theo profile**, có thể nhầm ID Token thành access token.

Demo bắt `aud=orders-api`; production nên quy định `typ=at+jwt` theo RFC 9068 nếu issuer dùng profile đó, xem xét `azp`/`client_id` và scopes đúng grant. Không mặc định ID Token có thể dùng thay Bearer API credential.

### 12.4. Mix-up identity giữa các issuers

Hai issuers có thể cùng cấp `sub=123`. Nếu account index chỉ dùng `sub`, user Alpha có thể bị gán vào user Beta. Dùng composite identity `(issuer, subject)`, thêm tenant/owner context và giới hạn authorization của từng resource.

### 12.5. Global vs tenant scope

`scope=orders:read` có thể giống nhau ở A/B nhưng không có nghĩa quyền liên tenant. Scope do issuer đã ký phải được phối hợp với tenant mapping, resource ownership và business policy. Đừng cho route path tự xác định tenant authorization.

### 12.6. Header X-Tenant không phải authentication

Nếu gateway nhận:

```http
GET /api/tenants/beta/orders HTTP/1.1
X-Tenant: beta
Authorization: Bearer <TOKEN_ALPHA>
```

`X-Tenant` có thể giúp chọn context trước authentication **nếu được thiết kế**, nhưng không thể tự nâng quyền. Với demo, token Alpha dù có header `X-Tenant: beta` cũng không được đọc tenant Beta vì `TenantGuard` dựa vào issuer verified và URL tenant.

Nếu proxy chuyển một `X-Verified-Issuer` header, backend **chỉ được tin khi** gateway xác thực token, xóa toàn bộ client-supplied headers trùng tên và có mTLS/network authentication giữa các hops. Client ngoài không được tự giả header này.

### 12.7. Không bỏ qua audience theo issuer

Có thể trong cùng issuer có nhiều access tokens cho API khác nhau. Cấu hình `audience` theo từng issuer, fail closed khi mismatch. Nếu mỗi issuer có `aud` khác nhau, đừng xây một universal audience wildcard. **Token dành cho Billing API không được gọi Orders API chỉ vì nó được ký bởi issuer đã duyệt**.

### 12.8. JWT hết hạn vẫn có thể nằm trong cache

Nếu một gateway cache Authentication hoặc quyết định authz lâu hơn `exp`/revoke SLA, token không còn hợp lệ có thể vẫn được sử dụng trong cache. Giới hạn TTL, cache key theo issuer/token/authz context, không bao giờ cache allow vượt token expiry. Authorization errors và revocation đều cần metrics/refresh policy.

## 13. JWKS discovery, cache và rotation

### Vì sao manager theo issuer có cache?

Public keys thường có thể được fetch từ JWKS và cache để giảm mạng. Cache hợp lệ phải cân bằng:
- OP key rotation (thêm `kid` mới trước khi phát token).
- Network timeout và OP outage.
- Không cho untrusted issuer gây tạo nhiều cache entries.
- Eviction/failure policy, TTL và lifecycle metrics.

**Dòng thời gian rotation chuẩn:**

```text
T0  OP JWKS có key K1, token đang ký bằng K1
T1  OP công bố thêm K2 (JWKS chứa K1 + K2)
T2  OP bắt đầu ký token mới bằng K2
T3  RS cache refresh, có thể verify K2
T4  Sau khi token K1 không còn hợp lệ, OP bỏ K1
```

Nếu OP xóa K1 quá sớm, các token K1 còn trong TTL sẽ fail. Nếu gateway cache key K1 quá lâu sau incident key compromise, có thể tiếp tục chấp nhận token bị giả. Cần rotation policy và emergency response theo threat model.

### Fail-closed và availability

Nếu issuer JWKS endpoint không sẵn:
- Token cần key chưa có trong cache có thể không verify được → request authentication fail.
- Không được fallback sang **key của issuer khác** hoặc “skip signature check”.
- Tránh retry vô hạn và block event loop.
- Dùng timeouts, connection pools và observe p95/p99, error rates.
- Dùng health/readiness phù hợp với số issuers, không đánh dấu toàn gateway vô dụng chỉ vì một tenant không hoạt động nếu service policy cho phép các tenants còn lại phục vụ.

### Caching theo issuer chính xác

Cache key phải gắn với **issuer/JWK URI/algorithm/kid** phù hợp, tránh trộn keys giữa issuers hoặc tenants. Nếu registry thay đổi dynamic, invalidation phải xử lý atomically, versioned config và audit.

## 14. Dynamic onboarding/offboarding issuer

Mô hình allowlist tĩnh có lợi thế dễ kiểm toán; nhưng gateway nhiều khách hàng có thể cần thêm/xóa tenant không restart. Hãy thiết kế **control plane**:

1. Admin xác minh danh tính OP, issuer URI và liên hệ khách hàng/tenant.
2. Kiểm tra HTTPS/TLS, exact issuer, metadata/JWKS URI, audience và thuật toán.
3. Kiểm tra issuer không bị gán trùng tenant trái thiết kế.
4. Phê duyệt bản ghi (issuer, tenant, jwks, aud, key policy) rồi lưu trong kho được phân quyền.
5. Tạo decoder/manager **chỉ từ approved record**, không từ JWT chưa xác minh.
6. Publish configuration version/atomic snapshot tới các gateway instances.
7. Health-check issuer readiness, test sample signed JWT.
8. Audit người thêm, sửa, disable; có rollback.
9. Offboard: xóa manager/kênh trust, clear caches, kiểm tra request bằng JWT issuer cũ bị 401.
10. Đảm bảo stale nodes/regions không tiếp tục cho phép issuer bị tắt quá SLA.

Spring Security docs gợi ý constructor `JwtIssuerReactiveAuthenticationManagerResolver` có resolver lấy manager từ một repository có thể chỉnh runtime. Nhưng repository này phải **có allowlist/trust validation**. Không dùng lambda:

```java
// ANTI-PATTERN: issuer từ JWT chưa verify được dùng như URL tùy ý.
issuer -> Mono.just(
        new JwtReactiveAuthenticationManager(
                ReactiveJwtDecoders.fromIssuerLocation(issuer)))
```

Khi cần thêm issuer, manager phải được tạo từ **policy record đã duyệt**; không để resolver tự động chấp nhận bất kỳ `iss` nào nhìn thấy.

### Tenant disable khác key rotation

- **Disable issuer/tenant:** cần làm tất cả tokens của issuer đó bị từ chối mới, kể cả ký đúng. Xóa trust record và đẩy config mới khắp gateway.
- **Rotate JWK key:** vẫn giữ issuer hợp lệ, chỉ thay key set theo OP.
- **Revoke token cá nhân:** JWT self-contained không tự hỗ trợ tức thời; cần jti denylist/introspection/authz_version tùy SLA.
- **Xóa quyền của user:** JWT scope snapshot có thể stale; cần current-state authorization nếu yêu cầu hiệu lực ngay.

## 15. Reactive WebFlux: tránh blocking và quản trị lỗi

### 15.1. Không block event loop

`ReactiveJwtDecoder` và `ReactiveAuthenticationManagerResolver` hoạt động trong reactive pipeline. Không dùng `.block()`, `Thread.sleep` hay JDBC sync trực tiếp trong auth filter.

Nếu tenant registry lấy từ database:
- Dùng R2DBC/reactive Redis/WebClient.
- Hạn chế concurrency và đặt timeout; đừng retry vô hạn với nguồn identity.
- Chọn cách cache managers theo approved registry snapshots.
- Repository errors không được biến thành “accept token anyway”.
- Không sử dụng `subscribe()` tự phát trong security chain; Spring quản lý subscription.

### 15.2. Tại sao 401 và 403 phải rõ?

Nếu JWT issuer lạ nhưng app trả 403 “permission denied”, monitoring có thể nhầm authentication failure thành authorization failure. Theo pipeline:
- Resolver không tìm được trusted issuer/manager hoặc decoder reject → 401.
- Authenticated Jwt nhưng tenant/path/scope không hợp lệ → 403.
- Public route → 200 dù không Bearer.
- Lỗi JWKS unavailable có thể thành 401/5xx theo framework/cause handling; API không được tiết lộ key endpoints hoặc token.

Đừng viết catch-all `onErrorResume(e -> allow)`. Nếu muốn custom error response, giữ semantics Bearer-token authentication, `WWW-Authenticate` header khi phù hợp, không đưa thông tin nhạy cảm vào body.

### 15.3. Proxy/Gateway forwarding

Nếu gateway chỉ xác thực ở edge rồi forward request:
- Có mTLS hoặc network identity cho edge → backend.
- Backend không tin `X-User`/`X-Tenant` do client ngoài có thể giả.
- Gateway phải strip/sanitize headers do client cung cấp trước khi thêm verified identity.
- Cần thiết kế token forwarding hay identity-propagation rõ ràng; nếu backend cần verify JWT độc lập, gửi đúng token hoặc token exchange.
- CORS preflight không chứa Bearer token; xử lý CORS trước authentication nếu browser clients được hỗ trợ.
- Không đưa raw Authorization vào logs, traces, cache key public hoặc metrics labels.

### 15.4. Logging đa tenant

Log an toàn chỉ nên gồm:
- request ID/correlation ID,
- route/template, status code,
- issuer alias (đã allowlist) hoặc tenant ID sau xác thực,
- authorization outcome code, latency, cache hit/miss, key ID nếu audit policy cho phép.

**Không log:** raw JWT, signature, headers Authorization, raw unverified `iss` không sanitize, full JWK material ngoài public data cần thiết, email/PII từ claims, full exception messages chứa token.

## 16. Phân tích các anti-pattern

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Nhận mọi issuer rồi discovery từ `iss` | Token attacker tự khai issuer và public key | Exact approved allowlist/registry |
| `iss.startsWith("https://idp")` | Prefix/hostname/path confusion | Exact string match tới issuer metadata |
| Dùng 1 decoder mà không kiểm tra issuer | Token của key source không đúng policy có thể lọt | Per-issuer validators |
| Chỉ kiểm tra chữ ký mà bỏ `aud` | Token dành cho API khác được dùng ở đây | Expected audience |
| Dùng `kid` làm URL tìm key | JKU/KID injection/SSRF | Key select trong trusted JWKS |
| Dùng `sub` làm global user ID | Trùng user IDs giữa issuers | Composite (iss, sub) identity |
| Có `scope=orders:read` là cho mọi tenants | Cross-tenant IDOR | TenantGuard + DB ownership |
| Tin `X-Tenant` từ client như verified claim | Header spoofing | Verified issuer/tenant policy |
| Chấp nhận ID Token cho API | Token substitution | Access-token audience/type validation |
| Gộp trusted issuer A/B trong một global wildcard JWKS | Key confusion | Manager và keys theo issuer |
| Cho unknown issuer tạo manager mới | Dynamic trust/DoS/SSRF | Deny unknown; admin onboarding |
| Tắt validation khi OP outage | Fail-open nghiêm trọng | Fail closed, reliability policy |
| Không test cross-signed JWT | Không phát hiện key confusion | Signed RSA tests A/B |
| Chỉ test `mockJwt()` | Bypass decoder, không test signature | Unit signed JWT + HTTP auth tests |
| Bật CSRF disable toàn app browser | Bỏ bảo vệ cookie-auth actions | Tách chains/CSRF theo client model |
| Không đặt expiry/nbf checks | Token stale/future có thể chạy | JwtValidators + clock skew policy |
| Trust config được sửa bởi người dùng tenant | Cho phép tự phê duyệt issuer | Admin control plane, review/audit |

## 17. Checklist triển khai production

- [ ] Danh sách issuer có nguồn **đáng tin**, do operator/admin quản trị, version/audit rõ.
- [ ] Unknown `iss` bị từ chối, **không gọi discovery từ issuer chưa cho phép**.
- [ ] `JwtIssuerReactiveAuthenticationManagerResolver` được dùng đúng **WebFlux**; không nhầm Servlet.
- [ ] Mỗi issuer mapping đúng JWKS/key source, algorithm policy và validators.
- [ ] JWT chữ ký phải được verify **trước khi tin claims để cấp quyền**.
- [ ] `iss` exact match được validate rõ, không chỉ “đã chọn manager”.
- [ ] `exp` và `nbf`/clock skew được validate với contract rõ.
- [ ] `aud` phải đúng resource server và từng issuer/tenant policy.
- [ ] Nếu dùng RFC 9068, token type `at+jwt` và claims profile được xem xét.
- [ ] Không tin `jku`/`x5u`/`kid` ngoài trusted key source.
- [ ] Không lấy tenant chỉ từ URL/query/header; phải đối chiếu verified identity và policy.
- [ ] `scope` không thay quyền ownership ở DB/resource level.
- [ ] Principal/audit keys kết hợp issuer+subject; không collision multi issuer.
- [ ] TLS/hostname validation ở mọi hop/JWKS fetch; outbound egress có giới hạn.
- [ ] Duy trì JWKS cache/rotation policy và emergency key compromise process.
- [ ] Issuer disable/offboard có cơ chế xóa trust/caches và rollout toàn cluster.
- [ ] Revocation/permission changes có freshness SLA riêng nếu JWT self-contained.
- [ ] Không block event loop khi lấy key/registry, không có unbounded retry.
- [ ] 401/403 và error responses không rò raw tokens/claims/keys.
- [ ] Không log Authorization/raw JWT, query token, unverified issuer nguyên văn.
- [ ] Test thật hai RSA issuers, cross-key, unknown issuer, audience sai, exp/nbf.
- [ ] Test cross-tenant URL/ownership và missing scope trên gateway.
- [ ] Test nhiều nodes, JWKS cache miss/rotation/outage và control-plane updates.
- [ ] Nâng cấp Spring Security đã vá advisory (đặc biệt issuer validation) và chạy regression suite.

## 18. Câu hỏi tự kiểm tra

**1. Có thể tin `iss` ngay sau khi Base64 decode JWT không?**  
Không. Nó là claim chưa verify, chỉ có thể dùng làm gợi ý chọn **manager đã được tin**, không để cấp quyền.

**2. `JwtIssuerReactiveAuthenticationManagerResolver` làm nhiệm vụ gì?**  
Đọc `iss` từ bearer token để chọn `ReactiveAuthenticationManager` phù hợp trong kiến trúc multi-issuer reactive.

**3. `fromTrustedIssuers(...)` được lợi gì?**  
Tạo resolver chỉ chấp nhận issuers được allowlist và khởi tạo/lấy các managers lazily theo tài liệu.

**4. Vì sao issuer phải match chính xác?**  
Chống prefix/path/hostname confusion và bảo đảm token thuộc issuer đã đăng ký.

**5. Chỉ kiểm tra chữ ký đủ chưa?**  
Chưa. Cần issuer, expiry/nbf, audience, token type/scope và authorization theo tenant/resource.

**6. Key của issuer A có được dùng verify token tự khai `iss=B` không?**  
Không. Manager B phải dùng key source B; cross-signed token bị reject.

**7. `kid` có vai trò gì?**  
Chọn một key trong JWKS đáng tin; không phải quyền tự fetch arbitrary key URL.

**8. Vì sao `aud` rất quan trọng?**  
Ngăn token phát cho API/client khác bị dùng tại API hiện tại.

**9. Nếu cùng issuer phục vụ 10 tenant thì dùng issuer làm tenant ID được không?**  
Không. Cần verified tenant claim và current membership/resource authorization.

**10. Hai issuer cùng có `sub=123` là cùng user không?**  
Không tự động. Dùng composite identity `(iss, sub)`.

**11. Token A đủ `orders:read` có đọc tenant B được không?**  
Không nếu TenantGuard và business policies kiểm tra cross-tenant.

**12. Unknown issuer phải trả gì?**  
Authentication failure 401, không đi tìm metadata của issuer tùy ý.

**13. `mockJwt()` có kiểm tra chữ ký không?**  
Không. Nó giả lập một authenticated JWT principal để test authorization.

**14. Làm sao kiểm tra key confusion thật?**  
Ký JWT bằng private key B nhưng khai `iss=A`, xác nhận decoder manager A reject chữ ký.

**15. `NimbusReactiveJwtDecoder.withJwkSetUri` có tự biết issuer expected không?**  
Không; phải cấu hình issuer validator rõ ràng.

**16. Nếu JWKS endpoint downtime, có nên bỏ qua signature check không?**  
Không. Fail closed với thông tin lỗi an toàn; có cache/reliability policy riêng.

**17. Issuer whitelist được update từ user input có an toàn không?**  
Không. Việc trust issuer là control-plane change cần phân quyền, validation, review và audit.

**18. JWT valid nhưng không có scope cần thiết trả 401 hay 403?**  
Thường 403 vì đã authenticate nhưng không được authorize.

**19. Vì sao cần test egress khi unknown issuer?**  
Để bảo đảm code không dùng `iss` chưa tin làm URL và gây SSRF.

**20. JWT đã ký đúng có tự phản ánh quyền user vừa bị xóa không?**  
Không. Self-contained claims là snapshot; cần revocation/current-state check nếu muốn tức thời.

### Bài tập thực hành

1. Sử dụng `IssuerRoutingTests`, sửa token Alpha khai Beta nhưng ký Alpha. Giải thích vì sao routing chọn manager Beta và chữ ký bị reject.
2. Thêm issuer Gamma vào app config và registry được duyệt; viết signed-RSA test Gamma hợp lệ, unknown Delta bị reject.
3. Thay expected audience Alpha thành `billing-api`; dùng token `orders-api` và quan sát lỗi.
4. Tạo một JWT `nbf` trong tương lai và test authentication failure theo timestamp validator.
5. Thử `iss` có trailing slash hoặc khác path; kiểm tra exact matcher không tự chuẩn hóa.
6. Thêm claim `tenant_id` cho mô hình shared issuer, đối chiếu với tenant/path/resource ownership sau verify.
7. Tạo token Alpha và Beta cùng `sub=employee-1`; thiết kế composite identity key.
8. Dùng local JWKS HTTP test server và signed tokens, gửi Bearer qua WebTestClient không mock auth; kiểm tra 200/401/403.
9. Giả lập JWKS rotation từ K1 → K2, kiểm tra key cache behavior trước/sau refresh.
10. Giả lập issuer B unavailable; verify token A không cần gọi B và request B fail-closed.
11. Thiết kế quy trình disable issuer A, test mọi instance ngừng chấp nhận token A sau rollout.
12. Đánh giá vì sao `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` đủ cho use case đơn giản nhưng cần registry riêng khi audience/JWKS không đồng nhất.
13. Kiểm tra trong DevTools/proxy log không chứa raw Authorization header.
14. Cấu hình trusted proxy và bảo đảm client không giả verified tenant headers.
15. Viết policy cho **scope + tenant + order ownership**, không chỉ scope claim.
16. Tạo alert cho tỷ lệ 401 unknown issuer tăng bất thường nhưng không lưu raw untrusted issuer/token.
17. Xem CVE-2026-22748 và giải thích vì sao cần gọi `setJwtValidator(JwtValidators.createDefaultWithIssuer(...))` khi dựng decoder tùy biến trên version cũ.
18. So sánh multi-issuer gateway với việc tách một Resource Server per tenant về isolation, latency, operations và blast radius.

## 19. Tài liệu chính thức

- [Spring Security — Reactive Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): `JwtIssuerReactiveAuthenticationManagerResolver`, trusted issuers, dynamic managers và warning về untrusted issuers.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): chữ ký, issuer/exp/nbf, `ReactiveJwtDecoder`, validators và audience.
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/site/docs/6.2.3/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html): `fromTrustedIssuers` và constructor repository manager.
- [Spring Security API 6.3 — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): `withJwkSetUri`, `withPublicKey` và `setJwtValidator`.
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, custom reactive authorization.
- [Spring Security API — AuthorizationContext](https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/web/server/authorization/AuthorizationContext.html): URI path variables qua `getVariables()`.
- [Spring Security — Reactive OAuth2 Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` test authorization, không test decoder signature.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `@ConfigurationProperties` và map binding.
- [Spring Security Advisory CVE-2026-22748](https://spring.io/security/cve-2026-22748): rủi ro thiếu issuer validation khi cấu hình decoder theo issuer trên các bản chưa vá.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `nbf`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key confusion, JWT substitution và validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token type, audience và access-token claims.
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer và JWK Set metadata.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): TLS, authn/authz và token validation.

**Ghi nhớ:** Trong gateway nhiều tenant, `iss` từ JWT **chưa xác minh chỉ là gợi ý chọn manager**. Server phải chọn **duy nhất những issuers trong allowlist do mình quản lý**, rồi dùng decoder/keys đúng issuer để **verify chữ ký, exact issuer, `exp/nbf`, audience và token profile**. Chỉ sau authentication mới dùng claims/authorities để **authorize tenant và resource**; JWT hợp lệ của Alpha không được tự truy cập Beta. **Không bao giờ** tạo discovery/JWKS URL từ issuer tùy ý trong token.