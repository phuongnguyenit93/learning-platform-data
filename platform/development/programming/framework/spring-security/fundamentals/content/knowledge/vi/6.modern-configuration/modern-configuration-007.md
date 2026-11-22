# permitAll khác với bỏ qua toàn bộ chuỗi bảo mật

> **Phạm vi:** Spring Security Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. Bài học giải thích vì sao **permitAll()** cho phép truy cập một endpoint mà **vẫn giữ request trong SecurityFilterChain**, còn **web.ignoring()** hoặc request không khớp bất kỳ chain nào có thể làm Spring Security **không áp dụng các filter bảo vệ**. Bài có cấu hình Lambda DSL, ví dụ chạy được và kiểm thử chứng minh khác biệt về security headers, CSRF, authentication và authorization.

## 1. Hiểu đúng một câu trước khi cấu hình

Khi muốn công khai **GET /public**, hai cách sau trông có thể cho cùng kết quả **200 OK**:

~~~java
// Cách A: vẫn nằm trong SecurityFilterChain
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .anyRequest().authenticated()
);
~~~

~~~java
// Cách B: bỏ qua Spring Security filters cho request được match
@Bean
WebSecurityCustomizer ignoringExample() {
    return web -> web.ignoring().requestMatchers("/public");
}
~~~

Hai đoạn trên chỉ là **snippet riêng để so sánh**, không phải cấu hình khuyến nghị áp dụng đồng thời cho cùng endpoint. Chúng có **ý nghĩa bảo mật khác nhau**:

- **permitAll():** quy tắc **authorization** nói rằng request đã khớp không cần được cấp quyền để đi tiếp. Nó **không xóa request khỏi filter chain**. Các filter khác của chain vẫn có thể xử lý request.
- **web.ignoring():** quy tắc ở mức **WebSecurity** yêu cầu Spring Security bỏ qua các request khớp. Các filter **bên trong chuỗi Spring Security** không chạy cho request ấy; Spring Security không thêm các security headers do filter của nó cung cấp.
- **Không khớp SecurityFilterChain nào:** cũng có thể khiến request không được Spring Security bảo vệ, nhưng nguyên nhân khác với một rule authorization permitAll. Đây là lỗi coverage có thể xuất hiện khi dùng **securityMatcher(...)** không đúng phạm vi.

**Kết luận kỹ thuật cần kiểm chứng:** “Public” không có nghĩa “bỏ bảo vệ”. Một endpoint cho phép anonymous đi vào vẫn có thể cần **security headers, CSRF protection, CORS integration, exception handling, request context** và những filter bảo vệ khác theo cấu hình.

## 2. Ba câu hỏi quyết định đường đi HTTP request

Với **GET /public**, phân tích theo ba tầng:

1. **Request có đi vào Spring Security không?** Tầng servlet đưa request qua DelegatingFilterProxy và FilterChainProxy; nếu request bị web.ignoring hoặc không có chain khớp thì những filter Spring Security của chain không chạy.
2. **Nếu đi vào, nó thuộc SecurityFilterChain nào?** Mỗi chain có matcher; FilterChainProxy chọn chain phù hợp đầu tiên theo thứ tự ưu tiên.
3. **Trong chain đã chọn, rule authorization nào áp dụng?** AuthorizationFilter hỏi AuthorizationManager. **permitAll()** chỉ quyết định bước này.

~~~text
Client request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    +-- web.ignoring hoặc không có chain khớp?
    |       |
    |       +--> Không chạy Spring Security filters của chain
    |             |
    |             +--> Servlet chain / DispatcherServlet / ứng dụng
    |
    +-- Có SecurityFilterChain phù hợp
            |
            +--> HeaderWriterFilter, SecurityContext, CSRF, ...
            +--> Authentication filter nếu cơ chế được bật
            +--> ExceptionTranslationFilter
            +--> AuthorizationFilter
                     |
                     +-- rule permitAll()
                     |       |
                     |       +--> Không yêu cầu authorization;
                     |             đi tiếp tới ứng dụng
                     |
                     +-- rule authenticated()/hasRole(...)
                     |       |
                     |       +--> Kiểm tra Authentication và authorities
                     |
                     +-- denyAll() --> từ chối request
~~~

Sơ đồ trên trình bày **trách nhiệm và đường đi**, không phải thứ tự đầy đủ, cố định của mọi filter. Một chain thực tế chỉ có những filter tương ứng với cấu hình của nó. Một filter có thể kết thúc response sớm và không gọi filter tiếp theo; **permitAll không bảo đảm controller chắc chắn được thực thi** nếu filter khác chặn request.

### 2.1. securityMatcher khác requestMatchers

**securityMatcher("/api/**")** chọn **phạm vi SecurityFilterChain**. **requestMatchers("/api/ping").permitAll()** định nghĩa **rule trong phạm vi chain đó**.

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Đoạn trên là **snippet minh họa**, cần lớp cấu hình và imports. Một request đến **/web/account** không khớp **securityMatcher("/api/**")**; quy tắc **anyRequest()** của apiChain **không áp dụng** cho nó. Nếu không có chain khác nhận /web/account, Spring Security không bảo vệ request đó.

Đối với ứng dụng có nhiều chain, cần **fallback chain** bao trùm mọi URL còn lại mà ứng dụng muốn bảo vệ. Đừng dùng **anyRequest().denyAll()** trong một chain giới hạn rồi tưởng nó bao phủ mọi URL của cả hệ thống.

