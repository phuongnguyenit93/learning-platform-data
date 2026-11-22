# Mono, Flux và cách biểu diễn kiểu dữ liệu trả về

Spring WebFlux dùng Reactor để biểu diễn kết quả bất đồng bộ bằng hai kiểu phổ biến: **Mono<T>** cho tối đa một phần tử và **Flux<T>** cho không, một hoặc nhiều phần tử. Khi viết controller, hai kiểu này mô tả cách dữ liệu được phát ra trong quá trình xử lý. OpenAPI lại mô tả HTTP response mà client nhìn thấy: status code, media type, schema và headers.

Vì vậy, không thể chỉ nhìn tên Mono hoặc Flux rồi kết luận response sẽ là object, array hay luồng sự kiện. Cần xét cả kiểu phần tử T, kiểu wrapper, media type và cách WebFlux ghi dữ liệu ra HTTP. springdoc-openapi phân tích chữ ký method và metadata để tạo schema, nhưng tài liệu cuối cùng vẫn cần được kiểm tra cùng response thực tế.

## 1. Mono và Flux trong WebFlux

Reactor cung cấp hai publisher thường dùng:

| Kiểu | Số phần tử có thể phát ra | Trường hợp sử dụng |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Chi tiết một tài nguyên, kết quả tìm kiếm đơn, thao tác bất đồng bộ |
| Flux<T> | 0 đến nhiều | Danh sách, luồng sự kiện, dữ liệu phát liên tục |

Mono<OrderResponse> biểu diễn một kết quả đơn lẻ hoặc không có kết quả. Flux<OrderResponse> biểu diễn một chuỗi các kết quả có thể được phát dần theo thời gian.

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}

@GetMapping("/api/orders")
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

Trong hai method trên, method đầu trả về một publisher có tối đa một OrderResponse; method thứ hai có thể phát nhiều OrderSummary. Cả hai đều không chặn thread để chờ dữ liệu hoàn tất.

Một Mono có thể hoàn tất mà không phát phần tử. Một Flux có thể hoàn tất ngay mà không phát phần tử nào. Đây là đặc tính của publisher, không đồng nghĩa với một mã HTTP cụ thể.

## 2. Kiểu Java và HTTP representation là hai lớp khác nhau

OpenAPI không có kiểu Mono hay Flux. Đặc tả mô tả dữ liệu được truyền qua HTTP, không mô tả cơ chế Reactor phát dữ liệu nội bộ.

| Chữ ký controller | Ý nghĩa publisher | HTTP representation thường gặp |
|---|---|---|
| Mono<OrderResponse> | Tối đa một object | Một JSON object |
| Flux<OrderResponse> với application/json | Nhiều object | Một JSON array |
| Mono<Void> | Chỉ báo hoàn tất | Không có response body |
| Flux<OrderEvent> với text/event-stream | Chuỗi sự kiện | SSE stream |
| Flux<OrderEvent> với application/x-ndjson | Nhiều JSON record | Một JSON object trên mỗi dòng |

Đây là các cách biểu diễn thường gặp, không phải quy tắc suy ra chỉ từ kiểu Java. Media type, codec, cấu hình controller và annotation có thể làm thay đổi representation.

Khi đọc OpenAPI, hãy tìm operation response và content trước, sau đó kiểm tra schema. Khi đọc code, hãy tìm kiểu publisher và media type được khai báo ở mapping.

## 3. Mono<T> thường được mô tả bằng schema của T

Với endpoint trả về một object JSON:

~~~java
@GetMapping(
    value = "/api/orders/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Nếu springdoc phân giải được generic type, response schema thường tham chiếu schema của OrderResponse thay vì một kiểu Mono.

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '200':
          description: Thông tin đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
~~~

Trong components.schemas, OrderResponse mô tả các field JSON mà client nhận. Client không cần biết server dùng Mono, CompletableFuture hay một cơ chế bất đồng bộ khác bên trong.

Nếu kiểu trả về là Mono<OrderResponse>, đừng mô tả schema thành object có property tên value hoặc publisher. Publisher là chi tiết triển khai; schema phải phản ánh body thực tế.

## 4. Flux<T> với application/json thường là một JSON array

Một endpoint trả nhiều bản ghi trong một response JSON:

~~~java
@GetMapping(
    value = "/api/orders",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

Với media type application/json, WebFlux thường ghi chuỗi phần tử thành một JSON array. Ví dụ body:

~~~json
[
  {
    "id": "ORD-1001",
    "status": "PAID"
  },
  {
    "id": "ORD-1002",
    "status": "PENDING"
  }
]
~~~

OpenAPI schema cần biểu diễn array với items là OrderSummary:

~~~yaml
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: Danh sách đơn hàng
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/OrderSummary'
~~~

springdoc thường có thể suy ra array schema từ Flux<T>. Nếu cần khai báo tường minh bằng annotation, có thể dùng ArraySchema:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Danh sách đơn hàng",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = OrderSummary.class)
        )
    )
)
~~~

Chỉ thêm annotation tường minh khi kết quả suy luận chưa đúng hoặc cần kiểm soát metadata. Sau đó kiểm tra JSON OpenAPI để chắc chắn schema là array, không phải một object đơn.

## 5. Flux không mặc nhiên có nghĩa là streaming HTTP

Flux cho phép phát dữ liệu dần trong ứng dụng, nhưng HTTP representation còn phụ thuộc media type và encoder.

- application/json thường gom các phần tử thành một JSON array.
- text/event-stream biểu diễn Server-Sent Events.
- application/x-ndjson thường dùng một JSON record trên mỗi dòng.
- application/stream+json có thể dùng để truyền các giá trị JSON theo dạng streaming tùy codec và client.

Nếu dùng application/json, client thường nhận một body JSON theo cấu trúc array. Dù server có thể bắt đầu ghi dữ liệu khi publisher phát phần tử, client và codec vẫn xử lý representation JSON theo cách của media type đó.

Nếu cần client xử lý từng event ngay khi nhận, hãy chọn media type streaming phù hợp và kiểm tra hành vi codec, proxy và client. Không chỉ đổi return type từ List<T> sang Flux<T> rồi kết luận API đã trở thành event stream.

## 6. Server-Sent Events với Flux<ServerSentEvent<T>>

Server-Sent Events (SSE) là cơ chế server gửi các event tới client qua một kết nối HTTP kéo dài. WebFlux có thể trả về Flux<ServerSentEvent<T>>.

~~~java
@GetMapping(
    value = "/api/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<OrderEvent>> streamOrderEvents() {
    return orderEventService.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(event.id())
            .event("order-update")
            .build());
}
~~~

Một event SSE có thể chứa id, event name, data và retry. Wire format của SSE là văn bản theo từng event, không phải một JSON array duy nhất. Nếu data là object, WebFlux có thể serialize payload theo cấu hình codec; event framing vẫn theo quy tắc SSE.

Trong OpenAPI, response cần khai báo media type text/event-stream. Ví dụ:

~~~yaml
paths:
  /api/orders/events:
    get:
      responses:
        '200':
          description: Luồng sự kiện đơn hàng theo định dạng SSE
          content:
            text/event-stream:
              schema:
                type: string
                description: >
                  Luồng event SSE. Trường data mang payload OrderEvent;
                  mỗi event có thể có id và event name.
~~~

Có thể định nghĩa thêm component OrderEvent để mô tả cấu trúc payload data. OpenAPI và các client generator không biểu diễn đồng nhất framing, reconnect và event metadata của SSE; cần kiểm tra công cụ tiêu thụ cụ thể.

Không mô tả SSE như application/json array nếu client phải đọc từng event theo giao thức EventSource.

## 7. NDJSON và các dạng JSON streaming

NDJSON (Newline Delimited JSON) biểu diễn mỗi record JSON trên một dòng. Đây là định dạng hữu ích khi server phát nhiều record và client muốn xử lý từng dòng.

~~~java
@GetMapping(
    value = "/api/orders/stream",
    produces = "application/x-ndjson"
)
public Flux<OrderEvent> streamOrders() {
    return orderEventService.stream();
}
~~~

