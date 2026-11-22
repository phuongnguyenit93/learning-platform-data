# authenticated, fullyAuthenticated, rememberMe và anonymous trong phân quyền HTTP (Spring Security Servlet)

## 1. Vấn đề: cùng là Authentication nhưng mức độ tin cậy khác nhau

Một request HTTP có thể đi qua `AuthorizationFilter` với một đối tượng `Authentication` biểu diễn:

- **Anonymous** — chưa đăng nhập; framework có thể đưa `AnonymousAuthenticationToken` vào ngữ cảnh để việc xử lý thống nhất.
- **Remember-me** — trước đó người dùng đã chọn “ghi nhớ đăng nhập”; session đầy đủ không còn, nhưng remember-me cookie được kiểm tra hợp lệ và tạo `RememberMeAuthenticationToken`.
- **Full authentication** — người dùng vừa hoặc đã đăng nhập bằng một cơ chế được Spring Security xem là xác thực đầy đủ, chẳng hạn form login username/password, và trạng thái đó còn hợp lệ trong session.

Spring Security có bốn điều kiện rất dễ nhầm khi viết quy tắc phân quyền HTTP:

```java
.authenticated()
.fullyAuthenticated()
.rememberMe()
.anonymous()
```

Chúng **không phải bốn cách viết đồng nghĩa của “có quyền”**. Chúng dựa vào loại và mức độ tin cậy của Authentication, khác với việc kiểm tra authority bằng `hasRole`/`hasAuthority`.

Ví dụ yêu cầu nghiệp vụ:

- Trang `/account` có thể cho phép cả login bằng form và remember-me.
- Trang `/settings/security` nên yêu cầu xác thực đầy đủ, không chỉ remember-me.
- Trang `/welcome-new` chỉ dành cho người chưa đăng nhập.
- Endpoint minh họa `/remember-only` chỉ được truy cập khi request thực sự được xác thực bằng remember-me.
- Endpoint `/admin-sensitive` phải kiểm tra **cả** role admin **và** full authentication.

Bài học tập trung vào **quyết định phân quyền HTTP của Spring Security Servlet**, không đánh đồng việc “bật tính năng nhớ đăng nhập” với việc “viết matcher rememberMe”.

### 1.1. Kết quả học tập

Sau bài này, bạn sẽ:

1. Dự đoán một request được cho phép hay từ chối với mỗi predicate.
2. Hiểu vì sao `Authentication.isAuthenticated()` đơn lẻ không đủ phân biệt anonymous.
3. Dùng `authorizeHttpRequests` với các rule chính xác, theo đúng thứ tự.
4. Phân biệt lỗi cần login (form redirect) với lỗi đã xác thực nhưng không thỏa rule.
5. Kết hợp authentication trust và authority/role trong endpoint nhạy cảm.
6. Kiểm thử thực tế bằng Spring Boot 3, Java 17, MockMvc, form login và remember-me cookie.

## 2. Phân loại trạng thái bằng AuthenticationTrustResolver

Trong Spring Security, `AuthenticationTrustResolver` là abstraction để nhận diện mức độ tin cậy của một authentication. Implementation thường gặp là `AuthenticationTrustResolverImpl`.

Các ý nghĩa chủ chốt:

- `isAnonymous(authentication)`: token thuộc loại anonymous theo trust resolver.
- `isRememberMe(authentication)`: token thuộc loại remember-me.
- `isAuthenticated(authentication)`: đã được xác thực theo cách framework nhận diện, không phải anonymous.
- `isFullyAuthenticated(authentication)`: xác thực hợp lệ nhưng **không** phải anonymous và **không** phải remember-me.

Đây là bảng mô hình cho các token chuẩn:

| Loại request | `isAnonymous` | `isRememberMe` | `isAuthenticated` | `isFullyAuthenticated` |
| --- | --- | --- | --- | --- |
| Anonymous | true | false | false | false |
| Remember-me hợp lệ | false | true | true | false |
| Full form login | false | false | true | true |

Bảng giả định các token được Spring Security tạo đúng và không có resolver tùy biến. Một custom `Authentication` hoặc cấu hình đặc biệt cần test với resolver thực tế của hệ thống.

### 2.1. Cạm bẫy: AnonymousAuthenticationToken.isAuthenticated()

`AnonymousAuthenticationToken` có thể có `isAuthenticated() == true` theo API token, dù người dùng chưa chứng minh danh tính. Vì thế đoạn logic tự viết kiểu:

```java
// KHÔNG nên dùng đơn lẻ để nhận diện người dùng đăng nhập thật:
if (authentication != null && authentication.isAuthenticated()) {
    // ...
}
```

có thể đưa ra kết luận sai về anonymous. Với phân quyền HTTP, dùng `authenticated()` và các predicate của Spring Security thay vì tự dựa duy nhất vào flag đó.

### 2.2. “Fully authenticated” không đồng nghĩa đã làm MFA

Trong ngữ cảnh này “fully” có nghĩa không phải anonymous/remember-me theo trust resolver. Nó **không tự chứng minh** người dùng:

- đã thực hiện MFA;
- vừa nhập mật khẩu trong vài phút gần đây;
- đang dùng thiết bị tin cậy;
- có quyền truy cập tài nguyên của người khác;
- có session chưa bị chiếm quyền;
- đã trải qua step-up cho thao tác chuyển tiền.

Khi nghiệp vụ yêu cầu xác thực lại gần đây hoặc MFA, phải thiết kế thêm chính sách về thời điểm/mức độ xác thực, không thể chỉ dựa vào `fullyAuthenticated()`.

## 3. Bảng chân trị của bốn rule HTTP

Giả sử Spring Security Servlet đang bật anonymous và remember-me theo cấu hình thông thường.

