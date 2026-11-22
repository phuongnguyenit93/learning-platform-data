# Vai trò của các thư viện core, web, config, crypto và test trong Spring Security

Khi khởi tạo dự án Spring Security, bạn có thể thấy các artifact như `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-crypto` và `spring-security-test` trong cây dependency. Chúng thuộc cùng hệ sinh thái nhưng đảm nhiệm **những trách nhiệm khác nhau**: cung cấp mô hình danh tính và quyền, bảo vệ request web, khai báo chính sách, xử lý mật mã cần thiết và hỗ trợ kiểm thử.

Hiểu vai trò từng thư viện giúp bạn biết nên import class từ đâu, lý giải vì sao `spring-boot-starter-security` thường đủ cho một ứng dụng web cơ bản, phát hiện thiếu dependency và kiểm thử đúng phần bảo mật đang muốn chứng minh. Bài lấy **Spring Boot 3 + Spring Security 6, Java 17+ và ứng dụng Servlet/Spring MVC** làm bối cảnh. Với phiên bản Spring Boot/Spring Security khác, hãy dùng tài liệu tương ứng và để BOM/dependency management chọn các phiên bản tương thích.

## 1. Bức tranh tổng thể: năm module, năm nhóm trách nhiệm

| Artifact | Vai trò chính | Ví dụ class / API | Thường sử dụng ở đâu? |
| --- | --- | --- | --- |
| **`spring-security-core`** | Các abstraction nền tảng cho authentication, security context, authority, authorization | `Authentication`, `SecurityContextHolder`, `GrantedAuthority`, `UserDetails`, `AuthenticationManager`, `AuthorizationManager` | Logic xác thực/phân quyền ở tầng ứng dụng và các module tích hợp |
| **`spring-security-web`** | Tích hợp an ninh với request/response web, chủ yếu qua filter chain trong ứng dụng Servlet | `SecurityFilterChain`, `FilterChainProxy`, `BasicAuthenticationFilter`, `CsrfFilter`, `AuthorizationFilter` | Web/API request processing |
| **`spring-security-config`** | Khai báo, lắp ráp và cấu hình các chính sách bảo mật | `HttpSecurity`, `@EnableWebSecurity`, `@EnableMethodSecurity`, `authorizeHttpRequests`, `httpBasic` | Lớp `@Configuration` và security DSL |
| **`spring-security-crypto`** | Các primitive/hỗ trợ mã hóa đối xứng, sinh khóa và **mã hóa một chiều mật khẩu** | `PasswordEncoder`, `BCryptPasswordEncoder`, `PasswordEncoderFactories`, `Encryptors`, `KeyGenerators` | Password storage, cryptographic utility theo nhu cầu |
| **`spring-security-test`** | Tạo security context giả lập, tích hợp MockMvc và công cụ thử request có/không có quyền | `@WithMockUser`, `user()`, `httpBasic()`, `csrf()`, `springSecurity()` | `src/test`, test classpath |

Năm module này **không phải năm công đoạn luôn chạy tuần tự**. `core` định nghĩa hợp đồng và đối tượng dùng chung; `web` xử lý ranh giới HTTP; `config` tạo cấu hình và lắp các thành phần; `crypto` cung cấp công cụ phục vụ việc bảo vệ bí mật, đặc biệt là password; `test` giúp kiểm chứng hành vi trong bài test, không phải một lớp bảo vệ tự động tại runtime.

Một cách ghi nhớ:

```text
                 +----------------------+
                 | spring-security-test |
                 |  test security flow  |
                 +-----------+----------+
                             | hỗ trợ kiểm thử
                             v
  +----------------------- ỨNG DỤNG WEB -----------------------+
  |                                                           |
  |  spring-security-config           spring-security-web     |
  |  HttpSecurity / policy    --->    SecurityFilterChain     |
  |                                   FilterChainProxy        |
  |                                   Authentication filters  |
  |                                          |                |
  |                                          v                |
  |                              spring-security-core         |
  |                              Authentication / Context     |
  |                              GrantedAuthority / authz     |
  |                                          ^                |
  |                                          |                |
  |                              spring-security-crypto       |
  |                              PasswordEncoder, hashing     |
  +-----------------------------------------------------------+
```

Mũi tên thể hiện **quan hệ trách nhiệm ở mức khái niệm**, không phải danh sách phụ thuộc Maven chính xác. Để biết một class nằm trong JAR nào, xem package/JAR; để biết dependency thực tế, kiểm tra `runtimeClasspath` và `testRuntimeClasspath` của chính dự án.

## 2. spring-security-core: ngôn ngữ chung của xác thực và phân quyền

