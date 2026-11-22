# Phân biệt WebFilter với HandlerFilterFunction trong Spring WebFlux

Spring WebFlux có hai hợp đồng filter thường được dùng để chèn logic trước và sau một handler: **WebFilter** và **HandlerFilterFunction**. Cả hai đều chạy theo mô hình reactive, có thể kiểm tra request, chặn request, gọi phần xử lý tiếp theo và biến đổi response. Tuy nhiên, chúng nằm ở hai tầng khác nhau:

- **WebFilter** thuộc WebHandler API của Spring. Một bean WebFilter được áp dụng trên chuỗi xử lý HTTP exchange của ứng dụng, trước WebHandler đích. Nó có thể bao quanh annotated controller, functional endpoint và các WebHandler khác trong cùng WebFlux application.
- **HandlerFilterFunction** thuộc WebFlux.fn. Nó bao quanh một HandlerFunction trong RouterFunction, nên phạm vi của nó là các functional route mà router builder hoặc RouterFunction đã gắn filter đó.

Vì vậy, nếu cần một chính sách chung cho request ở cấp ứng dụng như correlation ID, CORS, logging, timeout hoặc một bước kiểm tra bảo mật tích hợp, hãy xem xét WebFilter. Nếu cần middleware nhỏ chỉ dành cho một nhóm route được khai báo bằng RouterFunction, HandlerFilterFunction thường phù hợp hơn.

Bài học thuộc nhóm **Filter và phiên**, tập trung vào cách phân biệt hai filter, tổ chức chain, truy cập WebSession và chọn đúng phạm vi áp dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vị trí của WebFilter trong WebHandler processing chain.
- Giải thích hợp đồng filter(ServerWebExchange, WebFilterChain) và giá trị trả về Mono<Void>.
- Mô tả hợp đồng HandlerFilterFunction<T, R> trong WebFlux.fn.
- Phân biệt phạm vi áp dụng của filter toàn ứng dụng với filter theo functional route.
- Dùng filter để tiếp tục, chặn hoặc biến đổi request/response.
- Phân biệt before, after và filter trong RouterFunctions.Builder.
- Hiểu thứ tự filter và phạm vi của filter trong nested route.
- Truy cập WebSession từ ServerWebExchange hoặc ServerRequest mà không vô tình tạo session.
- Viết ví dụ Java 17+ có WebFilter, HandlerFilterFunction và WebTestClient.
- Tránh các lỗi phổ biến về body một lần đọc, subscribe thủ công, session không cần thiết và bảo mật.

## 2. Đặt hai filter vào đúng tầng xử lý

WebFlux cung cấp một chuỗi xử lý HTTP chung. WebFilter nằm ở tầng WebHandler API, bao quanh phần xử lý còn lại. Sau khi request đi qua chuỗi filter, WebHandler trung tâm thường là DispatcherHandler. DispatcherHandler tìm handler thông qua các HandlerMapping và gọi handler qua HandlerAdapter thích hợp.

Functional endpoint cũng tham gia vòng đời DispatcherHandler. RouterFunctionMapping tìm route, HandlerFunctionAdapter gọi HandlerFunction và ServerResponseResultHandler ghi kết quả. Vì thế, functional route vẫn đi qua WebFilter ở tầng ngoài.

~~~text
HTTP server
    |
    v
WebExceptionHandler chain
    |
    v
WebFilter chain
    |
    v
WebHandler / DispatcherHandler
    |
    +-------------------------------+
    |                               |
    v                               v
Annotated controller          Functional endpoint
HandlerMapping                 RouterFunctionMapping
    |                               |
HandlerAdapter                 HandlerFunctionAdapter
    |                               |
Controller method              HandlerFunction
    |                               |
    v                               v
Result handling                ServerResponse
    |                               |
    +---------------+---------------+
                    |
                    v
              HTTP response
~~~

Sơ đồ là mô hình khái quát. Một ứng dụng có thể có nhiều filter, exception handler, security filter và các HandlerMapping khác nhau. Điểm cần nhớ là **WebFilter bao quanh tầng handler chung**, còn **HandlerFilterFunction nằm bên trong nhánh functional routing sau khi một route được chọn**.

Một request tới annotated controller vẫn đi qua WebFilter. Request đó không tự đi qua HandlerFilterFunction của một RouterFunction khác.

## 3. WebFilter là gì?

WebFilter là hợp đồng trong package org.springframework.web.server. Nó có một phương thức:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)
~~~

Hai tham số có vai trò khác nhau:

- **ServerWebExchange:** đại diện cho HTTP request-response exchange hiện tại. Nó cho phép truy cập request, response, request attributes, session, principal và các thông tin khác.
- **WebFilterChain:** cung cấp phương thức để chuyển request tới filter tiếp theo hoặc WebHandler đích.

