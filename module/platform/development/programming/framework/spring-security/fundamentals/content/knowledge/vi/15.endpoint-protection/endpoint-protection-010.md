# Kiểm tra đường dẫn ngoài dự kiến để phát hiện khoảng trống bảo vệ

> **Phạm vi:** Spring Security cho ứng dụng **Spring MVC/Servlet**, tập trung vào **kiểm thử phủ định (negative security testing)** đối với các URL, HTTP method và điểm vào nằm ngoài danh sách endpoint dự kiến. Ví dụ sử dụng **Java 17, Spring Boot 3.5.0, Spring Security 6.x, JUnit 5 và MockMvc**. Các nguyên tắc kiểm thử ranh giới cũng áp dụng cho WebFlux, nhưng WebFlux dùng `ServerHttpSecurity`/`SecurityWebFilterChain` và `WebTestClient` thay vì các API Servlet trong ví dụ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu thế nào là một **khoảng trống bảo vệ endpoint**: request có thể đi đến controller, servlet, filter, Actuator hoặc một route mới mà không chịu chính sách authorization như dự kiến.
2. Phân biệt **endpoint hợp lệ được phép** với **đường dẫn ngoài dự kiến phải bị từ chối**, kể cả khi caller đã đăng nhập hoặc có quyền cao.
3. Dùng `requestMatchers`, `securityMatcher`, thứ tự `SecurityFilterChain` và `anyRequest().denyAll()` để thiết kế mặc định an toàn.
4. Tạo ma trận test cho đường dẫn biến thể, HTTP method, cấu hình nhiều filter chain, đường dẫn mới, context path, reverse proxy và URL có encoding bất thường.
5. Viết **MockMvc + Spring Security Test** để xác minh các đường dẫn ngoài dự kiến không trả thành công và không rò rỉ dữ liệu.
6. Phân biệt lỗi **401, 403, 404, 400** và những gì một status đơn lẻ *chưa chứng minh được*.
7. Đưa việc tìm đường dẫn thiếu bảo vệ vào quy trình cập nhật API và CI.

## 2. Vấn đề: bảo vệ những URL đã biết vẫn có thể để hở URL khác

Giả sử một ứng dụng có ba endpoint đã được xác định rõ:

| HTTP | Path | Ý định |
| --- | --- | --- |
| GET | `/api/public/ping` | Công khai |
| GET | `/api/account/me` | Chỉ người đăng nhập |
| GET | `/api/admin/report` | Chỉ người có role `ADMIN` |

Nhóm phát triển kiểm tra ba đường dẫn này đều đúng. Nhưng về sau có thêm một controller:

```java
@GetMapping("/api/experimental/export")
String export() {
    return "sensitive-export";
}
```

Nếu cấu hình bảo mật chỉ áp dụng cho `/api/admin/**`, còn request khác được `permitAll()` hoặc rơi **ngoài mọi `SecurityFilterChain`**, endpoint mới có thể bị gọi mà không qua kiểm soát mong muốn.

Đây là điểm mấu chốt của bài:

> **Không chỉ kiểm tra "đường dẫn cần bảo vệ đã được bảo vệ chưa", mà còn kiểm tra "mọi đường dẫn chưa được phê duyệt có bị đóng hay không".**

"Đường dẫn ngoài dự kiến" có thể là route mới bị quên phân quyền, URL dự phòng/legacy, đường dẫn gần giống route hợp lệ, method khác trên cùng URL, đường dẫn do một filter/servlet khác đăng ký, hoặc URL được proxy/servlet chuẩn hóa theo cách khác người viết matcher dự đoán.

Một test chỉ gọi `GET /api/admin/report` bằng user không có role chưa đủ để phát hiện các trường hợp đó. Cần có **bài kiểm thử ranh giới** (boundary/negative test) bao phủ cả các đường vào chưa liệt kê.

## 3. Ba lớp cần kiểm tra riêng

### 3.1. Lớp chọn `SecurityFilterChain`

Spring Security dùng `FilterChainProxy` lựa chọn một `SecurityFilterChain` phù hợp với request. Nếu khai báo `http.securityMatcher("/api/**")`, chain đó chỉ được áp dụng cho request khớp `/api/**`.

**Nguy cơ:** cấu hình **chỉ có** một chain giới hạn `/api/**` có thể để `/internal/**`, `/legacy/**` hoặc endpoint mới ở ngoài sự bảo vệ của Spring Security. `anyRequest()` bên trong chain `/api/**` **không** áp dụng cho đường dẫn không khớp chain.

### 3.2. Lớp chọn rule trong chain

Bên trong `authorizeHttpRequests`, Spring Security xét các `requestMatchers` theo **thứ tự khai báo** và dùng rule khớp đầu tiên. Ví dụ:

```java
// Ví dụ lỗi về thứ tự: rule quá rộng đứng trước rule admin.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Route admin đã khớp rule `/api/**`, nên rule `hasRole("ADMIN")` phía sau không còn cơ hội bảo vệ. Test trên `/api/admin/report` phải phát hiện điều này.

### 3.3. Lớp định tuyến của ứng dụng và hạ tầng

Spring MVC, servlet container, reverse proxy, gateway, Actuator, WebSocket handshake và các route do filter cung cấp có thể hiểu đường dẫn khác nhau. `@GetMapping("/api/admin/report")` và một matcher bảo mật riêng có thể lệch nhau khi ứng dụng đổi context path, servlet path, xử lý trailing slash, encoded slash hoặc khi thêm một servlet.

Vì vậy, cần kiểm tra cả **cấu hình bảo mật**, **mapping thực tế** và **đường đi HTTP sau khi triển khai**. Test MockMvc có giá trị lớn nhưng không mô phỏng đầy đủ mọi cấu hình của proxy hoặc container production.

## 4. Nguyên tắc thiết kế: danh sách cho phép + mặc định từ chối

Với API có chính sách route chặt chẽ, một cấu hình dễ kiểm tra là:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/account/me").authenticated()
    .requestMatchers(HttpMethod.GET, "/api/admin/report").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Giải thích:

- `permitAll()` chỉ áp dụng cho GET của đúng route ping công khai.
- `authenticated()` yêu cầu xác thực nhưng không tự kiểm tra quyền trên tài nguyên cụ thể.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` theo quy ước mặc định; truyền `"ADMIN"` chứ không phải `"ROLE_ADMIN"` vào `hasRole`.
- `anyRequest().denyAll()` từ chối mọi yêu cầu **đã vào chain này** nhưng không khớp các rule trên. Vì vậy, nếu endpoint mới được triển khai mà người viết quên khai báo chính sách, route đó **không tự trở thành public**.
- Việc khai báo `HttpMethod.GET` còn khiến `POST`, `PATCH`, `DELETE` hoặc một method khác trên cùng path không tự nhận quyền của GET.

Không phải ứng dụng nào cũng cần deny-all trên mọi URL: trang web có tài nguyên tĩnh, login hoặc endpoint nghiệp vụ cần những rule tương ứng. Tuy nhiên, mỗi trường hợp được phép phải được **định nghĩa và kiểm thử có chủ đích**. Nếu dùng fallback `authenticated()`, hãy hiểu đó là quy tắc "mọi người đã đăng nhập có thể đi qua"; nó không tự chặn một endpoint nhạy cảm vừa được bổ sung.

**Cảnh báo quan trọng:** nếu dùng nhiều chain có `securityMatcher`, cần một **chain cuối cùng phủ mọi request** hoặc một cơ chế bảo vệ toàn cục tương đương. `denyAll()` ở chain giới hạn sẽ không bảo vệ URL ngoài chain.

## 5. Chuẩn bị ví dụ chạy được với Spring Boot

Ta tạo API có ba endpoint hợp lệ và **một endpoint chưa được phê duyệt** `/api/experimental/export`. Route cuối này cố ý tồn tại trong demo để chứng minh fallback từ chối **ngay cả khi controller thật sự có thể xử lý request**; nó không chỉ nhận 404 vì "chưa có handler".

### 5.1. Cấu trúc dự án

```text
route-boundary-demo/
├── pom.xml
├── src/
│   ├── main/java/demo/routes/
│   │   ├── RouteBoundaryApplication.java
│   │   ├── SecurityConfig.java
│   │   └── DemoController.java
│   └── test/java/demo/routes/
│       └── EndpointSecurityTest.java
```

Cần **JDK 17+** và Maven. Ví dụ dùng Maven parent cố định `3.5.0` để tránh mơ hồ về phụ thuộc; với dự án thật hãy dùng bản vá được hỗ trợ mới nhất tương thích với hệ thống.

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>route-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

`spring-security-test` cung cấp `user(...)`, `csrf()` và công cụ test Spring Security với MockMvc. `spring-boot-starter-test` cung cấp JUnit, AssertJ và Spring Test.

### 5.3. Điểm khởi động

`src/main/java/demo/routes/RouteBoundaryApplication.java`:

```java
package demo.routes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RouteBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RouteBoundaryApplication.class, args);
    }
}
```

### 5.4. Controller có route dự kiến và route bất ngờ

`src/main/java/demo/routes/DemoController.java`:

```java
package demo.routes;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/account/me")
    public String me(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "REPORT_PRIVATE";
    }

    // Có handler nhưng chưa được cấp phép trong SecurityConfig.
    @GetMapping("/experimental/export")
    public String experimentalExport() {
        return "UNRELEASED_EXPORT";
    }
}
```

Route `/experimental/export` là **fixture học tập**: mục đích của nó là chứng minh luật mặc định từ chối. Trong dự án thật, một route thử tương tự nên được đặt trong test profile/fixture thay vì vô tình đóng gói một endpoint không dùng đến vào production.

### 5.5. SecurityConfig với fallback rõ ràng

`src/main/java/demo/routes/SecurityConfig.java`:

```java
package demo.routes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/account/me"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/api/admin/report"
                ).hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

Một điểm chủ ý: **không gọi `securityMatcher`** trong chain duy nhất này, nên chain có matcher mặc định áp dụng cho mọi request của ứng dụng Spring Security. Điều kiện `anyRequest().denyAll()` bao phủ URL chưa liệt kê, bao gồm route fixture `/api/experimental/export`.

Tài khoản trong bộ nhớ và mật khẩu tĩnh chỉ dành cho demo. Trong production, dùng cơ chế xác thực phù hợp, TLS, lưu mật khẩu an toàn và không phát hành tài khoản minh họa.

**CSRF vẫn bật mặc định** trong cấu hình này. Với request ghi `POST/PATCH/DELETE` từ MockMvc, thêm `with(csrf())` để test authorization sau khi vượt qua CSRF; không tắt CSRF chỉ để một bài test dễ chạy. Việc có cần vô hiệu CSRF cho API stateless phụ thuộc **cách truyền thông tin xác thực** và nguy cơ browser tự gửi credentials.

## 6. Kiểm thử tự động để phát hiện các khoảng trống

Tạo `src/test/java/demo/routes/EndpointSecurityTest.java`:

```java
package demo.routes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingCanBeCalledWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void accountEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/api/account/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/account/me")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:reader"));
    }

    @Test
    void adminEndpointRejectsAReader() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanUseOnlyApprovedAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT_PRIVATE"));
    }

    @Test
    void existingButUnlistedHandlerIsDenied() throws Exception {
        // Handler có tồn tại trong DemoController,
        // nhưng không có rule nào cho phép đi tới nó.
        mvc.perform(get("/api/experimental/export")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void nearMissRoutesAreDeniedEvenForAdmin() throws Exception {
        String[] unapprovedPaths = {
            "/api/admin/report/",
            "/api/admin/report.json",
            "/api/admin/report/extra",
            "/api/admin",
            "/API/admin/report",
            "/api/admin/REPORT",
            "/internal/admin/report"
        };

        for (String path : unapprovedPaths) {
            var response = mvc.perform(
                    get(path).with(user("admin").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andReturn()
                .getResponse();

            assertThat(response.getContentAsString())
                .doesNotContain("REPORT_PRIVATE")
                .doesNotContain("UNRELEASED_EXPORT");
        }
    }

    @Test
    void unexpectedPostCannotReuseGetPermission() throws Exception {
        mvc.perform(post("/api/admin/report")
                .with(user("admin").roles("ADMIN"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicGetDoesNotOpenPostAtSamePath() throws Exception {
        mvc.perform(post("/api/public/ping")
                .with(user("reader").roles("USER"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

Để chạy:

```bash
mvn test
mvn spring-boot:run
```

Khi Maven hoàn tất bình thường, bộ test trên có **8 phương thức `@Test`** và dự kiến tất cả đều pass. Đây là **kết quả kỳ vọng từ source demo**, không phải log chạy thực tế của một dự án đã được khởi động trong bài đọc này.

Các kiểm tra đóng góp khác nhau:

- **Positive controls:** URL công khai hoạt động; admin thật sự truy cập được URL admin đúng. Nếu toàn bộ ứng dụng bị chặn, các test phủ định có thể "xanh" mà hệ thống vẫn bị cấu hình sai.
- **Negative controls:** user thường không được vào admin; endpoint có handler nhưng chưa cấp phép vẫn bị deny; ngay cả admin cũng không được vào URL lệch quy tắc.
- **Method boundary:** rule GET không mở quyền POST. `csrf()` bảo đảm lỗi 403 được đo ở tầng authorization thay vì chỉ do thiếu CSRF token.
- **No-leak assertion:** body của response bị từ chối không chứa marker dữ liệu nhạy cảm, bên cạnh kiểm tra status.

**Lưu ý:** các trường hợp đổi path thông thường ở đây dự kiến **403** do `anyRequest().denyAll()`. Với URL chưa có handler nhưng **không** bị chặn sớm, MVC có thể trả **404**; với URL bị `HttpFirewall` từ chối, tầng HTTP có thể trả **400** hoặc xử lý khác theo cấu hình. Đừng áp đặt 403 cho mọi chuỗi URL kỳ dị, đặc biệt với request lỗi cú pháp. Mục tiêu bất biến là **không truy cập trái phép và không rò rỉ nội dung**.

### 6.1. Kiểm tra qua HTTP thực

Khởi động ứng dụng ở cổng 8080 và thực hiện:

```bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/account/me
curl -i -u reader:reader-demo http://localhost:8080/api/admin/report
curl -i -u admin:admin-demo http://localhost:8080/api/admin/report
curl -i -u admin:admin-demo http://localhost:8080/api/admin/report/
curl -i -u admin:admin-demo http://localhost:8080/api/experimental/export
```

Với demo, các status dự kiến theo thứ tự là **200, 401, 403, 200, 403, 403**. Chỉ request thứ tư có quyền nhận body `REPORT_PRIVATE`. Không sử dụng tài khoản/password cố định của demo bên ngoài môi trường local.

Test trên server thực có giá trị bổ sung cho MockMvc vì container, reverse proxy và đường vào mạng thật có thể thay đổi cách xử lý URL. Khi có reverse proxy, lặp lại bài test qua **địa chỉ public sau proxy**, thay vì chỉ gọi loopback.

## 7. Xây ma trận đường dẫn ngoài dự kiến

Không thử ngẫu nhiên một vài URL rồi kết luận đã kín. Hãy lấy **danh sách endpoint thực tế** làm gốc, sau đó có hệ thống tạo những nhóm biến thể:

| Nhóm | Ví dụ từ `/api/admin/report` | Điều cần xác minh |
| --- | --- | --- |
| Thiếu/thừa segment | `/api/admin`, `/api/admin/report/extra` | Không vô tình khớp rule quá rộng |
| Trailing slash | `/api/admin/report/` | Bảo mật và controller hiểu nhất quán |
| Chữ hoa/thường | `/API/admin/report`, `/api/admin/REPORT` | Không dựa vào giả định case normalization |
| Phần mở rộng | `/api/admin/report.json`, `/api/admin/report.csv` | Endpoint alias hoặc suffix không mở quyền |
| Method khác | POST/PUT/PATCH/DELETE/HEAD/OPTIONS cùng path | Phân quyền theo hành động, CORS/HEAD đúng thiết kế |
| Đường dẫn cũ | `/admin/report`, `/v1/admin/report` | Không bỏ quên alias, redirect, route deprecated |
| Trùng hoặc lặp dấu phân cách | `/api//admin/report` | Xác minh proxy, container, firewall xử lý nhất quán |
| Dot segment | `/api/../api/admin/report` | Không có khác biệt authorization sau normalization |
| Encoded separator | `/api/admin%2Freport`, `/api/admin/report%2F` | Không bypass bằng mã hóa dấu `/` |
| Semicolon/matrix parameter | `/api/admin;v=1/report` | Firewall và matcher không bất đồng |
| Đường dẫn servlet khác | `/internal/admin/report` | Không rơi ngoài tất cả filter chain |
| Context path/proxy prefix | `/app/api/admin/report` khi app mount dưới `/app` | Matcher tương ứng với đường dẫn mà Spring Security thực tế thấy |
| API chưa công bố | `/api/experimental/export` | Fallback phải deny ngay cả khi có handler |
| Error/forward dispatch | Request chuyển sang `/error` hoặc internal forward | Không mở đường vòng trái ý định |
| Endpoint vận hành | `/actuator/**`, health, metrics, mappings | Có chính sách và bề mặt mạng riêng |

**Quan trọng về query string:** `/api/admin/report?format=csv` vẫn có **cùng path** `/api/admin/report`; một matcher chỉ dựa vào path thường **không** coi đây là đường dẫn khác. Nếu `format=csv` thay đổi dữ liệu hoặc hành động được thực hiện, cần kiểm tra ở tầng service/policy của chức năng; không mặc định rằng thay query parameter sẽ bị fallback chặn.

### 7.1. URL encoding và `StrictHttpFirewall`

Spring Security có `HttpFirewall` để bảo vệ khỏi các biến thể URL gây bất đồng giữa servlet container và matcher. `StrictHttpFirewall` theo mặc định từ chối nhiều request đáng ngờ như dấu `;`, encoded slash, backslash hoặc đường dẫn không được chuẩn hóa. **Không nên nới lỏng firewall chỉ để một URL lạ "chạy được"** nếu không có yêu cầu nghiệp vụ và phân tích sự khác biệt giữa các lớp.

Những trường hợp này cần test ở **hạ tầng thật**, vì MockMvc, Tomcat/Jetty/Undertow, gateway, CDN và proxy có thể có cách decode hoặc chuẩn hóa khác nhau. Với môi trường kiểm thử được phép, có thể dùng:

```bash
# Giữ dot-segment nguyên trạng đến phía server/proxy trong phạm vi curl cho phép.
curl --path-as-is -i -u reader:reader-demo \
  'http://localhost:8080/api/../api/admin/report'

# Encoded slash: phản hồi cụ thể phụ thuộc container/firewall.
curl -i -u reader:reader-demo \
  'http://localhost:8080/api/admin%2Freport'
```

Điều cần ghi nhận là raw URL, HTTP method, response status/body, **request có đến controller nhạy cảm không** và phiên bản/config của proxy, container, Spring Security. Một phản hồi 400 do firewall từ chối hoàn toàn có thể là kết quả bảo mật đúng.

### 7.2. HTTP method và method override

Nhiều chính sách chỉ định `GET`, `POST`...; test phải thử những method không nằm trong hợp đồng API. Đặc biệt:

- **HEAD:** một số framework tự hỗ trợ HEAD cho GET; trong ví dụ, policy method GET không có nghĩa HEAD tự động được phép. Nếu cần HEAD, định nghĩa và test có chủ đích.
- **OPTIONS/CORS:** preflight có quy tắc riêng; bảo vệ đúng phải cho phép preflight hợp lệ mà không mở dữ liệu nhạy cảm. Không kết luận rằng `OPTIONS 200` đồng nghĩa bất kỳ caller nào cũng gọi được GET.
- **POST/PUT/PATCH/DELETE:** cần test CSRF phù hợp để không nhầm lỗi CSRF với authorization.
- **Method override:** nếu ứng dụng bật `HiddenHttpMethodFilter` hoặc cơ chế `X-HTTP-Method-Override` của proxy, cần kiểm tra **method cuối cùng mà router và security nhìn thấy**. Đừng tự cấu hình hỗ trợ override nếu ứng dụng không cần.

## 8. Lỗi phổ biến: một `SecurityFilterChain` chỉ phủ `/api/**`

Xét cấu hình sau:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

*Đây là phần code minh họa, không phải file độc lập trong demo mục 5.*

Nếu đây là **chain duy nhất**, request tới `/internal/status` hoặc `/legacy/export` không khớp `/api/**`. Spring Security không tự áp một fallback authorization rule từ chain này lên chúng. Nếu các URL đó có handler, có thể bị bỏ qua Spring Security.

Một cấu hình nhiều chain thường cần **catch-all cuối cùng**:

```java
// Đặt trong cùng class @Configuration của kiến trúc nhiều chain.
// Đây là minh họa thay thế, không ghép thêm vào demo mục 5.
@Bean
@org.springframework.core.annotation.Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
```

Sự khác biệt:

- `securityMatcher` quyết định **chain nào nhận request**; `requestMatchers` quyết định **rule nào áp dụng bên trong chain đó**.
- `@Order(1)` cho chain cụ thể quyền được xét trước; chain mặc định không khai `securityMatcher` phải được xét sau.
- `anyRequest().denyAll()` ở fallback **mới** bao phủ các route không thuộc `/api/**`.
- `anyRequest().authenticated()` trong chain API chỉ là chính sách login, chưa đủ cho tất cả thao tác nhạy cảm theo đối tượng/role. Trong hệ thống thật cần thay bằng các rule chi tiết theo chức năng.

**Chú ý khi gắn nhiều servlet:** Nếu ứng dụng có nhiều Servlet hoặc thay đổi servlet path, hãy kiểm tra matcher gắn đúng servlet. Không thể chỉ đọc chuỗi URL từ trình duyệt rồi suy ra chính xác giá trị path mà từng matcher thấy.

## 9. Chống bỏ sót route mới bằng inventory và kiểm thử ràng buộc

### 9.1. Tạo bản kê endpoint thực tế

Đối chiếu ít nhất ba nguồn:

1. **Ứng dụng runtime:** các mapping từ Spring MVC `RequestMappingHandlerMapping`, các router function, servlet/filter do thư viện đăng ký, endpoint do Spring Security tự cung cấp và Actuator.
2. **Hợp đồng API:** OpenAPI, tài liệu endpoint, bảng phân quyền nghiệp vụ và đường dẫn public được phê duyệt.
3. **Hạ tầng triển khai:** gateway route, reverse proxy rewrite, context path, management port, ingress rule và các URL legacy.

`/actuator/mappings` có thể giúp kiểm kê một phần mapping khi được cấu hình/expose **chỉ trong môi trường và phạm vi truy cập an toàn**. Không mở công khai endpoint mappings/beans/env chỉ để phục vụ test. Chỉ nhìn OpenAPI cũng chưa chắc thấy hết endpoint do thư viện, filter hoặc servlet tạo ra.

Đối chiếu mỗi route bằng bộ ba `(HTTP method, effective path pattern, security policy)` và có thể mở rộng bằng actor/role, tenant, phiên bản API và nguồn chain.

### 9.2. Một phương pháp CI có tính tái sử dụng

- **Baseline:** lấy danh sách route đã phê duyệt từ repo/config. Gắn cho mỗi route trạng thái public, authenticated, role/scope hoặc custom authorization.
- **So khớp:** phát hiện route runtime mới không có chính sách trong baseline; yêu cầu cập nhật rule/test nếu đây là tính năng hợp lệ.
- **Negative tests:** sinh các biến thể ngoài hợp đồng cho route nhạy cảm, cùng những đường dẫn tồn tại nhưng chưa phê duyệt. Caller kiểm tra phải gồm **anonymous**, **user thông thường**, và khi cần cả **admin**, vì người có quyền cao vẫn không nên đi vào route chưa công bố.
- **Positive tests:** giữ kiểm tra rằng các route hợp lệ tiếp tục hoạt động. Điều này tránh trường hợp "mọi thứ đều bị cấm" nhưng test an ninh vẫn báo xanh.
- **Integration smoke:** chạy thêm qua reverse proxy/server thật cho các chuỗi URL bất thường. Không dùng MockMvc làm bằng chứng duy nhất về URL normalization.
- **Review khi thay đổi:** khi có controller mới, đổi mapping, thêm chain, sửa gateway, cài Actuator hoặc thêm servlet, cập nhật inventory và regression tests.

Đừng yêu cầu mọi URL đoán ngẫu nhiên đều trả đúng một status cố định. Gắn kỳ vọng theo **chính sách**: route hợp lệ có quyền → thành công; route có tồn tại nhưng caller không có quyền → từ chối; route ngoài hợp đồng → **không thực thi chức năng/không trả dữ liệu bí mật**.

## 10. 401, 403, 404 và 400 nói lên điều gì?

| Status | Diễn giải thường gặp | Điều chưa thể kết luận |
| --- | --- | --- |
| `401 Unauthorized` | Không có/xác thực không hợp lệ, thường có cơ chế challenge của HTTP Basic | Không khẳng định endpoint đã được bảo vệ bằng đúng rule nghiệp vụ |
| `403 Forbidden` | Bị từ chối khi đủ context hoặc CSRF thất bại | Cần xem bị chặn vì authorization, CSRF, firewall hay logic khác |
| `404 Not Found` | Không có handler hoặc ứng dụng cố tình che giấu tài nguyên | **Không chứng minh** rằng một handler khác hoặc route xuất hiện sau này cũng sẽ được bảo vệ |
| `400 Bad Request` | Request không hợp lệ, có thể bị firewall/container từ chối | Không chứng minh các biến thể hợp lệ khác an toàn |
| `2xx` | Request đã xử lý thành công ở một tầng nào đó | Với endpoint nhạy cảm ngoài hợp đồng, đây là **dấu hiệu cần điều tra** |

Ví dụ: `GET /legacy/admin` hiện trả 404. Điều đó không chứng minh có security rule bảo vệ `/legacy/admin`; đơn giản có thể chưa có controller. Nếu ngày mai một plugin đăng ký route này, trạng thái có thể thay đổi thành 200. Cần có **fallback bảo vệ** và test trên một route thực sự tồn tại nhưng chưa được cho phép như `/api/experimental/export`.

Ngay cả khi nhận 403, cần xác minh handler không bị gọi và không có side effect. Ví dụ POST ghi DB rồi mới dùng `@PostAuthorize` để từ chối kết quả là **quá muộn**; kiểm tra authorization phải nằm trước khi có tác dụng phụ, hoặc gắn vào điều kiện giao dịch phù hợp.

## 11. Những góc khuất dễ bị bỏ qua

### 11.1. Đường dẫn public quá rộng

```java
// Rủi ro nếu trong vùng /api/public/** xuất hiện endpoint nhạy cảm.
.requestMatchers("/api/public/**").permitAll()
```

Một controller được chuyển vào namespace public theo nhầm lẫn có thể tự được mở. Khi nhóm ít endpoint public, dùng matcher chính xác theo method/path và test route mới trong namespace đó.

### 11.2. Thứ tự matcher

Nếu `/api/**.authenticated()` đứng trước `/api/admin/**.hasRole("ADMIN")`, endpoint admin chỉ còn yêu cầu login. Kiểm thử **user thường không có role ADMIN** trên chính endpoint admin để phát hiện thứ tự sai. Đừng chỉ thử admin vì admin thường đi qua cả hai rule.

### 11.3. Security bỏ qua filter chain

Cấu hình `web.ignoring()` có thể khiến các URL được chỉ định **bỏ qua toàn bộ Spring Security filter chain**, gồm nhiều lớp bảo vệ khác. Đối với tài nguyên tĩnh/public, Spring Security khuyến nghị dùng `permitAll()` trong chain khi có thể. Kiểm tra đặc biệt các rule ignore diện rộng như `/resources/**`, `/static/**` và alias legacy.

### 11.4. Error và forward dispatch

`AuthorizationFilter` có thể chạy cho cả `REQUEST`, `FORWARD`, `ERROR`. Một lỗi hợp lệ có thể forward sang trang lỗi và bị một rule deny quá chặt chặn tiếp, khiến status quan sát khác dự kiến. Nếu ứng dụng phải permit một số dispatcher type để render lỗi/view, cần kiểm thử để không vô tình mở handler nhạy cảm qua forward. Không tự động `permitAll()` cho mọi đường dẫn nội bộ nếu chưa phân tích đường dispatch và điều kiện truy cập.

### 11.5. Actuator/management

Một số endpoint quản trị có thể nằm trên context hoặc port quản lý khác. Một `SecurityFilterChain` của ứng dụng chính **không thể mặc nhiên chứng minh** port quản lý được cấu hình giống hệt. Kiểm tra riêng `health`, `metrics`, `mappings`, `env`, `heapdump` và các endpoint Actuator đã bật; cân nhắc network isolation và quyền truy cập tương ứng.

### 11.6. Static content, download, redirect

Một URL không xuất hiện trong controller không có nghĩa không phục vụ nội dung: resource handler, servlet mặc định, redirect, download endpoint, web server static directory hoặc object storage proxy cũng có thể trả dữ liệu. Kiểm tra file được trả về, redirect location và URL đích cuối cùng. Không dựa vào kiểm tra UI "nút không xuất hiện" làm phân quyền.

### 11.7. Reverse proxy và context path

Proxy có thể thêm hoặc bỏ prefix `/app`, chuẩn hóa `//`, decode `%2F` hoặc chuyển từ một host/path sang service khác. Một request bị chặn khi gọi trực tiếp backend có thể đi đường khác qua gateway, và ngược lại. Test bằng **đúng scheme/host/port/path công khai** và so sánh với backend route. Không sử dụng trực tiếp header `X-Forwarded-*` do client gửi nếu hạ tầng chưa thiết lập nguồn proxy đáng tin.

### 11.8. CORS và CSRF

CORS kiểm soát khả năng JavaScript trong browser đọc response theo origin; **CORS không phải authentication/authorization** và không chặn curl hoặc server-to-server client. CSRF bảo vệ một loại request giả mạo khi browser tự gửi credentials; **CSRF không thay thế phân quyền**. Khi test method lạ, tách lỗi CORS/CSRF khỏi chính sách quyền để hiểu đúng lý do bị từ chối.

### 11.9. Route được tạo động

Plugin, versioned API, router function, endpoint bị feature flag điều khiển và các tài nguyên được expose theo profile có thể khác nhau giữa local/test/staging/prod. Chạy route inventory và smoke test trên **profile, dependency và cấu hình gần production**; bộ test chỉ biết source code của một module không bao phủ mọi đường vào được deploy.

## 12. Quy trình phát hiện và sửa một khoảng trống bảo vệ

Giả sử phát hiện `GET /api/experimental/export` trả 200 cho user thường:

1. **Tái hiện có kiểm soát:** ghi lại request method/path/host, danh tính thử nghiệm, cấu hình, response; hạn chế dữ liệu thật và tránh tác động người dùng.
2. **Xác định đường xử lý:** request đã khớp chain nào? Có `securityMatcher` nào bỏ sót không? Rule nào trong `authorizeHttpRequests` khớp đầu tiên? Có `web.ignoring()` hoặc proxy rewrite không?
3. **Chốt quyền nghiệp vụ:** endpoint phải public, authenticated, role cụ thể hay cần object-level authorization? Không chỉ vá tạm một URL mà bỏ qua route anh em.
4. **Sửa cấu hình nhỏ nhất:** thêm rule đúng trước fallback, điều chỉnh chain phủ hết request hoặc thêm một catch-all; nếu cần, kiểm tra quyền trong service cho từng tài nguyên.
5. **Thêm regression test:** người hợp lệ có thể dùng đúng route; người không hợp lệ và đường dẫn ngoài dự kiến bị chặn. Thêm test với handler thật để chứng minh không phải chỉ 404.
6. **Thử qua hạ tầng cuối:** lặp lại kiểm thử khi đi qua proxy/container, với method/encoding/path variants liên quan; so sánh kết quả với chính sách đã phê duyệt.
7. **Theo dõi:** log/metric kết quả deny, thay đổi mapping và các 2xx bất thường ở route chưa được phân loại; tránh log token, mật khẩu hoặc payload nhạy cảm.

Không biến mọi đường dẫn "bị deny" thành thành công: sau khi thêm rule, vẫn cần positive test để bảo đảm route được phép hoạt động và service thực hiện authorization theo dữ liệu nghiệp vụ.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao `anyRequest().denyAll()` trong một chain `securityMatcher("/api/**")` chưa đủ bảo vệ `/internal/secret`?**  
Vì `anyRequest()` chỉ áp dụng **sau khi request đã được chọn vào chain**. `/internal/secret` không khớp `/api/**`; nếu không có chain khác, nó nằm ngoài phạm vi Spring Security.

**2. Nếu `/legacy/export` trả 404, đã chứng minh đường dẫn an toàn chưa?**  
Chưa. Nó có thể chỉ chưa có handler. Cần kiểm tra fallback security chain, route inventory và đường xử lý nếu endpoint xuất hiện.

**3. Nếu `/api/**.authenticated()` được khai trước `/api/admin/**.hasRole("ADMIN")`, chuyện gì xảy ra?**  
Matcher rộng khớp đầu tiên, user chỉ cần xác thực có thể đi qua URL admin. Đảo thứ tự rule và kiểm thử với role USER.

**4. Tại sao trong test POST phải kèm `csrf()` nếu muốn đánh giá authorization?**  
Vì thiếu CSRF token có thể gây 403 ngay ở lớp CSRF, khiến ta tưởng rule authorization đã chặn đúng dù nó chưa được chạy.

**5. Có phải `/api/admin/report?format=csv` là đường dẫn khác với `/api/admin/report` về request matcher dựa trên path?**  
Thường không. Phần query không nằm trong path matcher; nếu format thay đổi hành vi, chức năng phải kiểm tra quyền tương ứng.

**6. Nếu user ADMIN bị 403 ở đường dẫn chưa phê duyệt thì có hợp lý không?**  
Có. Admin không đồng nghĩa được gọi mọi API bí mật/chưa công bố; quyền phải được cấp bằng rule nghiệp vụ rõ ràng.

**7. MockMvc pass hết có chứng minh proxy production an toàn trước encoded slash không?**  
Không. Cần kiểm tra thêm servlet container, firewall và đường đi qua reverse proxy thật vì cách chuẩn hóa URL có thể khác.

## 14. Checklist đưa vào code review và CI

- [ ] Liệt kê mapping HTTP thực tế, kể cả legacy, Actuator, servlet/filter, resource handlers và route do dependency thêm.
- [ ] Mỗi route dự kiến có policy rõ ràng theo method/path, role/scope hoặc kiểm tra dữ liệu nghiệp vụ.
- [ ] Các `SecurityFilterChain` phủ đầy đủ phạm vi cần bảo vệ; có chain fallback cho URL nằm ngoài chain cụ thể.
- [ ] Matcher theo thứ tự từ cụ thể đến tổng quát; rule cuối có chính sách mặc định có chủ đích.
- [ ] URL public chỉ mở đúng method/path; tránh ignore hoặc permit quá rộng.
- [ ] Positive test xác nhận route hợp lệ và role hợp lệ vẫn hoạt động.
- [ ] Negative test xác nhận anonymous, user thường và khi cần cả admin không vào được route ngoài hợp đồng.
- [ ] Test có **handler tồn tại nhưng không được liệt kê** để kiểm chứng deny-by-default.
- [ ] Thử trailing slash, case, path extension, extra segment, method khác và các biến thể encoding liên quan.
- [ ] Với method ghi, tách lỗi CSRF khỏi authorization; xác minh không có side effect khi request bị từ chối.
- [ ] Test riêng context path, proxy rewrite, management port và các dispatcher type liên quan.
- [ ] Đối chiếu status **cùng body và side effect**, không coi 403/404 riêng lẻ là bằng chứng toàn bộ hệ thống an toàn.
- [ ] Khi thêm controller/route/dependency, CI phát hiện mapping mới và yêu cầu test/phê duyệt policy.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): thứ tự matcher, `anyRequest`, dispatcher, matching theo path/method.
- [Spring Security — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher` và các chain lựa chọn request.
- [Spring Security — HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): nguy cơ path normalization và `StrictHttpFirewall`.
- [Spring Security — MockMvc Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): cách tích hợp security filter và viết test.
- [OWASP Web Security Testing Guide — Authorization Testing](https://owasp.org/www-project-web-security-testing-guide/): tư duy kiểm thử trường hợp bị từ chối và sự khác biệt giữa các điểm vào.
