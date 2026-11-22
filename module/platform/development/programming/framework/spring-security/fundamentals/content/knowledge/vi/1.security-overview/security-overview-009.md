# Kiến thức đầu vào và trình tự học Spring Security: từ cấu hình nhỏ đến luồng xử lý hoàn chỉnh

## 1. Mục tiêu học tập và phạm vi

Bài này trả lời hai câu hỏi: **cần biết gì trước khi học Spring Security?** và **nên học theo thứ tự nào để đi từ một cấu hình bảo mật nhỏ đến việc giải thích được toàn bộ quá trình xử lý request?**

Đích đến không chỉ là viết được một cấu hình cho phép hoặc từ chối URL. Sau lộ trình, người học có thể:

1. Đọc một HTTP request và phân biệt dữ liệu xác thực, session, token, phương thức HTTP và mã phản hồi.
2. Hiểu Spring Boot tạo ứng dụng web, Controller, Bean và hệ thống Servlet Filter như thế nào.
3. Phân biệt **authentication (xác thực)**, **authorization (phân quyền)**, role/authority và kiểm tra quyền sở hữu dữ liệu.
4. Viết được một **SecurityFilterChain** tối thiểu, tạo tài khoản thử, dùng **PasswordEncoder** và xác định URL nào được phép truy cập.
5. Lần theo một request từ client qua filter, SecurityContext, kiểm tra quyền, Controller đến response.
6. Dùng các trường hợp có và không có quyền để kiểm tra cấu hình; nhận biết vì sao có phản hồi 200, 401, 403 hoặc chuyển hướng đăng nhập.
7. Biết khi nào nên học tiếp về CSRF, session, OAuth2/OIDC, Bearer token, method security và kiểm tra bảo mật.

Ví dụ thực hành sử dụng **Java 17+**, **Spring Boot 3.x**, **Spring Security 6.x** trên **Spring MVC/Servlet**. WebFlux có mô hình reactive và cấu hình bảo mật riêng; không áp dụng trực tiếp mã HttpSecurity của Servlet cho WebFlux.

## 2. Những kiến thức cần có trước khi bắt đầu

Không nhất thiết phải là chuyên gia Java hay Spring. Tuy nhiên, các kiến thức dưới đây đủ để người học không phải đoán cách framework hoạt động.

| Nhóm | Cần hiểu được | Bài tự kiểm tra nhỏ |
| --- | --- | --- |
| Java cơ bản | Class, interface, constructor, method, exception, annotation, lambda | Đọc được hàm tạo Bean và một lambda cấu hình |
| Spring Core | IoC container, Bean, dependency injection, @Configuration, @Bean, component scanning | Giải thích vì sao Controller nhận được Service do Spring quản lý |
| Spring Boot | Starter, auto-configuration, application entry point, cấu hình dependency | Hiểu chuyện gì xảy ra khi thêm starter vào classpath |
| Spring MVC | @RestController, @GetMapping, @PostMapping, DispatcherServlet | Tạo endpoint GET trả về một chuỗi |
| Servlet | Filter, ServletRequest/Response, chuỗi filter trước Controller | Vẽ được vị trí filter nằm trước DispatcherServlet |
| HTTP | GET/POST, URL, status 200/401/403/404, header Authorization | Phân biệt thiếu credentials với thiếu quyền |
| Web state | Cookie, session, HTTPS; khái niệm Bearer token | Biết trình duyệt có thể tự gửi cookie theo request |
| Bảo mật cơ bản | Authentication, authorization, password hashing, least privilege | Giải thích vì sao đăng nhập thành công vẫn có thể bị 403 |
| Công cụ | JDK, Gradle/Maven, curl hoặc Postman, log ứng dụng | Chạy được ứng dụng Boot và gửi request có header |

### 2.1. Chốt bốn khái niệm trước khi viết code

- **Authentication:** Xác minh ai đang gửi request. Kết quả thường được biểu diễn bởi một đối tượng **Authentication**.
- **Authorization:** Xác định danh tính đã biết được phép thực hiện hành động nào. Có thể phân quyền theo URL, HTTP method, role, authority hoặc dữ liệu nghiệp vụ.
- **Principal:** Danh tính hiện hành, ví dụ username hoặc một đối tượng user đã xác thực.
- **Authorities:** Tập các quyền/nhãn quyền được gắn cho Authentication. Với cách cấu hình thông thường, **hasRole("ADMIN")** kiểm tra authority **ROLE_ADMIN**.

