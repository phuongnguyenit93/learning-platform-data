# Preflight OPTIONS và thứ tự xử lý trước xác thực

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Proxy và CORS

## 1. Vấn đề: vì sao OPTIONS bị 401 trong khi GET có token?

Giả sử giao diện frontend chạy tại **http://localhost:5173** và API Spring Boot chạy tại **http://localhost:8080**. Người dùng đã đăng nhập, frontend muốn gọi GET /api/profile với header **Authorization** hoặc header ứng dụng **X-Request-Id**. Trình duyệt có thể gửi một **OPTIONS preflight request** trước khi gửi GET thật.

Ví dụ JavaScript mô tả yêu cầu:

~~~javascript
fetch("http://localhost:8080/api/profile", {
    headers: {
        "Authorization": "Bearer <access-token>",
        "X-Request-Id": "request-101"
    }
});
~~~

Đây chỉ minh họa một frontend có cơ chế lấy token hợp lệ; demo runnable ở phần sau sử dụng **HTTP Basic** để dễ thử bằng curl, không có chức năng cấp bearer token.

Nếu **OPTIONS** bị bộ lọc authentication từ chối với **401 Unauthorized**, browser có thể báo lỗi CORS và **không gửi GET thật**. Do đó thêm token vào GET, sửa controller hay mở quyền GET không tự giải quyết được lỗi. Cần cấu hình **CORS được xử lý trước bước authentication** cho một preflight hợp lệ, rồi vẫn kiểm tra authentication/authorization trên actual request.

Bài học hướng tới việc:

- Hiểu origin và điều kiện phát sinh preflight.
- Đọc đúng các CORS request/response headers.
- Nắm rõ thứ tự **CorsFilter → Authentication → Authorization → Controller** trong Servlet Spring Security.
- Chạy ví dụ **Spring Boot 3.x + Spring Security 6 + Java 17+**.
- Kiểm thử OPTIONS thành công không cần credential, trong khi GET thực tế vẫn đòi xác thực.
- Phân biệt CORS với **CSRF**, các lỗi 401/403 và các tác nhân chặn OPTIONS ở **proxy, ingress, CDN, API gateway**.

## 2. Origin: scheme, hostname và port

Một origin là tổ hợp **scheme + hostname + port**. CORS là cơ chế do browser thực thi khi JavaScript ở origin này muốn truy cập resource của origin khác.

| Frontend | API | Có cùng origin? | Lý do |
| --- | --- | --- | --- |
| http://localhost:5173 | http://localhost:8080/api/profile | Không | Port khác. |
| https://app.example.test | https://api.example.test/profile | Không | Host khác. |
| http://app.example.test | https://app.example.test/api | Không | Scheme khác. |
| https://example.test | https://example.test/api | Có | Scheme, host và port mặc định khớp. |
| https://example.test:443 | https://example.test/api | Có | Port 443 là mặc định của HTTPS. |

**CORS không phải authentication hoặc firewall.** Một HTTP client như curl có thể tự gắn Origin; nó không tuân thủ giới hạn đọc response của browser. Chỉ cho phép một origin không chứng minh người gọi có quyền xem dữ liệu. Backend vẫn phải kiểm tra credential, permission và input.

**CORS cũng không chặn mọi request cross-origin trước khi đến server.** Một số request thuộc nhóm simple có thể được gửi thật, rồi browser chỉ chặn JavaScript đọc response nếu server không cung cấp CORS permission. Điều này đặc biệt quan trọng khi thiết kế bảo vệ CSRF.

## 3. Khi nào browser cần gửi preflight OPTIONS?

Một cross-origin request thường cần preflight nếu dùng method hoặc request headers nằm ngoài nhóm **CORS-safelisted**. Những trường hợp quen thuộc:

| Actual request được JavaScript dự định gửi | Có preflight thông thường? | Giải thích |
| --- | --- | --- |
| GET, không có header tùy chỉnh | Không | Có thể thuộc simple request. |
| GET với Authorization | Có | Authorization không phải CORS-safelisted header. |
| GET với X-Request-Id | Có | Header tự định nghĩa không safelisted. |
| POST với Content-Type: application/json | Có | JSON không thuộc nhóm safelisted Content-Type. |
| POST với Content-Type: application/x-www-form-urlencoded và header an toàn | Thường không | Có thể là simple request. |
| POST với multipart/form-data đúng điều kiện safelist | Thường không | Một form upload đơn giản có thể không cần preflight. |
| PUT, PATCH hoặc DELETE cross-origin | Có | Method không thuộc nhóm GET/HEAD/POST. |
| GET tới cùng origin | Không vì CORS | Không có cross-origin boundary cần kiểm tra. |

Các nhóm safelisted request methods cơ bản là **GET, HEAD, POST**. Những Content-Type thường được phép trong phạm vi điều kiện safelist là **application/x-www-form-urlencoded, multipart/form-data và text/plain**; các giới hạn bổ sung của Fetch Standard vẫn áp dụng. Không chỉ nhìn tên method mà bỏ qua header.

