# Server-Sent Events với `Flux` và `ServerSentEvent` trong Spring WebFlux

## 1. Server-Sent Events dùng khi nào?

**Server-Sent Events (SSE)** là cơ chế truyền sự kiện một chiều từ server tới client qua một HTTP response được giữ mở. Browser có thể nhận từng event ngay khi server phát ra, thay vì chờ toàn bộ response hoàn tất.

SSE phù hợp với các trường hợp client cần cập nhật liên tục nhưng không cần một kênh hai chiều như WebSocket:

- Trạng thái xử lý đơn hàng hoặc tác vụ dài.
- Tiến độ import/export file.
- Thông báo mới, activity feed hoặc cập nhật dashboard.
- Giá, số liệu hoặc trạng thái thiết bị được server đẩy tới browser.
- Log trực tiếp hoặc thông tin tiến trình.

Trong Spring WebFlux, kiểu trả về tự nhiên cho một stream là `Flux<T>`. Khi cần kiểm soát metadata của từng event, dùng `ServerSentEvent<T>`:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Notice>> events() {
    return eventService.events()
            .map(notice -> ServerSentEvent.builder(notice).build());
}
```

WebFlux đăng ký response writer phù hợp, serialize từng event và ghi dần xuống kết nối HTTP. Không cần tự tạo thread, gọi `.subscribe()` hoặc quản lý socket trong controller.

## 2. SSE khác polling và WebSocket thế nào?

| Cơ chế | Hướng dữ liệu | Kết nối | Khi phù hợp |
|---|---|---|---|
| Polling | Client hỏi server định kỳ | Mỗi lần hỏi thường là một request mới | Dữ liệu ít thay đổi, đơn giản |
| Long polling | Client hỏi; server giữ request tới khi có dữ liệu hoặc timeout | Request được giữ rồi client gửi request tiếp | Cần cập nhật gần realtime nhưng không dùng stream |
| SSE | Server đẩy event tới client | Một HTTP response mở lâu dài | Server → browser, event dạng text |
| WebSocket | Hai chiều | Kết nối socket lâu dài | Client và server đều cần gửi dữ liệu liên tục |

SSE dùng HTTP và một response body dạng text. Client vẫn có thể gửi request HTTP riêng để tạo command, xác nhận thao tác hoặc cập nhật dữ liệu; stream SSE chỉ đảm nhiệm chiều server tới client.

WebSocket phù hợp hơn khi cần trao đổi hai chiều liên tục, binary frame hoặc giao thức tương tác phức tạp. SSE thường đơn giản hơn khi browser chỉ cần nghe thông báo.

## 3. Cấu trúc wire format của một SSE event

SSE dùng UTF-8 text stream với media type:

```http
Content-Type: text/event-stream
```

Một event có thể có các field:

```text
id: 42
event: order-status
retry: 3000
data: {"orderId":42,"status":"SHIPPED"}

```

Một dòng trống kết thúc event. Nếu không có dòng trống, browser chưa coi event là hoàn chỉnh.

| Field | Ý nghĩa |
|---|---|
| `data` | Payload của event; có thể có nhiều dòng `data:` |
| `event` | Tên loại event; mặc định là `message` nếu bỏ qua |
| `id` | Event ID để browser ghi nhớ và gửi lại khi reconnect |
| `retry` | Khoảng chờ reconnect tính bằng milliseconds |
| Comment (`:`) | Dòng comment, thường dùng làm heartbeat; không phát thành event cho JavaScript |

Ví dụ chỉ có data:

```text
data:hello

```

Ví dụ nhiều dòng data:

```text
data:first line
data:second line

```

Browser ghép các dòng data bằng ký tự newline. Dòng bắt đầu bằng `:` là comment:

```text
: keep-alive

