# Reactive types và backpressure trong Spring Integration WebFlux

## 1. Vấn đề cốt lõi: bên nhận xử lý chậm hơn bên gửi

Hãy hình dung một luồng tích hợp nhận sự kiện đặt hàng qua HTTP, biến đổi dữ liệu rồi chuyển đến dịch vụ lưu trữ hoặc broker. Khi lượng request tăng đột biến, tầng HTTP có thể nhận dữ liệu nhanh hơn tầng xử lý nghiệp vụ. Nếu cứ nhận và tích lũy message mà không có giới hạn, ứng dụng sẽ tăng bộ nhớ, độ trễ và cuối cùng có thể hết tài nguyên. Nếu giữ thread chờ mỗi kết nối hoặc thao tác I/O, khả năng phục vụ đồng thời cũng bị giới hạn.

Trong chương **Adapter WebFlux** thuộc module **SPRING_INTEGRATION_ADAPTERS**, ta sử dụng inbound/outbound adapter, gateway, poller và `MessageChannel` để kết nối hệ thống bên ngoài qua HTTP, file, SFTP, JMS, AMQP, Kafka và database. **Reactive types** mô tả cách một thành phần phát hoặc tiêu thụ dữ liệu bất đồng bộ; **backpressure** cho phép bên nhận truyền tín hiệu về lượng dữ liệu nó sẵn sàng xử lý. Hai khái niệm quyết định việc ghép Spring WebFlux với Spring Integration có vận hành ổn định dưới tải hay không.

Ví dụ thực tế: dịch vụ HTTP bên ngoài phát một luồng cập nhật trạng thái giao hàng. Spring Integration nhận dữ liệu, đối chiếu đơn hàng trong database rồi phát sự kiện sang Kafka. Nếu database chỉ xử lý được một lượng hữu hạn message đồng thời, luồng nhận cần điều tiết hoặc lưu đệm có giới hạn; việc có `WebClient` hoặc `Flux` trong cấu hình **không tự động giải quyết** bài toán này.

~~~mermaid
flowchart LR
    A["Reactive HTTP source"] -->|"Publisher: dữ liệu"| B["MessageChannel"]
    B --> C["Consumer / Handler"]
    C --> D["Database hoặc broker"]
    C -.->|"request(n): demand nếu cùng chuỗi Reactive Streams"| B
    B -.->|"demand lan truyền nếu nguồn hỗ trợ"| A
~~~

Tín hiệu demand trong sơ đồ chỉ áp dụng khi các thành phần thuộc **cùng chuỗi publisher/subscriber tương thích**. Đường đi qua queue thuần, API đồng bộ hoặc broker có quy trình ACK riêng có thể tạo một ranh giới mà backpressure không thể tự động đi xuyên qua.

## 2. Reactive Streams là hợp đồng gì?

Reactive Streams mô tả cách trao đổi các phần tử bất đồng bộ có thể kiểm soát lượng dữ liệu đang được yêu cầu. Bốn thành phần chính:

| Thành phần | Vai trò | Ví dụ liên quan |
|---|---|---|
| `Publisher<T>` | Cung cấp chuỗi phần tử kiểu `T` cho subscriber | `Flux<OrderEvent>`, `Mono<Quote>` |
| `Subscriber<T>` | Đăng ký nhận phần tử; xử lý tín hiệu dữ liệu/kết thúc/lỗi | Consumer ở cuối luồng reactive |
| `Subscription` | Liên kết giữa publisher và subscriber; có `request(n)` và `cancel()` | Yêu cầu thêm 8 phần tử hoặc dừng nhận |
| `Processor<T,R>` | Vừa nhận vừa phát dữ liệu; khái niệm có trong đặc tả | Các phép biến đổi giữa source và sink |

Trình tự tín hiệu điển hình:

1. Subscriber đăng ký với publisher qua `subscribe(...)`.
2. Publisher gọi `onSubscribe(subscription)`.
3. Subscriber gọi `request(n)`, với `n` dương, để cấp nhu cầu (*demand*).
4. Publisher phát **không quá nhu cầu đã được cấp** bằng `onNext(item)`, hoặc kết thúc bằng `onComplete()` hay `onError(error)`.
5. Subscriber có thể yêu cầu thêm hoặc `cancel()` khi không cần dữ liệu nữa.

~~~mermaid
sequenceDiagram
    participant Pub as Publisher
    participant Sub as Subscriber
    Sub->>Pub: subscribe()
    Pub-->>Sub: onSubscribe(subscription)
    Sub->>Pub: request(2)
    Pub-->>Sub: onNext(A)
    Pub-->>Sub: onNext(B)
    Note over Pub,Sub: Publisher chờ nhu cầu tiếp theo
    Sub->>Pub: request(1)
    Pub-->>Sub: onNext(C)
    Pub-->>Sub: onComplete()
