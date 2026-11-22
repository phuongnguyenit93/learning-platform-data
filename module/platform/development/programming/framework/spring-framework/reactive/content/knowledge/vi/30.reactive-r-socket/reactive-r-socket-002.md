# RSocket: Fire-and-forget, Request-response, Request-stream và Request-channel

**Module:** Spring Framework – reactive  
**Chủ đề cha:** RSocket  
**Đề bài:** Fire-and-forget, request-response, request-stream và request-channel

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích RSocket là giao thức ứng dụng bất đồng bộ, song công (duplex), multiplex nhiều request trên một connection TCP/WebSocket và có Reactive Streams semantics.
2. Phân biệt chính xác bốn mô hình tương tác dựa trên **số thông điệp đầu vào** và **số thông điệp đầu ra**, không nhầm với bốn HTTP method.
3. Đánh giá ý nghĩa của fire-and-forget: hoàn tất gửi không đồng nghĩa được xử lý thành công.
4. Viết request-response với `Mono<T>`, request-stream với `Flux<T>` và request-channel với hai luồng có thể hoạt động đồng thời.
5. Hiểu `REQUEST_N`, backpressure, `CANCEL`, `COMPLETE` và `ERROR`; biết khi nào phải dừng upstream và giải phóng tài nguyên.
6. Ánh xạ `@MessageMapping` phía responder và `RSocketRequester` phía requester trong Spring Boot 3.
7. Chạy ví dụ Java 17+ gồm đủ bốn mô hình trên TCP và kiểm tra handler bằng Reactor Test.
8. Chọn mô hình phù hợp với nhu cầu nghiệp vụ, độ tin cậy, xử lý lỗi, giới hạn tải và bảo mật.

## 1. Nền tảng: RSocket truyền thông điệp thay vì HTTP response truyền thống

RSocket là **application protocol** chạy trên các byte-stream transport như TCP hoặc WebSocket. Sau khi thiết lập kết nối, mỗi bên có thể khởi xướng request tới bên kia; vì vậy thuật ngữ chính xác là **requester** (bên mở một tương tác) và **responder** (bên phục vụ tương tác), không nhất thiết là client HTTP và server HTTP cố định.

Một connection RSocket có thể chứa nhiều tương tác độc lập, phân biệt bằng stream ID. Các frame từ nhiều stream được multiplex trên cùng kết nối vật lý. RSocket có data payload, metadata (ví dụ route), framing, flow control và các tín hiệu lifecycle; nó **không phải giao thức HTTP**. Khi chạy trên WebSocket, WebSocket chỉ là transport, còn request-response/request-stream vẫn là mô hình của RSocket.

```text
                 Một kết nối RSocket (TCP hoặc WebSocket)
Requester                                                        Responder
   |                                                                 |
   |--- REQUEST_RESPONSE (stream 1) -------------------------------->|
   |--- REQUEST_STREAM   (stream 3, demand=N) ---------------------->|
   |<-- PAYLOAD           (stream 3) ---------------------------------|
   |<-- PAYLOAD           (stream 1, response+complete) -------------|
   |--- REQUEST_FNF      (stream 5) -------------------------------->|
   |--- REQUEST_CHANNEL  (stream 7, dữ liệu chiều đi) --------------->|
   |<-- PAYLOAD           (stream 7, dữ liệu chiều về) --------------|
   |                                                                 |
```

RSocket sử dụng Reactive Streams để truyền demand giữa requester và responder. Khi responder có `Flux` lớn, requester có thể yêu cầu n phần tử thay vì buộc server đẩy vô hạn; việc này đặc biệt quan trọng với stream dài hạn.

### 1.1. SETUP, route và payload

Một client thực hiện TCP/WebSocket connection rồi trao đổi `SETUP` để thỏa thuận thông tin kết nối như MIME type của data và metadata. Mỗi tương tác thường có route (ví dụ `orders.lookup`) trong metadata đầu tiên và data payload (ví dụ một ID hoặc JSON object).

Trong Spring:

- `@MessageMapping("orders.lookup")` khai báo route phía responder.
- `requester.route("orders.lookup")` đặt route vào request metadata.
- `data(...)` cung cấp data payload.
- `RSocketStrategies` quản lý codec và giải mã các payload thành kiểu Java.
- `RSocketRequester.Builder` giúp tạo requester và kết nối TCP/WebSocket.

Route **không phải URL HTTP** và `@MessageMapping` không phải `@GetMapping`. Giao thức có thể dùng những tên route dạng phân cấp bằng dấu chấm.

## 2. Bảng so sánh bốn mô hình

| Mô hình | Đầu vào requester → responder | Đầu ra responder → requester | API requester trong Spring | API responder thường gặp | Ví dụ thực tế |
| --- | --- | --- | --- | --- | --- |
| **Fire-and-forget (FNF)** | 1 thông điệp | Không có response payload | `route(...).data(x).send(): Mono<Void>` | `@MessageMapping` trả `void` hoặc `Mono<Void>` | Telemetry không quan trọng, sự kiện chấp nhận mất. |
| **Request-response (RR)** | 1 thông điệp | Tối đa 1 kết quả / lỗi | `retrieveMono(T.class)` | Nhận object, trả `Mono<T>` | Tra cứu tài khoản, kiểm tra trạng thái. |
| **Request-stream (RS)** | 1 thông điệp | 0..N kết quả theo thời gian | `retrieveFlux(T.class)` | Nhận object, trả `Flux<T>` | Báo giá liên tục, dữ liệu đọc theo lô, cập nhật vị trí. |
| **Request-channel (RC)** | Một luồng 1..N thông điệp | Một luồng 0..M thông điệp độc lập | `data(Flux<X>, X.class).retrieveFlux(Y.class)` | Nhận `Flux<X>`, trả `Flux<Y>` | Chat, tương tác điều khiển/giám sát, telemetry hai chiều. |

