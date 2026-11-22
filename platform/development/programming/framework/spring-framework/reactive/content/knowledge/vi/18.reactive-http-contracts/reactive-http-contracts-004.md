# Giới hạn đổi status sau khi phản hồi đã được gửi trong Spring WebFlux

## 1. Vì sao không thể tùy ý đổi HTTP status?

Trong Spring WebFlux, server xây dựng một HTTP response gồm status code, headers và body. Status cùng headers được gửi ở phần đầu của response; body được gửi sau đó. Khi server đã **commit response**, phần metadata đầu tiên đã được áp dụng vào response ở tầng HTTP. Lúc này client đã nhận hoặc có thể nhận status code và headers, nên server không thể thay status cũ bằng một status mới.

Ví dụ, server đã bắt đầu gửi:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

The operation started...
```

Sau đó một tác vụ phía sau phát hiện database bị lỗi. Server không thể đổi response đã gửi thành:

```http
HTTP/1.1 500 Internal Server Error
```

vì status `200` đã được gửi trong phần headers. Việc cố gọi API đổi status sau commit không thể thu hồi bytes mà client đã nhận.

Đây là giới hạn của giao thức HTTP và vòng đời response, không phải một thiếu sót riêng của Reactor. Spring WebFlux biểu diễn ranh giới này qua `ServerHttpResponse.isCommitted()` và kết quả boolean của `setStatusCode(...)`.

**Quy tắc thực tế:** quyết định status và các headers cần thiết trước khi bắt đầu ghi body. Khi response đã commit, chỉ tiếp tục gửi phần body còn lại nếu stream vẫn hợp lệ; nếu stream lỗi thì xử lý theo chính sách dành cho stream đã bắt đầu, không cố thay status.

## 2. Response commit là gì?

Một response có thể đi qua các giai đoạn khái niệm:

```text
NEW
 |
 | Thiết lập status, headers, cookies
 v
READY TO COMMIT
 |
 | Bắt đầu ghi/flush body hoặc hoàn tất response
 v
COMMITTING
 |
 | Áp dụng beforeCommit actions, status, headers, cookies
 v
COMMITTED
 |
 | Tiếp tục ghi body nếu là response streaming
 v
COMPLETE
```

Tên trạng thái trên là mô hình giúp hiểu vòng đời, không phải enum public mà ứng dụng cần tự điều khiển.

- **Trước commit:** ứng dụng có thể chọn status, content type, cache headers, cookies và các metadata khác.
- **Trong quá trình commit:** Spring áp dụng các callback `beforeCommit`, status, headers và cookies xuống response native.
- **Sau commit:** status và headers ban đầu đã được gửi. Không thể thay chúng bằng giá trị mới.
- **Sau khi body hoàn tất:** response kết thúc bình thường. Một số response streaming có thể đã commit từ lâu nhưng vẫn còn đang phát body.

Thông thường response được commit khi bắt đầu ghi body hoặc flush dữ liệu. Với response không có body, quá trình hoàn tất (`setComplete`) cũng có thể kích hoạt commit. Thời điểm cụ thể phụ thuộc cách handler ghi response và implementation server.

Điểm rất quan trọng: **committed không đồng nghĩa với body đã gửi xong**. Với `Flux` hoặc SSE, server có thể commit headers và gửi chunk đầu tiên, rồi tiếp tục phát dữ liệu trong nhiều giây hoặc nhiều phút. Trong suốt phần còn lại đó, status ban đầu vẫn cố định.

## 3. API cần biết trên `ServerHttpResponse`

`ServerHttpResponse` thuộc package `org.springframework.http.server.reactive`. Các API quan trọng:

| API | Ý nghĩa |
|---|---|
| `setStatusCode(HttpStatusCode status)` | Đặt status; trả `true` nếu thay đổi được chấp nhận, `false` nếu response đã commit |
| `getStatusCode()` | Đọc status đã đặt hoặc status từ server nền; có thể `null` nếu chưa có giá trị mặc định |
| `isCommitted()` | Kiểm tra response đã commit hay chưa |
| `getHeaders()` | Truy cập headers của response |
| `getCookies()` / `addCookie(...)` | Chuẩn bị cookie cho response |
| `beforeCommit(Supplier<Mono<Void>> action)` | Đăng ký công việc chạy ngay trước khi response commit |
| `writeWith(Publisher<DataBuffer>)` | Ghi body theo một Publisher |
| `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` | Ghi các nhóm buffer và flush sau từng nhóm |
| `setComplete()` | Hoàn tất response không cần body |

### 3.1. Giá trị trả về của `setStatusCode`

Đây là điểm cần nhớ nhất:

```java
boolean changed = response.setStatusCode(
        HttpStatus.INTERNAL_SERVER_ERROR
);