| Quy tắc | Anonymous | Remember-me | Full login |
| --- | --- | --- | --- |
| `authenticated()` | Không | Có | Có |
| `fullyAuthenticated()` | Không | Không | Có |
| `rememberMe()` | Không | Có | Không |
| `anonymous()` | Có | Không | Không |
| `permitAll()` | Có | Có | Có |
| `denyAll()` | Không | Không | Không |

**Nhận định quan trọng:** `rememberMe()` và `anonymous()` là những **predicate nhận diện trạng thái**, không phải “ít nhất mức tin cậy này”.

Nếu người dùng full login truy cập endpoint chỉ cho `rememberMe()`, request **không** thỏa rule đó. Dù full authentication thường mạnh hơn remember-me, Spring Security không diễn giải `rememberMe()` thành “remember-me hoặc cao hơn”. Khi muốn cho cả remember-me và full, dùng `authenticated()`.

Ngược lại, `anonymous()` không phù hợp với mọi trang công khai. Một trang `/about` cho tất cả khách và thành viên nên dùng `permitAll()`; nếu dùng `anonymous()`, người đã đăng nhập sẽ bị từ chối.

### 3.1. Ví dụ gắn với URL

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/welcome-new").anonymous()
    .requestMatchers("/account").authenticated()
    .requestMatchers("/remember-only").rememberMe()
    .requestMatchers("/settings/security").fullyAuthenticated()
    .anyRequest().denyAll()
);
```

Đây là **đoạn nằm bên trong SecurityFilterChain**, không phải chương trình chạy độc lập. Nó đưa ra quy tắc authorization chứ không tự cấu hình form login hay remember-me cookie. Phần ví dụ Maven hoàn chỉnh ở dưới khai báo cả các cơ chế authentication.

### 3.2. Phân biệt “bật remember-me” với “rule rememberMe”

Có hai API khác nhau:

```java
// Kích hoạt tính năng xác thực tự động bằng remember-me cookie:
http.rememberMe(remember -> remember
    .key("only-for-demo")
    .userDetailsService(users));

// Quy tắc quyền: request này phải đang ở trạng thái remember-me:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/remember-only").rememberMe());
```

Đây là hai mảnh cấu hình để minh họa (phần trên cần `HttpSecurity http` và `UserDetailsService users`). **Dòng thứ hai không tự phát hành hoặc kiểm tra remember-me cookie**. Nếu không bật remember-me authentication hoặc không có cơ chế nào tạo RememberMeAuthenticationToken, endpoint `rememberMe()` có thể không bao giờ được phép truy cập.

## 4. Chúng hoạt động ở đâu trong filter chain?

Một luồng Servlet có thể được hình dung như sau:

```text
GET /account
     |
     v
DelegatingFilterProxy / FilterChainProxy
     |
     v
SecurityFilterChain được chọn
     |
     +-- SecurityContext được khôi phục từ repository nếu có
     |
     +-- Authentication filter / RememberMeAuthenticationFilter
     |       -> nếu session full còn: thường giữ Authentication hiện có
     |       -> nếu không và remember-me cookie hợp lệ:
     |              tạo RememberMeAuthenticationToken
     |
     +-- AnonymousAuthenticationFilter
     |       -> nếu vẫn chưa có Authentication: tạo anonymous token
     |
     +-- ExceptionTranslationFilter
     |
     +-- AuthorizationFilter
             |
             +-- request matcher phù hợp
             +-- AuthorizationManager kiểm tra rule
             |
             +-- GRANTED: tiếp tục controller
             +-- DENIED: exception handling/entry point
```

Đây là sơ đồ khái niệm, không phải danh sách đầy đủ hoặc cam kết mọi version có đúng các filter theo thứ tự trên. Cơ chế authentication khác như OAuth2, HTTP Basic, bearer token hoặc custom filter có thể tạo loại Authentication khác.

### 4.1. Request matcher không chọn authentication mechanism

`requestMatchers("/account").authenticated()` chỉ định **rule phân quyền** cho URL đó. Nó không tự bật form login, HTTP Basic, remember-me hay session.

Để bật cơ chế cần cấu hình riêng, ví dụ `formLogin(...)` và `rememberMe(...)` trong `HttpSecurity`. Với nhiều `SecurityFilterChain`, các rule này chỉ có ý nghĩa trong chain được `FilterChainProxy` chọn theo `securityMatcher` và thứ tự `@Order`.

### 4.2. Thứ tự quy tắc quan trọng

Trong `authorizeHttpRequests`, thứ tự request matchers quyết định rule được áp dụng. Chỉ một rule phù hợp đầu tiên được chọn, không phải toàn bộ rule được tự động AND:

```java
// SAI với mục tiêu bảo vệ /admin bằng full authentication:
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
    // .requestMatchers("/admin").fullyAuthenticated() không nên đặt sau anyRequest
);
```

Thay bằng rule cụ thể trước fallback:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin").fullyAuthenticated()
    .anyRequest().authenticated()
);
```

Đây là hai đoạn **mô tả thứ tự rule**; để yêu cầu cả role admin và full, cần kết hợp hai điều kiện rõ ràng thay vì giả định hai `requestMatchers` trùng URL sẽ cùng được chạy.

## 5. authenticated(): chấp nhận remembered và full login

`authenticated()` có mục tiêu cho phép người dùng có danh tính được xác thực theo framework. Với remember-me chuẩn:

- Anonymous không thỏa `authenticated()`.
- RememberMeAuthenticationToken hợp lệ có thể thỏa `authenticated()`.
- Full form-login Authentication thỏa `authenticated()`.

Ví dụ route xem thông tin cá nhân có độ rủi ro phù hợp:

```java
.requestMatchers("/account/overview").authenticated()
```

Điều này **không tự bỏ qua kiểm tra sở hữu dữ liệu**. Request của user A không được đọc tài khoản B chỉ vì `authenticated` true. Phải kết hợp authorization resource-level trong application service, dữ liệu tenant và quyền phù hợp.

### 5.1. authenticated không phải role check

