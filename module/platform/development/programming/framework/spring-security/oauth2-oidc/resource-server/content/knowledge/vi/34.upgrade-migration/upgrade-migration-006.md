# Chuyển servlet javax sang jakarta đúng phạm vi

## 1. Vì sao migration này cần xác định đúng phạm vi?

Từ Jakarta EE 9, nhiều API Java EE chuyển namespace từ `javax.*` sang `jakarta.*`. Với ứng dụng Servlet dùng Spring Security OAuth 2.0/OIDC Resource Server, thay đổi dễ thấy nhất là:

```java
// Trước: Servlet API thuộc Java EE namespace
import javax.servlet.Filter;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// Sau: Servlet API thuộc Jakarta EE namespace
import jakarta.servlet.Filter;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Đây là thay đổi package ở cấp API và bytecode. Một class được biên dịch để triển khai `javax.servlet.Filter` không tự động trở thành implementation của `jakarta.servlet.Filter`. Vì vậy, chỉ nâng version Spring Boot hoặc đổi container chưa đủ nếu source code, dependency hoặc plugin vẫn phụ thuộc Servlet API cũ.

Tuy nhiên, **không phải mọi package bắt đầu bằng `javax.` đều chuyển sang `jakarta.`** Nhiều package thuộc Java SE vẫn giữ nguyên namespace. Đổi hàng loạt mọi chuỗi `javax` có thể làm hỏng code hợp lệ như JDBC, cryptography, networking, XML processing hoặc Java annotation processing.

Bài học thuộc chương **Nâng cấp và di chuyển** của mô-đun **Spring Security OAuth 2.0 OIDC Resource Server**. Nội dung tập trung vào phạm vi chuyển đổi Servlet API, cách phân biệt Java SE và Jakarta EE packages, ảnh hưởng đến Spring Boot 3/Spring Framework 6/Spring Security 6, dependency và container compatibility, custom filters, OAuth2 Resource Server configuration, test và xử lý lỗi migration.

> **Quy tắc cốt lõi:** Chuyển các API Jakarta EE thực sự sang namespace `jakarta`. Giữ nguyên Java SE packages `javax` và các package riêng của Spring. Xác minh cả compile-time lẫn runtime dependencies vì bytecode của thư viện cũ vẫn tham chiếu tên class cũ.

---

## 2. Bối cảnh: Java EE trở thành Jakarta EE

Java EE được chuyển giao cho Eclipse Foundation và phát triển dưới tên Jakarta EE. Một thay đổi quan trọng của Jakarta EE 9 là chuyển phần lớn enterprise API từ `javax.*` sang `jakarta.*`.

Ví dụ:

| API trước migration | API sau migration |
|---|---|
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.websocket.*` | `jakarta.websocket.*` |
| `javax.enterprise.*` | `jakarta.enterprise.*` |
| `javax.inject.*` | `jakarta.inject.*` |
| `javax.annotation.*` (Jakarta Common Annotations) | `jakarta.annotation.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.activation.*` | `jakarta.activation.*` |

Các API trên không chỉ đổi tên trong source code. Tên class đầy đủ (fully qualified class name) cũng thay đổi trong bytecode, method signatures, annotations, descriptors và dependency metadata.

### 2.1. Vì sao binary compatibility bị ảnh hưởng?

Giả sử một thư viện cũ khai báo:

```java
public class LegacyAuthFilter implements javax.servlet.Filter {
    // ...
}
```

Ứng dụng mới chạy trên Servlet container chỉ cung cấp `jakarta.servlet.Filter`. JVM xem hai interface có tên khác nhau là hai kiểu khác nhau. Class cũ không triển khai interface mà container mới yêu cầu.

Có thể gặp lỗi:

```text
ClassNotFoundException: javax.servlet.Filter
NoClassDefFoundError: javax/servlet/Filter
ClassCastException: ... cannot be cast to jakarta.servlet.Filter
```

Ngay cả khi source code ứng dụng đã đổi import, một dependency đã biên dịch sẵn với `javax.servlet` vẫn có thể gây lỗi runtime.

### 2.2. Jakarta namespace không phải prefix để thay toàn cục

Migration cần phân biệt:

- Jakarta EE API: đổi namespace theo release tương ứng.
- Java SE API: giữ nguyên namespace nếu package vẫn thuộc JDK.
- Spring API: tiếp tục dùng package `org.springframework.*`.
- Third-party API: theo version tương thích của vendor.
- Application-specific package: chỉ đổi nếu chính ứng dụng sở hữu namespace đó và có lý do rõ ràng.

---

## 3. Phân biệt package javax cần đổi và package javax cần giữ

Đây là phần quan trọng nhất của migration “đúng phạm vi”.

### 3.1. Các package Jakarta EE thường cần chuyển

| Namespace cũ | Namespace mới | Khi nào gặp trong ứng dụng |
|---|---|---|
| `javax.servlet` | `jakarta.servlet` | Filters, servlets, listeners, request/response, ServletContext. |
| `javax.servlet.http` | `jakarta.servlet.http` | HttpServletRequest, HttpServletResponse, HttpSession. |
| `javax.servlet.annotation` | `jakarta.servlet.annotation` | @WebServlet, @WebFilter, @WebListener. |
| `javax.servlet.descriptor` | `jakarta.servlet.descriptor` | Deployment descriptor APIs. |
| `javax.validation` | `jakarta.validation` | Bean Validation constraints và Validator. |
| `javax.persistence` | `jakarta.persistence` | JPA entity, EntityManager, persistence annotations. |
| `javax.transaction` | `jakarta.transaction` | Jakarta Transactions API, ví dụ UserTransaction. |
| `javax.annotation` | `jakarta.annotation` | PostConstruct, PreDestroy, Resource, RolesAllowed. |
| `javax.inject` | `jakarta.inject` | Inject, Named, Provider. |
| `javax.enterprise` | `jakarta.enterprise` | CDI annotations và APIs. |
| `javax.ws.rs` | `jakarta.ws.rs` | JAX-RS resources, providers, filters. |
| `javax.websocket` | `jakarta.websocket` | WebSocket endpoints. |
| `javax.xml.bind` | `jakarta.xml.bind` | JAXB marshalling/unmarshalling. |
| `javax.mail` | `jakarta.mail` | Jakarta Mail. |
| `javax.activation` | `jakarta.activation` | Jakarta Activation. |
| `javax.servlet.jsp` | `jakarta.servlet.jsp` | JSP APIs. |
| `javax.security.enterprise` | `jakarta.security.enterprise` | Jakarta Security APIs. |
| `javax.security.auth.message` | `jakarta.security.auth.message` | Jakarta Authentication/JASPIC APIs. |