if (!changed) {
    // Response đã commit; status không được thay đổi.
}
```

`setStatusCode` **không nhất thiết ném exception** khi response đã commit. Nó trả `false` để báo rằng thay đổi không được thực hiện. Đừng bỏ qua giá trị boolean nếu code phụ thuộc vào việc status đã được đặt thành công.

Không nhầm với `setRawStatusCode(Integer)`: API raw status cũng có kết quả boolean tương tự và đã được đánh dấu deprecated trong các phiên bản Spring mới hơn để ưu tiên `HttpStatusCode`.

### 3.2. `isCommitted()` chỉ là phép quan sát

Có thể kiểm tra trước khi thay đổi:

```java
if (!response.isCommitted()) {
    response.setStatusCode(HttpStatus.BAD_REQUEST);
}
```

Đây là kiểm tra hữu ích để chọn nhánh xử lý. Tuy nhiên, trong pipeline bất đồng bộ, một callback khác có thể khiến response commit sau lúc kiểm tra. Vì vậy **không coi `isCommitted()` như khóa đồng bộ**. Hãy kiểm tra kết quả của `setStatusCode` và thực hiện quyết định status tại một ranh giới trước khi ghi response.

### 3.3. Headers và cookies cũng chịu giới hạn commit

Status không phải metadata duy nhất bị khóa. Sau commit, việc thay đổi headers có thể không còn tác dụng hoặc có thể bị từ chối tùy implementation. `addCookie` trên `ServerHttpResponse` có thể ném `IllegalStateException` khi response đã commit.

Hãy chuẩn bị các giá trị như:

- `Content-Type`
- `Content-Length` (nếu biết chính xác và phù hợp)
- `Cache-Control`
- `ETag`
- `Location`
- `Set-Cookie`
- CORS/security headers

trước khi bắt đầu ghi body, hoặc đăng ký callback `beforeCommit` cho metadata cần thêm ở thời điểm commit.

## 4. Đặt status trước khi ghi body

Cách đơn giản và rõ ràng nhất là quyết định status trước `writeWith(...)`:

```java
Mono<Void> writeCreated(ServerHttpResponse response) {
    response.setStatusCode(HttpStatus.CREATED);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

    byte[] bytes = "created\n".getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(bytes);

    return response.writeWith(Mono.just(buffer));
}
```

Trình tự:

1. Chọn `201 Created`.
2. Chuẩn bị `Content-Type`.
3. Tạo `DataBuffer`.
4. Trả Publisher ghi body.
5. Spring/server commit response và gửi status, headers cùng body.

Ở thời điểm `writeWith` được subscribe và bắt đầu thực hiện, status đã được chọn. Nếu dữ liệu cần thiết để quyết định status chưa có, hãy lấy dữ liệu đó trước khi gọi `writeWith`.

### 4.1. Kiểm tra nghiệp vụ trước khi commit

Ví dụ endpoint tạo đơn hàng cần kiểm tra sản phẩm và quyền sở hữu trước khi trả `201`:

```java
Mono<Void> createOrder(ServerHttpResponse response, CreateOrder command) {
    return orderService.validate(command)
            .then(orderService.create(command))
            .flatMap(order -> {
                response.setStatusCode(HttpStatus.CREATED);
                response.getHeaders().set(
                        HttpHeaders.LOCATION,
                        "/orders/" + order.id()
                );
                return response.writeWith(
                        Mono.just(jsonBuffer(response, order))
                );
            })
            .onErrorResume(ProductNotFoundException.class, error -> {
                response.setStatusCode(HttpStatus.NOT_FOUND);
                return response.writeWith(
                        Mono.just(textBuffer(response, "product not found"))
                );
            });
}
```

Đây là mã minh họa: `orderService`, `CreateOrder`, `jsonBuffer` và `textBuffer` là thành phần ứng dụng. Ý nghĩa là phần validate/create chạy trước khi body được gửi; nếu lỗi xảy ra ở giai đoạn này, handler còn có thể chọn `404` hoặc status phù hợp.

Nếu `orderService.create(...)` đã ghi dữ liệu thành công nhưng việc ghi response thất bại, không nên tự động retry thao tác tạo đơn mà không có idempotency key. Lỗi transport và lỗi nghiệp vụ là hai tình huống khác nhau.

## 5. `beforeCommit`: chuẩn bị metadata ngay trước khi gửi

`beforeCommit(...)` hữu ích khi một filter hoặc tầng hạ tầng cần thêm headers/cookies sau khi logic handler đã xác định response, nhưng trước khi server commit.

```java
response.beforeCommit(() -> Mono.fromRunnable(() -> {
    response.getHeaders().set("X-Response-Policy", "validated");
    response.setStatusCode(HttpStatus.ACCEPTED);
}));
```

Callback nhận một `Supplier<Mono<Void>>`. **Action phải được defer** để nó chạy đúng thời điểm commit và đúng thứ tự với các action khác. Các dạng thường dùng:

```java
response.beforeCommit(() ->
        Mono.fromRunnable(() ->
                response.getHeaders().set("X-Trace-Ready", "true")
        )
);
```

Hoặc:

```java
response.beforeCommit(() ->
        Mono.defer(() -> {
            response.getHeaders().set("X-Trace-Ready", "true");
            return Mono.empty();
        })
);
```

Không viết như sau:

```java
// SAI: tác dụng phụ chạy ngay lúc đăng ký, không được defer.
response.beforeCommit(setHeaderImmediately(response));
```

Nếu `setHeaderImmediately(...)` thay đổi header ngay khi được gọi và chỉ trả về một Mono đã tạo sẵn, tác dụng phụ có thể xảy ra trước thời điểm callback được thực thi.

Dùng `beforeCommit` cho công việc ngắn, không blocking, có thể hoàn thành trong thời gian commit. Không gọi database, không chờ HTTP client hoặc thực hiện I/O blocking trong callback này. Các tác vụ đó cần hoàn tất trước khi bắt đầu commit.

**Giới hạn:** `beforeCommit` là cơ hội cuối cùng để chuẩn bị metadata trước khi gửi; nó không phải hook để sửa status sau khi body đã được gửi. Đăng ký callback sau khi response đã commit không thể quay ngược thời gian để sửa response.

## 6. Vì sao `onErrorResume` sau khi ghi body không đổi được status?

Một lỗi phổ biến là đặt fallback sau thao tác ghi:

```java
return response.writeWith(body)
        .onErrorResume(error -> {
            response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
            return response.writeWith(
                    Mono.just(textBuffer(response, "failed"))
            );
        });