`authenticated()` không bảo đảm tồn tại `ROLE_ADMIN` hay quyền `invoice:read`. Một user remembered có `ROLE_READER` có thể được vào `/account/overview`, nhưng không có nghĩa được đọc mọi đơn hàng.

Đây là hai trục độc lập:

```text
Authentication trust:   anonymous / remember-me / full
Authorization rights:   ROLE_READER / ROLE_ADMIN / invoice:read / ownership
```

Cần kiểm tra cả hai nơi phù hợp với rủi ro; một rule không thay thế rule kia.

## 6. fullyAuthenticated(): khi remember-me chưa đủ

`fullyAuthenticated()` yêu cầu authentication không bị trust resolver phân loại là anonymous hoặc remember-me. Một người đã được khôi phục từ remember-me cookie có thể cần **đăng nhập tương tác lại** để truy cập trang chỉ cho full.

Ví dụ:

```java
.requestMatchers("/settings/security").fullyAuthenticated()
```

Trong form login, remember-me user bị chặn khỏi route full có thể được `ExceptionTranslationFilter` đưa tới authentication entry point, dẫn đến redirect `/login`. Response thực tế phụ thuộc chain, entry point, URL và custom handlers; đừng tuyệt đối hóa 302 cho mọi ứng dụng.

### 6.1. Vì sao không đặt fullyAuthenticated cho tất cả route?

Nếu mọi route đều yêu cầu full, remember-me mất phần lớn giá trị trải nghiệm. Thường chỉ các tác vụ có rủi ro cao cần mức độ tin cậy cao hoặc xác thực bổ sung. Một chính sách được cân nhắc:

| Loại thao tác | Gợi ý mức độ tin cậy tối thiểu |
| --- | --- |
| Trang trợ giúp công khai | `permitAll` |
| Xem dashboard cá nhân ít nhạy cảm | `authenticated` + ownership |
| Xem thông tin đã xác minh, đổi email | `fullyAuthenticated` và có thể thêm reauthentication |
| Xóa tài khoản, chuyển tiền, thay MFA | Full + step-up/recent authentication/MFA |
| Endpoint quản trị | Vai trò admin + policy trust + kiểm tra nghiệp vụ |

Không suy ra mức bảo vệ chính xác của một ứng dụng chỉ từ tên route. Phải đánh giá threat model, cách dữ liệu được hiển thị và khả năng mất thiết bị/cookie.

## 7. rememberMe(): chỉ đúng với authentication kiểu nhớ đăng nhập

`rememberMe()` là matcher chuyên biệt, thường dùng để kiểm thử và nhận diện request đã được tự xác thực bằng cookie. Nó không có nghĩa “hãy kích hoạt chức năng Remember Me”.

Trường hợp:

```text
Cookie session chứa full Authentication -> rememberMe() = false
Không có full session, remember-me cookie hợp lệ
    -> RememberMeAuthenticationToken -> rememberMe() = true
Không có login/cookie hợp lệ -> anonymous -> rememberMe() = false
```

Một ứng dụng thông thường hiếm khi cần chặn full-login user khỏi một trang. Khi muốn cho phép remembered hoặc full, **dùng `authenticated()`**, hoặc một rule tổng hợp phù hợp thay vì `rememberMe()`.

### 7.1. Không dùng rememberMe để thay thế session validity

Dù remember-me cookie có thời gian sống dài, nó không bảo đảm session hoặc user state bất biến. Người dùng có thể đổi mật khẩu, bị khóa, bị xóa, cookie hết hạn hoặc token bị revoke. Chỉ `RememberMeServices` xác minh cookie hợp lệ mới có thể tạo remember-me Authentication.

## 8. anonymous(): chỉ dành cho người chưa đăng nhập

`anonymous()` khớp với anonymous authentication theo framework, không phải mọi người có quyền truy cập.

Ví dụ có thể hữu ích khi UX muốn điều hướng người đã đăng nhập đi trang khác:

```java
.requestMatchers("/register-intro").anonymous()
```

Nhưng có hai giới hạn:

1. Chặn full hoặc remember-me user vào trang thông tin không nhất thiết có ý nghĩa bảo mật. Nếu thực sự muốn nội dung công khai, chọn `permitAll()`.
2. Anonymous policy dựa vào trust resolver/anonymous support. Một security chain tắt anonymous hoặc sử dụng custom resolver cần test chi tiết.

### 8.1. anonymous là authentication state, không phải role

Một authority có tên `ROLE_ANONYMOUS` không tự biến một token tùy ý thành `AnonymousAuthenticationToken`. Tương tự, user có `ROLE_GUEST` đã đăng nhập không tự thỏa `anonymous()`.

Không kiểm tra anonymous bằng cách so sánh username với chuỗi cố định `anonymousUser`; tên đó có thể tùy biến hoặc không phù hợp với cơ chế hiện tại.

## 9. Vì sao hasRole("ADMIN") chưa đủ cho trang nhạy cảm?

Một user admin đăng nhập bằng form có `ROLE_ADMIN`. Sau khi HTTP session mất, remember-me cookie của user đó vẫn có thể được xác minh và khôi phục authorities, gồm `ROLE_ADMIN`.

Nếu chỉ viết:

```java
.requestMatchers("/admin-sensitive").hasRole("ADMIN")
```

rule này **không bắt buộc fullyAuthenticated**. Một remembered admin có thể vào nếu có đúng authority và không bị chặn bởi policy khác.

Một cách thiết kế đúng hơn là kết hợp:

```text
allow /admin-sensitive
  iff has ROLE_ADMIN
  AND AuthenticationTrustResolver.isFullyAuthenticated(authentication)
  AND business policy khác (nếu có)
```

Trong ví dụ code đầy đủ ở phần 11 sẽ có một `AuthorizationManager<RequestAuthorizationContext>` tự kết hợp **role AND full trust**. Nhờ vậy, nó cho thấy rõ thứ tự đánh giá và tránh giả định đặt hai request matchers trùng nhau sẽ tự giao nhau.

