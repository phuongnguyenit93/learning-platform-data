# Phân biệt AuthenticationManager dùng chung và AuthenticationManager của từng SecurityFilterChain

> **Phạm vi:** Spring Security **Servlet** (Spring MVC, Java 17+, Spring Boot 3.5.x / Spring Security 6.5.x). Bài này tập trung vào cách các HTTP request chọn `SecurityFilterChain` và cách **mỗi chain nhận `AuthenticationManager`**: dùng chung, độc lập hoặc kế thừa qua parent. Cần phân biệt rõ **quy tắc chọn filter chain** với **quy tắc chọn provider**, kiểm chứng khi cấu hình nhiều vùng URL, hiểu ranh giới của session/context và biết chọn kiểu phù hợp. Ví dụ chạy hoàn chỉnh sử dụng Spring Boot 3.5.7 và HTTP Basic để quan sát sự khác biệt; thông tin mật khẩu demo chỉ dùng cục bộ.

## 1. Hai lớp lựa chọn: chọn filter chain rồi mới xác thực

Trong ứng dụng Servlet, luồng xử lý thường như sau:

```text
Client gửi HTTP request (path, headers, cookies)
               │
               ▼
    FilterChainProxy của Spring Security
               │
               ├─ duyệt các SecurityFilterChain theo thứ tự
               ├─ chọn CHAIN ĐẦU TIÊN có RequestMatcher khớp
               └─ chạy tập filter của chain đã chọn
                               │
                               ▼
                   Authentication filter
                   (Basic, form login, bearer...)
                               │
                   tạo Authentication request
                               │
                               ▼
                  AuthenticationManager
                    (manager mà filter dùng)
                               │
                     ProviderManager?
                               │
                 ├─ AuthenticationProvider A
                 ├─ AuthenticationProvider B
                 └─ optional parent manager
                               │
                   Authentication thành công
                               │
                      SecurityContext
                               │
                         Authorization
                 (roles, scopes, rules, resource)
```

**Hai quyết định khác nhau:**

1. **`FilterChainProxy` chọn `SecurityFilterChain`** theo matcher của HTTP request và thứ tự `@Order`. Chỉ chain đầu tiên khớp sẽ xử lý request qua bộ filter của nó; không chạy tuần tự tất cả các chain.
2. **Authentication filter của chain sử dụng một `AuthenticationManager`**. Manager này có thể là đối tượng dùng chung với chain khác, manager riêng của chain, hoặc manager có parent để dùng một phần cơ chế chung.

Ví dụ hai URL `/api/orders` và `/portal/profile` có thể đi vào hai filter chain khác nhau nhưng vẫn gọi **cùng một manager** để kiểm tra username/password. Ngược lại, chúng có thể dùng **hai manager riêng**, kiểm tra hai kho tài khoản độc lập. Hai chain không tự tạo ra hai tập user tách biệt.

## 2. Khái niệm chính và các tên dễ nhầm

| Thành phần | Trách nhiệm | Có phải cùng một thứ? |
| --- | --- | --- |
| `SecurityFilterChain` | Danh sách security filters áp dụng cho request khớp một matcher | Không phải `AuthenticationManager` |
| `FilterChainProxy` | Chọn chain đầu tiên khớp request | Không duyệt `AuthenticationProvider` |
| `HttpSecurity` | Builder tạo cấu hình của một `SecurityFilterChain` | Không phải bản thân chain đã build |
| `AuthenticationManager` | API `authenticate(Authentication)`; tạo kết quả xác thực hoặc ném lỗi | Interface, không định nghĩa cách lưu session |
| `ProviderManager` | Implementation phổ biến dùng danh sách `AuthenticationProvider` | Chọn provider theo loại token và kết quả xử lý |
| `AuthenticationProvider` | Xác thực một kiểu credential/token bằng cơ chế cụ thể | Có thể dùng lại trong nhiều manager, cần xem trạng thái và chính sách |
| `SecurityContext` | Chứa `Authentication` hiện tại | Không phải danh sách user hay manager |
| `AuthorizationManager` | Quyết định quyền truy cập sau khi có authentication | Không thay thế việc xác thực |

Từ **global/shared `AuthenticationManager`** có hai cách dùng dễ gây lẫn:

- **Global do Spring Security cấu hình**: manager chung được dựng qua cấu hình toàn cục, liên quan `AuthenticationConfiguration` và các bean/provider được đăng ký theo cơ chế framework.
- **Shared do ứng dụng thiết kế**: một đối tượng `AuthenticationManager` mà ứng dụng tạo và **chủ động truyền cùng một reference** vào từ hai chain trở lên. Nó có thể là Spring bean hoặc một object cấu hình; “shared” ở đây nói về **object thực sự được dùng**, không tự động bảo đảm rằng mọi nơi trong application context đều sử dụng object đó.

Một `@Bean AuthenticationManager` không tự chứng minh mọi authentication filter đều dùng bean này. Khi có nhiều manager, **phải chỉ ra chain nào nhận manager nào** qua code hoặc kiểm thử. Một chain cũng có thể tạo manager **nội bộ từ `AuthenticationManagerBuilder`** và dùng global làm parent theo cấu hình; vì thế không nên giả định tất cả những gì không khai `.authenticationManager(...)` sẽ dùng chính xác cùng một instance.

## 3. Cấu hình nhiều SecurityFilterChain: matcher và thứ tự

