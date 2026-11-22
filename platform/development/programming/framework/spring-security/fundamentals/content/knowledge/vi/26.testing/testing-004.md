# Giả lập principal không đồng nghĩa với kiểm thử quá trình xác thực thực

## 1. Vấn đề: request được phép truy cập chưa chứng minh đăng nhập đã hoạt động

Trong Spring Security, một bài kiểm thử có thể tạo sẵn **principal** hoặc **Authentication** trong `SecurityContext`, rồi gửi request tới endpoint đã được bảo vệ. Nếu request trả `200 OK`, điều đó thường chứng minh rằng **mã ứng dụng và cơ chế authorization xử lý một danh tính đã được cấp trước**. Nó **không tự chứng minh** rằng hệ thống đã kiểm tra username/password, xác minh chữ ký JWT, đổi authorization code, đọc tài khoản từ database hoặc tạo session đúng cách.

Đây là ranh giới quan trọng trong chủ đề **Kiểm thử** của *Spring Security - fundamentals*:

- **Principal**: danh tính được đại diện trong quá trình xử lý, ví dụ username hoặc `UserDetails`. Principal có thể do test dựng ra.
- **Authentication**: đối tượng thường chứa principal, credentials, authorities và trạng thái xác thực. Trong test, có thể tạo một `Authentication` đã được đánh dấu authenticated mà không cần cung cấp mật khẩu đúng.
- **SecurityContext**: nơi Spring Security giữ `Authentication` cho request/luồng hiện tại. Test helper có thể nạp context trực tiếp.
- **Authentication filter / provider / decoder**: các thành phần đọc credentials thực từ request và xác minh chúng. Những bước này có thể **không chạy** khi test đã cài sẵn `SecurityContext`.

Ví dụ, `@WithMockUser(username = "phantom", roles = "ADMIN")` cho phép test mô phỏng admin **không hề tồn tại trong database**. Một endpoint dùng `hasRole("ADMIN")` có thể trả 200. Đó là một **test phân quyền hợp lệ**, nhưng không phải bằng chứng người dùng `phantom` có thể đăng nhập bằng mật khẩu bất kỳ.

**Mục tiêu học tập:** phân biệt mock identity với xác thực thật; chọn đúng mức kiểm thử cho `@WithMockUser`, `user()`, `httpBasic()`, form login, Bearer JWT, OIDC và WebFlux; xây dựng các test dương/âm qua filter chain; nhận diện false positive; và thiết kế ma trận kiểm thử hoàn chỉnh mà không đòi mỗi bài test phải dựng cả identity provider.

## 2. Phân biệt authentication, authorization và những bằng chứng mà test cung cấp

| Thành phần / hành vi | Câu hỏi nó trả lời | Test nên chứng minh điều gì? |
| --- | --- | --- |
| **Authentication** | Người gọi có đúng là ai họ khai báo không? | Password/credential/token hợp lệ được chấp nhận; sai/hết hạn/bị thu hồi bị từ chối |
| **Authorization** | Danh tính đã xác thực có quyền làm gì? | Có role/scope thì được vào; thiếu quyền thì nhận 403; owner/tenant được kiểm tra |
| **SecurityContext** | Ứng dụng đang thấy Authentication nào? | Principal, authorities và tên người dùng được truyền đúng trong request |
| **Session / token lifecycle** | Danh tính được lưu/khôi phục thế nào giữa các request? | Login/logout/timeout/rotation/revocation vận hành đúng |
| **HTTP security integration** | Request thật đi qua các filter và entry point thế nào? | 401, 403, redirect, cookie, CSRF, WWW-Authenticate, security headers đúng thiết kế |

Một test không thể khẳng định nhiều hơn những gì nó thật sự đi qua:

```text
Test A: @WithMockUser("admin")
    |
    v
SecurityContext được dựng sẵn
    |
    v
AuthorizationFilter / controller
    |
    v
200 OK
=> Có bằng chứng cho QUY TẮC PHÂN QUYỀN trên danh tính mock
=> Chưa có bằng chứng cho mật khẩu, UserDetailsService, login, JWT decoder


Test B: request thật kèm Authorization: Basic ...
    |
    v
BasicAuthenticationFilter
    |
    v
AuthenticationManager -> AuthenticationProvider
    |
    v
UserDetailsService + PasswordEncoder
    |
    v
SecurityContext -> AuthorizationFilter -> controller
    |
    v
200 / 401 / 403
=> Kiểm tra được pipeline HTTP Basic được cấu hình trong test


Test C: request Bearer token được ký thật
    |
    v
BearerTokenAuthenticationFilter
    |
    v
JwtDecoder: signature + validators (issuer/time/audience nếu có cấu hình)
    |
    v
JwtAuthenticationConverter -> authorization
=> Kiểm tra được các bước verify mà test thực sự cấu hình/thi hành
```

**Lưu ý:** `MockMvc` vẫn là môi trường Servlet mô phỏng, không mở cổng HTTP thật. Khi `MockMvc` được cấu hình với Spring Security filters, nó vẫn có thể gọi xác thực qua `BasicAuthenticationFilter` và provider thực của application context. Test với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client đi qua một HTTP listener thật hơn, nhưng ngay cả nó cũng không chứng minh được tích hợp với IdP/DB production nếu test vẫn dùng stub hoặc in-memory data.

