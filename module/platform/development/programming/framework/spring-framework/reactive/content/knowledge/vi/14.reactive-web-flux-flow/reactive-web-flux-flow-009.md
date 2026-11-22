# Ranh giới giữa sự kiện mạng, codec và xử lý nghiệp vụ

**Ngữ cảnh:** Spring Framework Reactive → **Luồng xử lý WebFlux**.

Một request WebFlux đi qua nhiều lớp trước khi dữ liệu trở thành đối tượng Java mà service có thể xử lý. Trên đường vào, server nhận byte từ kết nối HTTP, adapter chuyển I/O thành tín hiệu reactive, codec đọc byte và giải mã nội dung, rồi controller/service mới làm việc với DTO hoặc domain object. Trên đường ra, kết quả nghiệp vụ đi qua encoder/HTTP message writer, được chuyển thành byte và gửi qua transport tới client.

Điểm quan trọng là **sự kiện mạng, buffer byte, phần tử đã giải mã và sự kiện nghiệp vụ là bốn khái niệm khác nhau**. Một TCP packet không tương ứng với một JSON object; một `DataBuffer` không nhất thiết chứa trọn một event; một `onNext(Dto)` không chứng minh client đã render hoặc xử lý nghiệp vụ xong. Hiểu đúng các ranh giới này giúp thiết kế streaming, backpressure, validation, lỗi, cancellation và quản lý bộ nhớ chính xác.

## 1. Bản đồ xử lý request và response

```text
CLIENT
  │ HTTP bytes (TCP hoặc QUIC; có thể qua TLS/proxy)
  ▼
SERVER ADAPTER (Reactor Netty hoặc adapter non-blocking khác)
  │ chuyển I/O thành request/response abstractions
  ▼
HttpHandler → WebHandler chain → WebFilter
  │
  ▼
DispatcherHandler / RouterFunction
  │ tìm handler và chuẩn bị arguments
  ▼
HttpMessageReader + Decoder
  │ DataBuffer → content → DTO
  ▼
CONTROLLER / HANDLER
  │ Publisher<DTO>
  ▼
APPLICATION SERVICE
  │ validation, authorization, domain rules, persistence
  ▼
Publisher<DomainResult>
  │
  ▼
Encoder + HttpMessageWriter
  │ DTO/domain result → DataBuffer / HTTP content
  ▼
SERVER ADAPTER → NETWORK → PROXY → CLIENT
```

Đây là mô hình kiến trúc, không phải danh sách thread hay chuỗi hàm cố định cho mọi server. WebFlux có hai mô hình lập trình chính:

- **Annotated controllers:** khai báo bằng `@RestController`, `@GetMapping`, `@PostMapping`; framework tìm handler, giải mã argument và ghi response.
- **Functional endpoints:** dùng `RouterFunction` và `HandlerFunction`; ứng dụng mô tả route và handler bằng hàm.

Cả hai cùng dựa trên reactive web foundation và các abstraction HTTP/codec của Spring.

| Lớp | Trách nhiệm | Dữ liệu thường thấy |
|---|---|---|
| Server adapter | Nhận/gửi I/O từ server runtime | ByteBuffer, ByteBuf, socket events |
| `HttpHandler` / `WebHandler` | Cầu nối request/response và web filter chain | `ServerHttpRequest`, `ServerHttpResponse` |
| Dispatcher / Router | Chọn controller hoặc handler | Path, method, headers |
| `HttpMessageReader` / Decoder | Đọc HTTP body và giải mã | `DataBuffer` → DTO |
| Controller / Handler | Điều phối request, tạo response publisher | `Mono<Dto>`, `Flux<Dto>` |
| Service/domain | Thực thi quy tắc nghiệp vụ | Command, event, entity, result |
| Encoder / `HttpMessageWriter` | Mã hóa body response | DTO → `DataBuffer` |
| Transport/proxy/client | Truyền byte và tiêu thụ response | HTTP frames, network buffers |

Spring cung cấp `HttpHandler` làm contract xử lý request với non-blocking I/O và Reactive Streams backpressure; các adapter kết nối contract đó với server runtime. Codecs đọc/ghi nội dung qua `DataBuffer`. Xem [Spring WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).

## 2. Phân biệt bốn loại event

Khi debug một luồng WebFlux, hãy xác định đang nói tới loại dữ liệu nào:

1. **Network event / transport bytes:** byte được nhận hoặc gửi bởi TCP/QUIC và HTTP implementation. Chúng không mang ý nghĩa domain.
2. **Buffer event:** một `DataBuffer` hoặc `ByteBuf` chứa một vùng byte. Buffer có thể chứa một phần thông điệp, nhiều phần thông điệp hoặc ranh giới bất kỳ tùy tầng.
3. **Codec output:** đối tượng Java mà decoder tạo ra, ví dụ `EventDto`. Đây là đơn vị dữ liệu của ứng dụng sau giải mã.
4. **Business event:** sự kiện hoặc command có ý nghĩa nghiệp vụ sau khi ứng dụng xác thực, kiểm tra và áp dụng quy tắc domain, ví dụ `OrderAccepted`.