`spring-security-core` cung cấp các interface/implementation cốt lõi, dùng được ở nhiều loại ứng dụng chứ không gắn chặt với HTTP Servlet.

Các khái niệm điển hình:

- **`Authentication`** biểu diễn yêu cầu hoặc kết quả xác thực, chứa `principal`, `credentials`, `authorities` và trạng thái `authenticated`.
- **`AuthenticationManager`** và **`AuthenticationProvider`** điều phối/triển khai việc xác minh danh tính theo cơ chế phù hợp.
- **`SecurityContext`** lưu `Authentication` của ngữ cảnh xử lý; **`SecurityContextHolder`** là API truy cập context.
- **`GrantedAuthority`** mô tả quyền được cấp, thường dưới dạng role/permission/scope; **`SimpleGrantedAuthority`** chứa chuỗi quyền cụ thể.
- **`UserDetails`**, **`UserDetailsService`** và các class liên quan mô tả người dùng trong luồng username/password.
- **`AuthorizationManager`** là abstraction để đưa ra quyết định truy cập từ một `Authentication` và ngữ cảnh được bảo vệ.

Ví dụ các import thuộc nhóm core:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.authorization.AuthorizationManager;
```

Một đoạn code đọc danh tính/authority đã có trong context:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String principalName = authentication.getName();
    boolean hasAdmin = authentication.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
}
```

Đây là **đoạn minh họa trong ứng dụng có Spring Security**, chưa phải một chương trình Java độc lập. Với request anonymous, `authentication` có thể null hoặc là một anonymous token; `isAuthenticated()` của token anonymous có thể trả true. Để bảo vệ endpoint, hãy dùng rule `authenticated()` của Spring Security và chính sách quyền cần thiết thay vì chỉ dựa vào `authentication != null` hoặc `isAuthenticated()`.

**Giới hạn của core:** các abstraction này **không tự chặn HTTP request** nếu bạn không tích hợp đúng vào security filter chain hoặc cơ chế gọi tương ứng. Một đối tượng `Authentication` được tạo bằng tay và gán `authenticated=true` cũng không có nghĩa credentials đã được xác minh.

## 3. spring-security-web: áp dụng bảo mật cho HTTP request

Trong mô hình Servlet, việc bảo vệ request chủ yếu được thực hiện qua filter. Các lớp đáng chú ý:

- **`FilterChainProxy`** là bộ phận trung tâm, chọn `SecurityFilterChain` phù hợp với request.
- **`SecurityFilterChain`** chứa danh sách filter và matcher dành cho một nhóm request.
- **`BasicAuthenticationFilter`** tiếp nhận HTTP Basic authentication khi được bật.
- **`UsernamePasswordAuthenticationFilter`** phục vụ cơ chế form login theo cấu hình.
- **`CsrfFilter`** kiểm tra CSRF token ở request cần bảo vệ.
- **`AuthorizationFilter`** thực thi chính sách authorization đã được lắp ráp.
- **`ExceptionTranslationFilter`** xử lý các ngoại lệ authentication/authorization theo cơ chế web.

Các class này thường ở `org.springframework.security.web...`. Spring Boot sẽ tích hợp filter với Servlet container qua cơ chế đăng ký phù hợp; khi dùng starter và cấu hình chuẩn, bạn thường **không tự đăng ký từng filter bằng tay**.

Luồng khái niệm:

```text
Client HTTP request
        |
        v
Servlet filter chain
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy  (spring-security-web)
        |
        v
Matching SecurityFilterChain
        |
        +-- Security filters: context, CSRF, authentication, authz ...
        |
        v
DispatcherServlet -> Controller -> Service
```

**Không được xem các bước trong sơ đồ là thứ tự cố định của mọi filter.** Thứ tự thực tế khác nhau theo cơ chế, matcher và cấu hình, và một filter có thể từ chối request trước khi controller được gọi.

### 3.1. SecurityFilterChain khác HttpSecurity

- `SecurityFilterChain` là abstraction trong **`spring-security-web`**, mô tả chuỗi filter được chọn cho request.
- `HttpSecurity` là **builder thuộc `spring-security-config`**, dùng khai báo và xây dựng `SecurityFilterChain`.

Ví dụ bạn viết:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

`HttpSecurity` giúp *cấu hình*, còn đối tượng `SecurityFilterChain` sau `build()` được *sử dụng để bảo vệ request*. Code trên là một fragment của lớp `@Configuration`, cần imports/dependencies và cách cung cấp user xác thực.

### 3.2. Nhiều chain và lỗi lọt request

