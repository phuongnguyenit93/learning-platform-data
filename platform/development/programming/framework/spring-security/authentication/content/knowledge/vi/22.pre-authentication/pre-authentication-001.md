# Mô hình pre-authentication khi danh tính đã được xác minh ở hệ thống phía trước

## 1. Bài toán và kết quả cần đạt

Trong nhiều hệ thống doanh nghiệp, người dùng đăng nhập **trước khi** HTTP request đến ứng dụng Spring Boot. Một cổng SSO, identity-aware reverse proxy, API gateway, máy chủ ứng dụng hoặc thành phần xác thực bằng chứng chỉ X.509 đã kiểm tra người dùng. Ứng dụng ở phía sau cần biết **ai đang gọi** và **người đó được phép làm gì**, nhưng không nên buộc người dùng nhập lại mật khẩu ở mỗi ứng dụng.

Spring Security gọi đây là **pre-authentication** (tiền xác thực). “Pre” nghĩa là danh tính đã được bên ngoài kiểm chứng trước khi đi vào cơ chế nhận diện người dùng của Spring Security. Nó **không** có nghĩa ứng dụng có thể tin mọi chuỗi tên người dùng do client gửi đến.

Sau bài học, bạn cần có thể:

1. Vẽ ranh giới tin cậy giữa browser/client, hệ thống xác thực phía trước và ứng dụng Spring.
2. Giải thích đường đi của principal và authorities khi Spring Security dùng pre-authentication.
3. Phân biệt `RequestHeaderAuthenticationFilter`, `PreAuthenticatedAuthenticationProvider` và `UserDetailsService`.
4. Cấu hình một ví dụ Servlet/Spring MVC nhận principal từ một header **chỉ do gateway đáng tin cậy đặt**, rồi phân quyền trong Spring Security.
5. Kiểm tra các tình huống thiếu danh tính, người dùng không tồn tại, có danh tính nhưng thiếu quyền và thay đổi principal.
6. Nhận ra rủi ro giả mạo header, truy cập vòng qua gateway, lưu session cũ và nhập nhằng giữa authentication/authorization.

## 2. Ai chịu trách nhiệm điều gì?

Mô hình tổng quát:

```text
Client / browser
    |
    | 1. Đăng nhập SSO, xác thực chứng chỉ hoặc gửi token
    v
Trusted identity gateway / reverse proxy
    | 2. Kiểm chứng credentials và session/token của client
    | 3. Gỡ bỏ mọi identity header do client tự gửi
    | 4. Gắn identity đã xác minh (ví dụ X-Verified-User: alice)
    v
Kênh nội bộ chỉ cho gateway truy cập (TLS/mTLS + chính sách mạng)
    |
    v
Spring Boot (Servlet filter chain)
    | 5. Pre-auth filter lấy principal từ request
    | 6. AuthenticationManager / provider ánh xạ principal tới UserDetails + authorities
    | 7. Đặt Authentication thành công vào SecurityContext
    | 8. AuthorizationFilter xét quyền endpoint
    v
Controller / service
```

**Trách nhiệm của hệ thống phía trước:** xác thực danh tính thật, quản lý phiên/credential, chống giả mạo và chuyển tiếp identity đã kiểm chứng theo một hợp đồng rõ ràng.

**Trách nhiệm của Spring Security:** nhận thông tin danh tính từ **nguồn đã xác lập độ tin cậy**, ánh xạ về tài khoản và quyền phù hợp, kiểm tra trạng thái tài khoản (nếu thiết kế yêu cầu), xây dựng `Authentication`/`SecurityContext`, và thực thi authorization.

**Trách nhiệm của hạ tầng triển khai:** ứng dụng không thể bị gọi trực tiếp từ Internet hay từ đường mạng không được phép với một header tự điền; các hop giữa gateway và ứng dụng phải được bảo vệ. Mã Spring không thể tự biến một HTTP header do bất kỳ người nào gửi thành bằng chứng xác thực.

