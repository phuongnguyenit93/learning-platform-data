# SSE với Flux và ServerSentEvent trong Spring WebFlux

## 1. Tình huống và mục tiêu

Một dashboard muốn hiện thông báo tức thời khi đơn hàng thay đổi; một trang quản trị muốn hiển thị log, tiến độ job, giá chứng khoán hoặc trạng thái tác vụ mà không phải gửi `GET` lặp lại mỗi giây. **Server-Sent Events (SSE)** là cơ chế HTTP cho phép server **đẩy một dòng sự kiện một chiều** đến client thông qua kết nối response mở lâu. Trong Spring WebFlux, bạn có thể trả **`Flux<T>`** với `produces = text/event-stream`, hoặc trả **`Flux<ServerSentEvent<T>>`** để kiểm soát `id`, `event`, `retry`, `comment` và `data`.

Bài học này đi từ giao thức SSE đến vận hành thực tế với **Java 17+, Spring Framework 6.x và Spring Boot 3.x**. Học xong bạn sẽ:

1. Đọc đúng `text/event-stream` gồm `data:`, `id:`, `event:`, `retry:`, dòng chú thích `:` và dòng trống kết thúc event.
2. Giải thích `Flux<ServerSentEvent<T>>` và cơ chế **non-blocking HTTP response streaming** trong Spring WebFlux; phân biệt với `Mono<T>`, JSON response thông thường và MVC `SseEmitter`.
3. Tạo controller SSE hữu hạn/dài hạn, đặt event ID, named events, event data, retry delay và heartbeat.
4. Kết nối từ browser bằng **`EventSource`**, xử lý named events, `onerror`, `readyState`, tự động reconnect và `close()`.
5. Hiểu **`Last-Event-ID`**, replay checkpoint, ordering, at-least-once/duplicate/out-of-order caveats; biết SSE **không tự có event log bền vững**.
6. Phân biệt `Flux.interval` per-client cold publisher với hot shared source (`Sinks.Many`), và quản lý backpressure, slow consumers, memory, cancellation.
7. Cấu hình reverse proxy, timeout, keep-alive, CORS/cookies, authorization, content security và giới hạn kết nối.
8. Chạy một ứng dụng Spring Boot WebFlux có endpoint `/api/events/history` và `/api/events/ticks`, trang web EventSource và kiểm thử HTTP với `WebTestClient`.
9. Biết khi nào nên chọn SSE, WebSocket, polling hoặc message broker.

**Phạm vi:** WebFlux reactive stack (không cần `spring-boot-starter-web`). Ví dụ dùng EventSource của browser và endpoint GET; không hứa delivery chính xác một lần hoặc durable replay nếu không có backing event store. Các đoạn gắn nhãn “minh họa” cần phụ thuộc bên ngoài trước khi dùng, còn nhóm file ở mục 11 là ví dụ thực hành độc lập khi đặt vào dự án Maven Spring Boot 3.x có dependencies đã liệt kê.

## 2. SSE là gì? Vì sao vẫn là HTTP?

SSE sử dụng một **HTTP GET** thông thường, với response:

~~~http
GET /api/events/history HTTP/1.1
Host: localhost:8080
Accept: text/event-stream
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream;charset=UTF-8
Cache-Control: no-cache

id: 1
event: news
retry: 2000
data: news-1

id: 2
event: news
retry: 2000
data: news-2

~~~

Sau headers là các dòng UTF-8. **Một dòng trống** phân cách hai events. Server có thể tiếp tục ghi event tiếp theo mà không kết thúc response. Khác với polling, client không phải tạo request mới cho từng update; khác với WebSocket, client và server không trao đổi các message hai chiều trên cùng một kênh SSE.

SSE không có một “TCP protocol mới”: nó chạy trên HTTP, dùng những proxy/firewall/observability HTTP thông thường nhưng vẫn chịu ảnh hưởng của HTTP response buffering, idle timeout và connection limits.

### SSE một chiều

| Nhu cầu | SSE | WebSocket | Polling |
| --- | --- | --- | --- |
| Server liên tục đẩy cập nhật | Rất phù hợp | Phù hợp | Có thể nhưng tốn requests |
| Client gửi thông điệp realtime cùng kết nối | Không | Có | Tạo HTTP request riêng |
| Browser API đơn giản | `EventSource` | `WebSocket` | `fetch`/XHR |
| Reconnect mặc định trên browser | Có, với quy tắc EventSource | App tự thiết kế | App tự lập lịch |
| Chuẩn hóa event ID/retry | Có các field SSE | App tự định nghĩa | App tự định nghĩa |
| Mỗi luồng tương ứng HTTP GET | Có | Handshake/connection riêng | Có nhiều GET |
| Đảm bảo durable replay | Không tự có | Không tự có | Phụ thuộc server |
| Truyền binary trực tiếp theo protocol | Không (UTF-8 text) | Có binary frames | HTTP hỗ trợ binary |

Nếu ứng dụng cần gửi cursor/input/actions lên server, vẫn có thể **POST qua HTTP endpoint khác** trong khi EventSource nhận notifications qua GET. Nếu client phải gửi nhiều messages realtime liên tục và server phản hồi tương ứng, hãy cân nhắc WebSocket.

## 3. Định dạng wire-level `text/event-stream`

Theo tiêu chuẩn SSE và tài liệu MDN, stream phải được encode UTF-8. Mỗi event gồm những **dòng có cấu trúc**, kết thúc bởi **một dòng trống**. Các trường quan trọng:

| Field | Vai trò | Lưu ý |
| --- | --- | --- |
| `data: ...` | Nội dung event | Nhiều dòng data được nối bằng ký tự newline |
| `event: news` | Loại/named event | Browser dùng `addEventListener("news", handler)` |
| `id: 42` | Event ID | Browser ghi nhớ để có thể gửi `Last-Event-ID` khi reconnect |
| `retry: 3000` | Gợi ý thời gian reconnect **mili giây** | Chỉ số nguyên hợp lệ; không phải thời gian timeout của server |
| `: comment` | Chú thích | Không dispatch message, phù hợp heartbeat |
| Dòng trống | Kết thúc event | Nếu thiếu, client có thể chưa dispatch event |

Một event không có `event:` được xử lý thành **`message` event**; browser gán handler qua `onmessage` hoặc `addEventListener("message", ...)`. Nếu có `event: news`, nó trở thành named event **`news`**, và **không** tự gọi `onmessage` cho cùng event đó.

### 3.1. Một event có nhiều dòng data

~~~text
event: notice
id: 17
data: line one
data: line two

~~~

Browser nhận `event.data` tương đương:

~~~text
line one
line two
~~~

Dòng cuối cùng trống chỉ để kết thúc event; không nằm trong nội dung. Việc chứa các dấu xuống dòng trong data do encoder/server phải serialize đúng, không tự nối raw user input vào wire format.

### 3.2. `id` và `retry`

~~~text
id: 18
retry: 5000
data: pending

~~~

Browser có thể nhớ ID **18** và dùng reconnect time **5000 ms**. Tuy nhiên `retry` không phải heartbeat interval, cũng không phải guarantee server sẽ phát đúng ID 19. Event IDs phải được thiết kế cùng storage/replay semantics.

