# SecurityContextRepository và các chiến lược lưu, tải ngữ cảnh trong Spring Security Servlet

## 1. Mục tiêu và vấn đề cần giải quyết

Khi một người dùng đăng nhập thành công, Spring Security có thể đặt đối tượng **Authentication** vào **SecurityContext** để các thành phần tiếp theo trong cùng request biết ai đang thao tác. Tuy nhiên, câu hỏi tiếp theo là:

> Khi request kết thúc và request mới đến, Spring Security lấy lại thông tin xác thực từ đâu?

**SecurityContextRepository** là điểm mở rộng trả lời câu hỏi đó cho ứng dụng **Servlet**. Repository chịu trách nhiệm **nạp** và **lưu** SecurityContext liên quan đến HTTP request/response. Tùy mô hình ứng dụng, context có thể được lưu trong **HttpSession**, trong **request attribute**, hoặc **không lưu qua request**.

Sau bài này, bạn có thể:

1. Phân biệt **SecurityContextHolder**, **SecurityContextHolderStrategy**, **SecurityContextRepository** và cơ chế xác thực.
2. Hiểu thời điểm nạp/lưu/giải phóng SecurityContext trong Spring Security 6, đặc biệt **SecurityContextHolderFilter** và yêu cầu **lưu tường minh**.
3. Chọn đúng **HttpSessionSecurityContextRepository**, **RequestAttributeSecurityContextRepository**, **DelegatingSecurityContextRepository** hoặc **NullSecurityContextRepository**.
4. Giải thích tác động của **SessionCreationPolicy** đối với stateful/stateless authentication.
5. Chạy ví dụ Spring Boot trên Servlet stack, đăng nhập qua form và kiểm chứng danh tính được phục hồi ở request tiếp theo.
6. Biết cách tự lưu SecurityContext khi viết luồng xác thực riêng và chẩn đoán lỗi “đăng nhập được nhưng request sau lại mất login”.

Bài này chỉ xét SecurityContext trong **Spring Security Servlet**. Cách tích hợp Reactor context ở WebFlux có mô hình lưu/ngữ cảnh khác, không áp dụng nguyên xi các class Servlet dưới đây.

## 2. Bốn đối tượng dễ bị nhầm lẫn

| Thành phần | Vai trò | Phạm vi mặc định / thời điểm |
| --- | --- | --- |
| **Authentication** | Principal/danh tính, authorities và trạng thái xác thực; có thể chứa credentials nếu chưa được xóa | Được tạo/cập nhật bởi cơ chế xác thực |
| **SecurityContext** | Vỏ chứa Authentication của ngữ cảnh hiện hành | Được tham chiếu trong quá trình xử lý bảo mật |
| **SecurityContextHolder** + **SecurityContextHolderStrategy** | Cung cấp cách lấy/đặt SecurityContext đang có cho code chạy hiện tại | Mặc định dùng ThreadLocal với Servlet; cần xử lý riêng nếu chuyển thread |
| **SecurityContextRepository** | Nạp/lưu SecurityContext để kết nối ngữ cảnh với HTTP request, request attribute hoặc session | Phụ thuộc implementation và cấu hình chain |

Ví dụ, trong controller đã yêu cầu đăng nhập:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
~~~

Đoạn này **đọc context đã có trong phạm vi xử lý hiện tại**. Nó không tự ghi Authentication vào database, không tạo session và không cam kết rằng request HTTP tiếp theo sẽ có cùng danh tính.

Có thể hình dung:

~~~text
HTTP request hiện tại
     |
     v
SecurityContextRepository --load--> SecurityContext
                                     |
                                     +--> Authentication(principal, authorities...)
                                     |
SecurityContextHolderStrategy -------+--> code hiện tại đọc context
     |
     v
Nếu có sự kiện xác thực và cần duy trì state:
Repository.saveContext(context, request, response)
     |
     +--> request attribute, HttpSession hoặc không lưu (tùy repo)
     |
HTTP response kết thúc --> holder được dọn dẹp
     |
Request tiếp theo --> repository tải lại nếu có dữ liệu lưu phù hợp
~~~

**Nhớ:** Holder giải quyết **ngữ cảnh hiện tại**; Repository giải quyết **cách nạp/lưu ngữ cảnh gắn với HTTP request**. Chỉ gọi setContext(...) không đủ để bảo đảm lưu danh tính cho lần truy cập sau.

### SecurityContextHolder không phải nơi lưu session

SecurityContextHolder mặc định dùng **MODE_THREADLOCAL**, tức dữ liệu gắn với thread đang xử lý. Servlet container tái sử dụng thread giữa các request, nên Spring Security phải thiết lập và dọn ngữ cảnh phù hợp ở mỗi request để tránh rò rỉ danh tính giữa người dùng. HttpSession lại là cơ chế lưu trạng thái qua nhiều HTTP request và không đồng nhất với ThreadLocal.

Các strategy như MODE_INHERITABLETHREADLOCAL hoặc MODE_GLOBAL tồn tại nhưng không phải giải pháp phổ quát để bảo mật request. Đặc biệt, chuyển Authentication qua thread pool/async cần cơ chế truyền ngữ cảnh có chủ đích như DelegatingSecurityContextExecutor hoặc tích hợp async của framework; sao chép ThreadLocal tùy tiện có thể làm rò rỉ danh tính.

