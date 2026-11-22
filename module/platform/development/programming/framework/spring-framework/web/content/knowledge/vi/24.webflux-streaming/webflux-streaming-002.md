# JSON theo luồng, NDJSON và lựa chọn media type trong Spring WebFlux

## 1. Bối cảnh: một Flux không tự quyết định định dạng HTTP

Một controller Spring WebFlux có thể trả `Flux<Event>` để biểu diễn nhiều dữ liệu xuất hiện qua thời gian. Nhưng **`Flux<T>` là kiểu Publisher của ứng dụng, không phải một định dạng trên dây (wire format)**. Cùng một `Flux<Event>` có thể được HTTP encoder viết thành:

- **Một JSON array hoàn chỉnh** với `Content-Type: application/json`, ví dụ `[{"id":1},{"id":2}]`.
- **Các JSON values tách nhau bằng newline** với `Content-Type: application/x-ndjson`, ví dụ một object trên một dòng.
- **Server-Sent Events (SSE)** với `Content-Type: text/event-stream`, mỗi event có framing `id:`, `event:`, `data:`.
- Một dạng binary/streaming khác khi dùng codec, media type và contract tương ứng.

Sự khác biệt tác động trực tiếp tới thời điểm client thấy dữ liệu, memory, backpressure, caching, browser support, status/error handling và khả năng resume sau khi kết nối ngắt.

Ví dụ, một report trả dữ liệu sau 10 giây và gồm 10.000 records:

- Nếu client chỉ muốn tải một document JSON chuẩn và cần parse toàn bộ kết quả: `application/json` thường phù hợp.
- Nếu client muốn xử lý từng bản ghi ngay khi server phát ra, và cả hai bên hỗ trợ line-oriented parsing: **NDJSON** phù hợp hơn.
- Nếu browser muốn theo dõi các cập nhật dạng thông báo một chiều qua kết nối mở lâu: **SSE** thường dễ dùng hơn NDJSON với `EventSource`.
- Nếu yêu cầu là byte-stream/file, hoặc một protocol có framing khác, không nên đặt `application/json` chỉ vì dữ liệu ở source ban đầu là Java object.

**Phạm vi:** Spring **WebFlux** (không phải Servlet MVC), Java **17**, Spring Boot **3.3.5**, Spring Framework **6.1.x**, Reactor `Flux`/`Mono`, Jackson JSON codec, annotated controllers, WebTestClient. Chủ đề chính là **JSON streaming, NDJSON và lựa chọn media type**; những phần về bảo mật, cancel và backpressure chỉ giải thích các ranh giới cần thiết để triển khai đúng.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt JSON document, JSON array, NDJSON, JSON Text Sequences và SSE.
2. Biết vì sao `Flux<T>` với `application/json` và `application/x-ndjson` được encode khác nhau.
3. Thiết kế `produces`/`consumes`, `Accept`/`Content-Type` và test 406/415 đúng.
4. Viết endpoint trả `ResponseEntity<Flux<DTO>>` theo JSON array hoặc NDJSON.
5. Nhận `@RequestBody Flux<DTO>` dạng NDJSON, giới hạn kích thước và validate trước side effects.
6. Dùng `WebTestClient` để kiểm tra nội dung JSON array, line framing và reactive item decoding.
7. Hiểu sự khác biệt giữa flush của encoder và việc một client nhận từng network chunk.
8. Thiết kế status/headers và error policy khi HTTP response có thể đã commit một phần.
9. Lựa chọn SSE, NDJSON hoặc regular JSON theo consumer, kết nối và yêu cầu nghiệp vụ.
10. Phát hiện lỗi blocking event-loop, buffer vô hạn, request-body double-read, stream cancellation và bảo mật dữ liệu.

## 2. So sánh ba định dạng cần nhớ trước tiên

Giả sử dữ liệu Java gồm hai events:

```java
new Event(1L, "order", "created");
new Event(2L, "order", "paid");
```

Đây là snippet dùng record `Event` sẽ được khai báo trong project đầy đủ.

### 2.1. Một JSON array: application/json

HTTP body:

```json
[
  {"id":1,"type":"order","message":"created"},
  {"id":2,"type":"order","message":"paid"}
]
```

Đây là **một JSON document hợp lệ** có root là array. Dù Jackson có thể xuất tối giản không có khoảng trắng, array vẫn có opening bracket, separators giữa elements, closing bracket.

**Điểm mạnh:** hầu hết client JSON parsers hiểu được; thuận tiện cho list nhỏ/response hoàn tất, cache, schema và API tooling. **Giới hạn:** một JSON document chưa hoàn chỉnh cho tới khi có đủ closing delimiters; encoder WebFlux thường gom các phần tử của Flux để serialize thành một JSON array khi dùng media type không streaming. Không nên giả định client nhận được bản ghi đầu ngay khi upstream Flux phát bản ghi đầu.

### 2.2. NDJSON: application/x-ndjson

HTTP body:

```text
{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
```

Mỗi dòng là **một JSON text độc lập**. Các record cách nhau bằng `\n` (newline); thường có newline cuối. Đây **không phải** một JSON array và toàn bộ chuỗi nối các objects không phải một single JSON document mà `JSON.parse(wholeBody)` trực tiếp chấp nhận.

**Điểm mạnh:** line-oriented parser có thể xử lý record ngay sau khi nhận đủ newline; phù hợp export lớn, append-only logs/events, ETL, pipeline streaming. **Giới hạn:** schema/ordering/recovery do ứng dụng quyết định; parser cần xử lý dữ liệu đến từng phần, không được mặc định mỗi TCP read hoặc HTTP chunk tương ứng một dòng.

NDJSON là dạng thường được gọi là *Newline Delimited JSON* hoặc *JSON Lines*. MIME type phổ biến trong Spring WebFlux hiện đại là **`application/x-ndjson`**. Với hệ thống cũ có thể gặp `application/stream+json`; không coi chúng tự động interchangeable nếu chưa xác minh codec/version/client support.

### 2.3. SSE: text/event-stream

HTTP body:

```text
id: 1
event: order
data: {"id":1,"type":"order","message":"created"}

id: 2
event: order
data: {"id":2,"type":"order","message":"paid"}

```

SSE là **protocol framing khác**: blank line kết thúc event, `data:` chứa payload, `id:` hỗ trợ reconnection thông qua `Last-Event-ID` và `event:` đặt tên event. Nó có thể mang JSON trong data, nhưng **không phải NDJSON**. Trên browser, `EventSource` được thiết kế để tiêu thụ `text/event-stream`, không phải `application/x-ndjson`.

Một EventSource browser là **một chiều server → client**. Nếu cần client gửi liên tục hai chiều, thường cân nhắc WebSocket hoặc một protocol phù hợp khác.

### Bảng tóm tắt

| Thuộc tính | application/json | application/x-ndjson | text/event-stream |
| --- | --- | --- | --- |
| Framing | JSON document, thường array | Một JSON text mỗi dòng | SSE fields + blank line |
| Mức độ dễ parse | Rất phổ biến | Cần NDJSON parser | Browser EventSource hoặc SSE parser |
| Nhiều item theo thời gian | Có thể từ Flux nhưng encoder thường gom trước khi output | Có, flush từng item theo streaming codec | Có, flush theo event |
| Parse khi chưa có toàn bộ body | Không với JSON.parse toàn body | Có khi đủ newline của từng record | Có khi đủ event boundary |
| Client browser built-in | fetch + response.json() | fetch streaming + TextDecoder/parser | EventSource |
| ID/reconnect semantics | Tự thiết kế | Tự thiết kế | `id`, `Last-Event-ID`, auto reconnect của EventSource |
| Response có thể vô hạn | Không lý tưởng với JSON array | Có thể, khi đặt limits/protocol | Có thể, cần heartbeat/cancel |
| Typical use | CRUD/list nhỏ | Logs, exports, batch records | Live notifications, progress |

## 3. Media type là một phần của hợp đồng, không phải nhãn trang trí

WebFlux dùng `MediaType` để lựa chọn codec và hành vi ghi response. Hai quyết định thường độc lập:

- `Content-Type`: media type của **body HTTP đang được gửi**.
- `Accept`: media types mà **client muốn nhận** từ response.

Ví dụ client yêu cầu NDJSON:

