# REST API không tự quyết định ứng dụng phải dùng phiên hay token

> **Ngữ cảnh:** nền tảng HTTP trong Spring Security (Servlet/Spring MVC, Java 17+ và Spring Boot 3.x). Khi thiết kế API, thường gặp phát biểu “REST là stateless nên phải dùng JWT, tuyệt đối không được dùng session”. Phát biểu đó trộn lẫn **kiểu kiến trúc API**, **vòng đời trạng thái của client**, **cơ chế xác thực** và **cách lưu thông tin đăng nhập**. Những quyết định này liên quan nhưng cần được phân tích riêng.

## 1. Điều cần hiểu đúng trước tiên

- **REST** là phong cách kiến trúc với những ràng buộc, trong đó có **stateless communication**: server phải có đủ thông tin từ mỗi request để hiểu và xử lý request đó; server không dựa vào **trạng thái hội thoại của client** được lưu giữa các request.
- **HTTP** là giao thức request/response, bản thân mỗi request có thể độc lập; HTTP vẫn hỗ trợ cookie, authorization header và nhiều cơ chế để ứng dụng duy trì đăng nhập.
- **Session** là một cách duy trì ngữ cảnh đăng nhập hoặc dữ liệu khác qua nhiều request. Nếu server cần tra cứu **session xác thực của client đã lưu từ request trước** để hiểu một request, ứng dụng có phụ thuộc vào session state phía server và không đáp ứng cách diễn giải **REST statelessness nghiêm ngặt** cho luồng đó.
- **Token** là một bằng chứng. Token có thể là JWT tự xác minh được, hoặc opaque token phải hỏi một dịch vụ/lookup server để biết hiệu lực. Token không tự động làm hệ thống “stateless”.
- **Spring Security** không buộc mọi ứng dụng JSON API phải chọn session hoặc JWT. Bạn cấu hình **SecurityFilterChain**, cơ chế **Authentication**, **SecurityContextRepository** và chính sách session cho kiến trúc đang xây dựng.

Nói một cách thực dụng: **một HTTP API trả JSON vẫn có thể sử dụng session cookie** như rất nhiều ứng dụng web. Tuy nhiên, nếu yêu cầu là **tuân thủ chặt ràng buộc REST stateless**, hãy xem việc dựa vào server-stored client session như một phụ thuộc cần loại bỏ hoặc thiết kế lại. Nhãn “REST API” trên tài liệu không tự quyết định phương thức xác thực cho ứng dụng.

## 2. Ba câu hỏi độc lập dễ bị trộn làm một

Khi thiết kế endpoint **GET /api/orders/42**, hãy hỏi theo thứ tự:

| Trục quyết định | Câu hỏi | Các lựa chọn ví dụ |
| --- | --- | --- |
| **Kiểu API / semantics** | Tài nguyên, phương thức HTTP, representation và các ràng buộc REST là gì? | GET /orders/42, response JSON, cache policy, hypermedia nếu áp dụng |
| **Xác thực / credential** | Client chứng minh danh tính bằng gì? | Form login, HTTP Basic, OAuth2 access token, API key, mTLS |
| **Quản lý trạng thái xác thực** | Request kế tiếp lấy danh tính từ đâu? | HttpSession, header Basic mỗi lần, JWT Bearer, opaque token + introspection, BFF session |

Không suy ra một trục từ trục khác. Một endpoint trả JSON có thể phục vụ browser thông qua session cookie, ứng dụng mobile thông qua access token, hoặc service nội bộ qua mTLS, tùy cách triển khai và ràng buộc bảo mật.

**Statelessness của REST không đồng nghĩa với:**

1. “Server không được lưu bất cứ dữ liệu gì.” Server vẫn lưu **resource state**: đơn hàng, tài khoản, tồn kho, phiên bản, quyền của người dùng, v.v.
2. “Không được dùng database/cache.” Database và cache có thể phục vụ resource state hoặc kiểm tra quyền; điều quan trọng là request không được buộc phải dựa vào **client conversational context** ngầm từ request trước.
3. “Mỗi request phải chứa password.” Request có thể dùng credential đã được cấp, chẳng hạn Bearer access token.
4. “Bắt buộc JWT.” Token opaque, signed request hay Basic cũng có thể cung cấp đủ thông tin xác thực theo cơ chế tương ứng; còn JWT sai issuer/audience/chữ ký vẫn vô giá trị.
5. “Có JWT là mọi thứ stateless.” JWT có thể đi cùng refresh-token store, revocation list, session của authorization server hoặc các cơ chế trạng thái khác.

## 3. REST statelessness thật sự yêu cầu điều gì?

Theo mô tả REST của Roy Fielding, mỗi request từ client đến server phải chứa mọi thông tin cần để server hiểu request; request không được dựa vào ngữ cảnh được lưu trên server từ những tương tác trước. **Trạng thái phiên/hội thoại của client** thuộc trách nhiệm của client, còn **trạng thái tài nguyên** có thể và thường được lưu ở server.

