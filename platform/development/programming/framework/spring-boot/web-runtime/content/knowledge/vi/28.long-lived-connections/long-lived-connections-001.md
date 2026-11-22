# Phân biệt streaming HTTP, Server-Sent Events và WebSocket

Khi một trang web cần nhìn thấy dữ liệu trước khi server hoàn thành toàn bộ công việc, có ba kỹ thuật thường được nhắc đến: **HTTP streaming**, **Server-Sent Events (SSE)** và **WebSocket**. Chúng có thể cùng giữ một kết nối trong thời gian dài, nhưng **không cùng cấp độ khái niệm** và **không thay thế nhau trong mọi trường hợp**.

- **HTTP response streaming** là cách server gửi body của một HTTP response thành nhiều phần theo thời gian thay vì chuẩn bị xong rồi mới trả toàn bộ. Dữ liệu có thể là các byte, văn bản, NDJSON, tập tin hoặc định dạng tùy ứng dụng. Phía client muốn hiểu từng mảnh phải biết cách phân tách chúng.
- **SSE** là **một giao thức sự kiện trên HTTP response streaming**, với `Content-Type: text/event-stream`, các field `event:`, `data:`, `id:`, `retry:` và client browser `EventSource` có cơ chế tự nối lại kết nối. Dòng sự kiện ở cấp ứng dụng đi **từ server đến client**.
- **WebSocket** là giao thức giao tiếp **hai chiều, full-duplex** sau khi kết nối được thiết lập bằng handshake. Cả client và server có thể gửi các message text/binary bất kỳ lúc nào. Nó không mặc nhiên cung cấp authentication, business acknowledgements, replay hay reconnect.

Vì vậy, câu hỏi nên là **ứng dụng cần truyền thông tin theo hướng nào, định dạng nào, mức độ bảo đảm ra sao và qua hạ tầng proxy nào?** chứ không chỉ “công nghệ nào thời gian thực hơn?”.

Bài này sử dụng **Spring Boot 3.x, Spring MVC, Java 17+**, có demo chạy cả ba kỹ thuật trong cùng một ứng dụng và phần đối chiếu với **Spring WebFlux**. Các property và chi tiết server có thể khác ở Spring Boot major version khác.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Giải thích HTTP response body streaming, SSE và WebSocket theo **transport**, **message format**, **direction** và **lifecycle**.
- Đọc HTTP headers, SSE wire format và WebSocket handshake/trạng thái kết nối.
- Tạo NDJSON streaming bằng `StreamingResponseBody`, SSE bằng `SseEmitter` và WebSocket echo bằng `TextWebSocketHandler`.
- Dùng browser `fetch()` streaming reader, `EventSource` và `WebSocket`; thử NDJSON/SSE bằng `curl -N`.
- Phân biệt **streamed bytes**, **event delivery**, **message boundaries**, **heartbeats**, **reconnect**, **replay** và **backpressure**.
- Thiết kế timeout, proxy buffering, TLS, CORS/Origin/CSRF, giới hạn kết nối và quyền truy cập cho các kết nối dài.
- Nhận diện vì sao mở nhiều SSE/WebSocket connections không tự làm hệ thống scale tốt.
- Chọn giải pháp cho log tiến trình, giá cổ phiếu, notification, chat/collaboration, file download và dữ liệu nhị phân.
- Kiểm thử lúc kết nối mất giữa chừng, server restart, client chậm, nhiều replicas và rolling deployment.

## 2. Một bảng so sánh trước khi đi sâu

| Tiêu chí | HTTP response streaming | SSE | WebSocket |
| --- | --- | --- | --- |
| Bản chất | HTTP response được gửi dần theo các chunk/frame | **HTTP streaming có chuẩn sự kiện** `text/event-stream` | Giao thức message hai chiều sau handshake |
| Hướng ở ví dụ phổ biến | Server → client trong một response; HTTP vẫn hỗ trợ request body streaming ở flow khác | Server → client, lệnh client thường gửi bằng HTTP request khác | Client ↔ server trên cùng channel |
| Kiểu dữ liệu | Byte bất kỳ; NDJSON, text, CSV, video, file | UTF-8 text theo `data:`/`event:`, có thể chứa JSON dưới dạng text | Text và binary messages |
| Phân chia bản tin | Ứng dụng tự quy định: newline, length prefix, boundary... | SSE parser nhận event khi gặp dòng trống | WebSocket có message framing ở tầng protocol |
| Browser API | `fetch()` + `ReadableStream` hoặc stream reader tương ứng | `EventSource` | `WebSocket` |
| Mặc định tự kết nối lại | Không; ứng dụng tự làm | `EventSource` có tự reconnect | Không; ứng dụng tự làm |
| Khôi phục dữ liệu bị lỡ | Tự thiết kế offset/range/cursor | `id`/`Last-Event-ID` giúp yêu cầu resume, server **phải tự có replay store** | Tự thiết kế seq/ack/replay |
| Proxy/cache | Theo HTTP, có thể bị buffering | Theo HTTP, cần tắt buffering và cache sai | Cần cho phép handshake Upgrade/transport tương ứng |
| Mỗi request/connection | HTTP request có thể hữu hạn hoặc dài | Một HTTP response sống lâu; reconnect mở request mới | Một socket messaging channel sống lâu |
| Phù hợp | Download lớn, dữ liệu NDJSON, tiến trình tính toán | Event notifications, dashboard, theo dõi trạng thái | Chat, game, collaboration, thao tác tương tác hai chiều |
| Giới hạn đáng chú ý | Client phải tự parse và tự resume | Không gửi binary trực tiếp; browser `EventSource` GET và không tùy biến headers dễ dàng | Vận hành kết nối hai chiều, message security và state/phân phối phức tạp hơn |

**Quan hệ tập hợp:** SSE **là một dạng của HTTP streaming**. Đặt SSE và HTTP streaming cạnh nhau để so sánh là cách nói tắt về **HTTP streaming tùy ý** với **HTTP streaming có định dạng SSE**. WebSocket không đơn giản là “HTTP streaming tốt hơn”: ứng dụng nhận được một giao thức khác cùng các trách nhiệm khác.

## 3. Tại sao truyền từng phần lại quan trọng?

### 3.1. Phản hồi HTTP thông thường

```text
Client GET /report
            |
            v
Server tính toàn bộ báo cáo (5 giây)
            |
            v
HTTP 200 + body hoàn chỉnh
            |
            v
Client xử lý sau khi response xong
```

Với nội dung lớn hoặc được tạo dần, client phải chờ byte cuối mới có đủ dữ liệu nếu code tải toàn bộ body trước khi xử lý. Dù HTTP stack có thể đọc dần dữ liệu, ứng dụng gọi `response.json()` thường nhận kết quả chỉ khi **toàn bộ body được hoàn thành và parse được**.

### 3.2. HTTP response streaming

```text
Client GET /stream/ndjson
            |
            v
HTTP 200 + headers
            |
            +--> {"seq":1,"kind":"snapshot"}\n
            |
         800 ms
            |
            +--> {"seq":2,"kind":"snapshot"}\n
            |
         800 ms
            |
            +--> ...
            |
            +--> end of response
```

Mỗi dòng NDJSON là một JSON object **hoàn chỉnh**, phân cách bằng newline. Client có thể parse từng dòng khi đủ bytes mà không chờ body kết thúc. Nhưng TCP segments và HTTP chunks **không bắt buộc trùng** với ranh giới JSON line: một đối tượng có thể bị tách qua nhiều lần đọc, hoặc nhiều đối tượng được gộp trong một lần đọc. Parser phải **buffer phần chưa đủ**.

**Streaming không đồng nghĩa “HTTP chunked” cố định.** Với HTTP/1.1, server có thể dùng `Transfer-Encoding: chunked` khi không biết Content-Length. Với HTTP/2/3, dữ liệu được gửi theo DATA frames của protocol tương ứng; ứng dụng vẫn đọc response body dần. Không tự gắn `Transfer-Encoding: chunked` trong controller để bắt streaming hoạt động.

### 3.3. SSE là stream có cú pháp sự kiện chuẩn

```text
Client EventSource("/events")
            |
            v
GET /events
Accept: text/event-stream
            |
            v
HTTP 200 Content-Type: text/event-stream
            |
            +--> event: tick
            |    id: 1
            |    retry: 2000
            |    data: tick-1
            |
            |    [một dòng trống => dispatch event]
            |
            +--> event: tick
            |    id: 2
            |    data: tick-2
            |
            +--> ...
```

SSE vẫn là HTTP response; `EventSource` hiểu nội dung theo quy tắc trường và tự phát `MessageEvent` tương ứng. Khi socket hỏng, browser thường thử kết nối lại. Tuy nhiên server phải **giữ lịch sử event** nếu muốn client thật sự nhận lại những event bị lỡ.

### 3.4. WebSocket thiết lập một kênh message hai chiều

