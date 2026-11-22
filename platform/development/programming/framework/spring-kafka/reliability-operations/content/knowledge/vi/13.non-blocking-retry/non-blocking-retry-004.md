# Topic retry theo delay

Trong Spring Kafka, **non-blocking retry** sử dụng các Kafka topic trung gian để giữ record cần thử lại và định tuyến record tới consumer retry sau một khoảng trì hoãn. Thay vì chặn listener của topic gốc trong toàn bộ thời gian chờ, ứng dụng chuyển record thất bại sang một topic retry; listener gốc có thể tiếp tục nhận record mới. Đây là cơ chế phù hợp khi một dependency cần vài giây hoặc vài phút để phục hồi, trong khi consumer vẫn phải duy trì throughput và khả năng xử lý các record không lỗi.

**Topic retry theo delay** là cách tổ chức các lần thử tiếp theo dựa trên thời gian chờ mong muốn. Spring Kafka hỗ trợ thiết lập nhiều mốc retry bằng `@RetryableTopic` hoặc `RetryTopicConfiguration`, tự tổ chức topic và listener retry tương ứng, rồi đưa record thất bại đến Dead Letter Topic (DLT) khi chính sách kết thúc.

Điểm cần hiểu ngay: **Kafka broker không tự trì hoãn việc giao record chỉ vì tên topic chứa số milliseconds**. Cơ chế retry của Spring Kafka lưu metadata cho lần retry và thời điểm record đủ điều kiện xử lý; retry listener phối hợp việc poll và tạm dừng partition khi record chưa đến hạn. Thời điểm thực tế có thể lệch so với mốc cấu hình do poll, scheduling, rebalance và tải hệ thống.

## 1. Vì sao tách retry ra topic riêng?

Với blocking retry, listener đang xử lý một record lỗi sẽ thử lại sau khoảng backoff. Record phía sau cùng partition thường phải chờ, làm consumer lag tăng khi dependency gặp sự cố kéo dài.

Với non-blocking retry:

1. Listener topic gốc nhận record.
2. Lỗi được phân loại là retryable.
3. Spring Kafka publish record sang topic retry tương ứng với lần thử và delay.
4. Offset của record nguồn được xử lý theo chính sách recover/forward của container.
5. Listener topic gốc tiếp tục xử lý record khác.
6. Listener retry chỉ đưa record vào logic nghiệp vụ khi mốc delay cho phép.
7. Nếu vẫn lỗi và còn retry budget, record được publish sang retry topic tiếp theo; nếu hết lượt, record chuyển DLT hoặc một đích kết thúc được cấu hình.

~~~mermaid
flowchart TD
    A["Topic gốc: orders"] --> B["Listener xử lý"]
    B -->|Thành công| C["Hoàn tất và commit tiến độ"]
    B -->|Lỗi retryable| D["Publish sang retry topic"]
    D --> E["Chờ đến thời điểm đủ điều kiện"]
    E --> F["Retry listener xử lý"]
    F -->|Thành công| G["Hoàn tất retry"]
    F -->|Còn lượt retry| D
    F -->|Hết lượt hoặc lỗi fatal| H["DLT / quarantine"]
~~~

Bước chuyển topic giúp giải phóng luồng xử lý ban đầu nhưng tạo thêm các bước publish, consume, quản lý offset và topic. Tác động của việc chuyển record phải được tính vào thiết kế delivery guarantee.

## 2. Delay được biểu diễn bằng topic và metadata như thế nào?

Giả sử ứng dụng cần một lần xử lý ban đầu và ba lần retry, với khoảng chờ lần lượt là 1 giây, 2 giây và 4 giây. Một topology minh họa:

~~~text
orders
  |
  +-- lỗi lần đầu --> orders-retry-1000  (retry sau ~1 giây)
                          |
                          +-- lỗi --> orders-retry-2000  (~2 giây)
                                          |
                                          +-- lỗi --> orders-retry-4000  (~4 giây)
                                                          |
                                                          +-- lỗi --> orders-dlt
