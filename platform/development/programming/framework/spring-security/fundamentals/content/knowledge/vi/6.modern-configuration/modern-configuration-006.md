# Nhiều chuỗi bảo mật, thứ tự ưu tiên và chuỗi dự phòng trong Spring Security

## 1. Vấn đề và mục tiêu

Một ứng dụng Spring Boot có thể có nhiều khu vực HTTP với yêu cầu bảo mật khác nhau: REST API, trang quản trị, trang công khai và các endpoint vận hành. Ví dụ:

- **/api/** dùng HTTP Basic trong bài thực hành hoặc OAuth2 Resource Server/Bearer token trong ứng dụng thật.
- **/admin/** cần role ADMIN.
- **/** và **/status** là endpoint public.
- Các URL chưa được phân loại phải có chính sách rõ, không tự động công khai.

Spring Security hỗ trợ nhiều bean **SecurityFilterChain**. Mỗi chain có thể chứa bộ filter và quy tắc truy cập riêng. Nhưng **FilterChainProxy chỉ áp dụng SecurityFilterChain đầu tiên khớp request**, chứ không chạy tất cả chain rồi cộng dồn các điều kiện.

Vì thế cần kiểm soát:

1. **Phạm vi:** Chain này áp dụng cho URL hoặc RequestMatcher nào?
2. **Thứ tự:** Chain nào được xét trước?
3. **Fallback:** Request không thuộc các chain chuyên biệt được xử lý thế nào?
4. **Quy tắc nội bộ:** Sau khi chain được chọn, authorization có cho phép request không?
5. **Kiểm thử:** Liệu mọi URL quan trọng đều có một chain phù hợp và không có đường bypass?

Bài dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Với WebFlux, cấu hình tương ứng là SecurityWebFilterChain và ServerHttpSecurity, không dùng trực tiếp HttpSecurity của Servlet.

### Sau bài học, bạn có thể

- Phân biệt **securityMatcher** với **requestMatchers**.
- Giải thích @Order, cơ chế first-match và fallback.
- Tạo ba chain API, admin và fallback bằng lambda DSL hiện đại.
- Đọc ma trận kiểm thử HTTP **200, 401, 403 và 404**.
- Phát hiện chain quá rộng che khuất chain cụ thể, thiếu fallback, login URL không nằm trong chain hoặc sai thứ tự authorization rules.
- Tách yêu cầu authentication, authorization, CSRF, session và quyền dữ liệu theo đúng trách nhiệm.

## 2. Vị trí của FilterChainProxy

Trong Servlet, request đi vào servlet container, qua DelegatingFilterProxy tới FilterChainProxy. FilterChainProxy giữ một danh sách có thứ tự các SecurityFilterChain.

~~~text
HTTP client
    |
    v
