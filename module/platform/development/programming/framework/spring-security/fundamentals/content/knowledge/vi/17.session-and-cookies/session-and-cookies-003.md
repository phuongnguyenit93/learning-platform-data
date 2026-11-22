# Phân biệt ngữ cảnh theo yêu cầu với phiên tồn tại qua nhiều yêu cầu

## 1. Câu hỏi cốt lõi

Khi học Spring Security, có một hiện tượng tưởng như mâu thuẫn: **mỗi HTTP request đều có ngữ cảnh bảo mật riêng trong lúc xử lý, nhưng người dùng vẫn đăng nhập một lần và được nhận diện ở các request tiếp theo**. Cơ chế này hoạt động nhờ sự phân biệt giữa hai vòng đời:

- **Ngữ cảnh theo request**: dữ liệu chỉ có ý nghĩa trong lúc server xử lý một yêu cầu HTTP cụ thể, chẳng hạn request attributes, request-scoped bean và SecurityContext đang được gắn vào luồng xử lý hiện tại.
- **Phiên (HTTP session)**: trạng thái phía server có thể tồn tại qua **nhiều HTTP request** của cùng một phiên trình duyệt/client, được liên kết bằng session identifier (thường qua cookie tên JSESSIONID).

**SecurityContext không phải HttpSession.** SecurityContext chứa thông tin Authentication của ngữ cảnh bảo mật hiện hành; HttpSession là một cơ chế lưu trữ trạng thái lâu hơn một request. Trong ứng dụng đăng nhập bằng form truyền thống, Spring Security có thể lưu SecurityContext vào session rồi **nạp lại cho từng request**. Vì vậy, mỗi request có một ngữ cảnh đang hoạt động nhưng trạng thái đăng nhập vẫn được duy trì.

Bài này giúp bạn:

1. Giải thích rõ HTTP request, request scope, SecurityContextHolder, SecurityContext, HttpSession và session cookie.
2. Theo dõi một lần đăng nhập qua ba request liên tiếp.
3. Phân biệt việc **nạp ngữ cảnh**, **lưu ngữ cảnh** và **kết thúc request**.
4. Hiểu khi nào nên dùng phiên server-side và khi nào xác thực lại ở từng request (stateless).
5. Chạy ví dụ Spring Boot 3.x, Java 17+, để quan sát giá trị thay đổi theo request và giá trị tồn tại theo session.
6. Nhận biết các lỗi liên quan session, cookie, CSRF, timeout, ThreadLocal và SecurityContextRepository.

## 2. HTTP là giao thức không tự ghi nhớ phiên đăng nhập

Mỗi HTTP request có method, URL, headers và có thể có body. HTTP không tự bảo đảm rằng hai request liên tiếp thuộc cùng một người dùng. Server phải có một cơ chế liên kết các request, chẳng hạn **cookie phiên**, **Bearer token** hoặc một loại credential khác.

Giả sử client gửi ba request:

~~~http
GET /api/state HTTP/1.1
Host: localhost:8080

GET /api/state HTTP/1.1
Host: localhost:8080

GET /api/state HTTP/1.1
Host: localhost:8080
~~~

Ba request trên là **ba đơn vị xử lý riêng biệt**, dù URL giống nhau. Nếu không có cookie, token hay credential tương ứng thì không thể chỉ dựa vào đường dẫn /api/state để khẳng định chúng đến từ cùng một danh tính đã xác thực.

Trong ứng dụng stateful thông thường, browser bổ sung cookie:

~~~http
GET /api/state HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=example-session-id
~~~

**Giá trị cookie ở trên là minh họa, không phải session ID thật.** Container/ứng dụng dùng ID để tìm phiên server-side. Cookie thường chứa **mã nhận diện phiên**, không chứa nguyên bộ UserDetails/Authentication. Không nên đưa session identifier thật vào bài log, URL, đoạn chat hay response JSON vì người khác có được ID hợp lệ có thể tìm cách chiếm phiên.

### Ba cấp độ trạng thái cần phân biệt

| Đối tượng | Vòng đời | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **HttpServletRequest** | Một request/chuỗi dispatch liên quan | Method, URL, headers, request attributes | Kết thúc request thì không tiếp tục dùng instance đó cho request kế tiếp. |
| **Spring @RequestScope bean** | Một HTTP request | Giá trị đánh dấu request, dữ liệu xử lý tạm | Không tự tồn tại qua request tiếp theo. |
| **SecurityContextHolder** | Ngữ cảnh đang hoạt động; mặc định gắn với thread xử lý Servlet | Truy cập Authentication trong lúc xử lý | Được nạp và dọn theo cơ chế filter; **không** là kho lưu lâu dài giữa các request. |
| **SecurityContext** | Đối tượng chứa Authentication của ngữ cảnh bảo mật | Principal, authorities thông qua Authentication | Có thể được lưu/nạp bằng SecurityContextRepository tùy cấu hình. |
| **HttpSession** | Nhiều request cho tới khi hết hạn hoặc bị hủy | Session attributes, dữ liệu đăng nhập khi được lưu tại đây | Nằm phía server/container hoặc kho phiên được cấu hình. |
| **Spring @SessionScope bean** | Một HTTP session | Tùy chọn UI hoặc dữ liệu demo gắn với phiên | Một phiên dùng lại bean; phiên khác có bean khác. |
| **Session cookie (JSESSIONID thường gặp)** | Trên client theo thuộc tính cookie/browser | Một ID liên kết tới server-side session | Không đồng nghĩa với SecurityContext hay bản thân phiên server-side. |

