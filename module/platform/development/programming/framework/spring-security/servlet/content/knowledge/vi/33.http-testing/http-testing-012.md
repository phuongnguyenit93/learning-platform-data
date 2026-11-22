# Kiểm thử CORS, security headers, firewall và đường dẫn không chuẩn trong Spring Security Servlet

## 1. Mục tiêu và ranh giới bài học

Một API Spring MVC có thể vượt qua toàn bộ các bài test “đăng nhập đúng thì 200, đăng nhập sai thì 401” mà vẫn có lỗi bảo mật ở lớp HTTP:

- Request **CORS preflight** bị AuthenticationFilter chặn vì không có bearer token, làm trình duyệt không gửi được request chính.
- Response cho một origin ngoài danh sách được phép vẫn có **Access-Control-Allow-Origin** không phù hợp.
- Endpoint trả 200 nhưng thiếu **X-Content-Type-Options**, **Content-Security-Policy (CSP)** hoặc **HSTS** ở HTTPS.
- URL chứa **dấu chấm phẩy**, **%2F** (encoded slash), **%5C** (encoded backslash), **..** hoặc path không chuẩn được các tầng proxy, servlet container, firewall và MVC hiểu theo những cách khác nhau.
- Test bằng **MockMvc** thành công nhưng deployment thật lại chặn ở gateway/Tomcat, hoặc gateway đã chuẩn hóa đường dẫn trước khi Spring Security nhìn thấy.

Bài này hướng dẫn viết bài kiểm thử HTTP theo từng lớp, dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC (Servlet stack)**. Các snippet giả định ứng dụng đang dùng một SecurityFilterChain và cấu hình **StrictHttpFirewall** mặc định.

**Mục tiêu kiểm thử** là biết request nào cần 200, 401, 403 hoặc 400 trong cấu hình mẫu, đồng thời nắm rõ **tầng nào chịu trách nhiệm**. Không dùng một mã HTTP làm bằng chứng duy nhất rằng CORS, phân quyền hay firewall đều hoạt động đúng.

## 2. Bốn lớp xử lý liên quan

~~~text
Trình duyệt
  │
  ├─ Same-Origin Policy và CORS: trình duyệt kiểm tra response
  │
  ▼
Reverse proxy / gateway / WAF
  │  Có thể từ chối hoặc chuẩn hóa URI trước khi forward
  ▼
Servlet container (ví dụ Tomcat)
  │  Parse HTTP request target, mapping, decode/normalize theo cấu hình
  ▼
Spring Security FilterChainProxy
  │
  ├─ HttpFirewall (mặc định StrictHttpFirewall)
  │    ├─ URI không được chấp nhận → RequestRejectedException
  │    └─ URI hợp lệ → chọn security filter chain
  │
  └─ Filter chain
       ├─ CORS filter (khi cors() cấu hình đúng)
       ├─ Authentication + Authorization
       ├─ CSRF (cho các request cần bảo vệ)
       └─ Header writers
            ▼
       DispatcherServlet → Controller / Service
            │
            ▼
       Response và các security headers
~~~

**CORS** là cơ chế trình duyệt quyết định JavaScript từ origin khác có thể đọc response hay không. Nó **không** phải authorization của API: **curl**, server-to-server client và các chương trình không tuân theo browser SOP vẫn có thể gửi request. Cần authentication/authorization độc lập.

**Security headers** là các chỉ dẫn bảo mật cho trình duyệt (ví dụ nosniff, CSP, chống nhúng frame, HSTS). Chúng không thay thế TLS hoặc kiểm tra quyền.

**HttpFirewall** kiểm tra dạng request mà Spring Security nhận được, đặc biệt những dạng URI mơ hồ có thể gây bất đồng giữa security matcher và MVC. Nếu container hoặc proxy từ chối sớm, HttpFirewall chưa từng chạy.

**Đường dẫn không chuẩn** như **/api/docs/a%2Fb**, **/api/docs;role=admin** hay **/api//docs** phải được xem trong cả chuỗi xử lý, không chỉ trong unit test của controller.

### 2.1. Vì sao cần cả MockMvc và HTTP thực?

- **MockMvc** chạy request qua Spring MVC và filter Spring Security được đăng ký trong test; rất phù hợp để kiểm tra cấu hình filter, header, authorization và controller một cách nhanh/chủ động.
- **Unit test trực tiếp StrictHttpFirewall** cho biết firewall implementation chấp nhận/từ chối URI giả lập nào, không phụ thuộc Tomcat parse raw request.
- **HTTP integration test chạy ứng dụng qua server** cho biết container có chấp nhận request thật hay không. Nếu có reverse proxy/WAF, nên có thêm test qua public URL vì tầng ngoài có thể rewrite và cache header.