## 3. Vòng đời nạp và lưu context trong Spring Security 6

Trong cấu hình Servlet hiện đại, **SecurityContextHolderFilter** thường chịu trách nhiệm đưa SecurityContext từ repository vào **SecurityContextHolderStrategy** khi request đi vào filter chain. Nó dùng cơ chế **deferred context** để tránh nạp dữ liệu không cần thiết nếu không ai truy cập context.

Flow khái niệm:

~~~text
Client GET /me + Cookie: JSESSIONID=...
  |
  v
FilterChainProxy -> SecurityFilterChain đã khớp
  |
  v
SecurityContextHolderFilter
  |  lấy DeferredSecurityContext từ SecurityContextRepository
  |  đưa vào SecurityContextHolderStrategy
  |
  v
Các filter sau cần authentication -> context được resolve
  |
  +-- có context từ request attribute / HttpSession?
  |         |
  |         +-- có -> truy xuất Authentication đã lưu
  |         +-- không -> context trống ban đầu
  |
  v
Authentication filter (nếu cần xác thực mới)
  |
  v
AuthorizationFilter -> Controller
  |
  v
Kết thúc request -> context/holder được dọn dẹp đúng phạm vi
~~~

**Điểm quan trọng của Spring Security 6:** SecurityContextHolderFilter **nạp** context nhưng **không tự lưu context khi request kết thúc**. Khi ứng dụng tự thiết lập Authentication và muốn lưu sang request tiếp theo, nó phải gọi **SecurityContextRepository.saveContext(...)** theo cơ chế lưu đã chọn.

Điều này khác với mô hình cũ thường được mô tả qua **SecurityContextPersistenceFilter**, nơi filter quan sát/lưu context ở cuối chuỗi. Spring Security 6 ưu tiên cách **explicit save**, nhằm tránh các lần ghi không cần thiết và những tình huống response đã commit trước khi lưu xong.

Các filter xác thực chuẩn như form login được framework cấu hình để lưu context khi cần; lập trình viên dùng flow chuẩn **không phải** tự gọi saveContext sau mỗi login. Ngược lại, khi tự xây dựng cơ chế đăng nhập, việc chỉ set SecurityContextHolder mà không save có thể khiến login “có hiệu lực một request rồi mất”.

### Tại sao phải lưu trước khi response commit?

Sau khi server gửi/commit response (ví dụ redirect 302), việc thêm hoặc thay đổi session cookie có thể không còn khả thi. Đối với flow đăng nhập tùy biến, nên hoàn tất thiết lập context và **saveContext trước khi redirect hoặc ghi response**, thay vì chờ cuối request một cách không chắc chắn.

## 4. Giao diện SecurityContextRepository

Ở góc độ sử dụng, cần biết các hoạt động sau:

| API | Ý nghĩa |
| --- | --- |
| **loadDeferredContext(HttpServletRequest)** | Trả một DeferredSecurityContext; context có thể chỉ được tải khi cần |
| **saveContext(SecurityContext, HttpServletRequest, HttpServletResponse)** | Lưu context theo chính sách của implementation |
| **containsContext(HttpServletRequest)** | Cho biết repository có context gắn với request theo logic implementation hay không |

Các API cũ như loadContext(HttpRequestResponseHolder) xuất hiện trong tài liệu/phiên bản cũ, nhưng khi thiết kế mới với Spring Security 6 nên nắm cơ chế deferred loading và explicit save.

Một fragment đọc context trực tiếp (chỉ minh họa, không phải thay thế filter lifecycle):

~~~java
DeferredSecurityContext deferred =
    securityContextRepository.loadDeferredContext(request);

SecurityContext context = deferred.get();
Authentication authentication = context.getAuthentication();
~~~

Để biên dịch fragment này cần securityContextRepository, request và import DeferredSecurityContext, SecurityContext, Authentication tương ứng. Trong ứng dụng thường ngày, **nên lấy context từ SecurityContextHolder** do Spring Security quản lý; không gọi repository.loadDeferredContext tùy tiện nhiều lần trong controller.

Với **saveContext**, đừng hiểu nó tương đương “lưu password/token vĩnh viễn”. Repository chỉ lưu đối tượng SecurityContext theo chính sách đã chọn; trong mô hình session, nội dung Authentication có thể được gắn với session. Dữ liệu này cần được bảo vệ và không nên chứa credentials không cần thiết.

## 5. HttpSessionSecurityContextRepository: duy trì login theo session

**HttpSessionSecurityContextRepository** đọc/ghi SecurityContext trong **HttpSession**. Sau khi browser đăng nhập bằng form và phiên được lưu, các request sau dùng session cookie để server định vị session và lấy lại Authentication.

~~~text
POST /login (credentials + CSRF token hợp lệ)
  |
  +-- Form-login authentication thành công
  +-- tạo SecurityContext chứa Authentication
  +-- saveContext(...) -> HttpSession
  |
  +-- response gửi session cookie nếu cần
          |
Browser giữ cookie
          |
GET /me (Cookie: JSESSIONID=...)
  |
  +-- repository nạp SecurityContext từ HttpSession
  +-- AuthorizationFilter nhìn thấy user đã xác thực
  +-- controller được gọi
~~~

