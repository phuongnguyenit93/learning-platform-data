# Đường đi qua máy chủ reactive, HttpHandler và WebHandler trong Spring WebFlux

## 1. Mục tiêu và điểm mấu chốt

Một HTTP request đi vào ứng dụng **Spring WebFlux** không đi thẳng từ Reactor Netty đến phương thức @GetMapping. Nó đi qua nhiều lớp chuyển đổi và điều phối, trong đó hai interface đặc biệt quan trọng:

- **HttpHandler** (org.springframework.http.server.reactive.HttpHandler) là hợp đồng tối thiểu để xử lý request/response HTTP ở mức trừu tượng, không phụ thuộc trực tiếp vào kiểu dữ liệu riêng của Reactor Netty, Tomcat hay Jetty.
- **WebHandler** (org.springframework.web.server.WebHandler) là hợp đồng ở mức web application, nhận **ServerWebExchange**. Nó có thể được bao quanh bằng WebFilter và WebExceptionHandler; trong ứng dụng WebFlux mặc định, WebHandler trung tâm thường là **DispatcherHandler**.

Với cấu hình thông thường **Spring Boot 3.3.x + spring-boot-starter-webflux + Reactor Netty**, luồng khái quát:

~~~text
Client TCP/TLS/HTTP
  -> Reactor Netty HttpServer
  -> ReactorHttpHandlerAdapter
  -> Spring HttpHandler (thường là HttpWebHandlerAdapter)
  -> ServerWebExchange
  -> WebExceptionHandler/WebFilter chain
  -> WebHandler chính (DispatcherHandler)
  -> HandlerMapping -> HandlerAdapter -> HandlerResultHandler
  -> ghi response qua reactive ServerHttpResponse
  -> Reactor Netty gửi bytes về client
~~~

Đây là mô hình **logical flow**, không phải một stack trace tuyến tính hay khẳng định mọi request đều đi đến DispatcherHandler: WebFilter có thể chặn, WebExceptionHandler có thể xử lý lỗi, chức năng quan sát/codec có thể tham gia, và một số thành phần có thể chạy bất đồng bộ. **Không phải mỗi HTTP request mặc định được cấp một Java thread riêng**; cách xử lý phụ thuộc vào Reactor, scheduler, event loop, subscription và API blocking/non-blocking được gọi.

Bài học giúp bạn:

1. Phân biệt HTTP server, adapter runtime, HttpHandler, WebHandler và DispatcherHandler.
2. Hiểu ServerHttpRequest/ServerHttpResponse khác ServerWebExchange như thế nào.
3. Biết WebHttpHandlerBuilder lắp ghép filter và exception handler vào pipeline.
4. Theo dõi cách annotation controller và functional route được tìm/gọi.
5. Giải thích vai trò Mono<Void>, request body Flux<DataBuffer> và response commit.
6. Viết và kiểm thử ứng dụng Spring WebFlux Java 17+ có cả annotated controller, functional route và WebFilter.
7. Chẩn đoán 404, body parsing, filter, lỗi 500, blocking event loop và nhầm lẫn WebFlux với MVC.

## 2. Điều kiện tiên quyết: ứng dụng phải thật sự chạy WebFlux server

Ví dụ Gradle tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Starter này thường cung cấp Spring WebFlux và Reactor Netty. Khi không có Spring MVC lấn át việc nhận diện classpath và không có cấu hình tùy biến đặc biệt, Spring Boot suy ra **WebApplicationType.REACTIVE**, tạo reactive web ApplicationContext, tự động cấu hình ReactiveWebServerFactory và xây dựng HttpHandler phù hợp.

**Trường hợp rất dễ nhầm:** nếu đồng thời đưa cả spring-boot-starter-web và spring-boot-starter-webflux vào classpath, Spring Boot **mặc định ưu tiên Spring MVC/Servlet**. Bạn vẫn có thể dùng WebClient, Mono hay Flux trong MVC, nhưng HTTP request không vì thế mà tự đi qua WebFlux DispatcherHandler.

Khi thật sự cần server reactive trong một ứng dụng có cả hai starter, có thể chủ động đặt:

~~~properties
spring.main.web-application-type=reactive
~~~

Điều này thay đổi loại web ApplicationContext được Boot chọn; nó không tự làm những dependency blocking trở thành non-blocking. Với ứng dụng WebFlux thuần theo ví dụ trong bài, không cần thêm thuộc tính trên.

### WebFlux không đồng nghĩa bắt buộc Reactor Netty

Spring WebFlux được thiết kế để làm việc với nhiều runtime HTTP được hỗ trợ. **HttpHandler** là ranh giới trừu tượng giúp phần web framework không phải viết controller riêng cho từng server. Reactor Netty là lựa chọn mặc định phổ biến của starter-webflux; đường đi ở adapter tầng server có thể khác khi dùng một server khác.

Phải phân biệt:

| Thành phần | Là gì? | Vai trò trong request |
| --- | --- | --- |
| Reactor Netty HttpServer | Reactive HTTP server runtime | Quản lý network channel, HTTP parsing/encoding, I/O và event loop |
| NettyReactiveWebServerFactory | Factory của Spring Boot | Khởi tạo embedded Reactor Netty server trong lifecycle Spring Boot |
| ReactorHttpHandlerAdapter | Adapter giữa Reactor Netty và Spring HTTP abstraction | Chuyển request/response của Reactor Netty thành lời gọi HttpHandler |
| HttpHandler | Interface HTTP mức thấp của Spring | Nhận ServerHttpRequest/ServerHttpResponse, trả Mono<Void> |
| HttpWebHandlerAdapter | Implementation HttpHandler cho WebHandler stack | Tạo ServerWebExchange và gọi WebHandler chain |
| WebHandler | Interface xử lý web request mức cao hơn | Nhận ServerWebExchange, trả Mono<Void> |
| WebFilter | Filter theo mô hình reactive WebFlux | Bao quanh WebHandler chain, có thể tiếp tục hoặc dừng |
| WebExceptionHandler | Xử lý lỗi trong WebHandler chain | Chuyển error signal thành response khi có thể |
| DispatcherHandler | Front controller của Spring WebFlux | Chọn handler, gọi adapter và xử lý kết quả |
| HandlerMapping/HandlerAdapter/HandlerResultHandler | Các chiến lược dispatch | Map route, thực thi handler, ghi/render kết quả |

**NettyReactiveWebServerFactory không phải là request handler**. Nó được sử dụng trong quá trình khởi động để tạo server. Sau khi server đã start, mỗi request đi qua adapter/handler runtime; factory không được tạo mới cho từng request.

## 3. Lớp 1: Reactor Netty tiếp nhận kết nối và HTTP request