**Điểm mấu chốt:** Request-channel không nhất thiết 1 request ↔ 1 response. Cả hai phía có stream riêng và có thể phát nhiều tín hiệu độc lập về thời điểm. Ngược lại, request-stream chỉ có **một** request payload ban đầu, sau đó nhận nhiều response.

Một số `@MessageMapping` có cùng signature `void` hoặc `Mono<Void>` có thể phục vụ tương tác không trả payload, nhưng **kiểu request do requester khởi xướng** quyết định frame tương tác thực tế. Không suy ra hoàn toàn mô hình chỉ từ tên method.

## 3. Fire-and-forget: gửi một chiều, không nhận kết quả nghiệp vụ

### 3.1. Trình tự

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_FNF(data, route) -------------->|
    |                                            | (có thể xử lý)
    |                                            |
    |  Không có PAYLOAD phản hồi cho request này |
```

Requester không chờ một response payload. Ở Spring, `send()` trả `Mono<Void>`; Mono hoàn tất thể hiện việc gửi đã thành công ở góc nhìn transport/client, **không phải xác nhận responder đã xử lý, ghi database hay commit giao dịch**.

Ví dụ gửi telemetry không quan trọng:

```java
Mono<Void> sent = requester.route("metrics.sample")
        .data(new MetricSample("cpu", 62))
        .send();

sent.subscribe(); // Bắt đầu gửi; không phải chứng nhận xử lý thành công.
```

`MetricSample` là DTO giả định trong đoạn minh họa này. Ở ứng dụng production, nên kiểm soát error và lifecycle của subscription thay vì gọi `subscribe()` tùy tiện, không theo dõi.

Responder có thể là:

```java
@Controller
class MetricResponder {
    @MessageMapping("metrics.sample")
    public void consume(MetricSample metric) {
        // Ví dụ: ghi vào buffer có giới hạn.
    }
}
```

### 3.2. Những gì FNF không bảo đảm

FNF là best-effort. Server có thể chưa xử lý message dù requester đã hoàn tất `send()`; kết nối có thể lỗi, SETUP bị từ chối, handler có thể từ chối payload hoặc ứng dụng có thể sập trước khi commit.

Do không có response cùng tương tác:

- Requester không nhận ID tài nguyên hoặc trạng thái xử lý nghiệp vụ.
- Exception xảy ra trong business handler phía responder có thể không thể phản hồi ngược như một response cho FNF.
- Không dùng FNF làm bằng chứng đã trừ tiền, đã ghi đơn hoặc đã gửi email.

Nếu cần xác nhận, dùng request-response với kết quả `accepted/processed` được định nghĩa rõ. Nếu cần delivery bền vững và retry, cân nhắc hàng đợi/broker, outbox hoặc cơ chế idempotency thay vì giả định RSocket tự lưu message xuống đĩa.

### 3.3. Khi nào dùng

Dùng cho log mẫu, cập nhật thống kê không quan trọng, tín hiệu mà ứng dụng có thể bỏ qua khi lỗi, hoặc sự kiện đã được lưu bền vững ở nơi khác trước khi phát đi. Không dùng cho nghiệp vụ đòi hỏi exactly-once.

## 4. Request-response: một request, tối đa một kết quả

### 4.1. Trình tự

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_RESPONSE(query) --------------->|
    |                                            | tra cứu
    |<-- PAYLOAD(result) + COMPLETE -------------|
    |                  hoặc ERROR                |
```

Trong Spring, `retrieveMono(T.class)` tương ứng phản hồi đơn. `Mono<T>` biểu diễn 0 hoặc 1 dữ liệu, sau đó complete hoặc error. Response có thể rỗng tùy contract; không nên coi `Mono.empty()` tương đương với “không tìm thấy” nếu nghiệp vụ chưa định nghĩa.

Ví dụ:

```java
Mono<UserView> result = requester.route("users.byId")
        .data(new UserQuery("u-42"))
        .retrieveMono(UserView.class)
        .timeout(Duration.ofSeconds(3));
```

Các DTO ở đây chỉ minh họa cấu trúc. Một responder điển hình:

```java
@MessageMapping("users.byId")
public Mono<UserView> findUser(UserQuery query) {
    return userService.findById(query.id());
}
```

### 4.2. Xử lý lỗi và deadline

- `onErrorResume` có thể fallback khi remote trả error hoặc kết nối lỗi; chỉ fallback những loại lỗi đã biết.
- `timeout` đặt giới hạn chờ ở caller. Nó có thể hủy subscription, nhưng **không chứng minh side effect phía responder đã rollback**.
- Retry an toàn hơn đối với truy vấn thuần đọc. Với lệnh tạo/sửa dữ liệu, cần idempotency key, ràng buộc unique hoặc giải pháp chống trùng.
- Nếu server trả `Mono.empty()`, caller cần quy ước rõ: empty hợp lệ, không tìm thấy, hay lỗi nghiệp vụ? Có thể dùng response DTO chứa trạng thái hoặc `switchIfEmpty(Mono.error(...))`.

Request-response phù hợp cho RPC gọn, xác nhận một thao tác, lấy cấu hình, kiểm tra tài khoản hoặc tính toán có một kết quả.

