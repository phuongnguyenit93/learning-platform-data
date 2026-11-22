# Giới hạn đường dẫn, HTTP method và kiểu nội dung của endpoint đăng nhập trong Spring Security Servlet

## 1. Bối cảnh và mục tiêu

Khi tự xây dựng một endpoint đăng nhập, ví dụ **POST /api/login** nhận JSON, chúng ta không chỉ cần kiểm tra username/password. Ta còn phải quyết định **request nào thực sự được phép kích hoạt quá trình xác thực**. Một filter đăng nhập được viết quá rộng có thể xử lý nhầm URL, chấp nhận GET hoặc PUT, cố parse HTML/form như JSON, bỏ qua CSRF, hoặc xử lý nhiều lần khi Spring Security và Servlet container cùng đăng ký filter.

Vì vậy, một endpoint đăng nhập tùy chỉnh phải được thiết kế theo ít nhất ba ranh giới:

1. **Đường dẫn (path):** chỉ **/api/login**; không tự động nhận mọi URL bắt đầu bằng /api/login, không nhận /api/login/other.
2. **HTTP method:** chỉ **POST**, vì login gửi bí mật và làm thay đổi trạng thái xác thực. GET, HEAD, PUT, DELETE, PATCH không được âm thầm thực hiện login.
3. **Kiểu nội dung (Content-Type):** chỉ JSON theo contract, ví dụ **application/json** hoặc **application/json;charset=UTF-8**; form data, text/plain, XML và nội dung không xác định bị từ chối trước bước đọc credentials.

Ngoài ba điều kiện đó còn có **giới hạn kích thước body, validate cấu trúc, xử lý sai credentials, CSRF/session fixation, tránh ghi log bí mật và phân quyền cho endpoint sau login**.

Bài này hướng dẫn sự khác nhau giữa request matcher và xác thực, cách trả mã 400/401/403/405/413/415 có ý nghĩa, rồi cung cấp một dự án **Java 17+ / Spring Boot 3.3.13 / Spring Security 6** sử dụng Servlet SecurityFilterChain và custom OncePerRequestFilter. Có ví dụ curl và MockMvc để chứng minh đường dẫn, method và Content-Type được kiểm soát.

**Phạm vi:** ứng dụng **Spring Security Servlet**. Với WebFlux, cấu hình SecurityWebFilterChain, request API và cách quản lý context khác; không sao chép nguyên mã Servlet ở đây.

## 2. Đăng nhập là một endpoint có hợp đồng HTTP

Giả sử API công bố hợp đồng:

~~~http
POST /api/login HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token-from-current-session>
Cookie: JSESSIONID=<session-cookie>

{"username":"learner","password":"learner-pass"}
~~~

Hai giá trị trong ngoặc nhọn ở phần header là **mô tả vị trí dữ liệu được cấp động**, không phải header literal có thể gửi nguyên văn. Trong ví dụ thực hành có lệnh lấy token và cookie qua endpoint /csrf trước khi POST.

Hệ thống chỉ nên cho phép:

| Yếu tố | Chấp nhận | Từ chối hoặc không coi là login |
| --- | --- | --- |
| Path | /api/login đúng path của Servlet app | /api/login/extra, /api/login-debug, /other |
| Method | POST | GET, HEAD, PUT, PATCH, DELETE, OPTIONS nếu không có contract riêng |
| Content-Type | application/json, có thể kèm charset=UTF-8 | text/plain, application/x-www-form-urlencoded, multipart/form-data, application/xml, thiếu Content-Type |
| Body | JSON object có hai chuỗi username và password hợp lệ về hình dạng | JSON sai cú pháp, array, thiếu thuộc tính, giá trị không phải chuỗi |
| Body size | Nằm dưới ngưỡng công bố | Payload quá lớn |
| Credentials | Được AuthenticationManager xác minh | Username/password sai, user bị khóa/hết hạn theo policy |
| CSRF đối với session browser | Token hợp lệ theo cơ chế đang dùng | Thiếu hoặc sai token |

**Quan trọng:** kiểm soát HTTP contract **không đồng nghĩa** đã xác thực thành công. Request POST đúng path và Content-Type vẫn có thể mang password sai, dẫn tới **401**. Request JSON hợp lệ có thể bị **403** trước khi tới filter login nếu thiếu CSRF token.

### Tại sao phải tách ba ranh giới?

- **Path** xác định tính năng nào xử lý request. Nếu filter áp cho mọi /api/**, token/password có thể bị đọc nhầm ở endpoint khác.
- **Method** xác định thao tác. GET phải không có tác dụng phụ đăng nhập, không gửi password trong URL query string.
- **Content-Type** khai báo kiểu biểu diễn **request body**. Nó giúp chọn parser và từ chối các format mà API không hỗ trợ.
- **Body validation** đảm bảo dữ liệu **bên trong** JSON có đúng cấu trúc; Content-Type application/json tự nó không bảo đảm body là JSON hợp lệ.
- **CSRF** là bảo vệ riêng khi browser có cơ chế tự gửi cookie/credentials; nó có thể kiểm tra trước filter login.
- **Authorization sau login** là kiểm soát quyền truy cập tài nguyên, không thể thay thế bằng việc chỉ validate method login.

## 3. Phân biệt đường dẫn request với query string và context path

Một URL có thể gồm scheme, host, context path, servlet path, path info và query string. Khi dùng request matcher của Spring Security Servlet, cần hiểu path được matcher quan sát trong cấu hình triển khai cụ thể.

Ví dụ app chạy ở root context:

~~~text
http://localhost:8080/api/login?source=web
                      ^^^^^^^^^^  ^^^^^^^^^^
                      path        query string
~~~

Thông thường matcher cho **/api/login** kiểm tra phần path, **không coi query string là một thành phần tên path**. Do đó **POST /api/login?source=web** vẫn có thể đi vào filter login, trong khi **POST /api/login/extra** không được coi là login nếu matcher là exact path.

Nếu app được triển khai dưới context path **/shop**, request URL là **/shop/api/login** nhưng matcher Spring Security có thể làm việc với path **/api/login** bên trong ứng dụng. Đừng viết code so sánh toàn bộ URL tuyệt đối với chuỗi cố định chứa hostname, port hoặc query string.

Với Spring Security 6, có thể sử dụng RequestMatcher phù hợp với cấu hình path/method; **AntPathRequestMatcher** được dùng trong bài vì tương thích với Spring Security 6 của phiên bản minh họa. Ở các phiên bản Spring Security mới hơn, API matcher được khuyến nghị có thể thay đổi; lựa chọn cho dự án thực tế cần khớp phiên bản.

### Exact path khác pattern rộng

