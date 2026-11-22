# ServerWebExchange và vòng đời yêu cầu reactive trong Spring WebFlux

## Mục tiêu học tập

Spring WebFlux xử lý HTTP theo mô hình reactive, khác với cách hình dung “mỗi request giữ một thread đến khi hoàn tất” thường thấy ở các chương trình đồng bộ. **ServerWebExchange** là ngữ cảnh HTTP cấp request mà nhiều thành phần WebFlux cùng sử dụng để đọc yêu cầu, chuẩn bị phản hồi và trao đổi dữ liệu trong suốt quá trình xử lý.

Sau bài này, bạn có thể:

- Giải thích ServerWebExchange là gì và vì sao nó không phải một HTTP session hay Reactor Context.
- Phân biệt ServerHttpRequest, ServerHttpResponse, exchange attributes, WebSession và Principal.
- Mô tả luồng đi từ HTTP server qua HttpHandler, WebFilter, DispatcherHandler đến controller/handler và response.
- Viết WebFilter reactive đúng cách mà không gọi subscribe() hoặc block() thủ công.
- Hiểu khi nào response được commit, cách gắn header và hệ quả khi lỗi xảy ra sau khi đã gửi response.
- Phân tích vòng đời thành công, lỗi, timeout, cancellation và các lưu ý về streaming/backpressure.
- Kiểm thử hành vi từ request đến response bằng WebTestClient.

## 1. ServerWebExchange là gì?

Trong Spring WebFlux, interface **org.springframework.web.server.ServerWebExchange** mô tả ngữ cảnh của một lần trao đổi HTTP ở mức WebHandler API. Nó cung cấp hai đối tượng cốt lõi:

- **ServerHttpRequest** từ getRequest(): mô tả request được server nhận.
- **ServerHttpResponse** từ getResponse(): đại diện response mà server sẽ ghi.

Ngoài hai đối tượng đó, exchange còn cung cấp map thuộc tính theo request, thông tin locale, session, principal và các API dữ liệu form/multipart.

Có thể hình dung:

~~~text
                       ServerWebExchange
                    (một lần trao đổi HTTP)
                                |
        +-----------------------+-----------------------+
        |                       |                       |
   getRequest()            getResponse()         request context
        |                       |                       |
   method, URI,           status, headers,         attributes,
   headers, cookies,      cookies, response       WebSession,
   query, body            body, commit state      Principal, locale
~~~

**Phân biệt quan trọng:** Một ServerWebExchange gắn với quá trình xử lý một request, không phải một object đại diện cho toàn bộ TCP connection. Với keep-alive hoặc HTTP/2, cùng kết nối có thể phục vụ nhiều request; mỗi request có ngữ cảnh xử lý riêng.

Exchange còn không phải đối tượng làm việc tương đương hoàn toàn với **HttpServletRequest/HttpServletResponse** của Spring MVC. WebFlux cung cấp các abstraction reactive, không yêu cầu Servlet container khi chạy trên Reactor Netty.

### Những API thường dùng

| API | Mục đích | Lưu ý |
|---|---|---|
| exchange.getRequest() | Lấy ServerHttpRequest | Metadata và body được biểu diễn theo cách phù hợp reactive I/O. |
| exchange.getResponse() | Lấy ServerHttpResponse | Chỉnh status/header trước khi response commit. |
| exchange.getAttributes() | Map mutable gắn với request hiện tại | Chia sẻ dữ liệu giữa filter và handler. |
| exchange.getAttribute(name) | Đọc thuộc tính tùy chọn | Có thể trả null nếu chưa tồn tại. |
| exchange.getRequiredAttribute(name) | Đọc thuộc tính bắt buộc | Ném lỗi nếu thiếu; tránh dùng khi giá trị có thể vắng mặt. |
| exchange.getSession() | Mono<WebSession> | Không đồng nghĩa với tự động tạo session có dữ liệu. |
| exchange.getPrincipal() | Mono<Principal> | Có thể empty nếu chưa có người dùng xác thực. |
| exchange.getLocaleContext() | LocaleContext đã phân giải | Phụ thuộc resolver và request. |
| exchange.getFormData() | Mono<MultiValueMap<String,String>> | Dành cho form-urlencoded, có xử lý và cache form data. |
| exchange.getMultipartData() | Mono<MultiValueMap<String,Part>> | Dành cho multipart, cần quản lý chi phí bộ nhớ/tài nguyên. |
| exchange.getLogPrefix() | Prefix log liên quan exchange | Hữu ích để tương quan log request. |
| exchange.mutate() | Tạo builder cho exchange được decorate | Không tự sửa request gốc; có thể thay request/response được chuyển xuống chain. |

Tên và chi tiết API có thể được mở rộng trong các phiên bản Spring Framework; ở ví dụ bên dưới ta dùng các API phổ biến của Spring Framework 6.x và Spring Boot 3.x.

## 2. Vị trí ServerWebExchange trong kiến trúc WebFlux

WebFlux cung cấp hai cấp abstraction HTTP server:

1. **HttpHandler**: hợp đồng tối giản tiếp nhận ServerHttpRequest và ServerHttpResponse, trả về Mono<Void> mô tả quá trình xử lý.
2. **WebHandler API**: abstraction cao hơn, dùng ServerWebExchange và hỗ trợ WebFilter, WebExceptionHandler, session, form data, locale, principal.

Một cấu trúc xử lý điển hình của WebFlux với controller annotation:

~~~text
HTTP client
    |
    v
Reactor Netty / HTTP server khác
    |
    v
server adapter / HttpHandler
    |
    v
HttpWebHandlerAdapter
    |  tạo ServerWebExchange và nối HTTP abstractions
    v
WebExceptionHandler / exception-handling wrapper
    |
    v
WebFilter chain
    |  filter trước + filter sau, hoặc short-circuit
    v
DispatcherHandler (WebHandler của WebFlux)
    |
    +--> HandlerMapping: tìm route/handler
    |
    +--> HandlerAdapter: gọi controller hoặc handler phù hợp
    |
    +--> HandlerResultHandler: chuyển giá trị thành response
    |      JSON, view, ResponseEntity, streaming...
    v
ServerHttpResponse ghi status/headers/body
    |
    v
HTTP client
~~~

Sơ đồ này là hình dung kiến trúc, không khẳng định mọi thành phần luôn chạy theo một danh sách tuần tự cứng. Reactive pipeline có thể chạy bất đồng bộ, trả về Mono/Flux, nhảy thread qua scheduler và kết thúc theo các tín hiệu khác nhau.

**DispatcherHandler** là front controller của Spring WebFlux, tương tự vai trò của DispatcherServlet trong MVC nhưng dựa trên reactive WebHandler API. Framework cũng hỗ trợ functional endpoints thông qua RouterFunction/HandlerFunction; cả hai phong cách được xây trên hạ tầng WebFlux.

**WebHttpHandlerBuilder** là thành phần có thể tập hợp WebHandler, WebFilter, WebExceptionHandler và các collaborator thành HttpHandler để gắn vào HTTP server. Trong ứng dụng Spring Boot, phần lớn quá trình kết nối này được auto-configuration thực hiện.

## 3. Vòng đời của một request từ đầu đến cuối

### Giai đoạn 1 — Server nhận HTTP request

HTTP server nhận dữ liệu từ socket. Adapter của server chuyển metadata và dữ liệu request thành các abstraction reactive. Header, URL, method thường có thể truy cập ngay; body có thể được cung cấp dưới dạng luồng dữ liệu chưa được tiêu thụ.

Không đồng nghĩa với việc body đã được đọc toàn bộ vào bộ nhớ ngay khi server nhận request.

### Giai đoạn 2 — Tạo exchange và thiết lập context

WebFlux xây dựng ServerWebExchange từ ServerHttpRequest và ServerHttpResponse, cùng các thành phần trợ giúp như WebSessionManager, codecs và locale resolver.

Từ đây, filter và handler trong cùng một request có thể làm việc trên exchange, chẳng hạn gắn trace ID vào attributes hoặc thêm header cho response.

### Giai đoạn 3 — Chạy chuỗi WebFilter

Mỗi **WebFilter** có hợp đồng:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Filter có thể:

- Quan sát request method, path, header.
- Gắn metadata vào exchange attributes.
- Thêm/chỉnh response status hoặc header trước khi response commit.
- Chuyển request/exchange được decorate cho thành phần tiếp theo.
- Gọi chain.filter(exchange) để tiếp tục.
- Short-circuit khi cần trả response ngay, ví dụ request bị từ chối.

Kết quả Mono<Void> thể hiện **quá trình hoàn tất xử lý HTTP**, không phải giá trị body của controller. Đây là contract mà framework subscribe vào, không phải lời mời gọi subscribe() thủ công.

### Giai đoạn 4 — DispatcherHandler chọn route và handler

Khi request được chuyển tiếp, HandlerMapping tìm handler phù hợp với path, HTTP method và các điều kiện mapping khác.

Với annotation controller, HandlerAdapter đưa vào các tham số như @PathVariable, @RequestParam, @RequestBody, hoặc ServerWebExchange; rồi gọi method controller.

Method có thể trả một đối tượng thường, Mono<T>, Flux<T>, ResponseEntity<T>, Mono<ResponseEntity<T>> hoặc các kiểu được WebFlux hỗ trợ. HandlerResultHandler phối hợp codecs để ghi response thích hợp.

### Giai đoạn 5 — Reactive stream thực sự chạy

Một controller trả Mono hoặc Flux thường mới mô tả công việc. Khi framework subscribe, dữ liệu được phát theo signal và demand của Reactive Streams.

Ví dụ, một controller:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> findOne(@PathVariable long id) {
    return repository.findById(id);
}
~~~

Không có lý do gọi block() để lấy Product rồi tạo response thủ công. Controller trả Publisher, WebFlux điều phối subscription, serialization và việc ghi response.

Không được hiểu rằng **mọi** lệnh trong method controller đều lazy: code Java thực hiện trực tiếp trước khi tạo/trả Publisher vẫn chạy khi controller được gọi. Những thao tác nằm trong Mono.defer, Mono.fromCallable, flatMap và Publisher khác phụ thuộc thời điểm subscription.

