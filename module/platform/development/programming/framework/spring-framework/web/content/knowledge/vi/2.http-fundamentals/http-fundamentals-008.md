# Phân biệt REST, trang HTML, HTTP streaming và WebSocket

## 1. Bốn khái niệm nằm ở những tầng khác nhau

Trong một ứng dụng Spring, cùng một máy chủ có thể trả JSON cho ứng dụng di động, trả trang HTML cho trình duyệt, phát sự kiện liên tục qua HTTP và mở kết nối WebSocket. Những thứ này **không phải bốn framework cạnh tranh trực tiếp**:

- **REST** là *phong cách kiến trúc* cho API hướng tài nguyên: nhận diện tài nguyên bằng URI, thao tác qua ngữ nghĩa HTTP, trao đổi representation, giao tiếp stateless cùng những ràng buộc REST khác. JSON phổ biến nhưng **không bắt buộc**. Một API trả JSON chưa chắc tuân thủ đầy đủ REST.
- **Trang HTML** là *representation/giao diện tài liệu* mà browser nhận và render. Trang có thể tạo tại server (server-side rendering), phục vụ dưới dạng file tĩnh hoặc có JavaScript tải dữ liệu để cập nhật UI.
- **HTTP streaming** là *cách truyền response dần theo thời gian*: server gửi từng phần trong cùng một HTTP response khi dữ liệu xuất hiện. **Server-Sent Events (SSE)** và **NDJSON** là hai cách tổ chức dữ liệu streaming phổ biến.
- **WebSocket** là *giao thức giao tiếp hai chiều, liên tục* sau quá trình thiết lập kết nối. Client và server có thể chủ động gửi message tới nhau; dữ liệu không còn là từng HTTP response độc lập theo request.

Hai câu hỏi giúp phân biệt: **(1) API/document đang biểu diễn cái gì?** và **(2) dữ liệu đi qua kết nối theo mô hình nào?** Một endpoint REST hoàn toàn có thể cung cấp một representation HTML hoặc stream; ứng dụng HTML có thể gọi REST API và mở WebSocket. Vì vậy các khái niệm **có thể kết hợp**.

## 2. So sánh nhanh theo hành vi quan sát được

| Đặc điểm | REST API thông thường | Trang HTML | HTTP streaming (SSE/NDJSON) | WebSocket |
| --- | --- | --- | --- | --- |
| Bản chất | Kiến trúc API/resource | Định dạng tài liệu/UI | Phản hồi HTTP phát dần | Giao thức trao đổi message song công |
| Cách mở | HTTP request (GET/POST/PUT/DELETE...) | Thường HTTP GET | Thường HTTP GET cho stream; tùy use case | HTTP handshake; thường HTTP/1.1 Upgrade hoặc cách thiết lập tương ứng trên HTTP/2 |
| Sau khi mở | Một response cho mỗi request | Một response HTML, tải thêm CSS/JS/API nếu cần | Một HTTP response tồn tại lâu, nhiều chunk/event | Kết nối giữ mở; nhiều message theo hai chiều |
| Hướng dữ liệu điển hình | Client yêu cầu → server trả | Server trả HTML cho browser | Thường server → client trong response; client có thể gửi request riêng | Client ↔ server chủ động |
| Dạng nội dung | JSON, XML, HTML, binary... | `text/html` | `text/event-stream` (SSE), `application/x-ndjson` hoặc bytes | Text/binary WebSocket frames; schema do ứng dụng quyết định |
| Browser client | `fetch()` | Navigation/browser renderer | `EventSource` (SSE), `fetch()` stream | `WebSocket` API |
| HTTP status & caching | Có, theo ngữ nghĩa endpoint | Có, hỗ trợ cache tài liệu/asset | Status/header có lúc bắt đầu; stream thường không cache như tài liệu hữu hạn | Status HTTP liên quan handshake; message sau đó không mang status HTTP riêng |
| Trường hợp tiêu biểu | CRUD, resource API, nghiệp vụ | Trang giới thiệu, dashboard, form | Tiến độ, log, ticker, live feed | Chat, game, collaborative editing, tương tác hai chiều tức thời |

**Chú ý:** “REST” không đồng nghĩa “GET + JSON”, “streaming” không đồng nghĩa “WebSocket”, và “WebSocket” không có nghĩa mọi request HTTP trong ứng dụng phải được thay thế.

## 3. Minh họa timeline: điểm khác biệt ở vòng đời kết nối

### A. REST API: yêu cầu và phản hồi hữu hạn

~~~text
Browser / Mobile            Server
    |  GET /api/items/7        |
    |------------------------->|
    |  200 application/json    |
    |<-------------------------|
    |  {"id":7,"name":"Bàn phím"} |
    |  response hoàn tất       |
~~~

Request tiếp theo có thể dùng lại TCP connection qua HTTP keep-alive, nhưng vẫn là **HTTP request/response mới**. Không đánh đồng việc kết nối TCP được tái sử dụng với việc một HTTP response còn đang stream.

