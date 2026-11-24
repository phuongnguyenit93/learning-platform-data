# Streaming response bằng Flux trong Spring Integration WebFlux

## 1. Bài toán: trả kết quả dần thay vì chờ toàn bộ dữ liệu

Một HTTP API không phải lúc nào cũng trả một JSON object rồi đóng response. Ví dụ, dịch vụ theo dõi vận đơn cần gửi trạng thái *RECEIVED → IN_TRANSIT → OUT_FOR_DELIVERY → DELIVERED* theo thời gian thực; một dịch vụ báo cáo cần trả hàng nghìn record mà không đợi xây dựng một danh sách khổng lồ. **Streaming response** cho phép server phát từng phần tử khi có dữ liệu, và client đọc các phần tử khi chúng đến.

Trong chương **Adapter WebFlux** của module **SPRING_INTEGRATION_ADAPTERS**, ta kết nối hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`. Các luồng có thể bắt đầu từ file, SFTP, HTTP, JMS, AMQP, Kafka hoặc database. WebFlux kết hợp với Project Reactor giúp biểu diễn dòng kết quả bằng **`Flux<T>`**, nhưng vẫn phải làm rõ hợp đồng HTTP, cách Spring Integration đóng gói message, backpressure, lỗi và vòng đời kết nối.

**Hai hướng streaming khác nhau:**

- **Inbound WebFlux gateway:** HTTP client gọi **vào ứng dụng**; handler trong IntegrationFlow trả `Flux<T>`, gateway ghi các phần tử thành HTTP streaming response.
- **Outbound WebFlux gateway:** IntegrationFlow gọi **ra API bên ngoài** bằng WebClient; nếu remote trả một stream, gateway có thể đưa `Flux<T>` thành **payload của reply message** để downstream tiêu thụ.

~~~mermaid
flowchart LR
    A["Browser / curl / client"] -->|"HTTP GET"| B["WebFlux inbound gateway"]
    B --> C["IntegrationFlow"]
    C -->|"Reply payload: Flux<ShipmentUpdate>"| B
    B -->|"SSE: các event theo thời gian"| A
~~~

Streaming khác với mô hình trả `List<T>`: `List<T>` thường chỉ có sau khi toàn bộ kết quả đã được tạo và giữ trong bộ nhớ; `Flux<T>` có thể phát nhiều phần tử bất đồng bộ và kết thúc sau cùng, hoặc tiếp tục lâu dài.

## 2. Ba lớp cần phân biệt: Reactor, Spring Integration và HTTP

| Lớp | Đối tượng | Ý nghĩa |
|---|---|---|
| Project Reactor | `Mono<T>` | Publisher phát tối đa một phần tử |
| Project Reactor | `Flux<T>` | Publisher phát không đến nhiều phần tử; có thể kết thúc hoặc không kết thúc |
| Spring Integration | `Message<Flux<T>>` | **Một** integration message chứa publisher làm payload |
| Spring Integration | `Flux<Message<T>>` | Publisher phát **nhiều integration messages** |
| Spring Integration | `FluxMessageChannel` | Channel tích hợp Reactive Streams, không đồng nghĩa HTTP response streaming |
| HTTP | `text/event-stream` | Server-Sent Events: stream văn bản có khung sự kiện |
| HTTP | `application/x-ndjson` | Mỗi dòng văn bản là một JSON value, phù hợp các JSON object liên tiếp |
| HTTP | `application/json` | Thường là một JSON document; có thể cần hoàn tất/ghép tập kết quả để hợp lệ |

Ba lớp không tự chuyển đổi cho nhau. Nếu outbound gateway trả `Message<Flux<ShipmentUpdate>>`, một handler đang chờ `Message<ShipmentUpdate>` **không** tự nhận từng cập nhật. Cần một consumer/splitter hoặc bước reactive hiểu payload đó.

~~~text
Một message chứa stream:
Message<Flux<ShipmentUpdate>>
  └─ payload = Flux
     ├─ ShipmentUpdate(sequence=0)
     ├─ ShipmentUpdate(sequence=1)
     └─ ShipmentUpdate(sequence=2)

Stream gồm nhiều message:
Flux<Message<ShipmentUpdate>>
  ├─ Message(sequence=0)
  ├─ Message(sequence=1)
  └─ Message(sequence=2)
~~~

**Lưu ý:** từ *reactive* ở tầng WebClient/WebFlux không bảo đảm toàn bộ handler, poller, JDBC hoặc broker cùng tuân thủ Reactive Streams. Backpressure chỉ truyền được qua các thành phần có hợp đồng tương ứng.

## 3. Streaming response thực sự được truyền qua HTTP thế nào?

### 3.1. Server-Sent Events (SSE)

SSE dùng HTTP response có media type `text/event-stream`. Mỗi sự kiện có thể có `id`, `event`, `data` và `retry`; các sự kiện thường được phân tách bằng một dòng trống.

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

id: 0
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":0,"status":"RECEIVED"}

id: 1
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":1,"status":"IN_TRANSIT"}

~~~

Trong response thực tế, HTTP/1.1 có thể dùng chunked transfer encoding; HTTP/2 dùng các frame tương ứng. **Biên của một TCP packet hoặc HTTP chunk không phải biên của một SSE event.** Client phải parse format SSE, không dựa vào số lần nhận bytes.

SSE là giao thức **server → client** sau khi client mở HTTP request, phù hợp dashboard, notification hoặc tiến độ xử lý. Nó khác WebSocket (hai chiều) và khác việc gửi nhiều HTTP request độc lập.

### 3.2. NDJSON

Với `application/x-ndjson`, mỗi dòng là một JSON document độc lập:

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"shipmentId":"SHP-001","sequence":0,"status":"RECEIVED"}
{"shipmentId":"SHP-001","sequence":1,"status":"IN_TRANSIT"}
~~~

NDJSON phù hợp hệ thống xử lý dữ liệu theo record. Nó không có cấu trúc chuẩn `id/event/retry` như SSE. Nếu client là trình duyệt dùng `EventSource`, chọn SSE; nếu client có HTTP parser cho dòng JSON, NDJSON có thể đơn giản hơn.

### 3.3. Vì sao `application/json` chưa chắc là streaming?

Một JSON array chuẩn cần `[`, các phần tử phân tách bằng dấu phẩy, và `]` ở cuối. Tùy codec, cách encode và client, một chuỗi `Flux<T>` với `application/json` có thể bị buffer, hoặc chỉ được coi là một document hoàn tất sau khi server kết thúc stream. Đừng coi `Flux<T>` là bằng chứng mỗi object sẽ được hiển thị ngay cho client. **Hãy lựa chọn media type hỗ trợ streaming, codec đúng và kiểm thử dòng bytes thực nhận.**

## 4. Từ request-reply thông thường đến streaming gateway

Một WebFlux inbound **channel adapter** thường nhận HTTP request rồi đưa message vào channel; nó không dùng kết quả downstream để tạo body phản hồi nghiệp vụ. Để streaming **response từ flow**, cần **WebFlux inbound gateway**, vì gateway chờ reply message và chuyển payload reply thành HTTP body.

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant Gateway as WebFlux inbound gateway
    participant Flow as IntegrationFlow
    participant Pub as Flux Publisher
    Client->>Gateway: GET /api/shipments/progress
    Gateway->>Flow: Request Message + reply context
    Flow-->>Gateway: Reply Message<Flux<ShipmentUpdate>>
    Gateway->>Pub: Subscribe/đọc payload publisher
    Pub-->>Gateway: onNext(update 0)
    Gateway-->>Client: SSE event 0
    Pub-->>Gateway: onNext(update 1)
    Gateway-->>Client: SSE event 1
    Pub-->>Gateway: onComplete()
    Gateway-->>Client: Hoàn tất HTTP response
~~~

Sơ đồ mô tả **trình tự logic**, không khẳng định mỗi `onNext` tạo đúng một TCP write. Gateway và WebFlux runtime phối hợp đọc reply publisher theo codec/media type. Reply timeout của gateway (nếu được cấu hình) liên quan đến **đợi reply message**, không phải mặc nhiên là giới hạn cho toàn bộ thời gian phát của một `Flux` có thể kéo dài nhiều phút.

## 5. Chuẩn bị Spring Boot và Spring Integration

Ví dụ sử dụng Java 17+, Spring Boot và BOM phù hợp với Spring Integration. Với Spring Boot, nên để dependency management chọn các phiên bản Spring Framework, Reactor và Spring Integration tương thích.

~~~groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-integration-webflux` cung cấp WebFlux inbound/outbound gateway. `spring-boot-starter-webflux` cung cấp WebFlux runtime, WebClient và codec HTTP thường dùng. Trong ứng dụng đã được Spring Boot cấu hình WebFlux, không cần tự thêm `@EnableWebFlux` chỉ để chạy ví dụ.