```http
GET /api/streams/ndjson HTTP/1.1
Host: localhost:8080
Accept: application/x-ndjson
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
```

Với POST NDJSON, client gửi:

```http
POST /api/streams/ingest HTTP/1.1
Host: localhost:8080
Content-Type: application/x-ndjson
Accept: application/json

{"message":"first"}
{"message":"second"}
```

Ở đây **request body** là NDJSON còn **response body** có thể là một JSON object tóm tắt. Đừng yêu cầu Accept NDJSON chỉ vì Content-Type NDJSON; hai chiều là hai contract khác nhau.

### Các constants nên dùng

```java
MediaType.APPLICATION_JSON
MediaType.APPLICATION_JSON_VALUE
MediaType.APPLICATION_NDJSON
MediaType.APPLICATION_NDJSON_VALUE
MediaType.TEXT_EVENT_STREAM
MediaType.TEXT_EVENT_STREAM_VALUE
```

Đây là Spring `org.springframework.http.MediaType` constants, không phải strings tự định nghĩa trong project. Dùng chúng trong `@GetMapping(produces=...)`, `@PostMapping(consumes=...)`, `ResponseEntity.contentType(...)` và WebTestClient.

### Các media type dễ nhầm

| Media type | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| `application/json` | Một JSON representation/document | Không đồng nghĩa line-oriented stream |
| `application/x-ndjson` | NDJSON, một JSON text trên mỗi dòng | Dùng khi consumer hiểu NDJSON |
| `text/event-stream` | Server-Sent Events | Có fields/event boundaries, không phải NDJSON |
| `application/json-seq` | JSON Text Sequences theo RFC 7464 | Dùng RS (ASCII 0x1E) framing; **không phải NDJSON** |
| `application/stream+json` | Tên cũ thường thấy trong một số Spring integrations | Tùy version/codec; ưu tiên NDJSON khi hợp đồng cho phép |
| `application/octet-stream` | Bytes tùy ý | Không mang semantics JSON/object stream |
| `text/plain` | Văn bản thuần | Có thể chứa chuỗi JSON nhìn giống JSON nhưng không tự có JSON codec contract |

**Không chọn `application/json-seq` thay NDJSON chỉ vì đều "nhiều JSON".** RFC 7464 sử dụng record separator, còn NDJSON dựa trên newline. Parsers phải thống nhất framing.

## 4. Spring WebFlux encode Flux ra HTTP như thế nào?

Request đi qua `DispatcherHandler`/result handling và các `HttpMessageWriter`. Với JSON, `Jackson2JsonEncoder` và HTTP codecs của Spring làm việc dựa trên type, media type và reactive publisher.

Về cơ chế:

```text
Flux<Event> của controller
      |
      v
WebFlux HandlerResultHandler
      |
      v
HttpMessageWriter chọn encoder theo element type + media type
      |
      +--> application/json
      |      thường gom các elements trước khi encode
      |      tạo một JSON array document
      |
      +--> application/x-ndjson
             encode từng Event thành JSON text
             thêm newline separator
             flush theo từng value với streaming media type
      |
      v
ServerHttpResponse.writeWith / writeAndFlushWith
      |
      v
Reactive HTTP adapter + network buffers + proxy
```

### Vì sao chọn NDJSON lại có thể giảm latency "time-to-first-item"?

Với `application/json`, encoder thường cần biết collection để tạo một JSON array hoàn chỉnh. Với streaming media type, encoder có thể encode, write và **flush từng value**, nên không cần đợi source hoàn tất để đưa record đầu xuống output pipeline.

**Tuy nhiên flush không có nghĩa "đã tới browser ngay lập tức"**:
- Reactor Netty có event loops và TCP buffers.
- Kernel có packetization và network latency.
- Reverse proxy/API gateway có thể bật buffering/compression.
- HTTP/2 flow control hoặc client đọc chậm ảnh hưởng nhịp.
- Client decoder có thể đợi đủ newline/frame.
- TLS transport và network chunk boundaries không trùng record boundaries.

Vì vậy đo cả **server emission time**, **first byte time** và **client observed first record**, thay vì đo chỉ tổng latency.

### Flux<T> không bắt buộc là streaming response

```java
@GetMapping(path = "/json",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Event> json() {
    return source.events();
}
```

Không có gì trong chữ ký `Flux<Event>` đảm bảo mỗi Event được flush riêng. Nếu cần contract NDJSON, khai báo `produces=APPLICATION_NDJSON_VALUE` và test response Content-Type/wire format.

### Không dùng Flux<String> để "tự động tạo JSON array"

Với Jackson codecs, `String` có handling riêng, thường được coi là nội dung văn bản để CharSequence encoder ghi, không phải DTO JSON cần serialize thành JSON string elements. Vì vậy:

```java
// Để trả JSON array strings chính xác, dùng một value List:
@GetMapping(path = "/labels",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<List<String>> labels() {
    return Mono.just(List.of("first", "second"));
}
```

Snippet này phụ thuộc imports `GetMapping`, `Mono`, `List`, `MediaType`. Nó rõ ràng về JSON array `["first","second"]`. Đừng giả định `Flux.just("first","second")` được serialize thành cùng JSON array dưới mọi codec configuration.

## 5. Ba kiểu endpoint phổ biến

### 5.1. JSON list hữu hạn

```java
@GetMapping(path = "/list",
            produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Flux<Event>> list() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(source.events());
}
```

Status và Content-Type biết ngay. Body là Flux, nhưng vì media type là JSON thông thường nên HTTP result dự kiến là **một array JSON** sau quá trình encoding. Phù hợp khi danh sách hữu hạn và không quá lớn.

### 5.2. NDJSON hữu hạn

```java
@GetMapping(path = "/ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public ResponseEntity<Flux<Event>> ndjson() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(source.eventsWithDelay());
}
```

Nguồn phát theo thời gian; encoder NDJSON ghi từng object và newline. Client có thể xử lý từng record độc lập. Status 200 và headers được chọn trước khi body phát. **Nếu event thứ ba fail sau hai dòng đã flush, status khó có thể đổi thành 500 nữa.**

### 5.3. NDJSON dài hạn hoặc vô hạn

```java
@GetMapping(path = "/live",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Event> live() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(n -> new Event(
                    n + 100, "heartbeat", "tick-" + n));
}
```

Đây là snippet với record `Event` có ba fields được định nghĩa bên dưới. `Flux.interval` dùng Reactor scheduler; không tạo một Java thread ngủ riêng trên mỗi request.

**Không** gọi `collectList()` trên Flux vô hạn, vì Publisher không complete nên list không bao giờ phát và có thể dùng memory ngày càng lớn. Với live stream cần:
- Periodic heartbeat/đặc tả idle behavior.
- Idle timeouts phù hợp ở server/proxy/client.
- Client cancellation cleanup.
- Event retention/replay policy nếu cần resume.
- Backpressure/sampling/drop policy nếu producer nhanh hơn consumer.
- Hạn chế số concurrent connections.

## 6. SSE khác NDJSON ngay cả khi data là JSON

WebFlux hỗ trợ `ServerSentEvent<T>` thuộc `org.springframework.http.codec`:

```java
@GetMapping(path = "/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Event>> sse() {
    return source.eventsWithDelay()
            .map(value -> ServerSentEvent.<Event>builder()
                    .id(Long.toString(value.id()))
                    .event("change")
                    .data(value)
                    .build());
}
```

Đây là snippet với `source` đã có. Server-Sent Events cho browser `EventSource` metadata hữu ích như `id` và `event`, hỗ trợ reconnect. NDJSON thuần **không** có protocol chuẩn tương đương `Last-Event-ID`; muốn resume cần contract dựa trên offset/sequence/checkpoint riêng.

### SSE heartbeat

Trong stream dài hạn, nếu không phát gì quá lâu, broken connections có thể chỉ bị phát hiện chậm; đồng thời reverse proxy có thể idle-timeout. SSE có thể phát comment-only heartbeat:

```text
: keep-alive

```

Khi viết WebFlux SSE phức tạp, có thể kết hợp event publisher với một ticker phát comment-only `ServerSentEvent`, nhưng cần tránh gửi heartbeat vào cùng stream khi business contract không mong đợi. Client parser phải xử lý comments như SSE protocol định nghĩa.

