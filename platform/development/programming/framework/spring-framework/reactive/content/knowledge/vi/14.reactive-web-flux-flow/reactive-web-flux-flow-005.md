# HandlerMapping, HandlerAdapter và HandlerResultHandler trong Spring WebFlux

## 1. Vai trò trong kiến trúc xử lý request

Spring WebFlux dùng mô hình **Front Controller**. Một thành phần trung tâm là **DispatcherHandler** nhận request đã được chuyển vào tầng web của Spring, sau đó ủy quyền cho các thành phần chuyên trách. Ba hợp đồng quan trọng là:

- **HandlerMapping**: tìm handler phù hợp với request hiện tại.
- **HandlerAdapter**: biết cách gọi handler đã được chọn, bất kể handler thuộc kiểu lập trình nào.
- **HandlerResultHandler**: nhận kết quả từ lần gọi handler và hoàn tất response, thường bằng cách ghi body hoặc render view.

Ba thành phần giải quyết ba câu hỏi khác nhau:

| Thành phần | Câu hỏi | Kết quả |
| --- | --- | --- |
| HandlerMapping | Request này thuộc endpoint/handler nào? | Một handler object hoặc Mono rỗng nếu không tìm thấy |
| HandlerAdapter | Làm thế nào gọi handler object này? | Mono<HandlerResult> |
| HandlerResultHandler | Xử lý giá trị trả về và ghi response ra sao? | Mono<Void> báo khi xử lý response hoàn tất |

**DispatcherHandler điều phối**, còn ba thành phần trên cung cấp cách tìm, gọi và xử lý kết quả. Chúng không thay thế nhau và cũng không phải ba bước do controller tự gọi.

Luồng tổng quát:

~~~text
HTTP request
    |
    v
Server adapter / HttpHandler
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    +--> HandlerMapping #1
    |        |
    |        +--> không khớp: Mono.empty()
    |
    +--> HandlerMapping #2
    |        |
    |        +--> khớp: Handler object
    |
    +--> HandlerAdapter phù hợp
    |        |
    |        +--> gọi handler
    |        +--> Mono<HandlerResult>
    |
    +--> HandlerResultHandler phù hợp
             |
             +--> ghi HTTP status, headers, body hoặc render view
             |
             v
         Mono<Void>
             |
             v
       HTTP response hoàn tất
~~~

Sơ đồ lược bỏ các nhánh exception handling, CORS, security, codec và transport. Nó thể hiện thứ tự trách nhiệm chính trong một request WebFlux.

## 2. DispatcherHandler là trung tâm điều phối

**DispatcherHandler** là một **WebHandler** đóng vai trò Front Controller trong Spring WebFlux. Nó không cần biết mọi kiểu handler cụ thể. Thay vào đó, nó phát hiện các bean hạ tầng trong ApplicationContext và gọi những bean thực hiện các contract của WebFlux.

Trong cấu hình WebFlux thông thường, DispatcherHandler được đăng ký với tên bean **webHandler**. **WebHttpHandlerBuilder** có thể dùng ApplicationContext để xây dựng HttpHandler và lắp các WebFilter/WebExceptionHandler cùng những thành phần cần thiết vào chuỗi xử lý. Server adapter sau đó kết nối HttpHandler với runtime HTTP như Reactor Netty hoặc Servlet container được hỗ trợ.

DispatcherHandler thường phối hợp các bước:

1. Lấy danh sách **HandlerMapping** và hỏi theo thứ tự.
2. Dùng **handler đầu tiên được tìm thấy**.
3. Tìm **HandlerAdapter** hỗ trợ handler đó.
4. Gọi adapter để nhận **HandlerResult**.
5. Chọn **HandlerResultHandler đầu tiên hỗ trợ HandlerResult**.
6. Chờ Mono<Void> của result handler hoàn tất để biết việc xử lý response đã kết thúc.

Điểm quan trọng: **một mapping trả về handler không có nghĩa response đã được tạo**. Nó mới chỉ xác định ai sẽ xử lý request. Tương tự, adapter gọi handler xong vẫn chưa chắc response đã được ghi; kết quả còn cần một result handler xử lý.

## 3. HandlerMapping: tìm handler phù hợp

### 3.1. Hợp đồng cơ bản

