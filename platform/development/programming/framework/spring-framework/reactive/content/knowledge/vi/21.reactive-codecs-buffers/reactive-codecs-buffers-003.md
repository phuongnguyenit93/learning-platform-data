# JSON, chuỗi, dữ liệu nhị phân và media type tương ứng trong Spring WebFlux

## 1. Codec giải quyết vấn đề gì?

HTTP truyền dữ liệu qua network dưới dạng byte. Ứng dụng Java thường làm việc với object, String, byte array, Resource hoặc Publisher. Spring WebFlux cần một lớp chuyển đổi giữa hai thế giới đó: **codec**.

Ví dụ:

- Client gửi JSON bytes với Content-Type là application/json; WebFlux đọc bytes, dùng JSON decoder để tạo Java object.
- Controller trả một record Java; JSON encoder chuyển object thành bytes JSON để gửi cho client.
- Endpoint trả String; String encoder ghi nội dung văn bản với media type phù hợp.
- Endpoint trả byte[] hoặc Resource; binary/resource writer ghi nội dung nhị phân.
- Endpoint trả Flux<Item>; writer có thể ghi từng phần tử theo định dạng streaming phù hợp.

Codec là phần cốt lõi của request/response body trong Spring WebFlux. Nó ảnh hưởng đến:

- Dữ liệu nào có thể đọc hoặc ghi.
- Java type nào tương ứng với media type nào.
- Body được buffer thành một object hay stream từng phần.
- Giới hạn bộ nhớ khi gom dữ liệu.
- Cách xử lý JSON, text, binary, form, multipart, NDJSON và Server-Sent Events.
- Cách cấu hình server và WebClient để hai phía dùng cùng contract.

## 2. Pipeline đọc và ghi dữ liệu

WebFlux xây dựng các abstraction theo từng tầng:

~~~text
HTTP request bytes
      |
      v
DataBuffer
      |
      v
HttpMessageReader
      |
      v
Decoder
      |
      v
Java object / Mono / Flux
      |
      v
Controller hoặc HandlerFunction
      |
      v
Java object / Publisher
      |
      v
Encoder
      |
      v
HttpMessageWriter
      |
      v
DataBuffer
      |
      v
HTTP response bytes
~~~

Khi đọc request, WebFlux chọn một `HttpMessageReader` có thể đọc Java type và Content-Type của request. Reader thường sử dụng `Decoder` để chuyển byte content thành object hoặc publisher.

Khi ghi response, WebFlux chọn `HttpMessageWriter` tương thích với Java type và media type mà endpoint/client yêu cầu. Writer thường sử dụng `Encoder` để chuyển object thành byte content.

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `Encoder<T>` | Chuyển object thành byte content | Jackson JSON encoder, String encoder |
| `Decoder<T>` | Chuyển byte content thành object | Jackson JSON decoder |
| `HttpMessageReader<T>` | Đọc HTTP body và tạo object/publisher | Đọc JSON request body |
| `HttpMessageWriter<T>` | Ghi object/publisher thành HTTP body | Ghi JSON response |
| `DataBuffer` | Abstraction cho vùng byte buffer | ByteBuffer, Netty ByteBuf |
| `CodecConfigurer` | Đăng ký và cấu hình readers/writers | ServerCodecConfigurer, ClientCodecConfigurer |

`Encoder` và `Decoder` là abstraction chuyển đổi dữ liệu độc lập với HTTP. `HttpMessageReader` và `HttpMessageWriter` bổ sung ngữ cảnh HTTP như header, Content-Type, body và cách đọc/ghi theo Reactive Streams.

Không cần tự gọi encoder/decoder trong controller thông thường. WebFlux chọn codec dựa trên type và media type rồi thực hiện chuyển đổi.

## 3. Content-Type và Accept: hai header không thể nhầm

Hai header này quyết định codec được chọn theo hai hướng khác nhau.

- **Content-Type** mô tả định dạng của body request mà client đang gửi.
- **Accept** mô tả định dạng response mà client muốn nhận.

Ví dụ client gửi JSON và yêu cầu JSON response:

~~~http
POST /api/items
Content-Type: application/json
Accept: application/json

{"id":1,"name":"Keyboard"}
~~~

Server đọc request bằng JSON reader vì Content-Type là application/json. Khi ghi response, server chọn JSON writer vì Accept là application/json và endpoint hỗ trợ định dạng đó.

| Trường hợp | Header | Ý nghĩa |
| --- | --- | --- |
| Request JSON | `Content-Type: application/json` | Body request là JSON |
| Response JSON | `Accept: application/json` | Client chấp nhận JSON |
| Request text | `Content-Type: text/plain` | Body request là văn bản |
| Response text | `Accept: text/plain` | Client muốn văn bản |
| Request binary | `Content-Type: application/octet-stream` | Body request là byte content |
| Response binary | `Accept: application/octet-stream` | Client muốn byte content |

Trong Spring annotation-based controller, có thể giới hạn media type bằng `consumes` và `produces`:

~~~java
@PostMapping(
    value = "/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Item> create(@RequestBody Mono<Item> body) {
    return body;
}
~~~

- Request có Content-Type không được hỗ trợ có thể bị từ chối bằng **415 Unsupported Media Type**.
- Client yêu cầu Accept không tương thích với response endpoint hỗ trợ có thể nhận **406 Not Acceptable**.
- JSON malformed hoặc không decode được có thể dẫn tới lỗi request body như 400 Bad Request tùy exception handling.

