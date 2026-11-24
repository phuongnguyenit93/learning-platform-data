# Luồng hữu hạn, luồng liên tục và điều kiện hoàn thành

Trong RSocket, request-stream cho phép requester gửi một request ban đầu và nhận về một chuỗi response. Chuỗi này có thể hữu hạn, chẳng hạn danh sách giao dịch trong một khoảng thời gian, hoặc liên tục, chẳng hạn giá thị trường và trạng thái thiết bị realtime. Điểm quan trọng khi thiết kế request-stream là xác định rõ **khi nào luồng kết thúc**, ai có quyền dừng luồng và cách hệ thống xử lý khi không còn dữ liệu.

Trong Java, Reactor biểu diễn chuỗi response bằng **Flux<T>**. Một Flux có thể phát không, một hoặc nhiều phần tử; nó có thể hoàn tất bình thường, kết thúc bằng lỗi hoặc tiếp tục cho đến khi bị hủy. Spring RSocket ánh xạ mô hình này qua @MessageMapping ở phía responder và retrieveFlux ở phía requester. Bài học này đặt các điều kiện hoàn thành trong bối cảnh RSocket, điều tiết luồng và vận hành realtime.

Sau bài học, bạn có thể:

- Phân biệt luồng hữu hạn, luồng liên tục, luồng rỗng và publisher không phát tín hiệu.
- Giải thích các tín hiệu onNext, onComplete và onError trong vòng đời Flux.
- Xác định điều kiện hoàn tất cho request-stream.
- Triển khai request-stream bằng Spring Boot và RSocketRequester.
- Hiểu cách demand/backpressure và CANCEL ảnh hưởng đến luồng.
- Thiết kế timeout, giới hạn số phần tử, cleanup và kiểm thử cho cả luồng hữu hạn lẫn liên tục.

## 1. Request-stream trả về một chuỗi response

Requester gửi một request payload để bắt đầu interaction. Responder trả về không hoặc nhiều response payload theo cùng một stream ID. Khác với request-response, responder không cần kết thúc ngay sau response đầu tiên.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: REQUEST_STREAM (request + initial requestN)
    Note over S: Tạo publisher response
    loop Mỗi phần tử được yêu cầu
        S-->>C: PAYLOAD (NEXT)
        C->>S: REQUEST_N (khi cần thêm demand)
    end
    alt Nguồn hoàn tất tự nhiên
        S-->>C: PAYLOAD (COMPLETE)
    else Nguồn gặp lỗi
        S-->>C: ERROR
    else Client không còn cần dữ liệu
        C--xS: CANCEL
    end
~~~

Một request-stream có các đặc điểm:

- Một request ban đầu mở interaction.
- Responder phát nhiều response payload theo thời gian.
- Mỗi response được gắn với stream ID của interaction.
- Interaction kết thúc khi responder hoàn tất, responder phát lỗi, requester hủy hoặc kết nối không còn khả dụng.

Trong Reactor, kiểu trả về thường là Flux<T>. Flux biểu diễn số lượng phần tử từ 0 đến N, không giới hạn trước số lượng phần tử tối đa.

## 2. Bốn trạng thái cần phân biệt

Không phải mọi Flux đều có cùng cách kết thúc. Hãy phân biệt luồng hữu hạn, luồng liên tục, luồng rỗng và publisher không phát tín hiệu.

| Trạng thái | Giá trị được phát | Kết thúc bình thường? | Ví dụ |
|---|---:|---|---|
| Luồng hữu hạn | 0..N phần tử | Có, khi nguồn phát hết dữ liệu | Danh sách đơn hàng |
| Luồng liên tục | Có thể phát vô hạn | Không tự hoàn tất nếu nguồn vẫn hoạt động | Giá realtime |
| Luồng rỗng | Không có phần tử | Có, hoàn tất ngay | Không có sự kiện phù hợp |
| Publisher không phát tín hiệu | Không có phần tử | Không tự hoàn tất hoặc báo lỗi | Chờ một sự kiện chưa đến |

Ví dụ:

~~~java
Flux<Integer> finite = Flux.range(1, 5);

Flux<String> empty = Flux.empty();

Flux<Long> continuous = Flux.interval(Duration.ofSeconds(1));

Flux<String> pending = Flux.never();
~~~

**finite** phát các số từ 1 đến 5 rồi gọi onComplete. **empty** không phát onNext nhưng gọi onComplete ngay. **continuous** phát số tăng dần theo chu kỳ và tiếp tục cho đến khi bị hủy hoặc gặp lỗi. **pending** không phát onNext, onComplete hay onError.

Luồng rỗng và publisher không phát tín hiệu có vẻ giống nhau vì cả hai đều chưa phát giá trị, nhưng vòng đời khác nhau hoàn toàn: luồng rỗng đã hoàn tất; publisher không phát tín hiệu vẫn đang chờ.

## 3. Vòng đời của Flux và tín hiệu kết thúc

Một publisher Reactive Streams có thể phát các tín hiệu sau khi subscriber đăng ký:

1. onSubscribe: tạo subscription và cung cấp quyền yêu cầu dữ liệu.
2. onNext: phát một phần tử.
3. onComplete: kết thúc bình thường.
4. onError: kết thúc do lỗi.

onComplete và onError là các tín hiệu terminal. Một publisher chỉ được kết thúc bằng một trong hai tín hiệu này; sau đó không phát thêm onNext. Publisher cũng có thể hoàn tất mà không phát phần tử nào.

~~~mermaid
stateDiagram-v2
    [*] --> Active: subscribe
    Active --> Active: onNext
    Active --> Completed: onComplete
    Active --> Failed: onError
    Active --> Cancelled: cancel
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

**Cancel không phải onComplete.** Cancel là hành động của subscriber yêu cầu dừng việc phát dữ liệu. Publisher được thông báo hủy và nên giải phóng tài nguyên, nhưng không phát một tín hiệu onComplete ngược trở lại subscriber đã hủy.

Với request-stream, cần phân biệt:

- Server hoàn tất tự nhiên: responder gửi tín hiệu kết thúc cho requester.
- Server gặp lỗi: responder kết thúc interaction bằng ERROR.
- Client hủy: requester gửi CANCEL; server nhận tín hiệu hủy để dừng công việc.
- Kết nối đóng: interaction có thể kết thúc do lỗi kết nối; đây không phải hoàn tất nghiệp vụ bình thường.

## 4. Thiết kế luồng hữu hạn

Luồng hữu hạn phù hợp khi nguồn dữ liệu có điểm kết thúc xác định. Ví dụ:

- Lấy các giao dịch trong một khoảng thời gian.
- Trả về các thay đổi đã xảy ra từ một mốc thời gian đến hiện tại.
- Gửi danh sách cảnh báo đang chờ xử lý.
- Trả về kết quả tính toán theo từng phần rồi hoàn tất.

Các nguồn hữu hạn thường được tạo từ collection, truy vấn database hoặc một phép biến đổi kết thúc khi nguồn đầu vào kết thúc:

~~~java
Flux<OrderEvent> recentEvents(String customerId) {
    return orderEventRepository
        .findByCustomerIdOrderByCreatedAt(customerId);
}
~~~

Nếu repository phát hết các bản ghi phù hợp rồi hoàn tất, request-stream cũng kết thúc. Không cần tự gửi một thông điệp "đã xong" nếu giao thức và client đã nhận được tín hiệu hoàn tất của stream.

Có thể giới hạn một nguồn lớn thành một luồng hữu hạn:

~~~java
Flux<OrderEvent> latestEvents(String customerId) {
    return orderEventRepository
        .findByCustomerIdOrderByCreatedAt(customerId)
        .take(100);
}
~~~

take(100) chỉ cho downstream tối đa 100 phần tử. Khi đạt giới hạn, Flux phía requester hoàn tất và cancellation được truyền ngược upstream để dừng việc đọc thêm nếu nguồn hỗ trợ hủy.

### Kết hợp nhiều nguồn hữu hạn

Nếu một request cần ghép các nguồn dữ liệu, hãy chọn toán tử phù hợp với điều kiện kết thúc:

~~~java
Flux<AuditEvent> auditTrail(String aggregateId) {
    return Flux.concat(
        auditRepository.findCreatedEvents(aggregateId),
        auditRepository.findUpdatedEvents(aggregateId)
    );
}
~~~

concat đăng ký nguồn sau khi nguồn trước hoàn tất. Toàn bộ Flux hoàn tất khi tất cả nguồn được nối tiếp đã hoàn tất. Nếu một nguồn phát lỗi, chuỗi kết thúc bằng lỗi trừ khi ứng dụng xử lý lỗi đó.

Với merge, các nguồn có thể phát xen kẽ; Flux kết quả hoàn tất khi tất cả nguồn đã hoàn tất. Chọn concat hay merge dựa trên yêu cầu về thứ tự và tính đồng thời, không chỉ dựa vào cú pháp ngắn hơn.

## 5. Thiết kế luồng liên tục

Luồng liên tục phù hợp với dữ liệu phát sinh theo thời gian và không có mốc kết thúc tự nhiên ngay khi request bắt đầu:

- Giá cổ phiếu hoặc tỷ giá realtime.
- Trạng thái cảm biến hoặc thiết bị.
- Vị trí của phương tiện.
- Thông báo trạng thái của một tiến trình đang chạy.
- Sự kiện thay đổi của một thực thể đang được theo dõi.

Một nguồn có thể phát theo chu kỳ:

~~~java
Flux<Heartbeat> heartbeatStream() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(sequence -> new Heartbeat(
            sequence,
            Instant.now()
        ));
}
~~~

Flux.interval tiếp tục phát cho đến khi subscription bị hủy hoặc scheduler/nguồn phát sinh lỗi. Vì vậy, request-stream dựa trên nguồn này sẽ không tự hoàn tất sau một số phần tử cố định.

Trong hệ thống thực tế, luồng liên tục thường cần một khóa đăng ký hoặc bộ lọc:

~~~java
Flux<PriceUpdate> watchPrice(String symbol) {
    return priceFeed.events(symbol)
        .map(event -> new PriceUpdate(
            symbol,
            event.price(),
            event.timestamp()
        ));
}
~~~

Nguồn priceFeed có thể là hot publisher kết nối với một luồng sự kiện bên ngoài. Khi không có cập nhật, nó có thể tạm thời không phát onNext nhưng vẫn giữ stream mở. Điều này không có nghĩa là stream đã hoàn tất.

### Hot source và cold source

Nguồn cold thường bắt đầu công việc khi có subscriber và mỗi subscriber có thể tạo một luồng thực thi riêng. Nguồn hot có thể phát sự kiện độc lập với thời điểm subscriber đăng ký; subscriber mới có thể chỉ nhận sự kiện từ thời điểm đăng ký trở đi, tùy chính sách replay của nguồn.

| Loại nguồn | Hành vi thường gặp | Ví dụ |
|---|---|---|
| Cold | Mỗi subscription bắt đầu một lần thực thi | Flux.fromIterable, truy vấn reactive |
| Hot | Sự kiện phát độc lập với subscriber | Feed giá, event bus, Sinks.Many |
| Replayable | Có thể phát lại một phần lịch sử cho subscriber mới | Replay sink hoặc event log |

Khi dùng hot source cho request-stream, hãy xác định subscriber mới nhận dữ liệu từ thời điểm nào. Nếu client cần không bỏ sót sự kiện, hãy thiết kế cursor/offset, replay window hoặc cơ chế snapshot kết hợp với stream sự kiện.

## 6. Điều kiện hoàn thành của luồng

Điều kiện hoàn thành phải xuất phát từ nghiệp vụ. Một số mẫu phổ biến:

| Điều kiện | Cách biểu diễn | Khi phù hợp |
|---|---|---|
| Nguồn hết dữ liệu | Nguồn phát onComplete | Truy vấn hoặc batch hữu hạn |
| Đạt số lượng phần tử | take(n) | Chỉ cần N sự kiện đầu tiên |
| Hết khoảng thời gian theo dõi | take(Duration) | Theo dõi trong một cửa sổ thời gian |
| Đạt điều kiện nghiệp vụ | takeUntil(predicate) | Dừng khi tiến trình đạt trạng thái đích |
| Server chủ động đóng | Trả publisher đã hoàn tất | Phiên theo dõi kết thúc theo chính sách server |
| Client không còn cần dữ liệu | Hủy subscription, truyền CANCEL | Người dùng rời màn hình hoặc bỏ thao tác |

### Hoàn tất theo số lượng

~~~java
Flux<PriceUpdate> firstTenUpdates(String symbol) {
    return priceFeed.events(symbol)
        .take(10);
}
~~~

Client nhận tối đa mười cập nhật. Khi nhận đủ mười phần tử, Flux phía client hoàn tất. Nếu nguồn phía server còn hoạt động, cancellation sẽ được truyền ngược để dừng đăng ký tương ứng.

### Hoàn tất theo thời gian

~~~java
Flux<PriceUpdate> watchForThirtySeconds(String symbol) {
    return priceFeed.events(symbol)
        .take(Duration.ofSeconds(30));
}
~~~

take(Duration) kết thúc luồng sau khoảng thời gian quy định và hủy upstream. Đây là giới hạn tổng thời gian theo dõi. Nó khác timeout(Duration), vốn thường đặt giới hạn thời gian chờ một tín hiệu tiếp theo.

### Hoàn tất theo điều kiện nghiệp vụ

~~~java
Flux<JobStatus> watchUntilFinished(String jobId) {
    return jobStatusFeed.watch(jobId)
        .takeUntil(status ->
            status.state() == JobState.COMPLETED
                || status.state() == JobState.FAILED
        );
}
~~~

Khi phần tử thỏa điều kiện được phát, takeUntil vẫn phát phần tử đó rồi hoàn tất downstream và hủy upstream. Nếu muốn dừng mà không phát phần tử kết thúc, hãy chọn toán tử khác và diễn đạt rõ hợp đồng.

### Luồng không có dữ liệu mới

Một stream realtime có thể không phát dữ liệu trong một khoảng thời gian nhưng vẫn còn hoạt động. Đừng tự động xem im lặng là hoàn tất. Hãy phân biệt:

- Không có sự kiện mới: stream vẫn mở.
- Nguồn đã hết dữ liệu: onComplete.
- Nguồn không thể tiếp tục: onError.
- Client chủ động dừng: CANCEL.

Nếu nghiệp vụ cần thông báo "không có cập nhật", có thể phát heartbeat hoặc trạng thái keep-alive ở tầng ứng dụng. RSocket KEEPALIVE frame phục vụ quản lý kết nối và không thay thế một response event nghiệp vụ trong request-stream.

## 7. Triển khai request-stream ở phía responder

Spring ánh xạ route vào method @MessageMapping. Method trả về Flux<T> khi server cần phát nhiều response:

~~~java
@Controller
public class PriceController {

    private final PriceFeed priceFeed;

    public PriceController(PriceFeed priceFeed) {
        this.priceFeed = priceFeed;
    }

    @MessageMapping("prices.watch")
    public Flux<PriceUpdate> watch(WatchPriceRequest request) {
        return priceFeed.events(request.symbol())
            .map(event -> new PriceUpdate(
                request.symbol(),
                event.price(),
                event.timestamp()
            ));
    }
}
~~~

Requester gửi một WatchPriceRequest. Responder trả về Flux<PriceUpdate>. Nếu priceFeed là nguồn liên tục, handler giữ stream mở trong khi nguồn còn hoạt động.

Với nguồn hữu hạn, handler có thể trả trực tiếp Flux từ repository:

~~~java
@MessageMapping("orders.events")
public Flux<OrderEvent> orderEvents(OrderEventsRequest request) {
    return orderEventRepository
        .findByOrderIdOrderByCreatedAt(request.orderId());
}
~~~

Nguồn repository hoàn tất sau khi phát các event phù hợp. RSocket kết thúc interaction khi publisher hoàn tất.