## 5. Request-stream: một request, nhiều kết quả

### 5.1. Trình tự và demand

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_STREAM(input, initial N=2) ---->|
    |<-- PAYLOAD(item 1) ------------------------|
    |<-- PAYLOAD(item 2) ------------------------|
    |--- REQUEST_N(3) --------------------------->|
    |<-- PAYLOAD(item 3) ------------------------|
    |<-- PAYLOAD(item 4) ------------------------|
    |<-- PAYLOAD(item 5) ------------------------|
    |<-- COMPLETE -------------------------------|
```

Các số N trên là sơ đồ khái niệm; thư viện có thể prefetch/batch demand khác. RSocket hỗ trợ `REQUEST_N` để thể hiện số lượng phần tử downstream có thể nhận, thay vì server gửi vô hạn không quan tâm khả năng tiêu thụ. `CANCEL` có thể dừng stream trước khi hoàn tất.

Ví dụ:

```java
Flux<PriceQuote> quotes = requester.route("prices.watch")
        .data(new PriceFilter("BTC"))
        .retrieveFlux(PriceQuote.class);

// Caller có thể dừng khi đã đủ dữ liệu.
Mono<List<PriceQuote>> firstFive = quotes.take(5).collectList();
```

Responder:

```java
@MessageMapping("prices.watch")
public Flux<PriceQuote> watch(PriceFilter filter) {
    return quoteService.watch(filter.symbol());
}
```

### 5.2. Completion, cancellation và nguồn nóng

Request-stream có thể hữu hạn hoặc dài hạn. Với stream hữu hạn, responder phát `COMPLETE` khi xong. Với stream live không có điểm dừng, caller phải tự quản lý subscription và cancellation.

`take(5)` chỉ lấy năm phần tử rồi hủy upstream; hủy là tín hiệu best-effort, không bảo đảm một tác vụ blocking hoặc một request DB bên dưới dừng tức thì. Responder nên dùng nguồn reactive hỗ trợ cancel và giải phóng tài nguyên bằng `doFinally` hoặc `usingWhen` khi phù hợp.

Backpressure chỉ hiệu quả nếu upstream tuân thủ demand. Một hot source không có khả năng giảm tốc có thể cần chính sách buffer giới hạn, drop, latest hoặc báo lỗi; không cấu hình `onBackpressureBuffer()` vô hạn mà không tính giới hạn bộ nhớ.

### 5.3. Lựa chọn dùng

Dùng khi một request tạo tập kết quả lớn, dữ liệu được tính dần, cập nhật theo thời gian hoặc kết quả không cần gom toàn bộ trước khi gửi. So với request-response trả `List<T>`, request-stream có thể giảm độ trễ đến phần tử đầu tiên và giảm memory khi consumer xử lý từng phần tử.

## 6. Request-channel: streaming hai chiều

### 6.1. Trình tự

```text
Requester                                    Responder
    |                                            |
    |--- REQUEST_CHANNEL(msg 1, N out) --------->|
    |<-- REQUEST_N(N in) ------------------------|
    |--- PAYLOAD(msg 2) ------------------------>|
    |<-- PAYLOAD(reply A) -----------------------|
    |<-- PAYLOAD(reply B) -----------------------|
    |--- PAYLOAD(msg 3) ------------------------>|
    |--- COMPLETE (chiều đi) ------------------->|
    |<-- PAYLOAD(reply C) -----------------------|
    |<-- COMPLETE (chiều về) --------------------|
```

Hai phía có luồng dữ liệu riêng và demand riêng; có thể gửi/nhận xen kẽ. Một phía hoàn tất **chiều gửi** không nhất thiết làm chiều nhận kết thúc ngay. Khi cả hai chiều đã complete, hoặc khi error/cancel kết thúc tương tác, channel được giải phóng.

Request-channel cho phép:

- Requester gửi liên tiếp N thông điệp, responder gửi về M thông điệp.
- Responder có thể xử lý tuần tự, song song có kiểm soát hoặc phát response theo sự kiện ngoài.
- Hai chiều có thể có tốc độ khác nhau; backpressure cần xem xét trên từng chiều.
- Một channel có thể dài hạn, nên cần heartbeat, cancellation và quy trình shutdown.

Ví dụ:

```java
Flux<ChatMessage> outgoing = Flux.just(
        new ChatMessage("an", "xin chao"),
        new ChatMessage("binh", "webflux"));

Flux<ChatReply> incoming = requester.route("chat.room")
        .data(outgoing, ChatMessage.class)
        .retrieveFlux(ChatReply.class);