Nếu không khai báo consumes/produces, WebFlux vẫn sử dụng các codec mặc định và content negotiation. Khai báo rõ media type giúp contract API dễ hiểu và dễ kiểm thử.

## 4. Bản đồ media type thường gặp

Media type là nhãn mô tả định dạng dữ liệu. Không nên chọn chỉ dựa vào phần mở rộng file; hãy chọn theo representation thực tế của body.

| Dữ liệu | Media type thường dùng | Java type thường gặp |
| --- | --- | --- |
| JSON object/array | `application/json` | DTO, record, Map, List |
| Văn bản thuần | `text/plain` | String |
| HTML | `text/html` | String hoặc Resource |
| XML | `application/xml` hoặc `text/xml` | Object có XML codec, String |
| Byte tổng quát | `application/octet-stream` | byte[], ByteBuffer, DataBuffer, Resource |
| PNG | `image/png` | byte[], Resource, DataBuffer |
| JPEG | `image/jpeg` | byte[], Resource, DataBuffer |
| PDF | `application/pdf` | Resource hoặc byte[] |
| Form URL encoded | `application/x-www-form-urlencoded` | MultiValueMap<String,String> |
| Multipart | `multipart/form-data` | Part, FilePart, MultiValueMap |
| NDJSON | `application/x-ndjson` | Flux<T> |
| JSON Lines | `application/jsonl` | Flux<T> khi codec hỗ trợ media type |
| Server-Sent Events | `text/event-stream` | Flux<ServerSentEvent<T>> |

Các codec mặc định có thể thay đổi theo dependency có trên classpath. Ví dụ, Jackson hỗ trợ JSON; một số codec bổ sung có thể hỗ trợ Smile, JAXB/XML hoặc Protocol Buffers khi thư viện tương ứng được thêm vào.

Không phải mọi Java type đều tự động hỗ trợ mọi media type. Việc chọn codec còn phụ thuộc vào codec được đăng ký, cấu hình, generic type và khả năng encode/decode của nó.

## 5. JSON: object Java và application/json

JSON là định dạng phổ biến để trao đổi dữ liệu API. Trong WebFlux, Jackson thường là codec mặc định khi Jackson có trên classpath, như khi dùng Spring Boot WebFlux starter.

Ví dụ DTO:

~~~java
public record Item(long id, String name) {
}
~~~

Controller nhận và trả JSON:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Item> echo(@RequestBody Mono<Item> item) {
        return item;
    }
}
~~~

Client gửi:

~~~http
POST /api/items
Content-Type: application/json
Accept: application/json

{"id":7,"name":"Monitor"}
~~~

WebFlux decode body thành `Item`, controller nhận `Mono<Item>` và trả lại publisher. JSON writer serialize Item thành response body.

Với body đơn, có thể dùng `Mono<Item>` hoặc `Item` tùy nguồn dữ liệu. Nếu service reactive, hãy giữ publisher và compose bằng `map`/`flatMap`; không gọi `block()` chỉ để lấy object rồi trả về.

### 5.1. JSON object, list và Flux

- `Mono<Item>` thường biểu diễn một JSON object.
- `Mono<List<Item>>` biểu diễn một list đã được tạo/aggregate.
- `Flux<Item>` biểu diễn nhiều item có thể phát theo thời gian.

Với `application/json`, nhiều phần tử thường được ghi thành một JSON array theo semantics của JSON writer. Khi cần mỗi object là một record độc lập và có thể tiêu thụ từng dòng, dùng NDJSON/JSON Lines.

Không nên gom một Flux rất lớn bằng collectList chỉ để trả JSON nếu client có thể xử lý streaming. Việc gom toàn bộ dữ liệu làm tăng bộ nhớ và độ trễ trước khi byte đầu tiên được gửi.

### 5.2. Jackson và kiểu dữ liệu

Spring Boot tự cấu hình Jackson codec khi thư viện có trên classpath. Các kiểu như record, enum, collection và Java time có thể được serialize/deserialize tùy cấu hình ObjectMapper và module được đăng ký.

Nếu cần định dạng JSON đặc biệt, hãy cấu hình ObjectMapper/Jackson builder hoặc serializer/deserializer. Tránh tạo ObjectMapper riêng cho từng request; cấu hình một bean dùng chung.

Ví dụ record có thời gian:

~~~java
public record AuditEvent(
    long id,
    String action,
    Instant createdAt
) {
}
~~~

Với Jackson Java Time module được cấu hình, trường Instant có thể được biểu diễn theo định dạng ISO-8601. Contract nên quy định rõ timezone và format nếu nhiều hệ thống cùng tiêu thụ.

## 6. String và text/plain

String là dữ liệu văn bản, không mặc định là JSON. Nếu endpoint trả chuỗi thông báo hoặc nội dung text, dùng `text/plain`:

~~~java
@GetMapping(
    value = "/message",
    produces = MediaType.TEXT_PLAIN_VALUE
)
Mono<String> message() {
    return Mono.just("Hello WebFlux");
}
~~~

Response có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

Hello WebFlux
~~~

Một số điểm cần nhớ:

- `text/plain` phù hợp với văn bản thuần.
- `text/html` phù hợp với HTML.
- `application/json` phù hợp với JSON representation.
- Charset nên được xác định nhất quán, thông thường là UTF-8.
- Nếu String chứa nội dung JSON, đừng mặc định rằng Spring sẽ coi nó là JSON chỉ vì chuỗi có dấu ngoặc nhọn. Hãy khai báo media type JSON rõ ràng và bảo đảm chuỗi là JSON hợp lệ.

Ví dụ trả JSON string:

~~~java
@GetMapping(
    value = "/raw-json",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<String> rawJson() {
    return Mono.just("{\"status\":\"ok\"}");
}
~~~

Trong ví dụ này, ứng dụng tự chịu trách nhiệm tạo JSON hợp lệ. Với object Java thông thường, nên để Jackson serialize thay vì tự nối chuỗi JSON vì dễ lỗi escaping, encoding và cấu trúc.

## 7. Dữ liệu nhị phân: byte[], ByteBuffer, DataBuffer và Resource

Binary body là byte content không được hiểu như văn bản. Media type phải mô tả đúng nội dung, ví dụ application/octet-stream, image/png hoặc application/pdf.

### 7.1. byte[]

~~~java
@GetMapping(
    value = "/binary",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
Mono<byte[]> binary() {
    byte[] bytes = "BINARY".getBytes(StandardCharsets.UTF_8);
    return Mono.just(bytes);
}
~~~

`byte[]` đơn giản và dễ dùng khi payload nhỏ hoặc đã có sẵn trong bộ nhớ. Nhưng toàn bộ mảng byte phải tồn tại trong heap; không phù hợp để tải file rất lớn nếu dữ liệu có thể được stream từ nguồn.

### 7.2. ByteBuffer

`ByteBuffer` là abstraction của Java NIO cho dữ liệu byte. Codec có thể encode/decode ByteBuffer mà không cần chuyển qua String. Cần chú ý position, limit và việc tái sử dụng buffer vì trạng thái này ảnh hưởng dữ liệu được đọc.

### 7.3. Resource

`Resource` phù hợp khi response là file hoặc một tài nguyên có thể đọc theo stream:

~~~java
@GetMapping(value = "/manual.pdf", produces = MediaType.APPLICATION_PDF_VALUE)
Mono<Resource> manual() {
    Resource file = new FileSystemResource("/srv/app/manual.pdf");
    return Mono.just(file);
}
~~~

`Resource` writer có thể đọc nội dung từ resource theo cách phù hợp với HTTP response. Với file lớn, cách này thường tốt hơn việc đọc toàn bộ file thành byte[] trước khi trả response.

Đường dẫn file nên lấy từ cấu hình đáng tin cậy hoặc storage service; không ghép trực tiếp path do client gửi vào filesystem. Cần kiểm tra quyền truy cập, file tồn tại và loại media type.

### 7.4. DataBuffer

`DataBuffer` là abstraction thấp hơn, gần với byte buffer của transport. Dùng khi cần xử lý byte stream trực tiếp, ví dụ proxy dữ liệu, mã hóa/giải mã riêng hoặc thao tác streaming đặc biệt.

Nếu chỉ cần trả file hoặc byte[] thông thường, ưu tiên Resource/byte[] để codec quản lý buffer. Khi tự tạo hoặc consume DataBuffer, phải hiểu ownership và lifecycle của buffer.

## 8. NDJSON và streaming JSON

NDJSON (newline-delimited JSON) biểu diễn mỗi JSON object trên một dòng. Nó phù hợp với stream gồm nhiều record độc lập.

Ví dụ body:

~~~text
{"id":1,"name":"Mai"}
{"id":2,"name":"An"}
{"id":3,"name":"Binh"}
~~~

Endpoint:

~~~java
@GetMapping(
    value = "/items/stream",
    produces = "application/x-ndjson"
)
Flux<Item> streamItems() {
    return Flux.just(
        new Item(1, "Mai"),
        new Item(2, "An"),
        new Item(3, "Binh")
    );
}
~~~

Khác biệt:

| JSON array | NDJSON |
| --- | --- |
| Một document JSON gồm một array | Mỗi dòng là một JSON document riêng |
| Client thường parse toàn document/array | Client có thể parse từng dòng |
| Phù hợp response list hữu hạn vừa phải | Phù hợp stream record theo thời gian |
| Media type application/json | Thường dùng application/x-ndjson |

Định dạng streaming giúp giảm nhu cầu gom toàn bộ dữ liệu. Tuy nhiên, client và server phải thống nhất framing. Đừng gửi các object JSON nối liền nhau mà không có dấu phân cách và mong client tự đoán ranh giới record.

## 9. Server-Sent Events: text/event-stream

SSE là giao thức server gửi event một chiều tới client qua HTTP. WebFlux có codec hỗ trợ `ServerSentEvent<T>`.

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<String>> events() {
    return Flux.just("connected", "updated")
        .map(value -> ServerSentEvent.builder(value)
            .event("status")
            .build());
}
~~~

SSE thường dùng cho dashboard, notification hoặc cập nhật tiến trình. Một event có thể có:

- `id`: định danh event.
- `event`: loại event.
- `retry`: thời gian retry gợi ý.
- `data`: nội dung payload.
- Comment/heartbeat: giữ kết nối và giúp phát hiện client đã ngắt.

SSE là text protocol với media type text/event-stream; không dùng application/json chỉ vì data bên trong event là JSON. Nếu event chứa object, codec serialize phần data theo cấu hình SSE.

Với stream dài, hãy cân nhắc heartbeat định kỳ. Nếu không có byte nào được gửi trong thời gian dài, proxy hoặc server có thể không phát hiện client đã ngắt sớm. Spring khuyến nghị gửi dữ liệu định kỳ cho streaming response để nhận biết disconnect.

## 10. Form URL encoded và multipart

Không phải mọi HTTP body đều là JSON.

### 10.1. application/x-www-form-urlencoded

Đây là định dạng form đơn giản, dữ liệu được encode thành cặp key/value:

~~~http
POST /login
Content-Type: application/x-www-form-urlencoded

username=mai&remember=true
~~~

Trong functional endpoint, có thể đọc:

~~~java
Mono<ServerResponse> login(ServerRequest request) {
    return request.formData()
        .flatMap(form -> {
            String username = form.getFirst("username");
            String remember = form.getFirst("remember");
            return ServerResponse.ok()
                .bodyValue("user=" + username + ", remember=" + remember);
        });
}
~~~

`formData()` trả về Mono của MultiValueMap. Việc parse có thể aggregate form content, vì vậy vẫn chịu giới hạn bộ nhớ phù hợp.

### 10.2. multipart/form-data

Multipart phù hợp với upload file kèm metadata:

~~~http
POST /upload
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="description"

Profile photo
--boundary
Content-Disposition: form-data; name="file"; filename="photo.png"
Content-Type: image/png

...binary bytes...
--boundary--
~~~

Trong WebFlux controller, có thể nhận `FilePart`:

~~~java
@PostMapping(
    value = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<ResponseEntity<Void>> upload(
        @RequestPart("file") FilePart file) {

    return uploadService.store(file)
        .thenReturn(ResponseEntity.accepted().build());
}
~~~

`FilePart` cung cấp filename, headers và nội dung theo kiểu reactive. Service nên ghi file vào thư mục/storage được cấu hình, tạo tên file phía server và kiểm tra dung lượng, loại file, quyền truy cập. Không tin filename do client gửi.

Với functional endpoint:

~~~java
Mono<ServerResponse> upload(ServerRequest request) {
    return request.multipartData()
        .flatMap(parts -> {
            Part file = parts.getFirst("file");
            return uploadService.store(file)
                .then(ServerResponse.accepted().build());
        });
}
~~~

Multipart có các giới hạn riêng như số part, kích thước header, dung lượng part giữ trong RAM và dung lượng ghi ra disk. Cấu hình giới hạn phù hợp với use case upload.

## 11. Buffering, maxInMemorySize và DataBufferLimitException

Một số codec cần gom dữ liệu trước khi decode/encode. Ví dụ:

- Đọc request thành byte[] hoặc một JSON object lớn.
- Đọc form URL encoded.
- Đọc một phần multipart.
- Tách một stream thành các record JSON/delimited text.

Để tránh dữ liệu lớn chiếm bộ nhớ không giới hạn, codec có giới hạn buffer. Các codec mặc định thường có mức 256 KB cho những trường hợp cần aggregate, nhưng giới hạn thực tế phụ thuộc codec và cấu hình. Khi vượt giới hạn, ứng dụng có thể nhận `DataBufferLimitException` với thông báo vượt max bytes to buffer.

**Tăng giới hạn không phải cách chữa cho mọi lỗi.** Trước tiên hãy xem body có cần aggregate hay có thể stream. Nếu payload lớn hợp lệ, chọn cách đọc/ghi từng phần tử hoặc Resource/FilePart thay vì đưa toàn bộ body vào một object.

### 11.1. Cấu hình trong Spring Boot

Trong `application.properties`:

~~~properties
spring.codec.max-in-memory-size=1MB
~~~

Thuộc tính này áp dụng cho các WebFlux server và WebClient instance do Spring Boot auto-configure. Nó đặt giới hạn cho dữ liệu cần aggregate; các codec riêng vẫn có thể có hành vi/giới hạn cụ thể.

### 11.2. Cấu hình server bằng WebFluxConfigurer

~~~java
@Configuration
public class WebCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024);
    }
}
~~~

