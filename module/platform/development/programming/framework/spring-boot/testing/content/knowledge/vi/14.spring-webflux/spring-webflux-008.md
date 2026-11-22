# Spring WebFlux: kiểm thử streaming, SSE và giới hạn thời gian chờ

## 1. Mục tiêu và phạm vi

Ứng dụng Spring WebFlux có thể trả về dữ liệu **dần theo thời gian** thay vì một JSON response hoàn chỉnh. Ví dụ: giá giao dịch cập nhật liên tục, tiến độ xử lý, thông báo realtime hoặc kết quả tính toán dài hạn. Kiểm thử một luồng như vậy cần quan sát **các tín hiệu Reactive Streams**, nội dung từng phần, thời gian phát và cách đóng luồng — không chỉ kiểm tra HTTP 200.

Bài học này tập trung vào:

- `Flux<T>`, `Mono<T>`, tín hiệu `onNext`, `onComplete`, `onError` và `cancel`.
- `text/event-stream` / **Server-Sent Events (SSE)**, các trường `id`, `event`, `data`, `retry` và tính chất kết nối dài.
- Streaming JSON dạng `application/x-ndjson` (một JSON object trên mỗi dòng).
- `WebTestClient` để xác nhận status, `Content-Type`, body của stream và phần tử nhận được.
- `StepVerifier` để kiểm tra thứ tự sự kiện, completion, error, cancellation, thời gian thật và **virtual time**.
- `timeout(Duration)` của Reactor (timeout giữa các tín hiệu), fallback, HTTP 504, client-side response timeout và deadline của hạ tầng.
- Backpressure, hủy subscription, cleanup, xử lý lỗi **sau khi HTTP headers đã được gửi**.
- Độ ổn định của test trong CI: không đọc hết stream vô hạn, không dùng `Thread.sleep` dài, không để phép `verify()` chờ không giới hạn.

Các ví dụ hoàn chỉnh dùng **Java 17, Spring Boot 3.5.0, Spring Framework 6.2, Reactor 3.7**, Maven, JUnit Jupiter và `reactor-test`. Spring Boot 4 có focused test starter và một số package test annotation khác; xem phần tương thích ở cuối bài.

### Kết quả cần chứng minh

| Điều muốn biết | Phép thử thích hợp | Bằng chứng |
| --- | --- | --- |
| Publisher tạo đúng phần tử | Pure Reactor + StepVerifier | Giá trị và thứ tự `onNext` |
| Event đến sau khoảng thời gian quy định | StepVerifier virtual time | Không có tín hiệu sớm, có tín hiệu sau khi tiến clock |
| Client có thể ngừng stream vô hạn | StepVerifier `thenCancel()` | Không treo; upstream nhận cancellation trong test Reactor |
| Endpoint trả đúng SSE | WebTestClient | HTTP 200, `text/event-stream`, `data/id/event` |
| NDJSON là nhiều object tách rời | WebTestClient streaming body | Decode 3 object; stream hoàn thành |
| Upstream quá chậm | Reactor timeout/fallback test | `TimeoutException` hoặc fallback/504 theo hợp đồng |
| Server thật flush dữ liệu | `@SpringBootTest(RANDOM_PORT)` + WebTestClient | Client nhận các phần tử qua socket thật |
| Backpressure không bị hiểu nhầm | StepVerifier initial demand nhỏ | Kiểm chứng chỉ phát theo request trên publisher phù hợp |

**Nguyên tắc:** một stream có thể không bao giờ `onComplete`. Test phải có **điều kiện kết thúc riêng** bằng `take(n)` cho publisher phù hợp hoặc `thenCancel()` khi đang đọc HTTP stream. Không dùng `collectList()` hay `blockLast()` vô điều kiện với nguồn vô hạn.

## 2. Cơ chế của Reactive Streams trong WebFlux

Một `Publisher` theo Reactive Streams gửi các tín hiệu:

```text
subscribe
   |
   v
onSubscribe(Subscription)
   |
request(n)  ---> onNext(item1), onNext(item2), ...
   |
   +----> onComplete()           [kết thúc bình thường]
   |
   +----> onError(Throwable)     [kết thúc lỗi]
   |
   +----> cancel()               [subscriber hủy, không chờ terminal]
```

Luồng chỉ có **tối đa một terminal signal**: `onComplete` hoặc `onError`. `cancel()` là hành động của downstream để chấm dứt nhu cầu nhận tiếp, **không phải** một terminal signal bình thường được phát tới subscriber. Sau khi cancel, các nguồn tuân thủ Reactive Streams nên ngừng gửi thêm dữ liệu tới subscriber đó.

Một vài điểm dễ nhầm:

1. `Flux.just(1,2,3)` là **hữu hạn**, có completion; `Flux.interval(Duration)` có thể **vô hạn** nếu không có `take` hoặc điều kiện dừng.
2. `Flux.interval` phát dựa trên scheduler; trong test có virtual time cần **tạo publisher sau khi virtual scheduler được thiết lập**.
3. `Flux.never()` không phát phần tử, không complete và không error. Dùng nó để test timeout rất tốt; dùng nó với `expectComplete()` mà không có timeout cho verifier thì test có thể treo.
4. `Flux.empty()` hoàn thành ngay nhưng không phát dữ liệu. Khác hẳn `Flux.never()`.
5. `Flux.error(ex)` phát lỗi ngay. Có thể assert loại exception và thời điểm.
6. `Flux.take(n)` sẽ lấy `n` item rồi cancel phần upstream khi cần và phát completion downstream; không tương đương với việc upstream tự kết thúc tự nhiên.
7. `doFinally(SignalType.CANCEL)` thích hợp để kiểm tra cleanup khi cancel ở **cấp Reactor**; đừng giả định HTTP client cancel sẽ đồng bộ làm server chạy callback ngay trước khi test assert.

## 3. SSE khác JSON response và NDJSON thế nào?

SSE là cơ chế server đẩy sự kiện theo **HTTP một chiều**. Client gửi GET, server giữ response đang mở và liên tiếp gửi những bản ghi văn bản theo định dạng `text/event-stream`. Ví dụ wire format (chỉ minh họa; trình tự xuống dòng là thành phần quan trọng):

```text
id: 1
event: tick
retry: 2000
data: {"number":1,"text":"tick-1"}

id: 2
event: tick
retry: 2000
data: {"number":2,"text":"tick-2"}

```

Một dòng trống kết thúc một SSE event. Spring có thể bổ sung charset, và JSON encoder có thể chọn spacing/escaping khác. **Không kiểm tra raw byte bằng so sánh nguyên chuỗi nếu điều bạn cần xác minh là dữ liệu typed**. Dùng decoder đọc `ServerSentEvent<T>` hoặc payload type `T`; chỉ thử raw format khi hợp đồng cần wire-level compatibility.

Các trường:

| Trường SSE | Vai trò | Điều nên test |
| --- | --- | --- |
| `data` | Payload; có thể là JSON object | Schema, field values, order nếu có ý nghĩa |
| `id` | Event identifier; browser dùng làm last event ID | Tính nhất quán/không trùng, đặc biệt khi reconnect |
| `event` | Tên event (ví dụ `tick`, `progress`) | Đúng tên mà frontend subscribe |
| `retry` | Gợi ý thời gian browser EventSource reconnect (milliseconds trên wire) | Đúng chính sách nếu API công bố |
| Comment `: ...` | Có thể dùng heartbeat/keep-alive, không phải business event | Kết nối không bị idle proxy cắt, không tăng event business count |
| `Last-Event-ID` | Header từ client khi reconnect | Resume/replay **chỉ hoạt động nếu server tự hỗ trợ** |

**Không tự mặc định có replay.** Việc server gửi `id` không bảo đảm endpoint hỗ trợ nhận `Last-Event-ID`, truy xuất sự kiện cũ, deduplicate hoặc exactly-once delivery. Nếu có yêu cầu reconnect, cần thêm test riêng cho sự kiện bị mất, trùng lặp, cursor/offset và chính sách lưu lịch sử.

### So sánh ba kiểu trả dữ liệu

| Kiểu | Media type | Phương thức/controller | Đặc điểm |
| --- | --- | --- | --- |
| JSON kết quả đầy đủ | `application/json` | `Mono<List<T>>` hoặc `Flux<T>` được serialize thành mảng | Client thường đợi body hoàn chỉnh |
| SSE | `text/event-stream` | `Flux<ServerSentEvent<T>>` hoặc `Flux<T>` với produces SSE | Mỗi event được emit/flush dần; có metadata SSE |
| NDJSON | `application/x-ndjson` | `Flux<T>` | Mỗi phần tử thành JSON object trên một dòng; không có `id/event/retry` SSE |

Một `Flux<T>` với `produces = application/json` không tự động có nghĩa client quan sát mỗi phần tử ngay khi nó được tạo; codec/flush strategy tùy content type. Khi muốn streaming rõ ràng, chọn `text/event-stream` hoặc `application/x-ndjson` và kiểm tra thực tế qua client.

## 4. WebTestClient: đọc stream mà không chờ kết thúc

Theo tài liệu chính thức Spring Framework, chuỗi kiểm tra streaming điển hình là:

```java
FluxExchangeResult<MyEvent> response = client.get()
        .uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
        .returnResult(MyEvent.class);

StepVerifier.create(response.getResponseBody())
        .expectNext(expectedFirst)
        .expectNext(expectedSecond)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Đây là **trích đoạn**: `MyEvent`, `client` và các expected objects phải được định nghĩa trước. Mã đầy đủ của dự án ở phần 8–10.

Quan trọng:

- `exchange()` gửi request/nhận response; `expectStatus` và `expectHeader` xác nhận giao thức.
- `returnResult(MyEvent.class)` trả `FluxExchangeResult<MyEvent>` để test **subscribe/consume** các event đến dần.
- `getResponseBody()` là `Flux<MyEvent>`; `StepVerifier` kiểm tra các `onNext`.
- `thenCancel()` đóng subscription sau số event mong muốn; thích hợp với **stream vô hạn**.
- `verify(Duration.ofSeconds(5))` tạo hạn mức thời gian thực cho toàn bộ kịch bản. Không dựa vào `verify()` vô hạn.
- Đối với generic SSE bao gồm metadata, dùng `returnResult(new ParameterizedTypeReference<ServerSentEvent<MyEvent>>() {})` khi decoder/codec được cấu hình phù hợp.
- Với NDJSON **hữu hạn**, có thể kết thúc bằng `expectComplete().verify(Duration)`.

### Không dùng expectBodyList cho một stream vô hạn

```java
// Tránh dùng với endpoint vô hạn: có thể phải đợi mãi đến completion.
client.get().uri("/events").exchange()
    .expectBodyList(MyEvent.class);

// Đúng mục tiêu: lấy một số event, sau đó cancel.
FluxExchangeResult<MyEvent> response = client.get()
    .uri("/events")
    .exchange()
    .returnResult(MyEvent.class);
StepVerifier.create(response.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Hai đoạn trên chỉ minh họa. Với stream được giới hạn `take(3)` tại server, `expectComplete` là hợp lý, nhưng với server không bao giờ hoàn thành, test có thể treo hoặc vượt memory nếu cố gom body.

### Test bind-to-controller và server thật không tương đương

`WebTestClient` có thể:

- `bindToController(new Controller(...))`: thử WebFlux controller trực tiếp với mock exchange, không cần Spring Boot context.
- `bindToApplicationContext(context)`: thử WebFlux stack trong Spring test context, không mở TCP server.
- `bindToRouterFunction(routes)`: thử functional WebFlux endpoints.
- `bindToServer().baseUrl(...).build()`: gửi HTTP thật tới một server đang chạy.
- `@WebFluxTest`: Spring Boot slice tạo context WebFlux hẹp và auto-configure WebTestClient.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)`: mở real embedded server, có thể tạo client được bind tới port động.

Mock-bound tests kiểm tra routing, encoding, filters và response phù hợp trong mock exchange; chúng **không chứng minh** socket behavior, reverse proxy, TCP disconnect hoặc buffering trên production infrastructure. Để kiểm tra streaming flush thật và HTTP connection termination, cần ít nhất một integration test với server thật.

## 5. StepVerifier: tín hiệu, thời gian và cancellation

`reactor-test` cung cấp `StepVerifier` để mô tả kỳ vọng trên `Publisher`.

### Giá trị và completion

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Kỳ vọng đúng ba `onNext` rồi `onComplete`. Nếu Flux phát thêm, phát lỗi hoặc không complete, test FAIL.

### Error

```java
StepVerifier.create(
        Flux.concat(Flux.just("A"),
                    Flux.error(new IllegalStateException("stopped"))))
    .expectNext("A")
    .expectErrorMatches(ex -> ex instanceof IllegalStateException
            && "stopped".equals(ex.getMessage()))
    .verify(Duration.ofSeconds(2));
```

Luồng có thể phát một số item **rồi error**; không giả định error luôn xuất hiện trước item đầu. Trong HTTP streaming, lỗi xuất hiện sau khi response headers đã commit không còn có thể đổi status thành 500/504; xử lý phụ thuộc contract và client.

### Cancellation

```java
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

Trong ví dụ này `Flux.interval` phát 0 ở lần đầu (sau một interval) và 1 ở lần thứ hai. `thenCancel` không đợi complete. Test **cấp Reactive Streams** có thể dùng `doFinally` để assert upstream cleanup; test HTTP thật thường chỉ chứng minh client ngừng nhận, không chứng minh ngay lập tức mọi tài nguyên server đã giải phóng.

### Hạn mức cho phép kiểm chứng

Có hai loại “timeout” cần phân biệt:

- **Timeout của nghiệp vụ:** `Mono/Flux.timeout(Duration)`, làm Publisher phát `TimeoutException` nếu không có tín hiệu tiếp theo trước hạn.
- **Timeout của test harness:** `StepVerifier.verify(Duration)`, khiến test FAIL nếu kỳ vọng chưa hoàn tất trong hạn mức thực.

