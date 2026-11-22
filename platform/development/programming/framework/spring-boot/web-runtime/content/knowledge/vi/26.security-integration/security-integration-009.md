# Kiểm tra thứ tự bộ lọc để tránh đăng ký hoặc xử lý bảo mật hai lần

**Phạm vi:** Spring Boot → web-runtime → Tích hợp bảo mật. Bài này giúp xác định một request đang chạy qua những lớp lọc nào; phân biệt **Servlet container filter chain** và **Spring Security FilterChainProxy**; kiểm tra thứ tự `SecurityFilterChain`, `HttpSecurity.addFilterBefore/After/At`; phát hiện một custom filter vô tình được đăng ký **hai lần**; xử lý `OncePerRequestFilter`, dispatcher types, CORS/CSRF, JWT, logging và integration testing.

**Môi trường:** Java 17+, Maven 3.6.3+, Spring Boot **3.5.16** (Spring Security 6.5.x qua Spring Boot BOM), Servlet MVC/Tomcat. Project có mã Java biên dịch/chạy được, endpoint trả bộ đếm invocation và hai integration tests chạy trên HTTP server thật. Các đoạn khác được ghi rõ là minh họa. Spring Boot 3.5.16 là bản cuối của nhánh 3.5 theo hỗ trợ OSS (6/2026); khi đưa production hãy dùng phiên bản đang được vá (ví dụ dòng Boot 4.x hoặc dịch vụ bảo trì được hỗ trợ), không xem bản cố định trong bài là khuyến nghị production vĩnh viễn.

## 1. Bộ lọc bảo mật là gì và vì sao thứ tự quan trọng?

Trong một ứng dụng Servlet, request phải đi qua danh sách các **Filter** trước khi tới `DispatcherServlet`/controller. Mỗi filter có thể đọc/chỉnh request, response, hoặc **chặn** request bằng 401/403 khi phát hiện vấn đề. Filter chain thường có nhiệm vụ:

- áp dụng security headers, xử lý CORS và CSRF;
- đọc/khôi phục `SecurityContext` và principal;
- xác thực Basic, form login, bearer JWT/OAuth2 (tùy bật cơ chế nào);
- gắn anonymous principal nếu không có user;
- áp dụng authorization: cho phép, từ chối hoặc chuyển tới authentication entry point;
- bổ sung request ID, audit, rate-limit, tracing theo thiết kế.

Nếu một filter xác thực chạy **sau** authorization, authorization có thể không thấy user. Nếu custom filter bị gọi **hai lần** trên cùng request, token có thể bị kiểm tra hai lần, downstream service bị gọi hai lần, audit/metrics ghi lặp hoặc request body bị tiêu thụ trước khi controller đọc. Nếu chặn sai `OPTIONS` preflight, browser báo CORS error. Vì vậy **thứ tự** và **số lần đăng ký** đều quan trọng.

Tuy nhiên **hai dòng log không tự chứng minh một filter bị đăng ký trùng**. Có thể browser gửi hai HTTP requests, proxy retry, request được redirect, Servlet tạo `ASYNC`/`ERROR` dispatch khác hoặc có hai filter instances cùng log một thông điệp. Cần xem **cùng request ID**, dispatcher type, filter instance, SecurityFilterChain được chọn và Servlet registrations.

## 2. Kiến trúc hai tầng: Servlet filter vs Spring Security filter

~~~text
HTTP request
      │
      ▼