## 3. Những helper thường bị hiểu nhầm

| Công cụ Spring Security Test | Nó làm gì? | Nó **không** tự kiểm thử |
| --- | --- | --- |
| `@WithMockUser` | Tạo `SecurityContext` chứa user, role hoặc authority đã định | Tìm user trong DB, hash/matches password, HTTP login |
| `@WithUserDetails("alice")` | Dùng `UserDetailsService` lấy user và dựng `Authentication` cho test | So khớp password, kiểm header Basic hoặc form login end-to-end |
| `@WithSecurityContext` | Factory do bạn viết tạo một security context tùy ý | Các bước xác thực mà factory không gọi |
| `mvc.perform(...with(user("x")))` | Gắn user vào request cho `MockMvc` | Sự tồn tại của user, xác minh credentials |
| `mvc.perform(...with(authentication(auth)))` | Gắn một `Authentication` do test cung cấp | Bằng chứng provider chấp nhận nó từ HTTP |
| `mvc.perform(...with(jwt()))` | Cấp `JwtAuthenticationToken` mock cho authorization | Chữ ký JWT, `iss`, `aud`, `exp`, JWKS và decoder thật |
| `mvc.perform(...with(oauth2Login()))` | Tạo trạng thái OAuth2 login mock cho client test | Redirect, state/nonce, code exchange, token endpoint thực |
| `mvc.perform(...with(httpBasic(user, pass)))` | Đặt header `Authorization: Basic ...` vào request | **Có thể** kiểm tra provider nếu security filters thực sự được nối và không cài identity mock thay thế |
| `mvc.perform(...with(csrf()))` | Thêm CSRF token test để vượt kiểm tra CSRF theo cấu hình | Quy trình server cấp token/cookie/HTML form và client gửi token thật |

Đọc bảng theo hai chiều: mock principal **không sai**; đó là công cụ tốt khi mục tiêu chỉ là policy hoặc controller. Sai lầm nằm ở việc mô tả một test `@WithMockUser` là “đã kiểm thử đăng nhập, password encoder, JWT validation và toàn bộ authentication flow”.

### 3.1. `@WithMockUser`

Ví dụ:

```java
@Test
@WithMockUser(username = "administrator", roles = "ADMIN")
void mockAdminMayReadAdminEndpoint() throws Exception {
    mvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
}
```

Annotation tạo user mock với `ROLE_ADMIN`. Username có thể chưa từng tồn tại trong database; password mặc định của helper không được đem đi kiểm tra bằng provider. Nếu `@WithMockUser(roles = "ADMIN")`, giá trị role được Spring Security Test chuyển thành authority `ROLE_ADMIN` theo quy ước mặc định. Nếu bạn cần authority có tên chính xác như `SCOPE_reports.read`, dùng `authorities = "SCOPE_reports.read"`.

### 3.2. `with(user(...))`

Ví dụ:

```java
mvc.perform(get("/api/admin")
        .with(user("ghost").roles("ADMIN")))
        .andExpect(status().isOk());
```

`user(...)` tạo identity cho request. Nó **không chứng minh** tài khoản `ghost` có trong `UserDetailsService` hay mật khẩu của tài khoản đó đúng. Hãy dùng nó khi đang kiểm tra việc endpoint xử lý user/role đã xác thực.

Các helper cần security context được tích hợp với `MockMvc`. Cấu hình thủ công thường dùng:

```java
mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

Đoạn trên là fragment dành cho một test class có `WebApplicationContext context` và import tương ứng. `@SpringBootTest` + `@AutoConfigureMockMvc` thường tự cấu hình filter chain; nếu `@AutoConfigureMockMvc(addFilters = false)` hoặc `standaloneSetup(...)` không đăng ký security filters, kết quả có thể bỏ qua bảo vệ.

### 3.3. `@WithUserDetails`

`@WithUserDetails("alice")` gọi một `UserDetailsService` thực hoặc bean được thay bằng mock để lấy principal, rồi tạo context đã xác thực. Nó có thể phát hiện user không tồn tại hoặc mapping authorities sai từ loader đã dùng, nhưng **không đưa password qua `AuthenticationManager`/`PasswordEncoder.matches(...)`**. Vì thế vẫn cần test credential tốt/sai ở tầng authentication.

### 3.4. `with(httpBasic(...))` là request credential, không phải identity đã cấp

Khác với `with(user(...))`, helper HTTP Basic chủ yếu ghi header:

```text
Authorization: Basic YWxpY2U6Y29ycmVjdC1wYXNzd29yZA==
```

Header chỉ mã hóa Base64 `alice:correct-password`; **nó không xác minh ai cả**. Nếu `BasicAuthenticationFilter`/`AuthenticationManager` thật đang chạy trong filter chain, Spring Security sẽ đọc header và kiểm tra credential bằng provider. Nếu không chạy filters, một test trả 200 vẫn không thể dùng làm bằng chứng authentication.

Không kết hợp `@WithMockUser` với `with(httpBasic("alice", "wrong"))` rồi cho rằng 401/200 phản ánh kiểm tra mật khẩu: identity mock có thể làm sai tiền đề. Tách test mock authorization và test Basic credential thành các phương thức riêng, không giữ security context giả trên request kiểm tra đăng nhập.

## 4. Ví dụ runnable Java 17+: mô phỏng user và kiểm tra HTTP Basic thật

Dự án dưới đây dùng **Spring Boot 3.5.7, Spring Security 6.x, Spring MVC, Maven và Java 17+**. Nó cố ý có user lưu in-memory để test dễ lặp lại; các bước xác thực qua HTTP Basic vẫn phải đi qua provider. Hệ thống production nên dùng `PasswordEncoder` thích hợp và kho user/secret an toàn, không dùng `{noop}`.

### 4.1. Mục tiêu test

- `GET /api/me` yêu cầu authenticated, trả username đang đăng nhập.
- `GET /api/admin` yêu cầu `ROLE_ADMIN`.
- Tài khoản thực trong `UserDetailsService`: `alice`/`correct-password` có USER, `administrator`/`admin-password` có ADMIN.
- `phantom` không tồn tại trong user store. Với `@WithMockUser`, `phantom` vẫn truy cập `/api/admin` được nếu gán ADMIN vì test đã dựng danh tính.
- Request HTTP Basic với `phantom` hoặc mật khẩu sai bị **401** khi chạy filter chain thật.
- Request Basic đúng của `alice` vào `/api/admin` bị **403**, request đúng của `administrator` được **200**.

### 4.2. Cấu trúc

```text
security-test-boundary/
├── pom.xml
└── src/
    ├── main/java/demo/SecurityTestBoundaryApplication.java
    └── test/java/demo/
        ├── AuthenticationBoundaryMvcTest.java
        └── LiveHttpAuthenticationTest.java
