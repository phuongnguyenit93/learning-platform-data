# Xác nhận, checkpoint và phát lại dữ liệu ở tầng ứng dụng

## Bối cảnh: nhận được payload chưa có nghĩa nghiệp vụ đã xử lý xong

RSocket cung cấp giao tiếp hai chiều và reactive. Một server có thể mở request-stream để gửi sự kiện tới client; client có thể đồng thời gửi request-response ngược trên cùng kết nối để xác nhận những sự kiện đã xử lý. Cách này phù hợp với telemetry, đồng bộ trạng thái thiết bị, thông báo đơn hàng, luồng thay đổi dữ liệu và các nghiệp vụ cần tiếp tục sau khi kết nối bị gián đoạn.

Tuy nhiên, một payload đã được gửi qua mạng chưa chắc đã được ứng dụng xử lý bền vững. Client có thể nhận payload vào bộ nhớ rồi crash trước khi ghi database. Hoặc client đã commit dữ liệu nhưng phản hồi ACK bị mất trên đường về server. Khi reconnect, server cần biết nên phát lại từ đâu; client cần có khả năng nhận diện sự kiện đã xử lý để không lặp tác dụng phụ.

Ba khái niệm giúp giải quyết bài toán này:

- **Xác nhận (ACK):** client thông báo đã xử lý một sự kiện tới một mức được quy định, thường là đã commit kết quả nghiệp vụ.
- **Checkpoint:** vị trí bền vững mà consumer xác nhận đã xử lý liên tục, thường là sequence hoặc offset theo partition.
- **Replay:** server phát lại dữ liệu từ checkpoint đã lưu khi client đăng ký lại hoặc khôi phục sau gián đoạn.

Đây là giao thức ở tầng ứng dụng. RSocket flow control, REQUEST_N, transport delivery và session Resume hỗ trợ truyền dữ liệu, nhưng không tự bảo đảm database của client đã commit. Bài học này trình bày cách thiết kế ACK, checkpoint, replay, deduplication và kiểm thử để dữ liệu không bị mất khi hệ thống gặp lỗi.

## 1. Phân biệt flow control, transport delivery và ACK nghiệp vụ

Một nhầm lẫn phổ biến là xem việc server gửi được payload hoặc client cấp thêm demand là xác nhận nghiệp vụ. Các cơ chế này có mục tiêu khác nhau:

| Cơ chế | Ý nghĩa | Không bảo đảm điều gì |
|---|---|---|
| RSocket REQUEST_N | Client cho phép server gửi thêm số payload theo nhu cầu | Client đã lưu hoặc xử lý payload |
| PAYLOAD / response frame | Dữ liệu được truyền qua interaction | Tác dụng phụ nghiệp vụ đã commit |
| RSocket Resume | Khôi phục session và trao đổi lại frame cần thiết trong phạm vi trạng thái resume | Consumer đã commit event vào database |
| Application ACK | Consumer xác nhận theo hợp đồng nghiệp vụ | Không tự tạo exactly-once xuyên nhiều hệ thống |
| Application checkpoint | Lưu vị trí consumer đã xử lý liên tục | Không thay thế event log hoặc chính sách retention |

Ví dụ client gửi REQUEST_N(10). Điều đó có nghĩa client cho phép server gửi tối đa 10 payload theo credit hiện có. Nó không có nghĩa client đã xử lý thành công 10 sự kiện trước đó.

Tương tự, khi server nhận được tín hiệu transport hoặc session cho biết frame đã được trao đổi, server không thể suy ra rằng client đã ghi dữ liệu vào database. Nếu cần biết điều đó, client phải gửi ACK ở tầng ứng dụng sau khi hoàn thành bước xử lý mà hợp đồng yêu cầu.

~~~mermaid
sequenceDiagram
    participant S as Event Server
    participant C as Consumer
    participant DB as Consumer Database
    S->>C: REQUEST_STREAM / PAYLOAD event 104
    C->>DB: Xử lý và commit event 104
    DB-->>C: Commit thành công
    C->>S: REQUEST_RESPONSE events.ack(offset=104)
    S->>S: Lưu checkpoint 104
    S-->>C: ACK_ACCEPTED
~~~

Thứ tự quan trọng: client commit xử lý trước, sau đó mới gửi ACK. Nếu gửi ACK trước rồi crash trước khi commit, server có thể bỏ qua event mà client chưa xử lý.

## 2. Xác định đơn vị dữ liệu và vị trí checkpoint

