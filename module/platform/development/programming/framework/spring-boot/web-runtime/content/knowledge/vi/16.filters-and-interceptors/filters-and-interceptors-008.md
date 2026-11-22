# ServerHttpRequestDecorator, ServerHttpResponseDecorator và xử lý DataBuffer trong Spring WebFlux

Trong Spring Boot dùng **Spring WebFlux**, request và response đi qua các reactive HTTP abstractions. Khi muốn quan sát body, thay header, thêm quy tắc ghi response, hoặc tích hợp tracing/audit ở tầng web, các công cụ quen thuộc là **`WebFilter`**, **`ServerWebExchange`**, **`ServerHttpRequestDecorator`**, **`ServerHttpResponseDecorator`** và **`DataBuffer`**.

Đây là các thành phần của **reactive web stack**, khác với `HttpServletRequestWrapper`, `HttpServletResponseWrapper` và Servlet `Filter` trong Spring MVC. Một request WebFlux có thể được xử lý qua nhiều callback trên nhiều thread; không nên coi request body là một `InputStream` có thể đọc tùy ý nhiều lần.

Mục tiêu bài học:

1. Hiểu **vị trí decorator** trong pipeline và cách thay request/response mà handler phía sau thực sự nhìn thấy.
2. Phân biệt **quan sát**, **đọc/tiêu thụ**, **biến đổi** và **cache/replay** body.
3. Nắm hợp đồng **`Flux<DataBuffer>`**, vòng đời pooled buffer và quy tắc release.
4. Sử dụng đúng `writeWith` và `writeAndFlushWith` khi bọc response.
5. Viết một ví dụ **Java 17+ / Spring Boot 3.x** có thể chạy và test: đo lượng bytes của request/response mà không làm mất body.
6. Biết khi nào **không nên** dùng decorator; phát hiện lỗi data loss, double subscription, memory leak và response đã commit.

**Nguyên tắc thiết kế:** nếu chỉ cần đo lưu lượng hoặc theo dõi tiến trình, **không đọc, không giữ, không giải mã toàn bộ body**. Ưu tiên `doOnNext` quan sát kích thước `DataBuffer` và để framework sở hữu buffer tiếp tục xử lý. Chỉ sao chép/aggregate bytes khi có nhu cầu thực sự, có giới hạn kích thước và hợp đồng ownership rõ ràng.

## 1. Decorator nằm ở đâu trong Spring WebFlux?

Một request qua Reactor Netty thường đi theo mô hình:

~~~text
Client HTTP
    |
    v
Reactor Netty HTTP server
    |
    v
ServerWebExchange
    |-- ServerHttpRequest: URL, headers, cookies, Flux<DataBuffer> body
    |-- ServerHttpResponse: status, headers, ghi DataBuffer response
    |
    v
WebFilter chain
    |
    +-- tạo ServerHttpRequestDecorator
    +-- tạo ServerHttpResponseDecorator
    +-- exchange.mutate().request(...).response(...).build()
    |
    v
DispatcherHandler
    |
    +-- HandlerMapping / HandlerAdapter
    +-- @RestController hoặc functional handler
    +-- HttpMessageReader / Decoder đọc request body
    +-- HttpMessageWriter / Encoder ghi response body
    |
    v
HTTP response ra client
~~~

`ServerWebExchange` đại diện cho request/response của lượt xử lý reactive HTTP. `WebFilter#filter(ServerWebExchange, WebFilterChain)` có thể đưa một **exchange đã được trang trí** xuống chain.

**Mấu chốt:** chỉ tạo decorator không đủ. Phải chuyển chúng cho downstream qua exchange đã mutate:

~~~java
ServerWebExchange decorated = exchange.mutate()
        .request(decoratedRequest)
        .response(decoratedResponse)
        .build();

return chain.filter(decorated);
~~~

Đây là fragment: `decoratedRequest` và `decoratedResponse` phải là các đối tượng đã tạo trước đó. Nếu vẫn gọi `chain.filter(exchange)` trên exchange gốc, handler phía sau không nhìn thấy decorator mới.

### 1.1. WebFilter khác gì HandlerFilterFunction?

- `WebFilter` bao quanh xử lý ở tầng **reactive web application**, trước khi chọn handler. Nó phù hợp cho tracing, authentication/security integration, HTTP policy, request/response wrapping.
- `HandlerFilterFunction` thuộc **functional endpoint routing** và áp dụng cho các HandlerFunction/RouterFunction cụ thể.
- `HandlerInterceptor` của Spring MVC là cơ chế khác ở Servlet stack; không dùng class ấy để kỳ vọng thay thế WebFilter trên Reactor Netty.

Một filter có thể chặn request mà không gọi `chain.filter(...)`. Khi đó decorator response nếu đã tạo cũng không tự bảo đảm body được ghi; code phải hoàn tất response theo đúng reactive API.

## 2. ServerHttpRequestDecorator hoạt động thế nào?

`org.springframework.http.server.reactive.ServerHttpRequestDecorator` là lớp bao quanh một `ServerHttpRequest`. Nó ủy quyền các phương thức cho request gốc, trừ phương thức được override.

Các điểm tùy chỉnh thường gặp:

| Phương thức | Mục đích |
|---|---|
| `getBody()` | Bọc publisher dữ liệu request body |
| `getHeaders()` | Cung cấp view headers khác, cần nhất quán với body |
| `getURI()` | Thay view URI nếu thiết kế thực sự yêu cầu |
| `getMethod()` | Thay thông tin method theo cơ chế được hỗ trợ, rất hiếm khi cần |
| `getDelegate()` | Truy cập đối tượng request được decorator bao quanh |

