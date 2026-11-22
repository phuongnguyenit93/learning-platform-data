# StreamingResponseBody, ResponseBodyEmitter và SseEmitter trong Spring MVC

## Mục tiêu học tập

Bài thuộc nhóm **Đồng thời Servlet** của module **Spring Boot - web-runtime**. Sau bài này, bạn có thể:

1. Hiểu vì sao Spring MVC dùng **Servlet asynchronous request processing** để trả nhiều phần dữ liệu HTTP theo thời gian thay vì chờ toàn bộ nội dung xong mới phản hồi.
2. Phân biệt **StreamingResponseBody** (ghi byte trực tiếp), **ResponseBodyEmitter** (phát từng đối tượng qua HttpMessageConverter) và **SseEmitter** (phát sự kiện chuẩn Server-Sent Events).
3. Mô tả vòng đời request: Servlet thread ban đầu, async context, background producer, blocking response write, completion, timeout và error dispatch.
4. Phân biệt Servlet async với **I/O không chặn end-to-end** của Spring WebFlux; hiểu vì sao vẫn cần bounded TaskExecutor trong Spring MVC.
5. Thiết kế response đúng **Content-Type**, cấu trúc dữ liệu, encoding và cách flush; nhận diện lỗi nối các JSON object thành một body không hợp lệ.
6. Triển khai ứng dụng **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+** có đủ ba endpoint streaming, thread pool cấu hình rõ ràng và lifecycle callbacks.
7. Thử bằng **curl -N**, browser EventSource và integration test HTTP thật; phân biệt kiểm tra content với kiểm tra thời điểm chunk được nhận.
8. Thiết lập timeout, cleanup khi client disconnect, heartbeat và cơ chế SSE reconnect phù hợp.
9. Phân tích rủi ro memory, thread/connection exhaustion, slow consumer, proxy buffering, caching, CORS, authentication và thông tin nhạy cảm.
10. Chọn API phù hợp với báo cáo lớn, dữ liệu incremental, live notifications, streaming JSON/NDJSON và cập nhật hai chiều.

**Phiên bản:** Spring Boot 3.3.x chạy trên Java 17+, Spring Framework 6.1.x, Spring MVC và Servlet container như Tomcat. API ba lớp này thuộc **org.springframework.web.servlet.mvc.method.annotation**, không phải lớp mặc định của Spring WebFlux.

## 1. Tại sao cần streaming trong Servlet web runtime?

Thông thường controller tạo đầy đủ một response rồi Spring ghi nó:

~~~java
@GetMapping("/api/report")
List<ReportRow> report() {
    return service.findAll();
}
~~~

Đây là snippet mô tả ý tưởng, chưa phải file chạy độc lập. Với hàng trăm nghìn dòng dữ liệu, cách này có thể buộc ứng dụng tạo một List lớn, serialize thành JSON và làm client phải chờ lâu trước khi thấy nội dung hữu ích.

Một số nhu cầu thích hợp với streaming:

- Xuất **CSV/log/báo cáo lớn** dần thành các byte mà không giữ toàn bộ file trong heap.
- Phát **nhiều thông điệp hoặc đối tượng** theo tiến độ mà mỗi thông điệp có thể được serialize độc lập.
- Gửi **thông báo một chiều từ server tới browser** như trạng thái job, cảm biến, tiến độ tác vụ, thay đổi dữ liệu.
- Trả output từ một downstream producer được đọc theo từng khối.
- Giữ kết nối HTTP mở trong một khoảng thời gian để truyền các sự kiện mới.

Với HTTP streaming, client có thể nhận response headers trước và body được gửi trong nhiều đợt, nhưng **thời điểm client ứng dụng thấy mỗi đợt không được bảo đảm tuyệt đối**: Servlet output buffering, TCP, compression, gateway, CDN, browser hoặc HTTP client có thể gom dữ liệu.

### Không nhầm streaming với đa luồng tự động

Trả StreamingResponseBody hoặc SseEmitter **không tự động làm một truy vấn database chặn trở thành non-blocking**. Nó cho phép xử lý response theo cơ chế bất đồng bộ Servlet; phần I/O blocking và logic producer vẫn cần tài nguyên thích hợp.

## 2. Servlet async request processing hoạt động thế nào?

Khi controller Spring MVC trả loại return value hỗ trợ async, Spring tích hợp với Servlet asynchronous processing:

~~~text
Client mở HTTP connection
        |
        v
Tomcat worker thread
        |
        v
Servlet filters -> DispatcherServlet -> Controller
        |
        +--> Controller trả StreamingResponseBody / emitter
        |
        v
Servlet request đi vào asynchronous mode
        |
        +--> Thread xử lý request ban đầu được nhả
        |
        +--> HTTP response vẫn mở
                   |
                   v
            Background producer /
            AsyncTaskExecutor
                   |
                   v
            Ghi dữ liệu từng phần
                   |
                   +--> write/flush / emitter.send
                   +--> complete / timeout / error
                   |
                   v
             Async completion
             và/hoặc dispatch
                   |
                   v
           HTTP response hoàn tất
~~~

Framework dùng Servlet async support, về bản chất có cơ chế tương đương request.startAsync() và AsyncContext của Servlet API. Ứng dụng bình thường **không cần** tự gọi startAsync() khi đã trả đúng MVC return type.

Những điều cần ghi nhớ:

1. **Initial request thread được nhả** sau khi chuyển xử lý vào async mode.
2. **HTTP connection vẫn tồn tại** trong thời gian stream diễn ra.
3. Một hoặc nhiều producer tasks phải được quản lý qua executor/scheduler phù hợp.
4. **Các thao tác ghi ra Servlet response có thể chặn thread** khi client đọc chậm; việc dùng Servlet async không tự biến mọi write thành non-blocking.
5. Khi complete/timeout/error, container và Spring phối hợp kết thúc request; lỗi có thể kích hoạt final async dispatch và exception resolvers.

### Vì sao đây là chủ đề “Đồng thời Servlet”?

Ứng dụng nhận nhiều request đồng thời. Với một request stream lâu dài, cấu trúc thread pool, async timeout và số connection đang mở ảnh hưởng trực tiếp throughput và ổn định hệ thống.

Một sai lầm dễ gặp: tạo một Thread mới cho mỗi request SSE vô thời hạn. Nếu có hàng nghìn client, số thread hoặc task đang chờ có thể tăng không kiểm soát. Cần thiết kế capacity, backpressure và connection lifetime từ đầu.

## 3. So sánh ba API trong một bảng

| Tiêu chí | StreamingResponseBody | ResponseBodyEmitter | SseEmitter |
|---|---|---|---|
| Mục đích chính | Ghi raw bytes trực tiếp | Phát nhiều object/part theo thời gian | Phát SSE events chuẩn |
| Interface/class | Functional interface | Class | Class extends ResponseBodyEmitter |
| Kiểu body | OutputStream | send(Object), send(Object, MediaType) | send(event builder) hoặc send(Object) |
| Chuyển đổi object | Bạn tự ghi bytes | Qua HttpMessageConverter | Dùng converter cho event data |
| Content-Type | Ví dụ text/plain, application/octet-stream, text/csv | Tùy contract: text/plain, custom framed format | text/event-stream |
| Đơn vị phát | Bất kỳ khối byte nào | Một item được serialize | Một SSE event/frame |
| Ai gọi ghi? | Spring gọi writeTo(...) trên executor | Producer do ứng dụng cung cấp gọi send(...) | Producer gọi send(...) |
| Hoàn tất | Hàm writeTo kết thúc / lỗi | complete(), completeWithError(...) | complete(), completeWithError(...) |
| Phù hợp download | Rất phù hợp | Có thể nhưng không phải lựa chọn đầu | Không phù hợp |
| Phù hợp browser EventSource | Không trực tiếp | Không có SSE framing tự động | Rất phù hợp |
| Mức kiểm soát bytes | Cao | Theo converter | Theo SSE serializer |
| Có tự mở thread producer không? | Framework thực thi writeTo qua async executor | Không | Không |
| Blocking I/O? | Có thể | Có thể | Có thể |

