# Kiểm thử nhiều filter chain và endpoint không được khai báo trong Spring Security

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể thiết kế và kiểm thử HTTP cho ứng dụng **Spring Security Servlet/MVC** có nhiều `SecurityFilterChain`, chứng minh chain nào được chọn, kiểm tra quyền truy cập khi một URL không nằm trong các quy tắc `requestMatchers` và phân biệt đường dẫn không có controller với đường dẫn không được Spring Security bảo vệ.

Bài dùng **Java 17+, Spring Boot 4.1.2, Spring Security 7.x, JUnit Jupiter và MockMvc**. Đó là một ví dụ servlet; ứng dụng WebFlux dùng cơ chế `SecurityWebFilterChain` khác.

## 2. Hiểu chính xác các lớp quyết định

Luồng xử lý tổng quát:

~~~text
HTTP request
  -> Servlet Filter / FilterChainProxy
     -> thử SecurityFilterChain theo thứ tự @Order
     -> chọn CHAIN ĐẦU TIÊN có securityMatcher phù hợp
        -> các security filter: CSRF, authentication, authorization...
        -> authorizeHttpRequests: quy tắc requestMatchers, rồi anyRequest
  -> DispatcherServlet của Spring MVC
     -> tìm controller mapping, hoặc trả 404 nếu không có
~~~

- `securityMatcher(...)` xác định **phạm vi mà cả chain bảo vệ**. Ví dụ `/api/**`.
- `requestMatchers(...)` bên trong `authorizeHttpRequests` xác định **quy tắc cấp quyền khi request đã vào chain đó**. Nó không quyết định chain được chọn.
- `@Order(1)` được xét trước `@Order(2)`; chain đầu tiên khớp sẽ xử lý. Các chain không cộng dồn bộ lọc/quy tắc. Một chain không khai báo `securityMatcher` có matcher mặc định khớp mọi request, nên phù hợp làm fallback ở cuối.
- `anyRequest().authenticated()`: URL chưa khớp quy tắc trước đó trong chain vẫn được người dùng đã xác thực truy cập. `anyRequest().denyAll()`: từ chối tất cả URL còn lại trong chain. Một `anyRequest` của chain A không áp dụng cho chain B.
- Nếu **không có chain nào khớp**, các bộ lọc bảo mật Spring Security không bảo vệ request ấy. Controller còn tồn tại có thể phục vụ request; controller không tồn tại có thể trả 404. Đây là rủi ro bảo mật nếu vô tình thiếu fallback.
- Kết quả do **security** và **MVC** quyết định ở hai giai đoạn khác nhau. Không thể suy ra rằng URL không có controller luôn trả 404.

### Ba kiểu “endpoint không được khai báo”

| Tình huống | Ý nghĩa thực tế | Kết quả cần kiểm tra |
|---|---|---|
| A. Controller có `GET /api/profile`, nhưng không liệt kê trong `requestMatchers` | URL vẫn thuộc chain `/api/**` | Quy tắc `anyRequest` của chính API chain quyết định; trong ví dụ này phải đăng nhập |
| B. Controller có `GET /docs`, nhưng URL không khớp chain chuyên biệt | Đi vào fallback (nếu có) | Với fallback `denyAll`: bị từ chối, kể cả khi controller có thật |
| C. Không có controller cho `GET /api/ghost` | URL vẫn khớp API chain, rồi mới đến MVC | Anonymous có thể nhận 401; người đã xác thực đi qua authorization rồi nhận 404 |

Trường hợp **không có cả matcher chain lẫn fallback** khác với B: `/docs` có thể đi thẳng đến MVC mà không chịu authorization của Spring Security. Đừng đánh đồng “không liệt kê trong `requestMatchers`”, “không có chain” và “không có `@GetMapping`”.

### Đọc đúng HTTP status

