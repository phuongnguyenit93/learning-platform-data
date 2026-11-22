# HttpServletRequest.getUserPrincipal(), getRemoteUser() và isUserInRole trong Spring Security Servlet

## 1. Tổng quan

Trong Spring MVC (Servlet stack), HttpServletRequest cung cấp ba phương thức liên quan đến danh tính và vai trò của người đang gửi request:

~~~java
Principal principal = request.getUserPrincipal();
String name = request.getRemoteUser();
boolean admin = request.isUserInRole("ADMIN");
~~~

Đây là ba lời gọi minh họa bên trong phương thức đã có biến HttpServletRequest request; cần import java.security.Principal. Ba phương thức **đều thuộc chuẩn Servlet**, không phải API do Spring Security tự sáng tạo. Tuy nhiên, Spring Security có thể liên kết chúng với Authentication đang được lưu trong SecurityContext, giúp ứng dụng MVC hay code Servlet cũ đọc trạng thái xác thực một cách quen thuộc.

Bài học áp dụng cho Java 17+, Spring Boot 3.x, Spring Security 6.x và Spring MVC. WebFlux có mô hình SecurityContext và request khác, không dùng trực tiếp các ví dụ Servlet này.

Sau bài này, cần hiểu chính xác ba giá trị trả về, trường hợp anonymous, sự khác biệt giữa Principal và Authentication, quy tắc ROLE_, cách cấu hình SecurityFilterChain và cách kiểm thử bằng MockMvc.

## 2. Bảng so sánh ba phương thức

| Phương thức | Kiểu trả về | Ý nghĩa | Khi chưa xác thực |
| --- | --- | --- | --- |
| getUserPrincipal() | java.security.Principal | Đối tượng danh tính theo Servlet request | Thông thường null |
| getRemoteUser() | String | Tên principal của request | Thông thường null |
| isUserInRole("ADMIN") | boolean | Có role ADMIN trong ngữ cảnh Servlet hay không | false |

**Remote user không phải remote address.** getRemoteUser trả username/principal name; getRemoteAddr trả địa chỉ IP từ góc nhìn container. Khi request đi qua proxy, remote address còn phụ thuộc topology và forwarded-header trust policy.

Trong cấu hình Spring Security Servlet mặc định, getUserPrincipal thường trả Authentication, getRemoteUser thường trả Authentication.getName(), còn isUserInRole dựa trên GrantedAuthority cùng role prefix. Đây là behavior của **Spring Security servlet request wrapper**. Nếu request không đi qua Spring Security hoặc dùng custom wrapper, kết quả có thể khác.

## 3. Principal, Authentication và principal bên trong Authentication

Spring Security Authentication là một interface **kế thừa Principal**. Authentication chứa nhiều thông tin hơn một Principal thuần:

~~~text
Authentication
  getName()           -> tên định danh của chủ thể
  getPrincipal()      -> object principal bên trong
  getAuthorities()    -> danh sách GrantedAuthority
  getCredentials()    -> credentials, có thể đã bị xóa
  getDetails()        -> dữ liệu phụ trợ
  isAuthenticated()   -> cờ trạng thái của Authentication
~~~

Cần phân biệt:

- **request.getUserPrincipal()**: Principal do Servlet request trả ra; với Spring Security wrapper thường là chính Authentication.
- **authentication.getPrincipal()**: object nằm **bên trong** Authentication, có thể là UserDetails khi dùng login bằng username/password, Jwt khi dùng Resource Server JWT hoặc một custom object.
- **authentication.getName()**: String đại diện tên principal, không bảo đảm là email hoặc khóa người dùng toàn hệ thống.

Mã minh họa có kiểm tra kiểu:

~~~java
Principal principal = request.getUserPrincipal();

if (principal instanceof Authentication authentication) {
    String name = authentication.getName();
    Object innerPrincipal = authentication.getPrincipal();
    Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
}
~~~

Cần import Principal, Collection, Authentication và GrantedAuthority. Đây là đoạn mã đặt trong method, không phải file Java độc lập.

**Lỗi ép kiểu thường gặp:**

~~~java
UserDetails user = (UserDetails) request.getUserPrincipal();
~~~