```

Responder:

```java
@MessageMapping("chat.room")
public Flux<ChatReply> talk(Flux<ChatMessage> messages) {
    return messages.map(m ->
            new ChatReply(m.sender(), "echo:" + m.text()));
}
```

Đây là **ví dụ 1–1 để dễ quan sát**, không phải giới hạn của RSocket. Responder thực tế có thể dùng `flatMap`, `merge` hoặc một nguồn phát độc lập để trả số response khác số request; khi đó cần rõ ràng chính sách ordering, concurrency và buffer.

### 6.2. Không biến channel thành request-stream

Nếu chỉ cần gửi **một** điều kiện lọc rồi nhận các kết quả cập nhật, dùng request-stream. Chỉ dùng request-channel nếu **đầu vào cũng là dòng nhiều message** hoặc ứng dụng cần tương tác duplex có trạng thái như chat/điều khiển tiến trình.

Một stream không mang dữ liệu sau khi kết nối không phải lý do tự động chọn channel; chọn theo contract về luồng hai chiều, không chỉ vì server có thể push.

## 7. Spring @MessageMapping quyết định mô hình thế nào?

Spring Messaging nhận route từ metadata và tìm `@MessageMapping` tương ứng. Sau khi route được khớp, kiểu payload đầu vào và kiểu trả về giúp framework xác định các tương tác được handler hỗ trợ.

| Input của handler | Output của handler | Mô hình có thể phục vụ |
| --- | --- | --- |
| Object hoặc `Mono<T>` | `void`, `Mono<Void>` | FNF hoặc RR không có payload, tùy loại frame requester gửi |
| Object hoặc `Mono<T>` | Object hoặc `Mono<R>` | RR |
| Object hoặc `Mono<T>` | `Flux<R>` | Request-stream |
| `Flux<T>` | `Flux<R>`, `Mono<R>` hoặc no-value | Request-channel |

Trong bài tập này, dùng `void` cho FNF, `Mono<R>` cho RR, `Flux<R>` với một input cho RS và `Flux<T>` đầu vào cộng `Flux<R>` đầu ra cho RC. Bốn route khác nhau giúp code tường minh.

`RSocketRequester` xác định cách khởi tạo tương tác:

- `send()` → Fire-and-forget.
- `retrieveMono(...)` → Request-response, khi đầu vào là single value.
- `retrieveFlux(...)` cùng một input → Request-stream.
- `data(Flux<X>, X.class).retrieveFlux(Y.class)` → Request-channel.

Một request có input Publisher phát nhiều phần tử **không** thể trở thành mô hình “many-to-one” HTTP RPC thông thường; với RSocket, đầu vào nhiều phần tử dùng request-channel, kể cả khi handler chỉ trả một kết quả.

## 8. Hoàn chỉnh ví dụ Java 17+ chạy qua TCP

Ví dụ dùng **Spring Boot 3.3.5**, Java 17, Maven và RSocket TCP. Server và requester cùng trong một ứng dụng để chạy dễ dàng: Spring Boot mở cổng RSocket 7000, sau đó `ApplicationRunner` phát đủ bốn loại request tới `localhost:7000`. Đây là demo tự gọi chính mình, không phải mô hình triển khai bắt buộc.

### 8.1. Cấu trúc project

```text
rsocket-four-models/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── RSocketModesApplication.java
    │   │   ├── Messages.java
    │   │   ├── ModesController.java
    │   │   └── DemoRunner.java
    │   └── resources/application.properties
    └── test/java/demo/ModesControllerTest.java
```

### 8.2. pom.xml

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
    <artifactId>rsocket-four-models</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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
```

`spring-boot-starter-rsocket` cung cấp hạ tầng RSocket; `spring-boot-starter-json` bảo đảm Jackson codec cho DTO JSON; `reactor-test` cung cấp `StepVerifier`.

### 8.3. application.properties

```properties
spring.application.name=rsocket-four-models
spring.main.web-application-type=none
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

Ứng dụng này **không mở HTTP endpoint**. Thuộc tính `spring.rsocket.server.port` mở RSocket TCP listener. Nếu cổng 7000 đang dùng, chọn cổng khác đồng thời cập nhật host/port trong `DemoRunner`.

### 8.4. RSocketModesApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(RSocketModesApplication.class, args);
    }
}
```

Spring Boot tự cấu hình `RSocketMessageHandler`, `RSocketStrategies` và `RSocketRequester.Builder` khi có dependency thích hợp.

### 8.5. Messages.java — các DTO dùng chung

```java
package demo;

public final class Messages {
    private Messages() {
    }

    public record Notice(String text) {
    }

    public record NumberInput(int value) {
    }

    public record SquareReply(int result) {
    }

    public record StreamInput(int count) {
    }

    public record Tick(int sequence, String label) {
    }

    public record ChatMessage(String from, String text) {
    }

    public record ChatReply(String from, String text) {
    }
}
```

Các record Java 17 là kiểu dữ liệu nhỏ, bất biến. Client và server dùng cùng schema để demo JSON; hệ thống thật có thể chia schema/module hoặc áp dụng API/schema versioning khi hai phía triển khai độc lập.

### 8.6. ModesController.java — responder đủ bốn mô hình

```java
package demo;

import java.time.Duration;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class ModesController {

    private final Queue<Messages.Notice> notices =
            new ConcurrentLinkedQueue<>();

    // Fire-and-forget: một input và không có response payload.
    @MessageMapping("demo.fnf")
    public void onNotice(Messages.Notice notice) {
        notices.add(notice); // Demo: non-blocking in-memory operation.
    }

    // Chỉ phục vụ kiểm thử, không phải route RSocket.
    public int receivedNoticeCount() {
        return notices.size();
    }

    // Request-response: một input, tối đa một output.
    @MessageMapping("demo.rr")
    public Mono<Messages.SquareReply> square(
            Messages.NumberInput input) {
        return Mono.fromSupplier(() ->
                new Messages.SquareReply(
                        Math.multiplyExact(
                                input.value(), input.value())));
    }

    // Request-stream: một input, nhiều output có demand.
    @MessageMapping("demo.stream")
    public Flux<Messages.Tick> ticks(Messages.StreamInput input) {
        if (input.count() < 1 || input.count() > 100) {
            return Flux.error(new IllegalArgumentException(
                    "count must be from 1 to 100"));
        }

        return Flux.range(1, input.count())
                .delayElements(Duration.ofMillis(30))
                .map(i -> new Messages.Tick(i, "tick-" + i));
    }

    // Request-channel: input Flux và output Flux.
    @MessageMapping("demo.channel")
    public Flux<Messages.ChatReply> chat(
            Flux<Messages.ChatMessage> incoming) {
        return incoming.map(message ->
                new Messages.ChatReply(
                        message.from(),
                        "echo:" + message.text()));
    }
}
```