Với dự án đồng thời khai báo Spring MVC và WebFlux, phải kiểm tra loại web application đang chạy; có WebClient trong classpath không chứng minh server đang phục vụ request bằng WebFlux.

## 6. Ví dụ đầy đủ: inbound gateway trả SSE bằng Flux

Tạo một API công bố tiến độ xử lý vận đơn. Ứng dụng nhận HTTP `GET /api/shipments/progress`, tạo một reply publisher gồm bốn trạng thái và trả chúng dưới dạng SSE. Đây là ví dụ mô phỏng, **không** cần broker hay database ngoài.

~~~java
package com.example.integration;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Configuration
@EnableIntegration
public class ShipmentProgressFlow {

    public record ShipmentUpdate(
            String shipmentId, long sequence, String status) { }

    @Bean
    public IntegrationFlow shipmentProgressGateway() {
        String[] statuses = {
            "RECEIVED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"
        };

        return IntegrationFlow
            .from(WebFlux.inboundGateway("/api/shipments/progress")
                .requestMapping(mapping -> mapping
                    .methods(HttpMethod.GET)
                    .produces(MediaType.TEXT_EVENT_STREAM_VALUE)))
            .handle((payload, headers) ->
                Flux.interval(Duration.ofSeconds(1))
                    .take(statuses.length)
                    .map(index -> ServerSentEvent
                        .<ShipmentUpdate>builder()
                        .id(Long.toString(index))
                        .event("shipment-progress")
                        .data(new ShipmentUpdate(
                            "SHP-001", index, statuses[index.intValue()]))
                        .build()))
            .get();
    }
}
~~~