Ví dụ: tài khoản **learner** đăng nhập thành công, có quyền **ROLE_USER**. Khi gọi endpoint yêu cầu ADMIN, **authentication thành công nhưng authorization từ chối**. Ngược lại, người chưa đăng nhập gọi endpoint riêng tư có thể bị yêu cầu xác thực trước khi đến Controller.

### 2.2. Hiểu HTTP trước khi nhìn cấu hình security

Một HTTP request có method, URL, headers và có thể có body. Ví dụ:

~~~http
GET /me HTTP/1.1
Host: localhost:8080
Authorization: Basic bGVhcm5lcjpsZWFybjEyMw==
~~~

Header **Authorization: Basic** mang giá trị Base64 của username và password trong ví dụ học tập. **Base64 không phải mã hóa bảo mật**; Basic Authentication chỉ nên truyền qua **HTTPS** khi giao tiếp qua mạng thật.

Trên phương diện kết quả:

- **200 OK:** Request hợp lệ, được xử lý thành công.
- **401 Unauthorized:** Cần thông tin xác thực hợp lệ, thường đi kèm header yêu cầu xác thực theo cơ chế đang dùng.
- **403 Forbidden:** Request không được phép theo chính sách hiện hành; thường là đã xác thực nhưng không đủ quyền, cũng có thể vì thiếu CSRF token.
- **302 Redirect:** Với form login, request chưa đăng nhập có thể được chuyển đến trang login; không phải mọi cấu hình đều trả 401.
- **404 Not Found:** Ứng dụng không có resource/handler phù hợp, sau khi các lớp xử lý trước đó cho request đi tiếp.

Đừng đoán mã phản hồi chỉ dựa vào URL. Luồng xác thực, authorization entry point và exception handler quyết định kết quả.

## 3. Sơ đồ tư duy: từ HTTP đến nghiệp vụ

Bắt đầu bằng sơ đồ đơn giản này trước khi xem các interface trong framework:

~~~text
                         SPRING MVC / SERVLET
Client / curl
    |
    | HTTP request (path, method, headers, cookie/token)
    v
Servlet container (ví dụ Tomcat)
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    v
SecurityFilterChain phù hợp với request
    |-- SecurityContext và các filter liên quan
    |-- Xác thực credentials nếu cần
    |-- Kiểm tra CSRF khi áp dụng
    |-- Quyết định phân quyền
    |       |
    |       +--> Không hợp lệ: 401 / 403 / redirect
    v
DispatcherServlet
    |
    v
Controller -> Service -> Repository
    |
    v
HTTP response
~~~

Đây là **sơ đồ khái quát**, không khẳng định thứ tự chính xác của mọi filter trong mọi cấu hình. Việc chọn một SecurityFilterChain phụ thuộc request matcher và thứ tự các chain được khai báo.

Những thành phần cần hiểu theo thứ tự:

1. **SecurityFilterChain:** Danh sách security filters áp dụng cho request. Cấu hình HttpSecurity tạo ra một chain cho stack Servlet.
2. **AuthenticationManager/AuthenticationProvider:** Thực hiện việc kiểm tra credentials theo cơ chế xác thực phù hợp. Với username/password, provider có thể đọc user từ UserDetailsService và kiểm tra password đã hash.
3. **SecurityContext:** Chứa Authentication hiện hành, giúp các bước kiểm tra tiếp theo biết principal và authorities.
4. **Authorization:** So sánh Authentication và chính sách truy cập để cho đi tiếp hoặc từ chối.
5. **Controller/Service:** Chỉ được gọi khi request đã vượt qua các yêu cầu bảo mật của chain; tầng nghiệp vụ có thể còn phải kiểm tra quyền sở hữu tài nguyên.

**Điểm quan trọng:** Spring Security không chỉ “chạy trong Controller”. Với Servlet, phần lớn quyết định truy cập HTTP xảy ra ở **filter chain trước Controller**; method security có thể bổ sung một lớp kiểm tra gần nghiệp vụ hơn.

