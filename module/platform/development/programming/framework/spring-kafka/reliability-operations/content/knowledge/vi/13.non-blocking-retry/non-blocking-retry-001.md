# @RetryableTopic

Trong Spring Kafka, **@RetryableTopic** là annotation giúp triển khai **non-blocking retry** cho một phương thức **@KafkaListener**. Khi listener không xử lý được record và lỗi phù hợp với chính sách retry, Spring Kafka chuyển record sang một hoặc nhiều **retry topic**. Consumer dành cho retry topic sẽ nhận record và thực hiện lần xử lý tiếp theo sau một khoảng trì hoãn. Nếu hết số lần thử hoặc lỗi không thuộc nhóm được phép retry, record có thể được chuyển tới **dead-letter topic (DLT)**.

Cách này phù hợp khi hệ thống phụ thuộc tạm thời không khả dụng trong nhiều giây hoặc nhiều phút nhưng ứng dụng vẫn cần xử lý các record tiếp theo từ topic gốc. Một lỗi không còn giữ consumer của topic gốc trong toàn bộ thời gian backoff. Đổi lại, hệ thống có thêm producer gửi retry, retry topics, listener containers và DLT; việc chuyển record giữa các topic cũng có thể làm **mất thứ tự hoàn tất nghiệp vụ theo key**.

## 1. Mô hình hoạt động

Một listener gọi API thanh toán, gặp HTTP 503 rồi ném exception. Với retry theo kiểu blocking, consumer xử lý lại trên cùng luồng sau BackOff. Với non-blocking retry, Spring Kafka publish record lỗi sang retry topic và cho topic gốc tiếp tục tiến hành khi chuyển tiếp và checkpoint hoàn tất.

~~~mermaid
flowchart LR
    A["Producer"] --> B["orders.events"]
    B --> C["Main listener"]
    C -->|Success| S["Nghiệp vụ hoàn tất"]
    C -->|Transient error| D["orders.events-retry-1000"]
    D --> E["Retry listener"]
    E -->|Success| S
    E -->|Error| F["orders.events-retry-2000"]
    F --> G["Retry listener"]
    G -->|Success| S
    G -->|Exhausted| H["orders.events-dlt"]
    H --> I["@DltHandler hoặc recovery service"]
~~~

Tên topic trong sơ đồ là minh họa. Tên thực tế phụ thuộc chiến lược suffix, số attempt, cách tái sử dụng topic và phiên bản Spring Kafka.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| @KafkaListener | Xử lý record từ topic gốc |
| @RetryableTopic | Khai báo tổng số lần thử, backoff, nhóm lỗi, suffix, DLT |
| Retry-topic publisher | Gửi bản ghi lỗi đến retry topic hoặc DLT |
| Retry topics | Lưu các bản ghi chờ xử lý lại |
| Retry listeners | Nhận record từ retry topic theo thời điểm đủ điều kiện |
| @DltHandler | Xử lý record đã chuyển tới DLT nếu được khai báo |
| KafkaTemplate | Producer được dùng để chuyển tiếp record |
| Kafka broker | Lưu topic/partition và phục vụ fetch; không tự quyết định nghiệp vụ retry |

Một record đi sang retry topic là một Kafka record mới tại topic và offset khác. Event ID nghiệp vụ cần giữ ổn định để liên kết các bản ghi trong suốt vòng retry.

## 2. Khai báo @RetryableTopic

Ví dụ một listener nghiệp vụ:

~~~java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final OrderService orderService;
    private final DeadLetterService deadLetterService;

    public OrderConsumer(OrderService orderService,
                         DeadLetterService deadLetterService) {
        this.orderService = orderService;
        this.deadLetterService = deadLetterService;
    }

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
            delay = 1_000L,
            multiplier = 2.0,
            maxDelay = 8_000L
        ),
        include = {TransientDataAccessException.class},
        autoCreateTopics = "false"
    )
    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-processor"
    )
    public void handle(OrderEvent event) {
        orderService.applyIdempotently(event);
    }

    @DltHandler
    public void onDlt(OrderEvent event) {
        deadLetterService.recordForInvestigation(event);
    }
}
~~~