Ví dụ rút gọn:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain portal(HttpSecurity http) throws Exception {
    http.securityMatcher("/portal/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Đây là **snippet Spring `@Configuration`**, chưa đủ project chạy vì chưa có nguồn user/manager và endpoint. Ở đây:

- `@Order(1)` được xét trước `@Order(2)`. Chain đầu khớp `/api/**`; chain thứ hai khớp `/portal/**`.
- `http.securityMatcher(...)` quyết định **chain có áp dụng cho request hay không**.
- `authorizeHttpRequests().requestMatchers(...)` chỉ quyết định **quyền trong chain đã chọn**. Nó không phải công cụ chọn chain.
- Nếu cấu hình một chain catch-all `anyRequest`/mặc định ở thứ tự cao hơn, nó có thể bắt cả `/api/**` và che khuất các chain sau.
- Nếu **không chain nào khớp** request, request đó **không được Spring Security bảo vệ** bởi các chain đã khai. Với nhiều chain giới hạn path, nên có catch-all cuối cùng với chính sách được cân nhắc.
- Mỗi `HttpSecurity` được cấu hình để tạo chain tương ứng. Số lượng chain **không áp đặt** số lượng manager hoặc provider.

### Đường đi request minh họa

| Request | Chain đầu tiên khớp | Authentication manager được dùng |
| --- | --- | --- |
| `GET /api/me` | API chain `@Order(1)` | Manager mà authentication filter của API chain đã được cấu hình dùng |
| `GET /portal/me` | Portal chain `@Order(2)` | Manager mà authentication filter của Portal chain đã được cấu hình dùng |
| `GET /health` | Không phải hai chain trên | Chỉ được bảo vệ nếu có catch-all hoặc chain khác phù hợp |

**Lưu ý với login form:** nếu chain chỉ khớp `/portal/**` nhưng form login mặc định dùng `/login` và `POST /login` nằm ngoài matcher, các endpoint login có thể không được filter của chain đó xử lý như mong đợi. Khi tách các flow form login, phải cấu hình đường dẫn login/callback/logout và matcher sao cho request thực sự đi vào đúng chain.

## 4. Kiểu A: dùng chung một AuthenticationManager

Với kiểu dùng chung, nhiều chain tham chiếu cùng một `AuthenticationManager` (thường là `ProviderManager` có các provider/user store chung). Hai chain vẫn có thể khác nhau ở filter, entry point, session policy, CSRF và authorization.

```text
                  ┌── API SecurityFilterChain ── BasicAuthenticationFilter ─┐
HTTP request ─────┤                                                        ├─ sharedManager
                  └── Portal SecurityFilterChain ── BasicAuthenticationFilter┘      │
                                                                                   ├─ DaoAuthenticationProvider
                                                                                   └─ nguồn users chung
```

Có thể khai một bean manager chung và truyền **cùng bean** vào hai chain:

```java
@Bean
AuthenticationManager sharedManager(UserDetailsService users,
                                    PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(encoder);
    return new ProviderManager(provider);
}

@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http,
                        AuthenticationManager sharedManager) throws Exception {
    http.securityMatcher("/api/**")
        .authenticationManager(sharedManager)
        .httpBasic(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("API"));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain portal(HttpSecurity http,
                           AuthenticationManager sharedManager) throws Exception {
    http.securityMatcher("/portal/**")
        .authenticationManager(sharedManager)
        .httpBasic(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("PORTAL"));
    return http.build();
}
```

Đây là **ví dụ cấu hình cần `UserDetailsService`, `PasswordEncoder`, import và controller**, không phải class chạy độc lập. Để tránh bean type mơ hồ nếu application có nhiều `AuthenticationManager`, nên dùng tên bean/`@Qualifier` rõ ràng.

**Hệ quả quan trọng:** với một nguồn user chứa `api-user` có `ROLE_API` và `portal-user` có `ROLE_PORTAL`, manager chung có thể **xác thực cả hai tài khoản ở cả hai chain**. Sau xác thực, authorization rule của từng chain quyết định user có được vào hay không. Thường gặp:

- `api-user` + mật khẩu đúng gọi `/api/me` → **200**.
- `api-user` + mật khẩu đúng gọi `/portal/me` → xác thực **thành công**, nhưng thiếu `ROLE_PORTAL` nên **403**.
- User không tồn tại hoặc mật khẩu sai → authentication thất bại; với HTTP Basic thường là **401**.

**403 ở ví dụ thứ hai không có nghĩa manager không biết tài khoản**. Ngược lại, nó cho thấy manager chung **đã công nhận credential**, còn policy của chain chặn quyền. Đừng dùng “đúng tài khoản ở API thì portal trả 403” làm bằng chứng cho rằng credential không được portal chấp nhận về mặt authentication.

### Khi nào manager chung phù hợp?

- Cùng tập danh tính và cùng chính sách kiểm tra credential, ví dụ nhiều HTTP path cùng xác thực qua một kho user.
- Chỉ khác **authorization** theo vai trò, hoặc khác cách đặt endpoint/filter nhưng cùng trust domain.
- Muốn reuse một tập provider được quản trị thống nhất, tránh cấu hình password encoder/user cache sai lệch giữa nhiều chain.
- Cần thống nhất quy trình khóa tài khoản, rotation mật khẩu và auditing ở một identity store.

**Rủi ro:** mọi chain dùng manager chung đều có thể gửi credential thuộc tập chung đến cơ chế xác thực đó. Nếu thực sự phải cách ly realm, tenant hay loại credential, phân quyền bằng role đơn thuần có thể chưa đáp ứng yêu cầu tách biệt xác thực. Đặc biệt cẩn thận với shared manager có nhiều provider cùng `supports(...)` một token type: một provider thất bại không nhất thiết chặn provider sau, tùy loại lỗi/quy tắc của `ProviderManager`.

## 5. Kiểu B: manager riêng cho từng SecurityFilterChain

Với kiểu này, mỗi chain gọi **một manager riêng**. Có thể dùng hai `ProviderManager` độc lập với provider và user store khác nhau, hoặc manager có cấu trúc khác khi API dùng bearer token còn portal dùng form login.

```text
HTTP GET /api/me
   → API chain
   → BasicAuthenticationFilter
   → apiManager
   → API provider / API users

HTTP GET /portal/me
   → Portal chain
   → BasicAuthenticationFilter
   → portalManager
   → Portal provider / Portal users
```

Cách gắn manager riêng là `http.authenticationManager(managerForThisChain)`. API chính thức cho phép ghi đè manager chung bằng một local manager ở `HttpSecurity`.

### Thay đổi gì ở hành vi?

Nếu `apiManager` chỉ có `api-user` và `portalManager` chỉ có `portal-user`:

| Credential gửi tới endpoint | Kết quả với manager riêng | Giải thích |
| --- | --- | --- |
| `api-user` đúng mật khẩu → `/api/me` | **200** | API manager biết tài khoản |
| `portal-user` đúng mật khẩu → `/portal/me` | **200** | Portal manager biết tài khoản |
| `api-user` đúng mật khẩu → `/portal/me` | **401** với HTTP Basic | Portal manager không xác thực tài khoản API |
| `portal-user` đúng mật khẩu → `/api/me` | **401** với HTTP Basic | API manager không xác thực tài khoản Portal |
| Không có Authorization header → một trong hai endpoint | **401** với HTTP Basic | Filter yêu cầu credential |
| Manager trả authenticated user nhưng thiếu role chain yêu cầu | **403** | Authentication thành công, authorization từ chối |

Bảng giả định **HTTP Basic + không dùng session đăng nhập trước đó + không có parent/fallback khác**. Cùng một user string có thể tồn tại ở cả hai kho nhưng có password và role khác; kết quả phải dựa vào cấu hình thực tế.

**Quan trọng:** manager riêng **không tự tạo sandbox bảo mật tuyệt đối giữa các filter chain**. Nếu các chain dùng chung `SecurityContextRepository`/HTTP session, một request có thể nhận một `Authentication` đã lưu từ session mà **không gọi lại manager như khi nhập credential mới**. Điều này đặc biệt quan trọng khi một chain dùng form login/session và chain khác cũng chấp nhận session cookie. Cần thiết kế context/session boundary, stateless policy và authorization phù hợp; test cả trường hợp có cookie sau đăng nhập ở chain khác.

### Khi nào cần manager riêng?

- Hai vùng ứng dụng dùng **hai nguồn danh tính độc lập** và yêu cầu một account của realm A không được realm B chấp nhận.
- Kênh machine-to-machine khác browser, với credential/provider/chính sách kiểm tra khác nhau.
- API dùng JWT Resource Server còn portal dùng DB/form login; hai hệ thống có trust anchor và lifecycle riêng.
- Cần tách audit, failure policy hoặc quản trị nguồn account theo từng kênh, sau khi xác minh cách context/session được chia sẻ.

Đừng tạo manager riêng chỉ vì có nhiều URL. Nếu mọi chain xác thực cùng tập user và chỉ cần phân quyền khác nhau, một manager chung thường đơn giản hơn.

## 6. Ví dụ hoàn chỉnh: hai chain, hai manager thật sự độc lập

Dựng ứng dụng Spring Boot tối thiểu với hai endpoint:

- `GET /api/me` nhận **api-user / api-pass** qua HTTP Basic.
- `GET /portal/me` nhận **portal-user / portal-pass** qua HTTP Basic.
- Mỗi chain có `ProviderManager` riêng, `DaoAuthenticationProvider` riêng và `InMemoryUserDetailsManager` riêng.
- Có catch-all thứ ba **từ chối mọi path ngoài phạm vi demo**, để không vô tình bỏ trống vùng URL.
- Chỉ dùng GET, để mặc định CSRF protection của Spring Security; HTTP Basic trong ví dụ có phiên **STATELESS** để kiểm tra rõ ranh giới manager.
- Mật khẩu demo được mã hóa bằng BCrypt khi khởi động; không dùng dữ liệu cố định này trong môi trường thật.

### 6.1. Cấu trúc thư mục

```text
manager-scope-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/managers/ManagerScopeApplication.java
    └── test/java/dev/example/managers/ManagerScopeApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'manager-scope-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
```

Spring Boot quản lý phiên bản các dependency Spring Security tương thích, vì vậy không khai phiên bản Spring Security riêng cho starter. Khi triển khai thực tế nên dùng bản vá được dự án phê duyệt.

### 6.2. File Java chạy ứng dụng

Tạo `src/main/java/dev/example/managers/ManagerScopeApplication.java`:

```java
package dev.example.managers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ManagerScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManagerScopeApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    // Chỉ nhận các request bắt đầu /api/
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http, PasswordEncoder encoder) throws Exception {

        AuthenticationManager apiManager = newManager(
                "api-user", "api-pass", "API", encoder);

        http.securityMatcher("/api/**")
                .authenticationManager(apiManager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("API"))
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }

    // Chỉ nhận các request bắt đầu /portal/
    @Bean
    @Order(2)
    SecurityFilterChain portalChain(
            HttpSecurity http, PasswordEncoder encoder) throws Exception {

        AuthenticationManager portalManager = newManager(
                "portal-user", "portal-pass", "PORTAL", encoder);

        http.securityMatcher("/portal/**")
                .authenticationManager(portalManager)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("PORTAL"))
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }

    // Từ chối các path khác, tránh khoảng trống bảo vệ.
    @Bean
    @Order(3)
    SecurityFilterChain denyOtherPaths(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll());
        return http.build();
    }

    private AuthenticationManager newManager(
            String username, String rawPassword,
            String role, PasswordEncoder encoder) {

        UserDetails account = User.withUsername(username)
                .password(encoder.encode(rawPassword))
                .roles(role)
                .build();

        UserDetailsService users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        // Mỗi lần gọi trả về một ProviderManager mới,
        // không có parent và không dùng chung user store.
        return new ProviderManager(dao);
    }

    @RestController
    static class WhoAmIController {
        @GetMapping({"/api/me", "/portal/me"})
        String me(Authentication authentication) {
            return authentication.getName();
        }
    }
}
```

**Điểm cần quan sát trong code:**

1. `apiChain` và `portalChain` đều nhận builder `HttpSecurity` nhưng gọi `newManager(...)` **riêng hai lần**. Mỗi lần tạo một `ProviderManager` với chính account của realm đó; không có provider nào được chia sẻ giữa hai manager.
2. `http.authenticationManager(apiManager)` liên kết API chain với đúng manager; `http.authenticationManager(portalManager)` làm tương tự cho Portal chain. Đọc cấu hình này chắc chắn hơn việc đoán từ tên `@Bean`.
3. `securityMatcher("/api/**")` và `securityMatcher("/portal/**")` chọn **chain**; `hasRole("API")` và `hasRole("PORTAL")` quyết định **authorization** sau xác thực.
4. `newManager` cố ý là **private method**, không phải Spring bean. Điều này làm rõ tính local, tránh trường hợp có nhiều `AuthenticationManager` bean gây ambiguity khi inject theo type.
5. `DaoAuthenticationProvider` xử lý `UsernamePasswordAuthenticationToken` do HTTP Basic filter tạo; sử dụng `PasswordEncoder.matches(...)` để so password với BCrypt hash trong `UserDetails`.
6. `STATELESS` giúp mỗi HTTP Basic request được xác thực qua credential hiện tại, không dựa vào một login session được lưu trước đó. Nó không đồng nghĩa ứng dụng tự động an toàn với CSRF ở mọi loại client; phải xét cookie hoặc Authorization header có được browser tự gửi hay không.
7. `denyOtherPaths` là chain catch-all cuối, có matcher mặc định cho request còn lại, áp dụng deny-all. Nó không tạo thêm account và không cung cấp đường đăng nhập thay thế.

### 6.3. Chạy và quan sát HTTP

Tại thư mục chứa `build.gradle`, với Gradle tương thích Spring Boot 3.5 và JDK 17+, chạy:

```bash
gradle bootRun
```

Nếu đã có Gradle Wrapper, dùng `./gradlew bootRun` trên macOS/Linux hoặc `gradlew.bat bootRun` trên Windows. Trong một terminal khác, trên Windows dùng `curl.exe` (tránh PowerShell alias `curl`):

```bash
curl.exe -i -u api-user:api-pass http://localhost:8080/api/me
curl.exe -i -u portal-user:portal-pass http://localhost:8080/portal/me
curl.exe -i -u api-user:api-pass http://localhost:8080/portal/me
curl.exe -i -u portal-user:portal-pass http://localhost:8080/api/me
curl.exe -i http://localhost:8080/api/me
```

Trên macOS/Linux thay `curl.exe` bằng `curl`. Không đưa password thật lên lịch sử shell; đây là credential demo.

Kết quả HTTP cốt lõi, lược bỏ các header biến thiên:

| Request | HTTP status | Body chính khi thành công |
| --- | --- | --- |
| API credential → `/api/me` | **200** | `api-user` |
| Portal credential → `/portal/me` | **200** | `portal-user` |
| API credential → `/portal/me` | **401** | Không trả thông tin người dùng |
| Portal credential → `/api/me` | **401** | Không trả thông tin người dùng |
| Không credential → `/api/me` | **401** | HTTP Basic challenge |

Trong bảng này, **401** của hai dòng “gửi nhầm realm” xuất hiện vì **manager của chain được chọn không biết tài khoản đó**, dù credential đúng với manager của chain khác. Đây là dấu hiệu hành vi xác thực khác bản dùng shared manager.

### 6.4. Test tự động cho ranh giới manager

Tạo `src/test/java/dev/example/managers/ManagerScopeApplicationTests.java`:

```java
package dev.example.managers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ManagerScopeApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void eachPathUsesOnlyItsOwnManager() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("api-user", "api-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-user"));

        mvc.perform(get("/portal/me")
                        .with(httpBasic("portal-user", "portal-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("portal-user"));

        mvc.perform(get("/portal/me")
                        .with(httpBasic("api-user", "api-pass")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me")
                        .with(httpBasic("portal-user", "portal-pass")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
gradle test
```

Test sử dụng request thật qua `MockMvc`, đi qua **Spring Security filter chain** được cấu hình. Nó có giá trị hơn kiểm thử chỉ dựng `Authentication` giả với `@WithMockUser`, bởi `@WithMockUser` có thể bỏ qua password provider và không chứng minh manager thực tế của chain là đúng.

Nếu cần xác nhận ứng dụng có bảo vệ các path khác, có thể thêm test gọi `GET /unknown` và khẳng định request **không trả thành công** vì catch-all `denyAll` (status cụ thể chịu ảnh hưởng entry point và cấu hình xử lý exception của chain fallback).

## 7. Chuyển ví dụ sang manager chung: thay đổi có thể dự đoán

Trong ứng dụng trên, thử thay hai lời gọi `newManager(...)` bằng **một bean shared** chứa **cả hai user**. Cấu hình đại diện:

```java
@Bean
AuthenticationManager sharedManager(PasswordEncoder encoder) {
    UserDetails apiUser = User.withUsername("api-user")
            .password(encoder.encode("api-pass"))
            .roles("API")
            .build();

    UserDetails portalUser = User.withUsername("portal-user")
            .password(encoder.encode("portal-pass"))
            .roles("PORTAL")
            .build();

    UserDetailsService users =
            new InMemoryUserDetailsManager(apiUser, portalUser);

    DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
    dao.setPasswordEncoder(encoder);
    return new ProviderManager(dao);
}
```

Đây là **snippet đặt trong class `@Configuration` hiện có**; để hoàn thiện biến thể shared, thay đổi **chữ ký hai bean filter chain để inject chính bean `sharedManager`**, rồi dùng cùng dòng `.authenticationManager(sharedManager)` ở cả hai chain. Bỏ các lời gọi `newManager(...)` cũ. Ví dụ đoạn cần nối trong một bean:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http,
                             AuthenticationManager sharedManager)
        throws Exception {
    http.securityMatcher("/api/**")
            .authenticationManager(sharedManager)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().hasRole("API"))
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    return http.build();
}
```

Áp dụng cùng ý tưởng cho Portal chain với `hasRole("PORTAL")`. **Đây là bản biến đổi cấu hình, không dán đè vào ứng dụng đang có hai bean `apiChain` trùng tên.** Khi có một bean manager và yêu cầu thực sự dùng chung, đặt tên rõ ràng/`@Qualifier` trong code lớn để không phụ thuộc vào phỏng đoán injection.

Sau chuyển đổi:

- `api-user` vào `/api/me` vẫn **200**.
- `portal-user` vào `/portal/me` vẫn **200**.
- `api-user` vào `/portal/me`: manager chung **xác thực thành công** nhưng thiếu `ROLE_PORTAL`, thường **403**.
- `portal-user` vào `/api/me`: manager chung xác thực thành công nhưng thiếu `ROLE_API`, thường **403**.

Điều làm 401 chuyển thành 403 là **trách nhiệm của manager đổi**, không phải thay URL matcher hoặc bắt buộc đổi `hasRole`. Hai chain vẫn chạy riêng và vẫn giữ authorization rule tương ứng.

**Không nên dựa vào status 401/403 một cách máy móc** trong mọi ứng dụng: form login có thể redirect 302 khi chưa xác thực; custom entry point/access denied handler có thể thay status. Hãy kết luận dựa trên chính filter, manager, provider và rule đã cấu hình.

## 8. Mô hình C: manager riêng có shared parent

Dùng chung và tách biệt không chỉ có hai cực. `ProviderManager` hỗ trợ **parent `AuthenticationManager`**, cho phép nhiều child manager có provider cục bộ nhưng cùng sử dụng những phương thức xác thực được chia sẻ.

```text
                  apiChain                            portalChain
                      │                                    │
                      ▼                                    ▼
              ProviderManager A                    ProviderManager B
              [API-only provider]                  [Portal-only provider]
                      │ parent                            │ parent
                      └──────────────┬─────────────────────┘
                                     ▼
                         Shared parent manager
                           [Common provider]