Ví dụ: nếu ứng dụng tin `X-Verified-User: admin` mà client có thể kết nối trực tiếp tới ứng dụng, một client chỉ cần gửi header này là có thể mạo danh admin. Đó là lỗi **trust boundary**, không phải lỗi nhỏ về cú pháp Spring.

## 3. Pre-authentication khác đăng nhập và phân quyền như thế nào?

| Việc cần giải quyết | Nơi thực hiện trong mô hình này | Kết quả |
| --- | --- | --- |
| Kiểm tra mật khẩu/MFA/SSO hoặc chứng chỉ | Hệ thống xác thực phía trước | Danh tính bên ngoài được xác minh |
| Chuyển danh tính vào request nội bộ | Gateway/proxy tin cậy | Principal đã kiểm chứng, ví dụ mã người dùng ổn định |
| Tạo `Authentication` trong Spring | Pre-authentication filter và provider | Spring Security có thông tin người dùng đã được ánh xạ |
| Nạp quyền, kiểm tra user bị khóa/vô hiệu | `AuthenticationUserDetailsService`/`UserDetailsService` và user checker | Authorities và trạng thái tài khoản phù hợp |
| Quyết định endpoint/data có được truy cập | `AuthorizationFilter`, `authorizeHttpRequests`, method security | Cho phép hoặc từ chối hành động |

Hai kết luận quan trọng:

- Spring Security có thể sử dụng các API của `AuthenticationManager` dù **không kiểm tra lại mật khẩu**. Ở đây “authenticate” trong framework chủ yếu là **xử lý một principal vốn đã được xác minh**, bổ sung thông tin cần thiết và tạo authentication result.
- Có danh tính không mặc nhiên có toàn quyền. Gateway trả `alice` chỉ giúp biết ai đang gọi. Quyết định `alice` có `ROLE_ADMIN` hay không vẫn phải dựa vào chính sách phân quyền đáng tin cậy.

**Pre-authentication và bearer-token authentication không giống hệt nhau.** Nếu từng request mang JWT và ứng dụng Spring tự xác minh chữ ký, issuer, audience, expiry rồi tạo `JwtAuthenticationToken`, thì Spring vẫn **tự kiểm chứng bằng chứng xác thực** thông qua resource server. Trong header-based pre-authentication, Spring thường tin kết quả xác thực đã thực hiện bởi gateway; bản thân chuỗi username không chứa bằng chứng mật mã để Spring tự kiểm tra.

## 4. Các thành phần Spring Security (Servlet)

Các lớp điển hình của cơ chế này nằm trong `org.springframework.security.web.authentication.preauth`.

### 4.1. `AbstractPreAuthenticatedProcessingFilter`

Đây là lớp nền cho filter nhận principal đã được xác thực bên ngoài. Subclass triển khai:

```java
protected Object getPreAuthenticatedPrincipal(HttpServletRequest request);
protected Object getPreAuthenticatedCredentials(HttpServletRequest request);
```

Hai chữ ký trên là **trích đoạn API**, không phải chương trình Java độc lập. Lớp base kiểm tra `SecurityContext` hiện tại, lấy principal/credentials từ request khi cần, tạo `PreAuthenticatedAuthenticationToken` để chuyển cho `AuthenticationManager`, rồi xử lý kết quả.

Các cài đặt đáng chú ý:

- `setCheckForPrincipalChanges(true)`: kiểm tra thay đổi principal giữa các request, thay vì luôn giữ authentication cũ nếu `SecurityContext` đã có giá trị.
- `setInvalidateSessionOnPrincipalChange(true)`: lựa chọn liên quan đến việc hủy session khi principal thay đổi; mặc định của lớp là `true`.
- `setContinueFilterChainOnUnsuccessfulAuthentication(...)`: mặc định là `true`, cho phép chain tiếp tục khi authentication manager ném `AuthenticationException`. Nếu cấu hình `false`, lỗi được ném ngay và cơ chế xử lý lỗi phải được bố trí phù hợp.
- `setSecurityContextRepository(...)`: chỉ định cách lưu context sau khi pre-auth thành công. Không nên dựa vào giả định về session khi thiết kế hệ thống stateless.