Các class OrderEvent, OrderService và DeadLetterService là thành phần domain minh họa. Trong hệ thống thật cần cấu hình consumer deserializer, producer serializer, KafkaTemplate, broker connectivity, topic và ACL.

Ý nghĩa từng thuộc tính:

- **attempts = "4"** đặt tổng số lần delivery tối đa trong retry flow, **bao gồm lần xử lý đầu tiên ở topic gốc**. Ví dụ có tối đa một lần gốc và ba lần retry.
- **backoff** quy định khoảng chờ trước các lần thử tiếp theo.
- **include** chỉ định nhóm exception có thể được retry. Exception ngoài nhóm cần được xử lý theo policy và có thể đi DLT.
- **autoCreateTopics = "false"** yêu cầu các topic tương ứng đã được provision bên ngoài.
- **@DltHandler** là method xử lý record ở DLT; nó không đồng nghĩa xử lý nghiệp vụ gốc thành công.

Không nên coi việc thêm annotation là đủ để hoàn tất triển khai. Retry infrastructure còn cần producer có khả năng chuyển tiếp và các topic đích khả dụng.

## 3. Kích hoạt retry-topic infrastructure

Tùy phiên bản Spring Kafka và Spring Boot, retry-topic infrastructure có thể cần được bật bằng annotation cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaRetryTopic;

@Configuration
@EnableKafkaRetryTopic
public class KafkaRetryConfiguration {
}
~~~

Đây là cách tường minh để bật những thành phần Spring Kafka cần tạo retry endpoints. Trong môi trường mà auto-configuration đã thiết lập infrastructure, hãy tránh đăng ký trùng. Tập trung xác minh runtime đã tạo các listener containers cho topic gốc, retry topics và DLT theo đúng topology dự kiến.

Các điều kiện tối thiểu là KafkaTemplate dùng để chuyển tiếp record, producer serializers thích hợp, retry/DLT topics đã tồn tại hoặc được phép tạo, quyền publish/consume, và listener container factory đúng với ứng dụng.

## 4. Phân biệt delivery attempt và retry count

Giả sử record luôn xử lý thất bại và cấu hình attempts bằng 4:

| Lần xử lý | Nguồn | Kết quả |
|---:|---|---|
| 1 | Topic gốc | Thất bại; chuyển sang retry |
| 2 | Retry topic | Thất bại; chuyển sang retry tiếp |
| 3 | Retry topic | Thất bại; chuyển sang retry tiếp |
| 4 | Retry topic | Thất bại; hết attempts |
| Sau đó | DLT | Chờ recovery theo chính sách |

Ở đây tổng số attempt là 4 nhưng số lần retry sau lần đầu là 3. Nếu record thành công ở bất kỳ attempt nào, những lần tiếp theo sẽ không cần thiết.

Khi làm metric, phân biệt rõ **total delivery attempts**, **blocking retries trong một container**, và **số lần chuyển tiếp qua retry topics**. Các số này có thể khác nhau, nhất là khi kết hợp DefaultErrorHandler với @RetryableTopic.

## 5. Backoff: fixed và exponential

Thuộc tính backoff sử dụng annotation Backoff của Spring Retry. Các cấu hình thường gặp:

~~~java
// Fixed delay: khoảng chờ xấp xỉ 5 giây mỗi lần
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 5_000L)
)
~~~

~~~java
// Exponential delay có giới hạn
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1_000L,
        multiplier = 2.0,
        maxDelay = 10_000L
    )
)
~~~

Với exponential delay ở ví dụ thứ hai, các khoảng chờ minh họa có thể tăng theo 1, 2, 4 và 8 giây. Nếu số lần thử nhiều hơn, maxDelay giới hạn độ dài của những khoảng chờ tiếp theo. Thời điểm xử lý thực tế không chính xác tuyệt đối theo mili giây vì còn phụ thuộc poll loop, lịch chạy thread, broker/network và rebalance.

**Kafka broker không hỗ trợ native scheduling một record theo delay của @RetryableTopic.** Spring Kafka sử dụng thông tin thời gian trên record cùng cơ chế pause/resume hoặc trì hoãn của consumer để chỉ giao tới listener khi đến ngưỡng. Vì vậy có thể quan sát actual retry delay dài hơn configured backoff.