**Kết luận ngắn:**
- Cần ghi byte từ file/report: **StreamingResponseBody**.
- Cần phát các giá trị nhiều đợt nhưng không phải SSE: **ResponseBodyEmitter**.
- Cần thông báo một chiều cho browser theo chuẩn EventSource: **SseEmitter**.

## 4. StreamingResponseBody: ghi trực tiếp vào OutputStream

Spring MVC định nghĩa:

~~~java
org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody
~~~

Đây là một functional interface, có method:

~~~java
void writeTo(OutputStream outputStream) throws IOException;
~~~

Bạn nhận OutputStream của HTTP response và tự ghi bytes. Ví dụ:

~~~java
@GetMapping(
    path = "/api/export",
    produces = MediaType.TEXT_PLAIN_VALUE
)
StreamingResponseBody export() {
    return output -> {
        output.write("row-1\n".getBytes(StandardCharsets.UTF_8));
        output.flush();
        output.write("row-2\n".getBytes(StandardCharsets.UTF_8));
        output.flush();
    };
}
~~~

Đây là **method minh họa đặt trong Spring MVC controller**, cần imports và app tương ứng.

### Những gì xảy ra khi controller trả về

1. Controller chỉ tạo callback StreamingResponseBody và return.
2. Spring bắt đầu async handling.
3. Framework chạy callback writeTo ở async executor thích hợp.
4. Callback ghi vào OutputStream; flush có thể yêu cầu đẩy buffer xuống các tầng thấp.
5. Khi callback kết thúc bình thường, Spring hoàn tất response.
6. Khi callback ném exception, framework/container xử lý lỗi theo vòng đời async.

Với loại này, bạn **không phải** gọi complete(). Đừng tự close OutputStream do container quản lý; để framework chịu trách nhiệm tài nguyên response.

### StreamingResponseBody dùng tốt cho dữ liệu nào?

- CSV có thể viết từng record.
- File đã được đọc qua InputStream và copy qua OutputStream theo từng chunk.
- Dữ liệu text log vừa được tạo.
- File nén hoặc binary protocol được tạo dần.
- Output của một bộ sinh báo cáo xử lý từng batch.

Với file trên disk có sẵn, Spring còn có Resource, resource handler và hỗ trợ HTTP Range tùy cơ chế; không nên dùng StreamingResponseBody cho mọi file khi Resource đáp ứng tốt hơn.

## 5. StreamingResponseBody và file lớn: tránh giữ toàn bộ dữ liệu

Phản ví dụ:

~~~java
@GetMapping("/download")
byte[] all() {
    return Files.readAllBytes(Path.of("large-report.bin"));
}
~~~

Đây là snippet minh họa, không có xử lý lỗi và không thích hợp cho file rất lớn vì readAllBytes giữ toàn bộ file trong heap.

Thay vào đó, stream theo buffer:

~~~java
@GetMapping(
    path = "/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
ResponseEntity<StreamingResponseBody> download() {
    Path path = Path.of("/var/app/reports/report.bin");
    StreamingResponseBody body = output -> {
        try (InputStream input = Files.newInputStream(path)) {
            input.transferTo(output);
            output.flush();
        }
    };

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(body);
}
~~~

Đây là **snippet controller** cần imports, file phải tồn tại và có quyền đọc. Java InputStream.transferTo dùng copy có buffer nội bộ, không yêu cầu giữ toàn bộ file trong một byte[].

Cần thiết kế thêm:
- Xác thực/phân quyền download.
- Đường dẫn file do ứng dụng kiểm soát, không nối trực tiếp filename chưa kiểm tra từ client.
- Kiểm tra file existence và xử lý lỗi **trước khi response commit** nếu có thể.
- Content-Disposition, MIME type, Content-Length khi biết và phù hợp.
- Timeout và chính sách chống client đọc quá chậm.
- Không ghi response sau khi client đã đóng kết nối.

Khi cần HTTP Range, caching hoặc conditional GET, Resource/ResourceRegion/resource handlers có thể phù hợp hơn một callback stream tự viết.

## 6. ResponseBodyEmitter: nhiều đối tượng trên một response

Class:

~~~java
org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter
~~~

Nó cho phép một request trả nhiều phần nội dung được gửi **sau khi controller đã return**.

Ví dụ:

~~~java
@GetMapping(
    path = "/api/progress",
    produces = MediaType.TEXT_PLAIN_VALUE
)
ResponseBodyEmitter progress() {
    ResponseBodyEmitter emitter = new ResponseBodyEmitter(15_000L);

    executor.execute(() -> {
        try {
            emitter.send("start\n", MediaType.TEXT_PLAIN);
            emitter.send("processing\n", MediaType.TEXT_PLAIN);
            emitter.send("done\n", MediaType.TEXT_PLAIN);
            emitter.complete();
        } catch (IOException ex) {
            // Spring/Servlet xử lý thông báo lỗi kết nối I/O.
        } catch (RuntimeException ex) {
            emitter.completeWithError(ex);
        }
    });

    return emitter;
}
~~~

Đây là **snippet** giả sử executor là một executor đã cấu hình. Trong ví dụ đầy đủ ở phần thực hành, executor được khai báo bằng ThreadPoolTaskExecutor.

### Tại sao cần executor?

ResponseBodyEmitter **không tự chạy code sản xuất dữ liệu ở thread khác**. Nó chỉ là kênh gửi nhiều phần. Ứng dụng có thể nhận sự kiện từ service, listener hoặc task chạy nền; trong bản demo, chúng ta dùng một bounded executor.

### send(Object, MediaType) làm gì?

Spring MVC chọn HttpMessageConverter thích hợp để serialize object theo Java type/media type. Ví dụ gửi String dưới text/plain, hoặc một DTO dưới application/json nếu converter có mặt.

**Cẩn thận định dạng:** Nếu bạn gọi emitter.send(Product DTO, application/json) ba lần, HTTP body có thể có các JSON object nối tiếp mà **không có dấu phân cách hợp lệ cho một JSON document**. Không mặc định đó là JSON array.

Ví dụ sai khi client mong một JSON document:

~~~text
{"id":1}{"id":2}{"id":3}
~~~

Đây không phải một JSON array hợp lệ. Muốn nhiều JSON document theo dòng, thiết kế NDJSON đúng format:

~~~text
{"id":1}
{"id":2}
{"id":3}
~~~

Muốn browser EventSource, dùng SseEmitter để có SSE framing đúng. Với generic ResponseBodyEmitter, **quy tắc framing/record separator là trách nhiệm API**; converter chỉ chuyển phần tử thành bytes.

### ResponseEntity<ResponseBodyEmitter>

Có thể trả ResponseBodyEmitter làm body của ResponseEntity để điều khiển status và headers:

~~~java
ResponseBodyEmitter emitter = new ResponseBodyEmitter();
return ResponseEntity.ok()
        .contentType(MediaType.TEXT_PLAIN)
        .body(emitter);
~~~

Đây là snippet. Đặt Content-Type phù hợp nội dung. Nếu response là stream text, tránh khai application/json cho body chứa các dòng văn bản tùy ý.

## 7. SseEmitter: một cách phát HTTP events có chuẩn định dạng

Class:

~~~java
org.springframework.web.servlet.mvc.method.annotation.SseEmitter
~~~

SseEmitter **extends ResponseBodyEmitter**, nhưng thêm cách xây một SSE event đúng định dạng. Server-Sent Events là giao thức HTTP một chiều: **server gửi event tới client**; browser có thể dùng JavaScript EventSource để nhận và tự kết nối lại khi rớt kết nối.

Endpoint thường có:

~~~java
@GetMapping(
    path = "/api/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
SseEmitter events() {
    return new SseEmitter(30_000L);
}
~~~

Đây chỉ là snippet; nếu không có producer gọi send(...) và complete/timeout, client sẽ không có event. Return một emitter **không tự tạo dữ liệu**.

### SSE frame có dạng gì?

Ví dụ body:

~~~text
id:1
event:tick
data:{"id":1,"message":"hello"}

id:2
event:tick
data:{"id":2,"message":"world"}

~~~

Mỗi event kết thúc bằng **dòng trống**. SSE hỗ trợ các dòng như id, event, data, retry và comment; một event có thể có nhiều dòng data. Cách xuất dấu cách sau dấu hai chấm hoặc thứ tự dòng phụ thuộc serializer, nên không assert raw bytes cứng khi không cần.

SseEmitter hỗ trợ builder:

~~~java
emitter.send(
    SseEmitter.event()
        .id("42")
        .name("tick")
        .reconnectTime(3000L)
        .data(new Tick(42, "hello"), MediaType.APPLICATION_JSON)
);
~~~

Đây là snippet với record Tick và emitter đã tồn tại. Jackson converter encode object thành JSON rồi SSE writer tạo frame thích hợp.

### JSON bên trong SSE không làm toàn bộ body thành application/json

Với SSE, **top-level Content-Type là text/event-stream**, dù mỗi trường data chứa JSON.

Client cần parse event framing trước, rồi có thể JSON.parse(event.data) ở JavaScript. Nếu bạn gắn application/json cho toàn bộ SSE stream, JSON parser thông thường sẽ không hiểu các dòng id/event/data.

### SSE khác WebSocket

SSE:
- Chủ yếu **một chiều server -> client** qua HTTP.
- Browser EventSource hỗ trợ auto reconnect.
- Nội dung là text/event-stream, UTF-8 framing.
- Thích hợp notification, job progress, feed updates.
- Client muốn gửi message ngược lại thường dùng HTTP request riêng.

WebSocket:
- Kết nối hai chiều, client/server đều chủ động gửi frame.
- Phù hợp chat, collaboration, tương tác real-time hai chiều hoặc protocol phức tạp.
- Có bài toán heartbeat, auth, state, load balancing và capacity riêng.

Không dùng SSE cho mọi hệ thống real-time nếu yêu cầu trao đổi hai chiều dày đặc.

## 8. So sánh vòng đời: StreamingResponseBody và emitter

### StreamingResponseBody

~~~text
Controller trả StreamingResponseBody
          |
Spring gọi writeTo(outputStream)
          |
Code ghi byte / flush / tiếp tục
          |
Callback kết thúc
          |
Framework hoàn tất response
~~~

Bạn không chủ động gọi complete; callback kết thúc là tín hiệu quan trọng.

### ResponseBodyEmitter hoặc SseEmitter

~~~text
Controller tạo emitter và return
          |
Producer ở thread/scheduler phù hợp
          |
emitter.send(item/event) nhiều lần
          |
emitter.complete() hoặc completeWithError(...)
          |
Framework/container hoàn tất async request
~~~

Với emitter, **quên gọi complete khi stream hữu hạn** có thể khiến request treo đến timeout. Với stream vô hạn, phải thiết kế cancellation/lifecycle và timeouts/heartbeats rõ ràng; giữ connection mãi không phải chiến lược mặc định an toàn.

### Timeout constructor

~~~java
ResponseBodyEmitter emitter = new ResponseBodyEmitter(15_000L);
SseEmitter sse = new SseEmitter(30_000L);
~~~

Các giá trị này tính bằng **milliseconds**. Chúng đặt timeout tùy emitter; không phải khoảng cách giữa các event và không phải thời gian client tự reconnect. Timeout thực tế còn bị chi phối bởi Servlet container, reverse proxy, load balancer và network.

## 9. AsyncTaskExecutor: thành phần không nên để mặc định trong production

Spring Framework khuyến nghị cấu hình rõ executor cho blocking writes/Callable và các xử lý MVC async liên quan. Task executor mặc định cho một số trường hợp MVC async **không thích hợp tải production**.

Một bounded executor giúp:
- Giới hạn số worker threads.
- Có queue size rõ ràng.
- Có chiến lược overload/rejection.
- Cho phép đo active threads, queue, rejected tasks.
- Phân biệt request thread ban đầu với background producer.

### Ví dụ cấu hình

~~~java
@Bean
ThreadPoolTaskExecutor streamExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mvc-stream-");
    executor.initialize();
    return executor;
}
~~~

Đây là method bean minh họa; ví dụ đầy đủ sẽ có imports/class. Thread pool **không phải giải pháp vô hạn**: khi 8 threads bận và queue đủ 100 tasks, task tiếp theo có thể bị từ chối. API phải có chính sách load shedding và HTTP status phù hợp thay vì tạo thread không giới hạn.

### Cấu hình Spring MVC async

~~~java
@Override
public void configureAsyncSupport(
        AsyncSupportConfigurer configurer) {
    configurer.setTaskExecutor(streamExecutor);
    configurer.setDefaultTimeout(30_000L);
}
~~~

Đây là callback của WebMvcConfigurer. Nếu project có Servlet filters tự đăng ký, asyncSupported và ASYNC dispatcher handling phải được cấu hình đúng theo Servlet API. Spring Boot starter-web thông thường đã thiết lập những phần cốt lõi khi auto-configuration MVC.

**Chú ý:** Executor dùng để thực thi StreamingResponseBody.writeTo qua framework có thể khác với executor bạn tự dùng để gọi emitter.send(). Trong ví dụ chúng ta tiêm cùng một bean vào cả MVC async config và controller để quản lý rõ capacity. Với production tải lớn, có thể tách producer executor và blocking write executor theo nhu cầu.

## 10. Thời gian timeout và vòng đời kết nối

Spring Boot 3.3 có property:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 30s
~~~

Nó đặt timeout async request MVC. Nếu không cấu hình, mặc định phụ thuộc Servlet container. Với từng ResponseBodyEmitter/SseEmitter, có thể truyền timeout riêng tính bằng milliseconds.

Đừng gộp những thời hạn sau thành một:
- **MVC async request timeout**.
- **Servlet container async timeout**.
- **Emitter timeout**.
- **Reverse proxy idle/read timeout**.
- **Load balancer/CDN timeout**.
- **Client/browser/network timeout**.
- **EventSource reconnection delay** do event retry hoặc browser quyết định.

Một SSE emitter timeout 30 giây không nói client sẽ nhận event mỗi 30 giây, cũng không bảo đảm proxy cho connection sống đủ 30 giây.

### Lifecycle callbacks của emitter

~~~java
emitter.onCompletion(() -> {
    // Dừng producer, xóa registry entry, đóng subscription riêng.
});
emitter.onTimeout(() -> {
    // Đánh dấu đã timeout, hủy công việc nếu cần.
});
emitter.onError(error -> {
    // Ghi log có kiểm soát, hủy producer nếu cần.
});
~~~

Đây là snippet trong controller/service đã có emitter.

**Callbacks không thay thế quản lý tài nguyên của ứng dụng.** Chúng có thể được gọi từ threads của container khi Servlet async lifecycle thay đổi. Không dựa vào việc callback chạy trên cùng request thread ban đầu hoặc theo một thứ tự duy nhất trong mọi trường hợp.

## 11. IOException khi client ngắt kết nối: tránh xử lý sai

Khi client đóng tab, ngắt mạng hoặc proxy đóng connection, việc ghi ra Servlet response có thể gây IOException.

Với ResponseBodyEmitter hoặc SseEmitter, Spring Framework chỉ rõ: khi **emitter.send ném IOException do remote client không còn nhận**, ứng dụng **không cần gọi emitter.complete() hay completeWithError(IOException)**. Servlet container sẽ kích hoạt AsyncListener error notification và Spring MVC xử lý final async dispatch/exception resolution.

Mẫu phân biệt:

~~~java
try {
    emitter.send("hello", MediaType.TEXT_PLAIN);
} catch (IOException disconnected) {
    // Dừng producer và cleanup state của ứng dụng.
    // Không tự gọi completeWithError chỉ vì IOException từ send.
} catch (RuntimeException other) {
    emitter.completeWithError(other);
}
~~~

Đây là snippet, cần MediaType/imports. IOException không phải bằng chứng duy nhất client disconnect, nhưng khi send I/O thất bại, tránh nhân đôi final dispatch do tự completeWithError theo thói quen.

Với **StreamingResponseBody**, writeTo có thể ném IOException và Spring xử lý qua cơ chế async. Đừng nuốt IOException rồi tiếp tục ghi vô hạn; dừng công việc, đóng input resources do ứng dụng mở và để framework hoàn tất lifecycle.

### Không thể luôn đổi HTTP status sau khi response committed

Khi server đã gửi 200 + headers + một số bytes, lỗi sau đó không bảo đảm đổi thành JSON 500 hoặc HTML Whitelabel. Client có thể nhận stream truncated. Hãy định nghĩa protocol-level error events nếu app cần client biết lỗi phát sinh giữa chừng.

## 12. Heartbeat, proxy buffering và slow clients

SSE có thể đi qua:

~~~text
Browser EventSource
       |
       v
CDN / reverse proxy / ingress / load balancer
       |
       v
Tomcat + Spring MVC SseEmitter
~~~

Một số proxy:
- Buffer nhiều chunks trước khi chuyển tiếp.
- Đóng idle connection trước khi ứng dụng muốn.
- Áp đặt maximum connection lifetime.
- Áp dụng HTTP compression khiến event được flush không đúng thời điểm mong muốn.
- Có connection limits hoặc rate limits riêng.

**flush() hoặc emitter.send() chỉ là nỗ lực ghi tới tầng tiếp theo**, không bảo đảm client nhận ngay từng event trong cùng một thời điểm.

### SSE heartbeat

Một SSE comment-only frame:

~~~text
:keepalive

~~~

có thể giúp đường truyền không bị coi là idle ở những tầng nhận đủ bytes. Với SseEmitter có thể gửi builder comment:

~~~java
emitter.send(SseEmitter.event().comment("keepalive"));
~~~

Đây là snippet; cần chính sách gửi heartbeat định kỳ thích hợp và dừng khi client disconnect. Không gửi heartbeat quá dày gây lưu lượng/CPU vô ích.

Một số proxy như Nginx có thể có chính sách buffering riêng; trong kiến trúc cụ thể có thể cân nhắc no-buffer config hoặc header ứng dụng theo chính sách proxy. Không khẳng định một header tùy ý luôn vô hiệu buffering của mọi CDN.

### Slow consumer và memory

Khi client nhận chậm:
- Một write blocking có thể giữ worker thread lâu.
- Producer có thể tạo dữ liệu nhanh hơn network.
- Queue các event cho mỗi client có thể tăng memory.
- Nhiều idle connections đồng thời tiêu thụ file descriptors, session/state và tài nguyên container.

Hệ thống cần **bounded queues**, timeout, hủy producer và quy tắc bỏ/coalesce event khi phù hợp. Spring MVC async không tự giải quyết mọi backpressure của ứng dụng.

## 13. SSE id, Last-Event-ID và reconnect

Browser EventSource có hỗ trợ tự kết nối lại khi kết nối bị đóng và có thể gửi **Last-Event-ID** nếu đã nhận event có id.

Ví dụ stream:

~~~text
id:101
event:order-change
data:{"orderId":7,"status":"SHIPPED"}

id:102
event:order-change
data:{"orderId":8,"status":"PAID"}

~~~

Sau khi kết nối bị gián đoạn, browser có thể mở kết nối mới kèm:

~~~http
Last-Event-ID: 102
~~~

**SseEmitter không tự lưu lịch sử event hoặc replay missing events.** Nếu cần không mất thông báo, ứng dụng phải thiết kế storage/sequence ID và logic resume. Có thể:

1. Gán id tăng theo một nguồn tin cậy.
2. Lưu một cửa sổ sự kiện (database, log hoặc message broker).
3. Đọc Last-Event-ID ở request mới.
4. Phát lại event có id lớn hơn, theo quy tắc ordering/retention.
5. Cho client de-duplicate events vì reconnect/retry có thể lặp.

### EventSource trong browser

~~~javascript
const stream = new EventSource("/api/sse/ticks");

stream.addEventListener("tick", event => {
  const payload = JSON.parse(event.data);
  console.log(payload.id, payload.message, event.lastEventId);
});

stream.onerror = () => {
  console.log("SSE connection interrupted or unavailable");
};

// Khi không còn cần nhận events:
// stream.close();
~~~

Đây là snippet cho browser JavaScript chạy cùng origin với endpoint. Để chạy cross-origin, cần CORS và credential policy phù hợp. Browser EventSource API thông thường **không cho tùy ý thêm Authorization header** trong constructor; cần thiết kế authentication bằng same-origin cookies, gateway hoặc client transport khác, không đưa token nhạy cảm lên URL nếu tránh được.

### Reconnect không đồng nghĩa exactly-once delivery

Browser reconnect có thể dẫn tới event lặp hoặc mất nếu server không lưu lịch sử. Nếu API cần transaction semantics, đừng dựa một mình vào SSE framing; cần định nghĩa offset/replay/idempotency rõ.

## 14. Ví dụ thực hành: một Spring Boot MVC app có cả ba API

Project này dùng **Spring Boot 3.3.x, Java 17+ và spring-boot-starter-web**, không cần starter-webflux.

### 14.1. Dependencies

Trong một Gradle project Spring Boot đã có plugin, repositories và Java toolchain:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **block dependencies**, không phải toàn bộ build.gradle. Dùng Gradle wrapper do project cung cấp. Spring Boot 3.3.x yêu cầu Java 17 trở lên.

### 14.2. File Java hoàn chỉnh

Tạo **src/main/java/com/example/streammvc/ServletStreamingApplication.java**:

~~~java
package com.example.streammvc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
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
public class ServletStreamingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletStreamingApplication.class, args);
    }

    @Bean
    ThreadPoolTaskExecutor streamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mvc-stream-");
        executor.initialize();
        return executor;
    }

    @Configuration(proxyBeanMethods = false)
    public static class MvcAsyncConfig implements WebMvcConfigurer {

        private final ThreadPoolTaskExecutor executor;

        public MvcAsyncConfig(ThreadPoolTaskExecutor executor) {
            this.executor = executor;
        }

        @Override
        public void configureAsyncSupport(
                AsyncSupportConfigurer configurer) {
            configurer.setTaskExecutor(executor);
            configurer.setDefaultTimeout(30_000L);
        }
    }

    public record Tick(int id, String message) {}

    @RestController
    public static class StreamingController {

        private final ThreadPoolTaskExecutor executor;

        public StreamingController(ThreadPoolTaskExecutor executor) {
            this.executor = executor;
        }

        // Dành cho lab: tạo khoảng cách quan sát giữa các phần.
        private static boolean pause() {
            try {
                Thread.sleep(150L);
                return true;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return false;
            }
        }

        @GetMapping(
            path = "/api/stream/lines",
            produces = MediaType.TEXT_PLAIN_VALUE
        )
        public ResponseEntity<StreamingResponseBody> streamLines() {
            StreamingResponseBody body = output -> {
                for (int i = 1; i <= 3; i++) {
                    byte[] bytes = ("line-" + i + "\n")
                            .getBytes(StandardCharsets.UTF_8);
                    output.write(bytes);
                    output.flush();

                    if (!pause()) {
                        break;
                    }
                }
            };

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .cacheControl(CacheControl.noCache())
                    .body(body);
        }

        @GetMapping(
            path = "/api/emit/lines",
            produces = MediaType.TEXT_PLAIN_VALUE
        )
        public ResponseEntity<ResponseBodyEmitter> emitLines() {
            ResponseBodyEmitter emitter =
                    new ResponseBodyEmitter(15_000L);
            AtomicBoolean active = new AtomicBoolean(true);

            emitter.onCompletion(() -> active.set(false));
            emitter.onTimeout(() -> active.set(false));
            emitter.onError(error -> active.set(false));

            executor.execute(() -> {
                try {
                    for (int i = 1; i <= 3 && active.get(); i++) {
                        emitter.send(
                                "part-" + i + "\n",
                                MediaType.TEXT_PLAIN
                        );
                        if (!pause()) {
                            break;
                        }
                    }
                    if (active.get()) {
                        emitter.complete();
                    }
                } catch (IOException disconnected) {
                    // Servlet/Spring xử lý async I/O failure.
                    // Producer phải dừng; không tự completeWithError
                    // chỉ vì IOException do emitter.send.
                    active.set(false);
                } catch (RuntimeException ex) {
                    active.set(false);
                    emitter.completeWithError(ex);
                }
            });

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .cacheControl(CacheControl.noCache())
                    .body(emitter);
        }

        @GetMapping(
            path = "/api/sse/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
        )
        public ResponseEntity<SseEmitter> ticks() {
            SseEmitter emitter = new SseEmitter(15_000L);
            AtomicBoolean active = new AtomicBoolean(true);

            emitter.onCompletion(() -> active.set(false));
            emitter.onTimeout(() -> active.set(false));
            emitter.onError(error -> active.set(false));

            executor.execute(() -> {
                try {
                    for (int i = 1; i <= 3 && active.get(); i++) {
                        emitter.send(
                            SseEmitter.event()
                                .id(Integer.toString(i))
                                .name("tick")
                                .reconnectTime(2000L)
                                .data(
                                    new Tick(i, "tick-" + i),
                                    MediaType.APPLICATION_JSON
                                )
                        );
                        if (!pause()) {
                            break;
                        }
                    }
                    if (active.get()) {
                        emitter.complete();
                    }
                } catch (IOException disconnected) {
                    active.set(false);
                    // Không tự completeWithError khi send gây I/O error.
                } catch (RuntimeException ex) {
                    active.set(false);
                    emitter.completeWithError(ex);
                }
            });

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_EVENT_STREAM)
                    .cacheControl(CacheControl.noCache())
                    .body(emitter);
        }
    }
}
~~~

