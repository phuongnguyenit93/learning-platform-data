# javax.servlet và jakarta.servlet trong quá trình nâng cấp nền tảng

## 1. Vấn đề và mục tiêu

Khi nâng một ứng dụng từ **Spring Boot 2.x / Spring Framework 5.x / Spring Security 5.x** lên **Spring Boot 3.x / Spring Framework 6.x / Spring Security 6.x**, mã xử lý HTTP Servlet thường phải chuyển từ **javax.servlet** sang **jakarta.servlet**.

~~~java
// Trước nâng cấp (Java EE / Spring Boot 2.x):
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// Sau nâng cấp (Jakarta EE / Spring Boot 3.x):
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
~~~

Đây **không chỉ là đổi tên import**. JVM coi **javax.servlet.Filter** và **jakarta.servlet.Filter** là hai kiểu độc lập. Class đã biên dịch cho interface cũ không tự tương thích với interface mới. Nếu dự án hoặc thư viện phụ thuộc vẫn dựa vào Servlet API cũ, có thể gặp:

- Lỗi compile **package javax.servlet does not exist**, **method does not override or implement a method from a supertype**, hoặc không tìm được ServletException.
- Lỗi runtime **NoClassDefFoundError: javax/servlet/Filter**, **ClassNotFoundException**, **LinkageError**, **ClassCastException**, **NoSuchMethodError** do binary không đồng bộ.
- Custom **Filter/Servlet/Listener** không được đăng ký, bị gọi sai thời điểm hoặc thiếu Authentication trong request.
- WAR chạy được trên Tomcat đời cũ nhưng không khởi động trên container mới, hoặc ngược lại.
- HTTP test **401/403/302** thay đổi sau nâng cấp do **cấu hình Spring Security 6** chứ không trực tiếp do javax/jakarta.

Bài học giúp bạn hiểu bản chất namespace migration, lựa chọn đúng Servlet container và dependency, chuyển custom Security filter, viết một ví dụ Java 17 có thể xây dựng và kiểm thử, chẩn đoán lỗi, đồng thời giữ nguyên các kiểm soát bảo mật trong quá trình nâng cấp.

**Phạm vi:** Spring Security **Servlet stack**, không phải WebFlux. Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x**. Các phiên bản chính xác trong project thực tế phải tương thích với nhau.

## 2. Vì sao lại có javax.servlet và jakarta.servlet?

### 2.1. Từ Java EE tới Jakarta EE

Các đặc tả enterprise Java trước đây sử dụng namespace **javax.servlet**. Sau khi hệ sinh thái Java EE chuyển sang Jakarta EE, nhiều enterprise APIs đổi package sang **jakarta.***. Servlet API là một trong những thành phần phải chuyển đổi khi dùng Spring Framework 6.

| Stack minh họa | Servlet API/namespace | Container tiêu biểu |
| --- | --- | --- |
| Spring Boot 2.x, Framework 5.x, Security 5.x | **javax.servlet**, Servlet 4.0 | **Tomcat 9** |
| Jakarta EE 9, Servlet 5.0 | **jakarta.servlet** | **Tomcat 10.0** |
| Spring Boot 3.x, Framework 6.x, Security 6.x | **jakarta.servlet**, Servlet 6.0 | **Tomcat 10.1** |

Đây là bảng về **tổ hợp nền tảng phổ biến**, không phải bảng khẳng định mọi ứng dụng Java sử dụng đúng một container. Spring Boot 3 cần **Java 17+** và nền tảng Jakarta phù hợp; nâng source code lên Jakarta nhưng runtime vẫn là Java 11 hoặc external Tomcat 9 không tạo ra hệ thống tương thích.

### 2.2. Hai kiểu Java không thay thế được nhau

~~~text
javax.servlet.Filter         != jakarta.servlet.Filter
javax.servlet.Servlet        != jakarta.servlet.Servlet
javax.servlet.FilterChain    != jakarta.servlet.FilterChain
javax.servlet.ServletRequest != jakarta.servlet.ServletRequest

LegacyFilter implements javax.servlet.Filter
→ KHÔNG phải implementation của jakarta.servlet.Filter
~~~