Đặt cả hai rõ ràng khi test nhạy với thời gian. Hạn mức verifier thường **dài hơn** deadline nghiệp vụ để có thời gian cho CI scheduling.

## 6. Virtual time để test timeout mà không sleep thật

Reactor cho phép `StepVerifier.withVirtualTime(() -> publisher)` thay scheduler mặc định bằng scheduler ảo và điều khiển thời gian bằng `thenAwait`/`expectNoEvent`.

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
            .map(n -> "ready"))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(59))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext("ready")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
```

Test không thực sự đợi một giờ. Nhưng có ba quy tắc:

1. **Tạo time-based publisher bên trong lambda** của `withVirtualTime`. Nếu tạo `Flux.interval` trước rồi lambda chỉ trả lại instance đã tạo, timer có thể đã gắn scheduler thật.
2. `expectNoEvent(Duration)` cũng coi **subscription** là một event. Bởi vậy viết `expectSubscription()` trước `expectNoEvent(...)`.
3. `thenAwait(Duration)` chỉ tiến đồng hồ ảo; `expectNoEvent(Duration)` tiến đồng hồ **và** assert không có tín hiệu trong khoảng đó. Không dùng hai cái thay nhau nếu bạn cần kiểm chứng “chưa phát sớm”.

Thời gian ảo không thay được network timeout, blocking I/O, JDBC query hoặc mọi scheduler tùy biến. Test dùng `Thread.sleep` hoặc client HTTP thật **không nhanh lên** chỉ vì có virtual time. Khi có nhiều `publishOn`, `flatMap`, scheduler riêng, demand không đủ hoặc vô hạn emit cùng một thời điểm, virtual time có thể gây deadlock/starvation nếu thiết kế không đúng.

### Timeout “không nhận signal trong 3 giây”

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(2))
    .thenAwait(Duration.ofSeconds(1))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));
```

Ở đây timeout là lỗi nghiệp vụ sau **3 giây ảo**. Hạn mức `verify(2 seconds)` vẫn là **thời gian thật**, dùng để fail thay vì treo nếu test bị thiết kế sai. Để snippet biên dịch, cần imports `Mono`, `StepVerifier`, `Duration` và `TimeoutException`.

## 7. Phân biệt các lớp timeout trong ứng dụng WebFlux

| Lớp | Cơ chế | Tác động | Cách test |
| --- | --- | --- | --- |
| **Publisher first/next-signal timeout** | `Mono/Flux.timeout(Duration)` | Không có signal đúng hạn → `TimeoutException`, hoặc fallback nếu cung cấp | Pure Reactor + virtual time |
| **Response deadline trước khi commit** | Server mapping `TimeoutException` → HTTP 504 | Client nhận 504, nếu headers chưa commit | WebTestClient/HTTP integration |
| **Stream idle timeout** | `Flux.timeout(Duration)` sau mỗi `onNext` | Một khoảng im lặng quá lâu làm stream lỗi; có thể đã gửi 200 | StepVerifier cho sequence có gap |
| **Client response timeout** | `WebTestClient.Builder.responseTimeout(Duration)` | Giới hạn thời gian test client đợi response operation | WebTestClient, giới hạn riêng |
| **Connection/TCP timeout** | Reactor Netty/WebClient options | Connect/read/write/idle behavior transport | Real-server/stub/proxy integration |
| **Infrastructure idle timeout** | Gateway/LB/reverse proxy/network | Đóng SSE connection khi không có bytes | Staging/contract test qua đúng hạ tầng |
| **Test verifier timeout** | `verify(Duration)` | Bảo vệ CI không treo nếu publisher không đạt expectation | Mọi test streaming dài |

HTTP 504 là một **lựa chọn API contract** (Gateway Timeout). Spring Reactor `timeout` tự nó phát `TimeoutException`; nếu không xử lý, HTTP server có thể trả 500 hoặc đóng connection tùy thời điểm. Muốn 504, phải **map rõ ràng** ở tầng API khi còn có thể đặt status.

### Timeout trên Flux được tính lại sau mỗi item

```java
Flux<String> source = Flux.concat(
        Flux.just("first"),
        Mono.delay(Duration.ofSeconds(10)).map(n -> "second"));

Flux<String> guarded = source.timeout(Duration.ofSeconds(3));
```

Nguồn phát `first` ngay, rồi im lặng 10 giây. `timeout(3s)` sẽ phát `TimeoutException` khoảng 3 giây sau `first`, **không** chờ toàn bộ stream 10 giây. Đây là **idle-gap timeout**, không phải “thời gian toàn bộ request phải kết thúc trong 3 giây”.

Nếu nghiệp vụ cần một deadline cố định cho **toàn bộ hoạt động**, có thể dùng một nguồn timer hoặc áp dụng time budget riêng, không mặc định `Flux.timeout(Duration)` biểu diễn request-wide deadline vì timer reset khi có item mới.

### Fallback và exception mapping

```java
Mono<String> fallback = upstream
        .timeout(Duration.ofMillis(100), Mono.just("cached"));

Mono<String> error = upstream
        .timeout(Duration.ofMillis(100))
        .onErrorMap(TimeoutException.class,
                ex -> new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "upstream deadline exceeded", ex));
```

Đây là trích đoạn, `upstream` là `Mono<String>` được truyền từ service, cần imports. Fallback trả 200 khi chính controller chọn “cached” làm phản hồi; API quan trọng cần đánh dấu việc dùng dữ liệu stale nếu contract yêu cầu. `onErrorMap` chuyển exception thành lỗi HTTP 504 **nếu response chưa commit**.

### Không thể đổi HTTP status sau khi đã stream dữ liệu

Khi server đã gửi `200 OK` và một số SSE events, việc upstream lỗi không thể “thu hồi” HTTP 200 rồi đổi thành 504. Hướng xử lý cần đặc tả rõ:

- Đóng stream để client reconnect; có `id` và cursor/resume nếu cần.
- Phát một **SSE event loại error** (ví dụ `event: error` với payload an toàn) rồi complete; đây vẫn là HTTP 200 đã commit.
- Dùng heartbeat và server/client timeout policy để xử lý idle.
- Với stream hữu hạn cần atomic response/error status, có thể cân nhắc buffer toàn bộ trước khi ghi, chấp nhận chi phí bộ nhớ/độ trễ.

Không test “HTTP 504 sau sự kiện thứ ba” nếu response đã commit, trừ khi bạn đang kiểm chứng một giao thức riêng có status bên trong dữ liệu.

## 8. Dự án Java 17 chạy được: SSE, NDJSON, deadline và fallback

Ví dụ dưới đây không cần DB, Docker hoặc external API. Mô hình có ba tầng:

- `StreamService` sinh `Tick` và giả lập tác vụ chậm.
- `StreamController` định nghĩa các endpoint streaming/timeout.
- Ba nhóm test: **pure Reactor**, **`@WebFluxTest`**, **`@SpringBootTest(RANDOM_PORT)`**.

### 8.1. Cây thư mục

