# Provider hoặc AuthenticationManager riêng để kiểm tra API key trong Spring Security

## 1. Mục tiêu và bài toán

Một API nội bộ hoặc hệ thống tích hợp máy với máy thường nhận **API key** trong HTTP header để nhận diện client. Không có form đăng nhập, không có browser session và cũng không nhất thiết có người dùng cuối. Ứng dụng Spring Security phải chuyển một chuỗi bí mật do client cung cấp thành **Authentication đã xác minh**, sau đó quyết định client được gọi API nào.

Bài này giải thích cách tổ chức một **AuthenticationProvider tùy biến** hoặc **AuthenticationManager riêng**, đặt sau một filter lấy API key và trước lớp phân quyền Spring Security. Trọng tâm gồm:

1. Phân biệt công việc của `Filter`, `AuthenticationManager`, `AuthenticationProvider`, `Authentication` và `SecurityContext`.
2. Thiết kế API key như một bearer credential có định danh chủ sở hữu, trạng thái, quyền, hạn dùng và vòng đời thu hồi.
3. Chọn đúng lúc dùng `AuthenticationProvider` bên trong `ProviderManager` và lúc dùng `AuthenticationManager` trực tiếp.
4. Viết ví dụ **Java 17+ / Spring Boot Servlet** runnable, từ HTTP request đến status **401 Unauthorized** hoặc **403 Forbidden**.
5. Kiểm thử trường hợp thiếu key, key sai, key hợp lệ và key đúng nhưng không có quyền.
6. Nhận biết những lỗi nguy hiểm: hard-code key, so sánh chuỗi thiếu kiểm soát, lộ key qua log, dùng session sai, cấp quyền từ header không tin cậy và không có quy trình rotation.

**API key không phải mật khẩu người dùng, ID Token OIDC, JWT hay một cơ chế ủy quyền chuẩn.** Nó là một secret mà server phải kiểm chứng; nếu ai sở hữu secret đó thì thông thường người đó có thể hành động như client được gán với key. Vì vậy cần TLS, quản lý bí mật và giới hạn quyền như bất kỳ bearer credential nào.

## 2. Kiến trúc từ header đến Authentication

```text
HTTP client
    |
    | GET /api/whoami
    | X-API-Key: <secret>
    v
Spring Security FilterChainProxy / SecurityFilterChain
    |
    | ApiKeyAuthenticationFilter (custom OncePerRequestFilter)
    |   - đọc header đúng một giá trị
    |   - kiểm tra hình thức / kích thước input
    |   - tạo ApiKeyAuthenticationToken (chưa xác thực)
    |
    | AuthenticationManager.authenticate(token)
    |   |
    |   +-- ProviderManager
    |         |
    |         +-- ApiKeyAuthenticationProvider
    |                - nhận đúng token type
    |                - tra cứu/so khớp hash API key
    |                - kiểm tra revoked/expired/active
    |                - nạp clientId, authorities
    |                - trả Authentication đã xác thực
    |
    | SecurityContextHolder
    |   - gắn Authentication đã xác thực vào request
    |
    | AuthorizationFilter
    |   - authenticated(), hasAuthority("API_ADMIN"), ...
    v
Controller / Service -> kết quả
```

Một request có ba kết quả chính:

| Tình huống | Kết quả | Lý do |
| --- | --- | --- |
| Thiếu key, sai key hoặc key đã thu hồi | **401** | Chưa có Authentication hợp lệ |
| Key đúng nhưng client không đủ authority | **403** | Đã xác thực, bị từ chối quyền |
| Key đúng, còn hiệu lực và có authority phù hợp | **2xx** nếu xử lý thành công | Được xác thực và được cho phép |

Trong thực tế status có thể được thay đổi bởi `AuthenticationEntryPoint`/`AccessDeniedHandler` hoặc policy của tổ chức. Ví dụ ở dưới cấu hình đường xử lý 401 rõ ràng.

### 2.1. Vì sao không gọi trực tiếp controller để kiểm tra?

Nếu mọi controller đều viết:

```java
if (!"secret".equals(request.getHeader("X-API-Key"))) {
    // trả lỗi
}
```

thì rất dễ quên bảo vệ một endpoint, lộ secret trong source, khó audit và khó thống nhất xử lý authorization. Đưa kiểm chứng vào authentication filter + provider giúp mọi request trong phạm vi `/api/**` đi qua cùng một hợp đồng.

### 2.2. Mỗi thành phần nhận trách nhiệm nào?

| Thành phần | Chức năng | Không nên làm |
| --- | --- | --- |
| `OncePerRequestFilter` | Trích xuất header, tạo authentication request, gọi manager, xử lý lỗi | Truy vấn quyền trong mọi controller hoặc tự đặt `authenticated=true` khi chưa kiểm chứng |
| `AuthenticationManager` | API điều phối một lần authentication; thường là `ProviderManager` | Tự bị nhầm thành kho lưu key |
| `AuthenticationProvider` | Kiểm chứng một loại `Authentication` cụ thể và cấp principal/authorities | Tin quyền do client tự khai trong header |
| `Authentication` | Biểu diễn yêu cầu trước xác thực hoặc kết quả đã xác thực | Giữ nguyên raw API key trong principal sau xác thực |
| `SecurityContextHolder` | Giữ context của request hiện tại ở Servlet stack | Là kho lưu trạng thái đăng nhập giữa các request stateless |
| `SecurityContextRepository` | Quy định cách load/save context giữa requests khi cần | Bắt buộc phải ghi session cho mọi API |
| `AuthorizationFilter` | Đánh giá các rule như `hasAuthority(...)` | Kiểm chứng bí mật API key thay provider |