**Tên "context" có thể chỉ nhiều khái niệm khác nhau.** Request scope của Spring Framework và SecurityContext của Spring Security là hai cơ chế riêng. Cả hai cùng liên quan request đang xử lý, nhưng chỉ SecurityContext chứa thông tin xác thực/phân quyền. Ngược lại, HttpSession có thể chứa nhiều loại dữ liệu, không chỉ security.

## 3. SecurityContextHolder và Authentication hiện hành

Trong Servlet stack, Spring Security cung cấp một cách truy cập danh tính hiện hành qua SecurityContextHolder:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

Đây là **fragment Java cần import**, không phải chương trình chạy độc lập. Các kiểu thuộc package **org.springframework.security.core.context** và **org.springframework.security.core**.

Một SecurityContext chứa Authentication, mà Authentication thường có:

- **principal**: danh tính (ví dụ UserDetails hoặc Jwt).
- **authorities**: tập GrantedAuthority dùng để phân quyền.
- **authenticated**: trạng thái xác thực theo cơ chế đã sử dụng.
- **credentials/details**: thông tin có ý nghĩa trong quá trình xác thực, thường được xử lý để tránh giữ bí mật không cần thiết.

### 3.1. Vì sao SecurityContextHolder không giữ đăng nhập mãi?

Chiến lược mặc định của SecurityContextHolder trên Servlet là **MODE_THREADLOCAL**. Khi request được xử lý trên một worker thread, code trong luồng đó có thể đọc ngữ cảnh bảo mật hiện hành.

Nhưng web server tái sử dụng thread cho nhiều client. Nếu một ThreadLocal chứa danh tính của người A còn sót đến request của người B, đó là lỗi cô lập bảo mật nghiêm trọng. Spring Security filter chain phải quản lý vòng đời ngữ cảnh và **dọn ngữ cảnh khi xử lý request kết thúc** theo cơ chế áp dụng.

~~~text
Thời điểm T1: Thread-X xử lý request của Alice
               SecurityContextHolder -> Alice
               Xử lý xong -> clear/reset context

Thời điểm T2: Thread-X được tái dùng cho request của Bob
               Spring Security nạp/xác thực ngữ cảnh mới -> Bob
               Xử lý xong -> clear/reset context
~~~

**Một thread không đại diện cho một người dùng** và một phiên không bị ràng buộc mãi với một thread. Hai request của cùng người dùng có thể do hai thread khác nhau xử lý; nhiều request đồng thời của cùng một session cũng có thể chạy song song.

Dùng **@AuthenticationPrincipal**, tham số **Authentication** trong Spring MVC, hoặc cách truy cập context được hỗ trợ khi cần lấy danh tính trong ứng dụng. Không lưu Authentication của request hiện hành vào biến **static** hoặc field singleton rồi tái sử dụng cho người khác.

### 3.2. Context của request hiện hành có thể lấy lại từ dữ liệu tồn tại lâu hơn

SecurityContextHolder phục vụ **truy cập ngữ cảnh đang hoạt động**, trong khi **SecurityContextRepository** quyết định cách nạp/lưu SecurityContext qua các thời điểm phù hợp. Với đăng nhập theo phiên, repository thường sử dụng HttpSession.

Lưu ý quan trọng:

- Đầu request: có thể nạp SecurityContext từ repository.
- Trong request: SecurityContextHolder cung cấp Authentication hiện hành.
- Khi đăng nhập thành công: cơ chế xác thực phải bảo đảm SecurityContext được lưu nếu cần duy trì đăng nhập.
- Cuối request: ngữ cảnh đang gắn với thread được dọn.
- Request sau: repository có thể trả lại trạng thái bảo mật đã lưu, và Spring Security gắn nó vào ngữ cảnh xử lý mới.

**Không có nghĩa SecurityContextHolder là cùng một object Java xuyên suốt mọi request**, cũng không có nghĩa bắt buộc mỗi request phải đăng nhập lại nếu hệ thống đã có kho lưu trạng thái xác thực.

## 4. Một vòng đăng nhập theo phiên diễn ra như thế nào?

Giả sử ứng dụng Spring MVC dùng **formLogin** với session persistence:

~~~text
                 Request 1: GET /private
Browser ----------------------------------------------> Server
(Chưa xác thực)                                           |
                                                          | cần đăng nhập
Browser <---------------------------------------------- 302 /login
                 Request 2: GET /login
Browser ----------------------------------------------> trang login
                 Request 3: POST /login + CSRF token
Browser ----------------------------------------------> xác thực username/password
                                                          |
                                                          +--> Authentication thành công
                                                          +--> SecurityContext được lưu
                                                          +--> HttpSession liên kết danh tính
Browser <---------------------------------------------- 302 + cookie phiên (nếu cần)
                 Request 4: GET /private + cookie
Browser ----------------------------------------------> Server
                                                          |
                                                          +--> Tìm HttpSession theo cookie
                                                          +--> SecurityContextRepository
                                                          |    lấy ngữ cảnh đã lưu
                                                          +--> SecurityContextHolder hiện hành
                                                          |    có Authentication tương ứng
                                                          +--> Authorization cho phép