```text
Browser                                  Spring Boot
   |                                          |
   | HTTP/1.1 GET /ws/echo                    |
   | Upgrade: websocket                       |
   |----------------------------------------->|
   |        101 Switching Protocols           |
   |<-----------------------------------------|
   |                                          |
   |   WebSocket text message: "hello"        |
   |----------------------------------------->|
   |   WebSocket text message: "echo: hello"  |
   |<-----------------------------------------|
   |   text/binary messages both ways ...     |
   |<---------------------------------------->|
   |              Close handshake             |
   |<---------------------------------------->|
```

Đây là handshake **WebSocket over HTTP/1.1** thông dụng. HTTP/2 có cơ chế extended CONNECT dành cho WebSocket khi client/server/proxy hỗ trợ, không phải mọi triển khai Boot/ingress đều hỗ trợ. Khi đã nâng cấp, data messages không còn là các HTTP responses độc lập như SSE.

## 4. HTTP streaming: khái niệm và những định dạng phổ biến

### 4.1. Raw bytes và StreamingResponseBody

Trong Spring MVC, `StreamingResponseBody` cho phép ứng dụng viết trực tiếp xuống response `OutputStream` mà không phải xây toàn bộ body trước. Handler trả về một callback được thực thi theo cơ chế asynchronous request processing của Servlet; các lần `write`/`flush` có thể khiến bytes được chuyển đi dần nếu các tầng sau không buffer.

Dùng khi:

- Tạo CSV/export lớn theo từng record;
- Trả tệp hoặc báo cáo được tạo dần;
- Trả dữ liệu có định dạng streaming riêng;
- Trả NDJSON khi client cần xử lý từng object.

**Không mặc định** rằng mỗi lần `flush()` từ Java tương ứng ngay một lần `reader.read()` trong browser. Có thể có servlet buffer, gzip, reverse proxy buffering, TLS records, HTTP2 frames, network coalescing và browser buffering.

### 4.2. NDJSON: từng JSON object trên một dòng

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson
Cache-Control: no-store
```

Body minh họa:

```jsonl
{"seq":1,"kind":"snapshot"}
{"seq":2,"kind":"snapshot"}
{"seq":3,"kind":"snapshot"}
```

Định dạng **newline-delimited JSON** cho phép parse từng dòng. Nó khác với một mảng JSON duy nhất:

```json
[{"seq":1},{"seq":2},{"seq":3}]
```

Nếu code phía client gọi `await response.json()`, nó không tự biết từng dòng NDJSON; thường phải dùng `ReadableStream`, `TextDecoder` và buffer đến newline. Còn mảng JSON thông thường cần dữ liệu hoàn chỉnh hoặc incremental JSON parser chuyên biệt.

Có những stream khác như `text/plain` log lines, `multipart/mixed`, `application/octet-stream`, file/range hoặc một protocol custom có length prefix. Vì HTTP streaming không quy định event semantics chung, **hai phía phải thống nhất framing**.

### 4.3. HTTP có request streaming, nhưng khác bài toán server push

Một client có thể upload request body theo stream (ví dụ một file hoặc dữ liệu được tạo dần), còn server cũng có thể stream response. Tuy nhiên đây vẫn là các message HTTP với request/response semantics. Đừng nói “HTTP chỉ đi một chiều”: điều đúng là **một response stream cụ thể đi từ server đến client**, trong khi SSE chỉ chuẩn hóa hướng server→client ở cấp event API.

### 4.4. Trường hợp không cần giữ stream

Nếu backend có thể trả kết quả trong vài chục mili giây và payload nhỏ, response JSON thông thường dễ cache/test/observability hơn. Streaming tạo vòng đời request dài, khó timeout/retry và khó quản lý rate limit/CPU nếu không có giá trị thiết thực.

## 5. SSE: cấu trúc giao thức và EventSource

### 5.1. Content-Type và UTF-8

Response SSE sử dụng `Content-Type: text/event-stream`, nội dung là text UTF-8. Một event là một nhóm dòng, kết thúc bằng **dòng trống**. Các field thường gặp:

| Field | Ý nghĩa |
| --- | --- |
| `data:` | Payload dạng text; nhiều dòng data được nối bằng newline |
| `event:` | Tên loại sự kiện; client nghe bằng `addEventListener` |
| `id:` | ID event được browser nhớ để gửi lại khi reconnect |
| `retry:` | Gợi ý thời gian retry, tính bằng **mili giây**, phải là số hợp lệ |
| `: comment` | Comment/heartbeat, browser không phát như event ứng dụng |

Ví dụ raw stream:

```text
: heartbeat

id: 100
event: status
data: {"jobId":42,"state":"RUNNING"}

id: 101
event: status
data: {"jobId":42,"state":"DONE"}

```

Một event `status` được phát sau dòng trống, không phải ngay khi parser đọc dòng `data:`. Nếu payload nhiều dòng:

```text
event: notice
data: Dong thu nhat
data: Dong thu hai

```

Browser thấy `event.data` tương đương chuỗi `"Dong thu nhat\nDong thu hai"`. Khi gửi JSON multiline, phải đảm bảo mỗi dòng được định dạng đúng như SSE chứ không viết một JSON nhiều dòng tự do vào stream.

### 5.2. EventSource API

Trong browser:

```javascript
const source = new EventSource("/events");

source.addEventListener("tick", (event) => {
  console.log(event.lastEventId, event.data);
});

source.onerror = () => {
  console.log("SSE temporarily interrupted");
};

// Khi không còn cần nhận:
source.close();
```

`EventSource` tự quản lý kết nối GET, parse `text/event-stream`, dispatch events và mặc định thử reconnect khi kết nối bị mất/đóng theo điều kiện của chuẩn. Browser có thể dừng reconnect khi server trả status như `204 No Content` hoặc khi JavaScript gọi `close()`. Không viết logic dựa trên giả định mọi HTTP status/redirect sẽ dẫn đến cùng kiểu retry.

Với native `EventSource`, client không chủ động gửi các messages tùy ý ngược về server trên cùng stream. Một nút “hủy job” có thể gọi `fetch("/jobs/42/cancel", {method:"POST", ...})`, còn kết quả job được phát qua SSE. Đây là cách kết hợp phổ biến, đơn giản hơn WebSocket khi client chỉ gửi thao tác không thường xuyên.

### 5.3. Last-Event-ID không tự tạo độ tin cậy

Nếu browser đã nhận `id: 105`, khi reconnect nó có thể gửi:

```http
Last-Event-ID: 105
```

Server có thể đọc header và **truy vấn event store** để gửi các sự kiện sau ID đó. Nhưng `SseEmitter` không tự ghi event vào database và không tự replay. Nếu chỉ gửi event từ RAM, restart hoặc chuyển sang replica khác có thể khiến dữ liệu bị lỡ.

Muốn bảo đảm resume cần thiết kế:

1. ID có thứ tự/ý nghĩa trong một luồng, phù hợp scope user/job/tenant.
2. Event store hoặc durable log (database, Kafka, Redis Streams...) giữ các sự kiện đủ thời gian.
3. Server xác thực và authorize người gửi `Last-Event-ID` trước khi replay.
4. Server xác định khoảng thiếu và gửi lại **đúng dữ liệu được phép xem**.
5. Client xử lý duplicate hoặc gap bằng ID và idempotency.
6. Khi lịch sử đã bị xóa, client nhận tín hiệu reset/full resync rõ ràng.

**SSE không mặc định “exactly once delivery”.** Reconnect có thể khiến event lặp hoặc bị lỡ nếu chưa thiết kế persistence/dedup.

### 5.4. Heartbeat cho kết nối SSE

Proxy/load balancer thường cắt kết nối im lặng sau timeout. SSE có thể gửi comment `: heartbeat` định kỳ. Nó không làm event business thay đổi nhưng tạo lưu lượng để giữ chặng mạng hoạt động và phát hiện client disconnect sớm hơn.

Heartbeat phải phù hợp proxy idle timeout và chi phí kết nối. Nếu gửi quá dày trên hàng trăm nghìn clients, bandwidth và CPU sẽ tăng; nếu quá thưa, proxy có thể ngắt trước khi server gửi event tiếp theo. Cần đo ở tuyến thật.

## 6. WebSocket: message channel hai chiều

### 6.1. Handshake và trạng thái

Trong deployment `ws://` hoặc `wss://`, browser yêu cầu mở WebSocket bằng JavaScript:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.onopen = () => socket.send("hello");
socket.onmessage = (event) => console.log(event.data);
socket.onerror = () => console.log("Socket error");
socket.onclose = (event) => console.log(event.code, event.reason);
```

Với public website dùng HTTPS, WebSocket cũng nên dùng **`wss://`**. Browser có thể chặn mixed-content nếu trang HTTPS mở `ws://` không bảo mật. URL handshake có thể chịu ảnh hưởng context path, reverse proxy và host/port công khai.

Trạng thái browser `WebSocket.readyState` gồm `CONNECTING`, `OPEN`, `CLOSING`, `CLOSED`. Gọi `send()` khi chưa `OPEN` có thể lỗi; đừng đặt mọi message vào một mảng không giới hạn khi socket đang disconnected.