Cách này cấu hình giới hạn 1 MiB cho default codecs phía server. Khi dùng Spring Boot, có thể bổ sung WebFluxConfigurer mà vẫn giữ auto-configuration. Chỉ dùng @EnableWebFlux nếu muốn tự kiểm soát cấu hình WebFlux đầy đủ.

### 11.3. Giới hạn multipart

Spring Boot có các thuộc tính riêng cho multipart, ví dụ:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-parts=20
spring.webflux.multipart.max-disk-usage-per-part=100MB
~~~

- max-in-memory-size kiểm soát ngưỡng part được giữ trong memory trước khi ghi ra disk.
- max-parts giới hạn số phần trong một request.
- max-disk-usage-per-part giới hạn dung lượng disk cho mỗi part.

Cấu hình cụ thể nên phù hợp với kích thước upload và storage của ứng dụng. Tránh đặt -1 hoặc bỏ giới hạn trong môi trường công khai nếu không có kiểm soát tài nguyên khác.

## 12. DataBuffer lifecycle và tránh memory leak

`DataBuffer` có thể được backed bởi buffer thường hoặc pooled buffer. Trên một số server như Reactor Netty, byte buffer có thể được pooled và reference-counted. Khi ứng dụng tự consume buffer, phải giải phóng đúng lúc để tránh memory leak.