Những điểm cần hiểu:

- **JSESSIONID thường là khóa tham chiếu đến session**, không phải chính Authentication hay mật khẩu. Server tra session dựa vào cookie; không suy ra quyền từ việc client gửi một chuỗi cookie bất kỳ.
- Repository có thể **không tạo session mới** nếu context trống, anonymous hoặc không có thay đổi cần lưu; chính sách cho phép tạo session và các thành phần khác trong ứng dụng cũng có thể ảnh hưởng.
- **Session tồn tại không đồng nghĩa đã đăng nhập.** Spring Security có thể tạo session trước login vì request cache hoặc CSRF token; kiểm tra Authentication để kết luận danh tính.
- Session có thể hết hạn, bị invalidated khi logout hoặc không còn dùng chung giữa các node nếu hệ thống chưa có shared-session strategy.
- Mặc định Spring Security lưu SecurityContext trong session bằng khóa nội bộ được định nghĩa bởi HttpSessionSecurityContextRepository; không tự ý sửa attribute này từ controller.

**Thích hợp:** web MVC dùng form login, hoặc ứng dụng có yêu cầu đăng nhập duy trì qua nhiều request bằng HTTP session.

**Cần cân nhắc:** CSRF, session fixation, cookie Secure/HttpOnly/SameSite phù hợp, thời hạn phiên, logout, clustering và bảo vệ session store. Repository không thay thế các cơ chế này.

## 6. RequestAttributeSecurityContextRepository: giữ context trong một request

**RequestAttributeSecurityContextRepository** lưu SecurityContext vào **thuộc tính của Servlet request**, nhằm giúp các nhánh dispatch trong cùng request có thể tìm lại context.

Ví dụ có ích: endpoint gặp lỗi, container thực hiện **ERROR dispatch** đến trang lỗi; một số môi trường có thể dọn SecurityContextHolder giữa các dispatch. Request attribute cho phép context đã được lưu ở request có thể truy cập lại trong phần xử lý lỗi.

~~~text
Request ban đầu
  |
  +-- context được lưu vào request attribute
  |
  +-- xảy ra lỗi
          |
          +-- ERROR dispatch (cùng request)
                  |
                  +-- repository nạp lại context từ attribute
~~~

Nó **không** đồng nghĩa với lưu vào HttpSession. RequestAttributeSecurityContextRepository **không lưu ngữ cảnh cho HTTP request mới**: request sau có object HttpServletRequest khác, nên không lấy lại attribute cũ.

**Thích hợp:** giữ ngữ cảnh cho các dispatch nằm trong một request; thường là một phần của repository kết hợp. Nếu chỉ sử dụng request-attribute repository, login không tự tồn tại qua request tiếp theo.

## 7. DelegatingSecurityContextRepository: kết hợp nhiều nơi lưu

**DelegatingSecurityContextRepository** nhận nhiều SecurityContextRepository theo thứ tự, ví dụ:

~~~java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
~~~

Khi nạp, nó có thể sử dụng context đã có từ các delegate theo thứ tự; khi lưu, nó chuyển lời gọi saveContext đến các delegate theo contract. Với request attribute đặt trước và HttpSession đặt sau, ứng dụng vừa hỗ trợ context trong các dispatch của request, vừa có thể duy trì session login.

Đây là **cấu hình repository mặc định phổ biến trong Spring Security 6 cho ứng dụng Servlet có session**. Tuy nhiên, configuration cụ thể có thể thay đổi khi bật STATELESS, tự cung cấp repository, dùng nhiều SecurityFilterChain hoặc tùy biến các cơ chế xác thực.

Không nên hiểu DelegatingSecurityContextRepository như giải pháp phân tán session: nó **không tự nhân bản session giữa máy chủ**. Mỗi delegate vẫn áp dụng giới hạn/semantics riêng.

## 8. NullSecurityContextRepository: không lưu qua request

**NullSecurityContextRepository** không lưu SecurityContext qua request. Nó thường xuất hiện trong mô hình API stateless, nơi mỗi request tự đưa bằng chứng xác thực như **bearer token** hoặc **HTTP Basic**.

~~~text
GET /api/me + Authorization: Bearer <token>
  |
  +-- filter xác thực token của request này
  +-- đặt Authentication trong context của request này
  +-- controller xử lý
  |
  +-- request kết thúc, context bị dọn
          |
GET /api/me không token
  |
  +-- không có context login lưu từ request trước
  +-- endpoint được bảo vệ -> 401
~~~

**Null repository không vô hiệu hóa xác thực hoặc authorization.** Nó chỉ bỏ việc giữ context qua request. Filter xác thực vẫn có thể đặt Authentication vào SecurityContextHolder để các thành phần trong request hiện tại sử dụng.

Nếu ứng dụng dùng token, phải kiểm tra chữ ký/issuer/audience/expiry/scopes theo cơ chế phù hợp; repo Null **không làm token hợp lệ hay an toàn hơn**. Với OAuth2 Resource Server, ưu tiên chức năng của Spring Security hơn tự viết filter parse bearer token.

## 9. So sánh các chiến lược lưu context