Theo mặc định, nếu context đã có Authentication, filter không cần xử lý lại principal ở mọi request. Trong mô hình dựa vào identity mới từ gateway, điều này có thể khiến phiên cũ gây nhầm lẫn nếu không rà soát chiến lược session và principal change.

### 4.2. `RequestHeaderAuthenticationFilter`

Subclass này lấy username từ request header. Tên header mặc định là `SM_USER` (tương thích Siteminder). Có thể đổi thành `X-Verified-User` bằng `setPrincipalRequestHeader(...)`.

- Mặc định, thiếu principal header sẽ gây `PreAuthenticatedCredentialsNotFoundException`; `setExceptionIfHeaderMissing(false)` cho phép bỏ qua trường hợp thiếu header và để cơ chế authorization quyết định.
- Nếu không chỉ định credentials header riêng, filter sử dụng một chuỗi dummy thay cho credentials. Đây **không phải mật khẩu** và provider pre-auth không kiểm chứng nó.
- Filter **không xác minh header được gateway đặt thật hay không**. Sự bảo đảm đó phải đến từ kiến trúc mạng, proxy và giao thức tin cậy.

Các tình huống khác có thể sử dụng `RequestAttributeAuthenticationFilter`, `J2eePreAuthenticatedProcessingFilter` hoặc X.509-specific filter. Cơ chế trích xuất khác nhau, nhưng ý tưởng phân biệt **identity proof ở upstream** với **Spring Security authorization ở downstream** là giống nhau.

### 4.3. `PreAuthenticatedAuthenticationToken`

Đây là một dạng `Authentication` mô tả yêu cầu xác thực dựa trên principal đã được hệ thống khác kiểm chứng. Filter thường tạo token trước khi chuyển cho manager; provider trả về một Authentication được xác thực với authorities thích hợp.

Đừng tự tạo token “đã xác thực” từ header không đáng tin rồi đưa thẳng vào `SecurityContextHolder`. Làm vậy bỏ qua cả nguồn gốc danh tính và luồng nạp/kiểm tra quyền.

### 4.4. `PreAuthenticatedAuthenticationProvider`

Provider này xử lý `PreAuthenticatedAuthenticationToken` và gọi một `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`. Nó không kiểm tra lại mật khẩu của người dùng, bởi hợp đồng pre-auth giả định upstream đã làm việc đó.

Thông thường, provider cần nạp `UserDetails` và authorities rồi kiểm tra trạng thái tài khoản (ví dụ disabled, locked, expired) qua `UserDetailsChecker`. Nếu principal không tồn tại, thao tác nạp user có thể thất bại. Việc đưa `ROLE_ADMIN` vào một header thiếu tin cậy và tự động tin theo không phải chiến lược cấp quyền an toàn.

### 4.5. `UserDetailsByNameServiceWrapper`

Đây là adapter cho phép provider sử dụng `UserDetailsService.loadUserByUsername(...)` truyền thống trong trường hợp nhận principal qua một Authentication token. Nó thích hợp khi dữ liệu quyền nằm trong database/LDAP hoặc một nguồn danh tính nội bộ được quản trị.

Nếu upstream cung cấp authorities đã được xác minh, Spring Security có những tiện ích khác như `PreAuthenticatedGrantedAuthoritiesUserDetailsService`. Dù dùng cách nào, cần thiết kế rõ **nguồn quyền nào có thẩm quyền**, cách chuẩn hóa tên vai trò, vòng đời quyền và khi nào phải làm mới dữ liệu.

## 5. Luồng request chi tiết

Giả sử người dùng `alice` đăng nhập thành công ở gateway và gọi `GET /api/me`.

