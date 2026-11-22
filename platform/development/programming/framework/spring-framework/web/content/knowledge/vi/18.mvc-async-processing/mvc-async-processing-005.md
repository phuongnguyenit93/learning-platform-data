# ResponseBodyEmitter, SseEmitter và StreamingResponseBody trong Spring MVC

## 1. Khi nào một HTTP response nên được gửi theo dòng thời gian?

Phản hồi thông thường của Spring MVC thường được hoàn thành trong một lần:

```text
Client                Spring MVC
  | GET /api/report        |
  |----------------------->|
  |                        | Tính toàn bộ kết quả
  |<-----------------------| HTTP 200 + JSON hoàn chỉnh
  |     kết thúc           |
```

Nhưng một số yêu cầu cần **truyền kết quả thành nhiều phần** khi dữ liệu sẵn sàng:

- Một công việc dài gửi các bước tiến độ (queued, running, completed).
- Browser nhận thông báo một chiều từ server qua **Server-Sent Events (SSE)**.
- API sinh báo cáo CSV hoặc nội dung nhị phân lớn mà không giữ toàn bộ output trong RAM.
- Một truy vấn trả nhiều record tuần tự dưới dạng **NDJSON** (mỗi dòng là một JSON value).
- Hệ thống cần giảm **time to first byte** và tránh tạo một mảng/list lớn trước khi trả response.

Spring MVC Servlet cung cấp ba kiểu trả về tiêu biểu:

| API | Đơn vị được ghi | Định dạng | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **`ResponseBodyEmitter`** | Nhiều object; mỗi object qua `HttpMessageConverter` | Do ứng dụng quyết định, ví dụ text/NDJSON | Tiến độ dạng nhiều fragment, streaming các object |
| **`SseEmitter`** | Nhiều SSE events, là subclass của `ResponseBodyEmitter` | `text/event-stream`, có `event/id/data/retry` | EventSource của browser, thông báo một chiều |
| **`StreamingResponseBody`** | Bytes trực tiếp trên `OutputStream` | CSV, binary, text tùy code | Download/ghi stream không cần message conversion mỗi object |

Cả ba thuộc Spring MVC **bất đồng bộ**, nhưng **không biến Servlet output I/O thành non-blocking I/O**. Khi ghi response, một thread vẫn có thể bị block bởi network hoặc downstream client. Đây là điểm khác biệt quan trọng so với Spring WebFlux.

**Phạm vi:** Spring Framework 6.2.x / Spring Boot 3.5.x, Java 17+, **Servlet MVC** (ví dụ embedded Tomcat). Không import nhầm API reactive WebFlux khi dùng ba kiểu này.

## 2. Cơ sở Servlet async: request thread kết thúc nhưng response còn mở

Trong xử lý đồng bộ, container thread đi qua filters, `DispatcherServlet`, controller, ghi response rồi thoát. Với MVC async, Spring gọi cơ chế `request.startAsync()` của Servlet API (thông qua framework), cho phép **request thread trả về container** trong khi HTTP response chưa hoàn thành.

```text
HTTP GET /demo/events
       |
       v
Servlet container REQUEST dispatch (Thread A)
       |
Filters -> DispatcherServlet -> Controller
       |
Controller trả SseEmitter/ResponseBodyEmitter
       |
Spring MVC kích hoạt Servlet async
       |
Thread A trả về pool (response vẫn mở)
       |
Producer thread / message source (Thread B)
       |
  emitter.send(...) nhiều lần
       |
  emitter.complete() hoặc timeout/error/disconnect
       |
Servlet ASYNC dispatch để hoàn tất vòng đời
       |
Response kết thúc, callbacks cleanup
```

Đối với `StreamingResponseBody`, callback `writeTo(OutputStream)` được thực thi bất đồng bộ bởi MVC task executor, thay vì bắt container request thread chờ toàn bộ download. Vì vậy cần cấu hình **`AsyncTaskExecutor` có giới hạn và phù hợp tải thực tế**.

### “Async” không đồng nghĩa “không sử dụng thread”

- Servlet request thread có thể được giải phóng khi controller trả emitter hoặc streaming callback.
- Producer vẫn cần thread/worker hoặc một nguồn sự kiện có cơ chế phù hợp.
- Ghi `OutputStream` trong Spring MVC vẫn là thao tác **blocking** theo mô hình Servlet output truyền thống.
- Nếu client tải cực chậm, thread đang gọi `send` hoặc `writeTo` có thể bị chặn.
- Việc trả `Flux` trong Spring MVC có thể hỗ trợ reactive backpressure ở giao diện publisher, nhưng việc ghi HTTP cuối cùng vẫn có thể diễn ra trên thread và block.
- Với hệ thống có số lượng lớn kết nối kéo dài và mục tiêu I/O non-blocking end-to-end, cần cân nhắc **Spring WebFlux, WebSocket hoặc hạ tầng event streaming khác** theo đặc điểm ứng dụng.

## 3. So sánh trực tiếp ba API và các kiểu async khác

| Đặc tính | `ResponseBodyEmitter` | `SseEmitter` | `StreamingResponseBody` |
| --- | --- | --- | --- |
| Trả nhiều giá trị | Có | Có | Có, dưới dạng nhiều lần ghi bytes |
| Conversion object | Qua `HttpMessageConverter` | Qua converter cho phần data | **Không** cho bytes được viết trực tiếp |
| Tự có SSE event formatting | Không | **Có** | Không |
| Đọc từ JavaScript `EventSource` | Chỉ khi tự tạo đúng wire format | **Phù hợp nhất** | Có thể tự viết SSE bytes nhưng ít tiện |
| Dành cho file/CSV lớn | Có thể, nhưng ít trực tiếp | Không phải mục tiêu chính | **Phù hợp nhất** |
| Kiểm soát response status/headers | Trả trong `ResponseEntity<ResponseBodyEmitter>` | `ResponseEntity<SseEmitter>` | `ResponseEntity<StreamingResponseBody>` |
| Timeout callback tích hợp emitter | `onTimeout` | Kế thừa `onTimeout` | Không có emitter callback; xử lý qua MVC/Servlet async infrastructure |
| Hoàn tất bình thường | `complete()` | `complete()` | Callback `writeTo` trả về |
| Error application-level | `completeWithError(ex)` khi phù hợp | Kế thừa `completeWithError` | `writeTo` ném IOException/exception |
| Khi client ngắt | Ghi tiếp có thể gây IOException | Ghi heartbeat/event có thể phát hiện disconnect | `writeTo` có thể ném IOException |
| Đơn vị hiển thị phía client | Phụ thuộc content framing do bạn chọn | Event theo chuẩn SSE | Bytes do code xác định |

`DeferredResult<T>` và `Callable<T>` giải quyết **một kết quả bất đồng bộ**; chúng không tự tạo nhiều message trong một HTTP response. `WebAsyncTask` là cách cấu hình cho `Callable`. Nếu một job trả một JSON object sau khi hoàn tất, `DeferredResult` có thể đúng hơn. Nếu cần nhiều thông báo trên một response, hãy chọn trong ba API trên.