Ví dụ client gửi NDJSON:

```text
{"id":"e-1","amount":10}\n
{"id":"e-2","amount":20}\n
```

Ứng dụng có thể nhận byte theo nhiều lần đọc socket. Một buffer có thể kết thúc giữa chuỗi `"amount"`; buffer tiếp theo tiếp tục phần còn lại. Decoder nhận biết ranh giới record NDJSON, tạo hai DTO, sau đó service có thể tạo hai kết quả nghiệp vụ. Không được giả định mỗi lần đọc socket là một dòng JSON.

### Ranh giới không ánh xạ 1:1

| Quan sát | Có thể đúng | Không được suy ra |
|---|---|---|
| Một TCP packet đã tới | Một số byte đã tới tầng TCP | Một JSON object đã hoàn chỉnh |
| Một HTTP/2 DATA frame đã tới | Một đoạn content của stream đã tới | Một DTO đã giải mã xong |
| Một `DataBuffer` được phát | Một vùng byte sẵn cho codec | Một message/event trọn vẹn |
| Một `onNext(EventDto)` | Decoder đã tạo một DTO | Service đã lưu event hoặc client đã xử lý nó |
| Một response write hoàn tất ở adapter | Một tầng ghi đã nhận dữ liệu | Browser đã render hoặc người dùng đã nhìn thấy |
| Client gửi TCP ACK | Byte đã được TCP bên kia xác nhận theo giao thức | Nghiệp vụ đã commit hoặc được xác nhận |

TLS, HTTP framing, compression, buffering, proxy và network segmentation đều có thể chia/gộp dữ liệu. Ranh giới message phải được xác định bởi protocol và codec, không phải ranh giới packet.

## 3. Server adapter, HttpHandler và filter chain

WebFlux không bắt buộc chỉ chạy trên một loại server. Tùy dependency và cấu hình, reactive web stack có thể được nối với Reactor Netty hoặc adapter non-blocking của một số server/Servlet container.

`HttpHandler` cung cấp contract thấp cho request và response. `WebHandler` xây dựng web processing chain cao hơn; `WebFilter` có thể chạy logic chung như security, tracing, CORS hoặc correlation ID. Với annotated controllers, `DispatcherHandler` điều phối việc tìm handler và gọi handler adapter. Với functional endpoints, router chọn `HandlerFunction`.

Một WebFilter minh họa việc gắn correlation ID:

```java
@Component
public class CorrelationFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String id = exchange.getRequest().getHeaders()
                .getFirst("X-Request-Id");

        if (id == null || id.isBlank()) {
            id = UUID.randomUUID().toString();
        }

        exchange.getResponse().getHeaders().set("X-Request-Id", id);
        String requestId = id;

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put("requestId", requestId));
    }
}
```

Đây là snippet cần import và cấu hình component Spring. `contextWrite` đưa dữ liệu vào Reactor Context cho operator downstream có thể đọc bằng `deferContextual`. Không dựa vào `ThreadLocal` thông thường để mang context qua mọi scheduler boundary.

Filter chạy ở ranh giới request, phù hợp với logic cross-cutting. Nó không nên tự đọc body rồi subscribe riêng để log, bởi request body là một publisher có vòng đời và ownership cụ thể; việc tiêu thụ sai cách có thể khiến controller không còn body để đọc.

## 4. Codec: từ DataBuffer thành DTO và ngược lại

Spring tách việc encode/decode thành các abstraction:

- `Encoder<T>` và `Decoder<T>` xử lý chuyển đổi nội dung độc lập với HTTP.
- `HttpMessageReader<T>` đọc HTTP message content và tạo đối tượng.
- `HttpMessageWriter<T>` ghi đối tượng thành HTTP response content.
- `DataBuffer` là abstraction cho vùng byte; implementation có thể dựa trên Netty `ByteBuf` hoặc `ByteBuffer`.

Luồng request:

```text
Flux<DataBuffer>
       │
       ▼
Decoder / HttpMessageReader
       │
       ├── parse framing / character encoding
       ├── deserialize JSON / NDJSON / form / SSE ...
       ▼
Flux<EventDto>
```

Luồng response:

```text
Mono<Dto> hoặc Flux<Dto>
       │
       ▼
Encoder / HttpMessageWriter
       │
       ├── serialize object
       ├── chọn content type / format
       ▼
Publisher<DataBuffer>
       │
       ▼
HTTP adapter
```

Controller thường không cần tự gọi encoder hoặc thao tác byte. Framework chọn reader/writer dựa trên loại argument/return value, content type, Accept header và codec đã cấu hình.

Tài liệu nền tảng: [Spring Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html) và [WebFlux codec configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).

## 5. Request body: Mono, Flux và kiểu Java ảnh hưởng cách đọc

Ví dụ controller nhận một JSON object:

```java
@PostMapping("/profile")
public Mono<ProfileDto> save(@RequestBody Mono<ProfileDto> body) {
    return body.flatMap(profileService::save);
}
```

`Mono<ProfileDto>` biểu diễn một object được giải mã hoặc lỗi/empty theo contract của publisher. Framework quản lý việc đọc request body và subscription cần thiết.

Với một luồng record:

```java
@PostMapping(
        path = "/events",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Void> ingest(@RequestBody Flux<EventDto> events) {
    return events.concatMap(eventService::process).then();
}
```

`Flux<EventDto>` cho phép xử lý các phần tử theo luồng. `concatMap` subscribe vào từng thao tác xử lý và đợi inner hoàn tất trước khi chuyển sang item tiếp theo; `then()` trả `Mono<Void>` chỉ hoàn tất khi chuỗi thành công.

| Kiểu argument | Ý nghĩa ở tầng ứng dụng | Cân nhắc |
|---|---|---|
| `@RequestBody Mono<Dto>` | Một body object | Hợp với command/resource đơn |
| `@RequestBody Flux<Dto>` | Nhiều item có thể xử lý theo luồng | Cần định nghĩa framing, validation và giới hạn từng item |
| `@RequestBody Mono<List<Dto>>` | Một collection đã được gom thành list | Bộ nhớ tăng theo toàn bộ collection; cần giới hạn |
| `@RequestBody String` | Nội dung text đã đọc/giải mã | Không thích hợp cho body lớn nếu phải aggregate |
| `@RequestBody Flux<DataBuffer>` | Byte buffers thô | Ứng dụng chịu trách nhiệm parse và quản lý buffer đúng cách |

**Đừng chọn `Mono<List<T>>` chỉ vì JSON có dấu ngoặc vuông.** Nếu request lớn hoặc stream dài, kiểu collection đồng nghĩa ứng dụng cần có toàn bộ list trước khi xử lý theo kiểu đó. `Flux<T>` phù hợp khi có thể xử lý từng phần tử và codec hỗ trợ format streaming đã chọn.

### JSON array, NDJSON và SSE

- **JSON array** có cấu trúc một tài liệu JSON gồm nhiều phần tử. Decoder có thể giải mã phần tử thành `Flux<T>`, nhưng không được giả định cách client/server flush từng phần tử giống NDJSON.
- **NDJSON** phân cách record bằng newline, phù hợp cho nhiều JSON object liên tiếp trong một body.
- **SSE** dùng format event text với các field như `data:`, `id:` và dòng trống kết thúc event. WebFlux có hỗ trợ codec cho Server-Sent Events.
- **Multipart/form-data** có framing và cách lưu trữ riêng; file lớn cần cân nhắc streaming và giới hạn dung lượng.

Media type là một phần hợp đồng API. Gửi JSON object nhưng khai báo NDJSON, hoặc gửi SSE mà không có framing SSE hợp lệ, sẽ làm decoder/client không hiểu đúng nội dung.

## 6. Response body: DTO được ghi thành byte như thế nào?

Controller có thể trả `Mono<Dto>` hoặc `Flux<Dto>`:

```java
@GetMapping("/profile/{id}")
public Mono<ProfileDto> getProfile(@PathVariable String id) {
    return profileService.findById(id);
}

@GetMapping(path = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<EventDto> events() {
    return eventService.streamEvents();
}
```

`Mono<ProfileDto>` thường đại diện một response object. `Flux<EventDto>` có thể đại diện một chuỗi phần tử được encode theo media type được chọn. Writer xử lý serialization và gửi content qua server adapter.

**Một `onNext` không đồng nghĩa một lần ghi socket hoặc một packet.** Encoder có thể tạo một hay nhiều DataBuffer; adapter, TLS và network có thể gom hoặc chia byte. Ngay cả khi format streaming, thời điểm client nhìn thấy từng item phụ thuộc flush policy, buffering và transport.

Khi trả `Flux<T>` với `application/json`, response thường có dạng JSON array. Tùy writer và cấu hình, dữ liệu có thể được ghi dần; tuy nhiên client parser có thể vẫn chờ tài liệu hoàn chỉnh trước khi đưa từng object lên tầng ứng dụng.

NDJSON hoặc SSE biểu đạt ranh giới record/event rõ hơn cho consumer streaming. Với SSE, Reactor Netty có chiến lược flush từng phần tử của publisher khi dùng SSE response API; proxy/client vẫn có thể buffering ở tầng khác.

### Không tự subscribe trong controller

Controller nên trả publisher cho framework:

```java
@GetMapping("/feed")
public Flux<EventDto> feed() {
    return eventService.streamEvents();
}
```

Không làm như sau:

```java
@GetMapping("/feed")
public Mono<Void> wrong() {
    eventService.streamEvents().subscribe();
    return Mono.empty();
}
```

Đoạn sai tạo subscription tách rời; HTTP response có thể complete trước khi feed xử lý xong, lỗi và cancellation không còn thuộc response. Nếu công việc là một phần của response, hãy compose và return publisher.