Request decorator **không đồng nghĩa tạo bản sao của body**. Nếu `getBody()` trả thẳng publisher gốc, khả năng tiêu thụ vẫn theo bản chất của publisher kết nối HTTP: đó thường là nội dung đến từ network và không nên tùy ý subscribe hai lần.

### 2.1. Quan sát không làm thay đổi body

Ví dụ chỉ đếm bytes đi qua body khi downstream đọc:

~~~java
AtomicLong inboundBytes = new AtomicLong();

ServerHttpRequest request = new ServerHttpRequestDecorator(
        exchange.getRequest()) {

    @Override
    public Flux<DataBuffer> getBody() {
        return super.getBody()
                .doOnNext(buffer ->
                        inboundBytes.addAndGet(
                                buffer.readableByteCount()));
    }
};
~~~

Đây là fragment, cần imports `AtomicLong`, `ServerHttpRequest`, `ServerHttpRequestDecorator`, `Flux` và `DataBuffer`, cùng đối tượng `exchange`. Phương thức `readableByteCount()` chỉ đọc **số bytes có thể đọc**; nó không tự tiêu thụ bytes hoặc thay đổi read index.

`doOnNext` chạy khi publisher thực sự phát DataBuffer cho subscriber. Nếu route không cần đọc body, bộ đếm có thể vẫn là 0. Đếm này là lượng bytes **được quan sát đi qua publisher**, không phải chứng cứ tất cả bytes đã được ứng dụng parse thành công hoặc client đã gửi hết request trước khi cancel.

### 2.2. Vì sao đọc trực tiếp có thể làm mất body?

Một cách viết nguy hiểm:

~~~java
return super.getBody().doOnNext(buffer -> {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);  // Tiêu thụ readable bytes.
    logDebugLength(bytes.length);
});
~~~

Đây là **fragment minh họa lỗi**, không phải đoạn nên dùng nguyên trạng. `DataBuffer.read(byte[])` làm thay đổi vị trí đọc của buffer. Nếu sau đó để nguyên buffer được chuyển cho JSON decoder, downstream có thể nhận body rỗng/thiếu bytes.

Nếu mục tiêu chỉ đo kích thước, dùng `readableByteCount()`. Nếu cần kiểm tra nội dung mà không làm mất body, phải có chiến lược **sao chép hoặc replay** rõ ràng và tuân thủ ownership, kích thước tối đa, charset, data privacy và cancellation.

## 3. ServerHttpResponseDecorator hoạt động thế nào?

`org.springframework.http.server.reactive.ServerHttpResponseDecorator` bọc một `ServerHttpResponse`. Nó có thể được dùng để theo dõi khi response body được gửi qua reactive writer, hoặc thay đổi cách ghi trong giới hạn contract.

Các hook thường gặp:

- `writeWith(Publisher<? extends DataBuffer> body)`: ghi một publisher DataBuffer.
- `writeAndFlushWith(Publisher<? extends Publisher<? extends DataBuffer>> body)`: ghi các nhóm publisher, với ý nghĩa flush theo nhóm mà implementation hỗ trợ.
- `setComplete()`: đánh dấu response hoàn tất không có body.
- `beforeCommit(Supplier<? extends Mono<Void>> action)`: đăng ký hành động trước commit thông qua response implementation.
- `getHeaders()`, `setStatusCode(...)`: truy cập/thay đổi metadata khi response chưa commit.

**Không phải response nào cũng gọi `writeWith` theo một đường đi duy nhất.** Streaming hoặc writer đặc thù có thể dùng `writeAndFlushWith`; response không body có thể đi qua `setComplete`. Những cơ chế như zero-copy file transfer có thể sử dụng đường ghi khác. Vì vậy, một decorator chỉ override `writeWith` **không phải máy đo mọi bytes ra network**.

### 3.1. Đếm bytes bằng cách bọc publisher

~~~java
AtomicLong outboundBytes = new AtomicLong();

ServerHttpResponse response = new ServerHttpResponseDecorator(
        exchange.getResponse()) {

    @Override
    public Mono<Void> writeWith(
            Publisher<? extends DataBuffer> body) {
        return super.writeWith(
                Flux.from(body)
                    .doOnNext(buffer ->
                            outboundBytes.addAndGet(
                                    buffer.readableByteCount()))
        );
    }
};
~~~

Đây là fragment có imports tương ứng. Đoạn code **không tự subscribe** vào body; nó chuyển publisher đã được gắn operator xuống writer phía dưới. Không gọi `body.subscribe(...)` để log rồi lại gọi `super.writeWith(body)`: một HTTP body publisher có thể không thể đọc lại và việc subscribe kép có thể phá luồng.

Bộ đếm phản ánh **bytes emitted qua hook**; nó không khẳng định kernel đã ghi, gateway đã nhận, hay client đã đọc hết. Với cancellation, network failure hoặc writer đặc biệt, giá trị quan sát có thể không bằng bytes thật sự tới client.

### 3.2. writeAndFlushWith cần được xử lý khi quan sát streaming

Với dữ liệu streaming, response có thể dùng publisher lồng nhau:

~~~java
@Override
public Mono<Void> writeAndFlushWith(
        Publisher<? extends Publisher<? extends DataBuffer>> body) {
    return super.writeAndFlushWith(
            Flux.from(body)
                .map(part -> Flux.from(part)
                    .doOnNext(buffer ->
                            outboundBytes.addAndGet(
                                    buffer.readableByteCount())))
    );
}
~~~

