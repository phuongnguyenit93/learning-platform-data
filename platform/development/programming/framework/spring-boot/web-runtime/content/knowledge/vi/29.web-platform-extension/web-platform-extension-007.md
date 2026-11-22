# RSocket và sự khác biệt với mô hình yêu cầu–phản hồi HTTP

## 1. Vì sao cần tìm hiểu RSocket trong Spring Boot web-runtime?

Hầu hết API web bắt đầu bằng một request HTTP: client gửi `GET /orders/42`, server xử lý và trả về status, headers, body. Kiểu **request–response** rất phù hợp với CRUD, cache, trình duyệt, các API công khai và hạ tầng proxy hiện có. Tuy nhiên một số nhu cầu không chỉ cần một kết quả:

- Một thiết bị gửi dữ liệu cảm biến liên tục và cũng cần nhận lệnh điều khiển.
- Dashboard muốn nhận dãy kết quả ngay khi server tạo được, thay vì đợi batch hoàn tất.
- Client chỉ muốn phát một sự kiện không cần response body.
- Hai đầu muốn vừa nhận vừa gửi nhiều message **trên cùng một connection**, có cơ chế kiểm soát tốc độ sản xuất/tiêu thụ.

**RSocket** là một application protocol dành cho giao tiếp hai chiều, multiplexed và message-oriented trên các transport như **TCP** và **WebSocket**. Nó hỗ trợ bốn interaction models: **Request-Response**, **Fire-and-Forget**, **Request-Stream**, **Request-Channel**. Với streaming interactions, RSocket mang theo demand từ Reactive Streams ở mức protocol để bên gửi có thể điều chỉnh lượng dữ liệu phát.

Trong Spring Boot, RSocket thường được tích hợp qua `spring-boot-starter-rsocket`, `@MessageMapping`, `RSocketMessageHandler` và `RSocketRequester`. Bài hướng dẫn cách hiểu chúng, so sánh công bằng với HTTP, triển khai ví dụ **Java 17+ / Spring Boot 3.3.13** cùng kiểm thử thực tế.

**Ghi nhớ ngay từ đầu:** RSocket **không tự nhiên nhanh hơn HTTP**, không bảo đảm exactly-once, không tự cung cấp authentication, không tự biến nguồn dữ liệu blocking thành non-blocking, và không phải cách bắt buộc phải dùng cho mọi API cần realtime.

## 2. HTTP request–response: điểm bắt đầu để so sánh

Một HTTP API thông thường:

```http
GET /api/greet?name=Mai HTTP/1.1
Host: localhost:8080
Accept: text/plain
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

Hello, Mai!
```

Client gửi request; server gửi response. Mỗi tương tác HTTP có một **request message và response message** riêng với status code (`200`, `404`, `500`...), headers và body. Với HTTP/1.1 keep-alive, nhiều requests có thể dùng lại TCP connection; với HTTP/2, nhiều streams có thể multiplex trên cùng connection. Vì vậy câu “HTTP luôn mở kết nối TCP mới cho mỗi request” là **sai**.

HTTP cũng hỗ trợ các hình thức truyền liên tục:
- **Chunked/streaming HTTP response**: server gửi dần body.
- **SSE (Server-Sent Events)**: response text stream từ server về browser.
- **Long polling**: request giữ lâu để chờ event, rồi gửi lại request mới.
- **WebSocket upgrade**: chuyển sang protocol full-duplex khác.
- **HTTP/2/HTTP/3**: multiplexing và flow control ở nhiều lớp.

Vì vậy **khác biệt chính không phải “HTTP không thể stream”**, mà là **mô hình tương tác, định dạng protocol, ngữ nghĩa demand/cancellation, route/data/metadata và cách triển khai**. Đối với browser và public REST APIs, HTTP thường có lợi thế lớn về công cụ, proxy, cache, authentication conventions và khả năng tương thích.

### 2.1. Đối chiếu một request–response RSocket

```text
HTTP:
  Client ── GET /api/greet?name=Mai ──► HTTP server
  Client ◄─ HTTP 200 + "Hello, Mai!" ── Server

RSocket:
  Requester ── route="demo.greet", data="Mai" ──► Responder
  Requester ◄─ payload="Hello, Mai!" ───────────── Responder
```

RSocket không gửi HTTP method `GET` hay HTTP status `200` trong từng request frame. Nó dùng **route metadata** để tìm handler, và data payload để chứa dữ liệu. Khi xảy ra lỗi, RSocket dùng error frames/signals theo protocol thay vì HTTP status code trong tương tác TCP.

**Một kết nối RSocket có thể chở nhiều request streams đồng thời**, được phân biệt bằng stream ID ở protocol. Người dùng không cần tự mở một socket cho mỗi route/message.

## 3. Bốn interaction models của RSocket

| Mô hình | Requester gửi | Responder trả | Spring/Reactor API tiêu biểu | Tình huống |
|---|---|---|---|---|
| **Request-Response** | 0 hoặc 1 dữ liệu request | Một kết quả (hoặc completion/error phù hợp) | `retrieveMono(T.class)` | Tra cứu profile, xác nhận lệnh |
| **Fire-and-Forget** | Một thông điệp một chiều | Không có response payload nghiệp vụ | `send(): Mono<Void>` | Phát tín hiệu/telemetry chấp nhận thất lạc theo contract |
| **Request-Stream** | Một request | Nhiều response được phát dần | `retrieveFlux(T.class)` | Theo dõi kết quả xử lý, cập nhật định kỳ |
| **Request-Channel** | Dòng nhiều request messages | Dòng nhiều response messages | `data(Flux<T>,T.class).retrieveFlux(U.class)` | Telemetry hai chiều, interactive stream |

Một chi tiết quan trọng: `@MessageMapping` trong Spring chọn **interaction type** theo **cardinality** (số lượng) input/output, kết hợp với kiểu API phía requester. Đối với input nhiều phần tử, handler nhận `Flux<T>`. Với output nhiều phần tử, handler trả `Flux<T>`. Trường hợp many-to-one có những ràng buộc/mapping riêng, nên cần đối chiếu với bảng cardinality trong Spring Framework, không suy rằng mọi kết hợp `Mono`/`Flux` đều là một protocol interaction hợp lệ.

### 3.1. Request-Response

```text
Requester                                      Responder
   │ REQUEST_RESPONSE(route, data)                 │
   ├──────────────────────────────────────────────►│
   │                                               │
   │                       xử lý / validate        │
   │◄───────────────────────── PAYLOAD(response) ──┤
   │               hoặc ERROR                      │
```

Đây là mô hình gần HTTP nhất. Nó có một yêu cầu và một kết quả, nhưng vẫn sử dụng protocol RSocket, connection đã thiết lập, metadata riêng và các semantics khác HTTP.

### 3.2. Fire-and-Forget (FNF)

```text
Requester                                      Responder
   │ REQUEST_FNF(route, data)                      │
   ├──────────────────────────────────────────────►│
   │                                               │
   │    Không có business response trong protocol │
```