Filter trả về **Mono<Void>** để biểu thị toàn bộ quá trình xử lý request đã hoàn tất hoặc phát lỗi. Mono này là một phần của pipeline HTTP; không cần tự subscribe.

Một WebFilter đơn giản thêm header response:

~~~java
@Component
public class ResponseHeaderWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
            .getHeaders()
            .add("X-Application-Filter", "applied");

        return chain.filter(exchange);
    }
}
~~~

Đây là fragment cần import Spring WebFlux. Header được đặt trước khi gọi phần xử lý tiếp theo, nên response có thể mang header đó nếu response chưa được commit. Filter trả về publisher từ chain để framework quản lý lifecycle.

### Tiếp tục hay chặn request

Gọi chain.filter(exchange) cho phép request đi tiếp. Nếu filter không gọi chain, nó có thể tự tạo response và kết thúc pipeline:

~~~java
@Component
public class SimpleGateWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String token = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Demo-Token");

        if (!"allow".equals(token)) {
            exchange.getResponse()
                .setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
~~~

Đây là ví dụ minh họa một gate đơn giản, không phải cơ chế xác thực production. Khi từ chối request, filter đặt status rồi trả Mono<Void> từ setComplete. Nó không gọi chain, nên controller hoặc functional handler không được chạy.

Với xác thực và phân quyền thật, nên dùng Spring Security reactive. WebFilter tùy chỉnh có thể tham gia chuỗi bảo mật theo cấu hình, nhưng không nên tự phát minh việc kiểm tra token, quản lý danh tính, session fixation và authorization nếu Spring Security đã cung cấp cơ chế phù hợp.

## 4. WebFilter bean được áp dụng như thế nào?

Trong ứng dụng dùng WebFlux Config hoặc Spring Boot WebFlux, các bean có kiểu WebFilter được tự động đưa vào chuỗi filter cho các HTTP exchange. Vì vậy, một filter không cần được khai báo lại trong từng controller hoặc RouterFunction.

Có thể đăng ký bằng component:

~~~java
@Component
public class TraceWebFilter implements WebFilter {
    // ...
}
~~~

Hoặc khai báo bean:

~~~java
@Configuration
public class WebFilterConfiguration {

    @Bean
    WebFilter traceWebFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                .add("X-Trace-Filter", "applied");
            return chain.filter(exchange);
        };
    }
}
~~~

Hai cách trên đều tạo bean WebFilter. Chọn một cách phù hợp với cấu trúc cấu hình; không đăng ký trùng cùng một filter qua cả @Component và @Bean.

### Thứ tự của nhiều WebFilter

Khi thứ tự có ý nghĩa, WebFilter có thể implement Ordered hoặc dùng @Order:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
WebFilter firstWebFilter() {
    return (exchange, chain) -> chain.filter(exchange);
}

@Bean
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
WebFilter secondWebFilter() {
    return (exchange, chain) -> chain.filter(exchange);
}
~~~

Giá trị order thấp hơn được ưu tiên trước trong chuỗi. Filter chạy trước thường là lớp bao ngoài: phần code trước chain.filter chạy khi request đi vào; phần xử lý sau chain.filter chạy khi response quay ngược ra, nếu pipeline hoàn tất theo nhánh đó.

~~~text
Request đi vào:
Filter A before
  Filter B before
    Handler
  Filter B after
Filter A after

Response đi ra:
Filter B hoàn tất trước
Filter A hoàn tất sau
~~~

Trong thực tế, hãy kiểm tra order của các filter framework và filter ứng dụng. Spring Security sử dụng WebFilterChainProxy; CORS, observation và các filter khác cũng có thể có order được cấu hình. Đừng giả định filter tự viết luôn chạy trước hoặc sau Security nếu chưa đặt và kiểm tra thứ tự rõ ràng.

## 5. HandlerFilterFunction là gì?

HandlerFilterFunction thuộc package org.springframework.web.reactive.function.server của WebFlux.fn. Nó là một functional interface bao quanh một HandlerFunction.

Hợp đồng chính:

~~~java
Mono<R> filter(
    ServerRequest request,
    HandlerFunction<T> next
)
~~~

Trong đó:

- **ServerRequest:** request đã được chuyển sang abstraction của functional endpoint. Nó cung cấp method, URI, path variables, headers, query parameters, body, principal, session và exchange nền.
- **HandlerFunction<T>:** handler tiếp theo trong functional chain. Nó nhận ServerRequest và trả publisher chứa ServerResponse.
- **T và R:** kiểu response của handler và kiểu response mà filter trả về. Thông thường cả hai đều là ServerResponse.

HandlerFilterFunction có thể gọi next.handle(request) để chuyển tiếp. Nó cũng có thể không gọi next và tự trả response để chặn request.