Một bài test MockMvc khẳng định **400 do firewall mặc định** trong cấu hình demo không có nghĩa mọi reverse proxy phải trả 400 giống hệt: nó có thể trả 404/400 hoặc chuẩn hóa URL trước khi request vào ứng dụng.

## 3. Ma trận kỳ vọng trước khi viết mã

Giả sử frontend được phép ở **https://portal.example.test**, backend có endpoint public **GET /api/public/ping** và endpoint cần đăng nhập **GET /api/private/data**.

| Request | Kiểm tra | Kỳ vọng trong cấu hình mẫu |
| --- | --- | --- |
| OPTIONS /api/private/data, Origin được phép, Access-Control-Request-Method: GET | Preflight không cần Basic credentials | **200**, Access-Control-Allow-Origin khớp origin |
| Preflight với Origin không được phép | Chính sách CORS | **403**, không cấp Access-Control-Allow-Origin |
| Preflight yêu cầu method PUT không được phép | Allowed methods | **403** |
| Preflight yêu cầu header X-Admin-Override không được phép | Allowed headers | **403** |
| GET public, Origin được phép | Actual CORS request | **200**, header ACAO đúng origin |
| GET public, Origin không được phép | Actual CORS request | **403**, không cấp ACAO |
| GET private không có Basic credentials, Origin được phép | CORS **và** authentication | **401**, thường vẫn có ACAO từ CorsFilter |
| GET private với Basic đúng, Origin được phép | CORS **và** authentication | **200**, response có ACAO |
| GET public không có Origin | Không phải cross-origin browser request | **200**, thường không có ACAO |
| GET public qua HTTP không TLS | Security headers | Có nosniff, frame policy, CSP đã cấu hình; **không** mong HSTS |
| GET public qua HTTPS | Security headers | Có các header trên và **Strict-Transport-Security** |
| URI có semicolon, encoded slash/backslash hoặc path bất thường | StrictHttpFirewall | Bị từ chối nếu request tới firewall ở dạng đó |
| GET private không có credentials/không Origin | AuthenticationEntryPoint | **401** trong demo HTTP Basic |

Các mã trên là **contract của cấu hình ví dụ và Spring Security 6.x**, không phải tuyên bố rằng mọi proxy/container/IdP hoặc custom filter sẽ trả giống nhau.

## 4. CORS: preflight, actual request và những hiểu nhầm

### 4.1. Preflight khác request thật

Trước khi JavaScript thực hiện một cross-origin request không “simple” (ví dụ có header Authorization), trình duyệt có thể gửi preflight:

~~~http
OPTIONS /api/private/data HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight **không cần** mang Basic/Bearer credentials của request thật. CORS filter phải có khả năng quyết định policy **trước** khi filter authorization chặn nó. Nếu response preflight hợp lệ, trình duyệt mới cân nhắc gửi request GET thật, khi đó **Authentication** và **Authorization** vẫn hoạt động bình thường.

Một response preflight được phép có thể có:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Methods: GET,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Thứ tự, chữ hoa/thường và cách tách header trong response thực tế có thể khác theo framework và proxy. Test nên kiểm tra **giá trị quan trọng**, không đòi toàn bộ raw response khớp từng ký tự.

**Access-Control-Allow-Credentials: true** chỉ có ý nghĩa theo semantics của CORS; nó không tự chứng minh người dùng đã xác thực. Khi cho phép credentials, dùng origin cụ thể đáng tin cậy, **không** cấu hình Access-Control-Allow-Origin: * cho response credentialed.

### 4.2. Đừng dùng permitAll() để “giải quyết CORS”

Nếu preflight thất bại do CORS filter không được đặt đúng vị trí, thêm **requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()** không sửa việc kiểm tra origin/header/method. Nó có thể khiến OPTIONS đi xa hơn nhưng không tạo ra bộ header CORS đúng, và có thể mở ra cách xử lý method không mong muốn.

Hãy cấu hình **CorsConfigurationSource** đúng path, rồi bật **http.cors(...)** ở security chain áp dụng. Với nhiều SecurityFilterChain, cần kiểm tra request đi vào chain nào và chain đó đã xử lý CORS đúng hay chưa.

### 4.3. Origin không đồng nghĩa Referer, Host hoặc URL của backend

**Origin** gồm scheme, hostname và port theo định nghĩa web origin. Ví dụ:

- **https://portal.example.test** khác **http://portal.example.test**.
- **https://portal.example.test** khác **https://portal.example.test:8443**.
- **https://another.example.test** là một origin khác.
- Header **Referer** không thay thế cho cấu hình CORS.
- Browser không cho JavaScript tùy ý đặt Origin theo ý muốn trong luồng fetch chuẩn; nhưng client HTTP khác có thể giả lập bất kỳ Origin nào. Vì vậy không dùng Origin làm chứng cứ danh tính.

**CORS không phải CSRF protection.** Nếu API dùng cookie/session tự gửi và có POST/PUT/DELETE thay đổi trạng thái, vẫn cần chiến lược CSRF phù hợp. Một response bị browser chặn bởi CORS không bảo đảm request đã không được gửi hoặc side effect chưa xảy ra.

## 5. Security headers nên kiểm tra những gì?

Trong cấu hình Spring Security Servlet thông thường:

| Header | Tác dụng | Mặc định / lưu ý |
| --- | --- | --- |
| **X-Content-Type-Options: nosniff** | Giảm việc trình duyệt tự suy đoán MIME | Thường được Spring Security phát mặc định |
| **X-Frame-Options: DENY** | Hạn chế nhúng response vào frame | Thường mặc định; kiểm tra policy framing thực tế |
| **Cache-Control / Pragma / Expires** | Hạn chế caching response nhạy cảm | Spring Security có cache-control headers mặc định, nhưng có thể bị ghi đè |
| **Strict-Transport-Security (HSTS)** | Yêu cầu browser ưu tiên HTTPS về sau | Thường được ghi cho **secure requests**; không mong xuất hiện chỉ vì HTTP nội bộ |
| **Content-Security-Policy** | Giới hạn nguồn script/resource và framing khi cấu hình phù hợp | **Không** tự xuất hiện chỉ vì đã bật Spring Security; cần khai báo policy |
| **Referrer-Policy** | Hạn chế tiết lộ URL trong Referer | Cần xác định policy/nguồn phát phù hợp, không giả định mặc định |
| **Permissions-Policy** | Hạn chế các tính năng trình duyệt | Có thể cấu hình ở app/proxy; cần test ở nơi thực sự phát header |

Với SPA hoặc trang HTML, **CSP cần được thiết kế theo nguồn script/style/nonce/hash thực tế**. Ví dụ dưới dùng policy gọn để minh họa cách kiểm tra header; nếu ứng dụng phải tải script/style bên ngoài, cần chỉnh CSP có kiểm soát, không chuyển sang **unsafe-inline** chỉ để hết lỗi trình duyệt.

**HSTS** phải được kiểm tra qua kết nối HTTPS thực, đặc biệt khi TLS termination ở reverse proxy: Spring có thể chỉ thấy HTTP nội bộ trừ khi proxy gửi **Forwarded/X-Forwarded-Proto** tin cậy và ứng dụng xử lý. HSTS cũng có thể do ingress phát. Nếu cả app và proxy cùng đặt header, cần kiểm tra final response tại public edge, không chỉ test local MockMvc.

**Cache-Control** của response có dữ liệu nhạy cảm cần được thiết kế theo nội dung cụ thể, kể cả khi có reverse proxy/CDN. Không xem một header do Spring phát là đủ để ngăn mọi tầng cache ngoài ứng dụng.

## 6. HttpFirewall và đường dẫn bất thường

### 6.1. Vì sao URL mơ hồ có thể nguy hiểm?

Một tầng có thể đánh giá quyền trên đường dẫn **/api/items/a%2Fb** trong khi tầng tiếp theo giải mã thành **/api/items/a/b**. Hoặc phần **;v=1** sau dấu chấm phẩy bị loại bỏ khi matcher so khớp nhưng lại được controller/MVC xem là path parameter. Khi nhận dạng resource và kiểm tra quyền dựa trên **hai cách nhìn khác nhau**, route có nguy cơ đi sai chính sách.

**StrictHttpFirewall**, được sử dụng mặc định trong những cấu hình Spring Security Servlet phổ biến, từ chối nhiều dạng đường dẫn nguy hiểm hoặc không chuẩn theo chính sách của implementation. Các ví dụ:

| Path/request target | Rủi ro | Test thích hợp |
| --- | --- | --- |
| **/api/items;v=1** | Semicolon/path parameter/matrix variable | Unit trực tiếp StrictHttpFirewall và request qua HTTP |
| **/api/items/a%2Fb** | Encoded slash có thể tạo segment mới sau decoding | Unit firewall + container HTTP |
| **/api/items/a%5Cb** | Encoded backslash có thể được hiểu như separator | Unit firewall + container HTTP |
| **/api/items/a%25b** | Encoded percent có thể tham gia double decoding | Unit firewall + raw request |
| **/api//items** | Nhiều dấu slash; proxy/router có thể normalize | Unit firewall + request với --path-as-is |
| **/api/../admin** | Dot segment/traversal normalization | Unit firewall + request mà client không tự sửa path |
| **/api/items/%00** | Encoded NUL/ký tự điều khiển | Test tầng container/firewall, không phản chiếu payload nhạy cảm |