Interface **org.springframework.web.reactive.HandlerMapping** định nghĩa phương thức:

~~~java
Mono<Object> getHandler(ServerWebExchange exchange);
~~~

Đây là chữ ký API để hiểu contract; không phải mã triển khai hoàn chỉnh. **ServerWebExchange** đại diện cho ngữ cảnh HTTP hiện tại, bao gồm request, response và các thuộc tính trao đổi.

Kết quả:

- Nếu tìm thấy endpoint phù hợp, Mono phát ra **một handler object**.
- Nếu không tìm thấy handler, Mono có thể hoàn tất rỗng (**Mono.empty()**).
- Việc tìm kiếm thường xét path, HTTP method, header, parameter, content type, accept media type và các điều kiện routing khác, tùy implementation.

Handler object có thể là HandlerMethod của annotated controller, HandlerFunction của functional endpoint, WebHandler hoặc một kiểu handler chuyên biệt khác.

**HandlerMapping không gọi controller method.** Nó chỉ quyết định request được chuyển tới handler nào và có thể đặt một số metadata về pattern/URI variables vào ServerWebExchange.

### 3.2. Các HandlerMapping phổ biến

| Implementation | Cách tìm handler | Handler được trả về thường là |
| --- | --- | --- |
| **RequestMappingHandlerMapping** | Quét controller và các method có @RequestMapping, @GetMapping, @PostMapping... | HandlerMethod |
| **RouterFunctionMapping** | Duyệt các RouterFunction và kiểm tra predicate của route | HandlerFunction |
| **SimpleUrlHandlerMapping** | Tra URL pattern được đăng ký tường minh | WebHandler hoặc handler được map |
| **WebSocketHandlerMapping** | Ánh xạ URL tới WebSocket handler trong cấu hình WebFlux tương ứng | WebSocket handler |

### 3.3. Annotated controller: RequestMappingHandlerMapping

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {
    @GetMapping("/{id}")
    Mono<Product> find(@PathVariable String id) {
        return productService.findById(id);
    }
}
~~~

Đây là đoạn minh họa cần Product và productService do ứng dụng cung cấp. Khi ứng dụng khởi tạo, **RequestMappingHandlerMapping** phát hiện controller và đăng ký mapping cho GET /api/products/{id}.

Khi request GET /api/products/42 đến:

1. Mapping kiểm tra path và HTTP method.
2. Nếu các điều kiện khác phù hợp, nó tạo kết quả handler đại diện cho method **find**.
3. DispatcherHandler chuyển handler đó tới một HandlerAdapter thích hợp.

HandlerMapping không tự chạy find("42"), không gọi repository và không serialize Product.

### 3.4. Functional endpoint: RouterFunctionMapping

Ví dụ:

~~~java
@Bean
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
            .GET("/functional/products/{id}", handler::find)
            .build();
}
~~~

Đây là đoạn cấu hình minh họa với ProductHandler đã được đăng ký thành bean. **RouterFunctionMapping** phát hiện RouterFunction bean, kết hợp route và kiểm tra request predicate. Khi route khớp, nó trả HandlerFunction tương ứng.

Khác biệt với annotated controller nằm ở **cách khai báo và tìm handler**:

- Annotated controller: Spring quét annotation và method.
- Functional endpoint: ứng dụng khai báo route predicate và HandlerFunction tường minh.

Cả hai vẫn có thể đi qua DispatcherHandler và các contract adapter/result handler tương ứng.

### 3.5. Nhiều mapping và thứ tự ưu tiên

DispatcherHandler hỏi các HandlerMapping theo thứ tự. **Mapping đầu tiên trả về handler được chọn**; những mapping sau không còn được dùng để tìm một handler khác cho cùng request đó.

Điều này có ý nghĩa khi ứng dụng kết hợp:

- route tĩnh và annotated controller;
- custom URL mapping và functional endpoint;
- WebSocket mapping và HTTP controller;
- static resource mapping và API mapping.

Nếu có route chồng lấn, hãy cấu hình order có chủ đích và kiểm thử URL thực tế. Không dựa vào thứ tự ngẫu nhiên của bean hoặc giả định mapping cụ thể luôn thắng.

