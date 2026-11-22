# Phát SSE bằng SseEmitter trong Spring MVC và Flux trong Spring WebFlux

## 1. Bối cảnh: server cần đẩy cập nhật đến trình duyệt

Giả sử một hệ thống Spring Boot theo dõi trạng thái đơn hàng, tiến trình xuất báo cáo hoặc thông báo tác vụ. Sau khi browser gửi một HTTP request đăng ký nhận cập nhật, server muốn **gửi nhiều sự kiện theo thời gian** mà không cần browser liên tục hỏi `GET /status` mỗi giây. **Server-Sent Events (SSE)** là giải pháp HTTP tiêu chuẩn cho luồng **một chiều: server → client**.

~~~text
Browser / EventSource                    Spring Boot
        |                                      |
        | GET /events, Accept: text/event-stream
        |------------------------------------->|
        |<-- HTTP 200, text/event-stream ------|
        |                                      |
        |<-- id: 1, event: progress, data:... -|
        |<-- id: 2, event: progress, data:... -|
        |<-- : keep-alive ---------------------|
        |<-- id: 3, event: done, data:... -----|
        |                                      |
        | (kết nối tiếp tục hoặc được đóng)   |
~~~

Trong Spring Boot có hai cách triển khai phổ biến:

1. **Spring MVC/Servlet:** controller trả `SseEmitter`, ứng dụng gọi `emitter.send(...)` mỗi khi có sự kiện và quản lý vòng đời/timeout/cleanup.
2. **Spring WebFlux:** controller trả `Flux<T>` với `produces = text/event-stream`, thường dùng `Flux<ServerSentEvent<T>>` khi cần `id`, `event`, `retry` và comment; lifecycle gắn với reactive subscription.

Hai cách có **cùng giao thức SSE trên dây** nhưng có cơ chế lập lịch, hủy đăng ký và xử lý backpressure khác nhau. Bài này dùng **Java 17+, Spring Boot 3.x** và chia thành hai dự án mẫu riêng, không trộn Servlet MVC và WebFlux trong một ứng dụng học.

SSE rất hợp cho notification, job progress, timeline, market/telemetry snapshot cập nhật vừa phải; nó không phải lựa chọn mặc định cho chat hai chiều, truyền file nhị phân hay giao thức có acknowledgment/transaction từ browser. Với giao tiếp hai chiều, cân nhắc WebSocket; với nhu cầu đơn giản ít cập nhật, polling có thể đủ.

## 2. SSE hoạt động trên HTTP như thế nào?

Client thường mở một **HTTP GET**; server trả HTTP 200 và giữ response body **đang stream**, với `Content-Type: text/event-stream`. Body gồm các record text UTF-8 phân tách bằng **dòng trống**.

Ví dụ định dạng thô:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream;charset=UTF-8
Cache-Control: no-cache

id: 101
event: progress
retry: 3000
data: {"jobId":"job-42","percent":20}

id: 102
event: progress
data: {"jobId":"job-42","percent":50}

: keep-alive

id: 103
event: done
data: {"jobId":"job-42","percent":100}

~~~

Các trường có ý nghĩa:

| Dòng SSE | Ý nghĩa |
| --- | --- |
| `data: ...` | Payload text của sự kiện; nhiều dòng `data:` sẽ được ghép bằng ký tự newline |
| `event: progress` | Tên event; JS dùng `addEventListener("progress", ...)` để nghe |
| `id: 101` | Event ID mà EventSource ghi nhớ, dùng khi reconnect |
| `retry: 3000` | Gợi ý thời gian reconnect **3000 mili giây**; trình duyệt có quyền áp chính sách riêng |
| `: keep-alive` | Comment, browser bỏ qua; có thể duy trì lưu lượng để phát hiện disconnect/giảm idle timeout |
| Dòng trống | Kết thúc record; browser dispatch event khi đã nhận record hoàn chỉnh |

**Nếu có `event: tick`, handler `onmessage` không nhận nó như event mặc định; phải `addEventListener("tick", handler)`.** Nếu không có `event:`, browser gửi `message` event tới `onmessage`/listener `message`. Lỗi này gây tình trạng Network thấy SSE nhưng callback JS không chạy.

SSE là text stream, **không phải** một JSON array dài kiểu `[{"a":1},{"b":2}]`. Payload `data:` có thể chứa JSON đã serialize, nhưng **framing** dùng các dòng SSE và dòng trống. Đừng tự in JSON liên tiếp mà thiếu `data:`/dòng trống.

Một record có nhiều dòng:

~~~text
event: multiline
data: dong thu nhat
data: dong thu hai

~~~

Client nhận một event có `event.data` là chuỗi chứa newline. Phải tránh việc tùy tiện ghép input không tin cậy vào SSE lines khiến attacker chèn `event:`, `id:` hoặc record mới. Dùng builder/encoder framework hoặc escape/serialize đúng, thay vì nối string thô.

### SSE không phải WebSocket

| Tiêu chí | SSE | WebSocket | Polling |
| --- | --- | --- | --- |
| Hướng giao tiếp | Chủ yếu server → browser, một chiều | Hai chiều | Client liên tục request |
| Transport | HTTP response streaming | HTTP upgrade / WebSocket protocol | Nhiều HTTP requests |
| Browser API | `EventSource` | `WebSocket` | `fetch`, timer |
| Tự reconnect trong API chuẩn | EventSource thường tự thử lại | Tự viết logic | Tự viết lịch |
| Event ID/retry fields | Có chuẩn `id`, `retry` | Ứng dụng tự định nghĩa | Ứng dụng tự định nghĩa |
| Binary data trực tiếp | Không, text UTF-8; encode nếu cần | Hỗ trợ binary frames | Hỗ trợ thông thường |
| Dễ dùng với proxy HTTP | Thường có thể; phải tắt buffering/đúng timeout | Cần hỗ trợ upgrade | Thường dễ nhất |
| Server có thể phát nhiều lần trên một request | Có | Có | Một response/request, rồi request mới |

**SSE không cam kết giao hàng exactly-once.** Khả năng reconnect từ EventSource chưa đủ để đảm bảo không mất event giữa lúc mạng gián đoạn và thời điểm server gửi. Cần event log có cursor + replay policy nếu yêu cầu nhất quán nghiệp vụ.

## 3. Browser EventSource: ví dụ người nhận

Ở trang HTML đã có backend cùng origin, dùng:

~~~javascript
const source = new EventSource("/events/mvc");

source.addEventListener("open", () => {
  console.log("SSE connected");
});

source.addEventListener("tick", (event) => {
  const payload = JSON.parse(event.data);
  console.log("id =", event.lastEventId, "data =", payload);
});

source.addEventListener("done", () => {
  console.log("Server báo hoàn tất");
  source.close();
});

source.onerror = (event) => {
  console.warn("SSE failed or reconnecting", event);
};
~~~

Giải thích:

- `EventSource(url)` khởi tạo kết nối GET và nhận những record SSE hoàn chỉnh.
- `event.data` là **text**, nên parse JSON khi backend gửi JSON. Nên có try/catch cho dữ liệu không đúng schema ở ứng dụng thật.
- `event.lastEventId` mang giá trị `id` gần nhất trong event context.
- `source.close()` dừng stream ở browser; nếu server chủ động đóng response mà client **không gọi close()**, EventSource có thể thử reconnect theo chính sách chuẩn.
- `onerror` không đồng nghĩa chỉ có lỗi backend 500; nó cũng có thể xảy ra khi kết nối bị mất và browser chuẩn bị reconnect.
- `EventSource` **không cho script tự đặt arbitrary request headers** như `Authorization: Bearer ...` theo API chuẩn. Với auth bằng cookie có thể dùng EventSource và credential mode; với bearer header có thể dùng streaming `fetch` client/custom polyfill hoặc mô hình BFF an toàn.

Ví dụ frontend của hai project sẽ khác đường dẫn:

- MVC: `http://localhost:8081/events/mvc`.
- WebFlux: `http://localhost:8082/events/reactive`.