Ứng dụng có thể khai báo nhiều `SecurityFilterChain`, mỗi chain dùng `securityMatcher` và thứ tự ưu tiên riêng. `FilterChainProxy` chọn **chain đầu tiên khớp**; các chain còn lại không tự động áp vào cùng request. Nếu không có chain nào khớp, request có thể không đi qua bảo vệ của Spring Security.

Do đó, khi tách riêng `/api/**` và `/admin/**`, cần kiểm tra độ ưu tiên và chain fallback. Với một ứng dụng đơn giản, dùng một chain với `anyRequest().denyAll()` cho các endpoint chưa khai báo là cách giữ chính sách tường minh.

## 4. spring-security-config: khai báo và lắp ghép chính sách

`spring-security-config` cung cấp API để khai báo security bằng Java configuration (và những hình thức cấu hình được hỗ trợ). Đây là nơi bạn thường gặp:

- **`HttpSecurity`**: builder để khai báo HTTP security.
- **`@EnableWebSecurity`**: kích hoạt cơ chế cấu hình web security khi cần ở ứng dụng Spring.
- **`@EnableMethodSecurity`**: bật khả năng bảo vệ phương thức bằng `@PreAuthorize`, `@PostAuthorize`... theo cấu hình.
- **`authorizeHttpRequests`**, **`requestMatchers`**, **`httpBasic`**, **`formLogin`**, **`csrf`**, **`sessionManagement`** và các DSL khác.

Ví dụ:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là fragment cấu hình (thiếu imports và lớp ứng dụng), không phải file Java độc lập. Quy tắc trong `authorizeHttpRequests` được xét theo thứ tự, vì thế matcher hẹp nên đứng trước `anyRequest()`. `hasRole("ADMIN")` mặc định yêu cầu authority `ROLE_ADMIN`; `hasAuthority("ADMIN")` lại so khớp chính xác chuỗi `ADMIN`.

### 4.1. Config module không thay thế core hoặc web

`spring-security-config` giúp tạo các bean, policy và chain; nó không tự trở thành filter HTTP xử lý request. Các quyền và danh tính vẫn dùng abstraction từ `core`, còn filter thực thi trong Servlet thường đến từ `web`.

Cũng cần phân biệt **Spring Boot autoconfiguration** với `spring-security-config`. Boot có cơ chế tự cấu hình, starter và dependency management của riêng Boot; `spring-security-config` là module Spring Security cung cấp công cụ cấu hình bảo mật. Chúng phối hợp chứ không phải một artifact.

### 4.2. Vì sao không nên sao chép cấu hình cũ?

Với Spring Security 6, `WebSecurityConfigurerAdapter` đã không còn là API cấu hình được dùng. Mẫu hiện đại là khai báo bean `SecurityFilterChain` và những bean bảo mật cần thiết. Spring Boot 3 dùng namespace **`jakarta.servlet`** thay cho các import Servlet cũ `javax.servlet`.

Khi đọc tài liệu nhiều phiên bản, hãy đối chiếu API tương ứng thay vì trộn code của Spring Security 5, 6 và 7. Nếu không thấy `HttpSecurity` hoặc `@EnableMethodSecurity`, hãy kiểm tra dependency `spring-security-config`, phiên bản và import, không tự thêm JAR với phiên bản khác vào classpath.

## 5. spring-security-crypto: password encoding, sinh khóa và mã hóa

`spring-security-crypto` chứa các công cụ mật mã của Spring Security. Các nhu cầu phổ biến gồm:

| Nhóm chức năng | API ví dụ | Mục đích |
| --- | --- | --- |
| Hash password | `PasswordEncoder`, `BCryptPasswordEncoder` | Lưu và đối chiếu password qua hash có salt, thay vì plaintext |
| Tương thích/nâng cấp hash | `DelegatingPasswordEncoder`, `PasswordEncoderFactories` | Định danh thuật toán qua tiền tố như `{bcrypt}` và hỗ trợ migration |
| Sinh khóa/salt | `KeyGenerators` | Sinh dữ liệu dùng trong cơ chế mật mã phù hợp |
| Mã hóa dữ liệu đối xứng | `Encryptors`, `BytesEncryptor`, `TextEncryptor` | Mã hóa dữ liệu cần giải mã, khi use case và key management đúng |

**Password encoding khác encryption:**

- Password nên được **hash một chiều**, có salt và thuật toán password hashing phù hợp. Khi đăng nhập, kiểm tra với `PasswordEncoder.matches(rawPassword, storedHash)`.
- Dữ liệu cần lấy lại nguyên bản, ví dụ một secret phải gửi tiếp tới hệ thống khác, có thể cần **mã hóa hai chiều** và quản lý key, phân quyền, vòng đời; không dùng password hashing cho bài toán đó.
- Không dùng Base64, SHA-256 đơn giản hoặc mã hóa đối xứng thay cho password hashing chuyên dụng khi lưu password.