Danh sách này là các nhóm phổ biến, không phải phép thay thế mọi package có tên gần giống. Kiểm tra API documentation và dependency version của từng thư viện.

### 3.2. Các package Java SE thường phải giữ nguyên javax

| Package giữ nguyên | Lý do |
|---|---|
| `javax.crypto` | Cryptography APIs của Java SE. |
| `javax.net` và `javax.net.ssl` | Networking và TLS APIs của Java SE. |
| `javax.sql` | JDBC extensions/DataSource APIs của Java SE. |
| `javax.naming` | JNDI APIs của Java SE. |
| `javax.management` | JMX APIs của Java SE. |
| `javax.xml.parsers` | XML parser APIs của Java SE. |
| `javax.xml.transform` | XML transformation APIs của Java SE. |
| `javax.xml.namespace` | XML namespace APIs của Java SE. |
| `javax.xml.stream` | StAX APIs của Java SE. |
| `javax.xml.validation` | XML Schema validation APIs của Java SE; không nhầm với Bean Validation. |
| `javax.security.auth` | Java Authentication and Authorization Service (JAAS) APIs của Java SE. |
| `javax.security.auth.callback` | Java SE callback APIs. |
| `javax.security.auth.login` | Java SE login APIs. |
| `javax.annotation.processing` | Java compiler annotation-processing APIs. |
| `javax.lang.model` | Java compiler language model APIs. |
| `javax.transaction.xa` | XA transaction interfaces thuộc Java SE module. |

Ví dụ trong một ứng dụng Resource Server:

```java
import javax.crypto.SecretKey;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;

import jakarta.servlet.http.HttpServletRequest;
```

Các import `javax` đầu tiên vẫn hợp lệ trên JDK. Chỉ Servlet import chuyển sang `jakarta`.

### 3.3. Các trường hợp tên gần giống nhưng thuộc API khác nhau

Đừng nhầm:

- `javax.validation` (Bean Validation API cũ) với `javax.xml.validation` (Java SE XML validation).
- `javax.annotation` (Jakarta Common Annotations trước migration) với `javax.annotation.processing` (Java compiler API).
- `javax.transaction` (Jakarta Transactions API trước migration) với `javax.transaction.xa` (Java SE XA API).
- `javax.security.enterprise` hoặc `javax.security.auth.message` (Jakarta EE APIs trước migration) với `javax.security.auth` (JAAS của Java SE).

Không quyết định chỉ bằng prefix. Hãy kiểm tra package cụ thể, module sở hữu nó và version API.

---

## 4. Phạm vi trong Spring Boot, Spring Framework và Spring Security

Migration Servlet namespace thường xuất hiện khi nâng ứng dụng từ Spring Boot 2.x lên Spring Boot 3.x.

Các thay đổi liên quan:

| Thành phần | Trước migration phổ biến | Sau migration phổ biến |
|---|---|---|
| Spring Boot | 2.x | 3.x |
| Spring Framework | 5.x | 6.x |
| Spring Security | 5.x | 6.x |
| Java baseline | Java 8/11 tùy Boot 2 minor | Java 17 trở lên cho Spring Boot 3 |
| Servlet API | Java EE `javax.servlet` | Jakarta `jakarta.servlet` |
| Embedded Tomcat | Tomcat 9 | Tomcat 10.1 trong các dòng Boot 3 thông dụng |
| Servlet container | Servlet 4.0 ở cấu hình Boot 2 phổ biến | Jakarta Servlet 6.0 trong cấu hình Boot 3/Tomcat 10.1 phổ biến |

Luôn kiểm tra compatibility matrix của đúng Spring Boot minor release và container đang triển khai. Không suy ra mọi version Boot 3 đều dùng cùng minor Servlet API hoặc cùng embedded container.

### 4.1. Package của Spring Security không đổi sang jakarta

Các class sau vẫn nằm trong namespace Spring:

```java
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationFilter;
```

Không đổi chúng thành `jakarta.security.*` hoặc package tưởng tượng khác. Jakarta namespace migration chỉ áp dụng cho Jakarta EE APIs.

### 4.2. Spring Boot starter coordinates thường giữ nguyên

Ví dụ dependencies vẫn dùng artifact Spring:

```xml
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
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Bạn không đổi groupId thành `jakarta` cho các starter này. Spring Boot BOM quản lý version tương thích giữa Spring Framework, Spring Security và các dependency được hỗ trợ.

### 4.3. Java baseline là một phần của migration

Spring Boot 3 yêu cầu Java 17 trở lên. Trước khi đổi namespace:

- Kiểm tra JDK build và runtime.
- Cập nhật Maven/Gradle toolchain.
- Kiểm tra CI image và production base image.
- Cập nhật compiler release/target.
- Kiểm tra annotation processors và code generators.
- Xác nhận third-party libraries hỗ trợ Java 17 và Jakarta APIs.

Nếu build bằng JDK 17 nhưng production chạy JDK cũ, migration có thể compile thành công nhưng deployment thất bại.

---

## 5. Servlet API migration: các kiểu dữ liệu chính

Các kiểu Servlet thường xuất hiện trong custom filters, interceptors, listeners và authentication handlers.

| Trước | Sau |
|---|---|
| `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| `javax.servlet.FilterChain` | `jakarta.servlet.FilterChain` |
| `javax.servlet.ServletRequest` | `jakarta.servlet.ServletRequest` |
| `javax.servlet.ServletResponse` | `jakarta.servlet.ServletResponse` |
| `javax.servlet.ServletException` | `jakarta.servlet.ServletException` |
| `javax.servlet.ServletContext` | `jakarta.servlet.ServletContext` |
| `javax.servlet.ServletConfig` | `jakarta.servlet.ServletConfig` |
| `javax.servlet.http.HttpServlet` | `jakarta.servlet.http.HttpServlet` |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` |
| `javax.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` |
| `javax.servlet.http.Cookie` | `jakarta.servlet.http.Cookie` |
| `javax.servlet.http.HttpServletRequestWrapper` | `jakarta.servlet.http.HttpServletRequestWrapper` |
| `javax.servlet.http.HttpServletResponseWrapper` | `jakarta.servlet.http.HttpServletResponseWrapper` |
| `javax.servlet.annotation.WebFilter` | `jakarta.servlet.annotation.WebFilter` |
| `javax.servlet.annotation.WebListener` | `jakarta.servlet.annotation.WebListener` |

### 5.1. Custom Filter

Trước migration:

```java
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class RequestAuditFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        filterChain.doFilter(request, response);
    }
}
```

Sau migration:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class RequestAuditFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        filterChain.doFilter(request, response);
    }
}
```

