# Giới hạn tài nguyên, timeout, ngắt kết nối và dừng ứng dụng an toàn trong Spring Web

## 1. Mục tiêu: hệ thống hoạt động đúng cả khi quá tải và khi kết nối bị cắt

Một HTTP endpoint không chỉ cần trả JSON đúng lúc lưu lượng bình thường. Trong vận hành, hệ thống còn phải biết xử lý các trường hợp:

- Nhiều request đồng thời hơn số thread, connection hoặc phiên làm việc mà máy chủ xử lý được.
- Client gửi một request quá lớn, upload tệp lớn hoặc giữ kết nối chậm.
- HTTP call sang dịch vụ khác bị chậm hoặc mất kết nối; một request tưởng nhỏ giữ worker quá lâu.
- Browser đóng tab, mobile mất mạng, reverse proxy hết hạn idle timeout trong lúc server còn xử lý.
- Pod/process nhận tín hiệu dừng để triển khai phiên bản mới, nhưng vẫn còn request đang chạy.
- Một stream SSE hoặc WebSocket sống lâu, cần kết thúc và giải phóng tài nguyên khi client đi xa.

Bốn nhóm kiến thức cần phối hợp là **resource limits**, **timeouts**, **disconnect/cancellation** và **graceful shutdown**. Giải pháp an toàn không phải chỉ tăng số thread, tăng timeout hay cho phép upload vô hạn: các thay đổi đó có thể chuyển tắc nghẽn từ HTTP layer sang database, memory, thread pool hoặc service phụ thuộc.

Bài dùng chủ yếu **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. Phân biệt **Spring MVC trên Servlet/Tomcat** và **Spring WebFlux trên Reactor Netty** khi thuộc tính hay lifecycle có khác biệt. Những số cấu hình là ví dụ để học, phải đo tải và điều chỉnh theo hạ tầng thực tế.

### Mô hình đường đi của request

~~~text
Client/browser/mobile
       |
  Load balancer / ingress / reverse proxy
       |     (max request, keep-alive, idle timeout)
       v
  HTTP listener (Tomcat / Reactor Netty)
       |     (connections, backlog, event loop / worker threads)
       v
  DispatcherServlet (MVC) hoặc DispatcherHandler (WebFlux)
       |     (request body, codec, memory, validation)
       v
  Controller + business work
       |     (concurrency, queues, CPU, cancellation)
       +----> DB connection pool
       |
       +----> RestClient / WebClient -> remote API
       |           (connect, read, response, total timeout)
       v
  HTTP response / stream
       |
       v
  Client còn kết nối hoặc đã disconnect
~~~

Chỉ cần một tầng không có giới hạn, hệ thống có thể bị quá tải dù các tầng còn lại được cấu hình hợp lý.

## 2. Resource limits: cần giới hạn những tài nguyên nào?

| Tài nguyên | Rủi ro | Nơi kiểm soát thường gặp |
| --- | --- | --- |
| Số kết nối HTTP | Quá nhiều sockets, file descriptors, giữ kết nối nhàn rỗi | Tomcat/Netty, ingress, OS |
| Số request đang xử lý | Thread hoặc CPU bị giữ đến kiệt | Worker pool, semaphore, bulkhead |
| Queue chờ | Độ trễ không có trần, hết bộ nhớ | Executor queue, connection accept backlog, admission control |
| HTTP headers | Header quá lớn tiêu tốn bộ nhớ hoặc bị lợi dụng | server.max-http-request-header-size, proxy |
| Request body / upload | Disk/memory cạn, phải lưu dữ liệu rất lớn | Multipart limits, codec limits, proxy, file storage |
| JSON body | Decoder gom nhiều dữ liệu trong RAM | WebFlux codec maxInMemorySize, thiết kế stream |
| WebSocket/SSE sessions | Giữ socket và bộ đệm outbound lâu dài | Session limits, timeout/heartbeat, subscriber policy |
| Kết nối DB | Thread xếp hàng chờ DB, cascade failure | Connection pool max size và query timeout |
| HTTP client outbound | Quá nhiều kết nối gọi downstream, retry bão | HTTP pool, pending-acquire, concurrency limit |
| File/temp buffer | Temp disk cạn, rò tài nguyên | Temp directory quota, multipart cleanup, lifecycle |

**Bảo vệ nhiều tầng**: nếu ingress chặn upload lớn, ứng dụng vẫn nên có giới hạn của riêng mình. Nếu application giới hạn 20 business operations đồng thời, HTTP server vẫn cần giới hạn connections/threads và HTTP client outbound cần pool thích hợp.

### 2.1 Tomcat với Spring MVC

Một cấu hình minh họa trong **src/main/resources/application.properties**:

~~~properties
# Spring MVC sử dụng embedded Tomcat trong starter-web.
server.tomcat.threads.max=80
server.tomcat.max-connections=400
server.tomcat.accept-count=100

# HTTP request headers và multipart upload.
server.max-http-request-header-size=16KB
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

# Thời gian giữ kết nối nhàn rỗi hoặc chờ client gửi request line.
server.tomcat.keep-alive-timeout=20s
server.tomcat.connection-timeout=10s
~~~

