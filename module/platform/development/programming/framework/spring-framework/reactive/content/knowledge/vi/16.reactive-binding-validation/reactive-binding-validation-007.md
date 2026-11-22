# Ràng buộc tham số, giá trị trả về và điều kiện phiên bản Spring

Trong **Spring WebFlux**, một phương thức controller không chỉ nhận các tham số Java tùy ý và trả về bất kỳ kiểu nào. Spring cần biết **lấy dữ liệu đầu vào từ đâu**, **chuyển đổi hoặc giải mã dữ liệu bằng cách nào**, **kiểu trả về biểu diễn một response ra sao**, và **phiên bản Spring nào hỗ trợ cơ chế đó**.

Có ba nhóm quyết định cần xem cùng nhau:

- **Ràng buộc tham số (method arguments):** giá trị đến từ path, query, header, cookie, body, multipart, session hay request context; Spring chuyển đổi và validate chúng trước hoặc trong khi gọi handler.
- **Giá trị trả về (return values):** handler trả một giá trị, publisher bất đồng bộ, luồng nhiều phần tử, response có status/header riêng, hay một view.
- **Điều kiện phiên bản:** các thế hệ Spring thay đổi baseline Java, namespace validation (javax/jakarta), cách method validation hoạt động và hỗ trợ kiểu bất đồng bộ.

Bài này tập trung vào annotated controllers của Spring WebFlux, với ví dụ Java 17, Reactor, Bean Validation và WebTestClient.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các nguồn tham số như **@PathVariable**, **@RequestParam**, **@RequestHeader**, **@CookieValue**, **@RequestBody**, **@RequestPart** và **@ModelAttribute**.
2. Chọn kiểu tham số đồng bộ hay reactive phù hợp; hiểu vì sao Mono<T>/Flux<T> thường chỉ dùng ở những vị trí cần đọc body hoặc xử lý I/O bất đồng bộ.
3. Giải thích Spring chuyển đổi chuỗi sang kiểu Java như UUID, int, LocalDate, enum và áp dụng default/optional/required.
4. Phân biệt Mono<T>, Flux<T>, Mono<Void>, ResponseEntity<T>, ResponseEntity<Flux<T>>, String, Model và void ở vị trí return.
5. Hiểu quá trình encode/decode bằng HttpMessageReader và HttpMessageWriter, media type và streaming response.
6. Dùng @Valid, @Validated, constraint annotations, BindingResult và xử lý các exception validation.
7. Nhận diện các mốc quan trọng: WebFlux từ Spring 5.0, Kotlin coroutine support từ 5.2, namespace Jakarta từ 6.0, built-in method validation từ 6.1 và baseline của Spring 7.
8. Thiết kế controller tương thích với phiên bản dependency thực tế, tránh sao chép ví dụ dùng javax vào dự án jakarta hoặc dùng API chưa có.
9. Kiểm thử binding, validation, status, header và body bằng WebTestClient.

## 2. Luồng xử lý một controller method

Khi HTTP request tới một annotated controller, Spring WebFlux thực hiện một chuỗi công việc khái quát:

~~~text
HTTP request
    |
    v
Chọn handler theo @RequestMapping
    |
    v
Giải quyết method arguments
(path/query/header/cookie/body/session...)
    |
    v
Chuyển đổi kiểu + data binding + validation
    |
    v
Gọi controller method
    |
    v
Nhận return value
(Mono / Flux / ResponseEntity / void / view...)
    |
    v
Encode response bằng HttpMessageWriter hoặc render view
    |
    v
HTTP response
~~~

Không phải tất cả các tham số đều được giải quyết theo cùng cách:

- Path, query, header và cookie thường bắt đầu từ chuỗi, sau đó qua conversion service.
- Request body được giải mã qua codec/HttpMessageReader.
- @ModelAttribute dùng data binding để điền dữ liệu vào object.
- Mono/Flux ở những vị trí hỗ trợ thể hiện việc dữ liệu được cung cấp bất đồng bộ.
- Giá trị trả về được diễn giải theo loại return handler; String có thể là tên view, còn trong @RestController một đối tượng thường được ghi thành response body.

**Điểm quan trọng:** WebFlux có reactive I/O nhưng điều đó không có nghĩa mọi tham số phải bọc trong Mono. Các tham số đơn giản như path variable hoặc query parameter thường được giải quyết thành giá trị Java trước khi gọi handler. Dùng wrapper reactive sai vị trí có thể khiến chữ ký không được hỗ trợ hoặc làm code phức tạp không cần thiết.

## 3. Các loại method argument thường dùng

### 3.1. Đối tượng request và exchange

Một handler có thể nhận các đối tượng cung cấp quyền truy cập trực tiếp vào request/response:

| Tham số | Công dụng |
| --- | --- |
| ServerWebExchange | Container cấp cao cho request, response, session và request attributes. |
| ServerHttpRequest | Đọc method, URI, headers, cookies và body ở mức HTTP. |
| ServerHttpResponse | Điều khiển status, headers và response body khi cần thao tác trực tiếp. |
| WebSession | Truy cập session reactive; session không nhất thiết được tạo mới nếu không có thao tác yêu cầu. |
| Principal | Người dùng đã xác thực, nếu có security context phù hợp. |
| HttpMethod | HTTP method của request hiện tại. |
| Locale, TimeZone, ZoneId | Ngữ cảnh locale/múi giờ theo cấu hình resolver của ứng dụng. |
| UriComponentsBuilder | Tạo URL dựa trên scheme, host, port và context path của request. |

