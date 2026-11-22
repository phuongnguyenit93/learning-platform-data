# Cấu hình CORS bằng WebMvcConfigurer hoặc WebFluxConfigurer trong Spring Boot

## 1. CORS giải quyết vấn đề gì?

Một trang frontend chạy tại `http://localhost:5173` gọi API Spring Boot tại `http://localhost:8080/api/ping`. Browser có thể gửi request tới host/cổng khác, nhưng chính sách **same-origin policy** giới hạn JavaScript đọc một response từ origin khác nếu không có sự cho phép phù hợp của server.

**CORS (Cross-Origin Resource Sharing)** là cơ chế dựa trên **HTTP request/response headers** để server công bố những origin, method và header nào được browser phép sử dụng trong cross-origin requests. Trong Spring Boot, cách cấu hình CORS toàn cục thường dùng là:

- **Spring MVC/Servlet**: implement `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` và override `addCorsMappings(CorsRegistry)`.
- **Spring WebFlux/Reactive**: implement `org.springframework.web.reactive.config.WebFluxConfigurer` và override `addCorsMappings(CorsRegistry)`.

Hai API có mục đích tương tự, nhưng **khác package, khác web runtime và HandlerMapping**. Không chọn một API chỉ vì thấy tên “Web” chung.

Bài này thuộc mục **Proxy và CORS**, do đó ngoài cấu hình Java, chúng ta còn phân biệt **CORS tại backend, reverse proxy, API gateway, CDN, frontend dev proxy** và cách kiểm tra response cuối cùng mà browser thực sự thấy.

Mục tiêu:
1. Hiểu `Origin`, preflight `OPTIONS`, actual requests, các header `Access-Control-*` và `Vary`.
2. Tự viết global CORS mapping giới hạn đúng `/api/**` với origin cụ thể.
3. Chạy hai project Spring Boot Java 17+, một MVC và một WebFlux, cùng kiểm tra bằng `curl` và browser.
4. Sử dụng `allowedOrigins`, `allowedOriginPatterns`, `allowedMethods`, `allowedHeaders`, `exposedHeaders`, `allowCredentials`, `maxAge` đúng nghĩa.
5. Tránh wildcard + credentials, nhầm CORS với auth/CSRF, Security trả 401/403 trước preflight, proxy tạo header trùng nhau.
6. Chọn vị trí xử lý CORS khi ứng dụng nằm sau reverse proxy hoặc gateway.

> **Phiên bản thực hành:** Hai project riêng sử dụng **Java 17+ và Spring Boot 3.5.x**. MVC dùng starter `spring-boot-starter-web`, WebFlux dùng `spring-boot-starter-webflux`. Nếu tạo dự án Boot 4.x, starter MVC tương ứng là `spring-boot-starter-webmvc`. Nội dung CORS API và cách kiểm tra phù hợp với Spring Framework 6.2+/7.x ở nơi tính năng được hỗ trợ. Ví dụ chạy thử **không thêm Spring Security**; phần tích hợp Security có hướng dẫn riêng.

## 2. “Origin” không phải URL đầy đủ

Origin của browser được xác định bởi **scheme + host + port**. Phần path, query và fragment không thuộc origin.

Ví dụ:

| Trang đang mở | API được gọi | Có cùng origin không? |
|---|---|---|
| `http://localhost:5173` | `http://localhost:5173/api/ping` | Có |
| `http://localhost:5173` | `http://localhost:8080/api/ping` | Không, khác port |
| `https://shop.example.com` | `https://api.example.com/items` | Không, khác hostname |
| `https://example.com` | `http://example.com/api` | Không, khác scheme |
| `https://example.com` | `https://example.com:443/api` | Cùng origin, vì 443 là default HTTPS port |
| `https://example.com` | `https://example.com:8443/api` | Không, khác port |

Browser thêm header `Origin` cho CORS request khi thích hợp, ví dụ:

~~~http
Origin: http://localhost:5173
~~~

**Không ghi path** vào `allowedOrigins`:

~~~text
SAI:  http://localhost:5173/dashboard
ĐÚNG: http://localhost:5173
~~~

`/dashboard` là path của frontend route; không thuộc origin. Đừng đưa trailing slash tùy ý vào origin string. Với HTTPS ở production, `http://...` và `https://...` là hai origin khác nhau. Các URL `file://` hoặc môi trường sandbox có thể gửi `Origin: null`; không tùy tiện whitelist `null` vì có nguy cơ cho phép các nguồn không mong muốn.

CORS do **browser enforcement** áp dụng để giới hạn mã JavaScript đọc response. Một script dùng `curl`, Postman hoặc server-to-server HTTP client không bị browser same-origin policy điều khiển theo cùng cách. Server vẫn phải xác thực và phân quyền cho mọi client; **CORS không phải firewall chặn mọi HTTP request từ origin lạ**.

## 3. Cách một browser xử lý CORS request

### 3.1. Actual request không cần preflight

Một request GET đơn giản có thể được gửi trực tiếp:

~~~http
GET /api/ping HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

Nếu URL/handler có cấu hình cho phép origin, response có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"status":"ok"}
~~~

Browser kiểm tra `Access-Control-Allow-Origin`. Nếu phù hợp với origin caller và credential mode, JavaScript có thể đọc response. Nếu thiếu hoặc không khớp, browser có thể **không cho JavaScript truy cập response**, dù server đã thực hiện logic và trả HTTP 200 ở tầng mạng.

Vì vậy “trong Network tab nhìn thấy 200” **không có nghĩa CORS thành công**. Phải xem console, CORS response headers và response có được JavaScript đọc không.

### 3.2. Preflight OPTIONS

Một request POST gửi JSON (media type `application/json`) hoặc custom header như `Authorization` thường cần **preflight**:

~~~http
OPTIONS /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Spring CORS processor có thể phản hồi:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Đây là **minh họa headers**, không bảo đảm status code, thứ tự, dấu cách hoặc giá trị header đúng từng byte ở mọi server. Preflight hỏi liệu browser **được phép gửi** actual request có method/header đó; nó **không phải** chính request thực hiện nghiệp vụ.

Khi preflight được cho phép, browser có thể gửi actual request:

~~~http
POST /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Content-Type: application/json

{"text":"hello"}
~~~

CORS processor kiểm tra request, thêm CORS response headers và controller xử lý body JSON. Phản hồi có thể chứa:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: application/json

{"echo":"hello"}
~~~

**Lưu ý:** `allowedMethods("GET", "POST")` nói về những **actual HTTP methods** có thể được browser sử dụng. Không bắt buộc phải thêm `OPTIONS` vào allowedMethods chỉ để trả lời preflight; Spring CORS processor tự xử lý preflight OPTIONS đối với mapping phù hợp.

### 3.3. “Simple request” không đồng nghĩa an toàn

Một số request đáp ứng tiêu chí CORS-safelisted method/headers và Content-Type có thể bỏ qua preflight. Nhưng **không có preflight** không có nghĩa người dùng được phép gọi endpoint, cũng không có nghĩa request miễn CSRF. Browser có thể gửi những request cross-origin nhất định rồi chặn JavaScript đọc response.

Preflight còn có thể được browser **cache riêng** theo `Access-Control-Max-Age`. Khi đổi policy, browser cũ có thể chưa gửi OPTIONS mới do preflight cache; hãy kiểm thử trong browser session sạch hoặc điều chỉnh thời gian cache ở môi trường thử.

## 4. Các CORS headers phải hiểu chính xác

| Header | Chiều | Vai trò |
|---|---|---|
| `Origin` | Request | Origin của mã client đang yêu cầu |
| `Access-Control-Request-Method` | Preflight request | Actual method mà client muốn dùng |
| `Access-Control-Request-Headers` | Preflight request | Tên request headers không safelisted sẽ gửi |
| `Access-Control-Allow-Origin` | Response | Origin được phép truy cập response, hoặc `*` khi hợp lệ |
| `Access-Control-Allow-Methods` | Preflight response | Các actual methods được phép |
| `Access-Control-Allow-Headers` | Preflight response | Các request headers được phép gửi |
| `Access-Control-Allow-Credentials` | Response | Cho phép browser phơi lộ credentialed response khi chính sách client cũng phù hợp |
| `Access-Control-Expose-Headers` | Actual response | Những response headers ngoài CORS-safelisted response headers mà JS được phép đọc |
| `Access-Control-Max-Age` | Preflight response | Thời gian browser có thể cache kết quả preflight |
| `Vary: Origin` | Response | Giúp cache phân biệt response phụ thuộc `Origin` |
| `Vary: Access-Control-Request-Method` | Response | Hữu ích khi preflight outcome phụ thuộc method |
| `Vary: Access-Control-Request-Headers` | Response | Hữu ích khi preflight outcome phụ thuộc headers |

`Access-Control-Max-Age` **không phải** TTL cho response JSON của API; đó là cache của preflight. HTTP `Cache-Control` vẫn điều khiển việc cache representation. Nếu có CDN/shared cache, `Vary` cần được giữ đúng khi CORS header thay đổi theo `Origin`, không để cached response cho origin A bị dùng với header của origin B.

## 5. Vì sao chọn WebMvcConfigurer hay WebFluxConfigurer?

| Trường hợp | API cấu hình | Package quan trọng |
|---|---|---|
| Spring MVC / Servlet | `WebMvcConfigurer` | `org.springframework.web.servlet.config.annotation` |
| Spring WebFlux / Reactive | `WebFluxConfigurer` | `org.springframework.web.reactive.config` |
| Chỉ một controller muốn rule riêng | `@CrossOrigin` | `org.springframework.web.bind.annotation` |
| CORS trước filter chain hoặc yêu cầu đặc biệt | `CorsFilter` (MVC), `CorsWebFilter` (WebFlux) | `org.springframework.web.filter` / `org.springframework.web.cors.reactive` |
| Gateway làm reverse proxy cho nhiều service | Config CORS ở gateway phù hợp | Không giả định Configurer của backend xử lý được các route của gateway |

Spring MVC dùng `DispatcherServlet` và các MVC `HandlerMapping`. WebFlux dùng reactive `HandlerMapping` và `WebHandler`. Cả hai hỗ trợ callback `addCorsMappings` nhưng chỉ tác động lên stack của nó.

Nếu thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường chọn **SERVLET/MVC**. Việc import `WebClient` không tự chuyển toàn bộ ứng dụng sang WebFlux. Muốn học chính xác, nên chạy hai dự án riêng thay vì trộn cả hai starter.

**Spring Boot autoconfiguration:** không cần `@EnableWebMvc` hoặc `@EnableWebFlux` chỉ để thêm CORS mapping. Hai annotation này đưa nhiều quyết định MVC/WebFlux config về phía ứng dụng và có thể thay đổi những mặc định Boot đang quản lý. Một `@Configuration` implement configurer là lựa chọn đúng cho yêu cầu bài này.

## 6. Các phương thức của CorsRegistration trong addCorsMappings

Ví dụ áp dụng cho URL pattern `/api/**`:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins("http://localhost:5173")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
        .exposedHeaders("X-Request-Id")
        .allowCredentials(false)
        .maxAge(1800);
~~~

Giải thích:

- `addMapping("/api/**")`: giới hạn URL paths được áp dụng **global CORS rule**. Pattern này không tạo endpoint, không thay đổi routing controller, và không có nghĩa API phải bắt đầu bằng path `/api` nếu controller thực tế nằm ở path khác.
- `allowedOrigins(...)`: danh sách **origin chính xác** được phép, gồm scheme/host/port. Có thể cho nhiều origin đã xác minh, ví dụ localhost frontend và production frontend.
- `allowedMethods(...)`: các actual methods browser được phép dùng. Nếu API có PUT/DELETE, thêm có chủ đích sau khi đã test.
- `allowedHeaders(...)`: request headers mà client có thể yêu cầu trong preflight, ví dụ `Content-Type`, `Authorization`, `X-Request-Id`. Chúng **không phải** response headers.
- `exposedHeaders(...)`: response headers JavaScript có thể truy cập bằng `response.headers.get(...)` ngoài danh sách response headers safelisted. Nó không cấp phép gửi request headers.
- `allowCredentials(false)`: demo không sử dụng cross-origin cookie/HTTP credentials. Mặc định global CORS cũng không bật credentials; viết explicit giúp rõ ý đồ.
- `maxAge(1800)`: giá trị tính bằng **giây** cho preflight cache, ở đây 30 phút. Browser có thể áp giới hạn riêng.
- Dấu `/**` là path matching, không phải wildcard “mọi origin”.

### Default global CORS quá rộng nếu không khai báo rõ

Theo Spring Framework, global CORS mapping mặc định cho phép all origins và headers, với các method GET/HEAD/POST, và không bật credentials. Vì vậy không nên chỉ viết `registry.addMapping("/**")` trong API production rồi nghĩ rằng mọi method/domain đã được giới hạn an toàn. Hãy khai báo policy phù hợp với hợp đồng API thực tế.

## 7. Bài thực hành A — Spring Boot MVC với WebMvcConfigurer

Tạo dự án bằng **Spring Initializr**: Spring Boot **3.5.x**, Java 17+, Gradle, dependency **Spring Web**. Dự án có Gradle wrapper từ Initializr. Nếu project đã có Boot plugin và dependency management, starter được khai báo như sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Đây là **fragment dependency**, không phải toàn bộ file build. Với Boot 4.x, chọn `spring-boot-starter-webmvc`.

Tạo **một file Java** ở `src/main/java/demo/corsmvc/CorsMvcApplication.java`:

~~~java
package demo.corsmvc;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsMvcApplication.class, args);
    }
}

@Configuration
class MvcCorsConfiguration implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(false)
                .maxAge(1800);
    }
}

@RestController
class MvcDemoController {
    public record EchoRequest(String text) { }

    @GetMapping("/api/ping")
    public ResponseEntity<Map<String, String>> ping() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-42")
                .body(Map.of("status", "ok"));
    }

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> echo(@RequestBody EchoRequest input) {
        return Map.of("echo", input.text());
    }
}
~~~

Các class `MvcCorsConfiguration` và `MvcDemoController` cố ý là **package-private top-level classes** trong cùng source file; Java cho phép một file có một `public` class và các class không public. Spring Boot component scanning từ package `demo.corsmvc` sẽ tìm thấy hai bean có annotations. Không cần tạo file Java phụ.

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

Chạy từ root dự án:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ứng dụng có hai API:
- `GET /api/ping` trả `{"status":"ok"}` và response header `X-Request-Id: demo-42`.
- `POST /api/echo` nhận JSON `{"text":"hello"}` và trả `{"echo":"hello"}`.

### 7.1. Kiểm tra actual GET có Origin hợp lệ

~~~bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/ping
~~~

**Response body kỳ vọng:**

~~~json
{"status":"ok"}
~~~

Các response headers đáng tìm:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: X-Request-Id
X-Request-Id: demo-42
Vary: Origin
~~~

Header `Vary` thực tế có thể được ghi dưới dạng một hoặc nhiều field lines, bổ sung `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Không yêu cầu output khớp từng dòng/viết hoa. Vì `allowCredentials(false)`, không kỳ vọng `Access-Control-Allow-Credentials: true`.

### 7.2. Kiểm tra preflight OPTIONS trước POST JSON

~~~bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' \
  http://localhost:8080/api/echo
~~~

Các headers cần xác minh ở response preflight được cho phép:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
~~~

HTTP status thường là 200 ở cấu hình này; response body có thể là rỗng hoặc khác theo framework. Cụm `Content-Type` trong allowedHeaders là tên request header được phép, **không liên quan** việc bật CORS cho response content type.

### 7.3. Gửi actual POST

~~~bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/echo
~~~

**Response body kỳ vọng:**

~~~json
{"echo":"hello"}
~~~

Lưu ý `curl` **không tự làm browser preflight**: lệnh `OPTIONS` và lệnh `POST` được chạy độc lập. Browser tự quyết định có preflight hay không dựa trên method/headers/credentials và policy.

### 7.4. Test origin không được phép

~~~bash
curl -i \
  -H 'Origin: https://untrusted.example.test' \
  http://localhost:8080/api/ping
~~~

Origin này không nằm trong danh sách. Với Spring MVC CORS processor mặc định, request cross-origin bị từ chối có thể trả **403 Invalid CORS request**, tùy handler/filter/security/proxy. **Không dựa vào status đúng một giá trị** để xác nhận bảo mật: xem `Access-Control-Allow-Origin` có cho phép origin lạ không, và kiểm chứng hành vi thực tế ở browser.

Quan trọng hơn, **CORS không thay thế authentication**. Nếu API có request cùng-origin hoặc client server-to-server, chúng vẫn có thể đến controller khi hợp lệ ở các tầng khác.

## 8. Bài thực hành B — Spring Boot WebFlux với WebFluxConfigurer

Tạo **dự án riêng**, Spring Boot 3.5.x, Java 17+, Gradle, dependency **Spring Reactive Web**. Không thêm starter MVC. Dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Tạo file `src/main/java/demo/corsflux/CorsWebFluxApplication.java`:

~~~java
package demo.corsflux;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class CorsWebFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsWebFluxApplication.class, args);
    }
}

@Configuration
class ReactiveCorsConfiguration implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(false)
                .maxAge(1800);
    }
}

@RestController
class ReactiveDemoController {
    public record EchoRequest(String text) { }

    @GetMapping("/api/ping")
    public Mono<ResponseEntity<Map<String, String>>> ping() {
        return Mono.just(ResponseEntity.ok()
                .header("X-Request-Id", "demo-42")
                .body(Map.of("status", "ok")));
    }

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<EchoRequest> input) {
        return input.map(body -> Map.of("echo", body.text()));
    }
}
~~~

Mã là một Java source file hoàn chỉnh của dự án WebFlux. Cả `ReactiveCorsConfiguration` và controller đều được Spring scan. Import `CorsRegistry` ở đây là **`org.springframework.web.reactive.config.CorsRegistry`**, không phải package servlet. Handler POST sử dụng `Mono<EchoRequest>` và `Mono<Map<...>>` để phản ánh kiểu lập trình reactive. Không gọi `block()` trong controller.

Chạy `./gradlew bootRun` (hoặc Windows `.\gradlew.bat bootRun`) từ **project WebFlux**, sau khi dừng ứng dụng MVC nếu chúng dùng cùng cổng 8080.

Dùng **y hệt ba bộ lệnh curl ở mục 7** để kiểm chứng:
1. GET `/api/ping` với origin cho phép: body `{"status":"ok"}` và CORS headers.
2. OPTIONS `/api/echo` với POST, content-type: header preflight phù hợp.
3. POST JSON `{"text":"hello"}`: body `{"echo":"hello"}`.

Các HTTP headers, status và CORS policy có thể được áp dụng tương đương vì cùng định nghĩa, dù runtime khác nhau. Đừng nhận xét WebFlux “không cần CORS” chỉ vì nó không dùng Servlet: browser same-origin policy không phụ thuộc server reactive hay blocking.

## 9. Dùng allowedOriginPatterns khi cần danh sách tên miền con

Nếu frontend hợp pháp nằm ở một số subdomain, có thể dùng `allowedOriginPatterns(...)`:

~~~java
// Fragment trong addCorsMappings của MVC hoặc WebFlux:
registry.addMapping("/api/**")
        .allowedOriginPatterns("https://*.example.com")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type")
        .allowCredentials(true);
~~~

**Phân biệt:**
- `allowedOrigins("https://app.example.com")` dùng để cho phép **chính xác** một origin.
- `allowedOrigins("*")` cho phép mọi origin trong trường hợp không dùng credentials. Nó không thể dùng chung với `allowCredentials(true)` trong Spring Framework.
- `allowedOriginPatterns("https://*.example.com")` dùng pattern matching cho nhóm origin; khi match, Spring phản hồi bằng **origin cụ thể đã match**, thay vì trả ký tự `*` trong `Access-Control-Allow-Origin`. Do đó nó có thể dùng cùng credentials theo cơ chế của Spring.

Nhưng **có thể về cú pháp không đồng nghĩa an toàn về chính sách**. Wildcard subdomain có thể vô tình bao gồm subdomain do bên thứ ba kiểm soát, website do user tự tạo hoặc môi trường staging kém an toàn. Với cookie-based auth, điều đó mở rộng nhóm website có thể đọc dữ liệu người dùng. Ưu tiên danh sách origin hữu hạn; chỉ dùng patterns sau khi đánh giá quyền quản lý subdomain và rủi ro takeover.

Không biến `allowedOriginPatterns("*")` thành chính sách production khi dùng credentials: về thực chất nó sẽ cho phép vô số origin và tăng rủi ro nghiêm trọng. Nếu hệ thống cần nhiều tenant origins động, cân nhắc allowlist có quản lý, xác minh ownership tenant và cập nhật cấu hình an toàn.

### Các lỗi nhập URL thường gặp

- `allowedOrigins("localhost:5173")` thiếu scheme: origin không đúng.
- `allowedOrigins("https://example.com/path")` chứa path: không khớp browser Origin.
- Chỉ whitelist `http://localhost:5173` nhưng frontend chạy `http://127.0.0.1:5173`: đây là origin khác.
- Whitelist `https://app.example.com` nhưng request thực tế từ `https://www.app.example.com`: khác hostname.
- Chạy HTTPS frontend nhưng chỉ cho phép HTTP origin: khác scheme.
- Nhầm `*.example.com` với apex origin `https://example.com`: cần khai báo apex riêng nếu muốn cho phép.

## 10. Credentials, cookies và fetch: ba điều kiện phải đồng thời đúng

Trong demo, `allowCredentials(false)` vì không có session cookie cross-origin. Khi frontend thật cần gửi cookie session:

~~~javascript
const response = await fetch("https://api.example.com/me", {
  credentials: "include"
});
const data = await response.json();
~~~

Server cần policy tương thích, ví dụ:

~~~java
// Fragment addCorsMappings trong configurer đúng stack:
registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type", "X-CSRF-TOKEN")
        .allowCredentials(true);
~~~

Đối với credentialed CORS request, browser cần đồng thời:
1. Frontend gửi request với **credential mode phù hợp**, như `credentials: "include"` cho cross-origin fetch có cookie.
2. Response từ server có **`Access-Control-Allow-Origin` bằng origin cụ thể**, không phải `*`.
3. Response có **`Access-Control-Allow-Credentials: true`**.
4. Cookie phải phù hợp với **Domain, Path, SameSite, Secure và cookie policy** của browser. Với cross-site cookie, thường phải xét `SameSite=None; Secure` cùng HTTPS và chính sách third-party cookies của browser.
5. Endpoint vẫn phải có auth/authorization/CSRF policy phù hợp; CORS chỉ xử lý khả năng browser phơi lộ response.

