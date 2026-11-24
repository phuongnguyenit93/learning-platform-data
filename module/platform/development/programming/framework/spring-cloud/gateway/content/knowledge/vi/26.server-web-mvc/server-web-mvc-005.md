# GatewayRequestPredicates và các điều kiện được hỗ trợ trong Spring Cloud Gateway Server Web MVC

Khi xây dựng API Gateway, mỗi request trước tiên phải được **chọn đúng tuyến** rồi mới được chuyển đến microservice tương ứng. Câu hỏi “request này có khớp tuyến không?” được giải quyết bằng **request predicate**: điều kiện kiểm tra HTTP method, path, host, header, cookie, query parameter, thời gian hoặc tỷ trọng phân phối. Nếu điều kiện sai hoặc quá rộng, một request có thể đến nhầm backend, không nhận được filter bảo vệ cần thiết hoặc bị trả 404 dù service khỏe.

Trong **SPRING_CLOUD_GATEWAY**, có hai biến thể cần phân biệt: **Gateway Server WebFlux** sử dụng hệ sinh thái reactive, còn **Gateway Server Web MVC** sử dụng **Spring MVC Servlet stack** và cơ chế định tuyến hàm **WebMvc.fn**. Bài thuộc chương **Server Web MVC**, tập trung vào lớp `GatewayRequestPredicates`, các điều kiện được hỗ trợ, cách kết hợp điều kiện, kiểm thử và những giới hạn bảo mật khi Gateway đồng thời xử lý xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request.

> **Phạm vi phiên bản:** Các ví dụ Java dùng package `org.springframework.cloud.gateway.server.mvc.*` và cấu hình `spring.cloud.gateway.server.webmvc.routes` theo những dòng Gateway Server MVC hiện đại có hỗ trợ. Các tài liệu cũ có thể dùng namespace `spring.cloud.gateway.mvc.routes` hoặc khác biệt về starter/DSL. Danh sách predicate, đặc biệt `Version`, có thể **khác giữa Gateway 4.x và 5.x**. Luôn kiểm tra đúng Spring Boot, Spring Cloud release train, starter và tài liệu MVC tương ứng. Không áp nguyên Java API này vào WebFlux.

## 1. Predicate nằm ở đâu trong Gateway Server Web MVC?

**Request predicate** là một hàm kiểm tra `ServerRequest` và trả kết quả match hoặc không match. Ở Server MVC, các tuyến được biểu diễn dưới dạng **`RouterFunction<ServerResponse>`**, được tích hợp vào hạ tầng `HandlerMapping` của **Spring WebMvc.fn**.

~~~mermaid
flowchart TD
    C["HTTP request từ client"] --> S["Servlet filters / Spring Security"]
    S --> HM["Spring MVC HandlerMapping"]
    HM --> P{"RouterFunction + RequestPredicate match?"}
    P -->|Không| N["Thử route/handler phù hợp khác; có thể 404/405"]
    P -->|Có| F["Gateway MVC HandlerFilterFunctions"]
    F --> H["HandlerFunctions.http()"]
    H --> LB["HTTP routing hoặc load balancing"]
    LB --> B["Backend microservice"]
    B --> R["Response về client qua MVC Gateway"]
~~~

**Phân biệt ba công việc:**

| Cơ chế | Chức năng | Ví dụ |
|---|---|---|
| **Predicate** | Xác định request nào được route | `Path=/api/orders/**` và `Method=GET` |
| **Handler function** | Xử lý request đã match; Gateway thường proxy HTTP | `HandlerFunctions.http()` |
| **Handler filter function** | Làm việc trước/sau handler, biến đổi request/response hoặc áp chính sách | `BeforeFilterFunctions.uri(...)`, các filter path/header phù hợp |

Một predicate **không tự chuyển tiếp request**. Nó cũng **không đồng nghĩa xác thực/ủy quyền**. Request match `Host=admin.example.test` không có nghĩa người gửi đã được phép quản trị: `Host` là thông tin HTTP request cần quản trị qua ingress và Spring Security.

### Servlet MVC khác reactive WebFlux như thế nào?

