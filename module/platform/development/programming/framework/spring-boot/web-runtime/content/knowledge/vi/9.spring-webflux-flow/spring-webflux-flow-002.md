# DispatcherHandler, HandlerMapping và HandlerAdapter trong Spring WebFlux

## 1. Bài toán: một HTTP request đi đến đúng handler như thế nào?

Trong Spring WebFlux, controller hoặc functional endpoint không trực tiếp nhận socket TCP và cũng không tự quyết định URL nào được chuyển đến mình. Spring WebFlux có một cơ chế dispatch thống nhất để nhận request đã được HTTP server chuyển thành đối tượng trừu tượng của framework, tìm handler phù hợp, gọi handler và ghi kết quả thành HTTP response.

Ba thành phần cốt lõi của bài học:

- **DispatcherHandler**: front controller của Spring WebFlux, đóng vai trò trung tâm điều phối.
- **HandlerMapping**: tìm một handler thích hợp với request đang đến (dựa trên URL, HTTP method, media type hoặc quy tắc tương ứng).
- **HandlerAdapter**: biết cách thực thi đúng loại handler đã tìm được và trả về một HandlerResult trong trường hợp cần xử lý kết quả.

Sau ba bước này còn một thành phần quan trọng là **HandlerResultHandler**. Nó chuyển giá trị được handler trả về thành nội dung/headers/status của response, chẳng hạn serialize JSON hoặc ghi dòng dữ liệu. Nếu bỏ qua HandlerResultHandler, sẽ khó hiểu vì sao việc tìm và gọi controller chưa phải bước cuối của luồng HTTP.

Một request điển hình:

~~~text
Client
  |
  v
HTTP server (Reactor Netty / container được hỗ trợ)
  |
  v
HttpHandler / HttpWebHandlerAdapter
  |
  v
WebFilter chain; các WebExceptionHandler ở đường xử lý lỗi
  |
  v
DispatcherHandler (WebHandler)
  |
  +-- HandlerMapping #1 ----\
  +-- HandlerMapping #2 -----+--> chọn handler đầu tiên phù hợp
  +-- HandlerMapping #N ----/
  |
  v
HandlerAdapter phù hợp với loại handler
  |
  v
HandlerResult (giá trị + metadata xử lý)
  |
  v
HandlerResultHandler phù hợp
  |
  v
HTTP response: status + headers + body
~~~

Sơ đồ này mô tả đường xử lý logic, không khẳng định toàn bộ các thao tác diễn ra đồng bộ trên một thread. Spring WebFlux được xây dựng trên Reactive Streams: các bước xử lý thường tạo và kết hợp Publisher, sau đó được thực thi khi có subscription từ runtime HTTP; quá trình I/O và callback có thể được lập lịch trên những thread khác nhau theo server, scheduler và các operator mà ứng dụng sử dụng.

## 2. Bốn ranh giới cần nhớ

Không nên nhầm Spring WebFlux với Spring MVC chỉ vì cả hai hỗ trợ @RestController và @GetMapping.

| Tầng | Spring WebFlux | Spring MVC |
|---|---|---|
| Front controller | DispatcherHandler | DispatcherServlet |
| Hợp đồng xử lý request trung tâm | WebHandler / Mono<Void> | HttpServlet / Servlet API |
| Ngữ cảnh request/response | ServerWebExchange; ServerHttpRequest/Response | HttpServletRequest/Response |
| Cơ chế tích hợp HTTP server | HttpHandler và adapter của server | Servlet container và Servlet registration |
| Tìm annotated controller | RequestMappingHandlerMapping tương ứng WebFlux | RequestMappingHandlerMapping tương ứng MVC |
| Gọi annotated handler | WebFlux RequestMappingHandlerAdapter | MVC RequestMappingHandlerAdapter |
| Kiểu return phổ biến | Mono<T>, Flux<T>, ResponseEntity<T>, ServerResponse | T, ResponseEntity<T>, ModelAndView, async types |
| Functional routing | RouterFunctionMapping và HandlerFunctionAdapter | Có functional routing riêng của Spring MVC |
| Xử lý kết quả | HandlerResultHandler | HandlerAdapter kết hợp return-value handling MVC |
| Filter đặc trưng | WebFilter | Servlet Filter |
| Reactive error handling | WebExceptionHandler và cơ chế exception của handler | HandlerExceptionResolver và Servlet error handling |

Hai framework có nhiều API cùng tên nhưng thuộc package khác nhau. Ví dụ RequestMappingHandlerAdapter của WebFlux không phải cùng lớp với RequestMappingHandlerAdapter của Spring MVC. Khi đọc stack trace hoặc viết cấu hình, phải phân biệt tên package.

**Không tồn tại việc DispatcherHandler tự biến thành DispatcherServlet** khi thêm WebClient. WebClient chỉ là HTTP client có API reactive và có thể được dùng ngay trong một ứng dụng Spring MVC. Ngược lại, một ứng dụng Spring WebFlux reactive server sử dụng DispatcherHandler làm điểm dispatch trung tâm.

## 3. DispatcherHandler là gì?

DispatcherHandler là class trong package org.springframework.web.reactive. Nó triển khai WebHandler, nghĩa là nhận ServerWebExchange và trả về Mono<Void> biểu thị việc xử lý HTTP request/response đã hoàn tất theo hợp đồng reactive.

Phương thức khái niệm của WebHandler:

~~~java
Mono<Void> handle(ServerWebExchange exchange);
~~~

Trong đó:

- **ServerWebExchange** đại diện cho một lượt trao đổi HTTP, bao gồm request, response, attributes, thông tin session/principal và các thành phần liên quan. Không coi nó là một POJO được chia sẻ tự do qua request khác.
- **Mono<Void>** là Publisher báo hoàn thành hoặc lỗi của tác vụ xử lý; nó không mang đối tượng body để caller đọc trực tiếp. Body được ghi vào ServerHttpResponse trong quá trình xử lý.
- **DispatcherHandler** giữ vai trò điều phối, không phải nơi chứa logic nghiệp vụ, không trực tiếp thực thi SQL và không quyết định chính sách authentication thay cho WebFilter/Spring Security.

Một phiên bản đơn giản hóa của thuật toán dispatch:

~~~text
handle(exchange):
  tìm HandlerMapping trả về handler thích hợp
  nếu không có handler:
      tạo tín hiệu không tìm thấy đường xử lý (thường dẫn đến 404)
  chọn HandlerAdapter hỗ trợ handler vừa nhận
  adapter.handle(exchange, handler) -> Mono<HandlerResult>
  chọn HandlerResultHandler hỗ trợ HandlerResult
  resultHandler.handleResult(exchange, result) -> Mono<Void>
  hoàn tất hoặc chuyển exception sang đường xử lý lỗi
~~~

Thuật toán này dùng để hiểu kiến trúc, **không phải mã nguồn nguyên văn** của DispatcherHandler. Những chi tiết như xử lý result rỗng, exception handler gắn với kết quả, order và cách viết response cần tuân theo API/runtime thực tế.