### Đừng chọn SSE cho mọi streaming API

SSE tiện cho browser notification nhưng thường không phù hợp khi:
- Client cần POST một stream dữ liệu lên server.
- Cần binary data.
- Cần giao thức hai chiều với command/data flows.
- Client cần một NDJSON export được xử lý bằng Unix line tools.

Ngược lại, NDJSON thường phù hợp cho server-to-server ETL/log exports mà không cần EventSource behavior.

## 7. Chọn media type dựa trên nhu cầu của client

| Nhu cầu | Nên bắt đầu bằng | Vì sao |
| --- | --- | --- |
| Một DTO | `application/json` + `Mono<DTO>` | Một JSON object |
| Một list nhỏ (tối đa vài trăm phần tử theo policy) | `application/json` + list/Flux hữu hạn | Client parsing đơn giản |
| Export lớn cần xử lý từng record | `application/x-ndjson` + `Flux<DTO>` | Streaming per-line |
| Browser dashboard nhận thông báo | `text/event-stream` + SSE events | EventSource, id/reconnect |
| Client POST nhiều records đến dần | NDJSON request + `@RequestBody Flux<DTO>` | Producer/consumer stream |
| Một batch transactional cần validate trước | `application/json` array + `Mono<List<DTO>>`/wrapper | Dễ atomic validation/response |
| File raw bytes | `application/octet-stream` hoặc file-specific type | Không sai framing |
| Protocol JSON sequence theo RFC 7464 | `application/json-seq` | RS framing theo spec, không phải NDJSON |
| GraphQL/gRPC/WebSocket | Protocol được thiết kế riêng | Không trá hình thành NDJSON |
| Client chỉ gọi `response.json()` | `application/json` | NDJSON toàn body không phải JSON document |

**Câu hỏi trước khi thiết kế:** client có đọc incremental không; nếu server trả hàng nghìn items, client có đủ bộ nhớ không; có cần per-record ack/retry không; có cần thứ tự; có cần resume và event IDs; kết nối có proxy buffering không; status phải biết khi nào; error xảy ra nửa chừng sẽ biểu diễn ra sao?

## 8. Content negotiation: Accept, Content-Type, produces, consumes

`@GetMapping(produces=...)` ràng buộc response representation theo Accept; `@PostMapping(consumes=...)` ràng buộc media type request body theo Content-Type.

```java
@GetMapping(path = "/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Event> ndjson() {
    return source.events();
}

@PostMapping(path = "/ingest",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<IngestReceipt> ingest(
        @RequestBody Flux<NewEvent> body) {
    return service.accept(body);
}
```

Đây là snippets với classes/service của ví dụ. Đừng tráo:
- `Accept: application/x-ndjson` nghĩa client muốn **nhận** NDJSON.
- `Content-Type: application/x-ndjson` nghĩa client **đang gửi** NDJSON.
- `produces` mô tả response format.
- `consumes` mô tả request-body format.

Ví dụ:
- GET NDJSON endpoint với `Accept: text/plain` có thể nhận **406 Not Acceptable**.
- POST tới NDJSON-only endpoint với `Content-Type: application/json` có thể nhận **415 Unsupported Media Type**.
- JSON malformed hoặc NDJSON line sai cú pháp thường thành **400 Bad Request**, tùy error handling.
- Với browser fetch, nếu có credentials/cross-origin, còn có CORS preflight policy.

HTTP clients có thể gửi `Accept: */*`. Khi có nhiều mapping cùng path phân biệt bằng media type, phải kiểm tra content negotiation/ordering để tránh một client tình cờ nhận format không mong đợi. Với API contract lâu dài, explicit paths hoặc headers có thể dễ quản lý hơn implicit negotiation khi streaming vs non-streaming khác semantics mạnh.

## 9. Đọc request body NDJSON bằng @RequestBody Flux<T>

Với NDJSON input:

```http
POST /api/streams/ingest HTTP/1.1
Content-Type: application/x-ndjson

{"message":"first"}
{"message":"second"}
```

Controller có thể khai báo:

```java
@PostMapping(path = "/ingest",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Receipt> ingest(
        @RequestBody Flux<NewEvent> incoming) {

    return incoming
            .map(this::validate)
            .collectList()
            .map(events -> new Receipt(events.size()));
}
```

Đây là **snippet** có `Receipt` và `validate` giả định. `HttpMessageReader`/Jackson decoder tạo ra `NewEvent` theo framing NDJSON. Nhưng `@RequestBody Flux<T>` **không tự bảo đảm**:
- Dữ liệu được giới hạn records/bytes.
- Tất cả field constraints được validate như mong muốn.
- Tất cả events sẽ được persisted atomically.
- Client disconnect sẽ rollback side effects đã hoàn thành.
- Mỗi raw network packet chứa đúng một JSON object.

### Lựa chọn: xử lý từng record hay gom batch?

**Xử lý từng record:**

```java
return incoming
        .concatMap(eventStore::save)
        .count();
```

Snippet với `eventStore.save` trả `Mono<?>`. `concatMap` bảo toàn processing order theo thứ tự đầu vào và giới hạn concurrency theo cách tuần tự. Nhưng nếu record thứ 5 lỗi, 4 record đầu có thể đã lưu: **không atomic**.

**Gom batch có giới hạn:**

```java
return incoming.take(6)
        .collectList()
        .flatMap(list -> {
            if (list.size() > 5) {
                return Mono.error(new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "Too many records"));
            }
            return validateThenSave(list);
        });
```

Snippet với `validateThenSave` giả định. Nếu chấp nhận tối đa 5 records, cần đọc tối đa **6** để phát hiện vượt hạn; `take(5)` rồi tự ý chấp nhận 5 đầu sẽ âm thầm làm mất phần dư. Sau đó validate *toàn bộ* trước khi side effect nếu contract đòi tính toàn vẹn.

Giới hạn số records **không đủ** bảo vệ server trước một JSON object khổng lồ. Cần thêm byte limits, JSON nesting limits, timeouts và business quotas.

## 10. Lỗi giữa stream: HTTP status đã commit thì sao?

Giả sử server đã gửi:

```text
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
```

Sau đó source phát `Mono.error(new IOException(...))` trước record thứ 3. Trong HTTP, status và headers thường **đã được commit**. Framework không thể đảm bảo biến stream trước đó thành một response mới `500 application/problem+json`; client có thể chỉ thấy kết nối đóng đột ngột, body thiếu hoặc protocol-level error.

Vì vậy với NDJSON export:
- Document rõ rằng stream có thể incomplete.
- Dùng stable event IDs/sequence để client phát hiện missing records.
- Nếu cần resume, thiết kế checkpoint/`?afterId=...` và retention policy.
- Nếu cần toàn-or-nothing, đừng bắt đầu response trước khi validate/compute xong; chọn JSON array hoặc trả job ID để tải file đã chuẩn bị.
- Logging/metrics ghi nhận `onError` và `CANCEL` khác với HTTP 5xx.
- Không retry một stream nhập dữ liệu có side effects nếu thiếu idempotency.

### Những thứ không nên làm

```java
// PHẢN VÍ DỤ: mọi lỗi đều được che bằng Flux.empty()
return source.eventsWithDelay()
        .onErrorResume(error -> Flux.empty());
```

Nếu server đã gửi 2/3 records mà operator chuyển lỗi thành complete bình thường, client có thể lầm tưởng export đã hoàn tất. Chỉ dùng fallback nếu protocol/business contract cho phép, phải có dấu hiệu completeness/checksum/end marker thích hợp.

### Thiết kế sentinel kết thúc khi bắt buộc

Một số protocol xây event wrapper:

```json
{"type":"row","data":{"id":1}}
{"type":"row","data":{"id":2}}
{"type":"end","count":2}
```

Đây **không phải NDJSON mặc định của Spring**, mà là một application-specific contract. Client phải chỉ coi stream đầy đủ khi thấy `type=end` và kiểm tra count/checksum; nếu socket đóng trước marker thì retry/resume. Không tự gửi marker giả khi upstream fail.

## 11. Reactive backpressure và quan hệ với HTTP transport