```

**Ngữ nghĩa cần hiểu:** child thử các provider mà nó quản lý. Nếu chưa được xác thực và không gặp một lỗi buộc dừng, nó có thể nhờ parent. Như vậy parent là **một đường xác thực bổ sung thật sự**, không chỉ là “mượn code” hoặc metadata.

Đoạn minh họa xây manager cha/con:

```java
AuthenticationManager common = new ProviderManager(commonProvider);

ProviderManager apiManager =
        new ProviderManager(List.of(apiProvider), common);

ProviderManager portalManager =
        new ProviderManager(List.of(portalProvider), common);
```

Đây là **pseudoconfiguration Java**, giả sử `commonProvider`, `apiProvider` và `portalProvider` đã được khai báo là `AuthenticationProvider` phù hợp; không phải chương trình có thể chạy riêng. Cấu trúc này hữu ích khi có một cơ chế xác thực chung được cho phép ở cả hai kênh, ví dụ loại service credential đã được định nghĩa rõ ràng.

**Rủi ro:** nếu child manager từ chối credential thuộc realm riêng nhưng parent lại chấp nhận nó, bạn có thể phá vỡ chính sách cách ly. `BadCredentialsException` từ một provider không phải lúc nào cũng làm `ProviderManager` dừng ngay; cần hiểu thứ tự/fallback/loại exception. Lỗi trạng thái account như `LockedException` hoặc `DisabledException` thường phải dừng luồng. Thiết kế parent phải xác định rõ namespace, trusted issuers, token type và rule chặn fallback yếu.

Không đặt parent chỉ để “mọi tài khoản đều đăng nhập được ở đâu đó”. Nếu yêu cầu là cách ly chặt hai identity realm, hai `ProviderManager` không có shared parent thường dễ kiểm chứng hơn.

## 9. Phân biệt shared manager, local manager và local provider registration

### 9.1. Explicit shared object

```java
http.authenticationManager(sharedManager);
```

Chain sẽ dùng manager object được chỉ định ở vị trí cấu hình đó. Nếu hai chain được truyền đúng **một reference**, đó là shared manager theo nghĩa vận hành.

### 9.2. Explicit local object

```java
http.authenticationManager(new ProviderManager(apiProvider));
```

Chain dùng manager riêng. Cần đảm bảo `apiProvider` được khởi tạo với credential store, encoder và exception policy đúng. Ví dụ này là snippet cần biến `apiProvider`; không phải code độc lập.

### 9.3. Thêm provider qua HttpSecurity

```java
http.authenticationProvider(apiProvider);
```

Đây là **đăng ký provider vào cấu hình của HttpSecurity**, không tương đương trực tiếp với “tất cả chain dùng cùng một manager object”. Tùy cách framework dựng `AuthenticationManagerBuilder` và parent, một manager cục bộ có thể gồm provider riêng cộng với khả năng gọi global manager. Phải xem configuration thực tế của từng chain; đừng tự tuyên bố rằng `authenticationProvider(...)` bảo đảm cách ly toàn bộ.

### 9.4. Không gắn manager rõ ràng

```java
http.securityMatcher("/api/**")
    .httpBasic(Customizer.withDefaults());
