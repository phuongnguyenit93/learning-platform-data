# Chẩn đoán HTTP 404 do context path, servlet path, base path hoặc request mapping sai trong Spring Boot

## 1. Mục tiêu bài học

Một ứng dụng Spring Boot đã khởi động thành công, controller có `@GetMapping("/ping")` nhưng gọi `http://localhost:8080/ping` lại nhận **HTTP 404 Not Found**. Nguyên nhân không nhất thiết là thiếu controller: có thể HTTP request đang được gửi đến **sai context path**, **sai servlet path**, **sai WebFlux base path**, **sai mapping ở class/method**, bị reverse proxy chỉnh URL, hoặc ứng dụng đã tìm được handler nhưng chính handler quyết định trả 404.

Bài thuộc nhóm **Gỡ lỗi và nâng cấp**, module **Spring Boot - web-runtime**. Mục tiêu là biết *request path được phân tích theo những tầng nào*, xác định nơi phát sinh 404 bằng chứng cứ thay vì đoán, sửa đúng tầng và viết integration tests chống tái phát.

Sau bài học bạn có thể:

1. Phân biệt `server.servlet.context-path`, `spring.mvc.servlet.path`, `spring.webflux.base-path` và các mapping trong `@RequestMapping`/`@GetMapping`.
2. Tính URL thực tế cho Spring MVC/Servlet và WebFlux, tránh cộng/trừ prefix nhầm.
3. Phân biệt 404 do **Tomcat/container**, **DispatcherServlet/DispatcherHandler**, **static resource handler**, **controller/service chủ động** và **reverse proxy/gateway**.
4. Dùng `curl`, startup mapping logs, `/actuator/mappings`, request attributes và test qua **RANDOM_PORT** để truy nguyên.
5. Hiểu giới hạn của `PathPatternParser` với servlet path tùy chỉnh trên Spring Boot 3.5, sự thay đổi trailing slash, HTTP method/media types và static resource behavior.
6. Chạy hai dự án Java 17+ nhỏ: **MVC có context path** và **WebFlux có base path**, kèm HTTP integration tests thực tế.
7. Kiểm tra Actuator paths, management port, proxy rewrite/forwarded headers, security và cấu hình environment khi nâng cấp/deploy.

**Phương pháp cốt lõi:** hãy xác minh đường đi **client URL → proxy/gateway rewrite → server/context → servlet hoặc reactive base → handler mapping → handler thực thi**. Không thêm `/api` hoặc `/app` ngẫu nhiên vào mọi URL, không sửa controller trước khi biết request đã tới đúng ứng dụng hay chưa.

## 2. Phân biệt bốn loại prefix/path

### 2.1. Servlet context path: `server.servlet.context-path`

Đây là **context root của web application Servlet**, do servlet container như Tomcat quản lý. Ví dụ:

```properties
server.port=8080
server.servlet.context-path=/shop
```

Controller:

```java
@RestController
@RequestMapping("/api")
class PingController {
    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
```

Với `DispatcherServlet` mặc định tại `/`, đường dẫn client cần gọi:

```text
GET http://localhost:8080/shop/api/ping     -> route mong đợi
GET http://localhost:8080/api/ping          -> sai context path
```

Trong `@RequestMapping("/api")` **không cần** viết `/shop/api`. Context path là prefix của container, không phải phần route business mà controller phải lặp lại.

Một request bị gửi thiếu `/shop` có thể bị container trả 404 **trước khi DispatcherServlet xử lý**. Khi đó việc bật DEBUG handler mapping không thấy request là dấu hiệu hữu ích. Cũng kiểm tra có nhiều web applications cùng Tomcat hoặc proxy routing sai host/port không.

`server.servlet.context-path` là thuộc tính cho **Servlet web application**. Nó **không** phải tên khác của `spring.webflux.base-path` và không nên được dùng như cách cấu hình base path của một ứng dụng WebFlux chạy Reactor Netty.

### 2.2. DispatcherServlet path: `spring.mvc.servlet.path`

Đây là **đường đăng ký DispatcherServlet** trong Spring MVC, mặc định là `/`. Nó khác context root:

```properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/internal
```

Trong một cấu hình MVC tương thích với servlet prefix, controller `@RequestMapping("/api")` + `@GetMapping("/ping")` được truy cập qua:

```text
/shop + /internal + /api + /ping
= http://localhost:8080/shop/internal/api/ping
```

Tuy nhiên **giới hạn rất quan trọng của Spring Boot 3.5**: chiến lược `PathPatternParser` mặc định **không tương thích với cấu hình DispatcherServlet có path prefix tùy chỉnh**. Nếu thực sự cần `spring.mvc.servlet.path` trên dòng này, tài liệu Boot hướng dẫn chuyển sang matching strategy tương thích:

```properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
spring.mvc.servlet.path=/internal
```

`AntPathMatcher` là nhánh matching cũ, cần đánh giá implications về URI parsing, security và migration; không nên chuyển toàn hệ thống chỉ để che một lỗi proxy/config. Khi không có yêu cầu kỹ thuật đặc biệt về Servlet mapping, thường đơn giản hơn là giữ `spring.mvc.servlet.path=/` và dùng **context path** hoặc **application route prefix** đúng mục đích.

**Không mặc định rằng mọi Spring Boot version hỗ trợ phối hợp servlet path và parser giống nhau**: kiểm tra version, tài liệu API và integration tests trong bản nâng cấp của bạn. Với WebFlux native Netty, `spring.mvc.servlet.path` không phải prefix của reactive handlers.

### 2.3. WebFlux base path: `spring.webflux.base-path`

Ứng dụng **Spring WebFlux reactive** có property:

```properties
spring.webflux.base-path=/edge
```

Controller WebFlux:

```java
@RestController
@RequestMapping("/api")
class ReactiveController {
    @GetMapping("/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

URL từ phía client:

```text
GET http://localhost:8080/edge/api/ping     -> route mong đợi
GET http://localhost:8080/api/ping          -> thiếu WebFlux base path
```

`spring.webflux.base-path` là **base path cho các web handlers**. Trong một app reactive Netty thông thường, **không dùng `server.servlet.context-path` hay `spring.mvc.servlet.path` để thay nó**. Nếu có Servlet-based reactive deployment hoặc gateway riêng, cần xác minh thêm container/adapter thay vì áp dụng công thức Netty mù quáng.

Spring Boot mặc định có thể chọn **Spring MVC** nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng nằm trên classpath. Khi gặp 404 do base-path không có tác dụng, trước hết xác định ứng dụng thực đang chạy Servlet hay Reactive.

### 2.4. Handler mapping: `@RequestMapping`, `@GetMapping`, `@PostMapping`

Mapping của controller và method được kết hợp **sau** tầng context/servlet/base path:

```java
@RestController
@RequestMapping("/api/v1")
class OrderController {
    @GetMapping("/orders/{id}")
    Map<String, String> get(@PathVariable String id) {
        return Map.of("orderId", id);
    }
}
```

Mapping nội bộ là `GET /api/v1/orders/{id}`. Nếu MVC context path `/shop` thì URL bên ngoài là `/shop/api/v1/orders/123`; nếu WebFlux base path `/edge` thì là `/edge/api/v1/orders/123`. **Không trộn cả hai trường hợp thành một URL**.

Một `@RequestMapping("/api")` trên class + `@GetMapping("/ping")` trên method là `/api/ping`; URL `/ping` không được tự động map vì bạn đã đặt path ở class level.

`@GetMapping` giới hạn HTTP method. Nếu client gọi `POST` lên path chỉ hỗ trợ GET, thường nhận **405 Method Not Allowed**, không phải 404. Tương tự mismatch `consumes` thường dẫn tới 415, mismatch `produces/Accept` có thể dẫn tới 406. Nếu nhận 404, vẫn xem request có tới controller mapping hay đã bị một tầng khác chặn/trả khác.

## 3. Công thức xác định URL và bảng tình huống

### 3.1. Spring MVC Servlet với context và servlet path

Khi xử lý một endpoint thuộc Spring MVC và các tầng được cấu hình tương thích:

```text
URL path phía client
  = [servlet context path]
  + [DispatcherServlet mapping prefix, nếu custom]
  + [class-level @RequestMapping path]
  + [method-level @GetMapping/@PostMapping path]
```

Đây là **mô hình tư duy**, không phải phép nối strings trong source code: dấu `/` được chuẩn hóa theo routing config, paths có thể có URI variables, proxy rewriting, URL encoding hoặc patterns. Một servlet mapping không phải prefix mapping (ví dụ extension mapping) cũng không thể được giải thích bằng cộng chuỗi đơn giản.

| Trường hợp MVC | Context path | Servlet path | Controller + method | URL path dự kiến |
| --- | --- | --- | --- | --- |
| Default | root | `/` | `/api` + `/ping` | `/api/ping` |
| Context tùy chỉnh | `/shop` | `/` | `/api` + `/ping` | `/shop/api/ping` |
| Servlet prefix (với strategy tương thích) | root | `/internal` | `/api` + `/ping` | `/internal/api/ping` |
| Cả context + servlet prefix | `/shop` | `/internal` | `/api` + `/ping` | `/shop/internal/api/ping` |
| Route đã có version | `/shop` | `/` | `/api/v1` + `/ping` | `/shop/api/v1/ping` |

**Đừng “sửa” 404 bằng cách tự thêm `/shop` vào `@RequestMapping`** trong khi context path đã là `/shop`: có thể khiến URL thành `/shop/shop/api/ping` và tạo lỗi mới. Tránh hardcode public base URL trong controller/business logic; lấy từ deployment configuration/URI builder an toàn khi tạo link.

### 3.2. Spring WebFlux

```text
HTTP URL path = [spring.webflux.base-path] + [WebFlux handler mapping path]
```

| WebFlux base path | Controller + method | URL path |
| --- | --- | --- |
| Trống (mặc định) | `/api` + `/ping` | `/api/ping` |
| `/edge` | `/api` + `/ping` | `/edge/api/ping` |
| `/platform` | `/v1` + `/orders/{id}` | `/platform/v1/orders/42` |

Đối với functional `RouterFunction`, route được khai báo bằng predicates thay vì controller annotations; base path vẫn là phần routing config của WebFlux. Nếu functional route không được đăng ký hay không thuộc Spring context đang chạy, người dùng có thể thấy 404 dù annotated controllers khác hoạt động.

### 3.3. Phân biệt base path của Actuator

`management.endpoints.web.base-path` **không phải API base path**. Nó là prefix của Actuator web endpoints, mặc định `/actuator`.

Theo Spring Boot 3.5, khi Actuator **cùng port** với ứng dụng:

- Servlet MVC: Actuator base path tương đối với `server.servlet.context-path`.
- WebFlux: Actuator base path tương đối với `spring.webflux.base-path`.

Nếu Actuator chạy trên **port riêng** bằng `management.server.port`, base path của Actuator tương đối với `management.server.base-path` ở management server, **không cộng context path của main app theo cùng công thức**.

Ví dụ MVC:

```properties
server.port=8080
server.servlet.context-path=/shop
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,mappings
```

URL diagnostics trong demo local:

```text
http://localhost:8080/shop/actuator/health
http://localhost:8080/shop/actuator/mappings
```

Nếu tách management server:

```properties
management.server.port=9090
management.server.base-path=/ops
management.endpoints.web.base-path=/actuator
```

Khi cấu hình này áp dụng và endpoints được phép expose, diagnostics dự kiến ở **management server**:

```text
http://localhost:9090/ops/actuator/health
http://localhost:9090/ops/actuator/mappings
```

Vì security/access/exposure có thể chặn, 404 ở `/actuator/mappings` không tự chứng minh route kinh doanh bị thiếu. **Đừng công khai `mappings`/`env`/`configprops` ra Internet**; chúng có thể tiết lộ cấu trúc API và cấu hình. Trong ví dụ bên dưới chỉ bind localhost và dùng môi trường học.

## 4. Một 404 có thể đến từ nhiều tầng

```text
Client: GET /shop/api/ping
         |
         v
Gateway / load balancer / ingress
  - sai hostname, path rewrite, upstream, prefix? -> 404 từ gateway
         |
         v
Tomcat Servlet context /shop
  - thiếu /shop, context khác?              -> 404 từ container
         |
         v
DispatcherServlet mapping /
  - có /internal prefix?                   -> 404 hoặc không tới servlet
         |
         v
Spring RequestMappingHandlerMapping
  - route /api/ping có đăng ký?             -> không có handler
         |
         v
