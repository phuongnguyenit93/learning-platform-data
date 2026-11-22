# ResponseEntity và thời điểm xác định status, header, body trong Spring WebFlux

## 1. Vai trò của ResponseEntity

Trong Spring WebFlux, controller có thể trả về publisher như Mono<T> hoặc Flux<T> để framework ghi response theo cách reactive. Khi cần chủ động điều khiển HTTP response, controller có thể dùng ResponseEntity<T>.

ResponseEntity gom ba thành phần của một HTTP response:

1. **Status code:** ví dụ 200 OK, 201 Created, 204 No Content, 400 Bad Request, 404 Not Found.
2. **Headers:** ví dụ Content-Type, Location, ETag, Cache-Control hoặc header nghiệp vụ.
3. **Body:** đối tượng hoặc publisher được message writer/codec chuyển thành dữ liệu HTTP.

Điểm dễ nhầm trong WebFlux là **thời điểm quyết định status/header và thời điểm body thực sự phát dữ liệu có thể khác nhau**. Chỉ cần thay đổi vị trí của Mono trong kiểu trả về, ta có thể thay đổi thời điểm biết status:

- **ResponseEntity<T>:** controller trả cả status, headers và body dạng giá trị ngay.
- **Mono<ResponseEntity<T>>:** publisher bên ngoài phát ra toàn bộ ResponseEntity sau khi xử lý bất đồng bộ; status/header có thể phụ thuộc kết quả nghiệp vụ.
- **ResponseEntity<Mono<T>>:** controller quyết định status/header ngay; body là publisher được tiêu thụ bất đồng bộ sau đó.
- **ResponseEntity<Flux<T>>:** status/header được xác định trước khi stream body; body có thể phát nhiều phần tử theo thời gian.

Đây là khác biệt cốt lõi để xử lý đúng 404, 201, 204, header, body rỗng và lỗi xuất hiện trong lúc stream. ResponseEntity không tự làm code blocking trở thành non-blocking; nó là mô hình biểu diễn response metadata và body.

## 2. Ba thời điểm cần tách biệt

Khi một request tới WebFlux, hãy hình dung ba thời điểm:

**Thời điểm A — controller tạo kết quả:** method controller được gọi, tạo một giá trị hoặc publisher. Nếu return là Mono<ResponseEntity<T>>, publisher này có thể chưa phát ResponseEntity. Nếu return là ResponseEntity<Mono<T>>, object ResponseEntity đã có status/header ngay khi method trả về.

**Thời điểm B — framework nhận metadata:** WebFlux xử lý giá trị return, chọn status, headers, message writer và chuẩn bị ghi body. Với ResponseEntity, framework lấy status/header từ object rồi ghi vào server response.

**Thời điểm C — response được commit và body được ghi:** khi server bắt đầu gửi response qua network, status/header trở thành một phần của HTTP response đã gửi. Sau khi response đã commit, ứng dụng **không thể thay status code hoặc header đã gửi**. Nếu body publisher tiếp tục phát lỗi sau thời điểm đó, server thường chỉ có thể kết thúc stream/connection hoặc xử lý lỗi ở tầng transport; không thể đổi response 200 thành 500 đã gửi ngược về client.

Sơ đồ khái quát:

~~~text
Request
  |
  v
Controller được gọi
  |
  +--> ResponseEntity<T>
  |      metadata + body value đã có
  |
  +--> Mono<ResponseEntity<T>>
  |      chờ outer Mono phát ResponseEntity
  |      rồi mới biết status/header/body
  |
  +--> ResponseEntity<Mono<T>> / ResponseEntity<Flux<T>>
         metadata đã có
         body publisher được subscribe/ghi sau
  |
  v
WebFlux áp status + headers
  |
  v
Response commit (headers được gửi)
  |
  v
Body được ghi / stream tiếp tục
~~~

Sơ đồ mô tả ý nghĩa của các kiểu return, không khẳng định mọi implementation server đều commit tại cùng một dòng code. Thời điểm commit thực tế phụ thuộc việc ghi response, flush, body publisher và server adapter.

## 3. So sánh các kiểu return quan trọng

| Kiểu return | Khi nào biết status/header? | Body | Phù hợp |
| --- | --- | --- | --- |
| ResponseEntity<User> | Ngay khi method trả object | Giá trị User đã có | Kết quả đồng bộ, metadata quyết định ngay |
| Mono<ResponseEntity<User>> | Khi outer Mono phát ResponseEntity | Giá trị User nằm trong entity | Tìm dữ liệu reactive rồi chọn 200/404/201 |
| ResponseEntity<Mono<User>> | Ngay khi method trả entity | Mono<User> được tiêu thụ sau | Status/header cố định, body tới bất đồng bộ |
| ResponseEntity<Flux<Event>> | Ngay khi method trả entity | Flux<Event> được ghi theo luồng | Streaming, SSE hoặc nhiều bản ghi |
| Mono<User> | Theo status mặc định/annotation của endpoint | Một body value hoặc empty | Response body reactive, không cần tự chọn header/status |