| Matcher/ý định | Ví dụ được nhận | Nguy cơ |
| --- | --- | --- |
| /api/login (exact) | /api/login | Phạm vi hẹp, phù hợp login |
| /api/login/** | Có thể bao gồm /api/login/other | Quá rộng nếu chỉ có một endpoint |
| /api/** | Nhiều endpoint API | Có thể đọc nhầm requests không phải login |
| /** | Hầu hết request | Không phù hợp với login filter thông thường |

**Quy tắc tốt:** filter có thể được đăng ký trong SecurityFilterChain, nhưng logic nhận diện **endpoint login** phải có matcher hẹp. Đừng dựa vào tên class hoặc việc controller nằm dưới /api để suy ra filter chỉ xử lý đúng URL.

### Có nhiều SecurityFilterChain?

Nếu ứng dụng có nhiều chain được khai bằng **securityMatcher(...)** và thứ tự **@Order**, request chỉ đi qua **chain đầu tiên khớp**. Đặt custom login filter trong chain **không khớp /api/login** sẽ khiến filter không được gọi, dù code matcher nội bộ đúng. Ngược lại, một chain API có matcher quá rộng có thể nhận request trước chain khác dự kiến xử lý login.

Hãy xác minh cả **chain-level matcher** lẫn **login filter matcher**; chúng là hai lớp chọn lọc khác nhau.

## 4. HTTP method: chỉ cho POST vào luồng xác thực

### Vì sao không GET?

GET được thiết kế cho đọc tài nguyên, có thể bị prefetch, cache, thu thập trong lịch sử hay được crawler gọi. Đặt username/password trong query string, ví dụ **GET /api/login?password=...**, dễ làm lộ bí mật qua URL log, history và đường truyền. Một login thành công còn có thể thiết lập SecurityContext/session nên **không nên** là tác dụng phụ của GET.

**POST** phù hợp hơn để gửi request body chứa credentials và diễn đạt hành động đăng nhập. Tuy nhiên POST **không tự cung cấp bảo mật**: vẫn cần HTTPS, CSRF khi thích hợp, validate dữ liệu, bảo vệ brute force và quản lý session.

### 405 Method Not Allowed và Allow header

Nếu **/api/login** tồn tại nhưng không cho GET:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: POST
Content-Type: application/json

{"error":"method_not_allowed"}
~~~

**405** biểu thị method không được hỗ trợ trên tài nguyên đó; response nên có **Allow** liệt kê method được hỗ trợ. Trong ứng dụng có xử lý OPTIONS/CORS riêng, hành vi có thể khác theo chính sách. Đừng chuyển GET thành POST hoặc xác thực dù method bị cấm.

**HEAD và OPTIONS:** HEAD có đặc tính liên hệ với GET nhưng không nên kích hoạt login. OPTIONS có thể dùng cho CORS preflight hoặc discovery; trong ví dụ đơn giản, filter login không coi nó là yêu cầu đăng nhập. Khi có CORS, nên để phần CORS xử lý OPTIONS đúng chính sách, tránh trả 405 bừa bãi cho preflight cần thiết của frontend.

### Chỉ cấu hình requestMatchers(POST, "/api/login") đã đủ chưa?

Chưa chắc. Cấu hình:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
    .anyRequest().authenticated()
);
~~~

chỉ khai báo **quy tắc authorization** cho một lớp request. Nó không nhất thiết quyết định **custom filter** có chạy trên GET hay không, cũng không tự trả 405 với Allow. Một filter viết không có matcher method vẫn có thể cố xử lý GET trước khi AuthorizationFilter đến lượt.

**Phải bảo vệ tại nơi thật sự đọc credentials**: filter/controller login cần kiểm tra method và ngừng xử lý nếu sai. Authorization rule và authentication filter nên nhất quán, nhưng không thay thế nhau.

## 5. Content-Type: giới hạn định dạng request body

### Content-Type không phải Accept

| Header | Bên khai báo | Dùng để làm gì |
| --- | --- | --- |
| **Content-Type: application/json** | Client | Body gửi lên là JSON |
| **Accept: application/json** | Client | Client muốn nhận response dạng JSON |
| **Content-Type: application/json** trên response | Server | Response body được biểu diễn bằng JSON |

Client có thể gửi:

~~~http
POST /api/login HTTP/1.1
Content-Type: text/plain
Accept: application/json

{"username":"learner","password":"learner-pass"}
~~~

Dù body trông giống JSON và Accept là application/json, **request Content-Type vẫn là text/plain**, không đúng hợp đồng. Endpoint giới hạn JSON nên trả **415 Unsupported Media Type** thay vì tự đoán body rồi xác thực.

Ví dụ lỗi:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/json

{"error":"unsupported_media_type"}
~~~

**Content-Type có thể có tham số**, ví dụ **application/json;charset=UTF-8**. Không so sánh bằng equals("application/json") trên raw header vì như vậy sẽ loại sai request JSON hợp lệ có tham số.

Trong Spring Framework, dùng **MediaType.parseMediaType(...)** để parse và **MediaType.APPLICATION_JSON.isCompatibleWith(actual)** để kiểm tra tương thích. Nếu cần chính sách chặt, kiểm tra charset, giới hạn kiểu vendor và phần thân riêng. Bài thực hành chấp nhận **application/json** (có hoặc không có khai báo **charset=UTF-8**) và từ chối charset được khai khác UTF-8.

### application/*+json thì sao?

Một số API dùng media type có suffix **+json**, như **application/problem+json** hoặc **application/vnd.company+json**. Chúng không tự nhiên nằm trong contract chỉ chấp nhận **application/json** của ví dụ. Nếu API muốn hỗ trợ, hãy **công bố rõ allowlist** và test các kiểu được nhận; không nới mở vô điều kiện chỉ vì một chuỗi chứa chữ json.

### JSON hợp lệ chưa chắc đúng schema

Ví dụ cùng có Content-Type application/json nhưng không nên được chấp nhận:

~~~json
["learner","learner-pass"]
~~~

~~~json
{"username":"learner"}
~~~

~~~json
{"username":"learner","password":123}
~~~

~~~json
{"username":"learner","password":"learner-pass","isAdmin":true}
~~~

Một login endpoint có contract hai trường chuỗi nên từ chối JSON array, thiếu password, password kiểu number hoặc trường thừa nếu chủ đích schema nghiêm ngặt. Trong ví dụ sẽ có kiểm tra **JsonNode.isObject**, **root.size() == 2**, kiểu chuỗi, độ dài và giá trị không rỗng.

**400 Bad Request** là mã phù hợp khi media type đã đúng nhưng cú pháp/cấu trúc JSON không hợp lệ. **415** là vấn đề kiểu media không được hỗ trợ. Đừng gộp tất cả lỗi thành 401, vì 401 dành cho **xác thực credentials thất bại**.

## 6. Trình tự xử lý: giới hạn hình thức rồi mới xác thực

Một luồng JSON login chủ đích có thứ tự:

~~~text
HTTP request
  |
  v
SecurityFilterChain đúng request
  |
  v
CsrfFilter kiểm tra token nếu request cần CSRF
  |               \
  |                +-- sai/thiếu --> 403, login filter chưa chạy
  v
Custom login filter
  |
  +-- path không phải /api/login --> chuyển filter chain tiếp
  |
  +-- path đúng, method != POST --> 405 + Allow: POST
  |
  +-- POST, Content-Type không được hỗ trợ --> 415
  |
  +-- POST + JSON, body quá lớn --> 413
  |
  +-- POST + JSON, cú pháp/schema sai --> 400
  |
  v
AuthenticationManager.authenticate(...)
  |
  +-- AuthenticationException --> 401 (lỗi chung, không lộ account)
  |
  +-- thành công
          |
          +-- session fixation / CSRF authentication strategy
          +-- tạo SecurityContext chứa Authentication
          +-- SecurityContextRepository.saveContext trước response commit
          |
          v
        HTTP 200 + JSON không chứa password
~~~