Body minh họa:

~~~text
{"id":"ORD-1001","status":"PAID"}
{"id":"ORD-1002","status":"SHIPPED"}
{"id":"ORD-1003","status":"DELIVERED"}
~~~

Media type và cách ghi từng record phải được hỗ trợ bởi codec trong phiên bản Spring Framework đang dùng. Có thể dùng application/stream+json nếu hệ thống và client thống nhất định dạng đó.

OpenAPI cần ghi đúng media type. Schema có thể mô tả payload record, ví dụ OrderEvent, đồng thời description nêu rõ body gồm nhiều JSON record phân tách bằng newline. Không nên tự động biến schema thành array nếu wire format thực tế là nhiều JSON record nối tiếp mà không có dấu ngoặc array.

Khả năng sinh client cho NDJSON khác nhau theo generator. Một số công cụ chỉ tạo model cho payload, không tạo API stream reader. Hãy kiểm tra generated client và viết test đọc nhiều dòng.

## 8. Mono<Void> biểu diễn thao tác không có body

Mono<Void> thường dùng cho thao tác chỉ cần báo hoàn tất, chẳng hạn xóa dữ liệu hoặc kích hoạt một hành động:

~~~java
@DeleteMapping("/api/orders/{id}")
public Mono<Void> deleteOrder(@PathVariable String id) {
    return orderService.deleteById(id);
}
~~~

Mono<Void> không chứa một object response để serialize. Tuy nhiên, nó không tự quyết định status code là 204.

Nếu muốn trả 204 No Content, có thể khai báo:

~~~java
@DeleteMapping("/api/orders/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> deleteOrder(@PathVariable String id) {
    return orderService.deleteById(id);
}
~~~

Hoặc:

~~~java
@DeleteMapping("/api/orders/{id}")
public Mono<ResponseEntity<Void>> deleteOrder(
    @PathVariable String id
) {
    return orderService.deleteById(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

OpenAPI tương ứng nên mô tả 204 mà không khai báo content body:

~~~yaml
responses:
  '204':
    description: Đơn hàng đã được xóa
~~~

Nếu controller không đặt status, response có thể dùng status mặc định của framework. Hãy khai báo và test status rõ ràng thay vì suy ra 204 chỉ từ Mono<Void>.

## 9. Mono.empty() không tự động có nghĩa là 404

Mono<T> có thể hoàn tất mà không phát giá trị. Trường hợp này thường xảy ra khi không tìm thấy dữ liệu hoặc không có kết quả.

~~~java
public Mono<OrderResponse> findById(String id) {
    return repository.findById(id)
        .map(orderMapper::toResponse);
}
~~~

Nếu repository không tìm thấy bản ghi, publisher có thể là Mono.empty(). Điều đó không tự động biến thành HTTP 404. Status và body phụ thuộc cách controller, framework hoặc exception handler xử lý publisher rỗng.

Nếu hợp đồng yêu cầu 404, hãy chuyển trạng thái rỗng thành response rõ ràng:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<ResponseEntity<OrderResponse>> getOrder(
    @PathVariable String id
) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Nếu API dùng body lỗi thống nhất, có thể tạo ResponseEntity.status(HttpStatus.NOT_FOUND).body(apiError) ở nhánh rỗng.

OpenAPI cần mô tả đúng các nhánh 200 và 404. Đừng khai báo 404 chỉ vì service trả Mono.empty(); hãy xác minh controller thực sự tạo status 404.

## 10. ResponseEntity và thứ tự wrapper reactive

Spring WebFlux hỗ trợ một số cách kết hợp ResponseEntity với publisher. Thứ tự wrapper ảnh hưởng thời điểm status/header được xác định.

| Kiểu trả về | Ý nghĩa |
|---|---|
| ResponseEntity<Mono<T>> | Status và header có sẵn; body được phát bất đồng bộ |
| ResponseEntity<Flux<T>> | Status và header có sẵn; body được phát thành nhiều phần tử |
| Mono<ResponseEntity<T>> | Toàn bộ response entity được tạo bất đồng bộ |
| Mono<ResponseEntity<Flux<T>>> | Response entity được tạo bất đồng bộ, body tiếp tục stream |

Ví dụ ResponseEntity<Mono<T>>:

~~~java
@GetMapping("/api/orders/{id}")
public ResponseEntity<Mono<OrderResponse>> getOrder(
    @PathVariable String id
) {
    Mono<OrderResponse> body = orderService.findById(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(body);
}
~~~

Status 200 và Content-Type được thiết lập ngay, còn body được phát sau.

Ví dụ Mono<ResponseEntity<T>>:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<ResponseEntity<OrderResponse>> getOrder(
    @PathVariable String id
) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Trong trường hợp này, controller có thể chọn 200 hoặc 404 sau khi publisher phát kết quả hoặc hoàn tất rỗng.

springdoc có thể phân giải các wrapper phổ biến để tạo schema, nhưng khi kiểu lồng nhau phức tạp hoặc generic bị mất, cần bổ sung annotation và kiểm tra OpenAPI JSON. Tránh dùng raw type như Mono hoặc Flux không có generic vì schema có thể trở nên quá chung.

## 11. Generic response wrapper kết hợp với Mono

Nhiều API dùng envelope chung:

~~~java
public record ApiResponse<T>(
    String code,
    String message,
    T data
) {}
~~~

Controller có thể trả:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<ApiResponse<OrderResponse>> getOrder(
    @PathVariable String id
) {
    return orderService.findById(id)
        .map(order -> new ApiResponse<>(
            "SUCCESS",
            "Lấy đơn hàng thành công",
            order
        ));
}
~~~

OpenAPI cần giữ được kiểu generic cụ thể để property data tham chiếu OrderResponse. Nếu tài liệu chỉ hiển thị data là object không xác định hoặc schema bị mất generic, client generator có thể tạo model không chính xác.

Có thể dùng @Schema(implementation = ...) hoặc customizer nếu cần kiểm soát component, nhưng phải bảo đảm response schema vẫn thể hiện đúng ApiResponse<OrderResponse>. Tên component được sinh phụ thuộc phiên bản swagger-core/springdoc và cách phân giải generic; hãy đọc components.schemas thay vì đoán tên.

Nếu nhiều operation dùng envelope nhưng data type khác nhau, kiểm tra từng operation riêng. Không mặc định mọi response wrapper được mô tả giống nhau chỉ vì cùng class ApiResponse.

## 12. Khai báo response schema bằng annotation

Khi springdoc suy ra schema chưa đúng hoặc cần mô tả rõ media type, có thể khai báo @ApiResponse, @Content và @Schema.

Ví dụ Mono<OrderResponse>:

~~~java
@GetMapping("/api/orders/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Thông tin đơn hàng",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Ví dụ Flux<OrderSummary> dưới dạng JSON array:

~~~java
@GetMapping("/api/orders")
@ApiResponse(
    responseCode = "200",
    description = "Danh sách đơn hàng",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = OrderSummary.class)
        )
    )
)
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

Annotation là metadata tài liệu, không thay đổi cách WebFlux serialize response. Nếu controller trả một Flux nhưng annotation mô tả object đơn, tài liệu có thể sai dù ứng dụng vẫn chạy.

Không khai báo schema implementation cho Mono<Void> hoặc response 204 không có body. Nếu cần mô tả headers, khai báo headers riêng mà không thêm content.

## 13. Media type phải khớp với produces

Thuộc tính produces trên mapping quyết định media type mà endpoint công bố và có thể ảnh hưởng lựa chọn codec:

~~~java
@GetMapping(
    value = "/api/orders",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

Với SSE:

~~~java
@GetMapping(
    value = "/api/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<OrderEvent>> events() {
    return eventService.events();
}
~~~

Với NDJSON:

~~~java
@GetMapping(
    value = "/api/orders/stream",
    produces = "application/x-ndjson"
)
public Flux<OrderEvent> stream() {
    return eventService.stream();
}
~~~

Hãy đối chiếu mapping produces, content trong OpenAPI response, header Content-Type thực tế, codec hỗ trợ media type và cách client đọc body.

Nếu OpenAPI mô tả application/json nhưng runtime trả text/event-stream, client generator có thể tạo code đọc body sai. Ngược lại, tài liệu mô tả SSE nhưng controller thực tế trả JSON array cũng là sai hợp đồng.

## 14. Mô tả request body reactive

Request body trong WebFlux cũng có thể được nhận dưới dạng publisher:

~~~java
@PostMapping(
    value = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> createOrder(
    @Valid @RequestBody Mono<CreateOrderRequest> request
) {
    return request.flatMap(orderService::create);
}
~~~

Với một JSON object thông thường, OpenAPI requestBody vẫn mô tả schema CreateOrderRequest. Mono chỉ biểu diễn quá trình nhận body bất đồng bộ.

Nếu endpoint nhận nhiều record hoặc stream request, representation sẽ phụ thuộc media type và codec. Ví dụ NDJSON request có thể dùng Flux<CreateOrderLine> và consumes application/x-ndjson. Khi đó cần mô tả rõ framing và kiểm tra client có thể gửi nhiều dòng hay không.

Không mô tả request body thành schema Mono hoặc Flux. Hãy mô tả payload mà server nhận sau khi giải mã.

## 15. Xử lý lỗi trong pipeline reactive

Lỗi trong Reactor được phát ra như tín hiệu onError. WebFlux có thể chuyển lỗi thành HTTP response thông qua exception handler hoặc cơ chế xử lý lỗi của ứng dụng.

~~~java
public Mono<OrderResponse> findById(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(id)
        ))
        .map(orderMapper::toResponse);
}
~~~

Có thể xử lý tập trung:

~~~java
@RestControllerAdvice
class ReactiveExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    Mono<ResponseEntity<ApiError>> handleNotFound(
        OrderNotFoundException exception
    ) {
        ApiError error = new ApiError(
            "ORDER_NOT_FOUND",
            "Không tìm thấy đơn hàng"
        );

        return Mono.just(
            ResponseEntity.status(HttpStatus.NOT_FOUND).body(error)
        );
    }
}
~~~

