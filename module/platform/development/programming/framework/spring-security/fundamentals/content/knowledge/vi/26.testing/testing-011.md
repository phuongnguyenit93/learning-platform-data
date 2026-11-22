# Kiểm thử endpoint không nằm trong những đường dẫn dự kiến

> **Chủ đề:** Spring Security — fundamentals / Kiểm thử. Bài hướng dẫn kiểm chứng các đường dẫn HTTP và phương thức **ngoài danh sách API được phép** (unexpected / unlisted endpoints) có bị chặn đúng chính sách hay không. Trọng tâm là Spring Security trên **Servlet stack** với Java 17+, Spring Boot 3.x và Spring Security 6.x; ví dụ hoàn chỉnh dùng Spring Boot 3.5.0 và MockMvc.

## 1. Tại sao endpoint "ngoài dự kiến" là một rủi ro bảo mật?

Một ứng dụng có thể chủ đích công khai `GET /public/ping`, cho user đã xác thực đọc `GET /api/documents/{id}` và chỉ admin đọc `GET /admin/report`. Tuy nhiên trong quá trình phát triển, thư viện, module cũ hoặc cấu hình routing có thể thêm endpoint như:

- `GET /internal/diagnostics` — chẩn đoán nội bộ chứa thông tin nhạy cảm.
- `GET /legacy/export` — đường xuất dữ liệu còn sót từ phiên bản cũ.
- `GET /api/documents/101/export` — thao tác bổ sung nằm gần một API đã được cho phép.
- `GET /admin/report/archive` — một URL cùng tiền tố với URL admin hợp lệ nhưng có semantics khác.
- `POST /public/ping` — cùng URI với public GET nhưng là **hành động thay đổi trạng thái**.
- `GET /no-such-path` — URL thật sự không có controller.
- Endpoint Actuator, static file, tài liệu API, endpoint từ một servlet khác, một cổng management khác hoặc ứng dụng đứng sau proxy.

Kẻ tấn công thường không biết chính xác mọi endpoint. Họ có thể thử path, HTTP method, prefix, route cũ, biến thể mã hóa hoặc những đường phụ được lộ qua OpenAPI, JavaScript, log, thông báo lỗi. Nếu chính sách chỉ bảo vệ một tập URL đã nhớ đến, đường mới/đường cũ dễ trở thành lối truy cập trái phép.

**Mục tiêu của bài:** chứng minh bằng test rằng request ngoài allowlist **không đi vào business handler** và không tạo side effect; đồng thời những endpoint chính thức vẫn hoạt động. Bài này khác kiểm thử quyền sở hữu trên document: ở đây trước hết phải xác minh **cả URL lẫn HTTP method** có thuộc bề mặt API được phép.

## 2. Phân biệt URL không tồn tại và URL có handler nhưng chưa được cho phép

| Loại request | Ví dụ | Điều cần kiểm chứng |
|---|---|---|
| **Listed + allowed** | `GET /public/ping` | Hoạt động đúng, không đòi đăng nhập |
| **Listed + protected** | `GET /api/documents/101` | Chỉ principal có quyền phù hợp được truy cập |
| **Unlisted nhưng có handler** | `GET /internal/diagnostics` | Handler không được chạy, kể cả khi caller đăng nhập hoặc là admin |
| **Cùng URL, method khác** | `POST /public/ping` | Public GET không kéo theo public POST |
| **Đường phụ dưới prefix tương tự** | `GET /api/documents/101/export` | Quy tắc cấp quyền cho đọc tài liệu không tự cho phép export |
| **Không có handler** | `GET /no-such-path` | Phải phân biệt kết quả 404 do thiếu mapping với bảo vệ của Spring Security |
| **Không thuộc security chain nào** | URL nằm ngoài mọi `securityMatcher` | Đây có thể là khoảng trống bảo mật, dù mỗi chain đều có `anyRequest().denyAll()` |

**Một request trả 404 không chứng minh API an toàn.** Nó có thể chỉ đơn giản là chưa có controller; khi controller được thêm vào ở lần deploy sau, request có thể lập tức truy cập được nếu có rule quá rộng. Để chứng minh hành vi "deny by default", cần tạo **endpoint thử có mapping thật nhưng không nằm trong allowlist**, rồi xác minh authenticated caller không vào được.

**Một request trả 403 cũng không luôn chứng minh đúng authorization:** request `POST/PATCH/DELETE` có thể bị `CsrfFilter` từ chối trước khi tới quyết định URL. Test âm về HTTP method phải dùng CSRF token hợp lệ khi muốn kiểm tra nhánh authorization, rồi kiểm thử CSRF riêng.

## 3. Quy tắc mặc định từ chối — deny by default

Trong Spring Security Servlet, `authorizeHttpRequests` xây các quy tắc authorization ở mức request. Các `requestMatchers` được xét theo thứ tự khai báo; khi một rule khớp, rule tương ứng quyết định có cho tiếp tục hay không.