**Một lưu ý về thứ tự:** nếu CSRF bật và token thiếu, request POST có thể bị **403 trước khi** custom filter kiểm tra Content-Type hoặc body. Đây không phải lỗi của parser; nó là quyết định của filter bảo mật chạy trước. Khi test riêng 415, 400 hoặc 413, phải dùng **CSRF token hợp lệ** nếu hệ thống yêu cầu.

Với hệ thống API hoàn toàn không dùng cookie hay bất kỳ credentials tự gửi bởi browser, chính sách CSRF có thể khác. Nhưng không được tắt CSRF chỉ vì “endpoint là JSON” hoặc “session policy là STATELESS”; cần phân tích cơ chế client gửi credentials, CORS, cookies và threat model.

## 7. Chọn lớp mở rộng: controller, AuthenticationFilter hay custom Filter?

Spring Security có nhiều cách xây login. Không cần tạo filter bằng mọi giá.

| Lựa chọn | Phù hợp khi | Điểm cần tự làm |
| --- | --- | --- |
| MVC controller với @PostMapping(consumes="application/json") | Login thật sự là API MVC, muốn hưởng request mapping / 405 / 415 | AuthenticationManager, SecurityContext lưu tường minh, session protection, CSRF và success/failure |
| AuthenticationFilter với AuthenticationConverter, RequestMatcher | Muốn dùng phần lớn luồng xác thực/hook của Spring Security | Matcher, converter, handlers, SecurityContextRepository và session strategy phù hợp |
| AbstractAuthenticationProcessingFilter tùy biến | Muốn sử dụng hook xử lý success/failure/session của lớp nền | Matcher, attemptAuthentication, các thành phần liên quan |
| OncePerRequestFilter tùy biến | Cần tự minh họa/kiểm soát HTTP contract trong SecurityFilterChain | Tự quản lý **toàn bộ** response, xác thực, lưu context và session strategies |

Bài này dùng **OncePerRequestFilter** để mọi ranh giới path/method/media/body hiển thị tường minh trong mã. Với sản phẩm thực tế, thường nên ưu tiên **controller với consumes đúng** hoặc một filter xác thực chuẩn có extension point phù hợp để giảm lượng code bảo mật phải tự duy trì.

### Controller consumes có làm HTTP contract dễ hơn?

Một ví dụ rút gọn về MVC routing:

~~~java
// Fragment minh họa trong @RestController đã có loginService.
@PostMapping(path = "/api/login", consumes = "application/json",
             produces = "application/json")
public LoginResponse login(@RequestBody LoginRequest body) {
    return loginService.login(body);
}
~~~

Controller có thể được Spring MVC chọn theo path, method và consumes; MediaType không phù hợp thường trả 415, method không hỗ trợ thường trả 405. Đây **chỉ là fragment**, không có định nghĩa LoginResponse/LoginRequest/loginService và không tự thực hiện session/CSRF/security, nên không được coi là chương trình biên dịch độc lập. **Filter chạy trước MVC**; nếu có login filter tự ý xử lý mọi request, annotation consumes trên controller **không bảo vệ được filter đó**.

## 8. Project Spring Boot hoàn chỉnh: JSON login exact path + POST + application/json

### 8.1. Quy tắc và môi trường

Dùng Java 17+, Maven, Spring Boot **3.3.13** (Spring Security 6), Spring Web và Spring Security.

Demo chỉ chấp nhận:

- **POST /api/login**, Content-Type **application/json** với UTF-8.
- Body JSON object có đúng **username** và **password** kiểu String.
- Kích thước body không quá **4096 byte**.
- Dữ liệu ví dụ: **learner / learner-pass** có ROLE_USER; **admin / admin-pass** có ROLE_ADMIN.
- **GET /csrf** trả CSRF token cho session browser trước khi POST.
- **GET /me** yêu cầu user đã đăng nhập; **GET /admin** yêu cầu ROLE_ADMIN.

Demo dùng **HttpSessionSecurityContextRepository** để giữ login qua request. CSRF **được bật**, vì browser gửi session cookie tự động. Sau login thành công, ví dụ có session fixation strategy và làm mới CSRF token cho session; request đổi trạng thái tiếp theo phải lấy token mới khi cần. Không tạo endpoint HTTP nào để trả password hash, session ID hoặc raw password.

### 8.2. Cây dự án

~~~text
restricted-login-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/restrictedlogin/
    │   ├── RestrictedLoginApplication.java
    │   ├── SecurityConfig.java
    │   ├── JsonLoginFilter.java
    │   └── DemoController.java
    └── test/java/com/example/restrictedlogin/
        └── RestrictedLoginTest.java
~~~

### 8.3. pom.xml

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
    <artifactId>restricted-login-demo</artifactId>
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

### 8.4. RestrictedLoginApplication.java

~~~java
package com.example.restrictedlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RestrictedLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(RestrictedLoginApplication.class, args);
    }
}
~~~

Các class nằm chung package com.example.restrictedlogin để Spring Boot tìm thấy cấu hình và controller.

### 8.5. JsonLoginFilter.java

Filter sau chỉ xử lý đúng **/api/login**. Nếu path khác, nó gọi filterChain.doFilter để các endpoint khác tiếp tục. Nếu path đúng nhưng method không phải POST, nó trả 405. Với POST, nó kiểm tra Content-Type, body size, UTF-8 và schema JSON **trước khi gọi AuthenticationManager**.

~~~java
package com.example.restrictedlogin;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

public final class JsonLoginFilter extends OncePerRequestFilter {

    private static final int MAX_BODY_BYTES = 4096;
    private static final RequestMatcher LOGIN_PATH =
        new AntPathRequestMatcher("/api/login");

    private final AuthenticationManager manager;
    private final ObjectMapper mapper;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    public JsonLoginFilter(
            AuthenticationManager manager,
            ObjectMapper mapper,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {

        this.manager = manager;
        this.mapper = mapper;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // 1. Chỉ nhận đúng path login. Không động vào request khác.
        if (!LOGIN_PATH.matches(request)) {
            chain.doFilter(request, response);
            return;
        }

        // 2. Chỉ POST mới có quyền thực hiện authentication.
        if (!"POST".equals(request.getMethod())) {
            response.setHeader("Allow", "POST");
            sendJson(response, 405, Map.of("error", "method_not_allowed"));
            return;
        }

        // 3. Content-Type thuộc allowlist JSON, charset UTF-8 nếu khai báo.
        String rawType = request.getContentType();
        if (rawType == null) {
            sendJson(response, 415, Map.of("error", "unsupported_media_type"));
            return;
        }

        MediaType actual;
        try {
            actual = MediaType.parseMediaType(rawType);
        } catch (IllegalArgumentException ex) {
            sendJson(response, 415, Map.of("error", "unsupported_media_type"));
            return;
        }

        if (!MediaType.APPLICATION_JSON.isCompatibleWith(actual)
                || (actual.getCharset() != null
                    && !StandardCharsets.UTF_8.equals(actual.getCharset()))) {

            sendJson(response, 415, Map.of("error", "unsupported_media_type"));
            return;
        }

        // 4. Đọc tối đa 4097 byte để phát hiện body vượt 4096 byte.
        byte[] body = request.getInputStream().readNBytes(MAX_BODY_BYTES + 1);
        if (body.length > MAX_BODY_BYTES) {
            sendJson(response, 413, Map.of("error", "payload_too_large"));
            return;
        }

        // 5. Từ chối byte không phải UTF-8 hợp lệ.
        String json;
        try {
            json = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(body))
                .toString();
        } catch (CharacterCodingException ex) {
            sendJson(response, 400, Map.of("error", "invalid_json"));
            return;
        }

        // 6. Parse JSON và không cho phép nội dung JSON thừa phía sau.
        JsonNode root;
        try {
            root = mapper.readerFor(JsonNode.class)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .readValue(json);
        } catch (JsonProcessingException ex) {
            sendJson(response, 400, Map.of("error", "invalid_json"));
            return;
        }

        // 7. Chỉ object gồm đúng hai thuộc tính chuỗi.
        if (root == null || !root.isObject() || root.size() != 2
                || root.get("username") == null
                || root.get("password") == null
                || !root.get("username").isTextual()
                || !root.get("password").isTextual()) {

            sendJson(response, 400, Map.of("error", "invalid_login_body"));
            return;
        }

        String username = root.get("username").asText();
        String password = root.get("password").asText();

        if (username.isBlank() || username.length() > 100
                || password.isBlank() || password.length() > 256) {

            sendJson(response, 400, Map.of("error", "invalid_login_body"));
            return;
        }

        // 8. Chỉ bây giờ mới yêu cầu kiểm tra credentials.
        try {
            Authentication verified = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    username, password));