### Giai đoạn 6 — Ghi response và commit

Trước khi ghi response, framework xác định status, headers và codec phù hợp. ServerHttpResponse trở thành **committed** khi status/headers được áp dụng để phát response; điều đó có thể xảy ra lúc bắt đầu ghi body hoặc hoàn tất response.

Khi response đã commit, không thể kỳ vọng thay đổi status/headers còn hiệu lực. Stream có thể vẫn tiếp tục truyền body sau khi headers đã được gửi.

### Giai đoạn 7 — Kết thúc

Có ba dạng kết thúc quan trọng:

- **ON_COMPLETE**: pipeline hoàn tất bình thường, response được xử lý thành công theo hợp đồng.
- **ON_ERROR**: publisher phát lỗi; framework và exception handlers có thể chuyển lỗi thành HTTP response nếu còn khả năng.
- **CANCEL**: subscriber bị hủy, ví dụ client ngắt kết nối hoặc timeout hủy công việc phía sau.

Không được suy ra mọi ON_COMPLETE đều đồng nghĩa HTTP 200; status có thể là 201, 204, 404 hoặc giá trị khác, tùy logic và bộ xử lý.

## 4. Đọc thông tin request từ exchange

**ServerHttpRequest** có các thông tin phổ biến:

| API | Ví dụ | Ý nghĩa |
|---|---|---|
| getMethod() | GET | HTTP method. |
| getURI() | URI đầy đủ mà server nhìn thấy | Có thể bị proxy tác động. |
| getPath() | RequestPath | Cho phép thao tác path theo cách có cấu trúc. |
| getHeaders() | HttpHeaders | Header request, có thể nhiều giá trị. |
| getQueryParams() | MultiValueMap | Các query parameter đã được framework xử lý. |
| getCookies() | MultiValueMap | Cookie nhận từ client. |
| getBody() | Flux<DataBuffer> | Luồng dữ liệu body, không mặc định là String. |
| getId() | String | Identifier của request, hữu ích cho logging. |

Ví dụ đọc metadata bằng controller:

~~~java
@GetMapping("/request-info")
public Mono<Map<String, String>> requestInfo(ServerWebExchange exchange) {
    ServerHttpRequest request = exchange.getRequest();

    return Mono.just(Map.of(
        "method", request.getMethod().name(),
        "path", request.getPath().pathWithinApplication().value(),
        "requestId", request.getId()
    ));
}
~~~

Đây là đoạn method minh họa; để chạy cần đặt bên trong @RestController, thêm imports phù hợp và ứng dụng WebFlux.

**Đừng đánh đồng request body với request metadata.** Query parameters và headers có thể đọc từ request ngay; body là Flux<DataBuffer> và chỉ nên được tiêu thụ theo cách thích hợp với framework.

## 5. Các kiểu dữ liệu ngữ cảnh: attributes, session, principal, Reactor Context

Các tên gọi sau dễ bị dùng lẫn nhau nhưng có vòng đời và nhiệm vụ khác nhau.

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| exchange.getAttributes() | Một HTTP exchange/request | Chia sẻ metadata giữa WebFilter, handler và infrastructure của cùng request. |
| exchange.getSession() | Web session gắn client/session id, có thể sống qua nhiều request | Lưu trạng thái session nếu ứng dụng dùng session. |
| exchange.getPrincipal() | Danh tính đã được phân giải cho request | Phục vụ code cần identity; có thể không có giá trị. |
| Reactor Context | Một subscription/reactive chain | Truyền metadata theo reactive context, không lệ thuộc ThreadLocal. |
| ThreadLocal | Một Java thread | Không nên xem là request context đáng tin trong pipeline có thể đổi thread. |

### Exchange attributes

Map được trả về bởi getAttributes() có thể ghi:

~~~java
exchange.getAttributes().put("example.traceId", traceId);
~~~

Sau đó, thành phần khác có thể lấy:

~~~java
String traceId = exchange.getAttribute("example.traceId");
~~~

Đây là map mutable theo request. Chọn key có namespace để tránh trùng với thuộc tính framework hoặc thư viện; tránh giữ reference tới exchange trong cache toàn cục hoặc lưu trực tiếp thông tin nhạy cảm không cần thiết.

### WebSession

getSession() trả Mono<WebSession>. Truy cập session có thể cho một đối tượng WebSession, nhưng chỉ gọi getSession() **không tự động** khiến server tạo/persist một session mới có trạng thái. Việc lưu session được quản lý theo cấu hình và trạng thái session.

Ví dụ đọc thuộc tính:

~~~java
Mono<String> cart = exchange.getSession()
    .map(session -> session.getAttributeOrDefault("cartId", "none"));
~~~

Nếu một endpoint hoàn toàn stateless, đừng tạo session chỉ để truyền dữ liệu giữa hai bước trong cùng request; exchange attributes hoặc Reactor Context có thể phù hợp hơn.

### Principal

getPrincipal() trả một Publisher về người dùng đã xác thực; có thể empty. Để xử lý không có danh tính:

~~~java
Mono<String> userName = exchange.getPrincipal()
    .map(principal -> principal.getName())
    .defaultIfEmpty("anonymous");
~~~

Danh tính và quyền truy cập thực tế do hệ thống security quyết định. Không tự xem header do client gửi như bằng chứng xác thực nếu chưa được Spring Security hoặc một cơ chế tin cậy xác minh.

### Reactor Context

Reactor Context đi theo subscription, hữu ích khi một chuỗi reactive chuyển thread. Exchange attributes thuận tiện hơn cho các thành phần WebHandler cần trao đổi dữ liệu theo request. Hai cơ chế có thể phối hợp nhưng **không đồng nhất**.

Ví dụ truyền metadata qua Reactor Context:

~~~java
Mono<String> operation = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("correlationId", "missing"))
).contextWrite(context -> context.put("correlationId", "req-123"));
~~~

Khi có subscriber, Mono trên phát "req-123". Đây là ví dụ độc lập về Reactor Context, không chứng minh exchange tự động được đưa vào Reactor Context trong mọi môi trường.

## 6. WebFilter: đúng vai trò và cách chạy reactive

WebFilter dùng cho logic HTTP xuyên suốt nhiều endpoint, ví dụ logging, trace metadata, một số header hoặc các concern hạ tầng. Hợp đồng phải được nối vào chain, không được chặn event loop bằng I/O blocking.

### Ví dụ hoàn chỉnh: trace ID trong filter và controller

Giả sử bạn tạo một dự án **Spring Boot 3.x, Java 17+**, có dependency **spring-boot-starter-webflux** qua Spring Initializr. Trong một project Spring Boot 4.x, dùng starter WebFlux tương ứng do phiên bản đó quản lý.

Tạo ba Java file trong package **com.example.exchange**.

**File ExchangeApplication.java:**

~~~java
package com.example.exchange;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExchangeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExchangeApplication.class, args);
    }
}
~~~

**File TraceWebFilter.java:**

~~~java
package com.example.exchange;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class TraceWebFilter implements WebFilter {

    public static final String TRACE_KEY = "example.traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();

        exchange.getAttributes().put(TRACE_KEY, traceId);
        exchange.getResponse().getHeaders().set("X-Trace-Id", traceId);

        return chain.filter(exchange);
    }
}
~~~

**File PingController.java:**

~~~java
package com.example.exchange;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Mono<Map<String, String>> ping(ServerWebExchange exchange) {

        String traceId =
            exchange.getAttributeOrDefault(TraceWebFilter.TRACE_KEY, "none");

        return Mono.just(Map.of(
            "message", "pong",
            "traceId", traceId
        ));
    }
}
~~~

Chạy từ project đã có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Gọi API:

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Kết quả được mong đợi là HTTP 200, có header **X-Trace-Id** và JSON chứa **message: pong** cùng **traceId**. Giá trị UUID thay đổi theo request, vì vậy không nên viết test so sánh UUID với một chuỗi cố định.

Ví dụ kết quả body minh họa (UUID ở mỗi lần chạy sẽ khác):

~~~json
{
  "message": "pong",
  "traceId": "123e4567-e89b-12d3-a456-426614174000"
}
~~~

Từ ví dụ rút ra:

1. Filter tạo metadata một lần trong vòng xử lý HTTP request, gắn vào attributes.
2. Controller đọc metadata từ cùng exchange.
3. Filter đặt response header **trước** khi chain bắt đầu xử lý body.
4. Filter trả Mono<Void> của chain; không tự subscribe và không gọi block().
5. Những bước sau như security, handler mapping và response writing vẫn do framework điều phối.

Nếu có nhiều WebFilter, thứ tự được quyết định bởi cơ chế ordering của Spring và những filter được framework/ứng dụng đăng ký. Đừng giả định chỉ dựa vào @Order(0) rằng filter luôn chạy trước mọi Spring Security filter; cần kiểm tra chain thực tế nếu chính sách bảo mật phụ thuộc thứ tự.

## 7. Filter short-circuit và cách kết thúc response

WebFilter không bắt buộc chuyển tiếp mọi request. Một filter có thể từ chối request rồi hoàn tất response tại chỗ. Ví dụ method minh họa:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String token = exchange.getRequest()
        .getHeaders()
        .getFirst("X-Demo-Token");

    if (!"allow".equals(token)) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
~~~

Để dùng trong một class WebFilter, cần import các kiểu Spring tương ứng, bao gồm **org.springframework.http.HttpStatus**. Đây chỉ là minh họa luồng ngắn, **không phải** một cơ chế xác thực sản xuất: secret/tokens không nên được kiểm tra kiểu hardcode, và hệ thống nên dùng Spring Security hoặc giải pháp security phù hợp.

Điều cần phân biệt:

- Trả **chain.filter(exchange)**: chuyển request xuống những filter và handler tiếp theo.
- Trả **response.setComplete()**: kết thúc response không có body trong nhánh minh họa.
- Trả một Mono không được framework subscribe hoặc tự gọi subscribe trong filter: dễ khiến request không hoàn tất như dự kiến.
- Bỏ gọi chain.filter(exchange) mà không chủ ý short-circuit có thể khiến controller không bao giờ chạy.

