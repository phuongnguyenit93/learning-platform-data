# permitAll và WebSecurityCustomizer.ignoring: khác biệt về bộ lọc bảo vệ trong Spring Security Servlet

Trong ứng dụng **Spring MVC chạy trên Servlet stack**, hai cấu hình sau có vẻ cùng tạo ra một URL “không cần đăng nhập”:

- `authorizeHttpRequests(...).requestMatchers("/public/**").permitAll()`;
- `WebSecurityCustomizer` với `web.ignoring().requestMatchers("/public/**")`.

Thực tế, chúng **không tương đương**. `permitAll()` là **quy tắc phân quyền** cho request vẫn đi qua chuỗi filter bảo mật. `ignoring()` khiến request được khớp **bỏ qua các filter của Spring Security**. Sự khác biệt ảnh hưởng trực tiếp tới CSRF, security headers, xác thực tùy chọn, security context, logging và khả năng áp dụng chính sách bảo vệ về sau.

Bài này xét **Spring Security cho Servlet** (`HttpSecurity`, `SecurityFilterChain`, `WebSecurityCustomizer`, `HttpServletRequest`), đặc biệt hệ cấu hình bean phổ biến ở Spring Boot 3.x / Spring Security 6.x. Với phiên bản khác, hãy đối chiếu API và migration guide tương ứng; khái niệm **cho phép tại bước authorization** so với **bỏ qua security filters** vẫn là trọng tâm.

## 1. Spring Security xử lý một request Servlet ở những lớp nào?

Khi ứng dụng bật Spring Security Web, container gọi các servlet filter, trong đó `DelegatingFilterProxy` thường chuyển tiếp việc xử lý bảo mật tới bean `springSecurityFilterChain`. Bean này là `FilterChainProxy`, chọn **SecurityFilterChain** đầu tiên phù hợp với request.

```text
HTTP request
    |
Servlet container FilterChain
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |-- chọn SecurityFilterChain theo request matcher
    |       |
    |       +-- SecurityContext / authentication-related filters
    |       +-- header / CSRF / exception-handling filters
    |       +-- AuthorizationFilter (authorizeHttpRequests)
    |       +-- các security filters khác theo cấu hình
    |
DispatcherServlet -> Controller -> Service
```

Sơ đồ là mô hình khái niệm; **thứ tự và danh sách filter cụ thể** tùy các tính năng đang bật, phiên bản và cấu hình. Không giả định mọi ứng dụng đều có cùng một danh sách filter.

Ba quyết định cần phân biệt:

1. **Chọn chain:** `FilterChainProxy` tìm cấu hình `SecurityFilterChain` phù hợp với request.
2. **Chạy filter:** các filter trong chain đó có cơ hội đọc/lưu authentication, xử lý exception, CSRF, header... theo cấu hình.
3. **Phân quyền:** bộ authorization xét rule như `permitAll`, `authenticated`, `hasRole` hoặc `access`.

**`permitAll` tác động vào bước 3; `web.ignoring` tác động trước bước 2.** Một request được phép truy cập controller không có nghĩa nó đã đi vòng qua mọi security filter.

Đặc biệt, security filters ở đây là filter **thuộc Spring Security**. Servlet filter độc lập do ứng dụng/container đăng ký bên ngoài `FilterChainProxy` vẫn có thể chạy với request bị `web.ignoring`; không nên diễn giải `ignoring` thành “bỏ qua mọi filter trong toàn bộ server”.

## 2. permitAll: vẫn chạy chuỗi bảo mật, chỉ bỏ yêu cầu quyền ở URL đó

Cấu hình Servlet điển hình:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **đoạn method bean minh họa**; phần dự án chạy được đầy đủ nằm ở mục 5. Với request `GET /public/ping`:

1. Request phù hợp với cấu hình `SecurityFilterChain` của ứng dụng.
2. Các filter của Spring Security trong chain vẫn được kích hoạt nếu có và đáp ứng điều kiện xử lý.
3. Tới `AuthorizationFilter`, rule `permitAll` cho phép request mà **không đòi principal đã đăng nhập**.
4. Request tiếp tục vào controller; controller quyết định nội dung và HTTP status.