Tên package là một phần của **binary class name** lưu trong bytecode. Một JAR bên thứ ba còn tham chiếu **javax/servlet/Filter** vẫn phụ thuộc vào API cũ ngay cả khi project chính đã thay mọi import thành jakarta.servlet.

Do đó cần nâng **toàn bộ phần mềm chạy trong cùng web application class loader** đến phiên bản hỗ trợ Jakarta, đặc biệt các library tạo Filter, ServletContextListener, servlet initializer, JSP/JSTL, SSO adapter và test support.

### 2.3. Không đổi mọi package javax.* một cách mù quáng

| Kiểu trước đây | Việc nên làm khi migrate |
| --- | --- |
| javax.servlet.Filter | **jakarta.servlet.Filter** |
| javax.servlet.FilterChain | **jakarta.servlet.FilterChain** |
| javax.servlet.ServletException | **jakarta.servlet.ServletException** |
| javax.servlet.http.HttpServletRequest / Response | **jakarta.servlet.http.HttpServletRequest / Response** |
| javax.servlet.annotation.WebFilter | **jakarta.servlet.annotation.WebFilter** |
| javax.servlet.jsp.* | **jakarta.servlet.jsp.*** nếu dự án dùng JSP |
| javax.validation.Valid | **jakarta.validation.Valid** |
| javax.persistence.Entity | **jakarta.persistence.Entity** |
| javax.annotation.PostConstruct | **jakarta.annotation.PostConstruct** khi dùng Jakarta annotation |
| javax.ws.rs.* | API Jakarta REST phù hợp nếu dự án dùng JAX-RS |
| javax.net.ssl.* | **Giữ nguyên**, Java SE TLS |
| javax.crypto.* | **Giữ nguyên**, Java SE cryptography |
| javax.sql.* | **Giữ nguyên**, Java SE SQL |
| javax.xml.parsers.* | **Giữ nguyên**, Java SE XML |

Không chạy tìm-thay toàn bộ **javax. → jakarta.**. Một số API Java SE vẫn có tên javax và hoàn toàn chính xác trên Java 17. Hãy migrate từng hệ API theo dependency/version.

## 3. Các vị trí liên quan Spring Security Servlet cần kiểm tra

Ứng dụng có thể không có bất kỳ import javax.servlet nào ở controller nhưng vẫn cần migration vì Spring Security Servlet được triển khai trên **Servlet Filter API**.

Một số thành phần tiêu biểu:

- **FilterChainProxy** điều phối **SecurityFilterChain**.
- **DelegatingFilterProxy** kết nối filter registration của servlet container với bean filter do Spring quản lý.
- **OncePerRequestFilter** là base class thường dùng cho custom authentication/audit/request wrapper filters.
- **AuthenticationEntryPoint / AccessDeniedHandler** có method nhận Servlet request/response để gửi phản hồi 401/403 hoặc redirect.
- **RequestCache, SecurityContextRepository, LogoutHandler, SessionAuthenticationStrategy, HttpSession** làm việc với Servlet request hoặc session.
- **HttpFirewall / StrictHttpFirewall** nhận servlet request, phân tích và từ chối các đường dẫn không chuẩn.
- **FilterRegistrationBean, ServletContextInitializer, @WebFilter, @WebListener** và **web.xml** là điểm giao với servlet container.
- Custom **CsrfTokenRepository**, custom authentication filters và SSO/OIDC adapters có thể chứa Servlet API trong chữ ký public method.

Trong một project lớn, rà soát cả modules chứa test fixture, filter framework, internal authentication SDK, tracing libraries, servlet initializer và tích hợp bên thứ ba.

### 3.1. OncePerRequestFilter đổi chữ ký thế nào?

Một đoạn kiểu Boot 2 / Spring 5 (chỉ minh họa, không dùng với Boot 3):

~~~java
// Bên trong subclass của OncePerRequestFilter cũ:
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {
    chain.doFilter(request, response);
}
~~~

Trên Boot 3 / Spring 6:

~~~java
// Bên trong subclass của OncePerRequestFilter mới:
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {
    chain.doFilter(request, response);
}
~~~

Hai đoạn trên là **snippet** nằm trong class có import **java.io.IOException**, không phải source file độc lập. Nếu superclass đòi jakarta.servlet.FilterChain còn subclass khai báo javax.servlet.FilterChain, chữ ký không còn khớp và **@Override** thường báo lỗi. **Không** chữa bằng cách xóa @Override; hãy sửa đúng import và kiểm tra method được framework gọi thực sự.

