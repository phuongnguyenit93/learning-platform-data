# Quan hệ giữa HTTP Basic, phiên và việc xác thực lại từng yêu cầu

> **Phạm vi:** Spring Security 6 trên **Servlet stack**, Spring Boot 3.x, Java 17+. Nội dung tập trung vào cơ chế **HTTP Basic authentication**, cách `SecurityContext` có thể được nạp/lưu trong phiên (`HttpSession`), và điều kiện khiến server **xác thực lại credentials** ở một request mới. Không đồng nhất HTTP Basic với “bắt buộc stateless” hoặc “bắt buộc gọi AuthenticationManager ở mọi request”.

## 1. Kết luận trọng tâm: ba khái niệm phải tách riêng

HTTP Basic, session và authentication trên từng request trả lời **ba câu hỏi khác nhau**:

1. **HTTP Basic:** Client gửi thông tin đăng nhập như thế nào? Thông thường dùng header `Authorization: Basic ...`, trong đó dữ liệu username/password được mã hóa Base64 theo quy ước giao thức. Base64 **không phải encryption**.
2. **Session:** Server có lưu kết quả authentication giữa các HTTP request hay không? Điều này phụ thuộc `SecurityContextRepository`, `SessionCreationPolicy` và cách bộ lọc xác thực thực hiện lưu context, **không tự suy ra chỉ từ việc dùng HTTP Basic**.
3. **Xác thực lại:** Khi request tiếp theo đến, Spring Security có phải gọi `AuthenticationManager`/`AuthenticationProvider` lại không? Câu trả lời phụ thuộc có credentials trong request, có `Authentication` hợp lệ đã được nạp vào `SecurityContextHolder`, và hành vi của `BasicAuthenticationFilter`.

**Tóm tắt dễ nhớ:**

- HTTP Basic là **cách client trình bày credentials trên HTTP**, không phải một session mechanism.
- Một API cấu hình **stateless** thường đòi client gửi Basic credentials trên mỗi request cần bảo vệ, từ đó mỗi request phải xác thực độc lập với session trước.
- Một ứng dụng **stateful** có thể nhận Basic credentials lúc đầu, lưu `SecurityContext` vào `HttpSession`, rồi request sau dùng session cookie để lấy lại authentication **ngay cả khi request sau không gửi Basic header**.
- **Có Basic header trong mỗi request không đồng nghĩa mật khẩu luôn được kiểm tra lại:** khi Spring Security đã nạp một `Authentication` phù hợp từ session/context, `BasicAuthenticationFilter` có thể bỏ qua lần xác thực lại cho cùng username.
- Chính sách nào đang hoạt động phải được chứng minh bằng **cấu hình thực tế và kiểm thử nhiều request**, không suy luận từ tên “Basic”.

## 2. HTTP Basic vận hành như thế nào?

HTTP Basic authentication thường bắt đầu khi client yêu cầu một URL bảo vệ mà chưa cung cấp danh tính:

```text
Client                                        Server
  |                                            |
  | GET /api/me                                |
  |------------------------------------------->|
  |                                            |
  | 401 Unauthorized                           |
  | WWW-Authenticate: Basic realm="api"        |
  |<-------------------------------------------|
  |                                            |
  | GET /api/me                                |
  | Authorization: Basic <Base64(user:pass)>   |
  |------------------------------------------->|
  |                                            |
  | 200 OK (nếu credentials và quyền hợp lệ)  |
  |<-------------------------------------------|
```

Chuỗi `Base64(user:pass)` không làm password trở nên bí mật trên đường truyền. Người đọc được header có thể giải mã Base64 để lấy credentials. **Phải dùng HTTPS**; tránh gửi header Basic tới host/origin không tin cậy.

### 2.1. Client có nhất thiết gửi Basic header ở mọi request?

HTTP Basic được thiết kế để client có thể **gửi lại** credentials trên những request thuộc phạm vi authentication thích hợp; browser có thể cache credentials và tự gắn header sau một challenge. Công cụ như `curl -u` cung cấp header cho lời gọi tương ứng. Tuy nhiên, **không phải mọi client đều tự gắn header ở mọi request hoặc mọi URL**.

Ví dụ hai lời gọi `curl` tách biệt:

```bash
curl -i -u learner:study123 http://localhost:8080/stateless/me
curl -i http://localhost:8080/stateless/me
```

Ở lời gọi thứ hai không có `-u`, không có Authorization header do người dùng yêu cầu ở ví dụ, nên với chain stateless và endpoint yêu cầu authentication, kết quả dự kiến là 401. Việc lời gọi đầu thành công **không tạo ra chứng cứ rằng request sau đã đăng nhập**.

### 2.2. HTTP Basic không phải cookie session

