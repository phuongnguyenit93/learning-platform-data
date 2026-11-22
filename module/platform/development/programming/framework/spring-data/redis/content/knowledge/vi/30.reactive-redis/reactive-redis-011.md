# Pub/Sub và Streams trong ứng dụng WebFlux với Spring Data Redis

## 1. Vì sao WebFlux cần phân biệt Redis Pub/Sub và Redis Streams?

Một ứng dụng xây dựng bằng **Spring WebFlux** thường phải phục vụ nhiều kết nối đồng thời: API trả dữ liệu bất đồng bộ, Server-Sent Events (SSE), WebSocket, cập nhật realtime, hoặc xử lý sự kiện nền. Spring Data Redis hỗ trợ API **reactive** dựa trên Reactor (`Mono`, `Flux`) để giao tiếp Redis mà không buộc ứng dụng chặn thread cho mỗi I/O request theo cách của API đồng bộ.

Tuy nhiên, **reactive** mô tả cách ứng dụng tiêu thụ và xử lý luồng dữ liệu; nó **không** tự thay đổi cam kết giao thông điệp của Redis:

- **Redis Pub/Sub:** phát thông điệp tới những subscriber đang kết nối. Không có backlog/ACK/replay theo consumer. Phù hợp thông báo realtime có thể mất, tín hiệu cache invalidation, cập nhật UI đang online.
- **Redis Streams:** ghi bản ghi vào một log Redis có ID, có thể đọc lại; consumer group hỗ trợ Pending Entries List (PEL), acknowledgment (`XACK`) và phục hồi pending bằng claim. Phù hợp xử lý công việc/sự kiện cần theo dõi tiến độ, retry và khả năng đọc lại trong giới hạn retention.
- **Reactor `Flux`:** mô hình Publisher có subscription, cancellation và backpressure ở phía Java. Nó không biến Redis Pub/Sub thành hệ thống truyền tin có retention và cũng không tự ACK message trong Redis Streams.

Một hệ thống realtime điển hình:

```text
                  ỨNG DỤNG WEBFLUX
                          |
             +------------+------------+
             |                         |
             v                         v
       Redis Pub/Sub               Redis Streams
       (tín hiệu realtime)         (log + xử lý bền vững hơn)
             |                         |
        Flux message              Flux records
             |                         |
             v                         v
     SSE/WebSocket clients       Worker xử lý sự kiện
             |                         |
       đang online mới nhận       business side effect
                                       |
                                       v
                                    XACK
```

Điều quan trọng nhất là **chọn cơ chế theo yêu cầu giao thông điệp**, rồi mới quyết định dùng WebFlux/Reactor để triển khai I/O.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao `ReactiveRedisTemplate` và `ReactiveRedisMessageListenerContainer` phù hợp cho ứng dụng WebFlux.
2. Phân biệt hành vi `Flux` ở mức subscriber với cơ chế lưu trữ Pub/Sub và Streams của Redis.
3. Publish/subscribe qua `ReactiveStringRedisTemplate` và `ReactiveRedisMessageListenerContainer`.
4. Chuyển thông báo Pub/Sub thành SSE, hiểu những giới hạn của SSE và client chậm.
5. Ghi và đọc Stream bằng API reactive của Spring Data Redis.
6. Hiểu vị trí của `XREADGROUP`, `XACK`, PEL và quy trình khôi phục message chưa ACK.
7. Xử lý lỗi và retry mà không gây mất hoặc lặp side effect ngoài ý định.
8. Thiết kế consumer lifecycle, backpressure, serialization, monitoring và triển khai nhiều instance.
9. Tránh các lỗi phổ biến như `.block()` trên event-loop, quên `.subscribe()`, hoặc ACK trước khi commit nghiệp vụ.

## 2. Ba tầng cần phân biệt: WebFlux, Reactive Redis và Redis server

Các tầng liên quan nhưng không đồng nhất:

| Tầng | Trách nhiệm | Ví dụ |
|---|---|---|
| Spring WebFlux | HTTP, SSE, WebSocket, request/response, event-loop | `@RestController`, `Flux<ServerSentEvent<?>>` |
| Spring Data Redis Reactive | Tạo Reactive Streams Publisher cho lệnh Redis | `ReactiveStringRedisTemplate`, `ReactiveRedisMessageListenerContainer` |
| Redis server | Lưu Stream, fan-out Pub/Sub, quản lý consumer group/PEL | `PUBLISH`, `XADD`, `XREADGROUP`, `XACK` |
| Reactor | Composition, cancellation, error propagation, demand | `map`, `flatMap`, `concatMap`, `retryWhen`, `onBackpressure...` |
| Nghiệp vụ | Xác định khi nào được xem là hoàn thành | Commit database, gọi API ngoài, idempotency |

Một lời gọi reactive:

```java
Mono<Long> result = redis.convertAndSend(
    "notifications",
    "hello"
);
```

`result` là một **Publisher mô tả thao tác**. Trong mô hình lazy phổ biến của Reactor, việc gán `Mono` vào biến **chưa có nghĩa lệnh đã được gửi ngay**. Lệnh thường được thực thi khi có subscription từ WebFlux hoặc một subscriber chủ động.

Ngược lại, nếu gọi:

```java
redis.convertAndSend("notifications", "hello");
```

rồi bỏ `Mono` đi, ứng dụng có thể **không publish gì cả** vì không có ai subscribe. Đây là lỗi rất dễ mắc khi chuyển từ `StringRedisTemplate` (đồng bộ) sang `ReactiveStringRedisTemplate` (reactive).

### 2.1. Reactive không có nghĩa tự động chạy song song

`Flux`/`Mono` giúp mô tả chuỗi thao tác bất đồng bộ; chúng không tự biến mọi xử lý thành đa luồng hay đảm bảo song song.

- `map` biến đổi dữ liệu, thường thực thi trên thread phát tín hiệu của upstream.
- `flatMap` kết hợp các Publisher và có thể cho phép nhiều tác vụ in-flight, tùy overload và concurrency.
- `concatMap` xử lý các Publisher bên trong theo thứ tự, hữu ích khi cần tránh chồng lấn side effect.
- `publishOn` thay scheduler cho các bước downstream.
- `subscribeOn` điều khiển context subscription của upstream, không thay đổi bản chất API blocking.

Nếu dùng một API Redis đồng bộ hoặc JDBC blocking trong `map`, thread event-loop của WebFlux vẫn có thể bị chặn dù method trả `Flux`.

## 3. Dependency và cấu hình cơ bản

Với Spring Boot và Maven, một ví dụ cấu hình:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
</dependencies>
```

Với Gradle:

```gradle
implementation 'org.springframework.boot:spring-boot-starter-webflux'
implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
```

Ví dụ `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 3s
```

Các địa chỉ và thời gian timeout chỉ minh họa cho môi trường phát triển. Trong production cần bổ sung authentication, TLS, cấu hình cluster/sentinel (nếu có), timeout và retry phù hợp.

Spring Data Redis Reactive thường sử dụng **Lettuce** làm connector reactive. Không nên giả định mọi `RedisConnectionFactory` hoặc client Redis đều hỗ trợ đầy đủ các API reactive.

Các thành phần điển hình:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.listener.ReactiveRedisMessageListenerContainer;
```

`ReactiveStringRedisTemplate` thuận tiện cho key/value văn bản UTF-8. `ReactiveRedisTemplate<K, V>` cho phép cấu hình serialization context tùy kiểu dữ liệu. Dù dùng reactive, bạn vẫn phải xác định **định dạng bytes của key, channel, payload và field Stream**.

### 3.1. Không tự chuyển API blocking thành reactive bằng cách đổi kiểu trả về

Ví dụ có vấn đề:

```java
@GetMapping("/value")
public Mono<String> value() {
    String value = stringRedisTemplate.opsForValue().get("key");
    return Mono.justOrEmpty(value);
}
```

Ở đây `stringRedisTemplate` là API blocking; lệnh Redis đã chạy và có thể chặn thread trước khi `Mono` được tạo.

API reactive tương ứng:

```java
@GetMapping("/value")
public Mono<String> value() {
    return reactiveStringRedisTemplate
        .opsForValue()
        .get("key");
}
```

Một ứng dụng WebFlux cần giữ đường xử lý I/O không blocking để tận dụng lợi ích về concurrency của mô hình phản ứng.

Nếu bắt buộc tích hợp legacy blocking I/O, có thể chuyển phần việc đó sang scheduler thích hợp với `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, nhưng đây là **cách cô lập blocking**, không biến thư viện blocking thành non-blocking. Tài nguyên thread vẫn có giới hạn và cần đo latency.

## 4. Pub/Sub trong WebFlux: nhận tín hiệu khi đang online

Redis Pub/Sub hoạt động theo cơ chế phát thông điệp từ publisher tới những subscriber hiện đang đăng ký.

```text
Service A                     Redis                      Service B
    |                           |                            |
    | PUBLISH events.order      |                            |
    +-------------------------->|                            |
    |                           |---- Pub/Sub message ------>|
    |                           |                            |
    |                           |                     Flux onNext(...)
    |                           |                            |
    |                           |                       SSE/WebSocket
```

Một publication có thể đến tất cả subscriber phù hợp (fan-out). Redis Pub/Sub không yêu cầu subscriber ACK và không giữ một entry bền vững để subscriber đăng ký sau đọc lại.

Nếu Service B mất kết nối khi event được publish, nó có thể mất event ấy vĩnh viễn ở tầng Pub/Sub. WebFlux và Reactor không làm thay đổi điều đó.

### 4.1. Channel thường và pattern

Dùng channel chính xác:

```redis
SUBSCRIBE orders.created
```

Dùng pattern subscription:

```redis
PSUBSCRIBE orders.*
```

Một publisher vẫn gửi tới channel cụ thể:

```redis
PUBLISH orders.created '{"orderId":"o-101"}'
```

Pattern chỉ thay đổi **phạm vi nhận** của subscriber. Nó không phải queue wildcard, không replay message và không tự bảo đảm độ tin cậy.

Trong Spring Data Redis:

```java
new ChannelTopic("orders.created")
new PatternTopic("orders.*")
```

`ChannelTopic` biểu diễn exact subscription; `PatternTopic` biểu diễn so khớp theo glob. Nếu một subscriber đăng ký cả hai và cả hai cùng khớp, một publication có thể dẫn đến nhiều lượt nhận về mặt subscription. Vì vậy, business handler có side effect cần tránh registration chồng lấn hoặc có idempotency.

## 5. Publish thông điệp bằng ReactiveStringRedisTemplate

Giả sử hệ thống phát event JSON dưới dạng String:

```java
package com.example.realtime;

