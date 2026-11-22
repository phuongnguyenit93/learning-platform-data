# HttpMessageReader, HttpMessageWriter và bộ codec trong Spring WebFlux

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Spring WebFlux cần chuyển đổi giữa **luồng byte HTTP** và **các giá trị Java** trong mô hình reactive.
2. Phân biệt các hợp đồng **Decoder/Encoder** của Spring Core với **HttpMessageReader/HttpMessageWriter** của tầng HTTP.
3. Theo dõi luồng đọc @RequestBody, ghi @ResponseBody và ResponseEntity, cũng như thao tác bodyToMono/bodyToFlux trong WebFlux.fn và WebClient.
4. Mô tả vai trò của **DataBuffer**, Reactive Streams, backpressure, JSON codec, String codec, binary, form/multipart và Server-Sent Events.
5. Dự đoán việc lựa chọn reader/writer dựa vào kiểu Java, Content-Type, Accept, produces/consumes, và phân biệt HTTP 400, 406, 415.
6. Cấu hình bộ codec mặc định qua **ServerCodecConfigurer**, **WebFluxConfigurer**, **CodecCustomizer** và thuộc tính Spring Boot 3.3.
7. Nhận biết khi nào cần streaming thay vì buffer toàn bộ body, cách quản lý giới hạn bộ nhớ và tài nguyên pooled buffer.
8. Tạo ứng dụng Spring Boot 3.3.x / Java 17+ minh họa JSON, text, binary, JSON streaming, SSE, functional endpoint; kiểm thử bằng WebTestClient.

**Phạm vi:** Spring WebFlux trong Spring Framework 6.1.x, sử dụng Reactor Mono/Flux, Spring Boot 3.3.x và Java 17+. Bài áp dụng cho cả WebFlux annotation controller lẫn WebFlux.fn. Spring MVC sử dụng **HttpMessageConverter** đồng bộ; các lớp trong bài thuộc một pipeline khác.

## 1. Bài toán: HTTP mang byte, ứng dụng làm việc với object

Xét HTTP request:

~~~http
POST /api/notes HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"Reactive Spring"}
~~~

Ở tầng mạng, HTTP body là các byte được truyền đến server. Controller lại cần một record Java:

~~~java
public record NoteInput(String title) {}
~~~

Phản hồi có thể là một Note DTO:

~~~java
public record Note(long id, String title) {}
~~~

Để xử lý, server cần:

- **Decode** byte JSON của request thành NoteInput.
- Chạy logic controller/service.
- **Encode** Note thành byte JSON của response.
- Chọn media type và headers phù hợp để client hiểu dữ liệu.

Ở Spring MVC, lớp trung tâm là HttpMessageConverter, thường làm việc với InputStream/OutputStream. **WebFlux** xử lý non-blocking body dưới dạng **Publisher<DataBuffer>**, nên sử dụng các reader/writer và codec hỗ trợ Reactive Streams.

Ví dụ tổng quan:

~~~text
HTTP body bytes
  |
  v
Flux<DataBuffer>          // data đến theo các buffer
  |
  v
HttpMessageReader
  |
  v
Decoder (Jackson/String/...)
  |
  v
Mono<NoteInput> hoặc Flux<NoteInput>
  |
  v
Controller / service (Publisher<Note>)
  |
  v
HttpMessageWriter
  |
  v
Encoder (Jackson/String/...)
  |
  v
Publisher<DataBuffer>
  |
  v
HTTP response bytes
~~~

Sơ đồ thể hiện khái niệm: một số reader/writer có xử lý chuyên biệt và không nhất thiết luôn bọc một Encoder hoặc Decoder theo đúng một kiểu. Điểm chính là WebFlux đọc và ghi body dưới dạng **luồng có thể phát tín hiệu dữ liệu, hoàn tất, lỗi và hủy**.

## 2. Bốn khái niệm cốt lõi

### Encoder<T> — chuyển object thành DataBuffer

Encoder thuộc package:

~~~java
org.springframework.core.codec.Encoder<T>
~~~

Nó nhận Publisher các giá trị và tạo ra Publisher<DataBuffer> theo kiểu dữ liệu và định dạng được yêu cầu. Encoding không nhất thiết biết HTTP request/response cụ thể.

Ví dụ: Jackson2JsonEncoder chuyển Note Java thành byte JSON. StringEncoder biến chuỗi thành byte theo charset. Không nên tưởng mọi Encoder đều có khả năng ghi mọi media type.

### Decoder<T> — chuyển DataBuffer thành object

Decoder thuộc:

~~~java
org.springframework.core.codec.Decoder<T>
~~~

Nó nhận Publisher<DataBuffer> và chuyển thành giá trị Java: một Mono<T> cho trường hợp decodeToMono, hoặc Flux<T> cho luồng nhiều phần tử khi định dạng cho phép.

Ví dụ: Jackson2JsonDecoder dùng Jackson để đọc JSON thành DTO. Với định dạng có nhiều JSON object tách dòng, codec thích hợp có thể phát lần lượt các object, thay vì buffer thành một chuỗi JSON khổng lồ.

### HttpMessageReader<T> — đọc HTTP body

HttpMessageReader nằm ở:

~~~java
org.springframework.http.codec.HttpMessageReader<T>
~~~

Nó kết hợp đọc HTTP message, headers, media type, body publisher và decoding thành Java. Một triển khai thông dụng là **DecoderHttpMessageReader**, bọc một Decoder.

Reader xử lý tình huống @RequestBody, @RequestPart hoặc các lời gọi như ServerRequest.bodyToMono và WebClient response.bodyToMono (tùy reader được chọn). Nó không tự thực thi validation nghiệp vụ hay authorize người dùng.

### HttpMessageWriter<T> — ghi HTTP body

HttpMessageWriter nằm ở:

~~~java
org.springframework.http.codec.HttpMessageWriter<T>
~~~

Nó kết hợp HTTP response headers với việc encode các giá trị Java thành byte. Một triển khai thường gặp là **EncoderHttpMessageWriter**, bọc Encoder.

Writer tham gia ghi @ResponseBody, ResponseEntity<T>, ServerResponse.bodyValue/body, WebClient request.bodyValue/body và các trường hợp streaming.

Bảng phân biệt:

| Cấp | Đọc | Ghi | Quan tâm đến HTTP? |
|---|---|---|---|
| Spring Core codec | Decoder<T> | Encoder<T> | Không bắt buộc |
| Spring HTTP codec | HttpMessageReader<T> | HttpMessageWriter<T> | Có: media type, headers, message |
| WebFlux controller | @RequestBody, request argument resolver | @ResponseBody, ResponseEntity | MVC-style annotation |
| WebFlux.fn | ServerRequest.bodyToMono/bodyToFlux | ServerResponse.bodyValue/body | Functional API |
| WebClient | ClientResponse.bodyToMono/bodyToFlux | RequestHeadersSpec.bodyValue/body | HTTP client |

**Không đồng nhất** HttpMessageReader với Reader của java.io hoặc HttpMessageWriter với Writer của java.io. Chúng là chiến lược đọc/ghi dữ liệu HTTP reactive theo kiểu Java và media type.