Fragment này nằm trong cùng `ServerHttpResponseDecorator` đã có `outboundBytes`. Nó bọc mỗi inner publisher nhưng **giữ cấu trúc nhóm và flush**; không gom mọi part thành một byte array lớn. Nếu chỉ dùng `Flux.from(body).flatMap(...)` tùy tiện, việc sắp xếp/flush và thứ tự dữ liệu có thể bị thay đổi.

**Không tự ghi hai lần.** `writeWith` và `writeAndFlushWith` là các entry point do framework chọn theo cách ghi response. Mục tiêu là đo tại entry point nào được gọi, không gọi cả hai từ application code để “chắc chắn bắt đủ”.

## 4. DataBuffer là dữ liệu theo luồng, không phải một String

`org.springframework.core.io.buffer.DataBuffer` là abstraction vùng dữ liệu byte của Spring. Một body có thể được phát qua nhiều DataBuffer:

~~~text
POST /api/echo
      |
      v
Flux<DataBuffer>
   |-- DataBuffer #1: 120 bytes
   |-- DataBuffer #2: 256 bytes
   |-- DataBuffer #3: 76 bytes
      |
      v
Decoder (có thể aggregate/parse)
      |
      v
Java DTO
~~~

Số chunk/kích thước chunk là giả định để minh họa; **không có bảo đảm mỗi chunk trùng TCP packet**, mỗi field JSON, mỗi HTTP chunk hay mỗi dòng NDJSON.

Một vài phương thức/cơ chế quan trọng:

| API | Tác dụng | Lưu ý |
|---|---|---|
| `readableByteCount()` | Kiểm tra còn bao nhiêu bytes có thể đọc | Không tiêu thụ |
| `read(byte[])` | Đọc dữ liệu ra byte array | Có thể dịch read position |
| `DataBufferUtils.join(...)` | Aggregate buffers thành một DataBuffer | Cần giới hạn nếu nguồn không tin cậy |
| `DataBufferUtils.release(...)` | Giải phóng khi sở hữu pooled buffer | Tránh quên release hoặc double-release |
| `DataBufferUtils.retain(...)` | Tăng reference count khi phù hợp | Phải cân bằng release |
| `DataBufferUtils.write(...)` | Ghi stream DataBuffer vào đích phù hợp | Cần đọc kỹ overload/lifecycle |
| `doOnDiscard(...)` | Hook cleanup cho dữ liệu bị operator loại bỏ | Không phải giải pháp chung cho mọi leak |

Trên Reactor Netty, một số buffer có thể dựa trên Netty pooled/direct memory. Memory leak có thể thể hiện ở **direct memory**, không chỉ Java heap.

### 4.1. Quy tắc ownership

Một câu hỏi rất thực dụng khi viết filter custom: **“Đoạn code nào là bên sở hữu DataBuffer ở thời điểm này?”**

- Nếu chỉ `doOnNext(buffer -> meter.add(...))` rồi chuyển buffer **nguyên trạng** xuống downstream: không tự release ở callback quan sát.
- Nếu tự consume buffer và **không chuyển tiếp** cho ai khác: phải release theo hợp đồng API.
- Nếu gọi `DataBufferUtils.join` và nhận buffer kết quả rồi sử dụng xong: phải release buffer kết quả khi đã có ownership.
- Nếu tạo một buffer mới từ dữ liệu đã copy: chịu trách nhiệm thiết kế nơi downstream có quyền sở hữu buffer mới.
- Nếu có cancellation/error hoặc operator discard buffer: bảo đảm cleanup phù hợp, không double release.

**Tránh “thêm release ở khắp nơi cho an toàn”.** Release sai chỗ có thể khiến downstream đọc buffer đã bị giải phóng, dẫn đến lỗi khó tái hiện.

## 5. Ví dụ đầy đủ: WebFilter dùng hai decorator đo byte

Ví dụ này dùng **Spring Boot 3.x**, **Java 17+**, **Spring WebFlux** và Reactor Netty mặc định. Dùng một project Spring Boot có plugin và dependency management đã thiết lập.