Class `OncePerRequestFilter` vẫn là class Spring. Các kiểu Servlet trong method signature chuyển sang Jakarta. Khi compile với Spring Framework 6, method override phải khớp chính xác kiểu Jakarta.

### 5.2. Custom Servlet

```java
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/legacy-status")
public class StatusServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain");
        response.getWriter().write("OK");
    }
}
```

Nếu ứng dụng dùng Spring MVC controllers, thường không cần tự viết Servlet. Nhưng các servlet legacy, vendor integration và servlet registration vẫn phải dùng Jakarta types khi chạy trên Jakarta container.

### 5.3. Servlet listener

```java
import jakarta.servlet.ServletContextEvent;
import jakarta.servlet.ServletContextListener;
import jakarta.servlet.annotation.WebListener;

@WebListener
public class StartupListener implements ServletContextListener {

    @Override
    public void contextInitialized(ServletContextEvent event) {
        // Initialize application resources.
    }

    @Override
    public void contextDestroyed(ServletContextEvent event) {
        // Release application resources.
    }
}
```

Kiểm cả listener registration trong code và deployment descriptor. Một listener cũ có thể compile nếu API cũ vẫn có trong classpath, nhưng container mới không nhận nó như Jakarta listener.

---

## 6. OAuth2 Resource Server: phần nào đổi, phần nào giữ nguyên?

Spring Security Resource Server sử dụng các package riêng của Spring. Cấu hình JWT/opaque token thường không cần đổi tên package Spring Security chỉ vì Servlet API chuyển namespace.

Ví dụ SecurityFilterChain:

```java
@Configuration
@EnableWebSecurity
public class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Không cần thay `org.springframework.security` thành `jakarta.security`.

### 6.1. BearerTokenAuthenticationFilter và servlet request

Spring Security 6 dùng Servlet API Jakarta ở implementation của filter chain. Nếu ứng dụng tự tạo filter, resolver hoặc authentication handler làm việc với request/response, các method signature phải nhận Jakarta types.

Ví dụ custom authentication entry point:

```java
@Component
public class ApiAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"error\":\"unauthorized\"}"
        );
    }
}
```

Imports Servlet chuyển sang `jakarta.servlet.http.*`; `AuthenticationEntryPoint` và `AuthenticationException` vẫn thuộc `org.springframework.security.*`.

### 6.2. Custom BearerTokenResolver

```java
public final class HeaderOnlyBearerTokenResolver
        implements BearerTokenResolver {

    private final DefaultBearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    @Override
    public String resolve(HttpServletRequest request) {
        return delegate.resolve(request);
    }
}
```

`HttpServletRequest` ở đây phải là `jakarta.servlet.http.HttpServletRequest`. `BearerTokenResolver` và `DefaultBearerTokenResolver` vẫn nằm trong Spring Security.

### 6.3. JWT và Opaque Token không đổi namespace

Các API sau vẫn là Spring Security types:

- `JwtDecoder`
- `Jwt`
- `JwtAuthenticationConverter`
- `OAuth2TokenValidator<Jwt>`
- `OpaqueTokenIntrospector`
- `OAuth2AuthenticatedPrincipal`
- `BearerTokenAuthentication`
- `BearerTokenAuthenticationFilter`

Nếu code chỉ làm việc với các type này mà không tham chiếu Servlet API trực tiếp, không cần thay package import chỉ vì migration Servlet.

### 6.4. SecurityFilterChain là cấu hình Spring, không phải Servlet API

`SecurityFilterChain` vẫn được khai báo bằng Spring Security. Tuy nhiên, chain được gắn vào Servlet container thông qua Spring Security filter infrastructure. Vì vậy dependency Spring Framework/Security phải tương thích Jakarta Servlet API.

---

## 7. Spring Security 6 có thay đổi API riêng ngoài namespace

Nâng Spring Boot 2 lên 3 thường kéo theo Spring Security 5 lên 6. Một số API Spring Security thay đổi độc lập với việc `javax.servlet` chuyển sang `jakarta.servlet`.

| Cấu hình cũ thường gặp | Hướng cấu hình mới |
|---|---|
| `WebSecurityConfigurerAdapter` | Khai báo bean `SecurityFilterChain` và `WebSecurityCustomizer` khi cần. |
| `antMatchers(...)` | `requestMatchers(...)`. |
| `mvcMatchers(...)` | `requestMatchers(...)` với matcher phù hợp. |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity`. |
| Override configure(HttpSecurity) | Cấu hình bằng lambda DSL trong bean `SecurityFilterChain`. |

Ví dụ cũ:

```java
@Override
protected void configure(HttpSecurity http) throws Exception {
    http
        .authorizeRequests()
        .antMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders:read");
}
```

Ví dụ mới:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}
```

Đừng trộn hai loại thay đổi thành một. Nếu compiler báo thiếu `javax.servlet`, xử lý namespace/dependency. Nếu compiler báo không tìm thấy `WebSecurityConfigurerAdapter` hoặc `antMatchers`, đó là Spring Security API migration.

---

## 8. Dependency management: chọn đúng Jakarta API

### 8.1. Dùng Spring Boot dependency management

Với Spring Boot, ưu tiên starters và BOM cùng một release line.

Maven:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
</parent>

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
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Ví dụ trên dùng placeholder version để thể hiện BOM management; dự án cần chọn một Spring Boot release đã được tổ chức hỗ trợ và dùng cùng release line cho plugin/dependencies.

### 8.2. Không thêm Servlet API thủ công nếu starter đã cung cấp

Với Spring Boot web application chạy embedded container, `spring-boot-starter-web` kéo theo stack tương ứng. Không cần thêm một Servlet API cũ vào classpath.

Nếu build WAR để deploy external container, dependency Servlet API có thể được khai báo scope `provided` theo cách đóng gói phù hợp. Khi đó phải dùng Jakarta Servlet API version tương thích với target container.

Ví dụ Maven khi cần khai báo API rõ ràng:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

Không ghim version tùy tiện nếu Spring Boot BOM đã quản lý version tương thích.

### 8.3. Dependencies Bean Validation

Nếu ứng dụng dùng Bean Validation, chuyển API và provider đồng bộ:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
```

Spring Boot 3 thường dùng Hibernate Validator tương thích Jakarta Validation. Đừng chỉ thay annotation import mà giữ một provider cũ biên dịch với `javax.validation`.