Không khẳng định một request nào cũng tới được **StrictHttpFirewall** nguyên dạng. Tomcat, reverse proxy, gateway, WAF hoặc HTTP client có thể xử lý **trước**.

### 6.2. Firewall chạy trước authorization matcher

Trong luồng **FilterChainProxy**, HttpFirewall xử lý request trước khi chọn các filter trong SecurityFilterChain. Một request bị từ chối vì URI không chuẩn không thể được “mở” bằng **permitAll()**, **hasRole()** hoặc **@PreAuthorize**.

Khi nhận request không được phép, Spring Security có thể tạo **RequestRejectedException**; handler mặc định ở nhiều phiên bản Spring Security 6 chuyển thành HTTP 400. Nếu container/proxy chặn trước, HTTP status có thể khác. Unit test exception là dấu hiệu rõ nhất cho luật của chính firewall; integration test xác định kết quả end-to-end.

### 6.3. Có nên bật setAllowSemicolon(true) hoặc encoded slash?

Chỉ khi có nhu cầu nghiệp vụ được phân tích đầy đủ. Một số ứng dụng dùng matrix variables có thể cần **setAllowSemicolon(true)**; nới một luật phải đi kèm test chứng minh authorization matcher và controller diễn giải cùng resource. **setAllowUrlEncodedSlash(true)** không bảo đảm proxy/container cho %2F đi qua và có thể tạo đường dẫn mơ hồ.

Không chuyển toàn bộ ứng dụng sang firewall ít nghiêm ngặt hơn chỉ để một URL hoặc một test trả 200. Thường tốt hơn là chuyển khóa tài nguyên có dấu slash sang query parameter, UUID hoặc một opaque URL-safe ID.

## 7. Ứng dụng mẫu Spring Boot 3.x / Spring Security 6.x

Ví dụ tạo ứng dụng có:
- **GET /api/public/ping**: public và dùng để kiểm tra header.
- **GET /api/private/data**: yêu cầu HTTP Basic authentication.
- CORS chỉ cho phép frontend **https://portal.example.test** vào **/api/**, GET/OPTIONS và header Authorization/Content-Type.
- Security headers mặc định cộng thêm CSP rõ ràng.
- **StrictHttpFirewall** mặc định (không nới lỏng).

### 7.1. Dependencies

Trong dự án Gradle Spring Boot 3.x đã có wrapper, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 7.2. Application, security filter chain, CORS và controller

Tạo **src/main/java/com/example/httpsecurity/HttpSecurityTestingApplication.java**:

~~~java
package com.example.httpsecurity;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class HttpSecurityTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpSecurityTestingApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/api/private/data").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp.policyDirectives(
                                "default-src 'self'; object-src 'none'; "
                              + "frame-ancestors 'none'")))
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
                List.of("https://portal.example.test"));
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Chỉ là credential phục vụ local demo/test.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-password"))
                        .roles("USER")
                        .build());
    }
}

@RestController
class ApiController {
    @GetMapping("/api/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/private/data")
    String privateData(Authentication authentication) {
        return "private-for-" + authentication.getName();
    }
}
~~~

**Giải thích thiết kế:**

1. **cors(Customizer.withDefaults())** bật CORS trong Spring Security; bean CorsConfigurationSource cung cấp policy.
2. **Access-Control-Allow-Origin** không dùng **\*** vì **allowCredentials(true)** chỉ có thể áp dụng an toàn với origin cụ thể hoặc pattern được giới hạn chặt.
3. OPTIONS preflight được CORS filter quyết định trước authentication. Nhưng một GET thật vào private endpoint vẫn phải qua HTTP Basic; không được phép chỉ nhờ origin hợp lệ.
4. Ví dụ không có POST/PUT/DELETE làm thay đổi trạng thái, nên **không tắt CSRF**. Với API thật có cookie/session, phải duy trì CSRF protection phù hợp.
5. **X-Content-Type-Options**, **X-Frame-Options**, HSTS và cache headers được cấu hình theo các mặc định phổ biến; CSP ở đây được **chủ động thêm** bằng **contentSecurityPolicy**.
6. Ví dụ giữ **StrictHttpFirewall mặc định**. Nếu ứng dụng thêm custom HttpFirewall, kết quả unit test mặc định chỉ xác minh policy của instance mới tạo, không chứng minh ứng dụng đang dùng đúng instance đó.

