# Timeout và cancellation trong RSocket Adapter

## 1. Bối cảnh: request chờ quá lâu và client không còn cần kết quả

Trong module **SPRING_INTEGRATION_ADAPTERS**, ứng dụng dùng inbound/outbound adapter, gateway, poller và `MessageChannel` để trao đổi message với hệ thống bên ngoài; cần kiểm soát cả hợp đồng request/reply, lỗi và vòng đời kết nối. Với chương **Adapter RSocket**, hai tình huống thường gặp là **timeout** khi một thao tác không trả kết quả đúng hạn và **cancellation** khi bên nhận chủ động dừng một tương tác còn hoạt động.

Ví dụ một ứng dụng điều hành kho gọi route `inventory.stock` để đọc số tồn. Nếu truy vấn cơ sở dữ liệu kéo dài 15 giây trong khi màn hình chỉ chờ 2 giây, client không nên đợi mãi. Trong một route khác, `inventory.events` trả về dòng sự kiện liên tục; khi người dùng đóng màn hình, client cần dừng stream để server không tiếp tục giữ tài nguyên.

~~~text
Request-response:
  Client ---- inventory.stock ----> Server -> IntegrationFlow -> DB
  Client -- hết 2 giây --X
  Server có thể vẫn đang chạy truy vấn DB.

Request-stream:
  Client ---- inventory.events ---> Server
  Client <--- event 101 ----------- Server
  Client <--- event 102 ----------- Server
  Client -- CANCEL ---------------> Server
  Server cần ngừng phát và giải phóng subscription/tài nguyên.
~~~

Sau bài này, bạn có thể:

- Phân biệt **timeout phía client**, **timeout ở server/IntegrationFlow**, **timeout do mất kết nối** và **giới hạn thời gian nghiệp vụ**.
- Giải thích cách `Mono.timeout(...)`, `Flux.timeout(...)` và cancel của Reactive Streams tác động đến RSocket.
- Biết khi nào RSocket có thể phát frame `CANCEL`, và những gì cancellation **không bảo đảm**.
- Thiết kế đường xử lý hủy an toàn khi đi qua `@MessageMapping`, `MessageChannel` và messaging gateway.
- Kiểm thử tình huống chậm, client ngừng chờ, hủy stream, tài nguyên bị rò rỉ và kết quả nghiệp vụ không rõ.

## 2. Phân biệt timeout, cancellation và lỗi kết nối

| Thuật ngữ | Ai khởi xướng? | Điều xảy ra | Cần lưu ý |
| --- | --- | --- | --- |
| **Request timeout** | Thường do caller đặt deadline | Publisher báo lỗi nếu không có tín hiệu đúng hạn | Có thể hủy subscription upstream |
| **Stream idle timeout** | Consumer hoặc producer | Không có phần tử tiếp theo trong một khoảng thời gian | Khác thời lượng tối đa của toàn stream |
| **Cancellation** | Subscriber không còn cần tín hiệu | Gửi yêu cầu hủy upstream | Không đồng nghĩa đã rollback side effect |
| **Connection timeout/keepalive failure** | Transport/RSocket | Peer bị xem là mất kết nối | Có thể làm nhiều stream cùng lỗi |
| **Business deadline** | Hợp đồng nghiệp vụ | Từ chối hoặc dừng tác vụ quá hạn | Cần kiểm soát ở nơi thực thi và lưu trạng thái |
| **Retry** | Chính sách phục hồi | Đăng ký/gửi lại thao tác sau lỗi | Có thể tạo request mới và lặp side effect |

**Timeout** thường kết thúc với `onError`, chẳng hạn `TimeoutException` ở Reactor. **Cancellation** là tín hiệu từ subscriber lên publisher; tự nó **không phải** `onError`. Khi client dùng `take(3)`, downstream có thể hoàn tất bình thường sau ba phần tử, trong khi upstream nhìn thấy tín hiệu cancel.

Giới hạn thời gian cần gắn với một ý nghĩa rõ ràng. “2 giây” là thời gian chờ **một response**, khoảng tối đa **giữa hai event**, hay toàn bộ thời gian dành cho **một giao dịch nghiệp vụ**? Những cách hiểu này đòi hỏi cách lập trình khác nhau.

## 3. RSocket truyền cancellation như thế nào?