Trong `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Không thêm `spring-boot-starter-web` vào project minh họa: khi cả Web MVC và WebFlux xuất hiện trên classpath, Spring Boot thường suy luận Servlet MVC mặc định. Bài này cần **Reactive WebFlux server**.

Tệp **src/main/java/demo/decorator/DecoratorDemoApplication.java**:

~~~java
package demo.decorator;

import java.util.concurrent.atomic.AtomicLong;

import org.reactivestreams.Publisher;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DecoratorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DecoratorDemoApplication.class, args);
    }
}

record Note(String message) {
}

@Component
class BodyMeterFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        AtomicLong requestBytes = new AtomicLong();
        AtomicLong emittedResponseBytes = new AtomicLong();

        ServerHttpRequest decoratedRequest =
                new ServerHttpRequestDecorator(exchange.getRequest()) {

            @Override
            public Flux<DataBuffer> getBody() {
                return super.getBody()
                        .doOnNext(buffer -> requestBytes.addAndGet(
                                buffer.readableByteCount()));
            }
        };

        ServerHttpResponse decoratedResponse =
                new ServerHttpResponseDecorator(exchange.getResponse()) {

            @Override
            public Mono<Void> writeWith(
                    Publisher<? extends DataBuffer> body) {

                return super.writeWith(
                        Flux.from(body)
                            .doOnNext(buffer ->
                                emittedResponseBytes.addAndGet(
                                    buffer.readableByteCount())));
            }

            @Override
            public Mono<Void> writeAndFlushWith(
                    Publisher<? extends Publisher<? extends DataBuffer>>
                            body) {

                return super.writeAndFlushWith(
                        Flux.from(body)
                            .map(part -> Flux.from(part)
                                .doOnNext(buffer ->
                                    emittedResponseBytes.addAndGet(
                                        buffer.readableByteCount()))));
            }
        };

        // Dấu hiệu test đơn giản; phải thêm trước khi response commit.
        decoratedResponse.getHeaders().set("X-Body-Meter", "on");

        ServerWebExchange decoratedExchange = exchange.mutate()
                .request(decoratedRequest)
                .response(decoratedResponse)
                .build();

        return chain.filter(decoratedExchange)
                .doFinally(signal -> System.out.printf(
                        "meter: request=%d responseEmitted=%d signal=%s%n",
                        requestBytes.get(),
                        emittedResponseBytes.get(),
                        signal));
    }
}

@RestController
class DecoratorDemoController {

    @PostMapping(
            path = "/demo/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Note> echo(@RequestBody Mono<Note> input) {
        return input;
    }

    @GetMapping(
            path = "/demo/ping",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

### 5.1. Vì sao ví dụ này không làm mất body?

1. `getBody()` chỉ gắn `doOnNext` vào publisher gốc; nó **không gọi `read(byte[])`**, không giữ buffer, không subscribe độc lập, không release buffer.
2. `writeWith(...)` và `writeAndFlushWith(...)` chuyển publisher đã gắn đo lường cho `super`. Bytes không được sao chép hay thay thế.
3. `exchange.mutate()` chuyển cả hai decorator cho các filter/handler phía sau.
4. `AtomicLong` lưu số bytes quan sát riêng cho **mỗi lượt gọi filter**, không dùng một biến static để trộn các request đồng thời.
5. `doFinally` giúp in số đếm khi reactive chain kết thúc với complete, error hoặc cancel. Nó báo **tín hiệu hoàn tất của chain**, không bảo đảm toàn bộ bytes đã đi tới client hoặc đã qua TCP ACK.
6. Header `X-Body-Meter: on` là dấu hiệu để test filter được áp dụng. Trong thực tế, không dùng một header tùy biến làm bằng chứng bảo mật hay hệ thống chống giả mạo request.

**Lưu ý quan trọng:** các byte count không được hứa là số chính xác của network traffic. Compression, frame/chunk overhead, transfer encoding, zero-copy và response writer đặc thù có thể khiến số bytes phát qua hook khác số bytes trên wire. Với response không có body, bộ đếm emitted có thể là 0.

### 5.2. Chạy và gọi API

Từ thư mục dự án đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. Khi Reactor Netty lắng nghe cổng mặc định 8080:

~~~bash
curl -i http://localhost:8080/demo/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"message":"xin chao"}'
~~~

Kỳ vọng HTTP status **200**, response có header `X-Body-Meter: on` và JSON tương đương:

~~~json
{"message":"xin chao"}
~~~

Gọi endpoint không có request body:

~~~bash
curl -i http://localhost:8080/demo/ping
~~~

Body là:

~~~text
pong
~~~

Console sẽ có những dòng bắt đầu bằng `meter: request=... responseEmitted=... signal=...`, nhưng **không đưa ra một bộ số cố định**: số DataBuffer, cách serialize response và trạng thái cancellation có thể thay đổi theo client/runtime. Với `GET /demo/ping`, request body thông thường rỗng nên số bytes quan sát qua `getBody()` có thể là 0.

### 5.3. Điều gì xảy ra nếu client không gửi body?

Nếu WebFlux không subscribe vào request body vì handler không cần đọc, `getBody()` có thể không phát bất kỳ buffer nào. Điều này không làm sai logic của filter: chỉ số `requestBytes` đo **bytes được downstream tiêu thụ qua decorator**, không phải số bytes client có thể đã truyền tới transport ở tầng thấp hơn.

Không buộc subscribe body chỉ để làm số đếm bằng Content-Length. Nếu cần so sánh với Content-Length, cần nhớ header có thể thiếu, không tin cậy hoặc không phản ánh kích thước body sau một số biến đổi.

## 6. Kiểm thử WebFilter bằng WebTestClient

Trong cùng project trên, thêm `spring-boot-starter-test`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tạo **src/test/java/demo/decorator/DecoratorDemoApplicationTest.java**:

~~~java
package demo.decorator;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class DecoratorDemoApplicationTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void requestAndResponseRemainReadable() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .build();

        client.post()
              .uri("/demo/echo")
              .contentType(MediaType.APPLICATION_JSON)
              .accept(MediaType.APPLICATION_JSON)
              .bodyValue(Map.of("message", "xin chao"))
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals("X-Body-Meter", "on")
              .expectBody()
              .jsonPath("$.message").isEqualTo("xin chao");
    }

    @Test
    void emptyRequestBodyDoesNotBreakResponse() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .build();

        client.get()
              .uri("/demo/ping")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals("X-Body-Meter", "on")
              .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

Ở ví dụ này, `WebTestClient` được import từ **`org.springframework.test.web.reactive.server.WebTestClient`**. `bindToApplicationContext(...)` tạo client dùng WebFlux infrastructure trong process, không yêu cầu auto-inject một HTTP client sẵn có hay mở TCP server thật. Test kiểm tra filter hoạt động **và** body vẫn được decode/encode bình thường.

Chạy:

~~~bash
./gradlew test
~~~

Các test không khẳng định byte count chính xác, vì mục đích là chứng minh **không làm hỏng body**. Nếu cần kiểm thử behavior qua HTTP network, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và WebTestClient/HTTP client được cấu hình cho cổng thực; bài test trong process không thay thế test Reactor Netty TCP/TLS.

## 7. Tình huống cần thực sự đọc hoặc biến đổi body

Quan sát số bytes không tương đương với đọc nội dung. Khi muốn sửa JSON hoặc thêm chữ ký/hmac, bài toán khó hơn đáng kể:

1. Request publisher thường **được thiết kế cho tiêu thụ một lần**. Không tự subscribe vào body ở filter rồi trông chờ controller đọc lại.
2. Muốn xem đầy đủ body, thường cần **aggregate** một số buffers. Phải đặt giới hạn và cân nhắc payload lớn hoặc streaming.
3. Nếu đọc buffer làm thay đổi read index, phải tạo lại một publisher DataBuffer chứa nội dung để downstream đọc.
4. Khi đổi body length, phải xem lại `Content-Length` hoặc `Transfer-Encoding`; không được giữ header thể hiện kích thước cũ.
5. Charset, compression và content type phải tương thích với bytes được thay.
6. Nếu tạo buffer mới, phải hiểu ownership/release khi hoàn tất, lỗi hoặc cancel.
7. Không áp dụng cơ chế gom toàn bộ cho upload file lớn hoặc NDJSON stream nếu mục tiêu là xử lý theo luồng.
8. Security/tracing không nên phụ thuộc vào lưu toàn bộ body nhạy cảm.

### 7.1. Ví dụ aggregate có giới hạn, đọc xong phải release

Fragment minh họa một utility **sao chép body nhỏ ra byte array**. Đây là phép aggregate có giới hạn, **không phải** một request decorator hoàn chỉnh:

~~~java
static Mono<byte[]> copySmallBody(Flux<DataBuffer> source) {
    int maxBytes = 64 * 1024;

    return DataBufferUtils.join(source, maxBytes)
            .map(joined -> {
                try {
                    byte[] result =
                            new byte[joined.readableByteCount()];
                    joined.read(result);
                    return result;
                } finally {
                    DataBufferUtils.release(joined);
                }
            });
}
~~~

Để dùng fragment, cần import `DataBuffer`, `DataBufferUtils`, `Flux` và `Mono`. `DataBufferUtils.join(source, maxBytes)` kiểm soát số bytes được join. Khi vượt giới hạn, nó có thể phát `DataBufferLimitException` thay vì cho phép aggregate không giới hạn; cần chính sách xử lý lỗi phù hợp.

Ở nhánh thành công, code sao chép bytes ra một mảng độc lập và **release buffer kết quả trong finally**. Đây là cách bảo đảm không giữ pooled DataBuffer khi ta đã lấy ra byte array. `Mono` được trả về sẽ không phát dữ liệu nếu upstream rỗng; ứng dụng có thể cần xử lý body trống theo hợp đồng endpoint.

**Đừng dùng utility này rồi return `chain.filter(exchange)` với request body gốc:** body đã được tiêu thụ. Nếu thực sự cần cho controller đọc lại, phải tạo `ServerHttpRequestDecorator` mới với `getBody()` trả về **buffer mới chứa bytes đã sao chép**, chuyển decorator vào `exchange.mutate()`, và xem lại headers/giới hạn/cancellation. Việc này nên có integration tests riêng cho cả body nhỏ, body lớn, body trống, lỗi decode và client cancel.

### 7.2. Replaying byte array cần tạo DataBuffer mới mỗi subscription

Sau khi đã sở hữu một `byte[] bytes` độc lập, một fragment minh họa publisher mới:

~~~java
Flux<DataBuffer> replay = Flux.defer(() ->
        Flux.just(exchange.getResponse()
                .bufferFactory()
                .wrap(bytes)));
~~~

Đây là fragment: `bytes` và `exchange` có sẵn trong phạm vi method. `Flux.defer` tạo một DataBuffer wrapper mới mỗi lần subscribe, thay vì cố phát lại **cùng một pooled DataBuffer đã bị đọc hoặc release**. Sử dụng buffer factory thuộc exchange chỉ để minh họa việc tạo DataBuffer; production code cần xem xét factory thích hợp, ownership và behavior khi framework giải phóng buffer.

**Không áp dụng vô hạn:** replay vẫn giữ toàn bộ byte[] trong bộ nhớ cho đến khi request/chain không còn tham chiếu, nên phải giới hạn kích thước và thời gian sống. Đồng thời, nếu body thực sự đã được sửa, cần cập nhật request headers tương ứng trước khi chuyển cho decoder.

## 8. Điều chỉnh Content-Length và Content-Type khi biến đổi request

Nếu filter thay đổi bytes từ dài 20 bytes thành 50 bytes nhưng giữ `Content-Length: 20`, downstream có thể đọc thiếu, chờ quá lâu hoặc xử lý sai body. Với content encoding/compression, chỉ sửa độ dài cũng chưa đủ.

Có thể tạo request header view mới qua `ServerHttpRequestDecorator#getHeaders()`, nhưng phải xử lý nhất quán:

- `Content-Length` phải phản ánh đúng bytes mới **nếu** muốn khai báo độ dài cố định.
- Nếu không biết trước độ dài vì response/request được stream, không tự bịa Content-Length.
- Nếu chuyển format JSON → text hoặc ngược lại, `Content-Type` cần phù hợp.
- Nếu đang có transfer encoding hoặc content encoding khác, phải hiểu cơ chế transport trước khi thay.
- Nếu thực hiện request signature verification, sử dụng bytes và canonicalization đúng hợp đồng chữ ký.
- Không sửa headers như `Authorization` hoặc `X-Forwarded-*` tùy tiện, vì đó là dữ liệu có ý nghĩa bảo mật và proxy trust boundary.

Với request headers có thể đọc trong decorator, tránh sửa trực tiếp một collection immutable hoặc được chia sẻ từ request gốc. Tạo bản sao phù hợp và chỉ thay những header có căn cứ. Để thay path, query hoặc metadata đơn giản hơn, cân nhắc `ServerHttpRequest.mutate()`; khi cần override cách đọc body, decorator là điểm mở rộng trực tiếp hơn.

## 9. DataBufferLimitException và giới hạn memory

`DataBufferLimitException` có thể xuất hiện khi một codec hoặc thao tác như `DataBufferUtils.join` vượt mức bytes được phép aggregate.

