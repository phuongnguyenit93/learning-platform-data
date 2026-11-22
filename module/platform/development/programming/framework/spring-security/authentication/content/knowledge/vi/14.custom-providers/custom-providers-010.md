# Kiểm thử provider độc lập trước khi ghép vào chuỗi HTTP

## Mục tiêu bài học

Trong Spring Security, `AuthenticationProvider` là nơi xác minh credential và quyết định có tạo một `Authentication` đáng tin cậy hay không. Khi viết provider riêng cho API key, OTP, tài khoản nội bộ hoặc một cơ chế đặc thù, cần **kiểm thử provider trực tiếp trước khi đưa nó vào SecurityFilterChain**. Việc cô lập này giúp phân biệt lỗi xử lý credential với lỗi filter, HTTP status, session, CSRF hay URL matcher.

Sau bài này bạn sẽ biết cách:

1. Tách rõ nhiệm vụ của **AuthenticationProvider**, **ProviderManager** và các thành phần **Servlet HTTP**.
2. Thiết kế bộ test JUnit 5 cho cả thành công lẫn các nhánh từ chối, với `Authentication` đầu vào **chưa được xác thực**.
3. Dùng fake store trong bộ nhớ để chạy logic provider thật mà không cần web server hay database.
4. Kiểm tra `supports()`, `authenticate()`, trạng thái account/key, principal, authorities, ngoại lệ và bảo vệ credential.
5. Kiểm thử `ProviderManager` tối thiểu, rồi lập kế hoạch thử bằng `MockMvc` sau khi tích hợp chuỗi HTTP.

Ví dụ sử dụng **Java 17+**, **Spring Security 6.5.x**, **JUnit Jupiter 5** và Gradle. Các file trong mục 4–5 chạy như một project Gradle Java bình thường; không dùng `@SpringBootTest` hoặc servlet container trong bộ test provider.

## 1. Xác định ranh giới cần kiểm thử

Một request HTTP thường đi theo chuỗi:

~~~text
HTTP request
  |
  +-- SecurityFilterChain
        |
        +-- Filter đọc credential từ header/body/cookie
        +-- Tạo Authentication token chưa trusted
        |
        v
     AuthenticationManager (ProviderManager)
        |
        +-- supports(token.getClass()) -> chọn provider
        |
        v
     Custom AuthenticationProvider
        |
        +-- validate input và đọc dữ liệu do server kiểm soát
        +-- kiểm tra credential và trạng thái tài khoản/key
        +-- xác định principal và GrantedAuthority từ server
        |
        +-- thất bại -> AuthenticationException
        +-- thành công -> Authentication đã xác thực
        |
        v
     Filter đặt kết quả vào SecurityContext
        |
        +-- AuthenticationEntryPoint/FailureHandler cho lỗi
        +-- AuthorizationFilter xét quyền
        +-- Controller xử lý request
~~~

**Unit test provider** chỉ cần token đầu vào, provider thật và kho dữ liệu kiểm thử. Khi test này pass, bạn biết các nhánh xác thực cơ bản hoạt động theo hợp đồng. Nó chưa chứng minh HTTP filter đọc đúng header hoặc client được trả 401/403. Đó là phần kiểm thử riêng sau khi tích hợp.

### Ba cấp test cần phân biệt

| Cấp | Đối tượng thật cần chạy | Phát hiện lỗi gì? | Cần HTTP? |
| --- | --- | --- | --- |
| **Provider unit test** | Token, `AuthenticationProvider`, logic xác minh và ánh xạ quyền | Credential đúng/sai, account disabled, quyền vượt mức, secret không được xóa | Không |
| **Manager test** | `ProviderManager` và provider thật | `supports` sai, không có provider, điều phối provider không đúng | Không |
| **HTTP integration / MockMvc** | Security filter chain, authentication mechanism, entry point, authorization | Header không được đọc, sai thứ tự filter, 401/403, session/context/CSRF | Có tầng Servlet, có thể không mở cổng thật |

Chẳng hạn, nếu HTTP request với key đúng nhận 401, nguyên nhân có thể là filter không được cài, header sai tên, `SecurityFilterChain` không khớp URL, provider từ chối hoặc entry point sai. Một unit test provider độc lập giúp loại trừ hoặc xác nhận **một** nguyên nhân quan trọng.

## 2. Hợp đồng của AuthenticationProvider

Giao diện chính:

~~~java
Authentication authenticate(Authentication authentication)
    throws AuthenticationException;

boolean supports(Class<?> authenticationType);
~~~

Trong `org.springframework.security.authentication.AuthenticationProvider`:

- **supports(Class<?>)** trả lời provider **có thể xem xét** loại token đó hay không. Nó không kiểm tra password, API key hoặc quyền.
- **authenticate(Authentication)** trả về `Authentication` đã xác thực khi thành công, **ném AuthenticationException** khi thông tin xác thực sai hoặc trạng thái account không cho phép.
- Provider có thể **trả null** nếu không thể xử lý/không quyết định được cho token để manager thử provider khác theo hợp đồng. Không nên tùy tiện trả null khi credential thực sự đã được xác định là sai.
- **ProviderManager** chọn provider thích hợp. Nếu không provider nào hỗ trợ được token, manager có thể ném `ProviderNotFoundException`.

Ví dụ:

| Input vào provider | Kết quả cần test |
| --- | --- |
| Token đúng loại, key hợp lệ và còn hiệu lực | `authenticated=true`, principal và authorities đến từ server |
| Token đúng loại, secret sai | `BadCredentialsException` |
| Token đúng loại, client ID không tồn tại | `BadCredentialsException` với thông điệp an toàn |
| Token đúng loại, key disabled | `DisabledException` hoặc exception theo chính sách |
| Token sai định dạng | Từ chối có kiểm soát; không rò lỗi parse hay secret |
| Token khác loại | `supports=false`, provider không nhận xử lý |
| Input token tự gọi `setAuthenticated(true)` | Không được nâng thành trusted |
| Result thành công | Credential nhạy cảm không bị giữ lại nếu không cần |

**Principal** là danh tính đã được chứng thực; **authorities** là quyền hiệu lực lấy từ nguồn do server kiểm soát. Chuỗi trong header hoặc JSON do client cung cấp **chưa chứng minh** user/role tương ứng. Vì vậy test cần khẳng định quyền không được lấy từ đầu vào tự khai.

### Tại sao không dùng HTTP status trong provider test?

`AuthenticationProvider` không nhận `HttpServletResponse`. Nó nên báo thành công hoặc `AuthenticationException`; filter, `AuthenticationEntryPoint` và `AccessDeniedHandler` mới quyết định phản hồi HTTP. Test “sai key trả 401” thuộc tầng HTTP. Test “sai key ném BadCredentialsException” thuộc tầng provider.

## 3. Thiết kế ma trận kiểm thử trước khi code

| Test | Điều kiện | Assertion chính |
| --- | --- | --- |
| U1 | Key hợp lệ, enabled=true | Result khác input; true; principal đúng; chỉ scope server cấp |
| U2 | Secret sai | `BadCredentialsException`; không có result trusted |
| U3 | ID không tồn tại | `BadCredentialsException`; không tiết lộ ID/secret |
| U4 | Key disabled | Bị từ chối kể cả secret đúng |
| U5 | Null/rỗng/sai dấu phân cách/quá dài | Từ chối an toàn và dọn credential |
| U6 | Token không được hỗ trợ | supports=false; authenticate không xử lý |
| U7 | Input gọi `setAuthenticated(true)` | Ném lỗi; trạng thái vẫn false |
| U8 | Key đúng | Result không giữ raw secret; input được dọn |
| U9 | Provider đã chạy | Không tự đặt Authentication vào `SecurityContextHolder` |
| M1 | ProviderManager chứa provider | Gọi provider và nhận trusted result |
| M2 | Manager chỉ có provider API key nhưng nhận token password | `ProviderNotFoundException` |

Hãy kiểm tra **happy path và negative path**. Một provider chấp nhận mọi secret có thể qua bài test thành công duy nhất; chính các bài test với key sai, missing, disabled và malformed mới phơi bày lỗ hổng.

Với dữ liệu có thời hạn, bổ sung kiểm thử key expired/revoked và `Clock` được tiêm vào để cố định thời gian. Với tenant, bổ sung test membership và nguyên tắc quyền tối thiểu. Tránh gọi database hoặc thời gian thực nếu mục đích là xác nhận thuật toán của provider.

## 4. Project Gradle có provider thật, không phụ thuộc HTTP