RSocket là giao thức request-response, fire-and-forget, request-stream và request-channel, chạy trên transport như TCP hoặc WebSocket. Với các tương tác cần một luồng phản hồi, bên khởi tạo có thể không còn quan tâm đến kết quả trước khi tương tác hoàn tất.

Ở mức protocol, RSocket có frame **`CANCEL`** mang stream ID để yêu cầu peer kết thúc stream/tương tác liên quan. RSocket hỗ trợ cancellation cho các kiểu tương tác phù hợp như request-response, request-stream và request-channel; **fire-and-forget** vốn không có reply stream để caller tiếp tục chờ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket server
    participant F as IntegrationFlow
    C->>S: REQUEST_STREAM inventory.events
    S->>F: Subscribe/đọc dữ liệu
    S-->>C: PAYLOAD event 101
    S-->>C: PAYLOAD event 102
    Note over C: Người dùng đóng màn hình
    C->>S: CANCEL (streamId)
    Note over S,F: Hủy publisher nếu còn hoạt động
    S--xF: Cancel subscription/cleanup
~~~

Cần diễn giải đúng phạm vi của `CANCEL`:

1. Nó là **yêu cầu ngừng gửi/nhận thêm dữ liệu** của tương tác trên RSocket, có thể giải phóng tài nguyên còn hoạt động.
2. Một `CANCEL` có thể không được gửi nếu stream đã kết thúc, kết nối đã mất hoặc request chưa kịp đi ra wire. Hành vi quan sát phụ thuộc thời điểm xảy ra cancellation.
3. Frame `CANCEL` **không phải** lệnh rollback transaction, xóa message khỏi queue, hoặc hoàn tác REST/API call đã gửi tới hệ thống khác.
4. Server cần sử dụng API bất đồng bộ có hỗ trợ hủy hoặc cấu hình cleanup riêng nếu handler giữ resource bên ngoài.
5. Việc peer nhận `CANCEL` và đã dừng xử lý hay chưa có thể có độ trễ; không được suy luận chỉ từ thao tác đóng màn hình.

### Backpressure khác cancellation

Với request-stream/channel, RSocket dùng cơ chế yêu cầu số phần tử (**`REQUEST_N`**) để điều phối nhu cầu. Khi consumer chưa yêu cầu thêm, producer phải tuân thủ nhu cầu phát tương ứng. **Backpressure** điều tiết tốc độ; **cancellation** yêu cầu dừng hẳn subscription.

| Tín hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `REQUEST_N(5)` | Consumer có nhu cầu thêm 5 phần tử | Xem tiếp một trang sự kiện |
| Không yêu cầu thêm | Có thể đang tạm chờ/đang xử lý | Tạm ngừng tăng nhu cầu |
| `CANCEL` | Consumer không cần stream đó nữa | Rời khỏi màn hình dashboard |
| `ERROR` | Tương tác kết thúc lỗi | Decoder hoặc handler ném lỗi |
| `COMPLETE` hoặc tín hiệu kết thúc phù hợp | Tương tác hoàn tất | Trả hết kết quả hữu hạn |

Không xây hệ thống dựa trên giả định “không có `REQUEST_N` nghĩa là stream sẽ tự bị hủy”. Một stream chưa bị cancel có thể tiếp tục giữ state/tài nguyên.

## 4. Timeout ở Reactor: Mono và Flux có nghĩa khác nhau

### 4.1. `Mono.timeout` cho request-response

Ví dụ caller chỉ cho phép đợi tối đa hai giây:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

record StockQuery(String sku) {}
record StockReply(String sku, int available) {}

class StockClient {
    private final RSocketRequester requester;

    StockClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<StockReply> getStock(String sku) {
        return requester.route("inventory.stock")
            .data(new StockQuery(sku))
            .retrieveMono(StockReply.class)
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

`timeout` tính từ lúc **subscribe** vào publisher, không phải từ lúc tạo biến `Mono`. Nếu quá thời hạn mà chưa có tín hiệu kết quả phù hợp, Reactor phát lỗi `TimeoutException` và hủy subscription upstream. Khi request-response RSocket đang thực sự chạy và kết nối còn hoạt động, cancellation có thể được truyền thành `CANCEL` tới server.

Điều cần nhớ: **client báo timeout không chứng minh server chưa thực hiện gì**. Nếu server đã commit cập nhật tồn kho hoặc đã đẩy event sang Kafka, kết quả đó có thể vẫn tồn tại sau khi client ngừng chờ.

### 4.2. `Flux.timeout` thường là timeout giữa các phần tử

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<InventoryEvent> events = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .timeout(Duration.ofSeconds(5));
~~~

Với overload `Flux.timeout(Duration)`, timer áp dụng khi chưa nhận được phần tử đầu tiên và được **đặt lại cho khoảng chờ đến mỗi phần tử tiếp theo**. Dòng sự kiện chạy hàng giờ vẫn hợp lệ nếu cứ ít hơn 5 giây lại có một phần tử.

Đừng dùng `Flux.timeout(Duration.ofSeconds(5))` rồi diễn giải thành “stream phải kết thúc sau 5 giây”. Nếu mục tiêu là **giới hạn tổng thời gian được phép xem stream**, có thể dùng `take(Duration)`:

~~~java
Flux<InventoryEvent> tenSecondPreview = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .take(Duration.ofSeconds(10));
~~~

`take(Duration)` ngừng nhận sau khoảng thời gian đó và thường **hoàn tất downstream**, thay vì phát `TimeoutException`. Nó sẽ cancel upstream nếu nguồn chưa kết thúc. Chọn `timeout` nếu **thiếu dữ liệu đúng hạn là lỗi**, chọn `take` nếu **hết thời gian xem là một kết thúc bình thường**.

### 4.3. `take(n)` và hủy chủ động

~~~java
Flux<InventoryEvent> firstThree = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .take(3);
~~~

Sau ba phần tử, downstream phát complete, còn upstream nhận cancel. Vì client không còn đợi, server nên giải phóng subscription nguồn. Đối với ứng dụng web hoặc mobile, việc hủy `Disposable` do `subscribe()` trả về thường được nối với vòng đời màn hình/component:

~~~java
Disposable subscription = requester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class)
    .subscribe(
        event -> render(event),
        error -> showError(error)
    );

// Khi màn hình bị đóng:
subscription.dispose();
~~~

`render(...)` và `showError(...)` là callback giả định ở lớp giao diện. Trong WebFlux hoặc một phương thức handler reactive, thông thường nên **trả lại `Flux`/`Mono` cho framework quản lý subscription**, thay vì tự gọi `subscribe()` trong tầng service rồi mất quyền điều phối cancel.

## 5. Ví dụ server: quan sát cancellation và cleanup

Đoạn dưới minh họa endpoint request-stream chạy trên Spring Boot 3 / Spring Framework 6. Nguồn `Flux.interval` có thể dừng khi subscription bị hủy. Đặt `doFinally` giúp phân biệt các kiểu kết thúc:

~~~java
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

record InventorySubscription(String warehouseId) {}
record InventoryEvent(String warehouseId, long sequence) {}

@Controller
class InventoryRSocketController {
    private static final Logger log =
        LoggerFactory.getLogger(InventoryRSocketController.class);

    @MessageMapping("inventory.events")
    Flux<InventoryEvent> events(@Payload InventorySubscription request) {
        return Flux.interval(Duration.ofMillis(250))
            .map(index -> new InventoryEvent(
                request.warehouseId(),
                index + 1
            ))
            .doOnCancel(() -> log.info(
                "RSocket consumer cancelled warehouse={}",
                request.warehouseId()
            ))
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    log.info("Source cleaned after cancel");
                } else {
                    log.info("Source terminated with {}", signal);
                }
            });
    }
}
~~~

Khi client dùng `take(3)` hoặc hủy subscription, nguồn reactive của endpoint nhận cancel, và `Flux.interval` ngừng lịch phát phần tử theo cơ chế của Reactor. `doFinally` được gọi cả khi complete, error và cancel, vì vậy hợp với việc **giải phóng tài nguyên** dùng chung cho mọi tình huống kết thúc.

Nếu nguồn thực sự là kết nối đến service bên ngoài, cần móc cleanup vào lifecycle của subscription. Ví dụ giả mã:

~~~java
Flux<InventoryEvent> fromExternalFeed(String warehouseId) {
    return Flux.create(sink -> {
        ExternalSubscription handle = externalFeed.subscribe(
            warehouseId,
            sink::next,
            sink::error
        );

        sink.onDispose(handle::close);
    });
}
~~~