OpenAPI operation cần mô tả response 404 với schema ApiError nếu đây là hành vi thực tế. Annotation @ApiResponse không tự xử lý onError và cũng không biến exception thành status.

Với lỗi xảy ra sau khi stream đã bắt đầu ghi body, server có thể không còn thay đổi được HTTP status hoặc headers. Khi đó, giao thức stream cần quy ước riêng để báo lỗi trong luồng hoặc kết thúc kết nối. Đây là điểm cần cân nhắc với SSE và NDJSON.

## 16. Backpressure không được mô tả bằng schema OpenAPI

Reactor hỗ trợ backpressure để subscriber điều tiết lượng dữ liệu publisher phát ra. Đây là cơ chế điều khiển luồng nội bộ giữa publisher và subscriber.

OpenAPI schema không mô tả tốc độ phát event, request demand, buffering strategy, cancellation, retry/reconnect, thời điểm stream kết thúc hoặc chính sách giữ kết nối.

Nếu client cần biết stream có thể kéo dài bao lâu, event có thể bị lặp hay cách reconnect, hãy bổ sung description, tài liệu vận hành hoặc giao thức ứng dụng rõ ràng. Không thể suy ra các quy tắc này từ type Flux<T>.

Đối với SSE, hãy mô tả event name, id và payload. Đối với NDJSON, mô tả cách phân tách record và điều kiện kết thúc stream. Với stream có thể vô hạn, nói rõ client cần hủy subscription hoặc đóng kết nối như thế nào.

## 17. Phân biệt Flux danh sách với Page và Slice

Flux<T> có thể phát nhiều phần tử, nhưng không tự cung cấp metadata phân trang như Page<T>.

| Kiểu | Dữ liệu | Metadata |
|---|---|---|
| Flux<T> | Chuỗi phần tử | Không có totalElements/page number mặc định |
| Mono<List<T>> | Một danh sách hoàn chỉnh | Không có metadata phân trang mặc định |
| Mono<Page<T>> | Một trang dữ liệu | Có totalElements, totalPages, page number |
| Mono<Slice<T>> | Một lát dữ liệu | Có hasNext/hasPrevious |