Ví dụ:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> routeGuard =
    (request, next) -> {
        String token = request.headers()
            .firstHeader("X-Route-Token");

        if (!"allow".equals(token)) {
            return ServerResponse.status(HttpStatus.FORBIDDEN)
                .bodyValue("Blocked by route filter");
        }

        return next.handle(request);
    };
~~~

Đây là fragment dành cho WebFlux.fn. Filter chỉ có tác dụng khi được gắn vào RouterFunction hoặc router builder. Nó không tự động trở thành filter toàn ứng dụng chỉ vì biến được khai báo trong cấu hình.

### Gắn HandlerFilterFunction vào RouterFunction

Có thể gắn filter bằng builder:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/fn/hello", request ->
            ServerResponse.ok().bodyValue("hello"))
        .filter(routeGuard)
        .build();
~~~

Filter được áp dụng cho các route được xây dựng trong builder đó. Có thể áp dụng cho một RouterFunction đã tồn tại:

~~~java
RouterFunction<ServerResponse> secured =
    existingRoutes.filter(routeGuard);
~~~

Một RouterFunction có thể được compose với RouterFunction khác. Hãy gắn filter ở đúng cấp route để tránh vô tình bảo vệ quá rộng hoặc quá hẹp.

## 6. before, after và filter trong functional routing

RouterFunctions.Builder cung cấp ba cách thêm logic quanh functional route:

- **before(requestProcessor):** nhận ServerRequest và trả ServerRequest đã biến đổi trước khi handler chạy.
- **after(responseProcessor):** nhận request cùng ServerResponse và trả response sau khi handler hoàn tất.
- **filter(handlerFilterFunction):** bao quanh HandlerFunction, có thể kiểm tra request, quyết định có gọi handler hay không và quan sát hoặc biến đổi response.

### before: biến đổi request trước handler

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/fn/header", request ->
            ServerResponse.ok().bodyValue(
                request.headers().firstHeader("X-Route-Tag")))
        .before(request -> ServerRequest.from(request)
            .header("X-Route-Tag", "from-before")
            .build())
        .build();
~~~

ServerRequest là immutable abstraction. ServerRequest.from(request) tạo builder dựa trên request hiện tại; header được thêm vào bản request mới rồi chuyển tới handler. Request gốc không bị sửa trực tiếp.

### after: quan sát response sau handler

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/fn/hello", request ->
            ServerResponse.ok().bodyValue("hello"))
        .after((request, response) -> {
            log.info("Functional response status: {}",
                response.statusCode());
            return response;
        })
        .build();
~~~

Callback after nhận response đã được handler tạo. Ví dụ chỉ ghi log rồi trả lại chính response, do đó giữ nguyên body và headers. Nếu cần thay đổi response, phải tạo một response mới với status, headers và body được xác định rõ; không giả định builder chỉ sao chép status/header sẽ tự giữ body cũ.

### filter: bao quanh toàn bộ handler

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> loggingFilter =
    (request, next) ->
        next.handle(request)
            .doOnNext(response ->
                log.info("{} {} -> {}",
                    request.method(),
                    request.path(),
                    response.statusCode()));
~~~

Filter gọi next.handle(request), rồi quan sát ServerResponse khi publisher phát kết quả. Vì doOnNext chỉ quan sát và trả nguyên tín hiệu, response body vẫn được giữ nguyên. Nếu filter không gọi next, nó có thể tự trả ServerResponse để chặn request.

## 7. Phạm vi của HandlerFilterFunction và nested routes

Một filter được thêm vào router builder áp dụng cho các route thuộc builder đó. Với nested route, vị trí khai báo quyết định phạm vi:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/people", people -> people
            .nest(accept(MediaType.APPLICATION_JSON), json -> json
                .GET("/{id}", handler::getPerson)
                .GET("", handler::listPeople)
                .before(request -> ServerRequest.from(request)
                    .header("X-Json-Route", "yes")
                    .build()))
            .POST(handler::createPerson))
        .after((request, response) -> {
            log.info("Completed {}", request.path());
            return response;
        })
        .build();
~~~

Trong ví dụ:

- before nằm trong nhánh nested có điều kiện Accept JSON, nên chỉ tác động các GET route trong nhánh đó.
- after nằm ở builder ngoài, nên tác động tất cả route được compose trong builder, bao gồm các nested route.
- Một route nằm ngoài builder này không nhận filter chỉ vì nó cùng ứng dụng.

Điều này khác với WebFilter bean, vốn được đưa vào chuỗi HTTP exchange chung. Nếu muốn một chính sách cho toàn ứng dụng, không nên tạo hàng loạt HandlerFilterFunction rồi gắn thủ công từng RouterFunction.

## 8. Bảng so sánh trực tiếp

