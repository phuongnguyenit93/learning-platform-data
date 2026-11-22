# @AuthenticationPrincipal và ánh xạ principal vào tham số Controller (Spring Security Servlet)

> **Phạm vi:** Spring Security 6.x + Spring MVC trên Servlet stack, ví dụ Spring Boot 3.x/Java 17+. Bài này giải thích `@AuthenticationPrincipal` lấy **principal đã được Spring Security xác thực** rồi cung cấp trực tiếp vào tham số phương thức Controller; cách ánh xạ principal thành đối tượng miền, thuộc tính hoặc DTO; các điểm khác nhau giữa form/HTTP Basic, JWT Resource Server và OAuth2/OIDC; cùng các lỗi bảo mật và kiểm thử quan trọng. Ví dụ hoàn chỉnh sử dụng HTTP Basic **chỉ để mô phỏng** một Authentication có custom principal, không coi Basic là lựa chọn mặc định cho mọi hệ thống.

## 1. Vấn đề mà @AuthenticationPrincipal giải quyết

Sau khi đăng nhập hoặc xác minh Bearer token, Spring Security thường lưu thông tin người gọi trong `SecurityContext`, bao gồm đối tượng `Authentication`. Trong một controller, ta có thể cần biết **ai đang gọi** để:

- trả hồ sơ của chính người dùng;
- tìm các đơn hàng thuộc `currentUser.id`, không dựa vào ID tự khai từ request;
- ghi audit event hoặc điều kiện authorization theo tài khoản;
- hiển thị tên của người đang đăng nhập mà không phải tự truy vấn credential;
- ánh xạ claim từ `Jwt` hoặc `OidcUser` vào một tham số phù hợp.

Một cách dài dòng là tự đọc security context:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

Object principal = authentication.getPrincipal();
~~~

Đây là **đoạn minh họa trong Java có Spring Security**, không phải chương trình chạy độc lập. Nó đòi hỏi xử lý `authentication == null`, xác định kiểu của principal và tránh ép kiểu sai. Trong một MVC controller, Spring Security có thể làm phần **argument resolution** thay cho ta:

~~~java
@GetMapping("/api/me")
public MeResponse me(@AuthenticationPrincipal AppPrincipal currentUser) {
    return new MeResponse(currentUser.getId(), currentUser.getUsername());
}
~~~

Khi request vào handler, Spring MVC phối hợp với `AuthenticationPrincipalArgumentResolver` để lấy principal từ security context và đưa vào đúng tham số được gắn annotation. Từ đó code controller có ý nghĩa rõ ràng hơn: **“tham số này là principal hiện tại do Spring Security cung cấp”**.

**Nguyên tắc cốt lõi:** `@AuthenticationPrincipal` **không thực hiện đăng nhập, không tự xác minh JWT/chữ ký/password, không cấp quyền**. Nó chỉ đọc **kết quả authentication đã có**. Authentication/authorization phải được cấu hình trước bằng security filter chain, provider, decoder, entry point và policy phù hợp.

## 2. Phân biệt SecurityContext, Authentication và principal

Mô hình khái niệm:

~~~text
HTTP request
    |
    v
SecurityFilterChain
    |
    +--> form login / Basic / OAuth2 login / JWT Resource Server ...
    |
    v
Authentication được tạo sau khi xác thực thành công
    |
    +--> isAuthenticated()
    +--> getName()
    +--> getAuthorities()
    +--> getCredentials()
    +--> getDetails()
    +--> getPrincipal()    <--- principal có kiểu tùy cơ chế
    |
    v
SecurityContextHolder / SecurityContext của request
    |
    v
DispatcherServlet -> Controller method
    |
    +--> @AuthenticationPrincipal AppPrincipal current
    +--> @AuthenticationPrincipal Jwt jwt
    +--> @AuthenticationPrincipal OidcUser oidcUser
