# Endpoint nằm ngoài mọi SecurityFilterChain: lỗ hổng bao phủ đường dẫn trong Spring Security

## 1. Bài toán và kết quả học tập

Trong một ứng dụng Spring MVC dùng **Spring Security (Servlet)**, lập trình viên có thể viết `anyRequest().authenticated()` hoặc `anyRequest().denyAll()` rồi tin rằng mọi endpoint đã được bảo vệ. Niềm tin đó sai nếu câu lệnh chỉ thuộc một `SecurityFilterChain` có phạm vi hẹp: một request **không khớp bất kỳ chain nào** sẽ không đi qua các security filter của chain, kể cả bộ lọc phân quyền.

Ví dụ: ứng dụng khai báo một chain cho `/api/**`, nhưng lại có endpoint `GET /admin/export`. Nếu không có chain dự phòng và không có biện pháp bảo vệ độc lập khác, `/admin/export` có thể được gọi trực tiếp dù chưa đăng nhập.

Mục tiêu của bài:
1. Giải thích cơ chế `DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain` và cách chọn chain đầu tiên khớp request.
2. Phân biệt **request nằm ngoài mọi chain**, **request vào chain và được `permitAll`**, **request vào chain bị `denyAll`**, và **request bị `web.ignoring()` loại khỏi bộ lọc**.
3. Tái hiện lỗi, khắc phục bằng chain cuối bao phủ toàn bộ request, rồi dùng unit-style coverage test và `MockMvc` để xác minh cả phạm vi lẫn hành vi HTTP.
4. Xây dựng checklist phòng ngừa khi thêm endpoint mới, đổi matcher, cấu hình nhiều chain và triển khai ứng dụng.

**Phạm vi:** Spring Security Servlet (Spring MVC, `HttpSecurity`, `SecurityFilterChain`). WebFlux sử dụng `SecurityWebFilterChain` và `ServerHttpSecurity` với cơ chế khác; không trộn hai API. Ví dụ chạy trên Java 17+, Spring Boot 3.3.x/Spring Security 6.3.x; nguyên lý và DSL cốt lõi cũng áp dụng cho Spring Security 6.5.

## 2. Spring Security chọn chain như thế nào?

### 2.1. Hai bước độc lập: chọn chain rồi mới quyết định quyền

~~~text
HTTP request
    │
    ▼
Servlet filter chain của container
    │
    ▼
DelegatingFilterProxy ("springSecurityFilterChain")
    │
    ▼
FilterChainProxy
    │  duyệt các SecurityFilterChain theo thứ tự
    ├── chain @Order(1), matcher "/api/**" ? ── khớp ──→ filter của chain API
    │
    ├── chain @Order(2), matcher "/admin/**" ? ─ khớp ──→ filter của chain admin
    │
    └── chain mặc định, matcher "mọi request" ? ─ khớp ──→ filter của fallback
          │
          └── không chain nào khớp → không thực thi security filters của chain
                                        │
                                        ▼
                                 các filter còn lại / MVC
~~~

`FilterChainProxy` xét các `SecurityFilterChain` theo thứ tự và **chọn chain đầu tiên khớp**. Nó không cộng dồn các chain để thực thi toàn bộ filter của mọi chain. Khi không có chain nào khớp, quy tắc phân quyền trong các chain không được chạy. Controller vẫn có thể nhận request vì servlet container và Spring MVC là các tầng riêng.

Một `HttpSecurity` thường có matcher mặc định khớp mọi request. Khi gọi `http.securityMatcher("/api/**")`, bạn **thay đổi phạm vi của toàn bộ chain** thành `/api/**`. Quy tắc `anyRequest()` ở bên trong chỉ áp dụng cho tập request đã vượt qua matcher ngoài đó.

### 2.2. So sánh các loại matcher và quyết định