| Tiêu chí | WebFilter | HandlerFilterFunction |
| --- | --- | --- |
| API | WebHandler API | WebFlux.fn |
| Package | org.springframework.web.server | org.springframework.web.reactive.function.server |
| Hợp đồng | ServerWebExchange + WebFilterChain | ServerRequest + HandlerFunction |
| Giá trị trả về | Mono<Void> | Mono<R> |
| Phạm vi | Chuỗi xử lý HTTP của ứng dụng | RouterFunction/functional routes được gắn filter |
| Annotated controller | Có thể bao quanh | Không tự động áp dụng |
| Functional endpoint | Có, ở tầng ngoài | Có, ở tầng functional route |
| Truy cập response | ServerWebExchange.getResponse() | Xử lý ServerResponse bất biến |
| Biến đổi request | Dùng exchange/request wrapper hoặc mutate | Dùng ServerRequest.from(request).build() |
| Chặn request | Không gọi chain.filter; tự hoàn tất response | Không gọi next.handle; trả ServerResponse |
| Đăng ký | Spring bean WebFilter | RouterFunction.filter hoặc builder.filter |
| Thứ tự | Ordered / @Order | Composition và vị trí filter trong router |
| Session | exchange.getSession() | request.session() |
| Use case | Cross-cutting toàn ứng dụng | Middleware gắn với route chức năng |

Cả hai đều reactive, nhưng abstraction và phạm vi khác nhau. WebFilter thao tác với ServerWebExchange và hoàn tất toàn bộ HTTP exchange. HandlerFilterFunction thao tác với ServerRequest và response được biểu diễn bằng ServerResponse.

## 9. Chọn filter theo use case

### Chọn WebFilter khi logic phải áp dụng rộng

Các ví dụ thường phù hợp với WebFilter:

- Gắn correlation ID hoặc request ID vào mọi request.
- Ghi nhận observation/logging ở ranh giới HTTP.
- Cấu hình CORS ở tầng WebFlux.
- Áp dụng timeout hoặc giới hạn request theo chính sách toàn ứng dụng.
- Đọc hoặc cập nhật metadata/session dùng chung ở nhiều endpoint.
- Tích hợp chuỗi filter của Spring Security.
- Chuẩn hóa một số response header ở mọi route.

Một WebFilter có thể kiểm tra path rồi chỉ làm thêm việc cho một nhóm endpoint, nhưng bean vẫn được gọi trong chuỗi của mọi exchange. Nếu logic thực sự chỉ thuộc một functional route, dùng HandlerFilterFunction sẽ thể hiện phạm vi rõ hơn.

### Chọn HandlerFilterFunction khi logic thuộc functional route

Các ví dụ phù hợp:

- Chặn một nhóm functional route bằng policy riêng.
- Thêm request header nội bộ trước khi HandlerFunction chạy.
- Kiểm tra metadata riêng của module functional.
- Gắn session attribute cho một workflow functional cụ thể.
- Ghi log response chỉ cho một RouterFunction.
- Tạo middleware có thể compose cùng route builder.

HandlerFilterFunction không được gắn vào annotated controller method. Nếu muốn hành vi tương tự trên annotated controller, hãy cân nhắc WebFilter, Spring Security, @ControllerAdvice, hook phù hợp hoặc logic trong service tùy yêu cầu.

### Không dùng filter thay cho mọi tầng khác

Filter là điểm can thiệp ở tầng HTTP. Nó không phải nơi mặc định đặt mọi quy tắc nghiệp vụ.

- Xác thực và phân quyền nên dựa trên Spring Security reactive.
- Kiểm tra dữ liệu nghiệp vụ nên nằm ở service/domain boundary.
- Chuyển đổi lỗi nghiệp vụ thành response có thể dùng exception handler/advice.
- Ghi log nghiệp vụ sau khi thao tác thành công nên đặt ở use case/service phù hợp.
- Logic chỉ dành cho một functional route có thể đặt ở HandlerFilterFunction.

## 10. Truy cập WebSession trong WebFlux

**WebSession** là abstraction của Spring cho session phía server, cho phép giữ attributes qua nhiều HTTP request. Session ID thường được gửi cho client bằng cookie; nội dung session được quản lý bởi WebSessionStore.

Có hai lối truy cập phù hợp với hai loại filter:

- Trong WebFilter: gọi **exchange.getSession()**, trả về Mono<WebSession>.
- Trong HandlerFilterFunction: gọi **request.session()**, trả về Mono<WebSession>.

Cả hai method đều trả publisher vì session có thể cần được lấy từ session store. Việc gọi getSession/session để lấy instance **không tự động khởi tạo session mới đã được lưu**.

~~~java
// Trong WebFilter
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put(
            "lastPath",
            exchange.getRequest().getPath().value());
        return chain.filter(exchange);
    });
~~~

~~~java
// Trong HandlerFilterFunction
return request.session()
    .flatMap(session -> {
        session.getAttributes().put(
            "lastFunctionalPath",
            request.path());
        return next.handle(request);
    });
~~~