Với Spring Security, giá trị Servlet request trả thường là Authentication, chứ không trực tiếp là UserDetails. Để lấy UserDetails, dùng Authentication.getPrincipal() và kiểm tra kiểu, hoặc @AuthenticationPrincipal với đúng authentication mechanism. Nếu request dùng JwtAuthenticationToken thì principal bên trong thường là Jwt, không phải UserDetails.

## 4. SecurityContextHolderAwareRequestFilter

Spring Security lưu Authentication của request trong **SecurityContext**. SecurityContextHolder cho phép các phần của ứng dụng truy cập security context trong ngữ cảnh xử lý phù hợp. Nhưng chuẩn Servlet API có ba phương thức về user và role. Để hai thế giới khớp nhau, Spring Security dùng **SecurityContextHolderAwareRequestFilter**.

Filter này bọc HttpServletRequest thành một request wrapper có cách hiện thực getUserPrincipal, getRemoteUser và isUserInRole dựa trên Authentication của Spring Security.

Luồng khái quát:

~~~text
Client request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy -> SecurityFilterChain
    |
    +--> SecurityContext management
    |
    +--> HTTP Basic / form / Bearer authentication
    |         |
    |         v
    |     SecurityContext có Authentication
    |
    +--> SecurityContextHolderAwareRequestFilter
    |         |
    |         v
    |     Servlet request wrapper
    |
    +--> AuthorizationFilter
    |
    v
DispatcherServlet -> Controller
       |
       +--> request.getUserPrincipal()
       +--> request.getRemoteUser()
       +--> request.isUserInRole("ADMIN")
~~~

Sơ đồ mô tả vai trò chức năng, không cố liệt kê mọi filter hoặc bảo đảm thứ tự tuyệt đối của các filter bổ sung trong mọi cấu hình. Một request bị filter từ chối có thể không đi tới controller.

Không cần tự thêm filter này theo cách viết một GenericFilterBean tùy biến chỉ để đọc principal. Cấu hình Spring Security Servlet chuẩn đã cung cấp integration cần thiết. Không nên tự set Authentication trong controller chỉ để khiến ba API hoạt động.

## 5. getUserPrincipal() và request anonymous

Trong request đã được xác thực bằng form login hoặc HTTP Basic, getUserPrincipal thường trả **UsernamePasswordAuthenticationToken**, một implementation của Authentication. Nó có getName là username và getPrincipal bên trong có thể là UserDetails.

Trong ứng dụng OAuth 2.0 Resource Server JWT, getUserPrincipal có thể trả **JwtAuthenticationToken**. Các JWT claims phải được lấy từ Jwt bên trong và chỉ đáng tin sau khi decoder xác minh signature, issuer, audience và thời hạn.

Với request chưa đăng nhập, Servlet API thường trả null:

~~~java
Principal principal = request.getUserPrincipal();

if (principal == null) {
    // Không có principal đã xác thực ở góc nhìn Servlet.
} else {
    String name = principal.getName();
}
~~~

Spring Security có thể chứa **AnonymousAuthenticationToken** trong SecurityContext ngay cả khi Servlet request trả null. AnonymousAuthenticationToken không đại diện một tài khoản đã xác thực thật. Request wrapper nhận biết anonymous và thường không trả nó như getUserPrincipal của request.

Vì vậy không nên suy luận rằng SecurityContextHolder.getContext().getAuthentication() khác null nghĩa là người dùng đã đăng nhập. Cần phân biệt anonymous, authentication thực và authorization rules.

## 6. getRemoteUser() và định danh

**getRemoteUser()** thường trả Authentication.getName() của người dùng đã được xác thực, hoặc null nếu request không có principal được nhận diện theo Servlet API.

~~~java
String remoteUser = request.getRemoteUser();

if (remoteUser == null) {
    // Có thể là request vô danh.
}
~~~

Với người dùng alice đã đăng nhập, request.getUserPrincipal().getName() và request.getRemoteUser() thường cùng là "alice". Nhưng giá trị không mặc nhiên là username bất biến hoặc email.

