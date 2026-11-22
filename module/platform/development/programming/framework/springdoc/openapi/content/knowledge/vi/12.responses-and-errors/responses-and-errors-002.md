# Suy luận schema từ kiểu trả về của handler

Khi tạo đặc tả OpenAPI từ controller Spring Boot, springdoc-openapi thường dựa vào kiểu trả về của handler để suy luận nội dung response. Một phương thức trả về DTO có thể tạo schema object; một phương thức trả về danh sách DTO có thể tạo schema array; một phương thức trả về ResponseEntity<OrderResponse> cho biết phần body có kiểu OrderResponse. Nhờ đó, nhiều endpoint có thể được mô tả mà không cần viết lại toàn bộ schema bằng annotation.

Việc suy luận chỉ chính xác khi chữ ký Java thể hiện đúng dữ liệu mà API thực sự gửi về client. Kiểu trả về không tự mô tả mọi mã trạng thái, mọi nhánh lỗi hoặc toàn bộ header của response. Với những trường hợp có nhiều kết quả, generic bị mất, body rỗng hoặc kiểu dữ liệu đặc biệt, cần bổ sung metadata bằng @ApiResponse, @Content và @Schema.

## 1. Cơ chế suy luận response schema

springdoc-openapi đọc mapping của Spring, chữ ký handler, kiểu Java, annotation OpenAPI và cấu hình liên quan để tạo Operation trong tài liệu. Với endpoint REST, kiểu trả về thường được dùng để xác định schema của response thành công.

Luồng xử lý có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Handler method trong controller] --> B[Đọc kiểu trả về Java]
    B --> C{Có wrapper hoặc kiểu generic?}
    C -->|Có| D[Phân tích kiểu body bên trong]
    C -->|Không| E[Phân tích kiểu trả về trực tiếp]
    D --> F[Tạo schema OpenAPI]
    E --> F
    F --> G[Đưa schema vào response content]
    G --> H[Kiểm tra /v3/api-docs]
    H --> I[Đối chiếu với JSON runtime]
~~~

Điều cần phân biệt là Spring quyết định cách xử lý giá trị trả về khi request chạy, còn springdoc mô tả hành vi đó trong hợp đồng OpenAPI. Với REST controller, giá trị trả về thường được chuyển thành response body thông qua HttpMessageConverter của Spring MVC hoặc HttpMessageWriter của WebFlux. springdoc dùng thông tin kiểu và annotation để mô tả hình dạng dữ liệu đó.

Schema trả về thường được đặt trong response content của operation, ví dụ:

~~~yaml
responses:
  '200':
    description: Tìm thấy đơn hàng
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

Nếu schema object được dùng lại, nó có thể nằm trong components.schemas và được operation tham chiếu bằng $ref. Với kiểu đơn giản, schema có thể nằm trực tiếp trong response content.

## 2. Trả về DTO trực tiếp

Đây là trường hợp dễ suy luận nhất. Controller trả về một DTO cụ thể, springdoc đọc các thuộc tính của DTO và tạo schema tương ứng.

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse getById(@PathVariable long id) {
        return orderService.getById(id);
    }
}
~~~

DTO:

~~~java
public class OrderResponse {

    private Long id;
    private String orderNumber;
    private BigDecimal total;
    private String status;

    // Getter và setter được lược bỏ.
}
~~~

Vì controller dùng @RestController, đối tượng OrderResponse được ghi vào response body. springdoc có thể suy ra schema object với các thuộc tính id, orderNumber, total và status. Nếu DTO có nested object, enum hoặc collection, schema có thể tham chiếu đến các schema thành phần tương ứng.

Nếu dùng @Controller thay cho @RestController, cần đánh dấu method bằng @ResponseBody khi muốn trả dữ liệu trong HTTP response. Trong controller MVC thông thường, một giá trị String có thể được hiểu là tên view thay vì response body. Vì vậy, cần xét cả annotation của controller và method khi đọc chữ ký trả về.

## 3. Trả về kiểu đơn giản, chuỗi và collection

Kiểu Java trả về ảnh hưởng trực tiếp đến hình dạng schema:

| Kiểu trả về | Hình dạng schema thường gặp | Ví dụ JSON |
| --- | --- | --- |
| String | string | "Đơn hàng đã tạo" |
| Integer, Long | integer | 42 |
| BigDecimal, Double | number | 125000.50 |
| Boolean | boolean | true |
| DTO | object | {"id":42,"status":"NEW"} |
| List<OrderResponse> | array có items là OrderResponse | [{"id":42,"status":"NEW"}] |
| OrderResponse[] | array có items là OrderResponse | [{"id":42,"status":"NEW"}] |
| Map<String, String> | object với thuộc tính động | {"region":"north"} |