```

Đoạn trên **không an toàn**. Khi `writeWith(body)` phát lỗi, response có thể đã commit và một phần body đã đến client. `setStatusCode(500)` lúc đó có thể trả `false`; việc gọi `writeWith` lần thứ hai cũng không thể biến response đã gửi thành một response mới hợp lệ.

Cách đúng là phân biệt lỗi xảy ra **trước** hay **sau** commit:

```java
return operationThatMayFail()
        .flatMap(value -> writeSuccess(response, value))
        .onErrorResume(error -> {
            if (response.isCommitted()) {
                return Mono.error(error);
            }

            boolean changed =
                    response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);

            if (!changed) {
                return Mono.error(error);
            }

            return writeError(response, "request failed");
        });
```

Đây là mã minh họa. `operationThatMayFail`, `writeSuccess` và `writeError` thuộc ứng dụng. Nhánh trước commit còn có thể chọn status và ghi error body. Nhánh sau commit truyền lỗi tiếp để runtime/server xử lý việc stream thất bại, thay vì giả vờ có thể tạo một HTTP response mới.

Trong ứng dụng thật, nên đặt ranh giới lỗi quanh từng công việc nghiệp vụ trước khi ghi body. Nếu lỗi chỉ có thể xảy ra trong lúc stream, chọn một giao thức biểu diễn lỗi trong stream hoặc chấp nhận stream bị kết thúc bất thường.

## 7. Xử lý lỗi trong `WebExceptionHandler`

`WebExceptionHandler` thường được dùng để ánh xạ lỗi WebFlux thành response thống nhất. Handler phải kiểm tra response đã commit hay chưa:

```java
@Component
class ApiExceptionHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            Throwable error) {

        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            // Không thể thay status/body đã gửi.
            return Mono.error(error);
        }

        response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] bytes = "internal server error\n"
                .getBytes(StandardCharsets.UTF_8);

        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