| Thuộc tính | HTTP Basic | Session cookie |
| --- | --- | --- |
| Dữ liệu client gửi | Header `Authorization: Basic ...` chứa credentials đã Base64 | Header `Cookie: JSESSIONID=...` (hoặc tên cookie ứng dụng dùng) |
| Ý nghĩa | Trình bày danh tính/mật khẩu cho authentication | Trình bày session identifier để server tra trạng thái phiên |
| Có chứa raw password hoặc biểu diễn tương đương? | Có: username/password có thể khôi phục từ Base64 | Thường không chứa password; cookie là mã phiên đủ quyền dùng |
| Server có thể xác minh mật khẩu? | Có, khi filter/provider quyết định authenticate | Thường không cần kiểm tra password nếu context hợp lệ đã được khôi phục |
| Phụ thuộc session persistence? | Không bắt buộc | Có, hoặc một session store tương đương |
| Rủi ro chính | Lộ header dẫn đến lộ password, browser giữ credentials | Session hijacking/fixation/CSRF tùy cách ứng dụng dùng cookie |

**Cả hai đều nhạy cảm.** Đối với Basic header, bảo vệ password; đối với cookie, bảo vệ session ID như một bearer credential. Không log header Authorization, cookie hay credential đã giải mã.

## 3. Vị trí của Spring Security trong Servlet filter chain

Một request HTTP vào ứng dụng Servlet có thể đi theo đường sau:

```text
Servlet container
   |
   v
DelegatingFilterProxy (target "springSecurityFilterChain")
   |
   v
FilterChainProxy
   |
   +--> chọn SecurityFilterChain đầu tiên match request
           |
           +--> SecurityContextHolderFilter
           |      nạp hoặc trì hoãn nạp SecurityContext từ repository
           |
           +--> BasicAuthenticationFilter
           |      đọc Authorization: Basic, xác thực nếu cần
           |
           +--> ExceptionTranslationFilter / AuthorizationFilter
                  kiểm tra có authentication/authorization phù hợp
           |
           +--> DispatcherServlet -> Controller
   |
   v
Response, dọn SecurityContextHolder ở cuối xử lý
```

Sơ đồ là mô hình khái niệm; thứ tự chính xác và số filter phụ thuộc cấu hình, phiên bản, và những filter được thêm vào. Điều quan trọng là `SecurityContextHolderFilter` và `BasicAuthenticationFilter` có **trách nhiệm khác nhau**:

- `SecurityContextHolderFilter` giúp request nhận ngữ cảnh từ `SecurityContextRepository` và dọn holder khi hoàn tất. Trong cơ chế **explicit save** của Spring Security 6, filter này không tự lưu mọi thay đổi context ở cuối request.
- `BasicAuthenticationFilter` đọc Basic header nếu có; khi cần, tạo authentication request và gọi `AuthenticationManager`. Nếu xác thực thành công, nó đặt `Authentication` vào context; cơ chế lưu context sau đó phụ thuộc repository đã cấu hình cho filter và policy.
- `AuthorizationFilter` dùng `Authentication` hiện có để quyết định request có đủ quyền truy cập endpoint không. Việc không có Basic header **không tự làm request bị từ chối** nếu context hợp lệ đã được nạp từ một session được ứng dụng chấp nhận.

**Đừng nhầm:** `SecurityContextHolder` lưu trạng thái cho luồng xử lý request hiện tại, còn `SecurityContextRepository` quyết định cách state được nạp/lưu giữa các request.

## 4. Stateless Basic: mỗi request phải tự mang credentials

Với một API chọn **`SessionCreationPolicy.STATELESS`** và repository không lưu (`NullSecurityContextRepository`), Spring Security không sử dụng `HttpSession` để lấy `Authentication` cho các request kế tiếp. Mỗi request tới endpoint bảo vệ phải tự có một credential hợp lệ theo cơ chế authentication của chain (ở đây là HTTP Basic).

```text
GET /stateless/me + Authorization: Basic valid
     -> SecurityContextRepository không nạp session auth
     -> BasicAuthenticationFilter gọi xác thực
     -> trả 200 "learner"

GET /stateless/me (không Authorization)
     -> context không có auth từ request trước
     -> request bảo vệ thiếu authentication
     -> 401 + WWW-Authenticate

GET /stateless/me + Authorization: Basic valid (lần nữa)
     -> cần xác minh credentials cho request mới
     -> trả 200 "learner"
```

Trong cấu hình thực tế, việc **cấp phép** còn phụ thuộc các matcher/roles và filter khác. Ví dụ trên chỉ xét một endpoint yêu cầu `authenticated()` và không có cơ chế authentication thứ hai.

### SessionCreationPolicy.STATELESS có đồng nghĩa “toàn hệ thống không bao giờ có HttpSession”?

Không. Policy này nói Spring Security không tạo/dùng `HttpSession` để lấy `SecurityContext` theo cấu hình liên quan. **Code ứng dụng, thư viện MVC hoặc bộ lọc khác vẫn có thể tạo `HttpSession`** vì lý do riêng. Do đó đừng chỉ tìm cookie `JSESSIONID` để kết luận một URL đang dùng session để xác thực.

Muốn API có hành vi thực sự stateless đối với security context, kiểm tra **cả** session policy, `SecurityContextRepository` và request cache/các cơ chế authentication khác.

