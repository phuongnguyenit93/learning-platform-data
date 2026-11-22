# Tránh đăng ký bộ lọc hai lần qua Spring Boot và Spring Security

## 1. Mục tiêu và lỗi thường gặp

Trong ứng dụng Spring Boot dùng Servlet web stack và Spring Security, một custom Filter có thể đi vào **hai chuỗi xử lý khác nhau**:

- Chuỗi **Servlet filters** mà embedded Tomcat/Jetty/Undertow quản lý.
- Chuỗi **Security filters** nằm bên trong FilterChainProxy của Spring Security.

Khi một class implements jakarta.servlet.Filter được đánh dấu @Component hoặc khai báo là @Bean, Spring Boot có thể **tự đăng ký nó như một filter của Servlet container**. Nếu cùng instance đó lại được thêm bằng HttpSecurity.addFilterBefore/addFilterAfter/addFilterAt, filter có thể bị gọi **hai lần** trên một request, ở những vị trí và thứ tự khác nhau. Đây là vấn đề wiring/registration chứ không nhất thiết là bug của phương thức doFilter.

Hậu quả thường thấy:

- Audit log/metric bị ghi hai lần, event phát hai lần.
- Gọi downstream, đọc token, tính phí hoặc cập nhật dữ liệu lặp.
- Header/tracing context bị set/clear nhiều lần.
- Security logic có thể chạy trước khi authentication context sẵn sàng, hoặc chạy bên ngoài security matcher.
- Request/response wrapper bị bọc nhiều lớp.
- Một số request chỉ gặp lỗi ở ERROR/ASYNC dispatch, làm vấn đề khó tái hiện.
- Developer dùng OncePerRequestFilter thấy doFilterInternal chỉ chạy một lần rồi kết luận không có duplicate registration, trong khi có hai điểm đăng ký thật.

Mục tiêu của bài: phân biệt hai chain, tái hiện nguyên nhân, sửa đúng bằng FilterRegistrationBean.setEnabled(false) hoặc không tạo Filter bean, xác nhận bằng HTTP integration test, hiểu phạm vi OncePerRequestFilter, securityMatcher, dispatcher types và các điểm cần chú ý khi có nhiều SecurityFilterChain.

**Phiên bản ví dụ:** Java 17+, Spring Boot 3.3.x, Spring Security 6.x và Servlet web stack. Spring Boot 4/Spring Security 7 có một số thay đổi API, dependency/starter và cấu hình; đối chiếu tài liệu chính thức của phiên bản thực tế trước khi chuyển code. Bài học này không viết về WebFlux SecurityWebFilterChain trừ phần so sánh ranh giới.

## 2. Sơ đồ hai lớp filter

Một request điển hình:

~~~text
Client HTTP request
        |
        v
Embedded Servlet Container (Tomcat/Jetty)
        |
        v
Servlet Filter A
        |
        v
DelegatingFilterProxy ("springSecurityFilterChain")
        |
        v
Spring Bean: FilterChainProxy
        |
        +--> First matching SecurityFilterChain
                 |
                 +--> SecurityContextHolderFilter
                 +--> authentication-related filters
                 +--> custom security filter
                 +--> AuthorizationFilter
                 +--> ...
        |
        v
Servlet Filter B
        |
        v
DispatcherServlet -> Controller
        |
        v
HTTP response
~~~

Sơ đồ là biểu diễn khái quát; thứ tự chính xác phụ thuộc cấu hình và các filter được bật. Một Servlet Filter có thể đứng **trước hoặc sau** DelegatingFilterProxy. Nó không nhất thiết có được security context giống filter bên trong SecurityFilterChain.

Ba tên cần nhớ:

- **DelegatingFilterProxy:** Filter được đăng ký với Servlet container, chuyển lời gọi tới Spring-managed bean có tên tương ứng. Với Spring Security, target bean thường tên springSecurityFilterChain.
- **FilterChainProxy:** Bean Spring Security chứa danh sách SecurityFilterChain và chọn chain áp dụng cho request.
- **SecurityFilterChain:** Danh sách các Security Filter dùng để xử lý request phù hợp với RequestMatcher của chain đó.

SecurityFilterChain **không phải** Servlet FilterRegistrationBean. Spring Boot có thể đăng ký filter thành phần ngoài Servlet chain; Spring Security thêm filter vào chain nội bộ. Vì vậy một class hiện diện ở cả hai nơi không phải hai tên gọi cho cùng một lần đăng ký.

## 3. Tại sao @Component hoặc @Bean tạo duplicate?

Giả sử ta viết một filter:

~~~java
@Component
public class TokenInspectionFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Đọc/kiểm tra thông tin request.
        chain.doFilter(request, response);
    }
}
~~~

Trong Spring Boot Servlet app, @Component tạo một Spring bean có kiểu Filter. Boot tự phát hiện và đăng ký các Filter bean vào embedded servlet container. Đồng thời cấu hình security:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        TokenInspectionFilter tokenFilter) throws Exception {

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.addFilterBefore(
            tokenFilter,
            UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
~~~

Đây là **ví dụ cấu hình gây rủi ro**, chưa có phần authentication thực tế. Filter cùng instance được container đăng ký một lần và được SecurityFilterChain sử dụng một lần. Thứ tự chính xác có thể phụ thuộc filter registration order và security chain order.

Spring Security documentation nêu trực tiếp rằng Filter bean (@Component hoặc @Bean) được Spring Boot auto-register với container, nên nếu cùng thêm vào SecurityFilterChain nó có thể được gọi hai lần. Tài liệu khuyên không tạo Filter bean nếu không cần; nếu cần dependency injection thì đăng ký FilterRegistrationBean với enabled=false.

### 3.1. Hai lần đăng ký không nhất thiết là hai instance

Nếu @Component và HttpSecurity dùng cùng object từ dependency injection, có **một object** nhưng **hai đường vào** doFilter. Vì vậy số bean = 1 không chứng minh số registration = 1.

Ngược lại, nếu vừa có @Component TokenInspectionFilter và vừa new TokenInspectionFilter() cho security, có thể tồn tại **hai object** cùng chức năng. Việc tắt registration cho một object không sửa object còn lại; cần rà toàn bộ cấu hình.

### 3.2. Vì sao đôi khi log chỉ xuất hiện một lần?

OncePerRequestFilter dùng request attribute để tránh gọi doFilterInternal trùng trong một dispatch thích hợp. Trong trường hợp hai lần gọi lồng nhau của **cùng filter**, lần thứ hai có thể bị guard bỏ qua. Tuy nhiên hai registration vẫn tồn tại, thứ tự vẫn có thể sai, hành vi có thể khác ở ERROR/ASYNC dispatch hoặc với những filter không kế thừa OncePerRequestFilter.

Không dùng số dòng log trong doFilterInternal để chứng minh rằng filter chỉ được đăng ký một lần. Khi điều tra, phải kiểm tra cấu hình container và security chain.

## 4. Các cách đăng ký Filter trong Spring Boot

| Cách | Ai sở hữu lifecycle/registration? | Dùng khi nào |
| --- | --- | --- |
| @Component trên Filter | Boot auto-register với Servlet container | Filter hạ tầng áp dụng rộng ở Servlet layer |
| @Bean trả Filter | Boot auto-register với Servlet container | Tương tự, cần khởi tạo qua configuration |
| @Bean FilterRegistrationBean<T> enabled=true | Boot đăng ký rõ qua container với URL/order/dispatcher | Chỉ muốn Servlet filter và kiểm soát mapping |
| @WebFilter + @ServletComponentScan | Servlet component scanning / container registration | Dự án dùng Servlet component model |
| HttpSecurity.addFilterBefore/After/At | Spring Security FilterChainProxy | Security logic trong một SecurityFilterChain |
| FilterRegistrationBean<T> enabled=false | **Vô hiệu hóa** registration ở container cho Filter bean | Filter là Spring bean nhưng chỉ chạy trong security chain |
| new CustomFilter(...) bên trong cấu hình HttpSecurity | FilterChainProxy nhận instance, không tự thành Servlet bean | Security filter không cần bean độc lập |

Cảnh báo: @WebFilter chỉ có hiệu lực theo cách component scanning của Servlet được kích hoạt/triển khai; không nên trộn nó với @Component và một FilterRegistrationBean khác cho cùng chức năng.

**Một filter nên có một chủ sở hữu chính.** Nếu là hạ tầng servlet trước mọi security decision, quản lý nó bằng container registration. Nếu phụ thuộc vào security context và security matcher, quản lý qua HttpSecurity. Tránh kết hợp hai cách chỉ vì cả hai đều có thể biên dịch.

## 5. Phương án A: security-only filter không là Spring bean

Cách đơn giản là tạo filter ngay khi cấu hình SecurityFilterChain:

~~~java
@Configuration(proxyBeanMethods = false)
class SecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated());

        http.addFilterBefore(
                new MySecurityAuditFilter(),
                AuthorizationFilter.class);

        return http.build();
    }
}
~~~

