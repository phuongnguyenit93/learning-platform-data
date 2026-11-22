# Từ yêu cầu HTTP đến danh tính, quyết định truy cập và phản hồi trong Spring Security

> **Bối cảnh:** Spring Security cho ứng dụng Spring MVC/Servlet, Java 17+ và Spring Boot 3.x. Bài học lần theo **một HTTP request** từ lúc vào ứng dụng đến khi được cho phép, bị yêu cầu đăng nhập hoặc bị từ chối. Tên filter và thứ tự cụ thể có thể thay đổi theo cấu hình.

## 1. Ba câu hỏi mà một request phải đi qua

Giả sử client gọi **GET /admin**. Ứng dụng cần làm rõ:

1. **Request đi qua lớp bảo vệ nào?** Servlet container chuyển request qua chuỗi filter; Spring Security chọn một **SecurityFilterChain** phù hợp.
2. **Ai đang gửi request?** **Authentication** mô tả danh tính hiện có. Danh tính có thể được nạp từ phiên đăng nhập, xác thực từ username/password, HTTP Basic, bearer token, hoặc vẫn là anonymous.
3. **Danh tính ấy có quyền thực hiện request không?** **AuthorizationManager** áp dụng rule; request được chuyển đến controller hoặc phát sinh ngoại lệ truy cập để thành phản hồi HTTP thích hợp.

Hai khái niệm cần tách bạch:

| Khái niệm | Câu hỏi | Kết quả điển hình |
| --- | --- | --- |
| **Authentication (xác thực)** | Bạn là ai? Bằng chứng có hợp lệ không? | Đối tượng **Authentication** chứa principal và authorities; thất bại thường dẫn đến cơ chế yêu cầu xác thực. |
| **Authorization (phân quyền)** | Danh tính hiện tại có được truy cập tài nguyên/hành động này không? | Cho request đi tiếp hoặc từ chối bằng **AccessDeniedException**. |

**Đã đăng nhập không đồng nghĩa với đủ quyền.** Người dùng **alice** có **ROLE_USER** có thể xem **/me** nhưng không mặc nhiên xem **/admin** yêu cầu **ROLE_ADMIN**.

## 2. Sơ đồ đường đi của HTTP request

~~~text
Client: GET /admin + Authorization header (nếu có)
  |
  v
Servlet container
  |
  v
DelegatingFilterProxy -> FilterChainProxy ("springSecurityFilterChain")
  |
  +-- Chọn SecurityFilterChain đầu tiên khớp request
        |
        +-- SecurityContextHolderFilter: lấy/khởi tạo SecurityContext
        +-- Các filter bảo vệ: headers, CORS/CSRF nếu được cấu hình
        +-- Filter xác thực thích hợp: Basic, form login, bearer... nếu áp dụng
        +-- AnonymousAuthenticationFilter: cung cấp anonymous nếu chưa có danh tính
        +-- ExceptionTranslationFilter: bao các bước phía sau để bắt lỗi bảo mật
        +-- AuthorizationFilter: hỏi AuthorizationManager
              |
              +-- ĐƯỢC PHÉP ---> DispatcherServlet -> Controller -> Service
              |                         |
              |                         +--> HTTP 200/201/... hoặc lỗi nghiệp vụ
              |
              +-- BỊ TỪ CHỐI -> AccessDeniedException
                                      |
                                      v
                            ExceptionTranslationFilter
                              |                    |
                       Chưa xác thực          Đã xác thực,
                       / anonymous           thiếu quyền
                              |                    |
                       AuthenticationEntryPoint   AccessDeniedHandler
                              |                    |
                       401 + challenge,          thường là 403
                       hoặc 302 login
~~~

Đây là **sơ đồ tư duy**, không phải danh sách filter cố định của mọi ứng dụng. Các filter được chọn tùy cấu hình (HTTP Basic, form login, OAuth2 resource server, v.v.). **ExceptionTranslationFilter đứng trước AuthorizationFilter trong chuỗi**, gọi phần tiếp theo rồi bắt ngoại lệ phát sinh từ phần đó. Request được phép mới đi tiếp đến Spring MVC; một filter có thể tự hoàn tất response mà không gọi filter tiếp theo.

### 2.1. Từ Servlet container đến SecurityFilterChain

- **DelegatingFilterProxy** nối filter của servlet container với bean **springSecurityFilterChain** trong Spring.
- Bean này thường là **FilterChainProxy**, giữ nhiều **SecurityFilterChain**; mỗi chain có **RequestMatcher** và tập filter riêng.
- **FilterChainProxy chọn chain phù hợp đầu tiên**, rồi chạy các filter của chain đó. Nếu cấu hình nhiều chain, thứ tự và phạm vi matcher rất quan trọng; request không khớp bất kỳ chain nào có thể không được Spring Security bảo vệ.
- **securityMatcher(...)** chọn **request thuộc chain nào**, còn **requestMatchers(...)** bên trong **authorizeHttpRequests(...)** chọn **rule phân quyền của chain đã được chọn**. Không nên nhầm hai tầng này.

Ví dụ hệ thống có chain API dành cho **/api/** và chain web dành cho phần còn lại: chọn chain API là bước trước; quy tắc **/api/admin/** yêu cầu ADMIN là bước sau.

### 2.2. SecurityContext được thiết lập, sử dụng và dọn dẹp

**SecurityContextHolder** giữ **SecurityContext** của luồng xử lý hiện tại (thường qua ThreadLocal). **SecurityContext** có thể chứa **Authentication**. **SecurityContextHolderFilter** tích hợp với **SecurityContextRepository** để lấy ngữ cảnh khi bắt đầu request; **FilterChainProxy** bảo đảm xóa context của request khi kết thúc, tránh rò danh tính giữa các request/luồng.

Không mặc định rằng mỗi request đều xác thực username/password lại: một phiên đăng nhập có thể cung cấp context đã lưu, còn HTTP Basic hoặc bearer token thường cung cấp bằng chứng cho từng request. Việc **lưu SecurityContext để dùng ở request sau** phụ thuộc cơ chế đăng nhập và cấu hình repository/session; trong cách cấu hình hiện đại, filter/cơ chế thực hiện xác thực cần lưu context khi muốn duy trì phiên, thay vì mặc định mọi cập nhật vào ThreadLocal đều được lưu tự động.

Một **Authentication** thường có:

- **principal**: danh tính, có thể là **UserDetails**, chuỗi tên người dùng hoặc đối tượng khác;
- **credentials**: bằng chứng như mật khẩu/token, thường được xóa hoặc hạn chế lưu sau xác thực;
- **authorities**: quyền dưới dạng **GrantedAuthority**, ví dụ **ROLE_USER**, **ROLE_ADMIN**, **SCOPE_read**;
- **authenticated**: trạng thái nội bộ của đối tượng; **không chỉ dựa vào isAuthenticated() để kết luận người dùng đã đăng nhập thực sự**, vì anonymous authentication cũng có thể báo **true**. Framework có cơ chế phân biệt anonymous/remember-me/full authentication.

## 3. Authentication: từ bằng chứng đến danh tính

Với ví dụ **HTTP Basic**, chuỗi xử lý điển hình là:

1. Client gửi **Authorization: Basic ...** (thông tin username/password được mã hóa Base64, **không phải mã hóa bảo mật**).
2. **BasicAuthenticationFilter** lấy credential và tạo một yêu cầu **Authentication** ban đầu.
3. **AuthenticationManager** xử lý xác thực; triển khai phổ biến **ProviderManager** chuyển cho **AuthenticationProvider** hỗ trợ loại token đó.
4. Ví dụ **DaoAuthenticationProvider** dùng **UserDetailsService** tìm tài khoản và **PasswordEncoder** kiểm tra mật khẩu đã mã hóa.
5. Khi hợp lệ, kết quả **Authentication** có danh tính và danh sách authorities được đặt vào **SecurityContextHolder**. Nếu sai credential, cơ chế xác thực xử lý thất bại và có thể yêu cầu client gửi lại credential.

~~~text
HTTP Basic header
    -> BasicAuthenticationFilter
    -> AuthenticationManager (thường ProviderManager)
    -> AuthenticationProvider
    -> UserDetailsService + PasswordEncoder (trường hợp username/password)
    -> Authentication đã xác thực
    -> SecurityContext
~~~

**Không phải mọi authentication đều dùng UserDetailsService.** Bearer JWT thường được thành phần resource server xác minh chữ ký, issuer, audience, thời hạn và chuyển claims thành authorities; đăng nhập bằng form thường qua **UsernamePasswordAuthenticationFilter**. Bài này chỉ cần hiểu điểm chung: cơ chế nhận bằng chứng, kiểm tra bằng chứng, rồi đưa **Authentication** vào context cho authorization.

Khi không có credential và chưa có danh tính, **AnonymousAuthenticationFilter** có thể đưa vào một **AnonymousAuthenticationToken**. Điều đó giúp xử lý nhất quán nhưng **anonymous không được coi là người dùng đăng nhập** cho rule **authenticated()**.

## 4. Authorization: từ Authentication đến quyết định cho phép

Khi request tới **AuthorizationFilter**, filter lấy **Authentication** qua **SecurityContextHolder** (có thể truy xuất trì hoãn) và chuyển cùng request đến **AuthorizationManager**. Với cấu hình **authorizeHttpRequests**, các rule được xét theo thứ tự khai báo; **rule đầu tiên khớp** quyết định quyền truy cập.

| Rule | Ý nghĩa |
| --- | --- |
| **permitAll()** | Cho phép truy cập mà không yêu cầu đăng nhập; vẫn đi qua chuỗi filter bảo vệ. |
| **authenticated()** | Yêu cầu danh tính được Spring Security coi là đã xác thực. |
| **hasRole("ADMIN")** | Yêu cầu authority **ROLE_ADMIN** theo tiền tố mặc định. |
| **hasAuthority("SCOPE_read")** | Yêu cầu chính xác chuỗi authority **SCOPE_read**. |
| **denyAll()** | Từ chối mọi request khớp rule. |

Các quyết định có hai đường chính:

- **Granted:** **AuthorizationFilter** gọi phần tiếp theo; request tới **DispatcherServlet**, controller và service. Sau đó controller có thể trả JSON, văn bản, redirect, lỗi nghiệp vụ hoặc gọi method có bảo vệ bổ sung.
- **Denied:** **AuthorizationFilter** phát sinh **AccessDeniedException**; **ExceptionTranslationFilter** ở phía trước chuyển lỗi bảo mật sang cách phản hồi HTTP đã cấu hình.

**Phân quyền URL chỉ là một lớp.** Nếu **GET /orders/123** yêu cầu ROLE_USER, ứng dụng vẫn phải kiểm tra người đó có quyền xem đơn **123** hay không (ownership/tenant). Có thể thực hiện ở service hoặc qua method security như **@PreAuthorize** khi đã bật **@EnableMethodSecurity**; một role chung không tự giải quyết quyền truy cập theo dữ liệu.

## 5. Vì sao có 401, 403 và đôi khi 302?

**ExceptionTranslationFilter** kết nối ngoại lệ bảo mật với HTTP response:

- **AuthenticationException**, hoặc **AccessDeniedException** từ người dùng **anonymous/chưa xác thực**: gọi **AuthenticationEntryPoint** để bắt đầu xác thực.
- **AccessDeniedException** từ người dùng **đã xác thực nhưng thiếu quyền**: gọi **AccessDeniedHandler**, thường trả **403 Forbidden**.

| Tình huống | Kết quả điển hình | Lý do |
| --- | --- | --- |
| GET endpoint công khai, không đăng nhập | 200 nếu controller thành công | Rule **permitAll()** cho đi tiếp. |
| GET endpoint yêu cầu đăng nhập, không có credential, API dùng HTTP Basic | **401 Unauthorized**, thường kèm **WWW-Authenticate: Basic ...** | **AuthenticationEntryPoint** yêu cầu credential. |
| GET endpoint yêu cầu đăng nhập, web dùng form login | **302** tới trang đăng nhập | Entry point dành cho form chọn redirect thay cho 401. |
| Credential HTTP Basic sai | Thường **401** | Authentication thất bại; chưa tạo được danh tính hợp lệ. |
| Người dùng đã đăng nhập với ROLE_USER truy cập endpoint cần ROLE_ADMIN | Thường **403 Forbidden** | Có danh tính nhưng không đủ authority. |
| POST với session/cookie thiếu CSRF token hợp lệ khi CSRF đang bật | Thường **403 Forbidden** | **CsrfFilter** chặn request, có thể trước bước authorization. |
| Được cho phép nhưng controller không tìm thấy resource | Có thể **404 Not Found** | Lỗi/tình huống ở lớp ứng dụng, không phải quyết định quyền. |

**Không quy mọi 401/403 về một filter:** entry point, access denied handler, CSRF, error dispatch và cấu hình cụ thể ảnh hưởng response. 401/403 còn có thể do ứng dụng hoặc hạ tầng phía trước trả về; đọc log để xác định nguồn. Với Basic, cần **HTTPS** vì Base64 không bảo vệ mật khẩu trên đường truyền.

## 6. Ví dụ chạy được: một API tối giản có public, user và admin

Giả sử đã có dự án **Spring Boot 3.x + Java 17+**, dùng Spring MVC. Thêm dependencies sau vào **build.gradle** hiện hữu (version plugin/BOM do dự án quản lý):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo ba file trong thư mục **src/main/java/com/example/securityflow/**, cùng package **com.example.securityflow**.

**SecurityFlowApplication.java**

~~~java
package com.example.securityflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFlowApplication.class, args);
    }
}
~~~

**SecurityConfig.java**

~~~java
package com.example.securityflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**DemoController.java**

~~~java
package com.example.securityflow;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + authorities;
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

**Giải thích cấu hình:**

- **/public** dùng **permitAll()**; **/admin** yêu cầu authority **ROLE_ADMIN**; mọi đường dẫn còn lại yêu cầu **authenticated()**.
- **httpBasic(...)** bật cơ chế HTTP Basic. Tài khoản demo **alice** có **ROLE_USER**; **admin** có **ROLE_ADMIN**. Hàm **roles("ADMIN")** tự thêm tiền tố **ROLE_**.
- **BCryptPasswordEncoder** băm mật khẩu để so sánh an toàn hơn lưu plaintext; hai mật khẩu trong ví dụ chỉ dành cho môi trường học, phải thay bằng hệ thống quản lý danh tính và secrets phù hợp khi triển khai thực tế.
- **DemoController.me(...)** nhận **Authentication** hiện tại từ Spring MVC và hiển thị tên cùng authorities, cho thấy kết quả sau authentication được controller sử dụng như thế nào.
- Các lệnh ví dụ là **GET**, tránh trộn lẫn bài học phân quyền với yêu cầu CSRF cho phương thức thay đổi trạng thái. Cấu hình này **không tự đặt session thành stateless**.

