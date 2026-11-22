# Kiểm soát FORWARD, ERROR và ASYNC bằng dispatcherTypeMatchers trong Spring Security Servlet

**Bài học:** Phân quyền HTTP. **Môi trường minh họa:** Java 17+, Spring Boot 3.3.5, Spring Security 6.x và Jakarta Servlet. Bài này hướng dẫn dùng <code>dispatcherTypeMatchers</code> để tránh chặn nhầm FORWARD/ERROR/ASYNC dispatch, đồng thời không vô tình miễn phân quyền cho controller hoặc service nhạy cảm.

**Điểm quan trọng:** Một HTTP request do browser gửi có thể tạo ra nhiều lượt Servlet dispatch nội bộ. Những lượt này có thể có DispatcherType khác nhau. Security rule trên URL không phải lúc nào cũng tự động được áp dụng theo cùng cách cho REQUEST, FORWARD, ERROR và ASYNC. Muốn kiểm soát đúng phải xem cả **Servlet filter registration**, **SecurityFilterChain** được chọn, **thứ tự authorization matcher** và **path đích của dispatch**.

## 1. Hiểu DispatcherType trước khi cấu hình

<code>jakarta.servlet.DispatcherType</code> là enum mô tả kiểu dispatch của Servlet container, không phải HTTP method.

| DispatcherType | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| <code>REQUEST</code> | Client gửi HTTP request trực tiếp | GET /reports |
| <code>FORWARD</code> | Server chuyển xử lý nội bộ sang resource khác | Spring MVC <code>forward:/internal/render</code> |
| <code>ERROR</code> | Container xử lý lỗi và gọi error page/servlet | Gửi 500 rồi gọi /error |
| <code>ASYNC</code> | Servlet tiếp tục request đã xử lý bất đồng bộ | MVC <code>Callable</code> trả kết quả, sau đó redispatch |
| <code>INCLUDE</code> | Resource được đưa nội dung vào response của resource khác | <code>RequestDispatcher.include(...)</code> |

GET/POST nói về HTTP method, còn REQUEST/FORWARD/ERROR/ASYNC nói về **lượt xử lý Servlet**. Một GET có thể có cả REQUEST rồi FORWARD hoặc REQUEST rồi ASYNC. Header tùy ý như <code>X-Dispatcher-Type: FORWARD</code> không thể trực tiếp thay đổi dispatcher type; quyền quyết định thuộc container. Tuy nhiên internal dispatch target có thể bị tác động gián tiếp nếu một controller nhận path do client gửi và sử dụng path đó để forward.

### FORWARD

~~~text
Browser GET /view
  |
  v
DispatcherType.REQUEST /view
  |
  | MVC Controller trả "forward:/internal/render"
  v
DispatcherType.FORWARD /internal/render
  |
  v
HTTP response
~~~

### ERROR

~~~text
Browser GET /error-trigger
  |
  v
DispatcherType.REQUEST /error-trigger
  |
  | response.sendError(500)
  v
DispatcherType.ERROR /error
  |
  v
Trang lỗi với status 500
~~~

### ASYNC

~~~text
Browser GET /async/report
  |
  v
DispatcherType.REQUEST /async/report
  |
  | Spring MVC Callable bắt đầu async processing
  v
Task trên worker thread xử lý
  |
  v
DispatcherType.ASYNC /async/report
  |
  v
MVC hoàn tất response
~~~

Đây là cơ chế bên trong server. Không đồng nhất ASYNC dispatch với một công việc chạy trong <code>CompletableFuture</code> bất kỳ: tác vụ chạy thread khác không tự tạo Servlet ASYNC dispatch nếu không có Servlet async lifecycle.

## 2. Hai lớp phải bật đúng: filter mapping và authorization

**Lớp thứ nhất là Filter registration.** Servlet container chỉ gọi security filter ở dispatcher types được đăng ký. Nếu <code>springSecurityFilterChain</code> không được mapping tới FORWARD, thì rule <code>dispatcherTypeMatchers(FORWARD)</code> sẽ không được đánh giá ở lượt FORWARD đó.