Trước khi thiết kế ACK, cần xác định dữ liệu được sắp thứ tự theo đơn vị nào. Một hệ thống có thể phát event từ nhiều thiết bị hoặc nhiều partition. Sequence của hai partition không thể so sánh trực tiếp.

Một event envelope có thể gồm:

~~~java
public record EventEnvelope<T>(
    String eventId,
    String partition,
    long offset,
    int schemaVersion,
    Instant occurredAt,
    T data
) {}
~~~

Các trường có ý nghĩa:

- **eventId:** định danh ổn định của sự kiện, dùng cho deduplication.
- **partition:** phạm vi sắp thứ tự độc lập, ví dụ device ID hoặc partition của event log.
- **offset:** vị trí tăng đơn điệu trong partition.
- **schemaVersion:** phiên bản cấu trúc dữ liệu để consumer giải mã đúng cách.
- **occurredAt:** thời điểm nghiệp vụ xảy ra; không nên dùng riêng timestamp làm checkpoint.
- **data:** payload nghiệp vụ.

Một checkpoint có thể được biểu diễn như sau:

~~~java
public record ConsumerCheckpoint(
    String consumerId,
    String partition,
    long committedOffset,
    Instant updatedAt
) {}
~~~

Khóa checkpoint nên bao gồm consumer và partition. Nếu có hai consumer độc lập cùng đọc một event log, checkpoint của consumer A không được làm consumer B bỏ qua dữ liệu.

### Không dùng một offset toàn cục cho nhiều partition

Giả sử partition device-01 đã xử lý đến offset 105, còn device-02 mới xử lý đến offset 98. Checkpoint phải lưu hai vị trí riêng:

| Consumer | Partition | Checkpoint |
|---|---|---:|
| dashboard-ops | device-01 | 105 |
| dashboard-ops | device-02 | 98 |

Không thể lấy giá trị lớn nhất là 105 rồi coi mọi partition đều đã xử lý tới 105. Cách đó sẽ bỏ qua dữ liệu chưa được xử lý của device-02.

Nếu nguồn có nhiều partition, subscription request có thể mang tập checkpoint hoặc server tự đọc checkpoint đã lưu cho consumer. Server phải xác thực consumerId thuộc về principal hiện tại, không tin giá trị client tự khai báo.

### Offset và sequence phải có quy ước rõ ràng

Nếu offset bắt đầu từ 0, ACK offset 104 có thể mang nghĩa consumer đã xử lý event tại offset 104. Nếu API dùng nextOffset, giá trị 105 có thể mang nghĩa event tiếp theo cần đọc. Hai quy ước đều có thể dùng, nhưng không được trộn lẫn.

Trong bài này, ACK mang **committedOffset**, nghĩa là offset lớn nhất đã xử lý liên tục và bền vững. Khi đăng ký lại, server đọc event có offset lớn hơn committedOffset.

Nếu consumer lọc event từ một log có offset toàn cục, các offset nhìn thấy có thể không liền nhau vì một số bản ghi đã bị lọc có chủ đích. Khi đó, checkpoint phải biểu diễn vị trí log đã quét và đánh giá xong, không chỉ là offset của event cuối cùng được chuyển cho handler. Event store cần cho consumer biết ranh giới scan đã hoàn tất; không coi mọi khoảng trống số học là event bị mất.

## 3. ACK cần xác nhận mức xử lý nào?

Một ACK cần có ngữ nghĩa cụ thể. Có thể chia thành các mức:

| Mức xác nhận | Consumer đã làm gì? | Khi nào dùng |
|---|---|---|
| RECEIVED | Đã nhận payload vào ứng dụng | Chẩn đoán hoặc đo thời gian nhận; không đủ cho độ tin cậy nghiệp vụ |
| VALIDATED | Đã kiểm tra schema và quy tắc đầu vào | Pipeline có bước xác thực riêng |
| COMMITTED | Đã commit thay đổi nghiệp vụ và dấu vết xử lý bền vững | Mức thường dùng để tiến checkpoint |
| COMPLETED | Đã hoàn tất cả tác vụ bên ngoài theo hợp đồng | Workflow có nhiều bước và cần xác nhận kết quả cuối |

Không nên dùng ACK_RECEIVED để xóa event khỏi retention nếu consumer chỉ mới đưa dữ liệu vào một queue trong bộ nhớ. Nếu process crash trước khi queue được ghi bền vững, event có thể bị mất.