Nếu API cần page, size, totalElements và totalPages, hãy dùng kiểu kết quả phân trang phù hợp thay vì giả định Flux là một Page.

Với repository reactive, Spring Data có thể hỗ trợ các kiểu trả về khác nhau tùy module và store. Hãy kiểm tra khả năng của repository đang dùng. Không phải mọi repository reactive đều hỗ trợ Page theo cùng cách với repository blocking.

Nếu endpoint trả Flux nhưng thực tế chỉ lấy một trang rồi phát từng item, OpenAPI có thể chỉ thấy array hoặc stream mà không thấy page metadata. Nếu client cần metadata, hãy thiết kế response envelope phù hợp.

## 18. Dependency WebFlux và springdoc

Một ứng dụng Spring Boot WebFlux cần starter WebFlux. Với springdoc 2.x và Spring Boot 3, starter thường dùng cho WebFlux UI là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>YOUR_COMPATIBLE_SPRINGDOC_VERSION</version>
</dependency>
~~~

Dùng phiên bản springdoc tương thích với dòng Spring Boot đang sử dụng và quản lý version qua dependency management hoặc property của dự án. Không trộn starter WebMVC và WebFlux một cách tùy tiện trong cùng ứng dụng; lựa chọn runtime stack cần rõ ràng.

Sau khi ứng dụng khởi động, tài liệu mặc định thường có tại /v3/api-docs và giao diện tại /swagger-ui.html. Nếu dự án đổi path, group hoặc cấu hình UI, dùng URL đã cấu hình thay vì giả định mặc định.

## 19. Kiểm tra OpenAPI JSON

Tải tài liệu từ ứng dụng:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Xem response schema của endpoint Mono:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
~~~

Xem response schema của endpoint Flux:

~~~bash
jq '.paths["/api/orders"].get.responses["200"].content["application/json"].schema' openapi.json
~~~

Với Flux JSON, xác nhận schema có type array và items trỏ tới component của phần tử. Với Mono JSON, xác nhận schema trỏ tới object đơn.

Kiểm tra media type của SSE:

~~~bash
jq '.paths["/api/orders/events"].get.responses["200"].content | keys' openapi.json
~~~

Kết quả cần có text/event-stream nếu endpoint công bố SSE. Tương tự, endpoint NDJSON cần có media type mà controller thực sự sử dụng.

Đối chiếu thêm components.schemas, generic wrapper, response 204, response 404, status code và produces/media type. OpenAPI JSON là đầu ra cuối cùng để Swagger UI và client generator tiêu thụ; không chỉ kiểm tra annotation trong source code.

## 20. Kiểm tra runtime bằng WebTestClient

WebTestClient phù hợp để kiểm thử WebFlux. Ví dụ kiểm tra một response Mono:

~~~java
@WebFluxTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsSingleOrder() {
        given(orderService.findById("ORD-1001"))
            .willReturn(Mono.just(new OrderResponse(
                "ORD-1001",
                "PAID"
            )));

        webTestClient.get()
            .uri("/api/orders/{id}", "ORD-1001")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("ORD-1001")
            .jsonPath("$.status").isEqualTo("PAID");
    }
}
~~~

Kiểm tra Flux JSON array:

~~~java
webTestClient.get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$[0].id").isEqualTo("ORD-1001");
~~~

Kiểm tra SSE cần xác minh media type và event stream:

~~~java
webTestClient.get()
    .uri("/api/orders/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM);
~~~

Đối với stream không bao giờ hoàn tất, tránh assertion đợi toàn bộ body. Hãy dùng cách tiêu thụ stream có giới hạn, timeout và hủy subscription trong test để không treo pipeline.

Test cần chuẩn bị mock, DTO và imports theo ứng dụng. @MockitoBean có trong các phiên bản Spring Framework/Spring Boot mới; dự án cũ có thể dùng annotation mock tương ứng đã được hỗ trợ.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| OpenAPI hiển thị Mono như object wrapper | Generic type không được phân giải hoặc custom converter sai |
| Flux JSON bị mô tả thành object đơn | Schema annotation ghi đè suy luận array |
| Flux bị hiểu nhầm là SSE | Chỉ đổi kiểu return mà không khai báo text/event-stream |
| Swagger UI hiển thị JSON nhưng runtime trả SSE | produces và response content không đồng bộ |
| Mono.empty() trả 200 thay vì 404 | Chưa ánh xạ nhánh rỗng thành status 404 |
| Mono<Void> vẫn trả 200 | Chưa khai báo ResponseEntity hoặc @ResponseStatus phù hợp |
| ResponseEntity wrapper bị mất schema | Generic lồng nhau không được phân giải như mong đợi |
| NDJSON client chỉ đọc một object | Generator không hỗ trợ framing hoặc schema mô tả chưa rõ |
| Stream lỗi sau khi đã gửi một phần body | HTTP status/header không còn thay đổi được |
| Swagger UI chờ mãi khi gọi Flux vô hạn | Endpoint là stream kéo dài; cần client và test đọc theo event |
| Schema Page không có metadata | Controller chỉ trả Flux<T> thay vì kiểu phân trang |
| Generic ApiResponse<T> thành object chung | Type parameter bị mất hoặc raw type được sử dụng |

## 22. Quy ước thiết kế response reactive

Để hợp đồng dễ hiểu:

- Dùng Mono<T> cho response đơn.
- Dùng Flux<T> với application/json khi muốn trả một JSON array.
- Dùng text/event-stream cho SSE và mô tả event payload rõ ràng.
- Dùng NDJSON hoặc media type streaming đã thống nhất khi cần record theo dòng.
- Dùng Mono<Void> cho response không body và đặt status tường minh.
- Chuyển Mono.empty() thành 404/204 nếu nghiệp vụ yêu cầu; không dựa vào suy đoán.
- Giữ generic type cụ thể, tránh raw Mono và raw Flux.
- Dùng ResponseEntity khi cần kiểm soát status và headers theo nhánh.
- Khai báo response schema, content và produces đồng bộ.
- Kiểm tra OpenAPI JSON cùng WebTestClient.

Một API reactive tốt không chỉ có publisher phù hợp mà còn có HTTP representation rõ ràng cho client. Hãy chọn kiểu trả về theo cách client cần tiêu thụ dữ liệu, không chỉ theo cách service nội bộ xử lý bất đồng bộ.

## 23. Checklist

- [ ] Đã phân biệt Mono<T> và Flux<T>.
- [ ] Đã xác định HTTP representation thay vì suy luận chỉ từ publisher.
- [ ] Mono JSON được mô tả bằng schema object của T.
- [ ] Flux application/json được mô tả bằng array schema.
- [ ] SSE dùng text/event-stream và có mô tả event payload.
- [ ] NDJSON/streaming media type được ghi đúng và mô tả framing.
- [ ] Mono<Void> không khai báo response body.
- [ ] Status cho Mono.empty() được xử lý tường minh.
- [ ] ResponseEntity wrapper giữ đúng status, header và body schema.
- [ ] Generic response wrapper giữ đúng kiểu phần tử.
- [ ] Exception reactive có response documentation phù hợp.
- [ ] Đã phân biệt Flux với Page/Slice.
- [ ] Dependency springdoc WebFlux tương thích phiên bản Spring Boot.
- [ ] Đã kiểm tra /v3/api-docs.
- [ ] Đã test JSON, SSE hoặc NDJSON bằng WebTestClient.

## 24. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Spring Framework – WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework – Reactive libraries](https://docs.spring.io/spring-framework/reference/web/webflux-reactive-libraries.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object)

Mono và Flux mô tả publisher reactive ở phía server; OpenAPI mô tả representation HTTP mà client nhận. Mono thường ánh xạ thành một payload, Flux có thể là JSON array hoặc stream tùy media type, còn Mono<Void> thường không có body. Hãy xác minh schema, content type, status và body bằng cả /v3/api-docs lẫn WebTestClient để tài liệu phản ánh đúng hành vi WebFlux.