            // Tích hợp chính sách session của login tùy chỉnh.
            sessionStrategy.onAuthentication(verified, request, response);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(verified);
            SecurityContextHolder.setContext(context);

            // Spring Security 6: muốn request sau dùng session phải save.
            repository.saveContext(context, request, response);

            // Không trả lại raw password hoặc password hash.
            sendJson(response, 200, Map.of(
                "username", verified.getName(),
                "authenticated", true));

        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            // Thông báo chung, không tiết lộ username có tồn tại hay không.
            sendJson(response, 401, Map.of("error", "invalid_credentials"));
        }
    }

    private void sendJson(
            HttpServletResponse response,
            int status,
            Map<String, ?> body) throws IOException {

        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

**Các điểm quan trọng trong filter:**

1. **new AntPathRequestMatcher("/api/login")** dùng để nhận diện đường dẫn của endpoint, không chọn /** hoặc /api/**.
2. Phân nhánh method nằm **sau khi path trùng**: GET/PUT đến /api/login sẽ bị 405 với Allow: POST. Request path khác được chuyển tiếp, không bị filter nhận nhầm.
3. **MediaType.parseMediaType** nhận được application/json có tham số charset, không dùng so sánh raw header bằng chuỗi đơn giản. Chỉ cho UTF-8 và JSON đúng allowlist.
4. **readNBytes(4097)** giới hạn lượng body thực sự đọc trong filter, không chỉ tin vào Content-Length do client khai báo. Khi body vượt ngưỡng, trả 413 trước parse.
5. **CharsetDecoder** báo lỗi nếu body không phải UTF-8 hợp lệ. JsonNode/strict reader xử lý cú pháp JSON; schema kiểm tra hai field có kiểu String.
6. **AuthenticationManager** mới là nơi xác minh username/password qua provider. Không tự viết so sánh password bằng equals.
7. **SessionAuthenticationStrategy** và **SecurityContextRepository** phải được sử dụng đúng vì đây là login custom, không đi qua UsernamePasswordAuthenticationFilter của formLogin mặc định.
8. **401** chỉ áp cho AuthenticationException ở bước kiểm tra credentials; các lỗi method/media/body được trả status riêng. Đây là lựa chọn API contract của demo, không phải quy tắc rằng mọi ứng dụng buộc trả chính xác body lỗi này.
9. **sendJson** đặt Content-Type JSON cho response, không nhầm với Content-Type client gửi.
10. **JsonLoginFilter không được đánh dấu @Component hoặc @Bean** trong demo; nó sẽ được thêm đúng **một lần** vào SecurityFilterChain. Nếu vừa tự động đăng ký Servlet filter vừa addFilterBefore, có nguy cơ filter chạy hai lần.

**Giới hạn của ví dụ:** kiểm tra JSON object có hai field và FAIL_ON_TRAILING_TOKENS không mặc nhiên từ chối mọi JSON duplicate-key. Với production có schema nghiêm ngặt, có thể bật cơ chế duplicate detection của Jackson và thiết kế lỗi input rõ ràng. Ví dụ không triển khai rate limiting, audit, lockout, CORS, captcha, MFA hay kiểm soát tài khoản phân tán; những yêu cầu đó cần bổ sung theo threat model.

### 8.6. SecurityConfig.java

~~~java
package com.example.restrictedlogin;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ObjectMapper mapper,
            UserDetailsService users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(provider);

        SecurityContextRepository contextRepository =
            new HttpSessionSecurityContextRepository();

        CsrfTokenRepository csrfRepository =
            new HttpSessionCsrfTokenRepository();

        SessionAuthenticationStrategy sessionStrategy =
            new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)
            ));

        JsonLoginFilter loginFilter = new JsonLoginFilter(
            manager, mapper, contextRepository, sessionStrategy);

        http
            .securityContext(context ->
                context.securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                .requestMatchers("/api/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .exceptionHandling(exception -> exception
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                loginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Đọc cấu hình theo mục tiêu:**

- **DaoAuthenticationProvider** kiểm tra credentials với UserDetailsService và BCryptPasswordEncoder, không đưa raw password vào database.
- **ProviderManager** là AuthenticationManager mà custom login filter trực tiếp sử dụng.
- **HttpSessionSecurityContextRepository** được gắn ở cả filter login (save) lẫn phần securityContext của chain (load). Nếu lưu một nơi nhưng chain tải nơi khác, request sau có thể mất login.
- **CsrfTokenRepository** dùng HttpSession; login POST sẽ qua **CsrfFilter** trước custom filter. Ví dụ không disable CSRF.
- **CompositeSessionAuthenticationStrategy** gọi đổi session ID khi thích hợp để giảm session fixation và làm mới CSRF token sau xác thực. Custom filter phải chủ động gọi sessionStrategy.onAuthentication(...).
- **IF_REQUIRED** cho phép session tồn tại khi cần; demo chủ đích là session login chứ không phải token API stateless.
- **requestMatchers("/api/login").permitAll()** cho phép request đi tới login filter dù chưa authenticated, nhưng **không tự mở mọi method/media type**. Các giới hạn đó được filter áp dụng.
- **/me** chỉ cần authenticated; **/admin** cần ROLE_ADMIN. **anyRequest().denyAll()** giảm nguy cơ endpoint mới vô tình công khai.
- **HttpStatusEntryPoint(401)** trả status khi request chưa đăng nhập tới URL được bảo vệ, không tự redirect đến form login. Không dùng Basic challenge vì demo không bật httpBasic.
- **formLogin/httpBasic disabled** tránh cơ chế login khác nhận nhầm credentials trong bài thực hành.
- **addFilterBefore** thêm filter login trước vị trí UsernamePasswordAuthenticationFilter trong thứ tự của chain. Đây là vị trí anchor trong Spring Security; không phải lời khẳng định formLogin filter đang được bật.
- Filter được tạo trong phương thức cấu hình, **không** khai báo @Bean hay @Component, để tránh Servlet container tự đăng ký nó lần thứ hai.

**Lưu ý session fixation:** chiến lược đổi session ID chỉ có ý nghĩa khi có session phù hợp; trong ví dụ GET /csrf tạo session trước login. Production có thể cần thêm giới hạn concurrent sessions, session invalidation, remember-me, audit, MFA và các quy định riêng; đừng hiểu CompositeSessionAuthenticationStrategy mẫu là bao phủ mọi trường hợp đăng nhập.

### 8.7. DemoController.java

~~~java
package com.example.restrictedlogin;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/csrf")
    public Map<String, String> csrf(
            @RequestAttribute("_csrf") CsrfToken token) {

        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken());
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

**/csrf** là endpoint hỗ trợ minh họa CSRF session: đọc token Spring Security đặt vào request attribute và trả token cho client có cùng session. Việc truy cập token có thể kích hoạt tạo/lưu token qua deferred CSRF token mechanism. Đối với frontend production, cần xem mô hình cookie/header và không mở CORS bừa bãi để website không tin cậy có thể đọc token.

**/me** đọc Authentication đã xác thực từ context. Không nhận raw username/password và không cố tự gọi PasswordEncoder. **/admin** được bảo vệ bởi rule có ROLE_ADMIN.

Đây là ví dụ login session; nếu cần API không session dùng bearer token, hãy thiết kế OAuth2 Resource Server/token issuance theo mô hình riêng thay vì đổi IF_REQUIRED thành STATELESS và hy vọng saveContext vẫn hoạt động qua request.

## 9. Thử HTTP end-to-end bằng curl

Khởi động từ thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Ví dụ dùng địa chỉ http://localhost:8080 chỉ **trên máy phát triển**. Với credentials thật hoặc qua Internet phải dùng **HTTPS**. Các lệnh shell sau dùng cú pháp bash và công cụ **jq** để đọc JSON; trên PowerShell có thể dùng curl.exe và ConvertFrom-Json hoặc thực hiện bằng Postman/HTTP client tương đương.

### 9.1. Lấy CSRF token và cookie cho session

~~~bash
TOKEN=$(curl -sS -c cookies.txt http://localhost:8080/csrf | jq -r '.token')
~~~

Lệnh GET /csrf có thể khiến server tạo session; **cookies.txt** ghi cookie tham chiếu session để POST tiếp theo gửi về cùng session. TOKEN là token nhận được trong JSON, không phải password hoặc bearer token cấp quyền API.

### 9.2. POST JSON login đúng contract

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login
~~~

Dự kiến **HTTP 200**, JSON có **username=learner**, **authenticated=true**. Server có thể xoay session ID hoặc cập nhật session cookie. Lệnh dùng cả **-b** và **-c** để đọc và lưu cookie đã đổi, rồi dùng cho request tiếp theo.

### 9.3. Dùng session vừa đăng nhập

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
~~~

Dự kiến **200** với username=learner. Nếu không gửi cookie session, request GET /me chưa đăng nhập thường nhận **401**.

~~~bash
curl -i http://localhost:8080/me
~~~

### 9.4. Sai method trên đúng path

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/login
~~~

Dự kiến **405 Method Not Allowed**, header **Allow: POST**. Custom login filter không biến GET thành một thao tác login.

### 9.5. Sai Content-Type nhưng có CSRF hợp lệ

Để tách riêng lỗi media type, dùng session/token mới từ GET /csrf (token của lần login cũ có thể đã bị làm mới):

~~~bash
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

curl -i -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: text/plain" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login
~~~

Dự kiến **415 Unsupported Media Type**. Dù body trông giống JSON, header text/plain không thỏa contract.

### 9.6. JSON sai cấu trúc

~~~bash
curl -i -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"username":"learner"}' \
  http://localhost:8080/api/login
~~~

Dự kiến **400 Bad Request** vì thiếu trường password. Với JSON sai cú pháp, ví dụ thiếu dấu ngoặc, cũng là lỗi 400. Nếu token CSRF đã hết hiệu lực, server sẽ có thể trả 403 trước khi đến bước validate body; hãy lấy token mới để test đúng nhánh.

### 9.7. JSON đúng nhưng password sai

~~~bash
curl -i -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json;charset=UTF-8" \
  --data '{"username":"learner","password":"wrong-pass"}' \
  http://localhost:8080/api/login
~~~

Nếu CSRF token hợp lệ, dự kiến **401 Unauthorized** với lỗi chung **invalid_credentials**. Không trả thông báo user có tồn tại hay không.

### 9.8. POST thiếu CSRF

~~~bash
curl -i -b cookies.txt \
  -H "Content-Type: application/json" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login
~~~

Dự kiến **403 Forbidden** từ CSRF protection nếu không gửi token. Đó là hành vi bảo mật chủ đích. Không sửa bằng cách disable CSRF toàn bộ khi endpoint dùng session cookie ở trình duyệt.

### 9.9. Đường dẫn gần giống

~~~bash
curl -i -b cookies.txt \
  -H "Content-Type: application/json" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login/extra
~~~

Custom login filter **không nhận đường dẫn này**. Status cuối phụ thuộc các rule authorization/handler của ứng dụng (thường 401 với anonymous hoặc không có route); điều cần chứng minh là không chạy logic login và không lưu session mới. Đừng đoán rằng mọi path không khớp bắt buộc phải trả 404: SecurityFilterChain có thể từ chối trước khi tới MVC.

## 10. Kiểm thử tích hợp MockMvc

Tạo file **src/test/java/com/example/restrictedlogin/RestrictedLoginTest.java**. Test dùng **spring-security-test** để cấp CSRF token hợp lệ bằng **with(csrf())** khi muốn cô lập đúng nhánh method, Content-Type, body hoặc credentials.

~~~java
package com.example.restrictedlogin;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class RestrictedLoginTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID_BODY =
        "{\"username\":\"learner\",\"password\":\"learner-pass\"}";

    @Test
    void onlyExactLoginPathCanAuthenticate() throws Exception {
        mvc.perform(post("/api/login/extra")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_BODY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void getLoginReturns405AndAllowPost() throws Exception {
        mvc.perform(get("/api/login"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string("Allow", "POST"))
            .andExpect(jsonPath("$.error")
                .value("method_not_allowed"));
    }

    @Test
    void wrongContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content(VALID_BODY))
            .andExpect(status().isUnsupportedMediaType())
            .andExpect(jsonPath("$.error")
                .value("unsupported_media_type"));
    }

    @Test
    void invalidJsonBodyReturns400() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"learner\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                .value("invalid_login_body"));
    }

    @Test
    void oversizedBodyReturns413() throws Exception {
        String bigBody = "x".repeat(4097);

        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(bigBody))
            .andExpect(status().isPayloadTooLarge())
            .andExpect(jsonPath("$.error")
                .value("payload_too_large"));
    }

    @Test
    void missingCsrfReturns403BeforeCustomLoginFilter()
            throws Exception {

        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordReturns401() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"learner\","
                    + "\"password\":\"wrong-pass\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error")
                .value("invalid_credentials"));
    }

    @Test
    void validJsonLoginCreatesSessionForNextRequest()
            throws Exception {

        MvcResult login = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_BODY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authenticated").value(true))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());

        // Request mới không mang session đã đăng nhập.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void csrfEndpointReturnsToken() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName")
                .value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isString());
    }
}
~~~