MySecurityAuditFilter là class implements Filter được tạo bằng new, **không có @Component và không có @Bean trả về instance đó**. Vì không phải Servlet Filter bean, Boot sẽ không tự đăng ký object này với container. Nó được quản lý theo cấu hình security chain.

Nếu filter cần dependency injection, có thể truyền service qua constructor:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        AuditService auditService) throws Exception {

    MySecurityAuditFilter audit =
            new MySecurityAuditFilter(auditService);

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.addFilterBefore(audit, AuthorizationFilter.class);
    return http.build();
}
~~~

AuditService là dependency giả định cần định nghĩa; đây là snippet kiến trúc. Dù filter không phải bean, constructor của configuration vẫn nhận các Bean khác rồi truyền xuống. Đừng cho filter tự truy cập ApplicationContext tùy tiện; constructor injection rõ ràng giúp test dễ hơn.

**Lưu ý về lifecycle:** Vì filter không phải Spring bean độc lập, không dựa vào @PostConstruct, @PreDestroy, @Autowired fields hoặc @ConfigurationProperties trên chính filter để được Boot thực hiện như với Bean. Nếu cần quản lý lifecycle, cấu hình rõ hoặc cân nhắc phương án B.

## 6. Phương án B: filter là Bean, tắt container registration

Khi cần injection, metrics hoặc quản lý Bean cho một custom security filter, phương án được Spring Security/Spring Boot khuyến nghị:

~~~java
@Bean
FilterRegistrationBean<MySecurityAuditFilter> disableAutoRegistration(
        MySecurityAuditFilter filter) {

    FilterRegistrationBean<MySecurityAuditFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

Kết hợp:

~~~java
@Bean
MySecurityAuditFilter securityAuditFilter(
        AuditService auditService) {
    return new MySecurityAuditFilter(auditService);
}

@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        MySecurityAuditFilter filter) throws Exception {

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.addFilterBefore(filter, AuthorizationFilter.class);
    return http.build();
}
~~~

Ở hai snippet trên, MySecurityAuditFilter và AuditService là class giả định cần định nghĩa. Ý nghĩa quan trọng:

1. **Chỉ một Filter Bean:** Bean được tạo cho dependency injection.
2. **FilterRegistrationBean cho đúng instance:** Boot thấy wrapper registration của filter đó, với enabled=false, nên không tự map filter đó vào Servlet container.
3. **HttpSecurity thêm filter vào SecurityFilterChain:** Filter chạy ở vị trí xác định bởi API addFilterBefore/After.
4. **Không đụng DelegatingFilterProxy của Spring Security:** Nó vẫn phải được đăng ký ở Servlet container để SecurityFilterChain được thực thi.

Tắt registration ở đây **không vô hiệu hóa security filter trong Spring Security**. Nó chỉ ngăn đường đăng ký Servlet thứ hai đối với custom Filter Bean.

### 6.1. Vì sao không dùng registration.setOrder(...) thay cho enabled=false?

FilterRegistrationBean#setOrder điều chỉnh **thứ tự Servlet filter**. Nó không xóa registration và không điều chỉnh thứ tự của filter bên trong SecurityFilterChain. Nếu filter vẫn nằm ở cả hai nơi, đổi order chỉ làm hai lần chạy xuất hiện tại những vị trí khác nhau.

Muốn security-only filter: setEnabled(false) ở container registration, rồi dùng addFilterBefore/After theo thứ tự security phù hợp.

### 6.2. Vì sao FilterRegistrationBean phải trỏ đúng Bean?

Nếu đã có:

~~~java
@Bean
MySecurityAuditFilter auditFilter() {
    return new MySecurityAuditFilter();
}
~~~

nhưng lại viết:

~~~java
@Bean
FilterRegistrationBean<MySecurityAuditFilter> disabled() {
    FilterRegistrationBean<MySecurityAuditFilter> registration =
            new FilterRegistrationBean<>(
                    new MySecurityAuditFilter());
    registration.setEnabled(false);
    return registration;
}
~~~

Cấu hình sai này tạo thêm object thứ hai trong registration bean. Nó **không đảm bảo** auto-registration của Bean auditFilter thực tế bị tắt. Phải inject đúng Bean vào constructor của FilterRegistrationBean.

## 7. Project thực hành: chứng minh filter chỉ chạy một lần

Ví dụ hoàn chỉnh dưới đây dùng Java 17+, Spring Boot 3.3.x, Spring Security 6.x, embedded Tomcat và **HTTP server thật**. Custom RequestAuditFilter cố tình dùng GenericFilterBean thay vì OncePerRequestFilter để phép thử nhìn thấy chính xác số lần vào doFilter. Nó không xử lý authentication, chỉ đánh dấu response header theo số lần filter được gọi trong một request.

API có GET /api/hello công khai và những path khác yêu cầu authentication theo rule minh họa. Chỉ để học việc đăng ký filter; **không phải mẫu bảo mật production**.

Cấu trúc:

~~~text
filter-registration-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          filters/
            FilterRegistrationDemoApplication.java
            HelloController.java
            RequestAuditFilter.java
            SecurityConfiguration.java
      resources/
        application.yml
    test/
      java/
        example/
          filters/
            FilterRegistrationDemoTests.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'filter-registration-demo'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chỉ có Servlet MVC starter; không thêm spring-boot-starter-webflux. Boot 3.3 sử dụng Java 17 trở lên. Cần tạo Gradle Wrapper có phiên bản được Boot 3.3 hỗ trợ; nếu dự án đã có build convention thì nên theo phiên bản quản lý của dự án thay vì copy version demo.

### 7.3. application.yml

~~~yaml
spring:
  application:
    name: filter-registration-demo

server:
  port: 8080
~~~

### 7.4. FilterRegistrationDemoApplication.java

~~~java
package example.filters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterRegistrationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                FilterRegistrationDemoApplication.class, args);
    }
}
~~~

### 7.5. HelloController.java

~~~java
package example.filters;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }
}
~~~

Chỉ có một GET endpoint công khai. Không đưa token hay secret thật vào demo để tránh tạo thói quen log/echo dữ liệu nhạy cảm.