Reactive Streams có `request(n)`/demand và cancellation. Khi HTTP response consumer chậm, pipeline có thể giảm demand từ upstream nếu codecs/server/runtime hỗ trợ đúng. Nhưng:
- `Flux.create` đẩy events từ callback không giới hạn có thể tích tụ memory.
- `onBackpressureBuffer()` không giới hạn có thể OOM.
- `collectList()` trên stream vô hạn không complete và tăng memory.
- `flatMap` với concurrency cao có thể làm đổi ordering hoặc quá tải downstream.
- `publishOn`/`subscribeOn` chỉ chuyển scheduler; không làm đồng bộ JDBC trở thành non-blocking.
- File reads/DB drivers có blocking APIs nếu application sử dụng những APIs đó.

### Blocking example

```java
// Không nên làm trong WebFlux event-loop path:
return source.events()
        .map(event -> blockingJdbcRepository.save(event));
```

Đây là snippet với repository giả định; JDBC call vẫn chiếm thread đang thực thi. Nếu phải dùng blocking driver trong thời gian chuyển đổi:

```java
return source.events()
        .concatMap(event ->
                Mono.fromCallable(
                        () -> blockingJdbcRepository.save(event))
                    .subscribeOn(Schedulers.boundedElastic()));
```

Cách này offload sang bounded workers, **không biến JDBC non-blocking**. Đặt connection pool, timeouts, concurrency và cancellation strategy. Với pipeline cần non-blocking end-to-end, dùng client/driver reactive phù hợp.

### Order và consistency

Với events theo sequence, `concatMap` bảo toàn processing order; `flatMap` mặc định có thể hoàn thành out-of-order. Nếu stream phản ánh một aggregate transaction sequence, contract phải nêu rõ ordering. HTTP/TCP giữ thứ tự bytes trên một connection, nhưng upstream merge/flatMap có thể làm dữ liệu **được tạo** sai thứ tự trước khi encode.

## 12. Bảo mật và vận hành stream

### Authentication/authorization

Một endpoint export NDJSON có thể trả hàng nghìn records nhạy cảm. Cần:
- Spring Security reactive authentication/authorization trước khi bắt đầu stream.
- Per-resource/tenant access checks, tránh IDOR.
- Không lấy `X-User` hoặc `X-Role` do client tự gửi làm identity.
- Đảm bảo quyền không bị bỏ qua bởi một custom WebFilter tạo response stream.
- Nếu stream dài và token hết hạn/ACL thay đổi, có business policy rõ cho việc refresh/terminate stream.

### Privacy

Một record NDJSON vẫn có thể chứa PII/secrets; newline delimiter không tự mask. Đặt `Cache-Control: no-store` hoặc cache policy thích hợp nếu dữ liệu cá nhân, tránh shared CDN cache. Không log nguyên response body hoặc `Authorization` header. Nếu gửi NDJSON qua file export, kiểm soát thời gian tồn tại, signed URL TTL và audit access.

### Injection và parser safety

NDJSON là JSON syntax, không tự chống XSS hoặc injection ở consumer. Nếu consumer chèn `message` vào DOM bằng `innerHTML` thì vẫn có XSS risk; dùng textContent/escaping. Nếu dữ liệu được đưa vào SQL/command downstream, dùng parameterized statements/escaping đúng nơi. Parser cần validate schema, max line length, max JSON depth, Unicode handling và duplicate keys policy.

### DoS/resilience

- Bounded concurrent streams/users.
- Request/input limits theo byte và record count.
- Idle/total duration limits theo endpoint.
- Client disconnect/cancellation cleanup; không giữ publisher/subscription vô hạn.
- Retry/backoff/resume limits để tránh thundering herd.
- Reverse proxy buffering/timeouts phù hợp; không tắt mọi protections để "stream nhanh".
- Metrics: bytes/second, emitted records, dropped items, active connections, p95 first-record latency, error/cancel count.

## 13. Dự án Spring Boot 3.3.5 hoàn chỉnh

Demo gồm các endpoints:

| Endpoint | Method | Request Content-Type | Response Content-Type | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `/api/streams/json` | GET | Không có body | `application/json` | Flux 3 items → JSON array |
| `/api/streams/ndjson` | GET | Không có body | `application/x-ndjson` | Flux 3 items, phát cách nhau ngắn |
| `/api/streams/sse` | GET | Không có body | `text/event-stream` | SSE có ID và event name |
| `/api/streams/live` | GET | Không có body | `application/x-ndjson` | Stream vô hạn, client chủ động cancel |
| `/api/streams/single` | GET | Không có body | `application/json` | Một JSON object |
| `/api/streams/strings` | GET | Không có body | `application/json` | JSON array strings chính xác |
| `/api/streams/ingest` | POST | `application/x-ndjson` | `application/json` | Đọc 1–5 records rồi trả summary, validate explicit |

Không có database. Dữ liệu dùng `List.of` bất biến; `Flux.delayElements`/`Flux.interval` minh họa publisher phát theo thời gian. Không có blocking I/O hay code tự gọi `subscribe()`. Request ingest **không lưu dữ liệu**; chỉ validate và trả summary để tập trung vào codec/framing.

### 13.1. Cây project

```text
webflux-ndjson-demo/
├── pom.xml
└── src/
    ├── main/java/example/streaming/
    │   ├── StreamingApplication.java
    │   ├── StreamEvent.java
    │   ├── IncomingEvent.java
    │   ├── IngestReceipt.java
    │   ├── EventSource.java
    │   └── StreamController.java
    └── test/java/example/streaming/
        └── StreamControllerTest.java
```

### 13.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-ndjson-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

Chỉ thêm `spring-boot-starter-webflux`, **không thêm `spring-boot-starter-web`**, để Spring Boot mặc định chọn reactive web application type. Jackson JSON support đến từ WebFlux starter. Validation starter cung cấp Jakarta Bean Validation `Validator`.

### 13.3. Application class

**`src/main/java/example/streaming/StreamingApplication.java`**

```java
package example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
```

### 13.4. DTO records

**`src/main/java/example/streaming/StreamEvent.java`**

```java
package example.streaming;

public record StreamEvent(
        long id,
        String type,
        String message) {}
```

**`src/main/java/example/streaming/IncomingEvent.java`**

```java
package example.streaming;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record IncomingEvent(
        @NotBlank @Size(max = 80) String message) {}
```

**`src/main/java/example/streaming/IngestReceipt.java`**

```java
package example.streaming;

import java.util.List;

public record IngestReceipt(
        int accepted,
        List<String> messages) {}
```

Java 17 records là DTO bất biến và Jackson có hỗ trợ JSON record serialization/deserialization trong Boot 3.3.5. `@NotBlank` và `@Size` chỉ là validation metadata; demo sẽ **gọi `Validator.validate(...)` chủ động**, thay vì giả định body Flux nhất định đã được kiểm tra theo mọi custom validation policy.

### 13.5. EventSource: nguồn dữ liệu và nhịp phát

**`src/main/java/example/streaming/EventSource.java`**

```java
package example.streaming;

import java.time.Duration;
import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class EventSource {

    private final List<StreamEvent> seed = List.of(
            new StreamEvent(1, "order", "created"),
            new StreamEvent(2, "order", "paid"),
            new StreamEvent(3, "order", "shipped"));

    public Flux<StreamEvent> snapshot() {
        return Flux.fromIterable(seed);
    }

    public Mono<StreamEvent> first() {
        return snapshot().next();
    }

    public Flux<StreamEvent> delayed() {
        return snapshot().delayElements(Duration.ofMillis(50));
    }

    public Flux<StreamEvent> live() {
        return Flux.interval(Duration.ofMillis(150))
                .map(n -> new StreamEvent(
                        n + 100, "heartbeat", "tick-" + n));
    }
}
```

`snapshot()` tạo Flux từ List hữu hạn; `delayed()` phát 3 items cách nhau một khoảng ngắn bằng Reactor scheduler, không `Thread.sleep`; `live()` tạo stream vô hạn để test cancellation. Không giả định thời gian 50 ms/150 ms là deadline cứng: scheduler và OS có jitter. Trong production, nguồn có thể là change stream, message broker hoặc R2DBC; backpressure/cancellation phải được xử lý tại nguồn thật.

### 13.6. Controller: JSON, NDJSON, SSE và ingest

**`src/main/java/example/streaming/StreamController.java`**