### 3.1. ResponseEntity<T> — toàn bộ response đã có

~~~java
@GetMapping("/version")
ResponseEntity<String> version() {
    return ResponseEntity.ok()
        .header("X-App-Version", "2.0")
        .body("ready");
}
~~~

Đây là snippet trong controller WebFlux. Method tạo một ResponseEntity có status 200, header và body string ngay trong lần gọi. WebFlux vẫn chịu trách nhiệm ghi response qua HTTP server và codec phù hợp; controller không tự ghi byte vào socket.

### 3.2. Mono<ResponseEntity<T>> — quyết định response sau khi có kết quả

~~~java
@GetMapping("/users/{id}")
Mono<ResponseEntity<User>> find(@PathVariable long id) {
    return service.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Đây là snippet; User và service.findById do ứng dụng định nghĩa. Service trả Mono<User>. Khi có user, outer publisher phát ResponseEntity 200. Khi nguồn hoàn tất rỗng, defaultIfEmpty phát ResponseEntity 404.

Đây là kiểu phù hợp khi **chính kết quả reactive quyết định status/header**. WebFlux chờ outer Mono phát ResponseEntity để biết metadata trước khi ghi body.

### 3.3. ResponseEntity<Mono<T>> — metadata cố định, body bất đồng bộ

~~~java
@GetMapping("/preview/{id}")
ResponseEntity<Mono<User>> preview(@PathVariable long id) {
    Mono<User> body = service.findById(id);

    return ResponseEntity.ok()
        .header("X-Response-Mode", "body-is-reactive")
        .body(body);
}
~~~

Status 200 và header được chọn ngay trong controller. Body publisher mới được tiêu thụ khi framework ghi response. Nếu user không tồn tại và body là Mono.empty(), response vẫn giữ status 200 đã chọn và body rỗng. Nó **không tự biến thành 404**.

Nếu sự tồn tại của user phải quyết định 200 hay 404, dùng Mono<ResponseEntity<User>> hoặc một outer publisher có thể tạo ResponseEntity sau khi biết kết quả.

### 3.4. ResponseEntity<Flux<T>> — status/header trước, stream body sau

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
ResponseEntity<Flux<ServerSentEvent<Event>>> events() {
    Flux<ServerSentEvent<Event>> body = eventService.events()
        .map(event -> ServerSentEvent.builder(event).event("update").build());

    return ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(body);
}
~~~

Đây là snippet WebFlux/SSE. Status 200 và content type được xác định trước khi stream body. Flux có thể phát event theo thời gian; client nhận các event khi server ghi chúng.

Nếu publisher lỗi sau khi response đã commit, status 200 đã gửi không thể được thay bằng 500. Vì vậy streaming endpoint cần thiết kế lỗi trong stream, logging, retry ở upstream hoặc protocol-level event báo lỗi nếu client cần nhận thông tin lỗi nghiệp vụ.

## 4. Chọn kiểu return theo câu hỏi nghiệp vụ

Đừng bắt đầu từ kiểu generic. Hãy hỏi: **Có cần chờ kết quả bất đồng bộ để quyết định status/header hay không?**

| Tình huống | Kiểu nên cân nhắc | Lý do |
| --- | --- | --- |
| GET một resource; không tìm thấy thì 404 | Mono<ResponseEntity<T>> | Chờ lookup rồi chọn 200 hoặc 404 |
| POST tạo resource; cần Location theo ID sinh ra | Mono<ResponseEntity<T>> | Chờ create hoàn tất rồi mới tạo 201 + Location |
| Response luôn 202; body là job status bất đồng bộ | ResponseEntity<Mono<JobStatus>> | Status đã biết, body tới sau |
| SSE luôn trả 200 và stream event | ResponseEntity<Flux<ServerSentEvent<T>>> | Metadata cố định, body stream |
| Giá trị đã có đồng bộ và cần custom header | ResponseEntity<T> | Không cần outer publisher |
| Chỉ trả dữ liệu reactive, status mặc định phù hợp | Mono<T> / Flux<T> | Đơn giản hơn, framework xử lý body |
| Cần 204 khi command hoàn tất | Mono<ResponseEntity<Void>> hoặc Mono<Void> với semantics phù hợp | Chọn rõ status và không có body |
| Lỗi nghiệp vụ cần status riêng | @ExceptionHandler hoặc onErrorResume tạo ResponseEntity | Map lỗi sang response có chủ đích |

Một endpoint không cần ResponseEntity chỉ vì nó trả Mono. Nếu status mặc định 200 và không cần custom header, return Mono<T> thường gọn hơn. Dùng ResponseEntity khi status, header hoặc body absence là một phần của hợp đồng HTTP.

## 5. 404: body rỗng khác với không tìm thấy

Đây là một trong những lỗi phổ biến nhất khi viết reactive controller.

### 5.1. Sai kỳ vọng: body Mono rỗng tự chuyển thành 404

~~~java
@GetMapping("/users/{id}/body")
ResponseEntity<Mono<User>> body(@PathVariable long id) {
    return ResponseEntity.ok(service.findById(id));
}
~~~

Nếu service trả Mono.empty(), controller đã chọn 200. Framework ghi một response 200 không có body. Mono.empty() chỉ biểu thị publisher hoàn tất mà không phát phần tử; nó không có nghĩa HTTP 404.

### 5.2. Chọn status sau khi lookup

~~~java
@GetMapping("/users/{id}")
Mono<ResponseEntity<User>> find(@PathVariable long id) {
    return service.findById(id)
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(ResponseEntity.<User>notFound().build());
}
~~~

Ở đây outer Mono sẽ phát đúng một ResponseEntity cho cả trường hợp có dữ liệu và không có dữ liệu. Nếu source empty, defaultIfEmpty tạo entity 404. Cách này diễn đạt đúng ý “không tồn tại là một kết quả HTTP hợp lệ”.

### 5.3. Fallback bằng switchIfEmpty

Có thể tạo fallback response bằng switchIfEmpty:

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok(user))
    .switchIfEmpty(Mono.fromSupplier(
        () -> ResponseEntity.<User>notFound().build()
    ));