### HTTP chunked transfer không phải wire protocol riêng của API

Khi không biết Content-Length, HTTP/1.1 server có thể dùng `Transfer-Encoding: chunked`; HTTP/2 có frame riêng. **Đừng viết hoặc parse chunk markers** trong code ứng dụng. Bạn viết logical data/fragments, container và HTTP stack quyết định cách biểu diễn transport.

Ngay cả khi gọi `flush()`, proxy, CDN, compression, browser buffering hoặc TCP vẫn có thể làm dữ liệu đến theo các nhóm khác nhau. Không dựa vào “mỗi `send` tạo chính xác một network chunk”.

## 4. `ResponseBodyEmitter`: gửi lần lượt nhiều object

Class:

```java
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter;
```

Controller có thể trả emitter ngay:

```java
@GetMapping("/progress")
ResponseBodyEmitter progress() {
    ResponseBodyEmitter emitter = new ResponseBodyEmitter(30_000L);
    // Producer ở thành phần/thread khác sẽ gọi send và complete.
    return emitter;
}
```

**Đây là method fragment**, không phải flow hoàn chỉnh; nếu không có producer hoặc không gọi complete, kết nối có thể treo tới timeout.

### 4.1. API thiết yếu

- `new ResponseBodyEmitter()`: timeout từ cấu hình MVC/server nếu không đặt riêng.
- `new ResponseBodyEmitter(Long timeout)`: timeout cho emitter; đơn vị **milliseconds**.
- `send(Object object)`: chuyển object qua một `HttpMessageConverter` tương thích.
- `send(Object object, MediaType hint)`: đưa media type gợi ý để chọn converter.
- `complete()`: thông báo producer hoàn tất bình thường.
- `completeWithError(Throwable)`: hoàn tất với lỗi application-level phù hợp, kích hoạt async dispatch.
- `onTimeout(Runnable)`: callback khi request async bị timeout.
- `onError(Consumer<Throwable>)`: callback khi xử lý async gặp lỗi.
- `onCompletion(Runnable)`: callback khi request async kết thúc, gồm success, timeout và network error.

Spring 6.2 cho phép đăng ký nhiều callbacks cho các lifecycle events nói trên. Các callbacks có thể chạy trên **container threads**, không mặc định cùng producer thread. Vì vậy mọi shared state phải thread-safe.

### 4.2. Một emitter không tự tạo NDJSON hợp lệ

Nếu muốn nhiều records dưới dạng NDJSON:

```text
{"seq":1,"state":"queued"}
{"seq":2,"state":"running"}
{"seq":3,"state":"done"}
```

Mỗi dòng phải là JSON value hợp lệ và có delimiter **newline**. Việc gọi `emitter.send(object, MediaType.APPLICATION_JSON)` liên tiếp không tự bảo đảm các object được phân tách thành từng dòng: nếu chỉ ghép JSON object sát nhau, output `{}{}` không phải một JSON document hoặc NDJSON hợp lệ.

Một producer có thể gửi **object JSON rồi ký tự newline** theo đúng contract:

```java
emitter.send(new Progress(1, "queued"), MediaType.APPLICATION_JSON);
emitter.send("\n", MediaType.TEXT_PLAIN);

emitter.send(new Progress(2, "done"), MediaType.APPLICATION_JSON);
emitter.send("\n", MediaType.TEXT_PLAIN);

emitter.complete();
```

Đây là **fragment**, giả định record `Progress` và emitter đã được khai báo. Trong ví dụ runnable phần 9, server dùng `application/x-ndjson` ở response, dùng converter JSON cho từng record và text/plain cho delimiter.

Nếu cần đảm bảo framing/flush đặc thù ở tốc độ rất cao, `StreamingResponseBody` có thể phù hợp hơn hoặc chọn framework chuyên biệt cho publisher/batching.

### 4.3. Error lifecycle: đặc biệt với IOException

Theo hướng dẫn Spring MVC:

- Nếu `emitter.send(...)` ném **`IOException`** vì client đã ngắt hoặc network write thất bại, **không tự gọi `complete()` hoặc `completeWithError()`** từ nhánh đó. Servlet container sẽ thông báo async error; Spring hoàn tất request qua xử lý tương ứng.
- Với lỗi **do ứng dụng phát sinh** trong producer (business failure, serialization bug trước khi response committed), `completeWithError(ex)` có thể được sử dụng, nếu emitter chưa hoàn tất.
- Khi response đã commit (đã ghi bytes/headers), handler lỗi **không chắc có thể thay HTTP status thành 500 hoặc thay body bằng JSON error**. Client có thể nhận phần dữ liệu đầu rồi stream đột ngột kết thúc.
- `onCompletion` là nơi phù hợp để gỡ reference emitter khỏi registry và giải phóng tài nguyên; đừng coi nó chỉ xảy ra trên happy path.

## 5. `SseEmitter`: Server-Sent Events chuẩn cho browser

Class:

```java
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
```

`SseEmitter` kế thừa `ResponseBodyEmitter` nhưng bổ sung cách xây **SSE event**:

```java
SseEmitter emitter = new SseEmitter(30_000L);

emitter.send(SseEmitter.event()
        .id("event-42")
        .name("progress")
        .reconnectTime(2_000L)
        .data("Đã hoàn thành 42%"));
```

Đây là **fragment**, chưa có controller/executor và exception handling. `SseEmitter.event()` trả `SseEventBuilder` để đặt fields; `send(builder)` ghi event theo định dạng `text/event-stream`.

### 5.1. Định dạng wire của SSE

Một stream SSE là **UTF-8 text** với các events tách nhau bởi **dòng trống**:

```text
id: 42
event: progress
retry: 2000
data: {"percent":42}

id: 43
event: finished
data: {"percent":100}

```

Các trường quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| `data:` | Payload. Nhiều dòng `data:` liên tiếp được nối bằng newline ở client |
| `event:` | Loại event để JavaScript dùng `addEventListener("progress",...)` |
| `id:` | Event ID, dùng cho `lastEventId` và cơ chế reconnect |
| `retry:` | Gợi ý milliseconds cho client khi reconnect; phải là số nguyên |
| Dòng bắt đầu bằng `:` | Comment/heartbeat, client không coi là application event |
| Dòng trống | Kết thúc một event frame |

**Tên field không phải HTTP headers.** `id:` ở đây nằm trong response body `text/event-stream`, không phải `ETag` hay HTTP `Last-Modified`. Mỗi event cần có frame delimiter đúng; `SseEmitter` giúp giảm sai sót khi tự nối các chuỗi.

### 5.2. JavaScript `EventSource`

Browser có API EventSource:

```javascript
const source = new EventSource("/demo/sse");

source.addEventListener("progress", event => {
  console.log("Progress:", event.lastEventId, event.data);
});

source.addEventListener("finished", event => {
  console.log("Finished:", event.data);
  source.close(); // Demo stream hữu hạn, tránh tự reconnect.
});

source.onerror = event => {
  console.warn("SSE interrupted", event);
};
```

Lưu ý:

- `EventSource` dùng **HTTP GET** để đăng ký stream.
- Một kết nối bị đóng có thể **tự reconnect** theo chính sách browser; với stream cố ý kết thúc sau vài events, client nên gọi `source.close()` hoặc có protocol stop thích hợp.
- `EventSource` hỗ trợ thông điệp **server → client**; muốn client gửi commands thường dùng POST/PUT qua `fetch` hoặc WebSocket nếu cần hai chiều.
- EventSource trong browser không có API chuẩn để tự gắn mọi custom request header; với auth thường dùng cookie phù hợp hoặc kiến trúc gateway/token có thiết kế riêng. Không đưa access token thô vào URL query.
- Cross-origin EventSource cần cấu hình CORS chính xác. Nếu dùng credentials/cookies, cần `withCredentials: true` và CORS policy cho phép origin cụ thể; không dùng wildcard origin khi cho credentials.
- SSE được hỗ trợ trên nhiều browser hiện đại; proxy/CDN buffering và HTTP/1.1 connection limits có thể gây khó khi mở nhiều tab.

### 5.3. `Last-Event-ID` và reconnect

Nếu server gửi `id: 42`, browser có thể gửi **`Last-Event-ID: 42`** ở lần kết nối lại. Điều này **không tự tạo replay log trong Spring**. Nếu app chỉ giữ emitter trong RAM, khi reconnect sang node khác hoặc sau restart nó không biết phải gửi tiếp từ event nào.

Một hệ thống SSE production nếu cần delivery continuity phải:

1. Gán IDs ổn định, có thứ tự theo stream/resource.
2. Lưu events trong broker/database/log theo retention policy.
3. Khi client gửi Last-Event-ID, kiểm tra ID theo người dùng/tenant/stream, sau đó replay events phù hợp.
4. Xử lý duplicate events theo semantics **at-least-once** nếu cần; client cần idempotency.
5. Giải quyết gap nếu event cũ đã hết retention.
6. Khi scale nhiều nodes, dùng shared event source hoặc pub/sub, không chỉ local map of emitters.

**Đừng hứa exactly-once** chỉ vì SSE có `id`.

### 5.4. Heartbeat và phát hiện disconnect

Servlet API không thông báo client disconnect ngay lập tức trong mọi tình huống. Với stream chạy lâu, cần **gửi dữ liệu định kỳ** để giữ kết nối và phát hiện write failure. SSE có thể dùng event comment:

```java
emitter.send(SseEmitter.event().comment("heartbeat"));
```

Đây là fragment. Comment `:heartbeat` không tạo application event ở browser. Interval cần nhỏ hơn idle timeout của proxy/container theo kiến trúc, có jitter/backoff nếu thích hợp. Heartbeat không thay thế authorization, connection limits hoặc subscriber cleanup.

Không thiết kế **mỗi client một Thread.sleep vô hạn**; cần scheduler/producer event loop có giới hạn, đo số subscribers, tối ưu broadcaster và xử lý slow clients.

## 6. `StreamingResponseBody`: ghi trực tiếp tới OutputStream

Class là functional interface:

```java
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
```

Method cốt lõi:

```java
void writeTo(OutputStream outputStream) throws IOException;
```

Spring MVC thực thi callback `writeTo` bất đồng bộ, cho ứng dụng **ghi bytes trực tiếp**. Không có message conversion cho từng object như `ResponseBodyEmitter`.

Ví dụ một CSV response:

```java
@GetMapping(path = "/export.csv", produces = "text/csv")
ResponseEntity<StreamingResponseBody> export() {
    StreamingResponseBody body = output -> {
        output.write("id,name\n".getBytes(StandardCharsets.UTF_8));
        output.write("1,Ada\n".getBytes(StandardCharsets.UTF_8));
        output.flush();
    };

    return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(
                    "text/csv;charset=UTF-8"))
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"export.csv\"")
            .body(body);
}
```

Đây là **method fragment** trong controller; cần imports `StandardCharsets`, `ResponseEntity`, `HttpHeaders`, `MediaType`. Production cần escape CSV đúng và giới hạn output.

### 6.1. Tránh giữ toàn bộ file vào RAM

Anti-pattern cho file lớn:

```java
byte[] all = Files.readAllBytes(path);
return ResponseEntity.ok(all);
```

Khi nhiều clients tải file lớn, bộ nhớ có thể tăng theo tổng file sizes. Dùng `StreamingResponseBody` với buffer:

```java
StreamingResponseBody body = output -> {
    try (InputStream source = Files.newInputStream(path)) {
        source.transferTo(output);
        output.flush();
    }
};
```

Đây là **fragment**, cần kiểm tra `path` do server sở hữu và quyền truy cập trước đó. `InputStream#transferTo` stream qua buffer nội bộ thay vì materialize toàn bộ file, nhưng network write vẫn blocking, tốc độ download phụ thuộc downstream.

Với file rất lớn có sẵn trên disk, Spring MVC `Resource` / `ResourceRegion` có thể thích hợp hơn khi cần HTTP Range, conditional GET, Content-Length hoặc sendfile. `StreamingResponseBody` **không tự cung cấp** resumable download/`206 Partial Content`.

### 6.2. CSV/NDJSON phải tự kiểm soát framing

- Với CSV, escape dấu phẩy, quote và newline đúng. Khi export từ input người dùng vào spreadsheet, cân nhắc **CSV formula injection** (giá trị bắt đầu bằng `=`, `+`, `-`, `@` có thể được phần mềm bảng tính diễn giải như công thức).
- Với NDJSON, mỗi line là **một JSON value hoàn chỉnh**, có newline delimiter; tự nối field strings có thể tạo JSON invalid.
- Với binary, không dùng `Writer` trộn charset không kiểm soát vào `OutputStream`.
- Ghi theo batches hợp lý, không flush từng byte gây overhead lớn.
- Không set Content-Length nếu không biết chính xác bytes được gửi và không thể đảm bảo độ dài.
- Không truy cập request-scoped bean hoặc `HttpServletRequest` từ callback async nếu không có context propagation rõ ràng; truyền immutable metadata, path/ID sau khi đã validate.

## 7. Lifecycle, timeout, errors và connection cleanup

### 7.1. Các trạng thái hữu ích cho emitter

```text
CREATED
   |
   v
ACTIVE --send()--> ACTIVE --send()--> ACTIVE
   |                  |                 |
   | complete()       | timeout         | IOException/disconnect
   v                  v                 v
COMPLETED           TIMED_OUT          ERROR
   \                  |                 /
    \_________________|________________/
                       |
                onCompletion()
                giải phóng registry
```

