# Quy tắc dấu gạch chéo cuối đường dẫn và tính nhất quán khi phân quyền trong Spring WebFlux

## 1. Vì sao trailing slash quan trọng?

Hai request sau chỉ khác một dấu gạch chéo:

~~~text
GET /admin/reports
GET /admin/reports/
~~~

Trong HTTP, chúng là hai request target khác nhau. Controller mapping, reverse proxy, cache và tầng authorization có thể diễn giải chúng theo các quy tắc khác nhau.

Một lỗi thiết kế phổ biến xảy ra khi controller hoặc proxy xem hai URL là cùng một tài nguyên, trong khi security matcher chỉ khớp chính xác một dạng. Request có slash cuối có thể không khớp luật cụ thể và rơi xuống matcher rộng hơn. Nếu một tầng phía sau lại chuẩn hóa path, request cuối cùng có thể tới cùng tài nguyên nhưng đã đi qua một quyết định phân quyền khác.

Mục tiêu là thiết lập một **canonical path** (đường dẫn chuẩn), để URL normalization, Spring Security và handler mapping cùng nhìn thấy một path trước khi xử lý request.

## 2. Quy tắc mặc định của PathPattern trong WebFlux

Spring WebFlux dùng PathPattern và PathPatternParser để khớp URL. Đây là cơ chế được thiết kế cho HTTP path và là lựa chọn của WebFlux; WebFlux không dùng AntPathMatcher làm cơ chế định tuyến controller.

Từ Spring Framework 6.0, PathPatternParser mặc định không tự động coi dấu gạch chéo cuối là tùy chọn:

~~~text
Pattern: /home

/home   -> match
/home/  -> không match theo mặc định
~~~

Ví dụ:

~~~java
@GetMapping("/home")
public Mono<String> home() {
    return Mono.just("home");
}
~~~

GET /home khớp mapping. GET /home/ là path khác và không tự động khớp chỉ vì có thêm slash cuối.

### Thay đổi từ Spring 6.0

Trong các phiên bản trước Spring 6, PathPatternParser từng cho phép optional trailing separator theo mặc định. Từ Spring 6.0:

- matchOptionalTrailingSeparator mặc định đổi từ true thành false.
- setMatchOptionalTrailingSeparator(boolean) bị deprecated.
- Tài liệu Spring khuyến nghị dùng redirect hoặc filter rõ ràng thay vì bật lại cơ chế tự khớp slash cuối.

Không nên dựa vào giả định cũ rằng /resource và /resource/ luôn tương đương. Khi nâng cấp lên Spring 6, cần kiểm tra URL client đang sử dụng và xác định một quy tắc canonical.

### Ví dụ pattern