```

### 4.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-test-boundary</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

### 4.4. `src/main/java/demo/SecurityTestBoundaryApplication.java`

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityTestBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestBoundaryApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}correct-password")
                        .roles("USER")
                        .build(),
                User.withUsername("administrator")
                        .password("{noop}admin-password")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }

        @GetMapping("/api/admin")
        Map<String, String> admin(Authentication authentication) {
            return Map.of(
                    "username", authentication.getName(),
                    "result", "allowed");
        }
    }
}
```

Các điểm cần hiểu:

1. `UserDetailsService` thực sự tồn tại trong application context; chỉ có `alice` và `administrator`. `phantom` chỉ được tạo bởi test mock.
2. `httpBasic` cấu hình `BasicAuthenticationFilter` và cơ chế xác thực username/password, với provider phù hợp. Khi request có Basic header, Spring Security giải mã và kiểm credentials.
3. `"{noop}"` được dùng **chỉ trong demo** để tránh phải tạo hash cố định. Production sử dụng hash có salt/chính sách nâng cấp mật khẩu phù hợp như BCrypt/Argon2 và secrets store.
4. `hasRole("ADMIN")` kiểm authority `ROLE_ADMIN`. Account `alice` chỉ có `ROLE_USER`, nên một request đã xác thực của Alice vào `/api/admin` bị 403.
5. Không có form login và không có authentication controller tự viết. Cấu hình giúp các test tập trung vào Basic và authorization. Demo chỉ dùng GET nên không yêu cầu thay đổi CSRF.

### 4.5. Test `MockMvc`: một suite, hai kiểu bằng chứng khác nhau

Tạo `src/test/java/demo/AuthenticationBoundaryMvcTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class AuthenticationBoundaryMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "phantom", roles = "ADMIN")
    void mockIdentityCanPassAuthorizationWithoutAnAccount() throws Exception {
        mvc.perform(get("/api/admin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("phantom"))
                .andExpect(jsonPath("$.result").value("allowed"));
    }

    @Test
    void requestPostProcessorAlsoInjectsIdentity() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(user("ghost").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("ghost"));
    }

    @Test
    void missingCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void nonExistentUserCannotAuthenticateWithBasic() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("phantom", "any-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejectedByAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordAuthenticatesOrdinaryUser() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "correct-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGetsForbidden() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "correct-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void realAdminCredentialsAllowAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("administrator", "admin-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("administrator"));
    }
}
```

**Phân tích bằng chứng của bộ test trên:**

| Test | Luồng có ý nghĩa | Kết luận hợp lệ |
| --- | --- | --- |
| `@WithMockUser("phantom", ADMIN)` | SecurityContext đã được cấp quyền | Rule authorization chấp nhận ADMIN; **không** chứng minh login |
| `with(user("ghost").roles("ADMIN"))` | Mock principal trên request | Controller nhận principal mock và policy cho phép |
| Không credentials | Entry point của chuỗi HTTP | Endpoint không cho anonymous |
| Basic `phantom:any-password` | HTTP Basic + provider + user store | User không tồn tại bị 401 |
| Basic `alice:wrong-password` | HTTP Basic + provider + password check | Password sai bị 401 |
| Basic `alice:correct-password` | HTTP Basic + provider + controller | Credentials đúng xác thực vào endpoint authenticated |
| Basic Alice đến `/api/admin` | Xác thực thành công rồi phân quyền | Đã đăng nhập nhưng thiếu role nhận 403 |
| Basic administrator đến `/api/admin` | Xác thực và phân quyền đều thành công | User hiện có với password đúng/ADMIN được 200 |