Ví dụ tài nguyên:

~~~http
GET /api/orders/42 HTTP/1.1
Host: example.test
Accept: application/json
Authorization: Bearer <access-token>
~~~

Một implementation có thể đọc **resource 42** từ database và kiểm tra danh tính/quyền theo access token trong request. Database lưu đơn hàng không vi phạm ý tưởng stateless. Câu hỏi cốt lõi: server có cần nhớ “client này vừa đến bước 2 trong một cuộc hội thoại trước đó” hay “session id này trỏ đến context đã giữ từ lần đăng nhập trước” để hiểu request không?

### 3.1. Phân biệt application state và resource state

- **Resource state**: trạng thái một tài nguyên được quản lý bởi server; ví dụ đơn hàng số 42 đang **PAID**. Đây là dữ liệu nghiệp vụ.
- **Client application state**: client đang đứng ở màn hình nào, bộ lọc đang chọn, bước workflow nào, representation/URL kế tiếp nào. Trong REST nghiêm ngặt, server không giữ một “conversation slot” bí mật để client bắt buộc phải dựa vào.
- **Authentication/session state**: tên người dùng, authorities hoặc SecurityContext được giữ qua request. Việc lưu chúng ở server rồi tra cứu bằng cookie tạo ra phụ thuộc giữa các request. Điều đó có thể **hoàn toàn phù hợp một ứng dụng web thực tế**, nhưng cần thành thật với sự khác biệt so với ràng buộc stateless nghiêm ngặt.

Một workflow vẫn có thể gồm nhiều bước trong API stateless nếu **trạng thái workflow là tài nguyên có địa chỉ và cách chuyển trạng thái rõ ràng**, ví dụ **POST /orders** tạo đơn hàng rồi **POST /orders/42/approve** dựa trên trạng thái tài nguyên hiện tại và quyền trong request. Không cần server giữ biến toàn cục “client đang ở step 2”.

### 3.2. HTTP stateless không xóa được khái niệm session

HTTP request thường độc lập ở tầng giao thức. Để giữ đăng nhập, web app có thể:

~~~text
POST /login (đăng nhập)
    |
    v
Server xác thực, lưu SecurityContext/session, phát session id
    |
    v
Set-Cookie: JSESSIONID=...
    |
    v
GET /account  +  Cookie: JSESSIONID=...
    |
    v
Server tra session -> nhận Authentication -> kiểm tra quyền
~~~

HTTP vẫn vận chuyển các request hợp lệ, song **thông tin xác thực hữu ích nằm trong trạng thái session phía server**. Session không phải thuộc tính bắt buộc của HTTP hay REST; đó là **một lựa chọn kiến trúc ứng dụng**.

## 4. Hai cách đi qua cùng một endpoint bảo mật

Giả sử endpoint **GET /me** trả thông tin người dùng.

### 4.1. Dùng session cookie

~~~http
POST /login HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded

username=alice&password=example
~~~

Đây là ví dụ HTTP minh họa, không phải thông tin đăng nhập thật. Nếu thành công, một ứng dụng web có thể tạo session và trả cookie:

~~~http
HTTP/1.1 302 Found
Location: /
Set-Cookie: JSESSIONID=<session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Sau đó browser gửi:

~~~http
GET /me HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-id>
~~~

Server cần tìm session còn hiệu lực, khôi phục authentication, rồi quyết định quyền. Client **không cần gửi password lại trên mỗi request**. Browser cũng thường tự gửi cookie theo Domain/Path/Secure/SameSite của cookie.

Với session cookie, logout có thể làm session phía server mất hiệu lực. Nhưng hệ thống phân tán cần thiết kế lưu trữ session dùng chung, stickiness hoặc cơ chế thích hợp; việc thêm server instance không tự bảo đảm mọi instance nhận được cùng session.

### 4.2. Dùng Bearer access token

Sau một quy trình cấp token hợp lệ (ví dụ OAuth2 Authorization Code + PKCE), client dùng access token để gọi API:

~~~http
GET /me HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Resource server cần xác minh token, nguồn phát hành, đối tượng nhận token, hạn dùng và quyền phù hợp. Nếu token là **JWT được ký**, nhiều thông tin có thể kiểm chứng dựa trên khóa/validator mà không cần truy vấn session theo client ở mỗi request. Nếu token là **opaque**, resource server có thể dùng **introspection** hoặc tra cứu dữ liệu do authorization server quản lý. Những cách này có đặc tính vận hành khác nhau.

Bearer token là “ai có token thường có thể dùng token”. Do đó access token bị đánh cắp là một rủi ro nghiêm trọng, ngay cả khi API không dùng session.

**Access token không phải ID token**: ID token trong OpenID Connect dành cho client xác minh thông tin về phiên xác thực; không tự lấy ID token thay access token gửi vào mọi resource API.

