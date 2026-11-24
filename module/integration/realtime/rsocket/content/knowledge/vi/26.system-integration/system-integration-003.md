# Chuyển nguồn dữ liệu phản ứng thành request-stream

## Bối cảnh: một request có thể mở ra luồng dữ liệu liên tục

Trong RSocket, request-stream là interaction trong đó client gửi một request ban đầu và server trả về không, một hoặc nhiều payload theo thời gian. Với Spring, một phương thức xử lý route có thể trả về Flux; Spring kết nối publisher đó với RSocket responder và truyền các phần tử thành response stream.

Cách này phù hợp khi dữ liệu đã có nguồn reactive, chẳng hạn:

- Repository dùng R2DBC trả về Flux các bản ghi.
- WebClient đọc response body thành Flux từ một dịch vụ khác.
- Reactive Kafka consumer phát các record mới.
- Nguồn telemetry hoặc event bus phát sự kiện theo thời gian.
- Một API callback cũ cần được bọc thành Publisher.

Điểm cốt lõi là giữ dữ liệu trong pipeline reactive từ lúc đọc nguồn đến lúc gửi response. Khi client giảm demand hoặc hủy subscription, tín hiệu cần được truyền ngược về publisher nguồn để điều tiết hoặc dừng việc đọc dữ liệu.

Bài học này trình bày cách chuyển đổi các nguồn dữ liệu đó thành request-stream, chọn giữa nguồn cold và hot, quản lý backpressure, lỗi, cancellation và kiểm thử luồng dữ liệu từ đầu đến cuối.

## 1. Request-stream nhận một request và trả về nhiều response

Request-stream có một payload request ban đầu. Payload này thường mang tiêu chí truy vấn như sensor ID, khoảng thời gian, bộ lọc hoặc cursor. Server dùng request để tạo một Publisher và phát nhiều response.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant H as Spring Message Handler
    participant S as Reactive Data Source
    C->>H: REQUEST_STREAM sensor.readings
    H->>S: Tạo Flux theo sensorId
    S-->>H: onNext(event 1)
    H-->>C: PAYLOAD event 1
    C-->>H: REQUEST_N
    S-->>H: onNext(event 2..N)
    H-->>C: PAYLOAD event 2..N
    S-->>H: onComplete
    H-->>C: COMPLETE
~~~

Ví dụ route có thể được khai báo như sau:

~~~java
public record SensorQuery(
    String sensorId,
    Instant from,
    Instant to
) {}

public record ReadingEvent(
    String sensorId,
    long sequence,
    Instant observedAt,
    double temperature
) {}

@Controller
class SensorStreamController {

    private final ReadingService readingService;

    SensorStreamController(ReadingService readingService) {
        this.readingService = readingService;
    }

    @MessageMapping("sensor.readings")
    Flux<ReadingEvent> readings(@Payload SensorQuery query) {
        return readingService.streamReadings(query);
    }
}
~~~

Client gửi một SensorQuery và nhận nhiều ReadingEvent:

~~~java
Flux<ReadingEvent> readings = requester
    .route("sensor.readings")
    .data(new SensorQuery(
        "sensor-01",
        Instant.now().minus(Duration.ofMinutes(10)),
        Instant.now()
    ))
    .retrieveFlux(ReadingEvent.class);
~~~

Spring dùng kiểu trả về Flux để xác định response là một stream. Mỗi phần tử được encode thành payload riêng. Publisher hoàn tất thì interaction kết thúc bình thường; publisher phát lỗi thì interaction kết thúc bằng lỗi; client hủy subscription thì cancellation được truyền về phía server.

### Phân biệt request-stream và request-channel

Request-stream chỉ có một request payload ban đầu và nhiều response payload. Request-channel cho phép client gửi một Publisher nhiều payload, đồng thời server có thể trả về nhiều payload.

| Nhu cầu | Interaction phù hợp |
|---|---|
| Gửi một query, nhận nhiều bản ghi | Request-stream |
| Gửi một command, nhận một kết quả | Request-response |
| Gửi nhiều command và nhận nhiều acknowledgement | Request-channel |
| Gửi thông báo không cần response nghiệp vụ | Fire-and-forget |

Nếu đầu vào là Flux các truy vấn hoặc command, đó không còn là request-stream thuần túy; hãy xem xét request-channel. Chọn đúng interaction giúp route có hợp đồng dữ liệu rõ ràng.

## 2. Chuyển reactive repository thành response stream

Nguồn dễ tích hợp nhất là repository đã trả về Publisher. Với Spring Data R2DBC, một phương thức repository có thể trả Flux các entity phù hợp với điều kiện truy vấn.

Ví dụ:

~~~java
public interface ReadingRepository
        extends ReactiveCrudRepository<ReadingEntity, Long> {

    Flux<ReadingEntity> findBySensorIdAndObservedAtBetweenOrderBySequenceAsc(
        String sensorId,
        Instant from,
        Instant to
    );
}
~~~

Service chuyển entity thành DTO dùng trên wire:

~~~java
@Service
class ReadingService {

    private final ReadingRepository repository;

    ReadingService(ReadingRepository repository) {
        this.repository = repository;
    }

    Flux<ReadingEvent> streamReadings(SensorQuery query) {
        return Flux.defer(() ->
            repository
                .findBySensorIdAndObservedAtBetweenOrderBySequenceAsc(
                    query.sensorId(),
                    query.from(),
                    query.to()
                )
                .map(entity -> new ReadingEvent(
                    entity.getSensorId(),
                    entity.getSequence(),
                    entity.getObservedAt(),
                    entity.getTemperature()
                ))
        );
    }
}
~~~

**Flux.defer** trì hoãn việc gọi repository cho đến khi có subscriber. Điều này hữu ích khi mỗi request-stream cần một lần truy vấn riêng. Hai client đăng ký cùng route sẽ tạo hai subscription và có thể thực hiện hai truy vấn độc lập.

Không nên trả entity persistence trực tiếp nếu nó chứa trường nội bộ, quan hệ lazy hoặc cấu trúc không phải hợp đồng API. Hãy chuyển thành DTO có schema ổn định, có thể thêm version nếu payload được nhiều ứng dụng tiêu thụ.

### Nguồn database hữu hạn và nguồn live

Một truy vấn R2DBC thông thường thường trả về một tập kết quả hữu hạn rồi complete. Nó vẫn có thể được truyền dưới dạng request-stream, nhưng stream sẽ kết thúc khi đọc hết các hàng.

Nếu muốn gửi dữ liệu mới liên tục, cần một nguồn live như change feed, CDC, reactive message broker hoặc event bus. Không nên giả định Flux từ một truy vấn database tự động theo dõi các hàng mới được insert sau khi query hoàn tất.

Có thể kết hợp snapshot ban đầu với nguồn cập nhật live, nhưng phải xác định ranh giới nhất quán giữa hai nguồn. Nếu không có cursor hoặc high-watermark chung, event xuất hiện đúng lúc chuyển từ snapshot sang live có thể bị bỏ sót hoặc lặp lại.

## 3. Chuyển response body của WebClient thành request-stream

WebClient có thể đọc response body thành Flux. Khi dịch vụ upstream trả về JSON array hoặc stream các phần tử, server RSocket có thể chuyển đổi chúng thành response cho client của mình.

~~~java
@Service
class RemoteReadingService {

    private final WebClient webClient;

    RemoteReadingService(WebClient webClient) {
        this.webClient = webClient;
    }

    Flux<ReadingEvent> streamRemoteReadings(String sensorId) {
        return webClient.get()
            .uri(uriBuilder -> uriBuilder
                .path("/sensors/{sensorId}/readings")
                .build(sensorId))
            .retrieve()
            .bodyToFlux(ReadingEvent.class)
            .onErrorMap(error ->
                new UpstreamReadException(
                    "Cannot read sensor stream",
                    error
                )
            );
    }
}
~~~

Handler chỉ cần trả publisher:

~~~java
@MessageMapping("sensor.remote-readings")
Flux<ReadingEvent> remoteReadings(@Payload SensorQuery query) {
    return remoteReadingService.streamRemoteReadings(query.sensorId());
}
~~~

WebClient và RSocket cùng sử dụng reactive pipeline, nên response từ upstream có thể được chuyển tiếp theo demand downstream. Không cần tạo thread riêng hoặc tự subscribe vào WebClient.

Cần cấu hình timeout, xác thực upstream và giới hạn kích thước response phù hợp. Nếu upstream là stream vô hạn, nên có chính sách kết thúc như thời lượng tối đa, cursor hoặc cancellation từ client.

## 4. Chuyển reactive message consumer thành stream

Một reactive message broker có thể cung cấp Publisher cho các record mới. Ví dụ với Reactor Kafka, receiver phát các record từ topic:

~~~java
Flux<ReadingEvent> streamKafkaReadings(String sensorId) {
    return kafkaReceiver.receive()
        .filter(record ->
            sensorId.equals(record.key()))
        .map(record -> record.value());
}
~~~

Đây là ví dụ minh họa nguồn reactive; cấu hình receiver, consumer group, partition assignment và commit offset cần được quản lý theo lifecycle của ứng dụng.

Không nên tự động commit offset Kafka ngay khi map record thành DTO hoặc khi RSocket vừa gửi payload. Việc record đã được phát xuống client không chứng minh client đã commit nghiệp vụ. Nếu cần bảo đảm nghiệp vụ, hãy dùng application ACK/checkpoint riêng và thiết kế quan hệ giữa offset Kafka với trạng thái consumer một cách rõ ràng.

Một receiver dùng chung cho nhiều client cần chính sách phân phối phù hợp. Nếu mỗi client phải nhận toàn bộ event, hãy chọn consumer group hoặc fan-out architecture phù hợp; không giả định nhiều subscriber trên cùng một Kafka receiver đều nhận bản sao của mọi record.

## 5. Bọc API callback thành Flux

Không phải nguồn nào cũng hỗ trợ Reactive Streams. Một thư viện telemetry cũ có thể đăng ký listener và gọi callback mỗi khi có dữ liệu. Có thể bọc API đó bằng **Flux.create**.

Giả sử API callback có dạng:

~~~java
interface EventRegistration {
    void cancel();
}

interface LegacyEventSource {
    EventRegistration subscribe(
        Consumer<Reading> onNext,
        Consumer<Throwable> onError,
        Runnable onComplete
    );
}
~~~

Adapter chuyển callback thành Flux:

~~~java
Flux<Reading> adapt(LegacyEventSource source) {
    return Flux.create(sink -> {
        EventRegistration registration = source.subscribe(
            sink::next,
            sink::error,
            sink::complete
        );

        sink.onDispose(registration::cancel);
    }, FluxSink.OverflowStrategy.ERROR);
}
~~~

Khi downstream hủy hoặc stream kết thúc, callback onDispose hủy đăng ký listener. Điều này giúp tránh listener tiếp tục giữ tham chiếu tới handler sau khi client đã ngắt kết nối.

**Flux.create** phù hợp với callback có thể phát từ nhiều thread. Nếu nguồn bảo đảm chỉ phát trên một thread, Flux.push có thể phù hợp hơn. Chọn adapter theo concurrency contract của nguồn.

### Adapter không tự tạo backpressure cho API callback

Flux.create đưa callback vào reactive pipeline, nhưng nguồn callback có thể vẫn phát nhanh hơn demand. Chiến lược overflow trong ví dụ là ERROR: nếu downstream không theo kịp, stream kết thúc bằng lỗi thay vì âm thầm tích lũy dữ liệu vô hạn.