**Lớp thứ hai là Spring Security authorization.** Khi security filter chain xử lý dispatch, <code>authorizeHttpRequests</code> sẽ xét các matcher để quyết định quyền.

Ví dụ một đoạn cấu hình:

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .anyRequest().authenticated());
~~~

Đoạn trên cho phép ERROR **nếu security filter thật sự chạy trên ERROR dispatch**. Nó không tự thay đổi Servlet filter registration.

Trong Spring Boot 3.x, có thể chỉ định dispatcher types của security filter bằng property:

~~~yaml
spring:
  security:
    filter:
      dispatcher-types: request, async, error, forward
~~~

Ví dụ chủ động thêm FORWARD để test. Không áp dụng trực tiếp property này cho một ứng dụng Servlet thuần không dùng Spring Boot; khi đó phải đăng ký filter qua cơ chế Servlet container phù hợp. Khi deploy WAR, thêm reverse proxy hoặc thay đổi bootstrap, xác minh mapping thực tế thay vì suy ra từ code.

Ngoài ra, một số filter bên trong chain có logic riêng về việc chạy ở ERROR/ASYNC dispatch, ví dụ các filter kế thừa <code>OncePerRequestFilter</code>. Container gọi chain không có nghĩa mọi filter con đều chạy hoàn toàn giống REQUEST. Vì thế test trên Servlet container thật quan trọng.

## 3. dispatcherTypeMatchers: cú pháp, thứ tự và quyền

DSL Spring Security có thể dùng:

~~~java
import jakarta.servlet.DispatcherType;

// Trích đoạn bên trong bean SecurityFilterChain:
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
    .dispatcherTypeMatchers(DispatcherType.ASYNC).authenticated()
    .anyRequest().denyAll());
~~~

<code>dispatcherTypeMatchers</code> tạo matcher theo kiểu dispatch; sau đó kết hợp với <code>permitAll</code>, <code>authenticated</code>, <code>hasRole</code>, <code>hasAuthority</code>, <code>denyAll</code>...

**Đây chỉ là minh họa API, không phải policy production khuyến nghị.** Cho phép **mọi** FORWARD có thể khiến một forward vào endpoint nhạy cảm vượt qua URL authorization. Cho phép ASYNC chỉ dựa vào trạng thái authenticated cũng có thể làm yếu rule hasRole của URL đích. Chính sách mẫu ở dưới sẽ giới hạn theo cả dispatcher type và path.

### Matcher đầu tiên khớp thắng

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll());
~~~

