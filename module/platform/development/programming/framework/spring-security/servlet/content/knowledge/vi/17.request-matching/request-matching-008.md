# Nhiều DispatcherServlet và yêu cầu cấu hình đường dẫn gốc chính xác

Khi ứng dụng Spring MVC Servlet có nhiều `DispatcherServlet`, mỗi Servlet có thể được đăng ký ở một URL prefix riêng và có `WebApplicationContext` chứa những controller/`HandlerMapping` khác nhau. Một `SecurityFilterChain` chọn sai đường dẫn hoặc một `MvcRequestMatcher` lấy nhầm `HandlerMappingIntrospector` có thể khiến endpoint được bảo vệ bằng rule không phù hợp.

Bài học này tập trung **RequestMatcher và servlet root**, không chỉ cách đặt `@GetMapping`. Phạm vi: Spring Security **Servlet**, Spring MVC, Java 17+, Spring Security 6.x. Ví dụ cố định Spring Boot 3.3.5 để học, không khẳng định đây là bản mới nhất hay còn hỗ trợ. Với các release mới, cần đọc API và migration notes của matcher trước khi cập nhật.

## 1. Servlet mapping khác Spring MVC controller mapping

Giả sử một `ServletContext` đăng ký hai servlet:

```text
catalogDispatcher -> /catalog/*
officeDispatcher  -> /office/*
default servlet   -> /           (nếu ứng dụng vẫn có)

GET /catalog/products -> catalogDispatcher -> @GetMapping("/products")
GET /office/report    -> officeDispatcher  -> @GetMapping("/report")
```

Servlet container chọn servlet trước; servlet được chọn mới tìm controller theo các MVC mappings trong context của nó. Một controller trong Catalog với `@GetMapping("/products")` không đương nhiên có full URL `/products`. Prefix `/catalog` đã được định nghĩa tại **Servlet registration**.

Một DispatcherServlet có thể có child `WebApplicationContext` riêng. Root context thấy shared services, nhưng không tự động đọc được mọi beans chỉ ở child context của các dispatcher khác. Do vậy, một `HandlerMappingIntrospector` từ root/Office context không thể mặc định đại diện cho Catalog controllers.

## 2. Phân biệt contextPath, servletPath, pathInfo và requestURI

Khi app triển khai dưới context path `/store` và Catalog servlet map `/catalog/*`, một request thông thường:

```text
GET /store/catalog/products/42?view=full

getContextPath() = "/store"
getServletPath() = "/catalog"
getPathInfo()    = "/products/42"
getRequestURI()  = "/store/catalog/products/42"
getQueryString() = "view=full"
```

| Thuộc tính | Ý nghĩa | Lỗi dễ gặp |
|---|---|---|
| `contextPath` | Đường dẫn gốc của web application | Cộng nhầm `/store` vào matcher vốn xét path trong app |
| `servletPath` | Phần path do container dùng để chọn Servlet | Nghĩ nó bằng `/products/42` dù mapping là `/catalog/*` |
| `pathInfo` | Phần còn lại với Servlet prefix mapping | Quên trường này có thể là `null` với mapping kiểu khác |
| `requestURI` | URI path thường gồm contextPath | Lấy chuỗi thô rồi so với MVC-relative route |
| MVC mapping | Đường dẫn handler xử lý bên trong servlet | Coi `@GetMapping("/products")` là full URL ngoài |

Đây là ví dụ với **prefix mapping**. Default mapping `/`, exact mapping hoặc extension mapping có thể phân chia `servletPath/pathInfo` khác. Không sửa security logic bằng cách suy đoán một kiểu mapping từ URL ngoài.

## 3. securityMatcher và requestMatchers là hai quyết định khác nhau

`FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp** request, theo order. Sau đó `AuthorizationFilter` dùng các `requestMatchers` bên trong chain đó để chọn quyền. Rule của chain không được chọn hoàn toàn không có hiệu lực.

```text
GET /office/report
    |
