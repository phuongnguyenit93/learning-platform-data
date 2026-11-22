# Kiểm thử ReactiveAuthenticationManager và ServerAuthenticationConverter

## 1. Mục tiêu và bối cảnh

Bài học thuộc phần **Kiểm thử chuyên sâu** của module **Spring Security - reactive**. Trong Spring WebFlux, một cơ chế xác thực tùy biến thường gồm hai thành phần có trách nhiệm khác nhau:

- **`ServerAuthenticationConverter`**: đọc `ServerWebExchange`, trích xuất credential từ HTTP request và tạo một đối tượng `Authentication` **chưa xác thực**.
- **`ReactiveAuthenticationManager`**: nhận đối tượng đó, gọi dịch vụ/repository reactive để kiểm tra credential, rồi phát ra `Authentication` đã xác thực hoặc lỗi phù hợp.

`AuthenticationWebFilter` nối converter và manager với **`SecurityWebFilterChain`**. Kiểm thử tốt cần tách kiểm thử từng hợp đồng khỏi kiểm thử HTTP tích hợp, thay vì chỉ gửi vài request với `mockUser()` rồi kết luận cơ chế xác thực hoạt động.

Sau bài này, bạn có thể:

1. Giải thích chính xác ba nhánh `ReactiveAuthenticationManager.authenticate(...)`: **`Mono.just(Authentication)` thành công**, **`Mono.empty()` không xác định/không hỗ trợ loại token**, **`Mono.error(AuthenticationException)` khi xác thực thất bại**.
2. Giải thích `ServerAuthenticationConverter.convert(...)`: header không có → `Mono.empty()`; header hợp lệ về cấu trúc → tạo **unauthenticated Authentication**; header trùng, quá dài hoặc sai rõ ràng → authentication error.
3. Dùng **`StepVerifier`** kiểm tra tín hiệu `onNext/onComplete/onError`, phân biệt Mono empty với Mono error và kiểm tra **deferred execution**.
4. Dùng **`MockServerHttpRequest`** và **`MockServerWebExchange`** test converter mà không chạy HTTP server hay Spring Boot.
5. Dùng fake `ReactiveKeyRepository`/`Clock.fixed(...)` để kiểm thử manager **không dựa vào ngủ chờ** hoặc database/Redis thật.
6. Viết **`WebTestClient.bindToApplicationContext(context).apply(springSecurity())`** để kiểm tra converter → manager → filter → authorization, không mock authentication.
7. Phân biệt **401** do thiếu/sai credential, **403** do có authentication hợp lệ nhưng không đủ quyền, và **200** khi thành công; xác nhận không có trạng thái xác thực được kế thừa từ request trước.
8. Dùng một API key demo gồm key ID + random secret, lưu **SHA-256 digest** của secret, sử dụng `MessageDigest.isEqual`; hiểu các giới hạn của demo một JVM.
9. Tổ chức kiểm thử đúng mức: unit, HTTP integration, infrastructure failure, security regression, performance và E2E; tránh false-positive từ `mockUser()` hoặc `mockJwt()`.
10. Biết lỗi phổ biến, bảo mật logs/test fixtures, virtual time, reactive I/O, timeout, cancellation và consistency khi chạy nhiều instance.

**Phạm vi:** Đây là bài **kiểm thử chuyên sâu** hai hợp đồng Spring Security reactive. API key chỉ là **bối cảnh minh họa** đủ đơn giản để viết test độc lập; đây không phải hướng dẫn xây một hệ thống API key provisioning/rotation production hoàn chỉnh. Toàn bộ chương trình và test dùng **Java 17+, Spring Boot 3.3.5, Spring Security 6.3.x, JUnit 5, Reactor Test**. Các kết quả kiểm thử ở cuối bài là **dự kiến theo mã**, không khẳng định lệnh Gradle đã được chạy trong môi trường hiện tại.

## 2. Đặt ba hợp đồng vào đúng vị trí

Một request API:

```http
GET /api/items HTTP/1.1
Host: localhost:8080
X-API-Key: ak_demo_<random-base64url-secret>
```

Chuỗi `<random-base64url-secret>` chỉ là ký hiệu. Không dùng giá trị này làm khóa thực.

Luồng đúng:

```text
HTTP Request
   |
   v
SecurityWebFilterChain
   |
   v
AuthenticationWebFilter
   |
   +--> requiresAuthenticationMatcher("/api/**")?
   |      no  --> tiếp tục filter chain
   |      yes
   |       |
   |       v
   |    ServerAuthenticationConverter
   |       | 
   |       +--> header vắng mặt .......... Mono.empty()
   |       +--> header không hợp lệ ...... Mono.error(...)
   |       +--> header hiện diện .......... Authentication(false)
   |                                          |
   |                                          v
   |                              ReactiveAuthenticationManager
   |                                          |
   |                          +---------------+----------------+
   |                          |               |                |
   |                      hợp lệ           sai/expired      unsupported
   |                     Mono.just(...)    Mono.error(...)   Mono.empty()
   |                          |               |                |
   |                         success        failure         no decision
   |                          |               |                |
   |                          v               v                v
   |                    SecurityContext     HTTP 401       tiếp tục chain
   |
   v
AuthorizationWebFilter
   +--> anonymous/không auth --> 401
   +--> authenticated, thiếu quyền --> 403
   +--> authenticated, đủ quyền --> controller, 200
```

**Lưu ý:** `Mono.empty()` có thể xuất hiện ở **hai lớp**, nhưng ý nghĩa không giống nhau hoàn toàn:

| Nơi trả empty | Ý nghĩa cụ thể | Điều không được suy ra |
| --- | --- | --- |
| Converter không thấy header cần thiết | Không có authentication attempt cho scheme này | Request được phép truy cập |
| Manager nhận loại `Authentication` không hỗ trợ | Không thể đưa ra quyết định cho loại token này | Credential đã xác thực |
| Repository lookup thiếu key record | Nguồn dữ liệu không có bản ghi | Manager có quyền trả empty đến filter như “không sao” |
| `Mono.empty()` sau manager đang xử lý key sai | **Bug thiết kế** nếu muốn trả lỗi cho credential sai | Có thể bỏ qua 401 của scheme hoặc nhầm flow |

Khi một manager đã nhận trách nhiệm xử lý API key, **key sai/disabled/expired phải là authentication failure**. Nó không được tạo `Authentication` với `isAuthenticated=true` trước khi đã kiểm tra credential.

### Interface thật

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}

@FunctionalInterface
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
```

Đây là **trích hình dạng API để học hợp đồng**, không phải hai interface cần tự tạo trong project. Các interface có sẵn trong `spring-security-core` và `spring-security-web`.

Kết quả test phải khẳng định đúng **tín hiệu reactive**:

```java
// Thành công: đúng một Authentication rồi onComplete.
StepVerifier.create(manager.authenticate(candidate))
        .assertNext(auth -> assertTrue(auth.isAuthenticated()))
        .verifyComplete();

// Không hỗ trợ type: không onNext, không error.
StepVerifier.create(manager.authenticate(unsupported))
        .verifyComplete();

// Credential sai: onError, không phải onComplete.
StepVerifier.create(manager.authenticate(wrongKey))
        .expectError(BadCredentialsException.class)
        .verify();
