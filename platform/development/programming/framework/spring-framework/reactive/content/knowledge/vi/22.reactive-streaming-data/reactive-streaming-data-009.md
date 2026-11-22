# Giới hạn sửa HTTP status và báo lỗi giữa một luồng đang phát trong Spring WebFlux

Trong một HTTP response thông thường, server chuẩn bị status, headers rồi ghi body. Với response streaming, body được gửi thành nhiều phần theo thời gian. Sau khi server đã gửi headers hoặc byte đầu tiên và response được **commit**, status và headers đã trở thành một phần của response trên network. Server không thể đổi status từ 200 thành 500 chỉ vì publisher phát lỗi ở giữa luồng.

Đây là giới hạn quan trọng khi xây dựng endpoint trả về Flux, NDJSON hoặc Server-Sent Events (SSE). Một lỗi từ Reactor publisher vẫn là tín hiệu lỗi kết thúc stream, nhưng nếu response đã commit thì framework không thể quay ngược lại để thay status line hay thay body đã gửi. Ứng dụng phải quyết định trước cách biểu diễn lỗi giữa luồng: gửi một record lỗi theo giao thức, kết thúc kết nối, hoặc cho client tiếp tục từ checkpoint.

Bài học thuộc nhóm **Truyền dữ liệu liên tục**, tập trung vào ranh giới commit của HTTP response, khả năng sửa status trước/sau commit, cách xử lý lỗi reactive và hợp đồng báo lỗi cho client đang đọc stream.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích response commit và thời điểm status/header không còn thay đổi được.
- Dùng ServerHttpResponse.isCommitted() và setStatusCode() đúng cách.
- Đăng ký callback beforeCommit để chuẩn bị status/header trước khi response được gửi.
- Phân biệt lỗi xảy ra trước khi ghi body với lỗi xảy ra sau khi stream đã phát dữ liệu.
- Hiểu vì sao @ExceptionHandler hoặc WebExceptionHandler không thể thay một response đã commit.
- Phân biệt doOnError, onErrorMap, onErrorResume và retryWhen.
- Thiết kế error record cho NDJSON hoặc error event cho SSE.
- Xử lý lỗi preflight bằng Mono<ResponseEntity<Flux<T>>>.
- Hiểu rủi ro của JSON array bị ngắt giữa chừng.
- Thiết kế cancellation, logging, checkpoint và reconnect cho stream.
- Viết ví dụ Java 17+ Spring Boot WebFlux với WebTestClient.

## 2. HTTP response có ranh giới commit

Một HTTP response gồm status code, headers và body. Server phải gửi status và headers trước body. Khi metadata này được ghi ra network, response đã commit.

~~~text
Trước commit
    |
    | Có thể chọn status
    | Có thể sửa headers
    | Có thể chuyển lỗi thành response khác
    v
Commit response
    |
    | Status + headers được gửi
    v
Đang ghi body / stream
    |
    | Có thể gửi thêm dữ liệu theo giao thức
    | Có thể phát hiện lỗi và log
    | Không thể thay status/header đã gửi
    v
Hoàn tất hoặc kết nối bị kết thúc
~~~

Với WebFlux, response thường được commit khi framework bắt đầu ghi body hoặc flush headers. Đối với stream, thời điểm này có thể đến ngay khi phần tử đầu tiên được ghi. Controller method có thể đã trả về một Flux từ trước, nhưng publisher chỉ được subscribe trong quá trình framework ghi response.

Cần phân biệt:

- **Controller method đã return:** method Java đã trả về publisher.
- **Publisher đã emit:** upstream đã phát một hoặc nhiều phần tử.
- **Response đã commit:** status và headers đã được gửi; từ thời điểm này không thể thay đổi chúng.

Ba sự kiện liên quan nhưng không đồng nghĩa. Một Flux có thể được tạo trước, subscribe sau, rồi mới phát phần tử đầu tiên. Lỗi trong publisher có thể xảy ra trước commit hoặc sau commit tùy thời điểm ghi dữ liệu và cách writer xử lý media type.

### ServerHttpResponse cung cấp API nào?

| API | Ý nghĩa |
| --- | --- |
| isCommitted() | Cho biết response đã commit hay chưa |
| setStatusCode(status) | Đặt status nếu response chưa commit; trả boolean cho biết có đặt được hay không |
| getStatusCode() | Đọc status hiện tại |
| getHeaders() | Truy cập response headers |
| beforeCommit(action) | Đăng ký công việc chạy trước khi response commit |
| writeWith(body) | Ghi publisher DataBuffer vào body |
| writeAndFlushWith(body) | Ghi các nhóm DataBuffer và flush theo nhóm |
| setComplete() | Hoàn tất response mà không ghi thêm body |

Điểm quan trọng là **setStatusCode trả boolean**. Nếu trả false, status không được thay đổi, thường vì response đã commit. Không nên gọi setStatusCode rồi mặc định rằng status mới đã được áp dụng.

~~~java
ServerHttpResponse response = exchange.getResponse();

boolean changed = response.setStatusCode(HttpStatus.BAD_GATEWAY);

if (!changed) {
    log.warn("Response already committed; status cannot be changed");
}
~~~

Đây là fragment minh họa; cần import HttpStatus và cấu hình logger. Khi có thể, hãy chọn status trước khi bắt đầu ghi body thay vì chờ tới khi lỗi xảy ra.

## 3. beforeCommit: chuẩn bị status và headers trước khi gửi

ServerHttpResponse.beforeCommit nhận một Supplier trả về Mono<Void>. Callback chạy ngay trước khi response commit. Đây là nơi phù hợp để thêm header cuối cùng hoặc hoàn tất metadata phụ thuộc kết quả xử lý.

