# Backpressure ở mức giao thức và khác biệt với HTTP

**Module:** Spring Framework – reactive  
**Chủ đề cha:** RSocket  
**Trọng tâm:** Cách RSocket truyền nhu cầu tiêu thụ qua mạng bằng `REQUEST_N`, khác biệt với điều tiết luồng ở TCP/HTTP và cách sử dụng với Spring Reactor.

## 1. Bài toán: bên gửi nhanh hơn bên nhận

Hãy hình dung service A tạo 10.000 sự kiện/giây, trong khi service B chỉ xử lý 100 sự kiện/giây. Nếu A gửi liên tục không quan tâm B, dữ liệu sẽ tích tụ ở hàng đợi, tăng bộ nhớ, độ trễ và cuối cùng có thể làm ứng dụng hết tài nguyên. **Backpressure** là cơ chế để nơi nhận bày tỏ lượng dữ liệu hiện có thể tiếp nhận và để nơi gửi điều chỉnh theo giới hạn ấy.

Trong Reactive Streams, `Subscriber` không chỉ nhận `onNext(T)` mà còn có thể gọi `Subscription.request(n)`, tức yêu cầu thêm `n` phần tử. `Publisher` tuân thủ demand sẽ không phát vượt quá số phần tử chưa được cấp phép. Ví dụ, subscriber yêu cầu 2 item, tiêu thụ xong 2 item, rồi yêu cầu tiếp 3 item.

**Điểm khác biệt chính:**

- **Project Reactor (`Flux`/`Mono`) trong cùng JVM:** `request(n)` là tín hiệu giữa các thành phần reactive trong một process, có thể đi ngược qua chuỗi operator.
- **RSocket:** biến nhu cầu đó thành **tín hiệu trên giao thức** (`REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_N`), cho phép backpressure đi qua kết nối mạng giữa requester và responder.
- **HTTP:** HTTP/1.1 không có chuẩn yêu cầu thêm `n` đối tượng ứng dụng; HTTP/2 có flow control nhưng cấp tín dụng theo **byte** qua `WINDOW_UPDATE`, không theo số item Reactor.

Do đó, không nên nói “HTTP không có flow control”. Điều chính xác là **HTTP có cơ chế điều tiết network/byte tùy phiên bản và transport, còn RSocket đưa demand theo phần tử vào protocol của request stream/channel**.

## 2. RSocket là gì và backpressure đặt ở đâu?

RSocket là giao thức nhị phân, bất đồng bộ, hỗ trợ multiplex nhiều stream và giao tiếp hai chiều trên một kết nối transport như TCP hoặc WebSocket. Sau khi kết nối được tạo và trao đổi `SETUP`, hai phía có thể gửi request cho nhau; vì thế giao thức dùng khái niệm **requester** (bên bắt đầu một interaction) và **responder** (bên xử lý interaction), không đồng nhất cố định với client/server TCP.

Bốn interaction model:

| Interaction | Hướng trao đổi | Kết quả | Backpressure theo số phần tử |
|---|---|---|---|
| Request–Response | Một request, tối đa một response | `Mono<T>` | Không cần cửa sổ request-N nhiều item cho response đơn |
| Fire-and-Forget | Một chiều, không có response body | `Mono<Void>` ở API gửi | Không có demand response theo từng item |
| Request–Stream | Một request, nhiều response | `Flux<T>` | Có, requester cấp tín dụng cho response |
| Request–Channel | Stream dữ liệu hai chiều | `Flux<T>` đầu vào và `Flux<R>` đầu ra | Có, hai hướng có tín dụng độc lập |

RSocket không tự đảm bảo mọi request được xử lý thành công: Fire-and-Forget là best-effort, lỗi ứng dụng vẫn có thể xảy ra; connection có thể đứt và resource có thể cần cleanup.

**Backpressure không phải tải đều theo thời gian.** Demand n chỉ nói số phần tử còn có thể phát, không nói gửi một phần tử mỗi 100 ms hay kiểm soát tổng số byte. Một item 1 KiB và một item 10 MiB đều tiêu thụ một đơn vị demand ở tầng Reactive Streams, dù vận chuyển có thể cần nhiều frame/fragment.

## 3. Từ request(n) tới REQUEST_N trên dây

RSocket sử dụng **credit-based flow control**: bên nhận cấp tín dụng theo số `PAYLOAD` có thể mang sự kiện `onNext`; bên gửi chỉ được phát thêm trong lượng tín dụng được cấp.

Đặc tả quy định:

- `REQUEST_STREAM` mang trường `Initial Request N`: số item response ban đầu requester cho phép responder gửi.
- `REQUEST_CHANNEL` cũng mang `Initial Request N` cho **luồng response**; phía responder dùng `REQUEST_N` để cấp tín dụng gửi tiếp cho **luồng request** của requester.
- `REQUEST_N` là frame cấp thêm tín dụng cho stream tương ứng sau khi interaction đã bắt đầu.
- Giá trị `N` phải dương; trường protocol là 31-bit unsigned, tối đa `2^31 - 1` cho mỗi giá trị.
- Credit được **cộng dồn**: `request(3)` rồi `request(2)` tạo tổng quyền phát 5 item, trừ những item đã gửi.
- `PAYLOAD` mang cờ `NEXT` được xem là một item có thể tiêu thụ tín dụng. Frame chỉ báo `COMPLETE` không phải một item mới.

Ví dụ nguyên lý request-stream:

```text
Requester B                                  Responder A
    |                                              |
    | REQUEST_STREAM(initialRequestN=2) ---------->|
    |                                              |
    |<------------------------------- PAYLOAD #1   |  credit: 1
    |<------------------------------- PAYLOAD #2   |  credit: 0
    |                                              |  không phát #3
    | REQUEST_N(N=3) ------------------------------>|
    |                                              |
    |<------------------------------- PAYLOAD #3   |  credit: 2
    |<------------------------------- PAYLOAD #4   |  credit: 1
    |<---------------- PAYLOAD #5 + COMPLETE        |  kết thúc
    |                                              |
```

Ví dụ mô tả logic chuẩn. Trong ứng dụng dùng thư viện, các operator có thể **prefetch**, cộng gộp hoặc chia nhỏ demand, và implementation có thể chọn initial request-N lớn hơn yêu cầu vừa thấy ở một subscriber ngoài cùng. **Không khẳng định** hai lần gọi `thenRequest(2)` ở test sẽ tạo chính xác hai frame có giá trị N=2 trên dây.

### 3.1. Vì sao có initial request N?

Nếu phía responder chưa được cấp bất kỳ tín dụng nào thì không thể phát response item. Để tránh phải gửi một frame request rồi gửi thêm frame credit riêng trước item đầu tiên, `REQUEST_STREAM` và `REQUEST_CHANNEL` gắn tín dụng ban đầu ngay trong frame mở interaction. Khi tín dụng cạn, requester gửi `REQUEST_N` để mở rộng cửa sổ.

RSocket chỉ quy định semantics tín dụng và frame, không áp đặt thuật toán khi nào nên replenishment; việc gọi request theo lô hay từng item là quyết định của subscriber và thư viện.

### 3.2. Credit không phải byte limit hoặc giới hạn bộ nhớ tuyệt đối

Nếu được phép phát 10 item, mỗi item có thể rất lớn. Cần kết hợp:

- Giới hạn kích thước payload/fragment và codec.
- Giới hạn số stream đồng thời và số request chưa hoàn tất.
- Pool/resource quotas và thời hạn xử lý.
- Kiểm soát producer/hot source không tuân thủ demand.
- Metrics về backlog, pending requests, latency và bộ nhớ.

Backpressure giúp ngăn dữ liệu phát vượt nhu cầu, nhưng không thay thế capacity planning.

## 4. Request–Stream: điều tiết response từ requester

Trong request-stream, phía requester gửi **một** request mở stream; phía responder trả về nhiều item.

Ví dụ Spring:

```java
@Controller
class NumbersResponder {

    @MessageMapping("numbers.stream")
    public Flux<Integer> numbers(Integer count) {
        return Flux.range(1, count);
    }
}
```

Phía requester:

```java
Flux<Integer> numbers = requester.route("numbers.stream")
        .data(5)
        .retrieveFlux(Integer.class);
```

`retrieveFlux` thể hiện response nhiều giá trị, tương ứng request-stream khi input là một item. `Flux.range` tuân thủ Reactive Streams demand. Nếu requester chưa cho phép thêm item, implementation RSocket sẽ điều tiết lượng response chuyển qua kết nối.

Phân biệt hai lớp:

1. `Flux.range` là publisher tạo số trong process responder.
2. RSocket protocol trao đổi tín dụng để điều khiển dữ liệu giữa hai process.

Khi downstream đổi nhu cầu, RSocket Java cầu nối các tín hiệu để producer không phải tự thao tác với frame `REQUEST_N`.

## 5. Request–Channel: hai hướng backpressure độc lập

Request-channel có hai luồng:

- Requester → Responder: các item request sau thông điệp đầu tiên.
- Responder → Requester: các item response.

Mỗi hướng phải tuân thủ demand từ phía **đang nhận** hướng ấy. Đây không phải một bộ đếm tín dụng chung.

```text
      REQUESTER                                    RESPONDER
   request Flux ---> REQUEST_CHANNEL + PAYLOAD ---> handle input Flux
                  <--- REQUEST_N for input items --
                  ----- next PAYLOAD if credited -->
                  <---- response PAYLOAD if credited
   response Flux  <--- response stream ----------------
   response demand -> REQUEST_N for response -------->
```

Theo đặc tả, `REQUEST_CHANNEL` mang initial request-N cho output response, còn responder phải gửi `REQUEST_N` để cho phép requester gửi thêm request `PAYLOAD` sau frame đầu tiên. Trong implementation, việc prefetch hoặc buffering có thể khiến quan sát từng frame không trùng từng lời gọi `request(n)` ở ứng dụng.

Ví dụ responder:

```java
@Controller
class TransformResponder {

    @MessageMapping("labels.channel")
    public Flux<String> transform(Flux<Integer> input) {
        return input.map(number -> "label-" + number);
    }
}
```

Requester:

```java
Flux<Integer> input = Flux.range(1, 5);

Flux<String> output = requester
        .route("labels.channel")
        .data(input, Integer.class)
        .retrieveFlux(String.class);
```

Đây là snippet dùng Spring `RSocketRequester`; để hoạt động cần RSocket server/client đã kết nối và codecs thích hợp. `data(Publisher, elementClass)` mô tả kiểu của mỗi item request. Vì đầu vào multi-value và đầu ra multi-value, Spring chọn channel interaction.

**Sai lầm phổ biến:** xem request-channel như một WebSocket chat chỉ có “send” và “receive”. WebSocket tự nó không chuẩn hóa tín dụng `request(n)` theo thông điệp ứng dụng; RSocket chạy trên WebSocket thì lớp RSocket mới cung cấp semantics đó.

## 6. Request–Response và Fire-and-Forget không giống stream

**Request–Response** nhận tối đa một response. Không cần replenishment `REQUEST_N` như request-stream. Subscriber vẫn có thể hủy interaction nếu không muốn chờ kết quả.

**Fire-and-Forget** gửi một message mà không có response payload để requester điều tiết. Việc lời gọi gửi hoàn tất không chứng minh responder đã thực thi nghiệp vụ hoặc commit dữ liệu.

```java
Mono<Receipt> receipt = requester.route("orders.create")
        .data(command)
        .retrieveMono(Receipt.class);

Mono<Void> acknowledgement = requester.route("telemetry.oneway")
        .data(event)
        .send();
```

Hai snippet giả định DTO và route tồn tại. Đối với lệnh có side effect quan trọng, không nhầm fire-and-forget với giao nhận bền vững. Nếu cần bảo đảm xử lý, idempotency, retry, acknowledgement nghiệp vụ hoặc queue bền vững phải được thiết kế riêng.

## 7. Cancellation và terminal signal ở cấp stream

Reactive Streams phân biệt:

- `onComplete`: stream đã hoàn tất.
- `onError`: stream thất bại.
- `Subscription.cancel()`: subscriber không còn muốn nhận item.

RSocket có các frame `CANCEL` và `ERROR` tương ứng với lifecycle ở cấp interaction. Nếu requester hủy request-stream trước khi nhận đủ item, responder cần ngừng phát theo contract và giải phóng tài nguyên gắn với subscription.

Ví dụ:

```java
return repository.streamByCategory(category)
        .doOnRequest(n -> metrics.recordDemand(n))
        .doOnCancel(() -> metrics.incrementCancelled())
        .doFinally(signal -> metrics.recordTerminal(signal.name()));
```

`doOnCancel` dùng để quan sát hủy; `doFinally` quan sát cả complete, error, cancel. Nếu publisher giữ cursor/connection, hãy dùng `Flux.using` hoặc `Flux.usingWhen` để cleanup theo subscription lifecycle, không chỉ `doOnError`.

**Cancellation không tự rollback side effect.** Database query hoặc network call đã xảy ra có thể không được hoàn tác. Nếu producer không thể dừng ngay (legacy blocking call hoặc hot source), tín hiệu cancel vẫn cần được xử lý và resource phải có timeout/cleanup riêng.

## 8. RSocket và HTTP khác nhau ở tầng nào?

Để so sánh công bằng, phải tách **application item**, **protocol stream** và **network bytes**:

| Tiêu chí | RSocket | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|---|
| Semantics request | Bốn interaction models | Request–response truyền thống | Request–response, nhiều stream multiplex | Request–response qua QUIC |
| Dữ liệu nhiều item | `REQUEST_STREAM`/`REQUEST_CHANNEL` | Chunked/stream response có thể dùng | Response DATA trên HTTP/2 stream | Response DATA trên QUIC stream |
| Tín dụng theo **item** | Có, `Initial Request N` / `REQUEST_N` | Không chuẩn hóa ở HTTP | Không chuẩn hóa ở HTTP/2 | Không chuẩn hóa ở HTTP/3 |
| Flow control theo **byte** | Do transport bên dưới | TCP receive window | `WINDOW_UPDATE` theo byte ở stream và connection | QUIC flow control ở stream và connection |
| Hai chiều trên một connection | Có, protocol symmetric; channel hai hướng | Không có request-channel chuẩn | Multiplex nhiều HTTP stream, semantics request/response | Multiplex qua QUIC, semantics HTTP |
| Hủy tương tác | `CANCEL` | Ngắt/đóng kết nối hoặc logic ứng dụng | `RST_STREAM` và hủy request tùy tình huống | Cancel/reset stream ở QUIC/HTTP semantics |
| Bản chất backpressure | Nhu cầu số thông điệp ứng dụng | Bộ đệm và network flow control | Credit byte, hop-by-hop | Credit byte ở QUIC và transport |

Bảng mô tả **cơ chế chuẩn**, không phủ nhận thư viện có thể triển khai điều tiết bổ sung. WebFlux có thể truyền backpressure từ subscriber xuống socket ở một số đường xử lý và hỗ trợ trả `Flux` trên HTTP, nhưng HTTP không quy định frame `REQUEST_N` theo từng object nghiệp vụ.

### 8.1. HTTP/1.1 và TCP

HTTP/1.1 có thể gửi response lớn theo chunked transfer encoding hoặc content-length, và ứng dụng có thể phát từng chunk. Khi phía nhận chậm, TCP receive window, socket write readiness và buffering ảnh hưởng tốc độ phía gửi.

Tuy nhiên TCP chỉ biết byte. TCP không biết JSON object A hay event B. Các layer phía trên phải quyết định cách parse và giới hạn queue. TCP flow control không truyền trực tiếp yêu cầu “cho tôi đúng 3 bản ghi tiếp theo”.

Nếu server tạo dữ liệu nhanh hơn khả năng ghi của socket, framework có thể giảm demand lên publisher trong process. Nhưng đây là cách implementation nối local Reactive Streams với transport, không phải một điều khoản chuẩn HTTP cho credit theo application item.

### 8.2. HTTP/2: WINDOW_UPDATE không phải REQUEST_N

RFC 9113 `5.2` và `6.9` định nghĩa HTTP/2 flow control theo **octet/byte**:

- Có cửa sổ riêng cho từng HTTP/2 stream.
- Có cửa sổ cho toàn connection.
- Receiver gửi `WINDOW_UPDATE` để tăng số byte được phép truyền.
- Flow control là **hop-by-hop**: intermediary có thể nhận và cấp cửa sổ riêng với mỗi phía, không tự chuyển tiếp credit end-to-end.
- Chỉ `DATA` frames bị điều tiết bởi flow control được quy định trong RFC này.
- Cửa sổ mặc định ban đầu là 65.535 byte (có thể được điều chỉnh theo protocol).

Ví dụ: client cấp thêm 32 KiB, server được gửi thêm tối đa 32 KiB `DATA` theo cửa sổ liên quan, không phải đúng 32 JSON object. Một item ứng dụng có thể trải nhiều DATA frame và ngược lại một DATA frame có thể chứa nhiều item.

RSocket `REQUEST_N(3)` có ý nghĩa khác: receiver cho phép thêm 3 message/`onNext` của RSocket stream, bất kể mỗi message sau đó cần bao nhiêu frame/byte để truyền.

**Không nói HTTP/2 không có backpressure.** Nó có flow control ở tầng transport/framing, nhưng không chuẩn hóa Reactive Streams `request(n)` ở tầng message nghiệp vụ.

### 8.3. HTTP/3: QUIC flow control là byte-based

HTTP/3 vận chuyển HTTP trên QUIC. QUIC có cơ chế flow control theo byte tại connection và stream, với tín dụng như `MAX_DATA`/`MAX_STREAM_DATA`. Đây không phải tín dụng theo số JSON object hoặc phần tử Reactor.

HTTP/3 không tự biến endpoint thành RSocket request-stream. Nếu ứng dụng cần protocol-level item demand, phải có semantics bổ sung ở tầng ứng dụng hoặc dùng protocol như RSocket.

### 8.4. SSE, NDJSON, gRPC và WebSocket

- **SSE trên HTTP:** response dài gồm các event `text/event-stream`. Browser `EventSource` không có frame chuẩn gửi `request(n)` cho server.
- **NDJSON:** nhiều JSON object phân tách theo dòng trong một response; client có thể decode thành `Flux<T>`, nhưng format dòng không tạo credit ứng dụng.
- **gRPC streaming:** dùng HTTP/2 và có cơ chế flow control, nhưng không đồng nghĩa HTTP/2 `WINDOW_UPDATE` đã trở thành Reactive Streams item request-N. Cần xét semantics của gRPC library và ứng dụng.
- **WebSocket:** hỗ trợ truyền message hai chiều; bản thân WebSocket không định nghĩa `REQUEST_N`. RSocket có thể chạy **trên WebSocket** và lúc đó lớp RSocket cung cấp credit theo message.

Không chọn transport chỉ vì “WebSocket hai chiều” hoặc “HTTP/2 multiplex”; yêu cầu của ứng dụng là streaming một chiều, song công, tín dụng theo message, compatibility với browser/gateway, authentication hay observability?

## 9. Backpressure đi qua nhiều lớp trong hệ thống thực

Một pipeline có thể chứa:

```text
Database / Broker
       |
       v
Publisher trong server  -- Reactive Streams request(n) -->
       |
       v
RSocket responder
       |
       |  REQUEST_N / PAYLOAD trên mạng
       v
RSocket requester
       |
       v
Reactor operators (map / filter / flatMap)
       |
       v
Subscriber cuối cùng
```

Thư viện có thể truyền demand ngược từ subscriber cuối qua network tới source, nhưng end-to-end backpressure chỉ hiệu quả khi **tất cả các đoạn** tôn trọng demand. Các điểm có thể phá vỡ cơ chế:

1. Source hot tự phát bất kể subscriber đang cần bao nhiêu.
2. Message broker đẩy vào một queue không giới hạn.
3. `onBackpressureBuffer` cho phép tích lũy quá nhiều item.
4. `publishOn` hoặc `flatMap` tạo prefetch/inner subscriptions khác với nhu cầu quan sát bên ngoài.
5. API blocking đang đọc toàn bộ result set trước khi tạo Flux.
6. Codec aggregate body lớn thành một object trước khi publish.
7. Producer tự gọi `subscribe()` và tách khỏi lifecycle của request.

RSocket không thể biến nguồn hot không hợp tác thành cold publisher tự động. Với dữ liệu không thể chậm lại, cần policy rõ: drop, latest, bounded buffer, error, sampling hoặc queue bền vững có quota.

## 10. Prefetch, limitRate và số REQUEST_N thực tế

Reactor có nhiều operator điều chỉnh demand. Ví dụ:

```java
Flux<Event> processed = requester.route("events.live")
        .retrieveFlux(Event.class)
        .limitRate(16)
        .concatMap(event -> saveEvent(event));
```

`limitRate(16)` làm thay đổi cách operator request upstream theo lô; `concatMap` xử lý tuần tự. Nhưng tín hiệu chạy qua RSocketRequester, codecs và operator nội bộ. Không nên suy đoán rằng từng lần `request(n)` ở subscriber trực tiếp tương ứng một frame `REQUEST_N(N=n)`.

`doOnRequest` là công cụ quan sát demand **tại vị trí đặt operator**:

```java
return Flux.range(1, 20)
        .doOnRequest(n ->
                log.info("source has received demand={}", n));
```

Log này không phải packet capture và không chứng minh frame wire-level. Muốn kiểm tra credit mạng thật, cần instrument/interceptor ở RSocket transport hoặc packet/frame tracing phù hợp, đồng thời đối chiếu với spec và version thư viện.

### 10.1. Không mặc định request(long.MAX_VALUE) giống số nguyên RSocket

Reactive Streams trong JVM cho phép `Subscription.request(long)` và dùng `Long.MAX_VALUE` để biểu thị demand không giới hạn. Trong khi đó, frame `REQUEST_N` của RSocket có trường 31-bit dương. Thư viện có trách nhiệm chuyển demand lớn thành biểu diễn hợp lệ ở wire level.

Không tự ép `long` demand thành `int` bằng cast rồi gửi frame; có thể overflow hoặc tạo N=0 không hợp lệ.

## 11. Chương trình Java 17+ chạy được: Spring Boot RSocket + StepVerifier

Ví dụ dưới đây dùng Spring Boot 3.5.16, Java 17 và RSocket TCP. Server cung cấp route `numbers.stream` trả các số từ 1 đến 5. Integration test tạo client thật, gọi route bằng `RSocketRequester`, rồi dùng `StepVerifier` chủ động yêu cầu từng đợt. Một test riêng quan sát demand local của Reactor để phân biệt nó với số credit frame trên mạng.

Cấu trúc:

```text
rsocket-backpressure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/RsocketBackpressureApplication.java
    │   ├── java/demo/NumbersResponder.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/RsocketBackpressureIntegrationTest.java
```

### 11.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>rsocket-backpressure-demo</artifactId>
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

`spring-boot-starter-rsocket` cung cấp Spring Messaging RSocket, RSocket Java, Reactor Netty và codecs do Boot quản lý. `reactor-test` chỉ cần cho test. Không cần `spring-boot-starter-webflux` nếu ứng dụng chỉ phục vụ RSocket TCP và không có HTTP endpoint.

### 11.2. application.properties

```properties
spring.application.name=rsocket-backpressure-demo
spring.main.web-application-type=none
spring.rsocket.server.address=127.0.0.1
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

RSocket TCP server chạy độc lập trên cổng 7000. Cấu hình `web-application-type=none` nói rõ project không cần HTTP web server; RSocket server vẫn được auto-configure bằng `spring.rsocket.server.port`.

Vì test dùng cổng cố định, hãy bảo đảm 7000 chưa có service khác chiếm. Trong hệ thống CI chạy song song, có thể dùng random port và lấy cổng bind thực tế qua hạ tầng test thay vì dùng giá trị cố định.

### 11.3. RsocketBackpressureApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RsocketBackpressureApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RsocketBackpressureApplication.class, args);
    }
}
```

### 11.4. NumbersResponder.java

```java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;

@Controller
public class NumbersResponder {

    @MessageMapping("numbers.stream")
    public Flux<Integer> numbers(Integer count) {
        return Flux.range(1, count)
                .doOnRequest(n ->
                        System.out.println("source demand=" + n))
                .doOnCancel(() ->
                        System.out.println("stream cancelled"));
    }
}
```

`@MessageMapping` khai báo route RSocket, không phải `@GetMapping` HTTP. Kết quả là `Flux<Integer>`; với payload đầu vào đơn và output nhiều item, Spring dùng request-stream.

`Flux.range` tạo số theo demand. `doOnRequest` chỉ log demand mà publisher nguồn quan sát được; không nhất thiết đúng số `REQUEST_N` frames thực tế. `doOnCancel` chạy khi subscription bị hủy.

### 11.5. RsocketBackpressureIntegrationTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class RsocketBackpressureIntegrationTest {

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Test
    void requestStreamHonorsDownstreamDemand() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", 7000);

        try {
            Flux<Integer> response = requester
                    .route("numbers.stream")
                    .data(5)
                    .retrieveFlux(Integer.class);

            StepVerifier.create(response, 0)
                    .thenRequest(2)
                    .expectNext(1, 2)
                    .thenRequest(3)
                    .expectNext(3, 4, 5)
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.rsocket().dispose();
        }
    }

    @Test
    void localReactiveStreamsDemandCanBeMeasured() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(requested::addAndGet);

        StepVerifier.create(source, 0)
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .expectComplete()
                .verify(Duration.ofSeconds(3));

        assertThat(requested).hasValue(5);
    }
}
```

Chạy test với JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** Maven kết thúc với exit code 0, hai test thành công, không có test failure. Console từ `doOnRequest` phía server có thể hiển thị các số khác 2 và 3 vì implementation RSocket có thể prefetch/replenish theo policy nội bộ. Đừng dùng số lần log từ server làm expected stdout cố định.

Nếu chỉ muốn khởi động server, dùng:

```bash
mvn spring-boot:run
```

Ứng dụng mở cổng RSocket TCP 7000 chứ không có HTTP `GET /numbers.stream`. Muốn gọi route, dùng `RSocketRequester` hoặc client RSocket tương thích, không dùng `curl http://localhost:7000`.

### 11.6. Test chứng minh điều gì và chưa chứng minh điều gì?

Test mạng chứng minh caller có thể subscribe với demand ban đầu bằng 0, tăng nhu cầu qua `thenRequest` và nhận đủ các item theo thứ tự. Nó kiểm tra giao diện Reactive Streams và tương tác RSocket thực, nhưng **không khẳng định frame capture thực tế là REQUEST_N(2) rồi REQUEST_N(3)**.

Test local với `Flux.range` kiểm tra việc một publisher tuân thủ demand và tổng request mà `doOnRequest` quan sát được là 5. Vì không qua RSocket, test local không nói gì về wire frames.

Để xác minh chính xác frame protocol, phải dùng RSocket frame interceptor/instrumentation hoặc một integration test phù hợp tầng transport rồi đối chiếu với đặc tả. Không coi một `StepVerifier` đơn thuần là packet analyzer.

## 12. Khi kết hợp RSocket với WebFlux HTTP

Một ứng dụng có thể có cả hai endpoint:

- HTTP WebFlux cho browser, REST, SSE hoặc NDJSON.
- RSocket để giao tiếp service-to-service hoặc stream hai chiều có tín dụng theo item.

Cấu hình Boot khi muốn RSocket chạy qua WebSocket trong WebFlux server:

```properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
```

Đây là cấu hình cho RSocket-over-WebSocket gắn vào web server Reactor Netty; ứng dụng cần WebFlux server phù hợp. Với RSocket TCP server riêng, đặt `spring.rsocket.server.port` và `transport=tcp`.

Không nhầm một WebSocket endpoint tùy ý với RSocket endpoint. RSocket-over-WebSocket vẫn dùng `SETUP`, `REQUEST_STREAM`, `REQUEST_N` và các frame RSocket; WebSocket thuần không tự sinh các frame đó.

Nếu ứng dụng cần expose cùng dữ liệu qua HTTP và RSocket, chia sẻ **reactive service** chứ không cố ép hai protocol dùng cùng kiểu response:

```java
@Service
class EventService {
    public Flux<Event> streamEvents() {
        return repository.findEvents();
    }
}
```

HTTP controller có thể serialize `Flux<Event>` thành NDJSON/SSE; RSocket responder trả `Flux<Event>` qua route. Source sẽ nhận demand khác nhau tùy subscriber, operator và transport. Đừng giả định cùng service đồng nghĩa HTTP cũng được protocol-level `REQUEST_N`.

## 13. RSocket LEASE khác với request-N

Đặc tả còn định nghĩa `LEASE` để giới hạn **số interaction mới** mà requester được phép khởi tạo trong một khoảng thời gian (TTL). Đây là công cụ kiểm soát khả năng chấp nhận request ở cấp connection/request admission.

Phân biệt:

| Cơ chế | Đối tượng được giới hạn | Ví dụ |
|---|---|---|
| `REQUEST_N` | Số item response/request-channel trong một stream | Cho phép 3 event tiếp theo |
| `LEASE` | Số interaction mới được mở trong TTL | Cho phép mở thêm 10 request trong 5 giây |
| Connection pool/quota | Số connection hoặc request đang thực thi | Tối đa 50 connection |
| Rate limiter | Số operation theo chính sách thời gian | 100 request/giây |
| Transport flow control | Số byte có thể truyền | HTTP/2 WINDOW_UPDATE 32 KiB |

`LEASE` không thay `REQUEST_N`. Một requester có thể được phép mở một request-stream theo lease nhưng vẫn chỉ có 2 tín dụng response item. Các implementation có thể không bật leasing mặc định; kiểm tra cấu hình/version cụ thể.

## 14. Giới hạn: backpressure không giải quyết mọi vấn đề

RSocket backpressure có ý nghĩa khi ứng dụng có producer tuân thủ demand. Nó **không tự bảo đảm**:

- Độ trễ đầu-cuối luôn thấp.
- Queue trong broker/database tự biến mất.
- Payload lớn không làm cạn bộ nhớ.
- Side effect được rollback khi client hủy.
- Các stream tự động phân bổ CPU và connection công bằng.
- Một hot producer sẽ ngừng tạo event khi subscriber chậm.
- Stream bị treo do thiếu demand sẽ tự timeout.
- Kết nối đứt có thể resume thành công trong mọi trường hợp.

RSocket có `KEEPALIVE` để hỗ trợ phát hiện connection không hoạt động và có tùy chọn `RESUME` khi implementation/protocol extension cho phép. Nhưng keepalive, resume và request-N là các cơ chế khác nhau. Không coi resume là exactly-once processing hoặc durable message queue.

Nếu không nhận thêm `REQUEST_N`, một stream có thể dừng gửi dữ liệu chờ demand. Đặc tả không bắt buộc timeout riêng chỉ vì thiếu demand; ứng dụng cần deadline và policy phù hợp để tránh giữ resource vô hạn.

## 15. Cách thiết kế consumer chậm an toàn

### 15.1. Giảm demand thay vì buffer vô hạn

Giả sử xử lý mỗi event tốn 100 ms. Consumer nên giữ concurrency có giới hạn:

```java
Flux<Processed> processed = requester.route("events.stream")
        .retrieveFlux(Event.class)
        .concatMap(event -> processEvent(event));
```

`concatMap` giữ thứ tự xử lý. Nếu muốn concurrency, dùng `flatMap` với giới hạn:

```java
Flux<Processed> processed = requester.route("events.stream")
        .retrieveFlux(Event.class)
        .flatMap(event -> processEvent(event), 4);
```

Giới hạn concurrency là 4 không đồng nghĩa một request-N có N=4 trên dây; Reactor còn có prefetch/replenishment. Hãy đo metrics queue, throughput và latency.

### 15.2. Hot source phải có overload policy

Nếu nguồn dữ liệu phát độc lập với demand:

```java
Flux<Event> hot = eventBroker.liveFeed();
```

Khi adapter của broker không thể chậm lại, cần policy rõ ràng:

- Bounded buffer và từ chối khi tràn.
- Drop mới, drop cũ hoặc latest nếu dữ liệu được phép mất.
- Sampling/rate reduction.
- Persist sự kiện vào queue/broker bền vững có quota.
- Tách slow consumer khỏi fast consumer nếu nhiều subscribers.

Không mặc định thêm `onBackpressureBuffer()` không giới hạn và cho rằng RSocket sẽ bảo vệ heap. Buffer chỉ dời vấn đề sang bộ nhớ.

### 15.3. Cancellation và resource ownership

Nếu stream dùng connection/cursor:

```java
Flux<Row> rows = Flux.usingWhen(
        connectionFactory.acquire(),
        connection -> queryRows(connection),
        connection -> connection.closeAsync(),
        (connection, error) -> connection.closeAsync(),
        connection -> connection.closeAsync());
```

Đây là snippet abstraction: `acquire`, `queryRows` và `closeAsync` là API của resource cụ thể. `usingWhen` khai báo cleanup async khi complete, error hoặc cancel. Phải gắn resource theo subscription chứ không tạo một cursor dùng chung cho mọi client.

### 15.4. Bảo vệ message và giới hạn size

Một response `Flux<Payload>` có thể tạo rất nhiều item nhỏ hoặc ít item rất lớn. Hãy giới hạn:

- Kích thước message/fragment.
- Số interaction đang chạy và số subscriber đồng thời.
- Timeout xử lý, idle timeout và chính sách connection.
- Bộ nhớ codec và phần data bị giữ trong buffer.
- Tracing/log payload với sampling; tránh log PII hoặc token.
- CPU công việc decode/encode.

Đặt limit phù hợp business contract. Đừng tối ưu chỉ một con số request-N.

## 16. Quan sát và kiểm thử backpressure

Nên kiểm thử ở ba cấp:

**Cấp 1 — Reactor publisher trong process.**

- `StepVerifier.create(publisher, 0)` khởi tạo với demand bằng 0.
- `thenRequest(n)` tăng demand.
- `expectNext(...)` xác nhận không thiếu, lặp hoặc sai thứ tự.
- `thenCancel()` xác nhận đường hủy.
- `doOnRequest` và `doFinally` giúp quan sát nguồn.

**Cấp 2 — RSocket qua TCP/WebSocket thật.**

- Dùng requester và responder riêng hoặc embedded RSocket server.
- Thực hiện request-stream/channel thực tế.
- Kiểm tra dữ liệu đúng, cancellation, lỗi và cleanup.
- Tạo consumer chậm nhưng có deadline test rõ ràng.
- Quan sát queue, bytes, active streams và resource release.

**Cấp 3 — Protocol framing.**

- Instrument RSocket frame interceptor hoặc transport-level tracing.
- Kiểm tra `REQUEST_STREAM Initial Request N` và `REQUEST_N` tăng credit đúng.
- Kiểm tra responder không phát `NEXT` vượt credit còn lại.
- Kiểm tra `CANCEL` giải phóng stream và resource.
- Kiểm tra channel có credit độc lập hai hướng.
- Kiểm tra phân mảnh message và payload frame không bị đếm nhầm thành item ứng dụng.

Không dùng `Thread.sleep` để xác minh chính xác thứ tự frame. Dùng StepVerifier, latch/probe hoặc interceptor có timeout và assert có điều kiện. Nếu test cần chứng minh implementation không gửi trước khi có credit, cần instrument ở lớp frame chứ không suy luận từ log ứng dụng.

## 17. Các sai lầm thường gặp

1. **Nói “HTTP không có backpressure”.** HTTP/2 có byte-level flow control; TCP cũng có receive window. Khác biệt là demand theo application item.
2. **Nhầm `WINDOW_UPDATE` với `REQUEST_N`.** Một bên cấp byte, một bên cấp số message/`onNext`.
3. **Nhầm `Request–Stream` với `Request–Channel`.** Channel có input và output streams cần credit độc lập.
4. **Nghĩ Fire-and-Forget luôn thành công.** Không có response nghiệp vụ và có thể mất/xảy ra lỗi.
5. **Nghĩ `request(n)` luôn tương ứng một frame có N=n.** Prefetch/replenishment có thể thay đổi frame phát thực tế.
6. **Cho rằng một PAYLOAD fragment luôn là một item.** Phải phân biệt fragmentation với `onNext` logic.
7. **Không kiểm tra giá trị N.** REQUEST_N phải dương và bị giới hạn bởi trường 31-bit.
8. **Coi credit là giới hạn byte.** Một item rất lớn vẫn có thể chiếm nhiều memory và fragment.
9. **Dùng `onBackpressureBuffer()` vô hạn.** Có thể gây OutOfMemoryError.
10. **Tự `subscribe()` trong service.** Tách subscription khỏi lifecycle, làm mất cancellation/error propagation.
11. **Chặn event loop bằng `block()` hoặc JDBC.** Có thể khiến nhiều stream khác bị chậm.
12. **Coi `doOnRequest` log server là wire trace.** Nó chỉ thấy demand tại vị trí operator.
13. **Không cleanup khi cancel.** Resource có thể bị giữ sau khi subscriber ngừng nhận.
14. **Nghĩ cancel hoàn tác mọi side effect.** Side effect có thể đã commit.
15. **Gộp lease và request-N.** Lease kiểm soát số request mới; request-N kiểm soát item trong stream.
16. **Coi WebSocket là RSocket.** WebSocket thuần không tự định nghĩa request-N.
17. **Dùng SSE vô hạn với `collectList()`.** Publisher có thể không bao giờ complete và memory tăng.
18. **Không kiểm thử producer hot.** Demand có thể không tới source không hợp tác; cần overload policy.
19. **Chọn RSocket cho mọi REST API.** HTTP vẫn đơn giản hơn khi cần browser/cache/CDN và API request-response công khai.
20. **Nhầm multiplex với công bằng tài nguyên.** Multiplex cho phép nhiều stream chia connection, không tự đảm bảo fairness/CPU quota.
21. **Thiết kế timeout chỉ ở TCP.** Stream có thể đứng đợi demand vô hạn; cần application deadline và cleanup policy.
22. **Test chỉ dữ liệu nhận được.** Cần cả cancellation, outstanding demand, queue/buffer, memory và connection lifecycle.
23. **Cho rằng gRPC stream tương đương REQUEST_N của RSocket.** Xem đúng semantics và tầng flow control của thư viện.
24. **Bỏ qua security/authentication khi dùng kết nối lâu dài.** RSocket route và metadata có thể chứa thông tin nhạy cảm; xác thực, phân quyền và kiểm soát lease/DoS.

## 18. Checklist khi chọn RSocket thay cho HTTP

Trước khi quyết định dùng RSocket:

- Có thật sự cần nhiều message trên cùng interaction, streaming dài hoặc duplex channel?
- Consumer có cần điều chỉnh nguồn bằng tín dụng theo **số item** ở protocol level?
- Nguồn dữ liệu là cold/backpressure-aware hay hot/unbounded?
- Team/client hiện có hỗ trợ RSocket hay cần giao tiếp browser/CDN/API gateway HTTP?
- Có cần request-response, stream hay channel? Có chọn đúng interaction?
- Payload thường lớn bao nhiêu byte? Có fragmentation và memory limit phù hợp?
- Có đo prefetch và demand ở các operator thay vì suy đoán frame?
- Có test credit thông qua interceptor khi cần chứng minh wire protocol?
- Có cơ chế cleanup cho cancel, error, timeout và disconnect?
- Có chính sách dành cho subscriber chậm, buffer đầy và hot publisher?
- Có cần lease để hạn chế số interaction mới, khác với request-N?
- Có cần keepalive, resume, reconnect và idempotency theo business contract?
- Có giới hạn số stream, độ dài connection và quota cho từng client?
- Có quan sát latency, demand, queue depth, memory, active streams và lỗi transport?
- Có tương thích với network/proxy/TLS, bảo mật route và metadata?
- Có trường hợp HTTP/2, SSE hoặc NDJSON đã đủ đơn giản hơn không?

**Ghi nhớ:** RSocket thực hiện backpressure theo số **message** trong request-stream/channel bằng `Initial Request N` và `REQUEST_N`. Những tín dụng này liên kết với semantics Reactive Streams qua ranh giới mạng. HTTP/1.1 dựa vào TCP flow control, HTTP/2 dùng `WINDOW_UPDATE` theo byte và HTTP/3 dùng QUIC byte credit; chúng không định nghĩa chuẩn `request(n)` theo item ứng dụng. RSocket vẫn cần timeout, giới hạn payload/queue, cancellation và cleanup đúng cách. Quan sát `doOnRequest` giúp học về demand nhưng không thay thế protocol-frame tracing.

## Tài liệu tham khảo

- RSocket Protocol Specification — [REQUEST_STREAM, REQUEST_CHANNEL, REQUEST_N, Flow Control and Lease](https://github.com/rsocket/rsocket/blob/master/Protocol.md).
- RSocket — [Protocol Overview](https://rsocket.io/about/protocol/).
- Spring Framework — [RSocket reference: interactions, requester and annotated responder](https://docs.spring.io/spring-framework/reference/rsocket.html).
- Spring Boot 3.5 — [RSocket auto-configuration and server/client setup](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html).
- Project Reactor — [Backpressure and Reactive Streams](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).
- Project Reactor — [StepVerifier testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- IETF RFC 9113 — [HTTP/2 `5.2 Flow Control and `6.9 WINDOW_UPDATE](https://www.rfc-editor.org/rfc/rfc9113.html).
- IETF RFC 9000 — [QUIC Transport Flow Control](https://www.rfc-editor.org/rfc/rfc9000.html).
