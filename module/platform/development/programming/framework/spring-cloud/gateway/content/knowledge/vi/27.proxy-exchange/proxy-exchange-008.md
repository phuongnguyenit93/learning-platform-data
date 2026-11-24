# forward() đến handler nội bộ trong biến thể Web MVC

## 1. Bối cảnh: chuyển xử lý nội bộ thay vì gọi thêm một HTTP service

Trong một hệ thống microservices, **Spring Cloud Gateway** thường nhận request tại cổng vào, chọn route bằng predicate, áp dụng filter chain, sửa path/header, chuyển đến service qua discovery/load balancing và kết hợp xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS cùng observability. Tuy nhiên, không phải request nào cũng cần gọi một microservice khác qua HTTP.

Có những trường hợp ta muốn đưa request qua một **controller ở cổng vào**, kiểm tra một điều kiện nghiệp vụ đơn giản rồi **chuyển quyền xử lý cho một handler MVC khác ngay trong cùng ứng dụng**. Ví dụ:

- Client gọi `GET /edge/products/42`.
- Controller ở mép hệ thống kiểm tra input và quyết định dùng handler nội bộ.
- Handler nội bộ `GET /internal/products/42` trả JSON.
- Client chỉ thấy response của cùng HTTP request, URL trong trình duyệt vẫn là `/edge/products/42`.

Trong **Spring Cloud Gateway Proxy Exchange cho Spring Web MVC**, đối tượng `ProxyExchange` có hỗ trợ **`forward(String)`** để thực hiện kiểu chuyển tiếp này. Đây là chủ đề **“forward() đến handler nội bộ trong biến thể Web MVC”**, thuộc chương **Proxy Exchange** của module **SPRING_CLOUD_GATEWAY**.

Bài học giúp bạn:

1. Phân biệt **Proxy Exchange MVC**, **Gateway Server Web MVC** và **Gateway Server WebFlux**.
2. Hiểu **server-side forward** khác HTTP redirect và remote HTTP proxy như thế nào.
3. Viết `@Controller` dùng `ProxyExchange<byte[]>` và `forward("/internal/...")`.
4. Viết handler nội bộ `@RestController` xử lý forward bằng Spring MVC.
5. Hiểu HTTP method, request body, Servlet request attributes và response lifecycle khi forward.
6. Kiểm thử bằng `MockMvc`, HTTP integration test và `curl`; phát hiện forward loop, mapping mismatch, thiếu security và lỗi content negotiation.
7. Quyết định khi nào nên chọn forward, khi nào nên dùng HTTP proxy, hoặc khi nào nên gọi thẳng một service Java.

> **Phạm vi phiên bản:** tài liệu Spring Cloud Gateway hiện hành phân biệt hai **flavor** là *Server* và *Proxy Exchange*. Ví dụ này dùng **Proxy Exchange Web MVC**, với artifact `spring-cloud-gateway-proxyexchange-webmvc` trong các release mới (ví dụ 4.3/5.x). Một số release cũ dùng tên `spring-cloud-gateway-mvc`. Không nhầm với starter **`spring-cloud-starter-gateway-server-webmvc`** của Gateway Server Web MVC. API và package cần được xác nhận với release train đang chạy.

## 2. Trước hết: ba kiểu chuyển tiếp trông giống nhau nhưng khác bản chất

### 2.1. So sánh forward, redirect và proxy

| Cơ chế | Ai thực hiện chuyển tiếp? | Có HTTP request mới từ browser? | Đi qua mạng tới service khác? | URL browser thay đổi? |
| --- | --- | --- | --- | --- |
| **MVC internal forward** | Server/Servlet container trong cùng ứng dụng | Không | Không, khi đích là local handler | Không |
| **HTTP redirect 302/307/308** | Browser/client đọc `Location` rồi gọi lại | Có | Tùy đích | Thường có |
| **Remote proxy qua `ProxyExchange.uri(...).get()`** | Ứng dụng Gateway tạo outbound HTTP call | Không có request *thứ hai từ browser*, nhưng có request từ Gateway đến backend | Có | Không |
| **Gọi Java service trực tiếp** | Controller gọi method/service trong JVM | Không | Không | Không |

Một điểm dễ nhầm: cả **forward** và **remote proxy** đều có thể làm client chỉ nhìn thấy một URL công khai. Nhưng **proxy** tạo thêm HTTP request outbound và chịu ảnh hưởng của DNS/TLS, connection pool, timeout, upstream status. **Forward** đi tới local handler trong cùng Servlet application và không cần service discovery.

### 2.2. Sơ đồ luồng `forward()`

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP Client
    participant D as Spring MVC DispatcherServlet
    participant E as Edge Controller
    participant I as Internal Controller
    C->>D: GET /edge/products/42
    D->>E: Match @GetMapping
    E->>D: proxy.forward("/internal/products/42")
    Note over D: Forward nội bộ trong Servlet application
    D->>I: Dispatch GET /internal/products/42
    I-->>D: 200 + JSON
    D-->>C: 200 + JSON
    Note over C,D: Không có Location redirect và không có client GET thứ hai
~~~

Lược đồ mô tả **đường xử lý logic**. Việc Spring MVC resolve forward view và Servlet `RequestDispatcher` làm việc ra sao phụ thuộc implementation và cấu hình container/view resolver. Không dùng sơ đồ này để giả định mọi `Filter`/Spring Security chain chắc chắn chạy lại theo cùng một cách ở dispatch thứ hai.

### 2.3. Vì sao `forward()` không phải `forward:///...`?

Spring Cloud Gateway **Server WebFlux** có route `uri: forward:///localendpoint` và `ForwardRoutingFilter` xử lý qua `DispatcherHandler` reactive. Đó là **API thuộc Server WebFlux**.

Trong bài này ta dùng một **argument của MVC controller**:

~~~java
ProxyExchange<byte[]> proxy
~~~

và phương thức:

~~~java
proxy.forward("/internal/products/42")
~~~

Hai cơ chế cùng hướng tới việc xử lý local nhưng **không cùng runtime, không cùng filter chain và không có cùng API**. Không đem cấu hình `forward:///...` của WebFlux vào một MVC annotation-based controller rồi mong `ProxyExchange.forward()` tự chạy.

## 3. Phân biệt hai nhánh mang tên “MVC” của Spring Cloud Gateway

Đây là nơi dễ chọn sai dependency nhất:

| Khía cạnh | **Proxy Exchange Web MVC** (bài này) | **Gateway Server Web MVC** |
| --- | --- | --- |
| Mục đích | Thêm khả năng proxy/forward trong **controller có annotation** | Xây **API Gateway Server** đầy đủ với route predicates/filters |
| Điểm vào Java | `@GetMapping`, `@PostMapping`, `ProxyExchange<T>` | `RouterFunction<ServerResponse>`, `GatewayRouterFunctions.route()` |
| Local forward đặc trưng | `ProxyExchange.forward(String)` | Cơ chế handler/filter của Server MVC, không phải API argument này |
| Remote proxy | `proxy.uri(url).get()`, `.post()`... | `HandlerFunctions.http()` với target URI/filter |
| Artifact hiện hành | `spring-cloud-gateway-proxyexchange-webmvc` | `spring-cloud-starter-gateway-server-webmvc` |
| Runtime | Servlet / Spring MVC annotation handlers | Servlet / Spring WebMvc.fn |
| Áp dụng tất cả Gateway Server filters? | **Không** | Có hệ sinh thái filters/predicates của Server MVC theo version |
| Dùng YAML route `spring.cloud.gateway.server.webmvc.routes`? | Không phải điều kiện để `ProxyExchange` được inject | Có thể dùng ở Server Web MVC version phù hợp |

**Tài liệu Proxy Exchange nói rõ đây là một kiểu gateway thay thế; các phần tài liệu Gateway Server không mặc nhiên áp dụng cho nó.** Vì vậy, khi thêm module Proxy Exchange vào một Spring MVC application, bạn **không tự nhận** toàn bộ cơ chế route-definition repository, GatewayFilterChain, RedisRateLimiter hay circuit breaker của Gateway Server.

Dù không có những server filters đó theo mặc định, ứng dụng vẫn có thể dùng **Spring Security MVC**, Servlet filters, service Java, validation, tracing, metrics hoặc resilience thư viện khác. Nhưng chúng phải được cấu hình riêng và kiểm thử.

## 4. Dependency và cấu trúc project

### 4.1. Maven cho Proxy Exchange Web MVC hiện hành

Trong một ứng dụng đã quản lý Spring Boot/Spring Cloud BOM tương thích:

~~~xml
<!-- Spring MVC Servlet application -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<!-- Proxy Exchange cho MVC annotation-based controllers -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>
~~~

Không tự chỉ định một version độc lập cho artifact Gateway nếu đã dùng Spring Cloud BOM. Spring Boot/Spring Cloud không phải các thư viện luôn có thể nâng version riêng rẽ; hãy chọn **release train tương thích** với runtime (Java/Spring Framework) của dự án.

Ở các release trước khi đổi tên module, dependency có thể là:

~~~xml
<!-- Tên cũ, chỉ khi release train tương ứng thực sự dùng nó -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-mvc</artifactId>
</dependency>
~~~

Không thêm cả **artifact cũ + mới + Gateway Server Web MVC** vào một bài lab chỉ để “đảm bảo có forward”: dependency trùng/khác flavor khiến startup và debugging khó hơn.

### 4.2. Tổ chức Java class minh họa

~~~text
src/main/java/example/proxy/
  ProxyForwardApplication.java
  EdgeForwardController.java
  InternalProductsController.java
~~~

Các code block ở mục sau được thiết kế theo một ứng dụng nhỏ. Đặt chúng trong cùng base package `example.proxy` hoặc bảo đảm component scan bao phủ cả controllers.

## 5. Ví dụ hoàn chỉnh: GET từ public URL đến local handler

### 5.1. Spring Boot application

~~~java
package example.proxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyForwardApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyForwardApplication.class, args);
    }
}
~~~

Một cấu hình port tùy chọn:

~~~yaml
server:
  port: 8080
~~~

Chưa cần Redis, Eureka, Config Server hoặc upstream HTTP khác để thử **forward nội bộ**. Cả edge controller và target controller chạy trong **cùng ứng dụng Spring MVC**.

### 5.2. Controller ở cạnh ngoài: dùng `@Controller`, không dùng `@RestController`

~~~java
package example.proxy;

import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class EdgeForwardController {

    @GetMapping("/edge/products/{id}")
    public String product(
            @PathVariable("id") long id,
            ProxyExchange<byte[]> proxy) {

        if (id <= 0) {
            throw new IllegalArgumentException("Product ID must be positive");
        }

        return proxy.forward("/internal/products/" + id);
    }
}
~~~

**Giải thích:**

1. `@GetMapping` cho Spring MVC biết URL và HTTP method công khai.
2. `ProxyExchange<byte[]>` được MVC argument resolver của Proxy Exchange cung cấp khi module và auto-configuration đúng.
3. `proxy.forward(String)` nhận **đường dẫn local**; ví dụ dùng đường dẫn cố định có tham số `id` đã kiểm tra.
4. Handler trả về **`String` theo nghĩa tên view/forward instruction của Spring MVC**.
5. `@Controller` quan trọng vì một `String` trả về sẽ được **view resolution** xử lý thay vì tự coi là response body.
6. Đích `/internal/products/{id}` phải thật sự có handler khớp; nếu không, kết quả sẽ là lỗi không tìm thấy handler/view theo ứng dụng.

**Không đặt `@ResponseBody` trên method forward**, cũng không thay class thành `@RestController` chỉ vì endpoint cuối trả JSON. Với `@RestController`, chuỗi kiểu `forward:/internal/products/42` có thể bị ghi thẳng thành response body thay vì được dùng để chuyển tiếp. Chức năng forward thuộc **cơ chế xử lý view của MVC**.

> **Ghi chú kỹ thuật:** `forward(String)` là API có trong **ProxyExchange MVC**. Phần Javadoc của một nhánh cũ (4.1.x) liệt kê `forward(String)`, còn tài liệu 4.3/5.x xác nhận có local forwarding. Nếu behavior khác giữa các phiên bản, trước hết kiểm tra đúng artifact/package và chạy integration test; không thay nó bằng một `ResponseEntity` tự chứa chuỗi `forward:`.

### 5.3. Local controller: trả JSON bình thường

