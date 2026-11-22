# Khởi tạo ứng dụng Servlet hoặc WebFlux theo mục tiêu thực thi

Khi xây dựng **OAuth 2.0 Resource Server bằng Spring Security**, một quyết định cần đưa ra ngay từ lúc khởi tạo dự án là chọn **Spring MVC trên Servlet stack** hay **Spring WebFlux trên reactive stack**. Cả hai đều có thể bảo vệ REST API bằng access token do một **Authorization Server** phát hành; khác biệt chính nằm ở **mô hình xử lý request, cách tổ chức I/O, bộ API lập trình và thành phần Spring Security được sử dụng**.

Ví dụ, Orders API có thể dùng Spring MVC với `SecurityFilterChain` hoặc WebFlux với `SecurityWebFilterChain`. Trong cả hai trường hợp, client vẫn gửi:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Resource Server cần xác minh token, kiểm tra quyền và trả kết quả. Chọn Servlet hay WebFlux **không thay đổi trách nhiệm OAuth 2.0 này**, nhưng ảnh hưởng lớn đến thư viện, kiểu trả về, cách truy cập cơ sở dữ liệu, luồng thực thi và phương án mở rộng hệ thống.

## 1. Phân biệt ba quyết định dễ bị gộp làm một

Trước khi tạo project, tách rõ ba câu hỏi:

1. **Ứng dụng có vai trò bảo mật nào?** Trong bài này, ứng dụng là **Resource Server**, nhận access token của request đến. Nó không tự cấp access token hoặc làm mới token thay client.
2. **Ứng dụng dùng web stack nào?** Chọn Spring MVC/Servlet hoặc Spring WebFlux/reactive theo mục tiêu thực thi.
3. **Ứng dụng xác minh token theo cơ chế nào?** Chọn JWT với chữ ký/claims hoặc opaque token với introspection, theo hợp đồng với Authorization Server. Cả hai web stack đều có khả năng cấu hình JWT và opaque token.

Một hệ thống có thể dùng Authorization Server hỗ trợ OIDC để người dùng đăng nhập, trong khi API chỉ đóng vai trò OAuth 2.0 Resource Server. **OIDC login cho client và bearer-token authentication cho API là hai bài toán khác nhau**. Chọn WebFlux không tự bật OIDC login; thêm Resource Server starter cũng không tự tạo token endpoint.

## 2. Servlet và WebFlux khác nhau ở đâu?

| Tiêu chí | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Mô hình xử lý web | Mô hình request/response dựa trên Servlet API, thường dùng luồng xử lý đồng bộ | Mô hình phản ứng dựa trên Reactive Streams, hỗ trợ I/O không chặn và backpressure |
| Starter web thường dùng | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Controller thường gặp | `@RestController`, trả DTO, `ResponseEntity<T>` | `@RestController`, thường trả `Mono<T>` hoặc `Flux<T>` |
| Security HTTP | `HttpSecurity` → `SecurityFilterChain` | `ServerHttpSecurity` → `SecurityWebFilterChain` |
| Authentication context | `SecurityContextHolder` trong luồng đồng bộ tương ứng | `ReactiveSecurityContextHolder` gắn với Reactor context |
| Xác minh JWT bằng Spring Security | `JwtDecoder`, thường là `NimbusJwtDecoder` | `ReactiveJwtDecoder`, thường là `NimbusReactiveJwtDecoder` |
| Opaque token introspection | Thành phần introspector cho Servlet stack | Thành phần reactive introspector |
| Truy cập dữ liệu tự nhiên | JDBC, JPA/Hibernate, các thư viện blocking | R2DBC, reactive clients; chú ý khi phải gọi thư viện blocking |
| Mô hình mở rộng | Dễ dùng với thư viện Java đồng bộ và hệ sinh thái Servlet | Hữu ích cho nhiều thao tác I/O đồng thời khi các tầng thực sự hỗ trợ reactive |
| Cách xử lý dữ liệu lớn/streaming | Có các cơ chế async/streaming của MVC | Có `Flux`, streaming và backpressure theo mô hình reactive |

**Không có kết luận “WebFlux luôn nhanh hơn MVC”.** Hiệu năng phụ thuộc tải thực tế, cơ sở dữ liệu, độ trễ I/O, mức độ blocking, cấu hình máy chủ và cách triển khai. Servlet cũng có các lựa chọn tối ưu và những phiên bản Spring/Java mới có thể hỗ trợ virtual threads. WebFlux có lợi thế về mô hình reactive khi thành phần phía dưới thực sự không chặn; nếu dùng các thao tác blocking trên event loop, lợi thế này có thể giảm hoặc biến thành vấn đề.

### Cách Servlet xử lý một request

Ở mô hình MVC truyền thống, code service có thể gọi một repository đồng bộ và chờ kết quả:

~~~text
HTTP request
     |
     v
Servlet container
     |
     v
Spring Security filter chain
     |
     v
Spring MVC Controller
     |
     v
Service -> JPA/JDBC (blocking) -> Database
     |
     v
HTTP response
~~~

Lập trình viên thường viết một hàm trả về đối tượng Java:

~~~java
@GetMapping("/api/orders/{id}")
public OrderDto getOrder(@PathVariable long id) {
    return orderService.getOrder(id);
}
~~~

Nếu `getOrder` gọi I/O đồng bộ, luồng xử lý có thể chờ dữ liệu. Đây là mô hình trực quan, phổ biến, tương thích tốt với nhiều thư viện đang dùng trong ứng dụng nghiệp vụ.

### Cách WebFlux xử lý một request

Ở WebFlux, controller và service có thể biểu diễn kết quả bất đồng bộ qua `Mono` (0 hoặc 1 giá trị) và `Flux` (0 đến nhiều giá trị):

~~~text
HTTP request
     |
     v
Reactive HTTP server
     |
     v
Spring Security WebFilter chain
     |
     v
WebFlux Handler
     |
     v
Reactive Service -> Reactive database/HTTP client
     |
     v
Mono/Flux -> HTTP response
~~~

Ví dụ:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderDto> getOrder(@PathVariable long id) {
    return reactiveOrderService.getOrder(id);
}
~~~

`Mono<OrderDto>` không có nghĩa là “một luồng Java mới”. Nó biểu diễn một pipeline phản ứng được thực thi qua subscription và scheduler theo ngữ cảnh. Code sử dụng API blocking bên trong pipeline vẫn là **blocking**, cho dù chữ ký phương thức trả `Mono`.

## 3. Chọn stack từ mục tiêu thực thi

Một số tiêu chí thực tiễn:

| Mục tiêu/điều kiện | Xu hướng lựa chọn | Vì sao |
| --- | --- | --- |
| REST API CRUD với JPA/Hibernate hoặc JDBC | **Servlet / Spring MVC** | Đồng bộ với các thư viện dữ liệu blocking, luồng xử lý dễ theo dõi |
| Đội ngũ đã vận hành tốt hệ sinh thái Spring MVC/Servlet | **Servlet / Spring MVC** | Giảm số khái niệm mới và chi phí chuyển đổi |
| API gateway, proxy hoặc aggregator gọi nhiều dịch vụ qua HTTP reactive | **WebFlux** nếu I/O xuyên suốt là reactive | Thuận lợi cho kết hợp nhiều request bất đồng bộ |
| Streaming dữ liệu, nhiều kết nối chờ I/O, nhu cầu backpressure | **WebFlux** là lựa chọn đáng cân nhắc | Reactor cung cấp các phép toán streaming và backpressure |
| Phần lớn dependency là blocking, nhưng muốn có một endpoint `Mono` | Thường **Servlet / Spring MVC** vẫn hợp lý | Trả kiểu reactive không tự chuyển toàn bộ hệ thống thành non-blocking |
| Hệ thống đã có repository R2DBC và WebClient reactive | **WebFlux** | Duy trì chuỗi I/O reactive từ web đến dữ liệu |
| Chỉ cần xác minh Bearer JWT/OIDC issuer | **Cả hai** | Token validation không phải tiêu chí đủ để quyết định web stack |

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["API sẽ nhận Bearer access token"] --> B{"Các dependency nghiệp vụ chủ yếu blocking?"}
    B -->|Có, JPA/JDBC/SDK blocking| C["Ưu tiên Spring MVC / Servlet"]
    B -->|Không hoặc đã có hỗ trợ reactive| D{"Có nhu cầu reactive rõ ràng?"}
    D -->|Có: I/O đồng thời, streaming, backpressure| E["Cân nhắc Spring WebFlux"]
    D -->|Chưa rõ| F["Bắt đầu từ Spring MVC"]
    C --> G["Cấu hình Resource Server và quyền API"]
    E --> G
    F --> G
~~~

Sơ đồ là hướng lựa chọn ban đầu, không thay thế đo đạc tải thật. Nếu cần throughput hoặc latency cụ thể, nên thử nghiệm với dependency, số kết nối và mô hình triển khai thực tế.

## 4. Khởi tạo dự án: những phần chung

Bạn có thể tạo một ứng dụng Spring Boot bằng Spring Initializr, công cụ IDE hoặc cấu trúc build sẵn có. Cả hai phương án cần thống nhất:

- **Java/JDK** phù hợp với phiên bản Spring Boot/Spring Security mà dự án chọn.
- **Maven hoặc Gradle** cùng quản lý phiên bản dependency bằng Spring Boot parent/BOM hoặc cách quản lý tương đương.
- **Spring Boot application entry point** với `@SpringBootApplication`.
- **OAuth2 Resource Server starter**, cộng với **web starter phù hợp**.
- **Địa chỉ issuer và/hoặc JWK Set URI** hoặc **introspection endpoint**, tùy loại access token.
- **Hợp đồng quyền truy cập API**: audience, scope/authorities và quyền nghiệp vụ.

Đặt danh sách dependency và cấu hình web theo một phương án rõ ràng, ví dụ chỉ tạo một trong hai ứng dụng sau. Nếu cần cả MVC và WebFlux trong cùng một project vì thư viện client, phải hiểu chính xác web application type mà Spring Boot đã chọn.

### Cấu trúc thư mục ví dụ

~~~text
orders-api/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/orders/
    │   │   ├── OrdersApiApplication.java
    │   │   ├── security/
    │   │   │   └── ApiSecurityConfiguration.java
    │   │   ├── controller/
    │   │   │   └── OrdersController.java
    │   │   └── service/
    │   │       └── OrdersService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/
~~~

Entry point giống nhau về bản chất ở cả hai stack:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApiApplication.class, args);
    }
}
~~~

Trong ví dụ `pom.xml` bên dưới, giả định dự án đã dùng Spring Boot parent/BOM để quản lý phiên bản; các đoạn dependency được thêm vào phần `<dependencies>` tương ứng. Tên starter có thể thay đổi theo dòng Spring Boot lớn mà dự án chọn; cần dùng starter có mặt trong phiên bản đã chọn và không ghép tùy tiện các major version Spring.

## 5. Phương án A: tạo Resource Server trên Servlet stack

### 5.1. Dependencies

Với cấu trúc Spring Boot có starter web MVC mang tên `spring-boot-starter-web`:

~~~xml
<dependencies>
    <!-- Spring MVC chạy trên Servlet stack -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Bearer token authentication cho API -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Starter web MVC thường cấu hình một servlet container nhúng (ví dụ Tomcat) theo mặc định của phiên bản Starter. Resource Server starter cung cấp các thành phần Spring Security cần thiết để xử lý bearer token với JWT hoặc opaque token theo cấu hình.

Đây là **Resource Server**, chưa phải OAuth2 Client hoặc Authorization Server. Nếu ứng dụng cần gọi API khác và tự lấy token cho request đi ra, đó là một chức năng bổ sung cần thiết kế riêng.

### 5.2. Cấu hình issuer cho JWT

Ví dụ `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` phải trùng issuer thực tế mà Authorization Server công bố và sử dụng trong claim `iss`. Resource Server dùng metadata/khóa xác minh theo cơ chế được hỗ trợ để kiểm tra JWT. Đây là địa chỉ **minh họa**, không phải issuer đang hoạt động.

Khi cấu hình JWT, cần xác định thêm điều kiện **audience** theo hợp đồng API để tránh chấp nhận access token được phát hành cho tài nguyên khác. Không mặc định chỉ có `issuer-uri` là đã đáp ứng toàn bộ yêu cầu audience và quyền nghiệp vụ.

Nếu Authorization Server phát hành **opaque access token**, thay nhánh JWT bằng cấu hình introspection tương ứng, sử dụng endpoint và credential riêng dành cho Resource Server. Không dùng JWT decoder để đọc một opaque token.

### 5.3. Cấu hình bảo mật Servlet