Ví dụ dùng API key theo mẫu `clientId.secret`. `clientId` dùng tra bản ghi, `secret` được băm rồi đối chiếu với digest lưu ở server. Bản ghi phía server định nghĩa account, enabled và scopes; client không có quyền tự chọn principal hoặc authority.

Tạo file `settings.gradle`:

~~~groovy
rootProject.name = 'provider-unit-test-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'

    testImplementation platform('org.junit:junit-bom:5.12.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Đây là project Java độc lập để chạy test. Khi đưa logic vào ứng dụng Spring Boot, dùng BOM của ứng dụng để quản lý phiên bản Spring Security và JUnit tương thích, tránh tự nâng riêng một thư viện.

### 4.1. Mã provider

Tạo file `src/main/java/example/auth/ApiKeyAuthentication.java`:

~~~java
package example.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class ApiKeyAuthentication {

    private ApiKeyAuthentication() {
    }

    // Request token chưa được xác thực, chỉ chứa credential.
    public static final class ApiKeyRequestToken
            extends AbstractAuthenticationToken {

        private String presentedKey;

        public ApiKeyRequestToken(String presentedKey) {
            super(List.of());
            this.presentedKey = presentedKey;
            super.setAuthenticated(false);
        }

        @Override
        public Object getPrincipal() {
            return null;
        }

        @Override
        public Object getCredentials() {
            return presentedKey;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Input token cannot authenticate itself"
                );
            }
            super.setAuthenticated(false);
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            presentedKey = null;
        }
    }

    // Bản ghi do server kiểm soát.
    public record KeyRecord(
            String accountId,
            byte[] secretDigest,
            boolean enabled,
            List<String> scopes) {

        public KeyRecord {
            Objects.requireNonNull(accountId, "accountId");
            secretDigest = Objects.requireNonNull(
                secretDigest, "secretDigest"
            ).clone();
            scopes = List.copyOf(scopes);
        }

        @Override
        public byte[] secretDigest() {
            return secretDigest.clone();
        }
    }

    @FunctionalInterface
    public interface KeyStore {
        Optional<KeyRecord> findById(String clientId);
    }

    public static final class Provider implements AuthenticationProvider {

        private final KeyStore store;

        public Provider(KeyStore store) {
            this.store = Objects.requireNonNull(store);
        }

        @Override
        public boolean supports(Class<?> type) {
            return ApiKeyRequestToken.class.isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (!(authentication instanceof ApiKeyRequestToken request)) {
                return null; // Token loại khác: provider này không xử lý.
            }

            try {
                if (request.isAuthenticated()) {
                    throw badCredentials();
                }

                String raw = (String) request.getCredentials();
                if (raw == null || raw.isBlank() || raw.length() > 512) {
                    throw badCredentials();
                }

                int dot = raw.indexOf('.');
                if (dot < 1 || dot == raw.length() - 1) {
                    throw badCredentials();
                }

                String id = raw.substring(0, dot);
                String secret = raw.substring(dot + 1);
                if (!id.matches("[A-Za-z0-9_-]{1,64}")) {
                    throw badCredentials();
                }

                KeyRecord record = store.findById(id)
                    .orElseThrow(ApiKeyAuthentication::badCredentials);

                if (!record.enabled()) {
                    throw new DisabledException("API key disabled");
                }

                byte[] providedDigest = digest(secret);
                byte[] expectedDigest = record.secretDigest();

                boolean accepted;
                try {
                    accepted = MessageDigest.isEqual(
                        providedDigest, expectedDigest
                    );
                } finally {
                    Arrays.fill(providedDigest, (byte) 0);
                    Arrays.fill(expectedDigest, (byte) 0);
                }

                if (!accepted) {
                    throw badCredentials();
                }

                List<GrantedAuthority> authorities = record.scopes()
                    .stream()
                    .map(scope -> (GrantedAuthority)
                        new SimpleGrantedAuthority("SCOPE_" + scope))
                    .toList();

                // Chỉ tạo trusted token sau khi credential hợp lệ.
                return UsernamePasswordAuthenticationToken.authenticated(
                    record.accountId(),
                    null,
                    authorities
                );
            } finally {
                // Dọn reference tới secret trên input token.
                request.eraseCredentials();
            }
        }
    }

    private static BadCredentialsException badCredentials() {
        return new BadCredentialsException("Invalid API key");
    }

    private static byte[] digest(String secret) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(
                secret.getBytes(StandardCharsets.UTF_8)
            );
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

**Giải thích thiết kế:**