## 7. Ranh giới giữa codec và nghiệp vụ

Codec chịu trách nhiệm biến đổi **representation**; service chịu trách nhiệm kiểm tra và thực hiện **ý nghĩa nghiệp vụ**.

Ví dụ request JSON:

```json
{
  "eventId": "evt-100",
  "accountId": "acct-7",
  "amount": 250
}
```

Sau khi decoder tạo `TransferRequest`, service vẫn cần kiểm tra:

1. Cấu trúc/field bắt buộc có hợp lệ không?
2. Kiểu và miền giá trị có đúng không?
3. Người gọi có quyền thực hiện hành động không?
4. Account có tồn tại và ở trạng thái cho phép không?
5. Số dư, hạn mức và quy tắc nghiệp vụ có thỏa không?
6. Request có idempotency key hoặc event ID để tránh xử lý trùng không?
7. Việc ghi dữ liệu và phát event có nằm trong transaction/outbox phù hợp không?

JSON parse thành công **không có nghĩa nghiệp vụ hợp lệ**. Một request có thể hợp lệ về cú pháp nhưng bị từ chối vì business rule. Hãy phân biệt lỗi representation, validation và domain failure để ánh xạ HTTP status phù hợp.

### DTO không nhất thiết là domain entity

Nên xem DTO là cấu trúc transport. Chuyển sang command/value object/domain model tại application boundary giúp domain không phụ thuộc tên field, Jackson annotation hay format HTTP. Với API nhỏ, DTO có thể dùng trực tiếp ở service; với domain phức tạp, tách lớp giúp kiểm soát thay đổi và bảo mật.

Không bind trực tiếp request vào entity persistence có quyền cập nhật mọi field. Điều đó có thể cho phép client sửa field nội bộ, trạng thái hoặc ownership mà API không định cung cấp.

## 8. Xử lý nhiều event: thứ tự, concurrency và backpressure

Sau khi codec phát `Flux<EventDto>`, cách kết hợp service quyết định tốc độ và thứ tự nghiệp vụ.

### concatMap: tuần tự

```java
Flux<ProcessedEvent> result = incoming
        .concatMap(event -> service.process(event), 1);
```

Inner publisher được xử lý tuần tự; item sau chờ item trước hoàn tất. Phù hợp khi thứ tự cập nhật cùng một aggregate quan trọng hoặc muốn giới hạn công việc đồng thời ở một subscription.

### flatMap: cho phép đồng thời

```java
Flux<ProcessedEvent> result = incoming
        .flatMap(event -> service.process(event), 8);
```

Tối đa tám inner publisher được quản lý đồng thời theo overload này. Kết quả có thể xen kẽ theo thời gian hoàn tất; không bảo đảm cùng thứ tự input. Con số 8 không phải giới hạn tổng connection, byte, DB pool hay toàn hệ thống.

### flatMapSequential: chạy đồng thời nhưng giữ thứ tự output

```java
Flux<ProcessedEvent> result = incoming
        .flatMapSequential(event -> service.process(event), 8);
```

Operator có thể subscribe nhiều inner đồng thời nhưng giữ thứ tự phát kết quả theo thứ tự nguồn; kết quả hoàn tất sớm hơn có thể phải chờ trong buffer. Cần giới hạn concurrency và hiểu chi phí buffering.

### Buffering không biến thành xử lý bền vững

- `buffer(n)` gom nhiều item thành một collection; giảm số lần gọi downstream nhưng tăng memory theo batch.
- `collectList()` gom toàn bộ stream trước khi phát một list; không phù hợp nguồn vô hạn hoặc body lớn không có giới hạn.
- `publishOn` tạo ranh giới scheduler và có prefetch/buffer riêng.
- `limitRate` điều chỉnh request upstream tại vị trí operator; không giới hạn tổng byte mạng hay mọi queue.
- `onBackpressureBuffer` cần giới hạn và overflow policy rõ ràng; buffer không giới hạn có thể dẫn tới OOM.

Backpressure điều tiết demand giữa các publisher/subscriber có hỗ trợ; nó không thay thế quota request, giới hạn payload, concurrency limit, database pool hay durable queue.

## 9. DataBuffer và quyền sở hữu bộ nhớ

`DataBuffer` là abstraction quan trọng vì codec và HTTP layer làm việc trên byte. Với Reactor Netty, buffer có thể dựa trên pooled, reference-counted Netty `ByteBuf`. Vì vậy, **buffer có vòng đời và quyền sở hữu**, không phải lúc nào cũng là byte array được GC tự do.

Quy tắc thực hành:

- Trong controller thông thường nhận DTO qua `@RequestBody`, để framework/codec quản lý buffer.
- Khi tự xử lý `Flux<DataBuffer>`, xác định rõ ai sở hữu buffer và lúc nào nó được release.
- Nếu giữ buffer để xử lý sau, phải bảo đảm release trên cả complete, error và cancel.
- Khi operator loại bỏ item, kiểm tra discard support và giải phóng pooled buffer đúng cách.
- Tránh gọi `retain()` trừ khi cần giữ reference qua ranh giới ownership; nếu retain, phải có nơi release tương ứng.
- Không release buffer hai lần và không đọc buffer sau khi đã release.

### Khi cần gom body vào một buffer

`DataBufferUtils.join(...)` có thể nối nhiều buffer thành một buffer tổng hợp. Khi cần giới hạn, dùng overload có `maxByteCount` để tránh aggregate body không giới hạn.

```java
Mono<String> bodyText = DataBufferUtils
        .join(request.getBody(), 1024 * 1024)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
```

Đây là snippet cho trường hợp **chủ động aggregate body tối đa 1 MiB**; cần `ServerHttpRequest`, `DataBufferUtils`, `StandardCharsets` và Reactor import. Buffer joined được release sau khi đọc. Trong ứng dụng thật, nếu có thể xử lý từng item thì nên stream thay vì gom toàn bộ body.

### doOnDiscard khi operator có thể bỏ DataBuffer