### B. Trang HTML: trình duyệt render tài liệu

~~~text
Browser                       Server
    | GET /page                   |
    |---------------------------->|
    | 200 text/html               |
    |<----------------------------|
    | parse HTML, render DOM      |
    | tải CSS / JS / ảnh nếu có   |
    | JS có thể gọi REST hoặc WS  |
~~~

HTML có thể tĩnh hoặc sinh bởi template engine. Ở ứng dụng hiện đại, một lần tải HTML có thể tạo ra hàng chục request tải asset/API; đó vẫn là hoạt động HTTP bình thường.

### C. HTTP streaming: một response chứa nhiều phần đến dần

~~~text
Client                        Server
    | GET /events                |
    |--------------------------->|
    | 200 text/event-stream      |
    |<---------------------------|
    | event #1                  <|
    | event #2 (sau một lúc)    <|
    | event #3 (sau một lúc)    <|
    | response kết thúc/ngắt     |
~~~

Server gửi một số header từ đầu, rồi tiếp tục flush body khi có dữ liệu. Dữ liệu streaming có thể tạo ra một hoặc nhiều đoạn ở transport; **ranh giới chunk mạng không mặc nhiên là ranh giới message ứng dụng**.

### D. WebSocket: một session trao đổi message hai chiều

~~~text
Browser / App                Server
    | request handshake         |
    |--------------------------->|
    | handshake thành công      |
    |<---------------------------|
    |--- "hello" -------------->|
    |<------------ "welcome" ---|
    |<--------------- "update" -|
    |--- "ack" ---------------->|
    |        ...                |
    | close / kết nối ngắt       |
~~~

Sau handshake, message WebSocket **không phải các HTTP response JSON riêng lẻ**. Muốn mô tả nghiệp vụ như “đăng ký room”, “gửi tin”, “ACK”, “thông báo lỗi”, ứng dụng phải định nghĩa message schema hoặc sử dụng một subprotocol phù hợp.

## 4. REST: hiểu tài nguyên, method và representation

REST nhấn mạnh tài nguyên có URI ổn định và cách thao tác tuân thủ hợp đồng HTTP. Ví dụ:

| Request | Ý nghĩa ví dụ | Response minh họa |
| --- | --- | --- |
| `GET /api/orders/42` | Lấy representation của đơn 42 | `200 OK` + JSON |
| `POST /api/orders` | Yêu cầu tạo một đơn theo quy ước API | `201 Created` + `Location` khi tạo thành công |
| `PUT /api/orders/42` | Thay thế trạng thái tài nguyên theo representation hợp đồng | `200 OK` hoặc `204 No Content` |
| `PATCH /api/orders/42` | Áp dụng cập nhật từng phần theo patch document/hợp đồng | `200 OK` hoặc `204 No Content` |
| `DELETE /api/orders/42` | Yêu cầu xóa tài nguyên | `204 No Content` thường gặp |

Ngữ nghĩa cần nhớ:

- `GET` là **safe** theo nghĩa không nhằm tạo thay đổi trạng thái do client yêu cầu; `GET` cũng idempotent. Ghi log, metrics vẫn có thể phát sinh ở server.
- `PUT` và `DELETE` có ngữ nghĩa **idempotent**: lặp yêu cầu cùng ý định phải có hiệu ứng mong muốn giống một lần, nhưng **không bắt buộc mỗi response/status giống nhau**.
- `POST` không idempotent theo mặc định. Các giao dịch tạo đơn/thanh toán có thể cần **idempotency key** do ứng dụng thiết kế để retry an toàn.
- `PATCH` không mặc nhiên idempotent; tính chất tùy patch semantics.
- **Stateless** trong REST nghĩa là mỗi request mang đủ ngữ cảnh cần thiết để server xử lý, không phụ thuộc vào trạng thái phiên ứng dụng riêng lưu bên server để hiểu request. Điều này không cấm dữ liệu được lưu lâu dài trong database.
- `Accept` thể hiện loại representation client muốn nhận; `Content-Type` biểu thị loại dữ liệu body đang gửi. `Accept: application/json` và response `Content-Type: application/json` là ví dụ, không phải định nghĩa REST.

Ví dụ biểu diễn JSON:

~~~http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

REST không quy định bắt buộc JSON hay “mỗi URI chỉ trả đúng một format”. Một tài nguyên có thể có nhiều representation; HTML cũng có thể là một representation của tài nguyên.

## 5. HTML: khi server trả tài liệu dành cho browser

Một endpoint trả HTML:

~~~http
GET /page HTTP/1.1
Host: localhost:8080
Accept: text/html
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8

<!doctype html>
<html lang="vi">
  <head><meta charset="UTF-8"><title>Trang mẫu</title></head>
  <body><h1>Chào mừng</h1></body>
</html>
~~~

Có ba kiểu thường gặp:

1. **Static HTML:** server phân phối file `.html` và các asset; phù hợp trang tĩnh, tài liệu hoặc SPA entry point.
2. **Server-side rendered HTML (SSR):** controller đưa model sang template engine như Thymeleaf; server render HTML và trả cho browser. Phù hợp nội dung cần HTML hoàn chỉnh ngay lần tải đầu, form truyền thống, SEO trong những trường hợp liên quan.
3. **Client-rendered UI (SPA):** server trả một HTML shell; JavaScript ứng dụng dùng `fetch()` để lấy REST/HTTP API data và render giao diện.

Trong Spring MVC, một method `@Controller` trả tên view, ví dụ `"product-detail"`, có thể được template resolver xử lý; method `@RestController` hoặc `@ResponseBody` thường trả **body** trực tiếp. Trả chuỗi HTML từ `@RestController` chỉ là demo; ứng dụng thực nên dùng view/template hoặc static resource phù hợp và escape nội dung do người dùng cung cấp.

**HTML không phải đối thủ của REST:** cùng một website có thể trả HTML ở `/products` và JSON ở `/api/products`. Dùng CSS/JS hoặc tải dữ liệu async không biến một trang HTML thành WebSocket.

## 6. HTTP streaming: phát dữ liệu dần trong một response

Trong HTTP response thông thường, server thường đã biết dữ liệu hữu hạn và client xử lý sau khi nhận đủ body hoặc đọc dần body khi về. Với streaming, server cố ý giữ response mở một thời gian và gửi nội dung mới theo từng đợt.

Các dạng phổ biến:

- **Streaming bytes/file:** download file lớn, proxy stream, video/file chunks; client đọc dần bytes, có thể không có message-level framing.
- **SSE:** text theo chuẩn `text/event-stream`, mỗi event có trường như `data:`, `event:`, `id:`; browser có API `EventSource` thuận tiện.
- **NDJSON (Newline-Delimited JSON):** mỗi dòng là một JSON value độc lập, ví dụ telemetry/log/items; client dùng line separator để parse từng record.
- **Long polling:** client giữ một request chờ sự kiện rồi response kết thúc và client gửi request mới. Đây là cơ chế khác với response stream nhiều sự kiện và khác WebSocket.

Với **HTTP/1.1**, một response stream không có sẵn Content-Length có thể sử dụng `Transfer-Encoding: chunked` tùy server và trường hợp. Với **HTTP/2**, dữ liệu truyền qua DATA frames, **không dùng HTTP/1.1 chunked transfer encoding**. Client không nên lấy ranh giới TCP/HTTP frame làm ranh giới dữ liệu nghiệp vụ.

### 6.1 SSE: event server gửi về browser

Response header quan trọng:

~~~http
Content-Type: text/event-stream
Cache-Control: no-cache
~~~

Body SSE có thể trông như:

~~~text
id: 101
event: status
data: {"orderId":42,"state":"PACKING"}

id: 102
event: status
data: {"orderId":42,"state":"SHIPPING"}

~~~

Một **dòng trống** kết thúc một event. `data:` có thể xuất hiện nhiều lần trong cùng event và được ghép theo quy tắc SSE. `id:` cho phép browser lưu last event ID; khi reconnect, client có thể gửi `Last-Event-ID` để server biết mốc cuối, **nhưng khả năng phát lại event bị lỡ là trách nhiệm của ứng dụng/server**, không tự có chỉ vì dùng SSE.

Client browser:

~~~javascript
const source = new EventSource("/events");
source.addEventListener("status", (event) => {
  console.log(event.lastEventId, JSON.parse(event.data));
});
source.onerror = () => console.log("SSE mất kết nối hoặc lỗi");
~~~

`EventSource` thường dùng GET và tự reconnect khi cần; ứng dụng nên có cách đóng bằng `source.close()`. Native `EventSource` không hỗ trợ truyền tùy ý custom request headers như `fetch()`; khi cần auth phải thiết kế cookies/credentials hoặc client streaming khác phù hợp, đồng thời xét CORS.

**Nên chọn SSE khi:** client cần nhận cập nhật trạng thái đơn hàng, dashboard, báo tiến độ job, monitoring hoặc feed liên tục; thao tác gửi lệnh từ client vẫn dùng HTTP POST/PUT riêng. Nếu cần hai chiều liên tục, xét WebSocket.

### 6.2 NDJSON: nhiều JSON document trên cùng một HTTP response

Ví dụ body có ba dòng độc lập:

~~~ndjson
{"id":1,"name":"Bút"}
{"id":2,"name":"Sổ"}
{"id":3,"name":"Thước"}
~~~

Content type thường dùng: `application/x-ndjson`. Client **không** parse cả body như một JSON array, mà đọc từng dòng, ghép các mảnh byte khi cần rồi parse từng JSON object. Trong JavaScript, `fetch()` cung cấp `Response.body` là `ReadableStream` trên browser hỗ trợ; khi decode stream UTF-8 bằng `TextDecoder`, phải xử lý ký tự/dòng bị cắt giữa các network chunk.