### 8.4. Dependencies persistence

Nếu ứng dụng có JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.EntityManager;
```

Chọn Hibernate/JPA provider hỗ trợ Jakarta Persistence. Một entity compiled against `javax.persistence.Entity` không phải Jakarta entity chỉ vì package annotation có tên gần giống.

### 8.5. Tránh trộn API cũ và mới

Không cố đưa đồng thời `javax.servlet-api` và `jakarta.servlet-api` vào ứng dụng để “cho cả hai cùng chạy”. Chúng là hai API khác nhau. Một thư viện legacy cần đúng version Jakarta hoặc cần được thay thế/chuyển đổi.

---

## 9. Kiểm tra dependency tree và transitive libraries

Đổi import trong source không xử lý dependency transitives.

### 9.1. Maven

Xem dependency tree:

```bash
mvn dependency:tree
```

Lọc các API có liên quan:

```bash
mvn dependency:tree -Dincludes=javax.servlet:*,jakarta.servlet:*
```

Kiểm tra dependency convergence và loại trừ artifact cũ khi có bằng chứng dependency mới thay thế được:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-integration</artifactId>
    <version>LIBRARY_VERSION</version>
    <exclusions>
        <exclusion>
            <groupId>javax.servlet</groupId>
            <artifactId>javax.servlet-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Chỉ exclusion khi thư viện không còn cần API cũ hoặc đã có artifact Jakarta tương thích. Exclusion đơn thuần không chuyển bytecode cũ sang Jakarta.

### 9.2. Gradle

Xem dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm dependency cũ:

```bash
./gradlew dependencyInsight --dependency javax.servlet --configuration runtimeClasspath
```

Nếu có nhiều configuration, kiểm tra cả compile, runtime, test và annotation processor configurations.

### 9.3. Kiểm tra bytecode của thư viện

Một dependency có thể không khai báo trực tiếp `javax.servlet-api` nhưng bytecode vẫn tham chiếu `javax/servlet/...`. Có thể dùng `jdeps`, `jar tf` và công cụ bytecode/dependency analysis để tìm class reference trong JAR.

Ví dụ:

```bash
jdeps --recursive --multi-release 17 path/to/legacy-library.jar
```

`jdeps` hữu ích để nhận diện package dependencies nhưng không thay thế runtime test. Reflection, service loading, string-based class names, XML descriptors và generated metadata có thể không hiện rõ trong dependency graph.

### 9.4. Phân loại từng dependency

Với mỗi thư viện:

- Có version Jakarta-compatible chính thức không?
- Vendor có phát hành artifact riêng cho Jakarta không?
- Thư viện chỉ dùng Java SE hay trực tiếp tham chiếu Servlet/JPA/Validation?
- Có plugin, annotation processor hoặc generated source đi kèm không?
- Có còn được maintain không?
- Có thể thay bằng Spring-native API không?
- Nếu tạm transform bytecode, có test và support policy không?

Ưu tiên nâng version chính thức hoặc thay dependency không còn được duy trì.

---

## 10. Embedded container và external container

Servlet namespace phải khớp với runtime container.

| Container family | Namespace Servlet | Ghi chú |
|---|---|---|
| Tomcat 9 | `javax.servlet` | Dòng Java EE Servlet 4.0. |
| Tomcat 10.0 | `jakarta.servlet` | Jakarta EE 9 namespace; nhánh 10.0 đã hết vòng đời hỗ trợ. |
| Tomcat 10.1 | `jakarta.servlet` | Dùng trong nhiều cấu hình Spring Boot 3.x; kiểm Servlet API version tương ứng. |
| Jetty 9/10 | Chủ yếu Java EE namespace ở các cấu hình cũ | Kiểm đúng distribution/module và version. |
| Jetty 11 | `jakarta.servlet` | Jakarta EE 9 era. |
| Jetty 12 | Hỗ trợ các environment EE theo module | Chọn đúng EE environment và version tương thích. |
| Undertow | Phụ thuộc major/version và integration | Kiểm Jakarta-compatible release. |

Không dùng một container cũ chỉ vì ứng dụng compile được. External container phải cung cấp Servlet API mà ứng dụng và Spring Framework yêu cầu.

### 10.1. Embedded deployment

Khi chạy Spring Boot executable JAR, Boot quản lý embedded container theo dependency graph. Nâng Boot release line thường kéo theo container tương thích.

### 10.2. WAR deployment

Khi deploy WAR:

- Kiểm external container hỗ trợ Jakarta Servlet API đúng version.
- Đặt API container ở scope phù hợp, thường là provided.
- Không đóng gói Servlet API cũ trong WAR.
- Kiểm container libraries không có duplicate/legacy servlet classes.
- Kiểm server startup logs và classloader behavior.
- Thử deployment trên đúng container version như production.

### 10.3. Không thể chỉ đổi server version để sửa thư viện legacy

Nếu JAR bên thứ ba vẫn implements `javax.servlet.Filter`, Tomcat 10.1 không thể tự xem nó là `jakarta.servlet.Filter`. Cần bản thư viện Jakarta, rebuild source hoặc transformation có kiểm soát.

---

## 11. Migration deployment descriptors và annotations

### 11.1. web.xml

Ứng dụng dùng Servlet deployment descriptor cần kiểm version và schema namespace theo target Jakarta EE/Servlet level.

Ví dụ descriptor Jakarta Servlet 6.0:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      https://jakarta.ee/xml/ns/jakartaee
      https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <display-name>orders-api</display-name>
</web-app>
```

Dùng descriptor version tương thích với Servlet container thực tế. Nếu ứng dụng không cần `web.xml`, không thêm chỉ để migration.

### 11.2. Servlet annotations

Chuyển:

```java
import jakarta.servlet.annotation.WebFilter;
import jakarta.servlet.annotation.WebListener;
import jakarta.servlet.annotation.WebServlet;
```

Các annotations Spring như `@RestController`, `@RequestMapping`, `@Component`, `@Configuration` vẫn nằm trong Spring packages.

### 11.3. Annotation lifecycle và injection