Với JWT, getName thường xuất phát từ claim sub hoặc được JwtAuthenticationConverter tùy chỉnh. Nếu issuer A và issuer B cùng cấp sub="42", hai người dùng ở hai tổ chức có thể cùng getRemoteUser()="42". Không sử dụng duy nhất chuỗi này để liên kết tài khoản hoặc phân quyền đa tenant. Phân biệt bằng issuer+subject hoặc ID nội bộ đã ánh xạ và xác thực.

Khi audit, ghi request ID, principal đáng tin, issuer/tenant và hành động theo quy trình bảo mật; không ghi raw Bearer token, Authorization header hay mật khẩu.

## 7. isUserInRole() và ROLE_ prefix

Trong Spring Security Servlet integration mặc định, role ADMIN thường tương ứng authority **ROLE_ADMIN**. Một Authentication có:

~~~text
ROLE_USER
ROLE_ADMIN
SCOPE_reports.read
~~~

sẽ có kết quả điển hình:

~~~java
request.isUserInRole("USER");   // true
request.isUserInRole("ADMIN");  // true
request.isUserInRole("AUDIT");  // false
~~~

Cách truyền **"ADMIN"** là cách dùng tự nhiên của Servlet role API. Không coi mọi GrantedAuthority là role: một JWT có authority SCOPE_admin không mặc nhiên có ROLE_ADMIN; isUserInRole("ADMIN") thường false nếu thiếu authority role tương ứng.

Đặt các kiểu rule cạnh nhau:

~~~java
// Servlet API role check trong method có biến request:
request.isUserInRole("ADMIN");

// Request authorization rule trong HttpSecurity:
auth.requestMatchers("/admin/**").hasRole("ADMIN");

// Authority check chính xác:
auth.requestMatchers("/reports/**")
    .hasAuthority("SCOPE_reports.read");
~~~

Đây là các mảnh mã độc lập được dùng trong ngữ cảnh khác nhau. Khi ứng dụng tùy chỉnh prefix, role hierarchy hoặc authority converter, các điểm kiểm tra có thể không luôn đồng nhất. Cần test thực tế với Authentication của ứng dụng.

**isUserInRole chỉ trả boolean.** Một controller gọi nó rồi bỏ qua kết quả không chặn được request. Quy tắc bảo mật cho endpoint nhạy cảm nên ở SecurityFilterChain, method security hoặc service authorization; role check trong controller có thể dùng để tương thích với Servlet API cũ hoặc lựa chọn nội dung hiển thị.

## 8. Ví dụ Spring Boot 3, Spring Security 6 hoàn chỉnh

Ứng dụng minh họa dùng HTTP Basic và hai user trong bộ nhớ:

- Alice: ROLE_USER và ROLE_ADMIN.
- Bob: ROLE_USER.
- /mvc/public: công khai, có thể quan sát cả anonymous và authenticated.
- /mvc/secure: yêu cầu authentication.
- /mvc/admin: yêu cầu ROLE_ADMIN.

### 8.1. Dependency

Trong build.gradle của dự án Spring Boot có plugin/BOM tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 8.2. Lớp khởi động

File src/main/java/demo/servletapi/ServletApiDemoApplication.java:

~~~java
package demo.servletapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletApiDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletApiDemoApplication.class, args);
    }
}
~~~

### 8.3. SecurityFilterChain và demo users

File src/main/java/demo/servletapi/SecurityConfig.java:

~~~java
package demo.servletapi;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/mvc/public").permitAll()
                .requestMatchers("/mvc/secure").authenticated()
                .requestMatchers("/mvc/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .roles("USER", "ADMIN")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

Đây chỉ là demo, không phải cách lưu tài khoản thật trên production. User.withUsername(...).roles("ADMIN") tạo authority ROLE_ADMIN theo mặc định. Mật khẩu demo không được dùng cho tài khoản thực; production phải có identity store và chính sách credentials phù hợp.

Ví dụ giữ nguyên CSRF protection mặc định. Các thao tác ở đây chỉ dùng GET; với các request thay đổi trạng thái phải đánh giá CSRF theo mô hình browser/cookie/authentication thực tế. HTTP Basic chỉ nên sử dụng qua HTTPS ngoài môi trường localhost được kiểm soát.

### 8.4. Controller sử dụng cả ba API

File src/main/java/demo/servletapi/IdentityController.java:

~~~java
package demo.servletapi;

import jakarta.servlet.http.HttpServletRequest;
import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mvc")
public class IdentityController {

    @GetMapping("/public")
    public Identity publicInfo(HttpServletRequest request) {
        return inspect(request);
    }

    @GetMapping("/secure")
    public Identity secureInfo(HttpServletRequest request) {
        return inspect(request);
    }

    @GetMapping("/admin")
    public Identity adminInfo(HttpServletRequest request) {
        return inspect(request);
    }

    private static Identity inspect(HttpServletRequest request) {
        Principal principal = request.getUserPrincipal();
        String remoteUser = request.getRemoteUser();

        return new Identity(
            principal == null ? "NONE" : principal.getName(),
            remoteUser == null ? "NONE" : remoteUser,
            request.isUserInRole("USER"),
            request.isUserInRole("ADMIN")
        );
    }

    public record Identity(
        String principal,
        String remoteUser,
        boolean userRole,
        boolean adminRole
    ) {}
}
~~~

Hai giá trị null được chuyển sang "NONE" **chỉ để kết quả JSON dễ quan sát**. Servlet API không tự trả "NONE". Controller không có if để chặn /mvc/admin, vì hasRole("ADMIN") đã bảo vệ endpoint trước khi controller chạy.

### 8.5. Chạy và kết quả

Với Gradle wrapper của dự án:

~~~bash
./gradlew bootRun
~~~

Gọi request vô danh:

~~~bash
curl -s http://localhost:8080/mvc/public
~~~

JSON tương đương:

~~~json
{
  "principal": "NONE",
  "remoteUser": "NONE",
  "userRole": false,
  "adminRole": false
}
~~~

Với Alice:

~~~bash
curl -s -u alice:demo-password http://localhost:8080/mvc/public
~~~

JSON tương đương:

~~~json
{
  "principal": "alice",
  "remoteUser": "alice",
  "userRole": true,
  "adminRole": true
}
~~~

Với Bob:

~~~bash
curl -s -u bob:demo-password http://localhost:8080/mvc/public
~~~

JSON tương đương:

~~~json
{
  "principal": "bob",
  "remoteUser": "bob",
  "userRole": true,
  "adminRole": false
}
~~~

Thứ tự key JSON có thể khác tùy serializer. Để kiểm tra authorization:

~~~bash
curl -i http://localhost:8080/mvc/secure
curl -i -u bob:demo-password http://localhost:8080/mvc/secure
curl -i -u bob:demo-password http://localhost:8080/mvc/admin
curl -i -u alice:demo-password http://localhost:8080/mvc/admin
~~~

Kỳ vọng trong cấu hình đơn giản: thiếu authentication vào /mvc/secure thường 401; Bob vào /mvc/secure 200; Bob vào /mvc/admin 403; Alice vào /mvc/admin 200. Cần sử dụng HTTPS khi thử credentials trên máy/host ngoài localhost.

## 9. Kiểm thử MockMvc

Thêm spring-security-test như phần dependency, rồi tạo src/test/java/demo/servletapi/IdentityControllerTest.java:

~~~java
package demo.servletapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAnonymous() throws Exception {
        mvc.perform(get("/mvc/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("NONE"))
            .andExpect(jsonPath("$.remoteUser").value("NONE"))
            .andExpect(jsonPath("$.userRole").value(false))
            .andExpect(jsonPath("$.adminRole").value(false));
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER", "ADMIN"})
    void loggedInAdminOnPublicEndpoint() throws Exception {
        mvc.perform(get("/mvc/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"))
            .andExpect(jsonPath("$.remoteUser").value("alice"))
            .andExpect(jsonPath("$.userRole").value(true))
            .andExpect(jsonPath("$.adminRole").value(true));
    }

    @Test
    void secureEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/mvc/secure"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobIsForbiddenFromAdmin() throws Exception {
        mvc.perform(get("/mvc/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER", "ADMIN"})
    void aliceIsAllowedIntoAdmin() throws Exception {
        mvc.perform(get("/mvc/admin"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.adminRole").value(true));
    }
}
~~~

Các test xác nhận behavior của Servlet request wrapper, anonymous, role prefix và authorization. **@WithMockUser giả lập Authentication**, không xác thực mật khẩu thật hay kiểm tra chữ ký JWT. Khi cần chứng minh HTTP Basic từ HTTP client hoặc Resource Server Bearer hoạt động end-to-end, hãy thêm integration test dùng credential/token và môi trường phù hợp.

Chạy test khi dự án có Gradle wrapper:

~~~bash
./gradlew test
~~~

Kỳ vọng năm test pass trong cấu hình trên; output console Gradle thực tế phụ thuộc plugin và môi trường, không có stdout cố định.

## 10. So sánh với Principal, Authentication và @AuthenticationPrincipal trong MVC

Spring MVC hỗ trợ các tham số/thành phần khác ngoài HttpServletRequest:

| Cách lấy | Nội dung | Gợi ý |
| --- | --- | --- |
| request.getUserPrincipal() | Principal, thường là Authentication | Tích hợp code Servlet |
| request.getRemoteUser() | Tên principal | Hiển thị tên hoặc audit có kiểm soát |
| request.isUserInRole() | Boolean role check | Legacy Servlet role APIs |
| Controller argument Principal | Principal | Cần tên, không cần biết Authentication cụ thể |
| Controller argument Authentication | Authentication và authorities | Cần chi tiết Spring Security |
| @AuthenticationPrincipal UserDetails | UserDetails bên trong Authentication | Username/password nếu principal là UserDetails |
| @AuthenticationPrincipal Jwt | Jwt bên trong JWT Authentication | Resource Server JWT |
| SecurityContextHolder | Authentication | Lớp không có HttpServletRequest nhưng có security context |

Ví dụ controller nhận Principal:

~~~java
@GetMapping("/greeting")
public String greeting(Principal principal) {
    return principal == null
        ? "Hello guest"
        : "Hello " + principal.getName();
}
~~~

Ví dụ controller nhận UserDetails:

~~~java
@GetMapping("/profile")
public String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

Đó là hai method rời đặt trong controller với imports tương ứng. Không dùng UserDetails cho JWT nếu principal thực sự là Jwt. Không xem getName là ID global bất biến khi có nhiều issuer.

## 11. Phân biệt role check với authorization bắt buộc

Trong Spring Security, request.isUserInRole("ADMIN") chỉ trả về true hoặc false. Một lời gọi bị bỏ qua không bảo vệ dữ liệu. Các endpoint nhạy cảm nên được kiểm soát bằng:

- **authorizeHttpRequests** trong SecurityFilterChain;
- **@PreAuthorize** và method security khi bật @EnableMethodSecurity;
- **object-level authorization** trong service/business layer, ví dụ quyền với đúng đơn hàng hoặc tài liệu.

Ví dụ method security:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteOrder(long orderId) {
    // Service còn có thể phải kiểm tra quyền trên orderId.
}
~~~

Đây là method minh họa, không phải file chạy riêng. @PreAuthorize chỉ có hiệu lực khi method security được kích hoạt và method được gọi qua cơ chế Spring proxy phù hợp.

Role ADMIN không tự đảm bảo quyền trên mọi bản ghi trong hệ thống đa tenant. Principal đã xác thực cũng không tự động có quyền đọc tài nguyên của người khác chỉ vì endpoint đó yêu cầu authenticated().

## 12. Trường hợp dễ sai khi tích hợp thực tế

**Public endpoint vẫn có principal:** permitAll cho phép khách truy cập nhưng không loại bỏ Authentication đã có. Alice gửi credentials tới public endpoint vẫn có thể thấy tên Alice và ROLE_ADMIN.

**SecurityContext có AnonymousAuthenticationToken:** token anonymous không phải chứng nhận một người thật đã đăng nhập; Servlet wrapper thường trả null cho principal của anonymous.

**Request bypass Spring Security:** khi cấu hình ignoring hoặc servlet filter mapping không bao phủ một route, các phương thức Servlet có thể phản ánh container authentication hay wrapper khác. Với URL public nhưng vẫn muốn các security filters khác, thường nên dùng permitAll thay vì bypass.

**Custom HttpServletRequestWrapper:** một filter custom override getUserPrincipal/getRemoteUser/isUserInRole sai cách có thể che giá trị do Spring Security cung cấp. Cần kiểm tra filter order và delegation.

**Nhiều SecurityFilterChain:** /api/** có thể dùng Bearer, /mvc/** dùng Basic hoặc form login; kiểu Authentication trong controller khác nhau. Không ép tất cả thành UsernamePasswordAuthenticationToken.

**Async/background thread:** SecurityContextHolder thường gắn với ngữ cảnh xử lý hiện tại; @Async, Executor hoặc thread khác không mặc nhiên có cùng Authentication. Không giữ HttpServletRequest để dùng sau khi request kết thúc. Nếu cần truyền security context, dùng cơ chế delegation được Spring Security hỗ trợ hoặc truyền thông tin nghiệp vụ đã được xác thực.

**Header X-Remote-User:** client có thể tự gửi header chứa username. Không coi nó là getRemoteUser hợp lệ nếu chưa có trust boundary và pre-authentication thực sự được kiểm soát bởi hệ thống.

## 13. Các lỗi thường gặp

1. **Gọi getUserPrincipal().getName() không check null:** gây NullPointerException ở request anonymous. Sửa bằng kiểm tra null hoặc dùng getRemoteUser an toàn.
2. **Ép getUserPrincipal thành UserDetails:** trong Spring Security Servlet thường cần Authentication.getPrincipal(), không phải Principal của Servlet.
3. **Nhầm remote user với IP:** getRemoteUser là username; getRemoteAddr liên quan địa chỉ mạng.
4. **Dùng remoteUser làm ID global:** tên/sub có thể trùng giữa issuer hoặc thay đổi; cần namespace và ánh xạ nội bộ.
5. **Nhầm ROLE_ với SCOPE_:** OAuth scope không tự chuyển thành role của Servlet.
6. **Chỉ chặn bằng if trong controller:** đặt authorization policy ở SecurityFilterChain/method/service để hạn chế sai sót.
7. **Xem permitAll như anonymous-only:** người dùng đã xác thực vẫn có principal.
8. **Tin vào isAuthenticated của anonymous token:** không chứng minh có người dùng đăng nhập thật.
9. **Quên custom wrapper/filter order:** kiểm tra Servlet integration và security chain.
10. **Dùng @WithMockUser để chứng minh JWT/Basic credential thật hợp lệ:** MockMvc postprocessor không test toàn bộ quá trình authentication.
11. **Chấp nhận header nhận dạng client tự đưa:** không tin X-User hoặc X-Remote-User nếu không có xác thực pre-auth đáng tin.
12. **Bỏ qua ownership:** role chung không thay thế kiểm tra quyền trên đối tượng cụ thể.

## 14. Checklist và tổng kết

- [ ] Phân biệt Principal trả từ Servlet API với Authentication.getPrincipal().
- [ ] Kiểm tra null cho getUserPrincipal và getRemoteUser trên request vô danh.
- [ ] Hiểu getRemoteUser là tên định danh, không phải IP.
- [ ] Hiểu ROLE_ADMIN, ROLE_USER và sự khác biệt với SCOPE_x.
- [ ] Xác nhận SecurityContextHolderAwareRequestFilter và SecurityFilterChain thực sự xử lý request.
- [ ] Không coi AnonymousAuthenticationToken là người đã đăng nhập.
- [ ] Test permitAll với cả anonymous và authenticated user.
- [ ] Test 401 thiếu authentication, 403 thiếu role và 200 khi đủ quyền.
- [ ] Dùng authorization trước business logic và object-level checks khi cần.
- [ ] Không log credentials hoặc dùng username làm khóa tenant toàn cục.
- [ ] Không giữ HttpServletRequest sau vòng đời request hoặc tự động tin dữ liệu pre-auth từ header.

**Kết luận:** Khi Spring Security Servlet integration được bật, HttpServletRequest.getUserPrincipal() thường trả Authentication, getRemoteUser() thường trả Authentication.getName(), và isUserInRole("ADMIN") kiểm tra role dựa trên GrantedAuthority theo convention ROLE_. Sự khác biệt giữa request anonymous và authenticated, giữa principal bên ngoài và principal bên trong Authentication, cùng việc đặt authorization policy đúng nơi là ba kiến thức cốt lõi để tích hợp Spring MVC an toàn.