### 9.1. Đừng nhầm request authorization với method authorization

`authorizeHttpRequests` bảo vệ request trước khi đi tới controller. Với hành động domain nhạy cảm, cần kiểm tra quyền ở service/method layer nếu business yêu cầu, ví dụ bằng `@PreAuthorize` khi bật method security.

Một method expression minh họa:

```java
// Minh họa trong bean có method security được bật, không độc lập:
@PreAuthorize("hasRole('ADMIN') and isFullyAuthenticated()")
public void approveSensitiveChange() {
    // Business validation và ghi audit ở tầng application.
}
```

Cần `@EnableMethodSecurity` và cấu hình expression tương ứng. Không gọi method này là “đã an toàn” nếu thiếu kiểm tra sở hữu tài nguyên, MFA, CSRF hay transaction. Method security còn bảo vệ các lời gọi không bắt nguồn từ URL cụ thể trong kiến trúc phù hợp.

## 10. HTTP response khi quy tắc không được thỏa

Đừng học thuộc rằng “authenticated sai → 401” và “fullyAuthenticated sai → 403”. HTTP response là kết quả của **authentication entry point**, **access denied handler**, **trust resolver** và cơ chế xác thực đang dùng.

Trong web form-login với session:

| Trạng thái | Rule bị chặn | Kết quả thường gặp |
| --- | --- | --- |
| Anonymous | `authenticated()` | 302 redirect tới trang login |
| Anonymous | `fullyAuthenticated()` | 302 redirect tới login |
| Remember-me | `fullyAuthenticated()` | Có thể được đưa tới login để xác thực tương tác |
| Remember-me | `anonymous()` | Không được cho phép; xử lý có thể redirect/re-auth tùy entry point |
| Full login | `rememberMe()` | Thường 403, vì đã authenticated nhưng không thỏa rule |
| Full login | Thiếu `ROLE_ADMIN` | Thường 403 |
| Anonymous API Basic | `authenticated()` | Thường 401 + Basic challenge |
| JWT API không có bearer token | `authenticated()` | Thường 401 theo API entry point |

**302, 401 và 403 không phải thuộc tính của riêng predicate.** Nếu ứng dụng có custom `AuthenticationEntryPoint` trả JSON hoặc security chain stateless, response khác với form login.

### 10.1. Tại sao remember-me thiếu full có thể redirect thay vì 403?

`ExceptionTranslationFilter` có thể coi remember-me không đủ khi cần full, rồi gọi authentication entry point thay vì trả một trang forbidden đơn thuần. Đây là lý do form-login remembered user vào trang nhạy cảm thường được mời đăng nhập lại.

Không suy luận rằng redirect login chứng minh cookie remember-me “hỏng”. Cookie có thể hoàn toàn hợp lệ, nhưng trust level không đủ đối với rule.

## 11. Ví dụ Maven Spring Boot 3.3.5 và Java 17 hoàn chỉnh

Ứng dụng mẫu này sử dụng **Spring Security Servlet** với form login, remember-me cookie và một `SecurityFilterChain`. Nó gồm hai user, reader/admin, và các route thể hiện rõ bốn predicate.

**Lưu ý:** Mật khẩu và signing key chỉ phục vụ học tập ở localhost. Trong production phải dùng HTTPS, secret manager, key rotation, user store phù hợp, logging an toàn và chính sách thu hồi token.

### 11.1. Cấu trúc thư mục

```text
http-auth-levels/
  pom.xml
  src/
    main/java/example/authlevel/
      AuthLevelApplication.java
      SecurityConfig.java
      PageController.java
    test/java/example/authlevel/
      AuthLevelsMvcTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>http-auth-levels</artifactId>
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

### 11.3. Khởi động ứng dụng

File `src/main/java/example/authlevel/AuthLevelApplication.java`:

```java
package example.authlevel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthLevelApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthLevelApplication.class, args);
    }
}
```

### 11.4. SecurityConfig với route rules và role AND full

File `src/main/java/example/authlevel/SecurityConfig.java`:

```java
package example.authlevel;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    private static AuthorizationManager<RequestAuthorizationContext>
            adminAndFullyAuthenticated() {

        AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

        return (authenticationSupplier, requestContext) -> {
            Authentication current = authenticationSupplier.get();

            boolean full = current != null
                && trust.isFullyAuthenticated(current);

            boolean admin = current != null
                && current.getAuthorities().stream().anyMatch(
                    a -> "ROLE_ADMIN".equals(a.getAuthority()));

            return new AuthorizationDecision(full && admin);
        };
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http,
                                    UserDetailsService users)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/guest").anonymous()
                .requestMatchers("/account").authenticated()
                .requestMatchers("/remember-only").rememberMe()
                .requestMatchers("/settings").fullyAuthenticated()
                .requestMatchers("/admin-role-only").hasRole("ADMIN")
                .requestMatchers("/admin-sensitive")
                    .access(adminAndFullyAuthenticated())
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .rememberMe(me -> me
                .key("training-signing-key-not-for-production")
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(60 * 60 * 24 * 7)
                .userDetailsService(users))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích chi tiết:**

- `/public` dùng `permitAll`; anonymous, remembered và full đều vào được.
- `/guest` dùng `anonymous`; user đã xác thực bằng bất kỳ hai cách kia sẽ không khớp.
- `/account` dùng `authenticated`; remembered hợp lệ vẫn được phép.
- `/remember-only` dùng `rememberMe`; full user không tự được coi là remember-me.
- `/settings` dùng `fullyAuthenticated`; cần full, không chỉ cookie nhớ đăng nhập.
- `/admin-role-only` cố ý dùng role đơn thuần; remembered admin có thể truy cập — một ví dụ để hiểu lỗ hổng policy nếu endpoint thật nhạy cảm.
- `/admin-sensitive` dùng **custom AuthorizationManager** kiểm tra đồng thời `ROLE_ADMIN` **và** full. Đây là minh họa kết hợp điều kiện đúng, không dựa vào việc định nghĩa hai matcher cùng URL.
- `anyRequest().denyAll()` là fallback chặt chẽ cho URL chưa khai báo; nếu thêm route mới cần chủ động định nghĩa quyền.
- `formLogin` tạo trải nghiệm login tương tác và session; `rememberMe` đăng ký dịch vụ xác thực tự động bằng cookie.
- `logout` được giữ theo mặc định, bao gồm cơ chế logout/CSRF của form login. Không nên tắt CSRF để tránh test phải cấp token.