Một số mapping có thể trả Mono.empty() để nhường cho mapping tiếp theo. **Không tìm được handler sau khi đã hỏi hết các mapping** thường đi vào nhánh lỗi không tìm thấy endpoint (HTTP 404 qua cơ chế xử lý lỗi của WebFlux).

### 3.6. Metadata do mapping cung cấp

Các implementation URL-based có thể đặt thông tin trong **ServerWebExchange attributes**, chẳng hạn:

- Handler được chọn.
- Best matching pattern.
- URI template variables như id = "42".
- Media type có thể được tạo ra bởi handler.
- Path nằm trong mapping.

Không phải mọi HandlerMapping đều hỗ trợ mọi attribute. Code tùy chỉnh nên dùng contract/attribute được tài liệu của implementation bảo đảm, tránh giả định attribute luôn tồn tại.

## 4. HandlerAdapter: gọi handler mà không buộc DispatcherHandler biết chi tiết

### 4.1. Hợp đồng cơ bản

Interface **org.springframework.web.reactive.HandlerAdapter** có hai phương thức cốt lõi:

~~~java
boolean supports(Object handler);

Mono<HandlerResult> handle(
        ServerWebExchange exchange,
        Object handler
);
~~~

**supports(handler)** xác định adapter có thể gọi kiểu handler này hay không. **handle(exchange, handler)** thực hiện việc gọi và trả về Mono<HandlerResult>.

Lý do có adapter: các handler không có cùng cách gọi. Annotated controller cần phân giải annotation, argument, binding và reactive return value. Functional endpoint có HandlerFunction và nhận ServerRequest. WebSocket handler lại có một contract riêng.

DispatcherHandler chỉ cần hỏi adapter nào hỗ trợ object được mapping trả về. Nó không cần viết riêng logic gọi cho mọi loại handler.

### 4.2. Các HandlerAdapter thường gặp

| Implementation | Hỗ trợ handler | Trách nhiệm |
| --- | --- | --- |
| **RequestMappingHandlerAdapter** | HandlerMethod từ annotated controller | Phân giải tham số method, đọc request body, binding, gọi controller method và thích ứng kiểu trả về |
| **HandlerFunctionAdapter** | HandlerFunction từ functional endpoint | Chuyển ServerWebExchange sang contract functional, gọi HandlerFunction và bọc kết quả |
| **SimpleHandlerAdapter** | WebHandler | Gọi WebHandler trực tiếp |
| **WebSocketHandlerAdapter** | WebSocketHandler | Thực hiện xử lý WebSocket theo contract chuyên biệt |

### 4.3. RequestMappingHandlerAdapter làm gì?

Với controller:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderDto> get(@PathVariable String id) {
    return orderService.find(id);
}
~~~

Adapter cho annotated controller cần giải quyết nhiều việc trước khi có kết quả:

- Đọc URI template variable và gán cho tham số **id**.
- Xử lý @RequestParam, @PathVariable, @RequestHeader, @RequestBody và các argument resolver tương ứng.
- Dùng **HttpMessageReader**/codec để đọc request body nếu cần.
- Thực hiện conversion, validation và data binding theo cấu hình.
- Gọi method trên controller.
- Nhận return value như OrderDto, Mono<OrderDto>, Flux<OrderDto>, ResponseEntity hoặc kiểu reactive được hỗ trợ.
- Tạo **HandlerResult** kèm metadata cần cho bước xử lý kết quả.

RequestMappingHandlerAdapter không phải serializer cuối cùng. Nó giúp gọi method và chuẩn bị HandlerResult; việc ghi body vẫn thuộc HandlerResultHandler.

### 4.4. HandlerFunctionAdapter làm gì?

Với functional endpoint:

~~~java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok().bodyValue("hello");
~~~

Đây là đoạn minh họa về HandlerFunction. **HandlerFunctionAdapter** hỗ trợ HandlerFunction, gọi handler và bọc ServerResponse vào HandlerResult. Sau đó **ServerResponseResultHandler** xử lý ServerResponse để ghi response.

Như vậy, cùng một DispatcherHandler có thể xử lý annotated controller và functional endpoint bằng hai adapter khác nhau. Đây chính là lợi ích của contract: dispatcher không bị gắn chặt với một programming model.

### 4.5. Adapter có thể trả Mono rỗng không?