### 6.2. Message text và binary

WebSocket cung cấp **messages** với boundaries ở API, khác với raw HTTP byte stream. Có thể gửi text, `ArrayBuffer` hoặc `Blob` ở browser; server hỗ trợ text/binary handlers. Nhưng WebSocket protocol **không quy định business schema**: nếu dùng JSON cần tự định nghĩa `type`, `id`, `payload`, error/ack semantics.

Một message WebSocket có thể được chia thành nhiều **frames** ở wire protocol; tầng API thường trình bày message hoàn chỉnh cho ứng dụng. Đừng giả định một TCP packet = một WebSocket frame hay một business message.

### 6.3. WebSocket không mặc định reconnect/replay

Khi mạng bị gián đoạn hoặc server restart, browser WebSocket thường chuyển `CLOSED`; app cần tự reconnect, backoff có jitter, re-authentication, re-subscribe và resume state. Một socket mới **không tự nhớ** các subscriptions/messages của socket cũ. Nếu cần delivery bền, thiết kế IDs/acks, storage và cơ chế truy vấn những gì đã bỏ lỡ.

### 6.4. Ping/pong và heartbeat

WebSocket protocol có control frames `Ping`/`Pong` để kiểm tra kết nối. Server/client libraries có thể quản lý ping/pong; **browser WebSocket API không cho JavaScript gửi control-frame ping tùy ý**. Nếu muốn heartbeat cấp ứng dụng, có thể định nghĩa JSON message như `{"type":"ping"}` với phản hồi `pong`, nhưng phải phân biệt với WebSocket ping/pong protocol. Proxy idle timeout vẫn có thể yêu cầu heartbeat thường xuyên.

### 6.5. Khi nào WebSocket đáng dùng?

- Chat hai chiều với lượng messages thường xuyên;
- Phối hợp chỉnh sửa tài liệu real-time, multiplayer game;
- Client gửi lệnh hoặc thao tác liên tục mà server cần phản hồi/đẩy cập nhật ngay;
- Cần binary messages hoặc một protocol message riêng;
- Một kênh subscription phức tạp với nhiều loại lệnh/tương tác.

WebSocket đổi lại **connection state**, permission ở message level, backpressure, reconnect, heartbeat, broker/routing và lifecycle khó hơn. Với dashboard chỉ cần server phát cập nhật, SSE thường đơn giản hơn.

## 7. Dự án Spring Boot MVC Java 17+ minh họa cả ba

Một ứng dụng duy nhất phục vụ:

- `GET /stream/ndjson`: 5 JSON lines được gửi dần qua HTTP streaming.
- `GET /events`: 5 SSE events `tick` có `id`, `retry`.
- `GET /ws/echo`: WebSocket echo, server phản hồi mỗi text message.
- `GET /`: trang HTML cho phép thử cả ba trong browser.

Để demo **dễ kiểm chứng và không cần database**, dữ liệu là số thứ tự từ 1 đến 5. Không có authentication trong app mẫu; production phải bổ sung authorization, TLS và resource limits.

### 7.1. Khởi tạo Spring Boot 3.x