```text
webflux-stream-demo/
├── pom.xml
└── src/
    ├── main/java/example/sse/
    │   ├── SseApplication.java
    │   ├── Tick.java
    │   ├── StreamService.java
    │   └── StreamController.java
    └── test/java/example/sse/
        ├── StreamServiceTest.java
        ├── StreamControllerTest.java
        └── StreamHttpIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>example</groupId>
    <artifactId>webflux-stream-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
</project>
```

`reactor-test` được khai báo tường minh để các `StepVerifier` tests không phụ thuộc việc starter test cụ thể có kéo nó vào classpath hay không. Spring Boot parent quản lý version của Reactor Test/JUnit, không khai báo phiên bản riêng. Chỉ dùng `spring-boot-starter-webflux` cho server WebFlux trong demo, tránh kéo `spring-boot-starter-web` vào cùng app: nếu cả Spring MVC và WebFlux cùng trên classpath, Spring Boot thường ưu tiên MVC trừ khi cấu hình application type thành reactive.

### 8.3. SseApplication.java

```java
package example.sse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SseApplication {
    public static void main(String[] args) {
        SpringApplication.run(SseApplication.class, args);
    }
}
```

### 8.4. Tick.java

```java
package example.sse;

public record Tick(long number, String text) {
}
```

Record có constructor, equality và accessors `number()`/`text()`. Jackson của Spring Boot 3.5 hỗ trợ serialization/deserialization record. Test có thể so sánh `new Tick(1, "tick-1")` với object đã decode mà không cần viết thủ công `equals`.

### 8.5. StreamService.java

```java
package example.sse;

import java.time.Duration;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class StreamService {
    public Flux<Tick> ticks(Duration period) {
        return Flux.interval(period)
                .map(n -> new Tick(n + 1, "tick-" + (n + 1)));
    }

    public Mono<String> delayed(Duration delay) {
        return Mono.delay(delay).map(n -> "ready");
    }
}
```

`Flux.interval(period)` phát số 0 sau một period rồi 1, 2...; service chuyển thành `Tick(number=1, ...)` cho lần đầu. Luồng `ticks` là **vô hạn** nếu không bị cancel/take. `delayed` phát một chuỗi `"ready"` sau khoảng chờ, phù hợp để mô phỏng slow upstream mà không gọi mạng thật.

**Lưu ý thực tế:** `Flux.interval` phụ thuộc scheduler và nếu downstream không đủ demand có thể lỗi overflow. Đối với production, việc dùng hot sources, buffers/drop/latest/replay, rate limit và backpressure phải được thiết kế theo loại dữ liệu. Không dùng infinite tick generator này như một hệ thống message broker có bảo đảm delivery.

### 8.6. StreamController.java

```java
package example.sse;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamController {
    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @GetMapping(
            path = "/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Tick>> sse() {
        return service.ticks(Duration.ofMillis(50))
                .map(tick -> ServerSentEvent.<Tick>builder(tick)
                        .id(Long.toString(tick.number()))
                        .event("tick")
                        .retry(Duration.ofSeconds(2))
                        .build());
    }

    @GetMapping(
            path = "/ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Tick> ndjson() {
        return service.ticks(Duration.ofMillis(20)).take(3);
    }

    // 250 ms upstream vs 50 ms deadline: timeout trước khi có body.
    @GetMapping(
            path = "/deadline",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> deadline() {
        return service.delayed(Duration.ofMillis(250))
                .timeout(Duration.ofMillis(50))
                .onErrorMap(TimeoutException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.GATEWAY_TIMEOUT,
                                "upstream deadline exceeded", ex));
    }

    // Hợp đồng cho phép fallback thay vì trả lỗi.
    @GetMapping(
            path = "/fallback",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> fallback() {
        return service.delayed(Duration.ofMillis(250))
                .timeout(Duration.ofMillis(50),
                        Mono.just("fallback"));
    }
}
```

Bốn endpoint có mục tiêu riêng:

| Endpoint | Behavior | Expected |
| --- | --- | --- |
| `GET /api/sse` | Infinite SSE, mỗi event có data/id/event/retry | 200, `text/event-stream`, client nhận 1/2/... và cancel |
| `GET /api/ndjson` | Ba Tick rồi complete | 200, `application/x-ndjson`, đúng ba objects |
| `GET /api/deadline` | Upstream cần 250 ms nhưng deadline 50 ms | 504 trước khi gửi body |
| `GET /api/fallback` | Cùng upstream chậm nhưng có fallback | 200, body `fallback` |

Đây là cấu hình học tập với thời gian ngắn; hệ thống thật cần timeout budgets theo service-level objective, network hops và tải thực tế. Không dùng các giá trị 50/250 ms làm default production khi chưa có số liệu.

## 9. Pure Reactor tests: virtual time, timeout, hủy subscription

Tạo `src/test/java/example/sse/StreamServiceTest.java`:

```java
package example.sse;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

class StreamServiceTest {
    private final StreamService service = new StreamService();

    @Test
    void ticksFollowVirtualTimeCadence() {
        StepVerifier.withVirtualTime(() ->
                service.ticks(Duration.ofSeconds(10)).take(3))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(new Tick(1, "tick-1"))
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(new Tick(2, "tick-2"))
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(new Tick(3, "tick-3"))
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void timeoutTriggersWhenThereIsNoSignal() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void slowWorkFallsBackAtVirtualDeadline() {
        StepVerifier.withVirtualTime(() ->
                service.delayed(Duration.ofSeconds(8))
                    .timeout(Duration.ofSeconds(3),
                            Mono.just("fallback")))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("fallback")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void fastWorkCompletesBeforeDeadline() {
        StepVerifier.withVirtualTime(() ->
                service.delayed(Duration.ofSeconds(3))
                    .timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("ready")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void cancellingStreamTriggersUpstreamCleanup() {
        AtomicReference<SignalType> termination =
                new AtomicReference<>();

        StepVerifier.withVirtualTime(() ->
                service.ticks(Duration.ofSeconds(2))
                    .doFinally(termination::set))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(new Tick(1, "tick-1"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(SignalType.CANCEL, termination.get());
    }

    @Test
    void timeoutMeasuresGapBetweenEmissions() {
        StepVerifier.withVirtualTime(() ->
                Flux.concat(
                        Flux.just("first"),
                        Mono.delay(Duration.ofSeconds(10))
                            .map(n -> "second"))
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNext("first")
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }
}
```

**Có 6 test methods.** Không có Spring annotations: `new StreamService()` chạy pure Reactor. Tất cả phép kiểm tra thời gian được tiến bằng virtual clock; test dùng `verify(Duration)` để không chờ vô hạn nếu expected signal không đến.

### Giải thích từng case