**Quan trọng:** custom `AuthorizationManager` ở đây làm rõ kỹ thuật AND cho bài học. Trong ứng dụng lớn, có thể dùng cơ chế kết hợp `AuthorizationManager` có sẵn hoặc method security phù hợp. Cần xác định yêu cầu full/recent MFA và ownership ở tầng nghiệp vụ, không chỉ so sánh chuỗi authority.

### 11.5. Controller

File `src/main/java/example/authlevel/PageController.java`:

```java
package example.authlevel;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/guest")
    String guestPage() {
        return "guest";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "account:" + authentication.getName();
    }

    @GetMapping("/remember-only")
    String rememberOnly(Authentication authentication) {
        return "remember:" + authentication.getName();
    }

    @GetMapping("/settings")
    String settings(Authentication authentication) {
        return "settings:" + authentication.getName();
    }

    @GetMapping("/admin-role-only")
    String adminRoleOnly(Authentication authentication) {
        return "role:" + authentication.getName();
    }

    @GetMapping("/admin-sensitive")
    String adminSensitive(Authentication authentication) {
        return "sensitive:" + authentication.getName();
    }
}
```

Controller không tự dùng `if (isRememberMe)` để phân quyền. `AuthorizationFilter` và `AuthorizationManager` kiểm tra trước khi request đi tới handler.

## 12. MockMvc: kiểm chứng qua form login và remember-me cookie thật

File `src/test/java/example/authlevel/AuthLevelsMvcTest.java`:

```java
package example.authlevel;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthLevelsMvcTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(String username, String password,
                            boolean remember) throws Exception {

        MockHttpServletRequestBuilder request = post("/login")
            .with(csrf())
            .param("username", username)
            .param("password", password);

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private Cookie rememberCookie(String username, String password)
            throws Exception {
        Cookie cookie = login(username, password, true)
            .getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        return cookie;
    }

    private MockHttpSession fullSession(String username, String password)
            throws Exception {
        MockHttpSession session = (MockHttpSession)
            login(username, password, false)
                .getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void anonymousCanUsePublicAndGuest() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/guest"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest"));
    }

    @Test
    void anonymousIsRedirectedFromAuthenticatedRoute()
            throws Exception {
        MvcResult result = mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void anonymousCannotUseRememberOnlyRoute()
            throws Exception {
        MvcResult result = mvc.perform(get("/remember-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void fullLoginCanUseAuthenticatedAndFullyAuthenticated()
            throws Exception {
        MockHttpSession session =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));

        mvc.perform(get("/settings").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("settings:reader"));
    }

    @Test
    void fullLoginDoesNotMatchAnonymous()
            throws Exception {
        MockHttpSession session =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/guest").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void fullLoginDoesNotMatchRememberMeOnly()
            throws Exception {
        MockHttpSession session =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/remember-only").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberedUserCanUseAuthenticated()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");

        // Không gửi .session(...): kiểm tra auto-login từ cookie.
        mvc.perform(get("/account").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("account:reader"));
    }

    @Test
    void rememberedUserMatchesRememberMeOnly()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");

        mvc.perform(get("/remember-only").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("remember:reader"));
    }

    @Test
    void rememberedUserMustReauthenticateForSettings()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");

        MvcResult result = mvc.perform(get("/settings")
                .cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNotNull(result.getResponse().getRedirectedUrl());
        assertTrue(result.getResponse().getRedirectedUrl()
            .contains("/login"));
    }

    @Test
    void rememberedUserIsNotAnonymous()
            throws Exception {
        Cookie cookie = rememberCookie("reader", "reader-pass");
        int status = mvc.perform(get("/guest").cookie(cookie))
            .andReturn().getResponse().getStatus();

        assertNotEquals(200, status);
    }

    @Test
    void adminRoleAloneCanBeSatisfiedByRememberMe()
            throws Exception {
        Cookie cookie = rememberCookie("admin", "admin-pass");

        mvc.perform(get("/admin-role-only").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("role:admin"));
    }

    @Test
    void adminSensitiveRequiresAdminAndFull()
            throws Exception {
        Cookie cookie = rememberCookie("admin", "admin-pass");

        int status = mvc.perform(get("/admin-sensitive")
                .cookie(cookie))
            .andReturn().getResponse().getStatus();
        assertNotEquals(200, status);

        MockHttpSession admin =
            fullSession("admin", "admin-pass");

        mvc.perform(get("/admin-sensitive").session(admin))
            .andExpect(status().isOk())
            .andExpect(content().string("sensitive:admin"));

        MockHttpSession reader =
            fullSession("reader", "reader-pass");

        mvc.perform(get("/admin-sensitive").session(reader))
            .andExpect(status().isForbidden());
    }
}
```

### 12.1. Các test có thực sự kiểm tra remember-me không?

Có: helper `rememberCookie(...)` POST `/login` với checkbox `remember-me` rồi lấy cookie được framework cấp. Request test kế tiếp **chỉ gửi cookie**, không gửi session đã dùng lúc login, nên filter remember-me phải xác thực lại cookie nếu muốn cho request tiếp tục.

Đây là phép kiểm thực tế hơn `.with(user("reader"))` — postprocessor đó dựng sẵn một principal thử nghiệm, có thể bỏ qua cookie authentication và không chứng minh remember-me services hoạt động.

### 12.2. Vì sao một số test không ép phải là 403?

