# SecurityContextHolderFilter và cơ chế explicit save theo phiên bản

> **Phạm vi:** Spring Security trên **Servlet stack** (Spring MVC), tập trung vào `SecurityContextHolderFilter`, `SecurityContextPersistenceFilter`, `SecurityContextHolder` và `SecurityContextRepository` khi xác thực người dùng cần tồn tại **qua nhiều HTTP request**. Trình bày rõ sự chuyển đổi từ Spring Security 5 sang 6, những gì filter có và không tự làm, cách lưu context trong login tùy chỉnh, xử lý session/logout, repository mặc định và các lỗi triển khai thường gặp. Ví dụ tích hợp đầy đủ dùng **Java 17, Spring Boot 3.5.7 / Spring Security 6.5.x**, kiểm thử bằng MockMvc với CSRF vẫn được bật.

## 1. Tình huống mở đầu: đăng nhập thành công nhưng request sau lại 401

Một lập trình viên tự xây endpoint `POST /manual/login`:

```java
Authentication result = authenticationManager.authenticate(token);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);
```

Đoạn trên là **snippet**, giả định `authenticationManager` và `token` đã có. Nó có thể khiến người dùng hiện diện trong `SecurityContextHolder` **ngay trong request đang xử lý**. Tuy nhiên, trên Spring Security 6 theo mặc định, điều đó **chưa đảm bảo** request kế tiếp sẽ được nhận diện đã đăng nhập.

Lý do: `SecurityContextHolderFilter` **đọc** context từ `SecurityContextRepository` vào holder nhưng **không tự ghi** context mới từ holder trở lại repository. Muốn một lần xác thực do ứng dụng tự thực hiện được duy trì qua HTTP request, cần gọi rõ ràng:

```java
securityContextRepository.saveContext(context, request, response);
```

Đây là API của `SecurityContextRepository`; `request` và `response` là `HttpServletRequest`/`HttpServletResponse` của request hiện tại, **trước khi response bị commit**. Thời điểm và loại repository quyết định liệu context có tồn tại qua request tiếp theo hay không.

**Điểm dễ nhầm nhất:** đây là quy tắc đối với **code ứng dụng tự tạo/đặt authentication**. Nếu sử dụng **form login, OAuth2 login hoặc authentication filter chuẩn** được Spring Security cấu hình đúng, cơ chế authentication của framework thông thường **đã thực hiện các bước lưu cần thiết** cho flow đó. Không phải lập trình viên phải tìm chỗ gọi `saveContext` thủ công sau mọi lần đăng nhập bằng Spring Security.

## 2. Bốn thành phần: Holder, Context, Repository và Filter

| Thành phần | Công việc thực tế | Không đảm nhận |
| --- | --- | --- |
| `SecurityContextHolder` | Đặt/đọc `SecurityContext` hiện tại, mặc định dựa trên `ThreadLocal` | Không tự lưu người dùng vào HTTP session |
| `SecurityContext` | Chứa `Authentication` của ngữ cảnh bảo mật hiện tại | Không phải password store, cũng không phải session ID |
| `SecurityContextRepository` | Đọc/ghi `SecurityContext` ở một nguồn persistence được chọn | Không tự xác minh password |
| **`SecurityContextHolderFilter`** | Nạp (có thể deferred) context cho request và dọn holder cuối chuỗi | **Không tự gọi save khi holder bị thay đổi** |
| `SecurityContextPersistenceFilter` | Kiểu legacy: nạp và tự lưu context khi kết thúc/request sắp commit | Không phải filter nên chạy đồng thời với HolderFilter |
| `AuthenticationManager` | Xác minh credential và trả `Authentication` đã xác thực | Không quyết định context lưu vào đâu nếu không có cơ chế tích hợp |

### 2.1. SecurityContextHolder là trạng thái hiện tại, không phải nơi lưu bền

`SecurityContextHolder.getContext().getAuthentication()` trả danh tính đang gắn với request/thread hiện tại. Mặc định holder dùng `ThreadLocal`, giúp code trong cùng luồng thực thi có thể đọc authentication mà không cần truyền qua mọi lời gọi phương thức.

```java
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

if (current != null && current.isAuthenticated()) {
    String name = current.getName();
}
```

Đây chỉ là **snippet**; chưa giải quyết anonymous principal hoặc cách framework đánh dấu anonymous authentication. Khi xác định người dùng thực sự đăng nhập, hãy dùng rule/annotation có ý nghĩa (`authenticated()`, principal type phù hợp) thay vì dựa duy nhất vào `isAuthenticated()` trong mọi trường hợp.

`SecurityContextHolder` không tự tạo cookie `JSESSIONID`, không lưu dữ liệu lên database và không tự chuyển dữ liệu sang thread khác hoặc request khác. Spring Security đảm nhiệm việc đặt và **xóa holder đúng vòng đời filter chain**, hạn chế rò rỉ danh tính khi servlet container tái sử dụng thread. Không dùng `MODE_GLOBAL` làm “cách lưu login” trong web app: nó có thể khiến danh tính của request này bị nhìn thấy ở request khác.

### 2.2. SecurityContextRepository mới là ranh giới lưu/khôi phục

Repository định nghĩa các thao tác như:

```java
DeferredSecurityContext loadDeferredContext(HttpServletRequest request);

void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);

boolean containsContext(HttpServletRequest request);
```

Đây là **chữ ký API minh họa**, không phải interface cần khai báo lại. Lưu ý `loadDeferredContext` được dùng thay cho API `loadContext(...)` cũ đã deprecated.

Các implementation quen thuộc:

- `HttpSessionSecurityContextRepository`: lưu/đọc context qua HTTP session nếu chính sách cho phép. Dùng cho login dựa trên session.
- `RequestAttributeSecurityContextRepository`: lưu context trong **request attribute**, giúp bảo toàn trong những dạng dispatch của cùng HTTP request, ví dụ ERROR; **không phải persistence qua request kế tiếp**.
- `DelegatingSecurityContextRepository`: đọc/lưu qua **nhiều delegate** theo thứ tự; trong Spring Security 6 cấu hình mặc định thường kết hợp request-attribute và session repository.
- `NullSecurityContextRepository`: không lưu context giữa các request. Phù hợp với một số cấu hình stateless như `SessionCreationPolicy.STATELESS`.