```

Các đoạn này là **fragments**, dùng biến từ bài test cụ thể. Bộ test runnable đầy đủ xuất hiện bên dưới.

## 3. Vì sao phải có ba lớp kiểm thử?

| Lớp | Gọi trực tiếp | Kiểm tra được | Không tự chứng minh |
| --- | --- | --- | --- |
| Converter unit test | `convert(exchange)` | Header absent/duplicate/malformed, unauthenticated token | Hash lookup, database, HTTP authorization |
| Manager unit test | `authenticate(authentication)` | Repository, hash compare, status, authorities, Mono contract, error propagation | HTTP header parser, filter ordering |
| HTTP integration | `WebTestClient` gửi `X-API-Key` thật qua filter chain | Converter → manager → SecurityContext → 200/401/403 | TLS/proxy/real multi-instance store |
| Persistence integration | Test R2DBC/Redis thật hoặc Testcontainers | Lookup/expiry/revoke consistency, connection failure | Framework HTTP policy nếu không đi qua chain |
| Deployment E2E | Real HTTP/TLS/proxy/client | Gateway header forwarding, timeouts, certificate, operational behavior | Mọi business authorization nếu test chưa bao phủ |

**Quan trọng:** Dùng `mockUser()`/`mockAuthentication()` để kiểm tra **authorization** là hợp lệ, nhưng chúng **bypass manager và converter**. Không thể dùng một test mock principal thành công để khẳng định mật khẩu, token signature hoặc API key verifier đã được kiểm chứng. Bộ HTTP integration ở đây **cố ý không dùng `mockUser()`**.

### Tại sao `StepVerifier` tốt hơn `block()` trong test?

- Nhìn thấy rõ `onNext`, `onComplete`, `onError`.
- Phân biệt **Mono empty** với **Mono.error**.
- Có thể dùng `assertNext(...)` để kiểm tra principal, scopes và việc credentials đã bị xóa.
- Có thể kiểm tra thời điểm subscription; tránh việc gọi repository quá sớm.
- Có `withVirtualTime(...)` cho nguồn dùng Reactor timer/scheduler, không cần `Thread.sleep`.
- Trong test thật có I/O, đặt **timeout** để tránh CI treo vô hạn.

Với các APIs reactive, **không viết**:

```java
// ANTI-PATTERN: block() có thể che lỗi reactive và làm test treo.
Authentication result = manager.authenticate(candidate).block();
assertTrue(result.isAuthenticated());
```

Đoạn này không kiểm tra rõ `Mono.empty` hay `onError` và bỏ qua giới hạn timing của reactive pipeline. `StepVerifier` là công cụ phù hợp hơn.

## 4. Thiết kế fixture API key để test

Mẫu dùng key format:

```text
ak_<keyId>_<base64url(32 random bytes)>
```

Ví dụ:
- `keyId=demo`: public identifier dùng lookup.
- Phần secret: **32 byte** tạo từ `SecureRandom`, Base64URL không padding, dài **43 ký tự**.
- Repository chỉ lưu **SHA-256 digest của secret** và metadata như client ID, scopes, enabled, expiresAt.
- `ServerAuthenticationConverter` chuyển raw header thành `ApiKeyAuthenticationToken.request(raw)` chưa authenticated.
- `ReactiveAuthenticationManager` parse key, đọc repository, so digest với `MessageDigest.isEqual`, kiểm tra expiry/status, trả token đã authenticated với credentials null.

Trong **unit tests**, có thể dùng `new byte[32]` để tạo **fixture tất định**. Đây là chuỗi toàn số 0 có **0 entropy**, tuyệt đối **không được dùng làm API key thực**. Ứng dụng demo chạy ngoài tests sẽ yêu cầu một key được sinh ngẫu nhiên từ `SecureRandom` và đưa qua biến môi trường.

### Các tình huống phải kiểm thử

**Converter:**
- Không có `X-API-Key` → `Mono.empty()`.
- Header hợp lệ → exactly one unauthenticated token.
- Header rỗng, dài, chứa comma hoặc duplicate → `BadCredentialsException`.
- Header tên chữ thường `x-api-key` vẫn được đọc (HTTP header name case-insensitive).
- Converter **không tự cấp role/authorities**.

**Manager:**
- Key đúng → authenticated principal, authorities server-side, credentials cleared.
- Cùng key ID nhưng secret sai → error.
- Key ID chưa tồn tại → error, không trả empty.
- Key malformed → error.
- Record disabled hoặc expired → error.
- Manager nhận `UsernamePasswordAuthenticationToken` → `Mono.empty()` vì không hỗ trợ.
- Repository outage → **error được propagate**, không fail-open.
- Lookup chưa chạy trước subscription.
- Sau expiry boundary với `Clock.fixed` → deny chính xác, không sleep.

**HTTP:**
- Public route anonymous → 200.
- Private route không key → 401.
- Invalid/duplicate/unknown key → 401.
- Correct key + correct scope → 200.
- Correct key + missing scope → 403.
- Request mới không có key → 401, không thừa kế session.
- Route chưa khai báo → denied by default.

## 5. Dự án Java 17 / Spring Boot 3.3.5

Tạo thư mục:

```text
reactive-authn-testing/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/authntest/
    │   │   ├── AuthenticationTestingApplication.java
    │   │   ├── ApiKeyMaterial.java
    │   │   ├── ApiKeyAuthenticationToken.java
    │   │   ├── ApiKeyRecord.java
    │   │   ├── ReactiveKeyRepository.java
    │   │   ├── DemoKeyRepository.java
    │   │   ├── ApiKeyReactiveAuthenticationManager.java
    │   │   ├── ApiKeyHeaderConverter.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DemoController.java
    │   │   └── LocalKeyGenerator.java
    │   └── resources/application.yml
    └── test/java/dev/example/authntest/
        ├── ApiKeyHeaderConverterTests.java
        ├── ApiKeyReactiveAuthenticationManagerTests.java
        └── ApiKeyHttpTests.java
```

Tên package, tên class và đường dẫn các source files khớp nhau. Mỗi source code Java bên dưới là **nội dung đầy đủ của một tệp**, không chỉ pseudocode.

### 5.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-authn-testing'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao từng dependency cần thiết?**
- `spring-boot-starter-webflux`: Reactor/Netty, reactive controllers, WebTestClient-capable WebFlux stack.
- `spring-boot-starter-security`: `ReactiveAuthenticationManager`, `AuthenticationWebFilter`, security context và authorization.
- `spring-boot-starter-test`: JUnit Jupiter, Spring Test, mock `ServerWebExchange`, WebTestClient.
- `spring-security-test`: `springSecurity()` cho WebTestClient và mutators khi cần.
- `reactor-test`: `StepVerifier` và virtual-time tools.

**Không thêm `spring-boot-starter-web` vào project WebFlux thuần**: khi có cả MVC và WebFlux starters, Spring Boot thường chọn Servlet/MVC stack, không còn tương thích với dự án này.

### 5.2. Runtime property

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

demo:
  api-key: "${DEMO_API_KEY:}"
```

Ứng dụng yêu cầu biến môi trường `DEMO_API_KEY`. Nếu không có key, `DemoKeyRepository` sẽ không khởi tạo được (fail fast). Điều này **cố ý**: không tự dùng một secret mặc định nguy hiểm.

Trong HTTP tests, `@DynamicPropertySource` ghi đè `demo.api-key` với fixture test và **không cần biến môi trường thật**. Unit tests không tải Spring Boot context.

### 5.3. Main class

`src/main/java/dev/example/authntest/AuthenticationTestingApplication.java`:

```java
package dev.example.authntest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationTestingApplication.class, args);
    }
}
```

### 5.4. Key parser và digest helper

`src/main/java/dev/example/authntest/ApiKeyMaterial.java`:

```java
package dev.example.authntest;

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

    public record Parts(String keyId, byte[] secret) {

        public Parts {
            secret = secret.clone();
        }

        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public static Parts parse(String raw) {
        if (raw == null || raw.length() > 128) {
            throw new BadCredentialsException("Invalid API key");
        }

        Matcher matcher = FORMAT.matcher(raw);
        if (!matcher.matches()) {
            throw new BadCredentialsException("Invalid API key");
        }

        byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder()
                    .decode(matcher.group(2));
        } catch (IllegalArgumentException ex) {
            throw new BadCredentialsException("Invalid API key");
        }

        if (decoded.length != 32) {
            throw new BadCredentialsException("Invalid API key");
        }

        // Bắt buộc Base64URL canonical, không padding.
        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(decoded);

        if (!encoded.equals(matcher.group(2))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return new Parts(matcher.group(1), decoded);
    }

    public static byte[] sha256(byte[] secret) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(secret);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is not available", ex);
        }
    }

    public static String sha256Hex(byte[] secret) {
        return HexFormat.of().formatHex(sha256(secret));
    }
}
```

**Lý do lựa chọn:** API key có **256 bit ngẫu nhiên**, nên SHA-256 digest có thể dùng làm verifier; **đây không phải công thức lưu mật khẩu con người**. Password entropy thấp phải dùng password hashing phù hợp như Argon2/bcrypt/scrypt. Raw key chỉ nên được cấp **một lần**, tránh lưu trong source/config repository, logs và test report.

Ở production, có thể dùng HMAC-SHA-256 với server-side pepper để giảm tác hại nếu DB verifier bị lộ, nhưng cần quản lý pepper bằng KMS/secret manager và kế hoạch rotation. Digest không phải encryption.

### 5.5. Custom Authentication token

`src/main/java/dev/example/authntest/ApiKeyAuthenticationToken.java`:

```java
package dev.example.authntest;

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
                "unverified", rawKey, List.of(), false);
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
        credentials = null;
        super.eraseCredentials();
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                    "Use verified(...) only after validation");
        }
        super.setAuthenticated(false);
    }
}
```

**Kiểm thử phải chú ý hai trạng thái:**

| Điều kiện | `request(rawKey)` | `verified(clientId, authorities)` |
| --- | --- | --- |
| `isAuthenticated()` | false | true |
| Principal | “unverified” (không đáng tin) | ID client từ repository |
| Credentials | Raw key tạm thời | null |
| Authorities | Rỗng | Danh sách do server cấp |
| Ai được tạo? | Converter | Manager sau khi verify |

Constructor private cùng factory `verified(...)` và `setAuthenticated(true)` bị chặn giúp tránh code ngoài manager nâng một request token thành authenticated mà không kiểm chứng.

**Không đưa raw credentials vào principal hoặc authorities**. `Authentication` có thể được truyền qua reactive context; hãy coi nó là dữ liệu nhạy cảm và không log toàn bộ object.

### 5.6. Record và repository reactive

`src/main/java/dev/example/authntest/ApiKeyRecord.java`:

```java
package dev.example.authntest;

import java.time.Instant;
import java.util.Set;

public record ApiKeyRecord(
        String keyId,
        String clientId,
        String digestHex,
        Set<String> scopes,
        boolean enabled,
        Instant expiresAt) {

    public ApiKeyRecord {
        scopes = Set.copyOf(scopes);
    }
}
```

`src/main/java/dev/example/authntest/ReactiveKeyRepository.java`:

```java
package dev.example.authntest;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveKeyRepository {
    Mono<ApiKeyRecord> findById(String keyId);
}
```

