# Endpoint bị bỏ lọt do `securityMatcher`, `@Order` hoặc không có chuỗi dự phòng

## 1. Vì sao một endpoint có thể không được Spring Security bảo vệ?

Trong **Spring Security Servlet**, việc có dependency `spring-boot-starter-security`, một `SecurityFilterChain` bean hoặc một rule `.anyRequest().authenticated()` **không đủ để kết luận mọi HTTP request đều được kiểm tra bởi Spring Security**. Khi ứng dụng định nghĩa nhiều chuỗi lọc, `FilterChainProxy` sẽ chọn **chuỗi đầu tiên** có `RequestMatcher` khớp request. Nếu **không có chuỗi nào khớp**, request không nhận các filter của Spring Security do `FilterChainProxy` quản lý.

Đây là lỗi triển khai nguy hiểm vì endpoint vẫn có thể hoạt động bình thường:

- `/api/orders` được bảo vệ bằng HTTP Basic/JWT nhưng `/health/internal` mới tạo lại trả `200 OK` không cần login;
- một chuỗi `/api/**` có cấu hình `authenticated()` rất chặt, song `/v2/api/orders` không khớp `/api/**`;
- hai chuỗi cùng khớp một URL, chuỗi `@Order(1)` cho phép truy cập công khai nên chuỗi `@Order(2)` yêu cầu vai trò không bao giờ được sử dụng;
- ứng dụng chỉ định nghĩa chuỗi cho `/admin/**`, sau đó tưởng Spring Boot sẽ tự bổ sung chuỗi mặc định cho mọi đường dẫn còn lại.

**Phân biệt ba kết quả:**

1. **Không chuỗi nào khớp:** request có thể đi đến controller **mà không qua Spring Security web filters**, nếu không có lớp bảo vệ khác.
2. **Có chuỗi khớp nhưng rule `permitAll`:** request **vẫn đi qua một SecurityFilterChain**, chỉ là bước authorization cho phép anonymous; một số filter khác vẫn có thể chạy.
3. **Có chuỗi khớp và rule từ chối:** Spring Security thực thi authentication/authorization và trả status theo entry point/handler.

Không nên suy đoán trạng thái bảo vệ chỉ từ HTTP 200/401/403/404. Phải xác định **chuỗi nào được chọn** và **rule nào được áp dụng**.

## 2. Mental model: `FilterChainProxy` chọn chuỗi đầu tiên

Hình dung cấu hình có ba chuỗi:

```text
HTTP REQUEST
    |
    v
DelegatingFilterProxy / springSecurityFilterChain
    |
    v
FilterChainProxy
    |
    +-- @Order(1) securityMatcher("/admin/**") ?
    |         YES -> dùng chuỗi ADMIN, DỪNG xét chuỗi khác
    |         NO  |
    |             v
    +-- @Order(2) securityMatcher("/api/**") ?
    |         YES -> dùng chuỗi API, DỪNG xét chuỗi khác
    |         NO  |
    |             v
    +-- @Order(3) matcher mọi request ?
              YES -> dùng chuỗi FALLBACK
              NO  -> KHÔNG có Spring Security filter chain
```

Với `FilterChainProxy`, một HTTP request **không cộng dồn filter của mọi chuỗi khớp**. Nó áp dụng filter của **chuỗi khớp đầu tiên**, theo thứ tự đã cấu hình.

Điều đó dẫn đến hai nguyên tắc:

- Chuỗi dành cho một phạm vi hẹp nên đứng **trước** chuỗi rộng hơn khi chúng có thể giao nhau.
- Luôn có một **chuỗi dự phòng (catch-all)** phù hợp với chính sách của ứng dụng nếu cần bảo đảm không request nào bị bỏ ngoài Spring Security.

Ví dụ `@Order(1)` bắt mọi request sẽ chiếm quyền chọn chuỗi trước các chuỗi API/ADMIN ở `@Order(2)`, `@Order(3)`. Các rule `hasRole` trong chuỗi đến sau **không có cơ hội chạy**. Đây là lỗi *chain shadowing*.

Đồng thời, một chuỗi fallback không nhất thiết phải “cho phép mọi thứ”. Trong hệ thống ưu tiên an toàn, fallback thường dùng `anyRequest().denyAll()` hoặc quy tắc xác thực/phân quyền rõ ràng.

## 3. Hai cấp matcher: chọn chuỗi và phân quyền trong chuỗi

Spring Security dùng các tên API gần nhau nhưng có ý nghĩa khác nhau.

### `http.securityMatcher(...)`

Đặt **điều kiện để toàn bộ `SecurityFilterChain` tham gia xử lý request**:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Đây là đoạn ví dụ trong một class `@Configuration` có imports thích hợp.

Với đoạn này:

- Request `/api/orders` thường khớp chuỗi API.
- Request `/public/info` **không khớp chuỗi API**.
- `.anyRequest().authenticated()` chỉ áp dụng **bên trong những request đã chọn vào chuỗi API**, không bảo vệ `/public/info`.

### `authorizeHttpRequests().requestMatchers(...)`

Đặt **quy tắc authorization bên trong một chuỗi đã được chọn**:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Request `/api/admin/report` được xét theo các rule của chuỗi API. Request `/admin/report` ở ngoài phạm vi `/api/**` **không được các rule này nhìn thấy**.

### Bảng đối chiếu

