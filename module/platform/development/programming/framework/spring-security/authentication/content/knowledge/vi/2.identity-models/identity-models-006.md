# isAuthenticated biểu diễn trạng thái nội bộ, không thay thế việc kiểm tra bằng chứng

> **Chủ đề:** Spring Security — Authentication → Mô hình danh tính. Bài học tập trung vào ý nghĩa chính xác của `Authentication.isAuthenticated()`, cách giá trị này được tạo trong một luồng xác thực đáng tin, vì sao `true` không tự chứng minh một người hay token là thật, và cách Spring Security xử lý anonymous, remember-me, phân quyền. Ví dụ hoàn chỉnh sử dụng Java 17+, Spring Boot 3.3.x và Spring Security 6.x (Servlet).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `isAuthenticated()` là **trạng thái được ghi trên đối tượng `Authentication`**; nêu ai có quyền tạo trạng thái đáng tin và vì sao giá trị boolean không phải bằng chứng mật mã.
2. Phân biệt **credential chưa kiểm tra**, **credential đã được xác thực**, **`Authentication` đã được lưu vào `SecurityContext`** và **quyền truy cập đã được cho phép**.
3. Hiểu trường hợp `AnonymousAuthenticationToken.isAuthenticated() == true` nhưng quy tắc `authenticated()` vẫn từ chối anonymous.
4. Phân biệt `authenticated()`, `fullyAuthenticated()`, `hasAuthority(...)`, và lý do remember-me không tương đương xác thực đầy đủ theo quy ước framework.
5. Tránh tạo `Authentication` “đã xác thực” trực tiếp từ dữ liệu HTTP, JWT chưa kiểm chữ ký, header tự khai hoặc kết quả test giả lập.
6. Viết và kiểm tra một ứng dụng Spring Security minh họa sự khác nhau giữa cờ nội bộ, mức tin cậy và quyền truy cập.

## 2. Câu hỏi cốt lõi: boolean đó thực sự nói lên điều gì?

Trong Spring Security, `Authentication` vừa đại diện cho **yêu cầu xác thực** (trước khi kiểm tra bằng chứng) vừa đại diện cho **kết quả xác thực** (sau khi cơ chế đáng tin xử lý). Giao diện này có phương thức:

~~~java
boolean isAuthenticated();
~~~

Giá trị `true` thông thường có nghĩa: **thành phần xác thực của ứng dụng đã đánh dấu đối tượng này là kết quả tin cậy để framework sử dụng tiếp**, giúp những bước xử lý sau không phải lặp lại toàn bộ quá trình xác thực trong mỗi lần kiểm tra. Nó là một phần hợp đồng nội bộ giữa thành phần tạo `Authentication` và thành phần sử dụng `Authentication`.

Giá trị đó **không tự trả lời** các câu hỏi:

- Người dùng đã nhập đúng mật khẩu, hoàn tất MFA, dùng passkey hay được xác minh bằng cơ chế nào?
- JWT đã được kiểm chữ ký, `iss`, `aud`, `exp`, `nbf` và các điều kiện của resource server chưa?
- Tài khoản còn hoạt động, phiên còn hợp lệ, hay quyền vừa bị thu hồi?
- Chủ thể có được sửa đúng tài nguyên/tenant đang yêu cầu không?
- Đối tượng `Authentication` do authentication filter/provider tin cậy tạo ra, hay do code không đáng tin dựng thủ công?

**Nguyên tắc:** `isAuthenticated()` phản ánh **một kết quả xác thực mà hệ thống đang tin**, không phải công cụ tự mình xác minh bằng chứng. Nếu nguồn tạo kết quả không đáng tin thì cờ có thể sai; kiểm tra lại cùng cờ đó không khắc phục được nguồn gốc sai.

### Các trường thường gặp của Authentication

| Thuộc tính/phương thức | Ý nghĩa | Không được ngộ nhận |
| --- | --- | --- |
| `getPrincipal()` | Chủ thể hoặc dữ liệu đại diện chủ thể; kiểu cụ thể phụ thuộc cơ chế xác thực | Principal có tên “admin” nghĩa là đã kiểm tra mật khẩu |
| `getCredentials()` | Thông tin xác thực đưa vào yêu cầu hoặc còn giữ trong token | Có mật khẩu/token trong object tức là chúng hợp lệ |
| `getAuthorities()` | Các `GrantedAuthority` mà cơ chế bảo mật đã đưa vào kết quả | Authority là quyền truy cập mọi dữ liệu mà không cần kiểm tra ngữ cảnh |
| `isAuthenticated()` | Trạng thái nội bộ của `Authentication` | `true` là bằng chứng mã hóa, MFA, hay giấy phép cho mọi hành động |
| `getDetails()` | Thông tin bổ sung, thường là ngữ cảnh request | Details tự động đáng tin nếu chúng lấy trực tiếp từ request |