Chạy trong thư mục dự án:

~~~bash
mvn test
~~~

**Điều các test kiểm chứng:**

- Path /api/login/extra **không** được coi là login; với cấu hình denyAll/entry point của demo và user anonymous, nó được từ chối.
- GET đúng path bị **405** với Allow: POST.
- POST Content-Type text/plain bị **415**.
- POST JSON thiếu trường bị **400**.
- Payload vượt 4096 byte bị **413**.
- POST thiếu CSRF bị **403**, trước khi tới login filter.
- POST JSON đúng nhưng password sai bị **401**.
- POST hợp lệ + CSRF hợp lệ tạo SecurityContext lưu trong session; GET /me cùng session thành công, GET /admin của ROLE_USER bị **403**, GET /me không session bị **401**.
- GET /csrf cung cấp token phục vụ client cùng session.

**Lưu ý test path không khớp:** HTTP status cuối cùng xuất phát từ authorization rule của demo, không phải JsonLoginFilter tự trả 401. Để khẳng định filter không gọi AuthenticationManager cho path khác trong hệ thống lớn, có thể thêm mock/spy có kiểm soát hoặc metric về số lần xác thực; không chỉ nhìn status.

### Kiểm thử content-type có tham số

Ngoài các test ở trên, nên thêm trường hợp **application/json;charset=UTF-8** để xác nhận media-type parser chấp nhận tham số hợp lệ, và trường hợp **application/json;charset=ISO-8859-1** để xác nhận trả 415 theo chính sách demo. Khi cần frontend gửi **application/vnd.company+json**, cập nhật allowlist có chủ đích và test lại; không âm thầm cho mọi subtype.