File `security/ApiSecurityConfiguration.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            // Chỉ phù hợp khi API dùng Bearer token, không dựa vào cookie session.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Ý nghĩa các thành phần:**

- `HttpSecurity` và `SecurityFilterChain` là API của nhánh **Servlet**.
- `oauth2ResourceServer(...jwt(...))` kích hoạt Bearer JWT authentication cho request vào.
- Với mapping scope phổ biến của Spring Security, scope `orders.read` thành authority `SCOPE_orders.read`; issuer dùng claims khác cần cấu hình mapping phù hợp.
- `SessionCreationPolicy.STATELESS` phù hợp API không dùng HTTP session để duy trì trạng thái đăng nhập.
- Tắt CSRF trong ví dụ chỉ phù hợp khi xác thực hoàn toàn dựa trên Bearer token do client chủ động gửi. Nếu ứng dụng dùng cookie xác thực tự động đính kèm từ trình duyệt, phải đánh giá và bảo vệ CSRF.
- `permitAll()` chỉ miễn yêu cầu phân quyền cho đường dẫn chỉ định; không biến toàn bộ ứng dụng thành API công khai.

Đặc biệt, `hasAuthority("SCOPE_orders.read")` chỉ kiểm tra quyền ở cấp route. API vẫn cần xác minh người dùng có được đọc **đúng đơn hàng** theo tenant, quyền sở hữu hoặc chính sách nghiệp vụ hay không.

### 5.4. Controller Servlet tối giản

~~~java
package com.example.orders.controller;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/orders/me")
    public Map<String, String> currentSubject(
            @AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject() == null ? "unknown" : jwt.getSubject(),
            "message", "Access token was accepted"
        );
    }
}
~~~

`@AuthenticationPrincipal Jwt` chỉ nhận dữ liệu từ ngữ cảnh xác thực đã được Spring Security thiết lập. Đây là cách minh họa lấy subject, **không phải bằng chứng rằng subject được phép đọc mọi đơn hàng**. Controller thực tế nên gọi service kiểm tra quyền ở cấp bản ghi.

Với đường dẫn `/api/orders/me`, token cần quyền `orders.read` theo security chain phía trên. Đường dẫn `/public/ping` có thể được gọi không cần token.

## 6. Phương án B: tạo Resource Server trên WebFlux stack

### 6.1. Dependencies

Với Spring Boot có starter `spring-boot-starter-webflux`:

~~~xml
<dependencies>
    <!-- Spring WebFlux và reactive web runtime -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <!-- Bearer token authentication cho API -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Một ứng dụng WebFlux dạng reactive thường chạy với **Reactor Netty** theo mặc định của WebFlux starter. WebFlux cũng có khả năng chạy trên một số Servlet container hỗ trợ async, vì vậy cần phân biệt **web programming model** với **tên HTTP server** đang chạy.

### 6.2. Cấu hình JWT

Resource Server WebFlux cũng có thể dùng:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Giá trị issuer cùng ý nghĩa như Servlet: token phải đến từ nguồn tin cậy và đáp ứng kiểm tra xác thực/ủy quyền của API. Các thành phần Spring Security dùng để xác minh JWT phía reactive thường thực thi qua `ReactiveJwtDecoder` thay vì `JwtDecoder` dạng đồng bộ.

### 6.3. Cấu hình bảo mật WebFlux

File `security/ApiSecurityConfiguration.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Phù hợp khi API chỉ xác thực bằng Bearer token.
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Điểm khác biệt với Servlet:**

- `ServerHttpSecurity` thay cho `HttpSecurity`.
- `SecurityWebFilterChain` thay cho `SecurityFilterChain`.
- `authorizeExchange` và `pathMatchers` thay cho `authorizeHttpRequests` và `requestMatchers`.
- Security context trong reactive pipeline gắn với **Reactor context**, không nên giả định dữ liệu xác thực luôn nằm trong `ThreadLocal` của một luồng cố định.
- Không bê nguyên cấu hình `SessionCreationPolicy.STATELESS` của Servlet sang WebFlux. Nhánh reactive có API và cơ chế quản lý security context/session riêng; ứng dụng bearer API phải thiết kế sao cho không phụ thuộc phiên đăng nhập phía server.

Lưu ý CSRF tương tự: ví dụ tắt CSRF cho API thuần Bearer token. Nếu ứng dụng WebFlux nhận xác thực bằng cookie từ browser, cần giữ hoặc cấu hình CSRF đúng với mô hình đó.

### 6.4. Controller WebFlux tối giản

~~~java
package com.example.orders.controller;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/orders/me")
    public Mono<Map<String, String>> currentSubject(
            @AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject() == null ? "unknown" : jwt.getSubject();

        return Mono.just(Map.of(
            "subject", subject,
            "message", "Access token was accepted"
        ));
    }
}
~~~

Đoạn này cho thấy **chữ ký reactive** của controller, chưa thực hiện I/O bất đồng bộ. Trong ứng dụng thật, việc kết hợp Repository, HTTP client hoặc stream dữ liệu mới là nơi cần thiết kế pipeline `Mono`/`Flux` và chính sách backpressure phù hợp.

Nếu phải lấy `Authentication` ở sâu trong reactive pipeline, dùng API phù hợp như `ReactiveSecurityContextHolder` hoặc truyền danh tính/claims một cách tường minh. Đừng giả định `SecurityContextHolder.getContext()` sẽ cho ra cùng thông tin ở mọi bước chạy asynchronous sau khi pipeline chuyển scheduler.

## 7. Cấu hình Resource Server giống và khác nhau ở hai stack

### Những gì giống nhau

Cả MVC và WebFlux Resource Server đều:

- Nhận access token thường qua header `Authorization: Bearer ...`.
- Xác thực token theo issuer, chữ ký/khóa hoặc introspection, thời hạn và các điều kiện cần thiết.
- Áp dụng quy tắc scope, authorities và phân quyền trên tài nguyên.
- Thường trả **401** khi không có thông tin xác thực hợp lệ, **403** khi đã xác thực nhưng không đủ quyền.
- Không tự phát hành access token hay refresh token cho client.
- Có thể phục vụ API dùng token do Authorization Server hỗ trợ OAuth 2.0/OIDC phát hành, miễn token đúng hợp đồng của API.