`@AutoConfigureMockMvc(addFilters = true)` giữ filters trong test. Nếu đổi thành `addFilters = false`, các assertions về 401/403 có thể thay đổi, và không được tiếp tục gọi chúng là test authentication. Nên giữ mỗi test authentication **không có `@WithMockUser` hoặc `with(user())`**.

### 4.6. Kiểm tra HTTP qua cổng thực (tầng cao hơn `MockMvc`)

`MockMvc` không mở socket. Nếu cần xác thực đường HTTP thực, tạo `src/test/java/demo/LiveHttpAuthenticationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpAuthenticationTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void wrongPasswordIs401OverActualHttp() {
        ResponseEntity<String> response = client
                .withBasicAuth("alice", "bad-password")
                .getForEntity("/api/me", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void validCredentialsAre200OverActualHttp() {
        ResponseEntity<String> response = client
                .withBasicAuth("alice", "correct-password")
                .getForEntity("/api/me", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("\"username\":\"alice\"");
    }

    @Test
    void ordinaryUserIs403OverActualHttp() {
        ResponseEntity<String> response = client
                .withBasicAuth("alice", "correct-password")
                .getForEntity("/api/admin", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }
}
```

`TestRestTemplate` được Spring Boot Test tự cấu hình trong `RANDOM_PORT` context và gọi HTTP qua port do server cấp. Đây là **HTTP thật đến server test** với in-memory users. Nó vẫn không phải là xác minh tích hợp với DB production, reverse proxy, TLS termination hay identity provider bên ngoài. Test ở localhost dùng HTTP để dễ chạy, không gửi Basic credentials qua HTTP công khai trong triển khai thật.

### 4.7. Lệnh biên dịch, chạy test và thử bằng `curl`

Chạy tại thư mục gốc chứa `pom.xml`, yêu cầu Java 17+ và Maven:

```bash
mvn -q test
mvn -q -DskipTests package
java -jar target/security-test-boundary-0.0.1-SNAPSHOT.jar
```

Terminal thứ hai:

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong-password http://localhost:8080/api/me
curl -i -u alice:correct-password http://localhost:8080/api/me
curl -i -u alice:correct-password http://localhost:8080/api/admin
curl -i -u administrator:admin-password http://localhost:8080/api/admin
curl -i -u phantom:any-password http://localhost:8080/api/admin
```

Các status kỳ vọng lần lượt là **401, 401, 200, 403, 200, 401**. Request `GET /api/me` có credentials đúng trả JSON chứa `"username":"alice"`; request admin đúng có `"result":"allowed"`. Dấu cách/thứ tự JSON, header và body lỗi có thể khác theo phiên bản/config; hãy kiểm tra status và các field thực sự cần thiết. Không mô tả output của Maven là “đã chạy qua” nếu chưa thực thi trên môi trường có Maven/Java.

## 5. Kiểm thử method security: mock principal là công cụ đúng mục tiêu

Nếu mục tiêu là chứng minh `@PreAuthorize` bảo vệ service, mock principal là cách cô lập chính sách rất hữu ích. Ví dụ **fragment service** trong ứng dụng đã bật `@EnableMethodSecurity`:

```java
@Service
public class BillingService {

    @PreAuthorize("hasAuthority('INVOICE_APPROVE')")
    public String approve(long invoiceId) {
        return "approved-" + invoiceId;
    }
}
```

Một method-security test có thể dùng:

```java
@Test
@WithMockUser(authorities = "INVOICE_APPROVE")
void approverCanApprove() {
    assertThat(billingService.approve(42L)).isEqualTo("approved-42");
}

