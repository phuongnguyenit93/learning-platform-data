# Cung cấp NDJSON hoặc SSE với vòng đời kết nối rõ ràng trong Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Chủ đề cha:** Thực hành tổng hợp  
> **Trọng tâm:** thiết kế HTTP streaming bằng Newline Delimited JSON (NDJSON) hoặc Server-Sent Events (SSE); chọn đúng media type và framing; phát dữ liệu theo từng phần tử; quản lý heartbeat, timeout, reconnect, cursor, cancellation, backpressure, proxy buffering và lỗi sau khi response đã commit. Project mẫu sử dụng Java 17+, Spring Boot 4.0.9, Spring WebFlux, Reactor và WebTestClient.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một `Flux<T>` trả từ controller chưa tự bảo đảm client nhận dữ liệu theo từng record.
2. Phân biệt JSON document/array, NDJSON và SSE theo định dạng byte trên HTTP.
3. Chọn `application/x-ndjson` hoặc `text/event-stream` theo nhu cầu client.
4. Viết WebFlux controller trả `Flux<T>` với media type streaming và hiểu codec flush từng phần tử.
5. Tạo `ServerSentEvent<T>` với `data`, `event`, `id`, `retry` và comment heartbeat.
6. Thiết kế event envelope có `data`, `complete`, `error` để client nhận biết trạng thái nghiệp vụ.
7. Phân biệt HTTP error trước khi commit với lỗi xảy ra giữa một stream đang gửi.
8. Hiểu `Last-Event-ID`, reconnect của `EventSource` và cách replay từ event store.
9. Viết client NDJSON bằng `fetch`, `ReadableStream`, `TextDecoder` và parser xử lý chunk bị chia tùy ý.
10. Hủy stream từ client và để cancellation đi ngược về Reactor publisher.
11. Giới hạn queue, tốc độ phát, thời lượng kết nối, số kết nối và tài nguyên trên mỗi stream.
12. Xử lý heartbeat, reverse proxy buffering, idle timeout và compression.
13. Kiểm thử NDJSON/SSE bằng `WebTestClient`, `FluxExchangeResult` và `StepVerifier`.
14. Tách vòng đời kết nối HTTP khỏi vòng đời job nếu tác vụ cần chạy bền vững sau khi client ngắt.

**Nguyên tắc chính:** một kết nối streaming có ba phần cần được thiết kế cùng nhau: *protocol* (record/event được đóng khung ra sao), *lifecycle* (bắt đầu, hoàn tất, lỗi, reconnect và cancel), và *resource policy* (buffer, tốc độ, timeout và giới hạn kết nối). Chỉ trả `Flux` mới giải quyết phần composition; server và client vẫn phải thống nhất hai phần còn lại.

## 2. Vì sao streaming cần framing?

HTTP truyền một luồng byte. TCP packet, HTTP/1.1 chunk hoặc HTTP/2 DATA frame không phải ranh giới record mà ứng dụng có thể dựa vào.

Giả sử server muốn gửi ba object:

~~~json
{"id":1,"state":"queued"}
{"id":2,"state":"running"}
{"id":3,"state":"done"}
~~~

Nếu client nhận được một buffer chứa 1,5 record hoặc nhiều record cùng lúc, nó phải biết record kết thúc ở đâu. Giao thức streaming cần một quy tắc framing ổn định.

### 2.1. Một JSON document không đồng nghĩa JSON stream

Một JSON document thông thường có thể là object:

~~~json
{"id":1,"state":"queued"}
~~~

Hoặc một array:

~~~json
[
  {"id":1,"state":"queued"},
  {"id":2,"state":"running"},
  {"id":3,"state":"done"}
]
~~~

Array là một JSON document hoàn chỉnh. Client thường phải đợi document đủ để parse array; cách encode này không phải lựa chọn phù hợp nếu client cần xử lý mỗi record ngay khi nó đến.

### 2.2. NDJSON: mỗi dòng là một JSON value

NDJSON (Newline Delimited JSON) dùng newline làm delimiter:

~~~text
{"id":1,"state":"queued"}\n
{"id":2,"state":"running"}\n
{"id":3,"state":"done"}\n
~~~

Các quy tắc quan trọng:
- Mỗi dòng là một JSON text hợp lệ.
- Mỗi record được theo sau bởi `LF` (`\n`); `CRLF` (`\r\n`) cũng được parser chấp nhận.
- Encoding là UTF-8.
- Không có dấu phẩy giữa các dòng và không có outer array.
- JSON string phải escape newline thành `\n`; newline thực được dùng để kết thúc record.
- Media type thường dùng là `application/x-ndjson`.

Một dòng có thể được parse độc lập. Parser phải tích lũy byte/character cho tới newline vì một network chunk có thể chứa nửa dòng hoặc nhiều dòng.

### 2.3. SSE: mỗi event là một khối text

SSE dùng media type `text/event-stream`. Một event gồm các field, kết thúc bằng **một dòng trống**:

~~~text
id: 1
event: progress
retry: 3000
data: {"percent":20,"message":"started"}

id: 2
event: progress
data: {"percent":60,"message":"working"}

id: 3
event: complete
data: {"percent":100,"message":"done"}

~~~

Các field thường dùng:
- `data`: payload event.
- `event`: tên event để client đăng ký listener riêng.
- `id`: event ID được lưu làm last event ID.
- `retry`: thời gian reconnect tính bằng milliseconds.
- Dòng bắt đầu bằng `:` là comment; thường dùng làm heartbeat.
- Event được phân tách bởi dòng trống, không phải bởi một TCP/HTTP chunk.

SSE là giao thức server-to-client một chiều trên HTTP. Trình duyệt có API `EventSource` hỗ trợ tự reconnect khi kết nối đóng, và gửi `Last-Event-ID` khi nối lại nếu event trước đó có `id`.

### 2.4. So sánh nhanh

| Tiêu chí | NDJSON | SSE |
| --- | --- | --- |
| Media type | `application/x-ndjson` | `text/event-stream` |
| Framing | Một JSON value + newline | Field lines + blank line |
| Payload | JSON trực tiếp trên từng dòng | Event data, thường là JSON |
| Event name | Do schema JSON tự định nghĩa | Field `event` |
| Event ID | Không có trong format cốt lõi | Field `id` |
| Reconnect | Client tự thiết kế | `EventSource` hỗ trợ |
| Cursor/replay | Query/header do API quy định | `Last-Event-ID` có sẵn trong protocol |
| Heartbeat | JSON control record theo schema | Comment `: keep-alive` |
| Browser API | `fetch` + `ReadableStream` | `EventSource` |
| Custom request headers | Có với `fetch` | Native EventSource không có API tùy ý cho headers |
| Hướng truyền | Một chiều trong một response | Một chiều server → client |
| Phù hợp | Data pipeline, CLI, backend consumer, records | Browser notifications, progress, live updates |

Chọn NDJSON khi consumer muốn xử lý record JSON tuần tự và tự kiểm soát cursor/retry. Chọn SSE khi browser cần event names, reconnect và last-event ID. Nếu cần client và server trao đổi hai chiều liên tục, xem WebSocket; nếu chỉ cần command hai chiều theo request, kết hợp POST cho command với SSE cho updates.

## 3. Streaming trong Spring WebFlux

WebFlux hỗ trợ reactive return values như `Mono` và `Flux`. Tuy nhiên, media type ảnh hưởng cách `HttpMessageWriter` encode multi-value publisher.

### 3.1. `application/json` và `application/x-ndjson`

