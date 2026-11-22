# Checklist dead letter và replay

Dead-letter topic (DLT) lưu những record không thể xử lý theo chính sách retry của consumer. DLT giúp tách record lỗi khỏi luồng chính để điều tra và phục hồi, nhưng việc đưa record vào DLT chưa có nghĩa nghiệp vụ đã hoàn tất. Mỗi record cần được truy vết, phân loại, quyết định cách khắc phục và replay có kiểm soát nếu phù hợp.

Trong Spring Kafka, DLT có thể được tạo bởi `DeadLetterPublishingRecoverer` khi dùng error handler hoặc bởi cơ chế non-blocking retry với `@RetryableTopic`. Quy trình vận hành phải bao gồm lúc record được đưa vào DLT, thời gian lưu giữ, người chịu trách nhiệm, cách replay và cách ngăn tác dụng phụ bị thực hiện trùng.

## 1. Xác định luồng tạo DLT

Trước tiên, ghi rõ listener đang dùng blocking retry hay non-blocking retry. Hai cơ chế có topology và cách điều khiển khác nhau.

| Cơ chế | Đường đi | Điểm cần kiểm tra |
|---|---|---|
| Blocking retry với `DefaultErrorHandler` | Topic gốc → listener → retry trong container → recoverer → DLT | BackOff, exception classification, recoverer và offset |
| Non-blocking retry với `@RetryableTopic` | Topic gốc → retry topic theo mức backoff → DLT | attempts, retry topic, DLT handler, partition và retention |
| Quy trình phục hồi riêng | DLT → replay worker → topic đích | Quyền truy cập, audit, rate limit và idempotency |

~~~mermaid
flowchart TD
    A[Topic gốc] --> B[Listener]
    B -->|Thành công| C[Hoàn tất offset]
    B -->|Lỗi| D[Retry policy]
    D --> E[Retry / retry topic]
    E --> B
    D -->|Hết retry| F[Recoverer]
    F --> G[(DLT)]
    G --> H[Điều tra và phân loại]
    H --> I{Có thể phục hồi?}
    I -->|Có| J[Replay có kiểm soát]
    J --> A
    I -->|Không| K[Compensation / lưu hồ sơ]
~~~

Một DLT record có thể phát sinh do lỗi dữ liệu, lỗi nghiệp vụ, dependency kéo dài, lỗi cấu hình hoặc lỗi lập trình. Không nên coi mọi record trong DLT là cùng một loại lỗi và replay tất cả theo một lệnh chung.

## 2. Checklist cấu hình retry và recoverer

Với blocking retry, xác nhận error handler có recoverer publish record sang DLT và xử lý lỗi publish đúng cách.

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    recoverer.setFailIfSendResultIsError(true);

    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedCurrencyException.class
    );

    return handler;
}
~~~

Gắn handler vào listener container factory:

~~~java
factory.setCommonErrorHandler(ordersErrorHandler);
~~~

- [ ] Listener để exception truyền về container khi muốn retry.
- [ ] Lỗi tạm thời và lỗi không thể retry được phân loại rõ.
- [ ] BackOff có giới hạn số lần hoặc tổng thời gian.
- [ ] Recoverer publish tới đúng topic đích.
- [ ] Kết quả publish DLT được kiểm tra.
- [ ] Serializer của DLT hỗ trợ đúng kiểu key/value và payload.
- [ ] Topic DLT đã được provision hoặc cơ chế tạo topic được kiểm soát.
- [ ] Offset chỉ được xử lý theo chính sách sau khi recoverer hoàn tất.

`setFailIfSendResultIsError(true)` yêu cầu recoverer báo lỗi khi gửi DLT thất bại thay vì âm thầm coi record đã được phục hồi. Kiểm tra API theo phiên bản Spring Kafka đang dùng. Nếu publish DLT thất bại, không để offset tiến qua record mà chưa được lưu an toàn.

