# @Controller, @RestController và đăng ký handler trong Spring WebFlux

Trong Spring WebFlux, một HTTP request phải được ánh xạ tới một phương thức xử lý, các giá trị từ URL, header và body phải được chuyển thành tham số Java, rồi kết quả của phương thức phải được ghi thành HTTP response. **@Controller** và **@RestController** là hai cách khai báo thành phần xử lý request theo mô hình annotated controller. Các annotation mapping như **@RequestMapping**, **@GetMapping** và **@PostMapping** mô tả điều kiện để Spring tìm đúng handler.

Cần hiểu cả hai phần: **controller được đăng ký như một Spring bean**, còn **các phương thức handler được phát hiện và đăng ký mapping** trong quá trình khởi tạo ứng dụng. Khi request đến, WebFlux chọn handler phù hợp, gọi phương thức theo mô hình reactive và chuyển kết quả thành response. Controller không tự gọi subscribe hoặc block để thực thi publisher.

Bài học thuộc nhóm **Controller**, với đề bài **@Controller, @RestController và đăng ký handler** trong Spring Framework - reactive.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt vai trò của **@Controller**, **@RestController** và **@ResponseBody**.
- Giải thích vì sao controller phải được Spring quản lý như một bean để handler mapping phát hiện.
- Mô tả vòng đời đăng ký và gọi handler qua **DispatcherHandler**, **HandlerMapping**, **HandlerAdapter** và **HandlerResultHandler**.
- Kết hợp mapping cấp lớp và cấp phương thức bằng **@RequestMapping**, **@GetMapping**, **@PostMapping**, **@PutMapping**, **@PatchMapping** và **@DeleteMapping**.
- Khai báo điều kiện route bằng path, HTTP method, params, headers, consumes và produces.
- Nhận dữ liệu qua **@PathVariable**, **@RequestParam**, **@RequestHeader**, **@RequestBody**, **@ModelAttribute** và các argument resolver.
- Trả về **Mono**, **Flux**, **ResponseEntity** hoặc **Mono<Void>** đúng ngữ nghĩa reactive.
- Phân biệt response body với tên view trong controller dùng view resolution.
- Kiểm thử việc đăng ký mapping bằng **WebTestClient**.
- Tránh xung đột route, gọi subscribe/block trong handler và lỗi cấu hình component scan.

## 2. Controller là gì trong WebFlux?

Controller là thành phần nhận yêu cầu ở tầng web và điều phối lời gọi tới service hoặc use case. Controller nên tập trung vào giao thức HTTP: đường dẫn, phương thức, status, header, nội dung request/response và chuyển đổi dữ liệu ở ranh giới web.

Một controller WebFlux thường là Spring bean có annotation **@Controller** hoặc **@RestController**. Các method handler được đánh dấu bằng annotation mapping. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public Mono<Product> findById(@PathVariable String id) {
        return productService.findById(id);
    }
}
~~~

Đây là mảnh ghép minh họa; cần khai báo **Product** và **ProductService**. Class mapping đặt tiền tố **/api/products**; method mapping thêm **/{id}** và chỉ nhận GET. Spring phát hiện method, tạo mapping metadata và gọi method khi request khớp.

Controller không nên tự quản lý vòng đời subscription. Khi method trả về **Mono<Product>**, WebFlux tiếp nhận publisher và quản lý việc subscribe, ghi response, xử lý lỗi và cancellation theo vòng đời request.

## 3. @Controller và @RestController khác nhau ở ngữ nghĩa trả về

### @Controller

**@Controller** là stereotype của Spring cho một thành phần xử lý web. Nó cũng được nhận diện như một component để component scanning đăng ký bean. Trong mô hình annotated controller, method có thể trả về tên view, ModelAndView hoặc response body tùy kiểu trả về và annotation.

Ví dụ controller phục vụ trang:

~~~java
@Controller
@RequestMapping("/pages")
public class PageController {

    @GetMapping("/welcome")
    public String welcome(Model model) {
        model.addAttribute("title", "Welcome");
        return "welcome";
    }
}
~~~

Với cấu hình view resolver phù hợp và template có tên **welcome**, chuỗi trả về được hiểu là **tên view** để render. Nó không mặc nhiên là văn bản được gửi thẳng trong HTTP body.

Nếu một method trong **@Controller** cần trả dữ liệu trực tiếp, có thể dùng **@ResponseBody**:

~~~java
@Controller
@RequestMapping("/api/status")
public class StatusController {

    @GetMapping
    @ResponseBody
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "UP"));
    }
}
~~~