Chạy từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Trên Windows: gradlew.bat bootRun
~~~

Gửi thử các request trên môi trường **localhost**:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
~~~

Kết quả cần quan sát (status và **response body**, các header khác có thể thay đổi):

| Request | HTTP status dự kiến | Response body khi thành công |
| --- | --- | --- |
| GET /public, anonymous | **200** | **public** |
| GET /me, anonymous | **401** | Không phụ thuộc nội dung body; quan sát header **WWW-Authenticate**. |
| GET /me, alice | **200** | **alice ROLE_USER** |
| GET /admin, alice | **403** | Không phụ thuộc nội dung body. |
| GET /admin, admin | **200** | **admin-only** |
| GET /me, password sai | **401** | Không phụ thuộc nội dung body. |

Các status trên giả định **ứng dụng chạy độc lập với đúng cấu hình ví dụ**, không có chain, exception handler hoặc reverse proxy tùy chỉnh khác. **curl -i** in cả header; đoạn văn bản trả về là response body chứ không phải stdout của chương trình Java.

## 7. Theo dấu ba request tiêu biểu

### Trường hợp A: anonymous gọi GET /me

1. Servlet container đưa request qua **FilterChainProxy** và chain bảo vệ.
2. Không có credential, **SecurityContext** chưa chứa danh tính; **AnonymousAuthenticationFilter** có thể gán anonymous.
3. **AuthorizationFilter** xét **/me**: không khớp **/public** hoặc **/admin**, gặp **anyRequest().authenticated()**.
4. Anonymous không đáp ứng **authenticated()** nên bị từ chối.
5. **ExceptionTranslationFilter** nhận lỗi, gọi **AuthenticationEntryPoint** của HTTP Basic.
6. Client nhận **401** và challenge; **DemoController.me(...) không chạy**.