Với `@RetryableTopic`, xác nhận `attempts` tính cả lần xử lý ban đầu, backoff phù hợp SLA, exception include/exclude đúng và DLT handler đã đăng ký. Non-blocking retry có giới hạn riêng về ordering, batch listener và container transaction; phải đối chiếu yêu cầu của luồng trước khi chọn.

## 3. Checklist thiết kế DLT topic

DLT là một Kafka topic bình thường nên cần cấu hình và vận hành như các topic khác.

- [ ] Tên DLT rõ ràng, nhất quán và không va chạm.
- [ ] Có quy tắc mapping từ topic gốc sang DLT.
- [ ] Số partition tương thích với cách recoverer định tuyến.
- [ ] Replication factor phù hợp yêu cầu chịu lỗi.
- [ ] Retention đủ dài cho thời gian điều tra và phê duyệt replay.
- [ ] Disk capacity tính theo kích thước payload và tốc độ phát sinh.
- [ ] ACL tách quyền ghi DLT, đọc DLT và quản trị replay.
- [ ] Có consumer group hoặc công cụ quản trị dành riêng cho DLT.
- [ ] Có cảnh báo khi DLT nhận record mới hoặc backlog tăng.
- [ ] Có quy trình lưu trữ/xóa dữ liệu sau thời hạn lưu giữ.

Với cấu hình mặc định thường gặp của `DeadLetterPublishingRecoverer`, DLT được đặt tên bằng cách nối hậu tố `.DLT` vào topic gốc và định tuyến về partition tương ứng. Nếu dùng destination resolver hoặc naming strategy riêng, phải kiểm tra quy tắc thực tế. Nếu resolver giữ nguyên partition number, DLT cần có partition tương ứng; nếu không, publish có thể thất bại vì partition đích không tồn tại.

`@RetryableTopic` có quy tắc đặt tên retry topic và DLT riêng. Không giả định tên topic của non-blocking retry giống DLT do recoverer mặc định tạo ra.

## 4. Checklist metadata cần giữ lại

Record trong DLT cần đủ thông tin để xác định nguồn gốc và quyết định cách phục hồi.

| Metadata | Mục đích |
|---|---|
| Event ID | Định danh nghiệp vụ ổn định để deduplicate |
| Original topic | Biết record xuất phát từ luồng nào |
| Original partition/offset | Truy lại vị trí record trong log gốc |
| Record key | Giữ quy tắc routing theo aggregate/key |
| Original timestamp | Biết thời điểm event được tạo |
| Consumer group/listener | Xác định luồng xử lý bị lỗi |
| Exception class | Phân loại loại lỗi |
| Exception message/stacktrace | Hỗ trợ điều tra trong giới hạn bảo mật |
| Retry/attempt metadata | Biết record đã trải qua những lần thử nào |
| Correlation/trace ID | Liên kết log và trace giữa các service |
| Schema/version | Đọc payload đúng phiên bản hợp đồng |

Spring Kafka bổ sung DLT headers chứa metadata nguồn gốc và exception theo phiên bản/cấu hình. Hãy xác nhận các header cần thiết được giữ khi record đi qua retry topic và recoverer.

- [ ] Event ID không bị tạo lại khi chuyển record sang DLT.
- [ ] Key được giữ nếu cần duy trì partitioning theo aggregate.
- [ ] Original topic, partition, offset và timestamp có thể tra cứu.
- [ ] Exception metadata không làm lộ secret hoặc dữ liệu nhạy cảm.
- [ ] Trace/correlation context đủ để tìm log.
- [ ] Header trùng hoặc header cũ được xử lý rõ khi replay.
- [ ] Payload và schema version được lưu đủ để deserialize về sau.

Không dùng event ID, order ID hoặc correlation ID làm metric tag có cardinality cao. Các định danh này phù hợp với log, trace và hệ thống tra cứu DLT.

## 5. Checklist consumer xử lý DLT