~~~java
package example.proxy;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InternalProductsController {

    @GetMapping("/internal/products/{id}")
    public ResponseEntity<Map<String, Object>> product(
            @PathVariable("id") long id,
            @RequestParam(value = "lang", defaultValue = "vi") String lang) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", id);
        body.put("name", "Demo product");
        body.put("lang", lang);
        body.put("handledBy", "internal-mvc-handler");

        return ResponseEntity.ok()
                .header("X-Handler-Type", "local-forward")
                .body(body);
    }
}
~~~

**Vì sao target dùng `@RestController` được?** Vì target trả một `ResponseEntity<Map<...>>` làm **HTTP response body**. Chỉ method *khởi tạo forward* cần trả instruction để MVC thực hiện internal dispatch. Hai controller dùng các annotation khác nhau có chủ đích.

Nếu client gọi:

~~~bash
curl -i http://localhost:8080/edge/products/42
~~~

ta **kỳ vọng** status 200 và JSON chứa:

~~~json
{
  "id": 42,
  "name": "Demo product",
  "lang": "vi",
  "handledBy": "internal-mvc-handler"
}
~~~

Cùng response có thể chứa header:

~~~http
X-Handler-Type: local-forward
~~~

JSON/header là **kết quả dự kiến từ code ví dụ**, chưa phải log chạy thật. Chưa có outbound HTTP call từ Gateway đến một host khác; không cần mock server port 8081 để kiểm tra ca này.

### 5.4. Không cần tự thêm `uri("http://localhost")`

Đối với forward local, đừng làm:

~~~java
// Sai mục tiêu: dùng HTTP proxy tới chính ứng dụng thay vì internal forward.
return proxy.uri("http://localhost:8080/internal/products/42").get();
~~~

Đoạn trên sẽ tạo **HTTP call outbound** tới port 8080 qua networking stack, dù vẫn chạy trên cùng host. Nó tăng latency, tốn connection và có thể gây loop hoặc timeout. Mục tiêu nội bộ nên dùng `forward("/internal/products/42")` hoặc đơn giản gọi thẳng Java service nếu không cần HTTP dispatch semantics.

## 6. Cách Servlet forward giữ nguyên một request

Server-side forward trong Servlet không tương đương với client tự gửi lại request. Về nguyên tắc:

- Request gốc vẫn là **một HTTP request từ client**.
- Internal dispatch xử lý **cùng ngữ cảnh request/response**, không làm browser đổi URL.
- **HTTP method** vẫn là method ban đầu, trừ khi custom wrapper/logic đặc biệt thay đổi.
- **Request attributes** có thể được truyền trong cùng request; Servlet container còn có các attributes liên quan đến forward.
- Header, cookie, query, body cần được hiểu theo quy tắc Servlet dispatcher/target mapping và cách filter đã đọc body.
- Response nội bộ sẽ được gửi cho client khi hoàn tất pipeline, miễn response chưa bị commit trước forward.

### 6.1. Không tự giả định query string luôn được tái cấu trúc y hệt

Nếu client gọi:

~~~http
GET /edge/products/42?lang=en HTTP/1.1
Host: localhost:8080
~~~

Ta có thể muốn local controller nhận `lang=en`. Với Servlet forwarding thông thường, request parameters gốc được giữ trong request khi forward, nhưng **path forward có thể kèm query riêng** và cách hợp nhất tham số có quy tắc của Servlet spec.

Trong bài lab, hãy thực sự kiểm tra:

~~~bash
curl -i "http://localhost:8080/edge/products/42?lang=en"
~~~

Rồi assert body có `"lang":"en"`. Nếu project có custom servlet mapping, URL encoding, forwarded path hoặc query manipulation, behavior cần được test trên container đang chạy.

### 6.2. Request attributes và phạm vi request

Ví dụ một controller có thể gắn thông tin vào request trước khi forward:

~~~java
@GetMapping("/edge/demo")
public String demo(ProxyExchange<byte[]> proxy,
                   jakarta.servlet.http.HttpServletRequest request) {
    request.setAttribute("edge.forward.reason", "local-handler");
    return proxy.forward("/internal/demo");
}
~~~

Target local handler có thể đọc:

~~~java
@GetMapping("/internal/demo")
public Map<String, String> internalDemo(
        jakarta.servlet.http.HttpServletRequest request) {
    Object reason = request.getAttribute("edge.forward.reason");
    return Map.of("reason", String.valueOf(reason));
}
~~~

Đây là **metadata cục bộ trong một request**. Nó không tự đi sang HTTP remote backend. Với các ứng dụng Servlet cũ (Spring Framework 5 / Java EE), import có thể là `javax.servlet.*`; ví dụ hiện đại dùng **`jakarta.servlet.*`** theo Spring Framework 6+/Boot 3+.

**Không gán dữ liệu người dùng nhạy cảm vào attribute rồi tự động log cả request attributes.** Với authorization, hãy lấy danh tính từ `SecurityContext` hoặc principal đã xác thực, không tin một attribute có tên đẹp.

## 7. GET, POST và body khi forward

### 7.1. Forward không biến POST thành GET

Một redirect `302` trong browser có thể dẫn tới request khác với method đổi thành GET tùy user agent/semantics. Nhưng **Servlet internal forward không phải redirect**: HTTP method đầu vào thường được giữ.

Điều này có nghĩa:

- Controller `@GetMapping("/edge/products/{id}")` forward tới target `@GetMapping("/internal/products/{id}")` là hợp lý.
- Controller `@PostMapping("/edge/echo")` phải forward đến **target hỗ trợ POST** nếu muốn giữ operation.
- Forward từ POST sang một endpoint chỉ hỗ trợ GET có thể dẫn đến `405 Method Not Allowed` hoặc xử lý khác theo mapping, không phải tự động convert sang GET.

### 7.2. POST body được target đọc

Ví dụ thêm vào một controller dùng `@Controller`:

~~~java
@PostMapping("/edge/echo")
public String echo(ProxyExchange<byte[]> proxy) {
    // Không đọc @RequestBody tại đây, để handler đích đọc body.
    return proxy.forward("/internal/echo");
}
~~~

Thêm vào controller dùng `@RestController`:

~~~java
@PostMapping(
    path = "/internal/echo",
    consumes = "application/json",
    produces = "application/json")
public ResponseEntity<Map<String, Object>> echo(
        @RequestBody Map<String, Object> payload) {

    return ResponseEntity.ok(Map.of(
            "received", payload,
            "handledBy", "internal-echo"));
}
~~~