Nếu trang HTML và API khác origin, ngoài SSE cần cấu hình **CORS** phù hợp. Chi tiết bảo mật nằm ở phần sau.

## 4. Kiến trúc SseEmitter của Spring MVC

Spring MVC chạy trên Servlet stack (ví dụ embedded Tomcat). `SseEmitter` kế thừa `ResponseBodyEmitter`, cho phép một controller trả về emitter **ngay**, sau đó gửi dữ liệu từ một thread/task khác theo thời gian.

~~~text
HTTP request /events/mvc
            |
            v
Spring MVC controller
            |
            +-- tạo SseEmitter(timeout)
            +-- đăng ký onCompletion/onTimeout/onError
            +-- đăng ký nguồn phát event
            |
            +-- return SseEmitter / ResponseEntity<SseEmitter>
                  |
                  v
             Servlet async request
                  |
                  +---- background scheduler/task ----> emitter.send(...)
                  |                               |
                  |                               +--> event: tick, id, data
                  |
                  +---- disconnect / timeout / complete --> cleanup
~~~

Đây là **Servlet async request processing**, không phải API reactive không chặn I/O như WebFlux. Việc controller thread có thể trả nhanh **không đồng nghĩa mỗi lần ghi ra socket đều non-blocking**. `SseEmitter.send` dùng message converters và ghi response qua Servlet infrastructure; các lần ghi có thể chặn worker thread khi downstream chậm. Đừng tạo một thread vĩnh viễn cho mỗi client hoặc giữ nguyên executor không giới hạn.

### API quan trọng của SseEmitter

| API | Vai trò |
| --- | --- |
| `new SseEmitter(timeoutMillis)` | Tạo emitter, timeout tính theo mili giây; không truyền `Duration` trực tiếp vào constructor này |
| `SseEmitter.event().id("1")` | Đặt event ID |
| `.name("tick")` | Đặt `event: tick` |
| `.data(object)` | Thêm `data: ...`; message converter có thể serialize DTO thành JSON |
| `.reconnectTime(3000L)` | Đặt `retry: 3000` |
| `.comment("keep-alive")` | Gửi comment SSE, hữu ích làm heartbeat |
| `emitter.send(builder)` | Ghi một SSE event |
| `emitter.complete()` | Kết thúc bình thường |
| `emitter.completeWithError(ex)` | Kết thúc do lỗi ứng dụng không phải write-disconnect thường gặp |
| `onCompletion(Runnable)` | Callback lúc request đã hoàn thành, dùng cleanup |
| `onTimeout(Runnable)` | Callback khi async timeout |
| `onError(Consumer<Throwable>)` | Callback khi async processing gặp lỗi |

Một điều quan trọng theo tài liệu Spring Framework: nếu `send` ném **`IOException` do client đã đi khỏi**, app không cần gọi `complete()` hoặc `completeWithError()` để cố sửa đường ghi; servlet container phát async error notification và Spring MVC xử lý. App nên **dừng producer và dọn tài nguyên**, để lifecycle framework hoàn tất.

Không phải lỗi nào cũng là IOException: serialization/business computation lỗi có thể cần `completeWithError` trước khi response commit. Sau khi response đã stream một phần body, không thể kỳ vọng exception handler đổi HTTP status từ 200 thành 500 bình thường; gửi event lỗi có schema và/hoặc đóng stream theo policy.

## 5. Dự án A: Spring MVC + SseEmitter chạy được bằng Java 17+

Ví dụ phát năm event `tick`, mỗi giây một sự kiện, sau đó gửi `done` và đóng response. Client EventSource nghe `done` rồi gọi `close()` để không tự reconnect vô tận sau khi stream ngắn kết thúc.

Đây là dự án **Servlet MVC riêng**, **không** thêm `spring-boot-starter-webflux`.

### 5.1. Cấu trúc

~~~text
mvc-sse-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/mvcsse/MvcSseApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/mvcsse/MvcSseTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-sse-lab'
~~~

`build.gradle`, ví dụ Spring Boot 3.3.13 + Java 17:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8081

# Servlet async timeout có thể bị giới hạn ở nhiều tầng.
# Controller bên dưới dùng SseEmitter(20000L) cho stream mẫu ngắn.
spring.mvc.async.request-timeout=30s
~~~

Không xem `spring.mvc.async.request-timeout` là lifetime của mọi SSE connection: `SseEmitter` có timeout riêng, servlet container và proxy có timeout khác. Production cần tính yêu cầu stream dài, heartbeat, cancel và connection quotas thay vì chỉ kéo mọi timeout vô hạn.

### 5.2. Mã nguồn độc lập và runnable

Tệp `src/main/java/demo/mvcsse/MvcSseApplication.java`:

~~~java
package demo.mvcsse;

import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class MvcSseApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSseApplication.class, args);
    }

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService sseScheduler() {
        return Executors.newScheduledThreadPool(4);
    }
}

@RestController
class MvcSseController {
    private final ScheduledExecutorService scheduler;