`id:` rỗng có ngữ nghĩa **xóa last-event-id** trong chuẩn EventSource. Không chủ ý phát ID rỗng khi bạn cần cơ chế khôi phục cursor.

### 3.3. Comment-only heartbeat

~~~text
: keep-alive

~~~

Dòng bắt đầu bằng `:` là comment và không tạo message thông thường, nhưng giúp **gửi bytes định kỳ** để phát hiện disconnect hoặc tránh một số idle timeouts. Heartbeat phải thực sự được flush qua server/proxy; nếu nginx/gateway đệm toàn response rồi mới gửi thì client vẫn không nhận.

### 3.4. Đừng tự nối dữ liệu không tin cậy thành event frame

Sai:

~~~java
String raw = "data: " + untrustedInput + "\n\n";
~~~

Nếu input chứa newline và `event:`, `id:` giả, bạn có thể làm thay đổi SSE framing. Dùng `ServerSentEvent.builder().data(...)` hoặc codec được cấu hình đúng để serialize. Khi nội dung là JSON, dùng DTO/JSON encoder và đảm bảo client render an toàn.

## 4. Spring WebFlux phát SSE bằng Flux

Một controller minh họa:

~~~java
@RestController
class DemoSseController {

    @GetMapping(path="/updates",
            produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<String> updates() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(index -> "update-" + index);
    }
}
~~~

Đây là class **minh họa** cần imports và Boot WebFlux project. WebFlux subscribe vào Publisher, encode mỗi string thành SSE `data:` và gửi dần thay vì chờ Flux complete. Dùng `produces=text/event-stream` rất quan trọng khi không sử dụng wrapper `ServerSentEvent`.

Với wrapper chuyên dụng:

~~~java
@GetMapping(path="/events",
        produces=MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .id(Long.toString(i))
                    .event("tick")
                    .retry(Duration.ofSeconds(3))
                    .data("tick-" + i)
                    .build());
}
~~~

Snippet trên là **method minh họa trong WebFlux controller**, không phải project độc lập. `ServerSentEvent` nằm ở **`org.springframework.http.codec.ServerSentEvent`**; sử dụng fluent builder: `id`, `event`, `retry(Duration)`, `comment`, `data`, `build`.

Nếu client browser dùng `source.onmessage = ...` mà server phát `event("tick")`, handler `onmessage` sẽ **không** bắt named event; phải `source.addEventListener("tick", ...)`.

### 4.1. `Flux` hữu hạn và vô hạn

- `Flux.range(1, 5)` có 5 items và hoàn tất; phù hợp demo/history/test.
- `Flux.interval(Duration.ofSeconds(1))` là chuỗi tick không có end theo mặc định, tiếp tục cho đến khi cancel/disconnect hoặc server stop.
- `Flux.interval(...).take(3)` phát đúng ba tick, rồi complete; phù hợp test deterministic về số items.
- Khi server kết thúc stream hữu hạn, browser `EventSource` thường **tự reconnect**, vì kết thúc kết nối có thể được hiểu là sự cố; với stream hữu hạn, client nên **`close()`** khi đã nhận đủ phần tử.
- Một Flux vô hạn không tự đồng nghĩa server có durable event log; khi client mất mạng, các events giữa hai lần kết nối có thể bị mất.

### 4.2. Không gọi `block()` hay `subscribe()` trong handler

Sai:

~~~java
@GetMapping("/wrong")
String wrong() {
    return remoteService.load().block();
}
~~~

Trên Reactor Netty event-loop, `.block()` có thể ném `IllegalStateException` hoặc gây blocking làm giảm throughput. `subscribe()` riêng trong controller khiến framework không quản lý được lifecycle/cancellation của task. Đúng là **return `Flux`/ `Mono` đã compose** để WebFlux subscribe.