**Quy tắc thiết kế:** filter đưa **credential chưa tin cậy** vào manager; provider trả **principal và quyền đã được server xác định**; filter mới đặt kết quả vào `SecurityContextHolder`. Spring Security có thể tiếp tục xử lý authorization như với các authentication mechanism khác.

## 3. Contract của AuthenticationProvider và ProviderManager

`AuthenticationProvider` trong Spring Security có hai phương thức:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

Đây là chữ ký rút gọn từ API, **không phải một lớp Java độc lập**.

- `supports(...)` trả `true` khi provider có thể xử lý loại token đưa vào, ví dụ `ApiKeyAuthenticationToken.class`.
- `authenticate(...)` nhận token chứa **raw key chưa xác thực**; nếu key hợp lệ, tạo một Authentication **mới** với principal/authorities đáng tin cậy.
- Khi key không hợp lệ, ném `BadCredentialsException` hoặc một `AuthenticationException` phù hợp. Không biến key sai thành anonymous-but-successful user.
- Khi provider không có khả năng xử lý loại Authentication, có thể trả `null` để manager xét provider khác. Trong ví dụ, provider chỉ phục vụ một token type.
- `ProviderManager` chuyển tiếp authentication request qua danh sách provider, xử lý kết quả/lỗi và có cơ chế xóa credentials khỏi kết quả authentication theo chính sách.

Vì vậy đoạn code kiến trúc có dạng:

```java
AuthenticationManager manager =
    new ProviderManager(apiKeyAuthenticationProvider);

Authentication result = manager.authenticate(
    new ApiKeyAuthenticationToken(rawKey));
```

Đây là **trích đoạn minh họa**; lớp `ApiKeyAuthenticationToken` và provider được định nghĩa đầy đủ ở phần 6.

**Không trộn lẫn `supports()` với authorization.** `supports(ApiKeyAuthenticationToken.class) == true` chỉ nói provider **biết kiểm tra loại token đó**, không chứng minh key hợp lệ và cũng không cho phép endpoint admin.

### Provider hay AuthenticationManager riêng?

| Lựa chọn | Phù hợp khi | Nhận xét |
| --- | --- | --- |
| **Custom `AuthenticationProvider` + `ProviderManager`** | Muốn tận dụng cơ chế chuẩn, có thể kết hợp với loại authentication khác | Dễ tách provider test, `supports()` rõ ràng, mở rộng được |
| **Custom `AuthenticationManager`** | Một security chain thật sự chỉ có logic kiểm chứng riêng, ví dụ gọi dịch vụ key verification tập trung | Đơn giản nếu quy trình nhỏ; tự chịu trách nhiệm hợp đồng authentication, lỗi và vòng đời secret |
| **`AuthenticationManagerResolver<HttpServletRequest>`** | Cần chọn manager khác theo host/tenant/issuer/request được xác minh, ví dụ nhiều vùng auth độc lập | Phải tránh chọn manager từ header do client điều khiển mà không xác minh trust boundary |

Không cần vừa viết một manager tùy biến vừa bọc nó bằng provider chỉ để đổi tên lớp. **Một manager dùng một provider rõ ràng là đủ** cho ví dụ này. Nếu API dùng nhiều cách xác thực, tách `SecurityFilterChain`/matcher hoặc cấu hình provider/manager theo phạm vi, tránh cơ chế yếu trở thành đường vòng vào endpoint cần bảo vệ cao.

## 4. Thiết kế đúng API key trước khi viết code

Một API key an toàn thường có **hai mặt**:

- **Giá trị bí mật:** chuỗi ngẫu nhiên có entropy cao được client giữ kín, dùng trong `X-API-Key` hoặc một header xác thực được quy định rõ. Bất kỳ ai có secret đều có thể dùng nó.
- **Bản ghi server-side:** ID của key, ID client/service owner, digest/credential verifier, authorities, thời điểm cấp/hết hạn, trạng thái revoked, audit metadata, policy rotation và quota/rate limit.

Bản ghi thực tế có thể trông như sau:

```text
key_id          = ak_2026_001               # public lookup identifier
client_id       = billing-exporter           # service principal
secret_digest   = SHA256(secret)             # demo: secret ngẫu nhiên 256-bit
authorities     = [API_READ]
created_at      = 2026-11-01T00:00:00Z
expires_at      = 2027-02-01T00:00:00Z
revoked_at      = null
enabled         = true
```

Trong production, nên chọn secret ngẫu nhiên ít nhất khoảng 128-bit entropy (ví dụ 32 byte ngẫu nhiên = 256 bit), hiển thị plaintext **một lần khi cấp**, rồi chỉ lưu verifier. Với secret do máy tạo có entropy cao, SHA-256/HMAC-SHA-256 có thể phù hợp; **nếu bí mật do người dùng chọn, có entropy thấp**, phải dùng thiết kế bảo vệ như password KDF (Argon2id/bcrypt/scrypt) hoặc tránh biến nó thành API key. HMAC với server-side pepper bổ sung một lớp bảo vệ cho dữ liệu hash khi DB bị lộ.