~~~

Dùng fromSupplier để tạo response fallback khi cần; với một builder đơn giản, Mono.just(ResponseEntity.<User>notFound().build()) cũng hợp lệ vì builder không có side effect đáng kể.

### 5.4. Phân biệt ba trạng thái

| Trạng thái publisher | Ý nghĩa | HTTP response nên chọn |
| --- | --- | --- |
| Mono.just(user) | Tìm thấy dữ liệu | 200 + body |
| Mono.empty() | Không có phần tử | Phụ thuộc nghiệp vụ; resource lookup thường là 404 |
| Mono.error(error) | Xử lý thất bại | Map lỗi sang 4xx/5xx phù hợp |

Không biến mọi empty thành 404 một cách máy móc. Một search query không có kết quả có thể là 200 với list rỗng; một resource được định danh cụ thể mà không tồn tại thường là 404. Status phản ánh hợp đồng endpoint, không chỉ phản ánh toán tử Reactor.

## 6. 201 Created, Location và response sau khi ghi

Khi POST tạo tài nguyên thành công, status 201 và header Location thường nên được tạo **sau khi** service trả về ID hoặc URI:

~~~java
@PostMapping("/users")
Mono<ResponseEntity<User>> create(@RequestBody CreateUserRequest request) {
    return service.create(request)
        .map(user -> ResponseEntity
            .created(URI.create("/users/" + user.id()))
            .body(user));
}
~~~

- created(URI) tạo ResponseEntity builder với status 201 và Location.
- body(user) thêm body; WebFlux sẽ serialize theo message codec.
- Nếu thao tác create thất bại, lỗi được chuyển thành onError; exception handler hoặc error mapping quyết định response lỗi.
- Không nên tạo Location từ ID giả trước khi thao tác lưu thành công.
- Với command chỉ được chấp nhận để xử lý sau, 202 Accepted có thể phù hợp hơn 201 Created.

Có thể trả 201 không body nếu hợp đồng cho phép:

~~~java
Mono<ResponseEntity<Void>> create(CreateUserRequest request) {
    return service.create(request)
        .map(user -> ResponseEntity
            .created(URI.create("/users/" + user.id()))
            .<Void>build());
}
~~~

Nếu cần body chứa resource vừa tạo, dùng body(user). Nếu không cần body, dùng build() với kiểu generic phù hợp.

## 7. 204 No Content và các response không có body

HTTP 204 biểu thị request thành công nhưng response không có nội dung. Không nên gắn một body publisher có thể phát dữ liệu vào response 204.

~~~java
@DeleteMapping("/users/{id}")
Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

Đây là snippet: giả sử service.delete trả Mono<Void> và hoàn tất bình thường khi xóa xong. thenReturn tạo ResponseEntity 204 sau khi command complete. Nếu delete lỗi, thenReturn không chạy và lỗi được truyền downstream.

Một lựa chọn là:

~~~java
@DeleteMapping("/users/{id}")
Mono<Void> delete(@PathVariable long id) {
    return service.delete(id);
}
~~~

Nếu không cần tùy biến status/header, return Mono<Void> có thể đủ; hãy chọn rõ semantics endpoint và xác minh response thực tế bằng WebTestClient.

Các status không nên có body theo semantics HTTP gồm 204 No Content và 304 Not Modified. Với các response này, đừng cố gửi JSON rỗng chỉ để có một payload; body absence là một phần của contract.

## 8. Header: quyết định ở builder và bảo toàn contract

ResponseEntity builder giúp tạo header có chủ đích:

~~~java
ResponseEntity<User> response = ResponseEntity.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .header("X-Correlation-ID", correlationId)
    .cacheControl(CacheControl.noCache())
    .eTag(etag)
    .body(user);
~~~

Những header hay gặp:

| Header | Mục đích | Lưu ý |
| --- | --- | --- |
| Content-Type | Định dạng body | Chọn tương thích với codec và client |
| Location | URI của resource mới hoặc nơi chuyển hướng | Thường dùng với 201 Created |
| ETag | Validator cho representation | Cần tính từ nội dung/phiên bản phù hợp |
| Last-Modified | Validator thời gian | Cần semantics thời gian chính xác |
| Cache-Control | Chính sách cache | Cân nhắc dữ liệu riêng tư và proxy |
| Vary | Nêu header request ảnh hưởng representation | Quan trọng với content negotiation/cache |
| Header correlation | Theo dõi request | Không đưa secret/PII vào header tùy tiện |

Dùng headers(HttpHeaders) hoặc headers(Consumer<HttpHeaders>) khi cần nhiều header; tránh tạo header không hợp lệ hoặc tự nối chuỗi từ dữ liệu không được validate. Không đặt Content-Length thủ công cho stream có kích thước chưa biết. Server/codec thường quản lý framing phù hợp với transport.

### 8.1. Header phụ thuộc kết quả bất đồng bộ

Nếu ETag hoặc Location phụ thuộc dữ liệu được load, tạo ResponseEntity **sau khi có dữ liệu**:

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok()
        .eTag(user.versionTag())
        .header("X-User-Version", user.version())
        .body(user))
    .defaultIfEmpty(ResponseEntity.<User>notFound().build());
~~~

Nếu status/header cố định bất kể body, ResponseEntity<Mono<T>> có thể thích hợp. Nếu status/header phụ thuộc kết quả, dùng outer publisher.

### 8.2. Conditional request và 304

ETag có thể được dùng để kiểm tra client đã có representation hiện tại hay chưa. Khi phù hợp, có thể dùng cơ chế của ServerWebExchange/request condition để trả 304 và bỏ body. Không nên tự so sánh chuỗi If-None-Match theo cách đơn giản nếu cần tuân thủ đầy đủ HTTP validator semantics (weak/strong ETag, wildcard và nhiều tag). Hãy dùng API Spring chuyên dụng hoặc thư viện HTTP phù hợp.

## 9. Streaming body: status/header đã chọn trước, body chưa hoàn tất

Một response ResponseEntity<Flux<T>> có thể stream nhiều phần tử:

~~~java
@GetMapping(value = "/numbers", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
ResponseEntity<Flux<Integer>> numbers() {
    Flux<Integer> body = Flux.range(1, 3);

    return ResponseEntity.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(body);
}
~~~

Trong ví dụ thực tế, nguồn có thể vô hạn hoặc đến từ broker. Khi đó:

- Status và header đã chọn khi ResponseEntity được tạo.
- WebFlux subscribe body publisher và ghi các phần tử theo demand/transport.
- Body không nhất thiết được gom thành một list trước khi gửi.
- Subscriber client có thể hủy khi đóng kết nối.
- Lỗi từ Flux sau khi response commit không thể đổi status/headers đã gửi.
- Không giữ toàn bộ stream trong RAM chỉ để có thể chọn status cuối cùng; streaming vốn không có “kết quả cuối” trước khi bắt đầu.

Nếu cần status dựa trên việc **nguồn có ít nhất một phần tử hay không**, có thể phải kiểm tra/peek dữ liệu trước khi tạo response. Nhưng điều đó có thể thay đổi buffering, latency, cancellation và semantics nguồn. Với stream vô hạn, chờ hoàn tất để chọn status là không khả thi. Thiết kế API nên chọn status dựa trên điều kiện có thể biết trước, còn lỗi sau commit được xử lý theo semantics của stream.

## 10. Lỗi trước và sau khi response commit

Đây là ranh giới quan trọng khi dùng ResponseEntity<Mono<T>> hoặc ResponseEntity<Flux<T>>.

### 10.1. Lỗi khi outer publisher chưa phát ResponseEntity

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok(user));
~~~

Nếu service.findById phát lỗi trước khi có ResponseEntity, outer Mono kết thúc bằng onError. Spring WebFlux có thể chuyển lỗi tới exception handler/global error handler để chọn response phù hợp, miễn response chưa commit.

### 10.2. Lỗi trong body publisher trước khi ghi body

~~~java
ResponseEntity<Mono<User>> response =
    ResponseEntity.ok(service.findById(id));
~~~

Status/header đã được chọn trong entity, nhưng thời điểm commit phụ thuộc adapter bắt đầu ghi response. Nếu body publisher lỗi trước khi server commit, framework còn có thể xử lý lỗi tùy pipeline/adapter. Không nên xây contract phụ thuộc vào việc một lỗi body “chắc chắn” sẽ đổi status; nếu status cần phản ánh lỗi lookup, hãy chờ lookup ở outer publisher và tạo ResponseEntity sau đó.