## 11. Tại sao chỉ dùng @PostMapping chưa đủ để bảo vệ một custom filter?

Giả sử controller login có:

~~~java
@PostMapping(path = "/api/login", consumes = "application/json")
public ResponseEntity<?> login(@RequestBody LoginRequest request) {
    // Fragment minh họa, cần LoginRequest và logic đăng nhập phù hợp.
    return ResponseEntity.ok().build();
}
~~~

Trong MVC, @PostMapping và consumes cung cấp request mapping tốt. Nhưng nếu bạn **đồng thời** có một custom filter được cấu hình cho /** và filter tự đọc password rồi gọi AuthenticationManager trước khi vào DispatcherServlet, thì mapping annotation không thể ngăn filter đó làm việc trên GET /api/login hoặc POST /api/other.

Khi dùng filter:

- Chọn matcher hẹp **trong filter** hoặc dùng AuthenticationFilter có RequestMatcher chính xác.
- Chọn SecurityFilterChain phù hợp **ở mức chain**.
- Duy trì authorization rules nhất quán **ở mức request**.
- Không cho filter đọc body của endpoint khác; body servlet thường chỉ đọc được một lần nếu không có wrapper thích hợp.
- Nếu cần 405/415 theo contract, xác định rõ thành phần nào chịu trách nhiệm trả chúng (MVC hay filter) thay vì trông đợi một rule permitAll.

## 12. Vì sao không kiểm tra kiểu nội dung chỉ bằng request.getHeader("Accept")?

**Accept** đại diện cho định dạng client muốn nhận trong response, không chứng minh request body là JSON. Một request có thể Accept: application/json nhưng Content-Type: application/x-www-form-urlencoded. Ngược lại, một client có Content-Type: application/json nhưng Accept: */* vẫn gửi JSON body hợp lệ.

Trong demo:

- Để quyết định **có parse JSON login body không**, xem Content-Type.
- Để quyết định **response trả định dạng gì**, có thể xem Accept hoặc công bố API luôn trả JSON theo contract.
- Để kiểm tra **dữ liệu JSON**, parse và validate body.
- Để kiểm tra **danh tính**, gọi AuthenticationManager.
- Để kiểm tra **quyền**, dùng authorizeHttpRequests và/hoặc method security.

Bốn câu hỏi này khác nhau; trộn chúng có thể tạo lỗi 401 giả, 415 giả hoặc đọc body sai.

## 13. 400, 401, 403, 405, 413, 415: đừng gộp mọi lỗi thành 401

| Status | Điều kiện tiêu biểu ở demo | Ý nghĩa thực tế |
| --- | --- | --- |
| **200 OK** | POST đúng contract, CSRF hợp lệ, credentials đúng | Đăng nhập thành công |
| **400 Bad Request** | JSON sai cú pháp/schema, username/password không đúng kiểu | Request body không hợp lệ |
| **401 Unauthorized** | Credentials sai, hoặc truy cập tài nguyên cần login mà chưa có session | Authentication không được chấp nhận |
| **403 Forbidden** | POST thiếu CSRF, hoặc user đã login nhưng không có ROLE_ADMIN | Policy bảo mật/authorization từ chối |
| **405 Method Not Allowed** | GET/PUT/... tới đúng /api/login | Method không được hỗ trợ; có Allow: POST |
| **413 Content Too Large** | JSON body quá 4096 byte | Server từ chối kích thước payload |
| **415 Unsupported Media Type** | Content-Type text/plain, XML, form hoặc thiếu header | Kiểu request body không nằm trong allowlist |

**Thứ tự lỗi không bất biến.** CSRF filter chạy trước JsonLoginFilter có thể trả 403 cho POST thiếu token dù body cũng sai Content-Type. Trong một hệ thống sử dụng CORS, preflight OPTIONS có thể được xử lý sớm hơn custom filter. Vì thế test mọi status phải tạo request thỏa các điều kiện đứng trước để cô lập nhánh muốn kiểm tra.

**413 và 415 không phải lỗi mật khẩu.** Đừng gọi AuthenticationManager khi đã biết payload quá lớn hoặc media type không được hỗ trợ.

**401 từ endpoint login** không cần trả tên user có tồn tại, trạng thái account, hash hoặc câu “password đúng/sai” quá chi tiết. Phản hồi chung giúp giảm nguy cơ username enumeration; audit nội bộ được bảo vệ có thể phân biệt nguyên nhân ở mức thích hợp.

## 14. Session, CSRF, cookie và lưu SecurityContext trong login tùy chỉnh

Khi bạn không dùng form login filter chuẩn mà tự viết authentication filter, **đăng nhập thành công trong request hiện tại không tự bảo đảm request tiếp theo đã login**.

Luồng cần hiểu:

~~~text
POST /api/login (CSRF hợp lệ + credentials đúng)
  |
  +-- AuthenticationManager tạo Authentication
  +-- SessionAuthenticationStrategy xử lý session liên quan login
  +-- SecurityContextHolder.setContext(context)
  +-- SecurityContextRepository.saveContext(context, request, response)
  |
  +-- response 200, session cookie được duy trì
          |
          v
GET /me + cookie cùng session
  |
  +-- SecurityContextHolderFilter/repository nạp context đã lưu
  +-- Authentication có danh tính hợp lệ
  +-- authorization cho /me
~~~

Trong Spring Security 6, **SecurityContextHolderFilter** không tự lưu mọi thay đổi context khi request kết thúc. Nếu tự gọi setContext mà không saveContext phù hợp, request hiện tại có thể biết user nhưng request sau mất login.

**Session fixation:** login làm thay đổi mức đặc quyền của session. Khi có session trước login, cần chính sách thay đổi session ID hoặc cách bảo vệ tương đương. Một custom filter không tự hưởng mọi hook của UsernamePasswordAuthenticationFilter, nên bài thực hành gọi session strategy tường minh.