public record RealtimeEvent(
    String eventId,
    String type,
    String payload
) {}
```

Một service publish:

```java
package com.example.realtime;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class RealtimePublisher {

    private final ReactiveStringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public RealtimePublisher(
            ReactiveStringRedisTemplate redis,
            ObjectMapper objectMapper) {
        this.redis = redis;
        this.objectMapper = objectMapper;
    }

    public Mono<Long> publish(RealtimeEvent event) {
        return Mono.fromCallable(
                () -> objectMapper.writeValueAsString(event))
            .flatMap(json ->
                redis.convertAndSend("events.realtime", json)
            );
    }
}
```

`ObjectMapper.writeValueAsString` là thao tác CPU cục bộ, không phải lệnh I/O chờ Redis. Với object nhỏ nó thường nhanh; với payload lớn hoặc mapping phức tạp cần xem xét chi phí CPU trên event-loop và giới hạn payload.

Tạo endpoint publish:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PublishController {

    private final RealtimePublisher publisher;

    public PublishController(RealtimePublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/api/events")
    public Mono<ResponseEntity<Void>> publish(
            @RequestBody Mono<RealtimeEvent> request) {

        return request
            .flatMap(publisher::publish)
            .thenReturn(ResponseEntity.accepted().build());
    }
}
```

WebFlux subscribe vào `Mono` trả từ controller để hoàn tất response, do đó thao tác Redis mới được thực thi theo chuỗi phản ứng.

**Lưu ý:** `convertAndSend` trả số liên quan tới subscriber nhận publication theo ngữ nghĩa Redis. Con số này **không phải ACK nghiệp vụ**, không chứng minh subscriber đã xử lý JSON thành công và cũng không chứng minh mọi WebSocket/SSE client nhận được payload.

### 5.1. Không gọi `subscribe()` tùy tiện trong controller

Tránh viết:

```java
@PostMapping("/api/events")
public Mono<Void> publish(@RequestBody RealtimeEvent event) {
    publisher.publish(event).subscribe(); // Fire-and-forget khó quản lý.
    return Mono.empty();
}
```

Với cách này, HTTP response có thể trả xong trước khi publish hoàn tất; exception của Redis không được nối vào response flow và việc cancellation/shutdown khó kiểm soát.

Tốt hơn là **return Publisher**:

```java
@PostMapping("/api/events")
public Mono<Void> publish(@RequestBody Mono<RealtimeEvent> event) {
    return event
        .flatMap(publisher::publish)
        .then();
}
```

Chỉ chủ động `.subscribe()` tại **ranh giới lifecycle** được quản lý rõ, ví dụ background worker, service khởi động và dừng được, hoặc một consumer độc lập với HTTP request.

## 6. Subscribe với ReactiveRedisMessageListenerContainer

Để lắng nghe Pub/Sub theo API reactive, Spring Data Redis cung cấp `ReactiveRedisMessageListenerContainer`.

Cấu hình bean:

```java
package com.example.realtime;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.listener.ReactiveRedisMessageListenerContainer;

@Configuration
public class ReactivePubSubConfiguration {

    @Bean
    ReactiveRedisMessageListenerContainer reactiveRedisListener(
            ReactiveRedisConnectionFactory connectionFactory) {

        return new ReactiveRedisMessageListenerContainer(
            connectionFactory
        );
    }
}
```

Nhận dữ liệu theo channel:

```java
import org.springframework.data.redis.listener.ChannelTopic;
import reactor.core.publisher.Flux;

Flux<String> messages = listenerContainer
    .receive(new ChannelTopic("events.realtime"))
    .map(message -> message.getMessage());
```

Theo cách dùng API Spring Data Redis Reactive thông dụng, `receive(...)` trả một `Flux` thông điệp có metadata về channel và payload. Kiểu chính xác và các overload có thể khác theo phiên bản hoặc serializer; khi dùng typed receive, cần cấu hình serialization context tương ứng.

Điểm thiết yếu: **`receive` đại diện cho subscription vào Redis Pub/Sub**, nhưng hiệu lực kết nối và lắng nghe gắn với việc có subscriber thực sự đối với `Flux` này.

### 6.1. Subscription là tài nguyên cần quản lý

Khi có Reactor subscriber:

```text
Application subscriber
       |
       | subscribe()
       v
ReactiveRedisMessageListenerContainer
       |
       | Redis SUBSCRIBE
       v
Redis channel "events.realtime"
       |
       | Redis PUBLISH
       v
Flux onNext(message)
```

Khi subscription bị cancel hoặc application shutdown, tài nguyên lắng nghe cần được giải phóng theo lifecycle của container/connection.

Không nên tạo mới một listener container hoặc một kết nối Redis cho từng message. Nếu endpoint SSE tạo một subscription Redis cho mỗi HTTP client, số subscription và network/resource usage có thể tăng theo lượng client; cần chủ động quyết định kiến trúc fan-out.

### 6.2. Pattern subscription

Có thể nhận nhiều channel:

```java
Flux<String> orderEvents = listenerContainer
    .receive(new PatternTopic("orders.*"))
    .map(message -> message.getMessage());
```

Nếu cần phân biệt `orders.created` và `orders.cancelled`, nên giữ metadata tên channel thực tế thay vì chỉ lấy body. Tùy overload, `ChannelMessage`/Message wrapper có phương thức truy cập channel và message tương ứng.

Ví dụ ý tưởng:

```java
listenerContainer
    .receive(new PatternTopic("orders.*"))
    .doOnNext(message -> {
        // message.getChannel(): channel thực tế
        // message.getMessage(): payload
    });
```

Không dùng pattern string `orders.*` như event type thực tế.

## 7. Chuyển Pub/Sub thành Server-Sent Events (SSE)

SSE cho phép server giữ một HTTP connection và phát nhiều event theo thời gian. Trong WebFlux, controller có thể trả `Flux<ServerSentEvent<T>>`.

Ví dụ:

```java
package com.example.realtime;

import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.ReactiveRedisMessageListenerContainer;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventFeedController {

    private final ReactiveRedisMessageListenerContainer container;

    public EventFeedController(
            ReactiveRedisMessageListenerContainer container) {
        this.container = container;
    }

    @GetMapping(
        path = "/api/events/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> stream() {
        return container
            .receive(new ChannelTopic("events.realtime"))
            .map(message ->
                ServerSentEvent.<String>builder()
                    .event("realtime")
                    .data(message.getMessage())
                    .build()
            );
    }
}
```

Luồng dữ liệu:

```text
Redis PUBLISH events.realtime
        |
        v
Reactive Redis Flux
        |
        v
Spring WebFlux handler
        |
        v
text/event-stream over HTTP
        |
        v
Browser EventSource / SSE client
```

Ví dụ client JavaScript:

```javascript
const feed = new EventSource("/api/events/stream");

feed.addEventListener("realtime", event => {
  const data = JSON.parse(event.data);
  console.log(data);
});

feed.onerror = error => {
  console.error("SSE connection interrupted", error);
};

// Khi rời trang hoặc không cần nghe:
feed.close();
```

**Giới hạn quan trọng:** SSE client kết nối muộn có thể bỏ lỡ các Pub/Sub message trước đó. `EventSource` có cơ chế reconnect ở HTTP/SSE, nhưng **Redis Pub/Sub không tự replay** các publication đã xảy ra trong thời gian ngắt kết nối.

### 7.1. SSE ID và Last-Event-ID không tự tạo lịch sử

SSE có thể gửi trường `id`, ví dụ:

```java
ServerSentEvent.<String>builder()
    .id(eventId)
    .event("realtime")
    .data(json)
    .build();
```

Trình duyệt có thể đưa `Last-Event-ID` khi reconnect. Nhưng nếu nguồn dữ liệu chỉ là Pub/Sub, server **không có log Redis Pub/Sub để đọc bù theo ID đó**.

Để hỗ trợ resume thực sự, có thể kết hợp:

- Redis Streams lưu lịch sử sự kiện với Stream ID.
- Pub/Sub làm tín hiệu realtime.
- Khi HTTP reconnect, server đọc các Stream entry sau ID client đã lưu, sau đó chuyển sang live feed theo cơ chế chống mất khoảng chuyển tiếp.

Thiết kế này cần xử lý race giữa truy vấn lịch sử và bắt đầu nhận live event, trùng ID, retention và thứ tự. Đặt một `id` trong SSE đơn thuần **chưa đủ tạo khả năng replay**.

### 7.2. Một SSE client không nên có nghĩa một Redis connection riêng

Ví dụ controller ở trên dễ hiểu nhưng có thể phát sinh nhiều subscriptions khi có nhiều HTTP clients. Với lưu lượng lớn, cân nhắc một **shared hot Flux** hoặc service fan-out tập trung:

```text
                  Redis Pub/Sub
                       |
                 1 listener/instance
                       |
               Shared event stream
                 /      |       \
                v       v        v
              SSE A   SSE B    SSE C
```

Reactor có các công cụ multicast/share hoặc `Sinks.Many` cho việc fan-out. Tuy vậy, shared Flux phải có chính sách:

- Subscriber đến muộn có được nhận event cũ hay không?
- Client chậm có làm tăng buffer hay bị drop?
- Không còn client thì có hủy Redis subscription không?
- Khi Redis reconnect thì các client hiện tại được thông báo thế nào?
- Khi có nhiều instance WebFlux, mỗi instance cần nguồn event riêng hay dùng service event gateway?

Không nên dùng `cache()` của Reactor một cách mù quáng cho luồng Pub/Sub vô hạn vì có nguy cơ giữ toàn bộ message trong bộ nhớ và tạo memory leak.

## 8. Backpressure: Flux có demand nhưng Redis Pub/Sub vẫn push

Reactive Streams cho phép downstream báo cho upstream biết cần bao nhiêu phần tử qua tín hiệu `request(n)`. Cơ chế đó đặc biệt hữu ích cho những nguồn có thể tạm dừng hoặc điều tiết việc sinh dữ liệu.

Redis Pub/Sub không cung cấp một cơ chế per-subscriber ACK/demand tương đương. Publisher có thể tiếp tục gửi thông điệp dù một SSE client chậm.

Mô hình:

```text
Publisher PUBLISH 10.000 msg/s
            |
            v
Redis Pub/Sub transport
            |
            v
Reactive listener -> Flux
            |
            v
SSE client đọc 50 msg/s
            |
            +--> Chênh lệch tốc độ phải được xử lý:
                  buffer / drop / disconnect / coalesce
```

Do đó, khi nói “đã dùng Flux nên backpressure được giải quyết”, cần hỏi **backpressure được thực thi đến tầng nào**. Từ Java tới SSE downstream có thể có điều tiết, nhưng nó không bảo đảm Redis publisher tự giảm tốc hoặc Redis giữ bền vững phần message chưa tiêu thụ.

### 8.1. Các lựa chọn đối với consumer chậm