- **200/201**: qua lớp security và controller thực hiện thành công (201 cho tạo mới trong ví dụ).
- **401**: chưa được xác thực và cơ chế HTTP Basic yêu cầu credentials; nếu dùng form login có thể là **302** về trang đăng nhập.
- **403**: đã xác thực nhưng không đủ quyền, hoặc request bị chặn bởi CSRF; cần xem ngữ cảnh để biết nguyên nhân.
- **404**: request đã đến MVC nhưng không có handler/controller phù hợp. Security hoàn toàn có thể từ chối trước khi MVC trả 404.

## 3. Bài thực hành: ba chain có thứ tự ưu tiên

Giả sử ứng dụng có:

1. **Chain admin**: `@Order(1)`, `securityMatcher("/api/admin/**")`, yêu cầu `ROLE_ADMIN`.
2. **Chain API**: `@Order(2)`, `securityMatcher("/api/**")`; GET `/api/public` công khai, các API khác cần xác thực.
3. **Chain fallback**: xét cuối, không đặt `securityMatcher`; `/health` công khai, mọi URL còn lại `denyAll`.

Vì `/api/admin/reports` cũng khớp `/api/**`, bắt buộc đặt admin chain trước API chain. Nếu đổi thứ tự, người dùng thường có thể lọt qua quy tắc `authenticated()` của API chain và bỏ qua yêu cầu `ROLE_ADMIN`.

Bảng dự kiến (các yêu cầu là GET, HTTP Basic được bật, các controller được khai báo như ví dụ bên dưới):

| URL | Anonymous | ROLE_USER | ROLE_ADMIN | Lý do |
|---|---:|---:|---:|---|
| `/api/public` | 200 | 200 | 200 | API chain, công khai |
| `/api/profile` | 401 | 200 | 200 | API chain, không liệt kê riêng, rơi vào `authenticated` |
| `/api/admin/reports` | 401 | 403 | 200 | Admin chain ưu tiên cao nhất |
| `/health` | 200 | 200 | 200 | Fallback cho phép chính xác URL này |
| `/docs` (có controller) | 401* | 403 | 403 | Fallback `denyAll` |
| `/api/ghost` (không có controller) | 401 | 404 | 404 | API xét quyền trước, MVC tìm không thấy handler |
| `/unknown` (không có controller) | 401* | 403 | 403 | Fallback từ chối trước khi có 404 |

Dấu *: khi chưa đăng nhập, `denyAll` kết hợp cơ chế bắt đầu xác thực của HTTP Basic thường trả 401; test cốt lõi của bài sử dụng người đã xác thực để kết quả 403 rõ ràng. HTTP status thực tế còn phụ thuộc cấu hình entry point, error dispatcher và cơ chế đăng nhập.

## 4. Dựng ví dụ chạy được

Cấu trúc Maven:

~~~text
security-routing-demo/
  pom.xml
  src/main/java/example/security/DemoApplication.java
  src/main/java/example/security/SecurityConfig.java
  src/main/java/example/security/DemoController.java
  src/test/java/example/security/SecurityRoutingTests.java
~~~

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-routing-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

`spring-boot-starter-webmvc-test` cung cấp hạ tầng kiểm thử MockMvc/JUnit; `spring-security-test` cung cấp `user()`, `csrf()` và các công cụ giả lập danh tính. Maven dùng dependency management từ Spring Boot parent, không cần tự chốt phiên bản riêng cho từng thư viện.

### `src/main/java/example/security/DemoApplication.java`

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### `src/main/java/example/security/SecurityConfig.java`

~~~java
package example.security;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain generalApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Cho phép servlet render lỗi sau khi xử lý request.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/health").permitAll()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Không có `csrf.disable()`: giữ CSRF protection mặc định để kiểm tra thêm tình huống POST. `DispatcherType.ERROR` được cho phép ở fallback để quá trình xử lý lỗi servlet không bị quy tắc `denyAll` chặn lần thứ hai; nó không biến một request GET thông thường thành URL công khai. Nếu dự án có nhiều servlet, context path, forwarding hoặc endpoint lỗi đặc biệt, cần kiểm thử dispatcher tương ứng.

### `src/main/java/example/security/DemoController.java`