**`send().then()/Mono<Void>` không chứng minh nghiệp vụ đã xử lý xong.** Spring Framework ghi rõ `RSocketRequester.send()` chỉ chỉ báo việc message đã được gửi thành công theo contract, **không phải confirmation từ responder rằng business handler đã xử lý, lưu DB hoặc commit transaction**. Nếu cần biết lệnh đã được chấp nhận/lưu, dùng Request-Response để trả acknowledgement hoặc mô hình event durable có ACK.

### 3.3. Request-Stream

```text
Requester                                      Responder
   │ REQUEST_STREAM(route, data, demand=N)         │
   ├──────────────────────────────────────────────►│
   │◄────────────────── PAYLOAD(item 1) ───────────┤
   │◄────────────────── PAYLOAD(item 2) ───────────┤
   │             REQUEST_N(more demand)            │
   ├──────────────────────────────────────────────►│
   │◄────────────────── PAYLOAD(item 3)... ────────┤
   │                COMPLETE / CANCEL / ERROR      │
```

Requester có thể tiêu thụ từng message theo tiến độ. Demand không phải “mỗi giây gửi N bản tin”, mà là thông tin về **số phần tử** còn có thể tiếp nhận trong một stream theo Reactive Streams contract. Việc điều tiết phải đi xuyên qua operator/driver tới nguồn mới giảm được công việc thật.

### 3.4. Request-Channel

```text
Requester                                      Responder
   │ REQUEST_CHANNEL(route, first data)            │
   ├──────────────────────────────────────────────►│
   │◄────────────────────────── response item 1 ───┤
   ├────────────────────────── request item 2 ────►│
   ├────────────────────────── request item 3 ────►│
   │◄────────────────────────── response item 2 ───┤
   │◄────────────────────────── response item 3 ───┤
   │        Hai chiều có demand/cancel độc lập     │
```

Channel là giao tiếp dòng hai chiều. **Không có quy tắc protocol rằng cứ một input bắt buộc có đúng một output**: handler có thể filter, aggregate, fan-out, batch hoặc tạo response độc lập, tùy contract ứng dụng. Ví dụ demo `uppercase` phía dưới cố ý biến mỗi input string thành một output string để dễ quan sát.

## 4. RSocket hoạt động trên những tầng nào?

```text
Application logic
  @MessageMapping / RSocketRequester
            │
        Spring Messaging
  Encoders/Decoders + RSocketStrategies
            │
        RSocket protocol
  SETUP / REQUEST_* / PAYLOAD / REQUEST_N / CANCEL
  ERROR / KEEPALIVE / LEASE / RESUME (khi cấu hình)
            │
        Transport layer
           ├── TCP
           └── WebSocket (trên HTTP handshake)
            │
        Network/TLS/firewall
```

**Phân biệt:**
1. **Transport TCP/WebSocket:** cách byte frames đi qua mạng. TCP không phải HTTP API.
2. **RSocket protocol:** frame types, stream IDs, request models, setup, demand.
3. **Spring Messaging:** route tới `@MessageMapping`, decode data/metadata thành Java objects.
4. **Ứng dụng:** validate message, authentication, authorization, transaction, retry, metrics.

RSocket qua **WebSocket** không có nghĩa application gửi plain text WebSocket frames theo schema tự nghĩ ra: bên trong WebSocket vẫn là **RSocket binary protocol**. Một browser chỉ dùng `new WebSocket(url)` và gửi JSON string thông thường **không thể nói chuyện trực tiếp với RSocket server**; cần thư viện RSocket client triển khai RSocket framing/protocol.

## 5. Kết nối, SETUP, payload và metadata

Khi mở một connection RSocket, hai bên thỏa thuận qua `SETUP` các điều kiện như MIME types cho **data** và **metadata**, keepalive và các khả năng giao thức. Ở một connection mới, request có thể mang:

- **Route metadata:** ví dụ `demo.greet` để Spring tìm `@MessageMapping("demo.greet")`.
- **Data payload:** ví dụ `"Mai"` hoặc một DTO JSON/CBOR, được encode theo data MIME type.
- **Authentication/trace metadata:** khi được triển khai và đăng ký, có thể là bearer token, trace context, tenant key...; tất cả đều cần kiểm tra nguồn tin cậy.

`@MessageMapping` định nghĩa **route**, không phải HTTP URL. Chẳng hạn `@MessageMapping("orders.find")` không tự tạo endpoint `GET /orders/find`. Route có thể có phân cấp/dấu chấm, nhưng không có HTTP method, URI query hoặc status code đi kèm.

**RSocketRequester.Builder trong Spring Framework 6.1** hỗ trợ `dataMimeType(...)`, `metadataMimeType(...)`, `setupData(...)`, `setupRoute(...)`, `setupMetadata(...)` và custom `RSocketConnector`. Việc gửi SETUP diễn ra khi kết nối thực sự được thiết lập, có thể deferred/lazy ở client mới. Một requester có thể tái sử dụng shared connection và tự tái kết nối khi cần gửi requests, nhưng điều đó **không tự bật session resumption hay exactly-once replay**.

**MIME/codec phải thống nhất:** client gửi DTO có Jackson JSON nhưng server chỉ chấp nhận CBOR (hoặc custom byte format khác) có thể lỗi trước khi vào handler. Trong demo ta dùng String/Integer và các codecs mà Spring Boot đã auto-configure; khi đổi định dạng cần kiểm tra cả hai bên.

## 6. Backpressure: RSocket có thêm gì so với streaming HTTP?

Trong Reactor, `Flux<T>` triển khai Reactive Streams. Subscriber yêu cầu một số phần tử qua `request(n)`, producer được khuyến khích chỉ phát theo demand. RSocket truyền các tín hiệu demand cho Request-Stream/Channel thành frames như `REQUEST_N`. Khi người dùng xử lý chậm, hệ thống có **cơ chế protocol-level** để nói “tôi chỉ nhận thêm từng này messages”.

```text
Requester (slow consumer)              Responder
         │ REQUEST_STREAM(count=5)         │
         ├─────────────────────────────────►│
         │◄──────── tick-1 ─────────────────┤
         │◄──────── tick-2 ─────────────────┤
         │                                  │
         ├──── REQUEST_N(2) ───────────────►│
         │◄──────── tick-3 ─────────────────┤
         │◄──────── tick-4 ─────────────────┤
         │                                  │
         ├──── REQUEST_N(1) ───────────────►│
         │◄──────── tick-5, COMPLETE ───────┤
```

Số request trong sơ đồ chỉ để minh họa; **không phải trace thực của mọi Reactor operator**, vì Reactor có prefetch, batching và có thể yêu cầu trước nhiều phần tử. Để kiểm chứng flow control thực, phải quan sát demand ở Publisher và transport/protocol metrics.