### Dọn dẹp khi client hủy

Nguồn realtime có thể tạo subscription vào broker, event bus hoặc tài nguyên bên ngoài. Hãy giải phóng chúng khi stream hoàn tất, gặp lỗi hoặc bị hủy:

~~~java
@MessageMapping("prices.watch")
public Flux<PriceUpdate> watch(WatchPriceRequest request) {
    return priceFeed.events(request.symbol())
        .map(this::toPriceUpdate)
        .doFinally(signalType -> {
            if (signalType == SignalType.CANCEL) {
                log.debug(
                    "Price stream cancelled: {}",
                    request.symbol()
                );
            }
        });
}
~~~

doFinally được gọi khi chuỗi kết thúc bằng complete, error hoặc cancel. Dùng nó để ghi nhận vòng đời hoặc gọi cleanup phù hợp. Nếu việc đăng ký nguồn ngoài cần đóng tài nguyên, hãy dùng API tạo publisher có hỗ trợ cleanup khi cancel, chẳng hạn Flux.using hoặc Flux.usingWhen cho tài nguyên bất đồng bộ.

Không dùng doOnComplete làm nơi duy nhất để cleanup một stream liên tục: khi client hủy, onComplete không được phát về subscriber đã hủy. Cần xử lý cả cancellation.

## 8. Nhận request-stream bằng RSocketRequester

Ở phía client, retrieveFlux yêu cầu response dưới dạng Flux:

~~~java
Flux<PriceUpdate> updates = requester
    .route("prices.watch")
    .data(new WatchPriceRequest("ACME"))
    .retrieveFlux(PriceUpdate.class);
~~~

Có thể xử lý từng phần tử khi nó đến:

~~~java
updates
    .doOnNext(update -> priceCache.put(
        update.symbol(),
        update.price()
    ))
    .doOnError(error ->
        log.warn("Price stream failed", error)
    )
    .doOnComplete(() ->
        log.info("Price stream completed")
    )
    .subscribe();
~~~

Trong ứng dụng reactive, nên trả Flux từ service để caller quyết định subscription và vòng đời. Ví dụ:

~~~java
@Service
public class PriceClient {

    private final RSocketRequester requester;

    public PriceClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Flux<PriceUpdate> watch(String symbol) {
        return requester
            .route("prices.watch")
            .data(new WatchPriceRequest(symbol))
            .retrieveFlux(PriceUpdate.class);
    }
}
~~~

UI hoặc tầng gọi có thể hủy subscription khi người dùng rời màn hình. Khi đó cancellation truyền ngược đến request-stream và server có thể dừng việc phát dữ liệu cho subscriber đó.

## 9. Backpressure và demand trong request-stream

Một stream có thể phát nhanh hơn tốc độ client xử lý. Reactive Streams dùng demand để subscriber báo trước số phần tử nó sẵn sàng nhận. RSocket hỗ trợ cơ chế này ở tầng giao thức:

- REQUEST_STREAM mang số lượng response ban đầu mà requester muốn nhận, gọi là initial request N.
- Khi requester cần thêm phần tử, nó gửi REQUEST_N với số lượng demand bổ sung.
- Responder chỉ được phát số phần tử tương ứng với demand đã nhận.
- Demand được cộng dồn; số lượng yêu cầu phải là số dương.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: REQUEST_STREAM (requestN = 5)
    S-->>C: PAYLOAD 1
    S-->>C: PAYLOAD 2
    S-->>C: PAYLOAD 3
    Note over C: Client xử lý dữ liệu
    C->>S: REQUEST_N (requestN = 3)
    S-->>C: PAYLOAD 4
    S-->>C: PAYLOAD 5
    S-->>C: PAYLOAD 6
    S-->>C: PAYLOAD 7
~~~

Ở tầng ứng dụng, Spring và RSocket Java quản lý việc chuyển demand của Reactive Streams thành request N của giao thức. Thông thường, bạn làm việc với Flux và các subscriber/operator thay vì tự gửi REQUEST_N frame.

