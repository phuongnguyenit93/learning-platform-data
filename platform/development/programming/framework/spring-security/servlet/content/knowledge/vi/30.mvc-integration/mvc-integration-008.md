# Bảo vệ đường dẫn tải tệp, tài nguyên tĩnh và view chuyển tiếp trong Spring Security Servlet + Spring MVC

## 1. Mục tiêu và tình huống thực tế

Một ứng dụng Spring MVC có ba kiểu đường dẫn:

- `/assets/app.css`, `/assets/logo.svg`: tài nguyên tĩnh **công khai** để trang đăng nhập và giao diện hoạt động.
- `/api/files/{id}/download`: tài liệu của **một người dùng hoặc tổ chức cụ thể**, chỉ được tải khi đã xác thực **và** sở hữu/có quyền đọc tài liệu.
- `/reports/summary` trả `forward:/internal/report-view`: một URL điều hướng nội bộ tới một handler/view khác, vẫn có thể xử lý dữ liệu nhạy cảm.

Sai lầm thường thấy là cho phép mọi `GET`, mọi `/static/**`, hoặc mọi `DispatcherType.FORWARD` rồi tin rằng MVC controller đã đủ an toàn. Thực tế có nhiều lớp cần kiểm soát độc lập: **Spring Security URL authorization**, **MVC handler/resource mapping**, **object-level authorization**, **Servlet dispatcher types**, **filesystem/storage boundary** và **HTTP response headers/cache**.

Một nguyên tắc xuyên suốt bài học:

> **Đường dẫn có thể truy cập từ browser không quyết định dữ liệu có công khai hay không. Chỉ những tài nguyên được phân loại công khai mới được `permitAll()`; tài liệu riêng phải kiểm quyền ở cả URL lẫn đối tượng, và view chuyển tiếp không được tạo lối đi vòng qua authorization.**

Bài hướng tới **Spring Security 6, Spring Boot 3.3.5, Java 17 và Servlet stack**. Các đoạn code đều được đánh dấu là file hoàn chỉnh hoặc mảnh minh họa; phần demo dùng HTTP Basic và dữ liệu trong bộ nhớ để dễ quan sát, không phải hệ thống lưu trữ tài liệu production.

## 2. Một request đi qua những thành phần nào?

Trong ứng dụng Servlet, request đi qua **filter chain** trước khi Spring MVC chọn controller hay static resource handler:

~~~text
Browser
  |
  | GET /api/files/alice-budget/download
  v
Servlet container
  |
  v
DelegatingFilterProxy
  |
  v
Spring Security FilterChainProxy / SecurityFilterChain
  |-- SecurityContext
  |-- Authentication (nếu cần)
  |-- AuthorizationFilter (quy tắc đường dẫn)
  |
  v
DispatcherServlet (Spring MVC)
  |
  +-- RequestMappingHandlerMapping -> @Controller/@RestController
  |                                    -> kiểm quyền sở hữu tài liệu
  |                                    -> trả ResponseEntity<Resource>
  |
  +-- ResourceHandlerMapping -> ResourceHttpRequestHandler
  |                            -> ảnh, CSS, JavaScript công khai
  |
  +-- ViewResolver -> JSP/Thymeleaf/InternalResourceView
                               -> có thể phát sinh FORWARD
~~~

Không nên mặc định rằng `ResourceHttpRequestHandler` chỉ xử lý tài nguyên an toàn; **nó xử lý những gì bạn đưa vào các thư mục hoặc location đã map**. Nếu tài liệu riêng nằm trong đường dẫn tĩnh công khai, một người không có quyền có thể tải nó mà không cần đi qua controller kiểm ownership.

`authorizeHttpRequests` có thể cho phép/từ chối URL trước MVC. Nhưng nó chỉ là lớp đầu tiên: hai tài liệu cùng nằm dưới `/api/files/**` không tự động có cùng chủ sở hữu. Vì thế `hasRole("FILE_READER")` vẫn chưa đủ để bảo vệ `/api/files/bob-budget/download` khỏi người dùng Alice nếu Alice cũng có role FILE_READER.

## 3. Phân loại URL trước khi viết request matcher

Bắt đầu bằng **bảng phân loại rõ ràng**, không phải một `permitAll("/**")` rồi thêm ngoại lệ khi phát sinh lỗi.

| Đường dẫn | Loại | Quyết định bảo mật hợp lý |
| --- | --- | --- |
| `/assets/**` | CSS/JS/ảnh đã kiểm kê, thật sự công khai | `permitAll()` nhưng vẫn cho request qua Spring Security filter chain |
| `/api/files/{id}/download` | Tệp riêng, do ứng dụng quản lý | Xác thực + role tối thiểu + **object-level ownership/ACL** |
| `/reports/**` | Endpoint báo cáo nhạy cảm | Role/phân quyền nghiệp vụ, không chỉ authenticated |
| `/internal/report-view` | Handler/view đích của `forward:` | Bảo vệ cả đường dẫn đích và/hoặc method-level check |
| `/error` | Trang/lời đáp lỗi không bí mật | Có thể cho phép để tránh lỗi lồng nhau, nhưng không tiết lộ dữ liệu |
| `/login` | Trang đăng nhập của ứng dụng | Cho phép truy cập trước khi login, giữ CSRF khi submit |
| `/admin/**`, `/private/**` | Endpoint/tài nguyên nhạy cảm | Role cụ thể hoặc `denyAll()` nếu không có route hợp lệ |
| URL chưa được khai báo | Không có nhu cầu công khai | Mặc định `denyAll()` |

**`permitAll()` không đồng nghĩa “bỏ Spring Security filter”.** Với `permitAll()`, request vẫn qua filter chain theo cấu hình hiện tại; các security headers và thành phần khác vẫn có cơ hội hoạt động. Ngược lại, `web.ignoring()` hoặc loại trừ filter chain có thể bỏ qua các kiểm soát này, nên thường **không cần** chỉ để tăng tốc static resources.