### permitAll có còn security headers không?

**Có, nếu header-writing filter được cấu hình và chạy.** Ví dụ `HeaderWriterFilter` của Spring Security có thể thêm các header mặc định như `X-Content-Type-Options: nosniff` hoặc `X-Frame-Options: DENY`. Chính xác những header nào xuất hiện còn phụ thuộc cấu hình, giao thức HTTP/HTTPS và phiên bản. **Content-Security-Policy không phải lúc nào cũng được bật mặc định**, nên muốn CSP phải cấu hình phù hợp.

### permitAll có tắt CSRF không?

**Không.** CSRF là một cơ chế kiểm tra riêng, thường áp dụng với các HTTP method thay đổi trạng thái khi CSRF protection bật. Ví dụ `POST /public/submit` có thể nhận `403 Forbidden` do thiếu CSRF token **dù URL được `permitAll`**. Đó là hai điều kiện độc lập: được phép tại authorization nhưng vẫn phải đáp ứng quy tắc CSRF.

Không tắt CSRF toàn cục chỉ để “sửa lỗi 403” khi website còn dùng cookie/session. Nếu API stateless thực sự chỉ xác thực qua bearer token gửi chủ động, cách xử lý CSRF khác và phải xét đúng mô hình credential.

### permitAll có bỏ qua authentication filter không?

**Không.** Một endpoint công khai không yêu cầu xác thực thành công để vượt qua bước authorization, nhưng các filter xác thực đang bật có thể vẫn xử lý credential được gửi. Ví dụ client cố gửi `Authorization: Basic ...` sai tới endpoint công khai, `BasicAuthenticationFilter` có thể phản hồi lỗi xác thực **trước khi controller chạy**. Vì vậy “public” không đồng nghĩa “mọi loại credential sai đều bị bỏ qua”.

Trên các bản Spring Security hiện đại dùng `authorizeHttpRequests`, bộ authorization cho `permitAll` thường không cần truy vấn `Authentication` chỉ để ra quyết định cho phép; lợi ích này không có nghĩa tất cả filter khác ngừng chạy.

### permitAll có làm mất thông tin người dùng đã đăng nhập không?

**Không tự động.** Khi request mang session/bearer credential hợp lệ và chain xử lý theo cấu hình, controller hoặc service có thể thấy authentication hiện tại. Trang công khai có thể cá nhân hóa cho người dùng đã đăng nhập nhưng vẫn cho anonymous truy cập. Điều này khác với việc loại toàn bộ Spring Security filter khỏi request.

## 3. WebSecurityCustomizer.ignoring: bỏ qua security filter chain

