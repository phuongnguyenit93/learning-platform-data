# RequestHeaderAuthenticationFilter và chống giả mạo header danh tính trong Spring Security Servlet

## 1. Bối cảnh và mục tiêu

Một hệ thống doanh nghiệp có thể đặt ứng dụng Java phía sau **reverse proxy, API gateway, SSO agent hoặc identity-aware proxy**. Tầng phía trước xác thực người dùng bằng OIDC, SAML, Kerberos, mTLS hay một cơ chế khác, rồi chuyển cho ứng dụng backend thông tin danh tính đã xác minh. Spring Security Servlet hỗ trợ mô hình này dưới tên **pre-authentication** (xác thực đã diễn ra trước khi request vào ứng dụng).

**RequestHeaderAuthenticationFilter** là filter để lấy danh tính từ một HTTP request header, sau đó đưa danh tính ấy vào quy trình **AuthenticationManager** của Spring Security. Nó có ích khi **một thành phần đáng tin cậy đã thực sự xác thực người dùng** và chỉ chuyển một danh tính được chứng thực đến backend.

Nhưng HTTP header thông thường **có thể do bất kỳ HTTP client nào tự đặt**. Nếu ứng dụng coi **X-Verified-User: alice** là chứng cứ đăng nhập, trong khi kẻ tấn công có thể gửi trực tiếp header này, kẻ tấn công có thể **mạo danh alice**. Đây là vấn đề trung tâm của bài: phải thiết kế **ranh giới tin cậy (trust boundary)** trước khi dùng RequestHeaderAuthenticationFilter.

Sau bài này, người học cần phân biệt được:

1. Filter **đọc header**, chứ không tự kiểm tra mật khẩu, chữ ký OIDC/JWT hay mTLS của người dùng.
2. Gateway **xác thực và tạo assertion danh tính**; backend chỉ tin assertion từ đường truyền, thành phần và cấu hình được bảo vệ.
3. **Authentication** (alice là ai?) khác **authorization** (alice có quyền đọc dữ liệu này không?).
4. Khi nào cần dùng pre-authentication, khi nào nên để Resource Server xác minh Bearer token trực tiếp.
5. Cách cấu hình Spring Security Servlet, kiểm thử backend và đặc biệt kiểm thử **đường đi qua proxy thật** để ngăn header spoofing.

## 2. RequestHeaderAuthenticationFilter là gì?

Class **org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter** thuộc nhóm xử lý **pre-authenticated requests**. Nó kế thừa hành vi từ **AbstractPreAuthenticatedProcessingFilter**, đọc principal từ request và yêu cầu **AuthenticationManager** xử lý danh tính đó.

Luồng khái quát:

~~~text
Client / Browser
    |
    | Cookie SSO hoặc token, tùy kiến trúc
    v
[Trusted Gateway / SSO Proxy]
    | 1. Xác thực request
    | 2. Xóa mọi header danh tính do client tự gửi
    | 3. Gắn header danh tính đã xác minh
    v
[Backend Spring Security Servlet]
    | RequestHeaderAuthenticationFilter đọc X-Verified-User
    v
AuthenticationManager
    |
    +-- PreAuthenticatedAuthenticationProvider
          |
          +-- Nạp UserDetails / authorities từ nguồn đáng tin
    |
    v
SecurityContext: Authentication đã xác thực
    |
    v
AuthorizationFilter kiểm tra quyền endpoint
    |
    v
Controller -> Service -> dữ liệu
~~~

**Pre-authentication không có nghĩa “bỏ xác thực”.** Nó có nghĩa phần **chứng minh danh tính** đã được thực hiện ở một ranh giới đáng tin bên ngoài Spring Security. Spring Security phía backend vẫn chịu trách nhiệm thiết lập Authentication, ánh xạ quyền và kiểm soát truy cập.

Các thành phần thường gặp:

| Thành phần | Nhiệm vụ |
| --- | --- |
| **RequestHeaderAuthenticationFilter** | Đọc giá trị header chứa danh tính từ HttpServletRequest |
| **PreAuthenticatedAuthenticationToken** | Biểu diễn principal/credentials trước và sau khi AuthenticationManager xử lý |
| **PreAuthenticatedAuthenticationProvider** | Dùng dịch vụ user details của backend để xây dựng Authentication đã xác thực |
| **UserDetailsByNameServiceWrapper** | Ánh xạ principal đã được xác thực từ trước thành UserDetails theo username |
| **UserDetailsService** | Nạp user và authorities từ nguồn mà backend quản lý |
| **SecurityContextHolder** | Cung cấp Authentication hiện hành cho security filters và controller |
| **AuthorizationFilter** | Kiểm tra authority/role/policy trước khi cho phép xử lý endpoint |

Lưu ý: việc nạp UserDetails **không chứng minh header là thật**. Nếu nguồn header đã bị mạo danh, tìm thấy username hợp lệ trong cơ sở dữ liệu chỉ giúp kẻ tấn công nhận được authorities của tài khoản bị mạo danh.