```java
package example.streaming;

import java.util.List;

import jakarta.validation.Validator;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/streams")
public class StreamController {

    private final EventSource source;
    private final Validator validator;

    public StreamController(
            EventSource source,
            Validator validator) {
        this.source = source;
        this.validator = validator;
    }

    @GetMapping(
            path = "/json",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Flux<StreamEvent>> json() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(source.snapshot());
    }

    @GetMapping(
            path = "/ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public ResponseEntity<Flux<StreamEvent>> ndjson() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .cacheControl(CacheControl.noStore())
                .body(source.delayed());
    }

    @GetMapping(
            path = "/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<StreamEvent>> sse() {
        return source.delayed()
                .map(event -> ServerSentEvent
                        .<StreamEvent>builder()
                        .id(Long.toString(event.id()))
                        .event("change")
                        .data(event)
                        .build());
    }

    @GetMapping(
            path = "/live",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<StreamEvent> live() {
        return source.live();
    }

    @GetMapping(
            path = "/single",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<StreamEvent> single() {
        return source.first();
    }

    @GetMapping(
            path = "/strings",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<String>> strings() {
        return Mono.just(List.of("first", "second"));
    }

    @PostMapping(
            path = "/ingest",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<IngestReceipt>> ingest(
            @RequestBody Flux<IncomingEvent> incoming) {

        return incoming.take(6)
                .collectList()
                .map(records -> {
                    if (records.size() > 5) {
                        throw new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "At most five records");
                    }
                    if (records.isEmpty()) {
                        throw new ResponseStatusException(
                                HttpStatus.BAD_REQUEST,
                                "At least one record required");
                    }
                    for (IncomingEvent record : records) {
                        if (!validator.validate(record).isEmpty()) {
                            throw new ResponseStatusException(
                                    HttpStatus.BAD_REQUEST,
                                    "Invalid event");
                        }
                    }

                    List<String> messages = records.stream()
                            .map(IncomingEvent::message)
                            .toList();

                    return ResponseEntity.ok(
                            new IngestReceipt(
                                    records.size(), messages));
                });
    }
}
```

### Vì sao các endpoints này thể hiện đúng media types?

- `json()` và `ndjson()` đều trả **`ResponseEntity<Flux<StreamEvent>>`**, nên chính `Content-Type`/`produces` làm rõ encoder nên tạo JSON array hay từng NDJSON line.
- `sse()` trả `Flux<ServerSentEvent<...>>` và `text/event-stream`; trên wire sẽ có `id`/`event`/`data` và blank lines thay vì NDJSON thuần.
- `live()` phát liên tục và client phải cancel; không có `collectList()`.
- `single()` dùng Mono cho đúng cardinality một object.
- `strings()` tránh nhầm `Flux<String>` với JSON array string values bằng cách trả một `Mono<List<String>>`.
- `ingest()` nhận NDJSON bằng `@RequestBody Flux<IncomingEvent>`, nhưng **trả JSON object thông thường**; giới hạn 5 records bằng `take(6)`, validate tất cả trước khi tạo receipt.
- `cacheControl(CacheControl.noStore())` gắn header để minh họa dữ liệu streaming/private không nên cache tùy tiện; ở app thật hãy chọn cache policy dựa vào dữ liệu.
- `ResponseStatusException` dùng khi body hợp lệ về cú pháp nhưng vi phạm quy tắc batch; lỗi decoder/malformed NDJSON xử lý qua WebFlux default error handling và không tự trở thành receipt.

**Lưu ý:** Demo ingest chỉ đếm/kiểm tra, không persist dữ liệu. Nếu thêm DB, phải thiết kế transactional/idempotent semantics; `collectList()` không phải một DB transaction. Nếu server bị client gửi một record khổng lồ, giới hạn 5 records không thay giới hạn request bytes.

## 14. Chạy project và quan sát wire format

Cài JDK 17+ và Maven. Từ thư mục `webflux-ndjson-demo`:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh chạy **tuần tự**. Sau khi Boot khởi động, mặc định listen tại `http://localhost:8080` nếu chưa đổi `server.port`.

### 14.1. Regular JSON array

```bash
curl -i \
  -H 'Accept: application/json' \
  'http://localhost:8080/api/streams/json'
```

Các phần chính của response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

[{"id":1,"type":"order","message":"created"},{"id":2,"type":"order","message":"paid"},{"id":3,"type":"order","message":"shipped"}]
```

JSON serializer có thể chọn spacing và header bổ sung khác. Điều cần kiểm tra là **một root array có 3 items**, không phải 3 JSON documents nối bởi newlines.

### 14.2. NDJSON output

```bash
curl -i -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/streams/ndjson'
```

Dự kiến body:

```text
{"id":1,"type":"order","message":"created"}
{"id":2,"type":"order","message":"paid"}
{"id":3,"type":"order","message":"shipped"}
```

`curl -N` giảm buffering ở phía curl để dễ quan sát dữ liệu đến theo thời gian; nó **không** tắt buffering tại proxy/server. Với decoder của Spring 6.1, NDJSON output được tạo theo từng value và newline separator. Không đồng nhất số HTTP chunks với số JSON lines.

### 14.3. SSE output

```bash
curl -i -N \
  -H 'Accept: text/event-stream' \
  'http://localhost:8080/api/streams/sse'
```

SSE body có dạng:

```text
id:1
event:change
data:{"id":1,"type":"order","message":"created"}

id:2
event:change
data:{"id":2,"type":"order","message":"paid"}

id:3
event:change
data:{"id":3,"type":"order","message":"shipped"}

```

Một số emitter/formatters có thể sử dụng dấu cách sau colon; parser SSE không nên phụ thuộc spacing đó. Điểm phân biệt là **trường `data:` và blank line kết thúc event**, không phải chỉ có newline giữa JSON objects.

### 14.4. Live NDJSON và hủy kết nối

```bash
curl -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/streams/live'
```

Đây là **stream vô hạn**. Dùng `Ctrl+C` để ngắt client khi quan sát đủ vài dòng. Không dùng một JSON parser đợi `]` kết thúc; stream không có một outer array. Với API thật, application cần dispose subscriptions và cleanup upstream resources khi client cancel.

### 14.5. POST NDJSON input, nhận một JSON receipt

Trên Bash:

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/x-ndjson' \
  -H 'Accept: application/json' \
  --data-binary $'{"message":"alpha"}\n{"message":"beta"}\n'
```

Dự kiến:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"accepted":2,"messages":["alpha","beta"]}
```

Trong PowerShell, cú pháp `$'...'` của Bash không hoạt động; hãy tạo file `input.ndjson` chứa đúng hai dòng rồi gọi:

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/x-ndjson' \
  --data-binary '@input.ndjson'
```

Đây là ý tưởng portable qua shell có `curl` thật, nhưng trên Windows PowerShell `curl` có thể là alias khác; dùng `curl.exe` khi cần.

### 14.6. Test lỗi Content-Type và Accept

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/json' \
  -d '[{"message":"wrong-format"}]'

curl -i \
  -H 'Accept: text/plain' \
  'http://localhost:8080/api/streams/ndjson'
```

Endpoint ingest khai báo `consumes=application/x-ndjson` nên request `application/json` không khớp, thông thường nhận **415 Unsupported Media Type**. NDJSON GET khai báo `produces=application/x-ndjson`, client chỉ Accept `text/plain` thường nhận **406 Not Acceptable**.

### 14.7. Test validation trên một NDJSON line

```bash
curl -i -X POST \
  'http://localhost:8080/api/streams/ingest' \
  -H 'Content-Type: application/x-ndjson' \
  --data-binary $'{"message":"   "}\n'