Nguyên tắc:

1. Nếu chỉ dùng codec ở mức object/String/Resource, để Spring quản lý DataBuffer.
2. Nếu tự consume hoặc bỏ một DataBuffer, kiểm tra ownership và release đúng cách.
3. Nếu chuyển buffer sang downstream để ghi tiếp, không release trước khi downstream hoàn tất.
4. Không release hai lần cùng một buffer.
5. Không giữ reference tới pooled buffer sau khi đã release.
6. Với custom codec, tuân thủ contract của Encoder/Decoder và DataBufferFactory.

Ví dụ release khi ứng dụng tự sở hữu buffer:

~~~java
DataBuffer buffer = ...;
try {
    // Đọc/copy byte cần thiết từ buffer.
} finally {
    DataBufferUtils.release(buffer);
}
~~~

Đây là snippet minh họa; chỉ release khi code của bạn thực sự sở hữu buffer và không chuyển nó tiếp cho thành phần khác. Khi làm việc với buffer stream, cần xử lý cả error/cancel và mọi buffer đã được cấp phát.

`DataBufferUtils.join` có thể gom nhiều buffer thành một buffer, nhưng thao tác aggregate vẫn cần giới hạn kích thước. Đừng dùng join để biến một file lớn thành một buffer khổng lồ nếu mục tiêu là streaming.

## 13. Cấu hình và đăng ký custom codec

WebFlux có sẵn nhiều reader/writer mặc định. Khi cần media type hoặc định dạng riêng, có thể thêm custom codec.

### 13.1. ServerCodecConfigurer

~~~java
@Configuration
public class CustomCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(1024 * 1024);

        configurer.customCodecs()
            .register(new MyMessageEncoder());

        configurer.customCodecs()
            .register(new MyMessageDecoder());
    }
}
~~~

`MyMessageEncoder` cần triển khai Encoder<MyMessage>; `MyMessageDecoder` cần triển khai Decoder<MyMessage>. Mỗi codec phải khai báo media type hỗ trợ, khả năng encode/decode type và cách xử lý buffer/backpressure.

### 13.2. Encoder và Decoder

Custom Encoder thường phải mô tả:

- Type Java được hỗ trợ.
- Media type có thể ghi.
- Khả năng encode một value hoặc Publisher.
- Cách tạo DataBuffer từ byte content.
- Cách xử lý hint và streaming nếu có.

Custom Decoder thường phải mô tả:

- Type Java đầu ra.
- Media type có thể đọc.
- Cách parse byte stream thành object.
- Cách xử lý buffer ranh giới record.
- Cách xử lý malformed input, cancel và release buffer.

Không viết custom codec nếu Jackson/String/byte[]/Resource codec mặc định đã đáp ứng. Codec tự viết là tầng thấp và có thể gây lỗi memory, framing hoặc tương thích nếu contract không được tuân thủ.

### 13.3. WebClient codec

WebClient có bộ codec riêng cho client request/response:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024))
    .build();
~~~

Gửi object JSON:

~~~java
Mono<Item> created = client.post()
    .uri("/api/items")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(new Item(7, "Monitor"))
    .retrieve()
    .bodyToMono(Item.class);
~~~

Đọc NDJSON thành Flux:

~~~java
Flux<Item> items = client.get()
    .uri("/api/items/stream")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Item.class);
~~~

`bodyToMono` thường aggregate một response body thành một giá trị; `bodyToFlux` phù hợp khi response được stream thành nhiều phần tử. Nếu response lỗi, dùng `onStatus` hoặc xử lý WebClientResponseException để map lỗi HTTP theo contract.

## 14. Chọn codec và media type: cách chẩn đoán

Khi nhận lỗi codec, kiểm tra theo thứ tự:

1. Request Content-Type có đúng định dạng body thực tế không?
2. Endpoint có consumes phù hợp không?
3. Client Accept có tương thích produces của endpoint không?
4. Java type có codec hỗ trợ không?
5. Codec cần thiết có dependency trên classpath và đã được đăng ký chưa?
6. Body có malformed hoặc charset không đúng không?
7. Body có vượt maxInMemorySize không?
8. Với multipart, có vượt max parts, memory, disk hoặc header limit không?
9. Nếu dùng DataBuffer trực tiếp, có giữ/release buffer đúng lifecycle không?
10. Nếu stream, client có hiểu framing NDJSON/SSE và có tiêu thụ đủ nhanh không?

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| 415 Unsupported Media Type | Content-Type không được endpoint/reader hỗ trợ | Gửi đúng Content-Type hoặc thêm codec |
| 406 Not Acceptable | Accept không tương thích response representation | Sửa Accept hoặc khai báo representation phù hợp |
| 400 khi đọc JSON | JSON malformed, field/type không hợp lệ | Kiểm tra payload và decoder/validation |
| DataBufferLimitException | Body cần aggregate vượt giới hạn | Stream dữ liệu hoặc tăng giới hạn có kiểm soát |
| Body String bị hiểu sai | Chọn nhầm media type hoặc charset | Khai báo text/plain hoặc application/json đúng contract |
| Binary bị hỏng | Encoding text không phù hợp hoặc buffer position sai | Dùng byte[]/Resource/DataBuffer đúng cách |
| Upload gây tăng RAM | Đọc toàn bộ file vào byte[] | Dùng FilePart/Resource streaming và giới hạn multipart |
| Stream chỉ hiện khi kết thúc | Client/proxy buffer hoặc định dạng không phải streaming | Chọn NDJSON/SSE, flush/heartbeat phù hợp |
| Memory leak với Netty | DataBuffer pooled không được release | Kiểm tra ownership và DataBufferUtils.release |
| Không tìm được codec | Codec không hỗ trợ Java type/media type hoặc chưa đăng ký | Cấu hình custom codec hoặc dùng type/media type được hỗ trợ |