**CSRF:** browser tự gửi session cookie trong những hoàn cảnh phù hợp, nên POST login và các thao tác đổi trạng thái cần xét CSRF. Demo giữ CSRF, cung cấp GET /csrf. Nếu custom login làm mới CSRF token sau thành công, client phải lấy token mới trước POST tiếp theo.

**Cookie attributes:** production cần HTTPS/Secure, HttpOnly, SameSite thích hợp, session timeout và logout đúng. Không ghi JSESSIONID ra log hay đưa vào URL.

**MFA/rate limits:** endpoint login thực có thể cần MFA, brute-force throttling, lockout/alerts, anomaly detection và chính sách bảo vệ tài khoản. Giới hạn path/method/media giúp giảm bề mặt lỗi nhưng **không thay thế những kiểm soát này**.

## 15. Một số khác biệt đáng chú ý trong triển khai

### 15.1. RequestMatcher có phải thay thế Content-Type check?

Không. RequestMatcher có thể kết hợp path và method, hoặc thậm chí kiểm tra header, nhưng **việc parse và validate JSON** vẫn phải diễn ra trước xác thực. Nếu đưa Content-Type vào matcher rồi để filter skip hoàn toàn khi media sai, request có thể rơi xuống authorizeHttpRequests và nhận 401/403/404 không nhất quán thay vì 415 theo API contract.

Trong demo, matcher chỉ nhận path; method và media type được kiểm tra bên trong để có status rõ ràng.

### 15.2. requestMatchers(...).permitAll có “mở login cho mọi method” không?

permitAll quyết định **authorization** nếu request tới bước đó, không bắt custom filter xác thực sai method. Tuy nhiên nó cũng không tự ngăn custom filter chạy; muốn 405 phải thiết kế rõ ở filter hoặc MVC mapping. Với demo, filter chặn method không phải POST trước controller.

### 15.3. Có nên disable CSRF cho /api/login?

Không như một phản xạ. Nếu login tạo session mà browser dùng cookie, login CSRF và CSRF cho các thao tác sau login vẫn cần phân tích. Demo giữ CSRF toàn bộ để minh họa. Nếu ứng dụng là API token stateless không dùng cookie/browser credentials tự gửi, có thể có chính sách khác, nhưng cần chứng minh threat model và test bảo mật.

### 15.4. Có nên cho phép GET /api/login để hiện form?

Ở ứng dụng **form login** truyền thống, GET /login có thể là trang HTML công khai, còn POST /login mới thực hiện xác thực. Ở **JSON API login** của bài này, /api/login chỉ có chức năng POST xác thực; nếu cần trang HTML riêng, đặt ở route khác như GET /login-page, tránh nhập nhằng.

### 15.5. Có nên nhận application/x-www-form-urlencoded thay vì JSON?

Có thể, **nếu đó là hợp đồng chủ đích**. Built-in UsernamePasswordAuthenticationFilter mặc định đọc các form parameter theo cơ chế riêng; JSON login custom không nên ngầm fallback sang form khi Content-Type sai. Nếu hỗ trợ cả hai, hãy công bố hai media types, hai parser, test CSRF và các quy tắc về precedence rõ ràng.

### 15.6. Có phải body JSON luôn dưới 4096 byte?

Không. Ngưỡng 4096 là **giá trị minh họa** cho hai chuỗi ngắn. Trong hệ thống thật, chọn giới hạn theo contract, headers/proxy limits, khả năng chống DoS và yêu cầu i18n. Đừng cho phép body không giới hạn vào object mapper hoặc log toàn bộ body để điều tra lỗi.

### 15.7. Có nên trả 404 thay cho 401 đối với path lạ?

Đây là quyết định thiết kế security/API. Trong demo, path lạ bị anyRequest().denyAll và anonymous được chuyển thành 401 bởi entry point; controller có thể chưa được gọi. Nếu muốn 404 cho route không tồn tại, phải thiết kế rule/exception handling có chủ đích, không dựa vào bộ lọc login để đoán.

### 15.8. Có nên dùng Content-Length làm kiểm tra duy nhất?

Không. Client có thể không gửi Content-Length (chunked) hoặc header không phản ánh lượng dữ liệu thực tế trong mọi đường đi. Demo giới hạn **số byte thực sự đọc** bằng readNBytes(MAX_BODY_BYTES+1), nên phát hiện vượt ngưỡng ngay cả khi không có Content-Length.

### 15.9. Có cần validate ký tự Unicode của username/password?

Nên xác định chính sách rõ: độ dài, chuẩn hóa, ký tự hợp lệ và xử lý Unicode nhất quán. Không tự động trim hoặc thay đổi password người dùng nhập vì password có thể hợp lệ với dấu cách. Demo chỉ bác giá trị toàn whitespace và quá dài; production phải có contract cụ thể và cân nhắc canonicalization của username.

### 15.10. Có cần validate Accept?

Nếu API contract chỉ trả JSON và client gửi Accept không phù hợp, server có thể áp dụng content negotiation và trả 406 Not Acceptable. Demo cố định response JSON cho ngắn gọn; nội dung bài tập trung vào **request Content-Type**, không tuyên bố đã hỗ trợ mọi Accept negotiation.