Browser có một **preflight cache** độc lập với HTTP cache thông thường. Vì vậy lần gọi thứ hai có thể bỏ qua OPTIONS trong khi request vẫn là loại có thể preflight, miễn kết quả cache còn phù hợp. Không có nghĩa browser hoặc server đã tắt CORS.

**Frontend bình thường không cần tự phát OPTIONS.** Browser tự thực hiện trước khi gửi actual request. Dùng curl để giả lập OPTIONS chỉ là cách xác minh server, không khiến browser lưu cache preflight thay cho request của browser.

## 4. Preflight hỏi điều gì và không gửi điều gì?

Giả sử browser cần GET /api/profile với hai header Authorization và X-Request-Id. Nó có thể gửi:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization,x-request-id
~~~

Điểm phân biệt:

1. **OPTIONS** là method của bước preflight.
2. **Access-Control-Request-Method: GET** hỏi liệu method **của actual request** có được phép không.
3. **Access-Control-Request-Headers** chứa **tên header** browser định gửi, không phải giá trị token.
4. **Origin** là origin của frontend, không phải URI của backend.
5. Preflight của browser thông thường **không mang Authorization hoặc cookie phiên JSESSIONID**; do đó không thể yêu cầu nó phải đăng nhập như request thật.
6. Các header HTTP khác có thể xuất hiện tùy browser, nhưng không thay đổi ý nghĩa của ba trường CORS chính.

Server cho phép request có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization,x-request-id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Đây là response minh họa. Spring CorsFilter thường trả **200** khi preflight hợp lệ; một API gateway có thể dùng **204 No Content**. Thứ tự/cách viết hoa header và cách gộp **Vary** khác nhau là bình thường nếu semantics đúng.

Các header có vai trò khác nhau:

| Header | Ý nghĩa |
| --- | --- |
| Origin | Origin thực của trang/browser gửi yêu cầu. |
| Access-Control-Request-Method | Method dự kiến của actual request. |
| Access-Control-Request-Headers | Tên những request headers sẽ xuất hiện ở actual request. |
| Access-Control-Allow-Origin | Origin được server chấp nhận; với credentialed request không được dùng wildcard không kiểm soát. |
| Access-Control-Allow-Methods | Method được phép dùng từ origin này. |
| Access-Control-Allow-Headers | Request headers được phép gửi. |
| Access-Control-Allow-Credentials | Cho phép browser cung cấp credentials theo chính sách CORS khi bật true. |
| Access-Control-Max-Age | Thời gian browser có thể cache **kết quả preflight**; không phải data TTL. |
| Vary | Định hướng shared cache phân biệt phản hồi dựa trên Origin/method/headers được hỏi. |
| Access-Control-Expose-Headers | Đặt ở actual response để JavaScript đọc những response header không thuộc safelist. |

Sau khi preflight đạt yêu cầu, browser mới gửi GET thật:

~~~http
GET /api/profile HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Authorization: Bearer <access-token>
X-Request-Id: request-101
~~~

**Preflight 200 không đồng nghĩa GET 200.** Request GET có thể trả 401 vì không có credential, 403 vì thiếu quyền hoặc status khác vì logic nghiệp vụ. Nếu actual response có CORS headers hợp lệ, frontend có thể đọc status 401/403 để xử lý trạng thái đăng nhập phù hợp.

## 5. Vì sao xử lý CORS trước authentication?

Spring Security Servlet documentation nêu rõ CORS phải được xử lý **trước Spring Security authentication**, bởi preflight thường không có cookie như **JSESSIONID**. Nếu filter kiểm authentication chạy trước và yêu cầu session cho mọi request, OPTIONS bị 401/403, kết thúc trước khi bộ xử lý CORS được áp dụng.

Luồng sai:

~~~text
Browser: OPTIONS /api/profile
  |
  v
Spring Security authentication filter
  |
  +--> Cookie/Authorization khong co
  |
  +--> 401 Unauthorized (hoac redirect login)
  |
  X   CORS headers khong duoc tao
  |
Browser: chan luong, khong gui GET that.
~~~

Luồng đúng:

~~~text
Browser: OPTIONS + Origin + Access-Control-Request-Method
  |
  v
CorsFilter / CORS processing duoc tich hop vao SecurityFilterChain
  |
  +--> Kiem origin, requested method, requested headers
  |      |
  |      +--> Hop le: tra headers CORS, ket thuc preflight
  |      |
  |      +--> Khong hop le: reject CORS
  |
  X   Khong yeu cau auth cho preflight

Browser: actual GET + Authorization/Cookie neu co
  |
  v
CORS validation cua actual request
  |
  v
Authentication -> Authorization -> Controller
  |
  v
Actual response + cac CORS headers phu hop
~~~