Trong ví dụ này, `externalFeed` và `ExternalSubscription` là API **minh họa**, không phải class có sẵn của Spring. `onDispose` đảm bảo yêu cầu đóng tài nguyên khi sink complete/error/cancel. Một hệ thống thật còn phải xử lý backpressure, race condition giữa phát event và đóng handle, cũng như khả năng lỗi lúc hủy nguồn.

### Cancellation thường có thể quan sát ở cả hai đầu

- **Client:** `doOnCancel` hoặc `doFinally(SignalType.CANCEL)` được kích hoạt khi hủy subscription local.
- **Server:** publisher vẫn sống nhận cancel từ tầng RSocket, các callback cleanup chạy khi tín hiệu đi tới đúng subscription.
- **Hệ thống bên ngoài:** chỉ biết về cancel nếu server **có cách chuyển ý định hủy** tới HTTP client, subscription Kafka, truy vấn DB hoặc job tương ứng.

Không suy ra server đã rollback hay dừng một truy vấn DB chỉ vì phía client ghi log “cancelled”.

## 6. Timeout phía server và timeout phía client cần phối hợp

Timeout của client bảo vệ **thời gian chờ của caller**. Timeout phía server bảo vệ **tài nguyên server**. Đặt cả hai theo hợp đồng và thứ tự thời gian hợp lý:

~~~mermaid
flowchart LR
    C["Client: timeout 2s"] --> R["RSocket handler"]
    R --> I["Spring Integration gateway"]
    I --> S["Service / DB"]
    S --> I
    I --> R
    R --> C
~~~

Nếu server mất 4 giây để xử lý còn client chỉ chờ 2 giây, client có thể hủy subscription sau giây thứ 2; server vẫn có thể đang xử lý. Để kiểm soát **giới hạn thực thi**, phải đặt timeout sát tài nguyên xử lý như timeout truy vấn DB, timeout HTTP client, hoặc deadline của job.

### Timeout phía responder

~~~java
import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class StockRSocketController {
    private final StockQueryService queryService;

    StockRSocketController(StockQueryService queryService) {
        this.queryService = queryService;
    }

    @MessageMapping("inventory.stock")
    Mono<StockReply> stock(@Payload StockQuery query) {
        return queryService.findStock(query.sku())
            .timeout(Duration.ofSeconds(4));
    }
}

// Service reactive; ví dụ nội bộ sẽ gọi DB/HTTP client non-blocking.
interface StockQueryService {
    Mono<StockReply> findStock(String sku);
}
~~~

Đối với nguồn thật sự reactive, cancel có thể lan truyền đến trình điều khiển dữ liệu hoặc HTTP client, tùy implementation. Tuy nhiên một giao dịch hay thao tác đã commit không thể “được thu hồi” chỉ bằng cancel; cần quy tắc ứng dụng rõ ràng.

## 7. Biên Spring Integration: điểm nào nhận được cancellation?

Luồng tích hợp thường có dạng:

~~~mermaid
flowchart LR
    A["RSocketRequester"] --> B["@MessageMapping / inbound gateway"]
    B --> C["MessageChannel"]
    C --> D["IntegrationFlow"]
    D --> E["Service / DB / external adapter"]
    E --> D
    D --> B
    B --> A
~~~

Khi `@MessageMapping` trả về `Mono` hoặc `Flux`, Spring có thể giữ chuỗi publisher và lan truyền tín hiệu hủy nếu các thành phần bên trong tuân theo Reactive Streams. Nhưng nếu request đã chuyển sang **messaging gateway đồng bộ** hoặc được đẩy vào một queue/job, cancellation của caller không tự thu hồi message đã gửi và không chắc dừng handler đang chạy.

### 7.1. Ví dụ bridge sang IntegrationFlow đồng bộ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

record StockQuery(String sku) {}
record StockReply(String sku, int available) {}

@MessagingGateway
interface StockGateway {
    @Gateway(requestChannel = "stockLookupInput")
    StockReply lookup(StockQuery query);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class StockFlowConfiguration {
    private final StockRepository repository;

    StockFlowConfiguration(StockRepository repository) {
        this.repository = repository;
    }

    @Bean
    IntegrationFlow stockFlow() {
        return IntegrationFlow.from("stockLookupInput")
            .handle(StockQuery.class, (query, headers) ->
                new StockReply(
                    query.sku(),
                    repository.findAvailable(query.sku())
                )
            )
            .get();
    }
}

interface StockRepository {
    int findAvailable(String sku);
}
~~~

Responder có thể bảo vệ RSocket event loop bằng scheduler:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import java.time.Duration;

@Controller
class StockGatewayResponder {
    private final StockGateway gateway;

