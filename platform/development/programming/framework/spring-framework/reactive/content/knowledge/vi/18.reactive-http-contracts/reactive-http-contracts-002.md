# Đàm phán nội dung bằng `Accept` và `Content-Type` trong Spring WebFlux

## 1. Mục tiêu: hai header trả lời hai câu hỏi khác nhau

Trong HTTP API, client và server cần thống nhất **định dạng dữ liệu**. Một request có thể gửi JSON nhưng muốn nhận JSON, hoặc gửi JSON nhưng muốn nhận phản hồi dạng văn bản. Hai header quan trọng nhất là:

- **`Content-Type`** mô tả định dạng của representation nằm trong **request body hiện tại**: client đang gửi JSON, XML, NDJSON, form data hay định dạng nào?
- **`Accept`** mô tả những định dạng representation mà client **muốn nhận trong response**: client chấp nhận JSON, XML, text hay một tập định dạng có mức ưu tiên?

Đừng đảo vai trò hai header. `Content-Type` trả lời “body tôi gửi được mã hóa theo định dạng gì?”, còn `Accept` trả lời “response gửi về cho tôi có thể dùng định dạng gì?”.

Trong Spring WebFlux, hai header tham gia vào hai giai đoạn khác nhau:

1. Khi đọc request body, `HttpMessageReader` và decoder phải tìm codec có thể đọc media type của `Content-Type` thành kiểu Java mà handler yêu cầu.
2. Khi ghi response body, `HttpMessageWriter` và encoder phải tìm codec có thể ghi kiểu Java thành một media type phù hợp với `Accept` và điều kiện mapping như `produces`.

Bài học giúp bạn hiểu cú pháp media range và quality value (`q`), cách Spring xử lý `consumes`/`produces`, lý do xuất hiện HTTP 406 và 415, cách khai báo functional route, và cách kiểm thử content negotiation.

~~~text
                 REQUEST
Client ----------------------------------------> Spring WebFlux
       Content-Type: application/json
       Accept: application/json, text/plain;q=0.5
       Body: JSON bytes

                 READ
       Content-Type + target Java type
                    |
                    v
             HttpMessageReader
                    |
                    v
             Decoder -> Java object
                    |
                    v
             Controller / HandlerFunction

                 RESPONSE
       Controller returns Mono<T> / Flux<T>
                    |
                    v
             HttpMessageWriter
                    ^
                    |
       Accept + produces + available codecs
                    |
                    v
             Encoder -> response bytes
                    |
                    v
Client <---------------------------------------- Spring WebFlux
       Content-Type: application/json
       Body: JSON bytes
~~~

## 2. Media type là gì?

Media type mô tả định dạng và loại nội dung của một representation. Cấu trúc cơ bản:

~~~text
type / subtype ; parameter=value
~~~

Ví dụ:

| Media type | Ý nghĩa |
| --- | --- |
| `application/json` | JSON |
| `application/xml` | XML |
| `text/plain` | Văn bản thuần |
| `text/html` | HTML |
| `application/x-www-form-urlencoded` | Form URL-encoded |
| `multipart/form-data` | Form nhiều phần, thường có file |
| `application/x-ndjson` | JSON objects phân tách theo dòng |
| `text/event-stream` | Server-Sent Events |
| `application/problem+json` | JSON theo định dạng Problem Details |
| `application/octet-stream` | Dữ liệu byte tổng quát |

Một media type có thể kèm parameter:

~~~http
Content-Type: application/json; charset=UTF-8
Accept: text/html;level=1
~~~

Parameter có thể ảnh hưởng cách diễn giải representation hoặc cách framework so khớp. Với JSON hiện đại, UTF-8 là lựa chọn mặc định phổ biến; không cần tự thêm charset vào mọi request nếu client và server đã thống nhất.

**Media type không phải content encoding.** Các khái niệm liên quan:

| Header | Vai trò |
| --- | --- |
| `Content-Type` | Định dạng representation của body hiện tại |
| `Accept` | Định dạng representation client chấp nhận trong response |
| `Content-Encoding` | Cách mã hóa/nén representation đang gửi, ví dụ `gzip` |
| `Accept-Encoding` | Các kiểu content encoding client chấp nhận |
| `Accept-Language` | Ngôn ngữ representation client ưu tiên |
| `Vary` | Cho cache biết request header nào ảnh hưởng lựa chọn response |

Ví dụ, một response có thể có `Content-Type: application/json` và `Content-Encoding: gzip` cùng lúc: nội dung logic là JSON, còn byte truyền đi đã nén gzip. `Accept-Encoding` không thay thế `Accept`.

## 3. `Accept`: client muốn nhận representation nào?

### 3.1. Cú pháp cơ bản

Client có thể gửi một hoặc nhiều media range:

~~~http
GET /api/products/1 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Nghĩa là client muốn nhận JSON. Có thể liệt kê nhiều loại:

~~~http
Accept: application/json, text/plain, application/xml
~~~

Có hai wildcard thông dụng:

- `application/*`: chấp nhận mọi subtype thuộc nhóm `application`.
- `*/*`: chấp nhận mọi media type.