| Cấu hình | Tác dụng | Với `GET /admin/export` khi chain chỉ nhận `/api/**` |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Chọn request **được xét bởi toàn chain** | Chain không khớp, bỏ qua chain này |
| `authorizeHttpRequests(a -> a.requestMatchers("/api/admin").hasRole("ADMIN"))` | Phân quyền **bên trong chain đã được chọn** | Không có tác dụng đối với `/admin/export` |
| `authorizeHttpRequests(a -> a.anyRequest().denyAll())` | Từ chối các request còn lại **trong chain đó** | Không biến một chain `/api/**` thành catch-all |
| Chain cuối **không gọi `securityMatcher(...)`** | Giữ matcher mặc định là mọi request | Có cơ hội xử lý những request chưa khớp chain đứng trước |
| `web.ignoring().requestMatchers(...)` | Cấu hình bypass các security filter cho đường dẫn tương ứng | Đây là cách bỏ qua filter có chủ đích, khác với matcher gap |

**Lưu ý bảo mật:** `permitAll()` có nghĩa endpoint được cho phép **bởi luật authorization trong một chain**, trong khi các security filter liên quan vẫn có thể chạy (chẳng hạn HTTP security headers). `web.ignoring()` và chain không khớp làm request không có các filter ấy. Không dùng `permitAll()` làm lý do bỏ qua việc kiểm tra chain coverage.

### 2.3. Chain nào chịu trách nhiệm?

Giả sử có:
- Chain A: `@Order(1)`, `securityMatcher("/api/**")`.
- Chain B: `@Order(2)`, `securityMatcher("/admin/**")`.
- Chain C: không `@Order`, không `securityMatcher` (catch-all).

`GET /api/profile` vào A; `GET /admin/export` vào B; `GET /public/ping` vào C. Nếu bỏ C, `/public/ping` không thuộc chain nào. Nếu chỉ có A mà lại khai báo `anyRequest().denyAll()` trong A, `/admin/export` vẫn nằm ngoài mọi chain. Nếu đặt catch-all trước A, mọi request có thể bị catch-all bắt trước, khiến A không có cơ hội xử lý. Cấu hình thứ tự quan trọng ngang với phạm vi matcher.

## 3. Lỗ hổng xuất hiện trong thực tế

### 3.1. Cấu hình lỗi: một chain hẹp, không có fallback

Đoạn sau chỉ nhằm tái hiện lỗi trong môi trường học tập; **không triển khai** như cấu hình bảo mật ứng dụng thật.

~~~java
// Trích đoạn SecurityConfiguration sai: chỉ bảo vệ /api/**.
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
// Không có SecurityFilterChain nào bao phủ /admin/** hoặc các URL khác.
~~~

Bảng diễn giải:

| Request | Chain `/api/**` có khớp? | Kết quả nếu không còn chính sách khác |
| --- | --- | --- |
| `GET /api/profile`, chưa đăng nhập | Có | Bị yêu cầu xác thực (HTTP Basic thường trả 401) |
| `GET /admin/export`, chưa đăng nhập | Không | Có thể chạy controller và trả 200 |
| `GET /public/ping` | Không | Có thể chạy controller |
| `GET /does-not-exist` | Không | MVC có thể trả 404, nhưng 404 **không chứng minh** request được bảo vệ |

Khi bạn tự khai báo `SecurityFilterChain`, không nên giả định Spring Boot sẽ tự tạo thêm một fallback chain bảo vệ mọi URL. Chính sách bao phủ URL còn lại là trách nhiệm của cấu hình security thực tế.

### 3.2. Hậu quả và giới hạn kết luận

Endpoint bỏ lọt có thể bị gọi không cần HTTP authentication/authorization của Spring Security; các filter như `AuthorizationFilter`, `SecurityContextHolderFilter`, `CsrfFilter` hoặc `HeaderWriterFilter` của chain cũng không chạy cho request đó. Tác động cụ thể phụ thuộc method, tài nguyên, cấu hình filter và nghiệp vụ: có thể dẫn đến lộ dữ liệu, thao tác quản trị không được kiểm soát hoặc thiếu security headers.

**Không đồng nhất với “mọi bảo vệ của ứng dụng biến mất”.** Những filter ở ngoài `FilterChainProxy`, kiểm tra nghiệp vụ, xác thực tại gateway, và method security (nếu bật) có thể vẫn can thiệp. `FilterChainProxy` cũng có lớp `HttpFirewall` xử lý request trước lúc chọn filters. Khẳng định chính xác là: request **không nhận bảo vệ từ các filter của `SecurityFilterChain`**, vì không chain nào được chọn. Bài demo cố ý không thêm bảo vệ độc lập để quan sát lỗ hổng rõ ràng.