**Chú ý Origin khác Site.** Hai hostname `app.example.com` và `api.example.com` là **khác origin** (có thể cần CORS), nhưng thường vẫn là **same-site** theo mô hình schemeful site nếu cùng scheme và registrable domain. Điều kiện SameSite không giống hệt điều kiện CORS.

`Access-Control-Allow-Credentials: true` không tự làm browser gửi cookie nếu client không yêu cầu hoặc cookie bị chặn. Ngược lại, `credentials:"include"` không vượt qua việc server không whitelist origin.

### Bearer token và credentials

Nếu frontend gửi `Authorization: Bearer ...`, việc thêm Authorization header thường làm request cần preflight và `allowedHeaders("Authorization")`. CORS không kiểm tra token có hợp lệ. Tùy credential mode và cách request được tạo, các quy tắc browser về credentials và response vẫn cần được hiểu, nhưng **đừng tự đánh đồng “có Authorization header” với “phải luôn allowCredentials(true)”**. Với API token-based không dùng cookie, thường chỉ cần giới hạn origin/method/header và xác thực token ở server theo đúng thiết kế.

## 11. CORS không thay thế authentication, authorization hay CSRF

CORS là cơ chế browser quản lý quyền **đọc cross-origin response**, không phải cơ chế bắt buộc mọi client phải tuân theo. Ví dụ một endpoint xóa dữ liệu không được bảo vệ bởi auth có thể bị gọi trực tiếp bằng curl bất kể CORS config. Một trang độc hại có thể kích hoạt một số loại request mà không đọc được response; vì vậy CORS **không tự chặn CSRF**.

Với ứng dụng dùng session cookie:
- Bảo vệ state-changing endpoints bằng CSRF protection hoặc biện pháp hợp lệ tương ứng.
- Dùng xác thực và phân quyền ở backend cho mọi request cần quyền.
- Chỉ whitelist các origins mà bạn thực sự muốn cho JavaScript đọc response có dữ liệu nhạy cảm.
- Không bật credentials cho mọi origin chỉ để “sửa lỗi CORS”.
- Không thay đổi Security policy kiểu `anyRequest().permitAll()` nhằm giải quyết preflight 401.

## 12. Spring Security: xử lý CORS trước authorization

Khi thêm Spring Security, request preflight `OPTIONS` thường **không mang session cookie** như actual request; nếu Security xử lý như một yêu cầu chưa xác thực trước khi CORS processor chạy, nó có thể trả 401/403 khiến browser không bao giờ gửi POST thật.

### Spring MVC và SecurityFilterChain

Nếu CORS rule đã khai báo qua `WebMvcConfigurer` và Spring MVC ở classpath, Spring Security có thể tích hợp MVC CORS configuration bằng `http.cors(...)` khi không có nguồn cấu hình CORS cạnh tranh. Ví dụ **fragment** trong class `@Configuration` dùng Spring Security 6.5 (Boot 3.5):

~~~java
// Fragment, cần Spring Security dependency và imports tương ứng.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        );
    return http.build();
}
~~~

Các imports quan trọng:
- `org.springframework.security.config.Customizer`
- `org.springframework.security.web.SecurityFilterChain`
- `org.springframework.security.config.annotation.web.builders.HttpSecurity`
- `org.springframework.context.annotation.Bean`

Đoạn này **không runnable độc lập** và không biến API demo mục 7 thành API công khai: nó yêu cầu authentication thật. Với POST dùng cookie/session, cần còn xử lý CSRF; không tắt CSRF bừa bãi chỉ để test.

### WebFlux và SecurityWebFilterChain

