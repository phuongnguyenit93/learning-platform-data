# RSocketRequester, RSocketStrategies và codec trong Spring Framework Reactive

RSocket là giao thức truyền thông hai chiều trên TCP, WebSocket hoặc transport phù hợp, cung cấp bốn interaction model: request-response, request-stream, fire-and-forget và request-channel. Spring Framework bổ sung các abstraction để ứng dụng trao đổi object và reactive stream mà không phải trực tiếp thao tác với byte buffer hoặc RSocket frame.

Ba khái niệm trung tâm của bài này:

- **RSocketRequester**: API fluent để chọn route, gửi data/metadata và nhận kết quả Mono/Flux.
- **RSocketStrategies**: cấu hình dùng chung cho encoder, decoder, route matcher, metadata extractor, buffer factory và reactive adapter.
- **Codec**: bộ mã hóa/giải mã giữa Java object và payload bytes theo kiểu dữ liệu và MIME type.

Nắm được chúng giúp tránh những lỗi thường gặp: client chỉ có codec cho String nhưng lại gửi DTO; SETUP khai báo application/json trong khi server chỉ hiểu CBOR; route không nằm trong metadata phù hợp; hoặc fire-and-forget bị nhầm thành xác nhận nghiệp vụ.

Bài học thuộc nhóm RSocket của module Spring Framework - reactive, dùng Java 17+ và Spring Boot 3.3.5 làm ví dụ thực hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt RSocket với HTTP và WebSocket transport thông thường.
- Hiểu bốn interaction model và API tương ứng của RSocketRequester.
- Tạo requester cho TCP hoặc WebSocket, quản lý lifecycle và kết nối chia sẻ.
- Hiểu SETUP frame, data MIME type và metadata MIME type.
- Gửi route, setup metadata và metadata theo request.
- Phân biệt retrieveMono(), retrieveFlux(), send() và sendMetadata().
- Hiểu chức năng encoder/decoder trong RSocketStrategies.
- Sử dụng JSON hoặc CBOR codec nhất quán giữa hai phía.
- Tùy chỉnh strategies bằng builder hoặc RSocketStrategiesCustomizer.
- Xử lý route matching, composite metadata và custom metadata extraction.
- Chọn type hint cho Publisher và ParameterizedTypeReference cho generic type.
- Giới hạn timeout, retry và backpressure phù hợp interaction model.
- Viết responder @MessageMapping và client RSocketRequester chạy được.
- Kiểm thử cả bốn kiểu tương tác qua TCP RSocket thật.

## 2. Cơ chế RSocket và bốn interaction model

Một connection RSocket bắt đầu bằng SETUP frame. Sau đó mỗi bên có thể khởi tạo interaction trên nhiều stream logic đồng thời.

~~~text
Requester                                 Responder
    |                                         |
    |---------- TCP/WebSocket ---------------|
    |--------------- SETUP ------------------>|
    |                                         |
    |----------- REQUEST_RESPONSE ---------->|
    |<-------------- PAYLOAD ----------------|
    |                                         |
    |----------- REQUEST_STREAM ------------>|
    |<-------------- PAYLOAD ----------------|
    |<-------------- PAYLOAD ----------------|
    |---------------- REQUEST_N ------------>|
    |<-------------- PAYLOAD ----------------|
    |                                         |
    |----------- REQUEST_CHANNEL ----------->|
    |---------------- PAYLOAD --------------->|
    |<-------------- PAYLOAD ----------------|
    |                                         |
    |------------ REQUEST_FNF --------------->|
    |                                         |
~~~

RSocket truyền demand qua REQUEST_N đối với stream cần backpressure. Đây là semantics ở tầng giao thức, không chỉ là logic trong một process Java.

| Interaction | Request data | Response data | RSocketRequester |
| --- | --- | --- | --- |
| Request-Response | Một message | Một message | retrieveMono(Class) |
| Request-Stream | Một message | Nhiều message | retrieveFlux(Class) |
| Fire-and-Forget | Một message | Không có business response | send() |
| Request-Channel | Nhiều message | Nhiều message | data(Flux, Class).retrieveFlux(Class) |

RSocket không thay thế mọi API HTTP. Nó hữu ích cho realtime, stream dài, tương tác hai chiều và kết nối có nhiều logical stream. HTTP vẫn phù hợp với REST, cache, request-response thông thường và hạ tầng web rộng rãi.

## 3. RSocketRequester là abstraction nào?

RSocketRequester nằm trên io.rsocket.RSocket của RSocket Java. API mức thấp làm việc với Payload và buffer. RSocketRequester nhận Java object, dùng codec để encode, gắn route/metadata rồi trả Mono hoặc Flux.

~~~java
Mono<GreetingReply> reply = requester.route("greet")
    .data(new GreetingRequest("Lan"))
    .retrieveMono(GreetingReply.class);
~~~

Ở đây:

1. route("greet") tạo routing metadata.
2. data(...) khai báo object phải encode thành payload.
3. retrieveMono(...) chọn request-response và kiểu Java được decode.
4. Việc gửi request thực sự diễn ra khi publisher được subscribe.
5. Kết quả phát onNext rồi onComplete hoặc kết thúc bằng onError.

Các method quan trọng:

| API | Vai trò |
| --- | --- |
| RSocketRequester.builder() | Tạo client requester builder |
| Builder.tcp(host, port) | Tạo requester dùng TCP |
| Builder.websocket(uri) | Tạo requester dùng WebSocket transport |
| Builder.transport(transport) | Dùng một ClientTransport có sẵn |
| route(route, vars...) | Đặt logical route trong metadata |
| data(object) | Gửi application data |
| data(publisher, elementClass) | Gửi nhiều data element với type hint |
| metadata(value, mimeType) | Gắn metadata theo request |
| retrieveMono(type) | Nhận một response object |
| retrieveFlux(type) | Nhận stream response objects |
| send() | Gửi fire-and-forget |
| dispose() | Giải phóng requester |
| isDisposed() | Xem requester đã dispose chưa |

