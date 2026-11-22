# Phân biệt lỗi người dùng với sự cố kho tài khoản hoặc dịch vụ danh tính

> **Phạm vi:** Spring Security fundamentals, nhóm “Lỗi bảo mật”. Bài học giải thích lỗi xác thực do credential/trạng thái tài khoản và lỗi do cơ sở dữ liệu, LDAP, IdP hoặc dịch vụ phụ thuộc không hoạt động. Ví dụ thực hành dùng Java 17, Spring Boot 3.3.x, Spring Security 6.x và Servlet/Spring MVC; nguyên tắc phân loại cũng dùng được cho các cơ chế danh tính khác, với handler riêng theo giao thức.

## 1. Vấn đề: “không đăng nhập được” không đồng nghĩa “nhập sai mật khẩu”

Khi người dùng đăng nhập thất bại, ứng dụng có thể đã xác minh được rằng credential không hợp lệ; cũng có thể hệ thống **không thể xác minh** vì kho tài khoản hoặc nhà cung cấp danh tính gặp sự cố. Hai tình huống này phải được phân biệt từ nguồn lỗi, dù thông điệp công khai đều cần ngắn gọn và an toàn.

- **Lỗi credential:** username không có sau một truy vấn thành công, password không khớp hash, token hỏng/hết hạn, grant hoặc credential bị từ chối hợp lệ.
- **Lỗi trạng thái tài khoản:** locked, disabled, account expired, credentials expired. Hệ thống biết tài khoản đang không đủ điều kiện đăng nhập; đây không phải lỗi kết nối hay nhất thiết là hành vi sai của người dùng.
- **Lỗi kho tài khoản/dịch vụ danh tính:** mất kết nối database, cạn connection pool, query timeout, LDAP không truy cập được, IdP/token endpoint lỗi 5xx, lỗi mạng khi tải khóa JWKS cần thiết. **Chưa đủ thông tin để kết luận password đúng hay sai.**
- **Lỗi cấu hình/lập trình:** không có `AuthenticationProvider» phù hợp, cấu hình client/redirect/certificate sai, bug mapping user hoặc schema. Lỗi hệ thống cần điều tra, không phải bằng chứng người dùng nhập sai.

**Nguyên tắc:** “không tìm thấy tài khoản” chỉ xảy ra nếu tra cứu **thành công** và trả về rỗng; “không tra cứu được tài khoản” phải được phân loại là lỗi backend. Không biến database timeout thành `UsernameNotFoundException» hoặc `BadCredentialsException» chỉ để khỏi phải xử lý exception.

### Vì sao phân loại đúng quan trọng?

Nếu trả “Sai tên đăng nhập hoặc mật khẩu” khi database đang down, người dùng có thể liên tục thử lại, đổi password hoặc làm tăng bộ đếm lần đăng nhập sai và bị khóa oan. Monitoring cũng có thể tưởng xảy ra credential stuffing thay vì outage. Ngược lại, nếu tiết lộ “username không tồn tại” quá cụ thể, API có thể bị lợi dụng để dò tài khoản (account enumeration). Nếu hệ thống bỏ kiểm tra danh tính khi backend lỗi thì có nguy cơ **fail-open**, nghiêm trọng hơn cả việc đăng nhập gián đoạn.

## 2. Bảng phân biệt theo root cause

| Tình huống đã xác minh | Phân loại nội bộ | Nên kết luận điều gì? | Hành động |
| --- | --- | --- | --- |
| Lookup thành công, không có username | `INVALID_CREDENTIALS» | Danh tính/credential không được chấp nhận | Từ chối; thông điệp bên ngoài giống sai password |
| Lookup có user, password hash không khớp | `INVALID_CREDENTIALS» | Credential không hợp lệ | Từ chối; tăng metric credential failure theo chính sách |
| Account locked / disabled / expired | `ACCOUNT_STATE» | Account không đủ điều kiện | Từ chối; khôi phục qua quy trình được kiểm soát |
| Database connection refused / query timeout | `IDENTITY_DEPENDENCY» | **Chưa thể kiểm tra credential** | Fail closed, cảnh báo outage |
| LDAP server unreachable / bind service timeout | `IDENTITY_DEPENDENCY» | Không đủ bằng chứng về credential | Theo dõi latency/dependency, không khóa oan user |
| IdP trả lỗi giao thức `invalid_grant» | `AUTHENTICATION_REJECTED» hoặc lỗi flow tùy mã | Grant không được chấp nhận; không mặc nhiên là password sai | Phân tích grant/flow, không trả chi tiết nhạy cảm |
| IdP/token endpoint trả `temporarily_unavailable» hay 5xx | `IDENTITY_DEPENDENCY» | Dịch vụ danh tính bị lỗi | Fail closed, giám sát, retry có giới hạn nếu phù hợp |
| JWT hết hạn, chữ ký sai, issuer/audience sai | `INVALID_TOKEN» | Token không hợp lệ | Thường 401 theo giao thức Bearer |
| JWKS endpoint timeout khi cần khóa mới | `IDENTITY_DEPENDENCY» | Chưa chắc token sai | Xem decoder/cache và phụ thuộc đang lỗi |
| `ProviderNotFoundException» vì cấu hình provider sai | `AUTH_CONFIGURATION» | Hệ thống không có provider hỗ trợ | Sửa cấu hình, không đổ lỗi user |
| User đã xác thực nhưng thiếu role/scope | `AUTHORIZATION_DENIED» | Thiếu quyền tài nguyên | Thường 403, không phải login failure |
| Bị rate limit do quá nhiều request | `RATE_LIMITED» | Chính sách chống lạm dụng kích hoạt | Có thể 429, backoff theo chính sách |