FilterChainProxy
    |
catalogChain.securityMatcher(...) -> false
officeChain.securityMatcher(...)  -> true
    |
officeChain.authorizeHttpRequests(...)
    |
GET /office/report -> hasRole("ADMIN")
```

Một sai lầm phổ biến:

```java
// Có thể KHÔNG chọn chain khi URL thật là /catalog/products/42.
http.securityMatcher("/products/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/products/**").authenticated()
        .anyRequest().denyAll());
```

Đặt rule `hasRole("ADMIN")` trong chain không match sẽ không cứu được request. Nếu không có fallback chain, URL không khớp chain nào có nguy cơ nằm ngoài Spring Security. Vì vậy cần test **cấp chain** và **cấp authorization**, không chỉ role tại controller.

## 4. MVC-aware matcher cần đúng MVC context và servletPath

`MvcRequestMatcher` có thể dùng `HandlerMappingIntrospector` để khớp path theo Spring MVC. Với prefix Servlet mapping:

```java
MvcRequestMatcher.Builder catalogBuilder =
    new MvcRequestMatcher.Builder(catalogIntrospector)
        .servletPath("/catalog");

MvcRequestMatcher getProduct =
    catalogBuilder.pattern(HttpMethod.GET, "/products/{id}");
```

Đây là **mảnh code minh họa**, không phải class chạy độc lập. Biến `catalogIntrospector` cần được kết nối với **MVC context của catalogDispatcher**, không lấy tùy tiện từ office hoặc root. `/catalog` là servletPath, `/products/{id}` là MVC-relative path và `/store` (context path) không được thêm vào đây.

Với nhiều Servlet (cả servlet không phải MVC), một lời gọi `requestMatchers(String...)` đôi lúc không đủ để Spring Security tự chọn matcher đúng; một số version có thể từ chối cấu hình mơ hồ ngay khi startup. Không khắc phục bằng `permitAll("/**")`. Chọn matcher tường minh và test. Với các version mới hơn, xem `PathPatternRequestMatcher` và builder base path nếu API có sẵn. Không copy class/version mới vào Boot phiên bản cũ rồi giả định có thể biên dịch.

Nếu không thể bảo đảm introspector đúng child context, dùng matcher dựa trên Servlet API ở tầng root là một lựa chọn đơn giản và kiểm chứng được:

```java
RequestMatcher catalog = request ->
    "/catalog".equals(request.getServletPath());

RequestMatcher catalogRead = request ->
    "/catalog".equals(request.getServletPath())
    && "/products".equals(request.getPathInfo())
    && "GET".equals(request.getMethod());