Ví dụ:

~~~java
@GetMapping("/debug")
Mono<String> debug(
        ServerWebExchange exchange,
        ServerHttpRequest request,
        HttpMethod method) {

    String path = request.getURI().getPath();
    String client = request.getHeaders()
        .getFirst("X-Client");

    return Mono.just(
        method + " " + path + " client=" + client
    );
}
~~~

Đây là snippet tích hợp cần import các kiểu Spring WebFlux tương ứng. Không nên nhận HttpServletRequest/HttpServletResponse trong controller WebFlux: dùng abstraction reactive như ServerHttpRequest, ServerHttpResponse hoặc ServerWebExchange.

### 3.2. @PathVariable

Dùng để lấy giá trị từ URI template:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderView> get(@PathVariable("id") UUID id) {
    return orderService.findById(id);
}
~~~

Với request /orders/6a..., Spring lấy segment {id} và chuyển thành UUID. Nếu chuỗi không hợp lệ, quá trình chuyển đổi thất bại trước khi handler được gọi và đi vào cơ chế xử lý lỗi binding/conversion.

Path variable thông thường là bắt buộc vì chính path pattern yêu cầu nó. Đặt tên rõ trong annotation giúp code không phụ thuộc việc compiler giữ tên tham số bằng tùy chọn -parameters.

### 3.3. @RequestParam

Trong WebFlux, @RequestParam dùng để lấy **query parameter**:

~~~java
@GetMapping("/search")
Flux<ProductView> search(
        @RequestParam("q") String keyword,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {
    return productService.search(keyword, page, size);
}
~~~

Ví dụ request:

~~~text
GET /api/products/search?q=keyboard&page=0&size=20
~~~

Các thuộc tính quan trọng:

- name/value: tên query parameter.
- required: mặc định true.
- defaultValue: dùng khi parameter vắng mặt hoặc giá trị rỗng; khi có default thì parameter không còn bắt buộc.
- Map<String, String> hoặc MultiValueMap<String, String> có thể dùng khi cần lấy nhiều query parameter.

Với giá trị tùy chọn, có thể dùng Optional<T>:

~~~java
@GetMapping("/products")
Flux<ProductView> list(
        @RequestParam(required = false) Optional<String> category) {
    return productService.list(category);
}
~~~

Optional.empty() thể hiện query parameter không có; tránh dùng chuỗi "null" làm dấu hiệu cho dữ liệu vắng mặt.

**Khác biệt cần nhớ:** trong Spring MVC, @RequestParam có thể bao gồm query/form parameters theo mô hình Servlet. Trong Spring WebFlux, @RequestParam tập trung vào query parameters. Với form body, dùng @ModelAttribute, ServerWebExchange.getFormData() hoặc cách đọc body phù hợp.

### 3.4. @RequestHeader và @CookieValue

@RequestHeader bind giá trị từ HTTP header:

~~~java
@GetMapping("/me")
Mono<String> me(
        @RequestHeader("X-Request-Id") String requestId,
        @RequestHeader(name = "Accept-Language", required = false)
        Optional<String> language) {
    return Mono.just("request=" + requestId
        + ", language=" + language.orElse("vi"));
}
~~~

@CookieValue bind giá trị cookie:

~~~java
@GetMapping("/preferences")
Mono<String> preferences(
        @CookieValue(name = "locale", defaultValue = "vi")
        String locale) {
    return Mono.just("locale=" + locale);
}
~~~

Header/cookie cũng được chuyển đổi sang kiểu Java phù hợp khi có converter. Không dùng required=false nếu logic thật sự cần giá trị bắt buộc; hãy định nghĩa default hoặc xử lý Optional rõ ràng.

### 3.5. @RequestBody và HttpEntity

@RequestBody giải mã request body qua HttpMessageReader/codec. Với WebFlux, có thể dùng kiểu giá trị trực tiếp hoặc reactive wrapper tùy nhu cầu:

~~~java
@PostMapping("/orders")
Mono<OrderView> create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Hoặc khi muốn kết hợp body theo pipeline reactive:

~~~java
@PostMapping("/orders")
Mono<OrderView> create(
        @RequestBody Mono<CreateOrderRequest> request) {
    return request.flatMap(orderService::create);
}
~~~

Với body dạng stream:

~~~java
@PostMapping(
    path = "/events/import",
    consumes = "application/stream+json"
)
Mono<ImportSummary> importEvents(
        @RequestBody Flux<EventInput> events) {
    return importService.process(events);
}
~~~

Flux<T> có thể giúp xử lý từng phần tử khi codec và media type hỗ trợ streaming. Không mặc định rằng mọi JSON body đều là stream không giới hạn; kiểu media type và codec quyết định cách đọc. Với body hữu hạn nhỏ, một DTO trực tiếp hoặc Mono<DTO> thường dễ quản lý hơn.

HttpEntity<T> cho phép truy cập cả headers và body:

~~~java
@PostMapping("/echo")
Mono<ResponseEntity<String>> echo(
        HttpEntity<Mono<String>> entity) {
    return entity.getBody()
        .defaultIfEmpty("")
        .map(body -> ResponseEntity.ok()
            .header("X-Received", "true")
            .body(body));
}
~~~

Đây là snippet tích hợp minh họa. Dùng HttpEntity khi cần request headers cùng body trong một tham số; nếu chỉ cần body, @RequestBody rõ ràng hơn.

### 3.6. @RequestPart và multipart

Đối với multipart/form-data, @RequestPart truy cập một phần theo tên:

~~~java
@PostMapping(
    path = "/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    return file.transferTo(
        Paths.get("/tmp/uploads", file.filename())
    ).thenReturn(file.filename());
}
~~~

