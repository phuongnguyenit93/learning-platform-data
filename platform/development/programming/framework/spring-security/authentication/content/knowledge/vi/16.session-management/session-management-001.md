# SessionCreationPolicy: ALWAYS, IF_REQUIRED, NEVER và STATELESS

## Mục tiêu và phạm vi

**SessionCreationPolicy** quyết định Spring Security Servlet có chủ động tạo **HttpSession** hay dùng session đã tồn tại khi quản lý trạng thái bảo mật. Đây là lựa chọn quan trọng khi xây dựng đăng nhập bằng form, JSON, HTTP Basic, API key hoặc Bearer token.

Sau bài này, bạn sẽ:

1. Phân biệt chính xác bốn chính sách **ALWAYS**, **IF_REQUIRED**, **NEVER** và **STATELESS**.
2. Giải thích vì sao **không tạo session** khác với **không dùng session để khôi phục SecurityContext**.
3. Kết nối SessionCreationPolicy với **HttpSession**, **JSESSIONID**, **SecurityContextHolder**, **SecurityContextRepository**, **RequestCache** và chiến lược xác thực.
4. Cấu hình Spring Security Servlet bằng Java 17+ và kiểm chứng việc tạo session bằng các request thật.
5. Lựa chọn chính sách phù hợp cho đăng nhập có trạng thái hoặc API không trạng thái, đồng thời tránh những ngộ nhận về CSRF, logout và việc lưu Authentication.

Bài học tập trung vào **Spring Security Servlet** (Spring Boot dùng Spring MVC/Jakarta Servlet). Spring Security WebFlux sử dụng các thành phần quản lý context và session của Reactive stack khác, không áp dụng nguyên xi enum/cấu hình Servlet bên dưới.

## 1. Phải phân biệt bốn khái niệm trước khi chọn policy

### 1.1. HttpSession là gì?

**HttpSession** là phiên phía server thuộc Servlet API. Nó cho phép lưu dữ liệu liên quan một phiên giao tiếp của client: thuộc tính phiên, giỏ hàng, trạng thái biểu mẫu hoặc **SecurityContext** nếu ứng dụng cấu hình như vậy.

Trình duyệt thường giữ cookie **JSESSIONID**; khi request sau mang lại cookie hợp lệ, Servlet container có thể tìm phiên tương ứng.

- **Có HttpSession** không có nghĩa người dùng đã đăng nhập. Một phiên vô danh vẫn có thể chứa CSRF token hoặc dữ liệu của ứng dụng.
- **Không có HttpSession** không có nghĩa request không được xác thực. API nhận Bearer token hoặc HTTP Basic có thể xác thực độc lập trên mỗi request.
- **Có JSESSIONID** không bảo đảm phiên còn tồn tại hoặc có Authentication hợp lệ: session có thể đã hết hạn, bị invalidated hoặc thuộc ứng dụng khác.

### 1.2. SecurityContextHolder khác HttpSession

**SecurityContextHolder** cung cấp **SecurityContext** cho luồng xử lý request hiện tại; bên trong thường có **Authentication** đã xác thực hoặc trạng thái anonymous. Nó không mặc nhiên lưu danh tính cho request tiếp theo.

**SecurityContextRepository** là hợp đồng đọc/lưu SecurityContext giữa các request:

- **HttpSessionSecurityContextRepository** có thể dùng HttpSession để lưu và phục hồi context.
- **RequestAttributeSecurityContextRepository** giữ context trong phạm vi request, hữu ích khi request đi qua nhiều dispatch như ERROR.
- **DelegatingSecurityContextRepository** có thể phối hợp nhiều repository; Spring Security 6 sử dụng dạng này trong cấu hình stateful mặc định.
- **NullSecurityContextRepository** không lưu context cho request sau và không đọc phiên để phục hồi Authentication.

**SessionCreationPolicy** là một đầu vào quan trọng khi Spring Security lựa chọn cách sử dụng session và context repository, nhưng không thay thế toàn bộ cấu hình repository, filter hoặc authentication mechanism.

### 1.3. Ai có thể tạo session?

Không chỉ Spring Security: **Servlet container, Spring MVC, RequestCache, CSRF token repository, thư viện khác và code ứng dụng** có thể tạo hoặc sử dụng HttpSession.

Vì thế cần phân biệt ba câu hỏi:

1. **Spring Security có chủ động tạo HttpSession không?**
2. **Spring Security có dùng HttpSession đã tồn tại để khôi phục SecurityContext không?**
3. **Có thành phần nào khác của ứng dụng tạo HttpSession không?**

Một dự án thực tế có thể trả lời khác nhau cho cả ba. Không được suy ra một câu chỉ từ câu khác.

## 2. Bảng so sánh chính xác bốn SessionCreationPolicy

Enum nằm ở:

~~~java
org.springframework.security.config.http.SessionCreationPolicy
~~~

Bốn giá trị:

| Policy | Spring Security chủ động tạo HttpSession? | Có thể dùng HttpSession đã tồn tại cho SecurityContext? | Đặc trưng |
| --- | --- | --- | --- |
| **ALWAYS** | **Có**: yêu cầu tạo session khi cần bắt đầu request chưa có session | **Có**, theo repository cấu hình | Ưu tiên phiên được tạo sớm |
| **IF_REQUIRED** | **Chỉ khi cần** | **Có**, theo repository cấu hình | Chính sách stateful linh hoạt, phổ biến |
| **NEVER** | **Không chủ động tạo** theo chính sách này | **Có** | Tận dụng session đã tồn tại; không tương đương stateless |
| **STATELESS** | **Không** cho mục đích quản lý bảo mật | **Không** dùng HttpSession để lấy SecurityContext | Xác thực độc lập từng request, phù hợp API stateless |

**Phát biểu cốt lõi từ hợp đồng của enum:**

- **ALWAYS:** luôn tạo HttpSession.
- **IF_REQUIRED:** Spring Security chỉ tạo HttpSession nếu cần.
- **NEVER:** Spring Security không chủ động tạo HttpSession, nhưng vẫn có thể sử dụng HttpSession đang tồn tại.
- **STATELESS:** Spring Security không tạo HttpSession và không dùng nó để lấy SecurityContext.

Có hai điểm cần diễn đạt cẩn thận:

**Thứ nhất, NEVER không phải STATELESS.** Cả hai có thể trông giống nhau nếu client mới chưa có session, nhưng khi một session hợp lệ đã tồn tại và chứa SecurityContext, hành vi khôi phục Authentication có thể khác nhau.

**Thứ hai, STATELESS không cấm code ứng dụng gọi request.getSession(true).** Nó ngăn Spring Security dùng session để khôi phục SecurityContext trong mô hình cấu hình tương ứng; application code hoặc thành phần khác vẫn có thể tự tạo phiên. Không thể khẳng định “server tuyệt đối không bao giờ phát JSESSIONID” chỉ vì chọn STATELESS.

## 3. Hiểu từng policy qua luồng request

### 3.1. ALWAYS — chủ động tạo session

~~~text
GET /public, browser chưa có JSESSIONID
       |
       v
Spring Security với ALWAYS
       |
       +--> đảm bảo có HttpSession
       |
       v
Controller xử lý request
       |
       v
Response có thể kèm Set-Cookie: JSESSIONID=...
~~~

Spring Security có cơ chế tạo session sớm, ví dụ **ForceEagerSessionCreationFilter**, khi cấu hình policy này.

**Điểm cần nhớ:**

- Một request đến endpoint **permitAll()** vẫn có thể tạo HttpSession, dù chưa đăng nhập.
- “ALWAYS” không có nghĩa **mỗi request tạo thêm một session mới** nếu phiên hợp lệ đã tồn tại. Nó có nghĩa cơ chế cố bảo đảm request có phiên.
- Phiên được tạo không tự động chứa người dùng đã xác thực. **Tạo HttpSession** và **lưu Authentication** là hai hoạt động khác nhau.
- Có chi phí quản lý session, bộ nhớ, cookie và có thể cần chia sẻ phiên nếu scale nhiều instance.

**Phù hợp** khi ứng dụng có yêu cầu rõ ràng phải có phiên sớm, ví dụ một luồng web truyền thống dựa vào server-side session. Không nên chọn ALWAYS chỉ để “chắc chắn người dùng đăng nhập được” nếu không có nhu cầu tạo phiên cho mọi request.

### 3.2. IF_REQUIRED — chỉ tạo session khi cần

~~~text
GET /public
  -> Nếu không thành phần nào cần HttpSession: có thể không tạo

GET /login hoặc POST /login theo một luồng có phiên
  -> Thành phần bảo mật/ứng dụng có thể cần HttpSession
  -> Session được tạo khi cần lưu context, CSRF token,
     saved request hoặc dữ liệu khác theo cấu hình
~~~

**IF_REQUIRED** không phải “mỗi request đều có session”. Nó cho phép Spring Security dùng session khi cần thay vì tạo sớm.

Trong các cấu hình stateful, đây thường là lựa chọn thực dụng cho form login hoặc JSON login có cookie phiên: khách chưa đăng nhập có thể chưa cần session, còn một lần login thành công có thể tạo session để lưu SecurityContext.

Tuy nhiên, sự tồn tại của policy IF_REQUIRED **không tự lưu** Authentication được tạo trong custom controller. Với Spring Security 6, custom authentication code cần dùng đúng **SecurityContextRepository.saveContext(...)** nếu muốn duy trì đăng nhập giữa các request.

### 3.3. NEVER — không chủ động tạo, nhưng có thể dùng phiên cũ

~~~text
Client A: chưa có HttpSession
  -> Spring Security không chủ động tạo session vì policy NEVER

