# HttpSecurity, Lambda DSL và bước build một SecurityFilterChain

Khi cấu hình bảo mật cho **Spring MVC trên Servlet stack**, một trong những đoạn code quan trọng nhất là bean trả về `SecurityFilterChain`, được xây dựng bằng `HttpSecurity` và **Lambda DSL**. Hiểu đoạn code này giúp trả lời các câu hỏi rất thực tế: request nào được áp dụng chính sách nào, vì sao người gọi được vào hoặc bị chặn, điều gì xảy ra khi gọi `build()`, và vì sao một rule trông đúng nhưng endpoint vẫn trả 401/403.

Bài học sử dụng Java 17+, Spring Boot 3.3.x và Spring Security 6.x làm bối cảnh cho ví dụ. Các nguyên tắc về cấu hình Servlet, matcher, authentication và authorization cần được phân biệt rõ trước khi học các tính năng khác như OAuth2, JWT hoặc method security.

**Mục tiêu sau bài:**

- Biết `HttpSecurity` là **builder cấu hình** của một chuỗi security filter, không phải đối tượng trực tiếp xử lý từng HTTP request.
- Đọc và viết được Lambda DSL, hiểu vai trò của lambda tham số, `Customizer.withDefaults()` và `build()`.
- Phân biệt điều kiện **chọn SecurityFilterChain** với các **quy tắc phân quyền bên trong chain**.
- Giải thích trình tự khởi tạo bean tại startup và trình tự xử lý một request lúc runtime.
- Tạo cấu hình thực thi được, test các nhánh public, authenticated, authority/role và CSRF, sau đó chẩn đoán lỗi phổ biến.

## 1. Bức tranh tổng thể: từ HTTP request đến SecurityFilterChain

Ứng dụng Servlet nhận HTTP request qua Servlet container (ví dụ Tomcat). Trước khi `DispatcherServlet` và controller của Spring MVC xử lý, request đi qua chuỗi `Filter`. Spring Security tích hợp ở tầng này: `DelegatingFilterProxy` chuyển việc xử lý đến bean `springSecurityFilterChain`, thường là `FilterChainProxy`. Thành phần đó chọn một `SecurityFilterChain` tương ứng request và gọi các security filter theo thứ tự mà framework xây dựng.

~~~text
Client -> Servlet container
       -> DelegatingFilterProxy
       -> FilterChainProxy
          -> chọn SecurityFilterChain khớp request
          -> security filters (context, authentication, CSRF, authorization, ...)
       -> DispatcherServlet -> Controller -> Response
~~~

Nếu security filter từ chối request, controller có thể **không được chạy**. Kết quả 401, 403 hoặc redirect phụ thuộc vào cơ chế xác thực, entry point và chính sách được cấu hình. Cùng một URL có thể trả 200 khi credentials hợp lệ, 401 khi thiếu credentials và 403 khi đã đăng nhập nhưng không có quyền.

**Hai thời điểm cần tách bạch:**

1. **Startup/configuration:** Spring tạo bean `SecurityFilterChain`; phương thức bean sử dụng `HttpSecurity` để **cấu hình và build một chuỗi filter**.
2. **Runtime/request:** `FilterChainProxy` chọn chain phù hợp rồi các filter được xây dựng ở startup mới thực sự xử lý request.

Mỗi request **không chạy lại** đoạn `http.authorizeHttpRequests(...).httpBasic(...).build()`. Không đặt logic phụ thuộc request cụ thể trực tiếp vào phương thức xây dựng bean như thể phương thức này là controller.

### Các thành phần có trách nhiệm khác nhau

| Thành phần | Vai trò | Điều không nên nhầm |
| --- | --- | --- |
| `HttpSecurity` | Builder cấu hình web security Servlet; lắp các configurer/filter và shared objects | Không phải filter trực tiếp nhận HTTP request |
| `SecurityFilterChain` | Tập security filter và điều kiện matcher cho request | Không phải chuỗi rule authorization đơn thuần |
| `FilterChainProxy` | Chọn chain và áp dụng các filter cho request | Không được tạo riêng cho mỗi request |
| `authorizeHttpRequests` | Cấu hình điều kiện cấp quyền HTTP | Không tự quyết định chain nào được chọn |
| `securityMatcher` | Giới hạn phạm vi request của một `HttpSecurity`/chain | Khác `requestMatchers` trong authorization |
| `Authentication` | Danh tính và authorities đang có | Không đồng nghĩa tự động có đủ quyền |
| `AuthorizationFilter` | Áp dụng chính sách truy cập mà cấu hình tạo ra | Không trực tiếp xác thực mật khẩu |

