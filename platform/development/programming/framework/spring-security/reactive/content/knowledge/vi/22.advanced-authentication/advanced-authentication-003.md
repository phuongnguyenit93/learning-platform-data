# Triển khai ReactiveAuthenticationManager cho API key

## 1. Bối cảnh, mục tiêu và phạm vi

Bài học thuộc phần **Xác thực mở rộng** của **Spring Security - reactive / Spring WebFlux**.

Nhiều API dành cho dịch vụ tích hợp, scheduled jobs, CLI hoặc đối tác sử dụng **API key**: một chuỗi bí mật được client gửi kèm request, ví dụ bằng HTTP header `X-API-Key`. Server cần kiểm tra khóa có tồn tại, đúng bí mật, còn hiệu lực, chưa bị thu hồi và mang những quyền cụ thể. Với Spring Security WebFlux, có thể đưa cơ chế này vào **authentication pipeline chuẩn** thay vì tự viết một `WebFilter` gán principal tùy ý.

Ba thành phần chính:
- **`ServerAuthenticationConverter`**: lấy credential từ HTTP request, tạo `Authentication` **chưa được xác thực**.
- **`ReactiveAuthenticationManager`**: kiểm tra credential qua repository/service bất đồng bộ, trả `Authentication` **đã xác thực** hoặc báo lỗi.
- **`AuthenticationWebFilter`**: nối converter với manager, đưa kết quả vào reactive `SecurityContext` và xử lý thành công/thất bại.

Sau bài học bạn có thể:

1. Giải thích API key là **bearer secret**, không phải JWT có claims hay một mật khẩu người dùng.
2. Hiểu hợp đồng `Mono<Authentication>` của `ReactiveAuthenticationManager.authenticate(...)`: `Mono.just` khi hợp lệ, `Mono.empty` khi manager không xử lý loại `Authentication` đó, `Mono.error(AuthenticationException)` khi credential của loại mình hỗ trợ nhưng sai.
3. Thiết kế API key gồm **public key ID** và **secret ngẫu nhiên ≥256 bit**, lưu **digest** thay vì raw API key; kiểm tra hash bằng so sánh constant-time.
4. Viết custom `ApiKeyAuthenticationToken` với trạng thái **unauthenticated → authenticated**, không đưa secret vào principal hay authorities.
5. Viết `ServerAuthenticationConverter` đọc `X-API-Key`, từ chối header rỗng, quá dài, lặp lại hoặc sai định dạng.
6. Viết `ReactiveAuthenticationManager` không `block()`, không gọi I/O đồng bộ trên Netty event loop, đọc key record, kiểm tra `enabled`, `expiresAt` và authorities.
7. Cấu hình `AuthenticationWebFilter` qua `ServerHttpSecurity.addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`, stateless security context và chính sách 401/403.
8. Chạy ví dụ **Java 17+, Spring Boot 3.3.5**, dùng Gradle, curl và kiểm thử `StepVerifier` + `WebTestClient`.
9. Xác định giới hạn của demo lưu trong memory, cách thay bằng Redis/R2DBC, xoay vòng/thu hồi key, rate limit, audit, TLS và phòng lộ key qua logs/proxy.
10. Phân biệt authentication API key với authorization theo scope, ownership, tenant và các tình huống tích hợp browser/CORS/CSRF.

**Quan trọng:** Bản demo dùng **một API key được cấp lúc khởi động qua biến môi trường** và repository trong một JVM để tập trung học pipeline. Đây không phải giải pháp quản lý key production: production phải có provisioning an toàn, store chia sẻ, trạng thái revocation, audit, rotation, giới hạn quyền và mô hình consistency.

## 2. API key dùng để làm gì?

Một client tích hợp có thể gửi:

```http
GET /api/data HTTP/1.1
Host: api.example.test
X-API-Key: ak_demo_<SECRET_BASE64URL>
Accept: application/json
```

`<SECRET_BASE64URL>` là ký hiệu tài liệu, **không phải một khóa thực**. Server không nên đưa key vào query parameter:

```http
GET /api/data?api_key=real-secret HTTP/1.1
```

vì query dễ bị ghi vào access logs, browser history, analytics, Referer hoặc support screenshots. Tránh đưa API key vào URL, log và response body. Luôn dùng **HTTPS/TLS hợp lệ** khi gửi key trên mạng; HTTP trên localhost chỉ dành cho demo.

### API key, HTTP Basic, OAuth2 và JWT khác nhau thế nào?

| Cơ chế | Credential | Cách kiểm tra | Phạm vi sử dụng |
| --- | --- | --- | --- |
| API key | Secret ứng dụng được cấp từ hệ thống | Lookup key ID, kiểm tra secret + status + quyền | Machine-to-machine, partner integration |
| HTTP Basic | Username/password hoặc một đôi credential | UserDetails/password validation | Legacy API/protocol, cần TLS |
| OAuth2 Client Credentials | Access token cấp qua Authorization Server | JWT verification hoặc introspection | Delegated/service authorization có vòng đời token |
| JWT bearer | Signed token có claims/time/audience | Signature/issuer/audience/expiry | Self-contained access token |
| Opaque bearer token | Chuỗi không tự giải mã | Online token introspection | Central token status/revocation |

**API key thường là bearer credential:** ai sở hữu đủ chuỗi key có thể thử dùng nó cho tới khi key hết hạn/bị revoke. Không tự có MFA, claims ký số, auto-expiry hoặc rotation; các tính năng này phải được thiết kế trong server-side key registry.

### Không nhầm authentication với authorization

**Authentication:** “Chuỗi `ak_demo_...` có thực sự thuộc về client `demo-client` và còn hiệu lực không?”

**Authorization:** “Client `demo-client` có được gọi `GET /api/data` hoặc `POST /api/admin` không? Có quyền trên tenant/resource đang yêu cầu không?”

Trong Spring Security, bước authentication tạo authorities như `SCOPE_data:read`. Sau đó `authorizeExchange(...)` hoặc method/business authorization đánh giá authorities và dữ liệu hiện hành. Một API key đúng **không đương nhiên được làm mọi việc**.

## 3. Luồng xử lý của Spring Security reactive

```text
HTTP request
      |
      v
WebFlux SecurityWebFilterChain
      |
      v
AuthenticationWebFilter
      |
      +--> requiresAuthenticationMatcher("/api/**")?
      |         |
      |        Không -> bỏ qua filter
      |         |
      |        Có
      |         v
      |    ApiKeyHeaderConverter
      |         |
      |         +-- Không có header -> Mono.empty()
      |         |    (chưa xác thực, authorization phía sau xử lý)
      |         |
      |         +-- Header sai/duplicate -> AuthenticationException
      |         |
      |         v
      |    ApiKeyAuthenticationToken (authenticated=false)
      |         |
      |         v
      |    ApiKeyReactiveAuthenticationManager.authenticate(...)
      |         |
      |         +-- Không hỗ trợ loại token -> Mono.empty()
      |         +-- Key sai/disabled/expired -> Mono.error(...)
      |         +-- Key đúng -> Mono<Authentication> đã authenticated
      |         |
      |         v
      |    AuthenticationWebFilter đưa kết quả vào Reactor Context
      |
      v
authorizeExchange:
    authenticated / hasAuthority / denyAll
      |
      +-- Không xác thực --> 401
      +-- Có xác thực, thiếu quyền --> 403
      +-- Có quyền --> Controller
```

### Vì sao không chỉ viết một WebFilter custom và set header?

Spring Security đã cung cấp:
- Phân biệt **authentication failure** và **authorization denial**.
- Chuẩn hóa `Authentication`, `GrantedAuthority`, `ReactiveSecurityContextHolder`.
- Đặt authentication trong **Reactor Context**, phù hợp reactive pipeline.
- Tương thích `@PreAuthorize` (khi bật reactive method security), `ServerHttpSecurity.authorizeExchange`, tests và security entry points.
- Hạn chế việc tự viết một filter không kiểm tra đầy đủ trạng thái key hoặc đánh dấu `authenticated=true` trước khi xác minh.

Nếu chỉ kiểm tra header trong controller, các route mới rất dễ quên validation; nếu chỉ có `permitAll()` ở chain rồi tự bảo vệ từng endpoint, sai sót có thể làm lộ API. Đưa authentication vào filter chain và **deny by default** giúp an toàn hơn.

### Reactor Context không phải ThreadLocal trực tiếp

Trong WebFlux, authentication thường được lan truyền qua `ReactiveSecurityContextHolder`/Reactor Context. Đừng dùng `SecurityContextHolder.getContext()` kiểu ThreadLocal truyền thống trong custom reactive code rồi kỳ vọng luôn đúng qua `publishOn`/`flatMap`. Hãy để `AuthenticationWebFilter` thiết lập context; controller có thể nhận `Principal` hoặc service dùng reactive context.

## 4. Hợp đồng của ReactiveAuthenticationManager

Interface:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Ba kết quả cần hiểu chính xác:

| Trường hợp | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Manager xác thực thành công credential thuộc loại nó hỗ trợ | `Mono.just(authenticatedAuthentication)` | Principal và authorities đã được xác minh |
| Manager **không hỗ trợ** loại `Authentication` này | `Mono.empty()` | Không quyết định; manager khác có thể xử lý nếu được ghép |
| Manager hỗ trợ loại này nhưng credential **sai, hết hạn hoặc bị thu hồi** | `Mono.error(AuthenticationException)` | Authentication thất bại, trả 401 qua failure handler |
| Repository/network bị lỗi | Thường propagate error, quản lý policy riêng | Không được xem lỗi store là “key đúng” |

**Phân biệt rất quan trọng:** Không dùng `Mono.empty()` cho **API key sai**. Đối với một chain có nhiều authentication managers, empty có thể khiến manager khác thử tiếp hoặc thiếu thông tin về lỗi. Không dùng `Mono.just(authentication)` để trả lại token **unauthenticated**, vì đó không phải xác thực thành công.