## 3. Threat model: một header được nhận từ đâu?

### 3.1. Ví dụ lỗ hổng

Giả sử backend có endpoint bảo vệ **GET /api/documents**, và filter tin header **X-Verified-User**. Client có thể tự tạo request:

~~~http
GET /api/documents HTTP/1.1
Host: backend.example.internal
X-Verified-User: alice
~~~

Nếu backend chấp nhận trực tiếp request này mà **không có một lớp xác thực đáng tin đảm bảo header được tạo bởi gateway**, header chỉ là dữ liệu **do caller khai báo**, không phải bằng chứng caller là alice.

Nguy cơ thường xuất hiện khi:

- Backend bất ngờ có cổng public hoặc ingress thứ hai bỏ qua SSO proxy.
- Gateway không **xóa header cùng tên** từ request do client cung cấp mà chỉ forward nguyên bản.
- Có nhiều proxy liên tiếp, một proxy làm sạch nhưng proxy khác thêm/ghi đè không nhất quán.
- Một số biến thể tên header, dấu gạch dưới/gạch ngang, chữ hoa/thường hoặc **duplicate headers** được proxy và Servlet container hiểu khác nhau.
- Endpoint admin hoặc route nội bộ dùng chung ingress mà chưa được bảo vệ tương đương.
- Web app tin một giá trị **X-Forwarded-User** hay **X-Auth-User** do client gửi, chỉ vì tên có vẻ “đến từ proxy”.

**Dấu hiệu nguy hiểm:** mở DevTools, curl hoặc Postman rồi tự thêm header có tên đang dùng cho danh tính; nếu có thể gọi trực tiếp backend và nhận quyền của người khác, thiết kế đã mất ranh giới tin cậy. Đây không phải “vấn đề tên header khó đoán”: header name không phải secret và không thay thế xác thực.

### 3.2. Kiến trúc an toàn hơn

~~~text
INTERNET / UNTRUSTED NETWORK
             |
             v
 [Public Gateway / SSO Proxy]
    - Xác thực người dùng / service
    - Từ chối request không xác thực
    - Loại bỏ header danh tính client tự nhập
    - Thiết lập một danh tính canonical duy nhất
             |
             | Chỉ một tuyến mạng nội bộ được cho phép
             | TLS/mTLS hoặc biện pháp bảo vệ hop phù hợp
             v
       [Java Backend]
    - Không truy cập trực tiếp được từ bên ngoài
    - Chỉ nhận identity assertion từ gateway được tin
    - Nạp authorities từ nguồn tin cậy
    - Kiểm tra quyền tới từng endpoint/tài nguyên
~~~

**Yêu cầu bất biến:** mọi request có thể đến được filter phải đi qua cùng chính sách xác thực và sanitization đáng tin cậy. Chỉ cần một đường vòng đến backend để bỏ qua gateway, mọi thứ dựa vào identity header có thể mất ý nghĩa.

Để đạt điều đó, áp dụng nhiều lớp kiểm soát:

1. **Network boundary:** backend chỉ nghe mạng private hoặc được firewall/security group/network policy cho phép truy cập từ gateway; chặn direct public exposure, cổng debug, health/admin port không chủ ý.
2. **Authenticated transport:** bảo vệ hop gateway → backend bằng TLS, ưu tiên mTLS hoặc service identity ở hạ tầng phù hợp; không suy luận rằng chỉ có private IP là đủ.
3. **Header sanitization:** gateway phải loại bỏ tất cả header/biến thể danh tính từ request client rồi **tự gắn lại** header canonical sau khi xác thực.
4. **Fail closed:** thiếu, thất bại hoặc không rõ trạng thái xác thực thì gateway không được chuyển một principal đáng tin về backend. Backend cũng phải từ chối endpoint bảo vệ nếu thiếu Authentication.
5. **Authorization độc lập:** backend chỉ dùng principal đã xác thực làm đầu vào, vẫn kiểm tra roles/scopes và quyền tới đối tượng cụ thể.
6. **Quan sát an toàn:** log request ID, nguồn gateway tin cậy và quyết định security, không log token/cookie/secret hay dữ liệu cá nhân dư thừa.

## 4. Tên header, giá trị principal và hành vi mặc định

**RequestHeaderAuthenticationFilter** có cấu hình chính:

~~~java
RequestHeaderAuthenticationFilter filter =
        new RequestHeaderAuthenticationFilter();

filter.setPrincipalRequestHeader("X-Verified-User");
filter.setExceptionIfHeaderMissing(false);
filter.setAuthenticationManager(authenticationManager);
~~~

Giải thích:

- **setPrincipalRequestHeader(...)** chọn chính xác header chứa danh tính mà filter đọc. Nếu không cấu hình, triển khai này thường dùng tên mặc định **SM_USER**, xuất phát từ một số hệ thống pre-authentication truyền thống.
- **setExceptionIfHeaderMissing(false)** cho phép request thiếu header tiếp tục qua filter mà không ném exception do riêng việc thiếu header. **Không đồng nghĩa cho phép truy cập:** endpoint vẫn phải yêu cầu authenticated/authority và nhận 401/403 phù hợp.
- **setAuthenticationManager(...)** liên kết filter với AuthenticationManager có provider xử lý **PreAuthenticatedAuthenticationToken**.
- Filter có thể đọc một credentials header tùy cấu hình, nhưng **không nên truyền mật khẩu thực của người dùng trong một HTTP header để “làm pre-auth”**. Mục tiêu là tiêu thụ danh tính đã xác minh từ trusted boundary, không chuyển trách nhiệm kiểm tra mật khẩu sang backend bằng cách nhét credentials vào header.
- Header name tùy chọn không phải khóa bí mật. Đổi từ X-Verified-User sang một tên dài/ngẫu nhiên **không ngăn spoofing** nếu attacker còn có thể gửi request đến backend hoặc khiến gateway forward header.

**Phân biệt username và quyền:** header **X-Verified-User: alice** không có nghĩa alice có role ADMIN. Khi thiết kế có nguồn dữ liệu user nội bộ, backend nên nạp authorities từ nguồn được tin và kiểm tra chính sách nhất quán. Nếu gateway cũng gửi roles/groups, phải có contract ràng buộc nguồn và tính toàn vẹn rõ ràng; tuyệt đối không tin **X-Verified-Roles** của request bên ngoài.

**Ký tự và chuẩn hóa:** gateway phải quy định một representation ổn định cho principal (ví dụ subject ID bền vững), tránh nhầm username có thể đổi hoặc trùng giữa tenants. Phải định nghĩa cách xử lý giá trị trống, trùng lặp, không hợp lệ và ánh xạ tenant; không chỉ dùng **getHeader(...)** rồi mặc nhiên tin đó là một user duy nhất.

## 5. Spring Security xử lý pre-authentication như thế nào?

Ở backend, filter thu thập principal từ request. Từ đó một provider phù hợp có thể xác minh **tính hợp lệ theo chính sách backend** của principal, ví dụ tìm một UserDetails đã đăng ký, đang enabled, và nạp các authorities tương ứng.

Điều này **khác** password authentication:

| Khía cạnh | Username/password tại backend | Pre-authentication bằng header |
| --- | --- | --- |
| Bằng chứng ban đầu | Username + secret được kiểm tra bởi authentication flow | Assertion do trusted gateway tạo |
| Thành phần kiểm tra secret/SSO | Backend hoặc IdP trong flow được tích hợp | Gateway/SSO proxy bên ngoài backend |
| Giá trị backend thấy | Username/password hoặc token do backend trực tiếp xác minh | Principal header không tự có chữ ký |
| Provider điển hình | DaoAuthenticationProvider hoặc cơ chế phù hợp | PreAuthenticatedAuthenticationProvider |
| Rủi ro đặc thù | Brute force, secret handling, credential stuffing | **Header spoofing**, direct backend bypass, stale principal |
| Phân quyền | Vẫn cần | **Vẫn cần** |

Trong mô hình pre-authentication, AuthenticationManager không nên chấp nhận “bất kỳ tên nào” rồi cấp role cao. Một provider có **UserDetailsService** chỉ nên cấp quyền dựa trên dữ liệu mà backend tin. Trường hợp ứng dụng hỗ trợ nhiều tổ chức/tenant, principal được gateway tạo nên là định danh đủ mạnh để tránh va chạm giữa hai tổ chức.

### 5.1. Nếu thiếu header?

Với **exceptionIfHeaderMissing(false)**, filter có thể không tạo Authentication mới; endpoint đòi xác thực phải từ chối theo rule. Với **exceptionIfHeaderMissing(true)**, filter có thể ném exception do header thiếu. Hai chế độ khác nhau về **cách báo lỗi**, không phải về nghĩa vụ xác thực. Mục tiêu production là response rõ ràng, fail closed và không làm lộ thông tin hệ thống.

### 5.2. Nếu session và header thay đổi?

Một ứng dụng có thể sử dụng session/SecurityContext giữa các request. Khi đó phải phân tích nguy cơ **identity A ở session nhưng header của request hiện tại là identity B**. AbstractPreAuthenticatedProcessingFilter có khả năng kiểm tra thay đổi principal theo cấu hình, nhưng chính sách re-authentication/invalidation cần được thiết kế và kiểm thử; đừng coi mỗi header mới tự động thay thế Authentication cũ trong mọi trường hợp.

Đối với API pre-auth phía sau gateway, nếu backend không cần HttpSession, mô hình **stateless** có thể giảm rủi ro tái dùng SecurityContext cũ. Dù vậy cần nhớ: nếu **gateway xác thực browser bằng cookie** thì hệ thống ở ranh giới ngoài vẫn có thể chịu rủi ro **CSRF**, kể cả khi backend không lưu session. Stateless của backend **không tự biến mọi request browser thành an toàn với CSRF**.