```

Khi không gọi `authenticationManager(...)`, Spring Security sẽ quyết định/bổ sung manager qua cơ chế cấu hình của nó. Có thể sử dụng cấu hình toàn cục, bean provider/service hoặc manager được xây cho `HttpSecurity`. **Không suy ra chỉ từ số chain rằng có hay không manager chung.** Nếu cần hợp đồng cách ly có thể test và kiểm toán, ưu tiên gắn manager tường minh.

### 9.5. Publish AuthenticationManager bean cho service/controller

Một `@Bean AuthenticationManager` có thể được inject vào service dùng xác thực bằng code; việc inject manager ở service không có nghĩa các filter từ mọi chain gọi đúng bean đó. Vì vậy **manager được publish**, **manager mà authentication filter đang dùng** và **manager có parent** là ba thông tin phải xác minh riêng.

Khi có nhiều bean cùng kiểu, dùng `@Qualifier` hoặc tên bean phù hợp; tránh field injection theo type mơ hồ dẫn đến `NoUniqueBeanDefinitionException` hoặc việc Spring chọn bean không đúng ý định.

## 10. SecurityContext và session: vì sao manager riêng chưa đủ

AuthenticationManager thường được gọi **khi có yêu cầu xác thực credential**. Sau khi login thành công, Spring Security có thể lưu `Authentication` trong `SecurityContext` và qua `SecurityContextRepository`/HTTP session. Request tiếp theo mang session cookie có thể được nhận diện từ context đã lưu **mà không cần chạy lại toàn bộ provider**.

Giả sử:

1. Browser đăng nhập form vào `/portal/**` và lưu session cookie.
2. Browser gọi `/api/**` có gửi cùng cookie, nhưng không gửi API Basic header.
3. Tùy cấu hình session/context repository của chain API và rule authorization, danh tính đã lưu từ portal có thể còn được nhìn thấy; không thể kết luận “API manager riêng thì API sẽ luôn trả 401” nếu chưa test session.

Muốn cách ly thực tế cần thiết kế **cả**:

- URL matchers, filter chain order và authentication mechanisms.
- Manager/provider/credential store/trust realm.
- `SecurityContextRepository`, session policy, cookie scope, login/logout, remember-me.
- CORS/CSRF cho browser và việc tự gửi cookie/Authorization.
- Authorization rules, đặc biệt role, scope, issuer, tenant và quyền theo tài nguyên.

Trong demo, `SessionCreationPolicy.STATELESS` kết hợp HTTP Basic giúp tách rõ trường hợp mỗi request có credential riêng. Trong hệ thống có form login, cần test thêm đăng nhập một chain rồi dùng **chính cookie đó** truy cập chain khác. Không sử dụng `SecurityContextHolder` global/static để giải quyết việc chia sẻ phiên.

## 11. Cơ chế khác nhau giữa API và web app

Một ứng dụng thực tế có thể dùng:

| Vùng | Chain | Authentication mechanism | Manager/provider thông dụng |
| --- | --- | --- | --- |
| `/api/**` | API chain | `oauth2ResourceServer().jwt(...)` | Manager/provider kiểm tra JWT theo issuer/JWKS |
| `/portal/**` | Portal chain | `formLogin(...)` | Manager/provider username/password từ DB |
| `/internal/**` | Internal chain | HTTP Basic/mTLS/custom theo yêu cầu | Manager/provider riêng cho service identities |
| Các path khác | Catch-all | Deny-all hoặc chính sách đã kiểm soát | Không nhất thiết cần manager đăng nhập |

Đây là **bảng kiến trúc minh họa**. Khi dùng OAuth2 Resource Server, các authentication filter/provider có thể được dựng và kết nối nội bộ theo DSL, và kiến trúc đa issuer có thể dùng `AuthenticationManagerResolver<HttpServletRequest>` để chọn manager theo request. **Resolver** là kỹ thuật chọn manager **bên trong một cơ chế xác thực**; nó không thay thế quy tắc `FilterChainProxy` chọn chain theo matcher.

Không có quy tắc “mọi API đều phải có một manager mới” hoặc “JWT và form login phải nằm chung manager”. Thiết kế theo trust boundary, loại credential, chiến lược session và yêu cầu quản trị.

## 12. Cách nhận diện manager được dùng khi debug

Thứ tự điều tra hiệu quả:

1. **Xác minh path và method** của request, kể cả context path/proxy rewrite.
2. **Liệt kê các `SecurityFilterChain` theo `@Order`**, cùng `securityMatcher` và catch-all. Xác định chain đầu tiên khớp.
3. **Xác định filter xác thực** có trong chain: Basic, form login, bearer token, custom filter… Nếu chỉ có authorization filter mà không có cơ chế nhận credential, yêu cầu chưa login không tự trở thành authenticated.
4. **Tìm nơi cấu hình manager** cho chain: `http.authenticationManager(...)`, provider trong `HttpSecurity`, global authentication config hoặc resolver. Đừng xem duy nhất tên bean.
5. **Với `ProviderManager`, kiểm tra danh sách provider, thứ tự, `supports(tokenClass)`, null/exception và parent**.
6. **Kiểm tra state**: request đang gửi credential mới hay đã có `SecurityContext` khôi phục từ session? Có remember-me hay token filter khác không?
7. **Đọc status/entry point**: 401 Basic challenge, 302 form-login redirect, 403 access denied là những kết quả theo cơ chế đã cấu hình; không chẩn đoán chỉ từ status.
8. **Kiểm tra trust domain và authorization**: user được manager chấp nhận nhưng thiếu role sẽ khác user không được manager xác thực.
9. **Kiểm tra audit**: log loại token, chain/matcher, outcome và mã lỗi; không ghi password, Authorization header, raw token hoặc password hash.

Có thể bật DEBUG của Spring Security trong môi trường phát triển có kiểm soát để xem danh sách security filters và việc request được bảo vệ bởi chain nào. Không để debug log nhạy cảm hoạt động lâu ở production. Nếu code dùng nhiều manager, nên viết test bằng `MockMvc` hoặc integration test thật cho từng cặp (path × credential × session state), vì chỉ nhìn constructor của `ProviderManager` không xác nhận được đường đi của request.

## 13. Ma trận kiểm thử cần có khi nhiều chain

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| `/api/**` match API chain | Các filter/manager API thực sự xử lý request |
| `/portal/**` match Portal chain | Không bị catch-all đứng trước chiếm request |
| Path nằm ngoài các matcher | Catch-all bảo vệ đúng; không vô tình mở endpoint |
| Credential đúng realm API vào API | 200 khi đủ quyền |
| Credential đúng realm Portal vào Portal | 200 khi đủ quyền |
| API credential vào Portal với **manager riêng** | Xác thực thất bại theo chính sách, thường 401 với Basic |
| API credential vào Portal với **manager chung** | Xác thực có thể thành công, nhưng role check thường trả 403 |
| Password sai, tài khoản bị khóa | Không chấp nhận qua fallback/provider khác |
| Request không credential | Entry point/challenge hoặc redirect đúng cơ chế |
| Có session từ Portal rồi gọi API | Context có bị tái sử dụng ngoài mong muốn không |
| Logout, expire, remember-me | Không còn quyền sau khi trạng thái thay đổi theo chính sách |
| Chain dùng JWT, chain dùng Basic/form | Không nhầm token type, issuer, manager hoặc session |
| Provider chung trong parent | Kiểm tra đường fallback và account state |
| Một bean manager được inject vào service | Không tự giả định filter cũng dùng bean đó |

Nên kiểm thử **positive và negative cases**, vì hệ thống có thể hoạt động bình thường với user đúng nhưng vẫn có lỗi nghiêm trọng khi credential thuộc một realm khác được chấp nhận nhầm.

## 14. Lỗi thường gặp và cách sửa

1. **“Hai `SecurityFilterChain` = hai manager độc lập.”** Sai. Số lượng chain và manager không có quan hệ 1-1 bắt buộc. Kiểm tra object thực tế được gắn vào từng chain.
2. **“Có một `@Bean AuthenticationManager` thì tất cả chain dùng nó.”** Không thể kết luận. Bean có thể dành cho service; filter chain có thể dùng manager khác hoặc được cấu hình cục bộ.
3. **“`requestMatchers` quyết định chain.”** `securityMatcher` của mỗi chain mới là bộ lọc ở mức chain. `requestMatchers` bên trong `authorizeHttpRequests` là rule nội bộ sau khi chain được chọn.
4. **Đặt catch-all `@Order(1)` trước API chain.** Nó che các chain sau. Đặt matcher cụ thể ở độ ưu tiên cao hơn và catch-all ở cuối.
5. **Không có catch-all mà nghĩ mọi path đã được bảo vệ.** Request không khớp chain nào nằm ngoài sự bảo vệ của Spring Security filter chains.
6. **Để form login ở `/login` nhưng chỉ match `/portal/**`.** Login endpoint có thể không đi vào đúng chain. Định vị endpoint login/logout/callback nhất quán với matcher.
7. **Nhầm 403 với việc manager từ chối credential.** 403 có thể là authentication thành công nhưng authorization thiếu quyền; so sánh với 401 của Basic khi xác thực thất bại.
8. **Manager riêng nhưng dùng lại session/context giữa các chain mà không kiểm thử.** Tách user store chưa đủ tách session. Đánh giá policy ở cả request đã có cookie.
9. **Khai nhiều bean `AuthenticationManager` rồi inject không `@Qualifier`.** Có thể lỗi ambiguity hoặc dùng sai bean trong refactor.
10. **Coi `http.authenticationProvider(provider)` luôn tách hoàn toàn khỏi global parent.** Cần hiểu cách builder dựng manager và parent, không suy đoán isolation.
11. **Để parent chung xác thực credential bị từ chối ở child sai ranh giới.** Đặt namespace, token type, account state và fallback policy rõ ràng.
12. **Tắt CSRF và session tùy tiện để “API chạy”.** Với browser tự gửi cookie/Basic, CSRF vẫn có thể cần bảo vệ. Cấu hình theo cơ chế credential và đặc điểm client.
13. **Chỉ test bằng `@WithMockUser`.** Test giả lập security context không đi qua toàn bộ authentication filter/manager; thêm test thực sự gửi credential vào endpoint.
14. **Tự gọi một manager bằng code rồi tưởng toàn bộ HTTP chain dùng manager đó.** Manager được inject vào controller có thể khác manager mà filter Basic/form/bearer sử dụng.
15. **Đặt mọi loại credential vào một provider bất kể token type.** Mất ranh giới và dễ gây fallback không mong muốn. Dùng provider/manager/resolver phù hợp.

## 15. Bài tập và tiêu chí hoàn thành

**Bài 1 — Vẽ hai tầng chọn:** mô tả lần lượt matcher chọn chain và manager chọn provider cho request `GET /api/me` mang Basic credentials. Giải thích vì sao sửa `@Order` không đồng nghĩa sửa thứ tự `AuthenticationProvider`.

**Bài 2 — Quan sát 401 và 403:** chạy demo manager riêng và chụp HTTP status cho 5 request ở mục 6. Chuyển sang manager chung theo mục 7 và đối chiếu hai request sai realm; giải thích bằng authentication/authorization chứ không chỉ chép status.

**Bài 3 — Login form:** thiết kế thêm chain `/portal/**` dùng form login và session. Xác định đường dẫn GET/POST login, logout, CSRF token, cookie và test chéo session với API chain. Không chỉ sửa `.httpBasic(...)` thành `.formLogin(...)` rồi bỏ qua endpoint path.

**Bài 4 — Parent:** có một provider OTP/machine identity được chia sẻ có chủ đích giữa các chain, vẽ cấu trúc child parent phù hợp; chỉ rõ credential nào tuyệt đối không được fallback sang parent.

**Bài 5 — Debug:** giả sử `/api/me` trả 302 tới login form trong khi dự kiến 401 Basic. Viết chuỗi kiểm tra: chain được chọn, thứ tự `@Order`, filter được bật, entry point, manager và session trước khi sửa code.

**Bài 6 — Kiểm thử thực tế:** viết thêm integration test cho request `/outside`, cho wrong password, cho account disabled và cho tình huống đã có session từ một chain khác. Giải thích tại sao kiểm thử chỉ dùng `@WithMockUser` không chứng minh ranh giới manager.

**Hoàn thành bài** khi tự trả lời được: “Request nào đi vào chain nào?”, “Filter nào gọi manager nào?”, “Manager đó chứa provider gì, có parent không?”, “Khi credential đã đúng nhưng thiếu quyền thì sao?”, và “Session có thể khiến request không gọi lại manager hay không?”. Phân biệt được tính độc lập của **authentication manager** với tính độc lập của **security context** là yêu cầu quan trọng nhất khi thiết kế nhiều chain.

## 16. Tài liệu đối chiếu chính thức

- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `securityMatcher`, `@Order`, chain đầu tiên khớp và nguy cơ không có chain bảo vệ.
- [Spring Security 6.5 — Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html): manager toàn cục, `@Bean AuthenticationManager`, `http.authenticationManager(...)` gắn local manager.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, parent và `SecurityContext`.
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `FilterChainProxy`, security filters, việc cấu hình/đọc filter chain.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): username/password, `UserDetailsService` và `PasswordEncoder`.
- [Spring Boot 3.5.7 — Release](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now/): phiên bản Spring Boot cụ thể dùng trong ví dụ Gradle.

Các tài liệu tham khảo tập trung vào Spring Security 6.5/Boot 3.5 vì đó là tuyến API của ví dụ. Nếu dự án sử dụng Spring Security 7, WebFlux hay custom authentication filter, cần đối chiếu API/configuration của đúng phiên bản và stack trước khi áp dụng máy móc.