## 8. Mutate exchange khi cần thay request trước khi chuyển tiếp

Phần lớn ứng dụng không cần thay request. Khi thực sự cần thay header hoặc URL theo quy tắc hạ tầng, dùng API decorator/builder thay vì tự thay đổi những object có tính bất biến.

Đoạn minh họa bên trong WebFilter:

~~~java
ServerHttpRequest updatedRequest = exchange.getRequest()
    .mutate()
    .header("X-Internal-Source", "gateway")
    .build();

ServerWebExchange updatedExchange = exchange.mutate()
    .request(updatedRequest)
    .build();

return chain.filter(updatedExchange);
~~~

Để compile trong một WebFilter, import **org.springframework.http.server.reactive.ServerHttpRequest**. exchange.mutate().build() tạo wrapper/decorator tương ứng, cung cấp request đã được thay đổi cho downstream. Không được coi đây là việc sửa ngược lại mọi nơi đang giữ reference tới request gốc.

Nếu mục tiêu chỉ là trao đổi metadata nội bộ, exchange attributes thường ít xâm lấn hơn việc ghi thêm header, vì header có thể bị truyền tới code khác hoặc bị hiểu là dữ liệu do client cung cấp. Đặc biệt không tự nâng quyền theo một header có thể do client sửa.

Với việc thêm hoặc rewrite body, việc chỉ gọi mutate().header(...) là **không đủ**. Body là Flux<DataBuffer>, cần wrapper/decorator và quản lý buffer/backpressure đúng cách.

## 9. Request body: đọc một lần, codec và quản lý DataBuffer

ServerHttpRequest.getBody() trả **Flux<DataBuffer>**, phản ánh dữ liệu request dưới dạng streaming. Những điều phải chú ý:

- Không giả định có sẵn một String JSON đồng bộ từ request body.
- Request body là stream; nếu filter tự tiêu thụ, handler phía sau có thể không còn đọc được body như mong đợi.
- Muốn filter kiểm tra body rồi vẫn chuyển xuống handler, cần thiết kế cơ chế cache/decorate dữ liệu chính xác, đồng thời giới hạn kích thước, quản lý reference-counted buffers khi cần.
- Với request body lớn, gom toàn bộ vào RAM chỉ để log là nguy hiểm. Tránh log mật khẩu, token, dữ liệu cá nhân và payload nhạy cảm.
- Nếu cần decode JSON, @RequestBody Mono<MyDto> hoặc các API codec của framework thường an toàn, dễ duy trì hơn việc tự ghép byte từ Flux<DataBuffer>.

Ví dụ controller đọc body theo reactive contract:

~~~java
public record EchoRequest(String message) {
}

@PostMapping("/api/echo")
public Mono<Map<String, String>> echo(
        @RequestBody Mono<EchoRequest> payload) {

    return payload.map(value ->
        Map.of("echo", value.message())
    );
}
~~~

Đây là đoạn mã minh họa cần nằm trong @RestController, thêm imports @PostMapping, @RequestBody, Mono và Map. Khi gửi application/json với body hợp lệ, WebFlux sử dụng message reader/codec tương ứng để decode dữ liệu.

### Form và multipart

ServerWebExchange cung cấp getFormData() cho application/x-www-form-urlencoded và getMultipartData() cho multipart/form-data. Chúng trả Mono vì parsing dữ liệu có thể cần I/O và tiêu thụ request body.

Không nên vừa tự subscribe getBody() vừa mong framework tự decode lại cùng body không có cơ chế cache phù hợp. Multipart file có thể lớn: lựa chọn mô hình streaming/tạm lưu và giới hạn cấu hình cần dựa theo yêu cầu an toàn tài nguyên.

## 10. Response status, headers, body và thời điểm commit

ServerHttpResponse cung cấp các thao tác như:

- **setStatusCode(...)**: chọn HTTP status trước commit.
- **getHeaders()**: truy cập response headers.
- **getCookies()**: cấu hình response cookies theo API được hỗ trợ.
- **beforeCommit(...)**: đăng ký callback reactive chạy trước khi response được commit.
- **isCommitted()**: kiểm tra response đã commit hay chưa.
- **writeWith(...)**: ghi body từ Publisher<DataBuffer>.
- **setComplete()**: biểu diễn quá trình hoàn tất response.

Một nguyên tắc quan trọng: **status và headers chỉ nên thay đổi trước khi commit**. Các đoạn xử lý chạy sau khi response đã bắt đầu truyền không được kỳ vọng có thể đổi HTTP status từ 200 sang 500.

### Dùng beforeCommit cho công việc trước khi gửi headers

Ví dụ bên trong WebFilter:

~~~java
ServerHttpResponse response = exchange.getResponse();

response.beforeCommit(() -> Mono.fromRunnable(() -> {
    response.getHeaders().set("X-Processed", "yes");
}));

return chain.filter(exchange);
~~~

Cần import **org.springframework.http.server.reactive.ServerHttpResponse** và **reactor.core.publisher.Mono**. Callback đã đăng ký được thực thi theo quá trình commit response, không phải ngay lúc dòng trước đó được gọi.