~~~java
package example.security;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String apiPublic() {
        return "PUBLIC";
    }

    @GetMapping("/api/profile")
    public String apiProfile() {
        return "PROFILE";
    }

    @GetMapping("/api/admin/reports")
    public String adminReports() {
        return "REPORTS";
    }

    @GetMapping("/health")
    public String health() {
        return "HEALTHY";
    }

    @GetMapping("/docs")
    public String docs() {
        return "DOCUMENTATION";
    }

    @PostMapping("/api/items")
    @ResponseStatus(HttpStatus.CREATED)
    public String createItem() {
        return "CREATED";
    }
}
~~~

**Cố ý không khai báo** bất kỳ controller nào cho `/api/ghost` hay `/unknown`; chúng dùng để kiểm thử “endpoint không tồn tại”.

## 5. Test toàn bộ đường đi với MockMvc

### `src/test/java/example/security/SecurityRoutingTests.java`

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRoutingTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointsWorkWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC"));

        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("HEALTHY"));
    }

    @Test
    void broaderApiChainRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/profile")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("PROFILE"));
    }

    @Test
    void specificAdminChainWinsBeforeBroaderApiChain() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/admin/reports")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/reports")
                .with(user("boss").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORTS"));
    }

    @Test
    void existingControllerNotAllowedByFallbackIsDenied() throws Exception {
        mvc.perform(get("/docs")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/docs")
                .with(user("boss").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingControllerInsideApiIs404OnlyAfterAuthorization() throws Exception {
        mvc.perform(get("/api/ghost"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/ghost")
                .with(user("alice").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void missingControllerOutsideApiIsBlockedByFallback() throws Exception {
        mvc.perform(get("/unknown")
                .with(user("boss").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsafeMethodRequiresCsrfToken() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/items")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("CREATED"));
    }
}
~~~

Chạy tại thư mục dự án bằng **JDK 17+ và Maven 3.6.3+**:

~~~bash
mvn test
mvn spring-boot:run
~~~

Dự kiến **7 phương thức test đều thành công** khi cấu hình và dependencies đúng. Các status và chuỗi response là các điều kiện `andExpect` trong source, không phải bản sao log Maven thực tế. Nếu chạy app bằng HTTP Basic ở ngoài test, phải cung cấp tài khoản thật do ứng dụng cấu hình (ví dụ user tạm của Boot nếu được tạo); `user(...)` chỉ tạo `SecurityContext` trong bài test, không tạo tài khoản production.

### Test đang chứng minh điều gì?

- `specificAdminChainWinsBeforeBroaderApiChain` là phép thử **ưu tiên chain**. Nếu đưa `/api/**` lên trước `/api/admin/**`, người dùng `ROLE_USER` có thể được cho qua endpoint admin vì API chain chỉ yêu cầu `authenticated()`. Test sẽ phát hiện hồi quy.
- `broaderApiChainRequiresAuthentication` chứng minh `/api/profile` vẫn được bảo vệ dù **không có matcher riêng** trong `authorizeHttpRequests`.
- `existingControllerNotAllowedByFallbackIsDenied` chứng minh việc có `@GetMapping("/docs")` không đồng nghĩa được phép truy cập; fallback vẫn có hiệu lực.
- `missingControllerInsideApiIs404OnlyAfterAuthorization` thử cả trước và sau authorization: **401 cho anonymous**, **404 cho người dùng hợp lệ**. Chỉ assert 404 sẽ bỏ sót lỗ hổng.
- `missingControllerOutsideApiIsBlockedByFallback` chứng minh `/unknown` bị **deny trước khi đến MVC**.
- `unsafeMethodRequiresCsrfToken` cô lập nguyên nhân 403 do CSRF. Có `ROLE_USER` cũng không tự cấp CSRF token.

## 6. Kiểm tra nguy cơ không có fallback

**Biến thể chỉ dùng để phân tích, không thêm vào ứng dụng chạy ở mục 4:** giả sử ứng dụng chỉ khai báo chain `securityMatcher("/api/**")` và không có chain cuối khớp tất cả. Request `GET /docs` sẽ **không đi qua security filters** của Spring Security; nếu MVC có controller `/docs`, request có thể thành công mà không đăng nhập. Vì vậy:

- Đừng tưởng `.anyRequest().denyAll()` trong **API chain** sẽ bảo vệ `/docs`; nó chỉ xét request vốn đã khớp `/api/**`.
- Có thể thêm fallback `anyRequest().denyAll()` (chính sách allowlist) hoặc `authenticated()` nếu thật sự muốn cho mọi URL còn lại vào ứng dụng sau đăng nhập. Chọn chính sách có chủ ý, rồi viết test tương ứng.
- Phân biệt `permitAll()` (vẫn qua filter chain với các lớp bảo vệ như security headers) với `web.ignoring()`/URL hoàn toàn ngoài chain (bỏ qua nhiều bảo vệ). Thường ưu tiên `permitAll()` cho tài nguyên công khai.

Không nên dùng kiểm thử một URL thực sự không tồn tại để chứng minh có bảo mật: cả hệ thống được bảo vệ đúng và hệ thống không có chain đều có thể trả 404. Hãy kiểm tra thêm một **controller có thật** ngoài phạm vi các chain chuyên biệt (ví dụ `/docs`), một người dùng chưa xác thực và một người dùng đã xác thực.

## 7. Cách mở rộng thành bộ test đủ mạnh

Một ma trận kiểm thử hữu ích có các trục độc lập:

| Trục | Ca kiểm thử tối thiểu |
|---|---|
| Chain ưu tiên | Pattern cụ thể chồng lên pattern tổng quát; hoán đổi thứ tự phải làm một test fail |
| Authorization | Anonymous, authenticated không đúng role, authenticated đúng role |
| URL | Endpoint được liệt kê, endpoint có controller nhưng không liệt kê, URL không có handler, URL ngoài matcher chuyên biệt |
| HTTP method | GET cho phép, POST/PUT/DELETE cần quyền và CSRF phù hợp |
| Boundary | `/api/admin` so với `/api/admin/`; `/api/admin2`; query string, chữ hoa/thường, context/servlet path |
| Error dispatch | 404/403/401 khi chạy qua container thật, với điều kiện `ERROR`/`FORWARD` và trang `/error` |
| Cấu hình | Bean chain mới, thay `@Order`, thay `securityMatcher`, thay fallback |

**Quan trọng:** `@WebMvcTest` chỉ dựng một phần application context; nếu không nhập đủ security config, kết quả có thể đang kiểm tra chain mặc định hoặc chain giả. Để kiểm thử **tương tác của nhiều chain thật**, ưu tiên `@SpringBootTest + @AutoConfigureMockMvc` và đảm bảo filter được bật (mặc định). Nếu tự tạo `MockMvcBuilders`, áp dụng `springSecurity()` vào builder để gắn `FilterChainProxy`. Không dùng `addFilters = false` để kiểm thử authorization.

Với quyền phức tạp hoặc path matcher tùy biến, nên kiểm thêm phương thức, servlet path, dispatcher type, phía sau reverse proxy, và trường hợp API chưa có controller. Khi yêu cầu kiểm chứng toàn bộ container behavior (forward/error dispatch, session cookie, redirect), thêm ít nhất một test HTTP thật với `@SpringBootTest(webEnvironment = RANDOM_PORT)`; MockMvc không mô phỏng hoàn toàn vòng đời của servlet container.

## 8. Các lỗi thường gặp và cách chẩn đoán

1. **Chain rộng đứng trước chain hẹp.** `/api/**` được xét trước `/api/admin/**`, làm mất kiểm tra role admin. Giữ `@Order` rõ ràng và có test chồng matcher.
2. **Nhầm `securityMatcher` với `requestMatchers`.** `requestMatchers` chỉ chọn quy tắc *sau* khi chain đã khớp. Một `anyRequest` không thể bao phủ URL nằm ngoài chain.
3. **Thiếu fallback hoặc fallback quá thoáng.** Controller mới xuất hiện ở URL ngoài matcher có thể bị lộ hoặc vô tình trở nên công khai. Viết test cho URL thật nằm ngoài API chain.
4. **Assert 404 cho anonymous và bỏ qua 401/403.** Không có controller không đảm bảo request đi tới MVC. Luôn thử cùng URL với ít nhất hai trạng thái đăng nhập.
5. **Đọc 403 thành sai role trong mọi trường hợp.** Với POST, thiếu CSRF token cũng dẫn tới 403; dùng `with(csrf())` khi mục tiêu là test authorization, và test riêng CSRF nếu cần.
6. **Test bỏ mất FilterChainProxy.** Tự dựng MockMvc không gắn security hoặc đặt `addFilters=false` khiến endpoint đều có vẻ công khai. Kiểm lại context và cấu hình MockMvc.
7. **Lẫn role/authority.** `hasRole("ADMIN")` kiểm `ROLE_ADMIN`; `user("boss").roles("ADMIN")` tạo đúng authority. Với `hasAuthority("ADMIN")` phải cấp chính xác `ADMIN`.
8. **Cấu hình cơ chế đăng nhập khác nhưng assert cứng 401.** HTTP Basic có thể trả 401, form login thường redirect 302; khẳng định đúng theo authentication entry point của chain.
9. **Test matcher quá dễ dãi.** `/api/admin/**`, method, servlet path và URL gần giống phải được kiểm theo matcher thực tế. Query parameters không tự động là tiêu chí của path matcher.
10. **Bỏ qua ERROR dispatch.** Một 404 ở MVC có thể qua `/error` trong container thật và chịu thêm authorization; phân biệt lỗi do security với lỗi định tuyến.

Để điều tra, bật logging có chọn lọc trong môi trường test:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access=DEBUG
~~~

Kiểm tra request được chain nào match, `Authentication` đang có authority gì, bước authorization nào quyết định từ chối, rồi mới kiểm tra controller mapping. Chỉ bật logging chi tiết khi cần; không ghi credentials/token thực vào log.

## 9. Bài tự kiểm tra

1. Đổi `@Order` của `generalApi` thành ưu tiên cao hơn `adminApi`. Test nào nên fail và vì sao? **Đáp án:** `specificAdminChainWinsBeforeBroaderApiChain`; `ROLE_USER` có thể nhận 200 thay vì 403 ở `/api/admin/reports`.
2. Đổi `generalApi.anyRequest().authenticated()` thành `denyAll()`. Khi đã đăng nhập, `/api/profile` còn 200 không? **Không**, bị 403 do thiếu allow rule riêng.
3. Bỏ fallback, vẫn giữ controller `/docs`. Tại sao đây là nguy cơ dù `/api/ghost` trả 404? **Vì** `/docs` nằm ngoài tất cả chain, nên vẫn có thể được MVC phục vụ mà Spring Security không bảo vệ; 404 trên URL giả không kiểm chứng coverage.
4. Với `GET /api/ghost`, tại sao cần thử anonymous và user? **Vì** kết quả 401/404 tương ứng chứng minh có authorization trước khi MVC phát hiện thiếu handler.
5. Với `POST /api/items` và `ROLE_USER`, vì sao có thể gặp 403? **Vì** mặc định CSRF bảo vệ phương thức không an toàn; bổ sung token CSRF rồi mới kiểm tra rule authentication.

## 10. Tài liệu chính thức để đối chiếu

- [Spring Security — FilterChainProxy và nhiều SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — nhiều HttpSecurity và phạm vi securityMatcher](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — authorizeHttpRequests, requestMatchers, anyRequest, denyAll](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — thiết lập MockMvc và Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — kiểm thử CSRF với MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Boot — kiểm thử ứng dụng với MockMvc](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

**Nguyên tắc cần nhớ:** thử **chain đầu tiên khớp**, rồi thử **authorization của chain đó**, sau đó mới xét **controller có tồn tại hay không**. Một bộ test tốt buộc phải chứng minh cả ba ranh giới.