Phân biệt: SSE quy định cú pháp event và có `EventSource` tự reconnect; NDJSON chỉ là quy ước mỗi dòng JSON, không mặc định có `id`, replay hay tự reconnect.

### 6.3 Những giới hạn vận hành của HTTP streaming

- **Status và header được gửi từ đầu.** Sau khi response đã commit, không thể đổi status thành `500` một cách bình thường nếu stream lỗi; cần cơ chế thông báo lỗi trong stream hoặc đóng kết nối.
- **Proxy/CDN/load balancer** có thể buffer, idle timeout hoặc đóng kết nối. Đo thời gian từ server phát đến client nhận; kiểm tra buffering/flush thực tế.
- **Slow consumer/backpressure:** client đọc chậm gây áp lực buffer/memory; reactive backpressure có thể giúp trong các publisher hỗ trợ nhưng không tự hạn chế toàn bộ traffic hay upstream ngoài.
- **Reconnect, retry, duplicate:** stream có thể ngắt giữa chừng. Muốn độ tin cậy cần cursor/event ID, replay store, deduplication và quy tắc resume.
- **Timeout/heartbeat:** kết nối dài có thể cần keep-alive event hoặc heartbeat và timeout phù hợp. SSE có thể gửi dòng comment bắt đầu bằng `:`.
- **Bảo mật:** stream vẫn cần xác thực/phân quyền, giới hạn kết nối và kiểm soát lượng dữ liệu phát cho từng subscriber.

## 7. WebSocket: phiên hai chiều cho các message độc lập

WebSocket phù hợp khi **server và client đều phải chủ động gửi dữ liệu với độ trễ thấp**. Ví dụ chat: client gửi `SEND_MESSAGE`, server phản hồi `ACK`, server đẩy `NEW_MESSAGE` cho nhiều client khi có tin mới. Một connection có thể chuyên chở nhiều message mà không tạo request HTTP mới cho mỗi message.

Trên HTTP/1.1, browser thường khởi tạo bằng handshake có header:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: [giá trị do client tạo]
Sec-WebSocket-Version: 13
~~~

Khi thành công, server phản hồi `101 Switching Protocols` cùng các header WebSocket cần thiết. Trên HTTP/2, tiêu chuẩn cũng cho phép cơ chế thiết lập khác (extended CONNECT) nếu client/server hỗ trợ; không giả định mọi WebSocket đều dùng chính xác handshake HTTP/1.1. Với TLS, browser dùng scheme `wss://` thay vì `ws://`; trên trang HTTPS, nên dùng WSS.

**Sau handshake:**

- Kênh truyền là WebSocket frames/messages (text hoặc binary), không phải JSON HTTP response với status/header cho từng message.
- WebSocket **không quy định** message nghiệp vụ là JSON, protobuf, tên topic hay cấu trúc event; đây là hợp đồng ứng dụng.
- **STOMP over WebSocket** là một lựa chọn subprotocol/messaging khi ứng dụng cần destination/subscription; STOMP không bắt buộc đối với WebSocket.
- WebSocket có ping/pong cấp giao thức, nhưng chiến lược heartbeat application, timeout và reconnect vẫn cần được đánh giá.
- WebSocket **không tự đảm bảo** message đã được lưu, đúng một lần, replay sau reconnect hay phân phối xuyên nhiều instance.

### Khi nào WebSocket có lợi thế?

- Chat hai chiều, presence và typing indicator.
- Collaborative editing với nhiều thay đổi client ↔ server.
- Multiplayer game / điều khiển tương tác hoặc các luồng command và push dày.
- Telemetry hai chiều cần kênh message liên tục.

Nếu client chỉ cần nhận một luồng sự kiện đơn hướng, SSE có thể đơn giản hơn. Với cập nhật thưa và không yêu cầu thời gian thực, periodic polling hoặc REST API có thể đủ.

### Những điều phải thiết kế cho production

- Xác thực lúc kết nối và phân quyền **cho từng loại message/destination**; không coi kết nối thành công là toàn quyền.
- Kiểm tra `Origin` cho browser, chính sách cookie/session, CSRF ở nơi liên quan, và không tin payload từ client.
- Giới hạn kích cỡ message, rate, số connection, outbound queue và thời gian nhàn rỗi.
- Phát hiện disconnect, reconnect theo backoff và đồng bộ trạng thái/cursor sau reconnect.
- Khi chạy nhiều instance, xác định cách broadcast tới đúng subscriber (broker/pub-sub/shared state) và cấu hình load balancer hỗ trợ WebSocket; sticky session một mình không thay thế hệ thống phân phối message.
- Theo dõi active connections, send queue, ping/pong, lỗi handshake, event-loop latency và downstream saturation.

## 8. Spring MVC và Spring WebFlux hỗ trợ những cách nào?