## 6. Ví dụ Java 17: RequestHeaderAuthenticationFilter trong Spring Security Servlet

Ví dụ sử dụng **Spring Boot 3.4.5, Spring Security 6, Java 17, Spring MVC**. Endpoint **GET /api/documents** yêu cầu role READER. Filter chỉ đọc **X-Verified-User**, nạp authorities cho hai user **alice** (READER) và **bob** (VIEWER).

**Giới hạn an toàn của demo:** mã Java sau **giả định** đã có một gateway đáng tin xác thực user, xóa header giả mạo và là tuyến truy cập duy nhất đến backend. Chạy độc lập trên localhost **không chứng minh gateway tồn tại**; nếu cổng backend được phơi ra Internet, người ngoài có thể tự đặt X-Verified-User. Ví dụ này nhằm minh họa Spring Security filter/provider, **không được sao chép nguyên trạng để mở public API**.

Cấu trúc dự án:

~~~text
header-preauth-demo/
├── pom.xml
└── src/
    ├── main/java/demo/preauth/HeaderPreauthApplication.java
    └── test/java/demo/preauth/HeaderPreauthApplicationTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>header-preauth-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/preauth/HeaderPreauthApplication.java**:

~~~java
package demo.preauth;

import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HeaderPreauthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeaderPreauthApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    UserDetailsService userDetailsService() {
        // Mô phỏng directory nội bộ. Password không được dùng
        // để xác minh pre-authentication bằng trusted gateway.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}unused")
                    .roles("READER").build(),
                User.withUsername("bob")
                    .password("{noop}unused")
                    .roles("VIEWER").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                           UserDetailsService users)
            throws Exception {
        // Chỉ backend tin gateway đã xác minh identity mới
        // được phép dùng mô hình này ở production.
        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
                lookup = new UserDetailsByNameServiceWrapper<>();
        lookup.setUserDetailsService(users);

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(lookup);
        AuthenticationManager manager = new ProviderManager(provider);

        RequestHeaderAuthenticationFilter preAuth =
                new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(manager);

        // Khởi tạo filter trực tiếp trong chain, KHÔNG khai báo
        // riêng @Bean RequestHeaderAuthenticationFilter:
        // tránh Spring Boot tự đăng ký nó như Servlet Filter
        // chạy lần thứ hai ngoài SecurityFilterChain.
        return http
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/documents")
                            .hasRole("READER")
                        .anyRequest().denyAll())
                .exceptionHandling(ex -> ex.authenticationEntryPoint(
                        (request, response, exception) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .addFilterBefore(preAuth,
                        UsernamePasswordAuthenticationFilter.class)
                // CSRF giữ nguyên mặc định. Demo chỉ có GET.
                .build();
    }
}

@RestController
class DocumentController {
    @GetMapping("/api/documents")
    ResponseEntity<Map<String, Object>> list(Authentication authentication) {
        return ResponseEntity.ok(Map.of(
                "user", authentication.getName(),
                "documents", List.of("DOC-001")));
    }
}
~~~

**Đọc code theo trình tự:**

1. **UserDetailsService** nạp user và role; đây là nguồn authorities backend tự quản lý.
2. **UserDetailsByNameServiceWrapper** giúp provider tìm UserDetails bằng principal mà pre-auth filter cung cấp.
3. **PreAuthenticatedAuthenticationProvider** xử lý PreAuthenticatedAuthenticationToken được filter tạo; nó không tự kiểm tra SSO cookie hay mật khẩu của client.
4. **RequestHeaderAuthenticationFilter** lấy **X-Verified-User**, giao cho AuthenticationManager, và đặt Authentication vào SecurityContext theo hành vi filter.
5. **addFilterBefore(...)** đưa filter vào Spring Security chain trước UsernamePasswordAuthenticationFilter. Điều này **không khiến header trở nên đáng tin**: chỉ gateway/network controls làm được việc đó.
6. **hasRole("READER")** yêu cầu authority **ROLE_READER**. alice có ROLE_READER nên qua; bob chỉ có ROLE_VIEWER nên bị từ chối.
7. **anyRequest().denyAll()** là fallback an toàn cho các route khác. **SessionCreationPolicy.STATELESS** ngăn thiết kế lưu Authentication trong HttpSession của backend.
8. Chúng ta **không tắt CSRF bằng một cấu hình máy móc**. Vì bài demo chỉ có GET, CSRF không cản trở request. Nếu về sau gateway dùng cookie để xác thực browser và API có POST/PUT/DELETE, phải đánh giá và duy trì CSRF protection thích hợp ngay cả khi backend stateless.