| Repository | Lưu ở đâu? | Có thể dùng lại trong request mới? | Trường hợp thích hợp |
| --- | --- | --- | --- |
| HttpSessionSecurityContextRepository | HttpSession phía server | **Có**, nếu session hợp lệ và context đã được lưu | Form login / web có trạng thái |
| RequestAttributeSecurityContextRepository | Thuộc tính của HttpServletRequest | **Không** | ERROR/FORWARD dispatch trong một request |
| DelegatingSecurityContextRepository | Chuyển đến các repository con | **Tùy delegate**; thường có HttpSession | Servlet web cần cả request dispatch và session |
| NullSecurityContextRepository | Không lưu context | **Không** | API stateless, xác thực theo từng request |

Hỏi **“lưu ở đâu?”** trước khi hỏi **“vì sao user bị logout?”**. Nếu chọn NullSecurityContextRepository, đăng nhập rồi kỳ vọng tự có session ở request sau là mâu thuẫn với chính sách đã chọn.

### Bốn kiểu session creation policy

**SessionCreationPolicy** là cấu hình cấp SecurityFilterChain liên quan việc Spring Security tạo/sử dụng HttpSession; nó không phải tên khác của SecurityContextRepository.

| Policy | Ý nghĩa chính | Tình huống |
| --- | --- | --- |
| **ALWAYS** | Spring Security tạo session | Ứng dụng chủ đích cần session ngay |
| **IF_REQUIRED** | Spring Security chỉ tạo session khi cần | Web login stateful thông thường |
| **NEVER** | Spring Security không chủ động tạo session, nhưng có thể dùng session đã tồn tại | Chính sách hạn chế tạo session nhưng không hoàn toàn stateless |
| **STATELESS** | Spring Security không tạo session và không dùng HttpSession để lấy SecurityContext | API xác thực độc lập theo request |

Một cấu hình tiêu biểu:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

Hoặc:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Hai đoạn mã là **lựa chọn thay thế**, không phải gọi nối tiếp trong một cấu hình. Khi đã dùng STATELESS, hãy thiết kế luồng xác thực độc lập theo request và kiểm chứng không dựa vào session cũ.

**Lưu ý quan trọng:** việc một endpoint thấy cookie hoặc session còn tồn tại có thể đến từ bộ phận khác của ứng dụng. STATELESS đặt ràng buộc cho cách Spring Security sử dụng session để lấy context; nó không bảo đảm mọi thư viện Servlet ngoài Spring Security tuyệt đối không tạo session. Cấu hình và kiểm thử vẫn phải xét toàn bộ ứng dụng.

## 10. Ví dụ chạy được: lưu SecurityContext qua form login

Ta tạo ứng dụng Spring Boot MVC để thấy **request đầu tiên xác thực, request tiếp theo nạp lại context từ session**. Ví dụ dùng:

- Java 17 trở lên, Maven.
- Spring Boot **3.3.13** (dòng Spring Security 6).
- Một SecurityFilterChain dùng form login mặc định.
- DelegatingSecurityContextRepository gồm RequestAttribute và HttpSession.
- Một người dùng trong bộ nhớ có mật khẩu được băm bằng BCrypt.
- Một controller đọc Authentication và kiểm tra session có tồn tại không.

### 10.1. Cây dự án

~~~text
context-repository-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/contextdemo/
    │   ├── ContextDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/contextdemo/
        └── ContextRepositoryTest.java
~~~

### 10.2. pom.xml

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
    <artifactId>context-repository-demo</artifactId>
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

### 10.3. ContextDemoApplication.java

~~~java
package com.example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextDemoApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig.java

~~~java
package com.example.contextdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {

        http
            .securityContext(context ->
                context.securityContextRepository(repository))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("password123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Giải thích các quyết định:**

1. **securityContextRepository()** là bean cấu hình repo có hai delegate. Ở bài học ta khai báo tường minh để nhìn rõ nơi lưu; trong nhiều cấu hình Servlet session thông thường, Spring Security đã có repository kết hợp tương tự.
2. **http.securityContext(...repository(...))** chỉ định repo cho SecurityFilterChain. Đừng kỳ vọng việc tạo một bean riêng mà không kết nối cấu hình luôn thay đổi toàn bộ các chain trong ứng dụng.
3. **IF_REQUIRED** cho phép Spring Security sử dụng session khi cần lưu trạng thái đăng nhập.
4. **formLogin(...)** bật trang đăng nhập mặc định, cơ chế xử lý POST /login và lưu context theo cấu hình của framework sau khi xác thực thành công.
5. **PasswordEncoder** tạo hash BCrypt. Mật khẩu mẫu đặt trong source chỉ để học tập; production dùng nguồn user bền vững và quản lý bí mật phù hợp.
6. **CSRF protection không bị tắt.** Form login được Spring Security sinh ra có token CSRF; trình duyệt gửi token qua form khi đăng nhập hoặc logout.

Trong các phiên bản Spring Security hiện đại, các authentication filter chuẩn được cấu hình để lưu context khi cần. Bạn **không cần** tự thêm controller POST /login hoặc tự gọi repository.saveContext sau form login mặc định.

### 10.5. DemoController.java

~~~java
package com.example.contextdemo;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            Authentication authentication,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);

        return Map.of(
            "username", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "sessionPresent", session != null
        );
    }
}
~~~

Điểm quan sát của **/me**:

- **username** đến từ Authentication do Spring Security đã nạp/khôi phục trong request này.
- **authenticated** cho biết trạng thái cờ của Authentication hiện hành. Trong endpoint đã bảo vệ, form login hợp lệ mới có thể vượt qua yêu cầu authenticated().
- **sessionPresent** chỉ báo có HttpSession tại thời điểm controller chạy; nó không trả session ID hoặc cookie nhạy cảm. **Giá trị true tự nó không chứng minh user đã xác thực**, vì session có thể tồn tại từ trước login.

### 10.6. Khởi động và quan sát bằng trình duyệt

Tại thư mục context-repository-demo:

~~~bash
mvn spring-boot:run
~~~

Mở lần lượt:

1. **http://localhost:8080/public**: endpoint công khai trả HTTP **200** và JSON có trường message = "public-ok".
2. **http://localhost:8080/me** khi chưa đăng nhập: theo cấu hình formLogin, browser thường được **302 redirect** tới /login.
3. Trên trang /login do Spring Security tạo, nhập username **learner** và password **password123** rồi gửi form. Framework kiểm tra credentials, thiết lập Authentication, lưu SecurityContext và chuyển hướng về trang đã yêu cầu hoặc URL thích hợp.
4. Mở lại **http://localhost:8080/me** bằng **cùng trình duyệt** và **cùng session**. Bạn sẽ thấy HTTP **200**, trường username = "learner", authenticated = true và sessionPresent = true.
5. Mở cửa sổ riêng tư mới chưa dùng cùng session rồi vào /me: sẽ phải đăng nhập lại. Đây là dấu hiệu context của browser trước không tự lan sang browser khác.
6. Truy cập **/logout** và hoàn tất thao tác logout bằng form có CSRF token (nếu hiển thị trang xác nhận). Khi session bị kết thúc/context được xóa, /me lại yêu cầu đăng nhập.

Ví dụ /me thành công có các **giá trị** sau (thứ tự khóa JSON có thể thay đổi):

~~~json
{
  "username": "learner",
  "authenticated": true,
  "sessionPresent": true
}
~~~

Đừng hiểu rằng server “nhớ” password đã nhập: trong flow thông thường, HTTP session chứa context thể hiện danh tính đã xác thực, còn password không cần được giữ nguyên. Tên cookie/session và thời hạn phụ thuộc cấu hình container, Spring Security và ứng dụng.

### 10.7. Kiểm thử tự động qua MockMvc

Để tránh chỉ tin vào trạng thái browser, thêm tệp **src/test/java/com/example/contextdemo/ContextRepositoryTest.java**:

~~~java
package com.example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ContextRepositoryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void formLoginPersistsAuthenticationAcrossRequests() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("learner").password("password123"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authenticated").value(true))
            .andExpect(jsonPath("$.sessionPresent").value(true));
    }

    @Test
    void newRequestWithoutSessionMustAuthenticateAgain() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Chạy tại thư mục dự án:

~~~bash
mvn test
~~~

Hai test kiểm chứng **sự khác nhau giữa request sử dụng lại session và request không có session**. Ở test thứ nhất, formLogin() của spring-security-test gửi request login thử nghiệm; đối tượng MockHttpSession từ request login được gắn vào GET /me tiếp theo. Ở test thứ hai, GET /me với client chưa có session bị điều hướng đăng nhập.

Nếu bạn thay cấu hình repo thành NullSecurityContextRepository, test lưu session không còn có cùng kết quả; hãy thử đối chiếu sau khi hiểu chính sách stateless ở phần tiếp theo.

## 11. Ví dụ đối chiếu: API stateless không dùng HttpSession để khôi phục context

Để so sánh, **thay** phương thức SecurityFilterChain của ví dụ ở phần 10 bằng cấu hình dưới đây; đây là một biến thể riêng, không đăng ký đồng thời hai chain cùng matcher nếu chưa thiết kế thứ tự rõ ràng.

~~~java
@Bean
SecurityFilterChain statelessSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .securityContext(context ->
            context.securityContextRepository(new NullSecurityContextRepository()))
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .formLogin(AbstractHttpConfigurer::disable);

    return http.build();
}
~~~

Đây là **fragment thay thế phương thức bean**, cần thêm các import tương ứng cho SessionCreationPolicy, NullSecurityContextRepository, AbstractHttpConfigurer, SecurityFilterChain, HttpSecurity, Customizer và @Bean. Hai bean **UserDetailsService/PasswordEncoder** của ví dụ trước tiếp tục được dùng.

Điểm khác:

- **STATELESS** bảo Spring Security không dùng session để lấy context.
- **NullSecurityContextRepository** không lưu Authentication sang request sau.
- **HTTP Basic** cho phép request tự đưa credentials qua header Authorization.
- **formLogin(disable)** loại bỏ luồng login dựa trên form; request thiếu Basic credentials tới /me sẽ nhận HTTP **401**.
- **CSRF không tự bị tắt** chỉ vì code này dùng STATELESS. Trong ví dụ chỉ kiểm tra GET, không cần CSRF token. Nếu phát triển endpoint thay đổi trạng thái, phải xét rủi ro CSRF theo cách client gửi credentials; trình duyệt có thể tự gửi thông tin HTTP Basic đã nhớ.

Sau khi thêm import và chạy lại ứng dụng, gọi:

~~~bash
curl -i -u learner:password123 http://localhost:8080/me
curl -i http://localhost:8080/me
~~~

Kết quả mong đợi:

| Request | HTTP status | Quan sát |
| --- | --- | --- |
| GET /me có HTTP Basic hợp lệ | **200** | username = learner; request này có Authentication |
| GET /me tiếp theo không gửi credentials | **401** | Không có login được lưu từ request trước |

Trong cấu hình thử nghiệm hoàn toàn stateless, sessionPresent của request thành công thường là false nếu không thành phần khác tạo session. **Đừng coi flag này là kiểm thử duy nhất**; quan sát quan trọng là request không credentials sau đó bị 401.

HTTP Basic không phải cơ chế “mã hóa password”: nó dùng Base64 biểu diễn credentials và **cần HTTPS trong môi trường thật**. Với API production, bearer token thường được xử lý bằng OAuth2 Resource Server thay vì tự viết logic session/token.

## 12. Khi tự xây dựng xác thực: explicit saveContext

Xét một endpoint hoặc filter login **tùy biến** (không sử dụng filter formLogin chuẩn). Sau khi xác thực thành công, bạn muốn lưu context để request kế tiếp dùng lại session.

Trình tự cốt lõi:

~~~java
// Fragment minh họa bên trong một handler đã có authenticationManager,
// securityContextRepository, request và response.
// Đây không phải một lớp Java độc lập.

Authentication verified = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);

SecurityContextHolder.setContext(context);

// Lưu tường minh vào repository đã cấu hình cho security chain.
securityContextRepository.saveContext(context, request, response);
~~~

Để fragment biên dịch trong handler thích hợp, cần các import của Authentication, UsernamePasswordAuthenticationToken, SecurityContext, SecurityContextHolder và kiểu của các dependency. **username/password chỉ là biến input**, phải lấy từ flow xác thực an toàn, kiểm soát đầu vào và CSRF; không dùng trực tiếp đoạn này làm endpoint public trong production.

Giải thích từng bước:

1. **AuthenticationManager.authenticate(...)** kiểm tra credentials; chỉ sử dụng kết quả **verified** đã được xác thực.
2. **createEmptyContext()** tạo một SecurityContext mới. Không sửa trực tiếp context dùng chung nếu không hiểu vòng đời; dùng context mới tránh tác động không mong muốn.
3. **setAuthentication(verified)** cho context biết danh tính hợp lệ.
4. **SecurityContextHolder.setContext(context)** làm danh tính hiện diện với code trong request hiện tại.
5. **securityContextRepository.saveContext(...)** lưu theo chính sách repository (ví dụ HttpSession) để request sau có thể nạp lại.

Nếu bỏ bước 5 khi dùng SecurityContextHolderFilter với explicit save, request hiện tại có thể thấy user nhưng request mới **không nhận lại context**. Nếu dùng NullSecurityContextRepository, saveContext là no-op về mặt lưu bền qua request; đổi sang session repository và chiến lược session phù hợp nếu mục tiêu là duy trì login.

**Tuyệt đối không** tự đặt Authentication là authenticated=true chỉ vì client gửi username; phải qua cơ chế xác minh credentials. Với endpoint login thực, cần thêm xử lý thất bại, bảo vệ CSRF, chống brute force, session fixation, logging không lộ bí mật và response rõ ràng. Cũng cần sử dụng **chính repository** mà SecurityFilterChain nạp ở request tiếp theo, nếu không lưu một nơi rồi lại nạp từ nơi khác.

### Vì sao không dùng request.getSession().setAttribute(...) tùy tiện?

Tự ghi một chuỗi username hoặc object Authentication không đúng schema vào session **không thay cho saveContext**. SecurityContextRepository có contract riêng về context, phát hiện thay đổi và cách phối hợp với filter chain. Hãy dùng abstraction chính thức để tránh lỗi tên attribute, tính nhất quán và thay đổi phiên bản.

## 13. Ngữ cảnh, anonymous và quyền truy cập

Khi request chưa đăng nhập, **AnonymousAuthenticationFilter** có thể đặt một AnonymousAuthenticationToken vào SecurityContextHolder để các thành phần sau xử lý thống nhất.

Điều đó không có nghĩa repository đã tìm thấy login hợp lệ. **AnonymousAuthenticationToken.isAuthenticated() có thể trả true**, nhưng Spring Security vẫn xem nó là anonymous đối với rule **authenticated()** theo AuthenticationTrustResolver.

Nếu viết code tự kiểm tra danh tính, tránh dùng mỗi biểu thức:

~~~java
boolean loggedIn =
    SecurityContextHolder.getContext()
        .getAuthentication()
        .isAuthenticated();
~~~

Đoạn trên còn có thể gây NullPointerException khi không có Authentication, và không phân biệt đúng anonymous. Nên ưu tiên **authorizeHttpRequests(...authenticated())**, @PreAuthorize hoặc các cơ chế xác thực/phân quyền chính thức; khi cần kiểm tra thủ công, dùng AuthenticationTrustResolver hoặc kiểm tra rõ loại Authentication và null.

Repository quyết định **lấy context từ đâu**, còn authorization quyết định **danh tính đó được làm gì**. Có session chứa Authentication hợp lệ không tự cho quyền truy cập mọi đơn hàng, tenant hoặc hành động.

