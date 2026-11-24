# BeforeFilterFunctions, AfterFilterFunctions và HandlerFilterFunction

## 1. Một route MVC có thể can thiệp request và response như thế nào?

Trong **Spring Cloud Gateway Server Web MVC**, API Gateway nhận request từ client, so khớp **route predicate**, chạy các bộ lọc trước/sau khi proxy tới microservice, có thể thay đổi đường dẫn và header, dùng service discovery để chọn backend, kết hợp xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát hoạt động. Khác với biến thể **Server WebFlux**, Server Web MVC xây dựng trên **Servlet stack** và **Spring WebMvc.fn**.

Một yêu cầu thực tế:

1. Client gọi `GET /api/echo` vào Gateway.
2. Gateway chuyển đường dẫn thành `/echo` và thêm `X-Route-Tag: mvc-demo` trước khi gọi backend.
3. Backend trả dữ liệu với status 200.
4. Gateway gắn `X-Gateway-After: applied` vào response trả về client.
5. Nếu request mang cờ thử nghiệm `X-Lab-Block: yes`, một filter tùy biến phải **từ chối trước khi proxy**, không gọi backend.

Với Java Routes API của Gateway MVC, ba công cụ chính cho yêu cầu này là:

- **`BeforeFilterFunctions`**: tập hàm xử lý **request trước handler**; Java Routes API dùng `.before(...)`.
- **`AfterFilterFunctions`**: tập hàm xử lý **response sau handler**; Java Routes API dùng `.after(...)`.
- **`HandlerFilterFunction`**: filter tổng quát **bao quanh handler**, có thể làm việc trước và sau `next.handle(request)`, từ chối sớm hoặc điều phối logic khác; dùng `.filter(...)`.

Bài này thuộc chương **Server Web MVC** của module **SPRING_CLOUD_GATEWAY**, hướng tới việc sử dụng ba kiểu filter đúng trách nhiệm, không nhầm với `GlobalFilter`/`GatewayFilterFactory` của Server WebFlux hay `jakarta.servlet.Filter` của Servlet container.

Mục tiêu:

1. Hiểu luồng WebMvc.fn `RouterFunction → HandlerFunction → ServerResponse` của Gateway MVC.
2. Phân biệt contract và vị trí của `before`, `after`, `filter`.
3. Dùng các hàm có sẵn để thay đổi request/response headers và path.
4. Tự viết `Function<ServerRequest, ServerRequest>`, `BiFunction<ServerRequest, ServerResponse, ServerResponse>` và `HandlerFilterFunction<ServerResponse, ServerResponse>`.
5. Chạy lab Gateway MVC → backend echo và thử nhánh từ chối.
6. Nắm rõ phạm vi filter, lỗi, thứ tự xử lý, Servlet Filter, body handling và tác động bảo mật/vận hành.

> **Phạm vi:** Các code Java bên dưới hướng đến Spring Cloud Gateway **Server Web MVC**, sử dụng WebMvc.fn đồng bộ trên Servlet runtime. Khi ứng dụng thực tế dùng Server WebFlux, cần viết API reactive tương ứng, không đổi tên import một cách cơ học.

## 2. Nền tảng WebMvc.fn trong Gateway Server Web MVC

Spring WebMvc.fn cung cấp một cách khai báo route theo hàm, bên cạnh mô hình `@Controller`:

| Khái niệm | Kiểu Java | Trách nhiệm |
| --- | --- | --- |
| Route predicate | `RequestPredicate` | Xác định request có khớp route không |
| Request | `ServerRequest` | Truy cập method, path, headers, params, body |
| Handler | `HandlerFunction<ServerResponse>` | Xử lý một request, trả `ServerResponse` |
| Response | `ServerResponse` | Chứa status, headers và body |
| Route | `RouterFunction<ServerResponse>` | Chọn handler khi request khớp |
| Filter tổng quát | `HandlerFilterFunction<T,R>` | Bao quanh handler hoặc filter tiếp theo |
| Bộ tạo route | `RouterFunctions.Builder` | Ghép predicate, handler và before/after/filter |

Trong Gateway MVC, handler proxy HTTP do Gateway cung cấp là **`HandlerFunctions.http()`**. Địa chỉ backend có thể được thiết lập bằng hàm **`BeforeFilterFunctions.uri(...)`**, thường sử dụng cùng **`GatewayRouterFunctions.route("route-id")`** để có metadata route ID cho các filter nâng cao.

~~~mermaid
flowchart LR
    C["Client"] --> S["DispatcherServlet"]
    S --> P["RouterFunction<br/>match predicate"]
    P --> F["HandlerFilterFunction chain"]
    F --> B["Before request transformations"]
    B --> H["HandlerFunctions.http()"]
    H --> U["Backend microservice"]
    U --> A["After response transformations"]
    A --> C
~~~

Sơ đồ là mô hình khái niệm. Một `HandlerFilterFunction` có thể chạy **cả trước và sau** khi gọi next; các hàm `before/after` được ghép vào chuỗi bằng cơ chế thích nghi của WebMvc.fn. Thứ tự chính xác khi có nhiều filter/nested routes cần được kiểm thử, không suy tuyệt đối chỉ từ vị trí trên sơ đồ.

### 2.1. So sánh Web MVC và WebFlux

| Vấn đề | Gateway Server Web MVC | Gateway Server WebFlux |
| --- | --- | --- |
| Web stack | Spring MVC/WebMvc.fn, Servlet/Tomcat/Jetty | Spring WebFlux, reactive Netty |
| Kiểu request | `org.springframework.web.servlet.function.ServerRequest` | `ServerWebExchange`, `ServerHttpRequest` |
| Route Java | `RouterFunction<ServerResponse>` | `RouteLocator` hoặc cấu hình routes |
| Proxy handler | `HandlerFunctions.http()` | Netty routing filter trong reactive chain |
| Filter tùy biến | `HandlerFilterFunction`/`before`/`after` | `GatewayFilter`/`GlobalFilter` |
| Kết quả filter | `ServerResponse` trực tiếp | Thường `Mono<Void>` |
| Threading | Servlet request threads, blocking I/O có kiểm soát | Non-blocking reactive event loop |
| Custom filter classes | `BeforeFilterFunctions`, `AfterFilterFunctions` | `GatewayFilterFactory`, `GlobalFilter` |

**Đừng viết** `Mono<Void> filter(ServerWebExchange, GatewayFilterChain)` vào route Web MVC rồi mong `.before(...)` nhận nó. Ngược lại, một `HandlerFilterFunction` dùng `next.handle(...)` là API **Servlet/WebMvc.fn**, không phải `WebFilter` của WebFlux.

### 2.2. Dùng starter đúng phiên bản

Theo tài liệu Spring Cloud Gateway:

| Dòng Gateway Server MVC | Starter Maven | Namespace route YAML |
| --- | --- | --- |
| 4.2.x (tên “Server MVC”) | `spring-cloud-starter-gateway-mvc` | `spring.cloud.gateway.mvc.routes` |
| 4.3.x (“Server Web MVC”) | `spring-cloud-starter-gateway-server-webmvc` | `spring.cloud.gateway.server.webmvc.routes` |
| 5.0.x/5.1.x (“Server Web MVC”) | `spring-cloud-starter-gateway-server-webmvc` | `spring.cloud.gateway.server.webmvc.routes` |

Luôn dùng **Spring Cloud BOM tương thích Spring Boot** đang chạy. Không ghép các release tùy ý. Các ví dụ Java Routes API phía dưới tương ứng các phiên bản hỗ trợ `GatewayRouterFunctions`, `HandlerFunctions.http()` và before/after/filter; kiểm tra Java API của bản patch cụ thể khi nâng cấp.

Ví dụ dependency cho Gateway MVC dòng mới:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
~~~

Gateway MVC chạy trên Servlet container. **Không thêm Starter WebFlux để “bật BeforeFilterFunctions”**: đây là một hệ filter khác. Với backend echo của lab, dùng Spring MVC/Servlet cũng là lựa chọn dễ hiểu.

## 3. Bản chất của ba API filter