~~~

Các tên trên chỉ là **ví dụ**. Spring Kafka có thể sử dụng hậu tố theo delay hoặc index, tái sử dụng topic có cùng khoảng delay và thay đổi quy tắc đặt tên theo cấu hình hoặc phiên bản. Không dùng tên topic như nguồn duy nhất để xác định chính sách retry.

Khi chuyển record, framework kèm metadata như thời điểm backoff dự kiến, topic/partition/offset gốc và thông tin lần thử trong các header thích hợp. Retry listener dùng metadata đó để quyết định khi nào record có thể được xử lý. Nếu nhận record trước hạn, hạ tầng tạm dừng partition và tiếp tục kiểm tra khi đến thời điểm phù hợp.

Ví dụ timeline (bỏ qua thời gian gọi nghiệp vụ và publish):

| Mốc | Nơi xử lý | Hành vi |
|---|---|---|
| `t = 0` | `orders` | Lần xử lý đầu thất bại |
| `t ≈ 1s` | Retry lần 1 | Xử lý lại sau delay 1 giây |
| `t ≈ 3s` | Retry lần 2 | Nếu lần 1 lỗi, chờ thêm 2 giây |
| `t ≈ 7s` | Retry lần 3 | Nếu lần 2 lỗi, chờ thêm 4 giây |
| Sau retry cuối lỗi | `orders-dlt` | Lưu record để điều tra hoặc replay |

Bảng sử dụng các mốc cộng dồn. Delay 1s, 2s, 4s không có nghĩa ba retry xảy ra ở t=1s, t=2s và t=4s tính từ lần nhận đầu tiên.

## 3. Cấu hình nhanh với @RetryableTopic

Spring Kafka hỗ trợ khai báo topology retry trên listener bằng `@RetryableTopic`. Ví dụ non-blocking retry sử dụng exponential backoff:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 4_000
    ),
    autoCreateTopics = "false",
    include = {TemporaryInventoryException.class},
    exclude = {InvalidOrderEventException.class}
)
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-projection")
public void onOrder(OrderEvent event) {
    orderProjectionService.apply(event);
}
~~~

Ở đây:

- `attempts = "4"` là **tổng số lượt xử lý**, bao gồm lần nhận từ topic gốc: lần đầu và tối đa ba lần retry.
- `@Backoff(delay = 1_000, multiplier = 2.0, maxDelay = 4_000)` cho chuỗi delay dự kiến 1s, 2s, 4s.
- `include` và `exclude` minh họa phân loại lỗi. Lỗi không được retry sẽ chuyển tới recovery theo chính sách thay vì đi qua mọi retry topic.
- `autoCreateTopics = "false"` phù hợp khi topic được provision bằng IaC/cluster admin. Cần tạo đầy đủ topic gốc, retry và DLT với số partition phù hợp trước khi chạy.

Tùy phiên bản Spring Kafka và cấu hình ứng dụng, tính năng retry topic cần được bật bằng `@EnableKafkaRetryTopic`, cấu hình support tương ứng hoặc cơ chế cấu hình được Spring Boot tích hợp. Nên dùng một cơ chế cấu hình nhất quán với phiên bản đang triển khai, tránh đăng ký cùng topology nhiều lần.

Ví dụ minh họa bật retry topic trong một cấu hình ứng dụng:

~~~java
@Configuration
@EnableKafka
@EnableKafkaRetryTopic
public class KafkaRetryTopicConfiguration {
}
~~~

Tên class là tên của ứng dụng, không phải class bắt buộc từ Spring Kafka. Trước khi áp dụng, kiểm tra phiên bản `spring-kafka` vì API và quy tắc bật retry topic đã được phát triển qua nhiều phiên bản.

## 4. Fixed delay và exponential delay