```

Dự kiến **400 Bad Request** vì `@NotBlank` được kiểm tra thủ công qua `Validator` trong handler. Error body mặc định của Spring Boot có thể khác theo configuration; demo không tuyên bố một JSON error schema cụ thể cho nó.

## 15. WebTestClient: kiểm chứng JSON array, NDJSON framing và streaming

Tập hợp tests dưới đây chạy `RANDOM_PORT`, kiểm thử toàn bộ reactive HTTP server pipeline, codecs và content negotiation chứ không chỉ gọi Java method. Các tests dùng dữ liệu bất biến nên không phụ thuộc thứ tự thực thi.

**`src/test/java/example/streaming/StreamControllerTest.java`**

```java
package example.streaming;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void regularJsonReturnsOneArrayWithThreeEvents() {
        client.get().uri("/api/streams/json")
              .accept(MediaType.APPLICATION_JSON)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_JSON)
              .expectBodyList(StreamEvent.class)
              .hasSize(3);
    }

    @Test
    void ndjsonHasThreeNonemptyLines() {
        client.get().uri("/api/streams/ndjson")
              .accept(MediaType.APPLICATION_NDJSON)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.APPLICATION_NDJSON)
              .expectBody()
              .consumeWith(result -> {
                  byte[] bytes = result.getResponseBody();
                  assertNotNull(bytes);

                  String body = new String(
                          bytes, StandardCharsets.UTF_8);
                  List<String> lines = body.lines()
                          .filter(line -> !line.isBlank())
                          .toList();

                  assertEquals(3, lines.size());
                  assertTrue(lines.get(0).contains("\"id\":1"));
                  assertTrue(lines.get(1).contains("\"id\":2"));
                  assertTrue(lines.get(2).contains("\"id\":3"));
              });
    }

    @Test
    void reactiveDecoderReadsNdjsonItems() {
        Flux<StreamEvent> events = client.get()
                .uri("/api/streams/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamEvent.class)
                .getResponseBody();

        StepVerifier.create(events)
                .expectNextMatches(event -> event.id() == 1)
                .expectNextMatches(event -> event.id() == 2)
                .expectNextMatches(event -> event.id() == 3)
                .verifyComplete();
    }

    @Test
    void sseResponseUsesEventFraming() {
        client.get().uri("/api/streams/sse")
              .accept(MediaType.TEXT_EVENT_STREAM)
              .exchange()
              .expectStatus().isOk()
              .expectHeader().contentTypeCompatibleWith(
                      MediaType.TEXT_EVENT_STREAM)
              .expectBody()
              .consumeWith(result -> {
                  byte[] bytes = result.getResponseBody();
                  assertNotNull(bytes);
                  String text = new String(
                          bytes, StandardCharsets.UTF_8);
                  assertTrue(text.contains("id:"));
                  assertTrue(text.contains("event:"));
                  assertTrue(text.contains("data:"));
              });
    }

    @Test
    void ingestFluxOfTwoNdjsonObjects() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_NDJSON)
              .accept(MediaType.APPLICATION_JSON)
              .body(Flux.just(
                      new IncomingEvent("alpha"),
                      new IncomingEvent("beta")),
                      IncomingEvent.class)
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.accepted").isEqualTo(2)
              .jsonPath("$.messages[0]").isEqualTo("alpha")
              .jsonPath("$.messages[1]").isEqualTo("beta");
    }

    @Test
    void ingestRejectsInvalidRecord() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_NDJSON)
              .body(Flux.just(new IncomingEvent("   ")),
                      IncomingEvent.class)
              .exchange()
              .expectStatus().isBadRequest();
    }

    @Test
    void ingestRejectsMoreThanFiveRecords() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_NDJSON)
              .body(Flux.range(0, 6)
                      .map(n -> new IncomingEvent("m" + n)),
                      IncomingEvent.class)
              .exchange()
              .expectStatus().isEqualTo(413);
    }

    @Test
    void rejectsWrongRequestContentType() {
        client.post().uri("/api/streams/ingest")
              .contentType(MediaType.APPLICATION_JSON)
              .bodyValue("{\"message\":\"one\"}")
              .exchange()
              .expectStatus().isEqualTo(415);
    }

    @Test
    void rejectsUnacceptableResponseType() {
        client.get().uri("/api/streams/ndjson")
              .accept(MediaType.TEXT_PLAIN)
              .exchange()
              .expectStatus().isEqualTo(406);
    }

    @Test
    void infiniteStreamCanBeCancelled() {
        Flux<StreamEvent> stream = client.get()
                .uri("/api/streams/live")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamEvent.class)
                .getResponseBody();

        StepVerifier.create(stream)
                .expectNextCount(2)
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void stringArrayIsValidJsonArray() {
        client.get().uri("/api/streams/strings")
              .accept(MediaType.APPLICATION_JSON)
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$[0]").isEqualTo("first")
              .jsonPath("$[1]").isEqualTo("second");
    }
}
```

Bộ test có **11 test methods**. Khi source files được tạo đúng và các tests pass, Maven thường báo tổng `Tests run: 11, Failures: 0, Errors: 0` (thông tin có thể thay đổi theo test runner). **Mã được rà soát tĩnh; trong quá trình viết Knowledge lên Google Sheets, không chạy Maven runtime.**

### Test nào xác minh điều gì?

- `regularJsonReturnsOneArrayWithThreeEvents`: list kết quả là một JSON array có 3 DTOs.
- `ndjsonHasThreeNonemptyLines`: HTTP raw bytes chứa ba dòng riêng, đúng thứ tự events.
- `reactiveDecoderReadsNdjsonItems`: NDJSON response được WebTestClient decode thành ba `StreamEvent` theo Reactive Streams.
- `sseResponseUsesEventFraming`: có các fields `id:`, `event:`, `data:`; không đồng nhất với NDJSON.
- `ingestFluxOfTwoNdjsonObjects`: WebTestClient tự encode Flux đầu vào thành NDJSON và server decode thành Flux DTO.
- `ingestRejectsInvalidRecord`: Jakarta Validator từ chối message chỉ có whitespace.
- `ingestRejectsMoreThanFiveRecords`: giới hạn record count; 6 items trả 413.
- `rejectsWrongRequestContentType`: `consumes` của POST không chấp nhận application/json.
- `rejectsUnacceptableResponseType`: `produces` của GET không chấp nhận text/plain.
- `infiniteStreamCanBeCancelled`: client nhận hai items rồi hủy; không block đợi stream vô hạn complete.
- `stringArrayIsValidJsonArray`: Mono<List<String>> có JSON array semantics.

### Vì sao không assert mỗi HTTP chunk là một record?

Một NDJSON line có thể bị chia giữa nhiều TCP packets hoặc nhiều lines có thể đi trong một packet. Kiểm thử phải parse bằng **newline delimiter** hoặc codec, không dựa vào HTTP chunk count.

### Vì sao StepVerifier quan trọng cho stream vô hạn?

Nếu dùng `expectBody()` đối với stream không bao giờ complete, test có thể chờ mãi hoặc timeout. `StepVerifier` với `thenCancel()` cho phép thực hiện một kịch bản client thật: nhận vài phần tử rồi đóng subscription.

### Kiểm thử bổ sung khi dùng production

- Slow downstream consumer, proxy buffering, gzip/HTTP2 interactions.
- Client disconnect trước record cuối và cleanup upstream.
- Stream error sau record đầu, incomplete export detection.
- 1000+ lines, max line/JSON nesting/byte size.
- UTF-8 split giữa các network reads.
- Invalid JSON ở dòng thứ 2.
- Sensitive data/cache directives.
- Phân quyền theo tenant/owner.
- Timeout/keepalive ở proxy và server.
- Resume từ event sequence hoặc offset.
- Backpressure trên broker/DB thật, không chỉ in-memory Flux.

## 16. Client parser: cách đọc NDJSON an toàn

### 16.1. Python client đọc từng dòng

Ví dụ client Python dựa trên requests `stream=True`:

```python
import json
import requests

url = "http://localhost:8080/api/streams/ndjson"

with requests.get(
    url,
    headers={"Accept": "application/x-ndjson"},
    stream=True,
    timeout=(5, 30),
) as response:
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        record = json.loads(line)
        print(record["id"], record["message"])
```

Đây là ví dụ runnable khi cài package `requests`; output ID/message dự kiến là:

```text
1 created
2 paid
3 shipped
```

Không dùng `response.json()` cho toàn NDJSON body: nó không phải một JSON document duy nhất.

### 16.2. JavaScript fetch stream parser

Browser `fetch` có thể đọc `ReadableStream` theo chunks. Cần ghép partial chunks rồi tách theo newline:

```javascript
async function readNdjson(url, onRecord) {
  const response = await fetch(url, {
    headers: { Accept: "application/x-ndjson" }
  });
  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }
  if (!response.body) {
    throw new Error("Streaming body unavailable");
  }

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .getReader();

  let pending = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    pending += value;

    let newline;
    while ((newline = pending.indexOf("\n")) >= 0) {
      const line = pending.slice(0, newline).trim();
      pending = pending.slice(newline + 1);
      if (line.length > 0) {
        onRecord(JSON.parse(line));
      }
    }
  }

  // Chấp nhận dòng cuối không có newline khi protocol cho phép.
  if (pending.trim() !== "") {
    onRecord(JSON.parse(pending.trim()));
  }
}