```

Comment hữu ích để giữ kết nối sống qua proxy có idle timeout mà không tạo message nghiệp vụ.

Không tự nối chuỗi event tùy ý nếu có thể dùng `ServerSentEvent`. Writer của Spring chịu trách nhiệm format field, newline và encode dữ liệu.

## 4. `ServerSentEvent<T>` trong Spring

`org.springframework.http.codec.ServerSentEvent<T>` là model cho một event. Các thuộc tính chính:

- `id`: định danh event.
- `event`: tên event.
- `retry`: thời gian client chờ trước khi thử reconnect.
- `comment`: comment/heartbeat.
- `data`: payload của event.

Builder thường dùng:

```java
ServerSentEvent<Notice> event =
        ServerSentEvent.<Notice>builder()
                .id("42")
                .event("order-status")
                .retry(Duration.ofSeconds(3))
                .data(new Notice(42L, "SHIPPED"))
                .build();
```

Có thể tạo event chỉ chứa data:

```java
ServerSentEvent<Notice> event =
        ServerSentEvent.builder(new Notice(42L, "SHIPPED")).build();
```

Hoặc heartbeat không có data:

```java
ServerSentEvent<Notice> heartbeat =
        ServerSentEvent.<Notice>builder()
                .comment("keep-alive")
                .build();