### 10.3. Lỗi sau khi body đã bắt đầu ghi

Khi response đã commit, status và headers đã gửi. Nếu body Flux tiếp tục lỗi:

- Không thể thay 200 đã gửi thành 500.
- Server có thể kết thúc connection hoặc báo lỗi ghi theo transport.
- Client có thể thấy body bị ngắt giữa chừng.
- Ứng dụng nên log, metric và thiết kế retry/heartbeat/protocol event phù hợp.

Đối với SSE, nếu nghiệp vụ cần thông báo lỗi trong stream, có thể phát một event kiểu error theo schema ứng dụng trước khi kết thúc bình thường, nếu chính sách bảo mật và giao thức cho phép. Đừng nhầm event lỗi trong body với HTTP status 500.

## 11. onErrorResume và exception handler khi tạo ResponseEntity

Có thể map lỗi thành response ngay trong pipeline:

~~~java
Mono<ResponseEntity<User>> response = service.findById(id)
    .map(user -> ResponseEntity.ok(user))
    .onErrorResume(AccessDeniedException.class, error ->
        Mono.just(ResponseEntity.<User>status(HttpStatus.FORBIDDEN).build())
    );
~~~

Snippet này cần import các kiểu liên quan và exception của ứng dụng. Dùng onErrorResume khi xử lý lỗi là một phần của logic cục bộ của endpoint. Đừng catch mọi Throwable rồi trả 200 hoặc 400 một cách tùy tiện; lỗi hạ tầng, lỗi lập trình và lỗi nghiệp vụ cần mapping khác nhau.

Với mapping tập trung, dùng @RestControllerAdvice và @ExceptionHandler:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(UserNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(UserNotFoundException error) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            error.getMessage()
        );
        body.setTitle("User not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

Đây là snippet; cần import ProblemDetail, HttpStatus, annotation và exception của ứng dụng. ProblemDetail là mô hình lỗi HTTP có cấu trúc trong Spring 6+. Đảm bảo message trả về client không tiết lộ SQL, stack trace, token hoặc thông tin nội bộ.

Exception handler cũng chịu giới hạn commit: nếu response đã gửi header/body một phần, handler không thể quay ngược response đã gửi để đổi status.

## 12. ResponseEntity không làm blocking code trở thành reactive

Một lỗi phổ biến là đặt lời gọi blocking trong controller rồi bọc bằng ResponseEntity:

~~~java
@GetMapping("/legacy/{id}")
ResponseEntity<User> legacy(@PathVariable long id) {
    User user = jdbcRepository.findByIdBlocking(id);
    return ResponseEntity.ok(user);
}
~~~

Kiểu return ResponseEntity<User> không thay đổi bản chất của JDBC. Method vẫn chặn thread đang gọi controller.

Nếu bắt buộc dùng API blocking cũ, hoãn lời gọi và đưa nó lên scheduler dành cho blocking:

~~~java
@GetMapping("/legacy/{id}")
Mono<ResponseEntity<User>> legacy(@PathVariable long id) {
    return Mono.fromCallable(() -> jdbcRepository.findByIdBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .map(user -> ResponseEntity.ok(user))
        .defaultIfEmpty(ResponseEntity.<User>notFound().build());
}
~~~

Đây là snippet minh họa. fromCallable hoãn lời gọi tới subscription; subscribeOn(boundedElastic) cách ly thao tác blocking khỏi event-loop; map chọn response sau khi có kết quả. JDBC vẫn chặn một worker trong thời gian chạy, không biến thành non-blocking I/O. Nếu có thể, ưu tiên driver reactive như R2DBC cho đường xử lý reactive thực sự.

Không dùng block() trong controller:

~~~java
User user = service.findById(id).block();
return ResponseEntity.ok(user);
~~~

block() chặn thread gọi và có thể bị Reactor cấm trên thread đánh dấu non-blocking. Hãy compose publisher bằng map, flatMap, switchIfEmpty, onErrorResume và return nó cho WebFlux.

## 13. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Ví dụ này minh họa ba contract:

1. Mono<ResponseEntity<User>>: tìm user rồi chọn 200/404.
2. ResponseEntity<Mono<User>>: status cố định 200 dù body có thể empty.
3. ResponseEntity<Flux<ServerSentEvent<String>>>: status/header cố định và body stream.

### 13.1. Cấu trúc dự án

~~~text
response-entity-demo/
  build.gradle
  src/
    main/
      java/demo/
        ResponseEntityDemoApplication.java
        User.java
        CreateUserRequest.java
        UserService.java
        UserController.java
    test/
      java/demo/
        ResponseEntityControllerTest.java
~~~

### 13.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
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

Spring Boot quản lý phiên bản Spring Framework, Reactor và các thư viện liên quan thông qua dependency management. Không tự thêm một phiên bản Reactor khác nếu không có lý do tương thích rõ ràng.

### 13.3. ResponseEntityDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseEntityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseEntityDemoApplication.class, args);
    }
}
~~~