- `ticksFollowVirtualTimeCadence`: các Tick đến tại 10/20/30 giây ảo, không có Tick trước ngưỡng. `take(3)` khiến publisher downstream complete và upstream hủy.
- `timeoutTriggersWhenThereIsNoSignal`: `Mono.never()` không phát event; 3 giây ảo trôi qua làm `timeout` phát `TimeoutException`.
- `slowWorkFallsBackAtVirtualDeadline`: nguồn có thể trả `ready` sau 8 giây, nhưng fallback kích hoạt ở 3 giây.
- `fastWorkCompletesBeforeDeadline`: nguồn phát sau 3 giây, deadline là 5; luồng trả `ready` và complete.
- `cancellingStreamTriggersUpstreamCleanup`: `doFinally` quan sát `CANCEL` trong test ở cấp publisher; không suy luận callback network server chạy ngay khi một client disconnect.
- `timeoutMeasuresGapBetweenEmissions`: đã nhận `first` vẫn có thể timeout nếu khoảng im lặng giữa các item vượt 3 giây.

### Dấu hiệu lỗi khi dùng virtual time

Nếu test đứng ở `expectNext` nhưng không có `thenAwait`, timer ảo có thể chưa được tiến. Nếu publisher được tạo ngoài lambda, scheduler ảo có thể không quản lý timer của nó. Nếu `expectNoEvent` được dùng ngay từ đầu mà không có `expectSubscription`, nó có thể FAIL vì subscription được coi là signal. Với nguồn blocking thật, không dùng virtual time để giả định I/O đã được tăng tốc.

## 10. @WebFluxTest: kiểm tra SSE metadata, NDJSON và timeout ở HTTP layer

Tạo `src/test/java/example/sse/StreamControllerTest.java`:

```java
package example.sse;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@WebFluxTest(StreamController.class)
class StreamControllerTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    StreamService service;

    @Test
    void sseContainsIdNameAndTypedPayload() {
        when(service.ticks(any(Duration.class))).thenReturn(
                Flux.just(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"))
                    .concatWith(Flux.never()));

        FluxExchangeResult<ServerSentEvent<Tick>> result =
                client.get().uri("/api/sse")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.TEXT_EVENT_STREAM)
                    .returnResult(
                            new ParameterizedTypeReference<
                                    ServerSentEvent<Tick>>() {});

        StepVerifier.create(result.getResponseBody())
                .assertNext(event -> {
                    assertEquals("1", event.id());
                    assertEquals("tick", event.event());
                    assertEquals(new Tick(1, "tick-1"),
                            event.data());
                })
                .assertNext(event -> {
                    assertEquals("2", event.id());
                    assertEquals("tick", event.event());
                    assertEquals(new Tick(2, "tick-2"),
                            event.data());
                })
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        verify(service).ticks(any(Duration.class));
    }

    @Test
    void ndjsonHasThreeObjectsAndCompletes() {
        when(service.ticks(any(Duration.class))).thenReturn(
                Flux.just(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"),
                        new Tick(3, "tick-3")));

        FluxExchangeResult<Tick> result =
                client.get().uri("/api/ndjson")
                    .accept(MediaType.APPLICATION_NDJSON)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.APPLICATION_NDJSON)
                    .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"),
                        new Tick(3, "tick-3"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void deadlineMapsSlowUpstreamToHttp504() {
        when(service.delayed(any(Duration.class)))
                .thenReturn(Mono.never());

        client.get().uri("/api/deadline")
                .exchange()
                .expectStatus().isEqualTo(504);
    }

    @Test
    void fallbackReturns200AndExplicitValue() {
        when(service.delayed(any(Duration.class)))
                .thenReturn(Mono.never());

        client.get().uri("/api/fallback")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("fallback");
    }

    @Test
    void fastUpstreamDoesNotUseFallback() {
        when(service.delayed(any(Duration.class)))
                .thenReturn(Mono.just("ready"));

        client.get().uri("/api/fallback")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ready");
    }
}
```

**Có 5 test methods.** `@WebFluxTest(StreamController.class)` chỉ nạp test slice WebFlux; `StreamService` là bean mock bởi `@MockitoBean`, vì vậy test xác minh controller mapping, content type, SSE serialization/decoding và timeout mapping **không chờ service interval thật**.

### Tại sao thử SSE với generic type?

`ServerSentEvent<Tick>` cho phép assert metadata `id`/`event` và payload typed. `ParameterizedTypeReference` giữ thông tin generic `Tick` khi WebTestClient decode SSE. Nếu test chỉ cần dữ liệu, có thể `returnResult(Tick.class)` và kiểm tra từng item; nhưng khi cần bảo đảm frontend sẽ subscribe đúng tên event hay sử dụng `Last-Event-ID`, nên thử cả metadata.

`Flux.just(...).concatWith(Flux.never())` cho hai business events rồi vẫn mở kết nối; test `thenCancel()` kết thúc một cách chủ động. Nếu chỉ trả `Flux.just(...)` thì stream sẽ tự complete và không thử được yêu cầu “client cancel một SSE stream chưa đóng”.

### Không coi test 504 là timeout của client

Ở `deadlineMapsSlowUpstreamToHttp504`, `Mono.never()` do service mock trả và controller dùng **Reactor `timeout(50ms)`**, sau đó ánh xạ `TimeoutException` sang `ResponseStatusException(504)`. Đây là deadline của ứng dụng, **không phải** WebTestClient tự timeout. Nếu client tự timeout trước, test thường nhận exception từ client chứ không phải HTTP status 504 hợp lệ.

## 11. HTTP integration: kiểm tra stream thực từ Reactor Netty

Tạo `src/test/java/example/sse/StreamHttpIntegrationTest.java`:

```java
package example.sse;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamHttpIntegrationTest {
    @LocalServerPort
    int port;

    private WebTestClient liveClient() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void liveSseDeliversTwoEventsAndCanBeCancelled() {
        FluxExchangeResult<Tick> result = liveClient()
                .get().uri("/api/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(1, "tick-1"))
                .expectNext(new Tick(2, "tick-2"))
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void liveNdjsonDeliversThreeAndCompletes() {
        FluxExchangeResult<Tick> result = liveClient()
                .get().uri("/api/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"),
                        new Tick(3, "tick-3"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void liveDeadlineReturnsHttp504() {
        liveClient().get().uri("/api/deadline")
                .exchange()
                .expectStatus().isEqualTo(504);
    }
}
```

**Có 3 test methods.** `@SpringBootTest(RANDOM_PORT)` khởi chạy embedded server thật (Reactor Netty khi chỉ có WebFlux starter); `@LocalServerPort` nhận port do hệ điều hành cấp. `WebTestClient.bindToServer()` gửi HTTP thực qua loopback.

Bằng chứng từ test:

1. SSE được flush từng phần để client nhận ít nhất hai event dù stream không bao giờ complete.
2. Client có thể hủy sau hai events thay vì đợi connection vô hạn.
3. NDJSON gồm ba object được stream và kết thúc đúng cách.
4. Deadline được server phản ánh bằng HTTP 504 trước khi commit success body.

**Giới hạn:** test chạy trên loopback, không kiểm tra đúng proxy/cdn/gateway hoặc trình duyệt EventSource production. Nó cũng không chứng minh rằng cancellation của HTTP client đã giải phóng tài nguyên server tại cùng một thời điểm trước khi test kết thúc. Việc đó cần quan sát resource lifecycle ở server và có thể dùng metrics/logging/integration test riêng.

### Hạn mức 5 giây có vai trò gì?

`responseTimeout(5s)` bảo vệ client trước một server không trả response đúng hạn. `StepVerifier.verify(5s)` giới hạn thời gian quan sát/tiêu thụ body sau khi đã nhận response. Chúng **không thay thế** `timeout(50ms)` ở controller, vốn là quy tắc nghiệp vụ. Đặt hai tầng hạn mức giúp test không bị treo nếu có bug tạo stream.

Không lấy `RANDOM_PORT` làm lý do bắt buộc test chạy chậm: bài demo phát event sau 50 ms, deadline sau 50 ms; việc khởi động Spring context có thể chiếm phần lớn thời gian. Nếu CI tải nặng, điều chỉnh hạn mức test harness dựa vào số liệu, không nới mọi business deadline chỉ để làm test pass.

## 12. Chạy Maven và kỳ vọng

Từ thư mục chứa `pom.xml`, yêu cầu JDK 17+ và Maven có thể tải dependencies:

```bash
mvn test
```

Chạy riêng từng nhóm:

```bash
mvn test -Dtest=StreamServiceTest
mvn test -Dtest=StreamControllerTest
mvn test -Dtest=StreamHttpIntegrationTest
```

Số method `@Test` trong dự án mẫu:

| Class | Số test | Phạm vi |
| --- | --- | --- |
| `StreamServiceTest` | 6 | Publisher values, virtual interval, timeout, fallback, cancellation, idle gap |
| `StreamControllerTest` | 5 | Mock-bound SSE metadata, NDJSON, HTTP 504, fallback/fast |
| `StreamHttpIntegrationTest` | 3 | HTTP real SSE, NDJSON, deadline |
| **Tổng** | **14** | Không dùng DB/Docker |

Kỳ vọng **14 PASS, 0 FAIL, 0 SKIPPED** trong môi trường phù hợp. Đây là kết quả mong đợi của mã ví dụ; cần thực sự chạy trên máy có dependencies để xác nhận. Source không dùng `System.out.println`, nên không có stdout cố định của ứng dụng. Maven/JUnit có thể in logs khác nhau; xem báo cáo `target/surefire-reports` và kiểm tra số test thực sự được chạy, không chỉ `BUILD SUCCESS`.

Với code trên, các test Reactor ảo tiến vài chục giây virtual nhưng không sleep từng giây thật. Test HTTP thật chỉ dùng interval ngắn và client có hạn mức 5 giây. Không chờ completion của endpoint vô hạn `/api/sse`.

## 13. SSE reconnect, Last-Event-ID và idempotency

Frontend dùng `EventSource` thường tự động reconnect sau khi connection bị ngắt, có thể gửi `Last-Event-ID` cho server. Nhưng WebFlux `ServerSentEvent.builder().id(...)` **chỉ điền metadata**; server phải tự implement resume/history nếu muốn phát lại đúng dữ liệu.

Một thiết kế có replay có thể dùng:

- Event store ghi các business events với sequence tăng dần và retention policy.
- Client gửi `Last-Event-ID` (nếu có).
- Server kiểm tra quyền truy cập, xác định cursor và phát các events sau ID đó, rồi chuyển sang live feed.
- Duplicate/out-of-order detection nếu event store và live stream giao nhau.
- Resume strategy cho ID quá cũ, event retention hết, hoặc client không có ID.

### Ma trận test reconnect

| Kịch bản | Given | Then |
| --- | --- | --- |
| Connect lần đầu | Không có Last-Event-ID | Nhận events hiện hành/initial snapshot đúng hợp đồng |
| Disconnect sau ID 10 | Client reconnect với `Last-Event-ID: 10` | Nếu contract có replay, nhận từ 11 (hoặc trạng thái snapshot được chỉ định) |
| ID không tồn tại | ID malformed hoặc đã hết retention | Response/status/event policy rõ ràng, không crash |
| Duplicate replay | Backend phát lại một event | Client/idempotency logic không xử lý side effect hai lần |
| Client không có quyền | Subscription tới stream khác tenant | Trả 401/403 hoặc đóng kết nối theo security policy |
| Connection bị proxy ngắt | Idle lâu | Heartbeat hoặc reconnect strategy được kiểm chứng |

**Đừng mặc định exactly-once delivery.** SSE chạy trên HTTP và reconnect có thể tạo khoảng dữ liệu trùng/mất nếu không có event persistence và replay. Các guarantee cần được định nghĩa ở tầng sản phẩm, không thể suy ra chỉ từ sự tồn tại của trường `id`.

### Heartbeats là tín hiệu truyền tải, không phải business event

Một số hệ thống gửi comment SSE như `: heartbeat` để giữ kết nối qua proxy có idle timeout. Client EventSource thường không giao comment đó tới event handler như một business event. Test raw wire/transport hoặc metrics nên xác nhận heartbeat được phát đủ nhịp; test business events không được đếm heartbeat thành một Tick.

## 14. Backpressure, buffering và slow consumers

Reactive Streams có cơ chế **demand**: subscriber gọi `request(n)` để chỉ định số phần tử muốn nhận. Với nguồn thích hợp, điều này giúp producer không đẩy vô hạn vào consumer chậm.

Một ví dụ test demand không cần HTTP:

```java
AtomicLong requested = new AtomicLong();

StepVerifier.create(
        Flux.range(1, 3).doOnRequest(requested::addAndGet),
        0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .expectComplete()
    .verify(Duration.ofSeconds(2));

assertEquals(3L, requested.get());
```

Đây là **trích đoạn** với imports `AtomicLong`, `Flux`, `StepVerifier` và `assertEquals`. Tham số `0` của `StepVerifier.create(publisher, 0)` khởi động với **zero demand**. Sau đó test yêu cầu một item rồi hai item; `doOnRequest` quan sát các yêu cầu đi ngược lên nguồn.

**Không suy luận backpressure của toàn pipeline từ HTTP headers/status.** HTTP transport, Netty buffering, codec, operator như `publishOn`/`flatMap`, prefetch và downstream demand có thể thay đổi số lượng request/bytes. Một HTTP test chỉ nhận 2 events rồi cancel không bảo đảm upstream chỉ từng được request đúng 2 items.

Nguồn thời gian như `Flux.interval` có thể báo overflow nếu bị yêu cầu ít hơn tốc độ tick, thay vì tự động buffer mãi. Trong hệ thống thật:

- Chọn queue/buffer bounded; có chính sách overflow rõ.
- `onBackpressureLatest` có thể bỏ intermediate states phù hợp dashboard tiến độ, **không phù hợp** dữ liệu thanh toán/event không được mất.
- `onBackpressureDrop` chỉ phù hợp dữ liệu cho phép rơi, và cần metric các sự kiện bị loại.
- Với business events bắt buộc, dùng durable broker/persistence hoặc cơ chế delivery/acknowledgment phù hợp.
- Không dùng `collectList()`, `cache()` không giới hạn hay in-memory replay vô hạn trên feed nhiều người.
- Kiểm tra disconnect để cancel subscription và dọn resource, không giữ database cursor/file/socket sau khi client đã đóng.