| Chiến lược | Hành vi | Phù hợp |
|---|---|---|
| Buffer có giới hạn | Giữ tạm message trong RAM | Burst ngắn, payload nhỏ |
| Drop latest | Bỏ message mới khi quá tải | Một số telemetry chấp nhận bỏ mẫu |
| Drop oldest | Bỏ message cũ để giữ trạng thái gần nhất | Dashboard thể hiện trạng thái hiện thời |
| Latest only | Chỉ giữ cập nhật mới nhất | Giá trị như CPU usage, presence |
| Fail/disconnect | Ngắt client không theo kịp | Khi cần giới hạn tài nguyên rõ ràng |
| Chuyển sang Streams | Đọc bù từ log có retention | Khi message không được phép biến mất chỉ vì client chậm |

Ví dụ minh họa cho luồng trạng thái có thể bỏ cập nhật cũ:

```java
Flux<String> latestUpdates = container
    .receive(new ChannelTopic("metrics.current"))
    .map(message -> message.getMessage())
    .onBackpressureLatest();
```

`onBackpressureLatest()` có thể bỏ qua nhiều giá trị trung gian để downstream thấy giá trị mới hơn, **không phù hợp nếu mỗi message là một hành động nghiệp vụ cần xử lý đủ**.

Với luồng yêu cầu không được mất message, thay vì tăng buffer vô hạn, hãy chọn Streams/queue và thiết kế consumer có ACK/recovery.

### 8.2. Những nguồn gây OOM khác

- `.onBackpressureBuffer()` không giới hạn trong một stream tốc độ cao.
- `Flux.cache()` hoặc replay không giới hạn trên luồng vô hạn.
- Duy trì hàng nghìn SSE subscriptions không timeout, không cleanup.
- Payload JSON lớn, xử lý và copy qua nhiều buffer.
- Fan-out một message cho quá nhiều WebSocket/SSE clients.
- Retry ở tầng listener làm nhiều pipeline trùng nhau, không dispose pipeline cũ.

Cần đo queue length, lượng buffer, downstream latency, reconnect rate và số subscriber.

## 9. Lỗi kết nối và hủy subscription ở Pub/Sub

Khi Redis connection mất:

```text
t0: Subscriber đã subscribe.
t1: Mất connection.
t2: Redis publish event E.
t3: Connection hồi phục, subscriber đăng ký lại.
```

Event E ở `t2` không được Redis Pub/Sub tự phát lại. Kể cả client tự reconnect/resubscribe, việc đó chỉ nối lại dòng event **từ thời điểm subscription mới có hiệu lực**.

Tương tự, khi HTTP SSE client disconnect:

- WebFlux cancellation có thể hủy downstream subscription.
- Nếu downstream trực tiếp sở hữu Redis subscription, cần giải phóng connection/topic registration tương ứng.
- Nếu luồng Redis được chia sẻ, cancellation của một HTTP client không nên vô tình ngắt tất cả client khác.
- Nếu triển khai SSE tự reconnect, cần phân biệt “kết nối lại thành công” với “không mất event”.

Nên ghi logs/metrics phân biệt các trạng thái: Redis disconnect, reconnect, resubscribe, SSE client close và errors của handler.

### 9.1. `retryWhen` không có nghĩa replay Pub/Sub

Reactor hỗ trợ retry:

```java
flux.retryWhen(
    Retry.backoff(
        5,
        Duration.ofMillis(200)
    )
);
```

Đối với một nguồn subscription bị lỗi, retry có thể thiết lập một subscription mới nếu upstream hỗ trợ. Nhưng **message đã publish trong khoảng mất kết nối không được tạo lại**.

Tránh retry vô hạn với độ trễ bằng 0 vì có thể tạo vòng lặp nhanh khi Redis down. Dùng backoff, jitter, observability và ngưỡng phục hồi phù hợp.

## 10. Streams trong WebFlux: từ tín hiệu realtime sang bản ghi có ID

Redis Streams lưu các entry như một log. Ví dụ producer:

```redis
XADD orders:events * eventId evt-101 orderId o-101 type CREATED
XADD orders:events * eventId evt-102 orderId o-102 type PAID
```

Redis trả về ID riêng cho mỗi entry, ví dụ:

```text
1763000000123-0
1763000000124-0
```

Một entry có các trường (field/value) và ID. Khi dùng consumer group, một entry có thể được giao cho consumer, nằm trong PEL đến khi được ACK.

So với Pub/Sub:

```text
Pub/Sub:
  PUBLISH event -> người nghe online nhận -> không có backlog

Stream:
  XADD event -> entry nằm trong Stream
            -> consumer đọc theo ID/group
            -> xử lý
            -> XACK trạng thái pending
            -> entry gốc tiếp tục tồn tại đến khi retention/xóa
```

Redis Streams không tự động hẹn giờ retry, không bảo đảm exactly-once và không tự động gọi handler Java. Các khả năng đó phải được hoàn thiện bởi consumer lifecycle, recovery và logic nghiệp vụ.

## 11. Ghi Stream bằng API reactive

Spring Data Redis Reactive cung cấp stream operations trên `ReactiveRedisTemplate` hoặc `ReactiveStringRedisTemplate`.