Ví dụ:

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.annotation.Resource;
```

`@PostConstruct` và `@PreDestroy` là Jakarta Common Annotations. Nếu dùng `javax.annotation.processing.*` trong annotation processor, giữ nguyên vì đó là Java compiler API.

### 11.4. JSP, JSTL và tag libraries

Nếu ứng dụng dùng JSP, kiểm cả Servlet JSP API và JSTL version tương thích Jakarta. Một số tag library URI/version có thay đổi theo Jakarta Tags. Đừng chỉ thay import Java mà bỏ qua JSP pages, TLD files và taglib dependencies.

---

## 12. Custom Spring filters và filter registration

### 12.1. Filter kế thừa Spring OncePerRequestFilter

`OncePerRequestFilter` vẫn là Spring class. Chỉ các Servlet types trong override signature đổi sang Jakarta.

```java
@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String correlationId =
            request.getHeader("X-Correlation-Id");

        if (correlationId == null || correlationId.isBlank()) {
            correlationId = UUID.randomUUID().toString();
        }

        response.setHeader("X-Correlation-Id", correlationId);
        chain.doFilter(request, response);
    }
}
```

Imports phải dùng:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;
```

### 12.2. FilterRegistrationBean

`FilterRegistrationBean` vẫn thuộc Spring Boot:

```java
@Bean
FilterRegistrationBean<CorrelationIdFilter> correlationFilter(
        CorrelationIdFilter filter) {
    FilterRegistrationBean<CorrelationIdFilter> registration =
        new FilterRegistrationBean<>();
    registration.setFilter(filter);
    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
```

Generic type phải là Filter implementation tương thích Jakarta. Kiểm tránh đăng ký cùng filter hai lần: một lần qua Servlet container registration và một lần trong Spring Security chain.

### 12.3. Filter trong SecurityFilterChain

Nếu filter có nhiệm vụ security, thường nên đặt nó trong Spring Security chain bằng cơ chế phù hợp:

```java
http.addFilterBefore(
    correlationIdFilter,
    BearerTokenAuthenticationFilter.class
);
```

Thứ tự filter có ý nghĩa. Không đặt custom authentication/authorization filter tùy tiện trước hoặc sau Bearer filter khi chưa hiểu exception handling, SecurityContext lifecycle và async dispatch behavior.

### 12.4. Async và error dispatch

Sau migration, test cả:

- Request dispatch bình thường.
- Async dispatch nếu filter hỗ trợ.
- Error dispatch.
- Request wrapper/response wrapper.
- Filter order và dispatcher types.
- SecurityContext propagation.

Các vấn đề này không chỉ là namespace issue nhưng thường lộ ra khi custom filter được compile lại.

---

## 13. Authentication handlers, resolver và servlet adapters

Các class Spring Security có thể nhận Servlet types trong method signatures.

Ví dụ:

```java
public class JsonBearerEntryPoint
        implements AuthenticationEntryPoint {

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"error\":\"invalid_token\"}"
        );
    }
}
```

Các import:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
```

Tương tự, kiểm các extension points:

- `AuthenticationEntryPoint`
- `AccessDeniedHandler`
- `BearerTokenResolver`
- `AuthenticationFailureHandler`
- `AuthenticationSuccessHandler`
- `RequestMatcher`
- `SecurityContextRepository`
- Custom `Filter` hoặc `HandlerInterceptor`
- Custom servlet request/response wrappers

Các interface Spring vẫn giữ namespace Spring. Chỉ Servlet parameter types chuyển.

---

## 14. Spring MVC, WebFlux và ranh giới migration

Không phải mọi Spring application đều dùng Servlet API.

### 14.1. Spring MVC

Spring MVC chạy trên Servlet stack. Controller thường không import Servlet types, nhưng custom filters, servlet listeners, request wrappers và security adapters có thể cần đổi.

### 14.2. Spring WebFlux

WebFlux dùng reactive HTTP abstractions như `ServerWebExchange` và không dựa trên Servlet API trong execution model chính. Các import `org.springframework.web.server`, `org.springframework.http.server.reactive` và Spring Security reactive APIs không đổi thành Jakarta Servlet types.

Nếu ứng dụng có cả MVC và WebFlux dependencies, xác định application thực sự chạy stack nào. Không thêm Servlet API chỉ vì thấy Spring Security OAuth2 Resource Server.

### 14.3. Reactive Resource Server

Reactive security configuration thường dùng `SecurityWebFilterChain` và `ServerHttpSecurity`:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}
```

Đây là Spring WebFlux API, không cần thay sang Jakarta Servlet API. Nếu code reactive có một integration library Servlet-based, migration scope của dependency đó cần đánh giá riêng.

---

## 15. Spring Security Test và MockMvc sau migration

Các package của Spring Test và Spring Security Test vẫn thuộc Spring:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
```

MockMvc không đổi namespace. Tuy nhiên, Spring Framework 6 và Spring Security 6 dùng Servlet API Jakarta bên dưới.

### 15.1. MockMvc với Bearer token

Ví dụ filter-flow test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerMigrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void protectedEndpointRejectsMissingBearerToken()
            throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }
}
```

### 15.2. Authorization-only test

Spring Security Test post-processors như `jwt()` vẫn thuộc Spring Security Test:

```java
mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());
```

Test này hữu ích cho authorization rules. Nó không chứng minh JWT decoder hoặc Servlet Bearer filter đã xác minh token compact thực tế.

### 15.3. Filter-flow test

Để kiểm tra Resource Server filter chain, gửi Bearer header và dùng decoder thật hoặc mock decoder theo mục tiêu:

```java
mvc.perform(get("/api/orders/42")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer " + signedTestToken))
    .andExpect(status().isOk());
```

Với migration test, hãy xác nhận custom filters và servlet integration vẫn chạy trên Jakarta types. Giữ riêng test signature/issuer/audience và test namespace compatibility để kết quả dễ chẩn đoán.

### 15.4. Test Servlet mocks