### 4.3. Dùng HTTP Basic với request độc lập

~~~http
GET /me HTTP/1.1
Host: api.example.test
Authorization: Basic YWxpY2U6ZXhhbXBsZQ==
~~~

Chuỗi Base64 ví dụ đại diện **alice:example**. Basic thường gửi lại username/password theo request, vì vậy có thể triển khai không dùng HttpSession để lưu SecurityContext. **Basic không cần JWT**, nhưng phải dùng HTTPS; Base64 không phải mã hóa bảo mật. Browser có thể tự gửi lại Basic credential theo cơ chế HTTP authentication, nên không được suy ra “đã stateless thì chắc chắn không có CSRF”.

Cả ba cách vẫn phải kiểm tra **AuthorizationManager** hoặc policy nghiệp vụ để quyết định có được phép truy cập **GET /me** hay không. Không cơ chế nào tự thay thế kiểm tra quyền.

## 5. Session, JWT và opaque token: so sánh đúng các tiêu chí

| Tiêu chí | Session cookie lưu context ở server | Bearer JWT access token | Opaque access token |
| --- | --- | --- | --- |
| **Credential client giữ** | Session identifier | JWT | Chuỗi opaque |
| **Server biết danh tính** | Tra session/context | Xác minh chữ ký và claims | Tra cứu/introspection |
| **Giữ trạng thái phiên ở server** | Thường có | Không cần để xác minh một JWT ký đúng, nhưng hệ thống vẫn có thể có state khác | Thường có dữ liệu trạng thái token ở server cấp token |
| **Thu hồi ngay** | Có thể vô hiệu hóa session phía server | Thường cần thời hạn ngắn, danh sách thu hồi hoặc biện pháp bổ sung | Có thể kiểm tra trạng thái token, tùy caching |
| **Dữ liệu client có thể đọc** | Session id thường không diễn giải được | Payload JWT ký thường đọc được sau Base64URL decode | Client thường không đọc claims trực tiếp |
| **Rủi ro khi credential lộ** | Chiếm phiên cho đến khi hết hiệu lực/thu hồi | Sử dụng token cho tới hết hạn/thu hồi | Sử dụng token cho tới hết hạn/thu hồi |
| **Scale hệ thống** | Cần kho session nhất quán hoặc giải pháp tương đương | Resource server có thể xác minh local, cần key rotation/validator | Cần introspection/lookup hoặc cache có kiểm soát |
| **Browser/CSRF** | Cookie tự gửi: phải cân nhắc CSRF | Header Bearer do code chủ động thêm: mô hình CSRF khác | Phụ thuộc cách token được truyền; cookie chứa token cũng có CSRF |
| **Phù hợp điển hình** | Web app truyền thống, server-rendered, BFF | API cho mobile/SPA/service theo kiến trúc OAuth2 | API cần token mờ và kiểm tra trạng thái tập trung |

Bảng là **so sánh đặc tính thường gặp**, không phải khẳng định bất biến. JWT cũng có thể đặt trong cookie; session id có thể được gửi qua custom header; opaque token vẫn có thể được cache; một hệ thống có thể dùng session ở browser và access token giữa backend với API. Vì vậy câu hỏi “cookie hay JWT?” thực ra đang so sánh **một phương tiện truyền credential** với **một định dạng token**, không cùng cấp khái niệm.

### 5.1. Cookie không phải session; JWT không phải header

- **Cookie** là cơ chế browser lưu/gửi một cặp name/value qua header Cookie; giá trị có thể là session id hoặc token tùy kiến trúc.
- **Session** là ngữ cảnh phía server hoặc một khái niệm phiên trong hệ thống; có thể được nhận diện qua cookie.
- **Authorization** là HTTP header phổ biến để gửi Basic/Bearer credential.
- **JWT** là định dạng token có claims; cách truyền JWT không cố định là header, mặc dù **Authorization: Bearer** thường là lựa chọn chuẩn cho resource API.
- **OAuth2** là khung cấp quyền và cấp token; OAuth2 không đồng nghĩa JWT hoặc “bắt buộc stateless”.
- **OpenID Connect** bổ sung lớp identity trên OAuth2; ID token có mục đích khác access token.

## 6. Spring Security quản lý SecurityContext và HttpSession ra sao?

**Authentication** (principal, authorities, trạng thái xác thực) được Spring Security giữ trong **SecurityContext** của request. **SecurityContextHolder** giúp filter/controller/service truy cập ngữ cảnh đó trong phạm vi thực thi phù hợp. Một **SecurityContextRepository** có thể tải/lưu ngữ cảnh giữa các request, chẳng hạn qua **HttpSessionSecurityContextRepository**, hoặc không lưu qua session như **NullSecurityContextRepository**.

Vòng đời đơn giản:

~~~text
Nhận request
    |
    v
Tìm SecurityFilterChain phù hợp
    |
    v
Tải/khởi tạo SecurityContext theo repository của chain
    |
    v