Nếu không gửi `Accept`, client không nêu sở thích định dạng cụ thể; server có thể chọn một representation phù hợp. `Accept: */*` cũng biểu thị chấp nhận mọi loại theo media range.

### 3.2. Quality value (`q`): mức ưu tiên

Mỗi media range có thể có quality value từ `0` đến `1`. Nếu không ghi `q`, giá trị mặc định là `1`. Giá trị càng cao thể hiện mức ưu tiên càng cao; `q=0` nghĩa là representation tương ứng không được chấp nhận.

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5, application/xml;q=0.2
~~~

Ví dụ này ưu tiên JSON, sau đó text, rồi XML. Quality value có thể có tối đa ba chữ số thập phân theo cú pháp HTTP:

~~~http
Accept: application/json;q=1.0, text/plain;q=0.75, application/xml;q=0
~~~

`q` là trọng số ưu tiên của client, không phải phần trăm xác suất và cũng không phải điểm chất lượng của dữ liệu.

### 3.3. Wildcard và độ cụ thể

~~~http
Accept: application/*;q=0.8, application/json;q=1.0, */*;q=0.1
~~~

Các media range có độ cụ thể khác nhau. Khi xác định chất lượng của một media type cụ thể, range cụ thể hơn có thể chi phối range tổng quát. Ví dụ `application/json` được mô tả trực tiếp với `q=1.0`, nên ưu tiên hơn mức tổng quát `application/*` hoặc `*/*`.

Đừng tự viết thuật toán chọn media type chỉ bằng cách sắp xếp mọi giá trị `q` giảm dần rồi bỏ qua độ cụ thể. Spring còn xét điều kiện mapping, kiểu Java và khả năng ghi của các codec hiện có.

### 3.4. `Accept` là sở thích, không phải lệnh buộc server phải có codec

Nếu client gửi:

~~~http
Accept: application/xml
~~~

nhưng endpoint chỉ có khả năng tạo JSON, server không thể tự biến object thành XML nếu không có writer/encoder hỗ trợ. Tùy mapping và cấu hình, kết quả có thể là HTTP **406 Not Acceptable**.

Nếu endpoint chỉ tạo JSON và client gửi `Accept: application/json`, request có representation phù hợp. Nếu client gửi `Accept: application/*`, JSON cũng có thể phù hợp với wildcard này.

### 3.5. `q=0` loại một định dạng khỏi tập được chấp nhận

~~~http
Accept: application/json;q=0, text/plain;q=1
~~~

Client nói rõ không muốn JSON và ưu tiên text. Nếu server chỉ có endpoint/representation JSON, không nên trả JSON như thể client đã chấp nhận; có thể phát sinh 406. Nếu server có representation text phù hợp, nó có thể chọn text.

## 4. `Content-Type`: request body đang được gửi theo định dạng nào?

### 4.1. Gửi JSON phải khai báo JSON

~~~http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{"name":"Keyboard","price":120}
~~~

`Content-Type: application/json` cho server biết byte body cần được giải mã như JSON. `Accept: application/json` cho server biết client muốn nhận response JSON. Hai header có thể cùng giá trị, nhưng chúng phục vụ hai chiều khác nhau.

Một request hoàn toàn có thể dùng:

~~~http
Content-Type: application/json
Accept: text/plain
~~~

Nghĩa là client gửi JSON nhưng muốn server trả văn bản thuần. Server chỉ đáp ứng được nếu endpoint có thể tạo text representation phù hợp.

### 4.2. Body không phải JSON thì phải khai báo đúng

Ví dụ form:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=linh&password=secret
~~~

Ví dụ multipart:

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----client-boundary
~~~

Ví dụ NDJSON:

~~~http
POST /events HTTP/1.1
Content-Type: application/x-ndjson

{"id":1,"type":"created"}
{"id":2,"type":"updated"}
~~~

Nếu gửi byte JSON nhưng khai báo `Content-Type: text/plain`, server sẽ lựa chọn reader theo text/plain. Nếu handler chỉ chấp nhận JSON, request có thể bị từ chối với 415.

### 4.3. Request không có body thường không cần `Content-Type`

Một GET request thông thường không có body nên thường không cần `Content-Type`. Header này không nói server phải trả định dạng gì. Muốn chọn response, gửi `Accept`.

Đây là lỗi phổ biến:

~~~http
GET /api/products/1
Content-Type: application/json
~~~

Header trên không có nghĩa client yêu cầu JSON response. Header đúng cho mục tiêu đó là:

~~~http
GET /api/products/1
Accept: application/json
~~~

## 5. Phân biệt `consumes` và `produces` trong Spring WebFlux

Trong annotated controller, Spring dùng hai thuộc tính của mapping để ràng buộc media type.

### 5.1. `consumes` khớp với request `Content-Type`

~~~java
@PostMapping(
    path = "/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
    return body.flatMap(service::create);
}
~~~

`consumes` mô tả loại request body mà handler có thể nhận. Nếu client gửi `Content-Type: text/plain` nhưng mapping chỉ `consumes=application/json`, mapping không phù hợp và Spring thường trả **415 Unsupported Media Type**.