Chọn backoff cần tính đến downstream outage, rate limiting, thời gian phục hồi thường gặp và SLA. Một retry delay quá ngắn có thể gây retry storm; quá dài có thể khiến sự kiện bị tồn đọng không cần thiết.

## 6. Phân loại exception

Không phải lỗi nào cũng nên thử lại. Lỗi transient có thể biến mất khi dependency phục hồi; lỗi vĩnh viễn thường cần sửa dữ liệu hoặc cấu hình.

| Nhóm lỗi | Hành vi thường cân nhắc |
|---|---|
| Database deadlock | Retry có giới hạn sau khi transaction rollback |
| HTTP 429 / 503 | Retry với BackOff và giới hạn tổng thời gian |
| Network timeout | Retry nếu thao tác bên ngoài có idempotency |
| ValidationException | Không retry; recovery/DLT |
| Schema không tương thích | Điều tra producer/consumer contract, có thể DLT |
| AuthorizationException | Sửa quyền; retry không tự cấp ACL |
| Business invariant violation vĩnh viễn | Không retry, ghi nhận và xử lý nghiệp vụ |
| Duplicate event | Xử lý idempotent, không xem duplicate hợp lệ là lỗi transient |

Có thể cấu hình include và exclude:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000L),
    include = {
        org.springframework.dao.TransientDataAccessException.class
    },
    exclude = {
        IllegalArgumentException.class
    }
)
~~~

Exception có thể bị bọc bởi Spring listener exception, driver exception hoặc HTTP client exception. Cần xác định quy tắc duyệt cause chain và classification trong phiên bản Spring Kafka đang chạy. Nếu cấu hình include quá rộng, lỗi vĩnh viễn có thể chiếm retry topics trong thời gian dài. Nếu cấu hình exclude sai, một lỗi có thể phục hồi lại đi thẳng tới DLT.

## 7. Topic naming và retry stages

Spring Kafka thường dùng suffix cho retry topics và DLT. Với topic gốc orders.events, tên có thể tương tự:

~~~text
orders.events
orders.events-retry-1000
orders.events-retry-2000
orders.events-retry-4000
orders.events-dlt
~~~

Tên trên chỉ nhằm giải thích topology. Không được suy ra số retry topic bằng attempts trừ một trong mọi trường hợp: cùng delay có thể dùng lại retry topic tùy chính sách, chiến lược suffix có thể gắn delay hoặc index và hành vi thay đổi theo phiên bản.

Có thể chỉ định suffix:

~~~java
@RetryableTopic(
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    attempts = "4",
    backoff = @Backoff(delay = 1_000L, multiplier = 2.0)
)
~~~

Khi thay đổi retry topic naming hoặc số attempt trên deployment đang chạy, cần xác định backlog còn trong các topic cũ. Một topic cũ không còn được listener mới subscribe có thể giữ record đến khi retention xóa chúng. Đổi topology cần plan di chuyển hoặc drain backlog.

## 8. Topic provisioning và ACL

Khi autoCreateTopics được đặt false, các topic retry và DLT phải được tạo trước. Khi bật tự tạo, cần kiểm soát quyền Admin, partition count, replication, retention và chính sách của đội nền tảng.

Ví dụ một topology đã được duyệt:

| Topic | Partition | Replication | Mục đích |
|---|---:|---:|---|
| orders.events | 6 | 3 | Event nguồn |
| orders.events-retry-1000 | 6 | 3 | Retry stage 1 |
| orders.events-retry-2000 | 6 | 3 | Retry stage 2 |
| orders.events-retry-4000 | 6 | 3 | Retry stage 3 |
| orders.events-dlt | 6 | 3 | Điều tra/replay |

Các giá trị chỉ minh họa. Hãy provision theo **topology thực tế** sau khi Spring đã áp dụng strategy. Đảm bảo partition của retry/DLT topic tương thích với cách Spring chuyển tiếp partition index. Nếu topic đích thiếu partition được nhắm tới, publish có thể thất bại.

Quyền truy cập thường cần:

- Consumer principal: READ topic gốc/retry/DLT theo listener được triển khai và quyền consumer group phù hợp.
- Retry publisher principal: WRITE retry/DLT topics.
- Provisioning principal: quyền CREATE/ALTER nếu hạ tầng tạo topic theo cách quản trị.