@Test
@WithMockUser(roles = "USER")
void readerCannotApprove() {
    assertThatThrownBy(() -> billingService.approve(42L))
            .isInstanceOf(AccessDeniedException.class);
}
```

Đây là **fragments**, cần các imports và context thật chứa service/proxy đã kích hoạt method security. Những test này chứng minh policy method trước một `Authentication` được cấp, không chứng minh password, login hay user lookup. Đồng thời cần kiểm tra truy cập đối tượng/tenant trong service nếu `invoiceId` là dữ liệu phân quyền: role `INVOICE_APPROVE` có thể chưa đủ để phê duyệt bất kỳ hóa đơn nào.

Cần bảo đảm lời gọi đi qua Spring proxy; self-invocation trong cùng bean có thể bỏ qua AOP proxy và khiến `@PreAuthorize` không chạy. Test nên gọi bean Spring quản lý, không tạo `new BillingService()` thủ công rồi suy ra bảo vệ thật.

## 6. JWT Resource Server: `jwt()` helper bỏ qua xác minh token thực

Trong Spring Security Test cho Servlet, `with(jwt())` (hoặc `with(authentication(jwtAuthenticationToken))`) cấp `JwtAuthenticationToken` mock vào request. Các API này **rất phù hợp** để test role/scope trong controller và authorization nhưng không tự chạy:

- Kiểm tra chữ ký JWT hoặc thuật toán ký;
- Tải JWK, xử lý key rotation hoặc tin issuer;
- Kiểm `iss`, `aud`, `exp`, `nbf` theo validator thực;
- Phân tích Bearer header bị hỏng từ client;
- Xác minh converter/claim mapping thật nếu chính test tự gán authorities.

### 6.1. Ví dụ test authorization với JWT mock (fragment)

Giả sử một API Resource Server đã cấu hình endpoint `/api/reports` với policy `hasAuthority("SCOPE_reports.read")`:

```java
mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
```

Fragment cần import `jwt` từ `SecurityMockMvcRequestPostProcessors` và `SimpleGrantedAuthority`, cùng endpoint/config phù hợp. Test này **không tạo token được ký**. Nó chỉ kiểm rằng endpoint cho phép một `JwtAuthenticationToken` đã có `SCOPE_reports.read`.

Nếu converter thật phải lấy `app_roles` từ claims rồi chuyển thành `ROLE_ADMIN`, test mock gán trực tiếp `ROLE_ADMIN` sẽ **không phát hiện lỗi converter**. Hãy tách rõ kiểm thử chuyển claims sang authorities (unit test converter) và kiểm thử authorization sử dụng authority.

### 6.2. Kiểm tra Bearer token đi qua pipeline như thế nào?

Để kiểm thử **decoder và validation thật** của Resource Server:

1. Dùng request HTTP hoặc MockMvc kèm header `Authorization: Bearer <token>` (dữ liệu token được sinh bằng test fixture ký thực).
2. Bảo đảm `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider` và `JwtDecoder` cấu hình phù hợp thực sự tham gia request.
3. Dùng khóa public/private test riêng, thuật toán ký được phép và issuer/audience trong fixture.
4. Gửi các token: hợp lệ, signature sai, issuer sai, audience sai, `exp` quá hạn, `nbf` tương lai, scope thiếu.
5. Khẳng định 401 cho token không hợp lệ, 403 khi token xác thực thành công nhưng thiếu quyền, và 200 khi đạt đủ điều kiện. Với Bearer token, còn kiểm tra `WWW-Authenticate` và mã lỗi theo giao thức.

Nếu thay `JwtDecoder` bằng `@MockitoBean JwtDecoder` và cấu hình nó luôn trả `Jwt` hợp lệ, test đó kiểm tra đường filter/integration với **mock decoder**, không xác minh chữ ký hoặc validator thật. Dùng mock decoder có ích cho test riêng nhưng cần ghi rõ phạm vi bằng chứng.

**Cảnh báo:** `jwt().jwt(jwt -> jwt.claim("roles", ...))` hoặc fixture `Jwt.withTokenValue(...)` có thể chứa claims bạn tự đặt; điều này không chứng minh claims có nguồn gốc từ issuer tin cậy. Không gọi mock token là “đã xác minh thật”.

### 6.3. JWT và authentication success có nhiều tầng

Một JWT response 200 có thể là false positive nếu test:

- Cài sẵn `Authentication` qua `jwt()` nên decoder không được gọi.
- Gán authorities trực tiếp thay vì chạy converter mà production sử dụng.
- Tắt security filters hoặc bỏ qua `SecurityWebFilterChain` tương ứng.
- Mock toàn bộ provider/decoder mà quên có test validation riêng.
- Chỉ kiểm 200, không thử token thiếu/sai/hết hạn hoặc quyền thiếu.

Vì vậy, trong báo cáo kiểm thử cần ghi rõ **token mock**, **decoder mock**, hay **token ký thật và decoder thật**.

## 7. OAuth2 Login/OIDC: mock user không kiểm tra giao thức đăng nhập

Các helper như `oauth2Login()`, `oidcLogin()` (Servlet MockMvc) tạo `OAuth2AuthenticationToken`/`OidcUser` và dữ liệu liên quan cho test authorization/controller. Điều đó không chứng minh được toàn bộ luồng Authorization Code/OIDC:

```text
Trình duyệt -> /oauth2/authorization/{registrationId}
           -> redirect tới identity provider
           -> callback với code và state
           -> kiểm state, token exchange, ID token, nonce
           -> load user/claims, map authorities
           -> tạo session, redirect về ứng dụng
```

Một test `with(oidcLogin())` có thể cho phép controller đọc claim `email` hoặc `sub` mà không có request nào tới token endpoint hoặc user-info endpoint. Đây là kiểm thử hợp lý cho code xử lý principal **sau đăng nhập**, không chứng minh chống CSRF ở OAuth2 state, nonce replay, issuer, client credentials, redirect URI hoặc mapping provider thật.

**Thiết kế test hợp lý:**

- **Controller/authorization**: dùng `oauth2Login()`/`oidcLogin()` với claims/authorities mock.
- **Mapping login**: unit test `GrantedAuthoritiesMapper`, `OAuth2UserService`, `OidcUserService` với dữ liệu hợp đồng.
- **Giao thức**: integration test với IdP giả lập nhưng đáp ứng discovery, authorization, token, JWKS và user-info nếu dùng; kiểm redirect, state/nonce, cookies/session và lỗi.
- **End-to-end thực tế**: môi trường staging với nhà phát hành/registration config tương đương production, được phép truy cập và có test account riêng.

Không sử dụng mock OAuth2 login làm bằng chứng duy nhất rằng SSO đang hoạt động đúng.

## 8. Authentication flow thực trong form login

Khi ứng dụng dùng `formLogin`, mock principal cũng bỏ qua các bước quan trọng:

- `POST /login` phải đi qua `UsernamePasswordAuthenticationFilter` theo matcher/config.
- `AuthenticationManager` chọn `AuthenticationProvider`, gọi `UserDetailsService` và kiểm password qua encoder.
- Cấu hình CSRF có thể yêu cầu token khi POST; test phải cung cấp token phù hợp.
- Đăng nhập thành công có thể thay session ID, lưu security context, thực hiện success handler/redirect.
- Đăng nhập thất bại phải gọi failure handler, không được lưu authenticated session.

Ví dụ **fragment cho một ứng dụng đã bật `formLogin` và user store phù hợp**:

```java
mvc.perform(formLogin().user("alice").password("correct-password"))
        .andExpect(authenticated().withUsername("alice"));