Đây là **sơ đồ khái niệm**, không phải enum trạng thái công khai của `ResponseBodyEmitter`. Lifecycle có thể xảy ra gần nhau trên các threads khác nhau; dùng `AtomicBoolean` hoặc synchronization thích hợp khi cần bảo vệ thao tác cleanup khỏi race.

### 7.2. onTimeout khác với completeWithError

`emitter.onTimeout(...)` chỉ đăng ký callback; nó không tự hủy mọi producer trong một external message broker. Application cần cancel task/unsubscribe, giải phóng resources theo policy.

`onCompletion` chạy khi async request hoàn tất vì success/error/timeout; thường là nơi tốt nhất để remove emitter khỏi registry. Với disconnect, không chờ callback ở một thời điểm cụ thể nếu không có write/heartbeat phát hiện lỗi.

### 7.3. Sai lầm với IOException

Nếu `send` ném `IOException` vì container write failure, ứng dụng **không được tự gọi `completeWithError` hoặc `complete` cho chính sự kiện container này**. Container sẽ cung cấp error notification, Spring xử lý async completion. Lời khuyên này đến từ Spring MVC async streaming reference.

Nếu lỗi business xảy ra trước/sau khi gửi một số events, `completeWithError(ex)` có thể khiến Spring xử lý exception resolver khi async dispatch. Nhưng nếu **headers/response đã committed**, status/body không còn được thay an toàn; server nên phát một event lỗi thuộc protocol trước khi complete (nếu connection còn usable), hoặc để client xử lý disconnect/retry.

### 7.4. Timeout ba tầng

1. **Emitter timeout**: `new SseEmitter(30_000L)` hoặc `new ResponseBodyEmitter(30_000L)`.
2. **MVC default async timeout**: `AsyncSupportConfigurer#setDefaultTimeout`; áp dụng khi không có override.
3. **Servlet container/proxy/load balancer timeout**: kết nối có thể bị đóng độc lập với hai giá trị trên.

Đừng đồng nhất “timeout emitter 30 s” với “mọi proxy chắc chắn giữ connection ít nhất 30 s”. Reverse proxy có idle/read timeout riêng, browser có chính sách reconnect riêng.

## 8. Cấu hình TaskExecutor và Servlet async

### 8.1. Spring Boot 3.5 có executor tự cấu hình — nhưng vẫn cần sizing

Spring Boot 3.5 có cơ chế auto-configure `AsyncTaskExecutor` khi điều kiện phù hợp. Trong phiên bản này, bean auto-configured dùng tên **`applicationTaskExecutor`**; Spring MVC cần bean có tên đó và kiểu `AsyncTaskExecutor` khi dùng Boot auto-configuration.

Tài liệu Spring Framework khuyến nghị cấu hình executor phù hợp tải thay vì phụ thuộc vào fallback mặc định khi streaming cần blocking writes. Boot thường tạo `ThreadPoolTaskExecutor` trừ khi Java 21+ virtual threads được bật. Sự có mặt của một custom `Executor` bean có thể làm Boot auto-configuration back off, nên cần kiểm tra executor thực tế.

Một cấu hình manual rõ ràng trong demo phần 9:

```java
@Configuration
class StreamingAsyncConfig implements WebMvcConfigurer {

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("mvc-stream-");
        pool.initialize();
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(applicationTaskExecutor());
        configurer.setDefaultTimeout(30_000L);
    }
}
```

Đây là **class fragment**, cần imports Spring Config/AsyncTaskExecutor; xem full file runnable phần 9.

- Pool có tối đa 8 workers và queue 100 requests/tasks trong ví dụ. Đây là **con số để học**, không phải sizing production cho mọi hệ thống.
- Nếu task bị block do slow clients, pool có thể cạn workers; khi queue đầy cần fail-fast/rejection/backpressure policy.
- `StreamingResponseBody` và producer tasks trong demo dùng chung pool để đơn giản; trong production, nên **tách các executors** nếu load profile khác nhau, để streaming writes không làm nghẽn các producers.
- Có thể dùng Boot properties `spring.task.execution.pool.*` nếu để Boot auto-configure executor; tránh vừa tạo custom executor vừa kỳ vọng mọi Boot properties tự thay đổi nó.
- Với Java 21+ virtual threads, việc sử dụng threads nhẹ hơn không biến network I/O thành backpressure tự động. Cần giới hạn clients và lượng dữ liệu in-flight.

### 8.2. Servlet/Filter registrations phải hỗ trợ async

Nếu dùng Servlet 3+ và Java configuration đúng của Spring Boot, `DispatcherServlet` thường được đăng ký hỗ trợ async. Nhưng một custom filter thiếu `asyncSupported=true` có thể khiến request không thể chuyển sang async.

Với `FilterRegistrationBean` tùy chỉnh:

```java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
        DispatcherType.REQUEST, DispatcherType.ASYNC);
```

Đây là **fragment**, cần đúng filter registration và imports `jakarta.servlet.DispatcherType`. `ASYNC` dispatcher mapping dùng khi cần tham gia redispatch; không tự bảo đảm filter cũng chạy lại logic nếu base class `OncePerRequestFilter` mặc định skip async/error.

Nếu khai báo `web.xml`/WAR ngoài, cần cấu hình `<async-supported>true</async-supported>` cho servlet và relevant filters. Test trong embedded container hoặc target deployment thay vì chỉ unit test controller.

## 9. Ứng dụng Spring Boot 3.5 + Java 17 có thể chạy

Ba endpoints:

1. `GET /demo/objects` — `ResponseBodyEmitter` xuất **hai NDJSON records** dùng Jackson converter và dấu xuống dòng.
2. `GET /demo/sse` — `SseEmitter` xuất một event `progress` và một event `finished`, mỗi event có ID.
3. `GET /demo/report.csv` — `StreamingResponseBody` xuất một file CSV không materialize toàn bộ response trước.

Để test hữu hạn và không treo người dùng, mỗi stream cố ý **kết thúc bình thường**. Chúng không mô phỏng endless live feed, shared pub/sub hoặc lưu trạng thái qua nodes. Full source nằm trong một file Java.

### 9.1. Gradle dependencies

Trong project Spring Boot 3.5 có Boot plugin, repositories, dependency management và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **mảnh cấu hình `build.gradle`**, không phải Gradle file độc lập. Starter web có Servlet MVC/Jackson dùng cho JSON object conversions. Không cần dependency WebFlux để chạy ba kiểu streaming này.

### 9.2. Toàn bộ Java source

Tạo file **`src/main/java/demo/streaming/StreamingDemoApplication.java`**:

```java
package demo.streaming;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class StreamingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamingDemoApplication.class, args);
    }
}

@Configuration
class StreamingAsyncConfig implements WebMvcConfigurer {

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("mvc-stream-");
        pool.initialize();
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(applicationTaskExecutor());
        configurer.setDefaultTimeout(30_000L);
    }
}

record Progress(int seq, String state) {}

@RestController
class StreamingController {

    private static final MediaType NDJSON =
            MediaType.parseMediaType("application/x-ndjson");

    private final AsyncTaskExecutor executor;

    StreamingController(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @GetMapping(path = "/demo/objects",
            produces = "application/x-ndjson")
    ResponseEntity<ResponseBodyEmitter> objects() {
        ResponseBodyEmitter emitter = new ResponseBodyEmitter(15_000L);
        AtomicBoolean stopped = registerLifecycle(emitter);

        executor.execute(() -> {
            try {
                if (stopped.get()) {
                    return;
                }

                emitter.send(new Progress(1, "queued"),
                        MediaType.APPLICATION_JSON);
                emitter.send("\n", MediaType.TEXT_PLAIN);

                emitter.send(new Progress(2, "done"),
                        MediaType.APPLICATION_JSON);
                emitter.send("\n", MediaType.TEXT_PLAIN);

                if (!stopped.get()) {
                    emitter.complete();
                }
            } catch (IOException disconnected) {
                // Servlet container handles IOException/async error.
                stopped.set(true);
            } catch (RuntimeException failure) {
                if (!stopped.get()) {
                    emitter.completeWithError(failure);
                }
            }
        });

        return ResponseEntity.ok()
                .contentType(NDJSON)
                .cacheControl(CacheControl.noStore())
                .body(emitter);
    }

    @GetMapping(path = "/demo/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> sse() {
        SseEmitter emitter = new SseEmitter(15_000L);
        AtomicBoolean stopped = registerLifecycle(emitter);

        executor.execute(() -> {
            try {
                if (stopped.get()) {
                    return;
                }

                emitter.send(SseEmitter.event()
                        .id("1")
                        .name("progress")
                        .reconnectTime(2_000L)
                        .data("queued"));

                emitter.send(SseEmitter.event()
                        .id("2")
                        .name("finished")
                        .data("done"));

                if (!stopped.get()) {
                    emitter.complete();
                }
            } catch (IOException disconnected) {
                // Do NOT call completeWithError after an I/O failure.
                stopped.set(true);
            } catch (RuntimeException failure) {
                if (!stopped.get()) {
                    emitter.completeWithError(failure);
                }
            }
        });

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noCache())
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }

    @GetMapping(path = "/demo/report.csv",
            produces = "text/csv")
    ResponseEntity<StreamingResponseBody> csv() {

        StreamingResponseBody body = output -> {
            // Deterministic demo, no user-provided spreadsheet cells.
            output.write("id,name\n".getBytes(StandardCharsets.UTF_8));
            output.write("1,Ada\n".getBytes(StandardCharsets.UTF_8));
            output.write("2,Lin\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
        };

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"report.csv\"")
                .cacheControl(CacheControl.noStore())
                .body(body);
    }

    private static AtomicBoolean registerLifecycle(
            ResponseBodyEmitter emitter) {
        AtomicBoolean stopped = new AtomicBoolean(false);
        emitter.onTimeout(() -> stopped.set(true));
        emitter.onError(error -> stopped.set(true));
        emitter.onCompletion(() -> stopped.set(true));
        return stopped;
    }
}
```

**Đây là file Java 17 hợp lệ trong Spring Boot 3.5:** chỉ `StreamingDemoApplication` là public; `StreamingAsyncConfig`, `StreamingController` và record `Progress` cùng package nên được Spring component scan. `ThreadPoolTaskExecutor` là Spring `AsyncTaskExecutor`, được dùng cho cả producer và MVC async trong demo.

Chú thích:

- `objects()` gửi JSON objects và `"\n"` riêng để tạo **NDJSON**. Cần message converters của `spring-boot-starter-web`. Một producer duy nhất đảm bảo thứ tự messages theo `seq`.
- `sse()` định dạng đúng các SSE frames, có `id` và `event`; không phải JSON. Header `X-Accel-Buffering: no` mang tính **cấu hình riêng cho NGINX** nếu reverse proxy tôn trọng, không phải HTTP standard header bắt buộc.
- `csv()` được Spring MVC schedule callback lên async executor; không tự tạo thread. Ví dụ text CSV cố định, không có yêu cầu escape input người dùng.
- Timeout 15 giây được đặt **trên từng emitter**, còn MVC default timeout 30 giây là fallback cho request kiểu async không override.
- `onTimeout`, `onError` và `onCompletion` chỉ đặt flag; trong hệ thống thật cần dừng producer/subscription, huỷ scheduled tasks và xóa emitter khỏi registry.
- Nếu executor quá tải, lệnh `execute` có thể ném rejection exception ngay trong handler; production cần admission control, fallback status/metrics, không retry vô hạn.
- Việc gửi trước khi Spring hoàn tất khởi tạo emitter có thể được framework queue để flush sau khi handler được gắn; không dựa vào thứ tự thread để suy ra bytes chắc chắn được gửi trước lúc controller trả.
- Không tự thiết kế endless `while(true)` trong mỗi HTTP request, nhất là với thread pool cố định.
- Response media types rất quan trọng: client cần biết `application/x-ndjson`, `text/event-stream` hoặc `text/csv` đúng chức năng.

## 10. Gọi bằng curl và đọc kết quả mong đợi

Chạy application:

```bash
./gradlew bootRun
```

### 10.1. Object streaming/NDJSON

```bash
curl -N -i 'http://localhost:8080/demo/objects'
```

`-N` (no-buffer) giúp curl không tự buffer output; không ép mọi proxy flush ngay.

Body dự kiến (hai dòng, mỗi dòng là một JSON object):

```json
{"seq":1,"state":"queued"}
{"seq":2,"state":"done"}
```

Thứ tự keys bên trong JSON object phụ thuộc Jackson; ví dụ này dùng record với hai fields theo thứ tự khai báo. Client NDJSON nên parse **từng dòng** thay vì parse toàn body như một JSON array.

### 10.2. SSE

```bash
curl -N -i \
  -H 'Accept: text/event-stream' \
  'http://localhost:8080/demo/sse'
```

Phần body có dạng:

```text
id:1
event:progress
retry:2000
data:queued

id:2
event:finished
data:done

```

Định dạng có thể có dấu cách sau dấu hai chấm hoặc thứ tự field hơi khác theo serializer; **contract quan trọng** là các field và event delimiter. `curl` chỉ hiển thị bytes, không tự parse SSE như browser `EventSource`.

### 10.3. Download CSV

```bash
curl -i 'http://localhost:8080/demo/report.csv'
```

Status dự kiến `200 OK`; headers gồm `Content-Type: text/csv;charset=UTF-8` và `Content-Disposition: attachment; filename="report.csv"`. Body:

```csv
id,name
1,Ada
2,Lin
```

Tải file ra disk bằng `curl -o report.csv 'http://localhost:8080/demo/report.csv'`; không dùng `-i` khi lưu CSV thực để tránh đưa HTTP headers vào file.