Imports bổ sung cho hai đoạn trên là `org.springframework.web.bind.annotation.PostMapping`, `RequestBody`, `org.springframework.http.ResponseEntity`, `java.util.Map`.

Chạy thử:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}' \
  http://localhost:8080/edge/echo
~~~

Kỳ vọng response body mô tả đã nhận thông điệp và xử lý bởi local handler. **Cần kiểm thử body và Content-Type thật** vì một Servlet filter ở trước đó có thể đã đọc hết `InputStream`, hoặc ứng dụng có custom wrapper/request parsing. Không mặc định body được đọc lại vô hạn.

### 7.3. Vì sao không nên đọc body ở cả edge và target?

Servlet request body thường là **stream có giới hạn khả năng đọc lại**. Nếu controller edge hoặc một filter đọc xong raw input, target có thể gặp body rỗng hoặc lỗi parsing. Cách tốt hơn:

1. Nếu cần validate payload trước forwarding, thiết kế request wrapper/cache **có giới hạn kích thước**, kiểm tra giải phóng bộ nhớ.
2. Nếu đã parse thành DTO và logic tiếp theo nằm cùng JVM, cân nhắc **gọi Java service trực tiếp** thay vì forward.
3. Nếu cần giữ semantics POST tới local MVC target, để **handler target** đảm nhiệm việc parse body khi phù hợp.
4. Với upload/multipart lớn, tránh đọc/copy body không cần thiết; kiểm tra Servlet multipart limits.
5. Test Content-Type sai, JSON không hợp lệ, body trống, charset và request cancellation.

**Không tự kết luận ProxyExchange.forward() cung cấp cache body/multipart replay.** Nó là cơ chế chuyển xử lý local, không phải bộ đệm stream miễn phí.

## 8. Đường dẫn forward và tránh vòng lặp

### 8.1. Dùng local path có owner rõ ràng

Thiết kế an toàn:

~~~text
Public:
  /edge/products/{id}

Internal:
  /internal/products/{id}
~~~

Phân tách prefix giúp code review và kiểm thử dễ hơn. Nhưng prefix `/internal` **không tự biến endpoint thành private**. Nếu application public vẫn nhận được `GET /internal/products/42` trực tiếp, client có thể bypass edge validation trừ khi security và network route được thiết kế đúng.

### 8.2. Sai lầm nguy hiểm: forward tới chính mình

~~~java
// PHẢN VÍ DỤ: vòng lặp forward, không chạy!
@GetMapping("/edge/loop")
public String loop(ProxyExchange<byte[]> proxy) {
    return proxy.forward("/edge/loop");
}
~~~

Một request bị chuyển đến mapping lại gọi forward chính nó. Tuỳ Servlet container và exception handling, điều này có thể dẫn đến lỗi, stack overflow, vượt dispatcher depth, timeout hoặc log lặp. Không khẳng định một status HTTP cố định.

Nguyên tắc phòng ngừa:

- Không forward đến cùng path/mapping nếu không có guard có chứng minh chặt.
- Với mọi forwarding chain dài hơn một hop, có **sơ đồ luồng có hướng**, không tạo chu trình.
- Giới hạn số lần forward theo policy nếu sử dụng custom routing.
- Test các path ranh giới và query/encoded slash.
- Không tạo route kiểu `/edge/** -> /edge/**` rồi dùng substring thiếu validation.

### 8.3. Không dùng path nhận trực tiếp từ client để forward

Đoạn sau rất rủi ro:

~~~java
// KHÔNG áp dụng cho endpoint public:
@GetMapping("/edge/go")
public String arbitrary(
        @RequestParam("next") String next,
        ProxyExchange<byte[]> proxy) {
    return proxy.forward(next);
}
~~~

Client có thể chọn `next=/internal/admin`, `/actuator`, path chứa `..`, encoded characters hoặc một mapping chưa được bảo vệ. Dù forward local **không giống SSRF ra mạng**, nó có thể gây **internal endpoint exposure** và bypass lớp kiểm tra được đặt ở edge.

Nên dùng allowlist cố định:

~~~java
@GetMapping("/edge/page")
public String page(
        @RequestParam("view") String view,
        ProxyExchange<byte[]> proxy) {
    return switch (view) {
        case "summary" -> proxy.forward("/internal/pages/summary");
        case "help" -> proxy.forward("/internal/pages/help");
        default -> throw new IllegalArgumentException("Unsupported view");
    };
}
~~~

Không dùng `String.contains("internal")` hay blacklist yếu làm policy. Nếu cần nhiều target, lưu mapping ở code/config đáng tin, validate URI/path normalization và dùng Spring Security để bảo vệ target thực sự.

## 9. Authentication và authorization khi request được forward

### 9.1. Không xem forward là một lớp security

Giả sử `/edge/products/42` được bảo vệ bằng Spring Security và controller kiểm tra quyền, còn `/internal/products/42` có handler trả dữ liệu nhạy cảm. Nếu client có thể gọi `/internal/products/42` trực tiếp, bảo vệ ở `/edge/**` **không đủ**.

Một rule chỉ dựa vào `/edge/**` có thể không bao phủ direct requests vào `/internal/**`. Hãy bảo vệ target dựa trên principal và quyền nghiệp vụ.

### 9.2. DispatcherType.FORWARD có ý nghĩa gì?

Servlet có các dispatcher types như **REQUEST**, **FORWARD**, **INCLUDE**, **ASYNC**, **ERROR**. Một filter có thể đăng ký cho loại dispatch nhất định, còn Spring Security behavior phụ thuộc version và filter-chain configuration.

Cần phân biệt:

1. **Client request trực tiếp** vào `/internal/**` với dispatcher type REQUEST.
2. **Nội bộ forward** từ `/edge/**` tới `/internal/**` với dispatch type FORWARD trong luồng Servlet.

**Không tuyên bố “Spring Security chắc chắn kiểm tra lại mọi forward”**, cũng không tuyên bố “Spring Security luôn bỏ qua forward” trong mọi version. Một rule path, dispatcher registration hoặc một cấu hình `dispatcherTypeMatchers` có thể thay đổi cách auth diễn ra. Kiểm tra bằng integration tests đúng filter chain thực tế.

### 9.3. Mô hình bảo vệ được khuyến nghị