### 3.2. Thêm javax.servlet-api không phải biện pháp migration

Thấy lỗi compile rồi thêm:

~~~groovy
// Cách làm sai trong một ứng dụng Boot 3 Jakarta:
implementation 'javax.servlet:javax.servlet-api:4.0.1'
~~~

có thể làm một source cũ compile được ở một số nơi, nhưng **không** làm interface javax.servlet.Filter trở thành jakarta.servlet.Filter. Runtime có thể phải mang đồng thời hai loại class, dẫn tới xung đột.

Giải pháp là **nâng/biên dịch lại thư viện** để dùng Jakarta API và để Spring Boot dependency management giữ stack đồng bộ. Với Boot web thông dụng, starter-web/embedded container cung cấp Servlet APIs cần thiết; không tự thêm nhiều servlet-api JAR tùy ý.

## 4. Kế hoạch nâng cấp nhiều lớp

### 4.1. Lập baseline

Trước khi thay code, ghi nhận:

1. JDK tại **developer machine, CI, Docker image, production runtime**; Spring Boot 3 yêu cầu Java 17+.
2. Phiên bản **Spring Boot, Spring Framework, Spring Security** thực tế được resolve, không chỉ version mong muốn trong file build.
3. Cách đóng gói **executable JAR/embedded Tomcat** hay **WAR/external servlet container**.
4. Mọi custom **Filter, listener, servlet, authentication entry point, request wrapper**.
5. Các thư viện liên quan **JSP/JSTL, OAuth2/OIDC adapters, OpenAPI, tracing/observability, Spring Session, internal SDK**.
6. Các rule Spring Security quan trọng: public/private routes, 401/403/302, CSRF, CORS, session fixation, remember-me, request matchers.
7. Các integration tests và cách rollback artifact/container.

Nếu không có baseline, dễ quy nhầm một lỗi **403 do CSRF hoặc matcher** thành lỗi Jakarta, hoặc một **NoClassDefFoundError** thành lỗi filter logic.

### 4.2. Lộ trình mẫu

~~~text
Boot 2.x / Security 5.x / javax.servlet
     │
     ├─ Cố định baseline và regression tests
     │
     ├─ Có thể chuẩn bị API migration trên Boot 2.7/Security 5.8
     │  (nếu dependency compatibility cho phép)
     │
     ├─ Nâng JDK, Gradle/Maven và CI lên Java 17+
     │
     ├─ Chọn các thư viện có phiên bản Jakarta compatible
     │
     ├─ Nâng lên Boot 3 / Framework 6 / Security 6
     │
     ├─ Thay đúng các enterprise API namespaces
     │
     ├─ Chuyển SecurityFilterChain và security matchers
     │
     ├─ Test Servlet filters, authentication/authorization
     │
     ├─ Test embedded/external container và proxy thực
     │
     └─ Release có giám sát, fallback và rollback đồng bộ
~~~

Đây là **lộ trình gợi ý**, không phải bắt buộc phải đi qua mọi phiên bản trung gian. Với library không còn được maintain nhưng vẫn phụ thuộc javax.servlet, ưu tiên thay thế hoặc nâng version; không giấu rủi ro bằng cách trộn cả hai namespace.

## 5. Ví dụ hoàn chỉnh Spring Boot 3.x / Security 6.x / Java 17+

Ví dụ cho thấy một custom **OncePerRequestFilter** dùng Jakarta Servlet API trong một **SecurityFilterChain** thực sự, cộng hai HTTP endpoints và bốn bài kiểm thử.

Các file:

~~~text
jakarta-migration-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat (Gradle wrapper của project)
└── src/
    ├── main/java/com/example/migration/MigrationApplication.java
    └── test/java/com/example/migration/MigrationApplicationTest.java
~~~

### 5.1. Build file

**settings.gradle**:

~~~groovy
rootProject.name = 'jakarta-migration-demo'
~~~

**build.gradle** (version ghim cho ví dụ có thể tái lập; trong triển khai thật hãy chọn bản vá được hỗ trợ phù hợp với hệ thống):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