### Một manager tối giản (minh họa, không phải source hoàn chỉnh)

```java
@Override
public Mono<Authentication> authenticate(Authentication candidate) {
    if (!(candidate instanceof ApiKeyAuthenticationToken token)
            || token.isAuthenticated()) {
        return Mono.empty(); // Không xử lý loại này
    }
    return keyRepository.findById(...)
            .flatMap(record -> verifyThenBuildAuthentication(record, token));
}
```

Đây là **fragment mô tả hợp đồng**; source runnable có ở phần 9 và không dùng biến `...`. Nó cho thấy đường phân nhánh theo **loại authentication** trước khi đọc key registry.

### Đánh dấu authenticated đúng thời điểm

Một custom `Authentication` thường có hai trạng thái:
- **Trước authentication:** principal chưa được tin cậy; credentials mang raw API key; `isAuthenticated() == false`; authorities rỗng.
- **Sau authentication:** principal là client ID/identity xác minh bởi repository; credentials **null/đã xóa**; `isAuthenticated() == true`; authorities được server cấp theo record, **không lấy từ HTTP header**.

Không cho request header chứa `role=ADMIN` hoặc `scope=admin:write` rồi tự biến thành authority: client có thể tự khai báo quyền. Authorities phải đến từ **trusted server-side metadata**.

## 5. Thiết kế API key an toàn

### 5.1. Tách public identifier và secret

Một format thuận tiện:

```text
ak_<keyId>_<base64url-of-32-random-bytes>
```

Ví dụ `ak_demo_...`, trong đó:
- `ak_` là prefix giúp phân biệt loại credential.
- `keyId` là identifier dùng lookup, **không phải bí mật**. Đề bài demo giới hạn 1–32 ký tự chữ, số hoặc dấu `-`.
- Phần secret chứa **32 bytes ngẫu nhiên từ SecureRandom** (256 bit entropy), Base64URL không padding thành 43 ký tự.

Lợi ích:
1. Tra cứu bản ghi theo key ID thay vì quét toàn bộ các hashes.
2. Có thể revoke/rotate từng key riêng.
3. Có thể audit theo **key ID** (không lưu raw key).
4. Có thể kiểm tra quyền theo client, expiry, tenant và policy.

**Điểm cần nhớ:** Prefix/key ID **không** tạo thêm bảo mật nếu secret đoán được. Cần 256 bit ngẫu nhiên thực; không dùng `password123`, timestamp, UUID theo tên, email, số thứ tự hoặc `Math.random()` làm secret.

### 5.2. Chỉ lưu digest của secret

Ví dụ bảng dữ liệu logic:

| Trường | Ý nghĩa | Có phải secret? |
| --- | --- | --- |
| `key_id` | Định danh public | Không |
| `client_id` | Principal được xác thực | Không trực tiếp |
| `secret_sha256_hex` | Digest của 32 bytes secret | Dữ liệu bảo mật, không công bố |
| `scopes` | Quyền máy chủ cấp | Không được tin từ request |
| `enabled` | Trạng thái thu hồi/khóa | Chính sách nội bộ |
| `expires_at` | Thời điểm hết hạn | Chính sách nội bộ |
| `tenant_id` | Tenant/phạm vi | Dữ liệu nghiệp vụ |
| `created_at`/`last_used_at` | Audit không chứa raw secret | Theo retention/privacy |

Vì secret **được tạo ngẫu nhiên đủ entropy**, SHA-256 của bytes secret có thể dùng làm verifier không phải dạng password hash chậm. Với **mật khẩu do con người chọn**, phải dùng password hashing thích hợp (Argon2/bcrypt/scrypt) vì entropy thấp; đừng sao chép cách hash API key sang lưu password.

Một số hệ thống dùng **HMAC-SHA-256 với server-side pepper** để bổ sung lớp bảo vệ nếu database verifier bị lộ. Khi đó phải quản lý pepper qua KMS/secret manager, hỗ trợ rotation và versioning. Không coi SHA-256 là encryption; raw key chỉ hiện một lần khi provisioning, không được truy xuất lại từ database.

### 5.3. So sánh digest constant-time

Sai:

```java
// ANTI-PATTERN: so sánh String chứa raw secret/digest một cách tùy tiện.
if (storedSecret.equals(rawApiKeyFromRequest)) {
    // allow
}
```

Đúng hơn cho verifier digest có độ dài cố định:

```java
byte[] expectedDigest = HexFormat.of().parseHex(storedSha256Hex);
byte[] actualDigest = MessageDigest
        .getInstance("SHA-256")
        .digest(secretBytes);
boolean same = MessageDigest.isEqual(expectedDigest, actualDigest);
```

Đây là **fragment**; phải xử lý `NoSuchAlgorithmException`, metadata lookup, expiry và identity, như source đầy đủ ở phần 9. `MessageDigest.isEqual` tránh so sánh byte-by-byte ngây thơ, nhưng **không tự ngăn** timing leaks từ việc key ID có tồn tại hay không. Nếu threat model yêu cầu chống enumeration qua timing, có thể hash against dummy digest cả khi key ID không tồn tại, thống nhất lỗi client và rate-limit.

### 5.4. Một key tương ứng những quyền nào?

Với API key cho ứng dụng tích hợp:
- Client identity: `demo-client`, không phải một user trong browser.
- Authorities: `SCOPE_data:read`, không phải `ROLE_ADMIN` trừ khi business policy quy định.
- Tenant/owner: nếu nhiều tenant, metadata phải chứa phạm vi tenant và business layer xác nhận resource.
- Allowed routes/methods: có thể được mô tả bằng policy authorization.
- Expiration/revocation: phải được tra mỗi request hoặc cache với SLA rõ.
- Rate limit/quota: key ID + client/tenant; tránh attacker tạo vô hạn token thử sai.

Cấp **least privilege**. Không dùng một API key quản trị toàn hệ thống cho mọi đối tác.

## 6. API key là bearer secret: nguy cơ thường bị bỏ qua

| Rủi ro | Cơ chế | Phòng ngừa |
| --- | --- | --- |
| Lộ qua logs | Access log, reverse proxy, APM ghi headers | Redact `X-API-Key`, không ghi Authorization/cookies |
| Lộ qua URL | Key đặt trong query | Chỉ dùng header, tránh URL/history |
| Lộ qua Git/CI | Hardcode key trong source/env output | Secret manager, scanning, rotation |
| Replay khi bị đánh cắp | Bearer key dùng lại từ client khác | TLS, TTL/revocation, ràng buộc mạng/mTLS khi cần |
| Brute-force/credential stuffing | Thử key yếu hoặc ID có thể đoán | 256-bit CSPRNG, 401 generic, rate limit |
| Rò verifier digest | Database backup bị lộ | High-entropy secret, hạn chế quyền DB, HMAC pepper tùy threat model |
| Excessive scopes | Một key có quyền quá rộng | Least privilege, allowlist scopes/tenant |
| Key dùng mãi | Không có expiry/rotation | Expiry, rotate/revoke, audit last use |
| Multiple instances | In-memory registry không chia sẻ | Redis/R2DBC/central registry có consistency |
| Blocking lookup | JDBC blocking trên Netty event loop | Reactive driver/WebClient, timeout |
| API key ở frontend public | Browser JS bundle có secret | Không nhúng shared secret vào SPA/mobile binary |
| Header proxy không truyền | Gateway xóa `X-API-Key` | Kiểm tra hop, schema và secret-redaction |
| Browser preflight OPTIONS bị 401 | CORS chưa chạy trước auth | Cấu hình WebFlux CORS chính xác |
| Đánh đồng API key với user login | Bỏ tenant/user authorization | Client identity và rights riêng |

Nếu API key nằm trong ứng dụng JavaScript chạy trên trình duyệt, người dùng có thể đọc nó qua DevTools/bundle. **Không dùng shared server API key để bảo vệ dữ liệu riêng cho từng browser user**; cân nhắc OAuth2/OIDC với PKCE, backend-for-frontend hoặc session authentication phù hợp.

## 7. Thiết kế WebFlux theo ba lớp

### 7.1. Converter chỉ làm việc với giao thức HTTP

`ApiKeyHeaderConverter`:
- Chỉ đọc header `X-API-Key`.
- Trả `Mono.empty()` khi **header vắng mặt**, vì converter không tạo authentication attempt.
- Trả `AuthenticationException` khi header hiện diện nhưng malformed/duplicate.
- Tạo `ApiKeyAuthenticationToken.request(rawKey)` **chưa xác thực**.
- Không truy vấn database, không kiểm tra scopes, không gán `authenticated=true`.

Nhờ tách converter, bạn có thể test parsing mà không dựng cả Spring context.

### 7.2. Manager chỉ làm việc với credential và key metadata

`ApiKeyReactiveAuthenticationManager`:
- Nhận đúng loại `ApiKeyAuthenticationToken` đang unauthenticated.
- Phân tích key format có giới hạn độ dài/characters.
- Tính digest phần secret.
- Gọi `ReactiveApiKeyRepository.findById(keyId)` trả `Mono<ApiKeyRecord>`.
- So sánh digest constant-time, kiểm tra enabled/expiry.
- Trả principal `clientId` và authorities từ bản ghi tin cậy, raw credentials = null.
- Sai key/disabled/expired/unknown → `BadCredentialsException` generic.
- Không hỗ trợ loại Authentication khác → `Mono.empty()`.
- Lỗi store → propagate; không im lặng cho phép request.

### 7.3. Filter quản lý context và failure behavior