Nếu method không có body, `consumes` thường không cần thiết. Nếu có nhiều định dạng đầu vào, có thể khai báo nhiều media type:

~~~java
@PostMapping(
    path = "/import",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        "application/x-ndjson"
    }
)
public Mono<Void> importData(@RequestBody Flux<ImportRow> rows) {
    return service.importRows(rows);
}
~~~

Đây là đoạn minh họa: ngoài mapping, ứng dụng còn phải có reader/decoder hỗ trợ từng định dạng được khai báo.

### 5.2. `produces` khớp với request `Accept` và định dạng response

~~~java
@GetMapping(
    path = "/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Product> get(@PathVariable String id) {
    return service.findById(id);
}
~~~

`produces` mô tả representation mà handler có thể trả. Spring so khớp điều kiện này với `Accept` của request và sử dụng media type đã chọn khi ghi response.

Nếu client gửi `Accept: text/plain` trong khi mapping chỉ tạo JSON, mapping không phù hợp và thường dẫn đến **406 Not Acceptable**.

### 5.3. Có thể khai báo nhiều media type

~~~java
@GetMapping(
    path = "/report",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public Mono<Report> report() {
    return reportService.load();
}
~~~

Ví dụ này chỉ hoạt động đầy đủ nếu ứng dụng có codec/writer có thể ghi `Report` thành JSON **và** XML. Khai báo hai chuỗi trong `produces` không tự cài đặt XML encoder. Nếu thiếu writer XML, client yêu cầu XML vẫn không nhận được representation hợp lệ.

Spring có thể chọn representation phù hợp theo `Accept`, mapping và writer. Hãy kiểm tra cả dependency codec lẫn response thực tế.

### 5.4. Bảng nhớ nhanh

| Thành phần | Kiểm tra điều gì? | Chiều dữ liệu |
| --- | --- | --- |
| `consumes` | Request `Content-Type` | Client → Server |
| `produces` | Request `Accept` và khả năng tạo response | Server → Client |
| `@RequestBody` | Đọc/decode request body | Client → Java |
| `@ResponseBody` / `@RestController` | Encode return value thành response body | Java → Client |
| `HttpMessageReader` | Có thể đọc media type thành kiểu Java? | Decode |
| `HttpMessageWriter` | Có thể ghi kiểu Java thành media type? | Encode |

## 6. HTTP 406, 415 và các lỗi dễ nhầm

### 6.1. 406 Not Acceptable

Xảy ra khi server không tìm được representation response phù hợp với các media range mà client chấp nhận, trong khi endpoint/framework yêu cầu tuân thủ negotiation.

Ví dụ:

~~~http
GET /api/product
Accept: text/csv
~~~

Nếu endpoint chỉ hỗ trợ JSON, server không có representation CSV để trả và có thể trả 406.

### 6.2. 415 Unsupported Media Type

Xảy ra khi server không hỗ trợ media type của request body hoặc handler mapping không chấp nhận `Content-Type` đó.

Ví dụ:

~~~http
POST /api/echo
Content-Type: application/xml
Accept: application/json

<message>hello</message>
~~~

Nếu endpoint chỉ nhận JSON, request bị từ chối với 415 dù client sẵn sàng nhận JSON response. `Accept` đúng không thể bù cho `Content-Type` sai.

### 6.3. 400 Bad Request khác 415

~~~http
POST /api/echo
Content-Type: application/json
Accept: application/json

{"name":
~~~

Ở đây media type JSON được hỗ trợ, nhưng cú pháp body không hợp lệ. Lỗi là lỗi parse/đầu vào, thường được ánh xạ thành **400 Bad Request**, không phải 415.

### 6.4. Các status thường cần phân biệt

| Status | Nguyên nhân thường gặp | Cần kiểm tra |
| --- | --- | --- |
| 400 Bad Request | JSON hỏng, dữ liệu đầu vào không hợp lệ, decode/validation lỗi | Body, schema, validation |
| 404 Not Found | Không có route/mapping hoặc resource không tồn tại | Path, method, route, ID |
| 406 Not Acceptable | Không có response representation phù hợp với Accept/produces | Accept, produces, writer |
| 413 Payload Too Large | Payload vượt giới hạn server/codec | Kích thước body, giới hạn buffer |
| 415 Unsupported Media Type | Content-Type request không được mapping/reader hỗ trợ | Content-Type, consumes, decoder |
| 500 Internal Server Error | Lỗi server chưa được ánh xạ phù hợp | Log, exception, handler |

**Cách chẩn đoán:** nếu lỗi xảy ra trước khi controller được gọi, kiểm tra mapping và argument resolver. Nếu controller đã chạy nhưng response không ghi được, kiểm tra writer, media type, kiểu return và lỗi encode.

## 7. Spring WebFlux chọn reader và writer như thế nào?

### 7.1. Đọc request: `HttpMessageReader`

Luồng khái niệm:

~~~text
HTTP request body bytes
       |
       v
Content-Type + target Java type
       |
       v
ServerCodecConfigurer
       |
       v
HttpMessageReader.canRead(...)
       |
       v
Decoder
       |
       v
Mono<T> / Flux<T> / object
~~~

`HttpMessageReader` kiểm tra khả năng đọc kiểu Java và media type. Ví dụ, Jackson JSON reader có thể decode `application/json` thành một DTO. Reader form hoặc multipart xử lý định dạng tương ứng.

Trong annotated controller:

~~~java
@PostMapping(
    path = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderReceipt> create(
    @RequestBody Mono<CreateOrder> request
) {
    return request.flatMap(orderService::create);
}
~~~

Với `Mono<CreateOrder>`, controller nhận Publisher đại diện cho body; reader thực sự tiêu thụ body khi subscription đi tới Publisher đó. Với tham số `@RequestBody CreateOrder` không reactive, Spring cần resolve object trước khi gọi method.

Trong WebFlux.fn:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateOrder.class)
        .flatMap(orderService::create)
        .flatMap(saved -> ServerResponse
            .created(URI.create("/orders/" + saved.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(saved));
}
~~~

`bodyToMono` sử dụng codec để đọc body. Hãy compose Publisher vào chuỗi trả về; không tự `subscribe()` hoặc `block()`.

### 7.2. Ghi response: `HttpMessageWriter`

Luồng khái niệm:

~~~text
Controller returns Mono<T> / Flux<T>
                 |
                 v
Accept + produces + declared body type
                 |
                 v
ServerCodecConfigurer
                 |
                 v
HttpMessageWriter.canWrite(...)
                 |
                 v
Encoder -> DataBuffer
                 |
                 v
HTTP response body
~~~

`HttpMessageWriter` chọn encoder tương thích với kiểu Java và media type response đã chọn. Ví dụ:

~~~java
@GetMapping(
    path = "/products",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<Product> products() {
    return repository.findAll();
}
~~~

Framework đăng ký ghi response và tiêu thụ `Flux<Product>` theo demand. Với JSON array, codec có thể aggregate các phần tử trước khi serialize; với streaming media type như NDJSON/SSE, writer có thể ghi từng phần tử. Media type và writer quyết định hành vi thực tế.

### 7.3. `ServerCodecConfigurer`

WebFlux cung cấp codec mặc định và cho phép tùy chỉnh. Ví dụ giới hạn bộ nhớ cho những codec cần aggregate:

~~~java
@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Đây là cấu hình minh họa cho giới hạn 2 MiB. Giá trị thực cần căn cứ vào payload, kiểu codec và yêu cầu hệ thống. Tăng giới hạn không thay thế kiểm soát kích thước request hoặc xử lý streaming.

Khi thêm media type riêng, cần đăng ký codec/reader/writer phù hợp. Chỉ thêm media type vào `produces` hoặc `consumes` không đảm bảo ứng dụng đã biết cách decode/encode.

## 8. Content negotiation trong WebFlux.fn

Trong functional endpoint, request predicates có thể kiểm tra `Accept` và `Content-Type`.

### 8.1. Predicate `accept`

~~~java
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;

RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/report",
            accept(MediaType.APPLICATION_JSON),
            handler::jsonReport)
        .build();
~~~

`accept(MediaType.APPLICATION_JSON)` kiểm tra request có chấp nhận JSON hay không. Đây là điều kiện route; handler vẫn phải tạo response JSON:

~~~java
public Mono<ServerResponse> jsonReport(ServerRequest request) {
    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("status", "ready"));
}
~~~

### 8.2. Predicate `contentType`

~~~java
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;

RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .POST("/api/orders",
            contentType(MediaType.APPLICATION_JSON),
            handler::create)
        .build();
~~~

`contentType(MediaType.APPLICATION_JSON)` kiểm tra định dạng body request. Predicate này không chọn định dạng response; muốn response JSON, handler phải thiết lập `ServerResponse.contentType` hoặc có cấu hình phù hợp.

### 8.3. Predicate không giống hoàn toàn mapping `consumes`/`produces`

Trong annotated controller, Spring có cơ chế mapping chuyên biệt để ánh xạ điều kiện `consumes` và `produces` sang lỗi HTTP thích hợp, thường là 415 và 406.

Trong WebFlux.fn, `accept(...)` và `contentType(...)` là RequestPredicate. Khi predicate trả false, router coi route không khớp và thử route tiếp theo. Nếu không có route/fallback phù hợp, kết quả thường là 404. Predicate không tự động có nghĩa “mọi trường hợp không khớp Accept đều trả 406” hoặc “mọi Content-Type sai đều trả 415”.

Nếu API functional cần status 406/415 rõ ràng, khai báo fallback route theo method/path hoặc kiểm tra header trong handler rồi trả status tương ứng. Ví dụ:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/report",
            accept(MediaType.APPLICATION_JSON),
            handler::jsonReport)
        .GET("/api/report", handler::notAcceptable)
        .POST("/api/orders",
            contentType(MediaType.APPLICATION_JSON),
            handler::create)
        .POST("/api/orders", handler::unsupportedMediaType)
        .build();
~~~

Các method fallback `notAcceptable` và `unsupportedMediaType` do ứng dụng định nghĩa:

~~~java
public Mono<ServerResponse> notAcceptable(ServerRequest request) {
    return ServerResponse.status(HttpStatus.NOT_ACCEPTABLE).build();
}

public Mono<ServerResponse> unsupportedMediaType(ServerRequest request) {
    return ServerResponse.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE).build();
}
~~~