### 3.1. BeforeFilterFunctions — chỉ biến đổi request

Kiểu đầu vào của `RouterFunctions.Builder.before(...)`:

~~~java
java.util.function.Function<ServerRequest, ServerRequest>
~~~

Một before function nhận request ban đầu và trả request dùng cho phần xử lý tiếp theo:

~~~java
Function<ServerRequest, ServerRequest> before =
        request -> ServerRequest.from(request)
                .header("X-Lab-Before", "added")
                .build();
~~~

Trong code, `ServerRequest.from(request)` dựng một request mới có header bổ sung. Ta **không** cần gọi `next.handle(...)` vì before processor chỉ tập trung vào request. Tài liệu Gateway hướng dẫn ưu tiên dùng các hàm chuyên biệt trong `BeforeFilterFunctions` khi chúng đáp ứng mục tiêu, ví dụ:

~~~java
BeforeFilterFunctions.uri("http://127.0.0.1:9091")
BeforeFilterFunctions.stripPrefix(1)
BeforeFilterFunctions.addRequestHeader("X-Route-Tag", "mvc-demo")
~~~

**Chú ý header trùng:** `addRequestHeader` có ý nghĩa “thêm”; khi bảo vệ header danh tính/ủy quyền, không mặc định việc thêm sẽ loại bỏ một giá trị client đã gửi trước đó. Dùng hàm đặt/xóa header theo mục tiêu cụ thể và xác minh header backend nhận.

### 3.2. AfterFilterFunctions — can thiệp response sau handler

Kiểu đầu vào của `RouterFunctions.Builder.after(...)`:

~~~java
java.util.function.BiFunction<ServerRequest, ServerResponse, ServerResponse>
~~~

After function thấy cả request và response mà handler/filter bên trong đã trả về:

~~~java
BiFunction<ServerRequest, ServerResponse, ServerResponse> after =
        (request, response) -> {
            response.headers().add("X-Lab-After", "added");
            return response;
        };
~~~

Ví dụ tích hợp sẵn:

~~~java
AfterFilterFunctions.addResponseHeader("X-Gateway-After", "applied")
AfterFilterFunctions.setResponseHeader("X-Response-Policy", "v2")
~~~

`addResponseHeader` thêm một giá trị; `setResponseHeader` thay giá trị cùng tên theo chính sách của Gateway. Với response chứa header bảo mật đơn trị, việc **append trùng** có thể làm client/proxy diễn giải khác nhau. Trong API Gateway, hãy quyết định rõ nên *set*, *add* hay *remove*.

Spring WebMvc.fn mô tả `ServerRequest` và `ServerResponse` là các interface thiên về bất biến, nhưng Spring Cloud Gateway MVC có một số implementation cho phép thay đổi header đáp ứng nhu cầu proxy. Mẫu dùng `response.headers().add(...)` là cách chính tài liệu Gateway trình bày cho custom after filter. **Không suy từ đó rằng mọi `ServerResponse` do mọi thư viện tạo ra đều có thể sửa vô hạn, kể cả khi response đã được commit.**

### 3.3. HandlerFilterFunction — bao quanh toàn bộ handler

Contract tổng quát:

~~~java
@FunctionalInterface
public interface HandlerFilterFunction<T extends ServerResponse,
        R extends ServerResponse> {
    R filter(ServerRequest request, HandlerFunction<T> next)
            throws Exception;
}
~~~

Lưu ý đó là **chữ ký minh họa contract**, không phải yêu cầu tự khai báo lại interface Spring. Với kiểu phổ biến:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse>
~~~

ta có thể:

- Đọc request **trước** khi gọi `next.handle(request)`.
- Tạo request mới rồi truyền vào `next.handle(modifiedRequest)`.
- **Ngắt chuỗi** bằng một `ServerResponse` khác mà không gọi next.
- Đọc response sau khi next trả về, chỉnh header hoặc ghi metrics.
- Đặt `try/finally` để đo thời gian kể cả khi downstream lỗi.

Ví dụ:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> audit =
        (request, next) -> {
            long started = System.nanoTime();
            try {
                ServerResponse response = next.handle(request);
                response.headers().add("X-Lab-HandlerFilter", "passed");
                return response;
            } finally {
                long elapsed = System.nanoTime() - started;
                // Gửi elapsed vào metrics/logs đã kiểm soát.
            }
        };
~~~

**Không cần dùng HandlerFilterFunction cho mọi việc.** Nếu chỉ thêm header trước request, `.before(...)` diễn đạt ý định rõ hơn; nếu chỉ thêm response header, `.after(...)` rõ hơn. Dùng `.filter(...)` khi bạn thật sự cần quyết định **trước/sau/short-circuit/error handling**.

### 3.4. So sánh nhanh

| Đặc điểm | `.before(...)` | `.after(...)` | `.filter(...)` |
| --- | --- | --- | --- |
| Contract chính | `Function<ServerRequest,ServerRequest>` | `BiFunction<ServerRequest,ServerResponse,ServerResponse>` | `HandlerFilterFunction<T,R>` |
| Có truy cập request? | Có | Có | Có |
| Có response của handler? | Chưa | Có | Có, nếu gọi next |
| Có thể không gọi handler? | Không theo contract processor | Không | Có |
| Mục đích điển hình | Path/header/URI đầu vào | Response headers/status policy phù hợp | Auth gate, audit timing, phối hợp logic |
| Cách viết Java DSL | `.before(fn)` | `.after(fn)` | `.filter(fn)` |
| Độ phức tạp | Thấp | Thấp | Cao hơn, quản lý next/lỗi |

Trong cả ba trường hợp, filter **chỉ chạy đối với routes thuộc phạm vi router builder đó sau khi predicate match**, không tự áp dụng cho mọi request trong Servlet container.

## 4. Một route Java dùng cả before, after và filter

Ví dụ sau chỉ dùng **một ứng dụng Gateway MVC** và **một backend echo**. Gateway lắng nghe `localhost:8080`, backend `localhost:9091`.

### 4.1. Lớp khởi động Gateway

Với project có starter `spring-cloud-starter-gateway-server-webmvc` (dòng 4.3+/5.x) và Spring Cloud BOM tương thích:

`src/main/java/demo/mvcgateway/MvcGatewayApplication.java`:

~~~java
package demo.mvcgateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcGatewayApplication.class, args);
    }
}
~~~

`src/main/resources/application.yml` của Gateway:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: mvc-filter-lab-gateway
~~~

Trong cách khai báo **Java Routes API** bên dưới, không cần khai thêm cùng route ID trong YAML.

### 4.2. Viết các hàm filter tùy biến có kiểu rõ ràng

`src/main/java/demo/mvcgateway/DemoMvcFilters.java`:

~~~java
package demo.mvcgateway;

import java.util.function.BiFunction;
import java.util.function.Function;

import org.springframework.http.HttpStatus;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

public final class DemoMvcFilters {

    private DemoMvcFilters() {
    }

    // BEFORE: tạo một ServerRequest mới với header bổ sung.
    public static Function<ServerRequest, ServerRequest> beforeMarker() {
        return request -> ServerRequest.from(request)
                .header("X-Mvc-Before", "custom-before")
                .build();
    }

    // AFTER: làm việc với response do handler/filter đã trả về.
    public static BiFunction<ServerRequest, ServerResponse, ServerResponse>
            afterMarker() {
        return (request, response) -> {
            response.headers().add(
                    "X-Mvc-After-Custom", "custom-after");
            return response;
        };
    }

    // HANDLER FILTER: có thể short-circuit hoặc bao quanh next.
    public static HandlerFilterFunction<ServerResponse, ServerResponse>
            blockLabRequest() {

        return (request, next) -> {
            String labFlag =
                    request.headers().firstHeader("X-Lab-Block");

            if ("yes".equalsIgnoreCase(labFlag)) {
                // Chỉ là cờ lab; KHÔNG phải bảo mật/auth thật.
                return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .header("X-Mvc-Decision", "blocked")
                        .body("Blocked by the demo filter");
            }

            long start = System.nanoTime();
            try {
                ServerResponse response = next.handle(request);
                response.headers().add(
                        "X-Mvc-Decision", "forwarded");
                return response;
            } finally {
                long elapsedNanos = System.nanoTime() - start;
                // Lab: thay bằng metric histogram cardinality thấp.
                // Không log request body, Cookie hoặc Authorization.
            }
        };
    }
}
~~~