Mã HTTP là **hành vi phản hồi**, không phải bằng chứng root cause. Cùng một exception có thể được các filter/handler hoặc gateway chuyển thành status khác nhau; mặc định Spring Security không đảm bảo rằng mọi lỗi database sẽ tự động trở thành 503.

## 3. Cơ chế Spring Security xử lý lỗi

### 3.1 Luồng username/password trong Servlet

```text
HTTP request + credentials
    |
    v
Authentication filter (ví dụ BasicAuthenticationFilter)
    |
    v
AuthenticationManager / ProviderManager
    |
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername(username)
    |      |
    |      +--> Query OK, không có bản ghi:
    |      |       UsernameNotFoundException
    |      |       (mặc định có thể được che thành BadCredentialsException)
    |      |
    |      +--> Query OK, có bản ghi:
    |      |       kiểm tra trạng thái account + PasswordEncoder.matches()
    |      |       thành công / BadCredentialsException / account-status exception
    |      |
    |      +--> Query lỗi:
    |              AuthenticationServiceException /
    |              InternalAuthenticationServiceException
    |
    v
Authentication failure handling tùy filter:
    HTTP Basic -> AuthenticationEntryPoint
    Form login -> AuthenticationFailureHandler
    OAuth2/OIDC -> handler và protocol tương ứng
```

`DaoAuthenticationProvider» dùng `UserDetailsService» để tải `UserDetails», rồi kiểm tra password và trạng thái account. Với username không tồn tại, `AbstractUserDetailsAuthenticationProvider» mặc định bật `hideUserNotFoundExceptions», nên `UsernameNotFoundException» thường được thay bằng `BadCredentialsException» giống password sai. Đây là cách giảm nguy cơ user enumeration; không nên tắt chỉ để hiển thị lỗi chính xác cho frontend.

### 3.2 Exception nào mang ý nghĩa gì?

| Lớp/exception | Diễn giải |
| --- | --- |
| `UsernameNotFoundException» | `UserDetailsService» không tìm thấy username sau một lookup hợp lệ |
| `BadCredentialsException» | Credential bị từ chối; **không chứng minh username có tồn tại** |
| `LockedException», `DisabledException» | Account bị khóa hoặc vô hiệu hóa |
| `AccountExpiredException», `CredentialsExpiredException» | Account hoặc credential đã hết hạn |
| `AuthenticationServiceException» | Lỗi dịch vụ trong quá trình xác thực |
| `InternalAuthenticationServiceException» | Lỗi nội bộ của dịch vụ xác thực, phù hợp để bao bọc một số lỗi backend |
| `ProviderNotFoundException» | Không provider nào hỗ trợ authentication token; thường kiểm tra lại cấu hình |
| `AccessDeniedException» | Lỗi từ chối truy cập ở authorization hoặc bảo vệ khác; **không đồng nghĩa sai password** |