- `ApiKeyRequestToken` không nhận role, không chứa principal đã xác minh, luôn bắt đầu với `authenticated=false`. Setter chặn tự nâng lên true.
- `supports()` chỉ khẳng định provider biết cách xử lý `ApiKeyRequestToken`; nó không có quyền chấp nhận mọi token cùng kiểu.
- Provider xác minh định dạng, tìm record, kiểm tra trạng thái key rồi so digest. Nếu sai, nó **ném exception**; không tạo token authenticated=false để giả làm kết quả success.
- Result là một token **mới** với account và scopes từ record. Mọi authority được xây dựng phía server.
- `KeyRecord` sao chép digest và scopes để tránh thay đổi ngoài ý muốn từ fixture hoặc adapter.
- `finally` gọi `eraseCredentials()`. Do `String` bất biến, bỏ tham chiếu trong token **không đảm bảo xóa sạch toàn bộ secret khỏi bộ nhớ JVM**; tránh ghi raw secret vào log và hạn chế thời gian sống.
- `MessageDigest.isEqual` so sánh digest. Với API key thực cần secret sinh đủ entropy, cơ chế lưu key, rotate/revoke, giới hạn rate và quan sát lỗi. **Không dùng SHA-256 đơn thuần thay thế PasswordEncoder dành cho mật khẩu người dùng.**

Đừng cho code xử lý HTTP tự gọi `UsernamePasswordAuthenticationToken.authenticated(...)` với principal hay role lấy từ JSON; factory trusted không tự xác minh credential. Chỉ dùng nó ở đoạn provider đã thực hiện kiểm tra thật.

## 5. Viết unit test không khởi động Spring context

Tạo file `src/test/java/example/auth/ApiKeyAuthenticationProviderTest.java`:

~~~java
package example.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class ApiKeyAuthenticationProviderTest {

    private ApiKeyAuthentication.Provider provider;

    @BeforeEach
    void setUp() {
        Map<String, ApiKeyAuthentication.KeyRecord> records = Map.of(
            "client-a",
            new ApiKeyAuthentication.KeyRecord(
                "svc-reports",
                digestForFixture("correct-secret"),
                true,
                List.of("reports.read")
            ),
            "blocked",
            new ApiKeyAuthentication.KeyRecord(
                "svc-blocked",
                digestForFixture("blocked-secret"),
                false,
                List.of("reports.read")
            )
        );

        ApiKeyAuthentication.KeyStore fakeStore =
            id -> Optional.ofNullable(records.get(id));

        provider = new ApiKeyAuthentication.Provider(fakeStore);
        SecurityContextHolder.clearContext();
    }

    @Test
    void validKeyProducesTrustedPrincipalAndServerScopes() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.correct-secret"
        );

        assertFalse(input.isAuthenticated());
        assertNull(input.getPrincipal());
        assertTrue(input.getAuthorities().isEmpty());

        Authentication result = provider.authenticate(input);

        assertNotNull(result);
        assertNotSame(input, result);
        assertTrue(result.isAuthenticated());
        assertEquals("svc-reports", result.getName());
        assertEquals(
            List.of("SCOPE_reports.read"),
            result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList()
        );
        assertNull(result.getCredentials());
        assertNull(input.getCredentials());
        assertFalse(input.isAuthenticated());

        // Provider không tự thiết lập SecurityContext.
        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void wrongSecretIsRejectedAndCredentialIsCleared() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.wrong-secret"
        );

        BadCredentialsException error = assertThrows(
            BadCredentialsException.class,
            () -> provider.authenticate(input)
        );

        assertEquals("Invalid API key", error.getMessage());
        assertNull(input.getCredentials());
        assertFalse(input.isAuthenticated());
    }

    @Test
    void unknownIdIsRejectedWithoutDisclosingSecret() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "unknown.any-secret"
        );

        BadCredentialsException error = assertThrows(
            BadCredentialsException.class,
            () -> provider.authenticate(input)
        );

        assertEquals("Invalid API key", error.getMessage());
        assertNull(input.getCredentials());
    }

    @Test
    void disabledKeyIsRejectedEvenWhenSecretMatches() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "blocked.blocked-secret"
        );

        assertThrows(
            DisabledException.class,
            () -> provider.authenticate(input)
        );
        assertNull(input.getCredentials());
    }

    @Test
    void malformedInputIsRejectedSafely() {
        List<String> badInputs = List.of(
            "",
            "client-a",
            ".secret",
            "client-a.",
            "bad id.secret",
            "client-a." + "x".repeat(600)
        );

        for (String raw : badInputs) {
            var input = new ApiKeyAuthentication.ApiKeyRequestToken(raw);
            assertThrows(
                BadCredentialsException.class,
                () -> provider.authenticate(input)
            );
            assertNull(input.getCredentials());
        }

        var nullInput = new ApiKeyAuthentication.ApiKeyRequestToken(null);
        assertThrows(
            BadCredentialsException.class,
            () -> provider.authenticate(nullInput)
        );
        assertNull(nullInput.getCredentials());
    }

    @Test
    void requestTokenCannotMarkItselfAuthenticated() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.correct-secret"
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> input.setAuthenticated(true)
        );
        assertFalse(input.isAuthenticated());
        assertTrue(input.getAuthorities().isEmpty());
    }

    @Test
    void supportsOnlyItsTokenType() {
        assertTrue(provider.supports(
            ApiKeyAuthentication.ApiKeyRequestToken.class
        ));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class
        ));
        assertNull(provider.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "someone", "password"
            )
        ));
    }

    @Test
    void providerManagerCallsTheRealProvider() {
        ProviderManager manager = new ProviderManager(List.of(provider));

        Authentication result = manager.authenticate(
            new ApiKeyAuthentication.ApiKeyRequestToken(
                "client-a.correct-secret"
            )
        );

        assertTrue(result.isAuthenticated());
        assertEquals("svc-reports", result.getName());
        assertNull(result.getCredentials());
    }

    @Test
    void providerManagerRejectsUnsupportedTokenType() {
        ProviderManager manager = new ProviderManager(List.of(provider));

        assertThrows(
            ProviderNotFoundException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "someone", "password"
                )
            )
        );
    }

    private static byte[] digestForFixture(String secret) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(
                secret.getBytes(StandardCharsets.UTF_8)
            );
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