Chú ý phiên bản: trong Spring Framework 6.1, Builder.tcp() và Builder.websocket() trả **RSocketRequester**, sử dụng shared connection theo nhu cầu. Các API cũ connectTcp() và connectWebSocket() trả Mono<RSocketRequester> đã deprecated. Code mới nên dùng tcp()/websocket() để không nhầm kiểu trả về.

## 4. Tạo requester với TCP và WebSocket

### TCP

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

tcp() tạo requester không bắt buộc phải mở socket ngay lập tức. Khi một request được subscribe, kết nối được thiết lập và có thể tái sử dụng cho các request sau.

### RSocket qua WebSocket

~~~java
URI endpoint = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester = RSocketRequester.builder()
    .websocket(endpoint);
~~~

RSocket-over-WebSocket vẫn truyền **RSocket frame** bên trong WebSocket transport. Một WebSocketHandler gửi chuỗi text tùy ý không phải RSocket responder; hai phía phải dùng cùng giao thức RSocket.

### Giao thức không phụ thuộc transport

Route greet và record GreetingRequest không cần thay đổi khi chuyển TCP sang WebSocket, miễn server và client cùng khai báo transport tương ứng. URL WebSocket thường dùng ws:// khi local và wss:// khi triển khai production với TLS.

### Tái sử dụng thay vì tạo cho từng message

Nên xây dựng requester một lần cho từng upstream/connection policy, rồi inject vào service. Không tạo builder và TCP connection mới trong mỗi method gọi service. Khi application shutdown, giải phóng requester bằng dispose() hoặc quản lý qua Spring bean lifecycle.

## 5. SETUP frame và MIME type cấp connection

Khi thiết lập connection, requester gửi SETUP frame gồm MIME type, keepalive/lifetime và dữ liệu setup tùy chọn.

Các API builder:

| Method | Ý nghĩa |
| --- | --- |
| dataMimeType(MimeType) | MIME của application data trên connection |
| metadataMimeType(MimeType) | MIME của metadata trên connection |
| setupData(Object) | Payload data trong SETUP |
| setupRoute(String, Object...) | Route xử lý setup |
| setupMetadata(Object, MimeType) | Thêm setup metadata |
| rsocketStrategies(RSocketStrategies) | Chọn strategies |
| rsocketConnector(configurer) | Tùy chỉnh RSocketConnector thấp hơn |

Ví dụ minh họa SETUP:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"))
    .setupRoute("client.setup")
    .setupData(new ClientHello("reporting-service"))
    .tcp("localhost", 7000);
~~~

Đây là **fragment minh họa**: phía responder phải có hợp đồng setup tương ứng, ví dụ @ConnectMapping, nếu không SETUP có thể không được chấp nhận. Trong ứng dụng tối giản không cần setupRoute và setupData.

Data MIME type mặc định được chọn dựa trên Decoder được cấu hình. Với nhiều codec như JSON và CBOR, nên khai báo rõ dataMimeType để tránh vô tình dùng một format ngoài dự kiến.

Metadata MIME type mặc định thường là composite metadata, cho phép chứa nhiều metadata entry có MIME type riêng. Hai thông số MIME nằm trong SETUP và áp dụng cho connection, không phải chọn lại tùy ý cho từng message.

## 6. Route, data và metadata trong request

Data mang nội dung nghiệp vụ; metadata mang route, tracing, authentication hoặc metadata extension khác.

~~~java
Mono<OrderView> result = requester.route("orders.get")
    .data(new OrderQuery("O-101"))
    .retrieveMono(OrderView.class);
~~~

Route orders.get là logical destination, không phải HTTP URL. Spring Messaging đọc routing metadata để tìm @MessageMapping phù hợp.

### Route template

~~~java
Mono<OrderView> result = requester
    .route("orders.{id}", "O-101")
    .retrieveMono(OrderView.class);
~~~

Responder cần mapping tương ứng và có thể dùng @DestinationVariable theo quy ước route pattern.

### Metadata bổ sung

~~~java
MimeType traceMime =
    MimeTypeUtils.parseMimeType("text/plain");

Mono<OrderView> result = requester
    .route("orders.get")
    .metadata("trace-123", traceMime)
    .data(new OrderQuery("O-101"))
    .retrieveMono(OrderView.class);
~~~

Fragment này gửi một metadata entry text/plain. Server phải có metadata extraction configuration nếu muốn truy xuất trace ID bằng @Header. Không tự động có tracing hoàn chỉnh chỉ nhờ thêm một entry metadata.

Metadata có thể chứa secret hoặc token. Không ghi chúng vào log, không gửi token trong application data nếu API yêu cầu authentication metadata. Hãy dùng cơ chế bảo mật dành cho RSocket khi xây dựng authentication.

## 7. Composite metadata và routing

Composite metadata có MIME type:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Routing entry trong metadata thường dùng:

~~~text
message/x.rsocket.routing.v0
~~~

Một request có thể chứa nhiều entry độc lập:

~~~text
Metadata entry 1:
    MIME: message/x.rsocket.routing.v0
    Value: orders.get

Metadata entry 2:
    MIME: text/plain
    Value: trace-123

Application data:
    MIME theo SETUP: application/json
    JSON: {"id":"O-101"}