### 6.1. Đọc từng thành phần

1. `WebFlux.inboundGateway(...)` tạo HTTP endpoint **request-reply**. Reply mang `Flux<ServerSentEvent<ShipmentUpdate>>` nên có thể được HTTP writer serialize dần.
2. `requestMapping(...).methods(GET)` định nghĩa HTTP method, còn `produces(TEXT_EVENT_STREAM_VALUE)` xác định media type của response.
3. `handle((payload, headers) -> ...)` là một service activator inline. Ví dụ không cần body hay query parameter, nên không dùng request payload.
4. `Flux.interval(Duration.ofSeconds(1))` phát chỉ số theo lịch Reactor, không dùng `Thread.sleep` để chặn thread.
5. `take(statuses.length)` giới hạn bốn phần tử; sau đó publisher gửi `onComplete` và HTTP response có thể kết thúc.
6. `ServerSentEvent.builder()` đặt `id` và `event` rõ ràng; `data` chứa DTO được codec serialize.
7. Không có một `List<ShipmentUpdate>` lớn được dựng trước. Tuy nhiên, bảng `statuses` nhỏ chỉ phục vụ mô phỏng; trong thực tế nguồn có thể là một reactive repository hoặc event source.

**Giới hạn của ví dụ:** mỗi HTTP subscription tạo một chuỗi interval mới và các trạng thái được mô phỏng. Dịch vụ thật cần lấy `shipmentId` từ request một cách an toàn, kiểm tra quyền xem vận đơn, kết nối đến nguồn dữ liệu và xác định chính sách replay khi client reconnect.

## 7. Thử bằng curl và trình duyệt

Chạy ứng dụng Spring Boot/WebFlux trên `localhost:8080` rồi gửi:

~~~bash
curl -N -i \
  -H 'Accept: text/event-stream' \
  http://localhost:8080/api/shipments/progress
~~~

`-N` hoặc `--no-buffer` tắt buffering đầu ra của curl, giúp quan sát từng event khi server phát. Trong PowerShell có thể dùng `curl.exe` để tránh alias khác cú pháp.

Response minh họa (bỏ qua headers transport không quan trọng):

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

id: 0
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":0,"status":"RECEIVED"}

id: 1
event: shipment-progress
data: {"shipmentId":"SHP-001","sequence":1,"status":"IN_TRANSIT"}

...
~~~

Kết quả phụ thuộc codec, định dạng serialization và các lớp proxy ở giữa. Nếu tất cả phần tử chỉ xuất hiện cùng lúc khi request kết thúc, hãy kiểm tra **media type, codec, buffering ở proxy và HTTP client**, thay vì kết luận `Flux.interval` không chạy.

Một trình duyệt có thể tiêu thụ SSE bằng API `EventSource`:

~~~javascript
const stream = new EventSource("/api/shipments/progress");

stream.addEventListener("shipment-progress", event => {
  const update = JSON.parse(event.data);
  console.log(update.shipmentId, update.status);
});

stream.onerror = error => {
  console.error("SSE connection error", error);
};

// Khi không cần nhận nữa:
// stream.close();
~~~

`EventSource` hỗ trợ SSE một chiều và có thể tự reconnect theo hành vi trình duyệt. **Tự reconnect không tự có replay**: server phải dùng `Last-Event-ID` và kho sự kiện phù hợp nếu muốn client nhận những sự kiện đã bỏ lỡ. Ví dụ dùng `Flux.interval` không có cơ chế replay lịch sử.

## 8. Từ dữ liệu giả lập sang nguồn sự kiện thực