Embedded Servlet container (Tomcat)
      │
      ├── Optional container Filter A
      │
      ├── DelegatingFilterProxy ("springSecurityFilterChain")
      │         │
      │         ▼
      │      FilterChainProxy (Spring Security)
      │         │
      │         ├─ SecurityFilterChain 1: matcher /api/**
      │         └─ SecurityFilterChain 2: matcher any request
      │                       │
      │                  CHỌN CHAIN KHỚP ĐẦU TIÊN
      │                       ▼
      │            [SecurityContextHolderFilter,
      │             HeaderWriterFilter, CsrfFilter,
      │             BasicAuthenticationFilter,
      │             AnonymousAuthenticationFilter,
      │             CustomFilter, AuthorizationFilter]
      │                       │
      │                       ▼
      │                servlet chain.doFilter(...)
      │
      ├── Optional container Filter B
      │
      ▼
DispatcherServlet → @Controller/@RestController → response
~~~

### 2.1. `DelegatingFilterProxy` và `FilterChainProxy`

**`DelegatingFilterProxy`** là một Servlet `Filter` làm cầu nối giữa Servlet container và Spring ApplicationContext. Trong cấu hình Spring Security, nó delegate đến Spring bean tên **`springSecurityFilterChain`**, thường chính là **`FilterChainProxy`**.

**`FilterChainProxy`** giữ danh sách `SecurityFilterChain`. Nó tìm **chain đầu tiên khớp request** và gọi danh sách security filters của chain đó; nó không chạy lần lượt tất cả chains. Nó còn tích hợp các cơ chế chung như security context cleanup và `HttpFirewall`. Thứ tự filters trong chain được framework tổ chức, tùy những DSL/features đang bật.

Spring Boot/Spring Security auto-configuration thông thường **đã đăng ký DelegatingFilterProxy**. Đừng tự thêm một registration bean hoặc khai báo `web.xml` cho cùng `springSecurityFilterChain` nếu không nắm rõ lifecycle; việc đăng ký hai proxy có thể dẫn tới pipeline bị gọi hai lượt hoặc lỗi khó truy vết.

### 2.2. Filter của Servlet container và filter trong Spring Security không cùng “order”

| Đối tượng | Đăng ký ở đâu? | Thứ tự được điều khiển bởi |
| --- | --- | --- |
| `jakarta.servlet.Filter` qua `FilterRegistrationBean` | Servlet container | `FilterRegistrationBean#setOrder`, URL patterns, dispatcher types |
| `Filter` bean thông thường trong Boot Servlet app | Có thể được Boot auto-register vào container | Auto-registration / `@Order` / registration config |
| `DelegatingFilterProxy` | Servlet container, delegate tới security bean | Vị trí của proxy trong container chain |
| `SecurityFilterChain` | `FilterChainProxy` | Matcher + `@Order` giữa các chain beans |
| Filter thêm qua `HttpSecurity.addFilterBefore/After/At` | Bên trong một `SecurityFilterChain` | Vị trí tương đối với security filter được chỉ định |
| `OncePerRequestFilter` | Có thể ở cả hai tầng nếu lập trình sai | Request attribute guard, không phải registration policy |

**Ví dụ cần phân biệt:** `@Order(1)` gắn lên method tạo `SecurityFilterChain` làm chain đó được xét trước chain khác. Nó **không** khiến custom filter nằm đầu chain. Ngược lại, `FilterRegistrationBean#setOrder(1)` chỉ điều khiển thứ tự Servlet filters ở container; nó **không** điều khiển vị trí của custom filter được thêm bằng `HttpSecurity`.

### 2.3. `chain.doFilter` cần gọi đúng một lần theo mục đích

~~~java
@Override
public void doFilter(ServletRequest request, ServletResponse response,
                     FilterChain chain)
        throws IOException, ServletException {
    // Xử lý trước handler/downstream.
    chain.doFilter(request, response);
    // Xử lý sau downstream.
}
~~~

Đây là **mảnh code minh họa**. Nếu filter cần chặn request, nó có thể chủ động ghi status/response và **không** gọi tiếp. Nhưng nếu muốn tiếp tục, gọi `chain.doFilter` theo hợp đồng **một lần** trên đường đi thông thường. Gọi hai lần vì nghĩ “bảo đảm next” có thể làm downstream/controller chạy lặp hoặc response bị committed. Quên gọi hoàn toàn khiến request không tới controller.

## 3. Thứ tự logic của security filters

Security filters chạy theo trình tự đảm bảo những công việc cần thiết đã diễn ra trước authentication và authorization. Danh sách minh họa (thực tế tùy `HttpSecurity` config và phiên bản):

| Filter | Nhiệm vụ |
| --- | --- |
| `DisableEncodeUrlFilter` | Điều chỉnh mã hóa URL trong một số trường hợp |
| `WebAsyncManagerIntegrationFilter` | Tích hợp security context với Servlet MVC async |
| `SecurityContextHolderFilter` | Làm sẵn/đọc security context đúng strategy |
| `HeaderWriterFilter` | Ghi response security headers |
| `CorsFilter` | Xử lý CORS/preflight nếu được cấu hình |
| `CsrfFilter` | Kiểm tra CSRF ở request phù hợp |
| `LogoutFilter` | Xử lý logout |
| `UsernamePasswordAuthenticationFilter` | Form login khi bật |
| `BasicAuthenticationFilter` | HTTP Basic khi bật |
| `BearerTokenAuthenticationFilter` | Bearer token khi bật OAuth2 resource server |
| `AnonymousAuthenticationFilter` | Anonymous principal khi chưa có auth |
| `ExceptionTranslationFilter` | Chuyển authentication/access-denied errors thành HTTP response |
| `AuthorizationFilter` | Kiểm tra quyền truy cập endpoint |

**Không phải mọi app có tất cả filters trên.** Dự án bật HTTP Basic thường khác form login. App không cấu hình resource server không cần BearerTokenAuthenticationFilter. Thứ tự nội bộ của Spring Security được quản lý qua `FilterOrderRegistration`; không sao chép danh sách cố định rồi tự khởi tạo các core filters nếu chỉ cần DSL `httpBasic`, `formLogin`, `oauth2ResourceServer`, `authorizeHttpRequests`, `csrf` hay `cors`.

Quy tắc thiết kế custom filter:
1. Nếu cần `SecurityContext` đã có, đừng đứng trước filter tải security context.
2. Nếu **xác thực** một cơ chế mới, filter phải hoàn thành authentication **trước `AuthorizationFilter`**. Tài liệu Spring Security gợi ý đặt một authentication filter custom sau `LogoutFilter` hoặc tại mốc phù hợp với cơ chế.
3. Nếu chỉ cần đọc thông tin user đã xác thực, đặt sau những authentication filters cần thiết, ví dụ `addFilterAfter(..., AnonymousAuthenticationFilter.class)` hoặc `addFilterBefore(..., AuthorizationFilter.class)`, rồi kiểm thử.
4. Dùng `addFilterBefore(Filter, Class<?>)`/`addFilterAfter(...)` hơn là đoán số order. `addFilterAt(...)` dùng cùng vị trí của filter chuẩn nhưng **không được tự động coi là “gỡ filter cũ”** nếu DSL vẫn thêm filter cũ; kiểm tra chain cuối cùng.
5. Không viết lại logic JWT đã có trong `oauth2ResourceServer().jwt()` chỉ để “thêm logging”: hãy cân nhắc authentication converter/filter hook và tracing phù hợp.

## 4. Có nhiều `SecurityFilterChain` có làm bảo mật chạy hai lần không?

**Không, không phải mặc định.** `FilterChainProxy` chọn **first matching chain**. Ví dụ:

~~~text
@Order(1) securityMatcher("/api/**") → API chain
Không @Order, match any request → fallback chain

GET /api/hello  → API chain
GET /public     → fallback chain
GET /admin      → fallback chain
~~~

Nó không có nghĩa `GET /api/hello` đi qua API chain rồi **lại** qua fallback chain. Trùng xử lý thường do **cùng filter nằm ở Servlet container chain và Spring Security chain**, hoặc do một custom logic được gọi ở nhiều component, không phải cứ có hai `SecurityFilterChain`.

**Sai lầm nghiêm trọng:** gắn `@Order(1)` lên fallback matcher `/**` trước chain đặc thù `/api/**`. Chain rộng khớp trước, nên API chain có thể **không bao giờ được chọn**. Nếu fallback quá dễ dãi, API nhạy cảm bị đặt dưới policy sai; đây là chain **shadowing**, không nhất thiết double registration.

### 4.1. `securityMatcher` và `requestMatchers`

- `http.securityMatcher("/api/**")`: chọn **cả chain** này có áp dụng cho request hay không.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin/**").hasRole("ADMIN"))`: một **authorization rule** trong chain đã được chọn.

Nếu chain không match, các `requestMatchers` bên trong chain sẽ không được đánh giá. Nếu **không chain nào match**, request có thể không được Spring Security bảo vệ. Dùng một fallback chain với chính sách `denyAll()`/`authenticated()` phù hợp thay vì để lỗ hổng bảo mật.

## 5. Project Java 17 chạy được: đếm invocation của custom filter

Ví dụ này chủ động dùng `jakarta.servlet.Filter` thuần, **không** dùng `OncePerRequestFilter` cho bộ đếm. Nhờ đó nếu filter bị đăng ký thêm ở container và chạy lồng nhau với security, phép thử có thể thấy 2 invocations. Dùng `OncePerRequestFilter` có request attribute guard khiến trùng đăng ký đôi khi không hiện rõ ở `doFilterInternal`.

**Thiết kế đúng:** filter Audit được tạo bằng `new AuditFilter()` **chỉ trong security chain**, không là `@Bean`, không `@Component`, không `@WebFilter`.

Cây thư mục:

~~~text
filter-order-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/filterdemo/
    │   │   ├── FilterOrderApplication.java
    │   │   ├── AuditFilter.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/com/example/filterdemo/
        └── FilterOrderIntegrationTest.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>filter-order-demo</artifactId>
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

### 5.2. `src/main/java/com/example/filterdemo/FilterOrderApplication.java`

~~~java
package com.example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterOrderApplication.class, args);
    }
}
~~~

### 5.3. `src/main/java/com/example/filterdemo/AuditFilter.java`

~~~java
package com.example.filterdemo;

import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AuditFilter implements Filter {
    public static final String COUNT =
            AuditFilter.class.getName() + ".invocations";
    private static final Logger log =
            LoggerFactory.getLogger(AuditFilter.class);

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        Object previous = http.getAttribute(COUNT);
        int count = (previous instanceof Integer n ? n : 0) + 1;
        http.setAttribute(COUNT, count);

        log.info("AUDIT count={} dispatcher={} method={} uri={}",
                 count,
                 http.getDispatcherType(),
                 http.getMethod(),
                 http.getRequestURI());

        chain.doFilter(request, response);
    }
}
~~~

**Giải thích:** request attribute `COUNT` chỉ sống trong request và dùng để chẩn đoán, không là counter toàn JVM, không được dùng cho authentication/authorization. Mỗi lần `doFilter(...)` được gọi trên cùng Servlet request, `COUNT` tăng. Đây là **filter quan sát** không làm thay đổi quyết định bảo mật, nên không xử lý JWT hay credentials.

Nếu filter bị đăng ký ở cả container và security chain, số đếm có thể tăng lên hai lần. Nếu có `ERROR/ASYNC` dispatch mới hoặc hai HTTP requests khác nhau, cần kiểm tra `DispatcherType` và request identity trước khi kết luận nguyên nhân.

### 5.4. `src/main/java/com/example/filterdemo/SecurityConfiguration.java`

~~~java
package com.example.filterdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .addFilterBefore(new AuditFilter(),
                             AuthorizationFilter.class);
        return http.build();
    }

    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().denyAll());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-only")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

`apiChain` được xét **trước** vì `@Order(1)`; chỉ khớp `/api/**` và yêu cầu authenticated Basic. Một custom `AuditFilter` được thêm vào **trước `AuthorizationFilter`**. `fallbackChain` giữ các route khác, chỉ cho `/public` và deny toàn bộ route còn lại. `FilterChainProxy` chọn **một** trong hai chains.

**Không được copy password `{noop}demo-only` vào production.** Nó chỉ phục vụ lab local; hệ thống thật phải dùng password hash mạnh, identity provider, secret management và TLS. **Ví dụ không tắt CSRF**; nó chỉ có các GET endpoints. Nếu bổ sung POST dùng cookie/session, cần chính sách CSRF phù hợp.

### 5.5. `src/main/java/com/example/filterdemo/DemoController.java`

~~~java
package com.example.filterdemo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/hello")
    public String hello(HttpServletRequest request) {
        return "hello; auditCount="
                + request.getAttribute(AuditFilter.COUNT) + "\n";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public\n";
    }
}
~~~

Controller gửi bộ đếm trong response **chỉ để học và test**; không expose debug endpoint hoặc thông tin nội bộ như thế này ở production. Khi dùng `@RestController`, return String được ghi thành response body, không phải logical view name.

### 5.6. `src/main/resources/application.properties`

~~~properties
server.port=8080
spring.application.name=filter-order-demo

# Chỉ bật chi tiết ở development/staging khi chẩn đoán.
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.com.example.filterdemo.AuditFilter=INFO
~~~

`DefaultSecurityFilterChain` DEBUG hỗ trợ xem danh sách filters lúc startup; `FilterChainProxy` TRACE giúp theo dõi request được xét bởi chain nào và security filters nào được gọi. Các log entries phụ thuộc Spring Security version/configuration; không hardcode toàn bộ log output làm expected stdout.

### 5.7. Chạy project và test HTTP

Trong thư mục `filter-order-demo`:

~~~bash
java -version
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
# Fallback chain, public endpoint:
curl -i http://localhost:8080/public

# API chain, chưa đăng nhập:
curl -i http://localhost:8080/api/hello

# API chain, có HTTP Basic demo:
curl -i -u learner:demo-only http://localhost:8080/api/hello
~~~

**Kỳ vọng với project như trên, không thêm Security config ngoài:**
- `GET /public`: **200 OK**, response body `public\n`.
- `GET /api/hello` không có Basic credentials: **401 Unauthorized** và header `WWW-Authenticate` do Basic entry point cung cấp.
- `GET /api/hello` có user/password hợp lệ: **200 OK**, response body **`hello; auditCount=1\n`**. Một log AuditFilter có `count=1 dispatcher=REQUEST method=GET uri=/api/hello`.
- Khi credentials sai, `BasicAuthenticationFilter` có thể chặn request **trước** custom AuditFilter, vì vậy log custom filter không xuất hiện không chứng minh chain không áp dụng.
- `GET /admin` thuộc fallback chain và bị `denyAll()`; response 401/403 tùy entrypoint/exception handling. Quan trọng là route không được cung cấp public.

Body có newline cuối vì Java controller trả `"\n"`. `curl -i` cũng in HTTP headers, server date, connection info tùy container. Không coi toàn bộ output của curl là một chuỗi cố định khi xác minh.

### 5.8. Integration test với embedded servlet container thật

Tạo **`src/test/java/com/example/filterdemo/FilterOrderIntegrationTest.java`**:

~~~java
package com.example.filterdemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterOrderIntegrationTest {
    @LocalServerPort
    private int port;

    @Test
    void authenticatedApiPassesAuditFilterExactlyOnce() {
        String body = RestClient.create().get()
                .uri("http://localhost:" + port + "/api/hello")
                .headers(h -> h.setBasicAuth("learner", "demo-only"))
                .retrieve()
                .body(String.class);

        assertEquals("hello; auditCount=1\n", body);
    }

    @Test
    void publicPageDoesNotNeedApiFilter() {
        String body = RestClient.create().get()
                .uri("http://localhost:" + port + "/public")
                .retrieve()
                .body(String.class);

        assertEquals("public\n", body);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Với source đúng như ví dụ, **hai tests được thiết kế phải PASS**; đây là expected outcome theo code, không phải khẳng định đã chạy trên mọi host. `RANDOM_PORT` tạo embedded server thật, nên phép thử có thể quan sát **Servlet filter registrations thực**, khác một số `MockMvc` standalone hoặc test slice chỉ mô phỏng MVC.

Nếu một test fail, xem server logs và lỗi build/HTTP trước khi đổi security policy. Không bật `permitAll` mọi nơi chỉ để test không còn 401/403.

## 6. Tái hiện lỗi đăng ký trùng và sửa đúng cách

### 6.1. Phản ví dụ: `@Component` và `addFilterBefore` trên cùng filter

Một custom `Filter` khi được gắn `@Component` hoặc khai báo bằng `@Bean` sẽ là Spring Bean. Trong Servlet Spring Boot, **Filter bean có thể được Boot tự đăng ký vào container**. Nếu đồng thời tham chiếu cùng bean trong `HttpSecurity.addFilterBefore(...)` thì có hai tầng gọi.

Mảnh cấu hình **SAI** (chỉ dùng để nhận diện lỗi, không paste nguyên vào project đúng ở mục 5):

~~~java
@Component
public class MyAuditFilter implements Filter {
    // doFilter(...)
}

@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             MyAuditFilter myAuditFilter)
        throws Exception {
    http.securityMatcher("/api/**")
        .addFilterBefore(myAuditFilter, AuthorizationFilter.class);
    return http.build();
}
~~~

Nếu dùng `Filter` thuần đếm request attribute, cùng request có thể thấy hai invocations. Nếu dùng `OncePerRequestFilter`, `doFilterInternal` có thể bị guard bỏ qua một lượt lồng và **che mất dấu hiệu lặp**; registration vẫn sai, thứ tự thực không đáng tin. Đặc biệt nếu tạo **hai instances** khác nhau, marker của chúng có thể khác và cả hai vẫn chạy logic.

**Không nhầm một filter được inject vào hai bean methods với hai security chains:** một request chỉ chạy chain khớp đầu tiên; điều cần phát hiện là việc auto-registration ở container và lặp logic của các filters khác nhau hoặc duplicated security proxy.

### 6.2. Giải pháp A: không tạo filter bean

Trong project mẫu, filter được khởi tạo bằng:

~~~java
.addFilterBefore(new AuditFilter(), AuthorizationFilter.class)
~~~

Không thêm `@Component`, không tạo `@Bean AuditFilter`, không dùng `@WebFilter` cho cùng class. Khi không cần dependency injection vào filter, đây là cách trực tiếp nhất để nó **chỉ tồn tại trong SecurityFilterChain**.

Nếu filter cần service/repository, có thể nhận service trong method `@Bean SecurityFilterChain` rồi truyền qua constructor mà **không cần khai báo filter bean**. Đây là mảnh minh họa, không độc lập:

~~~java
@Bean
SecurityFilterChain chain(HttpSecurity http, AuditService service)
        throws Exception {
    AuditFilter audit = new AuditFilter(service);
    // Cần constructor AuditFilter(AuditService) trong implementation.
    http.addFilterBefore(audit, AuthorizationFilter.class);
    // Còn phải đặt authentication/authorization theo nghiệp vụ.
    return http.build();
}
~~~

Nếu làm theo đoạn này, thay đổi class phù hợp và **không copy chồng** lên method `apiChain` của project mẫu; nội dung chỉ minh họa kỹ thuật constructor injection.

### 6.3. Giải pháp B: cần Filter bean thì disable Servlet registration

Khi filter cần là Spring Bean để tái sử dụng, DI hay cấu hình test, dùng `FilterRegistrationBean` với **`setEnabled(false)`**, như tài liệu Spring Security/Spring Boot hướng dẫn:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AuditFilterBeanConfig {

    @Bean
    AuditFilter auditFilter() {
        return new AuditFilter();
    }

    @Bean
    FilterRegistrationBean<AuditFilter> noServletRegistration(
            AuditFilter auditFilter) {
        FilterRegistrationBean<AuditFilter> reg =
                new FilterRegistrationBean<>(auditFilter);
        reg.setEnabled(false);
        return reg;
    }
}
~~~

**Đây là phương án thay thế.** Nếu áp dụng, sửa method tạo api chain để nhận `AuditFilter auditFilter` như tham số rồi dùng:

~~~java
.addFilterBefore(auditFilter, AuthorizationFilter.class)
~~~

Không giữ `new AuditFilter()` đồng thời với bean nếu muốn dùng đúng **một instance**. `setEnabled(false)` chỉ tắt registration ở **Servlet container**; Spring Security vẫn có thể gọi bean filter được thêm qua `HttpSecurity`. Không setEnabled(false) trên `springSecurityFilterChain`/proxy bảo mật — điều đó có thể vô hiệu hóa security.

Nếu dùng `@Component` thay vì `@Bean` để tạo filter, vẫn có thể tham chiếu bean đó trong disabled `FilterRegistrationBean`, nhưng **không tạo thêm một bean thứ hai** cùng chức năng. Kiểm tra filter đã thật sự biến mất khỏi Servlet registrations mà vẫn có đúng một instance trong security chain.

### 6.4. Giải pháp C: filter chỉ cần ở Servlet container

Filter thuần request ID, compression, tracing, v.v. không cần authenticated `SecurityContext` có thể nằm trong container chain. Đăng ký **chỉ một lần** bằng `FilterRegistrationBean`, chọn URL patterns, dispatcher types và order, rồi **không** thêm filter đó vào `HttpSecurity`.

Mảnh minh họa (cần implementation `RequestIdFilter` và imports):

~~~java
@Bean
FilterRegistrationBean<RequestIdFilter> requestIdRegistration(
        RequestIdFilter filter) {
    FilterRegistrationBean<RequestIdFilter> reg =
            new FilterRegistrationBean<>(filter);
    reg.setUrlPatterns(java.util.List.of("/*"));
    reg.setOrder(org.springframework.core.Ordered.HIGHEST_PRECEDENCE);
    return reg;
}
~~~

**Đừng** nghĩ FilterRegistrationBean#setOrder đặt filter sau `BasicAuthenticationFilter`: nó điều khiển **container order**, không bảo đảm security context đã được xác thực. Nếu filter muốn đọc authentication, nên thiết kế nó như Spring Security filter tại vị trí xác thực đã xảy ra.

## 7. `OncePerRequestFilter` và các loại servlet dispatch

`OncePerRequestFilter` là base class của Spring Framework, có hook `doFilterInternal`. Nó dùng **already-filtered request attribute** để tránh logic nội bộ chạy lặp trong một dispatch theo tên/marker của filter.

~~~java
public class MyOnceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        // Tác vụ tối đa một lần trong phạm vi dispatch theo contract.
        chain.doFilter(request, response);
    }
}
~~~

Đoạn trên **không độc lập**: cần imports `OncePerRequestFilter`, `HttpServletRequest`, `HttpServletResponse`, `FilterChain`, `ServletException` và `IOException`.

### 7.1. “Once” không có nghĩa “đăng ký một lần”

- Cùng filter instance/marker trong **nested invocation** có thể bỏ qua lần thực thi `doFilterInternal` thứ hai.
- Hai **instances** hoặc names/markers khác nhau có thể cùng thực thi logic.
- `OncePerRequestFilter` không xóa một Servlet registration thừa; chỉ quản lý thực thi theo request attribute.
- Một HTTP request có thể có nhiều **Servlet dispatcher types**: `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR`.
- Theo mặc định `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()` trả **true**, nên bỏ qua các dispatch async/error tiếp theo; override thành false khi thật sự cần xử lý trên các dispatch đó.
- Một số container có **nested ERROR dispatch** khi response gửi lỗi; Spring có `doFilterNestedErrorDispatch(...)` cho trường hợp đặc thù. Không khẳng định mọi ERROR dispatch luôn là request mới.
- Browser/proxy retry là **HTTP request mới**; một per-request guard không ngăn lần retry đó.

**Không dùng global static boolean** để bảo đảm mọi request sau không bị chạy filter: nó có thể khiến authentication/authorization bị bỏ qua trên các request khác. Không biến `OncePerRequestFilter` thành cách che hai registrations sai: phải sửa đúng cấu hình.

### 7.2. Ghi log để phân biệt dispatch

Trong filter chẩn đoán, thông tin giá trị gồm:
- một request/correlation ID (nếu proxy/app đã tạo tin cậy);
- `HttpServletRequest#getDispatcherType()`;
- method và path;
- tên/identity filter instance;
- thứ tự vào/ra filter (trước và sau `chain.doFilter`);
- HTTP status (nếu có thể quan sát an toàn) và elapsed time.

Nếu log cho cùng path nhưng hai request IDs khác nhau, đó có thể là **hai HTTP requests độc lập**. Nếu cùng request ID nhưng `REQUEST` rồi `ERROR`, cần xem error dispatch configuration; nó không tự chứng minh duplicate registration. Nếu cùng request ID và `REQUEST` với hai separate invocation vào cùng custom filter, hãy xem Servlet registrations cùng security chain.

## 8. Quan sát security chain bằng log

Spring Security chính thức gợi ý dùng log để kiểm tra danh sách filters và thứ tự:

~~~properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Ở startup, `DefaultSecurityFilterChain` DEBUG thường hiển thị dòng `Will secure ... with [...]` tương ứng từng security matcher và list filters. `FilterChainProxy` TRACE cho biết cách match và các filter invoked ở request cụ thể.

**Một request có nhiều log từ nhiều security filters là bình thường.** Nhiệm vụ là:
1. Mỗi chain có đúng filter cần thiết và không có hai copies cùng logic.
2. `@Order` của chains và matcher đúng.
3. Custom filter xuất hiện trong chain **cần thiết**, tại đúng vị trí tương đối.
4. Nếu custom filter cũng xuất hiện trong Servlet container registry, loại registration ngoài ý muốn.
5. Không có **hai security proxy registrations** đưa cùng request vào FilterChainProxy nhiều lần.

Thực tế có thể dùng Spring Actuator mappings, `ServletContext.getFilterRegistrations()` hoặc startup inspection code để thấy container registrations riêng. **Security chain debug log không tự hiển thị đầy đủ container filter registrations**, nên không dùng nó như bằng chứng duy nhất.

### 8.1. Kiểm tra Servlet filter registrations

Mảnh code minh họa có thể thêm tạm vào `@Configuration` của môi trường development:

~~~java
@Bean
ApplicationRunner listServletFilters(ServletContext context) {
    return args -> context.getFilterRegistrations().forEach((name, reg) ->
        System.out.println("SERVLET FILTER: " + name
                + " -> " + reg.getClassName()));
}
~~~

Imports: `org.springframework.boot.ApplicationRunner`, `jakarta.servlet.ServletContext`, `org.springframework.context.annotation.Bean`. Đoạn này **không thuộc project hoàn chỉnh mục 5**; dùng để debug nếu cần.

Trong project đúng, có container registration cho `springSecurityFilterChain`/proxy là **hợp lệ**. Không cần có registration container riêng mang tên `auditFilter`. Nếu thấy hai entries cùng logic filter hoặc cùng proxy, kiểm tra `@Component`, `@Bean`, `@WebFilter`/`@ServletComponentScan`, `FilterRegistrationBean`, registrations từ thư viện và code `web.xml`.

**Không expose mappings/debug endpoints cho người ngoài Internet**, tránh tiết lộ topology bảo mật. Không bật TRACE ở production lâu dài; giới hạn thời gian logging, bảo vệ logs khỏi tokens, cookies và thông tin nhạy cảm.

### 8.2. Phân biệt filter identity và tên class

Một class `JwtFilter` có thể được tạo **hai instances**:
- một instance do `@Bean`;
- một instance do `new JwtFilter()` trong chain.

Log chỉ ghi tên class sẽ không cho biết đó là hai instances. Khi debug, có thể ghi identity (ví dụ `System.identityHashCode(this)`) trong môi trường test, bean name/registration name và dispatcher type. Không biến identity hash code thành security identifier duy nhất; nó chỉ hữu ích để phân biệt nhanh ở một JVM.

## 9. MockMvc không thay thế full integration test

**Unit test filter** có thể khẳng định một nhánh `doFilter` gọi next đúng một lần. **MockMvc** có thể test Spring MVC + Spring Security integration hiệu quả. Nhưng một `MockMvcBuilders.standaloneSetup(...)` có thể không khởi động **Servlet container đầy đủ**, nên bỏ sót Boot auto-registration của Filter beans. Một lỗi ở Tomcat thật có thể không xuất hiện trong standalone test.

| Test | Kiểm tra tốt | Không chứng minh hoàn toàn |
| --- | --- | --- |
| Unit test filter | Logic branch, `chain.doFilter`, error handling | Container registrations, actual security chain |
| `@WebMvcTest`/`@AutoConfigureMockMvc` | Routing, security policy, response 401/403 | Mọi container filter registration và dispatcher lifecycle |
| **`@SpringBootTest(webEnvironment=RANDOM_PORT)`** | HTTP server thật, Boot auto-registration, security chain, response behavior | Proxy/ingress bên ngoài, production retry/config differences |

Ví dụ mục 5 dùng `RANDOM_PORT` để phát hiện một phần duplicate filter registration. Một test tốt không chỉ kiểm tra status 200: nó cần xác nhận **số lần chạy**, policy 401/403, CORS/CSRF nếu có, và chain matching.

**Các test khác nên bổ sung** cho hệ thống thật:
- API thiếu authorization trả 401, authenticated nhưng thiếu role trả 403 khi route cần quyền;
- fallback deny đúng mọi endpoint nhạy cảm;
- `/api/**` không bị fallback chain shadowing;
- custom filter chạy đúng một lần trên successful request và không gọi service hai lần;
- `OPTIONS` CORS preflight xử lý phù hợp;
- POST có CSRF token hoặc stateless policy được quyết định rõ;
- `ASYNC`/`ERROR` dispatch không tạo bất ngờ;
- khi deploy WAR/external Tomcat, kiểm tra thêm `web.xml` và `@WebFilter` registrations;
- proxy retries/redirects không bị hiểu nhầm là duplicate filter trong app.

## 10. CORS và CSRF: thứ tự sai có thể gây 401/403

### 10.1. CORS preflight

Browser có thể gửi:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: Authorization, Content-Type
~~~

Preflight thường **không có session cookie** như request chính. Nếu authentication logic chạy trước CORS và bắt phải có credentials, response dễ thành 401/403. Spring Security có `http.cors(Customizer.withDefaults())` và hỗ trợ tích hợp `CorsConfigurationSource`/MVC CORS config.

**Không** đăng ký cùng `CorsFilter` một lần ở container và một lần trong Spring Security mà không có design rõ ràng; dễ làm response trùng `Access-Control-Allow-*` hoặc xử lý preflight không nhất quán.

Ví dụ đoạn cấu hình **minh họa**, chưa kèm allowed origins và imports đầy đủ:

~~~java
http.cors(Customizer.withDefaults())
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

CORS **không phải authorization**. Nó chỉ quyết định browser có cho frontend origin đọc response từ server khác origin không. `Origin` policy phải dùng explicit allowlist và credential rules đúng; không phản xạ Origin bất kỳ chỉ vì muốn tránh 403.

### 10.2. CSRF

`CsrfFilter` bảo vệ các request state-changing theo security policy. Với ứng dụng web dùng session/cookie, POST form thiếu token có thể bị 403. Đừng tắt CSRF toàn app để “sửa lỗi filter chạy hai lần”: hãy xem chain chọn đúng chưa, request method, CSRF token, session, repository và filter nào đã chạy.

Với stateless API chỉ nhận bearer token qua Authorization header, có thể có chính sách CSRF khác, nhưng phải dựa trên threat model và cấu hình chain riêng. Không giả định mọi SPA, cookie, cross-site credential flow đều an toàn khi `csrf.disable()`.

### 10.3. JWT bị decode hai lần

Nếu đã dùng:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Spring Security có `BearerTokenAuthenticationFilter` và chuỗi authentication tương ứng. Nếu thêm `CustomJwtFilter` riêng lại đọc `Authorization: Bearer ...`, parse JWT, gọi upstream kiểm tra và set `SecurityContext` lần nữa, bạn đang làm **double authentication logic** ngay cả khi không trùng Servlet filter registration. Chọn đúng extension point như `JwtDecoder`/`JwtAuthenticationConverter`/AuthenticationProvider hoặc audit after-authentication filter, không thêm filter tự parse toàn bộ token nếu không thật sự cần.

**Không log Authorization header, password hoặc JWT** để debug vì sẽ gây lộ thông tin. Log tên filter, request ID, dispatcher type, status, policy result là đủ cho nhiều tình huống.

## 11. Sai order và đăng ký trùng trong các mô hình khác

### 11.1. Filter dùng SecurityContext nhưng đăng ký ở container trước security proxy

Một servlet filter có `@Order(HIGHEST_PRECEDENCE)` chạy trước `DelegatingFilterProxy` sẽ **không mặc nhiên có authentication do Spring Security vừa tạo**. Nếu nó cần user ID đã đăng nhập, đặt vào Spring Security chain ở vị trí sau các authentication filters theo security architecture. Không sửa bằng cách đọc raw JWT trong filter nữa nếu Spring Security đã có decoder.

### 11.2. Filter dùng `OncePerRequestFilter` nhưng chạy thêm ở error dispatch

Khi controller ném exception, servlet container có thể dispatch tới `/error`. Nếu log thứ hai xuất hiện với `DispatcherType.ERROR`, đó có thể là error path chứ không phải registration trùng. Hãy kiểm tra `shouldNotFilterErrorDispatch()`, filter mappings và endpoint error. Một số nested error dispatch có vòng đời riêng; không sử dụng global guard làm request lỗi bỏ qua authentication.

### 11.3. Async controller và WebAsyncManager

Controller trả `Callable`/`DeferredResult` hoặc Servlet async có thể gây `ASYNC` dispatch. `WebAsyncManagerIntegrationFilter` hỗ trợ một số tác vụ context trong Spring MVC. Khi custom filter cần xử lý mỗi async dispatch, nó phải được thiết kế thread-safety và xác định rõ `shouldNotFilterAsyncDispatch()`, servlet dispatcher types và context propagation. **Đừng nhầm sự có mặt của hai thread logs với hai Servlet registrations.**

### 11.4. Reverse proxy và retry

CDN/ingress có thể retry GET khi upstream fail hoặc tạo redirect HTTP↔HTTPS. Hai request đến ứng dụng sẽ có hai sets Servlet filters; “once per request” không có nghĩa “once per browser action”. Cần correlation ID đến từ điểm ingress tin cậy và distributed traces để biết hai HTTP requests thật.

## 12. WebFlux: dùng WebFilter, không áp dụng trực tiếp Servlet Filter

Trong **Spring WebFlux/Netty**, Spring Security có hệ sinh thái khác:

| MVC/Servlet | WebFlux/Reactive |
| --- | --- |
| `jakarta.servlet.Filter` | `org.springframework.web.server.WebFilter` |
| `FilterChainProxy` | `WebFilterChainProxy` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `addFilterBefore/After` | `addFilterAt(WebFilter, SecurityWebFiltersOrder)` |
| Servlet container registration | Reactive web filter configuration |
| `OncePerRequestFilter` | Không áp dụng trực tiếp cho reactive WebFilter |

Đoạn cấu hình minh họa WebFlux (không nằm trong project MVC, cần WebFlux Security dependencies/imports):

~~~java
@Bean
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Cần kiểm tra `SecurityWebFilterChain` order và `SecurityWebFiltersOrder` cho custom reactive filters. Nếu một WebFilter được đăng ký ở outer reactive chain và trong Spring Security chain, logic có thể bị gọi nhiều lần tương tự nguyên tắc Servlet, nhưng không dùng `FilterRegistrationBean` của Servlet để chữa lỗi trong Netty.

Nếu project khai báo cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường ưu tiên Servlet MVC application type. Không kết luận đang chạy WebFlux chỉ vì có `Mono` hoặc `WebClient`. Và không dùng ThreadLocal security context như thể reactive stream luôn chạy cùng một thread.

## 13. Anti-pattern và cách sửa nhanh

| Anti-pattern | Lỗi | Sửa |
| --- | --- | --- |
| `@Component Filter` + `addFilterBefore(bean, ...)` | Boot auto-register container, Security cũng gọi filter | Không làm bean hoặc disable Servlet registration |
| `@WebFilter`/`@ServletComponentScan` + bean filter | Hai hình thức Servlet registration có thể trùng | Chỉ chọn một registration |
| Tự đăng ký hai `DelegatingFilterProxy` | Spring Security pipeline có thể bị gọi lại | Để Boot đăng ký proxy đúng một lần |
| Chain `/**` `@Order(1)` trước `/api/**` | Specific chain bị shadow | Chain hẹp trước, fallback cuối |
| Nghĩ `requestMatchers` chọn chain | Matcher cấp authorization bị hiểu sai | `securityMatcher` quyết định chain |
| Dùng `FilterRegistrationBean#setOrder` để xếp custom security filter | SetOrder chỉ ảnh hưởng container chain | `HttpSecurity.addFilterBefore/After` |
| `OncePerRequestFilter` che triệu chứng | Duplicate registration vẫn tồn tại | Sửa root cause và kiểm tra cả 2 registry |
| Dùng static boolean “đã lọc” | Các request sau bị skip | Chỉ guard theo request/dispatch đúng contract |
| Gọi `chain.doFilter(...)` 2 lần | Downstream có thể chạy 2 lần | Gọi tiếp một lần nếu phù hợp |
| Xác thực JWT ở hai filters | CPU và auth context bị ghi đè | Dùng built-in bearer support và extension points |
| Tắt CORS/CSRF hoặc permitAll để khỏi 401/403 | Tạo lỗ hổng bảo mật mới | Giữ policy và sửa thứ tự/filter configuration |
| Log credentials để debug | Rò rỉ password/token/cookie | Chỉ log các metadata an toàn |
| Chỉ test MockMvc standalone | Có thể bỏ lọt Servlet registration của Boot | Thêm RANDOM_PORT integration test |

## 14. Quy trình debug có thể áp dụng ngay

1. Ghi HTTP method, path, request ID, dispatcher type và response status. Đếm theo request thật, không chỉ theo URL.
2. Bật `DefaultSecurityFilterChain=DEBUG` để xem chains/matchers/filters lúc startup, `FilterChainProxy=TRACE` ở staging để xem route đang chọn.
3. Xem Servlet registrations thật qua container registry/logs. Đừng nhầm proxy `springSecurityFilterChain` hợp lệ với custom filter đăng ký thêm.
4. Tìm mọi nguồn tạo filter: `@Component`, `@Bean Filter`, `@WebFilter`, `@ServletComponentScan`, `FilterRegistrationBean`, manual `ServletContext.addFilter` và library auto-config.
5. Xem custom filter có **một** instance hay nhiều instances, nằm trong security chain nào và container chain nào.
6. Kiểm tra chain `@Order`, `securityMatcher`, fallback, cùng authorization `requestMatchers`. Đừng để chain rộng shadow chain hẹp.
7. Kiểm tra vị trí custom filter với authn, authz, CORS/CSRF, SecurityContextHolderFilter. Đặc biệt cẩn thận filter tự parse JWT cùng resource server.
8. Tách `REQUEST` với `ERROR`/`ASYNC`; xem browser redirect, favicon, preflight và proxy retry.
9. Chạy full integration test HTTP container và test 401/403/200, filter count, routes, anonymous/authenticated, CSRF/CORS.
10. Sửa **một nguyên nhân gốc**: bỏ registration thứ hai, disabled FilterRegistrationBean cho bean dùng trong Security, hoặc thay `@Order`/matcher. Không vô hiệu hóa Spring Security để “chữa”.
11. Chạy lại test, tắt TRACE, xóa debug endpoint và tránh để secrets ở logs.

### Triệu chứng → nghi ngờ

| Triệu chứng | Giải thích có thể | Xác minh |
| --- | --- | --- |
| Custom filter xuất hiện ở cả servlet registry và security DEBUG | Double registration | So class/instance và source bean/registration |
| `auditCount=2` sau gắn `@Component` | Container thêm một vòng gọi filter | Bỏ @Component, dùng new hoặc disabled registration |
| Filter log một lần nhưng HTTP response có hai dấu vết | Hai requests/dispatch hoặc filter guard che lần lặp | Request ID, dispatcher type, servlet registry |
| `/api/**` bị xử lý theo fallback | Chain rộng đứng trước hoặc matcher sai | TRACE first matching, `@Order` |
| OPTIONS trả 401 | CORS preflight bị auth chặn | CORS config và filter ordering |
| POST trả 403 | CSRF token/authorization thiếu | Log selected chain, CSRF, authentication |
| Filter không nhìn thấy user | Đứng trước authentication hoặc context loading | Xem vị trí tương đối, auth provider |
| Chỉ test MockMvc pass, prod gọi hai lần | Test không khởi động real container auto-registration | SpringBootTest RANDOM_PORT |
| JWT verification lặp | Built-in resource server + custom parser | Chain list và decoder metrics |
| Lỗi chỉ ở `/error` | ERROR dispatch | DispatcherType, filter mapping |
| Thêm `setOrder(-100)` nhưng không đổi vị trí security custom filter | Đổi nhầm container order | Dùng `addFilterBefore/After` |
| Endpoint nhạy cảm không bị chặn | Không security chain match hoặc policy fallback permitAll | Chain matcher và deny-by-default |

## 15. Câu hỏi tự kiểm tra

1. `DelegatingFilterProxy` và `FilterChainProxy` khác nhau ở trách nhiệm nào?
2. Có hai `SecurityFilterChain` nghĩa là một request chạy qua cả hai không?
3. `@Order(1)` trên security chain và `addFilterBefore` khác nhau thế nào?
4. Vì sao một `Filter` có `@Component` và đồng thời `http.addFilterBefore(bean, ...)` có thể chạy hai lần?
5. Cách làm một Filter bean chỉ chạy trong Spring Security chain mà không được Boot auto-register vào container là gì?
6. `OncePerRequestFilter` có chứng minh chỉ có một Servlet registration không?
7. `securityMatcher("/api/**")` khác `requestMatchers(...)` của `authorizeHttpRequests` ra sao?
8. Vì sao một chain match mọi path đứng đầu có thể gây lỗ hổng?
9. Filter xác thực user nên chạy trước hay sau `AuthorizationFilter`?
10. Khi log một URL hai lần, cần xem những dispatcher types và client behaviors nào?
11. Tại sao cần `@SpringBootTest(webEnvironment=RANDOM_PORT)` để phát hiện duplicate Servlet registration?
12. FilterRegistrationBean#setOrder có xếp filter bên trong SecurityFilterChain không?
13. Vì sao CORS preflight có thể bị 401 ngay trước login dù browser đã có session?
14. Khi có `oauth2ResourceServer().jwt()`, lý do nào khiến custom JWT filter riêng gây double-auth?
15. Nếu filter cần dependency injection, có thể dùng những cách nào để vẫn tránh auto-registration?
16. Có nên chuyển tất cả endpoints thành `permitAll` khi gặp duplicate filter/403 không?
17. `AuditFilter.COUNT` trong project mẫu là request attribute hay static global counter?
18. Vì sao hai log có request IDs khác nhau không chứng minh một request được xử lý hai lần?
19. Spring WebFlux dùng `WebFilterChainProxy` và loại security chain nào?
20. Tại sao `OncePerRequestFilter#doFilterInternal` chỉ hiện một lần không đủ chứng minh không có registration trùng?

**Đáp án trọng tâm:** (1) Servlet proxy tìm Spring bean, FilterChainProxy chọn security chain. (2) Không, first match only. (3) @Order xếp chains; addFilterBefore xếp filter nội bộ. (4) Boot có thể tự đăng ký Servlet Filter bean và Spring Security cũng gọi bean. (5) `FilterRegistrationBean#setEnabled(false)`. (6) Không. (7) Chọn chain vs rule authorization trong chain. (8) Chain đặc thù bị shadow hoặc policy sai. (9) Trước. (10) REQUEST/ERROR/ASYNC/FORWARD, redirect/retry/OPTIONS. (11) Nó chạy embedded server/registrations thật. (12) Không. (13) Preflight thường không mang authentication cookies. (14) Hai bộ xử lý cùng đọc/verify token và set context. (15) Tạo non-bean instance nhận service qua constructor hoặc bean + disabled registration. (16) Không, sửa root cause. (17) Request attribute. (18) Có thể là hai HTTP requests. (19) `SecurityWebFilterChain`. (20) Guard có thể che một nested invocation mà registration vẫn sai.

## 16. Nguồn chính thức

- Spring Security 6.5 — Servlet architecture, DelegatingFilterProxy, FilterChainProxy, Filter order, custom filter bean registration: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Multiple HttpSecurity, `securityMatcher` vs `requestMatchers` và first-matching chain: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Boot 3.5 — Embedded Web Servers, disable Servlet/Filter bean registration: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Framework 6.2 — OncePerRequestFilter API, ASYNC/ERROR dispatch: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security 6.5 — Reactive Security/`SecurityWebFilterChain`: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Reactive architecture/`WebFilterChainProxy`: https://docs.spring.io/spring-security/reference/6.5/reactive/architecture.html
- Spring Boot 3.5.16, System Requirements (Java 17+): https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5.16, release announcement and end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