Nếu thay vì đó gọi getHeaders().set(...) trước chain, cũng hợp lệ khi chắc chắn chưa có thành phần nào đã commit response. beforeCommit phù hợp khi muốn thực hiện tác vụ ngay trước lúc headers được áp dụng, nhưng không nên sử dụng callback cho công việc blocking hoặc các thao tác I/O kéo dài.

### Khi nào isCommitted quan trọng?

Nếu response chưa commit, error handler có thể có khả năng chọn status/body khác. Khi đã commit, việc thay status có thể không thành công và framework không thể “rút lại” những byte đã gửi. Đặc biệt với streaming, lỗi có thể xảy ra sau khi một số phần tử body đã được truyền.

Không tự gọi setComplete() hoặc writeWith() trong controller đồng thời vẫn trả một đối tượng để WebFlux tự serialize response, trừ khi bạn chủ động xây custom response handler. Trộn hai cơ chế có thể dẫn tới double write hoặc lỗi response committed.

## 11. Mono<Void> của WebFilter và thứ tự tín hiệu

WebFilter thông thường chỉ nối vòng đời request:

~~~java
return chain.filter(exchange)
    .doOnSubscribe(subscription -> logStart())
    .doOnError(error -> logFailure(error))
    .doFinally(signal -> logFinish(signal.name()));
~~~

Đây là pseudocode minh họa cần có các method logStart, logFailure, logFinish phù hợp; nó cho thấy vị trí gắn hook, không phải chương trình chạy độc lập.

**Các operator nên hiểu:**

- **doOnSubscribe**: callback khi có subscription; không phải nơi thực thi I/O blocking.
- **doOnError**: quan sát lỗi, không tự xử lý hoặc thay lỗi.
- **onErrorResume**: có thể chuyển nhánh sang một Publisher dự phòng theo logic rõ ràng.
- **doFinally**: callback khi stream kết thúc vì complete, error hoặc cancellation.
- **then(...)**: nối một hành động sau khi publisher trước hoàn tất bình thường, thường dùng khi làm việc với Mono<Void>.
- **timeout(...)**: phát timeout error theo ngưỡng; xử lý hoặc mapping response tùy mục tiêu.

Chú ý: doFinally có thể được gọi khi một publisher nằm trong chain kết thúc, nhưng không đủ để kết luận client đã đọc hết response. Ngoài ra một WebExceptionHandler bên ngoài filter có thể biến lỗi của chain thành HTTP response khác, nên log ở filter và kết quả HTTP cuối cùng có thể không hoàn toàn giống nhau.

Cũng tránh phụ thuộc vào thread identity khi đọc log: reactive processing có thể đổi thread qua Scheduler hoặc callback I/O.

## 12. Xử lý lỗi trong vòng đời request

Lỗi có thể phát sinh ở nhiều tầng:

- Parse request, decode JSON hoặc validation.
- HandlerMapping không tìm thấy route hoặc không phù hợp HTTP method.
- Controller/service phát exception hoặc Mono.error.
- Filter phát lỗi hoặc chủ động ngắt chain.
- Response codec không thể encode dữ liệu.
- Network I/O lỗi trong khi response đang streaming.

Spring WebFlux có nhiều điểm xử lý lỗi:

| Cơ chế | Phạm vi thường dùng |
|---|---|
| @ExceptionHandler | Xử lý exception cho controller theo phạm vi annotation. |
| @RestControllerAdvice | Chuyển lỗi controller thành HTTP response theo logic nghiệp vụ. |
| ResponseStatusException | Biểu diễn HTTP status khi không có kết quả thành công. |
| WebExceptionHandler | Xử lý lỗi ở tầng WebHandler chain, bao gồm filter/handler theo cơ chế đăng ký. |
| Spring Boot reactive error handling | Tạo phản hồi lỗi mặc định theo cấu hình ứng dụng. |

Ví dụ chuyển lỗi nghiệp vụ thành 404 khi service không tìm thấy dữ liệu:

~~~java
@GetMapping("/api/items/{id}")
public Mono<Item> item(@PathVariable long id) {
    return service.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Item not found"
            )
        ));
}
~~~

Đây là method minh họa: cần các imports Spring và service thực tế. Mấu chốt là **Mono.empty()** không giống **Mono.error()**. Handler ở tầng HTTP có thể áp dụng cách biểu diễn empty theo contract; nếu yêu cầu API phải trả 404 thì cần biểu diễn rõ qua status hoặc exception.

**Lỗi sau response commit** là trường hợp khác: HTTP headers hoặc một phần body đã được gửi, vì vậy error handler không thể luôn thay response thành một JSON error chuẩn. Với SSE hoặc NDJSON streaming, cần thiết kế giao thức ứng dụng để báo lỗi qua sự kiện hoặc đóng stream theo quy tắc thích hợp.

Đừng biến mọi exception thành HTTP 200 chỉ để “không lỗi”. Trạng thái HTTP nên phản ánh kết quả thực tế của request.

## 13. Cancellation, timeout và backpressure

### Cancellation

