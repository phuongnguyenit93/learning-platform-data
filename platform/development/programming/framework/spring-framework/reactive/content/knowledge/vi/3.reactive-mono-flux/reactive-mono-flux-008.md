# Vì sao WebFlux thường là bên thực hiện subscribe

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Mono và Flux

## Bạn sẽ hiểu gì sau bài này?

- Tại sao controller WebFlux thường **trả về** `Mono`/`Flux` thay vì tự gọi `subscribe()`.
- Subscriber thực sự xuất hiện ở đâu trong vòng đời HTTP, ai điều phối gửi response, demand, lỗi và hủy.
- Vì sao `subscribe()` thủ công có thể khiến công việc chạy tách khỏi HTTP request, trả kết quả quá sớm, bỏ sót lỗi hoặc làm trùng side effect.
- Khi nào ứng dụng **cần tự subscribe** (đúng tại một boundary do ứng dụng sở hữu) và khi nào dùng `StepVerifier`, `WebTestClient` hay `block()` trong thử nghiệm.
- Những ngoại lệ quan trọng: `Mono`/`Flux` không tự bảo đảm mọi thứ đều lazy, cold hoặc có thể hủy ngay; WebFlux cũng không phải lúc nào là lớp Java trực tiếp gọi phương thức `subscribe`.

## 1. `Mono` và `Flux` là gì, và ai làm chúng chạy?

`Mono<T>` biểu diễn một publisher phát **tối đa một phần tử**, rồi hoàn tất hoặc báo lỗi. `Flux<T>` có thể phát từ 0 đến nhiều phần tử. Cả hai triển khai Reactive Streams `Publisher<T>`. Một publisher được **đăng ký** khi có subscriber gọi `Publisher.subscribe(subscriber)`, dẫn đến tín hiệu `onSubscribe(Subscription)`; sau đó subscriber yêu cầu dữ liệu bằng `request(n)`, nhận `onNext`, `onComplete` hoặc `onError` theo giao thức.

Đối với hầu hết publisher **cold** trong Reactor, việc tạo pipeline với `map`, `flatMap`, `filter`, `delayElement`… mới mô tả các bước xử lý. Chúng chỉ thực hiện phần việc được trì hoãn khi có subscription.

```java
Mono<String> greeting = Mono.defer(() -> {
    System.out.println("Running deferred work");
    return Mono.just("Hello");
});
// Không có ai subscribe vào greeting ở đây,
// nên "Running deferred work" chưa được in ra.
```

Đây là **đoạn minh họa** dùng `reactor.core.publisher.Mono`, không phải một chương trình Java độc lập. Khi có subscription, supplier của `Mono.defer` chạy. Nhưng **không phải mọi thao tác đều trì hoãn**: Java vẫn thực hiện các biểu thức khi lắp pipeline. Ví dụ `Mono.just(expensiveCall())` gọi `expensiveCall()` ngay tại thời điểm tạo `Mono`; `Mono.defer(() -> Mono.just(expensiveCall()))` mới trì hoãn lời gọi theo mỗi lần subscribe. Publisher hot có thể đã phát dữ liệu dù một subscriber đến sau chưa đăng ký.

### Vai trò của WebFlux

Trong ứng dụng HTTP dùng Spring WebFlux, code của controller thường chỉ **khai báo công việc** và **trả publisher**:

```java
@GetMapping("/users")
public Flux<UserDto> users() {
    return userService.findAll();
}
```

Đoạn trên **minh họa trong controller**, giả sử có `UserDto`, `userService` và các import tương ứng. Controller không cần tự gọi `subscribe()`: WebFlux phối hợp pipeline mà controller trả về với pipeline xử lý HTTP response, và **hạ tầng WebFlux cùng reactive HTTP server** sở hữu việc subscribe, đọc phần tử và ghi dữ liệu ra client.