Nên có **key prefix / key ID** để chọn bản ghi kiểm chứng, ví dụ `ak_live_<public-id>.<random-secret>`; lưu public ID và digest của secret riêng. Ví dụ dưới dùng scan hai digest trong memory để minh họa provider, **không phải thiết kế tra cứu thích hợp cho hàng triệu key**.

### Những ràng buộc quan trọng

1. **Không lưu plaintext** trong database, code, cấu hình được commit hoặc log.
2. **Không lấy authority từ header** như `X-Role: ADMIN` do client tự gửi. Authority phải lấy từ bản ghi key server-side.
3. **Không coi key = danh tính người dùng cuối.** Thường nên xác thực thành một service/client principal. Nếu cần “on behalf of user”, dùng OAuth/OIDC hoặc cơ chế delegation phù hợp.
4. **Không dựa chỉ vào key prefix.** Prefix là thông tin tra cứu/hiển thị, không phải bằng chứng xác thực.
5. **Mỗi client có nhiều key khi rotation:** cho phép tạo key mới, chuyển đổi trong khoảng overlap có kiểm soát, rồi revoke key cũ.
6. **Thu hồi và hết hạn:** kiểm tra mỗi request hoặc cache có TTL ngắn/chiến lược invalidation phù hợp.
7. **Scope/authority ít nhất cần thiết:** ví dụ client đọc báo cáo nhận `API_READ`, client vận hành riêng nhận thêm `API_ADMIN`.
8. **TLS bắt buộc** trên mọi hop; key không được đưa vào query string vì URL thường bị ghi log, cache và referrer.
9. **Chống lạm dụng:** rate limiting, quota, audit theo `client_id/key_id`, phát hiện sử dụng bất thường và cảnh báo rotation.
10. **Cấu hình fail-closed** khi key store không truy cập được. Đừng “tạm cho qua” request do dependency bị lỗi.

## 5. Luồng xử lý và SecurityContext theo từng request

Ví dụ request:

```http
GET /api/whoami HTTP/1.1
Host: api.example.com
X-API-Key: <random-secret>
```

Trong `doFilterInternal(...)`:

1. Xác nhận path thuộc phạm vi API key, ví dụ `/api/**`.
2. Đọc header. Nếu thiếu, trùng hoặc sai format → trả 401 qua `AuthenticationEntryPoint`, không chuyển request cho controller.
3. Tạo `ApiKeyAuthenticationToken` chưa xác thực; `getCredentials()` chứa raw key và `isAuthenticated() == false`.
4. `AuthenticationManager.authenticate(...)` gọi provider phù hợp. Provider so digest với server-side verifier, kiểm tra trạng thái và trả Authentication có `principal="report-reader"` và `API_READ`.
5. Filter tạo `SecurityContext` mới và đặt kết quả vào `SecurityContextHolder` **cho request hiện tại**.
6. Gọi `filterChain.doFilter(...)` để Spring tiếp tục authorization và controller.
7. Luôn clear context trong `finally` để không làm rò authentication sang request khác khi server tái sử dụng thread.

**Tại sao filter phải tự xử lý lỗi `AuthenticationException`?** Một custom authentication filter được đặt **trước `ExceptionTranslationFilter`** trong SecurityFilterChain. Exception ném trước filter đó thường không thể trông đợi được `ExceptionTranslationFilter` phía sau bắt hộ. Vì vậy ví dụ bắt lỗi từ `manager.authenticate(...)` và gọi `AuthenticationEntryPoint` trực tiếp, còn authorization error phía sau do Spring Security xử lý.

**Stateful hay stateless?** API key thường xác thực **mỗi request**, không cần cookie phiên. Trong mẫu dưới dùng `SessionCreationPolicy.STATELESS` cùng `NullSecurityContextRepository`: không lưu `Authentication` sang HTTP session. Một lần xác thực thành công không cho phép request sau thiếu key.

## 6. Ví dụ Spring Boot Java 17+ chạy được

Mẫu này minh họa **Spring Boot 3.5.16, Spring Security 6.x, Servlet/Spring MVC**. Boot 3.5.16 là một phiên bản cố định để tái lập bài thực hành; nhánh 3.5 đã kết thúc hỗ trợ OSS, do đó hệ thống mới nên chọn nhánh đang được hỗ trợ và điều chỉnh API cho đúng phiên bản.

Điểm thiết kế:

- Hai API key **64 ký tự hex** được tạo từ 32 byte ngẫu nhiên, cấp qua biến môi trường (không commit secret).
- Provider băm key bằng SHA-256 và so digest, không lưu plaintext như một constant trong source.
- `report-reader` có `API_READ`; `ops-admin` có `API_READ` và `API_ADMIN`.
- Filter bảo vệ mọi request thuộc `/api/**`; `/public` không cần key.
- Để ví dụ tập trung vào authentication, chỉ có GET endpoint. Nếu sau này thêm POST/PUT/DELETE, phải thiết kế CSRF theo mô hình sử dụng cookie hay header-only, không tắt toàn bộ bảo vệ một cách vô điều kiện.

Cấu trúc:

```text
api-key-demo/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/demo/apikey/ApiKeyDemoApplication.java
└── src/test/java/demo/apikey/ApiKeyDemoApplicationTests.java
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>api-key-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Chỉ cần Spring Security core/web qua starter. **Không có starter API key chính thức bắt buộc** cho custom provider này; các lớp `AuthenticationProvider`, `ProviderManager`, `AbstractAuthenticationToken` và `OncePerRequestFilter` có sẵn trong các dependency trên.

### 6.2. `application.yml`

```yaml
app:
  api-key:
    user: "${APP_API_KEY_USER}"
    admin: "${APP_API_KEY_ADMIN}"

server:
  port: 8080
```

Ứng dụng sẽ không khởi động nếu thiếu biến môi trường cần thiết. Bản production có thể dùng secret manager, database hoặc KMS thay cho hai biến demo; không để secret trong repository.

### 6.3. Một file Java đầy đủ, gồm Filter, Provider và Manager

Tạo `src/main/java/demo/apikey/ApiKeyDemoApplication.java`:

```java
package demo.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Enumeration;
import java.util.List;
import java.util.Collection;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}

@Configuration
class ApiKeySecurityConfig {

    @Bean
    ApiKeyProvider apiKeyProvider(
            @Value("${app.api-key.user}") String userKey,
            @Value("${app.api-key.admin}") String adminKey) {
        return new ApiKeyProvider(userKey, adminKey);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, ApiKeyProvider provider) throws Exception {

        // Manager RIÊNG cho key-based authentication.
        AuthenticationManager manager = new ProviderManager(provider);
        AuthenticationEntryPoint entryPoint =
            new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);

        // Không khai báo filter này là @Bean: Boot có thể đăng ký
        // nó ngoài Spring Security và chạy hai lần.
        ApiKeyFilter apiKeyFilter = new ApiKeyFilter(manager, entryPoint);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasAuthority("API_ADMIN")
                .requestMatchers("/api/**").hasAnyAuthority(
                    "API_READ", "API_ADMIN")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository()))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                apiKeyFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}

/**
 * Token trước xác thực: principal=null, credentials=raw key.
 * Token sau xác thực: principal=service ID, credentials=null,
 * authorities được cấp bởi server.
 */
final class ApiKeyToken extends AbstractAuthenticationToken {

    private final String principal;
    private String key;

    ApiKeyToken(String presentedKey) {
        super(null);
        this.principal = null;
        this.key = presentedKey;
        super.setAuthenticated(false);
    }

    private ApiKeyToken(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = principal;
        this.key = null;
        // Chỉ factory nội bộ sau khi provider đã kiểm chứng.
        super.setAuthenticated(true);
    }

    static ApiKeyToken authenticated(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyToken(principal, authorities);
    }

    @Override
    public Object getCredentials() {
        return key;
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        this.key = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                "Unverified API key cannot be marked authenticated");
        }
        super.setAuthenticated(false);
    }
}

/**
 * Demo: hai verifier lưu trong bộ nhớ.
 * Production: tra bản ghi key theo keyId; kiểm tra expiry/revocation.
 */
final class ApiKeyProvider implements AuthenticationProvider {

    private static final Pattern HEX_256 =
        Pattern.compile("[0-9a-f]{64}");

    private final List<ClientRecord> clients;

    ApiKeyProvider(String readerSecret, String adminSecret) {
        byte[] readerHash = digest(validSecret(readerSecret));
        byte[] adminHash = digest(validSecret(adminSecret));
        if (MessageDigest.isEqual(readerHash, adminHash)) {
            throw new IllegalArgumentException(
                "Reader and admin API keys must be different");
        }
        clients = List.of(
            new ClientRecord(
                "report-reader",
                readerHash,
                List.of(new SimpleGrantedAuthority("API_READ"))),
            new ClientRecord(
                "ops-admin",
                adminHash,
                List.of(
                    new SimpleGrantedAuthority("API_READ"),
                    new SimpleGrantedAuthority("API_ADMIN")))
        );
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        if (!(request instanceof ApiKeyToken token)
                || token.isAuthenticated()) {
            throw new BadCredentialsException("Invalid API key");
        }
        String raw = (String) token.getCredentials();
        if (raw == null || !HEX_256.matcher(raw).matches()) {
            throw new BadCredentialsException("Invalid API key");
        }

        byte[] presentedDigest = digest(raw);
        ClientRecord match = null;

        // Không short-circuit khi so nhiều verifier trong demo nhỏ.
        for (ClientRecord record : clients) {
            if (MessageDigest.isEqual(
                    presentedDigest, record.secretDigest())) {
                match = record;
            }
        }
        if (match == null) {
            throw new BadCredentialsException("Invalid API key");
        }
        return ApiKeyToken.authenticated(
            match.clientId(), match.authorities());
    }

    @Override
    public boolean supports(Class<?> type) {
        return ApiKeyToken.class.isAssignableFrom(type);
    }

    private static String validSecret(String raw) {
        if (raw == null || !HEX_256.matcher(raw).matches()) {
            throw new IllegalArgumentException(
                "API key must be 64 lowercase hexadecimal characters");
        }
        return raw;
    }

    private static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private record ClientRecord(
        String clientId,
        byte[] secretDigest,
        List<GrantedAuthority> authorities) {}
}