Việc thêm attribute làm session bắt đầu. Ứng dụng có thể gọi start() để bắt đầu rõ ràng. Session được lưu tự động trước khi response được commit; thông thường không cần gọi save() thủ công.

### Một số thao tác WebSession

| API | Ý nghĩa |
| --- | --- |
| getAttribute(name) | Đọc attribute nếu có |
| getAttributeOrDefault(name, fallback) | Đọc với giá trị mặc định |
| getAttributes() | Truy cập map attribute |
| start() | Bắt đầu session rõ ràng |
| isStarted() | Kiểm tra session đã bắt đầu |
| changeSessionId() | Đổi session ID |
| invalidate() | Hủy session và xóa storage |
| setMaxIdleTime(duration) | Đặt thời gian idle tối đa |

Các thao tác bất đồng bộ như changeSessionId() và invalidate() trả Mono<Void>; phải compose chúng vào pipeline. Đừng gọi subscribe() tách riêng.

### Session không giống request attribute

- **Request attribute** chỉ tồn tại trong một HTTP exchange hiện tại.
- **WebSession attribute** tồn tại qua nhiều request mang cùng session ID, theo chính sách lưu trữ và thời hạn session.
- **Reactor Context** gắn với subscription, không tự động tồn tại qua request tiếp theo.
- **Cookie** thường mang session ID, không phải toàn bộ dữ liệu session.

Không lưu dữ liệu lớn, object không thể serialize theo store đang dùng, hoặc thông tin nhạy cảm không cần thiết trong session. Với ứng dụng nhiều instance, cần session store dùng chung như Spring Session Redis hoặc cơ chế lưu trữ phù hợp; session chỉ nằm trong bộ nhớ một instance không tự chia sẻ giữa các node.

## 11. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này dùng cả hai loại filter trong cùng một ứng dụng:

- Một **WebFilter** thêm request ID vào response cho mọi exchange, bao gồm annotated controller và functional route.
- Một **WebFilter** khác chỉ cập nhật session trên endpoint /api/session/visits.
- Một **HandlerFilterFunction** bảo vệ functional route /fn/hello, chặn request thiếu token và thêm header vào bản ServerRequest chuyển tới handler.
- Một **HandlerFilterFunction** khác cập nhật session cho functional route /fn/session/visits.
- Một annotated controller và hai functional routes giúp so sánh phạm vi hoạt động.

### Cấu trúc project

~~~text
webflux-filter-demo/
├── pom.xml
└── src
    ├── main/java/com/example/filters
    │   ├── FilterDemoApplication.java
    │   ├── ApiController.java
    │   └── FilterConfiguration.java
    └── test/java/com/example/filters
        └── FilterComparisonTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-filter-demo</artifactId>
  <version>1.0.0</version>

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
~~~

Spring Boot parent quản lý phiên bản Spring Framework và Reactor tương thích. Ví dụ dùng Java 17 và starter WebFlux.

### FilterDemoApplication.java

~~~java
package com.example.filters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

### ApiController.java

~~~java
package com.example.filters;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("annotated");
    }

    @GetMapping("/session/visits")
    public Mono<String> sessionVisits(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> "visits=" +
                session.getAttributeOrDefault("webFilterVisits", 0));
    }
}
~~~

Endpoint /api/hello chỉ trả nội dung để kiểm tra WebFilter toàn cục. Endpoint /api/session/visits đọc session đã được WebFilter cập nhật trước đó.

### FilterConfiguration.java

~~~java
package com.example.filters;

import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;

@Configuration
public class FilterConfiguration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter requestIdWebFilter() {
        return (exchange, chain) -> {
            String requestId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Request-Id");

            if (requestId == null ||
                    !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
                requestId = UUID.randomUUID().toString();
            }

            exchange.getResponse()
                .getHeaders()
                .set("X-Request-Id", requestId);

            return chain.filter(exchange);
        };
    }

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE + 10)
    WebFilter webFilterSessionCounter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest()
                .getPath()
                .value();

            if (!"/api/session/visits".equals(path)) {
                return chain.filter(exchange);
            }

            return exchange.getSession()
                .flatMap(session -> {
                    Integer current =
                        session.getAttribute("webFilterVisits");

                    session.getAttributes().put(
                        "webFilterVisits",
                        current == null ? 1 : current + 1);

                    return chain.filter(exchange);
                });
        };
    }

    @Bean
    RouterFunction<ServerResponse> functionalRoutes() {
        HandlerFilterFunction<ServerResponse, ServerResponse> routeGuard =
            (request, next) -> {
                String token = request.headers()
                    .firstHeader("X-Route-Token");

                if (!"allow".equals(token)) {
                    return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .bodyValue("Blocked by functional route filter");
                }

                ServerRequest decorated = ServerRequest.from(request)
                    .header("X-Route-Filter", "applied")
                    .build();

                return next.handle(decorated);
            };

        RouterFunction<ServerResponse> helloRoute =
            RouterFunctions.route()
                .GET("/fn/hello", request ->
                    ServerResponse.ok().bodyValue(
                        "functional:" +
                        request.headers().firstHeader("X-Route-Filter")))
                .filter(routeGuard)
                .build();

        HandlerFilterFunction<ServerResponse, ServerResponse> sessionCounter =
            (request, next) -> request.session()
                .flatMap(session -> {
                    Integer current =
                        session.getAttribute("functionalVisits");

                    session.getAttributes().put(
                        "functionalVisits",
                        current == null ? 1 : current + 1);

                    return next.handle(request);
                });

        RouterFunction<ServerResponse> sessionRoute =
            RouterFunctions.route()
                .GET("/fn/session/visits", request ->
                    request.session()
                        .flatMap(session ->
                            ServerResponse.ok().bodyValue(
                                "visits=" + session.getAttributeOrDefault(
                                    "functionalVisits", 0))))
                .filter(sessionCounter)
                .build();

        return helloRoute.andOther(sessionRoute);
    }
}
~~~