`AuthenticationEntryPoint» xử lý phản hồi yêu cầu xác thực, ví dụ status 401 và `WWW-Authenticate» trong HTTP Basic. `AuthenticationFailureHandler» thường xử lý lỗi form login. `AccessDeniedHandler» xử lý từ chối quyền đối với người dùng đã xác thực; không phải chỗ sửa lỗi kho tài khoản. `ExceptionTranslationFilter» điều phối các ngoại lệ bảo mật trên đường đi của filter chain, nhưng ngoại lệ đã bị một authentication filter bắt và xử lý có thể theo failure handler riêng.

### 3.3 Phân biệt authentication, authorization và lỗi hạ tầng

- **401 Unauthorized:** thường yêu cầu xác thực lại hoặc token không hợp lệ; Basic/Bearer cần giữ HTTP challenge đúng giao thức.
- **403 Forbidden:** đã xác thực nhưng không đủ quyền (hoặc có cơ chế bảo vệ khác như CSRF); không mặc nhiên là login failure.
- **503 Service Unavailable:** có thể được ứng dụng lựa chọn khi dịch vụ xác thực phụ thuộc không hoạt động. Spring Security **không tự động map** mọi `AuthenticationServiceException» thành 503.
- **429 Too Many Requests:** có thể do rate limiting; không khẳng định user/password sai.
- **5xx khác:** lỗi hệ thống hoặc cấu hình; cần kiểm tra handler, logs và root cause.

Với lỗi user, thông điệp công khai nên thống nhất giữa username không tồn tại và sai mật khẩu. Với lỗi hạ tầng, có thể dùng mã lỗi công khai như `identity_service_unavailable» mà không tiết lộ tên database, hostname LDAP, thông tin user, stack trace, hoặc tình trạng tồn tại của tài khoản.

## 4. Ví dụ hoàn chỉnh: một REST API phân biệt lỗi credential và lỗi identity store

Mẫu dưới đây có user `alice» và endpoint bảo vệ `GET /secure». Kho tài khoản giả lập có hai trạng thái: hoạt động bình thường hoặc bị outage. **Không tạo endpoint HTTP để bật/tắt outage**, vì đó là thao tác có thể phá xác thực nếu bị lộ ra ngoài; test sẽ điều khiển trạng thái này bên trong JVM.

### 4.1 Cấu hình Maven

File `pom.xml» cho Java 17 và Spring Boot 3.3.5:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>identity-error-demo</artifactId>
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

### 4.2 Code ứng dụng