- Public `/edge/**` phải qua authentication/authorization theo nghiệp vụ.
- Nếu `/internal/**` không được gọi trực tiếp từ bên ngoài, đảm bảo **direct client requests bị từ chối** bởi security policy, không chỉ đặt tên “internal”.
- Không dùng `permitAll` cho toàn bộ `/internal/**` chỉ để làm forward hoạt động.
- Nếu cho phép dispatch `FORWARD` đến internal target theo policy, ghi rõ giới hạn và kiểm chứng request là forward hợp lệ, không giả định một header client đủ chứng minh.
- Với dữ liệu nhạy cảm, **authorization ở service/handler đích** vẫn nên xác minh principal và object-level permission.
- Không cho client tự chọn forwarding path.
- Test cả 401/403 và direct/forward paths.

Ví dụ một ứng dụng có thể áp dụng **Servlet `SecurityFilterChain`** với `HttpSecurity`, không dùng `SecurityWebFilterChain` của WebFlux. Nhưng không nên chép một mẫu `permitAll(FORWARD)` chung vào production mà chưa có threat model và tests, vì nó có thể làm những target khác được truy cập ngoài ý muốn.

### 9.4. CORS và CSRF không được “giải quyết” chỉ bằng forward

- **CORS** giới hạn request do JavaScript browser gửi từ origin khác, không tự cấp quyền truy cập tài nguyên.
- **CSRF** quan trọng nếu API dựa vào cookie/session credential cho thao tác ghi; internal forward không xóa rủi ro của POST đầu vào.
- **TLS** ở ingress chỉ bảo vệ network leg tương ứng, không thay đổi kiểm soát quyền ở target.
- **Forwarded/X-Forwarded headers** từ trusted proxy phải được xử lý ở trust boundary; không coi header client tự đặt là bằng chứng đã qua kiểm tra.

## 10. Không nhầm hành vi của `forward()` với remote `get()`

Trong Proxy Exchange, cùng một controller có thể chọn local hoặc remote theo policy **được kiểm soát**, nhưng hai lệnh rất khác.

### 10.1. Local forward

~~~java
@Controller
class LocalBranchController {

    @GetMapping("/edge/local")
    String local(ProxyExchange<byte[]> proxy) {
        return proxy.forward("/internal/demo");
    }
}
~~~

### 10.2. HTTP proxy tới upstream

~~~java
@RestController
class RemoteBranchController {

    @GetMapping("/edge/remote")
    ResponseEntity<?> remote(ProxyExchange<byte[]> proxy)
            throws Exception {
        return proxy.uri("http://localhost:8081/demo").get();
    }
}
~~~

Ở case remote:

- `uri(...)` chỉ định **HTTP target**.
- `.get()` thực hiện outbound GET tới server `8081`.
- HTTP status, body, headers đến từ HTTP response upstream (có thể được mapper chỉnh).
- Có network latency, DNS/connection failures, TLS verification, retries/timeouts theo client/config.
- Các headers sensitive/skipped của Proxy Exchange có policy riêng; theo tài liệu hiện hành, các nhóm mặc định gồm `cookie`, `authorization` và những headers hop-by-hop/không nên copy theo cách mù như `host`, `content-length`. Các mặc định có thể thay đổi theo phiên bản.

Ở case local:

- Không cấu hình URI external.
- Không tạo outbound HTTP tới port 8081.
- Không tự xử lý header như một downstream HTTP proxy; sử dụng request/response Servlet cùng ứng dụng.

### 10.3. ProxyExchange `header()` không phải API của `forward()`

Tài liệu Proxy Exchange có `header()`/`headers()` và mapper cho `get()`, `post()`... để điều chỉnh **downstream HTTP call** hoặc response của nó. **Không tự giả định việc set một header dành cho outbound proxy sẽ tự chuyển thành response header của handler local forward**.

Nếu local handler cần metadata, cân nhắc request attributes hoặc service-level context được xác thực. Nếu muốn response header, set bằng handler target hoặc Servlet response API thích hợp **trước khi response commit**.

## 11. Forward có thể được thay bằng redirect hoặc gọi service khi nào?

### 11.1. Khi nên forward

Dùng internal forward khi:

- Hai handler chạy trong **cùng Servlet application**.
- Bạn muốn một endpoint public **ủy quyền xử lý** cho một MVC mapping có sẵn.
- Không muốn browser thực hiện HTTP request thứ hai.
- Cần giữ HTTP method/request context.
- Đã có chính sách security cho cả entry và target.
- Có lý do sử dụng **MVC handler mapping** thay vì gọi method Java trực tiếp.

Ví dụ một ứng dụng chuyển alias URL cũ `/legacy/help` đến local `/help` mà không đổi URL ở client — nếu việc này được thiết kế rõ và kiểm thử.

### 11.2. Khi nên redirect

Dùng `302`/`307`/`308` khi:

- Muốn client biết **canonical URL** mới hoặc đi sang một origin khác.
- Muốn browser cập nhật URL/history.
- Muốn phân tách request đầu và request tiếp theo ở client.
- Đã đánh giá đúng semantics HTTP method. `307/308` có quy tắc giữ method rõ hơn các redirect truyền thống.

Không dùng forward khi business contract yêu cầu client thật sự chuyển URL.

### 11.3. Khi nên gọi service Java trực tiếp

Nếu handler edge chỉ cần gọi một method nghiệp vụ cục bộ, đôi khi điều đơn giản nhất là:

~~~java
@RestController
class EdgeProductApi {
    private final ProductQueryService products;

    EdgeProductApi(ProductQueryService products) {
        this.products = products;
    }

    @GetMapping("/edge/products/{id}")
    ProductView product(@PathVariable long id) {
        return products.findOne(id);
    }
}
~~~

Đây là **mẫu minh họa**, giả định `ProductQueryService`/`ProductView` được khai báo ở phần application domain. Cách này tránh phụ thuộc vào MVC forward/view resolution; dễ test trực tiếp logic hơn. Chỉ dùng forward khi **sự tái sử dụng handler/MVC dispatch** thực sự cần thiết.

### 11.4. Khi nên dùng Gateway Server đầy đủ

Nếu yêu cầu là:

- Route predicate/filter chain hàng trăm routes.
- Service discovery và load balancing nhiều upstream.
- Rate limiting, circuit breaker, retry, tracing và TLS policy tập trung.
- Quản trị routes bằng config/DSL hoặc refresh phù hợp.
- Nhiều Gateway replicas và control plane.