Các điểm cần quan sát:

1. **requestIdWebFilter** là bean WebFilter. Nó được gọi trên cả /api/hello và /fn/hello, rồi thêm X-Request-Id vào response.
2. **webFilterSessionCounter** cũng là WebFilter, nhưng chỉ thực hiện session logic khi path đúng /api/session/visits. Những request khác vẫn đi tiếp mà không tạo session.
3. **routeGuard** chỉ được gắn vào helloRoute. Nó từ chối request nếu thiếu X-Route-Token=allow. Khi được phép, nó tạo một ServerRequest mới có X-Route-Filter và chuyển request đó tới handler.
4. **sessionCounter** chỉ được gắn vào sessionRoute. Nó truy cập WebSession qua request.session(), cập nhật số lượt và gọi handler tiếp theo.
5. Hai RouterFunction được compose bằng andOther. Filter của helloRoute không tự áp dụng cho sessionRoute; WebFilter toàn ứng dụng vẫn bao quanh cả hai.

### FilterComparisonTests.java

~~~java
package com.example.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterComparisonTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void webFilterWrapsAnnotatedController() {
        webTestClient.get()
            .uri("/api/hello")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Request-Id")
            .expectHeader().doesNotExist("X-Route-Filter")
            .expectBody(String.class)
            .isEqualTo("annotated");
    }

    @Test
    void handlerFilterFunctionCanShortCircuitFunctionalRoute() {
        webTestClient.get()
            .uri("/fn/hello")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().exists("X-Request-Id")
            .expectBody(String.class)
            .isEqualTo("Blocked by functional route filter");
    }

    @Test
    void handlerFilterFunctionCanDecorateFunctionalRequest() {
        webTestClient.get()
            .uri("/fn/hello")
            .header("X-Route-Token", "allow")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Request-Id")
            .expectBody(String.class)
            .isEqualTo("functional:applied");
    }

    @Test
    void webFilterCanUpdateWebSession() {
        webTestClient.get()
            .uri("/api/session/visits")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Set-Cookie")
            .expectBody(String.class)
            .isEqualTo("visits=1");
    }

    @Test
    void handlerFilterFunctionCanUpdateWebSession() {
        webTestClient.get()
            .uri("/fn/session/visits")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Set-Cookie")
            .expectBody(String.class)
            .isEqualTo("visits=1");
    }
}
~~~

Chạy toàn bộ test:

~~~bash
mvn -q test
~~~

Nếu năm test pass, Maven kết thúc với exit code 0. Các test kiểm tra ba điều cốt lõi:

- WebFilter được chạy cả trên annotated controller.
- HandlerFilterFunction chỉ bảo vệ functional route đã gắn filter và có thể chặn request hoặc chuyển request đã biến đổi tới handler.
- Cả hai loại filter đều có thể truy cập WebSession và cập nhật session theo phạm vi riêng.

### Chạy ứng dụng và gọi thử

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Annotated controller luôn có request ID từ WebFilter:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Functional route bị chặn nếu thiếu token:

~~~bash
curl -i http://localhost:8080/fn/hello
~~~

Gửi token để functional route được tiếp tục:

~~~bash
curl -i -H "X-Route-Token: allow" http://localhost:8080/fn/hello
~~~

Hai endpoint session minh họa hai vị trí filter:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/session/visits
curl -i -b cookies.txt -c cookies.txt http://localhost:8080/api/session/visits
curl -i -c functional-cookies.txt http://localhost:8080/fn/session/visits
curl -i -b functional-cookies.txt -c functional-cookies.txt http://localhost:8080/fn/session/visits
~~~

Client phải gửi lại cookie session ở request tiếp theo để tiếp tục cùng một WebSession. Hai bộ cookie trong ví dụ được tách riêng để không trộn trạng thái của hai endpoint.

