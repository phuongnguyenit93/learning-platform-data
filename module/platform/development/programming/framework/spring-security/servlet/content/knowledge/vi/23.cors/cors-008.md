# CORS cho nhiều SecurityFilterChain và các nhóm endpoint khác nhau

## 1. Bài toán và kết quả cần đạt

Một ứng dụng Spring Boot 3.x / Spring Security 6.x trên **Servlet stack** có thể vừa phục vụ API công khai cho một website, vừa phục vụ API nội bộ cho website khác, vừa có giao diện MVC chạy cùng origin:

- **/api/catalog/**: được đọc bởi **https://catalog.example**, không mang credential.
- **/api/operations/**: được dùng bởi **https://console.example**, có authentication và quyền **OPERATOR**; CORS cho phép GET/POST từ origin này nhưng không tự bỏ qua CSRF.
- **/web/**: trang MVC truyền thống chạy cùng origin, không chủ ý mở cross-origin.

Mỗi nhóm cần policy khác nhau. Nếu CORS bị mở quá rộng, một origin chỉ được phép đọc catalog có thể nhận phản hồi chứa dữ liệu từ API nội bộ khi người dùng có credential. Nếu cấu hình CORS không được gọi ở chain xử lý OPTIONS, trình duyệt có thể báo lỗi preflight dù controller hoạt động bình thường qua curl.

**CORS (Cross-Origin Resource Sharing)** là quy tắc cho trình duyệt quyết định JavaScript từ origin này có thể đọc phản hồi của origin khác hay không. Origin gồm **scheme + hostname + port**: **https://console.example**, **http://console.example** và **https://console.example:8443** là ba origin khác nhau. CORS không cấp authentication/authorization; client server-to-server, curl hoặc Postman không thực thi hạn chế CORS của trình duyệt. CORS cũng không phải biện pháp thay thế CSRF.

Bài học tập trung vào cách đặt **SecurityFilterChain**, **securityMatcher**, **CorsConfigurationSource**, thứ tự chain và việc kiểm chứng cả preflight và actual request.

## 2. Hai tầng định tuyến: filter chain và CORS source

Spring Security dùng **FilterChainProxy** để tìm **SecurityFilterChain khớp đầu tiên** theo thứ tự. Mỗi request chỉ đi qua một security chain được chọn. **securityMatcher(...)** quyết định request thuộc chain nào; **requestMatchers(...)** bên trong **authorizeHttpRequests** chỉ đặt quy tắc phân quyền sau khi chain đã được chọn.

~~~text
Trình duyệt
  │
  ├── Preflight (nếu cần): OPTIONS /api/operations/tasks
  │   Origin: https://console.example
  │   Access-Control-Request-Method: POST
  │   Access-Control-Request-Headers: authorization,x-csrf-token
  │
  ▼
FilterChainProxy: chọn SecurityFilterChain KHỚP ĐẦU TIÊN
  │
  ├── /api/operations/**  → operationsChain (@Order 1)
  │                           → CORS policy cho console.example
  ├── /api/catalog/**     → catalogChain    (@Order 2)
  │                           → CORS policy cho catalog.example
  └── các path còn lại    → webChain        (@Order 3)
                              → không mở CORS
  │
  ▼
CorsFilter trong chain được chọn
  ├── Preflight hợp lệ: phản hồi CORS, kết thúc xử lý OPTIONS
  ├── Origin/method/header bị từ chối: thường HTTP 403
  └── Actual request hợp lệ: thêm CORS headers, tiếp tục
  │
  ▼
CSRF → Authentication → Authorization → Controller
~~~

Sơ đồ giản lược các filter nhưng giữ đúng thứ tự logic: **CORS phải được xử lý trước việc kiểm tra bảo mật cần credential**. Preflight không có đầy đủ cookie/credential như actual request nên nếu hệ thống buộc OPTIONS phải đăng nhập, trình duyệt có thể gặp 401/403/302. **http.cors(...)** giúp Spring Security đặt CORS filter đúng vị trí.

### Preflight khác actual request

| Loại | Request/response then chốt | Ý nghĩa |
| --- | --- | --- |
| Preflight | OPTIONS + **Origin**, **Access-Control-Request-Method**, đôi khi **Access-Control-Request-Headers** | Hỏi server có cho phép actual request cross-origin không; thường không cần login |
| Actual request | GET/POST với Origin và dữ liệu thật | Có thể được thêm **Access-Control-Allow-Origin**, nhưng vẫn phải qua authentication, authorization, CSRF |
| Trình duyệt | Kiểm tra response headers CORS | Chỉ cho JavaScript đọc phản hồi khi đáp ứng policy; không thay thế quyền phía server |

Không phải mọi cross-origin request đều có OPTIONS. Ví dụ GET đơn giản thường gửi thẳng actual request. Các request dùng **Authorization** header, **Content-Type: application/json**, hoặc phương thức như PUT/DELETE thường cần preflight theo quy tắc browser.

Một preflight nhận 200 chỉ chứng minh **CORS policy cho phép gửi request**. POST thật vẫn có thể bị 401 vì thiếu đăng nhập, 403 vì thiếu role hoặc 403 vì thiếu CSRF token.

## 3. Thiết kế rõ nhóm endpoint và thứ tự ưu tiên

| Security chain | Path | Allowed origins | Methods | Credentials | Quyền / CSRF |
| --- | --- | --- | --- | --- | --- |
| operationsChain | **/api/operations/** | **https://console.example** | GET, POST | **true** | role OPERATOR; CSRF bật |
| catalogChain | **/api/catalog/** | **https://catalog.example** | GET | **false** | đọc public |
| webChain | fallback | Không cấu hình cross-origin | — | theo phiên web | form login; CSRF bật |

Dùng **@Order(1)** và **@Order(2)** cho hai matcher hẹp; fallback **@Order(3)** không gọi securityMatcher, nên khớp các đường dẫn còn lại. Đặt fallback ở đầu sẽ khiến những chain sau không có cơ hội xử lý request.

Không chỉ actual method phải trúng chain: **preflight OPTIONS cũng phải trúng cùng chain**. Ví dụ, nếu dùng custom securityMatcher chỉ chấp nhận GET/POST, OPTIONS sẽ rơi sang fallback và có thể bị yêu cầu login. Matcher theo path cho cả OPTIONS lẫn actual request thường phù hợp hơn.

Nếu nhiều endpoint chia sẻ một mô hình authentication và authorization, không bắt buộc có nhiều chain. Có thể dùng một CorsConfigurationSource với nhiều **registerCorsConfiguration(pathPattern, policy)**. Chỉ tách chain khi có ranh giới bảo mật cần xử lý riêng; mỗi chain vẫn cần chính sách CORS nhất quán.

## 4. Ví dụ đầy đủ Spring Boot 3.x / Java 17+

Tại dự án Spring Boot có Gradle wrapper, cần các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tệp **src/main/java/com/example/corsgroups/CorsGroupsApplication.java**:

~~~java
package com.example.corsgroups;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsGroupsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsGroupsApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    @Order(1)
    SecurityFilterChain operationsChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/operations/**")
                .cors(cors -> cors.configurationSource(
                        sourceFor("/api/operations/**",
                                List.of("https://console.example"),
                                List.of("GET", "POST"),
                                List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"),
                                true)))
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("OPERATOR"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain catalogChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/catalog/**")
                .cors(cors -> cors.configurationSource(
                        sourceFor("/api/catalog/**",
                                List.of("https://catalog.example"),
                                List.of("GET"),
                                List.of("Content-Type"),
                                false)))
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().permitAll())
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    private CorsConfigurationSource sourceFor(
            String path,
            List<String> origins,
            List<String> methods,
            List<String> headers,
            boolean credentials) {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(origins);
        policy.setAllowedMethods(methods);
        policy.setAllowedHeaders(headers);
        policy.setAllowCredentials(credentials);
        policy.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration(path, policy);
        return source;
    }

    // Chỉ dùng cho demo local; thay bằng hệ thống danh tính thật.
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo-operator")
                        .password(encoder.encode("local-only-password"))
                        .roles("OPERATOR")
                        .build());
    }
}

@RestController
class ApiController {
    @GetMapping("/api/catalog/items")
    List<String> items() {
        return List.of("book", "pen");
    }

    @GetMapping("/api/operations/status")
    String status() {
        return "ready";
    }

    @PostMapping("/api/operations/tasks")
    String createTask() {
        return "created";
    }

    @GetMapping("/web/home")
    String home() {
        return "home";
    }
}
~~~

### Phân tích cấu hình

**(1) Mỗi chain chỉ định source riêng bằng cors.configurationSource(...).** Method **sourceFor** tạo **CorsConfiguration** rồi đăng ký theo đúng path với **UrlBasedCorsConfigurationSource**. Hai policy không bị trộn origin, method, header hoặc cờ credentials. Có hai lớp giới hạn: **securityMatcher** chọn chain, **registerCorsConfiguration** chọn policy theo path. Khi đổi đường dẫn cần cập nhật cả hai.

**(2) Operations nhận GET/POST từ một origin cụ thể.** **setAllowCredentials(true)** báo cho trình duyệt có thể cho phép request mang credential trong tình huống đáp ứng các điều kiện khác. Nếu dùng fetch cross-origin cần cấu hình **credentials** tương ứng ở client. Cookie cross-site còn phụ thuộc **SameSite**, **Secure**, domain và chính sách trình duyệt. Basic auth trong demo giúp dễ học, nhưng việc được browser nhớ/tự gửi Basic credential là lý do cần cân nhắc CSRF.

**(3) CORS không thay authorization.** Chain operations vẫn yêu cầu **ROLE_OPERATOR** trên actual request. Demo giữ CSRF bật: POST của người dùng đã đăng nhập nhưng không kèm CSRF token hợp lệ vẫn 403. Muốn frontend khác origin thực hiện POST bằng session/cookie/Basic cần thiết kế cách lấy/gửi CSRF token đúng với hệ thống thật. Không nên disable CSRF chỉ vì vừa cho phép một CORS origin.

**(4) Catalog chỉ có GET public.** CORS policy không cho phép POST cross-origin từ trình duyệt, nhưng server vẫn phải hạn chế method tại route và/hoặc authorization. Không coi CORS là tường lửa chặn curl/Postman hoặc backend khác gửi request.

**(5) Fallback không mở CORS.** Website cùng origin vẫn hoạt động với form login và CSRF mặc định. Một request Origin từ console.example tới **/web/home** không tự nhận CORS policy của operations.