## 11. Kiểm thử MockMvc cho async và streaming hữu hạn

`MockMvc` không chạy một HTTP socket real như Tomcat, nên nó phù hợp để kiểm tra **MVC contract, media type và body sau khi producer hoàn tất**. Nó không đo được flush latency trên đường truyền, proxy buffering, TCP disconnect hay behavior của browser EventSource thực.

Tạo **`src/test/java/demo/streaming/StreamingDemoApplicationTests.java`**:

```java
package demo.streaming;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StreamingDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void emitsTwoNdjsonRecordsAndCompletes() throws Exception {
        MvcResult result = mvc.perform(get("/demo/objects"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L); // Chờ signal hoàn tất, không sleep.

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        "application/x-ndjson"))
                .andExpect(content().string(
                        containsString("\"state\":\"queued\"")))
                .andExpect(content().string(
                        containsString("\"state\":\"done\"")));
    }

    @Test
    void writesSseFieldsAndCompletes() throws Exception {
        MvcResult result = mvc.perform(get("/demo/sse")
                        .accept("text/event-stream"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        "text/event-stream"))
                .andExpect(content().string(
                        containsString("event:progress")))
                .andExpect(content().string(
                        containsString("data:queued")))
                .andExpect(content().string(
                        containsString("event:finished")));
    }

    @Test
    void writesCsvBytesInAsyncCallback() throws Exception {
        MvcResult result = mvc.perform(get("/demo/report.csv"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Content-Disposition",
                        "attachment; filename=\"report.csv\""))
                .andExpect(content().string(
                        "id,name\n1,Ada\n2,Lin\n"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Ba tests được **thiết kế để pass** với project Spring Boot 3.5 và full source trên; đây là **kỳ vọng đã rà soát**, **không phải kết quả Gradle đã chạy**. Test dùng `asyncDispatch` sau khi async result signal có mặt, đúng cách test MVC async được Spring document.

**Giới hạn MockMvc:** nếu một test cần chứng minh *streaming một phần trước khi hoàn tất*, đừng chỉ assert body sau `asyncDispatch`. Hãy khởi chạy `@SpringBootTest(webEnvironment=RANDOM_PORT)` và dùng client đọc response **incrementally**, ví dụ Java `HttpClient` với `BodyHandlers.ofInputStream()` hoặc HTTP/SSE client phù hợp.

## 12. Test trực tiếp trên embedded server và tránh false positive

Với Servlet streaming, một test chỉ đọc toàn bộ body sau khi kết thúc **không chứng minh** dữ liệu từng được flush sớm. Để đo thực sự:

1. Khởi chạy Boot trên port thật (RANDOM_PORT).
2. Tạo producer gửi các events cách nhau một khoảng có kiểm soát.
3. HTTP client lấy `InputStream`/SSE frames khi response còn mở.
4. Đo thời điểm nhận frame đầu tiên, không chờ toàn bộ stream.
5. Kiểm tra status/Content-Type; đóng client giữa stream.
6. Xác minh producer/registry dọn kết nối và không còn tăng memory.
7. Lặp qua reverse proxy/ingress/CDN staging.
8. Test network chậm, timeout và retry behavior.

Mẫu client Java 17 để đọc response (fragment trong test HTTP thực):

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(
                "http://localhost:" + port + "/demo/sse"))
        .header("Accept", "text/event-stream")
        .GET()
        .build();

HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                response.body(), StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Đây là **fragment**, cần imports `java.net.http.*`, `java.net.URI`, `java.io.*`, `StandardCharsets` và biến `port` do `@LocalServerPort` test cung cấp. Ví dụ stream hữu hạn, nên vòng lặp sẽ kết thúc; stream production vô hạn cần read deadline/cancellation.

Trong test thật nên dùng timeouts/awaitility hoặc logic có bound, không dùng `Thread.sleep` vô hạn hoặc assert network timing quá chặt gây flaky CI.

## 13. Reverse proxy, browser và HTTP buffering

Một stream đúng ở controller vẫn có thể bị gom ở proxy:

```text
Producer send event 1 -----+
Producer send event 2 -----+--> Servlet output
Producer send event 3 -----+
                                |
                        NGINX / CDN buffer
                                |
                   Client nhận cả 3 lúc cuối