Backpressure không đồng nghĩa với việc nguồn dữ liệu luôn có thể chậm lại. Một số nguồn bên ngoài không hỗ trợ demand, chẳng hạn thiết bị phát dữ liệu liên tục hoặc broker đã đẩy sự kiện vào consumer. Khi đó ứng dụng cần quyết định cách đệm, giới hạn, bỏ hoặc gộp dữ liệu.

### Chọn chiến lược khi consumer chậm

| Chiến lược | Cách xử lý | Phù hợp khi |
|---|---|---|
| Buffer có giới hạn | Lưu tạm tối đa N phần tử; xử lý chính sách khi đầy | Mỗi event đều quan trọng trong giới hạn tải |
| Drop | Bỏ phần tử mới hoặc cũ theo chính sách | Dữ liệu có thể mất mà không làm sai nghiệp vụ |
| Latest | Chỉ giữ giá trị mới nhất | UI chỉ cần trạng thái hiện tại |
| Sample/throttle | Giảm tần suất phát | Telemetry hoặc cập nhật quá dày |
| Từ chối/đóng stream | Kết thúc khi vượt ngưỡng | Không thể tiếp tục an toàn khi quá tải |

Ví dụ giới hạn buffer:

~~~java
Flux<PriceUpdate> updates =
    externalPriceFeed.events()
        .onBackpressureBuffer(
            500,
            dropped -> log.warn(
                "Price buffer is full; event dropped: {}",
                dropped.symbol()
            ),
            BufferOverflowStrategy.DROP_OLDEST
        );
~~~

Chọn buffer có giới hạn để bộ nhớ không tăng vô hạn. Nếu dữ liệu bị drop, phải xác định ứng dụng có thể khôi phục bằng snapshot hoặc truy vấn lại hay không. Với giao dịch tài chính hoặc lệnh điều khiển, bỏ sự kiện có thể không được phép; khi đó cần cơ chế lưu bền vững hoặc dừng consumer có kiểm soát.

Các toán tử onBackpressureBuffer, onBackpressureDrop và onBackpressureLatest thay đổi cách ứng dụng xử lý khi nguồn không tuân theo demand. Chúng không thay thế backpressure của RSocket và không tự tạo ra khả năng điều tiết cho một nguồn ngoài vốn không thể tạm dừng.

## 10. Timeout, im lặng và heartbeat

Đối với stream liên tục, timeout cần được hiểu chính xác. Reactor timeout(Duration) thường giới hạn khoảng thời gian chờ tín hiệu tiếp theo. Nếu stream phát đều đặn, timer được làm mới theo từng tín hiệu; nếu không có dữ liệu trong khoảng quy định, chuỗi kết thúc bằng TimeoutException.

~~~java
Flux<PriceUpdate> watch(String symbol) {
    return requester
        .route("prices.watch")
        .data(new WatchPriceRequest(symbol))
        .retrieveFlux(PriceUpdate.class)
        .timeout(Duration.ofSeconds(15));
}
~~~

Ví dụ này phù hợp khi nghiệp vụ kỳ vọng có ít nhất một cập nhật trong mỗi khoảng 15 giây. Nếu thị trường có thể không thay đổi lâu hơn, timeout như vậy có thể gây ngắt stream dù kết nối vẫn khỏe. Khi đó hãy dùng heartbeat ứng dụng hoặc một chính sách timeout phù hợp với tần suất sự kiện.

Timeout theo khoảng thời gian chờ tín hiệu khác với giới hạn tổng thời gian theo dõi:

~~~java
Flux<PriceUpdate> watchForOneMinute(String symbol) {
    return requester
        .route("prices.watch")
        .data(new WatchPriceRequest(symbol))
        .retrieveFlux(PriceUpdate.class)
        .take(Duration.ofMinutes(1));
}
~~~

take(Duration) kết thúc downstream sau một phút dù các event vẫn tiếp tục đến. timeout(Duration) kết thúc khi không nhận được tín hiệu tiếp theo đủ lâu.