Nếu source là thư viện blocking, có thể cần `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; đó là cơ chế **offload**, không biến JDBC/file SDK blocking thành API non-blocking. Giới hạn tasks/queue/downstream connection pool vẫn bắt buộc.

## 5. EventSource của browser

Trong browser:

~~~javascript
const source = new EventSource("/api/events/history");

source.addEventListener("news", (event) => {
  console.log("ID:", event.lastEventId);
  console.log("Data:", event.data);
});

source.onerror = (event) => {
  console.warn("SSE disconnected or failed", source.readyState);
};

// Gọi khi không còn cần theo dõi:
source.close();
~~~

Điểm cần hiểu:

- `EventSource(url)` mở HTTP **GET**. JavaScript **không** tự chọn POST, `Content-Type` request body hoặc binary frames.
- Browser có thể tự reconnect khi kết nối hỏng hoặc server đóng, theo thuật toán EventSource.
- `event.lastEventId` cho biết last event ID liên quan event được dispatch.
- `source.readyState`: `0=CONNECTING`, `1=OPEN`, `2=CLOSED`. `onerror` không luôn có nghĩa stream chấm dứt vĩnh viễn.
- `close()` đóng kết nối và chặn reconnect. Nên dùng trong component unmount, tab/page navigation hoặc khi nhận event terminal.
- EventSource tiêu chuẩn **không cho tùy ý thêm custom HTTP headers** vào request từ constructor, ví dụ `Authorization: Bearer ...`. Với bearer-token auth, có thể cần một phương án khác (same-origin cookie với CSRF/CORS policy, `fetch` streaming parser, hoặc ticket ngắn hạn) và thiết kế bảo mật phù hợp.
- Có thể dùng `new EventSource(url, { withCredentials: true })` trong những trường hợp CORS credentialed requests được phép và cookies đáp ứng SameSite/Secure. Không dùng `Access-Control-Allow-Origin: *` cùng credentials.

### 5.1. Named events khác `onmessage`

Server:

~~~text
event: progress
data: 25

event: progress
data: 50

event: done
data: finished

~~~

Browser:

~~~javascript
source.addEventListener("progress", (e) => {
  console.log("Progress:", e.data);
});
source.addEventListener("done", () => source.close());
~~~

Không đợi `onmessage` nhận event `progress`. Nếu muốn một handler chung, bạn phải subscribe đến những names phù hợp hoặc phát mặc định không có trường `event:`.

### 5.2. Render event data an toàn

Không làm:

~~~javascript
result.innerHTML = event.data;
~~~

Nếu server phản ánh user input trong event.data mà không sanitize, HTML injection có thể thành XSS. Với text messages:

~~~javascript
result.textContent = event.data;
~~~

Với JSON, parse bằng `JSON.parse(e.data)`, validate schema/type/limits rồi render từng giá trị qua `textContent` hoặc framework escaping. EventSource không thay chính sách CSP, authentication, authorization hoặc output encoding theo ngữ cảnh.

## 6. Last-Event-ID, resume và ngữ nghĩa delivery

Khi server gửi:

~~~text
id: 102
event: news
data: updated

~~~

Browser theo thuật toán EventSource có thể nhớ `102`. Nếu kết nối bị ngắt, request mới thường có:

~~~http
GET /api/events/history HTTP/1.1
Accept: text/event-stream
Last-Event-ID: 102
~~~

**Nhưng giao thức chỉ cung cấp cursor**, không tự lưu events 103, 104, 105 tại server. Muốn resume đúng, server phải có **nguồn replay đáng tin** và hiểu ID:
- Append-only database/event log (có retention).
- Kafka partition/topic theo key và offset tương ứng với consumer contract.
- Redis Streams có stream IDs và retention chính sách.
- Event store với global/per-user sequence numbers và khả năng truy vấn `WHERE id > lastId`.

Nếu server chỉ dùng `Flux.interval` tạo dữ liệu mới theo từng subscriber, ID `0,1,2` của connection A **không có nghĩa** connection B có thể lấy lại phần thiếu từ A. Không dùng timer indexes làm global durable event IDs.

### 6.1. Replay phải xử lý duplicates và gaps

Giả sử client nhận và hiển thị event #42 nhưng chưa kịp persist việc xử lý trước khi ngắt. Khi reconnect, server có thể gửi lại #42 hoặc #43 tùy thời điểm ID được browser cập nhật/đồng bộ. Điều này đòi hỏi:
- Event IDs ổn định và có ý nghĩa trong domain/stream scope.
- Client xử lý **idempotent**, hoặc bỏ qua ID đã thấy theo chính sách.
- Server xác định rõ **exclusive resume** (thường `id > Last-Event-ID`) hay inclusive semantics.
- Xử lý **cursor quá cũ** (đã vượt retention): yêu cầu full resync/snapshot hoặc báo lỗi API có chủ đích.
- **Phân quyền khi replay**: ID của tenant A không được khiến tenant B đọc event A.
- Không hứa “exactly-once” nếu chưa có transaction/idempotency/state acknowledgement thực.
- Khi nhiều partitions/users, ordering chỉ có thể bảo đảm trong một key/partition/stream mà app định nghĩa, không mặc định global.

### 6.2. Ví dụ logic DB, không phải controller runnable

~~~java
Flux<Notification> replayAfter(String principalId, long lastSeenId) {
    return notificationRepository
            .findAuthorizedAfter(principalId, lastSeenId);
}
~~~

Đây là đoạn mô hình nghiệp vụ, phụ thuộc reactive repository thật. Query phải lọc authorization/tenant, order theo sequence đáng tin và giới hạn batch/read timeout. Nếu cần **kết hợp replay với live stream**, phải tránh race “sau khi query xong nhưng trước khi subscribe live” bằng cursor + atomic subscribe/snapshot hoặc thiết kế event log như nguồn duy nhất. `Flux.concat(replay, live)` đơn giản có thể bỏ lỡ sự kiện trong khe nối nếu không có cơ chế đồng bộ.

## 7. Heartbeat, flush và phát hiện disconnect

SSE là kết nối thường mở lâu. Các tầng có thể đóng connection nếu lâu không có dữ liệu:
- Load balancer idle timeout.
- CDN/reverse proxy response timeout.
- NAT hoặc intermediaries.
- Browser/mobile network mất kết nối.
- Container/server write error khi client đã rời.

Theo Spring WebFlux reference, khi streaming nên phát dữ liệu định kỳ để **phát hiện client đã disconnect sớm hơn**. Heartbeat SSE dưới dạng comment:

~~~java
Flux<ServerSentEvent<String>> heartbeats =
        Flux.interval(Duration.ofSeconds(15))
                .map(i -> ServerSentEvent.<String>builder()
                        .comment("keep-alive")
                        .build());
~~~

Đoạn trên là snippet dùng Reactor, không phải controller độc lập. Khi merge với notifications, nên dùng một publisher có heartbeat và một nguồn notifications:

~~~java
Flux<ServerSentEvent<String>> stream =
        Flux.merge(notifications, heartbeats);
~~~

Giả sử `notifications` là publisher thực được khai báo. Không dùng `heartbeats` như một cơ chế lặp event nghiệp vụ: comment-only event không được dispatch như `message` trong browser. Heartbeat là giao thức kiểm tra kết nối; khi producer lâu không có event, gửi comment nhỏ sẽ hữu ích hơn giữ im lặng hàng phút.

**Lưu ý cấu hình thực tế:** đặt heartbeat 15–30 giây chỉ là ví dụ; cần đảm bảo nhỏ hơn idle timeout thực tế ở toàn đường HTTP, đủ phù hợp bandwidth/connection costs. Nếu proxy buffer dữ liệu, heartbeat phải được forward/flush, không chỉ được tạo trong Reactor pipeline.

## 8. Cold Flux và hot publisher: một kết nối hay nhiều subscribers?

### 8.1. `Flux.interval` thường có chuỗi riêng mỗi subscription

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
~~~

Khi mỗi client subscribe, `Flux.interval` tạo timer sequence theo subscription; nhiều clients có thể thấy `0,1,2,...` riêng. Điều này tốt cho demo/timers per-client nhưng không thể biểu diễn shared business updates với một global monotonic ID.

Nếu có 10.000 EventSource clients, 10.000 per-client intervals/subscriptions vẫn có chi phí scheduling và connection management, dù không giữ 10.000 blocking Servlet threads. Kiểm soát global connection limits và broadcast architecture.

### 8.2. `Sinks.Many` cho hot source

Một mẫu minh họa trong Spring service:

~~~java
@Service
class NewsHub {

    private final Sinks.Many<String> sink =
            Sinks.many().multicast().directBestEffort();

    public Flux<String> events() {
        return sink.asFlux();
    }

    public boolean publish(String message) {
        Sinks.EmitResult result = sink.tryEmitNext(message);
        return result.isSuccess();
    }
}
~~~

Đây là **class minh họa**, cần imports `@Service`, `Sinks`, `Flux` và producer thực. `directBestEffort` không cache history và có thể **bỏ qua subscriber chậm** để subscribers khác còn nhận. `tryEmitNext` có thể trả `FAIL_ZERO_SUBSCRIBER`, `FAIL_OVERFLOW`, `FAIL_NON_SERIALIZED` hoặc trạng thái khác; không gán `publish=true` là đã ghi bền vững.

Nếu nhiều producers phát vào cùng sink đồng thời, cơ chế `Sinks` kiểm tra concurrent emission và có thể từ chối non-serialized signals. Hãy serialize producers hoặc xử lý `EmitResult` có metric/retry bounded theo policy, không spin vô hạn trên event loop.

### 8.3. Những loại sink khác nhau

| Sinks.Many | Ý nghĩa | Trade-off |
| --- | --- | --- |
| `multicast().directBestEffort()` | Best effort, subscriber chậm có thể mất item | Không dành cho durable/reliable delivery |
| `multicast().directAllOrNothing()` | Nếu một subscriber không có demand, event có thể bị bỏ cho tất cả | Một slow consumer ảnh hưởng cả nhóm |
| `multicast().onBackpressureBuffer()` | Có buffer và demand coordination | Cần chọn bounded size, overflow policy, tránh slow subscriber làm nghẽn |
| `replay().limit(n)` | Replay được một số gần nhất cho late subscribers | Chỉ cache in-memory, reset khi restart, chưa durable |
| Event log DB/Kafka/Redis Streams | Truy vấn durable history theo cursor | Thêm storage/retention/authorization/ordering complexity |

Một **sink là source phát events**, không phải cơ sở dữ liệu. Hệ thống nhiều pods không tự thấy cùng events chỉ vì mỗi pod tạo sink singleton; cần broker/stream distribution hoặc sticky routing hợp lệ.

## 9. Backpressure và slow clients trong SSE

Reactive Streams có backpressure: downstream yêu cầu `request(n)`, upstream theo khả năng sẽ sản xuất có kiểm soát. Nhưng **HTTP SSE/EventSource không có per-event business acknowledgement**. Khi browser đọc chậm hoặc TCP buffers đầy, backpressure có thể xuất hiện tại HTTP output/writer, còn event log upstream hoặc producer bên ngoài vẫn có thể phát liên tục.

Các vấn đề cần đánh giá:

- Mỗi SSE client là một connection lâu dài, có network/file-descriptor/memory overhead.
- Client dùng mobile network hoặc tab bị background throttle có thể đọc chậm.
- Nếu queue per-client không giới hạn, memory sẽ tăng theo số client × lag.
- Nếu drop events, downstream có thể bị **gaps theo id**; client phải detect/resync.
- Nếu terminate slow client, browser tự reconnect tạo **reconnect storm** nếu không có backoff/rate control.
- Nếu một shared sink buffer chịu áp lực bởi subscriber chậm, **tất cả** subscribers có thể bị ảnh hưởng.
- Nếu producer publish các events chưa persist nhưng SSE connection đứt, các events có thể mất khi không có durable store.

### Operator patterns

~~~java
Flux<ServerSentEvent<String>> result =
        source.onBackpressureLatest()
              .map(v -> ServerSentEvent.<String>builder(v).build());
~~~

Đây là snippet có `source` là publisher thực. `onBackpressureLatest` có thể bỏ intermediate values, chỉ phù hợp khi **chỉ cần state mới nhất** như nhiệt độ/giá hiển thị, **không** phù hợp với giao dịch thanh toán hoặc các events không được mất. Không chọn drop/overflow policy chỉ vì nó giúp dashboard “mượt”.

Nếu cần mọi event có thể replay: dùng durable log và cursor, phát có giới hạn khi client có demand. Nếu không thể đáp ứng, chủ động đóng stream hoặc gửi signal cần resync, không giữ queue vô hạn.

## 10. Security, cookies, CORS và reverse proxy

### 10.1. Authorization cho HTTP GET đang mở lâu

SSE thường là GET, nhưng URL có thể lộ dữ liệu nhạy cảm. Quy tắc:
1. Xác thực và phân quyền **trước** subscribe vào nguồn events.
2. Với replay, kiểm tra quyền **theo từng event/tenant** hoặc enforce query đúng scope, không chỉ check `Last-Event-ID`.
3. Không để event IDs chứa secret/token hay PII nếu không cần; `id` có thể xuất hiện trong logs/headers.
4. Nếu quyền bị thu hồi trong khi kết nối vẫn mở, thiết kế re-evaluation/forced disconnect và revoke subscription.
5. Không dùng một singleton `Sinks.Many<UserMessage>` rồi broadcast mọi tin của mọi user cho toàn bộ listeners mà không filter quyền.
6. Tránh đưa bearer token vào URL query string vì URLs dễ bị log/lộ qua analytics/referrer/history. EventSource không hỗ trợ custom auth headers chuẩn; chọn cookie/session hoặc design thay thế cẩn trọng.

### 10.2. CORS và credentialed EventSource

~~~javascript
const source = new EventSource(
  "https://api.example.com/api/events/ticks",
  { withCredentials: true }
);
~~~

Đây là **ví dụ URL minh họa**, không hoạt động với local demo nếu chưa cấu hình CORS/HTTPS. Backend phải cho phép cụ thể `Origin`, credentials và cookie policy hợp lệ. Không thiết lập `Access-Control-Allow-Origin: *` khi request dùng credentials; giải quyết `SameSite`, `Secure`, HTTPS và CSRF policy theo threat model.

SSE chỉ là server → browser channel. Nếu trang dùng POST riêng để tạo công việc, POST có cookie auth cần CSRF protection như mọi unsafe request thông thường.

### 10.3. Proxy buffering và idle timeout

Một vài reverse proxies/CDNs có thể đệm HTTP response. Dù server đã emit event, browser không nhận gì cho đến khi buffer đầy hoặc connection đóng. Cần xác minh và cấu hình riêng từng tầng:
- Content-Type đúng **`text/event-stream; charset=UTF-8`**.
- Disable response buffering cho SSE route ở proxy nếu cần (ví dụ một số cấu hình nginx có `proxy_buffering off`; header `X-Accel-Buffering: no` chỉ có tác dụng ở các tầng thực sự hỗ trợ).
- Idle timeout **lớn hơn heartbeat interval**; kiểm tra ingress, LB, CDN, app server và mobile carriers.
- Streaming flush thực sự tới client; không áp compression/buffering theo cách gộp nhiều events gây delay.
- `Cache-Control: no-cache` hoặc policy phù hợp để tránh cache/intermediary dùng lại một response stream không đúng. Đây không phải `no-store` và không giải quyết auth/caching riêng.
- Connection limits/HTTP/2 multiplexing: HTTP/1.1 browser thường giới hạn số kết nối song song trên cùng origin, nhiều tab EventSource có thể cạnh tranh connection slots; HTTP/2 có concurrent streams negotiated khác. Không coi HTTP/2 là vô hạn streams.
- Observability: đo bytes/second, concurrent SSE connections, drop/reconnect rate, response status, disconnect cause.

Không giả định `Flux<ServerSentEvent>` tự sửa cấu hình gateway hoặc giúp proxy stream events nếu tầng proxy bật buffering.

## 11. Ví dụ Spring Boot 3.x + Java 17 chạy được

Để học protocol/replay mà không phụ thuộc DB/message broker, ứng dụng thực hành dùng **danh sách sự kiện 1..5 cố định**. Controller cung cấp:

- `GET /api/events/history`: `Flux<ServerSentEvent<String>>` hữu hạn. Với `Last-Event-ID`, trả các events có ID lớn hơn ID đã nhận. Đây **chỉ là in-memory lesson dataset**; nếu deployment restart nhưng data thay đổi, code này không còn chứng minh durable replay.
- `GET /api/events/ticks`: `Flux<ServerSentEvent<String>>` chạy 1 giây/lần, phát event tên `tick`. Đây là timer **per subscription** và không hứa global sequence/replay.
- `GET /` phục vụ file HTML tĩnh với `EventSource` kết nối tới history/ticks.
- `WebTestClient` integration tests trên server HTTP thật, assert named event ID/data, Last-Event-ID và validation.
- Không dùng security, Redis, Kafka, reverse proxy hay DB, vì mục đích là hiểu SSE wire/lifecycle một cách xác định được.

### 11.1. Tạo project

Spring Initializr: Maven, Java 17+, Spring Boot **3.x**, dependency `Spring Reactive Web` (artifact `spring-boot-starter-webflux`), và `Spring Boot Starter Test`.

Snippet trong `pom.xml` được Spring Initializr sinh ra:

~~~xml
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
~~~

Đây là **đoạn dependencies**, chưa phải file Maven đầy đủ (parent/BOM/compiler/spring-boot-maven-plugin đã nằm trong skeleton do Initializr tạo). Đừng thêm `spring-boot-starter-web` vì Boot 3.x thường chọn Spring MVC nếu MVC và WebFlux đều có trên classpath.

Cấu trúc files:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  NewsEventsController.java
src/main/resources/static/
  index.html
src/test/java/com/example/demo/
  NewsEventsControllerTest.java
~~~

### 11.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.3. NewsEventsController.java

~~~java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/events")
public class NewsEventsController {

    private static final int LAST_DEMO_ID = 5;

    @GetMapping(path = "/history",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> history(
            @RequestHeader(name = "Last-Event-ID",
                    required = false) String lastEventId) {

        int afterId = parseCursor(lastEventId);

        return Flux.range(afterId + 1, LAST_DEMO_ID - afterId)
                .delayElements(Duration.ofMillis(60))
                .map(id -> ServerSentEvent.<String>builder()
                        .id(Integer.toString(id))
                        .event("news")
                        .retry(Duration.ofSeconds(2))
                        .data("news-" + id)
                        .build());
    }

    @GetMapping(path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {

        return Flux.interval(Duration.ofSeconds(1))
                .map(index -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .comment("per-subscriber demo timer")
                        .data("tick-" + index)
                        .build());
    }

    private static int parseCursor(String value) {
        if (value == null || value.isBlank()) {
            return 0;
        }
        try {
            int id = Integer.parseInt(value);
            if (id >= 0 && id <= LAST_DEMO_ID) {
                return id;
            }
        } catch (NumberFormatException ignored) {
            // Return 400 below for malformed or non-numeric IDs.
        }
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid Last-Event-ID");
    }
}
~~~

**Phân tích từng bước:**

1. `history` nhận `Last-Event-ID` là **HTTP request header** tùy chọn. Nếu vắng, coi như `0` trong dataset này; giá trị không phải integer 0..5 bị từ chối **400**.
2. `Flux.range(afterId+1, 5-afterId)` phát các số nguyên từ ID tiếp theo tới 5. Với `Last-Event-ID: 3`, nó phát **4,5**; với 5 thì phát Flux rỗng.
3. `delayElements(60ms)` chỉ để cho curl/browser thấy streaming qua thời gian; nó không mô phỏng durable queue. Test có thể chờ đến 5 seconds.
4. `ServerSentEvent.<String>builder().id(...).event("news").retry(...).data(...).build()` tạo đúng frame có ID, named event và data.
5. `ticks` là infinite cold timer per subscription, không cung cấp IDs bởi những index mỗi subscriber không phải global log cursor.
6. Controller **không** tự subscribe; WebFlux quản lý subscribe, write và cancel khi connection kết thúc.
7. `parseCursor` giới hạn dữ liệu đầu vào, không cho một header tùy ý làm thay đổi scope của demo. Production không thể chỉ validate numeric range nếu event log có namespace/authorization/retention phức tạp.
8. Không dùng `Thread.sleep` trong Netty event-loop; Reactor timer scheduling không cần giữ blocked thread cho mỗi tick.
9. Các event data là `String` ngắn và cố định. Với DTO/JSON, `ServerSentEvent<SomeRecord>` hoạt động tương tự nếu codec được cấu hình, nhưng client cần `JSON.parse`.
10. Không xây `Cache-Control`/CORS/security/proxy deployment trong demo này. Phần production cần cấu hình các lớp đó và kiểm thử qua actual ingress.

### 11.4. index.html: browser client

`src/main/resources/static/index.html`

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Spring WebFlux SSE Demo</title>
</head>
<body>
  <h1>Thông báo SSE</h1>
  <p id="state">Chưa kết nối</p>
  <ul id="news"></ul>
  <button id="startTicks">Mở live ticks</button>
  <button id="stopTicks">Đóng live ticks</button>
  <ul id="ticks"></ul>

  <script>
    const state = document.getElementById("state");
    const news = document.getElementById("news");
    const ticks = document.getElementById("ticks");

    // Stream hữu hạn; tự đóng ở event ID 5 để ngăn reconnect loop.
    const history = new EventSource("/api/events/history");

    history.onopen = () => {
      state.textContent = "Đang nhận lịch sử";
    };
    history.addEventListener("news", event => {
      const li = document.createElement("li");
      li.textContent = event.lastEventId + ": " + event.data;
      news.appendChild(li);

      if (event.lastEventId === "5") {
        history.close();
        state.textContent = "Đã nhận đủ năm sự kiện";
      }
    });
    history.onerror = () => {
      if (history.readyState !== EventSource.CLOSED) {
        state.textContent = "Mất kết nối, browser có thể thử lại";
      }
    };

    let live = null;
    document.getElementById("startTicks").onclick = () => {
      if (live !== null) return;

      live = new EventSource("/api/events/ticks");
      live.addEventListener("tick", event => {
        const li = document.createElement("li");
        li.textContent = event.data; // không dùng innerHTML
        ticks.appendChild(li);
      });
      live.onerror = () => {
        // Browser xử lý reconnect; log/observe nếu cần.
        console.warn("tick stream disconnected");
      };
    };
    document.getElementById("stopTicks").onclick = () => {
      if (live !== null) {
        live.close();
        live = null;
      }
    };
    window.addEventListener("beforeunload", () => {
      history.close();
      if (live !== null) live.close();
    });
  </script>
</body>
</html>
~~~

**Điểm thiết kế:**
- Khi đã nhận ID cuối `5`, code **`history.close()`** vì endpoint history hữu hạn. Nếu không, EventSource có thể reconnect sau khi server hoàn thành.
- `tick` là named event nên phải dùng `addEventListener("tick", ...)`.
- `textContent` tránh đưa dữ liệu SSE trực tiếp vào HTML parser; nếu hiển thị rich HTML phải sanitize và tuân output encoding/CSP.
- `stopTicks` đóng subscription/kết nối, giúp giải phóng tài nguyên browser/server sớm hơn.
- Code `live` không chống rendering hàng triệu `li` nếu để mở nhiều giờ; production cần **giới hạn số items hiển thị** hoặc virtualized list. UI memory cũng là thành phần cần giám sát.
- Không xem một EventSource nối lại là bảo đảm server đã phát lại mọi dữ liệu thiếu; demo history chỉ replay năm IDs cố định.

### 11.5. NewsEventsControllerTest.java

Các test dùng **WebTestClient** qua embedded HTTP server để đọc stream hữu hạn thành typed `ServerSentEvent<String>`. Không kết nối `ticks` vô hạn và cố đợi nó `complete`.

~~~java
package com.example.demo;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NewsEventsControllerTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void emitsFiveNamedEventsWithIdsAndRetry() {
        List<ServerSentEvent<String>> received =
                client.get()
                        .uri("/api/events/history")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().contentTypeCompatibleWith(
                                MediaType.TEXT_EVENT_STREAM)
                        .returnResult(
                            new ParameterizedTypeReference<
                                ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(received);
        assertEquals(5, received.size());

        ServerSentEvent<String> first = received.get(0);
        assertEquals("1", first.id());
        assertEquals("news", first.event());
        assertEquals("news-1", first.data());
        assertEquals(Duration.ofSeconds(2), first.retry());

        ServerSentEvent<String> last = received.get(4);
        assertEquals("5", last.id());
        assertEquals("news-5", last.data());
    }

    @Test
    void lastEventIdRequestsOnlyEventsAfterCursor() {
        List<ServerSentEvent<String>> received =
                client.get()
                        .uri("/api/events/history")
                        .header("Last-Event-ID", "3")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .returnResult(
                            new ParameterizedTypeReference<
                                ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(received);
        assertEquals(2, received.size());
        assertEquals("4", received.get(0).id());
        assertEquals("5", received.get(1).id());
    }

    @Test
    void malformedCursorIsBadRequest() {
        client.get()
                .uri("/api/events/history")
                .header("Last-Event-ID", "abc")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void liveTimerProducesEventsWithoutWaitingForCompletion() {
        List<ServerSentEvent<String>> received =
                client.get()
                        .uri("/api/events/ticks")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .returnResult(
                            new ParameterizedTypeReference<
                                ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .take(2)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(received);
        assertEquals(2, received.size());
        assertEquals("tick", received.get(0).event());
        assertEquals("tick-0", received.get(0).data());
        assertEquals("tick-1", received.get(1).data());
    }
}
~~~

Các test nhấn mạnh:
- Khi stream hữu hạn, `collectList()` chỉ complete sau event cuối; cần timeout để tránh test treo nếu code thay đổi thành infinite stream.
- Khi stream vô hạn, **`take(2)` giới hạn dữ liệu và cancel subscription** sau hai items; không gọi `collectList()` trên Flux vô hạn.
- Assert `id`, `event`, `data`, `retry` thay vì dựa vào các đoạn output byte có thể thay đổi whitespace/codec.
- `Last-Event-ID: 3` tạo events 4,5 theo contract demo. Đây là logic replay có dataset cố định chứ chưa là message durability.
- HTTP server dùng random port và client `bindToServer`, khác với test controller trực tiếp; **test này không mô phỏng reverse proxy/CDN**. Test streaming qua ingress thật vẫn cần riêng.
- `.block(Duration)` được dùng **chỉ trong JUnit test thread** để chờ kết quả; không dùng `.block()` trong WebFlux event-loop controller.

Để chạy:
~~~bash
./mvnw test
~~~

Trên Windows:
~~~powershell
.\mvnw.cmd test
~~~

Nếu không có Maven wrapper, dùng `mvn test` với Maven đã cài. Test timeout ở đây là bảo vệ JUnit run, không chứng minh SLA/liveness trên production.

## 12. Thử bằng curl và quan sát wire format

Khởi động ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

Đọc lịch sử:

~~~bash
curl -N -i   -H "Accept: text/event-stream"   http://localhost:8080/api/events/history
~~~

Đầu ra minh họa (bỏ qua những headers khác):

~~~text
id:1
event:news
retry:2000
data:news-1

id:2
event:news
retry:2000
data:news-2

~~~

Codec thực tế có thể có dấu cách sau dấu `:` hoặc thứ tự các fields khác nhưng semantics phải giống nhau. `-N` của curl tắt buffering stdout, giúp nhìn events tới từng đợt. Nếu dùng `curl` không có `-N`, có thể thấy hiển thị bị giữ lại bởi output buffering dù server thực sự stream.

Thử resume:

~~~bash
curl -N -i   -H "Last-Event-ID: 3"   -H "Accept: text/event-stream"   http://localhost:8080/api/events/history
~~~

Kết quả stream có **ID 4 và 5**, không phát lại 1–3. Điều này chỉ đúng do contract của demo.

Xem live ticks:

~~~bash
curl -N -H "Accept: text/event-stream"   http://localhost:8080/api/events/ticks
~~~

Trong terminal, nhấn `Ctrl+C` để chủ động ngắt; phía server nên nhận signal cancellation/connection closed để ngừng subscription. Đừng để test/CLI mở vô hạn rồi kết luận server leak khi connection chưa đóng.

Sai cursor:

~~~bash
curl -i   -H "Last-Event-ID: abc"   http://localhost:8080/api/events/history
~~~

Endpoint trả **400 Bad Request** theo `parseCursor` đã định nghĩa.

**Lưu ý về shell:** ví dụ nhiều dòng dùng dấu `\` dành cho Linux/macOS/Git Bash. Trên Windows PowerShell, dùng `curl.exe` trong một dòng hoặc cú pháp line continuation phù hợp.

## 13. Error handling: trước và sau khi response đã commit

Khi controller trả Publisher, **errors có thể xảy ra**:
1. Trước HTTP response headers: parse `Last-Event-ID` lỗi → có thể trả **400** như API thông thường.
2. Sau khi gửi event thứ 100: response headers đã commit, server không thể tùy ý đổi sang HTTP 500 JSON body mà vẫn giữ cùng response. Kết nối có thể kết thúc/lỗi và browser sẽ reconnect.
3. Trong source `WebClient`/database/message broker: cần phân biệt recoverable vs fatal. Nếu muốn gửi một **application-level error event** và đóng stream, có thể `onErrorResume` sang event `error` theo protocol riêng nhưng không được rò exception stack/credentials ra client.
4. Client disconnect: Reactor subscription thường cancel; source cần release DB cursor, broker subscription và resources qua `doFinally`/`usingWhen` khi cần.

Ví dụ minh họa:

~~~java
return source
        .map(message -> ServerSentEvent.<String>builder()
                .event("news")
                .data(message)
                .build())
        .onErrorResume(ex ->
                Flux.just(ServerSentEvent.<String>builder()
                        .event("stream-error")
                        .data("Temporary stream error")
                        .build()));
~~~

Đây là snippet chưa runnable độc lập vì `source` chưa được khai báo. Sau khi phát `stream-error`, stream thường complete; client phải quyết định resubscribe, UI error hay full resync. **Không** tự gửi `ex.getMessage()` nếu exception có thể chứa nội bộ service/token/PII.

### 13.1. Retry storm

Nếu 5.000 browser clients cùng reconnect sau một outage, tất cả có thể gửi GET lại gần như đồng thời. `retry: 1000` không giải quyết server saturation. Cần:
- Rate limit/admission control ở ingress.
- Server/client policy retry/backoff/jitter khi có quyền điều chỉnh.
- Hạn chế subscription setup nặng.
- Shared event storage và incremental catch-up phù hợp.
- Capacity/load testing với reconnect bursts.
- Không tạo connection pool/tracing objects mới vô hạn cho từng reconnect.

Browser EventSource built-in `retry` không thể biểu diễn tất cả jitter policies phức tạp chỉ qua một field. Nếu yêu cầu chuyên biệt, application-level connection management có thể cần một transport/client khác.

## 14. SSE và transaction/event outbox

Ví dụ: một REST POST tạo đơn hàng trong database, rồi notification được đẩy qua SSE. Nếu code phát event **trước khi DB commit**, browser có thể nhận “order-created” trong khi transaction rollback. Nếu phát **sau commit** nhưng server crash trước publish, event bị mất.

Một kiến trúc đáng tin cậy hơn:

~~~text
HTTP POST /orders
     |
     v
DB transaction: orders row + outbox_event row
     |
     +---- COMMIT
               |
               v
Outbox publisher/broker
               |
               v
Durable event stream
               |
               +---- replay after Last-Event-ID
               |
               v
Authorized SSE subscriptions (per user / tenant)
               |
               v
Browser EventSource
~~~

Outbox xử lý consistency giữa DB changes và notification workflow tốt hơn “save DB rồi fire-and-forget `sink.tryEmitNext`”. Nhưng vẫn phải xử lý duplicate delivery, retention, authorization, crash/restart, message ordering và poison messages.

### Last-Event-ID và DB cursor

Ví dụ SQL giả định có `notification_events(id BIGINT, owner_id, payload)`:

~~~sql
SELECT id, payload
FROM notification_events
WHERE owner_id = :ownerId
  AND id > :lastEventId
ORDER BY id ASC
LIMIT :batchSize;
~~~

Các variables là bind parameters của DB driver, không nối string từ header. Nếu IDs tăng toàn cục và có gaps, truy vấn vẫn trả những events có ID lớn hơn theo thứ tự. `LIMIT` kiểm soát batch memory nhưng server cần lặp tới khi bắt kịp log rồi chuyển live tail **mà không bỏ lỡ khoảng giao nhau**.

Một vài stream IDs từ Kafka/Redis không phải số nguyên tuyến tính một chiều toàn hệ thống. `Last-Event-ID` là chuỗi opaque đối với SSE protocol; ứng dụng có thể đặt cursor dạng composite/versioned token (không chứa secret) và parse theo format riêng.

## 15. Quan sát, tối ưu và giới hạn tài nguyên

Mỗi SSE connection có một thời gian sống dài; HTTP server latency metric cho request có thể bằng **thời gian mở kết nối** chứ không phải latency của từng event. Hãy đo:

| Metric | Dùng để biết |
| --- | --- |
| `sse_connections_active` | Đang có bao nhiêu subscribers/kết nối |
| `sse_subscribe_rate` | Tốc độ kết nối mới/reconnect |
| `sse_disconnections_total` | Client rời, network lỗi, proxy timeout |
| `sse_heartbeat_gap_seconds` | Có gửi/flush heartbeat đúng hạn không |
| `sse_event_lag_ms` | Từ event source timestamp đến lúc client nhận (nếu đo được) |
| `sse_events_dropped_total` | Sink/operator policy làm mất event |
| `sse_replay_requests_total` | Khối lượng reconnect/replay |
| `sse_replay_gap_total` | Cursor quá cũ hoặc missing data |
| JVM heap/direct memory/GC/threads | Sức khỏe server và buffer pressure |
| Gateway/LB concurrent streams/timeouts | Bottleneck tầng ngoài |
| DB/broker consumer lag | Source đã chậm trước khi phát SSE |

Các tên metrics là **gợi ý thiết kế**, không tuyên bố Spring Boot tự xuất đúng chúng mà không instrumentation. `Micrometer`/Actuator có thể thêm để ghi gauges/counters theo ứng dụng; tránh gán label `userId` có cardinality rất cao nếu không cần.

### 15.1. Không giữ toàn bộ events trong memory

~~~java
// ANTI-PATTERN: không có bound rõ cho history.
List<Notification> history = new ArrayList<>();
~~~

Nếu lưu mỗi event vĩnh viễn cho mọi user, heap tăng không giới hạn. Hãy dùng durable store có TTL/retention, pagination/checkpoints; nếu replay in-memory chỉ dùng `replay().limit(n)` với n nhỏ, biết rõ sẽ mất khi restart.

### 15.2. Slow subscribers

Đặt policy trước: events có được phép mất không? Nếu là telemetry mới nhất có thể drop intermediate states. Nếu là audit/payment events, không được silently drop, nên lưu durable log và cho client catch up bằng cursor. Đừng chọn `onBackpressureBuffer` không giới hạn chỉ để tránh lỗi immediate overflow.

### 15.3. Timeouts và heartbeat

Chọn nhịp heartbeat sao cho nhỏ hơn toàn bộ idle timeouts, đồng thời không làm network bùng nổ khi số client cực lớn. Nếu 100.000 clients và heartbeat 15 s, trung bình sẽ có khoảng 6.667 heartbeat writes/second chưa tính event thật; phải đo năng lực server/gateway, không coi comment-only frame là miễn phí.

### 15.4. Graceful shutdown

Khi deploy rolling restart, connections có thể bị ngắt/reconnect. Thiết kế:
- Health/readiness chặn subscriptions mới khi chuẩn bị shutdown.
- Có thời gian drain/close stream phù hợp.
- Browser reconnect sang instance khác mà cursor vẫn hợp lệ trong durable store.
- Logs/metrics nhận diện deliberate shutdown khác outage.
- Không để job/thread/connection từ source tiếp tục hoạt động khi SSE subscription đã cancel.

## 16. Khi nào chọn SSE thay vì WebSocket?

Chọn **SSE** khi:
- Dữ liệu truyền chủ yếu **server → browser**.
- Nội dung là text/JSON notifications; client không cần binary/multiplex custom protocol.
- Muốn browser tự reconnect theo SSE semantics.
- Có thể dùng GET trên HTTP infrastructure sẵn có.
- Không cần client gửi realtime nhiều messages trên cùng connection.

Chọn **WebSocket** khi:
- Cần **full-duplex**: game, chat với input realtime, collaboration, low-latency interactive controls.
- Truyền binary messages theo framing riêng.
- Cần hai chiều nhiều messages trong cùng một persistent channel và sẵn sàng quản lý reconnect/ack/protocol.

Chọn **polling** khi:
- Tải thấp, dữ liệu cập nhật thưa, simplicity/infra compatibility quan trọng hơn realtime.
- Gateways/proxies không hỗ trợ long-lived SSE connections như yêu cầu.
- Client/công nghệ hạn chế EventSource.

Chọn **message broker** như Kafka/Redis Streams khi cần fan-out/durable replay/scale pods; broker là **nguồn/transport nội bộ**, và SSE có thể là **giao diện HTTP ra browser**. Đây không phải hai lựa chọn loại trừ nhau.

## 17. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Client chỉ thấy output sau khi stream đóng | Proxy/HTTP client buffering | `curl -N`, proxy buffering off, heartbeat/flush |
| `onmessage` không chạy | Server phát named `event: news` | `addEventListener("news", ...)` |
| EventSource mở lại nhiều lần khi đã nhận đủ | Flux hữu hạn complete; browser reconnect | Client `close()` ở terminal event |
| Duplicate messages sau reconnect | Replay có thể trùng/cursor update timing | Idempotent client, sequence IDs |
| Mất events khi chuyển pod | In-memory sink/timer không durable | Shared event log + Last-Event-ID |
| Cùng ID nhưng payload khác sau restart | ID không ổn định/global | Stable event IDs thuộc domain/stream |
| Client bị 400 khi reconnect | Header cursor format không hợp lệ/đã đổi | Version cursor parser, resync policy |
| Server không nhận Last-Event-ID như mong đợi | Client chưa từng thấy ID hợp lệ hoặc không dùng EventSource | Inspect request/reconnect headers |
| SSE stream trả Content-Type application/json | Thiếu `produces=text/event-stream` | Khai báo đúng mapping hoặc ServerSentEvent wrapper |
| Client không hiển thị dữ liệu | Named event vs JSON parsing/display logic | Check frames, event names, textContent |
| Kết nối đóng mỗi phút | Gateway idle timeout | Heartbeat nhỏ hơn timeout, config gateway |
| Browser thiếu cookie cross-site | SameSite/CORS credentials | Origin allowlist, Secure cookie, withCredentials |
| Dùng Bearer header được với fetch nhưng EventSource không | EventSource không hỗ trợ custom headers | Cookie hoặc streaming fetch client |
| Tất cả users nhận thông báo user khác | Shared broadcast sink không filter | Per-tenant/user subscriptions + authorization |
| RAM tăng cùng số clients | Unbounded buffer/history/UI list | Bounded queues, retention, cleanup |
| Một client chậm làm nghẽn mọi người | Sink policy có coupling/buffer | directBestEffort hoặc isolated durable fan-out |
| Data events mất khi drop policy | `onBackpressureLatest` bỏ intermediate updates | Durable log cho dữ liệu cần chính xác |
| EventSource gửi lại request sau lỗi | Auto reconnect là behavior chuẩn | Xử lý backoff/rate/close khi terminal |
| `Flux.interval` có ID 0 lại sau reconnect | Per-subscriber timer | Không dùng timer ID làm durable cursor |
| Test `collectList` treo | Flux vô hạn không complete | `take(n)` trước `collectList` |
| SSE bị XSS ở UI | Dùng `innerHTML = event.data` | `textContent`/escaping |
| Server lỗi sau khi đã stream vài events | HTTP headers đã commit | App-level error event + close/reconnect |
| Thống kê latency HTTP lớn | SSE connection kéo dài | Đo per-event lag, connection metrics riêng |

## 18. Câu hỏi ôn tập

**1. SSE có hoạt động theo cả hai chiều không?**  
Không. SSE là luồng response từ server tới client qua HTTP GET; cần request khác để client gửi dữ liệu.

**2. `ServerSentEvent` cho phép đặt những field nào?**  
Các trường chính `id`, `event`, `data`, `retry`, `comment`. `Flux<ServerSentEvent<T>>` phù hợp khi cần điều khiển chúng.

**3. Khi nào dùng `onmessage`, khi nào dùng `addEventListener`?**  
`onmessage` nhận event mặc định không có named `event:`; named events như `event: news` cần `addEventListener("news", ...)`.

**4. Last-Event-ID có tự phát lại các events bị mất không?**  
Không. Nó cung cấp cursor, server phải có durable replay source và logic truy vấn/authorization.

**5. Vì sao browser reconnect sau khi Flux hữu hạn complete?**  
EventSource thường retry khi connection đóng; client nên `close()` khi nhận sự kiện kết thúc có chủ đích.

**6. Heartbeat `: keep-alive` có dispatch message không?**  
Không. Comment frame giúp gửi bytes định kỳ, kiểm tra connection/idle proxy, nhưng không gọi `onmessage`.

**7. `Flux.interval` có phải hot topic chung cho mọi browser không?**  
Không mặc định; mỗi subscription có timer/index riêng. Muốn fan-out dùng shared source/Sinks/broker và thiết kế event IDs.

**8. `directBestEffort` có bảo đảm mọi subscriber nhận đủ dữ liệu không?**  
Không. Subscriber chậm có thể bị bỏ sự kiện, và sink không persist history.

**9. SSE có đảm bảo exactly-once delivery không?**  
Không. Cần idempotency, checkpoint và hệ thống lưu sự kiện nếu muốn delivery semantics mạnh.

**10. Tại sao `collectList()` trên `/ticks` dễ gây test treo?**  
Vì `Flux.interval` không kết thúc. Phải `take(n)`/timeout hoặc chủ động cancel.

**11. Vì sao không nên đưa bearer token lên query param SSE URL?**  
URL dễ xuất hiện trong log, analytics, referrer, browser history; nên dùng cookie có security policy hoặc giải pháp authentication được thiết kế.

**12. HTTP/2 có loại bỏ tất cả connection limits cho SSE?**  
Không. Có limits concurrent streams và hạ tầng/proxy/server budgets; cần load test thực.

## 19. Checklist triển khai production

1. Khai báo response `text/event-stream`, UTF-8; trả `Flux<ServerSentEvent<T>>` khi cần fields đầy đủ.
2. Định nghĩa event names, schema JSON/version, IDs và retry semantics rõ ràng cho clients.
3. Dùng `EventSource` đúng named event listeners; `close()` khi không còn cần stream.
4. Đặt heartbeat comment-only nếu đường truyền có thể idle; test flush thật qua CDN/proxy.
5. Khi muốn resume, lưu event log đáng tin + retention và xử lý `Last-Event-ID`, duplicate/gap/resync.
6. Authorization cho connection, replay và từng tenant/user; không broadcast dữ liệu nhạy cảm qua sink chung.
7. Bảo vệ cookie/CORS/CSRF cho những endpoints liên quan; không gửi token trong URL.
8. Chọn rõ hot/cold Publisher; giới hạn connection count, per-client buffer, subscriber lag và cancellation.
9. Không bật replay/all hoặc unbounded buffers mà thiếu retention/memory budgets; chịu trách nhiệm overflow policy.
10. Đặt timeout/ingress/proxy buffering/HTTP2 settings thích hợp với SSE, đo reconnect storms.
11. Với events thật từ DB, cân nhắc outbox/event log để tránh publish-before-commit và mất thông báo sau crash.
12. Test browser, `curl -N`, WebTestClient, replay từ cursor, named events, slow client, proxy buffering và rolling restart.
13. Đo số connections, retry/drop/replay, per-event delivery lag, JVM memory, broker lag và Gateway limits.
14. Không hứa SSE luôn nhanh hơn polling hoặc WebSocket; đo theo traffic profile và operational constraints.

## 20. Nguồn tham khảo

- [Spring Framework 6.2 — WebFlux controller return values, Flux ServerSentEvent](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — WebFlux Streaming and heartbeat](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — ServerSentEvent API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Project Reactor — Sinks and multicast/replay/backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Project Reactor — Flux.interval and Reactor operators](https://projectreactor.io/docs/core/release/reference/)
- [MDN — Using server-sent events / EventSource](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [WHATWG HTML Living Standard — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