### 7.6. RequestAuditFilter.java

~~~java
package example.filters;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.GenericFilterBean;

public class RequestAuditFilter extends GenericFilterBean {

    private static final String ATTR =
            RequestAuditFilter.class.getName() + ".count";

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        Integer previous = (Integer) request.getAttribute(ATTR);
        int count = previous == null ? 1 : previous + 1;
        request.setAttribute(ATTR, count);

        if (response instanceof HttpServletResponse http) {
            http.setHeader(
                    "X-Audit-Filter-Calls", Integer.toString(count));
        }

        chain.doFilter(request, response);
    }
}
~~~

Cơ chế đếm được giữ trên **ServletRequest attribute** thay vì một field singleton. Nó độc lập giữa các request, giúp test không phụ thuộc vào thứ tự chạy hoặc concurrent request. Nếu cùng filter được gọi lần thứ hai trong cùng một request/dispatch, header cuối cùng thường mang giá trị 2.

Đây chỉ là filter quan sát phục vụ lab, không phải authentication filter hay hệ thống audit production. Trên ứng dụng thật, không tin response header do client không xác thực cung cấp làm bằng chứng security. Nếu dùng filter ghi event bên ngoài, phải có idempotency và bảo vệ dữ liệu.

### 7.7. SecurityConfiguration.java

~~~java
package example.filters;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    RequestAuditFilter requestAuditFilter() {
        return new RequestAuditFilter();
    }

    @Bean
    FilterRegistrationBean<RequestAuditFilter> disableContainerAudit(
            RequestAuditFilter filter) {

        FilterRegistrationBean<RequestAuditFilter> registration =
                new FilterRegistrationBean<>(filter);

        registration.setEnabled(false);
        return registration;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestAuditFilter filter) throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.GET, "/api/hello")
                .permitAll()
                .anyRequest()
                .authenticated());

        http.addFilterBefore(
                filter,
                AuthorizationFilter.class);

        return http.build();
    }
}
~~~

Đây là cấu hình **đúng** cho một security-only custom filter:

- requestAuditFilter() tạo đúng một Filter Bean, không cần @Component.
- disableContainerAudit(...) nhận **cùng Bean** rồi tắt đăng ký Servlet cho nó.
- securityFilterChain(...) thêm Bean đó vào Spring Security trước AuthorizationFilter.
- springSecurityFilterChain do Spring Security/Boot tích hợp sẽ vẫn xuất hiện dưới dạng proxy Servlet ở container.
- GET /api/hello được permitAll để client có thể kiểm thử không cần credentials. Những path khác cần authentication; demo không cấu hình user store hoặc login flow cho chúng.

Filter đứng trước AuthorizationFilter, nhưng vì đây là filter chỉ đánh dấu header, ví dụ không phụ thuộc vào trạng thái authentication cụ thể. Với filter cần authenticated user, phải chọn vị trí **sau authentication filters** theo Security architecture và kiểm thử chính xác. Không đặt một authentication/authorization filter tùy tiện chỉ vì thấy một tên filter tồn tại.

### 7.8. FilterRegistrationDemoTests.java

~~~java
package example.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterRegistrationDemoTests {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    FilterRegistrationBean<RequestAuditFilter> registration;

    @Test
    void containerRegistrationIsDisabled() {
        assertFalse(registration.isEnabled());
    }

    @Test
    void filterInvokedExactlyOnceOverHttp() {
        ResponseEntity<String> response =
                rest.getForEntity("/api/hello", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "1",
                response.getHeaders()
                        .getFirst("X-Audit-Filter-Calls"));

        String body = response.getBody();
        assertNotNull(body);
        assertTrue(body.contains("\"hello\""));
    }

    @Test
    void anotherGetStillHasOneInvocation() {
        ResponseEntity<String> response =
                rest.getForEntity("/api/hello", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "1",
                response.getHeaders()
                        .getFirst("X-Audit-Filter-Calls"));
    }
}
~~~

Test đầu xác minh wrapper registration có enabled=false. Hai test sau tạo **embedded HTTP server thật** trên port ngẫu nhiên, gửi request qua TCP và đọc header do filter đặt. HTTP test có giá trị hơn unit test chỉ gọi doFilter trực tiếp, bởi cần kiểm tra cả Servlet registration lẫn Spring Security registration.

Các assertion kỳ vọng khi dùng đúng Spring Boot/Spring Security versions và code tương ứng. Nếu test không pass, cần kiểm tra actual startup logs và exception thay vì tuyên bố source đã chứng minh thành công. Bài học này cung cấp source và kết quả dự kiến; không khẳng định đã thực thi Gradle trên môi trường người học.

Chạy:

~~~bash
./gradlew test
~~~

Hoặc trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Khởi động thủ công:

~~~bash
./gradlew bootRun
~~~

Gọi HTTP:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Response dự kiến: HTTP 200, JSON có message="hello" và response header:

~~~http
X-Audit-Filter-Calls: 1
~~~

Không cần phụ thuộc vào thứ tự các JSON keys hoặc một giá trị ID ngẫu nhiên.

## 8. Tái hiện lỗi double registration một cách có kiểm soát

Trong một branch lab riêng, **chỉ để quan sát và không deploy**, có thể tạm bỏ method disableContainerAudit(...) nhưng giữ RequestAuditFilter là @Bean và tiếp tục addFilterBefore.

Lúc này:

1. Spring Boot thấy Filter Bean và tự đăng ký nó như Servlet Filter.
2. Spring Security FilterChainProxy nhận cùng Bean qua HttpSecurity.addFilterBefore.
3. Khi GET /api/hello đi qua cả hai integration points, GenericFilterBean#doFilter có thể được gọi hai lần.
4. Header X-Audit-Filter-Calls có thể trở thành 2 thay vì 1.
5. Integration test filterInvokedExactlyOnceOverHttp thất bại, giúp xác nhận lỗi.

Cần hiểu chính xác: **kết quả thực tế phụ thuộc thứ tự Servlet Filter, dispatcher types và đường đi request**; không nên ép kết luận mọi môi trường luôn nhận 2 với mọi URI. Nhưng với hai registrations cùng áp dụng một request, nguy cơ double invocation là thực.

Sau thử nghiệm, **khôi phục method disableContainerAudit() trước khi sử dụng**, chạy lại tests và xác minh header là 1. Không cần sửa code filter hay thêm cờ skip trong nghiệp vụ chỉ để che triệu chứng.

### 8.1. Vì sao dùng GenericFilterBean trong phép thử?

GenericFilterBean cho thấy doFilter invocation trực tiếp. Nếu dùng OncePerRequestFilter, cơ chế already-filtered attribute có thể skip doFilterInternal lần thứ hai khi nested calls, làm log trong doFilterInternal trông như chỉ chạy một lần. Điều đó không chứng minh configuration đúng.

Production có thể dùng OncePerRequestFilter cho tính chất once-per-dispatch phù hợp; còn test hạ tầng cần kiểm tra **có bao nhiêu nơi filter được đăng ký**, không chỉ số lần một callback nội bộ được chạy.

## 9. OncePerRequestFilter: hữu ích, nhưng không chữa registration trùng

OncePerRequestFilter nằm trong org.springframework.web.filter. Nó cung cấp cấu trúc doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain) và sử dụng một request attribute để đánh dấu đã lọc trong một dispatch nhất định.

Ví dụ:

~~~java
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader(
                "X-Request-Id", UUID.randomUUID().toString());
        chain.doFilter(request, response);
    }
}
~~~