Ý nghĩa cụ thể:
- **threads.max** giới hạn các worker thread của Tomcat kiểu truyền thống. Đây không phải giới hạn chính xác số request toàn ứng dụng nếu còn async request, virtual threads, background jobs hoặc side effects.
- **max-connections** giới hạn số connection mà server xử lý ở một thời điểm; HTTP keep-alive có thể giữ connection dù không có request đang thực thi.
- **accept-count** điều tiết backlog khi tài nguyên chấp nhận request đã bão hòa; không phải hàng đợi nghiệp vụ có thể giao tác.
- **max-http-request-header-size** bảo vệ header request, không áp dụng cho toàn bộ file upload; cách tính có khác nhau giữa Tomcat và Netty.
- **max-file-size/max-request-size** thuộc Servlet multipart parsing; không áp dụng trực tiếp cho WebFlux multipart hoặc mọi dạng application/json.
- **connection-timeout** và **keep-alive-timeout** thuộc giai đoạn kết nối/HTTP parser; chúng không tự đặt deadline cho business method chạy lâu.
- Khi dùng **virtual threads** của Java 21+ với cấu hình hỗ trợ, property threads.max của Tomcat có thể không tác động như pool truyền thống. Bài thực hành đang dùng Java 17 và worker threads thường.

Thông số quá thấp có thể từ chối request hợp lệ; quá cao có thể dồn thêm tải xuống DB/CPU, kéo dài tail latency. Tăng cùng lúc các chỉ số mà không đo thường làm khó tìm bottleneck.

### 2.2 WebFlux và codec limits

Ở Spring WebFlux, nhiều HTTP connection có thể được một số event-loop thread phục vụ; **không được block event loop** bằng Thread.sleep, JDBC đồng bộ hoặc xử lý CPU dài. Reactive Streams có backpressure, nhưng nó không tự giới hạn kích thước toàn bộ JSON, số concurrent subscriptions hoặc tổng thời gian sống của mọi stream.

Ví dụ tùy biến giới hạn giải mã trong WebFlux server:

~~~java
@Configuration
public class WebFluxCodecConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Imports cần dùng trong fragment:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;
~~~

**maxInMemorySize** giới hạn lượng dữ liệu mà decoder cần buffer cho một object/chunk tùy codec. Với một stream NDJSON, giới hạn có thể áp dụng trên mỗi record cần giải mã; nó **không là giới hạn total bytes mọi response**. Nếu codec vượt giới hạn, có thể nhận **DataBufferLimitException**. Đừng tăng lên hàng trăm MB chỉ để hợp thức hóa kiểu giải mã không phù hợp.

Đối với multipart WebFlux, giới hạn **non-file part**, ngưỡng ghi file part ra disk, dung lượng file trên disk và tổng số part là các khái niệm khác nhau. Ví dụ thuộc tính Spring Boot 3.5:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=20MB
spring.webflux.multipart.max-parts=20
~~~

Đọc và xác minh theo đúng version của Boot và bộ multipart reader. Nếu ứng dụng sử dụng Servlet multipart thay vì WebFlux, hãy cấu hình **spring.servlet.multipart.***. Đảm bảo thư mục tạm có giới hạn và cleanup; giới hạn codec không thay cho antivirus, file type validation, quota của tài khoản hoặc storage policy.

### 2.3 Chặn tải ở tầng nghiệp vụ bằng semaphore/bulkhead

Số connection HTTP không phản ánh mức tài nguyên nghiệp vụ: một request gọi DB 5 lần có thể đắt hơn hàng trăm request static. Đặt một concurrency limit ở đoạn công việc cần bảo vệ, trả thông báo quá tải ngay khi không còn chỗ:

~~~java
private final Semaphore permits = new Semaphore(8, true);

@GetMapping("/process")
public ResponseEntity<?> process() {
    if (!permits.tryAcquire()) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .header(HttpHeaders.RETRY_AFTER, "1")
            .build();
    }

    try {
        return ResponseEntity.ok(service.performWork());
    } finally {
        permits.release();
    }
}
~~~

Fragment trên thuộc một controller có **service** đã được inject và imports Spring/Java tương ứng. **tryAcquire()** không chờ, giúp hệ thống từ chối sớm thay vì đẩy request vào queue vô hạn. **finally** bảo đảm trả permit cả khi business method ném exception. Dùng **503 Service Unavailable** hợp lý cho overload toàn hệ thống; **429 Too Many Requests** thường phù hợp giới hạn theo caller/rate policy. Chọn status và Retry-After theo hợp đồng.

**Cảnh báo về phạm vi:** semaphore trong một JVM chỉ giới hạn instance đó. Với nhiều pod, giới hạn toàn hệ thống cần điều phối cùng load balancer/quota hoặc distributed limit. Đừng cho rằng mỗi pod có 8 permits tương đương toàn cluster tối đa 8 operations.

## 3. Timeout là một họ cơ chế, không phải một nút bấm

| Timeout/deadline | Đo từ đâu | Khi hết thời gian | Nơi cấu hình |
| --- | --- | --- | --- |
| TCP connect timeout | Bắt đầu thiết lập kết nối | Không kết nối được | HTTP client connector |
| Connection-pool acquire timeout | Chờ lấy connection từ pool | Không lấy được slot | HTTP client pool |
| Read/response timeout | Chờ nhận response/data theo cơ chế connector | Đóng/hủy request outbound, error signal | RestClient/WebClient connector |
| Tổng thời hạn nghiệp vụ | Bắt đầu operation đến deadline | Hủy hoặc báo timeout toàn chuỗi | Business layer, Reactor timeout, request context |
| Servlet async timeout | Request async bắt đầu | Spring/Servlet dispatch lỗi timeout | spring.mvc.async.request-timeout, DeferredResult |
| Idle/keep-alive timeout | Kết nối rỗi không có request/bytes | Kết nối có thể đóng | Tomcat/Netty, proxy |
| Proxy upstream timeout | Gateway chờ backend | Gateway có thể trả 504 hoặc đóng | Reverse proxy/ingress |
| Graceful shutdown timeout | Application bắt đầu dừng | Giai đoạn chờ hoàn tất kết thúc | spring.lifecycle.timeout-per-shutdown-phase |