Ở đây **@ResponseBody** yêu cầu Spring ghi giá trị trả về vào response body qua hệ thống message writer/codec. View resolution không được dùng cho kết quả đó.

### @RestController

**@RestController** là annotation tổng hợp kết hợp **@Controller** và **@ResponseBody** ở cấp lớp. Vì thế, các method handler của class mặc định ghi kết quả vào HTTP response body.

~~~java
@RestController
@RequestMapping("/api/status")
public class ApiStatusController {

    @GetMapping
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "UP"));
    }
}
~~~

Kết quả là response body được encode, thường là JSON nếu content negotiation và codec chọn JSON.

### So sánh

| Tiêu chí | @Controller | @RestController |
| --- | --- | --- |
| Là Spring component stereotype | Có | Có, thông qua @Controller |
| Ngữ nghĩa mặc định của method trả về | Có thể tham gia view/model resolution | Ghi kết quả vào response body |
| Cần @ResponseBody cho method trả JSON trực tiếp | Thường có, hoặc dùng annotation ở cấp method | Không cần |
| Phù hợp | MVC-style view, template, hoặc method có chọn lọc trả body | REST API, JSON, XML, streaming response |
| Có thể trả Mono/Flux | Có; cách diễn giải phụ thuộc return-value handling | Có; publisher được ghi vào response body |

**Chọn theo hợp đồng HTTP:** API trả dữ liệu thường dùng **@RestController**. Ứng dụng có trang HTML có thể dùng **@Controller** cho view và thêm **@ResponseBody** ở những method cung cấp API. Có thể kết hợp view và API trong một class **@Controller** nếu ngữ nghĩa từng method được khai báo rõ.

## 4. Controller phải được đăng ký thành Spring bean

Annotation mapping không tự hoạt động chỉ vì class tồn tại trong source code. Spring cần phát hiện controller và quản lý nó như một bean.

Các cách phổ biến:

1. **Component scanning:** đặt controller trong package được component scan.
2. **Explicit bean registration:** khai báo bean qua cấu hình khi có lý do cụ thể.
3. **Import configuration:** import cấu hình hoặc class bean theo cấu trúc ứng dụng.

Với Spring Boot, **@SpringBootApplication** thường đặt ở package gốc. Annotation này bao gồm cấu hình component scanning theo package của application class và các package con. Ví dụ:

~~~text
com.example.app
├── Application.java
├── controller
│   └── BookController.java
├── service
│   └── BookService.java
└── repository
    └── BookRepository.java
~~~

Nếu Application nằm ở **com.example.app**, controller ở **com.example.app.controller** thường được scan. Nếu controller nằm ngoài cây package đó, cần điều chỉnh phạm vi scan hoặc đăng ký bean phù hợp.

Ví dụ class khởi động:

~~~java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Không tạo controller bằng **new BookController(...)** trong một nơi tùy ý rồi kỳ vọng handler mapping tự phát hiện object đó. Handler mapping làm việc với các bean được quản lý trong ApplicationContext.

### Dependency injection trong controller