| Pattern | Path | Kết quả |
| --- | --- | --- |
| /users | /users | Khớp |
| /users | /users/ | Không tự khớp do slash cuối |
| /users/{id} | /users/42 | Khớp một segment |
| /users/{id} | /users/42/ | Không tự khớp do slash cuối |
| /users/** | /users/42/profile | Khớp nhiều segment |

Các wildcard như /** có ngữ nghĩa riêng. Không suy luận từ một pattern catch-all rằng mọi mapping literal cũng tự chấp nhận slash cuối.

## 3. Định tuyến controller và authorization là hai bước riêng

Trong WebFlux, Spring Security hoạt động bằng WebFilter. Security filter chain chạy trước target WebHandler, nơi có DispatcherHandler và controller mapping.

~~~text
HTTP request
     |
     v
WebFilter chain
     |
     +--> URL normalization filter
     |
     +--> Spring Security WebFilterChainProxy
     |         |
     |         +--> chọn SecurityWebFilterChain
     |         +--> authentication
     |         +--> authorization matcher
     |
     v
DispatcherHandler
     |
     v
RequestMappingHandlerMapping
     |
     v
Controller method
~~~

Luật authorization không đợi controller quyết định method nào sẽ xử lý. Spring Security kiểm tra request path bằng matcher ngay trong filter chain.

Trong WebFlux Security, authorizeExchange().pathMatchers(...) và PathPatternParserServerWebExchangeMatcher dùng cơ chế match path theo PathPattern. Có thể cấu hình nhiều SecurityWebFilterChain với matcher và thứ tự riêng; chain đầu tiên phù hợp sẽ được chọn.

Điều cần bảo đảm:

1. Đường dẫn được chuẩn hóa trước khi Security kiểm tra.
2. Security matcher và controller mapping áp dụng cùng quy tắc path.
3. Luật cụ thể đứng trước luật rộng hơn.
4. Luật cuối cùng có chủ đích rõ ràng, ví dụ authenticated hoặc deny all.
5. Không để alias URL của tài nguyên nhạy cảm đi qua một nhánh authorization yếu hơn.

## 4. Sai lệch giữa mapping và phân quyền

Giả sử API có endpoint quản trị:

~~~java
@GetMapping("/admin/reports")
public Mono<Report> reports() {
    return reportService.load();
}
~~~

Security rule:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/admin/reports").hasRole("ADMIN")
    .anyExchange().permitAll()
)
~~~

Nếu request path được chuẩn hóa thành /admin/reports trước Security, cả /admin/reports và /admin/reports/ đều được đánh giá bởi cùng matcher và luật ADMIN.

Nếu một filter hoặc proxy chỉ sửa path sau Security, Security có thể nhìn thấy /admin/reports/ trong khi tầng xử lý phía sau nhìn thấy /admin/reports. Với matcher chính xác, request có slash có thể không khớp luật cụ thể và rơi xuống luật rộng hơn.

Hệ quả phụ thuộc matcher và route thực tế:

- Request bị từ chối ở một dạng URL nhưng được chấp nhận ở dạng khác.
- Một alias được định tuyến tới cùng tài nguyên nhưng không chịu cùng luật authorization.
- Request đi vào fallback route hoặc error handler khác.
- Cache, audit log và rate limit ghi nhận hai path khác nhau cho cùng tài nguyên.

Không xem 404 ở controller là biện pháp bảo vệ authorization. Phân quyền phải đúng ngay tại tầng security, không phụ thuộc việc controller có tìm được handler hay không.

## 5. UrlHandlerFilter trong Spring Framework 6.2

Spring Framework 6.2 cung cấp org.springframework.web.filter.reactive.UrlHandlerFilter cho WebFlux. Đây là một WebFilter chuyên xử lý trailing slash.

Filter áp dụng cho các pattern đã chọn và có thể bỏ slash cuối bằng hai cách:

- **Redirect:** trả response redirect để client gọi lại URL canonical.
- **Mutate request:** sửa path trong ServerWebExchange rồi tiếp tục xử lý request hiện tại.

Ví dụ:

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
    .trailingSlashHandler("/blog/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
    .trailingSlashHandler("/admin/**")
        .mutateRequest()
    .build();
~~~

Trong ví dụ, /blog/post/ được redirect vĩnh viễn sang /blog/post bằng HTTP 308; /admin/users/ được sửa thành /admin/users trong request nội bộ.

Javadoc Spring ghi rõ filter cần chạy trước các security filter để URL-based authorization và handler mapping có cùng cách nhìn về path.

### Đăng ký filter thành bean

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
UrlHandlerFilter urlHandlerFilter() {
    return UrlHandlerFilter
        .trailingSlashHandler("/admin/**", "/api/**")
        .mutateRequest()
        .build();
}
~~~

WebFlux tự phát hiện bean WebFilter. @Order(Ordered.HIGHEST_PRECEDENCE) đặt filter ở vị trí ưu tiên cao để normalization diễn ra trước Spring Security.

Không đặt URL normalization sau Security. Nếu làm vậy, Security và controller có thể tiếp tục đánh giá hai path khác nhau.

## 6. Chọn redirect hay mutateRequest?

| Tiêu chí | Redirect | Mutate request |
| --- | --- | --- |
| URL client nhìn thấy | Chuyển sang URL canonical | Giữ URL ban đầu |
| Số request | Client có thể gửi request thứ hai | Một request nội bộ |
| Cache và bookmark | Dễ hội tụ về URL canonical | Client vẫn có thể lưu URL có slash |
| API client | Cần hỗ trợ redirect | Không cần client xử lý redirect |
| Security | Request follow-up được kiểm tra trên URL canonical | Filter chuẩn hóa trước khi Security chạy |
| Log ở client/proxy | Có thể ghi redirect và request tiếp theo | Vẫn thấy URL ban đầu ở tầng trước filter |

### Redirect bằng HTTP 308

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
UrlHandlerFilter docsUrlHandlerFilter() {
    return UrlHandlerFilter
        .trailingSlashHandler("/docs/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
        .build();
}
~~~

308 Permanent Redirect biểu thị URL tài nguyên đã được chuyển sang URI chuẩn. Theo HTTP semantics, 307 và 308 là redirect giữ nguyên method; 308 phù hợp khi muốn công bố URL canonical lâu dài.

Ví dụ:

~~~http
GET /docs/install/ HTTP/1.1
~~~

Response:

~~~http
HTTP/1.1 308 Permanent Redirect
Location: /docs/install
~~~

Với request POST/PUT, giữ nguyên method và body rất quan trọng. 301/302 có lịch sử hành vi client có thể đổi POST thành GET; 307/308 được định nghĩa để tránh việc đổi method khi follow redirect.

Redirect vĩnh viễn có thể được cache. Chỉ dùng 308 khi URL canonical đã ổn định và client hỗ trợ hành vi redirect phù hợp.

### Mutate request

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
UrlHandlerFilter adminUrlHandlerFilter() {
    return UrlHandlerFilter
        .trailingSlashHandler("/admin/**")
        .mutateRequest()
        .build();
}
~~~

Với request GET /admin/users/, filter sửa path nội bộ thành /admin/users trước khi request đến Security và handler mapping.

Ưu điểm là không yêu cầu client gửi request thứ hai. Đây thường là lựa chọn thuận tiện cho API cũ có nhiều client hoặc client không xử lý redirect đồng nhất.

Đổi lại, URL gốc mà browser hoặc proxy nhìn thấy vẫn có thể chứa slash cuối. Nếu cần một URL công khai duy nhất cho bookmark hoặc cache ở edge, redirect có thể phù hợp hơn.

## 7. Thứ tự filter là một phần của chính sách bảo mật

~~~text
Request /admin/reports/
          |
          v
UrlHandlerFilter
          |
          | mutate request path
          v
Request /admin/reports
          |
          v
Spring Security
          |
          | matcher sees canonical path
          v
Controller mapping
          |
          | same canonical path
          v
AdminController.reports()
~~~

Các nguyên tắc:

- Đặt UrlHandlerFilter trước Spring Security WebFilter chain.
- Không tự tạo filter thứ hai làm thay đổi path ở vị trí sau Security.
- Nếu reverse proxy cũng chuẩn hóa path, cấu hình proxy và ứng dụng cùng quy tắc.
- Nếu dùng nhiều SecurityWebFilterChain, canonical path phải được tạo trước khi chọn chain.
- Nếu filter khác kiểm tra tenant, rate limit, audit hoặc chữ ký request dựa trên path, xác định rõ nó cần path gốc hay path canonical.

### Nhiều SecurityWebFilterChain

Spring Security có thể tách chain theo path:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Một chain khác có thể xử lý phần còn lại. Vì Spring chọn chain theo matcher và thứ tự, canonicalization cần chạy trước quá trình lựa chọn đó.

## 8. Thiết kế URL canonical cho ứng dụng

Ví dụ ứng dụng chọn URL không có trailing slash cho mọi path ngoại trừ root /:

| URL nhận vào | URL canonical |
| --- | --- |
| /users | /users |
| /users/ | /users |
| /users/42 | /users/42 |
| /users/42/ | /users/42 |
| / | / |

Spring UrlHandlerFilter mặc định loại trừ root path / khỏi trailing slash handling.

Nếu một API cần giữ slash cuối vì hợp đồng bên ngoài, đừng đăng ký filter cho path đó. Có thể chọn quy tắc riêng theo pattern:

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
    .trailingSlashHandler("/api/**")
        .mutateRequest()
    .trailingSlashHandler("/docs/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
    .build();
~~~

Đừng áp dụng quy tắc toàn cục mà không xem xét route có ý nghĩa riêng. Một endpoint có thể coi slash cuối là một phần của hợp đồng, nhất là khi tương thích hệ thống cũ hoặc storage key đặc biệt.

### Explicit aliases

Một cách khác là khai báo rõ hai mapping:

~~~java
@GetMapping({"/catalog", "/catalog/"})
public Mono<Catalog> catalog() {
    return catalogService.getCatalog();
}
~~~

Cách này làm route chấp nhận hai URL, nhưng không tự chuẩn hóa request path cho các tầng khác. Nếu Security, cache, rate limit hoặc audit cần coi hai URL là một tài nguyên, vẫn phải đồng bộ chính sách ở các tầng đó.

## 9. Path normalization không chỉ có trailing slash

UrlHandlerFilter xử lý dấu gạch chéo cuối theo pattern đã khai báo. Nó không phải bộ chuẩn hóa mọi biến thể URL.

| Dạng path | Vấn đề cần cân nhắc |
| --- | --- |
| /files//report | Dấu slash lặp; proxy và server có thể diễn giải khác nhau |
| /files/../admin | Dot segment và xử lý path traversal |
| /files/%2Fadmin | Encoded slash; việc decode có thể khác giữa các tầng |
| /files/%252Fadmin | Double encoding; không decode lặp tùy tiện |
| /users;v=1 | Matrix/path parameters |
| /Admin và /admin | Case sensitivity |
| /api/v1.json | Suffix không phải trailing slash |

Spring WebFlux dùng RequestPath đã parse để truy cập path segment đã decode; semicolon content được xử lý riêng cho path matching. Không cần tự viết code decode path string để phục vụ controller matching.

Không nên làm kiểu:

~~~java
String path = exchange.getRequest().getURI().getRawPath()
    .replaceAll("/+$", "");
~~~

rồi tự tạo request path mới cho mọi trường hợp. Cách làm này có thể thay đổi encoded path, double slash, root path hoặc ý nghĩa segment ngoài dự kiến.

Nếu cần xử lý encoded slash, duplicate slash hoặc dot segment, hãy xác định hành vi thống nhất tại reverse proxy, HTTP server và ứng dụng; kiểm thử cùng một bộ URL trên toàn tuyến. Không decode hai lần.

## 10. Reverse proxy, gateway và forwarded headers

Ứng dụng thường nằm sau Nginx, ingress controller, API gateway hoặc load balancer. Các tầng này có thể thêm hoặc bỏ prefix, chuẩn hóa slash, redirect URL, rewrite path trước khi gửi tới WebFlux hoặc áp dụng authorization/cache trước khi request đến ứng dụng.

Nếu proxy chuẩn hóa /admin/reports/ thành /admin/reports nhưng Security trong ứng dụng nhìn thấy path khác do cấu hình forwarded/rewrite không nhất quán, log và policy có thể không khớp.

Spring WebFlux có ForwardedHeaderTransformer để xử lý thông tin forwarded như host, port, scheme và prefix. Các forwarded headers chỉ đáng tin khi proxy tại ranh giới tin cậy xóa header do client tự gửi rồi ghi lại giá trị của chính nó.

Checklist ở proxy:

1. Xác định proxy có redirect hoặc rewrite trailing slash không.
2. Ghi rõ path mà proxy gửi tới upstream.
3. Bảo đảm gateway authorization và application authorization dùng cùng canonical path.
4. Không tin forwarded headers do client bên ngoài tự gửi.
5. Kiểm thử path có query string, encoded segment và slash cuối.
6. Tránh hai tầng cùng redirect theo hai quy tắc khác nhau, gây vòng lặp.

## 11. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux và Security

Ví dụ dùng Spring Boot 3.5.0, Java 17+:

- Controller bảo vệ tài nguyên tại /admin/reports.
- Spring Security yêu cầu role ADMIN cho đúng path này.
- UrlHandlerFilter loại bỏ trailing slash trước Security.
- /admin/reports và /admin/reports/ đi qua cùng authorization matcher.
- WebTestClient xác nhận user thường không thể dùng slash cuối để vượt qua rule.

Cấu trúc dự án:

~~~text
webflux-path-security/
├── pom.xml
└── src/
    ├── main/java/com/example/pathsecurity/
    │   ├── PathSecurityApplication.java
    │   ├── UrlPolicyConfiguration.java
    │   ├── SecurityConfiguration.java
    │   └── AdminController.java
    └── test/java/com/example/pathsecurity/
        └── TrailingSlashSecurityTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-path-security</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### PathSecurityApplication.java

~~~java
package com.example.pathsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathSecurityApplication.class, args);
    }
}
~~~

### UrlPolicyConfiguration.java

~~~java
package com.example.pathsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.filter.reactive.UrlHandlerFilter;

@Configuration(proxyBeanMethods = false)
public class UrlPolicyConfiguration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    UrlHandlerFilter urlHandlerFilter() {
        return UrlHandlerFilter
            .trailingSlashHandler("/admin/**")
            .mutateRequest()
            .build();
    }
}
~~~

Filter chạy trước Spring Security. Khi request có path /admin/reports/, request path được mutate thành /admin/reports trước khi security matcher kiểm tra.

### SecurityConfiguration.java

~~~java
package com.example.pathsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails admin = User.withUsername("admin")
            .password("{noop}secret")
            .roles("ADMIN")
            .build();

        UserDetails user = User.withUsername("user")
            .password("{noop}secret")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(admin, user);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/admin/reports").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Luật authorization chỉ cấp quyền ADMIN cho matcher /admin/reports. Các request còn lại bị deny trong demo này. Mật khẩu {noop} chỉ để minh họa chạy local; production phải dùng PasswordEncoder thích hợp và nguồn user/role an toàn.

### AdminController.java

~~~java
package com.example.pathsecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/admin")
public class AdminController {

    @GetMapping("/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of(
            "resource", "admin-reports",
            "status", "ok"
        ));
    }
}
~~~

Mapping ở class là /admin, mapping method là /reports. Không dùng @RequestMapping("/") ở cấp class vì nó thêm slash vào type-level mapping và có thể không khớp sau khi filter loại bỏ slash cuối.

### TrailingSlashSecurityTest.java

~~~java
package com.example.pathsecurity;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TrailingSlashSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void adminCanAccessBothPathForms() {
        for (String path : new String[] {
                "/admin/reports",
                "/admin/reports/"
        }) {
            client.get()
                .uri(path)
                .headers(headers -> headers.setBasicAuth("admin", "secret"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.resource").isEqualTo("admin-reports");
        }
    }

    @Test
    void userCannotBypassAuthorizationWithTrailingSlash() {
        client.get()
            .uri("/admin/reports/")
            .headers(headers -> headers.setBasicAuth("user", "secret"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousRequestIsRejectedForBothForms() {
        for (String path : new String[] {
                "/admin/reports",
                "/admin/reports/"
        }) {
            client.get()
                .uri(path)
                .exchange()
                .expectStatus().isUnauthorized();
        }
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Các kiểm thử xác nhận:

- ADMIN gọi path có hoặc không có slash cuối đều nhận cùng tài nguyên.
- USER gọi /admin/reports/ vẫn nhận 403.
- Request chưa xác thực nhận 401 ở cả hai dạng URL.

### Chạy ứng dụng và thử bằng cURL

Khởi động:

~~~bash
mvn spring-boot:run
~~~

ADMIN gọi path không có slash:

~~~bash
curl -i -u admin:secret http://localhost:8080/admin/reports
~~~

ADMIN gọi path có slash:

~~~bash
curl -i -u admin:secret http://localhost:8080/admin/reports/
~~~

Cả hai response đều có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "resource": "admin-reports",
  "status": "ok"
}
~~~

USER gọi path có slash:

~~~bash
curl -i -u user:secret http://localhost:8080/admin/reports/
~~~

Response:

~~~http
HTTP/1.1 403 Forbidden
~~~

Request không có credentials nhận:

~~~http
HTTP/1.1 401 Unauthorized
~~~

Ví dụ dùng HTTP Basic và user in-memory chỉ phục vụ học tập. Không dùng cấu hình mật khẩu này cho hệ thống thật.

## 12. Cách kiểm tra một lỗi trailing slash trong production

Khi phát hiện /resource và /resource/ cho status hoặc quyền khác nhau, hãy kiểm tra từng tầng theo thứ tự:

1. **Client:** URL chính xác được gửi là gì? Có thư viện tự thêm slash không?
2. **Proxy/gateway:** path có bị rewrite, redirect hoặc normalize không?
3. **Forwarded headers:** prefix/host có được xử lý từ proxy đáng tin cậy không?
4. **WebFilter order:** filter chuẩn hóa có chạy trước Security không?
5. **SecurityWebFilterChain:** chain nào được chọn cho từng path?
6. **Authorization matcher:** rule cụ thể nào khớp? Có rơi xuống matcher rộng hơn không?
7. **Handler mapping:** controller hoặc functional route nào khớp?
8. **Method security:** có thêm @PreAuthorize hoặc policy theo domain không?
9. **Cache/CDN:** hai URL có tạo cache key khác nhau không?
10. **Logging/metrics:** log ghi path trước hay sau normalization?

### Log path có chủ đích

Nếu cần điều tra, log cả request URI gốc tại edge và path canonical trong ứng dụng. Không nên chỉ log một giá trị rồi suy đoán các tầng đã nhìn thấy cùng path.

Có thể thêm request ID để đối chiếu log gateway, WebFlux và downstream. Không log authorization header, cookie, access token hoặc dữ liệu nhạy cảm khi debug path.

### Kiểm thử ma trận URL

Với một endpoint nhạy cảm, kiểm thử tối thiểu:

| Path | Anonymous | USER | ADMIN |
| --- | --- | --- | --- |
| /admin/reports | 401 | 403 | 200 |
| /admin/reports/ | 401 | 403 | 200 |

Nếu ứng dụng dùng redirect thay vì mutate, kiểm tra response 308 và request follow-up riêng. Nếu endpoint nhận POST/PUT, xác nhận client giữ method/body khi follow redirect.

## 13. Những lỗi thường gặp

1. **Giả định /path và /path/ luôn giống nhau:** từ Spring 6.0, PathPatternParser mặc định không tự khớp optional trailing slash.
2. **Bật lại setMatchOptionalTrailingSeparator(true):** API đã deprecated từ Spring 6.0. Ưu tiên URL policy rõ ràng bằng filter hoặc redirect.
3. **Chuẩn hóa sau Spring Security:** Security đã quyết định trên path cũ, controller có thể nhận path mới. Đặt UrlHandlerFilter trước security.
4. **Chỉ sửa controller mapping:** không đồng bộ Security matcher, cache, gateway hoặc rate limit.
5. **Chỉ sửa Security matcher:** route mapping vẫn có thể xử lý URL khác với matcher.
6. **Dùng catch-all authorization quá rộng:** một path variant không khớp rule cụ thể có thể rơi xuống rule yếu hơn. Dùng fallback rõ ràng và kiểm thử.
7. **Dùng @RequestMapping("/") sau khi mutate slash:** mapping cấp class có thể tự thêm slash và không còn khớp. Dùng @RequestMapping không có path nếu cần root prefix.
8. **Đăng ký UrlHandlerFilter mà không đặt order:** filter có thể chạy sau security và không giải quyết được mismatch.
9. **Redirect 301/302 cho POST mà không xem method semantics:** client có thể đổi POST thành GET. Với redirect giữ method, cân nhắc 307/308.
10. **Dùng 308 khi URL canonical chưa ổn định:** redirect vĩnh viễn có thể được cache và khiến việc đổi policy khó hơn.
11. **Dùng mutateRequest nhưng quên log path gốc:** log ở các tầng khác nhau có thể cho thấy path khác nhau. Ghi rõ raw path và canonical path khi cần.
12. **Áp dụng filter cho root /**: UrlHandlerFilter loại trừ root path; không dựa vào filter để thay đổi /.
13. **Tưởng UrlHandlerFilter xử lý duplicate slash hoặc encoded slash:** filter chỉ giải quyết trailing slash theo pattern.
14. **Decode URI nhiều lần:** có thể biến encoded separator thành separator thật hoặc mở ra path traversal.
15. **Chỉ kiểm thử GET:** redirect cho POST/PUT/PATCH có hành vi về method và body cần xác minh.
16. **Bỏ qua reverse proxy:** proxy có thể canonicalize khác ứng dụng và tạo sai lệch trước khi request đến WebFlux.
17. **Cho rằng 404 là đủ để bảo vệ:** authorization phải được kiểm tra ở Security; không dựa vào controller mapping để thay thế.
18. **Không kiểm thử cả anonymous, user thường và admin:** status 200 ở một user không chứng minh path variants có cùng chính sách.
19. **Không kiểm tra nhiều SecurityWebFilterChain:** path có thể chọn chain khác nếu matcher và order không nhất quán.
20. **Không đồng bộ cache key:** /resource và /resource/ có thể lưu hai cache entry hoặc áp dụng policy cache khác nhau.

## 14. Checklist triển khai

- Đã xác định URL canonical cho từng nhóm endpoint chưa?
- Đã biết PathPatternParser mặc định không tự match slash cuối chưa?
- Có dùng UrlHandlerFilter của Spring Framework 6.2 khi cần không?
- Filter có chạy trước Spring Security không?
- Chọn redirect hay mutateRequest dựa trên hợp đồng client chưa?
- Nếu redirect, đã chọn status phù hợp và kiểm thử method/body chưa?
- Root path / có được xử lý đúng không?
- Mapping controller và Security matcher có dùng cùng path policy không?
- Các luật authorization cụ thể có đứng trước luật rộng không?
- Fallback có deny hoặc yêu cầu authentication theo chủ đích không?
- Proxy/gateway có cùng quy tắc canonical không?
- Encoded slash, duplicate slash, dot segment và matrix parameter có chính sách riêng không?
- Có test cả /path và /path/ với anonymous, USER và ADMIN không?
- Có test POST/PUT nếu endpoint hỗ trợ các method đó không?
- Log có thể đối chiếu path gốc và canonical path mà không lộ credentials không?

## 15. Câu hỏi tự kiểm tra

**1.** WebFlux sử dụng cơ chế path matching nào? PathPattern và PathPatternParser.

**2.** Từ Spring 6.0, /home có tự động match /home/ không? Không, optional trailing separator mặc định là false.

**3.** Vì sao trailing slash ảnh hưởng authorization? Security matcher và handler mapping có thể nhìn thấy hai path khác nhau, khiến request đi qua luật khác.

**4.** UrlHandlerFilter được giới thiệu từ phiên bản nào? Spring Framework 6.2.

**5.** UrlHandlerFilter có hai cách xử lý nào? Redirect client hoặc mutate request path nội bộ.

**6.** Vì sao filter phải chạy trước Spring Security? Để security matcher và controller nhận cùng canonical path.

**7.** mutateRequest() khác redirect như thế nào? Mutate thay path trong request nội bộ; redirect trả response để client gọi URL canonical.

**8.** HTTP 308 có ý nghĩa gì? Permanent Redirect; khi client follow redirect, method được giữ nguyên theo HTTP semantics.

**9.** UrlHandlerFilter có sửa root / không? Không, root path được loại trừ.

**10.** Vì sao @RequestMapping("/") có thể gây vấn đề sau khi bỏ trailing slash? Nó thêm slash vào mapping cấp class, khiến mapping không khớp path đã normalize.

**11.** Có thể dùng UrlHandlerFilter để xử lý %2F hoặc duplicate slash không? Không nên. Đây là các dạng path khác và cần policy riêng.

**12.** Nếu một request không khớp authorization rule cụ thể thì điều gì quan trọng? Phải xác định rõ fallback rule; không để path variant rơi vào luật yếu ngoài ý muốn.

**13.** Nên kiểm thử những identity nào? Anonymous, user thường và role được phép, trên cả path có và không có slash.

**14.** Nếu proxy đã rewrite path thì cần làm gì? Đồng bộ quy tắc giữa proxy, filter, Security matcher và handler mapping; kiểm thử toàn tuyến.

**15.** Bật setMatchOptionalTrailingSeparator(true) có phải giải pháp khuyến nghị không? Không; setter deprecated từ Spring 6.0. Dùng canonicalization rõ ràng.

**Ghi nhớ:** Trong Spring WebFlux, /path và /path/ là hai path riêng theo mặc định từ Spring 6.0. Nếu muốn chấp nhận cả hai, hãy chuẩn hóa bằng UrlHandlerFilter của Spring 6.2. Filter phải chạy trước Spring Security để authorization matcher và controller cùng nhìn thấy một canonical path. Chọn redirect 308 hoặc mutate request theo hợp đồng client, giữ root / đúng quy tắc và xử lý encoded path/duplicate slash bằng chính sách riêng.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — Reactive Core, URL Handler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebFlux Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-requestmapping.html)
- [PathPatternParser Javadoc — Default trailing separator behavior](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html)
- [UrlHandlerFilter Javadoc — WebFlux](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/filter/reactive/UrlHandlerFilter.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [PathPatternParserServerWebExchangeMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html)
- [RFC 9110 — HTTP Semantics, Redirection](https://www.rfc-editor.org/rfc/rfc9110.html).