Giải thích:

- `demo.fnf`: handler trả `void`, client không đợi business response. Queue demo có thể bỏ khi triển khai thật.
- `demo.rr`: `Mono.fromSupplier` thực hiện tính toán khi có subscription; `multiplyExact` đưa lỗi overflow thành error thay vì âm thầm tràn số.
- `demo.stream`: `Flux.range` là nguồn hữu hạn, `delayElements` làm rõ việc phần tử được phát theo thời gian. Kiểm soát `count` để tránh một request sinh quá nhiều phần tử.
- `demo.channel`: biến đổi từng input thành output. Đây là ví dụ echo 1–1, không giới hạn channel thật ở ánh xạ 1–1.

### 8.7. DemoRunner.java — requester đủ bốn mô hình

```java
package demo;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

@Component
public class DemoRunner implements ApplicationRunner {

    private final RSocketRequester.Builder builder;

    public DemoRunner(RSocketRequester.Builder builder) {
        this.builder = builder;
    }

    @Override
    public void run(ApplicationArguments args) {
        RSocketRequester requester = builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .tcp("localhost", 7000);

        // 1. Fire-and-forget.
        requester.route("demo.fnf")
                .data(new Messages.Notice("hello"))
                .send()
                .block(Duration.ofSeconds(5));

        System.out.println(
                "FNF: sent (not a business acknowledgment)");

        // 2. Request-response.
        Messages.SquareReply squared = requester.route("demo.rr")
                .data(new Messages.NumberInput(7))
                .retrieveMono(Messages.SquareReply.class)
                .block(Duration.ofSeconds(5));

        System.out.println("RR: " + squared);

        // 3. Request-stream. take(3) hủy upstream khi đủ dữ liệu.
        List<Messages.Tick> ticks = requester.route("demo.stream")
                .data(new Messages.StreamInput(5))
                .retrieveFlux(Messages.Tick.class)
                .take(3)
                .collectList()
                .block(Duration.ofSeconds(5));

        System.out.println("STREAM (first 3): " + ticks);

        // 4. Request-channel. Outbound cũng là Flux.
        Flux<Messages.ChatMessage> outgoing = Flux.just(
                new Messages.ChatMessage("an", "hello"),
                new Messages.ChatMessage("binh", "reactive"));

        List<Messages.ChatReply> replies =
                requester.route("demo.channel")
                        .data(outgoing, Messages.ChatMessage.class)
                        .retrieveFlux(Messages.ChatReply.class)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        System.out.println("CHANNEL: " + replies);
    }
}
```

Lưu ý:

1. `Builder.tcp(host,port)` trong Spring Framework 6.1 tạo requester có shared/lazy connection; connection được thiết lập khi thực sự có yêu cầu. Đừng nhầm với API `connectTcp` cũ trả về Mono và đã bị deprecated.
2. `block(Duration)` được dùng **chỉ trong ApplicationRunner của demo dòng lệnh**, không được gọi trong reactive handler hoặc event-loop thread của ứng dụng WebFlux.
3. `send()` hoàn tất không chứng minh handler FNF đã lưu Notice. Không dùng log FNF này như tín hiệu commit.
4. Các lời gọi RR, RS và RC có timeout phía client để tránh treo demo khi server không chạy.
5. `take(3)` chủ động hủy stream sau ba kết quả; không có nghĩa server chắc chắn chưa tính thêm phần tử do prefetch hoặc tác vụ song song.
6. Hai phần tử trong channel được gửi theo cùng một connection; số output ở đây bằng hai do code responder echo, không phải yêu cầu của protocol.

### 8.8. Kết quả dự kiến

Chạy:

```bash
mvn spring-boot:run
```

Bỏ qua các dòng log khởi động Spring/Netty; **bốn dòng nghiệp vụ** do `DemoRunner` in ra theo thứ tự:

```text
FNF: sent (not a business acknowledgment)
RR: SquareReply[result=49]
STREAM (first 3): [Tick[sequence=1, label=tick-1], Tick[sequence=2, label=tick-2], Tick[sequence=3, label=tick-3]]
CHANNEL: [ChatReply[from=an, text=echo:hello], ChatReply[from=binh, text=echo:reactive]]
```

Đây là các giá trị Java record với `toString()` mặc định. Log của Spring Boot và Reactor Netty có thể xen kẽ theo môi trường; thứ tự các dòng mà Runner chủ động in được bảo toàn vì các `block()` được thực hiện tuần tự.

Ứng dụng có RSocket server đang lắng nghe TCP cổng 7000, vì vậy tiến trình vẫn phục vụ request cho tới khi người dùng dừng bằng Ctrl+C. Trong production, tạo client/server thành các process riêng, chia sẻ schema và không dùng runner gọi chính mình.

### 8.9. ModesControllerTest.java — unit tests cho handler