Nên dùng constructor injection để khai báo rõ service mà controller cần:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Book> findById(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Spring tìm bean **BookService** phù hợp và inject vào controller. Nếu không có bean tương ứng hoặc có nhiều bean không phân giải được, ứng dụng có thể thất bại khi khởi động. Controller không nên tự tạo repository, tự mở connection hoặc giữ mutable request state trong field dùng chung giữa các request.

## 5. Handler được đăng ký và gọi như thế nào?

Trong annotated WebFlux, các annotation trên controller được đọc trong quá trình khởi tạo ApplicationContext. Có thể hình dung luồng tổng quát:

~~~text
ApplicationContext khởi động
       |
       v
Component scanning tìm @Controller / @RestController
       |
       v
RequestMappingHandlerMapping
  phát hiện các method có mapping
       |
       v
Đăng ký RequestMappingInfo -> HandlerMethod
       |
       v
HTTP request đến
       |
       v
DispatcherHandler
       |
       v
HandlerMapping chọn HandlerMethod phù hợp
       |
       v
RequestMappingHandlerAdapter gọi method
       |
       v
HandlerResultHandler + HttpMessageWriter / ViewResolver
       |
       v
HTTP response
~~~

Các thành phần chính:

- **DispatcherHandler:** front controller của WebFlux, điều phối việc tìm handler và xử lý kết quả.
- **HandlerMapping:** tìm handler phù hợp với request. Với annotated controller, **RequestMappingHandlerMapping** phát hiện các method mapping.
- **HandlerMethod:** mô tả method và bean sẽ được gọi.
- **RequestMappingHandlerAdapter:** gọi method handler, phân giải tham số và thích nghi kiểu trả về.
- **HandlerResultHandler:** xử lý kết quả của handler; ví dụ ghi response body hoặc render view.
- **HttpMessageReader/HttpMessageWriter và codecs:** đọc/ghi nội dung như JSON, text hoặc dữ liệu streaming.
- **ViewResolver:** tham gia nếu controller trả kết quả cần render view.

Đây là mô hình khái quát; request thực tế còn đi qua WebFilter, security chain, exception handler và server adapter theo cấu hình ứng dụng.

### Đăng ký mapping không phải đăng ký từng request

Spring thường phát hiện mapping khi ứng dụng khởi động. Khi request đến, framework so sánh request với mapping đã đăng ký để chọn handler. Không nên tạo mapping mới thủ công trong mỗi lần gọi controller.

Nếu hai method đăng ký cùng một mapping không thể phân biệt, ứng dụng có thể báo lỗi ambiguous mapping khi khởi tạo hoặc khi xử lý request, tùy loại xung đột. Thiết kế route rõ ràng theo path, method và điều kiện sẽ giúp tránh vấn đề.

## 6. @RequestMapping ở cấp lớp và cấp method

**@RequestMapping** có thể đặt trên class, method hoặc kết hợp cả hai. Class-level mapping tạo đường dẫn chung; method-level mapping xác định endpoint cụ thể.

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    public Flux<OrderDto> findAll() {
        return orderService.findAll();
    }

    @GetMapping("/{id}")
    public Mono<OrderDto> findOne(@PathVariable String id) {
        return orderService.findById(id);
    }

    @PostMapping
    public Mono<ResponseEntity<OrderDto>> create(
            @RequestBody Mono<CreateOrderRequest> request) {
        return request
            .flatMap(orderService::create)
            .map(saved -> ResponseEntity
                .created(URI.create("/api/orders/" + saved.id()))
                .body(saved));
    }
}
~~~

Các path được ghép:

| Mapping cấp lớp | Mapping cấp method | Endpoint |
| --- | --- | --- |
| /api/orders | @GetMapping | GET /api/orders |
| /api/orders | @GetMapping("/{id}") | GET /api/orders/{id} |
| /api/orders | @PostMapping | POST /api/orders |

Ví dụ là fragment cần khai báo DTO, service và import URI. Nó minh họa cách phân tách route, không phải chương trình chạy độc lập.

### Các annotation mapping rút gọn

Những annotation sau là composed annotation dựa trên **@RequestMapping** và đặt HTTP method tương ứng:

| Annotation | HTTP method |
| --- | --- |
| @GetMapping | GET |
| @PostMapping | POST |
| @PutMapping | PUT |
| @PatchMapping | PATCH |
| @DeleteMapping | DELETE |

Có thể viết:

~~~java
@RequestMapping(path = "/{id}", method = RequestMethod.GET)
public Mono<Book> find(@PathVariable String id) {
    return service.findById(id);
}
~~~

Hoặc dùng dạng ngắn gọn:

~~~java
@GetMapping("/{id}")
public Mono<Book> find(@PathVariable String id) {
    return service.findById(id);
}
~~~

Thông thường nên dùng annotation chuyên biệt để code dễ đọc. Tránh khai báo nhiều mapping annotation trên cùng một method; mỗi method nên có một mapping chính rõ ràng.

## 7. Điều kiện mapping: path, method, params, headers, consumes, produces

Một route có thể được ràng buộc bằng nhiều điều kiện:

- **path/value:** đường dẫn.
- **method:** HTTP method.
- **params:** điều kiện trên query parameter.
- **headers:** điều kiện trên request header.
- **consumes:** loại nội dung request mà handler nhận.
- **produces:** loại nội dung response mà handler có thể tạo.

Ví dụ:

~~~java
@PostMapping(
    path = "/import",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE,
    headers = "X-Import-Mode=validated")
public Mono<ImportResult> importData(
        @RequestBody Mono<ImportRequest> request) {
    return request.flatMap(importService::importValidated);
}
~~~

Handler chỉ phù hợp khi request là POST tới **/import**, Content-Type tương thích JSON, header **X-Import-Mode** có giá trị validated và client có thể nhận JSON theo điều kiện produces. Ví dụ cần khai báo các kiểu và service trong ứng dụng.

### Content negotiation

Client có thể gửi header **Accept** để nói định dạng muốn nhận. Mapping **produces** và message writer/codecs cùng tham gia chọn định dạng response. Nếu không có representation phù hợp, WebFlux có thể trả lỗi HTTP phù hợp như 406 Not Acceptable.