~~~java
response.beforeCommit(() ->
    Mono.fromRunnable(() ->
        response.getHeaders().set("X-Stream-State", "starting")));
~~~

Hành động cần được đặt bên trong publisher được trả về từ callback. Cách này giúp framework thực thi công việc theo lifecycle commit. Không gọi một side effect bất đồng bộ bên ngoài publisher rồi mong framework chờ nó hoàn tất.

Có thể đặt status trong callback nếu status vẫn chưa được chọn:

~~~java
response.beforeCommit(() ->
    Mono.fromRunnable(() -> {
        response.setStatusCode(HttpStatus.ACCEPTED);
        response.getHeaders().set("X-Stream-State", "ready");
    }));
~~~

Trong phần lớn controller, cách dễ đọc hơn là dùng ResponseEntity để khai báo status và headers ngay khi tạo response:

~~~java
return ResponseEntity.accepted()
    .header("X-Stream-State", "ready")
    .body(eventFlux);
~~~

Nếu cần kiểm tra một điều kiện bất đồng bộ trước khi bắt đầu stream, có thể trả về Mono<ResponseEntity<Flux<T>>>. Phần Mono quyết định response metadata; Flux bên trong là body được ghi sau đó.

~~~java
public Mono<ResponseEntity<Flux<Event>>> stream() {
    return verifySourceIsAvailable()
        .then(Mono.fromSupplier(() ->
            ResponseEntity.ok()
                .contentType(MediaType.valueOf("application/x-ndjson"))
                .body(eventSource())));
}
~~~

Nếu verifySourceIsAvailable() thất bại trước khi ResponseEntity được tạo và response commit, exception handler vẫn có thể trả 503 hoặc response lỗi khác. Nếu eventSource() thất bại sau khi đã phát record đầu tiên, status đã được gửi và không thể đổi.

**Preflight chỉ xác nhận điều kiện tại thời điểm kiểm tra.** Nó không bảo đảm nguồn dữ liệu sẽ không lỗi trong tương lai. Một stream dài vẫn cần chính sách lỗi giữa luồng.

## 4. Lỗi trước commit và lỗi sau commit

Hai tình huống này cần cách xử lý khác nhau.

### Lỗi trước khi response commit

Ví dụ:

- Không tìm thấy stream source.
- Không đủ quyền truy cập.
- Tham số truy vấn không hợp lệ.
- Không thể mở kết nối tới upstream.
- Kiểm tra quota hoặc trạng thái nghiệp vụ thất bại.

Trong các trường hợp này, server chưa gửi status/headers/body. Có thể trả một response lỗi thông thường:

~~~java
@ExceptionHandler(StreamUnavailableException.class)
public ResponseEntity<ApiError> handleUnavailable(
        StreamUnavailableException exception) {

    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .body(new ApiError(
            "STREAM_UNAVAILABLE",
            "The stream source is temporarily unavailable"));
}
~~~

Spring WebFlux có thể chuyển exception tới @ExceptionHandler/@RestControllerAdvice hoặc WebExceptionHandler. Nếu response chưa commit, cơ chế này có thể tạo response thay thế với status phù hợp.

### Lỗi sau khi response commit

Ví dụ:

- Upstream database hoặc message broker ngắt kết nối sau khi đã gửi vài event.
- Một record tiếp theo không giải mã được.
- Remote API phát lỗi giữa stream.
- Một phép biến đổi reactive thất bại sau khi client đã nhận dữ liệu.

Khi đó status đã được gửi. Không thể đổi 200 thành 500 hoặc thay body đã phát bằng JSON error object mới.

~~~text
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"type":"data","id":"evt-1"}
{"type":"data","id":"evt-2"}
<upstream fails here>
~~~

Nếu không có recovery, client có thể nhận stream bị kết thúc bất thường sau record thứ hai. HTTP status vẫn là 200 vì đó là status đã được gửi khi stream bắt đầu.

Có thể log lỗi, đóng kết nối hoặc gửi một record lỗi theo hợp đồng NDJSON/SSE. Lựa chọn phụ thuộc vào việc client có thể hiểu và xử lý một error event trong cùng stream hay không.

### Exception handler không thể quay ngược response

@RestControllerAdvice rất hữu ích cho lỗi xảy ra trước commit. Nhưng khi body publisher đã bắt đầu ghi, việc exception đi tới error handler không có nghĩa framework có thể gửi một response mới.

Tùy server và thời điểm lỗi, WebFlux có thể log lỗi, kết thúc quá trình ghi body hoặc đóng kết nối. Client có thể nhận body một phần hoặc một stream bị truncate. Không được giả định client sẽ nhìn thấy một JSON error response mới hoặc status 500.

## 5. Reactor error signal và các operator thường dùng

Trong Reactor, error là một terminal signal. Sau khi publisher phát onError, publisher đó không tiếp tục phát onNext như bình thường. Muốn tiếp tục, ứng dụng phải thay nguồn bằng một publisher khác hoặc chuyển lỗi thành một giá trị thuộc domain.

| Operator | Vai trò | Có thay lỗi bằng dữ liệu không? |
| --- | --- | --- |
| doOnError | Quan sát lỗi để log/metric | Không |
| onErrorMap | Đổi loại exception | Không; vẫn phát onError |
| onErrorResume | Chuyển sang publisher dự phòng | Có thể |
| retryWhen | Subscribe lại nguồn theo policy | Không trực tiếp; có thể phát lại dữ liệu |

### doOnError chỉ quan sát

~~~java
Flux<Event> events = upstream
    .doOnError(error ->
        log.error("Stream failed", error));