Từ [Spring Initializr](https://start.spring.io/), tạo Gradle/Groovy, Java 17+, **Spring Boot 3.x**, dependencies **Spring Web** và **WebSocket**. Trong `build.gradle` do Initializr tạo, dependencies cốt lõi:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **khối dependencies**, không phải `build.gradle` hoàn chỉnh độc lập; Initializr tạo plugins, repositories, version management và Gradle Wrapper. Với Boot 4.x cần kiểm tra tên starter và Spring Framework tương ứng; không trộn version.

Cấu trúc:

```text
src/main/
  java/demo/
    LongConnectionsApplication.java
    StreamConfiguration.java
    StreamController.java
    EchoHandler.java
    WebSocketConfiguration.java
  resources/
    application.properties
    static/index.html
```

### 7.2. LongConnectionsApplication.java

File `src/main/java/demo/LongConnectionsApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LongConnectionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(LongConnectionsApplication.class, args);
    }
}
```

`@SpringBootApplication` ở package `demo` quét các controller, handler/config beans bên dưới. Không cần Spring Security hay reactive dependencies để chạy demo MVC này.

### 7.3. StreamConfiguration.java: executor có giới hạn

Spring MVC streaming cần asynchronous request handling. Việc viết response vào Servlet `OutputStream` vẫn là **blocking I/O**, kể cả khi handler return sớm. Vì vậy ở production phải dùng một `AsyncTaskExecutor` được cấu hình phù hợp thay vì tin một executor mặc định không giới hạn là luôn an toàn.

File `src/main/java/demo/StreamConfiguration.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class StreamConfiguration {

    @Bean
    ThreadPoolTaskExecutor streamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("stream-demo-");
        executor.initialize();
        return executor;
    }

    @Bean
    WebMvcConfigurer mvcAsyncConfigurer(
            ThreadPoolTaskExecutor streamExecutor) {

        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(
                    AsyncSupportConfigurer configurer) {

                configurer.setTaskExecutor(streamExecutor);
                configurer.setDefaultTimeout(30_000L);
            }
        };
    }
}
```

Đây là cấu hình **lab với số lượng task có hạn**, không phải capacity planning đầy đủ. Dùng chung executor cho producer của SSE và MVC async writes trong demo; nhiều kết nối hơn khả năng pool có thể làm queue đầy/rejected và tăng latency. Với production, tách executor/luồng sự kiện phù hợp, đặt connection limits, bounded queues, metrics và xử lý rejection. Kể cả executor bounded, mỗi streaming response vẫn tiêu thụ socket, bộ đệm và tài nguyên của proxy.

`ThreadPoolTaskExecutor` được Spring quản lý vòng đời khi là bean. `configurer.setTaskExecutor` là điểm cấu hình MVC cho các tác vụ async như `StreamingResponseBody`. Trường hợp trả reactive types trên Spring MVC cũng cần executor xử lý blocking writes.

### 7.4. StreamController.java: NDJSON và SSE

File `src/main/java/demo/StreamController.java`:

```java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class StreamController {

    private final ThreadPoolTaskExecutor executor;

    public StreamController(ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    @GetMapping(
            path = "/stream/ndjson",
            produces = "application/x-ndjson")
    public StreamingResponseBody ndjson(HttpServletResponse response) {
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Accel-Buffering", "no");

        return outputStream -> {
            for (int i = 1; i <= 5; i++) {
                String line =
                        "{\"seq\":" + i + ",\"kind\":\"snapshot\"}\n";
                outputStream.write(
                        line.getBytes(StandardCharsets.UTF_8));
                outputStream.flush();

                try {
                    Thread.sleep(800);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        };
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(HttpServletResponse response) {
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Accel-Buffering", "no");

        SseEmitter emitter = new SseEmitter(30_000L);

        executor.execute(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    emitter.send(
                            SseEmitter.event()
                                    .id(Integer.toString(i))
                                    .name("tick")
                                    .reconnectTime(2_000L)
                                    .data("tick-" + i));
                    Thread.sleep(800);
                }
                emitter.complete();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                emitter.complete();
            } catch (IOException ex) {
                // Client đã ngắt; container thực hiện async error handling.
            } catch (RuntimeException ex) {
                emitter.completeWithError(ex);
            }
        });

        return emitter;
    }
}
```

**Cơ chế NDJSON:**

- `StreamingResponseBody` viết từng dòng JSON hoàn chỉnh theo byte UTF-8.
- `flush()` yêu cầu đẩy dữ liệu nhưng không đảm bảo bytes tới ngay browser nếu proxy/browser có buffering.
- Sau mỗi dòng, worker ngủ 800 ms để bạn dễ quan sát. **Không dùng `Thread.sleep` để tạo hoạt động production**; demo dùng delay giả lập.
- Khi callback hoàn thành, HTTP response kết thúc. Không có `Last-Event-ID` hay reconnect chuẩn cho NDJSON.
- `Cache-Control: no-store` làm rõ không cache content stream của demo. Header này không tự tắt gzip; production xem riêng buffering/compression.

**Cơ chế SSE:**

- `SseEmitter` format events theo chuẩn SSE.
- `id(1..5)` giúp browser nhận dạng từng event nhưng bản demo **không lưu replay store**.
- `reconnectTime(2_000L)` là gợi ý retry 2 giây. Khi emitter hoàn tất sau 5 sự kiện, **EventSource vẫn có thể reconnect** vì response đã đóng; trang HTML demo sẽ gọi `close()` khi nhận ID 5.
- Nếu `send()` ném `IOException` do client mất kết nối, Spring MVC/container xử lý async error dispatch; không nhất thiết gọi `completeWithError` trên IOException theo tài liệu Spring.
- Nếu có lỗi runtime khác, `completeWithError` thông báo cho Spring hoàn tất luồng bằng exception path. Khi headers đã gửi, không được giả định có thể đổi response status/body theo cách HTTP thông thường.

**Một khác biệt quan trọng:** response streaming thường gửi **một** callback theo MVC async executor. `SseEmitter` có thể giữ request mở và được gửi từ thread/service khác. Để broadcast hàng nghìn subscribers, không tạo `Thread.sleep`/một thread cho mỗi subscriber như bài demo; dùng event bus và chiến lược dispatch/buffer phù hợp.

### 7.5. EchoHandler.java: WebSocket echo

File `src/main/java/demo/EchoHandler.java`:

```java
package demo;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        String payload = message.getPayload();

        if (payload.length() > 1024) {
            session.sendMessage(
                    new TextMessage("error: message too long"));
            return;
        }

        session.sendMessage(new TextMessage("echo: " + payload));
    }
}
```

Server nhận text message rồi gửi reply trên **cùng WebSocket session**, khác với NDJSON/SSE chỉ gửi event từ server qua HTTP response. Phần check dài 1024 ký tự chỉ là logic demo; production phải cấu hình thêm **WebSocket frame/message limits ở server/container**, vì payload lớn đã có thể chiếm bộ nhớ trước khi handler thực thi.

Ở ví dụ này, chỉ callback xử lý input gửi reply, không có các publisher threads gửi cùng lúc. Khi nhiều threads muốn gửi qua cùng `WebSocketSession`, cần đảm bảo **không concurrent send bừa bãi**; Spring cung cấp `ConcurrentWebSocketSessionDecorator` hoặc một single-writer queue. Không mặc định `sendMessage` thread-safe với mọi WebSocket engine.

### 7.6. WebSocketConfiguration.java: đăng ký đường handshake

File `src/main/java/demo/WebSocketConfiguration.java`:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoHandler handler;

    public WebSocketConfiguration(EchoHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {

        registry.addHandler(handler, "/ws/echo");
    }
}
```

`@EnableWebSocket` với `WebSocketConfigurer` đăng ký raw `WebSocketHandler`. Không cần STOMP message broker cho một echo channel đơn giản. Spring mặc định hạn chế các origin được phép cho WebSocket handshake (same-origin theo cấu hình tiêu chuẩn); demo browser tải trang và kết nối trên cùng host/port. **Không thêm `setAllowedOriginPatterns("*")` để chữa mọi lỗi handshake**, vì trình duyệt WebSocket không bị same-origin policy hạn chế y hệt `fetch` và cần origin validation tại server.

### 7.7. static/index.html: test cả ba trong browser

File `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>HTTP stream, SSE va WebSocket</title>
</head>
<body>
  <h1>Demo ket noi dai</h1>

  <button id="ndjson">Stream NDJSON</button>
  <button id="sse">Open SSE</button>
  <button id="ws">WebSocket echo</button>
  <button id="stop">Stop connections</button>
  <pre id="output"></pre>

  <script>
    const output = document.querySelector("#output");
    const log = (line) => {
      output.textContent += line + "\n";
    };

    let source = null;
    let socket = null;
    let abort = null;

    document.querySelector("#ndjson").onclick = async () => {
      abort?.abort();
      abort = new AbortController();

      try {
        const response = await fetch("/stream/ndjson", {
          signal: abort.signal
        });
        if (!response.ok || !response.body) {
          throw new Error("HTTP status " + response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const result = await reader.read();

          if (result.done) {
            buffer += decoder.decode();
            if (buffer.trim()) log("last: " + buffer);
            break;
          }

          buffer += decoder.decode(result.value, { stream: true });
          let newline = buffer.indexOf("\n");

          while (newline !== -1) {
            const line = buffer.slice(0, newline).trim();
            buffer = buffer.slice(newline + 1);

            if (line) {
              log("NDJSON: " + JSON.stringify(JSON.parse(line)));
            }
            newline = buffer.indexOf("\n");
          }
        }
        log("NDJSON complete");
      } catch (error) {
        log("NDJSON stopped/error: " + error.message);
      }
    };

    document.querySelector("#sse").onclick = () => {
      source?.close();
      source = new EventSource("/events");

      source.addEventListener("tick", (event) => {
        log("SSE id=" + event.lastEventId +
            " data=" + event.data);

        // Demo stream hữu hạn: chặn reconnect sau event cuối.
        if (event.lastEventId === "5") {
          source.close();
          log("SSE closed by browser");
        }
      });

      source.onerror = () => log("SSE interrupted/reconnecting");
    };

    document.querySelector("#ws").onclick = () => {
      socket?.close();

      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const url = protocol + "//" + location.host + "/ws/echo";
      socket = new WebSocket(url);

      socket.onopen = () => {
        log("WebSocket OPEN");
        socket.send("hello");
      };
      socket.onmessage = (event) => {
        log("WebSocket: " + event.data);
      };
      socket.onclose = (event) => {
        log("WebSocket CLOSED code=" + event.code);
      };
      socket.onerror = () => log("WebSocket error");
    };

    document.querySelector("#stop").onclick = () => {
      abort?.abort();
      source?.close();
      socket?.close();
      log("All browser connections stopped");
    };
  </script>
</body>
</html>
```

Trình duyệt tải `http://localhost:8080/` và dùng nút để thử. Dữ liệu từ server được đưa qua `textContent` thay vì `innerHTML`; trong app thực phải kiểm soát nội dung người dùng, authorization và DOM injection tương ứng.

Bộ đọc NDJSON giữ một `buffer` vì một lần `reader.read()` có thể chứa nửa dòng hoặc nhiều dòng. `EventSource` lại tự làm parse `event:`/`data:` và dispatch. `WebSocket` gửi message khi `onopen`, nhận phản hồi trong `onmessage`.

Đây là demo một trang đơn giản, **không có app-level retry queue hoặc replay**. Nút Stop chủ động hủy HTTP stream, đóng EventSource và gửi WebSocket close. Khi server restart, HTTP stream bị cắt; SSE browser có thể reconnect, WebSocket browser không tự mở socket mới.

### 7.8. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.mvc.async.request-timeout=30s

# Tắt compression ở lab để xem từng chunk/event rõ hơn.
server.compression.enabled=false
```

`spring.mvc.async.request-timeout` đặt giới hạn cho các async requests trong MVC, nhưng mỗi `SseEmitter` cũng có timeout riêng (30.000 ms) trong code. Trong production, phải phối hợp với proxy idle/read timeouts và chiến lược kết thúc stream; tăng timeout lên vô hạn không giải quyết vấn đề mất client hoặc thiếu giới hạn tài nguyên.

### 7.9. Chạy ứng dụng

Từ thư mục root có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các Java files sử dụng Spring MVC/WebSocket APIs, không chạy độc lập bằng `javac StreamController.java` nếu không cung cấp classpath. Initializr và Gradle Wrapper sẽ quản lý compile/runtime dependencies. Mặc định ví dụ lắng nghe `http://localhost:8080` nếu port trống.

Truy cập trang `http://localhost:8080/` trong browser và thử các nút. Với source đúng như trên, nút WebSocket sẽ ghi:

```text
WebSocket OPEN
WebSocket: echo: hello
```

Đây là hai dòng chính; khi bạn đóng kết nối, trang còn có dòng CLOSED/Stop tương ứng. Thứ tự một số event phụ thuộc scheduling/network, nhưng echo payload là cố định.

## 8. Kiểm thử HTTP streaming bằng curl

Mở terminal trong khi `bootRun` đang chạy:

```bash
curl -N -i http://localhost:8080/stream/ndjson
```

`-N`/`--no-buffer` bảo curl không buffer output ở phía client. Bạn sẽ lần lượt nhận phần body:

```jsonl
{"seq":1,"kind":"snapshot"}
{"seq":2,"kind":"snapshot"}
{"seq":3,"kind":"snapshot"}
{"seq":4,"kind":"snapshot"}
{"seq":5,"kind":"snapshot"}
```

Đây là **body chính xác của callback**, bỏ qua headers và thời gian đến từng dòng. Các dòng được tạo với khoảng nghỉ 800 ms giữa các lượt; nếu proxy buffering hoặc terminal buffering xảy ra, bạn có thể không thấy từng dòng ngay dù code đã gọi `flush()`.

Thử client thường:

```bash
curl -i http://localhost:8080/stream/ndjson
```

Output có thể trông “đổ cả một cục” do buffer đầu cuối; điều đó không chứng minh server không stream. So sánh `curl -N`, browser Network timing và packet/edge logs.

**Không dùng `curl --compressed` để kiểm tra “từng lần flush” khi gzip đang bật**, vì compressor/proxy có thể gom output. Demo tắt compression ở `application.properties` để giảm biến số.

## 9. Kiểm thử SSE bằng curl và browser

```bash
curl -N -i -H 'Accept: text/event-stream' \
  http://localhost:8080/events
```

Header dự kiến gồm `Content-Type: text/event-stream`; body tương đương:

```text
id: 1
event: tick
retry: 2000
data: tick-1

id: 2
event: tick
retry: 2000
data: tick-2

...
id: 5
event: tick
retry: 2000
data: tick-5

```

Đây là **mẫu biểu diễn các trường**, không phải cam kết thứ tự field hoặc khoảng trắng của serializer trong mọi Spring Framework version. Điều quan trọng: mỗi event có tên `tick`, ID `1..5` và data `tick-1..tick-5`; giữa các events có dòng trống.

Nếu gọi thẳng bằng `curl`, khi server hoàn tất response, `curl` kết thúc; curl **không phải EventSource** nên không tự reconnect. Browser `EventSource` có reconnect, nhưng trang demo chủ động `close()` khi nhận `lastEventId === "5"`.

### 9.1. Nhận sự kiện đặt tên

```javascript
const source = new EventSource("/events");

source.onmessage = (event) => {
  console.log("default message:", event.data);
};

source.addEventListener("tick", (event) => {
  console.log("named tick:", event.data);
});
```

Vì server phát `event: tick`, client nên nghe bằng `addEventListener("tick", ...)`. `onmessage` dùng cho các event không có tên custom hoặc event loại `message` theo quy tắc chuẩn, nên nếu chỉ viết `onmessage` có thể tưởng server không gửi gì.

### 9.2. Thử Last-Event-ID theo yêu cầu

```bash
curl -N -H 'Last-Event-ID: 3' \
  http://localhost:8080/events
```

Trong demo, server **không đọc header**, vì vậy vẫn gửi từ `id: 1`. Đây không phải bug của SSE parser: ứng dụng chưa triển khai replay. Một service thật cần:

```java
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events(
        @RequestHeader(value = "Last-Event-ID", required = false)
        String lastEventId) {
    // Xác thực người dùng và cursor.
    // Query durable event store để replay sau lastEventId.
    // Sau đó stream các event mới cùng luồng.
    throw new UnsupportedOperationException("Illustrative only");
}
```

Đây là **snippet thiết kế, không chạy độc lập**, cố ý nêu rõ phần còn thiếu. Không copy nguyên `UnsupportedOperationException` vào demo đang chạy. Khi production triển khai replay, xử lý cursor sai/hết hạn, event thuộc tenant khác, race giữa replay và live subscribe, dedup và gap detection.

## 10. Kiểm thử WebSocket đúng công cụ

`curl` thông thường chỉ phù hợp kiểm tra HTTP upgrade headers ở mức thấp, **không phải WebSocket client hoàn chỉnh** để gửi/nhận frames đúng chuẩn. Dùng browser button trong trang demo hoặc WebSocket client chuyên dụng như `wscat`, `websocat`, Postman WebSocket mode hay tool khác.

Ví dụ một client dòng lệnh đã cài `websocat`:

```bash
websocat ws://localhost:8080/ws/echo
```

Sau khi kết nối, nhập:

```text
hello
```

Phản hồi:

```text
echo: hello
```

`websocat` là **công cụ ngoài**, không được tự cài bởi dự án Spring Boot. Không có nó thì dùng browser; không yêu cầu lệnh `curl -X POST /ws/echo` vì WebSocket handshake không phải một POST API JSON thông thường.

### 10.1. Có thể kiểm tra handshake nhưng chưa đủ

Một handshake HTTP/1.1 thường có `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key` và `Sec-WebSocket-Version: 13`; server trả 101 và `Sec-WebSocket-Accept` đúng. Sau đó phải đọc/ghi WebSocket frames theo protocol. Kể cả thấy 101 cũng **chưa chứng minh** echo messaging, authorization hoặc reconnect hoạt động.

### 10.2. Browser WebSocket khác raw HTTP requests

`new WebSocket("ws://...")` khởi tạo connection và một protocol object. Sau khi `onopen`, `send("hello")` gửi một WebSocket **message**, không phải một HTTP request mới. `onmessage` cũng không chứa một HTTP status per message. Muốn báo lỗi nghiệp vụ, định nghĩa message schema (ví dụ `{"type":"error","code":"INVALID_ROOM"}`) hoặc đóng socket bằng close code phù hợp.

## 11. Proxy/ingress: điểm streaming hay bị hỏng nhất

Một app chạy tốt khi truy cập trực tiếp `localhost:8080` có thể thất bại sau reverse proxy/CDN do:

- Proxy buffering giữ NDJSON/SSE cho tới khi đủ lớn hoặc response kết thúc;
- Nén gzip giữ bytes cho tới khi flush block;
- Idle timeout làm SSE/WebSocket bị cắt khi không có heartbeat;
- Proxy không chuyển các headers WebSocket `Upgrade`/`Connection`;
- CDN không hỗ trợ WebSocket hoặc cố cache stream;
- Upstream/downstream dùng HTTP versions khác nhau với cấu hình sai;
- TLS termination dẫn tới browser HTTPS nhưng app tạo `ws://` thay vì `wss://`;
- Rolling deploy ngắt các socket còn sống mà client không có resume.

### 11.1. NGINX minh họa cho ba loại đường dẫn

Giả sử NGINX chạy cùng host và proxy tới Spring Boot ở `127.0.0.1:8080`. Một cấu hình mẫu có `map` ở **ngữ cảnh http**:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 8081;
    server_name localhost;

    location /stream/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 90s;
        gzip off;
    }

    location /events {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 90s;
        gzip off;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 90s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
    }
}
```

Đây là **snippet NGINX không có đầy đủ nginx.conf** và sử dụng **HTTP local** để debug. Production cần HTTPS, hostname/Host forwarding, forwarded scheme, network policies, security headers và ingress trust boundary. Nếu NGINX nằm trong container khác, `127.0.0.1` có thể trỏ về chính container NGINX; thay bằng service DNS thực tế.

Giải thích:

- `proxy_buffering off` cố gắng chuyển các bytes streaming sớm thay vì đệm toàn response.
- `gzip off` trên hai routes giúp tránh gom từng event/chunk ở compression layer trong lab; production có thể cân nhắc compression cho stream nếu flush/latency được đảm bảo.
- `proxy_read_timeout 90s` là **khoảng chờ giữa các lần đọc từ upstream**, không phải thời gian sống tối đa chính xác của kết nối.
- WebSocket `Upgrade` là hop-by-hop header; NGINX cần chuyển thông tin cần thiết sang upstream và thiết lập tunnel khi handshake thành công.
- `map` dùng để đặt `Connection: upgrade` khi có Upgrade request và `close` khi không có.
- `proxy_http_version 1.1` đảm bảo có một upstream hop HTTP/1.1 phù hợp cho demo WebSocket. Với các bản NGINX rất mới, default có thể khác; đặt tường minh hữu ích khi minh họa.
- Khi route là `/events` hoặc `/ws/echo`, path public/URI phải khớp đường backend; thay đổi trailing slash trong `proxy_pass` có thể rewrite URI không mong muốn.

### 11.2. X-Accel-Buffering: no

Trong controller có:

```java
response.setHeader("X-Accel-Buffering", "no");
```

NGINX có thể dùng header này để điều khiển buffering khi không bị cấu hình bỏ qua. Nó **không phải tiêu chuẩn HTTP áp dụng cho mọi CDN/reverse proxy**; proxy khác có thể không hiểu. Vì vậy vẫn cần kiểm tra cấu hình ở từng hop. Nếu cache layer cố lưu response `text/event-stream`, cần bypass cache; bảo vệ privacy bằng `Cache-Control` và edge policies tương ứng.

### 11.3. Heartbeat so với timeout

Ví dụ proxy cắt stream nếu không nhận dữ liệu upstream trong 60 giây. Một SSE chỉ có event mỗi 5 phút nên gửi `: heartbeat` sau khoảng phù hợp (ví dụ 15–25 giây, tùy hạ tầng) để giữ kết nối và phát hiện ngắt. Với WebSocket, server có thể gửi protocol Ping frames hoặc heartbeat messages và kiểm tra Pong/timeout. **Không hứa heartbeat có thể ngăn mọi disconnect:** mạng di động, NAT, browser sleep, pod restart vẫn có thể đóng socket.

### 11.4. HTTP/2 không biến WebSocket thành SSE

SSE và NDJSON streaming chạy qua HTTP/1.1, HTTP/2 hoặc HTTP/3 tùy stack; format application vẫn vậy. WebSocket browser thông dụng dùng HTTP/1.1 Upgrade, còn một số hạ tầng hỗ trợ HTTP/2 extended CONNECT. Đừng copy config Upgrade HTTP/1.1 rồi mặc định mọi hop HTTP/2 tự thực hiện. Kiểm tra ingress/proxy/controller thật cùng browser.

## 12. Timeout và giới hạn tài nguyên

### 12.1. Ba nhóm timeout

| Timeout | Tầng | Hậu quả thường gặp |
| --- | --- | --- |
| MVC async request timeout | Spring MVC/Servlet | `StreamingResponseBody`/`SseEmitter` có thể bị timeout |
| Reverse proxy upstream read timeout | NGINX/LB/Ingress | Cắt stream nếu không có bytes trong khoảng yêu cầu |
| WebSocket idle/ping timeout | WebSocket engine/proxy | Socket bị đóng nếu idle quá lâu hoặc ping/pong không đáp ứng |

Ngoài ra còn TCP keep-alive, browser/mobile network timeout, CDN limits, application-specific session TTL, auth token expiry và rolling-deployment termination. Tăng một property không thể thay toàn bộ các giới hạn.

### 12.2. Thread và memory của Spring MVC

Spring MVC có asynchronous request processing, nhưng các lần write vào Servlet response vẫn **blocking** theo mô hình I/O của Servlet. Với hàng nghìn kết nối stream dữ liệu lớn, cần bounded worker pool và kiểm soát slow clients. Một request có thể giữ socket, response buffers, app resources và context trong thời gian dài dù request thread ban đầu đã được giải phóng.

`ThreadPoolTaskExecutor` trong demo là mô hình cơ bản, không được hiểu là có thể chịu vô hạn connections; khi pool/queue hết, app phải trả/ghi nhận lỗi có kiểm soát và chủ động giới hạn concurrent streams. Không chạy `Executors.newCachedThreadPool()` cho mỗi request hoặc spawn vô hạn `new Thread()`.

### 12.3. Backpressure là gì?

**Backpressure** là cơ chế phối hợp tốc độ sinh dữ liệu và tốc độ tiêu thụ để producer không tạo dữ liệu nhanh hơn consumer mãi mãi. Nếu server phát 1.000 events/s còn client chỉ xử lý 50 events/s, dữ liệu có thể dồn trong memory, TCP buffers, queue hoặc broker.

Các chiến lược:

- Giới hạn queue size và message size.
- Áp dụng backpressure/demand qua reactive streams khi dùng WebFlux, nhưng vẫn xét buffering ở network/client.
- Với dữ liệu live có thể bỏ qua, giữ “latest value” thay vì mọi tick.
- Với dữ liệu phải lưu đủ, dùng durable broker/log và client cursor/ack.
- Slow clients có thể bị ngắt có kiểm soát để bảo vệ toàn hệ thống.
- Định nghĩa business SLA về data loss, latency, ordering và replay.

WebSocket browser có `bufferedAmount` để đo bytes được queue cho `send()` ở phía browser; nó không tự bảo đảm server xử lý kịp. API browser WebSocket thông thường **không cung cấp backpressure đầy đủ** như Reactive Streams. SSE cũng không tự làm producer chậm đi theo client; `SseEmitter.send()` có thể block/error tùy transport và client.

### 12.4. Số lượng connections

Với SSE qua HTTP/1.1, browser có giới hạn thực tế về số connections tới cùng origin (thường khoảng 6 trong nhiều browser khi không dùng HTTP/2). Nhiều tab + nhiều EventSource connections có thể vượt hạn mức; HTTP/2 multiplex stream sẽ thay đổi giới hạn thực tế theo negotiated concurrent streams. Đừng mở một SSE connection cho mỗi widget nếu có thể dùng một stream và phân loại `event:`.

WebSocket cũng có giới hạn sockets, file descriptors, memory, load balancer capacity và browser/network. Không có công nghệ nào cho phép 100.000 connections chỉ bằng một annotation mà không phải capacity plan.

## 13. Reconnect, delivery và server restart

### 13.1. HTTP streaming bình thường

Khi response bị cắt ở dòng thứ 3, client cần tự quyết định request mới có bắt đầu từ đầu hay từ seq tiếp theo. Nếu có cursor:

```http
GET /stream/ndjson?after=3
```

Server có thể query durable store và phát từ seq 4. **Đây là API thiết kế thêm**, không có trong demo. Với file download, HTTP Range/ETag có thể hỗ trợ resume byte-level; với NDJSON business events, cursor record-level thường phù hợp hơn.

### 13.2. SSE

`EventSource` có reconnect và gửi `Last-Event-ID` theo chuẩn. Điều này **chỉ giúp client chuyển ID đã thấy**. Nếu server mới sau restart không lưu event cũ, những event tạo trong lúc downtime vẫn có thể mất. Dùng event store/broker nếu cần delivery đáng tin, không trông chờ vào tính năng có sẵn của `SseEmitter`.

### 13.3. WebSocket

WebSocket có thể đóng với close code `1000` (normal), `1001` (going away), `1006` (abnormal closure được API báo, không phải wire close frame) hoặc các code khác. Ứng dụng nên phân biệt đóng chủ động với mất mạng/server error; dùng reconnect backoff có jitter và timeout. Sau reconnect cần authentication, resubscribe, đồng bộ state và replay/dedup theo message ID.

### 13.4. Event delivery guarantees

| Đảm bảo | Cần gì? |
| --- | --- |
| Best effort | Gửi cho clients đang kết nối; có thể mất khi disconnect |
| At-most-once | Không replay, có thể mất; tránh duplicate theo thiết kế |
| At-least-once | Lưu event + retry/replay + ACK hoặc cursor; client dedup vì có thể lặp |
| Exactly-once business effect | Idempotent processing, transaction/unique constraints/dedup store; protocol một mình không bảo đảm |

Cùng một socket hoặc cùng một TCP connection không biến mọi business action thành exactly-once. Nếu dùng WebSocket để tạo đơn/thanh toán, yêu cầu server gắn idempotency key và ghi trạng thái bền vững giống HTTP POST.

## 14. Nhiều replicas, broadcast và broker

Xét hai Spring Boot pods A và B. Browser 1 giữ SSE connection tới A; Browser 2 giữ WebSocket connection tới B. Một event được tạo ở A:

```text
Business event created at A
            |
            v