Reactor Netty chạy trên nền Netty event loop. Với một HTTP/1.1 request thông thường, công việc tầng này gồm:

1. Hệ điều hành và channel tiếp nhận kết nối TCP; TLS handshake được xử lý nếu cấu hình HTTPS.
2. Netty đọc bytes bất đồng bộ, xử lý HTTP protocol theo cấu hình server.
3. Reactor Netty cung cấp đối tượng HttpServerRequest và HttpServerResponse cho handler function đã được đăng ký.
4. Adapter của Spring được gọi, trả về một **reactive completion publisher** biểu thị việc xử lý response.
5. Server runtime quản lý subscription, I/O và gửi bytes theo flow của transport.

Bước một đến năm là một mô tả tổng quát. TCP keep-alive có thể cho nhiều request trên một connection; HTTP/2 có multiplexing; proxy có thể chấm dứt TLS trước ứng dụng. Không thể suy từ “một request” thành “một socket mới” hoặc “một thread mới”.

### Event loop nghĩa là gì?

Netty dùng số lượng event-loop threads tương đối nhỏ để xử lý nhiều connection. Điều này hiệu quả khi phần lớn công việc không blocking. Nếu controller/service gọi Thread.sleep, JDBC blocking hoặc .block() trên Netty event loop, thread có thể bị giữ lại và làm tăng latency cho request khác.

Reactive API tạo khả năng non-blocking và xử lý bất đồng bộ, **không tự biến một đoạn code blocking thành non-blocking**. Khi buộc phải dùng API blocking, hãy thiết kế rõ ranh giới và scheduler thích hợp, đồng thời đo tài nguyên và throughput.

## 4. Lớp 2: ReactorHttpHandlerAdapter nối Netty và HttpHandler

**org.springframework.http.server.reactive.ReactorHttpHandlerAdapter** là adapter dành cho Reactor Netty. API thực chất có hình thức:

~~~java
public class ReactorHttpHandlerAdapter
        implements java.util.function.BiFunction<
                reactor.netty.http.server.HttpServerRequest,
                reactor.netty.http.server.HttpServerResponse,
                reactor.core.publisher.Mono<Void>> {

    // Chữ ký minh họa; không phải toàn bộ source code thực tế:
    public reactor.core.publisher.Mono<Void> apply(
            reactor.netty.http.server.HttpServerRequest request,
            reactor.netty.http.server.HttpServerResponse response) {
        // ...
        return null;
    }
}
~~~

Đây là **sơ đồ chữ ký API**, không phải code có thể sao chép chạy độc lập. Tác vụ thực tế của adapter là chuyển kiểu dữ liệu server-specific sang trừu tượng HTTP của Spring rồi ủy quyền cho HttpHandler được cấu hình.

Chính xác hơn, với Reactor Netty:

~~~text
Reactor Netty HttpServerRequest
     -> Spring ReactorServerHttpRequest
Reactor Netty HttpServerResponse
     -> Spring ReactorServerHttpResponse
     -> HttpHandler.handle(ServerHttpRequest, ServerHttpResponse)
~~~

Nhờ đó, code Spring WebFlux phía trên dùng giao diện Spring thay vì buộc controller hiểu đối tượng Reactor Netty.

### Tại sao adapter này hữu ích?

- Tách biệt network runtime và framework xử lý web.
- Giảm phụ thuộc server-specific trong HandlerMapping/controller.
- Cho phép WebFlux hỗ trợ nhiều reactive HTTP runtimes được Spring tích hợp.
- Giúp test tầng HttpHandler/WebHandler mà không buộc mở socket trong một số trường hợp.

**Không nên tự tạo ReactorHttpHandlerAdapter và gọi apply trong một controller.** Spring Boot và WebFlux đã cấu hình adapter để sử dụng tại ranh giới server.

## 5. Lớp 3: HttpHandler — hợp đồng HTTP mức thấp

Spring định nghĩa giao diện:

~~~java
package org.springframework.http.server.reactive;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface HttpHandler {
    Mono<Void> handle(
            ServerHttpRequest request,
            ServerHttpResponse response);
}
~~~

Đây là cấu trúc hợp đồng cốt lõi trong Spring Framework 6.x (bỏ qua annotation bổ sung nếu có ở bản Javadoc cụ thể).

Giải thích:

- ServerHttpRequest biểu diễn request HTTP theo trừu tượng Spring: path, method, headers, cookies, body Publisher.
- ServerHttpResponse biểu diễn status, headers, cookies và khả năng ghi response body.
- Mono<Void> mô tả completion hoặc error của quá trình xử lý, **không phải HTTP body** và cũng không phải một boolean xác nhận “đã trả 200”.
- HttpHandler chưa đưa vào tất cả khái niệm web application như session, localized context, form data, request attributes hoặc security principal theo dạng một exchange thống nhất.

Một HttpHandler tự viết có thể trả body cố định, nhưng nếu thay thế nó làm bean server mặc định một cách tùy tiện, bạn có thể bỏ qua WebFilter, WebExceptionHandler, DispatcherHandler, codecs và những tích hợp mà Spring Boot cung cấp. Với API thông thường, hãy viết controller, router function hoặc WebFilter thay vì thay toàn bộ HttpHandler.

### Ví dụ API minh họa

~~~java
// Minh họa cách dùng API; không dùng để thay HttpHandler mặc định:
HttpHandler handler = (request, response) -> {
    response.setStatusCode(org.springframework.http.HttpStatus.NO_CONTENT);
    return response.setComplete();
};
~~~

Đoạn này hợp lệ về ý nghĩa khi đặt trong Java code có imports cần thiết, nhưng **không tự khai báo server** và không phải ứng dụng Spring Boot độc lập.

Khi bạn thấy Mono<Void> trong HttpHandler, hãy nghĩ “khi nào chuỗi xử lý kết thúc hoặc báo lỗi?” chứ không nghĩ “giá trị dữ liệu mà client nhận được là Void”.

## 6. Lớp 4: HttpWebHandlerAdapter tạo ServerWebExchange

Giao diện WebHandler sử dụng:

~~~java
package org.springframework.web.server;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
~~~

HttpHandler chỉ nhận hai đối tượng request và response; WebHandler nhận **ServerWebExchange**, nơi gom thông tin web-level và một số khả năng tiện ích.

**HttpWebHandlerAdapter** là cầu nối thực hiện hợp đồng HttpHandler bằng cách tạo một ServerWebExchange, sau đó gọi WebHandler chain được lắp sẵn. Đây là lớp riêng biệt với ReactorHttpHandlerAdapter:

~~~text
ReactorHttpHandlerAdapter:
  Reactor Netty objects
    -> Spring ServerHttpRequest / ServerHttpResponse
    -> gọi HttpHandler

HttpWebHandlerAdapter:
  ServerHttpRequest / ServerHttpResponse
    -> ServerWebExchange
    -> gọi WebHandler chain
~~~

Hai lớp có tên dễ lẫn nhưng ở **hai ranh giới khác nhau**. Không phải “HttpHandler kế thừa WebHandler” hoặc “DispatcherHandler trực tiếp triển khai HttpHandler”: Spring WebFlux dùng adapter để liên kết các hợp đồng.

### ServerWebExchange mang những gì?

Một số dữ liệu/API thường dùng:

- exchange.getRequest(): request đã được chuẩn hóa theo abstraction Spring.
- exchange.getResponse(): response cho phép chỉnh status/header/body trước khi commit.
- exchange.getAttributes(): map thuộc tính theo request, hữu ích cho logging, tracing, thông tin trung gian.
- exchange.getSession(): Mono<WebSession> dùng theo thiết kế session của WebFlux.
- exchange.getPrincipal(): Mono<Principal> nếu đã có principal từ security/runtime.
- exchange.getFormData(): đọc dữ liệu form theo semantics của framework.
- exchange.getMultipartData(): hỗ trợ multipart.
- exchange.getLocaleContext(): ngữ cảnh locale.
- exchange.getLogPrefix(): prefix theo request để log.
- exchange.mutate(): tạo một exchange decorator/builder phù hợp để chuyển tiếp request biến đổi.

Một số API trả **Mono** vì không phải dữ liệu nào cũng đã sẵn hoặc đồng bộ. Ví dụ không nên gọi .block() để lấy session ngay trên Netty event loop.

### Exchange không phải là database transaction

Tên ServerWebExchange chỉ ngụ ý mô hình web request/response. Nó không tự tạo database transaction, không xác thực request và không đảm bảo toàn bộ luồng bất đồng bộ có cùng thread.

## 7. WebHttpHandlerBuilder lắp WebHandler chain như thế nào?

**org.springframework.web.server.adapter.WebHttpHandlerBuilder** là công cụ hạ tầng tạo một HttpHandler từ các thành phần WebFlux. Với ApplicationContext của ứng dụng, nó có thể tìm các bean đặc biệt:

- Bean tên **webHandler** làm WebHandler xử lý chính; trong WebFlux annotation/functional dispatch thông thường là DispatcherHandler.
- Các **WebFilter** được đăng ký.
- Các **WebExceptionHandler** được đăng ký.
- Các thành phần hỗ trợ như WebSessionManager, ServerCodecConfigurer, LocaleContextResolver và các thành phần khác tùy phiên bản/cấu hình.

Ở mức ý tưởng:

~~~java
HttpHandler httpHandler =
        WebHttpHandlerBuilder.applicationContext(applicationContext)
                .build();
~~~

Đây là đoạn minh họa cho code bên trong một ứng dụng có sẵn Spring ApplicationContext; **không phải chương trình độc lập** và không cần tự gọi đoạn này trong ứng dụng Spring Boot tiêu chuẩn.

Builder thực hiện hai nhiệm vụ:

1. Lắp **WebHandler chain**: WebHandler chính được bao bởi các WebFilter, rồi hệ xử lý exception ở bên ngoài.
2. Dùng **HttpWebHandlerAdapter** chuyển chain đó thành HttpHandler dùng được tại ranh giới HTTP server.

Sơ đồ bên dưới thể hiện sự bao bọc logic:

~~~mermaid
flowchart TD
    A["HttpHandler: HttpWebHandlerAdapter"] --> B["ServerWebExchange"]
    B --> C["ExceptionHandlingWebHandler"]
    C --> D["FilteringWebHandler"]
    D --> E["WebFilter 1"]
    E --> F["WebFilter 2 / Security WebFilters nếu có"]
    F --> G["DispatcherHandler (WebHandler chính)"]
    G --> H["Mapping / invocation / result handling"]
    H --> I["Reactive response write"]
    I --> J["Mono<Void> hoàn tất hoặc error"]
    J -. "error đi ngược upstream" .-> C
~~~

**Lưu ý sơ đồ:** Dấu mũi tên thể hiện thứ tự xử lý đi vào. Với Reactor, chính chuỗi Publisher được lắp sẵn và subscribed mới dẫn đến hoạt động; callback khi hoàn tất/error có thể chạy theo thứ tự ngược của lớp bọc. Không nên coi sơ đồ là thứ tự tuyệt đối của từng dòng stack trace.

### Trật tự của WebExceptionHandler và WebFilter

Trong WebHandler chain mặc định được xây từ WebHttpHandlerBuilder, WebExceptionHandler được đặt để xử lý những error signal phát ra từ WebFilter và WebHandler phía trong. Điều này cho phép lỗi từ controller hoặc từ filter được chuyển thành response nếu chưa commit.

Một WebFilter **không tự động là exception handler**. Nếu filter cần xử lý lỗi riêng, có thể dùng reactive operators đúng mục đích, nhưng với lỗi toàn ứng dụng nên cân nhắc WebExceptionHandler hoặc framework exception handling.

## 8. WebFilter: middleware reactive quanh WebHandler

Giao diện:

~~~java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
~~~

Với request bình thường, một filter gọi:

~~~java
return chain.filter(exchange);
~~~

Nếu filter **không gọi chain.filter**, request có thể dừng ở filter và filter tự hoàn tất response, ví dụ một cơ chế từ chối truy cập. Đây là short-circuit giống ý niệm middleware, không giống việc chỉ thêm header.

Filter có thể xử lý:

- Correlation ID và logging/observability.
- CORS trong cấu hình phù hợp.
- Authentication/authorization qua Spring Security reactive.
- Header chung trước khi response commit.
- Timing/thống kê hoàn thành, error và cancellation.
- Decorate request/response khi cần một tính năng middleware.

### Ví dụ WebFilter an toàn và đơn giản

~~~java
package com.example.flow;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class FlowHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .set("X-Flow", "webfilter");

        return chain.filter(exchange);
    }
}
~~~

Đây là class hoàn chỉnh dùng được trong ví dụ Spring Boot ở mục 15. Khi request đi qua filter, response sẽ mang header X-Flow: webfilter trừ khi thành phần khác chủ động sửa/xóa header trước commit.

**Không viết**:

~~~java
// Sai trong WebFilter thông thường:
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

Vì server runtime quản lý subscription, gọi subscribe() thủ công sẽ tách luồng lifecycle, khiến xử lý lỗi, completion và response commit khó kiểm soát; có thể tạo race hoặc gửi response quá sớm. Filter phải **return** chain Publisher.