### 13.4. User.java

~~~java
package demo;

public record User(long id, String name) {
}
~~~

### 13.5. CreateUserRequest.java

~~~java
package demo;

public record CreateUserRequest(String name) {
}
~~~

### 13.6. UserService.java

~~~java
package demo;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class UserService {
    public Mono<User> findById(long id) {
        if (id == 1L) {
            return Mono.just(new User(1L, "Mai"));
        }
        return Mono.empty();
    }

    public Mono<User> create(CreateUserRequest request) {
        return Mono.just(new User(2L, request.name()));
    }

    public Flux<String> events() {
        return Flux.just("created", "updated");
    }
}
~~~

Đây là service in-memory để demo. Trong ứng dụng thật, các method có thể gọi repository reactive, WebClient hoặc một publisher khác.

### 13.7. UserController.java

~~~java
package demo;

import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class UserController {
    private final UserService service;

    public UserController(UserService service) {
        this.service = service;
    }

    // Outer Mono quyết định response sau khi lookup hoàn tất.
    @GetMapping("/users/{id}")
    public Mono<ResponseEntity<User>> find(@PathVariable long id) {
        return service.findById(id)
            .map(user -> ResponseEntity.ok(user))
            .defaultIfEmpty(ResponseEntity.<User>notFound().build());
    }

    // Status/header được chọn ngay; body publisher có thể empty.
    @GetMapping("/users/{id}/body-only")
    public ResponseEntity<Mono<User>> bodyOnly(@PathVariable long id) {
        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Response-Mode", "body-only")
            .body(service.findById(id));
    }

    // Status 201 và Location được tạo sau khi có resource ID.
    @PostMapping("/users")
    public Mono<ResponseEntity<User>> create(
            @RequestBody CreateUserRequest request) {
        return service.create(request)
            .map(user -> ResponseEntity
                .created(URI.create("/users/" + user.id()))
                .body(user));
    }

    // Status/header cố định; Flux body được ghi theo stream.
    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<String>>> events() {
        Flux<ServerSentEvent<String>> body = service.events()
            .map(value -> ServerSentEvent.builder(value)
                .event("status")
                .build());

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .header("X-Stream-Mode", "live")
            .body(body);
    }
}
~~~

### 13.8. Chạy ứng dụng

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Nếu đã cài Gradle:

~~~bash
gradle bootRun
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/users/1
curl -i http://localhost:8080/users/99
curl -i http://localhost:8080/users/99/body-only
curl -i -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -d '{"name":"An"}'
curl -N -i http://localhost:8080/events
~~~

Các kết quả chính cần quan sát:

| Request | Status dự kiến | Body/headers |
| --- | --- | --- |
| GET /users/1 | 200 | JSON user Mai |
| GET /users/99 | 404 | Không có user body |
| GET /users/99/body-only | 200 | Body rỗng, có X-Response-Mode: body-only |
| POST /users | 201 | JSON user An và Location /users/2 |
| GET /events | 200 | text/event-stream, hai event status |

Endpoint /users/99/body-only cố ý cho thấy sự khác biệt: controller chọn 200 trước khi body được subscribe; body empty không tự thay status thành 404.

## 14. Kiểm thử bằng WebTestClient và JUnit 5

Tạo src/test/java/demo/ResponseEntityControllerTest.java:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ResponseEntityControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void foundResourceReturns200AndBody() {
        client.get()
            .uri("/users/1")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(User.class)
            .isEqualTo(new User(1L, "Mai"));
    }

    @Test
    void missingResourceReturns404() {
        client.get()
            .uri("/users/99")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .isEmpty();
    }

    @Test
    void emptyReactiveBodyDoesNotChangePreselectedStatus() {
        client.get()
            .uri("/users/99/body-only")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-Response-Mode", "body-only")
            .expectBody()
            .isEmpty();
    }

    @Test
    void createReturns201AndLocation() {
        client.post()
            .uri("/users")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateUserRequest("An"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody(User.class)
            .isEqualTo(new User(2L, "An"));
    }

    @Test
    void eventEndpointDeclaresStreamingContentType() {
        client.get()
            .uri("/events")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM
            )
            .expectHeader().valueEquals("X-Stream-Mode", "live");
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Hoặc:

~~~bash
gradle test
~~~

Năm test kiểm tra status, body, header và sự khác biệt giữa outer Mono và inner Mono. Test SSE kiểm tra metadata; nếu cần kiểm thử từng event và cancellation, có thể dùng returnResult(ServerSentEvent.class) hoặc một client streaming phù hợp, rồi xác minh từng event thay vì chỉ kiểm tra header.

Không cần Thread.sleep để test response body reactive. WebTestClient chờ response theo contract của exchange và assertions; nếu test một publisher có timer, dùng virtual time ở lớp Reactor unit test hoặc cấu hình timeout rõ ràng.

## 15. Khi nào dùng ResponseEntity, khi nào dùng ResponseStatusException?

Có hai cách phổ biến để biểu đạt lỗi.

**Trả ResponseEntity trực tiếp:**

~~~java
return Mono.just(ResponseEntity.status(HttpStatus.CONFLICT)
    .body(errorBody));
~~~

Phù hợp khi lỗi là một nhánh kết quả bình thường của endpoint và cần điều khiển headers/body cụ thể.

**Ném exception và để exception handler map:**

~~~java
return service.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));
~~~