Browser <---------------------------------------------- 200 trang riêng
                                                          |
                                                          +--> Dọn context của thread khi xong
                 Request 5: GET /private + cookie
Browser ----------------------------------------------> Server
                                                          |
                                                          +--> Nạp lại ngữ cảnh cho request mới
Browser <---------------------------------------------- 200 trang riêng
~~~

**Session không phải là request kéo dài vô hạn.** Request 4 và request 5 là hai lần xử lý độc lập. Trạng thái đăng nhập được tái sử dụng vì cùng client gửi thông tin liên kết tới phiên còn hợp lệ, không phải vì ThreadLocal cũ chưa bị xóa.

### 4.1. HttpSession và cookie khác nhau ở đâu?

Theo mô hình Servlet tiêu chuẩn:

- **HttpSession** là phần trạng thái do server/container quản lý (hoặc lưu ở store khác khi tích hợp Spring Session).
- **Cookie JSESSIONID** là một cách thường dùng để client cung cấp mã phiên cho request sau.
- Server tra cứu phiên nhờ ID đó rồi có thể đọc session attributes, bao gồm SecurityContext khi repository được cấu hình lưu tại session.
- Cookie có thể còn nhưng phiên server-side đã hết hạn hoặc bị hủy; khi đó không tự động khôi phục trạng thái đăng nhập cũ.
- Session có thể tồn tại phía server nhưng client không gửi đúng ID; server thường không nhận ra đây là cùng phiên.

Browser tab mới trong cùng profile thường dùng chung cookie phù hợp domain/path và có thể chia sẻ session. Cửa sổ ẩn danh hoặc profile khác thường có kho cookie độc lập. Không giả định **mỗi tab là một session riêng**.

### 4.2. Điều gì xảy ra khi logout?

Với cấu hình logout Servlet phổ biến, logout thành công sẽ làm sạch SecurityContext và vô hiệu hóa HttpSession nếu được cấu hình theo mặc định. Request kế tiếp không còn session bảo mật hợp lệ nên khi vào vùng yêu cầu đăng nhập, browser cần xác thực lại.

Một phiên cũng có thể kết thúc do **timeout**, quản trị viên thu hồi quyền đăng nhập/phiên hoặc server mất trạng thái phiên. Cookie cũ không đủ để xác minh rằng session server-side vẫn còn.

**Session ID có thể thay đổi ngay lúc đăng nhập** nhờ cơ chế bảo vệ **session fixation**. Vì vậy, không thiết kế ứng dụng dựa vào giả định "ID trước và sau đăng nhập luôn giống nhau".

## 5. SecurityContextRepository: cầu nối giữa request hiện tại và lần gọi sau

Trong Spring Security 6.x trên Servlet, repository mặc định thường là **DelegatingSecurityContextRepository**, phối hợp:

- **HttpSessionSecurityContextRepository**: liên kết SecurityContext với HttpSession, phù hợp với việc duy trì authentication qua nhiều HTTP request.
- **RequestAttributeSecurityContextRepository**: lưu context trong request attribute để có thể khôi phục trong các dispatch của **cùng request**, ví dụ ERROR dispatch, chứ **không** dùng để giữ đăng nhập qua những HTTP request độc lập.

Ví dụ:

~~~text
Request A (REQUEST dispatcher)
    |
    +--> SecurityContextHolder / Authentication
    +--> RequestAttributeSecurityContextRepository
    |        |
    |        +--> cùng request khi chuyển sang ERROR dispatcher
    |             vẫn có thể tìm lại context
    |
    +--> HttpSessionSecurityContextRepository
             |
             +--> Request B và C có cùng session hợp lệ
                  có thể nạp authentication đã lưu
~~~

**Hai repository giải quyết hai phạm vi lưu trữ khác nhau.** Tên "request attribute" không có nghĩa đối tượng đó được đưa vào cookie; "HttpSessionSecurityContextRepository" cũng không có nghĩa toàn bộ SecurityContext được gửi về browser.

### 5.1. Spring Security 6 cần chú ý cơ chế lưu context

Với Spring Security 6.x, cơ chế mặc định sử dụng **SecurityContextHolderFilter** để lấy SecurityContext từ SecurityContextRepository và đặt vào SecurityContextHolder. Lựa chọn này thiên về **explicit saving**: bản thân filter **không tự động lưu mọi thay đổi ngữ cảnh vào repository ở cuối request** như cơ chế cũ.

Các authentication filters chuẩn như xử lý form login đã thực hiện lưu trạng thái cần thiết trong luồng thành công. Nhưng nếu bạn viết **custom authentication controller/filter** rồi chỉ làm:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

thì điều đó có thể chỉ làm thay đổi context trong request hiện hành và **chưa đủ để duy trì đăng nhập ở request kế tiếp**.

Đối với luồng tự quản lý và repository đã được cấu hình đúng, cách làm cơ bản là tạo context rồi yêu cầu repository lưu:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Đây là **fragment khái niệm**, không phải controller hoàn chỉnh: cần một Authentication đã được kiểm chứng, SecurityContextRepository phù hợp với chính SecurityFilterChain, HttpServletRequest/HttpServletResponse hiện hành, session authentication strategy và cơ chế xử lý login/logout an toàn. **Không lấy ví dụ này làm hướng dẫn tự tạo đăng nhập mà bỏ qua AuthenticationManager hoặc các biện pháp chống session fixation**.