Với Spring Boot Servlet thông dụng, thêm `spring-boot-starter-security` và khai báo một bean `SecurityFilterChain` là cách đặt chính sách web security rõ ràng. Nếu ứng dụng không khai báo bean phù hợp, Boot có thể cung cấp chain mặc định; khi người dùng tự khai báo bean `SecurityFilterChain`, chính sách web security mặc định đó thường sẽ nhường chỗ cho cấu hình của ứng dụng. Đừng suy luận rằng mọi project có cùng chain/filter vì dependencies và cấu hình có thể khác nhau.

## 2. `HttpSecurity` thực sự cấu hình những gì?

Trong Spring Security Servlet, `HttpSecurity` là một builder được Spring Security cung cấp để định nghĩa chính sách cho một chain. Nó kết hợp các **configurer** để tạo các filter và thành phần được dùng trong quá trình xử lý request.

Ví dụ ngắn (đây là **đoạn cấu hình minh họa**, cần đặt trong class `@Configuration` và có import tương ứng):

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đọc theo ý nghĩa, không chỉ theo cú pháp:

1. `http` là builder do framework cung cấp trong lúc tạo bean.
2. `authorizeHttpRequests(...)` thêm cấu hình **authorization cho URL**.
3. Lambda `authorize -> ...` nhận đối tượng configurer để đăng ký các matcher và quyết định tương ứng.
4. `requestMatchers("/public/**").permitAll()` quy định request khớp matcher được phép đi tiếp theo chính sách này.
5. `requestMatchers("/admin/**").hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` theo quy ước mặc định.
6. `anyRequest().authenticated()` là rule dự phòng, dành cho request chưa khớp các rule phía trước.
7. `httpBasic(Customizer.withDefaults())` bật cơ chế HTTP Basic với các cấu hình mặc định áp dụng trong ngữ cảnh.
8. `build()` hoàn tất builder và trả về `SecurityFilterChain`. Bean này sau đó được hạ tầng security sử dụng; `build()` không tự gọi controller.

**Một bean SecurityFilterChain có thể bao gồm nhiều loại cấu hình:** xác thực HTTP Basic/form login/resource server, authorization, CSRF, session, exception handling, headers, CORS và filter bổ sung. Chỉ cấu hình những gì phù hợp với cơ chế bảo mật của ứng dụng; không coi mọi configurer đều cần phải xuất hiện trong mỗi bean.

## 3. Lambda DSL: cách đọc cho đúng

Lambda DSL là phong cách cấu hình dùng callback để nhóm các lựa chọn theo trách nhiệm. Cách viết này rõ vị trí rule và tránh phụ thuộc vào các chuỗi gọi `.and()` kiểu cũ.

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
~~~

Tại `authorizeHttpRequests(auth -> auth...)`, tham số `auth` **không phải Authentication hiện tại**. Nó là đối tượng builder/configurer để khai báo authorization. Người viết có thể đặt tên `authorize`, `rules` hay `requests` tùy ý; đó chỉ là biến lambda.

Một số mẫu thường gặp:

~~~java
// Đưa các lựa chọn cụ thể vào lambda:
http.csrf(csrf -> csrf.disable());

// Chấp nhận cấu hình mặc định của configurer:
http.httpBasic(Customizer.withDefaults());

// Định nghĩa rule và thứ tự xử lý:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/health").permitAll()
    .anyRequest().authenticated());
~~~

Ba đoạn này **chỉ minh họa cú pháp**, không phải gợi ý tắt CSRF mặc định. `csrf(csrf -> csrf.disable())` tắt bảo vệ CSRF trong chain liên quan; cần đánh giá cơ chế xác thực/cookie/session và threat model trước khi sử dụng ở môi trường thật.

### Phân biệt ba phong cách