Với luồng đồng bộ nghiệp vụ, một ACK COMMITTED thường có nghĩa:

1. Consumer đã xác thực event.
2. Consumer đã áp dụng thay đổi cần thiết.
3. Consumer đã lưu event ID hoặc idempotency record.
4. Consumer đã cập nhật local checkpoint trong cùng transaction nếu dùng chung database.
5. Sau commit, consumer mới gửi ACK về server.

ACK không nên chỉ là một thông báo log. Nó là một phần của hợp đồng giữa producer và consumer.

### ACK response cũng cần có ngữ nghĩa

Server trả ACK_ACCEPTED khi checkpoint đã được lưu bền vững. Nếu server chỉ nhận request nhưng chưa commit checkpoint, response không nên tuyên bố đã lưu thành công.

Ví dụ:

~~~java
public record EventAck(
    String consumerId,
    String partition,
    long committedOffset,
    String eventId
) {}

public record AckResult(
    String status,
    long storedOffset
) {}
~~~

ACK lặp lại cùng offset cần an toàn. Nếu server đã lưu offset 104, client gửi lại ACK 104 do response trước bị mất, server nên trả kết quả đã lưu thay vì coi đó là lỗi làm hỏng trạng thái.

## 4. Lưu checkpoint phía server và phía consumer

Trong nhiều hệ thống, cả server và consumer đều cần lưu trạng thái:

- **Consumer local checkpoint:** cho biết database nghiệp vụ của consumer đã xử lý đến đâu.
- **Server acknowledged checkpoint:** cho biết producer/server có thể bắt đầu replay từ đâu và có thể dùng cho retention hoặc quản lý subscription.

Hai checkpoint có thể lệch nhau trong một khoảng ngắn. Ví dụ consumer commit local offset 104, sau đó request ACK bị mất. Local checkpoint là 104 nhưng server vẫn lưu 103. Khi reconnect, server phát lại event 104. Consumer nhận ra event này đã được commit và gửi lại ACK 104.

Đây là hành vi bình thường. Hệ thống phải thiết kế để chịu được duplicate delivery.

### Bảng checkpoint phía server

Một schema đơn giản:

| Cột | Ý nghĩa |
|---|---|
| consumer_id | Danh tính consumer hoặc subscription |
| partition_id | Partition đang đọc |
| committed_offset | Offset được consumer xác nhận |
| updated_at | Thời điểm checkpoint được cập nhật |
| version | Version dùng cho optimistic locking nếu cần |

Tạo unique constraint trên cặp consumer_id và partition_id. Việc cập nhật cần transaction hoặc compare-and-set để tránh hai request ACK đồng thời ghi đè checkpoint theo thứ tự sai.

### Bảng xử lý phía consumer

Consumer có thể lưu dấu vết event đã xử lý:

| Cột | Ý nghĩa |
|---|---|
| consumer_id | Consumer sở hữu xử lý |
| event_id | ID ổn định của event |
| partition_id | Partition nguồn |
| offset | Vị trí event |
| processed_at | Thời điểm commit |
| result_reference | Tham chiếu kết quả nếu cần |

Đặt unique constraint trên consumer_id và event_id hoặc khóa phù hợp với nghiệp vụ. Nếu event được gửi lại, consumer kiểm tra dấu vết đã xử lý và bỏ qua tác dụng phụ lặp, sau đó vẫn có thể gửi lại ACK.

## 5. Trình tự xử lý an toàn: commit trước, ACK sau

Một quy trình at-least-once thường có trình tự:

~~~mermaid
flowchart TD
    A["Nhận EventEnvelope"] --> B["Kiểm tra schema và quyền"]
    B --> C{"Event ID đã xử lý?"}
    C -->|Đã xử lý| H["Không lặp tác dụng phụ"]
    C -->|Chưa| D["Mở transaction local"]
    D --> E["Áp dụng thay đổi nghiệp vụ"]
    E --> F["Lưu processed event và checkpoint local"]
    F --> G["Commit transaction"]
    G --> H
    H --> I["Gửi application ACK"]
    I --> J["Server commit checkpoint"]
    J --> K["ACK_ACCEPTED"]
~~~

Điểm quyết định là bước commit local phải hoàn tất trước khi gửi application ACK. Nếu ACK response bị mất, event có thể được replay, nhưng consumer deduplicate bằng event ID.

### Ví dụ consumer xử lý idempotent

~~~java
@Service
class ReadingConsumer {