### HTTP Basic có tự chứa authentication bền không?

Không. Basic header chỉ mang thông tin cần cho request đó. Server có thể quyết định xác thực bằng provider mỗi khi cần, nhưng bản thân header không biến thành “đã đăng nhập vĩnh viễn” hoặc token phiên. Khi mật khẩu bị thay đổi hay account bị vô hiệu hóa, một request Basic tiếp theo thực hiện kiểm tra lại có cơ hội nhận kết quả mới (còn tùy cache/phương thức kiểm tra tài khoản).

## 5. Stateful Basic: có thể kết hợp với HttpSession

HTTP Basic **không cấm dùng session**. Nếu application cấu hình repository lưu `SecurityContext` vào `HttpSession` **và** filter xác thực Basic thực sự dùng repository đó để lưu sau thành công, request sau có thể được khôi phục từ session cookie.

```text
Request 1: Basic + password đúng
     |
     +--> BasicAuthenticationFilter authenticate
     +--> SecurityContext được tạo/đặt
     +--> SecurityContextRepository.saveContext(...) ghi vào HttpSession
     +--> Response gửi session cookie (nếu tạo session mới)

Request 2: Cookie session nhưng KHÔNG Basic header
     |
     +--> SecurityContextHolderFilter nạp context từ HttpSession
     +--> BasicAuthenticationFilter không thấy Basic header nên đi tiếp
     +--> AuthorizationFilter thấy Authentication hợp lệ đã nạp
     +--> Controller trả 200

Request 3: KHÔNG cookie, KHÔNG Basic header
     |
     +--> không có context được nạp
     +--> 401 Unauthorized
```

**Chỉ đặt `SessionCreationPolicy.IF_REQUIRED` chưa đủ để khẳng định Basic authentication sẽ được lưu vào session.** Với Spring Security 6 và explicit save, cần xem **repository dùng để nạp context** và **repository mà `BasicAuthenticationFilter` sử dụng để save khi thành công**. Ở ví dụ chạy được bên dưới, ta cấu hình **cùng một `HttpSessionSecurityContextRepository` cho cả hai phía** để chứng minh hành vi.

### 5.1. Cái gì thực sự được lưu vào HttpSession?

Với `HttpSessionSecurityContextRepository`, kết quả là `SecurityContext` mang `Authentication` đã xác thực (thường có principal, authorities, thông tin liên quan), không phải chuỗi Basic header làm session key. Spring Security có thể clear thông tin credentials trên đối tượng authentication tùy provider/cấu hình.

Client mang một **session ID**; server dùng ID để lấy session context. Khi server restart hoặc session store hết hạn, dữ liệu có thể mất tùy session architecture. Khi cookie bị xóa, request mới không thể dựa vào session đó, dù trình duyệt có thể vẫn lưu Basic credentials và tự gửi lại.

### 5.2. Có session nhưng client vẫn gửi Basic header: provider có được gọi lại không?

Không bảo đảm. `BasicAuthenticationFilter` có logic xem authentication hiện có có đáp ứng request Basic hay không, nhằm tránh xác thực lại không cần thiết cho cùng danh tính. Khi context đã được nạp từ session và `Authentication` phù hợp vẫn được đánh dấu authenticated, filter **có thể bỏ qua** lời gọi `AuthenticationManager` cho Basic credentials mang cùng username.

Điều đó dẫn tới hai khác biệt:

- **Truyền credentials trên wire** và **kiểm chứng credentials tại server** là hai sự kiện khác nhau.
- **Có Basic header mỗi request** không đủ chứng minh server đã thực sự kiểm tra password/account state ở mỗi request, đặc biệt khi session đã có authentication cùng principal.

Khi username trong Basic header thay đổi, authentication hiện có không phù hợp, hoặc không có context hợp lệ, filter có thể tiến hành authentication mới. Không dựa vào một log `Authorization: Basic` để kết luận chính xác số lần `PasswordEncoder.matches(...)` được gọi.

Nếu policy **bắt buộc đánh giá lại mật khẩu hoặc tình trạng khóa account cho từng request**, không được chỉ thêm Basic header rồi mặc nhiên tin provider sẽ chạy lại. Thiết kế chain stateless/không nạp session authentication, kiểm soát cache và kiểm thử khả năng thu hồi credentials một cách chủ động.

## 6. Hai sơ đồ trình tự so sánh

### 6.1. Một request stateless và request tiếp theo

```text
Client               SecurityContextHolderFilter    BasicAuthenticationFilter     Provider
  |                              |                           |                   |
  | GET /stateless/me + Basic    |                           |                   |
  |----------------------------->|-------------------------->| authenticate ----->|
  |                              |                           |<--- Authentication-|
  |                              |                           |  set context      |
  |<-----------------------------|---------------------------| 200               |
  |                              |                           |                   |
  | GET /stateless/me no Basic   |                           |                   |
  |----------------------------->|-- empty context ---------->| no header          |
  |<-----------------------------|---------------------------| 401               |
```