`ReactiveKeyRepository` là abstraction do ví dụ định nghĩa. Với production, implement bằng **R2DBC/reactive Redis/WebClient** hoặc một client thật không block event loop. Trong tests, nó có thể là lambda trả `Mono.just`, `Mono.empty`, `Mono.error` hoặc `Mono.delay`.

### 5.7. Repository demo trong một JVM

`src/main/java/dev/example/authntest/DemoKeyRepository.java`:

```java
package dev.example.authntest;

import java.time.Instant;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

import reactor.core.publisher.Mono;

@Repository
public final class DemoKeyRepository
        implements ReactiveKeyRepository {

    private final Map<String, ApiKeyRecord> records;

    public DemoKeyRepository(
            @Value("${demo.api-key}") String rawDemoKey) {

        ApiKeyMaterial.Parts key =
                ApiKeyMaterial.parse(rawDemoKey);

        ApiKeyRecord record = new ApiKeyRecord(
                key.keyId(),
                "demo-client",
                ApiKeyMaterial.sha256Hex(key.secret()),
                Set.of("items:read"),
                true,
                Instant.MAX);

        records = Map.of(record.keyId(), record);
    }

    @Override
    public Mono<ApiKeyRecord> findById(String keyId) {
        return Mono.justOrEmpty(records.get(keyId));
    }
}
```

**Giới hạn cố ý của demo:**
- Raw key được nhận **một lần qua environment** lúc startup, sau đó chỉ lưu digest trong map.
- Chỉ có một client `demo-client` với scope `items:read`, không có scope `items:write`.
- `Instant.MAX` dùng trong local demonstration, **không phải chính sách key hết hạn hợp lệ cho production**.
- Không có API provisioning, revoke, audit, rate limit hay nhiều keys.
- Mỗi JVM giữ state riêng; deployment nhiều replicas không dùng map in-memory này.
- Repository errors (nếu thay bằng DB/Redis) phải đi theo error signal, không được chuyển thành allow.

### 5.8. ReactiveAuthenticationManager thực sự

`src/main/java/dev/example/authntest/ApiKeyReactiveAuthenticationManager.java`:

```java
package dev.example.authntest;

import java.security.MessageDigest;
import java.time.Clock;
import java.util.HexFormat;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class ApiKeyReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveKeyRepository repository;
    private final Clock clock;

    public ApiKeyReactiveAuthenticationManager(
            ReactiveKeyRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Override
    public Mono<Authentication> authenticate(
            Authentication candidate) {

        if (!(candidate instanceof ApiKeyAuthenticationToken token)
                || token.isAuthenticated()) {
            return Mono.empty(); // Không xử lý loại này.
        }

        return Mono.defer(() -> {
            ApiKeyMaterial.Parts presented =
                    ApiKeyMaterial.parse(
                            (String) token.getCredentials());

            byte[] actualDigest =
                    ApiKeyMaterial.sha256(presented.secret());

            return repository.findById(presented.keyId())
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException(
                                    "Invalid API key")))
                    .flatMap(record -> {
                        byte[] expectedDigest = HexFormat.of()
                                .parseHex(record.digestHex());

                        boolean matches = MessageDigest.isEqual(
                                expectedDigest, actualDigest);

                        boolean active = record.enabled()
                                && clock.instant().isBefore(
                                        record.expiresAt());

                        if (!record.keyId().equals(presented.keyId())
                                || !matches || !active) {
                            return Mono.<Authentication>error(
                                    new BadCredentialsException(
                                            "Invalid API key"));
                        }

                        var authorities = record.scopes().stream()
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

**Điểm test bắt buộc:**
1. `candidate instanceof ApiKeyAuthenticationToken` và `!isAuthenticated()`: manager chỉ xử lý type nó hỗ trợ.
2. `Mono.defer(...)`: parse/hash/repository lookup chạy **khi có subscription**, không thực hiện ngay khi method được gọi. Test có thể gắn `AtomicInteger` vào repository để xác minh.
3. `ApiKeyMaterial.parse(...)` có thể phát `BadCredentialsException` nếu malformed.
4. `repository.findById(...)` trả `Mono.empty()` cho missing record, nhưng manager chuyển thành `Mono.error(BadCredentialsException)` qua `switchIfEmpty`.
5. SHA-256 digest của raw secret được so với digest server-side bằng `MessageDigest.isEqual`, không so raw string trực tiếp.
6. `clock.instant().isBefore(record.expiresAt())`: đúng ngay trước expiry thì active, **bằng thời điểm expiry** đã invalid. Inject `Clock` để test boundary deterministically.
7. Scopes đến từ record tin cậy; convert thành `SCOPE_items:read`, **không đọc scope từ HTTP header**.
8. Verified authentication có principal `demo-client`, credentials `null`, `isAuthenticated=true`.
9. Store error được propagate; không `onErrorResume(e -> Mono.just(verified))`.
10. Corrupt digest không được silently accepted: lỗi parse từ trusted storage trở thành internal error, cần monitoring/fail-closed.
11. Đoạn code này dùng in-memory repository không có blocking I/O. Khi thay store, dùng reactive driver; **không gọi JDBC sync hoặc `.block()` trên Netty event loop**.

**Giới hạn bảo mật:** So sánh digest constant-time không triệt tiêu toàn bộ timing side-channel (ví dụ missing key ID có lookup khác). Production cần rate-limit, generic 401, tránh key enumeration, hết hạn, revoke, telemetry và chính sách khi store outage.

### 5.9. ServerAuthenticationConverter thực sự

`src/main/java/dev/example/authntest/ApiKeyHeaderConverter.java`:

```java
package dev.example.authntest;

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

        if (values == null || values.isEmpty()) {
            // Thiếu credential: scheme này không thử authenticate.
            return Mono.empty();
        }

        if (values.size() != 1) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        String raw = values.get(0);

        if (raw == null || raw.isBlank()
                || raw.length() > 128
                || raw.indexOf(',') >= 0
                || !raw.startsWith("ak_")) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        // Vẫn là Authentication chưa xác thực.
        return Mono.just(ApiKeyAuthenticationToken.request(raw));
    }
}
```

**Vai trò converter dừng tại HTTP boundary:**
- Không biết password/digest/repository; không cấp principal tin cậy.
- Header vắng mặt trả empty; route private cuối cùng phải bị authorization từ chối.
- Header duplicate, rỗng, quá dài, comma-merged hoặc khác scheme trả lỗi generic.
- Header bắt đầu bằng `ak_` nhưng sai secret length/base64 sẽ được **manager** từ chối bằng parse; converter không phải toàn bộ security check.
- HTTP header names case-insensitive, còn **giá trị credential là case-sensitive**.
- Không nhận secret từ query URL hoặc cookie để tránh log/history/referrer leakage.
- Không đưa header vào logs, metrics labels hoặc test failure messages.

### 5.10. WebFlux security chain: nối converter và manager

`src/main/java/dev/example/authntest/SecurityConfig.java`:

```java
package dev.example.authntest;