Lưu ý:

- `beforeMarker()` là **Function**, không gọi `next` và không nhận response.
- `afterMarker()` là **BiFunction**, xử lý response đã có; tên method là tùy chọn nhưng kiểu trả về phải hợp đồng của `.after(...)`.
- `blockLabRequest()` trả **HandlerFilterFunction**, kiểm tra cờ lab và có thể trả `403` khi **chưa gọi next**.
- Khi `next.handle(request)` trả về, filter gắn `X-Mvc-Decision: forwarded`. `finally` hữu ích để ghi thời gian kể cả khi có lỗi, nhưng không tự biến exception thành response 200.
- Code không copy request body hay giữ state theo request trong field dùng chung. Các hàm tạo filter có thể được dùng cho nhiều request đồng thời.
- Trường `elapsedNanos` cố ý chỉ phục vụ gợi ý metrics; bài không thêm hệ thống monitoring thật.

**Quan trọng:** Header `X-Lab-Block` được client tự gửi, nên là **công cụ kiểm thử nhánh short-circuit**, tuyệt đối không phải API authorization production. Client cũng có thể không gửi header này hoặc đổi giá trị tùy ý.

### 4.3. Nối các filter vào Java RouterFunction

`src/main/java/demo/mvcgateway/MvcRouteConfig.java`:

~~~java
package demo.mvcgateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static demo.mvcgateway.DemoMvcFilters.afterMarker;
import static demo.mvcgateway.DemoMvcFilters.beforeMarker;
import static demo.mvcgateway.DemoMvcFilters.blockLabRequest;
import static org.springframework.cloud.gateway.server.mvc.filter.AfterFilterFunctions.addResponseHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.addRequestHeader;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.stripPrefix;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration(proxyBeanMethods = false)
public class MvcRouteConfig {

    @Bean
    RouterFunction<ServerResponse> mvcFilterLabRoute() {
        return route("mvc-filter-lab")
                .GET("/proxy/echo", http())
                .before(uri("http://127.0.0.1:9091"))
                .before(stripPrefix(1))
                .before(addRequestHeader(
                        "X-Route-Tag", "mvc-route"))
                .before(beforeMarker())
                .filter(blockLabRequest())
                .after(addResponseHeader(
                        "X-Gateway-After", "applied"))
                .after(afterMarker())
                .build();
    }
}
~~~

**Từng dòng quan trọng:**

1. `route("mvc-filter-lab")` tạo builder có route ID; điều này có ích cho metadata của các filter Gateway.
2. `.GET("/proxy/echo", http())` chọn request GET đúng path và dùng handler HTTP proxy.
3. `.before(uri(...))` cung cấp destination URI cho `HandlerFunctions.http()`. Các overload `http(String)`/`http(URI)` cũ đã bị **deprecated từ Gateway 4.1.7**; ưu tiên `http()` kết hợp `uri()`.
4. `.before(stripPrefix(1))` bỏ phân đoạn `proxy` để backend nhận `/echo`. Đây là trước routing, không sửa response.
5. `.before(addRequestHeader(...))` gắn header do Gateway quản lý vào request đi xuống backend.
6. `.before(beforeMarker())` dùng **Function tùy biến**, không phải tên của một built-in.
7. `.filter(blockLabRequest())` đặt một **HandlerFilterFunction** có thể từ chối request và bao quanh handler.
8. `.after(addResponseHeader(...))` áp dụng built-in **AfterFilterFunctions** để có header trả về client.
9. `.after(afterMarker())` áp dụng **BiFunction tùy biến** trên response.

Lệnh gọi `.before(...).after(...).filter(...)` là cách ghép theo Java Routes API của WebMvc.fn. Các filter có thể được thực thi theo cấu trúc hàm bọc/ghép chứ không đơn giản như một danh sách chạy từ trên xuống rồi quay ngược; khi đổi thứ tự hoặc thêm nested routes, **kiểm tra điều kiện thực tế bằng tests**, đặc biệt đối với short-circuit và retry.

### 4.4. Dùng `GatewayRouterFunctions.route()` hay `RouterFunctions.route()`?

Spring Framework cung cấp:

~~~java
org.springframework.web.servlet.function.RouterFunctions.route()
~~~

Gateway MVC còn cung cấp:

~~~java
org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route(
        "mvc-filter-lab")
~~~

Tài liệu Gateway mô tả bản Gateway thêm **route ID metadata** vào request attributes, giúp các filter nâng cao xác định route. Với route proxy sử dụng filter nâng cao, ưu tiên `GatewayRouterFunctions.route("...")`. Đối với WebMvc.fn handler thông thường, `RouterFunctions.route()` vẫn là API hợp lệ.

## 5. Backend echo để kiểm chứng đúng phía request/response

Backend echo là một **ứng dụng Spring Boot MVC độc lập** tại port 9091. Nó nhận request và phản ánh những header Gateway gửi tới.

### 5.1. Cấu hình backend

Dependency Maven cho backend:

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
~~~

`src/main/java/demo/mvcbackend/EchoBackendApplication.java`:

~~~java
package demo.mvcbackend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoBackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoBackendApplication.class, args);
    }
}
~~~

`src/main/java/demo/mvcbackend/EchoController.java`:

~~~java
package demo.mvcbackend;

import java.util.LinkedHashMap;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @GetMapping("/echo")
    public Map<String, Object> echo(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("source", "mvc-backend");
        result.put("path", request.getRequestURI());
        result.put("routeTag",
                request.getHeader("X-Route-Tag"));
        result.put("beforeMarker",
                request.getHeader("X-Mvc-Before"));
        result.put("clientHeader",
                request.getHeader("X-Client-Note"));
        return result;
    }
}
~~~

Backend **không** tự biết lớp `DemoMvcFilters` hay `RouterFunction` của Gateway; nó chỉ thấy HTTP request đã được proxy. Đặc biệt, các header **response** như `X-Gateway-After` không nhất thiết xuất hiện trong **body echo** của backend, vì chúng được thêm ở đường response sau khi backend đã xử lý.

### 5.2. Chạy lab

Mở hai terminal ở đúng thư mục dự án tương ứng:

~~~bash
# Terminal backend: project mvc-backend
./mvnw spring-boot:run

# Terminal Gateway: project mvc-gateway
./mvnw spring-boot:run
~~~

Trên Windows, dùng `mvnw.cmd spring-boot:run`. Tài liệu này đưa ra **hướng dẫn tự thực hành**, không khẳng định đã thực hiện build/test trong repository.

Kiểm thử backend trực tiếp:

~~~bash
curl -i "http://127.0.0.1:9091/echo"
~~~

Kỳ vọng response từ backend có `"path":"/echo"` và các header do Gateway thêm thường ở trạng thái `null`, vì request không đi qua Gateway.

### 5.3. Gửi request qua Gateway

~~~bash
curl -i "http://127.0.0.1:8080/proxy/echo" \
  -H "X-Client-Note: sent-by-curl"
~~~

Khi route/proxy/filter hoạt động đúng, body có dạng:

~~~json
{
  "source": "mvc-backend",
  "path": "/echo",
  "routeTag": "mvc-route",
  "beforeMarker": "custom-before",
  "clientHeader": "sent-by-curl"
}
~~~

Và response header (thứ tự/định dạng thực tế có thể khác):

~~~http
HTTP/1.1 200 OK
X-Gateway-After: applied
X-Mvc-After-Custom: custom-after
X-Mvc-Decision: forwarded
Content-Type: application/json
~~~

Điểm quan sát:

| Bằng chứng | Nơi thấy | Filter/chức năng tạo ra |
| --- | --- | --- |
| `path=/echo` | JSON backend echo | `BeforeFilterFunctions.stripPrefix(1)` |
| `routeTag=mvc-route` | JSON backend echo | `BeforeFilterFunctions.addRequestHeader` |
| `beforeMarker=custom-before` | JSON backend echo | Custom `Function<ServerRequest,ServerRequest>` |
| `X-Gateway-After: applied` | HTTP response tới client | `AfterFilterFunctions.addResponseHeader` |
| `X-Mvc-After-Custom` | HTTP response tới client | Custom `BiFunction<ServerRequest,ServerResponse,ServerResponse>` |
| `X-Mvc-Decision` | HTTP response tới client | Custom `HandlerFilterFunction` |

Nếu backend thấy before header nhưng client không thấy after header, kiểm tra xem route có thật sự dùng `.after(...)`, response có bị commit sớm hoặc được thay bởi error handler/Servlet Filter khác hay không. Ngược lại, nếu client chỉ thấy header response mà backend không có marker request, kiểm tra before function và route path.

### 5.4. Kiểm chứng nhánh short-circuit

~~~bash
curl -i "http://127.0.0.1:8080/proxy/echo" \
  -H "X-Lab-Block: yes"
~~~

Theo `blockLabRequest()`, kết quả cơ bản được mong đợi:

~~~http
HTTP/1.1 403 Forbidden
X-Mvc-Decision: blocked

Blocked by the demo filter
~~~

**Backend không được nhận thêm một request mới** do lệnh trên, vì filter trả response trước khi gọi `next.handle(request)`. Với các after filters ở cùng builder, việc chúng có được áp dụng cho response bị short-circuit phụ thuộc **cách các filter được ghép trong chain**; không nên dùng sự hiện diện của `X-Gateway-After` làm điều kiện khẳng định chung cho mọi cách sắp xếp. Hãy test thực tế đúng version và thứ tự khai báo.

Để kiểm chứng không gọi backend, thêm một counter/log trên backend chỉ ghi route ID và số lần vào endpoint, sau đó so sánh trước/sau test. Không bật raw HTTP wiretap chứa secret ở production.

### 5.5. Negative tests cho route predicate

~~~bash
# Route được khai báo GET, không phải POST:
curl -i -X POST "http://127.0.0.1:8080/proxy/echo"

# Path khác:
curl -i "http://127.0.0.1:8080/proxy/other"
~~~

Nếu không có route/handler khác, Gateway thường trả 404/405 tùy cách mapping Servlet/WebMvc.fn. **Không kết luận custom filter chạy sai** nếu request chưa khớp predicate nên filter không được gọi.

### 5.6. Không gửi cờ lab vào production

Cờ `X-Lab-Block` chỉ giúp quan sát trường hợp `HandlerFilterFunction` trả response sớm. Nếu dùng nó để quyết định bảo mật, client có thể bỏ header và vượt qua policy. Production phải dùng **Spring Security trên Servlet stack**, kiểm tra JWT/session/authorization, và chính sách truy cập ở backend. Không chấp nhận header tự khai là bằng chứng danh tính.

## 6. Cấu hình built-in filters bằng YAML thay vì Java Routes API

Các built-in filter như `AddRequestHeader`, `StripPrefix` và `AddResponseHeader` còn được Gateway Server MVC hỗ trợ qua cấu hình route bên ngoài. Tên filter viết trong YAML dùng **factory/DSL discovery**, không giống việc gọi trực tiếp một static Java method.

### 6.1. Gateway Server Web MVC 4.3.x/5.x

`application.yml`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: mvc-header-yaml
              uri: http://127.0.0.1:9091
              predicates:
                - Path=/proxy/echo
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Route-Tag,yaml-route
                - AddResponseHeader=X-Gateway-After,applied
~~~

Với route này, `GET /proxy/echo` thường được gửi xuống `http://127.0.0.1:9091/echo`. Backend echo nhận `X-Route-Tag: yaml-route`, client nhận thêm `X-Gateway-After: applied`. **Không có** `DemoMvcFilters.beforeMarker()/afterMarker()/blockLabRequest()` ở cấu hình trên, vì chúng là các hàm **tùy biến** của ví dụ Java chứ không tự động được phát hiện từ tên method.

**Không đồng thời tạo cùng route ID/path với Java bean ở mục 4** rồi dùng kết quả để suy điều gì đã chạy. Hãy chọn **một trong hai cách** cho một lần thử, hoặc đặt các route trên path riêng và kiểm chứng route ID bằng logs/Actuator.

### 6.2. Gateway Server MVC 4.2.x