```java
package demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ModesControllerTest {

    private final ModesController controller = new ModesController();

    @Test
    void fireAndForgetHasNoResponsePayload() {
        controller.onNotice(new Messages.Notice("ping"));
        assertThat(controller.receivedNoticeCount()).isEqualTo(1);
    }

    @Test
    void requestResponseReturnsOneValue() {
        StepVerifier.create(
                controller.square(new Messages.NumberInput(7)))
                .expectNext(new Messages.SquareReply(49))
                .verifyComplete();
    }

    @Test
    void requestStreamReturnsMultipleValuesAndCanBeCancelled() {
        StepVerifier.create(
                controller.ticks(new Messages.StreamInput(5)).take(3))
                .expectNext(
                        new Messages.Tick(1, "tick-1"),
                        new Messages.Tick(2, "tick-2"),
                        new Messages.Tick(3, "tick-3"))
                .verifyComplete();
    }

    @Test
    void requestChannelReceivesAndEmitsStreams() {
        Flux<Messages.ChatMessage> incoming = Flux.just(
                new Messages.ChatMessage("an", "hello"),
                new Messages.ChatMessage("binh", "reactive"));

        StepVerifier.create(controller.chat(incoming))
                .expectNext(
                        new Messages.ChatReply("an", "echo:hello"),
                        new Messages.ChatReply("binh", "echo:reactive"))
                .verifyComplete();
    }
}
```

Chạy:

```bash
mvn test
```

Bốn bài test kiểm tra logic handler và tín hiệu Mono/Flux, **không** khởi động TCP listener hoặc kiểm tra serialization/routing trên dây. Phần chạy `mvn spring-boot:run` phía trên mới là smoke test end-to-end thực tế qua RSocket TCP. Nếu yêu cầu chất lượng cao hơn, bổ sung integration tests với cổng ngẫu nhiên, client kết nối thật, kiểm tra các trường hợp lỗi, timeout, disconnect và backpressure; không coi unit test là bằng chứng đầy đủ về transport.

## 9. Demand, backpressure và CANCEL hoạt động ra sao?

### 9.1. Backpressure nằm ở ranh giới mạng

Với request-stream và request-channel, requester và responder trao đổi demand bằng `REQUEST_N`. Điều này cho phép một subscriber chậm yêu cầu ít dữ liệu hơn. Nhu cầu có thể được khởi tạo trong frame ban đầu rồi bổ sung bằng `REQUEST_N`.

Trong Reactor:

```java
Flux<Messages.Tick> stream = requester.route("demo.stream")
        .data(new Messages.StreamInput(100))
        .retrieveFlux(Messages.Tick.class);

stream.take(10)
        .doFinally(signal -> System.out.println("end=" + signal))
        .subscribe(System.out::println);
```

`take(10)` hủy sau khi lấy đủ 10 phần tử. `doFinally` giúp ghi nhận completion, error hoặc cancel. Phần in ra có thể được xen kẽ với log scheduler nên chỉ dùng để hiểu lifecycle, không xem là stdout cố định.

### 9.2. Không đánh đồng backpressure với queue vô hạn

Backpressure là **tín hiệu yêu cầu tốc độ tiêu thụ**, không phải tự động lưu toàn bộ dữ liệu từ nguồn bên ngoài. Nếu producer là nguồn nóng không thể giảm tốc, cần chiến lược rõ ràng:

- Giới hạn số lượng buffer.
- Giảm tốc hoặc tạm dừng nguồn có hỗ trợ demand.
- Drop/latest đối với dữ liệu có thể mất.
- Báo lỗi khi vượt hạn.
- Ghi dữ liệu quan trọng vào hệ thống lưu trữ bền vững.

Dùng `onBackpressureBuffer()` không giới hạn trên luồng có thể phát vô hạn có nguy cơ hết bộ nhớ.

### 9.3. Hủy và giải phóng tài nguyên

Khi client cancel, responder nên giải phóng subscription, stream dữ liệu, connection DB, file hoặc tài nguyên bên ngoài nếu có thể. Với resource reactive, `usingWhen` hoặc `doFinally` giúp quản lý vòng đời; nếu đã gọi thư viện blocking không hỗ trợ cancel, tín hiệu cancel không thể tự động dừng tác vụ đó.

Không coi cancel là rollback giao dịch. Một lệnh ghi database có thể đã commit dù client timeout hoặc hủy.

## 10. Error và kết thúc stream

| Tình huống | FNF | RR | RS | RC |
| --- | --- | --- | --- | --- |
| Gửi request thành công | `send()` hoàn tất, không có ack xử lý | Chờ một response hoặc error | Bắt đầu nhận dữ liệu theo demand | Hai chiều có thể gửi/nhận |
| Responder báo lỗi nghiệp vụ | Không có response request chuyên dụng để xác nhận | `Mono.error` tới caller | `Flux.error` kết thúc stream | Error có thể kết thúc toàn channel |
| Requester hủy | Không có response stream cần cancel | Có thể cancel khi chờ response | `CANCEL` dừng stream | `CANCEL` chấm dứt interaction |
| Responder complete bình thường | Không có response payload | Kết quả hoặc hoàn tất rỗng | `COMPLETE` sau phần tử cuối | Mỗi chiều có thể complete độc lập |

Không dùng `retry()` vô hạn: việc kết nối lại và gửi lại request có thể tạo side effect trùng. Sử dụng `retryWhen` có backoff, giới hạn số lần và chỉ áp dụng theo idempotency contract.

Lỗi codec/route không khớp có thể biểu hiện dưới dạng RSocket error; kiểm tra MIME type, tên route, serializer của DTO, khả năng xử lý null/empty và sự tương thích schema trước khi nghi ngờ network.