| Viết trong dự án | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `http.httpBasic(Customizer.withDefaults())` | Bật configurer Basic với thiết lập mặc định | Cách dùng ngắn gọn khi không cần tùy chỉnh |
| `http.httpBasic(basic -> basic.realmName("demo"))` | Truyền callback tùy chỉnh HTTP Basic | Có thể dùng cùng các configurer khác |
| `http.authorizeHttpRequests(auth -> auth...)` | Khai báo nhiều authorization rule | Rule được xét theo thứ tự |
| `http.build()` | Tạo ra chain từ cấu hình hiện tại | Gọi ở cuối phương thức bean |
| Kiểu cấu hình dùng `.and()`/`antMatchers()` cũ | Hay gặp trong tài liệu Spring Security 5 | Không sao chép nguyên xi vào Spring Security 6 |

Khi migrate lên Spring Security 6, thường phải thay `authorizeRequests/antMatchers` bằng `authorizeHttpRequests/requestMatchers` phù hợp. Đồng thời nhiều cấu hình bắt buộc/khuyến khích phong cách lambda ở các phiên bản mới; kiểm tra API tại phiên bản dự án đang dùng. Không tự động thay tất cả matcher bằng một chuỗi path khi project có yêu cầu method, servlet path hoặc matcher tùy biến.

## 4. Ba loại “khớp” khác nhau: securityMatcher, requestMatchers, controller

Một nguồn lỗi rất phổ biến là thấy cùng tên “matcher” rồi nghĩ chúng làm một việc.

### 4.1. `securityMatcher(...)`: chọn phạm vi một security chain

Ví dụ:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
~~~

`securityMatcher("/api/**")` có nghĩa chain đang xây dựng chỉ dành cho các request khớp `/api/**`. Nếu request không khớp matcher này, `FilterChainProxy` xem chain tiếp theo (nếu có). Không được giả định rule `anyRequest()` trong chain này bảo vệ toàn bộ application: `anyRequest()` chỉ bao phủ request **đã được chọn vào chain**.

Nếu project chỉ khai báo chain giới hạn `/api/**` mà **không có chain phù hợp cho những URL khác**, các request còn lại có thể không được Spring Security bảo vệ. Do đó, khi có nhiều chain, phải kiểm tra toàn bộ matcher và fallback chain.

### 4.2. `requestMatchers(...)` trong `authorizeHttpRequests`: chọn rule trong chain

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports").hasAuthority("REPORT_READ")
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated());
~~~

Phân biệt method rõ ràng: GET `/api/reports` cần `REPORT_READ`, nhưng POST cùng URL không tự động dùng rule GET này và có thể rơi vào rule phía sau. Cả authorization và CSRF (nếu phù hợp) đều có thể ảnh hưởng đến kết quả. Với chính sách giới hạn theo method, hãy thử các method còn lại để tránh lỗ hổng.

Rule được áp dụng theo **thứ tự khai báo**; đặt matcher rộng phía trước có thể khiến rule phía sau không bao giờ tới lượt. `anyRequest()` nên ở cuối danh sách rule.

### 4.3. Mapping của controller là bước sau khi request đi qua security

Controller có thể định nghĩa:

~~~java
@GetMapping("/api/reports")
String reports() {
    return "report";
}
~~~

Controller mapping xác định handler MVC nào chạy, **không phải rule bảo mật**. Khi controller không có mapping cho request, kết quả 404 hoặc 405 có thể xuất hiện sau khi security đã cho phép request đi tiếp. Ngược lại, một URL chưa có handler vẫn có thể bị security từ chối trước.

### Bảng đối chiếu nhanh

| Câu hỏi | Nơi kiểm tra |
| --- | --- |
| Request có vào chain A hay chain B? | `securityMatcher`, `@Order` và thứ tự chain |
| Trong chain đó, được phép hay bị từ chối? | `authorizeHttpRequests` và authorities |
| Credentials được xử lý bằng gì? | `httpBasic`, `formLogin`, resource server hoặc bộ lọc tùy biến |
| Một POST bị 403 vì sao? | Authorization **và** cấu hình CSRF |
| Request được controller nào xử lý? | MVC mapping; kiểm tra sau bước security |

## 5. Bước `build()`: từ DSL thành SecurityFilterChain

Quá trình tạo bean có thể hiểu theo các bước sau:

~~~text
Ứng dụng tạo Spring ApplicationContext
    |
    v
Spring Security cung cấp HttpSecurity builder
    |
    v
@Configuration/@Bean thực thi
    |
    +--> gọi configurer: authorizeHttpRequests, httpBasic, csrf...
    +--> ghi nhận matcher, shared objects và cấu hình filter
    |
    v