~~~

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| `SecurityContext` | Giữ `Authentication` đang áp dụng trong security context của request. | Lấy qua `SecurityContextHolder.getContext()` |
| `Authentication` | Đại diện kết quả xác thực, kèm name, principal và authorities. | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` |
| `Authentication.getPrincipal()` | Đối tượng người gọi mà loại authentication đó cung cấp. | `UserDetails`, `Jwt`, `OAuth2User`, custom `AppPrincipal` |
| `Authentication.getName()` | Tên chuỗi của authentication theo triển khai. | username, subject JWT hoặc tên OIDC |
| `Authentication.getAuthorities()` | Quyền được framework gắn vào authentication. | `ROLE_READER`, `SCOPE_orders.read` |
| `@AuthenticationPrincipal` | Chọn **principal**, không phải toàn bộ authentication. | Tham số của MVC handler |
| `@CurrentSecurityContext` | Tiêm một phần security context theo expression, nếu cần. | `@CurrentSecurityContext(expression = "authentication")` |

Một `Authentication` có nhiều thông tin hơn principal. Vì vậy tham số `@AuthenticationPrincipal Authentication auth` **không phải cách phổ biến để lấy authentication**: annotation tìm `getPrincipal()`, mà principal thường không có kiểu `Authentication`. Nếu cần quyền, trạng thái xác thực hoặc details, dùng trực tiếp `Authentication`/`Principal` hoặc `@CurrentSecurityContext` phù hợp.

### Principal không nhất thiết là user entity

Trong HTTP Basic hoặc form login cấu hình bằng `UserDetailsService`, principal thường là một đối tượng implement `UserDetails` (hoặc custom principal). Trong JWT Resource Server, principal thường là `Jwt`. Trong `oauth2Login()`, principal thường là `OAuth2User`/`OidcUser`.

**Không mặc định ép về `org.springframework.security.core.userdetails.User` hay JPA `UserEntity`.** Phụ thuộc vào cơ chế xác thực và kiểu principal mà chính dự án cấu hình.

## 3. Cơ chế Spring MVC argument resolver

`@AuthenticationPrincipal` nằm ở package:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
~~~

Spring Security MVC integration cung cấp `AuthenticationPrincipalArgumentResolver`. Ở mức khái niệm, khi Controller có tham số chứa annotation:

1. `DispatcherServlet` đã chọn handler method.
2. Spring MVC gọi các `HandlerMethodArgumentResolver` để tạo giá trị từng tham số.
3. Resolver tương ứng với `@AuthenticationPrincipal` tìm `Authentication` hiện hành từ `SecurityContextHolder`.
4. Nếu có authentication, resolver lấy `authentication.getPrincipal()`.
5. Nếu annotation khai báo `expression`, resolver đánh giá SpEL dựa trên principal đó.
6. Giá trị sau ánh xạ được so với kiểu Java của tham số; nếu phù hợp thì truyền vào method, nếu không thì xử lý theo `errorOnInvalidType`.

**Không có bước xác thực credential lần thứ hai** ở đây. Ví dụ một token Bearer sai chữ ký cần bị từ chối bởi `JwtDecoder` trong Spring Security filters trước khi controller có cơ hội chạy.

### Annotation khác @RequestParam và @RequestBody

~~~java
public ResponseEntity<?> example(
    @RequestParam String username,
    @AuthenticationPrincipal AppPrincipal currentUser) {
    // username: dữ liệu client gửi lên (không phải danh tính đã xác minh).
    // currentUser: lấy từ security context (nếu được xác thực đúng).
    return ResponseEntity.ok().build();
}
~~~

Đây là fragment minh họa; các import `ResponseEntity`, `RequestParam` và annotations khác phải có khi đưa vào class thật. Không bao giờ coi `username` từ query/form/JSON body là bằng chứng người gọi là ai. Dùng `currentUser` hoặc kết quả authorization đã xác minh để thực hiện truy vấn thuộc về “tôi”.

## 4. Ba cách lấy thông tin danh tính trong Controller

### 4.1. Lấy principal bằng @AuthenticationPrincipal

~~~java
@GetMapping("/me")
public String me(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

Đoạn này hợp lệ **khi principal thực sự implement `UserDetails`** và request buộc phải authenticated. Nếu authentication mang principal kiểu `Jwt` hoặc `OidcUser` không tương thích `UserDetails`, tham số có thể là `null` (theo cấu hình mặc định của annotation) hoặc ném lỗi ép kiểu khi bật `errorOnInvalidType=true`.

### 4.2. Lấy java.security.Principal hoặc Authentication

~~~java
@GetMapping("/me/name")
public String name(java.security.Principal principal) {
    return principal.getName();
}
~~~

Đây là cách đơn giản nếu chỉ cần tên và không quan tâm concrete principal class. Một method có thể nhận `Authentication authentication` để lấy authorities hoặc thông tin khác theo cơ chế Spring Security/MVC. Cần nhớ `Authentication.getName()` tùy triển khai; JWT thường liên quan `sub`, UserDetails thường liên quan username.

### 4.3. Lấy toàn bộ SecurityContext hoặc authentication

~~~java
@GetMapping("/me/authorities")
public List<String> authorities(Authentication authentication) {
    return authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .sorted()
        .toList();
}
~~~

Đây là fragment controller cần import `Authentication` và `GrantedAuthority`. Chọn kiểu này khi thật sự cần metadata xác thực. Không truyền toàn bộ `Authentication` hoặc `UserDetails` trực tiếp ra JSON response, vì đối tượng có thể chứa credentials, claims, session details hoặc thông tin không thuộc API contract.

**Quy tắc lựa chọn:** cần object “ai đang gọi” → `@AuthenticationPrincipal`; chỉ cần tên → `Principal`; cần authorities/authentication metadata → `Authentication` hoặc `@CurrentSecurityContext`.

## 5. Hai thuộc tính quan trọng của @AuthenticationPrincipal

Annotation cho phép chọn một giá trị từ principal và quyết định cách xử lý sai kiểu.

### 5.1. expression: ánh xạ thuộc tính bằng SpEL

Ví dụ custom principal có getter `getId()`:

~~~java
@GetMapping("/me/id")
public Map<String, String> currentId(
        @AuthenticationPrincipal(expression = "id") UUID id) {
    return Map.of("id", id.toString());
}
~~~

Resolver đánh giá biểu thức `id` với **root object là principal**, tương đương đọc getter `getId()`. Kết quả có thể là `UUID` thay vì toàn bộ `AppPrincipal`. Đây là ví dụ trích xuất **một thuộc tính từ principal đã xác thực**, không phải đọc request parameter `id`.

Một số biểu thức phụ thuộc vào kiểu principal:

~~~java
// Chỉ áp dụng khi principal là Jwt, có claim tenant_id:
@AuthenticationPrincipal(expression = "claims['tenant_id']")
String tenantId

// Chỉ áp dụng khi principal là OAuth2User có attributes.email:
@AuthenticationPrincipal(expression = "attributes['email']")
String email
~~~

Hai dòng trên là **fragment tham số**, không phải phương thức Java đầy đủ. `Jwt.getClaims()` cho phép truy cập property `claims`; `OAuth2User.getAttributes()` tương ứng `attributes`. Khi claim vắng hoặc không có kiểu `String`, phải có chính sách xử lý đúng, không suy ra danh tính hợp lệ từ một trường tùy chọn.

**Lưu ý về SpEL:** biểu thức là do developer viết cố định trong source, không nên lấy nguyên biểu thức từ request do client gửi. Biểu thức nên đơn giản và không có side effects; hạn chế gọi phương thức làm thay đổi trạng thái hoặc truy vấn dữ liệu ngoài ý muốn.

### 5.2. errorOnInvalidType: chọn null hay lỗi ép kiểu

Khi không dùng `expression` hoặc sau khi expression đã tạo kết quả, type mismatch có thể xảy ra. Theo hợp đồng của annotation:

- `errorOnInvalidType = false` (mặc định): nếu principal/kết quả không thể gán cho kiểu tham số, resolver có thể trả `null`.
- `errorOnInvalidType = true`: nếu giá trị có kiểu không tương thích, resolver ném `ClassCastException` để phát hiện sai cấu hình sớm.
- Nếu **không có Authentication hoặc không có principal**: thường nhận `null`. Đặt `errorOnInvalidType=true` không tự biến một endpoint public thành endpoint authenticated.
- Nếu **SpEL expression tự lỗi** vì getter/claim/kiểu dữ liệu sai, đây là lỗi biểu thức, không phải thứ `errorOnInvalidType=false` có thể bảo đảm nuốt mọi trường hợp.

Ví dụ fail-fast cho vùng được bảo vệ:

~~~java
@GetMapping("/api/me")
public MeResponse me(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        AppPrincipal principal) {
    // Sai loại principal (ví dụ JWT trong chain mong AppPrincipal)
    // sẽ lộ ra ở argument resolution thay vì âm thầm trả null.
    return mapToResponse(principal);
}
~~~

Đây là fragment minh họa, `mapToResponse` cần do ứng dụng định nghĩa. **Không để xảy ra ClassCastException trong production như một luồng 401/403 chuẩn**; nên có thiết kế security chain/principal types nhất quán và test từng loại đăng nhập. Thuộc tính này không thay thế authorization.

## 6. Ví dụ hoàn chỉnh Java 17+ / Spring Boot 3: custom principal trong MVC

Ví dụ gồm một account `alice`, dùng HTTP Basic để chứng minh password được kiểm tra trước khi controller nhận principal. Chúng ta sẽ cho Spring Security tạo authentication có principal **`AppPrincipal` chứa UUID nội bộ**, sau đó dùng `@AuthenticationPrincipal` để trả DTO an toàn.

**Chỉ chạy trong môi trường học tập.** Password ví dụ là giá trị cố định, HTTPS và quản lý secret/IdP phải được thiết kế riêng cho production. Project sử dụng Maven và Spring Boot 3.3.5 như một **phiên bản tham chiếu cụ thể đã phát hành**, không phải khẳng định đây là phiên bản mới nhất.

### 6.1. Cấu trúc dự án

~~~text
principal-demo/
  pom.xml
  src/
    main/
      java/com/example/principaldemo/
        PrincipalDemoApplication.java
        AppPrincipal.java
        CurrentUser.java
        SecurityConfiguration.java
        ProfileController.java
    test/
      java/com/example/principaldemo/
        ProfileControllerTest.java
~~~

### 6.2. pom.xml

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>principal-demo</artifactId>
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
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Sử dụng JDK 17+ và Maven có thể tải dependency từ repository bình thường. `spring-boot-starter-security` cung cấp Spring Security web và cấu hình; MVC integration nhận `@AuthenticationPrincipal` khi security và Spring MVC được nối chuẩn. Không cần tự gọi `SecurityContextHolder` trong controller ở ví dụ này.

### 6.3. Main application

**`src/main/java/com/example/principaldemo/PrincipalDemoApplication.java`:**

~~~java
package com.example.principaldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PrincipalDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrincipalDemoApplication.class, args);
    }
}
~~~

### 6.4. Custom principal với internal ID

**`src/main/java/com/example/principaldemo/AppPrincipal.java`:**

~~~java
package com.example.principaldemo;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public final class AppPrincipal implements UserDetails {

    private static final long serialVersionUID = 1L;

    private final UUID id;
    private final String username;
    private final String passwordHash;
    private final Collection<? extends GrantedAuthority> authorities;

    public AppPrincipal(
            UUID id,
            String username,
            String passwordHash,
            Collection<? extends GrantedAuthority> authorities) {
        this.id = Objects.requireNonNull(id);
        this.username = Objects.requireNonNull(username);
        this.passwordHash = Objects.requireNonNull(passwordHash);
        this.authorities = List.copyOf(authorities);
    }

    // SpEL expression = "id" sẽ truy cập getter này.
    public UUID getId() {
        return id;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

**Tại sao dùng DTO ở controller thay vì trả thẳng AppPrincipal?** Một `UserDetails` chứa `getPassword()` phục vụ authentication. Nếu đưa nguyên principal cho JSON serializer, có rủi ro tiết lộ password hash và những thuộc tính chỉ dành cho server. DTO response chỉ chứa **ID, username và authorities được phép công khai** trong API demo. Ứng dụng thật phải tối thiểu hóa thông tin quyền và ID được trả cho client theo yêu cầu.

`getId()` trả UUID nội bộ và khác `getUsername()`; cách này tránh lấy email/username biến đổi làm khóa chính của record nghiệp vụ. Trong hệ thống đa tenant, internal ID phải đi kèm tenant/authorization đúng chính sách.

### 6.5. SecurityConfiguration: xác thực Basic rồi tạo Authentication

**`src/main/java/com/example/principaldemo/SecurityConfiguration.java`:**

~~~java
package com.example.principaldemo;

import java.util.List;
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        // DelegatingPasswordEncoder mặc định dùng thuật toán an toàn
        // theo cấu hình hiện hành, ví dụ bcrypt cho password mới.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        AppPrincipal alice = new AppPrincipal(
            UUID.fromString("11111111-1111-4111-8111-111111111111"),
            "alice",
            encoder.encode("demo-pass-123"),
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

        return username -> {
            if (!alice.getUsername().equals(username)) {
                throw new UsernameNotFoundException("Unknown account");
            }
            return alice;
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Giữ CSRF mặc định; ví dụ chỉ có GET endpoints.
            .build();
    }
}
~~~

**Giải thích:**

1. `UserDetailsService` trả **AppPrincipal**. Khi HTTP Basic xác minh mật khẩu đúng thông qua authentication provider, principal trong kết quả thường chính là custom `UserDetails` này.
2. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo password hash được gắn prefix scheme, không lưu plain password trong `UserDetails`. Password demo trong source chỉ phù hợp học tập; production dùng kho danh tính và secret management.
3. `anyRequest().authenticated()` yêu cầu authentication ở tất cả đường dẫn trừ `/api/public`. **Đây là phần bảo vệ endpoint**; `@AuthenticationPrincipal` không quyết định request được phép tới controller hay không.
4. `formLogin` tắt trong ví dụ chỉ để tập trung vào Basic; không hàm ý tắt login form ở ứng dụng khác.
5. `SessionCreationPolicy.STATELESS` giảm phụ thuộc vào session Spring Security. Nó không tự đảm bảo endpoint an toàn trước CSRF khi browser tự gửi credentials. Đối với cookie/form login hoặc Basic được browser tự gửi, cần đánh giá CSRF trước khi bỏ bảo vệ. Ví dụ dùng các GET endpoints, không gọi `csrf.disable()`.
6. Không cần tự tạo `Authentication` trong controller hay gắn `SecurityContextHolder` thủ công. Đây là trách nhiệm của Spring Security filters/authentication provider.
7. Ví dụ có một `UserDetailsService` duy nhất và một `PasswordEncoder` bean; cấu hình mặc định phù hợp cho authentication qua username/password. Khi có nhiều provider/chain, cần kiểm tra `AuthenticationManager` được nối đúng.

### 6.6. Tạo meta-annotation để thống nhất cách dùng

Ở codebase lớn, team có thể dùng `@CurrentUser` thay cho việc lặp annotation dài trong mọi controller. Spring Security hỗ trợ `@AuthenticationPrincipal` làm meta-annotation.

**`src/main/java/com/example/principaldemo/CurrentUser.java`:**

~~~java
package com.example.principaldemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.core.annotation.AuthenticationPrincipal;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@AuthenticationPrincipal(errorOnInvalidType = true)
public @interface CurrentUser {
}
~~~

`@CurrentUser` không tự xác thực user, không tạo security filter mới. Nó chỉ cố định cách **tiêm principal** cho controller và giúp API code nói rõ ý nghĩa tham số. Annotation này **giả định** tất cả endpoint dùng nó đều có principal kiểu `AppPrincipal`. Đừng dùng cùng annotation cho một chain chỉ có JWT principal nếu chưa thay hợp đồng.

### 6.7. Controller với ba kiểu ánh xạ

**`src/main/java/com/example/principaldemo/ProfileController.java`:**

~~~java
package com.example.principaldemo;

import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo(
            @AuthenticationPrincipal AppPrincipal user) {
        // Endpoint permitAll: với anonymous principal không đúng kiểu
        // AppPrincipal, resolver mặc định có thể đưa vào null.
        return Map.of("viewer", user == null ? "guest" : user.getUsername());
    }

    @GetMapping("/api/me")
    public MeResponse me(
            @AuthenticationPrincipal(errorOnInvalidType = true)
            AppPrincipal currentUser) {

        List<String> authorities = currentUser.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new MeResponse(
            currentUser.getId(),
            currentUser.getUsername(),
            authorities
        );
    }

    @GetMapping("/api/me/id")
    public Map<String, String> id(
            @AuthenticationPrincipal(
                expression = "id",
                errorOnInvalidType = true)
            UUID currentUserId) {

        return Map.of("id", currentUserId.toString());
    }

    @GetMapping("/api/me/alias")
    public Map<String, String> alias(@CurrentUser AppPrincipal user) {
        return Map.of("username", user.getUsername());
    }

    @GetMapping("/api/me/name")
    public Map<String, String> principalName(Principal principal) {
        return Map.of("username", principal.getName());
    }

    public record MeResponse(
        UUID id,
        String username,
        List<String> authorities) {
    }
}
~~~

Giải thích ba kỹ thuật chính:

- **Toàn object:** `@AuthenticationPrincipal AppPrincipal currentUser` nhận custom principal của Spring Security.
- **Một thuộc tính:** `@AuthenticationPrincipal(expression="id") UUID currentUserId` yêu cầu resolver đọc `getId()` của principal và đưa vào tham số.
- **Meta-annotation:** `@CurrentUser AppPrincipal user` dùng cùng resolver nhưng theo quy ước codebase.
- **Không dùng annotation:** `Principal principal` cung cấp tên theo Servlet/Spring Security integration khi chỉ cần một chuỗi định danh.
- **Anonymous:** `/api/public` cho phép không đăng nhập, nên phải xử lý principal `null`/không đúng loại thay vì gọi getter vô điều kiện.

Response đại diện cho `GET /api/me` với credential demo hợp lệ:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
~~~

JSON trên là **giá trị đại diện của controller demo**, không cam kết kiểu whitespace, thứ tự thuộc tính hay header sẽ giống hoàn toàn trên mọi môi trường.

### 6.8. Chạy dự án và quan sát HTTP

Yêu cầu JDK 17+, Maven và network để tải dependency lần đầu. Tại thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Gọi endpoint public:

~~~bash
curl -i http://localhost:8080/api/public
~~~

Body ví dụ:

~~~json
{"viewer":"guest"}
~~~

Gọi endpoint protected **không gửi credential**:

~~~bash
curl -i http://localhost:8080/api/me
~~~

**Kỳ vọng:** HTTP `401 Unauthorized`, thường có `WWW-Authenticate: Basic …`. Body/error page phụ thuộc server và error handling config.

Gửi credential demo:

~~~bash
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me/id
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me/alias
curl -i -u alice:demo-pass-123 http://localhost:8080/api/me/name
~~~

Kỳ vọng lần lượt: profile JSON chứa UUID/username/authority; endpoint `id` trả UUID; `alias` và `name` trả `alice`. Trên PowerShell, dùng `curl.exe` nếu `curl` là alias của cmdlet khác; tránh đưa password thật vào shell history và process list. **HTTP Basic phải đi qua HTTPS khi dùng thông tin đăng nhập thật.**

Không cố biến demo này thành hệ thống quản lý tài khoản production bằng cách thêm password mới vào source; cần user store, hashing, policy, rate limit và audit theo chuẩn của ứng dụng.

## 7. Kiểm thử Spring MVC: giá trị thật đến từ Authentication

Các test này có Spring Security filter chain và gửi Basic credential để thực sự đi qua authentication provider. Không dùng mock principal kiểu khác rồi kết luận `AppPrincipal` đã được tạo đúng.

**`src/test/java/com/example/principaldemo/ProfileControllerTest.java`:**

~~~java
package com.example.principaldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousCanAccessPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.viewer").value("guest"));
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordDoesNotCreateCurrentUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bindsCustomPrincipalAndSafeProfile() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.id").value(
                "11111111-1111-4111-8111-111111111111"))
            .andExpect(jsonPath("$.authorities[0]").value(
                "ROLE_READER"));
    }

    @Test
    void extractsPrincipalPropertyWithSpel() throws Exception {
        mvc.perform(get("/api/me/id")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(
                "11111111-1111-4111-8111-111111111111"));
    }

    @Test
    void metaAnnotationResolvesSameCurrentUser() throws Exception {
        mvc.perform(get("/api/me/alias")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void servletPrincipalNameIsAvailable() throws Exception {
        mvc.perform(get("/api/me/name")
                .with(httpBasic("alice", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }
}
~~~

Nhóm test trên xác nhận:

1. `permitAll` vẫn cho phép truy cập public và controller xử lý anonymous.
2. Endpoint protected không có authentication bị 401; sai password cũng bị 401.
3. Authentication provider lấy đúng `AppPrincipal` từ `UserDetailsService`.
4. `@AuthenticationPrincipal` ánh xạ object đúng kiểu, SpEL `id` và meta-annotation đều được nhận.
5. `Principal.getName()` hoạt động khi Spring Security/Servlet integration được nối đúng.

**Giới hạn:** đây là các test ví dụ trong project Spring Boot. Không có output Maven cố định vì môi trường có thể in log khác nhau. Các test này **không chứng minh** một JWT được kiểm tra chữ ký, một OAuth2/OIDC flow được cấu hình đúng hay một backend chống giả mạo header khi chạy sau proxy; cần test riêng cho từng cơ chế.

### Tại sao không chỉ dùng @WithMockUser?

`@WithMockUser(username="alice")` hoặc MockMvc `.with(user("alice"))` có ích khi test policy authorization, nhưng nó thường tạo principal kiểu Spring Security `User`/mock user, **không phải AppPrincipal** tùy chỉnh của demo. Nếu controller ép sang `AppPrincipal`, test dễ nhận `null` hoặc `ClassCastException`. Để test mapping custom principal, dùng HTTP Basic thực tế như trên, hoặc tự tạo `Authentication` có principal **đúng class**.

Điều này cũng giải thích tại sao một test controller chỉ `@WebMvcTest` với resolver chưa được nối đầy đủ có thể không phản ánh production security chain. Xác nhận Spring Security filters có được áp vào MockMvc và principal type đúng như app thực.

## 8. Khi principal là JWT, OAuth2User hoặc OidcUser

Không có một kiểu principal Java chung cho mọi authentication mechanism. Trong các cấu hình khác nhau, cùng một annotation có thể cần một tham số khác.

### 8.1. OAuth2 Resource Server với JWT

Nếu app cấu hình `oauth2ResourceServer(oauth2 -> oauth2.jwt(…))`, `JwtAuthenticationToken` thường có principal là `org.springframework.security.oauth2.jwt.Jwt`.

~~~java
@GetMapping("/api/jwt/me")
public Map<String, String> jwtMe(@AuthenticationPrincipal Jwt jwt) {
    return Map.of("subject", jwt.getSubject());
}
~~~

Đây là **fragment dành cho ứng dụng Resource Server đã cấu hình JWT decoder**, không đưa trực tiếp vào project HTTP Basic ở mục 6. `JwtDecoder` phải kiểm signature, issuer, time và audience theo policy để token được coi là authenticated. `@AuthenticationPrincipal Jwt` chỉ nhận đối tượng JWT **sau khi decoder xử lý thành công**, không tự làm kiểm tra nào.

Có thể ánh xạ một claim:

~~~java
@GetMapping("/api/jwt/tenant")
public Map<String, String> tenant(
        @AuthenticationPrincipal(
            expression = "claims['tenant_id']")
        String tenantId) {
    return Map.of("tenantId", tenantId);
}
~~~

Đây là fragment minh họa. `tenant_id` cần tồn tại, có kiểu chuỗi và được issuer cấp/kiểm theo hợp đồng. `Map.of` không chấp nhận giá trị `null`; production phải xử lý thiếu claim bằng chính sách rõ ràng. **Không lấy tenant từ một claim chưa được decoder và token validator xác minh**.

Ngoài ra, `aud` và `scope` vẫn phải được kiểm theo chính sách Resource Server. Chỉ biết `sub` chưa đủ để quyết định user được đọc tất cả bản ghi của tenant.

### 8.2. OAuth2 login

Với `oauth2Login()`, principal thường là `OAuth2User` và thuộc tính identity có thể nằm trong `attributes`:

~~~java
@GetMapping("/account/oauth")
public Map<String, String> oauth(
        @AuthenticationPrincipal OAuth2User oauthUser) {
    return Map.of("name", oauthUser.getName());
}
~~~

Fragment này dùng class `org.springframework.security.oauth2.core.user.OAuth2User`. `getName()` phụ thuộc provider/user-name attribute đã cấu hình; có thể là provider-specific ID chứ không phải email. Khi cần ánh xạ thành account nội bộ, sử dụng service ánh xạ theo issuer/provider + subject bền vững, không tự đồng nhất email.

### 8.3. OpenID Connect login

Với OIDC login, principal có thể là `OidcUser`:

~~~java
@GetMapping("/account/oidc")
public Map<String, String> oidc(
        @AuthenticationPrincipal OidcUser user) {
    return Map.of("subject", user.getSubject());
}
~~~

Fragment dùng `org.springframework.security.oauth2.core.oidc.user.OidcUser`. Trong OIDC, subject cần hiểu theo **issuer**, không chỉ theo một chuỗi ID toàn cục. Đừng đưa nguyên ID token hoặc toàn bộ claims nhạy cảm ra response.

### 8.4. Bảng chọn kiểu principal

| Kiểu authentication thường gặp | Principal hay gặp | Kiểu tham số dùng với @AuthenticationPrincipal |
| --- | --- | --- |
| Basic/form + `UserDetailsService` | `UserDetails`, custom user | `UserDetails` hoặc custom class tương ứng |
| JWT Resource Server | `Jwt` | `Jwt` hoặc SpEL thuộc tính/claim |
| Opaque token Resource Server | `OAuth2AuthenticatedPrincipal` | Principal/interface tương ứng |
| OAuth2 login | `OAuth2User` | `OAuth2User`, custom OAuth2User |
| OIDC login | `OidcUser` | `OidcUser`, custom OIDC principal |
| Anonymous request | Thường là chuỗi `anonymousUser` trong `AnonymousAuthenticationToken` | Khi mong `AppPrincipal`, thường null; phải xét public endpoint |

Các class và phụ thuộc phải có trong ứng dụng tương ứng. Không thể copy nguyên fragment `Jwt` vào project HTTP Basic rồi kỳ vọng Spring tự tạo JWT principal.

## 9. Khi nào nên ánh xạ sang đối tượng miền (domain user)?

Một thiết kế sạch là phân biệt:

~~~text
Authentication principal (đã xác thực)
        |
        | stable internalId / issuer+subject
        v
Application user lookup / authorization service
        |
        | kiểm tenant, account status, quyền đối tượng
        v
Domain User / business entity
        |
        v
DTO dành cho response
~~~

Lợi ích:

- `UserDetails`/`Jwt` giữ trách nhiệm authentication; entity JPA giữ trách nhiệm persistence.
- Có thể đổi cách đăng nhập mà không phải viết lại mọi service thao tác dữ liệu.
- Dễ tránh leak password hash, token claims và thông tin security session khi serialize.
- Có thể kiểm trạng thái account hiện tại, role, tenant và object-level policy thay vì dựa vào dữ liệu stale của principal.

Một controller theo cách này có thể truyền ID đã xác thực tới service:

~~~java
@GetMapping("/api/my-orders")
public List<OrderResponse> myOrders(
        @AuthenticationPrincipal(expression = "id") UUID accountId) {
    return orderService.findVisibleOrdersFor(accountId);
}
~~~

**Đây là fragment kiến trúc**, cần có `OrderResponse`, `orderService`, các import và method thực tế; không nằm trong project demo ở mục 6. `findVisibleOrdersFor` vẫn phải enforce quyền, tenant và object ownership. Nếu service nhận một `accountId` thông thường từ call khác, không thể giả định mọi caller đã được controller xác thực.

### Tránh IDOR

Không dùng:

~~~java
@GetMapping("/api/users/{userId}/orders")
public List<OrderResponse> unsafe(@PathVariable UUID userId) {
    return orderService.findAllFor(userId);
}
~~~

nếu logic chỉ dựa vào client-supplied `userId` để xác định được xem dữ liệu của ai. Đây là fragment mô tả anti-pattern. Với endpoint “my orders”, lấy current subject từ trusted principal. Với endpoint quản trị đọc đơn của người khác, phải có **explicit authorization** cho actor hiện tại trên target user/tenant.

**@AuthenticationPrincipal chỉ giúp lấy actor đáng tin; nó không tự làm object-level authorization.**

## 10. Anonymous, principal null và lỗi ép kiểu

### 10.1. Endpoint permitAll

Ở endpoint public, Spring Security thường có `AnonymousAuthenticationToken` với principal dạng `String "anonymousUser"`. Nếu method mong `AppPrincipal`, resolver mặc định có thể trả `null`. Không có gì bất thường: endpoint không yêu cầu đăng nhập.

~~~java
@GetMapping("/api/greeting")
public String greet(@AuthenticationPrincipal UserDetails current) {
    return current == null ? "Xin chào khách" :
            "Xin chào " + current.getUsername();
}
~~~

Đoạn này là fragment. Trong endpoint authenticated bắt buộc, nên dùng `.authenticated()` để yêu cầu có authentication hợp lệ trước khi controller dùng principal.

### 10.2. isAuthenticated không đủ để nhận biết end-user thực

`AnonymousAuthenticationToken` trong Spring Security có thể báo `isAuthenticated() == true` theo cơ chế token nội bộ. Vì vậy đừng viết policy “nếu `auth.isAuthenticated()` thì đã login” mà quên phân biệt anonymous, remember-me và fully authenticated. Dùng các authorization request matcher `authenticated()`, `fullyAuthenticated()` hoặc `AuthenticationTrustResolver` theo yêu cầu bảo mật. Tham số `@AuthenticationPrincipal` tự nó không giải quyết phân loại này.

### 10.3. Nhiều SecurityFilterChain và mismatch

Nếu `/api/**` nhận JWT mà `/admin/**` dùng form login, principal có thể có hai kiểu khác nhau. Một controller tái sử dụng chung `@CurrentUser AppPrincipal` có thể sai ở JWT chain. Cần thiết kế strategy ánh xạ thống nhất, hoặc dùng controller/annotation phù hợp từng chain. Với multi-auth application, có thể tạo service chuẩn hóa authenticated actor từ những authentication types đã được tin cậy và kiểm thử mọi đường đi; **không bao giờ tự coi mọi Object principal là AppPrincipal**.

### 10.4. SpEL thiếu property

Nếu dùng `expression = "id"` trên principal mà không có getter `getId()`, SpEL có thể ném lỗi vì không tìm thấy property; `errorOnInvalidType=false` không bảo đảm xóa lỗi expression. Khi thay đổi class principal, test injection/expression và giữ contract cho API.

## 11. Tương tác với authorization, method security và CSRF

### Authorization phải chạy trước khi dựa vào principal

Cấu hình `requestMatchers("/api/me").authenticated()` bảo đảm chỉ người đã xác thực được gọi endpoint. Nếu endpoint yêu cầu quyền cụ thể, thêm policy như `hasAuthority("ROLE_READER")` hoặc method security trong lớp dịch vụ, tùy yêu cầu. Đừng dựa vào sự tồn tại của một tham số annotation để bảo vệ URL.

Trong Spring Security 6, có thể dùng `@EnableMethodSecurity` và `@PreAuthorize` trên service để bảo vệ các thao tác, nhưng cần thiết kế đúng cách evaluator/permissions và tránh để client tự truyền actor ID. Phạm vi của bài này là **ánh xạ principal vào MVC method**, không phải hướng dẫn đầy đủ method-level authorization.

### CSRF là một vấn đề khác

`@AuthenticationPrincipal` đọc authentication, không kiểm tra CSRF token. Một browser có thể tự đính kèm session cookie hoặc Basic credentials trong bối cảnh nhất định; các HTTP methods thay đổi trạng thái cần bảo vệ CSRF theo threat model. Không tắt CSRF chỉ vì controller đã có principal hoặc vì ứng dụng “stateless” trong Spring Security. Với Bearer-only APIs không dựa trên ambient browser credentials, chính sách CSRF có thể khác; phải đánh giá đúng cơ chế auth.

### Không tự tạo Authentication trong controller

Các đoạn như `SecurityContextHolder.getContext().setAuthentication(...)` trong controller chỉ để “giúp @AuthenticationPrincipal chạy” là dấu hiệu cấu hình sai. Người dùng phải được xác thực bởi filter/authentication manager trước khi request tới controller. Việc tự đặt principal từ tham số request tạo nguy cơ authentication bypass.

## 12. Ranh giới tin cậy và thông tin nhạy cảm

### 12.1. Principal được lấy từ SecurityContext, nhưng phải biết ai tạo ra nó

`@AuthenticationPrincipal` tin vào kết quả trong `SecurityContext`. Nếu project có custom filter lấy `X-User: admin` từ HTTP header rồi set authentication mà không xác minh proxy/transport, annotation sẽ trả chính “admin” giả đó. Resolver không thể sửa một authentication pipeline vốn không đáng tin.

Nếu có proxy xác thực phía trước, backend phải chặn đường bypass, xác minh trusted proxy/service identity, xóa header do client gửi và gắn identity chỉ sau khi proxy đã xác thực. Hoặc dùng JWT assertion ký số mà backend xác minh issuer/audience/signature/time, tùy kiến trúc.

### 12.2. Tránh log và serialize toàn bộ principal

Principal có thể mang password hash, authorities nội bộ, JWT claims, tokens hoặc dữ liệu nhận dạng cá nhân. Không trả thẳng `Authentication`, `Jwt` hay entity JPA ra public API. Chỉ trả DTO với các field được phép. Không ghi token/credential vào log; khi debug type mismatch có thể log tên class và request ID đã sanitize thay vì dump toàn bộ object.

### 12.3. Principal có thể cũ hơn dữ liệu hiện tại

Nếu account bị disabled, đổi role hoặc bị chuyển tenant sau khi token/session được tạo, principal trong request có thể phản ánh trạng thái cũ tùy chiến lược xác thực/cache. Với quyền nhạy cảm, backend có thể cần lookup trạng thái user/entitlement mới nhất hoặc dùng token lifetime ngắn, revocation và policy nhất quán.

### 12.4. Async/thread context không tự truyền mọi nơi

Spring MVC request được xử lý trong ngữ cảnh security; nhưng công việc `@Async`, executor thread hoặc queue consumer không được mặc định có cùng `SecurityContext` trong mọi trường hợp. Đừng cố dùng `@AuthenticationPrincipal` trên method của service thông thường hoặc background worker — nó là **MVC argument resolver**. Truyền một `accountId` đã kiểm chứng vào service, hoặc dùng cơ chế context propagation dành cho Spring Security khi thật sự cần.

## 13. Bảng lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `@AuthenticationPrincipal UserDetails` luôn null dù login thành công | Principal thực tế là `Jwt`/`OAuth2User`/custom type hoặc không có auth. | Kiểm tra `authentication.getPrincipal().getClass()` bằng logging an toàn; chọn type đúng. |
| `errorOnInvalidType=true` gây ClassCastException | Kiểu principal không tương thích kiểu tham số. | Đúng security chain và principal class? Bổ sung test. |
| `expression="id"` lỗi SpEL | Principal không có getter `getId()` hoặc expression không đúng. | Kiểm class và expression, test code path. |
| Public endpoint lỗi NullPointerException | `permitAll` không đảm bảo principal mang kiểu ứng dụng. | Xử lý null hoặc yêu cầu authenticated trước khi gọi getter. |
| Response vô tình lộ password hash | Trả trực tiếp `UserDetails` hoặc authentication object. | Tạo DTO tối thiểu, không serialize secrets. |
| `@AuthenticationPrincipal Jwt` null khi dùng Basic | Principal là `UserDetails`, không phải `Jwt`. | Chọn đúng authentication mechanism hoặc mapper. |
| Annotation không hoạt động với MVC test | Test không chạy security filters/resolver hoặc mock principal type khác. | Dùng `@SpringBootTest + @AutoConfigureMockMvc` hoặc cấu hình mock đúng. |
| `@WithMockUser` không ánh xạ AppPrincipal | Mock user không phải custom principal. | Dùng Basic provider thật hoặc custom Authentication. |
| `@AuthenticationPrincipal` được hiểu là authorization | Annotation không kiểm quyền. | Cấu hình `authorizeHttpRequests`/method authorization. |
| `@AuthenticationPrincipal` cho ra admin khi header bị giả | Custom filter/proxy tin raw header. | Kiểm boundary, network/mTLS, token validation và ingress stripping. |
| Dùng `getName()` làm khóa tenant | Tên không ổn định hoặc trùng giữa IdP/tenant. | Dùng issuer+subject hoặc internal stable ID. |
| Service async không thấy SecurityContext | Context không tự truyền sang thread/job khác. | Truyền actor ID rõ ràng hoặc dùng context propagation đúng. |
| Đã authenticated nhưng hành động vẫn 403 | Thiếu authority, CSRF token hoặc object permission. | Phân biệt validation/authentication/authorization/CSRF. |
| Trả 401 nhưng Controller breakpoint không chạy | SecurityFilterChain đã chặn request trước MVC. | Kiểm security rules, credential/decoder và entry point. |

### Checklist debug từng bước

1. Xác nhận request đi qua **đúng SecurityFilterChain** và endpoint có policy authentication phù hợp.
2. Xác nhận login/JWT decoder đã tạo `Authentication` hợp lệ trước khi request vào controller.
3. Kiểm kiểu `Authentication.getPrincipal()` và giá trị `Authentication.getName()` — chỉ log thông tin đã lọc, không dump token.
4. Kiểm kiểu Java của tham số `@AuthenticationPrincipal` và SpEL expression (nếu có).
5. Nếu public endpoint, xử lý `null`/anonymous, không giả định luôn có user.
6. Nếu cần authorities/permission, dùng authorization policy và service, không nhầm chúng là thuộc tính của resolver.
7. Đảm bảo DTO không chứa password hash, credentials, token hoặc claims nhạy cảm.
8. Viết test thực sự chạy filter/authentication provider; thêm test cho anonymous, wrong credentials, mismatch và multi-chain nếu có.

## 14. Tình huống áp dụng và câu hỏi tự kiểm tra

**Tình huống A — “My orders”.** Controller nhận cả `@PathVariable UUID accountId` và `@AuthenticationPrincipal AppPrincipal user`. Khách hàng tự sửa accountId thành của người khác, service không kiểm quyền. Có an toàn không?

**Đáp án:** Không. Parameter do client gửi không xác minh actor. Dùng principal ID để lấy tài nguyên của chính người đó, hoặc kiểm authorization tường minh actor có quyền đọc target account; không dựa vào annotation đơn lẻ.

**Tình huống B — App chuyển sang JWT Resource Server.** Trước đây controller nhận `@AuthenticationPrincipal UserDetails user`, sau chuyển JWT thì user nhận null. Vì sao?

**Đáp án:** JWT Resource Server thường lưu principal kiểu `Jwt`, không phải `UserDetails`. Cần dùng `@AuthenticationPrincipal Jwt jwt` hoặc có lớp mapper chuẩn hóa từ JWT đã được xác thực sang principal ứng dụng.

**Tình huống C — Method public.** Endpoint `permitAll` dùng `@AuthenticationPrincipal(errorOnInvalidType=true) AppPrincipal` và người chưa đăng nhập gọi. Có chắc Spring sẽ tự trả 401 không?

**Đáp án:** Không. Annotation không tạo authorization rule. Với anonymous, principal có thể không phù hợp và resolver sẽ không cung cấp AppPrincipal; endpoint phải xử lý null hoặc chuyển policy thành authenticated.

**Tình huống D — SpEL.** `@AuthenticationPrincipal(expression="id") UUID id` có an toàn hơn `@RequestParam UUID id` để xác định người đang gọi?

**Đáp án:** Với authentication pipeline đáng tin, SpEL lấy internal ID từ principal đã xác thực thay vì ID do client khai. Nhưng service vẫn phải kiểm quyền/tenant; annotation không thay thế business authorization.

**Tình huống E — Test.** `@WithMockUser("alice")` pass với endpoint đọc `Authentication.getName()` nhưng fail với endpoint `@CurrentUser AppPrincipal`. Có phải lỗi framework?

**Đáp án:** Không nhất thiết. Mock principal thường là `User` của Spring Security, không phải custom AppPrincipal. Test phải tạo đúng principal hoặc đi qua authentication provider thật.

**Tình huống F — Header giả mạo.** Backend có custom filter biến `X-User: admin` thành Authentication và controller dùng `@AuthenticationPrincipal`. Liệu annotation làm cho header đáng tin?

**Đáp án:** Không. Resolver chỉ lấy principal có sẵn trong security context. Cần thiết kế trust boundary với gateway, chặn direct access và/hoặc xác minh assertion, không tin header thô.

### Câu hỏi ngắn

1. **`@AuthenticationPrincipal` đọc đối tượng nào?** Giá trị `Authentication.getPrincipal()` của authentication đang được Spring Security đặt vào security context.
2. **Cần toàn bộ authorities thì dùng gì?** `Authentication.getAuthorities()` hoặc method security/authorization policy; annotation này chủ yếu đọc principal.
3. **`expression="username"` có tác dụng gì?** Đánh giá SpEL property `username` trên principal, thông thường gọi `getUsername()` nếu có.
4. **`errorOnInvalidType=true` bảo đảm quyền đăng nhập không?** Không; nó chỉ báo lỗi khi kiểu trả về không phù hợp.
5. **Khi principal là JWT thì class nào phù hợp?** Thường là `org.springframework.security.oauth2.jwt.Jwt` trong JWT Resource Server.
6. **`@CurrentUser` meta-annotation có cần filter riêng không?** Không; nó dùng lại `AuthenticationPrincipalArgumentResolver`.
7. **Có nên trả nguyên `UserDetails` ra API không?** Không; tạo DTO tối thiểu để không lộ credentials hoặc fields nội bộ.
8. **Vì sao test MockMvc cần đúng kiểu principal?** Vì annotation lấy principal thật của authentication trong test context; mock `User` không tự biến thành custom `AppPrincipal`.
9. **Annotation có hoạt động trong @Async service không?** Không phải cơ chế tiêm argument chung; nó áp dụng cho MVC handler. Async code cần actor/context được truyền có chủ đích.
10. **Nếu `Authentication.getPrincipal()` do một filter không đáng tin tạo ra, annotation có bảo vệ được không?** Không; phải sửa authentication/trust boundary.

**Kết luận:** `@AuthenticationPrincipal` là công cụ **ánh xạ danh tính đã xác thực của Spring Security vào tham số MVC Controller**. Khi dùng đúng, nó giúp bỏ code đọc `SecurityContextHolder`, giảm ép kiểu thủ công và dễ xây dựng endpoint “current user”. Tuy nhiên **kiểu principal phụ thuộc authentication mechanism**, SpEL cần đúng getter/claims, anonymous có thể trả null, và mọi quyết định truy cập vẫn phải dựa trên **authentication pipeline đáng tin + authorization ở URL, method và business object**.