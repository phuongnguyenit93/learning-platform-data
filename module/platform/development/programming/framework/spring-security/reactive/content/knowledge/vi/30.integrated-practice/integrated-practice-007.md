# Triển khai API key tùy chỉnh với luân chuyển khóa và giới hạn quyền trong Spring Security Reactive

## 1. Bài toán và kết quả cần đạt

Một đối tác cần gọi API đơn hàng máy–máy trên ứng dụng **Spring WebFlux + Spring Security Reactive**. Mỗi đối tác có một hoặc nhiều API key; mỗi key chỉ được làm những việc được cấp phép. Hệ thống phải cho phép cấp key mới, chuyển client sang key mới trong một khoảng thời gian an toàn, rồi thu hồi key cũ **mà không làm key mới ngừng hoạt động**. Khi một key bị lộ, quản trị viên cần thu hồi nhanh, kiểm toán được ai sử dụng key nào và ngăn key đó vượt phạm vi truy cập.

Bài thực hành xây một luồng trọn vẹn:

```text
Client -- HTTPS: X-API-Key --> API gateway / reverse proxy
    -> Spring Security Reactive SecurityWebFilterChain
    -> AuthenticationWebFilter
    -> ServerAuthenticationConverter (lấy duy nhất 1 key)
    -> ReactiveAuthenticationManager
    -> Reactive key repository / verifier + hiệu lực + trạng thái
    -> Authentication(principal, key-specific authorities)
    -> authorizeExchange (path + HTTP method + scope)
    -> tenant/resource authorization trong nghiệp vụ
    -> WebFlux handler
```

Sau bài học, cần có khả năng:

1. Chọn **định dạng API key có public identifier và secret ngẫu nhiên**, chỉ hiển thị secret khi cấp.
2. Lưu **digest/verifier** thay vì lưu raw key; xác thực bằng so sánh digest an toàn và kiểm expiry/revocation.
3. Đưa kết quả xác thực vào **Reactor Context** qua cơ chế chuẩn của Spring Security, không tự tạo `ThreadLocal`.
4. Cấp **authority cho từng key**, kiểm HTTP method, endpoint và tenant; phân biệt 401 với 403.
5. Luân chuyển **hai khóa cùng tồn tại ngắn hạn**, chứng minh key mới hoạt động, sau đó thu hồi key cũ và xác minh 401.
6. Chạy test tự động, định nghĩa mô hình dữ liệu bền vững, tính tới nhiều replica, cache, audit và giới hạn tốc độ.

API key ở đây đại diện **ứng dụng gọi API**, không mặc nhiên đại diện một người dùng đang đăng nhập. Nếu hai dịch vụ có thể dùng OAuth2 Client Credentials, mTLS hoặc short-lived token theo hạ tầng sẵn có thì cân nhắc các giao thức được quản lý đó. Với yêu cầu tích hợp API key tùy chỉnh, vẫn phải thiết kế vòng đời và chính sách truy cập nghiêm túc.

## 2. Mô hình an ninh và phân quyền

Giả sử API có hai thao tác:

| HTTP | Đường dẫn | Authority cần có | Phạm vi dữ liệu |
| --- | --- | --- | --- |
| `GET` | `/api/orders/{tenantId}` | `KEY_orders:read` | Chỉ tenant gắn với key |
| `POST` | `/api/orders/{tenantId}` | `KEY_orders:write` | Chỉ tenant gắn với key |
| Phương thức/đường dẫn khác | `/api/**` | Không có rule cho phép | Từ chối mặc định |

Phân biệt ba lớp kiểm tra:

- **Authentication:** key có tồn tại, digest khớp, được kích hoạt, còn hạn, chưa bị thu hồi? Nếu sai, trả **401** và không tiết lộ key ID nào có tồn tại.
- **Authorization theo chức năng:** key có `orders:read` hay `orders:write`? Key hợp lệ nhưng thiếu authority thường trả **403**.
- **Authorization theo dữ liệu:** key được cấp cho tenant A không được truy cập tenant B, ngay cả khi có `orders:read`. Ở production, kiểm tenant/owner nên gắn vào query và transaction nghiệp vụ; kiểm URL đơn thuần không đủ chống IDOR/BOLA.

**Đặc quyền áp dụng cho từng khóa, không suy ra từ client.** Một client có key đọc và key ghi là hai khả năng riêng. Việc tạo key mới không được tự mở rộng scope; tác nhân cấp key chỉ được cấp phạm vi đã được phê duyệt.

Không gửi API key trong URL/query string (dễ vào access log, history, analytics, Referer), body dùng chung hoặc cookie browser. Dùng header chuyên biệt `X-API-Key` qua **HTTPS bắt buộc**, chặn/rewrite header đáng ngờ ở proxy. Không đưa long-lived key vào JavaScript frontend, mobile app phân phối rộng hoặc repository public; các môi trường đó không giữ được bí mật như một backend tin cậy.

## 3. Thiết kế định dạng và lưu trữ API key

### 3.1. Public identifier + secret entropy cao

Một key minh họa có dạng:

```text
ak1_<public-id-22-ký-tự>.<secret-43-ký-tự>
```

- `ak1_` là version/prefix để nhận dạng loại credential và hỗ trợ thay đổi định dạng về sau.
- `public-id` là 16 byte ngẫu nhiên mã Base64URL không dấu `=` (22 ký tự), được lưu để **lookup có chỉ mục**. Public ID không phải bí mật.
- `secret` là 32 byte từ `SecureRandom` mã Base64URL không dấu `=` (43 ký tự): **256 bit entropy**, tuyệt đối không cho người dùng tự chọn key ngắn/dễ đoán.
- Toàn bộ chuỗi `ak1_<id>.<secret>` là **bearer credential**: ai có key đều có thể gọi API trong phạm vi key trước khi hết hạn hoặc bị thu hồi.