readNdjson("/api/streams/ndjson", event => {
  console.log(event.id, event.message);
});
```

Đây là snippet thực tế cho browser hỗ trợ `fetch` streams và `TextDecoderStream`. Đối với production:
- Giới hạn `pending.length` để tránh một dòng độc hại vô hạn gây OOM.
- Nếu client yêu cầu newline cuối để xác nhận integrity, **không** tự coi pending cuối là record hoàn chỉnh.
- Xử lý AbortController/cancellation, timeouts, retries và CORS credentials.
- Với DOM, dùng `textContent` thay `innerHTML` để tránh XSS từ message.
- Dùng parser biết xử lý CRLF (`\r\n`), whitespace và invalid lines theo contract.
- Trong môi trường reverse proxy, lần read() không đồng nghĩa một record.

### 16.3. Unix command-line tools

`curl -N` + line-oriented processors thuận tiện cho NDJSON. Ví dụ với `jq`:

```bash
curl -sS -N \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/streams/ndjson' \
  | jq -r '.id | tostring'
```

Nếu server trả 3 records như seed, stdout:

```text
1
2
3
```

Lưu ý pipeline phụ thuộc `jq` được cài; đây là ví dụ tiện ích CLI, không phải bước bắt buộc chạy Spring app.

## 17. Lựa chọn ResponseEntity khi stream có điều kiện

Nếu status/headers đã biết trước khi phát stream:

```java
public ResponseEntity<Flux<StreamEvent>> export() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_NDJSON)
            .body(source.delayed());
}
```

Nếu phải kiểm tra quyền/quota hoặc resource existence **bất đồng bộ trước khi trả status**, chọn `Mono<ResponseEntity<Flux<StreamEvent>>>`:

```java
public Mono<ResponseEntity<Flux<StreamEvent>>> export() {
    return permissions.canExport()
            .map(allowed -> {
                if (!allowed) {
                    return ResponseEntity.status(
                            HttpStatus.FORBIDDEN)
                            .<Flux<StreamEvent>>build();
                }
                return ResponseEntity.ok()
                        .contentType(MediaType.APPLICATION_NDJSON)
                        .body(source.delayed());
            });
}
```

Hai đoạn là snippets với `permissions`, `source` giả định. Điểm cần nhớ:

- `ResponseEntity<Flux<T>>`: HTTP envelope (status/headers) được chọn ngay khi controller return.
- `Mono<ResponseEntity<Flux<T>>>`: HTTP envelope được chọn sau Mono check async; body Flux có thể stream sau.
- `Mono<ResponseEntity<T>>`: phù hợp request đơn cần chọn 200/404/201 theo result.
- Nếu stream đã bắt đầu, error sau commit không tự biến 200 thành 500.

Trong production, check quyền không chỉ là một boolean; cần Spring Security reactive authentication và kiểm tra resource/tenant tại service boundary. Không lấy `X-Role` do client gửi làm "admin".

## 18. Khi nào nên trả job ID thay vì giữ stream?

Không phải mọi export dài đều cần HTTP live stream. Nếu tạo báo cáo 30 phút, phải truy cập một DB rất đắt hoặc cần tệp có checksum ổn định, phương án phù hợp hơn có thể là:

1. `POST /exports` trả **202 Accepted** cùng job ID.
2. Worker riêng xây export file vào storage có lifecycle.
3. `GET /exports/{id}` trả trạng thái, checksum và metadata.
4. Khi hoàn tất, client tải một file `application/x-ndjson` hoặc `application/json` có content length/file integrity rõ.
5. Có TTL, access controls, audit, retry, idempotency.

Streaming hữu ích khi cần dữ liệu incremental thật sự, nhưng kết nối HTTP mở lâu tiêu thụ sockets, buffers và tracking state; proxy/CDN có thể timeout. "Reactive" không đồng nghĩa việc giữ vô hạn một HTTP connection luôn tốt hơn thiết kế job-based.

## 19. Sai lầm thường gặp và cách sửa

| Hiện tượng | Nguyên nhân phổ biến | Cách sửa |
| --- | --- | --- |
| Flux tạo 1 JSON array thay vì từng dòng | Response `application/json` | `produces=application/x-ndjson` và compatible codec |
| Client gọi JSON.parse(wholeBody) thất bại | Body là NDJSON nhiều JSON texts | Parse từng newline-delimited line |
| Client cứ chờ, không thấy record đầu | JSON codec gom Flux; proxy/client buffering | NDJSON/SSE, flush + đo client-side |
| Một chunk chứa nửa JSON object | Transport chunks không phải record framing | Giữ buffer đến newline |
| Chuỗi "first" không thành JSON array | `Flux<String>` được writer xử lý như text | `Mono<List<String>>` cho array |
| SSE client không nhận NDJSON | EventSource yêu cầu text/event-stream | Dùng `Flux<ServerSentEvent<T>>` |
| NDJSON parser hiểu sai json-seq | JSON-seq dùng RS delimiter | Chọn đúng spec/framing |
| 406 Not Acceptable | `Accept` không khớp `produces` | Gửi header phù hợp hoặc cung cấp representation khác |
| 415 Unsupported Media Type | `Content-Type` không khớp `consumes` | Đổi đúng request media type |
| 400 khi POST NDJSON | JSON line hỏng/DTO fail validation | Validate line và input schema, logs an toàn |
| Client gửi 6 records nhưng API chỉ nhận 5 | Thiếu record count limit policy | `take(6)` + reject >5 |
| API chấp nhận 5, bỏ dòng thứ 6 | Dùng `take(5)` truncate im lặng | Đọc thêm 1 để phát hiện overflow |
| Stream trả 200 dù lỗi ở giữa | Response đã commit | Resume/end marker/error protocol |
| App memory tăng với stream | `collectList()`/unbounded buffer | Bounded stream và limits |
| Thread pool nghẽn dù dùng Flux | Có JDBC/file/network blocking ở operator | Driver async hoặc bounded offload |
| Mất ordering | `flatMap` concurrency | `concatMap` hoặc sequence-aware merge |
| Proxy giữ toàn bộ response | Proxy buffering/compression | Cấu hình/tracing end-to-end cho stream |
| NDJSON lộ dữ liệu user | Không auth/tenant check/cache policy | Security + privacy + no-store |
| Client mất dữ liệu sau reconnect | Không có sequence/checkpoint | Event IDs, offsets, resume semantics |
| SSE id không hồi phục đúng | Server không xử lý Last-Event-ID | Retention/replay policy |
| Charset lỗi với Unicode split packets | Decode từng binary chunk độc lập | Streaming TextDecoder |
| 413 không xuất hiện như mong muốn | Giới hạn tại codec/proxy khác | Test 413/400 và own policy |
| Request body không đọc được | WebFilter subscribe raw DataBuffer trước | Không double-read, decorator đúng |
| NDJSON record gửi JSON array một dòng | Định dạng client sai | Một JSON object trên mỗi dòng |
| Streaming tests đứng mãi | Dùng expectBody() cho Flux vô hạn | StepVerifier + thenCancel |
| Throughput thấp | Downstream chậm, nhiều buffered items | Đo source/encoder/network/client separately |

## 20. Checklist triển khai thật

- [ ] Biết rõ client cần JSON document, NDJSON hay SSE.
- [ ] Chọn `produces`/`consumes` và status/headers nhất quán.
- [ ] Test `Accept`/`Content-Type` cùng 406/415 behavior.
- [ ] Đừng đồng nhất `Flux<T>` với "streaming on wire".
- [ ] Không giả định HTTP chunks/frames bằng JSON lines.
- [ ] Có NDJSON decoder phía client với buffer, UTF-8 và newline handling.
- [ ] Đặt giới hạn số items, bytes/line, JSON depth và request timeout.
- [ ] Không dùng `collectList()` cho stream không bound/vô hạn.
- [ ] Check validation/auth/tenant trước side effects và response commit.
- [ ] Dùng `ResponseEntity<Flux<T>>` hoặc `Mono<ResponseEntity<Flux<T>>>` đúng thời điểm chọn status.
- [ ] Không kỳ vọng đổi status sau partial writes.
- [ ] Có schema, ordering, idempotency, retry/resume contract.
- [ ] Streaming errors/timeout/cancel đều được logs/metrics phân loại.
- [ ] Không block event loop, không tự subscribe và không read body hai lần.
- [ ] Backpressure/buffer/cancellation ở upstream thật.
- [ ] Nếu dùng SSE, có reconnect/Last-Event-ID/heartbeat policy.
- [ ] Nếu sau reverse proxy, kiểm tra buffering, HTTP/2, TLS, compression.
- [ ] Không log PII/tokens/raw event payload, không cache private data công khai.
- [ ] Test list JSON, NDJSON raw lines, typed decoder, live cancellation và SSE framing.
- [ ] Benchmark qua production-like deployment; chỉ số server emission không đủ.
- [ ] Đánh giá job-based export khi công việc dài và không cần live interaction.

## 21. Bài tập thực hành

### Bài tập 1 — Thay media type

Đổi annotation của `/ndjson` từ `APPLICATION_NDJSON_VALUE` sang `APPLICATION_JSON_VALUE`, rồi quan sát:
- Content-Type trả về.
- Raw body sau khi 3 items complete.
- Bao lâu client thấy first complete JSON document.
- Điều gì xảy ra nếu thử parse từng dòng NDJSON.

Sau đó trả lại cấu hình NDJSON và viết lại một WebTestClient test chụp raw bytes, không đoán số network chunks.

### Bài tập 2 — Lỗi sau partial stream

Cho `source.delayed()` phát hai items rồi phát một `Flux.error`. Kiểm tra:
- Hai dòng đầu có đến client không?
- HTTP status còn 200 không?
- WebTestClient/curl phản ánh disconnect/error ra sao?
- Có cần end marker để phân biệt complete thành công với truncated stream không?

Không viết test cứng "luôn trả 500" vì response có thể đã commit.

### Bài tập 3 — Batch giới hạn và validation

Thay mức tối đa từ 5 thành 100:
- Dùng `take(101)`.
- Reject khi số phần tử lớn hơn 100, không lặng lẽ truncate.
- Validate mọi object trước khi ghi.
- Thêm max line bytes/request bytes ở runtime/proxy.
- Kiểm tra 100 records hợp lệ, 101 records, dòng số 2 invalid, empty stream và client cancel giữa chừng.

### Bài tập 4 — Browser consumer

Viết `fetch()` + streaming NDJSON reader. Dùng `AbortController` để hủy sau 2 records. Quan sát server logs/`doFinally` signal; đừng lưu entire payload trong browser memory.

### Bài tập 5 — SSE cho dashboard

Tạo một stream sự kiện tên `inventory-change` có `id` và JSON `data`. Dùng EventSource đọc và xử lý reconnect với `Last-Event-ID`. Cần có durable event store hoặc checkpoint mới bảo đảm không mất events, không phải chỉ thêm field `id` là đủ.

## 22. Câu hỏi tự kiểm tra

1. Vì sao `Flux<Event>` chưa đủ để quyết định body trên dây?
2. `application/json` khác `application/x-ndjson` thế nào khi upstream là Flux 3 items?
3. Vì sao `JSON.parse(wholeNdjsonBody)` thường lỗi?
4. NDJSON dùng delimiter nào? JSON Text Sequences (RFC 7464) dùng delimiter nào?
5. `text/event-stream` có phải NDJSON không?
6. `ServerSentEvent` có các fields nào quan trọng?
7. `Accept` và `Content-Type` khác chiều nào?
8. Annotated `produces` và `consumes` dùng để làm gì?
9. Khi nào HTTP status 406 và 415 thường xuất hiện?
10. Vì sao một `Flux<String>` không chắc thành JSON array strings?
11. `MediaType.APPLICATION_NDJSON` giúp điều gì trong codec?
12. `curl -N` có tắt proxy buffering không?
13. Có nên parse NDJSON theo ranh giới TCP packet/HTTP chunk không?
14. NDJSON có built-in Last-Event-ID như SSE không?
15. Status 200 có thể đổi thành 500 JSON sau khi đã gửi 2/3 lines không?
16. Tại sao `collectList()` trên stream vô hạn là lỗi nghiêm trọng?
17. Vì sao phải đọc phần tử thứ 101 để phát hiện batch >100?
18. `@Valid` có thay thế authorization/tenant checks không?
19. Gọi blocking JDBC trong `flatMap` có trở thành non-blocking nhờ Flux không?
20. `Schedulers.boundedElastic` làm thay đổi nơi blocking xảy ra như thế nào?
21. Vì sao `concatMap` hữu ích khi thứ tự sự kiện quan trọng?
22. HTTP status 404 có nhất thiết là một Reactor error signal không?
23. Vì sao cần heartbeat hoặc idle policy cho stream kết nối lâu?
24. Nếu client cancel, ai chịu trách nhiệm cleanup upstream?
25. Vì sao MIME type `application/json-seq` không nên bị gắn nhầm cho NDJSON?
26. WebTestClient cần test gì ngoài status để xác nhận framing?
27. Nếu client cần toàn bộ dữ liệu atomically, có nên stream partial NDJSON không?
28. Dữ liệu user-specific NDJSON nên được cache public ở CDN không?
29. Vì sao client cần buffer partial UTF-8 chunks và line fragments?
30. Khi nào nên dùng `202 Accepted` + job ID thay vì giữ HTTP stream mở?

**Gợi ý:** (1) Publisher type khác wire media type. (2) JSON array vs line-delimited objects/flush. (3) Không phải một JSON document. (4) LF so với ASCII RS. (5) Không, SSE có protocol fields. (6) id/event/data/retry/comment. (7) Nhận vs gửi. (8) Response vs request media predicates. (9) Accept không phù hợp vs request Content-Type không phù hợp. (10) String encoder đặc biệt. (11) Streaming JSON encoder/decoder. (12) Không. (13) Không. (14) Không, phải tự thiết kế resume. (15) Không bảo đảm vì committed. (16) Chờ complete và tăng RAM. (17) Reject chính xác mà không truncate. (18) Không. (19) Không. (20) Offload blocking, không chuyển driver thành non-blocking. (21) Bảo toàn order. (22) Không. (23) Phát hiện disconnect/proxy timeouts. (24) Application/source/client và reactive cancellation pipeline đúng trách nhiệm. (25) Framing khác. (26) Content-Type, raw lines, decoded DTOs, cancel. (27) Cân nhắc bounded JSON/job-based. (28) Không nếu dữ liệu nhạy cảm. (29) Chunks không trùng boundaries. (30) Công việc quá lâu, cần job lifecycle/checksum/retries.

## 23. Tài liệu tham khảo chính thức

- [Spring Framework — WebFlux Reactive Core, HTTP Codecs, Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux ResponseEntity return types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html#webflux-codecs)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework 6.1 — AbstractJackson2Encoder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/json/AbstractJackson2Encoder.html)
- [Spring Framework 6.1 — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Project Reactor — Backpressure and Reactive Streams](https://projectreactor.io/docs/core/release/reference/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 7464 — JavaScript Object Notation (JSON) Text Sequences](https://www.rfc-editor.org/rfc/rfc7464.html)
- [NDJSON specification repository](https://github.com/ndjson/ndjson-spec)

**Tổng kết:** **Flux là mô hình nhiều giá trị, không phải một định dạng HTTP.** Với WebFlux/Jackson, `application/json` thường đưa nhiều values thành **một JSON array**; `application/x-ndjson` cho phép **từng JSON text + newline**, encode/write/flush theo từng element. `text/event-stream` là SSE với framing và reconnect semantics khác. Hãy chọn media type theo **consumer protocol**, test đúng Content-Type/Accept và byte framing, thiết kế backpressure/bounds, giải quyết error sau commit và cancellation, và không dùng reactive types làm lý do bỏ qua validation, security hay hiệu năng downstream.