`WebSecurityCustomizer` là cấu hình ở mức `WebSecurity`, thường dùng như sau:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/assets/**");
}
```

Đây là **lựa chọn thay thế có cân nhắc**, không phải phần bắt buộc của cấu hình mẫu `permitAll`. Khi một request khớp matcher bị ignore:

- Spring Security không chạy tập filter thông thường của `SecurityFilterChain` cho request đó.
- Spring Security không áp dụng authorization rule `hasRole`/`authenticated`/`permitAll` trên request bị ignore.
- CSRF protection, security headers và các cơ chế khác **được cung cấp bởi Spring Security filter chain** không được thực thi cho request bị ignore.
- Authentication/security context sẽ không được khởi tạo hoặc nạp **bởi các filter thuộc chain bị bỏ qua**. Những cơ chế độc lập bên ngoài Spring Security vẫn có thể tồn tại, nhưng không được dựa vào chúng như hệ quả của `ignoring`.

Ví dụ nếu vừa viết `web.ignoring().requestMatchers("/assets/**")`, vừa viết `requestMatchers("/assets/**").authenticated()` trong một security chain: request bị ignore sẽ không đi tới authorization rule đó. Rule mạnh hơn ở dưới không “bảo vệ lại” được URL đã bỏ qua từ trước.

**Cảnh báo thực hành:** Spring Security thường khuyến nghị **`permitAll` thay cho `ignoring`** đối với static resources trong các ứng dụng hiện đại. Lợi ích của bypass filter phải được cân nhắc cụ thể và đo lường; không dùng `ignoring` như cách giải quyết nhanh lỗi 401/403.

## 4. So sánh cơ chế và hệ quả

| Tiêu chí | `permitAll()` | `WebSecurityCustomizer.ignoring()` |
|---|---|---|
| Vị trí cấu hình | `HttpSecurity.authorizeHttpRequests` trong một `SecurityFilterChain` | `WebSecurity.ignoring` ở mức cấu hình web security |
| Request có đi qua Spring Security filters không? | **Có** (các filter của chain phù hợp vẫn xử lý) | **Không** đối với các filter của Spring Security chain |
| Có cần đăng nhập để qua URL authorization? | Không | Không xét authorization của Spring Security cho URL bị ignore |
| CSRF filter của Spring Security | Vẫn có thể áp dụng, tùy method/cấu hình | Không chạy thông qua security chain |
| Security headers do Spring Security viết | Có thể được thêm theo cấu hình | Không được thêm bởi security chain |
| Authentication hợp lệ đã gửi | Có thể được xử lý và đưa vào context | Không được xử lý bởi filter xác thực đã bị bỏ qua |
| `AuthorizationFilter` | Vẫn được chọn và áp dụng rule cho phép | Không chạy |
| Method security như `@PreAuthorize` | Là lớp kiểm soát độc lập, có thể chặn tiếp | Vẫn có thể hoạt động nếu đã bật, nhưng không nên dựa vào security context do chain bị bỏ qua cung cấp |
| Trường hợp phù hợp thường gặp | Trang công khai, login, health endpoint public có giới hạn, static assets | Chỉ request thực sự muốn đi ngoài **toàn bộ Spring Security filter chain**, rất hiếm |
| Rủi ro khi dùng sai | Nhầm CSRF/authentication-filter error với authorization error | Bỏ luôn headers, CSRF, ngữ cảnh xác thực và chính sách bảo vệ ở filter level |

Không nên đọc bảng như cam kết kết quả HTTP cố định. Một ứng dụng có thể có reverse proxy, servlet filter riêng, controller validation và exception handler thêm kiểm tra hoặc header độc lập. Bảng chỉ so sánh trách nhiệm của **Spring Security Servlet**.

## 5. Ví dụ hoàn chỉnh với permitAll và kiểm thử MockMvc

Ví dụ dưới đây dùng **Spring Boot 3.3.5 / Spring Security 6 do Boot quản lý / Java 17** như một mốc build cụ thể để dễ tái tạo cách hoạt động. Đây là **mốc minh họa**, không khẳng định bản này còn được hỗ trợ hoặc là bản stable mới nhất. Với dự án thật, chọn phiên bản Boot đang được hỗ trợ và kiểm tra yêu cầu JDK/dependency của bản chính xác đó.

Cấu trúc:

```text
security-permitall-demo/
├── pom.xml
└── src/
    ├── main/java/example/securitydemo/
    │   ├── SecurityDemoApplication.java
    │   ├── ServletSecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/securitydemo/
        └── SecurityBoundaryTest.java
```

### 5.1. Khai báo Maven

Tạo `pom.xml`:

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

    <groupId>example</groupId>
    <artifactId>security-permitall-demo</artifactId>
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
```

Không gắn phiên bản riêng cho `spring-security-web` hoặc `spring-security-config`: Spring Boot parent quản lý bộ phụ thuộc Spring tương thích.

### 5.2. Ứng dụng và controller

Tạo `src/main/java/example/securitydemo/SecurityDemoApplication.java`:

```java
package example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

Tạo `src/main/java/example/securitydemo/DemoController.java`:

```java
package example.securitydemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public String ping() {
        return "PUBLIC_OK";
    }

    @PostMapping("/public/submit")
    public String submit() {
        return "SUBMITTED";
    }

    @GetMapping("/private/data")
    public String privateData() {
        return "PRIVATE_OK";
    }
}
```

### 5.3. Chỉ cấu hình permitAll, không có ignore

Tạo `src/main/java/example/securitydemo/ServletSecurityConfig.java`:

```java
package example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Không vô hiệu hóa `csrf`. Nhờ vậy ví dụ thể hiện rõ: **POST tới URL permitAll vẫn có thể bị CSRF filter chặn**, còn GET tới URL đó được phục vụ công khai. `httpBasic` tạo cơ chế xác thực cho đường dẫn private; nếu thiếu credential, kết quả thường là HTTP 401. Spring Boot có thể sinh user/password mặc định dành cho phát triển khi chưa cấu hình UserDetailsService; demo không sử dụng tài khoản mặc định để kiểm thử.

### 5.4. Integration tests kiểm chứng thật sự có filter

Tạo `src/test/java/example/securitydemo/SecurityBoundaryTest.java`:

```java
package example.securitydemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicGetIsPermittedAndSecurityHeadersStillAppear() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }

    @Test
    void publicPostStillNeedsCsrfToken() throws Exception {
        mvc.perform(post("/public/submit"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicPostWithCsrfTokenIsPermitted() throws Exception {
        mvc.perform(post("/public/submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("SUBMITTED"));
    }

    @Test
    void privateGetWithoutLoginIsUnauthorized() throws Exception {
        mvc.perform(get("/private/data"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void privateGetWithMockUserIsAccessible() throws Exception {
        mvc.perform(get("/private/data"))
            .andExpect(status().isOk())
            .andExpect(content().string("PRIVATE_OK"));
    }
}
```

`@WithMockUser` đưa người dùng giả lập vào ngữ cảnh test, không tạo user production. Hàm `csrf()` từ `spring-security-test` tạo CSRF token hợp lệ cho request kiểm thử; không chứng minh ứng dụng production tự gửi CSRF token đúng.

Chạy với **JDK 17+ tương thích, Maven có trên PATH và internet hoặc Maven cache**:

```bash
mvn -version
mvn test
mvn spring-boot:run
```

Lệnh `mvn test` kỳ vọng **5 phép kiểm thử đều pass** trong đúng project/phiên bản trên. Maven không có chuỗi stdout cố định vì log phụ thuộc máy và môi trường; không diễn giải đây là kết quả đã thực thi nếu chưa chạy thật.

Khi server chạy cổng 8080 mặc định, mở terminal khác:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/private/data
curl -i -X POST http://localhost:8080/public/submit
```

Kết quả hành vi kỳ vọng:

| Request | HTTP status điển hình | Giải thích |
|---|---|---|
| `GET /public/ping` không credential | `200`, body `PUBLIC_OK` | URL permitAll, controller chạy; header bảo mật có thể được thêm |
| `GET /private/data` không credential | `401` | Rule `authenticated()` và HTTP Basic entry point |
| `POST /public/submit` không CSRF token | `403` | CSRF chặn dù URL permitAll |
| `POST /public/submit` có CSRF token hợp lệ | `200`, body `SUBMITTED` | Trong integration test dùng `with(csrf())` |

Đừng copy token giả của `MockMvc` vào curl: CSRF token thực tế liên quan cơ chế repository/session/cookie và cần được gửi đúng thiết kế. Đối với app dùng HTTP Basic trong trình duyệt, khả năng credential được gửi tự động là lý do không tùy tiện tắt CSRF.

## 6. Thử nghiệm ignoring để thấy khác biệt (chỉ trên môi trường học)

Giữ nguyên các file của mục 5 và **tạm thêm** vào `ServletSecurityConfig` một bean mới, cùng các import tương ứng:

```java
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

// Bên trong class ServletSecurityConfig:
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/public/**");
}
```

Đây là **mảnh cấu hình minh họa chèn vào class đã có**, không phải file Java độc lập. Cấu hình này cố tình bỏ qua Spring Security cho `/public/**` và **không được khuyến nghị** như cấu hình production cho endpoint động.

Khi thử trong project của mục 5:

- `GET /public/ping` vẫn do controller phục vụ, thường vẫn trả `200`; nhưng Spring Security không thêm `X-Content-Type-Options` cho route đã ignore.
- `POST /public/submit` không CSRF token giờ có thể được controller phục vụ và trả `200`, vì CSRF filter của Spring Security không chạy trên request đã ignore.
- `/private/data` vẫn dùng security chain như cũ vì **không** khớp matcher ignore.
- Một warning của Spring Security có thể chỉ ra việc ignoring các request không được khuyến nghị.

Các khác biệt này đúng khi **không có filter/proxy khác** bổ sung header hoặc chặn POST và khi ứng dụng giữ nguyên các cấu hình còn lại. Đây là lý do không dùng kết quả GET=200 đơn lẻ để kết luận hai cơ chế giống nhau.

**Sau khi quan sát, loại bỏ bean `WebSecurityCustomizer` tạm thêm** để trở về cấu hình an toàn dựa trên `permitAll` ở mục 5. Bài minh họa không sửa dữ liệu hay bảo mật của ứng dụng khác.

## 7. Static resources: khi nào nên permitAll, khi nào mới cân nhắc ignoring?

Ví dụ ứng dụng phục vụ CSS/JS/ảnh tĩnh tại `/assets/**`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/favicon.ico").permitAll()
    .anyRequest().authenticated())
```

Đây là mảnh code trong cấu hình `HttpSecurity`. Nếu dùng Spring Boot 3.x với MVC, bạn cũng có thể dùng matcher tiện ích `PathRequest.toStaticResources().atCommonLocations()` nếu khớp cấu trúc tài nguyên thực tế; đừng cho rằng nó bao phủ mọi thư mục static tự đặt.

**Ưu tiên permitAll** vì security headers vẫn được áp dụng, chính sách bảo mật và logging theo filter chain vẫn nhất quán, và dễ thay đổi cấu hình khi URL phát triển thành resource động. Với các phiên bản Security mới, `permitAll` cũng tránh nhiều bước lấy authentication không cần thiết chỉ để quyết định quyền, nên lý do hiệu năng để ignore tài nguyên tĩnh thường yếu hơn suy đoán.

Chỉ cân nhắc `ignoring` nếu đã chứng minh có một phạm vi tài nguyên hoàn toàn công khai, không chứa dữ liệu nhạy cảm, không cần **bất kỳ** Spring Security filter nào, và có bằng chứng hiệu năng/vận hành đủ mạnh. Khi đó cần kiểm tra kỹ security headers ở CDN/reverse proxy, cache, cơ chế xác thực và test âm tính; đừng áp dụng matcher rộng kiểu `/**`, `/api/**` hay `/admin/**`.

### Public endpoints khác static resources

- **Trang đăng nhập, trang thông tin công khai, API trả dữ liệu public:** thường dùng `permitAll` vì vẫn cần xử lý HTTP security.
- **API webhook hoặc callback không dựa vào đăng nhập người dùng:** không suy rằng phải `ignore`. Thường vẫn cần chữ ký HMAC, OAuth, mTLS hoặc kiểm tra bí mật tại ứng dụng và có thể dùng `permitAll` tại URL authorization nếu phù hợp.
- **Health/readiness endpoint:** có thể công khai ở mức giới hạn hoặc cần xác thực tùy môi trường. Không bỏ qua toàn bộ chain chỉ vì endpoint phục vụ giám sát; xác định rõ dữ liệu tiết lộ.
- **CORS preflight (OPTIONS):** cấu hình CORS và xử lý preflight đúng với Spring Security; không dùng `web.ignoring("/**")` hay ignore API để che lỗi CORS.
- **Actuator, Swagger/OpenAPI, static app bundle:** quyết định phạm vi public riêng; đừng mở nguyên `/actuator/**` hoặc `/api/**` chỉ để truy cập được một vài tài nguyên.

## 8. Đừng nhầm ignoring với securityMatcher và nhiều SecurityFilterChain

Hai API khác nhau:

- `http.securityMatcher("/api/**")`: xác định **phạm vi request mà SecurityFilterChain này quản lý**.
- `auth.requestMatchers("/api/public/**").permitAll()`: xác định **quy tắc authorization bên trong chain đã chọn**.
- `web.ignoring().requestMatchers("/assets/**")`: loại request khỏi **Spring Security filter chain**.

Ví dụ nhiều chuỗi:

```java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **mảnh code độc lập về mặt hai method bean**, nhưng để đặt vào class cấu hình Java vẫn cần import `@Bean`, `@Order`, `HttpSecurity`, `Customizer` và `SecurityFilterChain`. Đừng chép cùng lúc với bean `securityFilterChain` ở mục 5 mà không điều chỉnh thiết kế.

Theo thứ tự `@Order`, request `/api/public/ping` chọn chain API rồi được `permitAll` **trong chain đó**; request ngoài `/api/**` được chain fallback kiểm soát. Nếu chỉ định securityMatcher hẹp nhưng **không có chain fallback**, những request không khớp bất kỳ security chain nào có thể đi ngoài sự bảo vệ của Spring Security; đó là cấu hình nguy hiểm nếu vô tình để hở endpoint.

**Chọn chain đầu tiên khớp** là cơ chế khác với “chạy lần lượt tất cả chain”. Vì vậy rule `permitAll` ở một chain không có tác dụng cho request đã bị chọn vào chain trước đó; đừng suy đoán kết quả nếu chưa xác định chain nào xử lý request.

## 9. Một số hiểu lầm quan trọng khi kiểm thử

### “permitAll thì mọi filter đều bị bỏ qua”

Sai: `permitAll` không tắt `CsrfFilter`, `HeaderWriterFilter`, các authentication filter hay custom filter nằm trong chain. Hãy viết test GET public có header bảo mật và POST public không CSRF token, như ví dụ ở mục 5.

### “Nếu dùng ignoring, @PreAuthorize chắc chắn vô hiệu”

Không chính xác. **Method security** là một lớp kiểm tra độc lập ở phương thức nếu đã bật qua `@EnableMethodSecurity`. Một method có `@PreAuthorize` vẫn có thể từ chối lời gọi. Tuy nhiên khi URL bị ignore, thông tin authentication có thể không được nạp vào `SecurityContextHolder` bởi web security filters; kết quả tùy cách method security lấy principal và cấu hình khác. Không dựa vào method security để biện minh cho việc bỏ toàn bộ web filters.

### “Đặt permitAll ở phía dưới anyRequest vẫn có tác dụng”

Thông thường không. Rules phải được cấu hình ở **thứ tự hợp lệ**, từ matcher cụ thể đến fallback; `anyRequest()` là luật bắt toàn bộ request còn lại. Nếu cấu hình matchers sai thứ tự, Spring Security có thể báo lỗi hoặc rule cụ thể không đạt hiệu quả dự định. Hãy bảo đảm:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated())
```

### “WebSecurityCustomizer.ignoring là cách sửa 403 CSRF”

Đó là cách **né tránh** CSRF filter, có thể mở ra lỗ hổng CSRF nếu browser tự gửi credential. Xác định method, session/cookie, token và yêu cầu bảo vệ; cấu hình CSRF đúng ở `HttpSecurity` thay vì bỏ toàn bộ filter chain.

### “Đường dẫn được ignore nên mọi Spring Security config đều không liên quan”

Với request bị ignore, Security filter chain không xử lý; nhưng vẫn có thể tồn tại global servlet filters, Reverse Proxy/CDN headers, controller validation, method security độc lập và các interceptor khác. Trong phân tích sự cố phải quan sát **đường đi HTTP thực tế**.

### “Chỉ cần GET trả 200 là chứng minh public route đã được bảo vệ đúng”

Không đủ. Cần kiểm tra cả 401/403, anonymous vs authenticated, POST không CSRF token, security headers, login/logout, filter logs và điều kiện truy cập theo vai trò. Một endpoint trả 200 có thể đã đi qua permitAll hoặc bypass mọi security filter; chỉ dựa status không thể phân biệt.

## 10. Cách chẩn đoán request được filter nào xử lý

1. **Xác định Servlet stack:** có `spring-boot-starter-web`, cấu hình `HttpSecurity` và bean `SecurityFilterChain`; không nhầm với `SecurityWebFilterChain` của WebFlux.
2. **Liệt kê security matcher:** xem `WebSecurityCustomizer`, `securityMatcher`, `@Order` của nhiều chain và fallback `anyRequest`.
3. **Xem logs khi phát triển:** cấu hình logging của `org.springframework.security` ở mức DEBUG chỉ trên môi trường phù hợp; Spring Security có thể ghi thông tin chọn/áp dụng filter, không bật DEBUG lâu dài trên production nếu log chứa dữ liệu nhạy cảm.
4. **Kiểm tra cơ chế cụ thể:** header mặc định, CSRF khi POST, basic/bearer credential không hợp lệ, anonymous/private authorization.
5. **Chạy MockMvc integration tests:** kiểm tra status, header, body và CSRF, kết hợp test service/method authorization theo nghiệp vụ.
6. **Đối chiếu với Servlet filter ngoài Security:** nếu đã ignore nhưng header/kiểm tra vẫn xuất hiện, tìm filter/proxy khác thay vì khẳng định `ignoring` không hoạt động.

Khi debug authorization, tránh kết luận “403 là do `hasRole`” trước khi xác định request có bị chặn bởi CSRF filter hoặc bởi service/method security không.

## 11. Chọn cấu hình theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Điều cần xác minh |
|---|---|---|
| Trang HTML public nhưng dùng session/cookie | `permitAll` | CSRF cho form POST, security headers, session |
| Controller GET công khai, có thể cá nhân hóa khi login | `permitAll` | Authentication được xử lý nếu có; anonymous vẫn truy cập |
| REST public trả dữ liệu không nhạy cảm | `permitAll` | CORS, rate limit/abuse controls, header, quy tắc method |
| Static CSS/JS/images của web MVC | Thường `permitAll` | Caching/CDN, security headers, hiệu năng đã đo |
| Health endpoint ở nội bộ | `permitAll` hoặc `authenticated` tùy chính sách | Không lộ thông tin vận hành nhạy cảm |
| Tài nguyên thật sự muốn bypass **mọi Spring Security filter** | Chỉ cân nhắc `ignoring` với ngoại lệ rất hẹp | Rủi ro headers/CSRF/authentication, tài liệu và test rõ |
| API bảo vệ bằng bearer token | Chain phù hợp + `oauth2ResourceServer` / `authenticated` / scope rules | Token validity, issuer/audience, policy; không ignore API |
| Đường dẫn với authorization khác nhau theo HTTP method | `requestMatchers(HttpMethod, path)` + rules cụ thể | CSRF độc lập với authorization và method safety |

**Quy tắc thực hành:** khi yêu cầu là **“không cần đăng nhập để truy cập URL”**, hãy bắt đầu bằng `permitAll`. Chỉ sử dụng `ignoring` khi yêu cầu thực sự là **“không chạy Spring Security filter nào cho request này”**, và hậu quả đã được hiểu rõ.

### Câu hỏi tự kiểm tra

**1.** `POST /public/submit` đã `permitAll`, vì sao HTTP 403?  
*Đáp án:* CSRF filter vẫn chạy và có thể từ chối POST thiếu token; authorization cho phép không đồng nghĩa tắt CSRF.

**2.** Cùng một static URL, tại sao dùng `ignoring` thì Spring Security không thêm header mặc định?  
*Đáp án:* Request không đi qua filter viết header trong Spring Security chain. Header có thể vẫn do thành phần khác thêm nhưng không phải nhờ chain đó.

**3.** Có thể dùng `web.ignoring().requestMatchers("/api/**")` rồi `hasRole("ADMIN")` để bảo vệ API không?  
*Đáp án:* Không. Ignore khiến request không tới authorization rule trong chain. Không dùng cách này cho API bảo vệ.

**4.** Khi website MVC cần trang chủ public nhưng vẫn muốn biết user đã đăng nhập, nên dùng gì?  
*Đáp án:* `permitAll`; security filters vẫn có thể nạp authentication hợp lệ, còn anonymous vẫn được phép.

**5.** `http.securityMatcher("/api/**")` có phải tương đương `web.ignoring().requestMatchers("/api/**")`?  
*Đáp án:* Không. `securityMatcher` giới hạn một chain xử lý URL; `ignoring` loại URL khỏi Spring Security filters.

**Kết luận:** `permitAll()` **cho phép ở bước phân quyền nhưng vẫn duy trì Spring Security filter chain**; `WebSecurityCustomizer.ignoring()` **bỏ qua chính filter chain đó**. Với phần lớn endpoint công khai trong Spring MVC/Servlet, `permitAll` là lựa chọn ít bất ngờ và giữ được các lớp bảo vệ HTTP.