Ví dụ endpoint trả danh sách:

~~~java
@GetMapping
public List<OrderResponse> findAll() {
    return orderService.findAll();
}
~~~

Schema được suy luận là array, trong đó items mô tả OrderResponse. Không nên khai báo response thành object chỉ vì service nội bộ trả về một collection; hãy kiểm tra JSON thực tế để biết API đang trả mảng trực tiếp hay một object wrapper chứa danh sách.

Ví dụ Map có key động:

~~~java
@GetMapping("/statistics")
public Map<String, Long> statistics() {
    return orderService.countByStatus();
}
~~~

Kết quả có thể là object với các key như NEW, CONFIRMED hoặc CANCELLED. Nếu tập key cố định và có ý nghĩa nghiệp vụ, DTO với thuộc tính cụ thể thường tạo tài liệu dễ hiểu hơn Map tổng quát.

Một kiểu String trong @RestController là response body dạng chuỗi. Nó không mặc nhiên là JSON object hoặc JSON string có cấu trúc phức tạp. Hãy kiểm tra Content-Type và cách converter ghi dữ liệu; nếu endpoint trả text/plain, cần mô tả media type tương ứng.

## 4. Suy luận body từ ResponseEntity<T>

ResponseEntity<T> biểu diễn toàn bộ response HTTP, bao gồm status, headers và body. Kiểu tham số T cho biết kiểu body. Vì vậy, springdoc có thể suy luận schema từ T thay vì tạo schema cho bản thân lớp ResponseEntity.

~~~java
@GetMapping("/{id}")
public ResponseEntity<OrderResponse> getById(@PathVariable long id) {
    OrderResponse order = orderService.getById(id);
    return ResponseEntity.ok()
        .header("X-Order-Source", "primary")
        .body(order);
}
~~~

Trong ví dụ, body có schema OrderResponse. Header X-Order-Source và status HTTP là những phần khác của response; chúng không trở thành thuộc tính của OrderResponse.

ResponseEntity giúp handler chọn status theo kết quả xử lý:

~~~java
@GetMapping("/{id}")
public ResponseEntity<OrderResponse> getById(@PathVariable long id) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Kiểu trả về vẫn cho biết body thành công là OrderResponse, nhưng không mô tả đầy đủ mọi nhánh status. Trường hợp không tìm thấy trả 404 và không có body; trường hợp tìm thấy trả 200 cùng body. Hãy khai báo các response riêng bằng @ApiResponses để hợp đồng thể hiện cả hai kết quả.

## 5. Generic wrapper và kiểu lồng nhau

Nhiều hệ thống dùng một wrapper chung để chuẩn hóa response:

~~~java
public class ApiEnvelope<T> {

    private boolean success;
    private T data;
    private String traceId;

    // Getter và setter được lược bỏ.
}
~~~

Nếu controller khai báo đầy đủ tham số kiểu:

~~~java
@GetMapping("/{id}")
public ApiEnvelope<OrderResponse> getById(@PathVariable long id) {
    return ApiEnvelope.success(orderService.getById(id));
}
~~~

springdoc có thể suy luận cấu trúc wrapper và kiểu của data từ ApiEnvelope<OrderResponse>. Schema dự kiến có các trường success, data và traceId; thuộc tính data tham chiếu hoặc mô tả OrderResponse.

Các generic lồng nhau cũng có thể được thể hiện khi chữ ký giữ đầy đủ kiểu:

~~~java
@GetMapping
public ResponseEntity<ApiEnvelope<List<OrderResponse>>> findAll() {
    List<OrderResponse> orders = orderService.findAll();
    return ResponseEntity.ok(ApiEnvelope.success(orders));
}
~~~

Kiểu body trong ví dụ là ApiEnvelope chứa danh sách OrderResponse. Đây là lý do nên giữ kiểu generic cụ thể ở chữ ký public của controller.

Nếu khai báo raw type hoặc wildcard:

~~~java
public ResponseEntity<?> getById(@PathVariable long id) {
    return ResponseEntity.ok(orderService.findById(id));
}
~~~

springdoc không có đủ thông tin tĩnh để biết body thực tế thuộc DTO nào. Kiểu Object hoặc schema quá tổng quát có thể xuất hiện. Nếu API thực sự trả một kiểu ổn định, hãy khai báo kiểu đó trong chữ ký hoặc mô tả tường minh bằng @ApiResponse và @Schema(implementation = OrderResponse.class).