## 11. Chọn mô hình theo tình huống

### Tình huống A: Thu thập nhiệt độ mỗi giây, chấp nhận mất mẫu

**FNF** phù hợp nếu gửi từng sample độc lập và mất một vài sample không ảnh hưởng nghiệp vụ. Nếu server phải xác nhận đã ghi từng mẫu, dùng RR hoặc một cơ chế ingest có delivery guarantee.

### Tình huống B: Người dùng yêu cầu tính điểm tín dụng

**RR** phù hợp vì người dùng cần một quyết định hoặc trạng thái cụ thể. Nếu quá trình kéo dài, cân nhắc trả ID công việc qua RR rồi theo dõi trạng thái bằng RS hoặc một mô hình khác.

### Tình huống C: Theo dõi 500 sự kiện gần đây hoặc giá theo thời gian thực

**RS** phù hợp: một điều kiện lọc, nhiều sự kiện. Dùng demand và cancellation để client không tải thừa. Phân biệt finite stream (500 bản ghi) với live stream (chạy cho đến khi hủy).

### Tình huống D: Chat hai chiều hoặc điều khiển thiết bị

**RC** phù hợp khi client liên tục gửi lệnh/tin nhắn và cũng liên tục nhận trạng thái/phản hồi. Hai chiều có vòng đời riêng và không cần ghép từng message thành request-response đơn lẻ.

### Tình huống E: Upload nhiều chunk và nhận một kết quả cuối

Đầu vào nhiều chunk → đó là **request-channel**, kể cả server trả về một kết quả tổng hợp cuối. Nhưng cần định nghĩa rõ giới hạn chunk, kiểm tra tổng kích thước, checksum, hủy giữa chừng và tránh giữ toàn bộ upload trong RAM.

## 12. Vận hành, bảo mật và khả năng khôi phục

### 12.1. Giữ connection và stream có giới hạn

- Theo dõi số connection và stream đang mở, tốc độ request, latency, RSocket ERROR/CANCEL và số lượng item pending.
- Đặt timeout hợp lý; với stream dài hạn, dùng idle/heartbeat policy thay vì deadline tổng quá ngắn.
- Giới hạn kích thước payload, tối đa item và concurrency để ngăn lạm dụng.
- Không tạo requester/connection mới cho mỗi phần tử của Flux; tái sử dụng requester có lifecycle quản lý.
- Gỡ bỏ subscription khi người dùng rời trang hoặc ứng dụng shutdown.

### 12.2. TLS, xác thực và ủy quyền

RSocket tự định nghĩa protocol nhưng **không tự cung cấp chính sách phân quyền nghiệp vụ**. Sử dụng transport bảo mật (TLS cho TCP, WSS cho WebSocket), xác thực danh tính (ví dụ setup/auth metadata kết hợp Spring Security RSocket) và kiểm tra quyền cho mỗi route.

Route nằm trong metadata nên cũng là input không đáng tin: không dựa vào route để suy ra người gửi đã được phép thực hiện thao tác. Không đưa token hoặc nội dung nhạy cảm vào wiretap logs. Giới hạn kích thước frame và yêu cầu để tránh DoS.

Ví dụ TCP `7000` trên máy local chỉ dành cho demo. Trong production cần kiểm soát network ingress/firewall, TLS, authentication, authorization và quota.

### 12.3. Resumption và leasing không phải bật sẵn

RSocket có khả năng mở rộng với **keepalive**, **leasing** (giới hạn số request phía kia được phép mở trong khoảng thời gian) và **session resumption** khi mất transport, nhưng khả năng hỗ trợ và cách bật tùy phiên bản thư viện, runtime và cấu hình cả hai phía.

Không khẳng định resumption tự động bảo đảm mọi business event không mất hoặc exactly-once. Muốn delivery bền vững vẫn cần transaction/outbox, idempotency và cơ chế replay có chủ đích.

### 12.4. Tránh block trên Reactor event loop

Không gọi `block()`, dùng JDBC blocking hoặc I/O đồng bộ lâu dài trong `@MessageMapping` reactive handler; việc đó có thể chặn event loop và làm tất cả stream chậm. Nếu bắt buộc gọi legacy blocking library, chuyển sang scheduler chuyên dụng có giới hạn như `Schedulers.boundedElastic()` và cân nhắc thay bằng reactive driver.

`block()` trong `ApplicationRunner` của ví dụ là ngoại lệ có chủ đích cho demo command-line tuần tự, không phải hướng dẫn viết production handler.