mvc.perform(formLogin().user("alice").password("wrong-password"))
        .andExpect(unauthenticated());
```

Đoạn này cần các static imports `formLogin` (`SecurityMockMvcRequestBuilders`), `authenticated`/`unauthenticated` (`SecurityMockMvcResultMatchers`), và `MockMvc` đã nối Spring Security filters. `formLogin()` tạo POST theo login endpoint mặc định và kèm token CSRF test phù hợp; nếu ứng dụng tùy biến login URL/parameter names, cần cấu hình request builder tương ứng.

Khác với `@WithMockUser`, request `formLogin()` kiểm cơ chế login ở `MockMvc` khi filters/provider thực chạy. Tuy nhiên response đúng chưa chứng minh form ngoài trình duyệt gửi token/cookie/redirect đúng hoặc môi trường production dùng cùng auth provider.

## 9. CSRF, session và logout: mock context cũng có giới hạn

Một request có `@WithMockUser` và `with(csrf())` có thể đi qua endpoint POST và được authorize. Đây là bằng chứng rằng **filter và policy được cấu hình trong test chấp nhận một CSRF token test hợp lệ**, không chứng minh:

- Trang/form thật phát token đúng;
- Cookie hoặc header CSRF từ browser đi qua reverse proxy đúng;
- Session ID được rotate sau login;
- Logout xóa cookie/session và chặn dùng lại credentials/token theo thiết kế;
- Session timeout hoặc concurrent-session control hoạt động trong môi trường nhiều node.

Hãy bổ sung các HTTP-flow test khi chính những hành vi đó là yêu cầu. Với API Bearer token **không sử dụng cookie authentication**, CSRF có thể có cấu hình khác; đừng tắt CSRF cho mọi hệ thống chỉ vì “API dùng JSON”.

Một nguyên tắc bảo vệ dữ liệu: không log raw `Authorization`, cookie, password, access token, refresh token hoặc thông tin phiên trong kết quả test/snapshot. Khi test thất bại, log nên giúp xác định mã lỗi và bước hỏng mà không làm lộ credentials.

## 10. WebFlux/reactive: cùng phân biệt, khác test API

Trong WebFlux, HTTP pipeline dùng `SecurityWebFilterChain`, `AuthenticationWebFilter` và `ReactiveAuthenticationManager` thay cho Servlet `SecurityFilterChain` và các servlet filter. Test thường dùng `WebTestClient` với Spring Security test support:

- `mutateWith(mockUser("alice"))`: dựng reactive security context với user mock.
- `mutateWith(mockJwt())`: cung cấp JWT mock cho authorization.
- Request với header `Authorization: Basic ...` hoặc `Authorization: Bearer ...` đi qua authentication pipeline **nếu** `WebTestClient` đã bind đúng ứng dụng/security config.
- `@WithMockUser` có thể hữu ích khi test reactive security; vẫn không kiểm credential thật.

**Fragment minh họa cho WebFlux đã có `WebTestClient client` và policy `hasRole("ADMIN")`:**

```java
client.mutateWith(mockUser("phantom").roles("ADMIN"))
        .get().uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
```

Đây là kiểm thử authorized principal giả lập; nó không xác nhận `phantom` có thể login vào reactive application. Fragment khác cho JWT:

```java
client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
        .get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk();
```

Các fragment cần imports `mockUser`/`mockJwt` từ `SecurityMockServerConfigurers` và application đã áp Spring Security lên `WebTestClient`, không chạy độc lập. `mockJwt()` không xác minh chữ ký JWT. Khi cần kiểm converter JWT reactive, kiểm `ReactiveJwtAuthenticationConverter`/adapter đúng loại và thêm integration test với `ReactiveJwtDecoder` thật. Đừng nhầm filter và extension point Servlet với reactive.

## 11. Ma trận kiểm thử tối thiểu theo mức tin cậy

Không phải mọi tính năng đều cần chạy IdP thật trong mỗi test. Nên chia thành các lớp có mục tiêu rõ ràng:

| Lớp kiểm thử | Công cụ thường dùng | Phạm vi được chứng minh | Không đủ để kết luận |
| --- | --- | --- | --- |
| Unit test converter / provider | JUnit, mock repository, encoder/validator thật khi cần | Logic biến credential/claim thành kết quả và lỗi theo input | HTTP filter/redirect/session |
| Controller và policy test | `@WithMockUser`, `user()`, `jwt()`, `MockMvc` | Authorization, response, principal mapping của controller | Password, token signature, login protocol |
| HTTP authentication test trong Spring context | `@SpringBootTest` + `@AutoConfigureMockMvc` + `httpBasic()` / `formLogin()` | Filter, provider/encoder/user store được cấu hình trong context, 401/403/200 | Socket, reverse proxy, external IdP thật |
| HTTP integration test qua port | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate`/HTTP client | Request qua web server thật của test app | Hạ tầng production nếu vẫn dùng DB/IdP giả |
| External identity integration | Local signed JWT + real decoder, hoặc IdP stub đúng giao thức | Signature/issuer/audience/claims/redirect tùy mức giả lập | Đúng tuyệt đối với cấu hình issuer production |
| Staging E2E | Client thật, TLS, IdP/test account, network/proxy/session | Luồng từ client qua hạ tầng dự kiến | Mọi tình huống tải lớn hoặc thay đổi production |