import java.time.Clock;

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
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ApiKeyReactiveAuthenticationManager manager) {

        var noSession =
                NoOpServerSecurityContextRepository.getInstance();
        var unauthorized =
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

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
                        .pathMatchers(HttpMethod.GET, "/api/items")
                            .hasAuthority("SCOPE_items:read")
                        .pathMatchers(HttpMethod.POST, "/api/admin")
                            .hasAuthority("SCOPE_items:write")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .anyExchange().denyAll())
                .addFilterAt(
                        apiKeyFilter,
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
```

**Giải thích cấu hình:**
- `AuthenticationWebFilter` gọi converter/manager; **`authenticationManager(...)` trên `ServerHttpSecurity` một mình không tự nhận ra `X-API-Key`**.
- `SecurityWebFiltersOrder.AUTHENTICATION` bảo đảm filter diễn ra trước authorization.
- `setRequiresAuthenticationMatcher("/api/**")` chỉ thử API key cho private API routes; `/public` không bị thất bại vì header có giá trị lạ.
- `NoOpServerSecurityContextRepository` ở filter và HTTP chain không lưu authentication vào session. Mỗi request mới phải trình API key.
- Failure handler của filter trả **401** cho invalid credentials. Entry point trả **401** nếu thiếu credential, còn access denied handler trả **403** cho authenticated principal thiếu scope.
- `hasAuthority("SCOPE_items:read")` yêu cầu authority thực tế do manager cấp. Demo chỉ có read, nên POST /api/admin luôn 403 với key demo.
- `anyExchange().denyAll()` chặn routes chưa khai báo trước khi controller nhận.
- Tắt HTTP Basic/form login/logout để test không bị một cơ chế authentication khác can thiệp vào kết quả.
- **`csrf.disable()` chỉ áp dụng vì demo là API key header-only stateless, không dùng browser cookie/session credentials.** Không copy thiết lập này sang ứng dụng browser/OIDC login có cookie tự động; hãy threat-model CSRF và tách filter chains khi cần.
- Đây là một application SecurityWebFilterChain **thật**, không giả security config trong test. HTTP tests sẽ dùng đúng chain này.

### 5.11. Controller để quan sát 200 và 403

`src/main/java/dev/example/authntest/DemoController.java`:

```java
package dev.example.authntest;

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

    @GetMapping("/api/me")
    public Mono<String> me(Principal principal) {
        return Mono.just(principal.getName());
    }

    @GetMapping("/api/items")
    public Mono<Map<String, String>> items(Principal principal) {
        return Mono.just(Map.of(
                "client", principal.getName(),
                "result", "items-read-ok"));
    }

    @PostMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

**Vì sao đây là fixture HTTP hữu ích?**
- `/public` cho phép test filter matcher không vô tình bảo vệ public route.
- `/api/me` quan sát principal xác thực thật (`demo-client`).
- `/api/items` đòi quyền read, giúp test cả authn + authz + response body.
- `/api/admin` đòi write, giúp phân biệt **403** với **401**.
- Nếu controller trả principal `unverified` hoặc secret của key, đó là lỗi authentication pipeline; unit + HTTP tests sẽ phát hiện principal không đúng.
- Không gọi `.block()` hoặc tạo ThreadLocal authentication thủ công trong reactive controller.

### 5.12. Sinh local key bằng SecureRandom

`src/main/java/dev/example/authntest/LocalKeyGenerator.java`:

```java
package dev.example.authntest;

import java.security.SecureRandom;
import java.util.Base64;

public final class LocalKeyGenerator {

    private LocalKeyGenerator() {
    }

    public static void main(String[] args) {
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);

        String secret = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);

        // Chỉ dùng tạo key thử nghiệm.
        // Không đưa raw key vào production logs hoặc tài liệu.
        System.out.println("ak_demo_" + secret);
    }
}
```

Chạy trong dự án sau khi compile:

```bash
gradle classes
java -cp build/classes/java/main dev.example.authntest.LocalKeyGenerator
```

Generator in ra một key thử nghiệm **ngẫu nhiên**; không có key cụ thể được công bố trong bài. Đưa key vào biến môi trường `DEMO_API_KEY` của shell/IDE đang chạy ứng dụng, tránh commit/ghi vào CI logs. Đối với production, phải có provisioning/secret manager, scopes, expiry/revoke và audit; không tái sử dụng demo một JVM.

## 6. Unit test ServerAuthenticationConverter bằng MockServerWebExchange

Không cần Spring Boot, Netty, database hay security chain: instantiate trực tiếp `ApiKeyHeaderConverter` rồi tạo giả HTTP request bằng Spring Test.

Tệp `src/test/java/dev/example/authntest/ApiKeyHeaderConverterTests.java`:

```java
package dev.example.authntest;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiKeyHeaderConverterTests {

    private static final String VALID_FORMAT =
            "ak_demo_" + "A".repeat(43);

    private final ApiKeyHeaderConverter converter =
            new ApiKeyHeaderConverter();

    private MockServerWebExchange exchange(String... keyValues) {
        MockServerHttpRequest.BaseBuilder<?> builder =
                MockServerHttpRequest.get("/api/items");

        if (keyValues.length > 0) {
            builder.header("X-API-Key", keyValues);
        }

        return MockServerWebExchange.from(builder.build());
    }

    @Test
    void noHeaderReturnsEmptyMono() {
        StepVerifier.create(converter.convert(exchange()))
                .verifyComplete();
    }

    @Test
    void existingHeaderProducesUnauthenticatedToken() {
        StepVerifier.create(
                converter.convert(exchange(VALID_FORMAT)))
                .assertNext(authentication -> {
                    assertTrue(
                            authentication instanceof ApiKeyAuthenticationToken);
                    assertFalse(authentication.isAuthenticated());
                    assertEquals("unverified", authentication.getName());
                    assertEquals(
                            VALID_FORMAT, authentication.getCredentials());
                    assertTrue(authentication.getAuthorities().isEmpty());
                })
                .verifyComplete();
    }

    @Test
    void emptyHeaderIsAuthenticationError() {
        StepVerifier.create(converter.convert(exchange("")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void duplicateHeadersAreRejected() {
        StepVerifier.create(converter.convert(
                exchange(VALID_FORMAT, VALID_FORMAT)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void commaJoinedHeadersAreRejected() {
        StepVerifier.create(converter.convert(
                exchange(VALID_FORMAT + "," + VALID_FORMAT)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void nonApiKeySchemeIsRejectedEarly() {
        StepVerifier.create(converter.convert(
                exchange("Bearer not-an-api-key")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void oversizeHeaderIsRejectedEarly() {
        StepVerifier.create(converter.convert(
                exchange("ak_" + "Z".repeat(200))))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void headerNamesAreCaseInsensitive() {
        MockServerWebExchange lowercase =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/api/items")
                                .header("x-api-key", VALID_FORMAT)
                                .build());

        StepVerifier.create(converter.convert(lowercase))
                .assertNext(authentication ->
                        assertEquals(
                                VALID_FORMAT, authentication.getCredentials()))
                .verifyComplete();
    }
}
```

**Mục tiêu của 8 tests:**
- **`Mono.empty`** khi không có header: `verifyComplete()` không có onNext.
- **`Mono.just`** khi có header: kiểm tra type, `authenticated=false`, credentials giữ raw header **tạm thời**, authorities rỗng.
- **`Mono.error`** khi malformed/duplicate: kiểm tra đúng `BadCredentialsException`, không 200 hoặc 500 tùy tiện.
- Header case-insensitive nhưng credential value giữ nguyên.
- Test converter **không** kết luận secret thực đã đúng; thậm chí `"A".repeat(43)` chỉ là chuỗi có hình thức hợp lệ, chưa được manager xác thực.
- Không mock repository trong converter tests, vì converter đúng ra không gọi repository.

**Lưu ý type:** `MockServerHttpRequest.BaseBuilder<?>` là builder của Spring Test; nếu IDE dự án đang dùng version có tên generic class khác, có thể tránh helper builder bằng cách tạo `MockServerWebExchange.from(MockServerHttpRequest.get(...).header(...).build())` cho từng test. Code ở đây nhắm Spring Framework 6.1.x do Boot 3.3 quản lý.

### Một assertion dễ viết sai

```java
// SAI: convert(...) không có quyền đánh dấu authenticated.
StepVerifier.create(converter.convert(exchange(VALID_FORMAT)))
        .assertNext(auth -> assertTrue(auth.isAuthenticated()))
        .verifyComplete();
```

Test mong `isAuthenticated=true` ngay ở converter là **anti-pattern**; converter chỉ **trích credential**. Authentication manager mới chịu trách nhiệm xác minh.

## 7. Unit test ReactiveAuthenticationManager bằng StepVerifier

Thay repository thật bằng **fake reactive repository** do test chủ động điều khiển. Dùng `Clock.fixed` để kiểm tra thời điểm hết hạn chính xác, không dùng `Thread.sleep` hay phụ thuộc đồng hồ máy CI.

Test fixture:
- `TEST_SECRET_BYTES = new byte[32]`: **chỉ test**, không dùng làm credential thật.
- `KEY = "ak_demo_" + Base64URL(TEST_SECRET_BYTES)`.
- `Clock.fixed(2030-01-01T00:00:00Z, UTC)`.
- Record `demo-client`, `enabled=true`, `scope=items:read`, `expiresAt=NOW+300s`.

Tệp `src/test/java/dev/example/authntest/ApiKeyReactiveAuthenticationManagerTests.java`:

```java
package dev.example.authntest;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

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

    // Fixture tất định để test, KHÔNG có entropy thực.
    private static final byte[] TEST_BYTES = new byte[32];

    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(TEST_BYTES);

    private static final String KEY = "ak_demo_" + SECRET;

    private static final Instant NOW =
            Instant.parse("2030-01-01T00:00:00Z");

    private static final Clock NOW_CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private ApiKeyRecord record(
            boolean enabled, Instant expiresAt) {
        return new ApiKeyRecord(
                "demo",
                "demo-client",
                ApiKeyMaterial.sha256Hex(TEST_BYTES),
                Set.of("items:read"),
                enabled,
                expiresAt);
    }

    private ReactiveKeyRepository repository(ApiKeyRecord record) {
        return id -> id.equals(record.keyId())
                ? Mono.just(record) : Mono.empty();
    }

    private ApiKeyReactiveAuthenticationManager manager(
            ReactiveKeyRepository repository,
            Clock clock) {
        return new ApiKeyReactiveAuthenticationManager(
                repository, clock);
    }

    private ApiKeyReactiveAuthenticationManager activeManager() {
        return manager(
                repository(record(true, NOW.plusSeconds(300))),
                NOW_CLOCK);
    }

    @Test
    void correctKeyEmitsAuthenticatedIdentityAndServerScopes() {
        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .assertNext(authentication -> {
                    assertTrue(authentication.isAuthenticated());
                    assertEquals("demo-client",
                            authentication.getName());
                    assertNull(authentication.getCredentials());
                    assertTrue(authentication.getAuthorities().stream()
                            .anyMatch(authority ->
                                    authority.getAuthority().equals(
                                            "SCOPE_items:read")));
                    assertFalse(authentication.getAuthorities().stream()
                            .anyMatch(authority ->
                                    authority.getAuthority().equals(
                                            "SCOPE_items:write")));
                })
                .verifyComplete();
    }

    @Test
    void knownIdWithWrongSecretFailsAuthentication() {
        byte[] wrongSecret = new byte[32];
        wrongSecret[0] = 1;

        String wrongKey = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(wrongSecret);

        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request(wrongKey)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unknownKeyIdIsAnErrorNotAnEmptyMono() {
        String unknown = "ak_unknown_" + SECRET;

        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request(unknown)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void malformedApiKeyFailsAuthentication() {
        StepVerifier.create(activeManager().authenticate(
                ApiKeyAuthenticationToken.request("not-an-api-key")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedAuthenticationTypeReturnsEmptyMono() {
        Authentication basic =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "user", "password");

        StepVerifier.create(activeManager().authenticate(basic))
                .verifyComplete();
    }

    @Test
    void disabledKeyFailsAuthentication() {
        var target = manager(
                repository(record(false, NOW.plusSeconds(300))),
                NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void expiredKeyFailsWithoutSleeping() {
        var target = manager(
                repository(record(true, NOW.minusSeconds(1))),
                NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void exactExpiryInstantFailsWithoutRace() {
        var target = manager(
                repository(record(true, NOW)),
                NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void repositoryFailureIsPropagatedNotAllowed() {
        ReactiveKeyRepository unavailable =
                id -> Mono.error(new IllegalStateException(
                        "Key store unavailable"));

        var target = manager(unavailable, NOW_CLOCK);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(IllegalStateException.class)
                .verify();
    }

    @Test
    void authenticationWorkIsDeferredUntilSubscription() {
        AtomicInteger lookups = new AtomicInteger();

        ReactiveKeyRepository instrumented = id -> {
            lookups.incrementAndGet();
            return Mono.just(record(true, NOW.plusSeconds(300)));
        };

        var target = manager(instrumented, NOW_CLOCK);

        Mono<Authentication> result = target.authenticate(
                ApiKeyAuthenticationToken.request(KEY));

        // Chưa subscribe -> chưa đọc repository.
        assertEquals(0, lookups.get());

        StepVerifier.create(result)
                .expectNextCount(1)
                .verifyComplete();

        assertEquals(1, lookups.get());
    }

    @Test
    void asyncRepositoryCanBeTestedWithVirtualTime() {
        ReactiveKeyRepository delayed = id ->
                Mono.delay(Duration.ofSeconds(10))
                        .thenReturn(
                                record(true, NOW.plusSeconds(300)));

        var target = manager(delayed, NOW_CLOCK);

        StepVerifier.withVirtualTime(() ->
                target.authenticate(
                        ApiKeyAuthenticationToken.request(KEY)))
                .thenAwait(Duration.ofSeconds(10))
                .assertNext(auth ->
                        assertTrue(auth.isAuthenticated()))
                .verifyComplete();
    }
}
```

### Phân tích 11 manager tests

| Nhóm | Test | Kết quả mong đợi |
| --- | --- | --- |
| Success | Correct key | Exactly one verified Authentication rồi complete |
| Secret validation | Same ID, wrong secret | `BadCredentialsException` |
| Missing record | Unknown ID | Error, **không** empty |
| Input validation | Malformed raw key | Error |
| Unsupported type | UsernamePasswordAuthenticationToken | **Empty Mono** |
| Status | Disabled | Error |
| Expiration | Before/at expiry boundary | Error |
| Failure propagation | Repository unavailable | `IllegalStateException`, không được accept |
| Laziness | Before subscribe | Zero repository lookups |
| Asynchronous | `Mono.delay` + virtual time | Test nhanh, không sleep |

**Một điểm quan trọng:** `StepVerifier.withVirtualTime(...)` chỉ thay scheduling của **Reactor timers** như `Mono.delay`. Nó **không tự tua `java.time.Clock`** mà manager đang sử dụng. Muốn test expiry, hãy inject `Clock.fixed(...)` như ở hai tests expiration. Đừng phụ thuộc `Thread.sleep(1000)` hoặc system clock để kiểm tra boundary: đó là flaky test.

**Cân nhắc lỗi repository:**
- `Mono.error(IllegalStateException)` từ store không phải “API key sai” về mặt nghiệp vụ; hạ tầng thật cần error mapping/monitoring an toàn.
- Nhưng error này **không được chuyển thành authenticated principal**. Với API bảo mật, fail-open im lặng nguy hiểm hơn availability loss.
- Unit test có thể xác nhận error được truyền; HTTP/E2E cần quy định 5xx/503/circuit breaker tùy hệ thống.

**Tại sao tests không dùng Spring context?** Vì đây là unit tests của contract manager, dependency duy nhất là fake repository và fixed clock. Chúng chạy nhanh và cho tín hiệu lỗi chính xác. Test Spring Boot context dành cho đường filter+HTTP ở mục sau.

## 8. HTTP integration tests: WebTestClient với manager/converter thật

Để chứng minh cả **`AuthenticationWebFilter`**, **`ServerAuthenticationConverter`**, **`ReactiveAuthenticationManager`**, **`SecurityWebFilterChain`** hoạt động cùng nhau, gửi **HTTP header `X-API-Key` thực** trong mock WebFlux server:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

`springSecurity()` ở đây là test configurer của Spring Security WebFlux. **Không dùng `mockUser()` trong các tests kiểm tra credential**; nếu mockUser pass, nó không hề chứng minh manager kiểm tra secret.

Test fixtures được cung cấp bằng `@DynamicPropertySource` thay property `demo.api-key` khi test Spring Boot context khởi động. Điều này giúp production/demo không có insecure default key, còn tests thì deterministic.

Tệp `src/test/java/dev/example/authntest/ApiKeyHttpTests.java`:

```java
package dev.example.authntest;

import java.util.Base64;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ApiKeyHttpTests {

    // CHỈ LÀ FIXTURE TEST: all-zero bytes không có entropy.
    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(new byte[32]);

    private static final String KEY = "ak_demo_" + SECRET;

    @DynamicPropertySource
    static void demoKeyProperty(DynamicPropertyRegistry registry) {
        registry.add("demo.api-key", () -> KEY);
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteDoesNotRequireApiKey() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateRouteWithoutKeyIs401() {
        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctKeyAndReadScopeAreAccepted() {
        client.get().uri("/api/items")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.client")
                .isEqualTo("demo-client")
                .jsonPath("$.result")
                .isEqualTo("items-read-ok");
    }

    @Test
    void principalAfterRealAuthenticationIsTrustedClientId() {
        client.get().uri("/api/me")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("demo-client");
    }

    @Test
    void malformedHeaderReturns401() {
        client.get().uri("/api/items")
                .header("X-API-Key", "not-an-api-key")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownKeyIdReturns401() {
        client.get().uri("/api/items")
                .header("X-API-Key", "ak_unknown_" + SECRET)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongSecretReturns401() {
        byte[] altered = new byte[32];
        altered[0] = 1;

        String wrongKey = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(altered);

        client.get().uri("/api/items")
                .header("X-API-Key", wrongKey)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void duplicateHeaderValuesReturn401() {
        client.get().uri("/api/items")
                .headers(headers -> {
                    headers.add("X-API-Key", KEY);
                    headers.add("X-API-Key", KEY);
                })
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void keyCanAuthenticateButFailAuthorization() {
        client.post().uri("/api/admin")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void authenticationIsNotRememberedOnNextRequest() {
        client.get().uri("/api/items")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDeniedByDefault() {
        client.get().uri("/api/unknown")
                .header("X-API-Key", KEY)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void publicRouteIgnoresMalformedApiKeyHeader() {
        // Filter matcher /api/** không kích hoạt tại /public.
        client.get().uri("/public")
                .header("X-API-Key", "not-an-api-key")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("public-ok");
    }
}
```

### Vì sao 12 HTTP tests này có giá trị?

- **Không dùng authentication mocks**: để lấy được 200, request phải đi qua `ApiKeyHeaderConverter.convert`, `ApiKeyReactiveAuthenticationManager.authenticate`, repository, digest, enabled/expiry và authorization.
- **401 missing header**: converter returns empty, security policy yêu cầu auth.
- **401 malformed/duplicate**: converter hoặc manager báo lỗi, failure handler chuyển thành unauthorized.
- **200 valid**: principal phải là ID đã được xác minh từ server metadata, không phải raw header.
- **403 valid nhưng thiếu `SCOPE_items:write`**: chứng minh authentication và authorization là hai quyết định khác nhau.
- **401 request thứ hai**: không có authentication lưu lại qua WebSession, nên mỗi request cần key.
- **403 unknown path**: `anyExchange().denyAll()` ngăn route khác bị mở ngầm.
- **200 public với header malformed**: matcher chỉ đọc API keys trên `/api/**`, không áp filter lên mọi public request.

**Giới hạn:** Tests chạy mock WebFlux HTTP stack trong Spring ApplicationContext, không qua TLS/Netty TCP socket hoặc proxy thật. Repository demo nằm trong memory một JVM và chưa test concurrency/multi-replica key rotation.

### Không “test manager” bằng cách mock manager

Một suite như:

```java
// ANTI-PATTERN khi mục tiêu là test manager thật:
@MockBean
ReactiveAuthenticationManager manager;

// ... stub:
when(manager.authenticate(any()))
        .thenReturn(Mono.just(
                ApiKeyAuthenticationToken.verified(
                        "demo-client", List.of())));
// rồi assert HTTP 200
```

Đây là **fragment anti-pattern**. Nó có thể kiểm tra filter wiring, nhưng **không kiểm tra hash, expiry, disabled, error propagation và principal mapping trong manager thật**. Test này có giá trị ở cấp **filter-only isolation** khi bạn chủ động muốn mock manager; đừng quảng cáo thành authentication integration test.

### Không “test converter” bằng mockUser()

```java
// ANTI-PATTERN nếu định kiểm tra X-API-Key header parser:
client.mutateWith(mockUser("admin"))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
```

`mockUser()` tạo SecurityContext test. Không cần header `X-API-Key` và không bảo đảm converter được gọi. Mẫu chỉ phù hợp kiểm tra authorization khi đã giả lập identity.

## 9. Chạy tests và diễn giải kết quả

Từ thư mục `reactive-authn-testing`:

```bash
gradle test
```

Nếu có Gradle Wrapper:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

**Dự kiến theo code:** 
- 8 converter unit tests.
- 11 manager unit tests.
- 12 HTTP integration tests.
- **Tổng 31 JUnit tests**.

Đây là **số test dự kiến** trong các tệp của bài, không phải báo cáo Gradle đã chạy thật. Khi thực thi, xem report `build/reports/tests/test/index.html` hoặc test runner của IDE/CI.

Kết quả mong đợi quan trọng:

| Request / Test | Kết quả |
| --- | --- |
| Converter không header | `Mono.empty()` |
| Converter header hợp lệ | Exactly one `Authentication(false)` |
| Converter duplicated/malformed | `BadCredentialsException` |
| Manager unsupported type | `Mono.empty()` |
| Manager valid key | `Authentication(true)`, credentials null |
| Manager wrong/missing/disabled/expired | `BadCredentialsException` |
| Manager store outage | Error propagated, không authenticated |
| GET `/public` | 200 |
| GET `/api/items` không key | 401 |
| GET `/api/items` key đúng | 200 + verified client ID |
| GET `/api/items` key sai | 401 |
| POST `/api/admin` key đúng, thiếu scope | 403 |
| Một request key đúng, request sau không key | 200 rồi 401 |

### Một kịch bản tối thiểu ngoài JUnit

Sinh key local `SecureRandom` bằng `LocalKeyGenerator`, đưa `DEMO_API_KEY` vào environment rồi chạy:

```bash
gradle bootRun
```

Sau đó (chỉ trên localhost để học tập):

```bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/api/items

curl -i -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/items

curl -i -H "X-API-Key: $DEMO_API_KEY" \
  -X POST http://localhost:8080/api/admin
```

**Kỳ vọng:** public 200, private thiếu key 401, items có key đúng 200, POST admin thiếu scope 403. Nếu dùng Windows PowerShell, cú pháp môi trường và continuation khác Bash; thay ví dụ shell phù hợp môi trường.

**Chú ý bảo mật:** `curl -H "X-API-Key: ..."` có thể hiển thị credential qua process listing hoặc shell history tùy hệ điều hành; với key thật, ưu tiên secret-aware HTTP client hoặc integration test không log headers. Trong production luôn dùng HTTPS/TLS.

## 10. Dùng StepVerifier nâng cao và tránh flaky tests

### 10.1. Ba loại assertion tín hiệu

```java
// Thành công đúng một giá trị và kết thúc.
StepVerifier.create(successMono)
        .expectNextCount(1)
        .verifyComplete();

// Không xử lý: không giá trị, kết thúc bình thường.
StepVerifier.create(unsupportedMono)
        .verifyComplete();

// Thất bại: phải phát AuthenticationException.
StepVerifier.create(invalidMono)
        .expectError(BadCredentialsException.class)
        .verify();
```

Đây là **fragments**; `successMono`, `unsupportedMono` và `invalidMono` là các biến trong tests cụ thể. `expectNextCount(1)` chỉ đếm, còn `assertNext(...)` có thể kiểm tra credential cleanup/principal/authorities.

### 10.2. Timeout cho test I/O

Trong một test có Redis/R2DBC/WebClient thật, `StepVerifier.verify()` không có timeout mặc định hữu ích trừ khi được cấu hình. Có thể dùng:

```java
StepVerifier.create(manager.authenticate(request))
        .expectNextCount(1)
        .verifyComplete();
```

Dạng trên phù hợp Mono đồng bộ/hữu hạn trong fixture. Với nguồn I/O, cân nhắc:

```java
StepVerifier.create(manager.authenticate(request))
        .expectNextCount(1)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Đây là **fragment cần import `Duration`**, đặt giới hạn thời gian test để CI không treo. Timeout 3 giây chỉ là minh họa; chọn theo performance envelope/CI thực tế. Không dùng `Thread.sleep` để chờ event trong test.

### 10.3. Virtual time không đồng nghĩa đồng hồ ứng dụng

`Mono.delay(Duration.ofSeconds(10))` thuộc Reactor scheduler nên có thể test bằng `StepVerifier.withVirtualTime(...)`:

```java
StepVerifier.withVirtualTime(() ->
        manager.authenticate(candidate))
        .thenAwait(Duration.ofSeconds(10))
        .expectNextCount(1)
        .verifyComplete();
```

**Nhưng `Clock.instant()` mà manager dùng sẽ không tự nhảy 10 giây**. Đối với expiry/lockout, inject `Clock.fixed` hoặc một controllable clock trong test. Cần đặt `Mono.delay` bên trong publisher được tạo sau virtual scheduler initialization nếu sử dụng custom scheduling phức tạp.

### 10.4. Kiểm tra laziness/deferred side effects

Manager trả `Mono.defer(...)` để lookup **không chạy khi method được gọi**, chỉ khi subscription. Test `authenticationWorkIsDeferredUntilSubscription` sử dụng `AtomicInteger` trong repository:

```text
construct Mono --> lookups = 0
subscribe      --> lookups = 1
complete       --> no extra lookup
```

Nếu một manager gọi DB blocking **trước khi trả Mono**, test này có thể phát hiện số lookups tăng trước subscription (nếu fake repository đo được đúng điểm gọi). Đừng dùng `Mono.just(repository.blockingLookup(...))`, vì đối số được thực thi ngay tại method invocation.

### 10.5. Test các tín hiệu lỗi cụ thể

Một regression suite tốt không chỉ `expectError()` chung chung, mà xác minh:
- `BadCredentialsException` cho invalid key.
- `Mono.empty` cho unsupported authentication **type**.
- `IllegalStateException` hoặc error phù hợp cho store unavailable.
- Nếu malformed input gây `ClassCastException`/`NullPointerException` thay vì BadCredentials, converter/manager có thể bị bug.
- Error không bị `onErrorResume(e -> Mono.just(verified))` làm thành công.

**Đừng assert response body luôn chứa “unknown key id”, “digest mismatch”, “disabled client”**. Generic 401 tốt hơn cho client; audit nội bộ có thể ghi mã lỗi không chứa secret.

## 11. Khi nào cần test AuthenticationWebFilter riêng?

Ngoài unit và full HTTP integration, đôi khi muốn cô lập chính filter. Ví dụ sau là **fragment định hướng**, không phải file Java hoàn chỉnh:

```java
AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);
filter.setServerAuthenticationConverter(converter);
filter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"));
filter.setSecurityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());
filter.setAuthenticationFailureHandler(
        new ServerAuthenticationEntryPointFailureHandler(
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)));
```

Sau đó test qua `MockServerWebExchange`/`WebFilterChain` có thể xem:
- Converter có được gọi khi path match không?
- Với absent credential, downstream filter chain có được gọi không?
- Với invalid credential, failure handler có trả 401 không?
- Với valid credential, downstream thấy authenticated principal trong Reactor Context không?
- Khi converter Mono.error, manager có bị gọi không?
- Với manager Mono.empty, filter ứng xử thế nào?

**Không bắt buộc tạo một filter-only test suite để hoàn thành bài** vì `WebTestClient` integration đã bao phủ wiring thực, nhưng filter-only tests hữu ích nếu nhiều custom matchers, authentication managers hoặc scheme precedence.

### Kiểm soát số lần gọi bằng fake manager

```java
AtomicInteger invocations = new AtomicInteger();