1. Browser có session/credential với gateway. Gateway xác minh nó cho request này.
2. Gateway xóa mọi header danh tính phía client rồi đặt `X-Verified-User: alice` trên request nội bộ đi tới Spring.
3. `FilterChainProxy` chọn `SecurityFilterChain` dành cho request. Pre-auth filter đọc principal `alice`.
4. Filter tạo `PreAuthenticatedAuthenticationToken` với principal `alice` cùng credentials dummy và gọi `AuthenticationManager`.
5. `PreAuthenticatedAuthenticationProvider` nhận token, dùng user details service tải tài khoản `alice`, thu được `ROLE_USER` và trạng thái tài khoản.
6. Provider trả Authentication được xác thực. Filter đặt Authentication vào `SecurityContext` của request và, theo cấu hình, có thể ghi vào `SecurityContextRepository`.
7. `AuthorizationFilter` đánh giá rule `/api/me` cần authenticated user. Rule đạt, controller đọc `Principal.getName()` là `alice`.

Với `GET /api/admin`, nếu `alice` không có `ROLE_ADMIN`, yêu cầu bị từ chối **403 Forbidden** mặc dù danh tính hợp lệ. Nếu request thiếu danh tính, một cấu hình API thường trả **401 Unauthorized**. Những mã này phụ thuộc cấu hình entry point và access-denied handling; ví dụ dưới đây cấu hình rõ đường 401.

## 6. Ví dụ Java 17+: Spring Boot MVC nhận identity từ gateway

Ví dụ tự chứa dưới đây dùng **Spring Boot 3.5.16**, Spring Security 6.x và Java 17+. Dùng MVC/Servlet để áp dụng đúng các lớp `RequestHeaderAuthenticationFilter`/`PreAuthenticatedAuthenticationProvider`. Gateway thực tế nằm **ngoài** dự án này; vì vậy ví dụ chỉ nhằm kiểm chứng phần ánh xạ danh tính bên trong Spring bằng local request/test. **Không mở cổng ứng dụng này ra mạng không tin cậy với cơ chế header-based pre-auth khi chưa có gateway bảo vệ thực sự.**

Cấu trúc dự án:

```text
preauth-demo/
├── pom.xml
├── src/main/java/demo/preauth/PreAuthDemoApplication.java
└── src/test/java/demo/preauth/PreAuthDemoApplicationTests.java
```

Tạo `pom.xml`:

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
    <artifactId>preauth-demo</artifactId>
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

Tạo file `src/main/java/demo/preauth/PreAuthDemoApplication.java`:

```java
package demo.preauth;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PreAuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PreAuthDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfig {
    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}not-used")
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}not-used")
            .roles("USER", "ADMIN")
            .build();
        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            lookup = new UserDetailsByNameServiceWrapper<>();
        lookup.setUserDetailsService(users);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(lookup);

        RequestHeaderAuthenticationFilter preAuth =
            new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(new ProviderManager(provider));
        preAuth.setCheckForPrincipalChanges(true);
        preAuth.setSecurityContextRepository(
            new NullSecurityContextRepository());

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository()))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(preAuth, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}

@RestController
class ApiController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    String currentUser(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
```

**Giải thích các lựa chọn quan trọng:**