```

Đây là mẫu minh họa cho lỗi chưa được xử lý ở các tầng trước. Trong ứng dụng production:

- Chỉ ánh xạ exception theo loại và chính sách HTTP; không biến mọi lỗi thành `500` nếu có status cụ thể.
- Không gửi stack trace, SQL, token hoặc thông tin nội bộ trong error body.
- Nếu response đã commit, không ghi thêm error body thứ hai. Ghi log/trace có correlation ID và để lỗi truyền tới runtime.
- Tránh để nhiều `WebExceptionHandler` cùng xử lý một lỗi hoặc tự subscribe vào Publisher.
- Nếu lỗi phát sinh khi client đã ngắt kết nối, kiểm tra cancellation và tránh thực hiện cleanup hai lần.

## 8. Streaming: status cố định ngay từ đầu

Streaming response làm giới hạn commit rõ nhất. Ví dụ server gửi ba dòng NDJSON:

```text
{"type":"progress","value":1}
{"type":"progress","value":2}
{"type":"progress","value":3}
```

Ngay khi response bắt đầu được gửi, status và headers đã được commit. Nếu nguồn phát lỗi trước dòng thứ ba, client có thể đã nhận status `200` và hai dòng đầu. Server không thể đổi status thành `500` ở dòng thứ ba.

Một stream có thể được tạo bằng:

```java
Flux<Progress> progress = job.events();

return progress
        .map(this::toProgressDto)
        .as(events -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(events, ProgressDto.class));
```

Đây là ví dụ WebFlux.fn minh họa; `job.events`, `toProgressDto` và các DTO thuộc ứng dụng. `ServerResponse.ok()` chọn status trước khi body Publisher được ghi. Nếu stream lỗi sau khi response đã commit, status `200` vẫn là status ban đầu.

### 8.1. Lỗi nghiệp vụ trong stream nên biểu diễn trong dữ liệu

Nếu giao thức cho phép, stream có thể phát một event báo lỗi như một phần tử cuối:

```java
Flux<StreamMessage> messages = job.events()
        .map(value -> StreamMessage.progress(value))
        .onErrorResume(error ->
                Flux.just(StreamMessage.failed("job interrupted"))
        );