ReactiveAuthenticationManager spyManager = request -> {
    invocations.incrementAndGet();
    return Mono.error(
            new BadCredentialsException("Invalid API key"));
};
```

Đây là fragment. Với test converter trả empty, manager invocation phải bằng 0. Với malformed header, converter nên fail trước manager. Với valid header shape, manager được gọi đúng một lần. **Đừng tính việc tạo Mono là request HTTP đã chạy**: Spring Security/Reactor phải subscribe publisher trước khi action phát sinh.

### Một nuance: failure handler vs authorization entry point

Hai lỗi có thể được tạo từ nơi khác nhau:
- **Header có mặt nhưng sai:** `AuthenticationWebFilter` gọi authentication failure handler, HTTP 401.
- **Header vắng mặt:** converter empty, filter tiếp tục, `AuthorizationWebFilter` thấy anonymous; `ExceptionTranslationWebFilter` dùng authentication entry point, HTTP 401.
- **Header hợp lệ nhưng thiếu scope:** authentication success, sau đó access denied handler, HTTP 403.

Cho nên cần test **cả missing, invalid và insufficient-scope**, không chỉ một request trả 401 và một request trả 200.

## 12. Kiểm thử tích hợp với database/Redis và lỗi phân tán

Demo repository memory giúp kiểm tra manager contract nhanh, nhưng production key store thường nằm trong Redis/R2DBC hoặc auth service. Khi thay nguồn, bổ sung:

| Tình huống | Test cần có | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| DB record active | Manager tạo principal | Lookup/schema sai |
| Key bị revoke/disabled | Request mới 401 | Cache còn enabled cũ |
| Key vừa expired | Manager 401 | Clock skew/stale record |
| Store `Mono.empty` | BadCredentials | Missing record bị coi là không có auth attempt |
| Store timeout | Error/fail closed | Fail-open hoặc request treo |
| Store network reset | Error/fail closed; retry có giới hạn | Retry amplification |
| Hai replicas | Cùng key/expiry/revocation state | Node A deny, node B allow |
| Key rotation overlap | New key accepted, old key disabled theo SLA | Downtime/lộ key cũ |
| Quota/rate limit | Giới hạn abusive traffic | Brute-force/DoS |
| Đồng thời nhiều requests | Không leak SecurityContext giữa users | Cross-request identity confusion |
| Wrong tenant/resource | Access denied dù key đúng | Cross-tenant IDOR |
| Gateway header rewriting | Converter nhận đúng `X-API-Key` | 401 tại ingress hoặc auth bypass |
| Secret redaction | Logs/APM không chứa key | Credential leakage |

### Testcontainers/R2DBC khi cần

Một integration test có thể dùng Testcontainers khởi động PostgreSQL/Redis thật, nạp hai bản ghi key:
- `demo-read` enabled, scope read;
- `demo-disabled` disabled;
- expiry rõ ràng dùng `Clock` được điều khiển.

Sau đó thay `ReactiveKeyRepository` bằng adapter thật để kiểm tra query/connection behavior. Khi đặt key vào DB fixture, **lưu digest**, không lưu raw secret. Những tests này khác unit tests manager trong bài và thường nằm trong suite integration chạy CI có hạ tầng phù hợp.

### Quan trọng với revoke SLA

Nếu key registry cache một record `enabled=true` trong 5 phút, admin revoke sẽ không được áp ngay trên mọi instance. Cần định nghĩa:
- mốc bắt đầu tính (revoke transaction commit),
- TTL cache/negative cache,
- replication lag,
- max propagation delay,
- fail-open/fail-closed khi store outage,
- trường hợp request đã authenticate trước revoke nhưng còn đang xử lý.

**Một unit test manager trong một JVM không chứng minh revocation tức thời toàn cluster.**

### Reactive performance và scheduler

- Repository blocking JDBC trực tiếp trong `flatMap` có thể block Netty event loop.
- Dùng R2DBC/reactive Redis/WebClient, connection pool và bounded timeout.
- Nếu buộc dùng blocking driver, cô lập bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` có giới hạn và monitoring; không xem nó là giải pháp thay reactive driver cho mọi tải.
- Test timeout/cancellation/circuit breaker; không tạo retry vô hạn trong đường authentication.
- Không gọi `.subscribe()` tự phát trong manager/filter: hãy trả publisher để framework quản lý.