| Tiêu chí | Gateway Server Web MVC | Gateway Server WebFlux |
|---|---|---|
| Nền tảng web | Spring MVC / Servlet stack | Spring WebFlux / reactive stack |
| Loại request trong functional routing | `org.springframework.web.servlet.function.ServerRequest` | `ServerWebExchange` trong gateway reactive |
| Điểm mở rộng route | `RouterFunction`, `RequestPredicate`, `HandlerFilterFunction` | RouteDefinition, predicate factory, GatewayFilter/GlobalFilter |
| Lớp predicate mở rộng | `GatewayRequestPredicates` | Những route predicate factories của WebFlux |
| Bảo mật phổ biến | Servlet `SecurityFilterChain` / `HttpSecurity` | Reactive `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Filter xử lý routing | MVC handler/before/after filter functions | Reactive GatewayFilter/GlobalFilter |
| Cấu hình phụ thuộc phiên bản | Nhóm `server.webmvc` hoặc namespace cũ | Nhóm `server.webflux` hoặc namespace cũ |

**Không thêm cả hai loại starter rồi cho rằng chúng chỉ khác tên.** MVC và WebFlux có mô hình request, filters, threading và integration khác nhau. Khi viết code, hãy kiểm tra imports và web stack thật để tránh gọi nhầm những API có tên tương tự.

## 2. GatewayRequestPredicates là gì?

Lớp trung tâm cho bài này là:

~~~java
org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates
~~~

Lớp này cung cấp những factory methods tạo **`RequestPredicate`** dùng trong WebMvc.fn. Gateway MVC **tái sử dụng nhiều predicate của Spring WebMvc.fn** đồng thời bổ sung những predicate đặc thù Gateway.

Những tên thường gặp trong tài liệu Gateway Server MVC:

- `after(...)`, `before(...)`, `between(...)`: điều kiện theo mốc thời gian.
- `cookie(...)`: tên cookie và regex giá trị.
- `header(...)`: tên HTTP header và regex giá trị.
- `host(...)`: pattern hostname; có thể chứa URI template variables.
- `method(...)`: một hoặc nhiều HTTP methods.
- `path(...)`: một hoặc nhiều `PathPattern`.
- `query(...)`: query parameter tồn tại hoặc regex của giá trị.
- `weight(...)`: chọn tuyến theo nhóm và tỷ trọng.
- **`version(...)`**: điều kiện API version trong những phiên bản mới hỗ trợ Spring MVC API version strategy.

**Không suy rằng mọi tên predicate của WebFlux đều là method cùng tên trong `GatewayRequestPredicates` của MVC.** Ví dụ `RemoteAddr` hoặc `XForwardedRemoteAddr` xuất hiện trong tài liệu WebFlux, nhưng **không có trong danh sách chính của trang Gateway Request Predicates cho Server MVC 4.3/5.0**. Nếu cần hạn chế IP hoặc kiểm tra forwarded address ở MVC, phải xác minh API/extension thực tế rồi thiết kế giải pháp servlet/proxy đúng trust boundary; không tự sao chép `GatewayRequestPredicates.remoteAddr(...)` từ WebFlux.

### Cú pháp Java DSL phổ biến

Một route Java có thể sử dụng tên tuyến, predicate, HTTP handler và before filter chỉ đích:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

@Configuration(proxyBeanMethods = false)
class GatewayMvcRoutes {

    @Bean
    RouterFunction<ServerResponse> catalogRoute() {
        return route("catalog-route")
            .route(path("/api/catalog/**"), http())
            .before(uri("http://localhost:9090"))
            .build();
    }
}
~~~

Cấu hình này có ý nghĩa:

1. `route("catalog-route")` tạo builder có **route ID** dùng cho metadata/quan sát Gateway.
2. `path("/api/catalog/**")` kiểm tra path incoming.
3. `http()` là handler proxy request đến đích đã được xác định.
4. `before(uri("http://localhost:9090"))` thiết lập URI đích trong giai đoạn xử lý trước handler.
5. `build()` trả `RouterFunction<ServerResponse>` cho Spring MVC đăng ký.

Phương thức `GatewayRouterFunctions.route(String)` hữu ích khi cần route ID rõ ràng. Spring WebMvc.fn cũng có `RouterFunctions.route()` cho API chức năng chung; **đừng nhầm hai factory chỉ vì cùng tên `route`**.

## 3. Bảng các điều kiện được hỗ trợ và phạm vi tương thích

Bảng này tổng hợp nhóm predicate được mô tả trong tài liệu **Gateway Server MVC**. Những ví dụ là **điều kiện match**, chưa bao gồm URI đích/filter.

| Predicate | Đầu vào chính | Ví dụ YAML | Ý nghĩa |
|---|---|---|---|
| **After** | Thời điểm có timezone | `After=2027-01-01T00:00:00+07:00[Asia/Ho_Chi_Minh]` | Match sau mốc |
| **Before** | Thời điểm có timezone | `Before=2027-12-31T00:00:00+07:00[Asia/Ho_Chi_Minh]` | Match trước mốc |
| **Between** | Hai mốc theo thứ tự | `Between=<start>,<end>` | Match trong khoảng thời gian |
| **Cookie** | Tên, regex | `Cookie=channel,partner` | Cookie `channel` khớp regex |
| **Header** | Tên, regex | `Header=X-Channel,partner` | Header khớp |
| **Host** | Danh sách hostname patterns | `Host=**.example.test` | Match theo host |
| **Method** | Một hoặc nhiều HTTP methods | `Method=GET,HEAD` | Match theo method |
| **Path** | Danh sách path patterns | `Path=/api/items/**` | Match theo đường dẫn |
| **Query** | Param, regex tùy chọn | `Query=lang,(vi|en)` | Query param tồn tại và khớp |
| **Weight** | Group, số trọng số | `Weight=catalog-rollout,8` | Chọn theo phân phối có trọng số |
| **Version** | Version cố định hoặc baseline | `Version=1.3` hoặc `Version=1.1+` | **Phụ thuộc phiên bản** và `ApiVersionStrategy` |

**Lưu ý về Version:** Trang tài liệu Gateway Server MVC **5.0** mô tả `Version` dựa trên `spring.mvc.apiversion.*` của Spring Framework. Trang **4.3** tập trung vào After/Before/Between/Cookie/Header/Host/Method/Path/Query/Weight và **không liệt kê Version** trong danh sách đó. Vì thế **không áp `Version` vào một bản 4.x nếu chưa kiểm tra API**.

**Lưu ý về WebMvc.fn:** `GatewayRequestPredicates` không phải toàn bộ tập điều kiện mà `RequestPredicate` trong Spring MVC có thể biểu diễn. Những predicate của `RequestPredicates` như `accept`, `contentType`, v.v. có thể được dùng trong Java DSL theo phiên bản Spring Framework, nhưng **không nên gọi tất cả chúng là Gateway-specific predicates** hoặc mặc định có YAML shortcut tương đương.

## 4. Path: chọn URL bằng Spring PathPattern

`Path` thường là điều kiện quan trọng nhất. Nó dùng cơ chế `PathPattern` từ Spring MVC để đối chiếu đường dẫn.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-by-path
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
~~~

Route match những đường dẫn như `/api/catalog/items/42`, nhưng không có nghĩa backend chắc chắn tồn tại endpoint `/api/catalog/items/42`. **Route matching và path rewrite là hai việc khác nhau**.

### Path variables

Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

// Bên trong một @Bean trả RouterFunction<ServerResponse>:
return route("item-by-id")
    .route(path("/api/items/{itemId}"), http())
    .before(uri("http://localhost:9090"))
    .build();
~~~

Với `GET /api/items/42`, path pattern match và biến `itemId` được rút trích. Trong MVC, `RequestPredicate` và `RouterFunction` lưu URI template variables trong **request attributes**, và các tiện ích MVC như `MvcUtils.getUriTemplateVariables(request)` có thể truy cập chúng khi dùng đúng ngữ cảnh.

**Không lấy biến trực tiếp từ `ServerWebExchange`** như code WebFlux; đây là MVC `ServerRequest`. Biến path cũng **không tự thay đổi** URI downstream nếu bạn chưa cấu hình filter/rewrite tương ứng.

### Những điều phải test với Path

- `/api/items/42` và `/api/items/42/` có được xử lý nhất quán không?
- `/api/items` có match `/api/items/**` đúng như mong muốn không?
- Case sensitivity có đúng yêu cầu không?
- Percent-encoded slash, dot segments, multiple slashes, Unicode normalization ở ingress/Gateway/backend có tương đương không?
- Pattern broad `/**` có chiếm route protected khác không?
- Route ID/ưu tiên hoặc thứ tự router functions có khiến request match nhầm tuyến không?

**Path không phải lớp authorization cuối cùng.** Backend vẫn phải kiểm tra quyền đối với item hoặc tenant. Đừng dựa vào `/api/public/**` để quyết định một request được quyền đọc dữ liệu.

## 5. Method: phân biệt GET, HEAD, POST và các thao tác khác

Predicate `method(...)` chọn một hoặc nhiều HTTP methods. Trong Server MVC, `GatewayRequestPredicates.method` có thể là một alias tiện lợi cho những phương thức tương ứng của WebMvc.fn.

~~~java
import org.springframework.http.HttpMethod;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;

var readMethods = method(HttpMethod.GET, HttpMethod.HEAD);
~~~

Cùng Path trong YAML:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: read-catalog
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET,HEAD
~~~

Đây là tuyến **chỉ đọc theo HTTP method**, nhưng backend vẫn phải tuân thủ semantics idempotency và authorization. Một `GET` được khai báo nhưng thực thi side effect nguy hiểm là vấn đề nghiệp vụ, không được predicate sửa giúp.

### Builder method + path shortcut

`RouterFunctions.Builder` cũng cung cấp cách ghép method và path:

~~~java
@Bean
RouterFunction<ServerResponse> getCatalogRoute() {
    return route("catalog-get")
        .GET("/api/catalog/**", http())
        .before(uri("http://localhost:9090"))
        .build();
}
~~~

Cách này thường ngắn hơn `path(...).and(method(HttpMethod.GET))` khi chỉ cần GET + Path.

**Chú ý OPTIONS và CORS preflight:** Route chỉ match `Method=GET` có thể không match `OPTIONS` do browser gửi trước request có CORS. Đừng vội mở toàn route cho mọi method; hãy cấu hình CORS và Spring Security/Servlet filters đúng vai trò, rồi kiểm thử OPTIONS end-to-end.

## 6. Host: chọn virtual host và tên miền

`host(...)` dùng hostname patterns theo cú pháp Ant-style với dấu chấm làm dấu phân cách. Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: public-catalog-host
              uri: http://localhost:9090
              predicates:
                - Host=**.api.example.test
                - Path=/catalog/**
~~~

Ứng dụng muốn phân biệt `catalog.api.example.test` và `admin.api.example.test` có thể dùng Host predicate, nhưng cần quản trị wildcard patterns.

Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.host;

var approvedHost = host("catalog.api.example.test");
~~~

### URI template variables từ Host

Một pattern như `{tenant}.api.example.test` có thể tạo biến `tenant`. Gateway MVC lưu URI template variables trong request attributes; handler filters có thể tham chiếu chúng theo API được hỗ trợ.

**Cảnh báo:** `tenant` trong hostname **không phải bằng chứng người gọi được phép dùng tenant ấy**. Host header có thể được client tự đặt và có thể bị thay đổi qua reverse proxy. Phải kết hợp TLS/ingress host ownership, trusted proxies, authentication, tenant authorization và kiểm tra backend.

## 7. Header: có tên và regex giá trị

`header(name, regexp)` giúp route chỉ match request mang một header có giá trị đúng regex. Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-partner-channel
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Channel,partner
~~~

Request:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: gateway.example.test
X-Channel: partner
~~~

Match route nếu header và những predicates khác cùng thỏa mãn.

Java:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

var channelCondition = header("X-Channel", "partner");
~~~

Vì `regexp` dùng Java regular expressions, lưu ý:

- `partner` khác `partner-2` theo cách thức match của implementation.
- Pattern dạng `\d+` trong Java string phải viết `"\\d+"` để giữ dấu backslash regex.
- Regex không được hiểu như wildcard path của `PathPattern`; đó là hai ngôn ngữ pattern khác nhau.
- Header có thể có nhiều giá trị; đừng tự suy cách matcher xử lý multiple values nếu logic quan trọng mà chưa test.
- Pattern quá phức tạp có thể gây CPU cao với input dài. Giới hạn độ dài và tránh regex có nguy cơ catastrophic backtracking.

**Không dùng `Header=X-Role,admin` để xác thực admin.** Client tự gửi header đó được. Muốn bảo vệ đường dẫn, dùng Servlet Spring Security `SecurityFilterChain` hoặc một lớp xác thực tin cậy phía trước.

## 8. Cookie: chọn theo cookie name và regex

`cookie(name, regexp)` kiểm tra cookie trong incoming request:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: cookie-demo
              uri: http://localhost:9090
              predicates:
                - Path=/api/demo/**
                - Cookie=channel,partner
~~~

Java:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.cookie;

var cookieCondition = cookie("channel", "partner");
~~~

**Cookie cũng là input client kiểm soát**. Cookie có thể mang session ID được server xác thực, nhưng chỉ nhìn giá trị cookie khớp regex `admin` **không chứng minh session đã được xác thực**.

Trong hệ thống có Spring Security Servlet, danh tính user phải được lấy từ security context/principal sau authentication. Filter hoặc predicate theo cookie có thể dùng cho **routing tiện ích**, ví dụ thử nghiệm trên client đã được cho phép, nhưng không phải cấp quyền.

### Cookie có biến thể và giới hạn

- Client có thể gửi cookie trùng tên do domain/path khác nhau.
- Browser quản lý `SameSite`, `Secure` và `HttpOnly` theo chính sách cookie.
- Header Cookie không phải định dạng phù hợp để log nguyên văn.
- Sticky routing dựa vào cookie tùy ý có thể không đạt phân phối ổn định khi user xóa cookie; cần thiết kế cơ chế stickiness rõ ràng.
- Không đưa session ID vào metric tags hoặc audit logs.

## 9. Query: kiểm tra param tồn tại hoặc regex của giá trị

`query(...)` có hai kiểu phổ biến:

1. Chỉ yêu cầu một query parameter **hiện diện**.
2. Yêu cầu parameter có giá trị khớp regex.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: has-preview-flag
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Query=preview

            - id: language-filter
              uri: http://localhost:9091
              predicates:
                - Path=/api/articles/**
                - 'Query=lang,(vi|en)'
~~~

Java DSL:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.query;

var hasPreview = query("preview");
var vietnameseOrEnglish = query("lang", "(vi|en)");
~~~

**Đừng coi tên query parameter có mặt là một bằng chứng feature đã được duyệt**. `?preview=true` có thể do client tự gửi. Nếu preview data là bí mật hoặc chưa công bố, backend vẫn phải xác thực quyền.

### Giá trị lặp và encoding

Test những URL:

~~~text
/api/articles?lang=vi
/api/articles?lang=en
/api/articles?lang=fr
/api/articles?lang=vi&lang=en
/api/articles?lang=
/api/articles?lang=%76%69
~~~

Cách chọn giá trị khi query xuất hiện nhiều lần, decode percent encoding và match regex cần được kiểm chứng bằng request thực trong Gateway/version đang dùng, nhất là khi routing ảnh hưởng dữ liệu hoặc policy. Nếu regex/cách parse không như dự kiến, có thể định tuyến request vào service sai.

## 10. After, Before, Between: điều kiện theo thời gian

Các predicate này cho phép routing dựa trên **thời điểm server xét request**.

- `after(ZonedDateTime)`: match request sau mốc.
- `before(ZonedDateTime)`: match request trước mốc.
- `between(ZonedDateTime, ZonedDateTime)`: match trong một khoảng; mốc thứ hai phải sau mốc thứ nhất.

Ví dụ một cửa sổ thử nghiệm năm 2027 với timezone rõ ràng:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-launch-window
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - After=2027-01-01T00:00:00+07:00[Asia/Ho_Chi_Minh]
                - Before=2027-02-01T00:00:00+07:00[Asia/Ho_Chi_Minh]
~~~

Hai điều kiện ở route trên phải cùng đúng. Nếu sử dụng `Between` thay thế, cần đưa hai mốc theo cú pháp đúng với release train.

Java:

~~~java
import java.time.ZonedDateTime;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.between;

var launchWindow = between(
    ZonedDateTime.parse(
        "2027-01-01T00:00:00+07:00[Asia/Ho_Chi_Minh]"),
    ZonedDateTime.parse(
        "2027-02-01T00:00:00+07:00[Asia/Ho_Chi_Minh]")
);
~~~

Một số dòng tài liệu hỗ trợ truyền mốc dạng **epoch milliseconds** trong cấu hình. Không tự lẫn epoch milliseconds với seconds, hay bỏ timezone rồi dựa vào default timezone của server.

### Điều kiện thời gian có những rủi ro nào?

| Rủi ro | Tác động | Cách kiểm tra |
|---|---|---|
| Server clocks lệch giữa Gateway nodes | Cùng request vào node khác cho kết quả khác | Đồng bộ NTP/clock và quan sát node |
| Thiếu timezone/offset | Truy cập mở/đóng lệch giờ | Luôn dùng `ZonedDateTime` rõ ràng |
| DST ở một timezone có daylight saving | Mốc thay đổi theo thời gian địa phương | Test gần thời điểm DST nếu có |
| Mốc thứ hai không sau mốc đầu | Cấu hình không hợp lệ hoặc match không như ý | Validate lúc startup/deploy |
| Khác nhau ở thời điểm đúng bằng boundary | Test thất bại sát mốc | Test trước/bằng/sau theo contract implementation |
| Dùng time predicate làm quyền truy cập | Route có thể mở khi policy bảo mật chưa sẵn sàng | Bảo vệ bằng Spring Security độc lập |

**Không lấy After/Before/Between làm cơ chế thu hồi quyền bảo mật.** Đó là route selection theo đồng hồ, không thay thế authentication, authorization, feature flags đã được kiểm soát hoặc release governance.

## 11. Weight: canary traffic theo nhóm và tỷ trọng

`weight(group, weight)` giúp phân phối requests giữa các routes thuộc **cùng nhóm** theo trọng số. Ví dụ hai phiên bản catalog:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-stable
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Weight=catalog-rollout,8

            - id: catalog-canary
              uri: http://localhost:9091
              predicates:
                - Path=/api/catalog/**
                - Weight=catalog-rollout,2
~~~

Mục tiêu là khoảng **80% traffic** cho stable và **20%** cho canary khi điều kiện khác nhau cùng khớp và cơ chế trọng số được áp dụng đúng.

**Không cam kết đúng 8/10 requests trong từng nhóm 10 requests.** Đây là phân phối có tính thống kê; cần lượng mẫu đủ lớn, đo theo route ID và thực hiện thử nghiệm thực tế.

Java DSL tương ứng:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.weight;

@Bean
RouterFunction<ServerResponse> catalogCanaryRoutes() {
    return route("catalog-stable")
        .route(weight("catalog-rollout", 8)
            .and(path("/api/catalog/**")), http())
        .before(uri("http://localhost:9090"))
        .build()
        .and(route("catalog-canary")
            .route(weight("catalog-rollout", 2)
                .and(path("/api/catalog/**")), http())
            .before(uri("http://localhost:9091"))
            .build());
}
~~~

### Weight không tự cung cấp những gì?

- **Không tự sticky theo user**; cùng user có thể đi stable ở request này và canary ở request tiếp theo.
- Không đồng nghĩa một canary deploy đã pass health/readiness.
- Không tự sửa token audience, session sharing, schema hay cache compatibility.
- Không tự giới hạn traffic theo địa lý hoặc tenant.
- Không tự bảo đảm fallback/circuit breaker ở hai routes có cùng chính sách.

Để rollout an toàn, nên phân phối **trong cùng một phạm vi path/method/host mong muốn**, giữ security filters và resource budgets nhất quán, đo lỗi/latency theo route và có rollback.

## 12. Version: predicate mới cần ApiVersionStrategy

Trong các bản Gateway Server MVC mới có `Version`, route matching có thể dựa trên API version được trích xuất bởi **Spring Framework `ApiVersionStrategy`**.

Ví dụ cấu hình resolver lấy phiên bản từ header, sau đó route theo phiên bản:

~~~yaml
spring:
  mvc:
    apiversion:
      use:
        header: X-API-Version

  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-v13
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Version=1.3

            - id: catalog-v11-plus
              uri: http://localhost:9091
              predicates:
                - Path=/api/catalog/**
                - Version=1.1+
~~~

Ý nghĩa trong tài liệu có hỗ trợ:

- `Version=1.3`: match phiên bản chính xác `1.3`.
- `Version=1.1+`: match phiên bản `1.1` trở lên theo chiến lược so sánh phiên bản.
- `spring.mvc.apiversion.use.header` chỉ cách trích xuất phiên bản từ request.

**Không áp đoạn này vào Gateway 4.3 hoặc một Spring Framework chưa có cơ chế MVC API version phù hợp**. Tên cấu hình và hành vi phải được xác nhận theo phiên bản mục tiêu.

### Nguy cơ fail-open khi thiếu resolver

Tài liệu Gateway MVC 5.0 mô tả một trường hợp đáng chú ý: **khi không có `ApiVersionStrategy` được cấu hình, predicate `Version` có thể coi request là match thay vì chặn**. Vì vậy, nếu cần route version để tách API nhạy cảm, phải:

1. Cấu hình strategy bằng một nguồn phiên bản rõ ràng.
2. Test request có version đúng, thiếu version, version sai và malformed.
3. Không coi version header do client chọn là authentication hoặc authorization.
4. Kiểm tra route order/conflicts, đặc biệt khi có tuyến baseline `1.1+` và tuyến exact `1.3` có thể cùng match.
5. Giữ backend compatibility; version routing không tự chuyển đổi schema/body.

**Quan trọng:** Cách xử lý “thiếu strategy” và tie-breaking có thể thay đổi trong bản phát hành khác. Không thiết kế quyền truy cập dựa duy nhất vào predicate version.

## 13. Kết hợp điều kiện bằng AND, OR và phủ định

`RequestPredicate` của **WebMvc.fn** hỗ trợ tổ hợp điều kiện bằng `and(...)`, `or(...)` và, với API framework phù hợp, `negate()`.

### AND: tất cả điều kiện phải đúng

~~~java
import org.springframework.http.HttpMethod;

import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

var partnerCatalog = path("/api/catalog/**")
    .and(method(HttpMethod.GET))
    .and(header("X-Channel", "partner"));
~~~

Request match khi **cùng lúc** path đúng, method GET và header đúng.

Cấu hình YAML nhiều predicates trên **cùng route** cũng biểu diễn ý tưởng AND:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: partner-catalog
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Channel,partner
~~~

### OR: chỉ cần một trong các nhánh khớp

~~~java
var eitherVersionPath = path("/api/v1/catalog/**")
    .or(path("/api/v2/catalog/**"));
~~~

Dùng OR khi các nhánh thực sự nên chọn **cùng route/handler**. Nếu chỉ muốn gộp hai path, `path("/api/v1/catalog/**", "/api/v2/catalog/**")` cũng là lựa chọn đáng xem xét.

**Không coi hai phần tử trong `predicates:` của một route YAML là OR**. Với cấu hình tĩnh, hãy dùng tính năng hỗ trợ danh sách patterns trong cùng predicate hoặc tạo routes riêng; không tự tạo cú pháp `Or=...` nếu bản Gateway không có.

### Kết hợp có ngoặc cho rõ logic

~~~java
var policy = path("/api/catalog/**")
    .and(method(HttpMethod.GET))
    .and(
        header("X-Channel", "partner")
            .or(query("preview"))
    );
~~~

Ý nghĩa:

~~~text
Path đúng
  AND Method=GET
  AND (X-Channel=partner OR có query parameter preview)
~~~

Biểu thức Java trên dùng `preview` như **tín hiệu routing minh họa**, không phải quyền xem dữ liệu preview. Authentication và authorization vẫn phải thực hiện riêng.

### Phủ định

`RequestPredicate.negate()` có thể hữu ích để loại một nhóm request trong Java DSL khi nền tảng hỗ trợ. Nhưng **không dùng phủ định của Header/Query để chống giả mạo security identity**: client có thể thay input, và một cấu hình có nhiều nhánh OR/NOT dễ tạo vùng match ngoài ý muốn.

~~~mermaid
flowchart TD
    A["Incoming request"] --> P{"Path=/api/catalog/**?"}
    P -->|Không| X["Không match"]
    P -->|Có| M{"Method=GET?"}
    M -->|Không| X
    M -->|Có| CH{"Header X-Channel=partner OR Query preview tồn tại?"}
    CH -->|Có| Y["Route match -> HandlerFunctions.http()"]
    CH -->|Không| X
~~~

## 14. Những điều kiện của WebMvc.fn không nhất thiết là Gateway-specific

`GatewayRequestPredicates` nằm trên nền **Spring WebMvc.fn**. Khi dùng Java DSL, bạn có thể gặp những predicate của Spring Framework:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RequestPredicates.contentType;

var expectsJson = accept(MediaType.APPLICATION_JSON);
var sendsJson = contentType(MediaType.APPLICATION_JSON);
~~~

Hai điều kiện khác nhau:

- `accept(application/json)` kiểm tra representation mà client **có thể nhận** (thường từ header `Accept`).
- `contentType(application/json)` kiểm tra media type của request body (từ `Content-Type`).

Chúng có thể giúp chọn handler trong WebMvc.fn, nhưng:

1. **Không gọi chúng là phương thức của `GatewayRequestPredicates` nếu thực ra import từ `RequestPredicates`.**
2. Không giả định mọi functional predicate có một cú pháp YAML Gateway route predicate tương ứng.
3. Không coi `Content-Type` do client gửi là bằng chứng body hợp lệ; backend phải validate payload/schema.
4. CORS, method matching và error handling phải được test ở MVC runtime thật.

### RemoteAddr và IP-based routing

Trong nhiều hướng dẫn WebFlux có các predicate `RemoteAddr`, `XForwardedRemoteAddr`. **Không copy nguyên danh sách đó sang Gateway MVC** khi trang MVC của phiên bản đang dùng không công bố chúng. Muốn routing theo client IP trong servlet stack có thể cần:

- Lớp ingress/WAF hoặc server-level routing đã được tin cậy.
- Một custom `RequestPredicate` xử lý `ServerRequest.servletRequest()`/remote address theo API được hỗ trợ, sau khi xác định proxy trust.
- Kiểm tra các cấu hình `Forwarded`/`X-Forwarded-For` thuộc web server/Spring MVC để tránh IP giả mạo.

**Không lấy `X-Forwarded-For` thô làm quyền truy cập.** Chỉ dùng thông tin forwarded do một chuỗi proxy đáng tin cậy kiểm soát; backend vẫn cần authorization.

## 15. Cấu hình cùng logic trong Java DSL và YAML

Giả sử mục tiêu nghiệp vụ: chỉ cho GET requests trên `/api/catalog/**` có header `X-Channel: partner` qua backend catalog.

### Cách 1: Java DSL

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

@Configuration(proxyBeanMethods = false)
public class CatalogGatewayMvcConfiguration {

    @Bean
    public RouterFunction<ServerResponse> partnerCatalogRoute() {
        return route("partner-catalog")
            .route(
                path("/api/catalog/**")
                    .and(method(HttpMethod.GET))
                    .and(header("X-Channel", "partner")),
                http()
            )
            .before(uri("http://localhost:9090"))
            .build();
    }
}
~~~

### Cách 2: YAML

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: partner-catalog
              uri: http://localhost:9090
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Channel,partner
~~~

**Không khai báo đồng thời hai định nghĩa cùng route ID này trong một app rồi coi là hai cách thể hiện một route duy nhất.** Hãy chọn một cơ chế cấu hình (hoặc quản lý ID/ưu tiên rõ ràng) để tránh routes trùng và hành vi lựa chọn không mong muốn.

### So sánh

| Tiêu chí | Java DSL | YAML |
|---|---|---|
| Khả năng tái sử dụng biểu thức Java | Cao, dễ `and`/`or`/custom predicate | Phụ thuộc cú pháp configuration binder |
| Review cấu hình route | Cần đọc code và tests | Dễ thấy routes và params |
| Custom `RequestPredicate` | Trực tiếp trong code | Cần infrastructure/binding phù hợp |
| Thay đổi cấu hình | Build/deploy code thông thường | Có thể đổi config qua deployment |
| Kiểm soát type | Compiler kiểm tra API | Startup/binding phát hiện lỗi |
| Rủi ro | Thiếu tests, DSL thay đổi theo version | Namespace sai, typo predicate, order/route overlap |

Chọn Java khi cần tổ hợp logic rõ ràng hoặc custom predicate; chọn YAML khi chỉ cần những điều kiện chuẩn, dễ review. Trong cả hai trường hợp, **không cho user không tin cậy tự quyết định URI, regex, filter, host và route priority**.

## 16. Route selection không bảo đảm chính sách bảo mật

Một route match đúng về mặt predicate có thể vẫn là request không được phép.

### Header, cookie, query và host do ai kiểm soát?

| Dữ liệu | Client có thể tự đặt không? | Có nên dùng để authorization không? |
|---|---|---|
| `X-Role` / `X-Channel` | Có | Không, nếu chưa được lớp tin cậy xác minh |
| Cookie tùy ý | Có | Không; phải xác thực session/credential |
| Query `?admin=true` | Có | Không |
| `Host` | Có thể gửi giá trị khác, tùy ingress/TLS/proxy | Không dùng một mình |
| `Authorization: Bearer ...` | Client gửi token, nhưng hệ thống phải xác minh | Dùng **Spring Security** để validate trước khi tin |
| JWT claims đã xác minh | Được cấp bởi issuer và đã validate | Có thể làm đầu vào của authorization policy |
| IP forwarded | Có thể giả nếu proxy không lọc | Chỉ qua trusted-proxy policy |

Gateway Server MVC thường tích hợp **Spring Security Servlet**. Route predicate chạy trong WebMvc.fn matching; nó **không tự đảm nhận** xác minh JWT, roles/scopes, session fixation hoặc CSRF.

Nếu cần bảo vệ `/api/admin/**`, hãy cấu hình một `SecurityFilterChain` phù hợp và kiểm tra backend authorization. Khi có nhiều Spring Security filter chains hoặc management port riêng, test cụ thể từng path/method/host, đừng tưởng vì route không match thì route khác không thể tiếp nhận.

### CORS preflight và method predicate

Browser có thể gửi `OPTIONS` preflight trước POST/GET có custom headers. Một route `Method=POST` thường không match OPTIONS; kết quả preflight phụ thuộc Servlet/Spring MVC CORS, Spring Security và reverse proxy. **Đừng thêm OPTIONS vào mọi route một cách vô điều kiện**; thiết lập CORS policy theo origin/method/header được phép, rồi kiểm thử bằng browser và cURL.

### Mở route trên Host wildcard

`Host=**.example.test` có thể match nhiều hostname thuộc các tenant/vhost khác nhau. Nếu đó là mục tiêu multitenancy, phải có **tenant routing + authorization** đúng, không chỉ trích template variable từ Host rồi forward request đến backend theo chuỗi tự nhập.

## 17. Kiểm thử predicates không chỉ bằng một request thành công

Một bài lab nên xác nhận đồng thời:

1. **Một request đúng** thực sự match và đến backend.
2. **Một request gần giống nhưng sai điều kiện** không rơi vào route đó.
3. Không có **route khác** nhận request bị loại ngoài ý muốn.
4. Không có mất mát security headers hoặc lộ dữ liệu giữa tenants.
5. Các trường hợp proxy/encoding/headers lặp và route overlap được xử lý như thiết kế.

### Môi trường lab

Giả sử:

- Gateway Server MVC tại `http://localhost:8080`.
- Backend echo test tại `http://localhost:9090`, trả lại path/method và mã HTTP test; không echo Authorization/Cookie thật.
- Route `partner-catalog` như phần 15.
- Không có route khác trùng `/api/catalog/**` trong môi trường test cơ bản.
- Có Spring Security policy lab rõ ràng; nếu auth được bật, truyền credentials test phù hợp.

### Bước 1 — Đúng ba điều kiện

~~~bash
curl -i \
  -H "X-Channel: partner" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Kỳ vọng **route match**, backend được gọi. Mã HTTP cuối phụ thuộc backend/test security; không dùng HTTP 200 làm bằng chứng duy nhất nếu phía trước có handler khác.

### Bước 2 — Sai Header

~~~bash
curl -i \
  -H "X-Channel: guest" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Kỳ vọng route `partner-catalog` **không match**. Có thể nhận 404, 405, 401/403 hoặc route khác tùy ứng dụng; điều chính yếu là backend partner-route **không bị gọi**.

### Bước 3 — Sai Method

~~~bash
curl -i -X POST \
  -H "X-Channel: partner" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Kỳ vọng không match route chỉ GET. Nếu app có handler POST khác, request vẫn có thể nhận response; vì thế test phải xác định **route ID/backend đích**, không chỉ status.

### Bước 4 — Sai Path

~~~bash
curl -i \
  -H "X-Channel: partner" \
  "http://localhost:8080/api/orders/42"
~~~

Không match predicate `Path=/api/catalog/**`.

### Bước 5 — Trường hợp CORS preflight

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: X-Channel" \
  "http://localhost:8080/api/catalog/items/42"
~~~

Quan sát `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và status theo policy thật. Không mặc định `GatewayRequestPredicates.method(GET)` tự xử lý OPTIONS.

### Ma trận kiểm thử theo predicate

| Predicate | Positive test | Negative/boundary test |
|---|---|---|
| Path | `/api/catalog/items/42` | Path khác, trailing slash, encoded slash |
| Method | GET được phép | POST/DELETE không được phép |
| Host | Host đúng pattern | Host tenant khác, fake Host, proxy host |
| Header | Giá trị đúng regex | Vắng header, multi-value, regex near-match |
| Cookie | Cookie đúng tên/giá trị | Cookie giả, trùng tên, missing cookie |
| Query | `lang=vi` | `lang=fr`, trùng param, percent-encoding |
| After/Before | Request trong cửa sổ | Trước/bằng/sau boundary, node lệch clock |
| Between | Mốc thời gian hợp lệ | Hai mốc ngược, lệch timezone |
| Weight | Nhiều requests phân bố gần tỷ trọng | Mẫu nhỏ, route overlap, canary unhealthy |
| Version nếu có | Version đúng | Thiếu resolver, missing/malformed version, overlap baseline |

## 18. Unit test trực tiếp với RequestPredicate và Mock ServerRequest

Vì Server MVC dùng **WebMvc.fn `RequestPredicate`**, một số trường hợp có thể test riêng logic matching mà không khởi động toàn Gateway. Ví dụ kiểm tra `Path` + `Method` + `Header` với `MockHttpServletRequest`:

~~~java
package example.gateway.mvc;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.converter.StringHttpMessageConverter;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.servlet.function.RequestPredicate;
import org.springframework.web.servlet.function.ServerRequest;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.method;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.header;

class GatewayRequestPredicateTest {

    private final RequestPredicate predicate =
        path("/api/catalog/**")
            .and(method(HttpMethod.GET))
            .and(header("X-Channel", "partner"));

    private ServerRequest request(
            String httpMethod, String uri, String channel) {

        MockHttpServletRequest servletRequest =
            new MockHttpServletRequest(httpMethod, uri);

        if (channel != null) {
            servletRequest.addHeader("X-Channel", channel);
        }

        return ServerRequest.create(
            servletRequest, List.of(new StringHttpMessageConverter()));
    }

    @Test
    void matchesWhenAllConditionsAreTrue() {
        assertTrue(predicate.test(request(
            "GET", "/api/catalog/items/42", "partner")));
    }

    @Test
    void rejectsDifferentMethod() {
        assertFalse(predicate.test(request(
            "POST", "/api/catalog/items/42", "partner")));
    }

    @Test
    void rejectsDifferentHeader() {
        assertFalse(predicate.test(request(
            "GET", "/api/catalog/items/42", "guest")));
    }
}
~~~

**Mục đích test:** chứng minh điều kiện `AND` và behavior của API trên một Spring Framework version. Đoạn test cần `spring-test`, JUnit và các dependencies tương ứng. Nó **chưa chứng minh** route bean được Spring đăng ký, YAML được bind đúng hay Gateway thực sự forward đến URI mong muốn.

### Integration test cần làm thêm

Một integration test với Gateway MVC runtime thật và mock HTTP backend phải kiểm tra:

- Route ID có được đăng ký trong `HandlerMapping` hay không.
- URI `http://localhost:9090` có được sử dụng đúng.
- Requests đúng/sai predicate có gọi backend hay không.
- Filter xử lý URI/path/header có chạy đúng trước `HandlerFunctions.http()`.
- Các response 404/405/401/403 phát sinh ở tầng nào.
- Sau khi thêm route khác, **route ordering/conflicts** có thay đổi không.
- Startup trên Java/Boot/Cloud baseline được hỗ trợ có còn hoạt động không.

Không kết luận cấu hình production đã đúng chỉ dựa vào ba unit tests ở trên.

## 19. Troubleshooting: khi route MVC không match

| Triệu chứng | Nguyên nhân cần xem | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy `GatewayRequestPredicates` | Dùng starter WebFlux, sai artifact/phiên bản, import nhầm | Xác nhận Gateway Server MVC và package |
| YAML route không được nạp | Sai namespace `server.webmvc`/namespace cũ | Đối chiếu configprops đúng release train |
| Path đúng nhưng nhận 404 | Method/Header/Host/Query khác; route chưa register | Test từng predicate và route ID |
| Method GET nhưng không match | Builder/route chỉ nhận method khác | So predicate/HTTP method thực |
| Host match khi gọi trực tiếp nhưng không match qua ingress | Host bị proxy rewrite | Kiểm tra Host/forwarded host và trusted proxies |
| Header/Cookie/Query regex match sai | Regex escape, YAML quoting, giá trị lặp | Test input thực, canonicalization |
| Dùng `and` nhưng muốn `or` | Boolean logic sai | Gom các nhánh rõ ràng trong Java DSL |
| YAML có nhiều predicates tưởng là OR | Cấu hình nhiều predicates thường AND | Dùng multi-pattern hoặc routes riêng |
| Time predicate lỗi ở một node | Clock/timezone lệch | Kiểm tra NTP/timezone và boundary |
| Weight phân phối không đúng 80/20 trên 10 requests | Mẫu quá nhỏ, route nhóm/khác predicates | Đo thống kê với lượng mẫu phù hợp |
| `Version` không hoạt động | Chưa hỗ trợ ở Gateway version hoặc thiếu `ApiVersionStrategy` | Kiểm tra Spring MVC version strategy, tests |
| RemoteAddr method không có | Sao chép API WebFlux sang MVC | Dùng custom MVC predicate/edge policy nếu cần |
| Request qua security trả 401/403 trước route | Servlet Spring Security chặn | Kiểm tra `SecurityFilterChain` riêng |
| OPTIONS preflight bị từ chối | Method predicate chỉ GET/POST; CORS/security sai | Kiểm tra CORS ở MVC/Servlet layer |
| Backend 404 nhưng route đã match | Không rewrite path/URI đúng | Quan sát request thật tại backend |
| Route mới chiếm traffic route cũ | Pattern/host/order overlapping | Review toàn bộ RouterFunctions, ưu tiên và route IDs |
| Header client tự đặt lại được coi là quyền | Dùng predicate thay authorization | Tách authentication và authorization |
| Cấu hình Weight canary lỗi sau deploy | Hai target không đồng nhất schema/auth | Rollback, kiểm tra health, request distribution |

### Quy trình xác định lỗi theo 6 câu hỏi

1. Ứng dụng chạy **Gateway Server Web MVC** hay WebFlux?
2. Route được khai báo bằng **YAML** hay **Java DSL**, và namespace/import có đúng không?
3. Những điều kiện `Path`, `Method`, `Host`, `Header`, `Cookie`, `Query`, thời gian hoặc version nào đang từ chối request?
4. Có route/handler khác match trước hoặc security filter chặn không?
5. Khi route đã match, `HandlerFunctions.http()` có forward đến đúng backend/path/instance không?
6. HTTP status cuối đến từ Gateway routing, Servlet security, ingress hay downstream?

Đừng sửa bằng cách đổi tất cả predicates thành `Path=/**` hoặc mở `permitAll` toàn cục: cách đó có thể biến một lỗi matching thành sự cố bảo mật.

## 20. Checklist nghiệm thu và những bài tập mở rộng

### Checklist

- [ ] Tôi biết **Server Web MVC** dựa trên Servlet/WebMvc.fn, không phải WebFlux reactive.
- [ ] Tôi import đúng `GatewayRequestPredicates` trong package `server.mvc.predicate`.
- [ ] Tôi hiểu `RouterFunction<ServerResponse>`, `HandlerFunctions.http()` và `BeforeFilterFunctions.uri(...)`.
- [ ] Tôi phân biệt predicate chọn route với handler/filter thực hiện forwarding.
- [ ] Tôi dùng `Path` đúng kiểu `PathPattern` và kiểm tra các URL có biến template.
- [ ] Tôi biết `Method` và `.GET(...)` trong Java DSL.
- [ ] Tôi biết `Header`, `Cookie` và `Query` dùng regex, không phải cơ chế authentication.
- [ ] Tôi xác minh `Host`/virtual host và proxy trust.
- [ ] Tôi biết `After`, `Before`, `Between` cần mốc có timezone và clock nhất quán.
- [ ] Tôi biết `Weight` là phân phối theo nhóm/tỷ trọng, không tự sticky và không bảo đảm tỷ lệ trên mẫu nhỏ.
- [ ] Tôi chỉ dùng `Version` khi Gateway/MVC framework thật sự hỗ trợ và đã cấu hình `ApiVersionStrategy`.
- [ ] Tôi không copy `RemoteAddr`/`XForwardedRemoteAddr` từ tài liệu WebFlux sang MVC mà không kiểm tra API.
- [ ] Tôi dùng `and`/`or`/`negate` đúng ý định, không nhầm nhiều YAML predicates thành OR.
- [ ] Tôi không gọi predicate có nguồn từ `RequestPredicates` là chức năng riêng của `GatewayRequestPredicates`.
- [ ] Tôi kiểm thử route conflicts, wildcard Path/Host và priority.
- [ ] Tôi không dùng Host/Header/Cookie/Query do client tự khai làm bằng chứng quyền truy cập.
- [ ] Tôi duy trì Spring Security Servlet authN/authZ, rate limit, TLS và backend authorization độc lập.
- [ ] Tôi đã test CORS preflight OPTIONS, forward path, backend errors và các header/proxy cases.
- [ ] Tôi chạy unit test WebMvc.fn predicates cùng integration tests Gateway → backend.
- [ ] Tôi xác minh config namespace/starter/version khi nâng Spring Cloud release train.

### Bài tập thực hành

**Bài tập 1 — AND:** Xây route chỉ match `GET /api/public/articles/**` khi `Query=lang,(vi|en)`. Test `lang=vi`, `lang=fr`, thiếu param, và request POST.

**Bài tập 2 — OR:** Dùng Java DSL để match cả `/api/v1/catalog/**` lẫn `/api/v2/catalog/**` vào một backend; so với hai routes YAML riêng và kiểm tra thứ tự.

**Bài tập 3 — Host:** Tạo hai routes cùng path nhưng khác Host. Test direct request và request qua ingress; chứng minh client không thể dùng Host đơn lẻ để vượt authorization.

**Bài tập 4 — Time window:** Dùng `Between` cho một cửa sổ bảo trì có timezone rõ ràng; test trước, đúng sát mốc và sau mốc trên hai Gateway nodes.

**Bài tập 5 — Canary:** Cấu hình `Weight=catalog-rollout,9` và `Weight=catalog-rollout,1` cho cùng path. Gửi lượng request test đủ lớn và kiểm tra phân phối, 5xx, latency, auth policy của stable/canary.

**Bài tập 6 — Version (nếu hỗ trợ):** Cấu hình `spring.mvc.apiversion.use.header` và `Version=1.3`. Test thiếu header, version sai, version đúng, rồi bỏ resolver trong lab để kiểm chứng behavior/version cụ thể.

**Bài tập 7 — Security invariants:** Thử đặt `Header=X-Role,admin` cho route nhạy cảm; giải thích tại sao vẫn cần Spring Security Servlet và backend authorization.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway — Gateway Request Predicates, Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html) — danh sách predicates và ví dụ Java/YAML của bản hiện hành.
- [Spring Cloud Gateway 4.3 — Gateway Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html) — đối chiếu tập predicate ở dòng 4.3, nhất là khi `Version` chưa được liệt kê.
- [Spring Cloud Gateway — Java Routes API, Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/java-routes-api.html) — `RouterFunctions.Builder`, `GatewayRouterFunctions` và `HandlerFunctions.http()`.
- [Spring Cloud Gateway — How It Works, Server Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html) — cơ chế `HandlerMapping` và các loại handler/filter.
- [Spring Framework — WebMvc.fn](https://docs.spring.io/spring-framework/reference/web/webmvc-functional.html) — `RouterFunction`, `RequestPredicate`, `and`/`or` và cách ghép functional routes.
- [Spring Framework — MVC API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-versioning.html) — `ApiVersionStrategy` và cơ chế phân giải version ở những dòng hỗ trợ.
- [Spring Security — Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/index.html) — authentication, authorization và `SecurityFilterChain`, không dùng predicate thay security.
- [Spring Boot — Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html) — cơ chế property binding và quản lý cấu hình theo môi trường.

**Ghi nhớ:** `GatewayRequestPredicates` trong **Spring Cloud Gateway Server Web MVC** giúp xây điều kiện match request cho **WebMvc.fn RouterFunction**, với các nhóm **Path, Method, Host, Header, Cookie, Query, After, Before, Between, Weight** và **Version ở những phiên bản có hỗ trợ**. Hãy chọn đúng stack, phân biệt **predicate với filter và authentication**, hiểu `and`/`or`, kiểm tra namespace/điều kiện theo release train và test cả những request **không được match**. Một route match đúng cú pháp chưa bảo đảm nó chọn đúng backend hoặc an toàn khi công bố.