Trong mỗi lớp, luôn test **đường thất bại**. Authentication không chỉ là chuyện “credentials đúng trả 200”; thiếu, sai, bị khóa, hết hạn, malformed, token sai issuer/audience và thiếu quyền là những ca có giá trị bảo mật cao.

### 11.1. Ma trận status cho API HTTP Basic trong ví dụ

| Người gọi và request | Expected | Bước quyết định |
| --- | --- | --- |
| Anonymous `GET /api/me` | 401 | Chưa xác thực |
| Username không tồn tại + bất kỳ password | 401 | User lookup / provider |
| `alice` + password sai | 401 | Password check |
| `alice` + password đúng tới `/api/me` | 200 | Authentication thành công |
| `alice` + password đúng tới `/api/admin` | 403 | Authorization thiếu ADMIN |
| `administrator` + password đúng tới `/api/admin` | 200 | Authentication + authorization |
| `@WithMockUser("phantom", ADMIN)` tới `/api/admin` | 200 trong test mock | Context giả lập, **không có credential validation** |

Kết quả cuối cùng của một hệ thống có thể là redirect 302 thay vì 401 nếu form login, hoặc có header Bearer challenge khi JWT; không áp một bảng status cho mọi cơ chế xác thực mà bỏ qua cấu hình.

## 12. Những false positive nguy hiểm và cách phát hiện

1. **Test toàn bộ controller với `@WithMockUser` rồi báo “login hoạt động”.** Thêm test request Basic/form/JWT qua filter chain và các ca sai credentials.
2. **Tạo user mock có role ADMIN không tồn tại trong DB.** Kết quả 200 có ý nghĩa cho authorization; kiểm user store/provider ở test riêng.
3. **Đổi `@AutoConfigureMockMvc(addFilters = false)` để tránh 403.** Test có thể bỏ toàn bộ security filters; sửa cấu hình test để giữ filters và cấp CSRF nếu endpoint cần.
4. **Dùng `MockMvcBuilders.standaloneSetup` rồi tưởng Spring Security đã được tích hợp.** Phải đăng ký security filters/configurer khi muốn kiểm pipeline; cân nhắc `webAppContextSetup(...).apply(springSecurity())`.
5. **Gán `ROLE_ADMIN` bằng `jwt().authorities(...)` rồi kết luận claim role mapping đúng.** Test riêng converter trên claims thật của issuer, sau đó test JWT qua decoder.
6. **Mock `JwtDecoder` luôn trả token hợp lệ và tuyên bố chữ ký JWT đã được kiểm.** Dùng real decoder + signed fixtures + invalid signature/issuer/audience tests.
7. **Dùng `@WithUserDetails` rồi cho rằng đã so khớp mật khẩu.** Helper tải UserDetails và dựng context; bổ sung test với credentials sai.
8. **Không có test anonymous/invalid credentials.** Một route bị `permitAll()` ngoài ý muốn có thể làm happy-path test vẫn pass.
9. **Chỉ assert response JSON, không assert 401/403/302 hoặc header.** Dễ bỏ sót authentication entry point, CSRF và Bearer challenge.
10. **Chạy `@WithMockUser` trên test thread rồi gọi server thật bằng HTTP client.** SecurityContext trong thread test không tự truyền sang server thread qua network; phải gửi credentials trên request.
11. **Không kiểm tra session giữa các request.** Một request mock authenticated không chứng minh login tạo session, logout vô hiệu hóa session.
12. **Trộn role và scope trong test.** `roles = "ADMIN"` cấp `ROLE_ADMIN` theo mặc định, không tự cấp `SCOPE_admin`; policy `hasAuthority(...)` cần chuỗi chính xác.
13. **Tạo custom AuthenticationProvider nhưng chỉ test controller đã mock context.** Các lỗi `supports()`, hash password, exception/lock state chưa hề được gọi.
14. **Cho qua test vì 200 nhưng security filter chain chưa khớp request.** Test phải xác minh matcher, fallback, nhiều chain và thứ tự chain. Kết quả trả 200 có thể đến từ endpoint không bảo vệ.
15. **Không kiểm tra disabled/locked/password expired users.** Những trạng thái account có thể bị giả lập bỏ qua hoàn toàn; phải kiểm provider và user store thật.
16. **Thấy 401 của request sai và suy rằng signature đã được kiểm.** 401 có thể đến từ thiếu Bearer header hoặc mock decoder; kiểm chính xác phần code được chạy.