Với nhiều **SecurityFilterChain**, hãy test trên từng chain thực tế. CORS được cấu hình cho một chain không có nghĩa một request rơi vào chain khác sẽ nhận đúng policy.

## 8. Bộ kiểm thử MockMvc và StrictHttpFirewall

Tạo **src/test/java/com/example/httpsecurity/HttpSecurityTestingTest.java**:

~~~java
package com.example.httpsecurity;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityTestingTest {

    private static final String FRONTEND =
            "https://portal.example.test";

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightDoesNotRequireAuthentication()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "GET")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "Authorization"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                        containsString("GET")));
    }

    @Test
    void preflightWithUnknownOriginIsForbidden()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN,
                            "https://untrusted.example.test")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "GET"))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void preflightWithUnsupportedMethodIsForbidden()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "PUT"))
                .andExpect(status().isForbidden());
    }

    @Test
    void preflightWithUnsupportedHeaderIsForbidden()
            throws Exception {
        mvc.perform(options("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "GET")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "X-Admin-Override"))
                .andExpect(status().isForbidden());
    }

    @Test
    void actualGetFromAllowedOriginReceivesCorsHeaders()
            throws Exception {
        mvc.perform(get("/api/public/ping")
                    .header(HttpHeaders.ORIGIN, FRONTEND))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND));
    }

    @Test
    void actualGetFromUnknownOriginIsRejected()
            throws Exception {
        mvc.perform(get("/api/public/ping")
                    .header(HttpHeaders.ORIGIN,
                            "https://untrusted.example.test"))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void ordinaryGetWithoutOriginNeedsNoCorsHeader()
            throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void corsDoesNotReplaceAuthentication()
            throws Exception {
        mvc.perform(get("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND));
    }

    @Test
    void authenticatedRequestStillHasCorsPolicy()
            throws Exception {
        mvc.perform(get("/api/private/data")
                    .header(HttpHeaders.ORIGIN, FRONTEND)
                    .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("private-for-alice"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        FRONTEND));
    }

    @Test
    void ordinaryHttpResponseHasBasicSecurityHeaders()
            throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                        "X-Frame-Options", "DENY"))
                .andExpect(header().string(
                        "Content-Security-Policy",
                        "default-src 'self'; object-src 'none'; "
                      + "frame-ancestors 'none'"))
                .andExpect(header().exists("Cache-Control"))
                .andExpect(header().doesNotExist(
                        "Strict-Transport-Security"));
    }

    @Test
    void hstsIsPresentOnSecureRequest() throws Exception {
        mvc.perform(get("/api/public/ping").secure(true))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Strict-Transport-Security",
                        containsString("max-age=")));
    }

    @Test
    void firewallRejectsSemicolonOverMockMvc()
            throws Exception {
        // MockMvc dùng FilterChainProxy và handler mặc định demo.
        mvc.perform(get("/api/public/ping;v=1"))
                .andExpect(status().isBadRequest());
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/api/items;v=1",
            "/api/items/a%2Fb",
            "/api/items/a%5Cb",
            "/api/items/a%25b",
            "/api//items",
            "/api/../items",
            "/api/items/%00"
    })
    void strictFirewallRejectsAmbiguousUri(String uri) {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", uri);

        assertThatThrownBy(
                () -> firewall.getFirewalledRequest(request))
                .isInstanceOf(RequestRejectedException.class);
    }

    @Test
    void semicolonExceptionDoesNotAllowEncodedSlash() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        firewall.setAllowSemicolon(true);

        assertThatCode(() -> firewall.getFirewalledRequest(
                new MockHttpServletRequest(
                        "GET", "/api/items;v=1")))
                .doesNotThrowAnyException();

        assertThatThrownBy(() -> firewall.getFirewalledRequest(
                new MockHttpServletRequest(
                        "GET", "/api/items/a%2Fb")))
                .isInstanceOf(RequestRejectedException.class);
    }
}
~~~

**Bộ test này kiểm tra nhiều tầng nhưng không đánh đồng chúng:**