Nếu body có thể thuộc nhiều kiểu khác nhau, hãy mô tả union bằng oneOf hoặc anyOf khi phù hợp. Không chọn tùy tiện một implementation duy nhất nếu runtime có thể trả nhiều cấu trúc JSON không tương thích.

## 6. Kiểu trả về Optional và kiểu bất đồng bộ

Một số handler trả kết quả có thể vắng mặt hoặc được tạo bất đồng bộ. Cần phân biệt wrapper biểu diễn trạng thái tính toán với kiểu dữ liệu cuối cùng gửi cho client.

Với Optional, nên xác định rõ hành vi HTTP khi không có dữ liệu. Ví dụ:

~~~java
@GetMapping("/{id}")
public ResponseEntity<OrderResponse> getById(@PathVariable long id) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Optional trong tầng service không cần xuất hiện trong response schema nếu controller đã chuyển nó thành ResponseEntity<OrderResponse>. Client nhận 200 với OrderResponse hoặc 404 không có body.

Spring MVC hỗ trợ các kiểu trả về bất đồng bộ như CompletableFuture<T>, CompletionStage<T>, Callable<T> và DeferredResult<T>. Spring xử lý kết quả khi tác vụ hoàn tất; springdoc thường mô tả kiểu giá trị cuối cùng thay vì một object CompletableFuture. Ví dụ:

~~~java
@GetMapping("/{id}")
public CompletableFuture<OrderResponse> getById(@PathVariable long id) {
    return orderService.findByIdAsync(id);
}
~~~

Hợp đồng API vẫn là response chứa OrderResponse. Wrapper bất đồng bộ là chi tiết thực thi.

Kết quả cụ thể phụ thuộc loại wrapper, stack Spring MVC/WebFlux và phiên bản springdoc. Khi dùng wrapper tùy chỉnh hoặc kiểu reactive lồng nhau, hãy kiểm tra OpenAPI JSON được sinh thay vì giả định mọi wrapper đều được tự động tháo lớp giống nhau.

## 7. Mono, Flux và response dạng stream

Trong Spring WebFlux, handler có thể trả về Mono<T> hoặc Flux<T>. Mono thường đại diện cho không hoặc một giá trị; Flux đại diện cho nhiều giá trị. Spring hỗ trợ cả response được ghi như một giá trị JSON và response stream tùy media type.

Ví dụ trả một đối tượng:

~~~java
@GetMapping("/{id}")
public Mono<OrderResponse> getById(@PathVariable long id) {
    return orderService.findById(id);
}
~~~

Ví dụ trả danh sách đã được gom thành một response:

~~~java
@GetMapping
public Flux<OrderResponse> findAll() {
    return orderService.findAll();
}
~~~

Với Flux, cách truyền phụ thuộc media type và cách Spring ghi response. Nếu client yêu cầu application/json, nhiều giá trị có thể được gom và ghi thành một JSON array. Nếu endpoint dùng text/event-stream hoặc một media type dạng stream, dữ liệu được phát theo từng sự kiện hoặc từng phần tử. Hai cách này có hợp đồng khác nhau.

Vì vậy, khi dùng Flux, cần khai báo produces rõ ràng và kiểm tra response thực tế. Với Server-Sent Events, có thể dùng Flux<ServerSentEvent<OrderEvent>> và media type text/event-stream. Schema của event data, cấu trúc khung stream và cách client tiêu thụ phải được mô tả đủ rõ; không nên mô tả một stream vô hạn như một JSON array thông thường.

Spring MVC cũng hỗ trợ ResponseBodyEmitter, SseEmitter và StreamingResponseBody. Các kiểu này phát dữ liệu theo luồng hoặc ghi trực tiếp vào OutputStream. Chúng cần mô tả media type và nội dung cụ thể bằng annotation response nếu suy luận tự động không phản ánh chính xác cách truyền.

## 8. void, ResponseEntity<Void> và response không có body

Handler có kiểu void hoặc ResponseEntity<Void> thường không trả JSON body:

~~~java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    orderService.delete(id);
}
~~~

Hoặc dùng ResponseEntity:

~~~java
@DeleteMapping("/{id}")
@ApiResponse(
    responseCode = "204",
    description = "Đã xóa đơn hàng",
    content = @Content
)
public ResponseEntity<Void> delete(@PathVariable long id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

Trong hợp đồng, response 204 thường không có content. springdoc FAQ hướng dẫn khai báo response rỗng bằng content = @Content hoặc content = @Content(schema = @Schema(hidden = true)).

Không gán schema object cho response 204 nếu server không gửi body. Cũng cần phân biệt status 200 với body rỗng và status 204 không có content: đây là các cam kết HTTP khác nhau.

Một method void không tự quyết định mọi trường hợp status. Trong Spring MVC, void có thể biểu thị response đã được xử lý nếu có ServletResponse, OutputStream, @ResponseStatus hoặc cơ chế tương ứng; nếu không, nó có thể là response body rỗng trong REST controller hoặc hành vi view trong controller MVC. Hãy kiểm tra annotation và hành vi runtime.

## 9. Media type và hình dạng response

Kiểu trả về cho biết cấu trúc dữ liệu; media type cho biết cách biểu diễn nội dung. Hai phần này cần khớp với nhau.

Ví dụ trả JSON:

~~~java
@GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}
~~~

Ví dụ trả văn bản:

~~~java
@GetMapping(value = "/health/text", produces = MediaType.TEXT_PLAIN_VALUE)
public String healthText() {
    return "UP";
}
~~~

Với file tải xuống, handler có thể trả Resource hoặc ResponseEntity<Resource>. Nhiều toolchain OpenAPI 3.0 mô tả nội dung file bằng kiểu string với format binary, cùng media type phù hợp như application/octet-stream hoặc loại file cụ thể. Khi xuất OpenAPI 3.1, hãy kiểm tra quy ước schema file mà phiên bản springdoc và công cụ validator đang dùng hỗ trợ. Với file upload/download, hãy khai báo rõ content thay vì chỉ dựa vào kiểu Java.

Nếu cùng endpoint hỗ trợ nhiều media type, OpenAPI có thể mô tả nhiều mục trong content của cùng response. Đây vẫn là một operation với nhiều cách biểu diễn response, không nhất thiết là nhiều schema khác nhau. Cần bảo đảm converter của Spring thực sự hỗ trợ các media type đã công bố.

## 10. Suy luận không thay thế việc mô tả các status và lỗi

Kiểu trả về chủ yếu giúp suy luận schema của response body. Một handler có thể trả 200, 201, 202, 204, 400, 404 hoặc 409 tùy điều kiện xử lý. Không thể biết đầy đủ mọi nhánh này chỉ từ một kiểu DTO.

Ví dụ mô tả nhiều kết quả:

~~~java
@PostMapping
@Operation(summary = "Tạo đơn hàng")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đã tạo đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu đầu vào không hợp lệ",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Đơn hàng bị trùng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderResponse created = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Trong ví dụ, kiểu trả về cho biết body thành công là OrderResponse. Các response lỗi dùng ApiError và được khai báo riêng.

Với @ControllerAdvice, springdoc có thể bổ sung các response lỗi dùng chung. Tài liệu springdoc khuyến nghị khai báo mã HTTP bằng @ResponseStatus trên các method xử lý exception để sinh tài liệu tự động. Thuộc tính springdoc.override-with-generic-response mặc định bật việc thêm response từ ControllerAdvice vào các operation được tạo; cần kiểm tra output để tránh response chung không phù hợp với endpoint cụ thể.

## 11. Khi nào cần override response schema?

Nếu kiểu trả về không đủ cụ thể hoặc không phản ánh JSON công khai, có thể khai báo response tường minh:

~~~java
@GetMapping("/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Thông tin đơn hàng",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public ResponseEntity<?> getById(@PathVariable long id) {
    return ResponseEntity.ok(orderService.findResponse(id));
}
~~~

Nếu response là danh sách nhưng chữ ký không giữ kiểu phần tử, có thể dùng @ArraySchema:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Danh sách đơn hàng",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
)
~~~

Khi đã có kiểu trả về cụ thể, nên ưu tiên để springdoc suy luận. Override chỉ nên dùng khi hợp đồng thực sự khác với kiểu Java được khai báo hoặc khi thông tin generic không còn đủ.

Nếu cần ẩn schema response hoặc mô tả response không có content, có thể dùng:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Không có nội dung trả về",
    content = @Content
)
~~~

hoặc:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Không có nội dung trả về",
    content = @Content(schema = @Schema(hidden = true))
)
~~~

## 12. Kiểm tra schema được suy luận

Sau khi khởi động ứng dụng, mở endpoint mặc định /v3/api-docs hoặc endpoint đã cấu hình. Tìm operation tương ứng và kiểm tra:

1. Response code được công bố có đúng với @ResponseStatus và các annotation @ApiResponse hay không; với ResponseEntity có nhiều nhánh status, hãy khai báo rõ từng mã có thể trả về.
2. Schema phản ánh body thực tế: object, array, primitive, map hoặc wrapper.
3. Generic type có được giữ đúng trong các lớp lồng nhau không.
4. Response không có body có content rỗng, không có schema giả định.
5. Media type trong content khớp với produces và converter thực tế.
6. Các response lỗi quan trọng đã được khai báo và có schema đúng.
7. Không có component hoặc $ref sai do kiểu wrapper hoặc cấu hình override.

Có thể tải tài liệu bằng curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Sau đó gọi endpoint thật để kiểm tra JSON, status và headers. Đặc tả OpenAPI là hợp đồng được công bố; nó không thể chứng minh response runtime luôn tuân thủ hợp đồng. Nên có kiểm thử tích hợp cho các nhánh thành công, lỗi, body rỗng và các media type khác nhau.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Schema response là Object | Handler dùng raw type, Object hoặc wildcard | Giữ kiểu generic cụ thể hoặc khai báo implementation |
| Wrapper có data nhưng schema data không rõ | Kiểu generic T không được giữ ở chữ ký public | Khai báo ApiEnvelope<OrderResponse> thay vì raw ApiEnvelope |
| ResponseEntity bị mô tả như object | Nhầm wrapper HTTP với body payload | Kiểm tra phiên bản springdoc và response content; schema mong đợi là kiểu T |
| List được mô tả thành object | Chữ ký trả về wrapper object hoặc kiểu collection bị khai báo không rõ | Kiểm tra JSON runtime và khai báo array schema khi cần |
| Status lỗi không xuất hiện trong tài liệu | Chỉ dựa vào kiểu trả về thành công | Khai báo @ApiResponse cho từng mã lỗi quan trọng |
| Response 204 có schema body | Annotation response mô tả content dù runtime không gửi body | Dùng content = @Content và kiểm tra status thực tế |
| String bị hiểu là view | Dùng @Controller mà thiếu @ResponseBody | Dùng @RestController hoặc thêm @ResponseBody nếu muốn trả body |
| Flux hiển thị như danh sách trong khi API phát SSE | Media type stream không được mô tả đúng | Khai báo produces = text/event-stream và kiểm tra cấu trúc event |
| File response bị mô tả thành object | Chưa khai báo media type và schema binary | Mô tả content với application/octet-stream và schema string/binary |
| Response lỗi từ ControllerAdvice bị thêm vào mọi operation | Generic response được áp dụng toàn cục | Kiểm tra springdoc.override-with-generic-response và cấu hình phạm vi lỗi |

## 14. Nguyên tắc thiết kế

Hãy khai báo kiểu trả về cụ thể ở controller để springdoc có đủ thông tin tạo schema. Dùng DTO công khai thay cho entity hoặc Object nếu dữ liệu trả về cần một cấu trúc ổn định. Giữ generic type trong wrapper và ResponseEntity để mô tả đúng kiểu body. Với body rỗng, dùng void hoặc ResponseEntity<Void> và khai báo status/content phù hợp. Với nhiều status, lỗi, media type hoặc stream, bổ sung metadata để hợp đồng phản ánh tất cả kết quả mà client có thể nhận.

Cuối cùng, đối chiếu đặc tả sinh ra với response runtime. Chữ ký Java giúp springdoc suy luận schema, nhưng chính JSON, status, headers và media type được ứng dụng gửi ra mới là dữ liệu mà client sử dụng.

## 15. Tài liệu tham khảo chính thức

- [springdoc-openapi — Features v2](https://springdoc.org/v2/features.html) — tích hợp REST, xử lý lỗi qua @ControllerAdvice và @ResponseStatus, functional endpoints.
- [springdoc-openapi — FAQ v2](https://springdoc.org/v2/faq.html) — khai báo response không có content và ẩn response schema.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html) — các kiểu trả về handler, void, ResponseEntity, async và reactive.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html) — status, headers, body và các dạng response bất đồng bộ.
- [Spring Framework — WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html) — cách xử lý kiểu reactive và stream.
- [springdoc-openapi Core Properties](https://springdoc.org/core-properties.html) — cấu hình response dùng chung từ ControllerAdvice.

Suy luận schema từ kiểu trả về giúp tạo tài liệu nhanh và giữ tài liệu gần với mã nguồn. Khi chữ ký Java cụ thể, wrapper rõ ràng và response được kiểm thử, springdoc-openapi có thể tạo một hợp đồng OpenAPI hữu ích cho frontend, mobile, đối tác và các công cụ sinh client.