    StockGatewayResponder(StockGateway gateway) {
        this.gateway = gateway;
    }

    @MessageMapping("inventory.stock")
    Mono<StockReply> read(@Payload StockQuery query) {
        return Mono.fromCallable(() -> gateway.lookup(query))
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(4));
    }
}
~~~

Các class ở phần này là **một ví dụ thay thế** cho responder/service reactive ở phần trước, không khai báo đồng thời hai `@MessageMapping("inventory.stock")` trong cùng ứng dụng. Tác vụ đồng bộ được chuyển khỏi event loop bằng `boundedElastic()`. Tuy vậy, nếu client cancel trong lúc `repository.findAvailable(...)` đang chờ JDBC, lời gọi có thể vẫn chạy; Reactor không bảo đảm dừng ngay mọi tác vụ blocking hoặc rollback transaction.

Với tài nguyên đồng bộ, cần phối hợp:

1. Timeout của **query/driver** hoặc API gọi ngoài, ví dụ giới hạn thời gian truy vấn phù hợp.
2. Timeout request/reply của **messaging gateway** nếu nó có thể đợi reply từ channel bất đồng bộ.
3. Thời gian chờ ở **RSocket caller/responder** để bảo vệ trải nghiệm và tài nguyên.
4. Cơ chế **idempotency, trạng thái tác vụ và giải phóng tài nguyên** khi việc xử lý đã bắt đầu.

Đặt `Mono.timeout` trên đầu chuỗi không thay thế ba mục còn lại.

### 7.2. Khi flow dùng queue hoặc poller

Ví dụ một inbound request được chuyển vào queue, sau đó poller mới lấy message:

~~~text
RSocket request
   -> send message vào queue channel
   -> poller xử lý sau 5 giây

Client timeout sau 2 giây
   -> không còn cần reply
   -> message có thể vẫn nằm trong queue / đã được poller lấy
~~~

Nếu tác vụ vẫn phải xử lý sau khi client đóng kết nối (ví dụ tạo báo cáo), nên thiết kế API theo kiểu **submit job → trả job ID → tra cứu trạng thái/cancel job có kiểm soát**. Nếu phải dừng thật sự, định nghĩa trạng thái `CANCEL_REQUESTED` và cho worker kiểm tra các điểm dừng an toàn; đừng dùng tín hiệu `CANCEL` của RSocket làm nguồn sự thật duy nhất.

## 8. Deadline và ngân sách thời gian xuyên nhiều adapter

Một request có thể đi theo chuỗi:

~~~text
RSocket inbound
  -> Spring Integration channel
  -> HTTP outbound gateway
  -> remote service
  -> database
  -> reply
~~~

Nếu mỗi tầng đều đặt 5 giây độc lập và caller chỉ chịu đợi 3 giây, server có thể tiếp tục dùng tài nguyên rất lâu sau khi caller đã rời đi. Nên phân biệt:

- **Client timeout:** khi nào caller ngừng chờ.
- **Overall deadline:** hạn cuối thực hiện nghiệp vụ theo hợp đồng.
- **Per-hop timeout:** thời gian cho HTTP, DB, JMS reply hoặc một adapter riêng.
- **Cancellation policy:** khi nào có thể bỏ việc; khi nào phải hoàn tất và lưu trạng thái để caller tra cứu.

Với nhiều dịch vụ, có thể truyền deadline hoặc remaining budget qua header đã xác thực, sau đó mỗi tầng tính lại thời gian còn lại theo đồng hồ của chính nó. Ví dụ:

~~~text
Deadline logic của request: tối đa 3000 ms
  RSocket + decode + routing: đã tiêu 100 ms
  Gateway/HTTP request: được cấp ngân sách phù hợp
  DB: có timeout riêng, không chờ quá deadline
  Reply: chừa thời gian mã hóa và gửi trả
~~~