**Quan trọng:** chọn repository nào ảnh hưởng lớn đến kết quả của lời gọi `saveContext`. Gọi `saveContext` lên `NullSecurityContextRepository` không biến một ứng dụng stateless thành ứng dụng đăng nhập bằng session.

### 2.3. SecurityContextHolderFilter

Trong Spring Security 6 với mặc định explicit-save, filter này:

1. Nhận HTTP request đầu vào.
2. Yêu cầu repository cung cấp `DeferredSecurityContext` hoặc context tương ứng.
3. Gắn context vào holder cho phần còn lại của chuỗi filter/Servlet.
4. Để các filter xác thực/ủy quyền và controller thực hiện công việc.
5. Dọn trạng thái holder khi request kết thúc.

**Filter không tự quan sát mọi thay đổi trong `SecurityContextHolder` rồi gọi `saveContext`.** Nếu một custom controller chỉ `setContext(...)`, lần đọc của request sau vẫn dựa vào repository cũ.

```text
HTTP request #1                         HTTP request #2
      │                                       │
      ▼                                       ▼
SecurityContextHolderFilter            SecurityContextHolderFilter
      │ load from repo                        │ load from repo
      ▼                                       ▼
SecurityContextHolder                   SecurityContextHolder
      │                                       │
Custom login verifies                  Có context được lưu?
      │                                       │
      ├─ setContext(...)                      ├─ nếu đã save → authenticated
      ├─ saveContext(...)  [BẮT BUỘC         └─ nếu không save → anonymous/unauthenticated
      │   nếu muốn persistence]
      ▼
Response / clear holder
```

### 2.4. SecurityContextPersistenceFilter

Filter legacy được dùng trong cơ chế tự lưu: nạp context lúc đầu, kiểm tra sự thay đổi và lưu vào repository khi thích hợp ở cuối request hoặc trước khi response commit. Nó phải xử lý tình huống redirect sớm, response wrapper và các vấn đề thứ tự commit, nên cơ chế tự động vừa phức tạp vừa đôi khi dẫn đến ghi repository không cần thiết.

Trong Spring Security 6, `SecurityContextPersistenceFilter` **không còn là filter mặc định**; hệ thống thường dùng `SecurityContextHolderFilter`. Spring Security khuyến cáo **mỗi security chain dùng một trong hai cơ chế**, không đưa cả hai filter này vào cùng một chain.

## 3. Thay đổi theo phiên bản: Spring Security 5 → 6

| Phiên bản/cấu hình | Filter chủ đạo | Ai lưu context khi authentication thay đổi? |
| --- | --- | --- |
| Spring Security 5 theo mặc định lịch sử | `SecurityContextPersistenceFilter` | Cơ chế tự lưu qua repository ở request lifecycle |
| Spring Security 5.8 khi opt-in `requireExplicitSave(true)` | `SecurityContextHolderFilter` | Code/authentication mechanism phải gọi save khi cần persistence |
| Spring Security 6 theo mặc định | `SecurityContextHolderFilter` | **Explicit save** đối với code tự thay holder; các authentication filter chuẩn xử lý lưu trong flow của chúng |
| Spring Security 6 opt-in legacy `requireExplicitSave(false)` | Cơ chế persistence filter kiểu cũ, khi được hỗ trợ ở nhánh sử dụng | Dùng chủ yếu phục vụ migration, không nên coi là cấu hình khuyến nghị lâu dài |

**Không nhầm cấu hình với vai trò của filter.** Trong Spring Security 6, `requireExplicitSave(true)` là hành vi mặc định; thêm dòng đó trong code có thể giúp người review đọc ý định nhưng không nhất thiết thay đổi hành vi. Spring Security 5.8 dùng flag này để cho phép chuẩn bị migration trước khi lên 6.

Ví dụ cấu hình Servlet trong Spring Security 6:

```java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.securityContext(security -> security
            .requireExplicitSave(true));
    return http.build();
}
```

Đây chỉ là **snippet cấu hình**, cần imports, rules authorization và authentication mechanism cho ứng dụng thực. Nó không tự tạo login endpoint và không tự lưu một `Authentication` mới.

**Các thay đổi liên quan cần để ý:**

- Spring Security 6 dùng `DelegatingSecurityContextRepository` làm lựa chọn mặc định thay cho chỉ `HttpSessionSecurityContextRepository` theo tài liệu migration.
- `SessionManagementFilter` không được đặt mặc định. Các authentication mechanism chuẩn thường tự gọi `SessionAuthenticationStrategy` nếu cần, thay vì dựa vào SessionManagementFilter dò authentication thay đổi sau mỗi request.
- Một số tùy chọn DSL session management trong code cũ có cơ chế hoặc thời điểm xử lý khác; không copy máy móc cấu hình Spring Security 5.
- Khi lên Spring Security 7 hoặc dùng custom filter chain, cần xem tài liệu đúng phiên bản và chính các filters được cấu hình. Bài này chuẩn hóa theo API/behavior Spring Security 6.5.

### Vì sao explicit save giúp rõ ràng hơn?

Cơ chế cũ phải phát hiện context có thay đổi hay không, thời điểm response bị commit và cách lưu đúng khi redirect. Cơ chế mới chuyển trách nhiệm ghi persistence sang **đường authentication được biết chắc là đã thành công**. Điều này giúp giảm những write không cần thiết và dễ kiểm soát khi nào session thực sự cần được cập nhật.

Nhưng cũng có hệ quả: code custom trước đây dựa vào “cuối request filter tự save” nay có thể trở thành bug **login một request rồi mất ở request kế tiếp**. Nên test end-to-end thay vì chỉ assert `SecurityContextHolder.getContext().getAuthentication() != null` trong cùng controller.

## 4. Quy tắc lưu explicit đúng: tạo context mới, set và save

Mẫu chuẩn cho **manual authentication**:

```java
UsernamePasswordAuthenticationToken unauthenticated =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);

// Phải xác minh credential trước.
Authentication authenticated =
        authenticationManager.authenticate(unauthenticated);

// Tạo context MỚI, không sửa bừa context được nạp từ session cũ.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);

// Danh tính chỉ được dùng ở request hiện tại nếu dừng tại đây.
SecurityContextHolder.setContext(context);

// Muốn request kế tiếp khôi phục được thì lưu rõ ràng.
securityContextRepository.saveContext(context, request, response);
```

Đây là snippet trong controller/filter đã có các dependencies, không phải class độc lập. Thứ tự đúng:

1. Đọc credential từ request theo cơ chế đã bảo vệ.
2. Dùng `AuthenticationManager.authenticate(...)` để xác minh; chỉ tiếp tục nếu thành công.
3. Tạo một `SecurityContext` mới; gắn kết quả xác thực.
4. Đặt context trong `SecurityContextHolder` cho phần còn lại của request.
5. **Trước khi redirect, trả response hoặc commit**, gọi `SecurityContextRepository.saveContext(context,request,response)`.
6. Để Spring Security dọn holder lúc kết thúc chuỗi filter; không dùng cách giữ holder qua thread cho request sau.

**Không gọi `saveContext` trước khi credential được kiểm tra**. Không tự dựng `UsernamePasswordAuthenticationToken.authenticated(...)` với authorities do client gửi và coi đó là login hợp lệ. Đó là bypass authentication.

### 4.1. Vì sao nên tạo SecurityContext mới?

Không ưu tiên:

```java
// Dễ gây side effects khi context trước đó là object được reuse.
SecurityContextHolder.getContext().setAuthentication(authenticated);
```

Nếu context lấy từ repository/session đã tồn tại và được tham chiếu ở chỗ khác, sửa trực tiếp có thể tác động vào cùng object trước khi bạn chủ động save. Tạo `SecurityContextHolder.createEmptyContext()` giúp ranh giới object rõ hơn và giảm lỗi chia sẻ mutable state.

Lưu ý ngược lại: **“chưa gọi save” không phải hợp đồng bảo đảm mọi mutation vào object shared sẽ bị rollback**. Chính vì vậy cần tránh thay đổi context cũ tại chỗ và viết test.

### 4.2. Đúng repository phải được dùng ở cả hai phía

Nếu filter đang dùng `DelegatingSecurityContextRepository` nhưng controller lại dựng riêng một `HttpSessionSecurityContextRepository` hoặc `NullSecurityContextRepository`, có thể gặp hành vi khác dự kiến. Hãy chủ động inject **cùng bean** hoặc cấu hình repository nhất quán cho security chain và code manual.

Ví dụ:

```java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain web(
        HttpSecurity http,
        SecurityContextRepository repository) throws Exception {
    http.securityContext(security -> security
            .requireExplicitSave(true)
            .securityContextRepository(repository));
    return http.build();
}
```

Đây là snippet giải thích việc chia sẻ repository; không phải cấu hình web bảo mật hoàn chỉnh. Các lớp `HttpSessionSecurityContextRepository` và `SecurityContextRepository` nằm trong package `org.springframework.security.web.context`.

### 4.3. Khi nào save không tạo session?

Ngay cả khi bạn gọi `saveContext`, kết quả còn phụ thuộc repository và session policy:

- `HttpSessionSecurityContextRepository` có thể tạo HTTP session khi cần lưu authenticated context, nếu được phép tạo session.
- `SessionCreationPolicy.IF_REQUIRED` cho phép tạo session khi cần.
- `SessionCreationPolicy.NEVER` không chủ động tạo session để phục vụ Spring Security, nhưng có thể dùng một session đã tồn tại; những phần khác của ứng dụng vẫn có thể tạo session.
- `SessionCreationPolicy.STATELESS` là lựa chọn không dùng HTTP session để lấy context cho Spring Security, thường kết hợp `NullSecurityContextRepository`.
- `RequestAttributeSecurityContextRepository` lưu trong cùng request/dispatch, không mang danh tính sang request HTTP khác.
- Với repository custom, phải đọc đúng hợp đồng `saveContext` và persistence policy của nó; không suy ra cách hoạt động từ tên.

**Không dùng `request.getSession(true)` đơn thuần rồi tưởng authentication đã được lưu.** Có session và có `SPRING_SECURITY_CONTEXT` hợp lệ là hai việc khác nhau; framework/repository mới quản lý vị trí lưu đúng.

## 5. Ví dụ Spring Boot 3.5 + Java 17: chỉ set context và explicit save khác nhau thế nào?

Ví dụ chạy **hai endpoint POST** dùng cùng `AuthenticationManager`:

- `POST /manual/unsaved`: xác minh đúng password, set holder nhưng **không save repository**.
- `POST /manual/saved`: xác minh đúng password, set holder **và save repository**.
- `GET /whoami`: chỉ cho user authenticated; có cùng session hay không sẽ quyết định thấy thông tin nào.

Ứng dụng cố ý **không dùng form login filter** để tách biệt tác động của `saveContext`. CSRF **được giữ bật** và kiểm thử POST bằng `csrf()`. Tài khoản/mật khẩu demo chỉ dùng trong test nội bộ.

> **Giới hạn an toàn:** đây là ví dụ học **persistence semantics**, chưa phải hệ thống login custom đủ điều kiện triển khai production. Một custom login thực còn phải xử lý `SessionAuthenticationStrategy` (session fixation, concurrent sessions), authentication events, remember-me/MFA nếu áp dụng, rate limit, CSRF, error handling và logout. Khi có thể, ưu tiên login mechanism chuẩn của Spring Security.

### 5.1. Cấu trúc thư mục