## 3. So sánh chính xác permitAll, ignoring và các ngoại lệ khác

| Cơ chế | Vị trí cấu hình | Rule authorization | Spring Security filters cho request khớp | Security headers do Spring Security cung cấp |
| --- | --- | --- | --- | --- |
| **permitAll()** | authorizeHttpRequests | Cho phép request khớp | **Vẫn chạy** theo chain | **Có thể được thêm** theo cấu hình headers |
| **authenticated()** | authorizeHttpRequests | Đòi Authentication hợp lệ | **Vẫn chạy** | **Có thể được thêm** |
| **denyAll()** | authorizeHttpRequests | Từ chối ở bước authorization | **Vẫn đi qua các filter trước bước từ chối** | **Có thể được thêm** |
| **web.ignoring()** | WebSecurityCustomizer/WebSecurity | **Không xét rule của chain** | **Bị bỏ qua** đối với request khớp | **Không do filter Spring Security thêm** |
| **Không có chain khớp** | Phạm vi securityMatcher của các chain | **Không có rule áp dụng** | **Không chạy filter của chain** | **Không do filter Spring Security thêm** |
| **csrf.ignoringRequestMatchers(...)** | CsrfConfigurer trong HttpSecurity | **Không tự thay rule authorization** | **Vẫn chạy chain**, chỉ bỏ kiểm tra CSRF cho request khớp | **Vẫn có thể được thêm** |
| **requestMatchers(...).permitAll() trong một chain cụ thể** | authorizeHttpRequests của chain đó | Public **trong chain đã chọn** | **Vẫn chạy chain đã chọn** | Theo cấu hình của chain đó |

**Bảng cần đọc đúng phạm vi:** việc “Spring Security không thêm headers” không có nghĩa mọi response ngoài đời đều thiếu security headers. Reverse proxy, API gateway hoặc một servlet filter **không thuộc Spring Security** vẫn có thể thêm headers. Bảng chỉ mô tả những gì Spring Security làm.

**csrf.ignoringRequestMatchers** và **web.ignoring** khác nhau rất nhiều dù đều có chữ “ignoring”:
- **csrf.ignoringRequestMatchers(...)** chỉ loại trừ **một kiểm tra CSRF** trong một chain có các filter khác.
- **web.ignoring()** bỏ qua **toàn bộ Spring Security filter chain** cho request khớp.

Không dùng hai cơ chế như thể chúng tương đương nhau.

## 4. permitAll() thực sự bỏ qua điều gì?

**permitAll** thuộc cấu hình authorization, ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Khi GET /public đến **AuthorizationFilter**, rule cho phép mà **không cần đọc quyền của người dùng** để đưa ra quyết định. Từ Spring Security 6, đối với rule **permitAll**, quá trình authorization **không cần lấy Authentication từ HttpSession** chỉ để kiểm tra quyền. Đây cũng là lý do tài liệu Spring Security khuyên dùng permitAll cho static resources thay vì cố bỏ qua filter nhằm tối ưu hiệu năng.

Nhưng các bộ phận khác vẫn có trách nhiệm:

- **HeaderWriterFilter** có thể thêm security headers như **X-Content-Type-Options: nosniff**, **X-Frame-Options: DENY** theo các mặc định/phần cấu hình phù hợp.
- **CsrfFilter** vẫn kiểm tra request dùng HTTP method không an toàn, ví dụ POST, khi CSRF protection đang bật.
- **BasicAuthenticationFilter** có thể xử lý Authorization Basic header đã được gửi, kể cả khi URL đích có permitAll. Credential sai có thể bị chặn **trước khi** request tới AuthorizationFilter.
- **CorsFilter** hoặc tích hợp CORS của Spring Security (nếu cấu hình) vẫn có thể xử lý CORS preflight/response.
- **SecurityContextHolderFilter**, session/context strategy và các filter bảo vệ khác vẫn hoạt động tùy chain.
- **ExceptionTranslationFilter** có thể chuyển AuthenticationException/AccessDeniedException từ các bước phía sau thành HTTP response phù hợp.
- **LogoutFilter, OAuth2 login callbacks** hoặc filter endpoint chuyên biệt vẫn thực hiện hành vi của chúng khi request khớp URL liên quan.

Do đó phát biểu **“permitAll tắt authentication”** là không chính xác. Nó chỉ nói rằng **authorization rule này cho phép request đi tiếp mà không cần principal có quyền cụ thể**. Một cơ chế authentication có thể đã được filter thực hiện trước bước authorization hoặc được thành phần khác yêu cầu.

### 4.1. GET public và POST public có thể khác status

Giả sử ta khai báo:

~~~java
.requestMatchers(HttpMethod.GET, "/public").permitAll()
.requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
~~~

Với CSRF protection Servlet mặc định:

- **GET /public** không yêu cầu CSRF token; nếu controller hoạt động có thể trả **200**.
- **POST /public/submit** không kèm CSRF token hợp lệ thường bị **CsrfFilter trả 403**, **dù** rule authorization là **permitAll**.
- **POST /public/submit** có CSRF token hợp lệ có thể tới controller và trả **200**.
- Nếu custom CSRF policy khác, kết quả có thể khác; không được suy ra một status cố định cho mọi ứng dụng.

Đây là khác biệt mạnh nhất giữa **mở quyền truy cập URL** và **bỏ toàn bộ bảo vệ**. CSRF là một cơ chế bảo vệ request, không phải role permission.

### 4.2. Public nhưng Basic header sai vẫn có thể bị từ chối