**Đây là một Java source file hoàn chỉnh trong project Spring Boot đã có dependencies**, không chạy bằng javac trần nếu không khai classpath Spring/Jackson/Servlet.

### Giải thích code

- **streamExecutor():** tạo ThreadPoolTaskExecutor có core=4, max=8, queue=100. Đây là giá trị minh họa để giới hạn tài nguyên, không phải sizing recommendation chung cho production.
- **MvcAsyncConfig.configureAsyncSupport:** cung cấp executor cho Spring MVC async và timeout 30 giây.
- **streamLines():** trả StreamingResponseBody; framework gọi callback writeTo trên async executor. Code ghi ba dòng byte UTF-8, flush mỗi dòng.
- **emitLines():** trả ResponseBodyEmitter; producer trên executor gọi send(String, text/plain) rồi complete. Content-Type text/plain được đặt rõ và mỗi part kết thúc bằng newline.
- **ticks():** SseEmitter gửi ba event có id, event name, retry và dữ liệu Tick được JSON serialize; top-level response là text/event-stream.
- **AtomicBoolean active:** callbacks đánh dấu stream không còn hoạt động; producer kiểm tra để tránh tiếp tục gửi sau completion/timeout/error. Đây là cleanup tối thiểu cho demo ngắn, không phải registry hoặc cancellation framework đầy đủ cho stream kéo dài.
- **IOException khi emitter.send:** producer dừng, để Spring/Servlet thực hiện xử lý async I/O error; code không tự completeWithError cho IOException từ send.
- **RuntimeException:** completeWithError báo lỗi cho framework khi còn có thể; không cam kết đổi status nếu response đã committed.
- **pause():** Thread.sleep minh họa để nhìn thấy ba đợt dữ liệu; chạy trên bounded worker pool, không phải kỹ thuật non-blocking. **Không dùng Thread.sleep trong request thread hoặc WebFlux event loop** ở ứng dụng thật.