Need to reach clients on A AND B
            |
      +-----+------+
      | shared bus |
      +-----+------+
         |      |
         v      v
        Pod A   Pod B
         |      |
      SSE/WS   SSE/WS
       clients  clients
```

Nếu chỉ lưu `List<SseEmitter>` hoặc `Map<WebSocketSession>` trong RAM của A, B không thấy connections đó. Cần một **pub/sub hoặc broker dùng chung**, trong khi mỗi pod quản lý physical client connections của mình. Các lựa chọn gồm Redis Pub/Sub (không durable), Redis Streams, Kafka, RabbitMQ hoặc service chuyên cho realtime; chọn theo durability, ordering, latency và nhu cầu.

Với Spring WebSocket messaging, **STOMP** là protocol bổ sung để routing messages theo destinations (`/topic`, `/queue`, `/app`), không phải phần bắt buộc của raw WebSocket. Spring có **simple in-memory broker** cho demo, nhưng nó không phù hợp clustering; muốn broadcast qua nhiều app nodes có thể dùng **STOMP broker relay** đến broker chuyên dụng.

**Không kết luận rằng dùng STOMP = giao hàng bền vững.** Việc ack, receipts, transactions, persistent queues, replay và retry phụ thuộc broker, protocol/subscription mode và cấu hình thực tế.

### 14.1. Sticky sessions và failover

Session affinity có thể giữ một client kết nối tới cùng instance trong suốt connection, nhưng khi pod bị thay, connection vẫn rớt. Khi client reconnect qua node khác, state của subscription phải được tạo lại hoặc lấy từ shared store. Sticky sessions không thay durable events hoặc broker.

### 14.2. Rollout và graceful shutdown

Khi deploy:

1. Đánh dấu pod đang draining, ngừng nhận kết nối mới.
2. Cho app hoàn tất response hữu hạn nếu trong hạn cho phép.
3. Với SSE/WS dài hạn, có thể báo client nối lại hoặc đóng có kiểm soát.
4. Client reconnect với jitter để tránh hàng nghìn connections đồng loạt tạo spike.
5. Resume bằng cursor/event ID hoặc tải snapshot mới để khôi phục state.

Graceful shutdown **không thể giữ nguyên một TCP socket qua việc JVM chết và tạo process mới**. Nó chỉ giúp giảm lỗi và cho client chuyển trạng thái hợp lý.

## 15. Bảo mật HTTP stream, SSE và WebSocket

### 15.1. Authentication và authorization

Các endpoint streaming có thể dùng Spring Security session, OAuth2 resource server/JWT, API key/mTLS hoặc identity phù hợp. **Không coi chỉ cần mở socket là mọi message sau đó đều được phép.**

- HTTP streaming: authorize GET + resource/job/tenant; tránh việc client đoán ID của người khác.
- SSE: authorize kết nối, rồi kiểm tra mỗi subscription/job/event được phép xem; token/role có thể thay đổi trong lúc stream còn mở.
- WebSocket: authorize handshake **và từng message/action**, kiểm tra message schema, rate limit, room membership và quyền gửi vào destination.
- Khi session/token bị thu hồi, ứng dụng phải quyết định có ngắt các connections đang mở hay không, vì một handshake thành công trước đó không bảo đảm quyền mãi mãi.

### 15.2. CORS và browser EventSource

SSE dựa trên HTTP GET nên chịu các chính sách browser cross-origin. Với kết nối sang origin khác, `EventSource` có tùy chọn:

```javascript
const stream = new EventSource("https://api.example.test/events", {
  withCredentials: true
});
```

Nếu dùng cookies/credentials cross-origin, server cần CORS allowlist chính xác, `Access-Control-Allow-Credentials` và cookie `SameSite`/`Secure` phù hợp. Native `EventSource` **không cho đặt Authorization header tùy ý** như `fetch`; với bearer tokens có thể cân nhắc same-origin BFF/cookie auth đúng CSRF policy, hoặc client HTTP streaming bằng `fetch` với custom headers khi cần. **Không đưa access token dài hạn vào query string** nếu tránh được vì URL có thể bị log/referrer/history lộ.

### 15.3. WebSocket Origin và Cross-Site WebSocket Hijacking

Browser WebSocket API không bị ràng buộc bởi same-origin policy giống `fetch`. Một trang độc hại có thể cố mở WebSocket đến service của bạn; nếu cookie được tự gửi cùng handshake và server không kiểm tra `Origin`, có nguy cơ **Cross-Site WebSocket Hijacking**.

Dùng:

- Origin allowlist chặt, không dùng wildcard `*` bừa bãi;
- Authentication/session/token hoặc channel binding phù hợp;
- Authorization per message/room/tenant;
- CSRF/handshake token theo cơ chế hệ thống nếu cần;
- TLS `wss://`, hạn chế số kết nối và kích thước message.