```

`StreamMessage` là kiểu DTO do ứng dụng định nghĩa. Client cần hiểu rõ event `"failed"` là kết quả nghiệp vụ của stream; status HTTP vẫn giữ nguyên vì response đã bắt đầu.

Với Server-Sent Events, có thể dùng event name như `progress`, `completed` và `error`. Với NDJSON, có thể phát object có trường `type`. Đây là giao thức ứng dụng; không nên gửi stack trace hoặc chi tiết nội bộ trong event lỗi.

Nếu API không định nghĩa event lỗi trong body, có thể kết thúc stream bằng lỗi và để client nhận biết kết nối/stream bị gián đoạn. Client cần retry/reconnect có kiểm soát, tốt nhất dựa trên event ID hoặc cursor để tránh xử lý trùng.

### 8.2. Không buffer toàn bộ stream chỉ để có thể đổi status

Một cách né vấn đề là gom mọi phần tử vào bộ nhớ rồi mới gửi response. Cách này cho phép xác định lỗi trước khi commit, nhưng có thể gây:

- RAM tăng theo kích thước kết quả.
- Tăng latency trước khi client nhận byte đầu tiên.
- Không phù hợp với stream vô hạn hoặc thời gian dài.
- Mất lợi ích backpressure và xử lý dần.

Chỉ buffer khi kết quả có giới hạn, kích thước được kiểm soát và nghiệp vụ thực sự cần biết toàn bộ kết quả trước khi trả status. Với dữ liệu lớn, nên thiết kế stream có event/error semantics rõ ràng.

## 9. `writeWith`, `writeAndFlushWith` và thời điểm commit

`writeWith(Publisher<DataBuffer>)` ghi body từ một Publisher. `writeAndFlushWith(Publisher<Publisher<DataBuffer>>)` ghi từng nhóm Publisher và flush sau mỗi nhóm.

Ví dụ stream flush từng dòng:

```java
Flux<Publisher<DataBuffer>> chunks = Flux.just(
        "first\n",
        "second\n",
        "third\n"
).map(line -> Mono.just(
        response.bufferFactory().wrap(
                line.getBytes(StandardCharsets.UTF_8)
        )
));