Khi app bật HTTP Basic, một request **GET /public** không kèm Authorization có thể trả 200. Tuy nhiên request đó nếu **có Basic credentials sai**, BasicAuthenticationFilter có thể bắt credential, cố xác thực rồi trả **401** qua authentication entry point. **permitAll không bảo đảm mọi credential được gửi kèm đều bị bỏ qua**.

Điều này không mâu thuẫn: URL public không cần người dùng đăng nhập, nhưng ứng dụng vẫn có thể phát hiện và từ chối một yêu cầu xác thực không hợp lệ ở filter trước đó. Hãy kiểm tra behavior cụ thể của chain và authentication mechanism thay vì coi permitAll là công tắc tắt mọi filter.

## 5. Security headers là ví dụ dễ quan sát

Spring Security Servlet có các mặc định security headers để giảm một số rủi ro phổ biến. HeaderWriterFilter là một phần của chain quản lý chúng. Những header thường thấy gồm:

| Header | Ý nghĩa | Lưu ý khi kiểm thử |
| --- | --- | --- |
| **X-Content-Type-Options: nosniff** | Hạn chế browser đoán MIME type trái với Content-Type | Thường có theo mặc định ở Spring Security Servlet |
| **X-Frame-Options: DENY** | Hạn chế bị nhúng vào frame để giảm nguy cơ clickjacking | Mặc định thường là DENY, có thể được thay đổi |
| **Cache-Control** và các header liên quan | Giúp hạn chế caching response nhạy cảm theo cấu hình mặc định | Có thể bị application/proxy điều chỉnh |
| **Strict-Transport-Security** | Yêu cầu browser dùng HTTPS trong thời gian đã khai báo | Chỉ phù hợp với **HTTPS**; không suy ra sẽ xuất hiện trên HTTP localhost |
| **Content-Security-Policy** | Hạn chế nguồn script/style/resource | Không tự được Spring Security cấu hình với policy của riêng ứng dụng |
| **Referrer-Policy** | Kiểm soát dữ liệu referrer gửi đi | Phải chọn và cấu hình theo nhu cầu |

**Không khẳng định mọi header trong bảng đều xuất hiện mặc định.** Các header có thể được cấu hình riêng, bị tắt hoặc thay đổi theo version/hạ tầng. Khi chứng minh sự khác biệt giữa permitAll và ignoring, nên kiểm tra một header mặc định cụ thể, ví dụ **X-Content-Type-Options: nosniff** trong một app demo không có proxy và không thay cấu hình headers.

Với **web.ignoring()**, Spring Security không chạy HeaderWriterFilter cho request bị ignore. Vì vậy **không còn bảo đảm** header của Spring Security được ghi vào response đó. Một trang CSS/JS cũng nên có các header bảo vệ nhất quán với policy của ứng dụng.

### 5.1. Vì sao tài liệu khuyên permitAll cho static resources?

Đoạn cấu hình nên ưu tiên:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Các file tĩnh vẫn được phục vụ bình thường, đồng thời được hưởng những security filters/headers của chain. Trong Spring Security 6, quyết định permitAll **không cần lấy Authentication từ session cho bước authorization**, nên một lý do hiệu năng lịch sử để ưu tiên ignoring đã được giảm đáng kể.

**Không dùng web.ignoring() chỉ vì file CSS là công khai.** Cần đặc biệt cẩn thận nếu static path chứa file do người dùng upload hoặc nội dung thay đổi: ngoài authentication còn có content type, CSP, cache, access control và chính sách lưu trữ.

## 6. Ví dụ chạy được: permitAll vẫn có headers và CSRF

Ví dụ dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC**. Ứng dụng gồm:
- **GET /public**: cho phép anonymous.
- **POST /public/submit**: cũng permitAll, nhưng vẫn chịu **CSRF**.
- **GET /private**: yêu cầu authentication.
- **GET /admin**: yêu cầu **ROLE_ADMIN**.
- **GET /unlisted**: có controller nhưng không có allow rule.
- **GET /css/site.css**: static asset được permitAll và vẫn nhận security headers.

Phần 7 sẽ thêm **một cấu hình chỉ dùng trong test** để so sánh với web.ignoring; ứng dụng khi chạy bình thường không có endpoint nào bị cố tình bỏ khỏi Spring Security.

### 6.1. Dependencies và cấu trúc file

Dùng project Spring Boot 3.x có Gradle Wrapper/plugin và Java 17+, thêm vào **build.gradle** hiện hữu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là dependencies block, không phải build.gradle hoàn chỉnh. Tạo những file:

~~~text
src/main/java/com/example/permitdemo/
  PermitDemoApplication.java
  SecurityConfig.java
  DemoController.java

src/main/resources/static/css/
  site.css

src/test/java/com/example/permitdemo/
  PermitAllTest.java
  IgnoringExperimentTest.java
~~~

### 6.2. PermitDemoApplication.java

~~~java
package com.example.permitdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermitDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermitDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