Trong production, cập nhật vận đơn có thể đến từ Kafka, JMS/AMQP, CDC, database hoặc các adapter file/SFTP. Thách thức lớn nhất là tách **nguồn message có thể tiếp tục chạy** khỏi **HTTP subscription có vòng đời ngắn**.

~~~mermaid
flowchart TD
    A["Kafka / AMQP / DB event source"] --> B["Validation + enrichment"]
    B --> C["Event store / bounded fan-out service"]
    C --> D["Publisher<ShipmentUpdate>"]
    D --> E["WebFlux inbound gateway"]
    E --> F["SSE clients"]
    F -.->|"disconnect / reconnect / Last-Event-ID"| C
~~~

**Hai kiểu nguồn đáng phân biệt:**

- **Cold publisher:** mỗi subscriber kích hoạt một luồng độc lập, ví dụ `Flux.interval` trong bài. Nếu 100 client subscribe, có thể có 100 nguồn tính toán/truy vấn độc lập. Cần kiểm soát concurrency và giới hạn subscription.
- **Hot publisher:** một nguồn có thể phát sự kiện liên tục và chia sẻ cho nhiều subscriber, chẳng hạn publisher gắn với event bus. Client đến sau có thể bỏ lỡ sự kiện đã qua nếu không có cơ chế replay.

Trong Reactor có `Sinks.Many<T>` để phát dữ liệu đến subscribers theo các chiến lược multicast/replay; chọn loại sink cần dựa trên chính sách buffer/overflow, mức độ mất dữ liệu được phép và vòng đời dữ liệu. `FluxMessageChannel` cũng dùng cấu trúc reactive để tích hợp message, nhưng **không đồng nghĩa** một event history store cho mọi người dùng SSE.

Đối với event quan trọng (thanh toán, xác nhận đơn hàng), không nên lấy **kết nối SSE đang mở** làm nơi lưu bền vững duy nhất. Dùng broker/outbox/event store phù hợp rồi ánh xạ các sự kiện đã được phép công bố ra HTTP stream.

## 9. Outbound gateway: nhận HTTP streaming response từ remote service

Đối với chiều **gọi ra ngoài**, Spring Integration WebFlux outbound gateway dùng WebClient để gọi remote HTTP API. Thông thường `expectedResponseType(ShipmentUpdate.class)` giải mã **một object** vào reply. Khi remote thực sự trả một stream, `replyPayloadToFlux(true)` cho phép reply message mang `Flux<ShipmentUpdate>`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class RemoteProgressClientFlow {

    public record ShipmentUpdate(
            String shipmentId, long sequence, String status) { }

    @Bean
    public IntegrationFlow fetchRemoteProgress(WebClient.Builder builder) {
        WebClient client = builder.build();

        return IntegrationFlow.from("remoteProgressRequests")
            .handle(WebFlux.outboundGateway(
                    "http://localhost:8080/api/shipments/progress", client)
                .httpMethod(HttpMethod.GET)
                .extractPayload(false)
                .expectedResponseType(ShipmentUpdate.class)
                .replyPayloadToFlux(true)
                .mappedRequestHeaders(HttpHeaders.ACCEPT))
            .channel("remoteProgressReplies")
            .get();
    }
}
~~~

Đây là một **flow client minh họa riêng**: để kết nối hai ứng dụng độc lập, chạy service SSE ở `8080` và ứng dụng gọi HTTP ở cổng/process khác. Chỉ cấu hình một channel tên `remoteProgressRequests` là chưa sinh ra request; cần producer gửi message vào channel.

Một producer có thể gửi message với header `Accept: text/event-stream`:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.messaging.support.MessageBuilder;

remoteProgressRequests.send(
    MessageBuilder.withPayload("trigger")
        .setHeader(HttpHeaders.ACCEPT,
            MediaType.TEXT_EVENT_STREAM_VALUE)
        .build());
~~~

Ở đây `extractPayload(false)` tránh gửi body của message vào HTTP GET. Remote trả các SSE events chứa JSON data; với codec tương thích, gateway giải mã từng data event theo `ShipmentUpdate.class`.

**Quan trọng:** `remoteProgressReplies` nhận một **reply message với payload `Flux<ShipmentUpdate>`**, không tự nhận bốn `Message<ShipmentUpdate>`. Downstream phải tiêu thụ publisher có quản lý subscription, backpressure, cancellation và error signals.

Trong một hệ thống lớn, nên giữ `WebClient` trong bean được inject và cấu hình connection pool/timeout ở một chỗ thay vì tạo client riêng cho từng lời gọi. Ví dụ rút gọn `builder.build()` trong lúc tạo flow bean vẫn tạo **một client lúc khởi tạo context**, không phải mỗi HTTP request.