`Origin` kiểm soát browser use cases nhưng client không phải browser có thể tự đặt/fake header, nên **Origin không thay authentication**. Spring raw WebSocket config mặc định có kiểm tra same-origin trong nhiều cấu hình, nhưng phải xác minh behavior khi tự tùy chỉnh endpoint/handshake.

### 15.4. Dữ liệu nhạy cảm và caching

SSE/NDJSON user-specific không nên bị CDN shared cache. Có thể dùng `Cache-Control: no-store` cùng CDN bypass policy để tránh lưu nhầm. WebSocket messages không nằm trong HTTP response cache nhưng vẫn có thể bị log bởi app, gateway, observability hoặc browser devtools; đừng gửi secrets không cần thiết.

Nếu muốn stream dữ liệu riêng, kiểm tra quyền trước khi bắt đầu và giữa vòng đời dài; ngắt/refresh khi user logout, quyền bị thu hồi hoặc job bị hủy.

### 15.5. Input validation và rate limits

WebSocket cần giới hạn max message size, connections/user, messages/s, subscription count, total buffer size. HTTP streaming và SSE cần giới hạn concurrent subscribers, heartbeat frequency, server event size và producer queue. Một client chậm/malicious có thể giữ connection và tiêu tốn sockets/threads lâu hơn request bình thường.