    private final ProcessedEventRepository processedEvents;
    private final ReadingRepository readings;
    private final LocalCheckpointRepository checkpoints;

    ReadingConsumer(
            ProcessedEventRepository processedEvents,
            ReadingRepository readings,
            LocalCheckpointRepository checkpoints) {
        this.processedEvents = processedEvents;
        this.readings = readings;
        this.checkpoints = checkpoints;
    }

    @Transactional
    public Mono<Void> processOnce(EventEnvelope<Reading> event) {
        return processedEvents.insertIfAbsent(
                "dashboard-ops",
                event.eventId(),
                event.partition(),
                event.offset()
            )
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }

                return readings.apply(event.data())
                    .then(checkpoints.advance(
                        "dashboard-ops",
                        event.partition(),
                        event.offset()
                    ));
            });
    }
}
~~~

Đây là phác thảo cho reactive repository. insertIfAbsent cần dựa trên unique constraint hoặc câu lệnh upsert có tính nguyên tử. Transaction phải bao trùm dấu vết processed event, thay đổi nghiệp vụ và checkpoint local. Nếu dùng Spring reactive transaction, các thao tác repository phải tham gia cùng reactive transaction context; không trộn lẫn JDBC blocking transaction với R2DBC rồi giả định chúng commit nguyên tử.

Với event đã tồn tại, consumer không áp dụng lại tác dụng phụ. Tuy nhiên, consumer vẫn phải xác nhận rằng event đó thuộc cùng consumer và cùng nội dung/ID theo hợp đồng. Không dùng một event ID có thể bị tái sử dụng cho payload khác.

## 6. Gửi application ACK bằng RSocketRequester

Client nhận một request-stream từ server và gửi ACK bằng một request-response riêng trên cùng kết nối. Hai interaction có thể hoạt động đồng thời vì RSocket là hai chiều và hỗ trợ nhiều stream trên một connection.

Ví dụ client:

~~~java
Flux<EventEnvelope<Reading>> events = requester
    .route("events.subscribe")
    .data(new SubscriptionRequest("dashboard-ops"))
    .retrieveFlux(
        new ParameterizedTypeReference<EventEnvelope<Reading>>() {}
    );

Flux<AckResult> acknowledgements = events.concatMap(event ->
    readingConsumer.processOnce(event)
        .then(Mono.defer(() ->
            requester.route("events.ack")
                .data(new EventAck(
                    "dashboard-ops",
                    event.partition(),
                    event.offset(),
                    event.eventId()
                ))
                .retrieveMono(AckResult.class)
        )),
    1
);
~~~

Đoạn code thể hiện thứ tự:

1. Nhận event từ request-stream.
2. Gọi processOnce và chờ transaction local hoàn tất.
3. Gửi request-response tới route events.ack.
4. Chờ server trả ACK result.
5. Tiếp tục xử lý phần tử tiếp theo.

concatMap với prefetch 1 giữ một luồng xử lý tuần tự và hạn chế số event được yêu cầu trước. Nếu cần throughput cao hơn, có thể dùng xử lý song song có giới hạn, nhưng checkpoint phải chỉ tiến qua offset liên tục đã commit. Không dùng giá trị offset lớn nhất vừa hoàn tất nếu còn event trước đó đang xử lý.

Trong ứng dụng thật, cần giữ subscription trong lifecycle component, xử lý lỗi và reconnect, cũng như quản lý dispose khi consumer dừng. Ví dụ trên minh họa pipeline chứ chưa phải một reconnect supervisor hoàn chỉnh.

## 7. Server phát lại từ checkpoint

Server cung cấp route đăng ký stream và route nhận ACK. Một cách tổ chức đơn giản:

~~~java
@Controller
class EventStreamController {

    private final EventLog eventLog;
    private final CheckpointStore checkpointStore;
    private final AckService ackService;

    EventStreamController(
            EventLog eventLog,
            CheckpointStore checkpointStore,
            AckService ackService) {
        this.eventLog = eventLog;
        this.checkpointStore = checkpointStore;
        this.ackService = ackService;
    }

    @MessageMapping("events.subscribe")
    Flux<EventEnvelope<Reading>> subscribe(
            @Payload SubscriptionRequest request) {
        return checkpointStore.loadAll(request.consumerId())
            .flatMapMany(checkpoints ->
                eventLog.streamAfter(request.consumerId(), checkpoints)
            );
    }

    @MessageMapping("events.ack")
    Mono<AckResult> acknowledge(@Payload EventAck ack) {
        return ackService.acknowledge(ack);
    }
}
~~~