Ví dụ:

```java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode("demo-password");
boolean right = encoder.matches("demo-password", storedHash);
boolean wrong = encoder.matches("wrong-password", storedHash);
```

Đoạn code trên yêu cầu dependency Spring Security phù hợp. Kết quả `right` là `true`, `wrong` là `false`; giá trị hash **không cố định** vì có salt. `DelegatingPasswordEncoder` thường lưu tiền tố nhận diện thuật toán trong hash, chẳng hạn `{bcrypt}...`.

**Không so sánh hai lần `encode` bằng equals:** dùng `matches`. Không hardcode password thật, log plaintext password/hash hay lưu hash bằng chuỗi cố định từ tài liệu demo trong production.

### 5.1. Crypto không tự làm authentication hoặc authorization

`spring-security-crypto` có thể được dùng độc lập để encode/check password, nhưng tự nó không hiểu:

- User nào đang cố đăng nhập;
- Account có bị khóa/vô hiệu hóa không;
- Principal cần nhận authorities gì;
- Endpoint hoặc object nào được phép truy cập;
- CSRF, session hay filter chain nào đang dùng.

Các trách nhiệm đó thuộc provider, policy, web layer và logic nghiệp vụ. `PasswordEncoder` là một thành phần **của quá trình xác thực password**, không phải giải pháp bảo mật toàn diện.

## 6. spring-security-test: kiểm tra hành vi bảo mật trong bài test

`spring-security-test` là thư viện **dành cho test scope**. Các công cụ thường gặp:

| Công cụ | Mục đích | Có kiểm tra password thật không? |
| --- | --- | --- |
| `@WithMockUser` | Đặt một user giả lập vào SecurityContext khi chạy test | Không |
| `with(user("alice"))` | Gắn user/authority giả lập cho một request MockMvc | Không |
| `with(httpBasic("alice", "password"))` | Đưa header Basic vào request để đi qua filter xác thực được cấu hình | Có thể kiểm tra qua provider thật trong integration test |
| `with(csrf())` | Thêm CSRF token hợp lệ cho request MockMvc | Không phải xác thực user |
| `with(csrf().useInvalidToken())` | Tạo trường hợp CSRF sai | Không |
| `springSecurity()` | Tích hợp Spring Security với MockMvc được dựng thủ công | Là cấu hình test, không phải auth provider |
| `@WithAnonymousUser` | Chạy test với identity anonymous | Không |

Ví dụ:

```java
mvc.perform(get("/admin")
        .with(user("reader").roles("USER")))
    .andExpect(status().isForbidden());

mvc.perform(post("/notes")
        .with(user("reader").roles("USER"))
        .with(csrf()))
    .andExpect(status().isOk());
```

Các lệnh trên **giả định** ứng dụng có controller và rule phù hợp, MockMvc được tích hợp Spring Security, static imports tương ứng và endpoint `POST /notes` thực sự cho phép ghi. `user()` tạo ngữ cảnh user giả; nó chứng minh **authorization với quyền đã cho**, chứ chưa kiểm tra `UserDetailsService` và `PasswordEncoder` có xác thực password đúng hay không.

### 6.1. Test authn và test authz phải có chủ đích

- Dùng `httpBasic()`, form login test hoặc token verifier phù hợp khi muốn đi qua cơ chế **authentication thật**.
- Dùng `@WithMockUser`/`user()` khi muốn cô lập và kiểm tra **authorization/policy** với các quyền định sẵn.
- Dùng `csrf()` hoặc token sai khi kiểm tra **CSRF protection** trong ứng dụng Servlet có bật CSRF.
- Test cả anonymous, tài khoản đúng quyền, tài khoản thiếu quyền, request thiếu token CSRF và request có token đúng.
- Với thao tác nhạy cảm, không chỉ assert HTTP status mà còn kiểm tra database hoặc mock service **không nhận side effect** khi bị từ chối.

### 6.2. Test jar có bảo vệ production không?

Không. `spring-security-test` giúp viết và chạy bài test; nó không tự bổ sung filter bảo vệ production và không được sử dụng làm nguồn chính cho runtime code. Hãy để dependency ở `testImplementation` (Gradle) hoặc `test` scope (Maven).

## 7. Khởi tạo dependency trong Spring Boot

### 7.1. Cách khuyến nghị với Spring Boot 3