Contract handle trả **Mono<HandlerResult>**. Thông thường nó phát một HandlerResult. Tuy nhiên, Javadoc cho phép Mono hoàn tất rỗng nếu request đã được adapter xử lý hoàn toàn và không cần chuyển tiếp một HandlerResult cho result handler khác.

Vì vậy, **Mono.empty() ở ba giai đoạn có ý nghĩa khác nhau**:

- HandlerMapping rỗng: mapping này không tìm thấy handler; DispatcherHandler có thể hỏi mapping tiếp theo.
- HandlerAdapter rỗng: adapter cho biết request đã được xử lý hoàn toàn và không cần HandlerResult tiếp theo.
- Mono trả về từ controller rỗng: handler đã được gọi, nhưng không có giá trị ứng dụng để phát; cách tạo response phụ thuộc result handler và kiểu return.

Đừng đánh đồng cả ba trường hợp thành “404”.

## 5. HandlerResult: cầu nối giữa việc gọi handler và việc ghi response

**HandlerResult** là object biểu diễn kết quả của việc gọi handler hoặc handler method. Nó có thể chứa:

- Handler object/method liên quan.
- Giá trị trả về của handler.
- Kiểu trả về được khai báo.
- Binding/model context cần cho việc xử lý.
- Cơ chế xử lý exception được adapter gắn vào nếu cần.

Ví dụ handler method trả:

~~~java
Mono<Product> find() {
    return Mono.just(new Product("P01", "Notebook"));
}
~~~

Adapter không cần tự chờ và block để lấy Product. Nó có thể tạo HandlerResult chứa return value dạng Mono<Product> cùng metadata. **HandlerResultHandler** tiếp tục xử lý Publisher đó theo contract reactive, không cần chuyển toàn bộ request thành một lời gọi đồng bộ.

HandlerResult **không phải HTTP response cuối cùng**. Nó là gói kết quả trung gian để framework chọn cách ghi response phù hợp.

## 6. HandlerResultHandler: xử lý kết quả và hoàn tất HTTP response

### 6.1. Hợp đồng cơ bản

Interface **org.springframework.web.reactive.HandlerResultHandler** định nghĩa:

~~~java
boolean supports(HandlerResult result);

Mono<Void> handleResult(
        ServerWebExchange exchange,
        HandlerResult result
);
~~~

- **supports(result)** trả lời result handler có hiểu kiểu kết quả này không.
- **handleResult(exchange, result)** xử lý kết quả, cập nhật status/header và ghi body hoặc render view.
- **Mono<Void>** biểu thị quá trình ghi response đã hoàn tất hoặc phát lỗi.

HandlerResultHandler không tìm endpoint và không gọi controller. Nó bắt đầu từ HandlerResult đã có.

### 6.2. Các implementation mặc định quan trọng

| Implementation | Kiểu kết quả được xử lý | Order mặc định |
| --- | --- | ---: |
| **ResponseEntityResultHandler** | ResponseEntity, thường từ controller | 0 |
| **ServerResponseResultHandler** | ServerResponse, thường từ functional endpoint | 0 |
| **ResponseBodyResultHandler** | Method @ResponseBody hoặc class @RestController | 100 |
| **ViewResolutionResultHandler** | CharSequence, View, Model, Map, Rendering hoặc object được xem là model attribute | Integer.MAX_VALUE |

DispatcherHandler chuyển HandlerResult tới **HandlerResultHandler đầu tiên mà supports(result) trả true**, theo thứ tự đã cấu hình. Order mặc định giúp những result handler chuyên biệt được xét trước result handler xử lý response body tổng quát.

### 6.3. ResponseEntityResultHandler

Controller có thể trả:

~~~java
@GetMapping("/products/{id}")
ResponseEntity<Mono<Product>> find(@PathVariable String id) {
    return ResponseEntity.ok(
            productService.find(id)
    );
}
~~~

Đây là đoạn minh họa với Product/service. **ResponseEntityResultHandler** xử lý ResponseEntity, bao gồm status và headers; body reactive được ghi theo cơ chế tương ứng. Nếu controller trả ResponseEntity.notFound().build(), status 404 được xác định bởi ResponseEntity.

### 6.4. ResponseBodyResultHandler

Với:

~~~java
@RestController
class HealthController {
    @GetMapping("/health")
    Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }
}
~~~

Đây là đoạn minh họa. @RestController tương đương controller có response body semantics. **ResponseBodyResultHandler** xử lý kết quả body và dùng các **HttpMessageWriter** phù hợp để encode thành JSON, text hoặc media type khác.

Nếu return value là Mono<T>, framework xử lý giá trị khi Publisher phát tín hiệu. Nếu là Flux<T>, body có thể được ghi theo dạng stream tùy media type và codec.

### 6.5. ServerResponseResultHandler

Functional handler có thể trả:

~~~java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello");
~~~

**ServerResponseResultHandler** gọi cơ chế writeTo của ServerResponse để hoàn tất response. Nó là result handler phù hợp cho functional endpoint, trong khi HandlerFunctionAdapter là adapter gọi HandlerFunction.

### 6.6. ViewResolutionResultHandler

Nếu ứng dụng render HTML bằng view technology, handler có thể trả tên view, View, Model, Map hoặc Rendering. **ViewResolutionResultHandler** dùng ViewResolver để tìm view và render với model.

Đây không phải bước cần có cho mọi REST API. Một API trả JSON thường dùng ResponseBodyResultHandler hoặc ResponseEntityResultHandler; view result handler chỉ tham gia khi kiểu kết quả phù hợp.

## 7. So sánh hai đường xử lý: annotated controller và functional endpoint

### Đường A: annotated controller

~~~text
GET /api/products/42
        |
        v
RequestMappingHandlerMapping
        |
        v
HandlerMethod (ProductController.find)
        |
        v
RequestMappingHandlerAdapter
        |
        v
HandlerResult (return value: Mono<Product>)
        |
        v
ResponseBodyResultHandler
        |
        v
HttpMessageWriter / JSON codec
        |
        v
HTTP 200 + JSON body
~~~

### Đường B: functional endpoint

~~~text
GET /functional/products/42
        |
        v
RouterFunctionMapping
        |
        v
HandlerFunction<ServerResponse>
        |
        v
HandlerFunctionAdapter
        |
        v
HandlerResult (return value: Mono<ServerResponse>)
        |
        v
ServerResponseResultHandler
        |
        v
ServerResponse.writeTo(...)
        |
        v
HTTP response
~~~

Cả hai đường dùng cùng DispatcherHandler và các contract tổng quát, nhưng dùng mapping, adapter và result handler phù hợp với từng kiểu handler/return value.

## 8. Order và lựa chọn handler: vì sao không phải cứ bean nào xuất hiện trước là chạy?

Có hai lần lựa chọn độc lập:

**Lần 1 — chọn handler:**

- DispatcherHandler hỏi các HandlerMapping theo order.
- Mỗi mapping kiểm tra request.
- Mapping đầu tiên tìm được handler sẽ quyết định handler cho request.
- Nếu không có mapping nào khớp, request đi vào nhánh not found.

**Lần 2 — chọn cách xử lý kết quả:**

- HandlerAdapter phù hợp được chọn bằng khả năng supports(handler).
- Adapter tạo HandlerResult.
- Các HandlerResultHandler được xét theo order.
- HandlerResultHandler đầu tiên hỗ trợ result được dùng.

Điều này có nghĩa:

- Order của HandlerMapping không phải order của HandlerAdapter.
- Order của HandlerResultHandler không quyết định endpoint nào được chọn.
- Một HandlerAdapter có thể hỗ trợ nhiều loại handler, nhưng vẫn phải xác định rõ contract.
- Một HandlerResultHandler tổng quát không nên giành mọi result nếu các result chuyên biệt cần được xử lý trước.

Khi tự đăng ký implementation, cần thiết kế **supports(...)** đủ chính xác. Nếu supports quá rộng, result có thể bị handler sai nhận trước. Nếu quá hẹp, không có implementation nào nhận và response không được xử lý như mong muốn.

## 9. Lỗi và exception trong chuỗi dispatch

Lỗi có thể xảy ra ở nhiều giai đoạn:

1. **Trước mapping:** WebFilter hoặc xử lý request ban đầu phát lỗi.
2. **Trong HandlerMapping:** lỗi khi phân tích/routing request.
3. **Trong HandlerAdapter:** lỗi đồng bộ khi phân giải tham số hoặc gọi method.
4. **Sau khi handler trả reactive type:** Mono/Flux trả về phát onError sau đó.
5. **Trong HandlerResultHandler:** lỗi encode, ghi response hoặc render view.
6. **Trong transport:** client ngắt kết nối hoặc I/O thất bại.

Không phải lỗi nào cũng xuất hiện ngay tại thời điểm controller method được gọi. Một controller có thể trả Mono thành công về mặt tạo object, nhưng Publisher chỉ phát lỗi khi được subscribe sau đó.

### 9.1. DispatchExceptionHandler và HandlerResult

Một HandlerAdapter có thể:

- Xử lý lỗi xảy ra trực tiếp trong lúc gọi handler.
- Gắn cơ chế **DispatchExceptionHandler** vào HandlerResult để xử lý lỗi phát sinh muộn từ reactive return value hoặc quá trình result handling.
- Triển khai DispatchExceptionHandler để tham gia xử lý lỗi xảy ra trước khi handler được chọn, tùy contract.

Trong annotated controller, cơ chế **@ExceptionHandler** và **@ControllerAdvice** có thể được dùng để chuyển exception thành response theo cấu hình WebFlux.

Ở tầng ngoài cùng còn có **WebExceptionHandler** trong chuỗi WebFilter. Nếu lỗi không được xử lý bởi cơ chế gần handler, nó có thể đi tiếp tới exception handler ở tầng WebFlux.

### 9.2. Phân biệt lỗi mapping và Mono rỗng

| Tình huống | Ý nghĩa thường gặp |
| --- | --- |
| Không có HandlerMapping nào tìm được handler | Không có endpoint phù hợp; thường trả 404 |
| Handler method đã được chọn và trả Mono.empty() | Không có giá trị body; không tự động có nghĩa 404 |
| Handler trả ResponseEntity.notFound() | ResponseEntity chủ động đặt HTTP 404 |
| Handler phát onError | Lỗi được xử lý bởi exception handling phù hợp |
| HandlerResultHandler không hỗ trợ result | Không có result handler phù hợp; thường là lỗi cấu hình/unsupported return value |

Nếu API cần trả 404 khi không có bản ghi, hãy chủ động ánh xạ trường hợp Mono.empty() trong service/controller, ví dụ bằng switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND))). Không dựa vào giả định rằng mọi Mono rỗng đều biến thành 404.

## 10. Ví dụ Java 17+ chạy được: annotated và functional cùng một ứng dụng

Ví dụ này tạo hai endpoint dùng hai programming model. Nó cho phép quan sát hai đường dispatch khác nhau nhưng cùng chạy trên Spring WebFlux.

Cấu trúc:

~~~text
webflux-dispatch-demo/
├── pom.xml
└── src/main/java/example/demo/
    ├── DemoApplication.java
    ├── GreetingController.java
    └── FunctionalRoutes.java
~~~

### 10.1. pom.xml

Ví dụ dùng Spring Boot **3.5.5** và Java 17+; starter quản lý các phiên bản Spring Framework, Reactor và server runtime tương thích:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-dispatch-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 10.2. DemoApplication.java

~~~java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. GreetingController.java

~~~java
package example.demo;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping(
            value = "/annotated/hello",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of(
                "message", "Hello from annotated controller"
        ));
    }
}
~~~

### 10.4. FunctionalRoutes.java

~~~java
package example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> functionalRoutes() {
        return RouterFunctions.route(
                GET("/functional/hello"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("Hello from functional endpoint")
        );
    }
}
~~~

### 10.5. Chạy ứng dụng và quan sát kết quả

Từ thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Gọi annotated endpoint:

~~~bash
curl -s http://localhost:8080/annotated/hello
~~~

Body:

~~~json
{"message":"Hello from annotated controller"}
~~~

Đường dispatch chính: **RequestMappingHandlerMapping → RequestMappingHandlerAdapter → HandlerResult → ResponseBodyResultHandler**.

Gọi functional endpoint:

~~~bash
curl -s http://localhost:8080/functional/hello
~~~

Body:

~~~text
Hello from functional endpoint
~~~