Tạo `src/main/java/com/example/identity/IdentityFailureDemoApplication.java»:

```java
package com.example.identity;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class IdentityFailureDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityFailureDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoAccountStore demoAccountStore(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new DemoAccountStore(Map.of("alice", alice));
    }

    @Bean
    UserDetailsService userDetailsService(DemoAccountStore store) {
        return username -> {
            try {
                return store.find(username)
                    .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));
            } catch (StoreUnavailableException cause) {
                // Service hỏng khác với username không tồn tại.
                throw new InternalAuthenticationServiceException(
                    "Account store unavailable", cause);
            }
        };
    }

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint() {
        return (request, response, authError) -> {
            boolean dependencyFailure =
                authError instanceof AuthenticationServiceException;

            response.setStatus(
                dependencyFailure
                    ? HttpServletResponse.SC_SERVICE_UNAVAILABLE
                    : HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());

            if (!dependencyFailure) {
                response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo\"");
            }

            response.getWriter().write(
                dependencyFailure
                    ? "{\"error\":\"identity_service_unavailable\"}"
                    : "{\"error\":\"invalid_credentials\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/health").permitAll()
                .requestMatchers("/secure").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(basic -> basic
                .authenticationEntryPoint(apiAuthenticationEntryPoint))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(apiAuthenticationEntryPoint));

        return http.build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/health")
        String health() {
            return "application running";
        }

        @GetMapping("/secure")
        String secure() {
            return "secure ok";
        }
    }

    static final class DemoAccountStore {
        private final Map<String, UserDetails> accounts;
        private volatile boolean available = true;

        DemoAccountStore(Map<String, UserDetails> accounts) {
            this.accounts = accounts;
        }

        Optional<UserDetails> find(String username) {
            if (!available) {
                throw new StoreUnavailableException();
            }
            return Optional.ofNullable(accounts.get(username));
        }

        void setAvailable(boolean available) {
            this.available = available;
        }
    }

    static final class StoreUnavailableException extends RuntimeException {
        StoreUnavailableException() {
            super("Simulated account-store outage");
        }
    }
}
```

**Vì sao ví dụ phân loại đúng?**

1. `store.find(username)» trả `Optional.empty()» khi lookup **hoàn tất bình thường** nhưng không tìm được account; `UserDetailsService» chuyển thành `UsernameNotFoundException». Provider mặc định có thể che nó thành `BadCredentialsException».
2. Khi backend không phục vụ được, `StoreUnavailableException» được bao bọc thành `InternalAuthenticationServiceException»; nó thuộc họ `AuthenticationServiceException» để nhánh xử lý lỗi dịch vụ nhận diện được.
3. Password sai được `DaoAuthenticationProvider» đối chiếu qua `PasswordEncoder», không cần tự viết so sánh password hay tạo exception giả.
4. `apiAuthenticationEntryPoint» chỉ trả **503 trong nhánh lỗi dịch vụ**, trả **401 và Basic challenge** cho các authentication failure khác. Đây là quy tắc của API demo; với form login/OAuth2/Bearer phải dùng handler tương ứng.
5. `SessionCreationPolicy.STATELESS» giữ các lần thử HTTP Basic độc lập. Không có đường nào cho qua xác thực khi store down, nên ví dụ tuân thủ **fail closed**.
6. Demo dùng password yếu để dễ học; production cần password chính sách mạnh, xử lý secret và repository thực tế. Không dùng `setAvailable» như một API vận hành công khai.

### 4.3 Chạy HTTP thử nghiệm

Máy cần Java 17+ và Maven. Từ thư mục chứa `pom.xml»:

```bash
mvn test
mvn spring-boot:run
```

Dùng cửa sổ terminal khác:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/secure
curl -i -u alice:wrong http://localhost:8080/secure
curl -i -u nobody:wrong http://localhost:8080/secure
curl -i -u alice:demo123 http://localhost:8080/secure
```

| Request | HTTP | Body mong đợi |
| --- | --- | --- |
| `GET /health» | 200 | `application running» |
| `GET /secure» chưa có credential | 401 | `{"error":"invalid_credentials"}» và `WWW-Authenticate: Basic ...» |
| `alice:wrong» | 401 | `{"error":"invalid_credentials"}» |
| `nobody:wrong» | 401 | **Cùng body** với password sai |
| `alice:demo123» | 200 | `secure ok» |

Không thể bật trạng thái store outage bằng curl trong ví dụ; phần test tiếp theo thực hiện việc này trong JVM.

### 4.4 Test tích hợp: credential failure khác dependency failure