thì nên đánh giá **Spring Cloud Gateway Server Web MVC** hoặc **Server WebFlux**, thay vì tự dựng hết route management trong một đám `@Controller + ProxyExchange`. Proxy Exchange hữu ích cho một số handlers proxy/forward trong ứng dụng MVC, nhưng **không được quảng bá như một bản thay thế 1:1 mọi chức năng Gateway Server**.

## 12. HTTP response khi forward: status, headers và error handling

### 12.1. Không có response HTTP 3xx trung gian

Với forward thành công, client thường chỉ nhận **response cuối** mà target handler tạo. Ví dụ local target trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Handler-Type: local-forward

{"handledBy":"internal-mvc-handler","id":42}
~~~

Sẽ **không có `Location: /internal/products/42`** theo cơ chế redirect vì browser không được yêu cầu tự gửi request khác. Nếu bạn nhìn thấy 302/307, có thể ứng dụng đang dùng `redirect:`, Spring Security authentication entrypoint hoặc một interceptor khác; không phải bản chất của `forward()`.

### 12.2. Nếu target trả lỗi

Ví dụ target có thể trả `404` khi product không tồn tại hoặc `403` nếu principal không có quyền. Client nhìn thấy response đó qua request công khai, trừ khi exception handler/filter tạo response khác.

**Không ép mọi lỗi thành `200 OK` chỉ vì request đã forward thành công ở tầng MVC.** Forward là bước điều phối nội bộ, không đảm bảo nghiệp vụ tại target thành công.

### 12.3. Response đã commit thì không thể forward đáng tin cậy

Một khi response headers/body đã được commit, việc gọi forward hoặc redirect có thể thất bại hoặc sinh kết quả không mong muốn tùy container. Đừng vừa:

~~~java
response.getWriter().write("partial response");
~~~

rồi mới yêu cầu MVC forward. Cần quyết định đích trước khi bắt đầu ghi response.

### 12.4. Exception handling có thể bắt lỗi ở handler đích

Một `@ControllerAdvice` phù hợp phạm vi có thể biến validation exceptions hoặc domain errors của local handler thành HTTP status/JSON nhất quán. Nhưng:

- Handler edge có thể lỗi **trước forward**.
- Target handler có thể lỗi **sau forward**.
- Servlet `Filter`, Security và `HandlerInterceptor` có thể hoạt động khác theo dispatch type.
- Error dispatch có thể tạo xử lý bổ sung.

Test từng nhánh, không giả định mọi exception được cùng một advice bắt trong mọi configuration.

## 13. Logging và observability: một request, hai điểm xử lý

Một internal forward có thể làm cả **edge** và **internal** handler ghi log. Nếu bạn đếm “lượt gọi user” bằng số log entry của controller, có thể đếm trùng.

Ví dụ timeline được làm sạch:

~~~text
requestId = req-123
clientMethod = GET
publicPath = /edge/products/42
forwardTarget = /internal/products/42
handlerTarget = InternalProductsController.product
finalStatus = 200
outboundHttpCalls = 0
~~~

Đây là **log design ví dụ**, không phải metric tự có của Proxy Exchange. Cần:

- Request/trace ID thống nhất cho toàn request.
- Một metric **client request count** ở ranh giới ingress.
- Metrics riêng cho handler latency hoặc internal dispatch khi muốn quan sát.
- Không gắn raw request ID làm metric label vì cardinality cao.
- Đếm outbound HTTP calls riêng; forward local không phải một upstream attempt.
- Che token, cookie, query chứa PII và body nhạy cảm.
- Theo dõi lỗi forward loop, target 404/405, exception, thời gian xử lý và security denied.

Nếu Gateway còn các layers như ingress/service mesh, trace nên phân biệt **client → Gateway** và **Gateway → remote service**. Với local forward sẽ không có network span tương đương remote proxy, nhưng có thể có instrumentation handler nội bộ.

## 14. Kiểm thử đơn vị bằng MockMvc

### 14.1. Điều kiện để test forward hoạt động đúng

Một test sử dụng `@WebMvcTest` chỉ khởi tạo một phần MVC context. Vì `ProxyExchange<byte[]>` là argument type của thư viện, **test slice có thể không tự đưa vào đầy đủ auto-configuration/argument resolver**.

Có hai chiến lược:

- **Integration test với `@SpringBootTest` + `@AutoConfigureMockMvc`** để gần với runtime thật nhất.
- **MVC slice test** có import configuration argument resolver cần thiết nếu biết chính xác cấu hình theo version; không lấy slice test fail do thiếu resolver làm kết luận `forward()` hỏng.

### 14.2. Một test kiểm tra forward target

Test skeleton bằng MockMvc khi app context đã có MVC/Proxy Exchange:

~~~java
package example.proxy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProxyForwardMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void edgeRouteForwardsToInternalMapping() throws Exception {
        mvc.perform(get("/edge/products/42"))
                .andExpect(status().isOk())
                .andExpect(forwardedUrl("/internal/products/42"));
    }
}
~~~

**Giải thích và caveat:**

- `forwardedUrl(...)` của MockMvc hữu ích để xác minh **đích forward**, nhưng cách MockMvc xử lý tiếp dispatch đến target **khác môi trường Servlet container thật**. Có cấu hình chỉ ghi nhận `forwardedUrl` thay vì tự gọi target/nhận JSON.
- Nếu test trên đã thấy đúng forward instruction mà chưa có JSON body cuối, **đó không đủ để kết luận runtime thật không trả JSON**.
- Bật Spring Security trong test có thể đổi expected HTTP status nếu thiếu mock principal/token. Cần mock authentication hợp lệ hoặc chạy theo chính sách bảo mật.
- Cần đúng Spring Boot/Test và JUnit dependencies; đây là ví dụ cần project setup tương thích, **chưa được chạy trong bài viết**.

### 14.3. Kiểm thử response cuối bằng embedded server

Để xác minh cả **edge và target cùng hoạt động**, nên chạy ứng dụng với Servlet container thật:

- `@SpringBootTest(webEnvironment = RANDOM_PORT)`.
- HTTP client test như `TestRestTemplate`, `RestClient`, `WebTestClient` HTTP-bound hoặc RestAssured, tùy hệ thống.
- Gửi GET tới cổng thật.
- Assert `200`, JSON và `X-Handler-Type`.
- Quan sát outbound HTTP client mock: **không có call nào đến remote service**.
- Assert direct access `/internal/products/{id}` bị từ chối nếu business policy yêu cầu.