Filter authentication đọc credential phù hợp
    |
    v
SecurityContext chứa Authentication hợp lệ
    |
    v
AuthorizationFilter / method security
    |
    v
Controller và service
    |
    v
Kết thúc request, dọn SecurityContext gắn với luồng
~~~

Cần phân biệt hai việc:

1. **Context hiện tại** tồn tại trong lúc xử lý request, dù API có được cấu hình stateless hay không.
2. **Lưu context qua nhiều request** là việc khác; phụ thuộc repository và cơ chế authentication/login. Trong cơ chế hiện đại, filter đăng nhập thường phải lưu context một cách rõ ràng nếu muốn tái sử dụng ở request sau.

### 6.1. SessionCreationPolicy có ý nghĩa thực tế gì?

Spring Security Servlet định nghĩa các chính sách sau:

| Giá trị | Ý nghĩa về HttpSession trong Spring Security |
| --- | --- |
| **ALWAYS** | Luôn tạo HttpSession khi cần thiết theo cơ chế của Spring Security |
| **IF_REQUIRED** | Chỉ tạo session khi cần, đây là lựa chọn mặc định điển hình |
| **NEVER** | Không chủ động tạo session nhưng có thể sử dụng session đã tồn tại |
| **STATELESS** | Không tạo session và không sử dụng HttpSession để lấy SecurityContext |

**STATELESS** là lựa chọn cấu hình quản lý session của **Spring Security**, không phải bộ kiểm chứng tuân thủ toàn bộ ràng buộc REST. Nó **không cấm mọi thành phần khác của ứng dụng gọi request.getSession()**, không chứng minh server không dùng database/cache và không tự kích hoạt xác thực JWT.

Ví dụ cấu hình riêng một chain API không lưu SecurityContext trong HttpSession:

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .httpBasic(Customizer.withDefaults());
~~~

Đây là **đoạn cấu hình trong SecurityFilterChain**, chưa phải một chương trình đầy đủ. HTTP Basic cho phép request cung cấp credential ở mỗi lần gọi; không có nhu cầu bắt buộc lưu session xác thực. Vì browser có thể tự gửi Basic credential và vì yêu cầu CSRF tùy cách client được dùng, **không tùy tiện tắt CSRF chỉ dựa trên chữ STATELESS**.

### 6.2. REST không yêu cầu SessionCreationPolicy.STATELESS trong mọi sản phẩm

Một web app server-rendered dùng session hợp lý vì client browser, logout, CSRF và vòng đời đăng nhập phù hợp. Khi team gọi các endpoint JSON của nó là “REST API”, cách gọi đó không tự biến một ứng dụng hiện hữu thành kiến trúc không có state. Có thể phục vụ JSON theo HTTP qua session mà vẫn có semantics API rõ ràng, đồng thời mô tả chính xác giới hạn khi xét REST stateless constraint.

Ngược lại, hệ thống chọn **STATELESS** vì mỗi request mang Basic hoặc Bearer credential cũng phải xử lý các vấn đề còn lại như quyền theo tài nguyên, token revocation, rate limiting và logging. Nó không tự bảo đảm API an toàn.

## 7. Ví dụ thực hành: cùng một ứng dụng có web session và API không dùng session

Ví dụ dùng **Spring Boot 3.x, Spring Security 6.x và Java 17+**. Chúng ta tạo **hai SecurityFilterChain có matcher rõ ràng**:

- **/api/**: HTTP Basic với **SessionCreationPolicy.STATELESS**. Request tới API phải tự cung cấp Basic credential khi endpoint cần đăng nhập.
- **Phần web**: form login và session. Sau đăng nhập browser có thể truy cập **/web/me** nhờ cookie chứa session id.

Cả hai dùng cùng danh sách user demo. Ví dụ chỉ dùng **GET** cho endpoint nghiệp vụ; **POST /login** sử dụng CSRF token do Spring Security cung cấp. Các password là giả cho môi trường localhost.

### 7.1. Dependencies