Đối với Spring MVC, hãy tạo một dự án Spring Boot 3 tương thích Java 17+ qua Spring Initializr hoặc template Boot hợp lệ. Trong `build.gradle` (Groovy DSL) đã có Boot Gradle plugin, thường chỉ cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-boot-starter-security` gom các dependency bảo mật cần thiết cho use case thông thường (đặc biệt config và web, các abstraction core/crypto được kéo vào theo cây dependency). `spring-boot-starter-web` cung cấp Spring MVC/Servlet cho ứng dụng ví dụ. `spring-boot-starter-test` có JUnit 5, Spring Test và các tiện ích test của Boot; `spring-security-test` thêm các tiện ích kiểm thử bảo mật.

Vì Spring Boot quản lý phiên bản qua BOM/plugin, **không thêm số phiên bản độc lập** cho `spring-security-web`, `config` hoặc `test` chỉ để “chọn bản mới hơn”. Điều quan trọng là các module Spring Security phải tương thích với nhau và phiên bản Boot đang chạy.

Nếu dùng Maven trong project Boot đã cấu hình dependency management:

```xml
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
```

Đây chỉ là **đoạn phần dependencies**; không phải `pom.xml` đầy đủ. Khi dùng Maven không có Boot BOM, cần dependency management hoặc phiên bản được kiểm soát tương thích.

### 7.2. Có cần khai báo đủ cả năm module bằng tay?

**Thông thường không** khi dùng Spring Boot starter. Thêm năm module thủ công có thể tạo dependency trùng, quản lý version phức tạp và dễ gây nhầm lẫn về scope.

Nếu **không dùng Spring Boot** và tự tích hợp Spring Security Servlet, thông thường điểm bắt đầu trực tiếp là `spring-security-web` và `spring-security-config`, cùng cơ chế build/BOM quản lý version và các dependencies bổ sung tùy use case. `core`/`crypto` có thể đến qua phụ thuộc bắc cầu. `spring-security-test` cần khai báo riêng khi viết test. Đây là lý do hướng dẫn “thêm cả năm JAR là xong” không phản ánh đúng cách Spring Security được dùng.

### 7.3. Đọc cây dependency thật

Trong dự án Gradle:

```bash
# Runtime dependencies: module nào được nạp khi chạy app
./gradlew dependencies --configuration runtimeClasspath

# Test dependencies: gồm những gì khi chạy test
./gradlew dependencies --configuration testRuntimeClasspath

# Ai kéo core vào, version được chọn là gì?
./gradlew dependencyInsight \
  --dependency spring-security-core \
  --configuration runtimeClasspath

# Chạy test
./gradlew test
```

Trên Windows PowerShell, dùng `.\gradlew.bat` thay cho `./gradlew` và viết mỗi lệnh trên một dòng (bỏ dấu nối dòng `\` của Bash). Với Maven, dùng `mvn dependency:tree` để xem phiên bản và quan hệ transitive.

Lưu ý: cây dependency thực tế phụ thuộc phiên bản Boot/Security, các starter khác và cơ chế giải quyết version. Bảng/module ở bài này mô tả **trách nhiệm**, không thay thế việc kiểm tra output Gradle/Maven.

## 8. Ví dụ hoàn chỉnh: từ module đến HTTP request được bảo vệ

Bộ ví dụ này sử dụng **Spring Boot 3 / Java 17+**, Spring MVC, hai user lưu trong bộ nhớ và HTTP Basic. Các file nằm cùng package `demo.security`, có thể đưa vào một dự án Boot 3 đã khai báo dependencies ở mục 7.

Mục tiêu nhìn rõ từng lớp:

- **core:** `UserDetailsService`, `Authentication` và authority của user.
- **crypto:** `PasswordEncoderFactories` và `PasswordEncoder` hash password.
- **config:** `HttpSecurity` và matcher tạo security policy.
- **web:** `SecurityFilterChain` và các security filters xử lý request.
- **test:** MockMvc mô phỏng request và xác nhận 200/401/403/CSRF.

### 8.1. Tạo ứng dụng

Tạo `src/main/java/demo/security/SecurityModulesDemoApplication.java`:

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityModulesDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityModulesDemoApplication.class, args);
    }
}
```

Tạo `src/main/java/demo/security/SecurityConfig.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/me", "/notes").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Giải thích:

1. `users()` tạo hai `UserDetails` bằng dữ liệu demo; các password được đưa qua `PasswordEncoder`. `DelegatingPasswordEncoder` giúp đánh dấu thuật toán bằng tiền tố như `{bcrypt}`.
2. `HttpSecurity` là builder **config**; kết quả `SecurityFilterChain` là kiểu thuộc **web**.
3. `.hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo quy ước mặc định; `.roles("ADMIN")` khi tạo user cung cấp authority tương ứng.
4. `httpBasic` bật việc kiểm tra header Basic bằng các thành phần authentication thích hợp; `csrf` giữ bảo vệ request khi có CSRF.
5. `anyRequest().denyAll()` từ chối endpoint chưa có rule, tránh vô tình mở đường dẫn mới.
6. Password chỉ dùng thử tại máy cục bộ. Thực tế cần HTTPS, lưu trữ danh tính và secret theo tiêu chuẩn triển khai.