Có thể dùng listener riêng để lưu DLT record thành một case có trạng thái:

~~~java
@Component
public class OrdersDltListener {

    private final DltCaseService dltCaseService;

    public OrdersDltListener(DltCaseService dltCaseService) {
        this.dltCaseService = dltCaseService;
    }

    @KafkaListener(
            topics = "orders.DLT",
            groupId = "orders-dlt-operations"
    )
    public void handle(ConsumerRecord<String, OrderEvent> record) {
        dltCaseService.register(
                record.key(),
                record.value(),
                record.topic(),
                record.partition(),
                record.offset(),
                record.headers()
        );
    }
}
~~~

- [ ] DLT consumer group có ID riêng và ổn định.
- [ ] Listener lưu metadata nguồn gốc và event ID.
- [ ] DLT handler có timeout và retry phù hợp.
- [ ] Lỗi khi lưu case được quan sát và phục hồi.
- [ ] Không tự động gửi lỗi của DLT handler về chính DLT vô hạn.
- [ ] Có thể tạm dừng DLT consumer khi hệ thống quản lý case gặp sự cố.
- [ ] Có quyền truy cập và audit cho người điều tra.
- [ ] DLT backlog và tuổi record cũ nhất được theo dõi.

Nếu DLT handler chỉ đọc rồi ghi log, log phải đủ bền vững và có người chịu trách nhiệm theo dõi. Với luồng quan trọng, nên lưu case có trạng thái rõ ràng thay vì dựa vào log text.

## 6. Phân loại record trước khi replay

| Nhóm lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| Dependency tạm thời đã phục hồi | DB timeout, API 503 | Replay sau khi xác nhận dependency khỏe |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai format | Sửa dữ liệu có audit hoặc xử lý nghiệp vụ |
| Schema không tương thích | Consumer không đọc được payload | Triển khai reader tương thích rồi mới replay |
| Lỗi nghiệp vụ | Trạng thái đơn hàng không cho phép | Xác minh trạng thái và quyết định compensation |
| Lỗi cấu hình/quyền | ACL, credential, topic mapping | Sửa cấu hình/quyền trước khi replay |
| Lỗi code | Bug trong handler | Triển khai bản sửa, kiểm thử và canary replay |
| Tác dụng phụ chưa rõ | API có thể đã thực hiện nhưng client timeout | Reconcile với hệ thống đích trước khi replay |

- [ ] Đã xác định nguyên nhân gốc.
- [ ] Đã xác nhận lỗi được khắc phục hoặc có cách xử lý dữ liệu.
- [ ] Đã kiểm tra event có được xử lý một phần trước khi vào DLT hay không.
- [ ] Đã xác minh trạng thái database/API bên ngoài nếu có tác dụng phụ.
- [ ] Đã xác định replay có thể tạo duplicate hay không.
- [ ] Đã có người phê duyệt với luồng nghiệp vụ quan trọng.
- [ ] Đã ghi lý do chọn replay, sửa dữ liệu, compensation hoặc giữ nguyên DLT.

Không replay chỉ vì dependency đã hoạt động trở lại. Một request timeout có thể xảy ra sau khi API đích đã thực hiện nghiệp vụ; cần tra cứu theo idempotency key hoặc transaction ID trước khi gửi lại.

## 7. Checklist idempotency trước replay

Replay có thể khiến cùng event được xử lý lại. Consumer cần bảo vệ tác dụng phụ bằng event ID ổn định và thao tác idempotent.

- [ ] Event ID gốc được giữ nguyên khi replay.
- [ ] Consumer có unique constraint/inbox key cho event đã xử lý.
- [ ] Dấu dedup và business update nằm trong cùng database transaction.
- [ ] API ngoài dùng idempotency key ổn định nếu được hỗ trợ.
- [ ] Không tạo idempotency key mới cho mỗi lần replay kỹ thuật.
- [ ] Tác vụ không idempotent đã được kiểm tra/reconcile.
- [ ] Nếu cần thực hiện lại nghiệp vụ có chủ ý, đó là command mới có audit, không giả dạng replay kỹ thuật.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa gồm consumer name và event ID để Billing, Notification hoặc các consumer logic khác có thể xử lý cùng event độc lập. Không dùng một dấu dedup toàn cục khiến consumer này vô tình chặn nghiệp vụ của consumer khác.

