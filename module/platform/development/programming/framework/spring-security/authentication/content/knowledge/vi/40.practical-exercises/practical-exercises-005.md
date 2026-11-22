# Xây AuthenticationProvider cho một loại bằng chứng riêng

## 1. Mục tiêu bài thực hành tổng hợp

Trong Spring Security, ứng dụng thường xác thực bằng username/password, session, HTTP Basic, JWT, OAuth2/OIDC hoặc passkey. Tuy nhiên có những hệ thống cần nhận **một loại bằng chứng riêng** từ thiết bị, quy trình cấp quyền nội bộ hoặc dịch vụ xác minh khác. Khi đó, thay vì nhét mã mới vào `UsernamePasswordAuthenticationToken` rồi giả vờ đó là password, ta có thể xây một **Authentication token riêng + AuthenticationProvider riêng + authentication filter riêng**, sau đó lắp vào `AuthenticationManager` và `SecurityFilterChain`.

Bài này thực hành theo mô hình **mã chứng thực mờ, chỉ dùng một lần** (*one-time opaque proof*), được cấp trước cho một principal cố định. Một HTTP client gửi mã qua header `X-Lab-Proof`. Server kiểm mã theo hash, thời hạn và trạng thái đã dùng; thành công sẽ tạo `Authentication` tin cậy có authority `PROOF_READ`, từ đó truy cập được một endpoint bảo vệ.

**Đây là bằng chứng dạng bearer secret**, không phải bằng chứng mật mã rằng client sở hữu private key, không phải passkey/FIDO2 và không phải SMS MFA. Ai biết đúng mã trước khi nó bị dùng có thể dùng mã ấy. Vì vậy phải bảo vệ **cấp phát, truyền tải, lưu trữ, sử dụng một lần và thu hồi**.

**Kết quả học tập:**

1. Hiểu đúng `Authentication`, `AuthenticationProvider`, `ProviderManager`, `SecurityContext` và trách nhiệm của Servlet filter.
2. Viết `ProofAuthenticationToken` chưa xác thực và phiên bản trusted **chỉ** do provider tạo sau khi kiểm bằng chứng.
3. Cài `supports(Class<?>)` đúng loại token và `authenticate(Authentication)` đúng ba trường hợp: success, `null` khi không hỗ trợ, `AuthenticationException` khi credential sai.
4. Kiểm bằng chứng một lần dùng bằng digest, so sánh an toàn, TTL và atomic state trong lab.
5. Tạo `SecurityFilterChain` stateless, custom header filter, 401 đúng và authorization theo authority.
6. Chạy Spring Boot/Java 17+ và kiểm thử provider, HTTP authentication, replay, credential clearing.
7. Biết rõ những gì **chưa đủ cho production**: phát hành mã, DB transaction phân tán, rate limiting, key management, MFA assurance và audit.

**Bộ phiên bản ví dụ:** Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.11**, Servlet/MVC, Maven và JUnit 5. Boot BOM 3.5.16 chính thức quản lý Security 6.5.11. Ví dụ không dựa vào API Spring Security 7+; nếu dùng Boot/Security dòng khác, kiểm compatibility và migration guide.

## 2. Chọn đúng bài toán: bằng chứng đặc biệt là gì?

Ví dụ một dịch vụ nội bộ tạo **một mã vào cổng duy nhất** cho người dùng đã được xác minh qua kênh đáng tin trước đó. Mã:

- Được phát hành ngoài HTTP API đang kiểm thử, thông qua một quy trình đã được xác thực/ủy quyền.
- Gắn với **account nội bộ** và một mục đích cụ thể, chẳng hạn `READ_ONE_DOCUMENT`.
- Có **entropy cao** nếu ở production, TTL ngắn, chỉ dùng **một lần**.
- Được chuyển đến client qua kênh bảo mật và gửi qua HTTPS header, **không** qua query string.
- Có bản digest được lưu ở server; sau khi xác minh thành công, trạng thái được chuyển sang **consumed**.
- Không tự cấp quyền ADMIN hoặc chọn principal theo giá trị JSON client gửi.

Trong **bài lab**, dùng mã có thể nhìn thấy `LAB-ONE-TIME-PROOF` để người học chạy `curl`. Đây là fixture **cố định và không bí mật**; không bao giờ dùng nó hoặc cách cấp mã hard-coded trong môi trường thật.

### 2.1. Phân biệt bốn thứ thường bị nhầm

| Đối tượng | Ý nghĩa | Ai tạo | Có đáng tin khi nhận từ client? |
| --- | --- | --- | --- |
| Raw proof | Mã/credential chưa được server xác minh | Một nhà phát hành tin cậy; trong lab là fixture | **Chưa** |
| Unauthenticated `ProofAuthenticationToken` | Container cho bằng chứng mà filter vừa nhận | Custom filter | **Chưa** |
| Authenticated `ProofAuthenticationToken` | Principal/authorities được server xác nhận | Custom provider sau proof validation | **Có**, trong trusted server boundary |
| `SecurityContext` | Trạng thái authentication của request/thread | Authentication filter/manager | Chỉ sau khi đặt Authentication đã được kiểm |

Không có ý nghĩa bảo mật nếu filter làm việc này ngay khi đọc header:

~~~java
// PHẢN VÍ DỤ: không bao giờ làm điều này!
var principal = request.getHeader("X-User");
var trusted = UsernamePasswordAuthenticationToken.authenticated(
    principal, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
SecurityContextHolder.getContext().setAuthentication(trusted);
~~~

Đoạn **phản ví dụ** tin trực tiếp dữ liệu do browser/client khai; attacker có thể đổi header thành principal khác. Đường đúng phải đi qua provider xác minh proof và ánh xạ proof sang account/quyền ở **dữ liệu server-side**.

### 2.2. Một proof một lần khác session đăng nhập dài hạn

Bài lab cho phép truy cập **một request HTTP** được gửi với proof hợp lệ; proof bị tiêu thụ ngay. Request tiếp theo dùng lại proof sẽ **401**. Đây là hành vi dự kiến, không phải bug.

Nếu ứng dụng thật cần “đăng nhập một lần rồi truy cập nhiều trang”, cần **flow trao đổi proof thành một session an toàn hoặc access token khác**, với session fixation protection, SecurityContextRepository, CSRF cho session/cookie, token audience/expiry/revocation. **Không tự biến one-time proof thành bearer token tái sử dụng** chỉ để tiện cho UI.

## 3. Kiến trúc Spring Security và đường dữ liệu

~~~text
HTTP GET /api/secret
X-Lab-Proof: <opaque-proof>
          |
          v
ProofHeaderFilter (OncePerRequestFilter)
  - đọc header có giới hạn độ dài
  - tạo ProofAuthenticationToken.untrusted(proof)
          |
          v
AuthenticationManager (ProviderManager)
          |
          v
ProofAuthenticationProvider
  - supports(ProofAuthenticationToken.class)?
  - kiểm kiểu token và isAuthenticated=false
  - kiểm proof trong ProofStore
  - xác minh hash + TTL + one-time use
  - ánh xạ subject + authorities SERVER-SIDE
          |
          +-- fail -> BadCredentialsException -> HTTP 401
          |
          +-- success -> ProofAuthenticationToken.trusted(...)
                               |
                               v
                 SecurityContextHolder.createEmptyContext()
                 context.setAuthentication(result)
                 SecurityContextHolder.setContext(context)
                               |
                               v
                  AuthorizationFilter: PROOF_READ?
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
                HTTP 200                 HTTP 403
                   |
                   v
         cuối request clear SecurityContext
         không lưu session (STATELESS)
~~~

**Trình tự trách nhiệm:**

- `OncePerRequestFilter`: chuyển request HTTP sang một Authentication request; xử lý HTTP response failure. Không tự công nhận mã là hợp lệ.
- `ProviderManager`: hỏi provider nào supports token, gọi authenticate và đưa ra kết quả hoặc exception.
- `AuthenticationProvider`: thẩm định proof, gắn một account đã biết và authority được cho phép, trả trusted token.
- `SecurityContextHolder`: lưu authentication **cho request hiện tại**, cần clear đúng lifecycle.
- `AuthorizationFilter`: kiểm endpoint có yêu cầu `PROOF_READ` hay không. Authentication thành công **không đồng nghĩa** có mọi quyền.
- `SecurityContextRepository`: quyết định lưu context giữa các request; lab dùng `NullSecurityContextRepository` để cố ý **không lưu session**.

### 3.1. Hợp đồng AuthenticationProvider

Hai phương thức:

~~~java
boolean supports(Class<?> authentication);
Authentication authenticate(Authentication authentication)
    throws AuthenticationException;
~~~

Trong provider cho proof riêng:

~~~java
@Override
public boolean supports(Class<?> type) {
    return ProofAuthenticationToken.class.isAssignableFrom(type);
}
~~~

`supports(true)` chỉ có nghĩa provider **có thể thử** xử lý loại token, không chứng minh proof đúng. Quy tắc return:

| Tình huống | authenticate(...) | Hệ quả |
| --- | --- | --- |
| Authentication token thuộc kiểu **khác** | `null` (nếu gọi trực tiếp) | Nhường provider khác; ProviderManager thường đã skip nhờ supports=false |
| Proof token đúng kiểu, mã đúng, chưa dùng, còn hạn | Trusted `Authentication` | Manager success |
| Proof token đúng kiểu, mã sai/hết hạn/đã dùng | Ném `BadCredentialsException` | Authentication failure |
| Proof token tự khai `isAuthenticated=true` ở input | Từ chối, không tin client | Chặn bypass |
| Store/service xác minh bị lỗi | `AuthenticationServiceException` hoặc fail closed phù hợp | Không giả thành success hoặc return null để qua provider yếu hơn |

**Không dùng `return null` cho proof sai** của một provider chịu trách nhiệm xác thực mã đó. Null có nghĩa không thể quyết định/không thuộc phạm vi, trong khi proof sai là một **kết quả thất bại**.

### 3.2. Vì sao cần custom Authentication token?

Có thể tận dụng `UsernamePasswordAuthenticationToken` để mang một chuỗi bất kỳ, nhưng rất dễ làm lẫn các cơ chế. Class riêng giúp:

- Nói rõ **đây là one-time proof**, không phải password.
- `supports(Class<?>)` không bắt nhầm username/password, OAuth2 bearer hoặc LDAP token.
- Phân biệt untrusted request và trusted result.
- Giữ authorities **trống** ở input, chỉ provider được quyền gắn role/scope.
- Có quy tắc không cho caller gọi `setAuthenticated(true)` để nâng tin cậy bằng tay.

`AbstractAuthenticationToken` là base class phù hợp: đã hỗ trợ authorities, details, `isAuthenticated()` và `CredentialsContainer`, nhưng ta vẫn phải định nghĩa principal, credentials và constructor an toàn.

## 4. Thiết kế ProofStore an toàn: digest, TTL và atomic consume

Trong lab, proof được “phát hành sẵn” ở startup. `ProofStore` ghi nhớ:

~~~text
proof_digest      = SHA-256(raw-proof)
subject_id        = learner
authority         = PROOF_READ
expires_at        = now + 30 minutes
used              = false
~~~

Khi nhận một mã:

1. Đảm bảo không null/trống và không quá dài.
2. Kiểm mã còn trong thời hạn theo **server clock**.
3. Tính digest bằng SHA-256; so với digest đã lưu bằng `MessageDigest.isEqual(...)`.
4. Nếu khớp, thực hiện atomic `compareAndSet(false, true)` để chỉ một lần nhận thành công trong **một JVM**.
5. Chỉ sau khi consume thành công mới cấp Authentication trusted.
6. Không gửi raw proof vào log, exception message, response hoặc SecurityContext.

**Vì sao SHA-256 digest có thể dùng với proof đủ ngẫu nhiên?** Nếu raw proof có 128–256 bit entropy, việc dò từ hash là không thực tế. Với password do con người đặt, **không** dùng SHA-256 đơn thuần; phải dùng `PasswordEncoder` phù hợp (bcrypt, Argon2, PBKDF2 hoặc scrypt tùy yêu cầu).

**Không nhầm atomic local với atomic đa máy chủ.** `AtomicBoolean` ngăn hai thread cùng process tiêu thụ một mã, nhưng **không chặn hai replicas** cùng chấp nhận. Production dùng database transaction/conditional update, Redis Lua script/atomic operation phù hợp, unique constraints và expiry; trạng thái consumed phải được ghi bền vững.

### 4.1. Mô hình database cho nhiều proof/account

Một thiết kế tham khảo:

~~~text
one_time_auth_proof
  id
  subject_id                (FK account nội bộ)
  digest                    (binary 32 bytes hoặc digest có domain separation)
  purpose                   (ví dụ READ_ONE_DOCUMENT)
  issued_at
  expires_at
  consumed_at nullable
  revoked_at nullable
  issuer_id
  audience/service
  account_version
  attempt_count
  metadata_sanitized
~~~

Giao dịch xác minh cần check **digest, subject binding, purpose, audience, TTL, active account và consumed_at IS NULL**; cập nhật `consumed_at` một cách atomic trước khi cấp principal. Nếu hàng bị cạnh tranh, chỉ một request được xác nhận.

**Không** cho client tự gửi `subject_id` rồi lấy user theo field đó. Subject phải lấy từ record bằng chứng được server xác minh. Nếu mã có giá trị đủ cao, nên thêm `HMAC(serverPepper, proof)` để hạn chế hậu quả khi database hash bị lộ, kết hợp key rotation; thiết kế phụ thuộc threat model và key management.

## 5. Project Spring Boot 3.5.16 / Java 17+ hoàn chỉnh

Ví dụ gồm **một file Java ứng dụng**, một file test provider, một file HTTP integration test và `pom.xml`. Code dùng bearer proof chỉ một lần, không có endpoint phát hành mã cho anonymous.

### 5.1. Cấu trúc

~~~text
custom-proof-provider/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/proof/ProofApp.java
    └── test/
        └── java/demo/proof/
            ├── ProofProviderTests.java
            └── ProofHttpTests.java
~~~

### 5.2. pom.xml

~~~xml
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
    <artifactId>custom-proof-provider</artifactId>
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
~~~

Không khai báo version riêng cho từng JAR Security để tránh lệch `core/web/config/test`. Với Spring Boot BOM 3.5.16, Spring Security 6.5.11 được quản lý đồng bộ.

### 5.3. ProofApp.java — application đầy đủ

Tạo `src/main/java/demo/proof/ProofApp.java`:

~~~java
package demo.proof;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AbstractAuthenticationToken;
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
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProofApp {

    public static void main(String[] args) {
        SpringApplication.run(ProofApp.class, args);
    }

    @Bean
    ProofStore proofStore() {
        return new ProofStore();
    }

    @Bean
    ProofProvider proofProvider(ProofStore store) {
        return new ProofProvider(store);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, ProofProvider provider) throws Exception {

        AuthenticationManager manager = new ProviderManager(provider);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/secret")
                    .hasAuthority("PROOF_READ")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            // Bài lab chỉ có GET, proof được gửi chủ động trong
            // header và không dùng cookie-based authentication.
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .addFilterBefore(
                new ProofHeaderFilter(manager),
                UsernamePasswordAuthenticationToken.class
                    .getSuperclass() == null
                    ? org.springframework.security.web.authentication
                        .UsernamePasswordAuthenticationFilter.class
                    : org.springframework.security.web.authentication
                        .UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @RestController
    static class Routes {

        @GetMapping("/api/health")
        String health() {
            return "ready";
        }

        @GetMapping("/api/secret")
        Identity secret(Authentication authentication) {
            return new Identity(
                authentication.getName(), "ONE_TIME_OPAQUE_PROOF");
        }
    }

    record Identity(String subject, String evidenceType) {}

    static final class ProofAuthenticationToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private Object proof;

        private ProofAuthenticationToken(
                Object principal,
                Object proof,
                Collection<? extends GrantedAuthority> authorities,
                boolean trusted) {
            super(authorities);
            this.principal = principal;
            this.proof = proof;
            super.setAuthenticated(trusted);
        }

        static ProofAuthenticationToken untrusted(String rawProof) {
            return new ProofAuthenticationToken(
                "unverified", rawProof, List.of(), false);
        }

        static ProofAuthenticationToken trusted(
                String userId,
                Collection<? extends GrantedAuthority> authorities) {
            return new ProofAuthenticationToken(
                userId, null, authorities, true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return proof;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            this.proof = null;
        }

        @Override
        public void setAuthenticated(boolean value) {
            if (value) {
                throw new IllegalArgumentException(
                    "Trusted tokens must be created by the provider");
            }
            super.setAuthenticated(false);
        }
    }

    static final class ProofStore {
        // FIXTURE công khai cho bài lab: KHÔNG dùng production!
        static final String LAB_PROOF = "LAB-ONE-TIME-PROOF";

        private final byte[] digest = sha256(LAB_PROOF);
        private final AtomicBoolean used = new AtomicBoolean(false);
        private final Instant expiresAt =
            Instant.now().plus(Duration.ofMinutes(30));

        String verifiedSubject() {
            return "learner";
        }

        boolean redeem(String submitted) {
            if (submitted == null || submitted.isBlank()
                    || submitted.length() > 256
                    || !Instant.now().isBefore(expiresAt)) {
                return false;
            }

            byte[] supplied = sha256(submitted);
            if (!MessageDigest.isEqual(digest, supplied)) {
                return false;
            }

            // Chỉ bảo đảm atomic trong một process/JVM.
            return used.compareAndSet(false, true);
        }

        private static byte[] sha256(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (NoSuchAlgorithmException impossible) {
                throw new IllegalStateException(impossible);
            }
        }
    }

    static final class ProofProvider implements AuthenticationProvider {
        private final ProofStore store;

        ProofProvider(ProofStore store) {
            this.store = store;
        }

        @Override
        public boolean supports(Class<?> type) {
            return ProofAuthenticationToken.class.isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication incoming)
                throws AuthenticationException {
            if (!(incoming instanceof ProofAuthenticationToken token)) {
                return null;
            }
            if (token.isAuthenticated()) {
                throw new BadCredentialsException("Invalid proof");
            }
            if (!(token.getCredentials() instanceof String raw)
                    || !store.redeem(raw)) {
                throw new BadCredentialsException("Invalid proof");
            }

            // Principal và authority đến từ dữ liệu SERVER, không
            // tin username hoặc role do client tự khai.
            return ProofAuthenticationToken.trusted(
                store.verifiedSubject(),
                List.of(new SimpleGrantedAuthority("PROOF_READ")));
        }
    }

    // Không gắn @Component/@Bean để tránh Boot đăng ký filter
    // thêm một lần ở Servlet container ngoài SecurityFilterChain.
    static final class ProofHeaderFilter extends OncePerRequestFilter {
        private final AuthenticationManager manager;

        ProofHeaderFilter(AuthenticationManager manager) {
            this.manager = manager;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String raw = request.getHeader("X-Lab-Proof");

            if (raw == null) {
                chain.doFilter(request, response);
                return;
            }

            if (raw.isBlank() || raw.length() > 256) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }

            ProofAuthenticationToken requestToken =
                ProofAuthenticationToken.untrusted(raw);
            Authentication verified;

            try {
                verified = manager.authenticate(requestToken);
            } catch (AuthenticationException failure) {
                // Không ghi header/credential hoặc exception message.
                SecurityContextHolder.clearContext();
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            } finally {
                requestToken.eraseCredentials();
            }

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(verified);
            SecurityContextHolder.setContext(context);

            try {
                chain.doFilter(request, response);
            } finally {
                SecurityContextHolder.clearContext();
            }
        }
    }
}
~~~

### 5.4. Chỉnh một dòng cho dễ đọc trước khi chạy

Trong `security(...)`, đoạn `.addFilterBefore(...)` của file trên có biểu thức ba ngôi chỉ để làm nổi bật việc anchor **bắt buộc là class Filter**, không phải Authentication token. Hãy **thay nguyên block `.addFilterBefore(...)` đó** bằng cách viết đơn giản và tương đương sau trước khi biên dịch:

~~~java
.addFilterBefore(
    new ProofHeaderFilter(manager),
    UsernamePasswordAuthenticationFilter.class);
~~~

Đồng thời thêm import:

~~~java
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
~~~

**Không được truyền `UsernamePasswordAuthenticationToken.class` làm anchor cho `addFilterBefore`**: token không phải Servlet Filter. Trong bài lab này, việc viết gọn trên là cách đề xuất và nên được dùng trong project cuối cùng.

> Phần cấu hình `csrf.disable()` ở ví dụ chỉ phù hợp vì đây là API lab **stateless, GET-only, không dựa vào cookie tự gửi** và client tự trình secret trong header. Nếu biến flow thành session/cookie hoặc thêm POST có side effects, phải phân tích lại CSRF và không copy tắt CSRF một cách máy móc.

## 6. Kiểm thử provider trực tiếp bằng JUnit 5

Tệp `src/test/java/demo/proof/ProofProviderTests.java`:

~~~java
package demo.proof;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class ProofProviderTests {

    @Test
    void supportsOnlyCustomTokenType() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        assertTrue(provider.supports(
            ProofApp.ProofAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
    }

    @Test
    void unsupportedAuthenticationReturnsNullIfCalledDirectly() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        Authentication unrelated =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "password");

        assertNull(provider.authenticate(unrelated));
    }

    @Test
    void incorrectProofIsRejectedAndDoesNotConsumeValidProof() {
        var store = new ProofApp.ProofStore();
        var provider = new ProofApp.ProofProvider(store);

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                ProofApp.ProofAuthenticationToken.untrusted("wrong")));

        Authentication success = provider.authenticate(
            ProofApp.ProofAuthenticationToken.untrusted(
                ProofApp.ProofStore.LAB_PROOF));

        assertTrue(success.isAuthenticated());
        assertEquals("learner", success.getName());
    }

    @Test
    void correctProofCreatesTrustedResultAndRejectsReplay() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        Authentication verified = provider.authenticate(
            ProofApp.ProofAuthenticationToken.untrusted(
                ProofApp.ProofStore.LAB_PROOF));

        assertTrue(verified.isAuthenticated());
        assertEquals("learner", verified.getName());
        assertNull(verified.getCredentials());
        assertTrue(verified.getAuthorities().stream()
            .anyMatch(a -> "PROOF_READ".equals(a.getAuthority())));

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                ProofApp.ProofAuthenticationToken.untrusted(
                    ProofApp.ProofStore.LAB_PROOF)));
    }

    @Test
    void trustedInputCannotBeReauthenticatedAsRawProof() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        Authentication alreadyTrusted =
            ProofApp.ProofAuthenticationToken.trusted(
                "fake-principal",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(alreadyTrusted));
    }
}
~~~