## 10. Tiêu thụ đúng reply payload dạng Flux

Giả sử outbound gateway tạo message payload `Flux<ShipmentUpdate>`. Có hai thiết kế phổ biến:

1. **Terminal reactive consumer**: endpoint cuối pipeline subscribe vào `Flux`, xử lý từng update và chịu trách nhiệm dừng/giới hạn nguồn.
2. **Biến Flux thành chuỗi integration messages**: dùng splitter hoặc một thành phần reactive-aware để mỗi update đi qua pipeline riêng. Phải chắc chắn splitter/consumer thực sự subscribe; không chỉ thay tên channel.

~~~mermaid
flowchart TD
    A["Reply: Message<Flux<Update>>"] --> B{"Downstream cần gì?"}
    B -->|"Ghi lại theo stream"| C["Reactive subscriber / sink"]
    B -->|"Từng message để route/transform"| D["Publisher-aware splitter"]
    D --> E["Flux<Message<Update>> hoặc message rời"]
    B -->|"Tổng hợp số lượng hữu hạn"| F["collectList() theo giới hạn"]
~~~

Với một **stream vô hạn**, `collectList()` sẽ không hoàn tất và có thể tích lũy vô hạn. Chỉ tổng hợp một tập hữu hạn đã có giới hạn số phần tử/thời gian và đã cân nhắc bộ nhớ.

Đoạn Reactor sau minh họa xử lý publisher ở **biên tiêu thụ cuối cùng**, không phải lời khuyên gọi `subscribe()` tùy tiện trong mọi handler:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

void consumeAtBoundary(Flux<ShipmentUpdate> updates) {
    updates.subscribe(new BaseSubscriber<ShipmentUpdate>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(1);
        }

        @Override
        protected void hookOnNext(ShipmentUpdate update) {
            System.out.println(update);
            request(1);
        }

        @Override
        protected void hookOnError(Throwable error) {
            System.err.println("Streaming failed: " + error);
        }
    });
}
~~~

`ShipmentUpdate` ở snippet là DTO của ứng dụng. `request(1)` thể hiện demand ở subscriber; **việc in log đồng bộ không phải xử lý nghiệp vụ đáng tin cậy**. Với ghi DB hoặc phát broker, cần gắn yêu cầu thêm phần tử với **thời điểm xử lý bất đồng bộ đã hoàn thành**, không gọi `request(1)` sớm rồi cho rằng đã bảo vệ downstream.

Nếu dùng Spring Integration reactive pipeline, nghiên cứu `FluxMessageChannel`, `ReactiveStreamsConsumer` và `handleReactive(...)` để duy trì composition và error/cancel signals. Không mặc định mọi kiểu `MessageHandler` sẽ tự động subscribe payload publisher.

## 11. Backpressure: client chậm và ranh giới thật sự

Reactive Streams dùng `request(n)` để subscriber biểu thị lượng phần tử muốn nhận. Khi HTTP writer tiêu thụ `Flux` theo demand, nó có thể giúp kiểm soát producer reactive trong cùng chuỗi. Tuy nhiên, **TCP flow control**, bộ đệm ở codec/proxy và publisher đang chạy trên scheduler độc lập có những đặc tính riêng.

| Đoạn luồng | Backpressure có thể hoạt động ra sao? | Điểm giới hạn |
|---|---|---|
| `Flux.range/interval` → HTTP writer | Runtime subscribe vào publisher; demand/cancellation được truyền trong reactive chain | Không bảo đảm mỗi request(n) tương ứng đúng một TCP chunk |
| `FluxMessageChannel` → ReactiveStreamsConsumer | Các thành phần tương thích có thể liên kết demand | Producer gọi `send()` imperative vẫn phải kiểm soát tốc độ riêng |
| Kafka/JMS/AMQP → service | Cơ chế driver: poll/prefetch/ACK/concurrency | Không tự dừng broker chỉ vì browser đọc SSE chậm |
| JDBC blocking → Flux | Có thể cô lập blocking trên executor/scheduler | Scheduler không biến JDBC thành non-blocking |
| HTTP stream qua proxy | Có thể flush/buffer theo cấu hình hạ tầng | Proxy có thể thay đổi thời điểm client nhìn thấy từng event |

Tránh thiết kế *unbounded buffer* giữa nguồn nhanh và client chậm. Nếu nguồn là dữ liệu nghiệp vụ cần đủ mọi sự kiện, nên có event store/replay và chính sách giới hạn kết nối, thay vì tích lũy vô hạn dữ liệu chưa gửi trong bộ nhớ.