Route cụ thể phải đứng trước route fallback. Nếu không, fallback tổng quát có thể bắt request trước khi route có predicate được xét.

## 9. Chọn media type cho JSON, NDJSON, SSE và file

### 9.1. JSON object hoặc JSON array

`application/json` phù hợp với một object hoặc một document JSON hoàn chỉnh. Với `Mono<T>`, writer thường encode một object. Với `Flux<T>`, Jackson writer mặc định thường aggregate thành JSON array để tạo một document hoàn chỉnh.

~~~java
@GetMapping(
    path = "/products",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<Product> products() {
    return repository.findAll();
}
~~~

Nếu dữ liệu rất lớn và client cần nhận từng phần tử khi có, hãy cân nhắc định dạng streaming. Đừng giả định chỉ cần đổi return type thành `Flux` là response tự flush từng item.

### 9.2. NDJSON

`application/x-ndjson` (JSON Lines) biểu diễn mỗi object JSON trên một dòng:

~~~text
{"id":1,"name":"A"}
{"id":2,"name":"B"}
{"id":3,"name":"C"}
~~~

Ví dụ:

~~~java
@GetMapping(
    path = "/events",
    produces = "application/x-ndjson"
)
public Flux<Event> events() {
    return eventService.stream();
}
~~~

Client phải gửi `Accept: application/x-ndjson` nếu muốn yêu cầu định dạng này. Với request body NDJSON, client gửi `Content-Type: application/x-ndjson` và server cần reader hỗ trợ.

### 9.3. Server-Sent Events

`text/event-stream` dành cho luồng event server-to-client:

~~~java
@GetMapping(
    path = "/notifications",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Notification>> notifications() {
    return notificationService.stream()
        .map(value -> ServerSentEvent.builder(value)
            .event("notification")
            .build());
}
~~~

Client thường gửi `Accept: text/event-stream`. SSE có format riêng, event framing và quy tắc reconnect; không chỉ là JSON được gửi liên tục. Kết nối dài cần quản lý cancellation, heartbeat và tài nguyên.

### 9.4. File download

File download thường cần media type mô tả nội dung file và header `Content-Disposition`:

~~~java
@GetMapping("/download")
public Mono<ResponseEntity<byte[]>> download() {
    byte[] content = "example".getBytes(StandardCharsets.UTF_8);

    return Mono.just(ResponseEntity.ok()
        .contentType(MediaType.TEXT_PLAIN)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            "attachment; filename=\"example.txt\"")
        .body(content));
}
~~~

Ví dụ này minh họa file nhỏ trong bộ nhớ. Với file lớn, ưu tiên streaming resource hoặc Publisher byte phù hợp, tránh gom toàn bộ file thành `byte[]`.

## 10. Cấu hình negotiation và media type riêng

### 10.1. Mặc định và cấu hình

Trong WebFlux, requested content type resolver tham gia xác định media type client chấp nhận, thông thường dựa trên header `Accept`. Ứng dụng có thể tùy chỉnh content type resolution thông qua `WebFluxConfigurer.configureContentTypeResolver` nếu có nhu cầu cụ thể.

Hãy ưu tiên header chuẩn `Accept` khi xây API HTTP. Nếu ứng dụng bổ sung query parameter như `?format=json`, cần quy định rõ cách nó tương tác với `Accept`, default format, lỗi format không hợp lệ và cache key. Không tự thêm nhiều cơ chế negotiation chồng lấn nếu không có hợp đồng rõ ràng.

### 10.2. Vendor-specific media type

API có thể dùng media type riêng, ví dụ:

~~~http
Accept: application/vnd.acme.product-v2+json
Content-Type: application/vnd.acme.product-v2+json
~~~

Đây là cách biểu diễn version/profile theo media type. Cần đăng ký mapping và bảo đảm codec có thể đọc/ghi subtype đó. Jackson có thể hỗ trợ nhiều media type JSON tùy cấu hình; hãy kiểm thử thực tế thay vì cho rằng mọi subtype `+json` đều tự động được hỗ trợ trong mọi cấu hình.

Versioning bằng media type cần tài liệu API rõ ràng, quy tắc deprecation và cách client fallback. Không nên dùng media type riêng chỉ để đặt tên tùy ý cho một object JSON không có khác biệt representation.

### 10.3. Problem Details

Lỗi API có thể dùng `application/problem+json` theo Problem Details:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "This endpoint accepts application/json."
}
~~~