Không phải topology nào cũng cần mốc tăng dần. Có thể sử dụng fixed delay để chờ cùng một khoảng giữa các lần xử lý:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 5_000),
    autoCreateTopics = "false"
)
@KafkaListener(topics = "notification-events", groupId = "notification-service")
public void onNotification(NotificationEvent event) {
    notificationService.send(event);
}
~~~

Với cấu hình này, ba lần retry đều có delay dự kiến 5 giây. Cách đặt tên và số lượng retry topic thực tế phụ thuộc vào chiến lược reuse topic cùng interval. Không mặc định rằng nhất định phải có ba Kafka topic retry vật lý khi mọi delay bằng nhau.

So sánh:

| Tiêu chí | Fixed delay | Exponential delay |
|---|---|---|
| Khoảng nghỉ | Không đổi qua các lượt | Tăng dần theo multiplier |
| Ví dụ | 5s, 5s, 5s | 1s, 2s, 4s |
| Dễ dự báo | Rất dễ | Cần tính dãy và max delay |
| Phù hợp | Outage ngắn hoặc nhịp retry ổn định | Phụ thuộc cần thời gian phục hồi tăng dần |
| Rủi ro | Nhiều consumer retry cùng nhịp | Vẫn có thể đồng bộ nếu không có jitter |

Khi cần phân tán thời điểm retry để tránh retry storm, có thể xem xét random/exponential-random backoff nếu phiên bản và cấu hình hỗ trợ. Đừng giả định fixed delay tự thêm jitter.

## 5. Tổng số attempts và retry budget

Một điểm dễ nhầm là ý nghĩa `attempts` của `@RetryableTopic` so với `maxAttempts` của `FixedBackOff` trong blocking retry.

| Cơ chế | Giá trị cấu hình | Cách đếm |
|---|---|---|
| `@RetryableTopic(attempts = "4")` | 4 | Tổng số lượt xử lý: 1 lần gốc + tối đa 3 retry |
| `new FixedBackOff(1000L, 3L)` | 3 | Ba lần retry **sau** lần gốc, tổng tối đa 4 lượt |

Với non-blocking retry, tổng thời gian trước khi đưa sang DLT có thể ước lượng:

~~~text
thời gian xử lý tổng
≈ tổng các delay đã dùng
+ thời gian gọi nghiệp vụ của các attempt
+ thời gian publish/consume/rebalance
+ thời gian recovery
~~~

Ví dụ ba delay 1s, 2s, 4s tạo tổng khoảng nghỉ 7 giây, nhưng đó không phải giới hạn thời gian xử lý cuối cùng. Nếu mỗi lần gọi dependency mất 3 giây, tổng thời gian sẽ tăng thêm tới khoảng 12 giây cho bốn lượt xử lý, chưa kể overhead.

Retry budget cần gắn với SLO. Một luồng đơn hàng yêu cầu xử lý trong 30 giây có thể chấp nhận các delay ngắn; một luồng thông báo có thể chấp nhận chờ vài phút hoặc chuyển sang một workflow xử lý khác.

## 6. Kafka không có cơ chế delayed delivery tự nhiên

Kafka lưu record theo thứ tự offset trong partition. Broker không chủ động giữ một record và chỉ giao nó khi tới timestamp business. Non-blocking retry của Spring Kafka sử dụng **consumer-side scheduling**:

1. Record thất bại được publish vào retry topic.
2. Hạ tầng ghi metadata xác định thời điểm có thể xử lý lần kế tiếp.
3. Retry consumer poll record từ Kafka.
4. Nếu chưa đến hạn, partition tương ứng được pause.
5. Consumer/container tiếp tục cơ chế poll, quản lý membership và resume khi điều kiện delay được đáp ứng.
6. Listener nghiệp vụ xử lý lại record khi tới hạn.

Điều này giải thích vì sao delay là **mốc sớm nhất mong muốn**, không phải SLA xử lý chính xác tới mili giây. Khi broker đang quá tải, consumer bị rebalance hoặc partition bị chặn bởi record chưa đến hạn, record có thể được xử lý muộn hơn.