    MvcSseController(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    record Tick(int sequence, String message) { }

    @GetMapping(path = "/events/mvc",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> events() {
        SseEmitter emitter = new SseEmitter(20_000L);
        AtomicInteger counter = new AtomicInteger();
        AtomicReference<ScheduledFuture<?>> taskRef =
                new AtomicReference<>();

        Runnable cancelTask = () -> {
            ScheduledFuture<?> task = taskRef.get();
            if (task != null) {
                task.cancel(false);
            }
        };

        emitter.onCompletion(cancelTask);
        emitter.onTimeout(cancelTask);
        emitter.onError(error -> cancelTask.run());

        Runnable publish = () -> {
            int number = counter.incrementAndGet();

            try {
                emitter.send(SseEmitter.event()
                        .id("mvc-" + number)
                        .name("tick")
                        .reconnectTime(3000L)
                        .data(new Tick(number, "event-" + number)));

                if (number == 5) {
                    emitter.send(SseEmitter.event()
                            .name("done")
                            .data("finished"));
                    emitter.complete();
                    cancelTask.run();
                }
            } catch (IOException disconnected) {
                // Client có thể đã ngắt. Container quản lý async error.
                cancelTask.run();
            } catch (RuntimeException unexpected) {
                cancelTask.run();
                emitter.completeWithError(unexpected);
            }
        };

        ScheduledFuture<?> task = scheduler.scheduleAtFixedRate(
                publish, 1, 1, TimeUnit.SECONDS);
        taskRef.set(task);

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }
}
~~~

### 5.3. Giải thích chi tiết controller

- `@GetMapping(... produces = TEXT_EVENT_STREAM_VALUE)` xác định response SSE. `ResponseEntity<SseEmitter>` cho phép đặt thêm headers như Cache-Control và `X-Accel-Buffering`.
- `new SseEmitter(20_000L)` timeout sau khoảng 20 giây theo servlet async lifecycle; lab gửi 5 events sau 1–5 giây nên nhỏ hơn timeout.
- `ScheduledExecutorService` là **bean dùng chung**, tránh tạo một new thread/executor cho mỗi connection. `@Bean(destroyMethod = "shutdown")` yêu cầu Spring shutdown scheduler khi application context đóng.
- Mỗi connection có `AtomicInteger`/`taskRef` riêng và một scheduled task. `onCompletion`/`onTimeout`/`onError` cancel task để tránh giữ emitter không còn client.
- `SseEmitter.event().id().name().reconnectTime().data()` dùng API builder, tránh tự nối strings và đảm bảo event framing.
- DTO `Tick` là Java record có fields `sequence`/`message`; Jackson từ Spring Web starter serialize nó thành JSON object.
- Lần thứ năm gửi thêm `done`. Browser cần xử lý `done` bằng `EventSource.close()` để không reconnect sau một stream hữu hạn.
- `IOException` khi ghi sau disconnect thường được container/Spring xử lý bằng async error lifecycle. App hủy producer nhưng **không** cố gọi `completeWithError` cho write-disconnect. Các lỗi runtime/serialization khác có thể báo `completeWithError`; lúc đó HTTP response có thể đã commit, không còn thay status bình thường.
- `no-cache, no-transform` là chính sách demo để hạn chế intermediary cache/rewrite; `no-cache` **không phải `no-store`**. Với notification chứa dữ liệu cá nhân, nên thay bằng `Cache-Control: no-store, no-transform` và bypass CDN cache.
- `X-Accel-Buffering: no` được NGINX proxy module hiểu trong các cấu hình tương thích; không bảo đảm mọi CDN/proxy khác tắt buffering.

**Giới hạn demo:** Có một scheduled task theo client và `send` có thể tốn thread khi mạng chậm. Đừng dùng executor 4 threads này cho hàng chục nghìn kết nối. Production cần giới hạn connections, bounded scheduling/queue, monitoring, worker isolation và cân nhắc WebFlux nếu phần lớn pipeline không blocking.

### 5.4. Chạy và quan sát

Nếu đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper, tạo wrapper với Gradle tương thích hoặc dùng Gradle được cài để chạy. Server lắng nghe `localhost:8081`.

Dùng cURL, option `-N`/`--no-buffer` tắt **cURL output buffering**:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8081/events/mvc
~~~

Kỳ vọng thấy HTTP 200 và `Content-Type: text/event-stream`, rồi mỗi giây một record dạng:

~~~text
id:mvc-1
event:tick
retry:3000
data:{"sequence":1,"message":"event-1"}

id:mvc-2
event:tick
retry:3000
data:{"sequence":2,"message":"event-2"}

...
event:done
data:finished

~~~

Các dấu cách sau dấu hai chấm, thứ tự/kiểu serialize hoặc metadata headers có thể thay đổi theo message converter/Spring version. Điều cần kiểm tra là **5 sự kiện tick, ID theo thứ tự và 1 sự kiện done**. `curl` kết thúc khi server hoàn tất response; `EventSource` không tự biết đây là kết thúc nghiệp vụ, nên cần client `close()` ở done.

### 5.5. Browser thử nghiệm

Mở DevTools trên một frontend cùng origin hoặc dùng CORS/same-origin reverse proxy phù hợp:

~~~javascript
const es = new EventSource("/events/mvc");

es.addEventListener("tick", event => {
  const tick = JSON.parse(event.data);
  console.log("MVC", event.lastEventId, tick.sequence, tick.message);
});

es.addEventListener("done", () => {
  console.log("MVC stream finished");
  es.close();
});

es.onerror = err => console.error("MVC SSE connection issue", err);
~~~

Nếu HTML được mở từ `http://localhost:5173` và API ở `http://localhost:8081`, chúng **khác origin**; CORS phải được cấu hình, nếu không browser chặn response. Hoặc dùng reverse proxy/frontend dev-server proxy để cả hai dưới cùng origin và không cần CORS.

## 6. Spring MVC async timeout, disconnect và resource cleanup

### 6.1. Timeout có nhiều lớp

| Tầng | Ý nghĩa |
| --- | --- |
| `SseEmitter(20000L)` | Timeout gắn với async lifecycle của emitter/request |
| `spring.mvc.async.request-timeout` | Mặc định MVC async request nếu không override ở emitter |
| Servlet container | Async request support, connector/response settings |
| Load balancer/CDN/NGINX | Idle/read timeout của upstream/downstream |
| Browser/network | Kết nối TCP, sleep tab, network transition, EventSource reconnect |
| Application | Mốc business timeout và policy số lượng stream |

Đặt `SseEmitter(0L)` hoặc timeout rất lớn không tự giúp stream sống mãi: network và proxy có thể ngắt do idle, quota hoặc triển khai. Với SSE dài, nên dùng heartbeat có chu kỳ **ngắn hơn idle timeout** của intermediary; đo lường theo môi trường thay vì đoán một thời gian cố định.

### 6.2. Tại sao cần heartbeat?

Theo tài liệu Spring MVC, Servlet API không cung cấp thông báo tức thì đáng tin chỉ vì một TCP peer vừa đi khỏi. Trong streaming, việc ghi định kỳ làm lỗi ghi hiện ra khi client đã ngắt. Có thể gửi comment-only event:

~~~java
// Snippet trên một SseEmitter còn hoạt động, dùng từ worker/scheduler:
emitter.send(SseEmitter.event().comment("keep-alive"));
~~~

Một comment `: keep-alive` bị EventSource bỏ qua, không gọi `onmessage`. Cần phân định heartbeat với event nghiệp vụ để tránh tăng sequence/Last-Event-ID vô cớ.

**Đừng tạo một scheduler mới mỗi request** hoặc gửi vô hạn không dọn. Khi có timeout, error, completion hoặc user logout, cancel publisher/task và xóa references khỏi registry để tránh memory leaks.

### 6.3. Registry nhiều subscriber trong MVC

Nếu nghiệp vụ là broadcast, app thường có một registry các `SseEmitter` active per user/tenant/topic, ví dụ `ConcurrentHashMap<...>` hoặc set thread-safe. Quy tắc:

1. Add emitter khi kết nối được phép đăng ký.
2. Remove emitter trong `onCompletion`, `onTimeout`, `onError` và khi gửi thất bại.
3. Send không được kéo dài lock của registry; khi client chậm, tránh để một socket chặn mọi người khác.
4. Không phát dữ liệu tenant A tới emitter của tenant B; map theo principal đã xác thực, không tin userId do client tự gửi.
5. Giới hạn số kết nối/subscribers trên mỗi user và toàn node, có capacity và eviction policy.
6. Registry JVM **chỉ thuộc một node**; khi chạy nhiều instance phải gắn nguồn broadcast qua broker/pubsub hoặc thiết kế affinity, không tưởng các registry tự chia sẻ.

Ví dụ lab không chứa global registry, vì mỗi connection có luồng riêng. Đó là cố ý để tránh biến một bài SSE thành hạ tầng pub/sub chưa có capacity policy.

### 6.4. Blocking writes và scheduler

Servlet async giải phóng request thread sau khi controller trả emitter, nhưng khi gọi `send` việc I/O/serialization có thể dùng thread blocking. Với vài connection, scheduled executor demo đủ; với nhiều connection:

- Dùng bounded task queues, thread pool metrics và per-client write strategy.
- Hạn chế queue events của client chậm; có thể drop snapshot cũ nếu dữ liệu là “latest state” nhưng **không drop event tài chính cần audit**.
- Rate limit connect/reconnect, cap active emitters, detect stuck tasks.
- Đặt timeout đồng bộ giữa servlet, LB, CDN, client heartbeat và business SLA.
- Nếu nguồn dữ liệu vốn reactive/nonblocking và số concurrent streams cao, đánh giá WebFlux.

Không kết luận rằng chỉ thay return type thành `Flux` trong một MVC app là pipeline đã trở thành reactive Netty. Spring MVC có thể adapt Reactor types để stream, nhưng underlying Servlet response writes vẫn blocking trong async executor; cần cấu hình executor phù hợp.

## 7. Spring WebFlux: Flux là luồng reactive, ServerSentEvent là metadata SSE

Spring WebFlux chạy với reactive server (thường Reactor Netty) và reactive HTTP codecs. Controller có thể trả:

~~~java
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> events() {
    return Flux.just("one", "two");
}
~~~

Khi có media type `text/event-stream`, mỗi element được viết dưới dạng SSE data event. Nhưng nếu cần `id`, `event`, `retry` và comment, trả:

~~~java
Flux<ServerSentEvent<MyEvent>>
~~~

và build từng element bằng `ServerSentEvent.builder(...)`.

**Flux** là Publisher có thể phát 0..N values theo thời gian và hỗ trợ reactive demand/cancellation. **ServerSentEvent<T>** là wrapper cho **một SSE record**, không phải Kafka message, WebSocket frame hay HTTP response độc lập.

~~~text
GET /events/reactive
       |
       v
WebFlux Handler
       |
       v
Flux<ServerSentEvent<Tick>>
       |    event 1
       |    event 2
       |    ...
       |
       v
SSE encoder -> Reactor Netty -> HTTP text/event-stream
       |
Client cancels/disconnects
       |
       v
Reactive subscription canceled; upstream can release resources
~~~

Điều này giảm nhu cầu giữ một Servlet write thread per active stream, **nếu các phần phụ thuộc phía sau cũng nonblocking**. Một đoạn code gọi JDBC blocking hay `Thread.sleep` trong WebFlux event loop sẽ phá lợi ích và gây nghẽn toàn server.

## 8. Dự án B: Spring WebFlux + Flux<ServerSentEvent<Tick>> chạy được

Dự án này **độc lập hoàn toàn** với MVC lab; nó chỉ thêm `spring-boot-starter-webflux`, không thêm `spring-boot-starter-web`. Ví dụ cũng phát 5 tick rồi done.

### 8.1. Cấu trúc

~~~text
webflux-sse-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/fluxsse/FluxSseApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/fluxsse/FluxSseTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-sse-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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

`src/main/resources/application.properties`:

~~~properties
server.port=8082
~~~

### 8.2. Mã nguồn runnable

Tệp `src/main/java/demo/fluxsse/FluxSseApplication.java`:

~~~java
package demo.fluxsse;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class FluxSseApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxSseApplication.class, args);
    }
}