## 3. DataBuffer và vai trò của Reactive Streams

Các transport adapter, ví dụ Reactor Netty, cung cấp dữ liệu yêu cầu thành nhiều khối nhỏ theo thời gian. Spring dùng **DataBuffer** để trừu tượng hóa các dạng bộ nhớ byte như Netty ByteBuf hoặc java.nio.ByteBuffer.

Một body 5 MB không nhất thiết được đưa tới ứng dụng thành một mảng byte[] duy nhất. Nó có thể đi qua một Publisher<DataBuffer> với nhiều đợt dữ liệu.

~~~text
Network socket
   |
   +---- DataBuffer 1
   +---- DataBuffer 2
   +---- DataBuffer 3
   +---- ... 
   |
   v
Flux<DataBuffer> -> decoder -> Flux<T> / Mono<T>
~~~

Reactive Streams quy định cách Publisher và Subscriber giao tiếp qua request(n), onNext, onError, onComplete và cancel:

- **Demand/backpressure** cho phép consumer thể hiện lượng dữ liệu muốn nhận.
- **Cancellation** cho phép ngừng chuỗi khi client hủy kết nối hoặc xử lý bị hủy.
- **Error signal** mang lỗi parse, I/O hoặc xử lý.
- **Completion** cho biết body/chuỗi hoàn tất.

**Backpressure không đồng nghĩa bộ nhớ tự động vô hạn hoặc luôn bằng 0.** Một codec khi cần tạo một object từ toàn bộ document có thể phải buffer dữ liệu để parse. Với streaming format thích hợp, codec có thể phát item dần khi đủ dữ liệu.

### DataBuffer có thể được pooled

Reactor Netty thường dùng các buffer có tham chiếu và được pool quản lý. Khi tự xử lý DataBuffer ở cấp thấp, ứng dụng phải đảm bảo release đúng lúc, nhất là các buffer bị bỏ qua khi filter, error hoặc cancel.

Thư viện Spring có DataBufferUtils.release(DataBuffer) và những helper liên quan. Một số codec chuẩn quản lý tài nguyên giúp bạn, nhưng khi tự tạo pipeline cấp thấp, cần tuân thủ contract ownership. Không được vừa release sớm rồi còn đọc buffer, cũng không được giữ buffer không giới hạn sau khi request đã hủy.

Hầu hết REST API thông thường nên trả DTO/record hoặc Mono/Flux DTO và **để codec của Spring quản lý DataBuffer**, thay vì xử lý raw buffer thủ công.

## 4. HttpMessageReader làm việc ở đâu trong annotated controller?

Đường vào với @RequestBody:

~~~text
Client sends Content-Type: application/json
        |
        v
Netty/Tomcat reactive adapter
        |
        v
WebFlux HttpHandler -> WebFilter chain
        |
        v
DispatcherHandler
        |
        v
RequestMappingHandlerMapping
        |
        v
RequestMappingHandlerAdapter
        |
        v
Argument resolver for @RequestBody
        |
        +--> Chọn HttpMessageReader theo ResolvableType + Content-Type
                    |
                    +--> Decode body Publisher<DataBuffer>
                    |
                    +--> Mono<NoteInput> hoặc giá trị Java phù hợp
        |
        v
Controller method
~~~

Ví dụ:

~~~java
@PostMapping(
    path = "/api/notes",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Note> create(@RequestBody Mono<NoteInput> request) {
    return request.map(input -> new Note(1, input.title()));
}
~~~

Đây là snippet bên trong một controller, cần imports và package phù hợp. Các bước:

1. Route và consumes condition được xét.
2. Spring nhìn kiểu tham số **Mono<NoteInput>**, hiểu phần tử body là NoteInput.
3. Spring chọn reader có thể đọc NoteInput từ application/json.
4. Reader/decoder xử lý body non-blocking.
5. Controller nhận Mono<NoteInput>; mã trong map chạy khi publisher được subscribed, không phải khi chỉ tạo Mono.
6. Khi một giá trị hợp lệ được decode, controller tạo Note mới.

**Không cần gọi subscribe() trong controller.** WebFlux runtime thực hiện việc subscribe, điều phối subscription và viết response. Subscribe thủ công thường làm mất khả năng điều phối error/cancel và tạo side effect ngoài luồng request.

### Mono<T> và Flux<T> khác nhau ở đâu?

- **Mono<T>:** tối đa một giá trị hoặc complete rỗng/lỗi; phù hợp một JSON object hoặc nội dung đơn.
- **Flux<T>:** nhiều giá trị theo thời gian; phù hợp các định dạng phân mảnh như NDJSON, SSE hoặc một luồng item.
- **Publisher<DataBuffer>:** luồng dữ liệu byte ở mức thấp.

Không phải cứ khai báo Flux<T> là response chắc chắn truyền từng T ngay lập tức. Format JSON array, buffering, network/proxy, compression và client đều ảnh hưởng đến thời điểm byte xuất hiện.

## 5. HttpMessageWriter xử lý kết quả của controller

Đường ra phổ biến:

~~~text
Controller returns Mono<Note> / Flux<Note>
        |
        v
Return-value handling
        |
        v
Chọn HttpMessageWriter theo Java element type,
Accept, produces và supported media types
        |
        v
Encoder chuyển value -> DataBuffer
        |
        v
ServerHttpResponse headers + body
        |
        v
Reactive HTTP server gửi bytes
~~~

Ví dụ:

~~~java
@GetMapping(
    path = "/api/notes/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Note> find(@PathVariable long id) {
    return Mono.just(new Note(id, "demo"));
}
~~~

Nếu Jackson JSON codec được đăng ký, Note được serialize thành JSON object. Kết quả body có ý nghĩa tương đương:

~~~json
{"id":5,"title":"demo"}
~~~

với GET /api/notes/5. Thứ tự field và whitespace trong JSON do Jackson configuration quyết định; đừng khẳng định tất cả môi trường trả byte-for-byte giống ví dụ.

### @RestController và ResponseEntity

Trong WebFlux, @RestController cũng bao gồm semantics @ResponseBody. Có thể trả trực tiếp Mono<Note>, Flux<Note> hoặc Mono<ResponseEntity<Note>>.

~~~java
@PostMapping("/api/items")
public Mono<ResponseEntity<Note>> create(
        @RequestBody Mono<NoteInput> input) {
    return input.map(value ->
            ResponseEntity.status(201)
                    .body(new Note(1, value.title())));
}
~~~

ResponseEntity điều khiển **status và headers**; message writer vẫn quyết định **cách ghi body** nếu có body.

**Lưu ý:** Nếu dùng ResponseEntity<Mono<T>> hoặc Mono<ResponseEntity<T>>, thời điểm xác định headers/status có khác nhau; Spring Framework hỗ trợ nhiều cách reactive return, nhưng nên dùng một kiểu rõ ràng và test thật để tránh điều khiển response sau khi đã commit.

## 6. Content-Type và Accept: reader và writer nhìn hai hướng khác nhau

| Header | Được gửi bởi | Tác động chính |
|---|---|---|
| Request Content-Type | Client | Reader chọn cách giải mã body mà client gửi |
| Request Accept | Client | Writer chọn loại response client chấp nhận |
| Response Content-Type | Server | Cho client biết kiểu byte thực tế server trả |
| Response Content-Length / Transfer-Encoding | Server/transport | Liên quan cách truyền body, không phải quy tắc decode DTO |

Ví dụ:

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Reactive Spring"}
~~~

- Reader xem Content-Type: application/json cùng target type NoteInput.
- Writer xem Accept: application/json, produces condition và kiểu Note để chọn JSON.
- Không có nghĩa Request Content-Type và Response Content-Type phải giống nhau: server có thể nhận JSON rồi trả text/plain hoặc binary nếu contract endpoint cho phép.

### consumes và produces

~~~java
@PostMapping(
    path = "/api/notes",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

- **consumes** ràng buộc media type request được handler chấp nhận.
- **produces** ràng buộc media type mà handler tuyên bố có thể trả và tương tác với Accept.
- Reader/writer vẫn phải thực sự hỗ trợ các kiểu dữ liệu đó.

Một annotation produces=application/pdf không thể tự biến record thành PDF nếu thiếu logic tạo PDF byte và writer phù hợp.

### Các mã lỗi dễ nhầm

| Trường hợp | Lỗi thường thấy |
|---|---|
| JSON request malformed, không decode thành DTO | 400 Bad Request |
| Body required=true nhưng thiếu | 400 Bad Request |
| Validation trên body đã decode thất bại | 400 Bad Request (có thể theo exception handling tùy cấu hình) |
| Client gửi text/plain nhưng endpoint chỉ consumes application/json | 415 Unsupported Media Type |
| Client chỉ Accept text/plain còn endpoint chỉ produces application/json | 406 Not Acceptable |
| Body cần aggregate vượt giới hạn buffer | DataBufferLimitException; HTTP status cần xác định theo cấu hình/exception mapping thực tế |
| Server encode/write thất bại sau khi đã commit response | Có thể đứt stream; không bảo đảm đổi thành JSON lỗi |

**415 liên quan input media type, 406 liên quan output representation.** Không sửa 406 bằng cách đổi Content-Type của request hoặc sửa 415 bằng cách đổi Accept một cách máy móc.

## 7. Bộ codec mặc định gồm những loại nào?

WebFlux có thể đăng ký codec theo framework và thư viện có trên classpath. Không tồn tại một danh sách cứng giống nhau cho mọi ứng dụng.

| Dữ liệu | Reader/Decoder hoặc Writer/Encoder thường gặp | Media type điển hình |
|---|---|---|
| JSON object, JSON array | DecoderHttpMessageReader + Jackson2JsonDecoder; EncoderHttpMessageWriter + Jackson2JsonEncoder | application/json, application/*+json |
| NDJSON stream | Jackson JSON codec với streaming media type | application/x-ndjson |
| Plain text | StringDecoder, CharSequenceEncoder/String writer phù hợp | text/plain |
| Binary | ByteArrayDecoder/Encoder hoặc DataBuffer codec | application/octet-stream |
| Resource | ResourceDecoder/ResourceHttpMessageWriter | file/binary media phù hợp |
| Form | FormHttpMessageReader, FormHttpMessageWriter | application/x-www-form-urlencoded |
| Multipart | MultipartHttpMessageReader, MultipartHttpMessageWriter và part handlers | multipart/form-data |
| Server-Sent Events | ServerSentEventHttpMessageWriter | text/event-stream |
| XML, CBOR, Protobuf và codec khác | Khi có module/dependency và registration hỗ trợ | Media type tương ứng |

Tên implementation phản ánh tầng khác nhau: một **decoder thấp** có thể được bọc trong **HTTP message reader**; không nhất thiết mọi hàng đều tương ứng đúng một lớp cho hai chiều.

Trong Spring Boot starter-webflux thông thường, Jackson JSON codec có sẵn qua dependency do starter quản lý. Khi thiếu thư viện cần thiết hoặc cấu hình codec đã bị thay thế, endpoint có thể không đọc/ghi được media type đó.

### Codec cho JSON có phải mapper Jackson không?

**ObjectMapper** là thư viện xử lý JSON; **Jackson2JsonEncoder/Decoder** tích hợp Jackson với DataBuffer/Reactive Streams; **HttpMessageReader/Writer** tích hợp codec với HTTP.

~~~text
Java object / JSON bytes
        ^
        |
  Jackson ObjectMapper
        ^
        |
Jackson2JsonEncoder / Jackson2JsonDecoder
        ^
        |
HTTP message writer / reader
        ^
        |
WebFlux request/response body pipeline
~~~

Đổi cấu hình Jackson có thể ảnh hưởng serialization JSON, nhưng không trực tiếp biến StringDecoder, multipart reader hoặc binary writer thành Jackson converter.

## 8. Streaming: JSON array, NDJSON và SSE khác nhau

Giả sử server có Flux<Note> phát ba item, mỗi item cách nhau 250 ms.

### application/json: một JSON document

Response thông thường:

~~~json
[{"id":1,"title":"n-1"},{"id":2,"title":"n-2"},{"id":3,"title":"n-3"}]
~~~

Đây là **một JSON array**. Writer có thể tạo JSON document theo dạng phù hợp với collection stream, nhưng client parse toàn bộ array có thể chỉ đưa kết quả cho ứng dụng sau khi document hoàn tất. Đừng mặc định ba lần onNext ứng với ba lần browser nhận một JSON object riêng.

### application/x-ndjson: từng JSON object trên một dòng

~~~text
{"id":1,"title":"n-1"}
{"id":2,"title":"n-2"}
{"id":3,"title":"n-3"}
~~~

Mỗi dòng là một JSON object độc lập. Với codec hỗ trợ streaming NDJSON và client đọc luồng, các object có thể được xử lý theo từng phần ngay khi dữ liệu đến. Không có dấu ngoặc vuông bao cả document. NDJSON hữu ích cho log/events hoặc batch item streaming.

### text/event-stream: Server-Sent Events

~~~text
id: 1
event: note
data: {"id":1,"title":"n-1"}

id: 2
event: note
data: {"id":2,"title":"n-2"}

~~~

SSE có quy tắc frame riêng: mỗi sự kiện gồm các dòng như id, event, data, cách nhau bằng một dòng trống. Data của SSE có thể là text hoặc JSON đã encode. Browser EventSource có thể nhận sự kiện theo stream; JSON parse nội dung data do client quyết định.

**Khác biệt:** NDJSON là một stream nhiều JSON document theo dòng; SSE là giao thức sự kiện qua HTTP. Nếu ghi một chuỗi có dấu xuống dòng và gắn text/event-stream, chưa chắc đã tạo một SSE event hợp lệ. Dùng ServerSentEvent<T> hoặc writer SSE chuẩn khi cần framing.

### Không đồng nhất Flux với streaming end-to-end

Streaming có thể bị ảnh hưởng bởi:

- HTTP message writer và cách encoder flush.
- Buffer của reverse proxy, CDN hoặc gateway.
- Nén HTTP và chính sách chunking.
- Client library sử dụng bodyToMono hoặc bodyToFlux.
- Media type của response và khả năng parse từng phần.
- Timeout và cancellation.

Phải kiểm tra bằng một client thật như curl -N, WebTestClient hoặc browser EventSource, đồng thời thử khi có proxy ở giữa.

## 9. Luồng WebFlux.fn cũng dùng cùng hệ reader/writer

WebFlux.fn là API functional routing: RouterFunction, HandlerFunction, ServerRequest và ServerResponse.

Ví dụ:

~~~java
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
        RequestPredicates.POST("/functional/echo"),
        request -> request.bodyToMono(NoteInput.class)
            .flatMap(input -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new Note(1, input.title())))
    );
}
~~~

Đây là snippet cần đặt trong @Bean của một @Configuration hoặc @SpringBootApplication với imports phù hợp. ServerRequest.bodyToMono sử dụng các **message readers** để decode body. ServerResponse.bodyValue sử dụng các **message writers** để encode giá trị.

Vì vậy, **cấu hình codec của WebFlux phục vụ cả annotation controllers và functional endpoints**, mặc dù cú pháp xử lý request khác nhau. Đừng nhầm WebFlux.fn với một web server hoặc một codec riêng biệt.

## 10. WebClient là HTTP client reactive, cũng sử dụng codec

Không chỉ server. **WebClient** nhận body từ HTTP response của server khác và encode body mà nó gửi trong HTTP request.

~~~text
Server-side WebFlux:
  Incoming HTTP request -> HttpMessageReader -> Java values
  Java values -> HttpMessageWriter -> HTTP response

WebClient:
  Java values -> HttpMessageWriter -> outgoing HTTP request
  Incoming HTTP response -> HttpMessageReader -> Java values
~~~

Ví dụ:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("http://localhost:8080")
    .build();

Mono<Note> note = client.get()
    .uri("/api/notes/{id}", 5)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(Note.class);
~~~

Đây là snippet cho component có import WebClient, Note và Mono phù hợp. Tạo Mono không tự gửi request; HTTP request xảy ra khi publisher có subscriber (ví dụ WebFlux runtime subscribe vào publisher được trả về từ handler).

### Tránh block event loop

**Không** gọi .block() trong WebFlux request path chỉ để biến Mono thành object đồng bộ. Điều đó có thể chặn event-loop, gây lỗi hoặc làm giảm thông lượng. Khi cần gọi API downstream, giữ chuỗi reactive bằng flatMap/map và timeout thích hợp.

Một ví dụ logic:

~~~java
Mono<Note> result = client.get()
    .uri("/api/notes/{id}", 5)
    .retrieve()
    .bodyToMono(Note.class)
    .map(note -> new Note(note.id(), note.title().toUpperCase()));
~~~

Đây là phép biến đổi dữ liệu, chưa tự thực hiện request khi chưa được subscribe. Hệ thống WebFlux sẽ subscribe cho pipeline mà controller trả về.

### Server codec và client codec có thể khác cấu hình

Spring Boot có thể tùy chỉnh WebClient.Builder do Boot tự cấu hình. Nếu bạn tự gọi WebClient.create() hoặc tự dựng builder độc lập, không nên mặc định nó nhận mọi tùy chỉnh từ Boot.

Khi custom riêng WebClient, có thể dùng:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs().maxInMemorySize(512 * 1024))
    .build();
~~~

Đây là snippet cấu hình độc lập, chỉ ảnh hưởng WebClient instance tạo ra từ builder đó. Không đồng nghĩa đổi toàn bộ reader/writer server.

## 11. Cấu hình giới hạn buffer: max-in-memory-size

Một số decoder phải buffer dữ liệu để chuyển thành một object; nếu không có giới hạn, body lớn có thể chiếm nhiều memory. WebFlux codec có ngưỡng buffering.

### Dấu hiệu thường gặp

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Lỗi này thường xuất hiện khi một codec cần giữ vượt quá giới hạn được cấu hình (mặc định nhiều codec ở Spring Framework khoảng **256 KiB**). Không nên suy ra mọi request vượt 256 KiB đều thất bại: còn phụ thuộc reader, kiểu dữ liệu, streaming/aggregation và cấu hình.

### Cấu hình bằng Spring Boot 3.3 property

Trong src/main/resources/application.yml:

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
~~~

Spring Boot 3.3 mô tả spring.codec.max-in-memory-size là giới hạn byte được buffer khi cần aggregate input. Nó tác động đến WebFlux server và **WebClient do Boot tự cấu hình**, không tự động áp dụng cho mọi WebClient tạo riêng ngoài Boot.

Đây **không** phải giới hạn upload HTTP tổng quát, cũng không thay thế giới hạn request size của proxy/server. Việc tăng lên vài chục MB có thể làm tăng tiêu thụ bộ nhớ khi có nhiều request đồng thời. Hãy cân nhắc streaming, giới hạn kích thước body và giới hạn concurrency thay vì chỉ tăng số.

### Cấu hình qua WebFluxConfigurer

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

Đây là một **class cấu hình bổ sung trong dự án WebFlux**, code có thể biên dịch với starter-webflux phù hợp. Nó áp dụng cho server-side WebFlux codecs. Nếu đã đặt property spring.codec.max-in-memory-size, không cần tự tạo configurer chỉ để lặp cùng ý định.

### Cấu hình qua CodecCustomizer

Spring Boot 3.3 có interface:

~~~java
org.springframework.boot.web.codec.CodecCustomizer
~~~

Một cấu hình:

~~~java
import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CodecCustomizerConfiguration {

    @Bean
    CodecCustomizer tuneCodecs() {
        return configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(512 * 1024);
    }
}
~~~

Đây là cấu hình bổ sung trong project Spring Boot 3.3. Spring Boot sẽ áp dụng CodecCustomizer cho các codec được Boot tự cấu hình theo cơ chế liên quan. Đừng bật cùng lúc nhiều customizer/property có giá trị mâu thuẫn mà không biết thứ tự áp dụng.

**Chú ý phiên bản:** ở Spring Boot 4.x, tên package và một số property codec đã thay đổi; ví dụ này được khóa vào Boot 3.3 để tránh sao chép nhầm API.

## 12. Bộ codec cấu hình bằng ServerCodecConfigurer

**ServerCodecConfigurer** cung cấp các nhóm codec:

- **defaultCodecs():** tinh chỉnh các reader/writer mặc định như Jackson hoặc maxInMemorySize.
- **customCodecs():** đăng ký reader/writer/encoder/decoder riêng.
- **getReaders()/getWriters():** lấy danh sách cuối cùng theo configuration để WebFlux sử dụng.
- **registerDefaults(boolean):** có thể bật/tắt default codecs tùy nhu cầu.

Ví dụ quan sát code:

~~~java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
~~~

Khi cần hỗ trợ media type như application/x-custom:

1. Xác định **kiểu dữ liệu Java** cần đọc/ghi.
2. Định nghĩa media type rõ ràng.
3. Dùng Decoder/Encoder phù hợp hoặc viết implementation an toàn.
4. Có thể bọc decoder bằng **DecoderHttpMessageReader** và encoder bằng **EncoderHttpMessageWriter**, rồi đăng ký vào customCodecs().
5. Đảm bảo canDecode/canEncode chỉ trả true cho type/media phù hợp.
6. Kiểm thử request, response, lỗi parse, cancellation và trường hợp codec khác không bị cướp quyền.

Nếu codec custom hỗ trợ mọi Object và mọi media type, nó có thể chiếm nhiệm vụ của Jackson JSON, String, binary hoặc Resource codec. Chọn codec **hẹp và có test tương thích**.

### Có nên tắt default codecs?

Tài liệu Spring Boot có ví dụ:

~~~java
configurer.registerDefaults(false);
~~~

Đây là câu lệnh hợp lệ trong hàm cấu hình; nó có thể dùng khi xây danh sách codec hoàn toàn riêng. **Không dùng như cách thêm một codec đơn lẻ**: tắt mặc định có thể khiến JSON, String, multipart, SSE hoặc binary ngừng hoạt động nếu chưa đăng ký lại đầy đủ.

### Không dùng @EnableWebFlux tùy tiện

Spring Boot tự cấu hình WebFlux và codecs nếu dependencies phù hợp. Để bổ sung cấu hình, tạo @Configuration implements WebFluxConfigurer **không cần** @EnableWebFlux. @EnableWebFlux yêu cầu bạn tự kiểm soát phần lớn cấu hình Spring WebFlux và có thể làm lùi các tiện ích của Boot.

Tương tự, nếu project có cả starter-web và starter-webflux, **Spring MVC thường được ưu tiên theo mặc định**. Khi đó phần customizer WebFlux server có thể không áp dụng cho server thực tế. Kiểm tra web application type và dependency graph trước khi kết luận codec bị lỗi.

## 13. Jackson codec: DTO, generics, date/time và security

### ObjectMapper vẫn quyết định JSON representation

Jackson2JsonDecoder và Jackson2JsonEncoder phụ thuộc vào ObjectMapper và các module Jackson. Ví dụ record:

~~~java
public record Event(long id, String label) {}
~~~

có thể được encode thành:

~~~json
{"id":2,"label":"demo"}
~~~

Cấu hình Jackson như property naming, serialization inclusion hoặc module cho java.time sẽ thay đổi cách JSON được đọc/ghi. Spring Boot có các property spring.jackson.* và customizer cho Jackson; nên tận dụng thay vì thay nguyên bộ codec khi chỉ cần đổi một quy tắc JSON.

### Generic type có ý nghĩa

WebFlux dùng **ResolvableType**, chứ không chỉ Class<?> đơn giản, để mô tả kiểu phần tử có generic như Mono<List<Event>> hoặc Flux<Event>. Các codec có thể kiểm tra kiểu Java và media type trước khi decode/encode.

~~~java
Mono<List<Event>> fullList;
Flux<Event> events;
~~~

Đây là hai khai báo loại dữ liệu, không phải chương trình chạy. Một JSON array hoàn chỉnh thường phù hợp với List<Event>; một stream nhiều object như NDJSON phù hợp Flux<Event> khi codec streaming hỗ trợ.

### Đừng serialize domain entity trực tiếp

Entity có thể có token, password hash, quan hệ lazy-loading hoặc vòng tham chiếu. Codec JSON sẽ áp dụng cấu hình serializer hiện có, nên bạn cần **response DTO** chỉ chứa dữ liệu công khai. Cũng cần kiểm tra giới hạn kích thước request, chiều sâu lồng JSON và validation của input.

### Không đồng nhất lỗi deserialize với lỗi nghiệp vụ

JSON malformed có thể khiến decoder tạo DecodingException hoặc lỗi được framework chuyển thành response HTTP 400. Một JSON hợp lệ nhưng title trống có thể qua decode rồi bị Bean Validation từ chối. Một title hợp lệ nhưng xung đột dữ liệu là lỗi nghiệp vụ cần xử lý riêng, có thể là 409 Conflict.

## 14. Multipart, form, streaming file và dữ liệu lớn

### Form

Với application/x-www-form-urlencoded, WebFlux có reader cho form data. Functional API có thể dùng ServerRequest.formData(); annotated handlers có thể dùng @RequestParam khi phù hợp.

Đừng giả định application/x-www-form-urlencoded là JSON. Đặt @RequestBody Mono<DTO> với Content-Type form sẽ không tự làm Jackson đọc form thành DTO.

### Multipart

WebFlux có các kiểu như Part, FilePart và hỗ trợ multipart codecs. Có thể xử lý part metadata bằng @RequestPart và file bằng FilePart:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    return file.transferTo(
            java.nio.file.Path.of("/tmp/received-file.bin")
    ).thenReturn("uploaded");
}
~~~

Đây là **snippet minh họa** trong @RestController có các import phù hợp; giả sử đường dẫn hợp lệ/ghi được và không có hai request cùng ghi một file. Không sử dụng trực tiếp filename từ client làm đường dẫn lưu; ứng dụng thực tế cần tên file an toàn, kiểm tra MIME, size, quyền truy cập và chính sách storage.

Với multipart stream lớn, WebFlux còn hỗ trợ **Flux<PartEvent>**, cho phép xử lý theo phần mà không buộc tập hợp toàn bộ multipart. Cần giải phóng DataBuffer đúng contract khi tự xử lý từng event.

### Phân biệt giới hạn bộ nhớ của codec và multipart

Spring Boot 3.3 có nhiều property khác nhau, ví dụ:

~~~yaml
spring:
  codec:
    max-in-memory-size: 512KB
  webflux:
    multipart:
      max-in-memory-size: 256KB
      max-disk-usage-per-part: 10MB
      max-parts: 20
~~~

Đây là **giá trị minh họa**, phải lựa chọn theo nhu cầu thực tế. spring.codec.max-in-memory-size điều khiển buffering khi codec cần aggregate; các thuộc tính spring.webflux.multipart.* quản lý giới hạn cụ thể cho multipart reader. Không kỳ vọng thay một property sẽ thay thế mọi giới hạn khác.

Trong môi trường sản xuất, thường cần thêm giới hạn của reverse proxy, gateway, transport và storage quota.

## 15. Ví dụ hoàn chỉnh: JSON, text, bytes, NDJSON, SSE và functional route

Phần thực hành này dùng Spring Boot 3.3.x, Java 17+, starter-webflux và Reactor Netty. Mỗi ví dụ controller dùng API WebFlux; không cần Servlet, DispatcherServlet hoặc HttpMessageConverter.

### 15.1. Dependencies

Trong project Gradle Spring Boot đã thiết lập plugin và repositories:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây chỉ là phần dependencies của build.gradle. Không thêm spring-boot-starter-web vào project thực hành này, vì khi cả hai starter hiện diện, Boot mặc định chọn MVC thay vì WebFlux.

### 15.2. Java application

Tạo file **src/main/java/com/example/webfluxcodec/CodecLessonApplication.java**:

~~~java
package com.example.webfluxcodec;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.http.codec.ServerSentEvent;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class CodecLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecLessonApplication.class, args);
    }

    public record NoteInput(String title) {}
    public record Note(long id, String title) {}

    @RestController
    static class NoteController {

        private final AtomicLong ids = new AtomicLong();

        @PostMapping(
                path = "/api/notes",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        @ResponseStatus(HttpStatus.CREATED)
        Mono<Note> create(@RequestBody Mono<NoteInput> body) {
            return body.map(input ->
                    new Note(ids.incrementAndGet(), input.title()));
        }

        @GetMapping(
                path = "/api/notes/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<Note> get(@PathVariable long id) {
            return Mono.just(new Note(id, "sample-" + id));
        }

        @PostMapping(
                path = "/api/text",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        Mono<String> text(@RequestBody Mono<String> body) {
            return body.map(String::toUpperCase);
        }

        @GetMapping(
                path = "/api/bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        Mono<byte[]> bytes() {
            return Mono.just(
                    "ABC".getBytes(StandardCharsets.US_ASCII));
        }

        @GetMapping(
                path = "/api/notes/ndjson",
                produces = MediaType.APPLICATION_NDJSON_VALUE
        )
        Flux<Note> ndjson() {
            return Flux.range(1, 3)
                    .delayElements(Duration.ofMillis(250))
                    .map(i -> new Note(i, "stream-" + i));
        }

        @GetMapping(
                path = "/api/notes/sse",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE
        )
        Flux<ServerSentEvent<Note>> sse() {
            return Flux.range(1, 3)
                    .delayElements(Duration.ofMillis(250))
                    .map(i -> ServerSentEvent.<Note>builder()
                            .id(Integer.toString(i))
                            .event("note")
                            .data(new Note(i, "stream-" + i))
                            .build());
        }
    }

    @Bean
    RouterFunction<ServerResponse> functionalRoute() {
        return RouterFunctions.route(
                RequestPredicates.POST("/functional/echo"),
                request -> request.bodyToMono(NoteInput.class)
                        .flatMap(input -> ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new Note(100, input.title())))
        );
    }
}
~~~

**Giải thích:**

- @RestController sử dụng WebFlux annotation handler adapter; JSON body đi qua reactive reader/writer, không qua HttpMessageConverter.
- POST /api/notes nhận Mono<NoteInput> rồi tạo Mono<Note>. Một JSON object hợp lệ được Jackson decoder chuyển thành NoteInput.
- GET /api/notes/{id} là endpoint minh họa, trả Note tạo từ id nhận vào; **không có database**, không nên xem đây là CRUD storage thật.
- POST /api/text dùng String codec để nhận/trả text/plain; String::toUpperCase phụ thuộc locale mặc định, nên bài test sử dụng ASCII đơn giản.
- GET /api/bytes trả ba byte ASCII A, B, C dưới application/octet-stream.
- GET /api/notes/ndjson trả nhiều Note dưới dạng NDJSON streaming.
- GET /api/notes/sse trả SSE có id/event/data và cấu trúc framing do writer SSE quản lý.
- FunctionalRoute cho thấy ServerRequest.bodyToMono và ServerResponse.bodyValue cũng dùng WebFlux codec.
- Flux.range và delayElements tạo nguồn dữ liệu in-memory, không phải I/O network thực tế. Trong ứng dụng production, nên dùng repository/client reactive phù hợp; tránh chặn event loop.

**Phạm vi chạy:** đây là một Java source file hoàn chỉnh trong **dự án Spring Boot 3.3.x có dependency starter-webflux**; không chạy javac độc lập khi chưa có classpath Spring/Reactor/Jackson.

### 15.3. Cấu hình application.yml

Tạo file **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  codec:
    max-in-memory-size: 512KB
~~~

Đây là mức buffer minh họa. Với các response NDJSON/SSE hữu hạn, mục tiêu là để người học quan sát streaming. Không cần tự đăng ký codec JSON khi starter-webflux đã cung cấp Jackson theo auto-configuration.

### 15.4. Chạy ứng dụng

Tại thư mục project Gradle:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 15.5. Thử JSON request/response

Trên Linux/macOS:

~~~bash
curl -i -X POST http://localhost:8080/api/notes \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Reactive Spring"}'
~~~

Một response điển hình cho request đầu:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":1,"title":"Reactive Spring"}
~~~

Status 201 là do @ResponseStatus(CREATED). ID là 1 khi đây là request tạo đầu tiên của tiến trình mới; khi đã gọi nhiều lần, id tăng. Thứ tự headers và JSON fields có thể khác.

Trên Windows PowerShell, cách tránh khác biệt quote JSON giữa các bản PowerShell là tạo file **note.json** có nội dung:

~~~json
{"title":"Reactive Spring"}
~~~

rồi chạy:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/notes -H "Content-Type: application/json" -H "Accept: application/json" --data-binary "@note.json"
~~~

Trong cùng môi trường, kiểm tra GET:

~~~bash
curl -s http://localhost:8080/api/notes/5
~~~

Body tương đương:

~~~json
{"id":5,"title":"sample-5"}
~~~

### 15.6. Thử text và binary

Text:

~~~bash
curl -s -X POST http://localhost:8080/api/text \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data 'hello'
~~~

Body chính xác của ví dụ với ASCII:

~~~text
HELLO
~~~

Binary:

~~~bash
curl -s http://localhost:8080/api/bytes
~~~

Body gồm byte 0x41 0x42 0x43, tương đương ASCII:

~~~text
ABC
~~~

Để kiểm tra binary trong ứng dụng thực tế, lưu ra file rồi đối chiếu kích thước/hash thay vì in dữ liệu không phải text ra terminal.

### 15.7. Thử NDJSON và SSE

NDJSON:

~~~bash
curl -N -H 'Accept: application/x-ndjson' \
  http://localhost:8080/api/notes/ndjson
~~~

Dữ liệu có ý nghĩa tương đương:

~~~text
{"id":1,"title":"stream-1"}
{"id":2,"title":"stream-2"}
{"id":3,"title":"stream-3"}
~~~

SSE:

~~~bash
curl -N -H 'Accept: text/event-stream' \
  http://localhost:8080/api/notes/sse
~~~

Dữ liệu có dạng:

~~~text
id:1
event:note
data:{"id":1,"title":"stream-1"}

id:2
event:note
data:{"id":2,"title":"stream-2"}

id:3
event:note
data:{"id":3,"title":"stream-3"}

~~~

Ký tự khoảng trắng sau dấu hai chấm, trình tự và cách flush frame có thể do serializer và version điều chỉnh. Điểm kiểm thử quan trọng là **ba sự kiện có id/event/data và body JSON đúng nội dung**.

Functional route:

~~~bash
curl -s -X POST http://localhost:8080/functional/echo \
  -H 'Content-Type: application/json' \
  --data '{"title":"function"}'
~~~

Body tương đương:

~~~json
{"id":100,"title":"function"}
~~~

## 16. Kiểm thử WebFlux codec bằng WebTestClient

Thêm test vào **src/test/java/com/example/webfluxcodec/CodecLessonApplicationTests.java**:

~~~java
package com.example.webfluxcodec;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CodecLessonApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void jsonBodyIsDecodedAndEncoded() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "demo"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.title").isEqualTo("demo");
    }

    @Test
    void rejectsRequestMediaTypeOtherThanJson() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isEqualTo(
                        HttpStatus.UNSUPPORTED_MEDIA_TYPE);
    }

    @Test
    void rejectsUnacceptableResponseType() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue(Map.of("title", "demo"))
                .exchange()
                .expectStatus().isEqualTo(HttpStatus.NOT_ACCEPTABLE);
    }

    @Test
    void badJsonGetsBadRequest() {
        client.post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{bad-json")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void textIsUppercased() {
        client.post()
                .uri("/api/text")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("HELLO");
    }

    @Test
    void ndjsonResponseHasStreamingMediaType() {
        client.get()
                .uri("/api/notes/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON);
    }
}
~~~

Dự án Spring Boot sử dụng Gradle wrapper:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Các test xác nhận: JSON reader và writer, text reader/writer, 415, 406, 400 và NDJSON Content-Type. Chúng kiểm tra hành vi WebFlux thật thay vì đoán một lớp codec chỉ bằng tên.

**Phạm vi test:** WebTestClient ở WebEnvironment.RANDOM_PORT thực hiện HTTP request đến embedded server thực. Nếu chỉ dùng bindToController hay bindToApplicationContext, test không mở TCP socket; cả hai cách đều hữu ích nhưng kiểm tra tầng khác nhau.

Không phụ thuộc thứ tự JSON fields hoặc khoảng trắng response. Với SSE streaming dài hạn, có thể dùng WebTestClient.returnResult(...).getResponseBody() cùng StepVerifier và timeout để xác nhận từng event và cancellation; tránh để test vô hạn.

## 17. Cách đọc lỗi 400/406/415 trong WebFlux

### 400 Bad Request

Nguyên nhân thường gặp:

- JSON malformed.
- Kiểu field không tương thích với target DTO.
- Body bắt buộc nhưng vắng mặt.
- Bean Validation thất bại trên giá trị đã decode.

Ví dụ:

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json

{bad-json
~~~

Jackson decoder không thể parse cú pháp nên WebFlux xử lý lỗi đọc body, thường trả HTTP 400. Phần error body do error handler và cấu hình Boot quyết định, không nên ghi cứng vào test.

### 415 Unsupported Media Type

~~~http
POST /api/notes HTTP/1.1
Content-Type: text/plain

hello
~~~

Endpoint chỉ consumes application/json. Handler không chấp nhận representation đó, hoặc reader không đọc được kiểu đích từ text/plain; HTTP 415 là phản hồi phù hợp.

### 406 Not Acceptable

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json
Accept: text/plain

{"title":"ok"}
~~~

Endpoint chỉ produces application/json. Client chỉ chấp nhận text/plain, nên server không thể chọn representation phù hợp và trả 406.

### Buffer limit và DataBufferLimitException

Nếu request JSON lớn hơn mức một codec được phép aggregate, có thể gặp DataBufferLimitException. Không cam kết status mặc định luôn là 413; status thực tế phụ thuộc exception mapping, codec, framework và thời điểm response commit. Khi cần API contract riêng cho body quá lớn, nên cấu hình giới hạn ở gateway/server cùng exception handler phù hợp.

### Encoding error

Serialization có thể lỗi khi DTO có getter ném exception, dữ liệu không tương thích JSON hoặc có vòng tham chiếu. Khi response đã stream một phần, không còn luôn có thể thay status/body cho toàn bộ response. Cần theo dõi log của server và tín hiệu lỗi trên client.

## 18. Reader/Writer không thay thế validation và nghiệp vụ

Codec chỉ làm việc giữa **representation** và **Java data**, không tự xử lý:

- Authentication/authorization.
- Database transaction và persistence.
- Business invariants như tồn kho, thanh toán, trạng thái workflow.
- Giới hạn tần suất hoặc chống lạm dụng.
- Chính sách lọc dữ liệu nhạy cảm.
- Timeout của downstream services.

Nếu dùng Bean Validation:

~~~java
public record CreateInput(
        @jakarta.validation.constraints.NotBlank String title
) {}
~~~

Khi được dùng với @Valid @RequestBody Mono<CreateInput> và dependency spring-boot-starter-validation, framework có thể kiểm tra constraint sau khi decode. Validation exception trong WebFlux có thể là WebExchangeBindException hoặc HandlerMethodValidationException tùy loại ràng buộc và controller method.

Đừng nhầm **decode thành công** với **input hợp lệ cho nghiệp vụ**.

## 19. Cách quan sát reader/writer trong runtime

Nếu debug khó hiểu, có thể quan sát danh sách đọc/ghi của một ServerCodecConfigurer được cấu hình. Ví dụ minh họa đặt trong cấu hình WebFlux:

~~~java
import org.springframework.http.codec.ServerCodecConfigurer;

ServerCodecConfigurer configurer = ServerCodecConfigurer.create();
System.out.println(configurer.getReaders().size());
System.out.println(configurer.getWriters().size());
~~~

Đây là **snippet minh họa về API**, không phải code kiểm tra trực tiếp chính xác codec registry của context đang chạy. Một configurer tự tạo không nhất thiết chứa toàn bộ customizer của Spring Boot, vì Boot có thể áp dụng properties và bean customization riêng.

Để quan sát registry trong ứng dụng đang chạy, lấy cấu hình codec mà framework thật sự dùng hoặc debug ServerCodecConfigurer, WebFluxConfigurer và CodecCustomizer beans. In danh sách codec của một configurer mới rồi cho rằng đó là cấu hình Boot runtime có thể dẫn đến chẩn đoán sai.

### Log và metric

Cân nhắc các thông tin:

- HTTP Content-Type request, Accept và Content-Type response.
- Kiểu Java đích/kiểu trả về.
- Route có consumes/produces condition nào.
- Codec nào đọc/ghi khi trace/debug.
- Lỗi decode/encode và root cause.
- Phản hồi 400/406/415, p95 latency và bộ nhớ.
- Số lượng request đồng thời và response đang stream.

Không bật body logging nhạy cảm hoặc DEBUG/TRACE cho toàn bộ production vô thời hạn. Property spring.codec.log-request-details kiểm soát việc logging request details cho codec (có thể bao gồm form hoặc headers), nên phải có chính sách log phù hợp.

## 20. Sai lầm thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| WebFlux dùng HttpMessageConverter giống Spring MVC | WebFlux dùng HttpMessageReader/Writer và codecs |
| Decoder/Encoder giống hoàn toàn Reader/Writer | Reader/Writer thêm ngữ cảnh HTTP và media type |
| Có Flux nghĩa là luôn streaming từng item tới client | Writer/media type, proxy và client có thể buffer |
| Tăng maxInMemorySize là cách duy nhất xử lý body lớn | Có thể thiết kế streaming, limit, multipart/file path |
| JSON codec tự validate business rules | Decoder chỉ đọc representation; validation/service xử lý rule |
| ResponseEntity loại bỏ nhu cầu writer | Body trong ResponseEntity vẫn cần encode |
| WebClient tạo Mono là đã gửi HTTP request | Reactive request thường cần subscription |
| Gọi block() trong WebFlux event loop là tiện và an toàn | Có thể block/hỏng throughput, nên giữ non-blocking pipeline |
| Dùng Content-Type request để yêu cầu response JSON | Accept mới thể hiện response preference |
| @EnableWebFlux luôn bắt buộc để tùy chỉnh codec | WebFluxConfigurer trong Boot thường không cần @EnableWebFlux |
| registerDefaults(false) chỉ thêm một codec | Nó có thể loại bỏ defaults, gây thiếu JSON/String/SSE |
| Cấu hình codec server tự động áp dụng mọi WebClient tạo riêng | Cần phân biệt auto-configured builder và custom client |
| DataBuffer tự động được release khi tự giữ trong collection | Pooled buffer cần owner rõ ràng và cleanup theo contract |

## 21. Quy trình chẩn đoán theo thứ tự

Khi endpoint trả sai media type hoặc không decode được:

1. **Kiểm tra stack thực tế:** Boot đã chọn REACTIVE hay SERVLET? Nếu có cả starter-web và starter-webflux, mặc định thường là MVC.
2. **Kiểm tra route:** path/method/consumes/produces có khớp request không?
3. **Kiểm tra Content-Type và Accept:** header đến server sau proxy có đúng như client gửi không?
4. **Kiểm tra Java type:** @RequestBody là NoteInput, Mono<NoteInput>, Flux<NoteInput> hay String? Writer nhận DTO, Mono, Flux, Resource hay byte[]?
5. **Kiểm tra registry:** Jackson/String/multipart/SSE codec còn được đăng ký không? Có custom codec quá rộng hoặc registerDefaults(false) không?
6. **Kiểm tra lỗi cụ thể:** malformed body (400), media type input (415), output (406), buffer limit hoặc serialize exception.
7. **Kiểm tra streaming:** response Content-Type, codec có flush theo item không, proxy có buffer không, client có đọc bodyToFlux hay gom thành một bodyToMono không?
8. **Kiểm tra resource:** pooled DataBuffer có bị leak, prefetch quá cao hoặc subscribe thủ công ngoài lifecycle không?
9. **Kiểm tra tests:** thêm WebTestClient để xác nhận status/body/media type; dùng StepVerifier khi cần chứng minh emission/cancellation.

Tránh tăng bộ nhớ vô hạn hoặc tắt toàn bộ codec mặc định khi chưa tìm được nguyên nhân cụ thể.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Decoder và HttpMessageReader có cùng trách nhiệm không?

**Đáp án:** Không hoàn toàn. Decoder chuyển DataBuffer thành dữ liệu Java ở cấp thấp; HttpMessageReader tích hợp decoding với HTTP headers, media type và message body.

**Câu 2.** Một controller trả Flux<Note> với produces=application/json. Có đảm bảo client nhận từng Note như NDJSON?

**Đáp án:** Không. JSON array và NDJSON có representation khác nhau; chỉ Flux không quyết định format/flush. Nếu muốn các JSON object độc lập theo dòng, chọn application/x-ndjson và codec/client hỗ trợ.

**Câu 3.** Client gửi JSON hợp lệ với Content-Type=text/plain tới endpoint chỉ consumes JSON. Lỗi điển hình?

**Đáp án:** 415 Unsupported Media Type vì media type khai báo không phù hợp với contract endpoint.

**Câu 4.** Khi cần format response, nên thay Reader hay Writer?

**Đáp án:** Writer/Encoder phụ trách response body; Reader/Decoder phụ trách request body. Một codec custom có thể cung cấp cả hai nếu format cần đọc và ghi.

**Câu 5.** Tại sao tăng spring.codec.max-in-memory-size lên 50 MB cho mọi endpoint có thể nguy hiểm?

**Đáp án:** Khi nhiều request đồng thời cần aggregate, tổng lượng memory bị buffer có thể tăng mạnh. Cần cân nhắc streaming, giới hạn kích thước và concurrency.

**Câu 6.** Tại sao WebClient.builder().build() tạo thủ công có thể khác builder do Boot inject?

**Đáp án:** Các customizer/properties của Boot được áp dụng theo cơ chế auto-configuration. Một builder tạo trực tiếp có thể không nhận những giá trị đó, nên phải cấu hình instance tương ứng.

**Câu 7.** Có nên tự gọi subscribe() để “chạy nhanh hơn” trong @RestController?

**Đáp án:** Không. WebFlux runtime quản lý subscription/cancellation cho pipeline response; tự subscribe có thể tách side effect khỏi request lifecycle.

**Câu 8.** Một response SSE là một JSON array thông thường?

**Đáp án:** Không. SSE có framing id/event/data và các dòng trống ngăn sự kiện. Trường data có thể chứa JSON nhưng toàn bộ response không phải một JSON array.

**Câu 9.** Vì sao một DataBuffer bị bỏ qua trong filter có thể cần cleanup?

**Đáp án:** Buffer có thể là pooled/ref-counted. Khi custom pipeline nhận quyền sở hữu rồi bỏ một buffer, cần release theo contract để không leak tài nguyên.

**Câu 10.** Khi project có cả starter-web và starter-webflux, bạn sẽ chỉnh CodecCustomizer WebFlux trước hay kiểm tra stack?

**Đáp án:** Trước tiên xác định web application type. Boot thường chọn Spring MVC khi cả hai starter có mặt; codec WebFlux server có thể không nằm trên đường xử lý request thực tế.

## 23. Checklist triển khai

- [ ] Đã xác nhận ứng dụng thực sự chạy WebFlux và chọn đúng web stack.
- [ ] Request Content-Type và response Accept/produces mô tả media type rõ ràng.
- [ ] DTO public/record và JSON serialization được kiểm soát, không lộ entity nhạy cảm.
- [ ] Chọn Mono<T> cho một item; Flux<T> cho nhiều item hoặc dữ liệu streaming thực sự.
- [ ] Phân biệt JSON array, NDJSON và SSE trong response contract.
- [ ] Có cấu hình max-in-memory-size hợp lý và giới hạn request/multipart tương ứng.
- [ ] Không tự gọi block()/subscribe() trong request path nếu không có lý do đặc biệt được kiểm soát.
- [ ] Custom codec hỗ trợ kiểu/media type đủ hẹp và giữ default codecs trừ khi có chủ đích.
- [ ] Tách cấu hình server-side WebFlux codecs khỏi WebClient được xây dựng riêng.
- [ ] Có test 400, 406, 415, JSON/text/binary và streaming media types.
- [ ] Khi xử lý DataBuffer thô, quản lý release/cancel/error đúng contract.
- [ ] Đã kiểm tra proxy và client nếu cần streaming end-to-end.
- [ ] Có tài liệu API và logging/metric để chẩn đoán lỗi decode hoặc encode.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Reactive Web Applications: HTTP Codecs with HttpMessageReaders and HttpMessageWriters](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Boot 3.3 — Common Application Properties (spring.codec.*, spring.webflux.multipart.*)](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