Đây là skeleton minh họa. Trong triển khai thật, service phải lấy consumer identity từ Authentication đã xác thực và kiểm tra quyền đọc event cũng như quyền cập nhật checkpoint. Không tin consumerId trong payload nếu caller có thể tự đổi giá trị.

Server đọc checkpoint đã lưu và yêu cầu event log phát các event có offset lớn hơn checkpoint tương ứng. Nếu client chưa gửi ACK cuối cùng, server sẽ phát lại event đó sau reconnect.

### Đảm bảo không có khoảng trống giữa replay và live stream

Một lỗi tinh vi xảy ra khi server đọc hết lịch sử rồi mới đăng ký nguồn event live:

1. Server đọc lịch sử đến offset 200.
2. Event 201 được ghi vào log.
3. Server đăng ký listener live sau đó.
4. Event 201 không nằm trong kết quả lịch sử và cũng đã phát trước khi listener được gắn.

Client bị mất event dù replay và live stream đều hoạt động.

Nguồn event cần cung cấp thao tác tail có ranh giới nhất quán. Một cách là:

1. Đọc high-watermark H của partition.
2. Replay các event từ checkpoint + 1 đến H.
3. Tiếp tục đọc từ H + 1 trên cùng log hoặc change feed không có khoảng trống.

Nếu event store hỗ trợ một thao tác subscribe-from-offset nguyên tử, hãy dùng thao tác đó. Không ghép lịch sử và live bằng hai nguồn độc lập mà không có cursor/handoff nhất quán.

## 8. ACK tích lũy và xử lý event ngoài thứ tự

Có hai cách xác nhận phổ biến:

- **ACK từng event:** client gửi xác nhận cho mỗi event ID hoặc offset.
- **Checkpoint tích lũy:** client xác nhận offset lớn nhất mà mọi event trước đó trong partition đã được xử lý liên tục.

Checkpoint tích lũy giảm số request ACK, nhưng chỉ an toàn nếu consumer giữ được thứ tự hoàn tất.

Ví dụ client nhận offset 10, 11, 12 và xử lý song song. Offset 12 hoàn tất trước, 10 và 11 vẫn đang chạy. Nếu client ACK 12 ngay, server có thể bỏ qua 10 và 11 khi replay. Điều này làm mất dữ liệu.

Với xử lý song song, consumer cần theo dõi các offset đã commit và chỉ tiến checkpoint qua chuỗi liên tục:

| Offset | Trạng thái |
|---:|---|
| 10 | Đã commit |
| 11 | Đang xử lý |
| 12 | Đã commit |

Checkpoint vẫn là 10 vì còn khoảng trống ở 11. Khi 11 commit, checkpoint mới có thể nhảy lên 12.

Với hệ thống đơn giản, concatMap tuần tự trên từng partition giúp tránh vấn đề này. Nếu cần concurrency, có thể xử lý song song giữa các partition nhưng vẫn tuần tự trong một partition.

### Kiểm tra ACK ở server

Server nên kiểm tra:

- Consumer có quyền xác nhận partition này không?
- Offset ACK có thuộc phạm vi event đã phát cho subscription không?
- Offset có vượt high-watermark đã gửi không?
- ACK có lùi checkpoint không?
- Có khoảng trống chưa xác nhận trong chế độ cumulative không?
- Event ID có khớp offset nếu ACK theo từng event không?

ACK lặp lại offset cũ có thể trả kết quả hiện tại. ACK tiến vượt qua dữ liệu chưa được phát hoặc vượt qua khoảng trống phải bị từ chối.

## 9. Batch ACK và cửa sổ xử lý

Gửi ACK từng event tạo thêm request-response. Với throughput cao, client có thể xác nhận theo batch hoặc theo thời gian:

- ACK sau mỗi N event.
- ACK sau một khoảng thời gian ngắn nếu có event mới.
- ACK khi đạt cả ngưỡng số lượng hoặc thời gian.
- ACK theo từng partition và offset liên tục.

Batch ACK giảm overhead nhưng tăng số event có thể phải replay khi client hoặc mạng gặp lỗi. Nếu client đã commit 100 event nhưng mới ACK đến 90, server có thể phát lại 91-100. Consumer phải deduplicate các event đó.

Một cửa sổ xử lý giới hạn số event chưa được ACK giúp cân bằng throughput và bộ nhớ:

~~~mermaid
flowchart LR
    A["Event log"] --> B["Cửa sổ tối đa N event"]
    B --> C["Consumer xử lý và commit"]
    C --> D["ACK checkpoint liên tục"]
    D --> E["Mở chỗ cho event tiếp theo"]
~~~

Cửa sổ này bổ sung cho RSocket backpressure. REQUEST_N giới hạn số payload được gửi theo nhu cầu giao thức; application ACK giới hạn số event mà nghiệp vụ chưa xác nhận. Có thể cấu hình hai giới hạn khác nhau nhưng cần tránh để hàng đợi chưa ACK tăng vô hạn.

## 10. Replay, duplicate và effectively-once

Replay có nghĩa server có thể phát lại event mà consumer chưa xác nhận. Vì ACK có thể bị mất sau khi consumer commit, duplicate delivery là điều bình thường.

Không nên tuyên bố hệ thống có exactly-once chỉ vì có ACK và checkpoint. Trên mạng phân tán, client có thể commit nhưng server không biết; server có thể phát lại event. Mục tiêu thực tế thường là:

- Server phát event theo at-least-once.
- Consumer xử lý idempotent theo event ID.
- Consumer commit dữ liệu nghiệp vụ và processed marker cùng transaction.
- Server chỉ tiến checkpoint sau application ACK.
- Replay duplicate không tạo tác dụng phụ lặp.

Đây thường được gọi là effectively-once business effect trong phạm vi các transaction và hệ thống đã được thiết kế để khử trùng lặp. Nếu consumer gọi hệ thống bên ngoài, cần thêm idempotency key ở downstream, outbox/inbox hoặc đối soát.

### Xử lý ACK bị mất

Giả sử consumer đã commit event 104 nhưng ACK bị mất:

1. Local database đã lưu event 104 và checkpoint local.
2. Server vẫn giữ checkpoint 103.
3. Client reconnect.
4. Server replay event 104.
5. Consumer thấy event ID đã được xử lý, không áp dụng tác dụng phụ lần nữa.
6. Consumer gửi lại ACK 104.
7. Server lưu checkpoint 104.

### Xử lý crash trước khi commit

Nếu consumer nhận event 104 nhưng crash trước khi transaction local commit:

1. Server chưa nhận ACK 104.
2. Local database không có processed marker của event 104.
3. Client reconnect và server replay event 104.
4. Consumer xử lý và commit bình thường.
5. Consumer gửi ACK 104.

### Không ACK trước khi commit

Nếu consumer gửi ACK 104 trước, server lưu checkpoint 104, sau đó consumer crash trước khi ghi dữ liệu nghiệp vụ, server có thể bắt đầu replay từ 105. Event 104 đã bị bỏ qua vĩnh viễn theo checkpoint đó. Đây là lỗi thứ tự nghiêm trọng.

## 11. Retention và checkpoint hết hạn

Event log thường chỉ giữ dữ liệu trong một khoảng thời gian hoặc dung lượng nhất định. Nếu consumer offline quá lâu, checkpoint có thể cũ hơn event đầu tiên còn được giữ.

Server cần phát hiện tình huống này thay vì âm thầm bắt đầu từ event mới nhất. Có thể trả trạng thái nghiệp vụ:

~~~java
public record SubscriptionStatus(
    String status,
    String partition,
    long requestedOffset,
    long earliestAvailableOffset,
    long latestAvailableOffset
) {}
~~~

Nếu checkpoint không còn nằm trong retention, server trả trạng thái RESYNC_REQUIRED hoặc một lỗi miền tương đương. Client khi đó cần lấy snapshot hiện tại, lưu snapshot cùng high-watermark nhất quán, rồi đăng ký stream từ offset tiếp theo.

Một quy trình resync:

1. Client yêu cầu snapshot cho phạm vi dữ liệu.
2. Server trả snapshot cùng high-watermark H.
3. Client lưu snapshot bền vững.
4. Client đặt checkpoint local ở H trong cùng transaction với snapshot.
5. Client gửi ACK/checkpoint H theo hợp đồng.
6. Client đăng ký lại stream từ H + 1.

Snapshot và H phải đại diện cùng một ranh giới dữ liệu. Nếu snapshot được đọc trước rồi high-watermark lấy sau, event phát sinh giữa hai thao tác có thể bị bỏ sót.

## 12. Event lỗi, poison message và retry

Không phải event nào cũng xử lý thành công. Một event có thể sai schema, thiếu dữ liệu, vi phạm quy tắc nghiệp vụ hoặc gọi dependency đang lỗi.