## 8. Checklist quy trình replay

Replay nên là quy trình có kiểm soát, có audit và có khả năng dừng.

1. Chọn record theo event ID, thời gian, partition, offset hoặc case ID.
2. Kiểm tra nguyên nhân lỗi và trạng thái tác dụng phụ.
3. Chọn topic đích: topic gốc, retry topic hoặc topic phục hồi riêng.
4. Xác minh schema, serializer, key và headers.
5. Chạy dry-run để đếm record và kiểm tra mẫu payload.
6. Replay thử một record hoặc batch rất nhỏ.
7. Xác nhận consumer xử lý thành công và không tạo tác dụng phụ trùng.
8. Mở rộng batch theo tốc độ giới hạn.
9. Theo dõi lag, retry rate, DLT ingress và dependency latency.
10. Dừng replay nếu lỗi tăng, backlog tăng nhanh hoặc downstream quá tải.
11. Ghi số record thành công, thất bại, bỏ qua và còn chờ.
12. Đóng case và lưu audit.

- [ ] Có tiêu chí chọn record rõ ràng.
- [ ] Có dry-run và giới hạn số lượng mỗi batch.
- [ ] Có rate limit/throttle.
- [ ] Có thể pause hoặc hủy replay.
- [ ] Có checkpoint để tiếp tục sau khi replay job bị dừng.
- [ ] Có log replay ID, operator, thời gian, topic nguồn/đích và kết quả.
- [ ] Có cảnh báo khi replay gây tăng retry hoặc DLT mới.
- [ ] Có cơ chế ngăn hai operator replay cùng tập record đồng thời.

## 9. Replay bằng KafkaTemplate: publish và ack

Replay worker có thể đọc DLT record, publish lại vào topic đích và chỉ xác nhận record nguồn sau khi broker xác nhận publish thành công.

~~~java
ProducerRecord<String, OrderEvent> replayRecord =
        new ProducerRecord<>(
                targetTopic,
                dltRecord.key(),
                dltRecord.value()
        );

replayRecord.headers().add(
        "x-replay-id",
        replayId.getBytes(StandardCharsets.UTF_8)
);