Dòng cũ hơn dùng `spring.cloud.gateway.mvc.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: mvc-header-yaml
            uri: http://127.0.0.1:9091
            predicates:
              - Path=/proxy/echo
              - Method=GET
            filters:
              - StripPrefix=1
              - AddRequestHeader=X-Route-Tag,yaml-route
              - AddResponseHeader=X-Gateway-After,applied
~~~

**Không đổi mỗi namespace theo cảm tính**: Gateway 4.2.x/4.3.x có sự thay đổi tên starter và prefix configuration. Chọn đúng BOM, starter, namespace cho release đang chạy, rồi kiểm tra route thực sự được nạp.

### 6.3. Java và YAML có mức tùy biến khác nhau

| Nhu cầu | Java Routes API | Route YAML |
| --- | --- | --- |
| Truyền static built-in before/after | Gọi `.before(addRequestHeader(...))` | Khai báo `AddRequestHeader=...` |
| Route ID, predicate, URI | `route("id").GET(...).before(uri(...))` | `id/uri/predicates` |
| Filter custom có lambda từ application code | Gọi `.before(customFn)`, `.after(customFn)`, `.filter(customFn)` | **Cần đăng ký discovery/supplier** nếu muốn tham chiếu bằng YAML |
| Loại bỏ payload lớn, retry, circuit breaker | Chọn bộ filter chuyên biệt tương ứng | Chọn factory/config tương ứng |
| Kiểm soát compile-time | Java compiler có thể bắt mismatch contract | Binding/argument conversion có thể lỗi khi load route |
| Thay đổi runtime | Deploy Java code hoặc cơ chế nạp route phù hợp | Có thể lấy từ config server/repository nếu hệ thống hỗ trợ |

### 6.4. Đăng ký custom HandlerFilterFunction cho external configuration

Theo tài liệu **Writing Custom Predicates and Filters** của Gateway Server MVC, muốn dùng một **custom filter** trong configuration file, cần đăng ký một **Supplier bean** để bộ lọc được discover. `SimpleFilterSupplier` là lựa chọn thuận tiện khi các static methods trong một class trả về `HandlerFilterFunction`.

Trong ví dụ, `DemoMvcFilters.blockLabRequest()` là static method trả `HandlerFilterFunction<ServerResponse,ServerResponse>`. Có thể khai báo:

~~~java
package demo.mvcgateway;

import org.springframework.cloud.gateway.server.mvc.filter.SimpleFilterSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class DemoMvcFilterSupplier extends SimpleFilterSupplier {
    DemoMvcFilterSupplier() {
        super(DemoMvcFilters.class);
    }
}

@Configuration(proxyBeanMethods = false)
class CustomFilterSupplierConfiguration {
    @Bean
    DemoMvcFilterSupplier demoMvcFilterSupplier() {
        return new DemoMvcFilterSupplier();
    }
}
~~~

Từ đó cơ chế `FilterDiscoverer` có thể phát hiện những static methods phù hợp. **Không coi mọi static Function/BiFunction trong class là tự được chuyển thành filter cấu hình**: tài liệu của `SimpleFilterSupplier` nói rõ hướng tới methods trả `HandlerFilterFunction`. Nếu cần expose một before/after tự viết qua YAML, có thể tạo wrapper bằng các adapter của `HandlerFilterFunction` hoặc tổ chức supplier/factory phù hợp.

Trước khi đưa filter custom vào config external:

1. Kiểm tra tên filter mà discoverer đăng ký ở đúng version.
2. Kiểm tra bind args, kiểu dữ liệu, giá trị mặc định và constraints.
3. Chạy integration test cho YAML, không chỉ unit test lambda.
4. Bảo đảm filter được đặt vào đúng route/đúng thứ tự.
5. Không đưa endpoint lab như `X-Lab-Block` ra production.

**Không nên ghi `BlockLabRequest` vào YAML rồi giả định chắc chắn framework đặt đúng tên** nếu chưa kiểm chứng naming/discovery của bản thư viện. Tài liệu Spring cũng mô tả đăng ký `FilterSupplier` qua `META-INF/spring.factories` kiểu cũ là deprecated; ưu tiên Spring bean theo hướng dẫn dòng hiện hành.

## 7. Adaptation: vì sao before và after cũng là filter?

WebMvc.fn có cơ chế chuyển hai function chuyên biệt thành `HandlerFilterFunction`:

~~~java
HandlerFilterFunction.ofRequestProcessor(beforeFunction)
HandlerFilterFunction.ofResponseProcessor(afterFunction)
~~~

Ví dụ trong Java:

~~~java
package demo.mvcgateway;

import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerResponse;

class FilterAdapters {
    static HandlerFilterFunction<ServerResponse, ServerResponse>
            asBeforeFilter() {
        return HandlerFilterFunction.ofRequestProcessor(
                DemoMvcFilters.beforeMarker());
    }

    static HandlerFilterFunction<ServerResponse, ServerResponse>
            asAfterFilter() {
        return HandlerFilterFunction.ofResponseProcessor(
                DemoMvcFilters.afterMarker());
    }
}
~~~

Nhờ vậy, ba dạng trên đều có thể tham gia một **chuỗi HandlerFilterFunction** của WebMvc.fn. Dù vậy, **chọn `.before(...)`/`.after(...)` khi phù hợp**: người đọc code dễ nhận biết filter chỉ đọc/sửa request hay response, và tránh tự xây logic next không cần thiết.

### 7.1. Ba cách biểu đạt cùng một ý định đơn giản

Thêm header vào request:

~~~java
// Cách A: WebMvc.fn before processor (nên dùng khi chỉ thay request)
.before(request -> ServerRequest.from(request)
        .header("X-Lab-Before", "added")
        .build())

// Cách B: Gateway built-in BeforeFilterFunctions
.before(BeforeFilterFunctions.addRequestHeader(
        "X-Lab-Before", "added"))

// Cách C: dạng adapter dưới lớp HandlerFilterFunction
.filter(HandlerFilterFunction.ofRequestProcessor(
        DemoMvcFilters.beforeMarker()))
~~~

Đoạn trên là ba biến thể **độc lập**; không dùng cả ba cùng lúc rồi mong chỉ có một header. Nếu dùng các hàm “add”, nhiều giá trị có thể bị ghi trùng.

### 7.2. Khi nào dùng FilterFunctions thay vì Before/AfterFilterFunctions?

Gateway Server MVC cung cấp `org.springframework.cloud.gateway.server.mvc.filter.FilterFunctions` như lớp chứa các bản **HandlerFilterFunction** đã thích nghi từ trước/sau. Tài liệu khuyến nghị ưu tiên **`BeforeFilterFunctions` và `AfterFilterFunctions` chuyên biệt** khi có thể, vì biểu đạt ý định rõ hơn.

Ví dụ, để đặt backend URI trước khi handler chạy, `BeforeFilterFunctions.uri(...)` là tự nhiên hơn một wrapper tổng quát phải đọc cả request và response. Để thêm response header, `AfterFilterFunctions.addResponseHeader(...)` dễ kiểm tra hơn một filter vừa đụng request vừa đụng response mà không có lý do.

### 7.3. Advanced filter không chỉ “before” hoặc “after”

Một số chức năng cần kiểm soát cả trước lẫn sau proxy, hoặc thậm chí thử lại handler:

| Nhóm filter MVC | Trách nhiệm thường gặp |
| --- | --- |
| `BodyFilterFunctions` | Đọc hoặc biến đổi body, phải hiểu chi phí buffering |
| `Bucket4jFilterFunctions` | Rate limiting với chính sách lưu bucket phù hợp |
| `CircuitBreakerFilterFunctions` | Bao quanh backend call, trả fallback khi cần |
| `RetryFilterFunctions` | Thử lại những lỗi được phép, có idempotency/replay constraints |
| `LoadBalancerFilterFunctions` | Chọn downstream instance từ service discovery |
| `TokenRelayFilterFunctions` | Chuyển token theo security context/policy phù hợp |

Những nhóm đó được tài liệu Gateway xếp vào **Advanced Filter Functions**, không chỉ là hai thao tác “thêm một header trước/sau”. **Không tự thay thế retry/circuit breaker bằng vòng lặp `next.handle(...)` tùy ý**: cần xét bảo toàn request body, lỗi kết nối, trạng thái downstream, timeout và side effects.

## 8. Thứ tự và phạm vi filter trong WebMvc.fn

### 8.1. Filter áp dụng cho router builder đã khai báo

Theo Spring Framework, `before`, `after` và `filter` được gắn vào **RouterFunctions.Builder**. Chúng áp dụng cho các routes **trong builder đó**, không mặc nhiên cho tất cả controllers trong Servlet application.

Ví dụ cấu trúc:

~~~text
Router A:
  GET /public/catalog
  before(add X-Catalog)   -> chỉ các routes thuộc Router A

Router B:
  GET /internal/health
  không có filter trên     -> không tự nhận X-Catalog

Servlet Filter:
  chạy ở mức Servlet filter chain theo URL/mapping/order
  có thể bao Router A, Router B và @Controller
~~~

Khi dùng nested routes, filter khai báo ở nested builder áp dụng cho nhóm nested routes, **không tự áp lên top-level siblings**. Spring WebMvc.fn docs có ví dụ `.path("/person", nestedBuilder -> ... .before(...))` và một `.after(...)` ở builder cha áp dụng cho tất cả routes của builder cha.

### 8.2. Trước và sau không đồng nghĩa “trước rồi sau đúng thứ tự dòng”

Với nhiều filter:

~~~java
.before(beforeA())
.before(beforeB())
.filter(aroundC())
.after(afterD())
~~~

Mô hình chung là **composition** của functions với handler nằm trong. Logic trước khi gọi next có thể đi theo một thứ tự, còn logic sau next trở ra có thể theo hướng ngược; cách chain builder/nested routes ghép filters là yếu tố quyết định. Không tuyên bố mọi phiên bản luôn chạy `A → B → C → Handler → D` theo đúng thứ tự văn bản.

Hãy kiểm thử bằng một **trace list per request** hoặc một backend echo với headers phân biệt. Không dùng singleton mutable list trong bean để ghi dấu vết requests concurrent; dùng dữ liệu per-request hoặc test-specific recording.

### 8.3. Route predicate phải match trước

Các filter thuộc một route không có quyền quyết định lại việc request đã match một route khác. Nếu request `POST /proxy/echo` nhưng chỉ khai báo `.GET("/proxy/echo", http())`, filter của GET route thường không chạy.

Khi test, luôn phân biệt:

- 404/405 do predicate/method không khớp.
- 403 do `HandlerFilterFunction` short-circuit.
- 502/503 do backend proxy/transport lỗi.
- 401/403 do Spring Security servlet chain.
- 429 do rate limiter chuyên biệt.

Mã HTTP giống nhau có thể phát sinh từ **nhiều tầng khác nhau**. Cần route ID, trace span và logs đã làm sạch để phân biệt.

### 8.4. Servlet Filter và HandlerFilterFunction không cùng phạm vi

| `jakarta.servlet.Filter` | `HandlerFilterFunction` WebMvc.fn |
| --- | --- |
| Được Servlet container/Servlet filter chain gọi | Chạy trong functional handler/route đã match |
| Nhận `ServletRequest`/`ServletResponse` và `FilterChain` | Nhận `ServerRequest` và `HandlerFunction<T> next` |
| Có thể bao cả DispatcherServlet, annotated controllers, WebMvc.fn | Gắn vào router builder cụ thể |
| Phù hợp security/cross-cutting ở tầng Servlet | Phù hợp route-specific proxy request/response |
| Thứ tự có thể dùng Filter registration/`Ordered` | Thứ tự theo composition của WebMvc.fn builder |

**Spring Security MVC** thường hoạt động qua Servlet Filter chain. Không giả định một custom `HandlerFilterFunction` thay được toàn bộ authentication/authorization/CSRF/cookie policy của `SecurityFilterChain`.

### 8.5. Lưu ý FormFilter cho form-urlencoded

Gateway MVC dùng Servlet container; với `application/x-www-form-urlencoded`, container có thể kết hợp dữ liệu form và query parameters khi ai đó đọc request parameters. Gateway có một `FormFilter` để hỗ trợ dựng lại form body cho downstream.

Tài liệu **Working with Servlets and Servlet Filters** cảnh báo: một **custom Servlet Filter** đọc request parameters trước filter chain có thể cần order so với `FormFilter.FORM_FILTER_ORDER`. Nếu không, request form proxy có thể bị biến đổi ngoài dự kiến.

Không dùng một before processor đọc và parse body form rồi tự xây lại body thủ công mà chưa xem quy tắc framework. Với body lớn/multipart/streaming, cân nhắc buffering, disk usage, request size limit và timeout.

## 9. Thiết kế HandlerFilterFunction an toàn khi có lỗi

### 9.1. Ba cách kết thúc một request

Một filter tổng quát có thể:

1. **Cho đi tiếp:** gọi `next.handle(request)` đúng một lần và trả response.
2. **Từ chối sớm:** trả một `ServerResponse` trực tiếp, không gọi next.
3. **Gặp lỗi:** handler/transport ném exception; filter có thể để lỗi lan lên error handling chuẩn hoặc xử lý có chủ đích.

Mẫu:

~~~java
return (request, next) -> {
    if (reject(request)) {
        return ServerResponse.status(403)
                .body("Not allowed");
    }
    return next.handle(request);
};
~~~

Đoạn trên minh họa cấu trúc, **không chứa implementation `reject(...)` hay bảo mật thật**.

Không gọi `next.handle(request)` hai lần khi chỉ muốn “thử lại một chút”, vì với POST/PUT/PATCH backend có thể đã thực hiện side effect ở lần đầu. Retry cần giải pháp chuyên biệt với timeout, budget, phương thức, status/exception cho phép và hợp đồng idempotency.

### 9.2. Exception có thể ngăn after processor chạy

Một custom after function được gọi khi handler bên trong trả về một `ServerResponse` để nó xử lý. Nếu handler **ném exception trước khi trả response**, không thể mặc định rằng `.after(...)` vẫn sẽ chạy và gắn header vào response lỗi.

Đối với metrics:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> timed =
        (request, next) -> {
            long startNanos = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long durationNanos =
                        System.nanoTime() - startNanos;
                // Ghi metric duration, kể cả khi next ném exception.
            }
        };
~~~

Đối với chuẩn hóa lỗi toàn ứng dụng, dùng Spring MVC exception handling, Servlet error dispatch hoặc các cơ chế chính thức có kiểm thử. Không nên tự catch mọi exception rồi đổi thành `200 OK` hay trả full exception message cho client.

### 9.3. Response có thể đã bị commit

Một response proxy có thể bắt đầu stream body tới client; khi headers đã commit, thay đổi status/header có thể không còn hợp lệ. Built-in `AfterFilterFunctions` được Gateway thiết kế cho luồng response thích hợp, nhưng custom code vẫn cần:

- Chỉ sửa những headers còn an toàn để thay đổi.
- Không thêm một `Content-Length` sai sau khi biến đổi body.
- Không gửi hai giá trị xung đột cho CORS/cache/security headers.
- Không giả định có thể hủy việc ghi body sau khi một phần đã được gửi.
- Kiểm tra nội dung khi backend trả redirect, 204 No Content, lỗi 4xx/5xx hoặc streaming response.

Nếu cần **biến đổi response body**, hãy dùng cơ chế body filter chuyên biệt và hiểu buffering/content encoding, thay vì viết trực tiếp vào response trong một after function đơn giản.

### 9.4. Quyết định status không chỉ phụ thuộc một filter

| Kết quả HTTP | Có thể đến từ | Cần kiểm tra |
| --- | --- | --- |
| 200 | Backend hoặc handler local | Có đúng backend, đúng route ID không? |
| 301/302 | Backend hoặc filter redirect | `Location`, Host/Proto, open redirect |
| 401 | Spring Security, backend OAuth2 | Token/issuer/audience, security chain |
| 403 | Spring Security, custom short-circuit | Log nguồn quyết định, không lộ details |
| 404/405 | Predicate không match, handler không tồn tại | Method, path, route order |
| 429 | Rate limiting | KeyResolver/tenant quota, Retry-After |
| 502/503 | Proxy, service discovery, backend outage | URI, TLS, DNS, LB, timeout |
| 500 | Exception trong custom filter hoặc framework | Logs/trace đã làm sạch, input validation |

Không ép mọi exception vào `403` để “an toàn”: điều đó che giấu lỗi hệ thống và khiến client/monitoring xử lý sai.

## 10. Bảo mật: custom MVC filter không thay thế bảo vệ API

### 10.1. Đừng tin header danh tính do client khai

Trong lab, `X-Route-Tag` và `X-Mvc-Before` là **marker kỹ thuật**. Trong hệ thống thật:

~~~http
X-User-Id: admin
X-Tenant-Id: enterprise
Authorization: Bearer ...
Forwarded: for=...
~~~

đều là dữ liệu HTTP cần đánh giá theo **trust boundary**. Một client có thể tự gửi `X-User-Id`, `X-Tenant-Id` hoặc `X-Forwarded-For`. Không được dùng `before(request -> ... )` để lấy những giá trị đó làm danh tính đã xác minh.

Hệ thống phải:

1. Xác thực access token/session/API key bằng Spring Security trên Servlet stack (hoặc thành phần được chỉ định).
2. Phân quyền theo principal/tenant/resource từ nguồn đáng tin.
3. Xóa/ghi đè những identity headers client không được phép kiểm soát.
4. Bảo vệ kết nối Gateway → backend bằng network policy/TLS/mTLS hoặc cơ chế tin cậy tương đương.
5. Để backend tự xác minh quyền tài nguyên nhạy cảm, không chỉ tin marker.

### 10.2. Chặn SSRF/open proxy ở destination URI

`BeforeFilterFunctions.uri(...)` định tuyến tới upstream. Một URI xuất phát từ cấu hình quản trị đáng tin có thể hợp lệ, nhưng nếu được xây **trực tiếp từ header/query của client**, kẻ tấn công có thể trỏ tới:

~~~text
http://127.0.0.1:...
http://169.254.169.254/...
http://internal-admin-service/...
~~~

Đó là rủi ro SSRF/open proxy. Với route động, cần allowlist scheme/host/port, kiểm tra DNS resolution/redirect và quyền cập nhật route, không dùng custom before filter như một proxy tùy ý theo client input.

### 10.3. After filter và security response headers

Nếu đặt `Content-Security-Policy`, `Strict-Transport-Security`, `Access-Control-Allow-Origin` hoặc `Cache-Control`, phải biết **header được set ở lớp nào** (backend, Gateway MVC, public Ingress). Hai lớp cùng `add` một header không có nghĩa trình duyệt hiểu theo ý định; CORS credentials và HSTS đặc biệt cần cấu hình nhất quán.

Không thêm `Access-Control-Allow-Origin: *` cho request có credentials và coi là đã giải quyết vấn đề. CORS là quy tắc browser, **không phải authentication hoặc CSRF protection**.

### 10.4. CSRF, cookies và Servlet stack

Nếu Gateway MVC dùng session-cookie authentication, trình duyệt có thể gửi cookie tự động. Cần phân tích **CSRF** cho POST/PUT/PATCH/DELETE theo Spring Security Servlet stack, SameSite/Secure/HttpOnly và HTTPS. Một custom `HandlerFilterFunction` chỉ xử lý route request/response **không tự cấp đầy đủ session fixation protection, CSRF token repository hoặc authorization rule**.

### 10.5. Sensitive data trong logs

Không log raw `Authorization`, cookie session, request body chứa dữ liệu cá nhân, refresh token, payment details hoặc full proxy URI có credentials. Nếu filter cần correlation ID, tạo ID an toàn, chuẩn hóa header do client gửi và giới hạn kích thước/charset. Metric labels chỉ nên có route ID/status/nhóm lỗi ít biến thể, không thêm từng user ID hay token.

## 11. Performance: Servlet threads, body và Retry

### 11.1. Web MVC không phải Reactor Netty

Server MVC chạy trên **Servlet runtime** (Tomcat/Jetty theo cấu hình), khác kiến trúc reactive WebFlux. Một `HandlerFilterFunction` nhận/trả `ServerRequest/ServerResponse` trực tiếp. Nếu bạn đặt lời gọi HTTP/DB chậm hoặc `Thread.sleep(...)` trong filter, các servlet request threads có thể bị chiếm giữ lâu, kéo theo queueing và giảm throughput.

Chỉ gọi I/O thực sự cần thiết trong filter, áp timeout và concurrency limits; giữ chính sách rate limiting/circuit breaker/retry có kiểm soát. Đừng copy mã WebFlux `Mono.defer()/flatMap()` vào MVC filter như thể hai stack có cùng contract.

### 11.2. Body không miễn phí chỉ vì dùng before function

Một before function thường chỉ nên sửa path/header/URI. Khi đọc body để ký HMAC, biến đổi JSON hoặc debug:

- Body stream có thể chỉ đọc được một lần nếu không có wrapper/caching phù hợp.
- Việc tạo `byte[]`/`String` giữ toàn bộ body trên heap, tăng memory khi có nhiều requests.
- Multipart/form-urlencoded có thêm chi phí phân tích/temporary files và `FormFilter`.
- Content-Length, Content-Type, charset và compression phải thống nhất sau transform.
- Một body lớn bị retry có thể bị giữ lâu hơn và gây memory amplification.

Ưu tiên **BodyFilterFunctions** hoặc filter chính thức phù hợp version, giới hạn payload bằng ingress/server và tests cho body chunked, file upload, UTF-8, empty body và client disconnect.

### 11.3. Retry lặp lại calls và có thể lặp side effects

Một `HandlerFilterFunction` bao quanh next có thể nằm trước hoặc trong phạm vi của Retry function, tùy cách chain được ghép. Nếu một request client được retry ba attempts tới backend, cần phân biệt:

- **logical client request count**;
- **downstream attempt count**;
- filter nào chỉ chạy một lần và filter nào chạy mỗi attempt;
- body có thể replay không;
- backend có idempotency key/transaction chống duplicate hay không.

Không đặt việc trừ tiền, gửi email hoặc cập nhật trạng thái nghiệp vụ trong một filter route nếu không có cơ chế exactly-once/idempotency phù hợp. Circuit breaker cũng cần được sắp xếp theo policy: breaker quan sát một request tổng hợp hay từng attempt sẽ ảnh hưởng thống kê lỗi.

### 11.4. Service discovery và thứ tự thay path

Khi dùng `lb://service-id` hoặc `LoadBalancerFilterFunctions`, thứ tự URL rewrite/StripPrefix và bước resolve instance quan trọng. Tài liệu `StripPrefix` của Gateway MVC nhấn mạnh rằng khi dùng `lb()`, cần đặt **sau `stripPrefix()`** để tránh tạo URL cuối không đúng; handler scheme `lb:` từ cấu hình có thể đặt filter ở mức ưu tiên cao riêng.