### 3.3. Nguyên nhân thường gặp

1. **Chỉ định `securityMatcher` quá hẹp:** bảo vệ `/api/**` nhưng quên `/admin/**`, `/actuator/**` hoặc endpoint mới dưới `/internal/**`.
2. **Thiếu catch-all:** tự thêm một hoặc nhiều chain chuyên biệt và không đăng ký chain cuối không giới hạn matcher.
3. **Hiểu sai `anyRequest`:** cho rằng `anyRequest().authenticated()/denyAll()` áp dụng toàn ứng dụng, dù chain có `securityMatcher`.
4. **`web.ignoring()` phạm vi rộng:** ví dụ bỏ qua `/admin/**` hoặc `/**`; đây là một bypass filter tường minh.
5. **Chuyển URL, servlet mapping, context path, HTTP method hoặc dispatcher type:** matcher thực tế không giống dự đoán, đặc biệt khi có nhiều servlet hoặc phân phối request nội bộ.
6. **Thứ tự chain:** catch-all đứng trước chain chuyên biệt khiến chain chuyên biệt bị che khuất. Đây là lỗi chọn **sai chain**, không phải “không khớp chain nào”; cả hai đều cần test.
7. **Nhiều cổng/management context:** endpoint quản trị có thể chạy trên cổng hoặc application context khác; cần kiểm tra bảo vệ ở đúng nơi endpoint được triển khai.

## 4. Cấu hình đúng: chain chuyên biệt cộng fallback bao phủ toàn bộ

Chiến lược an toàn trong ví dụ: chain `/api/**` yêu cầu đăng nhập; chain cuối không gọi `securityMatcher`, cho phép đúng `/public/ping`, yêu cầu vai trò ADMIN đối với `/admin/**` và **deny by default** với đường dẫn khác. Chỉ cho phép công khai các URL thực sự cần công khai.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    // Không khai báo securityMatcher => xử lý mọi request còn lại.
    @Bean
    SecurityFilterChain catchAllChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Trong code trên:
- `@Order(1)` làm chain API được thử trước.
- Bean `catchAllChain` không có `@Order`, chạy sau chain đã sắp thứ tự và có matcher mặc định khớp mọi request.
- `requestMatchers("/public/ping").permitAll()` là public access có chủ đích **trong security chain**.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; người dùng chỉ có `ROLE_USER` bị từ chối.
- `anyRequest().denyAll()` trong fallback giúp URL lạ bị chặn. Nếu sản phẩm cần nguyên tắc “mặc định phải đăng nhập”, có thể thay bằng `authenticated()` sau khi đã phân loại các route, nhưng kiểm tra sự đầy đủ của chính sách vẫn cần thiết.

**Lưu ý kiến trúc:** ví dụ đơn giản bật HTTP Basic cho cả hai chain để kết quả 401 dễ quan sát. Ứng dụng thật có thể dùng bearer token, session, OAuth2 Resource Server hoặc login form; lựa chọn cơ chế xác thực không thay đổi quy tắc bao phủ chain. Với nhiều servlet hoặc management context riêng, xác định matcher bằng request thực tế tương ứng; không suy đoán từ chuỗi URL của một servlet khác.

## 5. Ví dụ chạy được: Spring Boot + Spring Security + MockMvc

### 5.1. Project thử nghiệm

Tạo một Spring Boot Servlet project nhỏ (Java 17+, Gradle 8.5+, Spring Boot 3.3.x). Các file sau đặt đúng đường dẫn, phần ví dụ Java được tách thành các file độc lập. Project này chỉ phục vụ thử nghiệm; dữ liệu controller là giá trị giả lập.

File `settings.gradle`:

~~~groovy
rootProject.name = 'security-chain-gap'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    sourceCompatibility = JavaVersion.VERSION_17
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

Dùng Gradle wrapper tương thích với plugin Spring Boot đã khai báo. Các lệnh sau giả định project có `gradlew` và `gradlew.bat`; nếu tạo project bằng Spring Initializr, wrapper thường đã có sẵn. Phần mã không yêu cầu database hoặc dịch vụ authentication thật.