Những assert quan trọng:

- Kiểm loại token được hỗ trợ, loại không hỗ trợ.
- Unsupported trực tiếp trả `null`, còn sai proof thuộc đúng loại ném `BadCredentialsException`.
- Proof hợp lệ tạo principal tin cậy và chỉ authority `PROOF_READ`.
- Không giữ raw proof ở `getCredentials()` của authenticated result.
- Replay bị từ chối.
- Provider không chấp nhận sẵn một token trusted được ai đó tự tạo ở input.

**Phạm vi unit test:** mỗi test khởi tạo `ProofStore` mới, tránh việc test này tiêu thụ proof làm test khác thất bại theo thứ tự chạy. Với persistence production, test cùng DB transaction/multi-replica và race riêng.

## 7. Kiểm thử HTTP/Filter/SecurityContext bằng MockMvc

Tệp `src/test/java/demo/proof/ProofHttpTests.java`:

~~~java
package demo.proof;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProofHttpTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthIsAccessibleWithoutProof() throws Exception {
        mvc.perform(get("/api/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void missingProofCannotAccessProtectedResource()
            throws Exception {
        mvc.perform(get("/api/secret"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidProofGetsUnauthorizedWithoutPrincipal()
            throws Exception {
        mvc.perform(get("/api/secret")
                .header("X-Lab-Proof", "wrong"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validProofGrantsOneRequestAndReplayFails()
            throws Exception {
        mvc.perform(get("/api/secret")
                .header("X-Lab-Proof",
                    ProofApp.ProofStore.LAB_PROOF))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("learner"))
            .andExpect(jsonPath("$.evidenceType")
                .value("ONE_TIME_OPAQUE_PROOF"));

        mvc.perform(get("/api/secret")
                .header("X-Lab-Proof",
                    ProofApp.ProofStore.LAB_PROOF))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 7.1. Các tính chất được kiểm

| Test | Giá trị chứng minh |
| --- | --- |
| GET /api/health không proof | Route public hoạt động |
| GET /api/secret không proof | Authorization/entry point trả 401 |
| GET /api/secret proof sai | Provider/Filter từ chối, không tạo trusted principal |
| GET /api/secret proof đúng, rồi dùng lại | Request đầu có authority từ server, request sau bị chặn replay |

Bộ project có **5 unit tests + 4 HTTP integration tests = 9 tests**.

**Không dùng `@WithMockUser` để thay thế những test này:** helper đặt sẵn principal vào `SecurityContext` và **không chứng minh ProofAuthenticationProvider thật được gọi**. Hãy gửi custom header qua filter và kiểm request sau cùng như code trên.

### 7.2. Chạy tests

Trong thư mục project có JDK 17+ và Maven:

~~~bash
mvn clean test
~~~

Khi dependency resolution và code biên dịch thành công, tóm tắt kết quả **mong đợi**:

~~~text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kỳ vọng đối với project ví dụ**, không phải log đã được chạy trên máy người đọc. Maven còn in thêm output theo plugin và phiên bản JDK.

### 7.3. Chạy bằng HTTP local

Khởi động app từ một JVM mới (proof chưa bị tiêu thụ):

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint public:

~~~bash
curl -i http://localhost:8080/api/health
~~~

Gọi endpoint bảo vệ không có proof:

~~~bash
curl -i http://localhost:8080/api/secret
~~~

Kỳ vọng HTTP 401. Sau đó dùng **fixture demo**:

~~~bash
curl -i -H "X-Lab-Proof: LAB-ONE-TIME-PROOF" \
  http://localhost:8080/api/secret
~~~

Kỳ vọng HTTP 200, body có dữ liệu tương đương:

~~~json
{"subject":"learner","evidenceType":"ONE_TIME_OPAQUE_PROOF"}
~~~

Gửi **cùng lệnh lần thứ hai**: HTTP 401 vì `ProofStore` đã tiêu thụ mã.

Nếu bạn đã chạy request thành công một lần trong **cùng JVM**, lần chạy kế tiếp phải bị từ chối; để minh họa issuance mới trong lab, hãy restart process để `ProofStore` được khởi tạo lại. **Đây là hành vi lab không được dùng làm cơ chế reset proof production**; ở production, mã đã dùng phải không được tái kích hoạt khi restart server.

Cảnh báo: local HTTP/curl chỉ phục vụ lab. Trên môi trường thật phải dùng HTTPS, mã có entropy cao và không in raw proof vào shell history, log, proxy hoặc issue tracker.

## 8. Java 17 độc lập: mô phỏng so sánh digest và single-use

Để hiểu cơ chế một lần dùng **không cần Spring Boot**, tạo `OneTimeProofRulesDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;

public class OneTimeProofRulesDemo {

    static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    static final class OneTimeStore {
        private final byte[] expected = digest("proof-example");
        private final AtomicBoolean used = new AtomicBoolean(false);
        private final Instant expiresAt;

        OneTimeStore(Instant createdAt) {
            this.expiresAt = createdAt.plus(Duration.ofMinutes(10));
        }

        boolean redeem(String value, Instant now) {
            return value != null
                && now.isBefore(expiresAt)
                && MessageDigest.isEqual(expected, digest(value))
                && used.compareAndSet(false, true);
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        OneTimeStore store = new OneTimeStore(now);

        System.out.println("wrong=" + store.redeem("bad", now));
        System.out.println("first=" + store.redeem("proof-example", now));
        System.out.println("replay=" + store.redeem("proof-example", now));

        OneTimeStore expired = new OneTimeStore(now);
        System.out.println("expired=" +
            expired.redeem("proof-example", now.plusSeconds(601)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OneTimeProofRulesDemo.java
java OneTimeProofRulesDemo
~~~

**Stdout chính xác:**

~~~text
wrong=false
first=true
replay=false
expired=false
~~~

Bộ mã này cố tình sử dụng `proof-example` cố định **chỉ để dễ chạy**, không dùng làm security credential thật. `AtomicBoolean` chỉ an toàn trong một JVM; với nhiều replicas cần storage/transaction nhất quán.

## 9. Tại sao không dùng filter tự kiểm raw header và setAuthenticated(true)?

Một sai lầm phổ biến:

~~~java
// PHẢN VÍ DỤ, không dùng trong production!
if ("some-secret".equals(request.getHeader("X-Proof"))) {
    var result = UsernamePasswordAuthenticationToken.authenticated(
        request.getHeader("X-User"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
    SecurityContextHolder.getContext().setAuthentication(result);
}
~~~

Những vấn đề:

- Server tin username/role do client tự khai.
- Secret là hard-coded và so sánh đơn giản, có thể bị lộ trong mã nguồn.
- Không có TTL, purpose, account binding hoặc replay protection.
- Không có rate limit, audit và lifecycle.
- Không có provider riêng để unit test hoặc thay đổi cơ chế proof an toàn.
- Dễ dùng nhầm provider, bỏ qua state checking.
- Nếu đưa filter quá muộn trong security chain, authorization có thể đã diễn ra.
- Có nguy cơ không clear context đúng khi servlet thread được tái sử dụng.

**Thiết kế bài lab** tách filter (vận chuyển), manager (điều phối), provider (quyết định), store (trạng thái proof), authorization (cấp quyền theo policy) giúp kiểm từng lớp độc lập.

## 10. Tại sao chọn OncePerRequestFilter và vị trí filter?

`OncePerRequestFilter` là Spring Web abstraction giúp chạy filter một lần cho một request dispatch theo semantics của nó. Khi dùng trong Spring Security:

- Phải chạy **sau khi SecurityContextHolderFilter đã chuẩn bị context**, trước authorization.
- Có thể đặt trước `UsernamePasswordAuthenticationFilter` (một thứ tự đã đăng ký) hoặc theo hướng dẫn filter ordering phù hợp.
- Không nên gắn `@Component` cho filter **đồng thời** đưa nó vào `HttpSecurity.addFilterBefore/After` vì Spring Boot có thể auto-register servlet filter riêng, tạo **double execution**.
- Filter chỉ nên nhận proof, đóng gói untrusted token và gọi manager.
- Authentication failure phải xử lý rõ ràng; exception ném từ filter trước `ExceptionTranslationFilter` **không nên được giả định** tự biến thành 401 nếu không có failure handling phù hợp.
- Khi thành công, đặt `SecurityContext` mới và clear sau request, tránh làm lộ authentication sang request khác.
- Với stateless API, không save context; request tiếp theo phải đưa evidence mới hoặc một credential trao đổi phù hợp.
- Nếu thực hiện login tạo session, thêm `SessionAuthenticationStrategy` và `SecurityContextRepository.saveContext(...)` theo Spring Security 6, không chỉ gọi `SecurityContextHolder.setContext(...)`.

**Sửa chuỗi filter:** phần `addFilterBefore(...)` cuối cùng cần dùng anchor **`UsernamePasswordAuthenticationFilter.class`**, không phải class Authentication token. Việc nhầm lẫn “token” với “filter” là một lỗi compile phổ biến.

## 11. Stateless và CSRF: không sao chép cấu hình tùy tiện

Trong lab:

- Endpoint xử lý evidence là **GET**.
- Credentials nằm trong **header do client chủ động gửi**, không phải HTTP cookie tự gửi.
- `NullSecurityContextRepository` không lưu authenticated context.
- Không tạo browser login session.
- Vì vậy demo có thể tắt CSRF trong **security chain cụ thể này**.

Nếu mở rộng sang một ứng dụng web có cookie-based session, CSRF vẫn quan trọng cho POST login, logout, đổi dữ liệu. Không áp một câu “REST API không cần CSRF” cho mọi kiến trúc.

Nếu thêm endpoint POST `/api/proof/redeem` để đổi mã thành cookie:

1. Xác định credential nào browser gửi tự động.
2. Chặn CSRF/login CSRF theo threat model.
3. Tạo authenticated context sau khi proof được xác minh.
4. Gọi SessionAuthenticationStrategy để chống fixation và kiểm session policy.
5. `SecurityContextRepository.saveContext(context, request, response)` để lưu phiên.
6. Cấp cookie `Secure`, `HttpOnly`, `SameSite` phù hợp.
7. Vô hiệu hóa proof một lần với DB transaction trước khi cấp session; tính cả race/retry.
8. Audit, giới hạn số phiên và có logout/revocation.

**Không** lưu raw proof trong session, response body hoặc success-event payload.

## 12. Mở rộng sang proof loại khác

| Bằng chứng | Input token riêng | Provider cần xác minh |
| --- | --- | --- |
| Opaque one-time voucher | Custom ProofAuthenticationToken | Entropy, digest, TTL, account binding, single use |
| TOTP | Custom OTP token, thường là **factor bổ sung** | Secret đã enrollment, time step, replay/rate limit, MFA state |
| HMAC challenge response | Challenge token + signature/HMAC | Nonce, key binding, timestamp/audience, chống replay |
| mTLS client certificate | X.509 hoặc pre-auth token | TLS chain, CA trust, revocation, subject mapping |
| WebAuthn/passkey | Các loại WebAuthn token/ceremony phù hợp | Challenge, RP ID, origin, signature, UV và credential binding |
| Third-party signed assertion | SAML/OIDC/JWT validation phù hợp | Issuer, audience, signature, time, nonce/state, policy |
| Hardware device attestation | Custom attestation token | Certificate chain/vendor trust, challenge freshness, device binding |

**Ưu tiên framework/protocol được hỗ trợ** cho OAuth2/OIDC/SAML/WebAuthn/X.509 thay vì tự phát minh crypto/authentication protocol. Custom provider thích hợp khi loại bằng chứng thực sự riêng và có cơ chế verification có thể đánh giá/kiểm thử độc lập.

### 12.1. Opaque voucher không phải yếu tố chống phishing

Mã lab chỉ là bearer secret. Nó có thể bị phishing, malware hoặc người khác sao chép trước khi dùng. Nếu yêu cầu **phishing-resistant authentication**, cần cơ chế cryptographic challenge/response gắn origin/RP như WebAuthn theo chuẩn, không gọi một OTP hoặc one-time voucher là passkey.

### 12.2. Custom factor thường nên là step-up, không phải login thay thế

Nếu đang xây MFA, việc kiểm một OTP đơn lẻ thành công **không được tự tạo fully authenticated user** khi chính sách cần cả password và OTP. Cần mô hình lưu rõ primary factor đã xác minh, freshness, challenge-bound OTP, session binding và authorization theo MFA state. Không để one-time code đơn giản trở thành đường đăng nhập yếu hơn password/passkey.

## 13. Các lỗ hổng phải chủ động chống

| Rủi ro | Tình huống | Biện pháp |
| --- | --- | --- |
| **Spoofing principal** | Client gửi `X-User: admin` | Ánh xạ subject từ verified store, không tin header |
| **Role escalation** | Client gửi `role=ADMIN` | Authorities chỉ lấy từ server policy |
| **Replay** | Gửi proof thành công nhiều lần | Atomic consume, TTL, purpose |
| **Race** | Hai request song song vào hai replicas | Transaction/conditional update distributed |
| **Guessing** | Proof ngắn, dễ đoán | CSPRNG ≥128 bit entropy, rate limit, không enumeration |
| **Leakage** | Code trong URL, log, APM | Header over HTTPS; header allowlist/redaction |
| **Stolen bearer proof** | Credential bị copy trước khi dùng | TLS, TTL, hạn chế audience, device/risk context |
| **Confused deputy** | Proof phát cho service A dùng được ở B | Audience/service binding |
| **Account takeover** | Proof chưa đủ assurance nhưng đăng nhập full | Step-up/assurance policy, không downgrade |
| **Revocation gap** | Account bị khóa nhưng proof vẫn hoạt động | Check account active/version ngay lúc redeem |
| **DoS** | Attacker thử nhiều proof | Rate limit theo source/account risk, metrics |
| **Session leak** | Thread reuse mang SecurityContext cũ | Clear context, NullRepository khi stateless |
| **Filter double-registration** | Spring Boot đăng ký Filter bean ngoài chain | Không @Component Filter đã addFilterBefore |
| **Wrong chain/matcher** | Custom proof API vô tình permitAll | denyAll default, test security matchers |
| **Information leakage** | Response phân biệt unknown/expired/used | HTTP 401 + thông báo chung; audit nội bộ theo category |
| **Backdoor in test** | Fixture cố định vô tình lên production | Profile/env gating, secret issuance external |

### 13.1. Proof issuance phải được bảo vệ riêng

Chương trình thực hành **không có endpoint `/issue-proof`**, bởi việc phát mã cho người dùng **là một bài toán security khác**. Production nên phát mã bằng `SecureRandom`, ví dụ 32 byte và Base64URL:

~~~java
// Fragment Java17, không phải API phát mã hoàn chỉnh.
byte[] random = new byte[32];
new java.security.SecureRandom().nextBytes(random);
String rawProof = java.util.Base64.getUrlEncoder()
    .withoutPadding().encodeToString(random);
~~~

Không lưu plaintext mã trong database sau khi phát; chỉ trao cho chủ thể đã được xác thực qua kênh tin cậy. Nếu DB bị lộ, digest của mã đủ entropy giúp giảm nguy cơ brute force nhưng vẫn cần bảo vệ storage và truy cập.

### 13.2. Header parsing và request smuggling

Header `X-Lab-Proof` cần giới hạn ký tự/độ dài. Trong production còn phải quyết định nếu request chứa **nhiều header cùng tên**, comma-joined values hoặc proxy thay đổi capitalization/whitespace thì xử lý sao; nên từ chối ambiguity, không tự nối secrets. Đừng tin một header “X-Verified-User” do Internet trực tiếp gửi nếu chỉ proxy nội bộ có quyền tạo header đó.

Một request đến backend qua reverse proxy phải có trust boundary rõ. Nếu server tin client certificate hoặc pre-auth identity từ gateway, gateway phải **xóa header spoofed** từ request ngoài trước khi thêm header verified.

## 14. ProviderManager, thứ tự providers và sự kiện xác thực

`ProviderManager` thường thử các `AuthenticationProvider` theo thứ tự:

- Nếu `supports(type)=false`, bỏ qua provider.
- Nếu provider trả `null`, thử provider tiếp theo.
- Nếu provider trả non-null authenticated result, dừng thử và dùng kết quả.
- Với `BadCredentialsException` thông thường, manager có thể tiếp tục provider sau nếu nó cũng supports token; phải thiết kế **không cho fallback sang cơ chế yếu hơn** của cùng account.
- Với một số account status/service exceptions nghiêm trọng, manager dừng sớm; không được dùng fallback để bypass locked/disabled account.
- Nếu không provider nào xử lý, `ProviderNotFoundException`.
- `ProviderManager` thường gọi `eraseCredentials()` trên trusted result implements CredentialsContainer trước khi trả.

**Quan trọng về events:** Một `new ProviderManager(provider)` thủ công mặc định không tự gắn application event publisher. Nếu muốn `AuthenticationSuccessEvent` hoặc failure events, dùng `manager.setAuthenticationEventPublisher(authenticationEventPublisher)` và đảm bảo bean đúng. Tránh vừa phát trong provider/filter vừa để manager phát trùng.

Ví dụ fragment trong một cấu hình có bean publisher:

~~~java
ProviderManager manager = new ProviderManager(proofProvider);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

Không log raw `ProofAuthenticationToken` hoặc `AuthenticationException.getMessage()` có thể mang secret; audit nên ghi loại sự kiện, thời điểm, proof type, account ID nội bộ đã được bảo vệ, kết quả và correlation ID.

## 15. Kiểm thử bổ sung cho production

### 15.1. Unit test thiết yếu

- [ ] supports true cho token riêng, false cho `UsernamePasswordAuthenticationToken`/JWT token.
- [ ] Proof đúng tạo Authentication authenticated=true, principal đúng và authority tối thiểu.
- [ ] Proof sai ném `BadCredentialsException`, không `return null`.
- [ ] Token giả đã authenticated ở input bị chặn.
- [ ] Không ghi credential vào authenticated token, không log input.
- [ ] Proof rỗng/NULL/quá dài bị từ chối.
- [ ] Hết hạn theo server clock thì thất bại.
- [ ] Chạy lại proof sau success phải thất bại.
- [ ] Replay đồng thời nhiều threads chỉ một request thành công.

### 15.2. HTTP/security integration

- [ ] Public health hoạt động không cần proof.
- [ ] Protected resource thiếu/invalid proof trả 401.
- [ ] Valid proof tạo SecurityContext đúng và authorization mới qua.
- [ ] Không dùng lại proof để truy cập lần hai.
- [ ] Request không giữ authenticated session sau khi kết thúc.
- [ ] Endpoint không khai báo không bị bỏ trống security chain.
- [ ] Proof không xuất hiện trong response, logs, tracing, metrics.
- [ ] Nếu thay đổi thứ tự filters, kiểm provider vẫn chạy trước authorization.
- [ ] Nếu thêm browser cookie, bật lại CSRF/session policy phù hợp.

### 15.3. Multi-instance và vận hành

- [ ] Hai replicas nhận cùng proof chỉ một commit.
- [ ] Mất kết nối DB/Redis làm authentication fail closed, không trả success.
- [ ] Clock skew/bounds được đánh giá; TTL so theo thời gian server.
- [ ] State consumed/revoked không “sống lại” sau restart.
- [ ] Rate limiting, request size limits, WAF/gateway controls có test.
- [ ] Issuer/audience/purpose binding được kiểm; account bị khóa không truy cập.
- [ ] Có cleanup expired proofs, retention và audit.
- [ ] Có metrics failure theo category nhưng không dùng raw proof làm label.
- [ ] Secrets trong storage/backup/CI/logging được bảo vệ.
- [ ] Phân tích threat model, penetration testing và code review trước production.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `ProviderNotFoundException` | supports sai token class; manager không chứa provider | Test supports, kiểm wiring và Filter |
| `ClassCastException` | Provider cast token khác loại | Kiểm instanceof, supports đúng |
| Header đúng nhưng nhận 401 ngay lần đầu | Token đã tiêu thụ, timeout hoặc code khác fixture | Restart lab để reset fixture; production không reset consumed |
| Proof đúng nhưng 403 | Authentication success nhưng thiếu authority theo policy | Kiểm authorities server-side |
| Không thấy 401 khi thiếu header | Endpoint permitAll/matcher sai hoặc entry point khác | Default deny, test Missing Proof |
| Không có SecurityContext tại controller | Filter đặt sau authorization, context bị clear sớm | Kiểm filter order và chain |
| Request sau proof thành công bị 401 | Lab cố ý one-time + stateless | Nếu cần session, thiết kế exchange flow riêng |
| Vô tình tạo HttpSession | Repository/session policy không stateless hoặc filter khác | Kiểm session creation chain |
| Filter được gọi hai lần | Filter @Bean/@Component và addFilterBefore cùng lúc | Chỉ đăng ký trong SecurityFilterChain |
| Bad proof trả null và provider khác xác thực | Semantic fallback sai | Ném BadCredentialsException, giới hạn cơ chế khác |
| Provider báo success từ userId header | Trust boundary sai | Subject từ verified store |
| Role ADMIN do client gửi | Authority injection | Roles từ server policy |
| Race giữa hai replicas | AtomicBoolean chỉ local | Transaction/compare-and-set tập trung |
| Test với @WithMockUser vẫn pass khi provider hỏng | Test bỏ qua manager/filter | Gửi request thật với custom proof |
| Logout/browser flow hỏng sau khi đổi thành session | Thiếu session save, fixation/CSRF | Dùng SessionAuthenticationStrategy/Repository đúng |
| Bật token vào query URL để tiện debug | Log/referrer/history rò secrets | Header HTTPS, redaction và safe telemetry |

## 17. Câu hỏi tự kiểm tra

1. Tại sao nên tạo `ProofAuthenticationToken` riêng thay vì nhét mã vào username/password token?
2. `supports(Class<?>)` kiểm điều gì, và có kiểm mã đúng hay không?
3. `authenticate(...)` cần trả `null` khi nào? Vì sao proof sai không nên trả null?
4. Bằng chứng bearer một lần có phải phishing-resistant như WebAuthn không?
5. Vì sao client không được tự đặt principal hoặc authorities trong kết quả đã xác thực?
6. Vì sao chỉ provider mới nên được tạo token trusted?
7. Một one-time proof có thể dùng lại để gọi nhiều HTTP GET không?
8. `AtomicBoolean` bảo đảm single-use ở phạm vi nào?
9. Nếu chạy trên ba replicas, lưu `consumed_at` thế nào để không race?
10. Digest SHA-256 phù hợp với mã ngẫu nhiên 256-bit, nhưng có phù hợp mật khẩu ngắn không?
11. Vì sao `NullSecurityContextRepository` được dùng trong lab?
12. Tại sao custom filter không nên là Servlet Filter bean đăng ký hai lần?
13. Vì sao phải đặt filter trước authorization?
14. Một 401 thiếu/invalid proof khác 403 không đủ authority thế nào?
15. Khi đổi flow thành cookie-based login, phải thêm session fixation/CSRF/saveContext gì?
16. Vì sao cần test HTTP qua filter thay vì chỉ dùng @WithMockUser?
17. Issuer, audience và purpose binding giúp chống dạng tấn công nào?
18. Nên sử dụng custom provider hay giao thức chuẩn khi bài toán là OIDC, SAML, WebAuthn?
19. Làm sao đảm bảo mã bị revoke và không sống lại sau restart?
20. Trong tình huống DB xác minh proof mất kết nối, nên có hành vi fail-open hay fail-closed?

**Kết luận:** một `AuthenticationProvider` cho bằng chứng riêng phải **tách bằng chứng chưa tin cậy khỏi kết quả tin cậy**, chỉ ra chính xác token type bằng `supports(...)`, kiểm proof trong `authenticate(...)`, trả trusted principal/authorities **từ server**, xử lý sai/hết hạn/replay an toàn, và kết nối qua filter/manager/security context đúng thứ tự. Bài lab một lần dùng là bước khởi đầu để học contract; production đòi cấp phát entropy cao, distributed atomic state, rate limiting, quản lý session/assurance và audit.

## 18. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — AbstractAuthenticationToken Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [Spring Security 6.5 — Servlet Architecture, Adding Filters](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — NullSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/NullSecurityContextRepository.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