## 16. WebFlux: cách biểu diễn khác với Spring MVC

Trong **Spring WebFlux**, phản hồi dữ liệu theo luồng thường dùng Project Reactor `Flux<T>`. WebFlux có non-blocking I/O và Reactive Streams backpressure trong chuỗi xử lý, khác với Spring MVC `StreamingResponseBody` dùng blocking response writes trên async executor.

Ví dụ SSE WebFlux **snippet độc lập với dự án MVC ở mục 7**:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping(path = "/reactive/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(i -> ServerSentEvent.<String>builder()
            .id(Long.toString(i + 1))
            .event("tick")
            .data("tick-" + (i + 1))
            .build());
}
```

Đây là **method snippet** cần một `@RestController` trong dự án `spring-boot-starter-webflux`, không phải class biên dịch độc lập. Dòng `Flux.interval` phát các giá trị 0..4, được ánh xạ thành ID 1..5. `Flux` kết thúc sau 5 events; browser EventSource vẫn có thể reconnect nếu client không chủ động đóng.

WebFlux có thể trả `Flux<YourDto>` với streaming media type như `application/x-ndjson` hoặc `Flux<ServerSentEvent<?>>` cho SSE. Không suy rằng trả `Flux` với `application/json` sẽ luôn gửi từng item ngay lập tức: media type/encoder quyết định flush semantics.

### 16.1. WebSocket reactive

WebFlux dùng `org.springframework.web.reactive.socket.WebSocketHandler`, `WebSocketSession.receive()`/`send(Publisher<WebSocketMessage>)` và mapping handler reactive. Nó **không phải** raw MVC `TextWebSocketHandler`. Với WebFlux, không nên block event-loop bằng `Thread.sleep` hoặc JDBC synchronous calls trực tiếp; dùng reactive APIs hoặc offload đúng scheduler.

### 16.2. Backpressure không xuyên suốt mọi tầng một cách thần kỳ

Reactive Streams giúp producer/consumer trong pipeline phối hợp demand, nhưng browser native WebSocket API vẫn có buffering riêng, network/TCP có cơ chế flow control riêng, và một message broker có queue chính sách riêng. Phải đo end-to-end, nhất là khi WebFlux gửi cho client chậm.

## 17. Chọn công nghệ theo tình huống

| Tình huống | Gợi ý | Lý do và giới hạn |
| --- | --- | --- |
| Tạo báo cáo CSV nhiều GB | HTTP response streaming/download | Byte stream phù hợp; cần backpressure, Content-Disposition, Range/resume nếu cần |
| Tiến độ xử lý tác vụ | SSE nếu chỉ cần push; hoặc polling nếu cập nhật hiếm | Server phát trạng thái, nút Cancel vẫn dùng HTTP POST |
| Log build/deploy đang chạy | SSE hoặc NDJSON | SSE tiện EventSource/reconnect metadata; NDJSON tiện CLI và parser tùy chỉnh |
| Thông báo đơn hàng | SSE | Server→client; replay store để không bỏ lỡ notification |
| Dashboard giá/metrics | SSE nếu một chiều, WebSocket nếu cần lệnh tương tác thường xuyên | Cân bằng tần suất, số client và message semantics |
| Chat hai chiều | WebSocket | Client/server cùng gửi messages liên tục; cần auth, broker, persistence |
| Game multiplayer hoặc collaborative editor | WebSocket | Bi-directional low-latency messaging; ordering/reconciliation vẫn do ứng dụng |
| File binary streaming | HTTP streaming hoặc WebSocket theo yêu cầu | SSE chỉ text; tải file thường HTTP tiện caching/range hơn |
| Webhook giữa hai services | HTTP POST thông thường | Kết nối dài không bắt buộc, dùng delivery/retry/idempotency |
| Một giá trị JSON sau 100 ms | HTTP JSON thường | Đơn giản và dễ cache hơn stream |
| Gửi dữ liệu theo thời gian từ IoT device | HTTP upload streaming hoặc WebSocket tùy thiết kế | Không chọn SSE cho client→server stream vì SSE chỉ server→client |
| Mobile client bị ngắt mạng thường xuyên | Bất kỳ cách nào với durable cursor/ACK | Reconnect/replay quan trọng hơn chọn transport |

**Quy tắc nhanh:** chỉ cần *server đẩy event* và thích browser API đơn giản → xem xét SSE; muốn *tải nội dung lớn/tạo dần* → HTTP streaming; cần *hai chiều tương tác liên tục* → WebSocket. Với tần suất thấp và số clients lớn, **polling có điều kiện** đôi khi đơn giản và đủ tốt; không mặc định kết nối dài là tối ưu.

## 18. Quan sát, kiểm thử và vận hành

### 18.1. Metrics hữu ích

- Active streams/SSE emitters/WebSocket sessions theo pod và theo người dùng (tránh PII trong labels).
- Connection opens/closes, abnormal close codes, reconnect rate.
- Tuổi thọ kết nối, thời gian không có event, heartbeat failures.
- Bytes/messages per second, queue depth và số rejected tasks.
- Emitter send latency, blocked writer threads, proxy buffering delay.
- Dropped messages, duplicate IDs, replay gaps và độ trễ end-to-end.
- Memory/heap, GC, file descriptors, CPU, thread pool utilization.
- Số 401/403 khi handshake/subscribe và số sự kiện vượt quyền bị chặn.
- Proxy 499/502/504 hoặc trạng thái tương đương, load balancer idle resets, CDN behavior.

**Không log raw Authorization/cookies, tokens, toàn bộ private message payload hoặc user ID như metric label**. Dùng correlation IDs an toàn với retention có kiểm soát.

### 18.2. Ma trận thử lỗi

1. Chạy NDJSON/SSE/WebSocket trực tiếp trên `localhost:8080`; xác minh payload/time.
2. Chạy cùng endpoints qua NGINX/ingress/CDN; so thời gian từng event đến client.
3. Cố tình bật `proxy_buffering on` cho SSE trên môi trường test, quan sát khác biệt.
4. Giảm proxy read timeout dưới khoảng cách giữa heartbeats; đo disconnect.
5. Ngắt Wi-Fi/VPN, sleep browser tab, thay mạng mobile; quan sát reconnect và replay.
6. Restart Spring Boot khi SSE/WebSocket đang mở; xác nhận kết nối cũ đóng và client phục hồi theo logic đã viết.
7. Đặt nhiều replicas; xác nhận event từ A tới subscriber ở B qua broker.
8. Gửi messages lớn, rất nhiều clients và slow reader; xác nhận bounded queues và rejection.
9. Kiểm tra user A không xem stream/job/room của user B; Origin, CORS, cookies và TLS.
10. Khi deploy thay version, xác minh định dạng message và khả năng resume tương thích.

### 18.3. Test “stream thật” thay vì body cuối cùng

Một response `curl -s ...` hoàn thành đúng có thể che lỗi buffering. Đo timestamp ở phía server lúc `send/flush` và phía client lúc event/line/message được xử lý. So sánh **latency của từng phần tử**, không chỉ total response time. Với HTTP/2 proxying, đánh giá trên tuyến viewer thật thay vì chỉ localhost HTTP/1.1.

### 18.4. Những trường hợp có thể trả lỗi HTTP và không thể

Với HTTP streaming hoặc SSE, **trước khi gửi headers/body** server có thể trả status 401/403/500 và JSON error thông thường. **Sau khi body đã bắt đầu**, không thể đáng tin cậy “đổi status sang 500” trong cùng response. Cần dùng định dạng error record/event, kết thúc stream có kiểm soát và để client tự nhận biết incomplete/truncated stream. WebSocket cũng không có HTTP status per message sau handshake; có thể gửi error message hoặc close code theo protocol.

## 19. Những ngộ nhận phổ biến

| Nhận định sai | Sự thật |
| --- | --- |
| “SSE là công nghệ khác hẳn HTTP streaming.” | SSE dùng HTTP streaming với format `text/event-stream` chuẩn hóa. |
| “HTTP streaming chỉ cho phép TCP một chiều.” | HTTP có request/response và có request body streaming; một response stream cụ thể chủ yếu server→client. |
| “Một `flush()` là một JavaScript event.” | TCP/HTTP/proxy buffers không giữ boundary theo `write/flush`; cần protocol framing. |
| “Mỗi HTTP chunk tương ứng một dòng NDJSON.” | Parser phải buffer và tách theo newline, không theo chunk boundaries. |
| “EventSource tự đảm bảo không mất sự kiện.” | Nó tự reconnect và gửi Last-Event-ID; server cần replay store, dedup. |
| “SSE không thể tương tác.” | Server→client là một chiều, nhưng browser có thể gửi HTTP POST khác song song. |
| “WebSocket có built-in durable message queue.” | Không; phải thêm broker/storage/ACK/replay nếu cần. |
| “WebSocket browser tự nối lại.” | Không; code phải tự reconnect sau close/failure. |
| “WebSocket luôn nhanh hơn SSE.” | Hiệu năng phụ thuộc volume, protocol, hạ tầng và workload. |
| “Có @Async hoặc Flux là không còn blocking.” | Spring MVC writes vẫn blocking; WebFlux cần không block event loop. |
| “SSE hoạt động tốt qua mọi CDN.” | Proxy buffering, cache, idle timeout và HTTP versions phải tương thích. |
| “CORS bảo vệ WebSocket khỏi mọi client.” | WebSocket handshake/origin và authentication/authorization cần chính sách riêng. |
| “Heartbeat ngăn được mọi disconnect.” | Pod restart, mobile network changes và device sleep vẫn ngắt kết nối. |
| “Sticky sessions giải quyết failover.” | Không giữ socket hoặc RAM khi pod chết; reconnect + shared state mới quan trọng. |
| “Có WS là chat tự scale được nhiều pods.” | Cần message routing/broker và xử lý session state phân tán. |

## 20. Câu hỏi tự kiểm tra

**1.** Ứng dụng cần trả 5.000 dòng JSON để frontend hiển thị dần, không cần event names hoặc reconnect chuẩn. Chọn gì?  
**Đáp án:** HTTP streaming với NDJSON là một lựa chọn hợp lý. Client dùng `fetch().body`/reader và parser theo newline, không theo TCP chunks.

**2.** Một trang cần nhận status job mà server cập nhật, browser thỉnh thoảng gửi nút Cancel. Có bắt buộc WebSocket?  
**Đáp án:** Không. SSE cho status + HTTP POST cho Cancel thường đơn giản và phù hợp.

**3.** Khi `EventSource` reconnect với `Last-Event-ID: 27`, Spring `SseEmitter` có tự phát lại 28 trở đi?  
**Đáp án:** Không. App phải đọc header, query durable event store và replay; cần kiểm soát quyền và duplicate.

**4.** Chat có user gửi/nhận tin liên tục và cần binary attachment metadata. Nên cân nhắc gì?  
**Đáp án:** WebSocket cho messages hai chiều; file upload lớn có thể dùng HTTP riêng. Cần broker, auth/permissions, persistence/ack/resume.

**5.** `curl -N` thấy NDJSON mỗi 800 ms ở origin, nhưng ở CDN chỉ nhận khi server hoàn tất. Tìm nguyên nhân ở đâu?  
**Đáp án:** Proxy/CDN buffering, gzip, cache/response transforms hoặc tầng mạng. Kiểm tra trực tiếp từng hop.

**6.** `ws://` bị browser chặn trên trang HTTPS. Sửa thế nào?  
**Đáp án:** Dùng `wss://` tới public endpoint được TLS proxy hỗ trợ, cấu hình Upgrade/handshake và trust forwarded scheme phù hợp.