## 15. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Demo này minh họa bốn representation: JSON, text, binary và NDJSON. Nó cũng kiểm tra Content-Type/Accept bằng các status 415 và 406.

### 15.1. Cấu trúc dự án

~~~text
webflux-codec-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      Item.java
      CodecController.java
      WebCodecConfiguration.java
    main/resources/
      application.properties
    test/java/demo/
      CodecControllerTest.java
~~~

### 15.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management chọn phiên bản Spring Framework, Reactor, Jackson và test libraries tương thích. Không tự ghim phiên bản codec riêng nếu chưa có lý do tương thích.

### 15.3. application.properties

~~~properties
spring.application.name=webflux-codec-demo
spring.codec.max-in-memory-size=1MB
~~~

Demo đặt giới hạn aggregate của default codecs ở 1 MiB để minh họa cấu hình. Trong production, hãy chọn ngưỡng theo kích thước payload hợp lệ và tài nguyên của ứng dụng.

### 15.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 15.5. Item.java

~~~java
package demo;

public record Item(long id, String name) {
}
~~~

### 15.6. WebCodecConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024);
    }
}
~~~

Cấu hình này minh họa cách thay đổi giới hạn ở server. Có thể dùng application.properties hoặc WebFluxConfigurer; không cần đặt cả hai cùng một giá trị nếu không có mục đích rõ ràng.