Trong một số triển khai, credential có thể được xóa sau khi xác thực thành công để hạn chế rò rỉ. Vì vậy `getCredentials() == null` cũng **không** chứng minh việc xác thực chưa từng diễn ra.

## 3. Luồng xác thực đúng: bằng chứng đến trước, trạng thái đến sau

Ví dụ đăng nhập bằng tên/mật khẩu qua Spring Security Servlet:

~~~mermaid
sequenceDiagram
    participant Client
    participant Filter as Authentication Filter
    participant Manager as AuthenticationManager
    participant Provider as AuthenticationProvider
    participant Store as User Store / PasswordEncoder
    participant Context as SecurityContext
    Client->>Filter: Gửi username + password qua HTTPS
    Filter->>Manager: Authentication chưa xác thực
    Manager->>Provider: authenticate(request)
    Provider->>Store: Tra cứu account + kiểm tra credential, chính sách
    alt Bằng chứng hợp lệ
        Store-->>Provider: Xác minh thành công
        Provider-->>Manager: Authentication kết quả đáng tin
        Manager-->>Filter: Authentication thành công
        Filter->>Context: Lưu Authentication cho xử lý tiếp
    else Bằng chứng không hợp lệ
        Provider-->>Manager: AuthenticationException
        Manager-->>Filter: Thất bại
        Filter-->>Client: AuthenticationEntryPoint/failure handler
    end
~~~

**Trước khi kiểm tra:** đối tượng yêu cầu có thể chứa username và password nhưng chưa có cơ sở để tin, do đó thông thường mang trạng thái `false`.

**Sau khi kiểm tra:** `AuthenticationManager` chuyển yêu cầu cho `AuthenticationProvider` phù hợp. Provider kiểm bằng chứng và các điều kiện cần thiết; khi thành công, trả đối tượng kết quả đã xác thực với authorities được gán từ nguồn đáng tin. Cơ chế filter đặt kết quả vào `SecurityContext`. Khi thất bại, throw `AuthenticationException` và không tự đánh dấu thành công.

Ví dụ **đoạn minh họa tích hợp**, không phải chương trình độc lập:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(username, password);

// authManager phải được cấu hình với provider có thể kiểm bằng chứng.
// authenticate(...) có thể ném AuthenticationException.
Authentication verified = authenticationManager.authenticate(request);

// Chỉ nhánh thành công mới dùng kết quả cho SecurityContext.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

Đoạn trên giả định `username`, `password` và `authenticationManager` đã được khai báo trong thành phần xác thực tin cậy. Với ứng dụng web thông thường, hãy để **filter và cơ chế chuẩn của Spring Security** thực hiện công việc này, bao gồm quản lý context, session và sự kiện thành công/thất bại. Đừng tự viết controller xử lý đăng nhập rồi chỉ kiểm một boolean.

**Phân biệt nguồn bằng chứng:** mật khẩu được kiểm bằng `PasswordEncoder.matches(...)` trên hash đã lưu; JWT bearer access token cần `JwtDecoder` và các validator phù hợp; opaque access token cần introspection; mTLS cần xác thực chuỗi chứng chỉ và quy tắc ánh xạ danh tính. `isAuthenticated()` không thực hiện các phép kiểm đó thay cho từng cơ chế.

## 4. Vì sao cờ nội bộ không tự bảo đảm an toàn?

Xét đoạn code sai ý tưởng:

~~~java
// MINH HỌA SAI — không đưa vào mã ứng dụng!
Authentication trustedLooking =
        UsernamePasswordAuthenticationToken.authenticated(
                requestBody.username(),
                null,
                AuthorityUtils.createAuthorityList("ROLE_ADMIN"));
~~~

Nếu tạo object đã đánh dấu trusted **trực tiếp từ `requestBody` do người gọi kiểm soát**, code đã bỏ qua bước chứng minh họ sở hữu tài khoản, rồi còn tự cấp authority `ROLE_ADMIN`. Factory `authenticated(...)` tạo ra một đối tượng có trạng thái đã xác thực; nó **không** tự kiểm mật khẩu. Đoạn này chỉ được trình bày để nhận diện anti-pattern, **không phải cách triển khai đăng nhập**.

Đối tượng `Authentication` có thể được tạo bởi code Java. `SecurityContextHolder` cũng có API ghi vào context. Nếu tầng không tin cậy được quyền đặt một token “đã xác thực” vào context, ứng dụng có thể tin sai. Một số triển khai token (như `UsernamePasswordAuthenticationToken`) ngăn gọi `setAuthenticated(true)` trực tiếp; việc ngăn setter này không loại bỏ mọi cách tạo token trusted hoặc chặn lỗi thiết kế ở lớp ứng dụng. Vì vậy **nguồn tạo đối tượng và ranh giới tin cậy mới là điều quyết định**.

Các ví dụ sai khác:

1. **Client gửi `{"isAuthenticated": true}` trong JSON.** Đây chỉ là dữ liệu do người gọi khai báo; API không được dùng nó làm kết quả xác thực.
2. **Decode JWT rồi dựng `JwtAuthenticationToken` có authorities.** Đọc payload JWT bằng Base64 không kiểm chữ ký, issuer, audience, thời gian và policy. Resource Server phải xác minh token trước khi tạo principal đáng tin.
3. **Tin header `X-Authenticated-User` từ Internet.** Header chỉ có thể là nguồn pre-authentication trong kiến trúc proxy tin cậy đã xác thực upstream, loại bỏ header do client tự gửi và ngăn mọi đường truy cập vòng qua proxy.
4. **Lưu `Authentication` vào session/context rồi coi nó là bằng chứng còn hiệu lực vô thời hạn.** Niềm tin vào phiên còn phụ thuộc session cookie, session store, hạn sử dụng, logout, khóa tài khoản, thu hồi quyền và chính sách kiểm tra lại.
5. **Thấy `isAuthenticated() == true` rồi bỏ phân quyền.** Xác thực một chủ thể chưa quyết định chủ thể đó có quyền thao tác trên từng báo cáo, hóa đơn hay tenant.

Câu hỏi kiểm toán hữu ích nhất là: **Ai đã xác minh bằng chứng trước khi đối tượng này được đánh dấu trusted, và bước nào bảo vệ đường đi từ kết quả đến lúc sử dụng?**

## 5. Trường hợp dễ gây nhầm: anonymous vẫn có Authentication

Khi anonymous support được bật (thông thường theo cấu hình HTTP mặc định), `AnonymousAuthenticationFilter` có thể chèn `AnonymousAuthenticationToken` vào `SecurityContextHolder` nếu chưa có người dùng đăng nhập. Mục đích là giúp filter, audit và cơ chế truy cập luôn có một principal đại diện cho khách vãng lai.

**Đáng chú ý:** `AnonymousAuthenticationToken.isAuthenticated()` có thể trả về **`true`**. Điều này **không** có nghĩa người dùng anonymous đã đăng nhập bằng mật khẩu hay có danh tính con người được kiểm chứng.

Spring Security không dựa duy nhất vào giá trị raw này trong quy tắc `authenticated()`. Framework có `AuthenticationTrustResolver` để nhận diện anonymous và remember-me, rồi quyết định mức tin cậy phù hợp.

### So sánh ba cách đọc trạng thái

| Trạng thái điển hình | `auth.isAuthenticated()` | `trustResolver.isAuthenticated(auth)` | `trustResolver.isFullyAuthenticated(auth)` |
| --- | --- | --- | --- |
| Không có `Authentication` (null) | Không thể gọi trực tiếp | `false` | `false` |
| `UsernamePasswordAuthenticationToken` mới tạo bằng `unauthenticated(...)` | `false` | `false` | `false` |
| `AnonymousAuthenticationToken` của cấu hình chuẩn | `true` | `false` | `false` |
| `RememberMeAuthenticationToken` do cơ chế remember-me đáng tin tạo | `true` | `true` | `false` |
| Token username/password được provider xác thực thành công | `true` | `true` | `true` |
| `JwtAuthenticationToken` do Resource Server tạo **sau validation hợp lệ** | `true` | `true` | `true` theo phân loại mặc định |

Bảng mô tả **các token điển hình do cơ chế Spring Security chuẩn tạo ra**. Nếu ứng dụng có custom token/custom trust resolver, hành vi phụ thuộc cách hiện thực; trường hợp tự dựng trusted token trước khi kiểm bằng chứng vốn đã là lỗi.

- `Authentication.isAuthenticated()`: chỉ đọc **cờ trên object**.
- `AuthenticationTrustResolver.isAuthenticated(auth)`: xét object tồn tại, raw flag là true và **không phải anonymous**.
- `AuthenticationTrustResolver.isFullyAuthenticated(auth)`: đòi mức trên và **không phải remember-me**.

**Fully authenticated không đồng nghĩa vừa nhập mật khẩu, có MFA, đã kiểm danh tính thật ở độ bảo đảm cao, hay có quyền admin.** Nó là phân loại mức xác thực theo mô hình anonymous/remember-me của Spring Security. Muốn bắt buộc MFA hoặc re-authentication cho thao tác nhạy cảm phải thiết kế chính sách riêng (ví dụ kiểm thông tin `amr/acr/auth_time` từ issuer đã xác minh nếu phù hợp và một cơ chế step-up thật).

### Đọc ngữ cảnh anonymous đúng cách

Với Spring MVC, tham số handler kiểu `Authentication` thường đi qua servlet `HttpServletRequest#getPrincipal()`, có thể là **null khi anonymous**, dù `SecurityContextHolder` đang có `AnonymousAuthenticationToken`. Để kiểm tra context thực tế trong trường hợp anonymous, dùng `@CurrentSecurityContext` hoặc `SecurityContextHolder`, rồi để `AuthenticationTrustResolver` phân loại:

~~~java
@GetMapping("/state")
public Map<String, Object> state(@CurrentSecurityContext SecurityContext context) {
    Authentication authentication = context.getAuthentication();
    AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

    return Map.of(
            "rawFlag", authentication != null && authentication.isAuthenticated(),
            "recognizedAsAuthenticated", resolver.isAuthenticated(authentication),
            "fullyAuthenticated", resolver.isFullyAuthenticated(authentication));
}
~~~

Đây là **đoạn method tích hợp** cần các import Spring và một lớp `@RestController`; xem ví dụ ứng dụng hoàn chỉnh ở phần dưới. Chỉ dùng output trạng thái này cho mục đích học/debug phù hợp, không công khai thêm thông tin phiên hoặc credential.

## 6. Từ Authentication tới Authorization: các cổng quyết định khác nhau

Trong Spring Security Servlet, cơ chế xác thực thiết lập principal; sau đó `AuthorizationFilter` và/hoặc method security áp dụng chính sách truy cập. Những điều kiện phổ biến:

| Điều kiện bảo vệ | Ý nghĩa gần đúng | Có tự kiểm mật khẩu/JWT? |
| --- | --- | --- |
| `permitAll()` | Endpoint công khai trong phạm vi filter chain; không bắt buộc principal đăng nhập | Không |
| `authenticated()` | Yêu cầu principal được Spring Security nhận diện là authenticated, **loại anonymous** | Không — dựa trên kết quả xác thực đã có |
| `fullyAuthenticated()` | Yêu cầu authenticated và **không thuộc remember-me/anonymous** | Không — không thay thế MFA |
| `hasAuthority("reports:read")` | Yêu cầu có authority chính xác được cơ chế trusted cung cấp | Không — đây là kiểm tra quyền |
| `hasRole("ADMIN")` | Theo prefix mặc định, kiểm `ROLE_ADMIN` | Không — role phải có nguồn tin cậy |
| Kiểm tenant/ownership trong service | Xác minh chủ thể được thao tác trên **bản ghi cụ thể** | Không — là ranh giới phân quyền nghiệp vụ |

Với method security, biểu thức `@PreAuthorize("isAuthenticated()")` là biểu thức ủy quyền sử dụng semantics của framework, không nhất thiết tương đương với việc một lập trình viên tự gọi `auth.isAuthenticated()`. Tương tự, `@PreAuthorize("isFullyAuthenticated()")` không xác minh lại bằng chứng vừa gửi ở tầng HTTP.

**Không nhầm 401 và 403:**
- Khi request không có bằng chứng đăng nhập hợp lệ, endpoint yêu cầu xác thực thường trả **401** trong API dùng HTTP Basic/Bearer (hoặc chuyển hướng trang đăng nhập trong web có form login).
- Khi danh tính đã được xác thực nhưng thiếu quyền, response thường là **403**.
- Mã phản hồi thực tế tùy entry point, filter chain và thiết kế ứng dụng.

Đừng dùng thông tin kiểm quyền chưa qua xác minh từ client để “nâng cấp” `Authentication`. Cả principal và authority phải có provenance rõ ràng từ quá trình xác thực/ánh xạ quyền đã tin cậy.

## 7. Ứng dụng minh họa chạy được: raw flag, anonymous và kiểm quyền

Đây là **project Spring Boot độc lập**; dùng Java 17, Gradle 8.x, Spring Boot 3.3.5. Nó sử dụng HTTP Basic và hai tài khoản **chỉ cho môi trường demo**. Mật khẩu demo được băm lúc khởi động bằng BCrypt. Không dùng cách cấu hình `InMemoryUserDetailsManager` hay mật khẩu tĩnh này cho production.

Cấu trúc dự án:

~~~text
auth-flag-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/authflag/
    │   ├── AuthFlagDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/authflag/
        └── AuthenticationBoundaryTest.java
~~~

### 7.1. Cấu hình Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-flag-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Điểm vào ứng dụng

`src/main/java/example/authflag/AuthFlagDemoApplication.java`:

~~~java
package example.authflag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthFlagDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthFlagDemoApplication.class, args);
    }
}
~~~

### 7.3. Cấu hình xác thực và phân quyền

`src/main/java/example/authflag/SecurityConfig.java`:

~~~java
package example.authflag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/state").permitAll()
                .requestMatchers("/reports").hasAuthority("reports:read")
                .requestMatchers("/self").authenticated()
                .requestMatchers("/confirm").fullyAuthenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demoPass!"))
                .authorities("reports:read")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demoPass!"))
                .authorities("profile:read")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

**Giải thích:** HTTP Basic filter lấy credential từ header `Authorization` và dùng cơ chế xác thực của Spring Security. `PasswordEncoder` kiểm password với hash. Hai user được provider xác thực dựa trên mật khẩu và trạng thái account; authority chỉ được gán theo cấu hình phía server.

Điều kiện `authenticated()` ở `/self` dựa trên kết quả xác thực của request. Điều kiện `hasAuthority("reports:read")` ở `/reports` đòi thêm quyền phù hợp. `fullyAuthenticated()` ở `/confirm` minh họa phân loại mức xác thực; với HTTP Basic thông thường không bật remember-me, một request Basic hợp lệ thuộc mức fully authenticated theo cách phân loại này. Nó **không** chứng minh có MFA.

### 7.4. Controller chỉ hiển thị trạng thái cần học

`src/main/java/example/authflag/DemoController.java`:

~~~java
package example.authflag;

import java.util.Map;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/state")
    public Map<String, Object> state(
            @CurrentSecurityContext SecurityContext context) {
        Authentication auth = context.getAuthentication();
        AuthenticationTrustResolver resolver = new AuthenticationTrustResolverImpl();

        return Map.of(
                "kind", auth == null ? "none" : auth.getClass().getSimpleName(),
                "rawFlag", auth != null && auth.isAuthenticated(),
                "recognizedAsAuthenticated", resolver.isAuthenticated(auth),
                "fullyAuthenticated", resolver.isFullyAuthenticated(auth));
    }

    @GetMapping("/self")
    public String self(Authentication auth) {
        return auth.getName();
    }

    @GetMapping("/reports")
    public String reports() {
        return "REPORT_OK";
    }

    @GetMapping("/confirm")
    public String confirm() {
        return "NON_REMEMBER_ME";
    }
}
~~~

Nhánh `/state` được `permitAll()` cho phép quan sát cách framework biểu diễn anonymous. Ở request thông thường không có Basic credentials, `AnonymousAuthenticationFilter` đưa một `AnonymousAuthenticationToken` vào context. Vì vậy có thể nhận `rawFlag = true` nhưng `recognizedAsAuthenticated = false`. Đó chính là khác biệt mà bài học cần làm rõ.

### 7.5. Kiểm thử tự động với MockMvc

`src/test/java/example/authflag/AuthenticationBoundaryTest.java`:

~~~java
package example.authflag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousFlagIsTrueButNotAuthenticatedForAuthorization() throws Exception {
        mvc.perform(get("/state"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rawFlag").value(true))
                .andExpect(jsonPath("$.recognizedAsAuthenticated").value(false))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false));
    }

    @Test
    void anonymousCannotReadReports() throws Exception {
        mvc.perform(get("/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validUserWithoutPermissionIsForbidden() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("bob", "demoPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void validUserWithPermissionCanReadReports() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("alice", "demoPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("REPORT_OK"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/self").with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**Điều các test thực sự kiểm tra:** request đi qua HTTP Basic filter và provider của ứng dụng; password demo được kiểm bởi encoder; controller nhận trạng thái context sau filter. Bài test đầu cho thấy **raw flag true không đủ để vượt qua yêu cầu `authenticated()`**. Các test còn lại tách riêng việc chứng minh credential và điều kiện quyền.

Một test dùng `@WithMockUser` hoặc gắn `Authentication` trực tiếp bằng test helper **không kiểm thử đường xác minh mật khẩu thật**; nó hữu ích cho test phân quyền ở tầng riêng, nhưng không thay thế test end-to-end hoặc integration test của authentication filter/provider/decoder.

### 7.6. Chạy thử và kết quả mong đợi

Từ thư mục project, với JDK 17+ và Gradle được cài đặt hoặc Gradle Wrapper phù hợp:

~~~bash
gradle test
gradle bootRun
~~~

Nếu project có Gradle Wrapper, dùng `./gradlew test` và `./gradlew bootRun` (Windows PowerShell có thể dùng `.\gradlew.bat test` và `.\gradlew.bat bootRun`).

Ở terminal khác, thực hiện:

~~~bash
curl -i http://localhost:8080/state
curl -i http://localhost:8080/reports
curl -i -u "bob:demoPass!" http://localhost:8080/reports
curl -i -u "alice:demoPass!" http://localhost:8080/reports
curl -i -u "alice:wrong-password" http://localhost:8080/self
curl -i -u "alice:demoPass!" http://localhost:8080/state
~~~

Kỳ vọng về **logic và HTTP status** (không cố định mọi header hoặc thứ tự trường JSON):

| Lệnh/tình huống | Kỳ vọng |
| --- | --- |
| `/state` không credential | HTTP 200, `kind` là `AnonymousAuthenticationToken`; `rawFlag=true`, `recognizedAsAuthenticated=false`, `fullyAuthenticated=false` |
| `/reports` không credential | HTTP 401 với cấu hình Basic |
| `/reports`, Bob đúng mật khẩu | HTTP 403 vì Bob không có `reports:read` |
| `/reports`, Alice đúng mật khẩu | HTTP 200, body `REPORT_OK` |
| `/self`, Alice sai mật khẩu | HTTP 401 |
| `/state`, Alice đúng mật khẩu | HTTP 200, token được xác thực; ba boolean thông thường đều `true` |

Không cần tự can thiệp `isAuthenticated` trong bất cứ endpoint nào để đạt các kết quả trên: filter/provider làm công việc xác thực, còn authorization rules áp dụng quyền. Đó là ranh giới có chủ đích.

## 8. Đối chiếu với JWT Resource Server và đăng nhập có phiên

Ứng dụng ví dụ dùng HTTP Basic, nhưng bài học áp dụng tương tự cho token bearer và đăng nhập web.

### 8.1. JWT chưa được xác minh không phải Authentication đáng tin

Một JWT thường có header, payload và signature được mã hóa cho việc truyền tải. Tự tách token theo dấu chấm rồi giải mã payload **chỉ đọc claim**: attacker có thể đưa vào `sub`, `roles` hoặc `scope` do họ tự tạo.

Với OAuth2 Resource Server của Spring Security, cấu hình JWT decoder dựa trên issuer/JWK tin cậy và chính sách validator phù hợp. Trước khi nhận token là hợp lệ, cần kiểm chữ ký (với asymmetric/symmetric key phù hợp), issuer, thời gian và audience dành cho API. Ví dụ **cấu hình minh họa, cần IdP thật**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          audiences: https://api.example.test
~~~

Khi dùng JWT Resource Server, thêm dependency `spring-boot-starter-oauth2-resource-server` và cấu hình `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` phù hợp. `JwtAuthenticationProvider` làm việc với decoder rồi tạo `Authentication` dựa trên **token đã xác minh**. Việc mặc định map `scope` thành authority dạng `SCOPE_...` là một bước chuyển đổi sau validation; không gán quyền trực tiếp từ raw request.

Không kết hợp cấu hình JWT minh họa này một cách máy móc với demo HTTP Basic thành một hệ thống hoàn chỉnh. Khi API hỗ trợ nhiều cơ chế, từng filter chain/endpoint cần ranh giới và policy rõ ràng.

### 8.2. Web session giữ kết quả sau xác thực

Trong ứng dụng đăng nhập qua form hoặc OIDC, user có thể đã chứng minh credential ở **lần đăng nhập trước**. `SecurityContextRepository` / session lưu kết quả phù hợp để phục hồi `Authentication` ở request sau; không phải mỗi lần request đều nhập lại password. `isAuthenticated=true` lúc này là một **trạng thái được bảo toàn bởi cơ chế session đáng tin**.

Tuy nhiên, độ tin cậy của session phụ thuộc cookie bảo mật, session fixation protection, giới hạn thời gian, logout, thay đổi quyền và cơ chế vô hiệu phiên phù hợp. Nếu token/phiên hết hiệu lực theo chính sách, hệ thống phải từ chối hoặc yêu cầu xác thực lại; không thể dựa vào cờ true mãi mãi.

### 8.3. Remember-me, MFA và step-up

Remember-me có thể cho phép tái đăng nhập tự động bằng cookie theo cơ chế được cấu hình. Framework phân biệt remember-me khỏi fully authenticated; nhưng `fullyAuthenticated()` **không có nghĩa** một thao tác “nhập mật khẩu trong 5 phút vừa qua”, cũng không chứng minh mức bảo đảm MFA.

Nếu chuyển tiền, đổi phương thức khôi phục tài khoản hay đổi quyền quản trị đòi step-up, cần thiết kế kiểm soát riêng: xác minh claim về phương pháp/thời điểm xác thực từ issuer tin cậy, buộc luồng đăng nhập lại khi cần, hoặc xác nhận challenge có kiểm chứng. Không tự quy đổi `isAuthenticated=true` thành `mfa=true`.

## 9. Xử lý sai lệch và bảo vệ ranh giới tin cậy

### 9.1. Dữ liệu client và context không phải cùng một thứ

Tầng HTTP nhận dữ liệu không tin cậy: username, password, bearer token, cookie, header, JSON body, query parameter. Tầng xác thực có nhiệm vụ **chứng minh hoặc từ chối** các dữ liệu đó. Tầng ứng dụng được phép dùng kết quả `Authentication` chỉ khi kết quả được dựng qua đường được thiết kế đáng tin.

Không đưa các giá trị `authenticated`, `isAdmin` hoặc `authorities` do client gửi thẳng vào `Authentication`. Với custom `AuthenticationProvider`, token kết quả nên rõ trạng thái trước/sau, hạn chế mutable fields, và không cho caller đánh dấu trusted sau khi tạo bằng chứng chưa kiểm.

### 9.2. Tài khoản khóa, thay đổi quyền và dữ liệu cũ

Một token có raw flag true không hàm ý kiểm lại trạng thái account ở mọi request. Với session còn tồn tại hoặc JWT tự chứa đã phát hành, việc khóa tài khoản/đổi role có thể cần session invalidation, thời hạn token ngắn, revocation, introspection, cơ chế push sự kiện hoặc kiểm policy tại resource server. Lựa chọn phụ thuộc yêu cầu bảo mật và độ trễ chấp nhận được.

### 9.3. Kiểm quyền bản ghi và tenant

Ví dụ Alice có authority `reports:read` nhưng chỉ được xem báo cáo thuộc tổ chức A. Quy tắc `hasAuthority("reports:read")` chỉ xác nhận một tín hiệu quyền; service còn phải kiểm chính xác **subject thuộc tenant A và được phép đọc báo cáo ID cụ thể**. `isAuthenticated()` không có dữ liệu chứng minh điều này.

### 9.4. Bất đồng bộ và thread khác

`SecurityContextHolder` ở chế độ mặc định sử dụng chiến lược theo thread. Không giả định một object authentication còn nguyên hoặc đã được truyền an toàn sang executor, scheduler hay asynchronous callback. Dùng công cụ lan truyền `SecurityContext` được Spring Security hỗ trợ khi thực sự cần, quản lý vòng đời ngữ cảnh và tránh mang nhầm danh tính người dùng sang job nền. Job nền thường cần service identity riêng.

## 10. Anti-pattern và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `if (auth != null && auth.isAuthenticated())` dùng như **toàn bộ** policy | Anonymous token có thể có raw flag true; thiếu kiểm scope và tenant | Dùng authorization manager của Spring Security và policy tài nguyên |
| Controller đọc `isAuthenticated` từ request body | Attacker tự khai true | Để filter/provider tạo kết quả từ credential đã kiểm |
| Tự gọi `UsernamePasswordAuthenticationToken.authenticated(...)` từ username client | Hợp thức hóa danh tính/authority không qua chứng minh | Tạo unauthenticated request rồi gọi `AuthenticationManager` |
| Tự decode JWT và gắn `JwtAuthenticationToken` | Tin token giả, token sai issuer/audience/hết hạn | Dùng Resource Server `JwtDecoder` và validators |
| Xem `fullyAuthenticated()` là MFA hoặc xác thực vừa xảy ra | Cho phép thao tác rủi ro dù chưa đủ assurance | Chính sách step-up có kiểm chứng riêng |
| Xem remember-me và anonymous giống phiên login thường | Đánh giá sai mức tin cậy | Dùng `AuthenticationTrustResolver` và rule phù hợp |
| `hasRole("ADMIN")` trên authority do client tự gửi | Phân quyền giả | Cấp authority theo mapping backend/issuer đã xác minh |
| Tất cả endpoint chỉ có `authenticated()` | Người dùng bất kỳ có thể đi sâu vào dữ liệu không thuộc quyền | Kết hợp authority và kiểm ownership/tenant |
| Test `@WithMockUser` rồi kết luận password/JWT validation an toàn | Bỏ sót lỗi auth filter/provider/decoder | Bổ sung test tích hợp cho đường credential thật |
| Ghi raw token, password vào log để debug flag | Rò rỉ credential | Chỉ log trạng thái quyết định, type token và mã lý do an toàn |

## 11. Các bài tập tự kiểm tra

**Bài tập 1.** Một endpoint công khai in ra `auth.isAuthenticated() == true` dù người dùng chưa đăng nhập. Có chắc bị vượt xác thực không?

**Đáp án:** Chưa đủ kết luận. Nếu object là `AnonymousAuthenticationToken`, raw flag có thể true theo cách Spring Security biểu diễn anonymous. Kiểm `AuthenticationTrustResolver.isAnonymous(auth)`, `isAuthenticated(auth)` và quy tắc bảo vệ endpoint. Nếu endpoint cần bảo vệ mà lại cho phép anonymous, đó là lỗi policy cần sửa.

**Bài tập 2.** Endpoint chỉ gọi `if (authentication.isAuthenticated())` rồi cho phép xóa một báo cáo. Vấn đề nằm ở đâu?

**Đáp án:** Check này vừa có thể sai với anonymous, vừa không kiểm authority, subject, tenant hoặc ownership của báo cáo. Cần chính sách xác thực phù hợp và kiểm quyền xóa đúng tài nguyên, không chấp nhận boolean như đủ bằng chứng.

**Bài tập 3.** Một developer tạo `UsernamePasswordAuthenticationToken.authenticated("admin", null, ROLE_ADMIN)` sau khi nhận JSON `{"name":"admin"}`. Vì sao nguy hiểm?

**Đáp án:** Developer tự cấp kết quả trusted và authority từ dữ liệu client mà không qua `AuthenticationManager`/`AuthenticationProvider` và bước xác minh credential. Việc constructor/factory tạo được object không chứng minh người gửi là admin.

**Bài tập 4.** JWT từ nguồn ngoài có claim `{"sub":"alice","scope":"admin"}` và mã đã decode thành công. Có thể thiết lập `isAuthenticated=true` và cho phép quản trị không?

**Đáp án:** Không. Phải xác minh chữ ký, issuer, audience, thời hạn và các chính sách bắt buộc, rồi ánh xạ claim sang quyền theo quy tắc của resource server. Decode chỉ đọc dữ liệu.

**Bài tập 5.** Bob nhập đúng mật khẩu nên `isAuthenticated=true`; tại sao `/reports` trả 403?

**Đáp án:** Xác thực thành công không tự cấp authority `reports:read`. Bob chỉ có `profile:read` trong demo, nên bị chặn ở bước authorization dù credential đúng.

**Bài tập 6.** Một phiên remember-me có `isAuthenticated=true` nhưng không được vào một endpoint `fullyAuthenticated()`. Điều này có hợp lý?

**Đáp án:** Có. Spring Security nhận diện remember-me khác với fully authenticated theo trust resolver. Nếu ứng dụng đòi MFA hoặc reauthentication mới, cần định nghĩa chính sách bảo đảm cao hơn phân loại này.

## 12. Tổng kết và checklist

Đọc `isAuthenticated` theo đúng thứ tự nhân quả:

1. **Bằng chứng:** request đưa credential/token/phiên nào?
2. **Xác minh:** filter, provider, decoder hoặc session mechanism nào đã xác minh bằng chứng đó?
3. **Kết quả nội bộ:** `Authentication` đáng tin nào được tạo ra và được lưu vào `SecurityContext`?
4. **Phân loại:** token là anonymous, remember-me hay được nhận diện authenticated/fully authenticated?
5. **Phân quyền:** chủ thể thực sự có authority, policy và quyền trên đúng tài nguyên/tenant hay không?

**Câu cần nhớ:** `Authentication.isAuthenticated()` là **cờ trạng thái trong đối tượng bảo mật**. Bằng chứng thực phải được kiểm **trước khi** hệ thống cấp trạng thái đáng tin, và quyền truy cập phải được quyết định **sau đó** cho đúng hành động và tài nguyên. Không “xác minh” bằng cách đọc lại một boolean mà chính client hoặc code không đáng tin có thể tạo ra.

### Tài liệu gốc nên tra cứu

- Spring Security 6.5 — `Authentication` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — Anonymous Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html
- Spring Security — HTTP Request Authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Authorization Architecture and `AuthenticatedAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security — Remember-Me: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