```text
explicit-save-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ExplicitSaveApplication.java
    └── test/java/demo/ExplicitSaveApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'explicit-save-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

Spring Boot quản lý phiên bản dependency Spring Security tương thích; không khai chồng một version khác vào starter nếu không có lý do. Project yêu cầu JDK 17+ và Gradle tương thích với Spring Boot 3.5.

### 5.2. Ứng dụng Java đầy đủ

Tạo `src/main/java/demo/ExplicitSaveApplication.java`:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExplicitSaveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExplicitSaveApplication.class, args);
    }
}

@Configuration
class DemoSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("mai")
                        .password(encoder.encode("demo-pass-123"))
                        .roles("READER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Chọn session repository để thấy rõ save qua nhiều HTTP requests.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {

        http.securityContext(security -> security
                .requireExplicitSave(true)
                .securityContextRepository(repository));

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/manual/unsaved", "/manual/saved")
                .permitAll()
                .requestMatchers("/whoami").authenticated()
                .anyRequest().denyAll());

        http.exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(
                        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));

        // Tắt các login mechanism khác CHỈ để cô lập bài học manual login.
        // CSRF mặc định VẪN BẬT cho POST.
        http.formLogin(AbstractHttpConfigurer::disable);
        http.httpBasic(AbstractHttpConfigurer::disable);
        http.requestCache(AbstractHttpConfigurer::disable);

        return http.build();
    }
}

@RestController
class ManualLoginController {
    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;

    ManualLoginController(
            AuthenticationManager manager,
            SecurityContextRepository repository) {
        this.manager = manager;
        this.repository = repository;
    }

    @PostMapping("/manual/unsaved")
    String unsaved(
            @RequestParam String username,
            @RequestParam String password) {

        authenticateAndSetHolder(username, password);
        // Chỉ Authentication trong request hiện tại.
        return "current=mai";
    }

    @PostMapping("/manual/saved")
    String saved(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {

        SecurityContext context =
                authenticateAndSetHolder(username, password);

        // BƯỚC TẠO KHÁC BIỆT:
        repository.saveContext(context, request, response);

        return "current=mai";
    }

    private SecurityContext authenticateAndSetHolder(
            String username, String password) {
        Authentication authenticated = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        return context;
    }

    @GetMapping("/whoami")
    String whoami(Authentication authentication) {
        return authentication.getName();
    }
}
```

Hai method manual-login trong ví dụ trả body `current=mai` cố định vì chỉ dùng một test account; với sản phẩm thật không hardcode phản hồi theo user và không tiết lộ account details thừa. Nếu password sai, `AuthenticationManager` ném `AuthenticationException` và không đi đến `saveContext`.

**Cách đọc cấu hình:**

1. `securityContextRepository()` trả một `HttpSessionSecurityContextRepository` bean.
2. `SecurityFilterChain` dùng đúng bean đó qua `.securityContextRepository(repository)`.
3. Controller cũng inject **chính bean repository ấy**.
4. `requireExplicitSave(true)` bảo đảm mô hình HolderFilter/explicit save, dù ở Spring Security 6 đây đã là mặc định.
5. `SessionCreationPolicy.IF_REQUIRED` cho phép session khi cần lưu context.
6. `/manual/unsaved` chỉ set holder; `/manual/saved` làm thêm `saveContext`.
7. CSRF mặc định vẫn được bật. Bài không đưa ra endpoint GET làm thay đổi đăng nhập, cũng không tắt CSRF để “cho POST chạy”.
8. Entry point 401 được đặt chủ động để integration test có response ổn định cho request không authenticated; form login và HTTP Basic được tắt có chủ đích để tránh filter khác tự tạo authentication.

### 5.3. MockMvc test chứng minh persistence

Tạo `src/test/java/demo/ExplicitSaveApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

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
class ExplicitSaveApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void setContextOnlyDoesNotSurviveNextRequest() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/manual/unsaved")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("current=mai"));

        // CÙNG SESSION nhưng không có SecurityContext được save.
        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void explicitlySavedContextSurvivesNextRequest() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/manual/saved")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("current=mai"));

        // CÙNG SESSION đã có context: 200 và đúng principal.
        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));

        // SESSION KHÁC không thừa hưởng authentication của mai.
        mvc.perform(get("/whoami").session(new MockHttpSession()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void manualLoginRequiresCsrfToken() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/manual/saved")
                        .session(session)
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
gradle test
```

Nếu có Gradle Wrapper, dùng `./gradlew test` (macOS/Linux) hoặc `gradlew.bat test` (Windows). Kết quả mong đợi:

| Trường hợp | POST manual login | GET /whoami tiếp theo |
| --- | --- | --- |
| Chỉ `setContext`, không save | 200 ở request login hiện tại | **401**, dù gửi cùng session |
| Set + `repository.saveContext(...)` | 200 ở request login | **200**, trả `mai` nếu gửi cùng session |
| Request từ session khác | Không có context đã lưu | **401** |
| POST login không CSRF token | **403** | Không chạy phép xác thực hợp lệ |

Bộ test này chạy **Spring Security filter chain thật** trong MockMvc và gửi cùng `MockHttpSession` qua các request khác nhau. Nó đáng tin hơn một test chỉ gọi controller method rồi assert holder đang có authentication trong cùng stack frame.

**Chú thích thực thi:** ví dụ được thiết kế để biên dịch và chạy trên Java 17 với Spring Boot 3.5.7; các kết quả trên là kỳ vọng từ cấu hình đã nêu, không phải log từ một lần chạy test thực tế trong tài liệu. Khi chạy trên môi trường dự án, nếu test khác biệt, kiểm tra version, security chain order, CSRF, session repository, custom middleware và request cache trước khi thay đổi code.

## 6. Tại sao form login thông thường vẫn “tự lưu” mặc dù HolderFilter không save?

Vì **filter quản lý context** và **authentication mechanism** là hai tầng trách nhiệm khác nhau.

Trong form login tiêu chuẩn, khi người dùng gửi username/password đúng, `UsernamePasswordAuthenticationFilter` (dựa trên `AbstractAuthenticationProcessingFilter`) dùng manager để xác minh, xử lý session strategy cần thiết, đặt `Authentication` vào context, lưu bằng repository theo flow được Spring Security cấu hình và chạy success handler. Lập trình viên chỉ cần cấu hình đúng `formLogin` và session behavior; không phải viết controller tự gọi `saveContext`.