Nói "CORS trước Spring Security" không bắt buộc **tự tạo Servlet CorsFilter bean** có order thấp nhất. Spring Security 6 hỗ trợ **http.cors(Customizer.withDefaults())** để tích hợp CorsFilter đúng vị trí trong security filter chain khi có nguồn cấu hình phù hợp.

**Đừng nhầm OPTIONS thông thường với CORS preflight.** Preflight có đặc điểm như Origin và Access-Control-Request-Method. Một OPTIONS thiếu những header này có thể tiếp tục đi qua authorization theo chính sách mặc định của hệ thống.

### Chỉ permitAll OPTIONS đã đủ chưa?

Ví dụ cấu hình sau **không phải giải pháp CORS hoàn chỉnh**:

~~~java
// Mau minh hoa khong du de thay the CorsFilter:
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Dù OPTIONS không còn bị authentication chặn, browser vẫn yêu cầu **Access-Control-Allow-Origin**, **Allow-Methods**, **Allow-Headers** tương ứng; nếu thiếu, preflight vẫn thất bại. Ngược lại, với CorsFilter đúng chỗ, không cần mở **mọi OPTIONS** trên mọi URL chỉ để preflight chạy.

Không tắt bảo mật GET/POST để sửa OPTIONS; các actual requests vẫn phải được xác thực và phân quyền như trước.

## 6. CORS khác authentication, authorization và CSRF

| Mục tiêu | Thành phần tiêu biểu | Có tác dụng trên preflight không? |
| --- | --- | --- |
| Origin có được phép trao đổi cross-origin không? | CORS policy/CorsFilter | **Có**, đây là bước kiểm tra cần thiết. |
| Ai đang gọi API? | Spring Security authentication, session/JWT/Basic | **Không dùng preflight để kiểm danh tính người dùng**; kiểm actual request. |
| Người dùng có quyền đọc/sửa tài nguyên không? | Authorization role/scope/ownership | **Kiểm actual request**, không suy từ CORS. |
| Request thay đổi trạng thái có bị trang khác lợi dụng credential tự động gửi không? | CSRF token, Origin validation và những biện pháp bổ sung | **Kiểm trên actual state-changing request**, không dựa vào preflight như lớp phòng thủ duy nhất. |

**CORS không phải một lớp chống CSRF hoàn chỉnh.** Form POST simple cross-origin có thể không preflight mà vẫn làm server xử lý nếu backend không có CSRF protection. Với cookie-based session, cần cân nhắc CSRF token và SameSite cùng các biện pháp bổ sung. Nếu một ứng dụng dùng HTTP Basic và browser tự gửi credential, rủi ro CSRF cũng cần được phân tích.

**Không tắt csrf() chỉ để xử lý OPTIONS.** Trong bài demo chỉ có GET endpoints, nên giữ cấu hình CSRF mặc định. Khi mở POST, PUT, DELETE, phải quyết định chính sách xác thực và CSRF riêng; OPTIONS preflight thành công không bảo đảm actual POST sẽ không bị 403.

## 7. Demo Spring Boot 3.x + Java 17+ với SecurityFilterChain

Dự án dùng Spring MVC, embedded Tomcat, Spring Security 6. Hai endpoint:

- **GET /api/public/ping** công khai, phù hợp cho browser thử preflight mà không lộ credential.
- **GET /api/profile** yêu cầu xác thực HTTP Basic; preflight được chấp nhận trước authentication, còn GET thật chưa đăng nhập phải trả 401.

Dùng Spring Boot **3.3.13** để có bộ dependency nhất quán cho ví dụ. Với dự án mới, nên chọn phiên bản Boot còn hỗ trợ bảo trì và kiểm tra thay đổi của framework.

### 7.1. Cấu trúc file

~~~text
cors-preflight-demo/
  pom.xml
  src/main/
    java/com/example/corsdemo/
      CorsPreflightDemoApplication.java
      WebSecurityConfiguration.java
    resources/
      application.properties
  src/test/
    java/com/example/corsdemo/
      CorsPreflightDemoApplicationTests.java
~~~

### 7.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cors-preflight-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Không dùng **WebSecurityConfigurerAdapter** vì Spring Security 6 đã chuyển sang cấu hình dựa trên **SecurityFilterChain**.

### 7.3. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=cors-preflight-demo
~~~

### 7.4. Main class và controller

Tạo **src/main/java/com/example/corsdemo/CorsPreflightDemoApplication.java**:

~~~java
package com.example.corsdemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CorsPreflightDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsPreflightDemoApplication.class, args);
    }
}

@RestController
class DemoApiController {

    @GetMapping("/api/public/ping")
    public ResponseEntity<Map<String, String>> ping() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-public")
                .body(Map.of("message", "pong"));
    }

    @GetMapping("/api/profile")
    public ResponseEntity<Map<String, String>> profile(Principal principal) {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-profile")
                .body(Map.of("user", principal.getName(),
                             "status", "authenticated"));
    }
}
~~~