Đây là snippet minh họa; cần import jakarta.servlet.*, jakarta.servlet.http.*, java.io.IOException, UUID và OncePerRequestFilter.

**Hai câu hỏi riêng:**

- Filter có được **đăng ký đúng một nơi** không? Kiểm tra Servlet registrations và SecurityFilterChain.
- Filter có thực thi logic mong muốn **một lần mỗi request/dispatch** không? Kiểm tra OncePerRequestFilter và async/error dispatch behavior.

Không thay câu hỏi đầu bằng câu trả lời thứ hai. OncePerRequestFilter có thể hữu ích cho bảo vệ logic khi dispatch lại, nhưng không đảm bảo auto-registration được tắt và cũng không làm đúng thứ tự so với authentication/authorization.

### 9.1. Already-filtered marker và nhiều instance

OncePerRequestFilter thường dùng attribute gắn với tên filter để tránh chạy lặp. Nếu có nhiều filter instance/class/bean name hoặc request đi qua các dispatch khác nhau, guard có thể hoạt động không giống giả định. Không thiết kế hệ thống dựa vào việc hai registrations lỗi trùng nhau sẽ luôn tình cờ dùng chung marker.

Nếu có hai object khác nhau cùng chức năng nhưng attribute name khác, doFilterInternal có thể chạy cả hai. Tốt nhất vẫn là chỉ khai báo một owner/registration.

### 9.2. ASYNC và ERROR dispatch

Servlet request có thể phát sinh REQUEST, ASYNC, ERROR, FORWARD hoặc INCLUDE dispatch tùy container/configuration. OncePerRequestFilter có các hook shouldNotFilterAsyncDispatch() và shouldNotFilterErrorDispatch(); FilterRegistrationBean cũng có dispatcher types.

Một filter có thể chạy trong hai dispatch hợp lệ mà **không có double registration**. Vì thế, khi thấy số lần gọi >1, log thêm dispatcher type và request identity (không log secrets) để phân biệt:

- Gọi hai lần trong cùng dispatch do đăng ký trùng.
- Gọi một lần ở REQUEST và một lần ở ASYNC/ERROR theo cấu hình.
- Hai HTTP requests riêng (ví dụ browser gọi thêm favicon).
- Internal forward hoặc error routing.

Đừng dùng global static counter không gắn request để chứng minh duplicate registration.

## 10. FilterRegistrationBean#setEnabled(false) thực sự làm gì?

Mục đích là chặn việc **Servlet container tự thêm custom Filter Bean**. Nó không đổi:

- Việc Spring Security tạo FilterChainProxy.
- Việc DelegatingFilterProxy gọi FilterChainProxy.
- Thứ tự HttpSecurity.addFilterBefore/After.
- Matching của một SecurityFilterChain.
- Logic doFilter của Filter Bean.
- Authorization policy.
- FilterRegistrationBean của một filter khác.

Nếu Spring Security không thêm Filter đó vào bất kỳ chain nào, đặt enabled=false sẽ khiến filter **không được chạy** qua Servlet container và cũng không có nơi thứ hai gọi nó. Phải kiểm tra cả hai nửa cấu hình.

Ngược lại, nếu filter chỉ cần chạy ở Servlet layer và không liên quan security, **không cần** đặt enabled=false; hãy để Boot đăng ký hoặc dùng một FilterRegistrationBean enabled=true, đồng thời **không** thêm nó vào SecurityFilterChain.

### 10.1. Nếu cần FilterRegistrationBean enabled=true

Ví dụ Servlet-only filter áp dụng đúng URL:

~~~java
@Bean
FilterRegistrationBean<CorrelationFilter> correlationRegistration() {
    FilterRegistrationBean<CorrelationFilter> registration =
            new FilterRegistrationBean<>(new CorrelationFilter());

    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
~~~

CorrelationFilter là class giả định; snippet chỉ minh họa container-level registration. Với filter kiểu này, không gọi HttpSecurity.addFilterBefore/After nữa. Nếu một separate @Bean CorrelationFilter khác được tạo, cần tránh Boot auto-register thêm instance đó. Quản lý nhất quán nguồn tạo instance.

### 10.2. Những method setOrder không tương đương nhau

- FilterRegistrationBean#setOrder: vị trí **Servlet chain** của một registration.
- @Order trên SecurityFilterChain bean: mức ưu tiên xét **SecurityFilterChain** khi có nhiều chain.
- HttpSecurity.addFilterBefore/After/At: vị trí **bên trong một SecurityFilterChain**.
- @Order trên một Servlet Filter class/Bean theo cơ chế Boot: ảnh hưởng cách Boot đăng ký vào container, không tự quyết định vị trí security chain.

Dùng sai “hệ tọa độ” order sẽ không chữa duplicate registration.

## 11. Chọn vị trí custom filter trong Spring Security

Spring Security duy trì một thứ tự filter theo vai trò. Dùng:

~~~java
http.addFilterBefore(myFilter, AuthorizationFilter.class);
http.addFilterAfter(myFilter, AnonymousAuthenticationFilter.class);
http.addFilterAt(myFilter, SomeKnownFilter.class);
~~~

Các dòng trên là ví dụ **các phương án độc lập**, không có nghĩa nên gọi cả ba cho cùng filter. SomeKnownFilter là placeholder của loại filter đã biết và được framework hỗ trợ; không dùng nguyên tên đó trong code.

Hướng dẫn:

- Cần authentication context: đặt filter sau những authentication filters phù hợp theo thiết kế. Chỉ đặt trước AuthorizationFilter không bảo đảm user đã authenticated nếu flow chưa chạy authentication.
- Cần validate/parse token riêng: cân nhắc Spring Security authentication mechanisms có sẵn (OAuth2 Resource Server, HTTP Basic, form login) trước khi viết filter tự xử lý token.
- Cần kiểm tra authorization: ưu tiên authorizeHttpRequests và AuthorizationManager thay vì tự trả 403 trong custom filter.
- Cần tracing/correlation ở tất cả routes: nhiều trường hợp dùng Servlet Filter hoặc observability integration chuẩn phù hợp hơn.
- Cần security-only audit có thông tin người dùng: dùng custom security filter sau authentication, với container registration tắt.
- Cần xử lý error code từ security: phải hiểu ExceptionTranslationFilter và vị trí exception được ném, không giả định mọi filter có thể throw AccessDeniedException rồi được một nơi bất kỳ bắt.

**Cẩn trọng với addFilterAt:** nó không phải thao tác “thay thế filter mặc định” trong mọi tình huống. Thêm một filter ở cùng slot khi filter mặc định còn tồn tại có thể tạo xung đột hoặc behavior không được xác định theo thứ tự. Hãy dùng DSL của Spring Security để bật/tắt/configure filter có sẵn, hoặc hiểu rõ cơ chế replacement của phiên bản đang dùng.

## 12. Có cần tự đăng ký springSecurityFilterChain không?

Thông thường **không**. Với Spring Boot Servlet app và spring-boot-starter-security, Boot/Spring Security tích hợp DelegatingFilterProxy cho bean springSecurityFilterChain. Tự thêm một DelegatingFilterProxyRegistrationBean nữa cho cùng target có thể khiến **cả security chain** được gọi lặp hoặc thay đổi thứ tự.

Không “sửa” vấn đề custom filter trùng bằng cách:

- Tắt DelegatingFilterProxy toàn bộ.
- Bỏ SecurityFilterChain khỏi application context.
- Thêm thêm một springSecurityFilterChain Servlet registration bằng tay.
- Bỏ toàn bộ security rules để filter không còn được gọi.
- Dùng web.ignoring() cho API cần bảo vệ chỉ để né filter.

Vấn đề hẹp là **custom Filter Bean có hai registrations**; sửa đúng FilterRegistrationBean của custom Bean. Sau đó tiếp tục kiểm thử authentication/authorization để bảo đảm security chain vẫn chạy đầy đủ.

### 12.1. DelegatingFilterProxy và FilterChainProxy khác gì?

DelegatingFilterProxy implement Filter và nằm trong Servlet chain. Nó tra target Spring bean (thường springSecurityFilterChain) để delegate. FilterChainProxy của Spring Security chọn SecurityFilterChain theo RequestMatcher, áp dụng các security filters và gọi chain tiếp theo.

Cấu hình security DSL thường tạo các SecurityFilterChain Bean được FilterChainProxy sử dụng. Bạn không cần tự lập danh sách toàn bộ Spring Security filters rồi đăng ký từng cái với Servlet container.

## 13. Nhiều SecurityFilterChain: trùng registration hay hai chain hợp lệ?

Spring Security cho phép nhiều SecurityFilterChain:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/admin/**");
    http.authorizeHttpRequests(auth ->
            auth.anyRequest().hasRole("ADMIN"));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain defaultChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());
    return http.build();
}
~~~

Đây là ví dụ cấu hình minh họa thay thế, không đặt chung vào project demo chính. Spring Security FilterChainProxy chọn **SecurityFilterChain đầu tiên có RequestMatcher khớp**. Một request /admin/reports không tự đi qua cả adminChain và defaultChain chỉ vì cả hai có rule phù hợp. Nếu một request không khớp chain nào, nó có thể không được Spring Security bảo vệ; nên có fallback chain rõ ràng cho phần còn lại.

Vì vậy:

- Hai SecurityFilterChain beans không tự chứng minh filter sẽ chạy hai lần.
- Cùng một custom Filter Bean có thể được thêm vào nhiều chains với scope **không giao nhau**, khi request chỉ chọn một chain thì không double do nhiều chains.
- Nếu Filter Bean đồng thời auto-register ở Servlet container, double registration vẫn có thể xảy ra **bất kể chain nào đang match**.
- Nếu tự thêm cùng filter nhiều lần **trong cùng một chain**, có một lỗi cấu hình độc lập.

### 13.1. securityMatcher và requestMatchers không giống nhau

- http.securityMatcher("/api/**") quyết định **SecurityFilterChain này có áp dụng request không**.
- authorizeHttpRequests(... requestMatchers(...)) chỉ quyết định **quyền** cho request **đã được chain này chọn**.

Nếu custom filter được đăng ký ở Servlet container thì nó có thể chạy cho request nằm ngoài "/api/**", dù bên trong SecurityFilterChain filter chỉ được mong đợi chạy trên "/api/**". Đây là một hậu quả security quan trọng của double registration.

Ví dụ filter đọc JWT và ghi SecurityContext trước chain có thể chạy ở URL không có security matcher, tạo hành vi khó đoán. Đừng dựa vào một filter bên ngoài security chain để thực hiện authorization.

## 14. WebSecurityCustomizer, permitAll và bỏ qua security chain

Một lỗi sửa sai thường gặp là dùng WebSecurityCustomizer để ignore một URL:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/api/public/**");
}
~~~

Đoạn trên minh họa một lựa chọn **không nên dùng để chữa duplicate custom filter**. Ignoring có thể bỏ qua các cơ chế security như headers, CSRF hoặc các filter khác trên path phù hợp, không chỉ riêng custom filter đang bị trùng.

Khi cần endpoint công khai nhưng vẫn muốn đi qua Spring Security filters thông thường, ưu tiên:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

Các snippet này không phải cấu hình hoàn chỉnh độc lập. permitAll làm endpoint không đòi quyền truy cập trong rule tương ứng, **không** tắt security filter chain. Điều đó quan trọng để test custom security filter vẫn được gọi một lần trên endpoint công khai.

Đừng chọn cách bypass authorization để sửa lỗi lifecycle của filter.

## 15. Kiểm thử có thể phát hiện duplicate ở Servlet container

### 15.1. Vì sao unit test chưa đủ?

Gọi trực tiếp RequestAuditFilter.doFilter(...) một lần chỉ chứng minh code của nó chạy khi được gọi. Nó không nói Spring Boot có auto-register filter hay Spring Security có addFilterBefore filter hay không.

Để kiểm chứng hai registration paths, cần tạo **embedded servlet server thật**:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RegistrationIntegrationTest {
    // TestRestTemplate gọi qua network.
}
~~~

Test dự án phần 7 làm đúng điều đó. Một request HTTP tạo ra flow qua Servlet Filter chain và DelegatingFilterProxy, rồi controller. Nếu header đếm là 1 và wrapper disabled, đó là bằng chứng mạnh cho route đã test.

### 15.2. MockMvc có phát hiện được không?

MockMvc kiểm thử MVC mappings, security filter chains và exception behavior trong test context. Nhưng nó **không tạo một embedded Servlet container thật**, nên không phải bằng chứng chắc chắn về việc embedded Boot tự động đăng ký Filter Bean như thế nào trong production.

Vẫn nên dùng @AutoConfigureMockMvc + spring-security-test để kiểm tra authentication/authorization của filter, nhưng **thêm RANDOM_PORT test** nếu mục tiêu là phát hiện hai registrations ở Servlet container.

### 15.3. Test nhiều URL/method/dispatch

Một filter có thể đăng ký đúng một lần cho GET /api/hello nhưng không chạy hoặc chạy lặp với:

- /api/admin/** có SecurityFilterChain riêng.
- /actuator/** có filter registration/management port khác.
- /error hoặc ERROR dispatch.
- Async servlet request.
- POST request bị CSRF từ chối.
- Endpoint không khớp securityMatcher.
- Static resource URL.
- OPTIONS/CORS preflight.

Bộ regression test phải theo đúng URL pattern, dispatcher types và security policy đang triển khai. Không kết luận tất cả requests đều được xử lý giống GET /api/hello.

## 16. Đọc logs để xác minh registration và order

Spring Boot Servlet app có thể log filter registration order/URL patterns khi bật debug logging cho web group. Ví dụ cấu hình chỉ cho môi trường local hoặc test:

~~~yaml
logging:
  level:
    web: debug
    org.springframework.security: debug
~~~

Sau khởi động, kiểm tra log:

- Servlet container đăng ký filter nào, URL patterns và thứ tự.
- DelegatingFilterProxy/springSecurityFilterChain có bao nhiêu registration.
- FilterChainProxy chọn SecurityFilterChain nào cho URI.
- Danh sách Security filters trong chain phù hợp.
- Custom filter đang ở chain nào, vị trí trước/sau filter anchor nào.

Không cần log access token, request body, Authorization header hoặc raw cookies để debug routing. Trong production, security debug log có thể chứa thông tin định tuyến/ngữ cảnh nhạy cảm; chỉ bật có kiểm soát và kiểm tra mức độ ghi log.

**Chú ý:** Một log "Securing GET /..." từ FilterChainProxy không tự chứng minh custom filter chạy mấy lần. Kết hợp log registration với integration test và request-specific count mới có bằng chứng đầy đủ.

## 17. Checklist tìm nguồn của một filter

Khi thấy custom filter xuất hiện hai lần, rà soát theo các nhóm:

1. Class có @Component, @Service, @Configuration hoặc stereotype khác không?
2. Có @Bean trả về instance Filter này không?
3. Có @WebFilter và @ServletComponentScan không?
4. Có FilterRegistrationBean enabled=true hoặc registration thủ công không?
5. Có FilterRegistrationBean enabled=false trỏ vào **đúng** Filter Bean đang dùng không?
6. Có HttpSecurity.addFilterBefore/After/At không?
7. Có SecurityFilterChain thứ hai cũng thêm filter vào chain phù hợp không?
8. Có cấu hình auto đăng ký DelegatingFilterProxy thứ hai không?
9. Có library/starter bên ngoài tự cung cấp Filter bean tương tự không?
10. Có gateway/proxy hoặc forward tạo thêm HTTP request thật không?
11. Request có đi qua ERROR/ASYNC/FORWARD dispatch không?
12. Filter có OncePerRequestFilter marker riêng và hoạt động skip như thế nào?

Rà soát toàn bộ project và dependency theo mục tiêu thật thay vì chỉ đọc file định nghĩa filter. Những cùng class nhưng được tạo ở hai package/configuration khác nhau có thể gây double behavior dù mỗi nơi đều "đúng cú pháp".

## 18. Phân biệt filter cấp Servlet và HandlerInterceptor

Filter và HandlerInterceptor đều có thể dùng cho cross-cutting, nhưng thuộc các lớp khác nhau:

| Thành phần | Chạy ở đâu? | Có thay thế security chain không? |
| --- | --- | --- |
| Servlet Filter | Trước/ngoài DispatcherServlet, do Servlet container quản lý | Không |
| Spring Security Filter | Trong FilterChainProxy qua DelegatingFilterProxy | Là một phần của Spring Security |
| HandlerInterceptor | Spring MVC HandlerExecutionChain, trước/sau controller | Không |
| @ControllerAdvice | Xử lý exception/model tại web layer | Không |
| WebFilter | Spring WebFlux reactive web stack | Không phải Servlet Filter |
| SecurityWebFilterChain | Spring Security WebFlux | Không phải Servlet SecurityFilterChain |

Nếu mục tiêu chỉ là phân tích controller metrics hoặc thêm metadata theo handler, HandlerInterceptor có thể thích hợp. Nếu cần đọc HTTP request trước DispatcherServlet, Servlet Filter có phạm vi phù hợp. Nếu cần xác thực/phân quyền, nên dùng Spring Security mechanisms thay vì tự tạo một Interceptor rời rạc như lớp bảo vệ duy nhất.

Sử dụng HandlerInterceptor không tự giải quyết vấn đề auto-register của một Filter bean cũ còn nằm trong application context. Phải loại bỏ cấu hình không còn được dùng.

## 19. Vị trí filter so với SecurityContext

Một custom audit filter muốn biết Principal phải chạy sau phần authentication liên quan. Nhưng chain có nhiều mô hình: session, form login, HTTP Basic, bearer token, opaque token, custom authentication. Không có vị trí "sau toàn bộ authentication" hoàn toàn giống nhau cho mọi cấu hình.

Tài liệu Spring Security đưa ví dụ addFilterAfter(customFilter, AnonymousAuthenticationFilter.class) khi filter cần biết user đã được thiết lập trong chain; song vẫn phải hiểu role của từng filter và cơ chế authentication thực tế.

Một mô hình snippet:

~~~java
http.addFilterAfter(
        new TenantAccessFilter(accessService),
        AnonymousAuthenticationFilter.class);
~~~

TenantAccessFilter và accessService là dependency minh họa, không nằm trong project test. Filter kiểm soát tenant nên dựa trên SecurityContext đã xác thực và authorization đáng tin, **không** tin header X-Tenant-Id tự gửi để truy cập dữ liệu. Trong hệ thống thật, nên dùng AuthorizationManager hoặc policy có thiết kế chặt.

Nếu custom filter chạy một lần trong Servlet chain **ngoài** security chain, nó có thể không nhìn thấy SecurityContext đúng thời điểm và có thể chạy khi URL không được securityMatcher bao phủ. Đây là lý do sửa registration quan trọng hơn chỉ sửa log count.

## 20. Không tự thay thế các security filter mặc định khi không cần

Spring Security cung cấp DSL cho các tính năng HTTP Basic, form login, OAuth2 resource server, CSRF, CORS, logout, session management và exception handling. Khi cần behavior phổ biến, ưu tiên DSL thay vì copy code của filter nội bộ.

Ví dụ:

~~~java
http.httpBasic(Customizer.withDefaults());
~~~

Snippet trên cấu hình HTTP Basic qua DSL; cần import Customizer và một SecurityFilterChain hoàn chỉnh. Không vừa bật HTTP Basic vừa tự thêm một BasicAuthenticationFilter khác cùng vị trí chỉ vì muốn sửa thông điệp lỗi. Cấu hình đó có thể bị Spring Security từ chối hoặc gây conflict, tùy phiên bản.

Nếu muốn JWT bearer token, ưu tiên oauth2ResourceServer(...).jwt(...) khi phù hợp với hệ thống và cấu hình issuer/JWK/validation đúng; không tự parse JWT raw trong filter nếu thư viện/framework đã giải quyết bài toán.

**Sai mục tiêu:** Double registration của custom filter không phải lý do để tắt CSRF, authentication hoặc authorization. Hãy sửa đúng phần đăng ký custom filter.

## 21. Cấu hình khi filter chỉ áp dụng cho một SecurityFilterChain

Giả sử có API chain và web chain. Custom audit chỉ dành cho API:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(
        HttpSecurity http,
        RequestAuditFilter filter) throws Exception {

    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());
    http.addFilterBefore(filter, AuthorizationFilter.class);
    return http.build();
}
~~~

Một default chain khác có thể bảo vệ /ui/** theo chính sách riêng. Nếu filter là Bean, vẫn phải disable Servlet registration bằng FilterRegistrationBean cho cùng instance. Nếu không, filter sẽ còn chạy trên requests ngoài /api/** do được container map tới /*.

Đừng suy luận “đã đặt securityMatcher rồi thì Boot không tự đăng ký filter toàn cục”. Những cơ chế đó ở hai tầng độc lập.

### 21.1. Có thể tái dùng Filter bean trong hai chains không?

Có về mặt Java nếu chỉ một chain được chọn cho một request, nhưng phải cân nhắc:

- Filter có trạng thái mutable hoặc cache không an toàn khi chia sẻ nhiều requests/chains?
- Filter dùng config khác nhau cho API/admin/UI không?
- Filter có phụ thuộc order/exception handling khác nhau giữa chains?
- Vì sao không tạo hai filter với trách nhiệm rõ hơn nếu policy thực sự khác?

Không nhét global mutable request state vào Filter Bean singleton. Dữ liệu request phải đi qua request attributes, SecurityContext và các API được thiết kế cho lifecycle đó.

## 22. Một số lỗi gây hiểu nhầm khi dùng @Order

### 22.1. @Order trên Filter bean method không giống filter registration order

Spring Boot 3.3 docs ghi rõ có thể đặt @Order trên class Filter hoặc cho Filter implements Ordered; nếu không thể sửa class, dùng FilterRegistrationBean#setOrder để điều chỉnh Servlet registration. Không suy ra rằng thêm @Order vào **mọi @Bean method trả Filter** sẽ có hiệu quả ordering giống nhau.

Nếu filter là security-only và container registration đã bị disable, @Order của Servlet filter cũng không phải vị trí trong SecurityFilterChain. Vị trí trong security chain do HttpSecurity.addFilterBefore/After/At quyết định.

### 22.2. @Order trên SecurityFilterChain Bean

@Order(1) ở SecurityFilterChain bean làm chain đó được xét trước những chain khác. Nó không tự chuyển custom filter vào đầu security chain hoặc ngăn container auto-registration.

### 22.3. @Order trên cấu hình class

Một @Configuration class có @Order không tự định nghĩa mọi thứ tự trong các component bên trong. Khi cần xác minh, xem lớp sở hữu order thực tế: Servlet registration, chain matching hay security filter position.

## 23. Khi Filter Bean được tạo rất sớm

Spring Boot cảnh báo Filter beans có thể được khởi tạo sớm trong application lifecycle. Nếu một Filter Bean phụ thuộc quá nặng vào DataSource/JPA/business service hoặc Bean chưa sẵn sàng, có thể xuất hiện vòng phụ thuộc, bất ngờ eager initialization hoặc chi phí startup.

Các hướng xử lý:

- Tách filter khỏi repository blocking nếu có thể.
- Tránh gọi database bên trong mọi HTTP request chỉ để audit đơn giản.
- Đặt dependency nhẹ vào constructor, tách asynchronous processing khi phù hợp.
- Dùng filter factory/registration có lifecycle rõ hoặc DelegatingFilterProxy cho trường hợp thực sự cần delegation.
- Cân nhắc event listener/observability integration để giảm trách nhiệm filter.
- Không tự thêm filter registration thứ hai như một workaround cho vấn đề lifecycle.

Bật disabled FilterRegistrationBean xử lý **đăng ký** filter chứ không tự biến một bean phụ thuộc nặng thành nhẹ. Việc bean được tạo lúc nào là vấn đề khác cần thiết kế.

## 24. Async, ERROR dispatch và việc filter "chạy nhiều lần"

Một servlet request không nhất thiết là một invocation doFilter duy nhất. Async processing, error dispatch và các forwards có thể dẫn tới thêm filter chain invocation hợp lệ.

Các biến cần phân biệt:

- **HTTP request count:** số request từ client.
- **Servlet dispatch count:** REQUEST, ERROR, ASYNC, FORWARD, ...
- **Registration paths:** filter container và security chain.
- **Filter doFilter calls:** thực tế filter được gọi bao nhiêu lần.
- **doFilterInternal calls:** với OncePerRequestFilter có thể ít hơn doFilter calls vì guard.

Nếu đang điều tra duplicate, ghi metrics với method, route template, dispatcher type, request identity (không phải secret/raw ID) và filter registration owner; tránh chỉ nhìn tổng số doFilterInternal.

Ví dụ FilterRegistrationBean chỉ map REQUEST nhưng filter trong SecurityFilterChain có thể được Spring Security gọi ở những dispatcher types mà proxy đang xử lý. Mỗi layer có config dispatcher riêng; cần hiểu version default và test trên Servlet container thật.

Đừng dùng synchronized/static boolean để ép filter chạy một lần toàn hệ thống: nó gây race condition và có thể chặn tất cả requests sau request đầu tiên.

## 25. CORS preflight và filter registration

OPTIONS preflight từ browser là **một HTTP request riêng**, không phải việc filter chạy hai lần trên cùng request. Một GET thực tế có thể được browser gửi sau OPTIONS, nên thấy hai dòng log ở client interaction không tự chứng minh duplicate registration.

Khi sử dụng Spring Security:

- CORS nên được xử lý phù hợp trước những kiểm tra authentication có thể chặn preflight.
- Dùng http.cors(...) và CorsConfigurationSource/WebMvcCorsConfiguration theo hướng dẫn Spring Security/Boot, không tự viết filter cho mọi header.
- Không disable toàn bộ security chỉ vì preflight trả 401/403.
- Dùng request-specific test để xác định custom filter chạy mấy lần ở mỗi HTTP request.

Với custom filter chỉ áp dụng API, phân biệt OPTIONS preflight có vào SecurityFilterChain hay không với securityMatcher; nếu Filter Bean vẫn auto-register ở Servlet container, nó có thể được gọi cả khi chain không match.

## 26. Logging, audit và idempotency khi filter gây side effects

Một filter được đăng ký hai lần có thể đặc biệt nguy hiểm khi nó có side effect:

- Ghi event vào Kafka hai lần.
- Tăng counter tiêu thụ quota hai lần.
- Gửi billing/audit event lặp.
- Ký hoặc sửa response header nhiều lần.
- Tạo lại request ID giữa pipeline.
- Gọi API remote để xác thực nhiều lần, tăng latency và chi phí.
- Làm mất body nếu tự đọc request stream mà không có wrapper an toàn.

**Điều quan trọng:** Cấu hình filter đúng một nơi là lớp phòng vệ đầu tiên. Nhưng side effects quan trọng vẫn nên idempotent theo request/business ID vì retry, timeout, redirect hoặc nhiều HTTP requests thật có thể xảy ra độc lập với duplicate registration.

Đừng log Authorization header, access token, cookie session hoặc raw request body trong filter để chứng minh nó đã chạy. Dùng marker không nhạy cảm, structured logs và tracing được thiết kế an toàn.

## 27. Checklist trước khi đưa filter vào production

- [ ] Filter có một owner rõ: Servlet container hoặc SecurityFilterChain.
- [ ] Nếu Filter Bean chỉ dùng trong Security: có FilterRegistrationBean cho cùng instance và enabled=false.
- [ ] Không tồn tại @Component + @Bean tạo hai instance vô tình.
- [ ] Không có @WebFilter/@ServletComponentScan registration thứ hai cho cùng logic.
- [ ] Không tự tạo DelegatingFilterProxy springSecurityFilterChain trùng.
- [ ] SecurityFilterChain matching có fallback và không để endpoints nhạy cảm hở.
- [ ] Không dùng web.ignoring để chữa filter double registration.
- [ ] HttpSecurity.addFilterBefore/After có lý do rõ theo authentication/authorization order.
- [ ] Servlet registration order không bị nhầm với security filter order.
- [ ] Với OncePerRequestFilter, hiểu async/error dispatch và request attributes.
- [ ] Có integration test RANDOM_PORT chứng minh mỗi HTTP request đi qua đúng đường.
- [ ] Test trên ít nhất URL public, URL protected, 401/403, OPTIONS, ERROR/ASYNC nếu dùng.
- [ ] Có regression test authentication/authorization, không chỉ X-Audit-Filter-Calls.
- [ ] Không xuất raw secrets vào response, access logs hoặc metrics labels.
- [ ] Không gọi blocking I/O dài trong filter khi không có deadline/concurrency control.
- [ ] Có quan sát filter registration logs và test cụ thể trước/sau thay đổi.
- [ ] Có phương án rollback nếu behavior request bị thay đổi khi deploy.

## 28. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Custom filter được gọi hai lần | @Component/@Bean auto-register + addFilterBefore | Tắt container registration hoặc không làm Filter Bean |
| doFilterInternal log một lần nhưng vẫn thấy duplicate | OncePerRequestFilter guard che lần vào thứ hai | Kiểm tra registration, dùng test GenericFilterBean lab |
| Chỉnh @Order mà filter vẫn lặp | Thứ tự không xóa registration | Dùng FilterRegistrationBean.setEnabled(false) |
| Disable registration nhưng filter không còn chạy | Filter không được thêm vào matching SecurityFilterChain | Kiểm tra addFilter... và securityMatcher |
| Filter chạy ở đường dẫn không thuộc API | Container auto-register với /* | Tắt container registration cho security-only bean |
| Filter không có authenticated user | Chạy ở Servlet layer hoặc security order quá sớm | Chọn vị trí sau authentication phù hợp |
| Có hai Filter beans cùng class | @Component và @Bean cùng tồn tại | Chỉ tạo một instance rõ ràng |
| Thêm FilterRegistrationBean disable không hiệu quả | Bean chỉ tới object mới, không phải Filter Bean dùng thực tế | Inject cùng instance vào constructor |
| Multiple SecurityFilterChains nhưng trông như cả hai chạy | Container filter bên ngoài chain hoặc duplicate Security proxy | Kiểm tra first match và registrations |
| Request OPTION làm log 2 lần | Preflight + request thật | Đếm theo từng HTTP request, không theo click |
| Test MockMvc pass nhưng staging filter lặp | MockMvc không mô phỏng container registration đầy đủ | Test RANDOM_PORT và production-like container |
| Filter chạy lại khi server gửi lỗi | ERROR dispatcher type | Kiểm tra dispatcher types, request attributes |
| API protected chuyển 403/401 không như mong đợi | Bỏ qua security hoặc đổi chain order | Giữ security matcher và fallback, test auth |
| Custom authentication filter xung đột built-in | Tự thêm cùng chức năng với DSL | Dùng DSL chuẩn hoặc cấu hình filter thay thế |
| Filter bị tạo quá sớm | Servlet Filter bean lifecycle init | Giảm phụ thuộc, cân nhắc delegation/lazy strategy |
| Log token xuất hiện hai lần | Filter logging double hoặc request thực sự lặp | Ngừng log secret, sửa registration, kiểm tra request IDs |

## 29. Bài tập thực hành và bài kiểm chứng

### Bài 1 — Làm xuất hiện double invocation

Chạy project mẫu, ghi X-Audit-Filter-Calls=1. Ở một branch thử nghiệm riêng, bỏ disabled FilterRegistrationBean, giữ requestAuditFilter Bean và addFilterBefore; chạy GET /api/hello. Quan sát filter count/log và lý giải đường đi. Khôi phục cấu hình đúng trước khi kết thúc.

### Bài 2 — Filter không là Bean

Xóa requestAuditFilter() và disableContainerAudit(), thay tham số filter trong SecurityConfiguration bằng new RequestAuditFilter() tạo một instance trong SecurityFilterChain bean. Chạy HTTP tests, xác nhận X-Audit-Filter-Calls=1.

### Bài 3 — Scope của securityMatcher

Tạo một API SecurityFilterChain với securityMatcher("/api/**"), một fallback SecurityFilterChain cho URI khác và một security-only filter chỉ nằm ở API chain. Kiểm tra filter không chạy trên /public nếu không thuộc API chain; xác minh URL đó vẫn được fallback bảo vệ theo chính sách.

### Bài 4 — Servlet-only filter

Tạo một CorrelationFilter chỉ nằm ở FilterRegistrationBean(enabled=true), addUrlPatterns("/api/*"), không thêm vào HttpSecurity. Kiểm tra filter chạy ở URL cần thiết và không chạy ở URL khác. So sánh mức độ truy cập SecurityContext.

### Bài 5 — OncePerRequestFilter

Chuyển RequestAuditFilter sang OncePerRequestFilter, test doFilterInternal và filter registration riêng. Thử ERROR/ASYNC dispatch (nếu app sử dụng) và mô tả khi nào once-per-dispatch khác once-per-logical-request.

### Bài 6 — Security regression

Thêm security-test/MVC tests cho anonymous user, authenticated user và admin role theo thiết kế; xác minh rằng sửa filter registration không vô tình bỏ bảo vệ bất kỳ endpoint nào.

### Bài 7 — Audit side effects

Thay count header bằng một fake event publisher trong test (không gọi external service thật), xác minh một HTTP request không tạo hai event do duplicate registration. Đồng thời thiết kế event idempotency để chịu được retry HTTP thật.

### Bài 8 — So sánh WebFlux

Tạo một app WebFlux thuần với WebFilter/SecurityWebFilterChain và Reactor Netty, xác định vì sao Servlet FilterRegistrationBean không phải cơ chế tương ứng. Đừng đưa code Servlet Filter của bài này vào reactive stack rồi kỳ vọng nó chạy giống Spring MVC.

**Bằng chứng đạt:** source code, Gradle test output, HTTP headers, startup log đã loại secrets, bảng phân loại registration owners và một kết luận dựa trên request traces thực tế. Không tuyên bố benchmark/test PASS nếu chưa chạy trong môi trường tương ứng.

## 30. Câu hỏi tự đánh giá

1. Servlet Filter chain và SecurityFilterChain khác nhau ở chỗ nào?
2. DelegatingFilterProxy và FilterChainProxy đóng vai trò gì?
3. Vì sao @Component trên Filter có thể khiến Boot auto-register filter?
4. Điều gì xảy ra khi cùng Filter Bean được addFilterBefore trong HttpSecurity?
5. Một object Filter có thể có hai registration không?
6. Vì sao OncePerRequestFilter không phải cách sửa cấu hình trùng?
7. FilterRegistrationBean.setEnabled(false) vô hiệu hóa tầng nào?
8. Vì sao disabled FilterRegistrationBean phải chứa đúng Filter Bean?
9. Khi nào nên dùng new MyFilter(...) thay vì @Bean?
10. Nếu filter chỉ dành API, securityMatcher có giới hạn được Servlet auto-registration không?
11. @Order trên SecurityFilterChain khác FilterRegistrationBean#setOrder ra sao?
12. HttpSecurity.addFilterBefore/After khác @Order như thế nào?
13. Nhiều SecurityFilterChain có tự khiến request đi qua cả hai không?
14. Nếu một request không match chain nào thì rủi ro gì?
15. Vì sao không dùng web.ignoring hoặc tắt Spring Security để chữa duplicate?
16. Vì sao MockMvc một mình chưa đủ chứng minh filter không auto-register?
17. Khi nào thấy hai lần doFilter vẫn là behavior hợp lệ vì async/error dispatch?
18. OPTIONS preflight có phải là duplicate registration không?
19. Một security audit filter cần Principal nên được đặt ở vị trí nào?
20. Vì sao nên dùng DSL built-in thay vì tự thêm BasicAuthenticationFilter thứ hai?
21. Nếu filter làm side effects, tại sao còn cần idempotency dù đã sửa registration?
22. Làm sao chứng minh chính xác filter chỉ chạy một lần bằng integration test?

## 31. Tài liệu tham khảo chính thức

- [Spring Security — Architecture (Servlet)](https://docs.spring.io/spring-security/reference/servlet/architecture.html): DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, filter ordering và cảnh báo Filter Bean có thể bị chạy hai lần.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): nhiều SecurityFilterChain, @Order, securityMatcher và requestMatchers.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): auto-registration Servlet/Filter beans, order và Servlet context.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): cách disable registration bằng FilterRegistrationBean.enabled=false.
- [Spring Framework — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): already-filtered attribute, async/error dispatch và doFilterInternal.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): kiểm thử security behavior.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): integration test RANDOM_PORT và TestRestTemplate.

**Kết luận:** để tránh custom Servlet Filter chạy hai lần, hãy quyết định nó thuộc **Servlet container** hay **Spring Security**. Với security-only Filter Bean, dùng FilterRegistrationBean cho **cùng Bean** và đặt enabled=false; hoặc không tạo Filter Bean, chỉ tạo instance trong HttpSecurity. OncePerRequestFilter, @Order và securityMatcher có vai trò riêng nhưng không thay thế việc sửa double registration. Chứng minh kết quả bằng một HTTP integration test chạy container thật và regression tests cho authentication/authorization.