**Content-Type** mô tả định dạng body request; **Accept** mô tả định dạng response client chấp nhận. Hai khái niệm này không thay thế nhau.

### Tránh route quá rộng

Một method chỉ khai báo path quá rộng có thể khó hiểu và dễ cạnh tranh với route khác. Hãy ưu tiên path cụ thể, HTTP method cụ thể và điều kiện rõ ràng. Nếu có nhiều handler cùng gần khớp, Spring áp dụng quy tắc specificity; mapping mơ hồ cần được sửa thay vì dựa vào thứ tự khai báo source code.

## 8. Đọc dữ liệu request vào tham số method

Spring WebFlux sử dụng argument resolver để chuyển thông tin request thành tham số method. Một số annotation thường gặp:

| Annotation | Nguồn dữ liệu | Ví dụ |
| --- | --- | --- |
| @PathVariable | Một đoạn của URL path | /books/{id} |
| @RequestParam | Query parameter hoặc form parameter theo cấu hình | ?page=2 |
| @RequestHeader | HTTP header | Authorization, X-Request-Id |
| @CookieValue | Cookie | session |
| @RequestBody | Request body được decode | JSON object |
| @ModelAttribute | Model/form data và binding | form fields |
| @RequestPart | Một phần multipart request | file upload, metadata |

Ví dụ:

~~~java
@GetMapping("/search")
public Flux<Book> search(
        @RequestParam("q") String query,
        @RequestParam(defaultValue = "0") int page,
        @RequestHeader(name = "X-Request-Id", required = false)
            String requestId) {
    return bookService.search(query, page, requestId);
}
~~~

**required=false** cho phép header không có mặt; khi đó tham số có thể là null nếu kiểu khai báo cho phép. Với ứng dụng production, cân nhắc dùng Optional hoặc kiểu dữ liệu/validation phù hợp để tránh xử lý null tùy tiện.

### @RequestBody với Mono và Flux

Trong WebFlux, request body có thể được biểu diễn reactive:

~~~java
@PostMapping("/one")
public Mono<Book> createOne(@RequestBody Mono<CreateBookRequest> body) {
    return body.flatMap(bookService::create);
}

@PostMapping(
    path = "/bulk",
    consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Book> createMany(
        @RequestBody Flux<CreateBookRequest> body) {
    return body.concatMap(bookService::create);
}
~~~

**Mono<CreateBookRequest>** biểu diễn body được decode thành một đối tượng. **Flux<CreateBookRequest>** phù hợp với request body có nhiều phần tử theo media type/codec hỗ trợ, ví dụ NDJSON. Với thao tác ghi cần thứ tự, ví dụ dùng concatMap; nếu nghiệp vụ cho phép xử lý đồng thời thì chọn operator và giới hạn concurrency phù hợp.

Không dùng block để đọc body trong controller. Việc decode body và điều tiết dữ liệu do WebFlux quản lý.

## 9. Kiểu trả về của annotated controller trong WebFlux

Method handler có thể trả nhiều kiểu. Chọn kiểu theo số lượng dữ liệu, trạng thái HTTP và vòng đời công việc.

| Kiểu trả về | Ý nghĩa thường gặp |
| --- | --- |
| T | Kết quả đồng bộ, không phải lựa chọn mặc định cho I/O reactive |
| Mono<T> | 0 hoặc 1 kết quả bất đồng bộ |
| Flux<T> | 0 đến nhiều phần tử |
| Mono<Void> | Công việc bất đồng bộ chỉ cần biểu thị hoàn thành |
| ResponseEntity<T> | Status/header/body đồng bộ |
| Mono<ResponseEntity<T>> | Status/header/body được quyết định bất đồng bộ |
| ResponseEntity<Flux<T>> | Metadata response có thể xác định trước, body là stream |
| Flux<ServerSentEvent<T>> | Dòng sự kiện SSE |

### Mono và kết quả không tìm thấy

Một repository reactive có thể trả **Mono.empty()** khi không tìm thấy. Controller có thể ánh xạ thành 404:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<Book>> findById(@PathVariable String id) {
    return bookService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Đây là pattern rõ ràng: có dữ liệu thì 200; publisher hoàn thành rỗng thì 404. Nếu repository phát lỗi, lỗi đi tới cơ chế exception handling thay vì tự động biến thành 404.

### ResponseEntity và status/header

**Mono<ResponseEntity<T>>** hữu ích khi status hoặc header phụ thuộc kết quả bất đồng bộ. Ví dụ tạo tài nguyên có thể trả 201 Created và Location header. Khi status có thể xác định trước còn body là stream, **ResponseEntity<Flux<T>>** có thể phù hợp.

### Flux và streaming

Với response JSON thông thường, **Flux<T>** thường được encode thành JSON array. Nếu muốn client nhận từng sự kiện theo thời gian, chọn media type và giao thức streaming phù hợp:

- **text/event-stream:** Server-Sent Events.
- **application/x-ndjson:** JSON objects phân tách theo dòng nếu codec/cấu hình hỗ trợ.
- **application/json:** thường biểu diễn một JSON document/array, không mặc nhiên mang semantics SSE.

Ví dụ SSE:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.builder("tick-" + index)
            .event("heartbeat")
            .id(Long.toString(index))
            .build());
}
~~~