Sự khác nhau giữa **MockMvc forwardedUrl** và **real server final response** là một bài học quan trọng trong forward semantics.

## 15. Kiểm thử thủ công bằng curl

### 15.1. GET thành công

~~~bash
curl -i "http://localhost:8080/edge/products/42"
~~~

Kỳ vọng từ code mẫu:

~~~text
HTTP 200
Content-Type: application/json
X-Handler-Type: local-forward

Body có id=42 và handledBy="internal-mvc-handler"
~~~

Lưu ý `curl -i` hiển thị response cuối, **không hiển thị một bước redirect**, vì forward ở server.

### 15.2. Query parameter

~~~bash
curl -i "http://localhost:8080/edge/products/42?lang=en"
~~~

Kỳ vọng body chứa `"lang":"en"` khi forward và parameter handling đúng cấu hình Servlet MVC.

### 15.3. POST body

Sau khi thêm `@PostMapping("/edge/echo")` và target nội bộ:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}' \
  "http://localhost:8080/edge/echo"
~~~

Kỳ vọng target đọc payload JSON đúng và không có outbound HTTP call.

### 15.4. Direct target access

~~~bash
curl -i "http://localhost:8080/internal/products/42"
~~~

**Trong ứng dụng demo chưa có Spring Security**, request này có thể được xử lý trực tiếp bởi internal controller. Đây không phải behavior an toàn mặc định của một hệ thống chứa dữ liệu nhạy cảm. Khi đã thêm security policy, assert direct request bị từ chối theo yêu cầu, trong khi **forward hợp lệ** vẫn hoạt động.

### 15.5. Không nhầm redirect

~~~bash
curl -i "http://localhost:8080/edge/products/42"
~~~

Nếu response có `Location` và status 3xx, hãy kiểm tra:

1. Controller có thực sự là `@Controller` không?
2. Có trả `proxy.forward("/internal/...")` chứ không phải `"redirect:/internal/..."` không?
3. Có Spring Security login redirect hay interceptor không?
4. Có URL rewrite/redirect ở ingress hoặc reverse proxy trước app không?

Một JSON response 200 cuối là hợp lý cho case forward tới `@RestController`.

## 16. Ma trận kiểm thử quan trọng

| Ca | Thao tác | Assertion cần có |
| --- | --- | --- |
| F1 | GET `/edge/products/42` | Forward đúng `/internal/products/42`; JSON của target |
| F2 | GET cùng URL với `lang=en` | Query/parameter được xử lý đúng theo contract |
| F3 | GET `/edge/products/0` | Validation ngăn ID không hợp lệ |
| F4 | POST `/edge/echo` với JSON | Method POST giữ nguyên; target nhận đúng payload |
| F5 | POST nhưng target chỉ hỗ trợ GET | Method mismatch; không tự biến POST thành GET |
| F6 | Target trả 404 | Client thấy lỗi phù hợp; không chuyển mọi kết quả thành 200 |
| F7 | Target trả 403 | Không bypass object-level authorization |
| F8 | Gọi trực tiếp `/internal/**` | Bị từ chối nếu security contract yêu cầu |
| F9 | `@RestController` nhầm ở forward source | Test phát hiện response body là forward string, không dispatch |
| F10 | Forward target trùng với source mapping | Test phát hiện/không cho phép forward loop |
| F11 | Client cố đưa path tùy ý vào query | Allowlist chặn forward tới admin/local secrets |
| F12 | Gateway chỉ có Proxy Exchange MVC | Không ngầm có filter chain riêng của Gateway Server |
| F13 | MockMvc test | `forwardedUrl` đúng, không suy đoán JSON final nếu container chưa dispatch |
| F14 | Embedded server test | Response cuối đúng, không có HTTP 3xx/truy cập mạng mới |
| F15 | Security Filter với dispatcher FORWARD | Test thực tế path/principal và direct vs forwarded access |
| F16 | Servlet filter đọc body trước | Phát hiện lỗi stream cạn hoặc body parsing |
| F17 | Target response đã commit rồi cố forward | Không cho phép chuyển tiếp sau commit |
| F18 | Thử trên Servlet container khác/đổi Spring version | Behavior và mapping vẫn đúng theo hỗ trợ release |

Những trường hợp này là **kế hoạch kiểm thử**, không phải kết quả đã thực thi. Không chạy ca loop không giới hạn trên production; test trong môi trường cô lập với timeout bảo vệ.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Method `forward()` không tồn tại | Chọn nhầm ProxyExchange WebFlux hoặc artifact sai | Dùng `spring-cloud-gateway-proxyexchange-webmvc` đúng version |
| `ProxyExchange` argument không được resolve | Thiếu module/auto-configuration, sai MVC stack | Kiểm tra dependency, argument resolver, test context |
| Response hiện chuỗi `forward:/internal/...` | Controller dùng `@RestController` hoặc `@ResponseBody` | Đổi nguồn forward thành `@Controller`, return view instruction |
| `404 Not Found` sau forward | Target path không có mapping, context path sai | Kiểm tra target `@GetMapping`, request path |
| `405 Method Not Allowed` | Source POST, target chỉ GET | Căn chỉnh HTTP method giữa source và target |
| Client thấy 302 | Đang dùng redirect hoặc security login flow | Kiểm tra `redirect:`, Security, ingress |
| JSON body rỗng ở target POST | Servlet input stream đã bị đọc trước | Kiểm soát body consumption, wrapper/caching có giới hạn |
| MockMvc chỉ thấy forwardedUrl, chưa thấy JSON | Không có container dispatch đầy đủ trong mock | Test embedded server response cuối |
| Direct `/internal/**` trả dữ liệu nhạy cảm | Chỉ bảo vệ edge route | Bảo vệ target và test direct access |
| Sau forward quyền bị xử lý lạ | DispatcherType.FORWARD và security mappings | Test Servlet filter registrations, SecurityFilterChain |
| Request vô hạn/stack overflow | Forward loop | Chặn target trùng source, validation/graph checks |
| URI do client chọn dẫn tới handler admin | Forward target không được allowlist | Ánh xạ path cứng, deny sensitive targets |
| Không thấy route trong Gateway Actuator | Đang dùng Proxy Exchange MVC, không phải Server route | Quan sát Spring MVC mappings/controller |
| Không thấy `GatewayFilter` chạy | Proxy Exchange không chạy Gateway Server filter chain | Dùng Servlet filters/security hoặc chọn Gateway Server |
| Body/headers bị biến đổi khác dự kiến | Filter, argument resolver, content negotiation | Kiểm tra target và Servlet request thực tế |
| Forward sang service ở pod khác không hoạt động | Forward chỉ dành cho **local handler** | Dùng HTTP proxy/discovery, không dùng forward |
| CORS/CSRF lỗi | Chưa cấu hình Servlet Security/CORS/CSRF | Xử lý theo loại auth và origin thực tế |
| Dùng `forward:///...` trong `@Controller` | Lẫn cú pháp Server WebFlux | Dùng `proxy.forward("/path")` với MVC |
| 200 nhưng request không qua target mong muốn | Route/handler mapping khác, lỗi test assertion | Test `handledBy`, handler type và logs |