```

`ServerSentEvent<T>` không phải HTTP response hoàn chỉnh. Nó mô tả một event trong body. HTTP status, response headers và media type vẫn do controller/result handler quyết định.

### 4.1. `Flux<T>` hay `Flux<ServerSentEvent<T>>`?

Dùng `Flux<T>` khi chỉ cần gửi data event mặc định, không cần event name, ID hoặc retry metadata:

```java
@GetMapping(value = "/messages", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<Notice> messages() {
    return eventService.messages();
}
```

Dùng `Flux<ServerSentEvent<T>>` khi cần metadata theo từng event:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Notice>> events() {
    return eventService.messages()
            .map(notice -> ServerSentEvent.builder(notice)
                    .id(notice.id().toString())
                    .event("notice")
                    .build());
}
```

Nếu client cần phân biệt `progress`, `completed` và `failed`, event name giúp client đăng ký listener riêng. Nếu client cần resume sau reconnect, cung cấp `id` ổn định.

## 5. `Flux` điều khiển vòng đời stream

`Flux` biểu diễn 0..N event theo thời gian. Khi publisher phát event, WebFlux ghi event đó xuống response; stream có thể tiếp tục cho đến khi complete, error hoặc cancel.

Ví dụ phát một event mỗi giây:

```java
Flux<Notice> notices = Flux.interval(Duration.ofSeconds(1))
        .map(index -> new Notice(index + 1, "update-" + (index + 1)));
```

`Flux.interval` tạo sequence theo thời gian. Đây là nguồn demo; trong ứng dụng thật, nguồn có thể đến từ reactive database, message broker, event store hoặc một publisher chia sẻ.

### 5.1. Cold và hot publisher

Một cold publisher thường tạo luồng mới cho mỗi subscriber. Ví dụ `Flux.interval` trong method controller thường bắt đầu bộ đếm riêng khi mỗi client subscribe.

Một hot/shared publisher có thể phát cùng event tới nhiều client. Ví dụ notification từ broker hoặc một `Sinks.Many` được quản lý ở service. Khi dùng nguồn hot, cần quyết định:

- Mỗi client nhận mọi event hay chỉ event từ lúc kết nối?
- Có lưu event để client reconnect và replay không?
- Nếu một client chậm, queue của riêng client được giới hạn thế nào?
- Khi client disconnect, subscription có được hủy và giải phóng không?

Không dùng một queue không giới hạn cho mỗi client. Một client chậm không được phép khiến bộ nhớ tăng vô hạn.

### 5.2. Kết thúc stream có chủ đích

Có thể giới hạn số event trong demo:

```java
Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(index -> "event-" + index);
```

`take(5)` hoàn tất stream sau năm phần tử. Với SSE browser, kết nối đóng có thể khiến `EventSource` tự reconnect. Vì vậy endpoint hữu hạn có thể được gọi lại sau mỗi lần kết thúc; nếu dùng event ID, server cần xác định cursor tiếp theo.

Stream realtime production thường sống lâu hơn và kết thúc khi client đóng kết nối, server shutdown hoặc nguồn sự kiện hoàn tất.

## 6. Reconnect và `Last-Event-ID`

Một lợi ích quan trọng của SSE là browser `EventSource` tự reconnect khi kết nối bị gián đoạn. Nếu server gửi `id` cho event, browser ghi nhớ ID cuối cùng đã nhận và gửi header:

```http
Last-Event-ID: 42
```

Server có thể dùng giá trị đó làm cursor để tiếp tục stream từ event tiếp theo.

Trong Spring WebFlux, đọc header bằng:

```java
@RequestHeader(name = "Last-Event-ID", required = false)
String lastEventId
```

Ví dụ:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Notice>> events(
        @RequestHeader(name = "Last-Event-ID", required = false)
        String lastEventId) {

    long after = parseCursor(lastEventId);

    return eventStore.readAfter(after)
            .map(notice -> ServerSentEvent.builder(notice)
                    .id(Long.toString(notice.id()))
                    .event("notice")
                    .data(notice)
                    .build());
}
```

`eventStore.readAfter(after)` là API minh họa; trong ứng dụng thật, event store phải có khả năng đọc lại các event sau cursor. Không chỉ tăng bộ đếm rồi cho rằng đã replay dữ liệu.

### 6.1. ID phải ổn định và có thể tiếp tục

ID nên là cursor có thứ tự hoặc định danh event bền vững:

- Sequence number tăng dần.
- Offset của partition message broker.
- Event ID trong database.
- Cursor opaque do server tạo và có thể giải mã/tra cứu.

Không dùng timestamp hiện tại làm ID nếu nhiều event có thể trùng timestamp hoặc độ chính xác không đủ. Không dùng ID ngẫu nhiên nếu server cần biết event nào đến sau event nào.

### 6.2. Reconnect không tự đảm bảo không mất hoặc trùng event

`Last-Event-ID` chỉ cung cấp cursor cuối mà browser ghi nhận. Để resume đáng tin cậy:

1. Ghi event vào event store/broker trước hoặc cùng transaction với thay đổi nghiệp vụ.
2. Gửi ID duy nhất theo thứ tự mà client có thể tiếp tục.
3. Khi reconnect, đọc event sau ID đó.
4. Client xử lý event theo cách idempotent vì một số tình huống có thể dẫn tới nhận lặp.
5. Xác định retention: nếu cursor quá cũ và event đã bị xóa, trả lỗi hoặc yêu cầu client tải snapshot mới.

Nếu chỉ phát event realtime mà không lưu lại, server không thể tái tạo những event đã mất trong khoảng client offline.

## 7. Heartbeat để giữ kết nối sống

Một số proxy/load balancer đóng kết nối nếu không thấy dữ liệu trong một khoảng thời gian. Có thể gửi comment heartbeat định kỳ:

```java
Flux<ServerSentEvent<Notice>> heartbeats =
        Flux.interval(Duration.ofSeconds(15))
                .map(tick -> ServerSentEvent.<Notice>builder()
                        .comment("keep-alive")
                        .build());
```

Ghép với event stream dài hạn:

```java
Flux<ServerSentEvent<Notice>> output =
        Flux.merge(businessEvents, heartbeats);
```

`businessEvents` là `Flux<ServerSentEvent<Notice>>` từ nguồn nghiệp vụ. Heartbeat là comment, nên browser không gọi `onmessage` hoặc event listener cho comment đó.

Chọn chu kỳ heartbeat ngắn hơn idle timeout nhỏ nhất trên đường đi, nhưng không quá dày gây traffic không cần thiết. Ví dụ 15–30 giây thường là điểm bắt đầu để kiểm tra, không phải con số bắt buộc.

Không gửi heartbeat khi client đã disconnect. Khi downstream cancel, subscription heartbeat và event source cần được hủy theo reactive lifecycle.

## 8. Browser client với `EventSource`

Native browser API:

```javascript
const source = new EventSource("/api/events");

source.addEventListener("notice", (event) => {
    const notice = JSON.parse(event.data);
    console.log("id:", event.lastEventId, "notice:", notice);
});

source.addEventListener("completed", (event) => {
    console.log("completed:", event.data);
});

source.onerror = (error) => {
    console.log("SSE connection interrupted", error);
};

// Khi không còn cần nghe:
source.close();
```

Nếu server không đặt `event`, browser phát event mặc định tên `message` và có thể dùng `source.onmessage`.

`EventSource` tự reconnect khi kết nối bị ngắt. Field `retry` do server gửi điều chỉnh thời gian reconnect. Khi có `id`, browser gửi `Last-Event-ID` ở lần kết nối lại.

`event.data` luôn là text. Nếu server gửi JSON, client cần `JSON.parse(event.data)`.

### 8.1. Giới hạn của native EventSource

Native `EventSource` chủ yếu mở một GET request. API này không cho tùy ý đặt method POST, request body hoặc header `Authorization` tùy chỉnh.

Nếu cần authentication:

- Ưu tiên cookie/session bảo mật phù hợp với kiến trúc.
- Với cross-origin cookie, tạo `EventSource(url, { withCredentials: true })` và cấu hình CORS credentials chính xác.
- Không đưa bearer token nhạy cảm vào query string chỉ để native EventSource gửi được; URL có thể xuất hiện trong log, history hoặc telemetry.
- Nếu bắt buộc gửi custom authorization header hoặc body, cân nhắc `fetch` streaming và tự parse SSE framing, hoặc thiết kế endpoint cấp ticket ngắn hạn có kiểm soát.

Ví dụ credential mode:

```javascript
const source = new EventSource(
    "https://api.example.com/api/events",
    { withCredentials: true }
);
```

Server phải cho phép đúng origin và credentials; không thể kết hợp `Access-Control-Allow-Credentials: true` với wildcard origin.

## 9. CORS, authentication và quyền truy cập

SSE vẫn là HTTP endpoint nên cần cùng các biện pháp bảo vệ như API khác:

- Xác thực client trước khi bắt đầu stream.
- Kiểm tra user có quyền nhận event của resource/tenant tương ứng.
- Không tin `tenantId` hoặc user ID chỉ vì chúng xuất hiện trong query parameter.
- Không phát event của user A tới kết nối của user B.
- Giới hạn số stream đồng thời trên mỗi user/IP.
- Đóng stream khi session hết hạn hoặc quyền bị thu hồi.
- Không đưa token, secret hoặc dữ liệu cá nhân không cần thiết vào event payload.

Với Spring Security reactive, cấu hình authorization cho route SSE như một endpoint HTTP bình thường. Nếu stream phụ thuộc quyền sở hữu order, kiểm tra quyền trước khi subscribe vào event source và cân nhắc kiểm tra lại khi quyền có thể thay đổi trong thời gian kết nối mở.

CORS cần khai báo origin cụ thể khi dùng credentials. Native EventSource không cung cấp header tùy chỉnh nên cookie-based authentication thường dễ tích hợp hơn trong browser.

## 10. Backpressure, client chậm và giới hạn queue

`Flux` tham gia Reactive Streams nên demand và cancellation có thể truyền ngược từ response writer tới nguồn. Tuy nhiên, SSE không tự bảo đảm toàn bộ hệ thống luôn có đủ bộ nhớ nếu producer nhanh hơn client.

Các nguồn rủi ro:

- Một client mở kết nối lâu nhưng đọc rất chậm.
- Message broker phát nhanh hơn tốc độ ghi socket.
- Ứng dụng buffer event không giới hạn cho từng subscriber.
- Một stream phát payload lớn hoặc quá nhiều event nhỏ.
- Nhiều client đồng thời nhân bản queue và object.

Các cách kiểm soát:

- Dùng `concatMap` hoặc `flatMap` với concurrency giới hạn cho xử lý trước khi phát event.
- Giới hạn queue/prefetch và xác định overflow policy.
- Dùng bounded replay window thay vì lưu mọi event trong heap.
- Đặt giới hạn kích thước payload và tần suất event.
- Nếu event quan trọng không được phép mất, lưu bền vững trong broker/event store và để client resume bằng cursor.
- Nếu chỉ cần trạng thái mới nhất, có thể coalesce hoặc gộp cập nhật thay vì giữ mọi giá trị trung gian.

Không dùng `onBackpressureBuffer()` không giới hạn như giải pháp mặc định. Buffer chỉ trì hoãn vấn đề khi consumer chậm; cuối cùng nó có thể làm cạn bộ nhớ.

## 11. Cancellation và dọn tài nguyên

Khi browser gọi `source.close()`, tab đóng, mạng mất hoặc server timeout, downstream có thể cancel subscription.

Reactive pipeline cần gắn resource cleanup với lifecycle:

```java
Flux<ServerSentEvent<Notice>> stream =
        eventSource.events()
                .doOnCancel(() -> log.info("SSE client disconnected"));
```

`doOnCancel` hữu ích để quan sát disconnect, nhưng không thay thế việc đóng resource thật. Nếu handler tạo consumer, subscription tới broker hoặc file/channel riêng, cần hủy/đóng chúng khi stream complete, error hoặc cancel.

Có thể dùng `Flux.using` hoặc `Flux.usingWhen` khi resource có vòng đời gắn với subscription. Tránh gọi `.subscribe()` bên trong controller để mở một luồng độc lập; nếu làm vậy, request bị cancel có thể không dừng luồng nền và resource bị rò.

Nên ghi metric cho số kết nối đang mở, thời gian sống, event gửi/giây, disconnect, lỗi, queue depth và reconnect. Không dùng user ID hoặc session ID làm metric tag cardinality cao.

## 12. Lỗi trong một SSE stream

Status HTTP được gửi khi response commit, thường lúc event đầu tiên bắt đầu được ghi. Sau khi client đã nhận `200 OK` và một phần stream, server không thể đổi status thành `500` cho cùng response.

Nếu lỗi nghiệp vụ xảy ra sau commit, có thể phát một event lỗi theo schema đã công bố:

```java
return events
        .onErrorResume(error ->
                Flux.just(ServerSentEvent.<Notice>builder()
                        .event("error")
                        .data(new Notice(0L, "stream interrupted"))
                        .build())
        );
```

Đây là ví dụ minh họa; `Notice` cần được định nghĩa phù hợp. Không gửi stack trace hoặc exception message thô cho client.

Nếu không thể phát error event, để stream kết thúc bằng lỗi và để browser reconnect theo chính sách. Client phải phân biệt lỗi tạm thời với lỗi không thể phục hồi; có thể cần tải lại snapshot hoặc hiển thị trạng thái gián đoạn.

Lỗi xác thực/authorization nên được phát hiện trước khi response bắt đầu. Một khi stream đã commit, không thể đổi thành `401` hoặc `403`.

## 13. Caching, proxy buffering và timeout

SSE là response sống lâu, thường không phù hợp với cache HTTP thông thường. Một số header và cấu hình triển khai thường cần xem xét:

```http
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

- `Content-Type` cho biết body là SSE.
- `Cache-Control: no-cache` ngăn cache dùng lại một response cũ mà không revalidate; nếu stream chứa dữ liệu riêng tư và không muốn cache lưu, cân nhắc `no-store`.
- `X-Accel-Buffering: no` là header đặc thù Nginx để tắt response buffering khi cấu hình hỗ trợ.

Không đặt thủ công `Connection: keep-alive` cho mọi môi trường; đây là connection-specific header và không được dùng trong HTTP/2. Kiểm tra cấu hình reverse proxy/load balancer để tránh buffering hoặc idle timeout đóng stream quá sớm.

Compression middleware cũng có thể buffer dữ liệu trước khi gửi. Kiểm thử từ browser qua toàn bộ proxy/CDN thật, không chỉ gọi localhost. Nếu event chỉ tới client sau khi proxy gom nhiều KB, stream không còn cảm giác realtime dù publisher phát đúng thời điểm.

## 14. SSE trong HTTP/1.1 và HTTP/2

SSE sử dụng một HTTP response dài hạn. Với HTTP/1.1, browser thường giới hạn số kết nối đồng thời tới cùng origin; mở nhiều tab hoặc nhiều stream có thể chạm giới hạn. HTTP/2 multiplex nhiều stream trên một kết nối TCP nên giảm vấn đề giới hạn connection theo origin.

Dù dùng HTTP/2, mỗi stream vẫn tiêu thụ tài nguyên server: subscription, state, buffer, socket/stream state và có thể là consumer riêng tới broker. Cần giới hạn số kết nối, timeout và tài nguyên theo user.

Nếu ứng dụng có nhiều loại thông báo, cân nhắc gom chúng vào một SSE stream có event name khác nhau thay vì mở một kết nối cho từng loại.

## 15. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ tạo endpoint `GET /api/events`:

- Trả `text/event-stream`.
- Mỗi giây phát một event `notice`.
- Mỗi event có ID, event name, retry delay và JSON data.
- Kết thúc sau năm event để dễ thử bằng `curl`.
- Đọc `Last-Event-ID` để minh họa cursor khi reconnect.

### Cấu trúc dự án

```text
webflux-sse-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-sse-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import org.springframework.http.codec.ServerSentEvent;

import reactor.core.publisher.Flux;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
class EventController {

    @GetMapping(
            value = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<Notice>> events(
            @RequestHeader(
                    name = "Last-Event-ID",
                    required = false
            ) String lastEventId,
            ServerHttpResponse response) {

        long cursor = parseCursor(lastEventId);

        response.getHeaders().set(
                "Cache-Control", "no-cache"
        );
        response.getHeaders().set(
                "X-Accel-Buffering", "no"
        );

        return Flux.interval(Duration.ofSeconds(1))
                .map(tick -> cursor + tick + 1)
                .take(5)
                .map(id -> ServerSentEvent.<Notice>builder()
                        .id(Long.toString(id))
                        .event("notice")
                        .retry(Duration.ofSeconds(3))
                        .data(new Notice(id, "update-" + id))
                        .build());
    }

    private long parseCursor(String value) {
        if (value == null || value.isBlank()) {
            return 0;
        }

        try {
            long cursor = Long.parseLong(value);
            if (cursor < 0) {
                throw new NumberFormatException("negative cursor");
            }
            return cursor;
        } catch (NumberFormatException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Last-Event-ID must be a non-negative integer"
            );
        }
    }

    record Notice(long id, String message) {}
}
```

Chạy từ thư mục dự án bằng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

### Thử stream bằng curl

```bash
curl -N http://localhost:8080/api/events
```

`-N` tắt buffering phía curl để hiển thị dữ liệu ngay khi nhận. Body có dạng:

```text
id:1
event:notice
retry:3000
data:{"id":1,"message":"update-1"}

id:2
event:notice
retry:3000
data:{"id":2,"message":"update-2"}

id:3
event:notice
retry:3000
data:{"id":3,"message":"update-3"}

id:4
event:notice
retry:3000
data:{"id":4,"message":"update-4"}

id:5
event:notice
retry:3000
data:{"id":5,"message":"update-5"}

```

### Thử resume bằng Last-Event-ID

```bash
curl -N \
  -H "Last-Event-ID: 5" \
  http://localhost:8080/api/events
```

Event đầu tiên trong kết nối mới có ID `6`, sau đó là `7` tới `10`.

**Giới hạn của demo:** sequence được tạo từ cursor, không đọc event lịch sử từ một event store. Nó chỉ minh họa cách nhận `Last-Event-ID` và tạo ID tiếp theo. Production phải đọc lại các event còn thiếu từ database, broker hoặc log bền vững để không bỏ mất dữ liệu trong lúc client offline.

Header `X-Accel-Buffering` chỉ có ý nghĩa với Nginx khi cấu hình cho phép; có thể bỏ nếu hạ tầng không dùng Nginx. Không cần tự đặt header `Connection`.

## 16. Kiểm thử bằng `WebTestClient`

Có thể kiểm tra media type, event metadata và payload mà không mở cổng TCP:

```java
WebTestClient client = WebTestClient
        .bindToController(new EventController())
        .build();

FluxExchangeResult<ServerSentEvent<EventController.Notice>> result =
        client.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                        new ParameterizedTypeReference<
                                ServerSentEvent<EventController.Notice>>() {}
                );

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                "1".equals(event.id())
                        && "notice".equals(event.event())
                        && event.data() != null
                        && event.data().id() == 1
        )
        .expectNextCount(4)
        .verifyComplete();
```

Đây là đoạn test minh họa; cần `spring-test` và `reactor-test` (có thể thêm qua `spring-boot-starter-test`) cùng các import `WebTestClient`, `FluxExchangeResult`, `ParameterizedTypeReference`, `StepVerifier`, `Flux` và `ServerSentEvent`.

Nên kiểm thử thêm:

- Request không có `Last-Event-ID`.
- Reconnect với ID hợp lệ.
- Header cursor sai định dạng.
- Event có data, event name và retry.
- Client cancel giữa stream.
- Event source lỗi giữa stream.
- Nhiều client đồng thời và client đọc chậm.
- CORS và authentication từ browser thật.
- Proxy buffering và idle timeout trong môi trường triển khai.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Trả `application/json` cho SSE | Browser không xử lý response như EventSource stream | Dùng `text/event-stream` |
| Gom event thành `List` trước khi trả | Client phải chờ toàn bộ dữ liệu | Trả `Flux` để phát từng event |
| Không đặt `id` nhưng kỳ vọng resume | Server không có cursor đáng tin cậy | Gửi ID ổn định cho mỗi event |
| Dùng ID ngẫu nhiên không có thứ tự | Không thể truy vấn event tiếp theo | Dùng sequence/offset/cursor |
| Đọc `Last-Event-ID` nhưng không replay | Event trong thời gian offline vẫn bị mất | Đọc từ event store hoặc broker |
| Coi reconnect là exactly-once | Client có thể nhận event lặp | Thiết kế xử lý idempotent |
| Không có heartbeat | Proxy có thể đóng kết nối idle | Gửi comment heartbeat theo timeout hạ tầng |
| Dùng heartbeat quá dày | Tốn băng thông và CPU | Chọn chu kỳ theo idle timeout |
| Dùng queue không giới hạn | Client chậm làm RAM tăng | Queue bounded, overflow policy hoặc durable broker |
| Gọi `.subscribe()` trong controller | Stream tách khỏi request lifecycle | Trả `Flux` cho WebFlux |
| Không cleanup khi cancel | Consumer, file hoặc subscription còn sống | Gắn cleanup vào reactive lifecycle |
| Cố đổi status sau event đầu tiên | Response đã commit | Validate/authenticate trước khi phát event |
| Gửi stack trace trong error event | Lộ thông tin nội bộ | Gửi mã lỗi và message an toàn |
| Dùng EventSource với custom bearer header | Native API không hỗ trợ header tùy ý | Cookie/session hoặc fetch streaming |
| Không cấu hình CORS credentials đúng | Browser không mở được stream cross-origin | Khai báo origin cụ thể và credentials |
| Proxy buffer response | Event tới client trễ theo cụm | Tắt buffering phù hợp và kiểm thử qua proxy |
| Mở quá nhiều stream cho cùng origin | Chạm giới hạn connection hoặc tài nguyên | Gom event vào một stream và cân nhắc HTTP/2 |
| Dùng `Connection: keep-alive` trên mọi protocol | Header không phù hợp HTTP/2 | Để server quản lý connection semantics |

## 18. Checklist triển khai SSE

1. Xác định SSE có phù hợp với luồng một chiều server → client không.
2. Trả `Flux<T>` hoặc `Flux<ServerSentEvent<T>>` với `text/event-stream`.
3. Dùng event name để phân loại message; dùng ID ổn định nếu cần resume.
4. Đọc `Last-Event-ID` và replay từ nguồn dữ liệu bền vững.
5. Xác định client xử lý duplicate event theo cách idempotent.
6. Gửi heartbeat comment theo idle timeout của proxy/load balancer.
7. Giới hạn event size, event rate, queue và số kết nối đồng thời.
8. Propagate cancellation và cleanup consumer/resource.
9. Xử lý lỗi sau commit bằng event lỗi hoặc kết thúc stream.
10. Thiết kế authentication, authorization, tenant isolation và CORS.
11. Tắt proxy buffering nếu cần và kiểm tra timeout thực tế.
12. Kiểm thử reconnect, client chậm, disconnect và server restart.
13. Theo dõi số stream đang mở, throughput, latency, queue depth và error rate.

## 19. Bài tập tự kiểm tra

**Câu 1.** SSE truyền dữ liệu theo hướng nào?

**Đáp án:** Server tới client qua HTTP response stream. Client gửi dữ liệu ngược lại bằng request HTTP riêng.

**Câu 2.** Media type tiêu chuẩn của SSE là gì?

**Đáp án:** `text/event-stream`.

**Câu 3.** `Flux<T>` và `Flux<ServerSentEvent<T>>` khác nhau thế nào?

**Đáp án:** `Flux<T>` gửi data event mặc định; `Flux<ServerSentEvent<T>>` cho phép đặt ID, event name, retry và comment cho từng event.

**Câu 4.** Dòng trống trong SSE wire format có ý nghĩa gì?

**Đáp án:** Kết thúc event hiện tại để browser dispatch event.

**Câu 5.** `Last-Event-ID` được dùng khi nào?

**Đáp án:** Browser gửi lại ID cuối đã nhận khi reconnect; server dùng nó làm cursor để tiếp tục hoặc replay event.

**Câu 6.** Heartbeat comment có gọi event listener JavaScript không?

**Đáp án:** Không. Comment được bỏ qua ở tầng dispatch event, nhưng giúp giữ kết nối sống.

**Câu 7.** Vì sao cần event store nếu muốn resume đáng tin cậy?

**Đáp án:** Cursor chỉ cho biết client đã nhận đến đâu; server cần nguồn bền vững để đọc lại event phát sinh trong lúc client offline.

**Câu 8.** Native `EventSource` có gửi custom Authorization header không?

**Đáp án:** Không. Nó không cung cấp API đặt header tùy ý; dùng cookie/session hoặc fetch streaming khi cần custom header.

**Câu 9.** Server có thể đổi status thành 500 sau khi đã gửi event đầu tiên không?

**Đáp án:** Không. Response đã commit; hãy phát error event theo hợp đồng hoặc kết thúc stream.

**Câu 10.** Vì sao không dùng buffer không giới hạn cho client chậm?

**Đáp án:** Queue sẽ tăng theo chênh lệch tốc độ producer/consumer và có thể làm cạn bộ nhớ.

## 20. Quy tắc áp dụng

- Dùng SSE khi cần truyền event một chiều từ server tới browser qua HTTP.
- Dùng `Flux` để phát dần; dùng `ServerSentEvent<T>` khi cần `id`, `event`, `retry` hoặc comment.
- Giữ `Content-Type: text/event-stream` và kiểm tra proxy không buffer stream.
- Dùng ID ổn định cùng `Last-Event-ID` và event store nếu cần reconnect/replay.
- Gửi heartbeat comment theo idle timeout.
- Giới hạn queue, payload, tốc độ event và số stream.
- Propagate cancellation và cleanup resource khi client disconnect.
- Xác thực/ủy quyền trước khi stream bắt đầu; xử lý CORS và dữ liệu tenant an toàn.
- Sau commit, biểu diễn lỗi trong stream hoặc kết thúc stream; không cố đổi status HTTP.
- Kiểm thử bằng `WebTestClient` và browser qua hạ tầng thực tế.

**Ghi nhớ:** `Flux` điều khiển chuỗi event; `ServerSentEvent<T>` bổ sung metadata theo chuẩn SSE. `id` và `Last-Event-ID` hỗ trợ resume, heartbeat giữ kết nối sống, còn backpressure/cancellation giúp quản lý tài nguyên. Muốn stream đáng tin cậy khi reconnect, phải kết hợp cursor với event store và xử lý duplicate ở client.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework — Reactive Types và Server-Sent Events trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — `ServerSentEvent` Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework — `ServerSentEventHttpMessageWriter` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/ServerSentEventHttpMessageWriter.html)
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [WHATWG — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [MDN — EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