## 13. Chiến lược test cân bằng cho đội phát triển

Với một feature security mới, áp dụng quy trình:

1. **Viết rõ “đối tượng thực cần kiểm”.** Policy authorization, mật khẩu, JWT signature, mapping role, CSRF, session hay SSO redirect? Không dùng tên “security test” chung chung.
2. **Dùng mock principal cho business logic/authorization.** Như vậy test nhanh, dễ mô tả quyền và ít phụ thuộc.
3. **Có ít nhất một đường authentication qua request cho mỗi cơ chế đang hỗ trợ.** HTTP Basic cần đúng/sai/thiếu credentials; form login cần success/failure; JWT cần valid/invalid signature/time/issuer/audience.
4. **Giữ security filters trong integration tests.** Kiểm test context được lắp cùng `SecurityFilterChain` và các provider/decoder relevant.
5. **Tách mock dependency với integration dependency.** Nếu `UserDetailsService`, `AuthenticationManager` hoặc `JwtDecoder` đã bị mock, báo rõ phần nào không được kiểm thật.
6. **Kiểm status và hậu quả.** Với request từ chối, xác nhận không tạo session hoặc cập nhật state; không chỉ nhìn mã HTTP.
7. **Kiểm quyền trên đối tượng.** Role hợp lệ chưa chứng minh có thể đọc record của tenant khác; làm test IDOR/BOLA và owner checks.
8. **Giữ bộ test có thể lặp lại.** User fixtures, secrets và signing keys dành riêng cho test; không phụ thuộc tài khoản production; chú ý clock khi test token expiration.
9. **Đặt tên test phản ánh bằng chứng.** `mockPrincipalCanReadAdminEndpoint`, `wrongPasswordRejectedByBasicAuth`, `invalidSignatureRejectedByDecoder` — tên tự nói phạm vi.
10. **Rà lại khi đổi cơ chế.** Chuyển Basic sang JWT phải thay nhóm test credential bằng Bearer/decoder, không giữ `@WithMockUser` như bằng chứng đủ cho cơ chế mới.

### Trước khi merge, hỏi

- Mock user được tạo ở đâu? Có bài test nào thật sự chạy authentication filter/provider hoặc JWT decoder?
- Nếu thay password thật thành password sai, test nào phải fail? Nếu không có test nào, chưa kiểm tra password flow.
- Nếu xóa user ở DB, test nào phát hiện? Nếu vẫn toàn bộ pass, chưa kiểm user lookup/integration.
- Nếu token hết hạn hoặc bị ký sai, test nào phát hiện? Nếu không có, chưa kiểm token validation.
- Nếu người dùng có credentials đúng nhưng thiếu role, test nào xác nhận 403?
- Nếu cấu hình filter chain sai matcher hoặc filter bị tắt, test nào phát hiện?
- Nếu form login hoặc SSO yêu cầu CSRF/state/nonce và session, test nào đi qua hành vi đó?

## 14. Bài tập tự luyện

1. `@WithMockUser(username="root", roles="ADMIN")` làm `GET /admin` trả 200, nhưng database không có `root`. Test đã chứng minh điều gì và chưa chứng minh điều gì?
2. Vì sao `with(httpBasic("alice","wrong"))` có giá trị kiểm authentication hơn `with(user("alice"))` khi filter chain và provider thật hoạt động?
3. Một test JWT gọi `jwt().authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))`. Nó có thể phát hiện lỗi cấu hình `issuer-uri` hoặc audience không?
4. Khi dùng `@WithUserDetails`, thành phần nào có thể đã được gọi? Thành phần nào vẫn chưa kiểm credentials?
5. Một nhóm chỉ dùng `@WebMvcTest` với controller mocks, rồi ấn định tất cả request đều 200. Cần thêm dạng test nào để xác minh filter/authorization thật?
6. Vì sao `@WithMockUser` trên JUnit thread không làm HTTP request tới `RANDOM_PORT` tự trở thành authenticated?
7. Cần thêm test nào khi chuyển ứng dụng từ form login/session sang Resource Server JWT?
8. Nếu `ROLE_ADMIN` vẫn được cấp bởi `@WithMockUser` nhưng converter JWT production bị lỗi, test nào giúp phát hiện? Hãy phân lớp unit converter và integration Bearer pipeline.
9. Trong ứng dụng WebFlux, `mockJwt()` khác gì với HTTP request chứa token được ký thật?
10. Khi một request đã xác thực nhận 403, có nên sửa bằng cách bỏ CSRF hoặc thay `hasRole` thành `permitAll` không? Cần chẩn đoán gì trước?

## 15. Tài liệu chính thức

- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Testing OAuth 2.0 and JWT with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — WebFlux Test Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Reactive Test OAuth 2.0 / JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Framework — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html)

**Điểm ghi nhớ:** mock principal là bằng chứng hữu ích về **hành vi sau khi đã có danh tính**. Muốn khẳng định **quá trình xác thực thực**, hãy có ít nhất một lớp test gửi credentials/token qua đúng filter/provider/decoder và kiểm cả trường hợp thất bại. Việc đặt tên test đúng phạm vi giúp tránh nhầm một phản hồi `200 OK` với một hệ thống đăng nhập an toàn.