~~~

RSocketRequester.route() tạo routing metadata phù hợp khi dùng composite format mặc định. Nếu thay metadata MIME type sang format không tương thích, route có thể không được responder extract và @MessageMapping sẽ không khớp.

Đừng nhầm dataMimeType với metadataMimeType. Cả hai mô tả các phần byte khác nhau của RSocket payload.

## 8. Bốn cách gửi và nhận với RSocketRequester

### Request-Response

~~~java
Mono<GreetingReply> one = requester.route("greet")
    .data(new GreetingRequest("An"))
    .retrieveMono(GreetingReply.class);
~~~

Trả một object. Nếu server phát lỗi, Mono kết thúc bằng onError.

### Request-Stream

~~~java
Flux<NumberEvent> numbers = requester.route("count")
    .data(new CountRequest(3))
    .retrieveFlux(NumberEvent.class);
~~~

Trả nhiều message. Downstream có thể yêu cầu dần, cancel, timeout hoặc xử lý từng phần tử.

### Fire-and-Forget

~~~java
Mono<Void> sent = requester.route("audit.record")
    .data(new AuditRecord("login", "user-42"))
    .send();
~~~

Mono<Void> ở đây chỉ phản ánh hành vi gửi theo mô hình không có response nghiệp vụ. Nó **không** bảo đảm audit record đã được commit vào database. Nếu cần xác nhận đã xử lý, chuyển sang request-response trả Ack.

### Request-Channel

~~~java
Flux<UppercaseRequest> input = Flux.just(
    new UppercaseRequest("hello"),
    new UppercaseRequest("rsocket"));

Flux<UppercaseReply> output = requester.route("uppercase")
    .data(input, UppercaseRequest.class)
    .retrieveFlux(UppercaseReply.class);
~~~

Channel gửi nhiều request message và nhận nhiều response message. Truyền UppercaseRequest.class làm type hint để encoder không phải suy luận cho mỗi element. Hai chiều có thể hoạt động đồng thời tùy hợp đồng channel.

### Metadata Push

RSocket có interaction metadata-push ở cấp connection. Trong Spring, API chuyên biệt cho metadata push có semantics khác request-route thông thường: nó không yêu cầu response nghiệp vụ và phía nhận phải có handler/metadata extractor tương ứng. Không dùng metadata push như thay thế cho audit command cần Ack.

## 9. RSocketStrategies: vai trò và thành phần

RSocketStrategies nhóm các chiến lược mà requester và responder cần cho serialization và routing.

| Thành phần | Vai trò |
| --- | --- |
| Encoder | Chuyển Java object sang payload bytes |
| Decoder | Chuyển bytes thành Java object |
| RouteMatcher | So khớp route pattern với responder |
| MetadataExtractor | Trích xuất route và custom metadata |
| DataBufferFactory | Cấp phát buffer cho encode/decode |
| ReactiveAdapterRegistry | Nhận diện Mono, Flux và các reactive producer được hỗ trợ |

RSocketStrategies không phải network connection, không phải HTTP client và không tự gửi request. RSocketRequester tham chiếu tới strategies khi encode outbound data, decode inbound data và xử lý metadata.

### Builder với JSON codec

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoder(new Jackson2JsonEncoder())
    .decoder(new Jackson2JsonDecoder())
    .build();

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

Các class Jackson2JsonEncoder và Jackson2JsonDecoder thuộc org.springframework.http.codec.json. Đây là fragment dùng được khi các dependency Spring Web/Jackson có mặt. Nó không cấu hình responder; server vẫn phải có decoder/encoder cho JSON.

Có thể bổ sung strategies trực tiếp qua callback:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(builder ->
        builder.encoder(new Jackson2JsonEncoder())
               .decoder(new Jackson2JsonDecoder()))
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

Với Spring Boot starter RSocket, thường không cần cấu hình thủ công vì Boot đã auto-configure RSocketStrategies.

## 10. Codec, MIME type và kiểu dữ liệu

Codec chọn theo MIME type lẫn Java type. Encoder chuyển object thành bytes; Decoder đọc bytes thành object đã yêu cầu.

~~~text
GreetingRequest
      |
      | Encoder + application/json
      v
   JSON bytes
      |
      v
 RSocket transport
      |
      v
  Decoder + target type
      |
      v
 GreetingRequest ở responder
~~~

Nếu client gửi JSON nhưng responder chỉ biết CBOR, request có thể lỗi ngay khi decode. Tương tự, nếu response byte là JSON GreetingReply nhưng client gọi retrieveMono(OtherType.class), decoder có thể thất bại hoặc tạo object sai.

### JSON và CBOR

| Thuộc tính | JSON | CBOR |
| --- | --- | --- |
| MIME | application/json | application/cbor |
| Dạng data | Văn bản UTF-8 | Nhị phân |
| Debug bằng mắt | Dễ | Cần decoder |
| Kích thước | Thường lớn hơn | Thường gọn hơn |
| Yêu cầu | Hai phía đăng ký Jackson JSON | Hai phía đăng ký Jackson CBOR |

Boot RSocket starter cung cấp dependencies và auto-configuration hỗ trợ Jackson. Tùy classpath, CBOR codec có thể được ưu tiên trước JSON khi chọn mặc định; vì vậy ví dụ bên dưới đặt rõ MIME type JSON.

Không đổi JSON sang CBOR chỉ vì cho rằng CBOR luôn nhanh hơn. Hãy đo throughput, payload size và CPU trên dữ liệu thật, đồng thời kiểm soát version schema.

### Codec cơ bản