Nếu test trực tiếp Servlet APIs, kiểm import:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.mock.web.MockHttpServletRequest;
```

`MockHttpServletRequest` là Spring mock class; object của nó triển khai Jakarta Servlet contracts trong Spring Framework 6. Không dùng một mock/request từ thư viện test cũ triển khai javax contract.

---

## 16. Third-party libraries và các điểm migration thường bị bỏ sót

Một ứng dụng có thể compile source nhưng runtime vẫn nạp thư viện cũ.

| Nhóm | Ví dụ cần kiểm |
|---|---|
| Security integrations | SAML adapters, custom authentication filters, identity provider SDKs. |
| Servlet filters | WAF agent, tracing agent, compression, session, audit filter. |
| Persistence | JPA provider, entity listeners, custom Hibernate types. |
| Validation | Bean Validation provider và custom constraints. |
| JSON/XML | JAXB, XML bind adapters, SOAP/JAX-WS dependencies. |
| REST clients/servers | JAX-RS implementations, providers, servlet bridges. |
| Messaging | Jakarta Mail, JMS, messaging adapters. |
| CDI/injection | CDI extensions, javax.inject consumers. |
| Observability | APM Java agents, servlet instrumentation, tracing libraries. |
| Code generation | OpenAPI generators, annotation processors, generated stubs. |
| Testing | Mock servlet libraries, embedded containers, test fixtures. |
| Build plugins | Packaging, bytecode weaving, shading, enhancement plugins. |

### 16.1. APM agents và Java agents

Một agent có thể instrument method signatures của Servlet API. Nếu agent cũ chỉ nhận diện `javax.servlet`, nó có thể không instrument Jakarta requests hoặc gây lỗi linkage.

Kiểm version agent, bytecode transformer và startup flags. Không giả định agent tương thích chỉ vì ứng dụng compile.

### 16.2. Generated source

Code generated từ OpenAPI, WSDL, JAXB hoặc annotation processors có thể vẫn sinh import `javax.*`. Cập nhật generator/plugin và regenerate source. Không chỉ sửa file generated nếu lần build sau sẽ ghi đè.

### 16.3. Shaded/fat JAR dependencies

Một library có thể bundle API classes hoặc relocate packages. Kiểm nội dung JAR, service provider files và manifest. Không thêm API cũ vào fat JAR để che lỗi class loading.

---

## 17. Xử lý thư viện chỉ có bản javax

Ưu tiên theo thứ tự:

1. Nâng lên version chính thức hỗ trợ Jakarta.
2. Dùng artifact Jakarta variant nếu vendor phát hành.
3. Thay thư viện bằng implementation được duy trì.
4. Nếu có source, fork/rebuild và kiểm toàn bộ API surface.
5. Chỉ dùng bytecode transformation như giải pháp có kiểm soát khi không còn lựa chọn khả thi.

### 17.1. Vì sao không nên chỉ exclusion dependency cũ?

Nếu thư viện đã biên dịch có method:

```java
public void register(javax.servlet.Filter filter)
```

thì xóa `javax.servlet-api` khỏi dependency tree làm runtime thiếu class. Thêm `jakarta.servlet-api` không làm method signature tự đổi.

### 17.2. Transformation tools

Có các công cụ chuyển đổi Java EE namespace sang Jakarta, ví dụ Eclipse Transformer hoặc Apache Tomcat Jakarta EE Migration Tool. Chúng có thể hữu ích khi chuyển một ứng dụng/library legacy trong giai đoạn migration.

Tuy nhiên, transformation có giới hạn:

- Không thay thế việc nâng version vendor được hỗ trợ.
- Reflection hoặc class names lưu dưới dạng string có thể cần kiểm tra.
- Serialized data, service descriptors và XML resources cần xác minh.
- Không phải mọi third-party integration đều được transform an toàn.
- Cần kiểm license/support và quy trình tái tạo artifact.
- Phải test trên đúng runtime container.

Không biến transformed JAR thành dependency production lâu dài mà không có owner, reproducible build và kế hoạch thay thế.

---

## 18. Chiến lược migration theo từng bước

Migration an toàn nên được chia thành các thay đổi có thể kiểm soát.

### Bước 1: Chụp trạng thái hiện tại

Ghi lại:

- Java version.
- Spring Boot/Framework/Security versions.
- Servlet container và version.
- Build tool và dependency tree.
- Các custom filters, listeners, servlets.
- Các integration libraries.
- Test baseline và deployment target.
- OAuth2 Resource Server configuration.

Giữ baseline để phân biệt lỗi đã có từ trước với lỗi do migration.

### Bước 2: Kiểm tra compatibility matrix

Xác nhận:

- Spring Boot release hỗ trợ Java runtime hiện tại.
- Spring Framework/Security versions được Boot quản lý.
- Servlet container hỗ trợ Jakarta API cần thiết.
- OAuth2/JWT/JWK/introspection libraries tương thích.
- Vendor libraries và agents có bản Jakarta.

Không nâng riêng một JAR Spring Security ngoài BOM trừ khi có lý do tương thích rõ.

### Bước 3: Inventory namespace imports

Tìm các imports có khả năng cần chuyển:

```bash
rg -n "javax\.(servlet|validation|persistence|annotation|inject|ws\.rs|websocket|enterprise|transaction|xml\.bind|mail|activation)" src
```

Sau đó phân loại từng kết quả. Đừng chạy lệnh replace toàn bộ `javax`.

Tìm các tham chiếu Servlet trong generated source và test source, không chỉ thư mục main.

### Bước 4: Nâng framework và dependency đồng bộ

- Chuyển Spring Boot release line.
- Dùng BOM/parent quản lý versions.
- Nâng Spring Security cùng release line.
- Nâng Jakarta-compatible providers và integrations.
- Loại dependency javax API cũ chỉ khi consumer đã được cập nhật.
- Chuyển JDK toolchain và CI runtime.

### Bước 5: Sửa source theo package cụ thể

Chuyển Servlet imports và các Jakarta EE imports cần thiết. Giữ Java SE javax imports. Sửa custom filters, servlet adapters, listeners, validation/persistence annotations và generated sources.

### Bước 6: Cập nhật container/descriptors

- Chọn Jakarta-compatible embedded/external container.
- Cập nhật web.xml nếu có.
- Kiểm servlet registrations và listener declarations.
- Kiểm WAR packaging scope.
- Kiểm APM/agent support.

### Bước 7: Compile và kiểm dependency graph

Chạy compile/test compile và xem dependency tree. Xử lý từng library còn tham chiếu javax API cũ. Đừng che lỗi bằng cách đưa cả hai Servlet API vào classpath.

### Bước 8: Chạy tests theo tầng

- Unit tests cho custom filters/resolvers.
- Spring Security MockMvc tests.
- Signed JWT filter-flow tests.
- Opaque introspection tests.
- Integration tests với target container.
- End-to-end test qua gateway nếu có.

### Bước 9: Deploy staging và quan sát

Kiểm startup logs, class loading, filter registration, endpoint health, JWT validation, 401/403 behavior, downstream calls, metrics và traces.

### Bước 10: Rollout có kiểm soát

Giữ rollback artifact và configuration tương ứng. Theo dõi error rates, class loading exceptions, auth failures, latency và container restarts. Chỉ loại bỏ compatibility workarounds sau khi mọi runtime đã được chuyển.

---

## 19. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException: javax.servlet.Filter` | Dependency cũ tham chiếu Servlet API cũ | Nâng/rebuild thư viện hoặc thay dependency. |
| `NoClassDefFoundError: javax/servlet/...` | Legacy bytecode hoặc agent cần javax class | Xem stack trace và dependency origin; không thêm API cũ một cách mù quáng. |
| `ClassCastException` giữa javax và jakarta Filter | Hai interface khác nhau | Dùng implementation Jakarta-compatible. |
| `method does not override or implement a method` | Custom filter override còn dùng javax parameter types | Đổi đúng Servlet imports sang jakarta. |
| Spring context không tạo được SecurityFilterChain | Spring Security API/config migration hoặc dependency mismatch | Kiểm version/BOM, DSL và bean configuration. |
| Endpoint protected trả 401 hàng loạt | Filter chain, decoder, issuer/JWKS hoặc deployment config bị thay đổi | Kiểm startup, token validation và chain matcher. |
| Filter custom không chạy | Đăng ký sai type, thứ tự hoặc double registration | Kiểm bean/Servlet registration và SecurityFilterChain order. |
| WAR chạy local nhưng lỗi trên server | External container còn javax hoặc không đúng Servlet level | Chọn Jakarta-compatible container. |
| Build pass nhưng production fail | Runtime dependency/agent/container chưa tương thích | Kiểm runtimeClasspath và deployment artifact thực tế. |
| Annotation validation không hoạt động | javax và jakarta validation API/provider bị trộn | Nâng provider và annotations đồng bộ. |
| JPA entity không được phát hiện | Entity vẫn dùng javax.persistence | Chuyển sang jakarta.persistence và nâng provider. |
| Generated source lại sinh javax imports | Generator/plugin version cũ | Nâng generator, cấu hình namespace và regenerate. |
| Tests compile nhưng servlet mock lỗi | Test library hoặc mock cũ triển khai javax contract | Nâng Spring Test/security-test và mock dependency. |
| TLS/crypto code bị lỗi sau replace | Đã đổi nhầm Java SE javax package | Khôi phục javax.crypto/javax.net imports. |