Ví dụ Spring Boot WebFlux có property:

~~~yaml
spring:
  codec:
    max-in-memory-size: 256KB
~~~

Đây là ví dụ một mức giới hạn cho những default codecs được cấu hình theo Boot, **không phải giới hạn tổng kích thước HTTP request toàn cục**. Các custom join/decoder có thể dùng giới hạn khác; nếu cần bảo vệ mọi request, phối hợp với giới hạn proxy/ingress, server, multipart, upload và concurrency.

Một số nguyên tắc:

- Không tăng `max-in-memory-size` lên hàng chục MB chỉ để tránh lỗi.
- Tránh `DataBufferUtils.join(body)` không có giới hạn với nguồn không tin cậy.
- Không decode mọi upload file/NDJSON thành một `String` hoặc `byte[]` lớn.
- Tính đến số request đồng thời và memory budget của container.
- Đừng mặc định `DataBufferLimitException` luôn được map thành HTTP 413; status thực phụ thuộc nơi phát sinh và exception handling.
- Lỗi trong `WebClient` khi aggregate response khác với lỗi server decode request; phải chỉnh đúng client/server codec.

Một WebFilter chỉ đếm `readableByteCount()` như ví dụ chính **không tự tạo buffer aggregation**, nên ít rủi ro hơn đáng kể so với lọc bằng cách join toàn bộ request body.

## 10. Response decorator và thời điểm commit

Response được coi là **committed** khi status/headers đã được gửi hoặc không còn khả năng sửa như trước. `ServerHttpResponse#beforeCommit(...)` cho phép đăng ký callback chạy trước commit trong những tình huống được implementation hỗ trợ.

Ví dụ fragment đăng ký một callback trước commit:

~~~java
exchange.getResponse().beforeCommit(() -> {
    if (!exchange.getResponse().isCommitted()) {
        exchange.getResponse().getHeaders()
                .add("X-Trace-Layer", "webflux");
    }
    return Mono.empty();
});
~~~

Đây là fragment và không dùng trong runnable demo; cần import `Mono`. Một cách đơn giản hơn khi filter biết chắc cần thêm header ngay từ đầu là cập nhật `getHeaders()` **trước** `chain.filter(...)`, như `X-Body-Meter` trong demo.

Không ghi response status/body tùy tiện trong `doFinally`: lúc đó response có thể đã hoàn tất, error hoặc cancel. `doFinally` phù hợp để thống kê/cleanup, không phải nơi sửa HTTP body.

### 10.1. Các response không đi qua cùng một đường viết

Một response có thể:

- Gọi `writeWith` để gửi một stream DataBuffer.
- Gọi `writeAndFlushWith` cho nhóm stream cần flush.
- Gọi `setComplete` khi không có body, ví dụ 204 No Content.
- Dùng specialized writer hoặc zero-copy file transfer, có khả năng không đi qua cùng hook bạn đã override.
- Bị chặn/hủy trước khi body hoàn tất.

Vì vậy, đừng tuyên bố một response decorator đơn giản là **đồng hồ đo bytes thực tế trên dây** cho mọi trường hợp. Nếu cần metrics network chính xác, kết hợp thông tin từ Netty, load balancer, proxy và hệ thống observability.

## 11. Tương tác với Spring Security và thứ tự WebFilter

Với WebFlux reactive security, Spring Security sử dụng **reactive WebFilter chain**, không phải Servlet `FilterChainProxy` theo cùng đường thực thi của Spring MVC.

Các filter có thể được xếp thứ tự bởi framework hoặc annotation/configuration phù hợp. Nếu có nhiều filter:

~~~text
Outer filter: before
   Security/filter: before
      Controller / functional handler
   Security/filter: after
Outer filter: after
~~~

Đây là luồng khái quát. Đối với reactive pipeline, “before/after” có thể tương ứng lúc subscription, completion, error hoặc cancellation, không đơn thuần thứ tự dòng Java chạy khi khai báo Mono.

Nếu security chặn request trước filter đo body hoặc controller, bộ đếm request body có thể thấp hoặc bằng 0. Đừng tự subscribe để “bắt đủ bytes” nếu HTTP body không được security/handler đọc.

**Đặt logging/inspection ở đâu?** Cần cân nhắc authentication, authorization, PII, request size và thứ tự filters. Không ghi raw credentials, tokens, cookies, password, private key hoặc file upload lên log. Việc một filter có quyền nhìn raw body không có nghĩa được phép lưu nó.

## 12. Lỗi thường gặp khi tự xử lý DataBuffer