## 14. Bảo mật session và vận hành production

Khi chọn HttpSessionSecurityContextRepository, cần thêm các nguyên tắc:

**Session fixation protection.** Sau login, Spring Security thường thay đổi session ID theo cơ chế phù hợp để giảm nguy cơ cố định session. Không tự ghi đè flow này bằng login tùy biến không được kiểm thử.

**Cookie flags.** Dùng HTTPS, đánh giá Secure/HttpOnly/SameSite cùng chính sách cookie phù hợp. Cookie giúp browser tham chiếu session; bảo vệ cookie là một phần của bảo vệ danh tính.

**CSRF.** Browser tự gửi session cookie khi request phù hợp, nên ứng dụng dùng cookie-based authentication phải quản lý CSRF cho thao tác đổi trạng thái. Việc có SecurityContextRepository hoặc không có repository không tự loại bỏ mọi rủi ro CSRF.

**Logout.** Xóa Authentication khỏi holder mà không hủy session/clear repository có thể khiến context cũ xuất hiện lại ở request sau. Dùng logout support của Spring Security hoặc đảm bảo context và session được xử lý nhất quán.

**Session timeout.** Khi session hết hạn hoặc bị hủy, HttpSessionSecurityContextRepository không còn context cũ để nạp; user phải xác thực lại theo chính sách.

**Nhiều node.** Nếu các request có thể vào nhiều application instance, cần quản lý session phân tán/sticky sessions theo kiến trúc. DelegatingSecurityContextRepository không tự chia sẻ HttpSession giữa các máy.

**Serialization.** Nếu session được nhân bản/serialize, các đối tượng trong context có thể phải tương thích với serialization của session store. Tránh giữ dữ liệu lớn, không cần thiết hoặc nhạy cảm không được bảo vệ trong principal.

**Thread safety và async.** Context từ holder không mặc nhiên chạy theo tác vụ ngoài request thread. Với @Async hoặc thread pool, dùng cách truyền SecurityContext có kiểm soát; đừng đặt strategy GLOBAL để “sửa” mất danh tính, vì có thể trộn người dùng.

**SessionCreationPolicy không phải authorization.** Dù chính sách nào được chọn, vẫn phải xác thực credentials và phân quyền request/method/data đúng cách.

## 15. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Login thành công nhưng request tiếp theo lại chuyển /login | Handler custom chỉ set SecurityContextHolder, quên saveContext | Kiểm tra explicit save, repository của chain và response có commit trước lưu không |
| Request sau mất Authentication dù đã save | Lưu vào Null/RequestAttribute repo nhưng kỳ vọng session, hoặc nạp bằng repo khác | Xem SecurityContextRepository thực sự được dùng ở cả hai request |
| GET sau login bị 401/302 dù có cookie | Cookie/session đã hết hạn, không được gửi đúng domain/path, hoặc server không tìm thấy session | Kiểm tra cấu hình cookie, session store, load balancer và logout |
| User “nhớ” login dù mong stateless | Chain không áp STATELESS hoặc browser vẫn gửi credentials | Xác minh chain matcher, session policy, Authorization header/cookies ở từng request |
| Request error page không có Authentication | Context đã được dọn giữa các dispatcher; chưa lưu request attribute | Xem RequestAttributeSecurityContextRepository và cơ chế ERROR dispatch |
| Có HttpSession nhưng /me vẫn không có user | Session không có SecurityContext hợp lệ; session được tạo vì mục đích khác | Đừng coi sessionPresent là bằng chứng xác thực |
| Thread mới không đọc được Authentication | ThreadLocal không tự truyền theo thread pool/async | Dùng DelegatingSecurityContextExecutor hoặc tích hợp security async |
| Context anonymous nhưng isAuthenticated() true | AnonymousAuthenticationToken có thể đánh dấu authenticated | Dùng quy tắc authenticated() hoặc AuthenticationTrustResolver |
| Viết vào session thủ công mà Spring không nạp lại | Bỏ qua contract SecurityContextRepository hoặc dùng sai attribute | Dùng saveContext chính thức |
| Form login chạy nhưng request POST lỗi 403 | Thiếu CSRF token, không nhất thiết do repository | Kiểm tra CSRF token, form/endpoint, origin và policy |
| Nhiều chain cho kết quả khác nhau | Chain đầu tiên khớp request có repository/session policy khác | Kiểm tra securityMatcher, @Order và repo được chỉ định ở từng chain |

### Quy trình debug có thể lặp lại

1. **Xác định request vào SecurityFilterChain nào**; không đoán từ tên URL. Với nhiều chain, chain đầu tiên khớp được chọn.
2. **Xác minh policy:** IF_REQUIRED/NEVER/STATELESS và cấu hình repository thực tế của chain.
3. **Tách hai mốc:** lúc xác thực thành công đã set Authentication trong holder chưa? Sau đó đã **saveContext** trước response commit chưa?
4. **Quan sát request mới:** browser đã gửi cookie/token gì? Session đó có còn hợp lệ không? Context có được repository nạp lại không?
5. **Phân biệt repository và authorization:** có Authentication không? Có đúng authorities không? Endpoint bị từ chối do auth, CSRF hay rule khác?
6. **Kiểm tra các trường hợp khác:** error dispatch, logout, session timeout, chuyển node, async thread.
7. **Ghi log an toàn:** chỉ log request ID, thời điểm, filter/chain và trạng thái khái quát; không ghi password, session ID, cookie, token hoặc toàn bộ principal nhạy cảm.