Nếu chỉ dùng formLogin/OAuth2 login chính thống, thường không cần tự viết thao tác lưu context này; hãy sử dụng authentication mechanism được Spring Security hỗ trợ.

## 6. Ví dụ thực hành: hai loại dữ liệu, hai vòng đời

Một cách trực quan để tách **request lifetime** và **session lifetime** là tạo hai Spring bean:

- **@RequestScope**: một instance phục vụ mỗi HTTP request.
- **@SessionScope**: một instance tồn tại trong vòng đời một HTTP session.

Đây là **cơ chế scope của Spring Framework**, không phải bản thân SecurityContext. Tuy nhiên, kết hợp chúng với formLogin và Authentication hiện hành giúp chứng minh bằng quan sát: một request mới có dữ liệu request-scope mới, trong khi phiên đăng nhập và dữ liệu session-scope có thể được sử dụng lại.

### 6.1. Chuẩn bị dự án

Dùng **Spring Initializr** tạo Spring Boot **3.x**, Java **17+**, Gradle, group **com.example**, artifact **demo**, package **com.example.demo**. Chọn:

- **Spring Web** → spring-boot-starter-web.
- **Spring Security** → spring-boot-starter-security.

Ứng dụng tạo một user thử nghiệm **learner/demo123** và dùng form login mặc định của Spring Security; không cần viết HTML login riêng.

Tạo file:

~~~text
src/main/java/com/example/demo/RequestSessionDemoApplication.java
~~~

### 6.2. Toàn bộ mã Java

~~~java
package com.example.demo;

import java.util.Map;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class RequestSessionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestSessionDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .sessionManagement(session -> session
                    .sessionCreationPolicy(
                        SessionCreationPolicy.IF_REQUIRED))
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/public")
                        .permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/state")
                        .authenticated()
                    .anyRequest().denyAll())
                .formLogin(form -> form
                    .defaultSuccessUrl("/api/state", true)
                    .permitAll())
                .logout(logout -> logout
                    .logoutSuccessUrl("/login?logout")
                    .permitAll())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                    .password("{noop}demo123")
                    .roles("USER")
                    .build());
    }
}

@Component
@RequestScope
class PerRequestMarker {

    private final String marker = UUID.randomUUID().toString();

    public String marker() {
        return marker;
    }
}

@Component
@SessionScope
class PerSessionMarker {

    private final String marker = UUID.randomUUID().toString();

    public String marker() {
        return marker;
    }
}

@RestController
class ContextController {

    private final PerRequestMarker requestMarker;
    private final PerSessionMarker sessionMarker;

    ContextController(PerRequestMarker requestMarker,
            PerSessionMarker sessionMarker) {
        this.requestMarker = requestMarker;
        this.sessionMarker = sessionMarker;
    }

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/state")
    public StateView currentState(Authentication authentication,
            HttpServletRequest request) {
        String requestId = requestMarker.marker();
        String sessionMarkerValue = sessionMarker.marker();
        boolean hasHttpSession = request.getSession(false) != null;

        return new StateView(
                authentication.getName(),
                requestId,
                sessionMarkerValue,
                hasHttpSession);
    }

    public record StateView(
            String username,
            String requestMarker,
            String sessionMarker,
            boolean hasHttpSession) {
    }
}
~~~

**Tính runnable của ví dụ:**

- **RequestSessionDemoApplication** là public top-level class duy nhất; tên trùng file Java.
- Các class còn lại là package-private top-level classes được component scan trong cùng package.
- **@RequestScope** và **@SessionScope** mặc định sử dụng scoped proxy, nên một controller singleton có thể inject các bean này; mỗi lần gọi method trên proxy sẽ được chuyển tới instance đúng scope.
- **Authentication** được Spring MVC cung cấp cho endpoint đã xác thực.
- **sessionMarker** là giá trị demo tự sinh trong session scope, **không phải session ID thật**, nhằm tránh gửi session identifier nhạy cảm ra API.
- **UUID** có giá trị ngẫu nhiên, vì vậy nội dung response không có UUID cố định để chép nguyên làm expected stdout.
- **{noop}** chỉ phù hợp cho ví dụ học cục bộ; hệ thống thật phải băm mật khẩu bằng PasswordEncoder thích hợp.

### 6.3. Khởi chạy

Trong thư mục gốc dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng **gradlew.bat bootRun**. Ứng dụng thường lắng nghe ở **http://localhost:8080**, trừ khi bạn đổi server.port.

Cách quan sát dễ nhất bằng browser:

1. Truy cập **http://localhost:8080/public**: trả JSON công khai, không cần đăng nhập.
2. Mở **http://localhost:8080/api/state** khi chưa đăng nhập: mặc định chuyển hướng tới **/login**.
3. Đăng nhập bằng **learner / demo123** ở trang form được Spring Security sinh.
4. Đăng nhập thành công được đưa tới **/api/state**, trả JSON chứa username, requestMarker, sessionMarker và hasHttpSession.
5. Reload **/api/state** vài lần trong cùng browser profile và phiên cookie hợp lệ.
6. Mở **cửa sổ ẩn danh** rồi đăng nhập cùng user để so sánh sessionMarker của phiên khác.
7. Logout hoặc để session hết hạn, đăng nhập lại và quan sát sessionMarker mới ở phiên mới.