Ví dụ trả `Flux<OrderEvent>`:

~~~java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<OrderEvent> events() {
    return service.events();
}
~~~

Với `application/json`, client nhận một JSON document, thường là array chứa các phần tử. Đây không phải lựa chọn rõ ràng cho newline-delimited streaming.

Để streaming record:

~~~java
@GetMapping(value = "/events", produces = "application/x-ndjson")
public Flux<OrderEvent> ndjson() {
    return service.events();
}
~~~

Với streaming media type được hỗ trợ, Spring WebFlux encode, write và flush từng phần tử theo dạng line-delimited JSON. Mỗi record được đưa xuống response khi publisher phát tín hiệu, thay vì gom toàn bộ thành một list trong bộ nhớ.

### 3.2. SSE với `ServerSentEvent<T>`

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<OrderEvent>> sse() {
    return service.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(Long.toString(event.sequence()))
            .event("progress")
            .retry(Duration.ofSeconds(3))
            .build());
}
~~~

`ServerSentEvent<T>` biểu diễn metadata event và payload. Spring encode payload qua JSON codec, ghi event fields theo SSE format và flush để client nhận event mà không phải chờ toàn bộ stream.

### 3.3. Đừng dùng `collectList()` cho một stream cần phát từng phần tử

~~~java
// Không streaming: đợi tất cả rồi mới tạo response.
public Mono<List<OrderEvent>> buffered() {
    return service.events().collectList();
}

// Streaming: mỗi event được encode theo media type phù hợp.
public Flux<OrderEvent> streaming() {
    return service.events();
}
~~~

`collectList()` hợp lý khi contract yêu cầu một JSON array có giới hạn. Với stream lớn hoặc vô hạn, nó có thể giữ toàn bộ dữ liệu trong heap và làm response chỉ bắt đầu sau khi upstream complete.

### 3.4. Flush không đồng nghĩa một event = một packet

Khi Spring flush một phần tử, client có thể nhận dữ liệu sớm hơn. Nhưng TCP, TLS, HTTP/2, reverse proxy, compression và client runtime vẫn có thể gộp/chia byte thành những chunk khác nhau.

**Không viết parser dựa trên ranh giới chunk.** Chỉ parse theo newline của NDJSON hoặc blank-line/event framing của SSE.

## 4. Thiết kế protocol envelope và lifecycle

Một stream production cần nói rõ khi nào dữ liệu bắt đầu, khi nào thành công, khi nào lỗi và khi nào client nên nối lại.

### 4.1. Envelope thống nhất

Một schema đơn giản:

~~~json
{"type":"data","id":"1","sequence":1,"message":"job started"}
{"type":"data","id":"2","sequence":2,"message":"processing"}
{"type":"complete","message":"stream completed"}
~~~

Nếu tác vụ thất bại:

~~~json
{"type":"data","id":"1","sequence":1,"message":"job started"}
{"type":"stream-error","errorCode":"UPSTREAM_FAILED","message":"Stream could not continue"}
~~~

Quy ước:
- `data`: một record nghiệp vụ.
- `complete`: stream hoàn tất bình thường.
- `stream-error`: lỗi nghiệp vụ được biểu diễn trong stream.
- `id`/`sequence`: cursor ổn định để resume.
- Không đưa stack trace, SQL, credential hoặc raw exception message vào payload lỗi.

Không bắt buộc dùng đúng tên field trên; điều quan trọng là contract có versioning và client biết terminal semantics.

### 4.2. Sơ đồ vòng đời

~~~text
Client request
    |
    v
Validate auth, job, cursor, media type
    |
    +---- invalid before commit ----> HTTP 4xx/5xx Problem response
    |
    v
Commit HTTP status + streaming headers
    |
    v
Subscribe to reactive source
    |
    +---- data frame/event ---------> client processes incrementally
    |
    +---- heartbeat ---------------> connection remains active
    |
    +---- complete ----------------> normal end; client closes
    |
    +---- stream-error ------------> in-band error; client decides retry
    |
    +---- client disconnect -------> cancel upstream subscription
~~~

Việc validate trước khi commit rất quan trọng. Khi response đã gửi status/header và một số bytes, server không thể đổi status 200 thành 500 hoặc thay phần body đã gửi bằng ProblemDetail hoàn chỉnh.

### 4.3. Lỗi trước và sau khi response commit

| Thời điểm | Ví dụ | Cách biểu diễn |
| --- | --- | --- |
| Trước commit | Job ID không tồn tại, không có quyền | HTTP 404/403, ProblemDetail |
| Trước commit | Cursor sai định dạng | HTTP 400 |
| Sau commit | Database stream bị lỗi sau 4 record | In-band error event/record hoặc đóng kết nối |
| Sau commit | Client disconnect | Cancellation, cleanup |
| Sau commit | Proxy idle timeout | Client phát hiện disconnect và áp dụng reconnect policy |

Nếu lỗi sau commit được chuyển thành một `stream-error` record/event trong publisher, HTTP status vẫn là 200; client phải đọc `type` hoặc `event` để biết stream thất bại. Nếu không có in-band error protocol, connection có thể kết thúc bất thường và client phải coi stream là chưa hoàn tất.

### 4.4. Không đánh đồng HTTP completion với business completion

`onComplete` có nghĩa Publisher đã kết thúc bình thường. Nó không tự chứng minh một background job đã commit kết quả, một payment đã thành công hoặc dữ liệu đã lưu bền vững.

Nếu nghiệp vụ cần xác nhận kết quả, phát một frame `complete` chỉ sau khi trạng thái job đã được lưu hoặc xác minh. Với tác vụ durable, persist event/cursor để client có thể reconnect và lấy phần còn thiếu.

## 5. NDJSON: server framing và client parsing

### 5.1. Ví dụ byte stream

Một NDJSON response:

~~~text
Content-Type: application/x-ndjson; charset=utf-8

{"type":"data","sequence":1,"message":"started"}\n
{"type":"data","sequence":2,"message":"working"}\n
{"type":"complete","message":"done"}\n
~~~