Tạo `src/main/java/demo/security/DemoController.java`:

```java
package demo.security;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/notes")
    public String addNote() {
        return "created";
    }
}
```

`Authentication` ở controller được lấy từ security context; đây là abstraction **core**. Trong ứng dụng thật, không nên trả nguyên Authentication hoặc credentials cho client. Endpoint `POST /notes` chỉ minh họa thứ tự xử lý quyền và CSRF; nó chưa ghi database.

### 8.2. Kiểm chứng bằng bài test chạy cùng Spring Boot

Tạo `src/test/java/demo/security/SecurityIntegrationTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
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
class SecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void privateEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void httpBasicAuthenticatesReader() throws Exception {
        mvc.perform(get("/me").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void adminRoleIsRequired() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void csrfIsRequiredForPost() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }
}
```

**Lưu ý về imports ở trên:** các static import được viết xuống dòng trước dấu chấm để dễ đọc; trong Java, dấu chấm tiếp nối chuỗi tên đầy đủ vẫn hợp lệ về mặt cú pháp. Nếu IDE áp dụng formatter, có thể viết mỗi `import static` trên một dòng. Tệp test cần Spring Boot test và `spring-security-test` trên test classpath, và MockMvc được tự động cấu hình với Spring Security bởi `@AutoConfigureMockMvc`.

Chạy:

```bash
./gradlew test --tests demo.security.SecurityIntegrationTest
```

Với Windows:

```powershell
.\gradlew.bat test --tests demo.security.SecurityIntegrationTest
```

**Kỳ vọng:** cả **5 phương thức test** đều pass trong dự án đúng cấu hình. Không đưa ra chuỗi stdout Gradle cố định vì số lượng task, log và phiên bản công cụ có thể khác. Các HTTP status được kiểm tra bằng assertions trong chính bài test.

### 8.3. Đọc lại kết quả dưới góc nhìn module

| Request giả lập | Expected | Module góp phần chính |
| --- | --- | --- |
| GET `/public` không login | 200 | `config` khai báo `permitAll`; `web` xử lý filter chain |
| GET `/me` không login | 401 | `web` xử lý Basic challenge; `core` cung cấp abstraction danh tính |
| GET `/me` với Basic hợp lệ | 200 | `web` nhận header; `core` xác thực; `crypto` kiểm tra hash |
| GET `/admin` với reader | 403 | `config` khai báo role; `core` là nguồn authority; `web` từ chối request |
| GET `/admin` với admin | 200 | Các thành phần trên phối hợp |
| POST `/notes` không CSRF token | 403 | `web` thực thi CSRF protection |
| POST `/notes` có CSRF token hợp lệ | 200 | `test` cung cấp CSRF token giả lập; `web` xác thực request |

Một HTTP 403 không tự chứng minh “thiếu role”, vì request cũng có thể bị CSRF chặn. Khi debug, cần xác định chính xác filter/policy nào từ chối.

### 8.4. Cách phân biệt test thật với @WithMockUser

`@WithMockUser` hoặc `with(user(...))` **giả lập** authentication trong test, phù hợp khi chỉ cần kiểm tra policy. Với `httpBasic("reader","reader-pass")` như ví dụ, request đi qua HTTP Basic và xác thực bằng user store/PasswordEncoder của ứng dụng, nhờ đó kiểm thử được luồng kết hợp nhiều module.

Một bài test dùng `@WithMockUser(roles = "ADMIN")` pass không tự chứng minh password trong database có thể login, hay OAuth2 token thật được verify đúng. Hãy chọn test dựa trên điều muốn chứng minh.

## 9. Mở rộng: khi cần thêm module ngoài năm module trên

Năm module chính giúp hiểu nền tảng, nhưng một ứng dụng có use case chuyên biệt có thể cần:

| Use case | Module/Starter thường liên quan | Lưu ý |
| --- | --- | --- |
| API dùng OAuth2 Bearer JWT | `spring-boot-starter-oauth2-resource-server`, các module OAuth2 Resource Server/Jose phù hợp | Kiểm tra signature, issuer, audience, thời hạn, scope; không tự tạo JWT verifier thiếu kiểm tra |
| Ứng dụng đăng nhập qua OAuth2/OIDC | `spring-boot-starter-oauth2-client` | Phân biệt OAuth2 client/OIDC login với resource server |
| Spring LDAP authentication | Module tích hợp LDAP khi có nhu cầu | Cần cấu hình directory, kết nối và quyền phù hợp |
| Method security | `@EnableMethodSecurity` từ config + cơ chế core | Method security phải thực sự được bật và gọi qua đúng ranh giới áp dụng |
| Ứng dụng reactive WebFlux | Cấu hình/kiến trúc security reactive tương ứng | Không bê nguyên Servlet filter và MockMvc sang WebFlux; tham khảo WebTestClient/WebFlux security |