## 13. Bảo mật đặc biệt cho test fixtures và logs

### 13.1. Không đưa API key thật vào mã kiểm thử

Test fixture `new byte[32]` trong unit tests là **không an toàn nếu dùng production**. Nó chỉ có tác dụng tạo dữ liệu deterministic để assert. Production key phải được cấp bằng `SecureRandom`, đủ entropy và chỉ hiển thị một lần.

Dùng dummy ID/secret khác nhau giữa unit và dev/staging/prod. Không commit `.env` chứa live key hoặc client secrets.

### 13.2. Không log credential khi assertion fail

Nếu một test HTTP fail:
- Không in nguyên `X-API-Key`, `Authorization` hoặc response headers chứa token.
- Tránh sử dụng `toString()` của raw Authentication hoặc request trong error diagnostics nếu có thể bao gồm credential.
- Log sanitized key ID nếu policy cho phép, không log secret/digest.
- Redact trong CI, APM, reverse proxy, HTTP trace collector.
- Không để screenshot/network traces mang bearer secrets đi vào tài liệu công khai.

### 13.3. Timing/constant-time

`MessageDigest.isEqual` giúp so digest bytes theo cách tránh comparison loop ngây thơ. Nhưng thời gian lookup unknown ID có thể khác known ID; response body/status phải generic, rate limiting và abuse detection cần thiết. Không tự tạo random sleep như biện pháp bảo mật: có thể gây DoS và không loại bỏ side channels.