Đây là snippet minh họa cần import FilePart, Paths và cấu hình đường dẫn lưu trữ phù hợp. Không dùng trực tiếp tên file do client gửi để tạo đường dẫn tin cậy; ứng dụng thực tế phải kiểm tra tên, quyền, dung lượng, loại nội dung và vị trí lưu.

Nếu cần stream multipart ở mức thấp, WebFlux cũng cung cấp Part/Flux<Part> và các API của ServerWebExchange. Chọn cách đọc toàn bộ multipart hay stream từng part theo kích thước dữ liệu và yêu cầu bộ nhớ.

### 3.7. @ModelAttribute

@ModelAttribute dùng data binding để tạo hoặc cập nhật một command object từ các giá trị request được hỗ trợ:

~~~java
record ProductFilter(String category, Integer minPrice) {}

@GetMapping("/products/filter")
Flux<ProductView> filter(@ModelAttribute ProductFilter filter) {
    return productService.filter(filter);
}
~~~

Nếu tên tham số không được gắn annotation và không được resolver khác nhận diện, Spring thường coi kiểu đơn giản là request parameter, còn object phức tạp là model attribute. Nên dùng annotation tường minh trong API quan trọng để hợp đồng dễ đọc.

Data binding có thể đưa giá trị client gửi vào nhiều property của object. Để tránh mass assignment, dùng DTO chỉ chứa trường được phép bind; cấu hình allowed fields hoặc binder phù hợp qua @InitBinder. Không bind trực tiếp entity persistence có nhiều trường nhạy cảm như role, ownerId, balance hoặc audit fields.

### 3.8. @SessionAttribute, @RequestAttribute, Errors và BindingResult

- @SessionAttribute: đọc attribute đã tồn tại trong WebSession.
- @RequestAttribute: đọc attribute đã được filter/interceptor đặt trong request.
- Errors/BindingResult: đọc lỗi data binding/validation của command object.

BindingResult hoặc Errors phải đặt **ngay sau** tham số được validate để Spring gắn lỗi đúng với object:

~~~java
@PostMapping("/profile")
Mono<String> save(
        @Valid @ModelAttribute ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return Mono.just("invalid");
    }
    return profileService.save(form).thenReturn("saved");
}
~~~

Nếu có một tham số khác chen giữa object và BindingResult, Spring không thể liên kết lỗi theo cách này. Với reactive argument wrapper hoặc method validation cấp phương thức, hãy kiểm tra quy tắc của phiên bản Spring đang dùng; không áp dụng máy móc mẫu BindingResult của một chữ ký khác.

## 4. Reactive wrapper được hỗ trợ ở đâu?

Mono<T> và Flux<T> không phải annotation để biến mọi tham số thành bất đồng bộ. Spring WebFlux hỗ trợ reactive types trên những argument cần giải quyết I/O bất đồng bộ, ví dụ:

- @RequestBody Mono<T> hoặc @RequestBody Flux<T>.
- HttpEntity<Mono<T>> và kiểu body reactive tương ứng.
- @RequestPart khi xử lý multipart theo dạng reactive.
- Một số argument như WebSession và Principal có thể được cung cấp qua reactive type.

Với @PathVariable, @RequestParam, @RequestHeader và @CookieValue, thông thường dùng kiểu Java trực tiếp như UUID, String, int, Optional<String>. Không viết Mono<UUID> cho query parameter chỉ vì controller là WebFlux.

Một quy tắc hữu ích:

| Nguồn dữ liệu | Kiểu thường dùng |
| --- | --- |
| Path variable | UUID, String, long... |
| Query/header/cookie | Giá trị Java hoặc Optional<T> |
| JSON body đơn | DTO trực tiếp hoặc Mono<DTO> |
| Body stream | Flux<T> nếu codec/media type hỗ trợ |
| Multipart part | FilePart, Part hoặc reactive part type |
| Request/session context | ServerWebExchange, WebSession, Principal |

**Phiên bản và resolver cụ thể có thể ảnh hưởng các trường hợp đặc biệt.** Ví dụ, tài liệu Spring 5.3 từng mô tả reactive wrapper cho @ModelAttribute; khi nâng cấp lên nhánh mới, hãy đối chiếu bảng argument hiện hành và kiểm thử chữ ký thực tế. Nếu cần BindingResult, kiểu command object không bọc reactive là lựa chọn dễ hiểu và tương thích hơn.

## 5. Chuyển đổi kiểu và data binding

Spring chuyển đổi giá trị đầu vào sang kiểu Java bằng cơ chế conversion/formatting. Ví dụ:

~~~java
@GetMapping("/orders/{id}")
Mono<OrderView> get(
        @PathVariable UUID id,
        @RequestParam(defaultValue = "2026-01-01")
        LocalDate fromDate,
        @RequestParam(defaultValue = "1")
        int page) {
    return orderService.find(id, fromDate, page);
}
~~~