### Những gì khác nhau

| Chức năng | Servlet | WebFlux |
| --- | --- | --- |
| Đối tượng cấu hình security | `HttpSecurity` | `ServerHttpSecurity` |
| Bean security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Web request matching | `requestMatchers(...)` | `pathMatchers(...)` |
| Thiết lập quy tắc authorization | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| JWT decoder theo hướng mở rộng | `JwtDecoder` | `ReactiveJwtDecoder` |
| Kết quả nghiệp vụ | DTO hoặc `ResponseEntity` thông thường | `Mono<T>`, `Flux<T>` hoặc các kiểu phù hợp WebFlux |
| Context của authentication | Truyền thống theo luồng xử lý Servlet | Theo Reactor context trong pipeline |

Nếu cần tùy biến validation `aud` hoặc ánh xạ claim tùy chỉnh, hãy dùng **decoder/converter đúng stack**. Một bean `JwtDecoder` đồng bộ không phải sự thay thế trực tiếp cho `ReactiveJwtDecoder` của WebFlux; tương tự, ví dụ cấu hình SecurityFilterChain cho MVC không thể dán nguyên xi vào lớp WebFlux.

### JWT so với opaque token

Chọn Servlet/WebFlux **không buộc token phải là JWT**. Với opaque token, Resource Server có thể dùng introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: YOUR_INTROSPECTION_CLIENT_ID
          client-secret: YOUR_INTROSPECTION_CLIENT_SECRET
~~~

Các giá trị trên chỉ là giữ chỗ; cần dùng endpoint, quyền và cách bảo vệ credentials thực tế. Thay cấu hình `jwt(...)` trong security chain bằng chế độ opaque token tương ứng trên từng stack. Introspection là việc **kiểm tra token đã tồn tại**, không phải refresh token grant.

## 8. Chọn công nghệ truy cập dữ liệu đi cùng web stack

Quyết định Servlet hay WebFlux ảnh hưởng đến nhiều thành phần **sau** lớp xác thực:

### Servlet + JPA/JDBC

Đây là sự kết hợp phổ biến khi có mô hình giao dịch đồng bộ:

~~~text
Controller (Servlet)
    -> Service
        -> @Transactional
            -> JPA Repository / JDBC
                -> Database
~~~

Những lệnh đọc/ghi dữ liệu blocking thường nằm trong một luồng xử lý tương ứng. Việc triển khai transaction, tracing và kiểm soát lỗi có thể theo mô hình lập trình đồng bộ quen thuộc.

### WebFlux + R2DBC/Reactive HTTP client

Một hệ thống reactive thường sử dụng R2DBC hoặc SDK thực sự hỗ trợ Reactive Streams và `WebClient` cho lời gọi HTTP:

~~~text
Handler (WebFlux)
    -> Reactive Service
        -> Mono/Flux
            -> R2DBC / WebClient
                -> Database / Remote API
~~~

Ví dụ service kết hợp hai lời gọi bất đồng bộ:

~~~java
import reactor.core.publisher.Mono;

public Mono<OrderView> getOrderView(String orderId) {
    Mono<Order> order = orderRepository.findById(orderId);
    Mono<Customer> customer = customerClient.getByOrderId(orderId);

    return Mono.zip(order, customer)
        .map(tuple -> new OrderView(tuple.getT1(), tuple.getT2()));
}
~~~

Ví dụ giả định repository/client trả `Mono` và các thao tác thực sự reactive; `OrderView` là DTO của ứng dụng. `Mono.zip` kết hợp hai nguồn kết quả, nhưng **không chứng minh hai tác vụ luôn chạy nhanh hơn** trong mọi hoàn cảnh.

### Nếu buộc phải gọi thư viện blocking từ WebFlux

Ví dụ một SDK chỉ có API đồng bộ:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<LegacyResult> callLegacySdk() {
    return Mono.fromCallable(() -> legacySdk.fetch())
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đưa lời gọi blocking ra một scheduler thích hợp có thể giúp tránh chặn event loop. Tuy nhiên đây **không phải giải pháp biến SDK thành non-blocking**: vẫn có giới hạn luồng, bộ nhớ, số kết nối và transaction context cần được tính toán. Nếu phần lớn dịch vụ thực thi blocking, Spring MVC thường là điểm khởi đầu đơn giản hơn.

Ngược lại, ứng dụng MVC cũng có thể dùng `WebClient` để gọi HTTP. Việc thêm dependency WebFlux chỉ để dùng WebClient **không tự chuyển toàn bộ server sang WebFlux**.

## 9. Tránh chọn nhầm web application type khi có nhiều starter

Một lỗi khởi tạo phổ biến là thêm **cả** `spring-boot-starter-web` và `spring-boot-starter-webflux` rồi mặc định hệ thống chắc chắn chạy reactive.

Trong cách auto-detection phổ biến của Spring Boot, khi cả Spring MVC và WebFlux cùng xuất hiện, **Spring MVC thường được ưu tiên cho web application type**. Sự hiện diện của `Mono` hoặc `WebClient` trong classpath không tự biến tất cả servlet filters và controller thành reactive web runtime.

Vì vậy:

1. Nếu mục tiêu là MVC, chọn web starter dành cho MVC và dùng `SecurityFilterChain`.
2. Nếu mục tiêu là WebFlux, chọn web starter dành cho WebFlux và dùng `SecurityWebFilterChain`.
3. Nếu dự án phải mang nhiều thư viện cả hai bên, xác định rõ loại ứng dụng mong muốn và cấu hình theo cơ chế mà Spring Boot hỗ trợ, ví dụ thuộc tính `spring.main.web-application-type` nếu có lý do thực sự cần chỉ định thủ công.

Ví dụ định hướng reactive **khi classpath hỗn hợp khiến cần ép kiểu**:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Chỉ đặt cấu hình này sau khi hiểu rõ dependency, auto-configuration và khả năng hỗ trợ của chúng. Không coi đây là cách sửa mọi lỗi do trộn bean/filter đồng bộ với reactive.

Một vấn đề tương tự là cấu hình:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) { /* ... */ }
~~~

trong ứng dụng chạy hoàn toàn WebFlux. Sai họ API security có thể dẫn đến thiếu bean, lỗi khi khởi động hoặc chính sách không được áp dụng như mong đợi. Hãy dùng đúng cặp:

- **Servlet:** `HttpSecurity` + `SecurityFilterChain`.
- **WebFlux:** `ServerHttpSecurity` + `SecurityWebFilterChain`.

## 10. Chạy thử một Resource Server mới khởi tạo

### 10.1. Chuẩn bị Authorization Server

Trước khi kiểm thử endpoint bảo vệ:

- Authorization Server phải phát hành access token có issuer đúng cấu hình.
- Nếu dùng JWT, Resource Server phải truy cập được metadata/JWKS phù hợp với cấu hình để xác minh chữ ký (tùy cách cấu hình decoder).
- Nếu dùng opaque token, Resource Server phải gọi được introspection endpoint và có credential hợp lệ.
- Token dự kiến dùng với Orders API phải có audience/quyền được ứng dụng chấp nhận, ví dụ scope `orders.read`.

Một token của ứng dụng khác hoặc ID token từ đăng nhập OIDC không phải tự động là access token hợp lệ của Orders API.

### 10.2. Khởi động ứng dụng

Với Maven Wrapper trên hệ thống Unix-like:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Lệnh minh họa cách chạy dự án sau khi đã tạo file build và chọn web stack. Ứng dụng có thể khởi động không thành công nếu thiếu cấu hình, dependency không tương thích, hoặc issuer metadata không thể truy cập trong cấu hình cần khám phá thông tin lúc khởi động.

### 10.3. Thử endpoint công khai

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kết quả kỳ vọng với ví dụ controller:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
~~~

### 10.4. Thử endpoint bảo vệ khi chưa gửi token

~~~bash
curl -i http://localhost:8080/api/orders/me
~~~

Resource Server thường trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Header/body có thể khác theo cấu hình exception handling và phiên bản framework. Mục đích của phép thử là xác nhận API bảo vệ route, không tự redirect sang OIDC login cho một request Bearer API thông thường.

### 10.5. Thử với access token hợp lệ

~~~bash
curl -i \
  -H "Authorization: Bearer <VALID_ACCESS_TOKEN>" \
  http://localhost:8080/api/orders/me
~~~

Thay `<VALID_ACCESS_TOKEN>` bằng token thử nghiệm thực sự do issuer cấp cho API. Với một token đúng chữ ký, issuer, thời hạn, audience và scope `orders.read`, controller minh họa có thể trả:

~~~json
{
  "subject": "user-42",
  "message": "Access token was accepted"
}
~~~

Nếu token không hợp lệ hoặc hết hạn, API thường trả **401**. Nếu token đã được xác thực nhưng không có quyền `orders.read`, API thường trả **403**. Hai tình huống cần xử lý khác nhau: client không nên tự làm mới token vô hạn khi gặp 403.

**Không đưa token thật vào URL, source code, commit hoặc log.** Với terminal có thể sử dụng biến môi trường hoặc trình quản lý bí mật thay cho việc dán token vào lịch sử shell.

## 11. Các điểm cần cấu hình sau khi project chạy được

### 11.1. Kiểm tra issuer, audience và thời hạn

Một Resource Server an toàn cần làm rõ:

- `iss`: token phải được phát hành bởi issuer đáng tin cậy.
- `aud`: token phải dành cho API đang tiếp nhận nó.
- `exp` và `nbf`: token phải hợp lệ về thời gian theo chính sách và clock skew.
- Chữ ký JWT/khóa hoặc trạng thái opaque token phải hợp lệ.
- Scope/authorities và quyền nghiệp vụ phải phù hợp với thao tác.

Spring Security hỗ trợ các validator tương ứng, nhưng **cấu hình audience và quy tắc đặc thù phải được xác định rõ** theo yêu cầu hệ thống. Không coi một JWT có chữ ký hợp lệ là giấy phép gọi mọi API cùng issuer.

### 11.2. CORS và CSRF là hai cơ chế khác nhau

Nếu SPA ở origin khác gọi API trong trình duyệt, ứng dụng cần cấu hình **CORS** phù hợp với origin, header và phương thức được cho phép. CORS là cơ chế kiểm soát quyền đọc response của trình duyệt, **không thay thế xác thực bearer token và kiểm soát quyền tại API**.

**CSRF** là rủi ro khác, đặc biệt quan trọng khi browser **tự động đính kèm cookie xác thực**. Chỉ tắt CSRF theo ví dụ khi API thực sự dùng Bearer token được client gắn rõ ràng và không phụ thuộc cookie xác thực tự động gửi. CORS và CSRF cần được đánh giá riêng cho cả MVC và WebFlux.

### 11.3. Quyền truy cập cấp bản ghi

Nếu cả An và Bình có `orders.read`, Orders API vẫn phải kiểm tra An có được xem đơn hàng của Bình không. Route-level authorization như `hasAuthority("SCOPE_orders.read")` mới là điều kiện ban đầu; quyền ở cấp tenant, bản ghi và trạng thái nghiệp vụ thuộc về service/domain authorization.

### 11.4. Quản lý bí mật và cấu hình môi trường

Không hardcode private key, introspection client secret hoặc token trong repository. Đưa credential vào cơ chế secret management phù hợp và cấu hình riêng cho môi trường dev/staging/production. Địa chỉ issuer phải ổn định, đúng HTTPS trong môi trường vận hành và phù hợp chính sách tin cậy.

### 11.5. Quan sát hệ thống

Khi vận hành, cần quan sát mã 401/403, latency của API, độ trễ introspection (nếu dùng), lỗi khám phá JWKS, cảnh báo về downstream service và tải I/O. Tuy nhiên, **không ghi nguyên access token, refresh token hay authorization header** vào log và tracing.

Với WebFlux, chú ý thêm các tác vụ blocking trên event loop, cơ chế timeout và áp lực bộ nhớ khi tạo pipeline lớn. Với Servlet, quan sát thread pool, database connection pool và thời gian chờ downstream.

## 12. Lỗi khởi tạo thường gặp và cách hiểu

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không inject được `HttpSecurity`/`SecurityFilterChain` như kỳ vọng | Ứng dụng đang cấu hình reactive hoặc dependency security thiếu | Xem web application type, starter và dùng họ security phù hợp |
| Không inject được `ServerHttpSecurity`/`SecurityWebFilterChain` | Project thực tế chạy Servlet MVC hoặc thiếu WebFlux/security reactive | Xem dependencies, web application type và annotation/config |
| Có `Mono` nhưng server vẫn là MVC | WebFlux library chỉ có mặt trên classpath, Boot chọn Servlet | Xem starter thực sự và quy tắc auto-detection |
| Mọi endpoint bảo vệ đều 401 | Token vắng mặt, sai issuer/audience, hết hạn, chữ ký sai hoặc cấu hình decoder lỗi | Xác nhận Authorization header, issuer, token type, JWK/introspection |
| 403 dù đã gửi token | Token hợp lệ nhưng không có authority/scope hoặc thiếu quyền nghiệp vụ | Xác nhận scope claim, mapping `SCOPE_` và chính sách cấp bản ghi |
| Ứng dụng không khởi động do issuer | Metadata/JWKS không truy cập được hoặc URI sai trong cấu hình cần khám phá khi startup | Kiểm tra URL issuer, mạng, TLS, metadata và cách cấu hình JWK Set URI |
| WebFlux dưới tải có latency cao bất thường | I/O blocking nằm trên event loop, downstream chậm hoặc xử lý pipeline không hợp lý | Kiểm tra SDK, repository, scheduler, timeout và đo tải |
| Gọi `SecurityContextHolder` từ reactive callback không thấy authentication | Reactive context khác ThreadLocal đồng bộ | Dùng `ReactiveSecurityContextHolder`/cơ chế inject phù hợp |
| Browser chặn request do CORS | Origin/header/method chưa được cho phép | Cấu hình CORS đúng phía API; vẫn giữ xác thực/authorization |
| API có cookie đăng nhập nhưng bị tắt CSRF theo ví dụ | Áp dụng sai giả định API thuần Bearer token | Thiết kế lại CSRF theo mô hình cookie/session thực tế |

Không nên giải quyết các lỗi trên bằng cách bỏ xác minh chữ ký, tắt mọi filter hoặc cho phép toàn bộ route. Hãy xác định chính xác **web stack đang chạy**, **security chain đang được dùng** và **loại token hợp lệ** mà issuer cấp.

## 13. Ba tình huống thiết kế điển hình

### Tình huống A — Hệ thống quản lý đơn hàng với JPA

Ứng dụng có nhiều tác vụ CRUD, `@Transactional`, JPA Repository và một số REST endpoint. Nhóm phát triển đã quen với Spring MVC. Lựa chọn tự nhiên là:

- Spring MVC/Servlet starter.
- Resource Server starter.
- SecurityFilterChain, `HttpSecurity` và JWT/opaque-token validation theo issuer.
- JPA/JDBC ở lớp truy cập dữ liệu; kiểm tra quyền theo đơn hàng ở service.

Người dùng có thể đăng nhập thông qua một OIDC client khác; Orders API chỉ cần xác thực access token của request.

### Tình huống B — API tổng hợp dữ liệu từ nhiều nguồn reactive

API nhận yêu cầu danh sách dashboard và phải gọi đồng thời nhiều backend HTTP, tất cả được tích hợp qua `WebClient`/reactive SDK. Hệ thống đã dùng reactive persistence và có nhu cầu streaming. Khi đó có thể chọn:

- WebFlux starter.
- Resource Server starter.
- `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveJwtDecoder`.
- `Mono`/`Flux` xuyên suốt luồng I/O, tránh gọi SDK blocking trên event loop.

JWT vẫn phải được kiểm tra theo cùng yêu cầu issuer/audience/scope; dùng WebFlux không làm token an toàn hơn một cách tự động.

### Tình huống C — Backend đang dùng MVC, cần một HTTP client reactive

Một backend MVC chỉ cần dùng `WebClient` để gọi service khác. Có thể bổ sung WebClient/thư viện cần thiết mà **không nhất thiết chuyển server sang WebFlux**. Tách rõ phần client của request đi ra với phần Resource Server của request đi vào. Nếu backend tự xin token cho downstream API, đó là chức năng **OAuth2 Client** bổ sung, độc lập với việc nó là MVC hay WebFlux Resource Server.

## 14. Quy trình thực hiện cho dự án mới

Một quy trình khởi tạo theo mục tiêu thực thi:

1. **Xác định request và I/O chủ đạo**: CRUD/JPA blocking hay reactive HTTP/DB, streaming và nhiều kết nối chờ I/O.
2. **Chọn duy nhất web stack mục tiêu**: MVC/Servlet hoặc WebFlux; chọn starter và họ security tương ứng.
3. **Khởi tạo Spring Boot project** với entry point, Resource Server starter và cấu hình môi trường phù hợp.
4. **Chọn cơ chế access token** theo hợp đồng Authorization Server: JWT/JWKS hoặc opaque/introspection.
5. **Khai báo issuer, audience, authority mapping và quyền API**. Tránh chỉ kiểm tra token mà bỏ quyền cấp bản ghi.
6. **Tạo security chain phù hợp**: `SecurityFilterChain` trên Servlet hoặc `SecurityWebFilterChain` trên WebFlux.
7. **Tạo endpoint công khai và endpoint bảo vệ**, chạy thử không token, sai token, token thiếu scope và token đủ quyền.
8. **Triển khai service/data access đồng bộ hoặc reactive tương ứng**, sau đó đo latency, tải và xử lý lỗi theo môi trường thực.

**Kết luận:** MVC/Servlet là lựa chọn phù hợp cho nhiều API nghiệp vụ đồng bộ; WebFlux hữu ích khi hệ thống có mục tiêu reactive rõ ràng và I/O hỗ trợ từ đầu đến cuối. Trong cả hai trường hợp, một **Spring Security OAuth 2.0 Resource Server** vẫn có cùng trách nhiệm bảo mật: **xác minh access token, kiểm tra quyền truy cập và bảo vệ tài nguyên**. Hãy lựa chọn web stack dựa trên mô hình thực thi của ứng dụng, rồi sử dụng đúng API security, decoder và thư viện dữ liệu của stack đó.