Cần hiểu chính xác câu “WebFlux subscribe”: nó mô tả **quyền sở hữu boundary HTTP**. Tùy phiên bản, server adapter, handler, codec và cách trả kết quả, lệnh `subscribe(...)` trực tiếp có thể nằm bên trong các lớp hạ tầng HTTP/transport (chẳng hạn Reactor Netty), chứ không nhất thiết ở đúng một phương thức trong `@RestController` hay ở một lời gọi ngay sau `return`. Pipeline xử lý **toàn bộ request** đã có subscriber ở boundary server; publisher trả từ controller được kết hợp vào pipeline đó và được tiêu thụ khi response được xử lý.

## 2. Từ request đến response: vòng đời subscription

Một luồng điển hình với annotated controller trả `Mono<T>` hoặc `Flux<T>`:

```text
Client gửi HTTP request
          |
          v
Reactive HTTP server / WebFlux adapter
          |
          v
DispatcherHandler -> chọn handler/controller
          |
          v
Controller tạo và trả Mono<T> hoặc Flux<T>
          |
          v
HandlerResultHandler + HttpMessageWriter/encoder
          |
          v
ServerHttpResponse.writeWith(...) / writeAndFlushWith(...)
          |
          v
Server runtime subscribe/consume response publisher
          |
          +-- onSubscribe -> request(n) khi có thể xử lý thêm
          +-- onNext(value) -> encode / ghi response
          +-- onComplete -> hoàn tất response
          +-- onError(error) -> xử lý lỗi theo trạng thái response
          +-- cancel -> thông báo ngừng downstream khi có hủy
```

Đây là **sơ đồ khái niệm**, không phải stack trace cố định: WebFlux có thể tạo và subscribe các chuỗi trung gian theo nhiều cách. Điều cần nhớ là publisher của controller đi vào cơ chế trả lời HTTP; chính boundary này điều phối phần lớn lifecycle.

- **Khi chưa subscribe**, toán tử lazy chưa chạy. Controller có thể đã được gọi để tạo publisher, nhưng các hành động nằm trong `defer`/`flatMap` thường chưa được thực hiện.
- **Khi hạ tầng tiêu thụ publisher**, nó nhận tín hiệu và mã hóa dữ liệu theo `HttpMessageWriter`, kiểu kết quả, codec và `Content-Type`. Với một `Mono<String>` body ngắn, thường nhận một chuỗi rồi hoàn tất; với `Flux` streaming, response có thể được gửi dần.
- **Khi nguồn báo lỗi**, WebFlux có cơ hội đưa lỗi qua error handling của chuỗi HTTP. Nếu response chưa được commit, framework có thể chọn status/body lỗi; nếu đã gửi header hoặc một phần body, không thể tùy ý đổi mã HTTP đã gửi.
- **Khi client ngắt**, việc đóng kết nối có thể dẫn tới cancellation lan vào pipeline. Thời điểm và hiệu lực thực tế phụ thuộc server/transport và khả năng hủy của nguồn. `cancel` không bảo đảm sẽ dừng tức thì một tác vụ blocking hoặc side effect đã khởi động.

### Backpressure và yêu cầu dữ liệu

Reactive Streams không chỉ là “gọi hàm chạy bất đồng bộ”. Một `Subscription` cho phép bên nhận phát `request(n)`, để upstream biết mức nhu cầu. Hạ tầng ghi HTTP có thể điều phối demand theo khả năng ghi, codec, bộ đệm và transport. Không nên suy ra mỗi gói TCP, mỗi dòng JSON hoặc mỗi lần flush tương ứng chính xác với một lời gọi `request(1)`: toán tử có thể `prefetch`/buffer và codec có cách đóng gói riêng.

**Quan trọng:** Gọi `subscribe()` **không tự động tạo thread mới**. Một cold publisher đồng bộ như `Flux.range` có thể chạy ngay trên thread gọi subscribe cho đến khi hoàn tất hoặc bị chặn vì demand; sự bất đồng bộ xuất hiện khi nguồn/toán tử chủ động dùng scheduler hoặc I/O nonblocking.

## 3. Ví dụ chạy được: controller trả publisher, WebFlux tiêu thụ

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.5** (Spring WebFlux và Reactor Netty), **Maven**. Đây là một phiên bản cố định để có ví dụ tái lập; trong dự án thực tế hãy dùng phiên bản được dự án quản lý và còn được hỗ trợ.