RSocketStrategies.Builder có codec cơ bản cho String, byte[], ByteBuffer và DataBuffer. Việc gửi các Java record/DTO yêu cầu codec như Jackson JSON/CBOR.

### Generic type

~~~java
Mono<List<GreetingReply>> all = requester.route("greetings.all")
    .retrieveMono(new ParameterizedTypeReference<
        List<GreetingReply>>() {});
~~~

Dùng ParameterizedTypeReference để giữ generic type của phần tử trong List. Nếu chỉ dùng List.class, phần tử có thể được decode thành Map hoặc Object chung, không phải DTO mong muốn.

## 11. RSocketStrategiesCustomizer trong Spring Boot

Spring Boot tạo bean RSocketStrategies và cung cấp RSocketRequester.Builder dạng prototype, đã gắn codecs/connector config được auto-configure.

Để thêm codec ở cấp ứng dụng, dùng RSocketStrategiesCustomizer thuộc package org.springframework.boot.rsocket.messaging:

~~~java
@Configuration
public class RSocketCodecConfiguration {

    @Bean
    public RSocketStrategiesCustomizer extraJsonCodec() {
        return builder -> {
            builder.encoder(new Jackson2JsonEncoder());
            builder.decoder(new Jackson2JsonDecoder());
        };
    }
}
~~~

Imports minh họa:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
~~~

Đây là ví dụ syntax cho customizer, không cần thêm nguyên xi vào ứng dụng đã có Jackson JSON mặc định. Codec trùng không làm hệ thống tốt hơn; chỉ custom nếu có ObjectMapper riêng, định dạng data mới hoặc yêu cầu interop đã xác định.

Nếu nhiều customizer cùng thêm codec, thứ tự @Order có thể quan trọng. Hãy kiểm tra thứ tự encoder/decoder và test round-trip. Không thay serializer chung của hệ thống mà chưa đánh giá tác động tới các responder khác.

### Custom codec an toàn

Khi tạo codec cho định dạng nhị phân riêng:

1. Quy định MIME type chính xác.
2. Chỉ rõ Java types mà encoder/decoder hỗ trợ.
3. Bảo đảm client và server đăng ký codec tương ứng.
4. Giới hạn kích thước message và bộ nhớ.
5. Quản lý DataBuffer theo lifecycle đúng.
6. Test encode/decode ở unit level và trên kết nối thật.
7. Kiểm tra khả năng tương thích khi triển khai nhiều version.

Không gắn MIME application/json cho bytes không phải JSON để ép framework dùng một decoder.

## 12. RouteMatcher và MetadataExtractor

RSocketStrategies còn phục vụ routing.

### RouteMatcher

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .routeMatcher(new PathPatternRouteMatcher())
    .build();
~~~

RouteMatcher giải quyết việc so khớp route với @MessageMapping. PathPatternRouteMatcher hữu ích khi muốn pattern matching của Spring Web. Thay RouteMatcher cần test lại tên và pattern của các route.

### MetadataExtractor

MetadataExtractor trích xuất route metadata và các metadata entry bổ sung. Ví dụ đăng ký extraction cho metadata text/plain:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            MimeTypeUtils.TEXT_PLAIN,
            String.class,
            "traceId"))
    .build();
~~~

Fragment này minh họa cách đưa metadata đã decode thành một header có tên traceId. Responder có thể lấy header bằng @Header("traceId") khi Spring đã cấu hình extractor và metadata encoding phù hợp.

Trong production, dùng MIME type chuyên biệt để tránh biến mọi text/plain metadata thành traceId; phải thống nhất format, decoder và bảo mật hai phía.

### ReactiveAdapterRegistry và DataBufferFactory

ReactiveAdapterRegistry giúp Spring nhận biết reactive publisher types ngoài Mono/Flux nếu được hỗ trợ. DataBufferFactory ảnh hưởng cách cấp phát buffer; với Reactor Netty có thể dùng pooled buffer. Không tùy chỉnh DataBufferFactory hoặc giữ raw DataBuffer qua xử lý dài khi chưa hiểu retain/release, zero-copy và frame decoder.

## 13. Tùy chỉnh connector, timeout và lifecycle

RSocketRequester.Builder cho phép cấu hình RSocketConnector cấp thấp:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .rsocketConnector(connector ->
        connector.keepAlive(
            Duration.ofSeconds(20),
            Duration.ofSeconds(90)))
    .tcp("localhost", 7000);
~~~

Đây là fragment cấu hình keepalive và lifetime; các giá trị phải tương thích server, proxy và đặc tính network. Nó không đặt deadline cho một business request.

Để giới hạn một interaction, dùng Reactor timeout:

~~~java
Mono<GreetingReply> reply = requester.route("greet")
    .data(new GreetingRequest("An"))
    .retrieveMono(GreetingReply.class)
    .timeout(Duration.ofSeconds(3));
~~~

Khi requester không còn dùng, gọi dispose():

~~~java
requester.dispose();
~~~

Spring có thể quản lý qua bean:

~~~java
@Bean(destroyMethod = "dispose")
RSocketRequester catalogRequester(RSocketRequester.Builder builder) {
    return builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("catalog.internal", 7000);
}
~~~

Không tạo requester mới trong mỗi request handler. Không gọi block() trên event-loop của WebFlux; chỉ block trong CLI hoặc test đồng bộ khi có lý do và giới hạn thời gian phù hợp.

## 14. Error handling, retry và backpressure

Lỗi của một interaction xuất hiện dưới onError trong Mono/Flux. Cần phân biệt:

- Không kết nối được TCP/WebSocket.
- SETUP bị từ chối hoặc MIME type không hỗ trợ.
- Route không tìm thấy.
- Decode không được payload.
- Application error ở responder.
- Stream timeout.
- Client cancellation.
- Mất transport giữa stream.