Static resource handler /** (nếu được bật)
  - tìm resource, không có?                 -> NoResourceFoundException -> 404
         |
         v
Controller / service
  - record id không tồn tại?                -> chủ động trả 404
```

Trên WebFlux/Netty, thay tầng Servlet context/DispatcherServlet bằng **WebFlux base path + DispatcherHandler/HandlerMappings**, còn những nguyên tắc về gateway, handlers và app-level 404 vẫn tương tự.

Một số khác biệt dễ nhầm:

1. **404 từ proxy**: request có thể **chưa tới Java process**. Ứng dụng không có trace/access log tương ứng, response headers/body do gateway tạo (không phải bằng chứng tuyệt đối vì headers có thể bị chỉnh).
2. **404 từ Tomcat context**: port đúng nhưng request nằm ngoài context path; Spring MVC filters và handler mappings của app có thể không thấy request.
3. **404 từ WebFlux base path**: Netty nhận request nhưng WebFlux handlers không khớp route tương ứng do path prefix sai.
4. **404 không tìm thấy controller handler**: annotation bị sai, component không được scan, package root không đúng hoặc route mismatch.
5. **404 static resource**: Spring MVC/WebFlux static resource handler có thể nhận path theo pattern `/**`, rồi trả 404 vì không có file; message khác “No handler found”.
6. **404 có chủ đích**: controller ném `ResponseStatusException(HttpStatus.NOT_FOUND)` hoặc `@ExceptionHandler` map domain not-found thành 404. Mapping có tồn tại và đã chạy.

**HTTP status 404 không phải bằng chứng rằng ứng dụng “không khởi động”.** Nếu health có status 200 ở URL đúng, app đang chạy; cần tiếp tục phân vùng nguyên nhân. Ngược lại health 200 từ một **instance khác** hoặc **management port khác** không chứng minh request đã tới cùng backend.

## 5. Quy trình chẩn đoán 404 theo thứ tự ít tốn công nhất

### Bước 1 — chốt request đang được gửi thật

Ghi lại:

- Scheme (http/https), hostname, port, method, URL path, query, `Host`, `Accept`, `Content-Type`.
- Response status, headers, body, thời điểm, request ID/correlation ID nếu có.
- Có redirect 301/302/307/308 trước 404 không? Có rewrite/forward qua CDN, ingress, service mesh không?
- Client là browser, mobile app, curl hay reverse proxy health checker? Có giữ base URL cũ sau deploy không?

Đầu tiên thử từ **máy có quyền truy cập backend** (localhost/staging):

```bash
curl -i -v --max-time 5 "http://127.0.0.1:8080/shop/api/ping"
curl -i -v --max-time 5 "http://127.0.0.1:8080/api/ping"
```

Không dùng `-L` tự động follow redirect khi đang xác định chain 404; redirect có thể chuyển sang đường dẫn/host khác và che nguyên nhân. Dùng `curl --path-as-is` trong phép thử path đặc biệt có kiểm soát nếu cần kiểm tra normalization; **không test URL traversal trên hệ thống không được phép**.

### Bước 2 — xác định Servlet MVC hay WebFlux

Xem dependency list / server startup log của **đúng artifact**:

- Có `spring-boot-starter-web`, `DispatcherServlet`, Tomcat/Jetty/Undertow servlet? → thường là **Spring MVC**.
- Có `spring-boot-starter-webflux`, Reactor Netty, reactive `DispatcherHandler`? → thường là **WebFlux**.
- Cả hai starters cùng có? Spring Boot thường **ưu tiên MVC**; đừng đoán reactive từ controller trả `Mono`.
- App đứng sau Spring Cloud Gateway/nginx? Xem route config ở gateway trước khi đổi app properties.

Nếu thật sự là MVC, tập trung `server.servlet.context-path` + `spring.mvc.servlet.path` + controller mappings. Nếu thật sự là WebFlux, tập trung `spring.webflux.base-path` + WebFlux handlers.

### Bước 3 — xác minh cấu hình đang có hiệu lực

Kiểm tra từ deployment config, profile đang active, command-line arguments, environment variables và startup messages:

```properties
server.port=8080
server.servlet.context-path=/shop
spring.mvc.servlet.path=/
# Dùng cho WebFlux app riêng; đừng trộn mọi property vào cùng một app:
# spring.webflux.base-path=/edge
```

Tương ứng các biến môi trường mà Spring Boot relaxed binding có thể nhận:

```text
SERVER_PORT
SERVER_SERVLET_CONTEXT_PATH
SPRING_MVC_SERVLET_PATH
SPRING_WEBFLUX_BASE_PATH
SPRING_PROFILES_ACTIVE
```

Chỉ vì file `src/main/resources/application.properties` chứa `/shop` **không bảo đảm** runtime vẫn dùng giá trị đó: profile `application-prod.yml`, environment, command-line args, ConfigMap/Helm, remote config, test properties, container flags hoặc config import có thể override.

Không đưa tất cả environment variables vào production logs, vì nhiều biến chứa passwords/tokens. Nếu dùng Actuator `env`/`configprops` trong môi trường được quản lý, chỉ cấp quyền nội bộ và giữ nguyên sanitization, không public endpoints.

### Bước 4 — xác minh controller thật sự đăng ký mapping

Kiểm tra class có:

- `@RestController` hoặc `@Controller` đúng kiểu.
- Trong package được `@SpringBootApplication` component scan, hoặc được import/scan có chủ đích.
- Class-level `@RequestMapping` và method-level `@GetMapping` hợp lại thành path nào?
- Chỉ chạy trong profile/conditional bean nào?
- Có server version/instance chưa deploy controller mới không?
- Request method, headers/params, `consumes`/`produces` có match không?

Ví dụ:

```java
@RestController
@RequestMapping("/api/v1")
class OrderController {
    @GetMapping("/orders/{id}")
    public Map<String, String> get(@PathVariable("id") String id) {
        return Map.of("orderId", id);
    }
}
```

Đường dẫn mapping là `GET /api/v1/orders/{id}`, không phải `/orders/{id}` hoặc `/api/orders/{id}`. Nếu context path `/shop`, URL phải là `/shop/api/v1/orders/42`.

Một `@Controller` thiếu `@ResponseBody` cũng có thể được nhìn như **view resolver** thay vì JSON body, gây view-not-found hoặc các lỗi khác. Khi thiết kế REST API, dùng `@RestController` cho rõ.

### Bước 5 — dùng Actuator mappings khi an toàn

Trong **môi trường local hoặc nội bộ có quyền**, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

và cấu hình local:

```properties
management.endpoints.web.exposure.include=health,mappings
```

Sau đó, gọi URL Actuator **đã cộng đúng context/base path/management port**, ví dụ:

```bash
curl -i "http://127.0.0.1:8080/shop/actuator/health"
curl -i "http://127.0.0.1:8080/shop/actuator/mappings"
```

`/actuator/mappings` cung cấp danh sách registered request mappings; có thể xem controller handler và route pattern. **Pattern được báo trong mapping metadata không nhất thiết chứa cả servlet context path**: hiểu nó như thông tin handler nội bộ, sau đó kết hợp với cấu hình container/gateway để tìm URL public.

Không coi Actuator 404 ngay lập tức là app thiếu route: endpoint `mappings` có thể chưa được expose, bị chặn bảo mật hoặc đang ở management port/path khác. Với app có Spring Security, chỉ expose thông tin mapping cho người vận hành được xác thực và có quyền.

### Bước 6 — log một request có kiểm soát

Có thể bật logging về handler mappings trong **local/test profile**, không phải DEBUG toàn framework trên production:

```properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.reactive.result.method.annotation.RequestMappingHandlerMapping=TRACE
```

Đây là hai logger cho hai stack khác nhau; chỉ bật logger của stack đang chạy. Startup logs có thể cho biết paths đã đăng ký. Tên logger và nội dung log thay đổi theo Spring Framework version; xác minh thực thay vì phụ thuộc một dòng message cố định.

Nếu request đi vào Spring MVC, có thể quan sát attributes ở `HttpServletRequest`. Ví dụ filter/local endpoint có thể xem:

```java
String uri = request.getRequestURI();
String context = request.getContextPath();
String servlet = request.getServletPath();
String extra = request.getPathInfo();
```

Đây là **snippet**, cần `jakarta.servlet.http.HttpServletRequest`. Các giá trị có semantics tùy servlet mapping; `getRequestURI()` là URI path phía server nhận, không bao gồm query string, còn `getContextPath()` và `getServletPath()` giúp xác định phần prefix. Đừng log raw query/cookie/Authorization hoặc user identifiers để debug prefix.

Trong reactive WebFlux, xem request path qua `ServerHttpRequest.getURI().getRawPath()` hoặc `ServerHttpRequest.getPath()` trong một WebFilter test-only. **Không thêm filters log mọi request body hay PII** chỉ để tìm lỗi 404.

### Bước 7 — so trực tiếp backend và đường qua proxy

Thử cùng request qua hai đường, trong phạm vi được phép:

```text
Backend trực tiếp: GET http://127.0.0.1:8080/shop/api/ping
Public gateway:   GET https://app.example.test/portal/shop/api/ping
```

Nếu backend trực tiếp 200 nhưng gateway 404, điều tra **gateway rule, host match, path strip/rewrite, ingress service name/port, target instance** trước khi sửa `@GetMapping`. Nếu backend trực tiếp đã 404, tiếp tục kiểm context path/mappings của app.

Không suy "gateway tạo 404" chỉ từ một Server header: proxy có thể thay headers, còn app có thể trả custom error page. Ghép ingress access logs, application access logs, request ID và timing để kết luận.

## 6. Lưu ý về PathPatternParser, trailing slash và static resources

### 6.1. Servlet path custom có ràng buộc parser

Trong Spring Boot 3.5, tài liệu Web MVC nói rõ matching strategy `PathPatternParser` không tương thích việc cấu hình DispatcherServlet có **path prefix** qua `spring.mvc.servlet.path`. Ví dụ khi cần legacy servlet path:

```properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/internal
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
```

Lúc đó URL thử là `/shop/internal/api/ping`, còn `/shop/api/ping` thiếu servlet prefix. Trước khi đổi parser, kiểm tra các patterns hiện có (wildcards, encoded slashes, matrix vars), routing security và integration tests; việc chuyển từ PathPatternParser sang AntPathMatcher **không chỉ là cấu hình cosmetic**.

Nếu app chỉ cần hiển thị API dưới `/internal` ở gateway, có thể thay thế bằng **route prefix trong @RequestMapping**, context path, hoặc proxy rewrite có thiết kế, tránh đổi matching strategy khi không bắt buộc.

### 6.2. Trailing slash không mặc nhiên tương đương

```text
GET /shop/api/ping
GET /shop/api/ping/
```

Trên Spring Framework 6.x/Boot 3.x, không nên mặc định hai path match nhau. Các phiên bản mới đã thay đổi/giảm hỗ trợ transparent trailing-slash matching vì nguy cơ sai khác authorization. Nếu client gửi `/ping/` còn controller khai báo `@GetMapping("/ping")`, có thể nhận 404. Hãy **chọn một URL canonical** và xử lý redirects/normalization nhất quán tại edge/web filter hoặc khai báo mapping minh bạch khi có nhu cầu thật.

Đừng bật rewrite tùy ý có thể làm bypass role-based security: route security matcher và controller route phải áp dụng cùng semantics. Đặc biệt phân biệt `/admin` và `/admin/` trong security tests.

### 6.3. Static resource handler có thể giữ 404 dù không có controller handler

Spring Boot MVC mặc định phục vụ static resources từ các classpath locations như:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

với `spring.mvc.static-path-pattern=/**`. Vì vậy một URL **không khớp controller** có thể bị generic static resource handler nhận để tìm file. Nếu không thấy file, nó tạo `NoResourceFoundException` (Spring Framework 6.1+), HTTP status vẫn là 404.

Điều đó giải thích vì sao chỉ tìm `NoHandlerFoundException` trong logs có thể bỏ sót 404. Boot docs nêu: để bắt `NoHandlerFoundException`, cần giảm static path mapping, ví dụ:

```properties
spring.mvc.static-path-pattern=/assets/**
```

hoặc tắt static resource mapping khi thực sự không phục vụ assets:

```properties
spring.web.resources.add-mappings=false
```

**Đừng thay cấu hình static resources production chỉ để làm test 404 dễ đọc hơn**: UI/assets có thể hỏng. Trong chẩn đoán, đủ để phân biệt thiếu handler với thiếu resource qua logs, mappings và test. Nếu đang chạy WebFlux, dùng `spring.webflux.static-path-pattern` theo tài liệu stack reactive thay vì `spring.mvc.static-path-pattern`.

### 6.4. Sai method, media type và path không phải một lỗi

- `GET` mapping nhận `POST`: thường 405 (không hỗ trợ method).
- `@PostMapping(consumes="application/json")` nhận `text/plain`: thường 415.
- Mapping `produces` không match `Accept`: thường 406.
- Sai `params` hoặc `headers` condition: HTTP status phụ thuộc matching và exception resolution; kiểm log/mappings thay vì gọi chung 404.
- Sai URI variable regex (ví dụ chỉ chấp nhận chữ số): path không match → 404.
- Dấu hoa/thường, percent-encoding, duplicate slashes và path normalization qua proxy có thể tạo route khác.
- Controller được tìm thấy nhưng service ném `ResponseStatusException(404)` hoặc `@ControllerAdvice` chuyển lỗi thành 404: đó là **application-level not found**, không phải mapping missing.

## 7. Dự án thực hành MVC — context path gây 404

Dự án đầu tiên chạy **Spring Boot 3.5.16 + Java 17+ + Spring MVC + embedded Tomcat**. Nó có:

- `server.servlet.context-path=/shop`.
- `@RequestMapping("/api")` + `@GetMapping("/ping")` tạo endpoint nội bộ `/api/ping`.
- Client phải gọi `/shop/api/ping`.
- Một endpoint `/api/orders/{id}` để minh họa path variables.
- Actuator health/mappings chỉ phục vụ debug local.
- **Sáu HTTP integration tests** sử dụng `java.net.http.HttpClient` qua embedded server `RANDOM_PORT`, kiểm cả 200/404/405/actuator path.

### 7.1. Cấu trúc thư mục

```text
mvc-path-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingApplication.java
    │   │   └── PingController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/routing/
            └── PrefixRoutingIntegrationTest.java
```

### 7.2. `pom.xml` hợp lệ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-path-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

`spring-boot-starter-web` đem Spring MVC/Tomcat; `spring-boot-starter-actuator` cung cấp `/actuator/health` và `/actuator/mappings` khi exposure phù hợp; `spring-boot-starter-test` mang JUnit Jupiter. Không cần database hay công cụ bên ngoài.

### 7.3. Main class

**`src/main/java/com/example/routing/RoutingApplication.java`**

```java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
```

### 7.4. Controller: một route nội bộ, một URL public có prefix

**`src/main/java/com/example/routing/PingController.java`**

```java
package com.example.routing;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PingController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping("/orders/{id}")
    public Map<String, String> order(
            @PathVariable("id") String id) {
        return Map.of("orderId", id);
    }
}
```

**Không** đưa `/shop` vào annotation; context path thuộc Servlet container. Controller phải ở dưới package gốc `com.example.routing` để `@SpringBootApplication` scan ra.

### 7.5. Cấu hình localhost để chẩn đoán an toàn

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.address=127.0.0.1

server.servlet.context-path=/shop
# Mặc định DispatcherServlet /; ghi rõ để dạy về hai prefix khác nhau.
spring.mvc.servlet.path=/

# Chỉ dùng với localhost/lab; không expose mappings ra Internet.
management.endpoints.web.exposure.include=health,mappings
```

`server.address=127.0.0.1` giữ server tại loopback trong môi trường học. Khi ứng dụng chạy thật trong container hoặc sau reverse proxy, cần cấu hình listen address cho topology tương ứng thay vì sao chép một cách máy móc. `mappings` endpoint có thể tiết lộ danh sách routes và nên được bảo vệ/bật theo environment profile.

### 7.6. Tự gửi HTTP để tái hiện 404

Chạy trong thư mục dự án MVC:

```bash
java -version
mvn spring-boot:run
```

Trên terminal khác:

```bash
curl -i "http://127.0.0.1:8080/shop/api/ping"
curl -i "http://127.0.0.1:8080/api/ping"
curl -i "http://127.0.0.1:8080/shop/api/orders/A-7"
curl -i "http://127.0.0.1:8080/shop/actuator/health"
curl -i "http://127.0.0.1:8080/shop/actuator/mappings"
```

Kỳ vọng:

- `GET /shop/api/ping` → 200, JSON có `{"message":"pong"}`.
- `GET /api/ping` → 404 do thiếu `/shop`.
- `GET /shop/api/orders/A-7` → 200, JSON có `{"orderId":"A-7"}`.
- `GET /shop/actuator/health` → 200, JSON health khi có exposure.
- `GET /shop/actuator/mappings` → 200 và metadata mappings trong **local lab**.
- `GET /actuator/health` → 404 do thiếu context prefix.

Thời gian HTTP, headers `Date/Connection` và hình dạng body error 404 có thể khác giữa Tomcat/ErrorController/config. Không assert JSON schema cố định cho container-generated 404.

### 7.7. Sáu HTTP integration tests qua socket thật

**`src/test/java/com/example/routing/PrefixRoutingIntegrationTest.java`**

```java
package com.example.routing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class PrefixRoutingIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path)
            ).GET().build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    private HttpResponse<String> post(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path)
            ).POST(HttpRequest.BodyPublishers.noBody()).build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void routeWithContextPrefixReturns200() throws Exception {
        HttpResponse<String> response = get("/shop/api/ping");

        assertEquals(200, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertEquals("pong", body.get("message").asText());
    }

    @Test
    void missingContextPrefixReturns404() throws Exception {
        assertEquals(404, get("/api/ping").statusCode());
    }

    @Test
    void wrongRouteReturns404() throws Exception {
        assertEquals(404,
            get("/shop/api/does-not-exist").statusCode());
    }

    @Test
    void classAndMethodMappingsAreCombined() throws Exception {
        HttpResponse<String> response =
            get("/shop/api/orders/A-7");

        assertEquals(200, response.statusCode());
        assertEquals("A-7",
            mapper.readTree(response.body())
                .get("orderId").asText());
    }

    @Test
    void unsupportedHttpMethodReturns405() throws Exception {
        assertEquals(405,
            post("/shop/api/ping").statusCode());
    }

    @Test
    void actuatorPathAlsoUsesContextPrefix() throws Exception {
        HttpResponse<String> response =
            get("/shop/actuator/health");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("UP"));
    }
}
```

Chạy:

```bash
mvn test
```

**Sáu tests được thiết kế để pass**, nhưng kết quả là kỳ vọng khi người học chạy, **không phải tuyên bố đã thực thi Maven trong workspace hiện tại**. Khác với `MockMvc`, `RANDOM_PORT` khởi động embedded server thật và `HttpClient` gọi qua TCP loopback, nên có thể phát hiện lỗi context root/servlet registration mà unit/slice tests bỏ sót.

Test thứ hai cố ý yêu cầu URL **sai context path** trả 404; đây là test negative hữu ích để xác nhận prefix thay vì chỉ kiểm “route đúng 200”. Test 405 cho thấy method mismatch không đồng nghĩa 404.

### 7.8. Kiểm tra servlet prefix trên chính ứng dụng MVC

Khi đã chạy baseline, để minh họa `spring.mvc.servlet.path` một cách **có chủ đích**, dùng application properties ở profile thử nghiệm hoặc CLI args:

```properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/internal
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
```

Sau khi khởi động lại với config này, đường dẫn controller dự kiến là:

```text
http://127.0.0.1:8080/shop/internal/api/ping
```

Đây là **một biến thể cấu hình riêng**, không giữ đồng thời với bài integration tests baseline rồi mong chúng vẫn pass: các tests baseline đang xác nhận `/shop/api/ping`. Khi thay servlet prefix, cần cập nhật test URL thành `/shop/internal/api/ping` và thêm negative case `/shop/api/ping` để chống cấu hình sai.

Không dùng `PathPatternParser` mặc định cùng prefix tùy chỉnh rồi gán mọi lỗi startup cho “404 do controller”. Trong Spring Boot 3.5 đây là vấn đề **compatibility/configuration** có thể xuất hiện khi khởi tạo mapping, cần sửa cấu hình trước khi kiểm HTTP.

## 8. Dự án thực hành WebFlux — base path gây 404

Dự án thứ hai **độc lập hoàn toàn** với dự án MVC, minh họa `spring.webflux.base-path=/edge` trong Spring WebFlux + Reactor Netty. Không chạy cả hai app trên cùng port 8080 đồng thời.

### 8.1. Cây file

```text
reactive-basepath-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/reactivepath/
    │   │   ├── ReactiveBasePathApplication.java
    │   │   └── ReactivePingController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivepath/
            └── ReactiveBasePathIntegrationTest.java
```

### 8.2. POM WebFlux

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-basepath-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Chỉ có WebFlux starter, không có MVC starter. Spring Boot chọn reactive web application và khởi động Reactor Netty (mặc định) khi chạy như web service.

### 8.3. WebFlux properties

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.address=127.0.0.1
spring.main.web-application-type=reactive
spring.webflux.base-path=/edge
```

Lưu ý: không đặt `server.servlet.context-path=/edge` để mong cấu hình này có hiệu lực trên Netty; đó là Servlet-only property.

### 8.4. Reactive main class

**`src/main/java/com/example/reactivepath/ReactiveBasePathApplication.java`**

```java
package com.example.reactivepath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveBasePathApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveBasePathApplication.class, args);
    }
}
```

### 8.5. Reactive controller

**`src/main/java/com/example/reactivepath/ReactivePingController.java`**

```java
package com.example.reactivepath;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ReactivePingController {

    @GetMapping("/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("message", "pong"));
    }
}
```

Như MVC, mapping nội bộ vẫn là `GET /api/ping`, nhưng URL public đi qua base path `/edge`.

### 8.6. Ba integration tests WebFlux HTTP thật

**`src/test/java/com/example/reactivepath/ReactiveBasePathIntegrationTest.java`**

```java
package com.example.reactivepath;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ReactiveBasePathIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path)
            ).GET().build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void basePathAndMappingTogetherReturn200() throws Exception {
        HttpResponse<String> response =
            get("/edge/api/ping");

        assertEquals(200, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertEquals("pong", body.get("message").asText());
    }

    @Test
    void missingReactiveBasePathReturns404() throws Exception {
        assertEquals(404, get("/api/ping").statusCode());
    }

    @Test
    void duplicatedReactiveBasePathReturns404() throws Exception {
        assertEquals(404,
            get("/edge/edge/api/ping").statusCode());
    }
}
```

Chạy trong thư mục reactive project:

```bash
mvn test
mvn spring-boot:run
```

Khi app đang chạy, thử:

```bash
curl -i "http://127.0.0.1:8080/edge/api/ping"
curl -i "http://127.0.0.1:8080/api/ping"
curl -i "http://127.0.0.1:8080/edge/edge/api/ping"
```

Kỳ vọng: 200, 404, 404 theo thứ tự. **Ba tests được kỳ vọng pass khi chạy đúng source**; không giả định đã chạy trong workspace của người đọc. Đây là một **HTTP integration**, khác `WebTestClient.bindToController` hoặc `@WebFluxTest` vốn chạy mock exchange.

### 8.7. Nếu thêm Actuator vào reactive project

Khi thêm starter actuator và expose `health,mappings` (chỉ local), cùng port và `spring.webflux.base-path=/edge`, Actuator endpoint thường nằm dưới:

```text
/edge/actuator/health
/edge/actuator/mappings
```

Nếu chuyển `management.server.port` sang port khác, prefix phụ thuộc `management.server.base-path` trên management server, không còn đơn giản lấy WebFlux base path của main server cộng thêm Actuator path.

## 9. Reverse proxy/Ingress: nguyên nhân 404 rất thường gặp

Giả sử app MVC thực sự nhận:

```text
GET http://127.0.0.1:8080/shop/api/ping
```

Nhưng khách hàng nhìn thấy URL:

```text
GET https://service.example.test/portal/shop/api/ping
```

Một reverse proxy có thể **strip `/portal`** rồi gửi upstream `/shop/api/ping`, hoặc **giữ nguyên `/portal`** khiến upstream nhận `/portal/shop/api/ping` và Tomcat không match context `/shop`.

Ví dụ Nginx mô tả tình huống strip prefix (đặt trong một server block hoàn chỉnh tại môi trường được phép):

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

Với `proxy_pass` có URI `/` ở cuối như trên và `location /portal/` đơn giản, Nginx sẽ thay prefix location tương ứng bằng `/`; external `/portal/shop/api/ping` thành upstream `/shop/api/ping`. Nếu thay `proxy_pass` thành dạng **không có URI**:

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080;
}
```

trong trường hợp proxy không có rewrite khác, Nginx thường chuyển request URI theo nguyên trạng. **Các quy tắc còn phụ thuộc regex location/rewrite/normalization và config thực**; xác nhận bằng upstream access log thay vì coi hai snippets này là công thức cho mọi Nginx deployment.

Đối với Kubernetes Ingress, gateway hoặc service mesh:

- Kiểm path match type (Exact/Prefix/ImplementationSpecific), service name, namespace và service port.
- Có strip/rewrite path không? Rewrite target có làm mất `/shop` hay lặp `/api` không?
- Có host-based virtual routing khiến request vào backend khác khi `Host` thay đổi không?
- Đã apply manifests/Helm release mới chưa? Pod có version controller/mappings mới không?
- Healthcheck của gateway đang gọi `/health`, `/actuator/health` hay `/shop/actuator/health`? Port management có riêng không?

**`X-Forwarded-Prefix` không phải lệnh bắt buộc reverse proxy sẽ sửa actual request path**. Forwarded headers thường liên quan tới reconstruct public URL, scheme/host/prefix và link generation. Nếu dùng `server.forward-headers-strategy=framework` hoặc native forwarded-header processing, hãy xác định rõ edge có strip/rewrite request path thật không. Không cộng `X-Forwarded-Prefix` thêm lần nữa khi proxy đã rewrite hoặc app đã có context path.

**Bảo mật:** chỉ tin `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Prefix` từ **trusted proxy**; nếu client tự gửi được các header ấy, sai cấu hình có thể ảnh hưởng redirects, absolute links và authorization decisions. Ở edge nên xóa/ghi đè forwarded headers do client tự đặt.

## 10. 404 sau nâng cấp Spring Boot/Spring Framework

Những thay đổi đáng kiểm tra sau khi từ version cũ lên Boot 3.x/Framework 6.x:

1. **Jakarta namespaces:** javax.servlet → jakarta.servlet trong code filters/servlets; một custom filter không được port đúng có thể không đăng ký, ảnh hưởng rewrite/dispatch.
2. **PathPatternParser mặc định:** Spring MVC dùng parsed patterns, không tương thích một số custom servlet path configurations; strategy `ant-path-matcher` là lựa chọn legacy khi có yêu cầu.
3. **Trailing slash:** `/api/ping` và `/api/ping/` không nên mặc nhiên tương đương; tests cần yêu cầu chính xác.
4. **Static resource 404:** khi static mapping `/**` bắt request, có thể thấy `NoResourceFoundException` thay vì `NoHandlerFoundException`.
5. **Controller package scan:** đổi package main class, module jars hoặc component scan có thể khiến controller không được đăng ký.
6. **Security behavior:** 401/403/404 giả tùy authorization matchers, security config; không vô hiệu hóa security để “sửa” routing.
7. **Reverse proxy / Kubernetes ingress:** thay đổi rewrite flags, service port, hostname, path prefix trong deployment charts.
8. **Actuator management path:** separate management port hoặc `management.endpoints.web.base-path` làm URL diagnostics thay đổi.
9. **Spring Boot MVC vs WebFlux detection:** thêm starter hoặc chuyển server stack có thể khiến `spring.webflux.base-path` không còn là property đang áp dụng.
10. **Mapping regex/case/encoded path:** các chiến lược path parsing khác có thể thay đổi matching; test cả URL được hỗ trợ và URL đáng bị từ chối.

**Không sửa mọi 404 bằng cách hạ version hoặc tắt PathPatternParser.** Trước khi đổi behavior rộng, viết một integration test tái hiện đúng URL/scheme/method/Host và so sánh test trên hai versions với cùng settings.

## 11. Kiểm thử để ngăn 404 trở lại

### 11.1. Vì sao unit test controller chưa đủ?

Một unit test:

```java
assertEquals(
    Map.of("message", "pong"),
    new PingController().ping()
);
```

chỉ chứng minh method Java trả đúng Map; **không** chứng minh Spring có scan controller, mở context `/shop` hoặc request tới URL `/shop/api/ping` được route. Ngay cả `@WebMvcTest`/`MockMvc` tốt để test mappings cũng không hoàn toàn thay thế **embedded Tomcat + random port HTTP** khi vấn đề là actual context path/servlet registration.

### 11.2. Test nên có cả positive và negative path

Các test đáng giữ:

- `GET /shop/api/ping` → 200.
- `GET /api/ping` → 404 (bỏ context).
- `GET /shop/api/does-not-exist` → 404 (không có business route).
- `POST /shop/api/ping` → 405, phân biệt wrong method với mapping 404.
- `GET /shop/api/orders/A-7` → 200, xác minh class/method path combination.
- `GET /shop/actuator/health` → 200 khi health được expose và same port.
- Nếu dùng servlet prefix: positive `/shop/internal/api/ping`, negative `/shop/api/ping` với matching strategy phù hợp.
- Nếu dùng WebFlux base path: positive `/edge/api/ping`, negative `/api/ping` và duplicated-prefix `/edge/edge/api/ping`.
- Nếu có proxy: một HTTP integration test qua ingress/staging với hostname và rewrite rule production-like.

### 11.3. Đừng hardcode error body hoặc HTTP port

404 từ container, BasicErrorController, reactive error handler hoặc gateway có thể trả JSON/HTML khác nhau. Trong test đường dẫn sai, **assert status 404**, không nhất thiết assert body raw. Với server `RANDOM_PORT`, inject `@LocalServerPort` và tạo URL runtime, tránh port 8080 xung đột với ứng dụng khác trên CI.

Nếu yêu cầu có một error JSON schema chuẩn, đó là một **API contract riêng**: triển khai `@ControllerAdvice`/`@RestControllerAdvice` hoặc `ProblemDetail` có chủ đích rồi test schema cho những lỗi thuộc phạm vi ứng dụng. Không ép Tomcat-generated 404 bên ngoài context phải giống controller-generated 404.

### 11.4. Không lấy Actuator mappings làm HTTP E2E

`/actuator/mappings` chứng minh các handler được **đăng ký trong application context** theo metadata mà endpoint biết. Nó **không chứng minh** proxy public đang route đúng, container path đã được trừ đúng, security đã cho phép và client nhận HTTP 200. Kết hợp **mappings + startup logs + curl backend trực tiếp + curl public gateway + HTTP integration tests** để biết đường dẫn hỏng ở đâu.

## 12. Bảng chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Giả thuyết hợp lý | Kiểm tra và sửa |
| --- | --- | --- |
| `/api/ping` 404, `/shop/api/ping` 200 | Sai Servlet context path | Xác minh `server.servlet.context-path`, sửa client base URL |
| `/shop/api/ping` 404, `/shop/internal/api/ping` 200 | Có DispatcherServlet prefix | Xác minh `spring.mvc.servlet.path` và matching strategy |
| App crash/không lên khi set servlet path | PathPatternParser không tương thích | Review Boot version, đổi strategy hoặc bỏ servlet prefix |
| WebFlux `/api/ping` 404, `/edge/api/ping` 200 | Bỏ reactive base path | Kiểm `spring.webflux.base-path` và actual stack |
| `/shop/shop/api/ping` hoạt động, URL thường 404 | Prefix bị lặp ở controller/proxy | Bỏ một tầng lặp, định nghĩa canonical path |
| Backend direct 200, public gateway 404 | Proxy rewrite/Host/port sai | So request path upstream thực; đối chiếu ingress rules |
| `/shop/actuator/health` 404, app route vẫn 200 | Actuator không expose, management port/path khác | Kiểm actuator dependencies, exposure, management URL |
| `@GetMapping` thấy trong source, không có trong mappings | Controller chưa scan, profile/condition/version sai | Kiểm package root, jar, active profiles, startup logs |
| Path gần đúng, POST trả 405 | HTTP method mismatch | Dùng đúng verb, không gọi là 404 |
| POST trả 415 | Content-Type/consumes mismatch | Gửi đúng body media type |
| GET trả 406 | Accept/produces mismatch | Kiểm content negotiation |
| `/api/ping` 200, `/api/ping/` 404 | Trailing slash behavior | Canonicalize/redirect an toàn, test cả hai |
| Logs nhắc NoResourceFoundException | Static mapping `/**` bắt URL | Kiểm controller mapping, static resources, pattern |
| Không có app access log cho request lỗi | Gateway/container có thể trả trước handler | So ingress log, container log, correlation ID |
| `/items/unknown` trả 404 dù mapping đúng | Domain record không tồn tại | Kiểm service/database/error advice, không sửa prefix |
| Response khi sai Host trả 404 nhưng đúng Host trả 200 | Virtual host/ingress host match | Kiểm DNS, `Host`, gateway config |
| Sau deploy chỉ một số pods 404 | Version/config không đồng nhất | Kiểm image tag, release rollout, service endpoints |
| 404 chỉ trên URL đã percent-encode | Decode/normalization/URI variable pattern khác | Kiểm raw path, parser, proxy/security behavior |
| Khởi động báo Mapping ambiguous | Duplicate mappings | Sửa annotations, không giấu lỗi bằng URL rewrite |

## 13. Checklist dành cho người gỡ lỗi

- [ ] Ghi chính xác URL, HTTP method, headers, Host, response status và thời điểm xảy ra lỗi.
- [ ] Tách rõ **client URL** với **backend URL** sau proxy rewrite.
- [ ] Xác minh app là Spring MVC hay WebFlux, server implementation và artifact/version.
- [ ] Đọc **runtime effective config** của context path, servlet path, reactive base path, port/profiles.
- [ ] Hiểu URL theo thứ tự prefix phù hợp và không lặp prefix trong `@RequestMapping`.
- [ ] Nếu dùng `spring.mvc.servlet.path` custom trong Boot 3.5, xem vấn đề PathPatternParser compatibility.
- [ ] Kiểm class/method annotations, package scan, active profiles và conditional beans.
- [ ] Thử cả positive và negative URL với `curl -i -v` không tự follow redirect.
- [ ] Kiểm security/access log, mapping startup logs và container logs trong môi trường nội bộ.
- [ ] Dùng `/actuator/mappings` đúng URL và có quyền; không public endpoint này.
- [ ] Phân biệt gateway/container/mapping/static-resource/business 404.
- [ ] Biết wrong method/media type thường gây 405/406/415 chứ không phải 404.
- [ ] Kiểm trailing slash, case, percent-encoding và resource handler `/**`.
- [ ] Kiểm Actuator management port/base path riêng khi endpoint debug không có.
- [ ] Có integration test `RANDOM_PORT` qua HTTP thật cho đường dẫn đã sửa.
- [ ] Test proxy ở môi trường được phép khi lỗi chỉ xuất hiện qua ingress.
- [ ] Không vô hiệu hóa security, không log credentials/PII, không nhận forwarded headers từ nguồn không tin cậy.
- [ ] Ghi lại root cause tại đúng tầng trước khi chỉnh app hoặc deployment.

## 14. Câu hỏi tự kiểm tra

**1. Controller `@RequestMapping("/api")`, `@GetMapping("/ping")`, context path `/shop`: URL nào đúng?**  
`/shop/api/ping`. Không cần thêm `/shop` vào annotation.

**2. MVC có context `/shop` và servlet path `/internal`: URL nào đúng khi matching strategy tương thích?**  
`/shop/internal/api/ping`. Không coi servlet prefix là context prefix.

**3. Với Spring Boot 3.5, vì sao `spring.mvc.servlet.path=/internal` có thể gặp vấn đề?**  
Vì parser `PathPatternParser` mặc định không tương thích custom servlet prefix; cần đánh giá thay matching strategy sang `ant-path-matcher` hoặc bỏ prefix đó.

**4. Trên WebFlux/Netty, property tương đương mục đích base path là gì?**  
`spring.webflux.base-path`. `server.servlet.context-path` thuộc Servlet context, không phải thay thế cho WebFlux base.

**5. 404 từ reverse proxy có đảm bảo request đã tới controller không?**  
Không. Nó có thể được trả trước khi request đến app hoặc context servlet.

**6. Vì sao có thể thấy `NoResourceFoundException` thay vì `NoHandlerFoundException` khi URL sai?**  
Vì static resource handler mặc định có mapping rộng `/**` và nhận request trước khi kết luận không có file.

**7. `@GetMapping("/ping")` mà client gửi POST sẽ luôn là 404?**  
Không. Thường trả 405 khi path có mapping nhưng HTTP method không được hỗ trợ.

**8. `/shop/api/ping` và `/shop/api/ping/` có chắc cùng route?**  
Không. Đừng dựa vào trailing slash match mặc định; test cả hai và quy định URL canonical.

**9. `/actuator/mappings` 404 nghĩa controller không được đăng ký?**  
Không. Actuator có thể chưa expose, bị bảo mật hoặc nằm ở path/port khác.

**10. `@WebMvcTest` có đủ chứng minh Tomcat context prefix đang hoạt động không?**  
Không hoàn toàn. Dùng embedded server `RANDOM_PORT` với HTTP request thật để kiểm context/servlet deployment.

**11. Nếu backend trực tiếp trả 200 nhưng qua ingress 404, nên điều tra ở đâu trước?**  
Host/path rewrite/upstream routing của ingress/gateway và cấu hình deployment, không sửa annotation vội.

**12. Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` có mặt, có thể mặc nhiên coi là WebFlux không?**  
Không. Boot thường ưu tiên MVC; cần xác minh stack thực.

**13. Nếu controller tự ném `ResponseStatusException(HttpStatus.NOT_FOUND)`, đó có phải lỗi mapping không?**  
Không. Mapping đã match nhưng business handler chủ động trả 404.

**14. Có nên expose `/actuator/mappings` công khai để dễ debug không?**  
Không. Chỉ dùng trong môi trường nội bộ được bảo vệ với người vận hành có quyền.

## 15. Tài liệu chính thức

- Spring Boot 3.5 — **Common Application Properties**: `server.servlet.context-path`, `spring.mvc.servlet.path`, `spring.mvc.pathmatch.matching-strategy`, `spring.webflux.base-path`, static resource settings: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — **Servlet Web Applications**: MVC path matching strategy, servlet prefix compatibility, static resource handler và `NoResourceFoundException`: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — **Reactive Web Applications**: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Framework — **Mapping Requests in Spring MVC**, class/method annotations và URI patterns: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — **WebFlux annotated request mapping**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Boot 3.5 — **Actuator Monitoring and Management over HTTP**, context/base path và separate management port: https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html
- Spring Boot — **Mappings Actuator Endpoint API**: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/mappings.html
- Spring Framework — **Web MVC URL handler/trailing slash considerations**: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot 3.5 — **Testing Spring Boot Applications**: `@SpringBootTest(RANDOM_PORT)`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Kết luận:** 404 trong Spring Boot chỉ được chẩn đoán đúng khi biết **request đã đi đến tầng nào**. Trong Spring MVC, đường dẫn bên ngoài thường được cấu thành bởi Servlet context path, DispatcherServlet mapping (nếu khác mặc định) và handler mapping; trong WebFlux/Netty, dùng WebFlux base path cùng handler mapping. Reverse proxy có thể strip/giữ prefix, Actuator có base path/port riêng, và static resource handler hoặc business code cũng có thể phát 404. Hãy xác minh runtime configuration, actuator mappings và actual HTTP route; dùng integration tests qua server thật với cả URL đúng và URL sai để tránh tái phát sau khi nâng cấp.