## 12. Lỗi thường gặp và cách khắc phục

1. **Dùng HandlerFilterFunction rồi mong nó áp dụng cho @RestController.** Nó chỉ bao quanh functional route được gắn filter. Dùng WebFilter nếu cần phạm vi HTTP exchange chung.
2. **Dùng WebFilter cho một route functional duy nhất mà không cần phạm vi toàn cục.** Filter vẫn được gọi cho mọi exchange rồi phải tự kiểm tra path. Cân nhắc HandlerFilterFunction.
3. **Quên trả publisher của chain.** WebFilter phải compose và trả chain.filter(exchange); HandlerFilterFunction phải compose next.handle(request) khi cho phép đi tiếp.
4. **Gọi subscribe() bên trong filter.** Việc này tách công việc khỏi HTTP lifecycle, làm mất liên hệ với lỗi, cancellation và response.
5. **Gọi block() để lấy session hoặc body.** Các API session/body là reactive; hãy dùng flatMap/map và trả publisher.
6. **Không gọi next/chain nhưng lại mong handler chạy.** Nếu không delegate, filter đang short-circuit và phải tự tạo response phù hợp.
7. **Đọc request body ở filter rồi để handler đọc lại.** Body là stream có thể chỉ đọc một lần. Nếu cần kiểm tra body, phải thiết kế caching/wrapping phù hợp và giữ backpressure.
8. **Sửa trực tiếp ServerRequest hoặc ServerResponse.** Đây là immutable abstraction. Dùng builder/wrapper hoặc trả response mới có body được xây dựng rõ ràng.
9. **Giả định ServerResponse.from(response) giữ nguyên body.** Builder này dùng để bắt đầu từ status và headers; nếu tái tạo response, phải xử lý body có chủ đích.
10. **Tạo session cho mọi request không cần thiết.** Việc chỉ lấy session không tự bắt đầu session; thêm attribute hoặc gọi start() mới làm session bắt đầu. Chỉ truy cập session khi nghiệp vụ cần.
11. **Gọi WebSession.save() thủ công trong mọi request.** Framework tự lưu trước khi response commit. Hãy để pipeline quản lý, trừ khi có một yêu cầu đặc biệt được tài liệu hóa.
12. **Không compose invalidate() hoặc changeSessionId().** Đây là Mono<Void>; nếu bỏ qua publisher, thao tác bất đồng bộ có thể không được thực thi.
13. **Cho rằng session trong memory được chia sẻ giữa nhiều instance.** Cần store dùng chung nếu triển khai nhiều node.
14. **Tự viết authentication bằng một header demo.** Ví dụ token trong bài chỉ minh họa short-circuit; production cần Spring Security reactive, xác minh credential và authorization.
15. **Đặt @Order mà không xét filter framework.** Security, CORS, observation và filter ứng dụng có thể phụ thuộc thứ tự. Kiểm tra chuỗi thực tế.
16. **Đặt route filter ở builder quá rộng.** Filter có thể áp dụng cho mọi route được compose trong builder đó. Chia router hoặc dùng nested scope khi cần giới hạn.
17. **Nuốt lỗi trong filter.** Đừng chuyển mọi error thành response 200 hoặc Mono.empty(); để exception handler phù hợp xử lý lỗi.
18. **Không kiểm thử cả annotated và functional route.** Một test functional route không chứng minh WebFilter đã bao quanh annotated controller và ngược lại.

## 13. Checklist thiết kế

Trước khi triển khai filter, hãy xác định:

- **Phạm vi:** chính sách cần chạy trên mọi HTTP exchange, hay chỉ một functional route?
- **Hợp đồng:** code đang làm việc với ServerWebExchange/WebFilterChain hay ServerRequest/HandlerFunction?
- **Delegate:** khi nào cần gọi chain.filter hoặc next.handle, và khi nào được short-circuit?
- **Reactive lifecycle:** mọi publisher được compose và trả về đầy đủ chưa?
- **Request body:** filter có đọc body không? Nếu có, handler sau đó còn đọc được không?
- **Request mutation:** có dùng wrapper/builder thay vì sửa object immutable không?
- **Response mutation:** status, headers và body có được giữ đúng khi tạo response mới không?
- **Ordering:** các WebFilter và Spring Security có thứ tự phù hợp không?
- **Nested routes:** filter của builder có đúng phạm vi route mong muốn không?
- **Session:** có thực sự cần WebSession không? Có vô tình bắt đầu session cho request stateless không?
- **Storage:** session store có đáp ứng môi trường single-node hay multi-node không?
- **Security:** có dùng Spring Security reactive cho authentication/authorization không?
- **Errors:** lỗi được truyền tới WebExceptionHandler hoặc handler phù hợp chưa?
- **Tests:** có kiểm thử annotated controller, functional route, short-circuit, request mutation và session không?