## 15. Test stream lỗi giữa chừng: chọn kỳ vọng đúng

Đối với luồng:

```java
Flux<String> stream = Flux.concat(
        Flux.just("first", "second"),
        Flux.error(new IllegalStateException("backend failed")));

StepVerifier.create(stream)
        .expectNext("first", "second")
        .expectError(IllegalStateException.class)
        .verify(Duration.ofSeconds(2));
```

Reactor test sẽ quan sát hai items rồi lỗi. Nhưng nếu stream này được controller serialize thành SSE và server đã gửi ít nhất một event, client có thể đã nhận HTTP 200. Không thể assert “response status chuyển thành 500” sau khi đã commit header.

Có thể thiết kế event báo lỗi trong cùng SSE stream:

```java
Flux<ServerSentEvent<String>> sse = source
        .map(data -> ServerSentEvent.<String>builder(data)
                .event("data").build())
        .onErrorResume(ex -> Flux.just(
                ServerSentEvent.<String>builder("temporarily unavailable")
                        .event("error")
                        .build()));
```

Đây là **trích đoạn**, `source` cần là `Flux<String>` và có imports. Sau lỗi, server gửi một event tên `error` rồi complete với **HTTP status có thể vẫn là 200**, vì headers đã commit. API phải đặc tả schema và tính bảo mật của event lỗi; không gửi stack trace hoặc raw exception chứa thông tin nhạy cảm.

Nếu muốn status 504 cho timeout **trước khi có dữ liệu**, dùng `Mono` timeout/mapError như `/api/deadline` của dự án mẫu. Đừng đặt một test expectation không thể thỏa trên giao thức HTTP.

## 16. Các lỗi thường gặp trong kiểm thử WebFlux streaming

| Lỗi/triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Test SSE treo mãi | Đợi `onComplete` của `Flux.interval` vô hạn | `returnResult` + `StepVerifier.thenCancel()` |
| `expectBodyList` chờ rất lâu | Cố gom toàn bộ response vô hạn | Decode stream từng event với `FluxExchangeResult` |
| StepVerifier không phát event trong virtual time | Tạo publisher/scheduler bên ngoài lambda hoặc quên tiến clock | `withVirtualTime(() -> ...)`, `thenAwait` |
| `expectNoEvent` FAIL ngay khi subscribe | Subscription cũng tính là event | Đặt `expectSubscription()` trước |
| Timeout virtual test “thành công” nhưng I/O thật vẫn chậm | Virtual clock không điều khiển network/DB | Real-server/adapter test riêng |
| Test vẫn treo dù đã có business timeout | Verifier không có time limit hoặc publisher không nằm trên đường kiểm tra | Dùng `verify(Duration)`, xem operator chain |
| SSE status 200 nhưng chưa có data | Response đã commit hoặc event bị buffer | Assert từng event và thời gian, kiểm tra flush |
| `Content-Type` không đúng | Controller không khai báo SSE/NDJSON | `produces` đúng và kiểm tra `contentTypeCompatibleWith` |
| JSON decode lỗi | Mismatch schema/codec/generic type | Dùng DTO/record đúng và `ParameterizedTypeReference` khi cần |
| Nghĩ `take(2)` chứng minh upstream tự complete | `take` hủy upstream sau 2 items | Phân biệt downstream completion và upstream cancel |
| Client cancel nhưng server còn hoạt động | Cancellation/cleanup bất đồng bộ, source hot/shared | Instrument `doFinally`/metrics và test resource lifecycle |
| Muốn HTTP 504 sau khi đã gửi SSE | Status/headers đã commit | Emit SSE error event hoặc đóng kết nối theo contract |
| `Flux.timeout` không cắt stream liên tục | Timeout reset sau mỗi `onNext` | Dùng overall deadline riêng nếu yêu cầu |
| Test flake khi CI CPU cao | Deadline/assertion dùng thời gian thật quá sát | Virtual time cho logic, harness timeout đủ margin |
| `@WebFluxTest` không có service | Slice không scan `@Service` bình thường | `@MockitoBean` hoặc `@Import` có mục tiêu |
| Dùng `@WebMvcTest` để kiểm tra WebFlux | Sai web stack | Chọn `@WebFluxTest` và `WebTestClient` |
| App khởi động MVC dù mong WebFlux | Có cả starter web và webflux trên classpath | Chỉ dùng WebFlux hoặc chỉ rõ `spring.main.web-application-type=reactive` |
| Browser reconnect nhưng bỏ event | Không có server-side resume | Test `Last-Event-ID` và event store |
| Leak bộ nhớ ở slow consumer | Unbounded buffer/replay hoặc cancel không cleanup | Bounded buffering, backpressure policy và metrics |

## 17. Khi nào cần test với server thật, proxy thật và security?

### Mock-bound controller test

Dùng `@WebFluxTest` khi muốn kiểm chứng routing/codec/SSE metadata, timeout mapping với mock service, response contracts; không cần khởi động cổng server thật.

### Real HTTP integration

Dùng `@SpringBootTest(RANDOM_PORT)` khi muốn kiểm tra việc từng item thực sự tới HTTP client, server cancellation/flush, status và headers trên socket. Với DB/Redis/broker thật, thêm Testcontainers và test data ownership; không phải tất cả integration tests đều cần mạng/DB ngoài.

### Proxy/LB/staging

Một test HTTP loopback không kiểm chứng idle timeout ở nginx, Envoy, ingress hoặc CDN. Nếu SSE phải sống qua proxy 60 giây không event, cần staging test với đúng hạ tầng hoặc config test tương ứng. Heartbeat intervals nên nhỏ hơn idle cutoff với margin dựa trên vận hành, tránh chọn theo suy đoán.

### Security và dữ liệu nhạy cảm

Kết nối SSE kéo dài có thể vượt qua thay đổi quyền/trạng thái tài khoản sau khi HTTP request đã được xác thực. Cần chính sách authorization khi subscribe, hủy stream khi quyền bị thu hồi nếu cần, tenant isolation, rate limiting và kiểm thử không rò events giữa người dùng. Dùng Spring Security test support đúng WebFlux stack (`SecurityWebFilterChain`, `WebTestClient.mutateWith(mockUser())` từ `spring-security-test` khi có dependency) thay vì tắt security filters chỉ để test stream chạy.

## 18. Chiến lược test timeout an toàn trong CI

1. **Pure publisher logic:** dùng virtual time để thử các ngưỡng `T−ε, T, T+ε`, timeout/fallback và idle gap. Không ngủ thật.
2. **HTTP contract:** dùng WebTestClient với giới hạn response timeout; kiểm tra status/headers và một số events. Không cần stream complete khi API thiết kế vô hạn.
3. **Real server:** một số integration tests kiểm tra flush/cancel và lỗi trước khi commit. Dùng random port.
4. **External dependencies:** dùng stub server/containers, test timeout ở đúng lớp client; giữ network calls trong môi trường kiểm soát.
5. **Staging proxy:** kiểm tra kết nối dài/heartbeats/reconnect qua hạ tầng thật; không suy luận từ loopback.
6. **Observability:** ghi metric số kết nối SSE hiện tại, thời gian sống, disconnect/cancel, overflow và latency first-event; không log payload nhạy cảm.
7. **Không che lỗi:** tránh lặp test tự động đến khi pass; khi flake, điều tra scheduler, CI load, timeout budget, shared state và cleanup.