### 3.1. Vì sao DispatcherHandler không cần biết mọi loại controller?

DispatcherHandler chỉ cần những giao diện chiến lược. Các HandlerMapping biết cách tìm handler, các HandlerAdapter biết cách gọi loại handler đó, và các HandlerResultHandler biết cách ghi kết quả. Nhờ vậy cùng một front controller có thể phục vụ:

- Annotated controllers dùng @RestController, @RequestMapping, @GetMapping.
- Functional endpoints dùng RouterFunction và HandlerFunction.
- Tài nguyên tĩnh thông qua resource handler.
- Các handler mở rộng do framework hoặc ứng dụng cung cấp.

Thêm một phương thức @GetMapping mới không yêu cầu sửa DispatcherHandler. Spring đăng ký metadata route trong một HandlerMapping được quản lý bởi ApplicationContext; DispatcherHandler chọn mapping/adapter phù hợp tại runtime.

### 3.2. DispatcherHandler được đăng ký khi nào?

Trong ứng dụng Spring Boot dùng spring-boot-starter-webflux và chạy ở chế độ reactive web application, Boot thiết lập hạ tầng Spring WebFlux. DispatcherHandler thường là WebHandler trung tâm trong ApplicationContext. WebHttpHandlerBuilder kết hợp WebHandler với các WebFilter và WebExceptionHandler, rồi HttpWebHandlerAdapter cung cấp khả năng tích hợp với HttpHandler của HTTP server.

Với Reactor Netty, adapter phía server chuyển các request/responses mức Netty sang hợp đồng HttpHandler của Spring. Các web server reactive khác cũng có adapter tương ứng. Không đăng ký DispatcherHandler bằng web.xml hay ServletRegistrationBean như DispatcherServlet của Spring MVC.

Trong trường hợp nâng cao, @EnableWebFlux cho phép nhận toàn quyền hơn với cấu hình WebFlux; ứng dụng Spring Boot thông thường **không cần** tự thêm @EnableWebFlux. Nếu chỉ muốn mở rộng CORS, formatters hay resource handling, WebFluxConfigurer thường phù hợp hơn và giữ được phần lớn cấu hình tự động của Boot.

## 4. HandlerMapping: tìm handler nào sẽ xử lý request?

HandlerMapping trong WebFlux cung cấp hợp đồng đại ý:

~~~java
Mono<Object> getHandler(ServerWebExchange exchange);
~~~

Khi một mapping không nhận diện được handler phù hợp, nó thường trả Mono.empty(), để DispatcherHandler xem các HandlerMapping khác theo thứ tự. Khi tìm được handler, nó trả Publisher phát ra handler. Một mapping cũng có thể tạo lỗi HTTP cụ thể, ví dụ điều kiện method/media type không đáp ứng, thay vì đơn giản nói “không có handler”.

Các HandlerMapping phổ biến:

| Loại | Điều gì được đăng ký? | Handler trả về |
|---|---|---|
| RequestMappingHandlerMapping | Controller method với @RequestMapping/@GetMapping/... | HandlerMethod, mang thông tin bean và method |
| RouterFunctionMapping | Các RouterFunction được khai báo như bean | HandlerFunction phù hợp request |
| Mapping cho tài nguyên tĩnh | Các resource handlers/path patterns | ResourceWebHandler hoặc handler tài nguyên phù hợp |
| Mapping do ứng dụng/thư viện bổ sung | Route/handler đặc thù | Tùy loại handler và adapter hỗ trợ |

Điểm quan trọng là **handler không nhất thiết là Controller**. Với annotation model, nó thường là HandlerMethod. Với functional routing, nó thường là HandlerFunction. HandlerAdapter được chọn dựa trên **kiểu handler được tìm thấy**, không chỉ dựa vào request path.

### 4.1. Spring biết @GetMapping từ đâu?

Khi ApplicationContext khởi động, WebFlux RequestMappingHandlerMapping khám phá các bean controller và phương thức có annotation mapping. Nó xây dựng thông tin route từ:

- HTTP method: GET, POST, PUT, DELETE...
- URL/path pattern.
- Điều kiện params và headers.
- Điều kiện consumes và produces.
- Các metadata mapping liên quan.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping("/{id}")
    Mono<String> get(@PathVariable long id) {
        return Mono.just("item-" + id);
    }
}
~~~

GET /api/items/42 có thể được mapping đến HandlerMethod của ItemController.get(...). Tomcat/Netty không hiểu @GetMapping; chính Spring WebFlux hạ tầng HandlerMapping phát hiện annotation và lựa chọn handler.

### 4.2. HandlerMapping nào được ưu tiên?

Spring có thể có nhiều bean HandlerMapping cùng lúc. Chúng thường được sắp xếp theo order và DispatcherHandler xét theo thứ tự cho đến khi có một handler phù hợp. Thứ tự rất quan trọng khi một path có thể khớp cả functional route, annotated route và static resource handler.

Không nên tự suy đoán rằng annotation controller luôn thắng functional route trong mọi cấu hình hoặc mọi phiên bản. Nếu đăng ký hai endpoint cùng path+method theo hai mô hình khác nhau, phải kiểm tra mapping order/runtime, và tốt nhất tránh thiết kế route trùng nhau.

Thứ tự của các HandlerMapping và các HandlerResultHandler là hai khái niệm riêng: một bên quyết định **ai xử lý request**, bên kia quyết định **ai ghi kết quả đã xử lý**.

### 4.3. 404 không phải lúc nào cũng do thiếu Controller

Nếu không có HandlerMapping phù hợp, request thường dẫn đến 404 Not Found. Nhưng 404 cũng có thể do handler nghiệp vụ tự trả Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)), do resource handler không tìm thấy tệp, hoặc do gateway/proxy đã thay đường dẫn.

Vì vậy khi gặp 404, cần kiểm tra URL thực sự đi vào Spring, HTTP method, media type, handler đã được đăng ký, và có route khác hoặc static handler nhận request không. Đừng vội kết luận DispatcherHandler chưa được khởi tạo.

## 5. HandlerAdapter: thực thi handler đã được chọn

Sau khi HandlerMapping trả về handler, DispatcherHandler tìm một HandlerAdapter hỗ trợ handler đó. Giao diện cốt lõi được diễn đạt đơn giản:

~~~java
boolean supports(Object handler);

Mono<HandlerResult> handle(ServerWebExchange exchange, Object handler);
~~~

supports(...) xác định adapter có thể xử lý kiểu handler hay không. handle(...) gọi handler thông qua cơ chế tương ứng rồi trả một HandlerResult để các bước tiếp theo quyết định cách ghi response.

Các adapter thường gặp:

- **RequestMappingHandlerAdapter**: thực thi HandlerMethod của annotated controller. Nó sử dụng các argument resolvers, reactive type adapters, validation/binding khi phù hợp và các return-value mechanisms của WebFlux.
- **HandlerFunctionAdapter**: thực thi HandlerFunction được RouterFunctionMapping chọn, nhận ServerRequest tương ứng rồi tạo Publisher cho kết quả chức năng.
- **SimpleHandlerAdapter**: hỗ trợ các handler phù hợp hợp đồng WebHandler trong những trường hợp được framework hỗ trợ.