~~~

doOnError không xử lý lỗi. Sau khi log, lỗi vẫn truyền xuống downstream và kết thúc publisher. Nếu response đã commit, chỉ thêm log không thể tạo status 500.

### onErrorMap đổi exception nhưng không phục hồi

~~~java
Flux<Event> events = upstream
    .onErrorMap(
        IOException.class,
        error -> new UpstreamUnavailableException(error));
~~~

onErrorMap hữu ích để chuyển lỗi kỹ thuật thành exception có ngữ nghĩa của ứng dụng. Nó vẫn phát onError, nên nếu không có operator xử lý tiếp, response body stream vẫn kết thúc do lỗi.

### onErrorResume thay publisher khi lỗi

~~~java
Flux<Event> events = upstream
    .onErrorResume(error -> fallbackEvents());
~~~

onErrorResume chuyển sang một publisher dự phòng. Publisher dự phòng phải phù hợp với kiểu dữ liệu downstream. Nếu response đã commit, dữ liệu dự phòng sẽ trở thành phần tiếp theo của body đã bắt đầu; nó không thay đổi status đã gửi.

Đây là cơ sở để gửi một error record cuối cùng trong NDJSON hoặc một error event trong SSE. Chỉ dùng cách này khi hợp đồng API quy định client phải nhận diện record/event lỗi.

### retryWhen có thể phát lại dữ liệu

~~~java
Flux<Event> events = upstream
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200)));
~~~

Retry có thể phù hợp khi upstream lỗi tạm thời và có khả năng subscribe lại. Nhưng nếu stream đã phát evt-1, evt-2 rồi lỗi, lần retry có thể phát lại evt-1, evt-2. Client có thể nhận dữ liệu trùng.

Chỉ retry khi nguồn có semantics replay rõ ràng, hoặc mỗi event có ID/sequence để client deduplicate và resume. Với nguồn không thể replay, retry tự động có thể làm mất hoặc nhân đôi dữ liệu.

### onErrorResume không biến cancellation thành lỗi

Khi client đóng kết nối, downstream có thể gửi cancel. Cancellation không phải onError, nên onErrorResume không phải hook để xử lý client disconnect. Dùng doOnCancel hoặc doFinally để quan sát cancellation và giải phóng tài nguyên.

~~~java
Flux<Event> events = upstream
    .doOnCancel(() -> log.info("Client cancelled stream"))
    .doFinally(signal -> log.info("Stream finished: {}", signal));
~~~

doFinally nhận cả COMPLETE, ERROR và CANCEL. Không giữ socket, subscription hoặc tài nguyên ngoài lifecycle khi client đã hủy.

## 6. Báo lỗi trong NDJSON bằng một record thuộc giao thức

NDJSON biểu diễn mỗi record bằng một JSON value trên một dòng. Khi stream bị lỗi sau một vài record, server có thể phát một record cuối cùng mô tả lỗi, nếu schema của stream cho phép.

~~~text
{"type":"data","id":"evt-1","code":null}
{"type":"data","id":"evt-2","code":null}
{"type":"error","id":null,"code":"UPSTREAM_INTERRUPTED"}
~~~

Client đọc từng dòng, phân biệt type=data và type=error. HTTP status vẫn là 200 vì response đã commit khi bắt đầu stream. Error record là **dữ liệu của giao thức ứng dụng**, không phải một HTTP error response mới.

Một kiểu dữ liệu rõ ràng:

~~~java
public record StreamMessage(
    String type,
    String id,
    String code
) {
    public static StreamMessage data(String id) {
        return new StreamMessage("data", id, null);
    }

    public static StreamMessage error(String code) {
        return new StreamMessage("error", null, code);
    }
}
~~~

Publisher có thể chuyển lỗi thành record cuối:

~~~java
Flux<StreamMessage> messages = upstreamEvents
    .map(event -> StreamMessage.data(event.id()))
    .onErrorResume(error -> {
        log.warn("Event stream interrupted", error);
        return Flux.just(
            StreamMessage.error("UPSTREAM_INTERRUPTED"));
    });
~~~

Điều này tạo một stream hoàn chỉnh theo schema NDJSON. Client vẫn cần kiểm tra type của mỗi record và không coi error record là dữ liệu nghiệp vụ bình thường.

### Chọn mã lỗi ổn định

Không gửi nguyên exception message hoặc stack trace cho client. Hãy gửi mã lỗi ổn định, ví dụ:

- UPSTREAM_INTERRUPTED
- SOURCE_TEMPORARILY_UNAVAILABLE
- STREAM_CHECKPOINT_EXPIRED
- STREAM_RATE_LIMITED

Thông tin kỹ thuật chi tiết nên được ghi log phía server cùng correlation ID. Client có thể hiển thị message thân thiện hoặc quyết định retry theo code.

### Không dùng error record nếu client không biết schema đó

Nếu API đã công bố NDJSON chỉ chứa Event, đột nhiên gửi một JSON object có cấu trúc khác có thể làm client decode thất bại. Hãy định nghĩa một envelope từ đầu, ví dụ mọi record đều có type, payload và error, hoặc định nghĩa một union schema được client hiểu rõ.

## 7. Báo lỗi trong Server-Sent Events

SSE là giao thức streaming qua text/event-stream. Một event có thể có event name, ID, retry hint và data. Vì thế, có thể định nghĩa một event riêng cho lỗi giữa stream.

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<StreamMessage>> events() {
    return upstreamEvents()
        .map(event -> ServerSentEvent.builder(
                StreamMessage.data(event.id()))
            .id(event.id())
            .event("message")
            .build())
        .onErrorResume(error -> Flux.just(
            ServerSentEvent.builder(
                    StreamMessage.error("UPSTREAM_INTERRUPTED"))
                .event("stream-error")
                .build()));
}
~~~