Cũng cần phân biệt `pause()` của container với `stop()`. Pause vẫn giữ consumer chạy để duy trì consumer group, trong khi stop chấm dứt vòng đời consumer và thường kích hoạt việc gán partition lại.

## 7. Delay topic khác với blocking retry

| Tiêu chí | Blocking retry trong `DefaultErrorHandler` | Non-blocking retry topic |
|---|---|---|
| Nơi record chờ retry | Luồng xử lý của listener/container gốc | Topic retry riêng |
| Topic bổ sung | Thường không bắt buộc | Có retry topic và thường có DLT |
| Backoff dài | Có thể giữ partition/consumer trong quy trình retry | Chuyển record sang luồng retry, cho topic gốc tiếp tục |
| Thứ tự cùng key | Dễ giữ thứ tự xử lý trong partition gốc | Có thể bị đảo thứ tự theo nghiệp vụ |
| Tính đơn giản | Ít thành phần hơn | Nhiều consumer, topic, producer và offset hơn |
| Hạn chế | Poison record có thể giữ partition | Cần quản lý topology và tính idempotent |

Có thể kết hợp retry blocking ngắn cho lỗi thoáng qua và non-blocking retry dài hơn trong những phiên bản/cấu hình hỗ trợ. Khi kết hợp, cần tính số lượt thử ở từng tầng để tránh một record được gọi tới dependency nhiều hơn dự kiến.

## 8. Thứ tự xử lý không còn được bảo đảm xuyên retry topic

Kafka chỉ bảo đảm thứ tự record trong một partition của một topic. Khi record A lỗi và chuyển sang retry topic, record B đến sau cùng key trong topic gốc có thể được xử lý thành công trước A.

~~~mermaid
sequenceDiagram
    participant O as Topic gốc (partition p)
    participant L as Listener gốc
    participant R as Retry topic
    participant D as Database
    O-->>L: Event A, offset 100
    L-->>R: A lỗi, publish retry
    O-->>L: Event B, offset 101
    L->>D: Áp dụng B thành công
    Note over R: Chờ delay
    R-->>L: Event A được retry
    L->>D: Áp dụng A sau B
~~~

Nếu A là `OrderCreated` và B là `OrderCancelled`, việc áp dụng B trước A có thể vi phạm state machine nếu consumer phụ thuộc nghiêm ngặt vào thứ tự.

Các cách xử lý tùy nghiệp vụ:

- Thiết kế thao tác idempotent và dựa vào phiên bản trạng thái, event sequence hoặc optimistic locking để từ chối event cũ.
- Với luồng bắt buộc xử lý tuần tự, cân nhắc blocking retry hoặc giữ một workflow riêng theo aggregate/key.
- Dùng trạng thái trung gian và kiểm tra dependency: event tới sớm có thể được lưu chờ điều kiện nghiệp vụ thay vì áp dụng ngay.
- Tránh giả định dùng cùng partition number trên retry topic sẽ giữ được thứ tự tương đối giữa topic gốc và retry topic.

Non-blocking retry đổi thứ tự có thể quan sát để đổi lấy việc giải phóng luồng xử lý gốc. Quyết định này cần dựa vào invariant của nghiệp vụ.

## 9. Chọn số lượng partition và concurrency cho retry topic

Retry topic cũng được đọc bởi Kafka consumer group. Cần provision số partition, replica và retention phù hợp với topic gốc và năng lực phục hồi.

Ví dụ định hướng:

| Thuộc tính | Lý do cần quan tâm |
|---|---|
| Partition count | Đủ để chứa partition được forward và khai thác concurrency retry |
| Replication factor | Bảo vệ dữ liệu retry nếu broker gặp sự cố |
| Retention | Đủ dài để chờ delay và xử lý backlog/outage |
| Consumer concurrency | Đủ throughput cho retry, tránh gây quá tải dependency đang phục hồi |
| Producer serialization | Producer forward phải serialize được key/value đã nhận, kể cả payload lỗi deserialization |
| ACL/topic policy | Cho phép create/read/write/describe theo topology đã provision |