```

Nguyên nhân có thể là:

- Proxy `proxy_buffering`/compression làm response không flush theo events.
- CDN cache/transform, gateway timeout hoặc WAF policy không thích hợp cho long-lived connections.
- Response bị nén/buffer thành một khối trước khi gửi.
- Browser/devtools/curl output buffering.
- TCP segmentation/HTTP/2 framing không tương đương `send()` boundaries.
- Producer thực ra chỉ gửi sau khi hoàn tất công việc.
- Cấu hình executor thiếu worker, tasks bị queued quá lâu.

Các hướng kiểm tra:

- Với SSE, gửi `Content-Type: text/event-stream` và cache policy như `no-cache` thích hợp.
- Kiểm tra NGINX buffering. Header `X-Accel-Buffering: no` chỉ có tác dụng nếu proxy đó tôn trọng.
- Sử dụng `curl -N` hoặc HTTP client incremental.
- Theo dõi timestamps ở producer, Servlet write và client event receiver để xác định nơi bị chậm.
- Không tắt buffering/caching toàn hệ thống vô điều kiện; cấu hình theo streaming routes.
- Xác định proxy idle timeout và heartbeat interval hợp lý.

**Không hứa mỗi `flush()` tương ứng một network packet**. Hãy định nghĩa SLA theo thời điểm event xuất hiện ở client, và test qua đúng topology production.

## 14. Backpressure, slow consumers và giới hạn tài nguyên

### 14.1. `ResponseBodyEmitter`/`SseEmitter` không phải message broker

Nếu producer tạo 10.000 events/s nhưng client chỉ đọc được 100 events/s, ứng dụng có thể:

- Block worker trên socket writes.
- Tích lũy queue trong emitter registry/broadcaster.
- Dùng hết executor threads/heap.
- Timeout/disconnect các clients khác.

Giải pháp production:

- Giới hạn số subscribers trên user/tenant, tổng kết nối và event rate.
- Dùng queues có **capacity** thay vì unbounded lists; áp **drop/coalesce/disconnect policy** rõ ràng.
- Có metrics: active connections, queue depth, dropped events, average write latency, reconnect count.
- Với trạng thái tiến độ thường xuyên, **coalesce** thành bản cập nhật mới nhất thay vì giữ mọi event.
- Với event đòi hỏi durability, dùng DB/event log/message broker; SSE chỉ là lớp chuyển tới client.
- Kiểm tra quyền nhận từng stream và quyền truy cập sau khi reconnect.
- Tránh tạo thread riêng/scheduler mới **cho mỗi client** mà không giới hạn.
- Gỡ emitter khỏi registry ở `onCompletion`, `onTimeout`, `onError`; dừng heartbeat tương ứng.

### 14.2. `StreamingResponseBody` chịu tốc độ đọc của client

Nếu xuất file từ database hoặc object storage, mỗi download có thể giữ một worker trong suốt quá trình stream. Đừng mở `ResultSet`/DB transaction rất lâu chỉ để giữ kết nối HTTP chậm; cân nhắc:

- Tạo file tạm có kiểm soát rồi stream qua object storage/CDN.
- Export job bất đồng bộ: `POST /exports` trả `202 Accepted` và `GET /exports/{id}` trả status.
- Streaming query/cursor với timeout/batch size và transaction boundary đã thiết kế.
- Bounded connection pools/CPU/memory/IO quotas.
- Cơ chế Range/206 nếu người dùng cần resumable file download.

## 15. Bảo mật SSE và streaming

### 15.1. Authentication/authorization

Kết nối SSE có thể tồn tại lâu. Không chỉ kiểm tra lúc subscribe rồi mặc định user luôn có quyền vô hạn:

- Xác thực request ban đầu bằng Spring Security theo kiến trúc.
- Authorization theo resource/tenant cho event stream.
- Nếu quyền bị revoke trong lúc kết nối, cân nhắc disconnect hoặc giới hạn TTL và buộc reconnect/re-auth.
- Không phát events của tenant A tới subscribers của tenant B.
- Không nhét access token vào `?token=...` vì URL query có thể lọt vào browser history, logs, proxy/APM.
- Nếu cross-origin có cookie session, dùng CORS allowlist chính xác, CSRF cho các **state-changing request khác**, và đánh giá chính sách credentials.
- Tránh các response cache công khai cho streams có dữ liệu riêng.

### 15.2. Event data và frontend injection

`EventSource` chuyển `event.data` thành chuỗi. Nếu nội dung do user kiểm soát, không đưa thẳng vào `innerHTML`:

```javascript
source.addEventListener("progress", event => {
  const node = document.getElementById("progress");
  node.textContent = event.data; // Text, không parse HTML.
});
```

Đây là fragment, giả định DOM có element id `progress`. Nếu dùng JSON, parse bằng `JSON.parse` và validate schema/fields cần thiết. SSE framing không biến dữ liệu bên trong thành HTML an toàn.

### 15.3. File download headers

Với `StreamingResponseBody`:

- Đặt `Content-Type` đúng dữ liệu: `text/csv;charset=UTF-8`, `application/pdf`, `application/octet-stream`...
- Dùng `Content-Disposition: attachment` nếu muốn ép download, và encode filename bằng API thích hợp thay vì nối raw client filename vào header.
- `X-Content-Type-Options: nosniff` hữu ích khi file có thể bị browser sniff.
- Với tài liệu riêng, dùng `Cache-Control: private` hoặc `no-store`.
- Authorization phải xảy ra **trước khi mở stream**, không dựa vào file ID khó đoán là đủ.
- Khi export CSV từ dữ liệu không tin cậy, kiểm tra **formula injection** ở phần mềm bảng tính.
- Đừng log download bytes, access tokens hoặc signed URLs.

## 16. Khi nào nên chọn WebSocket hoặc WebFlux thay vì SSE/MVC streaming?

| Nhu cầu | Giải pháp nên cân nhắc |
| --- | --- |
| Browser chỉ nhận cập nhật server → client, event text | **SseEmitter** |
| Server gửi nhiều object fragments/NDJSON theo HTTP response | **ResponseBodyEmitter** |
| Gửi file/CSV/binary trực tiếp với bộ nhớ thấp | **StreamingResponseBody** |
| Một kết quả bất đồng bộ, không cần stream | `DeferredResult`/`Callable` |
| Hai chiều liên tục, client gửi events liên tục | WebSocket / STOMP tùy use case |
| Số kết nối/streams cực lớn cần reactive I/O non-blocking | Spring WebFlux hoặc gateway hỗ trợ reactive |
| Durable events/replay độc lập ứng dụng | Event broker/log + API SSE/WebSocket frontend |
| Batch export kéo dài hàng phút/giờ | Background job + object storage + download |
| Client dùng SSE nhưng cần gửi lệnh | EventSource GET + HTTP POST/PUT riêng |

SSE phù hợp nhiều dashboard/notification use cases vì đơn giản và browser hỗ trợ reconnect. Nhưng HTTP GET streaming không đáp ứng mọi giao tiếp hai chiều và không làm giảm nhu cầu broker, event retention, auth hoặc rate limits.

## 17. Lỗi thường gặp và troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Controller trả emitter nhưng browser mãi không thấy gì | Producer chưa `send`, proxy buffer, media type sai | Debug producer, `curl -N`, response headers |
| Request timeout sau vài giây | Emitter/MVC/Servlet/proxy timeout khác nhau | Log callbacks và kiểm tra proxy idle timeout |
| SSE browser reconnect liên tục sau 2 events | Stream hữu hạn hoàn tất nhưng EventSource tự retry | Client `source.close()` khi event finished |
| SSE có events nhưng `onmessage` không gọi | Có `event: progress` nên phải dùng `addEventListener("progress")` | Inspect wire frame |
| Client nhận JSON parse error | Ghép `{}{}` không newline/array delimiters | Dùng NDJSON framing rõ ràng |
| `send` ném IOException khi đóng tab | Client disconnect trong khi server write | Để container xử lý async error, cleanup registry |
| App gọi `completeWithError` sau IOException | Sai lifecycle theo Spring docs | Không gọi complete/error trong nhánh write IOException |
| Error sau khi gửi bytes vẫn trả HTTP 200 | Response committed, status không thể đổi | Thiết kế protocol error event/abort handling |
| Download chiếm nhiều RAM | `readAllBytes`/materialize output | Stream buffer qua `OutputStream` |
| CSV bị hỏng encoding | Charset mismatch hoặc writer không rõ charset | Sử dụng UTF-8 nhất quán |
| CSV mở Excel chạy công thức lạ | Formula injection từ user fields | Escape/sanitize export theo policy |
| Thread pool cạn khi nhiều SSE clients | Blocking writes/producer loops, unbounded connections | Executor metrics, connection caps, queue policy |
| Registry giữ emitter cũ mãi | Không cleanup onCompletion/error/timeout | Remove emitter, cancel heartbeat |
| MVC async không khởi động | Servlet/filter `asyncSupported=false` | Kiểm tra registrations |
| URL qua gateway trả kết quả cuối mới thấy | Proxy buffering/compression hoặc không flush | HTTP incremental test sau proxy |
| `Last-Event-ID` có nhưng bị mất events | Không có server-side replay store | Shared event log và resume policy |
| CORS lỗi trên cross-origin EventSource | Origins/credentials không khớp | Cấu hình CORS cho SSE endpoint |
| Authorization chỉ kiểm tra khi kết nối | Quyền người dùng thay đổi giữa stream | TTL/re-auth/disconnect policy |
| Test MockMvc fail vì async chưa hoàn tất | Test chưa đợi async result/dispatch | `getAsyncResult(...)` rồi `asyncDispatch(...)` |
| Stream trên WebFlux không dùng class MVC | Lẫn Servlet với reactive stack | Dùng API `Flux`/ServerSentEvent của WebFlux |

## 18. Các khác biệt theo version Spring Boot/Spring Framework

| Phiên bản | Lưu ý |
| --- | --- |
| Spring Framework 5.x + Boot 2.x | Các class `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody` đã tồn tại; Servlet API phần lớn dùng `javax.servlet.*` |
| Spring Framework 6.x + Boot 3.x | Java 17+, Servlet API `jakarta.servlet.*`; mã demo dùng thế hệ này |
| Spring Framework 7.x + Boot 4.x | MVC streaming concepts tiếp tục có, nhưng starter/modules/test APIs và executor auto-configuration có thể thay đổi; đọc docs/BOM đúng version |

Riêng **Spring Boot 3.5** thay đổi tên auto-configured TaskExecutor: bean tên `applicationTaskExecutor`; không còn mặc định alias `taskExecutor` như các version trước. Các ví dụ custom executor cần kiểm tra tên bean và điều kiện MVC yêu cầu kiểu `AsyncTaskExecutor`.

Spring Framework 6.2 bổ sung khả năng đăng ký nhiều callbacks trong emitter lifecycle. Nhưng sự hiện diện của callbacks không thay thế việc cleanup producer tasks nếu streams bị timeout hoặc disconnect.

Đừng trộn Java source WebFlux (`org.springframework.web.reactive.*`) với Servlet MVC (`org.springframework.web.servlet.mvc.method.annotation.*`). API tên gần nhau có thể có các hợp đồng thực thi khác nhau.

## 19. Checklist triển khai production

- [ ] Chọn đúng representation: NDJSON, SSE hay raw bytes.
- [ ] `Content-Type` và client parser tương thích với wire format.
- [ ] Producer không chạy vòng lặp vô hạn trên request/worker không được quản lý.
- [ ] Executor có giới hạn/metrics/rejection strategy; streaming writes không làm chết các workloads khác.
- [ ] Servlet và filters có `asyncSupported=true`; mapping ASYNC khi cần.
- [ ] Timeout emitter/MVC/container/proxy nhất quán với heartbeat/reconnect.
- [ ] `onCompletion`/`onError`/`onTimeout` cleanup subscribers, queues, scheduled tasks.
- [ ] Sau IOException khi gửi emitter không tự gọi `complete`/`completeWithError`.
- [ ] Khi response committed, error handling theo streaming protocol, không giả định trả status mới.
- [ ] SSE events có `id/event/data` hợp đồng rõ, Last-Event-ID/replay nếu business cần.
- [ ] EventSource client đóng stream chủ đích; dùng CORS/credentials đúng.
- [ ] Private streams authz theo user/tenant và có revocation strategy.
- [ ] Rate limit/connection cap/backpressure/slow-client policy.
- [ ] Downloads có Content-Disposition/MIME/cache/authorization thích hợp.
- [ ] Không log raw token, query secret hoặc payload nhạy cảm trong stream.
- [ ] Test MockMvc async semantics và test incremental streaming qua container thật.
- [ ] Test trên proxy/CDN cuối cùng, không chỉ localhost.
- [ ] Scale multi-node dùng shared event source khi cần replay/ordering.
- [ ] Theo dõi active streams, disconnections, errors, timeout rate, queue depth và memory.

## 20. Bài tập thực hành

1. Thay `ResponseBodyEmitter` bằng `DeferredResult<List<Progress>>`. Khác biệt về lúc client nhận từng record và memory là gì?
2. Bỏ các lệnh gửi `"\n"` trong endpoint NDJSON. Body nhận được có còn là NDJSON hợp lệ không?
3. Thay `SseEmitter.event().name("progress")` bằng không có `name`. Browser dùng `onmessage` hay `addEventListener("progress")`?
4. Giải thích khác nhau giữa `id:42` và `Last-Event-ID:42`. Spring SseEmitter có tự lưu replay events không?
5. Viết client EventSource đóng stream khi nhận event `finished`, rồi thử mở lại stream.
6. Nếu container proxy idle timeout 60 giây nhưng server chỉ gửi event mỗi 5 phút, cần heartbeat thế nào?
7. Khi `emitter.send` ném IOException, có nên gọi `completeWithError`? Nêu thứ tự xử lý lỗi do container quản lý.
8. Tại sao một server có 500 SSE connections có thể tốn threads nếu producers hoặc writes block? Đề xuất giới hạn và metrics.
9. Dùng `StreamingResponseBody` thay `Files.readAllBytes` để trả một file 2 GB. Cần xử lý Content-Length/Range/download cancellation thế nào?
10. Chỉnh CSV export để chứa giá trị bắt đầu bằng `=` từ người dùng. Rủi ro gì khi mở bằng spreadsheet? Cần escape theo policy nào?
11. Thêm test MockMvc cho cả ba endpoints dùng `asyncDispatch`; tại sao chỉ assert status trước async completion chưa đủ?
12. Tạo test HTTP thật với `HttpClient.BodyHandlers.ofInputStream` đo thời điểm nhận SSE frame đầu, so với thời điểm producer complete.
13. Khi bật Spring Security cookie authentication, cross-origin EventSource cần CORS/credentials như thế nào?
14. Trong rolling deployment, client reconnect với Last-Event-ID đến node khác; cần lưu state ở đâu?
15. So sánh dùng SSE, WebSocket, WebFlux khi dashboard cần cập nhật 1 lần/giây và khi game cần 2 chiều 60 lần/giây.
16. Nếu `@Async` method muốn lấy `RequestContextHolder` hoặc MDC, vì sao không tự có? Nêu cách truyền immutable context an toàn.
17. Khi ứng dụng trả ResponseEntity<SseEmitter>, header nào nên cấu hình trước first send và vì sao response committed làm thay đổi header thất bại?
18. Viết test fail-fast khi executor hết queue capacity, và chọn HTTP status/retry policy phù hợp cho clients.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Asynchronous Requests and HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Servlet async lifecycle, ResponseBodyEmitter, SseEmitter, StreamingResponseBody, disconnects và cấu hình.
- [Spring Framework 6.2 — ResponseBodyEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html): send, timeout, complete, error, lifecycle callbacks.
- [Spring Framework 6.2 — SseEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html): SSE event builder, id/event/data/retry.
- [Spring Framework 6.2 — StreamingResponseBody Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html): writeTo(OutputStream) và async execution.
- [Spring Framework 6.2 — AsyncSupportConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html): MVC executor và default timeout.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): applicationTaskExecutor, ThreadPoolTaskExecutor, Boot defaults.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): asyncResult, asyncDispatch.
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, SSE format, retry, Last-Event-ID và comments.
- [Spring MVC — Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): các kiểu async return value.