### 5.1. Điều gì khiến bộ test có ý nghĩa?

**Không mock provider:** `provider.authenticate` là code thật, từ parse đến so digest và mapping quyền. `fakeStore` chỉ thay cho database/secret store; fixture dữ liệu rõ ràng, không phụ thuộc I/O. Nếu bạn mock `provider.authenticate` để trả sẵn token success, bạn chưa test provider.

**Kiểm tra cả input và output:** input bắt đầu với `false`, principal null, authorities rỗng; kết quả là **đối tượng khác**, `true`, principal `svc-reports`, chỉ authority `SCOPE_reports.read`. Không có cơ hội lấy `ROLE_ADMIN` từ client.

**Negative paths riêng:** sai secret, unknown ID, disabled, malformed. Chỉ có test key hợp lệ là không đủ; một bug “accept all” vẫn có thể qua happy path.

**Dọn credential:** sau cả success/failure, request token không còn tham chiếu raw key. Result cũng không chứa credential. Đây là assertion về lifecycle tham chiếu, không phải kiểm thử xóa dữ liệu vật lý khỏi heap.

**Tách trách nhiệm:** test xác nhận provider không tự set `SecurityContextHolder`. Filter/controller mới là nơi gắn Authentication cho request sau khi manager thành công.

**Manager thật:** hai test cuối gọi `ProviderManager` thực tế; phân biệt token được hỗ trợ với `ProviderNotFoundException` cho token khác kiểu.

Các test không dùng Mockito, `@SpringBootTest`, `@WebMvcTest` hay `MockMvc` vì đó chưa phải tầng cần kiểm chứng.

### 5.2. Chạy test

Từ thư mục chứa `build.gradle` và Gradle wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu project chưa có wrapper nhưng Gradle đã được cài, dùng `gradle test`. Có thể chạy riêng class:

~~~bash
./gradlew test --tests example.auth.ApiKeyAuthenticationProviderTest
~~~

Đoạn test trên định nghĩa **9 phương thức @Test**; case malformed còn lặp qua nhiều chuỗi bên trong một phương thức. Khi chạy thành công, Gradle kết thúc với dòng **BUILD SUCCESSFUL**; báo cáo HTML thường ở `build/reports/tests/test/index.html`.

**Kết quả test thực tế** cần được xác nhận bằng lệnh Gradle trong môi trường dự án của bạn; nội dung bài minh họa phương thức và kết quả kỳ vọng, không phải bằng chứng rằng app đã được tích hợp HTTP.