Client B: đã có JSESSIONID hợp lệ
  -> Có thể khôi phục SecurityContext từ HttpSession đã tồn tại
     nếu repository và cơ chế hiện tại cho phép
~~~

Đây là chính sách dễ hiểu nhầm nhất.

- **NEVER** không có nghĩa vô hiệu hóa mọi HttpSession.
- Nếu một thành phần khác tạo session trước đó, Spring Security có thể sử dụng nó.
- Một số thành phần như **RequestCache** vẫn có thể lưu request để xử lý sau đăng nhập và vô tình khiến bạn quan sát thấy session. Tài liệu Spring Security đặc biệt nhắc đến trường hợp này.
- Nếu bạn cần đảm bảo không khôi phục Authentication từ HttpSession, chọn **STATELESS** thay vì NEVER và kiểm tra repository.

**Tình huống:** một ứng dụng có sẵn session do giao diện web hoặc module khác tạo. Bạn chọn NEVER cho một security chain. SecurityContext đã tồn tại có thể được đọc lại, nên request có thể vẫn được xác thực **dù không gửi header credential mới**. Không kết luận đó là lỗi dựa trên tên “NEVER”.

### 3.4. STATELESS — không phục hồi Authentication từ session

~~~text
GET /api/me
Authorization: Bearer <token hợp lệ>
     |
     v
Filter xác thực token của request này
     |
     v
SecurityContextHolder trong request này
     |
     v
Authorization -> Controller -> Response
     |
     v
Request kế tiếp cần tự cung cấp credential
~~~

Với cấu hình mặc định phù hợp, **STATELESS** khiến Spring Security không lấy SecurityContext từ HttpSession, và thường sử dụng **NullSecurityContextRepository** cùng cách tránh lưu request cần xác thực vào session.

Lưu ý:

- **STATELESS không đồng nghĩa không có SecurityContextHolder.** Request hiện tại vẫn có context sau khi authentication filter xác thực thành công.
- **STATELESS không tự xác thực client.** Bạn vẫn cần Basic, Bearer, API key hoặc cơ chế phù hợp.
- **STATELESS không đồng nghĩa không có cookie trong toàn hệ thống.** Thành phần ứng dụng khác vẫn có thể phát cookie/session.
- **STATELESS không đồng nghĩa không bị CSRF.** Nếu trình duyệt tự gửi Basic credential hoặc cookie khác đến server, vẫn phải đánh giá CSRF theo cách client hoạt động.
- **STATELESS không có nút logout kiểu hủy HttpSession** cho token Bearer tự chứa; việc thu hồi token phụ thuộc cơ chế phát hành, thời hạn và blacklist/revocation nếu có.

Policy này phù hợp cho **REST API dùng Authorization header trên mỗi request**, nhất là Bearer token hoặc API key, khi server không muốn dùng session để duy trì Authentication.

## 4. NEVER và STATELESS khác nhau chính xác ở đâu?

Giả sử Servlet container đã có một session hợp lệ trước khi request được đưa qua Spring Security.

| Tình huống | NEVER | STATELESS |
| --- | --- | --- |
| Client không có session | Không chủ động tạo phiên vì policy | Không chủ động tạo phiên cho security context |
| Client có JSESSIONID cũ | Có thể dùng session cũ | Không dùng session cũ để lấy SecurityContext |
| Session chứa Authentication đã được lưu hợp lệ | Có thể phục hồi theo repository | Không phục hồi từ session theo cấu hình stateless |
| Code controller gọi request.getSession(true) | Code ứng dụng vẫn có thể tạo | Code ứng dụng vẫn có thể tạo |
| Client chỉ mang JSESSIONID mà không có header Authorization | Có thể đã xác thực nếu context lưu trong session | Không được xác thực **chỉ nhờ context của HttpSession** |
| Trường hợp điển hình | Ứng dụng dùng lại session có sẵn và muốn hạn chế tạo thêm | API không giữ trạng thái xác thực phía server |

**Ví dụ có thể quan sát:**

1. Một luồng đăng nhập đáng tin cậy lưu Authentication cho user “alice” trong HttpSession.
2. Client giữ cookie JSESSIONID của session đó.
3. Client gọi tài nguyên bảo vệ nhưng không gửi Bearer/Basic header.

Nếu chain dùng **NEVER** cùng repository đọc HttpSession, nó có thể nhận lại Authentication “alice”. Nếu chain dùng **STATELESS** và không override repository trái với chính sách, context trong session cũ **không được dùng** để xác thực request.

Cần phân biệt “có thể” và “chắc chắn”: kết quả phụ thuộc **SecurityContextRepository**, các filter xác thực khác, session có còn hợp lệ, chain nào khớp URL và có cơ chế session/cookie khác không.

## 5. Cấu hình SessionCreationPolicy trong Spring Security Servlet

Cách dùng DSL cho một SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    );
    return http.build();
}
~~~

Import:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
~~~