### Rủi ro executor quá tải

Khi nhiều requests cùng stream, executor.execute có thể bị từ chối vì worker/queue đã đầy. Trong ví dụ, việc từ chối có thể truyền exception qua controller và thành response lỗi khi chưa commit. Production cần chính sách overload: giới hạn concurrent streams, từ chối có kiểm soát (ví dụ 503 khi phù hợp), metrics/retry hints và cleanup để không làm ứng dụng mất ổn định.

### Phạm vi của bản demo

Đây là ba streams **hữu hạn** (mỗi stream ba đợt), không phải hệ thống phát sự kiện vô hạn. Trong một dịch vụ real-time lớn, nên dùng event bus/pub-sub với bounded subscriptions, heartbeats và cancellation thay vì tạo một thread/task nằm chờ vô thời hạn cho mỗi người dùng.

## 15. Cấu hình application.yml và khởi động

Tạo file **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 30s
~~~

Property spring.mvc.async.request-timeout trong Boot 3.3 đặt timeout MVC async; ví dụ đồng thời có configurer.setDefaultTimeout(30000L), nên cùng thống nhất thời hạn 30 giây. Hai emitter có timeout riêng 15 giây.

Trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Chờ embedded Tomcat thông báo đã chạy trên cổng 8080. Nếu cổng bị chiếm, đổi server.port và dùng cổng mới trong curl.