Từ project Spring Boot 3.x có plugin, Gradle Wrapper và dependency management, bổ sung:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo các file Java trong thư mục **src/main/java/com/example/sessionortoken/**, với package **com.example.sessionortoken**.

### 7.2. SessionOrTokenApplication.java

~~~java
package com.example.sessionortoken;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionOrTokenApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionOrTokenApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java: hai chain, hai chính sách

~~~java
package com.example.sessionortoken;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
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
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .requestMatchers("/web/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

**Giải thích các điểm quan trọng:**

- **@Order(1)** chọn chain **/api/** trước; **@Order(2)** là chain web không khai báo securityMatcher nên có thể bắt các URL còn lại.
- **securityMatcher("/api/**")** quyết định request **thuộc chain API nào**; **requestMatchers(...)** bên trong quyết định các rule authorization. Nếu quên một chain bao trùm cho URL khác, các URL đó có thể nằm ngoài lớp bảo vệ Spring Security.
- Chain API dùng **STATELESS**, không nạp SecurityContext từ HttpSession. Dù client có session cookie của web, request **/api/me** chỉ có cookie đó không tự được công nhận là đăng nhập bởi chain API.
- Chain web dùng **formLogin**. Spring Security có thể tạo trang đăng nhập mặc định **GET /login**, nhận **POST /login**, lưu context trong session sau khi đăng nhập thành công và khôi phục cho request tiếp theo.
- Hai chain áp dụng các cơ chế khác nhau nhưng **cùng một ứng dụng HTTP**, minh họa rằng việc “trả API” không ép toàn bộ ứng dụng phải dùng một phương thức đăng nhập.
- **anyRequest().denyAll()** chặn endpoint chưa khai báo quyền. Khi phát triển thực tế cần thiết kế ngoại lệ có chủ đích cho health, error/forward dispatch, static assets và các endpoint kỹ thuật.
- CSRF **không bị vô hiệu hóa**. Ví dụ chạy các request GET và đăng nhập form có token CSRF hợp lệ; nếu mở POST/PUT/DELETE ở API, phải thiết kế chính sách CSRF dựa trên loại client và cách credential được gửi.
- **BCryptPasswordEncoder** băm password cho kiểm tra; demo dùng password cố định để dễ thử nhưng production phải dùng credential/identity management thích hợp.

### 7.4. DemoController.java

~~~java
package com.example.sessionortoken;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/api/public")
    public String publicApi() {
        return "api-public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web:" + authentication.getName();
    }
}
~~~

Controller chỉ lấy **Authentication** đã được Spring Security xác minh; nó không tự đọc password, cookie hay Bearer token từ request.

### 7.5. Chạy và quan sát bằng HTTP client

Khởi động trong thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Thử API trước:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i http://localhost:8080/web/me
~~~

Kết quả **dự kiến** với cấu hình minh họa:

| Request | Status | Ý nghĩa |
| --- | --- | --- |
| Anonymous → GET /api/public | **200**, body **api-public** | Public API |
| Anonymous → GET /api/me | **401**, có Basic challenge | API cần credential ngay trong request |
| Basic alice → GET /api/me | **200**, body **api:alice** | HTTP Basic xác thực cho request |
| Anonymous → GET /web/me | **302** đến trang login | Web chain dùng form login |
| Sau khi login thành công, cookie session → GET /web/me | **200**, body **web:alice** | Web chain dùng session |
| Chỉ đưa cookie web-session đến GET /api/me | **401** | API chain không dùng session đó để xác thực |

Cần phân biệt: dùng **curl -u** gửi Basic cho **một request** không có nghĩa curl đã giữ session đăng nhập cho **request tiếp theo**. Để mô phỏng web login thủ công với curl, cần xử lý trang/form login, cookie jar và CSRF token chính xác. Test MockMvc dưới đây cho một ví dụ tái lập ổn định hơn.

### 7.6. Kiểm thử MockMvc chứng minh hai cách hoạt động độc lập

Tạo **src/test/java/com/example/sessionortoken/SessionOrTokenTest.java**:

~~~java
package com.example.sessionortoken;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionOrTokenTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiAcceptsBasicWithoutSession() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:alice"));

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void webLoginCreatesReusableSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);

        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:alice"));

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void webWithoutSessionRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicApiRequiresNoCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Ý nghĩa của từng nhóm assertion:**

1. **apiAcceptsBasicWithoutSession:** API dùng Basic credential ngay ở request có header; request mới không có header không tự duy trì đăng nhập.
2. **webLoginCreatesReusableSession:** form login với CSRF token hợp lệ tạo session; gửi session sang request web kế tiếp cho phép nhận diện cùng user.
3. **webLoginCreatesReusableSession (phần API):** cùng session đó khi đưa đến API chain có **STATELESS** không thay thế được Basic credential.
4. **webWithoutSessionRedirectsToLogin:** form-login entry point có thể phản hồi redirect, khác HTTP Basic challenge.
5. **publicApiRequiresNoCredentials:** resource được phép công khai không cần xác thực.

Đây là các test tích hợp với **Spring Boot 3.x**. Nếu dùng Spring Boot 4 hoặc một phiên bản Spring Security khác, package/import và một số API kiểm thử có thể thay đổi; điều chỉnh theo dependency được chọn thay vì sao chép máy móc.

## 8. Nếu chọn Bearer token thay HTTP Basic cho API

HTTP Basic làm rõ ý tưởng **mỗi request tự có credential** nhưng việc gửi password lặp lại không phù hợp nhiều API production. Với hệ thống có OAuth2/OIDC, API có thể là **OAuth2 Resource Server** nhận access token.

Thêm dependency phù hợp vào project Spring Boot 3.x:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Cấu hình issuer minh họa trong **application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
~~~