Cần phân loại:

| Loại lỗi | Hành vi đề xuất |
|---|---|
| Lỗi tạm thời như timeout database | Retry có backoff và giới hạn |
| Dependency quá tải | Giảm concurrency, backoff, circuit breaker |
| Payload không hợp lệ | Đưa vào dead-letter/quarantine và cảnh báo |
| Version schema không hỗ trợ | Dừng partition hoặc yêu cầu nâng cấp consumer |
| Vi phạm nghiệp vụ cuối cùng | Lưu kết quả từ chối theo hợp đồng, rồi xác nhận nếu được phép |
| Lỗi không rõ trạng thái commit | Kiểm tra processed marker trước khi xử lý lại |

Không nên ACK một event lỗi vĩnh viễn rồi âm thầm bỏ qua nếu nghiệp vụ yêu cầu dữ liệu đầy đủ. Có thể chuyển event vào dead-letter store với event ID, payload reference, lỗi và thời điểm; checkpoint chỉ được tiến khi chính sách xử lý poison event đã được xác định rõ.

Với lỗi tạm thời, không tiến checkpoint qua event chưa xử lý. Nếu một partition cần giữ thứ tự, event lỗi ở offset 104 có thể chặn việc tiến checkpoint qua 105. Cần chính sách retry hoặc quarantine rõ ràng để không giữ partition vô thời hạn.

## 13. Bảo mật ACK và checkpoint

ACK có thể làm server ngừng replay dữ liệu. Vì vậy, ACK endpoint là một API nhạy cảm.

Các nguyên tắc cần áp dụng:

- Xác thực consumer bằng principal đã được xác minh.
- Ràng buộc consumerId với principal/tenant, không tin payload tự khai báo.
- Chỉ cho phép ACK partition mà consumer được phép đọc.
- Kiểm tra offset không vượt quá high-watermark server đã phát.
- Không cho ACK lùi hoặc nhảy qua khoảng trống.
- Dùng TLS hoặc mTLS để bảo vệ kết nối.
- Ghi audit khi checkpoint tiến bất thường.
- Giới hạn tốc độ ACK và số lượng subscription.
- Ký hoặc dùng cursor opaque nếu client không nên tự tạo vị trí checkpoint tùy ý.

Nếu server cho phép client gửi một offset bất kỳ mà không kiểm tra, client có thể ACK vượt tới cuối log và khiến dữ liệu chưa đọc bị bỏ qua. Không xem checkpoint do client gửi là dữ liệu đáng tin cậy chỉ vì nó đến qua một kết nối RSocket đã xác thực.

## 14. Kiểm thử xác nhận, checkpoint và replay

Kiểm thử quan trọng nhất là các điểm crash giữa commit và ACK. Chỉ test rằng ACK route trả về thành công chưa chứng minh hệ thống không mất hoặc nhân đôi tác dụng phụ.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Consumer commit rồi gửi ACK thành công | Server checkpoint tiến |
| Consumer commit nhưng ACK bị mất | Replay duplicate; consumer không lặp tác dụng phụ |
| Consumer crash trước commit | Event được replay và xử lý lại |
| ACK bị gửi hai lần | Server xử lý idempotent |
| ACK offset vượt high-watermark đã gửi | Server từ chối |
| ACK cumulative nhảy qua offset chưa commit | Server/consumer không tiến checkpoint qua gap |
| Hai partition có offset khác nhau | Checkpoint được lưu riêng |
| Consumer offline quá retention | Server yêu cầu resync |
| Event sai schema | Không âm thầm tiến checkpoint |
| Reconnect giữa replay và live | Không có khoảng trống event |
| Hai request ACK đồng thời | Checkpoint không lùi hoặc ghi đè sai |
| Principal không sở hữu consumer | ACK bị từ chối |

### Unit test cho xử lý idempotent

~~~java
@Test
void duplicateEventDoesNotApplyBusinessEffectTwice() {
    EventEnvelope<Reading> event = sampleEvent("event-104", 104);

    StepVerifier.create(
        consumer.processOnce(event)
            .then(consumer.processOnce(event))
    )
    .verifyComplete();

    verify(readingRepository, times(1)).apply(event.data());
}
~~~

Đây là phác thảo test. Test thật nên dùng database có unique constraint để kiểm tra hai lần xử lý, kể cả khi chúng đến đồng thời.