http.build()
    |
    v
SecurityFilterChain (matcher + các filter đã được tạo/ghép)
    |
    v
SecurityFilterChain được hạ tầng Spring Security thu nhận
    |
    v
FilterChainProxy chọn chain tại runtime cho mỗi request
~~~

Nói chính xác hơn, `HttpSecurity` triển khai cơ chế builder của Spring Security. Khi gọi `build()`, framework thực hiện các bước khởi tạo và cấu hình nội bộ, rồi xây dựng `DefaultSecurityFilterChain`. Cấu trúc chi tiết và các filter cụ thể phụ thuộc phiên bản và configurer đang dùng.

**Điều được quyết định tại build time:** matcher cấp chain, filter nào tồn tại, chính sách AuthorizationManager, phương thức authentication và exception handling.

**Điều được quyết định tại request time:** request hiện tại khớp matcher nào, credentials cụ thể, Authentication được thiết lập, authorities, CSRF token, kết quả đánh giá authorization và response.

Một đoạn code dùng `http.build()` hai lần trên cùng builder **không phải cách tạo hai chain độc lập**. Với hai bean chain, thông thường mỗi phương thức bean nhận builder riêng do framework cung cấp và build một lần. Không lưu một `HttpSecurity` singleton để chia sẻ rồi sửa cấu hình đồng thời trong runtime.

### Khi nào nên khai báo `SecurityFilterChain` bean?

Với Spring Boot Servlet, khai báo bean để:

- Mô tả rõ endpoint nào public, cần đăng nhập hay cần quyền.
- Chọn cơ chế xác thực phù hợp thay vì vô tình dựa vào mặc định.
- Quy định behavior cho CSRF/session/logout/exception handling theo nhu cầu.
- Tách nhiều chính sách theo nhóm request bằng nhiều chain nếu cần.

Khi đã có bean custom, phải kiểm tra đủ các phần bạn cần: Boot không tự chèn toàn bộ rule `permitAll/authenticated` hoặc `httpBasic/formLogin` của cấu hình mặc định vào mọi bean do ứng dụng định nghĩa.

## 6. Ví dụ chạy được: một chain với HTTP Basic và Lambda DSL

Ví dụ này dùng **Java 17, Spring Boot 3.3.5, Gradle, Spring MVC và Spring Security**. Nó có public endpoint, endpoint yêu cầu đăng nhập, endpoint yêu cầu authority, endpoint yêu cầu role và POST chịu bảo vệ CSRF. Không cần cơ sở dữ liệu; ba tài khoản trong bộ nhớ chỉ dùng cho môi trường học.

### 6.1. Cấu trúc project

~~~text
http-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/security/
    │       ├── HttpSecurityDemoApplication.java
    │       ├── SecurityConfiguration.java
    │       └── DemoController.java
    └── test/
        └── java/demo/security/
            └── SecurityConfigurationTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'http-security-demo'
~~~

Tệp `build.gradle`:

~~~groovy
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
~~~

BOM tương ứng Spring Boot quản lý phiên bản Spring Security; không tự cố định phiên bản riêng cho `spring-security-web` hoặc `spring-security-config` khi chưa có lý do tương thích. Trong dự án thực có thể dùng wrapper và version catalog sẵn có thay vì tạo project mới.

### 6.2. Entry point của ứng dụng

Tệp `src/main/java/demo/security/HttpSecurityDemoApplication.java`:

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpSecurityDemoApplication.class, args);
    }
}
~~~

### 6.3. Cấu hình SecurityFilterChain bằng lambda

Tệp `src/main/java/demo/security/SecurityConfiguration.java`:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode("analyst-pass"))
            .authorities("REPORT_READ")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, analyst, admin);
    }
}
~~~

Đọc từng quyết định của builder:

1. **Không dùng `securityMatcher` cấp `HttpSecurity`:** chain này áp dụng mặc định cho các request trong phạm vi bảo mật thông thường của ứng dụng.
2. **GET `/public/ping`:** bất kỳ người gọi nào cũng được phép; rule `permitAll()` không bỏ qua toàn bộ filter chain.
3. **GET `/api/reports`:** yêu cầu đúng authority `REPORT_READ`. Người dùng `analyst` có authority này.
4. **GET `/api/admin`:** yêu cầu `ROLE_ADMIN` nhờ `hasRole("ADMIN")`. Người dùng `admin` có role đó.
5. **Các request còn lại:** yêu cầu `authenticated()`, bao gồm `GET /api/me` và `POST /api/notes`.
6. **HTTP Basic:** credentials được đọc theo HTTP Basic. `UserDetailsService` và `PasswordEncoder` cung cấp cơ chế kiểm tra username/password.
7. **CSRF:** ví dụ không gọi `csrf(...disable...)` nên giữ bảo vệ CSRF mặc định cho request cần kiểm tra. Đặc biệt `POST /api/notes` cần token hợp lệ trong ngữ cảnh thử nghiệm.
8. **`build()`:** trả về bean SecurityFilterChain đã cấu hình. Framework quản lý bean để sử dụng khi xử lý request.

**Phân biệt role và authority:** `roles("ADMIN")` tạo authority `ROLE_ADMIN`. `hasRole("ADMIN")` tìm authority theo tiền tố role mặc định. `hasAuthority("REPORT_READ")` kiểm tra đúng chuỗi `REPORT_READ`; nó không tự thêm `ROLE_`.

### 6.4. Controller

Tệp `src/main/java/demo/security/DemoController.java`:

~~~java
package demo.security;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public String me(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "quarterly report";
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin console";
    }

    @PostMapping("/api/notes")
    public String createNote() {
        return "created";
    }
}
~~~

Các controller **không tự khai báo quyền**; việc bảo vệ URL đến từ cấu hình web security ở trên. Ở phần khác của hệ thống có thể bổ sung method security qua `@EnableMethodSecurity` và `@PreAuthorize`; đó là cơ chế thứ hai cần đánh giá riêng, không được suy ra chỉ từ rule HTTP hiện có.

### 6.5. Dùng MockMvc xác minh từng rule