Không mặc định mọi dependency trên đều nằm trong `spring-boot-starter-security`. Thêm đúng module theo kiểu ứng dụng và nhu cầu, đồng thời quản lý version nhất quán qua BOM.

## 10. Phân biệt lỗi do module với lỗi do cấu hình hoặc policy

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra đúng |
| --- | --- | --- |
| `Cannot resolve HttpSecurity` | Thiếu `spring-security-config`, import sai hoặc version không khớp | Kiểm tra starter, imports và cây runtime dependency |
| `Cannot resolve SecurityFilterChain` | Thiếu `spring-security-web` hoặc dependency không có trong module hiện tại | Kiểm tra starter/build configuration |
| `Cannot resolve PasswordEncoder` | Thiếu `spring-security-crypto` hoặc import sai | Kiểm tra `org.springframework.security.crypto.password.PasswordEncoder` |
| `Cannot resolve @WithMockUser` | Chưa thêm `spring-security-test` vào test classpath | Kiểm tra `testImplementation` và imports |
| `NoClassDefFoundError` khi chạy | JAR không có ở runtime, version xung đột hoặc dependency bị loại trừ | Đọc `runtimeClasspath` / `dependencyInsight` |
| GET private trả 401 | Không xác thực được hoặc thiếu credentials | Kiểm tra filter, cơ chế Basic/form/token, user store, log bảo mật |
| User đã login nhưng GET admin trả 403 | Thiếu authority hoặc policy từ chối | So sánh `ROLE_ADMIN` với `hasRole("ADMIN")`; kiểm tra quyền object |
| POST bằng MockMvc trả 403 | Có thể thiếu/sai CSRF token | Kiểm tra `csrf()` và loại cơ chế xác thực đang dùng |
| Một endpoint vô tình public | Chain/matcher cấu hình thiếu hoặc sai thứ tự | Kiểm tra `securityMatcher`, `@Order`, `anyRequest`, tests anonymous |
| Test pass nhưng production bị 401 | Test dùng `@WithMockUser` và không đi qua cơ chế xác thực thật | Bổ sung integration test `httpBasic`/token verifier thực |

**Đừng vội thêm dependency để sửa mọi 403.** Nếu project đã biên dịch, Spring Security đang chạy và chỉ sai quyền, nguyên nhân có thể nằm ở matcher, authority, CSRF hoặc business policy chứ không phải thiếu JAR.

## 11. Những nhầm lẫn phổ biến

1. **Coi core là đủ để bảo vệ HTTP.** Core cung cấp abstraction; muốn bảo vệ Servlet request cần tích hợp web filter và chính sách.
2. **Coi web là nơi viết toàn bộ policy.** Web nhận/trả request, còn `HttpSecurity` và các annotation cấu hình đến từ config; quyền business object vẫn cần service/repository.
3. **Coi config là Boot autoconfiguration.** Đây là hai hệ cơ chế phối hợp. Boot starter gom dependency và thiết lập mặc định, module config cung cấp DSL.
4. **Cho rằng crypto tự thực hiện đăng nhập.** `PasswordEncoder.matches` chỉ là một phần của authentication; nó không nạp user, đánh giá role hay bảo vệ route.
5. **Cho rằng test module phải chạy production.** `spring-security-test` thuộc phạm vi test và không thay thế filter thật.
6. **Dùng `@WithMockUser` để kết luận password login đã đúng.** Mock user không gọi password provider. Dùng integration test xác thực thật khi đó là mục tiêu kiểm tra.
7. **Thêm tất cả module bằng phiên bản khác nhau.** Dễ gây `NoSuchMethodError` hoặc xung đột classpath. Dùng BOM của Boot/Spring Security.
8. **Copy cấu hình `WebSecurityConfigurerAdapter` cũ vào Boot 3.** API hiện đại dùng bean `SecurityFilterChain`.
9. **Cho rằng `permitAll()` bỏ qua hết filter.** Request vẫn qua chain được chọn; chẳng hạn POST có thể vẫn bị CSRF chặn.
10. **Cho rằng role đủ bảo vệ mọi object.** Authentication và authority đúng không thay thế owner/tenant/record-level policy.
11. **Tắt CSRF để test pass.** Với ứng dụng dùng cookie/session, đây có thể là lỗ hổng; dùng `csrf()` trong test và đánh giá đúng threat model của API.
12. **Suy luận dependency từ tên package duy nhất.** Một module có thể dùng class từ module khác qua phụ thuộc bắc cầu; luôn kiểm tra artifact/JAR và cây dependency.
13. **Bỏ qua hệ reactive.** Spring WebFlux có cách cấu hình và test khác với Spring MVC; chọn hướng dẫn đúng loại ứng dụng.