Sau đó @RestControllerAdvice map UserNotFoundException sang 404. Phù hợp khi muốn tập trung hóa chính sách lỗi và không muốn mọi controller tự dựng response.

ResponseStatusException cũng có thể biểu đạt status cụ thể:

~~~java
return Mono.error(new ResponseStatusException(
    HttpStatus.NOT_FOUND,
    "User not found"
));
~~~

Không nên trộn nhiều cách tùy tiện. Chọn một quy ước nhất quán cho lỗi domain, validation, authentication/authorization và lỗi hạ tầng.

## 16. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng ResponseEntity<Mono<User>> rồi mong body empty tự thành 404 | Status đã được chọn là 200 | Dùng Mono<ResponseEntity<User>> nếu lookup quyết định status |
| Dùng Mono<ResponseEntity<User>> nhưng quên xử lý source empty | Không phát ResponseEntity; response không biểu đạt rõ resource absence | defaultIfEmpty(notFound().build()) hoặc switchIfEmpty |
| Nghĩ tạo ResponseEntity là response đã gửi qua network | Framework còn phải xử lý metadata và ghi body | Phân biệt entity creation với response commit |
| Đổi status sau khi stream body đã bắt đầu | HTTP headers đã commit; status không thể thay đổi | Chọn status trước stream, xử lý lỗi body theo protocol |
| Dùng ResponseEntity<Flux<T>> rồi collectList() toàn bộ stream | Mất lợi ích streaming và tăng RAM/latency | Return Flux trực tiếp nếu contract là stream |
| Đặt Content-Type không tương thích body codec | Client không giải mã đúng hoặc server không ghi được | Chọn media type phù hợp với body và message writer |
| Trả body cho 204 No Content | Vi phạm semantics HTTP | Dùng ResponseEntity<Void> và noContent().build() |
| Dùng ResponseEntity.ok(service.block()) trong WebFlux | Chặn event-loop | Compose Mono/Flux và return reactive type |
| Gắn Location trước khi create hoàn tất | Location có thể sai hoặc ID chưa tồn tại | Tạo ResponseEntity sau khi service trả resource |
| Catch mọi lỗi và trả 400 | Che giấu lỗi server hoặc lỗi lập trình | Map từng loại exception theo contract |
| Dùng ResponseEntity<Mono<T>> cho endpoint cần chọn status theo body | Không thể đổi status khi body empty sau đó | Dùng outer Mono<ResponseEntity<T>> |
| Nghĩ body publisher error luôn đổi status thành 500 | Nếu response đã commit, status cũ không đổi | Đưa lỗi có thể biết trước ra trước commit; thiết kế stream error |
| Đặt Content-Length thủ công cho stream vô hạn | Header sai, client/proxy xử lý không đúng | Để server quản lý framing streaming |
| Dùng Mono.empty() để biểu diễn lỗi | Empty là hoàn tất bình thường, không phải onError | Trả 404/fallback hoặc phát error theo contract |
| Dùng ResponseEntity ở mọi endpoint | Tăng boilerplate khi không cần custom metadata | Return Mono<T>/Flux<T> nếu mặc định đủ |

## 17. Checklist thiết kế response

Trước khi hoàn thành một endpoint, trả lời các câu hỏi:

1. Status có biết ngay khi controller được gọi không?
2. Nếu cần lookup bất đồng bộ, kết quả có quyết định 200/404/409 không?
3. Header có phụ thuộc ID/version/data được tạo sau này không?
4. Body là giá trị đơn, publisher đơn hay stream nhiều phần tử?
5. Nếu body publisher empty, status mong đợi là gì?
6. Nếu body publisher lỗi trước commit, error handler nào xử lý?
7. Nếu stream lỗi sau commit, client sẽ nhận dấu hiệu gì?
8. Có cần 201 + Location, 204 không body, ETag hoặc Cache-Control không?
9. Body có đúng codec/content type không?
10. Có blocking call hoặc block() trong request path không?
11. Response có lộ thông tin nhạy cảm trong headers/body/error detail không?
12. Đã test status, headers, body-empty, error và cancellation bằng WebTestClient/StepVerifier chưa?