**Tại sao ví dụ không dùng filter @Bean?** Với Spring Boot, một bean kiểu Servlet Filter có thể được tự động đăng ký vào Servlet container; nếu đồng thời thêm nó bằng **http.addFilterBefore(...)**, filter có nguy cơ chạy hai lần ở hai tầng. Khởi tạo filter bên trong cấu hình SecurityFilterChain như ví dụ giúp minh bạch phạm vi xử lý. Nếu hệ thống phải khai báo filter bean riêng, cần chủ động kiểm soát Servlet registration thay vì bỏ qua nguy cơ này.

### 6.1. Chạy demo

Từ thư mục dự án:

~~~bash
mvn test
mvn spring-boot:run
~~~

Các lệnh sau **chỉ minh họa cách backend xử lý header**, không xác nhận có gateway đáng tin:

~~~bash
# Không có danh tính -> bị chặn.
curl -i http://localhost:8080/api/documents

# Header khớp alice, user nội bộ có ROLE_READER -> 200.
curl -i http://localhost:8080/api/documents \
  -H "X-Verified-User: alice"

# Header khớp bob nhưng không có ROLE_READER -> 403.
curl -i http://localhost:8080/api/documents \
  -H "X-Verified-User: bob"
~~~

Với response hợp lệ, body từ controller có dạng:

~~~json
{"documents":["DOC-001"],"user":"alice"}
~~~

Thứ tự thuộc tính trong JSON không phải giao kèo cố định. Trong ví dụ đã chủ đích cấu hình AuthenticationEntryPoint trả **401** khi request chưa xác thực. **Cực kỳ quan trọng:** nếu direct curl gắn header alice và nhận **200**, kết quả này chứng minh bộ lọc tin giá trị header; nó **không chứng minh client đã được SSO xác thực**. Khi triển khai production, direct request đến backend phải **bị chặn ngay ở hạ tầng**, và request qua gateway phải được xác thực, làm sạch header rồi mới chuyển tiếp.

## 7. Unit/integration test trong Spring Security

Tạo **src/test/java/demo/preauth/HeaderPreauthApplicationTests.java**:

~~~java
package demo.preauth;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HeaderPreauthApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void missingHeaderDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/api/documents"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void trustedHeaderForReaderPassesApplicationRule()
            throws Exception {
        mvc.perform(get("/api/documents")
                        .header("X-Verified-User", "alice"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"))
                .andExpect(jsonPath("$.documents[0]").value("DOC-001"));
    }

    @Test
    void userWithoutRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/documents")
                        .header("X-Verified-User", "bob"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unrelatedHeaderIsNotAcceptedAsPrincipal()
            throws Exception {
        mvc.perform(get("/api/documents")
                        .header("X-Forwarded-User", "alice"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unrelatedRouteIsDeniedEvenWithValidPrincipal()
            throws Exception {
        mvc.perform(get("/api/other")
                        .header("X-Verified-User", "alice"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Những test này giúp xác nhận **mapping từ header sang Authentication**, các rule 401/403/200 và **deny-all fallback**. Chúng **chưa phải bằng chứng chống spoofing đầu cuối**: MockMvc gọi trực tiếp Spring application, không có gateway thực để làm sạch header. Test “trustedHeaderForReaderPassesApplicationRule” cố ý minh họa rằng khi một request mang header alice **đã tới được Servlet filter**, backend có thể chấp nhận nó như pre-authentication.

**Nếu chỉ chạy những unit tests trên rồi tuyên bố hệ thống đã ngăn header giả mạo, kết luận đó là sai.** Phần kiểm thử quan trọng nhất nằm ở mục kế tiếp.

## 8. Kiểm thử ngăn header spoofing ở đúng ranh giới

Kế hoạch kiểm thử bắt buộc ở staging có kiến trúc sát production:

~~~text
External client -> Public Gateway -> Internal Backend
                                    (no direct public route)
~~~

| Ca kiểm thử | Hành vi kỳ vọng |
| --- | --- |
| Client **không đăng nhập** gửi request không có header | Gateway từ chối/redirect theo contract; không tạo user đã xác thực |
| Client không đăng nhập **tự gắn X-Verified-User: alice** | Gateway từ chối request hoặc xóa header; backend không bao giờ coi request là alice |
| Client đăng nhập thật là **bob**, nhưng gửi thêm header **X-Verified-User: alice** | Gateway xóa header tự khai báo và gắn identity thật là bob; endpoint đòi READER vẫn 403 |
| Client đăng nhập thật là **alice**, gửi header giả khác | Gateway chuẩn hóa danh tính về alice; ứng dụng áp dụng quyền thực của alice |
| Client thử truy cập **IP/cổng backend trực tiếp** | Bị chặn bằng network/firewall/TLS trước khi đến RequestHeaderAuthenticationFilter |
| Client gửi **nhiều header cùng tên** hoặc biến thể chữ hoa/thường | Gateway và backend xử lý nhất quán; không thể chọn identity do client kiểm soát |
| Header có giá trị rỗng, quá dài, ký tự bất thường | Bị reject hoặc fail closed theo contract, không nhận một user mặc định có quyền |
| Gateway mất kết nối IdP hoặc kiểm tra token thất bại | Request không được gắn identity tin cậy; dịch vụ không tự chọn anonymous thành account hợp lệ |
| User bị khóa/thu hồi quyền giữa các request | Backend/IdP cập nhật quyền theo yêu cầu nghiệp vụ, không tiếp tục cấp đặc quyền cũ vô thời hạn |
| Một request thay đổi trạng thái qua browser đã có cookie SSO | Chính sách CSRF được áp dụng đúng tại gateway/backend, không suy luận an toàn từ session stateless của backend |

**Nguyên tắc kiểm thử:** xác nhận **identity thực được backend nhận**, authorities và dữ liệu trả về; không chỉ nhìn status. Với user bob giả mạo alice, test cần chứng minh **bob không nhận dữ liệu của alice**.

### 8.1. Ví dụ thao tác kiểm thử tại gateway

Gọi **địa chỉ gateway public** (không gọi trực tiếp backend) khi client chưa xác thực:

~~~bash
curl -i https://gateway.example.test/api/documents \
  -H "X-Verified-User: alice"
~~~

**Kỳ vọng:** gateway từ chối/đưa vào đúng flow authentication, không cấp quyền của alice. Với thử nghiệm user bob đã đăng nhập qua gateway, gửi thêm header alice và xác nhận backend vẫn xử lý **bob** hoặc từ chối theo policy; không được biến thành alice.

Đây là **mẫu kiểm thử kiến trúc**, không có một kết quả HTTP chung cho mọi gateway (401, 302 hay 403 tùy hợp đồng). **example.test** là domain minh họa, không phải endpoint sẵn có. Hãy thử qua hạ tầng staging do tổ chức sở hữu; không kiểm tra hệ thống bên thứ ba nếu không được phép.

### 8.2. Những tình huống header normalization cần xem xét

HTTP header name về nguyên tắc không phân biệt hoa/thường, trong khi proxy/CGI-style middleware có thể chuyển tên header thành biến môi trường hoặc dạng internal khác. Vì vậy cần kiểm tra cả:

- Header name trùng nghĩa nhưng khác chữ hoa/thường.
- Dấu **-** và **_** trong các tên có khả năng bị middleware chuẩn hóa khác nhau.
- Nhiều occurrence của cùng header, header có danh sách giá trị và giới hạn chiều dài.
- Các lớp CDN, WAF, Ingress Controller, mesh/sidecar và backend có cùng chính sách xóa/gắn identity headers hay không.
- Hop-by-hop headers, request smuggling và biến đổi đường dẫn liên quan nếu hạ tầng có nhiều bộ parser khác nhau.

Chỉ **xóa một tên header trong code Java** sau khi RequestHeaderAuthenticationFilter đã đọc nó là **quá muộn**. Sanitization phải diễn ra **trước** khi xác thực backend dựa trên header, tốt nhất tại gateway được tin và với access control mạng bảo đảm client không đi vòng.

## 9. Vai trò gateway: hợp đồng tin cậy cần ghi rõ

Một kiến trúc pre-authentication cần document tối thiểu:

**Đầu vào:** gateway nhận cookie phiên đăng nhập, OIDC access token, client certificate hoặc phương thức xác thực đã chọn. Phải xác minh issuer/audience/signature/expiry và policy cần thiết nếu đó là JWT; xác minh handshake, chứng chỉ và mapping identity nếu dùng mTLS; không tin một X-User do caller tạo.

**Đầu ra:** một header danh tính canonical, ví dụ **X-Verified-User**, chứa subject ID đã xác minh. Chỉ gateway được phép tạo nó. Backend không nên tự suy roles từ display name hoặc email do caller cung cấp.

**Truyền tải:** TLS/mTLS hay private network policy thích hợp, identity của gateway, cấu hình allowlist nguồn thật sự đáng tin. Không coi **X-Forwarded-For**, **X-Real-IP** hoặc Forwarded header tự gửi là chứng minh request đến từ gateway; các header này cũng cần xác thực/sanitization ở trust boundary.

**Xử lý lỗi:** khi IdP timeout, xác minh thất bại, user bị khóa, header không hợp lệ hoặc thiếu session, **fail closed**; không fallback thành user quyền cao, không bỏ qua auth chỉ để tăng availability.

**Phân quyền:** backend kiểm tra roles/permissions và quyền theo tài nguyên. Nếu một hệ thống nhiều tenants, identity nên gắn tenant/issuer theo contract bảo mật chặt chẽ; tránh hai tenant có cùng username nhưng bị nhập làm một.

**Quản lý vòng đời:** TTL của phiên gateway, refresh/revocation, thay đổi quyền, logout, time skew, quản lý key/certificate và audit. Nếu backend cache UserDetails, cần quy định thời gian phản ánh việc thu hồi quyền.

**Vận hành:** metric số request không có header canonical sau gateway, phân bố authorization denied, số trường hợp duplicate header, số request tới backend sai tuyến; alert cho bất thường. Log chỉ dữ liệu cần thiết với access control.

## 10. CSRF, session, CORS và các ranh giới khác

### 10.1. CSRF không biến mất chỉ vì backend tin header

Một lỗi lập luận phổ biến:

> Backend stateless, không dùng session cookie ở Java, nên cứ tắt CSRF là an toàn.

Điều này chỉ đúng khi đã kiểm chứng **toàn bộ phương thức xác thực** và cách browser tự gửi credentials. Nếu **gateway** dùng session cookie SSO, trình duyệt có thể tự đính cookie vào request qua gateway. Gateway xác thực cookie và gắn X-Verified-User, khiến backend nhìn thấy request đã xác thực dù người dùng không chủ động đồng ý thao tác. Vì vậy với các thao tác thay đổi trạng thái như POST/PUT/DELETE, cần cơ chế chống CSRF hoặc thiết kế xác thực không thể bị trình duyệt tự gửi trong bối cảnh tấn công.

Bài mẫu chỉ có GET để cô lập cơ chế pre-auth; giữ CSRF mặc định. Không áp dụng **csrf.disable()** toàn cục chỉ vì có RequestHeaderAuthenticationFilter.

### 10.2. CORS không phải cách ngăn spoofing

CORS quyết định JavaScript từ origin khác có thể đọc response và gửi các request cần preflight hay không. Nó **không chặn curl/Postman/backend client tự đặt header**. Một backend được phơi trực tiếp lên Internet vẫn có thể bị mạo danh bằng X-Verified-User ngay cả khi CORS chỉ cho phép một origin đáng tin.

### 10.3. Session và identity switching

Khi backend vừa dùng session vừa đọc identity header, phải thiết kế rõ request nào là nguồn danh tính chính. Nếu cùng HttpSession được tái sử dụng cho request của identity khác, nguy cơ session/context cũ có thể khiến request được cấp quyền sai. Có thể sử dụng cơ chế kiểm tra principal change của pre-auth filter và invalidation thích hợp, nhưng **không được coi đó là thay thế cho gateway sanitization**. Mô hình stateless cho API có thể dễ lý giải hơn nếu toàn bộ danh tính mỗi request đều do gateway cung cấp và hạ tầng bảo đảm tính xác thực của assertion.

### 10.4. Liên hệ với OAuth2 Resource Server

**Resource Server JWT** thường đọc **Authorization: Bearer ...**, tự xác minh chữ ký, issuer, thời hạn/audience và ánh xạ scopes/authorities. Đây là cách phù hợp khi API cần tự kiểm tra token do client trình ra.

**RequestHeaderAuthenticationFilter** đọc một header chứa tên user **không có chữ ký**, và **tin vào gateway bên ngoài** đã xác thực. Hai mô hình có thể đều an toàn khi được triển khai đúng trust boundary, nhưng không tương đương: Resource Server xác minh token tại API, còn header pre-auth phụ thuộc vào sự bảo đảm của gateway + tuyến mạng.

| Tình huống | Lựa chọn nên đánh giá |
| --- | --- |
| API public nhận OAuth2 Bearer token từ nhiều clients | Resource Server với JWT/opaque validation |
| Backend legacy chỉ có thể chạy sau SSO gateway được quản lý chặt | Pre-auth qua RequestHeaderAuthenticationFilter, với trust boundary hoàn chỉnh |
| Browser web app đăng nhập trực tiếp qua OIDC và giữ session | oauth2Login() / OAuth2 Client, không mặc định cần identity header |
| Gateway xác minh JWT, backend vẫn muốn tự kiểm chứng token | Token relay tới Resource Server hoặc giải pháp zero-trust phù hợp |
| Có nhiều đường truy cập backend không bảo đảm cùng policy | **Không dùng header pre-auth thuần** như bằng chứng đăng nhập |

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra/sửa |
| --- | --- | --- |
| Thêm X-Verified-User thủ công là vào được hệ thống | Backend bị gọi trực tiếp hoặc gateway forward header client | Đóng direct path; gateway xóa và tái tạo header sau auth |
| Request thiếu header nhưng không lỗi ngay ở filter | Đã setExceptionIfHeaderMissing(false) | Xác minh endpoint yêu cầu authenticated/role; phải fail closed |
| User hợp lệ vẫn 401 | Gateway không chuyển header, sai tên header, user không tồn tại ở UserDetailsService | Trace ở gateway/app bằng request ID, kiểm tra contract |
| User có principal nhưng 403 | Thiếu authority hoặc không đủ quyền tài nguyên | Kiểm tra ROLE_/SCOPE_ và permission service-layer |
| Test MockMvc pass nhưng production có thể spoof | MockMvc bypass gateway/network boundary | Viết black-box integration test đi qua gateway, thử direct backend từ ngoài |
| X-Forwarded-User bất ngờ được chấp nhận | Proxy/filter khác ánh xạ header sang principal | Kiểm tra tất cả lớp proxy/filter và contract chính tắc |
| Header trùng cho ra user khác mong đợi | Duplicate/normalization xử lý khác nhau giữa hop | Reject/normalize ở gateway trước khi tạo assertion |
| Request của user B dùng quyền A | Session/context cũ, stale principal hoặc identity switching | Xem stateful context, principal-change policy và kiểm thử nhiều request |
| Có header role ADMIN do client gửi | Ứng dụng tin quyền do client khai báo | Bỏ nguồn quyền không tin, nạp quyền từ nguồn đáng tin |
| Bị CSRF dù backend stateless | Gateway dùng browser cookie tự gửi | Giữ cơ chế CSRF phù hợp ở boundary có cookie |
| Client không login vẫn gọi API được trong mạng nội bộ | Network trusted quá rộng hoặc bỏ qua gateway | Giới hạn ingress, mTLS/service identity và audit |
| Lỗi đăng nhập sau timeout IdP | Gateway fail open hoặc giữ assertion stale | Fail closed, kiểm tra TTL, session revocation và outage handling |

**Quy trình debug ngắn:** xác định request đi qua **đúng gateway chưa** → tại gateway có xác thực thành công chưa → header do gateway tạo sau sanitization hay do client gửi → backend filter đọc principal nào → provider tải UserDetails/authorities nào → authorization rule nào quyết định 401/403 → quyền đối tượng và CSRF có được kiểm tra không. Đừng điều chỉnh thêm quyền hoặc đặt **permitAll()** chỉ để ẩn triệu chứng.

## 12. Checklist review trước production

- [ ] Mô hình pre-auth được chọn có lý do thay vì Resource Server/JWT validation trực tiếp.
- [ ] Backend không thể bị truy cập trực tiếp từ mạng không tin cậy, kể cả đường ingress phụ.
- [ ] Gateway thực hiện xác thực thật và **xóa mọi identity header do client tự cung cấp** trước khi tạo assertion mới.
- [ ] Hop gateway → backend có cơ chế bảo vệ transport và nhận diện gateway phù hợp.
- [ ] Tên header canonical, quy tắc duplicate/blank/encoding/normalization được xác định.
- [ ] Không dùng forwarded address header hoặc tên header “bí mật” làm bằng chứng xác thực.
- [ ] UserDetails/authorities nạp từ nguồn đáng tin, áp dụng quy tắc least privilege.
- [ ] Có kiểm thử gateway black-box cho spoofing, bypass, user-switching và revoke quyền.
- [ ] Các route quan trọng có authorization theo vai trò **và** theo tài nguyên thực tế.
- [ ] Cơ chế CSRF được đánh giá cả với cookie/session tại gateway; không tắt máy móc.
- [ ] Logging, tracing, alerting không làm lộ token/cookie hoặc thông tin cá nhân không cần thiết.
- [ ] Có owner, threat model, kế hoạch rollback và theo dõi sau rollout.

## 13. Câu hỏi tự kiểm tra

1. **RequestHeaderAuthenticationFilter** có tự xác minh JWT chữ ký hoặc SSO session của người dùng không? **Không.** Nó tiêu thụ một identity header đã được một thành phần đáng tin cậy xác thực trước.
2. Nếu caller được phép gọi trực tiếp backend và gửi **X-Verified-User: alice**, UserDetailsService có thể ngăn impersonation chỉ vì alice tồn tại không? **Không.** Vấn đề nằm ở nguồn header không đáng tin.
3. Điều gì phải xảy ra tại gateway trước khi gắn header identity? **Xác thực caller, xóa toàn bộ identity header đầu vào không tin cậy và tạo assertion canonical.**
4. Vì sao **hasRole("READER")** vẫn quan trọng? Vì xác thực danh tính không đồng nghĩa có quyền xem mọi endpoint hoặc dữ liệu.
5. Có phải chỉ cần CORS chặt là ngăn curl gửi identity header không? **Không.** CORS chủ yếu là cơ chế browser.
6. Backend stateless phía sau gateway có cookie SSO thì chắc chắn không cần CSRF? **Không.** Cần phân tích credentials tự gửi qua browser ở gateway và toàn hệ thống.
7. Test MockMvc với header alice trả 200 chứng minh điều gì? **Chứng minh filter/provider/authorization hoạt động trong backend**, không chứng minh gateway đã chống spoofing.
8. API public trực tiếp nhận Bearer token nên cân nhắc cơ chế nào? **OAuth2 Resource Server** tự xác minh token, thay vì tin username header từ client.

**Kết luận:** **RequestHeaderAuthenticationFilter chỉ đáng tin khi header danh tính đến từ một thành phần đã xác thực và một đường truyền được bảo vệ**. Để chống giả mạo, phải đảm bảo gateway xác thực và sanitization header, không có direct backend bypass, backend nạp authorities đáng tin và thực thi authorization/CSRF đúng chỗ. Đổi tên header, bật CORS hoặc chỉ kiểm tra user có tồn tại không **không tạo ra ranh giới tin cậy**.