Không có security session được dùng để giữ người dùng từ request thứ nhất. Request mới phải tự đáp ứng quy tắc authentication của endpoint.

### 6.2. Một request session-backed và request tiếp theo

```text
Client                 SecurityContextRepository       BasicAuthenticationFilter
  |                              |                                |
  | GET /session/me + Basic      |                                |
  |----------------------------->| context ban đầu                |
  |                              |---- authenticate + save <------|
  |<-----------------------------| 200 + session cookie           |
  |                              |                                |
  | GET /session/me + Cookie     |                                |
  |----------------------------->| load context từ session        |
  |                              |---- no Basic header ---------->|
  |<-----------------------------| 200 (authentication đã có)     |
```

Tùy cookie/session policy, thứ tự và filter cụ thể, kết quả có thể khác nếu application không thực sự lưu context hoặc cookie không được gửi lại. Vì vậy cần test ở cấp HTTP request thay vì chỉ quan sát `SecurityContextHolder` trong cùng request.

## 7. Ví dụ Spring Boot chạy được: hai chế độ trong một ứng dụng

Ví dụ dùng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.5**. Các endpoint:

- `GET /stateless/me`: yêu cầu Basic ở mỗi request; không dùng HTTP session để xác thực.
- `GET /session/me`: lần đầu có thể dùng Basic; sau khi Basic authentication được **lưu rõ ràng vào HttpSession**, request tiếp theo có session cookie có thể truy cập mà không gửi Basic header.
- Các đường dẫn còn lại được chain cuối từ chối theo chính sách demo.

Ta dùng một account `learner / study123` để kiểm thử, chỉ dành cho môi trường local.

### 7.1. Cấu trúc dự án

```text
http-basic-session-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    BasicSessionTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'http-basic-session-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

### 7.2. Lớp khởi động

Tệp `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 7.3. Cấu hình ba SecurityFilterChain