Issuer trên là **địa chỉ ví dụ**, không phải endpoint thực đang phát token. Với JWT, Resource Server cần khóa tin cậy và validators; trong production phải cấu hình kiểm tra **issuer**, **audience**, thời hạn và các thông số liên quan theo đặc tả API.

Thay cơ chế Basic của **apiChain** bằng đoạn sau, bên trong cấu hình SecurityFilterChain; đây là **snippet**, không phải một lớp Java biên dịch độc lập:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll()
    )
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

Từ client:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <valid-access-token>
~~~

**Không tự thay ID token cho access token.** Spring Security mặc định lấy Bearer từ Authorization header, kiểm tra access token theo cấu hình. JWT hợp lệ nhưng thiếu authority yêu cầu hoặc sai resource-level policy vẫn phải bị từ chối.

**STATELESS** ở đây phù hợp API không sử dụng HttpSession để lưu SecurityContext; **JWT không phải hệ quả bắt buộc của STATELESS**. Nếu thay JWT bằng opaque token + introspection, vẫn có thể vận hành một API không dựa vào session đăng nhập của browser, nhưng mức độ phụ thuộc trạng thái bên ngoài khác.

## 9. CORS, CSRF và cách client mang credential có tác động thế nào?

### 9.1. Cookie session và CSRF

Browser thường tự gửi session cookie theo quy tắc cookie. Điều này tạo rủi ro **Cross-Site Request Forgery** khi trang khác có thể khiến browser phát request thay người dùng. Web app dùng session/cookie cho thao tác đổi dữ liệu cần cơ chế CSRF như token hợp lệ và thuộc tính cookie phù hợp.

**HttpOnly** giúp hạn chế JavaScript đọc cookie nhưng không giải quyết CSRF: browser vẫn có thể tự gắn cookie. **SameSite** là một lớp giảm rủi ro, không tự thay mọi biện pháp bảo vệ CSRF. Trên Spring Security Servlet, CSRF protection thường bật mặc định cho các phương thức HTTP không an toàn khi chưa cấu hình thay đổi.

### 9.2. Bearer token trong Authorization header

Nếu JavaScript frontend chủ động gắn Bearer header cho request, trình duyệt **không tự đưa header đó vào mọi cross-site request** giống cookie. Vì thế mô hình CSRF khác session cookie. Tuy nhiên, frontend phải bảo vệ access token trước **XSS**, lộ qua logging, third-party script và việc lưu token không an toàn.

Nếu **token được chứa trong cookie tự gửi**, request vẫn có rủi ro CSRF dù nội dung cookie là JWT. Câu hỏi đúng là **credential có được browser tự thêm vào request hay không**, không phải “định dạng bên trong là JWT hay session ID”.

### 9.3. CORS không phải authentication

Browser gửi **Authorization: Bearer** đến origin khác thường cần CORS preflight. Server phải cấu hình CORS chính xác (origin, method, headers, credentials), nhưng cho phép CORS **không cấp quyền** cho người dùng. CORS là cơ chế phía browser kiểm soát truy cập tài nguyên cross-origin; curl/Postman không áp dụng chính sách browser đó.

Nếu frontend dùng session cookie cross-origin với **credentials: include**, cần đồng thời đáp ứng chính sách **SameSite/Secure** và CORS credentials. **Access-Control-Allow-Origin: *** không hợp lệ cho credentialed response trong browser; phải khai báo origin được phép cụ thể.

### 9.4. HTTPS và an toàn credential

Dù dùng cookie, Basic hay Bearer:

- Bắt buộc TLS hợp lệ trên mạng không tin cậy.
- Tránh ghi **Authorization**, **Cookie**, **Set-Cookie**, password và token vào log.
- Không đưa access token vào URL query hoặc browser history.
- Giới hạn quyền, thời hạn, audience, khả năng thu hồi và rotation.
- Không tự forward bearer token sang downstream service không đúng audience.
- Với session, cần session fixation protection, timeout, invalidation và cấu hình cookie như **Secure**, **HttpOnly**, **SameSite**.

## 10. Chọn phương án nào cho tình huống thực tế?

Không có một mặc định hoàn hảo cho mọi client. Hãy chọn dựa trên **nguồn credential**, **đường biên tin cậy**, **độ phức tạp vận hành** và **cách đăng xuất/thu hồi**.