Ứng dụng WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`, không dùng `HttpSecurity` của Servlet:

~~~java
// Fragment Spring Security reactive, cần imports và bean configuration.
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http.cors(Customizer.withDefaults())
        .authorizeExchange(auth ->
            auth.anyExchange().authenticated()
        )
        .build();
}
~~~

Để cấu hình CORS phức tạp hoặc quản lý sớm ở filter, WebFlux có `CorsWebFilter` và nguồn `UrlBasedCorsConfigurationSource` từ package reactive; Servlet có `CorsFilter` và nguồn cấu hình Servlet. **Không đăng ký đồng thời nhiều filter CORS có cùng trách nhiệm** mà không xác định ai phát/ghi đè header.

### Khi nào Configurer chưa đủ?

- CORS cần chạy **trước security filter chain** nhưng security integration đang không nhận mapping.
- API sử dụng **functional endpoints** hoặc gateway routing không tham gia cùng annotated HandlerMapping.
- Cần xác minh CORS sớm trong một filter/cross-cutting pipeline trước khi handler mapping có hiệu lực.
- Nhiều security chains hoặc CORS policies động theo tenant yêu cầu source riêng.

Khi đó cân nhắc `CorsConfigurationSource` với `CorsFilter` / `CorsWebFilter` và tích hợp đúng Security version. Không giải quyết bằng cách vô hiệu hóa authentication/CSRF.

## 13. Chọn nơi xử lý CORS khi có reverse proxy hoặc gateway

Một kiến trúc phổ biến:

~~~text
Browser https://app.example.com
       |
       | Origin: https://app.example.com
       v
CDN / reverse proxy / API gateway
       |
       +------> Spring Boot MVC service A
       |
       +------> Spring Boot WebFlux service B
~~~

Có hai cách hợp lý tùy kiến trúc:

**Cách A — backend tự xử lý CORS** qua Configurer. Proxy chuyển `Origin`, OPTIONS và các headers cần thiết đến backend, và bảo toàn các response headers do backend trả về. Phù hợp khi mỗi service có API và origin policy riêng.

**Cách B — gateway xử lý CORS tập trung**. Gateway trả preflight và thêm CORS headers cho browser. Phù hợp khi nhiều backend dùng cùng policy và gateway kiểm soát routing. Khi dùng cách này, cần tránh để backend cũng trả header CORS trùng hoặc xung đột.

Đừng giả định `WebMvcConfigurer` của backend có thể xử lý preflight bị chặn tại CDN/gateway: request có thể chưa tới backend. Tương tự, WebFluxConfigurer của một service không tự cấu hình toàn bộ Spring Cloud Gateway ở service khác.

### Các lỗi proxy thường gặp

- Gateway **chặn OPTIONS** vì chỉ route GET/POST hoặc auth filter bắt preflight.
- Reverse proxy thêm `Access-Control-Allow-Origin: *` lên mọi response trong khi backend trả origin cụ thể; browser gặp **nhiều hoặc xung đột CORS header values**.
- Proxy ghi đè `Vary`, khiến cached response của origin A được dùng cho origin B.
- Host/scheme bị rewrite làm logic origin/security ở backend khác thực tế public URL.
- Frontend dùng dev proxy như Vite `/api`; browser gọi **same-origin dev server** nên CORS không xuất hiện trong local, nhưng deployment production gọi API domain trực tiếp lại cần policy.
- Một phần endpoint trả từ gateway (404/502), phần còn lại từ backend 200: headers CORS không thống nhất, browser chỉ hiển thị “CORS error” thay vì nguyên nhân HTTP thực.

**Nguyên tắc vận hành:** xác định rõ **tầng duy nhất sở hữu CORS policy** cho từng public route. Nếu nhiều tầng bắt buộc góp phần, định nghĩa trách nhiệm merge headers và test response cuối cùng ở public endpoint.

## 14. CORS, Vary và cache HTTP

Khi CORS response thay đổi `Access-Control-Allow-Origin` theo request `Origin`, shared cache cần tránh trộn các variants:

~~~http
Vary: Origin
~~~

Với preflight, các điều kiện `Access-Control-Request-Method` và `Access-Control-Request-Headers` cũng có thể ảnh hưởng response:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Spring CORS processor có thể thêm các header `Vary` phù hợp; kiểm tra response từ gateway/CDN, không xóa khi thêm compression hoặc cache policy khác. **Vary không quyết định response được phép lưu hay không.** Với dữ liệu theo người dùng, dùng `Cache-Control: private` hoặc `no-store` phù hợp, không kỳ vọng chỉ `Vary: Origin` hay `Vary: Cookie` là biện pháp bảo mật dữ liệu.

Phân biệt:
- **`Access-Control-Max-Age`**: browser cache kết quả *preflight*.
- **`Cache-Control`**: private/shared HTTP caches quyết định lưu/tái sử dụng response.
- **`Vary`**: các request headers dùng để chọn đúng response variant.

Nếu frontend dùng cookie session, response cá nhân có thể thay đổi theo user ngay cả khi `Origin` giống nhau; vì vậy chỉ vary theo origin **không ngăn rò dữ liệu** qua shared caching. Policy HTTP cache riêng cho user data là bắt buộc.

## 15. @CrossOrigin so với global CORS configuration

`@CrossOrigin` cho phép rule tại controller class/method:

~~~java
// Fragment Spring MVC hoặc WebFlux annotated controller.
@CrossOrigin(origins = "https://app.example.com")
@GetMapping("/api/status")
public String status() {
    return "ok";
}
~~~

Ưu điểm: rule dễ đọc gần endpoint. Nhược điểm: dễ lặp across controllers, và policy có thể phân tán.

`WebMvcConfigurer` / `WebFluxConfigurer` là nơi tốt để quản lý **policy toàn cục theo URL namespace**, có thể test centrally.

Spring Framework có thể **kết hợp global và local CORS configurations**:
- Danh sách origins/methods/headers thường được hợp nhất theo cách cộng dồn.
- Các thuộc tính chỉ có một giá trị như `allowCredentials` và `maxAge` thường lấy local override global.
- Kết quả cuối có thể **rộng hơn mong đợi**, ví dụ global cho A, local cho B ⇒ cả A+B đều được phép ở route đó.

Vì vậy khi cần một allowlist chặt, **đừng giả định `@CrossOrigin` sẽ thay thế hoàn toàn global CORS origin list**. Đọc quy tắc combine của `CorsConfiguration` và test nhiều origin. Tránh đặt global `/**` quá rộng rồi cố “siết” từng controller bằng annotation, vì default hợp nhất có thể không phù hợp mục tiêu.

## 16. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh/sửa |
|---|---|---|
| Console báo “No Access-Control-Allow-Origin” | Không có CORS mapping phù hợp hoặc proxy làm rơi header | Xem Origin, URL, path pattern, response cuối |
| `OPTIONS` trả 401 | Security filter xử lý trước CORS | Tích hợp `http.cors` hoặc `CorsWebFilter` theo stack, không tắt auth |
| `OPTIONS` trả 404/405 | Gateway không route OPTIONS hoặc custom handler chặn | Xem gateway/proxy/router, Spring HandlerMapping |
| `OPTIONS` thành công nhưng POST lỗi | Actual request auth/CSRF/validation hoặc proxy behavior khác | Xem response của POST và logs, không kết luận CORS đã đủ |
| GET browser bị chặn, curl thấy 200 | Curl không thực thi browser CORS check | Xem ACAO/ACAC, DevTools console và origin thật |
| Browser báo wildcard không dùng được với credentials | `allowCredentials(true)` + `allowedOrigins("*")` hoặc ACAO wildcard | Thay bằng origin hữu hạn/pattern có kiểm soát |
| Cấu hình localhost đúng nhưng frontend vẫn lỗi | Frontend chạy khác port/scheme/hostname | So sánh Origin với allowedOrigins đúng từng byte/ngữ nghĩa |
| CORS error chỉ xảy ra production | Dev proxy same-origin che dấu vấn đề; gateway thay đổi route/headers | Test URL production public qua browser |
| Có hai Access-Control-Allow-Origin | Gateway và backend cùng thêm CORS headers | Chỉ định chủ sở hữu CORS, bỏ header trùng |
| `allowedHeaders` có Authorization nhưng JS không đọc được X-Request-Id | Nhầm request allowedHeaders với response exposedHeaders | Bổ sung `exposedHeaders("X-Request-Id")` |
| API bị 403 khi Origin lạ | Spring CORS processor từ chối | Xác minh origin allowlist, không vội thêm mọi origin |
| Ứng dụng WebFlux nhưng WebMvcConfigurer không hiệu lực | Import/configurer thuộc Servlet | Dùng `WebFluxConfigurer` từ package reactive |
| Ứng dụng MVC nhưng WebFluxConfigurer không hiệu lực | Boot chọn Servlet/MVC | Dùng `WebMvcConfigurer` từ package MVC |
| `@CrossOrigin` cục bộ không “thắt chặt” origin | Global và local origin lists được hợp nhất | Xem `CorsConfiguration.combine` và sửa global policy |
| Cross-site cookie không được gửi | `credentials:"include"` thiếu, SameSite/Secure/Domain sai hoặc third-party cookie blocked | Kiểm tra DevTools Cookies và HTTPS policy |
| Browser vẫn báo CORS ở lỗi 500 | Exception response từ proxy/error handler không có CORS header | Xem status thật và giữ CORS xử lý nhất quán trên error path |
| Chỉnh backend mà CDN không đổi | OPTIONS/ACAO được xử lý/cached ở CDN | Xem config gateway, invalidate cache theo chính sách |
| `Origin: null` khiến request fail | Browser từ sandbox/file origin; không nằm allowlist | Sử dụng frontend có HTTP origin hợp lệ; không whitelist null bừa bãi |

### Trình tự debug gọn

1. Ghi **trang frontend origin thực tế** theo scheme/host/port.
2. Ghi **request URL**, method và headers (nhất là Content-Type, Authorization, custom headers).
3. Xem có preflight OPTIONS không; nếu có, ghi ``Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
4. Tìm tầng nào trả response đầu tiên (browser cache, CDN, gateway, Spring).
5. Kiểm tra CORS rule: `addMapping`, origins, methods, allowedHeaders, credentials.
6. Nếu Security có mặt, kiểm tra thứ tự xử lý CORS và Security/CSRF.
7. Kiểm tra actual response `Access-Control-Allow-Origin`/`Access-Control-Allow-Credentials` và `Vary`.
8. Thử trên browser thật, không kết luận chỉ từ curl.
9. Chỉnh đúng tầng và test cả origin hợp lệ lẫn origin bị cấm.

## 17. Kiểm thử tự động bằng MockMvc và WebTestClient

Không cần khởi chạy browser cho mọi trường hợp; có thể kiểm tra status và headers server-side bằng test.

### 17.1. MVC — MockMvc

Đây là **fragment test** trong project MVC có `spring-boot-starter-test` và Spring Boot test infrastructure:

~~~java
// Trong @SpringBootTest + @AutoConfigureMockMvc test class,
// có @Autowired MockMvc mvc; imports theo Spring Test.
mvc.perform(options("/api/echo")
        .header("Origin", "http://localhost:5173")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type"))
   .andExpect(status().isOk())
   .andExpect(header().string(
       "Access-Control-Allow-Origin", "http://localhost:5173"));
~~~

Vì đây là fragment, không tự chạy riêng bằng `javac`. Với project Boot 3.5, MockMvc cùng các matchers thuộc Spring Test đã được kéo vào bằng starter test. Bài thực hành đầy đủ ở mục 7 vẫn tự chạy độc lập và không phụ thuộc test fragment.

### 17.2. WebFlux — WebTestClient

Đây là **fragment test** trong project WebFlux có `spring-boot-starter-test`, inject `WebTestClient` với cấu hình test phù hợp:

~~~java
// Trong integration test đã cấu hình WebTestClient client:
client.options()
      .uri("/api/echo")
      .header("Origin", "http://localhost:5173")
      .header("Access-Control-Request-Method", "POST")
      .header("Access-Control-Request-Headers", "content-type")
      .exchange()
      .expectStatus().isOk()
      .expectHeader()
      .valueEquals("Access-Control-Allow-Origin",
                   "http://localhost:5173");
~~~

`WebTestClient` hỗ trợ kiểm tra reactive handler không cần lập trình thủ công HTTP client. Tuy nhiên output thực của **browser** còn phụ thuộc cache, cookie policy, Origin do browser phát và proxy/CDN, nên integration test không thay thế hoàn toàn kiểm thử end-to-end.

### Ma trận kiểm thử CORS nên có

| Case | Origin | Method/Header | Kỳ vọng |
|---|---|---|---|
| GET hợp lệ | `http://localhost:5173` | GET | CORS cho phép, body đúng |
| POST JSON hợp lệ | `http://localhost:5173` | OPTIONS → POST; content-type | Preflight cho phép; POST tới controller |
| Origin khác | `https://untrusted.example.test` | GET | Không được browser đọc như allowed origin |
| Method không cho phép | `http://localhost:5173` | Preflight DELETE | Không công bố cho phép DELETE |
| Header không cho phép | `http://localhost:5173` | Preflight `X-Forbidden` | Không công bố cho phép header đó |
| Không có Origin | Không gửi | GET | Request same-origin/server-to-server vẫn xử lý theo auth/routing |
| Credentials với wildcard | Origin được chọn | `credentials:"include"` | Không dùng `Access-Control-Allow-Origin: *` |
| Security bật | Origin hợp lệ | OPTIONS / POST | Preflight đi trước auth; POST có auth/CSRF hợp lệ |
| Sau gateway | Origin hợp lệ và không hợp lệ | OPTIONS và actual | Một policy nhất quán, không trùng CORS headers |

## 18. Tóm tắt quy trình triển khai an toàn

Một chính sách CORS ổn định nên bắt đầu từ **nguồn phát request của frontend thật**, thay vì từ lỗi console. Nếu frontend ở `https://app.example.com` và API ở `https://api.example.com`, viết policy rõ ràng cho `/api/**`, origin, methods và headers thực sự dùng. Sau đó:
- Chọn **WebMvcConfigurer** nếu Boot chạy Servlet/MVC, hoặc **WebFluxConfigurer** nếu Boot chạy WebFlux.
- Đặt configurer trong package được component scan, không cần `@EnableWebMvc`/`@EnableWebFlux`.
- Chỉ dùng credentials khi có nhu cầu cookie/credentials cross-origin; whitelist các origins tin cậy.
- Đảm bảo CORS hoạt động **trước hoặc tích hợp đúng với Security**, nhưng không hạ authorization/CSRF.
- Nếu có gateway/proxy, xác định chính xác ai sở hữu CORS và ai xử lý OPTIONS.
- Theo dõi `Access-Control-Allow-Origin`, `Vary`, logs của OPTIONS/POST, cache policies và browser behavior.
- Kiểm tra bằng **cặp preflight + actual request**, ở cả môi trường development và public endpoint production.

## 19. Câu hỏi ôn tập

**Câu 1.** Trang `http://localhost:5173` gọi `http://localhost:8080/api/ping`. Vì sao cần CORS?

**Đáp án:** Cùng host nhưng khác port nên khác origin; browser hạn chế JavaScript đọc response trừ khi CORS response headers phù hợp.

**Câu 2.** MVC và WebFlux cùng có `addCorsMappings`, vậy có thể dùng `WebMvcConfigurer` cho WebFlux không?

**Đáp án:** Không. Phải implement đúng configurer và `CorsRegistry` theo stack: MVC package `org.springframework.web.servlet.config.annotation`; WebFlux package `org.springframework.web.reactive.config`.

**Câu 3.** Đã đặt `allowedMethods("GET","POST")`, có phải thêm `"OPTIONS"` để trả lời preflight không?

**Đáp án:** Không bắt buộc. `allowedMethods` mô tả actual methods; CORS processor xử lý OPTIONS preflight cho route phù hợp.

**Câu 4.** `allowedHeaders("Authorization")` có tự cho JavaScript đọc response header `X-Request-Id` không?

**Đáp án:** Không. `allowedHeaders` áp dụng cho request headers; muốn JS đọc một response header không safelisted phải cấu hình `exposedHeaders("X-Request-Id")`.

**Câu 5.** Có thể dùng `allowedOrigins("*").allowCredentials(true)` không?

**Đáp án:** Không. Spring Framework không cho dùng wildcard all-origins theo `allowedOrigins("*")` khi credentials true. Dùng allowlist origin cụ thể; `allowedOriginPatterns` chỉ khi thật sự cần và đã kiểm soát phạm vi.

**Câu 6.** Vì sao sau khi bật Spring Security, CORS preflight bị 401 nhưng curl GET không có Origin vẫn chạy?

**Đáp án:** Preflight thiếu cookie/session và có thể bị Security xử lý trước CORS; cần tích hợp đúng CORS trước Security. GET không có Origin không đại diện một CORS preflight.

**Câu 7.** Nếu proxy trả `Access-Control-Allow-Origin`, còn backend cũng trả header đó, kết quả có thể ra sao?

**Đáp án:** Response có thể chứa CORS headers trùng/xung đột khiến browser từ chối; chọn tầng quản lý nhất quán hoặc merge đúng luật.

**Câu 8.** CORS có bảo vệ API không cho curl gọi endpoint xóa tài nguyên không?

**Đáp án:** Không. CORS là browser-enforced read policy; authentication, authorization và CSRF khi phù hợp phải được thực thi riêng ở backend.

**Câu 9.** `maxAge(1800)` có nghĩa browser cache dữ liệu JSON API 30 phút không?

**Đáp án:** Không. Nó điều chỉnh thời gian cache preflight, không phải `Cache-Control` của actual JSON response.

**Câu 10.** Có thể sửa production CORS chỉ vì localhost test thông qua dev proxy không?

**Đáp án:** Không nên. Dev proxy có thể làm browser request cùng origin, che đi tình huống cross-origin production; phải test URL public cuối cùng với Origin thật và gateway/proxy.

### Bài tập mở rộng

Trong dự án MVC hoặc WebFlux ở mục 7/8, thêm `PUT /api/echo`, nhưng **chưa** đưa PUT vào `allowedMethods`. Gửi preflight OPTIONS với `Access-Control-Request-Method: PUT` và ghi kết quả. Sau đó thêm PUT vào allowlist rồi thử lại. Tiếp theo đổi frontend Origin thành `http://localhost:4173`, quan sát request bị từ chối cho đến khi allowlist được cập nhật. Cuối cùng thêm một response header `X-Server-Version` và thử browser `response.headers.get("X-Server-Version")` trước/sau khi bổ sung `exposedHeaders("X-Server-Version")`.

## 20. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — CORS for Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html)
- [Spring Framework 6.2 — CORS for Spring WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework — WebMvcConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework — WebFluxConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html)
- [Spring Security — Servlet CORS integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — Reactive CORS integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html)
- [Spring Boot — MVC customization](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — WebFlux customization](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [WHATWG Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol)

**Kết luận:** `WebMvcConfigurer.addCorsMappings` và `WebFluxConfigurer.addCorsMappings` là hai điểm cấu hình CORS **theo đúng web stack**. Một chính sách đúng phải khớp origin/method/header thực tế, kiểm soát credentials, xử lý preflight trước auth khi cần và nhất quán qua reverse proxy/CDN. CORS cho phép browser đọc response ở những origin được chỉ định; **nó không thay thế bảo mật API**.