Nếu API callback hỗ trợ pause/resume hoặc yêu cầu thêm dữ liệu theo demand, adapter nên nối nhu cầu của sink tới API đó. Nếu nguồn không thể dừng, phải chọn chính sách rõ ràng:

- Buffer có giới hạn và xử lý overflow.
- Drop event khi quá tải nếu dữ liệu có thể mất.
- Giữ giá trị mới nhất nếu chỉ cần trạng thái hiện tại.
- Phát lỗi và yêu cầu client đăng ký lại.
- Ghi event vào durable log trước khi đưa vào stream.

Không dùng buffer vô hạn cho nguồn có tốc độ không kiểm soát. Điều đó có thể làm bộ nhớ tăng liên tục khi client chậm hoặc mất kết nối.

## 6. Phân biệt nguồn cold và hot

Cold Publisher tạo hoặc đọc dữ liệu riêng cho từng subscription. Hot Publisher phát dữ liệu độc lập với một subscriber cụ thể và có thể được nhiều subscriber cùng quan sát.

| Đặc điểm | Cold source | Hot source |
|---|---|---|
| Khi bắt đầu | Thường khi có subscription | Có thể phát trước khi có subscriber |
| Mỗi subscriber | Có thể tạo query hoặc luồng riêng | Có thể cùng nghe một nguồn đang chạy |
| Ví dụ | R2DBC query, WebClient request | Telemetry bus, event sink, shared feed |
| Hủy một subscriber | Hủy công việc riêng của subscription đó | Thường chỉ gỡ subscriber đó; nguồn dùng chung vẫn chạy |
| Rủi ro chính | Nhiều client tạo nhiều truy vấn | Fan-out, buffer và subscriber chậm |

### Cold source với Flux.defer

~~~java
Flux<ReadingEvent> streamForClient(SensorQuery query) {
    return Flux.defer(() ->
        readingService.streamReadings(query)
    );
}
~~~

Mỗi lần route được subscribe sẽ tạo nguồn mới. Đây thường là hành vi phù hợp khi mỗi client có filter, quyền truy cập hoặc cursor riêng.

### Hot source với Reactor Sinks

Có thể dùng Sinks.Many để đưa callback hoặc event nội bộ vào một Flux được chia sẻ:

~~~java
class TelemetryEventBus {

    private final Sinks.Many<ReadingEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer(256, false);

    void publish(ReadingEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);

        if (result.isFailure()) {
            // Ghi metrics và áp dụng chính sách overflow/retry.
            log.warn("Cannot publish telemetry event: {}", result);
        }
    }

    Flux<ReadingEvent> events() {
        return sink.asFlux();
    }
}
~~~

Đây là một nguồn hot. Các route có thể lọc dữ liệu theo sensor:

~~~java
@MessageMapping("sensor.live")
Flux<ReadingEvent> live(@Payload SensorQuery query) {
    return telemetryEventBus.events()
        .filter(event ->
            query.sensorId().equals(event.sensorId()));
}
~~~

Ví dụ dùng buffer tối đa 256 phần tử và tắt auto-cancel để sink dùng chung vẫn tồn tại khi subscriber cuối cùng rời đi. Khi buffer đầy, tryEmitNext có thể trả về FAIL_OVERFLOW; ứng dụng phải ghi metrics và áp dụng chính sách phù hợp. Nếu muốn sink tự kết thúc khi subscriber cuối cùng hủy, hãy chọn auto-cancel theo đúng lifecycle mong muốn. Một subscriber chậm cũng có thể làm tăng áp lực buffer của multicast sink, vì vậy cần cân nhắc queue riêng cho từng client hoặc chiến lược drop nếu nghiệp vụ cho phép. Nếu mọi event phải được lưu bền vững, một sink trong bộ nhớ không thể thay thế event log hoặc message broker.

Không gọi subscribe trong phương thức publish hoặc trong handler để tạo một luồng nền ẩn. Hãy để Spring/RSocket quản lý subscription của từng request-stream và để một thành phần riêng quản lý lifecycle của nguồn hot.