Với remember-me token bị từ chối ở route yêu cầu full, `ExceptionTranslationFilter` có thể đưa người dùng trở lại login (302) thay vì 403. Đối với `anonymous()` từ remembered user hoặc custom manager, chính sách entry point có thể thay đổi cách response thể hiện.

Vì vậy có test chỉ assert **không 200** khi mục đích là chứng minh rule không cho phép, còn test full-login denial trong cấu hình web xác định thì assert 403. Khi triển khai thực, nên bổ sung assertions chính xác phù hợp entry point đã định nghĩa.

### 12.3. Mức tin cậy và role cần test cùng lúc

`adminSensitiveRequiresAdminAndFull` có ba trường hợp:

1. Admin remembered: role đúng, trust chưa đủ → không được phép.
2. Admin full: cả role và trust đúng → 200.
3. Reader full: trust đúng nhưng role thiếu → 403.

Đây là ma trận bắt lỗi mà một test “admin login vào được” đơn lẻ không phát hiện.

## 13. Chạy thử và những gì có thể kết luận

Từ thư mục `http-auth-levels` với JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

**Mười hai test dự kiến pass** nếu dependencies và cấu hình đúng. Đây là nhận định theo mã nguồn, không phải báo cáo một lượt Maven đã chạy; thời gian/log build có thể khác nhau theo máy.

Có thể dùng browser để mở `http://localhost:8080/account` rồi đăng nhập. Nếu chọn nhớ đăng nhập, khi session login cũ không còn nhưng remember-me cookie vẫn hợp lệ, `/account` có thể mở được trong khi `/settings` cần login tương tác. Khi sử dụng công cụ developer trên trình duyệt, **không tiết lộ giá trị cookie remember-me hoặc JSESSIONID**.

Các kết quả có thể quan sát theo rule:

| Thao tác | Kết quả với cấu hình mẫu |
| --- | --- |
| Anonymous GET `/public` | 200 `public` |
| Anonymous GET `/guest` | 200 `guest` |
| Anonymous GET `/account` | Redirect login |
| Full reader GET `/account` | 200 `account:reader` |
| Full reader GET `/settings` | 200 `settings:reader` |
| Full reader GET `/remember-only` | 403 |
| Remembered reader GET `/account` | 200 `account:reader` |
| Remembered reader GET `/remember-only` | 200 `remember:reader` |
| Remembered reader GET `/settings` | Redirect login |
| Remembered admin GET `/admin-role-only` | 200 `role:admin` |
| Remembered admin GET `/admin-sensitive` | Từ chối, yêu cầu trust phù hợp |
| Full admin GET `/admin-sensitive` | 200 `sensitive:admin` |
| Full reader GET `/admin-sensitive` | 403 |

Không tự suy ra “đã có cookie” là “cookie hợp lệ”: remember-me service phải kiểm tra chữ ký/thời hạn hoặc repository tương ứng trước khi tạo Authentication.

## 14. Java 17 độc lập: suy luận bằng bảng predicate

Để tự kiểm tra logic trước khi viết Spring Security configuration, có thể mô phỏng ba trạng thái bằng một enum. **Mã dưới không phải implementation AuthenticationTrustResolver**; nó chỉ biểu diễn bảng chân trị của các token chuẩn trong ví dụ.

Tạo file `HttpTrustRulesDemo.java`:

```java
public class HttpTrustRulesDemo {
    enum Kind {
        ANONYMOUS, REMEMBER_ME, FULL
    }

    static boolean authenticated(Kind kind) {
        return kind != Kind.ANONYMOUS;
    }

    static boolean fullyAuthenticated(Kind kind) {
        return kind == Kind.FULL;
    }

    static boolean rememberMe(Kind kind) {
        return kind == Kind.REMEMBER_ME;
    }

    static boolean anonymous(Kind kind) {
        return kind == Kind.ANONYMOUS;
    }

    static void print(Kind kind) {
        System.out.printf(
            "%s: authenticated=%b full=%b rememberMe=%b anonymous=%b%n",
            kind,
            authenticated(kind),
            fullyAuthenticated(kind),
            rememberMe(kind),
            anonymous(kind)
        );
    }

    public static void main(String[] args) {
        for (Kind kind : Kind.values()) {
            print(kind);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac HttpTrustRulesDemo.java
java HttpTrustRulesDemo
```

Stdout **chính xác** với Java 17:

```text
ANONYMOUS: authenticated=false full=false rememberMe=false anonymous=true
REMEMBER_ME: authenticated=true full=false rememberMe=true anonymous=false
FULL: authenticated=true full=true rememberMe=false anonymous=false
```

Java enum ở đây không có `SecurityContextHolder`, token hay servlet. Dùng nó để suy luận, rồi kiểm tra hành vi HTTP thật bằng MockMvc như phần 12.

## 15. Bảo mật remember-me và quyền truy cập nhạy cảm

### 15.1. Remember-me cookie là credential

Token nhớ đăng nhập có thể sống lâu hơn HTTP session. Nếu kẻ tấn công chiếm cookie còn hợp lệ, họ có thể được nhận diện là user đó ở mức remember-me. Do đó:

- Dùng HTTPS, cookie flags phù hợp, cấu hình domain/path cẩn thận.
- Không đưa token/cookie vào URL, log, metric labels hoặc ảnh chụp màn hình.
- Có chính sách thời hạn và lựa chọn tắt remember-me, đặc biệt trên máy dùng chung.
- Khi ứng dụng có yêu cầu thu hồi token theo thiết bị, cân nhắc persistent-token design và kho lưu trạng thái.
- Với token-based thuần có chữ ký, xóa cookie trong browser không tự vô hiệu hóa bản sao cookie đã bị đánh cắp.
- Đổi mật khẩu hoặc khóa tài khoản không được mặc định làm mất hiệu lực mọi session hiện hành; cần quy trình revoke tương ứng.