## 16. Bài tập tự thực hành

**Bài 1 — Vì sao setContext không đủ?**  
Tự xây dựng login handler dùng AuthenticationManager. Handler đặt context vào SecurityContextHolder nhưng không gọi saveContext, và ứng dụng dùng SecurityContextHolderFilter. Giải thích tại sao request login có thể thấy user trong khi GET /me sau đó lại mất danh tính.

**Gợi ý:** holder quản lý request hiện tại, repository quản lý nơi lưu; explicit save là bước cần thiết nếu muốn sử dụng lại context ở request sau.

**Bài 2 — Chọn repository cho ứng dụng.**  
(a) Trang quản trị MVC có form login và giữ login khi chuyển trang. (b) API nhận bearer token trên mỗi request. (c) Cần phục hồi Authentication trong trang lỗi thuộc cùng request.

**Gợi ý:** (a) HttpSession, thường qua Delegating. (b) Null/stateless khi thiết kế phù hợp. (c) RequestAttribute, thường kết hợp trong Delegating.

**Bài 3 — Phân biệt NEVER và STATELESS.**  
Nếu Servlet container hoặc thành phần khác đã tạo HttpSession, policy nào có thể tiếp tục dùng session đó, và policy nào không dùng HttpSession để nạp SecurityContext?

**Đáp án:** NEVER có thể dùng session có sẵn; STATELESS không dùng HttpSession để lấy SecurityContext.

**Bài 4 — Kiểm thử hai request.**  
Trong ví dụ phần 10, login bằng MockMvc và thực hiện GET /me với session nhận được. Sau đó thực hiện GET /me không truyền session. Vì sao hai request cho kết quả khác nhau?

**Đáp án:** request đầu nạp context lưu theo session; request thứ hai không có session login tương ứng nên bị yêu cầu xác thực lại.

**Bài 5 — Anonymous Authentication.**  
Một đoạn mã tự kiểm tra Authentication.isAuthenticated() để quyết định cho user truy cập chức năng nhạy cảm. Hãy chỉ ra hai vấn đề.

**Đáp án:** Authentication có thể null, và AnonymousAuthenticationToken có thể trả isAuthenticated() true. Dùng authorization của Spring Security hoặc kiểm tra danh tính bằng contract thích hợp.

**Bài 6 — Phân tích lỗi đăng nhập nhiều node.**  
Một ứng dụng lưu context trong HttpSession trên node A. Request sau của cùng browser đến node B nhưng bị coi như chưa đăng nhập. Repository nào là phù hợp với web login? Vì sao dùng DelegatingSecurityContextRepository chưa đủ để sửa lỗi này?

**Đáp án:** HttpSession/Delegating hợp lý với web login, nhưng cần session persistence/chia sẻ hoặc routing phù hợp giữa nodes. Delegating kết hợp các nơi lưu context trong cùng tiến trình/request chứ không tự đồng bộ session giữa máy.

## 17. Checklist quyết định trước khi triển khai

- [ ] Đã phân biệt **SecurityContextHolder hiện tại** với **SecurityContextRepository dùng để nạp/lưu**.
- [ ] Đã chọn mô hình browser session hay API stateless theo yêu cầu thực tế.
- [ ] Đã hiểu **SecurityContextHolderFilter trong Spring Security 6 không tự save ở cuối request**.
- [ ] Với custom login, đã gọi **saveContext đúng repository trước response commit**.
- [ ] Với formLogin chuẩn, đã để framework quản lý login, CSRF và lưu context đúng flow.
- [ ] Nếu dùng HttpSession, đã kiểm tra cookie/session timeout/logout/session fixation.
- [ ] Nếu dùng Null repository, đã bảo đảm mọi request cần xác thực tự mang credentials phù hợp.
- [ ] Nếu dùng RequestAttribute, không kỳ vọng lưu ngữ cảnh cho HTTP request tiếp theo.
- [ ] Nếu dùng Delegating, đã hiểu giới hạn của từng delegate và cấu hình mỗi security chain.
- [ ] Đã kiểm thử request đầu, request tiếp theo, thiếu cookie/token, timeout, logout và error dispatch khi có liên quan.
- [ ] Không log credentials, cookie phiên, access token hoặc toàn bộ SecurityContext ở production.
- [ ] Đã tách kiểm tra quyền truy cập tài nguyên khỏi cơ chế lưu session.

**Kết luận:** SecurityContextHolder cho biết danh tính trong lúc xử lý; SecurityContextRepository quyết định cách nạp và lưu danh tính gắn với HTTP request. Với ứng dụng web duy trì login, HttpSession (thường qua DelegatingSecurityContextRepository) là lựa chọn phổ biến; RequestAttribute phục vụ các dispatch của một request; Null phù hợp khi xác thực độc lập theo từng request. Trong Spring Security 6, hãy luôn xác định rõ **ai tạo Authentication, khi nào saveContext, request sau nạp từ đâu**, rồi chọn chiến lược phù hợp với mô hình session hoặc stateless.