Log có kiểm soát:

~~~java
Mono<GreetingReply> response = requester.route("greet")
    .data(new GreetingRequest("An"))
    .retrieveMono(GreetingReply.class)
    .doOnError(error ->
        log.warn("RSocket interaction failed", error));
~~~

doOnError chỉ quan sát; không phục hồi. onErrorResume có thể fallback nếu domain cho phép, nhưng không nên trả kết quả thành công giả khi business process thất bại.

### Retry không phải exactly-once

Một request đã tới responder có thể được xử lý trước khi kết nối bị đứt. Retry fire-and-forget hoặc request-channel có side effect có thể gây trùng. Dùng idempotency key, deduplication và retryWhen có backoff/giới hạn khi cần.

### REQUEST_N và cancellation

RSocket truyền demand qua REQUEST_N cho request-stream và channel. Nếu downstream dùng take(3), nguồn có thể nhận cancellation và dừng phát dữ liệu:

~~~java
Flux<NumberEvent> firstThree = requester.route("count")
    .data(new CountRequest(100))
    .retrieveFlux(NumberEvent.class)
    .take(3);
~~~

Không tạo queue vô hạn chỉ vì transport có backpressure. Nguồn push nóng vẫn có thể cần overflow policy; giới hạn concurrency, payload size và thời gian xử lý.

## 15. Responder @MessageMapping

Phía server, Spring Messaging nhận route qua RSocketMessageHandler và ánh xạ tới controller methods có @MessageMapping.

Request-response:

~~~java
@Controller
public class GreetingResponder {

    @MessageMapping("greet")
    public Mono<GreetingReply> greet(
            @Payload GreetingRequest request) {

        return Mono.just(new GreetingReply(
            "Xin chào, " + request.name()));
    }
}
~~~

Request-stream:

~~~java
@MessageMapping("count")
public Flux<NumberEvent> count(@Payload CountRequest request) {
    int safeCount = Math.max(0, Math.min(request.count(), 10));

    return Flux.range(1, safeCount)
        .map(i -> new NumberEvent(i, "event-" + i));
}
~~~

Request-channel:

~~~java
@MessageMapping("uppercase")
public Flux<UppercaseReply> uppercase(
        @Payload Flux<UppercaseRequest> requests) {

    return requests.map(r ->
        new UppercaseReply(r.value().toUpperCase(Locale.ROOT)));
}
~~~

Các đoạn ở đây minh họa method, không phải ba class Java độc lập. Project hoàn chỉnh phía dưới cung cấp một responder, records và imports để build.

Trong responder, không tự subscribe rồi trả Mono.empty() khi công việc còn cần được quản lý. Trả publisher để framework kiểm soát error/cancellation và backpressure.

## 16. Ví dụ Java 17+ chạy được: bốn interaction model

Project Spring Boot 3.3.5 dưới đây có TCP RSocket server ở port 7000 và bốn route:

- greet: request-response.
- count: request-stream.
- audit.record: fire-and-forget.
- uppercase: request-channel.

Client CLI chạy riêng, tạo RSocketStrategies JSON **tường minh** vì nó hoạt động ngoài Spring context, rồi gửi bốn request và in kết quả. Integration test dùng RSocketRequester.Builder do Boot cấu hình và port ngẫu nhiên.

### Cấu trúc project

~~~text
rsocket-codec-demo/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example/rsocket
    │   │   ├── RSocketCodecDemoApplication.java
    │   │   ├── Messages.java
    │   │   ├── DemoResponder.java
    │   │   └── ClientRunner.java
    │   └── resources/application.properties
    └── test
        └── java/com/example/rsocket
            └── RSocketCodecIntegrationTests.java
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
  <artifactId>rsocket-codec-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

### application.properties

~~~properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.main.web-application-type=none
~~~

Ứng dụng chạy standalone TCP RSocket server, không bắt buộc có HTTP web server. Nếu muốn transport=websocket, cần cấu hình server mapping path theo hạ tầng WebFlux/Reactor Netty phù hợp.

### Messages.java

~~~java
package com.example.rsocket;

record GreetingRequest(String name) {
}

record GreetingReply(String message) {
}

record CountRequest(int count) {
}

record NumberEvent(int number, String label) {
}

record AuditRecord(String kind, String actor) {
}

record UppercaseRequest(String value) {
}

record UppercaseReply(String value) {
}
~~~

Các record package-private dùng chung trong package com.example.rsocket. Jackson có thể serialize/deserialize Java records trên Java 17 khi dependency Boot phù hợp.

### DemoResponder.java

~~~java
package com.example.rsocket;

import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoResponder {

    private static final Logger log =
        LoggerFactory.getLogger(DemoResponder.class);

    @MessageMapping("greet")
    public Mono<GreetingReply> greet(
            @Payload GreetingRequest request) {

        return Mono.just(
            new GreetingReply("Xin chào, " + request.name()));
    }

    @MessageMapping("count")
    public Flux<NumberEvent> count(
            @Payload CountRequest request) {

        int count = Math.max(0, Math.min(request.count(), 10));

        return Flux.range(1, count)
            .map(i -> new NumberEvent(i, "event-" + i));
    }

    @MessageMapping("audit.record")
    public Mono<Void> audit(
            @Payload AuditRecord record) {

        return Mono.fromRunnable(() ->
            log.info("audit kind={}, actor={}",
                record.kind(), record.actor()));
    }

    @MessageMapping("uppercase")
    public Flux<UppercaseReply> uppercase(
            @Payload Flux<UppercaseRequest> requests) {

        return requests.map(item ->
            new UppercaseReply(
                item.value().toUpperCase(Locale.ROOT)));
    }
}
~~~