```text
Form login chuẩn:
UsernamePasswordAuthenticationFilter
    ↓ authenticate(...)
    ↓ SessionAuthenticationStrategy (khi phù hợp)
    ↓ SecurityContextHolder.setContext(...)
    ↓ SecurityContextRepository.saveContext(...)
    ↓ AuthenticationSuccessHandler (redirect/response)
    ↓ request tiếp theo khôi phục context

Manual login:
Controller hoặc custom Filter
    ↓ authenticate(...)
    ↓ [bạn phải xử lý session strategy cần thiết]
    ↓ setContext(...)
    ↓ [bạn phải saveContext(...) nếu muốn persistence]
    ↓ response
```

**Do đó cả hai nhận định đều đúng:** Spring Security có thể tự duy trì login của bạn khi dùng authentication mechanism chuẩn; còn một custom controller chỉ gọi `SecurityContextHolder.setContext(...)` thì không tự được lưu theo mặc định Spring Security 6.

### HTTP Basic, bearer token và stateless khác gì?

Một API stateless có thể nhận `Authorization: Basic ...` hoặc bearer token trên mỗi request. Filter kiểm tra credential/token từ request hiện tại và đặt authentication vào holder; nhiều cấu hình không cần lưu vào session. Trong trường hợp đó, `NullSecurityContextRepository` có thể là lựa chọn hợp lý.

Đừng đòi `saveContext` vào session để “sửa” một API đã chủ ý `SessionCreationPolicy.STATELESS`. Ngược lại, nếu một endpoint manual login được kỳ vọng tạo browser session, phải cấu hình repository/session nhất quán thay vì đặt stateless rồi cố tạo session trong controller.

**Lưu ý:** HTTP Basic có thể được tùy chỉnh để lưu session bằng repository khác theo tài liệu Spring Security; không định nghĩa mọi cơ chế HTTP Basic là tuyệt đối không thể có session.

## 7. Explicit save, SessionAuthenticationStrategy và session fixation

Đoạn sample ở mục 5 **chỉ chứng minh persistence**, không được dùng nguyên trạng làm login production. Với một lần login mới, ngoài `saveContext` có thể phải xử lý:

- **Session fixation protection:** xoay session ID khi đổi trạng thái anonymous → authenticated. Spring Security có `ChangeSessionIdAuthenticationStrategy` và chiến lược khác theo Servlet/session setup.
- **Concurrent session control:** nếu giới hạn số phiên, phải có `SessionRegistry` và `SessionAuthenticationStrategy` phù hợp, thường kết hợp nhiều strategy.
- **Authentication failure/success behavior:** handler, sự kiện audit, login throttling, MFA, remember-me và chính sách logout.
- **CSRF và cookie:** giữ chống CSRF cho các POST dùng cookie; `Secure`/`HttpOnly`/`SameSite`, HTTPS, session timeout và thông tin nhạy cảm.
- **Saved request và redirect:** chỉ redirect sau khi session/context được lưu đúng; không đợi cho response commit rồi mới save.

Snippet minh họa **bước strategy trước save** khi tự xây login:

```java
// Giả sử authentication đã được manager xác minh.
sessionAuthenticationStrategy.onAuthentication(
        authentication, request, response);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Đây là **pseudoconfiguration tích hợp**, cần một `SessionAuthenticationStrategy` được tạo/cấu hình theo session policies và các dependencies tương ứng; không copy vào project khi chưa có strategy đúng. Với form login chuẩn, framework đã có đường gọi strategy cần thiết; tự gọi thêm có thể gây double-processing.

**Không nhầm explicit save với tạo session an toàn.** `saveContext` là persistence; nó không tự thực hiện đầy đủ session fixation mitigation, login throttling hay MFA.

## 8. Logout: clear holder thôi chưa đủ

Một sai lầm tương tự xảy ra khi logout:

```java
SecurityContextHolder.clearContext();
```

Lệnh này chỉ xóa holder **hiện tại**. Nếu repository/session vẫn lưu context authenticated, request kế tiếp có thể đọc lại danh tính cũ. Với cơ chế explicit-save, lúc logout bạn cần dọn **cả trạng thái đã lưu** bằng repository/session và các login tokens liên quan theo chính sách.

**Ưu tiên dùng logout support chuẩn** của Spring Security:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/login?logout"));
```

Đoạn trên là snippet trong security-chain config, không phải class độc lập. Spring Security có các logout handlers chuẩn (gồm cơ chế xóa security context/session theo cấu hình) và với browser POST logout cần CSRF token hợp lệ. Không tự tạo GET logout để tiện thử nếu điều đó bỏ qua chống CSRF.

Nếu bắt buộc tự logout, logic thiết kế cần:

1. Từ chối request logout không có quyền hoặc CSRF proof phù hợp khi dùng cookie.
2. Xóa `Authentication` trong context và thực hiện `SecurityContextRepository.saveContext(emptyContext, request, response)` nếu repository yêu cầu.
3. Invalidate HTTP session/thu hồi cookie hoặc session identifiers theo chính sách.
4. Thu hồi remember-me/token/refresh token nếu ứng dụng có sử dụng.
5. Không chạy tiếp một request đã logout với authentication cũ trong holder.

Chỉ xóa một biến `ThreadLocal`, hoặc chỉ xóa cookie phía frontend, không đảm bảo server-side context/session đã bị loại bỏ.

## 9. DelegatingSecurityContextRepository và request dispatch

Spring Security 6 mặc định sử dụng `DelegatingSecurityContextRepository`, thường ghép:

```java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
```

Đây là snippet diễn đạt cách ghép repository, có thể dùng khi ứng dụng muốn cấu hình tường minh. Nó không thay thế cấu hình default nếu bạn không có yêu cầu tùy chỉnh.

**Mỗi delegate có mục đích khác:**

- `RequestAttributeSecurityContextRepository` giúp security context có thể tiếp tục xuất hiện trong **cùng HTTP request**, kể cả một số dispatcher chuyển sang ERROR dispatch sau khi holder đã được làm sạch theo filter lifecycle.
- `HttpSessionSecurityContextRepository` giúp context được khôi phục ở **request tiếp theo** nếu trình duyệt gửi đúng session cookie.
- `DelegatingSecurityContextRepository` đọc từ các delegate theo thứ tự và khi save sẽ chuyển lưu đến các delegate theo hợp đồng triển khai.