Tệp `src/test/java/demo/security/SecurityConfigurationTests.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigurationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicPingDoesNotRequireLogin() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void privateMeRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/api/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicCredentialsReachController() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }

    @Test
    void readerCannotReadReports() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystHasReportAuthority() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "analyst-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly report"));
    }

    @Test
    void readerIsNotAnAdmin() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminHasRequiredRole() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin console"));
    }

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/notes")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithAuthenticationAndCsrfTokenPasses() throws Exception {
        mockMvc.perform(post("/api/notes")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }
}
~~~

`@SpringBootTest` tải ApplicationContext thực, `@AutoConfigureMockMvc` cấu hình MockMvc với web layer và security filters. `httpBasic(...)` tạo Basic Authorization header để đi qua quy trình authentication; test này khác với dùng `@WithMockUser` hoặc `user("...")` để giả lập người dùng. `csrf()` là test post-processor giúp gửi token hợp lệ, không phải thay thế cơ chế CSRF thật của framework.

**Đọc kết quả test:** cùng `/api/reports`, `reader` đã xác thực nhưng thiếu `REPORT_READ` nên 403; `analyst` có `REPORT_READ` nên 200. Cùng `/api/me`, thiếu credentials thì 401; Basic đúng thì 200. Với POST, ngay cả credentials đúng cũng cần thỏa yêu cầu CSRF khi cơ chế được bật. Test giữ các chính sách bảo mật đang có, không phải tắt chúng cho tiện.

### 6.6. Chạy ứng dụng và quan sát HTTP

Với Gradle tương thích đã cài và cấu trúc tệp bên trên:

~~~bash
gradle test
gradle bootRun
~~~

Nếu dự án có Gradle wrapper, ưu tiên `./gradlew test` và `./gradlew bootRun` (Windows: `gradlew.bat test`, `gradlew.bat bootRun`). Đây là ứng dụng dùng thư viện Spring, vì vậy lệnh `javac`/`java` trần không đủ nếu chưa thiết lập classpath thủ công. Java source, package và đường dẫn tệp phải tương ứng như ví dụ.

Tại cổng mặc định `localhost:8080`, có thể dùng:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/reports
curl -i -u analyst:analyst-pass http://localhost:8080/api/reports
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i -u reader:reader-pass -X POST http://localhost:8080/api/notes
~~~

Kết quả dự kiến với cấu hình trên (headers và body lỗi có thể khác theo phiên bản/thiết lập):

| Request | HTTP status | Body khi 200 | Nguyên nhân chính |
| --- | --- | --- | --- |
| GET `/public/ping` không credentials | 200 | `pong` | `permitAll()` |
| GET `/api/me` không credentials | 401 | — | `authenticated()` + HTTP Basic challenge |
| GET `/api/me`, reader đúng password | 200 | `hello reader` | Authentication thành công |
| GET `/api/reports`, reader | 403 | — | Thiếu `REPORT_READ` |
| GET `/api/reports`, analyst | 200 | `quarterly report` | Đủ authority |
| GET `/api/admin`, admin | 200 | `admin console` | Có `ROLE_ADMIN` |
| POST `/api/notes`, reader + Basic, thiếu CSRF token | 403 | — | CSRF kiểm tra request thay đổi trạng thái |

**Vì sao lệnh POST không có ví dụ 200 bằng curl?** Ứng dụng chưa khai báo endpoint phát CSRF token cho client. Ví dụ chứng minh nhánh POST thành công qua MockMvc `with(csrf())`, nên không cần đưa ra một câu lệnh curl giả với token không tồn tại. Khi triển khai API thật, chọn chiến lược phát/đính kèm CSRF token hoặc chính sách CSRF phù hợp với mô hình session/cookie.

## 7. Nhiều SecurityFilterChain: thứ tự và fallback

Khi một project có nhiều nhóm URL sử dụng cơ chế xác thực khác nhau, có thể khai báo **nhiều bean SecurityFilterChain**. Hạ tầng Spring Security chọn **chain đầu tiên khớp request**; sau khi chọn chain, authorization rule của chain đó mới được áp dụng.

Ví dụ cấu hình sau là **biến thể độc lập để giải thích việc chọn chain**. Nếu muốn áp dụng trong dự án mẫu, hãy **thay thế bean SecurityFilterChain duy nhất trước đó** bằng hai bean này; không thêm nguyên xi như bean thứ ba bên cạnh cấu hình mẫu.

~~~java
// Đặt trong @Configuration class có các import HttpSecurity,
// Customizer, SecurityFilterChain, Order, Bean và HttpMethod.

@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain remainingChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Bảng chọn chain:

| Request | Chain được chọn | Rule |
| --- | --- | --- |
| GET `/api/public` | `apiChain`, `@Order(1)` | `permitAll()` |
| GET `/api/me` | `apiChain` | `authenticated()` |
| GET `/health` | `remainingChain` | `denyAll()` |
| GET `/` | `remainingChain` | `denyAll()` |

Trong biến thể này, `apiChain` **không** kế thừa rule `hasRole("ADMIN")` của ví dụ trước vì đã thay bean. Nó cũng không phục vụ `/api/public` nếu project chưa có controller tương ứng: security có thể cho qua rồi Spring MVC trả 404. Đây là điểm khác nhau giữa **được phép ở tầng bảo mật** và **tìm được handler**.

**Lỗi nghiêm trọng:** viết một chain duy nhất có `securityMatcher("/api/**")` rồi tưởng `anyRequest().authenticated()` bảo vệ `/login`, `/admin` và các endpoint ngoài `/api/**`. Nếu không có fallback chain, những request ngoài phạm vi có thể không qua Spring Security. Luôn kiểm tra danh sách chain, matcher, thứ tự và phạm vi bảo vệ thực tế.

Khi cần nhiều chain, mỗi chain có thể chọn cơ chế riêng (ví dụ HTTP Basic cho API, form login cho giao diện), cách quản lý session và xử lý CSRF khác nhau. Đây là quyết định kiến trúc cần test theo nhóm endpoint; đừng trộn ngẫu nhiên các cơ chế chỉ để hết 401.

## 8. Những cấu hình hay bị hiểu sai

### 8.1. `authenticated()` không tự định nghĩa cách đăng nhập

`authenticated()` là một điều kiện authorization: request phải có danh tính được xem là đã xác thực. Nó **không tự tạo user database**, không tự đọc JWT và không tự bật login page. Cơ chế thiết lập danh tính phải đến từ filter/provider tương ứng như HTTP Basic, form login hoặc bearer token authentication.

### 8.2. `permitAll()` khác loại trừ request khỏi security

`permitAll()` cho phép request theo một authorization rule. Security filters vẫn có thể chạy và những cơ chế khác có thể tác động (tùy cấu hình, loại request, CSRF). Bỏ qua hẳn Spring Security filter chain là quyết định khác, không nên làm cho endpoint chỉ vì nó public.

### 8.3. `httpBasic` không tự chứng minh hệ thống stateless

HTTP Basic đưa credentials trên request, nhưng **chính sách tạo/lưu session, SecurityContextRepository và authentication mechanisms khác** là những vấn đề độc lập. Nếu cần API stateless, cần cấu hình rõ chính sách session và đánh giá tương tác với các filter khác. Không suy ra một project stateless chỉ bằng cách tìm thấy `httpBasic(Customizer.withDefaults())`.

### 8.4. Không tự tắt CSRF chỉ vì thấy 403

CSRF đặc biệt liên quan các client trình duyệt có thể tự gửi cookie xác thực. Với request POST/PUT/PATCH/DELETE, CSRF có thể từ chối trước khi controller chạy; 403 lúc này không chứng minh user thiếu role. Kiểm tra request method, CSRF token, session/cookie và filter log trước khi thay cấu hình.

### 8.5. `build()` không đánh dấu “đã login”

`build()` chạy khi tạo bean để dựng security filters; nó **không xác thực một người dùng cụ thể**. `AuthenticationManager` hoặc filter xác thực xử lý credentials trong request/runtime. Nếu thấy method bean chạy lúc startup rồi không chạy khi gọi endpoint, đó thường là hành vi đúng.

### 8.6. Thêm `@EnableWebSecurity` không thay thế cấu hình cụ thể

Trong Spring Boot Servlet có starter security, hạ tầng web security thường được kích hoạt qua auto-configuration. Annotation có thể cần trong ứng dụng Spring Framework tự cấu hình hoặc các trường hợp cụ thể, nhưng **không thay thế** `SecurityFilterChain` bean, matcher, filter và logic authentication bạn thực sự cần.

### 8.7. Một matcher rộng đặt trước matcher đặc thù làm sai chính sách

So sánh:

~~~java
// Có vấn đề: rule rộng đã chiếm GET /api/admin
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin").hasRole("ADMIN")
~~~

với:

~~~java
// Rule đặc thù trước, fallback sau
.requestMatchers("/api/admin").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
~~~

Trong cùng một chain, các matcher authorization thường được đánh giá theo thứ tự; hãy tổ chức từ cụ thể đến tổng quát để điều kiện quan trọng không bị che khuất. Đừng chỉ nhìn một dòng `hasRole` rồi kết luận URL được bảo vệ đúng.

## 9. Quan sát quá trình build và xử lý request

### 9.1. Quan sát tại startup

Hãy đặt breakpoint hoặc log trong phương thức bean:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    System.out.println("Configuring SecurityFilterChain");
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **đoạn cấu hình minh họa riêng**. Khi phương thức bean được khởi tạo một lần trong context thông thường, dòng chữ có thể được in **một lần** lúc startup. Không lấy số lần in làm một contract tuyệt đối nếu ApplicationContext được khởi tạo lại trong tests/hot reload; điểm chính là code builder chạy theo **vòng đời bean**, không phải mỗi HTTP request.

Khi startup, Spring Security thường có log hiển thị những filter bảo vệ request. Danh sách filter và mức log phụ thuộc phiên bản. Có thể bật DEBUG cho môi trường học:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Sau đó đối chiếu việc tạo chain, request được bảo vệ và status. Tránh bật TRACE/DEBUG quá rộng trong production vì log có thể nhiều và chứa dữ liệu cần bảo vệ.

### 9.2. Quan sát tại runtime

Với GET `/api/reports`, so sánh hai request:

~~~text
GET /api/reports   Basic reader:reader-pass
  -> Authentication: reader, authorities=[ROLE_READER]
  -> authorization: requires REPORT_READ
  -> denied -> 403

GET /api/reports   Basic analyst:analyst-pass
  -> Authentication: analyst, authorities=[REPORT_READ]
  -> authorization: requires REPORT_READ
  -> granted -> controller -> 200 "quarterly report"
~~~

Đây là **sơ đồ kết quả logic**, không phải log literal của Spring Security. Khi phân tích dự án thật, đừng dựa vào tên một filter hoặc chuỗi log cố định: phiên bản, nhiều chain và configurer có thể thay đổi những thành phần xuất hiện.

Một quy trình debug có thứ tự:

1. Xác định HTTP method, path, headers và cookies của request đang thất bại.
2. Xem bean `SecurityFilterChain` và `securityMatcher` nào áp dụng, nhất là khi có `@Order`.
3. Xem rule của `authorizeHttpRequests` nào khớp; chú ý thứ tự và `anyRequest`.
4. Nếu thiếu danh tính, kiểm tra cơ chế authentication, credentials và provider.
5. Nếu có danh tính nhưng bị từ chối, kiểm tra authorities và role prefix; với unsafe methods, kiểm tra CSRF.
6. Sau khi security cho phép, kiểm tra handler MVC và nghiệp vụ.

### 9.3. Phân biệt những HTTP status thường gặp

| Trạng thái | Cách đọc hợp lý | Điều cần kiểm tra |
| --- | --- | --- |
| 200 | Security cho qua và handler xử lý thành công | Có đúng handler và response mong đợi không? |
| 401 | Với Basic, thường chưa có/sai credentials | `Authorization` header, user store, password encoder |
| 403 | Bị từ chối quyền hoặc cơ chế khác như CSRF | Authorities, matcher, CSRF token |
| 302 | Có thể là chuyển hướng tới form login | Entry point và form login được bật không? |
| 404/405 | Handler không tồn tại/method không hỗ trợ sau security | Controller mapping, method và path |

Không sửa tất cả lỗi bằng `anyRequest().permitAll()` hoặc `csrf(csrf -> csrf.disable())`. Cần xác định đúng nguyên nhân ở chain selection, authentication, authorization, CSRF hay MVC routing.

## 10. Kiểm tra kiến thức và bài tập áp dụng

1. Giải thích vì sao `HttpSecurity` được gọi là builder và `SecurityFilterChain` là output. Lúc nào `build()` chạy, lúc nào `AuthorizationFilter` chạy?
2. Trong ví dụ chính, thay `.requestMatchers(HttpMethod.GET, "/api/reports")` bằng matcher không giới hạn method. Dự đoán POST `/api/reports` chịu rule nào, sau đó phân tích thêm yêu cầu CSRF và tồn tại handler.
3. Đảo thứ tự `anyRequest().authenticated()` và rule `hasRole("ADMIN")` (nếu DSL không chấp nhận cách viết đó, giải thích ý nghĩa của thứ tự và contract của `anyRequest`). Vì sao matcher bao quát nên nằm cuối?
4. Dùng reader và analyst gọi cùng `GET /api/reports`. Ghi lại chuỗi **request → authentication → authority → authorization → response**; bước nào khác nhau?
5. Thử POST `/api/notes` bằng Basic đúng mà không có CSRF token. Từ 403 này có thể kết luận user thiếu role không? Cần chứng cứ nào?
6. Tách cấu hình thành hai chain với `@Order(1)` và `securityMatcher("/api/**")`. Viết bảng cho ba URL trong/ngoài prefix và nêu rõ fallback chain sẽ làm gì.
7. Nếu ứng dụng chỉ có `securityMatcher("/api/**")`, `GET /internal/secret` sẽ khớp chain nào? Vì sao phải kiểm tra cả các request **không** khớp chain?
8. Cho một dự án Spring Security 5.x còn `WebSecurityConfigurerAdapter` và `antMatchers`, nêu cách chuyển tư duy sang bean `SecurityFilterChain` và Lambda DSL Spring Security 6.
9. Nếu một test MockMvc trả 200 nhưng curl trả 401, kiểm tra xem test đã áp dụng security filters chưa, sau đó mới phân tích rule.
10. Thử giải thích lý do `@WithMockUser` có thể vượt qua rule `authenticated()` mà không kiểm tra mật khẩu. Khi muốn test đường xác thực thật của HTTP Basic, dùng công cụ nào?

**Checklist sau khi tự cấu hình thành công:** mỗi nhóm URL khớp chain dự định; mỗi chain có rule fallback rõ ràng; cơ chế authentication được bật có chủ đích; role/authority được so sánh đúng; CSRF/session được quyết định theo client và threat model; code gọi `build()` khi tạo bean; các test chứng minh được cả đường **được phép** lẫn **bị từ chối**.

Nếu có thể giải thích đầy đủ các bước “**HttpSecurity khai báo cấu hình → build SecurityFilterChain tại startup → FilterChainProxy chọn chain lúc request → filter xác thực và phân quyền → controller hoặc response từ chối**”, bạn đã có nền tảng vững để đọc các cấu hình Servlet Security phức tạp hơn.