Đây là **mẫu thiết kế**, không có header chuẩn bắt buộc tên `deadline` trong RSocket/Spring Integration. Nếu nhận deadline dạng timestamp từ client, phải tính đến sai lệch đồng hồ và giới hạn giá trị client được phép yêu cầu. Với nghiệp vụ quan trọng, deadline phía server cần được tính bằng thời gian đáng tin cậy do server quản lý và không cho phép client tự gia hạn vô hạn.

### Gợi ý lựa chọn timeout

| Tình huống | Điều cần đặt | Hành vi hợp lý |
| --- | --- | --- |
| Tra cứu tồn kho tương tác | Client 2–3 giây; server/service giới hạn riêng | Báo timeout và cho phép tra cứu lại |
| Stream sự kiện dài hạn | Idle timeout phù hợp hoặc heartbeat ở tầng ứng dụng | Không đặt một total timeout ngắn làm stream tự kết thúc ngoài ý muốn |
| Tạo đơn hàng | Deadline + idempotency key | Sau timeout tra cứu trạng thái trước khi retry |
| Job tạo báo cáo nhiều phút | Trả job ID và theo dõi trạng thái | Hủy job bằng API nghiệp vụ có kiểm soát |
| RSocket transport chập chờn | KEEPALIVE / reconnect / resume | Phục hồi kết nối, xử lý riêng timeout nghiệp vụ |

Những khoảng thời gian trong ví dụ chỉ mang tính minh họa; đo latency thực tế, tải hệ thống và yêu cầu SLA trước khi cấu hình production.

## 9. Timeout có tự động gửi CANCEL không?

Hình dung request-response `inventory.stock`:

~~~mermaid
sequenceDiagram
    participant C as Client Reactor
    participant R as RSocket responder
    participant G as IntegrationFlow/DB
    C->>R: REQUEST_RESPONSE inventory.stock
    R->>G: lookup sku
    Note over C: Mono.timeout(2s) hết hạn
    C--xR: CANCEL nếu stream còn hoạt động
    C-->>C: onError(TimeoutException)
    Note over G: Truy vấn đồng bộ có thể còn chạy
    G-->>R: Kết quả trả muộn
    Note over R: Không còn caller chờ reply
~~~

Khi subscription upstream còn gắn với request RSocket và transport hoạt động, cancel từ Reactor thường được chuyển xuống RSocket để gửi `CANCEL`. Nhưng đây là **hành vi cần kiểm thử trong cấu hình thật**, không nên coi đó là xác nhận chắc chắn rằng server đã dừng công việc.

Đặc biệt:

- Nếu client tự `subscribe()` và **không hủy Disposable**, request có thể tiếp tục dù màn hình đóng.
- Nếu handler server tự `subscribe()` vào một publisher khác mà không quản lý lifecycle, công việc phụ đó có thể tiếp tục sau cancel.
- Nếu message đã được gửi đến `QueueChannel`, JMS/Kafka hoặc một executor, hủy subscription của request không tự xóa công việc đã xếp hàng.
- Nếu server đã hoàn thành xử lý và chỉ mất reply, cancel không thể hoàn tác xử lý.
- Nếu transport đã mất, tín hiệu hủy có thể không đến peer; cần timeout/cleanup độc lập phía server.

## 10. Lỗi timeout và chính sách retry

Timeout thường đi kèm câu hỏi: “Có nên gửi lại không?”. Câu trả lời phụ thuộc **tính chất thao tác**, vì timeout không cho biết server đã xử lý đến đâu.

| Thao tác | Sau timeout | Cách xử lý |
| --- | --- | --- |
| `inventory.stock` chỉ đọc | Có thể thử lại khi lỗi tạm thời | Backoff, giới hạn retry, timeout tổng |
| `orders.submit` tạo đơn | Kết quả có thể đã commit | Giữ idempotency key, tra cứu trạng thái rồi mới thử lại |
| `payment.capture` | Side effect khó hoàn tác | Không tự retry vô điều kiện; dùng token/idempotency và tra cứu giao dịch |
| `inventory.events` stream | Retry tạo subscription **mới** | Dùng checkpoint/replay/dedup nếu không được mất event |
| `report.cancel` | Dừng job là nghiệp vụ riêng | Xác nhận trạng thái job, tránh nhầm với RSocket `CANCEL` |