### 5.3. Chạy riêng một case khi có lỗi

~~~bash
./gradlew test --tests example.auth.ApiKeyAuthenticationProviderTest.wrongSecretIsRejectedAndCredentialIsCleared
~~~

Nếu case này thất bại, hãy kiểm tra logic provider và dữ liệu fixture, không bật servlet container ngay. Nếu mọi provider test pass nhưng request HTTP vẫn thất bại, chuyển sang bước kiểm thử filter và cấu hình chain.

## 6. Kiểm thử ProviderManager riêng trước khi tích hợp HTTP

Một provider test trực tiếp **không kiểm chứng** manager có thực sự chọn được provider không. Vì vậy thêm một lớp test nhỏ bằng manager thật:

~~~java
ProviderManager manager = new ProviderManager(List.of(provider));

Authentication result = manager.authenticate(
    new ApiKeyAuthentication.ApiKeyRequestToken(
        "client-a.correct-secret"
    )
);
~~~

`ProviderManager` dựa vào `supports` và kết quả của `authenticate`. Nếu không provider nào xử lý được, nó có thể ném `ProviderNotFoundException`.

Phân biệt:

- **Token đúng kiểu, sai secret:** provider hỗ trợ nhưng từ chối bằng `BadCredentialsException`.
- **Token khác kiểu, không provider nào hỗ trợ:** lỗi cấu hình hoặc loại token với `ProviderNotFoundException`.
- **Provider hỗ trợ loại token nhưng trả null:** manager có thể thử provider khác. Đây không phải cách mặc định từ chối secret sai của ví dụ.
- **Key disabled:** `DisabledException` là lỗi trạng thái; khi manager có nhiều provider, đặc tính dừng/tiếp tục theo loại ngoại lệ cần được test theo cấu hình thực.

Nếu ứng dụng có nhiều provider, ví dụ API key và username/password, thêm các case manager-level cho **đúng thứ tự**, đúng type và fallback. Không nhầm việc một provider `supports=true` với việc credential chắc chắn hợp lệ.

`ProviderManager` còn có hành vi liên quan việc xóa credential của authenticated result (khi hỗ trợ `CredentialsContainer`) và phát authentication event khi được cấu hình. Test trực tiếp một provider không tự kiểm chứng các hành vi quản lý này; thêm test ở cấp manager nếu ứng dụng phụ thuộc vào chúng.

## 7. Phần nào vẫn cần test khi ghép vào SecurityFilterChain?

Sau khi provider unit test và manager test pass, bước tiếp theo mới là thử HTTP:

1. **Đọc credential:** filter có đọc đúng `X-API-Key`, xử lý thiếu header, header trùng và độ dài quá mức không?
2. **Filter chain:** request có đi qua đúng `SecurityFilterChain`, `securityMatcher` và vị trí filter không?
3. **Success path:** filter lấy result từ `AuthenticationManager`, đặt `Authentication` đã xác thực vào `SecurityContext` của request và tiếp tục xử lý phù hợp không?
4. **Failure path:** `AuthenticationException` có được entry point/failure handler chuyển thành 401 hợp lý, không lộ key không?
5. **Authorization:** authenticated token có `SCOPE_reports.read` truy cập endpoint đọc nhưng bị từ chối với endpoint ghi cần scope khác không?
6. **Lifecycle:** SecurityContext được làm sạch sau request và không rò sang request khác/thread khác không?
7. **Session policy:** với API key thường dùng stateless; nếu ứng dụng chủ động dùng session thì phải kiểm tra repository, login/logout và session fixation tương ứng.
8. **CSRF/CORS/TLS/reverse proxy:** đây là đặc tính tầng web/deployment và threat model, không được chứng minh bằng provider unit test.

Ví dụ **mã minh họa trong test class đã có MockMvc, filter và endpoint**:

~~~java
mockMvc.perform(get("/reports")
        .header("X-API-Key", "client-a.correct-secret"))
    .andExpect(status().isOk());

mockMvc.perform(get("/reports")
        .header("X-API-Key", "client-a.wrong-secret"))
    .andExpect(status().isUnauthorized());
~~~

Đoạn này không phải Java class chạy độc lập. Ứng dụng phải cấu hình filter, matcher, endpoint và test support tương ứng. Với Spring Boot Servlet, thường dùng `spring-security-test` cùng phiên bản do Spring Boot BOM quản lý và `MockMvc` để chạy slice/integration test.