Mỗi dòng có thể được parse độc lập. Không có dấu phẩy giữa các dòng và không có outer array. Nếu một chuỗi chứa newline, JSON encoder phải escape nó thành hai ký tự `\` và `n`, không chèn newline thực vào record.

### 5.2. Client `fetch` phải giữ phần cuối chưa hoàn chỉnh

`ReadableStream` có thể trả về:
- Một nửa JSON record.
- Nhiều JSON record trong một chunk.
- Record bị chia giữa hai chunk.
- Chunk cuối cùng không có newline kết thúc.

Vì vậy client giữ `buffer`, tách các dòng hoàn chỉnh và chỉ parse phần dư khi EOF:

~~~javascript
async function readNdjson(url, signal, onRecord) {
  const response = await fetch(url, { signal });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/x-ndjson")) {
    throw new Error(`Unexpected Content-Type: ${contentType}`);
  }

  if (!response.body) {
    throw new Error("Streaming response body is unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();

      buffer += decoder.decode(value, { stream: !done });

      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.length === 0) {
          continue; // Policy của client này: bỏ qua blank line.
        }
        onRecord(JSON.parse(line));
      }

      if (done) {
        break;
      }
    }

    // Xử lý record cuối nếu server đóng mà không có newline cuối.
    if (buffer.length > 0) {
      onRecord(JSON.parse(buffer));
    }
  } finally {
    reader.releaseLock();
  }
}
~~~

`TextDecoder` dùng `{stream:true}` để giữ lại một UTF-8 code point bị chia qua nhiều byte/chunk. Không chuyển từng chunk riêng lẻ thành string rồi parse ngay: chunk không phải record boundary.

Trong ví dụ, blank line được bỏ qua. NDJSON reader có thể cho phép bỏ dòng trống nếu policy được tài liệu hóa; nếu hệ thống muốn strict parsing, hãy báo lỗi khi gặp blank line.

### 5.3. Hủy request NDJSON

~~~javascript
const controller = new AbortController();

readNdjson(
  "/api/streams/job-42/ndjson?after=0",
  controller.signal,
  frame => {
    console.log(frame.type, frame.sequence, frame.message);
  }
).catch(error => {
  if (error.name !== "AbortError") {
    console.error("Stream failed", error);
  }
});

// Khi người dùng đóng màn hình hoặc bấm Stop:
controller.abort();
~~~

`AbortController.abort()` hủy fetch; browser đóng response stream. Ở server, cancellation có thể truyền tới publisher nếu connector và source hỗ trợ. Một blocking call đang chạy có thể không dừng ngay; đừng coi cancellation là cơ chế rollback transaction.

### 5.4. Resume cho NDJSON

NDJSON không định nghĩa `Last-Event-ID`. API phải tự chọn cursor, ví dụ:
- Query `?after=123`.
- Header `X-Stream-Cursor: 123`.
- POST body chứa cursor khi cần filter phức tạp.

Cursor phải ổn định và được kiểm tra quyền truy cập. Nếu dùng sequence ID tăng dần, server đọc các record sau cursor từ event store và không phụ thuộc vào state trong memory của connection cũ.

## 6. SSE: event format, heartbeat và reconnect

### 6.1. Cấu trúc event

Một SSE event có thể có các dòng:

~~~text
id: 42
event: progress
retry: 3000
data: {"sequence":42,"percent":70}

~~~

Dòng trống cuối khối kích hoạt dispatch. Nếu `data` xuất hiện trên nhiều dòng, browser nối chúng với newline. Event stream luôn dùng UTF-8.

### 6.2. Named events

~~~javascript
const source = new EventSource("/api/streams/job-42/sse");

source.addEventListener("progress", event => {
  const frame = JSON.parse(event.data);
  renderProgress(frame);
});

source.addEventListener("complete", () => {
  source.close();
});

source.addEventListener("stream-error", event => {
  const frame = JSON.parse(event.data);
  showStreamError(frame.errorCode);
  source.close();
});

source.onerror = error => {
  // Đây là lỗi kết nối/trạng thái EventSource,
  // khác với event nghiệp vụ tên "stream-error".
  console.warn("SSE transport error", error);
};
~~~

`EventSource` tự reconnect khi kết nối bị đóng theo cơ chế của browser. Khi ứng dụng nhận event `complete` hoặc `stream-error` và không muốn reconnect, hãy gọi `source.close()`.

### 6.3. `id` và `Last-Event-ID`

Nếu server gửi:

~~~text
id: 42
event: progress
data: {"sequence":42,"percent":70}

~~~

Browser lưu last event ID. Khi kết nối lại, nó có thể gửi:

~~~http
Last-Event-ID: 42
~~~

Server đọc header này và replay các event sau ID 42. Điều này chỉ có ích khi:
- Event ID có thứ tự hoặc semantics cursor rõ.
- Event history còn được lưu.
- Server có thể replay event từ cursor.
- Client được quyền đọc stream/job đó.
- Replay không tạo side-effect lặp lại.

**Không chỉ nhận header rồi bỏ qua.** Nếu server luôn bắt đầu từ event 1, client có thể nhận duplicate hoặc thiếu dữ liệu. Có thể dùng `Last-Event-ID` như sequence cursor hoặc opaque cursor đã ký.

### 6.4. `retry` không phải retry nghiệp vụ

SSE field `retry: 3000` yêu cầu browser chờ khoảng thời gian reconnect được chỉ định khi connection bị đóng. Nó không:
- Retry một event bị xử lý lỗi ở JavaScript.
- Bảo đảm event không bị mất hoặc trùng.
- Thay thế idempotency.
- Thay thế event replay trên server.

Nếu reconnect sau event 42, server cần replay từ event 43. Client vẫn nên chống duplicate theo event ID vì network failure có thể xảy ra quanh thời điểm event được dispatch.

### 6.5. Heartbeat bằng comment

Một SSE heartbeat:

~~~text
: keep-alive

~~~

Comment không tạo message event cho application listener, nhưng giúp giữ connection hoạt động qua một số proxy/load balancer có idle timeout. Heartbeat nên có chu kỳ nhỏ hơn idle timeout thấp nhất trong toàn đường truyền, có khoảng dự phòng.

Không gửi comment quá dày. Heartbeat tạo network traffic, encode/write và có thể làm log/metrics tăng. Chọn chu kỳ theo hạ tầng, thường tính bằng hàng chục giây, và đo thực tế qua proxy.

### 6.6. Native EventSource có giới hạn request

Browser `EventSource` tạo GET request và không có API tùy ý để thêm bearer `Authorization` header hoặc gửi POST body. Có thể dùng cookie/session với `withCredentials` nếu CORS/security policy phù hợp:

~~~javascript
const source = new EventSource(
  "https://api.example.test/events",
  { withCredentials: true }
);
~~~

Nếu cần bearer token trong custom header, POST body hoặc kiểm soát parser/cursor chi tiết, dùng `fetch` + `ReadableStream` và tự parse SSE. Không nhét access token vào query string vì URL thường bị ghi vào proxy/access logs.

## 7. Heartbeat, flush và reverse proxy

### 7.1. Vì sao heartbeat cần thiết?

Một stream có thể không phát business event trong vài phút. Proxy/load balancer có thể coi connection không có byte truyền là idle và đóng nó. Server có thể không biết client đã ngắt cho tới lần write tiếp theo.

Spring Framework khuyến nghị phát dữ liệu định kỳ cho streaming responses như `text/event-stream` hoặc `application/x-ndjson` để phát hiện disconnect sớm hơn. Heartbeat có thể là comment-only SSE event hoặc một no-op record phù hợp protocol.

### 7.2. NDJSON heartbeat là control record

NDJSON không có comment syntax. Nếu cần heartbeat, dùng envelope hợp lệ:

~~~json
{"type":"heartbeat","sentAt":"2026-11-08T08:30:00Z"}
~~~

Client cần nhận biết `type=heartbeat` và không hiển thị như business data. Không gửi một dòng trống để thay heartbeat; dòng trống không phải một JSON record.

### 7.3. Response headers

Một streaming response thường cần các header phù hợp:

~~~http
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
~~~

- `Content-Type` xác định protocol.
- `Cache-Control` tránh cache response streaming và hạn chế một số biến đổi trung gian.
- `X-Accel-Buffering: no` là header riêng thường được Nginx hiểu để tắt proxy buffering; nó không phải HTTP standard và proxy khác có thể bỏ qua.

Với NDJSON, thay `Content-Type` bằng `application/x-ndjson`.

### 7.4. Nginx minh họa

~~~nginx
location /api/streams/ {
    proxy_pass http://webflux_app;
    proxy_http_version 1.1;

    proxy_buffering off;
    proxy_cache off;

    proxy_read_timeout 75s;
    proxy_send_timeout 75s;
}
~~~

Cấu hình này chỉ là ví dụ cho Nginx; cần khớp upstream, TLS, ingress và phiên bản đang triển khai. `proxy_read_timeout` phải lớn hơn khoảng heartbeat dự kiến. Kiểm tra cả load balancer, API gateway, service mesh, CDN và client timeout; tắt buffering ở một proxy không tắt buffering ở tất cả tầng.

### 7.5. Compression và latency

Compression có thể gom dữ liệu trước khi gửi hoặc đợi đủ dữ liệu để nén hiệu quả hơn. Với stream cần latency thấp, kiểm tra cách server/proxy xử lý gzip/brotli và cân nhắc tắt compression cho route streaming. Không mặc định rằng `flush()` ở Spring sẽ khiến mọi proxy lập tức gửi byte ra Internet.

## 8. Backpressure, buffer và concurrency

### 8.1. Backpressure chỉ hữu ích nếu toàn pipeline tôn trọng demand

Reactive Streams cho phép downstream request số lượng phần tử. WebFlux và Reactor có thể truyền demand từ HTTP writer về publisher, nhưng một callback/queue ngoài Reactor có thể không biết hoặc không tuân theo demand.

Nếu producer nhanh hơn consumer, phải có policy:
- Giảm tốc producer nếu có flow control.
- Giới hạn queue.
- Drop dữ liệu không quan trọng nếu contract cho phép.
- Coalesce state update mới nhất thay vì giữ mọi update.
- Fail stream khi buffer đầy nếu không thể giữ dữ liệu.
- Dùng durable queue/event log khi không được phép mất record.

### 8.2. Không dùng unbounded buffer cho mỗi connection

Ví dụ nguy hiểm:

~~~java
source.onBackpressureBuffer();
~~~

Overload có thể làm queue tăng không giới hạn. Với nhiều kết nối đồng thời, memory usage có thể trở thành:

\[
\text{memory} \approx
\text{active connections}
\times \text{queued events per connection}
\times \text{average event bytes}
\]

Dùng buffer bounded với overflow policy phù hợp:

~~~java
source.onBackpressureBuffer(
    256,
    dropped -> metrics.recordDroppedEvent(),
    BufferOverflowStrategy.ERROR
);
~~~

Đây là ví dụ policy fail stream khi queue đầy; metric và error mapping cần được triển khai. Nếu event có thể bị bỏ, thông báo cho client hoặc cung cấp cursor/replay để không mất tính đúng đắn.

### 8.3. Giới hạn số kết nối và thời gian sống

Mỗi stream có thể giữ:
- HTTP connection/socket.
- Subscription và operator state.
- Event cursor, context và tracing state.
- Buffer và pending write.
- Scheduled heartbeat task.
- Tài nguyên downstream như DB cursor/message subscription.

Cần đặt giới hạn số stream theo user/tenant/service, thời gian sống tối đa, idle timeout, request timeout và rate limit. Đối với stream dài hạn, cân nhắc reconnect định kỳ để phân tán tải hoặc xoay vòng deploy.

### 8.4. Không dùng `collectList()` để “giữ stream ổn định”

`collectList()` giữ toàn bộ phần tử trước khi complete. Với stream vô hạn, nó không bao giờ phát list. Với stream lớn hữu hạn, nó tăng heap theo tổng số record.

Hãy encode từng event, giới hạn page hoặc lưu dữ liệu vào một event store riêng nếu cần replay.

## 9. Cancellation và vòng đời tài nguyên

### 9.1. Client disconnect truyền cancellation

Khi browser đóng tab, gọi `EventSource.close()`, abort fetch hoặc network mất kết nối, HTTP response subscriber có thể cancel publisher. Reactor truyền cancellation upstream để source dừng phát nếu hỗ trợ.

~~~java
return service.stream(jobId)
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            log.info("stream_cancelled jobId={}", safeJobId);
        }
    });
~~~

`doFinally` quan sát `ON_COMPLETE`, `ON_ERROR` và `CANCEL`. Không log raw query/header/secret cùng job ID.

### 9.2. Cleanup với resource bất đồng bộ

Nếu stream mở resource như DB cursor, listener hoặc subscription message broker, cleanup phải theo complete/error/cancel. Với resource bất đồng bộ, dùng `usingWhen` hoặc abstraction lifecycle của driver:

~~~java
Flux<Record> records = Flux.usingWhen(
    repository.openCursor(jobId),
    cursor -> cursor.readAll(),
    cursor -> cursor.close(),
    (cursor, error) -> cursor.close(),
    cursor -> cursor.close()
);
~~~

Đây là fragment khái niệm: kiểu cursor và `close()` phải trả reactive type phù hợp với overload được chọn. Trong code thật, xử lý riêng cleanup error và đảm bảo driver có semantics close/cancel đúng.

Không tự `.subscribe()` một cleanup task rồi trả response; hãy compose cleanup vào lifecycle của Publisher.

### 9.3. Kết nối HTTP khác vòng đời job

Có hai mô hình:

**Ephemeral stream gắn với connection**
- Client disconnect thì hủy source/job.
- Hợp với query tạm thời hoặc stream không có giá trị sau khi client rời đi.
- Cần cleanup ngay khi cancel.

**Durable job tách khỏi connection**
- Job tiếp tục chạy dù client disconnect.
- Event được lưu bền vững kèm sequence/cursor.
- Client reconnect và đọc event sau cursor.
- Hợp với report generation, import/export hoặc workflow kéo dài.

Không để một HTTP subscription duy nhất là nơi duy trì một job cần sống qua restart/deploy. Khi cần durable execution, dùng job store/event store và quản lý job lifecycle độc lập.

## 10. Lỗi và terminal event sau khi response commit

### 10.1. Không thể đổi status sau khi đã gửi bytes

Một stream có thể gửi status 200 và 3 record rồi mới phát lỗi. Server không thể quay lại và đổi response thành 500.

Vì vậy cần chọn một trong hai policy:

1. **In-band error:** phát record/event `stream-error` có mã ổn định, sau đó kết thúc stream.
2. **Abrupt termination:** đóng connection; client nhận biết không có `complete` marker và coi stream chưa hoàn tất.

Đối với client cần phân biệt complete/error, in-band error thường dễ hiểu hơn.

### 10.2. NDJSON terminal envelope

~~~json
{"type":"data","sequence":1,"message":"started"}
{"type":"data","sequence":2,"message":"working"}
{"type":"stream-error","errorCode":"UPSTREAM_FAILED"}
~~~

Nếu thành công:

~~~json
{"type":"data","sequence":1,"message":"started"}
{"type":"data","sequence":2,"message":"done"}
{"type":"complete"}
~~~

Client chỉ coi stream thành công khi nhận `complete`. EOF mà chưa có `complete` có thể là disconnect hoặc lỗi giữa stream.

### 10.3. SSE terminal event

~~~text
id: 2
event: progress
data: {"sequence":2,"message":"working"}

event: stream-error
data: {"errorCode":"UPSTREAM_FAILED"}

~~~

Hoặc event thành công:

~~~text
id: 2
event: progress
data: {"sequence":2,"message":"done"}

event: complete
data: {"status":"ok"}

~~~

Không sử dụng event name `error` cho lỗi nghiệp vụ nếu client cũng cần xử lý `EventSource.onerror` của transport; tên như `stream-error` dễ phân biệt hơn.

### 10.4. Error payload an toàn

Chỉ gửi:
- Error code ổn định.
- Thông điệp public đã được duyệt.
- Job/event ID nếu không nhạy cảm.
- Retryable flag nếu API contract định nghĩa.
- Trace/correlation ID nếu an toàn để client dùng hỗ trợ.

Không gửi raw exception message, SQL, stack trace, URL nội bộ, token hoặc credential.

## 11. Reconnect, replay và duplicate handling

### 11.1. SSE reconnect không tự bảo đảm exactly-once

`EventSource` gửi `Last-Event-ID`, nhưng việc không mất/không trùng event phụ thuộc server có lưu và replay event đúng không. Network có thể ngắt sau khi server gửi bytes nhưng trước khi client xử lý xong. Một event có thể được gửi lại.

Client nên:
- Lưu last processed event ID sau khi xử lý thành công.
- Bỏ qua event ID đã xử lý.
- Xử lý event theo thứ tự nếu protocol yêu cầu.
- Có idempotency cho side-effect.
- Xác minh cursor thuộc đúng job/user/tenant.

### 11.2. Event store và cursor

Một event store tối thiểu cần:
- `job_id`.
- `sequence` tăng đơn điệu trong phạm vi job.
- `event_type`.
- Payload/version.
- `created_at`.
- Retention hoặc checkpoint policy.

Khi reconnect với `Last-Event-ID=42`, server đọc các event có sequence `>42`. Nếu cursor quá cũ và history đã hết retention, trả lỗi rõ ràng trước commit hoặc yêu cầu client tải snapshot mới.

### 11.3. Cursor opaque

Không phải lúc nào sequence integer cũng đủ. Có thể dùng cursor ký hoặc opaque token chứa:
- Job ID.
- Offset/sequence.
- Version.
- Expiry.
- Integrity signature.

Không để client tự sửa cursor để đọc dữ liệu của job/tenant khác. Kiểm tra authorization cho từng lần reconnect.

## 12. Project runnable: Spring Boot 4.0.9 + Java 17+

Demo tạo hai endpoint cùng sử dụng một stream envelope:
- `GET /api/streams/{jobId}/ndjson?after=0`
- `GET /api/streams/{jobId}/sse`

Service phát 5 data frames, sau đó `complete`. Với `jobId=fail`, service phát một vài data frames rồi một `stream-error` frame. SSE route thêm heartbeat comment và nhận `Last-Event-ID` để mô phỏng replay. Client disconnect sẽ cancel subscription.

### 12.1. Cấu trúc project

~~~text
webflux-stream-lifecycle/
├── pom.xml
├── src/main/java/com/example/stream/
│   ├── StreamApplication.java
│   ├── StreamFrame.java
│   ├── StreamService.java
│   └── StreamController.java
└── src/test/java/com/example/stream/
    └── StreamControllerTest.java
~~~

### 12.2. `pom.xml`

Spring Boot 4.0.9 và Java 17+. Parent quản lý version của Spring Framework, Reactor và test dependencies.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-stream-lifecycle</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

### 12.3. `StreamApplication.java`

~~~java
package com.example.stream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamApplication.class, args);
    }
}
~~~

### 12.4. `StreamFrame.java`

~~~java
package com.example.stream;

public record StreamFrame(
    String type,
    String id,
    Long sequence,
    String message,
    String errorCode
) {
    public static StreamFrame data(long sequence, String jobId) {
        return new StreamFrame(
            "data",
            Long.toString(sequence),
            sequence,
            "job " + jobId + " update " + sequence,
            null
        );
    }

    public static StreamFrame complete() {
        return new StreamFrame(
            "complete", null, null, "stream completed", null);
    }

    public static StreamFrame error(String code) {
        return new StreamFrame(
            "stream-error", null, null, null, code);
    }
}
~~~

`type` định nghĩa protocol event; `id` là cursor của data event; `sequence` thuận tiện cho consumer; `errorCode` là mã public. Trong production, nên version schema và giới hạn kích thước message.

### 12.5. `StreamService.java`

~~~java
package com.example.stream;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Service
public class StreamService {

    private static final Logger log =
        LoggerFactory.getLogger(StreamService.class);

    private static final long EVENT_COUNT = 5;

    public Flux<StreamFrame> frames(
            String jobId,
            long afterSequence) {

        if (afterSequence < 0 || afterSequence > EVENT_COUNT) {
            return Flux.error(
                new IllegalArgumentException("invalid stream cursor"));
        }

        long remaining = EVENT_COUNT - afterSequence;

        Flux<Long> sequence = Flux.interval(Duration.ofMillis(250))
            .take(remaining)
            .map(index -> afterSequence + index + 1);

        if ("fail".equals(jobId)) {
            sequence = sequence
                .take(2)
                .concatWith(Mono.<Long>error(
                    new IllegalStateException("simulated upstream failure")));
        }

        return sequence
            .map(value -> StreamFrame.data(value, jobId))
            .concatWith(Mono.just(StreamFrame.complete()))
            .onErrorResume(error ->
                Flux.just(StreamFrame.error("UPSTREAM_FAILED")))
            .doFinally(signal ->
                logLifecycle(jobId, signal));
    }

    private void logLifecycle(String jobId, SignalType signal) {
        // Không ghi payload hoặc dữ liệu xác thực của client.
        log.info(
            "stream_finished jobId={} signal={}",
            safeJobId(jobId),
            signal.name());
    }

    private String safeJobId(String jobId) {
        if (jobId == null) {
            return "unknown";
        }
        return jobId.replaceAll("[^A-Za-z0-9_-]", "_")
            .substring(0, Math.min(40, jobId.length()));
    }
}
~~~

Giải thích:
- `Flux.interval` mô phỏng nguồn phát định kỳ; `take` giới hạn số phần tử.
- `afterSequence` mô phỏng cursor để phát tiếp sau event đã xử lý.
- Job `fail` phát một số record rồi lỗi.
- `onErrorResume` chuyển lỗi thành một `stream-error` frame an toàn; lỗi không bị mất mà được biểu diễn trong protocol.
- `concatWith(Mono.just(StreamFrame.complete()))` chỉ phát `complete` khi nguồn hoàn tất bình thường. Nếu nguồn lỗi, `concatWith` không phát complete; nhánh fallback chỉ phát `stream-error`.
- `doFinally` ghi `CANCEL`, `ON_ERROR` hoặc `ON_COMPLETE` theo vòng đời subscription.

Đây là nguồn demo trong memory, không phải event store bền vững. Khi reconnect, nó dựng lại record theo sequence; production cần replay từ dữ liệu đã lưu.

### 12.6. `StreamController.java`

~~~java
package com.example.stream;

import java.time.Duration;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/streams")
public class StreamController {

    private static final MediaType NDJSON =
        MediaType.parseMediaType("application/x-ndjson");

    private static final Duration HEARTBEAT_INTERVAL =
        Duration.ofMillis(500);

    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{jobId}/ndjson",
        produces = "application/x-ndjson")
    public ResponseEntity<Flux<StreamFrame>> ndjson(
            @PathVariable String jobId,
            @RequestParam(defaultValue = "0") long after) {

        validateCursor(after);

        Flux<StreamFrame> body = service.frames(jobId, after);

        return ResponseEntity.ok()
            .contentType(NDJSON)
            .header(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, no-transform")
            .header("X-Accel-Buffering", "no")
            .body(body);
    }

    @GetMapping(
        value = "/{jobId}/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<StreamFrame>>> sse(
            @PathVariable String jobId,
            @RequestHeader(
                name = "Last-Event-ID",
                required = false) String lastEventId) {

        long after = parseLastEventId(lastEventId);
        validateCursor(after);

        Flux<ServerSentEvent<StreamFrame>> data =
            service.frames(jobId, after)
                .map(this::toServerSentEvent);

        Flux<ServerSentEvent<StreamFrame>> body =
            data.publish(shared -> Flux.merge(
                shared,
                Flux.interval(HEARTBEAT_INTERVAL)
                    .map(tick ->
                        ServerSentEvent.<StreamFrame>builder()
                            .comment("keep-alive")
                            .build())
                    .takeUntilOther(shared.then())
            ));

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .cacheControl(CacheControl.noCache())
            .header("X-Accel-Buffering", "no")
            .body(body);
    }

    private ServerSentEvent<StreamFrame> toServerSentEvent(
            StreamFrame frame) {

        ServerSentEvent.Builder<StreamFrame> builder =
            ServerSentEvent.builder(frame)
                .event(frame.type())
                .retry(Duration.ofSeconds(3));

        if (frame.id() != null) {
            builder.id(frame.id());
        }

        return builder.build();
    }

    private long parseLastEventId(String value) {
        if (value == null || value.isBlank()) {
            return 0;
        }

        try {
            return Long.parseLong(value);
        }
        catch (NumberFormatException exception) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid Last-Event-ID");
        }
    }

    private void validateCursor(long cursor) {
        if (cursor < 0 || cursor > 5) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Stream cursor is out of range");
        }
    }
}
~~~

Các điểm cần chú ý:
1. NDJSON dùng `application/x-ndjson`, SSE dùng `text/event-stream`.
2. Response headers được thiết lập trước khi publisher bắt đầu phát.
3. SSE `id` chỉ được gắn vào data frames có cursor; `complete` và `stream-error` không thay đổi last event ID.
4. Heartbeat là comment-only SSE event; không tạo business message.
5. `publish` chia sẻ một upstream subscription giữa nhánh data và nhánh theo dõi completion của heartbeat.
6. Khi source complete, `takeUntilOther(shared.then())` dừng heartbeat.
7. Khi client cancel, cancellation đi ngược qua publisher; `StreamService.doFinally` quan sát lifecycle.
8. Cursor demo chỉ là số từ 0 đến 5; production phải xác minh cursor thuộc đúng job và user.

### 12.7. `StreamControllerTest.java`

~~~java
package com.example.stream;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamControllerTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void ndjsonStreamsFiveRecordsAndCompleteFrame() {
        FluxExchangeResult<StreamFrame> result =
            http().get()
                .uri("/api/streams/demo/ndjson?after=0")
                .accept(MediaType.parseMediaType(
                    "application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.parseMediaType(
                            "application/x-ndjson"))
                .returnResult(StreamFrame.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(frame ->
                frame.type().equals("data")
                    && frame.sequence() == 1)
            .expectNextCount(4)
            .expectNextMatches(frame ->
                frame.type().equals("complete"))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void ndjsonCanResumeAfterCursor() {
        FluxExchangeResult<StreamFrame> result =
            http().get()
                .uri("/api/streams/demo/ndjson?after=3")
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamFrame.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(frame ->
                frame.type().equals("data")
                    && frame.sequence() == 4)
            .expectNextMatches(frame ->
                frame.type().equals("data")
                    && frame.sequence() == 5)
            .expectNextMatches(frame ->
                frame.type().equals("complete"))
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void sseStreamsNamedEventsAndHeartbeatComments() {
        FluxExchangeResult<ServerSentEvent<StreamFrame>> result =
            http().get()
                .uri("/api/streams/demo/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<StreamFrame>>() {});

        Flux<ServerSentEvent<StreamFrame>> dataEvents =
            result.getResponseBody()
                .filter(event -> event.data() != null);

        StepVerifier.create(dataEvents)
            .expectNextMatches(event ->
                event.event().equals("data")
                    && event.id().equals("1")
                    && event.data().sequence() == 1)
            .expectNextCount(4)
            .expectNextMatches(event ->
                event.event().equals("complete"))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void sseResumesFromLastEventId() {
        FluxExchangeResult<ServerSentEvent<StreamFrame>> result =
            http().get()
                .uri("/api/streams/demo/sse")
                .header("Last-Event-ID", "2")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<StreamFrame>>() {});

        StepVerifier.create(
                result.getResponseBody()
                    .filter(event -> event.data() != null))
            .expectNextMatches(event ->
                event.id().equals("3")
                    && event.data().sequence() == 3)
            .expectNextMatches(event ->
                event.id().equals("4"))
            .expectNextMatches(event ->
                event.id().equals("5"))
            .expectNextMatches(event ->
                event.event().equals("complete"))
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void upstreamFailureBecomesAnInBandErrorFrame() {
        FluxExchangeResult<StreamFrame> result =
            http().get()
                .uri("/api/streams/fail/ndjson")
                .exchange()
                .expectStatus().isOk()
                .returnResult(StreamFrame.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextCount(2)
            .expectNextMatches(frame ->
                frame.type().equals("stream-error")
                    && frame.errorCode().equals("UPSTREAM_FAILED"))
            .verifyComplete();
    }

    @Test
    void cancellationReachesTheReactiveSource() {
        StreamService service = new StreamService();
        java.util.concurrent.atomic.AtomicReference<SignalType> signal =
            new java.util.concurrent.atomic.AtomicReference<>();

        Flux<StreamFrame> source = service.frames("demo", 0)
            .doFinally(signal::set);

        StepVerifier.create(source)
            .expectNextMatches(frame -> frame.type().equals("data"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(SignalType.CANCEL, signal.get());
    }

    @Test
    void invalidCursorIsRejectedBeforeStreaming() {
        http().get()
            .uri("/api/streams/demo/ndjson?after=99")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void invalidLastEventIdIsRejected() {
        http().get()
            .uri("/api/streams/demo/sse")
            .header("Last-Event-ID", "not-a-number")
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Test này dùng HTTP server thật ở random port, kiểm tra status/header và sau đó dùng `StepVerifier` tiêu thụ `FluxExchangeResult`. Spring Framework hướng dẫn cách này cho các response streaming có thể kéo dài hoặc vô hạn.

Test cancellation cuối xác minh signal ở service Publisher. Trong integration test production, nên bổ sung test đóng HTTP client sớm và quan sát cleanup ở server/driver.

### 12.8. Chạy project

Yêu cầu JDK 17+, Maven và network để tải dependencies lần đầu.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

### 12.9. Thử NDJSON bằng curl

~~~bash
curl -N -i \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/streams/demo/ndjson?after=0"
~~~

Output minh họa:

~~~text
{"type":"data","id":"1","sequence":1,"message":"job demo update 1","errorCode":null}
{"type":"data","id":"2","sequence":2,"message":"job demo update 2","errorCode":null}
{"type":"data","id":"3","sequence":3,"message":"job demo update 3","errorCode":null}
{"type":"data","id":"4","sequence":4,"message":"job demo update 4","errorCode":null}
{"type":"data","id":"5","sequence":5,"message":"job demo update 5","errorCode":null}
{"type":"complete","id":null,"sequence":null,"message":"stream completed","errorCode":null}
~~~

`curl -N` tắt buffering output ở phía curl để dễ quan sát từng phần tử. Thời điểm nhận phụ thuộc connector và proxy; đừng lấy dòng hiển thị của terminal làm bằng chứng duy nhất về latency production.

### 12.10. Thử SSE bằng curl

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  "http://localhost:8080/api/streams/demo/sse"
~~~

Response sẽ có event fields tương tự:

~~~text
id: 1
event: data
retry: 3000
data: {"type":"data","id":"1","sequence":1,"message":"job demo update 1","errorCode":null}

:keep-alive

id: 2
event: data
retry: 3000
data: {"type":"data","id":"2","sequence":2,"message":"job demo update 2","errorCode":null}

event: complete
retry: 3000
data: {"type":"complete","id":null,"sequence":null,"message":"stream completed","errorCode":null}

~~~

Thứ tự heartbeat so với data phụ thuộc timer; output chỉ minh họa format. SSE comment không tạo `data` event cho client.

### 12.11. Mô phỏng reconnect

Lấy event ID 2 rồi gửi header:

~~~bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Last-Event-ID: 2" \
  "http://localhost:8080/api/streams/demo/sse"
~~~

Server demo bắt đầu từ sequence 3. Với NDJSON, cursor được gửi qua query:

~~~bash
curl -N \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/streams/demo/ndjson?after=2"
~~~

## 13. Production design: kiểm tra trước commit, stream sau commit

Trước khi trả response:
- Xác thực user/tenant và quyền đọc job.
- Xác nhận job tồn tại và đang ở trạng thái cho phép stream.
- Kiểm tra `Accept` và media type.
- Parse/verify cursor.
- Chọn event source và replay window.
- Đặt response headers, idle policy và cache policy.
- Xác định client có được reconnect hoặc resume không.

Sau khi response commit:
- Phát record/event theo schema đã version.
- Heartbeat theo idle timeout.
- Giữ queue/concurrency có giới hạn.
- Chuyển lỗi sang in-band event nếu protocol quy định.
- Hủy upstream và cleanup khi cancel.
- Không thay đổi status/body đã gửi.

### 13.1. Tách validation khỏi Publisher body

Một lỗi dễ mắc là đặt toàn bộ validation bên trong một `Flux.defer` rồi trả HTTP 200 trước khi biết job có hợp lệ hay không. Khi validation phát lỗi sau commit, client chỉ thấy stream error.

Với yêu cầu trả 404/403/400 chuẩn, validate đồng bộ/async trước khi tạo `ResponseEntity` body:

~~~java
return jobService.authorize(jobId, principal)
    .switchIfEmpty(Mono.error(new ResponseStatusException(
        HttpStatus.NOT_FOUND)))
    .map(job -> ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(jobService.events(job)));
~~~

Đây là fragment minh họa; cần định nghĩa `principal`, `jobService` và kiểu trả về tương ứng. `authorize` phải complete trước khi response được tạo/commit. Lỗi phát sinh sau khi `events(job)` đã bắt đầu thì tuân theo stream error protocol.

### 13.2. Job durable và event replay

Với report/job dài hạn:
1. POST tạo job, trả `202 Accepted` và `jobId`.
2. Worker xử lý job độc lập với HTTP connection.
3. Mỗi event được persist cùng sequence.
4. GET NDJSON/SSE đọc event từ cursor.
5. Client disconnect chỉ dừng subscriber, không hủy job durable.
6. Client reconnect với cursor và nhận phần còn lại.
7. Job kết thúc thì phát `complete`; lỗi thì phát error code đã lưu.

Đây là mẫu tách execution khỏi delivery. Nó tránh mất tác vụ chỉ vì browser refresh hoặc mạng gián đoạn.

## 14. Bảo mật và quyền truy cập stream

Streaming kéo dài có một số đặc thù:
- Authorization phải kiểm tra trước commit và theo tenant/job.
- Nếu quyền có thể bị thu hồi trong lúc stream chạy, quyết định có cần re-check định kỳ hoặc cancel connection không.
- Không đặt bearer token trong query string.
- Không để `Last-Event-ID` trở thành IDOR vector; cursor không thay thế authorization.
- Giới hạn số stream đồng thời trên mỗi user/tenant.
- Giới hạn event payload size và field nhạy cảm.
- Validate event name/id; không cho user input chứa CR/LF phá framing.
- Không đưa raw exception/stack trace vào event.
- CORS và cookie credentials phải có policy rõ; không dùng wildcard origin với credentials.
- Với SSE GET có cookie authentication, cân nhắc CSRF/session policy và quyền truy cập route.

NDJSON và SSE đều có thể chứa dữ liệu riêng tư. Việc payload được stream từng phần không làm giảm yêu cầu bảo mật so với JSON response thông thường.

## 15. Observability cho kết nối streaming

Một request streaming có thể kéo dài nhiều phút. Log “request started” và “request completed” cần được phân biệt rõ; không ghi một log cho mỗi event nếu traffic cao.

Theo dõi:
- Active stream connections theo route/protocol/tenant group có giới hạn.
- Connection duration.
- Bytes/records/events emitted.
- Heartbeats sent.
- Client cancellations.
- Stream errors theo error code.
- Resume/reconnect count.
- Replay lag/cursor age.
- Queue depth và overflow.
- p95/p99 time-to-first-event và inter-event gap.
- Proxy idle timeout/disconnect.
- Memory/direct buffer và network throughput.

Không dùng job ID, user ID hoặc event ID làm metric tag nếu cardinality không giới hạn. Có thể ghi chúng trong structured log/trace với access control phù hợp.

## 16. Kiểm thử streaming đầy đủ

### 16.1. Unit test với StepVerifier

Kiểm tra:
- Thứ tự record.
- `complete` chỉ xuất hiện sau thành công.
- `stream-error` xuất hiện khi upstream fail.
- Cancellation phát `SignalType.CANCEL`.
- Resume cursor bắt đầu từ event kế tiếp.
- Không có duplicate sequence trong một lần stream.

### 16.2. HTTP contract test với WebTestClient

Kiểm tra:
- Status trước khi body bắt đầu.
- `Content-Type` chính xác.
- Cache/buffering headers nếu là API contract.
- NDJSON từng object được decode đúng.
- SSE event name/id/data.
- Heartbeat không trở thành business data.
- Reconnect với `Last-Event-ID`.
- Invalid cursor trả 400 trước khi stream commit.
- Client cancel làm upstream cleanup.

`WebTestClient` có thể trả `FluxExchangeResult<T>` cho stream dài; `StepVerifier` kiểm tra response body theo tín hiệu mà client thực sự nhận được.

### 16.3. Test qua proxy/load balancer

Unit test không phát hiện buffering ở Nginx, ingress hoặc CDN. Staging cần xác nhận:
- Time-to-first-event.
- Event có tới client trong lúc stream còn mở hay bị gom lại.
- Heartbeat đủ thường xuyên để connection không bị idle timeout.
- Client disconnect có được truyền tới server.
- Compression có làm tăng latency không.
- HTTP/2 hoạt động đúng.
- Reconnect có replay đúng cursor.
- Deploy/rolling restart không làm mất durable event.

## 17. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả `Flux<T>` với `application/json` nhưng mong NDJSON | Client nhận JSON document/array semantics | Dùng `application/x-ndjson` |
| Parse từng network chunk thành JSON | Chunk có thể chứa nửa record hoặc nhiều record | Buffer và parse theo newline |
| Không xử lý dòng cuối không có newline | Mất record cuối | Parse phần dư khi EOF |
| Pretty-print JSON trong NDJSON | Newline nội bộ phá framing | Serialize compact một dòng |
| Gửi SSE event không có blank line | Browser chưa dispatch event | Kết thúc mỗi event bằng blank line |
| Dùng newline đơn làm SSE delimiter | Event không được dispatch đúng | Dùng blank line |
| Dùng SSE comment như business event | Client không nhận callback data | Dùng `data`/`event` field |
| Không gửi event ID | Reconnect không có cursor đáng tin | Gửi ID ổn định và replay |
| Nhận `Last-Event-ID` nhưng không replay | Client nhận duplicate hoặc mất dữ liệu | Đọc event store sau cursor |
| Dùng `retry` như retry business | Không giải quyết duplicate/loss | Idempotency + event replay |
| Không có heartbeat | Proxy đóng stream khi idle | Comment SSE hoặc NDJSON heartbeat record |
| Heartbeat quá dày | Network/log/CPU tăng | Chọn interval theo idle timeout |
| Không tắt proxy buffering | Event bị giữ ở proxy | Cấu hình proxy và đo staging |
| Tin `flush()` đảm bảo client nhận ngay | Proxy/transport có thể buffer | Kiểm tra toàn đường truyền |
| Dùng unbounded `onBackpressureBuffer()` | Memory tăng khi consumer chậm | Bounded buffer và overflow policy |
| `collectList()` stream lớn | Tốn heap, response chờ complete | Stream từng phần tử |
| Không xử lý cancel | DB cursor/listener/job bị rò rỉ | `doFinally`, `usingWhen`, cleanup |
| Mặc định client disconnect hủy durable job | Job bị mất ngoài ý muốn | Tách job lifecycle khỏi connection |
| Trả HTTP 500 sau khi đã gửi 200 bytes | Không thể đổi status đã commit | In-band error frame/event |
| Không có complete marker | Client khó phân biệt success với truncation | Phát `complete` envelope |
| Đặt `complete` trước khi persist kết quả | Client tưởng job thành công quá sớm | Persist terminal state rồi mới phát |
| EventSource custom Authorization header | Browser API không hỗ trợ tùy ý | Cookie phù hợp hoặc fetch parser |
| Không giới hạn stream duration/connections | Giữ socket và state vô hạn | Quota, timeout, connection cap |
| Dùng event ID/user ID làm metric tag | Cardinality cao | Tag bằng route/protocol/outcome |

## 18. Checklist production

- [ ] Chọn NDJSON hoặc SSE theo nhu cầu consumer.
- [ ] Content-Type chính xác và được test.
- [ ] NDJSON: UTF-8, một JSON value mỗi dòng, LF delimiter, không outer array.
- [ ] SSE: UTF-8, `text/event-stream`, blank-line framing.
- [ ] Client parser xử lý chunk chia tùy ý và record cuối.
- [ ] Event envelope có schema/version rõ.
- [ ] Có terminal `complete` và in-band error policy.
- [ ] Lỗi validation/auth/cursor được xử lý trước response commit.
- [ ] SSE event ID ổn định và replay thực sự dựa vào cursor.
- [ ] NDJSON có cursor/retry policy riêng nếu cần resume.
- [ ] Heartbeat interval nhỏ hơn proxy idle timeout.
- [ ] Proxy buffering/cache/compression được cấu hình và kiểm tra staging.
- [ ] Queue/buffer/concurrency có giới hạn.
- [ ] Không gom toàn bộ stream vào memory.
- [ ] Client cancel truyền tới upstream và resource cleanup.
- [ ] Job durable có lifecycle tách khỏi HTTP connection.
- [ ] Authorization được kiểm tra cho mỗi reconnect.
- [ ] Cursor không thể dùng để đọc dữ liệu tenant khác.
- [ ] Không đặt secret trong URL hoặc stream payload.
- [ ] Có limits cho connection count, duration và event size.
- [ ] Metrics có cardinality hữu hạn.
- [ ] Có test NDJSON/SSE bằng WebTestClient và StepVerifier.
- [ ] Có test cancellation, reconnect, cursor replay và error frame.
- [ ] Có staging smoke test qua proxy/load balancer thật.
- [ ] Có runbook cho disconnect, backlog, stream errors và reconnect storm.

## 19. Bài tập thực hành

**Bài 1 – JSON array và NDJSON.** Trả cùng 5 record bằng `application/json` và `application/x-ndjson`; quan sát client parse từng contract khác nhau.

**Bài 2 – Client parser.** Tạo test feed NDJSON thành các chunk cố tình chia giữa UTF-8 character, giữa JSON token và giữa newline; xác nhận parser vẫn tạo đúng record.

**Bài 3 – SSE event types.** Phát `progress`, `complete`, `stream-error`; dùng `addEventListener` và `EventSource.close()` đúng lúc.

**Bài 4 – Heartbeat.** Cho source không phát business event trong 30 giây; gửi SSE comment định kỳ và xác nhận proxy không idle-close.

**Bài 5 – Resume.** Ngắt sau event 3, reconnect với `Last-Event-ID: 3`, xác nhận event tiếp theo là 4.

**Bài 6 – NDJSON cursor.** Gửi `?after=3`, xác nhận stream chỉ phát record sau cursor.

**Bài 7 – Error sau commit.** Phát hai record rồi lỗi; kiểm tra stream có `stream-error` frame và không gửi `complete`.

**Bài 8 – Cancel.** Client hủy sau record đầu; xác nhận service nhận `CANCEL`, DB cursor/listener được đóng.

**Bài 9 – Slow consumer.** Giảm tốc độ client, làm producer nhanh hơn; xác nhận queue bounded và overflow policy có hiệu lực.

**Bài 10 – Durable job.** Cho job tiếp tục sau khi HTTP disconnect; lưu event sequence và replay khi client reconnect.

**Bài 11 – Proxy buffering.** Bật rồi tắt Nginx buffering; đo time-to-first-event và inter-event latency.

**Bài 12 – Connection quota.** Mở nhiều stream đồng thời; kiểm tra per-user limit, idle timeout và metric cardinality.

## 20. Tài liệu tham khảo chính thức

1. Spring Framework – Reactive WebFlux Core, streaming media types, flush, heartbeat và DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
2. Spring Framework – Controller response body và reactive return values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
3. Spring Framework – `ServerSentEvent` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerSentEvent.html
4. Spring Framework – WebTestClient và kiểm thử streaming với `FluxExchangeResult`/`StepVerifier`: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
5. WHATWG HTML Living Standard – Server-sent events, EventSource, Last-Event-ID và event framing: https://html.spec.whatwg.org/dev/server-sent-events.html
6. MDN – Using server-sent events, reconnect, event names và heartbeat: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
7. NDJSON specification – UTF-8, newline delimiter và `application/x-ndjson`: https://github.com/ndjson/ndjson-spec
8. RFC 8259 – JSON Data Interchange Format: https://www.rfc-editor.org/rfc/rfc8259
9. Reactor Reference – Backpressure, cancellation và lifecycle: https://projectreactor.io/docs/core/release/reference/
10. Spring Boot 4.0 – WebFlux và dependency management: https://docs.spring.io/spring-boot/4.0/reference/web/reactive.html

**Tự đánh giá cuối:** Vì sao `Flux<T>` với `application/json` không tự có framing NDJSON? Client phải làm gì khi network chunk chỉ chứa nửa JSON record? SSE event được dispatch ở delimiter nào? `Last-Event-ID` có tác dụng gì nếu server không replay? Vì sao `retry` không đảm bảo exactly-once? Khi response đã commit, vì sao không thể đổi status sang 500? Client disconnect có nên hủy một job durable không? Nếu bạn trả lời được và chạy được hai endpoint cùng các test reconnect/cancel/error, bạn đã nắm được protocol và vòng đời của NDJSON/SSE trong Spring WebFlux.