Phân tách theo dấu `.` chỉ để tìm public ID; server vẫn tính `SHA-256` trên **toàn bộ chuỗi raw key** rồi so với digest 32 byte đang lưu. Dùng `MessageDigest.isEqual` để so sánh digest và tránh so sánh chuỗi secret bằng `String.equals`. SHA-256 phù hợp ở đây vì credential được tạo ngẫu nhiên với 256 bit entropy; **không áp dụng công thức hash nhanh này cho mật khẩu do người dùng chọn**. Mật khẩu cần thuật toán thích hợp như Argon2id/bcrypt/scrypt và chính sách tương ứng.

Không thể khôi phục raw key từ digest. Sau lần cấp đầu tiên, nếu người dùng làm mất key thì cấp key **mới**, không tạo chức năng “xem lại secret”. Với yêu cầu threat model cao hơn, có thể dùng HMAC-SHA-256 với secret pepper nằm trong KMS/vault độc lập; khi đó phải thiết kế version pepper và quy trình chuyển đổi digest, không nhúng pepper vào Git.

### 3.2. Record cần lưu

| Trường | Ý nghĩa |
| --- | --- |
| `key_id` | Public ID ngẫu nhiên; tra cứu chính xác, audit và revoke |
| `client_id` | Định danh integration/service sở hữu key |
| `tenant_id` | Định danh tenant mà key được phép sử dụng |
| `verifier_sha256` | Digest 32 byte của **raw key đầy đủ** |
| `permissions` | Tập scope duyệt cho key; ví dụ `orders:read` |
| `not_before` | Chưa cho phép sử dụng trước thời điểm này |
| `expires_at` | Từ thời điểm này trở đi key không hợp lệ |
| `revoked_at` | Có giá trị là key đã bị thu hồi |
| `created_at`, `last_used_at` | Vòng đời/quan sát an toàn |
| `created_by`, `rotation_group` | Audit cấp key/quan hệ key cũ và key mới |

**Bất biến:** một key đã bị revoke không được “bật lại”; không đổi digest của key cũ để quay vòng secret. Mỗi lần rotate phải tạo **key ID và secret mới**, quyền tối đa không được tăng ngoài sự phê duyệt. Có thể để hai key cùng hiệu lực trong khoảng chuyển tiếp được kiểm soát.

## 4. Ví dụ Java 17+ hoàn chỉnh cho tầng WebFlux

Ví dụ này cố ý dùng `ConcurrentHashMap` làm kho key trong bộ nhớ để sinh viên chạy test không cần database. Nó minh họa logic xác thực, per-key authority, revoke và rotate; **không dùng kho in-memory này trực tiếp cho production đa replica**, vì key sẽ mất khi restart và các pod không có cùng trạng thái.

Tệp `src/main/java/example/apikey/ApiKeySecurityConfig.java`:

```java
package example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ApiKeySecurityConfig {

    @Bean
    InMemoryApiKeyStore apiKeyStore() {
        return new InMemoryApiKeyStore(Clock.systemUTC());
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain apiKeys(ServerHttpSecurity http,
                                  InMemoryApiKeyStore store) {

        ServerAuthenticationEntryPoint unauthorized = (exchange, error) -> {
            exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
            exchange.getResponse().getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, "ApiKey realm=\"orders\"");
            return exchange.getResponse().setComplete();
        };

        // Chỉ xác thực credential chưa authenticated.
        ReactiveAuthenticationManager manager = candidate -> {
            if (!(candidate instanceof UsernamePasswordAuthenticationToken)
                    || candidate.isAuthenticated()) {
                return Mono.empty();
            }
            Object credentials = candidate.getCredentials();
            if (!(credentials instanceof String raw)) {
                return Mono.error(new BadCredentialsException("Invalid API key"));
            }

            return store.findActive(raw)
                    .map(record -> {
                        ApiClient principal = new ApiClient(
                                record.clientId(),
                                record.tenantId(),
                                record.keyId());
                        var authorities = record.permissions().stream()
                                .map(permission ->
                                        new SimpleGrantedAuthority("KEY_" + permission))
                                .toList();

                        // 3-arg constructor = Authentication đã xác thực.
                        return (Authentication) new UsernamePasswordAuthenticationToken(
                                principal, null, authorities);
                    })
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException("Invalid API key")));
        };

        AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);
        filter.setRequiresAuthenticationMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"));

        filter.setServerAuthenticationConverter(exchange -> {
            List<String> headers = exchange.getRequest()
                    .getHeaders().getOrEmpty("X-API-Key");

            if (headers.isEmpty()) {
                return Mono.empty(); // để authorization entry point trả 401
            }

            // Nhiều giá trị hoặc kích thước bất thường đều bị coi là invalid.
            String raw = headers.size() == 1
                    && headers.get(0).length() <= 256
                    ? headers.get(0) : "";

            return Mono.just((Authentication)
                    new UsernamePasswordAuthenticationToken("api-key", raw));
        });

        // Mỗi request phải cung cấp key lại; không lưu vào WebSession.
        filter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());
        filter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(unauthorized));

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .exceptionHandling(spec ->
                        spec.authenticationEntryPoint(unauthorized))
                // Chỉ áp dụng khi API thuần header-key, không dùng
                // cookie/session làm credential cho các route này.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .logout(ServerHttpSecurity.LogoutSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("KEY_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("KEY_orders:write")
                        .anyExchange().denyAll())
                .addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }

    // Demo an toàn: ngoài /api/** từ chối mọi request.
    // Trong app có UI/OAuth2, thay bằng chain riêng phù hợp.
    @Bean
    @Order(1)
    SecurityWebFilterChain denyUnknownRoutes(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex.anyExchange().denyAll())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    // Principal có nguồn gốc từ bản ghi key đã xác minh.
    public record ApiClient(
            String clientId, String tenantId, String keyId) implements Principal {
        @Override
        public String getName() {
            return clientId;
        }
    }

    // Không đưa raw key vào record auth hoặc log.
    public record IssuedKey(String keyId, String value, Instant expiresAt) {
        @Override
        public String toString() {
            return "IssuedKey(keyId=" + keyId
                    + ", value=[REDACTED], expiresAt=" + expiresAt + ")";
        }
    }

    public record KeyRow(
            String keyId,
            String clientId,
            String tenantId,
            byte[] verifier,
            Set<String> permissions,
            Instant notBefore,
            Instant expiresAt,
            Instant revokedAt) {

        public KeyRow {
            verifier = verifier.clone();
            permissions = Set.copyOf(permissions);
        }

        @Override
        public byte[] verifier() {
            return verifier.clone();
        }
    }

    public static final class InMemoryApiKeyStore {
        private static final Pattern FORMAT = Pattern.compile(
                "^ak1_([A-Za-z0-9_-]{22})\\.[A-Za-z0-9_-]{43}$");

        private static final Set<String> SUPPORTED_PERMISSIONS =
                Set.of("orders:read", "orders:write");

        private final SecureRandom random = new SecureRandom();
        private final ConcurrentMap<String, KeyRow> rows =
                new ConcurrentHashMap<>();
        private final Clock clock;

        public InMemoryApiKeyStore(Clock clock) {
            this.clock = clock;
        }

        // Chỉ gọi trong chức năng cấp key có xác thực + duyệt quyền riêng.
        // Kết quả value được trình bày đúng một lần cho người nhận.
        public IssuedKey issue(String clientId,
                               String tenantId,
                               Set<String> permissions,
                               Duration ttl) {

            if (clientId == null || clientId.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || permissions == null || permissions.isEmpty()
                    || !SUPPORTED_PERMISSIONS.containsAll(permissions)
                    || ttl == null || ttl.isNegative() || ttl.isZero()
                    || ttl.compareTo(Duration.ofDays(30)) > 0) {
                throw new IllegalArgumentException("Invalid key policy");
            }

            Instant now = clock.instant();
            Instant expires = now.plus(ttl);

            // putIfAbsent giữ tính duy nhất của ID khi cấp song song.
            while (true) {
                String id = urlSafeRandom(16);       // 22 ký tự
                String secret = urlSafeRandom(32);   // 43 ký tự
                String raw = "ak1_" + id + "." + secret;

                KeyRow row = new KeyRow(
                        id, clientId, tenantId,
                        sha256(raw), permissions, now, expires, null);
                if (rows.putIfAbsent(id, row) == null) {
                    return new IssuedKey(id, raw, expires);
                }
            }
        }

        public Mono<KeyRow> findActive(String raw) {
            return Mono.defer(() -> {
                if (raw == null) {
                    return Mono.empty();
                }

                Matcher matcher = FORMAT.matcher(raw);
                if (!matcher.matches()) {
                    return Mono.empty();
                }

                KeyRow row = rows.get(matcher.group(1));
                if (row == null) {
                    return Mono.empty();
                }

                Instant now = clock.instant();
                boolean active = row.revokedAt() == null
                        && !now.isBefore(row.notBefore())
                        && now.isBefore(row.expiresAt());

                if (!active || !MessageDigest.isEqual(
                        row.verifier(), sha256(raw))) {
                    return Mono.empty();
                }
                return Mono.just(row);
            });
        }

        // Thu hồi là chuyển đổi 1 chiều: không có "unrevoke".
        public void revoke(String keyId) {
            rows.computeIfPresent(keyId, (ignored, previous) -> {
                if (previous.revokedAt() != null) {
                    return previous;
                }
                return new KeyRow(
                        previous.keyId(),
                        previous.clientId(),
                        previous.tenantId(),
                        previous.verifier(),
                        previous.permissions(),
                        previous.notBefore(),
                        previous.expiresAt(),
                        clock.instant());
            });
        }

        // Chỉ phục vụ fixture test; không mở endpoint public để xóa store.
        public void clearForTest() {
            rows.clear();
        }

        private String urlSafeRandom(int byteCount) {
            byte[] bytes = new byte[byteCount];
            random.nextBytes(bytes);
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(bytes);
        }

        private static byte[] sha256(String raw) {
            try {
                return MessageDigest.getInstance("SHA-256")
                        .digest(raw.getBytes(StandardCharsets.US_ASCII));
            } catch (NoSuchAlgorithmException failure) {
                throw new IllegalStateException(
                        "Java runtime lacks SHA-256", failure);
            }
        }
    }

    @RestController
    public static class OrdersController {

        @GetMapping("/api/orders/{tenantId}")
        public Mono<String> read(@PathVariable String tenantId) {
            return replyForTenant(tenantId, "read");
        }

        @PostMapping("/api/orders/{tenantId}")
        public Mono<String> write(@PathVariable String tenantId) {
            return replyForTenant(tenantId, "write");
        }

        private Mono<String> replyForTenant(
                String requestedTenant, String action) {
            return ReactiveSecurityContextHolder.getContext()
                    .flatMap(context -> {
                        ApiClient actor = (ApiClient) context
                                .getAuthentication().getPrincipal();

                        // Chặn truy cập chéo tenant dù key có scope hợp lệ.
                        if (!actor.tenantId().equals(requestedTenant)) {
                            return Mono.error(new ResponseStatusException(
                                    HttpStatus.FORBIDDEN));
                        }

                        return Mono.just(action + ":" + requestedTenant
                                + ":" + actor.clientId());
                    });
        }
    }
}
```

### 4.1. Vì sao mẫu này phù hợp WebFlux?