### 15.7. CodecController.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class CodecController {

    @GetMapping(
        value = "/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Item> item(@PathVariable long id) {
        return Mono.justOrEmpty(
            id == 1L ? new Item(1L, "Keyboard") : null
        );
    }

    @PostMapping(
        value = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Item> echo(@RequestBody Mono<Item> item) {
        return item;
    }

    @GetMapping(
        value = "/text",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    Mono<String> text() {
        return Mono.just("Hello WebFlux");
    }

    @GetMapping(
        value = "/binary",
        produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    Mono<byte[]> binary() {
        byte[] bytes = "BINARY".getBytes(StandardCharsets.UTF_8);
        return Mono.just(bytes);
    }

    @GetMapping(
        value = "/items/stream",
        produces = "application/x-ndjson"
    )
    Flux<Item> stream() {
        return Flux.just(
            new Item(1L, "Keyboard"),
            new Item(2L, "Mouse")
        );
    }

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<String>> events() {
        return Flux.just("connected", "updated")
            .map(value -> ServerSentEvent.builder(value)
                .event("status")
                .build());
    }
}
~~~

Các endpoint minh họa:

- `/items/{id}` trả một Java record và được JSON encoder serialize.
- `/echo` đọc JSON body thành Mono<Item> rồi trả lại.
- `/text` trả String với text/plain.
- `/binary` trả byte[] với application/octet-stream.
- `/items/stream` trả nhiều Item dưới dạng NDJSON.
- `/events` trả SSE event với text/event-stream.

Service thực tế có thể thay dữ liệu cố định bằng repository hoặc publisher khác. Controller giữ nguyên reactive type để WebFlux điều phối đọc/ghi body.

### 15.8. Chạy ứng dụng

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc nếu đã cài Gradle:

~~~bash
gradle bootRun
~~~

Gọi endpoint:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/1
curl -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -H "Accept: application/json" -d '{"id":7,"name":"Monitor"}'
curl -i -H "Accept: text/plain" http://localhost:8080/api/text
curl -i -H "Accept: application/octet-stream" http://localhost:8080/api/binary
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/api/items/stream
curl -N -H "Accept: text/event-stream" http://localhost:8080/api/events
~~~

Kết quả body chính:

JSON:

~~~json
{"id":1,"name":"Keyboard"}
~~~

Text:

~~~text
Hello WebFlux
~~~

Binary:

~~~text
BINARY
~~~

NDJSON:

~~~text
{"id":1,"name":"Keyboard"}
{"id":2,"name":"Mouse"}
~~~

SSE có dạng:

~~~text
event:status
data:connected

event:status
data:updated
~~~

Kết quả thực tế có thể có khác biệt về header phụ trợ hoặc xuống dòng tùy server adapter, nhưng media type và payload semantics phải phù hợp với contract đã khai báo.

## 16. Kiểm thử bằng WebTestClient và JUnit 5

Tạo `src/test/java/demo/CodecControllerTest.java`:

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CodecControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void jsonObjectUsesApplicationJson() {
        client.get()
            .uri("/api/items/1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(Item.class)
            .isEqualTo(new Item(1L, "Keyboard"));
    }

    @Test
    void jsonRequestIsDecodedAndEncoded() {
        Item input = new Item(7L, "Monitor");

        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBody(Item.class)
            .isEqualTo(input);
    }

    @Test
    void stringUsesTextPlain() {
        client.get()
            .uri("/api/text")
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("Hello WebFlux");
    }

    @Test
    void byteArrayUsesOctetStream() {
        byte[] expected = "BINARY".getBytes(StandardCharsets.UTF_8);

        byte[] actual = client.get()
            .uri("/api/binary")
            .accept(MediaType.APPLICATION_OCTET_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_OCTET_STREAM)
            .expectBody(byte[].class)
            .returnResult()
            .getResponseBody();

        assertArrayEquals(expected, actual);
    }

    @Test
    void ndjsonStreamsMultipleObjects() {
        client.get()
            .uri("/api/items/stream")
            .accept(MediaType.parseMediaType("application/x-ndjson"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.parseMediaType("application/x-ndjson"))
            .expectBodyList(Item.class)
            .contains(
                new Item(1L, "Keyboard"),
                new Item(2L, "Mouse")
            );
    }

    @Test
    void unsupportedRequestMediaTypeReturns415() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("not-json")
            .exchange()
            .expectStatus().isEqualTo(415);
    }

    @Test
    void unacceptableResponseMediaTypeReturns406() {
        client.get()
            .uri("/api/items/1")
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isEqualTo(406);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các test xác minh JSON round trip, String, binary bytes, NDJSON stream và hai nhánh content negotiation 415/406. Test không cần Thread.sleep; WebTestClient chờ response theo reactive exchange và assertions.

SSE có thể kiểm thử riêng bằng `returnResult(ServerSentEvent.class)` rồi tiêu thụ response body stream và kiểm tra event name/data. Với stream vô hạn, cần timeout/cancellation có chủ đích thay vì chờ complete.

## 17. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng text/plain cho JSON object | Client coi JSON là văn bản thuần | Dùng application/json |
| Dùng application/json cho byte tùy ý | Client cố parse binary như JSON | Dùng application/octet-stream hoặc media type file cụ thể |
| Nhầm Content-Type với Accept | Server chọn reader/writer sai hoặc từ chối request | Content-Type mô tả request body; Accept mô tả response mong muốn |
| Trả String chứa JSON nhưng không khai báo media type | Client có thể nhận text/plain | Khai báo application/json hoặc trả object để Jackson serialize |
| Dùng byte[] cho file rất lớn | Toàn bộ file nằm trong heap | Dùng Resource hoặc stream |
| Dùng collectList cho stream lớn | Tăng RAM và chờ toàn bộ dữ liệu | Dùng Flux với NDJSON/SSE hoặc protocol streaming |
| Tăng maxInMemorySize quá lớn để bỏ qua lỗi | Tăng nguy cơ memory pressure | Xem có thể stream không, rồi đặt giới hạn có kiểm soát |
| Đọc multipart không giới hạn | RAM/disk bị tiêu thụ quá mức | Giới hạn part count, memory, disk và file size |
| Tự consume DataBuffer nhưng không release | Có thể memory leak với pooled buffer | Quản lý ownership và DataBufferUtils.release |
| Release DataBuffer trước khi downstream ghi xong | Body bị hỏng hoặc lỗi runtime | Chỉ release khi code thực sự sở hữu và đã consume xong |
| Dùng NDJSON nhưng client parse như JSON array | Client không hiểu framing | Thống nhất application/x-ndjson và parse từng dòng |
| Dùng SSE với application/json | Client không nhận đúng event framing | Dùng text/event-stream |
| Bỏ qua Accept/produces | Có thể gặp 406 khó hiểu | Khai báo media type và test negotiation |
| Bỏ qua consumes/Content-Type | Request không đúng định dạng đi vào decode | Giới hạn consumes và xử lý 415 |
| Tự viết codec không tuân thủ backpressure | Tốn bộ nhớ hoặc mất dữ liệu | Tuân thủ Encoder/Decoder và Reactive Streams |
| Tạo ObjectMapper riêng mỗi request | Tăng chi phí và cấu hình không nhất quán | Dùng ObjectMapper/codec được quản lý ở application context |
| Tin filename trong multipart | Path traversal hoặc ghi file ngoài vùng cho phép | Tạo tên file phía server và kiểm tra storage path |
| Log toàn bộ body binary hoặc multipart | Log phình lớn và có thể lộ dữ liệu | Log metadata, kích thước, media type và correlation ID |

## 18. Checklist chọn codec và media type

Trước khi triển khai endpoint, hãy xác định:

1. Body là JSON, text, binary, file, form, multipart hay stream?
2. Request Content-Type có mô tả đúng body không?
3. Client Accept có khớp representation endpoint cung cấp không?
4. Java type có codec mặc định hỗ trợ không?
5. Body được aggregate hay stream từng phần tử?
6. Payload lớn nhất hợp lệ là bao nhiêu?
7. maxInMemorySize và multipart limits đã được cấu hình phù hợp chưa?
8. Nếu dùng DataBuffer trực tiếp, ownership/release đã rõ chưa?
9. Với streaming, framing là JSON array, NDJSON hay SSE?
10. Client có đọc publisher streaming bằng bodyToFlux không?
11. Custom codec có thực sự cần thiết không?
12. Đã test 200, 400, 406, 415 và lỗi buffer phù hợp chưa?

| Nhu cầu | Lựa chọn gợi ý |
| --- | --- |
| REST DTO | application/json + Jackson |
| Văn bản thuần | text/plain + String |
| HTML | text/html |
| Byte nhỏ có sẵn | application/octet-stream + byte[] |
| File lớn | Resource/FilePart streaming |
| Stream nhiều JSON record | application/x-ndjson + Flux<T> |
| Push event một chiều | text/event-stream + Flux<ServerSentEvent<T>> |
| Form key/value | application/x-www-form-urlencoded |
| Upload nhiều phần | multipart/form-data + FilePart/Part |
| Protocol riêng | Custom Encoder/Decoder và reader/writer |

## 19. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Content-Type và Accept khác nhau thế nào?

**Đáp án:** Content-Type mô tả định dạng body request đang gửi. Accept mô tả định dạng response client có thể nhận.

**Câu 2.** HttpMessageReader và Decoder có giống nhau không?

**Đáp án:** Không. Decoder chuyển byte content thành object; HttpMessageReader là abstraction đọc HTTP message và thường dùng Decoder bên trong.

**Câu 3.** Khi controller trả record Java với application/json, thành phần nào serialize object?

**Đáp án:** JSON Encoder được sử dụng bởi HttpMessageWriter tương thích với type và media type.

**Câu 4.** Khi nào nên dùng text/plain?

**Đáp án:** Khi body là văn bản thuần như thông báo, nội dung text hoặc chuỗi không được mô tả là JSON/HTML.

**Câu 5.** Vì sao byte[] không phải lựa chọn tốt cho file rất lớn?

**Đáp án:** Toàn bộ nội dung được giữ trong một mảng byte trong heap. Resource hoặc stream cho phép ghi dữ liệu theo phần.

**Câu 6.** NDJSON khác JSON array thế nào?

**Đáp án:** NDJSON chứa một JSON document trên mỗi dòng, cho phép client xử lý từng record độc lập. JSON array là một document chứa toàn bộ phần tử.

**Câu 7.** Media type chuẩn cho SSE là gì?

**Đáp án:** text/event-stream.

**Câu 8.** DataBufferLimitException thường cho biết điều gì?

**Đáp án:** Một codec/reader đang aggregate dữ liệu vượt quá giới hạn bộ nhớ cấu hình. Có thể cần stream body hoặc tăng giới hạn có kiểm soát.

**Câu 9.** Vì sao cần release DataBuffer khi tự consume trên Netty?

**Đáp án:** Một số buffer được pooled và reference-counted. Không release đúng lúc có thể làm rò rỉ bộ nhớ native/direct.

**Câu 10.** HTTP 415 và 406 thường liên quan đến điều gì?

**Đáp án:** 415 là request Content-Type không được hỗ trợ; 406 là không có representation response phù hợp với Accept của client.

**Câu 11.** WebFlux có thể đọc multipart file thành FilePart không?

**Đáp án:** Có. FilePart cung cấp metadata và content publisher; có thể transferTo storage đích theo cách reactive.

**Câu 12.** Khi nào cần custom Encoder/Decoder?

**Đáp án:** Khi định dạng hoặc media type riêng không được codec mặc định hỗ trợ, hoặc cần behavior chuyển đổi đặc thù. Trước đó nên kiểm tra JSON/String/binary/Resource codec có sẵn.

## 20. Ghi nhớ và tài liệu chính thức

- Codec chuyển đổi giữa byte content và Java object; HTTP reader/writer gắn chuyển đổi đó với request/response.
- Content-Type mô tả body request; Accept mô tả response representation client chấp nhận.
- JSON dùng application/json; text thuần dùng text/plain; binary dùng application/octet-stream hoặc media type cụ thể.
- Resource phù hợp với file; byte[] phù hợp payload nhỏ; DataBuffer dành cho xử lý byte stream ở tầng thấp.
- NDJSON dùng application/x-ndjson cho record JSON từng dòng; SSE dùng text/event-stream.
- Form URL encoded và multipart có reader riêng và giới hạn riêng.
- maxInMemorySize bảo vệ các thao tác aggregate; tăng giới hạn cần đi kèm kiểm soát payload.
- Pooled DataBuffer phải được release đúng ownership khi ứng dụng tự consume.
- Dùng ServerCodecConfigurer/WebFluxConfigurer cho server và WebClient.Builder.codecs cho client.
- Chỉ viết custom codec khi codec mặc định không đáp ứng contract.

Tài liệu chính thức:

1. [Spring Framework Reference — Reactive Core: Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Encoder, Decoder, HttpMessageReader, HttpMessageWriter, DataBuffer, limits, streaming và custom codecs.
2. [Spring Framework Reference — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): ServerCodecConfigurer và cấu hình HTTP message codecs.
3. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): codec defaults, CodecConfigurer, CodecCustomizer và auto-configuration.
4. [Spring Boot 3.5 Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): spring.codec.max-in-memory-size và các thuộc tính multipart.
5. [Spring Framework Reference — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): client codec và maxInMemorySize.
6. [Spring Framework Javadoc — ServerCodecConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html): API cấu hình codec phía server.
7. [Spring Framework Reference — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBuffer lifecycle, pooled buffers và release.
8. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP response, body và content negotiation.