| Phương thức | Vai trò | Sai lầm thường gặp |
| --- | --- | --- |
| `securityMatcher("/api/**")` | Chọn **cả SecurityFilterChain** | Cho rằng `anyRequest` sau đó bảo vệ toàn bộ website |
| `requestMatchers("/api/public/**").permitAll()` | Cho phép một nhóm request **trong chain hiện tại** | Nhầm với việc bỏ qua filter hoàn toàn |
| `anyRequest().authenticated()` | Bảo vệ phần còn lại **đã vào chain** | Không bảo vệ request nằm ngoài `securityMatcher` |
| `anyRequest().denyAll()` | Từ chối phần còn lại **đã vào chain** | Không hoạt động nếu request không được chuỗi nào nhận |
| `web.ignoring().requestMatchers(...)` | Bỏ qua Spring Security web filter chain cho URL được chọn | Dùng với endpoint công khai trong khi muốn giữ security headers/CSRF-related infrastructure |

Một lời giải thích ngắn gọn: **`securityMatcher` là cổng vào chuỗi; `requestMatchers` là luật bên trong chuỗi.** Chúng không thay thế nhau.

## 4. `@Order` quyết định precedence, không quyết định quyền

Khi có nhiều `SecurityFilterChain` bean, `@Order` quyết định mức ưu tiên. Giá trị **nhỏ hơn** được xét trước:

```java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/admin/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().hasRole("ADMIN"))
            .build();
}
```

```java
@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
```

Hai đoạn riêng trên **chưa là project hoàn chỉnh**: cần cấu hình authentication mechanism, import và chuỗi dự phòng. Chúng minh họa ưu tiên.

Ví dụ sai:

```java
@Bean
@Order(1)
SecurityFilterChain permissiveFirst(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().permitAll())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain protectedApi(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
```

Chuỗi đầu **không giới hạn bằng `securityMatcher`**, nên mặc định khớp mọi request. `/api/orders` vào chuỗi đầu, được `permitAll`, chuỗi thứ hai không bao giờ tham gia. **Việc có một rule an toàn ở bean khác không cứu được endpoint.**

Cách sửa là giới hạn chuỗi hẹp đúng phạm vi, sắp xếp thứ tự, rồi thêm catch-all cuối:

```text
@Order(1): /admin/**
@Order(2): /api/**
@Order(3): mọi request còn lại -> denyAll
```

Nếu hai chain có matcher giao nhau như `/api/**` và `/api/admin/**`, hãy đặt `/api/admin/**` trước. Khi những matcher giao nhau mà không có điều khoản ưu tiên rõ, policy có thể thay đổi chỉ vì một lần refactor thứ tự bean.

**Không dựa vào thứ tự khai báo method trong file Java** để quyết định chọn chuỗi. Với cấu hình nhiều chain, khai báo `@Order` rõ ràng và có test chứng minh matching behavior.

## 5. Nguy cơ khi không có chuỗi fallback

Giả sử application chỉ khai báo:

```java
@Bean
@Order(1)
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Nếu ứng dụng cũng có controller:

```java
@GetMapping("/internal/export")
String export() {
    return "restricted";
}
```

Khi không có một chain khác khớp `/internal/export`, Spring Security web filters **không bảo vệ route đó**. Controller có thể trả dữ liệu trực tiếp khi được gọi. Đoạn controller chỉ là ví dụ rủi ro; không triển khai public như một API thật.

Một hiểu nhầm lớn: **“Spring Boot tự bổ sung SecurityFilterChain mặc định cho những URL chưa được chuỗi tự viết bảo vệ.”** Trong cấu hình Boot Servlet thường gặp, khi bạn đã cung cấp một `SecurityFilterChain` bean tùy chỉnh, auto-config mặc định tạo filter chain của Boot sẽ **back off**. Không nên trông chờ Boot tự lấp khoảng trống giữa các `securityMatcher` do bạn khai báo.

Đây là lý do nên có **fallback explicit** và test trực tiếp `/some-new-route` không nằm trong các đường dẫn dự kiến. Khi thêm route mới, kiểm thử bảo mật phải thất bại nếu route đó bị bỏ qua.

### Khi thiếu fallback, 404 không nói lên an toàn

Một request tới URL không có controller có thể trả `404 Not Found` kể cả khi Spring Security không hề được áp dụng. Nếu ngày mai developer bổ sung controller cho URL ấy, nó có thể bắt đầu trả 200 cho anonymous. Vì vậy kiểm thử an toàn cần route **thực sự tồn tại** hoặc một fallback được chứng minh là đã chọn; không xem 404 như bằng chứng filter hoạt động.

## 6. Cấu hình mẫu an toàn: chuỗi hẹp, fallback từ chối

Một kiến trúc dễ lý giải:

| Thứ tự | `securityMatcher` | Authorization bên trong | HTTP auth mechanism |
| --- | --- | --- | --- |
| 1 | `/admin/**` | Phải có `ROLE_ADMIN` | Basic demo |
| 2 | `/api/**` | `/api/public/status` public; `/api/reports` cần `ROLE_ANALYST`; phần còn lại deny | Basic demo |
| 3 | không giới hạn (catch-all) | `anyRequest().denyAll()` | Basic demo |

Các rule “deny all” được đặt ở **cuối mỗi chain** để route mới trong một chain không vô tình tự thành public, đồng thời catch-all cuối giúp mọi URL khác vẫn đi qua SecurityFilterChain.

Sơ đồ một số request:

```text
GET /admin/panel
    -> ADMIN chain
    -> ROLE_ADMIN required

GET /api/reports
    -> API chain
    -> ROLE_ANALYST required

GET /api/public/status
    -> API chain
    -> permitAll

GET /api/unknown
    -> API chain
    -> denyAll

GET /unlisted
    -> FALLBACK chain
    -> denyAll
```

Một URL công khai như `/api/public/status` vẫn đi qua filter chain và còn có thể chịu các filter/cơ chế bảo vệ khác. `permitAll` chỉ là **quyết định authorization** cho route đó, không phải bỏ hẳn Spring Security khỏi request.

## 7. Spring Boot 3.3.5 và Java 17: project thực hành

Ví dụ dùng **Spring MVC Servlet** với ba `SecurityFilterChain`, hai user test, HTTP Basic và các MockMvc tests. Đây là code để học **chain selection/authorization**, không phải cấu hình production:

- `User.withUsername(...)` lưu mật khẩu test có `{noop}`, không an toàn cho production.
- HTTP Basic dùng loopback local; khi ở mạng thật phải sử dụng HTTPS và credential management phù hợp.
- Các endpoint chỉ dùng GET để tránh làm nhiễu ví dụ bằng CSRF ở request thay đổi trạng thái.
- Mọi URL không được khai báo rõ bị từ chối; chỉ `/api/public/status` là public.

### 7.1. Cấu trúc dự án

```text
chain-routing-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/chain/
    │   │   ├── ChainRoutingApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/demo/chain/
        └── ChainRoutingTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

Project cần Gradle wrapper tương thích Java 17. Nếu chưa có wrapper, cài Gradle và tạo wrapper theo quy trình build của bạn; đừng coi chỉ có `build.gradle` là tự có executable `gradlew`.

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Chỉ bind loopback trong demo, tránh đưa password test hoặc HTTP Basic không TLS ra mạng công khai.

### 7.2. Lớp chạy ứng dụng

Tạo `src/main/java/demo/chain/ChainRoutingApplication.java`:

```java
package demo.chain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainRoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainRoutingApplication.class, args);
    }
}
```

### 7.3. Ba SecurityFilterChain rõ ràng, có fallback

Tạo `src/main/java/demo/chain/SecurityConfig.java`:

```java
package demo.chain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("ANALYST")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}demo-only")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/admin/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("ADMIN"))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public/status")
                                .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/reports")
                                .hasRole("ANALYST")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Giải thích từng điểm:**

1. `adminChain` chỉ tham gia request thuộc `/admin/**`; tất cả request trong đó cần `ROLE_ADMIN`.
2. `apiChain` chỉ tham gia `/api/**`; `/api/public/status` public và `/api/reports` cần `ROLE_ANALYST`.
3. `anyRequest().denyAll()` trong API ngăn developer vô tình thêm endpoint `/api/new-secret` rồi tự xem nó là protected chỉ vì nằm trong API chain.
4. `fallbackChain` **không có** `.securityMatcher(...)`: theo cấu hình này, nó nhận mọi request chưa được hai chain trước chọn. Đặt cuối bằng `@Order(3)`.
5. `httpBasic()` tạo authentication mechanism trong mỗi chain. Nếu chain nào chỉ có rule authorization mà không có cách xác thực, lỗi 401/403 có thể khác kỳ vọng; trong ví dụ từng chain có HTTP Basic để không bỏ qua vấn đề đó.
6. `SessionCreationPolicy.STATELESS` giúp demo không phụ thuộc vào session lưu authentication từ request trước. Không đồng nghĩa HTTP Basic tự dùng HTTPS.
7. `.roles("ADMIN")` tạo authority `ROLE_ADMIN`. `hasRole("ADMIN")` theo convention kiểm authority có tiền tố `ROLE_`.
8. Spring Boot dùng các bean `SecurityFilterChain` tự khai báo; ta tự chịu trách nhiệm bảo đảm có fallback. **Không đợi Boot tạo chain thứ tư.**

Trong production, thông thường API resource server sẽ dùng bearer token thay vì HTTP Basic; nhưng nguyên lý chain matching và `@Order` không đổi. Một chuỗi dành cho browser/OAuth2 login có thể yêu cầu `formLogin`/`oauth2Login`, trong khi chuỗi API dùng resource server; vẫn phải có thiết kế fallback rõ ràng.

### 7.4. Controller có route public và protected

Tạo `src/main/java/demo/chain/DemoController.java`:

```java
package demo.chain;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/status")
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(Principal principal) {
        return Map.of(
                "report", "quarterly",
                "requestedBy", principal.getName());
    }

    @GetMapping("/admin/panel")
    public Map<String, String> admin(Principal principal) {
        return Map.of(
                "panel", "admin",
                "requestedBy", principal.getName());
    }

    @GetMapping("/unlisted")
    public Map<String, String> unlisted() {
        // Có controller thật để chứng minh fallback từ chối.
        return Map.of("secret", "should-not-be-public");
    }
}
```

`/unlisted` cố ý tồn tại trong MVC nhưng **không được một chain chuyên biệt cho phép**. Nếu fallback thiếu, nó có thể đi thẳng đến controller; khi fallback tồn tại, request bị từ chối trước khi controller phản hồi. Mục đích duy nhất của route này là minh họa/test trong môi trường local; không để nội dung bí mật thật ở đây.

## 8. Kiểm thử với MockMvc qua SecurityFilterChain thật

Tạo `src/test/java/demo/chain/ChainRoutingTest.java`:

```java
package demo.chain;

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
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChainRoutingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiPublicStatusWorksWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void apiReportsRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void analystCanReadReports() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestedBy").value("alice"));
    }

    @Test
    void adminWithoutAnalystRoleCannotReadReports()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("bob", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminPanelRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin/panel"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanOpenAdminPanel() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("bob", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestedBy").value("bob"));
    }

    @Test
    void analystCannotOpenAdminPanel() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unlistedRouteRequiresProtectionEvenThoughItExists()
            throws Exception {
        mvc.perform(get("/unlisted"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedRouteRemainsDeniedAfterAuthentication()
            throws Exception {
        mvc.perform(get("/unlisted")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiRouteIsNotImplicitlyPermitted()
            throws Exception {
        mvc.perform(get("/api/unknown")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void incorrectCredentialsAreStillRejected() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("bob", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Test này dùng **HTTP Basic thực sự qua security filters**, không dùng `.with(user("..."))` để gắn sẵn principal và bỏ qua password check. `@SpringBootTest` + `@AutoConfigureMockMvc` nạp application context và filter chain, cho phép kiểm tra authorization chính xác hơn so với standalone MVC controller test.

**Kỳ vọng theo cấu hình demo:**

| Request | Kỳ vọng | Chain |
| --- | --- | --- |
| Anonymous `GET /api/public/status` | 200 | API |
| Anonymous `GET /api/reports` | 401 | API |
| `alice` GET `/api/reports` | 200 | API |
| `bob` GET `/api/reports` | 403 | API |
| Anonymous GET `/admin/panel` | 401 | ADMIN |
| `bob` GET `/admin/panel` | 200 | ADMIN |
| `alice` GET `/admin/panel` | 403 | ADMIN |
| Anonymous GET `/unlisted` | 401 | FALLBACK |
| `alice` GET `/unlisted` | 403 | FALLBACK |
| `alice` GET `/api/unknown` | 403 | API |

Bảng là **kỳ vọng từ cấu hình example**, không áp dụng như một chuẩn status cho mọi kiến trúc. `AuthenticationEntryPoint` có thể trả 302 khi dùng form login, hoặc response riêng khi dùng custom entry point. Ngoài ra CSRF, dispatcher type và thứ tự filter khác có thể ảnh hưởng kết quả.

## 9. Chạy HTTP trên loopback và đọc kết quả

Khởi động demo:

```bash
./gradlew bootRun
```

Thử endpoint công khai:

```bash
curl -i http://127.0.0.1:8080/api/public/status
```

Phản hồi thành công có HTTP 200 và body JSON tương đương:

```json
{"status":"ok"}
```

Đường API cần role:

```bash
curl -i http://127.0.0.1:8080/api/reports
```

Trong demo có HTTP Basic, không có credential hợp lệ thì thường là `401 Unauthorized`.

Gửi credential local của user `alice`:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/reports
```

Body JSON thành công tương đương:

```json
{
  "report": "quarterly",
  "requestedBy": "alice"
}
```

Gửi request tới route `/unlisted` có controller nhưng không được khai báo public:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/unlisted
```

Kỳ vọng `403 Forbidden`, **không có body chứa `secret`**, bởi fallback deny-all.

**Lưu ý bảo mật:** password và HTTP Basic trong ví dụ chỉ phục vụ local; không truyền credential qua HTTP public. Trong production dùng TLS, secret management và cơ chế xác thực hợp với loại client.

## 10. Ví dụ Java 17 độc lập minh họa “first match”

Phần này là **mô hình tư duy thuần Java**, không phải class Spring Security và không thay thế `FilterChainProxy`. Nó cho thấy tại sao một rule match-all đặt đầu danh sách sẽ che các rule phía sau.

Tạo file `FirstMatchDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class FirstMatchDemo {
    record Chain(String name, Predicate<String> matcher) {
        boolean matches(String path) {
            return matcher.test(path);
        }
    }

    static String selected(String path, List<Chain> chains) {
        return chains.stream()
                .filter(chain -> chain.matches(path))
                .map(Chain::name)
                .findFirst()
                .orElse("NONE");
    }

    public static void main(String[] args) {
        List<Chain> proper = List.of(
                new Chain("ADMIN", p -> p.startsWith("/admin/")),
                new Chain("API", p -> p.startsWith("/api/")),
                new Chain("FALLBACK", p -> true));

        for (String path : List.of(
                "/admin/panel", "/api/reports", "/unlisted")) {
            System.out.println(path + " -> " + selected(path, proper));
        }
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac --release 17 FirstMatchDemo.java
java FirstMatchDemo
```

Stdout **chính xác** của mô hình này:

```text
/admin/panel -> ADMIN
/api/reports -> API
/unlisted -> FALLBACK
```

Chỉ cần đặt `new Chain("MATCH_ALL", p -> true)` lên đầu `List.of(...)` là mọi path sẽ vào `MATCH_ALL` và các matcher đến sau không được chọn. Đây là mô hình minh họa **ưu tiên**, không mô phỏng đầy đủ URL matching của Servlet (context path, servlet path, encoding và các matcher trong Spring Security).

## 11. Lỗi điển hình A: `securityMatcher` hẹp hơn phạm vi thực tế

Ví dụ:

```java
http.securityMatcher("/api/v1/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
```

Nếu controller thực tế có thêm `/api/v2/orders`, endpoint v2 nằm ngoài chain v1. Nếu thiếu fallback, nó có thể bị bỏ lọt.

Cách xử lý:

1. Có **route inventory** của tất cả endpoint được deploy, không chỉ những URL test thủ công.
2. Quyết định route v2 phải được chuỗi API chung `/api/**` nhận hay có chuỗi `/api/v2/**` riêng.
3. Thêm negative tests cho anonymous và role không đủ quyền ở route v2.
4. Giữ fallback `denyAll` cho mọi đường dẫn không được phân loại.
5. Khi đổi prefix/version, coi đây là **thay đổi ranh giới bảo mật**, không chỉ sửa `@RequestMapping`.

Đừng chỉ đổi matcher thành `"/**"` ở một chain rất rộng rồi tự cho rằng đã sửa. Nếu chain rộng đứng trước admin chain, lại sinh **shadowing**.

## 12. Lỗi điển hình B: `@Order` sai làm chuỗi sau không bao giờ chạy

Giả sử:

```text
@Order(1) -> securityMatcher("/api/**")
             .anyRequest().authenticated()

@Order(2) -> securityMatcher("/api/admin/**")
             .anyRequest().hasRole("ADMIN")
```

`GET /api/admin/reports` đã khớp `"/api/**"` ở chuỗi đầu, nên nó **không được xét** trong chuỗi admin ở dưới. Kết quả có thể là user thường truy cập được endpoint admin dù bạn nhìn thấy `hasRole("ADMIN")` ở source.

Cách sửa:

```text
@Order(1) -> /api/admin/**  -> ROLE_ADMIN
@Order(2) -> /api/**        -> quyền API tương ứng
@Order(3) -> catch-all      -> denyAll
```

Hoặc gom logic vào **một chain** duy nhất và sắp thứ tự `requestMatchers("/api/admin/**")` trước rule rộng hơn. Hai cách đều hợp lý, tùy authentication mechanism và nhu cầu security filters khác nhau.

Khi nào nên tách chain?

- Khi `/api/**` dùng bearer token nhưng `/web/**` dùng session/form login.
- Khi một tập route yêu cầu filter/cơ chế xác thực đặc thù.
- Khi cần security filter chain riêng cho endpoint hệ thống.

Nếu chỉ khác **quy tắc quyền** mà vẫn cùng authentication mechanism, một chain với nhiều `requestMatchers` thường đơn giản hơn và tránh lỗi precedence giữa beans.

## 13. Lỗi điển hình C: không có fallback vì tin auto-config

Đoạn nguy hiểm:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
```

Nếu đây là chuỗi duy nhất, bất kỳ controller ngoài `/api/**` đều **nằm ngoài phạm vi SecurityFilterChain**. Trong nhiều cấu hình Boot, khai báo bean này làm Boot ngừng tạo default chain, nên không có “lớp bảo vệ ẩn” xuất hiện tự động.

Cách sửa nhỏ nhất theo ý tưởng:

```java
@Bean
@Order(100)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().denyAll())
            .build();
}
```

Đây là **đoạn rút gọn**; production phải quyết định authentication entry point, session/CSRF và semantics trả lỗi. Nó chứng minh phạm vi fallback: không đặt `.securityMatcher` để chain nhận mọi request còn lại.

**Cảnh báo:** fallback cũng phải đứng sau tất cả chain chuyên biệt; nếu để `@Order(0)` và bắt tất cả, nó sẽ từ chối hoặc xử lý mọi request trước các chain thiết kế riêng. Điều này tốt hơn là lộ dữ liệu nhưng vẫn là lỗi availability/chính sách.

## 14. `permitAll`, `denyAll` và `web.ignoring` không tương đương

Trong cùng chain:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().denyAll())
```

Route `/public/**` **vẫn đi qua** Spring Security web filters. Những filter như security headers, CSRF đối với các method liên quan, authentication processing hoặc logging có thể tiếp tục được áp dụng tùy cấu hình.

Ngược lại, dùng `WebSecurityCustomizer`:

```java
@Bean
WebSecurityCustomizer customizer() {
    return web -> web.ignoring()
            .requestMatchers("/assets/**");
}
```

Đây là đoạn minh họa cho tài nguyên tĩnh **chắc chắn** không cần security filters và phải có import `WebSecurityCustomizer`. Khi một URL bị cấu hình ignore, nó không được `FilterChainProxy` bảo vệ theo cách thông thường. **Không ignore URL có dữ liệu cá nhân, account, API session, OAuth2 callback hoặc chức năng ghi dữ liệu** chỉ vì muốn truy cập công khai.

Với một endpoint public bình thường, ưu tiên `.permitAll()` trong chain hơn là ignore toàn bộ. `denyAll` trong fallback tạo rào cản an toàn với route chưa phân loại; nhưng **không sửa được** việc một chuỗi đứng trước đã `permitAll()` quá rộng.

## 15. `SecurityFilterChain` và method-level security

Có trường hợp một endpoint bị bỏ ngoài web filter chain nhưng method bên trong có `@PreAuthorize`. Không nên xem điều đó như kiến trúc dự phòng an toàn cho mọi request.

Ví dụ:

```java
@PreAuthorize("hasRole('ADMIN')")
public Report internalReport() {
    // ...
}
```

Đây là method minh họa, chỉ hoạt động khi method security đã được bật và method được gọi qua Spring proxy phù hợp. Nó không bù cho việc:

- Những endpoint khác không có `@PreAuthorize`.
- `SecurityContext` chưa được thiết lập vì request không đi qua web filters.
- Filter bảo vệ CSRF/security headers/session/exception translation không chạy ở request.
- Method tự gọi trong cùng bean (*self-invocation*) bỏ qua proxy interception ở nhiều mô hình AOP.
- Security context bị gán không đúng loại authentication hoặc có dữ liệu từ thread cũ.

Web security và method security bổ sung cho nhau. Với Servlet HTTP endpoint, điểm khởi đầu nên là **mọi request thuộc chuỗi filter phù hợp** rồi mới đến quyền cấp method/object.

## 16. Phân tích đường dẫn: context path, servlet path và matcher

Một HTTP request có thể được nhìn qua:

- Request URI từ client.
- Context path của ứng dụng, ví dụ `/billing`.
- Servlet path nếu `DispatcherServlet` không map ở `/`.
- Path mapping của MVC controller, ví dụ `/api/reports`.
- Path thực tế sau rewrite bởi ingress/reverse proxy.

Ví dụ browser gọi:

```text
https://example.test/billing/api/reports
```

Nếu `/billing` là **context path**, matching của Spring Security có thể dựa trên các thành phần request đã được container tách ra. Không nên giả định `securityMatcher("/billing/api/**")` khớp chỉ vì browser thấy URL có `/billing`; cần hiểu matcher implementation và cấu hình servlet/context path.

Tương tự, nếu ingress rewrite `/portal/api/*` thành `/api/*` trước khi backend nhận request, backend có thể chỉ thấy `/api/reports`. Việc đặt matcher theo **đường dẫn public trước rewrite** có thể làm chain không khớp.

Những điểm thực hành:

1. Dùng URL/path nhất quán giữa `@RequestMapping`, `securityMatcher`, `requestMatchers` và reverse proxy.
2. Nếu có nhiều servlet hoặc custom servlet path, xác định matcher đang dùng Servlet path hay MVC path. Với Spring MVC có thể cần `MvcRequestMatcher`/builder hoặc API matcher tương ứng phiên bản; phải kiểm tra semantics trên đúng stack.
3. Với encoded slash, duplicate slash, trailing slash hoặc path normalization, tránh tự viết kiểm tra bằng `startsWith` mà không hiểu container.
4. Dùng test ở mức ứng dụng thật với context-path/servlet-path đã cấu hình, không chỉ MockMvc mặc định `/`.
5. Khi cập nhật framework, matcher implementation hoặc path pattern strategy có thể đổi, cần chạy lại test coverage.

Không quyết định bảo mật dựa trên một phép so prefix string thủ công trong interceptor nếu framework đã cung cấp RequestMatcher chính thức.

## 17. Khi có `DispatcherType.FORWARD`, `ERROR`, `ASYNC`

Servlet hỗ trợ các **dispatcher types** như `REQUEST`, `FORWARD`, `ERROR`, `ASYNC`. Một số request error hoặc async redispatch có thể được bảo vệ/đánh giá lại tùy filter registration và rule.

Ví dụ ứng dụng trả `404` rồi chuyển đến `/error`; nếu fallback deny-all áp dụng cả error dispatch mà chưa thiết kế exception handling, response cuối có thể bị biến thành `403` làm bạn tưởng endpoint chính bị thiếu quyền.

Có thể cần cho phép các dispatcher nội bộ phù hợp trong **authorization rule của đúng chain**, ví dụ:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
    .anyRequest().denyAll())
```

Đây là **đoạn minh họa**, cần import `jakarta.servlet.DispatcherType`; chỉ cho phép dispatcher type khi bạn hiểu rõ topology và policy. Không đưa một rule permit-all quá rộng lên đầu rồi xem toàn bộ external request là an toàn. Đừng dùng dispatcher allowance để vô tình mở một endpoint thực sự cần authentication.

Với async Servlet, phải bảo đảm security context và request lifecycle phù hợp; không tự suy rằng mỗi redispatch tạo một authentication mới hoặc áp lại toàn bộ filter theo cùng thứ tự.

**Khi debug một 404 bị biến thành 403**, kiểm tra dispatcher type và chain đang chạy, không xóa fallback deny-all chỉ để thấy lại 404.

## 18. CORS preflight, CSRF và HTTP method matching

Nếu API có CORS, browser có thể gửi request **OPTIONS preflight** không kèm credential user. Chỉ kiểm tra `GET /api/reports` không đủ để kết luận các request OPTIONS/POST được xử lý đúng.

Các lưu ý:

- CORS nên được cấu hình phù hợp với Spring Security để preflight không bị authentication filter từ chối sai; nhưng **preflight được phép** không có nghĩa request chính có quyền truy cập.
- `requestMatchers(HttpMethod.GET, "/api/reports")` chỉ áp dụng với GET. POST/PATCH trên cùng path có thể đi vào `anyRequest().denyAll()`, đây là chủ đích trong demo.
- Với session cookie, Spring Security CSRF protection vẫn quan trọng cho request thay đổi trạng thái. Đừng `.csrf().disable()` trên toàn app chỉ vì test POST nhận 403.
- Cấu hình `securityMatcher("/api/**")` không làm `/v2/api/**` hoặc WebSocket handshake endpoint ngoài prefix tự động được bảo vệ.
- Nếu một client có credential không hợp lệ ở route `permitAll`, authentication filter có thể vẫn phản ứng với Authorization header sai; `permitAll` không phải lệnh bỏ qua authentication filters.

Có thể đặt một chuỗi công khai riêng cho CORS/static assets khi thật sự cần filter policy khác. Nhưng mỗi chuỗi mới là một **bề mặt cần được kiểm thử precedence**, không phải một đường tắt miễn phí.

## 19. OAuth2, JWT Resource Server và nhiều cơ chế xác thực

Nhiều ứng dụng tích hợp:

```text
/admin/**   -> HTTP session / form login
/api/**     -> OAuth2 Resource Server JWT
/oauth2/**  -> OAuth2 Client login callback
/actuator/**-> management policy
fallback    -> denyAll
```

Chú ý cấu hình chain:

1. Nếu `/api/**` chỉ bật `.oauth2ResourceServer().jwt()`, nó **không có nghĩa** các URL ngoài API được xác thực bằng JWT.
2. Nếu chuỗi form login chỉ `securityMatcher("/web/**")`, các endpoint login/callback `/login`, `/oauth2/authorization/*`, `/login/oauth2/code/*` có thể nằm ngoài chain. Filter cung cấp endpoint cần nằm trong phạm vi chuỗi hoặc cần cấu hình endpoint URL phù hợp.
3. Một `oauth2Login()` bean có mặt trong source **không bảo đảm** request callback đi vào đúng chain.
4. Đừng để fallback permit-all trong lúc thử nghiệm rồi quên đổi ở production.
5. Với management/actuator endpoints ở một port riêng, phải kiểm security configuration của management context/port, không suy ra bằng requestMatchers của app chính.
6. JWT `SCOPE_*` và role `ROLE_*` có cách mapping khác nhau; quyền sai trong chain có thể gây 403, khác hoàn toàn với việc **không có chain**.

Nếu authentication mechanism khác nhau đáng kể, tách SecurityFilterChain là hợp lý. Tuy vậy mỗi filter-created endpoint (login, logout, callback, `/error`) đều cần xuất hiện trong bài test route coverage.

## 20. Actuator, tài nguyên tĩnh và endpoint do framework cung cấp

Route inventory chỉ liệt kê `@RestController` của dự án **không đủ**. Endpoint còn có thể đến từ:

- Spring Boot Actuator (nếu dependency được thêm).
- Login/logout/OAuth2 callback do Security filters tạo.
- Spring MVC error controller (`/error`) và dispatcher nội bộ.
- Static resources (`/assets/**`, `/css/**`, `/webjars/**`).
- Framework-generated endpoints, thư viện bên thứ ba hoặc servlet khác.
- WebSocket handshake/SSE endpoint.
- Endpoint được bật qua feature flag, profile hoặc deployment config.

Một số endpoint có thể **không tồn tại** ở môi trường test nhưng **được bật** ở staging/production (actuator exposure, profile-specific bean). Kịch bản không được bỏ qua là route mới được register sau khi security config đã chốt.

Với Actuator chạy **cùng port** có thể cần matcher chuyên biệt; với Actuator trên management port/context khác, cần kiểm tra security của management server. Không tự suy rằng fallback trên app chính bảo vệ mọi service/port.

Tài nguyên static thật sự public có thể `permitAll`; route phục vụ file từ user upload hoặc private report **không** nên được gom chung vào `/assets/**` public chỉ vì có dạng file.

## 21. Chẩn đoán theo log và FilterChainProxy

Khi nghi một request không được bảo vệ, cần chứng minh **request có đi vào SecurityFilterChain nào không**.

### 21.1. Bật log trong môi trường kiểm soát

Cấu hình debug tạm thời:

```yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security.web.access: DEBUG
```

Thực tế tên logger, thông điệp và mức độ chi tiết phụ thuộc phiên bản Spring Security. Hãy quan sát xem `FilterChainProxy` đã cố match những chain nào, có chọn chain nào, và quyết định authorization xảy ra ở đâu.

**Không bật TRACE toàn hệ thống lâu dài trên production** nếu log có thể chứa thông tin request nhạy cảm hoặc làm tăng chi phí/độ trễ. Che log credentials, tokens, cookies và identity assertions. Với hệ thống dùng nhiều chain, có thể log matcher/selected chain ở mức cấu hình kiểm toán có giới hạn.

### 21.2. Phân biệt ba trường hợp

| Quan sát | Khả năng | Hành động |
| --- | --- | --- |
| `FilterChainProxy` không chọn chain nào | Missing fallback hoặc URL nằm ngoài mọi securityMatcher | Bổ sung catch-all phù hợp và test endpoint thật |
| Request vào chain khác mong đợi | Sai `@Order` hoặc matcher quá rộng | Thu hẹp/đổi thứ tự chain, thêm overlap tests |
| Đúng chain nhưng 200 dù không có role | `permitAll`/rule rộng đứng trước, authority mapping sai hoặc method security chưa bật | Xem rules bên trong chain, test người không đủ quyền |
| Đúng chain nhưng 401 | Authentication chưa có/credential sai/entry point | Kiểm provider, filter và HTTP auth mechanism |
| Đúng chain nhưng 403 | Đã authenticated thiếu quyền, CSRF hoặc policy khác | Kiểm `GrantedAuthority`, CSRF, method/object rules |
| 404 với URL mới | Route chưa tồn tại hoặc không có chain | Dùng route có thật để kiểm coverage; 404 không chứng minh security |
| 302 về `/login` sai URL | Chain dùng form login/entry point hoặc callback không nằm trong chain | Kiểm matching các endpoint do filter tạo |
| 403 sau `/error` dispatch | Fallback deny-all cho ERROR/FORWARD | Kiểm dispatcher types, policy error path |

Đừng kết luận “có security rồi” chỉ vì một request có token trả 200. Test quan trọng nhất là **request không token**, **request có token nhưng thiếu quyền**, và **route ngoài mọi prefix dự kiến**.

## 22. Quy trình tìm và sửa endpoint bỏ lọt

Có thể dùng một quy trình chẩn đoán có thể lặp lại:

1. **Ghi lại URL thật** ở mức Servlet: method, request URI, context path, servlet path, dispatcher type và host/port public. Không log credential.
2. **Liệt kê các SecurityFilterChain đang được tạo** trong cùng Spring application context, order và matcher. Nếu có management context riêng, kiểm độc lập.
3. **Xác định chain đầu tiên match request.** Không chỉ tìm chain “nào có chứa rule `hasRole`”.
4. **Kiểm tra authorization rules** trong chain được chọn theo đúng thứ tự `requestMatchers`, HTTP method và authority.
5. **Kiểm tra authentication mechanism** tương ứng: HTTP Basic/form login/JWT/OIDC, entry point và session policy. Một endpoint trả 401 chưa đủ chứng minh đúng cơ chế.
6. **Xác minh có fallback** và nó đứng sau các chain chuyên biệt; tập URL mới chưa phân loại phải bị từ chối.
7. **Viết test regression** trên route thật, có anonymous, user không đủ quyền và user được phép. Tạo một endpoint test ngoài prefix để chứng minh catch-all.
8. **Test thêm path rewrites, context/servlet path và dispatcher ERROR/ASYNC** khi hệ thống có dùng.
9. **Không chữa bằng `permitAll` rộng**, web ignoring hoặc xóa toàn bộ matcher; phải cập nhật matchers theo kiến trúc đúng.
10. **Triển khai và theo dõi** auth denials, số request không có chain, 3xx/401/403, đồng thời bảo đảm logs không lộ dữ liệu nhạy cảm.

Nếu một incident đã có dữ liệu lộ ra, chỉ sửa matcher là chưa đủ: cần đánh giá phạm vi truy cập trái phép, audit, rotation credentials khi liên quan và các bước ứng phó theo chính sách của tổ chức.

## 23. Bẫy trong bài test và code review

### MockMvc không tích hợp Spring Security

Nếu dùng:

```java
MockMvcBuilders.standaloneSetup(controller).build();
```

đây là **đoạn khởi tạo MockMvc không tự đính kèm SecurityFilterChain**. Controller có thể trả 200 dù ứng dụng thật có security. Để test cấu hình bảo mật, ưu tiên `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc:

```java
MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
```

Đoạn `webAppContextSetup` là **snippet trong setup test**, yêu cầu imports và context Spring MVC phù hợp. Không để standalone test trả 200 rồi kết luận route production bị bỏ lọt; ngược lại, không dựa vào controller-only test để chứng minh route an toàn.

### Test dùng `.with(user("admin"))`

Spring Security Test `user(...)` gắn sẵn identity, không test credential thật. Nó phù hợp kiểm authorization nhưng không chứng minh JWT/Basic authentication đã hoạt động. Khi sửa một lỗi chain selection, cần test request **không có authentication**, kết hợp request với authentication thật phù hợp và có quyền sai.

### Một route sai có thể không hiện diện ở CI

Nếu route chỉ tồn tại theo `@Profile("prod")` hoặc feature flag, CI mặc định không thể kiểm coverage. Cần có test/application context đại diện cho cấu hình triển khai, hoặc dùng inventory/contract test có so sánh route và policy.

### Mặc định bỏ qua HTTP method

Security matcher theo path có thể chọn mọi method; rule `requestMatchers(HttpMethod.GET,...)` chỉ cho GET. Khi viết chính sách cho POST/PATCH/DELETE, test cả method và CSRF. Không cho `OPTIONS /** permitAll` tràn qua các route ngoài phạm vi cần thiết.

## 24. Kịch bản kiểm thử chống regression

Một bộ regression đáng có ngoài happy path:

| Kịch bản | Yêu cầu |
| --- | --- |
| Anonymous GET `/api/reports` | Không thấy báo cáo |
| Admin user không có ANALYST GET `/api/reports` | Bị từ chối |
| Analyst GET `/admin/panel` | Bị từ chối |
| Anonymous GET `/unlisted` **có controller thật** | Bị từ chối bởi fallback |
| Authenticated GET `/unlisted` | Bị deny-all |
| Authenticated GET `/api/new-secret` | Bị deny-all cho đến khi có policy |
| Route `/api/admin/secret` có hai matcher overlap | Chuỗi hẹp/role mạnh được chọn trước |
| Đổi `@Order` của API và ADMIN | Regression test thất bại nếu quyền bị hạ |
| Login/callback/`/error` | Có chain/dispatcher handling đúng theo UX |
| URL với context path/prefix từ ingress | Khớp chain mong đợi |
| API thêm version mới | Không bypass khi URL không còn bắt đầu `/api/` |
| Management/actuator port riêng | Kiểm riêng security của port đó |

Không bắt buộc trả status cụ thể như 401 cho mọi ứng dụng; status phụ thuộc entry point/form login. Điều quan trọng là **bảo vệ có hiệu lực**, principal/authority đúng và không tiết lộ dữ liệu.

## 25. Checklist review trước production

- Có danh sách toàn bộ Servlet/MVC/framework endpoints đã expose, kể cả URL do filter tạo.
- Mỗi endpoint có policy public/private/role/permission/tenant rõ ràng.
- Các `SecurityFilterChain` có `@Order` tường minh và được kiểm tra theo **first-match**.
- Chuỗi hẹp ưu tiên trước chuỗi rộng nếu các matcher có thể giao nhau.
- Không có catch-all `permitAll()` đứng trước chain bảo vệ.
- Mỗi chain giới hạn bằng `securityMatcher` đúng phạm vi hoặc cố ý khớp mọi request.
- Bên trong chain, `requestMatchers` sắp từ cụ thể tới tổng quát và kết thúc bằng `anyRequest` có chủ đích.
- Có **fallback** catch-all đứng cuối, ưu tiên deny-all khi route chưa phân loại.
- Không nhầm `web.ignoring` với `permitAll`; chỉ ignore static resources thực sự phù hợp.
- CORS, CSRF, ERROR/FORWARD/ASYNC dispatch và HTTP methods được xử lý phù hợp.
- Authentication mechanism tồn tại ở chain cần nó; login/logout/callback không bị securityMatcher loại trừ.
- Context path, servlet path, proxy rewrites và URL versioning được kiểm tra trong tests.
- Method security bổ sung chứ không thay thế web filter coverage.
- Với Actuator/management port riêng, có kiểm tra cấu hình bảo mật độc lập.
- Có MockMvc/integration tests cho anonymous, sai quyền, đúng quyền, unlisted route thật và overlap.
- Log/trace tạm thời đủ giúp thấy chain nào được chọn mà không lộ token/password.
- Mọi thay đổi matcher hoặc thứ tự chain được code review như thay đổi chính sách bảo mật.

## Ghi nhớ

Spring Security Servlet chọn **SecurityFilterChain đầu tiên có matcher khớp**. `securityMatcher` quyết định request **có vào chuỗi hay không**; `requestMatchers` quyết định **quyền bên trong chuỗi đã chọn**; `@Order` quyết định **chuỗi nào được thử trước**. Nếu không có chain nào khớp, Spring Security web filters có thể **bị bỏ qua hoàn toàn**. Khi khai báo custom SecurityFilterChain, không trông chờ Boot tự sinh thêm một default chain để bảo vệ phần còn lại. Hãy đặt chain chuyên biệt trước, có **fallback deny-all** cuối cùng, và chứng minh bằng test trên **endpoint có thật** rằng cả anonymous lẫn user không đủ quyền đều không thể đi vòng qua bảo mật.