- `AuthenticationWebFilter` là WebFilter chuẩn của **Spring Security Reactive**. `ServerAuthenticationConverter` rút credential khỏi `ServerWebExchange` thành một `Authentication` chưa xác thực.
- `ReactiveAuthenticationManager` tìm bản ghi key và chỉ tạo `UsernamePasswordAuthenticationToken` 3 tham số với principal + authorities **sau khi verifier và hiệu lực khớp**.
- `AuthenticationWebFilter` gắn authentication thành công vào Reactor Context cho phần pipeline tiếp theo; controller đọc qua `ReactiveSecurityContextHolder`. Không có `HttpServletRequest`, `OncePerRequestFilter` hoặc mutable `ThreadLocal`.
- `NoOpServerSecurityContextRepository` đảm bảo kết quả xác thực không được lưu sang request khác như một phiên. Mỗi request gửi lại key. Đây là một trade-off: kiểm key lặp lại mỗi request, nên cần kho/lookup có hiệu năng và cơ chế cache an toàn.
- `@Order(0)` và `securityMatcher("/api/**")` giới hạn chain API. Chain `@Order(1)` từ chối đường dẫn còn lại trong fixture, tránh vô tình để lộ endpoint mới. Trong ứng dụng có OAuth2/browser, thay chain fallback bằng chain đã được thiết kế cho phần web.
- `hasAuthority("KEY_orders:read")` kiểm đúng chuỗi authority sinh từ per-key permission. `hasRole("read")` là **khác** vì thông thường tìm tiền tố `ROLE_`; không trộn khái niệm API key scope với user role.
- Lỗi key thiếu/sai/expired/revoked trả 401 thông qua entry point/failure handler, với challenge `WWW-Authenticate: ApiKey realm="orders"`; không tiết lộ key có tồn tại hay vì sao key hỏng.
- Token chỉ giữ raw value trong `credentials` của request trước khi manager xác thực. `Authentication` đã xác thực có `credentials=null`; principal chỉ chứa ID/tenant/key ID, không chứa secret.

### 4.2. Hạn chế có chủ đích của fixture

Ví dụ này có đầy đủ flow test được nhưng **chưa phải sản phẩm production**:

1. `InMemoryApiKeyStore` dùng RAM một tiến trình, mất dữ liệu khi restart và không chia sẻ trạng thái khi scale nhiều pod. Production phải thay bằng repository Reactive bền vững có duy nhất nguồn chân lý, không dùng `Mono.fromCallable(... blocking JDBC ...)` trực tiếp trên event loop.
2. `issue()` là method Java dùng trong test; nó **không phải API quản trị**. Nếu làm chức năng cấp/revoke ngoài đời, đặt sau identity mạnh (admin/OAuth2/mTLS), xác thực người yêu cầu, duyệt scope, kiểm tenant, rate limit, audit và bảo vệ khỏi CSRF khi quản lý qua browser.
3. Thời hạn tối đa 30 ngày và tập permission là **giá trị minh họa của policy**, không phải mặc định bảo đảm của Spring Security. Thời hạn thực nên căn cứ rủi ro, thời gian triển khai và quản lý tự động.
4. Header `X-API-Key` là quy ước cho bài này; có thể xây scheme `Authorization: ApiKey ...`. Không bật đồng thời hai đường nạp credential trừ khi chính sách nhất quán và các proxy đều hiểu đúng.
5. Demo disable CSRF **chỉ ở chain header-only** không dùng cookie để cấp credential. Nếu API chấp nhận cookie/session hoặc được browser tự gửi credential, cần đánh giá CSRF và giữ bảo vệ tương ứng.
6. Nếu gateway/ingress ghi tất cả request headers, key vẫn có thể bị lộ trước khi vào ứng dụng. Cấu hình **redaction ở mọi hop**, TLS, giới hạn kích thước header và không truyền key sang service khác trừ khi được ủy quyền.

## 5. Gradle dependencies và ứng dụng chạy

Ghép đoạn này vào `build.gradle` của Spring Boot 3.x/Java 17+ đang dùng dependency management của Boot. Đây là **một đoạn build cấu hình**, không phải tệp Gradle độc lập:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Cấu hình `ApiKeySecurityConfig` là class Spring `@Configuration`. Khi đặt trong package được component scan của Spring Boot application, Bean store và filter chain sẽ được đăng ký. `OrdersController` trong ví dụ là nested class `@RestController`: fixture test phía dưới **import tường minh** class này để chắc chắn endpoint được đăng ký. Với ứng dụng thật, có thể tách controller thành tệp riêng trong package được scan.

Nếu muốn chạy ứng dụng trực tiếp, tạo entry point ở package cha, ví dụ:

```java
package example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(ApiKeySecurityConfig.OrdersController.class)
public class ApiKeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyApplication.class, args);
    }
}
```

Tệp `src/main/java/example/apikey/ApiKeyApplication.java` chỉ dùng cho chạy standalone. **Không tự động có API key hợp lệ sau boot** vì demo cố ý không mở endpoint tạo key. Phép thử JUnit bên dưới tự cấp key cho test. Trong production, bootstrap/management sẽ cấp key qua kênh bảo mật theo quy trình riêng, không in key ra stdout hoặc startup log.

## 6. Kiểm thử tự động WebTestClient: xác thực, phân quyền, tenant, rotate

Tệp `src/test/java/example/apikey/ApiKeySecurityTest.java`:

```java
package example.apikey;

import java.time.Duration;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ApiKeySecurityTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@Execution(ExecutionMode.SAME_THREAD)
class ApiKeySecurityTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    ApiKeySecurityConfig.InMemoryApiKeyStore store;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        store.clearForTest();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void missingMalformedAndDuplicateHeadersAre401() {
        client.get().uri("/api/orders/tenant-a")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", "guess")
                .exchange()
                .expectStatus().isUnauthorized();

        var issued = store.issue(
                "batch-importer", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", issued.value(), issued.value())
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readOnlyKeyCanReadButCannotWriteOrChangeTenant() {
        var readOnly = store.issue(
                "batch-importer", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", readOnly.value())
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("read:tenant-a:batch-importer");

        client.post().uri("/api/orders/tenant-a")
                .header("X-API-Key", readOnly.value())
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/orders/tenant-b")
                .header("X-API-Key", readOnly.value())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void writeGrantIsExplicitAndStillTenantBound() {
        var readWrite = store.issue(
                "batch-importer", "tenant-a",
                Set.of("orders:read", "orders:write"),
                Duration.ofHours(1));

        client.post().uri("/api/orders/tenant-a")
                .header("X-API-Key", readWrite.value())
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("write:tenant-a:batch-importer");

        client.post().uri("/api/orders/tenant-b")
                .header("X-API-Key", readWrite.value())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void rotationAllowsOverlapThenRevokesOnlyOldKey() {
        var oldKey = store.issue(
                "partner-1", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        var nextKey = store.issue(
                "partner-1", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", oldKey.value())
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", nextKey.value())
                .exchange()
                .expectStatus().isOk();

        store.revoke(oldKey.keyId());

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", oldKey.value())
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/orders/tenant-a")
                .header("X-API-Key", nextKey.value())
                .exchange()
                .expectStatus().isOk();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({
            ApiKeySecurityConfig.class,
            ApiKeySecurityConfig.OrdersController.class
    })
    static class TestApplication {}
}
```