Tệp `src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    @Order(1)
    SecurityFilterChain statelessChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/stateless/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http.securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(new NullSecurityContextRepository()));

        http.requestCache(cache -> cache.disable());

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain sessionChain(HttpSecurity http) throws Exception {
        // Cùng một repository cho filter nạp và Basic filter lưu context.
        HttpSessionSecurityContextRepository repository =
                new HttpSessionSecurityContextRepository();

        http.securityMatcher("/session/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));

        http.securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(repository));

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(basic -> basic
                .securityContextRepository(repository));

        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackDenyChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Đọc cấu hình đúng tầng:**

- `@Order(1)` chỉ áp dụng cho `/stateless/**`; kết hợp `STATELESS`, `NullSecurityContextRepository` và tắt request cache để request mới không dùng security session từ request trước.
- `@Order(2)` chỉ áp dụng cho `/session/**`; dùng một instance `HttpSessionSecurityContextRepository` cho cả `securityContext` (nạp ở đầu request) và `httpBasic` (lưu khi authentication thành công). Đây là **mấu chốt** của ví dụ session-backed.
- `@Order(3)` match mọi đường dẫn còn lại và `denyAll`; tránh việc route mới vô tình nằm ngoài tất cả security chains.
- `SessionCreationPolicy.IF_REQUIRED` cho phép Spring Security tạo session khi cần; **không có nghĩa mọi request tự tạo session**.
- `requireExplicitSave(true)` làm rõ contract của Spring Security 6. Việc Basic filter được cấu hình dùng repository để lưu khác với chỉ `SecurityContextHolder.setContext(...)`.

Tài khoản demo sử dụng BCrypt để hash password, không lưu plaintext trong `UserDetailsService`. Đừng hard-code tài khoản/mật khẩu trong sản phẩm thật; dùng nguồn account và secret management phù hợp.

### 7.4. Controller

Tệp `src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping({"/stateless/me", "/session/me"})
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

Controller không quan tâm authentication đến từ Basic header của request đang chạy hay từ context đã được khôi phục từ session. `Authentication` mà controller nhận là kết quả của Security filter chain.

### 7.5. Kiểm thử bằng MockMvc

Tệp `src/test/java/demo/BasicSessionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void statelessRequiresBasicCredentialsOnEachIndependentRequest()
            throws Exception {
        MvcResult first = mvc.perform(get("/stateless/me")
                        .with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"))
                .andReturn();

        // Chuỗi stateless không cần tạo HttpSession cho security context.
        assertNull(first.getRequest().getSession(false));

        mvc.perform(get("/stateless/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/stateless/me")
                        .with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void sessionModeReusesSavedContextWithoutRepeatingBasicHeader()
            throws Exception {
        MvcResult first = mvc.perform(get("/session/me")
                        .with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(session);

        // Request mới: chỉ mang session, không có Basic header.
        mvc.perform(get("/session/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));

        // Cùng session ID không vượt qua chain cố ý cấu hình STATELESS.
        mvc.perform(get("/stateless/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void noSessionAndNoBasicHeaderIsUnauthorized() throws Exception {
        mvc.perform(get("/stateless/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/session/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/stateless/me")
                        .with(httpBasic("learner", "wrong")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/session/me")
                        .with(httpBasic("learner", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Kết quả dự kiến với cấu hình demo: **4 test PASS**. Đây là kiểm thử hành vi của Spring Security theo HTTP request. Nó không dùng `@WithMockUser`, vì `@WithMockUser` có thể đưa sẵn authentication vào context và che mất điều cần chứng minh: **Basic filter có tạo/lưu authentication hay không**.

Điểm khác biệt quan trọng nhất nằm trong test `sessionModeReusesSavedContextWithoutRepeatingBasicHeader`: request đầu gửi Basic credentials; request thứ hai chỉ có `MockHttpSession`, không dùng `httpBasic`, nhưng vẫn vào controller nhờ repository nạp context.

### 7.6. Chạy và thử bằng curl

Cài JDK 17+ và Gradle 8.5 tương thích. Từ thư mục gốc của dự án:

```bash
gradle test
gradle bootRun
```

Nếu đã tạo Gradle Wrapper, có thể dùng `./gradlew` trên macOS/Linux hoặc `.\gradlew.bat` trên Windows.

**Nhóm stateless:**

```bash
curl -i -u learner:study123 http://localhost:8080/stateless/me
curl -i http://localhost:8080/stateless/me
curl -i -u learner:wrong http://localhost:8080/stateless/me
```

Dự kiến lần lượt: **200**, **401**, **401**.

**Nhóm session-backed:** lưu cookie từ lần Basic thành công; request tiếp theo chỉ gửi cookie, không dùng `-u`:

```bash
curl -i -c cookies.txt -b cookies.txt -u learner:study123 \
  http://localhost:8080/session/me

curl -i -b cookies.txt \
  http://localhost:8080/session/me

curl -i \
  http://localhost:8080/session/me
```

Dự kiến lần lượt: **200**, **200**, **401** (lời gọi cuối không gửi Basic/cookie). Tên/giá trị cookie và các header runtime không phải output cố định; nhìn vào `Set-Cookie` khi session mới được tạo.

**Không dùng HTTP thật để truyền password trên mạng công cộng.** `http://localhost` chỉ phù hợp thực hành cục bộ; với hệ thống thật phải có HTTPS, chính sách cookie chặt và cơ chế xác thực phù hợp.

### 7.7. Ma trận kết quả quan sát

| Request và credentials | Chain stateless | Chain session-backed |
| --- | --- | --- |
| Basic đúng, không có session trước | 200 | 200 và có thể tạo/lưu session |
| Request mới chỉ có cookie hợp lệ từ lần Basic thành công | 401 | 200 (với repository như demo) |
| Request mới không cookie, không Basic | 401 | 401 |
| Basic sai, không có context hợp lệ | 401 | 401 |
| Basic đúng ở request mới độc lập | 200, cần xác thực độc lập | 200, có thể tạo/lưu session |
| Có cookie context cũ và Basic cùng username | Không dùng session authentication | Filter có thể tận dụng authentication đang có thay vì xác thực lại |

Tất cả trạng thái HTTP trên giả định endpoint yêu cầu `authenticated()` và không có proxy/SSO/filter khác thay đổi authentication. Không suy ra cùng kết quả cho mọi ứng dụng chỉ từ việc `httpBasic()` đã bật.

## 8. Chính xác khi nào BasicAuthenticationFilter gọi AuthenticationManager?

Quy trình tư duy khi xử lý request:

```text
Request mới
  |
  +--> SecurityContextRepository có nạp Authentication hợp lệ không?
  |        |
  |        +--> có, nếu session-backed và session tồn tại
  |        +--> không, nếu stateless/null repository
  |
  +--> Có Authorization: Basic ... không?
           |
           +--> không: Basic filter không tự xác thực bằng password
           |           -> context đã có thì có thể được dùng
           |           -> không có context thì endpoint bảo vệ bị chặn
           |
           +--> có:
                   -> thông tin Basic có cần authentication mới không?
                          |
                          +--> cần: gọi AuthenticationManager
                          |          -> UserDetailsService/PasswordEncoder...
                          |          -> set/save SecurityContext nếu thành công
                          |
                          +--> không cần: dùng Authentication đang có
```

Đây là mô hình giải thích, không phải một bản sao mã nguồn. Chi tiết logic “authentication cần thiết hay không” phụ thuộc phiên bản `BasicAuthenticationFilter` và `SecurityContextHolderStrategy`. Trong cách triển khai điển hình, filter có thể kiểm tra danh tính trong Basic header so với authentication hiện tại và trạng thái `isAuthenticated()`.

### Tại sao không nên đo bằng số lần request?

Cùng một số request có thể dẫn đến số lần provider chạy khác nhau:

- 10 request vào chain stateless, mỗi request đều có Basic hợp lệ → thường có 10 lần xử lý authentication tương ứng, trừ các cache/optimization khác của provider/hạ tầng.
- 10 request vào chain session-backed sau login → có thể có một lần authentication bằng Basic đầu tiên và chín lần sử dụng context đã lưu.
- 10 request có Basic header nhưng context session cùng username đang authenticated → Basic filter có thể không gọi provider lại như suy đoán.
- Nếu HTTP client xóa cookie và không giữ credentials, request tiếp theo không có authentication nào → 401.

**Muốn chứng minh việc xác thực lại, đo đúng ranh giới:** instrument `AuthenticationProvider.authenticate(...)`/`UserDetailsService.loadUserByUsername(...)` hoặc thêm test kiểm soát reset account/session. Không kết luận chỉ từ request count, header count hoặc số dòng “Securing GET...” trong log.

## 9. SecurityContextRepository và SessionCreationPolicy quyết định điều gì?

| Tên | Chức năng | Ghi nhớ |
| --- | --- | --- |
| `SecurityContextHolder` | Context trong request/thread hiện tại | Được dọn cuối request; không tự lưu bền |
| `SecurityContextHolderFilter` | Nạp context từ repository và dọn holder | Explicit-save không tự ghi mọi thay đổi |
| `NullSecurityContextRepository` | Không lưu context vào kho bền | Phù hợp với stateless security |
| `RequestAttributeSecurityContextRepository` | Giữ context theo request attributes, hỗ trợ những dispatch trong cùng request | Không lưu giữa các request HTTP độc lập |
| `HttpSessionSecurityContextRepository` | Lưu/đọc context qua `HttpSession` | Có thể tái sử dụng authentication qua request sau |
| `DelegatingSecurityContextRepository` | Tổng hợp nhiều repository | Phải xem thành phần nào là session-backed |
| `SessionCreationPolicy.STATELESS` | Không tạo và không dùng session để lấy SecurityContext | Không cấm code khác tự tạo HttpSession |
| `SessionCreationPolicy.IF_REQUIRED` | Cho phép tạo session khi cần | Không đồng nghĩa mọi filter mặc định tự lưu context |
| `SessionCreationPolicy.NEVER` | Spring Security không tạo session, nhưng có thể dùng session đã tồn tại | **Không** đồng nghĩa stateless |
| `SessionCreationPolicy.ALWAYS` | Spring Security tạo session theo chính sách | Không thay việc cấu hình lưu context khi dùng explicit save |

**Lưu ý Spring Security 6:** khi `SecurityContextHolderFilter` yêu cầu explicit save, code authentication tùy chỉnh phải gọi `SecurityContextRepository.saveContext(context, request, response)` nếu muốn giữ context qua request. Một authentication filter chuẩn có thể được cấu hình để gọi save; ví dụ `httpBasic(basic -> basic.securityContextRepository(repo))` ở trên đảm nhận việc đó cho Basic flow.

Không viết custom controller login rồi chỉ gọi `SecurityContextHolder.setContext(...)` và mong `SessionCreationPolicy.IF_REQUIRED` tự lưu. Session policy quản lý cách tạo/dùng session, còn repository và filter quyết định việc save/load authentication.

## 10. Hệ quả bảo mật: thu hồi tài khoản, thay mật khẩu và logout

### 10.1. Password đã đổi nhưng session vẫn tồn tại

Trong chain stateless, khi Basic header được xác thực lại ở request mới, việc đối chiếu password mới và trạng thái account có cơ hội phản ánh thay đổi. Nhưng nếu provider/UserDetails được cache hoặc dữ liệu bị trễ, kết quả có thể chưa cập nhật ngay.

Trong chain session-backed, nếu request mới chỉ cần nạp `SecurityContext` cũ từ session, `PasswordEncoder.matches(...)` có thể **không chạy**. Do đó việc thay password, disable account hoặc khóa tài khoản trong database không tự động chứng minh session cũ đã bị thu hồi.

**Nếu yêu cầu thu hồi tức thì:** cần chính sách session invalidation, session registry/revocation hoặc xác thực lại/kiểm tra trạng thái account thích hợp. Một session có `Authentication.isAuthenticated() == true` không bảo đảm account ngoài database vẫn ở trạng thái hiện tại.

### 10.2. HTTP Basic không có thao tác logout chuẩn như form login

Browser có thể lưu Basic credentials và tự gửi lại trong phạm vi phù hợp. Một endpoint server trả 401 hay invalidate session **không bắt buộc** xóa credentials được browser lưu. Tính năng logout của ứng dụng phải hiểu:

- Nếu có session, invalidate session/xóa security context và cookie theo chính sách;
- Nếu Basic header vẫn được gửi lại, server có thể xác thực người dùng **lần nữa** ngay lập tức;
- Không giả định `logoutSuccess` đã khiến browser “quên” password đã cache;
- Với yêu cầu logout rõ ràng, có thể ưu tiên một cơ chế login/token phù hợp hơn HTTP Basic trực tiếp.

Không biến việc xóa `SecurityContextHolder` của request thành thao tác “thu hồi mọi phiên”.

### 10.3. Cookie authentication và CSRF

Khi ứng dụng dùng session cookie để nhận diện user ở request kế tiếp, trình duyệt có thể tự gửi cookie. Điều này làm **CSRF protection** quan trọng đối với các thao tác thay đổi trạng thái. Không mặc định tắt CSRF chỉ vì ban đầu ứng dụng sử dụng HTTP Basic.

Với API thuần stateless chỉ nhận Basic header do client chủ động kiểm soát, phân tích CSRF khác với web app có cookie tự động. Nhưng browser có thể tự cache/gắn Basic credentials, nên **không thể khẳng định “dùng Basic là không có CSRF”**. Hãy đánh giá cách client gửi credentials, cookies, CORS, `SameSite`, nguồn request và nghiệp vụ POST/PUT/DELETE thực tế.

Trong demo chỉ có endpoint GET nên không cần gửi CSRF token. Nếu mở rộng thêm POST, test CSRF rõ ràng hoặc sử dụng một policy CSRF đã được phân tích theo kiến trúc của từng chain.

### 10.4. Session fixation và giới hạn phiên

Cơ chế login tiêu chuẩn của Spring Security có thể phối hợp session authentication strategy để bảo vệ session fixation, giới hạn concurrent sessions, v.v. Khi cố ý cho **HTTP Basic tạo session bền**, đừng mặc định mọi bước session authentication strategy của form-login đã tự chạy giống hệt. Cần kiểm tra phiên bản/cấu hình, cơ chế rotate session ID, timeout, concurrent session policy và logout.

Ví dụ `/session/me` minh họa persistence **có chủ đích**; nó không phải hướng dẫn đầy đủ để triển khai browser login production. Với ứng dụng thật, thường nên chọn một cơ chế login/session cụ thể thay vì trộn Basic credentials và session cookie mà không có chính sách rõ ràng.

### 10.5. Session cookie và transport

Với môi trường production:

- Dùng HTTPS để bảo vệ cả Authorization header và session cookie.
- Đặt cookie `Secure`, `HttpOnly` và `SameSite` phù hợp threat model; tránh session ID trong URL.
- Rotate/invalidate session theo đúng policy, thiết lập idle/absolute timeout phù hợp.
- Tránh ghi credentials, Authorization header, session ID, cookie vào logs hoặc metrics không an toàn.
- Giới hạn rate login và bảo vệ credential stuffing/MFA khi phù hợp.

## 11. Các hiểu nhầm thường gặp

### 11.1. “HTTP Basic mặc định luôn stateless”

**Không nên khẳng định như vậy.** HTTP Basic là authentication scheme; session behavior là quyết định của ứng dụng/framework. Cần đọc `SecurityFilterChain`, `SecurityContextRepository`, `SessionCreationPolicy` và cách Basic filter lưu context. Một số cấu hình mặc định của Spring Security có thể sử dụng session cho request cache hoặc các mục đích khác; chỉ thấy session cookie chưa chứng minh authentication được lưu trong đó.

### 11.2. “Có JSESSIONID nghĩa là server không cần Basic nữa”

Không nhất thiết. Session có thể tồn tại do CSRF/request cache/MVC nhưng **không chứa authentication**; Basic filter có thể đang lưu context theo request attributes thay vì session. Muốn test, gửi request mới **chỉ có cookie** tới endpoint yêu cầu auth, không mang Authorization header. Nếu nhận 401, chỉ có cookie chưa đủ ở cấu hình đó.

### 11.3. “Có Basic header thì chắc chắn kiểm tra password mỗi request”

Không. Nếu `Authentication` hợp lệ từ session đã được nạp và Basic filter thấy cùng danh tính, nó có thể bỏ qua việc gọi provider. Xác thực lại không được đo bằng sự hiện diện của header.

### 11.4. “Chỉ cần IF_REQUIRED để giữ login”

Không. Nếu filter xác thực không gọi save vào repository session-backed trong explicit-save flow, context không tự bền qua request. Cần cấu hình đúng **cả phía load và phía save**.

### 11.5. “STATELESS cấm mọi code tạo session”

Không. Nó chỉ đặt chính sách liên quan đến Spring Security sử dụng session cho security context; code khác vẫn có thể tạo session. Kiểm tra nguồn cookie/session, không suy luận từ trạng thái browser.

### 11.6. “Basic là mã hóa password an toàn vì Base64 khó đọc”

Sai. Base64 giải mã được dễ dàng; HTTP Basic phải đi qua TLS. HTTPS bảo vệ đường truyền nhưng không thay hashing password trong database, rate limiting hay chính sách credential.

### 11.7. “Logout làm browser xóa Basic credentials”

Không có bảo đảm chuẩn như vậy. Browser có thể tiếp tục gửi Authorization header đã cache; session invalidation và xóa holder không phải thao tác xóa browser credential cache.

### 11.8. “Đổi password sẽ tự làm mọi request session bị 401”

Không. Session-backed context cũ có thể vẫn được nạp mà không kiểm tra lại password. Muốn thu hồi tức thì phải có cơ chế invalidate/revalidate phù hợp.

### 11.9. “Mọi URL cùng dùng một policy”

Không khi ứng dụng có nhiều `SecurityFilterChain`. Một chain cho `/stateless/**` và một chain cho `/session/**` có thể hoàn toàn khác nhau về repository/session/CSRF. `FilterChainProxy` chọn **chain đầu tiên match request**. Đừng kiểm tra `/stateless/me` rồi áp kết luận cho `/session/me`.

## 12. Checklist gỡ lỗi trong ứng dụng đang chạy

Khi một request trả 200/401 bất ngờ:

1. **Xác định đúng URL và chain.** Matcher nào chọn request, `@Order` của chain, có fallback chain?
2. **Kiểm tra header và cookie.** Có `Authorization: Basic` không? Có session cookie không? Client có tự gắn credentials hay cookie?
3. **Kiểm tra repository nạp context.** `SecurityContextHolderFilter` của chain đang dùng `NullSecurityContextRepository`, `HttpSessionSecurityContextRepository` hay repository khác?
4. **Kiểm tra đường lưu context sau authentication.** Basic filter có được cấu hình sử dụng cùng repository session-backed không? `requireExplicitSave` có ảnh hưởng custom flow không?
5. **Kiểm tra session policy.** `STATELESS`/`NEVER`/`IF_REQUIRED`/`ALWAYS` có đúng mục tiêu của URL?
6. **Thử hai request độc lập.** Basic đầu tiên thành công; request thứ hai chỉ cookie; request thứ ba không cookie/Basic.
7. **Thử account thay đổi.** Đổi password/khóa user và xem request dùng session cũ có bị chặn theo policy không.
8. **Đo provider nếu cần.** Instrument `AuthenticationProvider.authenticate` hoặc `UserDetailsService`; đừng chỉ đếm Authorization headers.
9. **Đối chiếu 401 với 403.** 401 thường do thiếu/không hợp lệ credentials trong demo; 403 do thiếu quyền hoặc CSRF; phụ thuộc entry point và handler.
10. **Không log secret.** Không đưa raw password, Basic header, cookie hoặc session ID vào log debug để tìm lỗi.

Khi debug môi trường phát triển, có thể bật DEBUG có kiểm soát:

```properties
logging.level.org.springframework.security=DEBUG
```

Không để logging quá chi tiết cho dữ liệu nhạy cảm ở production. Các dòng “Securing GET ...” cho biết request được bảo vệ bởi filter chain, **không chứng minh** provider đã xác thực lại password.

## 13. Câu hỏi tự kiểm tra

1. **HTTP Basic có tạo session theo chuẩn RFC không?** Không. Giao thức mô tả cách trình bày credentials/challenge, không tự quy định cơ chế session của Spring Security.
2. **Trong chain STATELESS, request thứ hai không có Basic header có được dùng authentication của request đầu không?** Không qua `HttpSession`, với NullSecurityContextRepository và không có auth mechanism khác.
3. **Vì sao cookie vẫn có thể được tạo trong một ứng dụng có chain stateless?** Code hoặc thành phần khác có thể dùng session; điều đó không chứng minh chain stateless đã sử dụng session để nạp authentication.
4. **Điều gì cần để một lần Basic login được dùng ở request sau chỉ có cookie?** Cần repository session-backed và cơ chế xác thực thực sự lưu `SecurityContext` vào repository đó, cùng cookie hợp lệ trên request sau.
5. **Có Basic header mỗi request có đảm bảo password được kiểm tra lại không?** Không; filter có thể sử dụng context đã xác thực phù hợp và skip việc authenticate lại.
6. **HTTP Basic và session cookie chứa cùng dữ liệu không?** Không; Basic mang credentials có thể khôi phục từ Base64, cookie thường mang session ID.
7. **Đổi password có tự thu hồi session cũ không?** Không được giả định; cần session revocation/revalidation policy.
8. **`SessionCreationPolicy.IF_REQUIRED` có tự động save context trong mọi custom auth flow không?** Không, explicit-save yêu cầu cơ chế authentication lưu context.
9. **Tại sao HTTP Basic phải đi với HTTPS?** Base64 không bảo vệ password trên wire.
10. **Cách kiểm tra ứng dụng có dùng session authentication hay không?** Test request đầu có Basic, request thứ hai chỉ có cookie và không có Authorization header, đối chiếu 200/401, đồng thời xem cấu hình repository.

**Ghi nhớ:** HTTP Basic **không đồng nghĩa** với stateless hoặc stateful. Header `Authorization: Basic` là cách cung cấp credentials; `SecurityContextRepository` và `SessionCreationPolicy` quyết định cách server khôi phục authentication qua request; `BasicAuthenticationFilter` quyết định khi nào cần gọi `AuthenticationManager`. Muốn xác thực độc lập trên mọi request, cấu hình stateless rõ ràng và test; muốn giữ session, cấu hình cả **load và save** context rồi test request thứ hai **không mang Basic header**. Luôn bảo vệ Basic credentials và session cookie bằng HTTPS và chính sách an toàn phù hợp.