| Sai lầm | Hậu quả | Hướng khắc phục |
|---|---|---|
| `getBody().subscribe(...)` trong WebFilter | Đọc body riêng, downstream có thể không đọc được | Compose vào `chain.filter`, không subscribe thủ công |
| `buffer.read(bytes)` rồi chuyển chính buffer ấy xuống | Decoder có thể thấy body rỗng/thiếu | Chỉ quan sát size, hoặc copy + replay có giới hạn |
| Gọi `DataBufferUtils.release` trên buffer chỉ được quan sát | Downstream có thể đọc buffer đã release | Chỉ release khi có ownership thực sự |
| Không release buffer kết quả từ `join` | Rò rỉ pooled/direct memory | `try/finally` release khi dùng xong |
| Cache một DataBuffer để dùng nhiều request/subscription | Double use/release, data corruption | Giữ byte[] có giới hạn rồi tạo buffer mới per subscription |
| `join` toàn bộ upload/file lớn | Memory spike, DataBufferLimitException/OOM | Streaming, multipart/`FilePart.transferTo` |
| Chỉ override `writeWith` | Bỏ sót stream dùng `writeAndFlushWith` | Hook phù hợp với API đang sử dụng |
| `flatMap` inner body không có ý thức thứ tự | Có thể đảo thứ tự chunks hoặc flush | Giữ inner publisher và order khi decorate |
| Đổi body nhưng không sửa headers | Content-Length/Content-Type không khớp | Đồng bộ header với bytes thực |
| Ghi response trong `doFinally` | Response có thể đã commit | Dùng beforeCommit hoặc chỉnh trước chain |
| Log toàn bộ body để debug | Lộ dữ liệu nhạy cảm, tăng tải | Chỉ log metadata/size, giới hạn sampling có kiểm soát |
| Dùng Servlet wrapper cho Reactor Netty WebFlux | Không áp dụng đúng stack | Sử dụng reactive ServerHttpRequest/Response decorators |

### 12.1. Đọc body hai lần sẽ ra sao?

Một request body được lấy từ network thường không phải một collection có thể phát lại tùy ý. Nếu filter subscription thứ nhất đã tiêu thụ bytes, subscription thứ hai có thể không có dữ liệu hoặc gây lỗi tùy implementation. Vì vậy, **đừng hứa getBody() cho phép đọc lại chỉ vì method trả Flux**.

Để hỗ trợ nhiều người tiêu thụ thật sự, cần thiết kế caching/replay ở ranh giới rõ, giới hạn kích thước, xử lý request không body, cancellation và lifecycle; không chỉ gọi `cache()` bừa bãi trên Flux chứa pooled DataBuffer.

### 12.2. doOnDiscard có cứu mọi buffer leak không?

Không. Với một reactive operator chủ động loại bỏ DataBuffer, có thể thêm hook `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` **ở đúng nơi sở hữu dữ liệu**. Nhưng nếu buffer vẫn được dùng downstream hoặc đã release ở nơi khác, thêm hook có thể gây double-release. Cần hiểu semantics của operator và test cancellation/error cases.

### 12.3. Vì sao count callback không bằng kích thước Content-Length?

- Request có thể bị cancel hoặc filter chặn trước khi decoder đọc toàn bộ.
- Request body publisher được chunk thành nhiều DataBuffer theo runtime, không theo HTTP header.
- Compression/coding có thể làm số bytes raw khác số bytes ứng dụng giải mã.
- Transfer-Encoding/chunk overhead không phải DataBuffer body payload.
- HTTP response có thể đi qua writer khác hoặc stream không được filter quan sát hết.
- Content-Length có thể vắng mặt khi stream/chunked hoặc không đáng tin cậy từ client.

Vì vậy, tách biệt **declared content length**, **bytes emitted through publisher** và **bytes thực qua network** trong tên metric.

## 13. Khi nào nên dùng cách khác?

Đừng đưa mọi yêu cầu vào custom WebFilter decorator:

- **Chỉ muốn HTTP request latency/status:** ưu tiên observability/Micrometer/Actuator hoặc tracing nếu đã có; custom filter chỉ khi cần metadata cụ thể.
- **Cần phân quyền/authentication:** dùng Spring Security reactive, không dựa vào việc tìm token trong body theo cách tự viết.
- **Cần validate JSON DTO:** dùng Bean Validation và argument resolution trong controller/service.
- **Cần chuẩn hóa JSON:** dùng Jackson config/codec customization, không rewrite toàn bộ raw JSON trong filter.
- **Cần transform response DTO:** cân nhắc tầng controller/service hoặc result handling phù hợp thay vì cắt nối bytes JSON ở response decorator.
- **Cần xử lý upload file lớn:** dùng `FilePart.transferTo` hoặc streaming APIs phù hợp; không giữ toàn bộ file trong byte[].
- **Cần điều tra lỗi codec:** quan sát `DataBufferLimitException`, media type và maxInMemorySize, không tự đặt body wrapper trước khi xác định nguyên nhân.
- **Cần filter chỉ cho functional endpoints:** cân nhắc `HandlerFilterFunction` khi scope phù hợp hơn global WebFilter.
- **Cần đo lưu lượng TCP chính xác:** dùng số liệu của Netty/proxy/load balancer thay vì đếm mọi DataBuffer ở Spring HTTP writer.

Chọn abstraction **thấp nhất nhưng đủ** để giải quyết yêu cầu, không hạ xuống byte-level nếu DTO/event-level đã cung cấp ngữ nghĩa cần thiết.

## 14. Hiệu năng, concurrency và cancellation

Một request có thể đi qua nhiều thread khi pipeline có scheduler boundary. Vì vậy:

- Bộ đếm theo request nên được chia sẻ an toàn giữa callbacks, ví dụ `AtomicLong` hoặc thiết kế khác bảo đảm ordering.
- Không dùng một field mutable của singleton `@Component` để giữ bytes/tạm body của tất cả request.
- Không gọi JDBC, blocking HTTP client, `Thread.sleep` hoặc thao tác CPU rất nặng trực tiếp trong callback ở Netty event loop.
- Khi cần dùng API blocking bất khả kháng, offload đúng chỗ bằng deferred source và scheduler phù hợp; decorator byte-level không phải nơi mặc định để truy cập DB.
- Đo callback bytes nhẹ để giảm overhead; việc decode lại JSON chỉ để log rất tốn CPU/memory.
- Khi client hủy request hoặc timeout, `doFinally` có thể thấy tín hiệu `cancel`; cleanup phải phù hợp với resources thực sự đang sở hữu.
- Thao tác logging bất đồng bộ hoặc metrics export cũng cần bounded queue; một filter “chỉ log” vẫn có thể gây bottleneck.

Ví dụ fragment phân biệt callback hoàn tất:

~~~java
return chain.filter(decoratedExchange)
        .doOnError(error -> recordFailure(error))
        .doFinally(signal -> recordTermination(signal));
~~~

Đây là fragment; `recordFailure`/`recordTermination` là các method giả định, không phải Java chạy độc lập. `doOnError` quan sát lỗi; `doFinally` chạy khi complete/error/cancel. Không tự kết luận `doFinally(ON_COMPLETE)` nghĩa là client đã nhận hết response qua mạng.

## 15. Kiểm thử nâng cao trước production

Ngoài happy path của demo, các tình huống cần test:

1. **Body trống:** GET hoặc POST không có body, không tạo NPE/cancel bất thường.
2. **JSON hợp lệ:** decoder nhận đủ body sau khi qua decorator.
3. **JSON sai:** status/error từ WebFlux vẫn đúng, filter không nuốt exception.
4. **Body lớn:** không tự aggregate; nếu code có join, phải có giới hạn.
5. **Streaming:** NDJSON/SSE dùng `writeAndFlushWith` khi tương ứng; không đảo thứ tự phần tử.
6. **Cancellation:** client hủy stream giữa chừng; không giữ pooled buffers và cleanup đúng.
7. **Concurrent requests:** requestBytes/responseBytes không bị trộn giữa các request.
8. **Response không body:** 204/304/HEAD, không giả định writeWith luôn được gọi.
9. **Security rejection:** 401/403 có thể trả trước controller; filter không ép đọc body.
10. **Response commit:** headers chỉ được sửa trước commit, không có double write.
11. **Upload/multipart:** không buffer nguyên file; xử lý ownership đúng.
12. **Server/runtime:** chạy end-to-end qua Reactor Netty thật và proxy khi mục tiêu là network behavior.

Có thể dùng `WebTestClient.bindToApplicationContext` cho nhiều tests của WebFlux pipeline trong process; riêng timeouts, pooled Netty memory và TLS cần integration/load tests qua network thực.

## 16. Checklist triển khai decorator an toàn

- Xác nhận ứng dụng thực sự dùng Spring WebFlux reactive stack, không nhầm với Spring MVC Servlet.
- Hiểu `ServerHttpRequestDecorator`, `ServerHttpResponseDecorator` chỉ bọc delegate; phải đưa chúng qua `exchange.mutate()`.
- Khi chỉ đo size, dùng `readableByteCount()` trong `doOnNext`; đừng `read(...)` hoặc subscribe thủ công.
- Không tự release pooled buffer nếu chỉ quan sát và vẫn chuyển downstream.
- Với response streaming, xem cả `writeWith`, `writeAndFlushWith`, `setComplete` và specialized writer.
- Khi transform body, đặt max size, sao chép dữ liệu có chủ đích, tạo buffer mới cho replay, cập nhật headers và bảo đảm cleanup.
- Dùng `DataBufferUtils.join(source, maxBytes)` khi aggregate có giới hạn; release kết quả khi đã đọc xong.
- Không cache/replay trực tiếp một pooled DataBuffer đã đọc/release.
- Bảo vệ dữ liệu nhạy cảm, không dump toàn bộ request/response body vào logs.
- Không sửa status/headers trong `doFinally` sau khi response có thể đã commit.
- Dùng concurrency-safe per-request state và theo dõi cancellation/error.
- Kiểm tra `DataBufferLimitException`, upload/file streaming và backpressure khi payload lớn.
- Phân biệt bytes trong DataBuffer, declared Content-Length và bytes trên network.
- Regression test JSON echo, text response, concurrent, empty body, cancel, security rejection và streaming.
- Ưu tiên Spring Security, Validation, Jackson codec hoặc observability abstraction khi chúng giải quyết bài toán ở tầng phù hợp hơn.

**Kết luận:** `ServerHttpRequestDecorator` và `ServerHttpResponseDecorator` là cách bọc các đối tượng HTTP reactive trong Spring WebFlux mà không thay thế handler. `DataBuffer` là dữ liệu byte theo luồng, có thể được pooled và phải tuân thủ ownership. Quan sát metadata hoặc size **không cần tiêu thụ body**; biến đổi body thì cần giới hạn, replay và release chính xác. Kết hợp `WebFilter` với `exchange.mutate()`, chỉ hook vào publisher cần thiết, và kiểm thử cả lỗi/cancellation/streaming là nền tảng để tùy chỉnh web runtime an toàn.