## 14. Bài tập tự kiểm tra

**Bài 1.** Một WebFilter bean được đăng ký trong ứng dụng WebFlux. Nó có thể bao quanh annotated controller và functional route không?  
**Đáp án:** Có. WebFilter nằm ở WebHandler chain chung, bên ngoài WebHandler đích.

**Bài 2.** HandlerFilterFunction có tự động chạy cho một @RestController không?  
**Đáp án:** Không. Nó chỉ chạy khi được gắn vào RouterFunction/functional route tương ứng.

**Bài 3.** Vì sao WebFilter trả Mono<Void> còn HandlerFilterFunction trả Mono<ServerResponse> trong trường hợp thông dụng?  
**Đáp án:** WebFilter bao quanh toàn bộ HTTP exchange và báo hoàn tất response; HandlerFilterFunction bao quanh HandlerFunction và trả response đã được tạo.

**Bài 4.** Nếu HandlerFilterFunction không gọi next.handle(request), điều gì xảy ra?  
**Đáp án:** Handler tiếp theo không chạy. Filter phải trả một ServerResponse thay thế, ví dụ 401 hoặc 403.

**Bài 5.** Muốn thêm header vào request trước một functional handler, dùng cách nào?  
**Đáp án:** Tạo ServerRequest mới bằng ServerRequest.from(request), thêm header rồi build và chuyển request mới cho next.handle.

**Bài 6.** before và after trong router builder có tác dụng gì?  
**Đáp án:** before biến đổi request trước handler; after xử lý response sau handler. filter bao quanh handler và có thể chặn hoặc delegate.

**Bài 7.** WebFilter có thể truy cập WebSession bằng API nào?  
**Đáp án:** ServerWebExchange.getSession(), trả Mono<WebSession>.

**Bài 8.** HandlerFilterFunction có thể truy cập WebSession bằng API nào?  
**Đáp án:** ServerRequest.session(), trả Mono<WebSession>.

**Bài 9.** Chỉ gọi getSession() có làm session mới được lưu và gửi cookie ngay không?  
**Đáp án:** Không. Việc lấy instance không tự bắt đầu session. Thêm attribute hoặc gọi start() mới bắt đầu session; session được lưu trước khi response commit.

**Bài 10.** Vì sao không nên gọi subscribe() trong filter?  
**Đáp án:** Nó tạo subscription tách khỏi HTTP lifecycle, khiến lỗi, cancellation và hoàn tất response khó được điều phối đúng.

**Bài 11.** Một filter gắn ở nested router có tác động tới route nằm ngoài nested scope không?  
**Đáp án:** Không. Phạm vi filter phụ thuộc builder và vị trí composition; filter ở builder ngoài có thể bao phủ cả nested routes.

**Bài 12.** Cần bảo vệ tất cả endpoint bằng authentication. Nên tự viết HandlerFilterFunction cho từng RouterFunction không?  
**Đáp án:** Không. Dùng Spring Security reactive và cấu hình WebFilter chain phù hợp để có chính sách bảo mật nhất quán.

## 15. Ghi nhớ

**WebFilter** là interceptor ở tầng WebHandler API. Bean WebFilter được đưa vào chuỗi xử lý HTTP exchange và có thể bao quanh annotated controller lẫn functional endpoint. Nó làm việc với ServerWebExchange và WebFilterChain, trả Mono<Void>, có thể delegate hoặc tự hoàn tất response, và có thể được sắp thứ tự bằng Ordered/@Order.

**HandlerFilterFunction** là middleware của WebFlux.fn. Nó làm việc với ServerRequest và HandlerFunction, trả Mono<ServerResponse>, và chỉ áp dụng cho RouterFunction/functional route đã gắn filter. Nó có thể short-circuit, biến đổi request trước khi handler chạy hoặc quan sát response sau handler.

Cả hai có thể truy cập WebSession qua API riêng: exchange.getSession() hoặc request.session(). Chỉ lấy session không tự bắt đầu session; thêm attribute hoặc gọi start() mới bắt đầu. Hãy chọn WebFilter cho chính sách ở ranh giới HTTP chung, HandlerFilterFunction cho middleware theo functional route, compose toàn bộ publisher và để Spring quản lý session save/cancellation/response lifecycle.

### Tài liệu tham khảo

- Spring Framework, [Reactive Core – WebHandler API and Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework, [Functional Endpoints – Filtering Handler Functions](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework Javadoc, [WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html).
- Spring Framework Javadoc, [HandlerFilterFunction](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/HandlerFilterFunction.html).
- Spring Framework Javadoc, [ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html).
- Spring Framework Javadoc, [ServerRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html).
- Spring Framework Javadoc, [WebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html).
- Spring Boot, [Reactive Web Applications and Web Filters](https://docs.spring.io/spring-boot/reference/web/reactive.html).