### 19.1. Đọc stack trace theo classloader origin

Khi gặp linkage error:

1. Tìm class đầu tiên thuộc ứng dụng hoặc third-party library.
2. Xác định class đang tham chiếu `javax/...` hay `jakarta/...`.
3. Kiểm JAR chứa class bằng dependency tree hoặc archive inspection.
4. Xác định dependency nào đưa API cũ vào runtime.
5. Kiểm classloader/container cung cấp API nào.
6. Sửa dependency source hoặc thay artifact.
7. Chạy lại trên đúng container, không chỉ embedded test.

Không xử lý bằng cách copy một Servlet API JAR ngẫu nhiên vào lib. Cách đó có thể tạo classloader conflicts và không biến legacy Filter thành Jakarta Filter.

### 19.2. Phân biệt namespace lỗi với Security API lỗi

Ví dụ:

- Không tìm thấy `jakarta.servlet.Filter`: Jakarta Servlet dependency/container issue.
- Không tìm thấy `WebSecurityConfigurerAdapter`: Spring Security 6 API change.
- Không tìm thấy `javax.crypto.SecretKey`: Java SE/runtime/module issue hoặc đã replace nhầm.
- `JwtDecoder` không có trong context: OAuth2 Resource Server configuration/dependency issue, không phải Servlet namespace.

---

## 20. Migration checklist dành cho OAuth2/OIDC Resource Server

| Khu vực | Điều cần xác nhận |
|---|---|
| **Java runtime** | Build và production dùng JDK 17+ nếu chuyển sang Spring Boot 3. |
| **Spring Boot** | Version được chọn quản lý đúng Spring Framework/Security. |
| **Servlet namespace** | Custom filters, handlers, listeners dùng `jakarta.servlet`. |
| **Java SE namespace** | `javax.crypto`, `javax.net`, `javax.sql`, `javax.naming`, `javax.xml.parsers` vẫn đúng. |
| **Spring imports** | `org.springframework.*` không bị đổi thành `jakarta.*`. |
| **JWT API** | `JwtDecoder`, `Jwt`, validators vẫn dùng Spring Security packages. |
| **Opaque token** | `OpaqueTokenIntrospector` và dependencies tương thích. |
| **Custom filter** | Method signatures dùng Jakarta request/response/filter chain. |
| **Filter registration** | Không double-register; order đúng. |
| **Security configuration** | Dùng `SecurityFilterChain` và API tương thích Spring Security 6. |
| **Audience/issuer** | Validators vẫn giữ đúng trust policy sau khi đổi decoder/config. |
| **Servlet container** | Embedded/external container hỗ trợ Jakarta Servlet version cần thiết. |
| **WAR packaging** | Không đóng gói Servlet API sai version; provided scope đúng. |
| **Transitive dependencies** | Không còn legacy library yêu cầu javax Servlet API trên runtime path. |
| **Generated code** | Generator/plugin sinh Jakarta imports. |
| **Annotations** | Common Annotations, Validation, Persistence đổi đúng API; compiler APIs giữ nguyên. |
| **Descriptors** | web.xml/JSP/tag libraries phù hợp target container. |
| **Tests** | MockMvc và Spring Security Test được nâng tương thích. |
| **Filter flow** | Bearer header đi qua filter chain thực. |
| **Runtime** | Chạy trên target container thật hoặc cùng major/version. |
| **Observability** | Logs/traces không lộ token; auth failures và class loading được theo dõi. |
| **Rollback** | Artifact và config cũ còn khả năng rollback trong rollout window. |

---

## 21. Ví dụ end-to-end: Servlet Resource Server sau migration

Ví dụ cấu hình tổng thể:

```java
@Configuration
@EnableWebSecurity
public class ResourceServerConfiguration {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Nếu có custom filter:

```java
@Component
public class SecurityAuditFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        try {
            chain.doFilter(request, response);
        } finally {
            // Record a redacted event. Never record the raw token.
        }
    }
}
```

Các imports liên quan:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;
```

Trong migration này:

- Servlet method parameters chuyển sang Jakarta.
- Spring filter base class vẫn là Spring.
- Security configuration vẫn là Spring Security.
- JWT decoder và authorities vẫn dùng Spring Security types.
- Java cryptography/TLS imports vẫn là Java SE namespace.
- OAuth issuer, audience, scope và token validation policy phải được giữ nguyên theo thiết kế bảo mật.

Đây là mục tiêu của migration đúng phạm vi: thay đổi platform API boundary mà không vô tình làm thay đổi authorization semantics.

---

## 22. Kiểm tra behavior trước và sau migration

Namespace migration có thể làm application không khởi động, nhưng cũng có thể làm security behavior thay đổi nếu cấu hình bị chỉnh cùng lúc. Nên giữ bộ test behavior trước/sau để so sánh.