- `preAuth` được khởi tạo **cục bộ bên trong `SecurityFilterChain`**, tránh khai báo thành một `@Bean` kiểu Servlet Filter rồi vô tình bị Spring Boot auto-register thêm bên ngoài Spring Security chain.
- `UserDetailsByNameServiceWrapper` nối pre-auth provider với danh sách account `alice`/`bob`. Mật khẩu `{noop}not-used` chỉ là dữ liệu test để `UserDetails` đầy đủ; luồng này **không kiểm tra mật khẩu đó**. Không dùng `{noop}` cho hệ thống thật.
- `setExceptionIfHeaderMissing(false)` cho phép `/public` chạy khi không có identity header; đường `/api/**` vẫn yêu cầu authentication.
- `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository` thể hiện lựa chọn **không duy trì Spring Security authentication qua HTTP session**. Mỗi request được gateway chứng thực và Spring ánh xạ lại principal. Nếu dùng session trong sản phẩm thật, cần chính sách về principal change, logout, expiry và cập nhật quyền.
- `HttpStatusEntryPoint(UNAUTHORIZED)` xác định hành vi 401 khi cần authentication nhưng request chưa có principal hợp lệ.
- `formLogin` và `httpBasic` được tắt vì ví dụ này chỉ nhận danh tính từ gateway; thêm cơ chế đăng nhập phụ trong cùng đường tin cậy có thể tạo cách vòng qua kiểm soát upstream.
- `addFilterBefore(preAuth, UsernamePasswordAuthenticationFilter.class)` đặt filter ở vùng authentication, trước phần authorization. `UsernamePasswordAuthenticationFilter` được dùng làm **mốc thứ tự** dù form login đã tắt.
- Các rule ở `authorizeHttpRequests` là **phân quyền**. `bob` có `ROLE_ADMIN`; `alice` chỉ có `ROLE_USER`. `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`.

### Chạy thử ở máy phát triển

Trong thư mục `preauth-demo`:

```bash
mvn spring-boot:run
```

Ở terminal khác (chỉ dùng cho **môi trường local** hoặc đường test tương đương; các lệnh có header ở đây cố tình mô phỏng gateway):

```bash
curl -s http://localhost:8080/public
curl -s -H "X-Verified-User: alice" http://localhost:8080/api/me
curl -s -H "X-Verified-User: bob" http://localhost:8080/api/admin
curl -i http://localhost:8080/api/me
curl -i -H "X-Verified-User: alice" http://localhost:8080/api/admin
curl -i -H "X-Verified-User: unknown" http://localhost:8080/api/me
```

Ba body đầu, theo thứ tự:

```text
public
alice
admin
```

Ba request còn lại minh họa các trạng thái:

| Request | Kỳ vọng | Lý do |
| --- | --- | --- |
| `/api/me` không có header | HTTP 401 | Không có principal được upstream cung cấp |
| `/api/admin` với `alice` | HTTP 403 | Đã có principal hợp lệ, thiếu `ROLE_ADMIN` |
| `/api/me` với `unknown` | HTTP 401 | Provider không tìm thấy account trong user store |

Các header/body lỗi phụ thuộc cách Spring Boot dựng response; ở đây kiểm tra HTTP status. `curl -s` không tự thêm newline, nên nếu chạy liên tiếp body có thể liền nhau trên màn hình.

**Giới hạn của demo:** bất kỳ ai kết nối được đến địa chỉ `localhost:8080` và tự đặt header `X-Verified-User` đều có thể giả lập user. Demo minh họa lý do **phải có gateway và chặn kết nối trực tiếp** khi triển khai thực tế; nó không phải cấu hình bảo mật production độc lập.

## 7. Kiểm tra tích hợp bằng MockMvc

Tạo `src/test/java/demo/preauth/PreAuthDemoApplicationTests.java`:

```java
package demo.preauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PreAuthDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void trustedPrincipalIsMappedToSpringAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Verified-User", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void authenticatedUserMayLackAuthority() throws Exception {
        mvc.perform(get("/api/admin")
                .header("X-Verified-User", "alice"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .header("X-Verified-User", "bob"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void missingOrUnknownPrincipalIsNotAuthorized() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me")
                .header("X-Verified-User", "unknown"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointNeedsNoIdentityHeader() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

Chạy:

```bash
mvn test
```

Kết quả mong đợi: cả bốn test pass. Các test chứng minh filter/provider/authorization của **Spring** kết hợp đúng. Chúng **không chứng minh** gateway đã xác minh danh tính hoặc ngăn được header spoofing từ ngoài. Việc đó cần integration/security test ở ranh giới mạng với một gateway thật.

Để kiểm tra sự phân tách trách nhiệm, có thể thêm test rằng một client gửi `X-Verified-User: bob` thẳng vào backend ở môi trường staging **không thể kết nối được** (ví dụ kết nối bị firewall từ chối). Test này phải chạy ở lớp hạ tầng; một `MockMvc` test không mô phỏng được firewall/mTLS.

## 8. Các kiểm soát bắt buộc khi đưa pre-auth ra production

### 8.1. Nguồn identity phải đáng tin cậy

Thiết kế gateway cần đáp ứng đồng thời:

1. **Xác minh request đến từ client**: SSO session, OAuth/OIDC login, client certificate hoặc phương thức upstream được tổ chức phê duyệt.
2. **Gỡ mọi header identity do client gửi** trước khi gắn giá trị mới. Không dùng quy tắc “nếu client đã gửi thì giữ nguyên”.
3. **Chỉ định rõ header hợp đồng**, loại bỏ header trùng, giá trị rỗng, ký tự không hợp lệ và identity không được xác minh. Nên dùng mã user ổn định/không tái sử dụng thay vì display name.
4. **Khóa đường vào backend**: private network, firewall/security group, service mesh policy, mTLS hoặc cơ chế xác minh peer tương đương. Cần bảo đảm mọi đường truy cập (HTTP/HTTPS khác, sidecar, cổng debug, ingress phụ, internal DNS) đều không bypass gateway.
5. **Bảo vệ từng hop** và giữ nguyên chỉ header do gateway tạo. Tin `X-Forwarded-*` hay một địa chỉ IP không được xác minh là không đủ để xác thực người dùng.
6. **Giới hạn/kiểm toán quyền đặt header** của các reverse proxy trung gian; thiết lập xử lý nhất quán khi retry, failover, cache và có nhiều proxy.
7. **Kiểm thử fail-closed** khi gateway hoặc identity service lỗi: không biến request chưa xác minh thành một user mặc định.

Một cách thiết kế mạnh hơn là dùng token assertion **được ký** bởi upstream và yêu cầu backend xác minh chữ ký, audience, issuer, thời hạn. Khi đó backend đang xác thực một bằng chứng mật mã, chứ không chỉ tin username header; cần chọn cơ chế Spring Security phù hợp (thường OAuth2 Resource Server nếu dùng JWT chuẩn).

### 8.2. Danh tính và quyền phải có quy tắc riêng

- **Principal/subject:** chọn khóa người dùng ổn định; xác định rõ mapping từ IdP username/email/subject đến user nội bộ. Tránh tự động tạo account quyền cao từ chuỗi do upstream gửi.
- **Authorities:** nếu lấy từ nội bộ, cập nhật theo user store; nếu gateway cung cấp, chỉ tin khi nguồn quyền được bảo vệ giống principal và có quy tắc ký/đồng bộ/chuẩn hóa.
- **Trạng thái tài khoản:** xác định liệu user bị disable/lock ở app có bị chặn dù SSO vẫn còn phiên hay không. Ví dụ ở phần 6 dùng `UserDetailsService` làm nguồn local.
- **Tenant:** không suy ra quyền truy cập tenant từ principal hoặc header `X-Tenant` đơn lẻ. Mọi truy cập dữ liệu nhạy cảm phải kiểm tra ràng buộc principal–tenant.
- **Phân quyền theo đối tượng:** `hasRole("ADMIN")` là kiểm tra coarse-grained; vẫn cần policy ở tầng service/data khi người dùng truy cập tài nguyên thuộc người khác.

### 8.3. Vòng đời session và thay đổi principal

Với ứng dụng **stateful**, phiên Spring Security có thể giữ Authentication đã tạo trước đó. Cần quyết định:

- Khi gateway thông báo user mới trong cùng browser/session, ứng dụng có cập nhật Authentication và hủy session cũ không?
- Khi quyền bị thu hồi, thời gian cache quyền hay session cho phép quyền cũ tồn tại bao lâu?
- Khi gateway logout/SSO hết hạn, các phiên ở downstream có bị hủy theo không?
- Khi backend có nhiều node, các node xử lý Principal/authorities có nhất quán không?

Trong `AbstractPreAuthenticatedProcessingFilter`, `checkForPrincipalChanges` là một công cụ liên quan, nhưng **không thay thế** thiết kế logout, session expiry, token revocation và quyền. Ví dụ ở phần 6 dùng stateless để tránh lưu authentication của request trước.

### 8.4. CSRF, CORS, logging và quyền gọi API

Pre-auth không tự xử lý CSRF. Nếu ứng dụng dùng cookie đăng nhập tại gateway và trình duyệt gửi cookie tự động, state-changing endpoints vẫn phải xem xét CSRF theo threat model. Trong ví dụ chỉ có GET nên không cần tắt CSRF. CORS chỉ điều khiển việc browser đọc/gửi cross-origin theo chính sách; CORS không phải cơ chế chứng minh header đã được gateway xác minh.

Trong log/tracing, ghi correlation ID và mã principal cần thiết, hạn chế PII. Không ghi cookie, raw SSO assertion, bearer token hay toàn bộ SecurityContext. Tránh đặt quyết định phân quyền chỉ dựa vào log hoặc một header mô tả role.

## 9. Nếu ứng dụng dùng Spring WebFlux thì sao?

Các lớp `RequestHeaderAuthenticationFilter` và `AbstractPreAuthenticatedProcessingFilter` ở trên là API **Servlet**, dựa trên `HttpServletRequest` và Servlet `FilterChain`. Không cài chúng vào `SecurityWebFilterChain` của WebFlux.

Với WebFlux, mô hình trust boundary vẫn giống nhau nhưng API khác:

- `ServerAuthenticationConverter` có thể trích xuất dữ liệu đã được gateway xác minh từ `ServerWebExchange` để tạo authentication request.
- `AuthenticationWebFilter` và `ReactiveAuthenticationManager` xử lý theo chuỗi reactive.
- `ReactiveSecurityContextHolder` đưa Authentication vào Reactor Context để các thành phần phía sau đọc.
- Với chứng chỉ client X.509, Spring Security có `ServerHttpSecurity.x509(...)` và `ReactivePreAuthenticatedAuthenticationManager` trong hướng dẫn reactive X.509.

Đây là sự phân biệt **mô hình** và **implementation API**. Không tái sử dụng nguyên mẫu Java Servlet ở phần 6 cho WebFlux. Cũng không coi mọi header username trong WebFlux là an toàn nếu thiếu gateway trust boundary.

## 10. Triệu chứng, nguyên nhân và cách xử lý

| Triệu chứng | Khả năng cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| User tự thêm header mà vào được tài khoản khác | Backend mở trực tiếp; gateway không xóa/ghi đè header | Khóa đường mạng vào backend và kiểm soát identity header tại gateway |
| Không có header mà nhận lỗi filter sớm | Mặc định `RequestHeaderAuthenticationFilter` ném lỗi khi thiếu header | Rà soát `exceptionIfHeaderMissing` và cấu hình response/fail-closed tương ứng |
| HTTP 401 dù gateway nói đã login | Header bị mất/khác tên, không tìm thấy principal, account bị khóa hoặc filter chain sai | Theo dõi một request qua gateway, matcher, filter và user store |
| HTTP 403 dù có Authentication | Principal hợp lệ nhưng thiếu quyền | Kiểm tra authorities, prefix `ROLE_`, matcher và policy tài nguyên |
| Thay SSO account nhưng backend vẫn là user cũ | Session/`SecurityContext` lưu Authentication trước; không kiểm tra principal changes | Kiểm tra strategy session, `checkForPrincipalChanges`, invalidate và logout |
| Header “ADMIN” khiến user có quyền admin | Trust nhầm role header hoặc mapping không kiểm soát | Lấy authorities từ nguồn được xác minh/kiểm soát; kiểm tra tenant và account |
| Pre-auth filter chạy hai lần | `@Bean` kiểu Servlet Filter bị auto-register và còn được thêm vào `SecurityFilterChain` | Chỉ cấu hình trong security filter chain hoặc disable servlet auto-registration có chủ ý |
| Ứng dụng không biết user ở `SecurityContextHolder` | Filter chưa chạy, bị skip bởi securityMatcher, provider chưa thành công | Kiểm tra chain được áp dụng, thứ tự filter, UserDetailsService và logs phù hợp |
| Không rõ 401, 403 hay redirect | Authentication entry point/exception handling được kế thừa từ cấu hình khác | Cấu hình entry point và authorization riêng theo cách API cần |
| Chạy WebFlux nhưng dùng Servlet filter | Nhầm hai servlet/reactive stack | Sử dụng API reactive tương ứng |

Một quy trình debug hữu dụng:

1. Đầu tiên xác nhận **ai đã xác minh** user tại upstream và header nào thực sự được gửi tới backend.
2. Kiểm tra request có đi qua đúng `SecurityFilterChain` không; nhiều chain có matcher khác nhau.
3. Tại pre-auth filter, principal có được lấy ra không? Có Authentication sẵn trong context làm filter bỏ qua không?
4. Provider có nhận đúng loại `PreAuthenticatedAuthenticationToken` và nạp đúng account/authorities không?
5. Tại authorization, rule nào bị từ chối? Không kết luận 403 là “SSO hỏng” khi nguyên nhân thực sự là thiếu quyền.

## 11. Các câu hỏi tự kiểm tra

1. **Tại sao HTTP header chứa username không tự là bằng chứng xác thực?** Vì client có thể tự tạo nó trừ khi một proxy đáng tin cậy kiểm chứng request, loại bỏ header giả và đảm bảo backend chỉ nhận luồng từ proxy.
2. **Ai kiểm tra mật khẩu trong mô hình header-based pre-auth?** Hệ thống phía trước. `PreAuthenticatedAuthenticationProvider` xử lý principal đã được tin cậy, chủ yếu nạp user/authorities và kiểm tra trạng thái tài khoản, không xác thực lại mật khẩu.
3. **User đã được nhận diện có chắc vào `/api/admin` không?** Không. Authorization vẫn kiểm tra authorities và policy; authenticated user thiếu `ROLE_ADMIN` nhận 403.
4. **Vì sao không khai báo `RequestHeaderAuthenticationFilter` vừa là `@Bean` vừa thêm bằng `addFilterBefore` một cách tùy tiện?** Vì Spring Boot có thể auto-register bean Servlet Filter ngoài `FilterChainProxy`, khiến filter chạy trùng hoặc sai vị trí.
5. **Header thiếu và header nhận giá trị `unknown` giống nhau không?** Không. Trường hợp đầu có thể không tạo authentication attempt; trường hợp sau có thể đi qua provider rồi thất bại vì không tìm được user. Ứng dụng có thể cấu hình cả hai trả 401.
6. **Dùng `SessionCreationPolicy.STATELESS` có tự làm gateway trở nên đáng tin không?** Không. Nó chỉ ảnh hưởng đến lưu trạng thái bảo mật trong Spring; trust boundary upstream vẫn phải được bảo vệ.
7. **Khi có Spring WebFlux, có giữ nguyên `RequestHeaderAuthenticationFilter` không?** Không. Cần API reactive của `SecurityWebFilterChain`/`AuthenticationWebFilter` và Reactor Context.

## 12. Tài liệu chính thức

- Spring Security, Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- `AbstractPreAuthenticatedProcessingFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- `RequestHeaderAuthenticationFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- `PreAuthenticatedAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Java Configuration: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security Reactive X.509: https://docs.spring.io/spring-security/reference/reactive/authentication/x509.html