final class ApiKeyFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-API-Key";
    private static final Pattern HEX_256 =
        Pattern.compile("[0-9a-f]{64}");

    private final AuthenticationManager manager;
    private final AuthenticationEntryPoint entryPoint;

    ApiKeyFilter(
            AuthenticationManager manager,
            AuthenticationEntryPoint entryPoint) {
        this.manager = manager;
        this.entryPoint = entryPoint;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return !(path.equals("/api") || path.startsWith("/api/"));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders(HEADER);
        if (!values.hasMoreElements()) {
            reject(request, response);
            return;
        }

        String key = values.nextElement();
        if (values.hasMoreElements() ||
                !HEX_256.matcher(key).matches()) {
            // Chặn header trùng hoặc malformed; không log raw key.
            reject(request, response);
            return;
        }

        Authentication result;
        try {
            result = manager.authenticate(new ApiKeyToken(key));
        } catch (AuthenticationException failure) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response, failure);
            return;
        }

        try {
            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(result);
            SecurityContextHolder.setContext(context);
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private void reject(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        SecurityContextHolder.clearContext();
        entryPoint.commence(
            request, response, new BadCredentialsException("Invalid API key"));
    }
}

@RestController
class ApiKeyController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/whoami")
    String whoami(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin-ok";
    }
}
```

**Đọc code theo đường dữ liệu:**

- `ApiKeyFilter` là lớp tiếp xúc HTTP. Nó chỉ nhận đúng một header có định dạng 64 ký tự hex, không echo hoặc log giá trị.
- `ApiKeyToken` bảo vệ ranh giới giữa token **chưa** và **đã** xác thực; caller không thể đơn giản gọi `setAuthenticated(true)` để bypass provider.
- `ApiKeyProvider` so SHA-256 digest của key có entropy cao với verifier đã được dựng khi startup. Nó trả principal và authority **từ server**, không từ client.
- `new ProviderManager(provider)` là AuthenticationManager riêng cho bộ lọc API key. Nếu provider ném `AuthenticationException`, filter gọi `AuthenticationEntryPoint` trả HTTP 401.
- `SecurityContext` được thiết lập cho request và xóa trong `finally`; không lưu authentication vào HTTP session giữa requests.
- `hasAuthority("API_ADMIN")` chạy **sau** xác thực; key của `report-reader` thành công ở `/api/whoami` nhưng bị từ chối `/api/admin`.
- `ApiKeyFilter` được tạo bên trong method cấu hình security, không trở thành Spring `Filter` bean được Boot tự đăng ký lần hai.

**Giới hạn của ví dụ:** đây là store in-memory chỉ có hai key và không hỗ trợ revoke, expiry, audit, rotation. Thiết kế ở production phải mở rộng provider để tra DB/secret service và kiểm tra trạng thái key. Không coi `SHA-256` đơn thuần là lời giải an toàn cho mọi secret có entropy thấp.

## 7. Chạy thử bằng terminal

Trên máy có OpenSSL, tạo hai secret **ngẫu nhiên riêng biệt** (cú pháp Bash):

```bash
export APP_API_KEY_USER="$(openssl rand -hex 32)"
export APP_API_KEY_ADMIN="$(openssl rand -hex 32)"

mvn spring-boot:run
```

Ứng dụng sử dụng biến môi trường cho hai key. Đừng in key lên terminal dùng chung, commit file shell chứa chúng hoặc chụp ảnh màn hình secret. Với hệ thống thật, cấp key bằng workflow quản lý secret.

Ở terminal **có cùng biến môi trường** (hoặc nhập các biến bằng kênh bí mật phù hợp):

```bash
# Public endpoint
curl -s http://localhost:8080/public

# Reader được phép vào /api/whoami
curl -s -H "X-API-Key: $APP_API_KEY_USER" \
  http://localhost:8080/api/whoami

# Admin được phép vào /api/admin
curl -s -H "X-API-Key: $APP_API_KEY_ADMIN" \
  http://localhost:8080/api/admin

# Thiếu key -> 401
curl -i http://localhost:8080/api/whoami

# Reader không đủ quyền admin -> 403
curl -i -H "X-API-Key: $APP_API_KEY_USER" \
  http://localhost:8080/api/admin

# Key sai -> 401
curl -i -H "X-API-Key: invalid" \
  http://localhost:8080/api/whoami