### 15.2. Logout cần xét cả session và remember-me

Logout form thường clear SecurityContext/invalidate session và gọi remember-me logout handler để xóa cookie của browser. Nhưng logout trên một thiết bị không nhất thiết xóa phiên/remember-me token trên mọi thiết bị. Nếu cần “logout everywhere”, phải quản lý session store/registry và token repository theo policy cụ thể.

### 15.3. CSRF và full authentication là hai lớp khác nhau

Cookie-authenticated request — kể cả remember-me — có thể bị browser tự động đính kèm credential. Đối với endpoint có tác dụng phụ như POST thay đổi dữ liệu, cần CSRF protection phù hợp. `fullyAuthenticated()` không tự bảo vệ khỏi CSRF; người dùng full login vẫn có thể bị CSRF nếu thiết kế thiếu kiểm soát.

**Không dùng GET cho hành động thay đổi trạng thái** chỉ vì route bảo vệ bằng full authentication. Cần HTTP semantics, CSRF, idempotency, validation và authorization theo nghiệp vụ.

## 16. Các lỗi thường gặp khi viết HTTP authorization rules

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dựa duy nhất vào `Authentication.isAuthenticated()` | Anonymous token có thể làm code tưởng user đã login | Dùng `authenticated()`/trust resolver |
| Nghĩ `authenticated()` loại remember-me | Cookie nhớ đăng nhập vẫn có thể vào route | Dùng `fullyAuthenticated()` khi cần trust cao hơn |
| Nghĩ `fullyAuthenticated()` chứng minh MFA | Sai chính sách với tác vụ nhạy cảm | Thêm step-up/MFA và recent-auth checks |
| Nghĩ `rememberMe()` cho phép full login | Full token không được phân loại là remember-me | Dùng `authenticated()` nếu muốn cả hai |
| Dùng `anonymous()` cho trang public | Người đã login bị từ chối | Dùng `permitAll()` |
| Nghĩ `hasRole("ADMIN")` tự yêu cầu full | Remembered admin có thể giữ role | Kết hợp role AND full trust |
| Định nghĩa hai rule cho cùng URL và mong chúng tự AND | Rule đầu tiên phù hợp được sử dụng | Dùng một AuthorizationManager kết hợp |
| Đặt `anyRequest` trước các matcher cụ thể | Mất hoặc lỗi cấu hình policy cụ thể | Đặt matcher cụ thể trước fallback |
| Chỉ thêm `rememberMe()` rule nhưng chưa bật `http.rememberMe` | Không có cookie authentication | Cấu hình mechanism và authorization riêng |
| Mặc định mọi denial cho fullyAuthenticated đều là 403 | Browser remembered có thể bị redirect login | Test entry point, denied handler và loại authentication |
| Test bằng `.with(user("reader"))` rồi khẳng định remember-me hoạt động | Bypass actual cookie authentication | Test POST login thật, lấy cookie và request không session |
| Dùng token signing key hardcode ở production | Lộ khóa, tăng khả năng giả mạo cookie | Secret manager, rotation và quản lý node |
| Truy cập entity chỉ vì đã authenticated | Có thể lộ tài nguyên của user khác | Kiểm tra ownership, tenant và domain policy |
| Tắt CSRF vì đã yêu cầu fullyAuthenticated | Không chặn request giả mạo từ browser | Giữ CSRF protection phù hợp |
| Chỉ xóa cookie để thu hồi token-based stolen cookie | Bản sao cookie có thể còn hợp lệ | Thiết kế revocation thực sự |
| Không kiểm thử thứ tự request matchers | Endpoint bị áp dụng rule rộng hơn | Test URL chồng lấp và fallback deny |
| Dùng chung giả định form login và JWT API | Response 302/401/403 sai kỳ vọng | Kiểm tra security chain/entry point thực tế |

## 17. Quy trình debug một request không đúng kỳ vọng

1. **Request vào SecurityFilterChain nào?** Xem `securityMatcher`, `@Order` và filter chain thực sự được chọn.
2. **Authentication từ đâu?** Session, form login, remember-me cookie, HTTP Basic, bearer token hay custom provider?
3. **Đã có Authentication trước RememberMeAuthenticationFilter chưa?** Full session còn tồn tại thường khiến remember-me filter không cần autoLogin.
4. **Token class là gì?** `AnonymousAuthenticationToken`, `RememberMeAuthenticationToken` hay một Authentication khác?
5. **Trust resolver phân loại ra sao?** `anonymous`, `rememberMe`, `authenticated`, `fullyAuthenticated` là điều kiện chính của bài.
6. **Rule HTTP nào match đầu tiên?** Có `requestMatchers` rộng hoặc `anyRequest` đặt sai thứ tự không?
7. **Route yêu cầu cả role và trust hay chỉ một trong hai?** Với admin, đừng chỉ xem `ROLE_ADMIN`.
8. **Response do handler nào tạo ra?** Entry point redirect login, Basic challenge 401, hay AccessDeniedHandler 403?
9. **Cookie có hợp lệ không?** Thời hạn, signature/key, user store, token repository, path/domain, Secure/SameSite và môi trường.
10. **Session có được gửi cùng request test không?** Nếu vô tình gửi session full, bạn không còn đang kiểm thử remember-me.
11. **CSRF có chặn POST không?** Đừng nhầm 403 từ CSRF với thất bại `fullyAuthenticated`.
12. **Method/business policy có chặn tiếp không?** HTTP rule granted chưa chắc controller/service đã cho phép.
13. **Custom AuthenticationTrustResolver?** Nếu có, test phân loại token/custom principal phù hợp.
14. **Có cơ chế token phụ?** Logout session không đồng nghĩa đã revoke remember-me hoặc access token độc lập.

Có thể bật logging chẩn đoán trong môi trường phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

Không ghi raw token, password, remember-me cookie, session ID, hoặc toàn bộ Authorization header vào log.

## 18. Câu hỏi ôn tập có đáp án