Không suy từ ví dụ `uri("http://127.0.0.1:9091")` rằng thay thành `uri("lb://orders-service")` là đủ trong mọi release. Kiểm tra load balancing dependency, service registry, URL attribute và các filter liên quan trong đúng Gateway MVC version.

## 12. Troubleshooting và cách phân biệt nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Java compile không tìm thấy `HandlerFilterFunction` | Import nhầm WebFlux, thiếu Spring MVC starter | Dùng `org.springframework.web.servlet.function.*` |
| Không tìm thấy `BeforeFilterFunctions` | Starter sai hoặc dùng Gateway 4.2 với prefix/docs 5.x | Kiểm tra `spring-cloud-starter-gateway-server-webmvc` hoặc starter cũ tương ứng |
| Route không được chọn | GET/path predicate không khớp, route ưu tiên khác | Gửi đúng method/path, xem route IDs |
| 404 khi gọi qua Gateway, backend trực tiếp 200 | `stripPrefix`/uri path không đúng | Echo `getRequestURI()` tại backend |
| Header request không đến backend | Before function chưa chạy, route khác, proxy xóa header | So response backend echo và route selection |
| Response không có header after | After chưa gắn, handler lỗi trước khi có response, response commit | Gọi case 200 và case lỗi riêng |
| Header có hai giá trị | Dùng add nhiều lần, client gửi sẵn header | Kiểm tra set/replace policy |
| Cờ lab trả 403 nhưng backend vẫn có log | Request khác/cạnh tranh, filter chain bị lắp khác ý định | Correlation ID/trace, đếm requests cùng ID |
| Backend không nhận `/echo` | `StripPrefix` sai parts hoặc route URI path bị hiểu sai | Kiểm tra URL downstream thực, thử raw path |
| YAML cấu hình route không có tác dụng | Sai namespace MVC 4.2 so với 4.3+/5.x | Kiểm tra configuration properties/startup logs |
| Custom filter Java chạy nhưng YAML không tìm thấy | Chưa đăng ký `FilterSupplier` bean/discovery | Test registration/name/binding |
| Response status sai khi backend lỗi | Exception khác status, error handling/Retry/CircuitBreaker | Phân tích nguyên nhân theo từng tầng |
| Thông lượng giảm mạnh sau thêm filter | I/O blocking, đọc body lớn, serialize/log nặng | Đo thread pool, p95/p99 latency, heap |
| POST form body thiếu dữ liệu | Servlet Filter đọc parameters hoặc FormFilter order | Kiểm tra filter registration và FormFilter |
| Security filter “không chạy” trên route mới | Route filter không phải Servlet/Spring Security chain | Đánh giá `SecurityFilterChain`/URL matcher |
| CORS lỗi khi browser gọi | Preflight không khớp route/security, header trùng | Kiểm tra OPTIONS, origins, credentials |