```

Body của ba request đầu, theo thứ tự:

```text
public
report-reader
admin-ok
```

Ba lệnh sau nhận **401**, **403**, **401** tương ứng. Tùy cách Spring Boot dựng lỗi, header và body có thể khác; mã HTTP là hành vi cần kiểm tra. `curl -s` không chèn newline, nên nếu gọi liên tiếp output có thể nằm cùng dòng.

**Lưu ý cú pháp:** Bash export ở một terminal không tự chuyển sang terminal khác. Khi chạy `curl` ở cửa sổ mới, phải có cùng secret bằng cơ chế truyền bí mật an toàn; nếu không, `$APP_API_KEY_USER` rỗng và request sẽ bị từ chối. Không ghi secret vào lịch sử shell dưới dạng lệnh trực tiếp với giá trị cố định.

## 8. Kiểm thử với MockMvc không cần key thật

Tạo `src/test/java/demo/apikey/ApiKeyDemoApplicationTests.java`:

```java
package demo.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyDemoApplicationTests {

    // Chỉ là secret GIẢ dùng trong test, không dùng để bảo vệ dịch vụ.
    private static final String READER_KEY = "a".repeat(64);
    private static final String ADMIN_KEY = "b".repeat(64);

    @DynamicPropertySource
    static void testKeys(DynamicPropertyRegistry registry) {
        registry.add("app.api-key.user", () -> READER_KEY);
        registry.add("app.api-key.admin", () -> ADMIN_KEY);
    }

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoKey() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void readerKeyBecomesServerOwnedPrincipal() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", READER_KEY))
            .andExpect(status().isOk())
            .andExpect(content().string("report-reader"));
    }

    @Test
    void adminAuthorityIsCheckedAfterAuthentication()
            throws Exception {
        mvc.perform(get("/api/admin")
                .header("X-API-Key", READER_KEY))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .header("X-API-Key", ADMIN_KEY))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));
    }

    @Test
    void missingInvalidAndDuplicateKeysAreRejected()
            throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/whoami")
                .header("X-API-Key", "bad"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/whoami")
                .header("X-API-Key", READER_KEY, ADMIN_KEY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aNewRequestMustPresentItsOwnKey() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", READER_KEY))
            .andExpect(status().isOk());

        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
mvn test
```

Kết quả mong đợi là **5 test pass** nếu dependencies được tải thành công. Các test kiểm tra trọn đường Spring MVC → SecurityFilterChain → filter → manager → provider → authorization → controller với hai secret thử nghiệm.

**Không nhầm mức độ kiểm thử:** MockMvc chỉ xác nhận logic ứng dụng. Nó chưa chứng minh reverse proxy đã bảo vệ header, traffic có TLS, API key được phát hành ngẫu nhiên trong sản phẩm thật hay cơ chế revoke/rotation trong cơ sở dữ liệu hoạt động. Các yêu cầu này cần integration/security tests tương ứng.

## 9. Nếu muốn tự viết AuthenticationManager thay Provider

Custom `AuthenticationManager` là hợp lệ khi không muốn chuỗi provider, ví dụ toàn bộ authentication sẽ do một service xác minh key riêng xử lý.

Chữ ký trung tâm:

```java
Authentication authenticate(Authentication request)
    throws AuthenticationException;
```

Ví dụ ý tưởng:

```java
AuthenticationManager manager = request -> {
    if (!(request instanceof ApiKeyToken token)) {
        throw new ProviderNotFoundException(
            "Unsupported authentication type");
    }
    return apiKeyVerificationService.authenticate(
        (String) token.getCredentials());
};
```

Đây là **trích đoạn kiến trúc**, không phải chương trình độc lập. `apiKeyVerificationService` là abstraction tự viết, phải **xác minh thực sự** secret, trạng thái, hết hạn, quyền và trả một `Authentication` an toàn; `ProviderNotFoundException` cần import từ `org.springframework.security.authentication`. Không được implement `authenticate(...)` bằng cách đơn giản gọi `ApiKeyToken.authenticated("admin", ...)` cho mọi raw input.

**Khi nào ưu tiên Provider?** Khi codebase đã dùng `ProviderManager`, có nhiều loại credentials, cần `supports()` rõ ràng, hoặc muốn thay đổi implementation key store mà không thay filter. **Khi nào manager trực tiếp hợp lý?** Một cơ chế độc lập có kiểm chứng từ hệ thống riêng và các bước fail-closed đã được kiểm thử đầy đủ.

Đối với nhiều tenant, có thể cấu hình nhiều `SecurityFilterChain` hoặc `AuthenticationManagerResolver<HttpServletRequest>`. Cần chọn manager bằng nguồn tin cậy (hostname/tenant đã ràng buộc ở gateway, client registration…), **không tự động tin header `X-Tenant: admin` để chọn manager yếu hơn**.

## 10. Nâng cấp provider cho production

### 10.1. Mô hình lưu key

Một bảng dữ liệu minh họa:

```sql
CREATE TABLE api_client (
    id UUID PRIMARY KEY,
    client_name VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE api_key (
    id UUID PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES api_client(id),
    public_key_id VARCHAR(80) NOT NULL UNIQUE,
    secret_digest VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE api_client_authority (
    client_id UUID NOT NULL REFERENCES api_client(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (client_id, authority)
);
```

Đây là schema tham khảo, chưa có generator/key issuance service. Chọn kiểu timestamp, index, audit và dữ liệu tenant phù hợp database thực. Không dùng `last_used_at` update đồng bộ trên từng request tải lớn nếu gây lock contention; có thể gom theo batch/event.

Quy trình provider trong production:

1. Parse một header duy nhất, giới hạn độ dài và ký tự được phép.
2. Trích xuất **public key ID** (không phải raw secret) nếu cấu trúc key có prefix/ID.
3. Tra đúng bản ghi ở trusted store; nếu không tồn tại, từ chối.
4. Tính digest/HMAC của phần secret, so với verifier theo hàm so sánh thời gian khó suy ra giá trị secret; không log giá trị.
5. Kiểm tra `enabled`, `revoked_at`, `expires_at` và trạng thái parent client.
6. Nạp authorities/tenant constraints từ server-side policy.
7. Trả Authentication chứa một `clientId/keyId` ổn định, **không chứa secret**.
8. Cập nhật audit/metrics riêng, không làm chậm quá nhiều đường auth; lỗi store phải fail-closed.

Key có thể có nhiều quyền nhưng mọi service không nên cùng dùng một key chung. Ràng buộc audit theo owner cụ thể giúp thu hồi đúng client khi bị lộ, không làm gián đoạn toàn hệ thống.

### 10.2. Xoay khóa, thu hồi, expiry

Ví dụ quy trình rotation không ngắt dịch vụ:

```text
T0: Key A active -> client dùng A
T1: Cấp Key B mới, cùng client và phạm vi quyền cần thiết
T2: Client triển khai B, xác nhận lưu lượng chuyển sang B
T3: Revoke A; A lập tức 401 theo chính sách kiểm tra trạng thái
T4: Dọn hash/audit cũ sau thời hạn lưu giữ
```

Nếu provider cache trạng thái key, `revoke A` có thể **không có hiệu lực ngay** nếu cache chưa được invalidated. Thiết kế TTL/cache version hoặc event invalidation đúng yêu cầu an ninh. Không dùng session application vô hạn để “ghi nhớ” API key đã xác thực.

### 10.3. Chính sách key theo client và tenant

- Đánh giá authorities ở cả API path và resource-level/tenant-level. Có `API_READ` không đồng nghĩa đọc dữ liệu của mọi tenant.
- Dùng nguyên tắc least privilege; tách key sandbox và production, tách key read-only và key write/admin.
- Hạn chế IP/ASN/network khi thực tế phù hợp nhưng **IP allowlist không thay thế key secret**, đặc biệt sau reverse proxy.
- Với service-to-service quan trọng, xem xét **mTLS, OAuth2 Client Credentials hoặc signed requests** nếu cần hạn chế replay/credential forwarding hơn API key bearer đơn thuần.
- Nếu dùng gateway kiểm tra API key và chuyển client identity cho Spring, backend cần trust boundary rõ (mTLS/network isolation/header stripping) và có thể dùng pre-auth thay vì kiểm tra lại raw key.

### 10.4. HTTP, proxy và log

Không nhận API key trong query string hoặc URL path. Header `X-API-Key` vẫn có thể bị lộ nếu gateway/access log ghi đầy đủ headers: cấu hình **redaction** ở proxy, app logs, APM, tracing, error reporting và support tooling.

Không trả `"unknown key ID"` hay `"expired key for customer X"` cho client chưa xác thực nếu làm lộ dữ liệu nhạy cảm. Câu trả lời ngoài nên thống nhất 401; server lưu nguyên nhân chi tiết trong log có kiểm soát mà không ghi secret.

API key bearer có thể bị replay nếu lộ. Dùng TLS đầy đủ, giới hạn nơi có thể sử dụng, thời hạn ngắn tương ứng rủi ro và quota. Đối với kịch bản cần chống replay mỗi request, bổ sung chữ ký request (timestamp/nonce) hoặc một giao thức được chuẩn hóa và kiểm chứng đúng, không chỉ thêm một timestamp chưa được ký.

## 11. Lưu ý CSRF, session và phân tách các SecurityFilterChain

Trong ví dụ, các endpoint API chỉ dùng GET và header key; CSRF mặc định không ngăn việc đọc. Khi thêm các HTTP method thay đổi dữ liệu, cần xác định rõ client là **browser dùng cookie** hay **máy dùng API key ở header**.

Nếu toàn bộ một chain chỉ nhận API key bằng header do client lập trình chủ động gửi và **không dùng cookie/session browser làm authentication**, có thể cân nhắc cấu hình bỏ CSRF cho riêng các matcher API đó. Nếu cùng ứng dụng còn form login, cookie hoặc SPA dùng session, giữ CSRF cho đường browser; không dùng `csrf.disable()` toàn cục chỉ để sửa lỗi 403 chưa phân tích.

Một ứng dụng có thể có:

- Chain `/api/**`: stateless, xác thực bằng API key hoặc bearer token theo chính sách.
- Chain `/web/**`: session/cookie, OIDC login, CSRF áp dụng.
- Các endpoint health/public: chỉ định rõ phạm vi và quyền truy cập.

Nếu có nhiều chain, dùng `@Order` và `securityMatcher(...)` đúng thứ tự; mỗi request thường được xử lý bởi **SecurityFilterChain khớp đầu tiên**, tránh chain `permitAll` vô tình che chain bảo vệ API. Khi thiết kế API key ở upstream gateway, không coi `X-Forwarded-*` hoặc `X-Client-Id` từ mạng không tin cậy là kết quả authentication.

## 12. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Request không có key trả 200 | Filter không nằm trong chain, matcher bỏ sót path hoặc rule `permitAll` quá rộng | Kiểm tra SecurityFilterChain, URL mapping và filter invocation |
| Key nào cũng được chấp nhận | Provider chưa thực sự kiểm chứng, hoặc tự tạo `authenticated=true` từ raw header | Xác minh digest trước khi tạo token authenticated |
| Key sai gây 500 thay vì 401 | Filter để `AuthenticationException` thoát ra trước `ExceptionTranslationFilter` | Bắt exception tại authentication filter và gọi `AuthenticationEntryPoint` |
| Key đúng nhưng 403 | Authority không đúng, thiếu role, hoặc endpoint yêu cầu chính sách khác | Kiểm tra `hasAuthority(...)` và server-side mapping |
| Key sai vẫn giữ user từ request trước | Không clear `SecurityContextHolder` trong `finally`, thread bị tái sử dụng | Tạo context riêng và clear mọi đường xử lý |
| Có 401 dù key hợp lệ | Key format sai, key khác do env chưa truyền tới process, hash khác, key revoked/expired | Kiểm tra cấu hình secret store và metadata mà không in raw key |
| Hai header key được chấp nhận không rõ cái nào | Proxy/container ghép hoặc chọn header đầu/cuối khác nhau | Chặn duplicate/malformed header, chuẩn hóa tại gateway |
| API key hết hạn nhưng vẫn gọi được | Cache cũ, session/sticky auth hoặc revoked state không được kiểm tra | Rà soát cache invalidation, expiry và stateless auth |
| Hết quyền admin nhưng request vẫn qua | Role lấy từ key header hay cache authorities chưa làm mới | Chỉ lấy từ server-side trusted policy, có cơ chế cập nhật |
| Filter chạy hai lần | Filter là Spring `@Bean` auto-register và còn được thêm vào SecurityFilterChain | Chỉ tạo filter cục bộ trong chain hoặc disable auto-registration có chủ đích |
| Header key xuất hiện trong access log | Reverse proxy/APM ghi toàn bộ request headers | Redact key trước log/export và xoay ngay key đã lộ |
| `ProviderNotFoundException` | Manager không đăng ký provider phù hợp token type; `supports()` trả false | Kiểm tra manager, token class và registration |
| Thêm POST bị 403 dù key hợp lệ | CSRF rule hoặc authorization rule còn áp dụng | Phân biệt CSRF và thiếu authorities; chỉnh đúng chain/matcher |
| MockMvc pass nhưng production 401 | Secret store không đồng bộ, gateway bỏ header, traffic qua chain khác | Kiểm thử qua ingress/TLS và kiểm tra version/config triển khai |

Trình tự chẩn đoán: request vào đúng chain chưa → filter có đọc key duy nhất không → manager dùng provider nào → provider xác minh đúng key store và trạng thái không → Authentication có principal/authorities nào → authorization rule nào áp dụng. Chỉ log key ID/client ID, trace ID và mã lỗi tổng quát; **không log raw secret hoặc digest có thể tái sử dụng để tấn công**.

## 13. Bài tập và câu hỏi tự kiểm tra

1. **Vì sao filter không nên tự đặt principal "admin" khi thấy header `X-Role: ADMIN`?** Vì header đó là dữ liệu do client cung cấp; authorities phải do provider/server xác định sau khi xác minh credential.
2. **Khi key sai, provider nên trả `null` hay ném lỗi?** Với token type mà provider thực sự xử lý, key sai nên ném `AuthenticationException`; `null` dành cho trường hợp provider không thể quyết định và để provider phù hợp khác thử.
3. **Khác nhau giữa 401 và 403?** 401: chưa có authentication hợp lệ; 403: authentication hợp lệ nhưng thiếu quyền cho tài nguyên.
4. **Provider đã kiểm chứng key có cần đưa raw key vào Authentication đã xác thực không?** Không; chỉ giữ principal/authorities/metadata an toàn. Raw secret cần xóa khỏi context càng sớm càng tốt.
5. **Tại sao chọn `ProviderManager(provider)`?** Để tách điều phối authentication với logic kiểm chứng cụ thể, dùng đúng contract chuẩn của Spring Security.
6. **Khi nào viết manager trực tiếp?** Khi một chain độc lập có logic xác thực chuyên biệt, không cần chuỗi providers, nhưng vẫn tuân thủ hợp đồng `authenticate(...)` và fail-closed.
7. **Có thể dùng `API_ADMIN` như một OAuth2 scope mặc định không?** Đây là authority tùy biến của ứng dụng; OAuth scopes thường có convention khác. Không tự đồng nhất hai hệ quyền.
8. **Nếu cache key đã thu hồi còn 15 phút, hành vi thu hồi có tức thời không?** Không. Phải thiết kế TTL/invalidation theo SLA an ninh.
9. **API key có thay thế mTLS/OAuth2 cho mọi hệ thống không?** Không. API key bearer đơn giản nhưng không gắn cryptographically với request; lựa chọn phụ thuộc threat model.
10. **Tại sao một test dùng `@WithMockUser` chưa đủ?** Nó mô phỏng Authentication đã tồn tại; không kiểm tra filter/provider thực sự xác minh raw key.

**Bài tập thực hành mở rộng:** thêm bảng `api_key` với `expires_at` và `revoked_at`; test rằng key bị thu hồi hoặc quá hạn luôn nhận 401, key còn hiệu lực nhưng thiếu `API_ADMIN` nhận 403, và rotation B cho phép chuyển đổi không gián đoạn. Tách keyId khỏi secret, lưu digest/HMAC và dùng dữ liệu thử nghiệm; không commit key thật.

## 14. Tài liệu chính thức

- Spring Security – Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Servlet Architecture / Adding a custom filter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- API `AuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- API `ProviderManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- API `AbstractAuthenticationToken`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html
- API `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security – SecurityContextHolder and SecurityContext: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html#servlet-authentication-securitycontextholder
- OWASP – REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- Spring Boot 3.5.16 release note: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