replayRecord.headers().add(
        "x-replayed-from",
        dltRecord.topic().getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(replayRecord)
        .get(10, TimeUnit.SECONDS);
~~~

Đoạn code chỉ minh họa bước publish. Replay worker còn phải quản lý offset DLT, lỗi send, chọn header được chuyển tiếp và audit.

Với listener DLT dùng manual acknowledgment, không ack record nguồn trước khi publish đích được xác nhận. Tuy nhiên, nếu publish thành công rồi process crash trước khi commit offset DLT, record có thể được replay lần nữa. Đây là cửa sổ duplicate của quy trình at-least-once.

Nếu cần Kafka-to-Kafka atomicity, có thể cấu hình listener container transaction và dùng cùng transactional producer factory để publish record đích cùng offset DLT trong một Kafka transaction. Khi transaction commit, output replay và offset nguồn cùng có hiệu lực; khi rollback, cả hai cùng không được commit. Kiểm thử cấu hình thực tế và dùng consumer downstream đọc `read_committed` khi cần loại record aborted.

- [ ] Xác định replay là at-least-once hay transactional.
- [ ] Không giả định send future thành công và offset commit là một transaction nếu chưa cấu hình.
- [ ] Giữ event ID và key gốc.
- [ ] Chỉ chuyển tiếp header cần thiết; loại header lỗi cũ hoặc metadata không phù hợp.
- [ ] Thêm replay ID và thông tin audit riêng.
- [ ] Có timeout và xử lý lỗi publish.
- [ ] Kiểm thử crash giữa publish và commit offset.

## 10. Không chuyển tiếp mù quáng toàn bộ DLT headers

Record DLT thường chứa header exception và metadata nguồn gốc. Nếu replay toàn bộ headers rồi record tiếp tục thất bại, header lỗi cũ có thể bị nhầm với lần xử lý mới hoặc bị nhân bản.

Khi replay:

- Giữ correlation ID, trace context và event ID nếu còn hợp lệ.
- Giữ metadata nghiệp vụ cần cho consumer.
- Chuyển thông tin nguồn gốc DLT vào audit/replay header có tên rõ ràng.
- Không mang stacktrace hoặc exception message cũ sang như lỗi của lần thử mới.
- Xử lý header trùng lặp theo chính sách.
- Không giữ header chứa credential, secret hoặc dữ liệu nội bộ không cần thiết.

Không xóa thông tin gốc trước khi đã lưu vào audit. Người vận hành cần truy được record replay bắt nguồn từ DLT nào, partition/offset nào và case nào.

## 11. Replay theo batch và giới hạn tốc độ

Một DLT backlog lớn có thể chứa hàng nghìn hoặc hàng triệu record. Replay tất cả cùng lúc có thể tạo đợt tải lớn lên topic gốc và downstream.

- [ ] Chọn batch size phù hợp với kích thước payload và capacity downstream.
- [ ] Giới hạn số record/giây.
- [ ] Theo dõi consumer lag của topic đích.
- [ ] Theo dõi CPU, heap, database pool và API rate limit.
- [ ] Dừng replay khi dependency chuyển sang trạng thái suy giảm.
- [ ] Ưu tiên record theo SLA hoặc mức độ nghiệp vụ.
- [ ] Không làm đảo thứ tự aggregate nếu nghiệp vụ cần ordering.
- [ ] Có thể resume từ checkpoint mà không phát lại ngoài kiểm soát.

Nếu replay record cùng aggregate, hãy giữ key và cân nhắc thứ tự theo original timestamp/version. Kafka giữ thứ tự theo partition tại thời điểm publish mới; nó không tự sắp xếp lại event lịch sử theo offset của topic cũ sau khi replay.

## 12. Theo dõi DLT và replay

| Metric | Ý nghĩa |
|---|---|
| DLT ingress rate | Số record mới vào DLT theo thời gian |
| DLT backlog | Số record chưa được điều tra/xử lý |
| DLT oldest age | Tuổi record cũ nhất |
| DLT handler failures | Lỗi trong quy trình tiếp nhận DLT |
| Replay requested | Số record được chọn để replay |
| Replay published | Số record đã publish lại thành công |
| Replay failed | Số lần publish/replay thất bại |
| Replay duplicate | Số record bị phát lại hoặc deduplicate |
| Retry rate sau replay | Cho biết bản sửa đã giải quyết lỗi chưa |

- [ ] Có dashboard riêng cho topic gốc, retry topic và DLT.
- [ ] Có alert theo DLT ingress rate, backlog và oldest age.
- [ ] Có alert nếu DLT handler hoặc replay worker thất bại.
- [ ] Có metric replay theo kết quả.
- [ ] Metric tag có cardinality giới hạn; không dùng event ID làm tag.
- [ ] Log chứa event ID, original topic/partition/offset, replay ID và exception class.
- [ ] Trace/correlation ID có thể dùng để tìm luồng liên quan.
- [ ] Payload nhạy cảm không bị ghi vào log hoặc dashboard.

## 13. Retention, bảo mật và quyền truy cập

DLT có thể lưu dữ liệu lỗi lâu hơn topic chính. Cần coi đây là dữ liệu vận hành có thể chứa thông tin nhạy cảm.

- [ ] Retention phù hợp SLA điều tra và thời gian phê duyệt replay.
- [ ] Có giới hạn disk và cảnh báo dung lượng.
- [ ] ACL chỉ cho phép service/operator cần thiết đọc DLT.
- [ ] Quyền replay được tách khỏi quyền xem record.
- [ ] Payload nhạy cảm được bảo vệ bằng encryption/access policy phù hợp.
- [ ] Log/trace không lộ token, password, payment data hoặc secret.
- [ ] Có chính sách lưu/xóa DLT case và audit.
- [ ] Có người chịu trách nhiệm cho từng DLT topic quan trọng.

Không xóa DLT topic hoặc reset offset DLT để "dọn backlog" nếu chưa lưu trữ và phân loại record. Nếu cần loại bỏ record không thể phục hồi, phải có quyết định nghiệp vụ, audit và chính sách retention rõ ràng.

## 14. Runbook xử lý một record trong DLT

Khi nhận một DLT case, thực hiện theo trình tự:

1. Mở case bằng event ID và replay ID nếu đã từng replay.
2. Xác định original topic, partition, offset, consumer group và listener.
3. Đọc exception class, error code và retry metadata.
4. Tra log/trace theo correlation ID.
5. Kiểm tra trạng thái nghiệp vụ ở database và hệ thống ngoài.
6. Xác định lỗi dữ liệu, code, dependency, quyền hay cấu hình.
7. Quyết định sửa dữ liệu, deploy fix, chờ dependency, compensation hoặc replay.
8. Xác nhận idempotency và thứ tự event trước khi replay.
9. Replay thử một record và xác minh trạng thái cuối.
10. Ghi kết quả và đóng case hoặc chuyển cấp xử lý.

Một case nên có trạng thái như NEW, INVESTIGATING, READY_TO_REPLAY, REPLAYING, RESOLVED, COMPENSATED hoặc REJECTED. Tên trạng thái tùy hệ thống quản lý, nhưng cần phân biệt record đang chờ, đang điều tra, đã replay và không thể phục hồi.

## 15. Những lỗi vận hành thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Record biến mất sau lỗi | Offset được xử lý dù DLT publish thất bại | Kiểm tra recoverer send result và offset policy |
| DLT không có partition tương ứng | Resolver giữ partition gốc nhưng DLT ít partition hơn | Tạo đủ partition hoặc đổi resolver |
| DLT backlog tăng mãi | Không có DLT consumer/owner hoặc xử lý case chậm | Gán owner, alert và runbook |
| Replay tạo duplicate | Publish thành công nhưng offset DLT chưa commit | Idempotency hoặc Kafka transaction |
| Replay record lại vào DLT | Nguyên nhân gốc chưa sửa hoặc payload chưa được sửa | Phân loại lại và dừng replay tự động |
| Event sai thứ tự | Replay batch không giữ key/version/ordering | Replay theo aggregate và kiểm tra version |
| DLT handler tạo vòng lặp | Handler lỗi lại được gửi về chính DLT không giới hạn | Tách error handling và giới hạn recovery |
| Header lỗi bị lặp | Chuyển tiếp toàn bộ DLT headers qua nhiều lần replay | Lọc header và lưu metadata gốc vào audit |
| Replay làm downstream quá tải | Không throttle hoặc batch quá lớn | Giới hạn tốc độ và canary replay |
| Không biết ai replay record | Thiếu audit và replay ID | Ghi operator, lý do, thời gian và kết quả |

## 16. Checklist trước khi đưa vào production

### Retry và DLT configuration

- [ ] Đã chọn blocking retry hoặc non-blocking retry theo ordering/transaction.
- [ ] Exception retryable/non-retryable được phân loại rõ.
- [ ] BackOff và attempts có giới hạn.
- [ ] Recoverer publish DLT và lỗi publish được xử lý.
- [ ] DLT topic có partition, replication, retention và ACL phù hợp.
- [ ] Serializer/deserializer xử lý được payload DLT.
- [ ] Metadata nguồn gốc và event ID được giữ lại.

### DLT operations

- [ ] Có consumer/công cụ tiếp nhận DLT riêng.
- [ ] Có owner, dashboard, alert và runbook.
- [ ] DLT case được phân loại trước khi replay.
- [ ] Có audit cho sửa dữ liệu, replay và compensation.
- [ ] Có retention và quy trình lưu trữ/xóa an toàn.

### Replay safety

- [ ] Consumer idempotent theo event ID.
- [ ] API ngoài dùng idempotency key nếu có thể.
- [ ] Replay giữ key/event ID và chỉ chuyển tiếp header cần thiết.
- [ ] Đã xác định semantics at-least-once hay transactional replay.
- [ ] Có dry-run, canary, batch size và rate limit.
- [ ] Có checkpoint, pause/stop và cơ chế resume.
- [ ] Đã kiểm thử duplicate, crash window và ordering.
- [ ] Có quy trình reconciliation khi kết quả tác dụng phụ chưa rõ.

## 17. Checklist kiểm thử DLT và replay

Trước khi phát hành, kiểm tra các tình huống:

1. Listener lỗi retryable và cuối cùng thành công.
2. Listener lỗi đến hết retry và record vào DLT.
3. Exception non-retryable đi theo chính sách DLT dự kiến.
4. DLT publish thất bại không làm record nguồn bị xác nhận sai.
5. DLT handler lưu đúng payload, key, headers và metadata nguồn.
6. Replay một record sau khi sửa nguyên nhân gốc.
7. Replay hai lần cùng event ID không tạo tác dụng phụ trùng.
8. Process crash sau publish nhưng trước offset commit.
9. Replay nhiều record có throttle và checkpoint.
10. Record replay thất bại lại được điều tra theo case mới.
11. Replay giữ ordering theo aggregate khi nghiệp vụ yêu cầu.
12. DLT retention, ACL và dashboard hoạt động đúng.

Với integration test, dùng Embedded Kafka hoặc Testcontainers để xác nhận record thực sự được publish và consume. Mock recoverer có thể kiểm tra logic gọi hàm, nhưng không chứng minh topic, partition, serializer, ACL hoặc transaction hoạt động trên broker.

## 18. Biểu mẫu thông tin cho một DLT case

Khi tạo case, nên ghi tối thiểu:

| Trường | Giá trị cần ghi |
|---|---|
| Case ID | ID quản lý sự cố |
| Event ID | Định danh event gốc |
| Original topic/partition/offset | Vị trí record ban đầu |
| DLT topic/partition/offset | Vị trí record trong DLT |
| Consumer group/listener | Luồng xử lý bị lỗi |
| Exception/error code | Nguyên nhân quan sát được |
| First failure time | Thời điểm lỗi đầu tiên |
| Last attempt time | Thời điểm thử cuối |
| Retry count | Số lần thử theo semantics đã xác định |
| Business impact | Tác động tới nghiệp vụ |
| Root cause | Nguyên nhân đã xác minh |
| Decision | Replay, repair, compensate hoặc reject |
| Replay ID/operator | Định danh và người thực hiện |
| Result | Success, failed, duplicate hoặc pending |

Biểu mẫu này giúp người vận hành không phải suy đoán từ một dòng log đơn lẻ và tạo lịch sử có thể kiểm toán.

DLT chỉ hữu ích khi đi kèm quy trình điều tra và phục hồi. Hãy bảo đảm record được publish an toàn, giữ metadata nguồn gốc, phân loại nguyên nhân trước replay, kiểm tra idempotency và giới hạn tốc độ phát lại. Với Spring Kafka, kết hợp retry/recoverer đúng cấu hình, DLT consumer riêng, audit, metric và runbook sẽ giúp xử lý record lỗi có trách nhiệm mà không làm mất dữ liệu hoặc nhân đôi tác dụng phụ nghiệp vụ.