**Không đánh đồng các timeout**: **server.tomcat.connection-timeout=10s** không có nghĩa một API có quyền chạy tối đa 10s. **spring.mvc.async.request-timeout=10s** không tự giới hạn tất cả controller method đồng bộ. **WebClient responseTimeout(2s)** là chính sách ở HTTP client, khác deadline tổng của 5 bước nghiệp vụ.

Nếu browser có deadline 3 giây nhưng API gọi ba service mỗi service với read timeout 10 giây tuần tự, response có thể xuất hiện quá muộn. Thiết kế thời gian từ ngoài vào trong:

~~~text
Client deadline (ví dụ 5s)
        |
Gateway deadline (ví dụ 4.5s)
        |
API business budget (ví dụ 4s)
        |
DB + downstream calls + serialization
        |
Phần dự phòng cho trả response/cleanup
~~~

Các số trên chỉ minh họa quan hệ; phải tính cả network latency và thời gian xếp hàng. Phân phối một **deadline tổng** cho các call con tốt hơn cấu hình mỗi call với timeout riêng mà không xét ngân sách còn lại.

## 4. Timeout cho RestClient đồng bộ

Với **RestClient** sử dụng JDK HttpClient (Java 17), cấu hình connect timeout trên HttpClient và read timeout qua **JdkClientHttpRequestFactory**:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

HttpClient jdkClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .build();

JdkClientHttpRequestFactory factory =
    new JdkClientHttpRequestFactory(jdkClient);
factory.setReadTimeout(Duration.ofSeconds(4));

RestClient client = RestClient.builder()
    .baseUrl("https://catalog.example.org")
    .requestFactory(factory)
    .build();
~~~

Đây là **configuration fragment**, cần có remote server thật khi gọi. **connectTimeout** liên quan đến TCP establishment; **setReadTimeout** với factory này đặt timeout ở request HTTP mà factory tạo (phù hợp Spring 6.2). HTTP client khác, ví dụ Apache HttpComponents hoặc Jetty, có API cho pool lease, connect và response timeout riêng: không sao chép nhầm thuộc tính giữa chúng.

Trong servlet thread đồng bộ, một lời gọi RestClient bị treo có thể giữ một Tomcat worker. Vì vậy **mọi outbound call đáng kể nên có timeout hữu hạn**, quan sát được và phù hợp SLA. Nếu xảy ra lỗi, xử lý bằng exception mapping; không tự động retry mọi POST có side effect.

### Timeout của một nghiệp vụ nhiều bước

Ví dụ workflow phải hỏi cả profile và inventory. Nếu tổng ngân sách 3 giây, không nên cho mỗi call 3 giây nối tiếp. Một mẫu design là truyền **Instant deadline** hoặc **Duration remainingBudget** xuống các client method và điều chỉnh timeout thực tế cho bước tiếp theo. Với blocking calls, hủy thực thi cần khả năng interrupt/cancel từ client và service; **Future.cancel(true)** là yêu cầu ngắt cooperative, không bảo đảm mọi I/O ngừng ngay lập tức.

**Tránh** tạo new Thread hoặc ExecutorService không giới hạn mỗi request để "ép timeout". Chúng chỉ đẩy số công việc còn sống ra khỏi request thread, khiến shutdown và leak trở nên phức tạp.

## 5. Timeout cho WebClient dùng Reactor Netty

Với WebClient, có thể cấu hình HTTP client connector:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
    .responseTimeout(Duration.ofSeconds(4));

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.org")
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
~~~

**CONNECT_TIMEOUT_MILLIS** giới hạn thiết lập kết nối. **responseTimeout** của Reactor Netty gắn với hành vi nhận response, không tự bảo đảm mọi logic trước/sau network và mọi thao tác DB hoàn thành trong một tổng deadline.

Khi cần timeout cho **toàn reactive pipeline**:

~~~java
Mono<Book> result = webClient.get()
    .uri("/api/books/{id}", 7)
    .retrieve()
    .bodyToMono(Book.class)
    .timeout(Duration.ofSeconds(5));
~~~

**Book** là DTO đã định nghĩa ở ứng dụng. Reactor **timeout** phát lỗi nếu nguồn không phát tín hiệu đúng hạn theo semantics của operator; việc hủy subscription có thể truyền xuống HTTP connector và ngừng I/O. Nhưng task blocking do code tự chạy bên ngoài reactive pipeline có thể không tự dừng. Với **Flux** nhiều phần tử, timeout operator thường quan tâm khoảng chờ giữa các signals chứ không tương đương thời hạn tuyệt đối từ đầu tới cuối; nếu cần fixed total deadline, thiết kế deadline rõ ràng.

### Pool và connection saturation

WebClient mặc định có thể dùng các tài nguyên Reactor Netty dùng chung (event loops, connection pool). Khi tải cao, cần quan sát số **active/idle/pending connections**, acquire latency và timeout. Nếu tự tạo **ConnectionProvider** với **maxConnections**, **pendingAcquireMaxCount**, **pendingAcquireTimeout**, phải dùng singleton/shared provider hợp lý và đóng nó theo application lifecycle. Không tạo một connection pool mới cho mỗi request.

Một request outbound fail do pool acquire timeout khác với DNS/connect timeout và khác response timeout. Sự phân biệt này giúp biết cần mở pool, hạn chế lưu lượng, rút ngắn downstream, hay tăng tài nguyên.

## 6. Spring MVC: timeout trong request bất đồng bộ