Ví dụ là fragment cần import Duration, ServerSentEvent và Reactor. Nguồn interval tiếp tục phát cho tới khi subscriber hủy; khi client đóng kết nối, cancellation cần được truyền về upstream để dừng công việc có thể hủy.

## 10. @ResponseBody, codec và việc ghi response

Khi method hoặc class có **@ResponseBody**, Spring không coi giá trị trả về là tên view. Kết quả được chuyển thành HTTP response body bằng các **HttpMessageWriter** và codec tương ứng.

Ví dụ:

~~~java
@RestController
public class GreetingController {

    @GetMapping(
        value = "/greeting",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Greeting> greeting() {
        return Mono.just(new Greeting("Hello", "Reactive"));
    }
}
~~~

Với class **Greeting** có thể serialize, codec JSON ghi response tương ứng. Việc chọn codec dựa trên kiểu dữ liệu, content negotiation, cấu hình codec và media type. Nếu client gửi Accept không tương thích, response có thể thất bại ở bước negotiation.

Không cần tự chuyển object thành JSON string bằng Jackson trong controller. Hãy trả object/Mono/Flux và để message writer serialize; cách này giữ được content negotiation và xử lý lỗi codec đúng tầng.

### Response không có body

Với thao tác chỉ cần báo hoàn tất:

~~~java
@DeleteMapping("/{id}")
public Mono<Void> delete(@PathVariable String id) {
    return bookService.deleteById(id);
}
~~~

**Mono<Void>** hoàn thành khi thao tác kết thúc thành công. Status HTTP mặc định phụ thuộc mapping/return handling; nếu cần status cụ thể như 204, dùng **@ResponseStatus** hoặc **ResponseEntity** phù hợp. Không kỳ vọng Mono<Void> phát một object body.

## 11. Xử lý lỗi trong controller

Không nên đặt toàn bộ try/catch đồng bộ quanh publisher rồi cho rằng sẽ bắt được lỗi phát ra sau đó. Lỗi reactive có thể xuất hiện khi subscription và trong quá trình publisher chạy.

Có thể xử lý theo các tầng:

- **Trong service/pipeline:** dùng các operator như onErrorMap, onErrorResume khi có ý nghĩa nghiệp vụ.
- **Tại controller:** chuyển kết quả thành ResponseEntity nếu đó là quyết định của endpoint.
- **@ExceptionHandler:** xử lý exception trong controller/advice.
- **@ControllerAdvice / @RestControllerAdvice:** áp dụng chính sách xử lý lỗi cho nhiều controller.

Ví dụ advice cho REST response:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            BookNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Map.of("error", exception.getMessage()));
    }
}
~~~

Đây là fragment cần khai báo BookNotFoundException và import. Với reactive flow, exception được phát thành onError vẫn có thể được cơ chế exception handler xử lý ở tầng web. Không dùng onErrorResume(error -> Mono.empty()) ở mọi nơi chỉ để tránh HTTP 500; làm vậy có thể che lỗi và biến thất bại thành response rỗng không đúng hợp đồng.

## 12. Annotated controller và functional endpoints

WebFlux hỗ trợ cả hai cách định nghĩa endpoint:

| Cách | Khai báo | Điểm mạnh |
| --- | --- | --- |
| Annotated controller | @Controller, @RestController và mapping annotation | Quen thuộc, gần mô hình MVC, dễ dùng argument resolver và annotation |
| Functional endpoint | RouterFunction và HandlerFunction | Khai báo route và handler bằng Java API, dễ tổ chức route theo module |

Ví dụ functional route:

~~~java
@Bean
RouterFunction<ServerResponse> routes(BookHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/functional/books"),
        handler::findAll);
}
~~~