## 4. Lộ trình học từng nấc, từ nhỏ đến hoàn chỉnh

| Nấc | Việc cần làm | Học được điều gì | Tiêu chí hoàn thành |
| --- | --- | --- | --- |
| 0. Spring MVC cơ bản | Tạo GET /public và GET /me | Request đi đến Controller như thế nào | Gọi API và nhận 200 |
| 1. Thêm dependency | Cài starter-security, quan sát mặc định | Auto-configuration có thể bảo vệ endpoint ra sao | Nhận ra API bị yêu cầu đăng nhập |
| 2. Quy tắc URL | Khai báo SecurityFilterChain với permitAll, authenticated, hasRole | Authorization được mô tả bằng policy | Dự đoán chính xác endpoint nào được phép |
| 3. Danh tính thử | Cấu hình PasswordEncoder và UserDetailsService | Dữ liệu tài khoản, roles và quá trình xác thực | User hợp lệ gọi /me thành công |
| 4. Bài kiểm thử nhỏ | Thử anonymous, sai mật khẩu, USER, ADMIN | Phân biệt 200, 401, 403 | Kết quả phù hợp bảng test |
| 5. Truy vết request | Đi từng bước từ Basic header qua filter đến Controller | Kết nối các cấu phần thành một luồng | Vẽ được flow và chỉ ra điểm từ chối |
| 6. Quyền nghiệp vụ | Thêm điều kiện sở hữu tài nguyên tại Service | Vì sao role không đủ cho tất cả dữ liệu | User A không xem được dữ liệu B |
| 7. Web security | Học CSRF, session/cookie, CORS, HTTPS và headers | Chọn biện pháp phù hợp kiểu client | Không vô tình tắt lớp bảo vệ cần thiết |
| 8. Kiến trúc thật | Học OAuth2/OIDC, Resource Server/JWT, method security, test | Tách demo ra khỏi cấu hình production | Giải thích được vai trò của từng thành phần |

Không cần học hết OAuth2, JWT hay tạo một hệ thống SSO ngay ở nấc 1. Mỗi nấc nên tạo thêm **một quan sát mới**: ban đầu thấy Controller chạy, sau đó thấy request bị chặn, tiếp theo thấy user đúng được phép, cuối cùng giải thích được từng quyết định.

### Nấc 0 — Có một ứng dụng HTTP đơn giản

Trước khi thêm Spring Security, hãy bảo đảm:

- Ứng dụng Boot khởi động và lắng nghe cổng 8080.
- Một Controller có thể trả về chuỗi ở /public.
- Bạn biết cách xem HTTP status bằng curl với tùy chọn **-i**.
- Bạn hiểu Controller thuộc luồng xử lý Spring MVC; Bean được tạo và quản lý trong Spring container.

Nếu chưa làm được, hãy ôn Spring Boot, dependency injection và mapping URL. Lỗi ở bước tạo Bean hoặc endpoint không phải lỗi của Spring Security.

### Nấc 1 — Thêm starter và quan sát mặc định

Trong một dự án Spring Boot 3.x sử dụng Gradle Groovy DSL, có các dependency sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Khi starter-security có mặt và ứng dụng chưa có cấu hình bảo mật tùy biến, Boot thường bảo vệ các endpoint bằng thiết lập mặc định, cung cấp user thử với mật khẩu ngẫu nhiên trong log khởi động. Đó là **hành vi phát triển ban đầu**, chưa phải hệ thống đăng nhập được thiết kế cho production.

Hãy tự trả lời: tại sao cùng một Controller, khi chưa có security thì có thể gọi thẳng, nhưng sau khi thêm dependency lại cần đăng nhập? Trả lời được câu này là hiểu tác động của auto-configuration lên request.

### Nấc 2 — Viết chính sách truy cập nhỏ nhất

Đầu tiên chọn ba nhu cầu rõ ràng:

- **GET /public**: người chưa đăng nhập cũng truy cập được.
- **GET /me**: chỉ danh tính đã được xác thực.
- **GET /admin**: chỉ danh tính có role ADMIN.
- Mọi endpoint khác: từ chối mặc định.