Khi record được forward giữ partition nguồn, topic đích cần có partition tương ứng. Nếu số lượng partition không khớp, publish có thể thất bại hoặc cần tùy biến routing có chủ đích.

Không tự động cấp concurrency retry bằng concurrency của topic gốc trong mọi trường hợp. Một dependency đang lỗi có thể cần retry chậm hơn để tránh làm sự cố trầm trọng hơn. Ngược lại, retry backlog lớn sau outage có thể cần capacity phục hồi riêng. Hãy dựa vào tốc độ phát sinh lỗi, thời gian outage và throughput của dependency.

## 10. Hạn chế theo loại listener và transaction

Non-blocking retry topic được Spring Kafka thiết kế chủ yếu cho **record listener**. Những phiên bản được dùng phổ biến không hỗ trợ áp dụng `@RetryableTopic` theo cùng cách cho batch listener; khi xử lý batch, cần xem giới hạn API của phiên bản triển khai và cân nhắc tách record listener hoặc retry riêng.

Với Kafka transaction, cần đặc biệt chú ý quan hệ giữa forward-to-retry và commit offset nguồn. Các cấu hình non-blocking retry thông thường không tương thích trực tiếp với transactional listener container. Đừng lấy ví dụ retry topic non-transactional rồi gắn vào luồng đang yêu cầu atomic consume-transform-produce mà không phân tích transaction boundary.

Kafka transaction có thể commit nguyên tử output Kafka và offset trong một luồng transaction đã cấu hình. Non-blocking retry tạo thêm bước forward và consumer khác; việc publish retry và tiến offset cần được quản lý theo semantics của topology thực tế.

Nếu nghiệp vụ yêu cầu exactly-once cho một chuỗi Kafka-to-Kafka, cần thiết kế riêng phù hợp với transaction và kiểm chứng ở phạm vi end-to-end. Nếu xử lý database hoặc HTTP API, hãy bổ sung idempotency và các workflow chịu được replay.

## 11. Xử lý lỗi deserialization trước khi listener

Một record JSON hỏng có thể khiến deserializer thất bại ngay khi consumer `poll()`, trước khi listener nhận được object. Với Spring Kafka, có thể cấu hình `ErrorHandlingDeserializer` để chuyển lỗi deserialization thành thông tin mà error handler có thể xử lý và chuyển DLT.

Ví dụ cấu hình consumer:

~~~yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

Lỗi JSON hỏng thường **không retryable** vì chờ thêm vài giây không làm payload hợp lệ. Với record không thể deserialize, cần cơ chế recovery/DLT được thiết kế phù hợp cùng serializer cho byte array gốc.

Nếu dùng chung producer publish retry và DLT, phải xác nhận producer có thể serialize mọi dạng payload có thể xuất hiện. Khi lỗi deserialization được forward, payload có thể là byte array thay vì object Java thông thường. Một serializer chỉ chấp nhận `OrderEvent` có thể khiến publish DLT thất bại.

## 12. Phân loại lỗi: retryable và fatal

Không phải exception nào cũng nên đi qua mọi delay topic:

| Lỗi | Chính sách gợi ý |
|---|---|
| HTTP 503, rate limit, timeout phụ trợ | Retry có delay/backoff, giới hạn attempts |
| Database connection tạm thời lỗi | Retry có delay, kiểm soát tải |
| Payload thiếu field không thể sửa | Non-retryable, DLT/quarantine |
| Schema version chưa hỗ trợ | DLT/quarantine và cảnh báo nâng cấp |
| Business rule violation mang tính terminal | Không retry; lưu kết quả từ chối hoặc DLT có chủ đích |
| Lỗi lập trình diện rộng | Cảnh báo, hạn chế tạo DLT hàng loạt, xử lý bản phát hành |

Nên biểu đạt nhóm lỗi bằng exception cụ thể, ví dụ `TemporaryInventoryException` và `InvalidOrderEventException`, thay vì dùng chung `RuntimeException` cho mọi trường hợp.