Đây là fragment; **BookHandler** cần có method trả về **Mono<ServerResponse>**. Functional endpoint không cần **@RestController** để đăng ký route; route được tạo từ bean RouterFunction.

Hai mô hình có thể cùng tồn tại trong một ứng dụng. Hãy tránh đăng ký cùng một path/method ở cả hai nơi nếu không có chủ đích, vì route resolution có thể trở nên khó hiểu. Chọn một phong cách nhất quán cho từng module.

## 13. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ sau tạo một REST controller đơn giản, có endpoint liệt kê, tìm theo ID và tạo sách. Dữ liệu nằm trong danh sách cố định để tập trung vào mapping và response handling; đây là demo, không phải persistence production.

Cấu trúc project:

~~~text
webflux-controller-demo/
├── pom.xml
└── src
    ├── main
    │   └── java
    │       └── com/example/demo
    │           ├── ControllerDemoApplication.java
    │           ├── BookController.java
    │           ├── Book.java
    │           └── CreateBookRequest.java
    └── test
        └── java
            └── com/example/demo
                └── BookControllerTests.java
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
  <artifactId>webflux-controller-demo</artifactId>
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

Spring Boot parent quản lý các phiên bản Spring Framework, Reactor và test dependency tương thích. Trong ứng dụng thực tế, nên dùng dependency management của Spring Boot thay vì tự đặt phiên bản reactor-core riêng.

### ControllerDemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ControllerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ControllerDemoApplication.class, args);
    }
}
~~~

### Book.java

~~~java
package com.example.demo;

public record Book(String id, String title) {
}
~~~

### CreateBookRequest.java

~~~java
package com.example.demo;

public record CreateBookRequest(String title) {
}
~~~