Đừng cấp ALL trên toàn cluster chỉ để @RetryableTopic hoạt động. Cấp đúng principal, resource và operation theo quy trình bảo mật.

## 9. DLT và @DltHandler

Sau khi hết retry hoặc khi lỗi không retryable, retry infrastructure có thể định tuyến record đến DLT. Một method có @DltHandler có thể nhận record và ghi nhận để điều tra:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.DltHandler;

@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {

    recoveryService.storeForReview(
        record.topic(),
        record.partition(),
        record.offset(),
        record.value()
    );
}
~~~

Trong hệ thống production, nên lưu event ID, topic gốc (từ header/metadata phù hợp), nguyên nhân lỗi, timestamp và trạng thái xử lý. Không nên chỉ log và loại bỏ record nếu nghiệp vụ yêu cầu khả năng phục hồi.

Nếu không khai báo DltHandler, hạ tầng có thể sử dụng handler mặc định theo phiên bản và cấu hình. Không nên dựa vào mặc định mà không biết DLT được tiêu thụ, ghi log hay cần một recovery service riêng.

Một số hệ thống chủ động không khởi chạy DLT handler, để đội vận hành duyệt dữ liệu trước khi replay. Quyết định này cần được thể hiện bằng configuration, ownership và runbook.

### Nếu DLT handler cũng ném lỗi

Spring Kafka hỗ trợ các chính sách DltStrategy để kiểm soát hành vi khi xử lý DLT thất bại. Ví dụ:

~~~java
import org.springframework.kafka.retrytopic.DltStrategy;

@RetryableTopic(
    attempts = "4",
    dltStrategy = DltStrategy.FAIL_ON_ERROR
)
~~~

Cần đối chiếu enum và semantics chính xác của phiên bản đang dùng. Một DLT handler lỗi có thể khiến record bị giao lại theo chính sách hoặc để lỗi được báo thay vì xem như đã phục hồi. Theo dõi DLT handler failure riêng với listener failure của topic gốc.

## 10. Vì sao @RetryableTopic có thể làm thay đổi thứ tự?

Giả sử cùng partition có ba event của đơn hàng 42:

~~~text
offset 100: OrderChanged(order=42, version=1)
offset 101: OrderChanged(order=42, version=2)
offset 102: OrderChanged(order=42, version=3)
~~~

Nếu version 1 lỗi và được chuyển sang retry topic, consumer topic gốc có thể xử lý version 2 và 3 trước khi version 1 được retry. Các side effect có thể hoàn tất theo thứ tự 2, 3, 1.

Kafka vẫn bảo đảm thứ tự trong từng partition của **từng topic**. Việc chuyển record sang retry topic tạo một đường đi khác và không giữ được thứ tự hoàn tất nghiệp vụ ban đầu.

Nếu yêu cầu strict ordering theo aggregate, cân nhắc:

- Blocking retry có giới hạn hoặc một cơ chế tuần tự riêng theo key.
- Kiểm tra version/sequence number trước khi cập nhật.
- Dùng conditional update chỉ chấp nhận version mới hơn.
- Giữ record sau của cùng aggregate trong workflow đến khi record trước hoàn tất.
- Thiết kế nghiệp vụ có thể tiếp nhận event đảo thứ tự.

Đây là quyết định thiết kế trọng tâm. Không nên bật non-blocking retry chỉ vì muốn giảm consumer lag khi domain yêu cầu thứ tự nghiêm ngặt.

## 11. Blocking retry so với non-blocking retry

| Tiêu chí | DefaultErrorHandler blocking retry | @RetryableTopic non-blocking |
|---|---|---|
| Nơi chờ | Trong đường xử lý listener hiện tại | Retry topic và retry consumer riêng |
| Delay vài giây/phút | Có thể giữ partition chậm | Topic nguồn có thể tiếp tục tiến |
| Ordering theo partition | Thường bảo toàn thứ tự xử lý trong luồng hiện tại | Có thể đảo thứ tự hoàn tất giữa topic nguồn và retry |
| Topic bổ sung | Không bắt buộc | Cần retry/DLT topology |
| Giám sát | BackOff, exception, attempt ở container | Retry stages, topic lag, forward success, DLT |
| Capacity | Ít thành phần hơn | Tăng topic/container/producer traffic |
| Phù hợp | Lỗi ngắn và ordering quan trọng | Lỗi dài, không yêu cầu strict ordering |