Trong ví dụ, event dữ liệu dùng event name message. Khi upstream lỗi, publisher phát một SSE có event name stream-error rồi hoàn tất. HTTP status vẫn là status ban đầu.

Client JavaScript có thể đăng ký event riêng:

~~~javascript
const source = new EventSource("/events");

source.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  console.log("data", message);
});

source.addEventListener("stream-error", event => {
  const message = JSON.parse(event.data);
  console.error("stream interrupted", message.code);
});
~~~

Đây là client-side minh họa. EventSource cũng có event error riêng liên quan tới kết nối/trạng thái transport; event nghiệp vụ stream-error do server định nghĩa là một thông điệp trong giao thức. Hai loại này không giống nhau.

### ID và resume

SSE hỗ trợ event ID. Nếu server gắn ID tăng dần hoặc cursor có thể replay, client có thể reconnect và gửi Last-Event-ID để tiếp tục từ vị trí phù hợp. Điều này cần server giữ được checkpoint hoặc có thể truy vấn lại event sau ID đó.

Không phát ID tùy tiện nếu không có semantics resume. Một ID chỉ hữu ích khi server biết cách tiếp tục mà không bỏ sót hoặc phát trùng dữ liệu.

## 8. Vì sao JSON array có thể bị hỏng khi stream lỗi?

Một Flux<Event> trả về với application/json thường được Jackson encoder thu thành một List rồi serialize thành một JSON array. Client nhận một JSON document hoàn chỉnh khi quá trình ghi hoàn tất.

Nếu hệ thống thực sự stream JSON array theo từng phần, lỗi sau khi gửi một vài phần tử có thể để lại body dang dở:

~~~text
[
  {"id":"evt-1"},
  {"id":"evt-2"},
~~~

Đây không phải JSON document hợp lệ vì dấu đóng array và phần còn lại chưa được gửi. Client parser có thể báo lỗi cú pháp hoặc unexpected end-of-input.

Cần phân biệt hai trường hợp:

- Với encoder mặc định gom Flux thành List cho application/json, dữ liệu có thể được buffer trước khi ghi; điều này giảm khả năng stream từng phần nhưng tăng bộ nhớ và có thể trì hoãn response.
- Với media type streaming như application/x-ndjson hoặc text/event-stream, mỗi record/event có thể được ghi và flush độc lập. Lỗi giữa luồng có thể được biểu diễn bằng record/event cuối hoặc bằng việc kết thúc kết nối.

Không chọn application/json array nếu yêu cầu sản phẩm là gửi record liên tục theo thời gian và client cần xử lý từng record ngay khi nhận. Hãy chọn NDJSON hoặc SSE với schema lỗi được công bố.

## 9. Khi nào nên trả status lỗi và khi nào nên phát error record?

| Tình huống | Cách xử lý phù hợp |
| --- | --- |
| Không xác thực được request trước khi stream | Trả 401/403 trước commit |
| Không có quyền xem tài nguyên | Trả 403 trước commit |
| Nguồn stream chưa sẵn sàng | Trả 503 trước commit |
| Query/filter không hợp lệ | Trả 400 trước commit |
| Upstream lỗi trước khi có response body | Dùng exception handler trả status lỗi nếu response chưa commit |
| Upstream lỗi sau khi đã gửi record | Error record NDJSON, SSE error event, hoặc kết thúc kết nối theo hợp đồng |
| Client đóng kết nối | Hủy upstream và giải phóng tài nguyên; không cố gửi error record |
| Hết thời gian chờ trước commit | Có thể trả 504 nếu response chưa commit |
| Hết thời gian chờ sau commit | Ghi nhận lỗi và kết thúc hoặc phát tín hiệu lỗi trong stream |

Quyết định này phải được thiết kế ở API contract. Client cần biết lỗi được thể hiện bằng status HTTP, record cuối, event riêng hay kết nối bị đóng. Không nên để client phải đoán dựa trên việc stream đột ngột dừng.

## 10. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này có bốn endpoint:

- GET /streams/preflight: kiểm tra nguồn trước khi tạo response; nếu không sẵn sàng, trả 503 qua exception advice.
- GET /streams/ndjson: phát hai record dữ liệu rồi mô phỏng upstream lỗi; lỗi được chuyển thành record NDJSON cuối.
- GET /streams/sse: phát một event dữ liệu rồi mô phỏng lỗi; lỗi được chuyển thành SSE event tên stream-error.
- GET /streams/accepted: chọn status 202 và thêm response header bằng beforeCommit trước khi body bắt đầu ghi.

### Cấu trúc project

~~~text
webflux-stream-error-demo/
├── pom.xml
└── src
    ├── main/java/com/example/stream
    │   ├── StreamDemoApplication.java
    │   ├── StreamController.java
    │   ├── StreamMessage.java
    │   ├── ApiError.java
    │   └── StreamExceptionAdvice.java
    └── test/java/com/example/stream
        └── StreamControllerTests.java
~~~

### pom.xml

~~~xml
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

  <groupId>com.example</groupId>
  <artifactId>webflux-stream-error-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

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
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
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
~~~

Spring Boot 3.3.5 quản lý các phiên bản Spring Framework, Reactor và Jackson tương thích. Ví dụ dùng Java 17 và Spring WebFlux.

### StreamDemoApplication.java

~~~java
package com.example.stream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamDemoApplication.class, args);
    }
}
~~~

### StreamMessage.java

~~~java
package com.example.stream;