Ví dụ biểu diễn hai lần GET sau khi đăng nhập bằng browser profile A:

~~~text
GET /api/state (lần 1)
username = learner
requestMarker = R1 (giá trị UUID thật)
sessionMarker = S1 (giá trị UUID thật)
hasHttpSession = true

GET /api/state (lần 2, cùng phiên)
username = learner
requestMarker = R2 (UUID khác R1)
sessionMarker = S1 (vẫn cùng giá trị)
hasHttpSession = true
~~~

**R1, R2, S1 là nhãn minh họa, không phải kết quả UUID cố định của ứng dụng.** Browser gửi lại session cookie để Spring Security nạp Authentication, đồng thời Spring SessionScope lấy lại instance PerSessionMarker trong phiên đó. Trong khi ấy, PerRequestMarker được tạo mới cho request thứ hai.

### 6.4. Bảng quan sát khi có nhiều client và request

| Tình huống | requestMarker | sessionMarker | username / authentication |
| --- | --- | --- | --- |
| GET đầu tiên sau login trong browser A | R1 | S1 | learner |
| Reload GET trong browser A, cùng session | R2 | S1 | learner |
| Một GET mới trong browser A | R3 | S1 | learner |
| Login trong cửa sổ ẩn danh B độc lập | R4 | S2 | learner, nhưng phiên khác |
| Logout A rồi login bằng phiên mới | R5 | S3 | learner, phiên đã thay đổi |
| Browser A gửi cookie cũ của phiên hết hạn | R6 khi endpoint được xử lý sau khi xác thực lại | S4 sau phiên mới | Phải đăng nhập lại nếu không có cơ chế tái xác thực khác |

Các nhãn R/S mang tính **logic, không phải số thứ tự thực tế server cấp**. Hai cửa sổ browser có thể truy cập cùng username nhưng không chia sẻ session nếu kho cookie tách biệt. Ngược lại, hai tab thường chia sẻ session cookie và trạng thái đăng nhập.

**Lưu ý về session-scoped bean:** demo không tạo lại PerSessionMarker cho mọi request. Tuy nhiên, khi triển khai nhiều instance server, dữ liệu session phải có cơ chế storage/replication phù hợp nếu muốn request được định tuyến sang instance khác mà vẫn giữ trạng thái. Đây là vấn đề của hệ thống phân tán, không phải ThreadLocal.

## 7. Kiểm thử tự động hai vòng đời

Thực hiện nhiều request cùng một **MockHttpSession** là cách kiểm chứng có tính quyết định hơn so với chỉ mở một trang bằng browser.

Thêm vào **build.gradle** của dự án nếu chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **fragment Gradle Groovy DSL**, không phải toàn bộ file build.gradle; nếu Spring Initializr đã khai báo starter-test thì không thêm trùng.