~~~java
package com.example.permitdemo;

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
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/css/**").permitAll()
                .requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
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

**Điểm đáng chú ý:**

1. Không dùng **WebSecurityCustomizer** trong cấu hình ứng dụng chạy bình thường.
2. Ba rule permitAll cho public GET, static CSS và public POST **chỉ mở bước authorization**; chúng vẫn thuộc SecurityFilterChain.
3. Không gọi **csrf.disable()**; CsrfFilter tiếp tục bảo vệ POST khi không có CSRF token hợp lệ.
4. **httpBasic(...)** cho phép curl/test gửi username/password để kiểm tra các endpoint bảo vệ.
5. **anyRequest().denyAll()** chặn các endpoint chưa khai báo, kể cả khi controller có mapping.
6. **PasswordEncoder** dùng BCrypt. Mật khẩu demo chỉ dùng trên localhost; hệ thống thật cần quản lý tài khoản và secrets an toàn.

**Không gọi .sessionManagement(STATELESS)** trong demo này vì ví dụ kiểm thử CSRF dùng cơ chế mặc định và cần nêu bật sự độc lập giữa authentication/authorization/CSRF. Việc một ứng dụng API sử dụng session, Basic hay Bearer và chính sách CSRF là quyết định kiến trúc riêng; chữ “API” không tự buộc tắt CSRF.

### 6.4. DemoController.java

~~~java
package com.example.permitdemo;

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

    @PostMapping("/public/submit")
    public String publicSubmit() {
        return "submitted";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "private:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }

    @GetMapping("/unlisted")
    public String unlisted() {
        return "must-not-be-visible";
    }
}
~~~

Endpoint **/unlisted** tồn tại về mặt MVC nhưng bị fallback deny. Endpoint **/public/submit** không thay đổi dữ liệu thật, chỉ trả string để minh họa kiểm tra CSRF. Trong sản phẩm, endpoint có side effect phải có policy riêng và chống CSRF theo loại client.

### 6.5. site.css — static resource

File **src/main/resources/static/css/site.css**:

~~~css
body { font-family: sans-serif; }
~~~

Spring Boot MVC phục vụ static resource ở **/css/site.css** khi cấu hình static resources thông thường được bật. Vì path được **permitAll**, anonymous có thể tải file; và do vẫn qua SecurityFilterChain, response mặc định được áp dụng security headers.

### 6.6. Chạy thử bằng curl

Từ thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows PowerShell hoặc cmd:
gradlew.bat bootRun
~~~

Từ terminal khác thử:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/css/site.css
curl -i -X POST http://localhost:8080/public/submit
curl -i http://localhost:8080/private
curl -i -u alice:alice123 http://localhost:8080/private
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/unlisted
~~~

Kết quả **dự kiến** với ứng dụng demo và không có proxy/handler tùy biến:

| Request | HTTP | Body hoặc ý nghĩa |
| --- | --- | --- |
| GET /public (anonymous) | **200** | **public**, kèm security headers |
| GET /css/site.css (anonymous) | **200** | Nội dung CSS, kèm security headers |
| POST /public/submit, không CSRF | **403** | CsrfFilter từ chối dù POST đã permitAll |
| GET /private (anonymous) | **401** | HTTP Basic yêu cầu credential |
| GET /private (alice) | **200** | **private:alice** |
| GET /admin (alice) | **403** | ROLE_USER không đủ ROLE_ADMIN |
| GET /admin (admin) | **200** | **admin** |
| GET /unlisted (admin) | **403** | Fallback denyAll chặn trước MVC controller |

Với GET /public, hãy kiểm tra trong response phần header **X-Content-Type-Options: nosniff**. Nếu thử qua reverse proxy hoặc app có cấu hình headers tùy chỉnh, kết quả có thể khác. Không dựa vào nội dung body của 403/401 làm contract cố định nếu chưa cấu hình error handling.

**Cảnh báo khi chạy với credential thật:** Basic truyền password dưới dạng Base64 có thể giải mã; hãy sử dụng HTTPS trên mạng và không đưa password vào shell history/log. Password trong demo chỉ để học trên localhost.

## 7. Kiểm thử tích hợp phân biệt permitAll và ignoring

Các test sau không gọi trực tiếp controller để đoán kết quả. Chúng dùng **MockMvc** chạy qua filter của Spring Security, nên có thể chứng minh header writer, CSRF và authorization đã thực thi.

### 7.1. PermitAllTest.java: kiểm tra app cấu hình an toàn

File **src/test/java/com/example/permitdemo/PermitAllTest.java**:

~~~java
package com.example.permitdemo;

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermitAllTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointHasSecurityHeader() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }

    @Test
    void permittedStaticCssStillHasSecurityHeader() throws Exception {
        mvc.perform(get("/css/site.css"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }

    @Test
    void permittedPostStillRequiresCsrf() throws Exception {
        mvc.perform(post("/public/submit"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/public/submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("submitted"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("private:alice"));
    }

    @Test
    void roleIsCheckedAfterAuthentication() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void unknownRouteWithControllerIsDenied() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidBasicCredentialsCanFailOnPublicRoute()
            throws Exception {
        mvc.perform(get("/public")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Cách hiểu các kiểm thử:

- **publicEndpointHasSecurityHeader** cho thấy permitAll không bỏ qua HeaderWriterFilter.
- **permittedPostStillRequiresCsrf** là bằng chứng rằng **quyền public không vô hiệu hóa CSRF**.
- **invalidBasicCredentialsCanFailOnPublicRoute** minh họa filter authentication vẫn có thể xử lý credential được gửi trên endpoint public; khi sai, nó có thể trả 401.
- Các test **private/admin/unlisted** cho thấy việc mở public endpoint không làm mất policy của phần còn lại.
- **httpBasic(...)** trong Spring Security Test tạo Authorization header; **csrf()** tạo một CSRF token hợp lệ theo hỗ trợ MockMvc. Chúng là request post-processors phục vụ kiểm thử, không phải logic xử lý dữ liệu thật.

### 7.2. IgnoringExperimentTest.java: chứng minh hệ quả của web.ignoring

Để so sánh với cách không khuyến nghị, thêm **một cấu hình chỉ tồn tại trong test**. Cấu hình ứng dụng ở phần 6 không chứa web.ignoring, vì không nên vô tình đưa bypass vào runtime bình thường.

File **src/test/java/com/example/permitdemo/IgnoringExperimentTest.java**:

~~~java
package com.example.permitdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(IgnoringExperimentTest.IgnoreOnlyPublic.class)
class IgnoringExperimentTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class IgnoreOnlyPublic {

        @Bean
        WebSecurityCustomizer ignorePublicForExperiment() {
            return web -> web.ignoring().requestMatchers("/public");
        }
    }

    @Test
    void ignoredRouteDoesNotGetSpringSecurityHeaders()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andExpect(header().doesNotExist("X-Content-Type-Options"));
    }
}
~~~

**Tại sao viết cấu hình chỉ trong test?** Bài muốn quan sát kết quả của **web.ignoring** mà tránh đưa một bypass vào ứng dụng chính. Trong test này:

1. Spring Boot tạo context có **WebSecurityCustomizer** bổ sung, chỉ ignore **/public**.
2. Controller vẫn có thể xử lý GET /public và trả **200**.
3. Filter security headers của Spring Security không chạy cho request ignored, nên test chờ header **X-Content-Type-Options** vắng mặt.
4. Đây là kết luận với **app demo không có proxy hoặc custom header filter khác**. Nếu một thành phần khác thêm cùng header, phải phân biệt nguồn của nó.

Đó là lý do tài liệu Spring Security ưu tiên **permitAll** cho static resources. Test này cố tình dùng một cách không khuyến nghị để **quan sát sự khác biệt**, không phải cấu hình cần mang sang môi trường production.

### 7.3. Chạy test

Từ root project:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

Đây là **bộ test dự kiến cho Spring Boot 3.x + Spring Security 6.x**, không phải kết quả đã được chạy sẵn trong môi trường học. Nếu dùng Spring Boot 4 hoặc Spring Security 7, phải kiểm tra version, package test và API cấu hình cụ thể. Không suy diễn rằng một test status 200 đã đủ chứng minh endpoint được bảo vệ đúng; cần kiểm tra headers và các trường hợp âm như trên.

## 8. Cách dùng web.ignoring khi thực sự cần

**WebSecurityCustomizer** là một entry point cấu hình WebSecurity (khác HttpSecurity). Ví dụ cú pháp cơ bản:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/some-special-resource/**");
}
~~~

Đoạn trên chỉ trình bày API; **không khuyến nghị sao chép cho resources thông thường**. Khi đưa path vào **web.ignoring**, bạn đang tuyên bố rằng **mọi filter bảo vệ của Spring Security có thể được bỏ qua** trên path đó, bao gồm:

- Các filter xác thực, nạp/ghi SecurityContext theo chain.
- Rule authorization như **authenticated()**, **hasRole()**, **denyAll()**.
- **CsrfFilter** của chain, nếu áp dụng.
- **HeaderWriterFilter** và security headers do Spring Security cung cấp.
- Những cơ chế CORS/exception handling/security behavior vốn gắn với chain.

**Phạm vi cần nói chính xác:** “bỏ qua toàn bộ chuỗi bảo mật” ở đây nghĩa là **chuỗi filter của Spring Security**, không phải tắt Servlet container, Spring MVC, web server, CDN, reverse proxy, mọi filter của ứng dụng hay các kiểm soát hạ tầng bên ngoài.

Vì vậy, nếu bạn có một nhu cầu rất đặc biệt cần bỏ qua request, hãy chứng minh rằng mọi lớp bảo vệ không còn áp dụng là có chủ đích. Trong phần lớn app web, **permitAll() dễ bảo trì và an toàn hơn**.

### 8.1. Tài nguyên tĩnh

Nên viết:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Thay vì:

~~~java
// Chỉ để đối chiếu; thông thường không được ưu tiên.
web.ignoring().requestMatchers("/assets/**");
~~~

Cấu hình permitAll vẫn cho phép asset CSS/JS/image được phục vụ mà giữ các filter/header của Spring Security.

### 8.2. Health check và tài nguyên công khai

Một endpoint **GET /actuator/health** hoặc **GET /healthz** có thể cần được gọi anonymous bởi load balancer. Nếu bạn chọn mở nó, hãy đặt rule path/method rõ ràng trong chain phù hợp và giữ headers. Cẩn thận với Actuator: health/info/metrics/env không có cùng độ nhạy; không cho phép mọi **/actuator/** chỉ vì cần một health check.

Tương tự, **/login**, **/register**, **/forgot-password**, **/csrf** có thể cần được truy cập trước khi đăng nhập. **permitAll()** phù hợp hơn một bypass rộng, vì các luồng này thường chính là nơi cần CSRF, headers hoặc filters khác hoạt động.

### 8.3. CORS preflight

Một browser có thể gửi **OPTIONS preflight** trước khi gọi API với header Authorization. Cấu hình CORS đúng thường nên được tích hợp để request preflight được xử lý trước authorization khi phù hợp:

~~~java
http.cors(Customizer.withDefaults());
~~~

**Snippet** này cần CORS policy thực tế, chẳng hạn CorsConfigurationSource hoặc cấu hình MVC được Spring Security nhận diện. **Không dùng web.ignoring("/api/**")** để chữa một lỗi preflight; điều đó bỏ bảo vệ cả API. Định nghĩa allowed origins, methods, headers và credentials theo yêu cầu client.

**CORS không thay authentication hoặc authorization**. Dù browser được phép đọc response cross-origin, backend vẫn phải kiểm tra principal và quyền đối với dữ liệu.

## 9. CSRF: ba cách cấu hình hay bị nhầm

Giả sử ứng dụng có **POST /public/submit** và browser dùng session/cookie.

**Cách 1 — permitAll ở authorization:**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
    .anyRequest().authenticated()
)
~~~

Request vẫn qua CsrfFilter và cần token nếu cấu hình CSRF yêu cầu.

**Cách 2 — loại trừ chỉ kiểm tra CSRF cho một path:**

~~~java
.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhook/external")
)
~~~

Request vẫn qua Spring Security chain và vẫn chịu authentication/authorization/headers. Chỉ nên dùng khi endpoint có cơ chế xác thực và chống replay phù hợp, ví dụ webhook ký HMAC được xác minh an toàn; đây không phải cách mặc định cho toàn bộ REST API.

**Cách 3 — bỏ qua Spring Security filter chain:**

~~~java
@Bean
WebSecurityCustomizer ignoring() {
    return web -> web.ignoring().requestMatchers("/webhook/external");
}
~~~

Cách 3 bỏ qua nhiều cơ chế hơn cần thiết. Nếu chỉ muốn loại trừ CSRF, không dùng web.ignoring thay thế.

**Ghi nhớ an toàn:** CSRF chủ yếu cần xét khi browser có thể tự gắn credential (cookie/session và một số HTTP authentication). Với API xác thực thuần bằng Bearer token do client chủ động đặt Authorization header, thiết kế CSRF khác; tuy nhiên token trong cookie tự gửi vẫn cần được đánh giá. Không tự động tắt CSRF chỉ vì endpoint trả JSON hoặc được gọi “REST”.

## 10. HTTP status không nói hết filter nào đã chạy

| Tình huống | Phản hồi thường gặp | Có phải bằng chứng request đã bỏ qua chain? |
| --- | --- | --- |
| Anonymous GET /public với permitAll | **200** | **Không**; chain vẫn chạy |
| Anonymous GET /public được web.ignoring | **200** nếu controller thành công | Có thể do ignored; phải kiểm tra chain/log, không chỉ status |
| Anonymous GET /private với Basic | **401** | Request được bảo vệ và entry point yêu cầu credential |
| Logged-in USER GET /admin cần ADMIN | **403** | Xác thực được nhưng thiếu authority |
| Anonymous POST /public/submit permitAll, thiếu CSRF | **403** | CsrfFilter vẫn có thể chặn |
| GET /missing permitAll nhưng không có controller/resource | **404** | Quyền cho đi tiếp không tạo ra endpoint |
| Request không khớp chain, controller tồn tại | Có thể **200** | Không được Spring Security bảo vệ nếu không có chain khớp |
| Request sai HTTP method | Có thể **403**, **404** hoặc **405** | Tùy authorization, CSRF và mapping của MVC |

Khi debug, hãy tìm nguyên nhân theo tầng: **RequestMatcher của chain → filter authentication → CSRF/CORS → rule authorization → controller/service**. Status 200 không chứng minh bảo mật đúng, còn 403 không nhất thiết là role rule (có thể CSRF).

### 10.1. permitAll với request error/forward

Servlet có thể tạo **ERROR** hoặc **FORWARD** dispatch khi xử lý lỗi hoặc view. Với các bản Spring Security hiện đại, authorization có thể được áp dụng tới dispatcher types theo cấu hình. Nếu muốn cho phép **ERROR/FORWARD** chỉ ở mức cần thiết, có thể thiết kế:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public").permitAll()
    .anyRequest().authenticated()
)
~~~

Đây là **snippet** cần import **jakarta.servlet.DispatcherType** và phải đánh giá đúng nhu cầu ứng dụng. Cho phép một dispatcher type ở bước authorization **không đồng nghĩa bỏ qua mọi filter**; cũng không được lấy việc hiển thị trang lỗi làm lý do cho phép mọi business endpoint.

## 11. Vì sao không nên tối ưu bằng cách ignore quá rộng?

Các lý do trước đây khiến nhiều người bỏ qua static resources thường là:

- Lo mỗi request static phải lấy session/principal từ database.
- Muốn tránh overhead của SecurityFilterChain.
- Muốn dùng cùng một cấu hình cho toàn bộ CSS/JS/image công khai.

Trong Spring Security 6, **permitAll/denyAll authorization không yêu cầu lấy Authentication từ session chỉ để đưa ra quyết định**, do đó lý do tối ưu hiệu năng bằng ignoring thường không còn mạnh như trước. Vẫn có chi phí filter riêng và hạ tầng, nhưng không thể kết luận rằng “ignore luôn nhanh hơn nên an toàn tương đương”.

Để đánh giá hiệu năng, nên:

1. Profile request path thực tế, xác định filter/DB/cache nào đang tốn chi phí.
2. Dùng **permitAll** cho static assets và đo performance.
3. Tối ưu static resource caching, CDN, compression và servlet handling hợp lý.
4. Kiểm tra chính sách security headers và cache policy có được giữ đúng không.
5. Chỉ thay đổi cơ chế bỏ qua chain khi có lý do đã được đánh giá và được test bằng behavior thực.

**Tối ưu hiệu năng không được âm thầm thay đổi ranh giới bảo mật.**

## 12. Nhiều SecurityFilterChain: tránh lỗ hổng không khớp chain

Giả sử một ứng dụng có chain chỉ cho **/api/**:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Nếu đây là chain duy nhất, các request ngoài **/api/** không được bảo vệ bởi chain đó. Để có fallback, thêm chain khác:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        );
    return http.build();
}
~~~

Hai đoạn trên là **snippet cho kiến trúc nhiều chain**, không phải cấu hình ghép thêm vào demo phần 6. Cần imports **Bean**, **Order**, **HttpSecurity**, **SecurityFilterChain**, **Customizer**. Nếu fallback denyAll được dùng, phải thêm các ngoại lệ có chủ đích cho static, login, error dispatch, Actuator, CORS và các endpoint framework thực sự cần phục vụ.

Điều cần phân biệt:
- **permitAll:** request vẫn thuộc chain đã chọn và qua các filter của chain.
- **web.ignoring:** bỏ qua các filter Spring Security đối với request được ignore.
- **request không khớp chain:** request không được bảo vệ vì cấu hình coverage thiếu, cho dù bạn đã đặt denyAll bên trong các chain khác.

Một project lớn cần test URL nằm **trong và ngoài** mỗi matcher, đồng thời kiểm tra thứ tự **@Order**.

## 13. Những lỗi thường gặp

### 13.1. Nghĩ permitAll là “không đi qua Spring Security”

Sai. permitAll là một quyết định authorization. Các filter trước/khác bước authorization vẫn có thể thực thi. Một POST permitAll vẫn có thể bị CSRF từ chối; security headers vẫn có thể được ghi.

### 13.2. Dùng web.ignoring cho CSS/JS mà không xét headers

Khi Spring Security không chạy HeaderWriterFilter, nó không thêm headers cho các response ignored. Hãy dùng permitAll cho static resources nếu không có lý do rõ ràng để bỏ cả chain.

### 13.3. Cho mọi /api/** permitAll để chữa lỗi 401

Điều này có thể mở cả endpoint riêng tư. Hãy xác định authentication mechanism, credential và authorization rule bị sai; chỉ mở chính xác tài nguyên public, theo HTTP method nếu cần.

### 13.4. Tắt CSRF vì POST permitAll vẫn 403

**CsrfFilter** bảo vệ khỏi request giả mạo, độc lập với rule permitAll. Trước khi thay policy, cần biết browser có tự gắn session cookie/Basic credential hay không và endpoint có side effect gì.

### 13.5. Nhầm csrf.ignoringRequestMatchers với web.ignoring

Một cái chỉ bỏ kiểm tra CSRF, một cái bỏ Spring Security filters. Chỉ dùng ngoại lệ CSRF được thiết kế theo threat model và test đầy đủ authentication/authorization còn lại.

### 13.6. Đặt anyRequest().permitAll cuối chain mà không phân loại endpoint

Dễ mở tất cả đường dẫn mới không chủ ý. Với API có dữ liệu nhạy cảm, ưu tiên allowlist rõ ràng và fallback authenticated/denyAll theo chính sách.

### 13.7. Đặt securityMatcher quá hẹp rồi tưởng denyAll bảo vệ toàn app

DenyAll của một chain không bao phủ URL ngoài matcher. Cần một chain fallback khớp mọi request còn lại nếu muốn bảo vệ toàn servlet application.

### 13.8. Nghĩ permitAll bỏ qua việc xử lý credential sai

Khi bật HTTP Basic, credential sai có thể bị filter xác thực từ chối trước bước authorization. Nếu muốn xử lý request public có credential khác hoặc invalid credential theo cách riêng, phải hiểu rõ cơ chế filter và thiết kế có chủ đích.

### 13.9. Nghĩ mọi 200/401/403 thể hiện cùng một nguyên nhân

200 chỉ cho biết controller hoặc hạ tầng trả thành công, không cho biết chain có chạy; 401 thường authentication; 403 thường authorization hoặc CSRF; 404 có thể do không có mapping. Cần log và test theo tầng.

### 13.10. Trả nguyên static file do user upload theo path public

Ngay cả khi route permitAll, phải xét quyền đọc object, MIME sniffing, executable content, cache, CSP, malware scanning và quản lý đường dẫn. Một file được gọi “static” không tự an toàn khi public.

### 13.11. Không test Spring Security headers

Chỉ kiểm tra body CSS/HTML trả 200 dễ bỏ sót việc bỏ toàn bộ chain. Khi thay config, hãy test ít nhất một header bảo vệ quan trọng ở public endpoint cùng response headers ở các endpoint nhạy cảm.

### 13.12. Cấu hình test khác production mà không nhận ra

Nếu test dùng WebSecurityCustomizer tắt chain, các assertion security headers/CSRF có thể không đại diện runtime thật. Bài này cố tình tách **IgnoringExperimentTest** như một thí nghiệm có nhãn rõ; production configuration vẫn dùng permitAll.

## 14. Checklist kiểm tra khi công khai endpoint

Khi thêm một endpoint public, hãy trả lời:

1. **Endpoint có thực sự cần public không?** Chỉ mở đường dẫn và HTTP method cần thiết.
2. **Request thuộc SecurityFilterChain nào?** Có securityMatcher hoặc @Order làm lệch chain không?
3. **Dùng permitAll hay bypass chain?** Mặc định ưu tiên **permitAll**.
4. **Security headers có còn được ghi?** Kiểm tra X-Content-Type-Options và các header app thực sự cần.
5. **Endpoint có side effect không?** POST/PUT/DELETE cần xem CSRF và quyền riêng, kể cả khi cho anonymous.
6. **Filter authentication có thể nhận credential không?** Đừng giả định permitAll vô hiệu hóa Basic/Bearer.
7. **Có CORS preflight không?** Xử lý origin/method/header đúng, không bỏ bảo vệ cả API.
8. **Có rule denyAll/authenticated cho phần còn lại không?** Mở một endpoint public không được mở endpoint khác.
9. **Có error dispatch/Actuator/static login assets không?** Thiết kế ngoại lệ hẹp cho hành vi framework cần thiết.
10. **Có negative tests không?** Kiểm tra anonymous, credential sai, thiếu role, sai HTTP method và endpoint chưa được khai báo.

### 14.1. Một bộ test nên có tối thiểu

| Điều cần chứng minh | Request/test |
| --- | --- |
| Public endpoint vẫn trong chain | GET /public trả 200 **và có X-Content-Type-Options** |
| Static asset vẫn có headers | GET /css/site.css trả 200 và có security header |
| CSRF không bị permitAll bỏ qua | POST /public/submit không có CSRF trả 403 |
| CSRF hợp lệ được xử lý | POST /public/submit với csrf() trả 200 |
| Endpoint riêng tư được bảo vệ | GET /private anonymous trả 401 trong Basic chain |
| Role vẫn có hiệu lực | ROLE_USER gọi GET /admin trả 403 |
| Fallback deny vẫn có hiệu lực | GET /unlisted kể cả ADMIN trả 403 |
| Ignoring có hệ quả khác biệt | Trong test-only ignore /public, security header của Spring Security vắng mặt |

**Sự khác biệt cần được xác minh bằng hành vi của filter**, không chỉ câu hỏi “URL public có trả 200 hay không”.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Đặt **requestMatchers("/public").permitAll()** có làm request bỏ qua SecurityFilterChain không?

**Đáp:** Không. Nó chỉ cho phép ở bước authorization; security filters vẫn có thể chạy.

**Câu 2.** Vì sao endpoint **GET /css/site.css** nên dùng permitAll hơn web.ignoring?

**Đáp:** File tĩnh vẫn được public nhưng có thể nhận security headers của Spring Security. Với ignoring, HeaderWriterFilter không chạy cho request bị ignore.

**Câu 3.** POST endpoint đã permitAll nhưng không có CSRF token, nhận 403. Đây có mâu thuẫn không?

**Đáp:** Không. permitAll là rule authorization; CsrfFilter độc lập vẫn có thể chặn unsafe method.

**Câu 4.** Một GET public có Basic header sai có thể nhận 401 không?

**Đáp:** Có. Nếu BasicAuthenticationFilter xử lý credential được gửi và xác thực thất bại trước AuthorizationFilter, entry point có thể trả 401.

**Câu 5.** **csrf.ignoringRequestMatchers("/webhook")** có bỏ các security headers và authentication cho /webhook không?

**Đáp:** Không. Nó chỉ loại trừ kiểm tra CSRF cho request khớp trong chain; các filter/rule khác vẫn áp dụng.

**Câu 6.** Chỉ có chain **securityMatcher("/api/**")**, đặt anyRequest().denyAll(). Request /admin có chắc bị chặn không?

**Đáp:** Không. Nếu /admin ngoài chain và không có fallback, nó có thể không được Spring Security bảo vệ.

**Câu 7.** Hai endpoint đều trả 200, có chứng minh chúng được bảo vệ tương đương không?

**Đáp:** Không. Một request có thể trả 200 sau khi qua chain permitAll, request khác có thể trả 200 vì bị ignoring hoặc không khớp chain. Cần kiểm tra filters/headers/log.

**Câu 8.** Dùng web.ignoring có tắt mọi filter của Servlet container và proxy không?

**Đáp:** Không. Nó bỏ filter bảo vệ do Spring Security áp dụng cho request khớp, không vô hiệu hóa toàn bộ hạ tầng HTTP.

**Câu 9.** Điều gì thay đổi về session lookup khi dùng permitAll ở Spring Security 6?

**Đáp:** Riêng bước authorization của permitAll không cần lấy Authentication từ session để quyết định cho phép. Những filter/cơ chế khác vẫn có thể cần session tùy cấu hình và request.

**Câu 10.** Cách phù hợp để public health check nhưng giữ security headers là gì?

**Đáp:** Cho phép đúng URL/method health check qua **permitAll** trong chain phù hợp; tiếp tục bảo vệ các actuator endpoint nhạy cảm và kiểm tra health response thực tế.

## Tài liệu chính thức

- Spring Security 6.5 — **Authorize HttpServletRequests**, mục **Favor permitAll over ignoring**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — **Java Configuration / Choosing securityMatcher or requestMatchers**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — **Servlet Architecture / FilterChainProxy**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — **Security HTTP Response Headers**: https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security — **Cross Site Request Forgery (CSRF)**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — **HTTP Basic Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **Web Security Customizer API**: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/config/annotation/web/configuration/WebSecurityCustomizer.html

**Điểm nhớ cuối:** **permitAll = được phép tại bước authorization trong một SecurityFilterChain; web.ignoring = bỏ các filter Spring Security cho request khớp**. Vì vậy, với endpoint công khai và static assets thông thường, hãy **giữ chain và dùng permitAll**, đồng thời kiểm thử security headers, CSRF, authentication và chính sách của các endpoint còn lại.