Ví dụ một service ghi event:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderEventWriter {

    private static final String STREAM = "orders:events";

    private final ReactiveStringRedisTemplate redis;

    public ReactiveOrderEventWriter(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<RecordId> append(
            String eventId,
            String orderId,
            String type) {

        MapRecord<String, String, String> record =
            StreamRecords
                .newRecord()
                .in(STREAM)
                .ofMap(
                    Map.of(
                        "eventId", eventId,
                        "orderId", orderId,
                        "type", type
                    )
                );

        return redis.opsForStream().add(record);
    }
}
```

Ví dụ dùng field và value dạng String nên dễ quan sát bằng Redis CLI. Khi dùng serializer custom/DTO, cần chọn kiểu record và conversion context phù hợp với cấu hình Spring Data Redis.

Cách sử dụng tại HTTP controller:

```java
@PostMapping("/api/orders/{id}/events")
public Mono<String> addEvent(
        @PathVariable("id") String orderId) {

    return writer
        .append(
            java.util.UUID.randomUUID().toString(),
            orderId,
            "CREATED"
        )
        .map(RecordId::getValue);
}
```

Vì controller trả `Mono`, WebFlux subscribe và lệnh `XADD` được thực hiện. Kết quả là ID của entry đã được ghi ở mức Redis command, không phải xác nhận rằng một downstream consumer đã xử lý thành công.

### 11.1. Ghi database và XADD không tự atomic

Ví dụ:

```text
1. INSERT order vào database.
2. XADD orders:events.
```

Nếu bước 1 thành công nhưng bước 2 thất bại, dữ liệu và Stream không nhất quán. Đổi sang Reactor `then`, `flatMap` hoặc thêm `@Transactional` cho database **không tự tạo distributed transaction giữa SQL và Redis**.

Với event quan trọng, cân nhắc **transactional outbox** trong cùng database transaction, sau đó một publisher bền vững đưa event vào Stream. Cần xử lý duplicate publish bằng eventId và idempotency.

## 12. Đọc Stream không dùng group: theo ID và retention

Một consumer có thể đọc Stream không qua consumer group bằng lệnh:

```redis
XREAD COUNT 10 STREAMS orders:events 0-0
```

Đây là đọc các entry có ID lớn hơn mốc được chỉ định. Nếu muốn chờ dữ liệu mới:

```redis
XREAD BLOCK 5000 STREAMS orders:events $
```

`$` yêu cầu bắt đầu từ điểm cuối khi lệnh bắt đầu đọc, phù hợp một số live tail scenario nhưng có thể làm bỏ qua entry có sẵn trước đó.

Trong Spring Data Redis, các offset thường dùng:

```java
ReadOffset.from("0-0")
ReadOffset.latest()
ReadOffset.lastConsumed()
```

Cần phân biệt:

- **`ReadOffset.from(id)`**: đọc từ mốc ID được chỉ định theo ngữ nghĩa Stream read.
- **`ReadOffset.latest()`**: bắt đầu theo vị trí mới nhất tại thời điểm đọc, dễ bỏ qua entry giữa các lần polling nếu dùng không đúng.
- **`ReadOffset.lastConsumed()`**: dựa trên tiến độ đã tiêu thụ của consumer/group theo ngữ cảnh API, thường dùng với consumer group để đọc entry chưa giao tiếp theo.

### 12.1. Bẫy `latest()` trong polling

Một nguồn reactive có thể tạm ngừng polling khi downstream không có demand hoặc trong giai đoạn xử lý. Nếu mỗi lần poll lại chọn `$`/`latest`, những entry được ghi trong khoảng tạm dừng có nguy cơ bị bỏ qua.

Với yêu cầu không mất dữ liệu, ưu tiên **ID cụ thể được theo dõi** hoặc **consumer group** và quản lý ACK, thay vì giả định một live-tail Flux dùng `latest()` sẽ luôn đọc đầy đủ mọi entry.

Điều này rất khác Pub/Sub: Stream có thể giữ entry theo retention, nhưng **consumer chọn offset sai vẫn có thể không đọc những entry đã tồn tại**.

### 12.2. Stream là log, không phải subscription broadcast tự động

Nếu có ba consumer độc lập không dùng group và mỗi consumer đọc từ ID riêng, cả ba có thể đọc cùng entry. Nếu dùng **một consumer group chung**, các entry mới được giao để chia việc giữa các consumer trong group.

Nếu có hai consumer group độc lập, mỗi group có tiến độ và PEL riêng, nên hai nhóm đều có thể xử lý cùng một entry theo trách nhiệm khác nhau.

## 13. Tạo consumer group và hiểu Pending Entries List

Tạo group trong môi trường thử nghiệm:

```redis
XGROUP CREATE orders:events orders-workers 0 MKSTREAM
```

Trong đó:

- `orders:events`: Stream key.
- `orders-workers`: tên consumer group.
- `0`: group có thể xử lý các entry có sẵn từ đầu Stream.
- `MKSTREAM`: tạo Stream rỗng nếu chưa tồn tại.

Nếu chọn `$` thay vì `0`, group bắt đầu ở cuối Stream hiện tại, chỉ tập trung vào entry mới sau thời điểm tạo group. Chọn sai offset khi khởi tạo có thể làm bỏ qua backlog lịch sử.

Consumer đọc:

```redis
XREADGROUP GROUP orders-workers worker-A COUNT 10 BLOCK 2000 STREAMS orders:events >
```

Ký hiệu `>` có nghĩa yêu cầu các entry chưa được giao cho consumer nào trong group theo cơ chế đọc message mới. Nếu không dùng `NOACK`, Redis sẽ theo dõi các ID được giao trong **Pending Entries List (PEL)**.

```text
Stream orders:events
   |
   | XREADGROUP GROUP orders-workers worker-A ... >
   v
worker-A nhận entry id=1763000000123-0
   |
   +--> PEL orders-workers:
         ID           = 1763000000123-0
         Owner        = worker-A
         Idle time    = ...
         Delivery cnt = ...
   |
   +--> Application xử lý event
         |
         +-- Thành công --> XACK
         +-- Crash     --> entry vẫn pending
```

`XACK` chỉ xóa **trạng thái pending trong group**, không xóa entry gốc khỏi Stream. Việc xóa log là một quyết định retention riêng.

### 13.1. Pending không đồng nghĩa thất bại

Một message có thể pending vì đang được xử lý bình thường. Nó chỉ có nghĩa Redis đã giao nhưng chưa nhận ACK. Nếu handler thường mất 90 giây, entry pending 20 giây không chứng minh worker đã chết.

Cần nhìn đồng thời thời gian xử lý bình thường, consumer health, pending idle và delivery count.

## 14. Đọc consumer group từ WebFlux/reactive worker

Spring Data Redis hỗ trợ `ReactiveStreamOperations` và các cơ chế nhận Stream liên tục, trong đó có `StreamReceiver` cho cách tiêu thụ dữ liệu theo mô hình reactive.

Về bản chất, worker cần:

```text
Reactive source từ Redis Stream
       |
       v
Flux<MapRecord<...>>
       |
       v
Validate / deserialize
       |
       v
Gọi nghiệp vụ bất đồng bộ
       |
       v
ACK bằng Redis reactive operation
```

Một ví dụ cấu trúc API consumer group với `StreamReceiver`:

```java
import java.time.Duration;

import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamReceiver;

StreamReceiver.StreamReceiverOptions<String, MapRecord<String, String, String>>
    options = StreamReceiver.StreamReceiverOptions
        .<String, MapRecord<String, String, String>>builder()
        .pollTimeout(Duration.ofSeconds(2))
        .build();

StreamReceiver<String, MapRecord<String, String, String>> receiver =
    StreamReceiver.create(connectionFactory, options);

Flux<MapRecord<String, String, String>> records =
    receiver.receive(
        Consumer.from("orders-workers", "worker-A"),
        StreamOffset.create(
            "orders:events",
            ReadOffset.lastConsumed()
        )
    );
```

Đoạn mã minh họa contract của receiver, loại record và offset. Generic builder, serialization option và overload có thể thay đổi theo phiên bản Spring Data Redis; khi đưa vào project, cần dùng đúng `StreamReceiverOptions`/serialization context của dependency thực tế.

Điểm quan trọng không nằm ở một cú pháp builder duy nhất mà ở các quyết định:

1. Dùng **consumer group** và consumer name rõ ràng.
2. Đọc với `ReadOffset.lastConsumed()` cho luồng message mới được group giao.
3. Giới hạn poll timeout và resources.
4. Trả một `Flux` để gắn với pipeline xử lý.
5. **ACK chỉ sau khi logic xử lý hoàn tất thành công**.
6. Có cơ chế recovery pending riêng, vì đọc message mới không tự trả lại pending của consumer khác.

### 14.1. Tại sao `StreamReceiver` khác Pub/Sub listener?

Pub/Sub được Redis push ngay khi có publication và không có backlog. Stream receiver có thể **poll** Redis để đọc log theo offset, có thể điều chỉnh hành vi polling và được ghép vào luồng Reactor.

Khả năng replay của Streams dựa trên entry còn trong Stream và vị trí đọc hợp lệ. Đó là khác biệt của **Redis data structure**, không phải do một Reactor operator tạo ra.

### 14.2. Polling không chặn thread request như API blocking

Redis command `XREAD`/`XREADGROUP` có tùy chọn `BLOCK` để chờ dữ liệu ở phía Redis server. Khi dùng connector reactive hỗ trợ, ứng dụng không cần `Thread.sleep()` hoặc giữ một thread Java request ở trạng thái blocking để đợi câu trả lời.

Tuy nhiên, một blocked read vẫn tiêu thụ **connection và tài nguyên server/client**. Cần cấu hình poll timeout, connection management và khả năng shutdown phù hợp. “Non-blocking Java I/O” không có nghĩa chi phí vận hành bằng 0.

## 15. ACK reactive: chỉ xác nhận sau khi xử lý thành công

Giả sử có một handler nghiệp vụ reactive:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import reactor.core.publisher.Mono;

public interface OrderEventHandler {
    Mono<Void> handle(MapRecord<String, String, String> record);
}
```

Một chuỗi xử lý dùng `concatMap`:

```java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

private Flux<Void> processRecords(
        Flux<MapRecord<String, String, String>> records,
        ReactiveStringRedisTemplate redis,
        OrderEventHandler handler) {

    return records.concatMap(record ->
        handler.handle(record)
            .then(
                redis.opsForStream().acknowledge(
                    "orders:events",
                    "orders-workers",
                    record.getId()
                )
            )
            .doOnNext(ackCount -> {
                if (ackCount == 0L) {
                    // Ghi metric/log khi entry không còn pending.
                }
            })
            .then()
            .onErrorResume(error -> {
                // Log theo Stream ID và phân loại lỗi.
                // Không ACK message chưa hoàn tất.
                return Mono.empty();
            })
    );
}
```

Đây là mã minh họa một method trong service. `records` là Flux nguồn từ receiver ở phần trước; `handler.handle` phải trả Publisher thể hiện **thời điểm nghiệp vụ thực sự hoàn thành**, không phải chỉ “đã lên lịch” công việc.

Thứ tự là:

```text
record -> handler.handle(record) hoàn tất thành công
       -> ACK trả kết quả
       -> chuyển sang record tiếp theo trong concatMap
```

Nếu `handler` báo lỗi, nhánh ACK không chạy. Entry vẫn có thể pending và phải được xử lý bằng retry/recovery đã thiết kế.

### 15.1. Vì sao không ACK khi vừa nhận?

Cách nguy hiểm:

```java
records.flatMap(record ->
    redis.opsForStream()
        .acknowledge(STREAM, GROUP, record.getId())
        .then(handler.handle(record))
);
```

Trong chuỗi này, ACK hoàn tất trước khi nghiệp vụ chạy. Nếu handler lỗi/crash, PEL đã mất trạng thái cần retry. Đối với tác vụ cần độ tin cậy, thứ tự này thường không phù hợp.

### 15.2. `flatMap` và concurrency

Nếu viết:

```java
records.flatMap(record -> handleAndAck(record))
```

nhiều message có thể được xử lý đồng thời và hoàn tất **không theo thứ tự nhận**. Điều này không hẳn sai nếu các event độc lập và hệ thống muốn tăng throughput, nhưng có thể phá invariant nếu nhiều event cùng `orderId` cần xử lý theo thứ tự.

Một số lựa chọn:

- `concatMap` xử lý tuần tự, dễ bảo toàn thứ tự trong một pipeline.
- `flatMap(record -> handleAndAck(record), concurrency)` giới hạn số tác vụ in-flight.
- Partition theo entity key rồi xử lý tuần tự **trong mỗi nhóm** nếu logic yêu cầu thứ tự theo entity; cần kiểm soát số nhóm và lifecycle để tránh giữ tài nguyên vô hạn.
- Dựa vào transaction/optimistic locking ở hệ thống sở hữu dữ liệu nếu có cập nhật đồng thời.

**Redis Streams không tự biến các tác vụ trên nhiều consumer thành một hệ thống xử lý theo thứ tự nghiệp vụ tuyệt đối.** Cần thiết kế khóa phân vùng, version và idempotency khi thứ tự quan trọng.

### 15.3. Cancellation giữa xử lý và ACK

Nếu Reactor subscription bị cancel sau khi side effect hoàn tất nhưng trước `XACK`, message có thể vẫn pending và được recovery worker xử lý lại.

Ngay cả khi side effect được thực hiện qua non-blocking API, không có atomic commit chung giữa database và Redis ACK chỉ nhờ `.then(...)`. Hãy dùng **idempotency** khi các side effect không được phép lặp.

## 16. At-least-once và idempotency trong WebFlux

Mô hình cần chú ý:

```text
t1: Worker đọc event E từ Stream.
t2: E được thêm vào PEL.
t3: Handler gọi database và commit thành công.
t4: Worker crash trước khi XACK.
t5: Recovery worker claim E.
t6: Handler chạy lại E.
```

Ở t6, nếu handler không idempotent, có thể gửi cùng email hai lần, cộng điểm thưởng hai lần, hoặc lặp ghi dữ liệu.

Một chiến lược thường dùng là **định danh event nghiệp vụ**:

```json
{
  "eventId": "evt-1001",
  "orderId": "o-101",
  "type": "OrderPaid"
}
```

Bên hệ thống xử lý, lưu `eventId` vào một nơi có unique constraint hoặc cơ chế compare-and-set phù hợp **trong cùng transaction** với side effect bền vững.

Ví dụ ý tưởng SQL:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Khi nhận E:

```text
BEGIN transaction
    INSERT processed_events(event_id = E.eventId)
    nếu duplicate: bỏ qua áp dụng side effect lần nữa
    nếu mới: cập nhật dữ liệu nghiệp vụ
COMMIT
XACK E
```

Ở phương án này, ACK có thể được gọi lại sau khi thấy event đã xử lý; việc gọi lại không được làm side effect trùng. Với API ngoài database (thanh toán, email), cần idempotency key phía provider hoặc một outbox/dispatch state riêng.

### 16.1. Reactivity không quyết định transaction boundary

Nếu handler dùng R2DBC và reactive database transaction, thời điểm `Mono` hoàn tất phải phản ánh transaction đã commit theo thiết kế. Nếu handler tự `.subscribe()` một lệnh database rồi trả `Mono.empty()`, caller có thể ACK quá sớm.

Tránh:

```java
public Mono<Void> handle(Event event) {
    repository.save(convert(event)).subscribe(); // Detached side effect
    return Mono.empty();
}
```

Nên trả Publisher nối trực tiếp với thao tác:

```java
public Mono<Void> handle(Event event) {
    return repository
        .save(convert(event))
        .then();
}
```

Với nhiều bước, dùng reactive transaction management phù hợp nếu tất cả thuộc cùng transactional resource. Không suy rằng `@Transactional` trên method reactive sẽ tạo atomic transaction giữa R2DBC database và Redis Stream.

## 17. Recovery PEL: đọc message mới không tự lấy pending cũ

Một vấn đề vận hành phổ biến:

```text
worker-A đọc E -> E pending -> worker-A chết
worker-B đọc STREAMS orders:events >
```

`worker-B` với `>` vẫn có thể đọc message **mới**, nhưng không tự nhận entry E đang thuộc PEL của `worker-A`.

Cần cơ chế recovery. Redis cung cấp:

```redis
XPENDING orders:events orders-workers
XPENDING orders:events orders-workers - + 20
```

để quan sát pending. Để chuyển ownership:

```redis
XCLAIM orders:events orders-workers worker-B 60000 <entry-id>
```

Hoặc để tìm và claim tự động theo idle time:

```redis
XAUTOCLAIM orders:events orders-workers worker-B 60000 0-0 COUNT 20
```

Ở ví dụ trên:

- `60000` là ngưỡng idle time tối thiểu 60 giây, không phải TTL của message.
- `0-0` là cursor bắt đầu quét PEL.
- Cần xử lý cursor trả về và các entry được claim.
- Claim **không ACK**; recovery worker vẫn phải xử lý và `XACK` sau khi thành công.

### 17.1. Recovery worker có thể dùng reactive API?

Spring Data Redis và driver có thể cung cấp các thao tác tương ứng cho Stream commands; mức hỗ trợ API reactive cụ thể phụ thuộc phiên bản. Nếu một command recovery cần thiết chưa có abstraction trực tiếp thuận tiện, có thể sử dụng API cấp thấp phù hợp hoặc một worker quản trị riêng, nhưng đừng đưa lệnh blocking vào WebFlux event-loop.

Một thiết kế hợp lý:

```text
Normal Reactive StreamReceiver
    -> đọc message mới
    -> process
    -> ACK

Recovery service
    -> quan sát PEL
    -> tìm entry idle lâu
    -> XAUTOCLAIM/XCLAIM
    -> process bằng cùng handler idempotent
    -> ACK
```

Phải có cơ chế tránh recovery claim quá sớm khi worker cũ vẫn đang xử lý. Chọn ngưỡng idle theo latency thực tế p99 và timeout nghiệp vụ, không mặc định 60 giây phù hợp mọi công việc.

### 17.2. Đọc lịch sử pending của cùng consumer

`XREADGROUP` với ID như `0` có thể đọc pending của **chính consumer name hiện tại** trong group, còn `>` đọc message mới. Một consumer restart với cùng tên có thể chủ động lấy lại lịch sử pending của mình.

Nhưng một consumer tên khác không tự lấy pending của consumer cũ chỉ bằng cách đọc từ `0`. Cần claim để đổi ownership.

### 17.3. Lỗi không thể xử lý và DLQ

Nếu message có payload sai schema hoặc vi phạm invariant không thể retry, cứ giữ pending và retry mãi có thể gây poison-message loop.

Một phương án:

```text
Receive E
    |
    +-- OK ----------------------> XACK
    |
    +-- Retryable ---------------> pending/retry với backoff
    |
    +-- Non-retryable -----------> ghi DLQ bền vững
                                     |
                                     v
                               XACK entry gốc
```

Bước ghi DLQ và ACK có thể thất bại độc lập. Muốn tránh mất hoặc nhân đôi bản ghi DLQ, cần thiết kế idempotency/transaction theo phạm vi Redis key hoặc nơi lưu trữ tương ứng.

## 18. StreamReceiver và quản lý lifecycle của background worker

Khác với HTTP endpoint do WebFlux quản lý subscription, một background worker cần có một **subscriber chủ động** và vòng đời rõ ràng.

Ví dụ mô hình:

```text
Spring Application Start
      |
      v
Tạo StreamReceiver
      |
      v
Đăng ký Flux xử lý
      |
      v
Lưu Disposable subscription
      |
      +-- Running: nhận và xử lý message
      |
Spring Application Shutdown
      |
      v
Cancel subscription / graceful stop
```

Nếu chỉ tạo `Flux` trong một `@Bean`:

```java
@Bean
Flux<?> orderMessages(StreamReceiver<?, ?> receiver) {
    return ...;
}
```

điều đó **không có nghĩa có ai subscribe và worker đang chạy**. Một bean mang kiểu `Flux` chỉ là object Publisher; cần một nơi quản lý subscription.

### 18.1. Dùng SmartLifecycle hoặc lifecycle component

Có thể dùng `SmartLifecycle` của Spring để khởi động/dừng pipeline và lưu `Disposable`. Pseudo-code phản ánh cấu trúc:

```java
public final class OrderWorkerLifecycle implements SmartLifecycle {

    private Disposable subscription;
    private boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }

        subscription = recordsFlux
            .concatMap(this::processAndAck)
            .doOnError(this::reportFailure)
            .retryWhen(
                Retry.backoff(
                    Long.MAX_VALUE,
                    Duration.ofMillis(500)
                ).maxBackoff(Duration.ofSeconds(10))
            )
            .subscribe();

        running = true;
    }

    @Override
    public void stop() {
        if (subscription != null) {
            subscription.dispose();
            subscription = null;
        }
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

Đoạn này là **khung minh họa**: `recordsFlux`, `processAndAck` và `reportFailure` cần được định nghĩa theo service thực tế, bổ sung logging, state thread-safety và shutdown policy. Các method mặc định của `SmartLifecycle` như phase/auto-start có thể được override theo nhu cầu.

Trong production, một hành động `.dispose()` có thể hủy in-flight operation chứ không phải graceful drain. Nếu cần cho tác vụ đang chạy hoàn tất, phải định nghĩa thời hạn dừng, ngưng poll, chờ tác vụ hiện tại và cách khôi phục pending sau khi timeout.

### 18.2. `retryWhen` ở tầng nào?

Hai loại lỗi cần phân biệt:

- **Lỗi đọc Redis:** connection down, timeout khi polling. Có thể cần tạo lại subscription với backoff.
- **Lỗi xử lý riêng một record:** payload sai, database lỗi, nghiệp vụ từ chối. Không nên làm chết toàn bộ luồng vì một record nhưng cũng không ACK bừa bãi.

Nếu đưa một `retryWhen` chung vào sau handler mà không phân biệt lỗi, lỗi một message có thể làm resubscribe toàn nguồn và bỏ lại pending; tùy offset/ownership, message đó không tự đến lại.

Một cấu trúc dễ quản lý hơn là xử lý lỗi **theo từng record**, ghi trạng thái/retry policy rõ ràng, đồng thời có nhánh retry riêng cho lỗi transport của stream reader.

## 19. Thứ tự và concurrency trong consumer group

Redis Streams bảo toàn thứ tự ID của các entry trong Stream, nhưng ứng dụng có thể làm mất thứ tự hiệu lực bằng cách xử lý song song.

Ví dụ:

```text
Stream:
    E1: order o-9 CREATED
    E2: order o-9 PAID
    E3: order o-9 CANCELLED

Worker-A nhận E1
Worker-B nhận E2
Worker-C nhận E3
```

Nếu E2 xử lý trước E1, hệ thống có thể cập nhật trạng thái sai dù thứ tự ID của Stream đúng.

Do đó, yêu cầu “event cùng aggregate phải xử lý theo thứ tự” không tự được bảo đảm bởi việc mọi consumer dùng chung group.

Các hướng thiết kế:

1. Giới hạn một consumer cho những luồng thật sự cần thứ tự toàn cục.
2. Partition theo `orderId` để cùng order được xử lý tuần tự, nếu chấp nhận thiết kế phân mảnh dữ liệu phức tạp.
3. Dùng version/sequence number ở mỗi event và optimistic concurrency control tại database.
4. Cho handler có khả năng trì hoãn, bỏ qua hoặc reconcile event đến sai thứ tự theo invariant.
5. Không tăng `flatMap` concurrency nếu nghiệp vụ cần xử lý tuần tự.
6. Nếu dùng nhiều Stream keys trên Redis Cluster, thiết kế hash tag và routing cẩn thận.

Đánh đổi: thứ tự nghiêm ngặt có thể giảm throughput; tăng throughput có thể đòi hỏi xử lý version và idempotency phức tạp hơn.

## 20. WebFlux SSE với nguồn Streams: khi cần replay

Đối với một dashboard muốn hiển thị lịch sử gần đây và tiếp tục theo dõi realtime, Redis Streams phù hợp hơn Pub/Sub thuần nếu cần đọc lại theo ID.

Mô hình:

```text
Browser SSE
   |
   | Last-Event-ID: 1763000000123-0
   v
WebFlux Controller
   |
   | XREAD/XRANGE sau ID đã nhận
   v
Redis Stream
   |
   +--> Phát event cũ còn giữ trong retention
   |
   +--> Tiếp tục đọc event mới theo offset
   |
   v
Flux<ServerSentEvent<...>>
```

Một đoạn mapping record sang SSE:

```java
Flux<ServerSentEvent<String>> feed = records
    .map(record ->
        ServerSentEvent.<String>builder()
            .id(record.getId().getValue())
            .event("order")
            .data(record.getValue().toString())
            .build()
    );
```

Đây là ví dụ minh họa mapping. `record.getValue().toString()` **không phải JSON serializer chuẩn**; nếu client cần JSON có schema, hãy dùng Jackson để serialize một DTO/envelope rõ ràng.

### 20.1. Không dùng chung consumer group cho mọi browser nếu muốn broadcast

Nếu tất cả browser SSE dùng cùng consumer group, Redis sẽ **chia việc** giữa consumer trong group; mỗi browser có thể chỉ thấy một phần entry. Điều đó không phù hợp nếu từng browser phải thấy **tất cả** event của feed.

Các lựa chọn:

- Dùng `XREAD` theo ID riêng của từng browser nếu số lượng kết nối và chi phí Redis cho phép.
- Dùng một reader server-side rồi fan-out tới các SSE clients; giữ cơ chế resume bằng Stream ID ở tầng gateway.
- Dùng Pub/Sub cho live notification và Streams cho backfill, có cơ chế nối hai luồng tránh gap/duplicate.
- Nếu nhóm dịch vụ khác nhau đều cần đọc toàn bộ Stream, dùng nhiều consumer group độc lập, nhưng **không tạo một group cho mỗi browser vô hạn** nếu không có lifecycle và cleanup.

Consumer group thích hợp cho **chia công việc**, không tự động thay thế cơ chế broadcast SSE.

### 20.2. Đồng bộ phần lịch sử và phần live

Một thiết kế naive:

```text
1. XRANGE đọc lịch sử tới ID hiện tại.
2. Đăng ký Pub/Sub.
```

có thể bỏ lỡ event publish giữa hai bước. Thiết kế theo chiều ngược:

```text
1. Subscribe Pub/Sub.
2. Đọc lịch sử từ Stream.
```

có thể nhận trùng event giữa luồng live và lịch sử. Đây là race kiến trúc, cần chống trùng theo Stream ID, thiết lập watermark, và quy trình chuyển tiếp có kiểm soát.

Một lựa chọn đơn giản hơn, khi latency và throughput cho phép, là dùng **Stream tail** theo ID liên tục làm nguồn duy nhất thay vì tự ghép hai loại subscription.

## 21. So sánh Pub/Sub và Streams trong WebFlux

| Tiêu chí | Reactive Pub/Sub | Reactive Streams |
|---|---|---|
| Bản chất Redis | Broadcast realtime | Log có ID |
| Lệnh chính | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | `XADD`, `XREAD`, `XREADGROUP`, `XACK` |
| API Spring tiêu biểu | `ReactiveRedisMessageListenerContainer` | `ReactiveStreamOperations`, `StreamReceiver` |
| Kiểu luồng Reactor | `Flux` nhận publication | `Flux` nhận Stream records |
| Lưu lịch sử | Không | Có, trong giới hạn retention |
| Người đến muộn đọc bù | Không qua Pub/Sub thuần | Có nếu còn entry và biết ID/offset |
| ACK consumer group | Không | Có bằng `XACK` |
| Pending/claim | Không | PEL, `XCLAIM`/`XAUTOCLAIM` |
| Broadcast nhiều subscriber | Tự nhiên | Cần reader riêng hoặc fan-out thiết kế rõ |
| Chia việc giữa workers | Không tự có consumer group | Có với `XREADGROUP` |
| Backpressure end-to-end | Không có bảo đảm Redis Pub/Sub chờ subscriber chậm | Có thể điều chỉnh polling/demand, nhưng vẫn cần thiết kế concurrency |
| Retry/recovery | Không có replay mặc định | Có thể triển khai dựa trên Stream/PEL |
| Exactly-once | Không | Không tự bảo đảm; cần idempotency |
| Quản lý bộ nhớ | Chủ yếu connection/output buffers | Thêm log data, retention và PEL metadata |
| Phù hợp | Notification cho UI, cache invalidation, tín hiệu realtime | Jobs, audit/events có khả năng đọc lại, xử lý có ACK |

**Không có cơ chế nào tự tốt hơn trong mọi tình huống.** Nếu mục tiêu chỉ là báo cho UI hiện đang mở rằng trạng thái vừa đổi, Pub/Sub có thể đơn giản và nhanh. Nếu thông điệp là nghĩa vụ cần xử lý sau crash, nên dùng Streams hoặc broker có retention/ACK.

## 22. Serialization: từ Redis bytes đến DTO reactive

Cả Pub/Sub và Streams đều truyền dữ liệu qua Redis protocol; Java object không tự đi qua mạng nguyên dạng.

Với Pub/Sub:

```text
Java event DTO
    |
    | ObjectMapper -> JSON string
    |
    | ReactiveStringRedisTemplate
    v
Redis channel + payload bytes
    |
    v
Flux<Message>
    |
    | JSON deserialize
    v
Java DTO
```

Với Stream:

```text
Java event
    |
    | fields: eventId, type, payload
    v
XADD stream * field/value...
    |
    v
MapRecord / ObjectRecord tùy cấu hình
    |
    | serializer/converter
    v
Java model
```

### 22.1. Chọn định dạng payload rõ ràng

Ví dụ JSON envelope:

```json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "type": "OrderCreated",
  "occurredAt": "2026-11-13T02:00:00Z",
  "payload": {
    "orderId": "o-101"
  }
}
```

Cần thỏa thuận:

- Encoding, thường UTF-8.
- Tên channel/Stream key.
- Schema version và cách tương thích ngược.
- Event ID nghiệp vụ (khác Redis Stream ID).
- Kích thước tối đa payload.
- Quy tắc validate và xử lý payload không hợp lệ.
- Chính sách che dữ liệu nhạy cảm trong log và metrics.

Nếu producer dùng JDK serialization nhưng consumer giải mã String JSON, việc decode sẽ thất bại. Nếu một consumer lấy `record.getValue()` rồi ép kiểu không kiểm soát, nó cũng có thể gặp lỗi do field/value serializer khác nhau.

### 22.2. `MapRecord` và `ObjectRecord`

- `MapRecord` biểu diễn một entry Stream như map field/value.
- `ObjectRecord` hỗ trợ mapping object qua converter.

Lựa chọn phụ thuộc schema và serializer. `MapRecord<String, String, String>` dễ quan sát khi tất cả field/value là String. `ObjectRecord` thuận tiện khi object mapping nhất quán, nhưng cần hiểu tên field, keyspace, format và khả năng tương thích phiên bản.

Với consumer group quan trọng, tránh để thay đổi DTO hoặc serializer làm toàn bộ worker thất bại rồi không ACK các entry cũ. Cần schema migration và DLQ rõ ràng.

## 23. Lỗi và retry trong Reactor: đừng làm thay đổi ngữ nghĩa nghiệp vụ

Reactor có các operator phổ biến:

```java
.retryWhen(...)
.onErrorResume(...)
.timeout(...)
.doOnError(...)
```

Chúng điều khiển Publisher **ở phía ứng dụng**. Chúng không tự sửa các vấn đề:

- Redis Pub/Sub đã bỏ lỡ event do mất kết nối.
- Stream entry đã ACK quá sớm.
- Side effect đã commit nhưng ACK thất bại.
- Consumer group còn pending không được claim.
- Payload vĩnh viễn sai schema.
- Hai workers xử lý cùng event vì claim sớm.

### 23.1. Retry lệnh đọc khác retry xử lý record

Nếu `XREADGROUP` mất kết nối, tạo lại reader với backoff có thể hữu ích. Nếu handler cho E thất bại, việc retry toàn bộ nguồn có thể tạo vòng xử lý khó dự đoán và khiến E tiếp tục pending.

Phân tách theo lỗi:

| Lỗi | Cách tiếp cận |
|---|---|
| Redis network timeout khi đọc | Backoff, reconnect, giữ trạng thái worker |
| Payload JSON sai | Không retry vô hạn; ghi DLQ nếu policy yêu cầu |
| Database tạm thời không sẵn sàng | Retry hữu hạn, rồi giữ pending hoặc chuyển trạng thái |
| External API trả lỗi vĩnh viễn | Bù/DLQ theo hợp đồng nghiệp vụ |
| ACK timeout sau business commit | Kiểm tra trạng thái, dựa vào idempotency khi redelivery |
| Downstream SSE client chậm | Buffer/drop/disconnect hoặc phục vụ từ Stream theo ID |
| Subscriber Pub/Sub rớt mạng | Reconnect; nếu cần bù lịch sử phải dùng nguồn log khác |

### 23.2. Timeout không chứng minh command chưa chạy

Ví dụ một `Mono` thực hiện `XADD` hoặc `XACK` bị timeout ở phía client. Redis có thể đã thực thi lệnh nhưng response chưa về. Không được tự suy luận “timeout nghĩa là lệnh chưa gửi”.

Với `XADD`, nếu lệnh bị gửi lại mà không có idempotency, có thể sinh thêm một Stream entry mang ID khác nhưng cùng `eventId`. Với `XACK`, có thể lần thứ hai trả `0` vì entry không còn pending. Phần downstream vẫn cần quyết định bằng eventId và dữ liệu thực tế.

## 24. Bảo vệ event-loop khỏi blocking code

WebFlux thường sử dụng một số ít event-loop threads để phục vụ nhiều kết nối. Nếu handler Stream làm việc blocking:

```java
public Mono<Void> handle(Event event) {
    jdbcRepository.save(event); // Blocking JDBC.
    return Mono.empty();
}
```

thì lời gọi blocking đã xảy ra ngay lúc method được thực thi, trước khi Publisher trả về. Cần dùng một API reactive phù hợp (ví dụ R2DBC cho truy cập database phản ứng) hoặc cô lập blocking:

```java
public Mono<Void> handle(Event event) {
    return Mono.fromRunnable(
        () -> jdbcRepository.save(event)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .then();
}
```

Đây là giải pháp tương thích cho một dependency blocking, không phải thiết kế tối ưu nhất cho throughput cao. `boundedElastic` có thread/queue hữu hạn; cần giám sát và không để thao tác blocking vô thời hạn.

### 24.1. Những chỗ có thể vô tình block

- Gọi `StringRedisTemplate` từ controller WebFlux.
- Dùng `.block()`/`.blockOptional()` trên Netty event-loop.
- Đọc file hoặc gọi HTTP blocking client trong `map`.
- Parse payload rất lớn hoặc tính toán CPU nặng trên thread sự kiện.
- Dùng `Thread.sleep()` trong retry thay vì Reactor `retryWhen`.
- Dùng synchronized lock giữ lâu trên callback nhận Pub/Sub.
- Gọi database transaction blocking trong handler Stream rồi lập tức ACK.

Mục tiêu là giữ **đường I/O non-blocking** và có giới hạn tài nguyên, đồng thời tách ranh giới transaction của nghiệp vụ rõ ràng.

## 25. Triển khai nhiều instance WebFlux

Giả sử có ba instance:

```text
               Redis
                |
        +-------+-------+
        |       |       |
        v       v       v
      App A   App B   App C
        |       |       |
       SSE     SSE     SSE
     clients clients clients
```

Với **Pub/Sub**:

- Mỗi instance đăng ký channel sẽ nhận publication phù hợp.
- Mỗi instance có thể fan-out cho SSE clients đang kết nối tới nó.
- Một publication không tự có một “consumer duy nhất” như worker queue.
- Khi một instance offline, các client của instance đó có thể bỏ lỡ event.
- Nếu cùng một instance đăng ký hai đường overlapping, nó có thể nhận trùng.

Với **Streams + một consumer group chung**:

- Các instance tham gia group chia nhau entry mới.
- Một instance không thấy toàn bộ event chỉ vì cùng tham gia group.
- Cần PEL recovery khi một instance crash.
- Nếu mỗi instance cần truyền **tất cả** event cho các client SSE của mình, không nên sử dụng một group chung để cung cấp trực tiếp nguồn broadcast.

### 25.1. Thiết kế phổ biến: Redis Stream làm nguồn bền vững, Pub/Sub làm tín hiệu

Một cách phối hợp:

```text
Business Service
   |
   +--> Ghi event vào Redis Stream
   |
   +--> Publish notification "new event"
                |
                v
        WebFlux app instances
                |
                +--> Nhận tín hiệu Pub/Sub
                |
                +--> Đọc Stream theo ID checkpoint
                |
                +--> Fan-out SSE clients
```

Ưu điểm: nếu tín hiệu Pub/Sub bị mất, reader có thể định kỳ đọc Stream theo checkpoint và không phụ thuộc hoàn toàn vào event trực tiếp.

Cần giải quyết:

- Thứ tự ghi Stream và phát tín hiệu, vì hai thao tác có thể thất bại riêng.
- Checkpoint lưu ở đâu, sống qua restart thế nào.
- Mỗi instance/broadcast group cần đọc những event nào.
- Đọc bù theo ID như thế nào, bảo đảm không trùng khi reconnect.
- Retention đủ lâu cho khoảng thời gian instance offline.
- Giới hạn tốc độ đọc bù để không tạo spike.

Đây là kiến trúc có thêm độ phức tạp. Nếu nghiệp vụ chấp nhận mất thông báo realtime và UI tự tải lại trạng thái khi mở trang, Pub/Sub trực tiếp có thể đã đủ.

## 26. Redis Cluster và các giới hạn liên quan

Redis Cluster phân chia key theo hash slot. Với Streams:

- Một Stream key thuộc một hash slot.
- Các lệnh với một Stream thường được route đến node sở hữu slot.
- Khi đọc nhiều Stream keys trong cùng một thao tác, có thể chịu ràng buộc **cùng hash slot**.
- Nếu script/transaction cùng lúc cập nhật Stream, PEL-related metadata hoặc data keys khác, cần phân tích các key nằm trong bao nhiêu slot; Redis Cluster không cung cấp transaction xuyên shard chỉ bằng Lua/`MULTI`.

Ví dụ hai Stream được đặt cùng slot nhờ hash tag:

```text
orders:{tenant-7}:events
orders:{tenant-7}:dlq
```

Cách colocate này có ích khi một workflow cần thao tác nguyên tử trong cùng slot, nhưng nếu toàn bộ tenant là một hot slot, nó có thể tạo điểm nghẽn.

### 26.1. Classic Pub/Sub và sharded Pub/Sub

Redis Cluster có **classic Pub/Sub** với `PUBLISH`/`SUBSCRIBE`/`PSUBSCRIBE` và **sharded Pub/Sub** (Redis 7 trở lên) với `SPUBLISH`/`SSUBSCRIBE`.

Không được mặc định rằng một `ReactiveRedisMessageListenerContainer.receive(new PatternTopic(...))` tự động sử dụng sharded Pub/Sub hoặc tự triển khai pattern subscription tương đương cho sharded channels. Phải kiểm tra API Spring Data Redis và driver hỗ trợ chế độ nào.

Chọn classic hay sharded Pub/Sub liên quan tới topology, network fan-out và pattern support; chọn Pub/Sub hay Streams liên quan tới khả năng lưu và xử lý message.

### 26.2. Không suy từ client redirect thành exactly-once

Lettuce cluster-aware có thể định tuyến và xử lý redirect cho nhiều lệnh Redis, nhưng trong resharding/failover vẫn có thể timeout hoặc trạng thái thực thi không chắc chắn.

Một retry `XADD` thiếu `eventId` idempotency có thể nhân đôi bản ghi nghiệp vụ. Một retry handler sau claim cũng có thể nhân đôi side effect. Phải xử lý ở tầng ứng dụng.

## 27. Retention và khả năng đọc lại trong Streams

Redis Streams giữ entry cho đến khi có thao tác retention/xóa phù hợp. Ví dụ:

```redis
XADD orders:events MAXLEN ~ 100000 * eventId evt-101 type CREATED
```

`MAXLEN ~ 100000` minh họa giới hạn gần đúng số entry. Nó không có nghĩa luôn giữ chính xác 100.000 entry.

Các lựa chọn liên quan:

```redis
XLEN orders:events
XTRIM orders:events MAXLEN ~ 100000
XRANGE orders:events - + COUNT 10
```

Đừng nhầm:

- `XACK` bỏ pending entry khỏi PEL trong group.
- `XDEL` xóa entry gốc khỏi Stream.
- `XTRIM` cắt log theo chính sách.
- `XLEN` là kích thước Stream còn lưu, không phải số message chưa xử lý của một group.

**Nếu trim entry trước khi consumer xử lý hoặc recovery, PEL có thể còn ID nhưng payload đã không còn.** Bởi vậy, retention phải tính tới tốc độ ghi, group chậm nhất, pending lâu nhất, thời gian offline tối đa và nhu cầu SSE replay.

### 27.1. Dùng Redis Streams như event log có giới hạn

Streams là cấu trúc phù hợp để lưu một lượng event trong Redis, nhưng không nên mặc định Redis RAM có thể giữ toàn bộ lịch sử vô hạn. Cần:

- Giới hạn số lượng/thời gian retention theo nhu cầu.
- Dùng metrics để phát hiện backlog.
- Lưu event lâu dài ở hệ thống khác nếu có yêu cầu kiểm toán nhiều năm.
- Cân nhắc dữ liệu nhạy cảm trong payload.
- Kiểm tra cơ chế backup/persistence và failover của Redis nếu dữ liệu quan trọng.
- Thiết kế replay khi ID cuối cùng của client đã bị trim.

Nếu `Last-Event-ID` của client nhỏ hơn entry đầu tiên còn giữ trong Stream, server cần phản hồi theo chính sách: gửi snapshot hiện tại, thông báo cần đồng bộ lại hoặc từ chối resume hoàn toàn, thay vì im lặng coi như đã đọc đủ lịch sử.

## 28. Observability: cần đo cả Reactor và Redis

Một ứng dụng reactive có thể trông “không bị block” nhưng vẫn đang mất thông báo, tăng backlog hoặc xử lý trùng.

Các nhóm metrics nên quan sát:

| Thành phần | Metric hoặc tín hiệu | Ý nghĩa |
|---|---|---|
| WebFlux | Số SSE connections, số disconnect/reconnect | Mức độ kết nối realtime |
| Reactor | Buffer occupancy, onNext rate, dropped events | Client có theo kịp nguồn không |
| Pub/Sub | Message received rate, listener errors, Redis reconnect | Nhận tín hiệu realtime có ổn định không |
| Streams | `XLEN`, group lag | Backlog entry còn được giữ và chưa giao |
| Consumer group | `XPENDING`, oldest idle, per-consumer pending | Message đã giao nhưng chưa ACK |
| Recovery | Số claim, retry, DLQ | Độ ổn định worker |
| Handler | Success/failure, p95/p99 latency | Chất lượng xử lý nghiệp vụ |
| Redis | CPU, memory, network, client buffers | Tài nguyên server |
| Serialization | JSON/schema errors | Có lỗi tương thích producer/consumer không |
| Delivery | Duplicate eventId/idempotency hits | Có side effect bị giao lại không |

Các lệnh Redis thường dùng:

```redis
XINFO STREAM orders:events
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events orders-workers
XPENDING orders:events orders-workers
XPENDING orders:events orders-workers - + 20
XLEN orders:events
```

Với Pub/Sub:

```redis
PUBSUB NUMSUB events.realtime
PUBSUB NUMPAT
```

`PUBSUB NUMSUB` chủ yếu đếm direct subscriber cho channel và không phải bằng chứng mọi pattern subscriber đã nhận. Đặc biệt, `PUBLISH` return count **không phải số business event đã được xử lý thành công**.

### 28.1. Reactor Context và correlation ID

Mỗi event nên có `eventId`, `traceId` hoặc thông tin tương quan phù hợp để theo dõi qua Redis và service khác. Reactor có `Context` gắn với subscription; thread-local MDC truyền thống không tự có nghĩa đúng trong mọi bước bất đồng bộ.

Đừng chỉ dựa vào thread name để nối log từ WebFlux HTTP request tới worker Stream. Nếu event cần trace xuyên các service, mang correlation metadata trong payload và dùng instrumentation/context propagation được cấu hình phù hợp.

Không đưa thông tin nhạy cảm hoặc token xác thực thô vào tên Redis key, channel hoặc log.

## 29. Những lỗi thường gặp

### 29.1. “Gọi convertAndSend nhưng không ai nhận”

Có thể bạn tạo `Mono` nhưng không trả về và không subscribe. Kiểm tra lifecycle Publisher trước khi kiểm tra tên channel. Ngoài ra, subscriber có thể chưa đăng ký hoặc sai Redis instance.

### 29.2. “Dùng WebFlux rồi nhưng request vẫn bị treo”

Có thể code gọi `StringRedisTemplate`, JDBC blocking hoặc `.block()` trên event-loop. `Mono.just(blockingCall())` vẫn thực thi `blockingCall()` ngay trong lúc tạo Mono.

### 29.3. “Listener Pub/Sub được tạo nhưng không có message”

Kiểm tra có subscriber thật cho Flux không, container lifecycle, channel exact/pattern, serialization, connection và thời điểm publish. Pub/Sub không phát lại event trước subscription.

### 29.4. “SSE reconnect nhưng mất một số cập nhật”

SSE reconnect không làm Redis Pub/Sub replay. Nếu cần bù, sử dụng Stream ID/offset và log retention; đặt SSE `id` thôi chưa đủ.

### 29.5. “Client SSE chậm làm memory tăng”

Kiểm tra buffer/operator và số downstream subscriptions. Thiết kế drop, coalesce hoặc chuyển sang Streams theo yêu cầu; tránh buffer vô hạn.

### 29.6. “Nhân số replica thì mỗi event bị xử lý nhiều lần”

Nếu tất cả instance Pub/Sub subscribe cùng channel, tất cả đều nhận. Đây là broadcast, không phải consumer group. Chọn Redis Streams consumer group nếu mục tiêu là chia công việc giữa các worker.

### 29.7. “Stream worker nhận message rồi không nhận lại sau lỗi”

Message có thể còn trong PEL; đọc `>` chỉ lấy message mới. Cần recovery `XCLAIM`/`XAUTOCLAIM` hoặc đọc pending history của đúng consumer.

### 29.8. “Sau khi ACK, XRANGE vẫn đọc được record”

`XACK` chỉ xóa trạng thái PEL, không xóa Stream entry. Muốn hạn chế log cần retention policy.

### 29.9. “Một order event chạy hai lần sau failover”

Có thể handler commit trước ACK, rồi recovery giao lại. Áp dụng idempotency bằng eventId/unique constraint và quy tắc xử lý external side effect.

### 29.10. “Dùng latest() để đọc live Stream nhưng bỏ sót message”

Khi các lần poll có khoảng trống, offset latest có thể nhảy đến thời điểm mới nhất. Muốn đọc đủ phải theo ID hoặc dùng consumer group và xử lý pending.

### 29.11. “Thêm flatMap làm event bị xử lý sai thứ tự”

`flatMap` cho concurrency, có thể hoàn tất out-of-order. Nếu các event cùng entity yêu cầu thứ tự, dùng `concatMap`, partition hoặc sequence checks.

### 29.12. “RetryWhen vô hạn nhưng event vẫn mất”

Retry Reactor không tạo lại message Pub/Sub đã mất và không tự claim PEL. Phải thiết kế recovery đúng theo cơ chế Redis tương ứng.

### 29.13. “Đã viết Redis Stream nhưng consumer mới không thấy event”

Group có thể được tạo bằng `$` sau khi event đã tồn tại, consumer dùng sai offset, hoặc event đã bị trim. Cần kiểm tra group creation/last-delivered-id và retention.

### 29.14. “Thay StringRedisTemplate bằng ReactiveRedisTemplate, payload trở thành binary khó đọc”

Do cấu hình serializer thay đổi. Cần thống nhất key/field/value serialization và JSON schema; reactive không quyết định tự động định dạng dữ liệu.

## 30. Hướng dẫn thiết kế theo từng nhu cầu

### 30.1. Thông báo UI “có dữ liệu mới”

Yêu cầu: client có thể bỏ lỡ một notification vì khi mở trang nó sẽ tải snapshot mới nhất.

Chọn:

```text
Business update
  -> PUBLISH notification
  -> WebFlux Pub/Sub listener
  -> SSE
  -> Browser gọi API lấy snapshot nếu cần
```

Lợi ích: thiết kế đơn giản, ít state server. Hạn chế: disconnect có thể mất notification, nên client phải có cơ chế lấy lại trạng thái mới nhất.

### 30.2. Xử lý hóa đơn cần retry

Yêu cầu: sau khi nhận một invoice event, tác vụ phải được xử lý hoặc chuyển DLQ, ngay cả khi worker crash.

Chọn:

```text
XADD invoice:events
  -> Reactive StreamReceiver / consumer group
  -> idempotent handler
  -> XACK
  -> recovery pending + DLQ
```

Không dùng Pub/Sub thuần làm nguồn duy nhất cho nghĩa vụ này.

### 30.3. Dashboard phải xem lịch sử khi reconnect

Yêu cầu: client có `Last-Event-ID`, muốn xem lại event đã bỏ lỡ trong 10 phút gần nhất.

Chọn:

```text
XADD metrics:events
  -> WebFlux XREAD by ID
  -> SSE id = Stream ID
  -> reconnect đọc từ ID sau cùng
```

Cần retention đủ dài và chính sách fallback khi ID đã bị trim. Nếu dùng shared fan-out, phải giải quyết race giữa historical replay và live emission.

### 30.4. Một event kích hoạt đồng thời hai nhóm xử lý độc lập

Ví dụ: `OrderCreated` cần xử lý thanh toán và audit.

Có thể dùng hai consumer group:

```text
Stream orders:events
  |
  +-- payment-workers group -> xử lý thanh toán, ACK riêng
  |
  +-- audit-workers group   -> ghi audit, ACK riêng
```

Mỗi group có tiến độ và PEL riêng. ACK của payment group không ACK thay audit group. Retention phải đủ cho nhóm chậm hơn.

### 30.5. Một signal và một workflow

Có thể dùng cả hai:

```text
Event vào Stream -> workflow bền vững hơn
         |
         +-- Pub/Sub notification -> UI realtime
```

Nếu việc publish Pub/Sub bị thất bại nhưng Stream đã có entry, UI có thể cần poll/read backfill để đối chiếu. Nếu Pub/Sub phát trước khi Stream ghi thành công, UI có thể nhìn thấy event chưa tồn tại trong log. Thứ tự và cách reconcile phải được xác định.

## 31. Bài thực hành: Pub/Sub và SSE

### Bài 1 — Phân biệt lazy publisher

Viết:

```java
Mono<Long> publish =
    reactiveRedisTemplate.convertAndSend(
        "lab.realtime",
        "hello"
    );
```

Không subscribe/return Mono; quan sát subscriber Pub/Sub. Sau đó nối Mono vào controller và thử lại. Giải thích khác biệt giữa mô tả thao tác reactive với việc thao tác thực sự chạy.

### Bài 2 — Reactive listener

Tạo `ReactiveRedisMessageListenerContainer`, đăng ký `ChannelTopic("lab.realtime")` và chuyển dữ liệu sang Flux String. Publish từ Redis CLI:

```redis
PUBLISH lab.realtime hello
```

Thử publish trước khi subscriber kết nối và sau khi subscriber kết nối. Giải thích vì sao thông điệp trước subscription không được replay.

### Bài 3 — SSE

Viết endpoint `/lab/events` trả `Flux<ServerSentEvent<String>>`. Mở một `EventSource` trong browser, rồi publish vài message. Đóng tab và mở lại. Giải thích tại sao các message gửi trong lúc đóng tab không tự xuất hiện lại.

### Bài 4 — Client chậm và backpressure

Tạo nguồn message nhanh hơn tốc độ client hiển thị. So sánh `onBackpressureLatest` với buffer hữu hạn. Mô tả loại dữ liệu nào cho phép drop (chẳng hạn trạng thái đo liên tục) và loại nào tuyệt đối không nên drop (lệnh thanh toán).

## 32. Bài thực hành: Streams và acknowledgment

### Bài 5 — Tạo Stream và group

```redis
XGROUP CREATE lab:orders lab-workers 0 MKSTREAM
XADD lab:orders * eventId evt-1 type CREATED
XADD lab:orders * eventId evt-2 type PAID
```

Cho consumer đọc:

```redis
XREADGROUP GROUP lab-workers worker-A COUNT 2 STREAMS lab:orders >
```

Xem PEL:

```redis
XPENDING lab:orders lab-workers
```

ACK một ID thực trả từ Redis:

```text
XACK lab:orders lab-workers <ID>
```

Kiểm tra PEL giảm trong khi dữ liệu Stream vẫn có thể còn.

### Bài 6 — Từ Flux record đến ACK

Viết handler `Mono<Void>` giả lập xử lý bất đồng bộ. Dùng `concatMap` để xử lý từng record và `then(acknowledge(...))` để ACK sau khi handler thành công. Chèn một lỗi cố ý vào handler. Quan sát entry lỗi vẫn pending.

### Bài 7 — Recovery sau crash

Cho consumer-A đọc một message nhưng không ACK. Khởi động consumer-B và đọc message mới bằng `>`. Kiểm tra message của A không tự xuất hiện ở B. Sau khi đủ idle, dùng `XAUTOCLAIM` hoặc `XCLAIM`, xử lý lại và ACK.

### Bài 8 — Idempotency

Giả lập:

```text
Handler cập nhật DB thành công.
Worker crash trước XACK.
Recovery giao lại message.
```

Thiết kế unique key theo `eventId` trong transaction database. Giải thích tại sao method reactive hoàn tất thành công không đồng nghĩa Redis ACK chắc chắn được ghi nếu process bị crash giữa hai bước.

### Bài 9 — Thứ tự xử lý

Tạo ba event cùng `orderId` với sequence tăng. So sánh xử lý bằng `flatMap` concurrency cao với `concatMap`. Đề xuất thêm `version` trong database để không cho event cũ ghi đè trạng thái mới.

### Bài 10 — Resume SSE bằng Stream ID

Lưu entry Stream, tạo SSE event với `id = record.getId().getValue()`. Khi client reconnect với ID cuối, đọc những entry có ID lớn hơn ID đó. Thảo luận việc cần xử lý nếu ID đã bị trim và race khi chuyển sang live feed.

## 33. Tự đánh giá

1. WebFlux/Reactive Redis có tự làm Pub/Sub message bền vững không?
2. Vì sao một `Mono<Long>` do `convertAndSend` tạo ra có thể chưa gửi lệnh Redis?
3. `ReactiveRedisMessageListenerContainer` dùng cho kiểu dữ liệu Redis nào?
4. Vì sao SSE `Last-Event-ID` không tự replay Pub/Sub?
5. Backpressure trong Reactor có buộc Redis publisher ngừng phát message không?
6. Vì sao nên tránh `.block()` trên Netty event-loop?
7. `XADD` và `PUBLISH` khác nhau về lưu trữ như thế nào?
8. `XREADGROUP ... >` khiến message đi vào PEL khi nào?
9. Vì sao `XACK` không xóa entry gốc khỏi Stream?
10. Vì sao nhóm worker dùng chung consumer group không phù hợp để broadcast mọi event cho mọi SSE client?
11. Khi worker crash trước ACK, thông điệp được phục hồi bằng cơ chế nào?
12. `ReadOffset.latest()` có rủi ro gì trong các khoảng ngừng polling?
13. Vì sao `flatMap` có thể không giữ thứ tự hiệu lực của nghiệp vụ?
14. Khi database commit rồi Redis ACK thất bại, idempotency giải quyết vấn đề gì?
15. Nếu Stream bị trim trước khi consumer đọc bù, client cần xử lý thế nào?
16. Có thể đặt một `Flux` bean mà không subscribe rồi kỳ vọng background worker chạy không?
17. Tại sao cần tách retry transport khỏi retry lỗi nghiệp vụ?
18. Nếu producer ghi Stream và publish Pub/Sub bằng hai lệnh riêng, có những failure window nào?
19. Classic Pub/Sub và sharded Pub/Sub khác nhau ra sao ở mức Redis Cluster?
20. Một hệ thống cần guaranteed delivery nên chọn hướng nào thay vì Pub/Sub thuần?

## 34. Ghi nhớ

- **Spring WebFlux và Reactive Redis** cung cấp mô hình I/O bất đồng bộ; **Pub/Sub và Streams** quyết định ngữ nghĩa giao sự kiện.
- Pub/Sub phù hợp tín hiệu realtime khi subscriber đang online; **không có backlog, ACK hay replay**.
- Streams lưu entry có ID; consumer group theo dõi message đã giao bằng **PEL**, và consumer phải **`XACK` sau khi xử lý thành công**.
- Với Reactor, `Mono`/`Flux` cần có subscription thực sự. Controller nên trả Publisher; background worker cần lifecycle và `Disposable` được quản lý rõ.
- `ReactiveRedisMessageListenerContainer` hỗ trợ luồng Pub/Sub; `ReactiveStreamOperations`/`StreamReceiver` phục vụ luồng Streams.
- SSE kết hợp Pub/Sub không tự có resume. Nếu cần đọc bù theo `Last-Event-ID`, hãy lưu log như Streams và quản lý retention/offset.
- **Backpressure trong Java không buộc Redis Pub/Sub chờ từng client**. Phải chọn chính sách buffer, drop, coalesce, disconnect hoặc chuyển sang log có retention.
- WebFlux không nên gọi blocking Redis/JDBC trên event-loop; nếu tích hợp legacy blocking code, cần cô lập và giới hạn tài nguyên.
- Stream consumer group dùng để **chia việc**, không phải broadcast tới tất cả browser. Các group độc lập có tiến độ riêng.
- **`XACK` và business commit không tự atomic xuyên Redis và database**. Idempotency, outbox và recovery là các thành phần cần thiết cho nghiệp vụ quan trọng.
- Reader chỉ đọc message mới không tự nhận pending của worker khác. Cần `XPENDING`, `XCLAIM` hoặc `XAUTOCLAIM` khi phục hồi.
- Cẩn trọng với offset `latest()`, concurrency `flatMap`, cancellation và retention để không bỏ sót hoặc xử lý sai thứ tự.
- Trong Redis Cluster, kiểm tra hash slot của các Stream keys và khả năng của driver đối với classic/sharded Pub/Sub.
- Chọn kiến trúc theo câu hỏi đầu tiên: **“Thông điệp này chỉ cần realtime, hay phải được xử lý/replay sau sự cố?”**

### Tài liệu tham khảo chính thức

- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Framework — WebFlux Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Data Redis — Redis Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Data Redis — Reactive RedisMessageListenerContainer API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/listener/ReactiveRedisMessageListenerContainer.html)
- [Spring Data Redis — StreamReceiver API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/stream/StreamReceiver.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/)
- [Redis — XREAD](https://redis.io/docs/latest/commands/xread/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/)
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/)