Tạo `src/test/java/com/example/identity/IdentityFailureDemoApplicationTest.java»:

```java
package com.example.identity;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityFailureDemoApplicationTest {

    @Autowired MockMvc mvc;
    @Autowired IdentityFailureDemoApplication.DemoAccountStore store;

    @AfterEach
    void resetStore() {
        store.setAvailable(true);
    }

    @Test
    void wrongPasswordAndUnknownUserLookTheSame() throws Exception {
        mvc.perform(get("/secure").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));

        mvc.perform(get("/secure").with(httpBasic("nobody", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void validCredentialWorks() throws Exception {
        mvc.perform(get("/secure").with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("secure ok"));
    }

    @Test
    void storeOutageIsNotBadCredentials() throws Exception {
        store.setAvailable(false);

        mvc.perform(get("/secure").with(httpBasic("alice", "demo123")))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error")
                .value("identity_service_unavailable"));

        mvc.perform(get("/secure").with(httpBasic("nobody", "wrong")))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error")
                .value("identity_service_unavailable"));
    }

    @Test
    void missingCredentialGetsBasicChallenge() throws Exception {
        mvc.perform(get("/secure"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", "Basic realm=\"demo\""));
    }
}
```

Bốn test xác nhận: username không tồn tại và password sai có **cùng phản hồi công khai**; credential đúng thành công; store outage luôn được phân loại **lỗi dịch vụ cho cả user có thật và không có**; request anonymous nhận đúng Basic challenge. Trường hợp outage không được làm controller `/secure» chạy thành công.

Chạy lại `mvn test». Các test cần `spring-boot-starter-test» và `spring-security-test» như file `pom.xml» đã khai báo. Đây là kiểm thử cho demo, không phải bằng chứng mọi dự án OAuth2/LDAP sẽ có mapping HTTP giống hệt.

## 5. Gắn với kho tài khoản thực tế: exception mapping ở ranh giới repository

Thay `DemoAccountStore» bằng JPA/JDBC/LDAP adapter, bảo đảm trường hợp truy vấn không có kết quả và trường hợp không thể truy vấn được được trả về khác nhau. Ví dụ **fragment**, cần repository và mapper của dự án:

```java
@Override
public UserDetails loadUserByUsername(String username) {
    try {
        var account = accountRepository.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        return accountMapper.toUserDetails(account);
    } catch (DataAccessResourceFailureException cause) {
        throw new InternalAuthenticationServiceException(
            "Account database is unavailable", cause);
    }
}
```

`DataAccessResourceFailureException» nằm trong `org.springframework.dao»; đây chỉ là một loại lỗi kết nối. Với database/LDAP client thật cần xác định chính xác các exception được ném, kể cả timeout, transaction, pool exhaustion; đừng bắt tất cả `RuntimeException» rồi coi là sai credential.

**Phản ví dụ 1 — che hỏng database thành username không tồn tại:**

```java
// SAI: query lỗi cũng thành "user không có".
try {
    return repository.findByUsername(username)
        .orElseThrow(() -> new UsernameNotFoundException("Not found"));
} catch (RuntimeException cause) {
    throw new UsernameNotFoundException("Not found");
}
```

**Phản ví dụ 2 — fail-open bằng user giả:** một số ứng dụng xử lý ngoại lệ bằng cách cấp quyền tạm thời. Đây là lỗ hổng nghiêm trọng; nếu chưa xác minh được danh tính thì không phát hành authenticated session/token và không cấp quyền mặc định. Không tạo fallback sang `ROLE_ADMIN» hoặc user cache chưa được đánh giá độ mới của trạng thái khóa/thu hồi.

## 6. Điểm khác biệt của LDAP, OAuth2/OIDC và JWT

### LDAP / Active Directory

Một LDAP bind bị từ chối do credential khác với connection timeout hoặc LDAP server mất kết nối. Mã lỗi LDAP có thể chứa nhiều nguyên nhân; đối chiếu protocol/driver và thực tế ứng dụng trước khi phân loại. Không lấy lỗi mạng rồi báo “mật khẩu sai”. Với LDAP dùng account trạng thái đặc biệt (locked/disabled), cân nhắc bảo vệ thông tin đó khỏi bị dò qua thông báo công khai.

### OAuth2 / OpenID Connect (OIDC)

- `invalid_grant» không nhất thiết do password sai; authorization code có thể hết hạn, bị dùng lại, refresh token bị thu hồi, hoặc tham số flow không hợp lệ.
- `temporarily_unavailable», `server_error», token endpoint timeout hoặc HTTP 5xx thường chỉ tới lỗi dịch vụ, nhưng vẫn cần kiểm tra nguyên nhân/cấu hình.
- Sai redirect URI, client secret, TLS trust hay clock skew có thể làm việc đăng nhập lỗi dù IdP đang chạy bình thường: phân loại lỗi cấu hình.
- Handler lỗi của `oauth2Login»/form login không giống `AuthenticationEntryPoint» của HTTP Basic. Không sao chép mapping 401/503 trong ví dụ sang mọi giao thức.

### JWT Resource Server / JWKS

JWT hết hạn, sai chữ ký, issuer/audience sai thường là **token không hợp lệ** và thường trả 401 Bearer theo protocol. Nếu cần tải key mới nhưng JWKS endpoint timeout thì lỗi có thể là **dịch vụ xác minh không khả dụng**; không thể kết luận token sai chỉ từ timeout. Tuy nhiên decoder có thể dùng JWK cache đã có, nên IdP tạm down không đồng nghĩa mọi request JWT sẽ thất bại. Kiểm tra `JwtDecoder», cache, cấu hình `jwk-set-uri» và thực tế trace.

Khi tùy biến Bearer, giữ `WWW-Authenticate» và error semantics theo RFC 6750; đừng thay bằng Basic challenge hoặc JSON body khiến client không nhận ra `invalid_token» / `insufficient_scope».

## 7. Quan sát và cảnh báo: đo lỗi hạ tầng tách khỏi lỗi người dùng

Nên có các field nội bộ rõ ràng (log/metric/tracing), nhưng không tiết lộ toàn bộ ra client:

| Field | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `category» | `INVALID_CREDENTIALS», `ACCOUNT_STATE», `IDENTITY_DEPENDENCY», `AUTH_CONFIGURATION» | Phân loại lỗi |
| `dependency» | `account-db», `ldap», `oidc-token-endpoint», `jwks» | Xác định nơi hỏng |
| `operation» | `loadUserByUsername», `tokenExchange», `jwtDecode» | Xác định thao tác |
| `exceptionClass / rootCause» | `InternalAuthenticationServiceException», timeout | Hỗ trợ điều tra |
| `traceId/correlationId» | Mã request | Liên kết nhiều dịch vụ |
| `duration / timeoutCount» | Latency, lỗi timeout | Báo động phụ thuộc chậm |
| `responseStatus» | 401, 403, 503 | Kiểm tra mapping công khai |

**Không log password, raw Authorization header, raw token, cookie session, OAuth2 authorization code, private key hoặc dữ liệu cá nhân không cần thiết.** Nếu cần liên kết theo user, dùng định danh nội bộ/băm an toàn theo chính sách bảo vệ dữ liệu, kiểm soát truy cập log và retention.

`DefaultAuthenticationEventPublisher» của Spring Security phát event cho một số exception, trong đó có `BadCredentialsException» và `AuthenticationServiceException». Cơ chế map event có thể cần bổ sung khi exception là subclass. Không dùng **tổng số authentication failures** để suy ra outage: credential thất bại tăng có thể do người dùng hoặc tấn công, trong khi timeout và lỗi kết nối phải có metric riêng.

Về vận hành, trạng thái “ứng dụng trả HTTP 200 cho /health” không chứng minh database/IdP sẵn sàng. Liveness, readiness và dependency health cần được định nghĩa theo kiến trúc; tránh khiến health check gây áp lực quá tải cho identity store.

## 8. Chính sách xử lý an toàn khi identity store không hoạt động

1. **Fail closed:** khi không xác minh được, không tạo phiên đăng nhập thành công, không phát hành token, không dùng user giả.
2. **Bảo toàn ngữ nghĩa lỗi:** phân biệt service failure và invalid credentials trong xử lý nội bộ; không dùng `catch (Exception) -> BadCredentialsException».
3. **Thông báo đúng mục đích:** credential sai có thể yêu cầu kiểm tra lại thông tin; outage nên thông báo dịch vụ tạm thời không khả dụng và hướng dẫn thử lại sau, không bảo người dùng đổi mật khẩu.
4. **Không tự động tăng failed-login count khi backend timeout:** nếu không, outage có thể gây lockout hàng loạt. Vẫn giữ các cơ chế rate limit chống lạm dụng độc lập.
5. **Retry hữu hạn:** timeout rõ ràng, retry/backoff/jitter và circuit breaker theo tính chất từng request; tránh “retry storm” hoặc lặp lại authorization-code exchange/operation một lần.
6. **Không làm lộ account existence:** phản hồi cho username không tồn tại và password sai nên giống nhau; timing cũng cần xem xét.
7. **Không tiết lộ thông tin hạ tầng:** tránh hostname DB, stack trace, tên role, trạng thái user trong response công khai.
8. **Không suy ra lỗi từ HTTP status:** xem exception gốc, điểm xảy ra lỗi và upstream response trước khi quyết định phương án sửa.

## 9. Checklist chẩn đoán sự cố đăng nhập

Khi có báo cáo “đăng nhập thất bại”, hãy kiểm tra theo thứ tự:

1. **Request đi qua đâu?** Xác định security filter chain, authentication filter, `AuthenticationProvider», kho user/IdP/JWKS và khả năng lỗi xảy ra ở proxy/gateway.
2. **Lookup có hoàn tất không?** Thành công nhưng không có bản ghi khác với query timeout/connection refused; không được đoán từ việc response body ghi “bad credentials”.
3. **Có account rồi thì kiểm tra gì?** Password hash, trạng thái locked/disabled/expired, token expiry, issuer/audience và loại authentication phù hợp.
4. **Lỗi thuộc giao thức hay dependency?** OAuth2 error code, LDAP code, trạng thái HTTP của token endpoint, lỗi DNS/TLS/JWKS; kiểm tra cấu hình client.
5. **Mapping phản hồi đã đúng chưa?** 401 có challenge phù hợp, 403 chỉ khi thích hợp, 503 nếu có chính sách lỗi dịch vụ; không trả 200 cho thất bại.
6. **Rủi ro bảo mật nào xuất hiện?** Có account enumeration, logging credential, khóa oan user, tạo authenticated context khi kho user down hay fallback sang quyền mặc định không?
7. **Kiểm thử hồi quy:** unknown user, wrong password, valid login, locked user, DB down với user có và không, thiếu quyền sau login, token lỗi, IdP timeout và header giao thức.

Một bộ kiểm thử tốt không chỉ xác minh status. Nó cần chứng minh rằng **lỗi hạ tầng không biến thành credential failure**, rằng người dùng chưa xác thực không được vào tài nguyên, và rằng phản hồi không tiết lộ thông tin nhạy cảm.

## 10. Ghi nhớ

- **Không có user sau một tra cứu thành công** và **không thể tra cứu user vì backend hỏng** là hai kết quả khác nhau.
- `BadCredentialsException» không chứng minh username tồn tại: Spring Security mặc định có cơ chế che `UsernameNotFoundException» để hạn chế dò tài khoản.
- Dùng `AuthenticationServiceException»/`InternalAuthenticationServiceException» hoặc phân loại nội bộ tương đương cho lỗi phụ thuộc. Trả 503 là một **chính sách ứng dụng cần cấu hình và test**, không phải mặc định mọi phiên bản/cơ chế.
- Phân biệt **authentication 401**, **authorization 403**, **dependency 5xx** và **rate limiting 429** theo root cause. Không dùng `AccessDeniedHandler» để khắc phục lỗi đọc user.
- Với LDAP, OAuth2/OIDC và JWT, giữ đúng semantics của protocol, không bỏ qua JWKS cache, không nhầm `invalid_grant» với sai password trong mọi hoàn cảnh.
- Khi không xác minh được danh tính, hệ thống **fail closed** và ghi nhận sự cố để khôi phục an toàn.

## Tài liệu chính thức

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- AbstractUserDetailsAuthenticationProvider / `hideUserNotFoundExceptions»: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- AuthenticationEntryPoint Java API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html