Đường dispatch chính: **RouterFunctionMapping → HandlerFunctionAdapter → HandlerResult → ServerResponseResultHandler**.

Hai endpoint có thể cùng tồn tại vì WebFlux có các mapping và adapter phù hợp cho từng programming model. Ví dụ này không tự in log nội bộ của DispatcherHandler; đường đi được xác định từ loại route, handler và return type.

## 11. Khi nào cần tùy biến ba contract này?

Trong ứng dụng thông thường, **không cần tự tạo HandlerMapping, HandlerAdapter hoặc HandlerResultHandler**. WebFlux Config và Spring Boot đã cung cấp các implementation mặc định.

Chỉ nên mở rộng khi có một kiểu handler hoặc result thực sự đặc thù:

| Nhu cầu | Điểm mở rộng có thể cân nhắc |
| --- | --- |
| Route từ metadata hoặc registry riêng | Custom HandlerMapping |
| Gọi một kiểu handler do thư viện/domain cung cấp | Custom HandlerAdapter |
| Xử lý một kiểu return value đặc biệt hoặc giao thức response riêng | Custom HandlerResultHandler |
| Chỉ cần đổi codec, CORS, view resolver, argument resolver hoặc formatter | Ưu tiên WebFluxConfigurer và các API cấu hình chuyên biệt |

### 11.1. Yêu cầu đối với custom HandlerMapping

- Trả Mono handler theo contract; Mono.empty() khi không khớp.
- Có order rõ ràng để không che mất mapping khác.
- Xử lý path, method, content negotiation và validation phù hợp.
- Không thực hiện business logic hoặc I/O blocking trong giai đoạn dò route.
- Không giữ request-specific state trong field của singleton bean.
- Nếu mapping cần tra cứu bất đồng bộ, biểu diễn bằng Publisher và quản lý cancellation đúng cách.

### 11.2. Yêu cầu đối với custom HandlerAdapter

- **supports(handler)** phải xác định đúng kiểu handler.
- **handle(exchange, handler)** trả Mono<HandlerResult> theo contract.
- Không tự block để chờ kết quả reactive.
- Xử lý lỗi đồng bộ và lỗi deferred có chủ đích.
- Giữ metadata/return type cần thiết để result handler hiểu kết quả.
- Không ghi response trực tiếp rồi vẫn trả HandlerResult khiến response bị xử lý lần hai; nếu adapter đã xử lý hoàn toàn, dùng contract hoàn tất rỗng phù hợp.

### 11.3. Yêu cầu đối với custom HandlerResultHandler

- **supports(result)** không nhận những result thuộc implementation chuyên biệt khác.
- Ghi đúng status, headers, content type và body.
- Dùng **HttpMessageWriter/codec** hoặc API response phù hợp thay vì tự nối chuỗi JSON.
- Trả Mono<Void> đại diện cho việc ghi response; lỗi ghi phải được truyền trong reactive chain.
- Tôn trọng cancellation và không giữ buffer/request sau khi response kết thúc.
- Chú ý response chỉ được commit một lần; sau khi body đã ghi một phần, không thể tùy tiện đổi sang error response khác.

## 12. Debug khi request đi sai handler hoặc response sai định dạng

Khi một request trả 404, 406, 415 hoặc body không đúng, kiểm tra theo đúng từng giai đoạn:

1. **Request có đến WebFlux không?** Kiểm tra server, port, context path và WebFilter.
2. **HandlerMapping nào có thể khớp?** Kiểm tra path, method, params, headers, consumes/produces và route order.
3. **Handler object nào được chọn?** Annotated HandlerMethod, functional HandlerFunction, WebHandler hay handler khác?
4. **HandlerAdapter nào hỗ trợ object đó?** Kiểm tra loại handler và cấu hình adapter.
5. **HandlerResult chứa gì?** Return value, kiểu trả về và metadata có đúng không?
6. **HandlerResultHandler nào nhận result?** Kiểm tra kiểu return và supports(...) của result handler.
7. **Codec có ghi được media type không?** Kiểm tra HttpMessageWriter, Accept, Content-Type và body type.
8. **Có exception deferred không?** Mono/Flux có thể lỗi sau khi controller method đã return.
9. **Response đã commit chưa?** Lỗi phát sinh sau khi body đã gửi một phần có thể không còn đổi status được.
10. **Có route trùng hoặc order không mong muốn?** Kiểm tra HandlerMapping order và functional/annotated route.