| Nhu cầu | Spring MVC / Servlet stack | Spring WebFlux / reactive stack |
| --- | --- | --- |
| JSON REST API | `@RestController` + `@GetMapping`, `ResponseEntity` | `@RestController` tương tự, có thể trả `Mono<T>` / `Flux<T>` |
| HTML trang | `@Controller` + view resolver/Thymeleaf, static resources | Có view rendering/static resources và annotated hoặc functional endpoints |
| SSE | `SseEmitter`, `ResponseBodyEmitter`, xử lý async Servlet | `Flux<ServerSentEvent<T>>` hoặc `Flux<T>` với `text/event-stream` |
| Stream raw/file | `StreamingResponseBody`, async support tùy trường hợp | `Flux<DataBuffer>` và reactive codecs |
| NDJSON stream | Có thể dùng emitter/custom streaming | `Flux<T>` với `application/x-ndjson` |
| WebSocket | Spring WebSocket Servlet API, `WebSocketHandler`, tùy chọn STOMP broker | Reactive `org.springframework.web.reactive.socket.WebSocketHandler` |
| Điểm đánh giá | Thư viện sync/JPA, Servlet async/virtual threads khi phù hợp | Chuỗi non-blocking xuyên downstream, Reactor semantics và flow control |

Không chọn WebFlux **chỉ** vì muốn SSE/WebSocket. Spring MVC cũng hỗ trợ streaming và WebSocket. Lựa chọn MVC/WebFlux là quyết định kiến trúc execution model/I/O chain rộng hơn nội dung bài học này.

## 9. Ví dụ chạy được: một ứng dụng WebFlux có cả bốn cách trao đổi

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.x / Spring Framework 6.1+**, một ứng dụng độc lập gồm:

- `GET /api/items/7` → một JSON response thông thường;
- `GET /page` → một HTML document;
- `GET /events` → ba SSE event được phát theo thời gian;
- `GET /stream/items` → ba NDJSON record được phát theo thời gian;
- `/ws/echo` → endpoint WebSocket echo, client có thể gửi message.

WebFlux được chọn **để biểu diễn các kiểu response trong một ví dụ thống nhất**; không có nghĩa MVC không làm được những kiểu này.

### 9.1 Cấu hình Gradle

Tạo thư mục project mới với `settings.gradle`:

~~~groovy
rootProject.name = 'protocol-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
}
~~~

Cần JDK 17+ và Gradle tương thích với phiên bản Spring Boot được sử dụng (ví dụ Gradle 8.x). Nếu có Gradle Wrapper, dùng wrapper; nếu chưa có, cần Gradle đã cài để chạy `gradle bootRun` hoặc tạo wrapper.

### 9.2 Java source

Tạo `src/main/java/example/protocols/ProtocolDemoApplication.java`:

~~~java
package example.protocols;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ProtocolDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProtocolDemoApplication.class, args);
    }

    public record Item(long id, String name) {}

    @RestController
    static class HttpController {

        @GetMapping(value = "/api/items/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Item item(@PathVariable long id) {
            return new Item(id, "Bàn phím");
        }

        @GetMapping(value = "/page",
                    produces = MediaType.TEXT_HTML_VALUE)
        public String page() {
            return "<!doctype html><html lang=\"vi\">"
                    + "<head><meta charset=\"UTF-8\">"
                    + "<title>HTML demo</title></head>"
                    + "<body><h1>Trang HTML từ Spring</h1></body></html>";
        }

        @GetMapping(value = "/events",
                    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
        public Flux<ServerSentEvent<String>> events() {
            return Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
                    .take(3)
                    .map(index -> ServerSentEvent.<String>builder()
                            .id(Long.toString(index))
                            .event("tick")
                            .data("Thông báo " + index)
                            .build());
        }

        @GetMapping(value = "/stream/items",
                    produces = MediaType.APPLICATION_NDJSON_VALUE)
        public Flux<Item> ndjson() {
            return Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
                    .take(3)
                    .map(index -> new Item(index + 1,
                            "Mặt hàng " + (index + 1)));
        }
    }

    @Component
    static class EchoSocket implements WebSocketHandler {

        @Override
        public Mono<Void> handle(WebSocketSession session) {
            return session.send(session.receive()
                    .map(message -> session.textMessage(
                            "echo: " + message.getPayloadAsText())));
        }
    }

    @Bean
    public HandlerMapping socketMapping(EchoSocket echoSocket) {
        Map<String, WebSocketHandler> endpoints =
                Map.of("/ws/echo", echoSocket);
        return new SimpleUrlHandlerMapping(endpoints, -1);
    }
}
~~~

Trong ứng dụng Spring Boot WebFlux cấu hình theo chuẩn Boot, WebSocket handler adapter được framework thiết lập. `SimpleUrlHandlerMapping` đăng ký `/ws/echo` với thứ tự ưu tiên `-1` để request handshake được đưa tới WebSocket handler. Khi client đóng kết nối, luồng receive hoàn tất và phiên được giải phóng. Đây là demo echo chữ, không phải giao thức chat hoàn chỉnh.