public record StreamMessage(
    String type,
    String id,
    String code
) {
    public static StreamMessage data(String id) {
        return new StreamMessage("data", id, null);
    }

    public static StreamMessage error(String code) {
        return new StreamMessage("error", null, code);
    }
}
~~~

### ApiError.java

~~~java
package com.example.stream;

public record ApiError(String code, String message) {
}
~~~

### StreamController.java

~~~java
package com.example.stream;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/streams")
public class StreamController {

    private static final Logger log =
        LoggerFactory.getLogger(StreamController.class);

    private static final String NDJSON_VALUE =
        "application/x-ndjson";

    private static final MediaType NDJSON =
        MediaType.valueOf(NDJSON_VALUE);

    @GetMapping("/preflight")
    public Mono<ResponseEntity<Flux<StreamMessage>>> preflight() {
        return verifySource()
            .then(Mono.fromSupplier(() ->
                ResponseEntity.ok()
                    .contentType(NDJSON)
                    .body(Flux.just(StreamMessage.data("evt-ready")))));
    }

    private Mono<Void> verifySource() {
        return Mono.error(new StreamUnavailableException());
    }

    @GetMapping(
        value = "/ndjson",
        produces = NDJSON_VALUE)
    public Flux<StreamMessage> ndjson() {
        return simulatedMessages()
            .onErrorResume(StreamInterruptedException.class, error -> {
                log.warn("NDJSON source interrupted", error);
                return Flux.just(
                    StreamMessage.error("UPSTREAM_INTERRUPTED"));
            });
    }

    private Flux<StreamMessage> simulatedMessages() {
        return Flux.concat(
            Flux.just(
                StreamMessage.data("evt-1"),
                StreamMessage.data("evt-2")),
            Mono.<StreamMessage>error(
                new StreamInterruptedException()));
    }

    @GetMapping(
        value = "/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<StreamMessage>> sse() {
        Flux<ServerSentEvent<StreamMessage>> source = Flux.concat(
            Flux.just(
                ServerSentEvent.builder(StreamMessage.data("evt-1"))
                    .id("1")
                    .event("message")
                    .build()),
            Mono.<ServerSentEvent<StreamMessage>>error(
                new StreamInterruptedException()));

        return source.onErrorResume(
            StreamInterruptedException.class,
            error -> {
                log.warn("SSE source interrupted", error);
                return Flux.just(
                    ServerSentEvent.builder(
                            StreamMessage.error("UPSTREAM_INTERRUPTED"))
                        .id("2")
                        .event("stream-error")
                        .build());
            });
    }

    @GetMapping(
        value = "/accepted",
        produces = NDJSON_VALUE)
    public ResponseEntity<Flux<StreamMessage>> accepted(
            ServerHttpResponse response) {

        response.beforeCommit(() ->
            Mono.fromRunnable(() ->
                response.getHeaders().set(
                    "X-Stream-State", "starting")));

        return ResponseEntity.accepted()
            .contentType(NDJSON)
            .body(Flux.just(StreamMessage.data("evt-accepted")));
    }
}

class StreamUnavailableException extends RuntimeException {
}

class StreamInterruptedException extends RuntimeException {
}
~~~

Điểm cần chú ý:

1. **preflight** mô phỏng lỗi trước khi ResponseEntity được tạo. Mono phát lỗi nên StreamExceptionAdvice có thể trả 503 khi response chưa commit.
2. **ndjson** phát hai record rồi phát lỗi. onErrorResume thay tín hiệu lỗi bằng một StreamMessage có type=error. Client nhận ba dòng NDJSON; status vẫn là 200.
3. **sse** phát một event message rồi một event stream-error. Tên event giúp client phân biệt dữ liệu với thông báo lỗi của stream.
4. **accepted** khai báo status 202 bằng ResponseEntity và thêm header trong beforeCommit. Callback chạy trước khi status/header được gửi.
5. Hai exception mô phỏng được đặt package-private cùng file để giữ ví dụ gọn. Trong ứng dụng thật, có thể đặt exception ở package riêng.

### StreamExceptionAdvice.java

~~~java
package com.example.stream;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class StreamExceptionAdvice {

    @ExceptionHandler(StreamUnavailableException.class)
    public ResponseEntity<ApiError> unavailable(
            StreamUnavailableException exception) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError(
                "STREAM_UNAVAILABLE",
                "The stream source is temporarily unavailable"));
    }
}
~~~

Advice xử lý lỗi preflight. Lỗi StreamInterruptedException trong body publisher được xử lý tại chính pipeline của NDJSON/SSE vì nó có thể xảy ra sau khi response đã commit.

### StreamControllerTests.java

~~~java
package com.example.stream;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@WebFluxTest(StreamController.class)
@Import(StreamExceptionAdvice.class)
class StreamControllerTests {

    private static final MediaType NDJSON =
        MediaType.valueOf("application/x-ndjson");

    @Autowired
    private WebTestClient client;

    @Test
    void preflightFailureCanReturnServiceUnavailable() {
        client.get()
            .uri("/streams/preflight")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("STREAM_UNAVAILABLE");
    }

    @Test
    void lateNdjsonFailureBecomesAnErrorRecord() {
        WebTestClient.ResponseSpec response = client.get()
            .uri("/streams/ndjson")
            .accept(NDJSON)
            .exchange()
            .expectStatus().isOk();

        response.expectHeader().contentTypeCompatibleWith(NDJSON);

        FluxExchangeResult<StreamMessage> result =
            response.returnResult(StreamMessage.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                StreamMessage.data("evt-1"),
                StreamMessage.data("evt-2"),
                StreamMessage.error("UPSTREAM_INTERRUPTED"))
            .verifyComplete();
    }