Spring MVC có Servlet async processing thông qua **Callable<T>**, **DeferredResult<T>**, **WebAsyncTask<T>**, **SseEmitter** và **ResponseBodyEmitter**. Nó giải phóng servlet thread trong lúc chờ kết quả, nhưng một số công việc vẫn có thể chạy trên executor và các lần ghi response streaming là blocking I/O.

Cấu hình mặc định async request timeout:

~~~properties
spring.mvc.async.request-timeout=10s
~~~

Thuộc tính này áp dụng **Servlet MVC asynchronous request processing**, không áp dụng cho một controller đồng bộ bình thường hoặc toàn WebFlux. Nếu không đặt, default timeout phụ thuộc Servlet container/implementation.

Ví dụ một operation với **DeferredResult** và timeout callback:

~~~java
@GetMapping("/async")
public DeferredResult<ResponseEntity<String>> async() {
    DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(3_000L);

    result.onTimeout(() -> result.setErrorResult(
        new ResponseStatusException(
            HttpStatus.GATEWAY_TIMEOUT, "Upstream quá chậm")));

    service.startAsyncWork(result);
    return result;
}
~~~

Đoạn trên là **fragment minh họa** với **service** định nghĩa trong ứng dụng. **startAsyncWork** phải hoàn thành bằng **setResult(...)** hoặc **setErrorResult(...)**; không chờ đồng bộ ngay trong controller. Với DeferredResult timeout, setting error result làm Spring chạy async dispatch để xử lý lỗi. Callback **onCompletion** thích hợp để giải phóng dữ liệu/đăng ký liên quan; nhưng nó không đồng nghĩa hủy tức thời mọi background task.

Với **Callable**, có thể dùng **WebAsyncTask<T>** để cấu hình timeout riêng; đồng thời phải cấp **AsyncTaskExecutor** phù hợp. Spring MVC tài liệu cảnh báo default async executor không thích hợp cho production under load; nên cấu hình pool có giới hạn và backpressure rõ ràng nếu dùng async methods nhiều.

### Timeout thực sự hủy được công việc không?

Không mặc định. Một DeferredResult hết hạn chỉ hoàn tất phần HTTP-facing lifecycle; nếu bạn đã khởi chạy blocking DB call hoặc future không gắn cancellation thì nó có thể vẫn chạy. Thiết kế cancellation token, query timeout và task interruption ở các tầng liên quan, bảo đảm resource cleanup trong finally/onCompletion. Đừng để hàng ngàn công việc "mồ côi" tiếp tục sau khi client đã bỏ đi.

## 7. Phát hiện client ngắt kết nối trong Spring MVC

**Servlet API không cung cấp tín hiệu tức thời và đáng tin cậy cho mọi tình huống client ngắt kết nối.** Đặc biệt với response stream/SSE, server thường chỉ nhận biết khi cố ghi bytes lên socket và ghi bị lỗi. Một browser đóng tab không bảo đảm controller đồng bộ đang xử lý sẽ lập tức nhận exception.

Với **SseEmitter**, có thể đăng ký các callback:

~~~java
SseEmitter emitter = new SseEmitter(30_000L);

emitter.onCompletion(() -> {
    // Bỏ subscription, giải phóng tài nguyên của stream.
});

emitter.onTimeout(() -> {
    // Đánh dấu stream đã timeout, dọn dữ liệu liên quan.
});

emitter.onError(error -> {
    // Ghi metric phù hợp, không log stacktrace lặp vô hạn.
});
~~~

Code trên là **fragment** của API **org.springframework.web.servlet.mvc.method.annotation.SseEmitter**. Khi emit theo thời gian, gửi heartbeat SSE comment định kỳ để phát hiện client đã đi xa và tránh một số idle timeout:

~~~java
emitter.send(SseEmitter.event().comment("heartbeat"));
~~~

Lệnh send phải chạy trong logic streaming với lifecycle rõ ràng, xử lý **IOException** theo đúng quy ước. Theo Spring MVC reference, nếu **ResponseBodyEmitter/SseEmitter.send(...)** ném IOException do client rời đi thì servlet container sẽ kích hoạt error notification và Spring xử lý completion; application không cần tự gọi **complete()** hay **completeWithError()** ngay trong catch IOException. Tránh giữ emitter trong collection không có cơ chế remove để không rò memory.

Một mẫu quản lý subscription:

~~~text
Mở SSE: tạo emitter + register onCompletion/onTimeout/onError
        |
Đăng ký vào nguồn sự kiện
        |
Phát data hoặc heartbeat định kỳ
        |
Lỗi ghi / timeout / disconnect / server shutdown
        |
Ngừng subscription, xóa emitter khỏi registry, dọn task
~~~

**Heartbeat** không phải guarantee phát hiện disconnect trong mọi trạng thái mạng; nó giúp phát hiện bằng I/O. Khi nhiều người dùng SSE, tần suất heartbeat phải cân bằng giữa phát hiện nhanh và overhead.

## 8. WebFlux: cancellation, DataBuffer và tài nguyên reactive

Ở WebFlux, publisher trả cho framework đại diện vòng đời response:

~~~java
@GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return eventSource.stream()
        .map(item -> ServerSentEvent.<String>builder()
            .data(item)
            .build())
        .doFinally(signal -> {
            // signal có thể là CANCEL, ON_COMPLETE, ON_ERROR.
            metrics.recordTermination(signal.name());
        });
}
~~~

Ví dụ là **fragment**: cần một **eventSource** và **metrics** đã định nghĩa/inject, import **Flux**, **ServerSentEvent**, **MediaType**, **@GetMapping**. Nếu client ngắt kết nối, hủy subscription có thể tạo **SignalType.CANCEL** ở chuỗi publisher. **doFinally** thích hợp cho metric và cleanup; không tự hiểu một **CANCEL** là lỗi nghiệp vụ hay tự ghi lại HTTP response khi socket không còn.

Các chú ý quan trọng:
- **Publisher cancellation** phải truyền đến upstream/resource owner. Nếu đã gọi **subscribe()** thủ công trong controller, framework khó quản lý subscription đó; nên return Flux/Mono.
- Khi tự sử dụng **DataBuffer**, cần tuân theo lifecycle: tiêu thụ, chuyển tiếp hoặc release buffer đúng API, nhất là với pooled buffers ở Netty. Tránh giữ DataBuffer bên ngoài request.
- **collectList()**, **cache()**, **buffer()** không giới hạn trên stream dài hạn là nguyên nhân gây tăng RAM; dùng xử lý theo phần tử và các toán tử bounded.
- Code **Thread.sleep**, JDBC đồng bộ và các thao tác block lâu trên Netty event-loop làm toàn bộ các connection dùng loop đó bị ảnh hưởng. Nếu buộc tích hợp API blocking, offload có kiểm soát bằng **Schedulers.boundedElastic()** và giới hạn concurrency; không coi offload là giải pháp thay việc chuyển sang API async phù hợp.
- Connection client đã đóng không có nghĩa background work vốn được submit cho executor tự bị hủy; quản lý task lifecycle và deadline ở tầng sở hữu công việc.

### Trường hợp response body lớn

Nếu endpoint trả hàng triệu record, đừng trả **Mono<List<BigRecord>>** chứa tất cả và tăng maxInMemorySize vô hạn. Khi contract cho phép, thiết kế stream NDJSON/SSE hoặc phân trang; giới hạn kích thước mỗi phần tử. Nếu bắt buộc trả một JSON array lớn, phải phân tích buffering, time-to-first-byte và giới hạn memory đúng codec/server/client.

## 9. Graceful shutdown: dừng server khác gì ngắt process ngay?

**Graceful shutdown** cho phép các request đang chạy có một khoảng thời gian hoàn tất trong lúc server ngừng nhận những request mới. Với Spring Boot **3.5**, graceful shutdown được **bật mặc định** cho embedded Tomcat, Jetty, Reactor Netty và Undertow; có thể khai báo tường minh để dễ đọc cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring thực hiện shutdown khi **ApplicationContext đóng**, trong một pha sớm của quá trình dừng **SmartLifecycle** beans. Thời gian cấu hình là **grace period cho mỗi pha** lifecycle, không phải một "request timeout = 20s" chung. Khi hết thời gian chờ, framework sẽ tiếp tục shutdown, nên công việc dài hơn chưa chắc hoàn tất.

### Timeline triển khai một pod

~~~text
T0: orchestrator yêu cầu instance dừng (SIGTERM)
      |
      +--> Load balancer/ingress cần ngừng route traffic mới
      |
      +--> Spring ApplicationContext bắt đầu đóng
              |
              +--> web server graceful shutdown:
              |       không nhận request mới theo cách của server
              |       đợi request hiện hữu trong grace window
              |
              +--> SmartLifecycle beans và tài nguyên khác dừng
              |
              +--> close data sources / HTTP client pools / executors
      |
T_deadline: hết shutdown grace hoặc bị hệ thống ngoài cưỡng bức
      |
      v
Container/process kết thúc
~~~

Cách từ chối request mới phụ thuộc server: Tomcat, Jetty, Reactor Netty thường ngừng nhận ở network layer; Undertow có thể trả **503** trong giai đoạn shutdown. Không viết test kỳ vọng **mọi server đều trả HTTP 503** khi graceful shutdown.

**SIGKILL**, process crash, mất điện, JVM bị kill cưỡng bức hay container hết termination grace không cho ứng dụng cơ hội cleanup đầy đủ. Trong IDE, nút Stop có thể kết thúc ngay tùy cách gửi tín hiệu. Do đó graceful shutdown là **best effort với deadline**, không phải cam kết hoàn tất mọi workflow hay đảm bảo exactly-once.

### Phải phối hợp với orchestrator

Trong Kubernetes hoặc hệ thống orchestrator tương tự:
- Đặt readiness false và ngừng định tuyến lưu lượng mới đến instance đang drain.
- Kiểm tra propagation delay của endpoint updates/proxy; đôi lúc request vẫn đang trên đường.
- Chọn **terminationGracePeriodSeconds** lớn hơn hoặc đủ bao quát cửa sổ Spring graceful shutdown, thời gian dọn tài nguyên, quá trình stop container và phần dự phòng.
- Đặt request timeout, downstream budget và shutdown window nhất quán. Nếu request hợp pháp có thể chạy 2 phút nhưng grace chỉ 20 giây, request đó có nguy cơ bị cắt.
- Với SSE/WebSocket stream dài hạn, cần chính sách yêu cầu reconnect hoặc đóng có kiểm soát; chờ stream vô hạn thì graceful window cũng không thể kết thúc một cách trọn vẹn.
- Nếu công việc phải survive restart, ghi vào durable job queue/database để instance khác tiếp tục; không giữ toàn bộ trạng thái quan trọng chỉ trong memory.

Một pod "đã đóng cổng" không đồng nghĩa job nền đã hoàn thành hoặc transaction đã commit. Đưa trạng thái công việc vào kho durable và thiết kế idempotency/transaction boundary thích hợp.

## 10. Dừng executor và tài nguyên do ứng dụng tự quản lý

Spring quản lý vòng đời nhiều bean và embedded server, nhưng nếu ứng dụng tự tạo ExecutorService, scheduled task, client connector, file handle hay message consumer thì cũng cần owner chịu trách nhiệm dọn.

Ví dụ **ThreadPoolTaskExecutor** có số thread/queue hữu hạn:

~~~java
@Configuration
public class WorkerPoolConfig {
    @Bean("workExecutor")
    public ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("work-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(15);
        return executor;
    }
}
~~~

Imports: **org.springframework.context.annotation.Bean**, **Configuration**, **org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor**.

- **core/max pool size** hạn chế workers; **queueCapacity** hạn chế pending tasks.
- Khi pool/queue bão hòa, executor có thể từ chối task; caller phải xử lý **TaskRejectedException** hoặc policy tương ứng thay vì âm thầm chấp nhận công việc.
- **waitForTasksToCompleteOnShutdown(true)** yêu cầu executor chờ các task đang chạy/đã queue khi đóng, nhưng không tự bảo đảm đủ thời gian của toàn quá trình shutdown và các beans khác.
- **awaitTerminationSeconds(15)** giới hạn thời gian chờ của executor khi shutdown; cần cân đối với Spring lifecycle shutdown budget và orchestrator deadline.
- Nếu có công việc chạy vô hạn hoặc không tôn trọng interruption, shutdown vẫn có thể bị kéo dài/hết hạn. Thiết kế task có deadline, cancellation và checkpoint; dùng durable queue khi mất task là không chấp nhận được.

Đoạn này là **fragment cấu hình**, có thể được đưa vào ứng dụng Spring Boot. Không tự thêm một executor như trên nếu ứng dụng không thực sự cần xử lý bất đồng bộ. Trong một WebFlux controller thuần non-blocking, không dùng thread pool để bọc mọi lời gọi mà không xét nhu cầu.

### Hủy subscription và consumer

Một WebSocket/SSE subscription hoặc message consumer chạy nền phải có logic **stop requesting more work**, hủy subscription, đóng file/network resources và xử lý in-flight messages trước khi ngừng hoàn toàn. Với Reactive Streams, giữ **Disposable** hoặc quản lý publisher lifecycle tại một component đúng ownership; gọi **dispose()** khi stop và bảo đảm close/rollback khi hủy. Không giữ đối tượng subscription trong static field không được cleanup.

## 11. Demo chạy được: hạn chế công việc đồng thời và graceful shutdown (Spring MVC)

Demo Java 17 dùng Spring Boot 3.5.0, embedded Tomcat và một **Semaphore** nhằm cho tối đa **hai thao tác business đang thực thi** tại một thời điểm trong JVM. Nếu có thêm request trong lúc cả hai permits được giữ, server trả **503 + Retry-After: 1**. Request có thời gian giả lập quá dài bị từ chối bằng 400 trước khi lấy permit. Phần shutdown để Spring Boot thực hiện theo **server.shutdown=graceful**.

Cấu trúc thư mục:

~~~text
resource-limits-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ResourceLimitsApplication.java
    │   │   └── WorkController.java
    │   └── resources/application.properties
    └── test/java/demo/WorkControllerTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>resource-limits-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**src/main/java/demo/ResourceLimitsApplication.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceLimitsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceLimitsApplication.class, args);
    }
}
~~~

**src/main/java/demo/WorkController.java**:

~~~java
package demo;

import java.util.concurrent.Semaphore;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class WorkController {

    // Chỉ giới hạn business work trong instance này.
    private final Semaphore slots = new Semaphore(2, true);

    public record WorkResult(String status, long durationMs) {}

    @GetMapping("/work")
    public ResponseEntity<WorkResult> work(
            @RequestParam(name = "ms", defaultValue = "100") long ms) {

        if (ms < 0 || ms > 2_000) {
            return ResponseEntity.badRequest().build();
        }

        if (!slots.tryAcquire()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .build();
        }

        try {
            // Chỉ mô phỏng blocking work để thấy tác động dưới tải.
            Thread.sleep(ms);
            return ResponseEntity.ok(new WorkResult("completed", ms));

        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .build();

        } finally {
            slots.release();
        }
    }
}
~~~

**Thread.sleep** có chủ đích chỉ để học cách giữ servlet worker. Trong production thay bằng logic nghiệp vụ thật, với timeout/transaction/cancellation và hạn chế DB/downstream riêng. Semaphore (fairness=true) áp dụng theo JVM và chỉ bao quanh work method; nó không hạn chế mọi HTTP endpoint hoặc toàn cluster. Đối với một ứng dụng thật, xem xét bulkhead ở service layer thay vì lặp semaphore trong nhiều controller.

**src/main/resources/application.properties**:

~~~properties
server.port=8080

# HTTP/Servlet resource boundaries cho demo.
server.tomcat.threads.max=20
server.tomcat.max-connections=100
server.max-http-request-header-size=16KB
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

# Chỉ có tác dụng trên MVC async request, nếu ứng dụng dùng.
spring.mvc.async.request-timeout=10s

# Chờ request hiện hữu trong một shutdown phase.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

Cấu hình graceful timeout ở đây **10s** vì demo chỉ chạy work tối đa 2s; khi ứng dụng thật có request hợp pháp lâu hơn cần điều chỉnh theo SLA và orchestrator. **server.tomcat.threads.max=20** không giới hạn business work ở hai: limit business work được thực hiện bằng semaphore.

**src/test/java/demo/WorkControllerTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(WorkController.class)
class WorkControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void successfulWorkReturnsKnownJson() throws Exception {
        mvc.perform(get("/api/work").param("ms", "0"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                org.springframework.http.MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value("completed"))
            .andExpect(jsonPath("$.durationMs").value(0));
    }

    @Test
    void invalidDurationRejectedBeforeWork() throws Exception {
        mvc.perform(get("/api/work").param("ms", "2001"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Hai test này xác minh **contract thành công 200/JSON** và **giới hạn input trả 400**. Chúng không chứng minh hệ thống xử lý đúng concurrent overload, timeout network hoặc graceful shutdown: những thứ đó cần integration/load/lifecycle tests vì MockMvc không mở socket thật.

Chạy tại thư mục gốc:

~~~bash
mvn test
mvn spring-boot:run
~~~

Khi dependencies tải thành công, hai JUnit test dự kiến pass. Trong terminal khác:

~~~bash
curl -i "http://localhost:8080/api/work?ms=0"
~~~

Phần body trả về từ controller, sau khi request thành công:

~~~json
{"status":"completed","durationMs":0}
~~~

Status kỳ vọng là **HTTP 200**, header **Content-Type: application/json**. Lệnh với ms không hợp lệ:

~~~bash
curl -i "http://localhost:8080/api/work?ms=2001"
~~~

Kỳ vọng **HTTP 400 Bad Request**; phần body lỗi cụ thể do Spring Boot error handling định nghĩa, không cam kết JSON body trong bài.

### Kiểm tra overload một cách có kiểm soát

Mở hai terminal gửi request giữ permit khoảng 2 giây:

~~~bash
curl -i "http://localhost:8080/api/work?ms=2000"
~~~

Ngay khi cả hai request đang chạy, gọi request thứ ba. Khi hai permits đều đang bị giữ, request thứ ba sẽ nhận **HTTP 503** và **Retry-After: 1**. Nếu request thứ nhất đã hoàn tất hoặc chưa thực sự chiếm permit khi request thứ ba đến, request thứ ba có thể thành công; thứ tự/đếm chính xác phụ thuộc thời điểm thử, vì vậy không giả định một số cố định trong test dùng terminal thủ công.

Trong môi trường test tự động có thể dùng **barrier/latch** và một server thật để kiểm chứng deterministically thời điểm hai permits đã được lấy. Tránh dùng chỉ một **Thread.sleep(100)** để hy vọng các request luôn song song; cách đó dễ flake trên CI.

### Kiểm tra graceful shutdown

Khởi động server với **mvn spring-boot:run**, phát request **ms=2000**, gửi SIGTERM tới đúng Java process khi request đang thực thi, và quan sát liệu nó hoàn tất trước khi hết cửa sổ 10s. Trong deployment thật kiểm tra qua orchestrator, traffic routing và readiness của pod. **Dùng Ctrl+C hoặc Stop ở IDE không phải phép thử tương đương trong mọi môi trường** vì cách đóng process có thể khác SIGTERM.

**Không cố diễn giải một lần thử bằng curl thành bảo đảm tuyệt đối**: nếu process bị cưỡng bức, chưa kịp tiếp nhận SIGTERM, reverse proxy timeout hoặc request vẫn đang trên đường, kết quả có thể khác. Graceful shutdown cần được test cùng load balancer, thread pools, DB transaction và job background thực tế.

## 12. Logging, metrics, tracing và cảnh báo

Để biết hệ thống bị giới hạn ở đâu, nên đo ít nhất:

| Metric / tín hiệu | Giải thích |
| --- | --- |
| HTTP active requests và latency p50/p95/p99 | Tải và tail latency đang tăng hay không |
| 4xx/5xx, 429, 503, 504 | Phân biệt input/rate limit, overload, gateway timeout |
| Tomcat threads busy/active và max | Server worker pool có bão hòa |
| Open/idle connections và accept backlog | Connection pressure, giữ socket nhàn rỗi |
| JVM heap, GC pause, direct memory | Buffer/JSON/DataBuffer gây memory pressure |
| Executor active threads, queue depth, rejected tasks | Nền xử lý đang quá tải |
| DB pool active/idle/pending và query timeout | Bottleneck downstream DB |
| HTTP outbound pool active/pending, connect/response timeout | Dependency remote gây tắc nghẽn |
| WebSocket/SSE active sessions, drops, termination reasons | Streaming leak hoặc disconnect |
| Shutdown duration và unfinished work | Có vượt graceful window hay không |

Spring Boot Actuator/Micrometer có thể cung cấp metrics theo instrumentation và backend được cấu hình, nhưng không phải mọi metric trên đều tự xuất hiện nếu ứng dụng chưa bật instrumentation tương ứng. Phân biệt **request canceled by client** với **server 500** trong log/metrics; broken pipe sau khi browser rời đi không có cùng ý nghĩa với lỗi business trước lúc trả response.

### Nguyên tắc log khi disconnect/timeout

- Ghi **request/correlation ID**, endpoint, duration, status/result và timeout category.
- Không log nguyên access token, full request body, file upload hoặc dữ liệu cá nhân.
- Một SSE/WebSocket disconnect bình thường không cần stacktrace ERROR lặp lại hàng nghìn lần; thống kê metric hợp lý.
- Đừng nuốt **InterruptedException**; khôi phục interrupt flag khi bắt tại blocking code và dừng sớm.
- Không coi **timeout** là dấu hiệu downstream chắc chắn đã rollback. Một POST từ client có thể đã được server thực thi thành công trước khi response bị mất; retry cần idempotency key.

## 13. Thiết kế kiểm thử cho failure modes

| Failure mode | Cách mô phỏng | Điều phải chứng minh |
| --- | --- | --- |
| Nhiều request đồng thời | Load test có concurrency rõ, test barrier/latch | Từ chối sớm, queue có trần, phục hồi sau overload |
| Request body lớn | Payload vượt multipart/codec limit | Từ chối phù hợp, disk/memory không tăng vô hạn |
| Downstream không nhận connection | Mock server unreachable/DNS/socket setup | Connect timeout hữu hạn, báo lỗi đúng |
| Downstream trả rất chậm | MockWebServer/WireMock với response delay | Response timeout, total deadline và cleanup |
| Pool outbound cạn | Giới hạn connection pool và tạo nhiều requests | Pending acquire bound, không xếp hàng vô hạn |
| Client đóng SSE/browser tab | HTTP client cancel/close socket | Subscription/task được release, metric phù hợp |
| Client hết hạn trước server | Proxy timeout ngắn hơn API | Không tiếp tục tốn tài nguyên vô ích khi có thể hủy |
| Nhận SIGTERM khi có request đang chạy | Integration/deployment test | Không nhận thêm request mới, in-flight trong grace hoàn tất nếu kịp |
| SIGKILL ngay giữa transaction | Chaos/drill có dữ liệu test | Durable state/idempotency giúp phục hồi |
| WebSocket/SSE khi triển khai phiên bản mới | Mở session rồi drain pod | Client reconnect, subscribe lại, state đồng bộ |

**Lưu ý trạng thái HTTP khi hủy:** đôi khi server không thể gửi bất kỳ status nào vì socket đã đóng. Trong log phía proxy có thể có mã vendor-specific cho client closed request, nhưng application không nên tự cố trả một "status ngắt kết nối" lên connection đã mất. Ở Reactor, **CANCEL** là signal publisher; nó không phải HTTP status.

Một bài test graceful shutdown đáng tin phải phân biệt các thời điểm: request thật sự đã được server chấp nhận, SIGTERM được nhận, server ngừng routing mới, request cũ hoàn thành/timeout, tài nguyên tắt. Nếu chỉ gửi SIGTERM rồi kiểm tra process exit code, chưa kiểm chứng đặc tính graceful.

## 14. Các lỗi phổ biến cần tránh

1. **Đặt server.tomcat.connection-timeout rồi tưởng API đã có business deadline.** Đây là timeout kết nối, không thay thế outbound read timeout và tổng ngân sách request.
2. **Tăng threads.max khi DB pool quá nhỏ.** Thêm nhiều servlet worker có thể chỉ tăng số luồng chờ DB và làm p99 xấu hơn.
3. **Để queue executor hoặc pending acquire vô hạn.** Quá tải nhỏ biến thành hàng nghìn request treo lâu thay vì thông báo từ chối sớm.
4. **Chỉ giới hạn upload tại client.** Kẻ gọi khác có thể bypass giao diện; cần kiểm server/proxy/storage.
5. **Tăng WebFlux maxInMemorySize để chữa stream lớn.** Nếu contract cho phép hãy chuyển sang phân trang/stream, giới hạn per-record.
6. **Dùng Thread.sleep/JDBC đồng bộ trên Netty event-loop.** Một tác vụ block ảnh hưởng nhiều kết nối khác.
7. **Gọi subscribe() thủ công ở controller reactive.** Mất cancellation/error propagation từ WebFlux, có thể tạo việc nền mồ côi.
8. **Coi DeferredResult timeout là task nền đã bị cancel.** Cần owner và cancellation/interrupt/query timeout rõ ràng.
9. **Chờ một callback disconnect tức thời trong Spring MVC.** Servlet không có notification đáng tin cho mọi remote close; I/O write/heartbeat giúp phát hiện.
10. **Gọi completeWithError() trong catch IOException của SseEmitter một cách vô điều kiện.** Spring/container có lifecycle error notification riêng.
11. **Cho mọi in-flight stream sống mãi trong graceful shutdown.** Cần policy drain/reconnect và thời hạn hợp lý.
12. **Coi graceful shutdown thay durable queue.** Process vẫn có thể bị kill, cần chống mất/trùng việc.
13. **Retry mọi lỗi timeout.** Timeout có thể xảy ra sau khi server hoàn tất side effect; retry cần idempotency.
14. **Không kiểm thử dưới proxy/load balancer.** Ứng dụng có thể chạy đúng khi localhost nhưng chết do gateway idle timeout hoặc termination grace không khớp.

## 15. Checklist vận hành trước khi triển khai

- [ ] Biết resource bottleneck thật: CPU, JVM memory, Tomcat threads, Reactor Netty pool, DB connections hay downstream.
- [ ] Đã đặt limit cho HTTP connections/headers, request/multipart/codec buffers và business concurrency theo công suất thực.
- [ ] Không có queue hoặc buffer tăng không giới hạn trên những đường xử lý nhiều traffic.
- [ ] Outbound HTTP có connect/read/response timeout hữu hạn và policy retry có kiểm soát.
- [ ] Tổng business deadline tương thích với gateway timeout và SLA; không cho mọi bước downstream dùng toàn bộ deadline.
- [ ] Streaming/SSE/WebSocket có cleanup, heartbeat phù hợp, cancellation và reconnect strategy.
- [ ] Spring MVC async có executor phù hợp và timeout; WebFlux không block event-loop.
- [ ] Graceful shutdown và thời gian dừng của orchestrator đủ cho request hợp pháp có giới hạn thời gian.
- [ ] Background tasks, thread pools, DB pools, network clients có lifecycle owner và dọn khi ApplicationContext đóng.
- [ ] Metrics/logs phân biệt overload, rate limit, timeout, disconnect, shutdown và lỗi nghiệp vụ.
- [ ] Đã kiểm thử tình huống overload, remote timeout, client abort và SIGTERM trong môi trường có proxy.

## Tài liệu chính thức

- [Spring Boot 3.5 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework 6.2 – Spring MVC Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework – Reactive Core và codec buffer limits](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework – WebClient Configuration, resources và timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [JdkClientHttpRequestFactory Javadoc (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html)
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html)