**Kết quả mong đợi:**

| Trường hợp | Response |
| --- | --- |
| Không header, format sai, nhiều header | `401 Unauthorized` |
| Key chỉ đọc vào GET đúng tenant | `200 OK`, body `read:tenant-a:batch-importer` |
| Key chỉ đọc vào POST | `403 Forbidden` |
| Key hợp lệ nhưng truy cập tenant khác | `403 Forbidden` |
| Key có write grant, POST đúng tenant | `200 OK`, body `write:tenant-a:batch-importer` |
| Old + new trước revoke | Cả hai `200 OK` |
| Old sau revoke, new vẫn active | Old `401`; new `200` |

Các test dùng credential do `SecureRandom` sinh, không giả định raw key cố định và không in key. `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` kiểm WebFlux filter chain trong application context, nên test chạm **converter → manager → authorization → controller**. `@Execution(SAME_THREAD)` giúp tránh test case đồng thời tác động vào cùng in-memory store do dùng chung application context.

Chạy từ Gradle project có wrapper:

```bash
./gradlew test --tests 'example.apikey.ApiKeySecurityTest'
```

Trên Windows:

```powershell
.\gradlew.bat test --tests "example.apikey.ApiKeySecurityTest"
```

Lệnh `gradlew test` xây và chạy JUnit bằng Java 17+. Không có dòng stdout nghiệp vụ bắt buộc, vì fixture không in secret hay result ra console. Khi cả 4 phương thức `@Test` qua các assertion đã liệt kê, Gradle sẽ báo test task thành công. Code này được viết cho Spring Boot 3.x / Spring Security 6.x với Java 17+, có thể cần điều chỉnh nếu dự án dùng phiên bản/framework khác; không nên áp API Servlet vào WebFlux.

### 6.1. Kiểm tra thời hạn mà không dùng sleep dễ flaky

Trên kho `InMemoryApiKeyStore`, thời gian được đọc từ `Clock`. Khi viết test cấp độ store, có thể dùng `Clock.fixed(instant, ZoneOffset.UTC)` để kiểm ngay trước/sau `expiresAt`, hoặc truyền `Clock` có thể thay đổi được trong fixture test. Kịch bản phải xác nhận:

- `now < notBefore` → 401.
- `notBefore <= now < expiresAt`, digest đúng và chưa revoke → 200 nếu đủ scope.
- `now == expiresAt` hoặc `now > expiresAt` → 401.
- Revoke làm key bị từ chối ngay cả khi `expiresAt` còn xa.

Ưu tiên deterministic clock thay vì `Thread.sleep(1000)`. Đồng hồ system ở nhiều replica phải đồng bộ; khi backend cho phép skew, quy tắc về thời hạn phải được định nghĩa rõ.

## 7. Luân chuyển key có kiểm soát: các bước vận hành

**Không thể xoay key bằng cách thay verifier của cùng một ID** nếu đang muốn bảo đảm key cũ và key mới được quản trị độc lập. Tạo **bản ghi mới**, dùng quan hệ `rotation_group` hoặc `replaced_key_id` để biết chuỗi luân chuyển.

Ví dụ đối tác `partner-1`, tenant `tenant-a` có key `K1` chỉ được `orders:read`:

```text
T0: K1 active                       -> K1 200; chưa có K2
T1: tạo K2 mới, scope=orders:read   -> K1 200; K2 200
T2: phát K2 qua kênh an toàn        -> client deploy K2; vẫn cho K1 dùng ngắn hạn
T3: kiểm K2 trên traffic thật       -> log theo keyId; xác nhận K2 nhận đủ request
T4: thu hồi K1 (revoked_at=now)    -> K1 401; K2 200
T5: hết hạn K2 hoặc xoay vòng tiếp -> phải cấp K3 trước khi K2 hết hạn
```

Quy trình:

1. **Đề nghị và phê duyệt:** xác minh client/tenant, mục đích, danh sách endpoint, scope, expiry. Key mới chỉ giữ scope cần thiết; nếu client đòi quyền rộng hơn thì chạy quy trình xin quyền riêng.
2. **Cấp key mới:** tạo ID và secret mới độc lập bằng RNG, lưu hash/metadata trong transaction, giữ K1 đang hoạt động, gắn audit who/when/why và rotation group.
3. **Phát secret đúng một lần:** qua secret manager/vault hoặc kênh bảo mật cho khách hàng; không gửi plaintext vào email, issue tracker, CI logs hoặc trang dashboard hiển thị lại nhiều lần. Cấu hình client hỗ trợ chọn key mới mà không restart toàn hệ thống nếu có thể.
4. **Giai đoạn chồng lấn:** thử một yêu cầu GET/POST được phép bằng K2 và một yêu cầu bị cấm theo scope; quan sát `key_id`, trạng thái 401/403, tần suất sử dụng. K1 và K2 cùng tồn tại chỉ trong thời gian chuyển đổi đã phê duyệt.
5. **Thu hồi K1:** ghi `revoked_at` một chiều trong nguồn dữ liệu chính, làm mất hiệu lực cache theo key ID, xác nhận mọi replica đọc trạng thái mới.
6. **Kiểm chứng:** request mới bằng K1 phải 401, K2 vẫn 200 và vẫn không được vượt scope/tenant. Xác nhận không có client còn gửi K1, cập nhật inventory/audit. Hủy bản lưu secret cũ ở client và secret manager khi đã an toàn.
7. **Phản ứng khẩn cấp:** nếu có bằng chứng K1 bị lộ, revoke **ngay**, chấp nhận gián đoạn cần thiết thay vì chờ overlap. Xoay credential downstream liên quan và điều tra phạm vi sử dụng trái phép.