Responder count giới hạn số phần tử, tránh một request yêu cầu stream quá lớn. Fire-and-forget chỉ log; nếu audit phải bền vững, nên có message queue hoặc request-response Ack riêng.

### RSocketCodecDemoApplication.java

~~~java
package com.example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketCodecDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketCodecDemoApplication.class, args);
    }
}
~~~

### ClientRunner.java

~~~java
package com.example.rsocket;

import java.util.List;

import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

public class ClientRunner {

    public static void main(String[] args) {
        // Chạy ngoài Spring context: tự cung cấp JSON codecs.
        RSocketStrategies strategies = RSocketStrategies.builder()
            .encoder(new Jackson2JsonEncoder())
            .decoder(new Jackson2JsonDecoder())
            .build();

        RSocketRequester requester = RSocketRequester.builder()
            .rsocketStrategies(strategies)
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .tcp("localhost", 7000);

        try {
            GreetingReply greeting = requester.route("greet")
                .data(new GreetingRequest("An"))
                .retrieveMono(GreetingReply.class)
                .block();

            System.out.println(greeting.message());

            List<NumberEvent> numbers = requester.route("count")
                .data(new CountRequest(3))
                .retrieveFlux(NumberEvent.class)
                .collectList()
                .block();

            numbers.forEach(n ->
                System.out.println(n.number() + ": " + n.label()));

            requester.route("audit.record")
                .data(new AuditRecord("login", "user-42"))
                .send()
                .block();

            System.out.println("Audit fire-and-forget sent");

            List<UppercaseReply> replies = requester
                .route("uppercase")
                .data(
                    Flux.just(
                        new UppercaseRequest("hello"),
                        new UppercaseRequest("rsocket")),
                    UppercaseRequest.class)
                .retrieveFlux(UppercaseReply.class)
                .collectList()
                .block();

            replies.forEach(r ->
                System.out.println(r.value()));
        } finally {
            requester.dispose();
        }
    }
}
~~~

ClientRunner chạy trên CLI main thread, vì vậy block() dùng để trình bày output theo thứ tự có thể chấp nhận được. Trong WebFlux handler, hãy trả Mono/Flux thay vì block event-loop.

Điểm quan trọng: nếu dùng RSocketRequester.builder() trực tiếp ngoài Spring context và không đặt rsocketStrategies(strategies), mặc định builder chỉ có codec cơ bản, không đủ để encode/decode mọi Java record. Tùy chỉnh JSON trong ClientRunner giải quyết vấn đề này. Trong integration test bên dưới, builder được inject từ Spring Boot nên đã nhận codecs auto-configured.

### Lệnh build và chạy

Từ thư mục chứa pom.xml:

~~~bash
mvn -q clean package
mvn spring-boot:run
~~~

Giữ terminal chạy server ở port 7000. Ở terminal thứ hai, chạy client:

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=com.example.rsocket.ClientRunner
~~~

Khi server và client chạy thành công, các dòng nghiệp vụ mong đợi:

~~~text
Xin chào, An
1: event-1
2: event-2
3: event-3
Audit fire-and-forget sent
HELLO
RSOCKET
~~~

Maven và logging framework có thể in các dòng log khác. Dòng Audit fire-and-forget sent không chứng minh server đã lưu sự kiện xuống durable storage.

## 17. Integration test JSON codec qua TCP

Test khởi động RSocket server với port 0, Boot cấp cổng ngẫu nhiên và inject bằng @LocalRSocketServerPort. Bốn test tương ứng bốn interaction model.

### RSocketCodecIntegrationTests.java