### 12.1. Test theo từng lớp

1. **Backend trực tiếp:** `GET http://127.0.0.1:9091/echo` phải hoạt động.
2. **Gateway route:** `GET http://127.0.0.1:8080/proxy/echo` phải match.
3. **Before markers:** backend thấy đúng path/headers.
4. **After markers:** client thấy đúng response headers.
5. **Handler short-circuit:** request có `X-Lab-Block: yes` không gọi backend.
6. **Method mismatch:** POST không vô tình đi vào GET-only route.
7. **Security/proxy behavior:** kiểm tra request có/không có credentials với chính sách thật, không dùng cờ lab.
8. **Performance:** đo p95/p99, thread utilization và memory khi tăng concurrency.

Trong quá trình debug, đừng tắt TLS, rate limiting, auth hoặc mở Actuator write access chỉ để “làm cho lab chạy”. Cô lập test environment sẽ giúp phân tích từng nguyên nhân mà không suy yếu production.

## 13. Bài tập thực hành mở rộng

### Bài 1 — Thay add bằng set

Sửa chính sách marker để khi client gửi sẵn `X-Route-Tag: client-value`, backend chỉ còn **một** giá trị do Gateway tạo. Hãy chọn built-in phù hợp như `setRequestHeader` (nếu được hỗ trợ trong version), viết test header trùng và giải thích vì sao add không thích hợp cho identity header.

### Bài 2 — Kết hợp filter trước và sau để đo latency

Viết `HandlerFilterFunction` nhận thời điểm bắt đầu, gọi `next.handle(request)` đúng một lần, rồi ghi **latency histogram** theo route/status. Đảm bảo `finally` ghi latency cả khi handler ném exception. Không gắn request ID/user ID vào metric labels.

### Bài 3 — Test short-circuit độc lập