**Cửa sổ consistency:** revocation có hiệu lực theo thời điểm check trong request. Một request đã qua kiểm tra trước khi commit revoke có thể đang xử lý tiếp; muốn thu hồi có bảo đảm mạnh cho thao tác nhạy cảm phải kiểm lại trạng thái key ở bước commit nghiệp vụ hoặc thiết kế cơ chế fencing/transaction phù hợp. Nếu dùng cache TTL, việc revoke có thể bị chậm bằng TTL/cộng độ trễ invalidation. Vì vậy hệ thống phải ghi rõ **SLO thu hồi** (ví dụ có giới hạn đo được), không tuyên bố “thu hồi ngay” khi mọi pod còn cache cũ.

### 7.1. Phân biệt rotate, renew và cấp quyền

- **Rotate:** sinh key ID/secret mới, để quyền hiệu lực theo policy, thu hồi key cũ sau chuyển đổi.
- **Renew:** sửa thời hạn/phiên bản key chỉ nếu chính sách cho phép; với hệ thống rủi ro cao, cấp key mới an toàn hơn gia hạn vô hạn một secret cũ.
- **Nâng scope:** không phải rotate thông thường; cần quyết định cấp quyền độc lập, duyệt tenant/resource và ghi audit.
- **Revoke:** làm key hiện tại bị từ chối. Không dùng “unrevoke” để quay lại key từng bị rò rỉ.
- **Expire:** hệ thống tự từ chối khi đến `expires_at`, kể cả khi không có công việc định kỳ xóa bản ghi. Job dọn bản ghi chỉ để housekeeping, không quyết định hiệu lực bảo mật.

## 8. Đưa từ kho in-memory sang kho bền vững

Ví dụ PostgreSQL DDL để hiểu cấu trúc, chưa phải migration chung cho mọi loại database:

```sql
CREATE TABLE api_keys (
    key_id              varchar(22) PRIMARY KEY,
    client_id           text NOT NULL,
    tenant_id           text NOT NULL,
    verifier_sha256     bytea NOT NULL,
    not_before          timestamptz NOT NULL,
    expires_at          timestamptz NOT NULL,
    revoked_at          timestamptz NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          text NOT NULL,
    rotation_group      text NOT NULL,
    CONSTRAINT verifier_length CHECK (octet_length(verifier_sha256) = 32),
    CONSTRAINT valid_times CHECK (expires_at > not_before)
);

CREATE TABLE api_key_permissions (
    key_id      varchar(22) NOT NULL
                REFERENCES api_keys(key_id) ON DELETE CASCADE,
    permission  text NOT NULL,
    PRIMARY KEY (key_id, permission)
);
```

Cấu trúc permission dạng bảng con cho phép audit và unique permission, nhưng phải đảm bảo **transaction** khi cấp key: insert parent + permissions cùng commit. Giữ constraints bảo đảm không có row hết hạn trước activation. Khi revoke:

```sql
UPDATE api_keys
SET revoked_at = CURRENT_TIMESTAMP
WHERE key_id = :key_id AND revoked_at IS NULL;
```

Đây là **SQL tham số** minh họa; `:key_id` chỉ là placeholder do client DB binding, không ghép giá trị từ HTTP vào SQL string. Để lưu `last_used_at`, dùng event/batch riêng có giới hạn, tránh mỗi request tạo transaction ghi nóng trên một row. Định danh client và tenant phải lấy từ DB sau xác thực, không lấy từ header do client tự khai.

Repository production nên có:

- `findByKeyId` trả `Mono<KeyRow>` bằng R2DBC/Reactive driver; tải permissions bằng truy vấn phù hợp và tránh N+1 không kiểm soát.
- Issuance/rotation/revoke phải chạy trong transaction với phân quyền operator, quy tắc quota, unique key ID và audit.
- Cần chiến lược cache: cache metadata theo key ID ở TTL nhỏ hoặc kiểm DB mỗi request, invalidation chủ động khi thu hồi, đo giới hạn trễ nhất và thử failover.
- Khi kho xác thực outage, fail **closed**: không xác thực thành công key chưa được kiểm. Nên phân biệt **lỗi hạ tầng** với invalid credential trong metrics/log; không nhất thiết ép mọi lỗi hạ tầng thành 401.
- Nhiều instance không dựa vào process memory; dữ liệu chủ sở hữu và scope phải nhất quán. Thời hạn UTC và đồng hồ đồng bộ.
- Mỗi service chỉ đọc verifier/metadata cần cho authentication; quyền **tạo/revoke** thuộc management service có danh tính và chính sách riêng.
- Database encryption at rest, backup, RBAC, audit log, secret-manager cho các thành phần nhạy cảm. Digest không phải nguyên liệu để dựng lại raw key.

**Không dùng** `Mono.fromCallable(() -> jdbcRepository.findById(...))` trực tiếp trên event-loop rồi coi là “reactive”. Nếu buộc tích hợp nguồn blocking, phải cách ly sang scheduler phù hợp và hiểu giới hạn thread pool, hoặc ưu tiên chuyển sang truy cập truly reactive.

## 9. Test matrix mở rộng trước production