Nếu ERROR dispatch có path thuộc /admin/**, rule ERROR ở trước khớp và được dùng. Đảo hai rule có thể khiến URL rule đòi ADMIN ngay cả khi container chỉ đang render một lỗi chung. Thứ tự là một phần của chính sách bảo mật.

Đừng nhầm thứ tự authorization matcher với thứ tự <code>SecurityFilterChain</code>. Khi có nhiều chain, <code>FilterChainProxy</code> chọn **chain đầu tiên** khớp request; authorization rules ở các chain khác không được xét. Một policy cho ERROR trong chain không được chọn thì không có tác dụng.

## 4. FORWARD: allow theo path, không mở rộng tùy ý

Spring MVC <code>@Controller</code> có thể trả view name <code>forward:/internal/render</code>. Với một trang cần ROLE_USER, ta mong đợi:
- Browser gửi REQUEST <code>/view</code>: cần ROLE_USER.
- MVC thực hiện FORWARD tới <code>/internal/render</code>: chỉ cho phép target này và vẫn kiểm tra ROLE_USER.
- Browser gọi trực tiếp REQUEST <code>/internal/render</code>: bị từ chối.

Một matcher kết hợp dispatcher type + path:

~~~java
RequestMatcher forwardView = req ->
    req.getDispatcherType() == DispatcherType.FORWARD
    && "/internal/render".equals(req.getServletPath());

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(forwardView).hasRole("USER")
    .dispatcherTypeMatchers(DispatcherType.FORWARD).denyAll()
    .anyRequest().denyAll());
~~~

<code>RequestMatcher</code> thuộc <code>org.springframework.security.web.util.matcher</code>. Phần <code>requestMatchers(forwardView)</code> đứng **trước** fallback FORWARD denyAll. Với servlet mapping mặc định của demo, <code>getServletPath()</code> là đường dẫn nội bộ được forward. Nếu ứng dụng dùng servlet mapping phức tạp, cần kiểm tra path thực tế của request trong môi trường chạy.

**Tại sao <code>permitAll(FORWARD)</code> có thể nguy hiểm?** Nếu endpoint public cho phép người dùng định nghĩa target forward, và FORWARD được permitAll, một request có thể nội bộ forward đến <code>/admin/export</code>. Khi đó rule ADMIN trên URL có thể bị bỏ qua trong lượt FORWARD vì matcher dispatch ở trước đã quyết định. Ngăn lỗi này bằng cách không forward đến target nhạy cảm từ input không tin cậy, lập allowlist target và kiểm thử forward bị cấm.

Trong hệ thống render template nội bộ an toàn, một rule rộng cho FORWARD có thể được xem xét, nhưng chỉ khi đã kiểm kê toàn bộ các target và biết REQUEST ban đầu thực thi authorization đúng.

## 5. ERROR: render lỗi nhưng không công khai dữ liệu bí mật

ERROR dispatch giúp Servlet container chạy error page khi xử lý gặp sự cố. Nếu authorization chặn lượt ERROR, một lỗi 500 có thể bị che bởi 401/403, khiến người dùng thấy trang lỗi sai và log khó truy vết.

Cấu hình thường dùng:

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .anyRequest().authenticated());
~~~

Điều này chỉ nên cho phép **render thông báo lỗi chung**. Nó không có nghĩa ERROR handler được phép truy cập dữ liệu nhạy cảm hoặc làm nghiệp vụ không cần quyền. Error page cần tránh trả stack trace, token, cookie, password hash, SQL hoặc PII. Nếu cần diagnostics chi tiết, dùng endpoint quản trị riêng có authentication/authorization.

Phân biệt servlet ERROR dispatch với các lỗi xử lý bởi <code>AuthenticationEntryPoint</code>/<code>AccessDeniedHandler</code> của Spring Security: một response 401/403 không bắt buộc luôn có ERROR dispatch. <code>MockMvc</code> cũng không luôn mô phỏng việc container xử lý <code>sendError</code> và dispatch tới /error đầy đủ như embedded Tomcat. Do đó cần test ERROR bằng HTTP qua server thật.

Một direct REQUEST tới <code>/error</code> khác ERROR dispatch tới cùng path. Rule <code>requestMatchers("/error").permitAll()</code> mở URL theo matcher path, còn <code>dispatcherTypeMatchers(ERROR).permitAll()</code> chỉ mở loại dispatch. Chọn theo chính sách của error handler.

## 6. ASYNC: không bypass role check ở lần redispatch

Spring MVC hỗ trợ <code>Callable</code>, <code>DeferredResult</code> và các kiểu xử lý async. Một REQUEST ban đầu có thể được authorize với role của URL, sau đó container dùng ASYNC dispatch để hoàn tất kết quả. Nếu đặt <code>dispatcherTypeMatchers(ASYNC).permitAll()</code> trước mọi URL rule, ASYNC dispatch đến một path nhạy cảm có thể không còn chịu hasRole/hasAuthority như mong đợi.

Ví dụ scoped ASYNC:

~~~java
RequestMatcher asyncReport = req ->
    req.getDispatcherType() == DispatcherType.ASYNC
    && "/async/report".equals(req.getServletPath());

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(asyncReport).hasRole("USER")
    .dispatcherTypeMatchers(DispatcherType.ASYNC).denyAll()
    .anyRequest().authenticated());
~~~

Luồng mong muốn:
1. REQUEST <code>/async/report</code> chỉ được bắt đầu khi user có ROLE_USER.
2. Khi ASYNC dispatch về đúng path, vẫn phải đáp ứng ROLE_USER.
3. ASYNC dispatch tới các path khác bị denyAll, thay vì mặc định bỏ qua quyền.

Không nhất thiết mọi app đều chọn policy này; có ứng dụng cho phép ASYNC sau khi REQUEST ban đầu đã kiểm tra mọi điều kiện. Tuy nhiên phải chứng minh đích redispatch chỉ thuộc những đường an toàn và logic async không thể đổi sang một tài nguyên có quyền cao hơn.

### SecurityContext trên worker thread

<code>WebAsyncManagerIntegrationFilter</code> hỗ trợ tích hợp SecurityContext cho một số luồng Spring MVC như <code>Callable</code>, nhưng không phải mọi executor/custom task đều tự kế thừa context. <code>SecurityContextHolder</code> mặc định thường gắn context với thread. Nếu job chạy trên thread khác, có thể cần <code>DelegatingSecurityContextCallable</code>, <code>DelegatingSecurityContextRunnable</code>, executor wrapper hoặc một policy kiểm tra quyền lại ở service.

Không bật bừa <code>MODE_INHERITABLETHREADLOCAL</code> cho thread pool vì có rủi ro giữ nhầm identity. <code>dispatcherTypeMatchers</code> kiểm soát Servlet dispatch; nó **không** thay thế việc truyền context đúng cách cho mọi Java async task.

## 7. Ma trận policy trước khi viết code

| Dispatch type | Path | Quyền | Lý do |
| --- | --- | --- | --- |
| REQUEST | GET /public | permitAll | Endpoint công khai |
| REQUEST | GET /view | ROLE_USER | User được xem trang |
| FORWARD | /internal/render | ROLE_USER | Forward nội bộ tới target duy nhất |
| FORWARD | Path khác | denyAll | Không bỏ qua quyền của URL nhạy cảm |
| ERROR | Error dispatch | permitAll | Cho container render lỗi an toàn |
| REQUEST | GET /async/report | ROLE_USER | Bắt đầu tác vụ async |
| ASYNC | /async/report | ROLE_USER | Chỉ tiếp tục đúng path và role |
| ASYNC | Path khác | denyAll | Không mở mọi async target |
| REQUEST | GET /admin | ROLE_ADMIN | Chức năng quản trị |
| REQUEST | /internal/render | denyAll | Không gọi trực tiếp internal view |
| REQUEST | Path khác | denyAll | Fail closed |

Các hành động truy cập dữ liệu cụ thể cần authorization tại service (owner/tenant, trạng thái bản ghi), không chỉ role ở HTTP. Với một sản phẩm nhiều Servlet hoặc Spring SecurityFilterChain, ma trận còn cần cột servlet mapping/chain ownership.

## 8. Dự án Spring Boot runnable

Ví dụ dùng Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Maven. HTTP Basic giúp test 200/401/403; user demo <code>reader</code> có ROLE_USER, <code>admin</code> có ROLE_USER và ROLE_ADMIN. Credential demo chỉ dùng tại localhost.

Cấu trúc:

~~~text
dispatcher-security-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/dispatchdemo/
    │   │   ├── DispatchSecurityApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── ViewController.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/dispatchdemo/
            └── DispatcherSecurityTest.java
~~~

### 8.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>dispatcher-security-demo</artifactId>
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

### 8.2. Main class

Tạo <code>src/main/java/com/example/dispatchdemo/DispatchSecurityApplication.java</code>:

~~~java
package com.example.dispatchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchSecurityApplication.class, args);
    }
}
~~~

### 8.3. application.yml — đăng ký filter cho FORWARD

~~~yaml
spring:
  security:
    filter:
      dispatcher-types: request, async, error, forward
~~~

Đây là property Spring Boot cho security filter registration. Nếu dùng một cấu hình Servlet khác, hãy xác minh filter mapping thực tế thay vì chỉ copy YAML.

### 8.4. SecurityConfiguration.java

Tạo <code>src/main/java/com/example/dispatchdemo/SecurityConfiguration.java</code>:

~~~java
package com.example.dispatchdemo;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass-123"))
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass-123"))
            .roles("USER", "ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        RequestMatcher forwardView = req ->
            req.getDispatcherType() == DispatcherType.FORWARD
            && "/internal/render".equals(req.getServletPath());

        RequestMatcher asyncReport = req ->
            req.getDispatcherType() == DispatcherType.ASYNC
            && "/async/report".equals(req.getServletPath());

        return http
            .authorizeHttpRequests(auth -> auth
                // Scoped matchers trước fallback theo dispatcher.
                .requestMatchers(forwardView).hasRole("USER")
                .dispatcherTypeMatchers(DispatcherType.FORWARD).denyAll()

                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()

                .requestMatchers(asyncReport).hasRole("USER")
                .dispatcherTypeMatchers(DispatcherType.ASYNC).denyAll()

                .requestMatchers(HttpMethod.GET,
                    "/public", "/error-trigger").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/view", "/secure", "/async/report").hasRole("USER")
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Giải thích cấu hình:
- FORWARD vào /internal/render cần ROLE_USER, FORWARD khác bị denyAll.
- ERROR dispatch được permitAll để tạo error response chung; error controller không được đọc dữ liệu nhạy cảm.
- ASYNC redispatch vào /async/report vẫn cần ROLE_USER; những ASYNC path khác denyAll.
- REQUEST /view và /async/report được kiểm tra trước khi tạo internal dispatch.
- Direct REQUEST /internal/render không thuộc allowlist, nên denyAll.
- REQUEST /admin cần ROLE_ADMIN; người đọc chỉ có ROLE_USER sẽ bị 403.
- <code>anyRequest().denyAll()</code> tránh endpoint mới mặc nhiên được mở.
- Spring Security mặc định bảo vệ CSRF cho method thay đổi trạng thái; ví dụ chỉ liệt kê GET, không tắt CSRF.

Nếu app thật có nhiều <code>SecurityFilterChain</code>, matcher ở đây chỉ có hiệu lực khi chain này được chọn. Demo chỉ có một chain và không dùng <code>securityMatcher</code> hẹp, để tập trung vào dispatcher authorization.

### 8.5. ViewController.java

Tạo <code>src/main/java/com/example/dispatchdemo/ViewController.java</code>:

~~~java
package com.example.dispatchdemo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class ViewController {
    @GetMapping("/view")
    public String view() {
        return "forward:/internal/render";
    }

    @ResponseBody
    @GetMapping("/internal/render")
    public String internalRender() {
        return "rendered-view";
    }
}
~~~

Class dùng <code>@Controller</code>, không phải <code>@RestController</code>, để chuỗi <code>forward:/internal/render</code> được Spring MVC diễn giải như một view name thực hiện FORWARD. Nếu dùng <code>@RestController</code>, String đó chỉ được gửi như body trong response thông thường.

### 8.6. ApiController.java

Tạo <code>src/main/java/com/example/dispatchdemo/ApiController.java</code>:

~~~java
package com.example.dispatchdemo;

import java.io.IOException;
import java.util.concurrent.Callable;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/secure")
    public String secure(Authentication auth) {
        return "secure:" + auth.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @GetMapping("/async/report")
    public Callable<String> asyncReport(Authentication auth) {
        String user = auth.getName();
        return () -> "async:" + user;
    }

    @GetMapping("/error-trigger")
    public void errorTrigger(HttpServletResponse response)
            throws IOException {
        response.sendError(
            HttpServletResponse.SC_INTERNAL_SERVER_ERROR, "demo failure");
    }
}
~~~

<code>Callable</code> là return type async của Spring MVC, không cần <code>@EnableAsync</code> chỉ để dùng tính năng này. Demo chụp username đã xác thực tại REQUEST; một task async truy cập dữ liệu thật vẫn phải kiểm tra permission/tenant/ownership ở tầng nghiệp vụ. <code>sendError(500)</code> cho embedded Servlet container cơ hội thực hiện ERROR dispatch.

## 9. Chạy và dự đoán hành vi

Tại thư mục dự án:

~~~bash
mvn test
mvn spring-boot:run
~~~

Thử bằng curl:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/secure
curl -i -u reader:reader-pass-123 http://localhost:8080/secure
curl -i -u reader:reader-pass-123 http://localhost:8080/view
curl -i -u reader:reader-pass-123 http://localhost:8080/internal/render
curl -i -u reader:reader-pass-123 http://localhost:8080/admin
curl -i -u admin:admin-pass-123 http://localhost:8080/admin
curl -i -u reader:reader-pass-123 http://localhost:8080/async/report
curl -i http://localhost:8080/error-trigger
~~~

| Tình huống | Expected HTTP | Ghi chú |
| --- | --- | --- |
| GET /public anonymous | 200 | <code>public</code> |
| GET /secure anonymous | 401 | HTTP Basic yêu cầu authentication |
| GET /secure reader | 200 | <code>secure:reader</code> |
| GET /view reader | 200 | REQUEST và FORWARD, body <code>rendered-view</code> |
| GET /internal/render reader | 403 | Direct REQUEST bị denyAll |
| GET /admin reader | 403 | Reader không có ROLE_ADMIN |
| GET /admin admin | 200 | <code>admin</code> |
| GET /async/report reader | 200 | REQUEST + ASYNC, body <code>async:reader</code> |
| GET /async/report anonymous | 401 | Chưa đủ quyền ngay từ REQUEST |
| GET /error-trigger anonymous | 500 | ERROR dispatch xử lý lỗi chung |

Đây là **kết quả dự kiến từ cấu hình ví dụ**, không phải log đã chạy. Nếu khác, điều tra thực tế filter registration, servletPath, security chain, authorization matcher order, async context và error controller trước khi sửa policy.

## 10. MockMvc tests: REQUEST, FORWARD và ASYNC

Tạo <code>src/test/java/com/example/dispatchdemo/DispatcherSecurityTest.java</code>:

~~~java
package com.example.dispatchdemo;

import jakarta.servlet.DispatcherType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DispatcherSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void requestRulesEnforceUserAndAdminRoles() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/secure"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/secure")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("secure:reader"));

        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void directRequestToInternalEndpointIsDenied() throws Exception {
        mvc.perform(get("/internal/render")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void mvcControllerChoosesForwardTarget() throws Exception {
        mvc.perform(get("/view")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(status().isOk())
            .andExpect(forwardedUrl("/internal/render"));
    }

    @Test
    void asyncRequestCompletesWithReaderRole() throws Exception {
        MvcResult started = mvc.perform(get("/async/report")
                .with(httpBasic("reader", "reader-pass-123")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(started))
            .andExpect(status().isOk())
            .andExpect(content().string("async:reader"));
    }

    @Test
    void scopedForwardMatcherRejectsOtherTargets() {
        RequestMatcher matcher = req ->
            req.getDispatcherType() == DispatcherType.FORWARD
            && "/internal/render".equals(req.getServletPath());

        MockHttpServletRequest req =
            new MockHttpServletRequest("GET", "/internal/render");
        req.setServletPath("/internal/render");
        req.setDispatcherType(DispatcherType.FORWARD);
        assertThat(matcher.matches(req)).isTrue();

        req.setServletPath("/admin");
        assertThat(matcher.matches(req)).isFalse();

        req.setServletPath("/internal/render");
        req.setDispatcherType(DispatcherType.REQUEST);
        assertThat(matcher.matches(req)).isFalse();
    }
}
~~~

**Phạm vi bảo đảm của test:**
- REQUEST tests xác nhận 200/401/403 theo credential và role.
- Direct REQUEST <code>/internal/render</code> bị deny dù internal FORWARD có scope được phép.
- <code>forwardedUrl</code> xác nhận MVC trả forward view, **không** chứng minh Tomcat đã chạy đầy đủ lượt FORWARD security filtering.
- <code>asyncDispatch</code> mô phỏng MVC async completion trong MockMvc và giúp phát hiện lỗi redispatch trong pipeline test.
- Unit test scoped RequestMatcher xác nhận DispatcherType và target servletPath đều phải đúng.

MockMvc không phải Servlet container thật. Để xác minh FORWARD/ERROR/ASYNC filter registrations và lifecycle chính xác, cần thêm test chạy embedded server thực. Nếu test thất bại do version hoặc container khác, kiểm tra framework behavior trước; không tự động đổi dispatcherTypeMatchers thành permitAll.

## 11. Xác minh ERROR dispatch trên embedded Servlet container

Dùng <code>mvn spring-boot:run</code> để chạy embedded Tomcat, rồi:

~~~bash
curl -i http://localhost:8080/error-trigger
~~~

Mong đợi lỗi gốc tạo HTTP 500, thay vì bị che bởi 401/403 từ một ERROR dispatch mà security filter vô tình chặn. Nội dung lỗi body do Boot/container cấu hình, không nên giả định luôn có cùng JSON/HTML.

Một integration test dùng <code>@SpringBootTest(webEnvironment = RANDOM_PORT)</code> kết hợp HTTP client có thể kiểm tra đường ERROR thật, cũng như xem filter có được container đăng ký cho FORWARD/ASYNC không. Khi cần debug, log loại dispatch và path ở môi trường test có kiểm soát, tránh log cookie/token hay dữ liệu nhạy cảm.

<code>MockHttpServletRequest.setDispatcherType(ERROR)</code> chỉ thay đổi thuộc tính trên một mock request, **không** có nghĩa container đã tạo ERROR dispatch, đi qua error controller và chạy các Servlet filter mappings.

## 12. FORWARD, ASYNC và ranh giới bảo mật

### FORWARD: ai chọn target?

Nếu một controller public tạo forward target từ user input, ví dụ parameter <code>next</code>, thì một rule mở tất cả FORWARD có thể biến nó thành đường đi bypass authorization. Không nhận path tùy ý làm forward target. Dùng allowlist target cố định, và đặt authorization thực tế ở service xử lý dữ liệu.

### ASYNC: xử lý quyền ở đâu?

Role ở HTTP cho biết user được bắt đầu tác vụ. Tác vụ chạy lâu có thể truy cập bản ghi thuộc tenant khác hoặc hoạt động sau khi quyền bị thu hồi. Cần check quyền trên reportId/tenantId, quyết định việc kiểm tra lại permission lúc thực thi và xử lý timeout/cancellation. Không dùng <code>Authentication.getName()</code> đã chụp ở REQUEST làm bằng chứng được phép đọc mọi tài nguyên.

### ERROR: tránh lộ thông tin

Ngay cả khi ERROR dispatch được permitAll, error page không được trả stacktrace, SQL, credential, session ID hoặc dữ liệu tài khoản. Mục đích của ERROR allow là render một response an toàn, không phải mở một đường truy cập bí mật.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách điều tra |
| --- | --- | --- |
| Forward bị 403 sau khi REQUEST đã qua | Target FORWARD không có rule phù hợp | Kiểm tra servletPath và dispatcher type |
| Rule FORWARD không có tác dụng | Security filter không mapping FORWARD | Xem effective Servlet filter registration |
| Broad FORWARD permitAll tạo quyền vào admin target | Miễn kiểm tra URL role ở dispatch | Scoped matcher + denyAll fallback |
| ERROR 500 trở thành 403 | ERROR dispatch bị chặn | Permit error rendering an toàn; test container |
| ERROR permitAll nhưng vẫn lỗi | Lỗi không phát sinh từ ERROR authorization | Kiểm tra stack/filter/error handler |
| ASYNC request không hoàn tất | ASYNC redispatch bị chặn hoặc context mất | Kiểm tra matcher/async lifecycle |
| ASYNC permitAll cho path nhạy cảm | Matcher quá rộng và đặt trước URL rules | Phân quyền theo dispatch+path |
| Direct internal URL vẫn 200 | URL REQUEST được mở vô ý | Deny direct URL, allow only scoped FORWARD |
| MockMvc xanh nhưng server thật sai | MockMvc không mô phỏng đầy đủ container | Test embedded Tomcat/Jetty |
| Principal trong async thread bị null | Thiếu context propagation | Kiểm tra WebAsyncManager/DelegatingSecurityContext |
| Có nhiều SecurityFilterChain | Chain khác được chọn trước | Kiểm tra first-matching securityMatcher |
| Quy tắc theo HTTP method sai | Nhầm DispatcherType với HttpMethod | Tách GET/POST khỏi REQUEST/FORWARD |
| Filter chạy hoặc skip ERROR bất ngờ | Filter-specific OncePerRequest behavior | Kiểm tra shouldNotFilter... và registration |
| INCLUDE có vấn đề | INCLUDE là type riêng | Không coi INCLUDE tương đương FORWARD |

## 14. Checklist áp dụng

1. Kiểm kê REQUEST endpoint, internal FORWARD targets, ERROR pages, ASYNC redispatch paths.
2. Xác nhận <code>springSecurityFilterChain</code> được container đăng ký cho các dispatcher types thực sự cần bảo vệ.
3. Xác định SecurityFilterChain đầu tiên khớp mỗi request trước khi đọc authorization rules.
4. Dùng path-scoped RequestMatcher cho FORWARD/ASYNC nhạy cảm; đặt trước fallback <code>dispatcherTypeMatchers(...).denyAll()</code>.
5. Chỉ permitAll ERROR cho trang lỗi chung không lộ dữ liệu nhạy cảm.
6. Tránh miễn quyền toàn bộ FORWARD/ASYNC khi chưa kiểm kê target có thể được gọi.
7. Kiểm tra URL authorization ở REQUEST ban đầu và quyền service trên tài nguyên thực.
8. Xác minh SecurityContext propagation cho Callable/custom executors, không tự chia sẻ mutable context giữa users.
9. Viết negative tests: anonymous, role thiếu, direct internal URL, unexpected FORWARD/ASYNC target.
10. Test FORWARD/ERROR/ASYNC bằng Servlet container thật, không chỉ MockMvc.
11. Giữ <code>anyRequest().denyAll()</code> cho đường chưa được phân loại khi policy yêu cầu fail closed.
12. Khi upgrade Spring Security/Boot hoặc sửa filter registration, chạy lại các integration tests.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Một browser có thể tự gửi header để biến request thành DispatcherType.FORWARD không?  
**Đáp án:** Không. DispatcherType do Servlet container quản lý; tuy nhiên input client vẫn có thể gián tiếp ảnh hưởng internal forward target nếu server cho phép.

**Câu 2:** Tại sao <code>.dispatcherTypeMatchers(FORWARD).permitAll()</code> đặt trước <code>hasRole("ADMIN")</code> có thể nguy hiểm?  
**Đáp án:** Vì một FORWARD tới path admin có thể được rule dispatcher cấp phép trước, không xét role của URL trong lượt dispatch đó.

**Câu 3:** Vì sao cần ERROR matcher?  
**Đáp án:** Để hạ tầng render trang lỗi an toàn khi container thực hiện ERROR dispatch, tránh bị một rule authentication khác che mất lỗi gốc.

**Câu 4:** <code>Callable</code> chạy trên worker thread có tự động được mọi loại executor giữ SecurityContext không?  
**Đáp án:** Không. Spring MVC có tích hợp cho một số mô hình như Callable, nhưng custom async tasks cần context propagation/authorization phù hợp.

**Câu 5:** Tại sao cấu hình dispatcherTypeMatchers không đủ nếu security filter registration không nhận FORWARD?  
**Đáp án:** Matcher chỉ được xét khi request thực sự đi qua Spring SecurityFilterChain ở lượt dispatch đó.

**Câu 6:** Unit test đặt <code>MockHttpServletRequest.setDispatcherType(ERROR)</code> có chứng minh Tomcat ERROR dispatch đã chạy không?  
**Đáp án:** Không. Cần test tích hợp trên Servlet container thật để xác nhận ERROR lifecycle và filter mappings.

**Câu 7:** Rule FORWARD tới /internal/render có cho phép browser GET trực tiếp /internal/render không?  
**Đáp án:** Không. Direct GET là REQUEST; demo dùng denyAll cho URL internal ở loại REQUEST.

**Kết luận:** <code>dispatcherTypeMatchers</code> kiểm soát quyền trên **một lượt Servlet dispatch**, không tự thay thế URL/role policy của REQUEST ban đầu và không tự thay đổi mapping của security filter trong container. Thiết kế FORWARD/ASYNC theo đích cụ thể, render ERROR an toàn, và kiểm thử cả matcher lẫn Servlet dispatch thực tế.