## 13. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng FNF để xác nhận tạo đơn hàng | `send()` không là business ack | Dùng RR và idempotency hoặc hàng đợi bền vững. |
| Mong FNF trả body | FNF không có response payload | Dùng RR nếu phải nhận kết quả. |
| Mong RR phát nhiều item | RR có tối đa một kết quả | Dùng RS hoặc gói kết quả vào một object khi thật sự cần. |
| Gửi đầu vào `Flux` nhưng nghĩ là request-stream | Input nhiều thuộc channel | Dùng RC với `data(Flux, elementClass)`. |
| Nghĩ channel buộc 1–1 request/response | Channel hai chiều độc lập | Thiết kế protocol ứng dụng với mối tương quan nếu cần. |
| Không subscribe requester publisher | Reactive pipeline lazy; chưa có tương tác | Subscribe đúng lifecycle hoặc để framework subscribe. |
| Gọi `subscribe()` tùy tiện, bỏ mất error | Không quản lý tài nguyên/error | Trả Mono/Flux cho caller hoặc quản lý subscription. |
| Dùng `block()` trong event loop | Làm nghẽn cả các stream khác | Dùng non-blocking operators. |
| Đặt buffer vô hạn cho hot publisher | Có thể cạn bộ nhớ | Dùng backpressure policy có giới hạn. |
| Không handle cancel khi stream dài hạn | Rò rỉ subscription/resource | Dùng `doFinally`/`usingWhen`, đóng connection khi shutdown. |
| Retry side effect không idempotent | Tạo giao dịch hoặc message trùng | Thêm idempotency key và giới hạn retry. |
| Mong timeout đồng nghĩa rollback | Server có thể đã xử lý trước timeout | Xác định trạng thái bằng API/ID riêng. |
| Nhầm RSocket route với URL HTTP | Mismatch routing và protocol | Dùng `@MessageMapping` và route metadata. |
| JSON codec không có trên classpath | Decode DTO thất bại | Thêm Jackson/codec và cấu hình MIME type thống nhất. |
| Cho rằng TCP RSocket tự mã hóa | TCP thường không TLS | Cấu hình TLS/WSS và authentication phù hợp. |
| Mở cổng public không giới hạn | Rủi ro lạm dụng và tấn công | Giới hạn ingress, authz, payload size và quota. |
| Coi `mvn test` là end-to-end test | Unit tests chỉ gọi handler trực tiếp | Chạy app kết nối TCP hoặc integration tests riêng. |

## 14. Câu hỏi tự kiểm tra

**Câu 1:** RSocket có phải HTTP và `@MessageMapping` có phải GET/POST không?  
**Đáp án:** Không. RSocket là application protocol riêng chạy trên TCP/WebSocket; route được truyền qua metadata.

**Câu 2:** FNF có xác nhận xử lý thành công không?  
**Đáp án:** Không. `Mono<Void>` của `send()` chỉ phản ánh gửi phía requester, không bảo đảm responder đã xử lý.

**Câu 3:** Một request, một object phản hồi phù hợp với mô hình nào?  
**Đáp án:** Request-response; thường dùng `retrieveMono`.

**Câu 4:** Một request và nhiều bản ghi được gửi dần phù hợp với gì?  
**Đáp án:** Request-stream; dùng `retrieveFlux` và responder trả `Flux`.

**Câu 5:** Requester gửi 10 thông điệp, responder gửi 2 thông điệp; có hợp lệ không?  
**Đáp án:** Hợp lệ với request-channel; hai chiều không bị buộc cùng số item.

**Câu 6:** `REQUEST_N` dùng để làm gì?  
**Đáp án:** Thể hiện số phần tử downstream còn muốn nhận, hỗ trợ backpressure ở ranh giới mạng.

**Câu 7:** Khi dùng `take(3)` trên request-stream, chuyện gì xảy ra?  
**Đáp án:** Caller nhận tối đa ba item rồi hủy subscription; RSocket có thể truyền CANCEL. Hủy không bảo đảm side effect đã rollback.

**Câu 8:** Phân biệt input `Flux<T>` với output `Flux<R>`?  
**Đáp án:** Input Flux nghĩa là requester gửi nhiều thông điệp (channel); output Flux nghĩa là responder có thể gửi nhiều thông điệp. Đầu vào một, đầu ra nhiều là request-stream.

**Câu 9:** Tại sao không đặt mọi thứ vào `Mono<List<T>>`?  
**Đáp án:** Cách đó phải gom kết quả trước khi trả, tăng memory/latency; request-stream cho phép truyền và tiêu thụ từng phần theo demand.

**Câu 10:** Resumption/lease có mặc định bảo đảm exactly-once không?  
**Đáp án:** Không. Đây là các khả năng protocol phụ thuộc hỗ trợ/cấu hình; tính đúng đắn nghiệp vụ cần cơ chế lưu bền, retry và idempotency riêng.

## 15. Tóm tắt

- **FNF:** 1 chiều, không có business ack; `send()` hoàn tất không đồng nghĩa message đã xử lý.
- **RR:** 1 request → tối đa 1 kết quả, thường dùng `Mono<T>`.
- **RS:** 1 request → nhiều kết quả, dùng `Flux<T>` cùng demand/cancel.
- **RC:** hai chiều đều có thể là stream, không nhất thiết 1–1 và có lifecycle riêng.
- Spring `@MessageMapping` xử lý route; `RSocketRequester` khởi xướng tương tác qua `send`, `retrieveMono` hoặc `retrieveFlux`.
- Backpressure không tự thay thế giới hạn bộ nhớ, durability, authentication, timeout hoặc idempotency.

## Tài liệu tham khảo

1. [Spring Framework – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): overview, requester, annotated responder, cardinality và metadata.
2. [Spring Boot 3.3 – RSocket](https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html): auto-configuration, TCP/WebSocket server và RSocketRequester.Builder.
3. [RSocket Protocol Definition](https://github.com/rsocket/rsocket/blob/master/Protocol.md): frame REQUEST_FNF, REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL, REQUEST_N, CANCEL và COMPLETE.
4. [RSocket – Protocol](https://rsocket.io/about/protocol/): flow control, lifecycle và frame semantics.
5. [Spring Framework 6.1 – RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html): `tcp`, `dataMimeType`, connection setup.
6. [Spring Framework 6.1 – RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html): `data`, `send` và `retrieveFlux`.
7. [Project Reactor – Reference](https://projectreactor.io/docs/core/release/reference/): demand, cancellation, `Mono`, `Flux` và test support.