### Retry chỉ cho route đọc

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<StockReply> lookupWithRetry(String sku) {
    return Mono.defer(() -> requester
            .route("inventory.stock")
            .data(new StockQuery(sku))
            .retrieveMono(StockReply.class)
            .timeout(Duration.ofSeconds(2)))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(300))
                .filter(error -> error instanceof TimeoutException)
        );
}
~~~

Đây là chính sách **minh họa** cho truy vấn không có side effect. Trong production:

- Phân loại thêm các lỗi transport phù hợp và loại trừ lỗi validation/authentication.
- Cân nhắc **deadline tổng**: ba lần thử mỗi lần 2 giây có thể kéo dài hơn mức chờ người dùng chấp nhận.
- Tránh retry vô hạn hoặc số lượng client retry đồng loạt; sử dụng backoff và jitter.
- Không áp dụng lại đoạn code cho lệnh ghi khi chưa có idempotency/khả năng tra cứu kết quả.

## 11. Quan sát và kiểm thử timeout/cancellation

Một bộ kiểm thử có ý nghĩa phải đi qua responder RSocket thật hoặc môi trường mô phỏng cùng lifecycle subscription. Chỉ gọi trực tiếp Java method của `@MessageMapping` không kiểm thử được đường truyền `CANCEL`.

### Ma trận test

| Trường hợp | Cách tạo | Điều cần xác nhận |
| --- | --- | --- |
| Request trả nhanh | Server trả trước timeout client | Client nhận `onNext` và `onComplete` bình thường |
| Server chậm hơn client timeout | Giữ handler lâu hơn ngưỡng | Client nhận lỗi timeout; phía server đo được tình trạng xử lý |
| Stream bị cancel sau ba event | Client gọi `take(3)` | Downstream complete; server dừng subscription và cleanup |
| Stream không có event đủ lâu | `Flux.timeout(Duration)` | Client báo lỗi khoảng chờ giữa event; upstream bị hủy |
| Stream bị giới hạn tổng thời gian | `take(Duration)` | Client kết thúc bình thường và không leak subscription |
| Nhiều stream cùng một kết nối | Hủy một stream | Stream khác tiếp tục bình thường |
| Client mất mạng trước khi gửi CANCEL | Ngắt transport | Server cleanup theo phát hiện connection/timeout, không phụ thuộc duy nhất vào CANCEL |
| DB blocking đang chạy khi client cancel | Driver được cấu hình chậm | Không khẳng định đã rollback; quan sát query/job và resource |
| Request ghi commit xong nhưng reply mất | Chèn fault sau commit | Retry cùng request ID không tạo bản ghi trùng |
| Retry stream không có checkpoint | Làm gián đoạn rồi subscribe lại | Phát hiện nguy cơ nhận trùng/mất event, thiết kế cơ chế replay |

### Ghi log/metrics

Tùy nơi triển khai, nên quan sát các thông số:

- Số request timeout theo **route**, thời gian xử lý thực tế và mức timeout áp dụng.
- Số lần cancel, complete, error của các publisher và số subscription còn hoạt động.
- Dung lượng queue/`MessageStore`, thời gian chờ poller, số công việc chạy sau khi caller rời đi.
- Độ trễ DB/HTTP/JMS, tỷ lệ lỗi timeout từng adapter và số lần retry.
- Correlation ID, request ID, idempotency key và trạng thái xử lý sau timeout.

Không log token, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm chỉ để chẩn đoán timeout. Một log “caller timed out” nên được ghép với log “server completed/failed” bằng correlation ID; hai sự kiện có thể xảy ra ở thời điểm khác nhau.

## 12. Troubleshooting