## 7. Áp dụng filter, map, window và buffer trước khi gửi

Reactive operator giúp biến nguồn tổng quát thành response phù hợp với hợp đồng route.

Ví dụ lọc theo ngưỡng:

~~~java
Flux<ReadingEvent> stream = source
    .filter(event -> event.temperature() >= 30.0)
    .map(this::toPublicEvent);
~~~

Ví dụ gom thành batch:

~~~java
Flux<ReadingBatch> batches = source
    .bufferTimeout(100, Duration.ofSeconds(1))
    .filter(batch -> !batch.isEmpty())
    .map(ReadingBatch::new);
~~~

Batching giảm số payload và overhead giao thức, nhưng làm tăng độ trễ vì server có thể chờ đủ số lượng hoặc timeout. Hãy chọn kích thước batch theo SLA và kích thước payload tối đa.

Có thể giới hạn số phần tử:

~~~java
Flux<ReadingEvent> latestWindow = source.take(500);
~~~

take(500) phát tối đa 500 event rồi complete. Đây là cách tạo một stream hữu hạn; nếu client muốn tiếp tục, nó có thể mở request-stream mới với cursor tiếp theo.

Tránh dùng operator làm mất ý nghĩa dữ liệu mà không ghi rõ trong hợp đồng. Ví dụ distinct có thể loại bỏ các event trùng theo equality, nhưng không thay thế idempotency hoặc deduplication bền vững.

## 8. Backpressure: nối demand từ client tới nguồn dữ liệu

RSocket có flow control dựa trên REQUEST_N. Client cho biết số payload mà nó sẵn sàng nhận; server phát dữ liệu theo credit và demand. Trong Spring, publisher reactive được nối với interaction để demand có thể truyền ngược qua pipeline.

~~~mermaid
flowchart LR
    A["Client xử lý chậm"] --> B["Giảm demand / REQUEST_N"]
    B --> C["RSocket response stream"]
    C --> D["Flux upstream nhận demand"]
    D --> E["Reactive source đọc theo nhu cầu"]
~~~

Nếu nguồn là R2DBC, WebClient hoặc một Publisher tuân thủ Reactive Streams, demand có thể được truyền về upstream. Điều này giúp hạn chế việc đọc dữ liệu vượt quá khả năng tiêu thụ.

Một số operator hữu ích:

| Operator | Tác dụng | Lưu ý |
|---|---|---|
| limitRate(n) | Chia nhỏ request demand upstream | Không thay thế giới hạn tài nguyên nguồn |
| onBackpressureBuffer(n) | Buffer tối đa n phần tử | Phải xử lý overflow |
| onBackpressureDrop() | Bỏ phần tử khi downstream không theo kịp | Chỉ phù hợp nếu được phép mất dữ liệu |
| onBackpressureLatest() | Giữ giá trị mới nhất | Phù hợp trạng thái, không phù hợp event cần đầy đủ |
| publishOn(scheduler, prefetch) | Chuyển scheduler và tạo hàng đợi prefetch | Tăng queue và bộ nhớ cần quản lý |

Ví dụ buffer có giới hạn:

~~~java
Flux<ReadingEvent> bounded = source
    .onBackpressureBuffer(
        256,
        dropped -> metrics.bufferOverflow(dropped)
    );
~~~

Nếu buffer đầy, callback overflow được gọi. Ứng dụng cần quyết định có phát lỗi, ghi dead-letter, drop hay dừng nguồn. Với dữ liệu nghiệp vụ không được mất, không nên chọn DROP hoặc LATEST chỉ để tránh lỗi quá tải.

### Backpressure không thể sửa một nguồn không chịu điều tiết

Một callback API có thể đẩy dữ liệu bất kể subscriber có demand hay không. Trong trường hợp đó, Reactor phải buffer hoặc áp dụng overflow policy. Muốn thực sự điều tiết nguồn, adapter cần gọi pause/resume hoặc request(n) trên API nguồn nếu có.