### 9.3 Chạy và tự kiểm chứng HTTP

Từ thư mục project, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có wrapper, dùng `gradle bootRun` với Gradle tương thích đã cài. Khi server chạy mặc định trên cổng 8080:

**A. JSON REST-style GET**

~~~bash
curl -i http://localhost:8080/api/items/7
~~~

Status mong đợi: `200 OK`; `Content-Type` thuộc `application/json`. Body:

~~~json
{"id":7,"name":"Bàn phím"}
~~~

**B. HTML document**

~~~bash
curl -i http://localhost:8080/page
~~~

Status mong đợi: `200 OK`; `Content-Type` thuộc `text/html`. Body có `<h1>Trang HTML từ Spring</h1>`, trình duyệt sẽ render thành tiêu đề trang.

**C. SSE streaming**

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/events
~~~

Khi kết nối được phát dữ liệu theo lịch của ví dụ, body có ba event tương đương về nội dung:

~~~text
id:0
event:tick
data:Thông báo 0

id:1
event:tick
data:Thông báo 1

id:2
event:tick
data:Thông báo 2

~~~

Khoảng trắng sau dấu hai chấm tùy cách serialize SSE hợp lệ; **không phụ thuộc chính xác spacing**. `-N` yêu cầu curl không buffer stdout; mỗi event đến cách nhau xấp xỉ một giây, còn thời gian thực tế phụ thuộc scheduler và tải.

**D. NDJSON streaming**

~~~bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/stream/items
~~~

Các dòng body dự kiến, mỗi dòng là JSON độc lập:

~~~ndjson
{"id":1,"name":"Mặt hàng 1"}
{"id":2,"name":"Mặt hàng 2"}
{"id":3,"name":"Mặt hàng 3"}
~~~

Các dòng đến dần theo thời gian; không có dấu ngoặc vuông `[ ]` bao quanh toàn bộ dòng như JSON array.

**E. WebSocket client từ DevTools của browser**

Mở trang trong browser và chạy:

~~~javascript
const ws = new WebSocket("ws://localhost:8080/ws/echo");
ws.onopen = () => ws.send("xin chào");
ws.onmessage = (event) => console.log(event.data);
ws.onerror = (event) => console.error("WebSocket error", event);
ws.onclose = (event) => console.log("closed", event.code);
~~~

Kết quả console mong đợi khi kết nối thành công:

~~~text
echo: xin chào
~~~

Để đóng kết nối khi kiểm thử xong, gọi `ws.close()`. Nếu trang được truy cập qua HTTPS, URL WebSocket phải sử dụng `wss://` trong môi trường được triển khai với TLS phù hợp.

**F. SSE client từ browser**

Nếu đang mở cùng origin với ứng dụng demo:

~~~javascript
const es = new EventSource("/events");
let received = 0;

es.addEventListener("tick", (event) => {
  console.log("SSE", event.lastEventId, event.data);
  received++;
  if (received === 3) es.close();
});
~~~

Ví dụ đóng sau ba event, vì `EventSource` mặc định có thể kết nối lại khi stream đóng; `Flux.take(3)` ở server chỉ kết thúc response của **một lần kết nối**, không vô hiệu hóa khả năng reconnect của client.

### 9.4 Điều gì giúp ví dụ này hoạt động?

- `@RestController` và `produces` phân biệt content type cho JSON, HTML, SSE và NDJSON.
- `Flux.interval(...).take(3)` là publisher mô phỏng dữ liệu sinh dần. Thực tế có thể thay bằng nguồn events từ application service.
- `ServerSentEvent<T>` tạo cú pháp SSE có event name và ID.
- `Flux<Item>` với `application/x-ndjson` cho phép encode từng item thành dòng JSON; không gom thành một JSON array nếu giữ đúng streaming media type.
- `WebSocketHandler` tiêu thụ các message đến và chuyển thành message trả ra trên cùng session.
- Một ứng dụng dùng được cả năm endpoint chứng minh **cùng web stack có thể triển khai nhiều kiểu giao tiếp**.

**Giới hạn demo:** chương trình chưa có xác thực/phân quyền, rate limit, persistence, resume cursor hay xử lý lỗi/retry cho môi trường phân tán. Trong thực tế không đặt một broadcaster vô hạn hoặc echo tùy ý cho client không được tin cậy.

## 10. Cách chọn cho tình huống thực tế

### Tình huống 1 — Quản lý sản phẩm / đơn hàng

Người dùng nhấn “Tạo đơn” và xem lịch sử mua hàng. Client cần request có kết quả rõ ràng, HTTP status phù hợp và dễ cache dữ liệu GET khi được phép. **Dùng HTTP API theo resource/REST-style**, trả JSON cho ứng dụng hoặc HTML SSR nếu client là trang truyền thống. Không cần WebSocket để thay thế thao tác POST.