## 18. Bài thực hành cuối chương

**Bối cảnh:** Một ứng dụng Spring MVC có hai nhóm endpoint: API cũ ở `/legacy/products/{id}`, API nội bộ ở `/internal/products/{id}`; một endpoint khác dùng outbound HTTP proxy tới mock catalog service.

### Yêu cầu

1. Dùng đúng artifact **Proxy Exchange Web MVC** tương thích Spring Boot/Cloud BOM.
2. Tạo `@Controller` nhận `ProxyExchange<byte[]>`.
3. Tạo `@GetMapping("/legacy/products/{id}")` forward sang `/internal/products/{id}`.
4. Tạo `@RestController` target trả JSON với ID và một marker `handledBy`.
5. Xác minh `curl -i` không có HTTP 3xx redirect, body đến từ local handler.
6. Dùng `MockMvc` assert `forwardedUrl`; dùng embedded server assert final JSON/header.
7. Thử GET với query `lang=en`, xác nhận cách truyền parameters.
8. Thêm POST echo forward và test request body/method.
9. Đặt guard để không forward đến `/actuator`, `/admin` hoặc URL do client tự chọn.
10. Thêm Spring Security Servlet policy: direct `/internal/**` bị chặn theo business contract; forward hợp lệ không phá authorization.
11. Viết remote handler khác sử dụng `proxy.uri("http://localhost:8081/...").get()`, đo outbound HTTP calls.
12. So sánh error handling, latency và metrics của local forward với remote proxy.
13. Test một target không tồn tại và một loop trong sandbox đã giới hạn timeout, không triển khai loop vào production.
14. Ghi lại những điểm không thể sao chép trực tiếp từ Gateway Server WebFlux/MVC sang Proxy Exchange.

### Checklist kiểm tra trước production

- [ ] Đã chọn **Proxy Exchange Web MVC**, không nhầm với Server Web MVC starter.
- [ ] Controller khởi tạo forward dùng `@Controller`, không dùng `@RestController`/`@ResponseBody`.
- [ ] Dùng `proxy.forward("/local-path")`, không lẫn `forward:///...` của WebFlux.
- [ ] Target handler thực sự tồn tại trong cùng Servlet application.
- [ ] HTTP method và target mapping tương thích; POST không vô tình bị đổi thành GET.
- [ ] Request body chỉ được đọc theo thiết kế, không đòi replay stream không có cache.
- [ ] Không forward sau response commit.
- [ ] Đã chặn forward loop và không cho client quyết định arbitrary local target.
- [ ] Direct access đến internal paths được kiểm tra security phù hợp.
- [ ] `DispatcherType.FORWARD`, Servlet filters và Spring Security đã được test.
- [ ] Không coi “internal” trong URL là một lớp bảo mật.
- [ ] Các errors 400/401/403/404/405 được xử lý nhất quán với contract.
- [ ] Đã phân biệt forward, redirect, remote proxy và Java service call.
- [ ] HTTP proxy outbound dùng URI allowlist, timeout, TLS và secret handling đúng.
- [ ] Không giả định Proxy Exchange tự có toàn bộ Gateway Server predicates/filters.
- [ ] Có integration test chạy trên Servlet container thực.
- [ ] Logs/traces che token, cookie, PII; metrics không dùng raw request ID làm label.
- [ ] Đã kiểm tra dependency/package tương thích release train hiện tại.

## 19. Tổng kết và tài liệu tham khảo

**`ProxyExchange.forward(String)` trong Spring Cloud Gateway Proxy Exchange Web MVC** cho phép một **annotation-based MVC controller** chuyển request đến **local handler** trong cùng Servlet application. Đó không phải outbound HTTP proxy, không phải HTTP redirect, và cũng không phải `forward:///...` của Gateway Server WebFlux.

Trong Java, pattern cần nhớ là:

~~~java
@Controller
class EdgeController {
    @GetMapping("/edge/products/{id}")
    String product(@PathVariable long id,
                   ProxyExchange<byte[]> proxy) {
        return proxy.forward("/internal/products/" + id);
    }
}
~~~

Handler đích có thể là `@RestController` trả JSON. Điểm quan trọng nhất là **method ở nguồn trả view/forward instruction**, không biến string thành response body bằng `@RestController`. Để bảo đảm đúng nghiệp vụ, phải kiểm thử **không có redirect, đúng target, đúng HTTP method/body và security** ở cả direct request lẫn FORWARD dispatch.

Khi cần gọi microservice ở nơi khác, dùng `proxy.uri(...).get()/post()` hoặc Gateway Server với service discovery/load balancing; khi chỉ cần tái sử dụng logic Java, service method call có thể đơn giản hơn. Lựa chọn đúng giúp cổng vào microservices kết hợp được xác thực, rate limiting, retry, circuit breaker, TLS và observability **mà không đánh đồng các cơ chế routing khác stack**.

### Tài liệu tham khảo

- [Spring Cloud Gateway 5.x — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html).
- [Spring Cloud Gateway 4.3 — Proxy Exchange Web MVC](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html).
- [Spring Cloud Gateway — Tổng quan về Server và Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/intro.html).
- [Spring Cloud Gateway Server Web MVC — How It Works (để phân biệt với Proxy Exchange)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/how-it-works.html).
- [Spring Cloud Gateway Server WebFlux — Forward Routing Filter (cơ chế khác)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Framework — Spring Web MVC: View Resolution và forwarding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html).
- [Spring Framework — Spring Web MVC Controller Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
- [Servlet API — RequestDispatcher.forward](https://jakarta.ee/specifications/servlet/).