Có thể bật logging có chọn lọc cho package WebFlux trong môi trường phát triển. Không nên giữ log DEBUG quá rộng trong production nếu nó ghi request metadata hoặc dữ liệu nhạy cảm. Với Spring Boot Actuator, endpoint mappings có thể giúp kiểm tra các endpoint được đăng ký, nhưng nó không thay thế hiểu biết về adapter/result handler.

## 13. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| HandlerMapping gọi controller | Mapping chỉ chọn handler object |
| HandlerAdapter quyết định URL nào khớp | Mapping quyết định route; adapter chỉ gọi handler đã chọn |
| HandlerResultHandler gọi business service | Result handler xử lý kết quả và ghi response |
| HandlerResult là HTTP response cuối cùng | Nó là object trung gian chứa return value/context |
| Một request luôn dùng tất cả HandlerMapping | Mapping đầu tiên tìm được handler quyết định |
| Mono.empty() luôn trả 404 | Ý nghĩa phụ thuộc nó rỗng ở mapping, adapter hay return value |
| Mọi controller đều dùng cùng một HandlerAdapter | Annotated, functional, WebSocket và WebHandler có adapter khác nhau |
| Controller trả Mono nghĩa là adapter chờ block() | Adapter/result pipeline giữ reactive semantics |
| HandlerResultHandler nào cũng serialize JSON | Có result handler cho ResponseEntity, ServerResponse, body và view |
| Thêm custom result handler luôn an toàn | supports/order sai có thể chiếm result của handler khác |
| Lỗi chỉ xảy ra khi controller method ném exception | Publisher có thể phát onError sau khi method đã return |
| Tự ghi response trong adapter rồi trả HandlerResult bình thường | Có nguy cơ xử lý response hai lần; phải theo contract hoàn tất đúng |

## 14. Checklist ghi nhớ theo request lifecycle

Khi lần theo một request, hãy tự hỏi:

- **Mapping:** URL/method/headers này được mapping nào nhận? Nó trả handler object nào?
- **Adapter:** adapter nào hỗ trợ object đó? Nó giải quyết argument và gọi handler ra sao?
- **HandlerResult:** return value và declared type là gì? Có Mono/Flux deferred không?
- **Result handling:** result handler nào hỗ trợ kết quả? Nó chọn status, headers, codec hoặc view nào?
- **Reactive lifecycle:** lỗi có thể phát muộn không? Cancellation xảy ra ở đâu? Response đã commit chưa?
- **Ordering:** có mapping hoặc result handler custom nào có order ưu tiên hơn không?
- **Not found vs empty:** request không có handler hay handler có nhưng không phát value?
- **Extension:** có thể cấu hình bằng WebFluxConfigurer trước khi cần tự triển khai contract không?

## 15. Kết luận

**HandlerMapping** trả lời *request này thuộc handler nào*; **HandlerAdapter** trả lời *gọi handler đó theo contract nào*; **HandlerResultHandler** trả lời *xử lý kết quả và ghi response ra sao*. **DispatcherHandler** nối ba trách nhiệm này thành một quy trình thống nhất.

Trong annotated controller, đường thường gặp là **RequestMappingHandlerMapping → RequestMappingHandlerAdapter → ResponseBodyResultHandler/ResponseEntityResultHandler**. Trong functional endpoint, đường thường gặp là **RouterFunctionMapping → HandlerFunctionAdapter → ServerResponseResultHandler**.

Hiểu đúng ba contract giúp debug routing, return value, content negotiation và exception handling chính xác hơn. Trong phần lớn dự án, hãy dùng implementation và WebFlux Config có sẵn; chỉ tạo custom mapping/adapter/result handler khi có một contract thực sự mới cần tích hợp.

**Tài liệu chính thức:**
- [Spring Framework Reference — DispatcherHandler, special beans, processing và result handling](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework Javadoc — HandlerMapping](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerMapping.html)
- [Spring Framework Javadoc — HandlerAdapter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerAdapter.html)
- [Spring Framework Javadoc — HandlerResultHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/HandlerResultHandler.html)
- [Spring Framework Reference — Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