### Integration test cho ACK bị mất

Một integration test có thể mô phỏng:

1. Server phát event 104.
2. Consumer commit event 104.
3. Test chặn hoặc làm mất response của route events.ack.
4. Consumer reconnect.
5. Server phát lại event 104 vì checkpoint vẫn là 103.
6. Consumer nhận diện duplicate và không lặp tác dụng phụ.
7. Consumer gửi ACK 104 lần nữa.
8. Server lưu checkpoint 104.

Test này chứng minh thứ tự commit-before-ack và khả năng replay an toàn.

### Kiểm thử checkpoint liên tục

Nếu xử lý song song, hãy tạo tình huống offset 10 và 12 đã hoàn tất nhưng offset 11 chưa hoàn tất. Xác nhận checkpoint vẫn là 10. Sau khi offset 11 commit, checkpoint mới được tiến lên 12.

## 15. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Xem REQUEST_N là ACK nghiệp vụ | Server nghĩ consumer đã xử lý dù chỉ mới cấp demand | Tạo application ACK riêng |
| ACK ngay khi nhận payload | Crash sau ACK làm mất dữ liệu | ACK sau khi commit bền vững |
| Chỉ lưu checkpoint trong memory | Restart làm mất vị trí đã xác nhận | Lưu checkpoint bền vững |
| Dùng một checkpoint cho mọi partition | Có thể bỏ qua dữ liệu ở partition chậm | Lưu theo consumer và partition |
| Dùng max offset khi xử lý song song | Nhảy qua event chưa commit | Chỉ tiến high-watermark liên tục |
| Không deduplicate event | Replay tạo tác dụng phụ lặp | Unique event ID và xử lý idempotent |
| Nghĩ RSocket Resume thay thế application replay | Session hết hạn thì không khôi phục được tiến trình nghiệp vụ | Lưu checkpoint và event log |
| Ghép lịch sử với live stream không có ranh giới | Bỏ lỡ event ở thời điểm chuyển nguồn | Dùng high-watermark hoặc tail-from-offset nguyên tử |
| ACK vượt offset đã gửi | Client có thể làm server bỏ qua event | Validate delivered watermark |
| Xóa event ngay khi nhận ACK chưa commit | Dữ liệu có thể bị mất | Lưu checkpoint bền vững trước khi áp dụng retention |
| Không xử lý cursor hết retention | Consumer không thể bắt kịp nhưng server vẫn phát dữ liệu mới | Trả RESYNC_REQUIRED và lấy snapshot |
| Retry vô hạn một poison event | Partition bị kẹt | Retry có giới hạn và quarantine/DLQ |
| Tin consumerId trong payload | Consumer có thể ACK dữ liệu của tenant khác | Ràng buộc principal với consumer |
| Không kiểm thử ACK response bị mất | Lỗi duplicate chỉ xuất hiện khi có sự cố mạng | Fault-injection integration test |

## Kết luận

Xác nhận, checkpoint và replay là cơ chế độ tin cậy ở tầng ứng dụng. REQUEST_N chỉ điều tiết số payload được gửi; RSocket Resume khôi phục session trong phạm vi trạng thái giao thức; application ACK mới xác nhận consumer đã xử lý tới mức nghiệp vụ đã quy định.

Hãy dùng event ID ổn định, sequence hoặc offset theo partition, checkpoint bền vững cho từng consumer, và gửi ACK sau khi transaction local commit. Server chỉ tiến checkpoint sau khi xác thực consumer và kiểm tra offset hợp lệ. Khi ACK bị mất, replay duplicate là bình thường; consumer cần deduplicate và xử lý idempotent. Khi checkpoint đã cũ hơn retention, hãy yêu cầu resync bằng snapshot và high-watermark nhất quán.

Thiết kế này tạo ra luồng at-least-once có thể phục hồi và đạt effectively-once business effect trong phạm vi các transaction, idempotency và hệ thống phụ thuộc được kiểm soát. RSocket vận chuyển dữ liệu hai chiều; ứng dụng chịu trách nhiệm ghi nhận điều gì đã thực sự được xử lý và từ đâu cần phát lại.

## Tài liệu tham khảo

- [RSocket Protocol — Request Stream, Request Channel và Flow Control](https://rsocket.io/about/protocol/)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
- [Spring Framework RSocket Messaging](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Reactor Core — Flux và Backpressure](https://projectreactor.io/docs/core/release/reference/)
- [Spring Data R2DBC — Reactive Transactions](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