**Backpressure không đồng nghĩa an toàn bộ nhớ tuyệt đối:**
- Một `Sinks.Many` hoặc broker hot source vẫn có thể tích lũy sự kiện nếu không thiết kế overflow strategy.
- Một tác vụ blocking hoặc SDK callback không tuân theo demand thì RSocket không tự dừng nó.
- `Flux.onBackpressureBuffer()` không giới hạn có thể làm RAM tăng.
- CANCEL có thể báo upstream ngừng làm nhưng không hoàn tác side effect đã commit.
- Các connection concurrent vẫn tiêu tốn file descriptors/TLS state/CPU/memory.
- Với payload rất lớn, cần cấu hình frame fragmentation, max size và quota.

HTTP/2 cũng có **flow control ở mức stream/connection**; không nên nói rằng HTTP hoàn toàn không có backpressure. Khác biệt ở đây là **Reactive Streams demand ở mức số message ứng dụng** được RSocket biểu diễn trực tiếp ở protocol, trong khi cách streaming HTTP thường chịu ảnh hưởng body buffering/socket flow control và adapter.

## 7. Khi nào nên dùng HTTP và khi nào cân nhắc RSocket?

| Câu hỏi | HTTP REST / SSE / WebSocket | RSocket |
|---|---|---|
| Public CRUD API cho browser/mobile? | Thường ưu tiên HTTP/JSON/OpenAPI | Chỉ dùng nếu client/hạ tầng hỗ trợ đầy đủ |
| HTTP caching, CDN, status codes, crawlers? | Có hệ sinh thái chuẩn mạnh | Không có mapping tương đương tự động |
| One request → one response? | HTTP rất phù hợp | Request-Response được, nhưng tăng dependency/protocol |
| Server → browser streaming đơn giản? | SSE có thể đủ | Request-Stream cần client RSocket phù hợp |
| Hai chiều nhiều messages trên một connection? | WebSocket là lựa chọn phổ biến | Channel phù hợp nếu cần semantics RSocket và backpressure |
| Microservice streaming nhiều luồng/route? | HTTP/2/gRPC có thể phù hợp | RSocket có lợi thế request models và demand/duplex |
| Hạ tầng chỉ cho HTTP qua proxy? | Dễ triển khai hơn | RSocket TCP có thể bị chặn; dùng RSocket-over-WebSocket nếu hỗ trợ |
| Cần broker lưu bền/replay? | Cần Kafka/RabbitMQ/DB tùy mô hình | RSocket **không thay thế** broker durable |
| Chính sách firewall/observability chuẩn của tổ chức? | HTTP thường có sẵn | Cần bổ sung telemetry/gateway/protocol support |
| Một team chủ yếu dùng Spring Reactive? | WebClient, SSE, WebSocket dễ tích hợp | RSocketRequester + @MessageMapping có thể rất tự nhiên |

**Không có kết luận “RSocket thắng HTTP”.** RSocket phù hợp **duplex streaming nội bộ/clients có protocol stack tương ứng**, nhất là khi cần nhiều interaction models và network backpressure rõ ràng. HTTP rất mạnh cho tích hợp công khai, browser, API đơn giản và quản trị hạ tầng.

## 8. Project hoàn chỉnh: HTTP request–response song song với RSocket TCP

Ví dụ dưới đây tạo **một Spring Boot app**:
- HTTP WebFlux server trên **8080**, endpoint `GET /http/greet?name=Mai`.
- RSocket TCP server trên **7000** với bốn routes:
  - `demo.greet`: Request-Response.
  - `demo.notice`: Fire-and-Forget.
  - `demo.ticks`: Request-Stream.
  - `demo.uppercase`: Request-Channel.

Có integration test **khởi động server thật**, kết nối TCP bằng `RSocketRequester.Builder.tcp(...)` và gọi từng model; không cần thư viện HTTP/CLI bên ngoài cho RSocket tests.

### 8.1. Cấu trúc thư mục

```text
rsocket-vs-http-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/rsocketdemo/RSocketVsHttpApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/rsocketdemo/RSocketInteractionTest.java
```

### 8.2. Build Gradle — Java 17+ và Spring Boot 3.3.13

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Giải thích dependencies:**
- `spring-boot-starter-webflux` cho HTTP server reactive, Reactor, codecs.
- `spring-boot-starter-rsocket` cho RSocket transport, Spring Messaging integration và requester.
- `spring-boot-starter-test` + `reactor-test` dùng JUnit và StepVerifier nếu muốn kiểm thử Publisher.
- Không thêm `spring-boot-starter-web` để tránh Spring Boot ưu tiên Servlet/MVC khi cả hai starters cùng có mặt.

Đây là **hai servers cùng process nhưng khác cổng** theo ví dụ. Có RSocket starter không tự khiến HTTP GET trở thành RSocket route; chúng là những entry points khác nhau.

### 8.3. Application properties

`src/main/resources/application.properties`:

```properties
spring.application.name=rsocket-vs-http-demo

# HTTP API (Spring WebFlux):
server.port=8080

# RSocket TCP nằm ở cổng riêng:
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
spring.rsocket.server.port=7000
```

`spring.rsocket.server.address=127.0.0.1` giới hạn bind ở loopback **cho demo local**. Nếu RSocket requester chạy từ container/host khác, loopback sẽ không truy cập được; production phải thiết kế listening address, network policy, service mesh/firewall, TLS và authentication. **Không mặc định mở port RSocket ra Internet.**

Spring Boot chỉ tự khởi động RSocket server khi cấu hình và dependencies phù hợp. Với TCP, `spring.rsocket.server.port` là cổng RSocket. Nó không phải `server.port` của HTTP. `curl http://localhost:7000/...` không nói chuyện được với RSocket TCP dù socket 7000 đang listen.

### 8.4. Java application — đủ cả bốn mô hình

`src/main/java/com/example/rsocketdemo/RSocketVsHttpApplication.java`:

```java
package com.example.rsocketdemo;

import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class RSocketVsHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketVsHttpApplication.class, args);
    }
}

// HTTP request-response, dành cho browser/curl.
@RestController
class HttpGreetingController {

    @GetMapping(
            path = "/http/greet",
            produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> greet(@RequestParam String name) {
        return Mono.just("Hello, " + name + "!");
    }
}

// RSocket: routing qua metadata thay vì HTTP method + URL.
@Controller
class RSocketDemoController {

    private static final Logger log =
            LoggerFactory.getLogger(RSocketDemoController.class);

    // 1 input -> 1 output: Request-Response.
    @MessageMapping("demo.greet")
    Mono<String> greet(@Payload String name) {
        return Mono.just("Hello, " + name + "!");
    }

    // 1 input -> không response payload: Fire-and-Forget.
    @MessageMapping("demo.notice")
    Mono<Void> notice(@Payload String message) {
        return Mono.fromRunnable(() ->
                log.info("Demo notice received (length={}): ",
                        message.length()));
    }

    // 1 input -> stream output: Request-Stream.
    @MessageMapping("demo.ticks")
    Flux<String> ticks(@Payload Integer count) {
        if (count == null || count < 1 || count > 5) {
            return Flux.error(new IllegalArgumentException(
                    "count must be between 1 and 5"));
        }
        return Flux.range(1, count)
                .map(i -> "tick-" + i);
    }

    // Stream input -> stream output: Request-Channel.
    @MessageMapping("demo.uppercase")
    Flux<String> uppercase(@Payload Flux<String> words) {
        return words.map(value ->
                value.toUpperCase(Locale.ROOT));
    }
}
```

**Tại sao đoạn mã phù hợp Java 17+?**
- Chỉ có một top-level `public class` (`RSocketVsHttpApplication`); hai controller còn lại package-private trong cùng package vẫn được component scanning.
- `@RestController` xử lý HTTP route. `@Controller` + `@MessageMapping` thuộc RSocket messaging handler, không phải servlet `@GetMapping`.
- Các return types trùng interaction models: `Mono<String>` cho response đơn; `Mono<Void>` cho FNF; `Flux<String>` cho stream.
- Channel nhận `Flux<String>`, không dùng một field/queue global mutable.
- `@Payload` làm rõ argument lấy từ payload, không phải HTTP query param.
- `Locale.ROOT` giúp chuyển uppercase không lệ thuộc locale máy chạy.
- Route `demo.notice` **chỉ log số ký tự**, không log nội dung message để tránh in tùy tiện dữ liệu mà client gửi.
- `ticks` giới hạn tối đa 5 phần tử để demo không tạo nguồn vô hạn.

**Lưu ý nhận diện Fire-and-Forget:** callback `Mono.fromRunnable` chạy khi Publisher được subscribe bởi framework. Lệnh requester `send()` hoàn tất **không phải bằng chứng** log chắc chắn đã được ghi tại responder. Nếu nghiệp vụ cần xác nhận, dùng Request-Response trả acknowledgement sau khi đã commit.

**Lưu ý thực tiễn:** `ticks` trong demo là `Flux.range` đồng bộ, không mô phỏng latency hay network backpressure. Nó đủ để học interaction model. Nếu muốn quan sát streaming theo thời gian, có thể chèn `delayElements(Duration.ofMillis(200))` (cần import `Duration`), nhưng test sẽ chậm hơn và không làm semantics của RSocket thay đổi.

### 8.5. Chạy và kiểm tra HTTP

Trong thư mục project, với JDK 17+ và Gradle tương thích Boot 3.3.13:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper: `./gradlew bootRun` trên macOS/Linux hoặc `.\gradlew.bat bootRun` trong PowerShell. Cần có Gradle wrapper hoặc Gradle được cài sẵn; đoạn hướng dẫn không ngầm tạo wrapper.

Test HTTP bằng curl:

```bash
curl -i "http://localhost:8080/http/greet?name=Mai"
```

Body mong đợi:

```text
Hello, Mai!
```

HTTP status dự kiến `200 OK`, `Content-Type` phù hợp `text/plain`. Đây là endpoint **HTTP**. Không có lệnh `curl` REST đơn giản tương đương gọi `demo.greet` qua RSocket TCP; cần RSocket client nói đúng binary protocol hoặc integration test bên dưới.

## 9. Integration test RSocket thực qua TCP

Để tránh xung đột cổng trên CI, test sử dụng:
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` để HTTP server chọn cổng ngẫu nhiên.
- Property test `spring.rsocket.server.port=0` để RSocket server cũng chọn cổng ngẫu nhiên.
- `@LocalRSocketServerPort` (Spring Boot 3.3) để inject **cổng RSocket thực tế**.
- `RSocketRequester.Builder` do Spring Boot auto-configure để dùng codecs/mime type thích hợp.

`src/test/java/com/example/rsocketdemo/RSocketInteractionTest.java`:

```java
package com.example.rsocketdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.rsocket.server.port=0")
class RSocketInteractionTest {

    @LocalRSocketServerPort
    int rsocketPort;

    @LocalServerPort
    int httpPort;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Test
    void httpRequestResponseUsesStatusAndBody() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + httpPort
                        + "/http/greet?name=Mai"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Mai!", response.body());
    }

    @Test
    void requestResponseReturnsOneMessage() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            String reply = requester.route("demo.greet")
                    .data("Mai")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            assertEquals("Hello, Mai!", reply);
        } finally {
            requester.dispose();
        }
    }

    @Test
    void requestStreamReturnsSeveralMessages() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            List<String> replies = requester.route("demo.ticks")
                    .data(3)
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            assertEquals(
                    List.of("tick-1", "tick-2", "tick-3"),
                    replies);
        } finally {
            requester.dispose();
        }
    }

    @Test
    void requestChannelStreamsBothDirections() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            List<String> replies = requester.route("demo.uppercase")
                    .data(Flux.just("one", "two"), String.class)
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            assertEquals(
                    List.of("ONE", "TWO"),
                    replies);
        } finally {
            requester.dispose();
        }
    }

    @Test
    void fireAndForgetCanSendWithoutResponsePayload() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            requester.route("demo.notice")
                    .data("ping")
                    .send()
                    .block(Duration.ofSeconds(5));
            // Không assert business đã commit.
            // send() chỉ xác nhận message được gửi theo contract.
        } finally {
            requester.dispose();
        }
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả kỳ vọng** (theo logic và API): năm tests hoàn tất thành công với đúng dependencies và environment. **Chưa chạy Gradle trong bài** nên không coi đây là kết quả runtime đã xác minh.

**Điểm học được từ test:**
- HTTP `HttpClient` nhận `statusCode()` và body.
- `RSocketRequester` dùng `route(...)`/`data(...)`/`retrieveMono` hoặc `retrieveFlux`, không thao tác HTTP path/method/status.
- `RSocketRequester.Builder.tcp(...)` của Spring Framework 6.1 trả **requester có thể dùng ngay** và thực hiện kết nối theo cơ chế lazy/shared client; khác API cũ `connectTcp(...): Mono<RSocketRequester>` đã deprecated.
- `requester.dispose()` giải phóng client/connection sau test; không giữ socket lâu quá vòng đời.
- `block(Duration)` hợp lệ ở **JUnit test thread** để assert kết quả. **Không** gọi `block()` trong Reactor Netty event-loop hay RSocket handler ở production.
- Test Fire-and-Forget chỉ chứng minh **có thể gửi**, không chứng minh server đã hoàn tất side effect — đó là một điểm ngữ nghĩa quan trọng, không phải thiếu assertion.
- RSocket server port có thể khác HTTP port; `@LocalServerPort` và `@LocalRSocketServerPort` không thay thế lẫn nhau.

Nếu bài test báo timeout, cần kiểm tra server thực sự bind TCP, route names, serializer, thread starvation và quy trình shutdown, không chỉ tăng timeout một cách mù quáng.

## 10. Vì sao không gọi RSocket TCP bằng REST client hay curl?

RSocket over TCP truyền **frames RSocket** chứ không phải HTTP headers/body. Vì thế:

```bash
# ĐÚNG: Đây là HTTP endpoint.
curl -i "http://localhost:8080/http/greet?name=Mai"

# SAI MỤC ĐÍCH: Cổng 7000 là RSocket TCP,
# không phải HTTP server.
curl -i "http://localhost:7000/demo.greet"
```

RSocket client cần khởi tạo requester:

```java
// Mảnh code đặt trong test/service đã inject RSocketRequester.Builder.
RSocketRequester requester = builder.tcp(
        "127.0.0.1", 7000);

Mono<String> reply = requester.route("demo.greet")
        .data("Mai")
        .retrieveMono(String.class);

// Ở Spring WebFlux business service, return/compose reply.
// Đừng tự subscribe rồi bỏ qua kết quả và errors.
```

Mảnh code này **không phải class độc lập**: cần import `RSocketRequester`, `Mono`, và biến `builder` được inject. Trong ứng dụng thực, nên quản lý requester như một client dùng chung và có shutdown/dispose, không tạo một requester/connection mới cho mỗi request business.

Các tool chuyên RSocket có thể gửi frames và metadata đúng protocol, nhưng không được xem một HTTP GET tương đương bằng cách đổi URL.

## 11. RSocket-over-WebSocket: khi TCP riêng không đi qua hạ tầng

Khi browser/gateway chỉ hỗ trợ HTTP(S)/WebSocket, Spring Boot có thể phục vụ RSocket **qua WebSocket** thay vì TCP. Với WebFlux server và Reactor Netty, có thể map RSocket vào HTTP server đang tồn tại:

```properties
# Profile / cấu hình thay thế cho ví dụ TCP (không đặt song song).
server.port=8080
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
# Không đặt spring.rsocket.server.port nếu muốn chia sẻ
# HTTP WebFlux server theo cơ chế tích hợp được Boot hỗ trợ.
```

Client Java phía ngoài:

```java
// Mảnh code trong service/test:
RSocketRequester requester = builder.websocket(
        URI.create("ws://localhost:8080/rsocket"));

Mono<String> reply = requester.route("demo.greet")
        .data("Mai")
        .retrieveMono(String.class);
```

Cần imports `URI`, `RSocketRequester`, `Mono` và builder đã cấu hình. `ws://` chỉ dùng môi trường local không có TLS; với production browser/HTTPS phải dùng `wss://` và certificate hợp lệ. Có thể có standalone RSocket-over-WebSocket server riêng nếu cấu hình port/transport phù hợp; **mapping-path với HTTP web server** phụ thuộc server stack (tài liệu Spring Boot nhấn mạnh Reactor Netty).

**Quan trọng:** một WebSocket connection carrying RSocket **không phải** raw WebSocket chat connection. Client phải implement **RSocket SETUP, frame, metadata và interaction models** trên transport đó. Browser WebSocket API đơn thuần chỉ vận chuyển raw bytes/messages và không tự hiểu RSocket protocol.

Với reverse proxy/ingress cần WebSocket upgrade, TLS, idle timeout, host/origin policy, số kết nối và buffering phù hợp. Không giả định mọi HTTP API gateway hiểu route metadata RSocket hoặc áp HTTP-level per-request authorization cho từng RSocket frame.

## 12. RSocket so với raw WebSocket và Server-Sent Events (SSE)

| Vấn đề | Raw WebSocket | RSocket | SSE |
|---|---|---|---|
| Protocol/abstraction | Duplex frames; app tự định nghĩa JSON commands | Duplex + 4 interaction types, route/data/metadata | HTTP event stream server → client |
| Application backpressure | Phải tự thiết kế thêm nếu cần | Reactive Streams demand qua network cho streaming | Thường phụ thuộc HTTP/reader/network và client protocol |
| Multiplex nhiều logical streams | App tự thêm message IDs/routes | Có stream IDs ở protocol | Một HTTP response stream, có thể có nhiều connections |
| Built-in request-response semantics | App tự đặt correlation IDs | Request-Response | Phải dùng HTTP API riêng cho client → server |
| Browser khả dụng | Native WebSocket API | Cần RSocket client library qua WebSocket | EventSource native |
| Gateway/public internet | Thường dùng được khi hỗ trợ upgrade | TCP khó hơn; WS transport cần proxy/stack hỗ trợ | HTTP tooling/ingress gần gũi hơn |
| Durable message broker | Không tự có | Không tự có | Không tự có |
| Authorization per event | App tự xây | App tự xây theo RSocket metadata/route/security | App tự xây theo HTTP/session |

Nếu chỉ cần “server thông báo số đơn hàng mới cho dashboard”, **SSE có thể đơn giản hơn**. Nếu cần browser chat hai chiều không có requirements message-level backpressure/correlation phức tạp, raw WebSocket có thể đủ. Với nhiều request streams hai chiều và client/server nội bộ cùng hỗ trợ Spring Reactive, RSocket đáng cân nhắc.

## 13. Frame-level backpressure, LEASE, KEEPALIVE và RESUME

RSocket có nhiều tính năng protocol đáng chú ý. Không phải tính năng nào cũng được bật/mặc định sử dụng trong Spring Boot:

### 13.1. REQUEST_N

Với Request-Stream/Channel, receiver có thể yêu cầu thêm messages. `REQUEST_N` là tín hiệu demand; cancellation gửi tín hiệu để dừng một stream. **Cần kiểm tra các operators Reactor** vì prefetch có thể khiến upstream yêu cầu trước nhiều phần tử hơn downstream xử lý tại thời điểm nhất định.

### 13.2. LEASE

LEASE là một mechanism để một peer thông báo số request peer kia được phép bắt đầu trong thời gian nhất định. Đây là **request admission control**, không phải `Flux.request(n)` của một stream. Nó cần được bật/cấu hình qua RSocket connector/server API; chỉ thêm `spring-boot-starter-rsocket` không khẳng định ứng dụng đang gửi LEASE frames.

### 13.3. KEEPALIVE

Trên connection dài, keepalive dùng để phát hiện peer/network không còn khả dụng. Chính sách interval/timeout phải phù hợp proxy, load balancer, network và giới hạn tài nguyên. HTTP keep-alive, TCP keepalive và RSocket KEEPALIVE **không phải một thứ**; chúng hoạt động ở các tầng khác nhau.

### 13.4. RESUME

RSocket protocol hỗ trợ cơ chế resumption khi mất kết nối và hai phía còn giữ state cần thiết. **Điều này không tự tạo exactly-once business transaction**, không tự lưu message vô hạn và không bảo đảm khôi phục sau restart/pod crash. Bật resume có thêm memory/storage/operation complexity; cần cấu hình cả hai phía theo transport/version và kiểm thử fault injection thật.

### 13.5. Fragmentation

RSocket có thể chia payload/frame lớn thành các fragments và reassemble. Tuy vậy việc sử dụng frame fragmentation **không thay thế** kích thước message tối đa, codec memory limit, queue limit hay validation. Payload khổng lồ vẫn có thể gây OOM nếu app gom toàn bộ thành DTO/byte[].

## 14. Cancellation, timeout và ý nghĩa của lỗi

Ở HTTP, client có thể hủy request/đóng kết nối; server tùy stack có thể phát hiện qua I/O và cancel reactive pipeline. Ở RSocket streaming, requester có thể cancel **một stream** mà connection vẫn phục vụ các streams khác.

```text
Shared RSocket connection
   │
   ├── Stream A: demo.ticks ── CANCEL ──► dừng A khi upstream hợp tác
   │
   ├── Stream B: demo.greet ── PAYLOAD ─► tiếp tục hoàn tất
   │
   └── Stream C: demo.uppercase ────────► vẫn hoạt động
```

**Không nhầm cancel với lỗi và không mặc định rollback**:
- `onComplete`: Publisher hoàn tất bình thường.
- `onError`: lỗi encode/decode, handler, transport hoặc business operation.
- `cancel`: downstream không còn muốn nhận; upstream được báo nếu chain hỗ trợ propagation.
- Timeout Reactor `timeout(Duration)` là client-side deadline ở publisher; không bảo đảm DB query/blocking call đã thực sự dừng.
- Nếu đã ghi dữ liệu vào DB trước khi cancel, việc cancel stream không hoàn tác commit.
- Mất connection có thể làm nhiều in-flight streams lỗi; không mặc định retry một side-effecting command.

Ví dụ client **chỉ nhận hai tick rồi hủy phần còn lại**:

```java
// Mảnh code trong service/test:
Flux<String> firstTwo = requester.route("demo.ticks")
        .data(5)
        .retrieveFlux(String.class)
        .take(2);

// Return/subscribe có kiểm soát trong runtime thích hợp.
```

Operator `take(2)` cancel upstream sau khi nhận đủ hai phần tử theo contract. Nhưng **không phải chứng cứ rằng server mới từng tạo đúng hai phần tử**: do prefetch, network buffering và source scheduling, một số item khác có thể đã được tạo/gửi trước khi cancel tới nơi.

**Xử lý lỗi đúng:** không `onErrorResume(e -> Mono.empty())` vô điều kiện nếu điều đó che mất lỗi protocol/auth/serialize. Map exception thành error policy quan sát được, bounded retries, log correlation ID và metrics; không in raw token/payload nhạy cảm.

## 15. Security: đừng coi RSocket là HTTP có thêm một cổng

Một lỗi triển khai nguy hiểm là đã bảo vệ `/api/**` bằng Spring Security WebFlux nhưng lại để RSocket TCP port mở public **không có RSocket security**. Chúng là **hai entry points khác nhau**.

Cần giải quyết:
1. **Transport security:** TLS trên RSocket TCP (hoặc WSS nếu RSocket-over-WebSocket), certificate validation, mTLS nếu threat model yêu cầu.
2. **Connection-level authentication:** xác thực peer lúc SETUP/metadata theo khả năng Spring Security RSocket hoặc một policy tương đương.
3. **Per-route authorization:** không phải vì một connection đã authenticate mà mọi route/tenant action đều được phép.
4. **Payload validation:** message size, DTO schema/version, allowed route, ownership/tenant, rate limit.
5. **Network policy:** TCP port RSocket chỉ mở cho clients được phép; proxy/mTLS/ingress ACL phù hợp.
6. **Secrets:** không log payload, setup token, cookies hoặc authorization metadata; secret rotation và revocation.
7. **Backpressure/resource quotas:** giới hạn streams đồng thời, queue, frame/message size và subscriptions dài.

Spring Security có hỗ trợ RSocket security nhưng cần module/dependencies và configuration riêng. Thêm `spring-boot-starter-rsocket` **không tự bật xác thực tài khoản** hoặc áp mọi HTTP `SecurityWebFilterChain` lên RSocket TCP. Không dùng raw metadata như `X-User-Id` làm user identity mà chưa xác minh.

Với RSocket-over-WebSocket qua browser, `Origin`, cookie, TLS, reverse proxy và CORS/websocket upgrade policies còn có ý nghĩa. **Origin không phải bằng chứng user đã được authentication**; non-browser client có thể giả Origin. Các commands cần kiểm tra quyền theo nghiệp vụ.

Nếu dữ liệu có thông tin cá nhân, cần encryption in transit và storage protection phù hợp. RSocket over TCP **không được mặc định mã hóa** khi chạy theo cấu hình demo; loopback 127.0.0.1 chỉ giảm bề mặt tiếp cận trong lab, không thay thế TLS khi triển khai qua mạng.

## 16. RSocketRequester: quản lý client connection đúng cách

Trong Spring Boot 3.3, có bean `RSocketRequester.Builder` prototype auto-configured với codecs và các `RSocketConnectorConfigurer` phù hợp. Builder có trạng thái; không dùng cùng một builder mutable cho nhiều configurations khác nhau mà không tách rõ.

Có thể tạo requester dùng chung khi khởi động/khởi tạo bean:

```java
// Mảnh code minh họa trong @Configuration:
// Cần inject RSocketRequester.Builder builder.

@Bean(destroyMethod = "dispose")
RSocketRequester inventoryRequester(
        RSocketRequester.Builder builder) {
    return builder.tcp("inventory.internal.example", 7000);
}
```

Đây là **mảnh class config**, cần import `Bean` và `RSocketRequester`. `tcp(...)` tạo requester có thể sử dụng qua shared connection (connection may be established lazily). `destroyMethod="dispose"` đóng client khi Spring context shutdown. Trong production, cần externalize host/port/SSL settings và kiểm tra network policies.

**Không tạo một requester TCP mới mỗi lần một HTTP request vào app.** Điều đó làm tăng sockets/handshakes, giảm hiệu quả multiplexing và khó cleanup. Một requester cho mỗi downstream/trust domain thường dễ quản lý hơn.

**Không blocking trong reactive runtime**: lời gọi `retrieveMono(...)` trả Publisher. Trong WebFlux handler, return/compose Publisher, không `block()` trên Reactor Netty event-loop. Nếu có external SDK blocking, tách sang bounded worker có concurrency limit, nhưng đừng nhầm đó là non-blocking thật.

`data(Object)` và `data(Publisher, elementType)` là các overload khác nhau. Với `Flux<T>` request-channel, dùng overload có element type như `data(Flux.just("a","b"), String.class)` giúp framework biết rõ codec của từng phần tử.

## 17. HTTP mapping và RSocket route không thay thế nhau

Đặt cạnh nhau:

```java
// HTTP:
@GetMapping("/http/greet")
Mono<String> greet(@RequestParam String name) {
    return Mono.just("Hello, " + name + "!");
}

// RSocket:
@MessageMapping("demo.greet")
Mono<String> greetRSocket(@Payload String name) {
    return Mono.just("Hello, " + name + "!");
}
```

Đây là **mảnh code minh họa**, cần class controllers/imports tương ứng; project đầy đủ đã có ở mục 8. HTTP truyền name qua query string trong URL; RSocket truyền name trong data payload, route nằm ở metadata.

**Đừng tự suy từ RSocket route thành một HTTP API path**. Nếu muốn cùng một nghiệp vụ hỗ trợ cả hai, đặt xử lý chung vào service:
- HTTP controller chuyển request/response HTTP sang service.
- RSocket responder chuyển payload/metadata RSocket sang service.
- Service kiểm tra authorization/validation và thực thi business logic.
- Hai transport có error handling/auth/timeout/lifecycle riêng.