### Tình huống 2 — Giao diện website giới thiệu / biểu mẫu

Trang có nội dung đầy đủ ngay khi tải, template render dữ liệu và form post. **Trả HTML**; một số hành động vẫn có thể gọi JSON API. WebSocket không mang lại lợi ích chỉ vì browser đang mở trang.

### Tình huống 3 — Theo dõi tiến độ xử lý file trong 2 phút

Client gửi `POST /jobs` để tạo job, nhận `202 Accepted` và một `jobId`, sau đó theo dõi `GET /jobs/{id}/events` bằng SSE hoặc polling. **SSE** hợp lý khi cần server đẩy nhiều cập nhật một chiều và client giữ một request mở; nếu yêu cầu đơn giản, polling định kỳ cũng được. Cần có cơ chế reconnect/replay nếu không được mất tiến độ.

### Tình huống 4 — Dashboard log/telemetry chảy liên tục

Các record liên tiếp đến dưới dạng JSON. **NDJSON streaming** hợp với client có thể parse từng dòng, cần dữ liệu máy đọc được theo một chiều; **SSE** hợp nếu mục tiêu là browser dùng `EventSource` và muốn event ID/reconnect semantics thuận tiện.

### Tình huống 5 — Chat trực tiếp nhiều người

Client vừa gửi tin, vừa nhận tin mới và typing indicator. **WebSocket** hợp lý vì nhiều message hai chiều và kết nối giữ mở. Vẫn có thể dùng REST API cho đăng nhập, tải lịch sử, upload file, quản lý room; WebSocket đảm nhiệm luồng tương tác thời gian thực.

### Tình huống 6 — Giá cập nhật một lần mỗi 10 phút

GET API với cache/periodic refresh thường đơn giản hơn kết nối streaming/WebSocket luôn mở. “Realtime” là yêu cầu kinh doanh cần lượng hóa, không phải mục tiêu tự thân.

## 11. Khác biệt quan trọng khi thiết kế, debug và deploy

### 11.1 Độ trễ và buffering

Ứng dụng có thể `flush()` nhưng reverse proxy vẫn buffer body. Để kiểm tra stream, dùng `curl -N`, quan sát Network timing trong browser, thử qua đúng ingress/CDN production. Tách thời gian xử lý nghiệp vụ khỏi thời gian server write và client nhận. Streaming không bảo đảm một event lập tức được render khi proxy/client trì hoãn.

### 11.2 Caching và CDN

GET JSON/HTML có thể cache theo `Cache-Control`, `ETag`/`Last-Modified` khi hợp đồng cho phép. SSE và stream dài thường phải xem xét disable cache và proxy buffering. WebSocket không dùng HTTP response caching cho từng message. Tránh gắn `Cache-Control: public` cho dữ liệu cá nhân.

### 11.3 Backpressure, fan-out và tải

Nhiều người nhận cùng một broadcast có tốc độ đọc khác nhau; server phải có chính sách buffer, drop/coalesce, disconnect slow clients hoặc queue giới hạn. WebFlux hỗ trợ Reactive Streams, nhưng upstream/broker không nhất thiết có backpressure đến tận nguồn. Đo memory, số connection, queue length và tốc độ gửi.

### 11.4 Error semantics

HTTP API thông thường thể hiện lỗi qua HTTP status và error body. Với SSE/NDJSON, nếu headers đã commit rồi mới phát sinh lỗi, không thể thay status như response chưa bắt đầu; cần error event/record theo giao thức hoặc đóng stream và cho client resume. WebSocket cần định nghĩa error message hoặc close code, không thể mong HTTP 500 cho từng frame.

### 11.5 Mất kết nối và thứ tự message

SSE có hỗ trợ last event ID ở browser nhưng server phải lưu lịch sử để replay. NDJSON cần tự định nghĩa cursor/reconnect nếu cần. WebSocket trên **một kết nối** bảo toàn thứ tự message theo giao thức, nhưng khi reconnect, failover hoặc xử lý qua nhiều service, cần thiết kế ACK, offset, idempotency và deduplication ở tầng ứng dụng.

### 11.6 Xác thực và bảo mật

HTTP, SSE và WebSocket đều cần auth phù hợp dữ liệu. `EventSource` có giới hạn headers trong browser. Với WebSocket browser, phải xét Origin, cookie, handshake auth và **quyền của từng message**. Dùng TLS (`https://`, `wss://`), validate payload, giới hạn kích thước/tốc độ và kiểm tra phân quyền trước khi gửi dữ liệu vào room/topic.

### 11.7 Quan sát và test

- REST: status, response schema, cache headers, idempotent retry, p95/p99.
- HTML: render đúng, escaping/XSS, asset tải được, SEO/SSR nếu yêu cầu.
- SSE: nhiều event đến theo thời gian, reconnect, Last-Event-ID/replay, proxy idle timeout.
- NDJSON: mỗi dòng parse được, chunk có thể cắt giữa dòng/ký tự UTF-8, stream cancel và slow consumer.
- WebSocket: handshake, message schema, ping/pong, reconnect, auth per-message, nhiều client/instance và close code.