**(6) Không dùng wildcard origin khi cho credentials.** **setAllowedOrigins(List.of("*"))** không phù hợp với **setAllowCredentials(true)** và sẽ bị Spring từ chối ở bước kiểm tra cấu hình. Dùng danh sách origin xác định hoặc allowedOriginPatterns được kiểm soát; tránh phản chiếu Origin tùy ý trong response.

**(7) Không thiết lập đồng thời nhiều nguồn CORS vô chủ.** Ứng dụng có thể có **WebMvcConfigurer.addCorsMappings**, **@CrossOrigin**, **CorsFilter** tự tạo hoặc reverse proxy thêm headers. Hãy thống nhất nơi xử lý CORS. Khi đã có nhiều **CorsConfigurationSource** hoặc nhiều chain, **cors.configurationSource(...)** giúp tránh phụ thuộc vào việc framework tự chọn source. Nếu nhiều tầng cùng thêm **Access-Control-Allow-Origin**, trình duyệt có thể từ chối vì header bị lặp.

## 5. Kiểm thử bằng MockMvc

Bài test dưới đây kiểm tra cả ranh giới giữa hai chain, preflight OPTIONS không cần login, actual request cần role và POST vẫn cần CSRF.

Tệp **src/test/java/com/example/corsgroups/CorsGroupsTest.java**:

~~~java
package com.example.corsgroups;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CorsGroupsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void catalogAcceptsItsOrigin() throws Exception {
        mvc.perform(get("/api/catalog/items")
                        .header(HttpHeaders.ORIGIN, "https://catalog.example"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://catalog.example"))
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS));
    }

    @Test
    void catalogRejectsConsoleOrigin() throws Exception {
        mvc.perform(get("/api/catalog/items")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isForbidden());
    }

    @Test
    void operationsPreflightRequiresNoLogin() throws Exception {
        mvc.perform(options("/api/operations/tasks")
                        .header(HttpHeaders.ORIGIN, "https://console.example")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                "authorization,x-csrf-token"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://console.example"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true"));
    }

    @Test
    void operationsPreflightRejectsCatalogOrigin() throws Exception {
        mvc.perform(options("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://catalog.example")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void operationsActualGetRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void operationsRejectsInsufficientRole() throws Exception {
        mvc.perform(get("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void operationsAllowsAuthorizedRead() throws Exception {
        mvc.perform(get("/api/operations/status")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void allowedOriginDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/operations/tasks")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void csrfTokenAllowsPost() throws Exception {
        mvc.perform(post("/api/operations/tasks")
                        .header(HttpHeaders.ORIGIN, "https://console.example")
                        .with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void webFallbackDoesNotAddCorsOrigin() throws Exception {
        mvc.perform(get("/web/home")
                        .header(HttpHeaders.ORIGIN, "https://console.example"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

Chạy từ gốc dự án bằng Gradle wrapper:

~~~bash
./gradlew test --tests com.example.corsgroups.CorsGroupsTest
~~~

Trên Windows, dùng **gradlew.bat** thay cho **./gradlew**. Với cấu hình mẫu, 10 kiểm thử kỳ vọng lần lượt là **200, 403, 200, 403, 401, 403, 200, 403, 200, 200**. **@WithMockUser** mô phỏng principal đã được xác thực; **with(csrf())** cung cấp CSRF token hợp lệ trong test, không phải phương thức cấp token cho production. Khi tích hợp thật, hãy kiểm tra thêm proxy, cookie, redirect, cấu hình servlet path và chính sách authentication ngoài demo.

### Kiểm tra request preflight độc lập

Khởi chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Gửi OPTIONS như trình duyệt:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/operations/tasks' \
  -H 'Origin: https://console.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,x-csrf-token'
~~~

Kỳ vọng **HTTP 200** cùng headers **Access-Control-Allow-Origin: https://console.example** và **Access-Control-Allow-Credentials: true**; không cần Basic authentication trong preflight. Điều này **không bảo đảm POST thật thành công**: POST vẫn phải có thông tin xác thực, role thích hợp và CSRF token. curl chỉ giúp quan sát response, không thực thi chính sách CORS của trình duyệt.

## 6. Sự cố phổ biến và cách truy ra nguyên nhân

| Triệu chứng | Kiểm tra | Cách sửa |
| --- | --- | --- |
| OPTIONS trả 401/302 | securityMatcher chỉ nhận actual method, fallback được chọn hoặc thiếu http.cors | Để preflight tới đúng chain và chạy CORS trước auth |
| OPTIONS trả 403 | Origin, method, **Access-Control-Request-Headers** không nằm trong policy | So sánh request thực với CorsConfiguration đúng nhóm |
| Origin của catalog đọc được operations | Matcher/policy chung quá rộng hoặc proxy sinh header | Giới hạn origin theo endpoint; test âm giữa các nhóm |
| Access-Control-Allow-Origin bị trùng | MVC config, Security CorsFilter, proxy đều thêm header | Chọn một nơi chịu trách nhiệm và bỏ cấu hình chồng chéo |
| Preflight 200 nhưng actual 401/403 | CORS hợp lệ, thiếu login/role/CSRF | Gỡ lỗi lớp bảo mật theo response thực |
| Có allow-credentials mà cookie không gửi | Cookie SameSite/Secure/domain hoặc fetch credentials chưa đúng | Kiểm tra cookie và request ở Network tab của browser |
| Browser lỗi CORS nhưng curl chạy | Curl không kiểm soát CORS; origin/port/redirect hoặc error response khác | So sánh cả preflight và actual request bằng browser Network |
| Các route mới bị fallback nuốt | Thứ tự @Order sai hoặc securityMatcher chồng nhau | Đặt matcher hẹp trước fallback; thêm test theo path |

Ngoài ra, CORS **không chặn CSRF**. Trình duyệt có thể gửi một số cross-origin request dù không cho JavaScript đọc phản hồi. JWT trong cookie vẫn có nguy cơ CSRF; API bearer-token được gắn thủ công trong Authorization header có đánh giá rủi ro khác. Đánh giá CSRF dựa trên **cách credential được gửi**, không dựa vào tên gọi REST/API. HTTP Basic được browser ghi nhớ cũng có thể là credential tự gửi.

Không nên dùng path rộng **/** hay allowed origin **\*** làm giải pháp tạm để mọi preflight đều qua. Với environment khác nhau cần ghi rõ scheme, hostname, port, context-path, mapping của DispatcherServlet, gateway và filter bổ sung. Nếu sử dụng nhiều chain và MVC CORS, kiểm tra thực tế **chain nào được chọn trước** khi kết luận lỗi nằm ở controller.

## 7. Checklist để tự rà soát thiết kế

1. Đường dẫn và HTTP method thực thuộc nhóm nào? Có securityMatcher nào đứng trước vô tình bắt mất request?
2. Preflight OPTIONS có được chọn vào đúng chain của actual request không?
3. CorsConfigurationSource của chain ấy đăng ký đúng pattern, origin, method, headers và credentials chưa?
4. Một origin được phép ở nhóm A có chắc chắn **không được thừa hưởng** policy của nhóm B?
5. Actual request vẫn bắt buộc có authentication, role và CSRF khi cần chứ?
6. Đã kiểm thử cả **được phép** lẫn **bị từ chối**, gồm request thiếu credential, sai role, thiếu CSRF và origin không được phép chưa?
7. Có proxy, MVC config hay CorsFilter bổ sung nào gây header trùng hoặc đổi hành vi ở production không?

Một ví dụ diễn giải chuẩn: **OPTIONS /api/operations/tasks** từ **https://console.example** đi vào **operationsChain**, được CORS chấp nhận trước authentication; **POST /api/operations/tasks** vẫn phải có role OPERATOR và CSRF token; Origin **https://catalog.example** bị từ chối bởi CORS của operations. **GET /api/catalog/items** từ catalog.example được đọc công khai, còn đường dẫn **/web/** tiếp tục dùng chính sách web cùng origin.