Test provider độc lập **không cần** dependency `spring-security-web` hoặc `spring-security-test`; chỉ thêm những thứ đó khi thực sự kiểm tra HTTP.

## 8. Các lỗi thiết kế test thường gặp

### 8.1. Chỉ assert không có exception

~~~java
assertDoesNotThrow(() ->
    provider.authenticate(
        new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.correct-secret"
        )
    )
);
~~~

Điều này chưa kiểm chứng kết quả: provider có thể trả null, trả token chưa xác thực, principal sai hoặc quyền sai. Hãy assert đầy đủ các trường của trusted result trên happy path.

### 8.2. Mock chính logic cần test

~~~java
// Minh họa một test yếu nếu subject là provider.
when(provider.authenticate(any())).thenReturn(fakeSuccess);
~~~

Test này chỉ xác nhận cấu hình mock. Mock `KeyStore`, `Clock`, dịch vụ I/O hoặc dùng fake có kiểm soát; chạy **provider thật**.

### 8.3. Chỉ test đúng credential

Một provider lỗi có thể trả authenticated cho cả credential đúng và sai. Negative-path tests bắt buộc phải kiểm tra từ chối, thông điệp lỗi an toàn và không tạo trusted result.

### 8.4. Lấy authority từ request chưa được tin

Nếu token đầu vào chứa `roles` tự khai và provider sao chép thẳng vào `GrantedAuthority`, client có thể tự tăng quyền. Test cần gửi request khai quyền cao nhưng server record chỉ cho quyền thấp, sau đó assert chỉ có quyền server. Ví dụ API key trên không thiết kế trường role đầu vào để loại đường tấn công này ngay từ cấu trúc token.

### 8.5. Nhầm supports với xác thực thành công

`supports(ApiKeyRequestToken.class) == true` không chứng minh bất cứ key nào đúng. Điều đó chỉ nói provider có thể xem xét token. Logic `authenticate` vẫn phải thực sự kiểm chứng secret.

### 8.6. Mọi lỗi đều trả null

Với provider đã xác định một credential sai, `BadCredentialsException` rõ nghĩa hơn việc luôn trả null. Nếu dùng nhiều provider hỗ trợ cùng loại token, null có thể làm manager thử provider khác; chính sách fallback phải được xem xét chủ động.

### 8.7. Dùng thời gian thực, database thật trong unit test

Nếu cần kiểm tra expiry, tiêm `Clock` cố định. Nếu cần kiểm tra lookup, fake repository/KeyStore. Test dựa vào thời gian ngủ, network hoặc database ngoài dễ chậm và không ổn định; để integration test riêng kiểm tra adapter thật.

### 8.8. Khẳng định quá mức từ kết quả xanh

Unit provider pass không chứng minh hệ thống có HTTPS, rate limit, CSRF, CORS, session policy, logging an toàn, cấu hình `SecurityFilterChain` hoặc 401/403 đúng. Phải triển khai kiểm thử ở đúng tầng tiếp theo.

### 8.9. Kiểm thử nội bộ thay vì hành vi

Không nên buộc provider gọi từng helper theo một thứ tự ngẫu nhiên nếu thứ tự đó không ảnh hưởng bảo mật. Kiểm thử kết quả từ input và quy tắc đã định nghĩa. Riêng thứ tự **check trạng thái trước khi xác thực hay sau**, mức tiết lộ thông tin, số lần truy vấn kho dữ liệu và xử lý secret có thể mang ý nghĩa bảo mật; test rõ khi đó là yêu cầu thật.

### 8.10. Ghi raw credential vào log khi test fail

Tránh in `Authentication.toString()`, request headers hoặc exception chứa raw secret vào console. Nếu cần chẩn đoán, chỉ log loại lỗi, correlation ID, trạng thái kiểm thử và ID được ẩn danh. Đừng biến test logs trong CI thành nơi lưu mật khẩu/API key.

## 9. Gợi ý test cho provider doanh nghiệp

Mẫu API key cố ý đơn giản. Khi provider thật hỗ trợ người dùng, tenant, OTP, thiết bị hoặc token bên thứ ba, mở rộng ma trận theo policy:

| Chủ đề | Trường hợp nên có |
| --- | --- |
| **Trạng thái account** | Enabled, disabled, locked, expired |
| **Credential** | Sai, đúng, bị thu hồi, hết hạn, bị rotate |
| **Tenant** | User thuộc tenant A, request khai tenant B: từ chối |
| **Scopes/roles** | Quyền của server thay đổi, request tự khai role: không được cấp thêm |
| **OTP** | Đúng challenge, hết hạn, sai mã, replay, quá số lần thử |
| **Nguồn trust** | Header từ reverse proxy chỉ được tin khi kênh/proxy đã xác minh |
| **Kho dữ liệu lỗi** | Không fail-open thành authenticated result; log nội bộ có kiểm soát |
| **Đa provider** | Thứ tự, null fallback, lỗi account, parent manager |
| **Observability** | Không lộ password/API key/CSRF/session ID trong log và exception |

Ví dụ kiểm thử expiry nên lấy `Clock` cố định thay vì ngủ chờ; kiểm thử tính toán credential cần dùng dữ liệu đã biết và đúng công cụ mã hóa/verify. Đối với password, sử dụng `PasswordEncoder.matches` với hash do server lưu thay vì so chuỗi hoặc SHA-256 trực tiếp.

## 10. Checklist trước khi ghép provider vào HTTP

Một provider đủ kiểm thử ở mức độc lập khi bạn đã có bằng chứng tự động cho:

- Input token **isAuthenticated=false**, không có authorities đáng tin và không tự nâng quyền.
- Đúng credential -> result authenticated, principal/authorities từ nguồn server.
- Sai credential, unknown, disabled, malformed -> thất bại an toàn, không có result trusted.
- `supports` đúng loại token; token khác loại không bị xử lý nhầm.
- Result không giữ raw credential; request credential được dọn trong phạm vi có thể.
- Provider không tự phụ thuộc `SecurityContextHolder` hoặc servlet.
- `ProviderManager` thật chọn được provider và báo thiếu provider khi không hỗ trợ.
- Test có thể lặp lại, không phụ thuộc HTTP, database thật, cổng mạng hoặc đồng hồ ngẫu nhiên.

Sau đó, ghép provider vào `AuthenticationManager` và `SecurityFilterChain`, thêm `MockMvc`/integration tests cho filter, SecurityContext, authorization, 401/403 và vòng đời request. Khi một lỗi xuất hiện, bạn sẽ biết nó thuộc **xác thực credential**, **điều phối provider** hay **tầng HTTP**.

## 11. Câu hỏi tự kiểm tra

**1.** Unit test provider với key đúng trả `authenticated=true`. Bạn đã chứng minh endpoint HTTP trả 200 chưa?  
**Đáp án:** Chưa; filter, chain, context và authorization cần test riêng.

**2.** Vì sao `assertDoesNotThrow(provider.authenticate(...))` không đủ?  
**Đáp án:** Provider vẫn có thể trả null, trả token false hoặc cấp sai quyền.

**3.** `supports(UsernamePasswordAuthenticationToken.class)` trả false trong provider API key: có nghĩa password sai?  
**Đáp án:** Không; provider không nhận xử lý token đó. Manager thiếu provider tương ứng có thể ném `ProviderNotFoundException`.

**4.** Nên fake cái gì trong unit test provider?  
**Đáp án:** Fake data store hoặc external service; dùng **provider thật** để kiểm tra thuật toán xác minh và mapping quyền.

**5.** Người dùng gửi role `ROLE_ADMIN` từ request trong khi server chỉ cấp `reports.read`. Result nên có quyền gì?  
**Đáp án:** Chỉ quyền do server cấp, ví dụ `SCOPE_reports.read`; tuyệt đối không chấp nhận role tự khai.

**6.** Provider pass nhưng HTTP trả 500 cho API key sai. Bạn kiểm tra ở đâu trước?  
**Đáp án:** Filter và failure handler/entry point xử lý `AuthenticationException`, sau khi đã xác nhận provider unit test sai key pass.

**7.** Tại sao cần test `ProviderManager` riêng?  
**Đáp án:** `supports`, danh sách và thứ tự provider, null result và exceptions có thể làm hành vi điều phối khác với khi gọi trực tiếp một provider.

## Tài liệu tham khảo

- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — AuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security 6.5 — AbstractAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [JUnit Jupiter 5.12.2 User Guide](https://docs.junit.org/5.12.2/user-guide/)