`AuthenticationWebFilter`:
- Chỉ chạy trên `/api/**` (matcher) để không đọc key trên public route.
- Tích hợp manager và converter.
- Dùng `NoOpServerSecurityContextRepository` để không lưu authentication giữa requests.
- 401 generic khi invalid key; authorization layer trả 403 khi key valid nhưng thiếu quyền.
- Gắn vào `SecurityWebFiltersOrder.AUTHENTICATION` **trước authorization filter**.
- Không tự gọi `subscribe()`, `block()` hoặc ThreadLocal authentication setter.

Một điều có thể gây nhầm: `.authenticationManager(manager)` của `ServerHttpSecurity` cấu hình một default manager, nhưng **không tự tạo API key header converter/filter**. Để xử lý custom `X-API-Key`, demo tạo `AuthenticationWebFilter` tường minh.

## 8. Phân biệt kết quả 401/403 và các tình huống HTTP

| Request | Authentication stage | Authorization stage | HTTP mong đợi |
| --- | --- | --- | --- |
| GET `/public`, không header | Filter chỉ match `/api/**` nên bỏ qua | `permitAll` | 200 |
| GET `/api/data`, không key | Converter `Mono.empty()` | Yêu cầu authenticated/scope | 401 |
| GET `/api/data`, key sai | Manager lỗi `BadCredentialsException` | Không tiếp tục | 401 |
| GET `/api/data`, key expired/disabled | Manager từ chối generic | Không tiếp tục | 401 |
| GET `/api/data`, key hợp lệ có `data:read` | Tạo authenticated principal | `SCOPE_data:read` có | 200 |
| POST `/api/admin`, key hợp lệ chỉ có `data:read` | Auth thành công | Thiếu `SCOPE_admin:write` | 403 |
| GET `/api/data` sau một GET trước đó dùng key, request này không header | Không có auth mới, không session | Thiếu auth | 401 |
| GET `/api/unknown` | Có thể auth thành công | `denyAll` | 403 nếu đã auth, 401 nếu anonymous |

**Không dùng HTTP 200 cùng một JSON “error invalid key”**: nó làm middleware/caches/clients hiểu sai status. Không tiết lộ “ID này tồn tại”, “digest sai”, “key disabled” hay scopes nội bộ trong response 401; server có thể audit reason nội bộ theo mã an toàn **không chứa key**.

## 9. Dự án chạy được: Spring Boot 3.3.5 + WebFlux + Java 17

Ví dụ này gồm:
- Key format `ak_<id>_<Base64URL(32 random bytes)>`.
- CLI nhỏ sinh một API key demo (in ra **một lần** để provisioning, không dùng cho production).
- Repository in-memory chỉ giữ SHA-256 digest, client ID, scopes, enabled/expiry.
- Custom Authentication token (unauthenticated/verified).
- Converter cho `X-API-Key` và reactive manager.
- Stateless `SecurityWebFilterChain` với route GET và POST minh họa.
- Unit tests cho manager + HTTP tests qua WebTestClient.

### 9.1. Cấu trúc thư mục

```text
reactive-api-key-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/apikey/
    │   │   ├── ApiKeyApplication.java
    │   │   ├── ApiKeyMaterial.java
    │   │   ├── ApiKeyAuthenticationToken.java
    │   │   ├── ApiKeyRecord.java
    │   │   ├── ReactiveApiKeyRepository.java
    │   │   ├── DemoApiKeyRepository.java
    │   │   ├── ApiKeyReactiveAuthenticationManager.java
    │   │   ├── ApiKeyHeaderConverter.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DemoController.java
    │   │   └── DemoApiKeyGenerator.java
    │   └── resources/application.yml
    └── test/java/dev/example/apikey/
        ├── ApiKeyReactiveAuthenticationManagerTests.java
        └── ApiKeyHttpTests.java
```

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-api-key-demo'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Không thêm `spring-boot-starter-web` vào demo thuần WebFlux.** Nếu có cả MVC và WebFlux starters, Spring Boot thường chọn Servlet/MVC stack, khi đó WebFlux security classes không khớp ý định.

### 9.3. Runtime configuration

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

demo:
  api-key: ${DEMO_API_KEY}
```

Ứng dụng demo **yêu cầu** biến môi trường `DEMO_API_KEY` đã được tạo bằng `DemoApiKeyGenerator`. Nếu biến chưa có hoặc key sai định dạng, ứng dụng nên **fail at startup**, không tự phát hành một credential cố định nguy hiểm.

Với production, thay demo property bằng nguồn provisioning/store bảo mật: KMS/secret manager, key registry, DB encrypted at rest và digest; không đọc tất cả raw keys qua environment rồi giữ vô hạn trong memory.

### 9.4. Entry point

`src/main/java/dev/example/apikey/ApiKeyApplication.java`:

```java
package dev.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyApplication.class, args);
    }
}
```

### 9.5. Key parser và SHA-256 digest

`src/main/java/dev/example/apikey/ApiKeyMaterial.java`:

```java
package dev.example.apikey;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.security.authentication.BadCredentialsException;

public final class ApiKeyMaterial {

    private static final Pattern FORMAT = Pattern.compile(
            "^ak_([A-Za-z0-9-]{1,32})_([A-Za-z0-9_-]{43})$");

    private ApiKeyMaterial() {
    }

    public record Parts(String keyId, byte[] secretBytes) {
        public Parts {
            secretBytes = secretBytes.clone();
        }

        @Override
        public byte[] secretBytes() {
            return secretBytes.clone();
        }
    }

    public static Parts parse(String rawKey) {
        if (rawKey == null || rawKey.length() > 128) {
            throw new BadCredentialsException("Invalid API key");
        }

        Matcher matcher = FORMAT.matcher(rawKey);
        if (!matcher.matches()) {
            throw new BadCredentialsException("Invalid API key");
        }

        String secretEncoded = matcher.group(2);
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(secretEncoded);
        } catch (IllegalArgumentException ex) {
            throw new BadCredentialsException("Invalid API key");
        }

        // 32 random bytes, canonical Base64URL without padding.
        if (bytes.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(secretEncoded)) {
            throw new BadCredentialsException("Invalid API key");
        }