## 16. Chẩn đoán sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| GET /api/login cũng làm login | Custom filter chỉ so path, quên method | Kiểm tra điều kiện POST trong filter |
| POST /api/login/extra làm login | Matcher /** hoặc /api/login/** quá rộng | Dùng exact path matcher và negative-path test |
| POST text/plain vẫn login | Parser JSON được gọi mà không validate Content-Type | MediaType allowlist, test 415 |
| POST application/json;charset=UTF-8 bị từ chối | So chuỗi Content-Type bằng equals | Parse MediaType thay vì so raw string |
| JSON sai cấu trúc gây 500 | Không xử lý lỗi parse/schema | Trả 400, validate kiểu, độ dài, field |
| Body cực lớn làm server tốn bộ nhớ | Không giới hạn bytes, tin Content-Length | Limit ở gateway/container và filter |
| POST login hợp lệ nhận 403 | Thiếu hoặc sai CSRF token | GET /csrf, cookie cùng session, gửi X-CSRF-TOKEN |
| Login thành công nhưng /me sau đó 401 | Chỉ set SecurityContextHolder, quên saveContext hoặc mất cookie | Kiểm tra repository, session ID và request tiếp |
| Login sai password lại trả 400 | Trộn credentials với lỗi request body | Phân biệt 400 schema và 401 auth |
| Endpoint login trả redirect 302 | formLogin entry point/chain khác can thiệp | Xem SecurityFilterChain, formLogin/httpBasic, exceptionHandling |
| Filter chạy hai lần | @Component/@Bean gây Servlet registration và thêm vào SecurityFilterChain | Đăng ký một lần, kiểm tra chain |
| /api/login không bao giờ vào filter | securityMatcher chain không khớp, filter thứ tự sai | Xem chain đầu tiên khớp và filter insertion |
| Proxy làm mất Content-Type/CSRF/header | Gateway thay đổi hoặc không forward headers/cookie | Kiểm tra config proxy, không log raw secrets |
| OPTIONS preflight bị 405/403 | Chưa cấu hình CORS cho frontend khác origin | Thiết kế CORS/OPTIONS cụ thể, không mở rộng tùy tiện |

**Quy trình debug khuyến nghị:**

1. Tái hiện bằng request có method/path/Content-Type rõ ràng và credentials **dữ liệu test**.
2. Xác định SecurityFilterChain nào được chọn.
3. Kiểm tra CSRF/CORS có dừng request trước custom filter không.
4. Kiểm tra matcher path (có trùng hoàn toàn không), sau đó method.
5. Xác minh media allowlist, charset và byte count.
6. Parse/schema validation trước AuthenticationManager.
7. Nếu đến bước auth, kiểm tra UserDetailsService, PasswordEncoder và các AuthenticationException.
8. Khi auth thành công, kiểm tra SessionAuthenticationStrategy và repository.saveContext trước response commit.
9. Kiểm tra request tiếp theo có gửi cookie đúng scope và session còn hợp lệ không.
10. Dùng MockMvc/integration tests để khóa behavior; không chữa lỗi bằng cách disable toàn bộ security.

## 17. Bài tập thực hành

### Bài A — Phân biệt matcher và authorization

Custom filter có matcher /** nhưng security config chỉ permitAll POST /api/login. Request GET /api/users có thể bị filter đọc body trước khi tới AuthorizationFilter không?

**Đáp án:** Có thể. Rule permitAll không giới hạn filter chạy trước đó. Phải giới hạn filter bằng matcher đúng path/method hoặc kiểm tra contract bên trong.

### Bài B — Content-Type và Accept

Request gửi **Content-Type: text/plain**, **Accept: application/json**, body là JSON. Nên xem header nào để quyết định có parse JSON login body? Với contract JSON-only, status nào phù hợp?

**Đáp án:** Xem **Content-Type**, trả 415 vì text/plain không được hỗ trợ; Accept chỉ mô tả response mong muốn.

### Bài C — Có thể chấp nhận charset?

Request POST /api/login gửi **Content-Type: application/json;charset=UTF-8**. Tại sao so chuỗi với "application/json" là sai?

**Đáp án:** Media type có thể có tham số hợp lệ. Dùng MediaType.parseMediaType và kiểm tra tính tương thích/charset chính sách.

### Bài D — 405 hay 401?

Người chưa đăng nhập gọi **GET /api/login**. Với demo, vì sao 405 thay vì 401?

**Đáp án:** Request trùng exact login path, filter áp contract method trước khi yêu cầu xác thực; method GET không được hỗ trợ, nên trả 405 + Allow: POST. Nếu filter không xử lý trường hợp này, status có thể khác theo authorization config.

### Bài E — CSRF chạy trước media validation

POST /api/login với Content-Type text/plain và không có CSRF token. Demo có thể trả 403 thay vì 415 không? Vì sao?

**Đáp án:** Có. CsrfFilter từ chối request trước khi JsonLoginFilter kiểm tra media type. Khi muốn test 415, phải gửi CSRF token hợp lệ.

### Bài F — Truy cập path lạ

POST /api/login/extra với JSON credentials đúng có được đăng nhập không? Có chắc trả 404 không?

**Đáp án:** Không được login, vì matcher exact /api/login không nhận /api/login/extra. Status cuối do SecurityFilterChain/authorization/MVC quyết định, không luôn là 404.

### Bài G — Login thành công nhưng request tiếp mất trạng thái

Custom filter gọi manager.authenticate và SecurityContextHolder.setContext, trả 200 nhưng không saveContext. Vì sao GET /me với cookie vẫn có thể nhận 401?

**Đáp án:** Trong Spring Security 6 với explicit save, setContext cho request hiện tại không tự persist session. Cần repository.saveContext trước response commit và dùng repository tương ứng để load.

### Bài H — Body giới hạn và encoding

Client gửi Content-Type application/json nhưng body dài 5000 byte hoặc byte không phải UTF-8. Demo trả gì?

**Đáp án:** Body vượt 4096 byte trả 413; nếu size không vượt nhưng encoding UTF-8 sai thì 400. CSRF có thể trả 403 sớm hơn nếu thiếu token.

### Bài I — Viết test thiếu quyền

Sau khi learner login thành công, dùng session đó gọi GET /admin. Status nào? Có nghĩa mật khẩu sai không?

**Đáp án:** 403 vì learner có ROLE_USER nhưng endpoint đòi ROLE_ADMIN; mật khẩu đã được xác thực thành công trước đó.

### Bài K — Tư duy deployment nhiều chain

Có chain @Order(1) match /api/** và chain @Order(2) match /**, nhưng custom JsonLoginFilter chỉ được thêm vào chain thứ hai. POST /api/login có đi qua filter ở chain thứ hai không?

**Đáp án:** Không, vì chain đầu tiên đã khớp. Phải đặt filter vào chain xử lý /api/login hoặc sửa chiến lược matcher/thứ tự cho đúng.

## 18. Checklist trước khi release endpoint login tùy chỉnh

- [ ] Chỉ đúng **path login** được xử lý; đã test các đường dẫn gần giống, query string và context path khi triển khai.
- [ ] Chỉ đúng **HTTP method** được chấp nhận; method khác không thể kích hoạt AuthenticationManager.
- [ ] Có **405 + Allow** hoặc hợp đồng lỗi method tương đương được công bố và kiểm thử.
- [ ] Request **Content-Type** nằm trong allowlist; không nhầm Accept với Content-Type.
- [ ] Hỗ trợ tham số Content-Type hợp lệ; có chính sách rõ cho UTF-8, vendor +json, multipart/form và body rỗng.
- [ ] JSON được parse/validate schema, kiểu dữ liệu, độ dài và kích thước body trước bước xác thực.
- [ ] Phân biệt **400/401/403/405/413/415** theo nguyên nhân và thứ tự filter.
- [ ] Không log raw username/password, body nhạy cảm, session cookie, CSRF token, Authorization header hoặc token truy cập.
- [ ] HTTPS, rate limiting, giám sát brute force và bảo vệ tài khoản có thiết kế phù hợp.
- [ ] CSRF được phân tích theo client/session/cookie; không disable mặc định chỉ vì endpoint là JSON.
- [ ] Khi login custom dùng session, đã gọi SessionAuthenticationStrategy, setContext và **saveContext** trước response commit.
- [ ] Session fixation protection, CSRF rotation, cookie attributes, logout/session timeout được kiểm tra.
- [ ] Không đăng ký filter hai lần ở Servlet container và Spring Security chain.
- [ ] Không đặt filter nhầm SecurityFilterChain khi có nhiều chain.
- [ ] Đã test path sai, method sai, media sai, JSON sai, oversized payload, password sai, thiếu CSRF, login đúng và quyền truy cập sau login.
- [ ] Tham số minh họa (body size, password mẫu, in-memory users) được thay bằng thiết kế production thích hợp.

**Kết luận:** Đối với custom login, hãy kiểm soát **đúng URL → đúng HTTP method → đúng Content-Type → đúng JSON body → đúng credentials**, đồng thời nhớ rằng CSRF và các filter khác có thể quyết định trước. Authorization rules không tự giới hạn mọi filter, và annotation @PostMapping(consumes=...) không bảo vệ một filter chạy trước MVC. Spring Security có các extension point chính thức; khi tự viết filter, phải chịu trách nhiệm cả matcher, response lỗi, session protection và lưu SecurityContext an toàn.