Không chọn adapter dựa trên việc tên class có chữ Controller hay không; chọn dựa trên supports(handler). Nếu ứng dụng thêm một loại handler đặc thù nhưng không có HandlerAdapter nào hỗ trợ, DispatcherHandler không thể thực thi loại handler ấy theo hợp đồng mong đợi.

### 5.1. Annotated handler được gọi như thế nào?

Khi adapter xử lý một HandlerMethod, nó cần giải quyết các tham số của Java method:

- @PathVariable lấy giá trị từ path variables.
- @RequestParam lấy query parameters theo cấu hình.
- @RequestHeader đọc header tương ứng.
- @RequestBody kết hợp codec/body readers để giải mã HTTP body.
- ServerWebExchange, ServerHttpRequest, Principal và những kiểu tham số hỗ trợ khác được resolver tương ứng cung cấp.
- Khi dùng @Valid và Bean Validation phù hợp, có thể có bước validation sau khi bind dữ liệu.

Bên dưới còn các cơ chế reflection/invocation, conversion, validation, error handling và reactive type adaptation. Controller có thể trả Mono<T>, Flux<T>, ResponseEntity<T> hoặc những kiểu return value khác được WebFlux hỗ trợ.

Ví dụ method:

~~~java
@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<ResponseEntity<OrderView>> create(
        @RequestBody Mono<CreateOrder> body) {

    return body.map(req ->
            ResponseEntity.status(HttpStatus.CREATED)
                    .body(new OrderView(100L, req.item())));
}
~~~

Đây là một method minh họa, không phải class độc lập; cần đặt trong annotated controller và định nghĩa hai record CreateOrder/OrderView. Adapter giải mã body thành Mono<CreateOrder>, cung cấp nó cho controller rồi nhận Mono<ResponseEntity<OrderView>>. Việc ghi JSON và mã 201 thuộc bước xử lý kết quả, không phải việc HandlerMapping làm.

### 5.2. Functional handler được gọi như thế nào?

Với functional endpoints, RouterFunction định nghĩa một tập route theo các RequestPredicate. Khi RouterFunctionMapping tìm thấy route phù hợp, HandlerFunctionAdapter gọi HandlerFunction với ServerRequest.

Mẫu tổng quát:

~~~java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok().bodyValue("hello");
~~~

Đây là đoạn trích dùng kiểu org.springframework.web.reactive.function.server.HandlerFunction và ServerResponse; cần đặt trong Java class và có import. Kết quả functional handler là Mono<ServerResponse>; quá trình ghi response do những thành phần chuyên biệt của WebFlux đảm nhiệm.

Functional handler không phải một @RestController trá hình. RouterFunctionMapping không cần @GetMapping; nó đánh giá route predicates và chuyển request sang HandlerFunction. Tuy nhiên hai mô hình cùng tham gia vào pipeline DispatcherHandler tổng quát.

## 6. HandlerResult và HandlerResultHandler: bước còn thiếu để có HTTP response

Nếu chỉ học DispatcherHandler + HandlerMapping + HandlerAdapter, ta sẽ bỏ sót câu hỏi: “Giá trị mà controller trả về được serialize và ghi ra socket bởi ai?”

**HandlerResult** chứa kết quả handler invocation và metadata cần thiết cho result handling, chẳng hạn return value và loại dữ liệu. **HandlerResultHandler** biết cách diễn giải một dạng kết quả nhất định rồi ghi ra ServerHttpResponse.

Các result handlers thường gặp:

| HandlerResultHandler | Tình huống điển hình | Kết quả |
|---|---|---|
| ResponseBodyResultHandler | @ResponseBody hoặc @RestController | Serialize body bằng HttpMessageWriter phù hợp |
| ResponseEntityResultHandler | ResponseEntity, HttpEntity và các reactive wrapper được hỗ trợ | Thiết lập status/headers rồi ghi body |
| ServerResponseResultHandler | Functional endpoint trả ServerResponse | Ghi ServerResponse theo hợp đồng functional model |
| ViewResolutionResultHandler | Controller trả view/model | Chọn View phù hợp và render response |

Không phải mọi handler trả về giá trị theo cùng một kiểu. Ví dụ một annotated controller có thể trả Mono<Book>, trong khi functional handler trả Mono<ServerResponse>. Adapter của hai handler khác nhau; result handler phù hợp cũng khác.

### 6.1. Có Mono rồi thì ai subscribe?

Controller chỉ tạo và trả Publisher; việc tạo Mono/Flux không tự động thực hiện tất cả I/O. Spring WebFlux và HTTP runtime phối hợp để subscribe vào pipeline, yêu cầu dữ liệu theo Reactive Streams và hoàn tất ghi response.

Ví dụ:

~~~java
@GetMapping("/answer")
Mono<Integer> answer() {
    return Mono.fromSupplier(() -> 42);
}
~~~

Trong một controller WebFlux hợp lệ, supplier chạy khi Publisher được subscribe theo cơ chế reactive, không nhất thiết ngay tại thời điểm Java method tạo Mono. Không gọi .subscribe() thủ công trong controller để ép kết quả đi ra ngoài HTTP response; nếu làm vậy, bạn có thể tạo một công việc tách khỏi vòng đời request, gây khó xử lý lỗi, cancellation và backpressure.

### 6.2. Flux là response body có thể chứa nhiều phần tử

Nếu controller trả Flux<Book>, WebFlux có thể dùng JSON writer để encode body; định dạng cụ thể phụ thuộc Content-Type, codec và kiểu dữ liệu. Với application/json, nhiều phần tử thường được biểu diễn theo cấu trúc JSON phù hợp. Với text/event-stream hoặc application/x-ndjson, body có thể được gửi thành dòng dữ liệu khi codec/handler hỗ trợ.

Không kết luận “trả Flux thì mỗi phần tử chắc chắn được gửi ngay lập tức”. Buffering ở codec, HTTP stack, reverse proxy và client còn ảnh hưởng thời điểm nhận dữ liệu. Cần chọn media type và test streaming thực tế.

## 7. Ví dụ hoàn chỉnh: annotated WebFlux controller

Giả sử project Spring Boot 3.x sử dụng Java 17+, Gradle, Maven Central và Spring Boot Gradle plugin đã được cấu hình. Dependency cơ bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Tùy phiên bản project, starter test có thể đã mang đủ thư viện kiểm thử cần thiết; khai báo reactor-test trực tiếp giúp những ví dụ dùng StepVerifier có dependency rõ ràng. Ví dụ chủ động không thêm spring-boot-starter-web để tránh vô tình chuyển ứng dụng sang Servlet MVC.

Tạo src/main/java/dev/example/webflux/WebFluxFlowApplication.java:

~~~java
package dev.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxFlowApplication.class, args);
    }
}
~~~

Tạo src/main/java/dev/example/webflux/BookController.java:

~~~java
package dev.example.webflux;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {

    public record BookView(long id, String title) {}

    public record CreateBook(String title) {}

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<BookView> find(@PathVariable long id) {
        if (id <= 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "id must be positive"));
        }
        return Mono.just(new BookView(id, "WebFlux Handbook"));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<BookView>> create(
            @RequestBody Mono<CreateBook> body) {

        return body.map(input -> ResponseEntity
                .status(HttpStatus.CREATED)
                .body(new BookView(101L, input.title())));
    }
}
~~~

Đây là hai file Java độc lập về cú pháp trong một project Spring Boot WebFlux. Hai record là kiểu dữ liệu minh họa, không thực hiện truy vấn database hay ghi dữ liệu thật. @RestController được component scan phát hiện vì nằm cùng package với class @SpringBootApplication.

Tạo src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Chạy ứng dụng bằng Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng .\gradlew.bat bootRun. Kiểm tra GET:

~~~bash
curl -i http://localhost:8080/api/books/7
~~~

Kết quả chính cần thấy: HTTP 200 và JSON body:

~~~json
{"id":7,"title":"WebFlux Handbook"}
~~~

Kiểm tra POST:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Reactive Systems"}'
~~~

Lệnh nối dòng như trên dành cho shell Unix; trên Windows có thể dùng curl.exe với một dòng. Kết quả chính là HTTP 201 và JSON body:

~~~json
{"id":101,"title":"Reactive Systems"}
~~~

Các header như Date/Content-Length/Transfer-Encoding có thể khác nhau theo server, codec và thời điểm chạy; không coi toàn bộ header là output cố định.

### 7.1. Truy vết GET qua ba thành phần

Đối với GET /api/books/7:

1. HTTP runtime nhận request và tạo ServerWebExchange.
2. WebFilter chain xử lý những bước chung, nếu có.
3. DispatcherHandler yêu cầu các HandlerMapping tìm handler.
4. RequestMappingHandlerMapping xác định BookController.find(...), với path variable id=7.
5. DispatcherHandler chọn RequestMappingHandlerAdapter để thực thi HandlerMethod.
6. Adapter dùng argument resolver chuyển path segment "7" thành long 7 rồi gọi controller.
7. Controller trả Mono<BookView>; adapter tạo HandlerResult phù hợp.
8. ResponseBodyResultHandler ghi JSON body từ BookView bằng writer/codec có trên classpath.
9. Reactive pipeline hoàn tất, runtime gửi response cho client.

Nếu id không hợp lệ theo logic controller, Mono.error(ResponseStatusException) tạo đường xử lý lỗi và phản hồi HTTP 400 khi còn có thể thiết lập status. Luồng phản hồi lỗi khác với luồng kết quả bình thường nhưng vẫn thuộc cơ chế WebFlux.

### 7.2. Truy vết POST và body reactive

Đối với POST /api/books với JSON:

1. HandlerMapping xác định route POST và điều kiện consumes/produces.
2. RequestMappingHandlerAdapter sử dụng reader/codec để cung cấp @RequestBody Mono<CreateBook>.
3. Controller trả Mono<ResponseEntity<BookView>> được tạo từ việc map body.
4. ResponseEntityResultHandler nhận response entity sau khi Publisher phát kết quả.
5. Status 201 được áp dụng, BookView được serialize thành JSON và response hoàn tất.

Không dùng .block() trong controller để lấy CreateBook từ Mono; code viết reactive theo cách kết hợp Publisher và trả lại cho framework.

## 8. Ví dụ hoàn chỉnh: functional routing trên cùng DispatcherHandler

Bên cạnh annotated controllers, Spring WebFlux có functional endpoint API. Để chứng minh HandlerMapping/HandlerAdapter có thể thay đổi theo loại handler, tạo file src/main/java/dev/example/webflux/FunctionalRoutes.java:

~~~java
package dev.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    public record Message(String text) {}

    @Bean
    RouterFunction<ServerResponse> helloRoute() {
        return route(GET("/functional/hello"), request ->
                ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new Message("Hello functional WebFlux")));
    }
}
~~~

Lớp cấu hình được Spring Boot component scan phát hiện. Bean RouterFunction<ServerResponse> định nghĩa route GET /functional/hello.

Chạy cùng ứng dụng ở mục 7 rồi kiểm tra:

~~~bash
curl -i http://localhost:8080/functional/hello
~~~

Body dự kiến:

~~~json
{"text":"Hello functional WebFlux"}
~~~

Tại đây:

1. DispatcherHandler vẫn là front controller.
2. RouterFunctionMapping tìm route có RequestPredicate GET("/functional/hello") phù hợp.
3. HandlerFunctionAdapter gọi HandlerFunction với ServerRequest.
4. HandlerFunction trả Mono<ServerResponse>.
5. ServerResponseResultHandler ghi HTTP status, headers và JSON body.

Hai mô hình REST annotations và functional routing có thể cùng tồn tại trong một ứng dụng Spring WebFlux. Chúng không yêu cầu hai DispatcherHandler hoặc hai cổng HTTP.

### 8.1. Functional predicate có thể phức tạp hơn GET path

Các RequestPredicate có thể phối hợp HTTP method, path, headers, content type và thông tin request. Với functional API, một route nhận JSON có thể khai báo POST, yêu cầu content type và đọc body qua request.bodyToMono(...). Functional endpoint xử lý request theo ServerRequest và ServerResponse; annotated endpoint dùng các argument resolvers/return handlers riêng.

Không nên giả định toàn bộ exception handling của annotated @ControllerAdvice tự bao phủ mọi functional handler theo cùng cách. Với functional routes, thường cần các phép biến đổi reactive, error handling ở functional handler hoặc cơ chế WebExceptionHandler toàn cục được thiết kế tương thích.

### 8.2. Trùng route giữa annotation và functional model

Nếu cả BookController và một RouterFunction đều khai báo GET /api/books/7, runtime chọn theo thứ tự các HandlerMapping và điều kiện của chúng, không phải theo thứ tự file Java. Tránh tạo route trùng trong production. Nếu bắt buộc có nhiều chiến lược, xác nhận HandlerMapping order và test request thật để không lộ hành vi bất ngờ sau nâng cấp.

## 9. HandlerResultHandler khác HandlerAdapter như thế nào?

Đây là câu hỏi quan trọng thường gây nhầm khi đọc debug log.

**HandlerAdapter** giải quyết “làm sao **gọi** handler này?”  
**HandlerResultHandler** giải quyết “làm sao **ghi kết quả** được handler này trả về?”

Bảng minh họa:

| Handler được chọn | Adapter tương ứng | Return value | Result handler thường dùng |
|---|---|---|---|
| Annotated HandlerMethod GET /books | RequestMappingHandlerAdapter | Mono<BookView> với @ResponseBody | ResponseBodyResultHandler |
| Annotated HandlerMethod POST /books | RequestMappingHandlerAdapter | Mono<ResponseEntity<BookView>> | ResponseEntityResultHandler |
| Functional HandlerFunction | HandlerFunctionAdapter | Mono<ServerResponse> | ServerResponseResultHandler |
| Annotated controller trả view | RequestMappingHandlerAdapter | Model/view theo hợp đồng WebFlux | ViewResolutionResultHandler |