Nếu bạn dùng **chỉ RequestAttribute repository**, request kế tiếp sẽ **không** tự lấy lại login chỉ từ request attribute cũ. Nếu bạn dùng **chỉ HttpSession repository**, cần xem cách ERROR dispatch và response handling của chính ứng dụng. Nếu dùng **Null repository**, save không tạo persistence qua request.

### SecurityContextHolderFilter có tự tạo HttpSession?

Không phải trách nhiệm trực tiếp của HolderFilter. Việc một HTTP session được tạo hay không còn do repository, request cache, CSRF, login strategy, Servlet container và các thành phần khác. Vì vậy đừng kết luận “có session nghĩa là login được lưu” hoặc “không có cookie mới nghĩa là saveContext chắc chắn chưa chạy”.

### Vì sao save phải xảy ra trước response commit?

Với Servlet HTTP, response đã commit có thể không thêm được header `Set-Cookie` cho session ID mới. Một redirect ngay sau login có thể khiến client gửi request tiếp theo **trước khi server lưu context** nếu code tự viết sai thứ tự.

Quy tắc trong manual controller/filter:

```java
// Đã có Authentication hợp lệ và context mới.
SecurityContextHolder.setContext(context);
repository.saveContext(context, request, response);

// Sau đó mới commit response.
response.sendRedirect(request.getContextPath() + "/dashboard");
```

Đây là snippet; tránh dùng nó để redirect đến path do client tự cung cấp không được validate, vì open redirect là vấn đề khác cần xử lý. Không gọi `saveContext` trong `finally` sau khi response đã bị commit rồi hi vọng cookie/session luôn đúng.

## 10. Nhiều SecurityFilterChain và repository theo từng chain

Một ứng dụng có thể có:

```text
/api/**      -> API chain, bearer token, STATELESS
/portal/**   -> Browser chain, form login, session-based
/other       -> Catch-all chain, policy riêng
```

`FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp request**. Mỗi chain có thể có `SecurityContextRepository`/session policy riêng:

| Chain | Authentication | Repository/scope thường thấy |
| --- | --- | --- |
| API bearer token | JWT/bearer token mỗi request | Null/không lưu session |
| Browser form login | Username/password → session | Request attribute + HttpSession |
| Một custom manual login endpoint | Phải xem chain được chọn | Phải dùng repository tương thích với chain đó |

**Một quan hệ dễ gây lỗi:** controller thuộc `/portal/**` gọi `repository.saveContext(...)` nhưng request kế tiếp đến `/api/**` đi vào một chain stateless với `NullSecurityContextRepository`. Kết quả không lấy lại session là **đúng theo chính sách API**, không phải HolderFilter tự đánh mất login.

Ngược lại, nếu nhiều chain vô tình dùng chung HttpSession repository và đều đọc được context, authentication được lưu có thể ảnh hưởng đến authorization ở chain khác. Manager riêng cho từng chain không tự tạo ranh giới session cách ly. Khi có yêu cầu tenant/trust-domain isolation, phải test trạng thái session chéo chain.

### Matcher và login endpoint

Một chain chỉ áp dụng cho `/portal/**` mà lại tạo form login mặc định ở `/login` có thể khiến request login **không đi vào chain dự kiến**. Phải đảm bảo login, callback/logout và entry point khớp chain đã cấu hình, và catch-all không chặn chúng bất ngờ.

## 11. Async, ThreadLocal và request lifecycle

`SecurityContextHolder` mặc định dùng `ThreadLocal`. Một task chạy trong thread của `@Async`, `CompletableFuture` hoặc thread pool **không tự được đảm bảo** có cùng context như request thread. Các wrapper kiểu `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` hoặc cơ chế context propagation phù hợp giúp truyền context có kiểm soát.

Tuy nhiên **propagate context sang thread khác** không đồng nghĩa **persist context qua HTTP request khác**. Dù một background task nhận `Authentication`, không vì thế mà session đã được save. Không dùng `MODE_INHERITABLETHREADLOCAL` như biện pháp chung để tránh viết repository; thread pool và identity lifecycle có thể phức tạp, dễ rò rỉ danh tính.

Với async Servlet dispatch hoặc ERROR dispatch, request attributes và security filter lifecycle có thêm chi tiết. Đó là lý do `RequestAttributeSecurityContextRepository` tồn tại; hãy test đúng dispatcher types và authentication flow của ứng dụng khi cần.

## 12. Checklist chẩn đoán khi “login thành công nhưng request kế tiếp mất quyền”

1. **Xác định Spring Security version** và kiểm tra filter chain đang dùng `SecurityContextHolderFilter` hay legacy `SecurityContextPersistenceFilter`. Không chạy cả hai trong một chain.
2. **Xác định authentication mechanism:** form login chuẩn hay controller/filter tự viết? Nếu chuẩn, đừng mặc định chèn thêm save; kiểm tra config/filter.
3. **Tìm chỗ tạo Authentication:** có thật sự gọi `AuthenticationManager.authenticate(...)` hay chỉ tự đặt `authenticated=true`?
4. **Kiểm tra object SecurityContext:** có dùng `createEmptyContext()` và `setContext(context)` hay sửa context cũ theo reference?
5. **Kiểm tra saveContext:** nếu tự xác thực trong Spring Security 6, đã gọi `SecurityContextRepository.saveContext(context,request,response)` chưa?
6. **Kiểm tra thời điểm:** save có diễn ra **trước** `sendRedirect`, flush body hay response commit?
7. **Kiểm tra repository:** HttpSession, Delegating, RequestAttribute hay Null? Controller và chain có cùng repository không?
8. **Kiểm tra session policy:** `STATELESS`, `NEVER`, `IF_REQUIRED`, request cache và session creation.
9. **Kiểm tra cookie:** client có gửi session cookie hợp lệ ở request tiếp theo không? SameSite/Secure/Domain/Path, HTTPS, proxy và CORS credentials có đúng?
10. **Kiểm tra chain matcher:** request sau có đi vào chain khác, hoặc bị catch-all trước đó khớp không?
11. **Kiểm tra logout/session expiration:** session bị invalidate, cookie hết hạn, session fixation logic, concurrency policy hoặc phân tán nhiều node có chia sẻ session store không?
12. **Kiểm tra tests:** dùng `MockMvc` qua filter chain, gửi cùng `MockHttpSession` ở request sau; test cả session khác.
13. **Kiểm tra DEBUG trong môi trường an toàn:** xem filter chain và repository save/load, không bật log password, raw token, Authorization header hoặc cookie.
14. **Đối chiếu session với stateless:** nếu ứng dụng cố ý xác thực mỗi request, không nên đòi một session login như browser.

### Triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Khả năng cần kiểm tra | Hướng sửa |
| --- | --- | --- |
| POST login trả 200, GET /me ngay sau trả 401 | Custom login chỉ set holder | Save context vào đúng repository trước response |
| Login thành công nhưng không có cookie/session | Stateless policy hoặc repo không lưu session | Xem yêu cầu thật là stateless hay stateful |
| Có session cookie nhưng GET /me vẫn 401 | Context chưa save; cookie sai; chain khác | Test repository, matcher, cookie policy |
| Chỉ ERROR dispatch mất principal | Chỉ session repository/dispatch setup | Xem RequestAttribute repo/Delegating repo |
| Logout xong vẫn nhận user cũ | Session/repository chưa xóa | Dùng logout support, xóa và lưu context |
| Login nhiều lần không giới hạn session | Manual login bỏ qua SessionAuthenticationStrategy | Tích hợp strategy hoặc dùng mechanism chuẩn |
| Một chain nhận principal của chain khác | Chia sẻ session/context ngoài dự kiến | Thiết kế trust boundary và test cross-chain |
| @Async không thấy Authentication | Context ở ThreadLocal request | Dùng context propagation phù hợp, không dùng global holder |
| Form login mặc định không hoạt động sau thêm chain | Matcher không bao phủ login POST | Cấu hình đường dẫn login và chain matchers |
| Trước upgrade Spring Security 6 code chạy, sau upgrade mất session | Từng dựa vào implicit save | Thêm explicit save cho custom flow hoặc dùng built-in |

## 13. Kiểm thử QA nên có khi đổi phiên bản hoặc tự viết login

| Test | Yêu cầu kiểm chứng |
| --- | --- |
| Mặc định chain dùng HolderFilter | Không có legacy filter chạy đồng thời |
| Manual set không save | Chỉ request hiện tại có authentication; request sau 401 |
| Manual set + save | Request sau với cùng session có Authentication |
| Session khác | Không nhận danh tính của session đã login |
| POST không CSRF token | Bị từ chối khi dùng browser cookie auth |
| Password sai | Không lưu SecurityContext authenticated |
| Save trước redirect | Browser có session/cookie hợp lệ ở request theo redirect |
| Logout | Context trong session được xóa; request sau không còn authenticated |
| Session timeout hoặc invalidate | Khôi phục context thất bại đúng chính sách |
| Stateless API | Không vô tình lưu session chỉ vì Basic/JWT authentication |
| Nhiều filter chains | Repository, matcher và context đúng từng chain |
| Concurrent sessions/session fixation | Session ID thay đổi/limit áp dụng theo chính sách |
| ERROR dispatch | Principal visibility phù hợp khi dispatcher thay đổi |
| Distributed session | Các node có chính sách và session store nhất quán |

Test chỉ bằng `@WithMockUser` **không chứng minh** repository đã lưu session: annotation/post-processor có thể tạo sẵn authentication cho test request. Dùng login HTTP qua `MockMvc` rồi gửi **request thứ hai cùng session** như mục 5 để kiểm chứng persistence thật.

Khi nâng cấp Spring Security 5 → 6, nên ghi rõ một **migration checklist**:

1. Kiểm kê custom controllers, filters, success handlers hoặc service đang gọi `SecurityContextHolder.setContext`.
2. Tìm xem chỗ nào dựa vào implicit save, chỗ nào đã gọi `repository.saveContext`.
3. Quy định repo và session policy chính thức cho từng chain.
4. Chuyển các custom authentication flow sang explicit save đúng thứ tự.
5. Kiểm tra SessionAuthenticationStrategy, session fixation, concurrent sessions và logout.
6. Chạy test hai request/cookie/redirect, test stateless và CSRF.
7. Theo dõi 401/403 đột biến, session creation/write load và lỗi login sau deployment.
8. Không dùng `requireExplicitSave(false)` vô thời hạn chỉ để tránh sửa code; xem đây là lối chuyển tiếp nếu nhánh phiên bản còn hỗ trợ.

## 14. Sai lầm phổ biến và cách tránh

1. **Nhầm holder với repository:** `SecurityContextHolder.setContext` không đồng nghĩa session đã lưu.
2. **Nói HolderFilter tự save lúc kết thúc:** nó chỉ nạp và dọn holder; explicit-save đặt việc lưu ở authentication mechanism/code ứng dụng.
3. **Nói tất cả Spring Security 6 login đều cần gọi save thủ công:** các authentication mechanism chuẩn đã có cơ chế phù hợp.
4. **Dùng cả HolderFilter và PersistenceFilter trong cùng chain:** làm lifecycle khó dự đoán; chỉ chọn một.
5. **Dùng `requireExplicitSave(false)` như cấu hình mặc định mãi mãi:** nó là đường migration legacy, không phải lý do né hiểu contract.
6. **Chỉ test Authentication trong một request:** không phát hiện thiếu save giữa các request.
7. **Gọi save sau `response.sendRedirect` hoặc response commit:** có thể quá muộn để tạo/cập nhật session cookie.
8. **Dùng Null repository rồi mong login session tồn tại:** Null không lưu context giữa request.
9. **Dùng RequestAttribute repository rồi mong GET request mới được authenticated:** request attribute không tồn tại qua HTTP request khác.
10. **Dùng repository khác giữa controller và filter chain:** save và load không gặp nhau.
11. **Tạo HttpSession bằng tay rồi bỏ qua saveContext:** session tồn tại không đồng nghĩa context tồn tại.
12. **Sửa thẳng context cũ bằng getter:** có nguy cơ mutate object được share, khó kiểm soát persistence.
13. **Manual login bỏ qua SessionAuthenticationStrategy:** mất session fixation/concurrent session protection.
14. **Tắt CSRF để POST manual login chạy:** đặt rủi ro cho browser/session authentication.
15. **Tự set authenticated token từ dữ liệu client:** bypass xác minh credential và cấp quyền tùy ý.
16. **Chỉ clear ThreadLocal khi logout:** context stored trong session có thể được khôi phục ở request sau.
17. **Tưởng SecurityContextHolderFilter bảo đảm @Async có principal:** context propagation và persistence là hai bài toán khác nhau.
18. **Tưởng hai AuthenticationManager riêng tự cách ly session:** nếu repository/context được chia sẻ thì vẫn có liên hệ.
19. **Tắt session cho API nhưng kiểm thử cookie theo web browser:** test không đúng session policy.
20. **Không kiểm thử session cookie qua proxy/cross-site:** cookie Path, SameSite, Secure, Domain có thể làm mất session.
21. **Ghi log đầy đủ SecurityContext hoặc Authentication khi debug:** có nguy cơ lộ PII/credentials/token.
22. **Hiểu 401 là chắc chắn password sai:** có thể password đúng nhưng context không persist.
23. **Bỏ logout cleanup khi chuyển sang explicit save:** xóa holder nhưng không xóa persisted context.
24. **Đổi version mà không đọc migration guide:** khác biệt default filter/repository có thể ảnh hưởng behavior.
25. **Lưu full domain entity trong principal/session:** tăng rủi ro serialization, stale roles, dữ liệu không cần thiết.

## 15. Bài tập thực hành

**Bài 1 — Vẽ vòng đời:** vẽ hai sơ đồ: (a) HolderFilter tải context rồi dọn holder, không auto save; (b) PersistenceFilter legacy nạp, theo dõi và tự save. Giải thích vì sao không dùng cả hai trong một chain.

**Bài 2 — Chạy demo:** chạy `gradle test` ở mục 5. Giải thích vì sao cùng một `MockHttpSession`, `/manual/unsaved` vẫn trả 401 ở request tiếp theo, còn `/manual/saved` trả 200.

**Bài 3 — Redirect:** sửa endpoint saved để trả redirect sau khi gọi `saveContext`; kiểm tra cookie/session và request sau redirect. Đảo thứ tự save/redirect trong một test nghiên cứu rồi giải thích rủi ro response committed.

**Bài 4 — Repository:** thay `HttpSessionSecurityContextRepository` bằng `NullSecurityContextRepository`. Dự đoán test nào đổi kết quả; giải thích tại sao explicit save không thể ép Null repository lưu session.

**Bài 5 — RequestAttribute:** dùng `DelegatingSecurityContextRepository` với RequestAttribute + HttpSession, test một ERROR dispatch và một HTTP request mới. Phân biệt scope lưu.

**Bài 6 — Logout:** thêm logout chuẩn; gửi POST với CSRF token sau khi manual saved login, kiểm tra request sau không còn authenticated. Không chỉ clear holder trong controller.

**Bài 7 — Multi-chain:** tạo `/api/**` stateless và `/portal/**` stateful. Xác định chain/repo áp dụng cho manual login và test cookie không vô tình được chấp nhận bởi API.

**Bài 8 — Migration:** giả lập custom controller Spring Security 5 chỉ gọi `setContext`. Chuyển sang 6, thêm repository chung và explicit save; viết integration test gồm hai request. Kiểm tra session fixation/concurrent sessions riêng trước khi đưa production.

**Bài 9 — Async:** tạo một tác vụ chạy trên executor riêng sau login. Giải thích vì sao không tự có principal, cách sử dụng wrapper truyền context và vì sao việc đó không tự lưu HTTP session.

**Bài 10 — Security review:** liệt kê ít nhất năm cách một ứng dụng có thể báo “login thành công” dù chưa persist hoặc tạo phiên không an toàn, bao gồm thiếu `saveContext`, sai repo, sai cookie, bỏ session strategy và bypass authentication.

### Tiêu chí hoàn thành

Bạn tự trả lời được:

- `SecurityContextHolderFilter` có đọc/lưu context ở đâu và có tự gọi `saveContext` không?
- `SecurityContextPersistenceFilter` khác gì và default thay đổi từ Spring Security 5 sang 6 thế nào?
- `requireExplicitSave(true)` có ý nghĩa gì theo phiên bản?
- Vì sao form login chuẩn vẫn hoạt động mà manual controller thiếu save lại không?
- Sự khác biệt giữa `RequestAttribute`, `HttpSession`, `Delegating` và `NullSecurityContextRepository`?
- Khi nào cần `saveContext(context, request, response)` và vì sao phải làm trước response commit?
- Logout, session fixation, concurrent sessions, CSRF và nhiều filter chain liên quan persistence như thế nào?
- Làm sao viết test hai request cùng session để chứng minh context thực sự tồn tại?

## 16. Tài liệu chính thức để đối chiếu

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): hướng dẫn `SecurityContextRepository`, manual save, trạng thái default, `requireExplicitSave` và stateless.
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): Spring Security 5 automatic-save so với Spring Security 6 explicit-save, repository mặc định và SessionManagementFilter.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/servlet/authentication/persistence.html): sơ đồ HolderFilter/PersistenceFilter, request attribute/session delegation và nhu cầu explicit save. Khi dùng bản phát hành, đối chiếu trang versioned cùng nhánh.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, `Authentication`, filter authentication và flow thành công.
- [Spring Security 6.5.11 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `loadDeferredContext`, `saveContext` và `containsContext`.
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `SecurityFilterChain`, `FilterChainProxy`, thứ tự và gỡ lỗi filters.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): cơ chế xác thực chuẩn, success/failure handlers và phần tích hợp security context.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): bảo vệ POST và cookie-based session flows.

**Lưu ý về phiên bản:** các ví dụ Java dùng Spring Boot 3.5.7 tương ứng thế hệ Spring Security 6.5.11 về API. Khi áp dụng cho Spring Security 7 hoặc custom security filter stack, kiểm tra tài liệu và nguồn code chính xác của phiên bản đang chạy; tránh suy diễn từ behavior của một dự án/phiên bản khác.