Có thể kết hợp một số lần blocking retry nhanh với non-blocking retries theo tính năng và cấu hình phiên bản hỗ trợ. Khi đó cần tính tổng số lần gọi nghiệp vụ, backoff, latency và callback/metrics của mỗi lớp. Không để hai tầng retry cùng tăng không kiểm soát.

## 12. Giới hạn với batch listener và Kafka transactions

Trong các phiên bản Spring Kafka áp dụng retry-topic feature theo mô hình này, non-blocking retries **không hỗ trợ batch listeners** và **không kết hợp trực tiếp với container Kafka transactions**. Luôn xác minh giới hạn theo dependency version hiện tại.

Hệ quả:

- Không gắn @RetryableTopic vào batch listener rồi kỳ vọng từng record lỗi sẽ tự được tách đúng như record listener.
- Nếu container đang dùng Kafka transaction manager để xử lý và commit offset trong transaction, không giả định retry-topic infrastructure có thể tham gia cùng semantics.
- Kafka transaction không biến database transaction hoặc HTTP API thành transaction nguyên tử.
- Nếu cần consistency qua nhiều hệ thống, dùng transactional outbox, inbox, idempotency hoặc workflow được thiết kế rõ ràng.

Nếu use case là Kafka-to-Kafka exactly-once processing, cần đánh giá riêng cơ chế transactional listener, AfterRollbackProcessor và retry strategy phù hợp trước khi chọn @RetryableTopic.

## 13. Idempotency và duplicate delivery

Khi record được chuyển từ topic gốc sang retry topic, có bước publish record mới và bước xác nhận offset nguồn. Nếu publish đã thành công nhưng commit offset nguồn thất bại, record nguồn có thể được giao lại và gửi chuyển tiếp thêm lần nữa. Một sự cố restart hoặc rebalance cũng có thể dẫn tới redelivery sau khi database side effect đã commit.