Định dạng lỗi là response representation, nên `Accept` và writer vẫn có ý nghĩa. Không trả stack trace, SQL hoặc thông tin nhạy cảm trong trường `detail`.

### 10.4. Cache và `Vary: Accept`

Nếu cùng một URI trả JSON khi client gửi `Accept: application/json` và trả text khi client gửi `Accept: text/plain`, representation phụ thuộc vào request header `Accept`. Cache trung gian cần biết điều đó:

~~~http
Vary: Accept
~~~

`Vary` hướng dẫn cache phân biệt các biến thể response theo header. Nếu nội dung còn phụ thuộc `Accept-Language`, cache policy cần phản ánh header đó nữa. Không thêm `Vary` một cách máy móc cho mọi endpoint; chỉ khai báo các header thực sự ảnh hưởng representation.

Cũng cần thiết kế `Cache-Control`, ETag và authorization phù hợp. Content negotiation không tự giải quyết cache invalidation hoặc rò rỉ dữ liệu giữa người dùng.

## 11. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Ứng dụng dưới đây có ba endpoint:

- `GET /api/product`: chỉ trả JSON.
- `GET /api/plain`: chỉ trả text/plain.
- `POST /api/echo`: nhận JSON và trả JSON.

Ví dụ thể hiện rõ `Accept` quyết định định dạng response, còn `Content-Type` quyết định định dạng request body được chấp nhận. Project dùng Spring Boot **3.5.7** và Java 17.