| Dấu hiệu | Nguyên nhân có thể | Hướng khoanh vùng |
| --- | --- | --- |
| Client hết 2 giây nhưng server vẫn ghi DB | Cancellation không rollback blocking/transaction | Kiểm tra timeout DB, idempotency và transaction |
| Stream còn chạy sau khi đóng màn hình | Không dispose subscription, hoặc có `subscribe()` tách rời ở server | Nối lifecycle với `Disposable` và cleanup upstream |
| `Flux.timeout` lỗi khi không có event trong 5 giây | Timeout giữa các phần tử bị nhầm với toàn stream | Dùng heartbeat/tăng idle timeout hoặc dùng `take(Duration)` cho giới hạn tổng |
| Một stream bị hủy kéo theo tất cả stream khác | Lỗi connection thay vì chỉ stream, hoặc code chia sẻ resource không đúng | Phân biệt frame CANCEL với transport error và lifecycle resource |
| Retry tạo đơn trùng | Timeout bị coi là chắc chắn chưa xử lý | Sử dụng request ID duy nhất cho một ý định nghiệp vụ |
| Message trong queue vẫn xử lý sau cancel | Channel/poller đã nhận message | Thiết kế state machine và job cancellation riêng |
| Timeout quá ngắn gây lỗi nhiều lúc tải cao | Không đo latency, thiếu budget cho downstream | Đo p95/p99, tune timeout/hạn chế tải |
| Chờ rất lâu dù client đã timeout | HTTP/DB/JMS outbound không có deadline/timeout | Đặt timeout riêng cho downstream adapter/client |
| Không thấy `CANCEL` trong log server | Request đã xong, transport mất hoặc frame chưa gửi | Quan sát subscription, RSocket frames và thời điểm cancel |
| Dùng `onErrorResume` rồi tưởng request hoàn tất | Fallback che lỗi upstream nhưng công việc phụ có thể còn chạy | Kiểm tra lifecycle resource và ý nghĩa kết quả fallback |

Để chẩn đoán, kiểm tra theo thứ tự: **request deadline → Reactor signal (complete/error/cancel) → RSocket stream/transport → Spring Messaging handler → `MessageChannel` → IntegrationFlow → downstream timeout/transaction**. Mỗi tầng cần log và metric phù hợp.

## 13. Bài tập thực hành

### Bài A — Request-response timeout

Tạo route `inventory.stock` trả dữ liệu sau một khoảng delay chủ động. Client đặt `Mono.timeout(Duration.ofSeconds(2))`. Thử server trả sau 1 giây và sau 4 giây; giải thích vì sao một lần thành công và một lần timeout. Ghi nhận server có thực sự ngừng công việc sau client timeout không.

### Bài B — Cancel stream và giải phóng tài nguyên

Tạo route `inventory.events` phát event mỗi 250 ms. Client dùng `take(3)`. Ở server dùng `doFinally` và một nguồn giả lập có cơ chế `close()` để kiểm tra cleanup chỉ được thực hiện một lần. Sau đó thử hủy bằng `Disposable.dispose()` trước event đầu tiên.

### Bài C — Timeout xuyên IntegrationFlow

Thiết kế request đi qua `@MessageMapping` → messaging gateway → `MessageChannel` → service chậm. Đặt timeout RSocket client, timeout gateway khi chờ reply và timeout ở service/DB. Với mỗi timeout, ghi rõ điều gì hết hạn, tín hiệu nào được phát và liệu nghiệp vụ có thể còn chạy.

### Bài D — Không retry side effect vô điều kiện

Mô phỏng route `orders.submit` đã ghi DB xong nhưng reply bị mất. Thêm `requestId` và một unique constraint ở database. Retry cùng `requestId` và xác minh chỉ tạo một đơn. Phân biệt hủy subscription với hủy giao dịch nghiệp vụ.

## 14. Những điều cần nhớ

- **Timeout** đặt giới hạn thời gian chờ; **cancellation** báo không còn nhu cầu tiếp tục subscription. RSocket có frame `CANCEL` để yêu cầu kết thúc một stream đang hoạt động.
- `Mono.timeout` phù hợp cho request-response; `Flux.timeout(Duration)` thường kiểm soát khoảng chờ **giữa** các event. `take(Duration)` và `take(n)` là cách hoàn tất phía client và cancel upstream khi đủ điều kiện.
- RSocket cancellation có thể được truyền qua publisher reactive, nhưng **không tự rollback database, không tự hủy queue/job và không bảo đảm chặn tác vụ blocking**.
- Với Spring Integration, phân biệt timeout của request, gateway reply, downstream adapter và deadline toàn nghiệp vụ; đặt giới hạn phù hợp ở từng nơi.
- Timeout không xác định được side effect đã commit chưa. **Retry lệnh ghi cần idempotency và cơ chế tra cứu trạng thái**.
- Kiểm thử phải quan sát cả **tín hiệu Reactor**, **subscription server**, **tài nguyên ngoài** và **trạng thái nghiệp vụ** sau khi caller timeout/cancel.