### Filter order

WebFilter có thể được sắp xếp bằng @Order hoặc Ordered. Nếu có nhiều filter (đặc biệt security), thứ tự ảnh hưởng tới header/tracing/authentication/exception handling. Không tự đoán thứ tự nếu dùng nhiều thư viện: kiểm tra thứ tự bean thực tế và test chính sách bảo mật.

Đừng nhầm WebFilter với **jakarta.servlet.Filter**. WebFlux reactive stack dùng WebFilter, còn Servlet/MVC pipeline dùng Servlet Filter. Việc import cả hai API không có nghĩa chúng chạy trên cùng request.

## 9. DispatcherHandler: WebHandler chính của WebFlux

Ở ứng dụng WebFlux sử dụng annotated controllers hoặc functional routes, Spring cấu hình **DispatcherHandler** làm bộ điều phối web. Nó triển khai WebHandler, nghĩa là method xử lý nhận ServerWebExchange và trả Mono<Void>.

Đường đi logic trong DispatcherHandler:

1. Hỏi từng **HandlerMapping** theo thứ tự để tìm handler phù hợp.
2. Khi có handler, tìm **HandlerAdapter** hỗ trợ kiểu handler đó.
3. Adapter thực thi handler theo cơ chế tương ứng và trả **HandlerResult**.
4. Chọn **HandlerResultHandler** hỗ trợ kết quả để ghi response trực tiếp hoặc render view.
5. Hoàn tất Publisher; exception được xử lý bởi nhánh error handling thích hợp nếu có thể.

Sơ đồ:

~~~mermaid
flowchart TD
    A["DispatcherHandler.handle(exchange)"] --> B["HandlerMapping"]
    B --> C{"Có handler phù hợp?"}
    C -->|Không| D["Không tìm thấy handler -> lỗi not found phù hợp"]
    C -->|Có| E["HandlerAdapter hỗ trợ handler"]
    E --> F["Execute handler: Mono<HandlerResult>"]
    F --> G["HandlerResultHandler"]
    G --> H["Write body hoặc render view"]
    H --> I["Mono<Void> hoàn tất"]
~~~

**DispatcherHandler không phải Servlet DispatcherServlet**. Chúng có vai trò front controller tương tự nhưng nằm trên hai stack khác nhau. Annotation như @GetMapping có thể trông giống nhau, không đồng nghĩa cơ chế dưới chúng giống nhau.

## 10. Annotation controller và functional route đi cùng hạ tầng

### 10.1 Annotated controller

Ví dụ:

~~~java
@RestController
class GreetingController {

    @GetMapping("/api/greet/{name}")
    public Mono<String> greet(@PathVariable String name) {
        return Mono.just("Xin chào, " + name);
    }
}
~~~

Đoạn code trên chỉ minh họa method/class, không phải file độc lập có imports.

Trong luồng này:

- **RequestMappingHandlerMapping** tìm HandlerMethod được gắn @GetMapping.
- **RequestMappingHandlerAdapter** trong **package reactive** phân giải đối số và gọi method.
- **HandlerResult** gói kiểu trả về, reactive value và metadata.
- **ResponseBodyResultHandler** hỗ trợ @ResponseBody/@RestController; codec (HttpMessageWriter) ghi body theo media type.

Một Mono<String> không phải HTTP response đã được gửi ngay khi controller trả về. Đó là Publisher để framework đăng ký vào xử lý theo ngữ cảnh và ghi body khi subscription/request processing tiến triển.

### 10.2 Functional endpoints

Spring WebFlux cũng hỗ trợ RouterFunction<ServerResponse>:

~~~java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/functional/ping"),
            request -> ServerResponse.ok().bodyValue("pong"));
}
~~~

Đây là đoạn minh họa phương thức @Bean; file hoàn chỉnh xuất hiện ở mục 15.

Luồng tương ứng:

- **RouterFunctionMapping** dùng route predicates để tìm HandlerFunction.
- **HandlerFunctionAdapter** gọi HandlerFunction với ServerRequest.
- **ServerResponseResultHandler** xử lý ServerResponse và ghi HTTP response.

Không có một DispatcherHandler thứ hai dành riêng cho functional routing. Cả hai phong cách vẫn dùng hạ tầng WebFlux dispatch phù hợp với loại handler.

### 10.3 Bảng đối chiếu

| Bước | Annotation controller | Functional route |
| --- | --- | --- |
| Mapping | RequestMappingHandlerMapping | RouterFunctionMapping |
| Handler được tìm | HandlerMethod | HandlerFunction |
| Adapter | RequestMappingHandlerAdapter (WebFlux) | HandlerFunctionAdapter |
| Kết quả | HandlerResult cho giá trị trả về controller | HandlerResult chứa ServerResponse |
| Result handler điển hình | ResponseBodyResultHandler, ResponseEntityResultHandler, ... | ServerResponseResultHandler |
| HTTP entry point | Cùng HttpHandler/WebHandler chain | Cùng HttpHandler/WebHandler chain |

Thứ tự mapping có thể ảnh hưởng handler nào được chọn khi pattern chồng lấn. Tránh định nghĩa cùng route/method trong cả annotated và functional style rồi hy vọng framework tự chọn theo ý muốn.

## 11. Request body và HTTP codecs trong luồng reactive

Tại tầng HTTP trừu tượng:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

Đây là snippet minh họa với ServerWebExchange đã có sẵn; cần imports reactor.core.publisher.Flux và org.springframework.core.io.buffer.DataBuffer khi dùng trong class.

Body có thể đến theo nhiều chunk, không bắt buộc ứng dụng nhận toàn bộ request body như một byte[] trong một lần đọc. Framework dùng **HttpMessageReader**, **HttpMessageWriter**, **ServerCodecConfigurer** và các codec phù hợp để biến đổi giữa data buffers và object Java.

Ví dụ trong WebFlux controller:

~~~java
@PostMapping(path = "/api/echo",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<Payload> echo(@RequestBody Mono<Payload> payload) {
    return payload;
}
~~~

Đây là method minh họa, file hoàn chỉnh với DTO và imports ở mục 15. Với Content-Type: application/json và Jackson codec được starter hỗ trợ, JSON có thể được deserialize thành Payload khi pipeline subscribed.

**Không nhầm codec WebFlux với HttpMessageConverter của Spring MVC**. Chúng phục vụ mục đích tương tự về chuyển đổi message, nhưng nằm trong những API và pipeline khác nhau.

### Backpressure và DataBuffer

Reactive Streams backpressure cho phép downstream điều khiển lượng demand đối với publisher hỗ trợ demand. Nhưng không nên kết luận “mỗi bytes đến từ mạng đều được lưu bằng zero-copy” hoặc “một Flux luôn tự giới hạn tổng kích thước payload”. Server, codec, buffer, proxy và mức hỗ trợ backpressure của từng nguồn quyết định hành vi thực tế.

Nếu tự đọc Flux<DataBuffer> ở mức thấp, cần hiểu:

- DataBuffer có thể dùng pooled/native memory.
- Không lưu buffer để dùng lâu sau khi lifecycle request kết thúc.
- Không tự subscribe nhiều lần vào body; nội dung stream thông thường chỉ nên được tiêu thụ theo hợp đồng.
- Các API retain/release phải được sử dụng đúng khi tự can thiệp pooled buffers, tránh memory leak hoặc use-after-release.
- Cấu hình spring.codec.max-in-memory-size nếu codec cần tập hợp dữ liệu trong memory; nó không phải một giới hạn tuyệt đối cho mọi đường stream.
- Với upload lớn, ưu tiên streaming processing hoặc storage xử lý từng phần thay vì gom toàn bộ vào một List<byte[]> không giới hạn.

## 12. Response đi ngược lại qua những lớp nào?

Một handler có thể tạo response:

~~~java
@GetMapping(path = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
public Mono<String> hello() {
    return Mono.just("hello");
}
~~~

Với @RestController:

1. Controller trả Publisher (Mono<String>).
2. HandlerAdapter chuyển kết quả thành HandlerResult và trả về framework.
3. HandlerResultHandler thích hợp xác định cách ghi body.
4. HttpMessageWriter/Encoder biến chuỗi thành dữ liệu response theo media type.
5. ServerHttpResponse tiếp nhận status/header/body.
6. HttpWebHandlerAdapter và adapter HTTP server chờ/combine completion Publisher.
7. Reactor Netty gửi bytes ra channel, tôn trọng điều kiện của transport và lifecycle.

**Response headers/status phải được đặt trước khi response được commit.** Một WebFilter có thể dùng:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders().set("X-Flow", "committed");
    return Mono.empty();
});
~~~

Đây là snippet trong phạm vi đã có exchange; nó không phải class độc lập. beforeCommit đăng ký callback trước commit, hữu ích khi header phụ thuộc kết quả xử lý. Callback phải trả một Mono hoàn tất phù hợp; không làm blocking I/O trong đó.

### Mono<Void> hoàn tất có nghĩa gì?

Mono<Void> biểu diễn completion hoặc error của xử lý/ghi response, không khẳng định body rỗng. Một HTTP response có thể có JSON lớn được ghi qua các Publishers nhưng tầng điều phối vẫn trả Mono<Void> để báo khi việc ghi kết thúc.

Nếu exception xuất hiện **sau khi headers/body đã commit**, error handler thường không thể đổi HTTP status sang 500 hoặc ghi một JSON error body mới như khi response chưa commit. Một streaming response có thể kết thúc bất thường, và client có thể chỉ nhận một phần body.

## 13. Error signals và WebExceptionHandler

Với luồng reactive, một component có thể tạo tín hiệu lỗi:

~~~java
return Mono.error(new IllegalArgumentException("invalid"));
~~~

Đây là snippet Publisher; chưa tự tạo response.

Lỗi có thể xảy ra ở:

- WebFilter trước khi gọi handler.
- HandlerMapping vì không có route hoặc điều kiện mapping không khớp.
- Argument resolution, JSON decoding hoặc validation.
- Controller/service trong lúc xử lý.
- HandlerResultHandler hoặc response encoding.
- I/O khi client ngắt kết nối, timeout hoặc ghi response.

WebFlux có nhiều tầng xử lý exception:

1. **Handler-specific**: @ExceptionHandler trong controller hoặc @ControllerAdvice/@RestControllerAdvice có thể xử lý lỗi liên quan annotated controllers.
2. **Framework/global WebHandler chain**: WebExceptionHandler có thể xử lý error signal từ chain phía trong.
3. **Spring Boot error handling**: ứng dụng Boot thông thường cung cấp cấu hình xử lý lỗi web reactive phù hợp nếu chưa được thay thế.
4. **Transport**: network error xảy ra sau khi response commit có thể không chuyển được thành error body.

Ví dụ một @RestControllerAdvice trong WebFlux:

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid request"));
    }
}
~~~

Đây là class minh họa; cần imports java.util.Map, org.springframework.http.ResponseEntity và annotation classes để chạy độc lập. Nếu lỗi phát sinh từ thành phần ngoài annotated-controller exception mechanism, cần xem global WebExceptionHandler hoặc error chain tương ứng.

### Error response và bảo mật

Không gửi stack trace, token, Authorization header, internal SQL hoặc chi tiết hạ tầng nhạy cảm cho client. Log đủ correlation ID và root cause ở phía server, trả status/error code nhất quán. Tránh “nuốt” mọi lỗi rồi gửi HTTP 200.

## 14. Reactor subscription, cancellation và thread model

WebFlux không “chạy mọi Mono ngay lúc tạo”. Publisher có thể mô tả công việc deferred; phía HTTP runtime/framework là nơi kết nối và thực thi chain theo subscription.

Ví dụ so sánh:

~~~java
Mono<String> message = Mono.fromSupplier(() -> "hello");
// Tạo Mono chưa đồng nghĩa supplier đã được gọi.
// Server framework có thể subscribe như một phần xử lý request.
~~~

Đoạn trên là snippet Java có imports reactor.core.publisher.Mono, không phải server implementation.

### Nguyên tắc quan trọng

- **Không tự subscribe** trong WebFilter/controller để tạo response nếu framework đã nhận Publisher.
- **Không gọi .block() trên event-loop thread** để đợi database, WebClient hoặc Mono hoàn tất.
- **Không giả định mọi map/flatMap chạy trên thread duy nhất**: scheduling và async boundaries phụ thuộc publisher.
- Khi client hủy request/disconnect, cancellation có thể lan truyền downstream, nhưng tác dụng phụ đã xảy ra (ví dụ commit database transaction) không tự rollback nếu không có cơ chế transaction/cancellation phù hợp.
- Một long-running stream (SSE) có thể giữ response mở; completion của Mono<Void> chỉ đến khi stream hoàn tất, bị hủy hoặc lỗi.
- Với Flux nhiều phần tử, backpressure phối hợp tốc độ demand; không tự hứa tài nguyên luôn bounded nếu có buffer/cache/retry không giới hạn.
- ThreadLocal không tự động theo logical request xuyên qua các scheduler; dùng Reactor Context và công cụ context propagation phù hợp khi cần tracing/security.