Đừng nghĩ file được đặt ở thư mục tên `private` thì tự có quyền truy cập. Quy tắc phải dựa trên **vị trí thực tế được Spring MVC/web server/CDN phục vụ**, cộng với khả năng truy cập qua mọi đường dẫn/alias khác.

## 4. Tài nguyên tĩnh trong Spring Boot: đâu là công khai?

Spring Boot MVC thường tìm static resources theo các location classpath mặc định như `/static`, `/public`, `/resources`, `/META-INF/resources`; tùy cấu hình, URL công khai có thể được ánh xạ qua `/**`. Ví dụ nếu đưa `salary.csv` vào `src/main/resources/static`, **đây không phải nơi lưu file bí mật**, kể cả khi bạn kỳ vọng controller sẽ kiểm tra quyền tại `/api/files/**`: file có thể được phục vụ dưới một URL khác.

Nên tách rõ:

~~~text
src/main/resources/
  public-assets/
    app.css                 <- được expose qua /assets/**
  templates/
    login.html              <- template server render, không phải static public
  private-documents/
    internal-note.txt       <- không map tĩnh, chỉ là ví dụ phân loại

/srv/application/private-files/
  ...                       <- lưu bên ngoài web root; chỉ truy cập qua controller
~~~

Ứng dụng demo sẽ **tắt mapping mặc định của Spring Boot** rồi khai báo mapping hẹp `/assets/**`. Điều đó làm rõ đâu là public assets; không bắt buộc mọi dự án đều phải làm như vậy nếu đã kiểm soát cấu hình mặc định và nội dung các location.

~~~properties
# application.properties
spring.web.resources.add-mappings=false
spring.security.filter.dispatcher-types=request,async,error,forward
server.error.include-message=never
~~~

Ở đây `spring.web.resources.add-mappings=false` loại bỏ auto-registration của static mappings do Boot tạo; mapping do `WebMvcConfigurer` tự đăng ký vẫn được giữ. Property `spring.security.filter.dispatcher-types` khai báo những Servlet dispatcher types mà **Spring Security filter** được đăng ký xử lý trong ví dụ, bao gồm `FORWARD`. Tính năng forwarding còn chịu sự chi phối của container, filter registration và cấu hình triển khai thực tế; cần kiểm tra nó bằng integration test trên container nếu ứng dụng phụ thuộc vào việc kiểm soát dispatch lần hai.

Một `WebMvcConfigurer` có thể khai báo thư mục được phép phục vụ:

~~~java
@Bean
WebMvcConfigurer publicResources() {
    return new WebMvcConfigurer() {
        @Override
        public void addResourceHandlers(
                ResourceHandlerRegistry registry) {
            registry.addResourceHandler("/assets/**")
                    .addResourceLocations("classpath:/public-assets/");
        }
    };
}
~~~

Đây là **mảnh Java nằm trong Spring Configuration class**, chưa phải chương trình riêng. `ResourceHttpRequestHandler` chịu trách nhiệm phục vụ tài nguyên tại location đó. **Không** thêm `file:/srv/application/private-files/` vào một mapping `permitAll()`: làm vậy sẽ biến tệp riêng thành static public resource.

Các assets public vẫn cần quản trị nguồn: không trộn upload của người dùng vào cùng thư mục, cấu hình content type và security headers phù hợp, kiểm phiên bản/cache khi phát hành. Một file SVG/HTML/JavaScript không đáng tin có thể tạo rủi ro XSS nếu được phục vụ từ cùng origin với ứng dụng; không chỉ đánh giá theo việc “đó là tệp tĩnh”.

## 5. Tải tệp riêng: authentication, authorization và IDOR

Một URL `GET /api/files/{id}/download` có thể có ba lớp kiểm tra:

1. **Identity:** người gọi đã xác thực hay chưa? Ví dụ HTTP Basic/session xác nhận Alice.
2. **Coarse authorization:** người gọi có quyền dùng tính năng download? Ví dụ `ROLE_FILE_READER`.
3. **Object-level authorization:** tài liệu với `id` đó có thuộc Alice hoặc một tenant/nhóm mà Alice có quyền truy cập không?

Nếu thiếu bước 3, chỉ cần đoán ID hoặc thay `id` trong URL có thể tạo lỗi **Insecure Direct Object Reference (IDOR)** / Broken Object Level Authorization (BOLA).

Ví dụ:

~~~http
GET /api/files/alice-budget/download HTTP/1.1
Authorization: Basic <credential-example>
~~~

Alice có role `FILE_READER`, và file `alice-budget` thuộc Alice: có thể trả 200. Nhưng với cùng credentials:

~~~http
GET /api/files/bob-budget/download HTTP/1.1
Authorization: Basic <credential-example>
~~~

Server phải từ chối. Trong ví dụ sẽ trả **404 Not Found** cho cả file không tồn tại lẫn file tồn tại nhưng không thuộc chủ tài khoản; ứng dụng thật cũng có thể chọn 403 tùy chính sách, nhưng tránh biến thông báo lỗi thành công cụ dò ID/tên tài liệu của người khác.

**Không dùng đường dẫn file do client gửi làm quyền.** Ví dụ nguy hiểm:

~~~java
// KHÔNG an toàn: input do client kiểm soát có thể chứa ../
Path requested = Path.of("/srv/private").resolve(filenameFromUrl);
return new FileSystemResource(requested);
~~~

Một request như `/download?name=../../secrets/config.yml`, URL-encoded traversal hoặc symlink có thể khiến backend đọc ngoài vùng dự kiến. Cách tốt hơn:

- Request chỉ gửi một **opaque document ID** (thường UUID, không chứa đường dẫn).
- Server lookup metadata của ID đó từ database; metadata chứa owner/tenant, visibility, trạng thái, storage key.
- Kiểm ACL/ownership từ chính metadata đã xác minh với người dùng hiện tại.
- Lấy nội dung từ storage bằng **storage key do server quản lý**, không chuyển trực tiếp filename/URL của client thành `Path`.
- Nếu buộc phải dùng filesystem, kiểm real path và root (kể cả symlink), tránh race TOCTOU và phân quyền OS. Dùng object storage chuyên biệt và key được quản lý bởi ứng dụng khi phù hợp.

UUID không thay authorization. ID khó đoán giúp giảm khả năng liệt kê nhưng không bảo vệ nếu URL bị lộ từ log, email hoặc browser history.

## 6. Response của file download cũng là bề mặt bảo mật

Sau khi vượt qua authorization, response cần được kiểm soát:

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="alice-budget.txt"
Cache-Control: no-store
X-Content-Type-Options: nosniff

Private data...
~~~

`Content-Disposition: attachment` gợi ý browser **tải xuống** thay vì render inline; `filename` phải được tạo bằng API escape/encode của thư viện HTTP, không nối string từ input không tin cậy. `application/octet-stream` phù hợp với tệp download tổng quát; nếu cần preview PDF/ảnh an toàn, thiết kế route/headers khác.

`Cache-Control: no-store` hạn chế lưu cache nhạy cảm ở browser/proxy; với CDN, phải cấu hình thêm không cache nhầm tài nguyên riêng. `X-Content-Type-Options: nosniff` giúp giảm một số tình huống browser suy diễn content type không đúng. Đừng chỉ dựa vào header để xử lý nội dung HTML/SVG không đáng tin: xem xét **origin riêng cho user-generated content**, quét malware, hạn chế content type, không cho thực thi và không phục vụ upload từ public web root.

**Không trả `ResponseEntity<Resource>` mà bỏ kiểm ownership**, không gửi redirect tới một storage URL công khai dài hạn. Với object storage, một **presigned URL** là bearer credential: bất kỳ ai có URL trong thời gian nó còn hiệu lực có thể tải nội dung, nên phải kiểm quyền trước khi cấp, đặt thời hạn ngắn phù hợp, giới hạn thao tác và hiểu rằng URL có hạn **không tự động là URL dùng một lần**.

Lưu ý `HEAD`, `Range`, cache revalidation và file preview có thể được dùng để truy cập nội dung. Nếu hệ thống hỗ trợ chúng, áp dụng cùng quy tắc xác thực/ownership; không chỉ bảo vệ `GET` trong một handler rồi để một static mapping khác phục vụ file tương tự.

## 7. View forwarding khác redirect: cần bảo vệ cả đích

Trong Spring MVC, một controller có thể trả về:

~~~java
return "forward:/internal/report-view";
~~~

Đây là **server-side forward** qua Servlet `RequestDispatcher`, không phải browser tự gọi URL mới. Nó tạo một lượt dispatch tới đường dẫn đích bên trong server. Ngược lại:

~~~java
return "redirect:/reports/home";
~~~

`redirect:` trả HTTP 3xx, browser thực hiện **request mới** tới URL đích; security filter cho request mới sẽ chạy theo đăng ký bình thường. Một template được render trực tiếp (như `return "dashboard"` với Thymeleaf) lại không nhất thiết sinh ra request Servlet mới. Phải xác định ứng dụng đang dùng cơ chế nào.

### 7.1. Vì sao FORWARD có thể tạo lỗ hổng?

Giả sử `/reports/summary` yêu cầu `ROLE_ANALYST`, sau đó forward tới `/internal/report-view`. Nếu chỉ đường dẫn nguồn được bảo vệ, một request trực tiếp đến `/internal/report-view` có thể vượt qua kiểm soát nếu URL đích được cho phép rộng.

Với Servlet, `DispatcherType` thường gồm `REQUEST`, `FORWARD`, `INCLUDE`, `ERROR` và `ASYNC`. Spring Security `AuthorizationFilter` có thể đánh giá những dispatcher được filter registration chuyển vào Security chain; nếu một dispatcher type không được đăng ký cho Spring Security filter, **không nên suy đoán rằng filter sẽ luôn chạy lại** trên dispatch đó.

Cách phòng vệ nhiều lớp:

- Bảo vệ **URL nguồn** (`/reports/**`) để chỉ người đủ quyền khởi tạo báo cáo.
- Bảo vệ **URL đích** (`/internal/**`) nếu có thể được truy cập trực tiếp.
- Với handler xử lý dữ liệu nhạy cảm ở đích, thêm **method-level authorization** hoặc service-level ACL, không phụ thuộc hoàn toàn vào việc FORWARD được filter lại.
- Nếu đường đích chỉ nên được gọi bằng forward, kiểm **`DispatcherType.FORWARD`** tại handler đích để chặn request trực tiếp. Đây là điều kiện bổ sung, **không thay thế role check**.
- Kiểm hiệu lực bằng test thực tế của container có cấu hình dispatcher types tương ứng.

### 7.2. Không `permitAll(FORWARD)` vô điều kiện khi có dữ liệu nhạy cảm

Bạn có thể bắt gặp cấu hình:

~~~java
// Mảnh code có thể phù hợp trong một số ứng dụng;
// KHÔNG mặc định dùng với forward nhạy cảm.
auth.dispatcherTypeMatchers(DispatcherType.FORWARD).permitAll();
~~~

Nó có thể cần cho các hệ thống có view/error forwarding mà đã kiểm đủ quyền ở request gốc. Nhưng nếu một handler nhạy cảm được gọi bằng forward từ nơi khác, việc **bỏ qua authorization cho mọi FORWARD** có thể làm mất một lớp bảo vệ. Cần đánh giá từng đường, tách endpoint nội bộ và/hoặc áp dụng method security ở handler đích.

`DispatcherType.ERROR` đôi khi được permit để render trang lỗi mà không gây vòng lỗi bảo mật, nhưng **trang lỗi không được hiển thị nội dung riêng**. Với forward và error, không dùng một rule quá rộng chỉ để làm test “hết 403” nếu chưa tìm nguyên nhân.

`/WEB-INF` của JSP thường không phục vụ trực tiếp như static file theo cơ chế container, nhưng **đó không phải hệ thống phân quyền theo user/tenant**. Một controller trả dữ liệu nhạy cảm vào JSP vẫn phải kiểm quyền trước khi render. Kỹ thuật `forward:`, `include`, view resolver và templating khác nhau không tự bảo đảm dữ liệu được giữ kín.

## 8. Ví dụ chạy được: Spring Boot 3.3.5, Java 17

Mục tiêu demo:

1. Chỉ `/assets/**` chứa tài nguyên công khai; mapping static mặc định của Boot bị tắt.
2. `/api/files/**` yêu cầu `ROLE_FILE_READER`; tài liệu còn phải thuộc người dùng.
3. `/reports/**` và `/internal/**` yêu cầu `ROLE_ANALYST`.
4. `forward:/internal/report-view` là server-side dispatch; handler đích có **`@PreAuthorize`** và kiểm dispatcher type.
5. Đường khác bị `denyAll()`. HTTP Basic được dùng để demo; password `{noop}` chỉ là fixture học tập, không dùng production.
6. Tệp demo là `byte[]` nhỏ do server sở hữu; không phải upload thực hoặc storage bên ngoài. Điều này giữ ví dụ độc lập khỏi filesystem, không được hiểu là mẫu xử lý file lớn.

### 8.1. Cấu trúc

~~~text
protected-mvc-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/resources/public-assets/app.css
  src/main/java/example/protectedmvc/ProtectedMvcApplication.java
  src/test/java/example/protectedmvc/ProtectedMvcTests.java
~~~

**pom.xml**:

~~~xml
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
    <groupId>example</groupId>
    <artifactId>protected-mvc-demo</artifactId>
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

**src/main/resources/application.properties**:

~~~properties
spring.web.resources.add-mappings=false
spring.security.filter.dispatcher-types=request,async,error,forward
server.error.include-message=never
~~~

**src/main/resources/public-assets/app.css**:

~~~css
body {
    font-family: sans-serif;
    margin: 2rem;
}
~~~

### 8.2. Security configuration, download controller và forward

**src/main/java/example/protectedmvc/ProtectedMvcApplication.java**:

~~~java
package example.protectedmvc;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.stereotype.Controller;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
@EnableMethodSecurity
public class ProtectedMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProtectedMvcApplication.class, args);
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-password")
                        .roles("FILE_READER").build(),
                User.withUsername("bob")
                        .password("{noop}demo-password")
                        .roles("FILE_READER").build(),
                User.withUsername("analyst")
                        .password("{noop}demo-password")
                        .roles("ANALYST").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/error").permitAll()
                        .requestMatchers("/api/files/**")
                            .hasRole("FILE_READER")
                        .requestMatchers("/reports/**", "/internal/**")
                            .hasRole("ANALYST")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    WebMvcConfigurer publicResources() {
        return new WebMvcConfigurer() {
            @Override
            public void addResourceHandlers(
                    ResourceHandlerRegistry registry) {
                registry.addResourceHandler("/assets/**")
                        .addResourceLocations(
                                "classpath:/public-assets/");
            }
        };
    }

    @Bean
    FileCatalog fileCatalog() {
        return new FileCatalog();
    }

    record StoredFile(
            String owner, String downloadName, byte[] bytes) {}

    static final class FileCatalog {
        private final Map<String, StoredFile> files = Map.of(
                "alice-budget", new StoredFile(
                        "alice",
                        "alice-budget.txt",
                        "Budget for Alice\n".getBytes(
                                StandardCharsets.UTF_8)),
                "bob-budget", new StoredFile(
                        "bob",
                        "bob-budget.txt",
                        "Budget for Bob\n".getBytes(
                                StandardCharsets.UTF_8)));

        Optional<StoredFile> find(String id) {
            return Optional.ofNullable(files.get(id));
        }
    }

    @RestController
    static class FileController {
        private final FileCatalog catalog;

        FileController(FileCatalog catalog) {
            this.catalog = catalog;
        }

        @GetMapping("/api/files/{id}/download")
        ResponseEntity<ByteArrayResource> download(
                @PathVariable String id, Authentication auth) {
            StoredFile file = catalog.find(id).orElseThrow(() ->
                    new ResponseStatusException(HttpStatus.NOT_FOUND));

            // BOLA/IDOR: role hợp lệ vẫn phải đúng chủ sở hữu.
            if (!file.owner().equals(auth.getName())) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }

            String disposition = ContentDisposition.attachment()
                    .filename(file.downloadName(), StandardCharsets.UTF_8)
                    .build().toString();

            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .contentLength(file.bytes().length)
                    .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                    .body(new ByteArrayResource(file.bytes()));
        }
    }

    @Controller
    static class ForwardController {

        @GetMapping("/reports/summary")
        String summary() {
            // Dùng RequestDispatcher FORWARD, không phải 302 redirect.
            return "forward:/internal/report-view";
        }
    }

    @RestController
    static class InternalReportController {

        @PreAuthorize("hasRole('ANALYST')")
        @GetMapping("/internal/report-view")
        ResponseEntity<String> render(HttpServletRequest request) {
            // Role check độc lập với việc filter chạy lại ở FORWARD.
            if (request.getDispatcherType() != DispatcherType.FORWARD) {
                // Dù analyst đã login, không cho gọi trực tiếp view đích.
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body("Internal report for analysts");
        }
    }
}
~~~

**Từng lớp bảo vệ quan trọng:**

- `requestMatchers("/assets/**").permitAll()`: chỉ cho public CSS/ảnh/JS đã kiểm kê, không cho cả `/**`.
- `requestMatchers("/api/files/**").hasRole("FILE_READER")`: chặn người không có chức năng tải file trước MVC.
- `FileController`: lookup ID do server biết và kiểm `file.owner().equals(auth.getName())`; Alice không đọc được file của Bob dù cả hai đều có `ROLE_FILE_READER`.
- `ResponseEntity<ByteArrayResource>`: đặt `Content-Disposition: attachment`, `Content-Type: application/octet-stream` và `Cache-Control: no-store`. Với file lớn, thay bằng streaming và storage layer bảo mật.
- `requestMatchers("/reports/**", "/internal/**").hasRole("ANALYST")`: bảo vệ cả URL nguồn lẫn URL đích ở tầng HTTP. Khi dispatcher type FORWARD đi vào Security chain, nó cũng được kiểm tra.
- `@EnableMethodSecurity` và `@PreAuthorize("hasRole('ANALYST')")`: handler đích có lớp kiểm quyền **không phụ thuộc** vào việc filter được gọi lần hai khi forward.
- Check `DispatcherType.FORWARD` ngăn truy cập trực tiếp `/internal/report-view` dù người gọi có role. Check này **không** thể đứng một mình thay `@PreAuthorize`: kẻ tấn công có thể điều khiển các route forward khác nếu code của ứng dụng có lỗ hổng.
- `anyRequest().denyAll()`: đường dẫn chưa khai báo bị từ chối, không mở static resources ngoài ý muốn qua auto-mapping.
- `{noop}` và InMemoryUserDetailsManager chỉ là fixture demo; production cần hệ thống xác thực/mật khẩu đã hash đúng, account status và quản lý quyền từ DB/IdP.

`httpBasic` chỉ là lựa chọn để dễ thử với `curl`; với session form login vẫn cần các chính sách CSRF, session, cookie, logout và authentication phù hợp. `GET` không được phép gây thay đổi nghiệp vụ; ví dụ không có endpoint POST/DELETE nên không cần demo CSRF trong luồng tải file.

### 8.3. Chạy thử bằng curl

Từ thư mục `protected-mvc-demo`, cần JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Terminal khác:

~~~bash
# CSS công khai; không cần credentials.
curl -i http://localhost:8080/assets/app.css

# Tệp riêng chưa đăng nhập: 401 do HTTP Basic.
curl -i http://localhost:8080/api/files/alice-budget/download

# Đúng chủ tệp: 200 và download headers.
curl -i -u alice:demo-password \
  http://localhost:8080/api/files/alice-budget/download

# Đã login, cùng role nhưng không sở hữu: 404.
curl -i -u bob:demo-password \
  http://localhost:8080/api/files/alice-budget/download

# Thiếu ROLE_ANALYST: 403.
curl -i -u alice:demo-password \
  http://localhost:8080/reports/summary

# Đúng ROLE_ANALYST: 200 với nội dung từ forwarded handler.
curl -i -u analyst:demo-password \
  http://localhost:8080/reports/summary

# Gọi trực tiếp target FORWARD: 404 theo handler.
curl -i -u analyst:demo-password \
  http://localhost:8080/internal/report-view
~~~

Response file thành công có body `Budget for Alice` và thường có `Content-Disposition: attachment`, `Cache-Control: no-store`. Response của báo cáo có body `Internal report for analysts`. Với HTTP Basic, lỗi yêu cầu xác thực thường là 401; người đã xác thực nhưng thiếu role thường 403. Trên một số triển khai có `/error` hoặc proxy tham gia xử lý, body lỗi/headers có thể khác, nhưng **quyết định truy cập** cần giữ nguyên.

### 8.4. Tại sao không dùng `file:/srv/private/` trong ResourceHandler?

Bạn có thể viết:

~~~java
// Không làm thế cho tài liệu riêng chỉ vì có thêm /api/files/**.
registry.addResourceHandler("/downloads/**")
        .addResourceLocations("file:/srv/private/");
~~~

Khi Spring MVC xử lý `/downloads/**`, nó không tự gọi `FileController` để kiểm ownership của từng file. Nếu Security `permitAll("/downloads/**")` hoặc proxy khác expose cùng location, bảo vệ object-level hoàn toàn bị bỏ qua. Với file bí mật, route phải thực hiện **identity + ACL + controlled streaming** hoặc phát hành presigned URL sau khi đã kiểm quyền, không dựa vào static resource handler.

## 9. MockMvc tests: tách public asset, file ownership và forwarding

Thêm **src/test/java/example/protectedmvc/ProtectedMvcTests.java**:

~~~java
package example.protectedmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProtectedMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicAssetIsAvailableWithoutLogin() throws Exception {
        mvc.perform(get("/assets/app.css"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("font-family")));
    }

    @Test
    void privateFileRequiresLogin() throws Exception {
        mvc.perform(get("/api/files/alice-budget/download"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanDownloadPrivateFile() throws Exception {
        mvc.perform(get("/api/files/alice-budget/download")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("Budget for Alice\n"))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().exists(
                        HttpHeaders.CONTENT_DISPOSITION));
    }

    @Test
    void sameRoleCannotDownloadAnotherPersonsFile()
            throws Exception {
        mvc.perform(get("/api/files/alice-budget/download")
                        .with(httpBasic("bob", "demo-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void nonAnalystCannotEnterReport() throws Exception {
        mvc.perform(get("/reports/summary")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void analystCanInitiateProtectedForward() throws Exception {
        mvc.perform(get("/reports/summary")
                        .with(httpBasic("analyst", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(forwardedUrl("/internal/report-view"));
    }

    @Test
    void analystCannotCallInternalTargetDirectly()
            throws Exception {
        mvc.perform(get("/internal/report-view")
                        .with(httpBasic("analyst", "demo-password")))
                .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test xác minh **public CSS không cần login**, private file cần login, **owner** tải được còn user khác cùng role không được, role analyst cho phép yêu cầu forward và URL nội bộ từ chối request trực tiếp.

**Giới hạn quan trọng:** MockMvc kiểm `forwardedUrl(...)` ở đây xác nhận MVC tạo hành động forward, **không tự chứng minh Servlet container đã thực thi một FORWARD dispatch thật với filter registration đầy đủ**. Cần test bổ sung với embedded server thật (ví dụ `@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client) để chứng minh body của forwarded handler chỉ xuất hiện với analyst, và thử điều kiện auth trên request forwarded. Một test trực tiếp `/internal/report-view` có thể đánh giá chặn đường trực tiếp, nhưng không mô phỏng toàn bộ forward của container.

### 9.1. Những test cần thêm khi ứng dụng có tệp thật

- Người dùng cùng role nhưng khác tenant/owner, file không tồn tại, ID sai định dạng, tài liệu đã bị thu hồi hoặc không còn được chia sẻ.
- `../`, encoded slash, double encoding, URL path lạ, filename Unicode hoặc ký tự đặc biệt.
- `HEAD`, `Range`, request cache và các route preview nếu sản phẩm có hỗ trợ.
- Symlink, path escaping, file rename giữa lần check và open, dữ liệu nằm ngoài storage root.
- GET/HEAD cho static assets, không expose bất kỳ private folder nào trong `classpath:/public-assets/`.
- `REQUEST` trực tiếp tới URL nội bộ, `FORWARD` thật và `ERROR` dispatch khi đường đích sinh lỗi.
- Nhiều SecurityFilterChain, nhiều servlet path hoặc reverse proxy rewrite; request matcher phải đúng với URL cuối cùng.
- Cache/CDN không trả tài liệu của người A cho người B, kể cả sau khi logout hoặc đổi account.

## 10. Nếu file nằm trên đĩa: kiểm root, symlink và quyền OS

Trong demo, file lưu dưới dạng `byte[]`. Với file thực, nên chỉ lấy **storage-relative path từ database đã xác minh quyền**. Đừng dùng path từ input request. Ví dụ một hàm **minh họa** để kiểm boundary:

~~~java
// Mảnh Java trong storage service, không phải class độc lập.
static Path resolveApprovedFile(
        Path configuredRoot, String storedRelativePath)
        throws IOException {

    Path realRoot = configuredRoot.toRealPath();
    Path realFile = realRoot.resolve(storedRelativePath).toRealPath();

    if (!realFile.startsWith(realRoot)
            || !Files.isRegularFile(realFile)) {
        throw new FileNotFoundException("Not found");
    }

    return realFile;
}
~~~

Cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.io.IOException`, `java.io.FileNotFoundException`. `toRealPath()` theo symbolic links và canonicalization; so sánh bằng `Path.startsWith(Path)` (theo thành phần đường dẫn) khác với `String.startsWith`, tránh nhầm `/srv/private2` được xem là nằm dưới `/srv/private`. Nếu file bị symlink ra ngoài root, path thực có thể rời root và bị từ chối.

Tuy nhiên **đây chưa giải quyết hoàn toàn TOCTOU** nếu một tác nhân khác có quyền sửa symlink/path giữa lần kiểm và mở file. Storage production nên giới hạn quyền ghi của OS, tránh thư mục chung không đáng tin, dùng file descriptor/secure directory operations khi cần hoặc chuyển qua storage key/object API được thiết kế rõ. Quy tắc quan trọng vẫn là **lookup ID -> ACL -> resolve storage key nội bộ -> open/stream**, không phải `Path.of(userInput)`.

Không serve file lớn bằng cách đọc toàn bộ vào RAM như `ByteArrayResource` của demo; dùng streaming/`Resource` phù hợp, quota và limit đồng thời. Với tải lên và xem trước, còn cần giới hạn MIME, dung lượng, số lượng, scan malware, cách đặt tên và cô lập nội dung do user kiểm soát.

## 11. MvcRequestMatcher, đường dẫn và nhiều servlet

Trong Spring Security 6 Servlet với Spring MVC hiện diện, `authorizeHttpRequests().requestMatchers("/...")` thường sử dụng matching phù hợp với MVC khi có `HandlerMappingIntrospector`. Điều quan trọng là **đường dẫn thực tế mà Security thấy**, không chỉ chuỗi hiện trên browser:

- Có `server.servlet.context-path` hoặc servlet path riêng không? Matcher có thể yêu cầu cấu hình tương ứng; không thêm context path một cách tùy tiện vào mẫu matcher.
- Có nhiều `DispatcherServlet` hoặc servlet khác cùng ứng dụng không? Chỉ sử dụng MVC matcher cho phạm vi MVC phù hợp; có thể cần chỉ rõ servlet path/builder.
- Proxy có rewrite URL hay đưa prefix `X-Forwarded-*` không? Cần cấu hình proxy và trusted headers đúng, không lấy đường dẫn/host client tự khai làm bằng chứng quyền.
- Có nhiều `SecurityFilterChain` với `securityMatcher` khác nhau không? Request `FORWARD`, `ERROR`, static hoặc download có thể rơi vào chain khác hoặc không được chain bảo vệ nếu phạm vi sai.
- Đường dẫn được decode/normalize ở tầng container/MVC như thế nào? Encoded slash, semicolon/matrix variables và trailing slash cần kiểm thử theo container thực, không dựa trên một chuỗi regex tự nghĩ ra.

Đối với nhiều servlet path, có thể dùng `MvcRequestMatcher.Builder` với `HandlerMappingIntrospector` để xác định servlet path tường minh. Đây là **mảnh gợi ý cần điều chỉnh cho ứng dụng**, không thay cấu hình đầy đủ ở mục 8:

~~~java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector)
                .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
        .requestMatchers(mvc.pattern("/api/files/**"))
            .hasRole("FILE_READER")
        .anyRequest().denyAll());
~~~

Ứng dụng cần import `org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher` và inject `HandlerMappingIntrospector` tương ứng. **Không bê nguyên `/mvc`** nếu ứng dụng của bạn không có servlet path này.

Không dùng security matcher quá rộng hoặc quá hẹp tùy tiện. Đường dẫn tải file có thể xuất hiện qua route `/download/**`, `/api/files/**`, `/static/uploads/**` hoặc CDN; cần **kiểm kê tất cả cách truy cập cùng một tài nguyên** trước khi đánh giá bảo vệ đã hoàn chỉnh.

## 12. Rủi ro đặc biệt của forward, include và error view

### 12.1. Forward

`forward:/...` được thực hiện phía server và có thể thay đổi path được filter/handler nhìn thấy. Controller nguồn đôi khi đã làm một số kiểm tra, nhưng đích vẫn cần bảo vệ nếu có thể được gọi trực tiếp hoặc thông qua đường forward khác. Với tài liệu/tenant cụ thể, role chung không đủ: handler hoặc service phải kiểm quyền dựa trên dữ liệu đang render.

### 12.2. Include

Một JSP hoặc controller có thể **include** nội dung từ thành phần khác trong cùng response. Tùy dispatcher registration, Security filter có thể không chạy như một REQUEST mới trên `DispatcherType.INCLUDE`. Đừng đưa dữ liệu nhạy cảm vào một fragment mà mọi handler đều có thể include mà thiếu kiểm quyền service/view model. Kiểm theo dữ liệu nghiệp vụ, không dựa hoàn toàn vào tên JSP.

### 12.3. Error

Một exception có thể gây `ERROR` dispatch tới `/error`. Nếu error view vô tình in ra stack trace, request attributes, session info hoặc dữ liệu đã xử lý ở route riêng, `permitAll("/error")` không còn vô hại. Dùng trang lỗi tối thiểu, không đưa bí mật/PII vào thông báo và cấu hình hiển thị lỗi an toàn.

### 12.4. Redirect

`redirect:` trả 302/303/307... để browser gọi URL khác. Request mới phải được phân quyền theo route đích; không tự tin rằng vì người dùng được phép gọi route tạo redirect nên họ đã có quyền ở route đích. Tránh **open redirect** bằng cách chỉ redirect đến path/host đã được ứng dụng cho phép.

### 12.5. View templates và dữ liệu

Với Thymeleaf, FreeMarker, Mustache hoặc JSP, một template nằm trong thư mục không truy cập trực tiếp không tự bảo đảm dữ liệu trong model được phép đọc. Phải kiểm **ownership/tenant/role trước khi đưa dữ liệu vào model**, không chỉ kiểm sau render hoặc giấu nút/đường link ở frontend. Frontend ẩn menu không phải kiểm soát bảo mật.

## 13. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao nguy hiểm? | Cách khắc phục |
| --- | --- | --- |
| `permitAll("/**")` rồi hy vọng controller chặn | Mở quá rộng, bỏ sót route mới | Public allowlist hẹp, `anyRequest().denyAll()` |
| `web.ignoring("/static/**")` cho mọi tài nguyên | Bỏ qua Security filter chain, có thể thiếu security headers | Ưu tiên `permitAll()` cho public assets |
| Đưa file riêng vào `resources/static` | Có thể tải qua URL public khác, bypass download controller | Chuyển khỏi static root, chỉ expose qua ACL controller |
| Chỉ dùng `hasRole("FILE_READER")` | User cùng role tải file của người khác | Ownership/tenant/ACL trên từng document ID |
| Ghép `filename` client vào `Path` | Path traversal, symlink escape | Opaque ID -> server-side key, realpath/OS storage safety |
| Tin UUID là đủ bảo mật | ID có thể lộ, đoán khó không phải phân quyền | Kiểm auth + ACL mọi request |
| `forward:` tới URL `permitAll` có dữ liệu nhạy cảm | Bypass authorization ở target qua route khác | Bảo vệ source, target, method/service |
| `dispatcherTypeMatchers(FORWARD).permitAll()` vô điều kiện | Mất lớp kiểm soát với forwarded endpoints | Đánh giá từng path; method security cho đích nhạy cảm |
| Test `forwardedUrl` và tuyên bố filter đã chạy lần hai | MockMvc không tự đảm bảo forward thật như container | Integration test embedded servlet |
| Dùng CDN/cache chung cho file riêng | Có thể lộ dữ liệu giữa user/tenant | Cache-Control/private/no-store, partition key, signed URL policy |
| `Content-Disposition` nối thẳng tên file | Header injection, tên tệp sai encoding | Builder API, encode/escape, filename whitelist |
| `ResourceHttpRequestHandler` map `file:/private` | Static handler không biết ownership | Dùng controller có ACL hoặc storage signed URL sau auth |
| Error view công khai chứa dữ liệu | Lộ stack trace/model/PII qua error dispatch | Error response tối thiểu, không log token |
| Tin forward/redirect giống nhau | Nhầm dispatcher và request boundary | Kiểm servlet dispatch vs browser 3xx riêng |
| Bỏ qua `HEAD`, `Range` hoặc preview route | Còn lối đọc file ngoài GET thường | Áp dụng cùng ACL trên mọi đường đọc |
| Security matcher không phủ đúng servlet path | Request có thể rơi vào chain khác | Xác nhận HandlerMappingIntrospector, servlet path, proxy |

**Khi debug 401/403/404**, xác định lỗi đến từ Spring Security filter, MVC handler, owner check hay storage. Trong demo, file của người khác trả 404 theo chủ ý; đây không có nghĩa tài liệu thực sự không tồn tại. Ngược lại, 404 static có thể do resource handler không có mapping/file, không phải authentication.

## 14. Quy trình kiểm tra trên môi trường thực

1. **Lập bản đồ đường dẫn và storage.** Ghi các URL GET/HEAD/Range, controllers, static handlers, view resolvers, proxy/CDN route và nơi thực lưu dữ liệu.
2. **Phân loại dữ liệu.** Public CSS/JS/image khác file upload riêng, file export, hóa đơn, báo cáo, file tạm, attachment từ ticket.
3. **Tạo allowlist public.** Chỉ `/assets/**` hoặc danh sách location tin cậy cần `permitAll`; đường khác có role và deny-by-default.
4. **Xác định quyền theo đối tượng.** Với file ID, tra owner, tenant, visibility, ACL ở backend. Kiểm account bị khóa/đã mất quyền.
5. **Kiểm storage boundary.** Không để file riêng trong web root; path do server quản lý, chống traversal/symlink và hạn chế quyền OS.
6. **Xác định response header/cache.** Content-Disposition, Content-Type, nosniff, no-store, referrer/URL leakage và CDN policy.
7. **Kiểm forward/include/error.** Với mỗi route nội bộ, kiểm URL nguồn/đích, dispatcher registration, method security và các view không làm lộ model data.
8. **Viết test theo vai trò và chủ sở hữu.** Anonymous, role sai, owner đúng, cùng role khác owner, tài liệu không tồn tại, path đặc biệt, forward trực tiếp/gián tiếp.
9. **Kiểm với container/proxy thực.** MockMvc hữu ích nhưng không thay thế kiểm FORWARD/ERROR dispatch, header/caching và URL rewrite của hệ thống chạy thật.
10. **Theo dõi thay đổi.** Khi thêm static location, controller, servlet mapping hoặc CDN, phải cập nhật threat model và authorization tests.

Không log mật khẩu, bearer token, session cookie, presigned URL hoặc đường dẫn nhạy cảm nguyên vẹn trong báo cáo lỗi. Khi cần audit, lưu identity, document ID nội bộ, loại hành động và kết quả access (đã được xử lý theo chính sách bảo mật), tránh lưu nội dung tài liệu.

## 15. Bài tập tự kiểm tra

**Câu 1.** User Alice có `ROLE_FILE_READER` nên gọi `/api/files/bob-budget/download` được không?  
**Không.** Cần ACL/ownership theo từng file, role chỉ là điều kiện ban đầu.

**Câu 2.** Nếu file mật nằm trong `src/main/resources/static`, việc bảo vệ `/api/files/**` đã đủ chưa?  
**Chưa.** Có thể còn URL public do static handler phục vụ. Phải đưa file khỏi public locations và kiểm mọi lối truy cập.

**Câu 3.** Vì sao `permitAll("/assets/**")` thường tốt hơn `web.ignoring("/assets/**")`?  
**Vì** static request vẫn qua Security filter chain, giữ cơ hội áp dụng header và chính sách liên quan mà không buộc đăng nhập.

**Câu 4.** Khi `/reports/summary` forward tới `/internal/report-view`, cần bảo vệ đường nào?  
**Cả nguồn và đích**, đặc biệt khi đích có thể truy cập trực tiếp. Method/service-level authorization bảo vệ dữ liệu ngay tại handler.

**Câu 5.** `MockMvc.andExpect(forwardedUrl(...))` đã chứng minh một Servlet FORWARD dispatch thực sự được Security filter lại chưa?  
**Chưa.** Cần integration test container thật với dispatcher registration phù hợp.

**Câu 6.** Vì sao `DispatcherType.FORWARD` không phải một điều kiện cấp quyền?  
**Vì** nó chỉ mô tả cách request được dispatch, không chứng minh người dùng có vai trò hoặc quyền với dữ liệu.

**Câu 7.** Client gửi `?path=../../etc/passwd`, có nên làm `Path.of(root).resolve(path)` rồi trả tệp không?  
**Không.** Dùng ID opaque, server-side metadata + ACL, chống traversal/symlink và tách private storage khỏi web root.

**Câu 8.** `Content-Disposition: attachment` có thay thế authorization không?  
**Không.** Nó gợi ý cách browser xử lý response sau khi nội dung đã được server quyết định trả về.

**Câu 9.** Một presigned URL có TTL 10 phút có mặc định chỉ dùng được một lần không?  
**Không.** Người sở hữu URL có thể dùng lại trong thời hạn tùy quy tắc storage; cần kiểm quyền khi phát URL và hiểu bearer semantics.

**Câu 10.** File có thể đọc bằng GET và HEAD/Range; chỉ cần test GET 200/403 không?  
**Chưa.** Phải kiểm tất cả phương thức/route/cơ chế đọc mà ứng dụng hỗ trợ.

## 16. Ghi nhớ

- **Public assets**: đưa vào location đã kiểm kê, cho phép `/assets/**` đủ hẹp, vẫn giữ Spring Security filter chain và response headers.
- **Private downloads**: **xác thực + role + object-level ownership/ACL**. Đừng để file riêng lọt qua static resource handler hoặc CDN public; không lấy đường dẫn từ client làm file path.
- **Forwarded views**: hiểu `FORWARD` khác `redirect` và render template. Bảo vệ URL nguồn/đích, kiểm dispatcher registration, thêm method/service security cho nội dung nhạy cảm; không `permitAll(FORWARD)` đại trà.
- **File response**: download headers, cache, content sniffing và storage access cũng là một phần bảo mật, không chỉ `requestMatchers`.
- **Test**: unit/MockMvc cho role/owner/static mapping, integration test container cho FORWARD thật và proxy/storage cho toàn bộ đường tải tài nguyên.

**Kết luận:** Trong Spring Security Servlet tích hợp MVC, đường dẫn tĩnh, tải file và view chuyển tiếp đều là các bề mặt truy cập cần **quyết định phân quyền rõ ràng và kiểm chứng được**. URL-level rules chặn từ ngoài; ACL ở controller/service bảo vệ từng đối tượng; storage và dispatch configuration không được mở đường vòng tránh cả hai.