### Ma trận tối thiểu để nghiệm thu

| ID | Layer | Scenario | Then |
| --- | --- | --- | --- |
| ST01 | Reactor | Interval virtual 10/20/30s | Ba Tick đúng thời điểm; complete do `take(3)` |
| ST02 | Reactor | Never emits, timeout 3s | `TimeoutException` tại deadline |
| ST03 | Reactor | Slow upstream + fallback | `fallback` rồi complete |
| ST04 | Reactor | Fast upstream | `ready` trước deadline |
| ST05 | Reactor | Cancel sau một event | `SignalType.CANCEL` ở upstream |
| ST06 | Reactor | Khoảng im lặng sau event đầu | Gap timeout error |
| ST07 | WebFlux slice | SSE có 2 events, stream còn mở | HTTP 200, metadata đúng, client cancel |
| ST08 | WebFlux slice | NDJSON 3 items | Đúng ba JSON objects, complete |
| ST09 | WebFlux slice | Mono.never + deadline | HTTP 504 |
| ST10 | WebFlux slice | Mono.never + fallback | HTTP 200, body fallback |
| ST11 | WebFlux slice | Mono.just fast | HTTP 200, body ready |
| ST12 | Real HTTP | SSE qua socket | Nhận 2 items rồi cancel |
| ST13 | Real HTTP | NDJSON qua socket | 3 items rồi complete |
| ST14 | Real HTTP | Deadline qua socket | 504 |

## 19. Bài tập mở rộng

1. **SSE heartbeat:** thêm `ServerSentEvent.builder().comment("heartbeat")` và test rằng business-event consumer không đếm heartbeat là Tick.
2. **Last-Event-ID:** lưu 20 events trong in-memory bounded store, hỗ trợ replay từ ID client cung cấp và test reconnect với cursor cũ/mới.
3. **First-item timeout khác inter-item timeout:** dùng overload `Flux.timeout(firstTimeout, nextTimeout)` hoặc publisher timeout tương ứng để mô phỏng deadline khác nhau.
4. **Rate-limited consumers:** tạo downstream chỉ `request(1)` mỗi lần, kiểm tra policy overflow/loss đúng business contract.
5. **Server disconnect cleanup:** gắn `doFinally`/metrics vào flux trên server, đóng client và dùng polling có hạn mức để kiểm chứng resource được giải phóng.
6. **Remote streaming:** dùng WireMock/MockWebServer làm upstream để test network timeout, retry và cancellation qua WebClient.
7. **Event error sau commit:** phát hai SSE events rồi upstream error, kiểm tra client xử lý closure/error event đúng, không kỳ vọng HTTP status tự đổi.
8. **Backpressure policy:** so sánh `onBackpressureBuffer(max)`, `onBackpressureDrop` và `onBackpressureLatest` với yêu cầu lossless vs lossy của sản phẩm.
9. **SSE security:** test unauthenticated/unauthorized/tenant isolation với `spring-security-test` cho reactive stack.
10. **Staging proxy:** đo idle cutoff qua gateway và chứng minh heartbeats đủ giữ kết nối trong giới hạn yêu cầu.

Khi bổ sung các bài tập này, chọn mock/slice/real server theo tầng cần chứng minh; không dồn tất cả vào một `@SpringBootTest` khổng lồ.

## 20. Checklist trước khi kết luận test streaming đạt

- [ ] Đã xác định endpoint là hữu hạn hay vô hạn?
- [ ] `Content-Type` SSE/NDJSON đúng với hợp đồng?
- [ ] Status và headers được kiểm tra **trước** khi consume stream?
- [ ] Luồng vô hạn có `thenCancel` và `verify(Duration)`?
- [ ] Luồng hữu hạn có assert số phần tử, order và `onComplete`?
- [ ] SSE `id`, `event`, `data` và `retry` được test nếu client dựa vào chúng?
- [ ] Không dùng `collectList`/`expectBodyList` vô hạn?
- [ ] Test virtual time tạo publisher bên trong `withVirtualTime` lambda?
- [ ] Có `expectSubscription` trước `expectNoEvent`?
- [ ] Timeout nghiệp vụ phân biệt với client response timeout và verifier timeout?
- [ ] Với `Flux.timeout`, hiểu deadline reset sau mỗi tín hiệu?
- [ ] HTTP 504 chỉ được kỳ vọng trước khi response đã commit?
- [ ] Có test fallback/success/error và upstream cancellation cleanup?
- [ ] Đã kiểm tra slow consumer/backpressure policy phù hợp nghiệp vụ?
- [ ] Test server thật có random port, giới hạn thời gian và không leak resources?
- [ ] Nếu cần replay, server thực sự hỗ trợ `Last-Event-ID`?
- [ ] Test không yêu cầu exactly-once khi giao thức/hệ thống không bảo đảm?
- [ ] CI báo số test chạy thực sự và không có test bị treo/skipped ngoài ý định?
- [ ] Version Spring Boot, Reactor, JUnit và test annotations thống nhất?

## 21. Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): `FluxExchangeResult`, `returnResult` và test streaming responses.
2. [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): `Flux<ServerSentEvent>` và streaming return values.
3. [Spring Framework — Reactive HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Reactor/WebFlux runtime model và non-blocking semantics.
4. [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): signals, virtual time, `expectNoEvent`, `thenCancel`, `verify(Duration)`.
5. [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): API và timing guarantees.
6. [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `interval`, `take`, `timeout` và backpressure.
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockitoBean`, `@SpringBootTest`.
8. [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): cập nhật focused test modules khi dùng Spring Boot 4.
9. [WHATWG — Server-Sent Events Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html): event stream syntax, `EventSource`, reconnect và `Last-Event-ID`.

### Ghi chú Spring Boot 4

Các snippet runnable ở phần 8–11 nhắm **Boot 3.5.0**. Spring Boot 4 tổ chức test support theo công nghệ, có `spring-boot-starter-webflux-test`; package của `@WebFluxTest` thay đổi so với `org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest` của Boot 3.5. Khi nâng cấp, đối chiếu documentation và dependency tree thay vì đổi mỗi version number trong POM.

**Kết luận:** với streaming, bài test đáng tin không chỉ nói “HTTP 200” mà còn xác nhận **dữ liệu từng phần, metadata SSE, thời điểm phát, completion/error/cancel và giới hạn thời gian ở đúng tầng**. Virtual time chứng minh logic thời gian nhanh và xác định; WebTestClient xác nhận contract WebFlux; real-server test xác nhận HTTP streaming trên socket. Kết hợp cả ba sẽ tránh test vô hạn, flaky hoặc báo xanh nhưng không kiểm chứng được hành vi.