Nếu chỉ là telemetry realtime, có thể cân nhắc chính sách drop/latest kèm quan sát, **nhưng phải công bố rõ dữ liệu có thể bị bỏ qua**. Với thanh toán hoặc cập nhật đơn hàng quan trọng, drop không kiểm soát là không chấp nhận được.

### 11.1. Concurrency và memory

Mỗi SSE subscription có thể giữ tài nguyên trong thời gian dài: connection, parser/encoder, buffer, observer, correlation context và subscription nguồn. Cần giới hạn số client đồng thời, số subscription theo người dùng, tốc độ event, kích thước payload và số lượng pending messages.

Một `Flux` có thể non-blocking nhưng vẫn tạo áp lực bộ nhớ nếu upstream đẩy hàng nghìn events/giây cho client có đường truyền yếu. Giải pháp là **điều tiết nguồn, buffering có giới hạn, giảm tải hợp lệ, hoặc lưu bền vững rồi cho client đọc theo offset/cursor**.

## 12. Cancellation, reconnect và Last-Event-ID

Client có thể đóng tab, mất mạng hoặc gọi `EventSource.close()`. Khi đó WebFlux thường có thể hủy subscription HTTP; publisher Reactor nhận tín hiệu cancellation. Tuy vậy:

- Một truy vấn reactive có thể bị hủy nếu driver hỗ trợ cancellation; còn một tác vụ blocking đã đưa vào executor có thể tiếp tục.
- Một message đã gửi tới JMS/Kafka **không tự bị thu hồi** chỉ vì client SSE ngắt kết nối.
- Một lệnh ghi database đã commit sẽ không rollback do TCP connection bị đóng sau đó.
- Một nguồn hot có thể vẫn phát cho những client khác dù một client đã rời.

Có thể gắn hook để quan sát vòng đời publisher:

~~~java
Flux<ShipmentUpdate> monitored = updates
    .doOnSubscribe(s -> log.info("Stream subscribed"))
    .doOnCancel(() -> log.info("Stream cancelled"))
    .doOnComplete(() -> log.info("Stream completed"))
    .doOnError(error -> log.warn("Stream failed", error))
    .doFinally(signal -> log.info("Stream terminated: {}", signal));
~~~

Các biến `updates` và `log` ở đây là thành phần sẵn có trong service thực; snippet minh họa hook, không phải một file Java tự chạy.

SSE có trường `id` và header reconnect `Last-Event-ID`, nhưng framework không tự biết cách truy vấn lại lịch sử. Nếu yêu cầu **không bỏ lỡ sự kiện**, server phải:

1. Lưu events trong kho bền vững hoặc stream log có thứ tự/offset.
2. Sinh ID ổn định và có thể tìm lại tương ứng với sự kiện thực.
3. Xác minh quyền truy cập tài nguyên khi reconnect.
4. Đọc header `Last-Event-ID`, xác định cursor tiếp tục và trả lại các sự kiện còn thiếu trước khi stream live.
5. Xử lý retention hết hạn, cursor không hợp lệ và thay đổi thứ tự/partition.

`Flux.interval` dùng để minh họa ở mục 6 không thực hiện các bước trên.

## 13. Lỗi và timeout khi response đang streaming

### 13.1. Trước và sau khi HTTP headers được gửi

| Thời điểm lỗi | Khả năng xử lý | Ví dụ |
|---|---|---|
| **Trước** khi HTTP response được commit | Có thể chọn HTTP status và body lỗi khác | Validation fail, không đủ quyền, không tìm thấy shipment |
| **Sau** khi response đã bắt đầu streaming | Thông thường không thể đổi HTTP `200` thành `500` giữa response | Lỗi đọc DB hoặc event publisher giữa stream |
| Client hủy kết nối | Ngừng phát theo khả năng cancellation | Browser đóng tab, proxy timeout |
| Proxy timeout/idle close | Có thể đóng response dù ứng dụng vẫn còn publisher | Thiếu heartbeat hoặc proxy có timeout ngắn |

Một khi HTTP status và headers đã được commit, server không thể viết một **status code mới** giữa cùng một response. Có thể kết thúc stream, phát một **event nghiệp vụ báo lỗi** nếu hợp đồng cho phép và kết nối còn ghi được, hoặc để client reconnect. Không coi event báo lỗi nghiệp vụ là thay thế hoàn hảo cho HTTP 5xx.

### 13.2. Tránh nuốt lỗi một cách mơ hồ

~~~java
Flux<ShipmentUpdate> updates = loadUpdates(shipmentId)
    .doOnError(error -> log.error("Shipment stream error", error));
~~~

Snippet biểu thị việc ghi log. Nếu muốn `onErrorResume` chuyển sang một event cuối thông báo lỗi, phải chọn schema đó rõ ràng và chỉ công bố thông tin an toàn. Không tự đặt `onErrorResume(error -> Flux.empty())` cho mọi lỗi, vì client sẽ tưởng stream kết thúc bình thường và không biết đã mất dữ liệu.