~~~java
package com.example.rsocket;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.rsocket.server.port=0",
    "spring.rsocket.server.transport=tcp"
})
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RSocketCodecIntegrationTests {

    @LocalRSocketServerPort
    private int port;

    @Autowired
    private RSocketRequester.Builder builder;

    private RSocketRequester requester;

    @BeforeAll
    void setUp() {
        requester = builder
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .tcp("127.0.0.1", port);
    }

    @AfterAll
    void tearDown() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseUsesJsonCodec() {
        StepVerifier.create(
                requester.route("greet")
                    .data(new GreetingRequest("An"))
                    .retrieveMono(GreetingReply.class))
            .expectNext(new GreetingReply("Xin chào, An"))
            .verifyComplete();
    }

    @Test
    void requestStreamDecodesMultipleDtos() {
        StepVerifier.create(
                requester.route("count")
                    .data(new CountRequest(3))
                    .retrieveFlux(NumberEvent.class))
            .expectNext(
                new NumberEvent(1, "event-1"),
                new NumberEvent(2, "event-2"),
                new NumberEvent(3, "event-3"))
            .verifyComplete();
    }

    @Test
    void fireAndForgetHasNoResponseBody() {
        StepVerifier.create(
                requester.route("audit.record")
                    .data(new AuditRecord("login", "user-42"))
                    .send())
            .verifyComplete();
    }

    @Test
    void channelEncodesAndDecodesFluxValues() {
        Flux<UppercaseRequest> input = Flux.just(
            new UppercaseRequest("hello"),
            new UppercaseRequest("rsocket"));

        StepVerifier.create(
                requester.route("uppercase")
                    .data(input, UppercaseRequest.class)
                    .retrieveFlux(UppercaseReply.class))
            .expectNext(
                new UppercaseReply("HELLO"),
                new UppercaseReply("RSOCKET"))
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Test dùng TCP RSocket transport thật với JSON encode/decode qua Spring Messaging. Nó xác minh cả route, data MIME type, codec, annotated responder và response type, chứ không chỉ unit test một hàm serializer.

Các điểm đáng kiểm tra khi test thất bại:

- application.properties có port cố định nhưng test đã override thành port ngẫu nhiên chưa?
- Spring Boot có chạy RSocket server không?
- Requester lấy đúng port từ @LocalRSocketServerPort chưa?
- dataMimeType application/json và Jackson codecs đã có ở cả hai phía chưa?
- Handler route và DTO có đúng không?
- Có application khác chiếm port không?

## 18. Tình huống triển khai: nhiều version codec và client

Khi requester và responder được deploy độc lập, cần một hợp đồng wire rõ ràng:

- Route name ổn định và có version nếu semantics thay đổi.
- Data MIME type được chọn trước khi kết nối.
- Metadata MIME type hỗ trợ route và các extension cần thiết.
- DTO schema tương thích giữa các version.
- Enum/date/time và null policy được thống nhất.
- Custom MIME type có encoder/decoder trên cả hai phía.
- Giới hạn message size phù hợp.
- Không ghi raw token hoặc payload nhạy cảm trong log.
- Có integration test với những version thực tế cùng chạy trên production.

Ví dụ một hệ thống đổi data format từ JSON sang CBOR cần cập nhật cả requester, responder và các service trung gian. Việc thay codec không chỉ là đổi một string application/json thành application/cbor; còn cần dependencies, test schema và kiểm tra hiệu năng.

Nếu cần backward compatibility, có thể triển khai song song hai endpoint/connection policy trong giai đoạn chuyển đổi, không ép client cũ kết nối bằng format chưa hỗ trợ.

## 19. Quan sát và chẩn đoán

Trong production, nên có metrics/log cho:

- Connection setup thành công/thất bại.
- Request theo route và interaction model.
- Latency, số message và bytes.
- Errors theo route, transport và codec.
- Cancel và timeout của stream.
- Reconnect và số connection sống.
- Backpressure và queue behavior khi tải cao.
- Memory/buffer usage cho payload lớn.

Log route và correlation ID, nhưng tránh lưu access token, bí mật và raw user payload. Với stream vô hạn hoặc channel dài, latency tới event đầu tiên và message rate hữu ích hơn tổng thời gian interaction.

### Chẩn đoán theo dấu hiệu

| Hiện tượng | Nguyên nhân cần xem |
| --- | --- |
| Không kết nối được | Host, port, TCP/WebSocket transport, server startup |
| SETUP bị từ chối | MIME type, authentication/setup metadata, protocol config |
| Route not found | route(), @MessageMapping, routing metadata, RouteMatcher |
| Không encode được DTO | Encoder phù hợp Java type và data MIME type |
| Response decode error | Decoder/target type/schema |
| Chỉ String hoạt động, record lỗi | Requester tạo ngoài Boot không có JSON codec |
| Stream ngừng giữa chừng | onError, cancel, timeout hoặc transport disconnection |
| FNF gửi thành công nhưng không có dữ liệu lưu | FNF không có business acknowledgment |
| Memory tăng khi channel dài | Buffer/queue không giới hạn hoặc cleanup thiếu |
| Nhiều event trùng sau reconnect | Retry không có idempotency/deduplication |

## 20. Những lỗi thường gặp

1. **Nhầm RSocket và raw WebSocket.** WebSocket là transport; RSocket có protocol và interaction semantics riêng.
2. **Dùng connectTcp() mới thay vì tcp().** Trên Spring 6.1, phương thức cũ đã deprecated; nên dùng tcp().
3. **Cho rằng tcp() luôn kết nối ngay.** Requester dùng connection chia sẻ, thường kết nối khi có request.
4. **Tạo requester mới mỗi message.** Gây churn và khó cleanup; dùng requester lâu dài.
5. **Quên dispose().** Connection có thể giữ tài nguyên sau shutdown/test.
6. **Tạo requester ngoài Boot và thiếu JSON codec.** DTO không encode được dù server có hỗ trợ JSON.
7. **Thêm encoder mà không có decoder.** Gửi được request nhưng không đọc được response.
8. **Không khai báo data MIME type khi codec có nhiều format.** Có thể thương lượng format không như dự kiến.
9. **Nhầm data MIME và metadata MIME.** Route metadata được encode khác application data.
10. **Thay metadata MIME không hiểu composite metadata.** @MessageMapping có thể không tìm được route.
11. **Gửi metadata tùy chỉnh không khai báo extractor.** Server không tự có header để đọc.
12. **Dùng retrieveMono() cho stream nhiều phần tử.** Chọn retrieveFlux đúng interaction.
13. **Dùng send() như business Ack.** Fire-and-forget không chứng minh xử lý bền vững.
14. **Không truyền element type cho Flux phức tạp.** Codec lookup có thể khó hoặc chậm; dùng data(flux, Type.class).
15. **Decode generic bằng List.class.** Mất type của phần tử; dùng ParameterizedTypeReference.
16. **Tự subscribe trong responder.** Làm mất liên kết lifecycle/error; trả publisher.
17. **block() trong WebFlux event loop.** Gây nghẽn; dùng reactive composition.
18. **Retry FNF không idempotency.** Gây side effect trùng.
19. **Không giới hạn payload và concurrent stream.** Dễ tăng memory/cpu khi quá tải.
20. **Tùy chỉnh DataBufferFactory không hiểu pooled buffer.** Có thể gây memory leak hoặc frame decoder conflict.
21. **Đồng nhất reconnect với replay.** Connection mới không bảo đảm request cũ được gửi lại đúng một lần.
22. **Không test trên transport thực.** Unit test codec không phát hiện lỗi setup/route/metadata.

## 21. Checklist triển khai

Trước khi phát hành một RSocket client/responder:

- **Interaction model:** chọn Mono, Flux, FNF hay channel?
- **Transport:** hai phía cùng TCP, WebSocket hay transport khác?
- **Lifecycle:** requester được tái sử dụng và dispose đúng không?
- **SETUP:** dataMimeType và metadataMimeType có tương thích không?
- **Routing:** route string khớp @MessageMapping không?
- **Encoder/Decoder:** hai phía có codec cho DTO và MIME type không?
- **Strategies:** có dùng Boot-managed bean/builder khi chạy trong Spring không?
- **Custom codec:** có test round-trip và version compatibility không?
- **Metadata:** custom metadata có extractor ở responder không?
- **Generics:** khi cần, có dùng type hint và ParameterizedTypeReference không?
- **Backpressure:** stream có tôn trọng demand, cancel và overflow policy không?
- **Timeout:** client có deadline phù hợp?
- **Retry:** operation có idempotent hoặc deduplication không?
- **Security:** setup/request metadata và transport được bảo vệ không?
- **Monitoring:** route, errors, latency, reconnect có được quan sát không?
- **Tests:** đã test bốn interaction model qua real RSocket chưa?

## 22. Bài tập tự kiểm tra

**Câu 1.** RSocketRequester giúp gì so với io.rsocket.RSocket mức thấp?  
**Đáp án:** Gửi request bằng Java object với route/metadata và codec, thay vì tự xử lý Payload.

**Câu 2.** Builder.tcp() trả kiểu gì trong Spring Framework 6.1?  
**Đáp án:** RSocketRequester, dùng connection lazy/shared.

**Câu 3.** Hai MIME type quan trọng trong SETUP là gì?  
**Đáp án:** Data MIME type và metadata MIME type.

**Câu 4.** RSocketStrategies có những phần chính nào?  
**Đáp án:** Encoder, Decoder, RouteMatcher, MetadataExtractor, DataBufferFactory và ReactiveAdapterRegistry.

**Câu 5.** RSocket routing thường dùng metadata MIME type nào?  
**Đáp án:** message/x.rsocket.routing.v0 trong composite metadata.

**Câu 6.** Khi nào dùng retrieveFlux()?  
**Đáp án:** Khi tương tác mong đợi nhiều response message.

**Câu 7.** Vì sao send() không phải business Ack?  
**Đáp án:** Fire-and-forget không có response nghiệp vụ xác nhận xử lý.

**Câu 8.** Dùng data(flux, Type.class) có lợi ích gì?  
**Đáp án:** Cung cấp type hint để chọn encoder rõ ràng cho nhiều phần tử.

**Câu 9.** Boot cung cấp callback nào để tùy chỉnh codec?  
**Đáp án:** RSocketStrategiesCustomizer.

**Câu 10.** Requester tạo ngoài Spring context cần lưu ý gì với DTO?  
**Đáp án:** Phải cấu hình Jackson JSON/CBOR codecs và MIME tương ứng nếu dùng DTO.

**Câu 11.** MetadataExtractor làm gì?  
**Đáp án:** Trích metadata như routing hoặc custom fields để Spring Messaging dùng khi xử lý.

**Câu 12.** Vì sao request-channel cần backpressure?  
**Đáp án:** Vì nhiều message hai chiều có thể tích lũy nếu producer nhanh hơn consumer.

**Câu 13.** Có nên retry FNF vô điều kiện khi network lỗi?  
**Đáp án:** Không; server có thể đã xử lý message, gây side effect trùng.

**Câu 14.** Vì sao nên test qua TCP server thật?  
**Đáp án:** Test được SETUP, route, codec và annotated responder xuyên suốt, không chỉ serializer.

## 23. Ghi nhớ

RSocketRequester cung cấp API fluent để gửi RSocket request theo route, data và metadata, nhận kết quả qua retrieveMono(), retrieveFlux() hoặc gửi FNF bằng send(). Builder.tcp() và websocket() trả requester có shared connection theo nhu cầu; nên tái sử dụng và dispose đúng lifecycle.

RSocketStrategies quyết định encode/decode object, xử lý route/metadata và buffer. Codec phải tương thích Java type lẫn data MIME type đã được khai báo tại SETUP. Composite metadata cho phép route và các metadata entry khác có MIME type riêng. Spring Boot starter thường cấu hình sẵn RSocketStrategies và RSocketRequester.Builder; code ngoài Spring context cần cung cấp codec cho DTO.

RSocket có backpressure qua REQUEST_N đối với stream/channel, nhưng ứng dụng vẫn phải giới hạn concurrency, buffer, timeout và retry. Fire-and-forget không phải business acknowledgement. Khi thay đổi DTO hoặc codec, kiểm thử tương thích giữa các phiên bản và chạy integration test qua transport thực.

### Tài liệu tham khảo

- Spring Framework, [RSocket overview, requester và strategies](https://docs.spring.io/spring-framework/reference/rsocket.html).
- Spring Framework 6.1, [RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html).
- Spring Framework 6.1, [RSocketStrategies.Builder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html).
- Spring Framework 6.1, [RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html).
- Spring Boot 3.3, [RSocket auto-configuration](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/messaging.html#messaging.rsocket).
- Spring Boot Javadoc, [RSocketStrategiesCustomizer](https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/rsocket/messaging/RSocketStrategiesCustomizer.html).
- Project Reactor, [Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- RSocket, [Protocol](https://rsocket.io/about/protocol/).