| Yêu cầu | Kiểu return gợi ý |
| --- | --- |
| Lookup quyết định 200 hay 404 | Mono<ResponseEntity<T>> |
| Create trả 201 + Location theo ID | Mono<ResponseEntity<T>> |
| Metadata cố định, body bất đồng bộ | ResponseEntity<Mono<T>> |
| Metadata cố định, body streaming | ResponseEntity<Flux<T>> |
| Giá trị có sẵn, custom header | ResponseEntity<T> |
| Body reactive, status mặc định đủ | Mono<T> hoặc Flux<T> |
| Command hoàn tất, 204 | Mono<ResponseEntity<Void>> hoặc Mono<Void> theo contract |

## 18. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** ResponseEntity<Mono<User>> chứa Mono.empty() và được tạo bằng ResponseEntity.ok(). Status có tự thành 404 không?

**Đáp án:** Không. Status đã được chọn là 200; body empty chỉ có nghĩa không phát body value.

**Câu 2.** Kiểu nào phù hợp khi kết quả lookup quyết định status 200 hoặc 404?

**Đáp án:** Mono<ResponseEntity<User>>, vì outer Mono có thể phát ResponseEntity sau khi lookup cho biết có dữ liệu hay không.

**Câu 3.** ResponseEntity<Flux<Event>> trả stream và event thứ 10 phát lỗi sau khi đã gửi 9 event. Có thể đổi status 200 thành 500 không?

**Đáp án:** Không nếu response đã commit. Client có thể nhận stream bị kết thúc giữa chừng; cần logging và protocol-level error handling phù hợp.

**Câu 4.** Tại sao ResponseEntity.created(location).body(user) thường được tạo bên trong map sau khi create hoàn tất?

**Đáp án:** Vì ID/URI chính thức chỉ có sau khi lưu thành công; lúc đó mới biết Location đúng và có thể phát 201.

**Câu 5.** Khi nào ResponseEntity<Mono<T>> là lựa chọn hợp lý?

**Đáp án:** Khi status và headers được biết trước, còn body đến bất đồng bộ, ví dụ một endpoint luôn trả 200 với một body publisher.

**Câu 6.** Mono.empty() và Mono.error(ex) khác nhau như thế nào?

**Đáp án:** Empty là hoàn tất bình thường không có phần tử; error là terminal signal thất bại. Controller phải chọn 404/fallback cho empty theo nghiệp vụ và map error theo loại exception.

**Câu 7.** Vì sao không nên dùng block() trong controller WebFlux?

**Đáp án:** Nó chặn thread gọi, có thể là event-loop non-blocking, làm giảm khả năng phục vụ request và có thể bị Reactor từ chối.

**Câu 8.** Header Location thường xuất hiện cùng status nào khi tạo resource?

**Đáp án:** Thường là 201 Created. URI cần trỏ tới resource vừa tạo theo hợp đồng API.

**Câu 9.** Một lỗi xảy ra trong outer Mono<ResponseEntity<T>> trước khi ResponseEntity được phát. Nó có thể được exception handler map sang 500 không?

**Đáp án:** Có, nếu response chưa commit và handler phù hợp. Khi lỗi xảy ra sau khi response đã commit thì không thể thay status/header đã gửi.

**Câu 10.** Nếu endpoint trả một list rỗng hợp lệ, có nhất thiết phải dùng 404 không?

**Đáp án:** Không. Với collection search, 200 và list rỗng thường là kết quả hợp lệ; 404 thường dành cho resource định danh cụ thể không tồn tại.

## 19. Ghi nhớ và tài liệu tham khảo

- ResponseEntity biểu diễn status, headers và body; nó không tự ghi HTTP bytes ngay khi được tạo.
- Mono<ResponseEntity<T>> cho phép **chờ kết quả để chọn metadata**.
- ResponseEntity<Mono<T>> và ResponseEntity<Flux<T>> cho phép **chọn metadata trước, ghi body reactive sau**.
- Body empty không tự đồng nghĩa 404; phải định nghĩa semantics endpoint.
- Sau khi response commit, status và headers đã gửi không thể đổi; lỗi streaming sau commit phải được xử lý theo contract stream/transport.
- Dùng ResponseEntity khi cần custom status/header/body semantics; nếu không, Mono<T>/Flux<T> thường đơn giản hơn.
- Không dùng block() trong reactive request handler; không để blocking I/O chạy trên event-loop.

Tài liệu chính thức:

1. [Spring Framework Reference — WebFlux Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): semantics của ResponseEntity, Mono<ResponseEntity<T>>, ResponseEntity<Mono<T>> và ResponseEntity<Flux<T>>.
2. [Spring Framework Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): builders, status, headers và body.
3. [Spring Framework Reference — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html): @ExceptionHandler và @ControllerAdvice.
4. [Spring Framework Reference — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): ghi body bằng reactive codecs.
5. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử WebFlux endpoint.
6. [Project Reactor Reference — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): xử lý onError, fallback và terminal signals.