Có thể phân loại lỗi thông qua `include`/`exclude` trong `@RetryableTopic`. Danh sách exception mặc định được coi là fatal và cách xét cause chain khác nhau theo phiên bản Spring Kafka; khi triển khai cần đối chiếu API/phân loại lỗi thực tế.

Nếu nhiều event type chung topic nhưng cần delay/attempts khác nhau, cân nhắc tách topic/listener hoặc dùng cấu hình retry riêng theo endpoint. Một annotation trên một listener không tự hiểu SLA khác nhau của từng event type.

## 13. Dead Letter Topic và DLT handler

Khi hết retry budget hoặc exception bị phân loại không retry, record thường được publish sang DLT theo cấu hình. DLT đóng vai trò vùng cách ly để phân tích, sửa dữ liệu và replay. Nó không chứng minh bước nghiệp vụ ban đầu đã thành công.

Ví dụ listener có DLT handler:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0),
    autoCreateTopics = "false"
)
@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}

@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {
    log.error(
        "Order sent to DLT: topic={} partition={} offset={} key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );
    // Lưu trạng thái vận hành hoặc phát cảnh báo theo chính sách.
}
~~~

`@DltHandler` cần được đặt trong bối cảnh cấu hình retry topic phù hợp, và phương thức handler phải khớp cách framework đăng ký endpoint. Nếu không tự xử lý DLT bằng handler, hãy thiết kế consumer/ops workflow riêng để theo dõi record DLT.

DLT cần giữ thông tin truy vết: topic/partition/offset gốc, event ID, exception class, số attempt, thời điểm lỗi và phiên bản schema. Replay phải có kiểm soát, tránh vòng lặp khi nguyên nhân lỗi chưa được khắc phục. Không nên ghi payload chứa thông tin nhạy cảm nguyên vẹn vào log vận hành.

## 14. Không mặc định exactly-once khi forward sang retry topic

Trong một topology retry thông thường, listener gốc có thể gặp các thời điểm sau:

~~~text
1. Xử lý business record thất bại.
2. Publish record sang retry topic.
3. Container xử lý/commit offset nguồn.
4. Retry consumer đọc record đã forward.
~~~

Nếu process dừng giữa các bước publish và commit offset, record có thể được giao lại từ topic gốc trong khi bản sao đã tồn tại trên retry topic. Nếu publish retry thất bại, error handling phải nhận diện để record không bị bỏ qua mà chưa được lưu bền vững.

Vì vậy, retry topic không có nghĩa mỗi business event chắc chắn chỉ được xử lý đúng một lần. Hãy thiết kế **idempotent consumer** dựa trên event ID bền vững:

~~~java
@Transactional
public void apply(OrderEvent event) {
    if (!processedEventRepository.insertIfAbsent(event.eventId())) {
        return; // Event đã được áp dụng
    }

    orderRepository.apply(event);
}
~~~

`insertIfAbsent` ở đây là thao tác khái niệm, phải dựa trên unique constraint và transaction database để tránh race condition. Dấu đã xử lý và thay đổi nghiệp vụ phải commit cùng nhau. Với HTTP API bên ngoài, dùng idempotency key của provider hoặc workflow có state bền vững.

Không tạo event ID mới khi forward record qua retry topic. ID phải giữ nguyên để consumer phát hiện các lần giao lại của cùng business event.

## 15. Mối quan hệ giữa delay và backlog

Delay topic có thể tích lũy backlog trong outage dài. Giả sử producer tạo 2.000 record/phút, dependency lỗi trong 10 phút và một nửa record phải retry: sẽ có khoảng 10.000 bản ghi cần xử lý lại (chưa tính bản sao qua nhiều retry stage). Khi dependency phục hồi, retry consumer có thể tạo đỉnh lưu lượng lớn.

Một số vấn đề cần lập kế hoạch:

- **Retention:** phải dài hơn thời gian chờ + thời gian backlog dự kiến. Kafka log retention không tự thay đổi theo retry delay.
- **Capacity:** retry consumers có thể cần tăng concurrency sau outage, nhưng không vượt năng lực dependency.
- **Backpressure:** cần rate limiting để tránh retry storm.
- **SLO:** đo độ trễ hoàn tất cuối cùng, không chỉ latency của listener gốc.
- **Ordering:** sau outage, event cũ có thể trở về sau event mới trên topic gốc.
- **Storage:** mỗi retry forward tạo thêm một record trên topic tương ứng; nhiều stage làm tăng write/read và disk usage.

Ví dụ kiểm tra:

~~~text
original-topic rate:     2,000 events/minute
failure proportion:         50%
outage duration:            10 minutes
records entering retry: 10,000
~~~

Con số 10.000 chỉ là lượng record đi vào retry trong khoảng outage theo giả thiết, không phải số record cuối cùng còn tồn trong retry topics. Số tồn thực tế phụ thuộc attempts, routing, retention, tốc độ xử lý và phần record đã chuyển DLT.

## 16. Observability cho retry topic theo delay

Cần theo dõi hành trình của cùng một event qua nhiều topic, thay vì chỉ xem consumer lag của topic gốc.

| Metric/sự kiện | Ý nghĩa vận hành |
|---|---|
| Lag topic gốc | Có bao nhiêu record gốc chờ xử lý |
| Lag theo retry topic | Backlog từng stage retry |
| Tỷ lệ forward sang retry | Tỷ lệ lỗi gây chuyển luồng |
| Attempt count theo exception | Lỗi transient hay poison record |
| Thời gian từ lần đầu tới thành công | Độ trễ end-to-end thực tế |
| Thời gian trễ so với lịch retry | Retry listener có bị nghẽn sau hạn không |
| Số record vào DLT | Mức độ recovery không thành công |
| Lỗi publish retry/DLT | Nguy cơ record chưa được chuyển đến đích |
| Consumer rebalance/pause | Có ảnh hưởng đến delay scheduling không |

Log nên chứa topic hiện tại, topic nguồn, partition, offset, event ID, attempt, exception class và target retry topic. Dùng event ID để liên kết log/tracing nhưng tránh dùng event ID làm metric label vì cardinality có thể rất lớn.

Đặt cảnh báo khi DLT tăng bất thường, retry backlog tăng nhanh, tuổi record lớn nhất vượt SLO hoặc publish sang retry topic lỗi liên tục. Chỉ nhìn lag topic gốc có thể cho cảm giác ứng dụng đã xử lý kịp, trong khi hàng nghìn event đang chờ trên retry topics.

## 17. Triển khai topic bằng hạ tầng và ACL

Nếu dùng `autoCreateTopics = "false"`, topic cần được tạo trước khi listener chạy. Ví dụ một topology minh họa với các topic:

~~~text
orders
orders-retry-1000
orders-retry-2000
orders-retry-4000
orders-dlt
~~~

Đây là danh sách **ví dụ**; phải lấy tên topic thực tế từ retry topic configuration, suffix strategy và phiên bản đang dùng. Provision đúng tên, partition count, replication factor, retention và ACL.

Consumer group cần quyền đọc topic retry/DLT tương ứng; producer retry cần quyền ghi. Nếu topic không tồn tại hoặc ACL thiếu, framework có thể thất bại khi publish hoặc subscribe, làm pipeline retry mất khả năng tiến triển.

Khi thay đổi số attempts hoặc backoff, topology vật lý có thể thay đổi. Hãy xem đây là thay đổi hạ tầng: cập nhật IaC, ACL, monitoring dashboards và quy trình rollback trước khi rollout code mới.

## 18. Runbook: retry topic có record nhưng chưa được xử lý

Khi thấy record nằm trong retry topic lâu hơn dự kiến:

1. Xác nhận tên topic và cấu hình delay/attempts đang có hiệu lực.
2. Kiểm tra retry consumer group có member, partition assignment và lỗi authorization hay không.
3. Xem thời điểm record được đánh dấu đủ điều kiện retry; phân biệt **chưa đến hạn** với **quá hạn nhưng consumer không xử lý**.
4. Kiểm tra consumer pause/resume, poll timeout, rebalance và listener thread availability.
5. Kiểm tra dependency còn lỗi hay không; nếu vẫn lỗi, record có thể đang được forward qua stage tiếp theo.
6. Kiểm tra lỗi publish tới retry topic kế tiếp hoặc DLT; không chỉ kiểm tra exception của business listener.
7. Xem retention của topic có đủ chứa record qua thời gian outage và backlog không.
8. Sau khi sửa, theo dõi event ID qua các stage, xác nhận độ trễ end-to-end và idempotency.

Nếu topic retry có lag cao nhưng chưa tới hạn, việc tăng consumer thread không khiến record được xử lý trước delay. Nếu đã tới hạn nhưng không xử lý, cần kiểm tra consumer membership, task executor, deserialization, ACL và dependency.

## 19. Những lỗi thiết kế thường gặp

### Nhầm delay với thời điểm xử lý chính xác

Delay là khoảng chờ tối thiểu mong muốn. Thực tế bị ảnh hưởng bởi poll, pause, scheduling và tải. Không dùng topic retry làm hệ thống lập lịch chính xác tới millisecond.

### Cho rằng retry topic giữ thứ tự theo key

Record đã chuyển qua topic khác có thể được xử lý sau record mới từ topic gốc. Với workflow trạng thái, cần version/sequence hoặc một cơ chế giữ thứ tự riêng.

### Không tính đúng attempts

`@RetryableTopic(attempts = "4")` là tổng bốn lượt xử lý, không phải bốn lượt retry sau lần đầu. Cần tính đúng cả retry budget của HTTP client/service bên trong listener.

### Để Kafka tự tạo topic thiếu kiểm soát

Trong production, nên dùng quy trình provision và review retention/replication/partition. Thiếu topic hoặc sai số partition có thể làm bước forward thất bại.

### Chuyển mọi exception qua delay topics

Payload sai hoặc schema version không hỗ trợ thường không tự phục hồi. Phân loại non-retryable và chuyển DLT/quarantine có kiểm soát.

### Chỉ giám sát topic gốc

Lag topic gốc có thể thấp trong khi retry backlog và DLT cao. Dashboard phải bao phủ toàn bộ topology.

### Replay tạo event ID mới

Làm mất khả năng deduplicate và có thể nhân đôi side effect. Giữ nguyên ID, nguồn gốc và metadata replay.

## 20. Lựa chọn retry theo yêu cầu nghiệp vụ

| Nhu cầu | Hướng thiết kế |
|---|---|
| Lỗi ngắn dưới vài giây, thứ tự partition quan trọng | Blocking retry có backoff nhỏ |
| Dependency cần chờ nhiều giây/phút, topic gốc vẫn cần chạy | Non-blocking retry topic theo delay |
| Lỗi không thể khắc phục bằng retry | DLT/quarantine ngay |
| Luồng thanh toán cần thứ tự và exactly-once rõ ràng | Thiết kế transaction/workflow riêng; kiểm soát thứ tự và idempotency |
| Outage lớn tạo retry storm | Exponential/random backoff, rate limit, circuit breaker |
| Nhiều event type có SLA khác nhau | Tách listener/topic hoặc retry configuration phù hợp |

Topic retry theo delay là công cụ hiệu quả khi thời gian chờ kéo dài và không muốn record lỗi giữ luồng xử lý gốc. Để vận hành an toàn, cần xác định rõ số attempts và dãy delay, phân loại exception, provision đúng topic, quan sát backlog trên toàn bộ retry topology và chấp nhận rằng thứ tự xử lý có thể thay đổi. Trong mọi trường hợp, thiết kế idempotency và DLT recovery là phần không thể tách rời của reliability.