## 12. Checklist khởi tạo một ứng dụng Spring Security

Trước khi bắt đầu code:

- Xác định loại ứng dụng: Spring MVC/Servlet hay Spring WebFlux/reactive.
- Chọn phiên bản Spring Boot và Java tương thích; để BOM quản lý Spring Security modules.
- Với Spring MVC cơ bản, dùng `spring-boot-starter-web` và `spring-boot-starter-security`.
- Thêm `spring-boot-starter-test` và `spring-security-test` ở test scope.
- Khai báo `SecurityFilterChain` cho đúng endpoints; định nghĩa rule có chủ đích và chặn các route chưa khai báo.
- Chọn authentication thích hợp: Basic cho demo, session/form hoặc bearer token cho sản phẩm theo nhu cầu.
- Chọn `PasswordEncoder` và cơ chế quản lý người dùng phù hợp nếu dùng password; không lưu plaintext.
- Bật CSRF đúng threat model; xác định CORS/headers/session policy nếu ứng dụng có browser client.
- Thiết kế kiểm tra permission theo action và object ở service; chỉ có role HTTP chưa đủ.
- Kiểm tra bằng unit + integration tests: anonymous, valid user, thiếu quyền, token/password sai, CSRF thiếu/sai, object khác owner, sai tenant.
- Dùng `dependencies` / `dependencyInsight` để chẩn đoán classpath thay vì đoán module.
- Khi nâng cấp phiên bản, đối chiếu documentation và chạy security regression tests.

## 13. Câu hỏi tự kiểm tra

**1.** Vì sao `Authentication` thuộc core nhưng `SecurityFilterChain` lại thuộc web? Chúng phục vụ khác nhau ở điểm nào?

**2.** `HttpSecurity` và `SecurityFilterChain` khác nhau như thế nào? Module nào cung cấp mỗi loại?

**3.** Một ứng dụng có `spring-security-core` và `spring-security-crypto` nhưng không dùng web filter. Điều đó đã tự bảo vệ `GET /api/admin` chưa?

**4.** Vì sao `PasswordEncoder.matches` có thể cho kết quả đúng nhưng một request vẫn bị HTTP 403?

**5.** Tại sao cần thêm `spring-security-test` nếu đã có `spring-boot-starter-test`?

**6.** Test `@WithMockUser(roles = "ADMIN")` pass chứng minh được gì, và chưa chứng minh được gì?

**7.** Khi POST `/notes` trả 403 vì thiếu CSRF token, nên sửa bằng cách thêm dependency hay xem lại cách tạo request test?

**8.** Trong Spring Boot 3, có nên khai báo đủ năm module bằng các version riêng biệt trong build file không?

**Đáp án gợi ý:**

1. Core chứa mô hình danh tính/quyền dùng chung; web gắn cơ chế đó vào request/filter HTTP.
2. `HttpSecurity` là builder ở config; `SecurityFilterChain` là đối tượng filter chain ở web.
3. Chưa. Cần tích hợp filter chain và policy phù hợp cho HTTP.
4. Password đúng chỉ chứng minh một bước xác thực; vẫn có thể thiếu authority, sai owner/tenant hoặc bị CSRF chặn.
5. Starter test cung cấp hạ tầng test chung; security-test bổ sung mock principal, CSRF, security request processors và tích hợp Security với MockMvc.
6. Kiểm chứng hành vi policy với user giả định có role ADMIN; chưa chứng minh password thực, token, provider hoặc UserDetailsService.
7. Kiểm tra CSRF protection và dùng `with(csrf())` trong bài test khi mô hình cần token; không tắt bảo vệ chỉ để test qua.
8. Không nên. Với Boot starter và BOM, để cơ chế dependency management chọn phiên bản đồng bộ; chỉ thêm module riêng khi có use case cụ thể.

### Tài liệu chính thức để tra cứu đúng phiên bản

- [Spring Security – Getting Spring Security / Dependency Management](https://docs.spring.io/spring-security/reference/getting-spring-security.html)
- [Spring Security – Servlet Architecture / FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html)
- [Spring Security – Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security – MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