Tạo file **src/test/java/com/example/demo/RequestSessionDemoTest.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestSessionDemoTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    @Test
    void requestScopeChangesWhileSessionScopePersists()
            throws Exception {
        // Form login thực, không chỉ mock Authentication.
        MvcResult login = mvc.perform(post("/login")
                    .param("username", "learner")
                    .param("password", "demo123")
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        HttpSession httpSession =
                login.getRequest().getSession(false);
        assertNotNull(httpSession);
        MockHttpSession session = (MockHttpSession) httpSession;

        MvcResult first = mvc.perform(
                    get("/api/state").session(session))
                .andExpect(status().isOk())
                .andReturn();

        MvcResult second = mvc.perform(
                    get("/api/state").session(session))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode a = json.readTree(
                first.getResponse().getContentAsString());
        JsonNode b = json.readTree(
                second.getResponse().getContentAsString());

        assertEquals("learner", a.get("username").asText());
        assertEquals("learner", b.get("username").asText());

        // Mỗi HTTP request dùng instance request-scoped riêng.
        assertNotEquals(
                a.get("requestMarker").asText(),
                b.get("requestMarker").asText());

        // Cùng HttpSession -> giữ cùng instance session-scoped.
        assertEquals(
                a.get("sessionMarker").asText(),
                b.get("sessionMarker").asText());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows dùng **gradlew.bat test**. Test tập trung vào khác biệt lifecycle; nó không cố gán một UUID hay session ID cụ thể. Nếu chương trình đổi SessionCreationPolicy, authentication mechanism hoặc cách lưu context, kết quả có thể thay đổi và test cần điều chỉnh theo chính sách dự kiến.

**Vì sao test này khác @WithMockUser?** @WithMockUser mô phỏng Authentication trong test mà không nhất thiết kiểm tra login form và trạng thái được lưu qua request. Ở đây, test thực hiện POST /login với CSRF hợp lệ, lấy session của request login rồi tái sử dụng **đúng session đó** ở hai GET. Nhờ vậy phép thử thể hiện cả form authentication persistence và hai Spring bean scopes.

## 8. SessionCreationPolicy: ảnh hưởng đến SecurityContext qua các request

Spring Security Servlet cung cấp các giá trị **SessionCreationPolicy**:

| Policy | Spring Security dùng HttpSession như thế nào? | Diễn giải |
| --- | --- | --- |
| **ALWAYS** | Tạo HttpSession | Phù hợp khi cấu hình cố ý yêu cầu phiên cho request. |
| **IF_REQUIRED** | Chỉ tạo phiên khi cần | Thường dùng cho login qua session; Spring Security có thể tạo phiên để lưu thông tin cần thiết. |
| **NEVER** | Không chủ động tạo phiên, nhưng có thể dùng phiên đã tồn tại | Không đồng nghĩa không dùng session; cần kiểm tra nơi khác tạo session. |
| **STATELESS** | Spring Security không tạo session và không dùng nó để lấy SecurityContext | Hợp với xác thực per-request như Bearer token, khi cấu hình đầy đủ. |

Ví dụ đổi sang stateless ở tầng Security:

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Đây là **fragment cấu hình**, không phải file độc lập và không nên sao chép vào ứng dụng formLogin đang cần duy trì phiên mà không thiết kế lại cơ chế đăng nhập. Khi stateless, mỗi request được xác thực dựa trên credential có trong request (ví dụ Authorization: Bearer ...) thay vì dựa vào SecurityContext đã lưu trong HttpSession.

**STATELESS không bảo đảm toàn bộ ứng dụng Java không bao giờ tạo HttpSession.** Nó quy định hành vi của Spring Security; code MVC, thư viện khác hoặc chính ứng dụng vẫn có thể gọi request.getSession() và tạo session phục vụ mục đích khác. Nếu mục tiêu là API thực sự không có phiên, cần rà soát toàn bộ stack và không dùng @SessionScope/HttpSession cho trạng thái cần loại bỏ.

### 8.1. So sánh form login theo phiên và Bearer token

~~~text
STATEFUL:
  POST /login (mật khẩu, CSRF ...)
       -> server lưu SecurityContext gắn với HttpSession
       -> browser gửi session cookie ở request tiếp theo
       -> server tra session, nạp Authentication

STATELESS:
  GET /api/data + Authorization: Bearer <token>
       -> server kiểm tra token ở request hiện tại
       -> xây dựng Authentication cho request đó
       -> không dựa vào HttpSession để lấy SecurityContext
       -> request tiếp theo cần credential hợp lệ riêng
~~~

Mô hình stateless không có nghĩa không tồn tại **SecurityContextHolder**. Spring Security vẫn cần Authentication trong lúc xử lý request để authorization hoạt động; khác biệt là **cách xác minh/nạp danh tính cho từng request**, không phải sự hiện diện của object SecurityContext.

HTTP Basic có thể gửi credential trong mỗi request; Bearer token cũng vậy. Một số hệ thống kết hợp nhiều cơ chế, hoặc dùng JWT trong cookie; vì thế **"có cookie" không tự đồng nghĩa "có HttpSession"**, và **"không có JSESSIONID" không tự đồng nghĩa "không có authentication"**.

### 8.2. Không dùng request attribute để thay session

Dữ liệu đặt bằng:

~~~java
request.setAttribute("currentStep", "checked");
~~~

thuộc request cụ thể. RequestAttributeSecurityContextRepository có thể phục vụ **ERROR dispatch của cùng request**, nhưng request attribute không phải kho lưu trạng thái người dùng cho lần truy cập ngày mai.

Nếu cần giữ tùy chọn đơn giản xuyên nhiều request của một phiên:

~~~java
HttpSession session = request.getSession();
session.setAttribute("preferredLanguage", "vi");
~~~

Đây là fragment trong code xử lý request; cần import HttpSession/HttpServletRequest, và phải đánh giá rủi ro lưu dữ liệu vào session. Đọc ở request sau khi client mang cùng phiên:

~~~java
HttpSession session = request.getSession(false);
String language = session == null
        ? null
        : (String) session.getAttribute("preferredLanguage");
~~~

**getSession()** có thể tạo phiên; **getSession(false)** chỉ tìm phiên hiện tại và trả null nếu không tồn tại. Không nên vô tình tạo phiên chỉ để kiểm tra xem client có đang đăng nhập hay không.

## 9. Những giới hạn quan trọng của request context

### 9.1. Gọi bất đồng bộ và thread pool

Vì SecurityContextHolder trên Servlet mặc định dùng ThreadLocal, việc tạo luồng mới bằng **new Thread**, dùng **CompletableFuture** hay **@Async** có thể khiến code ở luồng con **không thấy Authentication hiện hành**, hoặc thấy một ngữ cảnh khác theo cách triển khai. Không sử dụng ThreadLocal để "truyền đăng nhập" một cách ngầm định.

Khi cần chạy công việc bất đồng bộ dưới một ngữ cảnh xác thực được kiểm soát, có thể dùng các helper như **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextExecutor** hoặc phương thức truyền context thích hợp. Dù vậy, vẫn phải cân nhắc thời điểm hết phiên, tính hợp lệ của quyền và giới hạn việc mang credentials sang background job.

**Không chuyển SecurityContextHolder sang MODE_GLOBAL chỉ để chữa lỗi @Async**: trong ứng dụng server nhiều người dùng, điều này phá ranh giới danh tính giữa request.

### 9.2. Nhiều request đồng thời của cùng một phiên

Cùng một HttpSession có thể được hai request khác nhau đọc hoặc cập nhật **đồng thời**. Session attributes không tự biến mọi thao tác read-modify-write thành an toàn cho concurrent access. Không lưu đối tượng mutable chia sẻ mà không thiết kế khóa, tính bất biến, lưu trữ transaction hoặc quy tắc cập nhật thích hợp.

~~~text
Request A, thread-1 -> HttpSession S -> attribute "cart"
Request B, thread-2 -> HttpSession S -> attribute "cart"

Cả hai có thể truy cập cùng dữ liệu phiên gần như đồng thời.
Mỗi thread vẫn có ngữ cảnh xử lý request riêng.
~~~

Việc cùng session và cùng username không làm các request trở thành một chuỗi tuần tự bắt buộc.

### 9.3. Phân tán nhiều server và session store

Với một server, phiên có thể được giữ trong bộ nhớ container. Khi chạy nhiều replica hoặc restart server, cần cân nhắc store chia sẻ, ví dụ Spring Session tích hợp Redis hoặc cơ chế session affinity phù hợp. Nếu session không được phân phối nhất quán, một request có thể nạp được Authentication nhưng request sau được gửi tới replica khác lại không thấy phiên.

Khi chọn lưu session ngoài bộ nhớ tiến trình, cần xem xét:
- Khả năng serialization của dữ liệu session.
- TTL/timeout và vô hiệu hóa phiên.
- Bảo mật Redis/store tương đương.
- Kích thước dữ liệu lưu session, tránh đẩy báo cáo lớn vào session.
- Cơ chế thay đổi quyền người dùng sau khi đăng nhập; authority lưu lâu có thể không phản ánh thay đổi quyền mới nhất nếu không có chiến lược làm mới/thu hồi.

## 10. Lưu ý bảo mật đối với session và cookie

### 10.1. Không lộ session identifier

Cookie chứa mã phiên là một **bearer credential theo nghĩa ai kiểm soát được mã phiên hợp lệ có thể tìm cách sử dụng phiên đó**. Không đưa session ID vào query string, log, screenshot công khai hoặc JSON API. Ví dụ demo chỉ trả một **sessionMarker ngẫu nhiên không dùng để xác thực**, không trả JSESSIONID.

Cấu hình cookie nên được đánh giá theo môi trường:
- **Secure**: cookie chỉ gửi qua HTTPS khi thuộc tính này được bật; production nên dùng HTTPS.
- **HttpOnly**: hạn chế JavaScript truy cập cookie khi cấu hình.
- **SameSite**: giúp giảm một số tình huống gửi cookie cross-site nhưng không tự thay thế CSRF protection.
- **Path/Domain**: giới hạn nơi cookie được gửi.
- **Max-Age/Expires** và chính sách session timeout: quyết định vòng đời phù hợp.

### 10.2. CSRF và session không phải một

Trong ứng dụng browser dùng session cookie, trình duyệt có thể tự gửi cookie khi đáp ứng các điều kiện cookie policy. Vì vậy, POST/PUT/DELETE thay đổi trạng thái thường cần **CSRF protection**. Spring Security bật CSRF mặc định cho mô hình Servlet phù hợp. Đừng tắt CSRF chỉ vì người dùng "đã đăng nhập".

Trong demo, các endpoint nghiệp vụ chỉ sử dụng **GET**; POST /login vẫn do Spring Security xử lý cùng CSRF token trong form sinh sẵn. Nếu dùng curl gửi POST /login mà không có CSRF token/cookie đúng, request có thể bị từ chối 403 trước khi mật khẩu được kiểm tra.

**Giới hạn:** SameSite và CSRF policy thực tế còn phụ thuộc client, cách gửi credentials, reverse proxy và cấu hình deployment. Không xem SameSite là giải pháp duy nhất.

### 10.3. Session fixation, timeout và logout

Một attacker có thể cố buộc nạn nhân dùng session identifier biết trước (session fixation). Spring Security hỗ trợ thay đổi session ID khi xác thực thành công trong cấu hình mặc định phù hợp. Đừng tắt bảo vệ này chỉ để giữ nguyên ID qua login.

Khi logout, cần đảm bảo phiên và SecurityContext không còn được dùng trái ý định; nếu dùng remember-me/token độc lập, có thể cần vô hiệu hóa thêm credential tương ứng. Khi session timeout, request tiếp theo phải được xử lý như không còn trạng thái đăng nhập hợp lệ, trừ khi có cơ chế tái xác thực khác.

### 10.4. Đừng tự lưu toàn bộ secret vào session

HttpSession là nơi lưu phía server nhưng không phải "kho bảo mật vô hạn". Không đặt access token plaintext, private key, mật khẩu hoặc đối tượng dữ liệu nhạy cảm không cần thiết vào session chỉ để tránh database call. Giảm kích thước session, đặt TTL hợp lý, mã hóa/bảo vệ store khi cần và phân quyền khi tải dữ liệu thực tế.

## 11. Chẩn đoán các nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra / sửa |
| --- | --- | --- |
| Request đầu sau login thành công, request sau lại bị yêu cầu đăng nhập | Cookie không được gửi, session hết hạn, SecurityContext không được lưu hoặc repository sai | Kiểm tra Set-Cookie/Cookie, SecurityContextRepository, session policy và flow xác thực. |
| Đổi sang STATELESS rồi form login không nhớ người dùng | Spring Security không dùng HttpSession để lấy SecurityContext | Dùng cơ chế xác thực per-request, hoặc chọn lại session policy phù hợp. |
| Đọc SecurityContextHolder trong @Async thấy null/anonymous | Context theo thread không được truyền tự động | Dùng cơ chế delegation/propagation phù hợp, không chuyển sang MODE_GLOBAL. |
| @RequestScope bean thay đổi sau mỗi lần reload | Đúng theo request lifetime | Dùng @SessionScope chỉ nếu thật sự cần dữ liệu theo phiên. |
| @SessionScope bean thay đổi ngay trong cùng phiên | Cookie/session thay đổi, timeout, logout, cấu hình distributed session | Kiểm tra session lifecycle, cookie và topology ứng dụng. |
| Hai tab dùng chung trạng thái | Chia sẻ session cookie trong cùng browser profile | Đúng với session-based authentication; muốn tách riêng cần mô hình nghiệp vụ khác. |
| HttpSession tồn tại nhưng SecurityContext trống | Session phục vụ dữ liệu khác, authentication không lưu ở đó, chưa đăng nhập hoặc stateless | Không dùng "session != null" để chứng minh đã xác thực. |
| Cookie JSESSIONID có trên browser nhưng endpoint vẫn 401/302 | Session không tồn tại/hết hạn hoặc không chứa authentication hợp lệ | Điều tra repo, cookie domain/path, timeout, logout. |
| Đã gọi SecurityContextHolder.setContext nhưng request tiếp theo mất login | Chưa gọi saveContext khi dùng cơ chế explicit save | Sử dụng authentication flow chuẩn hoặc lưu qua SecurityContextRepository đúng chỗ. |
| ERROR dispatch không nhìn thấy context cùng request | Request dispatcher hoặc repository không giữ request attribute/context tương ứng | Xem RequestAttributeSecurityContextRepository, filter mapping và error dispatch. |
| Cùng session nhưng cập nhật attribute bị mất | Race condition giữa nhiều request song song | Thiết kế concurrency, đồng bộ hoặc lưu dữ liệu trong kho có transaction. |
| Ứng dụng nhiều replica "đăng xuất ngẫu nhiên" | Phiên chỉ có ở một replica và load balancer chuyển request | Dùng session store chia sẻ/affinity phù hợp, theo dõi session TTL. |

### Logging khi điều tra

Ở môi trường phát triển có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Tập trung quan sát: HTTP method/path, request có cookie không, loại authentication mechanism, SecurityContextRepository, tên người dùng/authorities sau xác thực và redirect/status. **Không log nguyên cookie header, token, mật khẩu hay session identifier**.

## 12. Câu hỏi tự đánh giá

1. Vì sao hai request của cùng một người dùng có thể được xử lý trên hai thread khác nhau mà user vẫn đăng nhập?
2. HttpSession khác cookie JSESSIONID thế nào? Phía client lưu gì và phía server lưu gì?
3. SecurityContextHolder có phải kho lưu authentication lâu dài qua tất cả request không?
4. SecurityContextRepository giải quyết bước nào trong vòng đời authentication?
5. Vì sao RequestAttributeSecurityContextRepository hữu ích cho ERROR dispatch nhưng không đủ để duy trì login qua nhiều HTTP request?
6. Khi dùng Spring Security 6, tại sao chỉ set Authentication trong SecurityContextHolder có thể chưa đủ cho request tiếp theo?
7. Khi reload /api/state, requestMarker và sessionMarker thay đổi thế nào nếu session vẫn còn?
8. Hai cửa sổ ẩn danh với hai cookie jar độc lập nhưng cùng username có nhất thiết chia sẻ HttpSession không?
9. Nếu ứng dụng dùng Authorization: Bearer mỗi request, SecurityContext có còn được dùng để phân quyền trong request hiện hành không?
10. SessionCreationPolicy.NEVER và STATELESS khác nhau điểm gì?
11. Vì sao việc cùng session không bảo đảm các request xử lý tuần tự hoặc thao tác lên session attribute luôn thread-safe?
12. Khi người dùng logout hoặc session timeout, tại sao cookie còn sót lại không tự chứng minh vẫn đăng nhập?
13. Nếu dùng Spring WebFlux thay vì Spring MVC, bạn sẽ cần thay ThreadLocal SecurityContext bằng cơ chế ngữ cảnh nào?

**Ghi nhớ:** **request context** trả lời “ngữ cảnh nào đang hoạt động trong lần xử lý HTTP này?”; **HTTP session** trả lời “trạng thái server-side nào được liên kết với nhiều HTTP request?”. Trong Spring Security Servlet, **SecurityContextHolder** phục vụ request đang xử lý, **SecurityContextRepository** có thể nạp/lưu authentication, và **HttpSession + cookie phiên** có thể duy trì liên kết đó qua nhiều request. Stateful và stateless khác nhau chủ yếu ở **cách lấy lại danh tính**, không phải ở việc có hay không có SecurityContext trong lúc phân quyền.

## Tài liệu chính thức

- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Authentication Architecture / SecurityContextHolder: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — SecurityContextRepository API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html
- Spring Security 6.5 — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Framework — Request Scope and Session Scope: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