Đổi **SessionCreationPolicy.STATELESS** thành **ALWAYS**, **IF_REQUIRED** hoặc **NEVER** để chọn chiến lược khác. Cấu hình có ý nghĩa cho đúng **SecurityFilterChain** chứa nó.

### Khi có nhiều SecurityFilterChain

Ví dụ hệ thống có giao diện browser có login qua session và REST API có Bearer token. Thiết kế có thể tách:

~~~java
// Đoạn minh họa cấu hình hai chain, chưa phải ứng dụng độc lập.
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .sessionManagement(sm -> sm
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    // Bổ sung cơ chế Bearer/API-key cụ thể tại đây.
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .sessionManagement(sm -> sm
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Với đoạn minh họa này cần import **@Bean, @Order, Customizer** và cấu hình đầy đủ authentication mechanism cho API. Nó minh họa việc **chọn policy theo chain**, không phải dự án chạy độc lập.

Đặc biệt lưu ý: cookie JSESSIONID do giao diện web tạo có thể vẫn được trình duyệt gửi khi gọi **/api/**, nhưng API chain STATELESS không dùng cookie đó để khôi phục SecurityContext. Với ứng dụng hỗn hợp, hãy kiểm thử **matcher, thứ tự chain, CSRF, CORS, cookie path và authorization**. Không suy ra chính sách của toàn ứng dụng chỉ từ một bean.

## 6. Ví dụ Java 17+ chạy được: kiểm chứng bốn policy

Ta tạo một ứng dụng Spring Boot Servlet nhỏ cho phép chọn policy bằng tham số khởi động. Ví dụ chỉ nhằm quan sát khi nào session được tạo; cơ chế xác thực là HTTP Basic.

**Điểm quan trọng:** HTTP Basic thường xác thực credential trên mỗi request và không tự trở thành login session. Vì thế **/me** được gọi bằng Basic hợp lệ không chứng minh SecurityContext đã được lưu trong HttpSession. Đừng nhầm phép đo “sessionExists” với phép đo “đang đăng nhập”.

### 6.1. Gradle project

Yêu cầu **JDK 17+**, Gradle tương thích Spring Boot 3.5.x. Tạo **settings.gradle**:

~~~groovy
rootProject.name = 'session-policy-demo'
~~~

Tạo **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Plugin Spring Boot quản lý classpath/dependency cho ví dụ; không thể chạy file Java độc lập bằng **javac** mà thiếu thư viện Spring.

### 6.2. Ứng dụng

Tạo file **src/main/java/example/session/SessionPolicyDemoApplication.java**:

~~~java
package example.session;

import java.util.Locale;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionPolicyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionPolicyDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, Environment environment) throws Exception {

        String configured = environment.getProperty(
            "demo.session-policy", "IF_REQUIRED"
        );
        SessionCreationPolicy policy = SessionCreationPolicy.valueOf(
            configured.trim().toUpperCase(Locale.ROOT)
        );

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/probe",
                    "/demo/create-session"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .requestCache(cache -> cache.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(policy)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(passwordEncoder.encode("change-me"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class Api {

        public record Probe(boolean sessionExists) {
        }

        @GetMapping("/probe")
        Probe probe(HttpServletRequest request) {
            // false => KHÔNG tự tạo session để đo.
            HttpSession session = request.getSession(false);
            return new Probe(session != null);
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello, " + authentication.getName();
        }

        @GetMapping("/demo/create-session")
        String createSession(HttpServletRequest request) {
            // Chỉ để chứng minh APPLICATION có thể tự tạo session.
            // Không đưa endpoint tạo trạng thái bằng GET lên production.
            request.getSession(true).setAttribute("demo", "created");
            return "application-created-session";
        }
    }
}
~~~

**Giải thích lựa chọn trong ví dụ:**

1. **/probe** dùng **request.getSession(false)**. Điều này rất quan trọng: nếu dùng **getSession()** hoặc **getSession(true)** khi đo, controller sẽ tự tạo session, khiến bạn kết luận sai về policy.
2. **/demo/create-session** cố tình gọi **getSession(true)** để chứng minh code ứng dụng vẫn có khả năng tạo HttpSession dưới cả bốn policy. Endpoint chỉ phục vụ môi trường học tập và nên xóa khỏi sản phẩm thực; GET tạo trạng thái không phải thiết kế HTTP lý tưởng.
3. **/me** yêu cầu một request có Authentication hợp lệ; trong ví dụ client có thể gửi **Authorization: Basic** mỗi lần.
4. **requestCache.disable()** ngăn saved request từ cơ chế security làm phép đo session bị nhiễu. Ứng dụng không sử dụng form login hay redirect sau đăng nhập.
5. Không tắt **CSRF** một cách tùy tiện. Các endpoint demo ở đây là GET, và không có chức năng cập nhật nghiệp vụ. Trong hệ thống thực dùng browser/cookie, CSRF cần đánh giá riêng.
6. User **demo/change-me** chỉ để thử trên máy cá nhân; không nhúng credential thật vào mã nguồn.

### 6.3. Chạy và quan sát

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun --args='--demo.session-policy=ALWAYS'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.session-policy=ALWAYS"
~~~

Mặc định server lắng nghe tại **http://localhost:8080** nếu chưa cấu hình cổng khác. Dừng app và đổi tham số thành **IF_REQUIRED**, **NEVER**, **STATELESS** để thử lần lượt, dùng phiên cookie mới cho mỗi lần thử.

**A. Quan sát request vô danh đầu tiên:**

~~~bash
curl -i http://localhost:8080/probe
~~~

Trong môi trường ví dụ sạch, chưa gửi cookie và không có thành phần ngoài tạo session, body kỳ vọng:

| Policy chạy app | Body /probe ở request đầu |
| --- | --- |
| ALWAYS | **{"sessionExists":true}** |
| IF_REQUIRED | **{"sessionExists":false}** |
| NEVER | **{"sessionExists":false}** |
| STATELESS | **{"sessionExists":false}** |

Với **ALWAYS**, response cũng có thể chứa header **Set-Cookie: JSESSIONID=...** khi tạo session mới. Cookie, header và thứ tự hiển thị cụ thể phụ thuộc Servlet container/cấu hình. Không suy ra “không có session” chỉ từ việc không nhìn thấy cookie: endpoint **/probe** báo session thực tế tại request.

**B. Basic xác thực một request nhưng không chứng minh có login session:**

~~~bash
curl -sS -u demo:change-me http://localhost:8080/me
# hello, demo

curl -i http://localhost:8080/me
# HTTP/1.1 401 ... (trạng thái thường gặp khi thiếu credential)
~~~

Đây là hai request khác nhau. Trong cấu hình minh họa, Basic phục vụ xác thực request; ví dụ không thêm cấu hình lưu Authentication của Basic filter vào HttpSession. Bản thân **IF_REQUIRED** hoặc **ALWAYS** không biến Basic thành “đăng nhập một lần, những lần sau chỉ cần cookie”.

**C. Chứng minh session do code ứng dụng tạo có thể tồn tại dù STATELESS:**

~~~bash
curl -i -c demo-cookies.txt \
  http://localhost:8080/demo/create-session

curl -sS -b demo-cookies.txt http://localhost:8080/probe
# {"sessionExists":true}
~~~

Bộ cookie **demo-cookies.txt** lưu JSESSIONID được Servlet container phát cho endpoint tạo session. Khi request sau mang lại cookie hợp lệ, controller thấy HttpSession.

Nếu đang chạy **STATELESS**, kết quả trên **không trái policy**: ứng dụng cố ý tự tạo phiên. Quan trọng là Spring Security **không sử dụng phiên đó để khôi phục SecurityContext** theo cấu hình mặc định stateless. Chỉ có session không đồng nghĩa đã có Authentication.

**D. Không để cookie của phép thử trước làm nhiễu phép thử mới.** Khi chuyển policy, hãy chạy /probe với request **không gửi Cookie**, hoặc dùng cookie jar riêng cho mỗi policy. Nếu sử dụng một cookie cũ, bạn có thể vô tình đang đo phiên đã tồn tại.

### 6.4. Những gì demo chứng minh và không chứng minh

Demo quan sát trực tiếp:

- ALWAYS chủ động tạo session trong một request chưa có phiên.
- IF_REQUIRED/NEVER/STATELESS không cần tạo session cho /probe trong cấu hình đơn giản này.
- Code ứng dụng có thể tự tạo phiên dưới mọi policy.
- Authentication qua Basic không phụ thuộc nhất thiết vào HttpSession.

Demo **chưa chứng minh** cách một Authentication được lưu/khôi phục từ session, vì không triển khai một cơ chế login ghi SecurityContext. Để kiểm chứng điểm đó cần thêm form/JSON login có session và repository phù hợp, cùng test nhiều request có cookie.

## 7. SecurityContextRepository và việc lưu Authentication trong Spring Security 6

### 7.1. Vì sao policy không đủ để “đăng nhập một lần”?

Một luồng login tùy chỉnh thường đi qua:

~~~text
POST /login
  -> AuthenticationManager xác minh credential
  -> (nếu dùng session) SessionAuthenticationStrategy kiểm tra,
     bảo vệ session fixation và chính sách phiên
  -> tạo SecurityContext chứa Authentication thành công
  -> SecurityContextHolder sử dụng trong request hiện tại
  -> SecurityContextRepository.saveContext(...) để phục hồi sau này
  -> Response + cookie phù hợp
~~~

Trong Spring Security 6, **SecurityContextHolderFilter** thường đọc context từ repository và thiết lập cho request; nó **không mặc nhiên lưu** các thay đổi tự bạn đưa vào holder. **SecurityContextPersistenceFilter** và **SessionManagementFilter** không được bật mặc định theo cách của Spring Security 5.

Với **custom controller/filter**, nếu muốn dùng HttpSession để giữ đăng nhập, cần đảm bảo:

1. Chọn policy phù hợp, thường **IF_REQUIRED**.
2. Có repository đọc/lưu qua session, ví dụ **HttpSessionSecurityContextRepository**.
3. Sau khi **AuthenticationManager.authenticate(...)** thành công, gọi **SessionAuthenticationStrategy** khi cơ chế phiên yêu cầu, đặc biệt bảo vệ session fixation hoặc concurrent sessions.
4. Tạo SecurityContext mới, đặt Authentication đã xác thực và gọi **repository.saveContext(context, request, response)**.
5. Request sau gửi lại cookie phiên hợp lệ và filter đọc cùng repository.

Đoạn sau minh họa **bước lưu sau khi đã xác thực**, nằm trong custom authentication mechanism đã chuẩn bị đầy đủ dependencies; không phải ứng dụng độc lập:

~~~java
// authentication là kết quả hợp lệ từ AuthenticationManager.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// Cùng repository mà SecurityFilterChain dùng để đọc lại.
securityContextRepository.saveContext(context, request, response);
~~~

**Không dùng đoạn này để cố biến cấu hình STATELESS thành đăng nhập có phiên.** Nếu bạn override repository để lưu state, toàn bộ kiến trúc phải thống nhất theo lựa chọn stateful thực sự.

### 7.2. Chú ý đến RequestCache

**RequestCache** có thể lưu URL của request bị từ chối để người dùng được chuyển lại sau khi đăng nhập. Triển khai **HttpSessionRequestCache** có thể dùng HttpSession cho saved request.

Vì thế trong ứng dụng chọn **NEVER**, vẫn có thể thấy HttpSession được tạo do saved request, tùy cấu hình/cơ chế liên quan. Nếu API chỉ trả JSON và không cần redirect về request trước login, có thể vô hiệu hóa lưu request:

~~~java
http.requestCache(cache -> cache.disable());
~~~

Hoặc cấu hình **NullRequestCache** theo yêu cầu. Khi chẩn đoán phiên xuất hiện ngoài ý muốn, không chỉ kiểm tra SessionCreationPolicy; hãy kiểm tra request cache, CSRF token repository, các view/template, controller và thư viện khác.

### 7.3. Chú ý đến CSRF token và session

**HttpSessionCsrfTokenRepository** có thể lưu token CSRF trong session. Việc truy cập/lưu CSRF token có thể dẫn đến HttpSession, tùy repository và cách request được xử lý.

Nếu ứng dụng xác thực bằng cookie hoặc trình duyệt có khả năng tự gửi credential (kể cả HTTP Basic đã cache), rủi ro CSRF cần được đánh giá. **STATELESS không tự động miễn CSRF.**

Đối với API Bearer token gửi **chủ động qua Authorization header** từ client không phải browser, hoặc cơ chế không tự đính kèm credential, có thể lựa chọn cấu hình CSRF tương ứng sau khi phân tích threat model. Không tắt CSRF chỉ vì tên endpoint có “/api”.

## 8. Chọn policy theo tình huống ứng dụng

| Ứng dụng | Policy thường phù hợp | Điều kiện đi kèm |
| --- | --- | --- |
| Web MVC đăng nhập form, giữ phiên bằng JSESSIONID | **IF_REQUIRED** | Repository lưu/đọc context, CSRF, session fixation và logout được cấu hình |
| JSON login trên browser, sau đó dùng cookie phiên | **IF_REQUIRED** | Custom login phải lưu SecurityContext rõ ràng và xử lý SessionAuthenticationStrategy |
| Ứng dụng cần tạo HttpSession trước khi login | **ALWAYS** | Có lý do thực sự cho chi phí session mỗi client/request |
| Dự án tích hợp với session đã được thành phần khác tạo | **NEVER** có thể phù hợp | Chấp nhận khôi phục SecurityContext từ session cũ; kiểm tra repository và request cache |
| API xác thực bằng Bearer JWT hoặc opaque token mỗi request | **STATELESS** | Có authentication filter/resource server; xử lý expiry, signature/introspection, revocation |
| API key hoặc HTTP Basic trên mỗi request | **STATELESS** thường phù hợp | TLS, credential management, không dựa vào cookie phiên để lưu Authentication |
| Ứng dụng hỗn hợp web + API | **Phân chain:** web IF_REQUIRED, API STATELESS | Security matcher, thứ tự chain, CSRF/CORS/cookie rõ ràng |

Bảng là hướng thiết kế, **không thay thế phân tích nhu cầu**. Một cơ chế về bản chất là stateless như Basic vẫn có thể được cấu hình lưu Authentication trong session, nhưng điều đó là một quyết định khác cần kiểm thử cụ thể.

## 9. Những lỗi diễn giải thường gặp

### Lỗi 1: “NEVER là stateless”

Sai. NEVER không chủ động tạo phiên theo policy nhưng có thể dùng phiên đã tồn tại, gồm cả SecurityContext được lưu hợp lệ. Nếu mục tiêu không phụ thuộc HttpSession để nhận diện người dùng, chọn STATELESS.

### Lỗi 2: “STATELESS nghĩa là không bao giờ có JSESSIONID”

Sai. Servlet code hoặc CSRF repository/thành phần khác vẫn có thể tạo session. STATELESS điều khiển cách Spring Security sử dụng session cho context, không phải hệ thống chặn mọi lời gọi **getSession(true)**.

### Lỗi 3: “ALWAYS nghĩa là đã đăng nhập”

Sai. HttpSession có thể hoàn toàn vô danh. Cần có Authentication đã xác thực và được khôi phục đúng cách; một cookie phiên không đủ.

### Lỗi 4: “IF_REQUIRED tự lưu Authentication khi tôi gọi setContext”

Sai trong mô hình Spring Security 6 dùng explicit save. Custom controller/filter phải gọi đúng **SecurityContextRepository.saveContext(...)** nếu muốn duy trì qua request tiếp theo.

### Lỗi 5: “HttpSession vừa xuất hiện chắc do sessionManagement()”

Không đủ căn cứ. Kiểm tra **RequestCache**, CSRF, form login, controller gọi getSession(), servlet framework và các thư viện khác. Đừng chỉ nhìn Set-Cookie.

### Lỗi 6: “Dùng Basic mà request sau không gửi Authorization vẫn phải được đăng nhập vì có IF_REQUIRED”

Không đúng như một bảo đảm mặc định. Basic thường xác thực mỗi request; muốn lưu Basic Authentication trong session cần thiết lập repository/lifecycle phù hợp cho filter đó.

### Lỗi 7: “Tôi bật STATELESS nên không có SecurityContextHolder”

Sai. Filter vẫn đặt Authentication cho request hiện tại. Điều bị ngăn là dựa vào HttpSession để khôi phục Authentication trong request mới.

### Lỗi 8: “STATELESS có thể tắt CSRF trong mọi trường hợp”

Sai. Nếu trình duyệt tự gửi credential như Basic hoặc cookie, vẫn có đường CSRF. Quyết định phụ thuộc client, origin, phương thức xác thực và tài nguyên thay đổi trạng thái.

### Lỗi 9: “Tôi đặt nhiều SecurityFilterChain nhưng một policy sẽ áp dụng toàn hệ thống”

Sai. Mỗi chain có cấu hình riêng; request khớp chain nào mới đi qua filter/context policy của chain đó. Đối với ứng dụng đa chain, test matcher và thứ tự.

### Lỗi 10: “SessionCreationPolicy thay thế session fixation, logout và concurrent session control”

Sai. Tạo/không tạo phiên là một vấn đề; đổi ID sau login, giới hạn phiên, invalidation, timeout và đăng xuất là các trách nhiệm khác. Không suy ra chúng chỉ từ policy.

### Lỗi 11: “Cookie cũ tồn tại nên tôi đã khôi phục Authentication”

Sai. Cookie có thể trỏ đến session bị vô hiệu hóa/hết hạn, session vô danh hoặc session không chứa SecurityContext; xác nhận từ Authentication thực sự trong request.

### Lỗi 12: “STATELESS tự ngăn mọi lưu state phía server”

Sai. API vẫn có thể dùng database, cache, rate limiter, blacklist/revocation và dữ liệu nghiệp vụ. STATELESS nói về **trạng thái xác thực dựa vào HttpSession**, không phải tuyên bố toàn bộ hệ thống không có trạng thái.

## 10. Chẩn đoán thực tế và chiến lược kiểm thử

Khi kiểm tra một ứng dụng, nên quan sát:

1. **Request đầu tiên**: có cookie JSESSIONID không, filter có tạo session trước controller không?
2. **Trong controller**: gọi **request.getSession(false)** để kiểm tra mà không tạo mới.
3. **Sau xác thực**: SecurityContext được đặt bởi cơ chế nào, có lưu vào repository không?
4. **Request kế tiếp**: client gửi cookie hay Authorization header; Authentication đến từ session hay được xác thực lại?
5. **Khi lỗi 401/403**: phân biệt thiếu Authentication với đã xác thực nhưng thiếu quyền.
6. **SavedRequest/CSRF**: có thành phần nào tạo session một cách gián tiếp không?
7. **Multi-chain**: kiểm tra SecurityFilterChain thực tế khớp URL, đặc biệt khi web và API chia riêng.
8. **Session lifecycle**: hết hạn, đổi session ID sau login, logout, giới hạn phiên và chia sẻ state khi có nhiều instance.

### Kịch bản tối thiểu nên kiểm thử

| Scenario | Điều cần kiểm chứng |
| --- | --- |
| Anonymous GET, không cookie, ALWAYS | HttpSession được tạo theo thiết kế |
| Anonymous GET, không cookie, IF_REQUIRED | Session không cần thiết có thể không được tạo |
| Anonymous GET, không cookie, NEVER | Security không chủ động tạo session |
| Anonymous GET, không cookie, STATELESS | Không khôi phục Authentication từ HttpSession |
| Request có session cũ chứa context hợp lệ, NEVER | Có thể lấy Authentication từ session theo repository |
| Request có session cũ chứa context hợp lệ, STATELESS | Không dùng context trong session làm Authentication |
| API Bearer hợp lệ rồi request mới thiếu token, STATELESS | Request mới không thừa hưởng Authentication |
| Controller tự getSession(true) khi policy STATELESS | Session vẫn có thể xuất hiện nhưng không được dùng để khôi phục SecurityContext |
| JSON login có IF_REQUIRED nhưng quên saveContext | Login request có thể thành công, request sau có thể mất Authentication |
| Logout/session timeout | Cookie cũ không còn là bằng chứng đăng nhập hợp lệ |

**Lưu ý QA:** không viết test chỉ gọi **SessionCreationPolicy.values()** rồi so tên bốn enum; test đó không kiểm chứng hành vi ứng dụng. Hãy test các request thật hoặc **MockMvc** để quan sát session, SecurityContext và HTTP behavior.

### Nếu cần dùng Spring Security Test

Với dự án có test dependencies Spring Boot, có thể dùng **MockMvc** để kiểm tra GET /probe và Authentication. Tuy nhiên, session chính sách còn tương tác với servlet/container và repository. Một phép thử thực tế với curl, cookie jar và server chạy thật vẫn hữu ích để phát hiện vấn đề cookie/Set-Cookie mà mock không mô phỏng hết.

Đối với ứng dụng nhiều instance, cần kiểm chứng session replication hoặc **Spring Session** nếu đăng nhập stateful, còn API stateless cần kiểm chứng mọi instance đều xác minh token và chính sách thu hồi nhất quán. SessionCreationPolicy không tự triển khai chia sẻ phiên qua cluster.

## 11. Bài tập tự kiểm tra

**Câu 1.** NEVER và STATELESS đều có thể không tạo session cho request mới. Điều gì khiến chúng khác nhau?

**Đáp án:** NEVER vẫn có thể dùng session cũ để khôi phục SecurityContext; STATELESS không dùng HttpSession để khôi phục SecurityContext.

**Câu 2.** Bạn chọn ALWAYS, gọi /public và thấy JSESSIONID. Người dùng đã được xác thực chưa?

**Đáp án:** Chưa thể kết luận. HttpSession vô danh cũng có thể tồn tại; cần Authentication hợp lệ.

**Câu 3.** Bạn chọn IF_REQUIRED, custom JSON controller xác thực thành công và set SecurityContextHolder. Request sau có cookie nhưng vẫn nhận 401. Vì sao?

**Đáp án:** Có thể chưa gọi SecurityContextRepository.saveContext(...) hoặc repository dùng để lưu không trùng với repository được security chain đọc lại. Cần kiểm tra session strategy và chain.

**Câu 4.** Có người nói “STATELESS tuyệt đối không có cookie, nên nhìn thấy JSESSIONID là bug Spring Security”. Đúng không?

**Đáp án:** Không. Code ứng dụng/thư viện khác vẫn có thể tạo HttpSession và cookie. Điều cần kiểm tra là Spring Security có khôi phục Authentication từ HttpSession không.

**Câu 5.** Ứng dụng dùng API Bearer token mỗi request và không cần phiên đăng nhập phía server. Chọn gì?

**Đáp án:** Thường chọn STATELESS cùng cơ chế xác minh Bearer token. Vẫn cần xử lý HTTPS, lỗi token, phân quyền và CSRF theo threat model.

**Câu 6.** NEVER vẫn tạo session khi truy cập URL cần đăng nhập. Bắt đầu debug ở đâu?

**Đáp án:** Xem RequestCache lưu saved request, CSRF token repository, controller/filter gọi getSession(true), cấu hình chain và các thành phần ngoài SessionManagement.

**Câu 7.** Basic trả 200 ở request đầu có Authorization, request thứ hai không Authorization trả 401 dù chọn IF_REQUIRED. Đây là lỗi policy?

**Đáp án:** Không nhất thiết. Basic không mặc nhiên có login session; cần xem cơ chế lưu SecurityContext của Basic filter và request kế tiếp.

**Câu 8.** Tại sao không nên chỉ dùng getSession(true) trong endpoint kiểm thử “có session không”?

**Đáp án:** Vì chính phép đo tạo session. Dùng getSession(false) để xem phiên đã tồn tại, và tạo phiên chủ động ở một bước tách biệt nếu cần học tình huống đó.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — SessionCreationPolicy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/http/SessionCreationPolicy.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Authentication Persistence](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Session Management Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