### 13.3. Timeout nào áp dụng?

Phân biệt các hạn mức:

- `replyTimeout` của inbound gateway là thời gian chờ **reply message** của flow. Một reply sớm chứa `Flux` không có nghĩa toàn stream phải kết thúc trong hạn mức đó.
- `responseTimeout` của Reactor Netty WebClient là timeout phản hồi ở tầng client transport; với server gửi SSE thưa, đặt quá ngắn có thể làm stream bị ngắt.
- `timeout(Duration)` ở Reactor là giới hạn theo publisher/operator; tùy vị trí, nó có thể áp dụng giữa các tín hiệu hoặc trên toàn chain theo cơ chế operator.
- Proxy/load balancer có idle timeout, absolute connection lifetime và buffering riêng.
- Nghiệp vụ có thể cần *first-event timeout*, *idle timeout*, *max stream lifetime* và *reconnect backoff* độc lập.

Không dùng một giá trị “timeout 5 giây” duy nhất cho mọi tầng. Hãy mô tả rõ mỗi timeout bắt đầu, kết thúc và tạo lỗi ở đâu.

## 14. Bảo mật và vận hành HTTP stream

Streaming connection có thể tồn tại lâu hơn request REST thông thường, nên cần quản lý cả phiên người dùng và dữ liệu ra:

1. **Authentication/authorization:** kiểm tra quyền xem shipment trước khi mở stream; nếu stream kéo dài, cân nhắc việc token hết hạn/thu hồi và chính sách đóng kết nối.
2. **CORS và credentials:** với browser `EventSource`, cấu hình CORS/credentials đúng origin; CORS không thay thế xác thực.
3. **Kích thước và tần suất dữ liệu:** giới hạn payload, event rate, subscriber count, session lifetime và buffer capacity.
4. **Heartbeat:** nếu có idle proxy timeout, phát heartbeat SSE theo hợp đồng để tránh kết nối bị coi là chết; không gửi quá dày gây lãng phí.
5. **Observability:** đo active streams, latency đến first event, thời gian subscription, số event gửi, cancel, lỗi, reconnect và data lag.
6. **Logging:** dùng correlation ID không chứa bí mật; không log toàn bộ nội dung nhạy cảm hoặc `Authorization` header.
7. **Graceful shutdown:** ngừng nhận subscription mới, đóng những stream hiện có theo chính sách, dọn publisher/scheduler/resources.

**Header và cache:** dùng `Content-Type: text/event-stream`, có thể đặt `Cache-Control` theo hợp đồng. Các proxy có thể cache hoặc buffer response nếu cấu hình không phù hợp; cần kiểm thử với đường triển khai thực tế (ingress, CDN, reverse proxy) thay vì chỉ `localhost`.

## 15. Kiểm thử stream, không chỉ kiểm tra HTTP 200

Một test chỉ xác nhận `200 OK` **không đủ** để chứng minh API streaming đúng. Cần kiểm tra media type, số phần tử, khoảng phát tương đối, completion/cancellation và behavior khi lỗi.

### 15.1. WebTestClient đọc response body dạng Flux

Với `spring-boot-starter-test` hoặc dependency test thích hợp:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'io.projectreactor:reactor-test'
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ShipmentProgressStreamTest {

    @Autowired
    WebTestClient client;

    @Test
    void emitsShipmentUpdatesAsSse() {
        FluxExchangeResult<ShipmentProgressFlow.ShipmentUpdate> result =
            client.get()
                .uri("/api/shipments/progress")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM)
                .returnResult(ShipmentProgressFlow.ShipmentUpdate.class);

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(update ->
                update.sequence() == 0
                    && "RECEIVED".equals(update.status()))
            .expectNextCount(3)
            .verifyComplete();
    }
}
~~~

Test trên tập trung vào payload **data** được WebFlux SSE codec giải mã thành DTO. Nếu cần kiểm tra cả `id` và `event` của SSE frame, có thể đọc response body theo kiểu `ServerSentEvent<ShipmentUpdate>` với type reference phù hợp hoặc kiểm tra raw SSE stream; khi đó test có thể xác nhận event name và event ID, không chỉ JSON body.

Với test phát theo `Flux.interval(1s)`, mỗi request kéo dài vài giây. Trong test chuyên sâu, có thể kiểm soát publisher bằng test scheduler hoặc thay nguồn bằng fixture điều khiển được, thay vì dùng thời gian thực cho mọi test. Không chạy test/build trong bước soạn tài liệu này.

### 15.2. Ma trận lỗi cần thực hành