Tại sao bắt đầu bằng ba trường hợp? Vì chúng cho phép quan sát trực tiếp sự khác nhau giữa **permitAll**, **authenticated** và **hasRole**, trước khi hệ thống có nhiều role, nguồn dữ liệu hoặc cơ chế token.

### Nấc 3 — Có danh tính để thực sự kiểm tra

Tạo hai tài khoản **chỉ phục vụ demo**:

| Username | Password demo | Authority từ cấu hình roles | Quyền quan sát |
| --- | --- | --- | --- |
| learner | learn123 | ROLE_USER | Gọi /me, không được /admin |
| admin | admin123 | ROLE_ADMIN | Gọi /me và /admin |

Cấu hình **UserDetailsService** trả về hai tài khoản trong bộ nhớ; **PasswordEncoder** chịu trách nhiệm băm và kiểm tra password. Đây là cách quan sát authn/authz dễ nhất. Với ứng dụng thật, không hard-code username/password, không dùng tài khoản demo và không dựa vào in-memory store như một hệ thống quản lý người dùng đầy đủ.

### Nấc 4 — Chỉ sau khi có test mới đi sâu vào filters

Với mỗi endpoint, thử tối thiểu bốn góc nhìn: anonymous, mật khẩu sai, USER hợp lệ, ADMIN hợp lệ. Khi bảng kết quả ổn định, hãy chọn **một request cụ thể**, lần theo cách Spring Security nhận credentials, xác thực, ghi Authentication vào SecurityContext và so sánh authorities.

Đây là lúc các class trong framework có ý nghĩa: chúng giải thích một hiện tượng bạn đã nhìn thấy qua HTTP.

## 5. Ví dụ chạy được: kết nối cấu hình và request

**Giả định:** Dự án Spring Boot 3.x, Java 17+ đã tạo bằng Spring Initializr hoặc được cấu hình plugin Boot tương đương; có hai starter ở nấc 1 và Gradle Wrapper. Ví dụ sau là **toàn bộ file Java**, không phải các đoạn rời cần ghép thủ công.

Tạo file **src/main/java/com/example/securitypath/SecurityPathApplication.java**:

~~~java
package com.example.securitypath;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityPathApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityPathApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    String currentUser(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

**Vì sao đoạn mã này là một bước tiến có kiểm soát:**

1. **SecurityPathApplication** là entry point Spring Boot. **DemoController** nằm cùng package nên được component scan phát hiện.
2. Bean **SecurityFilterChain** định nghĩa chính sách HTTP. Chỉ GET được cho phép theo các matcher ghi rõ; các request còn lại đi tới **denyAll**.
3. **httpBasic** cho phép đưa username/password vào header khi thử bằng curl. **formLogin** được tắt có chủ đích trong demo để quan sát mã 401 thay vì bị chuyển hướng đến trang đăng nhập.
4. **InMemoryUserDetailsManager** giữ hai user thử. **roles("USER")** tạo authority **ROLE_USER**, tương tự **ROLE_ADMIN** cho admin.
5. **BCryptPasswordEncoder** băm mật khẩu trước khi tạo user. Việc dùng string rõ trong mã chỉ nhằm minh họa và tuyệt đối không phải cách lưu mật khẩu production.
6. **CSRF vẫn giữ cấu hình mặc định.** Ba endpoint đều GET, vì vậy không phải vô hiệu hóa CSRF để thử chúng. Không dùng GET cho thao tác thay đổi dữ liệu thật.
7. **Principal** ở endpoint /me cho thấy danh tính hiện hành đã được xác thực và truyền đến tầng MVC. Nếu client không hợp lệ, request bị từ chối trước khi phương thức này chạy.

Chạy ứng dụng tại thư mục gốc project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell, dùng **.\gradlew.bat bootRun**. Với Maven, dùng lệnh Boot tương ứng của dự án. Các request bên dưới giả định server đang chạy trên **http://localhost:8080** chỉ để học tập trên máy cá nhân.

Thử từng trường hợp bằng curl:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u learner:wrong http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/me
curl -i -u learner:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Trên PowerShell có thể dùng **curl.exe** để tránh alias của shell. Không gửi credentials thật tới endpoint không dùng HTTPS.

**Bảng kết quả mong đợi** với đúng cấu hình demo:

| Request | Kết quả | Điều được kiểm chứng |
| --- | --- | --- |
| GET /public, không đăng nhập | 200, body **public OK** | permitAll hoạt động |
| GET /me, không đăng nhập | 401 | Endpoint đòi authentication |
| GET /me, learner + mật khẩu sai | 401 | Credentials phải được xác minh |
| GET /me, learner hợp lệ | 200, body **hello learner** | Có danh tính, đủ quyền authenticated |
| GET /admin, learner hợp lệ | 403 | Authn thành công nhưng thiếu ROLE_ADMIN |
| GET /admin, admin hợp lệ | 200, body **admin OK** | Có ROLE_ADMIN nên vượt qua authorization |

Các dòng trên là **kỳ vọng được suy ra từ cấu hình**, không phải kết quả đo từ một server đã chạy trong bài này. Nếu có security chain khác, cấu hình exception handler khác, reverse proxy, context path hoặc chính sách endpoint khác, phản hồi thực tế có thể thay đổi.

## 6. Một request cụ thể đi hết đường như thế nào?

Dùng request **GET /admin** của tài khoản **learner** làm ví dụ. Nó rất có giá trị vì giúp thấy rõ điểm **xác thực thành công nhưng phân quyền thất bại**.

~~~text
curl -u learner:learn123 GET /admin
  |
  v
Tomcat -> DelegatingFilterProxy -> FilterChainProxy
  |
  v
SecurityFilterChain có các filter liên quan
  |
  +-- Nhận Basic Authorization header
  |     |
  |     +-- Giải mã credentials
  |     +-- AuthenticationManager / AuthenticationProvider
  |     +-- UserDetailsService tìm "learner"
  |     +-- PasswordEncoder kiểm tra mật khẩu
  |     +-- Thành công: Authentication(principal=learner, ROLE_USER)
  |
  +-- SecurityContext giữ Authentication hiện hành
  |
  +-- Authorization đối chiếu GET /admin -> hasRole("ADMIN")
  |     |
  |     +-- Có ROLE_USER, thiếu ROLE_ADMIN -> từ chối
  |
  v
403 Forbidden
(Controller /admin không được gọi)
~~~

**Trường hợp 1 — không có credentials:** Không có Authentication hợp lệ để truy cập endpoint yêu cầu đăng nhập. Với HTTP Basic như demo, framework kích hoạt authentication entry point và trả **401**, thường cùng header **WWW-Authenticate**.

**Trường hợp 2 — credentials sai:** Bước xác minh username/password thất bại, vì vậy không tạo một danh tính hợp lệ để được vào /me. Kết quả với Basic là **401**.

**Trường hợp 3 — learner truy cập /me:** Authentication được xác minh, principal là learner. Matcher /me yêu cầu **authenticated()**, nên Controller chạy và trả **hello learner**.

**Trường hợp 4 — learner truy cập /admin:** Xác thực hoàn tất nhưng yêu cầu role ADMIN không được đáp ứng. Framework xử lý lỗi truy cập và trả **403**; Controller không chạy.

**Trường hợp 5 — admin truy cập /admin:** Authentication có **ROLE_ADMIN** nên authorization cho phép request đi tiếp đến DispatcherServlet và Controller; trả **admin OK**.

Trong stack Servlet, **SecurityContextHolder** là điểm truy cập quen thuộc tới SecurityContext đang áp dụng. Cơ chế lưu và truyền ngữ cảnh phụ thuộc cách cấu hình, request, session và kiểu thực thi; không suy diễn rằng ThreadLocal sẽ tự truyền đúng qua mọi tác vụ bất đồng bộ. Trong WebFlux, reactive security context sử dụng cơ chế khác.

### Quy tắc đọc log và debug

Khi một request thất bại, hãy xác định **nó dừng ở chặng nào**:

1. Ứng dụng có khởi động và đăng ký endpoint không?
2. Request đã đi qua security chain nào, có matcher phù hợp không?
3. Có credentials không, theo đúng schema Basic, session hoặc Bearer không?
4. Authentication thành công hay thất bại? User có đúng authorities được yêu cầu không?
5. Có CSRF hoặc chính sách khác từ chối trước khi đến Controller không?
6. Nếu tới Controller/Service rồi, có còn kiểm tra permission nghiệp vụ và xử lý exception nào không?

Trong môi trường phát triển, có thể bật logging cho namespace Spring Security để quan sát filter và quyết định truy cập, nhưng phải kiểm soát độ chi tiết và tránh ghi credentials, tokens hoặc thông tin cá nhân vào log.

## 7. Mở rộng từ quyền URL sang quyền nghiệp vụ

Một ứng dụng thực tế thường cần nhiều hơn **hasRole("USER")**. Ví dụ API **GET /orders/123** yêu cầu user đã đăng nhập. Nếu order 123 thuộc tài khoản khác, cho phép mọi USER đọc nó sẽ dẫn đến lỗi kiểm soát truy cập dữ liệu (IDOR/BOLA).

Vì vậy nên đi theo hai tầng kiểm tra:

1. **Tầng HTTP:** Request phải đã được xác thực, đúng method và thuộc URL được phép.
2. **Tầng nghiệp vụ:** Service tải đơn hàng rồi đối chiếu owner của đơn với principal hiện hành, trừ khi chính sách cho phép role quản trị đọc đơn đó.

Không so sánh với ownerId do client tự khai trong request. Dữ liệu sở hữu phải đến từ nguồn đáng tin như database; principal phải đến từ Authentication đã được xác minh.

Với method security, có thể bật **@EnableMethodSecurity** và dùng **@PreAuthorize** cho những kiểm tra phù hợp. Cần hiểu rằng việc gọi method qua Spring proxy, cách đặt annotation và quyền truy cập dữ liệu đều ảnh hưởng tính đúng đắn. Một biểu thức role ở method không tự thay thế kiểm tra owner trên bản ghi.

Khi luyện tập, thêm hai tài khoản USER riêng với dữ liệu độc lập; yêu cầu USER A không đọc được bản ghi của USER B. Kiểm thử **negative case** này quan trọng không kém kiểm thử ADMIN có thể làm đúng việc.

## 8. Những chủ đề nên học tiếp theo và thứ tự hợp lý

### 8.1. CSRF, session và cookie

Website dùng **session + cookie** thường để trình duyệt tự gửi cookie ở các request sau. Điều này giúp duy trì phiên nhưng có rủi ro **CSRF** khi trang khác kích hoạt request thay đổi trạng thái. Spring Security có cơ chế CSRF token trong stack Servlet. Hãy học cách CSRF bảo vệ các HTTP method không an toàn trước khi quyết định có điều chỉnh hoặc tắt nó trong kiến trúc của mình.

Kiểm tra thêm cookie flags (**Secure**, **HttpOnly**, **SameSite**), session fixation, logout, timeout và HTTPS. CORS điều khiển quyền truy cập response cross-origin của trình duyệt; **CORS không thay thế CSRF, authentication hoặc authorization**.

### 8.2. Resource Server và Bearer token

Khi client đưa **Bearer access token** tới API, Spring Security có thể kiểm tra token qua cấu hình OAuth2 Resource Server. Với JWT, cần xác minh chữ ký, issuer, audience, thời hạn và ánh xạ claims thành authorities đúng chính sách.

**JWT là định dạng token**, không phải một hệ thống đăng nhập hoàn chỉnh. Chỉ thêm starter-security không tự phát hành JWT, thiết lập refresh token, thu hồi token hay bảo vệ quyền sở hữu tài nguyên.

### 8.3. OAuth2 và OpenID Connect

OAuth2 là hệ thống các chuẩn cấp quyền ủy thác; **OIDC** xây trên OAuth2 để cung cấp lớp xác thực danh tính. Ở mức nền tảng, hãy phân biệt:

- **Client:** Ứng dụng dùng OAuth2/OIDC để yêu cầu quyền hoặc đăng nhập.
- **Authorization Server / Identity Provider:** Thành phần cấp token và thực hiện các bước xác thực/ủy quyền liên quan.
- **Resource Server:** API nhận và kiểm tra access token trước khi trả dữ liệu.
- **ID Token:** Chứa thông tin danh tính trong OIDC; không tự thay thế access token để gọi API.

Học cấu trúc vai trò trước; sau đó mới triển khai flow cụ thể cho browser, mobile hoặc service-to-service.

### 8.4. Method security và nhiều filter chain

Sau khi hiểu một SecurityFilterChain, học cách cấu hình nhiều chain cho các phạm vi request khác nhau, chính sách method-level với @EnableMethodSecurity, và các tương tác với exception handling. Đặc biệt chú ý **securityMatcher**, **requestMatchers**, thứ tự chain và deny-by-default để không vô tình bỏ sót endpoint.

## 9. Những lỗi hay khiến người mới học lệch hướng

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm chứng |
| --- | --- | --- |
| Mọi endpoint đều yêu cầu đăng nhập | Mới thêm starter, đang dùng bảo mật mặc định | Kiểm tra có SecurityFilterChain tùy biến chưa |
| GET /public vẫn bị chặn | Matcher không đúng path/method hoặc chain khác được chọn | Kiểm tra context path, matcher và thứ tự chains |
| /me trả 401 dù đã tạo user | Sai credentials, password encoder hoặc kiểu Authorization header | Thử HTTP Basic với tài khoản đã cấu hình |
| /admin trả 403 với USER | Đã xác thực nhưng thiếu authority ROLE_ADMIN | Kiểm tra hasRole và authorities |
| Đăng nhập từ browser trả redirect thay vì 401 | Form login/entry point khác HTTP Basic | Kiểm tra cơ chế đăng nhập được cấu hình |
| POST trả 403 dù role đúng | Có thể thiếu CSRF token hoặc còn chính sách khác | Xác minh CSRF và request method trước khi thay đổi |
| Ứng dụng có role nhưng lộ dữ liệu user khác | Thiếu kiểm tra owner ở tầng Service/Repository | Thử truy cập chéo dữ liệu giữa hai USER |
| Boot không tìm được Controller | Sai package/component scanning hoặc application entry point | Kiểm tra package của @SpringBootApplication |
| Cố dùng HttpSecurity với WebFlux | Nhầm Servlet với reactive stack | Xác định dùng spring-boot-starter-web hay webflux |
| Tưởng Base64 bảo vệ mật khẩu HTTP Basic | Nhầm encoding với encryption | Dùng TLS và không hard-code credentials production |

Không “sửa” một lỗi 403 bằng cách thêm permitAll cho toàn bộ URL hoặc disable CSRF ngay lập tức. Cách đó có thể khiến kiểm thử qua được nhưng làm mất đi mục tiêu bảo vệ ban đầu.

## 10. Bài tập để tự đánh giá đã hiểu trọn luồng

**Bài tập A — dự đoán trước khi chạy:** Viết kết quả cho sáu request trong bảng ở mục 5 mà không tra code. Sau đó chạy thử và đối chiếu. Nếu sai, chỉ ra matcher hoặc bước xác thực tương ứng.

**Bài tập B — thêm một endpoint:** Thêm GET /reports vào Controller nhưng chưa thêm matcher. Hãy dự đoán vì sao nó không tự trở thành public. Tiếp đó cấu hình chỉ ADMIN được xem /reports, thử USER và ADMIN.

**Bài tập C — đổi role:** Đổi role của learner từ USER thành ADMIN trong demo, khởi động lại và dự đoán GET /admin có thay đổi gì. Giải thích bằng authority **ROLE_ADMIN**.

**Bài tập D — đặt quyền ở tầng dữ liệu:** Mô tả luồng GET /orders/123, trong đó user A có role USER nhưng đơn thuộc user B. Hãy chỉ ra bước nào phải đọc owner từ dữ liệu thật và từ chối.

**Bài tập E — mở rộng authentication:** So sánh Basic với session cookie và JWT Bearer. Với mỗi cơ chế, xác định credentials được gửi thế nào, thành phần nào xác minh, nhu cầu lưu session và mối quan tâm CSRF.

Bạn đã hiểu tuyến kiến thức này nếu có thể **tự vẽ flow của một request**, giải thích vì sao nhận 401/403/200, đồng thời nhận ra **quyền URL và quyền trên dữ liệu là hai trách nhiệm bổ sung cho nhau**.

## 11. Tài liệu tham khảo chính thức

- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot — Spring Security: https://docs.spring.io/spring-boot/reference/web/spring-security.html