- **MockMvc CORS tests** chạy request qua filter chain thật được khởi tạo trong Spring Test context. Chúng không chứng minh chính sách của proxy/WAF ở production.
- **Security header tests** xác nhận cả header mặc định và CSP do ứng dụng đặt. Test HSTS sử dụng **secure(true)** vì một MockMvc request HTTP thường không là secure request.
- **MockMvc firewall test** dùng default FilterChainProxy/RequestRejectedHandler của cấu hình demo Spring Security 6; nếu hệ thống tùy chỉnh handler, HTTP status có thể thay đổi.
- **StrictHttpFirewall unit tests** chứng minh luật chặn URI trên implementation mặc định. Chúng không kiểm tra cách Tomcat, gateway hoặc route MVC xử lý cùng URI.
- Test **setAllowSemicolon(true)** chỉ thay đổi một object firewall tạm trong unit test; **không** bật ngoại lệ trong ứng dụng demo hay yêu cầu production nới lỏng firewall.
- Không có test nào yêu cầu khởi động frontend hoặc thực sự kiểm tra browser SOP; API response có header đúng chỉ là **điều kiện để browser cho phép cross-origin access**, không phải chứng minh front-end đã hoạt động.

### 8.1. Chạy các bài test

Trong thư mục gốc dự án có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.httpsecurity.HttpSecurityTestingTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.httpsecurity.HttpSecurityTestingTest
~~~

**Kết quả kỳ vọng của cấu hình mẫu:** các bài test qua, bao gồm 200 với preflight hợp lệ, 403 khi origin/method/header không được phép, 401 cho private endpoint thiếu xác thực, 200 với HTTP Basic hợp lệ, HSTS trên secure request, 400 cho path chứa semicolon được HttpFirewall chặn, và các bài unit test RequestRejectedException.

Đó là **kết quả kỳ vọng từ thiết kế ví dụ**, không phải log đã chạy được xác nhận. Cần chạy trong dự án Spring Boot/Spring Security đã cấu hình version tương thích để xác nhận compile và behavior. Nếu dùng Spring Security phiên bản khác, cần kiểm tra thay đổi default RequestRejectedHandler, HSTS policy và cách path test được MockMvc xử lý.

### 8.2. Nếu test MockMvc không chạy như kỳ vọng

Kiểm tra:

1. Có **spring-boot-starter-security**, **spring-security-test**, và test context thực sự khởi tạo **SecurityFilterChain** của ứng dụng hay không.
2. Có **@AutoConfigureMockMvc** và filter registration đang bật không. Một MockMvc được dựng bằng **standaloneSetup(...)** không tự động chứa Spring Security filters.
3. Đúng bean **CorsConfigurationSource** có mapping **/api/** và **http.cors(...)** hay không.
4. HSTS test đã tạo **secure(true)** chưa; nếu không, Spring Security thường không gửi HSTS.
5. CSP đã được khai báo rõ chưa; đừng test CSP default khi ứng dụng chưa cấu hình.
6. Một test khác có **@MockBean** thay service hoặc filter làm mất đường thực thi cần kiểm chứng không.
7. Có custom **HttpFirewall**, **RequestRejectedHandler**, SecurityFilterChain order hoặc test profile nào khác không.

## 9. Thử request HTTP thực với curl

Khởi chạy ứng dụng mẫu:

~~~bash
./gradlew bootRun
~~~

### 9.1. Preflight hợp lệ và không hợp lệ

Từ terminal, mô phỏng preflight:

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/private/data' \
  -H 'Origin: https://portal.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Trong mẫu này, phản hồi dự kiến là **200** với **Access-Control-Allow-Origin: https://portal.example.test** và header Allow-Methods/Allow-Headers phù hợp. Không cần gửi Basic credentials trong preflight.

Thử origin khác:

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/private/data' \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: GET'
~~~

Dự kiến **403** từ CORS processing. Có thể có body ngắn **Invalid CORS request**, tùy framework/version. Đừng dùng body hoặc thông báo lỗi này làm căn cứ duy nhất trong hệ thống thật.

### 9.2. Actual request và authentication

~~~bash
curl -i 'http://localhost:8080/api/private/data' \
  -H 'Origin: https://portal.example.test'

curl -i -u alice:demo-password \
  'http://localhost:8080/api/private/data' \
  -H 'Origin: https://portal.example.test'
~~~

Request đầu dự kiến **401** vì không có credentials, request thứ hai dự kiến **200** với body **private-for-alice**. Cả hai vẫn được xử lý theo CORS policy; sự có mặt của Access-Control-Allow-Origin trên một 401 không có nghĩa người dùng đã được cấp quyền.

**curl không thực thi same-origin policy của trình duyệt**, nên các lệnh curl không thể tự chứng minh JavaScript trên origin không được phép sẽ không đọc được response. Với sản phẩm web, kiểm tra thêm DevTools ở trình duyệt thật và test E2E.

### 9.3. Đường dẫn lạ và tầng từ chối

~~~bash
curl --path-as-is -i \
  'http://localhost:8080/api/public/ping;v=1'

curl --path-as-is -i \
  'http://localhost:8080/api/items/a%2Fb'

curl --path-as-is -i \
  'http://localhost:8080/api//items'

curl --path-as-is -i \
  'http://localhost:8080/api/../items'
~~~

**--path-as-is** giảm khả năng curl tự chuẩn hóa một số dạng path trước khi gửi, đặc biệt dot-segment; không có nghĩa mọi byte sẽ được proxy/Tomcat chuyển nguyên vẹn tới Spring.

Diễn giải kết quả:

- **400 và log RequestRejectedException**: tín hiệu cho thấy request đã đến Spring Security HttpFirewall và bị từ chối.
- **400 ở log Tomcat/nginx mà không có Spring Security log**: tầng ngoài có thể chặn trước, đó không phải lỗi Jwt/Auth/Controller.
- **404**: có thể là MVC không tìm thấy route, gateway không map path, hoặc URL đã bị chuẩn hóa; không chứng minh firewall đã từ chối.
- **403**: có thể xuất phát từ CORS, authorization hoặc security handler khác; phải xem request và log liên quan.
- **200** với đường dẫn mơ hồ: cần kiểm tra URL đã được biến đổi ở tầng nào, liệu một route bypass hoặc firewall đã bị nới lỏng; đừng tự động xem là kết quả mong muốn.

**Không bật encoded slash hoặc semicolon một cách đại trà để khiến test HTTP thành công.** Quan sát sự khác biệt giữa các tầng rồi thiết kế URL, routing và matcher đồng nhất.

## 10. Kiểm thử qua reverse proxy, gateway và HTTPS

Trong production có thể có kiến trúc:

~~~text
Browser HTTPS
   ▼
Edge proxy / WAF (host, TLS, path rewrite)
   ▼
Tomcat HTTP nội bộ
   ▼
Spring Security Servlet
~~~

Một bộ test chạy trực tiếp localhost:8080 không xác nhận những hành vi ở public edge. Khi kiểm thử staging qua reverse proxy, hãy xác nhận:

1. Public URL dùng đúng **https**, hostname và path prefix. Nếu proxy strip prefix, đường dẫn bên ngoài và bên trong phải map nhất quán.
2. Chỉ proxy tin cậy được phép đặt **Forwarded / X-Forwarded-Proto / X-Forwarded-Host / X-Forwarded-Prefix**. Client không được tiêm forwarded headers để đánh lừa server về scheme/host/path.
3. **HSTS** có trên final HTTPS response ở public edge, kể cả khi TLS kết thúc ở proxy. Nếu app chỉ thấy HTTP nội bộ, có thể cần trusted forwarded header handling hoặc phát HSTS ở edge.
4. **CSP, nosniff, frame policy** có trên response trả cho người dùng, không bị proxy ghi đè/bỏ sót.
5. CORS preflight không bị redirect sai, không bị gateway authentication chặn hoặc trả policy wildcard. Test cả **OPTIONS** và actual method.
6. CORS policy khác nhau theo API/chain phải được kiểm trên từng route và từng origin, không chỉ trên **/api/public/ping**.
7. Proxy/caching layer phải xử lý **Vary: Origin** phù hợp nếu cache response theo Origin; tránh dùng response chứa ACAO của origin A cho origin B.
8. Request target có percent encoding/dot segments/semicolons được kiểm ở **edge lẫn container**, không chỉ MockMvc. Phải ghi nhận tầng từ chối.
9. Khi có nhiều path rewrite hoặc context path, đảm bảo authorization matcher trên đường dẫn mà ứng dụng thực thi, không chỉ đường dẫn public trước rewrite.
10. Nếu response lỗi được tạo hoàn toàn ở gateway, Spring Security header writers không chạy; cần cấu hình security headers tại nơi tạo **error response** đó khi phù hợp.

Không đưa raw Authorization/Cookie/token hoặc dữ liệu người dùng vào request log công khai để chẩn đoán các test này.

## 11. Những lỗi kiểm thử thường gặp