| Trường hợp | Điều kiện kích thích | Kết quả đúng |
| --- | --- | --- |
| Không gửi header | GET route được bảo vệ | 401, challenge phù hợp |
| Header trùng/format sai | Hai `X-API-Key`, chuỗi không đúng regex | 401, không lộ tồn tại của key ID |
| ID không tồn tại | Public ID hợp định dạng nhưng không lưu | 401, không leak chi tiết |
| Secret sai | ID tồn tại, secret thay 1 byte | 401 |
| `notBefore` tương lai | Đúng digest nhưng chưa tới hạn | 401 |
| Key hết hạn | `now >= expiresAt` | 401 |
| Key bị revoke | `revoked_at != null` | 401 |
| Key read GET đúng tenant | Có `orders:read` | 200, chỉ dữ liệu tenant của key |
| Key read POST | Không có `orders:write` | 403, không có side effect |
| Key write POST đúng tenant | Có `orders:write` | 200 khi nghiệp vụ thành công |
| Key read tenant khác | GET tenant B với key tenant A | 403 hoặc deny theo chính sách, không lộ dữ liệu |
| Không có route trong allowlist | `PATCH /api/orders/...` | 403/deny theo chính sách |
| K1 và K2 overlap | Cả hai active, scope không đổi | Cả hai request hợp lệ |
| K1 sau revoke | Revoke K1, K2 còn active | K1 401, K2 200 |
| Nhiều pod | Revoke qua pod A, gọi pod B | Pod B không còn nhận K1 sau SLO revocation |
| Scope bị tăng trái phép | Gọi issuance với scope vượt privilege operator | 403/deny tại management boundary |
| Header key qua proxy | TLS termination, ingress/gateway | Key được forward đúng một lần và bị redacted trong log |
| Key bị lộ ở log | Kiểm log APM, trace, reverse proxy, error body | Không có raw key; chỉ audit key ID đã qua policy |
| Kho verifier outage | DB unreachable | Không fail-open; metrics/alert riêng |
| Races | Revoke cùng lúc nhiều request | Quy tắc in-flight, consistency, thu hồi mới được đo |
| Rate limit | Nhiều lần đoán key ID/secret | Giới hạn tốc độ, không chặn hàng loạt tenant khác tùy tiện |

Không nhất thiết mọi trường hợp lỗi đều có cùng HTTP status khi hạ tầng thất bại; chỉ bảo đảm **không chấp nhận credential không được xác minh**. Lỗi 401/403 có thể được gateway chuẩn hóa theo hợp đồng API; mọi lớp phải giữ ngữ nghĩa và không lộ nguyên nhân nhạy cảm.

### 9.1. Test quyền theo tenant phải có dữ liệu thật

Fixture `OrdersController` trả chuỗi để thấy rõ điều kiện bảo vệ. Khi chuyển sang ứng dụng thật, dùng query có ràng buộc bắt buộc:

```sql
SELECT id, tenant_id, amount
FROM orders
WHERE id = :order_id AND tenant_id = :authenticated_tenant_id;
```

`authenticated_tenant_id` lấy từ `ApiClient` đã kiểm chứng ở Reactor Context, **không** lấy trực tiếp từ route param hoặc JSON body. Với thao tác UPDATE/DELETE, thêm điều kiện tenant tương tự vào `WHERE` và xác minh số row bị ảnh hưởng. Một key được cấp quyền `orders:read` không thể vì biết ID của đối tác khác mà truy cập dữ liệu đó.

### 9.2. Tải, brute force và độ trễ

Tạo quá nhiều key mà không quota làm metadata phình to; brute force vào public ID có thể gây nhiều truy vấn DB dù khả năng đoán secret 256 bit rất thấp. Thiết lập rate limiting theo **client identity, key ID hợp lệ, IP/cidr và edge policy** có kiểm soát; dùng backoff/alert khi 401 tăng bất thường, nhưng đừng lock toàn bộ tenant chỉ vì kẻ tấn công biết public ID. Cache một kết quả auth đã được cấp quyền phải tính tới revoke/expiry; không cache Authentication ở nơi dùng chung giữa request hoặc làm key A nhận scope của key B.

Các metric hữu ích: số key active theo client, key sắp hết hạn, số lần rotate, thời gian từ revoke đến deny ở mọi replica, tỷ lệ 401/403 theo route, độ trễ lookup verifier và 5xx từ key store. Chỉ log `key_id` đã lọc, client ID, request ID, outcome, thời gian; nếu quy định an ninh không cho log trực tiếp key ID, dùng fingerprint hoặc mã quy chiếu an toàn. Không log raw key trong query/body/header hoặc stack traces.

## 10. Những lỗi thiết kế thường gặp

### 10.1. Chỉ dùng `WebFilter` tự viết rồi đặt principal vào biến toàn cục

Sai: `static Authentication currentUser` hoặc `ThreadLocal` được đặt trong filter rồi controller đọc. Reactor có thể chuyển thread hoặc xử lý nhiều subscription xen kẽ; cách này có thể gây **rò rỉ danh tính và quyền**. Đúng: `AuthenticationWebFilter` + `ReactiveAuthenticationManager` + `ReactiveSecurityContextHolder` theo subscription. Không gọi `subscribe()` thủ công trong auth service; trả về publisher để framework subscribe.

### 10.2. Hash sai hoặc secret quá ngắn

Sai: key do người dùng nhập, 8 ký tự; lưu `SHA-256` rồi coi là an toàn. Digest nhanh của secret entropy thấp bị brute-force offline sau DB leak. Đúng: key do `SecureRandom` sinh ≥256 bit entropy, giới hạn format, lưu verifier; không dùng plain `String.equals` để so digest. Đổi threat model khi có yêu cầu kháng DB breach đặc biệt; cân nhắc server-side pepper/KMS có version và quản trị riêng.

### 10.3. Thay nội dung key cũ thay vì tạo key mới

Sai: update `verifier_sha256` trên row K1 và ngay lập tức yêu cầu khách hàng đổi secret, khiến request dùng K1 cũ bị 401 trước khi client chuyển. Đúng: tạo K2, giữ overlap được kiểm soát, confirm K2, revoke K1. Với key bị lộ, ưu tiên revoke khẩn cấp thay vì chờ rollout.

### 10.4. Cấp quyền ở mức client nhưng không ở mức key