RSocket KEEPALIVE dùng để phát hiện trạng thái kết nối ở tầng giao thức. Nó không nhất thiết tạo ra onNext trong Flux nghiệp vụ. Vì thế, một stream không có event không đồng nghĩa kết nối đã chết; cần phân biệt timeout của event với keepalive/connection liveness.

## 11. Lỗi và phục hồi stream

Nếu publisher phát onError, stream kết thúc. Không có response event tiếp theo trên cùng interaction sau lỗi terminal đó. Client có thể xử lý lỗi, chuyển sang nguồn dự phòng hoặc tạo một subscription mới tùy hợp đồng:

~~~java
Flux<PriceUpdate> watch(String symbol) {
    return primaryPriceFeed.watch(symbol)
        .onErrorResume(
            PriceFeedUnavailableException.class,
            error -> backupPriceFeed.watch(symbol)
        );
}
~~~

Nếu lỗi xảy ra ở một nguồn liên tục, cần xác định việc fallback có giữ được thứ tự, độ mới và tính đầy đủ của dữ liệu không. Hai feed có thể có offset hoặc thời gian cập nhật khác nhau.

Có thể retry stream khi lỗi được xác định là tạm thời:

~~~java
Flux<PriceUpdate> watch(String symbol) {
    return requester
        .route("prices.watch")
        .data(new WatchPriceRequest(symbol))
        .retrieveFlux(PriceUpdate.class)
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(500))
                .filter(this::isTransientFailure)
        );
}
~~~

Retry tạo subscription mới. Nó không tự khôi phục chính xác vị trí trong luồng cũ. Nếu stream chứa event có thể bị phát lại, client có thể nhận trùng hoặc bỏ sót event trong khoảng ngắt. Với event quan trọng, hãy truyền cursor/offset, sequence number hoặc timestamp có quy tắc rõ ràng; server cần hỗ trợ tiếp tục từ vị trí đó và client cần xử lý trùng lặp.

Với stream realtime, phục hồi kết nối ở tầng RSocket và phục hồi vị trí nghiệp vụ là hai vấn đề riêng. Resumption có thể hỗ trợ tiếp tục session theo khả năng của triển khai, nhưng không thay thế thiết kế replay/cursor của nguồn dữ liệu ứng dụng.

## 12. Kiểm thử luồng hữu hạn và liên tục

StepVerifier giúp kiểm tra các tín hiệu phát ra và điều kiện kết thúc.

### Luồng hữu hạn hoàn tất

~~~java
@Test
void finiteStreamEmitsValuesAndCompletes() {
    Flux<Integer> source = Flux.range(1, 3);

    StepVerifier.create(source)
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

### Luồng rỗng hoàn tất ngay

~~~java
@Test
void emptyStreamCompletesWithoutValues() {
    StepVerifier.create(Flux.<String>empty())
        .verifyComplete();
}
~~~

### Luồng liên tục được kiểm tra bằng giới hạn

Không nên chờ một Flux.interval vô hạn hoàn tất tự nhiên trong test. Dùng take để tạo một phần kiểm tra hữu hạn:

~~~java
@Test
void continuousSourceCanBeCancelledAfterThreeValues() {
    StepVerifier.withVirtualTime(() ->
            Flux.interval(Duration.ofMillis(10)).take(3)
        )
        .thenAwait(Duration.ofMillis(30))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
}
~~~

Với scheduler ảo, hãy tạo publisher bên trong Supplier truyền cho withVirtualTime để timer dùng virtual scheduler do StepVerifier cài đặt.

### Kiểm tra cancellation

~~~java
@Test
void cancellationReachesSource() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Long> source = Flux.interval(Duration.ofMillis(10))
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .thenAwait(Duration.ofMillis(30))
        .thenCancel()
        .verify();

    assertThat(cancelled).isTrue();
}
~~~

Kiểm tra cancellation đặc biệt quan trọng với stream liên tục vì nó xác nhận server hoặc publisher có cơ hội dừng nguồn và giải phóng tài nguyên khi client rời đi.

### Kiểm tra lỗi