| Tình huống | Hướng phù hợp để cân nhắc | Lý do và việc cần xử lý |
| --- | --- | --- |
| Website server-rendered, cùng origin | **Form login + session cookie** | Hợp với browser, logout/session management rõ; quản lý CSRF và cookie |
| Web SPA với backend riêng | **OAuth2 Authorization Code + PKCE**, cân nhắc **BFF** | Cân nhắc giữ token ở backend với session cookie HttpOnly, quản lý CSRF/XSS/CORS |
| Mobile client gọi API | **OAuth2 access token** | Phù hợp client có quy trình cấp/refresh token, lưu token an toàn và scope/audience |
| Service-to-service | **OAuth2 client credentials, workload identity hoặc mTLS** | Danh tính dịch vụ, credential rotation, scope và audit |
| Công cụ nội bộ ít endpoint | **Basic qua HTTPS** có thể dùng trong hoàn cảnh kiểm soát | Đơn giản nhưng gửi password theo request, rotation và client storage cần chú ý |
| Hệ thống cần thu hồi quyền rất nhanh | **Session hoặc opaque token/introspection**, hay JWT thời hạn ngắn + biện pháp bổ sung | Xem xét chi phí lookup, caching và consistency |
| API có nhiều vùng tài nguyên/tenant | **Bất kỳ cơ chế xác thực phù hợp + resource authorization** | Session/JWT không tự chứng minh người dùng được đọc resource cụ thể |

**BFF (Backend for Frontend)** là mẫu thường dùng: browser giữ **session cookie** với BFF; BFF thực hiện OAuth2, giữ token phù hợp và dùng **access token** để gọi API phía sau. Hệ thống như vậy **dùng cả session lẫn token** ở các ranh giới khác nhau. Đây không phải sự mâu thuẫn: mỗi tầng có nhiệm vụ và threat model riêng.

### 10.1. Quy trình đưa ra quyết định

1. **Xác định client:** browser cùng origin, SPA, mobile, command-line, service hoặc đối tác.
2. **Xác định ranh giới tin cậy:** credential đi qua những domain, reverse proxy, gateway, frontend/backend nào?
3. **Xác định yêu cầu xác thực:** username/password, OAuth2, enterprise SSO, API key, workload identity hay mTLS?
4. **Xác định cách duy trì đăng nhập:** session store, token local validation, introspection hoặc BFF.
5. **Xác định yêu cầu quyền:** roles, scopes, resource ownership, tenant và chính sách khi thiếu quyền.
6. **Xác định mức độ thu hồi nhanh:** logout, khóa tài khoản, token compromise, làm mới authorities.
7. **Xác định rủi ro browser:** CSRF, XSS, CORS, SameSite, token storage.
8. **Định nghĩa các test âm:** không credential, credential sai, sai audience, token hết hạn, session không tồn tại, sai tenant, truy cập API bằng cookie web khi không được hỗ trợ.

Tài liệu kiến trúc nên mô tả **cụ thể**: “API /api/** dùng Bearer JWT đã xác minh, không đọc HttpSession”, hoặc “/web/** dùng session cookie và CSRF”, thay vì chỉ ghi “đây là REST API nên stateless”.

## 11. Các ngộ nhận thường gặp và cách sửa

**Ngộ nhận 1 — “REST bắt buộc JWT.”**  
REST không quy định một token format. JWT là công cụ có ưu và nhược điểm riêng. Chọn nó chỉ khi thực sự phù hợp cơ chế xác thực/ủy quyền, kiểm tra chữ ký/claims và phân phối khóa.

**Ngộ nhận 2 — “Session cookie làm HTTP không còn hoạt động.”**  
HTTP vẫn dùng request/response bình thường. Tuy nhiên request phụ thuộc vào session phía server khác với ràng buộc stateless nghiêm ngặt của REST. Phân biệt giao thức và phong cách kiến trúc.

**Ngộ nhận 3 — “STATELESS nghĩa là server không lưu dữ liệu.”**  
Spring Security STATELESS không dùng HttpSession để lấy SecurityContext. Server vẫn lưu đơn hàng, tài khoản, audit, resource state và có thể dùng database/cache phục vụ các mục đích khác.

**Ngộ nhận 4 — “JWT không có state.”**  
JWT ký có thể kiểm chứng local nhưng vẫn cần kế hoạch refresh token, logout, revocation, rotation key, danh sách session hoặc trạng thái account. Phần JWT tự xác minh không chứng minh *toàn hệ thống* không có state.

**Ngộ nhận 5 — “Token an toàn hơn cookie.”**  
So sánh cần nêu rõ **token format**, **nơi lưu**, **cách vận chuyển**, **lifetime**, **scope**, **XSS/CSRF** và **khả năng thu hồi**. JWT trong localStorage và session cookie HttpOnly có bề mặt rủi ro khác nhau; không có kết luận tuyệt đối.

**Ngộ nhận 6 — “API stateless thì tắt CSRF là đúng.”**  
CSRF liên quan đến cách browser tự đính kèm credential. Browser có thể tự gửi cookie hoặc credential HTTP auth. Chỉ thiết kế CSRF exemptions khi đã đánh giá đúng client và credential.

**Ngộ nhận 7 — “Nếu dùng session thì phải dùng form login ở mọi endpoint.”**  
Một ứng dụng có thể có nhiều SecurityFilterChain, ví dụ web-session cho UI và Basic/Bearer cho API. Cần matcher đúng và kiểm thử hai cơ chế không vô tình thay thế nhau.

**Ngộ nhận 8 — “Có Authorization header là đã có quyền.”**  
Đó chỉ là nơi mang credential. Server còn phải xác minh danh tính, issuer/audience/expiry nếu là token, và các quyền/ownership cụ thể.

**Ngộ nhận 9 — “Không lưu session nên không cần kiểm tra tenant.”**  
Authentication và authorization là hai công việc khác nhau. Stateless API vẫn có thể lộ tài nguyên nếu chỉ kiểm tra role chung rồi cho phép truy cập ID bất kỳ.

**Ngộ nhận 10 — “Opaque token không dùng được cho API stateless.”**  
Opaque token có thể được gửi trong từng request và kiểm tra bằng introspection. Resource server phụ thuộc trạng thái token ở một dịch vụ khác; điều đó khác với việc giữ client conversational session trong chính ứng dụng. Hãy mô tả đặc tính cụ thể thay vì suy luận từ nhãn token.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một API trả JSON và nhận **JSESSIONID** từ browser. Có gọi API đó là “REST API” được không?

**Gợi ý đáp án:** Trong giao tiếp ngành phần mềm, người ta vẫn có thể gọi như vậy để nói về HTTP resource endpoints. Nhưng nếu đánh giá **REST statelessness nghiêm ngặt**, việc dựa vào ngữ cảnh xác thực lưu trong HttpSession là một phụ thuộc state phía server cần thừa nhận.

**Câu 2.** Spring Security đặt **SessionCreationPolicy.STATELESS** thì request có **SecurityContext** không?

**Đáp án:** Vẫn có ngữ cảnh bảo mật trong quá trình xử lý request khi cơ chế xác thực tạo ra Authentication. STATELESS điều chỉnh việc dùng HttpSession để lưu/đọc context qua các request; không xóa nhu cầu SecurityContext trong request hiện tại.

**Câu 3.** Vì sao JWT có thể xác minh không cần lookup session nhưng hệ thống dùng JWT vẫn có state?

**Đáp án:** Bản thân chữ ký/claims JWT có thể được xác minh local, song hệ thống vẫn quản lý tài khoản, quyền, refresh token, khóa ký và có thể dùng revocation/denylist. “Token tự chứa” không đồng nghĩa toàn hệ thống không lưu trạng thái.

**Câu 4.** Browser đã login form rồi gửi **JSESSIONID** sang **/api/me** ở ví dụ hai chain. API có tự đăng nhập thành alice không?