### Đặc biệt với logging

Ví dụ gắn callback completion:

~~~java
return chain.filter(exchange)
        .doOnError(error -> logger.error("Request failed", error))
        .doFinally(signal -> logger.debug("Request terminated: {}", signal));
~~~

Đoạn này minh họa trong một class WebFilter có logger được khai báo. doFinally chạy với signal COMPLETE/ERROR/CANCEL; nó không bắt buộc tương ứng HTTP status đã được ghi. Nếu body đã commit, logger vẫn có thể thấy cancellation/error; không cố sửa response sau khi đã commit.

## 15. Ví dụ hoàn chỉnh: theo dõi hai kiểu handler đi qua cùng WebFlux chain

Ta xây một ứng dụng Spring Boot 3.3.13, Java 17:

- Embedded Reactor Netty mở HTTP port 8080 mặc định.
- WebFilter thêm header X-Flow vào mọi request.
- Annotation controller xử lý GET /api/greet/{name} và POST /api/echo.
- Functional RouterFunction xử lý GET /functional/ping.
- Integration test dùng WebTestClient gọi server thật trên RANDOM_PORT.
- Không thêm spring-boot-starter-web để tránh Boot mặc định chọn Servlet MVC.

### 15.1 Cấu trúc project

~~~text
webflux-flow-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/flow/
    │       ├── FlowApplication.java
    │       ├── GreetingController.java
    │       ├── FunctionalRoutes.java
    │       └── FlowHeaderFilter.java
    └── test/
        └── java/com/example/flow/
            └── FlowIntegrationTests.java
~~~

### 15.2 settings.gradle

~~~groovy
rootProject.name = 'webflux-flow-demo'
~~~

### 15.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu dự án có Gradle wrapper, dùng ./gradlew trên Linux/macOS hoặc gradlew.bat trên Windows; ví dụ bên dưới dùng lệnh gradle đã cài. Các version nêu là cấu hình minh họa nhất quán với Spring Boot 3.3.x; khi dùng version khác, để Boot dependency management chọn Reactor/Netty tương ứng.

### 15.4 FlowApplication.java

~~~java
package com.example.flow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlowApplication.class, args);
    }
}
~~~

### 15.5 GreetingController.java

~~~java
package com.example.flow;

import java.util.Locale;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping(
            path = "/greet/{name}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> greet(
            @PathVariable String name,
            @RequestParam(defaultValue = "false") boolean upper) {

        String greeting = "Xin chào, " + name;
        return Mono.just(upper
                ? greeting.toUpperCase(Locale.ROOT)
                : greeting);
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Payload> echo(@RequestBody Mono<Payload> input) {
        return input.map(payload ->
                new Payload(payload.message().trim()));
    }
}

record Payload(String message) {
}
~~~

Giải thích:

- @GetMapping được RequestMappingHandlerMapping nhận diện.
- RequestMappingHandlerAdapter phân giải @PathVariable và @RequestParam.
- Method trả Mono<String>; framework xử lý return value và ghi text/plain.
- POST dùng @RequestBody Mono<Payload>; JSON decoding diễn ra trong reactive pipeline.
- Record Payload là package-private trong cùng package và được Jackson xử lý theo hỗ trợ Java records.
- Nếu JSON thiếu message hoặc message là null, method map sẽ phát sinh NullPointerException khi gọi trim(); đây không phải xử lý input production. Cần validation và error policy khi xây API thật.

### 15.6 FunctionalRoutes.java

~~~java
package com.example.flow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route(
                RequestPredicates.GET("/functional/ping"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("pong"));
    }
}
~~~

Ở route này, handler được tìm qua RouterFunctionMapping thay vì RequestMappingHandlerMapping. Functional route trả ServerResponse, sau đó ServerResponseResultHandler giúp ghi response. Cả hai kiểu vẫn nằm dưới cùng HTTP handler và WebFilter chain.

### 15.7 FlowHeaderFilter.java

~~~java
package com.example.flow;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class FlowHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .set("X-Flow", "webfilter");

        return chain.filter(exchange);
    }
}
~~~

Một filter này được gọi cho cả /api/greet/An và /functional/ping khi request đi qua WebFlux chain. Header X-Flow được đặt trước khi response commit. Nó không chứng minh chính xác callback của mọi filter khác trong ứng dụng thực, vì thứ tự và điều kiện có thể khác khi thêm security/CORS hoặc custom filters.

### 15.8 Chạy và xem kết quả

Từ thư mục project:

~~~bash
gradle clean test bootRun
~~~

Trong terminal khác:

~~~bash
curl -i 'http://127.0.0.1:8080/api/greet/An?upper=true'
~~~

Kỳ vọng HTTP 200, Content-Type text/plain, header:

~~~text
X-Flow: webfilter
~~~

Và body:

~~~text
XIN CHÀO, AN
~~~

Gọi functional route:

~~~bash
curl -i 'http://127.0.0.1:8080/functional/ping'
~~~

Kỳ vọng HTTP 200, header X-Flow: webfilter và body:

~~~text
pong
~~~

Gọi JSON endpoint:

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/echo' \
    -H 'Content-Type: application/json' \
    -d '{"message":" WebFlux "}'
~~~

Kỳ vọng HTTP 200 và JSON body tương đương:

~~~json
{"message":"WebFlux"}
~~~

Không khẳng định chính xác mọi header (Date, Content-Length, Connection) hoặc thứ tự field JSON, bởi những chi tiết này phụ thuộc server/encoder. Những kết quả trên là kỳ vọng từ source code, **không phải log của một lần chạy được thực thi trong tài liệu**.

### 15.9 FlowIntegrationTests.java

~~~java
package com.example.flow;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FlowIntegrationTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void annotatedControllerUsesWebFluxPipeline() {
        client().get()
                .uri("/api/greet/An?upper=true")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Flow", "webfilter")
                .expectBody(String.class)
                .isEqualTo("XIN CHÀO, AN");
    }

    @Test
    void functionalRouteUsesSameFilterChain() {
        client().get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Flow", "webfilter")
                .expectBody(String.class)
                .isEqualTo("pong");
    }

    @Test
    void jsonBodyIsDecodedAndEncoded() {
        client().post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("message", " WebFlux "))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("WebFlux");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Test sử dụng RANDOM_PORT nên không phụ thuộc port 8080 có trống hay không. WebTestClient.bindToServer thực sự gửi HTTP request qua TCP tới embedded server trong test. Việc test thành công chứng minh từ server HTTP qua WebFilter đến hai handler style đều hoạt động, và JSON codec đã đọc/ghi body. Nó **không chứng minh** hiệu năng non-blocking hoặc backpressure tốt trong mọi tải.