### 5.2. Ứng dụng và các endpoint

File `src/main/java/example/chaingap/ChainGapApplication.java`:

~~~java
package example.chaingap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainGapApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainGapApplication.class, args);
    }
}
~~~

File `src/main/java/example/chaingap/DemoController.java`:

~~~java
package example.chaingap;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DemoController {

    @GetMapping("/api/profile")
    String profile() {
        return "api-profile";
    }

    @GetMapping("/admin/export")
    String exportData() {
        return "admin-data";
    }

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }
}
~~~

File `src/main/java/example/chaingap/SecurityConfiguration.java` — **cấu hình đã sửa**:

~~~java
package example.chaingap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain catchAllChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### 5.3. Test chặn lỗ hổng ở hai mức: chain coverage và HTTP behavior

File `src/test/java/example/chaingap/SecurityCoverageTest.java`:

~~~java
package example.chaingap;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityCoverageTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy filterChainProxy;

    private SecurityFilterChain selectedChain(String path) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        request.setServletPath(path);

        return filterChainProxy.getFilterChains().stream()
                .filter(chain -> chain.matches(request))
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "No SecurityFilterChain matches GET " + path));
    }

    @Test
    void everyDeclaredEndpointHasAnAuthorizationFilter() {
        for (String path : List.of(
                "/api/profile", "/admin/export", "/public/ping")) {
            SecurityFilterChain chain = selectedChain(path);
            assertTrue(
                    chain.getFilters().stream()
                            .anyMatch(AuthorizationFilter.class::isInstance),
                    () -> "Missing AuthorizationFilter for GET " + path);
        }
    }

    @Test
    void apiRejectsAnonymousRequest() throws Exception {
        mvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAllowsAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/profile").with(user("alice")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-profile"));
    }

    @Test
    void adminRejectsAnonymousRequest() throws Exception {
        mvc.perform(get("/admin/export"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRejectsAuthenticatedNonAdmin() throws Exception {
        mvc.perform(get("/admin/export")
                        .with(user("viewer").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminAllowsAdmin() throws Exception {
        mvc.perform(get("/admin/export")
                        .with(user("operator").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-data"));
    }

    @Test
    void publicPingStaysPublicInsideFallbackChain() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

**Vì sao cần hai loại test?**

- `selectedChain(...)` truy cập danh sách chain và tìm chain **đầu tiên khớp** request mô phỏng; nếu không có chain, test thất bại tại `orElseThrow`. Kiểm tra tiếp `AuthorizationFilter` vì **một chain có thể tồn tại nhưng không chứa bộ lọc phân quyền**. Assertion này dành cho cấu hình mẫu dùng `authorizeHttpRequests`; hệ thống dùng bộ lọc phân quyền khác cần điều chỉnh assertion phù hợp.
- `MockMvc` gửi request theo lộ trình MVC và Spring Security được cấu hình thực tế. Assertion về status và body kiểm tra **quyền truy cập hữu hiệu**, không chỉ chuỗi matcher. `with(user(...))` đến từ `spring-security-test`; không cần tài khoản người dùng thật cho fixture.
- Test thứ nhất chỉ bao phủ các route đã liệt kê. Một endpoint mới không tự xuất hiện trong danh sách ấy; trong production cần giữ danh mục endpoint/test hoặc một kiểm tra tổng quát cập nhật theo API routing.

Chạy:

~~~bash
./gradlew test --tests 'example.chaingap.SecurityCoverageTest'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.chaingap.SecurityCoverageTest"
~~~

**Kỳ vọng:** 7 test thành công với cấu hình đã sửa; Gradle/JUnit có thể trình bày summary khác nhau nên không gán một chuỗi stdout giả định.

### 5.4. Tự tái hiện lỗ hổng trước khi sửa

Chỉ trong bản demo cục bộ, **tạm xóa toàn bộ bean `catchAllChain`**, giữ nguyên bean `apiChain`; không sửa thêm controller hay test. Sau đó chạy lại lệnh test:

- `everyDeclaredEndpointHasAnAuthorizationFilter` thất bại vì `GET /admin/export` và `GET /public/ping` không có chain khớp.
- `adminRejectsAnonymousRequest` không đạt: demo trả 200 kèm `admin-data` dù expected 401.
- `adminRejectsAuthenticatedNonAdmin` không đạt: demo trả 200 thay cho 403.
- `publicPingStaysPublicInsideFallbackChain` có thể vẫn trả 200, **nhưng việc trả 200 không chứng minh request đã đi qua chain**. Đó là lý do cần assertion chọn chain.

Khôi phục bean `catchAllChain` và chạy lại: test phải trở về trạng thái pass. Cách tái hiện bằng việc bỏ bean cho thấy rõ cấu hình nào khiến endpoint rơi khỏi lớp bảo vệ.

Có thể quan sát trực tiếp khi chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

~~~bash
curl -i http://localhost:8080/api/profile
curl -i http://localhost:8080/admin/export
curl -i http://localhost:8080/public/ping
~~~

Trên cấu hình **đúng**: `/api/profile` và `/admin/export` trả 401 cho anonymous, `/public/ping` trả 200 với body `pong`. Với cấu hình **lỗi chỉ có `/api/**`**, `/admin/export` trong demo trả 200 với body `admin-data`. Đây là kết quả dự kiến từ chính fixture, không phải kết luận chung cho mọi ứng dụng có thêm gateway, method security hoặc filter khác.

## 6. Chẩn đoán khi endpoint bị nghi nằm ngoài chain

### Bước 1 — Xác định request thực tế

Ghi lại **HTTP method, URL, servlet path, context path, dispatcher type và cổng**. URL bên ngoài reverse proxy có thể khác servlet path mà matcher nhìn thấy. Kiểm tra endpoint được đăng ký ở Spring MVC hay ở management application context. Không căn cứ vào tên controller/method để suy ra URL chắc chắn.

### Bước 2 — Liệt kê mọi chain theo đúng thứ tự

Tìm tất cả `@Bean SecurityFilterChain` và `WebSecurityCustomizer`, đọc `@Order` cùng `securityMatcher`. Xét từng request cụ thể: chain đầu tiên khớp là gì? Có chain cuối không giới hạn phạm vi hay không? `anyRequest` chỉ có ý nghĩa trong chain đã được chọn.

Có thể bật log cục bộ bằng `src/main/resources/application.properties`:

~~~properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Thông thường log lúc khởi động cho biết chain bảo vệ pattern nào và chứa những filter nào; log TRACE có thể thể hiện quá trình thử từng matcher và thông báo **No security for ...** khi không có filter áp dụng. Mẫu log chính xác thay đổi theo phiên bản. Tắt trace sau khi chẩn đoán, tránh ghi thông tin nhạy cảm vào production log.

### Bước 3 — Phân biệt “không khớp chain” và “bị bỏ qua có chủ đích”

| Quan sát | Khả năng | Cách xác minh |
| --- | --- | --- |
| Không chain nào `matches(request)` | Matcher gap thật sự | `getFilterChains()` + request chính xác; test HTTP |
| Một chain khớp nhưng `getFilters()` rỗng | Có thể là bypass/ignoring | Xem `WebSecurityCustomizer`, log và nội dung filters |
| Chain có `AuthorizationFilter`, rule `permitAll` | Public route được phân quyền cho phép | Test header/filter behavior và rule mong muốn |
| Chain có `AuthorizationFilter`, rule deny | Endpoint phải bị chặn theo rule | Test 401/403 với anonymous và từng quyền |
| Chain khớp nhưng chính sách sai | Sai authorization trong chain, không phải chain gap | Xem order `requestMatchers`, authority, principal |

`FilterChainProxy#getFilters(String)` chỉ là helper tiện lợi cho việc kiểm tra; khi matcher phụ thuộc servlet mapping, phương thức HTTP hoặc thuộc tính request, chuỗi URL không đủ. Ưu tiên kiểm tra bằng `MockMvc` và/hoặc một request mô phỏng phản ánh đúng servlet path/method, như test trên.

### Bước 4 — Kiểm tra hành vi, không chỉ status

Kiểm thử cả anonymous, user thường và user đủ quyền. Quan sát side effect: export dữ liệu, ghi DB, gọi dịch vụ ngoài. `403` hoặc `401` không tự chứng minh đã chọn đúng chain: gateway hoặc cơ chế khác cũng có thể từ chối; cần quan sát chain và cấu hình. Tương tự, `404` không chứng minh một URL an toàn: đó có thể chỉ là endpoint không tồn tại.

### Bước 5 — Chốt chính sách bao phủ

Đảm bảo mỗi endpoint thuộc ít nhất một chain phù hợp, được áp đúng authorization policy, có kiểm thử hồi quy và sở hữu rõ ràng. Đừng chỉ làm hết cảnh báo bằng cách `permitAll("/**")`. Fallback nên là `denyAll` hoặc `authenticated` theo yêu cầu đã duyệt của ứng dụng, ngoại lệ public khai báo tường minh.

## 7. Các bẫy cần tránh

1. **Chỉ đặt `.anyRequest().authenticated()` bên trong chain hẹp.** Đây không phải catch-all; phải có một chain thứ hai không giới hạn matcher.
2. **Cho rằng cứ khai báo `@EnableWebSecurity` là mọi URL chắc chắn được bảo vệ.** Cấu hình thực tế của tất cả `SecurityFilterChain` quyết định phạm vi.
3. **Dùng `web.ignoring()` cho endpoint động hoặc sensitive.** Nếu một URL phải công khai, thường dùng `permitAll` trong chain để vẫn có security headers và các filter cần thiết.
4. **Đặt chain dự phòng sai thứ tự.** `FilterChainProxy` chỉ dùng chain khớp đầu tiên; catch-all phải đứng sau các chain chuyên biệt.
5. **Không kiểm tra dispatcher type và servlet mapping.** Test GET thành công không đại diện cho POST, ERROR, FORWARD, URL có context path khác hoặc servlet khác.
6. **Dựa duy nhất vào HTTP status 200/401/403.** Kết hợp assertion chọn chain, filter có hiệu lực và quyền nghiệp vụ. Bảo vệ độc lập khác có thể che giấu chain gap.
7. **Kiểm thử mỗi endpoint đã biết rồi dừng.** Endpoint mới có thể được thêm sau đó; cập nhật security coverage test trong cùng thay đổi với route.
8. **Khẳng định mọi filter biến mất khi không match.** Chỉ security filter của `SecurityFilterChain` không chạy; container filters, `HttpFirewall` trong `FilterChainProxy` và cơ chế khác cần được xem xét riêng.
9. **Cấu hình security riêng cho management port rồi bỏ qua nó.** Nếu quản trị chạy ở context/cổng khác, xác minh đúng tập chain và endpoint quản trị ở đó.

## 8. Checklist áp dụng cho dự án thật

- [ ] Đã liệt kê toàn bộ `SecurityFilterChain`/`WebSecurityCustomizer` và thứ tự áp dụng.
- [ ] Có chain cuối bao phủ các request chưa khớp chain chuyên biệt, trừ trường hợp loại trừ đã được thiết kế và kiểm chứng riêng.
- [ ] `requestMatchers` trong từng chain đúng authority/policy; `anyRequest` không bị hiểu là toàn ứng dụng.
- [ ] Các route công khai dùng `permitAll` trong chain khi phù hợp, thay vì vô tình thiếu chain.
- [ ] Test anonymous / user thường / user đủ quyền cho URL nhạy cảm.
- [ ] Test xác minh route thuộc chain và chain có filter phân quyền cần thiết.
- [ ] Có test các biến thể HTTP method, servlet path, ERROR/FORWARD và cổng management khi chúng tồn tại.
- [ ] Có kiểm tra side effect ngoài status đối với endpoint thay đổi trạng thái.
- [ ] Security coverage test được cập nhật cùng lúc khi thêm hoặc đổi endpoint.
- [ ] Đã kiểm tra trên môi trường triển khai thực tế, nơi reverse proxy và base path có thể khác máy dev.

## 9. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): giải thích `securityMatcher`, thứ tự chain, matcher mặc định và hậu quả nếu không chain nào khớp.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `anyRequest`, `permitAll`, `denyAll`, khuyến nghị dùng `permitAll` thay vì ignoring.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, chuỗi security filters.
- [Spring Security 6.5 — MockMvc Test Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): cấu hình tích hợp Spring Security với Spring MVC test.