### Trường hợp B: alice gọi GET /admin với HTTP Basic hợp lệ

1. **BasicAuthenticationFilter** nhận username/password, xác thực qua manager/provider và có **Authentication** của **alice** chứa **ROLE_USER**.
2. **AuthorizationFilter** chọn rule **/admin → hasRole("ADMIN")**.
3. **ROLE_USER** không thỏa **ROLE_ADMIN**, nên phát sinh **AccessDeniedException**.
4. Vì alice đã được xác thực, **ExceptionTranslationFilter** dùng **AccessDeniedHandler** để trả **403**; **adminEndpoint() không chạy**.

### Trường hợp C: admin gọi GET /admin

1. Credential hợp lệ tạo **Authentication** của **admin** với **ROLE_ADMIN**.
2. **AuthorizationManager** cho phép vì authority phù hợp.
3. Request tiếp tục đến **DispatcherServlet**, gọi **adminEndpoint()**.
4. Controller trả chuỗi **admin-only**, HTTP **200** nếu không có lỗi khác.
5. Khi request kết thúc, context gắn với luồng được dọn dẹp đúng vòng đời filter.

## 8. Kiểm thử tự động đúng mục tiêu

Với hai dependency test đã khai báo, đặt **SecurityFlowTest.java** ở **src/test/java/com/example/securityflow/**:

~~~java
package com.example.securityflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadMeButCannotEnterAdmin() throws Exception {
        mvc.perform(get("/me").with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER"));

        mvc.perform(get("/admin").with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdmin() throws Exception {
        mvc.perform(get("/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Chạy **./gradlew test** (Windows: **gradlew.bat test**). Các test kiểm tra behavior HTTP end-to-end qua servlet filters; chúng không cần gọi trực tiếp **AuthenticationManager** hay tự đặt **SecurityContext** để làm giả kết quả bảo vệ. Khi muốn kiểm thử service-level authorization, bổ sung test riêng cho **@PreAuthorize**/ownership và các trường hợp cùng role nhưng khác chủ sở hữu.

## 9. Chẩn đoán khi status không như mong đợi

Bật log bảo mật ở mức DEBUG trong môi trường phát triển:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Khi khởi động, log Spring Security có thể liệt kê **filter chain**. Khi gửi request, đối chiếu:

1. **Có đúng chain đang xử lý request?** Kiểm tra matcher, thứ tự chain, đường dẫn thực tế và HTTP method.
2. **Có Authentication chưa?** Xem cơ chế đang bật, credential hợp lệ, session/context repository; không ghi log token/mật khẩu.
3. **Authorities là gì?** Phân biệt **ROLE_ADMIN** với **ADMIN**, **SCOPE_read** với **read**; không nhầm role và authority.
4. **Rule nào khớp đầu tiên?** Rule tổng quát đặt sớm có thể che rule chi tiết đặt sau.
5. **Ai trả status?** Phân biệt authentication entry point, access denied handler, CSRF filter, controller advice, servlet error handling và reverse proxy.

Những lỗi dễ gặp:

- **Đồng nhất 401 và 403:** chưa có danh tính hợp lệ khác với đã xác thực nhưng thiếu quyền. Form login còn có thể redirect **302**.
- **Chỉ kiểm tra role ở URL:** bỏ sót quyền đối với một bản ghi cụ thể (IDOR/BOLA). Cần kiểm tra ownership/tenant ở lớp nghiệp vụ.
- **Dùng securityMatcher để thay requestMatchers hoặc ngược lại:** dẫn đến chain không bảo vệ request dự kiến.
- **Nhầm permitAll với bỏ qua Spring Security:** **permitAll()** vẫn cho request đi qua các filter như security headers; không tùy tiện loại URL khỏi toàn bộ chain.
- **Vô hiệu hóa CSRF để chữa một lỗi 403:** trước tiên xác định client có dùng cookie/session trong trình duyệt hay không và CSRF đang bảo vệ điều gì. Với session/cookie, CSRF thường là yêu cầu bảo mật thiết yếu.
- **Tự đọc isAuthenticated() mà không tính anonymous:** kiểm tra quyền bằng policy/AuthorizationManager thay vì tự suy đoán từ một cờ boolean.
- **Nghĩ SecurityContext tự lưu cho mọi request:** hiểu sự khác nhau giữa context đang có trong request và context được lưu để khôi phục ở lần sau.
- **Tự viết filter xác thực nhưng không quản lý đúng vòng đời/context:** dễ làm rò danh tính hoặc bỏ qua exception handling; ưu tiên cơ chế Spring Security có sẵn.

## 10. Tự kiểm tra kiến thức

**Câu 1.** alice đã đăng nhập nhưng gặp **403** ở **/admin**. Cần kiểm tra gì trước?

**Đáp:** Quy tắc **hasRole("ADMIN")** đòi **ROLE_ADMIN**, trong khi alice chỉ có **ROLE_USER**. Danh tính hợp lệ không đủ để được cấp quyền.

**Câu 2.** Tại sao cùng request không đăng nhập có ứng dụng trả **401**, ứng dụng khác trả **302**?

**Đáp:** **AuthenticationEntryPoint** phụ thuộc cơ chế xác thực/cấu hình: HTTP Basic thường trả 401 kèm challenge; form login thường redirect đến trang đăng nhập.

**Câu 3.** Có thể dùng **permitAll()** cho **/public** mà vẫn áp dụng security headers không?

**Đáp:** Có. **permitAll()** là quyết định authorization; request vẫn đi qua **SecurityFilterChain** được chọn.

**Câu 4.** Nếu **ROLE_USER** truy cập được **GET /orders/123**, điều đó chứng minh họ sở hữu đơn hàng 123 chưa?

**Đáp:** Chưa. Rule URL chỉ kiểm tra quyền tổng quát; ứng dụng phải kiểm tra quyền với chính tài nguyên đó.

**Điểm nhớ cuối:** Với một request, hãy xác định **chain được chọn → Authentication trong SecurityContext → rule của AuthorizationManager → cho đi tiếp hoặc xử lý ngoại lệ → HTTP response**. Đây là đường đi cốt lõi giúp đọc cấu hình, debug 401/403 và thiết kế kiểm thử bảo mật đúng chỗ.

## Tài liệu tham khảo chính thức

- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Cross Site Request Forgery (CSRF): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