Sử dụng chung service tránh viết hai bộ logic, nhưng cần kiểm tra **hai transport có cùng security policy và validation semantics**. Một service dùng cho HTTP với role check ở web filter chưa chắc đã được bảo vệ nếu RSocket route gọi thẳng service mà không có method-level authorization.

## 18. Streaming từ dữ liệu thật: khi nào không nên dùng Flux.interval?

Trong demo, `Flux.range` tạo số phần tử hữu hạn. Ở production, nguồn có thể đến từ DB, Kafka, sensor callback hoặc tính toán nhiều bước. `Flux.interval` chỉ là nguồn định kỳ ở client/server memory, không phải message broker có persistence.

Ví dụ **minh họa** một request stream định kỳ có giới hạn:

```java
@MessageMapping("demo.clock")
Flux<String> clock(@Payload Integer count) {
    int bounded = Math.max(1, Math.min(count, 10));
    return Flux.interval(Duration.ofSeconds(1))
            .take(bounded)
            .map(i -> "second-" + i);
}
```

Đoạn này không nằm trong app chạy ở mục 8; muốn thêm cần import `Duration` và bảo đảm `count` không null trước khi Math.min. Đây là **mảnh demo**, không phải gợi ý triển khai hàng nghìn timers cho hàng nghìn clients mà không phân tích memory/scheduler.

**Production cần:**
- Backpressure-aware source hoặc bounded bridge từ nguồn hot/non-reactive.
- Giới hạn streams/user, data rate, outstanding messages và memory.
- Deadlines, heartbeat, cancel cleanup, retry/backoff và monitoring.
- Có nguồn sự thật durable nếu client phải nhận đầy đủ event sau reconnect.
- Không giữ Java entity/database connection theo một stream vô hạn mà không giải phóng.
- Khả năng khôi phục khi node chết; resumption chỉ khi cả hai phía triển khai đúng và có state.

Một broker như Kafka/RabbitMQ có chức năng lưu/định tuyến thông điệp riêng; RSocket phục vụ **giao tiếp trực tiếp giữa peers**, không thay thế toàn bộ các tính năng durability/consumer groups của message broker.

## 19. Deploy qua Docker/Kubernetes, proxy và scale-out

Các lưu ý cơ sở hạ tầng:

| Vấn đề | HTTP | RSocket |
|---|---|---|
| Exposure | Ingress HTTP/HTTPS thường có sẵn | TCP cần Service/L4 routing hoặc RSocket-over-WebSocket |
| Discovery | DNS/API gateway, HTTP service routes | DNS/port hoặc RSocket load balancing; không có HTTP route mặc định |
| Load balancing | Per HTTP request/connection tùy HTTP version | Connection có thể sống lâu; cần hiểu per-connection distribution |
| Pod restart | HTTP request lỗi có thể retry theo policy | Nhiều in-flight RSocket streams có thể lỗi cùng lúc |
| TLS | HTTPS, proxy termination | TLS TCP hoặc WSS; mỗi transport/config riêng |
| Metrics | HTTP status/URI template sẵn có | Cần metrics theo route, stream, connection, error |
| Scale-out | Stateless HTTP endpoints thường dễ hơn | Client cùng connection gắn một backend; cross-node broadcast cần broker |
| Browser | HTTP native | RSocket-over-WebSocket cần client library/protocol support |

Nếu một connection RSocket giữ nhiều logical requests, load balancer có thể phân phối **connection** tới một instance thay vì phân phối từng request như HTTP/1.1 qua gateway. Hệ thống cần thiết kế capacity dựa trên **active connections, streams per connection và per-node workload**, không chỉ số request mỗi giây.

Khi pod sắp drain, server có thể cần ngừng nhận connection mới, chờ in-flight work hợp lý và yêu cầu client reconnect với jitter. Tính năng retry ở client không bảo đảm không gây duplicate side effects; có idempotency keys cho lệnh ghi DB/tiền.

Nếu RSocket-over-WebSocket đi qua NGINX/Ingress, cần xác minh upgrade, keepalive/idle timeout, max frame size và TLS hostname/cert, không chỉ biết TCP port mở.

## 20. Quan sát, timeout và troubleshooting

### 20.1. Metrics nên theo dõi

- **Connection:** active RSocket connections, connect/setup failures, disconnect reasons, keepalive missed.
- **Per interaction:** route name, model type, stream duration, request rate, active streams, errors, cancel.
- **Backpressure/resource:** requested vs produced/delivered elements, queued bytes, pooled direct memory, frame size.
- **Resilience:** retry count, reconnect latency, timeouts, pod drain interruptions.
- **Security:** auth failure, rejected route, invalid payload, rate-limit reject, TLS failures.
- **Business:** processed/committed events tách khỏi “message sent” metrics.

Đặt metrics tags theo **route template ổn định**, không lấy raw payload, user ID hoặc token làm high-cardinality tags. Tracing qua metadata cần có instrumentation/context propagation và privacy controls phù hợp; RSocket không tự sinh distributed trace toàn hệ thống chỉ vì đã có request frames.

### 20.2. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| `curl localhost:7000` không nhận HTTP | Cổng 7000 là RSocket TCP, không phải HTTP | Dùng `RSocketRequester` hoặc RSocket CLI, không đổi URL |
| Kết nối bị từ chối | RSocket server chưa bind, sai port/address | Kiểm tra `spring.rsocket.server.port/address/transport` |
| `GET /demo.greet` 404 | `@MessageMapping` không tạo HTTP endpoint | Dùng RSocket route metadata qua requester |
| Request tới route đúng nhưng decode fail | MIME/codec hoặc DTO JSON/CBOR không tương thích | Kiểm tra RSocketStrategies, dataMimeType, encoded payload |
| `retrieveMono` không phát gì | Route sai, kiểu interaction không khớp, response không có payload | Kiểm tra handler signature, server logs, error frames |
| Fire-and-Forget không có business ACK | Protocol không có response payload | Dùng Request-Response hoặc explicit ACK workflow |
| Stream chạy mãi | Flux vô hạn, không giới hạn duration/element count | `take`/timeout/cancel, limits, cleanup |
| Slow client làm RAM tăng | Source hot không tôn trọng demand, queue không bounded | Backpressure-aware bridge/limits/drop/replay policy |
| Thread starvation | `block()`/JDBC sync trên Reactor event loop | Non-blocking drivers hoặc bounded offload |
| TLS handshake fail | Sai CA/SAN/certificate hoặc TLS chưa cấu hình | Cài trust material đúng, không trust-all |
| RSocket TCP chạy local nhưng lỗi qua Ingress | Ingress chỉ hỗ trợ HTTP, không TCP service | L4 routing hoặc RSocket-over-WebSocket |
| Browser WebSocket kết nối nhưng server lỗi protocol | Dùng raw WebSocket message, không phải RSocket frame | RSocket client library và SETUP đúng |
| Session mất sau pod restart | Không có durable state/resumption đúng | Reconnect/reauth/replay từ broker/DB |
| FNF bị xử lý trùng khi retry | Thông báo gửi không có business idempotency | Event ID và dedupe tại consumer |
| HTTP và RSocket cùng service nhưng quyền khác nhau | HTTP filter chain không tự bảo vệ RSocket TCP | RSocket Security và method-level policy |
| Client dùng URL `wss://` nhưng server vẫn TCP | Transport cấu hình không khớp | Chọn WebSocket transport và mapping-path |
| Hai streams độc lập cùng lỗi sau disconnect | Shared connection bị mất | Phân biệt stream cancellation với connection failure |
| Tests chỉ dùng `@WebFluxTest` mà không có RSocket server | Test slice không tạo đầy đủ RSocket infrastructure | Dùng `@SpringBootTest` với RSocket port thật |