        return new Parts(matcher.group(1), bytes);
    }

    public static byte[] sha256(byte[] secretBytes) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(secretBytes);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is unavailable in this JVM", ex);
        }
    }

    public static String digestHex(byte[] secretBytes) {
        return HexFormat.of().formatHex(sha256(secretBytes));
    }
}
```

**Các biện pháp bảo vệ:**
- Regex giới hạn key ID, Base64URL secret và độ dài.
- Phân tích raw key chỉ sau khi qua converter; không log raw string.
- Secret phải giải mã đúng **32 bytes**, dùng Base64URL canonical để loại những cách biểu diễn khác nhau cùng bytes.
- Java `record Parts` sao chép mảng khi nhận/trả để giảm khả năng sửa dữ liệu qua tham chiếu ngoài.
- `SHA-256` tính digest trên **random secret bytes**, không trên password con người. `HexFormat` Java 17 chuyển bytes sang hex cho DB verifier.
- `BadCredentialsException` cho key malformed là authentication failure, không phải lỗi 500.
- Digest không bao gồm public keyId vì repository đã lookup theo ID; production có thể HMAC/pepper nếu cần.

**Lưu ý:** Mảng raw secret và chuỗi key vẫn tồn tại tạm trong heap; Java không bảo đảm xóa ngay mọi chuỗi khỏi memory. Giảm thời gian tồn tại, tránh copy/log, bảo vệ heap dumps và secret management.

### 9.6. Tạo Authentication token riêng

`src/main/java/dev/example/apikey/ApiKeyAuthenticationToken.java`:

```java
package dev.example.apikey;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private ApiKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {

        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    public static ApiKeyAuthenticationToken request(String rawKey) {
        return new ApiKeyAuthenticationToken(
                "unverified-api-key", rawKey, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {

        return new ApiKeyAuthenticationToken(
                clientId, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        this.credentials = null;
        super.eraseCredentials();
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                    "Use verified(...) factory after authentication");
        }
        super.setAuthenticated(false);
    }
}
```

**Giải thích:**
- `request(rawKey)` tạo token với `authenticated=false`, principal chỉ là nhãn “unverified”; **raw credential không được coi là identity**.
- Chỉ manager sau khi verify key record mới gọi `verified(clientId, authorities)`. Constructor private dùng `super.setAuthenticated(...)`; code bên ngoài không thể chuyển từ false sang true bằng `setAuthenticated(true)`.
- Verified token **không mang raw API key** (`credentials=null`). Điều này giảm nguy cơ leak khi debug authentication.
- `getName()` kế thừa từ `AbstractAuthenticationToken` trả tên principal đã được xác minh.
- Đừng log `authentication` hoặc serialize security context. Không trả authentication object trực tiếp trong JSON.

Một custom token có thể chọn principal là một immutable `ApiClientPrincipal` record gồm id/tenant, nhưng phải giới hạn fields và không chứa secret. Demo chọn String `clientId` để dễ quan sát.

### 9.7. Key record và reactive repository

`src/main/java/dev/example/apikey/ApiKeyRecord.java`:

```java
package dev.example.apikey;

import java.time.Instant;
import java.util.Set;

public record ApiKeyRecord(
        String keyId,
        String clientId,
        String secretSha256Hex,
        Set<String> scopes,
        boolean enabled,
        Instant expiresAt) {

    public ApiKeyRecord {
        scopes = Set.copyOf(scopes);
    }
}
```

`src/main/java/dev/example/apikey/ReactiveApiKeyRepository.java`:

```java
package dev.example.apikey;

import reactor.core.publisher.Mono;

public interface ReactiveApiKeyRepository {
    Mono<ApiKeyRecord> findByKeyId(String keyId);
}
```

Repository là **abstraction tự định nghĩa**, không phải built-in Spring interface. Nó tách manager khỏi hạ tầng persistence; thay `DemoApiKeyRepository` bằng adapter reactive Redis/R2DBC mà không đổi security filter.

### 9.8. Repository demo chỉ lưu digest

`src/main/java/dev/example/apikey/DemoApiKeyRepository.java`:

```java
package dev.example.apikey;

import java.time.Instant;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

import reactor.core.publisher.Mono;

@Repository
public final class DemoApiKeyRepository
        implements ReactiveApiKeyRepository {

    private final Map<String, ApiKeyRecord> records;

    public DemoApiKeyRepository(
            @Value("${demo.api-key}") String demoKey) {

        ApiKeyMaterial.Parts parts =
                ApiKeyMaterial.parse(demoKey);

        ApiKeyRecord record = new ApiKeyRecord(
                parts.keyId(),
                "demo-client",
                ApiKeyMaterial.digestHex(parts.secretBytes()),
                Set.of("data:read"),
                true,
                Instant.MAX);

        records = Map.of(record.keyId(), record);
    }

    @Override
    public Mono<ApiKeyRecord> findByKeyId(String keyId) {
        return Mono.justOrEmpty(records.get(keyId));
    }
}
```

Repository:
- Nhận raw key **một lần lúc app startup** chỉ để demo và lưu digest. Không viết raw key vào database/log.
- `Map.of` cố định, chỉ có một key và scope `data:read`.
- `Mono.justOrEmpty(...)` tuân theo reactive repository contract.
- `Instant.MAX` nghĩa là demo không tự hết hạn; **production phải có expiry và revocation thật**.
- Không có API tạo/xóa/xoay key vì đây là bài xác thực, không phải hệ thống secret provisioning đầy đủ.
- Không dùng store này cho multi-instance production: mỗi restart/provisioning mới có thể thay key và state không đồng bộ.

**Tùy chọn production:** Lưu digest đã tạo lúc provisioning trong DB và **không** nạp raw key từ environment. Cho phép admin tạo key mới có expiry, hiển thị một lần, lưu hash, rotate với grace window có kiểm soát và revoke khi cần.

### 9.9. ReactiveAuthenticationManager

`src/main/java/dev/example/apikey/ApiKeyReactiveAuthenticationManager.java`:

```java
package dev.example.apikey;

import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class ApiKeyReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveApiKeyRepository repository;

    public ApiKeyReactiveAuthenticationManager(
            ReactiveApiKeyRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<Authentication> authenticate(
            Authentication authentication) {

        if (!(authentication instanceof ApiKeyAuthenticationToken token)
                || token.isAuthenticated()) {
            // Loại Authentication khác -> manager này không xử lý.
            return Mono.empty();
        }

        return Mono.defer(() -> {
            String rawKey = (String) token.getCredentials();
            ApiKeyMaterial.Parts presented =
                    ApiKeyMaterial.parse(rawKey);
            byte[] candidateDigest =
                    ApiKeyMaterial.sha256(presented.secretBytes());

            return repository.findByKeyId(presented.keyId())
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException(
                                    "Invalid API key")))
                    .flatMap(record -> {
                        byte[] expectedDigest = HexFormat.of()
                                .parseHex(record.secretSha256Hex());

                        boolean matches = MessageDigest.isEqual(
                                expectedDigest, candidateDigest);
                        boolean active = record.enabled()
                                && Instant.now().isBefore(
                                        record.expiresAt());

                        if (!matches || !active) {
                            return Mono.<Authentication>error(
                                    new BadCredentialsException(
                                            "Invalid API key"));
                        }

                        List<SimpleGrantedAuthority> authorities =
                                record.scopes().stream()
                                        .map(scope ->
                                                new SimpleGrantedAuthority(
                                                        "SCOPE_" + scope))
                                        .toList();

                        return Mono.<Authentication>just(
                                ApiKeyAuthenticationToken.verified(
                                        record.clientId(),
                                        authorities));
                    });
        });
    }
}
```

**Phân tích từng bước:**

1. Kiểm tra token **đúng type và chưa authenticated**. Nếu không phải API key token, trả `Mono.empty()` vì manager không nhận trách nhiệm.
2. `Mono.defer(...)` trì hoãn việc parse và hash cho đến subscription; không tự `subscribe()` hoặc `block()`.
3. `ApiKeyMaterial.parse(...)` đảm bảo định dạng có giới hạn. Parse lỗi tạo `BadCredentialsException` trong reactive subscription.
4. `sha256(...)` tạo digest bytes của secret; không so trực tiếp raw key với dữ liệu trong DB.
5. Repository tìm record theo `keyId`. Nếu không có, manager trả **authentication error**, không trả empty.
6. `MessageDigest.isEqual` so sánh verifier digest với candidate digest theo cách tránh so sánh ngây thơ; hai digest SHA-256 có chiều dài bằng nhau.
7. Check `enabled` và `expiresAt` tại lúc request được xử lý. Với production, một bản ghi stale cache vẫn có thể cho quyền cũ; thiết kế cache/revocation SLA.
8. Scopes chỉ lấy từ **server-side record**, rồi map sang `SCOPE_data:read`. Không nhận scope nào từ header của client.
9. Thành công trả `ApiKeyAuthenticationToken.verified(...)`, principal `demo-client`, credentials **null**, authenticated true.
10. Sai secret, disabled hoặc expired đều trả **cùng một message**: `Invalid API key`. Failure handler phía HTTP không tiết lộ nguyên nhân chi tiết.
11. Nếu repository lỗi thật, Mono error được propagate; không biến thành `Mono.just(verified)`. Production phân biệt lỗi hạ tầng với credential sai trong monitoring an toàn.
12. SHA-256 trên 32 bytes là CPU-bound rất nhỏ; repository I/O phải có reactive driver. Nếu chuyển sang sync JDBC và gọi trực tiếp trong `flatMap`, bạn có thể làm nghẽn Netty event loop.
13. Phần `record.scopes()` và expiry được đọc từ metadata đáng tin, không xây quyền từ `clientId` string do request cung cấp.
14. Demo chỉ yêu cầu account-level active status; business authorization trên từng resource/tenant vẫn phải được thực hiện riêng.

**Vấn đề không được che giấu:** Nếu key ID không tồn tại, đoạn code trả lỗi trước bước so hash; thời gian phản hồi có thể khác. Đối với môi trường nhạy cảm, cân nhắc dummy digest work, thống nhất thời gian/response trong giới hạn hợp lý, nhưng vẫn phải rate-limit và giám sát abuse. Không dùng random sleeps làm thay thế kiểm soát thực.

### 9.10. ServerAuthenticationConverter cho X-API-Key

`src/main/java/dev/example/apikey/ApiKeyHeaderConverter.java`:

```java
package dev.example.apikey;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class ApiKeyHeaderConverter
        implements ServerAuthenticationConverter {

    private static final String HEADER = "X-API-Key";

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> values =
                exchange.getRequest().getHeaders().get(HEADER);

        // Không có credential -> filter không thử authentication.
        // Route yêu cầu key sẽ nhận 401 ở authorization layer.
        if (values == null || values.isEmpty()) {
            return Mono.empty();
        }

        if (values.size() != 1) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        String rawKey = values.get(0);

        // Khóa có cấu trúc chính xác được kiểm ở manager.
        // Chặn sớm giá trị rỗng/quá dài/comma-joined headers.
        if (rawKey == null || rawKey.isBlank()
                || rawKey.length() > 128
                || rawKey.indexOf(',') >= 0) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        return Mono.just(
                ApiKeyAuthenticationToken.request(rawKey));
    }
}
```

**Những case cần lưu ý:**
- `X-API-Key` không có: converter empty. Security route vẫn yêu cầu principal, nên trả 401.
- Header có mặt nhưng malformed: trả lỗi 401 generic.
- Header bị lặp hoặc proxy gộp bằng dấu comma: từ chối, không lấy “giá trị đầu tiên” tùy ý.
- Không đọc secret từ URL query hay cookie để tránh những kênh rò rỉ.
- Converter chỉ kiểm header/path và **không gán quyền**.
- Key ID/secret vẫn được validate mạnh hơn trong `ApiKeyMaterial.parse`.

Một số reverse proxies có thể canonicalize tên HTTP header; `X-API-Key` thường case-insensitive theo HTTP. Kiểm thử end-to-end qua gateway thật, không cho gateway log giá trị header.

### 9.11. Cấu hình AuthenticationWebFilter và SecurityWebFilterChain

`src/main/java/dev/example/apikey/SecurityConfig.java`:

```java
package dev.example.apikey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ApiKeyReactiveAuthenticationManager manager) {

        var noSession =
                NoOpServerSecurityContextRepository.getInstance();
        var unauthorized =
                new HttpStatusServerEntryPoint(
                        HttpStatus.UNAUTHORIZED);

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(manager);

        apiKeyFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        apiKeyFilter.setServerAuthenticationConverter(
                new ApiKeyHeaderConverter());

        apiKeyFilter.setSecurityContextRepository(noSession);

        apiKeyFilter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        unauthorized));

        return http
                .securityContextRepository(noSession)
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler((exchange, error) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.FORBIDDEN);
                            return exchange.getResponse().setComplete();
                        }))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/data")
                            .hasAuthority("SCOPE_data:read")
                        .pathMatchers(HttpMethod.POST, "/api/admin")
                            .hasAuthority("SCOPE_admin:write")
                        .anyExchange().denyAll())
                .addFilterAt(
                        apiKeyFilter,
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
```

**Vì sao cấu hình này quan trọng?**

1. `AuthenticationWebFilter` tích hợp đúng framework authentication pipeline. Không tự viết một WebFilter “set authenticated=true” trước khi xác minh.
2. `setRequiresAuthenticationMatcher(...)` chỉ kích hoạt converter cho `/api/**`; `/public` không yêu cầu key.
3. `setServerAuthenticationConverter(...)` dùng API **WebFlux** (khác Servlet `AuthenticationConverter`).
4. `NoOpServerSecurityContextRepository` được đặt ở cả filter và `ServerHttpSecurity`: authentication không được persist giữa requests. **Mỗi request mới phải trình key**.
5. `ServerAuthenticationEntryPointFailureHandler` chuyển failure của API key filter thành 401 generic, không browser redirect tới form login.
6. `exceptionHandling.authenticationEntryPoint(unauthorized)` làm route bị bảo vệ nhưng thiếu credential trả 401. `accessDeniedHandler` làm credential hợp lệ nhưng thiếu authority trả 403.
7. `authorizeExchange` phân biệt `GET /api/data` (đòi `SCOPE_data:read`) và `POST /api/admin` (đòi `SCOPE_admin:write`). Demo key chỉ có scope đọc nên POST admin phải 403.
8. `anyExchange().denyAll()` fail closed đối với đường dẫn/method chưa khai báo.
9. `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)` đặt custom filter vào đúng phase, trước authorization. Không đặt auth filter phía sau controller hoặc authorization.
10. `httpBasic/formLogin/logout.disable()` cho demo header-only API không có cơ chế xác thực/đăng xuất khác. Nếu kết hợp OAuth2 Resource Server hoặc browser login, phải thiết kế matcher/manager resolver/multiple chains rõ ràng.
11. `csrf.disable()` **chỉ áp dụng cho API hoàn toàn stateless, dùng API key được client tự đặt trong custom header, không dùng browser session/cookie credentials**. Không copy cho ứng dụng browser có cookie/session mà không đánh giá CSRF.
12. `NoOpServerSecurityContextRepository` không có nghĩa server hoàn toàn không lưu state: key registry/digest, rotation/revocation và rate limits **vẫn là state phía server**.

### 9.12. Controller minh họa 200 và 403

`src/main/java/dev/example/apikey/DemoController.java`:

```java
package dev.example.apikey;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicRoute() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/data")
    public Mono<Map<String, String>> readData(Principal principal) {
        return Mono.just(Map.of(
                "client", principal.getName(),
                "message", "data-read-ok"));
    }

    @PostMapping("/api/admin")
    public Mono<String> adminOperation() {
        return Mono.just("admin-ok");
    }
}
```

- `Principal` trong `readData` do Spring WebFlux lấy từ security context. Giá trị là `demo-client` của verified Authentication, **không** phải secret của key.
- `adminOperation` tồn tại để mô phỏng hành động yêu cầu `SCOPE_admin:write`; demo key không có scope này nên request không đến controller.
- Trong ứng dụng thật, có thể cần kiểm tra tenant/resource ownership ngoài authority. Không dùng client ID đơn thuần để truy cập tài nguyên của mọi tenant.

### 9.13. CLI sinh API key demo với SecureRandom

`src/main/java/dev/example/apikey/DemoApiKeyGenerator.java`:

```java
package dev.example.apikey;

import java.security.SecureRandom;
import java.util.Base64;

public final class DemoApiKeyGenerator {

    private DemoApiKeyGenerator() {
    }

    public static void main(String[] args) {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);

        // Chỉ hiển thị một lần để tạo credential thử nghiệm.
        // KHÔNG in credential sống trong ứng dụng production.
        System.out.println("ak_demo_" + encoded);
    }
}
```

Build và tạo key một lần:

```bash
gradle classes
java -cp build/classes/java/main dev.example.apikey.DemoApiKeyGenerator
```

Output có dạng (đã **cố ý không chứa giá trị secret thật** trong tài liệu):

```text
ak_demo_<43_KY_TU_BASE64URL_NGAU_NHIEN>
```

Sao chép key vừa tạo vào **secret store/environment của môi trường local**, không commit trong repo, không gửi cho người khác, không đăng vào chat. Nếu đã hiện key trong terminal, hãy lưu ý terminal logs/scrollback và hạn chế thu thập debug recordings. Trong production, provisioning phải thực hiện ở một hệ thống riêng, chỉ trả raw key **một lần** cho người được cấp.

## 10. Chạy demo với curl

Cần **Java 17+**, Gradle 8.x tương thích và một biến môi trường `DEMO_API_KEY` đã thiết lập. Sau khi tạo key và đặt vào môi trường phù hợp:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows).

Lệnh dưới đây dùng biến shell `DEMO_API_KEY` **đã được đặt**, không đưa raw credential vào tài liệu. Với production key, hạn chế truyền trực tiếp trong shell flags có thể bị lộ qua process list, debug traces và terminal history. Một cách test tốt hơn trong môi trường bảo mật là HTTP client đọc secret từ secret manager và không ghi request headers.

### 10.1. Public route

```bash
curl -i http://localhost:8080/public
```

Dự kiến `200 OK` và body:

```text
public-ok
```

### 10.2. Thiếu API key

```bash
curl -i http://localhost:8080/api/data
```

Dự kiến `401 Unauthorized`, không redirect đến trang đăng nhập HTML.

### 10.3. Key hợp lệ

```bash
curl -i -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/data
```

Dự kiến `200 OK` và JSON chứa:

```json
{
  "client": "demo-client",
  "message": "data-read-ok"
}
```

JSON thực có thể khác thứ tự fields; Map không cam kết order.

### 10.4. Key sai

```bash
curl -i -H 'X-API-Key: definitely-invalid' \
  http://localhost:8080/api/data
```

Dự kiến `401 Unauthorized`, không tiết lộ key ID có tồn tại hay không.

### 10.5. Key hợp lệ nhưng thiếu scope

```bash
curl -i -X POST \
  -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/admin
```

Dự kiến `403 Forbidden`. Manager xác thực thành công `demo-client`, nhưng `authorizeExchange` yêu cầu `SCOPE_admin:write` mà record chỉ có `SCOPE_data:read`.

### 10.6. Request kế tiếp không kế thừa identity

```bash
curl -i -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/data
curl -i http://localhost:8080/api/data
```

Kỳ vọng request thứ nhất `200`, request thứ hai `401`. Không có một “login session” được tạo bởi API key authentication. Nếu bạn thấy request thứ hai `200` dù không header, kiểm tra security context repository, gateway tự gắn header hoặc một cơ chế authentication khác đang tham gia.

**Các HTTP outcomes trong bài là kỳ vọng theo source code, chưa phải kết quả đã chạy trong workspace của bạn.** Với production, luôn dùng HTTPS: mã ở đây dùng HTTP localhost chỉ để dạy luồng.

## 11. Unit tests: ReactiveAuthenticationManager

Để kiểm tra **chính manager**, không cần chạy Spring Boot hay WebFlux HTTP server. Dùng `StepVerifier` và một `DemoApiKeyRepository` tạo trực tiếp với test key. **Secret toàn-zero bytes chỉ là fixture test** để có định dạng hợp lệ, tuyệt đối không được phát hành làm key thực.

Tệp `src/test/java/dev/example/apikey/ApiKeyReactiveAuthenticationManagerTests.java`:

```java
package dev.example.apikey;

import java.time.Instant;
import java.util.Base64;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiKeyReactiveAuthenticationManagerTests {

    private static final byte[] TEST_BYTES = new byte[32];

    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(TEST_BYTES);

    private static final String KEY = "ak_demo_" + SECRET;

    private ApiKeyReactiveAuthenticationManager manager() {
        return new ApiKeyReactiveAuthenticationManager(
                new DemoApiKeyRepository(KEY));
    }

    @Test
    void validKeyProducesAuthenticatedPrincipalAndAuthorities() {
        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request(KEY)))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertEquals("demo-client", auth.getName());
                    assertNull(auth.getCredentials());
                    assertTrue(auth.getAuthorities().stream()
                            .anyMatch(authority ->
                                    authority.getAuthority().equals(
                                            "SCOPE_data:read")));
                })
                .verifyComplete();
    }

    @Test
    void wrongSecretForExistingKeyIdFails() {
        byte[] other = new byte[32];
        other[0] = 1;
        String wrong = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(other);

        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request(wrong)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unknownKeyIdFailsWithAuthenticationException() {
        String unknown = "ak_unknown_" + SECRET;

        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request(unknown)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void malformedKeyIsRejected() {
        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request("bad-key")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedAuthenticationTypeReturnsEmptyMono() {
        Authentication differentType =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "user", "password");

        StepVerifier.create(manager().authenticate(differentType))
                .verifyComplete();
    }

    @Test
    void disabledKeyIsRejected() {
        String digest = ApiKeyMaterial.digestHex(TEST_BYTES);
        ReactiveApiKeyRepository disabledRepository =
                keyId -> Mono.just(new ApiKeyRecord(
                        keyId,
                        "disabled-client",
                        digest,
                        Set.of("data:read"),
                        false,
                        Instant.MAX));

        var target = new ApiKeyReactiveAuthenticationManager(
                disabledRepository);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void expiredKeyIsRejected() {
        String digest = ApiKeyMaterial.digestHex(TEST_BYTES);
        ReactiveApiKeyRepository expiredRepository =
                keyId -> Mono.just(new ApiKeyRecord(
                        keyId,
                        "expired-client",
                        digest,
                        Set.of("data:read"),
                        true,
                        Instant.EPOCH));

        var target = new ApiKeyReactiveAuthenticationManager(
                expiredRepository);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void repositoryErrorIsNotSilentlyAccepted() {
        ReactiveApiKeyRepository failedRepository =
                ignored -> Mono.error(
                        new IllegalStateException("store unavailable"));

        var target = new ApiKeyReactiveAuthenticationManager(
                failedRepository);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(IllegalStateException.class)
                .verify();
    }
}
```

**Kỳ vọng:** 8 unit tests thành công theo code. Tests xác nhận:
1. Key đúng tạo principal/authority đã xác thực, không giữ raw credentials.
2. Cùng key ID nhưng secret sai gây authentication error.
3. Key ID chưa cấp gây error (không phải `Mono.empty()`).
4. Format sai bị chặn.
5. Manager trả `Mono.empty()` cho authentication type nó không xử lý.
6. Record disabled/expired bị từ chối.
7. Store outage **không** được biến thành authenticated principal.

**Điểm quan trọng:** Đây là test về contract của manager, không chứng minh HTTPS, proxy redaction, CORS, multi-node revocation, entropy của key production hoặc kiểm soát tenant. Chúng cần test riêng.

## 12. HTTP integration tests bằng WebTestClient

Dùng `@SpringBootTest(RANDOM_PORT)` để chạy cả **AuthenticationWebFilter + manager thật + repository demo + authorization rules**, không mock JWT/token và không bypass security chain.

Tệp `src/test/java/dev/example/apikey/ApiKeyHttpTests.java`:

```java
package dev.example.apikey;

import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiKeyHttpTests {

    // CHỈ LÀ TEST FIXTURE: zero bytes không có entropy,
    // tuyệt đối không dùng làm production API key.
    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(new byte[32]);

    private static final String VALID_KEY =
            "ak_demo_" + SECRET;

    @DynamicPropertySource
    static void demoProperties(DynamicPropertyRegistry registry) {
        registry.add("demo.api-key", () -> VALID_KEY);
    }

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutApiKey() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void protectedEndpointWithoutKeyIs401() {
        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyGetsDataAndVerifiedClientIdentity() {
        client.get().uri("/api/data")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.client").isEqualTo("demo-client")
                .jsonPath("$.message").isEqualTo("data-read-ok");
    }

    @Test
    void malformedKeyIs401() {
        client.get().uri("/api/data")
                .header("X-API-Key", "invalid")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void keyWithUnknownIdIs401() {
        client.get().uri("/api/data")
                .header("X-API-Key", "ak_unknown_" + SECRET)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongSecretWithKnownIdIs401() {
        byte[] other = new byte[32];
        other[0] = 1;

        String wrong = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(other);

        client.get().uri("/api/data")
                .header("X-API-Key", wrong)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void duplicatedApiKeyHeadersAreRejected() {
        client.get().uri("/api/data")
                .headers(headers -> {
                    headers.add("X-API-Key", VALID_KEY);
                    headers.add("X-API-Key", VALID_KEY);
                })
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyWithoutAdminScopeIs403() {
        client.post().uri("/api/admin")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void successfulRequestDoesNotCreateAuthenticationSession() {
        client.get().uri("/api/data")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        client.get().uri("/api/unknown")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

**Kết quả dự kiến:** 10 HTTP tests thành công. Mỗi test có mục tiêu riêng:
- Public không yêu cầu key.
- Protected endpoint thiếu key → 401.
- Key hợp lệ → 200, principal đúng từ record.
- Malformed/unknown/wrong secret → 401.
- Duplicate headers → 401, không lấy giá trị đầu tiên.
- Authenticated nhưng thiếu scope admin → 403.
- Không có WebSession authentication được lưu từ request trước.
- Unknown route fail closed.

**Lưu ý về status của route chưa khai báo:** Demo dùng `anyExchange().denyAll()`. Với một principal đã được xác thực, truy cập `/api/unknown` sẽ bị 403 bởi security policy trước khi Spring MVC/WebFlux routing trả 404. Đây là hành vi dự kiến của policy, không phải lỗi controller thiếu mapping.

### Chạy toàn bộ tests

```bash
gradle test
```

**Dự kiến:** 18 tests (8 manager tests + 10 WebTestClient tests) với các files và dependencies trên. Đây là **kỳ vọng từ ví dụ**, không phải tuyên bố đã chạy Gradle ở máy của bạn; hãy kiểm tra test report trên workspace thực trước khi đưa vào sản phẩm.

### Test nào chứng minh điều gì?

| Phạm vi test | Chứng minh | Chưa chứng minh |
| --- | --- | --- |
| `StepVerifier` của manager | Mono contract, hash/expiry/enabled và authorities | WebFilter ordering, HTTP responses |
| `WebTestClient` | Converter → manager → security chain → authorization HTTP | Multi-instance production, TLS/proxy |
| Duplicate/unknown key | Key parser và error status | Timing side-channel không tồn tại |
| No session test | Request thứ hai không tự được authenticated | Mọi gateway/proxy không tự chèn key |
| Admin 403 | Authn thành công nhưng không có scope admin | Business ownership/tenant isolation |
| Production security audit | Requires dedicated E2E tests | Không thể suy từ unit tests |

**Không dùng `mockUser()` hoặc một fake security context cho toàn bộ HTTP suite rồi tuyên bố đã kiểm thử API key authentication**. Một test mock principal có thể bỏ qua converter/manager, dẫn đến false confidence. Suite trên gửi header thật đến embedded WebFlux server và dùng repository demo được cấu hình riêng qua `@DynamicPropertySource`.

## 13. Tại sao status 401/403 cần cấu hình tường minh?

### 401 Unauthorized

Ba tình huống:
- Không gửi `X-API-Key` nhưng route yêu cầu key.
- Gửi key không đúng format/không tồn tại/digest sai.
- Key bị disabled hoặc expired.

Mục tiêu là cùng một client-visible status **401** (không leak chi tiết record). Không cần chuyển browser đến trang login, vì đây là machine-to-machine API.

### 403 Forbidden

Credential đã được xác minh và client có principal, nhưng route yêu cầu một authority không có trong key record. Ví dụ `SCOPE_admin:write` không thuộc scope của `demo-client`.

**Thận trọng:** Nếu bạn đặt key không hợp lệ và thấy 403, có thể filter không chạy đúng, hoặc exception handling đang coi anonymous là access denied. Kiểm tra matcher, filter order, entry point, các authentication schemes khác và tests.

### 5xx khi store lỗi

Database/Redis timeout không nên bị mô tả là “key sai” nếu không có bằng chứng; production response có thể là generic 503/500, nhưng API tuyệt đối không tiết lộ database names, raw key, stack trace hoặc internal host. Cần alert và metrics nội bộ, không tự động **fail open** cho endpoint nhạy cảm.

### Không nhầm empty Mono

- Converter `Mono.empty()` khi header vắng mặt → không có authentication attempt.
- Manager `Mono.empty()` khi **không hỗ trợ loại Authentication** → manager chưa quyết định; nếu là multi-manager chain, delegate khác có thể xử lý.
- Manager `Mono.error(BadCredentialsException)` khi **API key sai** → thất bại và phải dừng flow.
- Manager `Mono.just(verified)` khi **API key đúng** → success, có principal/authorities.

Đây là một trong những điểm quan trọng nhất của đề bài.

## 14. Nâng demo lên hệ thống production

### 14.1. Provisioning key không phải một API tự do

Khi tạo key mới:
1. Authentication và authorization admin/operator trước khi cấp key.
2. Tạo **32 random bytes** bằng CSPRNG, tạo key ID duy nhất.
3. Chọn client/tenant, scopes tối thiểu, expiration, rate limit/quota.
4. Tính digest/HMAC và lưu verifier, không lưu raw key.
5. Hiển thị raw API key **một lần** cho chủ key qua kênh bảo mật.
6. Audit người cấp key, thời điểm, policy, key ID — không log raw key.
7. Khuyến khích lưu trong secret manager và hạn chế dùng key trong CLI flags/CI logs.

**Không dùng demo generator/seed từ môi trường để vận hành mọi đối tác**, vì demo không có CRUD lifecycle, authorization cho provisioning, audit và store nhiều keys.

### 14.2. Schema và repository reactive thực

Một bảng logic:

```sql
CREATE TABLE api_keys (
    key_id             VARCHAR(32) PRIMARY KEY,
    client_id          VARCHAR(120) NOT NULL,
    secret_sha256_hex  CHAR(64) NOT NULL,
    enabled            BOOLEAN NOT NULL,
    expires_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    tenant_id          VARCHAR(120) NOT NULL,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Scope có thể lưu trong bảng phụ `api_key_scopes` hoặc dạng được normalize phù hợp DB. SQL trên là **schema minh họa**, không phải migration đủ cho mọi DB (indexes, precision, constraints, audit và encryption vẫn tùy hệ thống).

Triển khai `ReactiveApiKeyRepository.findByKeyId` bằng:
- R2DBC reactive repositories/client, không dùng JDBC sync trên event loop;
- Redis reactive nếu đó là store/lookup cache đáng tin cậy;
- WebClient tới một Authentication/Key Registry service với TLS, timeout và policy về service availability.

**Không làm thế này trong WebFlux:**

```java
// ANTI-PATTERN: blocking I/O ngay trong reactive pipeline.
return Mono.just(jdbcApiKeyRepository.findByKeyId(keyId));
```

`Mono.just(...)` thực thi đối số **ngay**, nên JDBC call vẫn block tại thời điểm method được gọi. Nếu chưa có reactive driver, wrapper có thể dùng:

```java
// FRAGMENT cho integration blocking bắt buộc; cần giới hạn tài nguyên.
return Mono.fromCallable(
        () -> jdbcApiKeyRepository.findByKeyId(keyId))
        .subscribeOn(Schedulers.boundedElastic());
```

Đoạn này là **fragment**, cần imports và mapping null/Optional phù hợp. Đây không thay thế reactive I/O; phải đặt timeout, concurrency limits, pool metrics và kế hoạch migrate khi throughput cao. Không gọi `.block()` trong `ReactiveAuthenticationManager`.

### 14.3. Rotation và revoke

Một key phải có:
- `key_id` duy nhất.
- `enabled`/revoked timestamp.
- Expiration và phương án renewal.
- Audit history, last use metadata.
- Owner, tenant, scopes, IP/network policy (nếu có).
- Rotation workflow.

Một chu kỳ rotation:
1. Tạo **key mới** (ID/secret mới), scope không rộng hơn yêu cầu.
2. Giao key mới cho client qua secure channel.
3. Cho phép **cửa sổ chuyển đổi có giới hạn** nếu cần.
4. Theo dõi key cũ còn được dùng không.
5. Revoke key cũ và xác nhận mọi Resource Server từ chối nó.
6. Xóa secret cũ khỏi CI secrets, config và support docs; audit incidents.

**Một key ID không nên đồng thời map tới hai secrets trong demo repository**, vì record chỉ có một verifier. Production có thể hỗ trợ nhiều key IDs active trong một overlap window.

### 14.4. Cache và yêu cầu thu hồi tức thời

Nếu Resource Servers cache `ApiKeyRecord` trong 10 phút, admin revoke key lúc 10:01 nhưng node vẫn dùng record `enabled=true` cũ tới 10:11. Một key registry “reactive” **không tự mang guarantee revocation tức thời**.

Định nghĩa rõ:
- Thời điểm revoke commit.
- Max propagation delay giữa regions/nodes.
- TTL cache result và event invalidation.
- Request đã authenticate trước revoke có được phép kết thúc không.
- Khi Redis/DB unavailable thì fail closed hay degrade có giới hạn.
- Audit/metric time từ revoke commit đến request mới bị từ chối.

Với giao dịch rủi ro cao, có thể phải đọc current policy gần transaction commit. Không chỉ rely vào authentication tại entrypoint nếu quyền có thể đổi giữa request dài.

### 14.5. Timing và enumeration

Dù digest so constant-time, lookup ID tồn tại có thể chậm/nhanh khác ID không tồn tại. Các biện pháp bổ sung:
- Dùng generic 401 và response body thống nhất.
- Thực hiện hash compare với dummy digest khi record không tồn tại nếu cần giảm timing difference.
- Giới hạn tốc độ theo IP/client/key prefix và phát hiện patterns.
- Tránh cho phép query key ID trong unauthenticated endpoint trả metadata/role.
- Không log raw key hay toàn bộ HTTP headers.
- Tránh thêm random sleep vô hạn dễ gây DoS và không giải quyết bản chất.

256-bit random secret khiến online guessing thực tế rất khó khi triển khai đúng; vẫn cần rate limit để chống abuse, DoS và phát hiện lộ key.

### 14.6. Replay và channel binding

API key là bearer secret nên nếu bị sao chép vẫn có thể được replay. HTTPS chống nghe lén trên đường truyền nhưng không cứu credential đã lộ trong logs/máy client. Với tích hợp nhạy cảm:
- Xem xét mTLS hoặc private network restrictions.
- Chữ ký request HMAC có timestamp/nonce và canonicalization chuẩn nếu threat model yêu cầu proof-of-possession; phải kiểm soát replay window/clock drift.
- Có thể dùng OAuth2 client credentials/mTLS-bound tokens thay key tĩnh.
- Không gửi key cho browser frontend public.
- Hỗ trợ cấp nhiều key theo dịch vụ để rotation không gây downtime.

**Đừng tự thiết kế “ký request” tùy tiện** mà không có thông số canonicalization, MAC algorithm, chống replay và key rotation rõ ràng.

## 15. Khi kết hợp API key với CORS/browser hoặc OAuth2

### 15.1. Browser gọi custom header có preflight

JavaScript từ origin khác gọi:

```javascript
// CHỈ minh họa HTTP; KHÔNG nhúng shared secret vào frontend public.
fetch("https://api.example.test/api/data", {
  headers: { "X-API-Key": "DO_NOT_PUT_SHARED_SECRET_IN_BROWSER" }
});
```

`X-API-Key` không phải CORS-safelisted header, nên browser có thể gửi **OPTIONS preflight** trước request thật. Preflight không mang raw API key; chỉ có `Access-Control-Request-Headers: x-api-key`.

Với Spring Security WebFlux, cấu hình CORS **trước authentication**, whitelist origins/methods/headers đúng, không bắt preflight gửi key. Demo ở phần 9 hướng tới `curl`/machine clients và **không tự cấu hình CORS cho browser**. Nếu muốn browser client, cần một design riêng về user authentication, secret exposure, CORS và CSRF.

### 15.2. Vì sao demo tắt CSRF có điều kiện?

CSRF thường liên quan khi browser **tự động gửi credentials** (cookie/session/HTTP Basic trong ngữ cảnh phù hợp). API key được một machine client **chủ động đặt vào header**, không mặc nhiên được browser gửi như cookie. Do đó app chuyên biệt API key stateless có thể tắt CSRF nếu **không có** cơ chế browser credentials đồng thời.

Nếu cùng app có login session/cookie:
- Giữ CSRF bảo vệ cho state-changing routes có credentials tự động.
- Tách security chains theo paths/API schemes rõ ràng.
- Không dùng `csrf.disable()` trên toàn app vì muốn một POST dùng API key chạy.

### 15.3. Kết hợp JWT bearer và API key

Nếu app hỗ trợ cả Bearer JWT và `X-API-Key`:
- Không để hai filters cùng cố xác thực một request trái ngược cách nhau.
- Dùng `securityMatcher`/multiple `SecurityWebFilterChain` hoặc `ReactiveAuthenticationManagerResolver` rõ.
- Quyết định credential precedence khi request có **cả hai headers**. Từ chối mơ hồ thường an toàn hơn tự chọn ngẫu nhiên.
- Phân biệt authorities và principal types; kiểm tra tenant scopes.
- Chống bypass khi converter trả empty rồi một cơ chế khác ngẫu nhiên cấp quyền.
- Viết tests cho cả hai headers, thiếu/sai một header, duplicate và mixed-auth requests.

### 15.4. Gateway có thể tự xác thực API key

Nếu gateway đã kiểm tra API key rồi chuyển identity vào internal headers:
- Chỉ tin gateway qua mTLS/network policy và xóa mọi client-supplied identity headers.
- Nếu backend không kiểm chứng nguồn header, attacker có thể giả `X-Authenticated-Client`.
- Cân nhắc defense-in-depth tại Resource Server cho endpoints nhạy cảm.
- Giao trách nhiệm rate limiting, revocation và audit giữa gateway/ứng dụng rõ ràng.

## 16. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| Key đúng nhưng luôn 401 | Converter không match/nhầm header hoặc registry digest sai | Test header→converter→manager, matchers |
| Key sai lại được 200 | Trả auth true trước validate, `permitAll` sai | Chỉ manager cấp verified principal, deny default |
| Key sai trả 403 thay vì 401 | Entry point hoặc anonymous/auth flow sai | Configure failure handler & exceptionHandling |
| Key đúng nhưng 403 ở data | Scope map sai (`SCOPE_` prefix) | Kiểm tra scopes từ record và hasAuthority |
| Key không được đọc trong request | Gateway xóa `X-API-Key` | Kiểm tra trusted proxy, không log value |
| Header duplicate được chấp nhận | Converter lấy `getFirst` | Reject duplicates/comma-joined values |
| App startup lỗi | Thiếu `DEMO_API_KEY` hoặc format không hợp lệ | Generate 32 bytes key và inject env |
| Revoke key chỉ hiệu lực node A | Store in-memory hoặc local cache | Shared store/consistency/TTL |
| Key lộ trong logs | HTTP header logging/APM | Redact, rotate exposed key |
| Request loop bị chậm | Blocking JDBC trong manager | Reactive I/O, no `block()` |
| Invalid key bị xem như missing | Manager trả `Mono.empty()` khi key sai | `Mono.error(BadCredentialsException)` |
| Key authenticated vẫn có raw credentials | Verified token giữ raw secret | Clear/null credentials after verification |
| Browser OPTIONS bị 401 | CORS không xử lý trước authentication | CorsConfigurationSource/CorsWebFilter đúng thứ tự |
| CSRF 403 trong app browser | Browser session + POST thiếu token | Giữ CSRF, thiết kế đúng client |
| Auth còn từ request trước | WebSessionSecurityContextRepository đang persist | NoOp repo cho API key-only chain |
| Không xác thực dù đã `authenticationManager` | Chưa có converter/filter cho `X-API-Key` | AuthenticationWebFilter + ServerAuthenticationConverter |
| `@PreAuthorize` không thấy auth | Sai Reactor Context, bypass chain | Để filter lập context, reactive method security đúng |
| Unit test PASS nhưng gateway fail | Chưa test ingress TLS/header propagation | Test E2E qua proxy, include rate limits |
| Rò key ID/role qua 401 | Lỗi chi tiết trả client | Generic error, audit nội bộ không secret |
| Tích hợp người dùng browser nhúng API key | Secret nằm trong JS bundle | OAuth2/OIDC/BFF thay shared key |
| Dùng BCrypt cho random 256-bit key và CPU tăng mạnh | Chọn password KDF không theo threat model | Dùng SHA-256/HMAC cho secret high-entropy, rate limit |
| Không có expiry | Key tồn tại mãi | Provisioning, expiration, rotation, revocation |

## 17. Checklist review bảo mật

1. [ ] API key được sinh từ CSPRNG với **ít nhất 256-bit random secret**, không phải từ user password/timestamp.
2. [ ] Key ID là định danh public, secret thật không được log/serialize.
3. [ ] DB lưu digest/HMAC verifier, không lưu raw secret.
4. [ ] Hash comparison dùng `MessageDigest.isEqual` với digest cùng độ dài.
5. [ ] Converter chỉ đọc **header được chọn** và reject duplicate/oversize/malformed.
6. [ ] `ReactiveAuthenticationManager` trả đúng `Mono.just`/`Mono.empty`/`Mono.error` theo contract.
7. [ ] Authentication token trước verify có `authenticated=false`, sau verify không giữ credentials.
8. [ ] Principal, scopes và tenant metadata đến từ server-side registry, không từ request.
9. [ ] Scope mapping `SCOPE_*` và default deny được test.
10. [ ] 401/403 phân biệt đúng, error body không chứa key ID/secret/stack trace.
11. [ ] `AuthenticationWebFilter` đặt trước authorization trong `SecurityWebFilterChain`.
12. [ ] `NoOpServerSecurityContextRepository` được dùng đúng khi API key-only/stateless.
13. [ ] CSRF chỉ disable khi threat model không có tự động gửi browser credentials.
14. [ ] CORS preflight được xử lý trước auth nếu hỗ trợ cross-origin browser.
15. [ ] Production key registry có nhiều key IDs, owner, tenant, scopes, expiry, enabled/revoke.
16. [ ] Rotation có overlap window và revoke old key đúng SLA.
17. [ ] Không dùng in-memory store demo cho multi-instance.
18. [ ] Reactive repository không blocking event loop; timeout/connection pool hợp lý.
19. [ ] HTTPS/TLS trên mọi hop mang key; proxy/WAF/APM redact `X-API-Key`.
20. [ ] Rate limiting/quotas/monitoring theo client/key ID và anomaly detection.
21. [ ] Không đưa API key vào query, URL history, browser JS public, Git hoặc CI logs.
22. [ ] Integration tests đi qua manager **thật**, không chỉ dùng `mockUser()`.
23. [ ] Permission per resource/tenant và high-risk operations được kiểm tra gần business action.
24. [ ] Store outage policy không âm thầm fail-open; có monitoring/incident response.

## 18. Câu hỏi tự kiểm tra

**1. Vai trò của `ServerAuthenticationConverter`?**  
Trích xuất API key từ HTTP request và tạo một `Authentication` chưa xác thực; không kiểm tra database hoặc cấp quyền.

**2. Vai trò của `ReactiveAuthenticationManager`?**  
Xác minh credential thông qua reactive repository/policy, rồi trả authenticated principal/authorities hoặc authentication error.

**3. Khi nào trả `Mono.empty()`?**  
Khi manager **không hỗ trợ loại Authentication**; converter cũng có thể empty khi không có credential. Không dùng empty để báo key sai.

**4. Key sai phải trả gì từ manager?**  
`Mono.error(new BadCredentialsException(...))` hoặc một `AuthenticationException` phù hợp.

**5. Key đúng trả gì?**  
`Mono.just(authentication)` với `isAuthenticated=true`, principal/authorities từ trusted registry và credentials không còn raw key.

**6. API key cần bao nhiêu entropy?**  
Demo chọn **256-bit random secret** từ `SecureRandom`; điều quan trọng là CSPRNG và secret không dự đoán được.

**7. Vì sao tách `keyId` và `secret`?**  
Cho phép lookup theo ID, revoke/rotate/audit từng key mà không quét mọi hashes.

**8. Vì sao dùng SHA-256 digest thay vì BCrypt trong demo key?**  
Key random 256 bit có entropy cao, khác với password do con người chọn; SHA-256/HMAC verifier kết hợp rate limit và policy phù hợp. Không dùng cùng cách đó để lưu mật khẩu yếu.

**9. Vì sao dùng `MessageDigest.isEqual`?**  
So sánh verifier digest với candidate digest tránh String/byte loop thông thường có thể leak timing theo dữ liệu. Nó không giải quyết mọi timing leak của lookup.

**10. Manager có được lấy role từ header không?**  
Không. Roles/scopes phải đến từ key metadata do server kiểm soát.

**11. Vì sao `X-API-Key` không nên nằm trong URL?**  
Nó là bearer secret, URL dễ bị ghi vào history, Referer, access logs và analytics.

**12. `NoOpServerSecurityContextRepository` nghĩa là gì?**  
Không persist authentication giữa requests; mỗi request cần gửi credential, nhưng key registry vẫn có state phía server.

**13. Vì sao key hợp lệ có thể nhận 403?**  
Authentication thành công nhưng thiếu authority/scope cho route hoặc resource.

**14. Vì sao thiếu/sai key thường nhận 401?**  
Không có Authentication hợp lệ cho endpoint yêu cầu authenticated.

**15. Spring Security có tự nhận `X-API-Key` chỉ nhờ `authenticationManager` không?**  
Không. Cần `ServerAuthenticationConverter`/`AuthenticationWebFilter` hoặc một mechanism tương đương.

**16. Có thể dùng raw API key trong browser SPA bundle không?**  
Không nên. Người dùng có thể đọc bundle/DevTools; dùng OAuth2/OIDC/PKCE hoặc BFF.

**17. Reactive manager có được gọi JDBC đồng bộ trực tiếp không?**  
Không nên; nó có thể block Netty event loop. Dùng R2DBC/reactive Redis/WebClient hoặc cô lập blocking calls đúng cách.

**18. In-memory registry demo có cho phép revoke trên mọi instance không?**  
Không. Mỗi JVM có map riêng và state mất khi restart.

**19. Một key bị disable nhưng cache còn record enabled thì sao?**  
Request có thể vẫn được phép tới khi cache refresh; thiết kế revocation SLA, cache invalidation và consistency.

**20. HTTP preflight OPTIONS có mang API key thật không?**  
Thông thường không; browser hỏi về header tên `x-api-key` trước request thật. CORS cần xử lý trước authentication.

**21. `@PreAuthorize` có thể dùng với API key principal không?**  
Có khi reactive method security cấu hình đúng và Authentication được đặt trong Reactor Context; test authorities và business rules.

**22. Vì sao một request được xác thực không nên tự cấp quyền cho mọi request sau đó?**  
API key header-only auth được thiết kế stateless: request nào cũng phải trình credential và được đánh giá theo status/permissions hiện tại.

### Bài tập thực hành

1. Chạy 8 manager tests; giải thích sự khác nhau giữa unsupported token (empty Mono) và wrong key (error Mono).
2. Chạy 10 WebTestClient tests; xác nhận thiếu key = 401, valid read key = 200, thiếu admin scope = 403.
3. Viết thêm test HTTP cho header rỗng, quá dài, chứa dấu comma và Base64URL không canonical.
4. Thử bỏ `NoOpServerSecurityContextRepository` ở một nhánh thử nghiệm; kiểm tra session persistence và giải thích vì sao không nên dựa vào request trước.
5. Thêm một key ID mới có scope `admin:write` vào repository test và xác minh POST /api/admin trả 200, nhưng GET /api/data cần scope riêng.
6. Thêm tenantId vào `ApiKeyRecord` và check tenant ownership trong service trước khi truy cập dữ liệu.
7. Thiết kế bảng PostgreSQL/R2DBC cho nhiều API keys, unique ID, expiry, revokedAt và scopes.
8. Thử disable một key trong store (ở bài lab), kiểm tra request kế tiếp trả 401; mô phỏng cache stale để đo latency revoke.
9. Thử repository trả `Mono.error` và xác minh manager không tạo authenticated token.
10. Thêm quota/rate limit theo key ID + client ID, không lưu secret trong metrics labels.
11. Đánh giá HMAC pepper vs SHA-256 verifier cho random API key, mô tả cách rotate pepper an toàn.
12. Cấu hình HTTPS/mTLS cho API tích hợp và kiểm tra gateway không log `X-API-Key`.
13. Thêm CORS cho một frontend test origin cụ thể, xác nhận OPTIONS preflight được xử lý trước key auth, đồng thời **không đưa shared key vào SPA thật**.
14. Nếu app hỗ trợ Bearer JWT đồng thời, thiết kế quy tắc từ chối request có cả Bearer và X-API-Key, kiểm thử credential precedence.
15. Mô tả một chiến lược rotation có overlap window, monitoring key cũ và revoke đúng SLA.
16. So sánh cách dùng custom API key với OAuth2 client credentials cho một dịch vụ đối tác: threat model, scope, expiry, revocation, scalability.
17. Thêm unit test giả lập unknown key ID nhưng dummy digest compare để giảm timing difference, kiểm soát DoS.
18. Viết checklist xử lý incident khi một API key bị lộ: revoke, rotate, audit activity, kiểm tra logs, thông báo owner và invalidate dependent secrets.

## 19. Tài liệu tham khảo chính thức

- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): cách hoạt động authentication trong WebFlux.
- [Spring Security 6.3 API — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html): ý nghĩa `Mono.just`, `Mono.empty`, `Mono.error`.
- [Spring Security 6.3 API — AuthenticationWebFilter](https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): matcher, converter, manager, context và success/failure handlers.
- [Spring Security 6.3 API — ServerAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): converter từ exchange tới `Mono<Authentication>`.
- [Spring Security 6.3 API — ServerHttpSecurity](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/web/server/ServerHttpSecurity.html): `addFilterAt`, `securityContextRepository`, `authorizeExchange`, `exceptionHandling`.
- [Spring Security 6.3 API — HttpStatusServerEntryPoint](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/server/authentication/HttpStatusServerEntryPoint.html): 401 generic cho API.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): điều kiện bật/tắt CSRF đúng với client/session.
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight trước authentication.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` và Reactor Context.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): TLS, authentication/authorization, HTTP statuses, security controls.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret storage, rotation, least privilege, audit.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication failure messages, throttling và logging.
- [Oracle Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): CSPRNG cho key generation.
- [Oracle Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `MessageDigest.isEqual`.

**Ghi nhớ:** Triển khai API key đúng trong **Spring Security reactive** theo hướng **converter (HTTP credential) → `ReactiveAuthenticationManager` (verify qua reactive store) → authenticated `Authentication` → authorization theo authorities/resource**. Khóa phải là secret đủ ngẫu nhiên, lưu digest, so sánh constant-time, giới hạn quyền, có expiry/rotation/revocation và không lộ qua logs. **`Mono.empty()` chỉ nghĩa là manager không xác định được/không xử lý loại Authentication; API key sai phải là `Mono.error(AuthenticationException)`.** Với API key-only stateless, mỗi request cần credential riêng; thành công 200, thiếu/sai key 401, thiếu quyền 403.