Ví dụ idempotent consumer:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void applyIdempotently(OrderEvent event) {

    boolean firstTime =
        processedEventRepository.insertIfAbsent(event.eventId());

    if (!firstTime) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Phương thức insertIfAbsent phải atomic, ví dụ dùng unique constraint trên event ID và thao tác insert-on-conflict tương đương của database. Marker đã xử lý và thay đổi nghiệp vụ phải nằm trong **cùng database transaction**. Nếu rollback, marker cũng rollback để lần retry có thể thực hiện lại.

Nếu gọi API thanh toán, gửi idempotency key ổn định khi API hỗ trợ. Nếu cần phát event sau khi cập nhật database, cân nhắc outbox. Không dùng topic/partition/offset của record retry như khóa nghiệp vụ duy nhất, vì record mới có offset mới.

## 14. Theo dõi attempts qua nhiều topic

Một record đi từ topic gốc sang các retry topic sẽ có metadata Kafka mới tại mỗi hop. Trong log và trace, nên giữ:

- Event ID và correlation ID ổn định.
- Topic, partition và offset hiện tại.
- Topic và partition nguồn nếu header/metadata có sẵn.
- Retry stage và delay dự kiến.
- Exception gốc và exception mới nhất.
- Thời điểm xảy ra lỗi, thời điểm đủ điều kiện retry.
- Kết quả publish và xử lý cuối cùng.

Các retry headers do Spring Kafka quản lý có thể khác nhau theo phiên bản. Khi viết code dùng metadata/header, dùng constant hoặc API được dependency hiện tại cung cấp thay vì hard-code một tên header từ ví dụ cũ.

**RetryListener** gắn vào DefaultErrorHandler quan sát attempt trong error handler cụ thể; nó không tự đếm toàn bộ các lần chuyển topic của @RetryableTopic. Nếu cần audit end-to-end xuyên qua restart và nhiều topic, xây dựng một bản ghi theo event ID trong hệ thống bền vững.

## 15. Lỗi khi publish retry hoặc DLT

Non-blocking retry phụ thuộc một producer để chuyển record. Việc chuyển tiếp có thể thất bại vì:

- Broker không khả dụng hoặc request timeout.
- Topic đích chưa được tạo.
- Principal thiếu WRITE trên retry hoặc DLT topic.
- Topic đích không có partition được chọn.
- Serializer không hỗ trợ payload hoặc header hiện tại.
- Quota, network hoặc producer configuration không phù hợp.
- Consumer rebalance và offset commit thất bại trong lúc chuyển tiếp.

Khi forwarding failure xảy ra, cần phân biệt listener đã lỗi, publish đã thành công hay chưa và committed offset của consumer nguồn. Không xem record đã được chuyển tiếp chỉ vì lỗi nghiệp vụ đã được phát hiện.

Log và alert nên có **retry forwarding failure** riêng với listener processing failure. Nếu publish sang DLT thất bại, quy trình recovery cũng chưa hoàn tất; record vẫn có thể cần được giao lại theo semantics của container/error handler.

## 16. Serializer và KafkaTemplate

Retry publisher phải gửi được kiểu key/value của record. Với JSON event đơn giản, cấu hình có thể như sau:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
~~~

Nếu consumer dùng ErrorHandlingDeserializer hoặc cần chuyển record có raw bytes khi deserialization lỗi, retry/DLT publisher phải hỗ trợ kiểu dữ liệu thực tế được gửi. Cần kiểm tra riêng case deserialization failure vì listener method có thể chưa từng nhận một object domain hợp lệ.

Nếu ứng dụng có nhiều KafkaTemplate, @RetryableTopic có thể tham chiếu tên bean của template phù hợp:

~~~java
@RetryableTopic(
    kafkaTemplate = "retryKafkaTemplate",
    attempts = "4",
    backoff = @Backoff(delay = 1_000L)
)
~~~

Bean tên retryKafkaTemplate phải được định nghĩa và có ProducerFactory/serializer/security thích hợp. Tránh để template nghiệp vụ chỉ serialize được một kiểu event nhưng retry infrastructure phải gửi nhiều kiểu payload khác nhau.

## 17. Retention và capacity

Record có thể chờ lâu ở retry topics. DLT thường cần giữ lâu hơn để điều tra và replay. Topic retention phải đủ cho delay cấu hình, thời gian downtime, backlog và lịch xử lý sự cố.

| Tài nguyên | Điều cần hoạch định |
|---|---|
| Retry topic retention | Lớn hơn thời gian chờ và outage dự kiến |
| DLT retention | Đủ thời gian phát hiện, điều tra và replay |
| Partition count | Phù hợp consumer concurrency và định tuyến |
| Replication | Phù hợp mức độ bền dữ liệu của nghiệp vụ |
| Disk/network | Chịu được retry storm và nhiều lần publish |
| Consumer lag | Quan sát được backlog của từng retry stage |

Một DLT có retention quá ngắn có thể xóa record trước khi người vận hành phát hiện. Retry topic có retention ngắn hơn delay lớn nhất cũng có thể làm mất record trước khi nó đủ điều kiện xử lý lại.

## 18. Concurrency của retry containers

Retry listeners có container riêng nên cần đánh giá concurrency độc lập với listener topic gốc. Tăng concurrency có thể giúp xử lý backlog nhanh hơn sau outage, nhưng cũng có thể gây áp lực trở lại cho downstream vừa phục hồi.

Giá trị phù hợp phụ thuộc số partition, số instance, tốc độ record vào retry stages, database connection pool, API rate limit và loại nghiệp vụ. Không mặc định concurrency cao nhất luôn tốt nhất. Nếu nghiệp vụ có contention trên cùng aggregate, chạy retry song song có thể tạo database deadlock hoặc duplicate side effect.

Một số phiên bản có thuộc tính cấu hình concurrency cho retry containers. Hãy xác minh API của phiên bản đang dùng và đo consumer assignments thực tế, không chỉ nhìn cấu hình annotation.

## 19. Observability và cảnh báo

Dashboard cho non-blocking retry phải bao gồm toàn topology.

| Chỉ số | Mục đích |
|---|---|
| Original listener failure rate | Phát hiện lỗi xử lý tại nguồn |
| Retry forwarding failure | Phát hiện không chuyển được record |
| Retry topic backlog/lag | Quan sát số record đang chờ |
| Oldest record age | Đánh giá record quá hạn SLA |
| Scheduled versus actual retry delay | Phát hiện delay kéo dài bất thường |
| Retry processing success rate | Đo hiệu quả các lần retry |
| DLT ingress rate | Phát hiện lỗi kéo dài hoặc non-retryable |
| DLT handler/replay failures | Quan sát đường phục hồi |
| Producer send latency/errors | Theo dõi kênh publish retry/DLT |
| Downstream error rate/latency | Liên hệ nguyên nhân gốc |

Ví dụ log:

~~~text
event=retry_forwarded
service=order-processor
event_id=evt-42
source_topic=orders.events
source_partition=1
source_offset=847
destination_topic=orders.events-retry-1000
retry_stage=1
exception_class=DownstreamUnavailableException
~~~

Event ID, offset và correlation ID nên có trong log/trace để tìm record cụ thể; không dùng các giá trị này làm metric tag vì cardinality lớn. Không log credential hoặc toàn bộ payload chứa dữ liệu nhạy cảm.

Một retry đơn lẻ có thể là bình thường. Nên cảnh báo theo tỷ lệ lỗi, backlog, oldest age, DLT spike và forwarding failure thay vì alert trên từng lần transient exception.

## 20. DLT replay an toàn

Record ở DLT không đồng nghĩa business event đã hoàn tất. Cần owner và quy trình phục hồi:

1. Lấy event ID, dữ liệu nguồn và exception từ DLT.
2. Xác định lỗi là schema, configuration, dependency hay nghiệp vụ.
3. Kiểm tra side effect có thể đã xảy ra trước khi thất bại.
4. Sửa nguyên nhân, xác minh downstream đã phục hồi.
5. Quyết định replay sang topic nào và có cần giữ thứ tự không.
6. Giữ nguyên event ID/idempotency key nếu cùng hành động nghiệp vụ.
7. Replay ở tốc độ phù hợp để tránh quá tải.
8. Theo dõi success, retry và DLT sau replay.
9. Ghi lại phạm vi, người thực hiện và kết quả.

Không replay hàng loạt mọi record DLT ngay khi dependency quay lại. Một số record có thể lỗi vĩnh viễn hoặc không còn hợp lệ với trạng thái nghiệp vụ hiện tại.

## 21. Kiểm thử non-blocking retry

Dùng Kafka broker thật hoặc Testcontainers để xác minh topology, ACL/serializer, delay và consumer group. Unit test của method listener không chứng minh hoạt động chuyển record qua topic.

Các tình huống nên kiểm thử:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Listener xử lý thành công ngay | Không phát record retry/DLT |
| Lỗi retryable rồi phục hồi | Record đi retry và xử lý thành công |
| Lỗi qua hết attempts | Record vào DLT đúng policy |
| Lỗi non-retryable | Không trải qua các retry stages không cần thiết |
| Retry topic thiếu | Forwarding failure được phát hiện |
| KafkaTemplate sai serializer | Lỗi chuyển tiếp có log/alert |
| Producer thiếu ACL | Authorization failure rõ nguyên nhân |
| Consumer restart trong khi chờ delay | Record vẫn có thể xử lý lại sau restart |
| Downstream outage kéo dài | Backlog và retention chịu được tải |
| DLT handler lỗi | Hành vi theo DltStrategy được quan sát |
| Nhiều event cùng key | Kiểm chứng reordering và idempotency |

Khi kiểm tra delay, ghi timestamp của lần lỗi và lần nhận tiếp theo; dùng assertion chờ có timeout. Không dùng sleep cố định duy nhất và kỳ vọng callback xảy ra chính xác ở mili giây định trước.

## 22. Runbook xử lý sự cố

Khi record không được retry đúng mong đợi:

1. Xác minh service, listener ID, topic gốc, partition, offset và event ID.
2. Kiểm tra annotation @RetryableTopic và infrastructure đã được bật.
3. Xác định exception gốc và cách classification áp dụng.
4. Kiểm tra attempts/backoff và thời điểm đủ điều kiện retry.
5. Liệt kê các retry/DLT topics thực tế.
6. Kiểm tra topic tồn tại, retention, partition count và ACL.
7. Kiểm tra KafkaTemplate, producer serializer và publish result.
8. Xác nhận retry listener container đang chạy và nhận partition.
9. Kiểm tra retry topic lag, pause state, rebalance và broker connectivity.
10. Tìm record ở retry stages hoặc DLT theo event ID.
11. Kiểm tra có duplicate forwarding hoặc side effect đã commit chưa.
12. Sửa nguyên nhân, theo dõi backlog giảm và success rate phục hồi.

Nếu topic gốc tiến nhanh nhưng nghiệp vụ vẫn chậm, kiểm tra backlog retry topics và delay. Nếu record không xuất hiện ở retry topic sau khi listener lỗi, ưu tiên kiểm tra classification và retry publisher.

## 23. Các hiểu nhầm thường gặp

**Annotation tự tạo quyền Kafka.** Ứng dụng vẫn cần ACL trên retry/DLT topics, group ID và các tài nguyên liên quan.

**attempts là số lần retry.** Nó thường tính cả lần giao đầu; cấu hình attempts bằng 4 nghĩa tối đa 4 deliveries.

**Backoff là thời điểm chạy chính xác.** Delay là ngưỡng; scheduling và tình trạng consumer có thể làm retry muộn hơn.

**Dùng retry topic vẫn giữ ordering.** Việc tách một event khỏi topic gốc có thể cho event sau xử lý trước.

**Tăng concurrency luôn cải thiện recovery.** Concurrency cao có thể làm quá tải downstream hoặc tăng database contention.

**Topic gốc hết lag nghĩa nghiệp vụ đã hoàn tất.** Event có thể đang chờ ở retry topics hoặc DLT.

**DLT là xử lý thành công.** DLT chỉ là nơi giữ record không hoàn tất nghiệp vụ để xử lý tiếp.

**Retry không thể tạo duplicate.** Publish sang retry và commit offset nguồn vẫn có các cửa sổ lỗi dẫn tới redelivery.

**Đổi retry suffix không cần migration.** Retry topic cũ có thể còn backlog không còn được consumer mới subscribe.

**Dùng với batch listener hoặc container transactions mà không kiểm tra.** Đây là các giới hạn quan trọng của retry-topic feature theo phiên bản.

## 24. Checklist trước production

**Thiết kế nghiệp vụ**

- [ ] Định nghĩa lỗi retryable và non-retryable.
- [ ] Chọn attempts/backoff theo SLA, downtime và rate limit.
- [ ] Đánh giá tác động mất ordering.
- [ ] Consumer và side effect có idempotency.
- [ ] Có quy trình xử lý DLT và replay.

**Kafka topology**

- [ ] Runtime đã tạo đúng retry/DLT listener endpoints.
- [ ] Tên retry/DLT topics và reuse strategy được xác minh.
- [ ] Partition/replication/retention phù hợp.
- [ ] Principal có READ/WRITE/group ACL tối thiểu.
- [ ] KafkaTemplate và serializers hỗ trợ forwarding.
- [ ] Có kế hoạch khi thay đổi topology giữa các bản deploy.

**Vận hành**

- [ ] Có alert forwarding failure và DLT publish failure.
- [ ] Dashboard có retry topic lag và oldest record age.
- [ ] Đã thử restart, rebalance và downstream outage.
- [ ] Đã kiểm tra giới hạn batch/transaction của phiên bản.
- [ ] Có integration tests cho success, retry, exhausted và DLT.
- [ ] Quy trình replay giữ event ID và chống side effect trùng.

## 25. Nguyên tắc sử dụng

**@RetryableTopic** triển khai non-blocking retry bằng cách chuyển record lỗi qua các Kafka retry topics và tới DLT khi cần. Nó đặc biệt hữu ích cho retry delay dài vì listener topic gốc có thể tiếp tục làm việc.

Muốn vận hành đáng tin cậy, cần hiểu rằng attempts tính cả lần đầu, backoff không bảo đảm thời điểm chạy chính xác, topic forwarding có thể tạo duplicate và thay đổi thứ tự xử lý. Thiết kế idempotency, provision topics/ACL/retention, giám sát toàn bộ retry pipeline và thử nghiệm cả đường lỗi publish trước khi dùng ở production.