### 13.4. Thay hash của random API key bằng password hash khi nào?

Random API key 256-bit entropy khác mật khẩu do người dùng nhập. Với random secret, SHA-256/HMAC verifier thường phù hợp khi được kết hợp với kiểm soát quyền lưu trữ, rate limits, rotation và breach monitoring. Với **mật khẩu người dùng**, không được dùng SHA-256 một lượt; dùng Argon2/bcrypt/scrypt theo hướng dẫn hiện hành.

### 13.5. CSRF, CORS và browser

Demo là **machine-to-machine API key-only**, nhận credential chủ động trong custom header và không có session cookie browser credentials, nên ví dụ tắt CSRF có điều kiện. Nếu ứng dụng hỗn hợp browser session/OIDC, không được tắt CSRF toàn cục vì test POST không pass.

`X-API-Key` là custom header, cross-origin browser request có thể cần CORS preflight; preflight thường không mang raw API key. Nếu bắt preflight gửi key, browser có thể không thực hiện request thật. Tuy nhiên **không nhúng một shared server API key vào SPA/mobile public**: người dùng có thể lấy key từ JS bundle/DevTools hoặc binary.

## 14. Các lỗi test thường gặp

| Lỗi | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Converter trả empty khi header duplicate | Code dùng `getFirst` rồi bỏ phần còn lại | Kiểm tra `get(...)` list và reject duplicates |
| Converter đánh dấu token authenticated | Nhầm trách nhiệm HTTP parsing/authentication | Factory request tạo authenticated=false |
| Manager trả empty cho key sai | Nhầm “unsupported” với “invalid” | `Mono.error(BadCredentialsException)` |
| Manager trả lại unauthenticated token | Chưa tạo verified principal | Chỉ trả authenticated sau verify |
| Manager bỏ qua disabled/expiry | Chỉ so hash | Test `enabled`, `Clock.fixed` expiry boundary |
| Credentials vẫn lưu sau success | Verified token giữ raw key | Assert `getCredentials()==null` |
| Unit test chỉ assert `expectNextCount(1)` | Không biết principal/authorities có đúng | Dùng `assertNext` cho nội dung |
| Test manager gọi repo trước subscribe | Thực thi đồng bộ trước khi tạo Mono | `Mono.defer` và counter assertion |
| Test expiry flaky | `Instant.now()` + `Thread.sleep` | Inject `Clock.fixed`/test clock |
| Test timeout treo CI | `StepVerifier.verify()` không có timeout rõ | `verify(Duration)` trong I/O tests |
| Store outage dẫn tới 200 | Có `onErrorResume(...allow)` | Fail-closed và monitor |
| HTTP 401 test thiếu key nhưng filter không chạy | Missing key được authorization entry point xử lý | Test thêm invalid key và valid key để bao phủ manager |
| HTTP test dùng `mockUser()` | Bypass converter/manager | Gửi header `X-API-Key` thật |
| HTTP test chỉ dùng `bindToController` | Thiếu SecurityWebFilterChain | Bind Spring ApplicationContext + springSecurity() |
| HTTP test dùng `bindToServer()` với mock mutators | Mock context không được truyền qua TCP | Dùng credentials thật cho live HTTP |
| Thiếu `spring-security-test` | Không có `springSecurity()` | Thêm test dependency đúng Boot BOM |
| Đặt `SecurityWebFiltersOrder` sai | Authentication sau authorization | Dùng `AUTHENTICATION` phase |
| 401 biến thành 302 | Form login được bật | Disable form login cho API hoặc dùng entry point rõ |
| 403 khi key đúng ở read | Scope mapping mismatch | Assert `SCOPE_items:read` và route policy |
| 403 khi POST ở browser app | Thiếu CSRF token | Giữ CSRF, dùng `csrf()` đúng mock-server test |
| Mặc định TestWebClient có mock admin | Anonymous test không còn đúng | Tạo fresh client per test |
| HTTP test 200 nhưng principal sai | Controller chỉ assert status | Assert JSON/client identity |
| Mất quyền khi nhiều replicas | Map in-memory/key store stale | Shared repository và consistency test |
| Converter nhận credential qua query URL | Secret bị log/referrer | Header only; redaction |
| Test trace chứa raw API key | Failure logging/CI artifacts | Không log headers, rotate nếu lộ |
| Nâng framework làm type/import lỗi | Dùng docs phiên bản khác | Chọn Spring Security/Framework docs đúng BOM |

## 15. Checklist QA trước khi merge

