# Khai báo tuyến Web MVC bằng cấu hình hoặc Java DSL

## 1. Đặt vấn đề: cùng một route, hai cách khai báo

Trong một kiến trúc microservices, **Spring Cloud Gateway** là cổng vào chung: route predicate chọn nơi xử lý request, filter chain sửa path/header, service discovery tìm instance upstream và các chính sách xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS, quan sát request giúp vận hành an toàn.

Spring Cloud Gateway có hai nhánh server cần phân biệt:

- **Server WebFlux** dựa trên WebFlux, Project Reactor và Netty; Java DSL thường dùng `RouteLocatorBuilder`, `RouteLocator`, `GatewayFilter`.
- **Server Web MVC** dựa trên **Servlet và Spring WebMvc.fn**; Java DSL tạo `RouterFunction<ServerResponse>` từ `GatewayRouterFunctions` và `HandlerFunctions.http()`.

Chủ đề **“Khai báo tuyến Web MVC bằng cấu hình hoặc Java DSL”** thuộc chương **Server Web MVC** của module **SPRING_CLOUD_GATEWAY**. Bài thực hành xuyên suốt một route:

~~~text
Client:
  GET http://localhost:8080/api/catalog/products/42

Gateway Server Web MVC:
  Path=/api/catalog/**
  Method=GET
  StripPrefix=1
  AddRequestHeader=X-Edge-Source, mvc-gateway

Mock catalog-service:
  GET http://localhost:8081/catalog/products/42
  X-Edge-Source: mvc-gateway
~~~

Ta sẽ tạo route trên bằng **YAML** và **Java DSL** rồi kiểm tra hai cách cho cùng kết quả. Bài còn minh họa nhiều route, kết hợp predicates, `lb://` và những lỗi cấu hình dễ gặp.

> **Quan trọng về phiên bản:** Spring Cloud Gateway **Server MVC 4.2** dùng starter `spring-cloud-starter-gateway-mvc` và property `spring.cloud.gateway.mvc.routes`. Tài liệu **Server Web MVC 4.3/5.x** dùng starter `spring-cloud-starter-gateway-server-webmvc` và property `spring.cloud.gateway.server.webmvc.routes`. Đây là những biến thể theo release train; **không khai báo đồng thời** để “chắc ăn”. Luôn kiểm tra BOM, dependencies và cấu hình hiệu lực của ứng dụng thực tế.

### Kết quả học tập

Sau bài, bạn có thể:

1. Nhận biết route WebMvc.fn khác route reactive WebFlux.
2. Khai báo `id`, `uri`, `predicates`, `filters` trong YAML đúng version.
3. Viết Java DSL với `@Bean RouterFunction<ServerResponse>`, `route("id")`, `http()`, `before(uri(...))`.
4. Kết hợp Path, Method và Host; sửa đường dẫn bằng `StripPrefix`/`RewritePath`.
5. Sử dụng service discovery qua `lb://` (YAML) hoặc `lb()` (Java).
6. Test request thật tới upstream, tránh route overlap, SSRF và thiếu security.

## 2. Cách Server Web MVC xử lý request

Trong Gateway Server Web MVC, các route là những `RouterFunction` bình thường của **Spring WebMvc.fn**, sử dụng một handler proxy HTTP do Gateway cung cấp.

~~~mermaid
flowchart LR
    C["HTTP Client"] --> T["Servlet Container<br/>Tomcat / Jetty"]
    T --> M["Spring MVC HandlerMapping"]
    M --> P{"RequestPredicate<br/>Path / Method / Host"}
    P -->|"Khớp"| B["Before filters<br/>URI, StripPrefix, Header"]
    P -->|"Không"| N["Route khác hoặc no match"]
    B --> H["HandlerFunctions.http()"]
    H --> U["Upstream HTTP service"]
    U --> A["Response / after filters"]
    A --> C
~~~

Ba phần cấu thành một tuyến:

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Predicate** | Request nào được phép khớp tuyến này? | Path, Method, Host |
| **Handler** | Sau khi khớp, handler làm gì? | `HandlerFunctions.http()` proxy HTTP |
| **Filter** | Sửa request/response hoặc áp dụng policy nào? | `StripPrefix`, `AddRequestHeader`, retry |

Các kiểu Java cơ bản:

~~~java
org.springframework.web.servlet.function.RouterFunction
org.springframework.web.servlet.function.ServerRequest
org.springframework.web.servlet.function.ServerResponse
org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions
org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions
org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions
~~~

**Không dùng `Mono<Void>`, `ServerWebExchange` hay `RouteLocatorBuilder` như ví dụ WebFlux** để khai báo route cho MVC. MVC sử dụng mô hình Servlet, cùng các before/after/handler filter theo WebMvc.fn.

### 2.1. Phân biệt public URL, route path và target URI

| Thành phần | URL hoặc path |
| --- | --- |
| Browser/client gửi | `http://localhost:8080/api/catalog/products/42` |
| Gateway MVC so khớp | `/api/catalog/products/42` |
| Sau `StripPrefix=1` | `/catalog/products/42` |
| Upstream origin | `http://localhost:8081` |
| Backend nhận | `GET /catalog/products/42` |

**Path trong `uri` không nên được dùng để ngầm thêm prefix.** Tài liệu *How It Works* của Gateway MVC nêu rằng path được khai báo trong route URI bị bỏ qua. Nếu cần đổi path, dùng filter `StripPrefix`, `SetPath`, `PrefixPath` hoặc `RewritePath` được hỗ trợ, và xác minh path cuối ở upstream.

## 3. Chuẩn bị dependencies đúng stack

### 3.1. Dòng 4.3/5.x — Server Web MVC

Trong `pom.xml` đã quản lý phiên bản bằng **Spring Cloud BOM** tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

Nhánh Server Web MVC này làm việc với Servlet runtimes như Tomcat/Jetty. Không hiểu nhầm nó là chương trình Netty reactive chỉ vì tên thư viện có chữ Gateway.

### 3.2. Dòng 4.2 — Server MVC

~~~xml
<!-- Dành cho release train tương thích SCG MVC 4.2 -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-mvc</artifactId>
</dependency>
~~~

Đừng thêm cả hai starter ở cùng một ứng dụng mà không có hướng dẫn rõ ràng của release bạn chọn. Nếu project đã dùng starter **Server WebFlux**, không dùng các route MVC trong bài như thể chúng là cùng một runtime.

### 3.3. Tiền đề chạy ví dụ

- Gateway tại `http://localhost:8080`.
- Mock catalog backend tại `http://localhost:8081`, hỗ trợ `GET /catalog/products/42`.
- Mock order backend tại `http://localhost:8082`, hỗ trợ `POST /orders/create`.
- Spring Boot/Spring Cloud version tương thích.
- Nếu có Spring Security, dùng Servlet `SecurityFilterChain`; cấp credentials test nếu route được bảo vệ.
- Đối với `lb://`, cần Spring Cloud LoadBalancer và một nguồn `ServiceInstance` phù hợp.

`localhost` là minh họa khi các tiến trình cùng chạy trên **một host**. Trong Kubernetes hoặc Docker, nó không trỏ tới một pod/container khác; dùng service DNS.

## 4. Khai báo route bằng YAML ở Server Web MVC 4.3/5.x

Một route có các field chính:

| Field | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `id` | Định danh route | `catalog-read` |
| `uri` | Địa chỉ proxy target | `http://localhost:8081` |
| `predicates` | Tập điều kiện chọn request | `Path`, `Method`, `Host` |
| `filters` | Những biến đổi/chính sách trên route | `StripPrefix`, `AddRequestHeader` |
| `order` | Thông tin thứ tự khi model/config hỗ trợ | Cần kiểm chứng bằng integration test |
| `metadata` | Metadata bổ sung nếu phiên bản hỗ trợ | Không thay authentication |

Ví dụ `application.yml` cho **4.3/5.x**:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Edge-Source, mvc-gateway
~~~

Giải thích:

1. `Path=/api/catalog/**` cho phép đường dẫn catalog.
2. `Method=GET` làm route chỉ khớp GET.
3. Hai predicates trong cùng route được **kết hợp AND**: cả Path và Method đều phải thỏa.
4. `StripPrefix=1` loại segment đầu tiên là `api`, backend nhận `/catalog/products/42`.
5. `AddRequestHeader` gửi thêm `X-Edge-Source: mvc-gateway` tới backend.
6. `uri` xác định origin của HTTP request, không tự thay đổi nghiệp vụ hoặc bảo mật.

Ví dụ client gửi:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: localhost:8080
~~~

Mock backend dự kiến thấy:

~~~http
GET /catalog/products/42 HTTP/1.1
X-Edge-Source: mvc-gateway
~~~

Đó là **expected behavior**, không phải kết quả test đã chạy. Header `Host` outbound còn phụ thuộc HTTP proxy/client và các filter; nên kiểm tra ở backend, không hard-code nhận định về Host.

### 4.1. Chú ý tên namespace

Trong MVC 4.3/5.x, `spring.cloud.gateway.server.webmvc.routes` **khác** với:

~~~yaml
# PHẢN VÍ DỤ: đây không phải routes namespace của MVC 4.3/5.x.
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://localhost:8081
~~~

`server.webflux` dành cho Server **WebFlux**. Một file YAML có cấu trúc hợp lệ nhưng dùng sai prefix có thể không bind thành route MVC, dẫn đến 404. Cần xem startup logs, configprops và test route thực tế.

### 4.2. Không kích hoạt cả Java route tương đương cùng lúc

Bài này dùng cùng Path/Method trong YAML và Java để học hai cách viết. Khi chạy:

- Chọn **YAML** và tắt bean Java tương đương; hoặc
- Chọn **Java DSL** và bỏ/tắt YAML route tương đương.

Nếu cả hai cùng khớp `GET /api/catalog/**`, bạn có thể tạo route overlap và không biết bản nào đã xử lý. Không có bảo đảm rằng Java route tự override YAML hoặc ngược lại trong mọi phiên bản.

## 5. Biến thể YAML dành cho Server MVC 4.2

Ở nhánh **4.2**, routes property là `spring.cloud.gateway.mvc.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: catalog-read
            uri: http://localhost:8081
            predicates:
              - Path=/api/catalog/**
              - Method=GET
            filters:
              - StripPrefix=1
              - AddRequestHeader=X-Edge-Source, mvc-gateway
~~~

Bảng phiên bản:

| Nhánh | Starter | Prefix route |
| --- | --- | --- |
| **MVC 4.2** | `spring-cloud-starter-gateway-mvc` | `spring.cloud.gateway.mvc.routes` |
| **Web MVC 4.3/5.x** | `spring-cloud-starter-gateway-server-webmvc` | `spring.cloud.gateway.server.webmvc.routes` |
| **WebFlux** | Starter WebFlux tương ứng | Prefix WebFlux riêng; không dùng hai prefix trên |

**Không đặt cả hai danh sách route song song để bao phủ mọi version.** Khi nâng cấp, cần migration có review, chỉ giữ cấu hình được phiên bản hiện tại nhận và test route sau startup.

## 6. Khai báo route bằng Java DSL

Cách Java DSL được khuyến nghị là dùng `GatewayRouterFunctions.route("route-id")` và `HandlerFunctions.http()`.

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
public class CatalogRoutes {

    @Bean
    RouterFunction<ServerResponse> catalogReadRoute() {
        return route("catalog-read")
                .GET("/api/catalog/**", http())
                .before(uri("http://localhost:8081"))
                .before(stripPrefix(1))
                .before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
                .build();
    }
}
~~~

Tương ứng từng dòng:

| Java DSL | YAML |
| --- | --- |
| `route("catalog-read")` | `id: catalog-read` |
| `.GET("/api/catalog/**", http())` | `Path=/api/catalog/**`, `Method=GET` |
| `.before(uri("http://localhost:8081"))` | `uri: http://localhost:8081` |
| `.before(stripPrefix(1))` | `StripPrefix=1` |
| `.before(addRequestHeader("X-Edge-Source", "mvc-gateway"))` | `AddRequestHeader=X-Edge-Source, mvc-gateway` |
| `.build()` | Hoàn chỉnh route definition |

`@Bean` phải nằm trong vùng component scan. Nếu Java class chưa được đăng ký, route có thể không xuất hiện mặc dù code biên dịch được.

### 6.1. Vì sao sử dụng GatewayRouterFunctions.route("id")?

Spring WebMvc.fn cung cấp builder thuần:

~~~java
import static org.springframework.web.servlet.function.RouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

// Ví dụ trong @Bean trả RouterFunction<ServerResponse>:
return route()
        .GET("/get", http())
        .before(uri("https://example.org"))
        .build();
~~~

Gateway còn có `org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route(String routeId)`, bổ sung **route ID vào request metadata**, hữu ích với một số Gateway filters nâng cao và observability. Với tuyến Gateway nghiêm túc, `route("catalog-read")` giúp giữ định danh rõ ràng.

**Không nhầm** với `RouteLocatorBuilder` của WebFlux chỉ vì cả hai có phương thức tên `route`.

### 6.2. Vì sao http() đi kèm before(uri())?

Tài liệu Gateway MVC mới hướng dẫn dùng:

~~~java
.GET("/api/catalog/**", http())
.before(uri("http://localhost:8081"))
~~~

`http()` không tham số tìm URI đích trong request attributes do các filter như `uri()` thiết lập. Kể từ tài liệu **4.1.7**, `HandlerFunctions.http(String)` và `http(URI)` được đánh dấu deprecated; cách mới giảm khác biệt về cách quản lý target URI.

Nếu không đặt URI và cũng không có load-balancer filter thích hợp, HTTP handler không có đích rõ ràng. Vì vậy không tạo route `.GET("/api/catalog/**", http()).build()` rồi mong nó tự gọi upstream.

## 7. Khai báo nhiều route bằng YAML

Ví dụ catalog đọc dữ liệu, orders ghi dữ liệu:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-read
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Edge-Source, mvc-gateway

            - id: orders-write
              uri: http://localhost:8082
              predicates:
                - Path=/api/orders/**
                - Method=POST
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Edge-Source, mvc-gateway
~~~

Ma trận định tuyến dự kiến:

| Client request | Route khớp | Upstream request |
| --- | --- | --- |
| GET `/api/catalog/products/42` | `catalog-read` | GET `/catalog/products/42` tại 8081 |
| POST `/api/orders/create` | `orders-write` | POST `/orders/create` tại 8082 |
| POST `/api/catalog/products` | Không khớp hai routes trên | Không được proxy qua `catalog-read` |
| GET `/api/orders/42` | Không khớp hai routes trên | Không được proxy qua `orders-write` |
| GET `/api/unknown` | Không khớp | Không tự proxy |

Status HTTP cuối khi route không khớp tùy HandlerMapping khác, Spring Security và cấu hình ứng dụng; có thể là 404/405 hoặc một response khác. **Assertion chính** là request không được chuyển tới backend bằng route sai.

### 7.1. Method predicate không thay authorization

`Method=POST` giúp chọn route ghi, **không tự ngăn giao dịch trùng** và không xác thực người dùng. Với `POST /payments`, cần kiểm tra quyền, validation, CSRF theo kiểu credential và `Idempotency-Key`/dedup backend nếu có retry.

## 8. Khai báo nhiều route bằng Java DSL

Có thể đăng ký nhiều `RouterFunction` beans:

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
public class GatewayRoutes {

    @Bean
    RouterFunction<ServerResponse> catalogRead() {
        return route("catalog-read")
                .GET("/api/catalog/**", http())
                .before(uri("http://localhost:8081"))
                .before(stripPrefix(1))
                .before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
                .build();
    }

    @Bean
    RouterFunction<ServerResponse> ordersWrite() {
        return route("orders-write")
                .POST("/api/orders/**", http())
                .before(uri("http://localhost:8082"))
                .before(stripPrefix(1))
                .before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
                .build();
    }
}
~~~

Hai Java beans trên là **phương án thay thế**, không chạy đồng thời với các routes YAML có cùng Path/ID khi đang so sánh. Khi cần kết hợp, phải quản lý ownership và precedence một cách tường minh.

### 8.1. Với Java DSL, có thể tổ chức theo domain

Chẳng hạn mỗi class `CatalogRoutes`, `OrdersRoutes`, `PartnerRoutes` chịu trách nhiệm một nhóm endpoint. Nhưng vẫn cần:

- Một nguồn truth cho route ID.
- Test xung đột predicates giữa các class.
- Quy tắc quản lý URI target theo environment.
- Logging/metrics theo route ID ổn định.
- Code review các thay đổi liên quan đến authentication và target host.

## 9. Kết hợp predicate nâng cao bằng Java

Spring WebMvc.fn `RequestPredicate` hỗ trợ `.and()`, `.or()`, `.negate()`. Gateway MVC bổ sung `GatewayRequestPredicates` cho nhiều điều kiện thường dùng.

### 9.1. Kết hợp Host và Path

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.host;
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

@Configuration
class PartnerRoutes {

    @Bean
    RouterFunction<ServerResponse> partnerCatalog() {
        return route("partner-catalog")
                .route(
                    host("partner.example.test")
                        .and(path("/partner/catalog/**")),
                    http())
                .before(uri("http://localhost:8081"))
                .build();
    }
}
~~~

Route trên cần **Host = partner.example.test AND Path khớp**. Khi cần thêm GET-only, bổ sung predicate `method(HttpMethod.GET)` hoặc builder method phù hợp để giữ semantics nhất quán.

Host là dữ liệu HTTP có thể bị giả mạo tùy bối cảnh mạng; **Host predicate không thay authentication**. Cần token/API key đã được xác minh, TLS và authorization ở service.

### 9.2. OR và NEGATE

Một nhóm API có thể cho phép hai path:

~~~java
import static org.springframework.cloud.gateway.server.mvc.predicate.GatewayRequestPredicates.path;

// Một RequestPredicate ví dụ:
path("/api/catalog/**").or(path("/api/products/**"))
~~~

Hoặc yêu cầu không nằm trong một path bị loại:

~~~java
// Chỉ minh họa phép toán RequestPredicate, không phải security policy.
path("/api/**").and(path("/api/admin/**").negate())
~~~

Các phép toán này hữu ích để mô tả route logic, nhưng **không nên coi NEGATE path là biện pháp duy nhất bảo vệ `/api/admin/**`**. Spring Security và backend authorization vẫn phải kiểm tra quyền.

### 9.3. YAML Path + Method là AND

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
~~~

Các điều kiện trong cùng route phải cùng thỏa. Trong Java, `.GET(path, http())` tạo điều kiện Method+Path tương đương cho case đơn giản.

## 10. Filters của Gateway MVC: before, after và filter

Trong **WebMvc.fn**, các nhóm API có mục đích khác nhau:

| Nhóm | Ví dụ | Công dụng |
| --- | --- | --- |
| `before` | `BeforeFilterFunctions.uri`, `stripPrefix`, `addRequestHeader` | Biến đổi `ServerRequest` trước proxy handler |
| `after` | Các hàm `AfterFilterFunctions` | Biến đổi `ServerResponse` khi phù hợp |
| `filter` | `LoadBalancerFilterFunctions.lb`, các filter resilience | Bao quanh logic handler hoặc xử lý routing nâng cao |
| WebFlux GatewayFilter | `GlobalFilter`, `GatewayFilter` reactive | **Không** dùng trực tiếp như WebMvc.fn filter |

Ví dụ:

~~~java
.before(uri("http://localhost:8081"))
.before(stripPrefix(1))
.before(addRequestHeader("X-Edge-Source", "mvc-gateway"))
~~~

Thứ tự biến đổi request có thể ảnh hưởng đích cuối, đặc biệt khi dùng path filter và load balancing. Đừng suy ra mọi filter WebFlux có cùng tham số Java hoặc cùng behavior khi chuyển sang MVC.

### 10.1. Tự viết before filter nhỏ

Nếu thực sự cần một biến đổi request riêng, WebMvc.fn cho phép `before` nhận một `Function<ServerRequest, ServerRequest>`:

~~~java
import org.springframework.web.servlet.function.ServerRequest;
import java.util.function.Function;

static Function<ServerRequest, ServerRequest> addRequestTag() {
    return request -> ServerRequest.from(request)
            .header("X-Gateway-Tag", "catalog")
            .build();
}
~~~

Sau đó có thể gọi:

~~~java
.before(addRequestTag())
~~~

Nhưng với thao tác đã có trong Gateway như thêm header, **ưu tiên filter built-in** để giảm mã tùy biến, dễ nâng cấp và kiểm thử.

**Không đưa token/raw user identity vào header chỉ vì một filter Java có thể viết được.** Những header chứng minh danh tính phải xuất phát từ authentication đáng tin và được downstream kiểm tra theo hợp đồng.

## 11. Service discovery: lb:// trong YAML và lb() trong Java

### 11.1. YAML

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-read-lb
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

`lb://ORDER-SERVICE` là URI scheme đặc biệt. Gateway MVC yêu cầu LoadBalancer/discovery có thể tìm instance của service ID `ORDER-SERVICE`. Nó không tự khởi động registry hoặc tạo instances.

### 11.2. Java DSL

Tài liệu Gateway Server MVC yêu cầu gọi **`lb()` tường minh** trong Java DSL:

~~~java
package example.gateway.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.LoadBalancerFilterFunctions.lb;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
class OrdersLoadBalancedRoutes {

    @Bean
    RouterFunction<ServerResponse> ordersRead() {
        return route("orders-read-lb")
                .GET("/api/orders/**", http())
                .before(stripPrefix(1))
                .filter(lb("ORDER-SERVICE"))
                .build();
    }
}
~~~

**Đặc biệt quan trọng:**

- YAML `uri: lb://ORDER-SERVICE` và Java `.filter(lb("ORDER-SERVICE"))` đều mô tả routing qua ServiceInstance.
- Java dùng `http()` không tham số, LoadBalancer filter chịu trách nhiệm chọn URI cuối.
- Nếu có `stripPrefix()` hoặc `setPath()`, áp dụng **trước `lb()`** để tránh route URL sai.
- Khi không có service instance, mặc định thường có response **503**; cần kiểm tra version/error policy thực tế.
- `ServiceInstance.isSecure` có thể quyết định dùng HTTP hay HTTPS cho chặng backend; inbound HTTPS không bảo đảm outbound HTTPS.

**Không thêm `@LoadBalanced RestClient.Builder` cho internal HTTP client do Gateway MVC dùng.** Gateway có proxy client riêng; cố gắng load balance lần nữa qua `RestClient` interceptor có thể phá URL đã được `lb()` giải quyết.

### 11.3. Dòng xử lý mong đợi

~~~text
GET /api/orders/42
 -> StripPrefix(1)
 -> /orders/42
 -> lb("ORDER-SERVICE")
 -> ServiceInstance(host=orders-1, port=8080)
 -> Proxy HTTP GET /orders/42
~~~

Đây là sơ đồ mô phỏng. Muốn xác minh, mock/discovery test phải quan sát **backend nhận đúng path**, không chỉ nhìn client được 200.

## 12. RewritePath khi StripPrefix không đủ

Ví dụ muốn chuyển:

~~~text
/public/catalog/products/42 -> /catalog/products/42
~~~

Với các prefix tĩnh, `StripPrefix=1` thường đơn giản hơn. Khi cần mapping phức tạp, có thể sử dụng `RewritePath` và regex.

Java DSL minh họa:

~~~java
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.rewritePath;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

// Phần nội dung một @Bean trả RouterFunction<ServerResponse>:
return route("legacy-path-rewrite")
        .GET("/legacy/**", http())
        .before(uri("http://localhost:8081"))
        .before(rewritePath("/legacy/(.*)", "/$1"))
        .build();
~~~

Đoạn Java trên dùng regex capture nhóm 1. Với YAML, dấu `$`/`${...}` có thể bị Spring property placeholder hoặc YAML parser xử lý theo cách dễ nhầm; hãy đối chiếu tài liệu `RewritePath` của **đúng phiên bản** và test replacement với nhiều path, kể cả ký tự được URL encode.

**Lưu ý:** tài liệu Gateway MVC cảnh báo **path được viết trong target URI bị bỏ qua**. Muốn thêm một prefix `/v2` vào upstream, đừng đặt `uri: http://host/v2` rồi tin nó tự hoạt động. Dùng filter path phù hợp và assert backend path.

## 13. Tránh route overlap và trùng route ID

Giả sử khai báo:

~~~text
Route A: Path=/api/**
Route B: Path=/api/orders/**
Request: GET /api/orders/42
~~~

Cả A và B có thể khớp. Nếu A proxy sang gateway khác hoặc target không có auth, hậu quả có thể nghiêm trọng hơn một lỗi 404.

**Không mặc định route “cụ thể nhất luôn thắng”** khi phối hợp nhiều `RouterFunction` beans, YAML routes, route metadata và các handler MVC khác. Thay vào đó:

1. Định nghĩa predicates đủ hẹp, kết hợp Method/Host khi cần.
2. Không khai báo đúp route ID giữa YAML và Java.
3. Quy định nguồn sở hữu route; tránh “Java sẽ override YAML” như một giả định.
4. Kiểm tra thứ tự registration/precedence của **đúng version** nếu bắt buộc overlap.
5. Viết integration tests cho `/api/orders`, `/api/orders/`, `/api/orders/42`, `/api/orders-old`.
6. Dùng cùng security/authorization test khi thêm route mới.

### 13.1. Java DSL không có nghĩa cập nhật route runtime tùy ý

Một `@Bean RouterFunction` được tạo khi ApplicationContext khởi động thường không tự thay đổi vì bạn sửa Java source file hoặc YAML trên disk. Muốn cập nhật routes theo thời gian chạy, cần cơ chế được Gateway **Server MVC** phiên bản tương ứng hỗ trợ; không áp dụng nguyên xi `RouteDefinitionRepository`/`RefreshRoutesEvent` của WebFlux.

Nếu triển khai nhiều replicas, phải kiểm tra chúng cùng chạy phiên bản route/ứng dụng mới, không chỉ sửa config trên một pod.

## 14. MVC khác WebFlux ở những điểm nào?

| Vấn đề | Gateway Server WebFlux | Gateway Server Web MVC |
| --- | --- | --- |
| Runtime | WebFlux/Reactor/Netty | Servlet/Tomcat/Jetty |
| Java route | `RouteLocatorBuilder`, `RouteLocator` | `RouterFunction<ServerResponse>`, `GatewayRouterFunctions` |
| Proxy handler | Reactive routing chain | `HandlerFunctions.http()` |
| Context | `ServerWebExchange` | `ServerRequest` / Servlet |
| Route filters | `GatewayFilter`, `GlobalFilter` | `.before()`, `.after()`, `.filter()` |
| Security | `SecurityWebFilterChain` | Servlet `SecurityFilterChain` |
| Cấu hình | Prefix WebFlux riêng | `gateway.mvc` (4.2) hoặc `gateway.server.webmvc` (4.3/5.x) |

Phản ví dụ copy sai:

~~~java
// Đây là phong cách Gateway WebFlux, KHÔNG phải Java DSL Server Web MVC:
@Bean
RouteLocator customRoutes(RouteLocatorBuilder builder) {
    return builder.routes()
            .route("catalog", r -> r.path("/api/catalog/**")
                    .uri("http://localhost:8081"))
            .build();
}
~~~

Trong MVC, Java route phải trả `RouterFunction<ServerResponse>`; đây không phải việc đổi một import đơn giản.

### 14.1. Security sử dụng Servlet chain

Mẫu ngắn về phong cách Servlet Security:

~~~java
// Ví dụ riêng lẻ; cần @Bean, imports và Resource Server configuration.
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ví dụ dùng Bearer JWT resource server; khi sử dụng cookie/session authentication cần đánh giá và bật **CSRF protection** thích hợp, không tắt CSRF một cách máy móc. Security filter không tự được thay thế bằng route predicate `Host` hay header `X-User` do client gửi.

## 15. Kiểm thử YAML và Java DSL bằng curl

### 15.1. Chuẩn bị

Giả sử Gateway chạy cổng 8080 và mock upstream chạy cổng 8081. Chỉ bật **YAML route** hoặc **Java bean**, không bật cả hai cho cùng path.

Gửi:

~~~bash
curl -i http://localhost:8080/api/catalog/products/42
~~~

Mock upstream cần ghi lại:

~~~text
Method = GET
Path = /catalog/products/42
X-Edge-Source = mvc-gateway
~~~

Đó là **kết quả kỳ vọng**, không phải thử nghiệm đã thực thi.

### 15.2. Kiểm tra method không khớp

~~~bash
curl -i -X POST http://localhost:8080/api/catalog/products/42
~~~

Route `catalog-read` không được proxy POST đến catalog backend. Status phía client có thể khác nhau tùy HandlerMapping, Security và handlers khác; assertion chắc chắn là **upstream counter không tăng vì route GET**.

### 15.3. Kiểm tra query string

~~~bash
curl -i "http://localhost:8080/api/catalog/products/42?lang=vi"
~~~

Với cấu hình không sửa query, backend được kỳ vọng nhận path `/catalog/products/42` và query `lang=vi`. Kiểm tra ở mock server thay vì chỉ dựa vào response body nếu mock trả dữ liệu cố định.

### 15.4. So sánh phương án Java

Tắt YAML route, bật `@Bean RouterFunction` tương đương, khởi động lại, chạy lại ba curl trên rồi so sánh method/path/header/outcome. Không dùng hai cấu hình cùng lúc nếu mục đích là chứng minh tính tương đương.

Nếu Java route không hoạt động, kiểm tra:

- Class `@Configuration` có nằm trong component scan không?
- `RouterFunction` bean được đăng ký chưa?
- Import `GatewayRouterFunctions.route`, `HandlerFunctions.http`, `BeforeFilterFunctions.uri` đúng không?
- Có route/Controller khác match path trước không?
- Backend mock có đang chạy không?
- Property/starter của version được chọn có đúng không?

## 16. Kiểm thử tự động bằng Servlet/MVC tools

Bộ công cụ phù hợp là **MockMvc**, `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP test client và mock upstream như WireMock/MockWebServer. **Không** dùng `StepVerifier`/`MockServerWebExchange` như phương án chính cho một Gateway MVC thuần Servlet.

Một integration test nên:

1. Khởi động Gateway với **một phương án route**.
2. Khởi động mock catalog backend ở port được injection qua property hoặc test configuration.
3. Cho backend trả 200 và JSON chứa ID.
4. Gửi GET vào gateway test port; assert status/body.
5. Kiểm tra backend nhận **đúng** `GET /catalog/products/42`.
6. Kiểm tra `X-Edge-Source` xuất hiện đúng một giá trị dự kiến.
7. Gửi POST cùng path; assert backend **không** nhận thêm request do route GET.
8. Thử một path không khớp và một path ranh giới.
9. Test backend mất kết nối để quan sát error mapping.
10. Nếu có security, test thiếu token/thiếu quyền để bảo đảm route không bypass.

Pseudo-test để mô tả assertion:

~~~java
// Pseudocode, không phải API có sẵn của một thư viện cụ thể:
gateway.get("/api/catalog/products/42").expectStatus(200);
catalogStub.verifyRequest("GET", "/catalog/products/42");
catalogStub.verifyHeader("X-Edge-Source", "mvc-gateway");

gateway.post("/api/catalog/products/42").expectNotProxiedBy("catalog-read");
catalogStub.verifyRequestCount(1);
~~~

Các tên như `expectNotProxiedBy` chỉ là **mô tả điều cần assert**, không phải method có thể copy chạy ngay. Khi triển khai, dùng API thật của MockMvc, RestAssured, WireMock hoặc MockWebServer.

## 17. Bảo mật và vận hành của route MVC

Việc khai báo route chỉ là một phần của Gateway. Khi đưa vào production:

- **Authentication/authorization:** dùng Spring Security Servlet và kiểm tra quyền tài nguyên ở backend.
- **Input validation:** `Path`/`Host` không thay kiểm tra business data.
- **TLS:** inbound HTTPS không tự tạo outbound HTTPS; chọn URI/ServiceInstance secure theo policy.
- **SSRF:** target URI phải từ cấu hình/allowlist đáng tin, không từ query/header tự do của client.
- **Retry:** không thử lại POST thanh toán/đơn hàng nếu chưa có idempotency backend.
- **Rate limiting:** dùng key đã được xác thực, không tin `X-User-ID` client tự đặt.
- **Circuit breaker:** fallback không được báo thành công giả nếu backend đã thực hiện một thao tác ghi nhưng response thất lạc.
- **CORS:** điều khiển JavaScript browser, không thay authentication.
- **Observability:** theo dõi route ID, method, upstream path, status, latency, retry count.
- **Deployment:** cập nhật YAML/Java route cần cách rollout/reload đã được kiểm thử theo Server MVC version.

Không log raw `Authorization`, `Cookie`, access token, PII hoặc request body nhạy cảm trong Gateway. Không đưa request ID động vào metric label high-cardinality.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Khắc phục |
| --- | --- | --- |
| YAML route không tạo | Sai prefix WebFlux/MVC hoặc 4.2/4.3 | Kiểm tra starter, configprops và route tests |
| Java route không được sử dụng | Class không được scan, Bean chưa load | Kiểm tra ApplicationContext |
| Copy `RouteLocatorBuilder` vào MVC | Dùng API WebFlux | Đổi sang `RouterFunction<ServerResponse>` |
| `http()` không có target | Thiếu `before(uri(...))`/LB | Đặt target rõ ràng |
| `http("...")` báo deprecated | API cũ | Dùng `http()` + `uri()` |
| Backend nhận path sai | `StripPrefix` thiếu/sai | Assert request path ở mock |
| `uri: http://backend/base` không thêm `/base` | Nhầm URI path | Dùng path filter |
| POST bị route GET proxy | Route overlap hoặc thiếu `Method=GET` | Phân biệt predicates |
| Thứ tự route khó dự đoán | Route quá rộng/trùng bean/YAML | Không overlap, test precedence |
| Java lb route trả lỗi | Quên `.filter(lb())` hoặc thiếu discovery | Dùng LB API đúng |
| LB chọn URL sai path | `lb()` trước path filters | Sửa path trước LB |
| Lỗi `Service Instance cannot be null` | Double LB do `@LoadBalanced RestClient` | Không gắn LB interceptor cho proxy internal |
| Local chạy, Docker lỗi | Dùng localhost cho container khác | Service DNS |
| 401/403 dù Path khớp | Security Servlet chặn | Kiểm tra auth/scope/CSRF |
| Có body đúng nhưng đi nhầm backend | Nhiều route khớp | Upstream request counter và trace |
| Đổi YAML nhưng không thấy thay đổi | Chưa restart/reload | Deployment/reload mechanism đúng version |
| Client có CORS error | CORS/credentials/preflight không hợp lệ | Cấu hình Servlet CORS và Security |
| Header `X-Edge-Source` mất | Filter không chạy hoặc route khác | Kiểm tra upstream headers |
| 503 khi `lb://` | Service registry không có instance | Discovery health |
| Nguy cơ SSRF | URI từ dữ liệu client chưa kiểm soát | Allowlist và egress policy |

## 19. Bài thực hành tổng hợp

**Bối cảnh:** Một Gateway Server Web MVC nhận GET catalog và POST orders, backend là hai mock services.

Yêu cầu:

1. Chọn release train, khai báo **đúng MVC starter**.
2. Viết `catalog-read` bằng YAML với `Path=/api/catalog/**` và `Method=GET`.
3. Thêm `StripPrefix=1` và header `X-Edge-Source: mvc-gateway`.
4. Tạo `orders-write` bằng YAML, `Method=POST`, `uri: http://localhost:8082`.
5. Assert GET catalog được proxy tới `/catalog/products/42`; POST catalog không đi vào route GET.
6. Tắt YAML routes rồi viết hai `@Bean RouterFunction<ServerResponse>` tương đương bằng Java.
7. Thử predicate `Host` + `Path` bằng `.and()`; không dùng Host thay authentication.
8. Thử route `orders-read-lb` qua `lb://ORDER-SERVICE` hoặc `lb("ORDER-SERVICE")` khi đã có discovery.
9. Test route overlap với một `Path=/api/**` có chủ đích; quan sát và loại bỏ conflict.
10. Test upstream lỗi, auth, latency và path/header thực tế trước khi coi route an toàn.

### Bảng test

| Ca | Kết quả cần đạt |
| --- | --- |
| T1: YAML MVC đúng prefix | Route được đăng ký |
| T2: GET catalog | Backend đúng nhận `/catalog/products/42` |
| T3: POST catalog | Không bị proxy bởi route GET |
| T4: Header filter | Backend có `X-Edge-Source: mvc-gateway` |
| T5: Java DSL tương đương | Path/method/header/response tương đương YAML |
| T6: Sai prefix WebFlux | Test chỉ ra route MVC không được load |
| T7: `lb://` thiếu instance | Báo tình trạng discovery/503, không tự tạo service |
| T8: Route overlap | Test xác định route được chọn và loại bỏ trùng |
| T9: Unauthorized request | Bị security chặn theo chính sách |
| T10: Backend 5xx | Error/traces đúng route, không che lỗi |

Đây là **tiêu chí kiểm thử**, không phải tuyên bố các ví dụ đã chạy thành công.

## 20. Checklist trước production

- [ ] Dự án dùng **Gateway Server Web MVC** đúng Servlet stack.
- [ ] Starter và routes namespace khớp **version thực tế**.
- [ ] Route `id` duy nhất và có owner rõ.
- [ ] Path/Method/Host predicates đủ hẹp; tránh overlap không chủ đích.
- [ ] YAML và Java DSL không đăng ký trùng một route.
- [ ] Java beans trả `RouterFunction<ServerResponse>`, không dùng `RouteLocatorBuilder` của WebFlux.
- [ ] `GatewayRouterFunctions.route("id")` được dùng khi cần route metadata.
- [ ] `HandlerFunctions.http()` nhận target từ `before(uri(...))` hoặc `lb()`.
- [ ] Path filters đã được test ở upstream; không dựa vào path trong target URI.
- [ ] `stripPrefix()` chạy trước `lb()`.
- [ ] Không gắn `@LoadBalanced RestClient` một cách vô thức vào HTTP proxy của Gateway.
- [ ] Có mock upstream integration tests cho GET/POST/query/header và route không khớp.
- [ ] Spring Security Servlet, TLS, CSRF/CORS và backend auth được cấu hình đúng.
- [ ] Không chọn URI đích từ client header/query chưa tin cậy.
- [ ] Retry/rate-limit/circuit breaker được đánh giá theo tính chất nghiệp vụ.
- [ ] Có metrics, logs, traces và upstream request counters, đã redact credentials.
- [ ] Các môi trường dùng DNS/port hợp lệ; không giữ localhost trong pod production.
- [ ] Có rollback/rollout plan để cập nhật routes giữa nhiều replicas.
- [ ] Đã đối chiếu tài liệu Gateway **Server Web MVC** của release đang sử dụng.

## 21. Tổng kết và tài liệu tham khảo

**Spring Cloud Gateway Server Web MVC** dùng Servlet/Spring WebMvc.fn để xây API Gateway. Có hai cách khai báo route chính:

- **YAML:** điền `id`, `uri`, `predicates`, `filters` dưới `spring.cloud.gateway.mvc.routes` ở 4.2 hoặc `spring.cloud.gateway.server.webmvc.routes` ở 4.3/5.x.
- **Java DSL:** đăng ký `@Bean RouterFunction<ServerResponse>`, tạo route bằng `GatewayRouterFunctions.route("id")`, dùng `HandlerFunctions.http()` để proxy và `.before(uri(...))`, `.before(stripPrefix(...))` để xây target/path.

Đừng trộn WebFlux DSL với MVC, đừng giả định URI tự nối path, và đừng coi `Host` predicate là auth. Với service discovery, YAML dùng `lb://service-id`, còn Java DSL cần filter `lb("service-id")` theo tài liệu MVC. **Kiểm thử ở upstream** là cách đáng tin để xác nhận method, path, header và target đã đúng.

### Tài liệu chính thức

- [Spring Cloud Gateway Server Web MVC 5.0 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/starter.html).
- [Spring Cloud Gateway Server MVC 4.2 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway-server-mvc/starter.html).
- [Spring Cloud Gateway Server Web MVC — Java Routes API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/java-routes-api.html).
- [Spring Cloud Gateway Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html).
- [Spring Cloud Gateway Server Web MVC — Gateway Request Predicates](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/gateway-request-predicates.html).
- [Spring Cloud Gateway Server Web MVC — StripPrefix](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/stripprefix.html).
- [Spring Cloud Gateway Server Web MVC — AddRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/addrequestheader.html).
- [Spring Cloud Gateway Server Web MVC — LoadBalancer](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html).
- [Spring Cloud Gateway Server Web MVC — RewritePath](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/rewritepath.html).
