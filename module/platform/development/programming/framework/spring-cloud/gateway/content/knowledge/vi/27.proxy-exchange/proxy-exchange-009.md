# Giới hạn áp dụng cấu hình route và filter của Gateway Server

## 1. Vấn đề: có ProxyExchange nhưng cấu hình Retry, RewritePath không chạy

Trong **SPRING_CLOUD_GATEWAY**, chúng ta thường xây dựng API Gateway với route predicates, filter chain, biến đổi đường dẫn/header, khám phá dịch vụ, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request. Các khả năng này được tài liệu **Spring Cloud Gateway Server** mô tả rất đầy đủ. Tuy nhiên, Spring Cloud Gateway còn có một phong cách khác: **Proxy Exchange**.

Ví dụ một controller:

~~~java
@GetMapping("/edge/items/{id}")
public ResponseEntity<?> read(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {
    return proxy.uri("http://127.0.0.1:9091/items/" + id).get();
}
~~~

Giả sử lập trình viên thêm:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - AddResponseHeader=X-Server-Filter,applied
          routes:
            - id: catalog
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/edge/items/**
              filters:
                - RewritePath=/edge/items/(?<id>.*), /items/\${id}
                - name: Retry
                  args:
                    retries: 2
                    statuses:
                      - BAD_GATEWAY
~~~

Rồi họ chờ controller `ProxyExchange` tự thêm header, sửa path và retry theo danh sách filter này. **Đó là một giả định sai về ranh giới hai sản phẩm.**

Tài liệu chính thức của Spring Cloud Gateway viết rõ về **Proxy Exchange**: đây là một phong cách Gateway thay thế, và **tài liệu Gateway Server không áp dụng cho phong cách này**. Cụ thể, một annotated controller dùng `ProxyExchange` **không tự trở thành RouteDefinition của Gateway Server**, cũng không tự đi qua các `GatewayFilterFactory` hoặc `HandlerFilterFunction` chỉ vì chúng được khai báo trong route của Gateway Server.

Bài thuộc chương **Proxy Exchange**, chủ đề **“Giới hạn áp dụng cấu hình route và filter của Gateway Server”**. Mục tiêu không phải chê ProxyExchange thiếu khả năng, mà là hiểu **đường xử lý, phạm vi cấu hình và trách nhiệm tự triển khai** để không tạo ra một cổng vào tưởng đã bảo vệ nhưng thực ra thiếu filter.

> **Kết luận sớm:** ProxyExchange phù hợp khi cần proxy có chọn lọc ngay trong một **`@Controller` / `@RestController`**. Nếu cần một cổng API với hàng trăm route, policy filter chuẩn theo route, route refresh, discovery và actuator route inventory, **Gateway Server** thường phù hợp hơn.

## 2. Hai flavor, mỗi flavor lại có hai web stacks

Spring Cloud Gateway phân biệt hai **flavor**:

1. **Gateway Server**: API Gateway đầy đủ, xử lý routing/filtering theo cấu hình route hoặc Java Routes API của Server.
2. **Proxy Exchange**: thư viện công cụ `ProxyExchange` đưa vào **annotated web handler**, cho phép controller thực hiện một HTTP exchange tới downstream.

Mỗi flavor có thể dùng **Web MVC** hoặc **WebFlux**. Đừng nhầm:

- `Gateway Server Web MVC` với `Proxy Exchange Web MVC` — **cùng Servlet stack** nhưng không cùng loại route/filter.
- `Gateway Server WebFlux` với `Proxy Exchange WebFlux` — **cùng reactive stack** nhưng không cùng bộ `RouteDefinition/GatewayFilter`.

| Lựa chọn | Điểm vào | Định tuyến chính | Bộ lọc đặc thù |
| --- | --- | --- | --- |
| Server WebFlux | `RoutePredicateHandlerMapping` và `RouteLocator` | `RouteDefinition`, predicate factories, Java routes | `GatewayFilter`, `GatewayFilterFactory`, `GlobalFilter` |
| Server Web MVC | WebMvc.fn `RouterFunction` với HTTP forwarding handler | Java Routes API hoặc routes YAML của Gateway Server MVC | `BeforeFilterFunctions`, `AfterFilterFunctions`, `HandlerFilterFunction` |
| Proxy Exchange WebFlux | `@GetMapping/@PostMapping` controller | Spring WebFlux annotated handler mapping + code controller | Spring WebFlux `WebFilter`/security, logic controller, `ProxyExchange` API |
| Proxy Exchange Web MVC | `@GetMapping/@PostMapping` controller | Spring MVC annotated handler mapping + code controller | Servlet `Filter`, Spring MVC interceptor/security, `ProxyExchange` API |

### 2.1. Sơ đồ đường đi của cùng một URI công khai

~~~mermaid
flowchart TB
    C["Client GET /edge/items/42"]
    C --> D{"Kiến trúc đã chọn?"}
    D -->|"Gateway Server WebFlux"| S1["RoutePredicateHandlerMapping"]
    S1 --> S2["RouteDefinition + Server GatewayFilter chain"]
    S2 --> P1["HTTP routing filter → backend"]
    D -->|"ProxyExchange WebFlux"| W1["Annotated @GetMapping handler"]
    W1 --> W2["ProxyExchange.uri(...).get()"]
    W2 --> P2["HTTP client → backend"]
    D -->|"ProxyExchange Web MVC"| M1["DispatcherServlet / @GetMapping"]
    M1 --> M2["ProxyExchange.uri(...).get()"]
    M2 --> P3["HTTP client → backend"]
~~~

Sơ đồ chỉ minh họa ba đường đi, **không** có nghĩa một ứng dụng không thể đồng thời chứa nhiều loại handler. Khi trộn modules, việc chọn handler chịu ảnh hưởng của các HandlerMapping/route predicates riêng; cần kiểm chứng request **thực tế được handler nào phục vụ**.

### 2.2. Điều gì vẫn có thể tái sử dụng?

Hai flavor vẫn dựa trên Spring Boot, Spring Framework và các thư viện Spring Security/Micrometer/Spring Cloud tương ứng. Chẳng hạn:

- **Spring Security** có thể bảo vệ request trước controller.
- **Bean Validation** có thể kiểm tra path/query/body của controller.
- **Micrometer/Observation** có thể ghi metrics và tracing.
- **Spring Cloud LoadBalancer hoặc Resilience4j** có thể được dùng **khi bạn tích hợp rõ ràng**, không phải tự động kế thừa mọi Server GatewayFilter.
- **TLS, timeouts, HTTP client pooling** vẫn có thể cấu hình ở HTTP client/infrastructure đúng tầng.

Điểm quan trọng: **dùng chung hệ sinh thái Spring không đồng nghĩa dùng chung route/filter pipeline của Gateway Server**.

## 3. Bản đồ các tính năng: tự động hay phải viết riêng?

| Chức năng yêu cầu | Gateway Server (đúng route/filter) | Annotated ProxyExchange đơn thuần |
| --- | --- | --- |
| Match path, method, header | Route predicate factories | `@GetMapping`/`@RequestMapping`, Spring MVC/WebFlux mapping |
| Định nghĩa ID, URI, predicates, filters bằng Gateway routes YAML | Được hỗ trợ | **Không tự bind vào controller** |
| `RewritePath`, `StripPrefix`, `SetPath` | Gateway filter theo route | Tự chọn/biến đổi destination URI trong controller |
| `AddRequestHeader`/`AddResponseHeader` factory | Theo filter chain của route | Dùng ProxyExchange header API, ResponseEntity mapper hoặc Spring web layer |
| `RequestRateLimiter` + `KeyResolver` | Server WebFlux GatewayFilterFactory | Không tự bật; tự tích hợp limiter/security/quota policy |
| `CircuitBreaker` và Retry GatewayFilter | Theo route Server với config tương ứng | Không tự chạy; áp resilience có chủ đích cho downstream call |
| `TokenRelay`/auth filter của Server | Dùng đúng cấu hình và dependency Server | Phải xác thực và chuyển credential có chủ đích |
| `lb://service-id` và discovery route locator | Server Gateway integration | Không tự áp route discovery cho annotated controller |
| `Default-filters` cho các routes Server | Áp cho Server route theo namespace/version | **Không phải global filter cho tất cả controllers** |
| `RefreshRoutesEvent`, route definition repository | Làm mới route cache Server | Không tự thay đổi `@GetMapping`/destination code |
| `/actuator/gateway/routes` | Quan sát routes Server khi bật Actuator đúng | Không phải danh mục đầy đủ của annotated `ProxyExchange` mappings |
| Servlet Filter / WebFlux WebFilter | Tùy web stack, độc lập route filters | **Vẫn có thể** áp dụng vào controller |
| Spring Security trên web stack | Có thể bảo vệ Gateway | Có thể bảo vệ ProxyExchange như handler thông thường |

Đây là **bản đồ phạm vi mặc định**, không tuyên bố mọi thứ không thể thực hiện với ProxyExchange. Bạn có thể **viết code/cấu hình riêng** để đạt chức năng tương đương. Nhưng khi đó cần xác minh implementation, thứ tự, hành vi lỗi và observability — không gọi một property Server rồi chờ phép màu.

### 3.1. Mẹo chẩn đoán ban đầu

Hỏi một câu trước khi debug:

> “Request này có được xử lý bởi một `Route` của Gateway Server, hay bởi một `@RestController` nhận `ProxyExchange`?”

Nếu là trường hợp thứ hai, không nên bắt đầu bằng cách chỉnh `spring.cloud.gateway.server.webflux.routes[...].filters` để sửa vấn đề controller. Hãy nhìn vào **mapping của controller, mã gọi `proxy.uri(...).get()`, HTTP client và các Spring filters/interceptors bảo vệ handler**.

## 4. Dependency và namespace: tránh cài sai loại Gateway

### 4.1. Proxy Exchange MVC/WebFlux

Từ tài liệu Gateway 4.3/5.x, hai artifact:

~~~xml
<!-- Cho annotated controller Spring MVC (Servlet) -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>
~~~

~~~xml
<!-- Cho annotated controller Spring WebFlux (reactive) -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
</dependency>
~~~

Dự án thực tế chỉ thêm **một** artifact phù hợp web stack, cùng Spring Boot web starter, và quản lý versions bằng **Spring Cloud BOM** phù hợp Spring Boot. Không dùng Server starter như điều kiện bắt buộc để có `ProxyExchange`.

### 4.2. Tên artifact cũ và mới

Từ Spring Cloud release train 2025.0, các module được đổi tên để tách rõ flavor và web stack:

| Mục đích | Tên cũ | Tên được công bố mới |
| --- | --- | --- |
| MVC Proxy Exchange | `spring-cloud-gateway-mvc` | `spring-cloud-gateway-proxyexchange-webmvc` |
| WebFlux Proxy Exchange | `spring-cloud-gateway-webflux` | `spring-cloud-gateway-proxyexchange-webflux` |
| MVC Gateway Server | `spring-cloud-starter-gateway-mvc` | `spring-cloud-starter-gateway-server-webmvc` |
| WebFlux Gateway Server | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` |

Tên cũ được deprecate theo release notes, không tự suy rằng chúng là **bốn sản phẩm có pipeline filter dùng chung**. Các project trên Gateway 4.2.x có thể dùng module/tiền tố cũ; hãy xem đúng BOM và bản triển khai, đừng trộn ngẫu nhiên code từ 4.2 với property 5.x.

### 4.3. Prefix cấu hình của Proxy Exchange cũng có namespace riêng

Release notes Spring Cloud 2025.0 phân biệt:

~~~properties
# Legacy prefix từng dùng cho ProxyExchange:
spring.cloud.gateway.proxy.*

# Prefix mới phân theo web stack:
spring.cloud.gateway.proxy-exchange.webmvc.*
spring.cloud.gateway.proxy-exchange.webflux.*
~~~

Đây là **nhóm properties của Proxy Exchange** (chẳng hạn header policy theo version), **không phải** namespace của Gateway Server routes hoặc default-filters. Khi dựa vào một property cụ thể, tra configuration metadata của **artifact/version đang chạy**.

Ngược lại, properties route của Gateway Server WebFlux đời mới là `spring.cloud.gateway.server.webflux.routes`, Gateway Server Web MVC là `spring.cloud.gateway.server.webmvc.routes`; trước đây lần lượt có tiền tố ngắn hơn như `spring.cloud.gateway.routes` và `spring.cloud.gateway.mvc.routes`.

## 5. Anti-pattern: cấu hình Server tưởng đã bảo vệ ProxyExchange

Giả sử một ứng dụng chỉ có **Proxy Exchange Web MVC**, controller:

~~~java
@GetMapping("/edge/items/{id}")
public ResponseEntity<?> read(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {
    return proxy.uri("http://127.0.0.1:9091/items/" + id).get();
}
~~~

Một bạn thêm cấu hình:

~~~yaml
# KHÔNG phải cách bật các Server GatewayFilter cho controller trên
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: catalog-server
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/edge/items/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Expected-Server-Filter,true
                - AddResponseHeader=X-Policy-From-Server,true
                - name: Retry
                  args:
                    retries: 2
~~~

Nếu chỉ cài Proxy Exchange MVC (không có Gateway Server MVC route machinery), **cấu hình route Server này không tạo filter chain quanh `@GetMapping`**. Framework binder có thể bỏ qua các property không có auto-configuration tương ứng hoặc xử lý khác tùy classpath/version; không tuyên bố YAML chắc chắn gây lỗi startup.

Nếu **cùng ứng dụng cũng cài Gateway Server MVC**, cấu hình có thể tạo một **Server route riêng**. Khi đó:

- Request nào khớp route Server có thể đi qua filter Server **do route Server sở hữu**.
- Request vào annotated ProxyExchange controller vẫn là một **đường handler độc lập**; không có chuyện `@GetMapping` tự kế thừa `StripPrefix`/`Retry` từ danh sách Server.
- Nếu Server route và controller **cùng match một URL**, có thể xảy ra xung đột/ưu tiên HandlerMapping. Hãy xác minh handler thực tế trước khi kết luận filter có tác dụng.

**Không làm bài test “cấu hình không áp dụng” bằng hai routes trùng path** rồi chỉ nhìn response 200. Nên dùng paths riêng, hoặc tắt hẳn Server route khi test ProxyExchange để thấy rõ phạm vi.

### 5.1. Vì sao default-filters cũng không phải filter global cho controllers?

Thuộc tính:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - AddResponseHeader=X-From-Server,yes
~~~

có nghĩa là “áp filter cho **routes của Gateway Server WebFlux** theo cơ chế Server”, **không** phải “thêm header cho mọi HTTP endpoint do Spring Boot phục vụ”. Một controller dùng `ProxyExchange WebFlux` không tự trở thành Server Route vì cùng dùng WebFlux.

Muốn một chính sách **global** cho annotated handlers, có thể dùng `WebFilter` (WebFlux) hoặc `Servlet Filter` (MVC) đúng phạm vi và thứ tự, hay một Security chain. Đây là **bộ lọc của Spring web stack**, không phải `Gateway Server default-filters`.

## 6. Lab MVC: một annotated controller tự quyết định destination

Ta dựng hai ứng dụng riêng trong một môi trường lab:

| Ứng dụng | Port | Vai trò |
| --- | ---: | --- |
| Proxy Exchange MVC | 8080 | Chứa `@GetMapping` nhận `ProxyExchange<byte[]>` |
| Backend catalog | 9091 | Nhận `GET /items/{id}` và trả JSON echo |

Lab này **không thêm Gateway Server starter** và không tạo `RouteDefinition`. Mục đích là thấy logic định tuyến thực sự đến từ **annotation + controller code**.

### 6.1. Dependencies

Với Spring Boot 3.x và Spring Cloud BOM phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

Không ghi version riêng cho thư viện Spring Cloud khi BOM đang quản lý. Với Spring Boot 4.x, tên web starter có thể khác, nên chọn dependency Spring MVC/Servlet theo BOM và tài liệu Boot tương ứng.

### 6.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: proxyexchange-mvc-lab

demo:
  proxy:
    backend-base-url: http://127.0.0.1:9091
~~~

`demo.proxy.backend-base-url` là **property tự định nghĩa của bài lab**, không phải `spring.cloud.gateway.server.webmvc.routes[0].uri`. Dự án có thể bind property bằng `@ConfigurationProperties` hoặc `@Value`. Điểm đến được cấu hình tập trung và cố định trong controller; không lấy URL từ query/header của client.

### 6.3. Spring Boot application và controller

`src/main/java/demo/proxymvc/ProxyMvcApplication.java`:

~~~java
package demo.proxymvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyMvcApplication.class, args);
    }
}
~~~

`src/main/java/demo/proxymvc/CatalogProxyController.java`:

~~~java
package demo.proxymvc;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CatalogProxyController {

    private final String backendBaseUrl;

    public CatalogProxyController(
            @Value("${demo.proxy.backend-base-url}") String baseUrl) {
        this.backendBaseUrl = baseUrl.replaceAll("/+$", "");
    }

    @GetMapping("/edge/items/{id}")
    public ResponseEntity<?> read(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) throws Exception {

        if (id < 1 || id > 1000000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid item id");
        }

        String upstreamUri = backendBaseUrl + "/items/" + id;

        return proxy
                .uri(upstreamUri)
                .header("X-Proxy-Lab", "mvc-controller")
                .get();
    }
}
~~~

Ở mã trên:

1. `@GetMapping` là **Spring MVC annotated mapping**, không phải một Gateway Server `Path` predicate.
2. Spring Cloud Gateway Proxy Exchange argument resolver tạo/inject `ProxyExchange<byte[]>` cho handler method.
3. Controller tự tạo **upstream URI** và gọi `proxy.uri(...).get()`. Không cần `NettyRoutingFilter` hoặc `RouteDefinitionRouteLocator`.
4. `proxy.header("X-Proxy-Lab", "...")` đặt một header cho **downstream call** theo Java API của ProxyExchange. Nó không phải `AddRequestHeaderGatewayFilterFactory`.
5. Controller kiểm tra `id` dạng số và khoảng hợp lệ để tránh nối nguyên đường dẫn do client tự khai. Với đường dẫn có nhiều phân đoạn tự do, phải xử lý encoding/path traversal kỹ hơn.
6. Generic `byte[]` là loại body đại diện cho downstream response; không nên mặc định bất kỳ endpoint nào cũng phù hợp với việc buffer body lớn trong RAM.

**Ghi chú API:** Package `org.springframework.cloud.gateway.mvc.ProxyExchange` được sử dụng trong các dòng API MVC đã công bố. Tên artifact mới `proxyexchange-webmvc` không có nghĩa mọi lớp Java sẽ đổi sang package `server.mvc`. Khi nâng cấp phiên bản, đối chiếu import từ artifact/Javadoc thực tế.

### 6.4. Vì sao ví dụ cố tình không có Retry, CircuitBreaker?

Chúng ta muốn kiểm chứng cấu trúc nhỏ nhất. Nếu backend lỗi, controller này **không hề thiết lập chính sách Retry/CircuitBreaker**, dù project khác trong tổ chức có route Server áp Retry. Thêm một danh sách filter Server vào YAML không biến `proxy.get()` thành calls có retry budget.

Muốn thêm resilience, phải thiết kế **bên ngoài hoặc quanh downstream call của controller**, thông qua thư viện/phương thức phù hợp với stack và có kiểm thử về timeout, failure policy, idempotency. Không viết vòng lặp vô hạn quanh `proxy.get()` chỉ vì bạn từng dùng `Retry` filter ở Server.

## 7. Lab WebFlux: cùng ý tưởng, kiểu trả về reactive

Nếu ứng dụng là Spring WebFlux/Reactive và muốn dùng **Proxy Exchange WebFlux**, dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình backend URL có thể giống mục 6.2. Nhưng **controller WebFlux không trả trực tiếp `ResponseEntity<?>`**, mà trả `Mono<ResponseEntity<?>>` theo ví dụ chính thức:

~~~java
package demo.proxyflux;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.webflux.ProxyExchange;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCatalogProxyController {

    private final String backendBaseUrl;

    public ReactiveCatalogProxyController(
            @Value("${demo.proxy.backend-base-url}") String baseUrl) {
        this.backendBaseUrl = baseUrl.replaceAll("/+$", "");
    }

    @GetMapping("/edge/items/{id}")
    public Mono<ResponseEntity<?>> read(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) {

        if (id < 1 || id > 1000000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid item id"));
        }

        return proxy
                .uri(backendBaseUrl + "/items/" + id)
                .header("X-Proxy-Lab", "webflux-controller")
                .get();
    }
}
~~~

Đây là **một lựa chọn thay thế riêng** cho Web MVC, không chạy hai controller có cùng path trong một application để “so sánh tự động”. Một project WebFlux không nên vô tình khởi động Servlet Spring MVC do có cả hai web starters.

### 7.1. WebFlux ProxyExchange không bằng ServerWebExchange Gateway

`ProxyExchange` nhận trong annotated controller là một tiện ích để tạo downstream call; nó không biến callback thành:

~~~java
GatewayFilter filter(ServerWebExchange exchange,
                     GatewayFilterChain chain)
~~~

Do đó:

- `GlobalFilter` của **Gateway Server WebFlux** không mặc định chạy quanh annotated controller.
- `RoutePredicateHandlerMapping` không tự tạo route ID cho handler này.
- `spring.cloud.gateway.server.webflux.default-filters` không tự được áp vào `Mono<ResponseEntity<?>>`.
- Khi dùng một `WebFilter` thông thường đúng web stack, filter đó có thể bảo vệ annotated handler **như các handler WebFlux khác**.

`Mono` cũng không có nghĩa auto retry: chỉ khi code sử dụng operator hoặc một thư viện resilience có kiểm soát mới có retry semantics tương ứng. Với HTTP call có side effect, cần phân tích khả năng replay và duplicate.

### 7.2. MVC và WebFlux khác về threading nhưng giống giới hạn cấu hình

| Chi tiết | ProxyExchange MVC | ProxyExchange WebFlux |
| --- | --- | --- |
| Handler | Annotated Spring MVC | Annotated Spring WebFlux |
| Return type thường gặp | `ResponseEntity<?>` | `Mono<ResponseEntity<?>>` |
| HTTP client | Công nghệ HTTP theo bản MVC/Boot, thường blocking | Client reactive theo bản WebFlux |
| Security filter | Servlet/Spring Security filter chain | WebFlux `SecurityWebFilterChain` |
| Controller binding | `@PathVariable`, `@RequestHeader`, `@RequestParam` | Cùng dạng annotations của WebFlux |
| Server route/filter config tự động áp dụng? | Không | Không |

Không dùng `block()` trên event-loop WebFlux để đổi `Mono<ResponseEntity<?>>` thành `ResponseEntity<?>`. Nếu muốn một HTTP proxy streaming lớn, cần đánh giá bộ nhớ, backpressure, timeout và semantics response riêng, không mặc định dùng `ProxyExchange<byte[]>`.

## 8. Backend echo độc lập để quan sát những gì thật sự đến nơi

Ta tạo một Spring Boot MVC backend nhỏ chạy cổng 9091 để kiểm tra request thực tế. Backend không cần biết Gateway Server hay ProxyExchange.

### 8.1. Cấu hình và application

Dependency backend theo Spring Boot MVC của version đang dùng; ví dụ Spring Boot 3.x:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091

spring:
  application:
    name: catalog-backend-proxyexchange-lab
~~~

`src/main/java/demo/catalog/CatalogApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 8.2. Backend controller

`src/main/java/demo/catalog/CatalogController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final AtomicLong totalCalls = new AtomicLong();

    @GetMapping("/items/{id}")
    public ResponseEntity<Map<String, Object>> read(
            @PathVariable long id,
            HttpServletRequest request) {

        long attempt = totalCalls.incrementAndGet();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("backend", "catalog-backend");
        body.put("id", id);
        body.put("path", request.getRequestURI());
        body.put("proxyMarker",
                request.getHeader("X-Proxy-Lab"));
        body.put("hasAuthorization",
                request.getHeader("Authorization") != null);
        body.put("hasCookie",
                request.getHeader("Cookie") != null);
        body.put("backendCallsSinceStart", attempt);

        if (id == 503) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .header("X-Backend-State", "temporary-error")
                    .body(body);
        }

        return ResponseEntity.ok()
                .header("X-Backend-State", "healthy")
                .body(body);
    }
}
~~~

Backend cố tình chỉ trả **boolean có/không** cho Authorization/Cookie, **không echo giá trị token hoặc cookie** vào response. Bộ đếm `AtomicLong` chỉ phục vụ lab trong **một process**, không phải metric production hay số attempts toàn cụm.

Endpoint với ID 503 luôn trả HTTP 503 để ta kiểm tra phản ứng của proxy. Việc client nhận đúng 503 hay có lỗi bọc lại tùy cách HTTP client/proxy xử lý lỗi trong bản dùng; mục đích quan trọng là xác minh **số backend calls** và không suy đoán auto Retry.

### 8.3. Chạy hai ứng dụng

Trong hai terminal tương ứng:

~~~bash
# Terminal 1: project catalog-backend
./mvnw spring-boot:run

# Terminal 2: project proxyexchange-mvc (hoặc proxyexchange-webflux)
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run` hoặc Maven đã cài. Đây là code thực hành để người học tự chạy; **bài không tuyên bố đã thực hiện build hoặc test trong repository**.

### 8.4. Thử backend trực tiếp

~~~bash
curl -i "http://127.0.0.1:9091/items/42"
~~~

Kỳ vọng HTTP 200 với body có `"id":42`, `"path":"/items/42"`. Vì bypass controller proxy, trường `proxyMarker` sẽ là `null`.

Khi gọi `/items/503` trực tiếp, backend trả 503. Dùng đường này để tách lỗi backend khỏi lỗi chọn route/ProxyExchange controller.

## 9. Kiểm thử đúng đường đi, không dựa vào YAML Server

### 9.1. Gọi qua ProxyExchange controller

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/42"
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Backend-State: healthy

{"backend":"catalog-backend","id":42,"path":"/items/42",
 "proxyMarker":"mvc-controller","hasAuthorization":false,
 "hasCookie":false,"backendCallsSinceStart":2}
~~~

Trường `backendCallsSinceStart` có thể khác 2 nếu người học chưa gọi trực tiếp hoặc có thêm traffic. **Không assert một giá trị cố định**; kiểm tra bằng chênh lệch trước/sau.

Hai bằng chứng mạnh hơn status 200:

- `path=/items/42`: controller tự tạo URI downstream, không cần `StripPrefix`.
- `proxyMarker=mvc-controller`: header được đặt bằng `proxy.header(...)`, không phải bằng `AddRequestHeaderGatewayFilterFactory`.

Nếu dùng **WebFlux ProxyExchange**, marker tương ứng là `webflux-controller`.

### 9.2. Kiểm tra giới hạn mapping của annotated handler

~~~bash
# Không có @PostMapping, nên không phải một proxy POST tự do:
curl -i -X POST "http://127.0.0.1:8080/edge/items/42"

# ID không chuyển được thành long:
curl -i "http://127.0.0.1:8080/edge/items/not-a-number"

# ID ngoài giới hạn định nghĩa ở controller:
curl -i "http://127.0.0.1:8080/edge/items/0"
~~~

Kỳ vọng: request không khớp method hoặc sai kiểu/range bị từ chối bởi mapping/binding/controller. Mã chính xác có thể là 400/405/404 tùy version và handlers khác. **Chúng không chứng minh Gateway Server Path/Method predicates đang chạy**.

### 9.3. Test chống giả định auto filter

Trong **một dự án chỉ có ProxyExchange module** như lab, thêm Server `default-filters`:

~~~yaml
# Cố ý dùng để kiểm chứng: KHÔNG phải policy cho ProxyExchange controller
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - AddResponseHeader=X-Expected-Server-Filter,applied
~~~

Chạy lại:

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/42"
~~~

Không được **coi `X-Expected-Server-Filter` là header bắt buộc** trên response controller, vì đây là config Server WebFlux, trong khi lab chạy ProxyExchange MVC/WebFlux controller. Nếu header vẫn xuất hiện, kiểm tra xem **có Server starter/route khác, filter khác hoặc reverse proxy đã thêm header**. Luôn xác minh **nguồn tạo header**, không chỉ xem giá trị.

### 9.4. Test “Retry mặc định” bằng backend có mã lỗi

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/503"
~~~

Backend cố tình trả lỗi. Hãy quan sát field `backendCallsSinceStart` và logs backend. **Không có Retry trong code controller**, nên không thể coi `retries: 2` viết dưới Server route YAML là lời hứa proxy này sẽ có ba backend attempts.

Nếu mã lỗi trên response proxy khác 503 do HTTP client/error handler của version, tách **error translation** khỏi **retry**: một exception được biến đổi thành HTTP 500/502 cũng không có nghĩa đã có thêm attempts.

### 9.5. Query parameters không tự là “RewritePath”

Trong lab, controller chủ động tạo URL:

~~~java
String upstreamUri = backendBaseUrl + "/items/" + id;
~~~

Nếu client gọi `/edge/items/42?lang=vi`, đoạn mã trên **không tự thêm `lang=vi` vào URL**. Đừng suy rằng ProxyExchange mặc định sẽ chuyển mọi query/path giống một Gateway Server route có `PreserveHostHeader` hoặc `RewritePath`.

Muốn truyền query parameters, cần thiết kế rõ **danh sách được phép**, URL encoding, default values và giới hạn. Ví dụ dùng `UriComponentsBuilder` để ghép một parameter được khai báo qua `@RequestParam`, thay vì nối nguyên raw query string không kiểm tra. Nếu downstream có phân quyền theo query/resource, phải đảm bảo không có parameter pollution hoặc duplicate keys ngoài ý muốn.

## 10. Request/response headers: cơ chế ProxyExchange khác FilterFactory

Một điểm dễ gây lỗi bảo mật là nghĩ `ProxyExchange` sẽ sao chép nguyên mọi HTTP header giống một reverse proxy được cấu hình bằng Gateway Server.

Tài liệu Proxy Exchange nêu **các nhóm header được xử lý đặc biệt**:

| Nhóm | Giá trị mặc định được tài liệu mô tả | Vì sao |
| --- | --- | --- |
| **Sensitive** | `Cookie`, `Authorization` | Tránh vô tình chuyển credential/client session tới backend ngoài ý muốn |
| **Skipped** | `Content-Length`, `Host` | HTTP client đến backend có thể đổi body length/transfer-encoding/authority |
| **Proxy headers** | `X-Forwarded-*` | Có hỗ trợ xử lý thông tin proxy theo cơ chế riêng |

Đây là behavior được tài liệu Proxy Exchange mô tả cho downstream call **mặc định**; khi tự sửa `sensitive()`, `header()`, cấu hình properties hay HTTP client, cần kiểm tra lại behavior cụ thể.

### 10.1. `proxy.header(...)` có phải AddRequestHeaderGatewayFilterFactory?

Không. Với ProxyExchange MVC, Java API có:

~~~java
proxy.header("X-Proxy-Lab", "mvc-controller");
~~~

API này đặt header cho **downstream call**. Nó được gọi **trực tiếp trong controller**, không cần route ID hay `GatewayFilterChain`. Khái niệm nghiệp vụ giống thao tác “thêm header cho request” của Gateway Server, nhưng **đường thực hiện khác nhau**.

Để thay response gửi client, ProxyExchange còn có các overload HTTP methods nhận **mapper**:

~~~java
// Mẫu minh họa: responseMapper chuyển response downstream
// thành response trả client, phù hợp khi cần chỉnh header/status.
return proxy.uri("http://127.0.0.1:9091/items/42")
        .get(response -> ResponseEntity
                .status(response.getStatusCode())
                .headers(response.getHeaders())
                .header("X-Proxy-Response", "mapped")
                .body(response.getBody()));
~~~

Đoạn minh họa trên dùng Java API của MVC ProxyExchange và Spring `ResponseEntity`. Nếu build với phiên bản có generic method signatures khác, cần đối chiếu Javadoc tương ứng. Khi copy downstream headers, đặc biệt lưu ý **hop-by-hop headers** và `Content-Length/Transfer-Encoding` không còn phù hợp nếu body hoặc encoding thay đổi. Không tự sao chép các headers xung đột để đổi status/body.

### 10.2. Không relay Authorization một cách mù quáng

Client có thể mang:

~~~http
Authorization: Bearer eyJ...
Cookie: SESSION=...
X-Forwarded-For: 203.0.113.77
~~~

Nếu frontend gửi token dùng để truy cập Gateway, backend có thể cần **token khác** với audience/scope riêng. Việc không forward `Authorization`/`Cookie` mặc định của ProxyExchange giúp tránh một số rò rỉ, nhưng **không tạo ra hệ thống ủy quyền**. Không thay `sensitive()` bằng danh sách rỗng chỉ để “làm backend gọi được” nếu chưa kiểm tra audience, scope, issuer và trust boundary.

Phương án an toàn hơn khi cần downstream identity:

1. Spring Security xác thực client ở web stack tương ứng.
2. Xác định backend nào cần danh tính hoặc delegated token.
3. Dùng cơ chế token exchange/client credentials/authorized client **có chủ đích**.
4. Không đưa raw token vào URL, log, response hoặc metric label.
5. Backend vẫn xác minh quyền đối với resource quan trọng.

**Không mặc định dùng Server `TokenRelay` filter** cho ProxyExchange controller: nó không tự được gắn vào annotated handler. Cần tích hợp OAuth2/Spring Security riêng, rồi kiểm thử thực tế header tới backend.

### 10.3. Host và Content-Length không được sao chép tùy ý

HTTP downstream call có thể có authority/port/scheme khác frontend; gán nguyên header `Host` của client có thể sai virtual-host routing hoặc làm backend tin nhầm origin. Tương tự, nếu body được serialize lại thành dạng khác hoặc gửi chunked, `Content-Length` gốc có thể sai.

Không tạo custom controller kiểu:

~~~java
// SAI về ý tưởng, không phải API gợi ý:
// for (var header : incomingHeaders) proxy.header(header);
~~~

Việc sao chép nguyên mọi header có thể truyền:

- Credential không đúng audience.
- `Connection` và các hop-by-hop headers.
- `Content-Length`/`Transfer-Encoding` không nhất quán.
- Header identity/tenant do client giả mạo.
- Forwarding metadata không đáng tin.

Dùng allowlist hoặc policy có danh sách loại trừ rõ ràng, dựa trên contract backend và trust boundary.

### 10.4. Forwarded/X-Forwarded-* vẫn phải kiểm tra proxy đáng tin

ProxyExchange có hỗ trợ `X-Forwarded-*`, nhưng **không nên coi mọi `X-Forwarded-For` là IP thật**. Nếu edge/ingress không xóa giá trị client tự gửi, một kẻ tấn công có thể tạo:

~~~http
X-Forwarded-For: 10.0.0.1
X-Forwarded-Proto: https
X-Forwarded-Host: admin.internal
~~~

Vì vậy, khi cần IP/trusted scheme/host để audit, rate limit hoặc redirect:

- Cô lập các đường vào Gateway, không cho client bypass ingress.
- Cho reverse proxy tin cậy làm sạch/ghi đè forwarding headers.
- Cấu hình trusted proxies theo cơ chế **WebFlux/MVC ProxyExchange và Spring Framework** thực tế, không bê properties của Server.
- Không dùng `X-Forwarded-Host` client tự khai để tạo redirect hoặc downstream URI.
- Test request giả mạo từ bên ngoài và kiểm tra backend nhận dữ liệu đúng.

Tài liệu Spring Cloud còn có các bản cập nhật bảo mật forwarding headers theo phiên bản. Sau upgrade, hành vi mặc định có thể thay đổi; không dựa vào ví dụ cũ để mở rộng trust.

## 11. Thay thế chính sách Server route/filter một cách có chủ đích

ProxyExchange là công cụ HTTP proxy **trong controller**, nên nếu cần cross-cutting behavior, hãy xác định lớp xử lý thật:

| Yêu cầu | Cách tiếp cận cho ProxyExchange | Vì sao không chỉ đặt Server filter? |
| --- | --- | --- |
| Chặn caller chưa xác thực | Spring Security `SecurityFilterChain` MVC hoặc `SecurityWebFilterChain` WebFlux | Server auth filter không tự bao annotated handler |
| Phân quyền theo tenant/item | Controller/service + Security authorization | Resource permission cần ngữ cảnh nghiệp vụ |
| Giới hạn request client | Servlet Filter, WebFilter, Bucket4j hoặc service quota được tích hợp chủ động | `RequestRateLimiter` của Server không tự chạy |
| Circuit breaker downstream | Resilience4j/Spring Cloud CircuitBreaker quanh HTTP client call, có fallback | Không có Server CircuitBreaker filter chain cho controller |
| Retry GET có kiểm soát | Retry riêng cho HTTP client, giới hạn attempts/deadline | Server Retry filter không tự được invoke |
| Đổi downstream path/header | Controller + ProxyExchange API + URI builder an toàn | Server `RewritePath/SetPath` không thay controller URI |
| CORS | Spring MVC/WebFlux CORS + Security policy | Server CORS route config không tự là policy controller |
| Service discovery | Dùng LoadBalancer client/DiscoveryClient qua tích hợp chủ động | Không tự biến `proxy.uri("lb://...")` thành Server LB routing |
| Observability | Micrometer/HTTP server metrics, HTTP client metrics, tracing chủ động | Không tự có route tags/counters từ Server route ID |
| Route refresh | Cấu hình riêng hoặc deploy/controller strategy | `RefreshRoutesEvent` không recompile `@GetMapping` |

### 11.1. Ví dụ Spring Security MVC chặn các request chưa đăng nhập

Nếu API cần bảo vệ toàn bộ `/edge/items/**`, một chiến lược là cấu hình Servlet Security:

~~~java
package demo.proxymvc.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/edge/items/**").authenticated()
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đây là **ví dụ Security có mục đích**, chỉ chạy khi thêm Spring Security resource-server dependencies và cấu hình issuer/JWKs, audience/validation, keys phù hợp. Không dùng đoạn này nguyên trạng mà chưa có IdP/test tokens. Security chain ở tầng Servlet có thể bao annotated controller **dù không cài Gateway Server MVC**.

**Không tuyên bố** Spring Security tự bật mọi policy mong muốn: phải có rules tương ứng, không mở `anyRequest().permitAll()` rồi nghĩ ProxyExchange tự có `TokenRelay` hoặc Gateway Server auth filters.

### 11.2. Ví dụ tương ứng cho Spring WebFlux

~~~java
package demo.proxyflux.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http.authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET,
                        "/edge/items/**").authenticated()
                .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

`SecurityWebFilterChain` bảo vệ annotated WebFlux handler theo matching policy của Spring Security. Nó **không phải** `GlobalFilter` của Gateway Server WebFlux. Hai ví dụ MVC/WebFlux khác nhau về imports, lifecycle và web stack; dùng đúng một ví dụ cho loại ứng dụng của bạn.

### 11.3. Thêm rate limiting và circuit breaker không nên “mô phỏng bằng boolean”

Một đoạn code:

~~~java
// PSEUDOCODE — các helper dưới đây phải được triển khai thật.
quotaPolicy.check(authenticatedPrincipal, "catalog-read");
return circuitBreaker.execute(
        () -> proxy.uri(fixedBackendUri).get());
~~~

chỉ minh họa **vị trí logic**. Nó chưa trở thành một RateLimiter/circuit breaker hoạt động, cũng chưa nói rõ 429/503, key uniqueness, timeouts, thread safety và state toàn cụm.

Khi tự tích hợp:

1. **Rate limit key** lấy từ principal/client/tenant đã xác thực hoặc IP qua trusted proxy; không tin header tự khai.
2. **State phân tán** dùng Redis/adapter phù hợp nếu nhiều ProxyExchange replicas. Local limiter độc lập chỉ có quota per-replica.
3. **Quota exceeded** trả 429; **quota store unavailable** cần policy fail-open/closed/degrade riêng, không mập mờ 429.
4. Circuit breaker fallback phải xử lý đúng semantics của downstream failure, không biến lỗi thật thành HTTP 200 bất kể contract.
5. Retry với POST/PUT/PATCH cần idempotency key bền vững ở backend; retry có thể nhân số downstream calls và giữ body lâu hơn.
6. Với WebFlux, không gọi blocking HTTP client trên event-loop; với MVC, không giữ Servlet request threads vô hạn.

Nếu những yêu cầu trên xuất hiện ở hàng trăm API/routes với chính sách lặp lại, đó là tín hiệu nên **chuyển sang Gateway Server** hoặc tạo một abstraction có tests/reuse đủ mạnh, thay vì nhân bản code ở mỗi controller.

## 12. Discovery, lb://, path rewriting và controller routes

### 12.1. `lb://service-id` không phải URI HTTP thông thường

Với Server Gateway, `lb://orders-service` có thể được một **LoadBalancer filter/routing integration** diễn giải. Nhưng ProxyExchange controller làm việc bằng HTTP client; một lệnh:

~~~java
// Không được coi là đủ để tự có Server LB filter:
proxy.uri("lb://orders-service/items/42").get();
~~~

**Không bảo đảm** được xử lý giống Server `lb://` route, vì không có Server LoadBalancer filter chain trên annotated controller. Kết quả có thể là scheme không được HTTP client hỗ trợ, trừ khi bạn đã cấu hình **một client/load-balancer integration rõ ràng**.

Các phương án:

- Chọn HTTP(S) upstream cố định qua configuration, như lab.
- Inject `DiscoveryClient` / `ReactiveDiscoveryClient` rồi chọn service instance theo chiến lược an toàn, nếu thực sự muốn tự quản lý discovery.
- Dùng một `@LoadBalanced` HTTP client có load-balancer integration phù hợp khi được tài liệu Spring Cloud hỗ trợ.
- Nếu việc route theo service ID và các điều kiện path/header là trọng tâm, dùng Gateway Server với discovery locator và load balancer filters.

Không tự chọn instance bằng `instances.get(0)` rồi gọi là production load balancing: phải xét health, zone, connection pool, retry và instance churn.

### 12.2. Path rewrite khác `proxy.path(...)`

Gateway Server có các built-in `RewritePath`, `StripPrefix`, `SetPath`. ProxyExchange cung cấp helper như `proxy.path(prefix)` để lấy phần path sau prefix; nhưng gọi helper này **không tự đăng ký Server RouteDefinition** và không tự áp tất cả behavior regex/route template của Server.

Ví dụ tài liệu:

~~~java
@GetMapping("/proxy/path/**")
public ResponseEntity<?> proxyPath(ProxyExchange<byte[]> proxy)
        throws Exception {
    String suffix = proxy.path("/proxy/path/");
    return proxy.uri(
            "http://127.0.0.1:9091/items/" + suffix).get();
}
~~~

Ví dụ này chỉ để hiểu `proxy.path(prefix)`; nếu đường dẫn suffix lấy từ client:

- Kiểm soát path traversal, percent-encoding, slash/backslash, ký tự Unicode đặc biệt.
- Không cho raw path đổi host/scheme hoặc thêm query/fragment ngoài policy.
- Dùng URI builder/allowlist và tests cho `%2F`, `..`, repeated slashes.
- Nếu API chỉ dùng ID dạng số, hãy ưu tiên `@PathVariable long id` như lab.

### 12.3. Header rewriting không tự là trust boundary

Một ProxyExchange controller có thể thêm:

~~~java
proxy.header("X-Route-Tag", "catalog");
~~~

Nhưng nếu backend tin `X-Tenant-Id` hoặc `X-Authenticated-User`, cần **xóa giá trị giả từ client và set giá trị từ authentication context đã xác minh**; không chỉ append. Việc kiểm tra headers phía backend trong integration test là bắt buộc cho policy nhạy cảm.

## 13. Actuator, route refresh và dynamic configuration: phạm vi khác

Gateway Server thường có:

~~~text
RouteDefinitionRepository/Locator
  → RouteDefinitionRouteLocator
  → CachingRouteLocator
  → Gateway filter chain

RefreshRoutesEvent / POST /actuator/gateway/refresh
  → yêu cầu dựng lại Server routes runtime
~~~

Annotated ProxyExchange controller thường có:

~~~text
Spring @RequestMapping metadata
  → Spring MVC/WebFlux handler mapping
  → controller method
  → proxy.uri(...).get()
~~~

**`RefreshRoutesEvent` là event của Gateway Server**, không tự thay đổi annotation `@GetMapping("/edge/items/{id}")`, không recompile controller và không tự đưa Server `default-filters` vào `ProxyExchange`.

### 13.1. Cái gì xảy ra khi đổi `demo.proxy.backend-base-url`?

Property lab:

~~~yaml
demo:
  proxy:
    backend-base-url: http://127.0.0.1:9091
~~~

được inject vào controller khi Spring tạo bean. Việc sửa `application.yml` trên đĩa sau startup **không tự khiến field trong bean đổi**. Cần redeploy/restart hoặc một cơ chế configuration refresh/application logic được thiết kế rõ ràng, có validation và rollback. Gửi `RefreshRoutesEvent` không phải câu trả lời mặc định.

### 13.2. `/actuator/gateway/routes` có phản ánh annotated controllers không?

Endpoint này chủ yếu dùng để quan sát các routes của **Gateway Server** khi endpoint Server Actuator được bật. Nó không phải danh mục chung cho tất cả `@GetMapping` hay `ProxyExchange` handlers.

Với annotated Spring handlers, Actuator **`/actuator/mappings`** (khi được expose có kiểm soát) là nguồn thích hợp hơn để kiểm tra mappings. Nhưng endpoint mappings **không tự trả ra destination URI động mà controller ghép trong Java** hoặc đảm bảo mọi security rule/timeout đang đúng.

Không bật `management.endpoints.web.exposure.include="*"` trên Internet để điều tra thiếu route. Chỉ expose các endpoint cần thiết trên management port riêng và bảo vệ bằng authentication/RBAC.

### 13.3. Khi cả Server và ProxyExchange được cài trong cùng app

Đây là trường hợp có thể nhưng khó quan sát:

~~~text
Gateway Server route:  Path=/api/**
ProxyExchange controller: @GetMapping("/api/catalog/{id}")
~~~

Một request có thể bị handler mapping của Server hoặc controller chiếm trước tùy web stack, cấu hình và order. Khi debug:

1. Đọc active Spring Boot web application type và các auto-configurations.
2. Ghi tên controller handler hoặc Server route ID đã xử lý request.
3. Dùng paths riêng trong integration tests để chứng minh hai pipeline.
4. Không giả định Server filters được thực hiện trước controller chỉ vì request path giống nhau.
5. Nếu chọn một flavor cho service, loại bỏ những starter không cần thiết để giảm nhầm lẫn.

Một ứng dụng có thể đồng thời dùng Servlet Filter/WebFlux WebFilter và một Server route filter — nhưng **sự tồn tại của cùng web stack không đồng nghĩa annotated controller đi qua Server route filter**.

## 14. Khi ProxyExchange gặp lỗi: status, timeout và memory không có “mặc định Gateway Server”

### 14.1. Hết quota khác upstream 503

Giả sử API cần giới hạn 20 requests/giây theo principal, trong khi backend đôi khi trả 503. Nếu dùng Gateway Server WebFlux, một route có thể tích hợp `RequestRateLimiter` và `Retry` với policy rõ ràng. Với ProxyExchange controller:

~~~text
Client
  ↓
Spring Security (xác thực/phân quyền nếu cấu hình)
  ↓
Controller (validate id, enforce quota nếu code có thực hiện)
  ↓
ProxyExchange GET downstream
  ↓
Backend trả 200 / 404 / 503
  ↓
Controller/HTTP client phản hồi client
~~~

Những gì chưa được lập trình **không xảy ra chỉ vì có tên filter trong tài liệu Server**. Cần phân biệt:

| Điều kiện | Response/policy mong muốn | Thành phần chịu trách nhiệm |
| --- | --- | --- |
| Principal không đủ quyền | 401/403 | Spring Security, backend authorization |
| Caller vượt quota | 429 | Limiter được tích hợp có chủ đích |
| Quota store lỗi, không xác định được quota | 503/fail-open có kiểm soát theo policy | Quota component của ứng dụng |
| Backend trả 503 | Có thể relay 503 hoặc error mapping thích hợp | HTTP client/ProxyExchange/controller/error handler |
| Backend unreachable, connect timeout | 5xx có phân loại, log/metric, deadline | HTTP client configuration và exception handling |
| Backend đã ghi dữ liệu nhưng response đứt | Không retry mù quáng | Idempotency contract và retry policy |

Không “sửa” mọi exception thành 429 hay 200 vì sẽ khiến monitoring và client hiểu sai trạng thái hệ thống.

### 14.2. HTTP client timeout không đồng nghĩa Retry filter timeout

Server Gateway có các timeout properties và một số filter riêng cho route. ProxyExchange sử dụng HTTP client bên dưới theo web stack/version. Vì vậy, những ví dụ kiểu:

~~~properties
# KHÔNG giả định đây là timeout của ProxyExchange controller:
spring.cloud.gateway.server.webflux.httpclient.connect-timeout=1000
~~~

không tự đặt connect timeout cho một ProxyExchange MVC HTTP client. Với MVC cần xác định client/request factory tương ứng và cấu hình connection/read timeouts; với WebFlux cần HTTP connector/response timeout phù hợp. Khi thay đổi implementation, kiểm thử cả DNS failure, connect timeout và response-body read timeout.

### 14.3. Quản lý body lớn

`ProxyExchange<byte[]>` thuận tiện cho response có kích thước vừa phải, nhưng mảng byte có thể phải giữ toàn bộ payload trong bộ nhớ. Nếu 200 requests đồng thời, mỗi response 4 MiB, mô hình payload đơn giản đã là:

\[
M_{\mathrm{payload}}\approx 200\times 4\,\mathrm{MiB}
=800\,\mathrm{MiB}
\]

Đây **không phải số đo heap thực tế**: còn bộ nhớ HTTP client, headers, TLS buffers, copies, GC và các đối tượng khác. Với ProxyExchange WebFlux, việc dùng reactive `Mono` không tự bảo đảm proxy file download lớn là streaming không buffer; loại body `byte[]` và implementation cụ thể vẫn quyết định.

Nếu API xử lý upload/download lớn, SSE/WebSocket hay streaming request/response:

- Chọn cơ chế streaming được tài liệu và version hỗ trợ, không tự giữ byte array lớn.
- Cấu hình giới hạn request size và concurrency.
- Không retry request body có side effect hoặc không thể replay.
- Kiểm thử hủy request, downstream disconnect và memory/direct buffers.
- Khi nhu cầu là reverse proxy streaming tổng quát, đánh giá Gateway Server hoặc reverse proxy chuyên dụng.

### 14.4. Error mapping và response headers

HTTP client dưới ProxyExchange có thể xử lý 4xx/5xx và network exceptions khác nhau theo bản thư viện. **Không dựa vào giả định rằng mọi lỗi luôn được chuyển thẳng thành ResponseEntity cùng status**.

Một hệ thống production nên kiểm thử:

- Downstream trả 404 có body.
- Downstream trả 429 có `Retry-After`.
- Downstream trả 503, rồi phục hồi.
- Kết nối refused/timeout/TLS handshake failed.
- Downstream trả redirect, 204 No Content hoặc response malformed.
- Client hủy request trước khi backend trả.

Kiểm tra response mapping không tự sao chép những headers gây xung đột: hop-by-hop headers, `Content-Length` sau biến đổi body hoặc `Location` trỏ domain nội bộ.

## 15. Kiểm thử âm để chứng minh chính sách Server *không* tự áp

Một bài test tốt phải chứng minh được **tầng xử lý** chứ không chỉ thấy HTTP 200.

### 15.1. Ma trận test tối thiểu

| Case | Input / thao tác | Quan sát cần đạt |
| --- | --- | --- |
| P01 | Gọi backend `:9091/items/42` trực tiếp | Backend chạy, không có marker ProxyExchange |
| P02 | Gọi `:8080/edge/items/42` | Backend thấy path `/items/42` và marker do controller thêm |
| P03 | POST vào GET-only annotated handler | Không biến thành proxy POST tự do |
| P04 | Gửi ID không phải số hoặc ID âm/0 | Binding/validation của annotated handler từ chối |
| P05 | Thêm Server `default-filters` trong app chỉ có ProxyExchange | Không mặc định xuất hiện response header từ filter Server |
| P06 | Thêm Server `Retry` config, gọi backend ID 503 | Không giả định có additional backend attempts |
| P07 | Gửi query parameter chưa được controller truyền | Không mặc định được rewrite/forward như Server route |
| P08 | Gửi `Authorization`/`Cookie` thử nghiệm | Backend không nhận credential theo default sensitive policy; kiểm tra theo version |
| P09 | Gửi `X-Forwarded-For` giả từ client | Không được sử dụng làm trusted client IP |
| P10 | Bật security đúng stack rồi gọi anonymous | Bị chặn theo policy của Security chain |
| P11 | Không cài Gateway Server starter nhưng gọi `/actuator/gateway/routes` | Không dùng endpoint này để khẳng định controller có/không |
| P12 | Chỉnh YAML Server routes nhưng không sửa controller | Annotated handler không tự đổi destination |
| P13 | Cùng app có cả Server route và controller trùng path | Xác minh handler thực bằng tracing/log, không suy từ status |
| P14 | Backend unreachable | Có timeout và error mapping, không treo request |
| P15 | Tải concurrent với response body lớn | Memory và latency nằm trong giới hạn |

Các test được phân biệt rõ giữa **default behavior** và **custom integration**: nếu ứng dụng có `Servlet Filter` hoặc `WebFilter` riêng, nó có thể gắn header/rate limit cho controller, không phải do Gateway Server route filters.

### 15.2. cURL kiểm tra sensitive headers (chỉ dùng dữ liệu giả)

~~~bash
curl -i "http://127.0.0.1:8080/edge/items/42" \
  -H "Authorization: Bearer LAB_FAKE_TOKEN_NOT_REAL" \
  -H "Cookie: lab=session-placeholder" \
  -H "X-Forwarded-For: 203.0.113.55"
~~~

Trong cấu hình ProxyExchange mặc định theo tài liệu, backend echo kỳ vọng:

~~~json
{
  "hasAuthorization": false,
  "hasCookie": false
}
~~~

Đây là **kỳ vọng dựa trên behavior documented**, không phải cam kết nếu code đã custom header policy hoặc dùng version/client khác. Không ghi token thật vào terminal history/log. Backend trong ví dụ chỉ echo boolean, không phơi lộ nội dung credential.

### 15.3. Chẩn đoán bằng mapping thay vì route ID

Trong ứng dụng annotated handler, có thể:

1. Ghi log điểm vào controller bằng một correlation ID đã làm sạch.
2. Xem mappings của Spring MVC/WebFlux (nếu Actuator mappings được bật trên management plane an toàn).
3. Đọc HTTP client logs/metrics cho downstream URL **sau khi lọc secrets**.
4. So đường dẫn/header đến backend.
5. Tách response do backend trả với response do exception handler tạo.

Không vội gỡ lỗi từ `/actuator/gateway/routes` nếu project không dùng Gateway Server routes.

## 16. Troubleshooting những lỗi xuất hiện khi áp nhầm tài liệu Server

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Header `AddResponseHeader` không xuất hiện | Đang gọi ProxyExchange controller, không phải Server route | Xem handler mapping, tìm nơi header được tạo |
| `RewritePath` không đổi backend path | Controller tự ghép URL | Đọc `proxy.uri(...)`, echo backend path |
| Retry không chạy dù `retries: 2` | Retry filter thuộc Server route khác | Log backend call count; xem retry implementation quanh ProxyExchange |
| RedisRateLimiter properties có nhưng vẫn vượt quota | Không có `RequestRateLimiter` pipeline | Kiểm tra limiter controller/Servlet Filter/WebFilter thật |
| `lb://orders-service` gây lỗi scheme/URI | Không có Server LoadBalancer filter | Xác định HTTP client/load-balancer integration |
| Spring Security hoạt động nhưng TokenRelay Server không | Security chain không tự chạy Server token relay | Thiết kế token forwarding theo backend audience |
| Đổi `spring.cloud.gateway.server.webflux.routes` không đổi controller | Annotated mapping và controller destination độc lập | Kiểm tra dependency/source of truth |
| Gửi `RefreshRoutesEvent` nhưng URL controller không đổi | Event chỉ refresh route cache Server | Kiểm tra config bean/controller refresh strategy |
| `/actuator/gateway/routes` rỗng, API Proxy vẫn chạy | Controller không nằm trong Server Route inventory | Dùng Actuator mappings và endpoint smoke test |
| Backend mất Authorization | Sensitive headers bị lọc theo ProxyExchange | Xem auth delegation contract; đừng bật pass-through bừa |
| Backend nhận `X-Forwarded-For` giả | Edge không sanitize forwarding metadata | Kiểm tra proxy trust boundary |
| POST payload bị thay Content-Length | HTTP client có thể đổi body/encoding | Không forward nguyên Content-Length/Host |
| 503 tới client nhưng backend chỉ thấy một call | Không có retry (hoặc không match policy) | Phân biệt status mapping với attempt count |
| Memory tăng khi file download | `byte[]` body và concurrent requests | Đo RSS/heap/direct memory và streaming strategy |
| Controller bị 404 khi route Server vẫn tồn tại | HandlerMapping precedence hoặc route conflict | Tách paths và kiểm chứng handler thực |
| CORS preflight lỗi | MVC/WebFlux CORS và Security không được cấu hình đúng | Kiểm tra OPTIONS và allowed origins/methods |

**Cách gỡ lỗi hệ thống:** Xác định `flavor → web stack → handler mapping → downstream client → security/filter boundary` theo thứ tự. Không tùy tiện cài thêm cả Server starter để “sửa thiếu header”; điều đó có thể tạo đường routing mới và làm chẩn đoán khó hơn.

## 17. Khi nào nên giữ ProxyExchange, khi nào chuyển sang Gateway Server?

### 17.1. Quyết định dựa trên quy mô chính sách

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ 1–3 endpoints proxy tùy biến ngay trong ứng dụng web hiện có | **ProxyExchange** | Gần business code, ít infrastructure route machinery |
| Một endpoint tổng hợp dữ liệu từ nhiều backend | Controller/service + HTTP client, có thể dùng ProxyExchange cho một số calls | Cần logic nghiệp vụ hơn là transparent reverse proxy |
| Hàng trăm routes với path/header predicates, route filters giống nhau | **Gateway Server** | Dùng route definitions và filter factories thống nhất |
| Dynamic route updates, live route inventory, route refresh | **Gateway Server** | Route repository/cache/actuator phù hợp hơn |
| Quota theo tenant/route, circuit breaker/retry/filter thứ tự phức tạp | Thường **Gateway Server** hoặc abstraction rõ ràng | Giảm duplicate policy implementation |
| Download/upload/streaming rất lớn, long-lived connections | Đánh giá Gateway Server hoặc proxy chuyên dụng | Cần memory, timeout, streaming semantics phù hợp |
| Ứng dụng đã có MVC Servlet Security Filter chain và cần 1 đường proxy có logic riêng | **ProxyExchange MVC** có thể hợp lý | Tái sử dụng authentication/authorization đã được kiểm soát |
| Phần lớn app chạy WebFlux reactive annotated controllers | **ProxyExchange WebFlux** có thể hợp lý cho số endpoint nhỏ | Giữ reactive programming model |
| Cần WebMvc.fn route-specific Before/After/HandlerFilterFunction | **Gateway Server Web MVC** | Không phải ProxyExchange MVC annotated handler |

Không có lựa chọn “đúng cho mọi hệ thống”. Quan trọng là **không quảng cáo tính năng của một flavor như thể flavor kia sở hữu pipeline đó**.

### 17.2. Luồng quyết định

~~~mermaid
flowchart TD
    A["Cần chuyển tiếp HTTP request?"] --> B{"Cần route inventory,<br/>nhiều predicates/filters, dynamic routes?"}
    B -->|"Có"| S["Ưu tiên Gateway Server phù hợp WebFlux/MVC"]
    B -->|"Không"| C{"Có controller cần business logic riêng?"}
    C -->|"Có"| P["Cân nhắc ProxyExchange trong annotated handler"]
    C -->|"Không"| D["Cân nhắc Gateway Server hoặc reverse proxy đơn giản"]
    P --> E["Thiết kế riêng AuthN/AuthZ, rate limit,<br/>timeout, resilience, header trust"]
    S --> F["Cấu hình route/filter theo đúng flavor và version"]
    E --> T["Integration tests chứng minh policy"]
    F --> T
~~~

### 17.3. Chuyển từ ProxyExchange sang Gateway Server: những gì phải di trú

Nếu dự án phát triển từ hai controllers thành hàng trăm tuyến:

1. Liệt kê **mọi annotated mappings** cần proxy, method/path/query và logic tự viết trong controller.
2. Chuyển route/URI sang **Server RouteDefinition/Java Routes API** phù hợp web stack, nhưng không nhân đôi path với controller khi rollout.
3. Map từng chức năng controller sang predicate/filter tương ứng; kiểm tra khác biệt **body, headers, status và forwarded metadata**.
4. Đặc biệt xem lại default sensitive headers: ProxyExchange có thể loại bỏ `Authorization`/`Cookie`, trong khi policy Server không nhất thiết giống vậy. **Đừng vô tình truyền credentials sang backend khi migration.**
5. Giữ authentication và backend authorization theo cùng trust boundary.
6. Thiết kế retry, circuit breaker, rate limiter và quota key rõ ràng thay vì sao chép default.
7. Test với traffic mirror/canary, phân biệt response 4xx/5xx do tầng nào tạo.
8. Kiểm tra service discovery, LoadBalancer, URI rewriting và Host/Proto trước rollout.
9. Chỉ loại bỏ controller cũ sau khi contract/metrics/security tương đương và rollback được.

**Không đánh đồng “cùng HTTP status và body” với “cùng mức bảo mật”.** Hai pipeline có thể trả 200 giống nhau nhưng khác nhau ở việc có gửi Cookie/JWT, có áp quota hoặc có thông tin Host/Forwarded đáng tin hay không.

## 18. Checklist production dành riêng cho ProxyExchange

- [ ] Đã xác định đây là **Proxy Exchange**, không phải Gateway Server; artifact đúng MVC/WebFlux.
- [ ] Dùng Spring Cloud BOM tương thích, đối chiếu tên module/property sau đổi tên 2025.0.
- [ ] Controller có mapping HTTP method/path rõ ràng, không mở `/**` proxy tùy ý.
- [ ] Destination URI từ allowlist/config tin cậy, không lấy trực tiếp từ untrusted header/query.
- [ ] Query/path parameters được validate và encode; tránh traversal, open redirect, SSRF.
- [ ] Không cho rằng `spring.cloud.gateway.server.*.routes/default-filters` áp vào ProxyExchange.
- [ ] Không cho rằng Server `RequestRateLimiter/Retry/CircuitBreaker/TokenRelay` tự bao controller.
- [ ] Spring Security MVC/WebFlux phù hợp đã được cấu hình và test anonymous/authorized cases.
- [ ] Sensitive headers, skipped headers và X-Forwarded trust được kiểm tra ở cả Gateway và backend.
- [ ] Không tự forward raw Cookie, Authorization, Host, Content-Length và hop-by-hop headers.
- [ ] Có timeout/connect/read policy cho HTTP client thực dùng bởi ProxyExchange.
- [ ] Nếu cần rate limit, dùng limiter được tích hợp thật, quota key đáng tin, state đúng phạm vi nhiều replicas.
- [ ] Retry không lặp side effects ngoài ý muốn; POST có idempotency contract nếu cho retry.
- [ ] Response mapper không làm hỏng status, Content-Length, Transfer-Encoding, Location hoặc CORS.
- [ ] Không buffer/download body lớn bằng `byte[]` mà chưa load-test memory và cancellation.
- [ ] Metrics phân biệt inbound request, downstream attempts, backend errors, timeouts và auth decisions.
- [ ] Không coi `/actuator/gateway/routes` là inventory của annotated controllers.
- [ ] Nếu project vừa có Server vừa có ProxyExchange, có tests chứng minh handler mapping/order và không trùng route ngoài ý muốn.
- [ ] Khi thay đổi backend URL, có cơ chế cập nhật config riêng, kiểm tra readiness và rollback.
- [ ] Có negative tests chứng minh Server filter config không bị nhầm với policy đã áp.

## 19. Câu hỏi tự kiểm tra

**1. Thêm `spring.cloud.gateway.server.webflux.default-filters` có tự thêm response header vào ProxyExchange WebFlux controller không?**

Không. Default-filters thuộc routes **Gateway Server WebFlux**. Controller ProxyExchange là một annotated handler riêng; muốn thay header cần ProxyExchange API, response mapper hoặc Spring WebFlux filter tương ứng.

**2. Gateway Server Web MVC và ProxyExchange Web MVC cùng dùng Servlet. Có cùng filter chain không?**

Không mặc định. Server Web MVC dùng WebMvc.fn route/HandlerFilterFunction; ProxyExchange MVC dùng `@Controller` và ProxyExchange argument resolver. Cả hai có thể chịu Servlet/Spring Security filters ở tầng chung, nhưng **không tự dùng chung Server route filters**.

**3. Vì sao `/actuator/gateway/routes` rỗng nhưng `/edge/items/42` vẫn gọi backend được?**

Vì annotated `@GetMapping` không phải Server RouteDefinition. Hãy kiểm tra `/actuator/mappings` được bảo vệ và controller/downstream logs.

**4. Khi đổi một Server route URI từ A sang B rồi phát `RefreshRoutesEvent`, controller có tự dùng B không?**

Không. Controller tự ghép URI từ code/config riêng. Sự kiện Server route refresh không tự viết lại field trong controller.

**5. ProxyExchange mặc định xử lý `Authorization` và `Cookie` thế nào?**

Tài liệu mô tả đó là **sensitive headers** mặc định không được chuyển downstream. Nhưng implementation/customization theo version vẫn cần được kiểm thử; không mặc định relay credential để “sửa” lỗi backend 401.

**6. Nếu backend trả 503 thì việc đặt `retries: 3` trong Server YAML có tác dụng gì với ProxyExchange controller?**

Không tự khiến controller gửi lại request. Muốn retry phải tích hợp policy vào HTTP call/stack thực tế và định nghĩa budget/deadline/idempotency.

**7. Khi nào nên chuyển sang Gateway Server?**

Khi cần nhiều routes, filters dùng chung, discovery/LoadBalancer tích hợp, dynamic route refresh hoặc observability theo route IDs. Quyết định cần dựa trên độ phức tạp/số lượng policy và yêu cầu vận hành thật.

## 20. Tài liệu tham khảo

1. [Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html): tài liệu gốc khẳng định Proxy Exchange là phong cách thay thế, tách khỏi tài liệu Gateway Server; artifact, controller và header policy.
2. [Spring Cloud Gateway Proxy Exchange 4.3](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html): đối chiếu hướng dẫn với các ứng dụng dùng release 4.3.x.
3. [Spring Cloud Gateway 5.0 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html): tham chiếu cho 5.0.x.
4. [Spring Cloud Gateway — Project Introduction](https://docs.spring.io/spring-cloud-gateway/reference/intro.html): Server vs Proxy Exchange, MVC vs WebFlux.
5. [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes): đổi tên artifacts và namespace configuration.
6. [Spring Cloud Gateway Server WebFlux — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/how-it-works.html): route predicate, Gateway filter chain và Netty routing của **Server**, dùng để nhận diện điểm khác biệt.
7. [Spring Cloud Gateway Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html): WebMvc.fn RouterFunction/HandlerFilterFunction của **Server MVC**.
8. [Spring Framework — Spring MVC annotated controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): `@RequestMapping` và các argument annotations trong MVC.
9. [Spring Framework — Spring WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): annotated handlers trong reactive WebFlux.
10. [Spring Security — Servlet authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) và [Reactive authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): các cơ chế security áp dụng theo stack.

**Ghi nhớ:** `ProxyExchange` cho phép một annotated MVC/WebFlux controller gọi downstream HTTP một cách thuận tiện, nhưng **không phải một Route của Spring Cloud Gateway Server**. Vì thế, `routes`, `default-filters`, `RequestRateLimiter`, `Retry`, `CircuitBreaker`, `TokenRelay` hay `RefreshRoutesEvent` của Server **không tự áp dụng** cho controller đó. Hãy kiểm chứng request đang đi qua **handler nào**, dùng đúng cấu hình theo **flavor và web stack**, rồi tích hợp xác thực, header trust, timeout, quota, resilience và observability có chủ đích. Khi số tuyến/chính sách lớn, chọn Gateway Server để giảm việc tự tái tạo cả một filter pipeline trong controller.