Thêm một bộ đếm endpoint backend cho lab. Gửi 10 request bình thường rồi 10 request có `X-Lab-Block: yes`. Kiểm chứng count backend chỉ tăng đối với những request không bị chặn; so status/headers và ghi nhận liệu after processor có chạy khi short-circuit ở cấu trúc filter đã chọn.

### Bài 4 — So sánh Java DSL và YAML

Chạy cùng logic header trên hai route **khác path/route ID**: một route viết bằng Java API, một route YAML built-in. So sánh header trước và sau. Giải thích vì sao các method Java custom không tự động có tên trong external configuration nếu thiếu filter supplier.

### Bài 5 — Lỗi 502 và Retry

Cho backend trả 502 lần đầu, 200 lần tiếp theo. Bật Retry MVC chuyên biệt cho **GET** với ngân sách hữu hạn, rồi quan sát số backend attempts, response cuối và latency. Giải thích vì sao phải thêm idempotency contract trước khi áp cùng ý tưởng cho POST tạo đơn.

## 14. Checklist để đưa custom MVC filter vào production

- [ ] Dự án thật sự dùng **Gateway Server Web MVC**, không trộn API WebFlux.
- [ ] Starter và Spring Cloud BOM đúng dòng 4.2, 4.3 hoặc 5.x; namespace YAML đúng version.
- [ ] Java proxy dùng `HandlerFunctions.http()` kết hợp `BeforeFilterFunctions.uri()`.
- [ ] Khi chỉ sửa request, ưu tiên `.before(...)`; khi chỉ sửa response, ưu tiên `.after(...)`.
- [ ] Dùng `.filter(...)` khi cần bao quanh handler hoặc short-circuit có chủ đích.
- [ ] Chỉ gọi `next.handle(request)` số lần phù hợp; không tự retry request non-idempotent.
- [ ] Hiểu scope của route builder/nested routes và thứ tự composition.
- [ ] Có tests route match, Before header/path, After header và HandlerFilterFunction short-circuit.
- [ ] Không dùng marker/header do client tự khai làm bằng chứng xác thực hoặc quyền truy cập.
- [ ] Security Servlet Filter chain, CSRF, cookie, OAuth2/JWT được thiết kế riêng.
- [ ] Destination URI được kiểm soát, tránh SSRF/open proxy.
- [ ] Không vô tình thêm trùng headers nhạy cảm như Authorization, Host, CORS, HSTS, Content-Length.
- [ ] Có timeout/concurrency limit và tránh blocking calls/large body buffering trong filter.
- [ ] Với form-urlencoded/multipart, đã kiểm tra Servlet Filter và FormFilter ordering.
- [ ] Retry/CircuitBreaker/LoadBalancer có thứ tự và failure policy rõ ràng, metrics phân biệt attempts.
- [ ] Không log raw token/cookie/body nhạy cảm hoặc high-cardinality metrics labels.
- [ ] Khi custom filter dùng YAML, đã đăng ký supplier và kiểm thử tên/args/binding.
- [ ] Có smoke test trước/sau nâng cấp Gateway, đặc biệt khi chuyển từ 4.2 sang 4.3+/5.x.

## 15. Tự kiểm tra kiến thức

**1. Vì sao `BeforeFilterFunctions` dùng `Function<ServerRequest, ServerRequest>`?**

Vì nó biến đổi request **trước khi handler chạy**, không cần response hoặc tự gọi handler. Kết quả là một request mới hoặc một request đã được biến đổi theo contract.

**2. `AfterFilterFunctions` có thể tự ngăn handler chạy không?**

Không theo contract after processor thông thường: nó xử lý request và response **đã được tạo**. Nếu cần short-circuit trước backend, dùng một `HandlerFilterFunction` (hoặc chính sách security/rate limiting phù hợp).

**3. `HandlerFilterFunction` khác before/after ở điểm cốt lõi nào?**

Nó nhận `HandlerFunction<T> next`, tự quyết định có gọi next hay không và có thể xử lý logic cả trước/sau next; linh hoạt hơn nhưng đòi hỏi kiểm soát lỗi, side effects và thứ tự.

**4. Vì sao Gateway MVC không dùng `GatewayFilterFactory<Config>` kiểu WebFlux cho route Java?**

Vì Web MVC xây trên WebMvc.fn/Servlet với `ServerRequest/ServerResponse/HandlerFilterFunction`, còn WebFlux dùng `ServerWebExchange/Mono<Void>/GatewayFilter` và routing reactive.

**5. Tại sao backend không thấy `X-Gateway-After` trong echo request?**

Vì after filter thêm header vào **response quay về client**, không phải request đã được gửi tới backend. Nếu muốn backend thấy một header, dùng before filter.

**6. Một custom static method trả `HandlerFilterFunction` có tự tham chiếu được từ YAML không?**

Không mặc nhiên. Tài liệu Gateway yêu cầu đăng ký **FilterSupplier/SimpleFilterSupplier** để framework discover custom filters từ external configuration.

**7. Có thể dùng cùng một HandlerFilterFunction cho mọi request, kể cả annotated controllers, bằng cách gắn vào một route không?**

Không. Filter gắn vào RouterFunction builder có **phạm vi các routes thuộc builder**, còn Servlet Filter/Spring Security chain hoạt động ở tầng rộng hơn theo mapping.

**8. Vì sao phải kiểm tra `stripPrefix()` cùng `lb()`?**

Vì việc dựng URL backend phụ thuộc path đã được biến đổi và thứ tự resolve service instance. Nếu load balancer filter chạy khi URL/path chưa ở trạng thái mong muốn, backend có thể nhận sai URI.

## 16. Tài liệu chính thức

1. [Spring Cloud Gateway Server Web MVC — Gateway Handler Filter Functions](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/gateway-handler-filter-functions.html): contract before/after, vị trí `BeforeFilterFunctions`, `AfterFilterFunctions`, `FilterFunctions` và các advanced filters.
2. [Gateway Server MVC — Writing Custom Predicates and Filters](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/writing-custom-predicates-and-filters.html): ví dụ Java dùng `Function`, `BiFunction`, `HandlerFilterFunction`, `FilterSupplier`.
3. [Gateway Server Web MVC — Java Routes API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/java-routes-api.html): `RouterFunctions.Builder`, `GatewayRouterFunctions.route(...)`, `HandlerFunctions.http()`, `BeforeFilterFunctions.uri()`.
4. [Gateway Server Web MVC — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/how-it-works.html): cấu trúc RouterFunction, HTTP handler và các filter.
5. [Gateway Server Web MVC — AddRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/addrequestheader.html): built-in request header function/YAML.
6. [Gateway Server Web MVC — AddResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/addresponseheader.html): built-in after function/YAML.
7. [Gateway Server Web MVC — StripPrefix](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/filters/stripprefix.html): sửa path và cảnh báo thứ tự với `lb()`.
8. [Spring Framework — WebMvc.fn Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webmvc-functional.html): `RouterFunction`, `HandlerFunction`, `ServerRequest/ServerResponse`, `before/after/filter` và nested scope.
9. [Gateway Server Web MVC — Working with Servlets and Servlet Filters](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/working-with-servlets-and-filters.html): Servlet Filter ordering và FormFilter.
10. [Gateway Server MVC 4.2 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway-server-mvc/starter.html): tên starter 4.2 và kiến trúc Servlet.
11. [Gateway Server Web MVC 4.3 — Starter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webmvc/starter.html): tên starter 4.3 và cách bật/tắt MVC gateway.

**Ghi nhớ:** Trong **Spring Cloud Gateway Server Web MVC**, `BeforeFilterFunctions` xử lý **request trước handler**, `AfterFilterFunctions` xử lý **response sau handler**, còn `HandlerFilterFunction` **bao quanh handler** và có quyền gọi hoặc không gọi `next.handle(request)`. Ba kiểu này dựa trên **WebMvc.fn/Servlet**, không phải reactive GatewayFilter của WebFlux. Hãy chọn công cụ đơn giản nhất đúng mục đích, kiểm chứng bằng request/response thực, bảo vệ filter khỏi input không tin cậy, và kiểm tra thứ tự, lỗi, retry, memory và security trước khi đưa route vào production.