Không nên thêm publishOn với prefetch lớn ở mọi tầng. Mỗi hàng đợi làm tăng tổng số phần tử có thể nằm trong bộ nhớ. Hãy tính tổng buffer của nguồn, operator, transport và consumer.

## 9. Cancellation và vòng đời nguồn

Khi client hủy request-stream, subscription phía server bị cancel. Cancellation cần truyền tới nguồn để dừng truy vấn, hủy listener hoặc ngừng đọc từ broker nếu subscription chỉ phục vụ interaction đó.

Ví dụ quan sát vòng đời:

~~~java
@MessageMapping("sensor.live")
Flux<ReadingEvent> live(@Payload SensorQuery query) {
    return Flux.defer(() -> telemetrySource.open(query.sensorId()))
        .doOnSubscribe(subscription ->
            metrics.streamOpened(query.sensorId()))
        .doOnCancel(() ->
            metrics.streamCancelled(query.sensorId()))
        .doFinally(signal ->
            metrics.streamTerminated(query.sensorId(), signal));
}
~~~

doOnCancel và doFinally phù hợp cho metrics và logging. Nếu nguồn sở hữu resource như file, cursor hoặc listener cần đóng, hãy gắn resource vào publisher bằng using/usingWhen hoặc bảo đảm adapter đăng ký cleanup qua onDispose.

Với tài nguyên đồng bộ:

~~~java
Flux<Reading> readings = Flux.using(
    () -> legacySource.openCursor(sensorId),
    cursor -> cursor.readAll(),
    ReadingCursor::close
);
~~~

Với cleanup bất đồng bộ, dùng usingWhen và cung cấp cleanup publisher tương ứng cho complete, error và cancel. Không dùng doFinally để khởi chạy một thao tác cleanup bất đồng bộ rồi giả định Reactor sẽ chờ nó hoàn tất.

Không tự gọi subscribe trong @MessageMapping. Nếu handler subscribe thủ công, pipeline đó có lifecycle riêng và có thể tiếp tục chạy sau khi client hủy stream. Hãy trả Flux trực tiếp để framework sở hữu subscription.

## 10. Xử lý lỗi của nguồn dữ liệu

Lỗi ở nguồn upstream sẽ kết thúc request-stream bằng error nếu không được xử lý. Các nguồn lỗi có thể gồm timeout database, HTTP 5xx, broker disconnect, lỗi giải mã hoặc callback adapter phát lỗi.

Có thể chuyển lỗi kỹ thuật thành lỗi miền:

~~~java
Flux<ReadingEvent> stream = source
    .map(this::toEvent)
    .onErrorMap(error ->
        new ReadingStreamException(
            "Reading source failed",
            error
        )
    );
~~~

Nếu có fallback phù hợp, dùng onErrorResume có chủ đích:

~~~java
Flux<ReadingEvent> stream = primarySource()
    .onErrorResume(error -> {
        if (isTemporary(error)) {
            return fallbackSource();
        }
        return Flux.error(error);
    });
~~~

Không dùng onErrorComplete để che giấu lỗi nếu client cần biết stream đã dừng bất thường. Nếu retry, hãy xem xét việc subscribe lại có tạo truy vấn từ đầu hay phát lại event đã gửi trước đó không. Nguồn cần cursor hoặc offset nếu không muốn lặp dữ liệu khi retry.

Với stream dài hạn, cần timeout, keepalive và reconnect policy ở phía client. Reconnect có thể tạo interaction mới; muốn tiếp tục chính xác cần cursor/checkpoint theo hợp đồng ứng dụng. Không giả định một Flux lỗi sẽ tự nối lại chỉ vì transport có khả năng Resume.

## 11. Kiểm soát subscription và chia sẻ dữ liệu an toàn

Mỗi request-stream là một subscription có vòng đời riêng. Nếu route được nhiều client gọi đồng thời, cần xác định dữ liệu được tạo riêng hay chia sẻ.