Servlet container (ví dụ Tomcat)
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    +--> SecurityFilterChain 1: @Order(1), /api/** ?
    |        |
    |        +-- Khớp: CHỌN chain 1, không thử các chain sau
    |
    +--> SecurityFilterChain 2: @Order(2), /admin/** ?
    |        |
    |        +-- Khớp: CHỌN chain 2, không thử các chain sau
    |
    +--> SecurityFilterChain fallback: không securityMatcher
             |
             +-- Khớp: dùng chain cuối cho URL còn lại

Trong chain đã chọn:
    authentication / security context / CSRF / authorization
    |
    v
DispatcherServlet -> Controller -> Service
~~~

Sơ đồ khái quát không khẳng định thứ tự nội bộ chính xác của mọi security filter. Nó nhấn mạnh rằng **một request chỉ được một SecurityFilterChain chọn**.

Ví dụ GET /api/orders khớp phạm vi /api/**. Dù fallback có matcher mặc định khớp mọi URL, request vẫn chỉ vào chain API vì nó có ưu tiên cao hơn.

**Quan trọng:** Nếu chain API đã chọn request rồi trả 403 do thiếu role, FilterChainProxy **không chuyển request sang fallback để thử lại**. Fallback chỉ áp dụng cho request chưa khớp chain nào trước đó.

### Ba loại thứ tự khác nhau

| Loại thứ tự | Chức năng | Ví dụ |
| --- | --- | --- |
| **Thứ tự SecurityFilterChain** | Chọn một chain cho request | @Order(1) trước @Order(2) |
| **Thứ tự filter bên trong chain** | Thực thi các bước security của chain đã chọn | Authentication filter, AuthorizationFilter |
| **Thứ tự authorization rule trong chain** | Chọn rule bảo vệ request | Matcher cụ thể trước anyRequest |

Đừng nhầm nhiều chain với nhiều filter. Một chain **chứa nhiều filter**; nhiều chain là nhiều lựa chọn cấu hình, và FilterChainProxy chỉ chọn chain đầu tiên khớp.

## 3. securityMatcher và requestMatchers không tương đương

**securityMatcher** là matcher cấp HttpSecurity/chuỗi: nó quyết định toàn bộ SecurityFilterChain có được chọn cho request hay không.

**requestMatchers** được dùng bên trong authorizeHttpRequests: nó lựa chọn một rule authorization **sau khi chain đã được chọn**.

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .anyRequest().hasRole("API")
    );
~~~

Đây là đoạn DSL minh họa bên trong phương thức xây SecurityFilterChain.

| Request | Chain API có khớp không? | Rule nếu đã vào chain |
| --- | --- | --- |
| GET /api/public | Có | permitAll |
| GET /api/orders | Có | anyRequest().hasRole("API") |
| GET /admin/dashboard | Không | Không có rule nào của chain API được xét |
| GET /reports | Không | Cần chain khác hoặc fallback |

**anyRequest() trong một chain có securityMatcher** chỉ áp dụng cho request đã vào phạm vi của chain đó. Nó không bao phủ tất cả URL toàn ứng dụng.

Nếu bỏ **securityMatcher("/api/**")** nhưng vẫn có **requestMatchers("/api/**")** trong authorizeHttpRequests, chain không được giới hạn thành API-only. Nó có thể tiếp nhận cả request admin; đây là nguồn lỗi nghiêm trọng khi các chain có ưu tiên khác nhau.

### Matchers và URL thực tế

Spring Security có thể dùng các loại RequestMatcher phù hợp với Servlet/Spring MVC. Ở ứng dụng có reverse proxy rewrite, context path, servlet path hoặc nhiều servlet registrations, URL client nhìn thấy có thể khác path app thực sự xét. Hãy kiểm tra method và path tại ứng dụng, thay vì suy ra matcher chỉ từ URL công khai.

## 4. @Order: ưu tiên xét chuỗi

Số @Order **nhỏ hơn** có độ ưu tiên cao hơn. Trong mẫu này:

| Bean | Ưu tiên | Phạm vi |
| --- | --- | --- |
| apiChain có @Order(1) | Cao nhất | /api/** |
| adminChain có @Order(2) | Tiếp theo | /admin/** |
| fallbackChain không @Order | Sau hai chain trên | Tất cả URL chưa được chọn |

Một chain không khai báo securityMatcher có matcher mặc định **mọi request**. Vì vậy nó nên nằm sau các chain cụ thể. Nếu đưa catch-all lên @Order(1), nó có thể bắt toàn bộ request và che các chain phía sau.

### 4.1. Ví dụ cấu hình sai do matcher quá rộng

Đây là **ví dụ nguy hiểm chỉ để nhận diện lỗi**, không dùng thật:

~~~java
@Bean
@Order(1)
SecurityFilterChain accidentalCatchAll(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .build();
}
~~~

Vì thiếu securityMatcher, chain có thể khớp /api/**, /admin/** và mọi đường dẫn khác. Với thứ tự cao nhất và permitAll, nó có thể làm các chain bảo vệ API/admin phía sau không bao giờ được chọn.

### 4.2. Ví dụ nhầm requestMatchers là giới hạn chain

~~~java
@Bean
@Order(1)
SecurityFilterChain mistaken(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").hasRole("API")
            .anyRequest().permitAll()
        )
        .build();
}
~~~

Chain này không có securityMatcher. Một request /admin/dashboard vẫn có thể vào chain này và khớp anyRequest().permitAll(). Cách đúng là đặt **securityMatcher("/api/**")** ở cấp HttpSecurity trước khi cấu hình rules.

### 4.3. Phạm vi chồng lấn

Nếu có chain /api/admin/** và chain /api/**, cả hai có thể phù hợp với /api/admin/reports. Khi ấy matcher hẹp **/api/admin/** phải có ưu tiên cao hơn nếu muốn nó được chọn. Nên đặt @Order tường minh, tránh dựa vào thứ tự tên method/Bean, đồng thời kiểm thử URL ở vùng giao nhau.

## 5. Fallback chain và hành vi khi không chain nào khớp

Nếu **không SecurityFilterChain nào khớp**, request **không được Spring Security bảo vệ**. Nó vẫn có thể đi đến Servlet/MVC hoặc chịu tác động của bộ lọc khác, nhưng không được các authentication/authorization filters của Spring Security trong những chain không khớp kiểm tra.

Ví dụ chỉ có hai chain /api/** và /admin/**, GET /reports/export không thuộc chain nào. Khi Controller /reports/export được thêm sau này, ứng dụng có thể vô tình để lộ endpoint đó.

Để tránh, thêm một fallback chain:

- Xếp sau chain API/admin.
- **Không dùng securityMatcher**, để nó khớp các request còn lại.
- Chỉ permitAll những endpoint public đã xác định.
- Dùng **anyRequest().denyAll()** hoặc **anyRequest().authenticated()** tùy chính sách.

Trong bài này, fallback **denyAll** các URL chưa được phân loại.

### Fallback denyAll không đồng nghĩa lúc nào cũng HTTP 403

Nếu một request chưa được xác thực đi vào fallback denyAll và HTTP Basic đang bật, Spring Security có thể dùng AuthenticationEntryPoint để trả **401**. Một request với credentials hợp lệ nhưng vẫn bị denyAll thường nhận **403**.

HTTP status phụ thuộc authentication state và cách exception handling được cấu hình. Bản chất cần kiểm tra là **request đã vào chain đúng và bị policy từ chối**, thay vì cứng nhắc chỉ chấp nhận một mã.

## 6. Thiết kế ví dụ ba chuỗi

Ta dùng các endpoint sau:

| Endpoint | Chain được chọn | Quy tắc |
| --- | --- | --- |
| GET /api/public | API @Order(1) | Không cần authentication |
| GET /api/orders | API @Order(1) | ROLE_API |
| GET /admin/dashboard | Admin @Order(2) | ROLE_ADMIN |
| GET / | Fallback | Không cần authentication |
| GET /status | Fallback | Không cần authentication |
| GET /unknown | Fallback | denyAll |

Tài khoản minh họa:

| Username | Password demo | Role |
| --- | --- | --- |
| api-user | api-pass | API |
| admin-user | admin-pass | ADMIN |
| ops-user | ops-pass | API và ADMIN |

Với UserDetailsService thông dụng, **roles("API")** tạo authority **ROLE_API**, và **roles("ADMIN")** tạo **ROLE_ADMIN**. Role ADMIN **không tự bao hàm ROLE_API**. ops-user được cấp cả hai nên có thể gọi cả hai khu vực.

Các tài khoản chỉ để học tại localhost; ứng dụng thật cần nguồn danh tính, HTTPS, bảo vệ secret và chính sách vận hành phù hợp.

## 7. Ví dụ Spring Boot 3.x hoàn chỉnh

### 7.1. Dependency

Dùng Spring Initializr tạo dự án Boot 3.x, Java 17+ có Gradle Wrapper và các starter dưới đây trong **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đoạn này nằm trong dự án Boot có plugin/build tool đã tạo; không phải toàn bộ file Gradle độc lập.

### 7.2. Source Java

Tạo file **src/main/java/com/example/multichain/MultiChainApplication.java**:

~~~java
package com.example.multichain;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MultiChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().hasRole("API")
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    // Fallback không giới hạn securityMatcher.
    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/status").permitAll()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("api-user")
                .password(encoder.encode("api-pass"))
                .roles("API")
                .build(),
            User.withUsername("admin-user")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build(),
            User.withUsername("ops-user")
                .password(encoder.encode("ops-pass"))
                .roles("API", "ADMIN")
                .build()
        );
    }
}

@RestController
class DemoController {

    @GetMapping("/")
    String home() {
        return "home OK";
    }

    @GetMapping("/status")
    String status() {
        return "ready";
    }

    @GetMapping("/api/public")
    String publicApi() {
        return "api public OK";
    }

    @GetMapping("/api/orders")
    String orders(Principal principal) {
        return "orders for " + principal.getName();
    }

    @GetMapping("/admin/dashboard")
    String dashboard() {
        return "admin dashboard OK";
    }
}
~~~

Đây là **một file Java** trong dự án Spring Boot đã thiết lập. Public class trùng tên file; class DemoController cùng package được Spring Boot component scan. Ba bean SecurityFilterChain có matcher và thứ tự riêng.

**Giải thích:**

1. **apiChain:** @Order(1), chỉ cho /api/**. GET /api/public permitAll, các request API còn lại cần ROLE_API.
2. **adminChain:** @Order(2), chỉ cho /admin/**, yêu cầu ROLE_ADMIN.
3. **fallbackChain:** không @Order và không securityMatcher, xử lý URL còn lại; GET / và GET /status permitAll, các URL khác denyAll.
4. **HTTP Basic** bật ở cả ba chain để quan sát kết quả 401/403 bằng curl; form login tắt trong demo.
5. **SessionCreationPolicy.STATELESS** chỉ được đặt ở chain API. Điều này không làm admin/fallback stateless và **không tự tắt CSRF**.
6. **CSRF protection vẫn theo mặc định**. Ví dụ chỉ có GET. Thêm POST/PUT/DELETE phải đánh giá CSRF theo cách client gửi credentials; HTTP Basic dùng trong browser cũng có thể chịu rủi ro CSRF.
7. **BCryptPasswordEncoder** tạo hash cho user in-memory. Mật khẩu hard-code chỉ dành cho học tập, không sử dụng production.

## 8. Chạy và kiểm thử bằng curl

Tại thư mục gốc dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng **.\gradlew.bat bootRun**. Khi server lắng nghe localhost:8080, thử:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/status
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/orders
curl -i -u api-user:api-pass http://localhost:8080/api/orders
curl -i -u admin-user:admin-pass http://localhost:8080/api/orders
curl -i -u api-user:api-pass http://localhost:8080/admin/dashboard
curl -i -u admin-user:admin-pass http://localhost:8080/admin/dashboard
curl -i -u ops-user:ops-pass http://localhost:8080/api/orders
curl -i -u ops-user:ops-pass http://localhost:8080/admin/dashboard
curl -i -u admin-user:admin-pass http://localhost:8080/unknown
curl -i -u api-user:api-pass http://localhost:8080/api/unknown
~~~

PowerShell có thể cần **curl.exe** vì curl là alias. Các password trong lệnh chỉ để demo local; khi thao tác thực tế, có thể dùng **curl -u api-user URL** để nhập password qua prompt thay vì để trong shell history. Dùng HTTPS khi gửi credential qua mạng.

### Kết quả kỳ vọng

| Request | Chain | HTTP status | Nội dung / lý do |
| --- | --- | --- | --- |
| GET /, anonymous | Fallback | **200** | home OK |
| GET /status, anonymous | Fallback | **200** | ready |
| GET /api/public, anonymous | API | **200** | api public OK |
| GET /api/orders, anonymous | API | **401** | Thiếu authentication Basic |
| GET /api/orders, api-user | API | **200** | orders for api-user |
| GET /api/orders, admin-user | API | **403** | Thiếu ROLE_API |
| GET /admin/dashboard, api-user | Admin | **403** | Thiếu ROLE_ADMIN |
| GET /admin/dashboard, admin-user | Admin | **200** | admin dashboard OK |
| GET /api/orders, ops-user | API | **200** | Có ROLE_API |
| GET /admin/dashboard, ops-user | Admin | **200** | Có ROLE_ADMIN |
| GET /unknown, admin-user | Fallback | **403** | denyAll trong fallback |
| GET /api/unknown, api-user | API | **404** có thể xảy ra | Qua authorization nhưng không có Controller |

Đây là **status dự kiến từ cấu hình**, không phải kết quả đo từ một tiến trình chạy trong tài liệu. URL rewrite, context path, filter bổ sung hoặc custom exception handler có thể làm phản hồi khác.

**Vì sao /api/unknown có thể 404 còn /unknown là 403?** Request /api/unknown vào chain API; api-user đủ quyền nên đi tới MVC, nhưng không có mapping. /unknown vào fallback và bị denyAll trước khi MVC tìm Controller.

**Vì sao permitAll vẫn có thể trả 401?** Nếu client chủ động gửi Authorization: Basic sai mật khẩu tới /api/public, BasicAuthenticationFilter có thể thử xác thực và xử lý lỗi trước khi authorization permitAll được xét. permitAll chỉ nghĩa là không bắt buộc Authentication cho endpoint đó.

## 9. Không có fallback là một đường bỏ sót security

Giả sử chỉ có apiChain và adminChain. GET /reports/export không khớp /api/** hoặc /admin/**. Khi đó **Spring Security không bảo vệ request này bằng các chain đã khai báo**.

Nếu Controller chưa tồn tại, request có thể 404. Nhưng khi developer tạo Controller ở /reports/export sau này, không có chain áp dụng nghĩa là endpoint có thể bị truy cập không qua những security filters đã dự kiến.

Vì vậy tài liệu Spring Security khuyến nghị có một SecurityFilterChain không dùng securityMatcher để toàn bộ ứng dụng được bao phủ. Fallback nên có policy cụ thể, chẳng hạn permitAll các URL đã xác định và anyRequest().denyAll().

**Không được hiểu fallback là chain xử lý lại yêu cầu bị API/admin từ chối.** Chỉ request chưa khớp chain trước mới vào fallback.

## 10. Thứ tự rule trong một chain

Ngoài @Order giữa các chain, hãy xét thứ tự requestMatchers trong authorizeHttpRequests.

**Đúng:** Rule public cụ thể trước rule bao quát:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
    .anyRequest().hasRole("API")
)
~~~

**Dễ sai:** Rule rộng permitAll đứng trước rule private:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/private").hasRole("API")
    .anyRequest().denyAll()
)
~~~

/api/private có thể khớp permitAll đầu tiên, khiến rule hasRole phía sau không thực sự bảo vệ nó. Đây là **lỗi thứ tự authorization rules bên trong chain**, khác với việc **chọn sai SecurityFilterChain**.

## 11. Bẫy login URL ngoài phạm vi chain

Một thiết kế có:

- adminChain chỉ khớp **/admin/**.
- Developer bật **formLogin** mặc định.
- Form login thường dùng **/login** làm endpoint processing.
- **/login** nằm ngoài phạm vi /admin/**.

POST /login khi ấy không vào adminChain, nên UsernamePasswordAuthenticationFilter của adminChain không xử lý như mong đợi. Có thể nhận 404 hoặc bị fallback từ chối.

Cách thiết kế đúng là xác định login page, loginProcessingUrl, logout và callback **thuộc chain có filter xử lý tương ứng**. Ví dụ tạo /admin/login cho cả GET page và POST processing, cấu hình permitAll cho endpoint phù hợp, xử lý CSRF với POST và session theo kiểu client.

Ví dụ chạy của bài dùng **HTTP Basic ở adminChain** để tránh yêu cầu xây login form. Khi chuyển sang OIDC/form login thật, phải cấu hình đường dẫn và handlers một cách đầy đủ.

## 12. CSRF, session, CORS và authentication theo chain

Các chain có thể sử dụng các bộ filter khác nhau:

- API có thể dùng HTTP Basic hoặc Resource Server xác minh Bearer token.
- Trang admin có thể dùng form login/OIDC, session cookie và CSRF token.
- Fallback có thể từ chối các URL chưa phân loại.

**Không có cơ chế cộng dồn các filter của fallback vào chain API**. Muốn một kiểm soát có tác dụng với API thì nó phải được áp ở chain API hoặc một tầng khác thực sự chạy cho request đó.

Điểm cần lưu ý:

1. **Stateless không tự làm CSRF biến mất.** Rủi ro phụ thuộc cách browser gửi credentials, ví dụ HTTP Basic hoặc cookie.
2. Nếu dùng Bearer JWT, phải xác minh chữ ký, issuer, audience, expiry và chuyển claims sang authorities đúng chính sách. Nhiều SecurityFilterChain không tự tạo Authorization Server.
3. **OPTIONS/CORS preflight** cần được xử lý đúng trước khi một rule authentication từ chối không hợp lý.
4. **AuthenticationEntryPoint** của API có thể trả 401, còn web login có thể redirect 302; chain quyết định cơ chế đang áp dụng.
5. CSRF, headers, logout, cookies và session policy cần được kiểm tra đúng chain; không giả định cấu hình trong fallback áp cho API.
6. **Authorization theo URL** không thay việc kiểm tra ownerId/permission của từng bản ghi ở Service/Repository.

### Actuator và reverse proxy

Endpoint Spring Boot Actuator thường ở **/actuator/** hoặc management port riêng; /status trong demo chỉ là Controller thường. Khi dùng custom SecurityFilterChain, cần kiểm tra endpoint exposure và access policy của Actuator. Không suy ra /api/** và /admin/** tự bao phủ mọi management endpoint.

Reverse proxy có thể rewrite URL. Hãy xác định path mà Spring Security thực sự nhận, context path và các header tin cậy trước khi khẳng định chain matcher đúng.

## 13. Quy trình debug có hệ thống

Khi request có status không mong đợi:

1. Kiểm tra HTTP method, URL, servlet/context path và proxy rewrite.
2. Liệt kê tất cả SecurityFilterChain, matcher và @Order.
3. Xác định **chain đầu tiên khớp**, hoặc phát hiện không có chain phù hợp.
4. Kiểm tra authentication filter của chain đó có nhận và kiểm tra credential không.
5. Đọc principal, authorities và authenticated status sau xác thực.
6. Xác định requestMatchers hoặc anyRequest rule nào được áp dụng.
7. Kiểm tra CSRF, CORS, session hoặc exception handling có từ chối không.
8. Kiểm tra Controller mapping để phân biệt 403 với 404.
9. Test các URL hỗ trợ như login/logout, OAuth2 callback, Actuator và OPTIONS.
10. Tạo negative tests cho URL chưa khai báo và người không đủ role.

Có thể bật DEBUG logging của Spring Security khi phát triển để quan sát chuỗi được chọn, nhưng **không log raw Authorization header, password, token, cookies hoặc secret**.

### Ma trận test nên có trước deployment

| Test | Mong đợi |
| --- | --- |
| API public không credentials | 200 qua API chain |
| API private không credentials | 401 qua API chain |
| API private thiếu ROLE_API | 403 qua API chain |
| Admin thiếu ROLE_ADMIN | 403 qua adminChain |
| Admin đủ ROLE_ADMIN | 200 qua adminChain |
| URL mới chưa phân loại | Fallback từ chối |
| API/admin URL chồng lấn | Đúng chain ưu tiên |
| Login processing và callback | Nằm trong chain xử lý authentication |
| Actuator và management endpoints | Được bảo vệ theo policy rõ ràng |
| Tài nguyên thuộc người khác | Business authorization từ chối |

## 14. Ngộ nhận thường gặp

**“Request chạy qua mọi SecurityFilterChain.”** Sai: FilterChainProxy dùng first matching chain.

**“@Order(1) luôn là tốt nhất.”** Sai: chain quá rộng ở ưu tiên cao có thể che policy phía sau.

**“requestMatchers("/api/**") giới hạn cả chain.”** Sai: securityMatcher mới giới hạn phạm vi chain.

**“anyRequest().denyAll() trong adminChain chặn mọi URL.”** Sai: nó chỉ áp cho request thuộc adminChain.

**“Không chain nào khớp thì Spring Security tự trả 403.”** Sai: request không được các chain của Spring Security bảo vệ.

**“Fallback sẽ cho phép yêu cầu API bị từ chối thử lại.”** Sai: chain đã chọn không được thay thế khi authorization thất bại.

**“Form login /login tự hoạt động trong chain chỉ match /admin/**.”** Không chắc: endpoint xử lý login phải nằm trong phạm vi chain có filter đó.

**“SessionCreationPolicy.STATELESS tự tắt mọi nguy cơ CSRF.”** Sai: CSRF phụ thuộc browser/credentials.

**“ADMIN luôn truy cập được API.”** Sai: vai trò API và ADMIN độc lập nếu policy không cấp quyền chung.

**“ROLE_API đủ bảo vệ dữ liệu mọi người.”** Sai: còn cần kiểm tra quyền sở hữu tài nguyên.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** GET /api/orders khớp API và fallback; có bao nhiêu chain được chọn?  
**Đáp:** Một: API chain có ưu tiên cao hơn.

**Câu 2.** Bỏ fallback, GET /reports không khớp chain nào. Có chắc trả 403?  
**Đáp:** Không. Request không được các chain Spring Security bảo vệ.

**Câu 3.** Rule anyRequest().hasRole("ADMIN") trong adminChain có bảo vệ /api/orders không?  
**Đáp:** Không, vì /api/orders chọn API chain.

**Câu 4.** Chain không securityMatcher, @Order(1), permitAll có rủi ro gì?  
**Đáp:** Nó có thể khớp mọi request, che các chain bảo vệ API/admin.

**Câu 5.** admin-user bị 403 ở /api/orders dù đăng nhập đúng, vì sao?  
**Đáp:** Có ROLE_ADMIN nhưng thiếu ROLE_API.

**Câu 6.** ops-user được phép vào cả hai khu vực vì sao?  
**Đáp:** Có cả ROLE_API và ROLE_ADMIN.

**Câu 7.** Chain chỉ match /admin/** nhưng formLogin xử lý /login. Điều gì có thể sai?  
**Đáp:** /login nằm ngoài chain, nên login filter của chain không xử lý request.

**Câu 8.** /api/unknown có thể 404, còn /unknown bị fallback trả 403; khác ở đâu?  
**Đáp:** Request API qua được policy nhưng không có MVC mapping; fallback từ chối /unknown trước đó.

**Câu 9.** Phân biệt securityMatcher và requestMatchers.  
**Đáp:** Một bên chọn phạm vi SecurityFilterChain; bên kia chọn authorization rule trong chain.

**Câu 10.** Vì sao cần kiểm tra Actuator và OAuth2 callback khi dùng nhiều chain?  
**Đáp:** Chúng có thể ở ngoài các prefix ứng dụng và cần matcher/policy riêng.

## 16. Tài liệu tham khảo chính thức

- Java Configuration và Multiple HttpSecurity Instances: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Servlet Architecture và Multiple SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Boot 3.3 Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