- [ ] Test converter riêng bằng `MockServerWebExchange`, không cần Spring Boot.
- [ ] Test converter **absent/valid/duplicate/oversize/malformed**.
- [ ] Converter không cấp authenticated principal hoặc authorities.
- [ ] Test manager riêng bằng `StepVerifier` với fake reactive repository.
- [ ] Manager returns **Mono.empty cho unsupported type**.
- [ ] Manager returns **Mono.error cho invalid key**.
- [ ] Manager returns **Mono.just verified Authentication** cho valid key.
- [ ] Test principal, scopes server-side, credential erasure.
- [ ] Test disabled, expired, exact expiry và missing record.
- [ ] Test repository failure không biến thành allow.
- [ ] Test defer: lookup chỉ chạy sau subscription.
- [ ] Nếu dùng delay, test với Reactor virtual time; expiry dùng `Clock.fixed`.
- [ ] Test HTTP đi qua **filter + converter + manager thật**, không dùng mockUser.
- [ ] Test private without key = 401, wrong key = 401, valid read = 200, missing scope = 403.
- [ ] Test duplicate header / unknown path / no session leakage.
- [ ] Client test dựng từ đúng ApplicationContext và `.apply(springSecurity())`.
- [ ] CSRF được bật/tắt có cơ sở từ loại credentials; không copy `csrf.disable()` vào app browser.
- [ ] Production logs/proxy/APM redaction bao phủ `X-API-Key` và Authorization.
- [ ] Test không chứa production credentials hoặc raw API key trong reports.
- [ ] Có test store/Redis/R2DBC, timeout, multi-instance revoke khi đưa production.
- [ ] Security code không block event loop hoặc tự `subscribe()`.
- [ ] Test report được xem thực tế sau khi chạy Gradle; không chỉ dựa vào mã minh họa.
- [ ] Spring Boot/Spring Security versions production được cập nhật và hỗ trợ.

## 16. Câu hỏi tự kiểm tra

**1. `ServerAuthenticationConverter` làm gì?**  
Chuyển HTTP exchange thành một `Mono<Authentication>` chưa được xác thực dựa trên credential request, không kiểm tra hash/DB.

**2. Khi không có credential của scheme, converter trả gì?**  
`Mono.empty()`, nghĩa là không thực hiện authentication attempt của scheme đó.

**3. Manager không hỗ trợ loại Authentication đầu vào thì sao?**  
`Mono.empty()` theo contract vì không đưa ra quyết định cho loại này.

**4. Credential của loại manager hỗ trợ nhưng sai thì sao?**  
`Mono.error(AuthenticationException)`, như `BadCredentialsException`.

**5. Tại sao không trả `Mono.empty()` cho API key sai?**  
Vì nó dễ che thất bại, gây nhầm multi-manager flows; manager cần signal authentication failure.

**6. Thành công cần assert gì ngoài `isAuthenticated()`?**  
Principal đáng tin, authorities đúng, credentials null, đúng một onNext rồi onComplete.

**7. `StepVerifier.verifyComplete()` khác `expectError(...).verify()` như thế nào?**  
Một cái xác nhận kết thúc không lỗi, cái kia xác nhận terminal error đúng loại.

**8. `MockServerWebExchange` kiểm tra được gì?**  
Converter xử lý method/path/headers và tạo Authentication, không cần HTTP network.

**9. Tại sao dùng `Clock.fixed`?**  
Test disabled/expired/boundary chính xác, không dựa timing của CI.

**10. `withVirtualTime` có tự tăng `Clock.instant()` không?**  
Không; chỉ điều khiển Reactor timer/scheduler khi dùng đúng.

**11. Vì sao `Mono.defer` hữu ích trong manager?**  
Cho phép parse/hash/repository lookup chạy lúc subscribe, không tạo blocking side effect trước publisher.

**12. Test manager qua `mockUser()` có đúng mục tiêu không?**  
Không. `mockUser()` bypass manager/converter, chỉ phù hợp test authz.

**13. `springSecurity()` dùng ở đâu?**  
Khi tạo mock WebTestClient qua `bindToApplicationContext(context).apply(springSecurity()).configureClient().build()`.

**14. Vì sao cần test both missing header và wrong header?**  
Missing có thể thất bại ở authorization entry point, còn wrong kiểm tra failure path của converter/manager.

**15. Vì sao valid key mà thiếu scope trả 403?**  
Authentication đã thành công, authorization không đủ authority cần thiết.

**16. Khi repository trả `Mono.empty` cho unknown ID, manager nên làm gì?**  
Chuyển thành `BadCredentialsException`; không trả empty cho sai credential của scheme này.

**17. Khi store timeout, có nên trả verified principal để giữ availability không?**  
Không nên với API security cần fail-closed; thiết kế outage response rõ.

**18. Vì sao dùng SHA-256 thay bcrypt trong ví dụ key?**  
Vì secret là 256-bit random; khác password entropy thấp. Production còn cần rotation, rate-limit và bảo vệ verifier.

**19. Tại sao credentials nên null trong Authentication thành công?**  
Giảm rủi ro key bị lộ qua context/logging/serialization.

**20. Dùng `NoOpServerSecurityContextRepository` có bảo đảm mọi request độc lập không?**  
Nó không lưu context ở repository; còn các authentication schemes/gateway state khác cũng phải được xem xét. Test request thứ hai không header.

**21. Bao nhiêu lớp test nên có?**  
Converter unit, manager unit, HTTP integration; bổ sung persistence/E2E theo rủi ro.

**22. Khi nào dùng test with real Netty/TLS/proxy?**  
Khi cần xác nhận HTTP network, certificate, header forwarding, cookies hoặc infrastructure behavior mà mock WebTestClient không thể chứng minh.

### Bài tập thực hành

1. Chạy 8 converter tests, diễn giải vì sao header vắng mặt là empty còn header malformed là error.
2. Chạy 11 manager tests, tách unsupported type với wrong key và kiểm tra credentials null sau success.
3. Chạy 12 HTTP tests và giải thích 200/401/403 dựa trên ba tầng converter/manager/authorization.
4. Thử đổi converter thành `getFirst("X-API-Key")`, quan sát duplicate-header test thất bại và phân tích rủi ro HTTP request smuggling/mismatch ở gateway.
5. Thử manager trả `Mono.empty()` cho wrong key, phân tích khác biệt failure handler và authorization entry point.
6. Thử đưa raw credential vào principal verified, viết test phát hiện leak và sửa bằng credentials null.
7. Thử xóa `.apply(springSecurity())` ở mock WebTestClient setup và nhận xét khác biệt test integration/mutators.
8. Thử dùng `mockUser("demo-client")` thay header trong một test, chỉ ra những mã không còn được kiểm thử.
9. Thêm record key disabled vào fake repository, assert BadCredentials exception.
10. Thêm kiểm tra `expiresAt` với Clock.fixed ngay trước và bằng thời điểm expiry; không dùng Thread.sleep.
11. Mô phỏng repository delay 60s bằng `Mono.delay` và viết `StepVerifier.withVirtualTime`.
12. Thêm giới hạn timeout cho manager I/O, test timeout fail-closed bằng virtual time.
13. Thêm policy `SCOPE_items:write` cho một key khác và test POST admin 200, trong khi key read chỉ 403.
14. Thay demo repository bằng R2DBC/Redis và test 2 instances cùng thấy revoked key.
15. Test converter header name case-insensitive nhưng credential value case-sensitive.
16. Thêm tenant ID vào trusted key record và test resource ownership, tránh cross-tenant IDOR.
17. Dựng `bindToServer()`/RANDOM_PORT integration test gửi key thật qua HTTP, so với mock client.
18. Thiết kế rate limiting, generic 401 và logs redaction để giảm brute force/credential enumeration.
19. Kiểm thử gateway/proxy không tự chèn hoặc log `X-API-Key`.
20. Với hệ thống nhiều auth schemes, viết tests khi request chứa đồng thời `X-API-Key` và `Authorization: Bearer`; từ chối mơ hồ hoặc xác định thứ tự theo policy.
21. Viết thêm một filter-only test với spy manager để đo `0` invocations khi converter trả empty và `1` khi header có mặt.
22. Mô phỏng Redis outage, xác nhận manager không phát authenticated principal, ghi metric đã sanitize.

## 17. Tài liệu tham khảo chính thức

- [Spring Security — ReactiveAuthenticationManager API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html): ý nghĩa `Mono<Authentication>` success/empty/error.
- [Spring Security — ServerAuthenticationConverter API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): `convert(ServerWebExchange)` và empty khi không có attempt.
- [Spring Security — AuthenticationWebFilter API 6.3](https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): converter/manager, matcher, success/failure handlers và context repository.
- [Spring Security — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext(...).apply(springSecurity())`.
- [Spring Security — Reactive Authentication Test Support](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()`/`@WithMockUser` và phạm vi mocks.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): điều kiện CSRF và application security.
- [Spring Framework — MockServerWebExchange](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/mock/web/server/MockServerWebExchange.html): mock reactive exchange trong tests.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock-server vs live-server binding, HTTP assertions.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, timeouts và reactive signals.
- [Project Reactor — Reactor Test API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `assertNext`, `expectError`, `verify(Duration)`.
- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, granted authorities và deny-by-default.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): TLS, credential handling, authentication/authorization.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): key storage, rotation, redaction.
- [Oracle Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn CSPRNG cho API keys.
- [Oracle Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `MessageDigest.isEqual`.

**Ghi nhớ:** Kiểm thử **`ServerAuthenticationConverter`** bằng `MockServerWebExchange` để xác minh **header → unauthenticated Authentication**; kiểm thử **`ReactiveAuthenticationManager`** bằng `StepVerifier` và fake reactive repository để xác minh **credential → authenticated Authentication hoặc error**; cuối cùng dùng **`WebTestClient + springSecurity()`** gửi credential thật qua filter chain để xác minh **200/401/403** và Reactor SecurityContext. **`Mono.empty()` không có nghĩa credential đúng**, **`mockUser()` không kiểm tra manager/converter**, và key sai phải phát authentication error chứ không được silently allow.