Ví dụ hướng đến allowlist:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{id}")
        .hasAnyRole("USER", "ADMIN")
    .requestMatchers(HttpMethod.GET, "/admin/report").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Đoạn trên là **mảnh cấu hình minh họa**, cần `HttpSecurity`, import `HttpMethod` và đặt trong một `SecurityFilterChain`. Chúng ta sẽ có một class đầy đủ ở mục 5.

Các điểm thiết yếu:

1. **Kết hợp HTTP method + path** khi quyền của GET khác POST/PATCH/DELETE. Chỉ `.requestMatchers("/public/ping").permitAll()` có thể cho phép **mọi method** tại URI này, tùy route/handler thực tế.
2. **Rule cụ thể đặt trước**, catch-all `.anyRequest().denyAll()` đặt cuối. Một `.requestMatchers("/**").permitAll()` đặt trước sẽ nuốt toàn bộ request và làm các rule phía sau vô nghĩa.
3. `.denyAll()` chỉ chặn request **đã vào chain chứa rule đó**. Nó không bảo vệ URL mà không có bất kỳ `SecurityFilterChain` nào khớp.
4. Một rule `"/api/**"` hoặc `"/admin/**"` quá rộng có thể vô tình cấp quyền cho endpoint mới. Chỉ dùng wildcard khi **toàn bộ** họ endpoint đó có chung chính sách, và kiểm thử các nhánh con nhạy cảm.
5. `hasRole("ADMIN")` kiểm `ROLE_ADMIN`, nhưng "admin" không có nghĩa được gọi mọi endpoint. Nếu đường nội bộ nằm ngoài danh sách được cấp phép, admin thông thường cũng phải bị từ chối.
6. `denyAll` là **quyết định truy cập**; mã HTTP phụ thuộc trạng thái xác thực và entry point/denied handler. Với HTTP Basic trong ví dụ: anonymous thường nhận `401`; caller đã xác thực nhận `403`.