    @Test
    void beforeCommitCanSetHeaderAndResponseStatus() {
        WebTestClient.ResponseSpec response = client.get()
            .uri("/streams/accepted")
            .accept(NDJSON)
            .exchange()
            .expectStatus().isAccepted();

        response.expectHeader()
            .valueEquals("X-Stream-State", "starting");

        FluxExchangeResult<StreamMessage> result =
            response.returnResult(StreamMessage.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(StreamMessage.data("evt-accepted"))
            .verifyComplete();
    }

    @Test
    void lateSseFailureBecomesNamedErrorEvent() {
        ParameterizedTypeReference<ServerSentEvent<StreamMessage>> eventType =
            new ParameterizedTypeReference<>() {};

        FluxExchangeResult<ServerSentEvent<StreamMessage>> result =
            client.get()
                .uri("/streams/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(eventType);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "message".equals(event.event()) &&
                StreamMessage.data("evt-1").equals(event.data()))
            .expectNextMatches(event ->
                "stream-error".equals(event.event()) &&
                StreamMessage.error("UPSTREAM_INTERRUPTED")
                    .equals(event.data()))
            .verifyComplete();
    }
}
~~~

Chạy test tại thư mục có pom.xml:

~~~bash
mvn -q test
~~~

Nếu bốn test pass, Maven kết thúc với exit code 0. Các test xác minh:

- Lỗi trước commit có thể được chuyển thành HTTP 503.
- Lỗi giữa NDJSON stream được biểu diễn bằng record cuối mà không thay status 200.
- beforeCommit thêm header trước khi response được gửi và ResponseEntity giữ status 202.
- SSE stream có thể phát event stream-error để client nhận biết lỗi nguồn dữ liệu.

### Chạy ứng dụng và gọi thử

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra lỗi preflight:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/streams/preflight
~~~

Kết quả chính: HTTP 503 Service Unavailable và JSON có code STREAM_UNAVAILABLE.

Đọc NDJSON:

~~~bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/streams/ndjson
~~~

Body có ba record: evt-1, evt-2 và record error UPSTREAM_INTERRUPTED. Status của response là 200 vì stream đã bắt đầu.

Đọc SSE:

~~~bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/streams/sse
~~~

Client nhận event message, sau đó event stream-error. Tùy client, cần đọc event name và parse data để xác định lỗi.

## 11. Nếu không thể phát error record thì sao?

Không phải stream nào cũng cho phép chèn một record lỗi. Ví dụ, client chỉ chấp nhận schema Event và không có trường type/error; hoặc upstream đã hỏng đến mức không thể tạo thêm một message đáng tin cậy.

Khi đó có một số lựa chọn:

1. **Kết thúc stream:** để publisher phát lỗi và connection kết thúc. Client phải nhận biết stream chưa hoàn tất, không coi dữ liệu đã nhận là toàn bộ kết quả.
2. **Gửi terminal marker nếu giao thức đã định nghĩa:** một record cuối như type=end hoặc type=error có thể xác nhận stream kết thúc bình thường hay thất bại.
3. **Reconnect từ checkpoint:** client gửi last-seen event ID/sequence để server tiếp tục từ vị trí đã nhận.
4. **Dùng SSE event riêng:** nếu giao thức là SSE, phát event stream-error khi còn khả năng ghi.
5. **Dùng status cho lần kết nối mới:** nếu stream cũ đã commit, client có thể mở request mới và lần request mới trả 503/429/401 tùy nguyên nhân.

Không nên giả vờ stream hoàn tất thành công nếu dữ liệu bị mất. Nếu không thể gửi marker lỗi, client cần có cách phát hiện kết nối bị ngắt trước terminal marker hoặc trước khi nhận được checkpoint hoàn tất.

### Terminal marker và sequence number

Một giao thức NDJSON có thể định nghĩa các record:

~~~json
{"type":"data","sequence":41,"payload":{"id":"evt-41"}}
{"type":"data","sequence":42,"payload":{"id":"evt-42"}}
{"type":"end","lastSequence":42}
~~~

Nếu nguồn lỗi:

~~~json
{"type":"error","lastSequence":42,"code":"UPSTREAM_INTERRUPTED"}
~~~

Client biết record cuối đã được xác nhận đến sequence 42. Khi reconnect, client có thể yêu cầu sequence lớn hơn 42 nếu server hỗ trợ replay. Cách này giúp phân biệt stream kết thúc thành công, stream bị lỗi và kết nối bị cắt đột ngột.

### Không gửi HTTP status mới trong body

Một record có field status=500 chỉ là dữ liệu ứng dụng. Nó không thay thế HTTP status line đã gửi. Có thể dùng trường code hoặc type để mô tả lỗi, nhưng không gọi đó là việc đổi HTTP status.

## 12. Timeout, cancellation và tài nguyên upstream

Streaming request có thể tồn tại lâu hơn một request-response thông thường. Khi lỗi hoặc cancellation xảy ra, cần dọn tài nguyên upstream.

### Timeout trước và sau commit

Timeout trước commit có thể được chuyển thành status 504 Gateway Timeout nếu response chưa bắt đầu. Timeout sau commit không thể đổi status; hãy phát error record/event nếu giao thức hỗ trợ hoặc kết thúc kết nối.

~~~java
Flux<StreamMessage> messages = upstream
    .timeout(Duration.ofSeconds(30))
    .onErrorResume(TimeoutException.class, error ->
        Flux.just(StreamMessage.error("STREAM_TIMEOUT")));
~~~

Ví dụ này biến timeout thành record lỗi nếu publisher còn có thể ghi body. Cần chọn timeout theo semantics: timeout cho lần đầu có dữ liệu, timeout giữa hai event, hay thời hạn tổng của stream là những chính sách khác nhau.

### Client cancellation

Khi client đóng kết nối, WebFlux có thể hủy subscription. Upstream nên nhận cancellation để dừng truy vấn, listener hoặc consumer không còn cần thiết.

~~~java
Flux<Event> events = eventSource()
    .doOnCancel(() -> subscriptionRegistry.remove(requestId))
    .doFinally(signal -> metrics.record(signal));
~~~

Nếu upstream là message broker consumer, database cursor hoặc resource bên ngoài, hãy đăng ký cleanup trong using/usingWhen hoặc cơ chế lifecycle phù hợp. Không dựa vào onErrorResume để dọn cancellation vì cancel không phải error signal.

### Không giữ tài nguyên chỉ để cố gửi thông báo lỗi

Nếu socket đã đóng, việc tạo thêm error record không có ích. Hãy ưu tiên hủy upstream, release buffer, đóng cursor và ghi log đủ correlation ID để điều tra. Client có thể reconnect theo checkpoint khi dịch vụ sẵn sàng.

## 13. Logging, metrics và correlation ID

Một stream có thể kéo dài nhiều phút. Log chỉ ghi “request failed” là chưa đủ để xác định event cuối cùng đã gửi là gì.

Nên ghi nhận:

- Request/correlation ID.
- Stream ID hoặc subscription ID.
- Route và media type.
- Event ID/sequence cuối cùng đã xác nhận gửi.
- Thời gian bắt đầu, thời gian hoạt động và thời điểm kết thúc.
- Kết quả terminal: complete, error hay cancel.
- Mã lỗi ổn định, không phải toàn bộ payload.
- Số record đã gửi và số lần reconnect nếu hệ thống quản lý được.

Có thể quan sát terminal signal bằng doFinally:

~~~java
Flux<Event> stream = source
    .doOnError(error ->
        log.warn("Stream failed, streamId={}", streamId, error))
    .doOnCancel(() ->
        log.info("Stream cancelled, streamId={}", streamId))
    .doFinally(signal ->
        log.info("Stream ended, streamId={}, signal={}",
            streamId, signal));
~~~

Không ghi toàn bộ event payload vào log nếu payload có dữ liệu cá nhân hoặc bí mật. Dùng ID, sequence, error code và correlation ID để truy vết.

## 14. Các lỗi thường gặp và cách khắc phục

1. **Cố đổi status sau khi stream đã gửi byte đầu tiên.** setStatusCode có thể trả false vì response đã commit. Quyết định status trước khi ghi body.
2. **Cho rằng @ExceptionHandler luôn tạo response 500.** Advice không thể thay status/body đã commit; lỗi muộn cần giao thức báo lỗi trong stream hoặc connection termination.
3. **Dùng doOnError như một cơ chế recovery.** doOnError chỉ quan sát; lỗi vẫn kết thúc publisher.
4. **Dùng onErrorMap rồi nghĩ stream tiếp tục.** onErrorMap chỉ đổi exception; nó vẫn là terminal error.
5. **Dùng onErrorResume nhưng không định nghĩa schema lỗi.** Fallback có thể gửi một object mà client không decode được. Công bố error record/event trong hợp đồng.
6. **Gửi JSON error object vào giữa một NDJSON stream chỉ chứa Event.** Client có thể không hiểu schema mới. Dùng envelope/union schema ngay từ đầu.
7. **Gửi error record nhưng tuyên bố HTTP status đã đổi thành 500.** Record là application data; status vẫn là status đã commit.
8. **Dùng application/json cho stream cần flush từng phần tử.** Encoder mặc định có thể thu Flux thành List rồi ghi array. Chọn NDJSON hoặc SSE cho streaming.
9. **Để JSON array dở dang sau lỗi.** Client có thể nhận JSON không hợp lệ. Thiết kế terminal marker hoặc chọn framing theo record.
10. **Retry vô điều kiện sau khi đã phát một số record.** Retry có thể phát lại dữ liệu và gây duplicate. Dùng ID/sequence, replay và deduplication.
11. **Nuốt lỗi bằng onErrorResume(Mono.empty()).** Client có thể tưởng stream hoàn tất thành công dù dữ liệu đã bị mất.
12. **Gửi exception message/stack trace cho client.** Dễ làm lộ cấu trúc nội bộ hoặc dữ liệu nhạy cảm. Dùng error code ổn định.
13. **Cố gửi error event khi client đã cancel.** Không còn downstream để nhận dữ liệu; hãy dọn tài nguyên.
14. **Dùng timeout tổng cho một stream vốn được thiết kế vô hạn.** Phân biệt idle timeout, first-event timeout và lifetime timeout.
15. **Không có heartbeat cho kết nối dài.** Proxy hoặc load balancer có thể đóng kết nối idle; cân nhắc heartbeat theo giao thức.
16. **Không lưu checkpoint.** Client không biết nên resume từ đâu sau lỗi hoặc disconnect. Dùng event ID/sequence có semantics rõ ràng.
17. **Dùng beforeCommit để thực hiện side effect nhưng không trả publisher.** Framework không chờ công việc bị tách khỏi Mono<Void> callback.
18. **Không kiểm tra boolean từ setStatusCode.** Code có thể tưởng status đã thay đổi trong khi response đã commit.
19. **Không phân biệt lỗi preflight với lỗi body publisher.** Hai lỗi có thể đi qua thời điểm commit khác nhau và cần hai chính sách response.
20. **Không kiểm thử lỗi sau phần tử đầu tiên.** Test chỉ kiểm tra status 200 sẽ bỏ sót việc error record/event có được gửi đúng hay không.

## 15. Checklist thiết kế stream error

Trước khi phát hành endpoint streaming, hãy xác định:

- **Commit boundary:** status và headers được quyết định ở thời điểm nào?
- **Preflight:** có thể xác thực quyền, tham số, quota và khả năng mở nguồn trước commit không?
- **Late error contract:** NDJSON error record, SSE error event, terminal marker hay đóng kết nối?
- **Schema:** client có thể phân biệt data, error và end record không?
- **Status:** status HTTP có phản ánh được mọi lỗi không, hay chỉ lỗi trước commit?
- **Media type:** JSON array có thực sự phù hợp, hay cần NDJSON/SSE?
- **Fallback:** onErrorResume có phát dữ liệu đúng schema không?
- **Retry:** nguồn có replay được không? Có ID/sequence để tránh mất hoặc trùng dữ liệu không?
- **Cancellation:** client disconnect có hủy upstream và release tài nguyên không?
- **Timeout:** idle, first-event và total lifetime được cấu hình riêng chưa?
- **Observability:** log/metric có stream ID, correlation ID, sequence cuối và terminal signal không?
- **Security:** error payload có tránh stack trace, credential và rejected data không?
- **Client behavior:** client có nhận biết terminal marker, error event và reconnect policy không?
- **Tests:** có test lỗi trước commit, lỗi sau vài record, SSE error event và beforeCommit không?

## 16. Bài tập tự kiểm tra

**Bài 1.** Server đã gửi status 200 và hai NDJSON record. Upstream phát onError. Có thể đổi status thành 500 không?  
**Đáp án:** Không. Response đã commit; setStatusCode không thể thay status đã gửi.

**Bài 2.** Server muốn trả 503 nếu không thể mở nguồn stream. Nên kiểm tra điều kiện đó khi nào?  
**Đáp án:** Trước khi tạo/bắt đầu body response, ví dụ trong Mono<ResponseEntity<Flux<T>>> hoặc bước preflight.

**Bài 3.** beforeCommit dùng để làm gì?  
**Đáp án:** Đăng ký công việc chạy trước khi response commit, ví dụ hoàn thiện headers hoặc status. Callback phải trả Mono<Void> để framework quản lý.

**Bài 4.** doOnError có làm stream tiếp tục không?  
**Đáp án:** Không. Nó chỉ quan sát lỗi; onError vẫn là terminal signal.

**Bài 5.** onErrorMap có biến lỗi thành record không?  
**Đáp án:** Không. Nó chỉ đổi exception. Muốn phát fallback publisher, dùng onErrorResume.

**Bài 6.** Nếu onErrorResume phát một record error trong NDJSON sau hai record data, HTTP status là gì?  
**Đáp án:** Status đã commit ban đầu, thường là 200. Error record là dữ liệu giao thức.

**Bài 7.** Vì sao SSE có thể phát event stream-error?  
**Đáp án:** SSE hỗ trợ event name và data; server có thể định nghĩa event riêng để báo lỗi trong stream.

**Bài 8.** Vì sao JSON array có thể bị hỏng khi lỗi giữa lúc stream?  
**Đáp án:** Body có thể thiếu dấu đóng array hoặc phần tử cuối, nên không còn là JSON document hợp lệ.

**Bài 9.** retryWhen sau khi đã phát một số event có rủi ro gì?  
**Đáp án:** Upstream có thể phát lại các event cũ, gây duplicate. Cần replay semantics, ID/sequence và deduplication.

**Bài 10.** Client cancel có kích hoạt onErrorResume không?  
**Đáp án:** Không. Cancellation là tín hiệu cancel; dùng doOnCancel/doFinally và cleanup phù hợp.

**Bài 11.** Một record JSON có field status=500 có làm HTTP status đổi không?  
**Đáp án:** Không. Đó chỉ là dữ liệu ứng dụng trong body.

**Bài 12.** Vì sao cần checkpoint hoặc Last-Event-ID?  
**Đáp án:** Để client reconnect từ vị trí đã nhận, giảm nguy cơ mất hoặc xử lý trùng event.

## 17. Ghi nhớ

HTTP status và headers chỉ có thể thay đổi trước khi response commit. Trong WebFlux, ServerHttpResponse.isCommitted() cho biết trạng thái; setStatusCode() trả boolean để báo có đặt được status hay không; beforeCommit() cho phép hoàn tất metadata ngay trước khi gửi response.

Lỗi xảy ra trước commit có thể được xử lý bằng @RestControllerAdvice hoặc WebExceptionHandler để trả status như 400, 403, 503 hoặc 504. Lỗi xảy ra sau khi stream đã bắt đầu không thể đổi status hoặc thay body đã gửi. doOnError chỉ quan sát, onErrorMap chỉ đổi exception, còn onErrorResume có thể chuyển sang publisher dự phòng.

Với NDJSON, hãy định nghĩa error record; với SSE, hãy định nghĩa event stream-error. Nếu giao thức không hỗ trợ báo lỗi trong body, kết thúc kết nối và cho client nhận biết stream chưa hoàn tất, sau đó reconnect từ checkpoint nếu có thể. Thiết kế status, media type, error schema, retry, cancellation và observability như một phần của hợp đồng streaming.

### Tài liệu tham khảo

- Spring Framework, [WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- Spring Framework, [WebFlux Return Values and Reactive Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
- Spring Framework, [WebFlux Streaming and Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework Javadoc, [ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html).
- Spring Framework Javadoc, [ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html).
- Project Reactor, [Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor, [Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- MDN, [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events).