Một public class được khai báo trong file trùng tên; controller package-private ở cùng package được component scan. **Principal** chỉ có khi actual request đã xác thực thành công theo SecurityFilterChain.

Header **X-Request-Id** là giá trị mẫu để kiểm **Access-Control-Expose-Headers**; trên production nên lấy request ID do tracing/middleware cung cấp.

### 7.5. Cấu hình CORS và Security

Tạo **src/main/java/com/example/corsdemo/WebSecurityConfiguration.java**:

~~~java
package com.example.corsdemo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/api/profile").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}demo-pass")
                .roles("LEARNER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Giải thích các quyết định chính:**

1. **.cors(Customizer.withDefaults())** tích hợp CORS vào Spring Security. Với một **UrlBasedCorsConfigurationSource** bean, Spring Security biết source nào chứa policy.
2. **setAllowedOrigins** chứa **frontend origin** chứ không phải địa chỉ backend. Host và port cần khớp chính xác, ví dụ 5173 khác 3000.
3. **setAllowedMethods(List.of("GET"))** cho biết method của **actual request** được phép. Preflight dùng OPTIONS nhưng header **Access-Control-Request-Method** hỏi GET; không nhất thiết thêm OPTIONS vào danh sách này.
4. **setAllowedHeaders** nói tới tên request headers frontend được gửi. Đối với **Authorization**, chỉ cho phép tên, không có nghĩa server chấp nhận token sai.
5. **setExposedHeaders** cho phép JavaScript đọc response header **X-Request-Id** vốn không thuộc response-header safelist.
6. **setAllowCredentials(true)** minh họa credentialed CORS cho một origin cụ thể. Đây là mức tin cậy cao; hệ thống không cần cross-origin cookie/credentials nên cân nhắc để false. Không kết hợp true với **allowedOrigins="*"**.
7. **setMaxAge(3600L)** điều khiển browser preflight cache, không làm dữ liệu profile được cache một giờ.
8. **anyRequest().denyAll()** cho thấy actual endpoints ngoài danh sách không tự mở quyền. Preflight hợp lệ được CorsFilter xử lý trước quy tắc bảo vệ actual request.
9. **CSRF mặc định không bị tắt**, vì bài chỉ cung cấp GET endpoints. Không có lý do bỏ CSRF để sửa CORS.
10. **{noop}demo-pass** và HTTP Basic chỉ phục vụ local demo. Production cần authentication provider an toàn, mật khẩu hash đúng cách, HTTPS và quản lý bí mật; không để password cứng ở source.

**Lưu ý:** không khai báo thêm một **CorsFilter** Servlet độc lập với policy khác, tránh xử lý trùng. Nếu dùng nhiều **SecurityFilterChain** hoặc nhiều nguồn CORS, phải gắn đúng policy vào chain phục vụ path đích. Nếu dùng Spring MVC global config/**@CrossOrigin** thay source bean, vẫn cần bật CORS integration trong Spring Security và kiểm các luật merge.

### 7.6. Build, test và khởi động

Từ thư mục chứa pom.xml, với Maven và Java 17+:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Server lắng nghe **http://localhost:8080**. Nếu Maven đã cài dependency đầy đủ, các lệnh chạy mà không cần frontend. Lệnh test dùng test class ở phần sau; server được chạy bằng lệnh thứ hai sau khi test thành công.

## 8. Kiểm tra OPTIONS và actual request bằng curl

**Curl không tự phát preflight như browser.** Để tái hiện, phải gọi OPTIONS với headers giống browser. Những kết quả dưới đây giả sử truy cập trực tiếp Spring Boot, không có proxy sửa response.

### A. Preflight hợp lệ và không có Authorization

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,x-request-id'
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization,x-request-id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
~~~

Có thể có **Vary** và một số header khác. Thứ tự/cách viết hoa không quan trọng; điều quan trọng là OPTIONS hợp lệ được chấp nhận **không cần credential**, trong khi actual profile vẫn yêu cầu authentication.

### B. Actual GET thiếu credential

~~~bash
curl -i -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/profile'
~~~

Kỳ vọng **401 Unauthorized** do HTTP Basic authentication của demo. Response vẫn có thể có **Access-Control-Allow-Origin** cho frontend được phép đọc lỗi. **Preflight PASS + actual 401** không phải mâu thuẫn.

### C. Actual GET với credential hợp lệ

~~~bash
curl -i -u learner:demo-pass \
  -H 'Origin: http://localhost:5173' \
  -H 'X-Request-Id: web-101' \
  'http://localhost:8080/api/profile'
~~~

Kỳ vọng **200 OK**, JSON chứa:

~~~json
{"user":"learner","status":"authenticated"}
~~~

Thứ tự property JSON có thể khác. Response có thể bao gồm **Access-Control-Expose-Headers: X-Request-Id** cùng header mẫu **X-Request-Id: demo-profile**.

**-u** gửi HTTP Basic cho request thật. Browser preflight sẽ không tự mang credential từ -u, bởi đây là hai cơ chế client khác nhau. Trên production không dùng password trực tiếp trong terminal history hoặc source code.

### D. Origin không hợp lệ

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: GET'
~~~

Với demo, CORS processor thường trả **403 Forbidden/Invalid CORS request** vì origin không thuộc allowlist. Đây là từ chối **CORS**, không tự động chứng minh user không có role hay JWT sai.

### E. Method không được phép

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE'
~~~

Chỉ GET được cho phép trong CORS config, nên preflight hỏi DELETE phải bị từ chối. Ngay cả khi cho DELETE trong CORS, vẫn cần @DeleteMapping, authentication, authorization và CSRF protection khi phù hợp.

### F. Header không được phép

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/profile' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-unknown-header'
~~~

Tên **x-unknown-header** không có trong allowedHeaders nên preflight bị từ chối theo policy. Không bật allowedHeaders="*" vô điều kiện nếu chưa xem mục đích các custom headers và trust boundary.

### G. OPTIONS bình thường, không phải preflight

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/profile'
~~~

Request này thiếu **Origin** và **Access-Control-Request-Method**, vì vậy nó không được xử lý như một preflight CORS hợp lệ. Với **anyRequest().denyAll()**, có thể trả 403. Không dùng kết quả OPTIONS không có header để bác bỏ thành công của test preflight ở case A.

## 9. JavaScript/browser test không nhúng password

Một frontend thực ở **http://localhost:5173** có thể kiểm tra endpoint public:

~~~javascript
async function loadPing() {
  const response = await fetch(
    "http://localhost:8080/api/public/ping",
    {
      method: "GET",
      headers: { "X-Request-Id": "browser-1" }
    }
  );

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  const payload = await response.json();
  const requestId = response.headers.get("X-Request-Id");
  console.log(payload.message, requestId);
}

loadPing().catch(console.error);
~~~

Khi browser thấy cross-origin GET chứa **X-Request-Id**, nó thường gửi preflight OPTIONS /api/public/ping trước rồi mới gửi GET. Console có thể in **pong demo-public** vì API public trả message pong và response header đã được expose.

**Nếu không thấy OPTIONS:** có thể browser đang dùng preflight cache, frontend đã đi qua dev proxy cùng origin, hoặc request không còn header kích hoạt. Xem **DevTools Network**, Request URL, Origin và danh sách request thực tế; không tự đánh đồng “không thấy OPTIONS” với “CORS đã tắt”.

**Không cố sửa bằng fetch mode "no-cors".** Khi no-cors, response thường trở thành **opaque** và JavaScript không được đọc body/status/header như mong muốn. Giải pháp là cấu hình server và proxy đúng.

### Cookie/credentials trong fetch

Nếu API sử dụng cookie phiên cross-origin và được phép theo thiết kế, frontend thường cần:

~~~javascript
fetch("https://api.example.test/account", {
  credentials: "include"
});
~~~

Đoạn này chỉ mô tả cú pháp; URL ví dụ không phải endpoint của demo Basic. Với **credentials: include**, server cần **Access-Control-Allow-Credentials: true** và **Access-Control-Allow-Origin** cụ thể, không phải wildcard. Cookie còn chịu **SameSite**, **Secure**, **Domain**, **Path**, HTTPS và chính sách của browser đối với third-party cookies.

**Preflight không cần mang JSESSIONID để xác thực user.** Browser sẽ quyết định gửi cookie trong actual request dựa trên credentials mode và cookie policy. Nếu actual request sử dụng Authorization header do JavaScript đặt, phải cho phép **Authorization** trong Access-Control-Allow-Headers.

## 10. Sai lầm thường gặp khi phối hợp CORS và security

### 10.1. Chỉ thêm @CrossOrigin ở controller

**@CrossOrigin** và **WebMvcConfigurer#addCorsMappings** hỗ trợ CORS ở Spring MVC HandlerMapping. Nhưng nếu security filter chặn OPTIONS trước HandlerMapping, annotation có thể không được dùng cho request đó.

Có hai cách thường hợp lệ:

1. Cấu hình **CorsConfigurationSource** bean và **http.cors(...)** như demo.
2. Cấu hình MVC CORS global/@CrossOrigin và bật **http.cors(...)** để Spring Security sử dụng nguồn MVC CORS khi phù hợp.

Cần review các luật kết hợp global + local và tránh khai báo hai policy không nhất quán. Với nhiều SecurityFilterChain, không suy rằng policy của chain A được áp dụng cho preflight vào chain B.

### 10.2. Cho phép OPTIONS nhưng thiếu CORS headers

Nếu chỉ **permitAll OPTIONS**, preflight có thể nhận status 200/204, nhưng browser vẫn chặn actual request vì không có **Access-Control-Allow-Origin**, hoặc thiếu requested method/header. CORS policy phải được áp dụng thực tế.

### 10.3. Dùng wildcard khi credentials được bật

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Đây **không phải** credentialed CORS response hợp lệ cho browser. Spring Framework cũng không cho **allowedOrigins="*"** kết hợp **allowCredentials=true** theo cấu hình chuẩn. Nếu có nhu cầu tenant dynamic, dùng **allowedOriginPatterns** với danh sách/pattern được quản trị, không phản chiếu mọi Origin không kiểm soát.

### 10.4. Đánh đồng 403 với cùng một nguyên nhân

- **403 ở preflight**: có thể do origin, method, header không được phép.
- **403 ở actual request**: có thể do authorization, CSRF, CORS actual check, WAF hoặc proxy.
- **401 ở preflight**: thường nghi vấn filter/gateway xác thực chạy trước CORS.
- **401 ở actual request**: thường do thiếu/không hợp lệ credential theo authentication scheme.
- **302 đến trang login trong preflight**: có thể browser coi là lỗi CORS hoặc redirect không phù hợp; không yêu cầu browser đăng nhập qua OPTIONS.

Luôn xác định **request nào trả status**, từ **layer nào**, trước khi sửa.

## 11. Reverse proxy, ingress, API gateway và thứ tự xử lý

Một request thực có thể đi qua nhiều thành phần:

~~~text
Browser
  |
  v
CDN / WAF / API Gateway (co the chan OPTIONS)
  |
  v
Ingress / Nginx (co the rewrite path, tra 204, redirect)
  |
  v
Spring Boot Servlet filter chain
  |
  v
CorsFilter -> Authentication -> Authorization -> Controller
~~~

**Nếu reverse proxy trả 401 trước Spring, bật http.cors ở backend chưa đủ.** Phải thống nhất nơi xử lý OPTIONS:

**Phương án backend quản lý:** proxy bảo toàn các header Origin, Access-Control-Request-Method, Access-Control-Request-Headers và forward OPTIONS vào Spring. Các lớp authentication ở edge không chặn preflight, nhưng vẫn bảo vệ actual request.

**Phương án gateway quản lý:** gateway trả preflight **200/204** theo chính sách origin/method/header, trước authentication ở gateway; actual request sau đó mới đi qua authentication và backend. Actual response, kể cả 401/403, cần CORS headers phù hợp. Tránh gateway và backend cùng phát Access-Control-Allow-Origin mâu thuẫn hoặc trùng nhau.

**Các lỗi proxy thường thấy:**

- Edge chỉ cho GET/POST và trả **405** cho OPTIONS.
- OAuth2 proxy redirect preflight đến trang login bằng 302/303.
- HTTPS public endpoint redirect OPTIONS từ HTTP, gây browser lỗi redirect hoặc mixed content.
- Ingress xóa Origin/Access-Control-Request-* khiến Spring không nhận diện preflight.
- Proxy rewrite **/api/profile** thành **/profile** nhưng CORS source chỉ đăng ký **/api/**.
- CDN cache một response preflight cho Origin A rồi trả lại cho Origin B vì cache key/Vary cấu hình sai.
- Gateway phát wildcard Allow-Origin trong khi backend trả origin cụ thể và Allow-Credentials true.
- WAF chặn OPTIONS hoặc header Authorization name trong Access-Control-Request-Headers dù GET thật được phép.

**Vary** cần xét khi response CORS khác theo Origin, requested method và requested headers. Nếu CDN cache preflight, phải phân biệt đúng các chiều ấy, không dùng response cho origin khác. **Access-Control-Max-Age** hướng browser preflight cache; nó không đặt TTL của dữ liệu API.

Với request thật có dữ liệu riêng tư, cần kiểm **Cache-Control** và shared-cache policy riêng. Không đánh đồng “cho phép origin đọc response” với “cho phép CDN public cache response này”.

### CORS không bảo vệ khỏi Origin giả mạo ngoài browser

Curl có thể chủ động gửi **Origin: http://localhost:5173** từ bất kỳ nơi nào. Điều đó không biến curl thành frontend tin cậy. API luôn phải xác thực request thật, phân quyền theo resource và chống CSRF theo mô hình authentication. CORS là cơ chế kiểm soát của browser, không phải cơ chế xác minh khách hàng API.

## 12. MockMvc integration tests kiểm tra đúng thứ tự

Tạo file **src/test/java/com/example/corsdemo/CorsPreflightDemoApplicationTests.java**:

~~~java
package com.example.corsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPreflightDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization,x-request-id"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173"))
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true"));
    }

    @Test
    void actualRequestWithoutLoginIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173"));
    }

    @Test
    void actualRequestWithLoginSucceeds() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("learner", "demo-pass"))
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void unknownOriginIsRejected() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://untrusted.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void forbiddenMethodIsRejected() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Điểm cần hiểu:

- **@SpringBootTest + @AutoConfigureMockMvc** dựng application context và tích hợp Spring Security filters.
- Preflight hợp lệ cho endpoint protected được chấp nhận **không credential**.
- Actual request chưa xác thực vẫn **401**.
- Actual request có HTTP Basic hợp lệ trả **200** và Principal được đọc trong controller.
- Origin/method sai bị từ chối ở CORS policy.
- Test này không thay thế browser thật, CDN, HTTPS, redirects, preflight cache hay cookie blocking policy.

Khi thêm actual POST, hãy bổ sung integration test **CSRF/authorization**; preflight OPTIONS 200 không chứng minh mọi POST được chấp nhận.

## 13. Spring WebFlux và reactive security

Nếu ứng dụng dùng **spring-boot-starter-webflux** trên Reactor Netty, Servlet **CorsFilter** và **SecurityFilterChain** không phải API đúng của reactive stack. WebFlux có:

- **CorsWebFilter**.
- **SecurityWebFilterChain** và **ServerHttpSecurity.cors(...)**.
- **org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource**.
- **WebFluxConfigurer#addCorsMappings** và cơ chế xử lý CORS của reactive HandlerMapping.

Nguyên tắc vẫn là **preflight được xử lý trước authentication**. Nhưng không chép loại bean của Servlet MVC vào WebFlux và cho rằng chạy được. Đặc biệt khi project chứa cả web và webflux starters, cần kiểm application thực sự được Boot cấu hình là Servlet hay Reactive; thường Spring MVC được chọn theo mặc định nếu cả hai có mặt.

Ví dụ cấu hình reactive chỉ để nhận biết API, không phải chương trình chạy độc lập:

~~~java
package com.example.reactivecors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class ReactiveCorsSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .cors(Customizer.withDefaults())
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(List.of("Authorization", "X-Request-Id"));
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Đây là cấu hình cho một project WebFlux riêng đã có Spring Boot main class và dependency reactive security. Tùy phiên bản Spring Security, thứ tự và cách tích hợp nhiều SecurityWebFilterChain phải được kiểm thử như Servlet case.

## 14. Chẩn đoán theo thứ tự request thực tế

Để xác định đúng lỗi trong DevTools Network:

1. Xem **Request URL** có thật cross-origin không; kiểm scheme, host, port và proxy.
2. Tìm request **OPTIONS**, xem Origin, Access-Control-Request-Method, Access-Control-Request-Headers.
3. Kiểm status của OPTIONS. Nếu **401/302**, nghi authentication/gateway chạy trước CORS. Nếu **403**, nghi policy origin/method/header hoặc WAF.
4. Kiểm **Access-Control-Allow-Origin/Methods/Headers** và credentials header; chỉ 200 không đủ.
5. Xem browser có phát **actual request** sau preflight không.
6. Nếu đã có actual, xem status 200/401/403/404/500 và nguyên nhân ở authentication, authorization, CSRF hoặc business logic.
7. Nếu curl tới app local đúng nhưng public domain sai, xác định layer proxy/CDN/ingress đang biến đổi request/response.
8. Nếu request không có preflight dù có custom header, cân nhắc browser preflight cache hoặc dev proxy đã đưa request về same-origin.
9. Không dựa riêng vào thông báo chung **TypeError: Failed to fetch**; còn có các lỗi mạng, TLS, mixed content, CSP, DNS hoặc proxy.
10. Quan sát logs an toàn: ghi request ID, Origin, method/path/status; **không log raw token, password hoặc cookie phiên**.

### Ma trận lỗi

| Kết quả quan sát | Diễn giải khả dĩ | Hành động |
| --- | --- | --- |
| OPTIONS 401 | Authentication chạy trước CORS hoặc auth proxy chặn | Tích hợp CorsFilter trước auth, hoặc cấu hình edge xử lý preflight. |
| OPTIONS 302 tới login | Authentication entry point muốn redirect OPTIONS | Đừng bắt browser đăng nhập qua OPTIONS; xử lý CORS sớm. |
| OPTIONS 403 Invalid CORS request | Origin/method/header/path không thuộc policy | So allowlist và Access-Control-Request-*; không mở quyền mù quáng. |
| OPTIONS 200 nhưng thiếu Allow-Origin | OPTIONS được permit nhưng không qua CORS processor | Cấu hình nguồn CORS + filter hoặc edge đúng. |
| OPTIONS 204 hợp lệ từ ingress, app không thấy | Edge chủ động xử lý preflight | Kiểm policy edge, actual request và headers. |
| OPTIONS PASS, actual 401 | Người gọi thiếu credential | Sửa authentication trên actual request, không đụng CORS. |
| OPTIONS PASS, actual 403 | Authorization/CSRF/CORS actual check | Đọc security log và phân biệt nguồn 403. |
| curl GET 200, browser bị chặn | Curl không áp dụng browser CORS | Dùng browser/OPTIONS với Origin thật và credentials mode. |
| Domain public lỗi, localhost đúng | Proxy/ingress/CDN/auth gateway thay đổi luồng | So response header theo từng hop và route. |
| Cookie không đến API | SameSite/Secure/Domain/Path/credentials/browser policy | Kiểm cookie DevTools; không ép preflight mang cookie. |

## 15. Checklist production

- [ ] Xác định chính xác frontend **scheme + host + port** và những origin được tin cậy.
- [ ] Phân biệt **simple request** với request preflight do method/header/Content-Type.
- [ ] Đảm bảo CORS processing chạy trước authentication ở hop được giao trách nhiệm.
- [ ] Với Spring Security Servlet, bật **http.cors(...)** và dùng **CorsConfigurationSource** hoặc MVC CORS config tương thích.
- [ ] Không thay CORS bằng quy tắc **OPTIONS permitAll** đơn thuần.
- [ ] Tách preflight permission khỏi **authentication/authorization/CSRF** của actual request.
- [ ] Đặt allowedOrigins, allowedMethods, allowedHeaders theo quyền tối thiểu; không phản chiếu Origin bất kỳ.
- [ ] Không dùng wildcard Allow-Origin với Allow-Credentials true.
- [ ] Kiểm preflight không credential vẫn PASS; actual thiếu credential vẫn FAIL.
- [ ] Kiểm origin/method/header sai thực sự bị từ chối.
- [ ] Quan sát Access-Control-Allow-*, Vary và Max-Age qua HTTP thật.
- [ ] Kiểm API gateway/WAF/CDN/ingress không redirect hoặc block OPTIONS trước CORS.
- [ ] Đảm bảo actual 401/403 responses có CORS headers phù hợp để frontend xử lý.
- [ ] Kiểm browser credentials mode, cookie rules và không dùng fetch no-cors để né policy.
- [ ] Test multi-chain security/filter order, reverse proxy path mapping, CSRF trên state-changing methods.
- [ ] Không log bearer tokens, Basic credentials, session IDs hoặc CSRF tokens khi debug.

## 16. Tự kiểm tra kiến thức

**1. Vì sao browser phát OPTIONS trước GET có Authorization?**  
Authorization là header không thuộc CORS safelist. Browser hỏi server cho phép origin, method và header name trước khi gửi GET thực tế.

**2. Trong preflight, Access-Control-Request-Method: GET nghĩa là gì?**  
GET là method dự định của actual request; method đang gửi vẫn là OPTIONS.

**3. Vì sao không nên yêu cầu JSESSIONID cho preflight?**  
Browser preflight thường không mang cookie phiên; xác thực diễn ra trên actual request sau khi CORS chấp nhận.

**4. Preflight 200 và actual GET 401 có mâu thuẫn?**  
Không. CORS permission không cấp quyền đọc profile; authentication vẫn được kiểm tra.

**5. Chỉ permit OPTIONS có đủ để browser gửi actual request?**  
Không. Response còn phải có các Access-Control-Allow-* headers hợp lệ.

**6. Vì sao GET có thể preflight nhưng POST đôi khi không?**  
GET có custom header/Authorization có thể preflight; POST simple dùng Content-Type safelisted và không có header ngoài safelist có thể không preflight.

**7. Có thể bật Access-Control-Allow-Origin: * với Allow-Credentials: true không?**  
Không phù hợp cho credentialed browser requests; dùng origin cụ thể hoặc policy pattern được kiểm soát.

**8. CORS có thay thế CSRF protection không?**  
Không. Simple requests vẫn có thể được gửi; khi credentials tự động đi kèm, phải bảo vệ các state-changing operations.

**9. Nếu Spring trả OPTIONS 200 ở localhost nhưng public domain trả 401?**  
Kiểm CDN/WAF/API gateway/ingress/auth proxy và policy của mỗi hop trước khi sửa code app.

**10. Tại sao curl -u không tự gửi OPTIONS?**  
Curl không thực thi browser CORS preflight protocol; phải tạo OPTIONS riêng để test.

**11. Vai trò của Vary: Origin là gì?**  
Giúp shared cache phân biệt response phụ thuộc Origin, giảm nguy cơ phát sai CORS permission giữa các nguồn.

**12. Khi nào cần CorsWebFilter thay vì CorsFilter?**  
Khi dùng Spring WebFlux reactive stack, không phải Servlet MVC.

## 17. Nguồn tài liệu

- **Spring Security – Servlet CORS:** https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html (CORS trước authentication, CorsFilter, UrlBasedCorsConfigurationSource).
- **Spring Framework – MVC CORS:** https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html (preflight/simple/actual, credentials, @CrossOrigin, CorsConfiguration).
- **Spring Security – CSRF:** https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html (phân biệt CORS và CSRF protection).
- **Spring Boot – Servlet Web Applications:** https://docs.spring.io/spring-boot/reference/web/servlet.html (Servlet web stack).
- **MDN – CORS:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- **MDN – Preflight request:** https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request
- **MDN – Access-Control-Allow-Headers:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers
- **WHATWG Fetch Standard:** https://fetch.spec.whatwg.org/ (CORS-preflight, credentials mode, safelisted methods/headers).