### BookController.java

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private static final List<Book> BOOKS = List.of(
        new Book("1", "Reactive Streams"),
        new Book("2", "Spring WebFlux")
    );

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Book> findAll() {
        return Flux.fromIterable(BOOKS);
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Book>> findById(
            @PathVariable("id") String id) {

        return Flux.fromIterable(BOOKS)
            .filter(book -> book.id().equals(id))
            .next()
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Book> create(
            @RequestBody Mono<CreateBookRequest> request) {

        return request.map(body ->
            new Book("new-1", body.title()));
    }
}
~~~

Các điểm cần chú ý:

- Class được đăng ký vì có **@RestController** và nằm trong package con của application class.
- **@RequestMapping("/api/books")** tạo prefix cho các method.
- **@GetMapping** xử lý GET collection; **@GetMapping("/{id}")** xử lý GET một tài nguyên.
- **@PathVariable("id")** lấy giá trị từ URL.
- **@RequestBody Mono<CreateBookRequest>** cho phép WebFlux decode body thành một publisher.
- **@ResponseStatus(CREATED)** đặt status 201 cho method tạo.
- **Mono<ResponseEntity<Book>>** cho phép chọn 200 hoặc 404 dựa trên kết quả.
- Controller trả publisher, không gọi subscribe hay block.

### BookControllerTests.java

~~~java
package com.example.demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(BookController.class)
class BookControllerTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void getCollectionRegistersAndInvokesHandler() {
        webTestClient.get()
            .uri("/api/books")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$[0].id").isEqualTo("1")
            .jsonPath("$[1].title").isEqualTo("Spring WebFlux");
    }

    @Test
    void missingBookReturnsNotFound() {
        webTestClient.get()
            .uri("/api/books/unknown")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void postMappingReadsBodyAndReturnsCreated() {
        webTestClient.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Reactive Controller"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("new-1")
            .jsonPath("$.title").isEqualTo("Reactive Controller");
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint từ terminal khác:

~~~bash
curl -i http://localhost:8080/api/books
curl -i http://localhost:8080/api/books/1
curl -i http://localhost:8080/api/books/unknown
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d "{\"title\":\"Reactive Controller\"}"
~~~

Response JSON cho GET collection có dạng:

~~~json
[
  {"id":"1","title":"Reactive Streams"},
  {"id":"2","title":"Spring WebFlux"}
]
~~~

Response cho GET **/api/books/1** có status 200 và body:

~~~json
{"id":"1","title":"Reactive Streams"}
~~~

GET **/api/books/unknown** trả 404. POST với body mẫu trả 201 Created và JSON:

~~~json
{"id":"new-1","title":"Reactive Controller"}
~~~

ID **new-1** cố định chỉ để demo. Trong ứng dụng thật, service/repository phải tạo ID duy nhất và lưu dữ liệu theo transaction/semantics phù hợp.

Test dùng **@WebFluxTest(BookController.class)** để tạo test slice cho controller và kiểm tra WebFlux mapping, argument binding và response encoding qua WebTestClient. Đây là kiểm tra việc controller được đăng ký và route hoạt động trong test context, không phải kiểm thử database hoặc toàn bộ production deployment.

## 14. Cấu hình Spring Boot và @EnableWebFlux

Với ứng dụng Spring Boot sử dụng **spring-boot-starter-webflux**, auto-configuration thường đã cấu hình hạ tầng WebFlux cần thiết. Không cần thêm **@EnableWebFlux** chỉ để @RestController hoạt động.

Trong ứng dụng cấu hình WebFlux thủ công, **@EnableWebFlux** có thể được dùng để bật hạ tầng annotated controller và các thành phần WebFlux. Tuy nhiên, khi dùng Spring Boot, thêm annotation này có thể làm ứng dụng chuyển sang cấu hình WebFlux do người dùng kiểm soát và ảnh hưởng một số auto-configuration. Chỉ dùng khi bạn thực sự muốn tiếp quản cấu hình; nếu chỉ cần custom codec, CORS hoặc resource handler, xem xét cơ chế cấu hình tương ứng của Boot trước.

Không nhầm **spring-boot-starter-web** với **spring-boot-starter-webflux**. Nếu cả hai starter cùng có mặt, Spring Boot có thể ưu tiên cấu hình Spring MVC theo điều kiện classpath và application type. Chọn stack chủ đích và kiểm tra dependency tree khi server khởi động không đúng như mong đợi.

## 15. Những lỗi thường gặp

1. **Class controller không được scan:** controller nằm ngoài package scan hoặc không được đăng ký thành bean. Đặt package đúng hoặc cấu hình scan/import.
2. **Dùng @Controller nhưng kỳ vọng String là response body:** String có thể được hiểu là view name. Dùng @ResponseBody hoặc @RestController cho API.
3. **Dùng @RestController cho method cần render view:** @RestController mặc định ghi body; chọn @Controller cho view resolution.
4. **Quên prefix cấp lớp:** method @GetMapping("/{id}") nằm trong class @RequestMapping("/api/books") tạo route /api/books/{id}, không phải /{id}.
5. **Nhầm @RequestParam và @PathVariable:** query parameter nằm sau dấu hỏi; path variable là một phần URL path.
6. **Thiếu Content-Type hoặc consumes không khớp:** request body có thể không được map tới handler hoặc không decode được.
7. **produces không tương thích Accept:** client có thể nhận 406 Not Acceptable.
8. **Hai method có mapping mơ hồ:** làm rõ path, HTTP method và điều kiện params/headers/consumes/produces.
9. **Tự parse JSON trong controller:** để HttpMessageReader và codec xử lý body, trừ khi có yêu cầu đặc biệt.
10. **Gọi subscribe() trong controller:** tạo subscription ngoài lifecycle của HTTP request, làm khó xử lý lỗi/cancel và có thể chạy side effect tách rời response.
11. **Gọi block() hoặc blockLast():** có thể chặn event-loop thread và làm giảm khả năng phục vụ nhiều request.
12. **Dùng Flux cho thao tác chỉ có một kết quả mà không cần streaming:** Mono diễn đạt rõ hơn kết quả 0..1.
13. **Trả Flux vô hạn với application/json:** client có thể chờ JSON document chưa hoàn tất. Nếu cần streaming, dùng SSE hoặc media type streaming thích hợp.
14. **Tưởng @ResponseStatus tự xử lý mọi exception:** annotation này đặt status theo handler; lỗi phát sinh cần error handling phù hợp.
15. **Tạo mutable field chứa dữ liệu từng request:** controller bean thường được dùng đồng thời; không lưu request state vào field dùng chung.
16. **Thêm @EnableWebFlux không cần thiết trong Boot:** có thể làm thay đổi auto-configuration. Hiểu rõ cấu hình trước khi bật.
17. **Đăng ký cùng path ở annotated và functional endpoint:** tránh xung đột route hoặc hành vi khó dự đoán.
18. **Không test route thực tế:** một method compile được không chứng minh mapping đã được đăng ký hoặc JSON codec hoạt động.

## 16. Checklist thiết kế controller

Trước khi hoàn thành một controller, hãy kiểm tra:

- **Bean registration:** class có nằm trong component scan hoặc được khai báo bean không?
- **Controller semantics:** cần view (@Controller) hay response body (@RestController/@ResponseBody)?
- **Class-level path:** prefix có rõ ràng và nhất quán không?
- **Method mapping:** HTTP method và path có đúng hợp đồng REST không?
- **Conditions:** params, headers, consumes, produces có thực sự cần thiết và không mâu thuẫn?
- **Arguments:** request data dùng đúng @PathVariable, @RequestParam, @RequestHeader, @RequestBody?
- **Reactive type:** Mono cho 0..1, Flux cho 0..N; body streaming có media type phù hợp?
- **Status and headers:** 201, 204, 404 và Location header có được biểu diễn đúng?
- **Error handling:** exception có được xử lý tại đúng tầng, không bị nuốt âm thầm?
- **Threading:** không có block, sleep hoặc I/O blocking trên event loop?
- **Lifecycle:** không subscribe lồng; publisher được compose và trả về cho WebFlux?
- **Tests:** WebTestClient kiểm tra mapping, argument binding, status và body?
- **Configuration:** Boot auto-configuration và starter đang chọn đúng WebFlux stack?

## 17. Bài tập tự kiểm tra

**Bài 1.** Một class có @Controller và method trả String. Chuỗi đó mặc nhiên là HTTP body phải không?  
**Đáp án:** Không. Trong view-based controller, chuỗi có thể là tên view. Muốn ghi trực tiếp body, dùng @ResponseBody hoặc @RestController.

**Bài 2.** @RestController khác @Controller ở điểm nào?  
**Đáp án:** @RestController kết hợp @Controller và @ResponseBody ở cấp lớp, nên kết quả method mặc định được ghi vào response body.

**Bài 3.** Class có @RestController nhưng nằm ngoài component scan. Handler có được tự động đăng ký không?  
**Đáp án:** Không. Class phải được đăng ký thành bean trong ApplicationContext.

**Bài 4.** Class mapping là /api/books, method mapping là /{id}. URL đầy đủ là gì?  
**Đáp án:** /api/books/{id}.

**Bài 5.** Client POST JSON nhưng method mapping khai báo consumes=text/plain. Điều gì có thể xảy ra?  
**Đáp án:** Request không thỏa điều kiện mapping hoặc body không được decode theo mong muốn. Khai báo consumes phải phù hợp Content-Type thực tế.

**Bài 6.** Nên dùng Mono<Book> hay Flux<Book> cho endpoint tìm một quyển sách?  
**Đáp án:** Mono<Book> vì kết quả có thể rỗng hoặc có một quyển. Nếu cần status 404 dựa trên kết quả, dùng Mono<ResponseEntity<Book>>.

**Bài 7.** Flux<Event> trả về từ controller có tự động trở thành SSE không?  
**Đáp án:** Không. Cần khai báo media type text/event-stream và định nghĩa semantics streaming phù hợp.

**Bài 8.** Vì sao không gọi subscribe() trong controller?  
**Đáp án:** Framework cần quản lý subscription gắn với HTTP request, bao gồm demand, cancellation, lỗi và ghi response. Subscribe thủ công tách công việc khỏi lifecycle đó.

**Bài 9.** Khi nào dùng @EnableWebFlux trong Spring Boot?  
**Đáp án:** Chỉ khi chủ động tiếp quản cấu hình WebFlux. Starter WebFlux của Boot đã auto-configure phần lớn hạ tầng cần thiết.

**Bài 10.** Hai controller cùng đăng ký GET /api/books/{id} có thể gây vấn đề gì?  
**Đáp án:** Mapping có thể xung đột hoặc mơ hồ. Thiết kế path/conditions rõ ràng và giữ một handler sở hữu route.

## 18. Ghi nhớ

**@Controller** khai báo một thành phần xử lý web; **@RestController** bổ sung semantics **@ResponseBody** cho toàn bộ method trong class. Controller phải được Spring quản lý như bean. Các mapping annotation cấp lớp và cấp method được **RequestMappingHandlerMapping** phát hiện để tạo HandlerMethod; khi request đến, **DispatcherHandler** điều phối, **RequestMappingHandlerAdapter** gọi method và các handler kết quả ghi body hoặc render view.

Trong WebFlux, trả **Mono/Flux** để framework quản lý subscription và response lifecycle. Dùng **@ResponseBody/@RestController** cho API body, view resolution cho trang, điều kiện mapping đúng với HTTP contract, và WebTestClient để xác minh route đã được đăng ký. Giữ controller mỏng, không block, không subscribe thủ công và không giữ state của từng request trong field dùng chung.

### Tài liệu tham khảo

- Spring Framework, [Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework, [Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html).
- Spring Framework, [Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html).
- Spring Framework, [Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
- Spring Framework, [WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Boot, [Developing Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html).