Sai: mọi key thuộc client có toàn bộ quyền client; key tạo cho báo cáo đọc cũng có quyền ghi/xóa. Đúng: quyền lấy trực tiếp từ record đã xác minh của **key đang gọi**, kiểm method/path + tenant/resource. Cấp key mới không vượt quyền được duyệt.

### 10.5. Nhầm “stateless” là không cần kho trạng thái

API key validation thường cần tra cứu metadata để kiểm expiry, scope và revoke. Một API stateless ở tầng **phiên HTTP** vẫn có state cho vòng đời credential trong kho dữ liệu. Chỉ hash raw key mà không lưu trạng thái revoke sẽ không hỗ trợ thu hồi linh hoạt trước thời hạn.

### 10.6. Dùng cùng chain browser login và API key

Nếu custom API key filter áp mọi request, nó có thể phá OAuth2 login, CORS preflight, health endpoint hoặc session auth. Đúng: xác định `securityMatcher` và `@Order`, dùng chain riêng cho API machine-to-machine; cân nhắc xử lý CORS preflight trước auth khi có client browser chính thức. Với browser sử dụng session, không tự disable CSRF chỉ để “tránh 403”.

### 10.7. Thu hồi xong nhưng cache và pod khác vẫn chấp nhận

Sai: xóa key trên một instance RAM và tuyên bố revoked. Đúng: central store + transaction + invalidation + test qua mọi pod; định lượng thời gian revoke thực tế. Nếu cần bảo đảm rất mạnh cho thao tác bất khả đảo ngược, xác minh lại phiên bản/thu hồi ở bước nghiệp vụ quan trọng.

### 10.8. Expose raw key qua cấp phát và observability

Sai: API quản trị trả raw key nhiều lần, record `toString()` mặc định chứa secret, exception in `X-API-Key`, reverse proxy dump mọi header, backup giữ plaintext. Đúng: hiển thị một lần, dùng response `Cache-Control: no-store` ở kênh cấp, TLS, secret manager, log redaction, chỉ lưu digest, và audit lifecycle.

## 11. Quy trình xử lý sự cố 401/403

```text
Client gửi X-API-Key nhưng nhận lỗi
 |
 +-- Request có đi qua proxy/ingress tới app không?
 |     +-- Không: kiểm HTTPS, proxy auth, header forwarding, route
 |     +-- Có:
 |         |
 |         +-- Chain /api/** được chọn? filter converter đọc 1 header?
 |         |      +-- Không: securityMatcher, @Order, route/prefix
 |         |      +-- Có:
 |         |          |
 |         |          +-- Format và key ID lookup hợp lệ?
 |         |          |      +-- Không: 401
 |         |          |      +-- Có:
 |         |          |          |
 |         |          |          +-- Digest, notBefore, expiresAt, revokedAt?
 |         |          |          |      +-- Fail: 401
 |         |          |          |      +-- Pass:
 |         |          |          |          |
 |         |          |          |          +-- Per-key authority đúng?
 |         |          |          |          |      +-- Không: 403
 |         |          |          |          |      +-- Có: kiểm tenant/owner trong nghiệp vụ
 |
 +-- Chỉ pod khác lỗi: kiểm shared store/cache/clock
 +-- Lỗi khi rotate: kiểm K2 đã rollout, K1 revoked_at, TTL và invalidation
 +-- Key được chấp nhận nhưng lộ dữ liệu tenant khác: kiểm DB predicate ngay
```

Ưu tiên đo **trạng thái xác thực và quyền** từng request bằng request ID, không in raw secret. Phân biệt lỗi thiếu/sai credential (401), key hợp lệ thiếu quyền (403), lỗi phụ thuộc như DB timeout (5xx hoặc trạng thái policy quy định), và lỗi không tìm được route (404). Khi nhận phản ánh “revoke không tác dụng”, thử cùng key trên từng replica ngay sau khi đã commit revoke, đo cache invalidation và kiểm có một hệ thống khác đang xác thực key ngoài kho được quản lý hay không.

## 12. Checklist nghiệm thu

- [ ] Có định dạng versioned `ak1_<id>.<secret>`, public ID ngẫu nhiên và secret 256 bit từ CSPRNG.
- [ ] Key chỉ hiển thị khi phát hành; chỉ lưu digest/verifier, metadata và per-key scopes; raw key không vào log/URL.
- [ ] `AuthenticationWebFilter` chạy trong chain WebFlux đúng route; converter xử lý thiếu/trùng/sai header.
- [ ] `ReactiveAuthenticationManager` xác minh digest an toàn, not-before, expiry và revoked state trước khi tạo Authentication.
- [ ] Stateless API chain không ghi auth vào WebSession; controller nhận đúng principal qua Reactor Context.
- [ ] GET/POST có các authority riêng; deny by default; tenant/object-level check có hiệu lực ở truy vấn dữ liệu thực.
- [ ] Key read-only không có write, key tenant A không đọc/ghi tenant B.
- [ ] Quy trình rotate tạo K2 mới, xác minh overlap, revoke K1, test K1 401 và K2 200; emergency revoke có đường xử lý riêng.
- [ ] Kho production dùng repository Reactive bền vững, transaction, quyền cấp/revoke riêng và shared state giữa các replica.
- [ ] Expiry/revoke kiểm theo thời điểm với test deterministic, có revocation SLO và kiểm cache/replica.
- [ ] TLS, gateway/ingress, rate limiting, audit và log redaction được cấu hình; không đưa key xuống browser.
- [ ] Test unit/integration WebTestClient cho missing/malformed/wrong/valid/insufficient permission/tenant/rotation; kiểm lỗi hệ thống fail closed.

## Tài liệu tham khảo

- [Spring Security — AuthenticationWebFilter Javadoc (Reactive)](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html).
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — SecurityWebFiltersOrder và ServerHttpSecurity](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.html).
- [Spring Security — NoOpServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html).
- [Spring Security — Testing WebFlux Security với WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html).
- [Oracle Java — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) và [MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html).
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet).
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet).