| Tình huống | Kết quả cần quan sát |
|---|---|
| Client request `Accept: text/event-stream` | Có HTTP media type phù hợp và từng SSE event |
| Client đọc rất chậm | Buffer/concurrency/latency tăng thế nào, có bảo vệ giới hạn không |
| Client đóng trước event cuối | Upstream nhận cancellation không, resources được dọn không |
| Publisher ném exception trước phần tử đầu | Error handler có thể trả HTTP status thích hợp không |
| Publisher ném exception sau hai event | Không thể đổi HTTP status đã commit; stream kết thúc/báo lỗi thế nào |
| Remote SSE dừng phát tạm thời | Timeout/heartbeat của client/proxy có phù hợp không |
| Client reconnect kèm `Last-Event-ID` | Có replay không, nếu không có thì ghi rõ không bảo đảm |
| Nhiều client cùng subscribe | Cold/hot publisher, memory và giới hạn số kết nối |

## 16. Bài thực hành vận dụng

1. Chạy `ShipmentProgressFlow` và dùng `curl -N` quan sát bốn sự kiện. Đổi `take(4)` thành `take(10)`, điều chỉnh nguồn dữ liệu để không truy cập ngoài chỉ số mảng.
2. Chuyển phần `data` từ `ShipmentUpdate` thành chuỗi text và so sánh SSE frame; giải thích cách codec serialize data.
3. Thêm một `ServerSentEvent` heartbeat hoặc một event riêng báo tiến độ, rồi kiểm tra proxy/browser xử lý ra sao.
4. Tạo endpoint thứ hai phát NDJSON bằng WebFlux; so sánh cách client parse NDJSON với `EventSource` cho SSE.
5. Chạy một outbound gateway với `replyPayloadToFlux(true)` gọi endpoint SSE. Quan sát kiểu payload của reply và thiết kế consumer thật sự tiêu thụ `Flux`.
6. Dùng một `BaseSubscriber` yêu cầu từng phần tử, rồi chuyển sang một reactive handler ghi DB có giới hạn concurrency; giải thích khi nào có thể `request(n)` thêm.
7. Giả lập một nguồn hot phát dữ liệu nhanh và một client chậm. Chọn bounded buffer/replay store hoặc chính sách drop có tài liệu hóa tùy nghiệp vụ.
8. Ngắt curl giữa chừng, dùng `doOnCancel` và `doFinally` quan sát lifecycle. Đảm bảo công việc đã commit ở broker/DB không bị hiểu nhầm là tự rollback.
9. Cho publisher lỗi trước phần tử đầu và sau khi phát hai phần tử; so sánh khả năng thay HTTP status/body.
10. Thiết kế cơ chế `Last-Event-ID` dùng event store có cursor ổn định, xác thực quyền và retry. Xác định tác động khi dữ liệu lịch sử đã hết thời gian lưu giữ.

**Câu hỏi tình huống:** Một hệ thống phát trạng thái xử lý đơn qua Kafka, đồng thời nhiều client mở SSE theo dõi. Nếu một client offline năm phút trong khi đơn hàng chuyển qua ba trạng thái, chỉ dùng `FluxMessageChannel` và `Flux.interval` có đáp ứng yêu cầu “không bỏ lỡ trạng thái” không? Hãy mô tả event store/cursor, cách replay, idempotency, giới hạn kết nối và nơi backpressure dừng lại.

## 17. Tài liệu tham khảo

- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): inbound/outbound gateway, reply `Flux`, `replyPayloadToFlux(true)` và WebClient.
- [Spring Integration API — WebFluxMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFluxMessageHandlerSpec.html): cấu hình `expectedResponseType`, `replyPayloadToFlux` và các tùy chọn WebFlux outbound.
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveStreamsConsumer` và composition của publisher.
- [Spring Framework Reference — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HTTP body codecs, SSE và reactive HTTP processing.
- [Spring Framework Reference — WebFlux Client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient nhận `Flux` và xử lý streaming response.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): cold/hot publisher, `request(n)`, error, cancellation và testing bằng StepVerifier.
- [MDN — Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): định dạng SSE, `EventSource`, sự kiện có ID và hành vi reconnect của browser.

> **Ghi nhớ:** `Flux` là mô hình publisher có thể phát nhiều phần tử; **streaming response** chỉ đạt được khi WebFlux HTTP writer, media type (SSE hoặc NDJSON), subscription và downstream cùng được thiết kế đúng. Trong Spring Integration, hãy phân biệt `Message<Flux<T>>` với `Flux<Message<T>>`, xác định backpressure/cancellation qua từng ranh giới và không nhầm một kết nối HTTP đang mở với kho lưu sự kiện đáng tin cậy.