**Đáp án:** Không. API chain dùng **STATELESS** và **HTTP Basic**, không đọc session web để phục hồi SecurityContext. Request API cần credential phù hợp.

**Câu 5.** Một web app dùng cookie HttpOnly chứa JWT có thể bỏ qua CSRF không?

**Đáp án:** Không suy ra được. Cookie có thể được browser tự gửi; cần đánh giá CSRF như với credential tự đính kèm. HttpOnly chủ yếu hạn chế JavaScript đọc cookie.

**Câu 6.** Một service-to-service API không có browser nên chọn session hay JWT?

**Đáp án:** Phải xét threat model, identity provider, credential rotation, quyền và revocation. OAuth2 client credentials, mTLS hoặc workload identity thường đáng cân nhắc; REST không tự chọn thay cho bạn.

**Câu 7.** Database vẫn lưu đơn hàng, API có thể đáp ứng ràng buộc stateless không?

**Đáp án:** Có. Đơn hàng là **resource state**, khác **client conversational state**. Từng request vẫn có thể chứa thông tin cần thiết để thao tác trên tài nguyên.

**Câu 8.** API trả 401 khi không có Basic header và website trả 302 về /login. Vì sao?

**Đáp án:** Hai chain có **AuthenticationEntryPoint** khác nhau: HTTP Basic thường challenge bằng 401, form login thường redirect. Status phát sinh từ cơ chế xác thực/điều hướng, không phải nhãn “REST”.

## Tài liệu chính thức

- Roy Fielding, **Architectural Styles and the Design of Network-based Software Architectures**, chương 5, REST: https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm
- HTTP Semantics, **RFC 9110**: https://www.rfc-editor.org/rfc/rfc9110.html
- HTTP State Management Mechanism, **RFC 6265**: https://www.rfc-editor.org/rfc/rfc6265.html
- OAuth 2.0 Bearer Token Usage, **RFC 6750**: https://www.rfc-editor.org/rfc/rfc6750.html
- Spring Security — **Session Management**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — **Java Configuration / Multiple HttpSecurity**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **OAuth2 Resource Server**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html

**Ý tưởng cần giữ:** **REST đặt ra ràng buộc về cách các request hoạt động, còn session hay token là quyết định thiết kế hệ thống xác thực.** Muốn tuân thủ REST statelessness nghiêm ngặt thì tránh phụ thuộc vào client session state phía server; muốn vận hành một web/API an toàn thì phải chọn đúng cơ chế credential, quản lý vòng đời của nó và kiểm tra quyền trên từng tài nguyên.