Không đưa logic serialize JSON vào HandlerMapping. Không đưa logic chọn controller theo URL vào HandlerResultHandler. Mỗi interface có một nhiệm vụ giúp hệ thống mở rộng và kiểm thử dễ hơn.

### 9.1. Header và status được đặt tại đâu?

Trong annotated WebFlux, ResponseEntity có thể kiểm soát status và headers, còn @ResponseStatus có thể cung cấp status theo metadata handler. Kết quả như Mono<ResponseEntity<T>> được framework giải thích trước khi ghi response.

Trong functional WebFlux, ServerResponse.ok(), ServerResponse.status(...), contentType(...) và các API tương ứng mô tả HTTP response. Trách nhiệm thực thi và ghi dữ liệu thuộc tầng xử lý ServerResponse.

HTTP status không được quyết định duy nhất bởi HandlerMapping: một handler có thể được chọn thành công nhưng trả 404 do không tìm thấy entity, trả 400 do validation, hoặc trả 503 do backend không sẵn sàng.

## 10. Lỗi, WebExceptionHandler và @RestControllerAdvice

Reactive pipeline có thể phát sinh lỗi ở nhiều nơi: WebFilter, HandlerMapping, argument binding, handler logic, codec hay giai đoạn ghi response. Đường xử lý lỗi phụ thuộc vị trí lỗi và trạng thái response.

Các cách thường dùng:

- **ResponseStatusException**: biểu thị HTTP status có chủ đích từ handler hoặc một tầng phù hợp.
- **@ExceptionHandler / @RestControllerAdvice**: hỗ trợ xử lý exception của annotated WebFlux controller theo cấu hình tương ứng.
- **WebExceptionHandler**: xử lý lỗi ở phạm vi WebHandler chain, có thể áp dụng rộng hơn một annotated controller cụ thể.
- **Reactive operators** như onErrorResume, onErrorMap, timeout: điều chỉnh lỗi theo từng reactive flow.
- **Spring Boot error handling**: tích hợp trả response lỗi theo ngữ nghĩa HTTP và nội dung cấu hình.

Ví dụ handler trả lỗi khi id không hợp lệ ở phần 7. Nếu muốn chuẩn hóa lỗi cho annotated API, có thể tạo một advice:

~~~java
package dev.example.webflux;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(IllegalArgumentException.class)
    public Mono<ResponseEntity<ApiError>> onBadInput(
            IllegalArgumentException error) {

        return Mono.just(ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(new ApiError("INVALID_INPUT", error.getMessage())));
    }
}
~~~

Lớp trên minh họa cách xử lý IllegalArgumentException trong annotated request processing. Không giả định nó sẽ xử lý mọi lỗi Netty, lỗi xảy ra trước DispatcherHandler hoặc exception do functional HandlerFunction phát ra. Với những đường này, cần thiết kế error handling theo phạm vi phù hợp.

**Cẩn trọng khi response đã committed.** Nếu Flux đang stream body và phía server đã gửi headers/bytes, một lỗi muộn có thể không còn cho phép đổi HTTP status thành 500. Khi đó cần quản lý stream termination, logging, client retry và cơ chế dữ liệu để bảo toàn ngữ nghĩa nghiệp vụ.

## 11. WebFilter khác HandlerInterceptor và Servlet Filter

Spring WebFlux sử dụng WebFilter để chặn/điều chỉnh dòng HTTP ở tầng WebHandler trước khi dispatch. Trong Servlet MVC, Servlet Filter thuộc jakarta.servlet và HandlerInterceptor nằm trong MVC handler chain. WebFlux không vận hành như một Servlet Filter chain mặc định trên Reactor Netty.

Ví dụ WebFilter đơn giản bổ sung header response:

~~~java
package dev.example.webflux;

import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class DemoResponseHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .add("X-App-Pipeline", "webflux");

        return chain.filter(exchange);
    }
}
~~~

Trong demo, filter được Spring đăng ký tự động vì @Component. Header được thêm trước khi chain tiếp tục xử lý; đây là minh họa, không phải chính sách bảo mật hoặc cơ chế trace đầy đủ. Nếu cần header phụ thuộc vào kết quả và trạng thái response, phải cân nhắc thời điểm commit hoặc dùng beforeCommit phù hợp.

Spring Security reactive server sử dụng WebFilter chain và SecurityWebFilterChain với các API dành cho WebFlux, không phải SecurityFilterChain của Servlet/MVC. Dùng nhầm loại filter hoặc cấu hình security có thể làm mọi request bị chặn hoặc khiến quy tắc bảo mật không chạy như dự kiến.

### 11.1. Tránh tạo side effect bên ngoài Publisher

Trong phương thức WebFilter/handler, nếu tự subscribe vào một Publisher để chạy việc phụ, request có thể hoàn thành trước khi side effect kết thúc, lỗi không truyền về HTTP pipeline và cancellation không còn kiểm soát được. Thay vào đó, thường nên chain publishers với then, flatMap, doOn... theo mục đích rõ ràng hoặc chuyển side effect sang một hệ thống xử lý nền có quản trị.

## 12. Threading, blocking và Reactive Streams

WebFlux hỗ trợ non-blocking HTTP handling, nhưng **không tự biến mọi dependency thành non-blocking**. Khi gọi JDBC, filesystem blocking hoặc SDK chờ mạng trực tiếp trên event-loop thread, ứng dụng có thể gây chậm tất cả request dùng chung event loop.

Điều cần nhớ:

- Reactor Netty thường sử dụng số lượng event-loop threads hữu hạn để xử lý nhiều kết nối.
- Mono và Flux là mô hình publisher; không có nghĩa mỗi request tạo một thread mới.
- map xử lý biến đổi nhanh/sync; flatMap thích hợp khi biến đổi trả publisher bất đồng bộ; concatMap giữ thứ tự tuần tự theo ngữ nghĩa Reactor.
- subscribeOn/publishOn thay đổi scheduler cho pipeline theo vị trí operator; không nên dùng bừa để “tăng concurrency”.
- Blocking I/O không biến mất chỉ vì được bọc bằng Mono.just(...). Hàm blocking bên trong Mono.just chạy ngay khi Java đánh giá biểu thức.
- BoundedElastic là lựa chọn chuyển tiếp có giới hạn dành cho blocking work khi chưa thể dùng reactive driver; cần giám sát queue/threads và deadline.

Ví dụ bọc một lời gọi blocking không thể thay thế ngay:

~~~java
Mono<LegacyResult> result = Mono
        .fromCallable(() -> legacyBlockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là đoạn trích minh họa: legacyBlockingClient, LegacyResult và import Reactor cần được định nghĩa trong project. Cách này **không biến dependency thành non-blocking**; nó chỉ tránh chiếm event loop trong thời gian blocking, đồng thời dùng tài nguyên worker của boundedElastic. Về dài hạn, nên ưu tiên WebClient, R2DBC hoặc driver tương thích reactive khi kiến trúc và nghiệp vụ cho phép.

Nếu phải xử lý nhiều phần tử, cần xét backpressure, cancellation, timeout và bộ nhớ. Một handler trả Flux vô hạn hoặc dữ liệu tốc độ cao mà không định nghĩa giới hạn có thể gây quá tải dù không block thread.

## 13. Khi nào WebFlux tự động tạo pipeline dispatch?

Một project Spring Boot WebFlux thông thường cần dependency phù hợp và có reactive server. Với spring-boot-starter-webflux, Boot thường dùng Reactor Netty làm embedded runtime mặc định. Trong quá trình startup, hạ tầng MVC annotations của WebFlux, functional routes và các WebFilter được cấu hình theo ApplicationContext.

Một số cấu hình đáng lưu ý:

~~~yaml
spring:
  main:
    web-application-type: reactive
  webflux:
    base-path: /service

server:
  port: 8080
~~~

**Cần phân biệt mục đích:** spring.main.web-application-type=reactive ép Boot chọn reactive web application khi cần; nhiều project chỉ có starter-webflux không cần ép. spring.webflux.base-path đặt base path theo cấu hình WebFlux tương ứng, ví dụ endpoint /api/books/7 có thể được truy cập qua /service/api/books/7. Không lấy server.servlet.context-path (thuộc Servlet MVC) để thay base-path reactive.

Khi vừa có spring-boot-starter-web vừa có starter-webflux, Spring Boot thông thường ưu tiên MVC Servlet stack nếu không override type. Không xác định web stack bằng việc thấy class Mono hoặc WebClient trong code. Hãy kiểm tra dependency tree, loại ApplicationContext và runtime server thực tế.

### 13.1. Có cần tự tạo DispatcherHandler bean?

Thông thường không. Nếu application đã chạy đúng WebFlux, framework sẽ thiết lập DispatcherHandler cùng các mapping/adapter/result handler thích hợp. Tự tạo một bean DispatcherHandler khác mà không hiểu cấu hình hạ tầng có thể gây thiếu chiến lược, xung đột bean hoặc thay đổi routing khó đoán.

Với nhu cầu thêm endpoint, chọn annotated controller hoặc RouterFunction. Với nhu cầu cấu hình CORS, codec, path matching, formatters hoặc resource handler, ưu tiên WebFluxConfigurer/customizer được hỗ trợ. Chỉ xây dựng custom HandlerMapping hoặc HandlerAdapter khi thật sự cần một kiểu handler không được framework hỗ trợ và đã có integration tests.

### 13.2. Khi nào dùng @EnableWebFlux?

@EnableWebFlux dùng để bật và kiểm soát cấu hình WebFlux framework khi cần quản lý nhiều khía cạnh thủ công. Trong Spring Boot, thêm annotation này có thể làm thay đổi mức độ auto-configuration/extension được Boot cung cấp. Đừng thêm chỉ để “kích hoạt DispatcherHandler” khi đã có starter-webflux.

Một ứng dụng có thể cần WebFluxConfigurer để tùy biến CORS hoặc codecs nhưng vẫn để Boot tự động cấu hình các phần khác. Chọn cách ít can thiệp nhất đáp ứng mục tiêu thực tế.

## 14. Kiểm thử HandlerMapping và HandlerAdapter với WebTestClient

Mock test chỉ gọi Java controller method trực tiếp không chứng minh route đã được đăng ký hoặc adapter hoạt động. Cần kiểm tra request đi qua WebFlux dispatch pipeline.

Với project mục 7, tạo src/test/java/dev/example/webflux/BookControllerTest.java:

~~~java
package dev.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = BookController.class)
class BookControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void findBookIsMapped() {
        client.get().uri("/api/books/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.title").isEqualTo("WebFlux Handbook");
    }

    @Test
    void invalidIdGetsBadRequest() {
        client.get().uri("/api/books/0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

@WebFluxTest khởi tạo tập con ApplicationContext phục vụ WebFlux controller testing thay vì mọi bean nghiệp vụ. Nếu controller cần service bean, dùng @MockBean hoặc cơ chế mock được phiên bản Boot hỗ trợ, hoặc cung cấp test configuration phù hợp. Trong ví dụ controller không có dependency service.

Đối với functional routes, có thể kiểm thử bằng WebTestClient được bind trực tiếp vào RouterFunction, hoặc chạy SpringBootTest integration và gọi GET /functional/hello. Khi muốn kiểm tra chính xác thứ tự HandlerMapping giữa annotation và functional model, chạy integration với cả hai loại route trong cùng ApplicationContext.

### 14.1. Integration test cần khi nào?

Nếu cần kiểm chứng HTTP server thật, WebFilter, TLS, Reactor Netty, proxy behavior hoặc lỗi phụ thuộc mạng, dùng @SpringBootTest(webEnvironment = RANDOM_PORT) với WebTestClient được gắn với server port thực tế. Một test slice không tái hiện mọi đặc tính của server/connector.

Các bài kiểm thử có giá trị:

1. GET /api/books/7 trả JSON 200 và được ánh xạ đến annotated controller.
2. POST /api/books nhận JSON body và trả JSON 201.
3. GET /functional/hello đi qua RouterFunctionMapping và HandlerFunctionAdapter.
4. Request sai HTTP method trả phản hồi phù hợp, thường 405 nếu path đúng mà method sai.
5. Request có Content-Type không đúng với consumes dẫn đến lỗi như 415.
6. Header Accept không tương thích với produces có thể dẫn đến 406.
7. Request không có route trả 404, phân biệt với resource handler fallback nếu có.
8. Invalid id phát ResponseStatusException và trả 400.
9. WebFilter bổ sung X-App-Pipeline vào response khi được đăng ký.
10. Trong môi trường test phù hợp, publisher bị cancel và lỗi streaming được quan sát đúng.

Kiểm thử không cần xác minh class nội bộ qua reflection nếu HTTP behavior đã rõ. Tuy nhiên khi debug một handler tùy chỉnh, có thể xem log hoặc bean types để xác nhận đúng mapping/adapter được chọn.

## 15. Quan sát và chẩn đoán pipeline

Cần phân biệt ba vấn đề riêng:

- **Request không được định tuyến:** mapping không tồn tại, base path sai, method/media type khác dự kiến, hoặc proxy rewrite URL.
- **Handler được chọn nhưng lỗi khi gọi:** argument conversion, body decoding, validation, service lỗi, blocking I/O hoặc exception trong Publisher.
- **Handler trả kết quả nhưng response lỗi:** result handler không hỗ trợ kiểu return, codec không hỗ trợ media type, response đã committed, client đóng kết nối hoặc lỗi encoding.

### 15.1. Logging có kiểm soát

Trong môi trường dev/test có thể tăng log:

~~~yaml
logging:
  level:
    org.springframework.web.reactive.DispatcherHandler: DEBUG
    org.springframework.web.reactive.result.method.annotation.RequestMappingHandlerMapping: TRACE
    org.springframework.web.reactive.function.server.support.RouterFunctionMapping: TRACE
~~~

Các category log và thông tin phát ra có thể thay đổi theo phiên bản; không phụ thuộc vào một chuỗi log cụ thể để xác nhận tất cả route. Mức TRACE có thể rất chi tiết, nên chỉ bật tạm thời và tránh ghi dữ liệu nhạy cảm.

### 15.2. Actuator mappings endpoint

Với dependency spring-boot-starter-actuator, có thể expose mappings ở môi trường kiểm thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,mappings
~~~

Sau đó gọi endpoint trên đúng cổng/đường quản trị:

~~~bash
curl -i http://localhost:8080/actuator/mappings
~~~

Đối với WebFlux, response thường chứa những thông tin về handler mappings; cấu trúc JSON cụ thể phụ thuộc phiên bản và cấu hình. Endpoint có thể lộ đường API nội bộ nên cần hạn chế truy cập bằng authentication/network policy hoặc chỉ bật ở môi trường phát triển.

Nếu management.server.port được cấu hình khác, /actuator/mappings có thể nằm trên port quản trị. Khi proxy hoặc Spring Security trả 401/403/404, kiểm tra cấu hình trước khi cho rằng DispatcherHandler không tồn tại.

### 15.3. Phân biệt 404, 405, 406, 415 và lỗi codec

| Kết quả | Nguyên nhân thường gặp | Việc cần kiểm tra |
|---|---|---|
| 404 Not Found | Không có handler/resource khớp hoặc handler chủ động báo không tìm thấy | Request path, base path, route registration, proxy rewrite |
| 405 Method Not Allowed | Path có mapping nhưng HTTP method sai | @GetMapping/@PostMapping, RequestPredicate |
| 406 Not Acceptable | Accept header không phù hợp kiểu response có thể tạo | produces, Accept, media type writers |
| 415 Unsupported Media Type | Content-Type của body không phù hợp | consumes, codecs, request body |
| 400 Bad Request | Binding/decoding/validation hoặc lỗi nghiệp vụ được quy về bad request | Path variables, query/body schema, lỗi codec |
| 500 Internal Server Error | Lỗi không được xử lý trong handler/pipeline | Stack trace, reactive error chain, response commit |
| Client timeout/connection closed | Lỗi mạng, server quá tải, thao tác blocking hoặc streaming/cancellation | Event loop, response time, downstream, reverse proxy |

Các mã này là tình huống điển hình, không phải kết quả bất biến của mọi cấu hình hoặc mọi API. Một request có thể bị WebFilter hoặc Spring Security chặn trước khi đến DispatcherHandler và trả 401/403 dù HandlerMapping đúng.

## 16. Tùy chỉnh WebFlux đúng tầng

Khi muốn thêm tính năng, hãy đặt logic ở tầng thích hợp:

| Mục tiêu | Điểm mở rộng thường phù hợp |
|---|---|
| Định nghĩa URL/HTTP method cho API | @RequestMapping annotations hoặc RouterFunction |
| Thêm CORS, formatters, custom codecs, static resources | WebFluxConfigurer hoặc cấu hình được Boot hỗ trợ |
| Xác thực/ủy quyền reactive | SecurityWebFilterChain và WebFlux security |
| Tracing/header chung mọi request | WebFilter, quan sát tracing/metrics tương ứng |
| Chuẩn hóa lỗi annotated controller | @RestControllerAdvice / @ExceptionHandler |
| Xử lý lỗi chung trước/sau handler | WebExceptionHandler hoặc error handling của Boot |
| Tùy biến serialize body | Codec/HttpMessageWriter thích hợp |
| Tùy biến cách chọn handler hoàn toàn mới | Custom HandlerMapping |
| Tùy biến cách thực thi một loại handler mới | Custom HandlerAdapter |
| Tùy biến cách ghi một kiểu HandlerResult | Custom HandlerResultHandler |

Không tự viết HandlerAdapter chỉ để “tối ưu tốc độ” cho một controller. Khi dùng @RestController, Spring đã cung cấp adapter được tối ưu và kiểm chứng. Tùy biến hạ tầng nên là lựa chọn sau khi API chuẩn không đáp ứng yêu cầu.

### 16.1. Vì sao extension phải đồng bộ ba phần?

Giả sử bạn viết một HandlerMapping trả về đối tượng MyHandler. Nếu không có HandlerAdapter với supports(MyHandler) phù hợp, dispatcher không thể gọi đối tượng đó. Nếu adapter trả HandlerResult có kiểu dữ liệu mà không HandlerResultHandler nào hỗ trợ, pipeline cũng không biết ghi response.

Do đó một kiểu handler hoàn toàn mới thường cần:

1. Quy tắc mapping (HandlerMapping).
2. Quy tắc invocation (HandlerAdapter).
3. Quy tắc representation của kết quả (dùng HandlerResultHandler hiện có hoặc tự bổ sung).
4. Quy tắc error, cancellation, ordering và observability.
5. Kiểm thử integration với các HandlerMapping/Adapter khác.

Không cần thực hiện toàn bộ công việc trên khi chỉ thêm một REST endpoint mới bằng annotation hoặc functional routing.

## 17. Những lỗi phổ biến cần tránh

**Lỗi 1 — Dùng DispatcherServlet và ServletRegistrationBean cho WebFlux reactive.**  
DispatcherServlet thuộc Spring MVC/Servlet. Spring WebFlux reactive front controller là DispatcherHandler và thường chạy qua HttpHandler adapter. Trước khi sửa “mapping”, xác nhận WebFlux hay MVC thật sự đang chạy.

**Lỗi 2 — Gọi .block() trong controller/WebFilter trên event loop.**  
Lệnh blocking có thể chặn event loop hoặc gây lỗi ở thread không cho phép blocking. Kết hợp Publisher bằng map/flatMap/zip; với dependency cũ bắt buộc blocking, offload có kiểm soát bằng boundedElastic hoặc chuyển sang driver reactive.

**Lỗi 3 — Tự gọi .subscribe() rồi trả Mono.empty().**  
Làm mất liên kết giữa side effect, response, lỗi và cancellation. Hãy trả Publisher mô tả toàn bộ công việc cần hoàn thành cho framework.

**Lỗi 4 — Chỉ thêm @GetMapping nhưng không có @RestController trong component scan.**  
ApplicationContext không tìm thấy handler method thì RequestMappingHandlerMapping không đăng ký route. Kiểm tra package của @SpringBootApplication, conditional bean và annotation controller.

**Lỗi 5 — Hiểu nhầm HandlerAdapter là đối tượng chọn URL.**  
HandlerMapping chọn handler; HandlerAdapter gọi handler. Hai tầng này xảy ra nối tiếp và xử lý những bài toán khác nhau.

**Lỗi 6 — Bỏ quên HandlerResultHandler.**  
Một handler có thể trả Mono<ResponseEntity<Book>>, nhưng response status/headers/body chỉ được hiện thực khi result handler phù hợp ghi nó vào HTTP response.

**Lỗi 7 — Lẫn RequestMappingHandlerAdapter WebFlux với MVC.**  
Tên lớp giống nhau nhưng package và hợp đồng khác. Khi import hoặc debug, xem package đầy đủ org.springframework.web.reactive... so với org.springframework.web.servlet....

**Lỗi 8 — Tưởng mọi Flux đều stream tức thời.**  
Định dạng HTTP body, codec, proxy buffering và client có thể gom dữ liệu. Khi cần streaming, dùng media type phù hợp như text/event-stream hoặc NDJSON, đồng thời test thời gian nhận dữ liệu.

**Lỗi 9 — Cho rằng WebFilter giống MVC HandlerInterceptor.**  
WebFilter bao quanh WebHandler exchange; HandlerInterceptor thuộc MVC Servlet stack. Không đặt bảo mật bắt buộc ở điểm mở rộng không chạy trong stack thực tế.

**Lỗi 10 — Cùng path được khai báo trong annotated và functional routes.**  
Thứ tự HandlerMapping có thể quyết định route nhận request. Thiết kế route duy nhất hoặc kiểm thử thứ tự cụ thể nếu bắt buộc chồng chéo.

**Lỗi 11 — Dùng server.servlet.context-path cho WebFlux.**  
Đó là Servlet property; với WebFlux reactive, dùng cấu hình base path phù hợp như spring.webflux.base-path và kiểm tra URL sau proxy.

**Lỗi 12 — Dùng @EnableWebFlux để sửa lỗi WebFlux starter.**  
Ứng dụng Boot có starter-webflux thường tự cấu hình hạ tầng. @EnableWebFlux có thể thay đổi auto-configuration, nên chỉ dùng khi chủ động nhận trách nhiệm cấu hình.

**Lỗi 13 — Tự đặt HTTP status khi response đã committed.**  
Một lỗi xảy ra sau khi streaming response bắt đầu có thể không còn đổi status được. Thiết kế protocol streaming, xác nhận thời điểm commit và xử lý lỗi phía client phù hợp.

## 18. Quy trình phân tích một request WebFlux thực tế

Khi một request GET /api/books/7 không trả kết quả mong đợi:

1. Xác nhận ứng dụng chạy **WebFlux reactive server**, không phải Spring MVC do cả hai starter cùng hiện diện.
2. Kiểm tra HTTP host/port, base path và đường request mà server nhận sau gateway/proxy.
3. Kiểm tra WebFilter/Spring Security: request có bị chặn trước dispatcher không?
4. Xác nhận DispatcherHandler được Boot cấu hình và handler mapping beans được đăng ký.
5. Xem RequestMappingHandlerMapping hoặc RouterFunctionMapping nào nhận request.
6. Kiểm tra route condition: path, method, headers, consumes, produces.
7. Nếu handler đã được chọn, xem HandlerAdapter nào supports(...) handler đó.
8. Nếu argument binding lỗi, kiểm tra @PathVariable/@RequestBody, JSON codec và validation.
9. Nếu handler trả Publisher, xác nhận pipeline không bị block, không tự subscribe tách nhánh, không bỏ quên return.
10. Xem HandlerResultHandler nào ghi status/headers/body.
11. Nếu response lỗi hoặc chậm, kiểm tra event loop, downstream, timeout, cancellation và trạng thái response đã committed.
12. Dùng WebTestClient/Actuator mappings/log có kiểm soát để kiểm thử và xác minh sau sửa.

Đừng chỉ đặt breakpoint ở controller và đoán mọi lỗi nằm trong nó. Với WebFlux, lỗi có thể xuất hiện trước khi handler được chọn hoặc trong phần thực thi Publisher sau khi controller method đã trả về.

## 19. Câu hỏi tự kiểm tra

**Câu 1. DispatcherHandler có phải Servlet không?**  
Không. DispatcherHandler thuộc Spring WebFlux và triển khai WebHandler; DispatcherServlet thuộc Spring MVC/Servlet stack.

**Câu 2. Vì sao cả @RestController và RouterFunction đều hoạt động?**  
Vì DispatcherHandler dùng nhiều HandlerMapping/HandlerAdapter: RequestMappingHandlerMapping + RequestMappingHandlerAdapter cho annotated handlers, RouterFunctionMapping + HandlerFunctionAdapter cho functional endpoints.

**Câu 3. HandlerMapping có serialize JSON không?**  
Không. Nó chọn handler. Serialize/ghi body thuộc result handling bằng HttpMessageWriter/codec và HandlerResultHandler phù hợp.

**Câu 4. HandlerAdapter quyết định status 201 hay 200 không?**  
Nó thực thi handler và trả kết quả phù hợp. Status có thể đến từ ResponseEntity, metadata hoặc ServerResponse, và được result handler áp dụng khi ghi response.

**Câu 5. Controller trả Mono<Book> là đã hoàn tất request chưa?**  
Chưa. Mono là Publisher mô tả một phép tính; runtime cần subscribe, tạo dữ liệu, encode/write body và hoàn tất reactive pipeline.

**Câu 6. Vì sao dùng Mono.just(blockingCall()) vẫn block?**  
Vì blockingCall() được Java thực thi ngay để làm argument cho just; cần defer bằng fromCallable và dùng scheduler thích hợp nếu phải dùng blocking dependency.

**Câu 7. Khi nào nên viết custom HandlerMapping và HandlerAdapter?**  
Khi ứng dụng thực sự có loại handler/chiến lược mapping mới mà annotated hoặc functional API không đáp ứng; phải kiểm soát order, result handling và kiểm thử.

**Câu 8. WebTestClient kiểm chứng được gì?**  
Nó có thể gửi request qua pipeline WebFlux để kiểm tra route, status, body, headers và behavior; muốn xác minh connector/network thực thì cần integration test với server thật.

## 20. Tổng kết

Hãy nhớ chuỗi trách nhiệm:

**DispatcherHandler điều phối → HandlerMapping tìm handler → HandlerAdapter gọi handler → HandlerResultHandler ghi kết quả.**

Trong Spring WebFlux, cùng một pipeline xử lý cả annotated controllers lẫn functional routes nhờ các chiến lược mapping và adapter khác nhau. ServerWebExchange mang ngữ cảnh request/response; Mono/Flux mô tả công việc bất đồng bộ; WebFilter xử lý cross-cutting concerns và các cơ chế error handling chịu trách nhiệm với lỗi phát sinh.

Hiểu đúng ranh giới của ba thành phần chính giúp bạn đọc stack trace, kiểm thử route, chẩn đoán 404/405/406/415, lựa chọn extension point và tránh nhầm WebFlux reactive server với Spring MVC Servlet. Trong ứng dụng Spring Boot thông thường, **không cần tự tạo DispatcherHandler hay HandlerAdapter**: chỉ cần khai báo controller/functional routes đúng stack, trả Publisher nhất quán và kiểm tra HTTP behavior bằng WebTestClient.

## 21. Tài liệu chính thức để đối chiếu

- Spring Framework WebFlux — DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework WebFlux — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework WebFlux — Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework WebFlux — WebHandler API và HTTP adapters: https://docs.spring.io/spring-framework/reference/web/webflux/web-handler-api.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework Testing — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