return response.writeAndFlushWith(chunks);
```

Đây là mã minh họa cần import `org.reactivestreams.Publisher`; các chunk có thể được flush riêng để client nhận dữ liệu sớm. Lần ghi/flush đầu có thể làm response commit. Các lần flush tiếp theo gửi thêm body; chúng không mở lại cơ hội đổi status.

Với `Flux<DataBuffer>`, `writeWith` có thể truyền nhiều buffer nhưng server có thể tự quyết định batching/flush. Nếu cần streaming từng nhóm, `writeAndFlushWith` biểu đạt rõ hơn yêu cầu flush. Dù dùng API nào, hãy coi **commit đầu tiên** là ranh giới status/header không còn thay đổi.

## 10. Header, cookie và các thay đổi sau commit

Các thao tác metadata cần được hoàn tất trước commit:

```java
response.setStatusCode(HttpStatus.CREATED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().setCacheControl(CacheControl.noStore());
response.getHeaders().setLocation(URI.create("/orders/123"));
response.addCookie(ResponseCookie.from("notice", "created")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build());
```

Đây là ví dụ chuẩn bị response metadata. Trong production, cookie cần các thuộc tính phù hợp với domain, HTTPS, SameSite và chính sách bảo mật của ứng dụng.

Sau commit:

- Status code đã cố định.
- Các header đã gửi không thể sửa lại.
- Cookie `Set-Cookie` đã gửi không thể bị thay thế trong response hiện tại.
- Không thể thay `Content-Type` để client diễn giải các byte đã nhận theo định dạng khác.
- Không thể đổi `Location` hoặc cache policy sau khi response đã bắt đầu.

HTTP trailers (nếu server/client/protocol hỗ trợ) là metadata ở cuối message; chúng không thay thế status ban đầu và không phải cách sửa status sau commit.

## 11. Phân biệt status response với lỗi transport

Không phải mọi lỗi xảy ra sau commit đều đồng nghĩa với một status HTTP khác.

| Tình huống | Có thể đổi status? | Hành vi phù hợp |
|---|---|---|
| Validation thất bại trước body write | Có | Trả `400` hoặc status nghiệp vụ phù hợp |
| Không tìm thấy dữ liệu trước commit | Có | Trả `404` |
| Service lỗi trước commit | Có | Ánh xạ thành `5xx` hoặc fallback |
| Stream đã gửi một số chunk rồi nguồn phát lỗi | Không | Phát event lỗi nếu giao thức hỗ trợ, hoặc kết thúc stream |
| Client ngắt kết nối khi body đang gửi | Không | Hủy công việc, giải phóng tài nguyên và ghi nhận cancellation |
| Ghi socket thất bại sau commit | Không | Truyền lỗi tới runtime, không ghi response thứ hai |
| Lỗi xảy ra sau khi body hoàn tất | Không cần đổi status | Log/metrics cho tác vụ hậu xử lý; response đã hoàn tất |

Một request có thể được xử lý thành công ở tầng nghiệp vụ nhưng client không nhận đủ response do lỗi mạng. Không thể biết chắc client đã nhận bao nhiêu byte chỉ bằng cách nhìn vào việc Publisher phát complete/error. Với thao tác ghi dữ liệu có side effect, hãy thiết kế idempotency và khả năng client truy vấn trạng thái giao dịch.

## 12. Ví dụ Java 17+ chạy được với Spring Boot WebFlux

Ví dụ dưới đây có ba endpoint:

- `/responses/early`: đặt status `201` trước khi ghi body.
- `/responses/before-commit`: đặt status `202` và header trong callback `beforeCommit`.
- `/responses/late`: ghi body trước, rồi thử đổi status sang `500`; API trả `false` vì response đã commit.

### Cấu trúc dự án

```text
response-commit-demo/
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
    <artifactId>response-commit-demo</artifactId>
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

import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/responses")
class ResponseController {

    @GetMapping("/early")
    Mono<Void> early(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.CREATED);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        return write(response, "created before commit\n");
    }

    @GetMapping("/before-commit")
    Mono<Void> beforeCommit(ServerHttpResponse response) {
        response.beforeCommit(() -> Mono.fromRunnable(() -> {
            response.setStatusCode(HttpStatus.ACCEPTED);
            response.getHeaders().set("X-Prepared", "true");
        }));

        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
        return write(response, "status prepared before commit\n");
    }

    @GetMapping("/late")
    Mono<Void> late(ServerHttpResponse response) {
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        return write(response, "body already sent with original status\n")
                .doOnSuccess(ignored -> {
                    boolean accepted = response.setStatusCode(
                            HttpStatus.INTERNAL_SERVER_ERROR
                    );

                    System.out.println(
                            "late status accepted=" + accepted
                                    + ", committed=" + response.isCommitted()
                    );
                });
    }

    private Mono<Void> write(ServerHttpResponse response, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
```

Từ thư mục dự án, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

### Kiểm tra status được đặt trước commit

```bash
curl -i http://localhost:8080/responses/early
```

Các phần quan trọng trong response:

```http
HTTP/1.1 201 Created
Content-Type: text/plain

created before commit
```

### Kiểm tra `beforeCommit`

```bash
curl -i http://localhost:8080/responses/before-commit
```

Các phần quan trọng:

```http
HTTP/1.1 202 Accepted
Content-Type: text/plain
X-Prepared: true

status prepared before commit
```

### Thử đổi status sau khi body đã gửi

```bash
curl -i http://localhost:8080/responses/late
```

Các phần quan trọng trong response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

body already sent with original status
```

Console của ứng dụng khi gọi endpoint `/late`:

```text
late status accepted=false, committed=true
```

Giải thích:

1. `/early` đặt `201` trước khi gọi `writeWith`, nên server gửi `201 Created`.
2. `/before-commit` đăng ký callback được defer; khi response chuẩn bị commit, callback đặt `202` và header `X-Prepared`.
3. `/late` ghi body trước. Khi `writeWith` hoàn tất, response đã committed.
4. Lệnh `setStatusCode(500)` trả `false`, do đó response vẫn là `200 OK`.
5. `doOnSuccess` chỉ quan sát kết quả ghi; nó không mở lại response để sửa status.

Các header phụ như `Date`, `Content-Length` hoặc `Connection` có thể khác theo server và HTTP client; phần status, header tùy chỉnh và body trên là nội dung cần kiểm tra.

## 13. Kiểm thử bằng `WebTestClient`

Có thể kiểm thử controller mà không mở cổng TCP:

```java
WebTestClient client = WebTestClient
        .bindToController(new ResponseController())
        .build();

client.get()
        .uri("/responses/early")
        .exchange()
        .expectStatus().isCreated()
        .expectBody(String.class)
        .isEqualTo("created before commit\n");

client.get()
        .uri("/responses/before-commit")
        .exchange()
        .expectStatus().isAccepted()
        .expectHeader().valueEquals("X-Prepared", "true");

client.get()
        .uri("/responses/late")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("body already sent with original status\n");
```

Đây là đoạn test cần dependency `spring-test` (thường được đưa vào qua `spring-boot-starter-test`) và import `WebTestClient`. Test xác minh status thực tế client nhận được, thay vì chỉ kiểm tra log nội bộ.

Có thể kiểm tra riêng logic commit bằng một mock response trong unit test nếu dự án dùng `spring-test`. Tuy nhiên, integration test qua WebTestClient hữu ích hơn khi cần xác nhận cả controller, response writer và status được phát ra.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Gọi `setStatusCode(500)` sau `writeWith` đã bắt đầu | Trả `false`; status cũ vẫn được giữ | Quyết định status trước lần ghi đầu tiên |
| Bỏ qua boolean trả về từ `setStatusCode` | Code tưởng đã đổi status nhưng client vẫn nhận status cũ | Kiểm tra giá trị trả về |
| Chỉ kiểm tra `isCommitted()` rồi mặc định thao tác chắc chắn thành công | Có thể gặp ranh giới commit bất đồng bộ | Kiểm tra cả kết quả `setStatusCode` |
| Dùng `onErrorResume` sau khi stream đã gửi một phần body | Không thể thay response cũ bằng status/body mới | Phục hồi lỗi trước commit hoặc phát event lỗi trong stream |
| Gọi `writeWith` lần hai để gửi error body | Có thể gây response đã commit, body lỗi hoặc lỗi ghi | Chỉ ghi một response; sau commit thì truyền lỗi/đóng stream |
| Đăng ký `beforeCommit` nhưng thực hiện side effect eager | Tác vụ chạy quá sớm, sai thứ tự | Trả `Mono.defer` hoặc `Mono.fromRunnable` từ supplier |
| Gọi blocking I/O trong `beforeCommit` | Làm chậm commit và có thể chặn event-loop | Hoàn tất I/O trước commit; callback chỉ làm việc ngắn |
| Buffer stream vô hạn để chờ xác định status | RAM tăng không giới hạn và latency lớn | Thiết kế status trước stream hoặc dùng event/error semantics |
| Nghĩ `isCommitted=true` nghĩa body đã xong | Bỏ qua lỗi/cancel vẫn có thể xảy ra khi stream tiếp tục | Phân biệt commit metadata với completion body |
| Cố thay Content-Type hoặc cookie sau commit | Client đã nhận metadata cũ | Chuẩn bị headers/cookies trước khi ghi |
| Nuốt lỗi sau commit rồi báo stream thành công | Client có thể nhận body thiếu mà không biết | Propagate error hoặc phát event lỗi theo giao thức |
| Retry toàn bộ thao tác sau lỗi ghi response | Side effect có thể chạy lặp | Dùng idempotency key và tách retry nghiệp vụ khỏi retry transport |

## 15. Checklist thiết kế endpoint an toàn

Trước khi trả response, hãy xác định:

1. Status phụ thuộc dữ liệu nào? Dữ liệu đó đã có trước lần ghi đầu tiên chưa?
2. Có thể xác thực, phân quyền và validate toàn bộ request trước commit không?
3. Headers, cookie, `Location`, cache policy và content type đã được chuẩn bị chưa?
4. Có callback `beforeCommit` nào cần chạy? Callback có deferred và không blocking không?
5. Body là một object hữu hạn hay stream dài? Nếu stream lỗi giữa chừng, client sẽ nhận biết bằng cách nào?
6. Error handler có phân biệt lỗi trước commit và sau commit không?
7. Có đoạn code nào cố ghi response lần thứ hai không?
8. Nếu client disconnect, các subscription và tài nguyên có được cleanup đúng không?
9. Với thao tác có side effect, client retry có thể gây trùng lặp không?
10. Có integration test xác minh status thực tế mà client nhận được không?

## 16. Bài tập tự kiểm tra

**Câu 1.** `ServerHttpResponse.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR)` trả về gì khi response đã committed?

**Đáp án:** `false`. Status mới không được áp dụng.

**Câu 2.** `isCommitted()` có nghĩa là toàn bộ body đã gửi xong không?

**Đáp án:** Không. Headers/status đã được commit, nhưng body có thể tiếp tục streaming.

**Câu 3.** Có thể dùng `beforeCommit` để thay status không?

**Đáp án:** Có, nếu callback được đăng ký trước khi commit và thực hiện thay đổi trong action được defer. Nó chạy ngay trước khi status/headers được áp dụng.

**Câu 4.** Một `Flux` đã gửi hai chunk rồi phát `onError`. Server có thể đổi status thành 500 không?

**Đáp án:** Không. Status ban đầu đã được gửi. Có thể phát event lỗi nếu giao thức ứng dụng hỗ trợ, hoặc kết thúc stream bằng lỗi.

**Câu 5.** Vì sao không nên gọi `writeWith` lần hai trong `onErrorResume` sau commit?

**Đáp án:** Response hiện tại đã bắt đầu gửi và không thể trở thành response mới. Ghi body lần hai có thể gây lỗi hoặc tạo dữ liệu không đúng giao thức.

**Câu 6.** Khi nào nên buffer toàn bộ dữ liệu trước khi ghi response?

**Đáp án:** Khi kết quả có giới hạn rõ ràng, cần biết toàn bộ dữ liệu trước khi quyết định status và dung lượng bộ nhớ chấp nhận được. Không buffer stream lớn/vô hạn chỉ để né commit boundary.

**Câu 7.** Vì sao cần kiểm tra boolean từ `setStatusCode` dù đã kiểm tra `isCommitted()`?

**Đáp án:** Vì commit là quá trình bất đồng bộ; trạng thái có thể thay đổi giữa phép kiểm tra và thao tác. Kết quả boolean cho biết thay đổi thực sự được chấp nhận hay không.

## 17. Quy tắc áp dụng

- Đặt status và headers **trước lần ghi body đầu tiên**.
- Dùng `isCommitted()` để quan sát và kiểm tra boolean của `setStatusCode(...)` để biết thay đổi có thành công.
- Dùng `beforeCommit` cho metadata cuối cùng; callback phải defer và không blocking.
- Xử lý validation, authorization và lỗi nghiệp vụ trước commit nếu status phụ thuộc các kết quả đó.
- Sau commit, không cố thay status, headers, cookie hoặc ghi một error response thứ hai.
- Với stream đã bắt đầu, biểu diễn lỗi trong event/body theo giao thức hoặc để stream kết thúc bằng lỗi.
- Kiểm thử bằng `WebTestClient` và xác minh status/body mà client thực sự nhận được.

**Ghi nhớ:** HTTP status được gửi cùng headers khi response commit. Trong Spring WebFlux, `setStatusCode` trả `false` nếu response đã commit; `beforeCommit` là cơ hội cuối để chuẩn bị metadata. Hãy quyết định status trước khi ghi body và thiết kế riêng cách biểu diễn lỗi cho response streaming.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — `ServerHttpResponse` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html)
- [Spring Framework 6.1 — `ReactiveHttpOutputMessage` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html)
- [Spring Framework 6.1 — `AbstractServerHttpResponse` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/server/reactive/AbstractServerHttpResponse.html)
- [Spring Framework — WebFlux functional endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — WebFlux exception handling](https://docs.spring.io/spring-framework/reference/web/webflux/ann-exceptions.html)