record Tick(int sequence, String message) { }

@RestController
class ReactiveSseController {
    @GetMapping(path = "/events/reactive",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<Flux<ServerSentEvent<Tick>>> events() {
        Flux<ServerSentEvent<Tick>> ticks =
                Flux.interval(Duration.ofSeconds(1))
                        .take(5)
                        .map(index -> {
                            long number = index + 1;

                            return ServerSentEvent
                                    .<Tick>builder(
                                            new Tick((int) number,
                                                     "event-" + number))
                                    .id("flux-" + number)
                                    .event("tick")
                                    .retry(Duration.ofSeconds(3))
                                    .build();
                        });

        ServerSentEvent<Tick> done = ServerSentEvent
                .<Tick>builder(new Tick(0, "finished"))
                .event("done")
                .build();

        Flux<ServerSentEvent<Tick>> stream = ticks
                .concatWith(Mono.just(done))
                .doFinally(signal ->
                        System.out.println("SSE terminated: " + signal));

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(stream);
    }
}
~~~

### 8.3. Phân tích operator và lifecycle

- `Flux.interval(Duration.ofSeconds(1))` phát các `Long` tăng dần **0, 1, 2, ...**, bắt đầu sau khoảng 1 giây. Không gọi `Thread.sleep`.
- `take(5)` giới hạn năm values, sau đó upstream complete. Vì source là cold per subscription, mỗi client tự có chuỗi năm tick riêng trong ví dụ này.
- `index + 1` tạo sequence 1..5. `ServerSentEvent.<Tick>builder(...)` chứa data DTO; `.id(...)`, `.event("tick")`, `.retry(Duration.ofSeconds(3))` tạo SSE metadata.
- `concatWith(Mono.just(done))` chỉ phát event `done` **sau** khi năm tick kết thúc. Client dùng done để chủ động đóng EventSource, tránh reconnect vòng lặp.
- `doFinally(signal -> ...)` nhận tín hiệu kết thúc như `onComplete`, `cancel` hoặc `onError` và là nơi phù hợp để ghi metrics/release resources. Ví dụ in stdout để quan sát, không nên log raw user token/session IDs.
- `ResponseEntity<Flux<ServerSentEvent<Tick>>>` thêm headers mà không biến stream thành list hoặc chờ tất cả values rồi mới trả.
- **Không gọi `collectList()` hay `block()` trong controller**: `collectList` biến stream thành một collection thay vì phát dần; `block` có thể chặn event loop hoặc phá reactive runtime.
- Khi browser ngắt kết nối, WebFlux có thể hủy subscription; các source/operators hợp tác với cancellation sẽ giải phóng tài nguyên. Không giả định mọi dependency (blocking API, custom hot source, broker) tự cancel đúng; cần triển khai cleanup/tối ưu riêng.

### 8.4. Chạy và quan sát

Trong project WebFlux:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Kết nối với cURL:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8082/events/reactive
~~~

Kỳ vọng 200 + `text/event-stream` và các records:

~~~text
id:flux-1
event:tick
retry:3000
data:{"sequence":1,"message":"event-1"}

id:flux-2
event:tick
retry:3000
data:{"sequence":2,"message":"event-2"}

...
event:done
data:{"sequence":0,"message":"finished"}

~~~

Các dấu cách, thứ tự field và header server có thể khác; kiểm tra theo nội dung logic, không so sánh byte-for-byte một mẫu in ra. Khi cURL disconnect bằng Ctrl+C, `doFinally` có thể in `cancel` nếu việc hủy được truyền đến Publisher.

### 8.5. Frontend lắng nghe reactive stream

~~~javascript
const es = new EventSource("/events/reactive");

es.addEventListener("tick", event => {
  const tick = JSON.parse(event.data);
  console.log("WebFlux", event.lastEventId, tick);
});

es.addEventListener("done", event => {
  console.log("Finished", JSON.parse(event.data));
  es.close();
});

es.onerror = error => {
  console.warn("Connection issue/reconnect", error);
};
~~~

Nếu trang nằm ở frontend khác origin, cần cấu hình CORS hoặc reverse proxy, tương tự MVC. EventSource không tự biết server đã gửi done nếu JS không xử lý đúng event name.

## 9. So sánh MVC SseEmitter và WebFlux Flux theo trách nhiệm

| Khía cạnh | Spring MVC + SseEmitter | Spring WebFlux + Flux |
| --- | --- | --- |
| Web stack | Servlet container, ví dụ Tomcat | Reactive stack, thường Reactor Netty |
| Controller return | `SseEmitter` hoặc `ResponseEntity<SseEmitter>` | `Flux<ServerSentEvent<T>>` hoặc `ResponseEntity<Flux<...>>` |
| Phát dữ liệu | Gọi `emitter.send` từ task/worker | Publisher tự phát onNext theo subscription/demand |
| Event metadata | `SseEmitter.event().id().name().data()` | `ServerSentEvent.builder().id().event().data()` |
| Kết thúc | `emitter.complete()` | Publisher complete sau phần tử cuối |
| Ngắt kết nối | Callback async + lỗi write; phải dọn task/registry | Cancellation signal; cần upstream hợp tác |
| Timeout | `SseEmitter(timeoutMillis)`, Servlet/proxy | Timeout/reactive operators/proxy/server configs |
| Backpressure | Không có protocol-level demand từ EventSource; write có thể blocking | Reactor demand/cancellation trong pipeline, nhưng TCP và event source vẫn cần capacity |
| Tài nguyên | Cần cân đối blocking writes/worker threads | Có lợi cho lượng kết nối cao nếu dependencies nonblocking |
| Nguồn dữ liệu blocking | MVC/JDBC thường dễ tích hợp | Cần offload hoặc chuyển nonblocking; không block event loop |
| Multi-node | Emitter registry riêng mỗi JVM | Subscription/hot source riêng mỗi instance nếu không có broker |
| Browser | EventSource, cùng SSE protocol | EventSource, cùng SSE protocol |

**Không kết luận WebFlux luôn nhanh hơn.** Với ít stream và ứng dụng phần lớn Spring MVC/JPA blocking, SseEmitter có thể đơn giản hơn. Với nhiều long-lived connections và reactive end-to-end stack, WebFlux có thể sử dụng tài nguyên hiệu quả hơn, nhưng cần kiểm soát memory, slow clients, hot publishers và consistency.

Spring MVC có thể nhận reactive return types như `Flux` khi classpath Reactor có mặt. Tuy nhiên MVC sẽ adapt stream sang Servlet async response với blocking writes qua executor; **không đồng nghĩa app đã chuyển sang Netty WebFlux**. Nếu đưa cả `spring-boot-starter-web` lẫn `spring-boot-starter-webflux` vào Boot, mặc định Boot thường chọn MVC/Servlet; phải xác minh web application type.

## 10. Vấn đề khó: backpressure, slow client và memory

### 10.1. SSE không có ACK riêng cho mỗi event

EventSource không gửi mỗi `id` một ACK trở lại server. `Last-Event-ID` chỉ xuất hiện trong quy trình reconnect và không bảo đảm server đã ghi bền hoặc client đã xử lý nghiệp vụ đúng. Do đó, với nguồn phát nhanh hơn client/network:

~~~text
Broker phát: 1000 event/s
                 |
                 v
SSE server ------ TCP/HTTP -----> Browser chậm 10 event/s
       |
       +--> queue tăng / write chặn / memory pressure
~~~

Nếu producer cứ đẩy vô hạn vào queue không giới hạn, ứng dụng có thể OOM; nếu dùng worker thread per slow client, thread pool có thể cạn.

### 10.2. Chiến lược theo loại dữ liệu

- **Snapshot trạng thái hiện tại:** có thể coalescing/drop intermediate updates, ví dụ chỉ gửi trạng thái mới nhất mỗi 500ms. Cần mô tả rằng giá trị trung gian không được bảo đảm.
- **Thông báo có thể hiển thị lại:** có thể dùng bounded replay window và cursor, cho client resync khi gap.
- **Event nghiệp vụ bắt buộc không mất:** lưu vào durable log/DB/broker trước; SSE chỉ là **kênh delivery**, không phải nguồn dữ liệu duy nhất.
- **Slow client:** giới hạn queue và total connection, đo write latency, hủy stream quá chậm hoặc yêu cầu client resync khi quá ngưỡng.
- **Flux hot publisher:** xem `onBackpressureBuffer` có giới hạn và overflow policy; `onBackpressureLatest` có thể bỏ events cũ, chỉ dùng khi semantics cho phép. `Sinks.Many` cần lựa chọn multicast/replay/overflow strategy; không nghĩ Reactor tự cung cấp queue vô hạn an toàn.
- **MVC scheduler:** hạn chế số task/threads và không để một `send` bị chặn làm nghẽn toàn bộ pool.

Trong WebFlux, reactive backpressure hỗ trợ phối hợp producer/consumer trong pipeline, nhưng **không biến SSE thành exactly-once protocol** và không xóa yêu cầu capacity planning.

## 11. Reconnect, Last-Event-ID và replay: phải thiết kế có chủ đích

EventSource thường tự reconnect khi kết nối bị ngắt, và có thể gửi:

~~~http
GET /events HTTP/1.1
Last-Event-ID: 103
Accept: text/event-stream
~~~

Giá trị `Last-Event-ID` bắt nguồn từ những `id:` client đã thấy; event ID rỗng (`id:`) có thể reset giá trị đã lưu. `retry: 3000` gợi ý khoảng chờ reconnect theo milliseconds.

**Quan trọng:** chỉ đặt `id` trong `SseEmitter` hoặc `ServerSentEvent` **không tự tạo event log hay replay**. Hai project lab bắt đầu chuỗi 1..5 trên mỗi connection; nếu browser reconnect, nó lại thấy chuỗi mới từ đầu. Điều đó có chủ đích cho demo nhưng **không đủ** cho một hệ thống cần tiếp tục chính xác sau disconnect.

### Thiết kế replay trong production

1. Gán event ID bền và có thứ tự trong **một stream scope rõ ràng** (theo user/tenant/topic), không lấy counter local JVM làm ID toàn hệ thống.
2. Ghi event vào DB/durable log hoặc một stream có retention rõ.
3. Khi client connect/reconnect, xác thực principal và kiểm tra quyền đọc stream **trước** khi xử lý cursor.
4. Đọc `Last-Event-ID`, xác minh định dạng, scope, quyền, retention và thứ tự; từ chối/đồng bộ lại nếu ID thuộc tenant khác, quá cũ hoặc không tồn tại.
5. Replay các sự kiện **sau cursor** rồi tiếp tục live stream, bảo đảm chuyển từ replay sang live không tạo gap bằng thiết kế offset/ordering nhất quán.
6. Client có thể nhận duplicates ở ranh giới reconnect; deduplicate theo event ID và thiết kế handler idempotent khi cập nhật state.
7. Khi cursor đã ngoài retention, gửi tín hiệu `resync-required` hoặc yêu cầu client tải snapshot mới rồi mở lại stream.
8. Không tin Last-Event-ID như bằng chứng authorization: non-browser client có thể tự gửi header ấy.

Sơ đồ:

~~~text
Business event producer -> Durable event store/broker
                                      |
                         +------------+------------+
                         |                         |
                    Spring node A             Spring node B
                         |                         |
                         +-----------+-------------+
                                     |
                         GET /events + Last-Event-ID
                                     |
                        auth + replay + live subscription
                                     |
                             Browser EventSource
~~~

### Phân biệt at-most-once, at-least-once và exactly-once

Một HTTP stream có thể bị cắt đúng lúc server ghi data nhưng browser chưa xử lý. Vì vậy hệ thống không thể chỉ dựa trên hành vi ghi socket để biết đã xử lý exactly-once. Với sự kiện cần chính xác, dùng durable event ID, idempotency và business transaction tương ứng. SSE delivery thường phải chấp nhận khả năng **duplicate hoặc gap** và giải quyết ở application protocol.

## 12. Authentication và authorization cho SSE

Một SSE endpoint là **HTTP endpoint thật** và có thể chạy lâu. Cần authentication trước khi subscribe, authorization theo user/tenant/topic và thiết kế revoke trong lúc kết nối đang mở.

### 12.1. Cookie/session

Browser EventSource có thể dùng cookies của cùng origin. Với API khác origin, nếu cần gửi cookie:

~~~javascript
const es = new EventSource("https://api.example.test/events", {
  withCredentials: true
});
~~~

Backend phải cấu hình CORS với `Access-Control-Allow-Origin` là origin cụ thể, `Access-Control-Allow-Credentials: true`, và cookie phải đáp ứng `Secure`, `SameSite`, Domain/Path, browser third-party-cookie policy. `Access-Control-Allow-Origin: *` **không hợp lệ với credentialed browser CORS**.

**Không xem CORS là authentication.** CORS chỉ kiểm soát quyền JS từ website khác đọc response; server/client không phải browser có thể gọi endpoint. SecurityFilterChain/`SecurityWebFilterChain` và domain authorization vẫn bắt buộc. Cookies tự gửi cần xem CSRF threat model cho endpoints thay đổi trạng thái; SSE GET thường chỉ đọc, tuyệt đối không tạo side effect nghiệp vụ qua GET.

### 12.2. Bearer token

Native `EventSource` không hỗ trợ arbitrary request headers như:

~~~http
Authorization: Bearer ...
~~~

Nếu API dùng bearer access token ở header, lựa chọn thông dụng:

- Dùng streaming `fetch` với `Authorization` và parser SSE phía client (tự xử lý framing/reconnect/Last-Event-ID hoặc thư viện đã kiểm chứng).
- Dùng BFF same-origin có HttpOnly cookie bảo mật, BFF giữ token server-side và mở stream tới backend.
- Chọn cơ chế ticket ngắn hạn, một lần dùng và được ràng buộc identity nếu thật sự cần, nhưng không vô tư đặt access token dài hạn trong query string vì có thể lộ vào logs, history và analytics.

Không đặt token vào `?token=...` như một shortcut production. Cần phân tích XSS, CSRF, CORS, cookie policy và token rotation theo kiến trúc app.

### 12.3. Quyền có thể thay đổi khi stream đang mở

Kiểm tra quyền ở thời điểm connect **chưa đủ** cho stream mở hàng giờ: role có thể bị thu hồi, tenant membership thay đổi hoặc account bị khóa. Hệ thống có thể cần:

- Stream lifetime tối đa và buộc reconnect/re-authentication định kỳ.
- Push revoke signal/hủy subscription khi user bị logout/disable.
- Reevaluate quyền khi phát dữ liệu nhạy cảm theo policy.
- Không broadcast data của tenant B cho emitter/subscriber của tenant A.
- Có monitoring xem connection đang dùng principal nào mà không log raw session IDs/tokens.

Một user đã authenticated với `ROLE_USER` không mặc nhiên có quyền subscribe `/events/orders/{orderId}` của người khác. Query/stream routing phải scope theo owner/tenant, tương tự REST API.

## 13. Proxy, CDN và timeout là yếu tố quyết định stream có “thật” hay không

Lỗi phổ biến nhất khi deploy SSE: Spring đã gọi `send` hoặc Flux đã emit, nhưng client chỉ thấy events **dồn một cục sau 30 giây** hoặc connection bị cắt định kỳ. Nguyên nhân thường là proxy buffering, idle timeout, compression buffering, CDN không hỗ trợ streaming như mong đợi hoặc HTTP topology.

### 13.1. NGINX ví dụ cho SSE

Snippet NGINX sau **cần** upstream `spring_backend` và server config của môi trường; không phải file nginx.conf độc lập:

~~~nginx
location /events/ {
    proxy_pass http://spring_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}
~~~

Giải thích:

- `proxy_buffering off`: chuyển data downstream khi nhận được thay vì đợi đầy buffer.
- `proxy_cache off`: không shared-cache response stream. Với dữ liệu cá nhân, origin nên dùng `Cache-Control: no-store`.
- `proxy_read_timeout 3600s` là giới hạn **không nhận bytes từ upstream trong một khoảng liên tục**, không nhất thiết là tổng duration của connection. Heartbeat phải có cadence phù hợp và proxy/cloud LB có timeout riêng.
- `proxy_http_version 1.1`, `Connection ""` giúp upstream connection phù hợp HTTP streaming trong cấu hình thường gặp; kiểm thử thực tế theo topology.
- `X-Accel-Buffering: no` từ origin có thể được NGINX tôn trọng nếu cấu hình cho phép; không thay rule khi CDN phía trước vẫn buffer.

Một CDN hoặc WAF ở phía trước NGINX có thể tự buffer, cache, giới hạn response duration hoặc áp compression. Test bằng **public hostname qua toàn bộ hops** và so sánh với việc gọi thẳng port Spring Boot.

### 13.2. Heartbeat và flush

Một SSE heartbeat comment có thể ngăn idle timeout **nếu** intermediary thực sự forwarding bytes và không gom buffer. Chỉ đặt `proxy_read_timeout` cao nhưng không gửi bất kỳ bytes nào trong hàng phút có thể vẫn khiến mobile network/TCP path ngắt. Ngược lại heartbeat quá nhanh với hàng chục nghìn clients tạo overhead.

Chọn chu kỳ heartbeat bằng đo lường: ví dụ 15–30 giây khi các timeout ở proxy/LB lớn hơn rõ rệt, nhưng không áp một số duy nhất cho mọi hệ thống. Kiểm tra thời gian thực giữa event server phát và browser nhận, không chỉ theo logs server.

### 13.3. HTTP/1.1 và HTTP/2

Với HTTP/1.1, browser có giới hạn số connection đồng thời đến một origin, và mỗi EventSource có thể chiếm một kết nối lâu. Mở nhiều tabs/streams có thể ảnh hưởng fetch khác. HTTP/2 multiplexing giúp chia sẻ connection, nhưng số streams vẫn có giới hạn được thương lượng bởi client/server/proxy; không có nghĩa vô hạn.

Tính đến việc user mở nhiều tabs, reconnect storm sau deploy, mobile sleep/resume và rolling restart. Dùng một stream multiplex các topic qua trường `event:` khi phù hợp thay vì mở quá nhiều EventSource độc lập.

## 14. Bài toán multi-instance: emitters và subscribers không tự được chia sẻ

Giả sử:

~~~text
Client A -- LB --> Spring node 1 -- SseEmitter A
Client B -- LB --> Spring node 2 -- SseEmitter B

Business event xử lý ở node 3
~~~

Nếu node 3 tự gọi emitter registry trong RAM của nó, A/B không nhận được gì. Mỗi JVM có registry/subscription riêng. Cần một bus:

~~~text
Business services
       |
       v
Redis Pub/Sub / Kafka / RabbitMQ / DB change stream
       |
       +--> Node 1 -> emitters/subscriptions node 1
       +--> Node 2 -> emitters/subscriptions node 2
       +--> Node 3 -> emitters/subscriptions node 3
~~~

Nhưng không đánh đồng các broker:

- Redis Pub/Sub đơn giản cho live notifications, **không durable replay** nếu subscriber offline.
- Redis Streams/Kafka/event log có thể hỗ trợ cursor/replay tùy policy và retention.
- MQ/DB transaction/outbox giúp gắn event phát ra với business state đúng hơn; cần idempotency.
- Routing topic/user phải có authorization. Không broadcast tất cả PII vào mọi node/client rồi dựa trên frontend tự lọc.
- Sticky load balancing không phải là event delivery protocol; node restart vẫn đóng HTTP stream, browser reconnect. Shared durable event log mới hỗ trợ resume có ý nghĩa.

Nếu chỉ cần hiển thị trạng thái hiện tại, có thể resync bằng REST snapshot sau reconnect thay vì dựng một event log đầy đủ.

## 15. Test MVC SSE: kiểm tra request là async

Trong project MVC, thêm `src/test/java/demo/mvcsse/MvcSseTest.java`:

~~~java
package demo.mvcsse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcSseTest {
    @Autowired
    MockMvc mvc;

    @Test
    void sseUsesAsyncServletProcessing() throws Exception {
        mvc.perform(get("/events/mvc")
                .accept(MediaType.TEXT_EVENT_STREAM))
            .andExpect(status().isOk())
            .andExpect(request().asyncStarted())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM));
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.mvcsse.MvcSseTest
~~~

Test này kiểm tra **async request đã được khởi tạo**, response status và media type. Nó **không** test streaming thật qua network, proxy buffering hay 5 events đầy đủ. Một `MockMvc` test với `asyncDispatch` có thể kiểm tra nội dung của một stream hữu hạn sau khi emitter complete, nhưng phải chọn timeout phù hợp và tránh dùng stream vô hạn gây test treo.

Để kiểm tra từng event tại runtime, dùng `curl -N` hoặc HTTP client streaming integration test qua port thật; đối chiếu thứ tự ID và event name/payload sau mỗi chu kỳ. Test disconnect bằng hủy cURL/`EventSource.close()` rồi quan sát cleanup/metrics, không chỉ HTTP status.

## 16. Test WebFlux SSE: WebTestClient + StepVerifier

Trong project WebFlux, tạo `src/test/java/demo/fluxsse/FluxSseTest.java`:

~~~java
package demo.fluxsse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FluxSseTest {
    @Autowired
    WebTestClient client;

    @Test
    void firstEventHasNameIdAndPayload() {
        var result = client.get()
                .uri("/events/reactive")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<Tick>>() { });

        StepVerifier.create(result.getResponseBody().take(1))
                .expectNextMatches(event ->
                        "tick".equals(event.event())
                        && "flux-1".equals(event.id())
                        && event.data() != null
                        && event.data().sequence() == 1)
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.fluxsse.FluxSseTest
~~~

`WebTestClient` kiểm tra response streaming; `StepVerifier` subscribe, lấy một event rồi `take(1)` cancel upstream, không chờ toàn bộ 5 seconds. Test này minh họa cancellation gắn với consumption. Nếu muốn test tất cả năm tick và done, tiêu thụ sáu records, kiểm tra `event`/`id`/payload theo thứ tự và đặt thời gian chờ phù hợp.

**Cần lưu ý:** `RANDOM_PORT` + `@AutoConfigureWebTestClient` tạo test đi qua HTTP runtime reactive, nhưng vẫn chưa đi qua external CDN/ingress. Một test HTTP streaming qua public URL/staging mới giúp phát hiện buffering và idle timeout thực tế.

## 17. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Browser gọi SSE nhận 404 | Path/port sai, controller không được scan | Kiểm tra mapping, app type và URL |
| HTTP 406 Not Acceptable | `produces`/Accept không tương thích | Dùng `text/event-stream` đúng |
| Network 200 nhưng UI không cập nhật | Event là named `tick`, JS chỉ dùng `onmessage` | `addEventListener("tick", ...)` |
| Events tới dồn một cục | NGINX/CDN/compression buffering | Tắt buffering, thử `curl -N` qua origin và public URL |
| Kết nối ngắt sau 30/60s | Servlet async timeout, proxy idle timeout, cloud LB | Căn timeout và heartbeat |
| MVC hết thread khi nhiều clients | Per-client thread, blocking writes, executor nhỏ/không giới hạn | Bounded pool, quota, đánh giá WebFlux |
| Emitter vẫn ở map sau disconnect | Không đăng ký cleanup handlers | onCompletion/onError/onTimeout và remove registry |
| `send` ném IOException | Client mất kết nối, network failure | Dừng producer, để container async error lifecycle xử lý |
| WebFlux không stream tới browser | Dùng `collectList()`/blocking logic hoặc sai media type | Trả Flux và `text/event-stream` |
| `block()` gây lỗi/lag trên Netty | Blocking call trên event loop | Reactive I/O hoặc offload blocking đúng cách |
| Browser tự reconnect mãi sau done | Chỉ server `complete()`, client không `close()` | Gửi named `done` và đóng EventSource |
| Reconnect mất events | Không có durable log/replay | Last-Event-ID + event store/REST resync |
| Reconnect nhận duplicates | Replay/live overlap và at-least-once delivery | Idempotent client và dedup theo event ID |
| OAuth2 bearer không đi qua EventSource | Native EventSource không đặt arbitrary headers | BFF cookie hoặc streaming fetch/client thích hợp |
| Browser báo CORS dù curl thành công | Origin/credentials/CORS policy sai | Kiểm tra CORS final headers, SameSite |
| Stream bên ngoài LB lag nhưng local bình thường | Proxy/CDN response buffering hoặc cache | Kiểm thử public route, inspect headers |
| Tin rằng WebFlux tự đảm bảo backpressure vô hạn | Hot sources và queues có giới hạn | Bounded overflow policy, metrics, slow client rules |
| SSE lộ thông báo tenant khác | Subscription routing/authorization sai | Scope stream theo principal, audit per event |
| SSE bị ghi vào shared CDN cache | Cache-Control/rule chưa phù hợp | Bypass shared cache, no-store với PII |

**Quy trình điều tra thực dụng:**

1. Dùng `curl -N -i` gọi trực tiếp Spring, xem HTTP status, Content-Type, từng record và khoảng thời gian đến.
2. Gọi **cùng URL qua public proxy/CDN**, đối chiếu timestamp: nếu chỉ ở public route mới dồn, kiểm tra buffering/timeouts.
3. Trong browser Network, kiểm tra Request Headers, CORS, EventStream tab, named event listeners và `EventSource.readyState`.
4. Đo số active emitters/subscribers, số task, thread pool usage, write latency, cancellation và timeout.
5. Nếu mất/double event, xem ID, Last-Event-ID, retention và cơ chế replay; không chỉ thay retry milliseconds.
6. Nếu auth lỗi, xem cookie/bearer mode, principal/tenant, quyền subscribe; không log raw tokens.
7. Test kill connection, rolling deploy, mạng chập chờn và slow client trên staging, không làm điều này với production stream có dữ liệu thật.

## 18. Observability và vận hành SSE

Các metrics nên thiết kế có cardinality kiểm soát:

- `sse.connections.active` theo route/node (không dùng session ID/user ID làm metric label).
- `sse.connections.opened`, `completed`, `timed_out`, `errored`, `canceled`.
- `sse.events.sent` và `sse.bytes.sent` theo event type/tập hợp route.
- `sse.send.latency` trong MVC; elapsed time giữa publish và browser receive nếu có client telemetry.
- `sse.backlog.depth`, `dropped.events`, `replay.events` nếu có buffer/pubsub.
- `sse.reconnect.rate`, tỷ lệ auth failures, quota exceeded, node distribution.
- Per-route proxy read timeouts, 499/client disconnect hoặc vendor-specific status, HTTP/2 streams và container socket usage.

Một stream sống lâu làm tăng số open connections/file descriptors. Kiểm soát: per-user quotas, request/auth rate limits, resource budgets, heartbeat, shutdown/draining và global capacity. Đừng log từng heartbeat với PII ở mức INFO cho hàng nghìn subscribers, vì log sẽ nổ và dễ chứa dữ liệu nhạy cảm.

### Graceful shutdown và rolling deployment

Khi node được đưa khỏi load balancer, connections cũ có thể tiếp tục đến hết grace period rồi bị đóng. Browser reconnect sang node khác; **nó cần resume/replay hoặc REST resync** nếu sự kiện bị bỏ lỡ. Sticky LB không đảm bảo session event stream không gián đoạn khi node chết.

Nếu app có `SseEmitter` registry, nên dọn khi Spring context đóng và cancel tasks; nếu reactive có subscriptions tới broker, cần dispose/cancel. Đặt shutdown timeout phù hợp load balancer draining và không coi “node healthy” nghĩa stream không bị reset.

## 19. Bảo mật payload và chính sách cache

Một stream riêng có thể mang số dư, nội dung chat, trạng thái đơn hàng hoặc dữ liệu người dùng. Các lưu ý:

1. Authenticate và authorize **trước khi cho subscribe**, sau đó bảo vệ mỗi topic/tenant và chính sách khi quyền thay đổi.
2. Dùng **HTTPS**, cookie Secure/HttpOnly/SameSite hoặc bearer transport phù hợp; đừng dùng query chứa long-lived access token.
3. CORS chỉ cho trusted origins; credentialed response không dùng wildcard ACAO.
4. SSE GET không được thực hiện side-effect nghiệp vụ; các API POST/PUT/DELETE tách riêng, chống CSRF theo credential mode.
5. Response riêng đặt `Cache-Control: no-store, no-transform` hoặc policy riêng tư phù hợp; **no-cache không cấm lưu**, no-transform không cấm cache.
6. Đừng để CDN shared-cache luồng SSE cá nhân hoặc trả response user A cho B.
7. Xử lý data serialization bằng framework; nếu tự tạo SSE strings, chống CR/LF injection khi payload không tin cậy.
8. Không đưa raw access token, Cookie, session ID hay dữ liệu nhạy cảm vào metrics/logs/sự kiện debug.
9. Nếu client refresh/reconnect, xác minh owner/tenant tại query replay; Last-Event-ID không là quyền truy cập.
10. Áp connection quotas để tránh một account mở hàng nghìn streams gây DoS.

**Một stream đã được mở trước khi user logout** có thể tiếp tục nhận sự kiện nếu server không có revalidation/revocation policy. Thiết kế connection lifetime và cancel-on-revoke theo yêu cầu sản phẩm.

## 20. Đánh giá kết quả: bài thực hành end-to-end

Hãy thực hiện hai dự án riêng, dùng cùng một contract logic:

- `tick` có `id` tăng 1..5 và `data` là JSON chứa `sequence` + `message`.
- `done` sau tick cuối, frontend đóng EventSource.
- MVC qua port 8081; WebFlux qua port 8082.
- Mỗi đường được kiểm tra bằng cURL, bằng browser và bằng test tương ứng.

**Bài kiểm tra 1 — format:** kiểm tra response 200, `text/event-stream`, dòng trống phân tách record, `event:tick` + `data:...` và ID có thứ tự. Kết quả không phải JSON array.

**Bài kiểm tra 2 — timing:** ghi thời điểm nhận từng record bằng cURL/Browser. Có đúng mỗi ~1 giây không hay bị gom? Nếu chỉ qua NGINX bị gom, tập trung proxy buffering.

**Bài kiểm tra 3 — disconnect:** mở cURL, đóng bằng Ctrl+C sau tick thứ hai. Trong MVC, task phải được cancel sau lỗi/callback thích hợp; trong WebFlux, nguồn reactive cần nhận cancel. Không kỳ vọng event nguồn dừng tức thì ở mọi transport nếu chưa có write mới.

**Bài kiểm tra 4 — client done:** giữ browser mở sau tick thứ năm. JS có `addEventListener("done")` và `close()` thì không tái khởi động luồng. Nếu xóa close, EventSource có thể reconnect.

**Bài kiểm tra 5 — auth:** thử một stream yêu cầu đăng nhập bằng session cookie qua same-origin; user chưa authenticated phải bị từ chối. Với cross-origin, kiểm tra CORS/credentials và SameSite.

**Bài kiểm tra 6 — reconnect:** cố ngắt và kết nối lại. Demo phát từ đầu; hãy giải thích vì sao `Last-Event-ID` tự nó không replay, rồi thiết kế thêm event store nếu cần.

**Bài kiểm tra 7 — slow client:** giả lập client đọc chậm ở staging và theo dõi memory, task/thread pool, event backlog. Đừng chỉ xem HTTP status rồi kết luận hệ thống chịu tải.

**Bài kiểm tra 8 — deploy:** kết nối qua hai Spring instances, restart node nhận request, kiểm tra reconnect, authorization và replay semantics.

## 21. Checklist chọn MVC hay WebFlux trong dự án thật

1. App hiện đang dùng Spring MVC/JPA blocking hay WebFlux/R2DBC/WebClient reactive?
2. Dự kiến có bao nhiêu concurrent SSE connections và tốc độ events?
3. Có payload JSON nhỏ theo chu kỳ, hay event stream tần suất cao cần buffer/replay?
4. Có cần broker multi-node, cursor durable và exactly-once business effects không?
5. Có rủi ro slow client làm blocked threads hoặc memory queue tăng không?
6. Timeout của app, proxy, LB và browser đã được đo, heartbeat phù hợp chưa?
7. Có yêu cầu authentication/cross-origin browser cookie/bearer hay không?
8. User đổi role/tenant/logout trong khi stream đang sống được xử lý thế nào?
9. Với MVC, callbacks cleanup và scheduler/executor bounded chưa?
10. Với WebFlux, toàn pipeline có nonblocking không, và cancellation/backpressure đã kiểm thử chưa?
11. Có test browser EventSource, curl -N, origin vs CDN và shutdown/reconnect chưa?
12. Có quan sát active streams, latency, reconnect, dropped/replayed events và quotas chưa?

**Quy tắc thực tế:** không đổi toàn bộ stack chỉ vì muốn phát vài notification SSE. SseEmitter đủ tốt cho nhiều ứng dụng MVC quy mô vừa nếu quản lý async lifecycle đúng. Nếu đã xây reactive web stack với nhu cầu lượng stream lớn, Flux/ServerSentEvent là lựa chọn tự nhiên — nhưng vẫn cần hạ tầng proxy, sự kiện bền và chính sách tài nguyên.

## 22. Câu hỏi tự kiểm tra

**1.** SSE là push hai chiều như WebSocket?

**Đáp án:** Không. SSE là stream HTTP một chiều server → client. Browser gửi commands bằng HTTP request khác hoặc dùng WebSocket nếu cần hai chiều liên tục.

**2.** `SseEmitter.send(...)` có làm response kết thúc sau một event?

**Đáp án:** Không. Nó ghi thêm record SSE. Request vẫn mở tới khi `complete()`, timeout, error hoặc disconnect, tùy lifecycle.

**3.** `Flux.just("a","b")` có tự là SSE không?

**Đáp án:** Chỉ khi mapping/content negotiation chọn `text/event-stream` và encoder phù hợp. Nếu cần named event/id/retry, dùng `Flux<ServerSentEvent<T>>`.

**4.** Vì sao MVC có `SseEmitter` vẫn có thể cạn threads?

**Đáp án:** Servlet async giải phóng request thread nhưng các lần ghi `send` có thể blocking trên worker; per-client threads/unbounded queues và slow clients vẫn gây cạn tài nguyên.

**5.** Khi `send` ném IOException vì client mất kết nối, có cần gọi `completeWithError` ngay không?

**Đáp án:** Theo hướng dẫn Spring MVC, không; container/Spring xử lý async error notification. App dừng producer và dọn resource, tránh double-completion.

**6.** Browser chỉ dùng `source.onmessage` nhưng server gửi `event: tick`, tại sao không nhận?

**Đáp án:** Đây là named event. Dùng `source.addEventListener("tick", ...)`; `onmessage` cho event mặc định không có tên.

**7.** EventSource có tự replay các events đã mất khi reconnect nếu server dùng `id`?

**Đáp án:** Không. Browser có thể gửi `Last-Event-ID`, nhưng server phải có durable store/cursor logic để replay. Client vẫn cần deduplicate/idempotency.

**8.** `retry: 3000` là timeout server hoặc TTL cache?

**Đáp án:** Không. Đó là gợi ý thời gian reconnect của client tính bằng mili giây; không phải request timeout, không phải `Access-Control-Max-Age` và không phải `Cache-Control`.

**9.** WebFlux tự biến mọi JDBC query trong stream thành nonblocking?

**Đáp án:** Không. Blocking JDBC cần offload hoặc giải pháp nonblocking phù hợp; gọi `block()` trên event loop có thể phá khả năng mở rộng.

**10.** API bearer token trong header có thể dùng native EventSource để tự thêm Authorization?

**Đáp án:** Native EventSource không hỗ trợ arbitrary request headers. Dùng streaming fetch/parser, BFF-cookie hoặc giải pháp auth khác có threat model rõ.

**11.** Vì sao test cURL local thấy mỗi giây một event nhưng CDN public URL nhận dồn cả 5?

**Đáp án:** Cần kiểm tra proxy buffering/compression/CDN streaming behavior và cache policy, không chỉ code SseEmitter/Flux.

**12.** Một user đã được xác thực có thể subscribe bất kỳ `/events/orders/{id}`?

**Đáp án:** Không. Phải kiểm tra owner/tenant/resource authorization và cả quyền khi stream sống dài, không chỉ `authenticated()`.

## 23. Tài liệu tham khảo chính thức

- [Spring Framework — MVC Asynchronous Requests và SSE](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `ResponseBodyEmitter`, `SseEmitter`, disconnect, Servlet async executor/timeout.
- [Spring Framework — SseEmitter Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html): `send`, `event`, timeout và lifecycle.
- [Spring Framework — WebFlux Controller Return Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): `Flux<ServerSentEvent>` và text/event-stream.
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): encoding reactive Publishers thành response stream.
- [Spring Framework — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): builder có `id`, `event`, `retry`, `comment` và `data`.
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, framing, event fields, reconnect, comments và browser behavior.
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource): API `close`, `withCredentials` và event listeners.
- [HTML Standard — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): đặc tả chuẩn event stream, reconnection và Last-Event-ID.
- [Reactor Core — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): interval/take/concatWith/doFinally, backpressure/cancellation.
- [Spring Boot — Web applications](https://docs.spring.io/spring-boot/reference/web/index.html): lựa chọn Servlet vs Reactive stack, runtime configuration.

**Kết luận:** `SseEmitter` cho phép **MVC/Servlet** chủ động `send` từng SSE record từ worker và phải dọn async tasks/emitters; `Flux<ServerSentEvent<T>>` cho phép **WebFlux** phát SSE từ Publisher với cancellation/backpressure semantics. Cả hai đều phải tuân `text/event-stream`, xử lý proxy buffering/timeout, bảo vệ stream theo user/tenant, giới hạn tài nguyên và thiết kế `Last-Event-ID` + replay nếu dữ liệu phải liên tục sau reconnect.