~~~

**Backpressure không đồng nghĩa với tự động làm chậm mọi nguồn dữ liệu bên ngoài.** Nó hoạt động trực tiếp khi publisher tôn trọng demand. Với một HTTP webhook, hệ thống đối tác vẫn có thể gửi thêm request độc lập; với Kafka/JMS, việc dừng hoặc giới hạn tiêu thụ đòi hỏi cơ chế điều phối riêng của client/broker.

## 3. Các reactive types thường gặp

Project Reactor là nền tảng reactive mà Spring Integration sử dụng, với hai kiểu quen thuộc nhất:

| Kiểu | Số phần tử tiềm năng | Tín hiệu kết thúc | Tình huống |
|---|---|---|---|
| `Mono<T>` | 0 hoặc 1 | Complete hoặc error | HTTP response một JSON object, tìm một bản ghi |
| `Flux<T>` | 0 đến nhiều | Complete, error hoặc tiếp tục vô hạn | SSE, nhiều record, dòng sự kiện |
| `Publisher<T>` | Giao diện tổng quát | Theo Reactive Streams | API chung không buộc dùng Reactor trực tiếp |
| `Mono<Void>` | Không có payload kết quả | Complete hoặc error | Gửi dữ liệu đi mà chỉ cần biết thao tác hoàn tất |
| `Flux<Message<T>>` | Nhiều **message** | Theo Publisher | Nguồn sự kiện reactive cấp từng message cho flow |
| `Message<Flux<T>>` | **Một message** chứa **một Flux** | Phụ thuộc cách downstream tiêu thụ payload | HTTP request/response streaming được giữ thành payload dạng Publisher |

Phân biệt hai kiểu cuối rất quan trọng:

~~~text
Flux<Message<OrderEvent>>
  ├─ Message<OrderEvent>("event-1")
  ├─ Message<OrderEvent>("event-2")
  └─ Message<OrderEvent>("event-3")

Message<Flux<OrderEvent>>
  └─ payload = Flux<OrderEvent>
       ├─ event-1
       ├─ event-2
       └─ event-3
~~~

Ở kiểu `Flux<Message<OrderEvent>>`, mỗi tín hiệu `onNext` đã là một Spring Integration message. Ở kiểu `Message<Flux<OrderEvent>>`, flow mới nhìn thấy **một message**; phải có bước hiểu publisher hoặc splitter phù hợp nếu muốn xử lý từng sự kiện. Không ép kiểu payload sang `OrderEvent` khi nó thực sự là `Flux<OrderEvent>`.

### 3.1. Code nhỏ minh họa Mono và Flux

~~~java
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

Mono<String> oneOrder = Mono.just("ORD-1001");

Flux<String> multipleOrders =
    Flux.just("ORD-1001", "ORD-1002", "ORD-1003");

Mono<String> maybeOrder = Mono.empty();
Flux<String> failedOrders =
    Flux.error(new IllegalStateException("Remote source unavailable"));
~~~

`Mono.just`/`Flux.just` tạo các publisher; `Mono.empty` hoàn tất không phát phần tử, còn `Flux.error` phát lỗi. **Không dùng `null` như một phần tử `onNext`**: Reactive Streams không cho phép tín hiệu dữ liệu `null`; nếu không có kết quả, dùng `Mono.empty()` hoặc hợp đồng dữ liệu thay thế.

## 4. Xây dựng publisher và thời điểm thực thi

Một chuỗi Reactor có hai pha: **xây dựng pipeline** và **subscription thực sự**. Nhiều publisher là *cold*: mỗi subscriber có một lượt thực thi riêng. Một số nguồn là *hot*: phát dữ liệu độc lập với một subscriber cụ thể, hoặc nhiều subscriber cùng nhìn thấy sự kiện theo cách nguồn được cấu hình.

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> sequence = Flux.defer(() -> {
    System.out.println("Creating source on subscribe");
    return Flux.range(1, 3);
});

// Chưa subscribe: chưa chạy lambda trong defer.
sequence.subscribe(i -> System.out.println("first: " + i));
sequence.subscribe(i -> System.out.println("second: " + i));
~~~

Ở ví dụ trên, `Flux.defer` trì hoãn việc tạo source đến mỗi subscription. Mỗi lần subscribe mới chạy lại lambda. Điều này hữu ích cho HTTP operation hoặc truy vấn khi chúng được gói đúng dạng deferred publisher.

Ngược lại, `FluxMessageChannel` của Spring Integration có một `Flux` nóng bên trong dùng làm sink cho message gửi qua `send()`. Phải cân nhắc thời điểm subscriber sẵn sàng, bộ đệm và vòng đời endpoint; không coi `send()` là tín hiệu chắc chắn “consumer đã xử lý xong”.

**Lưu ý về subscription:** tự gọi `subscribe()` ở mọi tầng thường làm tách luồng lỗi, cancellation và backpressure khỏi pipeline gốc. Trong Spring Integration, hãy để endpoint/reactive consumer hoặc HTTP runtime quản lý subscription theo hợp đồng, trừ khi bản thân bạn đang triển khai ranh giới subscribe cuối cùng có chủ đích.

## 5. Quan sát backpressure qua request(n)

Đoạn code Reactor sau là ví dụ thuần Java, chạy độc lập với Spring Integration. Nó dùng `BaseSubscriber` để chủ động yêu cầu số lượng phần tử:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandDemo {
    public static void main(String[] args) {
        Flux.range(1, 5)
            .doOnRequest(n -> System.out.println("requested=" + n))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("received=" + value);
                    request(1);
                }
            });
    }
}
~~~

Ban đầu subscriber chỉ yêu cầu 2 phần tử. Khi nhận mỗi phần tử, nó gọi `request(1)` để cấp thêm nhu cầu. Với nguồn `Flux.range` đồng bộ, lịch phát chính xác và log liên tiếp phụ thuộc cách Reactor điều phối yêu cầu phát sinh trong callback; ý nghĩa cần quan sát là **publisher được phép phát theo tổng demand**, thay vì đẩy vô hạn bất chấp subscriber.

### 5.1. Backpressure và rate limiting khác nhau

Giả sử một nguồn cố gắng phát dữ liệu nhanh, downstream chỉ có thể hoàn thành từng tác vụ chậm hơn. Có nhiều cơ chế điều tiết, mỗi cơ chế giải quyết bài toán khác nhau:

| Cơ chế | Điều chỉnh | Không tự bảo đảm |
|---|---|---|
| `request(n)` | Lượng phần tử subscriber muốn nhận | Nguồn không tuân thủ demand sẽ tự dừng |
| `limitRate(k)` | Cách Reactor chia nhu cầu upstream thành các đợt | Số request/giây hay giới hạn CPU tuyệt đối |
| `flatMap(mapper, concurrency)` | Số inner publishers được subscribe đồng thời | Bộ nhớ luôn cố định; còn prefetch/buffer và giá trị tạo ra |
| `concatMap(mapper)` | Xử lý inner publisher tuần tự, giữ thứ tự | Throughput cao khi thao tác chậm |
| `onBackpressureBuffer(capacity)` | Bộ đệm có giới hạn tại một đoạn hot/fast source | Lưu bền vững hoặc không mất message khi tràn |
| Rate limiter HTTP | Tốc độ request đến/đi ở biên HTTP | Demand Reactive Streams xuyên mọi adapter |
| Queue/broker | Đệm và tách nhịp xử lý, có thể lưu bền vững | Backpressure tự động cho mọi upstream |

Nếu `onBackpressureBuffer` đầy, cần chính sách overflow/lỗi rõ ràng. Với event nghiệp vụ không được phép mất, việc chuyển sang `onBackpressureDrop` hoặc `onBackpressureLatest` có thể gây mất dữ liệu và thường không phù hợp. Nếu bỏ phần tử là chấp nhận được (ví dụ một số dạng telemetry), phải ghi rõ quy tắc và quan sát số phần tử bị loại.

### 5.2. Ví dụ giới hạn số việc đồng thời

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import java.time.Duration;

Flux<String> processed = Flux.range(1, 20)
    .limitRate(8)
    .flatMap(i ->
        Mono.delay(Duration.ofMillis(100))
            .map(tick -> "processed-" + i),
        4); // Tối đa 4 inner publishers active cùng lúc.

processed.subscribe(
    System.out::println,
    error -> System.err.println("failed: " + error));
~~~

Ở đây `limitRate(8)` thay đổi cách yêu cầu đầu vào và tham số `4` giới hạn số inner publishers đồng thời ở `flatMap`. Nó **không** có nghĩa xử lý đúng 8 item mỗi giây. `flatMap` không cam kết giữ thứ tự kết quả khi các inner publishers hoàn thành ở các thời điểm khác nhau; nếu nghiệp vụ cần xử lý nối tiếp đúng thứ tự, dùng `concatMap` hoặc một cách tuần tự hóa phù hợp. Nếu ứng dụng phải ngừng có kiểm soát, cần quản lý `Disposable`/subscription thay vì chỉ dùng ví dụ `main` trên.

## 6. Channel quyết định hành vi của IntegrationFlow

Trong Spring Integration, `MessageChannel` tách phía gửi khỏi phía nhận. Cùng một handler có thể cư xử rất khác tùy loại channel nối trước nó:

| Channel | Kiểu dispatch | Tương tác với backpressure |
|---|---|---|
| `DirectChannel` | Subscriber nhận message theo đường gọi đồng bộ | Không tạo Reactive Streams demand; handler blocking có thể chặn caller |
| `ExecutorChannel` | Phân phối công việc qua `TaskExecutor` | Tách thread; cần giới hạn pool và queue, chưa tự thành reactive pipeline |
| `QueueChannel` | Queue nội bộ cho polling consumer | Dùng giới hạn dung lượng/timeout và poller; không phải `Publisher` |
| `FluxMessageChannel` | `MessageChannel` **và** `Publisher<Message<?>>` | Hỗ trợ reactive subscription, `request(n)` và liên kết upstream `Publisher` |
| Broker ngoài (JMS/Kafka/AMQP) | Theo cơ chế driver/adapter | Có prefetch, consumer concurrency, ACK, retry và buffer riêng |

### 6.1. FluxMessageChannel

`FluxMessageChannel` là kiểu channel đặc biệt kết hợp `MessageChannel` với `Publisher<Message<?>>`. Nó có `Flux` hot bên trong để nhận các message gửi qua `send()`, đồng thời triển khai `ReactiveStreamsSubscribableChannel` để nối một `Publisher<Message<?>>` ở upstream khi downstream có subscription.

Channel này **không phải** `SubscribableChannel` thông thường và cũng **không phải** `PollableChannel`. Do đó không dùng `@Poller` như với `QueueChannel`; consumer cần tương thích Reactive Streams. Spring Integration cung cấp `ReactiveStreamsConsumer` để các `MessageHandler` tham gia chuỗi reactive.

Điểm cần nhớ:

- Với upstream vốn là `Publisher<Message<?>>` có tuân thủ Reactive Streams, demand downstream có thể tác động đến lịch phát ở upstream.
- Với producer dùng API `channel.send(message)` đồng bộ để đẩy thật nhanh vào hot sink, không có cơ chế thần kỳ buộc producer chờ demand ở toàn bộ hệ thống. Cần thiết kế bộ đệm, tốc độ gửi và hành vi overload.
- Để bảo toàn backpressure qua nhiều endpoint, những endpoint trung gian phải duy trì reactive composition. Một handler gọi blocking JDBC trực tiếp hoặc đẩy sang queue không kiểm soát sẽ làm yếu hoặc đứt khả năng điều tiết xuyên suốt.

### 6.2. ReactiveStreamsConsumer và xử lý bất đồng bộ

Theo Spring Integration, `ReactiveStreamsConsumer` làm cầu nối giữa channel reactive và `MessageHandler`. Từ Spring Integration 5.5, consumer endpoint còn có tùy chọn `reactive()` để đưa logic consumer vào mô hình Reactive Streams. Từ 6.1, Java DSL hỗ trợ `handleReactive(...)` cho `ReactiveMessageHandler` trả về `Mono<Void>`, cho phép tích hợp side effect bất đồng bộ.

Với output channel bình thường, một handler trả payload reactive có thể cần cơ chế `async` và một subscriber phù hợp để tiêu thụ publisher. Khi output channel là `ReactiveStreamsSubscribableChannel`, framework có thể nối publisher vào chuỗi reactive thay vì bắt buộc gọi `block()` trong handler. Hãy luôn phân biệt **publisher đang là payload của một message** với **publisher đang điều phối các message trong flow**.

## 7. Ví dụ Spring Integration: FluxMessageChannel và ReactiveMessageHandler

Đoạn cấu hình dưới đây minh họa một nhánh reactive trong Spring Integration 6.1+. Trong ví dụ, consumer mô phỏng xử lý không chặn bằng `Mono.delay`; trong ứng dụng thật có thể thay bằng API reactive thích hợp.

~~~java
package com.example.integration;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.FluxMessageChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import reactor.core.publisher.Mono;

@Configuration
@EnableIntegration
public class ReactiveOrderFlowConfiguration {

    public record OrderEvent(String eventId, String orderId) {}

    @Bean
    public FluxMessageChannel reactiveOrders() {
        return new FluxMessageChannel();
    }

    @Bean
    public IntegrationFlow processReactiveOrders() {
        return IntegrationFlow.from("reactiveOrders")
            .handleReactive(message ->
                Mono.delay(Duration.ofMillis(100))
                    .doOnNext(ignored -> System.out.println(
                        "Processed: " + message.getPayload()))
                    .then())
            .get();
    }
}
~~~

Với ứng dụng Spring Boot có `spring-boot-starter-integration`, các bean trên có thể được tạo trong ApplicationContext. Để đưa một message vào channel từ code Java:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// channel được inject bằng @Qualifier("reactiveOrders").
boolean accepted = channel.send(
    MessageBuilder.withPayload(
        new ReactiveOrderFlowConfiguration.OrderEvent(
            "evt-001", "ORD-1001"))
        .build());
~~~

**Giới hạn của ví dụ:** lời gọi `send` là phía producer dùng API imperative; thành công của `send` chỉ cho biết việc gửi vào channel theo contract tương ứng, không bảo đảm handler đã chạy xong, HTTP đã ACK hay dữ liệu đã được lưu bền vững. Backpressure thể hiện rõ hơn khi **cả upstream lẫn downstream** đều dùng Reactive Streams theo subscription; ví dụ `send` chủ động cần chính sách chống quá tải riêng.

Ngoài cấu hình qua `FluxMessageChannel`, Java DSL cũng hỗ trợ bắt đầu IntegrationFlow từ `Publisher<Message<T>>` và xuất flow thành reactive publisher bằng `toReactivePublisher()`. Đây là các điểm nối hữu ích khi nguồn đã là Reactor (`Flux` từ WebClient hoặc R2DBC) hoặc khi downstream muốn trực tiếp subscribe.

## 8. WebFlux inbound: payload dạng Flux và HTTP SSE

### 8.1. Nhận request HTTP body dạng dòng

Spring Integration WebFlux có thể cấu hình `requestPayloadType` bằng `ResolvableType` cho payload reactive. Ví dụ rút gọn:

~~~java
import org.springframework.core.ResolvableType;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Bean
public IntegrationFlow incomingStringStream() {
    return IntegrationFlow
        .from(WebFlux.inboundChannelAdapter("/stream/events")
            .requestMapping(m -> m.methods(HttpMethod.POST))
            .requestPayloadType(
                ResolvableType.forClassWithGenerics(
                    Flux.class, String.class))
            .statusCodeFunction(m -> HttpStatus.ACCEPTED))
        .channel(c -> c.queue("streamPayloadQueue"))
        .get();
}
~~~

Đây là cấu hình **minh họa ranh giới HTTP → MessageChannel**, phù hợp với API trong tài liệu Spring Integration. Downstream nhận message có payload dạng `Flux<String>` và phải có bước **subscribe/split đúng chỗ** để xử lý từng phần tử. `QueueChannel` ở đây nhận message chứa publisher; bản thân queue **không** hiểu `request(n)` của từng phần tử bên trong payload. Cần cấu hình poller/handler tương ứng và kiểm tra codec, media type thực tế của client khi dùng streaming request.

### 8.2. Trả Flux dưới dạng Server-Sent Events

Khi HTTP client cần dòng cập nhật trạng thái, `WebFlux.inboundGateway(...)` có thể lấy reply publisher của flow và ghi thành SSE, chẳng hạn:

~~~java
import java.time.Duration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import reactor.core.publisher.Flux;

@Bean
public IntegrationFlow progressSse() {
    return IntegrationFlow
        .from(WebFlux.inboundGateway("/api/progress")
            .requestMapping(m -> m
                .methods(HttpMethod.GET)
                .produces(MediaType.TEXT_EVENT_STREAM_VALUE)))
        .handle((payload, headers) ->
            Flux.interval(Duration.ofMillis(500))
                .take(4)
                .map(i -> "progress-" + i))
        .get();
}
~~~

Thử gửi HTTP GET sau khi chạy ứng dụng:

~~~bash
curl -N -H 'Accept: text/event-stream' \
  http://localhost:8080/api/progress
~~~

WebFlux chịu trách nhiệm serialize stream theo `text/event-stream`; runtime có thể quản lý demand và cancellation theo kết nối HTTP. Nhưng **proxy, client, network và các buffer trung gian** có thể làm thay đổi độ trễ từng sự kiện. Nếu client rời giữa chừng, subscription HTTP có thể bị hủy; các công việc đã chuyển vào database, thread pool hoặc broker không được bảo đảm tự hủy theo.

## 9. WebFlux outbound gateway: Mono reply hay Flux reply?

Với outbound HTTP, `WebFluxRequestExecutingMessageHandler` dùng `WebClient` gọi dịch vụ ngoài. Hai cấu hình sau phục vụ hai kiểu response khác nhau.

**Một JSON object:**

~~~java
.handle(WebFlux.outboundGateway(
        "http://localhost:9090/api/orders/status")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(OrderStatus.class))
~~~

Gateway giải mã body theo `OrderStatus.class` và tạo reply message; payload đi tiếp thường là `OrderStatus` chứ không phải `Mono<OrderStatus>`. Đây là khác biệt giữa **publisher dùng trong cơ chế HTTP I/O** và **kiểu payload mà Spring Integration gửi cho downstream**.

**HTTP response chứa dòng nhiều phần tử:**

~~~java
.handle(WebFlux.outboundGateway(
        "http://localhost:9090/api/orders/updates")
    .httpMethod(HttpMethod.GET)
    .expectedResponseType(OrderStatus.class)
    .replyPayloadToFlux(true))
~~~

Khi server và codec tương thích streaming response, reply message có thể có **payload `Flux<OrderStatus>`**. Cần xử lý publisher này downstream (ví dụ splitter reactive) nếu mục tiêu là tạo các message riêng lẻ. Nó không tự tách thành `Flux<Message<OrderStatus>>` chỉ vì bật `replyPayloadToFlux(true)`.

Nếu remote trả response thường (không có streaming media type), không bật tùy chọn này một cách máy móc. Với streaming, phải xác định **không có buffering không giới hạn**, tốc độ tiêu thụ và hành vi khi upstream/người dùng đóng kết nối.

## 10. Ranh giới backpressure khi nối các hệ thống ngoài

Backpressure chỉ truyền thẳng qua những thành phần tương thích. Với các adapter trong phạm vi module, cần phân biệt:

| Hệ thống/đoạn | Cơ chế điều tiết thường dùng | Đừng giả định |
|---|---|---|
| WebFlux inbound request body | Subscriber demand, codec, giới hạn HTTP | HTTP client bên ngoài sẽ dừng mọi request mới |
| WebFlux outbound `WebClient` | Reactive publisher, client connector và limits | API đối tác chắc chắn nhận dữ liệu theo demand của IntegrationFlow |
| `FluxMessageChannel` | Publisher/subscriber và `request(n)` | `send()` đồng bộ tự chuyển thành backpressure hoàn chỉnh |
| JDBC đồng bộ | Connection pool, executor, rate limit | JDBC blocking tự chạy trên event-loop an toàn |
| R2DBC/reactive driver | Publisher demand, pool/concurrency | Mọi DB operation đều hoàn tất nhanh hay không cần transaction |
| JMS / AMQP | Listener concurrency, prefetch, ACK, queue limits | Reactive demand sẽ tự đi ngược qua broker tùy ý |
| Kafka | Poll/batch, pause/resume, consumer lag, offset commit | `request(n)` của Reactor tự điều khiển tất cả offset/poll |
| File / SFTP polling | `maxMessagesPerPoll`, chu kỳ poll, tải I/O | Poller thông thường tuân thủ Reactive Streams như `Flux` |

Với Spring Integration, một `SourcePollingChannelAdapter` có output là `ReactiveStreamsSubscribableChannel` có thể được bridge sang cách phát dựa trên Reactor và nhu cầu downstream. Tuy nhiên, cơ chế kích hoạt theo trigger, thao tác đọc nguồn thực tế và giới hạn nguồn vẫn phải được kiểm tra; filesystem hoặc SFTP không tự có Reactive Streams protocol chỉ vì flow dùng `FluxMessageChannel`.

### 10.1. Ba kiểu tích hợp cần phân biệt

~~~mermaid
flowchart TB
    subgraph Reactive["Chuỗi reactive xuyên suốt"]
      R1["Publisher"] --> R2["FluxMessageChannel"] --> R3["ReactiveStreamsConsumer"]
      R3 -.->|"demand ngược chiều"| R2
      R2 -.->|"demand ngược chiều"| R1
    end
    subgraph Buffered["Đường qua queue"]
      Q1["HTTP / source"] --> Q2["QueueChannel (bounded)"] --> Q3["Poller"] --> Q4["Handler"]
    end
    subgraph External["Đường qua broker"]
      E1["IntegrationFlow"] --> E2["Kafka / JMS / AMQP"] --> E3["Consumer khác"]
    end
~~~

Ba sơ đồ cùng có thể phục vụ bài toán tích hợp, nhưng mỗi bên có bộ quy tắc riêng: reactive demand, capacity/timeout của queue, hay ACK/prefetch/offset của broker. Cần đo và quản lý **từng ranh giới**, thay vì áp một giải pháp chung cho mọi nguồn dữ liệu.

## 11. Xử lý nguồn blocking trong flow reactive

Sai lầm thường gặp là gọi JDBC blocking hoặc `Thread.sleep` ngay trong một `map`/`flatMap` chạy trên event-loop:

~~~java
// Không nên làm nếu repository.findById là lệnh JDBC blocking:
// Giả định findById trả Optional<Order> như Spring Data.
Flux<Optional<Order>> wrong = incoming.map(
    event -> jdbcRepository.findById(event.orderId()));
~~~

Một cách cô lập thao tác blocking ở tầng Reactor:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux<Order> better = incoming.flatMap(event ->
    Mono.fromCallable(() ->
            jdbcRepository.findById(event.orderId()))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(optional -> Mono.justOrEmpty(optional)),
    8);
~~~

Ví dụ giả định `findById` trả `Optional<Order>` như Spring Data; cần thêm `import java.util.Optional;` cho ví dụ đầu. `Mono.justOrEmpty(optional)` bỏ qua bản ghi không có kết quả. Trong ứng dụng thật, có thể cần phát lỗi hoặc kết quả NOT_FOUND thay vì bỏ qua. Việc đặt blocking call vào `boundedElastic` và giới hạn số thao tác đồng thời ở `flatMap` **không thay thế** connection pool, transaction boundary hay giới hạn tải của database. Đối với flow phức tạp, một API reactive thực sự như R2DBC giúp giảm số lần chuyển mô hình.

Khi dùng `publishOn(scheduler)` hoặc `subscribeOn(scheduler)`, cần hiểu khác biệt:

- `subscribeOn` ảnh hưởng đến ngữ cảnh subscription và giai đoạn upstream tương ứng.
- `publishOn` chuyển thực thi downstream sang scheduler, với queue/prefetch và chi phí chuyển thread riêng.
- Cả hai **không** biến một thao tác blocking thành non-blocking; chúng chỉ đổi nơi thực thi thao tác đó.
- `Schedulers.boundedElastic()` có giới hạn nội bộ, vẫn cần quản lý concurrency bên ngoài nếu tài nguyên DB/API rất hạn chế.

## 12. Lỗi, cancellation, retry và idempotency

Reactive Streams mang ba dạng tín hiệu chính: dữ liệu `onNext`, kết thúc thành công `onComplete` và kết thúc lỗi `onError`. Một lỗi chưa được xử lý làm chuỗi tương ứng kết thúc; retry tạo subscription/lượt xử lý mới theo cách được cấu hình.

~~~java
Flux<String> resilient = remoteUpdates()
    .timeout(Duration.ofSeconds(3))
    .retryWhen(
        reactor.util.retry.Retry
            .backoff(2, Duration.ofMillis(200))
            .filter(error -> isTransient(error)))
    .doOnError(error -> recordFailure(error));
~~~

Đây là ví dụ khung: `remoteUpdates()`, `isTransient(...)` và `recordFailure(...)` là các hàm ứng dụng phải tự cài đặt. `Retry.backoff(2, ...)` thể hiện **tối đa hai lần thử lại** sau lần ban đầu đối với lỗi vượt qua bộ lọc. Không nên retry mọi lỗi codec, authentication hay validation; cũng không nên retry POST có side effect nếu hệ thống ngoài không hỗ trợ idempotency.

**Cancellation** xảy ra khi downstream không muốn nhận thêm dữ liệu. Chẳng hạn HTTP client đóng kết nối SSE; publisher có thể nhận tín hiệu hủy. Điều đó **không khẳng định** message đã gửi sang Kafka bị thu hồi hoặc transaction database đã rollback. Cần định nghĩa hợp đồng hủy riêng khi thao tác vượt qua biên hệ thống.

**Error channel của Spring Integration** và `onErrorResume`/`retryWhen` của Reactor phục vụ các mức xử lý lỗi khác nhau. Nếu dùng một `ReactiveMessageHandler` trong `ReactiveStreamsConsumer`, lỗi có thể nằm trong pipeline reactive. Nếu đẩy sang adapter imperative hay queue, lỗi còn có thể được thể hiện bằng `ErrorMessage`, advice hoặc retry của poller. Nên thử từng đường lỗi thay vì suy ra cách xử lý từ tên kiểu channel.

### 12.1. Chọn chiến lược khi downstream quá chậm

| Dữ liệu | Chiến lược ưu tiên | Rủi ro phải chấp nhận hoặc xử lý |
|---|---|---|
| Lệnh thanh toán/đơn hàng | Queue/broker bền vững, giới hạn tải, retry, idempotency | Trùng event, backlog, ACK/commit |
| Dữ liệu đo lường cho biểu đồ realtime | `onBackpressureLatest`/drop có kiểm soát, thống kê số mất | Mất điểm dữ liệu trung gian |
| Stream báo cáo cần đủ mọi bản ghi | Demand và buffer có giới hạn hoặc lưu tạm bền vững | Latency lớn, stream kéo dài |
| Truy vấn HTTP đồng bộ | Giới hạn request/concurrency và timeout, trả 429/503 khi cần | Client phải retry theo chính sách |

Đừng dùng một buffer vô hạn để “giải quyết” backpressure. Buffer chỉ chuyển nơi tích tụ dữ liệu, không làm tăng năng lực xử lý của downstream.

## 13. Quan sát và kiểm thử

Một flow reactive chạy đúng trong ví dụ vài item vẫn có thể gặp lỗi khi tải thực tăng. Những chỉ số cần theo dõi gồm:

1. **Ingress rate / completion rate:** số message đến và hoàn tất theo thời gian.
2. **In-flight operations:** số HTTP/DB requests đang xử lý và số subscription còn sống.
3. **Buffer/queue depth:** số phần tử đang chờ và thời gian chờ lớn nhất; cảnh báo trước khi tràn.
4. **Latency:** p50/p95/p99 qua từng đoạn HTTP → channel → handler → broker/DB.
5. **Error/cancel/retry:** số lần `onError`, timeout, cancel, dropped message và retry.
6. **Hạ tầng:** event-loop saturation, thread pool, connection pool, consumer lag, HTTP status 429/5xx và memory/GC.

Một bài kiểm thử demand cơ bản có thể dùng `reactor-test` và `StepVerifier`:

~~~groovy
// testImplementation trong build.gradle
testImplementation 'io.projectreactor:reactor-test'
~~~

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BackpressureTest {
    @Test
    void emitsOnlyAfterDemand() {
        Flux<Integer> numbers = Flux.range(1, 3);

        StepVerifier.create(numbers, 0)
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }
}
~~~

Test đặt initial request bằng `0`, sau đó cấp demand theo từng đợt. Nó kiểm chứng một publisher Reactor cơ bản; **không** chứng minh end-to-end backpressure cho HTTP server, database, queue và broker. Để kiểm thử hệ thống thực, cần thêm test với HTTP client chậm, consumer chậm, request bị hủy, queue đầy và server trả lỗi.

## 14. Bài thực hành vận dụng

1. Chạy `DemandDemo`, thay `request(2)` bằng `request(1)` rồi theo dõi thứ tự tín hiệu `doOnRequest` và `onNext`. Giải thích vì sao số demand không phải giới hạn request/giây.
2. Sử dụng `Flux.range(1, 20)` cùng `flatMap(..., 4)`, thay bằng `concatMap(...)` và đo sự khác biệt về concurrency và thứ tự kết quả.
3. Tạo `FluxMessageChannel` như mục 7, gửi một message từ Java và quan sát consumer. Giải thích tại sao `send() == true` chưa cho biết xử lý xong.
4. Thử cấu hình inbound HTTP payload `Flux<String>`, gửi request có codec hỗ trợ streaming và bổ sung downstream consumer xử lý publisher đúng cách. So sánh `Message<Flux<String>>` với `Flux<Message<String>>`.
5. Gọi một remote HTTP API phát SSE, cấu hình outbound gateway với `replyPayloadToFlux(true)` và xử lý từng phần tử bằng subscriber hoặc splitter reactive. Quan sát hành vi khi server tạm dừng phát.
6. Giả lập downstream chậm và nguồn đến nhanh; đặt buffer có giới hạn, quan sát overflow, sau đó thử một chiến lược giảm tải phù hợp với dữ liệu không được phép mất.
7. Đưa một JDBC blocking operation vào ví dụ, chuyển nó sang `boundedElastic` và giới hạn concurrency. Theo dõi lượng request DB và thời gian chờ trước/sau khi sửa.
8. Thử hủy SSE giữa chừng và đặt HTTP timeout. Xác định đoạn nào được hủy, đoạn nào vẫn tiếp tục, và điều gì xảy ra nếu một message đã được gửi sang Kafka/JMS.

**Tình huống suy luận:** ứng dụng nhận webhook thanh toán với tốc độ tăng đột biến, ghi database rồi phát thông báo Kafka. Hãy chỉ ra ranh giới Reactive Streams dừng ở đâu, cơ chế nào bảo đảm không mất message, cách giới hạn tải và thời điểm nào được phép trả HTTP `202 Accepted`. Việc chỉ đổi `DirectChannel` thành `FluxMessageChannel` đã đáp ứng toàn bộ yêu cầu hay chưa?

## 15. Tài liệu tham khảo

- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): contract reactive, `FluxMessageChannel`, `ReactiveStreamsConsumer`, `handleReactive`, source adapter và Java DSL.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): khác biệt giữa `DirectChannel`, `QueueChannel`, `ExecutorChannel` và `FluxMessageChannel`.
- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): inbound request payload dạng `Flux`, SSE, outbound `replyPayloadToFlux` và `WebClient`.
- [Project Reactor Reference — Backpressure](https://projectreactor.io/docs/core/release/reference/): `request(n)`, `BaseSubscriber`, `limitRate`, `flatMap` và các chiến lược overflow.
- [Reactive Streams Specification](https://www.reactive-streams.org/): các giao diện `Publisher`, `Subscriber` và `Subscription`, nguyên tắc non-blocking backpressure.

> **Ghi nhớ:** `Mono` và `Flux` mô tả dữ liệu bất đồng bộ; `request(n)` mô tả nhu cầu bên nhận. `FluxMessageChannel` có thể nối demand trong một Spring Integration flow reactive, nhưng backpressure không tự động đi xuyên HTTP client độc lập, JDBC blocking, queue hay broker. Thiết kế ổn định cần đồng thời có giới hạn tải, buffer phù hợp, xử lý lỗi, idempotency và quan sát từng ranh giới kết nối.