### Vì sao "anyRequest().authenticated()" có thể chưa đủ?

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/**").hasRole("USER")
    .anyRequest().authenticated()
);
~~~

Đây là **ví dụ cấu hình mở rộng quyền ngoài ý muốn** nếu sản phẩm chỉ định một số ít route hợp lệ. Người dùng có credentials hợp lệ có thể truy cập controller mới tại `/internal/diagnostics`, vì catch-all chỉ đòi đăng nhập. `/api/**` cũng có thể bao gồm API export/debug không dự kiến; `hasRole("USER")` không tự kiểm action hay ownership.

Khi policy nghiệp vụ là “chỉ các route khai báo được phục vụ”, hãy dùng allowlist rõ ràng và deny-all fallback. Nếu ứng dụng cần các trang đăng nhập, static assets, trang lỗi hoặc health check công khai, phải liệt kê những trường hợp **được chủ động phê duyệt**, không mở nguyên `/**`.

## 4. Cần kiểm thử ở đúng tầng: chain selection, authorization và MVC mapping

~~~mermaid
flowchart TD
    A["HTTP request: method + path + headers"] --> B{"Có SecurityFilterChain khớp?"}
    B -->|"Không"| X["Không được chain Spring Security đó bảo vệ<br/>cần kiểm tra và sửa cấu hình"]
    B -->|"Có"| C["Authentication / CSRF / các filter"]
    C --> D{"authorizeHttpRequests rule?"}
    D -->|"Listed + allow"| E["DispatcherServlet / Controller"]
    D -->|"Listed + deny"| F["401 / 403 tùy tình huống"]
    D -->|"Không khớp rule cụ thể"| G["anyRequest().denyAll()"]
    G --> F
    E --> H{"Controller mapping?"}
    H -->|"Có"| I["Handler thực thi"]
    H -->|"Không"| J["404 / 405 / phản hồi MVC phù hợp"]
~~~

**Hai bộ matcher khác chức năng:**

- `securityMatcher(...)` giới hạn **toàn bộ một `SecurityFilterChain`** được áp dụng cho những request nào; filter chain đầu tiên phù hợp theo thứ tự ưu tiên được chọn.
- `requestMatchers(...)` bên trong `authorizeHttpRequests` là rule phân quyền **chỉ đối với những request đã vào chain đó**.
- `DispatcherServlet` / Spring MVC mới quyết định controller nào khớp URI + method, sau khi request vượt qua security filters (trong cấu hình thông thường).

Không dùng `404` khi chưa có handler làm bằng chứng rằng `securityMatcher` đã phủ URL đó. Cũng không suy từ việc `/api/foo` bị chặn rằng `/legacy/foo` được bảo vệ — prefix khác có thể nằm ngoài chain.

### Ví dụ lỗi khi dùng nhiều SecurityFilterChain

~~~java
// CẤU HÌNH THIẾU: minh họa lỗi, không sử dụng làm cấu hình hoàn chỉnh.
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
    return http.build();
}
~~~

Dù có `.anyRequest().denyAll()`, chain này **chỉ** áp dụng cho `/api/**`. Nếu không có chain khác khớp `/internal/diagnostics` hoặc `/legacy/export`, Spring Security không bảo vệ các URL đó. Trong ứng dụng có bean `SecurityFilterChain` do bạn tự định nghĩa, đừng giả định Spring Boot luôn tạo thêm một chain mặc định làm fallback.

Cách sửa về mặt cấu trúc là đăng ký một chain cuối **không có `securityMatcher` hạn chế**:

~~~java
// Mảnh cấu hình minh họa thay thế cấu hình thiếu ở trên.
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
    return http.build();
}
~~~

Khi đưa vào app thật, phải thiết kế đầy đủ authentication/entry point, session, CSRF, các chain cụ thể, order và endpoint cần mở. Nếu một chain `@Order(1)` có `securityMatcher("/**")`, chain `@Order(2)` sẽ **không bao giờ nhận request**. Với phạm vi bài này, ví dụ hoàn chỉnh chỉ sử dụng **một chain phủ tất cả request** để tập trung vào kiểm thử allowlist.

## 5. Ví dụ chạy được: API có những endpoint "vô tình xuất hiện"

Ứng dụng demo có các route **được chủ động cho phép**:

- `GET /public/ping` — public;
- `GET /api/documents/{id}` — user hoặc admin;
- `GET /admin/report` — chỉ admin.

Đồng thời chúng ta cố ý **đăng ký một controller chứa các endpoint không được liệt kê trong policy**. Dù các phương thức Java này thật sự tồn tại, không principal nào được gọi vì catch-all denyAll. Một biến đếm `UnexpectedEndpointProbe` giúp chứng minh handler **chưa từng được thực thi**.

**Môi trường:** Java 17+, Maven 3.9+, Spring Boot 3.5.0 (Spring Security 6.x). Mật khẩu `pw` được dùng **chỉ trong môi trường học tập**, không đưa ra Internet.

Cấu trúc:

~~~text
unexpected-endpoints-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/unexpected/
    │   ├── UnexpectedEndpointsApplication.java
    │   ├── SecurityConfig.java
    │   ├── AllowedController.java
    │   └── UnlistedController.java
    └── test/java/com/example/unexpected/
        └── UnexpectedEndpointSecurityTest.java
~~~

### 5.1. pom.xml

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>unexpected-endpoints-demo</artifactId>
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

### 5.2. UnexpectedEndpointsApplication.java

~~~java
package com.example.unexpected;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UnexpectedEndpointsApplication {
    public static void main(String[] args) {
        SpringApplication.run(UnexpectedEndpointsApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.unexpected;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/documents/{id}")
                    .hasAnyRole("USER", "ADMIN")
                .requestMatchers(
                    HttpMethod.GET, "/admin/report").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Cố ý giữ CSRF protection mặc định.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}pw")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}pw")
                .roles("ADMIN")
                .build());
    }
}
~~~

Đọc đúng thứ tự:

1. `DispatcherType.ERROR` và `FORWARD` được permit để MVC/container có thể render trang lỗi/forward mà không bị catch-all cản trong demo. Đây là **loại dispatch**, khác với việc công khai URL `/error` ở request thông thường; trong ứng dụng thật hãy xác định phạm vi dispatch cần cho phép và kiểm thử đường forward liên quan.
2. `GET /public/ping` được mở chính xác theo method; `POST /public/ping` **không** kế thừa `permitAll`.
3. `GET /api/documents/{id}` được `USER` hoặc `ADMIN` gọi, nhưng `GET /api/documents/101/export` không khớp pattern một segment `{id}`.
4. `GET /admin/report` chỉ dành cho `ADMIN`; `GET /admin/report/archive` **không** khớp route chính xác và phải đi vào `denyAll`.
5. Mọi request khác trong **chain phủ toàn ứng dụng này** bị `denyAll`. Không có `securityMatcher("/api/**")` hạn chế chain.
6. `httpBasic` dùng để tạo hai danh tính demo; `STATELESS` yêu cầu credentials ở mỗi request.
7. CSRF mặc định không bị tắt. Trong test `POST`, phải kèm `with(csrf())` để phân biệt authorization denial với CSRF denial.
8. `{noop}` là password encoder demo cho học tập. Production cần password hashing thích hợp, secret management và HTTPS.

### 5.4. AllowedController.java

~~~java
package com.example.unexpected;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AllowedController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{id}")
    public String document(@PathVariable long id) {
        return "document:" + id;
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }
}
~~~

Controller này tạo ba endpoint *có trong allowlist*. Đây là demo kiểm thử đường dẫn; method `document(...)` không lưu trữ dữ liệu thật. Với ứng dụng production, GET document còn phải kiểm tra **ownership/tenant/object-level authorization** tại service/repository. Việc URL khớp và user có `ROLE_USER` chưa đủ bảo vệ nội dung của mỗi document ID.

### 5.5. UnlistedController.java

~~~java
package com.example.unexpected;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnlistedController {

    private final UnexpectedEndpointProbe probe;

    public UnlistedController(UnexpectedEndpointProbe probe) {
        this.probe = probe;
    }

    @GetMapping("/internal/diagnostics")
    public String diagnostics() {
        probe.recordCall();
        return "sensitive-debug-output";
    }

    @GetMapping("/legacy/export")
    public String legacyExport() {
        probe.recordCall();
        return "legacy-sensitive-export";
    }

    @GetMapping("/api/documents/101/export")
    public String documentExport() {
        probe.recordCall();
        return "document-101-export";
    }

    @GetMapping("/admin/report/archive")
    public String archivedReport() {
        probe.recordCall();
        return "archived-report";
    }

    @PostMapping("/public/ping")
    public String unexpectedMutation() {
        probe.recordCall();
        return "unexpected-write";
    }
}

// Package-private test probe trong cùng tệp; không có endpoint reset.
@Component
class UnexpectedEndpointProbe {
    private final AtomicInteger calls = new AtomicInteger();

    void recordCall() {
        calls.incrementAndGet();
    }

    int callCount() {
        return calls.get();
    }

    void reset() {
        calls.set(0);
    }
}
~~~

Tất cả mapping trong `UnlistedController` **thực sự tồn tại** trong Spring MVC. Chúng là “unlisted” vì chưa được cho phép trong `SecurityConfig`, không phải vì thiếu `@GetMapping`.

Nếu một request đến được method này, `probe.recordCall()` tăng biến đếm. Các test âm sẽ kiểm tra đồng thời status và `callCount() == 0`. Điều này cho bằng chứng mạnh hơn so với chỉ thử URL không có controller và nhìn thấy 404.

Biến đếm chỉ để học, dùng chung trong Spring context. Các test trong ví dụ chạy tuần tự theo cấu hình JUnit mặc định; khi chạy parallel hoặc dùng multi-process, cần fixture độc lập và không dựa trên một singleton counter để đánh giá request của test khác.

## 6. Ma trận test âm: URL ngoài allowlist, method khác và principal khác

Ma trận nên phân biệt **đường dẫn có handler chưa được phê duyệt** và **URL không có mapping**. Với cấu hình ở mục 5:

| ID | Request | Principal | Status dự kiến | Handler không được chạy? |
|---|---|---|---|---|
| ALLOW-01 | `GET /public/ping` | Anonymous | 200 | Handler public **được** chạy |
| ALLOW-02 | `GET /api/documents/101` | Alice / USER | 200 | Handler document **được** chạy |
| ALLOW-03 | `GET /admin/report` | Admin / ADMIN | 200 | Handler report **được** chạy |
| DENY-01 | `GET /api/documents/101` | Anonymous | 401 | Document handler không chạy |
| DENY-02 | `GET /admin/report` | Alice / USER | 403 | Report handler không chạy |
| UNLIST-01 | `GET /internal/diagnostics` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-02 | `GET /legacy/export` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-03 | `GET /api/documents/101/export` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-04 | `GET /admin/report/archive` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-05 | `POST /public/ping` + CSRF hợp lệ | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-06 | `DELETE /api/documents/101` + CSRF hợp lệ | Admin / ADMIN | 403 | Không thực hiện DELETE |
| UNLIST-07 | `GET /no-such-path` | Admin / ADMIN | 403 | URL không có handler; denyAll chạy **trước** MVC |
| UNLIST-08 | `GET /internal/diagnostics` | Anonymous | 401 | Probe = 0 |

`401`/ `403` trong ma trận là **hành vi kỳ vọng của cấu hình HTTP Basic + denyAll ở ví dụ**, không phải mã status bất biến của mọi Spring Security app. Ở một app dùng form login, anonymous có thể bị redirect `302`; app không có catch-all policy có thể trả `404` hoặc vô tình trả `200` cho handler nhạy cảm.

Mỗi hàng cần có: actor, method, URL, headers, expected status, expected data và expected side effects. Với multipart, file, webhook, GraphQL hay WebSocket, cũng phải xác định handshake/upgrade và kiểm tra từng kiểu truy cập.

## 7. MockMvc và JUnit 5: chứng minh denyAll hoạt động

Tạo `src/test/java/com/example/unexpected/UnexpectedEndpointSecurityTest.java`:

~~~java
package com.example.unexpected;

import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UnexpectedEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UnexpectedEndpointProbe probe;

    @BeforeEach
    void resetProbe() {
        probe.reset();
    }

    static Stream<Arguments> unlistedRequests() {
        return Stream.of(
            Arguments.of("UNLIST-01 internal", "GET",
                "/internal/diagnostics"),
            Arguments.of("UNLIST-02 legacy", "GET",
                "/legacy/export"),
            Arguments.of("UNLIST-03 nested export", "GET",
                "/api/documents/101/export"),
            Arguments.of("UNLIST-04 archived report", "GET",
                "/admin/report/archive"),
            Arguments.of("UNLIST-05 method mismatch", "POST",
                "/public/ping"),
            Arguments.of("UNLIST-06 delete method", "DELETE",
                "/api/documents/101"),
            Arguments.of("UNLIST-07 unknown route", "GET",
                "/no-such-path")
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("unlistedRequests")
    void unlistedRequestIsBlockedEvenForAdmin(
            String caseId, String method, String path)
            throws Exception {

        MockHttpServletRequestBuilder request = switch (method) {
            case "GET" -> get(path);
            case "POST" -> post(path).with(csrf());
            case "DELETE" -> delete(path).with(csrf());
            default -> throw new IllegalArgumentException(method);
        };

        mvc.perform(request.with(httpBasic("admin", "pw")))
            .andExpect(status().isForbidden());

        // Kết quả 403 thôi chưa đủ: handler đã gọi phải là 0.
        assertThat(probe.callCount()).isZero();
    }

    @Test
    void expectedPublicRouteWorksWithoutAuthentication()
            throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void listedUserRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:101"));
    }

    @Test
    void listedAdminRouteRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin/report")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/report")
                .with(httpBasic("admin", "pw")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }

    @Test
    void anonymousCannotCallUnlistedHandler() throws Exception {
        mvc.perform(get("/internal/diagnostics"))
            .andExpect(status().isUnauthorized());

        assertThat(probe.callCount()).isZero();
    }

    @Test
    void csrfFailureIsSeparateFromUrlAuthorization()
            throws Exception {
        // Bị chặn do không có CSRF token.
        mvc.perform(post("/public/ping")
                .with(httpBasic("admin", "pw")))
            .andExpect(status().isForbidden());

        // Vẫn 403 khi có CSRF hợp lệ: lúc này denyAll chặn method.
        mvc.perform(post("/public/ping")
                .with(httpBasic("admin", "pw"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertThat(probe.callCount()).isZero();
    }
}
~~~

### Vì sao đây là test có sức phát hiện lỗi?

- `@SpringBootTest` và `@AutoConfigureMockMvc` dựng Spring Security filter chain **thật** trong ứng dụng test, cùng các Spring MVC controller có mapping thực. Test không yêu cầu mở cổng TCP.
- `httpBasic("admin", "pw")` chứng minh rằng **ngay cả người có role cao** cũng không được vượt qua allowlist; test chỉ anonymous chưa đủ.
- `@ParameterizedTest` chạy cùng logic cho nhiều path/method; mỗi case có tên, status và `probe.callCount()`.
- `with(csrf())` trên POST/DELETE nhằm cô lập authorization; CSRF được test riêng. Nếu quên token, 403 từ CSRF có thể che lỗi `permitAll` sai.
- `GET /no-such-path` với admin trả 403 trong cấu hình này vì **denyAll chặn trước controller mapping**. Nếu chuyển catch-all thành `authenticated()`, URL không tồn tại có thể trả 404; một endpoint thật mới xuất hiện ở cùng vị trí có thể thành truy cập được.
- `POST /public/ping` có handler thực và được phép công khai ở **GET**; test phân biệt quyền theo method.
- Test ba route cho phép giữ chúng hoạt động sau khi thêm default-deny, tránh chỉnh cấu hình quá chặt làm hỏng chức năng cần phục vụ.
- Probe giúp phân biệt “chặn trước controller” với “handler đã chạy nhưng sau đó trả lỗi”. Trong hệ thống thật còn phải kiểm database, event, file, cache hoặc external call nếu route có side effect.

**Giới hạn của probe:** Nó chỉ đếm các handler demo của `UnlistedController`; trong ứng dụng thật phải kiểm thử side effect của chính service/domain. Bộ test không chứng minh proxy, gateway, Actuator trên port khác hoặc custom servlet cũng dùng cùng chain. Những lớp đó cần integration/E2E test tại đường HTTP thực tế.

## 8. Chạy và phân tích kết quả

Trong thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

Khi test pass, Maven Surefire thường ghi `BUILD SUCCESS` và báo các JUnit test đã chạy. Đây là **kết quả kỳ vọng**, không phải báo cáo đã thực thi trong tài liệu này.

Có thể khởi chạy ứng dụng để thử request GET từ terminal:

~~~bash
mvn spring-boot:run
~~~

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/101
curl -i -u alice:pw http://localhost:8080/api/documents/101
curl -i -u admin:pw http://localhost:8080/admin/report
curl -i -u admin:pw http://localhost:8080/internal/diagnostics
curl -i -u admin:pw http://localhost:8080/legacy/export
curl -i -u admin:pw http://localhost:8080/no-such-path
~~~

Với cấu hình demo, status chính theo thứ tự: `200`, `401`, `200`, `200`, `403`, `403`, `403`. Các header phụ và body lỗi mặc định phụ thuộc servlet container/Spring Boot; không so sánh nguyên chuỗi body lỗi.

Trên Windows PowerShell, có thể dùng `curl.exe` để tránh alias `curl`. Với POST/DELETE thủ công, request còn chịu CSRF; dùng MockMvc ở mục 7 để kiểm authorization độc lập với việc cấp CSRF token.

**Không kết luận các đường dẫn biến thể đều có cùng response trên mọi server:** các dạng `//`, `/api/documents/101/`, `%2F`, `%2e%2e`, `;` (matrix parameters), URL mã hóa hai lần hoặc thay đổi chữ hoa/thường có thể được proxy, servlet container, Spring MVC và `HttpFirewall` xử lý khác nhau. Chính sách phải được test qua hạ tầng deployment thật trước khi khẳng định chúng bị từ chối theo cùng một mã trạng thái.

## 9. Kiểm thử các tình huống dễ xuất hiện ngoài allowlist

### 9.1. Path typo, alias, trailing slash và đường dẫn chuẩn hóa

Những URL gần giống route chính thức có thể được một lớp routing chấp nhận dù lớp khác không khớp, ví dụ `/api/documents/101/`, `/api//documents/101` hoặc `/api/documents%2F101`. Test cần xác định **phản hồi được chặn hay được cho phép đúng chính sách**, không mặc định server nào cũng parse giống nhau.

Khi dùng `RequestMatcher` tự viết, đừng so sánh chuỗi URI tự phát mà bỏ qua context path/servlet path, query string hoặc quy tắc giải mã; ưu tiên matcher phù hợp với Spring MVC đang chạy. Đừng triển khai “decode liên tục cho đến khi hết ký tự %” hoặc tự loại `..` bằng vài phép replace. Hãy sử dụng khả năng chuẩn hóa và firewall do stack HTTP cung cấp, rồi test các biến thể tại ingress.

Mốc kiểm thử nên có cả **path nguyên bản** mà client gửi và **route Spring MVC cuối cùng** đã được xử lý; với proxy có rewrite, cần xem cấu hình proxy để biết request nào tới ứng dụng.

### 9.2. HTTP method không nằm trong chính sách

Cùng URI có thể mang nhiều method:

~~~http
GET /public/ping HTTP/1.1
~~~

~~~http
POST /public/ping HTTP/1.1
Content-Type: application/json

{"action":"change"}
~~~

Nếu `GET` là public nhưng `POST` sửa dữ liệu, rule không xét `HttpMethod` sẽ nguy hiểm. Test từng method nhạy cảm theo mapping thật, gồm `GET`, `POST`, `PUT`, `PATCH`, `DELETE`; `HEAD`, `OPTIONS` và CORS preflight cần chính sách riêng phù hợp. Không suy ra `OPTIONS` luôn phải trả 403: trình duyệt có thể cần preflight để dùng API hợp lệ, và Spring Security/CORS phải được cấu hình thống nhất.

Nếu app hỗ trợ HTTP method override bằng header/query/filter, test cả method **trước và sau khi được biến đổi**. Proxy và gateway cũng có thể thay method. Authorization nên áp trên method thực sự được controller xử lý.

### 9.3. Router phụ, Actuator, docs, file tĩnh và servlet khác

Có thể có endpoint ở `/actuator/**`, `/swagger-ui/**`, `/v3/api-docs/**`, `/h2-console/**`, tài nguyên `/static/**`, custom servlet hoặc cổng management khác. Không tự động thêm chúng vào `permitAll` chỉ để một UI hiển thị.

Một số endpoint không có trong cùng MVC `RequestMappingHandlerMapping` hoặc chạy dưới **application context/management port khác**. Một bộ MockMvc test của ứng dụng chính không chứng minh chúng đã bị chặn. Cần inventory toàn bộ surfaces, xác nhận route thực tế, bổ sung test HTTP qua cổng management/proxy và tắt endpoint không cần thiết.

Với tài nguyên tĩnh công khai, Spring Security thường khuyến nghị `permitAll` phù hợp hơn `web.ignoring`, vì bỏ qua filter chain có thể đồng nghĩa không áp dụng cả các security headers của chain. `permitAll` vẫn để các filter liên quan chạy.

### 9.4. Nhiều chain và thứ tự ưu tiên

Trong kiến trúc nhiều `SecurityFilterChain`, `FilterChainProxy` chọn chain phù hợp theo `@Order`/thứ tự ưu tiên. Một URL có thể thuộc chain khác dự đoán, hoặc **không có chain nào**. Đây là dạng bug mà test chỉ trên `/api/**` dễ bỏ sót.

Kiểm tra nguyên tắc: **mọi request bảo vệ đều phải khớp ít nhất một chain đúng chính sách**; fallback chain không hạn chế path nên được đặt cuối. Nếu app cố ý có URL bỏ qua Spring Security (ví dụ resource do proxy/nginx phục vụ hoàn toàn), phải ghi rõ kiểm soát truy cập ở tầng tương ứng, không suy từ một test MVC.

Ở môi trường phát triển, có thể bật tạm:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Log giúp thấy filter chain/matcher/authorization khi chẩn đoán. Không bật log credential, session cookie hoặc Bearer token trong production. Không dựa vào log như thay thế cho test.

### 9.5. Khi mapping thay đổi qua version hoặc feature flag

Route cũ có thể vẫn tồn tại sau migration. Feature flag hoặc profile có thể bật route nội bộ chỉ ở một môi trường. Một test pass trên `test` profile không tự chứng minh `prod` profile không sinh thêm controller.

Cần đối chiếu inventory route ở profile deploy tương ứng và kiểm thử ít nhất các feature/config ảnh hưởng đến mapping hoặc chain selection. Đường legacy/deprecated phải được quyết định rõ: giữ nhưng bảo vệ, vô hiệu hóa, hay xóa cùng các dependency.

## 10. Nâng cấp test từ một demo lên hệ thống thực

### Bước 1 — Lập allowlist từ hợp đồng API

Liệt kê method/path hợp lệ và quyền của từng nhóm người dùng: OpenAPI đã duyệt, controller mapping, yêu cầu nghiệp vụ, chính sách bảo mật. Mỗi endpoint public phải có lý do; không suy ra từ tên `/public` rằng nó an toàn cho mọi method.

Ví dụ hợp đồng:

~~~yaml
routes:
  - method: GET
    path: /public/ping
    authorization: PUBLIC
  - method: GET
    path: /api/documents/{id}
    authorization: USER_OR_ADMIN
  - method: GET
    path: /admin/report
    authorization: ADMIN
default: DENY
~~~

YAML trên là **dữ liệu chính sách minh họa**, không phải cấu hình Spring Security tự động hiểu. Muốn dùng để sinh test cần code đọc/biên dịch hợp đồng và kiểm chứng nó độc lập với implementation.

### Bước 2 — Lấy inventory endpoint thực

Có thể lấy mapping từ Spring MVC `RequestMappingHandlerMapping` trong test context, từ endpoint Actuator mappings được bảo vệ, hoặc từ contract/route registry đã xác minh. Không đồng nhất inventory của MVC với toàn bộ surfaces (static/proxy/management/custom servlet).

Nếu muốn kiểm tra sự xuất hiện **bất ngờ** của mapping, so sánh *set* thực tế (method + path pattern + handler) với danh sách đã duyệt. Đừng chỉ nhìn phản hồi của các URL thử bằng tay. Khi thêm API mới, review phải đồng thời cập nhật policy và test allowlist.

### Bước 3 — Sinh negative cases có ý nghĩa

Các nhóm tiêu biểu:

| Nhóm | Trường hợp |
|---|---|
| Route nội bộ | `/internal/**`, `/debug/**`, `/actuator/**` theo exposure thực |
| Route legacy | Prefix/version cũ, deprecated handler, redirect/forward alias |
| Route gần giống | Prefix con, route lồng, biến thể trailing slash, chữ hoa |
| Method | POST/PATCH/DELETE trên URL chỉ cho phép GET, hoặc method override |
| Principal | Anonymous, user thường, admin, user tenant khác |
| Payload | ID không hợp lệ, nested ID, path variable dài/sai kiểu |
| Hạ tầng | Rewrite của reverse proxy, context path, port management, custom servlet |
| Bản phát hành | Mapping chỉ xuất hiện theo profile/feature flag |

Không gửi hàng nghìn request mù quáng ở môi trường production; thiết kế test trên môi trường được phép, có fixture/cấp quyền và mức tải kiểm soát. Đối với biến thể path, một `400` do firewall, `404` do không mapping hoặc `403` do chính sách có thể đều an toàn tùy trường hợp, **miễn là endpoint nhạy cảm không được thực thi hoặc rò dữ liệu**.

### Bước 4 — Kiểm cả phản hồi và side effect

Mỗi negative test nên kiểm:

- Status phù hợp hợp đồng (và nếu cần, `WWW-Authenticate` cho 401).
- Body/header không chứa secret, stack trace, path nội bộ hoặc thông tin đối tượng cấm.
- Business handler không chạy hoặc state bất biến: database row count, file, message/event, export, cache, audit effect.
- Không có redirect/forward sang endpoint nhạy cảm ngoài chính sách.
- Không có chain gap trong cấu hình production.
- Positive test đảm bảo endpoint được phê duyệt vẫn hoạt động.

Nếu chỉ thử URL không được map rồi xác nhận 404, coverage về security gần như bằng không: **cần có những endpoint thật nhưng cố ý không được cho phép** như trong ví dụ.

### Bước 5 — Kết nối với CI và quy trình review

Ma trận test phải được chạy khi thêm controller, cập nhật `SecurityFilterChain`, thay `requestMatchers`, bật actuator/docs, đổi ingress/router hay nâng cấp Servlet stack. Khi policy thay đổi, cập nhật allowlist được phê duyệt và expected test **trước**, rồi sửa implementation. Không tự động coi mọi endpoint mới trong runtime inventory là hợp lệ.

Kết quả nên chỉ rõ `test case ID / method / path / actor / expected / actual / handler invoked?` để người review có thể phân biệt lỗi security rule với CSRF, mapping hoặc startup config.

## 11. Những sai lầm thường gặp

1. **Nhầm catch-all rule với catch-all chain:** `anyRequest().denyAll()` trong chain `/api/**` không bảo vệ `/legacy/**` nếu không có chain khác khớp.
2. **Dùng `anyRequest().authenticated()` khi policy cần allowlist:** mọi user đăng nhập có thể đi vào những controller mới vô tình xuất hiện.
3. **Đặt `permitAll("/**")` hoặc wildcard quá rộng trước rule nhạy cảm:** matcher đầu tiên khớp có thể cấp quyền ngoài chủ đích.
4. **Không giới hạn HTTP method:** `GET /public/foo` được phép không đồng nghĩa `POST /public/foo` được phép.
5. **Chỉ test anonymous:** handler unlisted vẫn có thể được mở cho bất kỳ user đã đăng nhập nào, kể cả admin tenant khác.
6. **Chỉ test 404 URL không tồn tại:** không cho biết policy sẽ xử lý thế nào khi có controller thật.
7. **Lấy 403 từ CSRF để khẳng định method authorization đúng:** hãy thêm CSRF hợp lệ trong test authorization rồi thử thiếu CSRF riêng.
8. **Chỉ nhìn HTTP status:** business handler có thể đã gây side effect trước khi lỗi được trả; kiểm trạng thái/interaction.
9. **Chỉ kiểm từ MockMvc, bỏ qua gateway/management port:** URL có thể được rewrite hoặc phục vụ ở context khác; kiểm thử qua entry point thực tế.
10. **Coi UUID hoặc một URL khó đoán là rào chắn:** biết URL không đồng nghĩa có quyền; object-level policy vẫn cần áp dụng.
11. **Thay `permitAll` bằng `web.ignoring` cho mọi static/docs:** bypass filter chain có thể bỏ các security headers và các bảo vệ liên quan.
12. **Lẫn lộn HTTP 401/403/404:** 401 thường là thiếu xác thực hợp lệ, 403 là bị từ chối quyền, 404 là không tìm thấy mapping/tài nguyên hoặc chủ động ẩn tài nguyên. Test cần nói rõ lớp nào sinh phản hồi.
13. **Không khóa scope của custom servlet/servlet path:** request matcher mặc định có thể cần cấu hình rõ ràng khi một ứng dụng chứa nhiều servlet.
14. **Tin một test pass ở profile khác production:** mapping/security filters có thể thay đổi theo profile, conditional bean hoặc deployment.

## 12. Bài tập và câu hỏi tự kiểm tra

1. Khi `/api/**` là chain duy nhất và `anyRequest().denyAll()` được khai báo bên trong, điều gì xảy ra với một controller `/internal/diagnostics`? Vì sao?
2. Tại sao `GET /unknown` trả `404` không đủ chứng minh security configuration an toàn?
3. Trong ví dụ, tại sao admin gọi `GET /admin/report` được, nhưng `GET /admin/report/archive` lại bị `403`?
4. Nếu đổi `.requestMatchers(HttpMethod.GET, "/public/ping").permitAll()` thành `.requestMatchers("/public/ping").permitAll()`, test nào chứng minh nguy cơ `POST` bị cho phép?
5. Nếu `POST /public/ping` trả 403 khi thiếu CSRF, vì sao phải thử lại với `with(csrf())` trước khi kết luận `denyAll` đúng?
6. Thêm một controller mới `GET /api/documents/101/share`. Viết test bảo đảm user và admin đều bị từ chối đến khi policy được phê duyệt.
7. Nếu `GET /api/documents/999` khớp route được cấp quyền cho USER nhưng không có dữ liệu, status HTTP nào là hợp lý? Cần kiểm tra gì để phân biệt lỗi dữ liệu và lỗi URL policy?
8. Với hai `SecurityFilterChain` có `@Order(1)` và `@Order(2)`, chain nào sẽ xử lý `/legacy/export` nếu chain đầu chỉ match `/api/**` và chain sau không có `securityMatcher`?
9. Nếu một endpoint nằm trên management port riêng, `@AutoConfigureMockMvc` của ứng dụng chính có đủ chứng minh endpoint này được bảo vệ không? Cần kiểm thử bổ sung tại đâu?
10. Nếu test chỉ assert 403 mà probe vẫn tăng, kết luận gì về security và cách khắc phục?

**Tiêu chí hoàn thành:** bạn có thể xây danh sách HTTP method + path được phê duyệt, xác định behavior mặc định cho request ngoài danh sách, phân biệt `securityMatcher` với `requestMatchers`, viết negative test trên những controller **có thật** nhưng không được phép, kiểm tra status lẫn side effect và phát hiện chain gap khi ứng dụng có nhiều filter chain.

## Tài liệu tham khảo chính thức

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Multiple HttpSecurity / SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