- Với cold source, mỗi request có thể chạy query riêng. Cần giới hạn số subscription và tải database.
- Với hot source, nhiều request có thể cùng nhận một nguồn. Cần lọc theo principal và query trước khi gửi dữ liệu.
- Với nguồn toàn cục, không để một client hủy subscription làm dispose toàn bộ event bus.
- Với nguồn theo session, hãy đóng resource khi connection hoặc interaction kết thúc.
- Với nguồn có chi phí cao, có thể chia sẻ upstream nhưng vẫn phải giữ filter, authorization và backpressure phù hợp cho từng subscriber.

Không dùng cache hoặc share một cách tùy tiện. cache có thể giữ dữ liệu cũ và replay cho subscriber mới; share/refCount có thể làm upstream bị dispose khi subscriber cuối cùng rời đi. Chọn operator theo semantics mong muốn và kiểm tra hành vi khi subscriber đầu tiên/cuối cùng kết nối.

Mọi filter theo tenant, sensor hoặc người dùng phải được kiểm tra phía server. Không chỉ tin giá trị sensorId trong request nếu người gọi không có quyền xem sensor đó.

## 12. Client tiêu thụ request-stream

Client nhận nhiều response bằng retrieveFlux:

~~~java
Flux<ReadingEvent> stream = requester
    .route("sensor.readings")
    .data(new SensorQuery(
        "sensor-01",
        Instant.now().minus(Duration.ofMinutes(5)),
        Instant.now()
    ))
    .retrieveFlux(ReadingEvent.class);
~~~

Có thể subscribe để hiển thị hoặc xử lý dữ liệu:

~~~java
Disposable subscription = stream.subscribe(
    event -> dashboard.update(event),
    error -> dashboard.showError(error),
    () -> dashboard.showCompleted()
);
~~~

Khi người dùng rời màn hình hoặc component bị đóng, dispose subscription:

~~~java
subscription.dispose();
~~~

Trong ứng dụng reactive end-to-end, ưu tiên compose Flux thay vì subscribe sớm. Ví dụ service có thể trả stream cho tầng cao hơn; chỉ thành phần sở hữu lifecycle UI hoặc worker mới subscribe và giữ Disposable để hủy.

Nếu consumer xử lý chậm, demand giảm và backpressure có thể truyền về server. Nếu consumer làm tác dụng phụ bất đồng bộ, hãy nối thao tác đó vào pipeline bằng concatMap hoặc flatMap với concurrency giới hạn; không gọi một tác vụ async fire-and-forget trong onNext rồi coi như đã xử lý xong.

## 13. Kiểm thử chuyển đổi nguồn thành request-stream

Nên kiểm tra pipeline nguồn trước, sau đó kiểm tra route RSocket với transport test.

### Unit test với TestPublisher và StepVerifier

~~~java
@Test
void mapsReactiveSourceIntoReadingEventsAndPropagatesCancel() {
    TestPublisher<Reading> source = TestPublisher.create();

    Flux<ReadingEvent> result = source.flux()
        .map(reading -> new ReadingEvent(
            reading.sensorId(),
            reading.sequence(),
            reading.observedAt(),
            reading.temperature()
        ));

    StepVerifier.create(result)
        .then(() -> source.next(sampleReading(1)))
        .expectNextMatches(event -> event.sequence() == 1)
        .thenCancel()
        .verify();

    source.assertCancelled();
}
~~~

Test này kiểm tra mapping và cancellation được truyền về publisher. Có thể bổ sung test lỗi bằng TestPublisher.error(...) và test demand bằng StepVerifier với initial request giới hạn.

### Kiểm thử route RSocket

Một integration test nên khởi động responder và requester qua transport thử nghiệm, rồi gọi route:

~~~java
StepVerifier.create(
    requester.route("sensor.readings")
        .data(new SensorQuery("sensor-01", from, to))
        .retrieveFlux(ReadingEvent.class)
)
.expectNextMatches(event ->
    event.sensorId().equals("sensor-01"))