Cấu trúc tệp:

```text
webflux-subscribe-demo/
├── pom.xml
└── src/main/java/demo/
    ├── WebfluxSubscribeApplication.java
    └── DemoController.java
```

### `pom.xml`

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
    <artifactId>webflux-subscribe-demo</artifactId>
    <version>1.0.0</version>

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

### `src/main/java/demo/WebfluxSubscribeApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxSubscribeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxSubscribeApplication.class, args);
    }
}
```

### `src/main/java/demo/DemoController.java`

```java
package demo;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    private final AtomicInteger helloSubscriptions = new AtomicInteger();

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> hello() {
        System.out.println("handler: create publisher");

        return Mono.defer(() ->
                Mono.just("hello #" + helloSubscriptions.incrementAndGet()))
                .doOnSubscribe(subscription ->
                        System.out.println("hello: subscribed"));
    }

    @GetMapping(value = "/managed", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> managed() {
        return delayedWork().thenReturn("work complete");
    }

    // Chỉ để minh họa anti-pattern: không làm theo trong handler thực tế.
    @GetMapping(value = "/detached", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> detached() {
        delayedWork().subscribe(
                value -> System.out.println("detached result: " + value),
                error -> System.err.println("detached error: " + error));
        return Mono.just("accepted");
    }

    @PostMapping(
            value = "/upper",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> upper(@RequestBody Mono<String> body) {
        return body.map(value -> value.toUpperCase(Locale.ROOT));
    }

    private Mono<String> delayedWork() {
        return Mono.delay(Duration.ofMillis(250))
                .map(tick -> "finished");
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Mở một terminal khác, thực hiện **từng lệnh**. Trên Windows PowerShell, dùng `curl.exe` để tránh alias `curl` của PowerShell; trên Linux/macOS có thể dùng `curl`:

```powershell
curl.exe -s http://localhost:8080/hello
curl.exe -s http://localhost:8080/hello
curl.exe -s http://localhost:8080/managed
curl.exe -s http://localhost:8080/detached
curl.exe -s -X POST -H "Content-Type: text/plain" --data "webflux" http://localhost:8080/upper
```

**Response body mong đợi**, theo thứ tự các lệnh trên và giả sử chưa có request khác gọi `/hello`:

```text
hello #1
hello #2
work complete
accepted
WEBFLUX
```

`curl.exe -s` không thêm xuống dòng cho response thiếu newline, vì vậy văn bản có thể dính liền nếu gõ các lệnh trong một script; khối ở trên trình bày **từng body riêng** để dễ đọc. Console ứng dụng có log Spring Boot khác; các dòng do ta chủ động in ở lần đầu gọi `/hello` là:

```text
handler: create publisher
hello: subscribed
```

Không cần controller tự `subscribe` để xuất hiện dòng thứ hai. `Mono.defer` trong `hello()` tăng bộ đếm khi publisher được đăng ký; lần request kế tiếp có subscription mới và tạo `hello #2`.

`/managed` kết hợp công việc được trì hoãn với response bằng `thenReturn`. WebFlux hoàn tất response khi chuỗi công việc hoàn tất. `/detached` cố ý minh họa cách sai: method tự mở **một subscription riêng** và trả `accepted` độc lập với kết quả đó. Dòng `detached result: finished` có thể xuất hiện sau response và thứ tự log tùy scheduler; không có bảo đảm rằng HTTP request đang chờ hoặc theo dõi việc này. `/upper` minh họa đầu vào `@RequestBody Mono<String>`: WebFlux giải mã request body và kết hợp với xử lý response mà không cần gọi subscribe trên `body`.

## 4. Vì sao `subscribe()` bên trong controller thường sai?

So sánh hai cách xử lý cùng một tác vụ reactive, giả sử `orderService.save(request)` trả về `Mono<Order>`:

**Cách sai – tự subscribe rồi trả kết quả khác:**

```java
@PostMapping("/orders")
public Mono<String> createOrder(@RequestBody Mono<OrderRequest> input) {
    input.flatMap(orderService::save)
         .subscribe(saved -> audit(saved));
    return Mono.just("accepted");
}
```

**Cách đúng – trả về chuỗi kết hợp:**

```java
@PostMapping("/orders")
public Mono<String> createOrder(@RequestBody Mono<OrderRequest> input) {
    return input.flatMap(orderService::save)
                .doOnNext(saved -> audit(saved))
                .thenReturn("created");
}
```

Hai đoạn trên **là mã minh họa trong controller**, giả sử ứng dụng đã định nghĩa `OrderRequest`, `Order`, `orderService` và `audit(...)`. `doOnNext` thích hợp với tác vụ quan sát nhẹ, đồng bộ; nếu `audit` là I/O hoặc publisher reactive, phải **compose** bằng `flatMap`/`then` hoặc mẫu giao dịch phù hợp, không dùng `doOnNext` để tự gọi subscribe.

Trong cách sai:

1. `subscribe` lập tức tạo subscriber thứ nhất cho logic lưu đơn. HTTP response `Mono.just("accepted")` là **publisher khác**.
2. Client có thể nhận `accepted` trước khi lưu thành công hoặc thất bại. Lỗi lưu không tự chuyển thành lỗi HTTP đã trả; callback `subscribe` thiếu hàm xử lý lỗi đầy đủ cũng có thể gây lỗi không được quản lý ở nhánh tách rời.
3. Nếu client ngắt kết nối, cancellation của nhánh response **không tự động** hủy nhánh đã subscribe thủ công.
4. Ngữ cảnh request, tracing, bảo mật, transaction và tài nguyên gắn với subscription ban đầu có thể không đi theo nhánh mới theo cách bạn tưởng; việc tách nhánh cần được thiết kế và quản lý riêng.
5. Nếu cũng trả lại hoặc subscribe một cold publisher lần nữa ở chỗ khác, side effect như ghi database, gọi HTTP hoặc phát sự kiện **có thể chạy hai lần**.

Trong cách đúng, kết quả lưu là một phần của pipeline trả về. `thenReturn("created")` chỉ phát chuỗi sau khi thao tác trước hoàn tất thành công. `onError` được truyền theo chuỗi để cơ chế lỗi của WebFlux xử lý; cancellation cũng có đường truyền về upstream khi nguồn hỗ trợ.

### Nếu audit là công việc reactive

Dùng composition để gắn rõ kết quả và lỗi:

```java
return input.flatMap(orderService::save)
            .flatMap(saved -> auditService.record(saved)
                    .thenReturn(saved))
            .thenReturn("created");
```

Đây là đoạn **minh họa**, giả sử `auditService.record(saved)` trả `Mono<Void>`. Response chỉ thành công khi cả hai bước thành công; việc bảo đảm tính nguyên tử giữa lưu đơn và audit còn phụ thuộc transaction/outbox và nguồn dữ liệu, không thể chỉ suy ra từ `flatMap`.

### `subscribe()` và `block()` đều tạo thêm subscription

- `publisher.subscribe(...)` tạo subscription, trả về `Disposable` trong Reactor; callback không gắn mặc định với response HTTP.
- `publisher.block()` cũng tạo subscription rồi **chờ đồng bộ** kết quả. Dùng trong handler WebFlux trên non-blocking event-loop có thể báo `IllegalStateException` hoặc gây ảnh hưởng throughput; không gọi `block()` để “lấy giá trị ra khỏi Mono” trong controller.
- `publisher.toFuture()` hay một terminal operation khác cũng có thể tiêu thụ publisher; điều quan trọng là **ai sở hữu terminal boundary**, không chỉ tên phương thức.

Trong handler, hãy ưu tiên `map`, `flatMap`, `zip`, `then`, `onErrorResume` và **trả về publisher đã compose**. Nếu chỉ cần trả về `Mono<Void>`, hãy trả chuỗi hoàn tất:

```java
@PostMapping("/notifications")
public Mono<Void> notify(@RequestBody Mono<Message> input) {
    return input.flatMap(notificationService::send).then();
}
```

Đây là **đoạn minh họa**, giả sử `Message` và service được ứng dụng định nghĩa. Khi `Mono<Void>` hoàn tất, WebFlux biết đã kết thúc xử lý; nếu lỗi, lỗi vẫn nằm trong HTTP chain.

## 5. Hệ quả thực tế khi để WebFlux quản lý subscription

### 5.1. Kết thúc response đúng thời điểm

Với `Mono<T>` response, trạng thái cuối của publisher góp phần quyết định khi nào server có thể kết thúc body. Với `Flux<T>`, server có thể xử lý nhiều phần tử theo codec. `Content-Type: text/event-stream` thường dùng SSE để phát theo sự kiện; `application/json` có thể cần tổ chức dữ liệu theo định dạng JSON phù hợp, không nhất thiết flush từng phần tử. Không nhầm một phần tử trong `Flux` với một HTTP response riêng.

### 5.2. Lỗi đi đúng đường

Một `Mono.error(...)` trong pipeline được trả có thể được WebFlux chuyển qua WebExceptionHandler hoặc cơ chế xử lý lỗi của ứng dụng khi response còn sửa được. `doOnError` chỉ quan sát lỗi, **không** thay thế lỗi. Nếu cần đổi lỗi thành giá trị, dùng `onErrorResume`; nếu cần giữ tính chất lỗi để server xử lý, để lỗi đi tiếp hoặc dùng `onErrorMap` khi phù hợp.

```java
return userService.findById(id)
        .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "User not found")));
```

Đây là **đoạn minh họa**, cần các import của Spring, `id` và `userService` do ứng dụng cung cấp. Nếu không tìm thấy user, lỗi nằm trong publisher trả về và có thể tạo HTTP 404 trước khi response được commit.

### 5.3. Backpressure và cancellation có cơ hội truyền ngược

Cơ chế subscribe của hạ tầng cho phép HTTP consumer điều phối demand, và cancellation từ phía downstream có thể chuyển ngược vào nguồn. Ví dụ, đóng kết nối giữa chừng khi server đang stream nhiều phần tử có thể làm subscription nhận `cancel` và dừng sinh phần tử sau đó. Nhưng đừng kỳ vọng mọi tác vụ hoặc socket có thể bị hủy tức khắc.

Với nguồn cấp tài nguyên theo subscription, hãy dọn dẹp bằng `using`/`usingWhen` hoặc theo dõi các kiểu kết thúc bằng `doFinally`:

```java
return someFlux
        .doFinally(signal -> metrics.recordTermination(signal));
```

Đây là **đoạn minh họa**: `metrics` và `someFlux` là thành phần của ứng dụng. `signal` có thể biểu thị hoàn tất, lỗi hoặc hủy; `cancel` không phát `onComplete`. Đừng dựa riêng vào `doOnComplete` để dọn tài nguyên trong trường hợp client ngắt kết nối.

### 5.4. Ngữ cảnh subscription được giữ trong pipeline

Reactor `Context` gắn dữ liệu theo **subscription**, hữu ích cho tracing, thông tin tương quan và thành phần reactive bảo mật/giao dịch. Khi controller trả cùng pipeline, các thành phần WebFlux và toán tử có đường truyền ngữ cảnh nhất quán hơn. Khi tự `subscribe` tạo nhánh tách rời, cần chủ động xác định ngữ cảnh nào được mang theo; không mặc định mọi `ThreadLocal` hoặc Reactor `Context` được sao chép sang subscription mới.

### 5.5. Quản lý I/O mà không chiếm event-loop

Trả `Mono`/`Flux` giúp WebFlux làm việc với I/O reactive không chặn thread. Điều này **không biến một lời gọi blocking thành nonblocking**. Ví dụ gọi JDBC đồng bộ trong `map` vẫn có thể chặn event-loop; `subscribe()` thủ công cũng không sửa được. Với hệ thống mới, dùng API reactive phù hợp (WebClient, R2DBC…) khi có thể. Nếu buộc phải bọc nguồn đồng bộ, cân nhắc `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` cùng chính sách giới hạn tài nguyên và timeout; đó là cầu nối, không phải thay thế cho nonblocking I/O.

## 6. Các trường hợp khiến quy tắc “WebFlux subscribe” cần hiểu linh hoạt

| Trường hợp | Ai thường sở hữu subscribe? | Cách triển khai phù hợp |
| --- | --- | --- |
| `@RestController` trả `Mono<T>`/`Flux<T>` | HTTP processing pipeline của WebFlux/server | Return publisher; framework ghi response. |
| WebFlux.fn với `ServerResponse` | Pipeline của WebFlux/server | Return `Mono<ServerResponse>` từ handler, đưa body vào builder. |
| `WebFilter` | HTTP pipeline đã do hạ tầng quản lý | Return `chain.filter(exchange)` và compose toán tử; không tự subscribe vào chain. |
| `@RequestBody Mono<T>` hoặc `Flux<T>` | Nguồn body được tiêu thụ khi nó được kết hợp vào pipeline HTTP | Compose `input.flatMap(...)`; không tự subscribe trong controller. |
| `Flux` sự kiện hot, SSE | HTTP pipeline subscribe từng client; nguồn event có thể đang chạy độc lập | Xác định multicast, replay, backpressure và vòng đời nguồn. |
| Consumer nền, worker, event listener hay CLI không có HTTP framework tiêu thụ | Thành phần khởi động/consumer **do ứng dụng quản lý** | Có thể chủ động subscribe; quản lý `Disposable`, lỗi, hủy và shutdown. |
| Unit test pure Reactor | Test harness | Dùng `StepVerifier`; có thể `block()` tại test boundary phù hợp. |
| Test endpoint WebFlux | `WebTestClient`/server test infrastructure | Gọi `exchange()` rồi assert status/body; test client kích hoạt luồng HTTP. |

Không có nghĩa **mọi** subscription đều phải do WebFlux thực hiện. Quy tắc chỉ áp dụng khi publisher là kết quả của request/response mà framework sẽ tiêu thụ. Nếu bạn chủ động tạo một pipeline nằm ngoài bất kỳ boundary nào (ví dụ tác vụ chạy nền khi ứng dụng khởi động), không có HTTP consumer tự động “đến subscribe hộ”.

### Ví dụ terminal boundary ngoài request

```java
Disposable subscription = Flux.interval(Duration.ofSeconds(1))
        .subscribe(
                value -> handleTick(value),
                error -> handleFailure(error));

// Khi ứng dụng dừng:
subscription.dispose();
```

Đoạn **minh họa**, không phải ứng dụng chạy độc lập: cần import `reactor.core.Disposable`, `reactor.core.publisher.Flux`, `java.time.Duration` và định nghĩa `handleTick`/`handleFailure`. Với subscription sống lâu, lưu handle để dọn khi shutdown; khi cần độ tin cậy dữ liệu phải có phương án retry, giám sát lỗi và cơ chế lưu trạng thái. `subscribe()` hoàn toàn hợp lý ở đây **nếu** thành phần này sở hữu và quản lý vòng đời consumer.

## 7. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Không gọi `subscribe()` thì API không chạy.” | Với publisher trả trong WebFlux handler, HTTP runtime có consumer của nó và sẽ tiêu thụ chuỗi. |
| “`subscribe()` luôn bất đồng bộ.” | Không. Nguồn đồng bộ có thể chạy ngay trong thread hiện tại; cần scheduler/I/O bất đồng bộ để thay đổi execution context. |
| “`return Mono.just(service.call())` là lazy.” | `service.call()` thực thi trước khi `Mono.just` được tạo; dùng API reactive hoặc `defer` khi muốn trì hoãn. |
| “Gọi `subscribe()` trong controller sẽ giúp API phản hồi nhanh và ổn định.” | Response có thể trả trước khi công việc hoàn tất và không còn phản ánh lỗi; task cần background thì thiết kế cơ chế durable/background riêng. |
| “WebFlux luôn subscribe chính xác một lần.” | Không nên lấy đó làm hợp đồng: resubscribe, retry, repeat, cache/share, nhiều consumer hoặc tích hợp khác có thể thay đổi số lượt. |
| “Response HTTP hủy là mọi database call dừng lập tức.” | Cancellation là yêu cầu dừng, phụ thuộc nguồn và transport; side effect đã cam kết không tự hoàn tác. |
| “Có lỗi trong nhánh tự subscribe thì WebFlux chắc chắn trả HTTP 500.” | Subscription riêng có kênh lỗi riêng; response HTTP không tự động bị ảnh hưởng. |
| “Hai request share cùng `Flux` thì luôn dùng chung một `Subscription`.” | Mỗi subscriber có quan hệ đăng ký riêng; nguồn cold/hot quyết định tiến độ và dữ liệu có chia sẻ hay không. |
| “`doOnNext` dùng được cho mọi side effect, kể cả I/O async.” | `doOnNext` là callback quan sát đồng bộ; I/O reactive cần compose bằng `flatMap`/`then`. |
| “Dùng `block()` là cách lấy giá trị trong controller.” | `block()` tạo subscription khác và chặn thread; tránh ở request handler nonblocking. |

## 8. Bài tập tự kiểm tra

**Câu 1.** Vì sao endpoint sau vẫn phản hồi dù controller không gọi `subscribe()`?

```java
@GetMapping("/answer")
public Mono<Integer> answer() {
    return Mono.just(42);
}
```

**Đáp án:** Publisher được trả cho WebFlux. Pipeline của HTTP server tiêu thụ publisher để tạo response. Đây là snippet minh họa trong `@RestController`, cần các import tương ứng.

**Câu 2.** Đoạn sau bảo đảm lưu xong trước khi trả `ok` không?

```java
service.save(item).subscribe();
return Mono.just("ok");
```

**Đáp án:** Không. Hai pipeline tách rời, response không chờ hoàn tất/lỗi của `save`. Nếu `save` trả `Mono<?>`, một cách compose là `return service.save(item).thenReturn("ok");`. Đây là snippet minh họa, `service` và `item` do ứng dụng định nghĩa.

**Câu 3.** “Gọi `subscribe()` hai lần thì WebFlux sẽ gửi hai response” có đúng không?  
**Đáp án:** Không. Hai subscription tạo hai lần tiêu thụ publisher; chúng không tự biến thành hai response HTTP. Một response do WebFlux quản lý có vòng đời riêng. Nếu nguồn cold có side effect, hai subscription có thể lặp side effect ngoài ý muốn.

**Câu 4.** Một controller trả `Flux<Long>` sinh số theo timer. Client ngắt giữa chừng thì điều gì chắc chắn?  
**Đáp án:** Không thể bảo đảm chính xác mọi tác vụ sẽ dừng tại thời điểm ngắt. Hạ tầng có thể phát cancellation tới subscription; nguồn và operator phải tôn trọng cancellation, còn side effect đã chạy không thể tự động đảo ngược.

**Câu 5.** Khi nào tự subscribe là đúng?  
**Đáp án:** Tại boundary do ứng dụng chủ động sở hữu (background consumer, event stream, CLI), khi không có framework nào sẽ consume publisher thay mình, và ứng dụng quản lý đầy đủ completion, error, cancellation và resource lifetime.

## Ghi nhớ

**Trong WebFlux handler, hãy trả về `Mono`/`Flux` thể hiện toàn bộ công việc cần gắn với HTTP request.** WebFlux cùng reactive HTTP server tiêu thụ publisher để điều phối body, lỗi, backpressure và cancellation. Tự `subscribe()` trong controller tạo nhánh công việc độc lập, thường làm mất quan hệ giữa kết quả nghiệp vụ và response. Chỉ subscribe thủ công khi bạn thực sự sở hữu terminal boundary và vòng đời của subscriber.

### Tài liệu tham khảo

- [Spring Framework – Reactive Web Applications / WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): kiến trúc WebFlux và xử lý HTTP bất đồng bộ.
- [Spring Framework – @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): cách annotated controller ghi response body.
- [Project Reactor – Simple Ways to Create a Flux or Mono and Subscribe to It](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): subscription và terminal operations.
- [Project Reactor – Backpressure](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): demand và `BaseSubscriber`.
- [Reactive Streams for the JVM – Specification](https://github.com/reactive-streams/reactive-streams-jvm): các hợp đồng `Publisher`, `Subscriber` và `Subscription`.