| Sai lầm | Vì sao sai | Cách kiểm tra đúng |
| --- | --- | --- |
| Test OPTIONS trả 200 rồi kết luận CORS đúng | Có thể thiếu ACAO/Allowed-Headers hoặc origin bị phản chiếu tùy ý | Kiểm tra cả status và **Access-Control-Allow-Origin/Methods/Headers** |
| Bỏ qua negative test origin lạ | Cấu hình quá rộng vẫn pass happy path | Test origin không hợp lệ, method/header không hợp lệ |
| Coi Origin hợp lệ là đã authentication | CORS chỉ là browser cross-origin policy | Test riêng 401/403 cho endpoint private |
| Dùng curl để xác nhận “trình duyệt sẽ chặn đọc” | curl không thực thi SOP | Kết hợp integration test với browser E2E/DevTools |
| Tắt CSRF vì đã bật CORS | CORS không bảo vệ khỏi mọi request thay đổi trạng thái | Kiểm tra CSRF theo cookie/session và unsafe method |
| Chỉ assert status 200, không kiểm header | Thiếu CSP, HSTS hoặc nosniff khó phát hiện | Assert từng header và điều kiện secure request |
| Yêu cầu HSTS trên MockMvc HTTP request | Header mặc định áp cho HTTPS/secure request | Dùng **.secure(true)** và test HTTPS public edge |
| Giả định Spring Security tự phát CSP | CSP không phải mặc định chung | Cấu hình **contentSecurityPolicy(...)** rồi test |
| Chỉ test controller standalone | Không chạy FilterChainProxy, CorsFilter hoặc HttpFirewall | Dùng **@SpringBootTest + @AutoConfigureMockMvc** hoặc MockMvc với springSecurity() |
| Mọi 400 đều bị coi là firewall | Container/proxy có thể chặn sớm | Đối chiếu log, unit firewall và request qua container |
| Chỉ test path bình thường | Bỏ sót encoded slash, semicolon, dot segments và double encoding | Thêm matrix URI bất thường |
| Dùng percent-encoded URL trong test mà client tự sửa | Test không còn gửi URI mà mình nghĩ | Dùng **--path-as-is**, inspect raw path và network boundary |
| Nới HttpFirewall để test xanh | Có thể mở lại đường dẫn mơ hồ | Giữ mặc định; chỉ nới theo yêu cầu nghiệp vụ đã đánh giá |
| Tắt security headers toàn bộ để “giảm xung đột” | Mất nhiều cơ chế browser defense | Điều chỉnh từng policy, test trên actual response |
| Chỉ test 200 mà quên response lỗi | 401/403/404 có thể đi qua handler/gateway khác | Test response lỗi theo từng nơi tạo response |

## 12. Checklist cho HTTP security test suite

- **Đúng test layer:** Có MockMvc với security filters, unit StrictHttpFirewall và HTTP E2E qua container/edge.
- **CORS:** Test allowed origin, unknown origin, preflight allowed, disallowed method/header, actual request có/không credentials; so sánh chính xác ACAO.
- **CORS vs auth:** Chứng minh preflight không cần credentials, nhưng actual private request vẫn cần authentication và authority.
- **Security headers:** Kiểm tra nosniff, frame policy, CSP đã cấu hình, cache policy và HSTS chỉ khi HTTPS/secure context; test final response qua proxy.
- **Firewall:** Có test dấu chấm phẩy, encoded slash/backslash/percent, duplicate slash, dot segments, encoded NUL; xác định tầng từ chối.
- **Routing:** Khi có nhiều SecurityFilterChain hoặc path prefix, thử từng chain và xác minh matcher đúng endpoint sau rewrite.
- **HTTP status:** Phân biệt 400 parser/firewall, 401 authentication, 403 CORS/authorization; không suy luận một status từ một nguyên nhân duy nhất.
- **CSRF:** Với cookie/session và unsafe methods, có test CSRF riêng. Không xem CORS là biện pháp thay thế.
- **Proxy trust:** Forwarded headers chỉ được chấp nhận từ proxy tin cậy; test HTTPS/HSTS, Vary và security header trên public edge.
- **An toàn test:** Không dùng credential production, không log token/cookie, không đưa payload bất thường tới hệ thống bên thứ ba không được phép.
- **Bảo trì:** Sau khi nâng Spring Security, Tomcat hoặc cấu hình proxy, chạy lại cả positive/negative cases; dùng assertions không phụ thuộc header order không cần thiết.

**Kết luận:** Một HTTP security test suite tốt không chỉ hỏi endpoint trả 200 hay không. Nó phải chứng minh **trình duyệt chỉ nhận CORS cho origin phù hợp**, **request thật vẫn được xác thực/phân quyền**, **response phát đúng security headers**, và **URL không chuẩn bị xử lý nhất quán tại firewall, container và reverse proxy**. Kết hợp MockMvc, unit test StrictHttpFirewall và kiểm thử end-to-end ở public edge giúp tránh cả false positive lẫn nguy cơ bypass do bất đồng cách hiểu đường dẫn.