**7.** Tại sao WebSocket phải kiểm tra Origin nếu user có session cookie?  
**Đáp án:** Browser WebSocket không chịu same-origin checks giống fetch; trang độc có thể thử mở WS với cookie browser tự gửi. Origin allowlist cộng authentication và per-message authorization là cần thiết.

**8.** WebSocket đã trả 101, liệu có thể trả HTTP 401 cho từng message sai quyền sau đó?  
**Đáp án:** Không như một HTTP response mới; gửi application error message hoặc close theo policy. Handshake có thể bị 401/403 trước khi nâng cấp.

**9.** Spring MVC `StreamingResponseBody` được trả ngay từ handler thì writes có non-blocking như WebFlux không?  
**Đáp án:** Không. MVC async hỗ trợ giải phóng request thread ban đầu nhưng response writes vẫn blocking, thường trên executor khác.

**10.** Một pod A có 50.000 SSE subscribers trong RAM, pod B phát event. A có tự nhận event ở B không?  
**Đáp án:** Không. Cần shared pub/sub/broker, và durable log nếu muốn replay khi disconnect.

## 21. Checklist triển khai

- [ ] Xác định rõ cần stream bytes, stream events một chiều hay channel hai chiều.
- [ ] Định nghĩa message framing: newline, SSE fields hay WebSocket message schema.
- [ ] Không giả định HTTP chunk, TCP packet hay proxy flush trùng business message.
- [ ] Dùng executor và bounded queues khi streaming bằng Spring MVC; không tạo thread vô hạn.
- [ ] SSE có `text/event-stream`, event names/data/id/retry hợp lệ và kế hoạch heartbeat.
- [ ] Nếu cần replay SSE, có durable store, quyền, cursor/dedup/gap handling.
- [ ] WebSocket có authentication handshake, Origin checks, per-message authorization và size limits.
- [ ] Không kỳ vọng WebSocket tự reconnect; có backoff/jitter/resubscribe logic.
- [ ] Các kết nối dài có timeouts, heartbeat và cleanup khi client disconnect.
- [ ] Proxy buffering/compression/caching được test cho từng route streaming.
- [ ] NGINX/ingress hỗ trợ WebSocket handshake Upgrade hoặc transport tương ứng.
- [ ] Dùng TLS HTTPS/WSS ở production, quản lý cookies/CORS/CSRF theo thực tế.
- [ ] Không chia sẻ cache các stream có dữ liệu riêng và không log tokens/payload nhạy cảm.
- [ ] Nhiều replicas có shared bus/broker; sticky session không thay durable state.
- [ ] Có idempotency/ack/resume khi yêu cầu delivery đáng tin, không dựa vào transport.
- [ ] Đo time-to-first-event, latency từng event, reconnect rate, queue depth và số kết nối.
- [ ] Test browser, CLI, proxy/CDN, rolling deploy, slow clients và network loss.

## Tài liệu tham khảo chính thức

- [Spring Framework — MVC Asynchronous Requests: ResponseBodyEmitter, SseEmitter, StreamingResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — WebSocket API, WebSocketConfigurer, WebSocketHandler](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework — WebSocket Overview và RFC 6455](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework — STOMP Message Broker and External Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — WebFlux Streaming and Reactive Backpressure](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot 3.3 — Common Application Properties: spring.mvc.async.request-timeout](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — WebSocket Support](https://docs.spring.io/spring-boot/3.3/reference/messaging/websockets.html)
- [MDN — Server-Sent Events và EventSource](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [WHATWG HTML Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN — WebSocket Browser API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [NGINX — HTTP Proxy Buffering/Timeout Configuration](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)

**Ghi nhớ:** HTTP streaming giúp **gửi response dần theo bytes**; SSE thêm **chuẩn sự kiện và tự reconnect trên HTTP streaming**; WebSocket cung cấp **kênh message hai chiều**. Khi lựa chọn, thiết kế **business framing, permissions, timeout, heartbeat, replay và scaling** là quan trọng hơn chỉ chọn một API nghe có vẻ “real-time”.