**Câu 1.** User chưa login nhưng `AnonymousAuthenticationFilter` đã đặt AnonymousAuthenticationToken. `Authentication.isAuthenticated()` có thể true; `authenticated()` có cho vào `/account` không?

**Đáp án:** Không theo trust resolver/authorization thông thường. Predicate `authenticated()` phân biệt anonymous chứ không chỉ dựa vào flag của token.

**Câu 2.** User đăng nhập bằng form, session hết hạn nhưng remember-me cookie còn hợp lệ. `/account` dùng `authenticated()`, `/settings` dùng `fullyAuthenticated()`. Kết quả?

**Đáp án:** `/account` có thể được phép nếu autoLogin tạo RememberMeAuthenticationToken hợp lệ. `/settings` không được phép chỉ bằng remember-me và có thể đưa user về login để nâng cấp xác thực.

**Câu 3.** Full user vào `/remember-only` có được phép không?

**Đáp án:** Không, nếu rule là `rememberMe()` chính xác. Full token không được resolver phân loại là remember-me.

**Câu 4.** Nếu trang `/info` phải công khai cho cả khách và thành viên, nên dùng `anonymous()` hay `permitAll()`?

**Đáp án:** `permitAll()`. `anonymous()` loại authenticated/remembered users.

**Câu 5.** Admin remembered có `ROLE_ADMIN`, endpoint `/admin` chỉ có `hasRole("ADMIN")`. Có thể được phép không?

**Đáp án:** Có thể, vì rule role không tự bắt fullyAuthenticated. Khi endpoint nhạy cảm, kết hợp authority AND trust/full/step-up theo policy.

**Câu 6.** Đặt một rule `.requestMatchers("/settings").authenticated()` rồi một rule khác `.requestMatchers("/settings").fullyAuthenticated()` có bảo đảm cả hai chạy không?

**Đáp án:** Không. Matcher đầu tiên phù hợp được dùng. Hãy đặt một rule đáp ứng yêu cầu hoặc kết hợp bằng AuthorizationManager.

**Câu 7.** `fullyAuthenticated()` có tự xác nhận người dùng vừa nhập OTP 5 phút trước không?

**Đáp án:** Không. Nó không lưu bằng chứng MFA hoặc thời điểm step-up.

**Câu 8.** Test sử dụng `.with(user("reader"))` vào `/account` rồi nói remember-me cookie tốt, có thuyết phục không?

**Đáp án:** Không. Postprocessor đó cấp principal thử nghiệm, có thể bypass cơ chế cookie. Cần login thật, lấy remember-me cookie và gửi request mới không session.

**Câu 9.** Request remembered vào `/settings` bị redirect tới `/login`. Có chắc cookie đã bị lỗi không?

**Đáp án:** Không. Cookie có thể hợp lệ nhưng mức độ tin cậy chưa đạt `fullyAuthenticated()`.

**Câu 10.** Sau logout browser xóa remember-me cookie, một bản sao cookie token-based đã bị lấy cắp có chắc bị thu hồi không?

**Đáp án:** Không, nếu không có cơ chế thu hồi server-side hoặc dữ liệu dùng kiểm tra token chưa thay đổi. Phải thiết kế revocation phù hợp.

## 19. Checklist áp dụng trước khi triển khai

**Chọn rule theo yêu cầu:**

- Trang có cần mọi người đọc? Dùng `permitAll`.
- Trang chỉ dành người chưa login? Dùng `anonymous` nếu UX cần.
- Chấp nhận remembered và full? Dùng `authenticated`.
- Chỉ chấp nhận request đúng là remember-me? Dùng `rememberMe` (hiếm khi là yêu cầu sản phẩm).
- Cần full tương tác? Dùng `fullyAuthenticated`; thêm MFA/recent authentication nếu nhạy cảm.
- Cần role/authority/ownership? Kết hợp tường minh, không suy luận từ trust level.

**Kiểm thử:**

- Anonymous, remembered và full đều có test.
- Kiểm tra full token không thỏa `rememberMe` và remembered token không thỏa `fullyAuthenticated`.
- Có test role đúng nhưng trust thiếu, trust đúng nhưng role thiếu.
- Test phân biệt form redirect và API entry point.
- Test cookie nhớ đăng nhập qua request **không truyền session cũ**.
- Bảo vệ CSRF cho request có tác dụng phụ và không log secret.

**Vận hành:**

- Bảo vệ remember-me cookie như credential.
- Xem xét TTL, rotation, revoke, multi-device và logout-all.
- Đảm bảo policy quyền ở controller/service phù hợp với security chain.
- Không nhầm full authentication với chứng cứ MFA/độ mới xác thực.

## 20. Ghi nhớ trọng tâm

- `authenticated()` chấp nhận **remember-me hoặc full**, không chấp nhận anonymous.
- `fullyAuthenticated()` chỉ chấp nhận authentication được trust resolver xem là **full**, loại remember-me và anonymous.
- `rememberMe()` chỉ chấp nhận trạng thái **remember-me**; full login không tự thỏa matcher này.
- `anonymous()` chỉ dành cho **anonymous**; trang công khai cho tất cả phải dùng `permitAll()`.
- `AuthenticationTrustResolver` giúp phân loại token; không dựa duy nhất vào `Authentication.isAuthenticated()` để suy ra người dùng thật đã login.
- `hasRole`/`hasAuthority` kiểm tra quyền, không tự kiểm tra full trust. Với route nhạy cảm, kết hợp các điều kiện bằng **một** `AuthorizationManager` hoặc method security phù hợp.
- Quy tắc HTTP chạy trong **SecurityFilterChain đã chọn**, và matcher cụ thể phải đứng trước fallback. Đừng nhầm `requestMatchers` với `securityMatcher`.
- Test bằng cookie remember-me được cấp từ login thật, **không gửi session**, để xác minh đúng sự khác biệt giữa remembered và full authentication.