```java
Flux<DataBuffer> filtered = body
        .filter(this::isRelevant)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là snippet cần kiểm tra ownership và operator discard support. `doOnDiscard` là hook cho các phần tử bị loại bỏ ở những operator hỗ trợ discard; nó không phải cách giải phóng mọi buffer ở mọi path. Không thêm hook release một cách máy móc vào pipeline DTO bình thường.

Tài liệu chi tiết: [Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).

## 10. Giới hạn codec và bảo vệ request

Codec có thể cần buffer để decode một object, aggregate form/multipart hoặc xử lý nội dung không streaming. Cấu hình `maxInMemorySize` giúp giới hạn một số thao tác aggregate của codec:

```java
@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(256 * 1024);
    }
}
```

Đây là ví dụ cấu hình giới hạn 256 KiB cho các trường hợp codec áp dụng; con số chỉ minh họa, cần chọn theo payload thực tế và codec. Với Spring Boot, khi chỉ cần tùy chỉnh một phần, dùng `WebFluxConfigurer` mà không thêm `@EnableWebFlux` để giữ các customizations của Boot.

**maxInMemorySize không phải quota RAM tổng của ứng dụng.** Nó không tự giới hạn mọi DataBuffer, Netty direct memory, queue của operator, object do service tạo, `collectList()` hay buffer ở proxy.

Ngoài codec limit, production thường cần:

- Giới hạn request body bytes và multipart/file size.
- Giới hạn kích thước từng event/record và độ sâu JSON phù hợp.
- Giới hạn số request/stream đồng thời, rate limit và timeout.
- Giới hạn concurrency của service và connection pool.
- Giới hạn queue/buffer theo item **và** byte khi payload có kích thước biến thiên.
- Chính sách overload rõ: reject, error, drop/latest hay lưu vào durable queue.
- Authentication/authorization trước khi xử lý business command.
- Giám sát direct memory, heap, queue, latency và số kết nối.

## 11. Ranh giới lỗi: network, codec, validation và business

Không phải mọi lỗi đều cùng một loại. Phân biệt nơi lỗi phát sinh để trả HTTP status và log đúng.

| Lớp | Ví dụ | Cách xử lý thường gặp |
|---|---|---|
| Network / server adapter | Client reset, timeout, TLS handshake failure | Quan sát transport, timeout, connection lifecycle |
| HTTP protocol | Method/path/header/framing không hợp lệ | HTTP server/protocol handling |
| Codec / deserialization | JSON malformed, sai kiểu field, vượt giới hạn decode | 400 hoặc lỗi representation phù hợp |
| Validation | Field thiếu, amount âm, format nghiệp vụ không đạt | 400/422 theo API contract |
| Authorization | User không có quyền trên resource | 401/403 |
| Domain | Account đóng, hạn mức vượt, trạng thái không cho phép | 409/422 hoặc status theo contract |
| Persistence / dependency | DB unavailable, downstream timeout | 5xx, retry có giới hạn nếu an toàn |
| Response encoding | Object không serialize được hoặc buffer lỗi | Response stream có thể fail giữa chừng |
| Client disconnect | Consumer đóng kết nối khi stream đang chạy | Cancellation/transport signal, không mặc định là business error |

### Trước và sau khi response commit

Nếu lỗi xảy ra **trước khi response headers/body được commit**, framework thường còn khả năng tạo error response với status/body phù hợp.

Nếu lỗi xảy ra **sau khi streaming response đã bắt đầu**, status và headers có thể đã gửi. Server không thể quay lại đổi HTTP 200 thành 500 hoặc thay toàn bộ response bằng một JSON error document. Stream có thể kết thúc bất thường; client cần nhận biết lỗi theo giao thức ứng dụng (nếu cần) hoặc reconnect/resume.

Với SSE, nếu muốn báo business error trong một event, hãy định nghĩa event type/error payload theo hợp đồng SSE. Một `onError` reactive không tự biến thành event SSE hợp lệ.

Không dùng `onErrorComplete()` một cách vô thức để che lỗi JSON malformed thành “body rỗng”. Cũng không chuyển lỗi database thành `Mono.empty()` nếu empty có nghĩa “không tìm thấy”. Giữ phân biệt giữa không có dữ liệu, dữ liệu sai và dependency thất bại.

## 12. Cancellation và vòng đời request

Khi client ngắt kết nối hoặc không còn nhận response, adapter có thể hủy subscription của response body. Cancellation có thể truyền qua publisher chain tới inner publisher đang hoạt động, nếu operator và source hỗ trợ.

```java
@GetMapping(path = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Update>> stream() {
    return updateService.stream()
            .map(update -> ServerSentEvent.builder(update).build())
            .doOnCancel(() -> log.info("stream cancelled"))
            .doFinally(signal -> log.debug("stream finished: {}", signal));
}
```

Đây là snippet; cần service, DTO và logger. `doOnCancel` quan sát cancellation; `doFinally` quan sát complete, error hoặc cancel. Các hook này phục vụ observability; resource thật nên được quản lý bằng publisher-scoped lifecycle như `using`/`usingWhen` hoặc transaction/resource operator phù hợp.

**Cancellation không phải rollback.** Nếu service đã gửi lệnh sang database hoặc payment provider, cancel request không bảo đảm side effect bên ngoài bị hoàn tác. Với thao tác ghi quan trọng, cần idempotency, transaction, outbox, trạng thái job và reconciliation.

Nếu tác vụ phải tiếp tục dù client đóng kết nối, hãy tách nó thành job có owner riêng (durable queue/background worker) và trả job ID. Đừng tự gọi `subscribe()` trong controller để biến một phần của response thành fire-and-forget vô chủ.

## 13. Functional endpoints: cùng ranh giới, cách khai báo khác

Functional endpoint có thể đọc body thành publisher bằng `bodyToFlux`:

```java
@Bean
RouterFunction<ServerResponse> eventRoutes(EventService service) {
    return RouterFunctions.route()
            .POST("/events",
                    request -> request.bodyToFlux(EventDto.class)
                            .concatMap(service::process, 1)
                            .as(results -> ServerResponse.ok()
                                    .contentType(MediaType.APPLICATION_NDJSON)
                                    .body(results, ProcessedEvent.class)))
            .build();
}
```

Đây là snippet cần các kiểu `EventDto`/`ProcessedEvent`, service và imports. `bodyToFlux` vẫn dựa trên codec để chuyển request content thành object; `ServerResponse.body` dùng writer/encoder để chuyển publisher kết quả thành response content. Thay đổi programming model không thay đổi ranh giới byte → codec → business → writer.

## 14. Ví dụ Java 17+ chạy độc lập: codec output → business → response representation

Ví dụ này dùng Reactor Core, không dựng HTTP server. Nó mô phỏng **phần giữa của WebFlux pipeline sau khi codec đã tạo DTO và trước khi HTTP writer gửi byte**. Nhờ vậy, output có thể xác định và tập trung vào ranh giới xử lý.

Cấu trúc:

```text
webflux-boundary-demo/
├── pom.xml
└── src/main/java/demo/WebFluxBoundaryDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-boundary-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/WebFluxBoundaryDemo.java`:

```java
package demo;

import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class WebFluxBoundaryDemo {

    record EventDto(String id, int amount) { }
    record ProcessedEvent(String id, int acceptedAmount) { }

    private static Mono<ProcessedEvent> process(EventDto event) {
        return Mono.fromSupplier(() -> {
            System.out.println("business: " + event.id());

            if (event.amount() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            return new ProcessedEvent(event.id(), event.amount());
        });
    }

    private static String encode(ProcessedEvent event) {
        return "{\"id\":\"" + event.id()
                + "\",\"acceptedAmount\":" + event.acceptedAmount() + "}";
    }

    public static void main(String[] args) {
        // Đại diện cho Flux<EventDto> do HttpMessageReader/Decoder tạo ra.
        Flux<EventDto> decodedByCodec = Flux.fromIterable(List.of(
                new EventDto("e-1", 10),
                new EventDto("e-2", 20)
        ));

        decodedByCodec
                .doOnNext(event ->
                        System.out.println("codec->dto: " + event.id()))
                .concatMap(WebFluxBoundaryDemo::process, 1)
                .map(WebFluxBoundaryDemo::encode)
                .subscribe(
                        line -> System.out.println("response representation: " + line),
                        error -> System.out.println("processing error: "
                                + error.getMessage()),
                        () -> System.out.println("publisher complete")
                );
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebFluxBoundaryDemo
```

**Standard output dự kiến** (không tính thông báo Maven):

```text
codec->dto: e-1
business: e-1
response representation: {"id":"e-1","acceptedAmount":10}
codec->dto: e-2
business: e-2
response representation: {"id":"e-2","acceptedAmount":20}
publisher complete
```

Giải thích:

1. `decodedByCodec` đại diện đầu ra của HTTP message reader. Trong chương trình demo, DTO đã được tạo sẵn bằng `Flux.fromIterable`; không có socket hoặc JSON decoder thực.
2. `doOnNext` quan sát mỗi DTO ở ranh giới codec → application.
3. `concatMap` gọi business function và đợi từng inner `Mono` hoàn tất trước item kế tiếp.
4. `map(encode)` tạo representation dạng JSON string để minh họa bước application result → encoder.
5. `subscribe` ở `main` là ranh giới thực thi của chương trình demo. Trong controller WebFlux, hãy return publisher để framework quản lý subscription và HTTP response.

Ví dụ cố ý không tự viết HTTP framing, DataBuffer hoặc TCP. Các lớp đó thuộc Spring codec và server adapter trong ứng dụng thật.

## 15. Kiểm thử theo đúng ranh giới

Không nên chỉ test service mà bỏ qua decoder/writer khi vấn đề nằm ở HTTP boundary.

- **Unit test service:** kiểm tra domain validation, transaction semantics và xử lý từng event.
- **StepVerifier:** kiểm tra số item, terminal signal, thứ tự, lỗi và cancellation trong publisher.
- **WebTestClient:** kiểm tra route/controller, content type, request decoding, response encoding và status.
- **Integration test qua server thật:** kiểm tra streaming, disconnect, timeout, TLS, proxy và transport behavior.
- **Load test:** kiểm tra payload lớn, burst, client chậm, nhiều stream đồng thời và giới hạn memory.

Ví dụ test publisher với StepVerifier:

```java
StepVerifier.create(service.process(new EventDto("e-1", 10)))
        .expectNextMatches(result ->
                result.id().equals("e-1")
                && result.acceptedAmount() == 10)
        .verifyComplete();
```

Ví dụ kiểm tra WebFlux endpoint bằng WebTestClient (snippet trong test có cấu hình controller):

```java
webTestClient.post()
        .uri("/events")
        .contentType(MediaType.APPLICATION_NDJSON)
        .accept(MediaType.APPLICATION_NDJSON)
        .bodyValue("{\"id\":\"e-1\",\"amount\":10}\n")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_NDJSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("e-1");
```

Snippet này cần `WebTestClient` và controller thực tế; body/response assertion cần khớp với cấu hình test và NDJSON decoder. Với stream nhiều record, kiểm tra response theo từng line hoặc dùng exchange/flux assertion phù hợp thay vì giả định một JSON document duy nhất.

### Test client disconnect

Để kiểm tra cancellation, cần một publisher có thể quan sát `doOnCancel` và client đóng response trước khi hoàn tất. Dùng `StepVerifier.thenCancel()` cho unit-level lifecycle; dùng WebTestClient hoặc client HTTP thật cho integration. Không dựa vào `Thread.sleep` để suy đoán server đã nhận disconnect.

## 16. Observability: đo ở đúng tầng

Một log ở controller không cho biết đầy đủ tình trạng network hoặc codec. Chia metric theo ranh giới:

| Tầng | Nên quan sát |
|---|---|
| Server/transport | Active connections, HTTP/2 streams, bytes received/sent, response time, transport errors |
| Codec | Decode/encode failures, body size, aggregate limit errors, serialization latency |
| Application | Items decoded, validation failures, business processing latency, success/failure |
| Queue/concurrency | Pending items/bytes, active inner operations, pool saturation, overflow/drop |
| Lifecycle | Cancellation, timeout, completion, client disconnect, resource cleanup |
| Client/proxy | Read latency, retry/reconnect, buffered bytes nếu có, stream lag |

Reactor Netty cung cấp Micrometer metrics. Ví dụ tên đầy đủ gồm `reactor.netty.http.server.connections.active`, `reactor.netty.http.server.data.received`, `reactor.netty.http.server.data.sent`, `reactor.netty.http.server.response.time` và các metric `reactor.netty.bytebuf.allocator.used.direct.memory`. Tên/khả dụng tùy phiên bản và cấu hình.

**Bytes sent không phải business acknowledgment.** Nó đo dữ liệu tại điểm quan sát server/transport, không chứng minh client đã parse, render, lưu hoặc commit nghiệp vụ. Nếu cần xác nhận nghiệp vụ, thiết kế acknowledgment/event ID ở tầng ứng dụng.

## 17. Những lỗi phổ biến khi nhầm ranh giới

1. **Coi một TCP packet là một JSON object.** Packet segmentation không phải message framing; hãy để codec parse content.
2. **Coi một DataBuffer là một record.** Buffer có thể chứa nửa record hoặc nhiều record.
3. **Đưa logic domain vào decoder.** Codec nên giải mã representation; validation và business rule thuộc application/domain layer.
4. **Dùng `collectList()` cho body stream lớn.** Nó gom toàn bộ item, có thể tăng memory theo kích thước request.
5. **Dùng `Mono<List<T>>` khi cần streaming.** Kiểu collection buộc gom dữ liệu trước khi xử lý theo cách đó.
6. **Giả định mỗi `onNext` tạo một lần flush hoặc một packet.** Writer/adapter/transport có buffering và framing riêng.
7. **Cho rằng HTTP 200 bảo đảm mọi event stream đã xử lý thành công.** Với streaming, response có thể đã commit trước lỗi xảy ra ở item sau.
8. **Bỏ qua lỗi deserialize.** JSON malformed xảy ra trước hoặc tại codec boundary; không phải lỗi domain validation.
9. **Gộp lỗi DB thành empty.** Empty, invalid representation và dependency failure có ý nghĩa khác nhau.
10. **Gọi `block()` hoặc nested `subscribe()` trong controller.** Điều này phá ownership, backpressure, error và cancellation của request.
11. **Giới hạn số item nhưng quên kích thước byte.** Một item có thể rất lớn; giới hạn payload và aggregate bytes riêng.
12. **Tự quản lý DataBuffer mà không release.** Pooled buffer có thể rò direct memory nếu ownership không rõ.
13. **Release buffer do framework đang sở hữu.** Có thể gây double release/use-after-release; chỉ release khi code của bạn chịu trách nhiệm.
14. **Retry lỗi sau khi response đã commit mà không xét semantics.** Client có thể nhận một phần stream; retry cần event ID/idempotency và protocol resume.
15. **Coi cancellation là rollback.** Hủy publisher không tự đảo ngược transaction hoặc side effect đã gửi ra hệ thống ngoài.
16. **Log toàn bộ request body trong WebFilter bằng subscription riêng.** Có thể consume body trước controller, tạo buffer copy lớn và lộ dữ liệu nhạy cảm.
17. **Dùng một limit codec như memory cap tổng.** Netty direct memory, operator queues, service objects và proxy buffers còn nằm ngoài giới hạn đó.
18. **Dùng flatMap không giới hạn cho mọi event.** Có thể tạo quá nhiều inner calls, connection và memory; chọn concurrency theo năng lực downstream.

## 18. Checklist thiết kế và review

Trước khi đưa endpoint WebFlux vào production, hãy kiểm tra:

- **Transport:** server adapter và protocol nào đang chạy? Có proxy/load balancer ở giữa không?
- **Framing:** body dùng JSON, NDJSON, SSE, multipart hay binary protocol? Ranh giới record được định nghĩa ở đâu?
- **Codec:** reader/writer nào được chọn? Có custom codec không? Có giới hạn aggregate body và record size không?
- **Memory ownership:** có thao tác trực tiếp `DataBuffer`/`ByteBuf`? Ai retain/release và xử lý cancel/discard?
- **Request model:** body là Mono, Flux, list hay raw buffer? Có vô tình aggregate toàn bộ?
- **Business semantics:** validate ở đâu? Transaction per request hay per event? Idempotency key nào?
- **Ordering/concurrency:** dùng concatMap, flatMap hay flatMapSequential? Concurrency và prefetch bao nhiêu?
- **Backpressure:** nguồn có hỗ trợ demand không? Queue nào có giới hạn? Overflow xử lý ra sao?
- **Response format:** content type có hỗ trợ consumer streaming không? Client có thể parse từng event không?
- **Error policy:** lỗi codec, validation, domain, persistence và transport được phân biệt thế nào?
- **Commit boundary:** lỗi xảy ra trước hay sau khi response bắt đầu gửi? Client có cơ chế resume không?
- **Cancellation:** disconnect có hủy upstream và cleanup resource? Có side effect cần sống độc lập không?
- **Security:** giới hạn body, rate, authorization, sensitive logging và tenant isolation đã được xử lý?
- **Observability:** metric có phân biệt bytes, DTO, business event và acknowledgment không?
- **Testing:** đã test malformed body, payload lớn, client chậm, disconnect, nhiều event, lỗi giữa stream và proxy thực tế?

**Ghi nhớ:** WebFlux biến I/O HTTP thành publisher, nhưng không xóa bỏ các ranh giới giữa transport, codec và nghiệp vụ. **Byte được nhận không phải DTO; DTO được giải mã không phải business event đã commit; response được ghi không phải client đã xử lý.** Hãy để server adapter và codec quản lý framing/serialization, giữ business logic trong publisher/service có thể compose, và kiểm soát riêng payload, buffer, concurrency, lỗi, cancellation cùng resource ownership.

## Tài liệu tham khảo

- Spring Framework — [Reactive Core: HttpHandler, WebHandler, codecs và DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [Data Buffers and Codecs: ownership, release và join](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [WebFlux configuration và HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework — [WebClient và codec configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Project Reactor — [Reactive Streams backpressure và request reshaping](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Reactor Netty — [HTTP Server: request receive, response send và metrics](https://projectreactor.io/docs/netty/release/reference/http-server.html).