Không cần @EnableAsync chỉ vì controller trả StreamingResponseBody/ResponseBodyEmitter/SseEmitter; đây là **Servlet MVC async return-value support**. @EnableAsync có mục đích khác là xử lý @Async method calls.

## 16. Thử StreamingResponseBody qua curl

Dùng:

~~~bash
curl -i -N \
  -H 'Accept: text/plain' \
  http://localhost:8080/api/stream/lines
~~~

Một body hợp lệ:

~~~text
line-1
line-2
line-3
~~~

- **-i** cho biết status và headers.
- **-N** hoặc --no-buffer giảm buffering ở phía curl, giúp quan sát từng đợt.
- Body dùng text/plain, không phải JSON.
- Flush xảy ra sau mỗi dòng trong server code, nhưng proxy/TCP/client vẫn có thể buffer.

### Thử độ nguyên vẹn khi save ra file

~~~bash
curl -sS -N \
  http://localhost:8080/api/stream/lines \
  -o lines.txt
~~~

File lines.txt có nội dung ba dòng trên, mỗi dòng kết thúc bởi ký tự newline. Đừng xem dấu xuống dòng là dấu hiệu TCP chunk boundary; HTTP framing và ứng dụng payload là hai lớp khác nhau.

### Binary download

Nếu stream file thực, dùng application/octet-stream hoặc media type cụ thể và Content-Disposition phù hợp. Đối với binary, không hiển thị raw bytes vào terminal và không tự chuyển bytes qua String chỉ để kiểm tra: dùng checksum/hex viewer/size.

## 17. Thử ResponseBodyEmitter qua curl

~~~bash
curl -i -N \
  -H 'Accept: text/plain' \
  http://localhost:8080/api/emit/lines
~~~

Một body hợp lệ:

~~~text
part-1
part-2
part-3
~~~

Trong ví dụ, chính ứng dụng thêm newline vào mỗi String trước khi send; **ResponseBodyEmitter không tự thêm newline cho mỗi object**.

Nếu thay các String bằng các DTO dưới application/json, phải xác định framing contract cụ thể. Ba DTO JSON nối nhau chưa tạo thành một JSON array. Muốn streaming nhiều JSON objects, cân nhắc NDJSON đúng chuẩn hoặc dùng SSE nếu các item là events.

## 18. Thử SseEmitter qua curl

~~~bash
curl -i -N \
  -H 'Accept: text/event-stream' \
  http://localhost:8080/api/sse/ticks
~~~

Response thường có Content-Type text/event-stream. Body có dạng tương đương:

~~~text
id:1
event:tick
retry:2000
data:{"id":1,"message":"tick-1"}

id:2
event:tick
retry:2000
data:{"id":2,"message":"tick-2"}

id:3
event:tick
retry:2000
data:{"id":3,"message":"tick-3"}

~~~

Thứ tự các dòng metadata trong một event, khoảng trắng sau colon, JSON field order và thời điểm flush có thể khác. Test nên kiểm tra **ba event hợp lệ, id, name, data và status/media type**, không so sánh toàn bộ raw text với transcript cố định.

### Cách parse trong browser

~~~javascript
const events = new EventSource("/api/sse/ticks");

events.addEventListener("tick", event => {
  const item = JSON.parse(event.data);
  console.log(item.id, item.message);
});

events.onerror = () => {
  console.log("Connection interrupted, closed or retrying");
};

// Không cần nữa thì gọi events.close().
~~~

Với endpoint demo, server chủ động complete sau ba events. Browser EventSource **có thể reconnect sau khi server đóng stream bình thường**, vì giao thức EventSource xem stream kết thúc và có retry logic. Muốn client dừng hẳn sau ba events, ứng dụng browser phải có điều kiện close() của riêng nó.

### PowerShell

Trên Windows dùng curl.exe thay vì alias:

~~~powershell
curl.exe -i -N -H "Accept: text/plain" "http://localhost:8080/api/stream/lines"
curl.exe -i -N -H "Accept: text/plain" "http://localhost:8080/api/emit/lines"
curl.exe -i -N -H "Accept: text/event-stream" "http://localhost:8080/api/sse/ticks"
~~~

## 19. Kiểm thử bằng HTTP thật với TestRestTemplate

Kiểm thử **nội dung cuối cùng** của các finite streams có thể dùng HTTP client nhận toàn bộ response. Để chứng minh độ trễ từng chunk, cần thêm test client đọc streaming và timestamp/flush observations; không thể khẳng định từ một kết quả String đã gom hết body.

Tạo **src/test/java/com/example/streammvc/ServletStreamingApplicationTests.java**:

~~~java
package com.example.streammvc;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ServletStreamingApplicationTests {

    @Autowired
    TestRestTemplate http;

    private ResponseEntity<String> get(
            String path, MediaType accept) {

        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(accept));

        return http.exchange(
                path,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );
    }

    @Test
    void rawStreamingWritesThreeLines() {
        ResponseEntity<String> result =
                get("/api/stream/lines", MediaType.TEXT_PLAIN);

        assertEquals(200, result.getStatusCode().value());
        assertNotNull(result.getHeaders().getContentType());
        assertTrue(result.getHeaders().getContentType()
                .isCompatibleWith(MediaType.TEXT_PLAIN));
        assertEquals("line-1\nline-2\nline-3\n",
                result.getBody());
    }

    @Test
    void emitterSendsThreePlainTextParts() {
        ResponseEntity<String> result =
                get("/api/emit/lines", MediaType.TEXT_PLAIN);

        assertEquals(200, result.getStatusCode().value());
        assertEquals("part-1\npart-2\npart-3\n",
                result.getBody());
    }

    @Test
    void sseProducesEventStreamWithThreeEvents() {
        ResponseEntity<String> result =
                get("/api/sse/ticks", MediaType.TEXT_EVENT_STREAM);

        assertEquals(200, result.getStatusCode().value());
        assertNotNull(result.getHeaders().getContentType());
        assertTrue(result.getHeaders().getContentType()
                .isCompatibleWith(MediaType.TEXT_EVENT_STREAM));

        String body = result.getBody();
        assertNotNull(body);
        assertTrue(body.contains("event:tick"));
        assertTrue(body.contains("tick-1"));
        assertTrue(body.contains("tick-2"));
        assertTrue(body.contains("tick-3"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Những test này gửi request qua embedded HTTP server trên random port, sau đó **đợi stream hữu hạn hoàn tất**. Chúng kiểm tra HTTP status, Content-Type và payload nhưng không chứng minh một dòng được giao chính xác sau 150 ms, vì buffering có thể xảy ra.

### Vì sao không chỉ dùng MockMvc?

MockMvc hỗ trợ MVC async testing với asyncStarted và asyncDispatch, thích hợp kiểm tra controller return values trong pipeline Spring MVC. Tuy nhiên, MockMvc không mở connection TCP thật và không mô phỏng mọi hành vi transport/proxy, flush hoặc client disconnect. Với mục tiêu học HTTP streaming, nên bổ sung integration test có embedded server thật như trên.

## 20. Phân biệt test “body đúng” và “stream đến dần”

Một test đọc response body thành String sau khi server complete chỉ chứng minh **nội dung cuối cùng**. Muốn đo streaming delivery, cần một client có thể đọc input theo thời gian:

~~~text
T0: client gửi GET /api/stream/lines
T1: client đọc "line-1"
T2: client đọc "line-2"
T3: client đọc "line-3"
T4: EOF
~~~

Một phép kiểm thử tốt sẽ ghi timestamp của lần đọc từng line, kèm timeout và không giả định network scheduler chính xác tuyệt đối.

Ví dụ Java 17 với HTTP client, trong một chương trình test/demo riêng:

~~~java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("http://localhost:8080/api/stream/lines"))
    .header("Accept", "text/plain")
    .GET()
    .build();

HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> body = response.body()) {
    body.forEach(System.out::println);
}
~~~

Đây là **snippet**, cần imports java.net.http.*, java.net.URI và java.util.stream.Stream, và server đang chạy. Không phải file Java độc lập vì thiếu main class. Với endpoint có ba dòng, output theo nội dung là:

~~~text
line-1
line-2
line-3
~~~

Không cam kết thời điểm đọc từng dòng sẽ đúng tuyệt đối 150 ms vì JVM, OS, TCP, Servlet/container và proxy đều có lịch điều phối riêng.

## 21. Filters, asyncSupported và DispatcherType

Spring MVC async dựa trên Servlet container. Trong một deployment tùy chỉnh, Servlet và Filters phải cho phép async processing:

- Servlet/Filter declarations có cờ **asyncSupported=true** khi cần.
- Filter mappings có thể cần **DispatcherType.ASYNC** theo chức năng muốn theo dõi.
- Một số filters được gọi lại khi có ASYNC dispatch, không được mặc định chạy đúng một lần cho toàn bộ lifecycle.
- Các wrappers chứa request/response phải tương thích với async lifecycle; nếu không, exception hoặc lỗi write có thể xuất hiện.

Với Spring Boot starter-web auto-configuration mặc định, các thiết lập cốt lõi thường đã được xử lý. Khi tự tạo FilterRegistrationBean hoặc khai Servlet thủ công, cần kiểm tra asyncSupported/dispatcher types.

### OncePerRequestFilter có thực sự chạy đúng một lần mọi thread?

Tên lớp giúp tránh xử lý trùng trong phạm vi dispatcher theo cấu hình và policy, nhưng async dispatch có thể là một lần xử lý khác. Các method như shouldNotFilterAsyncDispatch() và dispatcher types ảnh hưởng filter có chạy ở ASYNC dispatch hay không.

Không dùng ThreadLocal để suy ra một request giữ mãi cùng thread: request có thể chuyển từ Servlet thread sang executor rồi quay lại async dispatch trên thread khác.

### Logging và MDC

Nếu dùng MDC/trace ID với ThreadLocal, phải áp dụng context propagation phù hợp vào async tasks hoặc trích xuất các giá trị nhỏ trước khi bắt đầu. Đừng lưu nguyên HttpServletRequest vào singleton để đọc sau, vì request lifecycle và concurrency sẽ gây rủi ro.

## 22. Authentication, CORS và browser EventSource

SseEmitter không tự xác thực người dùng. Hãy đảm bảo route được bảo vệ bằng Spring Security phù hợp và mọi event chỉ chứa dữ liệu client được phép nhận.

Với browser EventSource:
- Constructor cơ bản không cho set mọi custom HTTP headers tùy ý.
- Same-origin cookie/session authentication có thể phù hợp nếu CSRF, cookie SameSite và session policy được thiết kế đúng.
- Cross-origin requests cần CORS policy, có thể cần credentials configuration khi dùng cookies.
- Không đưa access token nhạy cảm vào query string nếu tránh được, vì URL xuất hiện trong logs/history/monitoring.
- Cần kiểm tra trạng thái authorization trong suốt vòng đời connection nếu quyền có thể thay đổi.
- Một SSE stream đã mở có thể tiếp tục phát sau khi user bị revoke nếu producer không kiểm tra quyền và cancellation theo yêu cầu ứng dụng.

### SSE chỉ là một representation

EventSource là client tiện lợi cho SSE; backend vẫn là một HTTP endpoint, có thể kiểm thử bằng curl hoặc custom client. Không đặt Content-Type: application/json cho toàn bộ stream chỉ vì data field được JSON serialize.

## 23. Caching, headers và file downloads

Với response được cá nhân hóa/real-time, cần cân nhắc:

~~~http
Cache-Control: no-cache
Content-Type: text/event-stream
~~~

No-cache yêu cầu cache kiểm tra lại trước khi tái sử dụng, **không phải** cấm mọi lưu trữ. Nếu chứa dữ liệu nhạy cảm, có thể cần **Cache-Control: no-store** và policy tương ứng. Ví dụ app dùng CacheControl.noCache() để minh họa, không phải security policy production đầy đủ.

Với download:

~~~http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.csv"
~~~

Khi file là CSV thật, có thể dùng text/csv với charset thích hợp thay vì octet-stream; tùy cách muốn client xử lý. Content-Disposition chỉ gợi ý download filename, không đảm bảo quyền truy cập hoặc bytes đã đúng định dạng.

### Xác định Content-Length có nên đặt không?

Nếu không biết trước kích thước toàn bộ stream, thường không nên cố đo Content-Length bằng cách buffer toàn bộ body. HTTP/1.1 có thể dùng chunked transfer encoding, HTTP/2 có framing riêng; đây là trách nhiệm container/transport, không phải do mỗi flush ứng với một HTTP chunk.

## 24. Quan sát và giới hạn năng lực hệ thống

Streaming endpoint cần quan sát khác một REST endpoint ngắn:

| Metric | Lý do |
|---|---|
| Số connections/streams đang mở | Dễ cạn socket hoặc resource |
| Async request duration | Phát hiện stream treo/timeout |
| TaskExecutor active threads | Đánh giá blocking writes |
| Executor queue size / rejected tasks | Phát hiện quá tải |
| Bytes sent / event rate | Đánh giá throughput |
| Client disconnects / IOException | Phân biệt mất kết nối với server error |
| Timeout count | Đánh giá idle/proxy/timeouts |
| Producer backlog / retained events | Phát hiện memory tăng |
| 4xx/5xx / request latency | Theo dõi lỗi HTTP chung |
| Event id lag / replay rate | Kiểm soát SSE reconnect |

Hãy thiết kế **bounded resources** ở mọi tầng: active streams, producer subscriptions, per-client queue, max payload, max execution time, connection quotas, proxy limits.

### Khi nào không nên dùng SseEmitter?

Nếu ứng dụng cần hàng chục nghìn kết nối rất dài hạn và mỗi connection phải có thread blocking liên tục, MVC emitter có thể gặp chi phí tài nguyên đáng kể. Nên đánh giá **WebFlux non-blocking I/O**, messaging infrastructure hoặc WebSocket tùy nhu cầu, chứ không quyết định chỉ theo số lượng kết nối mà không benchmark.

## 25. Các sai lầm phổ biến

| Sai lầm | Thực tế |
|---|---|
| StreamingResponseBody đồng nghĩa response write không chặn | Servlet OutputStream writes có thể blocking |
| Trả ResponseBodyEmitter là producer tự chạy | Ứng dụng phải cung cấp producer/background thread hoặc event source |
| Một emitter.send tự thêm newline | Không; cần framing do ứng dụng thiết kế |
| Ba object JSON send liên tiếp tạo JSON array | Không chắc; có thể thành JSON nối không hợp lệ |
| SseEmitter là WebSocket | Không; SSE là server-to-client text/event-stream |
| EventSource luôn không reconnect sau complete | Browser có thể reconnect; client cần close khi muốn dừng |
| SSE id tự động giúp replay mất event | Không; app phải lưu lịch sử và xử lý Last-Event-ID |
| Gọi completeWithError cho mọi IOException từ send | Spring docs khuyến cáo để Servlet/Spring xử lý I/O disconnect |
| Timeout emitter là thời gian giữa các events | Không; đó là async lifecycle timeout |
| flush bảo đảm mỗi dòng hiện ngay trên browser | Không; proxy/network/client có thể buffer |
| MVC async không cần executor capacity planning | Sai; blocking writes và producers cần tài nguyên |
| Tạo thread mới cho mỗi client SSE vô thời hạn | Dễ cạn threads/memory |
| Client đã disconnect thì không cần cleanup | Phải hủy producer/subscription và xóa registry entry |
| @EnableAsync bắt buộc cho MVC streaming | Không; đây là Servlet async return-value mechanism |
| MockMvc test chứng minh TCP streaming đúng | Không; cần test HTTP thật |
| Content-Type JSON cho SSE data JSON | Sai; top-level SSE là text/event-stream |
| Response đã commit vẫn đổi thành 500 JSON được | Không bảo đảm |

## 26. Luyện tập

**Bài 1 — Đổi khoảng thời gian:** thay pause từ 150 ms thành 500 ms, dùng curl -N để quan sát. Đo thời gian từng dòng ở client, phân biệt timeout và interval.

**Bài 2 — NDJSON:** thay /api/emit/lines thành endpoint phát mỗi line là một JSON object được encode đúng và kết thúc bằng newline. Đặt media type application/x-ndjson, dùng parser NDJSON kiểm tra từng dòng. Không trả JSON objects nối sát nhau.

**Bài 3 — File lớn:** tạo dữ liệu thử nghiệm hợp lệ trên disk và dùng StreamingResponseBody + InputStream.transferTo; so sánh heap usage với Files.readAllBytes của file cùng kích thước. Đặt giới hạn request concurrency.

**Bài 4 — SSE client:** chạy browser EventSource, lắng nghe event "tick", parse JSON, rồi close() sau id=3 để tránh reconnect ở ví dụ finite stream.

**Bài 5 — SSE heartbeat:** thiết kế một event source dài hạn với comment heartbeat. Kiểm tra proxy idle timeout và cleanup producer khi client close.

**Bài 6 — Last-Event-ID:** xây một event log in-memory có giới hạn hoặc database, trả event id tăng; khi reconnect, đọc Last-Event-ID và phát lại đúng các event còn trong retention window. Xử lý duplicate IDs.

**Bài 7 — Overload:** chạy load test có giới hạn an toàn cho executor core=4, max=8, queue=100; đo thời gian chờ và rejected tasks. Đề xuất chính sách từ chối có kiểm soát thay vì tăng max threads vô hạn.

**Bài 8 — HTTP test:** viết một test chỉ assert body sau khi complete và một test đọc từng line kèm timestamp. Giải thích vì sao hai test chứng minh hai tính chất khác nhau.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào nên chọn StreamingResponseBody thay vì ResponseBodyEmitter?

**Đáp án:** Khi ứng dụng muốn kiểm soát trực tiếp raw bytes, ví dụ export/download file hoặc xuất báo cáo lớn theo từng khối.

**Câu 2.** ResponseBodyEmitter có tự thêm newline hoặc JSON array framing không?

**Đáp án:** Không. Nó ghi từng object thông qua HttpMessageConverter; ứng dụng phải thiết kế record separator/format phù hợp.

**Câu 3.** SseEmitter kế thừa từ lớp nào?

**Đáp án:** ResponseBodyEmitter.

**Câu 4.** Top-level media type của SSE là gì khi event data chứa JSON?

**Đáp án:** text/event-stream, không phải application/json.

**Câu 5.** Trả StreamingResponseBody có giải phóng Servlet request thread ban đầu không?

**Đáp án:** Có thể chuyển request sang Servlet async mode để nhả thread ban đầu; việc ghi response vẫn có thể blocking và chạy qua async executor.

**Câu 6.** Vì sao phải cấu hình TaskExecutor thay vì để mặc định?

**Đáp án:** Để quản lý blocking writes và worker capacity, giới hạn threads/queue và tránh overload mất kiểm soát.

**Câu 7.** Một emitter hữu hạn gửi xong ba items phải làm gì?

**Đáp án:** Gọi complete(), nếu không response có thể chờ đến timeout. StreamingResponseBody thì hoàn tất khi writeTo callback kết thúc.

**Câu 8.** Khi emitter.send gây IOException vì remote client ngắt kết nối, có nên luôn gọi completeWithError không?

**Đáp án:** Không. Spring Framework hướng dẫn để Servlet container/Spring async error listener xử lý I/O failure; ứng dụng dừng producer và cleanup.

**Câu 9.** SSE id có tự đảm bảo đúng một lần và replay sau reconnect không?

**Đáp án:** Không. App cần lưu lịch sử/offset, dùng Last-Event-ID và xử lý duplicate hoặc retention gap.

**Câu 10.** flush() có bảo đảm browser thấy dữ liệu ngay không?

**Đáp án:** Không. Proxy, TCP, compression và client có thể buffer.

**Câu 11.** MockMvc có chứng minh HTTP network chunking không?

**Đáp án:** Không. Nó giúp kiểm tra MVC async request processing; muốn kiểm tra delivery thực cần embedded HTTP server/client streaming.

**Câu 12.** Khi response đã commit mà producer ném lỗi, status có chắc đổi thành 500 không?

**Đáp án:** Không. Có thể stream bị ngắt và server chỉ log error.

## 28. Checklist triển khai

- [ ] Đã xác nhận ứng dụng chạy **Spring MVC Servlet**, không nhầm với WebFlux.
- [ ] Chọn StreamingResponseBody cho bytes, ResponseBodyEmitter cho nhiều serialized parts, SseEmitter cho chuẩn SSE.
- [ ] Content-Type phù hợp framing: text/plain, text/csv, application/octet-stream hoặc text/event-stream.
- [ ] Không ghép các JSON objects thành một body JSON không hợp lệ.
- [ ] Có bounded executor/scheduler và chính sách quá tải.
- [ ] Đã cấu hình asyncSupported khi tự đăng ký Servlet/Filter.
- [ ] Không dùng ThreadLocal request context xuyên async threads mà không propagate đúng.
- [ ] Có timeout ở MVC/emitter, reverse proxy và client theo yêu cầu thực tế.
- [ ] Producer hữu hạn gọi complete(); producer dài hạn có cancellation/cleanup.
- [ ] IOException từ emitter.send được xử lý theo khuyến cáo Servlet/Spring.
- [ ] Không hứa flush tương đương delivery tức thời tới browser.
- [ ] SSE có heartbeat, event id/replay/reconnect khi cần reliability.
- [ ] Có authentication/authorization và CORS phù hợp; không đưa tokens vào URL khi tránh được.
- [ ] Có metrics: active streams, executor pool/queue, timeouts, disconnects, event rate.
- [ ] Đã kiểm thử response qua embedded server và qua proxy/gateway thực tế.
- [ ] Với file lớn, tránh gom toàn bộ vào byte[] hoặc giữ vô hạn trong memory.
- [ ] Không assume response có thể đổi status sau khi đã commit bytes.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — MVC Asynchronous Requests: HTTP Streaming, SSE, Raw Data, Disconnects, Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.1 — StreamingResponseBody Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html)
- [Spring Framework 6.1 — ResponseBodyEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html)
- [Spring Framework 6.1 — SseEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html)
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Common Application Properties, spring.mvc.async.request-timeout](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