### 15.10 Test phân biệt với mock setup

WebTestClient cũng có thể được bind vào ApplicationContext/WebHandler để test mà không mở HTTP server thật. Khi test theo cách đó, network adapter ReactorHttpHandlerAdapter không được kiểm chứng bằng socket. Vì bài này học đường đi *qua reactive server*, dùng RANDOM_PORT + bindToServer giúp quan sát đường đi đầy đủ hơn.

## 16. Các nhánh xử lý khác nhau của cùng một HTTP request

Đường đi không cố định cho mọi request. Một số tình huống:

### 16.1 URL không được mapping

Nếu GET /missing không match controller/RouterFunction, DispatcherHandler có thể phát tín hiệu không tìm thấy handler. WebFlux/Boot error handling có thể tạo HTTP 404. WebFilter vẫn có thể đã chạy trước khi biết URL không tồn tại.

### 16.2 Filter chặn request

Một WebFilter kiểm tra chính sách có thể đặt status, gọi response.setComplete() và không gọi chain.filter(exchange). Khi đó DispatcherHandler có thể **không được gọi** cho request ấy. Hãy test cả request bị từ chối và request hợp lệ.

### 16.3 Sai Content-Type hoặc body không đọc được

Request POST /api/echo với Content-Type không được endpoint hỗ trợ có thể cho HTTP 415, còn JSON malformed có thể cho HTTP 400. Điều kiện thực tế phụ thuộc mapping, codecs và error handling. RequestMappingHandlerAdapter có thể chưa gọi controller method nếu decode @RequestBody thất bại.

### 16.4 Controller phát Mono.error

Một controller trả Mono.error hoặc throw exception trước khi trả publisher có thể được xử lý qua @ExceptionHandler hoặc chuỗi WebExceptionHandler tùy nơi lỗi xuất hiện và cấu hình. Nếu response chưa commit, có thể dựng status/body lỗi; nếu đã commit, không thể coi việc thay status là luôn an toàn.

### 16.5 Client hủy request

Client có thể đóng connection giữa lúc đang đọc response streaming. Cancellation có thể lan truyền tới Publishers; nhưng database write hoặc external side effect đã thực thi không tự được hoàn tác. Cần thiết kế idempotency, transaction và compensation riêng theo nghiệp vụ.

## 17. WebFlux và Spring MVC: những tên trùng nhưng luồng khác

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Front controller | DispatcherServlet | DispatcherHandler |
| HTTP abstraction hạ tầng | Servlet request/response | Reactive ServerHttpRequest/ServerHttpResponse |
| Middleware web | Servlet Filter / HandlerInterceptor | WebFilter / WebExceptionHandler |
| Đối tượng request context | HttpServletRequest, Model... | ServerWebExchange |
| Kết quả adapter | ModelAndView hoặc response đã xử lý | Mono<HandlerResult> theo hợp đồng WebFlux |
| Body codec | HttpMessageConverter | HttpMessageReader / HttpMessageWriter |
| Xử lý I/O | Servlet API; có async support | Reactive server adapters và Publishers |
| Server thông thường trong starter | Tomcat | Reactor Netty |

Spring MVC hỗ trợ trả Mono hoặc Flux trong một số trường hợp. Vì thế đừng kết luận chỉ từ return type. Hãy kiểm tra SpringApplication chọn SERVLET hay REACTIVE, runtime factory, application context và front controller.

Tương tự, **WebClient là HTTP client**, không phải bằng chứng WebFlux DispatcherHandler đang phục vụ server request. Một MVC app có thể dùng WebClient mà vẫn nhận HTTP bằng Tomcat + DispatcherServlet.

## 18. Quan sát và debug đường đi theo từng lớp

### 18.1 Log khởi động

Xác định embedded server đang chạy: Reactor Netty, Tomcat hay runtime khác. Với WebFlux + Reactor Netty, log thường liên quan Netty web server startup, nhưng tên log có thể thay đổi theo Spring Boot version. Xem cả WebApplicationType và dependency tree nếu nghi MVC được chọn ngoài ý muốn.

Lệnh:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Xác nhận spring-boot-starter-webflux và spring-boot-starter-reactor-netty đã hiện diện; kiểm tra spring-boot-starter-web nếu ứng dụng không chạy theo stack mong muốn.

### 18.2 Debug log có chọn lọc

~~~properties
logging.level.org.springframework.web.server.adapter.HttpWebHandlerAdapter=DEBUG
logging.level.org.springframework.web.reactive.DispatcherHandler=TRACE
logging.level.org.springframework.web.reactive.result.method.annotation=DEBUG
logging.level.reactor.netty.http.server=INFO
~~~

Logger chính xác và lượng output phụ thuộc version. Không bật wiretap toàn bộ request/response trong production nếu chưa có biện pháp bảo vệ dữ liệu. TRACE có thể tăng overhead và lộ metadata URL; cần lọc token/query strings nhạy cảm trước khi chia sẻ log.

Khi cần xem auto-configuration:

~~~bash
gradle bootRun --args='--debug'
~~~

Đọc Condition Evaluation Report của reactive web server và WebFlux, không suy đoán từ việc dependency Reactor có sẵn.

### 18.3 Breakpoint gợi ý

Nếu IDE có source của Spring Framework 6.1.x và Reactor Netty phù hợp, có thể đặt breakpoint ở các điểm quan sát:

~~~text
ReactorHttpHandlerAdapter.apply(...)
HttpWebHandlerAdapter.handle(...)
FilteringWebHandler.handle(...)
ExceptionHandlingWebHandler.handle(...)
DispatcherHandler.handle(...)
DispatcherHandler.handleResult(...)
RequestMappingHandlerAdapter.handle(...)
HandlerFunctionAdapter.handle(...)
ResponseBodyResultHandler.handleResult(...)
ServerResponseResultHandler.handleResult(...)
~~~

Một số method/overload có thể khác theo patch version; kiểm tra implementation thực tế trước khi đặt breakpoint. Mục đích là theo dõi:

- Server request đi vào có headers/path gì?
- Khi nào ServerWebExchange được tạo?
- Filter nào chạy, có short-circuit không?
- Mapping chọn HandlerMethod hay HandlerFunction?
- Adapter gọi controller/function thành công không?
- Return handler đã ghi status/body chưa?
- Lỗi xảy ra trước hay sau commit?

### 18.4 Quan sát bằng header và correlation ID

Bài thực hành dùng X-Flow: webfilter để chứng minh request qua filter. Với production, nên dùng tracing/observation có quản lý correlation ID thay vì in toàn bộ request body hoặc token.