| Scenario | Kết quả mong đợi |
|---|---|
| Request public endpoint | Đúng policy public hiện tại. |
| Protected endpoint không có token | 401 hoặc entry point contract hiện tại. |
| JWT chữ ký sai | 401. |
| JWT issuer/audience sai | 401. |
| JWT hết hạn/not-before invalid | 401. |
| JWT hợp lệ, thiếu scope | 403. |
| JWT hợp lệ, đủ scope | Request được phép nếu object policy cũng cho phép. |
| Opaque token inactive | Authentication bị từ chối. |
| Request cross-tenant | Bị từ chối theo object/tenant policy. |
| Custom Servlet filter | Chạy đúng một lần theo dispatcher policy. |
| Custom authentication entry point | Response status/content type/body đúng contract. |
| Async/error dispatch | Không mất security context hoặc bypass filter policy. |

### 22.1. Không dùng migration để thay đổi policy ngoài ý muốn

Nếu trước migration endpoint yêu cầu `SCOPE_orders:write`, sau migration không nên vô tình chuyển thành `authenticated()` chỉ để test pass.

Nếu cần đổi authorization policy, ghi rõ thay đổi và test riêng. Điều đó giúp xác định regression do namespace, framework API hay security design.

---

## 23. Rollback và vận hành sau migration

### 23.1. Artifact và runtime phải rollback cùng nhau

Không rollback riêng ứng dụng nhưng giữ container Jakarta mới nếu artifact cũ chỉ hỗ trợ javax. Ngược lại, không deploy artifact Jakarta lên container Java EE cũ.

Một rollback unit nên bao gồm:

- Application artifact.
- Runtime/container version.
- JDK version.
- Relevant configuration.
- Secret/issuer/JWKS settings nếu có thay đổi.
- Database/schema changes nếu migration khác cũng được thực hiện.

### 23.2. Canary và telemetry

Theo dõi:

- Application startup/restart rate.
- ClassNotFound/NoClassDef/LinkageError.
- HTTP 401/403 distribution.
- JWT decoder/JWKS failures.
- Introspection latency/errors.
- Request latency và throughput.
- Custom filter invocation.
- Downstream failure rate.
- Servlet container thread/connection pools.

Một đợt 401 tăng sau migration có thể do issuer/audience config, filter chain, decoder bean hoặc clock/identity dependency. Không mặc định mọi 401 là namespace failure.

### 23.3. Gỡ bỏ legacy compatibility

Sau khi các service đã chuyển hoàn toàn:

- Loại dependency javax API không còn dùng.
- Xóa exclusion/workaround tạm.
- Xóa transformed artifacts nếu đã thay bằng vendor release.
- Cập nhật build/deployment docs.
- Ghi lại container/JDK baseline.
- Giữ tests cho dependency graph và runtime behavior.

---

## 24. Những hiểu lầm cần tránh

| Hiểu lầm | Thực tế |
|---|---|
| Mọi package `javax.*` đều đổi thành `jakarta.*`. | Java SE packages như crypto, net, sql, naming và nhiều XML APIs giữ nguyên. |
| Chỉ cần search-replace `javax` thành `jakarta`. | Có thể phá Java SE imports, strings, generated code và package không liên quan. |
| Spring Security packages cũng chuyển sang `jakarta.security`. | Spring APIs vẫn ở `org.springframework.security.*`. |
| Thêm `jakarta.servlet-api` sẽ làm thư viện javax chạy được. | Hai interface khác nhau; legacy bytecode cần được nâng hoặc chuyển đổi. |
| Tomcat 10 tự tương thích mọi ứng dụng Tomcat 9. | Servlet namespace thay đổi; legacy applications cần migration. |
| Chỉ cần đổi source imports. | Transitive JARs, agents, descriptors, generated source và test mocks cũng cần tương thích. |
| JWT/OIDC protocol thay đổi vì Servlet namespace. | OAuth2/OIDC protocol semantics không đổi chỉ vì package namespace của Servlet API đổi. |
| 401 sau migration luôn là decoder lỗi. | Có thể do filter chain, issuer/audience, wrong container, dependency hoặc token config. |
| `javax.transaction.xa` phải đổi cùng `javax.transaction`. | XA API thuộc Java SE và giữ namespace `javax.transaction.xa`. |
| `javax.xml.validation` đổi cùng `javax.validation`. | XML validation thuộc Java SE; Bean Validation API cũ mới chuyển namespace. |

---

## 25. Tài liệu kỹ thuật tham khảo

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): yêu cầu Java 17, Jakarta EE migration và các thay đổi nền tảng.
- [Spring Framework 6.0 Overview](https://docs.spring.io/spring-framework/reference/overview.html): baseline Java và Jakarta EE support.
- [Spring Security 6 Migration Guide](https://docs.spring.io/spring-security/reference/6.0/migration/index.html): các thay đổi API và cấu hình khi nâng Spring Security.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT Resource Server trên Servlet stack.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque token introspection.
- [Jakarta EE 9 Platform](https://jakarta.ee/specifications/platform/9/): namespace transition và platform specifications.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): Servlet API và compatibility.
- [Apache Tomcat Migration Guide — Tomcat 9 to 10](https://tomcat.apache.org/migration-10.html): khác biệt namespace khi chuyển Tomcat 9 sang Tomcat 10.
- [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration): công cụ transform ứng dụng legacy trong quá trình migration.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer): công cụ chuyển đổi Jakarta namespace trong artifacts.
- [Java SE API Documentation](https://docs.oracle.com/en/java/javase/): phân biệt các package Java SE còn thuộc namespace javax.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): phân tích dependency tree.
- [Gradle Dependency Insight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): tìm nguồn dependency cũ trong dependency graph.

**Kết luận:** Chuyển Servlet từ javax sang Jakarta là migration namespace ở cấp API và bytecode, thường đi cùng Spring Boot 3, Spring Framework 6 và Spring Security 6. Hãy đổi các Jakarta EE packages như `javax.crypto`, `javax.net`, `javax.sql`, `javax.naming`, `javax.xml.parsers` và `javax.transaction.xa`. Các package Java SE này giữ nguyên namespace; `javax.servlet` và các Jakarta EE APIs tương ứng mới chuyển sang `jakarta`. Các package Spring Security vẫn nằm trong `org.springframework.security`. Kiểm dependency transitives, generated code, filters, descriptors, tests và runtime container để bảo đảm toàn bộ ứng dụng dùng cùng Servlet contract. Migration chỉ hoàn tất khi API khởi động và OAuth2 authentication/authorization behavior vẫn đúng trên runtime Jakarta mục tiêu.