Version của Boot và dependency-management plugin trong ví dụ là **một bộ minh họa**, không phải yêu cầu dùng đúng version này ở production. Có thể dùng bản patch mới hơn trong nhánh còn được support, sau khi kiểm thử tương thích. Không thêm javax.servlet-api.

### 5.2. Application, SecurityFilterChain, filter và controller

Tệp **src/main/java/com/example/migration/MigrationApplication.java**:

~~~java
package com.example.migration;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class MigrationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MigrationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/private/whoami").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                // Filter đặt ở Spring Security chain.
                // Không đồng thời đăng ký nó làm Servlet bean.
                .addFilterBefore(
                        new RequestMarkerFilter(),
                        BasicAuthenticationFilter.class)
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // Tài khoản demo local, không đưa vào production.
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("test-password"))
                        .roles("USER")
                        .build());
    }
}

final class RequestMarkerFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-Servlet-API", "jakarta.servlet");
        chain.doFilter(request, response);
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/private/whoami")
    public String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

**Vì sao ví dụ dùng new RequestMarkerFilter()?** Đây là filter đơn giản **không được khai báo @Bean/@Component**. Nó chỉ được đăng ký trong **Spring Security filter chain**. Nếu một Filter đồng thời là Spring bean và cũng được đưa vào SecurityFilterChain, Boot có thể tự đăng ký nó ở tầng servlet container, dẫn tới gọi hai lần hoặc thứ tự không mong muốn.

**Không dùng code này làm authorization policy cho dự án thật:** các rule ở đây chỉ để minh họa HTTP Basic. Với API Bearer/OIDC và các thao tác POST/PUT/DELETE, cần thiết kế phân quyền đối tượng, CSRF/CORS và bảo vệ session/token riêng.

### 5.3. Chạy thử từ terminal

Dự án cần có Gradle wrapper. Chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Thử endpoint public:

~~~bash
curl -i 'http://localhost:8080/public/ping'
~~~

**Dự kiến:** HTTP 200, body **pong**, và header:

~~~http
X-Servlet-API: jakarta.servlet
~~~

Thử private endpoint không credentials:

~~~bash
curl -i 'http://localhost:8080/private/whoami'
~~~

**Dự kiến:** HTTP 401 (HTTP Basic entry point). Thử tiếp với user demo:

~~~bash
curl -i -u demo:test-password \
  'http://localhost:8080/private/whoami'
~~~

**Dự kiến:** HTTP 200 và body:

~~~text
demo
~~~

Đây là output dự kiến từ cấu hình minh họa, không phải stdout đã chạy trong môi trường thực. Không dùng credential demo để chạy dịch vụ công khai; khi kiểm tra endpoint thật phải dùng TLS.

## 6. Bốn bài kiểm thử MockMvc cho Jakarta migration

Tệp **src/test/java/com/example/migration/MigrationApplicationTest.java**:

~~~java
package com.example.migration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MigrationApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void customFilterImplementsJakartaServletApi() {
        assertThat(jakarta.servlet.Filter.class
                .isAssignableFrom(RequestMarkerFilter.class))
                .isTrue();
    }

    @Test
    void publicRequestPassesThroughJakartaFilter()
            throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"))
                .andExpect(header().string(
                        "X-Servlet-API", "jakarta.servlet"));
    }

    @Test
    void privateRequestWithoutAuthIs401()
            throws Exception {
        mvc.perform(get("/private/whoami"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthWorksAfterMigration()
            throws Exception {
        mvc.perform(get("/private/whoami")
                        .with(httpBasic("demo", "test-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("demo"))
                .andExpect(header().string(
                        "X-Servlet-API", "jakarta.servlet"));
    }
}
~~~

Chạy:

~~~bash
./gradlew clean test --tests com.example.migration.MigrationApplicationTest
~~~

Windows:

~~~powershell
.\gradlew.bat clean test --tests com.example.migration.MigrationApplicationTest
~~~

**Kỳ vọng:** 4 bài test đạt trong một project Spring Boot 3.x hợp lệ. Test kiểm tra Filter thực sự implement **jakarta.servlet.Filter**, 200 cho public, 401 khi thiếu authentication và 200 khi Basic credentials đúng. Đây là **kiểm tra tĩnh dự kiến**, chưa phải log thực thi được xác nhận.

### Giới hạn của MockMvc

MockMvc kiểm tra request qua Spring Test context và SecurityFilterChain khi filter được đăng ký đúng, nhưng **không tái hiện hoàn toàn** external Tomcat WAR classloading, JSP compilation, ServletContainerInitializer của third-party library, WAF/proxy rewrites hoặc TLS termination. Sau test, cần chạy ứng dụng thật qua container HTTP và nếu phát hành WAR thì kiểm thử trên đúng external servlet container.

## 7. Phân tích dependency: tìm JAR còn tham chiếu javax.servlet

Không chỉ tìm import trong src/main; thư viện cũ có thể chứa bytecode tham chiếu package javax và chỉ được load khi request đụng tới một code path cụ thể.

### 7.1. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath \
  --dependency javax.servlet-api
./gradlew dependencyInsight --configuration testRuntimeClasspath \
  --dependency javax.servlet-api
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency javax.servlet-api
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency javax.servlet-api
~~~

**Lưu ý:** kết quả không có artifact **javax.servlet-api** chỉ chứng minh dependency graph đó không khai báo artifact khớp tên truy vấn. Nó **không chứng minh mọi JAR khác đã được biên dịch với jakarta.servlet**. Hãy rà cả thư viện nội bộ, SSO adapter, tracing agent, servlet filters, JSP/JSTL và custom test fixtures.

### 7.2. Maven

Nếu sử dụng Maven wrapper:

~~~bash
./mvnw dependency:tree -Dincludes=javax.servlet:javax.servlet-api
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

Trong PowerShell:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=javax.servlet:javax.servlet-api
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.security
~~~

Chọn đúng build tool của dự án; không cần có cả Gradle và Maven.

### 7.3. Tìm source, class signature và bytecode

Các chuỗi cần tìm trong Java source, tests, XML và config:

~~~text
import javax.servlet.
javax.servlet.Filter
javax.servlet.http.
javax.servlet.annotation.
javax.servlet.jsp.
~~~

Nếu source đã sạch nhưng runtime vẫn báo **NoClassDefFoundError: javax/servlet/Filter**, cần điều tra JAR:

- **jdeps** để kiểm tra class dependency của JAR có classpath phù hợp. Nó không luôn phát hiện việc load qua reflection hoặc chuỗi văn bản.
- **jar tf** để xem nội dung JAR.
- **javap -verbose** để tìm class names trong binary signature/constant pool.
- SBOM/dependency reports để xác định version và transitive dependency.
- Rebuild **internal SDK/filter JAR** với Jakarta dependency, cập nhật test fixture và phát hành version tương thích.

Không tùy tiện inject javax.servlet classes vào runtime Boot 3 vì “có thể cần để JAR cũ chạy”; điều đó có thể làm vấn đề khó phát hiện hơn mà không đảm bảo compatibility.

## 8. Embedded container và external WAR

### 8.1. Executable JAR

Khi Spring Boot 3 dùng **spring-boot-starter-web** với embedded Tomcat mặc định, dependency management chọn các artifact tương thích Jakarta. Nếu dự án override phiên bản Spring/Tomcat/Jakarta API một cách độc lập, cần kiểm tra thực tế classpath, nhất là sau khi nâng Gradle hoặc cập nhật platform BOM.

**Không** đưa Tomcat 9 trở lại một Boot 3 Servlet project để giữ binary cũ: Tomcat 9 dùng javax.servlet, không đáp ứng Servlet 6.0/Jakarta API theo nền Boot 3.

### 8.2. WAR trên container ngoài

Nếu deploy WAR lên **Tomcat 9**, Servlet classes sẽ thuộc namespace **javax.servlet**. Một ứng dụng Boot 3/Security 6 dùng **jakarta.servlet** không thể chạy nguyên trạng chỉ nhờ sửa một vài import. Hãy sử dụng container hỗ trợ Jakarta, ví dụ **Tomcat 10.1 (Servlet 6.0)**, và kiểm tra compatibility của toàn bộ ứng dụng.

Với Spring Boot WAR, thường cần:

- Gradle **war plugin** hoặc Maven WAR packaging thích hợp.
- Container dependency có scope **providedRuntime/provided** khi external container cung cấp nó.
- **SpringBootServletInitializer** được cấu hình để bootstrap web application theo mô hình Boot.
- Rà lại **@WebFilter**, **@WebListener**, **ServletContextInitializer**, **web.xml**, session persistence, JSP/JSTL.
- Chạy smoke test trong **container đích**, không chỉ unit test.

Không phải ứng dụng Boot **executable JAR** nào cũng cần web.xml hoặc Servlet initializer. Đó là lựa chọn của WAR/traditional deployment.

### 8.3. Descriptor web.xml

Các ứng dụng servlet truyền thống dùng **WEB-INF/web.xml** nên cập nhật namespace/schema nếu triển khai theo Servlet 6.0. Skeleton ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
    <display-name>Jakarta Migration Demo</display-name>
</web-app>
~~~

Đoạn này chỉ minh họa **web.xml skeleton**, chưa đăng ký servlet hay filter. Một web app chạy embedded Boot như mục 5 không cần web.xml.

### 8.4. JSP/JSTL và các tài nguyên ngoài Java

Một JSP/JSTL project có thể compile controller nhưng fail khi render view vì taglib hoặc JSP engine cũ. Cần phiên bản Jakarta-compatible cho JSP/Tags APIs, container hỗ trợ, đúng taglib URI và đúng packaging. Kiểm tra đặc biệt các trang login, error, CSRF forms và output encoding.

Các công cụ biến đổi bytecode/class names có thể hữu ích khi có quy trình kiểm định, nhưng **không bảo đảm** xử lý đầy đủ reflection, descriptor, XML, annotation, taglib và thay đổi API ngoài namespace. Ưu tiên JAR được maintainer hỗ trợ Jakarta hoặc rebuild từ nguồn.

## 9. Spring Security 5 → 6 có các thay đổi độc lập với Jakarta

### 9.1. Thay WebSecurityConfigurerAdapter và antMatchers

Một cấu hình Security 5 cũ có thể viết:

~~~java
// Mẫu API lịch sử, KHÔNG biên dịch trực tiếp với Security 6.
class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .anyRequest().authenticated();
    }
}
~~~

**WebSecurityConfigurerAdapter** đã bị loại bỏ khỏi cấu hình Spring Security 6. Hãy dùng bean **SecurityFilterChain** và DSL hiện đại:

~~~java
// Snippet trong một @Configuration class; thêm imports tương ứng.
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đừng giải quyết vấn đề này bằng cách đưa một thư viện Spring Security 5.x cũ vào Boot 3. Hãy migrate theo các APIs của Security 6 và kiểm tra quyền thực tế.

### 9.2. securityMatcher khác requestMatchers

- **securityMatcher(...)**: xác định request nào thuộc **SecurityFilterChain**.
- **requestMatchers(...)** bên trong **authorizeHttpRequests(...)**: đặt chính sách authorization cho request đã đi vào chain đó.

Với nhiều chain (ví dụ API Bearer và web form login), hãy test **thứ tự @Order**, fallback chain, request path/context path và AuthenticationEntryPoint. Lỗi 302 thay cho 401 có thể là do chọn chain sai, **không nhất thiết do Jakarta Servlet**.

### 9.3. @PreAuthorize, sessions, CSRF, CORS và filter registration

Nếu dùng method security, hãy kiểm tra **@EnableMethodSecurity**, AOP proxy và self-invocation; đó là một lớp khác với Servlet namespace.

Nếu chuyển custom filter từ Boot 2 sang 3, đừng vừa khai báo nó **@Component/@Bean** để container tự đăng ký, vừa gọi **http.addFilterBefore(...)** cho cùng filter. Một servlet Filter ngoài security chain và một filter bên trong FilterChainProxy có lifecycle, dispatcher mapping và thứ tự khác nhau. Kiểm tra session cookie, CSRF, CORS preflight và HTTP 401/403 sau nâng cấp, không tắt bảo mật để khiến test “xanh”.

## 10. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| **package javax.servlet does not exist** | Source cũ trên build Jakarta | Chuyển đúng import và method signatures |
| **method does not override...** | Method vẫn nhận javax.types thay vì jakarta.types | So với superclass/interface thực tế |
| **NoClassDefFoundError: javax/servlet/Filter** | Một JAR cũ còn phụ thuộc javax | Phân tích dependency tree và bytecode, nâng JAR |
| **ClassCastException: javax.servlet.Filter / jakarta.servlet.Filter** | Trộn loại Filter trong classloader | Dùng thống nhất một thế hệ Jakarta |
| **NoSuchMethodError** ở Web/Security | Version graph hoặc binary API mismatch | Loại override không tương thích, rebuild |
| Custom filter không chạy | Sai filter registration/annotation/chain matcher | Kiểm tra filter chain log, Spring bean, container mapping |
| Custom filter chạy hai lần | Vừa auto-register servlet filter vừa addFilter vào SecurityFilterChain | Chọn một registration đúng |
| **HTTP 401/403 khác trước** | Security 6 matcher/entry point/session/CSRF thay đổi | Kiểm tra policy và test request bị deny |
| **WAR không start trên Tomcat 9** | Container javax, app Jakarta | Nâng external container phù hợp |
| JSP error sau khi login | JSP/JSTL bản cũ | Nâng engine/taglib, test render thật |
| Unit test pass, production fail | MockMvc không chạy external container/JSP/proxy | Thêm integration E2E theo stack deploy |
| Build JDK 17, runtime JDK 11 | JVM runtime quá cũ | Đồng bộ Java runtime/toolchain/image |
| **404** sau proxy path rewrite | Path matching/routing không nhất quán | Kiểm tra proxy, context path và securityMatcher |

Không coi **thêm javax.servlet-api**, tắt CSRF, mở permitAll cho mọi route hoặc đổi servlet container về bản cũ là cách sửa đúng. Những mẹo này có thể che lỗi migration và đưa ứng dụng tới trạng thái thiếu kiểm soát bảo mật.

## 11. Checklist kiểm thử và bàn giao

**Build và dependency**

- Dùng Java 17+ cho cả build và runtime, kiểm tra Gradle/Maven và managed versions.
- Không còn source Servlet API cũ trong modules được deploy lên Boot 3.
- Internal/third-party JAR đã dùng Jakarta; không có runtime dependency hoặc binary cần javax.servlet ở cùng web app classloader.
- Không trộn Spring Boot 3 với Spring Security 5/Jakarta API version thiếu căn cứ.

**Servlet và SecurityFilterChain**

- Custom filter đúng **jakarta.servlet.Filter/FilterChain/ServletException**, không đăng ký hai lần.
- SecurityFilterChain match đúng HTTP routes; các trường hợp public/private vẫn giữ policy.
- AuthenticationEntryPoint, AccessDeniedHandler, CSRF, CORS và method security được kiểm tra độc lập.
- Nếu dùng multiple SecurityFilterChain, test cả fallback và URL ngoài matcher.

**Runtime và deployment**

- Spring Boot executable JAR chạy trên embedded container phù hợp.
- WAR (nếu có) chạy trên external container tương thích Jakarta, không phải Tomcat 9.
- web.xml, JSP/JSTL, listeners, ServletContainerInitializer tương thích nếu dự án sử dụng.
- Qua proxy/gateway, các trường hợp path prefix, HTTPS/HSTS, session cookies và request rejection vẫn đúng.

**Regression tests**

- MockMvc: public 200, missing-auth 401, valid credentials 200, denied scope/role 403 khi có policy.
- Test filter/lifecycle, duplicate registration, request dispatch và behavior sau khi error/async.
- Test raw HTTP qua container và qua edge với deployment thực, không chỉ unit test.
- Dùng test users và secrets riêng; không đưa credentials/tokens production vào console/log.
- Giữ rollback plan cho **cả application artifact và container/runtime**, không chỉ thay một JAR.

**Kết luận:** **javax.servlet** và **jakarta.servlet** là hai hệ Servlet API khác namespace, có binary name không tương thích trực tiếp. Nâng cấp sang **Spring Boot 3 / Spring Security 6** cần đồng bộ **Java 17+, Jakarta-compatible dependencies, custom filters, Servlet container, Security configuration và kiểm thử HTTP**. Đổi import là một phần cần thiết, nhưng bằng chứng thành công là toàn bộ ứng dụng compile, khởi động và thực thi đúng chính sách bảo mật ở môi trường triển khai.