Có thể lưu một attribute trong exchange:

~~~java
exchange.getAttributes().put("flow.stage", "filter");
return chain.filter(exchange);
~~~

Đây là snippet trong WebFilter có biến exchange/chain. Attribute chỉ gắn với logical request, không phải global shared state; tránh đặt request data trong static field mutable.

## 19. Những sai lầm thường gặp

### Sai lầm 1: Tự gọi subscribe() trong WebFilter

~~~java
// Không nên làm:
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

Server không được chờ đúng publisher, error/cancellation có thể mất kết nối với request lifecycle, response commit có thể race.

### Sai lầm 2: Dùng HttpHandler như controller business API

HttpHandler là cấp thấp. Dùng RouterFunction, @RestController hoặc WebFilter thường đúng và ít rủi ro hơn. Chỉ thay HttpHandler khi thật sự xây framework/server integration.

### Sai lầm 3: Coi WebHandler đồng nhất với DispatcherHandler

DispatcherHandler là một implementation WebHandler quan trọng, nhưng WebHandler là interface tổng quát; chain còn có wrappers cho filter và exception. Một ứng dụng có thể cấu hình WebHandler khác cho use case chuyên biệt.

### Sai lầm 4: Gọi HttpWebHandlerAdapter là ReactorHttpHandlerAdapter

Lớp thứ nhất chuyển **HttpHandler ↔ WebHandler/ServerWebExchange**; lớp thứ hai chuyển **Reactor Netty objects ↔ Spring HttpHandler**. Chúng không làm cùng một việc.

### Sai lầm 5: Tin rằng Mono<Void> nghĩa là body rỗng

Mono<Void> chủ yếu đánh dấu completion của việc xử lý. Body có thể được ghi theo nhiều chunk qua một Flux<DataBuffer> khác.

### Sai lầm 6: Block event loop

Dùng .block(), Thread.sleep hoặc JDBC synchronous trong Netty event loop có thể làm nghẽn request khác. Dùng reactive driver thích hợp hoặc cô lập blocking đúng cách.

### Sai lầm 7: Bật filter logging payload toàn phần

Request body là stream có lifecycle và pooled buffers; đọc rồi phát lại body sai cách có thể khiến controller đọc body rỗng hoặc rò memory. Không ghi token/cookie và dữ liệu nhạy cảm.

### Sai lầm 8: Coi HTTP 404 là server không chạy

404 có thể do DispatcherHandler không có mapping dù server và HttpHandler đã hoạt động. Kiểm tra route và WebFilter trước khi điều tra port.

### Sai lầm 9: Trả JSON lỗi sau khi response đã commit

Một response streaming có thể đã gửi headers. Error handler không thể tùy ý sửa status/body sau điểm đó; hãy ghi log và xử lý network termination đúng ngữ nghĩa.

### Sai lầm 10: Cố “cải thiện hiệu năng” bằng cách tăng threads vô hạn

Không có giá trị event-loop thread hoặc queue nào luôn tối ưu. Đo throughput, p95/p99 latency, blocking, allocation và connection behavior trước khi điều chỉnh.

## 20. Checklist thao tác chẩn đoán

Khi một request WebFlux không đi tới handler mong đợi, kiểm tra theo trình tự:

1. **Stack:** Spring Boot đang chạy REACTIVE, không bị starter-web làm chuyển sang SERVLET?
2. **Server:** Reactor Netty hoặc reactive server khác đã bind cổng, client kết nối đúng address/port?
3. **Adapter runtime:** server đã gắn HttpHandler đúng với reactive application context?
4. **Exchange:** HttpWebHandlerAdapter tạo ServerWebExchange đúng request/path?
5. **WebFilter:** filter có đang short-circuit, sửa path/header hoặc trả lỗi?
6. **Security:** WebFlux security chain có cho phép request đi tiếp?
7. **Mapping:** RequestMappingHandlerMapping hoặc RouterFunctionMapping chọn route nào?
8. **Adapter:** handler được gọi bằng RequestMappingHandlerAdapter hoặc HandlerFunctionAdapter tương ứng?
9. **Body:** request có Content-Type đúng, codec hỗ trợ JSON/stream và giới hạn bộ nhớ?
10. **Publisher:** handler có return Mono/Flux hợp lệ, không tự subscribe/block?
11. **Result:** HandlerResultHandler nào ghi response? Status/header đã commit chưa?
12. **Error:** lỗi có được @ExceptionHandler/WebExceptionHandler xử lý trước commit không?
13. **Cancellation:** client ngắt kết nối hay timeout từ proxy xảy ra không?
14. **Test:** kiểm chứng cả annotation controller lẫn functional route qua RANDOM_PORT.

Nếu điểm 2 thất bại, hãy xử lý server/port/dependency trước. Nếu điểm 7 thất bại, không sửa HttpHandler; kiểm tra mapping. Nếu điểm 8–11 thất bại, xem argument binding, codec, reactive Publisher và result handler. Nếu lỗi bắt đầu ở điểm 12–13, xem thời điểm response commit và lifecycle của connection.

## 21. Tóm tắt

Đường đi của một HTTP request trong WebFlux có **hai tầng adapter nối tiếp nhau**: adapter ở tầng server (ví dụ ReactorHttpHandlerAdapter) chuyển đối tượng Reactor Netty thành Spring HTTP abstraction; sau đó HttpWebHandlerAdapter chuyển HttpHandler call thành **ServerWebExchange + WebHandler chain**. Bên trong, các WebExceptionHandler/WebFilter bao quanh WebHandler chính; DispatcherHandler dùng HandlerMapping, HandlerAdapter và HandlerResultHandler để map, gọi và viết kết quả của controller hoặc functional handler.

**Bất biến cần nhớ:** HttpHandler nhận ServerHttpRequest/ServerHttpResponse; WebHandler nhận ServerWebExchange; cả hai trả Mono<Void> để biểu diễn completion của xử lý. Việc tạo Publisher, subscription, I/O và commit response là các giai đoạn khác nhau. Nắm đúng ranh giới này giúp debug request routing, middleware, body decoding, streaming và lỗi sau commit chính xác hơn.

## 22. Tài liệu tham khảo

- Spring Framework 6.1 — WebHttpHandlerBuilder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html
- Spring Framework 6.1 — ReactorHttpHandlerAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ReactorHttpHandlerAdapter.html
- Spring Framework 6.1 — HttpHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/HttpHandler.html
- Spring Framework 6.1 — WebHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebHandler.html
- Spring Framework — WebFlux Reactive Core / WebHandler API: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework — Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Reactor Netty — HTTP Server: https://projectreactor.io/docs/netty/release/reference/http-server.html