.expectNextCount(2)
.verifyComplete();
~~~

Các trường hợp nên có:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Nguồn phát 3 phần tử | Client nhận đủ 3 payload rồi complete |
| Nguồn rỗng | Stream complete mà không phát payload |
| Nguồn phát lỗi | Client nhận lỗi tương ứng |
| Client cancel sau vài payload | Nguồn upstream nhận cancellation |
| Client demand thấp | Nguồn không bị đọc vượt quá chính sách |
| Nhiều client đồng thời | Cold/hot semantics đúng như thiết kế |
| Client không có quyền | Server từ chối trước khi mở nguồn |
| Nguồn callback quá nhanh | Overflow policy được thực thi và có metrics |

Đối với nguồn hot, hãy kiểm thử subscriber đến muộn, subscriber chậm và trường hợp không có subscriber. Đối với callback adapter, kiểm tra listener được gỡ khi cancel và khi nguồn complete/error.

## 14. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi subscribe trong @MessageMapping | Nguồn chạy tách khỏi request lifecycle | Trả Flux trực tiếp |
| Dùng request-stream cho nhiều request đầu vào | Sai interaction model | Dùng request-channel |
| Nghĩ query database tự phát live update | Stream kết thúc sau tập kết quả hiện có | Dùng change feed, broker hoặc event source |
| Dùng hot source nhưng không định nghĩa fan-out | Client có thể không nhận đúng tập event | Chọn multicast/broadcast và consumer group rõ ràng |
| Dùng buffer vô hạn | Bộ nhớ tăng khi client chậm | Buffer giới hạn và overflow policy |
| Chỉ dùng REQUEST_N như application ACK | Nhầm demand với xử lý nghiệp vụ | Dùng ACK/checkpoint riêng nếu cần |
| Commit Kafka khi mới emit payload | Có thể mất event trước khi client commit | Quản lý offset theo hợp đồng xử lý |
| Không dọn listener khi cancel | Rò rỉ listener và tiếp tục nhận event | Dùng onDispose/using |
| Retry stream từ đầu | Phát lặp dữ liệu đã gửi | Tiếp tục từ cursor/offset đã xác nhận |
| Dùng onErrorComplete để ẩn lỗi | Client tưởng stream hoàn tất bình thường | Trả lỗi hoặc fallback có hợp đồng |
| Chia sẻ Flux giữa nhiều tenant mà lọc sai chỗ | Rò rỉ dữ liệu giữa client | Xác thực và filter theo principal ở server |
| Không giới hạn concurrency khi xử lý event | Tăng tải và làm checkpoint sai thứ tự | Giới hạn concurrency, giữ thứ tự theo partition |

## Kết luận

Chuyển nguồn dữ liệu reactive thành request-stream chủ yếu là giữ Publisher xuyên suốt pipeline và để RSocket quản lý việc phát response theo demand. Một route Spring có thể nhận một query, gọi repository, WebClient, Kafka hoặc callback adapter rồi trả Flux DTO. Client dùng retrieveFlux để tiêu thụ các payload.

Hãy phân biệt cold source và hot source trước khi chia sẻ stream; chuyển entity thành DTO; xác định chính sách backpressure cho nguồn không thể điều tiết; truyền cancellation tới database, broker hoặc listener; và xử lý lỗi theo hợp đồng rõ ràng. Không subscribe hoặc block bên trong handler. Kiểm thử cả dữ liệu, demand, lỗi, nhiều subscriber và cancellation để bảo đảm request-stream phản ánh đúng lifecycle của nguồn dữ liệu.

## Tài liệu tham khảo

- [Spring Framework — RSocket Messaging](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket Protocol — Request Stream và Flow Control](https://rsocket.io/about/protocol/)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring Data R2DBC — Reactive Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
- [Spring WebClient — Reactive HTTP Client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Reactor Kafka](https://projectreactor.io/docs/kafka/release/reference/)