**Không kết luận RSocket có lỗi chỉ từ một HTTP status.** Với TCP, xem các RSocket error frames, application logs và Reactor signals. Khi chạy over WebSocket, HTTP status như `101` chỉ là bước upgrade, không phải response status của từng RSocket business request.

## 21. Checklist thiết kế giao thức và vận hành

- [ ] Nhu cầu có thật sự cần full duplex/streaming hay HTTP/SSE đã đủ?
- [ ] Đã chọn interaction model đúng cardinality (0/1/many) chưa?
- [ ] Có tách route metadata, data payload và HTTP URL rõ ràng không?
- [ ] HTTP status và RSocket error semantics được ánh xạ riêng thế nào?
- [ ] Đã kiểm tra codecs/MIME và version của DTO giữa peers chưa?
- [ ] RSocket TCP/WebSocket transport, port, mapping-path và TLS được cấu hình khớp?
- [ ] Có xác thực connection và authorization theo route/command?
- [ ] Source reactive có tôn trọng demand? Queue/sink có giới hạn?
- [ ] Có timeout/cancel/cleanup rõ cho từng stream và connection?
- [ ] Fire-and-Forget có chấp nhận không ACK, hay cần business confirmation?
- [ ] Retry có idempotency key và giới hạn attempt/backoff?
- [ ] Requester được tái sử dụng, dispose đúng lifecycle, không tạo connection/request vô tội vạ?
- [ ] Đã test cả bốn models bằng RSocket client thật và HTTP baseline?
- [ ] Có đo active connections, streams, errors, cancels, queue bytes, memory?
- [ ] Có kế hoạch reconnect/resume/replay khi instance/network lỗi?
- [ ] Browser/gateway có RSocket library/proxy support thực tế?
- [ ] Security policies của HTTP và RSocket độc lập nhưng nhất quán với nghiệp vụ?

## 22. Câu hỏi tự kiểm tra

**1. RSocket Request-Response có khác HTTP ở chỗ nào?**  
Cùng có ý tưởng một yêu cầu một kết quả, nhưng RSocket route qua metadata, trao đổi payload/errors theo RSocket frames trên shared connection và không có HTTP method/status cho mỗi interaction.

**2. HTTP/2 có multiplex không?**  
Có. Không thể gọi multiplexing là đặc quyền duy nhất của RSocket. RSocket khác ở bốn models cùng Reactive Streams demand được biểu diễn ở protocol.

**3. Fire-and-Forget `send().block()` thành công có nghĩa message đã được commit vào DB?**  
Không. Theo contract chỉ xác nhận đã gửi message; cần ACK ở cấp business hoặc mô hình durable nếu yêu cầu.

**4. Request-Stream khác Request-Channel thế nào?**  
Request-Stream: một request, nhiều responses. Channel: hai bên có thể gửi streams messages trong cùng interaction.

**5. `@MessageMapping("demo.greet")` có nhận HTTP `GET /demo.greet` không?**  
Không, đó là RSocket route, không phải HTTP path/method.

**6. Tại sao `curl http://localhost:7000` không gọi được RSocket TCP?**  
Cổng RSocket TCP nói binary RSocket protocol, không hiểu HTTP request line/headers.

**7. `RSocketRequester.Builder.tcp` có cần `block()` lúc tạo không?**  
Với Spring Framework 6.1, `tcp(host,port)` trả `RSocketRequester` có thể dùng ngay và kết nối được thiết lập theo cơ chế lazy/shared. API `connectTcp` cũ trả Mono đã deprecated.

**8. Có thể bật `spring.rsocket.server.transport=websocket` rồi gửi raw JSON qua browser WebSocket không?**  
Không, WebSocket chỉ là transport; payload bên trong vẫn phải theo RSocket protocol.

**9. RSocket có thay Kafka hoặc RabbitMQ lưu dữ liệu bền không?**  
Không. Nó là giao thức giao tiếp giữa peers; durable broker, replay và consumer groups cần hệ thống/thiết kế riêng.

**10. Cancel stream có rollback tác vụ DB không?**  
Không tự động. Cancellation chỉ báo upstream ngừng nếu có thể; side effects đã commit cần chính sách transaction/idempotency riêng.

**11. Vì sao một proxy HTTP thông thường không route RSocket TCP theo path?**  
RSocket TCP không có HTTP URL/method. Cần L4 forwarding hoặc RSocket-over-WebSocket với protocol support.

**12. Nếu Spring Security bảo vệ HTTP endpoints, TCP RSocket có an toàn chưa?**  
Chưa. RSocket TCP có handshake/security policy riêng và cần bảo vệ transport, authentication/authorization, validation và network ACL.

## 23. Tài liệu chính thức và đọc thêm

1. Spring Framework — **RSocket protocol overview, RSocketRequester, Annotated Responders**, 4 interaction types, SETUP và REQUEST_N: https://docs.spring.io/spring-framework/reference/rsocket.html
2. Spring Boot 3.3 — **RSocket integration** (TCP/WebSocket server, messaging, requester): https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
3. Spring Boot 3.3 — **Common Application Properties**, `spring.rsocket.server.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
4. Spring Framework 6.1 — **RSocketRequester.Builder** Javadoc, `tcp`, `websocket` và deprecated `connectTcp`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
5. Spring Boot 3.3 — **LocalRSocketServerPort** cho integration tests: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html
6. Spring Project blog — **Getting Started with RSocket: Spring Boot Server**: https://spring.io/blog/2020/03/02/getting-started-with-rsocket-spring-boot-server/
7. Spring Project blog — **Testing Spring Boot Responders**: https://spring.io/blog/2020/05/25/getting-started-with-rsocket-testing-spring-boot-responders/
8. RSocket Protocol website/specification: https://rsocket.io/
9. Reactive Streams Specification, request(n)/backpressure: https://www.reactive-streams.org/

**Kết luận:** HTTP request–response vẫn là lựa chọn tốt cho phần lớn API công khai. RSocket mang lại một giao thức message-oriented hỗ trợ Request-Response, Fire-and-Forget, Request-Stream, Request-Channel trên connection có multiplexing và application-level backpressure. Trong Spring Boot, dùng `spring-boot-starter-rsocket`, `@MessageMapping` và `RSocketRequester` để hiện thực bốn mô hình, nhưng phải tự thiết kế security, timeout, durability, retry/idempotency và vận hành transport khi đưa lên production.