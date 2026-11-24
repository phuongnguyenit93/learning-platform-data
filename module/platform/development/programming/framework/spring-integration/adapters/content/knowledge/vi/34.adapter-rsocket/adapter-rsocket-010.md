# Reactive backpressure trong RSocket

## 1. Bối cảnh: khi producer nhanh hơn consumer

Trong module **SPRING_INTEGRATION_ADAPTERS**, ứng dụng kết nối hệ thống bên ngoài vào Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`. Một yêu cầu quan trọng khi trao đổi qua RSocket là kiểm soát **tốc độ chuyển dữ liệu**: server có thể phát hàng nghìn cập nhật kho mỗi giây, nhưng flow xử lý và database phía client chỉ ghi được vài trăm cập nhật.

Giả sử route `inventory.events` phát liên tục các sự kiện tồn kho. Nếu cứ nhận mọi sự kiện mà không điều tiết, bộ nhớ đệm tăng dần, độ trễ cộng dồn và có thể dẫn tới lỗi hết bộ nhớ. **Reactive backpressure** cho phép bên tiêu thụ thông báo mình sẵn sàng nhận thêm bao nhiêu phần tử, từ đó bên phát giới hạn lưu lượng theo nhu cầu.

~~~text
Nguồn sự kiện  ------->  RSocket  ------->  Spring Integration  ---> DB
     nhanh             truyền frame           xử lý chậm

Không giới hạn: 500 event/s đến, 200 event/s xử lý
              -> backlog tăng khoảng 300 event/s

Có backpressure:
  Consumer yêu cầu N phần tử
  Producer chỉ phát theo nhu cầu hợp lệ
  Các thành phần trung gian cần tôn trọng hoặc chuyển tiếp demand
~~~

Bài **Reactive backpressure trong RSocket**, thuộc chương **Adapter RSocket**, giúp bạn:

- Hiểu quan hệ giữa **Publisher**, **Subscriber**, **Subscription** và yêu cầu số phần tử.
- Phân biệt `REQUEST_N`, `CANCEL`, timeout và cơ chế request-reply ở RSocket.
- Nhìn thấy demand truyền từ `RSocketRequester` tới responder với `Flux`.
- Nhận ra điểm backpressure bị đứt khi chuyển sang queue, blocking gateway hoặc nguồn push không hỗ trợ demand.
- Chọn giới hạn concurrency, prefetch, buffer, xử lý quá tải và chiến lược nghiệp vụ phù hợp.
- Kiểm thử demand thật, các điều kiện tải chậm và quá trình giải phóng resource.

## 2. Cốt lõi Reactive Streams: bên nhận điều khiển demand

Theo mô hình Reactive Streams:

| Thành phần | Vai trò | Ví dụ trong ứng dụng |
| --- | --- | --- |
| `Publisher<T>` | Cung cấp các phần tử theo tín hiệu yêu cầu | `Flux<StockEvent>` |
| `Subscriber<T>` | Tiêu thụ phần tử và điều phối yêu cầu | Subscriber do Reactor hoặc người lập trình tạo |
| `Subscription` | Kênh điều khiển giữa hai bên | `request(n)` và `cancel()` |
| `onNext(T)` | Gửi một phần tử | Một `StockEvent` |
| `onError(Throwable)` | Kết thúc vì lỗi | Codec lỗi, nguồn thất bại, buffer tràn |
| `onComplete()` | Hoàn thành bình thường | Đã gửi hết danh sách hữu hạn |

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    S->>P: subscribe()
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(event 1)
    P-->>S: onNext(event 2)
    Note over P: Chưa có yêu cầu thêm
    S->>P: request(1)
    P-->>S: onNext(event 3)
    S->>P: cancel()
    Note over P,S: Dừng subscription, cleanup
~~~

Các nguyên tắc:

1. Với một subscription bình thường, publisher **không được phát `onNext` vượt tổng demand đã được cấp**.
2. `request(n)` với `n > 0` cấp thêm nhu cầu; nhiều lần request được cộng dồn có giới hạn và có thể được hiểu là nhu cầu rất lớn/không giới hạn.
3. `request(0)` hoặc số âm **không hợp lệ** theo Reactive Streams; không sử dụng chúng để “tạm dừng”. Để chưa nhận dữ liệu, đơn giản là không request thêm.
4. `cancel()` biểu thị subscriber không cần dữ liệu tiếp. Đây không phải lỗi và không tự hoàn tác thao tác nghiệp vụ đã hoàn thành.
5. Chỉ có **subscriber thực sự điều phối yêu cầu** mới tạo ra backpressure có ích. Việc một phương thức trả về `Flux` chưa bảo đảm nguồn ở cuối chuỗi sẽ chậm lại.

**Backpressure là cơ chế điều phối lưu lượng, không phải lưu trữ bền vững.** Nếu nguồn bên ngoài không thể ngừng phát, dữ liệu vẫn cần buffer, drop, gửi đi một kho lưu trữ hoặc thực hiện chính sách quá tải được định nghĩa trước.

## 3. `REQUEST_N`: cách RSocket chuyển demand qua mạng

RSocket tích hợp cơ chế backpressure cho những tương tác truyền nhiều phần tử. Khi subscriber ở một bên yêu cầu thêm dữ liệu, RSocket dùng khái niệm **request N** để giới hạn số payload tiếp theo mà peer được phép phát theo hướng đó.

### 3.1. Các frame liên quan

| Frame/tín hiệu | Tác dụng | Lưu ý |
| --- | --- | --- |
| `REQUEST_STREAM` | Bắt đầu request-stream, có **initial request N** | Kèm route, data/metadata theo hợp đồng |
| `REQUEST_CHANNEL` | Bắt đầu request-channel, bao gồm initial request N cho phía phản hồi | Hai chiều truyền dữ liệu có demand riêng |
| `REQUEST_N` | Bổ sung số phần tử phía nhận sẵn sàng nhận | Áp dụng trên stream tương ứng |
| `PAYLOAD` | Chuyển phần tử data/metadata được mã hóa | Phải tuân thủ nhu cầu và trạng thái stream |
| `CANCEL` | Yêu cầu dừng tương tác/stream | Khác với tạm thời chưa request thêm |
| `ERROR` | Kết thúc tương tác lỗi | Không thay cho backpressure |

Đối với **request-stream**, initial request N nằm ngay trong frame khởi đầu `REQUEST_STREAM`; các nhu cầu bổ sung có thể gửi bằng `REQUEST_N`. Vì vậy không nên nghĩ rằng **mọi** lần request đều tạo một frame `REQUEST_N` riêng: demand có thể được gom và gửi trong frame ban đầu hoặc được tối ưu bởi implementation.

### 3.2. Backpressure tùy kiểu tương tác

| Tương tác RSocket | Kết quả | Backpressure có ý nghĩa ở đâu? |
| --- | --- | --- |
| Request-response | Tối đa một phản hồi nghiệp vụ | Không cần request N lặp lại cho response đơn |
| Fire-and-forget | Không có reply payload nghiệp vụ | Không phải mô hình stream có request N |
| Request-stream | Nhiều response từ responder | Requester điều phối số response được phát |
| Request-channel | Luồng phần tử hai chiều | Mỗi chiều phải tuân theo demand của bên nhận chiều đó |

Ví dụ một request-stream hữu hạn:

~~~mermaid
sequenceDiagram
    participant C as Client / requester
    participant R as RSocket responder
    C->>R: REQUEST_STREAM inventory.snapshot (initial N=2)
    R-->>C: PAYLOAD item 1
    R-->>C: PAYLOAD item 2
    Note over R,C: Producer không có thêm demand cho item 3
    C->>R: REQUEST_N(2)
    R-->>C: PAYLOAD item 3
    R-->>C: PAYLOAD item 4
    C->>R: CANCEL
~~~

Sơ đồ chỉ minh họa **giới hạn phần tử ở tầng giao thức**. Số lượng frame thực tế, cách gom nhu cầu, prefetch, fragmentation và thời điểm scheduler phát các tín hiệu phụ thuộc thư viện/transport. Một yêu cầu `request(1)` tại Reactor không nhất thiết tương ứng với **đúng một frame mạng** cho mọi cấu hình.

### 3.3. Hai chiều request-channel

Trong request-channel, client gửi một `Publisher<RequestItem>` và nhận một `Publisher<ReplyItem>`. **Server** có thể điều phối demand đối với request item mà nó nhận; **client** điều phối demand đối với reply item mà nó nhận. Hai chiều điều phối độc lập:

~~~text
Client                                Server
  request items --------------------->  Server nhận theo demand phía server
  reply items   <---------------------  Client nhận theo demand phía client

Hai chiều đều có thể có REQUEST_N / CANCEL tùy trạng thái stream.
~~~

Không dùng một biến “window size” duy nhất để suy luận cả hai chiều sẽ luôn tiến cùng tốc độ. Nếu một phía cần gom dữ liệu từ nhiều request item trước khi trả reply, phải kiểm soát queue/buffer trung gian và các tình huống ngừng tiến triển.

## 4. Ví dụ server: phát `Flux` theo demand

Trong Spring Boot 3 / Spring Framework 6, `@MessageMapping` có thể trả về `Flux<T>` cho route request-stream. Đoạn sau dùng `Flux.range`, một publisher **cold** và có khả năng đáp ứng demand, để minh họa mà không phụ thuộc external event broker.

### 4.1. DTO và responder

~~~java
record SnapshotQuery(String warehouseId) {}

record StockEvent(String warehouseId, int sequence, int available) {}
~~~

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class StockSnapshotRSocketController {
    private static final Logger log =
        LoggerFactory.getLogger(StockSnapshotRSocketController.class);

    @MessageMapping("inventory.snapshot")
    Flux<StockEvent> snapshot(@Payload SnapshotQuery query) {
        return Flux.range(1, 100)
            .map(sequence -> new StockEvent(
                query.warehouseId(),
                sequence,
                1000 - sequence
            ))
            .doOnRequest(n ->
                log.debug("Downstream requested {} more items", n))
            .doOnCancel(() -> log.debug("Snapshot cancelled"));
    }
}
~~~

Khi subscriber phía client yêu cầu dữ liệu, demand đi qua lớp RSocket đến chuỗi Reactor trên server. `Flux.range` chỉ phát thêm trong giới hạn demand còn lại, vì vậy không cần gom trước cả 100 event vào một `List`.

Trong ví dụ, `doOnRequest` giúp quan sát yêu cầu ở vị trí operator. Giá trị log ở đây **không nhất thiết bằng từng `REQUEST_N` trên wire**: Reactor có thể prefetch hoặc thay đổi kích thước yêu cầu giữa các operator. Để kiểm tra giao thức, cần thêm integration test qua RSocket và công cụ quan sát frame khi cần.

### 4.2. Client sử dụng RSocketRequester

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Flux;

class StockSnapshotClient {
    private final RSocketRequester requester;

    StockSnapshotClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .tcp("localhost", 7000);
    }

    Flux<StockEvent> snapshot(String warehouseId) {
        return requester.route("inventory.snapshot")
            .data(new SnapshotQuery(warehouseId))
            .retrieveFlux(StockEvent.class);
    }
}
~~~

`retrieveFlux(StockEvent.class)` tạo một publisher cho dữ liệu response. Subscription bắt đầu khi có consumer subscribe, và demand phụ thuộc **chuỗi operator/subscriber phía sau**. Nếu client gọi `subscribe(event -> ...)` thông thường, Reactor thường yêu cầu lượng dữ liệu rất lớn. Điều đó không thể hiện chiến lược tiêu thụ chậm.

## 5. Kiểm soát demand phía client

### 5.1. Dùng `BaseSubscriber` để nhìn rõ `request(n)`

Một ví dụ học tập với công việc xử lý nhanh:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

Flux<StockEvent> stream = client.snapshot("warehouse-a");

stream.subscribe(new BaseSubscriber<StockEvent>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(StockEvent event) {
        System.out.println("Received: " + event.sequence());
        request(1);
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.err.println("Stream failed: " + error);
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Snapshot completed");
    }
});
~~~

Ở mức **Reactive Streams demand**, subscriber trên chỉ bổ sung một đơn vị sau mỗi phần tử đã xử lý. Tuy nhiên đừng đưa một lời gọi JDBC/HTTP **blocking** vào `hookOnNext`, vì callback có thể chạy trên event loop hoặc scheduler nhạy với độ trễ. Đối với xử lý I/O thực, ưu tiên chuỗi reactive có giới hạn concurrency; nếu bắt buộc dùng API blocking, chuyển sang scheduler phù hợp và giới hạn số tác vụ đồng thời.

Đoạn demo cũng không thay thế xử lý cancellation: trong UI, cần hủy `Subscription`/`Disposable` theo lifecycle màn hình nếu người dùng không còn nhận stream.

### 5.2. Dùng `concatMap` để gắn demand với xử lý bất đồng bộ

Giả sử `StockEventStore` là dịch vụ lưu sự kiện **non-blocking** và `save(...)` hoàn thành sau khi tác vụ lưu được xác nhận:

~~~java
import reactor.core.publisher.Mono;

interface StockEventStore {
    Mono<Void> save(StockEvent event);
}
~~~

Ta có thể xử lý từng event theo thứ tự:

~~~java
Mono<Void> consumeInOrder(
        StockSnapshotClient client,
        StockEventStore store) {

    return client.snapshot("warehouse-a")
        .concatMap(event -> store.save(event), 1)
        .then();
}
~~~

Ở đây `concatMap` giữ thứ tự xử lý và giới hạn việc đăng ký publisher con. Tham số `1` là **prefetch** được dùng trong ví dụ, giúp không yêu cầu trước một lượng lớn event từ upstream. Chỉ khi việc lưu trước đó hoàn thành, chuỗi mới có thể tiếp tục tiến.

Nếu công việc cho phép song song, `flatMap` với giới hạn concurrency có thể tăng throughput:

~~~java
Mono<Void> consumeWithBoundedConcurrency(
        StockSnapshotClient client,
        StockEventStore store) {

    int maxConcurrentSaves = 8;

    return client.snapshot("warehouse-a")
        .flatMap(
            event -> store.save(event),
            maxConcurrentSaves,
            1
        )
        .then();
}
~~~

Ở đây cùng lúc chỉ có tối đa **8 publisher lưu** đang được đăng ký thông qua toán tử đó; thực tế thông lượng còn phụ thuộc giới hạn kết nối DB, thread, CPU và những operator đứng trước/sau. `flatMap` không giữ thứ tự hoàn tất. Nếu các event phải cập nhật cùng một bản ghi theo sequence, hãy dùng `concatMap`, phân vùng theo key hoặc một cơ chế đồng bộ theo thứ tự.

**Điều kiện quan trọng:** `store.save(event)` phải phản ánh việc xử lý thật sự hoàn tất. Nếu method chỉ đẩy event vào queue rồi trả `Mono.empty()`, demand có thể tăng tiếp dù worker phía sau chưa kịp xử lý.

## 6. Ranh giới Spring Integration: demand có truyền xuyên flow không?

Một đường đi điển hình:

~~~mermaid
flowchart LR
    A["RSocket subscriber"] --> B["RSocket responder / requester"]
    B --> C["Reactive Publisher"]
    C --> D["MessageChannel / IntegrationFlow"]
    D --> E["DB / JMS / Kafka / HTTP adapter"]
~~~

Điều cần hỏi không phải chỉ là “RSocket có backpressure không?”, mà là **mỗi thành phần trong chuỗi có thực sự tôn trọng demand của thành phần sau hay không?**

| Biên tích hợp | Tính chất thường gặp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| RSocket `Flux` → Reactor operator | Demand được truyền qua Reactive Streams khi operator hỗ trợ | Prefetch, buffer do operator tạo |
| `DirectChannel` → handler đồng bộ | Gửi message theo lời gọi, xử lý trực tiếp trong luồng gửi | Blocking handler có thể chặn thread gọi |
| `ExecutorChannel` / executor | Giao việc cho thread pool | Hàng đợi executor và số tác vụ đang chờ |
| `QueueChannel` → poller | Message được đưa vào queue rồi xử lý sau | Queue tăng nhanh nếu producer không bị giới hạn |
| `FluxMessageChannel` | Hỗ trợ cách tiêu thụ theo Reactive Streams | Cần đấu nối publisher/subscriber đúng cách; buffer và subscription vẫn phải được quản lý |
| Outbound HTTP/JMS/Kafka adapter | Giao thức và cơ chế gửi riêng | RSocket demand không tự động chảy xuyên mọi adapter ngoài |

Spring Integration có các thành phần hỗ trợ reactive flow, nhưng **không thể suy ra tất cả `MessageChannel` đều có backpressure từ tên gọi**. Ví dụ, một inbound RSocket handler có thể tạo `Flux` rồi gọi một messaging gateway **đồng bộ**; khi đó cầu nối phải điều phối số request đồng thời hoặc chuyển công việc blocking sang scheduler phù hợp.

### 6.1. Ví dụ kết hợp RSocket và messaging gateway đồng bộ

Giả sử ứng dụng có Spring Integration flow để enrich mỗi event bằng một thao tác nghiệp vụ đồng bộ. Các kiểu DTO của ví dụ:

~~~java
record StockView(
    String warehouseId,
    int sequence,
    int available,
    String label
) {}
~~~

Khai báo gateway và IntegrationFlow:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@MessagingGateway
interface StockEnrichmentGateway {
    @Gateway(requestChannel = "stockEnrichmentInput")
    StockView enrich(StockEvent event);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class StockEnrichmentConfiguration {

    @Bean
    IntegrationFlow stockEnrichmentFlow() {
        return IntegrationFlow.from("stockEnrichmentInput")
            .handle(StockEvent.class, (event, headers) ->
                new StockView(
                    event.warehouseId(),
                    event.sequence(),
                    event.available(),
                    "CHECKED"
                )
            )
            .get();
    }
}
~~~

Responder nối từng phần tử của `Flux` với gateway:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Controller
class StockEnrichedRSocketController {
    private final StockEnrichmentGateway gateway;

    StockEnrichedRSocketController(StockEnrichmentGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("inventory.enriched-snapshot")
    Flux<StockView> snapshot(@Payload SnapshotQuery query) {
        return Flux.range(1, 100)
            .map(i -> new StockEvent(
                query.warehouseId(),
                i,
                1000 - i
            ))
            .concatMap(event ->
                Mono.fromCallable(() -> gateway.enrich(event))
                    .subscribeOn(Schedulers.boundedElastic()),
                1
            );
    }
}
~~~

Đây là một **cầu nối có giới hạn**:

1. `Flux.range` chỉ tạo event khi được yêu cầu.
2. `concatMap(..., 1)` giới hạn xử lý nối tiếp và prefetch trong ví dụ.
3. `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` chuyển gateway đồng bộ ra khỏi RSocket event loop.
4. Gateway chuyển event qua `MessageChannel` và `IntegrationFlow` rồi trả `StockView`.
5. RSocket response stream phát `StockView` theo nhu cầu của client.

Vì lời gọi gateway trong ví dụ là **blocking**, cancellation từ client không mặc nhiên hủy ngay một thao tác đang chạy trong gateway, DB hoặc adapter khác. `boundedElastic()` cũng không biến API blocking thành non-blocking. Nên dùng dịch vụ reactive thật sự khi cần khả năng điều phối end-to-end, hoặc thiết kế giới hạn concurrency và timeout của tài nguyên bên dưới.

**Không đăng ký đồng thời hai responder cho cùng route** nếu bạn giữ ví dụ `inventory.snapshot` ở phần trước. Ở đây sử dụng route `inventory.enriched-snapshot` để tách hợp đồng.

### 6.2. Nếu đưa message vào queue hoặc poller

Ví dụ producer gửi nhanh vào `QueueChannel`, poller tiêu thụ chậm:

~~~text
RSocket inbound
   -> QueueChannel (capacity ?)
   -> poller (maxMessagesPerPoll ?)
   -> handler

Nếu channel nhận/ACK việc gửi trước khi handler xử lý:
  việc upstream đã hoàn thành != việc xử lý nghiệp vụ đã xong.
~~~

Một queue dung lượng hữu hạn giúp tránh tăng bộ nhớ không giới hạn, nhưng **queue full sẽ dẫn đến chờ, lỗi hoặc từ chối gửi**, tùy cấu hình. Nó không tự động gửi demand ngược đến RSocket client nếu cầu nối chỉ gọi `send(...)` như một side effect rồi trả ngay.

Khi thiết kế:

- Đặt **capacity** rõ ràng và giám sát số message chờ.
- Phân biệt đã nhận vào queue, đã xử lý thành công và đã commit nghiệp vụ.
- Giới hạn số task executor, số message mỗi poll và tốc độ nhận upstream.
- Với dữ liệu không thể mất, dùng message store/broker bền vững và chính sách retry/deduplication.
- Tránh biến hủy RSocket stream thành giả định queue/job đã bị hủy.

## 7. Backpressure không xử lý được mọi loại nguồn

### 7.1. Cold source có hỗ trợ demand

`Flux.range`, `Flux.fromIterable` hoặc nhiều publisher từ reactive driver có thể chờ downstream yêu cầu trước khi phát. Đây là trường hợp đơn giản nhất để chứng minh `REQUEST_N` hoạt động.

~~~java
Flux<Integer> cold = Flux.range(1, 1_000_000)
    .doOnRequest(n ->
        System.out.println("requested = " + n));
~~~

Không có `collectList()` thì nguồn này không cần dựng ngay một triệu object trong bộ nhớ. Tuy nhiên nếu sau đó dùng `collectList()`, bộ nhớ dùng để gom toàn bộ dữ liệu vẫn có thể rất lớn.

### 7.2. Hot/push source không thể dừng theo demand

Sensor, callback từ thư viện cũ, UDP receiver hoặc external broker có thể đẩy dữ liệu liên tục dù RSocket subscriber không yêu cầu thêm. Trong Reactor, một callback được nối bằng `Flux.create` hoặc sink mà không có chính sách backpressure rõ ràng có nguy cơ tích lũy dữ liệu.

Ví dụ phản ví dụ:

~~~java
// Minh họa nguy cơ: externalFeed phát theo tốc độ riêng.
Flux<StockEvent> events = Flux.create(sink ->
    externalFeed.onEvent(sink::next)
);
~~~

`externalFeed` là API giả định. Đoạn minh họa **chưa có lifecycle cleanup, giới hạn buffer, quản lý lỗi hay backpressure**, không dùng trực tiếp trong production.

Phải lựa chọn chính sách khi nguồn không thể chậm lại:

| Chính sách | Công cụ/minh họa | Phù hợp với |
| --- | --- | --- |
| Chuyển demand tới nguồn | Reactive driver, `sink.onRequest(...)` | Nguồn hỗ trợ lấy theo nhu cầu |
| Buffer hữu hạn, báo lỗi khi tràn | `onBackpressureBuffer(capacity)` và xử lý overflow | Chịu burst ngắn, không chấp nhận tăng RAM mãi |
| Bỏ bớt phần tử | `onBackpressureDrop(...)` | Telemetry hoặc số liệu có thể mất mẫu |
| Giữ phần tử mới nhất | `onBackpressureLatest()` | Trạng thái dashboard, không cần từng thay đổi |
| Lưu bền rồi phát lại | Broker/event log + checkpoint | CDC, đơn hàng, giao dịch không được mất |
| Từ chối/tạm ngừng nguồn | Flow control ở ứng dụng/transport khác | Có thể yêu cầu upstream tạm dừng |

Một **bounded buffer** làm rõ lúc hệ thống quá tải; nó **không khiến nguồn push đột nhiên hỗ trợ demand**. Khi đầy, cần chính sách lỗi hoặc bỏ dữ liệu được chấp nhận bởi hợp đồng nghiệp vụ. Với dữ liệu quan trọng, không dùng drop/latest như một cách “giải quyết” nghẽn mà không có replay.

### 7.3. `Flux.interval` và nguồn theo thời gian

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100));
~~~

Nguồn phát theo đồng hồ có thể không đáp ứng được nếu subscriber không yêu cầu phần tử đúng lúc; trong Reactor, `Flux.interval` có thể phát lỗi vì thiếu demand cho tick. Nó **khác** `Flux.range` là nguồn hữu hạn chờ demand.

Nếu muốn thử khả năng điều phối demand, bắt đầu với `Flux.range` hoặc nguồn có `onRequest` thật sự. Nếu dùng nguồn thời gian, kiểm tra các tình huống demand bằng không, buffer đầy và cancellation.

## 8. Các operator Reactor hay gây hiểu nhầm

| Operator | Ý nghĩa chính | Điều cần quan sát |
| --- | --- | --- |
| `limitRate(32)` | Chia nhỏ yêu cầu downstream thành đợt yêu cầu upstream | Không chứng minh đã có giới hạn bộ nhớ mọi tầng |
| `concatMap(mapper, prefetch)` | Giữ thứ tự, điều phối publisher con và prefetch | Độ trễ từng item có thể giảm throughput |
| `flatMap(mapper, concurrency, prefetch)` | Cho phép xử lý song song có giới hạn | Không giữ thứ tự hoàn thành, cần giới hạn tài nguyên |
| `publishOn(scheduler, prefetch)` | Chuyển ngữ cảnh thực thi qua một queue có prefetch | Queue của scheduler và số task có thể gây backlog |
| `onBackpressureBuffer(capacity)` | Giữ phần tử khi downstream chậm, với giới hạn xác định | Đặt chính sách overflow; có thể làm nguồn upstream request nhiều |
| `onBackpressureDrop(...)` | Bỏ phần tử không thể giao kịp | Chỉ dùng khi chấp nhận mất sự kiện |
| `onBackpressureLatest()` | Giữ trạng thái mới nhất khi downstream chậm | Có thể bỏ qua các trạng thái trung gian |
| `take(n)` | Hoàn tất sau n phần tử và cancel upstream | Thao tác kết thúc, khác tạm giảm tốc |
| `timeout(Duration)` | Báo lỗi khi quá thời gian chờ tín hiệu tiếp theo | Timeout không phải `REQUEST_N` |
| `retryWhen(...)` | Tạo lại subscription sau lỗi | Có thể nhận lại dữ liệu hoặc chạy lại side effect |

Ví dụ giới hạn yêu cầu từ upstream:

~~~java
Flux<StockEvent> controlled = client.snapshot("warehouse-a")
    .limitRate(32)
    .doOnRequest(n ->
        System.out.println("Consumer requested " + n));
~~~

`limitRate(32)` giúp điều chỉnh cách **yêu cầu upstream** được chia thành lô; nó không đồng nghĩa “toàn hệ thống chỉ có 32 message trong RAM”, bởi codec, prefetch của các operator khác, queue, driver và broker vẫn có thể giữ dữ liệu. Để kiểm soát bộ nhớ phải tính toàn bộ pipeline.

Đặc biệt, `onBackpressureBuffer(...)` thường **ngăn lan truyền backpressure trực tiếp** từ downstream tới upstream bằng cách nhận và lưu các item để tiêu thụ sau. Đừng chèn buffer tùy tiện vào mọi nhánh rồi coi đó là điều phối demand end-to-end.

## 9. Tính ngân sách tải và buffer

Một bài toán vận hành đơn giản:

- Nguồn phát trung bình **500 event/giây**.
- Handler chỉ xử lý được **200 event/giây**.
- Chênh lệch **300 event/giây** phải đi đâu đó: chờ ở nguồn, bị buffer, lưu bền hoặc bị loại bỏ.
- Nếu không kiểm soát, sau **10 giây** đã tồn khoảng **3.000 event** chưa xử lý, chưa tính burst và kích thước metadata/payload.

Backpressure có hiệu quả khi **nguồn có thể giảm phát** theo demand hoặc khi hệ thống có giới hạn/chiến lược rõ ràng tại biên với nguồn không thể giảm phát. Băng thông mạng chỉ là một phần: áp lực còn nằm ở CPU decode/encode, database connection pool, memory queue và số task blocking.

### Kích thước buffer cần cân nhắc

Ví dụ, nếu cần chịu burst ngắn 2 giây với chênh lệch tối đa 300 event/giây, buffer phải chứa ít nhất khoảng **600 event**, cộng biên an toàn. Nhưng lựa chọn 600 chỉ có ý nghĩa khi:

1. Có thể đo được burst/tốc độ xử lý ở tải mục tiêu.
2. Biết kích thước trung bình và tối đa của mỗi event.
3. Có thời gian tối đa chờ và chính sách khi buffer đầy.
4. Có giám sát queue length, memory, latency, dropped events.
5. Chấp nhận được hậu quả dữ liệu mất/trùng và có phương án replay nếu cần.

**Backpressure không thay thế capacity planning.** Khi nguồn liên tục nhanh hơn công suất xử lý trong thời gian dài, không buffer hữu hạn nào giải quyết tận gốc; phải giảm upstream, mở rộng consumer hoặc thay đổi kiến trúc.

## 10. Cancellation, timeout và resume liên quan thế nào?

Backpressure điều tiết việc **còn muốn nhận thêm**; cancellation biểu thị **không muốn nhận nữa**; timeout và resume giải quyết các tình huống khác.

| Cơ chế | Ý nghĩa | Không tự bảo đảm |
| --- | --- | --- |
| `REQUEST_N` | Cấp thêm nhu cầu cho stream | Message được lưu trong database |
| `CANCEL` | Yêu cầu kết thúc stream/tương tác | Rollback side effect đã thực hiện |
| `timeout(...)` | Không đợi quá hạn theo quy tắc Reactor | Producer sẽ không bao giờ tiếp tục tác vụ blocking |
| Reconnect | Mở transport/kết nối để có thể gửi request mới | Duy trì demand và subscription cũ |
| Resume | Cố phục hồi phiên RSocket còn state | Exactly-once nghiệp vụ |
| Checkpoint/idempotency | Lưu tiến độ và xử lý trùng ở tầng ứng dụng | Giao thức tự tạo event log bền vững |

Ví dụ client đang stream `inventory.events`, còn demand bằng không nhưng transport vẫn sống: stream có thể **đang tạm chờ demand**. Nếu client cancel, nguồn nên dọn resource. Nếu transport mất và resume thất bại, một subscription mới không thể tự biết sự kiện nào đã commit ở consumer; cần checkpoint/offset nghiệp vụ để replay an toàn.

### Luồng với tác động ghi dữ liệu

Nếu mỗi item cập nhật tồn kho hoặc tạo hóa đơn:

~~~text
RECEIVE event #103
  -> validate
  -> apply business change + store checkpoint atomically
  -> COMMIT
  -> allow/request next item
~~~

Đây là thứ tự logic mong muốn. Với stream được prefetch, **nhiều event có thể đã tới bộ nhớ trước khi commit**, nên không được đồng nhất `REQUEST_N` với xác nhận xử lý nghiệp vụ. Nếu sự kiện quan trọng và phải sống qua restart, cần một broker/event store bền vững cộng checkpoint và deduplication, không chỉ dựa vào RSocket flow control.

## 11. Kiểm thử demand đúng cách

### 11.1. Unit test Reactor với `StepVerifier`

Với Reactor Test (`reactor-test`), ta có thể bắt đầu subscription với demand **bằng 0**, rồi chủ động request:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> source = Flux.range(1, 3);

StepVerifier.create(source, 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(50))
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .verifyComplete();
~~~

Điểm quan trọng: `StepVerifier.create(source, 0)` đặt **initial demand của test subscriber** bằng 0; điều này hợp lệ, **khác** với gọi `Subscription.request(0)` là vi phạm Reactive Streams. Nếu code phát `onNext` khi test subscriber chưa cấp demand, test có thể phát hiện hành vi sai.

Unit test này chỉ xác nhận publisher tuân theo Reactive Streams. Nó **chưa xác nhận** quá trình chuyển demand thành `REQUEST_STREAM`/`REQUEST_N` qua network.

### 11.2. Integration test qua RSocket

Khi chạy responder thật (ví dụ `inventory.snapshot`) và `RSocketRequester`:

1. Tạo subscriber cấp demand từng phần nhỏ, chẳng hạn 1 rồi 2 rồi 5.
2. Quan sát số item thực nhận, thứ tự và tín hiệu complete/error.
3. Quan sát `doOnRequest` trên server; xác nhận không phát trước khi có demand phù hợp.
4. Cancel giữa stream; xác nhận callback cleanup và không tăng task/subscription còn tồn tại.
5. Thêm xử lý chậm tại subscriber; theo dõi throughput, CPU, queue, memory và thời gian chờ.
6. Thử nguồn hot/`Flux.interval` khi demand thấp để xem chính sách buffer/drop/error thực tế.
7. Nối nguồn qua Spring Integration gateway/`QueueChannel`; xác định có chỗ nào nhận nhanh hơn tốc độ xử lý, và đo backlog.

Các số `request(n)` trong unit test, các log `doOnRequest` và số frame `REQUEST_N` có thể khác nhau vì prefetch, batching và initial request. Kiểm thử nên dựa trên **ngữ nghĩa không phát vượt demand ở mỗi ranh giới**, cùng các giới hạn tài nguyên và hợp đồng nghiệp vụ.

### 11.3. Một ma trận kiểm thử tối thiểu

| Test | Kỳ vọng |
| --- | --- |
| Subscriber ban đầu chưa request | Nguồn hỗ trợ demand không gửi `onNext` vượt nhu cầu |
| Request theo lô 2 → 3 | Nhận tối đa theo nhu cầu được cấp tại biên kiểm tra |
| `take(3)` | Downstream complete; upstream bị cancel nếu còn hoạt động |
| Consumer chậm, nguồn cold | Producer điều chỉnh tốc độ, không tăng queue không giới hạn |
| Consumer chậm, nguồn hot | Kích hoạt chính sách giới hạn buffer/drop/error đã công bố |
| `flatMap(..., 8)` | Đo tối đa 8 xử lý in-flight tại operator tương ứng |
| Bridge sang gateway đồng bộ | Không chặn event loop và giới hạn số tác vụ |
| Nhiều client cùng subscribe | Không để một client chiếm toàn bộ tài nguyên |
| Mất kết nối giữa stream | Xử lý cancellation/reconnect/resume và checkpoint đúng |
| Event có side effect rồi retry | Dedup/idempotency tránh thực hiện nghiệp vụ trùng |

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Bộ nhớ tăng dù dùng `Flux` | Producer push nhanh, `collectList` hoặc buffer/queue không giới hạn | Kiểm tra từng ranh giới và giới hạn buffer/concurrency |
| `doOnRequest` log giá trị lớn | Subscriber mặc định request rất nhiều hoặc operator prefetch | Dùng `BaseSubscriber` để học, cấu hình pipeline đúng nhu cầu |
| Tưởng `request(0)` là “pause” | Hiểu sai Reactive Streams | Ngừng yêu cầu thêm, hoặc dùng cơ chế tạm dừng riêng |
| Stream có ít demand nhưng vẫn phát lỗi | Nguồn `Flux.interval`/push không chờ nhu cầu | Chọn nguồn demand-aware hoặc chính sách drop/buffer/error |
| RSocket có backpressure nhưng queue vẫn đầy | Bridge gửi vào channel trước khi downstream commit | Giới hạn capacity, flow control tại boundary, lưu bền khi cần |
| `flatMap` làm thứ tự cập nhật sai | Các xử lý song song hoàn thành khác thứ tự | `concatMap` hoặc partition theo key, bảo vệ transaction |
| Xử lý bị chậm toàn bộ khi dùng `concatMap` | Từng item xử lý tuần tự | Tăng concurrency có kiểm soát nếu nghiệp vụ cho phép |
| Cancel stream nhưng DB job vẫn chạy | Blocking/queue bên dưới đã nhận việc | Đặt timeout, lifecycle cleanup và cơ chế hủy job riêng |
| Bỏ mất event quan trọng khi drop/latest | Chọn chính sách dành cho telemetry | Chuyển sang event log bền vững và replay |
| Request-channel bị nghẽn hai chiều | Thiếu demand/overflow hoặc phụ thuộc vòng giữa hai phía | Phân tích riêng từng chiều và các buffer trung gian |

Khi điều tra lỗi, đi theo thứ tự **subscriber demand → Reactor operators → RSocket `REQUEST_N`/`PAYLOAD` → responder source → Spring Integration channel → downstream resource**. Gắn correlation ID và stream ID phù hợp vào quan sát, đồng thời tránh ghi payload nhạy cảm.

## 13. Bài tập thực hành

### Bài A — Quan sát `REQUEST_N`

Tạo server `inventory.snapshot` trả 100 event từ `Flux.range`. Client dùng `BaseSubscriber` cấp lần lượt 1, 2 và 5 item; đo số `onNext`. Nếu có công cụ quan sát frame RSocket, so sánh frame khởi đầu `REQUEST_STREAM` và các `REQUEST_N` bổ sung với log `doOnRequest`. Giải thích các chênh lệch do prefetch hoặc batching.

### Bài B — Lưu database với concurrency hữu hạn

Viết `StockEventStore.save(event)` trả `Mono<Void>`. So sánh `concatMap(..., 1)` với `flatMap(..., 8, 1)` về throughput và thứ tự commit. Với một SKU chỉ được cập nhật tuần tự, chứng minh vì sao phải áp dụng quy tắc ordering hoặc transaction.

### Bài C — Chuyển vào Spring Integration

Xây dựng flow qua `@MessageMapping` → `StockEnrichmentGateway` → `MessageChannel` → handler đồng bộ. Thử 5 client subscribe và yêu cầu liên tục. Đo số tác vụ đang xử lý, thời gian chờ và số hàng đợi; giải thích tại sao `boundedElastic` và giới hạn concurrency là hai quyết định riêng.

### Bài D — Nguồn push và chính sách quá tải

Giả lập nguồn 500 event/giây trong khi consumer chỉ xử lý 200 event/giây. Thử buffer hữu hạn, drop/latest, rồi lưu vào broker có replay. Ghi lại dữ liệu bị mất, độ trễ và bộ nhớ. Chọn phương án riêng cho dashboard nhiệt độ và dữ liệu thay đổi đơn hàng.

## 14. Ghi nhớ

- **Backpressure** là cách subscriber điều phối lượng phần tử mà publisher được phép phát; demand đi qua `Subscription.request(n)`.
- Với request-stream, RSocket mang **initial request N** trong `REQUEST_STREAM` và dùng `REQUEST_N` khi cần thêm. Với request-channel, mỗi chiều có demand riêng.
- `RSocketRequester.retrieveFlux(...)` và `@MessageMapping` có thể tạo pipeline reactive, nhưng phải kiểm tra prefetch, queue và ranh giới Spring Integration để biết demand có được tôn trọng từ đầu đến cuối.
- `Flux.range` là nguồn phù hợp để học demand; nguồn hot/push có thể cần buffer, drop hoặc một giao thức điều tiết ở upstream. Không có buffer hữu hạn nào hấp thụ được chênh lệch tải kéo dài vô hạn.
- `concatMap` giữ thứ tự; `flatMap` tăng concurrency có giới hạn; `publishOn`, `limitRate` và các `onBackpressure...` operator đều có tác động khác nhau đến yêu cầu và bộ nhớ.
- **CANCEL, timeout, reconnect/resume, idempotency và checkpoint** giải quyết các vấn đề khác với backpressure. Việc client yêu cầu thêm item không đồng nghĩa item trước đã commit nghiệp vụ.
- Khi dùng RSocket adapter/gateway với `MessageChannel`, hãy kiểm thử cả tín hiệu Reactive Streams **và** tốc độ thực sự của database, queue, poller, HTTP/JMS/Kafka adapter phía sau.

## Tài liệu tìm hiểu thêm

- [Reactive Streams Specification](https://www.reactive-streams.org/): hợp đồng `Publisher`, `Subscriber` và `Subscription`.
- [RSocket Protocol](https://rsocket.io/about/protocol/): các frame `REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_N`, `PAYLOAD` và `CANCEL`.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): backpressure, `BaseSubscriber`, `StepVerifier`, prefetch và operator.
- [Spring Framework RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, `@MessageMapping` và tương tác với Reactor.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): `MessageChannel`, `FluxMessageChannel`, gateway, poller và reactive streams support.