## 12. Lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Sửa cách hiểu |
| --- | --- |
| “REST là JSON” | REST là kiến trúc; JSON chỉ là một kiểu representation; JSON API có thể không RESTful |
| “HTML là backend, REST là frontend” | Cả HTML và REST API có thể được server cung cấp và browser/mobile tiêu thụ |
| “Streaming phải dùng WebSocket” | HTTP streaming (SSE, NDJSON, file) hoạt động trong HTTP response |
| “SSE gửi hai chiều như WebSocket” | SSE stream gốc là server → client; muốn gửi lệnh, client dùng HTTP request khác |
| “`Transfer-Encoding: chunked` là chuẩn SSE” | SSE là cú pháp event; chunked chỉ là một cơ chế HTTP/1.1 truyền body |
| “Một TCP chunk tương ứng một JSON record” | Mạng có thể cắt/gộp bytes tùy ý; parse theo framing của SSE/NDJSON |
| “WebSocket tự có topic, room, ACK, lưu trữ” | WebSocket chỉ cung cấp transport message; ứng dụng hoặc subprotocol thiết kế các chức năng này |
| “HTTP status code cho mỗi WebSocket frame” | Status HTTP xử lý handshake; message sau đó cần schema lỗi riêng |
| “SSE có `id` thì tự replay mọi dữ liệu” | Server phải lưu và phát lại theo ID khi client reconnect |
| “Đổi sang WebFlux mới dùng được WebSocket/SSE” | Spring MVC cũng hỗ trợ SSE, WebSocket và async HTTP |
| “Có streaming là ngay lập tức không latency” | Proxy buffering, scheduler, backpressure và client read speed vẫn có tác động |
| “Giữ connection lâu là luôn tốt hơn polling” | Connection, memory, broker fan-out và vận hành đều có chi phí; chọn theo tần suất cập nhật |

## 13. Bài tập vận dụng

Chọn cơ chế giao tiếp thích hợp và nêu lý do:

1. Frontend cần lấy thông tin một sản phẩm theo ID, tải xong là đủ.
2. Server cần render trang danh sách bài viết cho trình duyệt, có liên kết và form.
3. Browser cần nhận tình trạng đồng bộ dữ liệu mỗi giây trong một phút; không gửi message tương tác qua cùng kênh.
4. CLI cần đọc hàng nghìn record JSON lớn dần, xử lý ngay từng dòng.
5. Hai người đang cùng sửa một tài liệu và gửi các thay đổi qua lại liên tục.
6. Dịch vụ chỉ cập nhật giá sản phẩm khoảng một lần mỗi giờ.

**Gợi ý đáp án:** (1) HTTP GET REST-style/JSON. (2) HTML từ server hoặc static/SSR. (3) SSE và có thể chọn polling nếu yêu cầu đơn giản. (4) NDJSON HTTP streaming. (5) WebSocket, cộng message schema và đồng bộ trạng thái. (6) GET có caching hoặc polling theo lịch, không nhất thiết giữ kết nối dài.

## 14. Checklist thiết kế một endpoint

- [ ] Xác định rõ mục tiêu: resource API, tài liệu HTML, feed một chiều hay tương tác hai chiều.
- [ ] Biết HTTP method, URI, status, `Content-Type`, `Accept` và cache policy.
- [ ] Với REST API: nắm ngữ nghĩa safe/idempotent, transaction và retry.
- [ ] Với HTML: biết render ở server hay client, escape dữ liệu động và quản lý assets.
- [ ] Với SSE/NDJSON: định nghĩa framing, giới hạn stream, timeout, heartbeat, backpressure và lỗi sau khi response commit.
- [ ] Với SSE: quyết định có cần event ID, replay và auth tương thích browser không.
- [ ] Với WebSocket: định nghĩa message schema, auth từng message, close/reconnect, capacity và broadcast nhiều instance.
- [ ] Kiểm chứng streaming qua proxy/load balancer thật; đo client nhận được lúc nào.
- [ ] Test khi client đọc chậm, ngắt giữa chừng hoặc reconnect.
- [ ] Chỉ chọn MVC/WebFlux sau khi xét **toàn bộ chuỗi I/O** và thư viện đang sử dụng.

**Kết luận ứng dụng:** REST giúp tổ chức API tài nguyên; HTML cung cấp tài liệu/giao diện; HTTP streaming cung cấp phản hồi dần trong HTTP; WebSocket cung cấp kênh message hai chiều dài hạn. Một hệ thống Spring khỏe mạnh có thể phối hợp cả bốn theo từng luồng nghiệp vụ.

### Tài liệu tham khảo

- [Spring Framework — Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
- [Spring Framework — Asynchronous Requests / SSE trong MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [MDN — Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