Các dạng chuyển đổi thường gặp:

- String sang số nguyên/số thực.
- String sang UUID.
- String sang enum.
- Ngày giờ theo formatter/converter đã cấu hình.
- Header/cookie/query sang Optional<T> hoặc collection khi resolver hỗ trợ.

Nếu định dạng ngày không phải ISO hoặc enum có quy ước đặc biệt, đăng ký Converter/Formatter phù hợp thay vì parse thủ công ở từng controller. Có thể cấu hình qua WebFluxConfigurer.addFormatters(...).

Lỗi chuyển đổi khác với lỗi validation:

- **Conversion error:** "abc" không thể chuyển sang int.
- **Validation error:** quantity=0 chuyển thành int hợp lệ nhưng vi phạm @Min(1).
- **Decode error:** body JSON sai cú pháp hoặc không tương thích DTO.
- **Missing value:** required parameter/body không có.

Phân loại đúng giúp API trả lỗi có ý nghĩa và tránh gom tất cả thành một thông báo “bad request” khó chẩn đoán.

## 6. Validation: @Valid, @Validated và constraint

### 6.1. Validate command object

Bean Validation đặt constraint trên field/record component:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

record CreateOrderRequest(
    @NotBlank String customer,
    @Min(1) @Max(100) int quantity
) {}
~~~

Trong controller:

~~~java
@PostMapping("/orders")
Mono<OrderView> create(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Khi body được decode thành object, Spring áp dụng validation. Nếu dữ liệu vi phạm constraint, handler có thể không được gọi và Spring phát WebExchangeBindException theo cơ chế validation từng object.

### 6.2. Validate trực tiếp tham số method

Có thể đặt constraint ngay trên tham số như @Min, @Max, @NotBlank:

~~~java
@GetMapping("/orders")
Flux<OrderView> list(
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int limit) {
    return orderService.list(limit);
}
~~~

Điều này là **method validation**. Từ Spring Framework 6.1, WebFlux có hỗ trợ method validation tích hợp cho @RequestMapping methods. Khi method validation được kích hoạt, Spring có thể ném HandlerMethodValidationException.

@Valid tự nó **không phải constraint**; nó yêu cầu validate các constraint lồng trong object. Constraint trực tiếp như @Min hoặc @NotBlank trên method parameter/return value mới là yếu tố kích hoạt method validation.

### 6.3. Phân biệt hai exception validation

| Exception | Trường hợp thường gặp |
| --- | --- |
| WebExchangeBindException | Validation từng command object như @RequestBody, @ModelAttribute, @RequestPart. |
| HandlerMethodValidationException | Validation ở cấp method do constraint trực tiếp trên tham số hoặc return value. |

Một controller có thể phát sinh cả hai loại tùy chữ ký method. Nếu cần chuẩn hóa lỗi, @ControllerAdvice/@ExceptionHandler nên xử lý cả hai, thay vì chỉ bắt WebExchangeBindException.

Ví dụ xử lý lỗi đơn giản:

~~~java
@RestControllerAdvice
class ApiValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<Map<String, String>> handleBinding(
            WebExchangeBindException ex) {
        Map<String, String> errors = new LinkedHashMap<>();
        ex.getFieldErrors().forEach(error ->
            errors.put(error.getField(), error.getDefaultMessage())
        );
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<Map<String, String>> handleMethodValidation(
            HandlerMethodValidationException ex) {
        return ResponseEntity.badRequest().body(
            Map.of("message", "Method argument validation failed")
        );
    }
}
~~~

Đây là snippet minh họa cho Spring 6.1+ và cần import các kiểu validation exception, Map, LinkedHashMap, ResponseEntity. Trong API thực tế, nên chuyển từng ParameterValidationResult thành lỗi có field/path và mã lỗi ổn định, không chỉ trả thông báo chung.

### 6.4. BindingResult và thứ tự tham số

Nếu dùng BindingResult, nó phải nằm ngay sau command object đã validate:

~~~java
@PostMapping("/forms")
Mono<ResponseEntity<?>> submit(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().body(result.getAllErrors()));
    }
    return registrationService.save(form)
        .map(saved -> ResponseEntity.ok(saved));
}
~~~

Với method validation cấp phương thức, Spring chỉ gọi handler nếu các lỗi nằm trên tham số có Errors/BindingResult ngay sau theo quy tắc của method validation. Nếu có lỗi ở một tham số khác không được xử lý qua BindingResult, HandlerMethodValidationException vẫn được phát.

## 7. Giá trị trả về của controller

### 7.1. @ResponseBody và @RestController

Với @RestController, giá trị trả về mặc định được ghi vào response body qua HttpMessageWriter:

~~~java
@GetMapping("/health")
Mono<Map<String, String>> health() {
    return Mono.just(Map.of("status", "UP"));
}
~~~

Với @Controller, cần @ResponseBody nếu muốn ghi object thành response body. Nếu không, một số kiểu như String có thể được hiểu là tên view để render.

### 7.2. Mono<T>: không hoặc một giá trị

Dùng Mono<T> khi endpoint trả một kết quả bất đồng bộ:

~~~java
@GetMapping("/{id}")
Mono<ProductView> get(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

Mono.empty() có thể biểu diễn không có kết quả; cách ánh xạ thành 404, 204 hay body rỗng phụ thuộc hợp đồng API. Đừng giả định Mono.empty() tự động trả 404 trong mọi controller.

### 7.3. Flux<T>: nhiều giá trị

~~~java
@GetMapping
Flux<ProductView> list() {
    return productService.findAll();
}
~~~

WebFlux có thể ghi các phần tử khi chúng đến thay vì gom toàn bộ vào bộ nhớ. Cách encode cụ thể phụ thuộc media type và codec. Với dữ liệu lớn hoặc nguồn dài hạn, streaming giúp tránh buffer toàn bộ danh sách, nhưng client phải chấp nhận response có thể được ghi từng phần.

Nếu lỗi xảy ra sau khi response đã bắt đầu ghi, server có thể không còn khả năng thay response bằng một status/error body hoàn chỉnh. Khi hợp đồng cần quyết định lỗi trước khi gửi response, có thể collect dữ liệu hữu hạn trước, đổi lại chi phí bộ nhớ và độ trễ.

### 7.4. Mono<Void> và void

Mono<Void> biểu diễn thao tác bất đồng bộ chỉ cần báo completion/error, ví dụ xóa hoặc gửi tín hiệu:

~~~java
@DeleteMapping("/{id}")
Mono<Void> delete(@PathVariable UUID id) {
    return productService.deleteById(id);
}
~~~

void cũng có thể được dùng nếu handler đã tự xử lý response qua ServerHttpResponse, ServerWebExchange hoặc @ResponseStatus. Trong reactive code, Mono<Void> thường thể hiện lifecycle rõ hơn vì có thể ghép, xử lý lỗi và cancellation.

### 7.5. ResponseEntity<T>

ResponseEntity<T> cho phép chọn status, headers và body:

~~~java
@GetMapping("/{id}")
Mono<ResponseEntity<ProductView>> get(@PathVariable UUID id) {
    return productService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Có thể dùng ResponseEntity<Mono<T>> hoặc ResponseEntity<Flux<T>> khi status/headers có thể quyết định ngay nhưng body được phát bất đồng bộ:

~~~java
@GetMapping("/stream")
ResponseEntity<Flux<EventView>> stream() {
    Flux<EventView> body = eventService.stream();
    return ResponseEntity.ok()
        .contentType(MediaType.valueOf("application/stream+json"))
        .body(body);
}
~~~

Phân biệt hai dạng:

- Mono<ResponseEntity<T>>: status/headers có thể được quyết định sau khi dữ liệu bất đồng bộ sẵn sàng.
- ResponseEntity<Mono<T>>: status/headers có thể trả về ngay, body tiếp tục phát sau.

### 7.6. Server-Sent Events

Với SSE, dùng text/event-stream:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<EventView>> events() {
    return eventService.stream()
        .map(event -> ServerSentEvent.builder(event).build());
}
~~~

Có thể trả Flux<EventView> mà không bọc ServerSentEvent nếu chỉ cần data event. Dùng wrapper khi cần event id, event name, retry hoặc comment. SSE là stream kéo dài; cần tính đến cancellation khi client ngắt kết nối, heartbeat, giới hạn subscriber và timeout phù hợp.

### 7.7. View và model

Trong controller phục vụ HTML, các kiểu như String, View, Model, Map hoặc Rendering có thể tham gia render view. Ví dụ:

~~~java
@GetMapping("/dashboard")
Mono<Rendering> dashboard() {
    return dashboardService.load()
        .map(data -> Rendering.view("dashboard")
            .modelAttribute("dashboard", data)
            .build());
}
~~~

Đây là snippet tích hợp. Không nhầm String là response body trong mọi controller: với @Controller truyền thống, String thường được hiểu là view name; với @RestController hoặc @ResponseBody, nó được ghi vào body.

## 8. Version compatibility: những mốc cần biết

Chữ ký controller phải tương thích với Spring Framework và dependency đang chạy. Những thay đổi lớn nhất liên quan đến WebFlux, Java baseline, namespace validation và method validation.

| Phiên bản Spring Framework | Điều cần nhớ |
| --- | --- |
| 5.0 | WebFlux được giới thiệu; Java 8 baseline; dùng hệ sinh thái Java EE/javax ở các API tương ứng. |
| 5.2 | Có hỗ trợ Kotlin coroutines cho annotated WebFlux controllers, bao gồm suspend và Flow trong các trường hợp được hỗ trợ. |
| 5.3 | Hoàn thiện nhiều API reactive; RxJava 1/2 bị deprecated từ 5.3.11, hướng tới RxJava 3. |
| 6.0 | Baseline JDK 17 và Jakarta EE 9; đổi nhiều package từ javax.* sang jakarta.*. |
| 6.1 | Bổ sung built-in method validation cho @RequestMapping controllers; HandlerMethodValidationException tham gia mô hình lỗi validation. |
| 6.2 | Duy trì baseline JDK 17 và Jakarta EE 9/10; tiếp tục hỗ trợ các cơ chế controller và validation hiện hành. |
| 7.0 | Baseline JDK 17, Jakarta EE 11; tiếp tục API WebFlux và method validation; cần dùng dependency tương thích với thế hệ mới. |

### 8.1. Spring 5.x: javax và nền tảng Java 8

Ở nhánh Spring 5.x, Bean Validation thường dùng namespace:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

Spring Framework 5.0 là thế hệ giới thiệu WebFlux. Spring 5.3 hỗ trợ Java 8 trở lên theo ma trận phát hành của nhánh 5.3. Kotlin coroutine support có từ Spring 5.2; khi dùng cần thêm dependency Kotlin/coroutines phù hợp.

Nếu dự án còn dùng Spring 5.x, không thể chỉ đổi import sang jakarta.validation rồi kỳ vọng tương thích với provider cũ. Kiểm tra version Bean Validation provider, servlet/container và các dependency liên quan.

### 8.2. Spring 6.x: JDK 17 và Jakarta namespace

Spring Framework 6.0 nâng baseline lên JDK 17 và Jakarta EE 9. Import validation chuyển thành:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
~~~

Đây là thay đổi source-level quan trọng khi nâng cấp từ Spring 5.x. Các package javax.servlet, javax.validation, javax.persistence không thể thay thế tùy tiện cho jakarta.* trong dependency Jakarta mới.

Spring 6.0 và 6.2 đều yêu cầu JDK 17; chọn container và provider phù hợp với Jakarta EE baseline mà nhánh đó hỗ trợ.

### 8.3. Spring 6.1: built-in method validation

Từ Spring Framework 6.1, WebFlux có method validation tích hợp cho @RequestMapping methods. Khi muốn dùng cơ chế tích hợp này, **không đặt class-level @Validated trên controller**. Nếu có @Validated ở cấp lớp, method validation được thực hiện qua AOP proxy theo cơ chế cũ.

Trước 6.1, method validation thường cần cấu hình AOP như @Validated và MethodValidationPostProcessor; validation từng object qua @Valid vẫn là một cơ chế riêng. Khi nâng cấp, kiểm tra exception handler và test lại vì cách validation được kích hoạt/phân loại có thể khác.

### 8.4. Spring 7.0

Spring Framework 7.0 giữ baseline JDK 17 và nâng baseline Jakarta EE lên thế hệ 11. Với dự án mới, hãy kiểm tra các phiên bản Spring Boot, JDK, servlet container, validation provider và test framework cùng lúc; không chỉ nâng spring-webflux đơn lẻ.

Ở thời điểm biên soạn, tài liệu chính thức hiển thị Spring Framework 7.0.x và 6.2.x là các nhánh stable; patch version thay đổi theo thời gian. Dùng trang release/support chính thức để xác nhận patch đang được hỗ trợ thay vì chép một số version cố định từ bài học cũ.

### 8.5. Quản lý version qua Spring Boot BOM

Trong ứng dụng Spring Boot, ưu tiên để Spring Boot BOM/dependency management chọn bộ Spring Framework, Reactor, Jackson, validation provider và test dependencies tương thích. Tránh tự ghim một version spring-webflux khác với spring-core hoặc spring-web.

Nếu dùng Gradle độc lập, phải quản lý đồng bộ toàn bộ Spring Framework modules cùng version. Kiểm tra dependency tree khi gặp NoSuchMethodError, ClassNotFoundException, NoClassDefFoundError hoặc lỗi linkage sau khi nâng cấp.

## 9. Chương trình Spring Boot WebFlux chạy được

Ví dụ dưới đây dùng Java 17 và Spring Boot 3.3.5, dựa trên Spring Framework 6.1.x. Nó minh họa:

- @PathVariable UUID và @RequestParam.
- @RequestHeader và @CookieValue dạng optional.
- @Valid @RequestBody với Jakarta Bean Validation.
- Method validation trên tham số query từ Spring 6.1.
- Giá trị trả về Mono<ResponseEntity<T>>, Flux<T> và Mono<ResponseEntity<Void>>.

### 9.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các version được ghim để ví dụ có thể tái hiện; Spring Boot quản lý phiên bản Spring Framework 6.1.x tương thích. Với ứng dụng mới, chọn phiên bản Spring Boot còn được hỗ trợ và để BOM quản lý dependencies.

### 9.2. src/main/java/demo/BindingDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
~~~

### 9.3. src/main/java/demo/OrderController.java

~~~java
package demo;

import java.net.URI;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record CreateOrderRequest(
    @NotBlank String customer,
    @Min(1) @Max(100) int quantity
) {}

record OrderView(UUID id, String customer, int quantity) {}

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final ConcurrentMap<UUID, OrderView> orders =
        new ConcurrentHashMap<>();

    @GetMapping
    Flux<OrderView> list(
            @RequestParam(defaultValue = "20")
            @Min(1) @Max(100) int limit) {
        return Flux.fromIterable(orders.values())
            .take(limit);
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable UUID id,
            @RequestHeader(
                name = "X-Request-Id", required = false
            ) Optional<String> requestId,
            @CookieValue(
                name = "locale", required = false
            ) Optional<String> locale) {

        return Mono.justOrEmpty(orders.get(id))
            .map(order -> {
                ResponseEntity.BodyBuilder response =
                    ResponseEntity.ok();

                requestId.ifPresent(value ->
                    response.header("X-Request-Id", value));
                locale.ifPresent(value ->
                    response.header("Content-Language", value));

                return response.body(order);
            })
            .defaultIfEmpty(
                ResponseEntity.<OrderView>notFound().build()
            );
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<OrderView>> create(
            @Valid @RequestBody CreateOrderRequest request) {

        return Mono.fromSupplier(() -> {
            UUID id = UUID.randomUUID();
            OrderView saved = new OrderView(
                id, request.customer(), request.quantity()
            );
            orders.put(id, saved);

            return ResponseEntity
                .created(URI.create("/api/orders/" + id))
                .body(saved);
        });
    }

    @DeleteMapping("/{id}")
    Mono<ResponseEntity<Void>> delete(@PathVariable UUID id) {
        return Mono.fromSupplier(() -> {
            OrderView removed = orders.remove(id);
            return removed == null
                ? ResponseEntity.<Void>notFound().build()
                : ResponseEntity.noContent().build();
        });
    }
}
~~~

Đây là ứng dụng demo dùng map trong bộ nhớ, không phải thiết kế persistence production. ConcurrentHashMap bảo vệ thao tác map cơ bản khi nhiều request truy cập đồng thời; nó không thay thế transaction/database.

Chú ý method list: @Min và @Max đặt trực tiếp trên tham số là method validation của Spring 6.1+. Controller không có class-level @Validated, nên có thể dùng built-in method validation. @Valid trên body lại minh họa validation từng command object.

### 9.4. Chạy ứng dụng và gọi thử

Khởi động:

~~~bash
gradle bootRun
~~~

Hoặc Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Liệt kê tối đa 10 đơn hàng:

~~~bash
curl -i "http://localhost:8080/api/orders?limit=10"
~~~

Truy vấn một UUID đã tồn tại:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  -H "Cookie: locale=vi" \
  http://localhost:8080/api/orders/00000000-0000-0000-0000-000000000001
~~~

ID trên chỉ là ví dụ định dạng; ứng dụng demo tạo UUID ngẫu nhiên khi POST nên cần dùng ID nhận từ response thực tế.

Tạo đơn hàng hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":3}'
~~~

Body response có UUID được tạo ngẫu nhiên, vì vậy không có stdout cố định cho toàn bộ lệnh. Response thành công có status 201 Created và header Location.

Thử validation body không hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":" ","quantity":0}'
~~~

Với validation được cấu hình, request bị từ chối trước khi tạo đơn hàng và thường trả 400 Bad Request.

Thử method validation:

~~~bash
curl -i "http://localhost:8080/api/orders?limit=0"
~~~

limit=0 vi phạm @Min(1) nên method validation từ chối request. Đây là điểm phụ thuộc Spring Framework 6.1+ trong ví dụ.

## 10. Kiểm thử bằng WebTestClient

Tạo src/test/java/demo/OrderControllerTest.java:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void invalidBodyIsRejected() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"customer\":\" \",\"quantity\":0}")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void methodConstraintRejectsInvalidLimit() {
        client.get()
            .uri("/api/orders?limit=0")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void invalidUuidCannotBindToPathVariable() {
        client.get()
            .uri("/api/orders/not-a-uuid")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void validEmptyListReturnsSuccess() {
        client.get()
            .uri("/api/orders?limit=10")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc ./gradlew test / .\gradlew.bat test. Các test kiểm tra:

- Bean Validation trên request body.
- Method validation trên query parameter.
- Conversion String sang UUID.
- Return value Flux<OrderView> được encode thành JSON response.

@WebFluxTest tạo slice test cho controller. Nếu controller có service dependency, cung cấp mock bean phù hợp hoặc dùng @SpringBootTest cùng WebTestClient khi cần kiểm thử đầy đủ application context.

## 11. Các vấn đề về phiên bản và migration

### 11.1. Lỗi javax.validation và jakarta.validation

Triệu chứng thường gặp khi nâng cấp:

- ClassNotFoundException: javax.validation...
- NoClassDefFoundError: jakarta.validation...
- Provider validation không được tìm thấy hoặc annotation không được nhận diện.

Cách xử lý:

- Spring 5.x thường dùng javax.validation.*.
- Spring 6.x/7.x dùng jakarta.validation.*.
- Chọn Hibernate Validator/provider tương thích namespace.
- Để Spring Boot BOM quản lý phiên bản starter và provider.
- Không để cả hai namespace xuất hiện lẫn lộn trong DTO/controller mà không có lý do rõ ràng.

### 11.2. @Validated ở cấp lớp trong Spring 6.1+

Nếu controller có:

~~~java
@Validated
@RestController
class ProductController {
    // ...
}
~~~

method validation được thực hiện qua AOP proxy. Để dùng built-in method validation của Spring Framework 6.1 cho @RequestMapping controllers, bỏ class-level @Validated khỏi controller và dùng cơ chế tích hợp. Nếu cần method validation AOP theo thiết kế cũ, hãy chủ động cấu hình MethodValidationPostProcessor và hiểu rõ phạm vi proxy.

### 11.3. Không dùng javax.servlet trong WebFlux

Spring WebFlux dùng abstraction reactive như ServerWebExchange, ServerHttpRequest, ServerHttpResponse. Các kiểu Servlet như HttpServletRequest không phải tham số controller WebFlux chuẩn. Nếu một ứng dụng dùng đồng thời Spring MVC và WebFlux, phải xác định đúng web application type và programming model cho từng controller.

### 11.4. RxJava và thư viện reactive

WebFlux dùng Reactor Mono/Flux nội bộ và có thể thích nghi với các Reactive Streams publisher/library được hỗ trợ. RxJava 1/2 đã bị deprecated trong Spring Framework 5.3.11; với code mới, ưu tiên Reactor hoặc RxJava 3 theo compatibility matrix của phiên bản Spring. Đừng giả định một type từ thư viện reactive bất kỳ tự động được hỗ trợ nếu không có adapter tương ứng.

### 11.5. Kotlin coroutine

Spring Framework 5.2 đã hỗ trợ coroutine cho WebFlux annotated controllers, bao gồm suspend functions và Flow/Deferred trong các trường hợp được hỗ trợ. Đây là tính năng Kotlin và cần dependency kotlinx-coroutines/Spring Kotlin support phù hợp; không áp dụng trực tiếp cho Java controller.

Ví dụ Kotlin minh họa:

~~~kotlin
@GetMapping("/orders/{id}")
suspend fun get(@PathVariable id: UUID): OrderView =
    orderService.findById(id)
~~~

Đây là snippet Kotlin, không phải mã Java. Với stream, có thể dùng Flow<T> theo adapter coroutine được Spring hỗ trợ.

## 12. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng Mono<String> cho @RequestParam đơn giản | Wrapper không phù hợp resolver của scalar argument | Dùng String, UUID, int, Optional<T> |
| Dùng HttpServletRequest trong WebFlux | Sai programming model và không tương thích handler chuẩn | Dùng ServerHttpRequest hoặc ServerWebExchange |
| Nhầm query parameter với form body | Không bind được dữ liệu form như mong đợi | Dùng @ModelAttribute hoặc API form data |
| Nhận entity persistence trực tiếp qua @ModelAttribute | Rủi ro mass assignment vào trường nhạy cảm | Dùng request DTO và allowed fields |
| Nghĩ @Valid luôn kích hoạt method validation | @Valid tự nó không phải constraint | Phân biệt object validation và method-level constraints |
| Chỉ bắt WebExchangeBindException | Có thể bỏ sót HandlerMethodValidationException | Xử lý cả hai khi dùng Spring 6.1+ |
| Đặt BindingResult cách xa object | Spring không gắn lỗi với đúng tham số | Đặt ngay sau argument được validate |
| Nghĩ Flux<T> luôn buffer toàn bộ response | Có thể hiểu sai streaming và memory | Xem media type/codec; stream theo nhu cầu |
| Dùng String nghĩ luôn là body text | Trong @Controller, có thể là view name | Dùng @ResponseBody/@RestController khi cần body |
| Trả Mono.empty() và mong luôn có HTTP 404 | Empty không tự định nghĩa status | Dùng switchIfEmpty, ResponseEntity hoặc exception mapping |
| Đổi import javax sang jakarta mà không nâng provider | Lỗi linkage hoặc validation không chạy | Đồng bộ Spring, provider và namespace |
| Dùng method validation mới trên Spring 6.0 | API/hành vi chưa có ở phiên bản đó | Dùng cơ chế AOP tương thích hoặc nâng lên 6.1+ |
| Nâng riêng spring-webflux | Các Spring modules có version lệch | Dùng Spring Boot BOM hoặc quản lý đồng bộ |
| Dùng @Validated class-level mà mong built-in 6.1 | Validation đi qua AOP proxy | Bỏ class-level @Validated khi chọn built-in method validation |

## 13. Checklist thiết kế một controller method

Trước khi viết chữ ký controller, hãy tự hỏi:

1. **Nguồn dữ liệu ở đâu?** Path, query, header, cookie, body, multipart, session hay request attribute?
2. **Kiểu Java phù hợp là gì?** Giá trị scalar, Optional<T>, DTO, Mono<T> hay Flux<T>?
3. **Có cần conversion không?** UUID, ngày giờ, enum và kiểu custom đã có converter/formatter phù hợp chưa?
4. **Body dùng codec nào?** Content-Type, DTO, HttpMessageReader, streaming và dung lượng có phù hợp?
5. **Validation ở cấp nào?** @Valid cho object, constraint trực tiếp cho method, BindingResult hay exception handler?
6. **Spring version có hỗ trợ không?** Đặc biệt namespace javax/jakarta, built-in method validation và reactive argument type.
7. **Return value có đúng hợp đồng HTTP?** Body, status, headers, view, stream, SSE hay completion-only?
8. **Có nguy cơ chặn thread không?** Không gọi block() hoặc tự subscribe() trong handler để chờ/kích hoạt công việc.
9. **Response có thể lỗi sau khi đã commit không?** Nếu streaming, xác định client sẽ xử lý partial response thế nào.
10. **Đã test binding và version-specific behavior chưa?** Dùng WebTestClient kiểm tra conversion, validation, status, headers, content type và response body.

**Ghi nhớ:** method argument mô tả Spring lấy và chuyển đổi dữ liệu request như thế nào; return value mô tả Spring ghi body, status, headers, stream hoặc view ra sao. Mono/Flux được dùng ở những vị trí phù hợp với I/O reactive, không phải bọc mọi tham số. Khi nâng Spring, đặc biệt chú ý JDK baseline, javax/jakarta và thay đổi method validation từ 6.1.

## Tài liệu tham khảo

- Spring Framework — WebFlux Handler Methods: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html
- Spring Framework — Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — Validation in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework — WebFlux Configuration and Validators: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework 5.3 — Web on Reactive Stack: https://docs.spring.io/spring-framework/docs/5.3.x/reference/html/web-reactive.html
- Spring Framework 6.0 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.0-Release-Notes
- Spring Framework 7.0 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes
- Spring Framework Versions and Support: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions
