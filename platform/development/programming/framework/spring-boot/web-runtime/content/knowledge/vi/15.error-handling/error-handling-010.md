# Lỗi khi phản hồi đã commit hoặc luồng dữ liệu đã bắt đầu trong Spring Boot WebFlux

## 1. Vấn đề: vì sao server báo lỗi mà client vẫn nhìn thấy HTTP 200?

Một HTTP response có thể đã được gửi đi một phần trước khi lỗi xảy ra. Ví dụ một endpoint Spring WebFlux phát Server-Sent Events (SSE): server đã gửi HTTP 200, Content-Type: text/event-stream cùng hai sự kiện dữ liệu, sau đó nguồn dữ liệu phát lỗi. Khi status và headers đã commit, server không thể thu hồi response cũ và thay bằng một HTTP 500 kèm JSON lỗi thông thường.

Đây là điểm khác biệt quan trọng giữa lỗi xảy ra trước khi HTTP response commit và lỗi khi body đang streaming.

Các nguyên tắc:

- Commit là thời điểm status và headers đã được cố định để phản hồi. Sau thời điểm này, đổi status không còn khả thi trên cùng response.
- Body bắt đầu được ghi thường kéo theo commit; nhưng response có thể commit ngay cả khi không có body, chẳng hạn khi setComplete.
- Lỗi trước commit có thể được ánh xạ thành HTTP 4xx/5xx bởi exception handling phù hợp.
- Lỗi sau commit có thể dẫn đến partial body, stream reset, connection close hoặc một thông báo lỗi trong body nếu giao thức ứng dụng đã định nghĩa cách biểu diễn nó.
- HTTP 200 không nhất thiết có nghĩa toàn bộ stream thành công. Client cần biết đã nhận đủ dữ liệu hay chưa.
- Không phải mọi exception đều được chữa bằng @RestControllerAdvice; callback xử lý lỗi không thể tạo lại những HTTP bytes đã gửi.

Bài dành cho Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+ với Spring WebFlux trên Reactor Netty. Ngoài lý thuyết, bài có một project Gradle hoàn chỉnh, ví dụ SSE lỗi trước/sau commit, kiểm thử WebTestClient, StepVerifier và MockServerHttpResponse.

## 2. Phân biệt khởi tạo, commit, streaming và completion

Một request có thể đi qua:

~~~text
HTTP request
  -> tìm handler
  -> tính toán kết quả hoặc tạo Mono/Flux
  -> cấu hình HTTP status + headers
  -> commit response
  -> encode / write / flush body
  -> hoàn tất hoặc error / cancel
~~~

Đây là chuỗi khái niệm, không phải một stack trace tuyệt đối. Các Publisher có thể chạy bất đồng bộ; encoder, HTTP server, proxy và client có buffering riêng.

| Trạng thái | Thay status/header? | Kết quả xử lý lỗi |
| --- | --- | --- |
| Chưa commit, chưa ghi dữ liệu | Thường còn khả thi | Có cơ hội trả 400/404/500 và JSON/ProblemDetail |
| Trong beforeCommit callback | Có thể điều chỉnh theo contract của callback | Tùy pipeline và việc callback hoàn tất |
| Headers đã commit, chưa ghi body | Không đổi status trên wire | Không tạo status khác trên cùng response |
| Đang ghi SSE/NDJSON/binary | Không đổi status | Lỗi in-band nếu format cho phép; nếu không, terminate stream |
| Body ghi dang dở, I/O lỗi | Không | Partial content, reset/close hoặc lỗi phía client |
| Response đã hoàn tất | Không | Không thể ghi thêm error response |

Commit của Spring response khác với việc client đã thực sự nhận bytes. Một proxy có thể buffer và gửi sau; client có thể mất mạng dù server vừa hoàn tất write. Vì thế phải phân biệt trạng thái Spring, trạng thái transport và xác nhận ở phía client.

### Ví dụ HTTP/1.1

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Transfer-Encoding: chunked

event: item
data: one

event: item
data: two

~~~

Nếu nguồn dữ liệu tiếp theo lỗi, không được nối một phản hồi HTTP thứ hai:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{"error":"upstream failed"}
~~~

vào giữa body cũ. Đó không phải cách hợp lệ để thay status đã gửi.

HTTP/2 dùng HEADERS/DATA frames và reset stream thay vì wire text của HTTP/1.1, nhưng nguyên tắc vẫn giống: response headers đã gửi thì không thể quay lại đổi status thành một phản hồi khác.

## 3. ServerHttpResponse.isCommitted() có ý nghĩa gì?

Trong WebFlux:

~~~java
boolean committed = exchange.getResponse().isCommitted();
~~~

org.springframework.http.server.reactive.ServerHttpResponse cho biết response đã commit theo trạng thái framework hay chưa. Dùng API này để quan sát và phân loại lỗi, không coi nó là cơ chế rollback.

API thay status thường gặp:

~~~java
ServerHttpResponse response = exchange.getResponse();

if (!response.isCommitted()) {
    boolean accepted =
            response.setStatusCode(HttpStatus.BAD_GATEWAY);
    // Nếu có concurrency, vẫn cần xem kết quả accepted.
}
~~~

Đây là snippet trong một class có ServerWebExchange và imports. setStatusCode(HttpStatusCode) trả boolean, không bảo đảm thay đổi đã được ghi nếu response đã commit hoặc đang commit đồng thời.

Không nên gọi getHeaders().set rồi tin rằng client sẽ thấy header mới sau commit. Header HTTP đã đi ra khỏi application không thể sửa bằng việc thay đổi một Java map.

### Một cạm bẫy

Một lỗi upstream có thể xuất hiện trong doOnError khi isCommitted() là true. Điều này không có nghĩa error handler đã bị gọi quá muộn vì bug của Spring; nó có thể đơn giản là phần body trước đó đã được stream thành công và status đã được gửi.

## 4. beforeCommit(): điểm mở rộng đúng thời điểm

Spring WebFlux hỗ trợ:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Response-Phase", "committing");
    return Mono.empty();
});
~~~

Đoạn này cần nằm trong method có exchange và Reactor Mono. beforeCommit đăng ký callback được thực thi trước response commit.

Nó hữu ích khi muốn:

- Gắn response metadata được xác định trước commit.
- Điều chỉnh header chung theo chính sách ứng dụng.
- Ghi dấu mốc quan sát trên response phục vụ test/debug.
- Đăng ký logic nhỏ, non-blocking ngay trước commit.

Nó không giúp:

- Thu hồi status hoặc body đã phát.
- Đổi status từ 200 sang 500 sau SSE event đầu.
- Viết lại một JSON body đã serialize và flush.
- Chờ database bằng Thread.sleep hoặc .block().
- Chứng minh phía client đã nhận dữ liệu.

Nếu beforeCommit callback tự phát lỗi, quá trình commit có thể thất bại. Hãy giữ callback gọn, không blocking và test riêng cho logic phức tạp.

## 5. Luồng xử lý lỗi ở tầng WebFlux

~~~mermaid
flowchart TD
    A["Reactor Netty / HTTP request"] --> B["HttpHandler, WebFilter chain"]
    B --> C["DispatcherHandler"]
    C --> D["Controller trả Mono/Flux"]
    D --> E["HandlerResultHandler / HttpMessageWriter"]
    E --> F{"Đã commit?"}
    F -->|"Chưa"| G["Exception handler có thể tạo status/body lỗi"]
    F -->|"Rồi"| H["Status/headers không thay được"]
    H --> I{"Có format lỗi trong body?"}
    I -->|"Có"| J["SSE event lỗi hoặc NDJSON error envelope"]
    I -->|"Không"| K["Error signal / reset / đóng stream"]
~~~

Trong ứng dụng thực, lỗi có thể phát sinh trước mapping, khi decode body, trong filter, trong controller, khi serialize response, ở upstream service hoặc ở transport. Đường error handling có thể thuộc @ExceptionHandler, WebExceptionHandler, Boot reactive error handler hoặc Reactor Netty.

Điểm chung: error handler chỉ có thể tạo một status và body mới nếu response chưa ở trạng thái cản trở việc đó.

### Vai trò từng thành phần

| Thành phần | Vai trò |
| --- | --- |
| DispatcherHandler | Điều phối request WebFlux |
| RequestMappingHandlerAdapter | Gọi method controller và tạo HandlerResult |
| HandlerResultHandler | Chọn cách xử lý giá trị trả về |
| HttpMessageWriter/Encoder | Ghi response body từ Java objects |
| ServerHttpResponse | Status, headers, cookies, body publisher, commit |
| WebFilter | Middleware reactive, có thể log error/cancellation |
| @RestControllerAdvice | Xử lý một số lỗi gắn với annotated controller |
| WebExceptionHandler | Xử lý error signal trong WebHandler chain |
| Boot reactive error handler | Cơ chế xử lý lỗi mặc định của Boot khi còn có thể |
| Reactor Netty | Ghi bytes và quản lý transport/channel |

Một lỗi đã được onErrorResume chuyển thành item hợp lệ **không còn là reactive onError** ở phía sau operator đó. Vì vậy nếu muốn ghi metrics về upstream error, phải đặt observation đúng chỗ.

## 6. Lỗi trước commit: ánh xạ HTTP status vẫn khả thi

Ví dụ một controller chỉ tạo response sau khi kiểm tra báo cáo có tồn tại:

~~~java
@GetMapping("/reports/{id}")
public Mono<ResponseEntity<ReportDto>> find(
        @PathVariable("id") String id) {

    return reportService.findById(id)
            .switchIfEmpty(Mono.error(
                    new ReportNotFoundException(id)))
            .map(ResponseEntity::ok);
}
~~~

Đây là method minh họa, cần reportService, ReportDto và exception class. Với kết quả Mono.empty hoặc lỗi trước khi response body bắt đầu, @ExceptionHandler phù hợp có thể trả 404 với JSON hợp lệ.

Nên thực hiện trước streaming:

1. Validation của input, Content-Type và tham số.
2. Authentication và authorization.
3. Kiểm tra file/resource có tồn tại.
4. Kiểm tra upstream bắt buộc có thể truy cập.
5. Xác định status, content type, caching, Content-Disposition.
6. Chọn stream format cùng hành vi lỗi nếu nguồn hỏng giữa chừng.

### Giới hạn

Một Mono<ResponseEntity<Flux<Item>>> giúp quyết định metadata **trước khi ghi Flux body**, nhưng không chứng minh các item trong Flux sẽ không lỗi. Nếu Flux đã phát dữ liệu, status của ResponseEntity vẫn không thể thay đổi.

## 7. Lỗi sau commit: @ExceptionHandler không thể chữa như lỗi trước commit

Ví dụ source stream:

~~~java
Flux<String> source = Flux.concat(
        Flux.just("one", "two"),
        Flux.error(new IllegalStateException("upstream unavailable")));
~~~

Đây là Reactor Publisher hợp lệ với import Flux, không tự tạo một HTTP response. Khi biến nó thành response text/event-stream, các item đầu có thể được encode và flush trước khi error cuối xuất hiện.

Nếu response đã commit HTTP 200, handler sau không biến nó thành 500 JSON như một request chưa ghi body:

~~~java
@ExceptionHandler(IllegalStateException.class)
public ResponseEntity<String> failed(
        IllegalStateException exception) {
    return ResponseEntity.status(500).body("failed");
}
~~~

Snippet này chỉ phù hợp khi error được xử lý ở thời điểm và phạm vi cho phép. Trong streaming response đã commit, framework không thể gửi lại status mới.

Điều đó đúng kể cả khi source lỗi từ database, custom JSON serializer, WebClient upstream hoặc client disconnect.

## 8. WebExceptionHandler có nên cố sửa response đã commit không?

org.springframework.web.server.WebExceptionHandler có API:

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

Một custom handler nâng cao phải phân biệt:

~~~java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(ex);
}

// Chỉ khi chưa commit mới có thể xem xét
// thiết lập status và body lỗi phù hợp.
~~~

Đây là code minh họa một nhánh trong method handle, không phải implementation đầy đủ.

Propagate lỗi khi response đã commit thường phù hợp hơn là cố viết một response HTTP thứ hai. Cách xử lý kết nối/stream tiếp theo phụ thuộc server và transport, không có lời hứa client sẽ thấy HTTP 500.

Không thêm WebExceptionHandler global chỉ để “bắt cho hết lỗi”. Thứ tự @Order, Boot default error handler, security filters và khả năng response đã commit cần được hiểu trước khi tùy chỉnh.

## 9. Ba chiến lược sau khi phát hiện lỗi streaming

### Chiến lược A: kiểm tra hoặc tạo kết quả trước commit

Với kết quả nhỏ, hữu hạn:

~~~java
public Mono<List<ItemDto>> items() {
    return itemService.loadAll()
            .collectList();
}
~~~

Nếu Publisher nguồn lỗi trước collectList hoàn tất, controller chưa có danh sách thành công để ghi nên thường còn khả năng trả HTTP error. Nhưng collectList tốn memory, tăng latency, mất streaming; nó không phù hợp với stream vô hạn và không bảo đảm serialization về sau không lỗi.

Nếu cần bảo đảm representation hoàn chỉnh, đôi khi phải tạo/validate/serialize nội dung ở vùng nhớ hoặc file tạm có giới hạn trước khi bắt đầu response. Phải thiết kế size limit, timeout, checksum và backpressure phù hợp.

### Chiến lược B: lỗi bên trong giao thức ứng dụng

SSE và NDJSON có thể định nghĩa event hoặc record lỗi, ví dụ:

~~~text
event: item
data: one

event: item
data: two

event: stream-error
data: UPSTREAM_UNAVAILABLE

~~~

Response có thể vẫn HTTP 200, nhưng event stream-error biểu thị lỗi **nghiệp vụ của stream**. Client phải hiểu contract này và không đánh dấu thành công chỉ vì request ban đầu được accept.

Với NDJSON, mỗi dòng là JSON độc lập:

~~~json
{"type":"item","id":"1","value":"one"}
{"type":"item","id":"2","value":"two"}
{"type":"error","code":"UPSTREAM_UNAVAILABLE"}
~~~

Đây là ba JSON values riêng trên ba dòng, không phải một document application/json có cấu trúc array/object duy nhất. Nếu client cần biết stream đã hoàn tất, có thể yêu cầu dòng type=complete hoặc event complete.

### Chiến lược C: propagate lỗi và terminate stream

Khi binary download đã ghi một phần, mạng đã hỏng hoặc format không hỗ trợ error message:

- Để reactive error signal propagate.
- Log/metric lỗi và thời điểm response commit.
- Để transport kết thúc/reset connection theo khả năng server.
- Client đánh dấu partial output/incomplete.
- Với file quan trọng, chỉ dùng file sau khi verify length/checksum.
- Thiết kế retry/resume với checkpoint hoặc range/ETag khi thích hợp.

Không chèn JSON lỗi vào giữa PNG, ZIP, PDF hay một binary format không định nghĩa cú pháp lỗi.

## 10. Server-Sent Events: thiết kế thành công và thất bại rõ ràng

Spring WebFlux có org.springframework.http.codec.ServerSentEvent<T>. Một SSE response dùng text/event-stream, có thể phát nhiều sự kiện:

~~~java
@GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.just(
            ServerSentEvent.<String>builder()
                    .event("item").id("1").data("one").build(),
            ServerSentEvent.<String>builder()
                    .event("complete").id("2").data("done").build());
}
~~~

Đoạn này là method trong một controller, chưa phải class độc lập.

Nên định nghĩa contract rõ:

| Event | Ý nghĩa |
| --- | --- |
| item | Một phần dữ liệu hợp lệ |
| complete | Kết quả nghiệp vụ đã phát đầy đủ |
| stream-error | Luồng thất bại sau khi bắt đầu |
| Không có complete và không có stream-error do ngắt mạng | Outcome chưa xác định, cần resume/retry theo policy |

SSE có event id có thể hỗ trợ checkpoint/resume khi server implement cơ chế Last-Event-ID và retention. Chỉ có id trên event không tự động tạo replay/resume an toàn.

### HTTP 200 không có nghĩa thành công

Nếu hai item được gửi rồi stream-error, HTTP status ban đầu vẫn có thể là 200. Client phải theo dõi terminal event để phân biệt với hoàn tất; metrics HTTP status 200 không đủ đo business success.

### Không tự thêm bytes JSON vào SSE

Để gửi lỗi, tạo sự kiện SSE hợp lệ như event: stream-error và data: error-code. Không tự ghi một JSON HTTP error response vào body SSE sau khi stream đã phát các sự kiện khác.

## 11. Reactor error operators cần dùng cẩn thận

Với Flux:

~~~java
Flux<String> data = Flux.concat(
        Flux.just("one", "two"),
        Flux.error(new IllegalStateException("upstream unavailable")));
~~~

Các operator có ý nghĩa khác nhau:

| Operator | Hành vi | Rủi ro |
| --- | --- | --- |
| doOnError | Quan sát/log onError, không chữa lỗi | Lầm tưởng đã xử lý lỗi |
| onErrorResume | Chuyển lỗi thành Publisher khác | Phải giữ đúng schema của stream |
| onErrorMap | Đổi exception giữ nguyên error signal | Không thay được HTTP status sau commit |
| onErrorComplete | Chuyển lỗi thành completion | Dễ che kết quả thiếu dữ liệu |
| retry | Subscribe lại source | Có thể phát lại item đã gửi, gây duplicate |
| doFinally | Nhìn COMPLETE/ERROR/CANCEL | Không chứng minh client nhận đầy đủ |
| concatWith | Phát lần lượt các Publisher | Nếu phần cuối error, các item đầu có thể đã gửi |
| collectList | Buffer cả stream hữu hạn thành List | Memory/latency và không dùng với infinite stream |

Ví dụ phục hồi hợp lệ nếu body là giao thức dòng:

~~~java
Flux<String> safe = data.onErrorResume(
        IllegalStateException.class,
        error -> Flux.just("ERROR:UPSTREAM_UNAVAILABLE"));
~~~

Điều này chỉ phù hợp nếu client đã biết xử lý dòng ERROR theo contract. Với JSON array nghiêm ngặt, chèn chuỗi lỗi có thể làm sai schema; với binary stream, tuyệt đối không tự ghép thông báo tùy ý.

Ví dụ nguy hiểm:

~~~java
Flux<String> hidden = data.onErrorComplete();
~~~

Nếu client nhận hai item mà server bỏ lỗi, nó có thể tin stream hoàn tất. Chỉ dùng khi partial success là một contract được document rõ ràng.

## 12. JSON array, NDJSON, SSE và file nhị phân

| Định dạng | Có thể phát từng phần? | Chiến lược lỗi giữa chừng |
| --- | --- | --- |
| application/json array | Có thể, tùy codec | Có thể làm JSON dở dang; khó chèn lỗi hợp lệ |
| application/x-ndjson | Các dòng JSON riêng | Dòng envelope lỗi được định nghĩa trước |
| text/event-stream | SSE events riêng | event stream-error và complete marker |
| text/plain stream | Các dòng hoặc bytes | Error marker nếu protocol định nghĩa |
| application/octet-stream | Bytes nhị phân | Thường terminate và verify checksum |
| CSV/ZIP/PDF download | Theo format | Không tự chèn JSON error; dùng temp file/checksum |

JSON array đang gửi dở có thể trở thành JSON không hoàn chỉnh. Nếu serializer của item thứ N thất bại sau nhiều item đã gửi, exception handler không thể thay status thành 500 dù đó là lỗi encoder thay vì lỗi service.

## 13. Ngay cả encoder cũng có thể lỗi

Nguồn dữ liệu có thể trả đúng Java objects nhưng HTTP message writer lại lỗi:

- DTO chứa giá trị không được JSON serializer hỗ trợ.
- Jackson custom serializer ném exception.
- Object graph có vòng lặp thiếu cấu hình.
- Trường dữ liệu không hợp lệ về schema.
- DataBuffer/Netty write fail.
- Client ngắt kết nối khi response đang ghi.
- Hết tài nguyên hoặc byte stream bị lỗi.

Nếu xảy ra sau khi body đã commit, status không thể đổi. Cách giảm rủi ro:

1. Test DTO serialization trên dữ liệu thực.
2. Validate và normalize các item trước khi trả Flux nếu có thể.
3. Với payload nhỏ, chuẩn bị toàn bộ representation trước khi ghi.
4. Với stream dài, dùng schema envelope và terminal marker.
5. Không làm I/O blocking trong JsonSerializer hoặc encoder.
6. Coi lỗi sau response commit là một sự kiện cần logging/metrics riêng.

collectList chỉ chuyển vấn đề buffering; nếu serialization lỗi ở giai đoạn ghi response sau đó, lỗi vẫn có thể xảy ra sau commit. Muốn bảo đảm atomic output phải thực sự chuẩn bị output hoàn chỉnh theo cách bounded trước commit.

## 14. Cancellation và client disconnect không giống upstream error

Client có thể rời trang, mạng bị mất, proxy timeout hoặc server graceful shutdown. Những trường hợp này có thể hủy subscription hoặc làm transport báo lỗi.

Ví dụ:

~~~java
return stream
        .doOnCancel(() ->
                log.info("client cancelled"))
        .doOnError(error ->
                log.warn("stream failed", error))
        .doFinally(signal ->
                log.debug("stream terminated: {}", signal));
~~~

Snippet cần stream và log được khai báo, không phải class độc lập.

Lưu ý:

- SignalType.CANCEL khác ERROR; không nhất thiết mọi client disconnect đến đúng operator bạn đang quan sát.
- Cancellation có thể truyền về upstream nhưng không rollback side effects đã hoàn tất.
- Một event được emit từ Flux không chứng minh client đã nhận và xử lý nó.
- Proxy buffering có thể che thời điểm flush thực.
- Nếu client reconnect, có thể nhận duplicate items khi retry source.

Đối với stream cần độ tin cậy cao, dùng sequence IDs, checkpoint, cursor, idempotency và terminal acknowledgement ở tầng ứng dụng.

## 15. Retry và resume phải có hợp đồng chống trùng

Giả sử source phát item 1, 2 rồi lỗi. Retry(3) có thể phát lại 1, 2 trước khi tiến tới item mới. Nếu client cộng dồn theo số lượng, dữ liệu bị nhân đôi.

Để retry an toàn:

1. Gắn ID/sequence ổn định cho mỗi item.
2. Lưu offset/cursor khi producer có khả năng replay.
3. Cho client gửi Last-Event-ID hoặc cursor tương ứng.
4. Xác định retention/window và trường hợp cursor hết hiệu lực.
5. Deduplicate ở client hoặc server.
6. Kiểm tra idempotency của các operation gây side effect.
7. Giới hạn retry và backoff.
8. Không retry lỗi schema/validation sẽ không tự biến mất.

Không gọi retry như một giải pháp tổng quát cho lỗi sau commit.

## 16. Project thực hành Spring Boot 3.3 và Java 17

Ví dụ này minh họa hai nhóm lỗi:

- GET /api/reports/{id}: lỗi ReportNotFoundException xảy ra **trước commit**, được chuyển thành HTTP 404 với JSON body.
- GET /api/events: thành công phát hai item và event complete; nếu fail=true, hai item rồi một event stream-error trong cùng response HTTP 200.
- GET /api/events-broken: cố tình phát hai item rồi onError không phục hồi, dùng để nghiên cứu error signal và giới hạn HTTP response.
- WebFilter.beforeCommit gắn header kiểm thử.
- WebTestClient gửi HTTP thật trên RANDOM_PORT; StepVerifier kiểm tra stream error trong JVM; MockServerHttpResponse xác minh không thể đổi status sau commit.

### 16.1 Cấu trúc thư mục

~~~text
committed-response-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/stream/
    │   ├── StreamApplication.java
    │   ├── StreamController.java
    │   ├── ReportNotFoundException.java
    │   ├── ErrorAdvice.java
    │   └── CommitMarkerFilter.java
    └── test/java/com/example/stream/
        ├── StreamHttpTests.java
        └── CommitSemanticsTests.java
~~~

### 16.2 settings.gradle

~~~groovy
rootProject.name = 'committed-response-demo'
~~~

### 16.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

Starter-webflux thường dùng embedded Reactor Netty. Không thêm spring-boot-starter-web trong project này vì Spring Boot mặc định ưu tiên MVC khi cả hai web starters có trên classpath.

### 16.4 StreamApplication.java

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

### 16.5 ReportNotFoundException.java

~~~java
package com.example.stream;

public final class ReportNotFoundException extends RuntimeException {

    public ReportNotFoundException(String id) {
        super("Unknown report: " + id);
    }
}
~~~

### 16.6 StreamController.java

~~~java
package com.example.stream;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamController {

    @GetMapping(
            path = "/reports/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ReportView>> report(
            @PathVariable("id") String id) {

        return Mono.defer(() -> {
            if (!"r1".equals(id)) {
                return Mono.<ResponseEntity<ReportView>>error(
                        new ReportNotFoundException(id));
            }

            return Mono.just(ResponseEntity.ok(
                    new ReportView("r1", "ready")));
        });
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(
            @RequestParam(
                    name = "fail",
                    defaultValue = "false") boolean fail) {

        Flux<ServerSentEvent<String>> items = Flux.just(
                event("item", "1", "one"),
                event("item", "2", "two"));

        Flux<ServerSentEvent<String>> terminal = fail
                ? Flux.error(
                        new IllegalStateException(
                                "upstream unavailable"))
                : Flux.just(event("complete", "3", "done"));

        return items.concatWith(terminal)
                .onErrorResume(
                        IllegalStateException.class,
                        error -> Flux.just(
                                event(
                                        "stream-error",
                                        "3",
                                        "UPSTREAM_UNAVAILABLE")));
    }

    @GetMapping(
            path = "/events-broken",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> brokenEvents() {

        return Flux.just(
                event("item", "1", "one"),
                event("item", "2", "two"))
                .concatWith(
                        Flux.error(
                                new IllegalStateException(
                                        "upstream unavailable")));
    }

    private static ServerSentEvent<String> event(
            String name, String id, String data) {

        return ServerSentEvent.<String>builder()
                .event(name)
                .id(id)
                .data(data)
                .build();
    }
}

record ReportView(String id, String status) {
}
~~~

Trong report, lỗi được phát trước khi có HTTP body thành công. Trong events(true), lỗi được thay thành một sự kiện SSE hợp lệ, nên kết quả business là lỗi dù HTTP status là 200. Trong brokenEvents, source phát onError sau hai items và không có fallback; HTTP transport có thể đóng hoặc reset sau partial output.

### 16.7 ErrorAdvice.java

~~~java
package com.example.stream;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(ReportNotFoundException.class)
    public ResponseEntity<ApiError> reportNotFound(
            ReportNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("REPORT_NOT_FOUND"));
    }
}

record ApiError(String code) {
}
~~~

Advice chỉ xử lý lỗi ReportNotFoundException. Nó không cố bắt toàn bộ Exception trong streaming response và không phản chiếu raw exception.getMessage chứa ID vào public response.

### 16.8 CommitMarkerFilter.java

~~~java
package com.example.stream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class CommitMarkerFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(CommitMarkerFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-Commit-Marker", "applied");
            return Mono.empty();
        });

        return chain.filter(exchange)
                .doOnError(error ->
                        log.error(
                                "Web request failed, committed={}",
                                exchange.getResponse().isCommitted(),
                                error));
    }
}
~~~

Filter không tự subscribe và không cố ghi JSON mới khi response đã commit. Nó giúp theo dõi lỗi chưa được phục hồi và thêm header trong beforeCommit.

## 17. WebTestClient kiểm chứng lỗi trước commit và SSE lỗi in-band

### 17.1 StreamHttpTests.java

~~~java
package com.example.stream;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamHttpTests {

    @LocalServerPort
    private int port;

    @Autowired
    private StreamController controller;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    private List<ServerSentEvent<String>> readEvents(
            String path) {

        FluxExchangeResult<ServerSentEvent<String>> result =
                client().get()
                        .uri(path)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().valueEquals(
                                "X-Commit-Marker", "applied")
                        .returnResult(
                                new ParameterizedTypeReference<
                                        ServerSentEvent<String>>() {});

        List<ServerSentEvent<String>> events =
                result.getResponseBody()
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertThat(events).isNotNull();
        return events;
    }

    @Test
    void precommitExceptionBecomesHttp404() {
        client().get()
                .uri("/api/reports/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().valueEquals(
                        "X-Commit-Marker", "applied")
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("REPORT_NOT_FOUND");
    }

    @Test
    void successfulSseHasCompletionMarker() {
        List<ServerSentEvent<String>> events =
                readEvents("/api/events?fail=false");

        assertThat(events).hasSize(3);
        assertThat(events.get(0).event()).isEqualTo("item");
        assertThat(events.get(0).data()).isEqualTo("one");
        assertThat(events.get(1).data()).isEqualTo("two");
        assertThat(events.get(2).event()).isEqualTo("complete");
        assertThat(events.get(2).data()).isEqualTo("done");
    }

    @Test
    void streamingFailureUsesInBandErrorEvent() {
        List<ServerSentEvent<String>> events =
                readEvents("/api/events?fail=true");

        assertThat(events).hasSize(3);
        assertThat(events.get(0).event()).isEqualTo("item");
        assertThat(events.get(1).event()).isEqualTo("item");
        assertThat(events.get(2).event())
                .isEqualTo("stream-error");
        assertThat(events.get(2).data())
                .isEqualTo("UPSTREAM_UNAVAILABLE");
    }

    @Test
    void brokenPublisherHasErrorAfterTwoItems() {
        StepVerifier.create(controller.brokenEvents())
                .expectNextCount(2)
                .expectError(IllegalStateException.class)
                .verify();
    }
}
~~~

Test WebTestClient gửi HTTP thật trên RANDOM_PORT để xác nhận 404 precommit và SSE 200 với event success/error. Test StepVerifier cuối kiểm tra Publisher gốc, **không** đoán status HTTP sau khi partial SSE đã được gửi. Đừng viết assert cố định rằng endpoint broken phải trả HTTP 500, vì điều đó trái với giới hạn response commit.

### 17.2 CommitSemanticsTests.java

~~~java
package com.example.stream;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;

class CommitSemanticsTests {

    @Test
    void cannotChangeStatusAfterCommit() {
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        assertThat(response.isCommitted()).isFalse();

        response.beforeCommit(() -> {
            response.getHeaders().set(
                    "X-Commit-Marker", "applied");
            return Mono.empty();
        });

        response.setComplete().block();

        assertThat(response.isCommitted()).isTrue();
        assertThat(response.getHeaders()
                .getFirst("X-Commit-Marker"))
                .isEqualTo("applied");

        boolean changed = response.setStatusCode(
                HttpStatus.INTERNAL_SERVER_ERROR);

        assertThat(changed).isFalse();
    }
}
~~~

MockServerHttpResponse chỉ kiểm tra hợp đồng Spring response trong JVM, không mô phỏng toàn bộ TCP/TLS/proxy. Sau setComplete, status không thể sửa. Test độc lập này bổ sung cho HTTP tests.

### 17.3 Chạy Gradle tests

~~~bash
gradle clean test
~~~

Nếu project có wrapper:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Không nên trình bày các kết quả kỳ vọng thành log thực thi. Cần chạy lệnh trên để xác minh trong môi trường Java/Gradle đang dùng; ứng dụng không cần database hoặc service ngoài.

## 18. Dùng cURL quan sát ba trường hợp

### 18.1 Server chạy

~~~bash
gradle bootRun
~~~

Theo cấu hình mặc định, Reactor Netty thường bind cổng 8080 nếu port trống.

### 18.2 Lỗi trước commit

~~~bash
curl -i 'http://127.0.0.1:8080/api/reports/missing'
~~~

Status mong đợi: 404, header X-Commit-Marker: applied, body tương đương:

~~~json
{"code":"REPORT_NOT_FOUND"}
~~~

Các header hạ tầng và thứ tự header có thể khác.

### 18.3 SSE thành công

~~~bash
curl -i -N 'http://127.0.0.1:8080/api/events?fail=false'
~~~

Body có semantics tương đương:

~~~text
id:1
event:item
data:one

id:2
event:item
data:two

id:3
event:complete
data:done

~~~

Thứ tự hoặc khoảng trắng quanh SSE fields tùy encoder; ứng dụng client nên parse SSE event thay vì so byte-for-byte.

### 18.4 SSE lỗi trong body, status vẫn 200

~~~bash
curl -i -N 'http://127.0.0.1:8080/api/events?fail=true'
~~~

Client nhận hai event item rồi event stream-error với data UPSTREAM_UNAVAILABLE. Status HTTP vẫn có thể là 200. Hợp đồng ví dụ: event complete mới là kết thúc thành công; event stream-error là lỗi nghiệp vụ.

### 18.5 SSE lỗi không xử lý

~~~bash
curl -i -N 'http://127.0.0.1:8080/api/events-broken'
~~~

Server có thể đã gửi hai item trước onError. Không khẳng định cURL sẽ thấy 500, một JSON error body hay phần response thành công; kết quả phụ thuộc server, proxy và HTTP version. Quan sát server error logs, trạng thái client, event count và stream completeness.

## 19. Tại sao JSON error sau commit không luôn có hiệu lực?

Một server response bao gồm:

1. Status line hoặc HTTP/2 pseudo-header.
2. Headers như Content-Type và cache metadata.
3. Body bytes.
4. Framing/termination ở HTTP transport.

Khi body đã phát, những phần trước đó đã được xác định. Việc thay Java object response hoặc return ResponseEntity.status(500) trong một callback muộn **không tự tạo lại bytes đã gửi**.

Nếu đang ghi JSON array:

~~~json
[{"id":1},{"id":2},
~~~

và item sau lỗi, không được nối một JSON object lỗi rồi cho rằng output là JSON hợp lệ. Client thường sẽ gặp parse error hoặc incomplete response.

Nếu API yêu cầu kết quả kiểu JSON atomically valid, cân nhắc precompute trong phạm vi bounded, kiểm tra serialization trước, hoặc đổi contract sang NDJSON envelope với explicit terminal item.

## 20. File download và checksum

Đối với file lớn:

- Kiểm tra resource/permission trước khi trả HTTP 200.
- Nếu Content-Length biết trước, client cần kiểm tra đã nhận đủ byte.
- Nếu checksum/ETag hoặc signed manifest có thể dùng, client nên verify trước khi dùng file.
- Ghi vào temp file phía client, chỉ đổi tên/promote khi download hoàn tất.
- Nếu storage lỗi giữa chừng, không chèn JSON error vào giữa ZIP, PDF, ảnh hoặc file nhị phân.
- Nếu retry với HTTP Range, cần bảo đảm snapshot consistency, ETag và Content-Range đúng contract.
- Nếu cần một response hoàn chỉnh hoặc không trả gì, tạo file tạm có giới hạn trước khi bắt đầu gửi.

Content-Length không phải checksum; nó kiểm tra độ dài chứ không đảm bảo nội dung không bị đổi.

## 21. Metrics: HTTP 200 không đủ đo business success

Nên theo dõi riêng:

| Chỉ số | Giá trị |
| --- | --- |
| stream_started | Đã mở session streaming |
| stream_completed | Đã phát terminal complete thành công |
| stream_error_event | Đã phát stream-error in-band |
| stream_aborted | Stream lỗi/đóng không hoàn tất |
| client_cancelled | Client ngắt/huỷ theo observation có thể ghi nhận |
| elements_emitted | Số item đã phát ở server |
| bytes_written | Số byte phía server ghi được |
| upstream_errors | Lỗi từ service/data source |
| serialization_errors | Lỗi codec/Jackson sau khi bắt đầu ghi |
| retry_count | Số lần phục hồi/reconnect |

HTTP status 200 và stream_error_event có thể cùng đúng. Đừng làm dashboards chỉ đếm 5xx rồi kết luận streaming API không có lỗi.

Với Micrometer, dùng bounded labels như error_code hoặc endpoint template; tránh dùng raw URL/user ID làm metric tag tạo cardinality vô hạn.

### doFinally không phải client acknowledgment

doFinally nhận COMPLETE, ERROR hoặc CANCEL của Publisher tương ứng. Nó không chứng minh client lưu thành công tất cả bytes. Nếu cần exactly-once hay end-to-end acknowledgment, phải có application protocol riêng.

## 22. Khác biệt với Spring MVC

Spring MVC cũng có response commit, nhưng dùng Servlet API:

| Khía cạnh | WebFlux | Spring MVC |
| --- | --- | --- |
| Front controller | DispatcherHandler | DispatcherServlet |
| Response | ServerHttpResponse | HttpServletResponse |
| Trạng thái commit | isCommitted() | isCommitted() |
| Hook trước commit | beforeCommit(...) | Không có hook tương đương hoàn toàn |
| Streaming | Flux, SSE, reactive DataBuffer | SseEmitter, ResponseBodyEmitter, StreamingResponseBody |
| Error handling | WebExceptionHandler, @ControllerAdvice | HandlerExceptionResolver, @ControllerAdvice, Servlet error dispatch |
| I/O | Reactive non-blocking theo runtime | Servlet/async với nhiều write blocking |
| Giới hạn sau commit | Không thể đổi status đã gửi | Cũng không thể đổi status đã gửi |

Trong Servlet, HttpServletResponse.reset() chỉ hợp lệ theo contract khi response chưa commit; sau commit có thể ném IllegalStateException. Không lấy reset() của Servlet rồi áp vào WebFlux.

MVC có thể trả Mono/Flux trong một số trường hợp, nhưng chỉ có reactive return type không chứng minh server đang dùng WebFlux. Spring Boot mặc định ưu tiên MVC nếu cả starter-web và starter-webflux có trong classpath.

## 23. Debug lỗi after-commit theo trình tự

1. Xác nhận ứng dụng dùng WebFlux hay MVC.
2. Xác nhận response là SSE, NDJSON, JSON array hay binary.
3. Kiểm tra status/header có bị commit trước lúc error không.
4. Xem source Publisher phát error trước hay sau một số phần tử.
5. Kiểm tra encoder có fail khi serialize item nào.
6. Phân loại upstream failure, client cancel, transport error, proxy timeout.
7. Quan sát WebFilter doOnError/doFinally và isCommitted ở thời điểm callback.
8. Nếu precommit, xem @ExceptionHandler hoặc WebExceptionHandler có map đúng status không.
9. Nếu postcommit, xác minh in-band error marker hoặc stream abort hợp lý.
10. Kiểm tra client có đòi terminal complete hoặc checksum không.
11. Kiểm tra retry có làm trùng item không.
12. Ghi metrics riêng cho stream success/error/cancel.
13. Test precommit error qua HTTP integration.
14. Test SSE success/error event bằng event parser.
15. Test broken Publisher riêng bằng StepVerifier, không gán cứng HTTP 500 sau commit.

Log phát sinh khi stream fail nên có correlation ID, không ghi raw Authorization, Cookie, access token hay body dữ liệu cá nhân. Nếu bật Netty wiretap ở môi trường debug, phải kiểm soát phạm vi và tắt sau điều tra.

## 24. Các lỗi thiết kế cần tránh

### Lỗi 1: Luôn trả 500 trong global advice

Response đã commit không thể thay status. Dùng global advice cho lỗi precommit, in-band event hoặc transport abort cho postcommit.

### Lỗi 2: onErrorComplete để “chữa” stream

Nó có thể che partial result, khiến client hiểu nhầm đã nhận đủ. Hãy có terminal marker.

### Lỗi 3: onErrorResume trả sai type

Nếu Flux<ItemDto> đang serialize NDJSON, không đột ngột trả String không thuộc contract. Dùng envelope type hoặc SSE event type rõ ràng.

### Lỗi 4: Tự subscribe

~~~java
// Không nên dùng trong controller trả reactive HTTP:
data.subscribe(this::save);
return Mono.empty();
~~~

Làm mất liên kết với lifecycle/error/cancellation HTTP. Return reactive chain cho framework.

### Lỗi 5: Gọi block() trên event loop

Có thể gây nghẽn và timeout những stream khác. Sử dụng reactive client/driver, hoặc cô lập blocking work đúng cách.

### Lỗi 6: Dùng collectList với nguồn vô hạn

Có thể không bao giờ hoàn tất và tiêu hao memory. Buffering chỉ dùng cho bounded payload với giới hạn size/time.

### Lỗi 7: Retry không kiểm soát

Có thể gửi lại items đã gửi. Dùng sequence/cursor/dedup.

### Lỗi 8: Tự ghi JSON error sau SSE item

Phá cú pháp protocol và không đổi được status. Nếu SSE có lỗi, phát event đúng schema.

### Lỗi 9: Đọc isCommitted rồi không kiểm tra kết quả setStatusCode

Giữa check và update có thể commit đồng thời. Cần xem return boolean và thiết kế pipeline tránh race.

### Lỗi 10: Coi HTTP 200 là metric stream thành công

Một response 200 có thể chứa stream-error hoặc thiếu complete marker. Tách metric ứng dụng khỏi metric HTTP.

### Lỗi 11: Thực hiện network/database I/O trong beforeCommit

Callback commit không phải nơi chạy blocking operation. Có thể làm chậm flush hoặc gây lỗi ngay khi commit.

### Lỗi 12: Cố chứng minh bằng test status HTTP 500 cho broken SSE

Kết quả phụ thuộc protocol/server/client; test data contract và error signal thay vì dựa vào phỏng đoán.

## 25. Checklist vận hành

- [ ] Xác định những điều kiện phải validate trước commit.
- [ ] Quyết định API là atomic body hay streaming.
- [ ] Có định dạng lỗi phù hợp với SSE/NDJSON nếu cần.
- [ ] Có terminal completion marker để client nhận biết thành công.
- [ ] Không sửa status/header sau commit.
- [ ] Sử dụng beforeCommit chỉ cho logic phù hợp trước commit.
- [ ] Không tự subscribe/block hoặc swallow errors.
- [ ] Định nghĩa retry/resume/checkpoint chống trùng.
- [ ] Phân biệt upstream error và client cancellation.
- [ ] Theo dõi incomplete streams ngoài HTTP status.
- [ ] Test lỗi precommit và postcommit riêng.
- [ ] Test SSE error event, terminal complete, duplicate IDs.
- [ ] Giới hạn memory nếu chọn buffering.
- [ ] Với download, xác minh length/checksum.
- [ ] Không gửi stack trace, token hoặc dữ liệu nhạy cảm cho client.
- [ ] Giữ code tương thích Spring Boot và Spring Framework versions đang chạy.

## 26. Tóm tắt

**Sau khi HTTP response đã commit, status và headers không thể bị thay bằng một phản hồi khác.** Trong Spring WebFlux, một Flux có thể phát hai item, server commit HTTP 200, rồi Publisher mới onError. Việc thêm @ExceptionHandler trả ResponseEntity.status(500) không thể thu hồi các bytes đã gửi.

Có ba lựa chọn thiết kế: kiểm tra và chuẩn bị dữ liệu trước commit nếu cần atomic response; xây stream có sự kiện lỗi in-band cùng terminal complete marker để client hiểu; hoặc propagate lỗi, đóng/reset stream và để client nhận diện incomplete output khi protocol không thể chèn lỗi.

Hiểu ServerHttpResponse.isCommitted(), beforeCommit, Reactor doOnError/onErrorResume/doFinally, HTTP codecs và sự khác nhau giữa completion và client acknowledgment là nền tảng xử lý lỗi streaming an toàn. Ở client, **đừng coi HTTP 200 là bằng chứng dữ liệu đã nhận đầy đủ**.

## 27. Tài liệu tham khảo

- Spring Framework 6.1 — ServerHttpResponse Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Framework — WebFlux Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework — WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework — WebExceptionHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
- Spring Framework — WebFlux Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Reactor — Error Handling Operators: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- MDN — Using Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