Khi client đóng kết nối, timeout hoặc subscriber phía server bị hủy, pipeline có thể nhận tín hiệu cancellation. Điều này cho phép nhiều upstream publisher dừng công việc còn lại.

Tuy nhiên:

- Cancellation không đảm bảo mọi I/O bên ngoài đã gửi đều được thu hồi.
- Cancellation không tự động rollback một transaction đã commit hoặc một side effect đã xảy ra.
- Signal CANCEL không luôn xuất hiện đúng lúc socket đóng ở mọi kiểu server và transport.
- Tự gọi subscribe() trong filter/controller tạo thêm subscription độc lập, dễ làm mất liên hệ với request cancellation.

Vì vậy, controller và filter thường nên **trả publisher** để WebFlux sở hữu subscription và quản lý vòng đời.

### Backpressure

Reactive Streams cho phép subscriber điều tiết số phần tử cần nhận qua cơ chế demand. Với dữ liệu streaming lớn, đây là một phần quan trọng giúp không giữ toàn bộ dữ liệu trong RAM.

Backpressure không đồng nghĩa tất cả thành phần network tự động chạy ở tốc độ giống nhau hoặc nguồn ngoài luôn điều chỉnh được; có thể có buffer, prefetch và giới hạn riêng.

Các tình huống cần chú ý:

- Dùng collectList() trên Flux rất lớn hoặc vô hạn có thể gây tăng bộ nhớ.
- Log mọi DataBuffer/request body có thể làm phát sinh lưu trữ dữ liệu ngoài dự kiến.
- Thao tác blocking trên event-loop thread làm các request khác chậm theo.
- Ghi dữ liệu streaming cần tôn trọng lifecycle và downstream demand.

### Timeout

Khi đặt timeout trên một Mono/Flux bên trong service, timeout là tín hiệu reactive error. Còn timeout trên reverse proxy hoặc HTTP server có thể diễn ra ở tầng khác. Phải đồng bộ deadline của client, gateway, server và downstream; không nên giả định chỉ có một timeout cho toàn bộ request.

## 14. Phân biệt exchange với Servlet request và WebClient

Ba khái niệm dễ gây nhầm lẫn:

| Môi trường | Đối tượng chính | Vai trò |
|---|---|---|
| Spring MVC / Servlet | HttpServletRequest và HttpServletResponse | Request/response theo Servlet API. |
| Spring WebFlux server | ServerWebExchange | Ngữ cảnh request-response reactive cho server-side WebHandler chain. |
| Spring WebClient | ClientRequest, ClientResponse, ExchangeFilterFunction | Các đối tượng phía HTTP client reactive; không phải ServerWebExchange. |

**WebFilter** thuộc phía HTTP server trong WebFlux. **ExchangeFilterFunction** thuộc phía WebClient. Hai loại filter đều có ý tưởng interception, nhưng API, vị trí và vòng đời khác nhau; không copy nguyên code của một bên sang bên kia.

Trong functional endpoint WebFlux, bạn thường làm việc với **ServerRequest** và **ServerResponse** thay vì trực tiếp đụng tới ServerWebExchange ở mọi method. Điều đó không có nghĩa exchange không tồn tại ở hạ tầng thấp hơn.

## 15. Kiểm thử request lifecycle bằng WebTestClient

Với ứng dụng từ mục 6, bạn có thể kiểm tra các quan sát có thể xác minh:

- GET /api/ping thành công.
- Response có header X-Trace-Id.
- JSON có message: pong và có traceId.
- Giá trị traceId trong response header và body giống nhau trong cùng request.

### Test tích hợp Spring Boot

Thêm **spring-boot-starter-test** (test scope) vào project, và sử dụng WebTestClient do Spring Boot auto-configure trong test. Ví dụ với Spring Boot 3.x:

~~~java
package com.example.exchange;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void pingHasTraceId() {
        EntityExchangeResult<byte[]> result = client.get()
            .uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Trace-Id")
            .expectBody()
            .jsonPath("$.message").isEqualTo("pong")
            .jsonPath("$.traceId").exists()
            .returnResult();

        String header = result.getResponseHeaders()
            .getFirst("X-Trace-Id");

        assertThat(header).isNotBlank();
        assertThat(new String(
            result.getResponseBody(), StandardCharsets.UTF_8
        )).contains(header);
    }
}
~~~

Test xác nhận behavior xuyên suốt HTTP request. JSON serialization của Map và UUID có thể được framework thực hiện mà không cần caller dùng block(). Ví dụ dùng assertThat để kiểm tra UUID header xuất hiện trong body JSON, không dựa vào UUID cố định.

Khi nâng lên Spring Boot 4.x, các package annotation test auto-configuration có thể thay đổi; hãy dùng import phù hợp với version đang chạy. Nếu chỉ muốn kiểm tra logic của một WebFilter, có thể dùng WebTestClient được bind với controller/router và filter thay vì khởi động toàn bộ HTTP server.

### Test lỗi và cancellation

Ngoài nhánh thành công, nên thêm:

- Request không có route: status 404.
- Request sai method: status 405 khi route khác method.
- Request body JSON không hợp lệ: lỗi client phù hợp với codec/validation.
- WebFilter short-circuit: controller không được gọi.
- Response đã commit rồi phát lỗi: không mong framework đổi status đã gửi.
- Streaming client cancel: upstream nhận cancellation khi điều kiện vận hành cho phép; test cần được thiết kế phù hợp với transport, không coi timing là tuyệt đối.

## 16. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Gọi block() trong WebFilter hoặc controller | Giữ event-loop thread và có thể vi phạm hợp đồng non-blocking | Nối Mono/Flux bằng operator, trả Publisher cho WebFlux. |
| Gọi subscribe() thủ công để “chạy” request | Công việc thoát khỏi subscription/lifecycle HTTP | Trả chain.filter(exchange) hoặc Publisher đúng contract. |
| Dùng exchange attributes như global cache | Rò rỉ trạng thái/request giữa các lần truy cập | Chỉ dùng cho metadata request, không giữ exchange ở singleton field. |
| Giả định getSession() đồng nghĩa tạo session persistent | Phát sinh hiểu sai về state và cookie | Phân biệt lấy WebSession với lưu thay đổi session. |
| Đọc getBody() từ filter rồi cho handler đọc lại | Body có thể bị tiêu thụ, gây lỗi decode | Thiết kế decorator/cache an toàn, giới hạn kích thước. |
| Thay header/status sau response commit | Thay đổi không còn hiệu lực như dự kiến | Đặt trước chain hoặc dùng beforeCommit phù hợp. |
| Bắt mọi lỗi rồi luôn trả HTTP 200 | Client hiểu sai kết quả API | Ánh xạ lỗi sang status thích hợp. |
| Dùng ThreadLocal làm request context bền vững | Dữ liệu mất hoặc sai khi pipeline đổi thread | Dùng Reactor Context hoặc exchange attributes theo mục đích. |
| Tự tạo cơ chế auth từ header chưa tin cậy | Rủi ro bypass/giả mạo | Dùng Spring Security và xử lý trust boundary. |
| Log toàn bộ body/token trong filter | Rủi ro lộ dữ liệu, tốn bộ nhớ | Ghi log metadata cần thiết, ẩn dữ liệu nhạy cảm. |
| Giả định CANCEL luôn rollback công việc | Side effect đã xảy ra có thể còn nguyên | Thiết kế idempotency, transaction và hủy tác vụ theo lớp. |
| Đồng nhất WebFilter với WebClient filter | Áp dụng sai API/lifecycle | Phân biệt server-side WebFilter và client-side ExchangeFilterFunction. |

## 17. Bài tập tự kiểm tra

**1.** ServerWebExchange đại diện cho TCP connection hay một HTTP exchange?  
**2.** WebFilter phải trả kiểu nào và tại sao không nên gọi subscribe() thủ công?  
**3.** Một filter muốn truyền correlation ID sang controller: nên dùng exchange attributes hay đặt nó trong một singleton field?  
**4.** getSession() trả về kiểu gì và có luôn tạo session persistent không?  
**5.** Một filter thay status code sau khi response đã commit có đảm bảo hoạt động không?  
**6.** Vì sao đọc request.getBody() để log rồi chuyển tiếp nguyên exchange có thể làm handler decode JSON thất bại?  
**7.** DispatcherHandler dùng những loại delegate nào để tìm handler, gọi handler và tạo response?  
**8.** Khi một Flux streaming đã phát một phần body rồi gặp lỗi, HTTP status đã gửi có thể đổi sang 500 không?  
**9.** exchange attributes khác Reactor Context như thế nào?  
**10.** CANCEL có bảo đảm rollback một lần ghi database đã commit không?

### Đáp án gợi ý

1. Một HTTP exchange/request; connection có thể được tái sử dụng.
2. Mono<Void>; Spring WebFlux subscribe và điều phối completion/error/cancellation cho request.
3. Dùng attributes gắn request; không lưu request state ở singleton field.
4. Mono<WebSession>; chỉ lấy session không tự động tạo session persistent có trạng thái.
5. Không; trạng thái commit ngăn việc thay status/header như trước khi gửi response.
6. Body là reactive stream và có thể đã bị tiêu thụ; muốn đọc lại phải thiết kế cache/decorate đúng.
7. HandlerMapping, HandlerAdapter và HandlerResultHandler.
8. Không thể rút lại headers đã gửi; cần xử lý lỗi theo giao thức streaming hoặc kết thúc luồng.
9. Attributes là map theo HTTP exchange; Reactor Context gắn với reactive subscription.
10. Không; cancellation không tự hoàn tác side effect đã xảy ra.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HttpHandler, WebHandler API, WebHttpHandlerBuilder, WebFilter và WebExceptionHandler.
- [Spring Framework — DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): front controller reactive, HandlerMapping, HandlerAdapter và result handling.
- [Spring Framework — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): contract, request/response, attributes, session, principal và mutate.
- [Spring Framework — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html): filter contract và Mono<Void>.
- [Spring Framework — ServerHttpResponse Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): status, headers và commit.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): mapping, argument binding và return types.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP request/response WebFlux.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/index.html): Mono, Flux, subscription, backpressure, cancellation và Reactor Context.