```

Cách này **chỉ đúng cho prefix Servlet mapping đã xác minh**; không nên thay bằng `startsWith("/catalog")` vì có thể match nhầm `/catalogue`. Với routes biến động, nhiều path variables, URL aliases hoặc một default Servlet, nên dùng matcher framework phù hợp và test toàn bộ phạm vi.

## 5. Quy tắc cấu hình nhiều DispatcherServlet

- Xác định rõ mọi `ServletRegistrationBean`, tên Servlet, mapping `/catalog/*`/`/office/*` và default servlet.
- Xác định Security config nằm ở root hay MVC child context; không suy ra rằng root `HandlerMappingIntrospector` biết tất cả child routes.
- Với nhiều `SecurityFilterChain`, đặt `@Order(1)` cho chain cụ thể và **fallback denyAll** sau các chain đặc thù; không đặt chain `/**` lên đầu.
- Trong từng chain, matcher method/path cụ thể trước, `anyRequest().denyAll()` ở cuối. Không dựa vào 404/405 hiện tại để làm policy.
- Nếu chỉ muốn bảo vệ MVC route dưới `/catalog/*`, hãy kiểm tra cả `servletPath` và `pathInfo` phù hợp; nếu match cả servlet root, security rule không nên mở rộng quyền ngoài ý muốn.
- `HEAD` không tự được cấp quyền chỉ vì MVC GET handler có thể phục vụ HEAD. `OPTIONS` cần CORS preflight đúng policy; không mở `permitAll("/**")` để né CORS.
- Với browser cookie/session và HTTP Basic, xét CSRF theo trust boundary thực tế; 403 do CSRF khác 403 do thiếu role.
- Nếu proxy strip `/app`, server có thể không nhìn thấy prefix đó. Không lấy client-supplied forwarded headers làm authorization source; cần cấu hình trusted proxy và kiểm tra effective Servlet path.
- Không tự parse URL encoded slash, double slash, dấu `..` hoặc dấu `;` bằng substring để thay thế `HttpFirewall`/MVC path matching.

## 6. Ví dụ chạy được với Java 17+ và **hai DispatcherServlet thật**

Dự án dùng Spring Boot 3.3.5 / Spring Security do Boot quản lý và Maven. Catalog servlet đăng ký `/catalog/*`, Office servlet `/office/*`. Root Spring Security config dùng **RequestMatcher lambda** để xác định servletPath và route, tránh tự suy đoán MVC context. HTTP Basic chỉ để kiểm thử trạng thái 401/403. Ví dụ có 2 user giả, không dùng credentials này ngoài localhost/HTTPS test.

### 6.1. Cấu trúc

```text
multi-servlet-security/
├── pom.xml
└── src/
    ├── main/java/
    │   ├── demo/main/
    │   │   ├── App.java
    │   │   ├── ServletRegistrations.java
    │   │   └── SecurityConfig.java
    │   └── demo/child/
    │       ├── catalog/CatalogMvc.java
    │       └── office/OfficeMvc.java
    └── test/java/demo/main/MultiServletTest.java
```

Hai MVC config nằm ở `demo.child.*` **ngoài package scan của root** `demo.main`, nên không bị Boot vô tình đăng ký controller vào default DispatcherServlet.

### 6.2. pom.xml

```xml
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
    <groupId>demo</groupId>
    <artifactId>multi-servlet-security</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
```

### 6.3. Spring Boot main

`src/main/java/demo/main/App.java`:

```java
package demo.main;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class App {
    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
```

### 6.4. Servlet registrations

`src/main/java/demo/main/ServletRegistrations.java`:

```java
package demo.main;

import demo.child.catalog.CatalogMvc;
import demo.child.office.OfficeMvc;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.DispatcherServlet;

@Configuration
public class ServletRegistrations {

    @Bean
    ServletRegistrationBean<DispatcherServlet> catalogServlet() {
        AnnotationConfigWebApplicationContext ctx =
            new AnnotationConfigWebApplicationContext();
        ctx.register(CatalogMvc.class);
        ServletRegistrationBean<DispatcherServlet> bean =
            new ServletRegistrationBean<>(
                new DispatcherServlet(ctx), "/catalog/*");
        bean.setName("catalogDispatcher");
        bean.setLoadOnStartup(1);
        return bean;
    }

    @Bean
    ServletRegistrationBean<DispatcherServlet> officeServlet() {
        AnnotationConfigWebApplicationContext ctx =
            new AnnotationConfigWebApplicationContext();
        ctx.register(OfficeMvc.class);
        ServletRegistrationBean<DispatcherServlet> bean =
            new ServletRegistrationBean<>(
                new DispatcherServlet(ctx), "/office/*");
        bean.setName("officeDispatcher");
        bean.setLoadOnStartup(1);
        return bean;
    }
}
```

Mỗi `DispatcherServlet` nhận một `AnnotationConfigWebApplicationContext` riêng. Servlet registration áp prefix ở container; MVC controller trong context con dùng đường dẫn tương đối với Servlet mapping.

### 6.5. Catalog MVC context

`src/main/java/demo/child/catalog/CatalogMvc.java`:

```java
package demo.child.catalog;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class CatalogMvc {

    @Bean
    CatalogController catalogController() {
        return new CatalogController();
    }

    @RestController
    public static class CatalogController {
        @GetMapping("/products")
        public String products(HttpServletRequest request) {
            return "CATALOG:" + request.getServletPath()
                + ":" + request.getPathInfo();
        }
    }
}
```

### 6.6. Office MVC context

`src/main/java/demo/child/office/OfficeMvc.java`:

```java
package demo.child.office;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class OfficeMvc {

    @Bean
    OfficeController officeController() {
        return new OfficeController();
    }

    @RestController
    public static class OfficeController {
        @GetMapping("/report")
        public String report(HttpServletRequest request) {
            return "OFFICE:" + request.getServletPath()
                + ":" + request.getPathInfo();
        }
    }
}
```

Controller trả đường dẫn Servlet thực để test. Không để lộ thông tin định tuyến nội bộ không cần thiết trong response production.

### 6.7. SecurityConfig

`src/main/java/demo/main/SecurityConfig.java`:

```java
package demo.main;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfig {

    private static RequestMatcher servlet(String path) {
        return request -> path.equals(request.getServletPath());
    }

    private static RequestMatcher route(
            String servletPath, String pathInfo, String method) {
        return request ->
            servletPath.equals(request.getServletPath())
                && pathInfo.equals(request.getPathInfo())
                && method.equals(request.getMethod());
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-demo"))
                .roles("VIEWER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-demo"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain catalogChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(servlet("/catalog"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(route("/catalog", "/products", "GET"))
                    .hasAnyRole("VIEWER", "ADMIN")
                .requestMatchers(route("/catalog", "/products", "HEAD"))
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain officeChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(servlet("/office"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(route("/office", "/report", "GET"))
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Giải thích:

1. Chain Catalog chỉ được chọn khi Servlet API báo `servletPath=/catalog`, Office khi `/office`. Với kiểu mapping khác, phải thay logic.
2. Authorization so **cả** `servletPath`, `pathInfo` và HTTP method; những request không được khai báo rơi vào `denyAll()`.
3. Viewer được GET Catalog nhưng không GET Office. Admin được GET Office và HEAD Catalog. GET không tự cấp HEAD.
4. Fallback chain ở cuối chặn các URL không thuộc hai servlets. Đặt fallback trước sẽ che rule đặc thù.
5. `httpBasic` tạo response 401 khi thiếu/sai credentials. CSRF không bị tắt; example dùng GET/HEAD, không có thao tác ghi dữ liệu.
6. Mật khẩu ví dụ được hash bằng BCrypt. HTTP Basic truyền credential theo request nên phải dùng HTTPS trong môi trường thực; tài khoản demo không được đưa lên production.

### 6.8. Integration tests trên embedded Servlet container

`src/test/java/demo/main/MultiServletTest.java`:

```java
package demo.main;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MultiServletTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void anonymousNeedsAuthentication() {
        assertThat(http.getForEntity("/catalog/products", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void viewerHitsTheCorrectCatalogServlet() {
        ResponseEntity<String> r = http.withBasicAuth("viewer", "viewer-demo")
            .getForEntity("/catalog/products", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo("CATALOG:/catalog:/products");
    }

    @Test
    void viewerCannotUseOfficeChain() {
        assertThat(http.withBasicAuth("viewer", "viewer-demo")
            .getForEntity("/office/report", String.class).getStatusCode())
            .isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void adminHitsTheCorrectOfficeServlet() {
        ResponseEntity<String> r = http.withBasicAuth("admin", "admin-demo")
            .getForEntity("/office/report", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo("OFFICE:/office:/report");
    }

    @Test
    void headIsNotSilentlyGrantedByGetRule() {
        ResponseEntity<String> viewer =
            http.withBasicAuth("viewer", "viewer-demo").exchange(
                "/catalog/products", HttpMethod.HEAD,
                HttpEntity.EMPTY, String.class);

        ResponseEntity<String> admin =
            http.withBasicAuth("admin", "admin-demo").exchange(
                "/catalog/products", HttpMethod.HEAD,
                HttpEntity.EMPTY, String.class);

        assertThat(viewer.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(admin.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void otherPathsAndServeltsAreDenied() {
        TestRestTemplate admin = http.withBasicAuth("admin", "admin-demo");
        assertThat(admin.getForEntity("/catalog/report", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(admin.getForEntity("/office/products", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(admin.getForEntity("/unmapped/report", String.class)
            .getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void invalidPasswordIsRejected() {
        assertThat(http.withBasicAuth("viewer", "wrong-password")
            .getForEntity("/catalog/products", String.class).getStatusCode())
            .isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
```

**Kỳ vọng:** 7 test pass nếu các file được đặt đúng, embedded Servlet container khởi động được và Maven dependencies được resolve. Kết quả **chưa được chạy trong bài viết này**; đó là assertions cần người học thực thi. Test dùng `RANDOM_PORT` để kiểm tra Servlet mapping/container thực, không chỉ một `MockMvc` gắn với default DispatcherServlet.

Test xác minh cả ranh giới đường dẫn và HTTP method: GET Catalog đúng role, Office riêng, unknown URL bị denyAll, HEAD không tự ăn theo GET. Việc controller trả `CATALOG:/catalog:/products` hoặc `OFFICE:/office:/report` là bằng chứng về phân tách `servletPath`/`pathInfo` theo Servlet prefix mappings đã đăng ký.

Chạy trong thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Khi server phát triển chạy cổng 8080 nếu còn rảnh:

```bash
curl -i http://localhost:8080/catalog/products
curl -i -u viewer:viewer-demo http://localhost:8080/catalog/products
curl -i -u viewer:viewer-demo http://localhost:8080/office/report
curl -i -u admin:admin-demo http://localhost:8080/office/report
```

Dự kiến trạng thái: `401`, `200` cùng body `CATALOG:/catalog:/products`, `403`, và `200` cùng body `OFFICE:/office:/report`. Không sử dụng fixture password trong môi trường công khai hoặc shell history chứa credential thật.

## 7. Kiểm tra non-root context path và reverse proxy

Nếu cấu hình:

```properties
server.servlet.context-path=/store
```

thì URL bên ngoài chuyển thành `/store/catalog/products` và `/store/office/report`. Với prefix mappings nêu trên, Servlet API thường vẫn trả:

```text
contextPath = "/store"
servletPath = "/catalog" hoặc "/office"
pathInfo   = "/products" hoặc "/report"
```

Do đó **không** sửa matcher `servlet("/catalog")` thành `servlet("/store/catalog")`. Muốn kiểm thử context path khác root, dùng profile test riêng và gửi request có thêm `/store` trong URL; không chạy nguyên một bài test root path với URL sai rồi kết luận matcher có lỗi.

Nếu reverse proxy có URL ngoài `/app/catalog/products` nhưng strip `/app` trước khi chuyển cho Tomcat, Servlet container có thể chỉ thấy `/catalog/products`. Nếu proxy không strip, context path phải được cấu hình tương ứng. Forwarded headers có thể hữu ích cho redirect/link generation nhưng cần trust boundary; đừng tin header client tự khai để quyết định authorization.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
|---|---|---|
| MVC controller tồn tại nhưng request trả 403 | Authorization chain match sai root hoặc denyAll | Log an toàn chain được chọn; test servletPath/pathInfo |
| Rule ADMIN không hoạt động | Chain khác match trước, hoặc route matcher sai | Kiểm tra `@Order` và cả hai cấp matcher |
| URL không thuộc servlet nào vẫn trả 200 | Không có fallback chain hoặc Servlet Filter registration thiếu phạm vi | Test unknown URL và default servlet |
| Server startup báo matcher không rõ MVC/Servlet | Nhiều servlet làm auto matcher mơ hồ | Chọn matcher loại rõ ràng, cấu hình đúng servletPath |
| Đổi context path làm endpoints không truy cập | Matcher cộng contextPath sai hoặc client gọi URL cũ | Phân biệt contextPath với servletPath |
| Cùng pathInfo nhưng khác servlet có role không đúng | Không xét servletPath | Test `/catalog/report` và `/office/report` độc lập |
| HEAD khác GET | Security rule có method riêng | Test HEAD rõ ràng thay vì suy từ GET |
| POST trả 403 dù role đúng | Có thể thiếu CSRF token | Giữ CSRF và test quyền với token hợp lệ |
| Redirect sai host/path sau proxy | Forwarded headers, context path hoặc proxy rewrite sai | Kiểm tra cấu hình proxy và effective request path |
| Role đúng nhưng xem dữ liệu tenant khác | Chỉ bảo vệ URL mà thiếu object-level authorization | Kiểm tra quyền ở service/resource |
| Test MockMvc pass nhưng real deployment lỗi | Không mô phỏng child Servlet registration | Chạy integration test qua container thật |

**Không biến lỗi route thành lý do tắt CSRF, firewall hoặc authorization.** Khi cần quan sát, bật log `org.springframework.security` ở mức DEBUG trong môi trường phát triển nhưng không ghi raw password, cookie, session ID hay Authorization headers.

## 9. Checklist và câu hỏi tự kiểm tra

- [ ] Liệt kê mọi DispatcherServlet, name, mapping, MVC context và Servlet Filter registration.
- [ ] Xác nhận giá trị contextPath/servletPath/pathInfo ở request thực tế.
- [ ] Chọn đúng `MvcRequestMatcher` cùng introspector của MVC context, hoặc matcher Servlet-level tường minh.
- [ ] Kiểm tra `securityMatcher` và `requestMatchers` riêng biệt.
- [ ] Chain đặc thù đứng trước fallback; rule không khai báo được denyAll.
- [ ] Test cùng pathInfo nhưng khác Servlet prefix và các HTTP methods khác nhau.
- [ ] Có test unknown URL, non-root context path, proxy rewrite và dispatcher types nếu ứng dụng dùng.
- [ ] CSRF/CORS và resource-level authorization được kiểm tra độc lập với URL matching.
- [ ] Integration tests sử dụng embedded Servlet container để xác minh Servlet mappings thật.

**Câu 1.** Với `/store/catalog/products`, app context path `/store` và Servlet mapping `/catalog/*`, servletPath bằng gì?  
**Đáp án:** Thông thường `/catalog`; pathInfo là `/products`.

**Câu 2.** `MvcRequestMatcher.Builder.servletPath("/catalog")` có cần cộng `/store` không?  
**Đáp án:** Không. `/store` là contextPath của application.

**Câu 3.** Vì sao `getRequestURI().startsWith("/products")` dễ sai?  
**Đáp án:** URI có thể chứa contextPath và servlet prefix, khác MVC-relative path.

**Câu 4.** Nếu `securityMatcher` không khớp nhưng `authorizeHttpRequests` có `hasRole("ADMIN")` thì sao?  
**Đáp án:** Rule trong chain không được chọn sẽ không chạy.

**Câu 5.** Vì sao root `HandlerMappingIntrospector` không mặc nhiên dùng cho mọi DispatcherServlet?  
**Đáp án:** Mỗi servlet có thể có child MVC context và handler mappings riêng.

**Câu 6.** Vì sao cần fallback denyAll?  
**Đáp án:** Để URL ở default/servlet khác không vô tình nằm ngoài các SecurityFilterChain đã định nghĩa.

**Kết luận:** Với **nhiều DispatcherServlet**, cần biết rõ **Servlet registration mapping**, **MVC-relative controller path** và **Security RequestMatcher đang đối chiếu phần nào của URL**. Cấu hình servletPath đúng, dùng introspector thuộc MVC context phù hợp khi cần, đặt chains đúng thứ tự và kiểm thử request thật qua container — đó là nền tảng để tránh bảo vệ nhầm hoặc bỏ sót endpoint.