~~~java
@Test
void streamTerminatesOnError() {
    Flux<String> source = Flux.concat(
        Flux.just("event-1", "event-2"),
        Flux.error(new IllegalStateException("feed failed"))
    );

    StepVerifier.create(source)
        .expectNext("event-1", "event-2")
        .expectErrorMessage("feed failed")
        .verify();
}
~~~

Kiểm thử tích hợp requester/responder nên bao gồm cả transport thực tế, metadata route, serialization, nhiều subscriber, client hủy stream, nguồn phát lỗi và hành vi khi consumer chậm.

## 13. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Stream giữ kết nối mãi dù dữ liệu đã hết | Nguồn không phát onComplete | Chọn nguồn hữu hạn hoặc thêm điều kiện kết thúc |
| Stream kết thúc quá sớm | Dùng take, timeout hoặc filter sai | Kiểm tra điều kiện giới hạn và tần suất event |
| Không có event nhưng client cho rằng lỗi | Nhầm im lặng với completion hoặc connection failure | Xác định rõ chính sách idle và heartbeat |
| Server vẫn làm việc sau khi client rời màn hình | Nguồn không phản ứng với cancel hoặc cleanup thiếu | Dùng doFinally/using và kiểm thử CANCEL |
| Bộ nhớ tăng khi client chậm | Buffer không giới hạn hoặc nguồn không hỗ trợ demand | Giới hạn buffer và chọn drop/latest/persist |
| Event bị trùng sau retry | Subscription mới phát lại dữ liệu cũ | Dùng sequence, cursor và deduplication |
| Client không nhận đủ event | Buffer overflow, drop hoặc reconnect không có replay | Chọn chính sách dữ liệu và cơ chế phục hồi rõ ràng |
| Timeout liên tục trên feed ít cập nhật | Timeout được đặt ngắn hơn khoảng im lặng hợp lệ | Điều chỉnh timeout hoặc phát heartbeat ứng dụng |

## 14. Quy trình chọn điều kiện hoàn thành

Khi thiết kế request-stream, hãy trả lời các câu hỏi sau:

1. Nguồn có điểm kết thúc tự nhiên không? Nếu có, dùng publisher hữu hạn và để onComplete kết thúc stream.
2. Nếu là feed liên tục, ai quyết định dừng: server, client hay một điều kiện nghiệp vụ?
3. Khi client không còn cần dữ liệu, cancellation có dừng subscription và giải phóng tài nguyên không?
4. Nếu không có event trong một khoảng thời gian, đó là bình thường hay là lỗi cần timeout?
5. Consumer chậm thì dữ liệu được buffer, drop, gộp hay stream bị đóng?
6. Khi lỗi hoặc mất kết nối, client bắt đầu lại từ đâu? Có cursor, sequence hoặc replay không?
7. Test đã xác nhận completion, error, cancellation và backpressure chưa?

Luồng hữu hạn nên kết thúc khi nguồn hoàn tất hoặc đạt giới hạn đã định. Luồng liên tục cần có chính sách vòng đời rõ ràng, thường kết thúc do client hủy, server đóng theo điều kiện nghiệp vụ hoặc lỗi. Phân biệt các tín hiệu này giúp RSocket stream hoạt động ổn định và tránh giữ tài nguyên vô thời hạn.

## Ghi nhớ

- Request-stream gửi một request và nhận không hoặc nhiều response payload.
- Flux có thể hữu hạn hoặc liên tục; kiểu Flux tự nó không nói trước khi nào stream kết thúc.
- onComplete là hoàn tất bình thường; onError là kết thúc do lỗi; cancel là yêu cầu dừng từ subscriber.
- Nguồn liên tục cần điều kiện kết thúc hoặc cơ chế hủy rõ ràng.
- RSocket dùng demand/request N để điều tiết số response được phát.
- Timeout giới hạn khoảng chờ tín hiệu; take(Duration) giới hạn tổng thời gian theo dõi.
- Retry tạo subscription mới; muốn tiếp tục đúng vị trí cần cursor/offset và xử lý trùng lặp.
- Luôn kiểm thử completion, error, cancellation và hành vi khi consumer chậm.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Protocol: Request-Stream](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Framework: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm)