### 11.1. Cấu trúc project

~~~text
webflux-content-negotiation/
├── pom.xml
└── src/main/java/example/negotiation/
    ├── ContentNegotiationApplication.java
    └── NegotiationController.java
└── src/test/java/example/negotiation/
    └── NegotiationIntegrationTest.java
~~~

### 11.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-content-negotiation</artifactId>
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

### 11.3. `ContentNegotiationApplication.java`

~~~java
package example.negotiation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContentNegotiationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ContentNegotiationApplication.class, args);
    }
}
~~~

### 11.4. `NegotiationController.java`

~~~java
package example.negotiation;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class NegotiationController {

    public record ProductView(String id, String name, int price) {}

    public record CreateProduct(String name, int price) {}

    public record Receipt(String id, String name, int price) {}

    @GetMapping(
        path = "/product",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ProductView> product() {
        return Mono.just(
            new ProductView("P-1", "Keyboard", 120));
    }

    @GetMapping(
        path = "/plain",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> plain() {
        return Mono.just("plain response");
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Receipt> echo(
        @RequestBody Mono<CreateProduct> body
    ) {
        return body.map(input -> new Receipt(
            "R-" + input.name(),
            input.name(),
            input.price()
        ));
    }
}
~~~

Các endpoint cố ý chỉ công bố media type mà writer tương ứng hỗ trợ. `/echo` dùng `consumes` để giới hạn request JSON và `produces` để giới hạn response JSON. `/product` minh họa response JSON; `/plain` minh họa response text.

### 11.5. Chạy ứng dụng

Cài JDK 17+ và Maven, sau đó chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

**Request 1 — yêu cầu JSON:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: application/json"
~~~

Response chính dự kiến:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body:

~~~json
{"id":"P-1","name":"Keyboard","price":120}
~~~

**Request 2 — yêu cầu text cho endpoint chỉ hỗ trợ JSON:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: text/plain"
~~~

Kết quả dự kiến: **406 Not Acceptable**, vì mapping chỉ khai báo `produces=application/json`.

**Request 3 — yêu cầu text ở endpoint text:**

~~~bash
curl -i http://localhost:8080/api/plain \
  -H "Accept: text/plain"
~~~

Response chính dự kiến:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
~~~

Body:

~~~text
plain response
~~~

**Request 4 — gửi JSON và nhận JSON:**

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Pen","price":15}'
~~~

Response chính dự kiến:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

Body:

~~~json
{"id":"R-Pen","name":"Pen","price":15}
~~~

**Request 5 — gửi sai Content-Type:**

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data "name=Pen&price=15"
~~~

Kết quả dự kiến: **415 Unsupported Media Type**, vì endpoint chỉ nhận JSON. Việc client chấp nhận JSON response không thay đổi điều kiện đọc request body.

**Request 6 — gửi JSON đúng nhưng không chấp nhận JSON response:**

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -H "Accept: text/plain" \
  -d '{"name":"Pen","price":15}'
~~~

Kết quả dự kiến: **406 Not Acceptable**, vì request body có media type đúng nhưng response mapping chỉ tạo JSON.

**Request 7 — dùng wildcard:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: application/*"
~~~

JSON tương thích với `application/*`, nên request có thể nhận response JSON.

**Request 8 — quality value:**

~~~bash
curl -i http://localhost:8080/api/product \
  -H "Accept: application/json;q=0.9, text/plain;q=0.4"
~~~

Endpoint chỉ cung cấp JSON; JSON là representation được chấp nhận nên request thành công. `q` không khiến server tạo ra một định dạng mà endpoint không hỗ trợ.

### 11.6. Kiểm thử bằng `WebTestClient`

Tạo file test sau. Dependency `spring-boot-starter-test` đã có trong `pom.xml`:

~~~java
package example.negotiation;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.http.MediaType.TEXT_PLAIN;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class NegotiationIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptsJsonRepresentation() {
        client.get()
            .uri("/api/product")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void rejectsUnacceptableResponseType() {
        client.get()
            .uri("/api/product")
            .accept(TEXT_PLAIN)
            .exchange()
            .expectStatus()
            .isEqualTo(HttpStatus.NOT_ACCEPTABLE);
    }

    @Test
    void rejectsUnsupportedRequestContentType() {
        client.post()
            .uri("/api/echo")
            .contentType(TEXT_PLAIN)
            .accept(APPLICATION_JSON)
            .bodyValue("name=Pen&price=15")
            .exchange()
            .expectStatus()
            .isEqualTo(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
    }

    @Test
    void decodesJsonAndWritesJson() {
        client.post()
            .uri("/api/echo")
            .contentType(APPLICATION_JSON)
            .accept(APPLICATION_JSON)
            .bodyValue(new NegotiationController.CreateProduct(
                "Pen", 15))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("R-Pen")
            .jsonPath("$.price").isEqualTo(15);
    }

    @Test
    void acceptsPlainTextAtPlainEndpoint() {
        client.get()
            .uri("/api/plain")
            .accept(TEXT_PLAIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("plain response");
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Các test kiểm tra hợp đồng HTTP thực tế: media type request, media type response, status code và body. Nếu đổi codec, dependency hoặc mapping, các test này sẽ giúp phát hiện sự thay đổi.

## 12. Cách chẩn đoán khi negotiation không hoạt động

Khi gặp 406 hoặc 415, kiểm tra theo thứ tự:

1. **Xem request header thực tế:** client có gửi đúng `Accept` và `Content-Type` không? Công cụ như curl, browser DevTools hoặc HTTP client log có thể cho biết giá trị thực.
2. **Kiểm tra endpoint mapping:** `consumes` và `produces` có giới hạn media type nào? Có mapping khác cùng path/method không?
3. **Kiểm tra kiểu tham số/return:** controller yêu cầu DTO nào, trả object nào, hay Publisher của kiểu gì?
4. **Kiểm tra codec:** có `HttpMessageReader` để decode request type và `HttpMessageWriter` để encode response type không?
5. **Kiểm tra media type parameter:** charset, boundary multipart hoặc parameter tùy chỉnh có tương thích không?
6. **Kiểm tra lỗi thực tế:** 400 do body malformed khác 415 do media type không hỗ trợ; 404 do không có route khác 406 do response representation không được chấp nhận.
7. **Kiểm tra functional predicate:** `accept`/`contentType` false có thể khiến route không match; nếu cần 406/415, xem fallback route.
8. **Kiểm tra proxy/cache:** tầng trung gian có thể sửa header hoặc cache response theo thiếu `Vary`.

Đừng sửa bằng cách bỏ mọi điều kiện `consumes`/`produces` ngay lập tức. Những điều kiện này có thể đang bảo vệ hợp đồng API. Hãy xác định header nào sai hoặc codec nào còn thiếu.

## 13. Lỗi phổ biến và cách phòng tránh

**Lỗi 1 — Dùng `Content-Type` để yêu cầu response JSON.** Content-Type mô tả body đang gửi. Dùng `Accept: application/json` để nói client muốn nhận JSON.

**Lỗi 2 — Dùng `Accept` để mô tả request body JSON.** Server đọc body theo Content-Type và reader/decoder. Gửi `Content-Type: application/json`.

**Lỗi 3 — Nghĩ hai header phải giống nhau.** Client có thể gửi JSON và muốn text response. Hai header độc lập theo hai chiều.

**Lỗi 4 — Nhầm `consumes` với `produces`.** consumes khớp Content-Type request; produces khớp Accept/representation response.

**Lỗi 5 — Khai báo `produces=application/xml` nhưng không có XML writer.** Mapping không cài codec. Cần đăng ký writer/encoder thực sự hỗ trợ kiểu Java đó.

**Lỗi 6 — Nghĩ `Accept: */*` bắt server trả JSON.** Wildcard chấp nhận mọi media type; nó không thể hiện ưu tiên JSON. Nếu muốn ưu tiên JSON, gửi media range JSON với q phù hợp.

**Lỗi 7 — Nghĩ `q=0.9` nghĩa là 90% request sẽ dùng JSON.** Đây là quality weight trong negotiation, không phải xác suất hoặc tỷ lệ traffic.

**Lỗi 8 — Bỏ qua `q=0`.** Media type với q=0 bị loại khỏi tập representation được chấp nhận.

**Lỗi 9 — Sắp xếp media range chỉ theo q mà bỏ qua specificity.** Range cụ thể có thể chi phối range wildcard; cần để framework xử lý negotiation hoặc tuân thủ đầy đủ quy tắc HTTP.

**Lỗi 10 — Nhầm 415 với 400.** 415 là media type request không được hỗ trợ; 400 thường là body đúng loại nhưng parse/validation không thành công.

**Lỗi 11 — Nhầm 406 với 404.** 406 là endpoint/handler có thể tồn tại nhưng không tạo representation phù hợp; 404 thường là không có route/resource phù hợp.

**Lỗi 12 — Cho rằng functional route predicate tự động tạo 406/415.** Predicate false làm route không khớp; hãy thêm fallback route hoặc ánh xạ status rõ ràng.

**Lỗi 13 — Gửi Content-Type trên GET rồi kỳ vọng chọn JSON response.** Dùng Accept. Content-Type chỉ hữu ích khi request có body cần mô tả.

**Lỗi 14 — Bỏ qua codec khi thêm media type vào mapping.** Mapping chỉ là điều kiện; reader/writer phải thực sự hỗ trợ định dạng.

**Lỗi 15 — Nghĩ mọi Flux response đều stream từng item.** JSON array có thể được aggregate; dùng NDJSON/SSE khi giao thức cần stream.

**Lỗi 16 — Không thêm `Vary: Accept` khi cache nhiều representation.** Cache có thể trả nhầm biến thể nếu nội dung phụ thuộc Accept mà cache không phân biệt.

**Lỗi 17 — Dùng content negotiation như cơ chế xác thực.** Accept/Content-Type do client kiểm soát và không chứng minh danh tính hoặc quyền. Dùng Spring Security và xác thực dữ liệu độc lập.

**Lỗi 18 — Trả lỗi kỹ thuật thô cho client.** 406/415 response nên có error code/message an toàn; log chi tiết ở server, không lộ stack trace hay cấu hình nội bộ.

## 14. Bài tập tự kiểm tra

1. `Content-Type` mô tả điều gì? **Định dạng representation của request body hiện tại.**
2. `Accept` mô tả điều gì? **Các media type client chấp nhận trong response.**
3. Client gửi JSON và muốn nhận text thì hai header có thể là gì? **`Content-Type: application/json` và `Accept: text/plain`.**
4. `consumes` tương ứng với header nào? **Content-Type.**
5. `produces` tương ứng với header nào? **Accept và representation response.**
6. `Accept: application/*` có chấp nhận `application/json` không? **Có.**
7. `Accept: */*` có nghĩa server bắt buộc trả JSON không? **Không; mọi media type đều được chấp nhận, server chọn representation phù hợp.**
8. `q=0` có ý nghĩa gì? **Media range đó không được chấp nhận.**
9. Khi client gửi `Accept: text/plain` nhưng endpoint chỉ produces JSON, status thường gặp là gì? **406 Not Acceptable.**
10. Khi client gửi `Content-Type: text/plain` nhưng endpoint chỉ consumes JSON, status thường gặp là gì? **415 Unsupported Media Type.**
11. JSON malformed nhưng Content-Type đúng thường là lỗi gì? **400 Bad Request.**
12. Có thể khai báo `produces=application/xml` mà không cần XML writer không? **Không; mapping không tự tạo codec.**
13. Trong WebFlux, interface nào đọc request body? **HttpMessageReader.**
14. Interface nào ghi response body? **HttpMessageWriter.**
15. `RequestPredicates.accept` kiểm tra header nào? **Accept.**
16. `RequestPredicates.contentType` kiểm tra header nào? **Content-Type.**
17. Functional predicate không match có tự bảo đảm 406/415 không? **Không; nó làm route không match, cần fallback/status mapping nếu muốn mã lỗi cụ thể.**
18. Khi cùng URI có nhiều representation phụ thuộc Accept, cache nên biết điều gì? **Thêm `Vary: Accept` nếu response thực sự thay đổi theo header đó.**
19. `Content-Encoding: gzip` có giống `Content-Type: application/json` không? **Không; một bên mô tả nén byte, bên kia mô tả định dạng representation.**
20. Nếu server hỗ trợ JSON nhưng client gửi `Accept: application/json;q=0` và không có media range phù hợp khác, kết quả có thể là gì? **406 Not Acceptable.**

## 15. Ghi nhớ và tài liệu tham khảo

- **`Content-Type`** nói định dạng body request đang gửi; **`Accept`** nói định dạng response client chấp nhận.
- **`consumes`** khớp Content-Type; **`produces`** khớp Accept và khả năng tạo response.
- `q` là quality weight từ 0 đến 1; `q=0` loại media range.
- **406** liên quan representation response không được chấp nhận; **415** liên quan media type request không được hỗ trợ; **400** thường liên quan nội dung malformed/không hợp lệ.
- `HttpMessageReader` và decoder đọc request; `HttpMessageWriter` và encoder ghi response.
- Khai báo media type không tự cài codec. Phải có reader/writer tương thích.
- WebFlux.fn dùng predicate `accept` và `contentType`; predicate false có thể làm route không match, nên thiết kế fallback nếu cần status rõ ràng.
- Dùng `Vary: Accept` khi cache representation thay đổi theo Accept.
- Framework quản lý subscription và ghi response; handler nên trả Publisher, không tự subscribe/block.

Tài liệu chính thức:

1. [Spring Framework Reference — Mapping Requests: consumes and produces](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-requestmapping.html): điều kiện mapping, `consumes`, `produces` và media type.
2. [Spring Framework Reference — @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): giải mã request body và `HttpMessageReader`.
3. [Spring Framework Reference — @ResponseBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html): reactive return values và `HttpMessageWriter`.
4. [Spring Framework Reference — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `RequestPredicates.accept`, `contentType`, `ServerRequest` và `ServerResponse`.
5. [Spring Framework Reference — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): `ServerCodecConfigurer`, codec mặc định và tùy chỉnh.
6. [RFC 9110 — HTTP Semantics, Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#name-content-negotiation): semantics của Accept, Content-Type, media range, quality value và Vary.
