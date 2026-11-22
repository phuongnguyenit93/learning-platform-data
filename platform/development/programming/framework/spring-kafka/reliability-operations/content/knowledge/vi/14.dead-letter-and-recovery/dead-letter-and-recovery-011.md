# DltHandler

Trong hệ thống sử dụng Spring Kafka, một record có thể thất bại dù đã được thử xử lý lại nhiều lần. Chẳng hạn, consumer nhận sự kiện thanh toán nhưng payload không hợp lệ, hoặc dịch vụ downstream tiếp tục trả về lỗi sau khi hết ngân sách retry. Nếu tiếp tục xử lý vô hạn, record lỗi có thể chiếm tài nguyên và làm tăng độ trễ của những record phía sau. Một phương án phục hồi phổ biến là đưa record sang **dead-letter topic (DLT)** để giữ lại bằng chứng và xử lý riêng.

`@DltHandler` là annotation của Spring Kafka dùng để chỉ định **phương thức xử lý các record được tiêu thụ từ DLT** trong cơ chế non-blocking retry do `@RetryableTopic` quản lý. Phương thức này không phải nơi đưa record vào DLT lần đầu; việc chuyển record sang DLT được thực hiện bởi retry-topic infrastructure và recoverer. DltHandler là điểm tiếp nhận **sau khi record đã tới DLT**.

Phân biệt hai bước này rất quan trọng khi thiết kế một pipeline đáng tin cậy:

- **Publish vào DLT:** Giữ lại record đã thất bại để không chặn xử lý trên topic chính, với metadata cho biết nguồn gốc và nguyên nhân.
- **Consume bằng DltHandler:** Ghi nhận sự cố, phân loại, lưu trạng thái, tạo thông báo hoặc đưa record vào quy trình điều tra/replay có kiểm soát.

Một DltHandler tốt không nhất thiết tự sửa record hay gửi nó ngay về topic chính. Mục tiêu là tạo một điểm quan sát và phục hồi có kiểm soát, tránh mất dữ liệu và tránh lặp tác động nghiệp vụ.

## 1. DLT nằm ở đâu trong luồng retry?

Trong non-blocking retry, record lỗi được publish sang những retry topic có thời gian chờ phù hợp. Khi record không còn đủ điều kiện retry, nó được định tuyến tới DLT nếu chính sách có cấu hình DLT.

~~~text
Producer
   |
   v
orders.events
   |
   v
@KafkaListener xử lý nghiệp vụ
   |
   +---- Thành công ----------------> Commit/ack theo container
   |
   +---- Exception
             |
             v
       Retry classification
             |
       +-----+-----------------------+
       |                             |
    Retryable                     Non-retryable
       |                             |
       v                             |
  Retry topic                       |
       |                             |
       +-- Thành công --> Xử lý xong |
       |                             |
       +-- Hết attempt --------------+
                                     |
                                     v
                                  DLT topic
                                     |
                                     v
                              DLT listener container
                                     |
                                     v
                                 @DltHandler
                                     |
                             Ghi audit / tạo ticket
                             / lưu trạng thái recovery
~~~

Tên topic và số bước retry tùy cấu hình của `@RetryableTopic` hoặc API tạo retry topology. Sơ đồ chỉ mô tả các thành phần chức năng.

### 1.1. Ba khái niệm không nên nhầm

| Khái niệm | Vai trò | Khi nào chạy? |
|---|---|---|
| `@KafkaListener` | Xử lý record ở topic chính và các endpoint retry được infrastructure tạo | Khi container nhận record |
| `DeadLetterPublishingRecoverer` | Publish record lỗi sang topic đích sau khi cơ chế xử lý lỗi quyết định recovery | Khi cần recover record đã thất bại |
| `@DltHandler` | Tiêu thụ record đã nằm trên DLT trong topology non-blocking | Khi DLT consumer được khởi động và poll record |

`@DltHandler` không phải tên chung của mọi listener tự subscribe DLT. Nếu ứng dụng tự tạo một `@KafkaListener(topics = "orders.events-dlt")`, đó là listener bình thường cho DLT, không nhất thiết là một endpoint của retry-topic infrastructure.

## 2. Khi nào cần @DltHandler?

Một hệ thống có DLT cần quyết định ai là người chịu trách nhiệm xử lý những record đã đi vào đó. `@DltHandler` phù hợp khi:

1. Ứng dụng dùng `@RetryableTopic` hoặc retry-topic infrastructure.
2. Muốn định nghĩa cùng class một phương thức tiếp nhận record DLT.
3. Muốn ghi audit và metadata nguyên nhân lỗi.
4. Muốn tạo cảnh báo/ticket hoặc trạng thái chờ điều tra.
5. Muốn xây dựng quy trình replay có người phê duyệt hay tự động theo điều kiện an toàn.

Nếu nhu cầu chỉ là **giữ record trên DLT để đội vận hành dùng công cụ ngoài kiểm tra**, không nhất thiết phải triển khai một DltHandler tự động đọc và xử lý mọi record. Một số hệ thống chủ động không chạy DLT consumer mặc định để dữ liệu ở lại topic cho đến khi quy trình kiểm tra sẵn sàng.

### 2.1. Không có DltHandler thì sao?

Trong cấu hình non-blocking retry của Spring Kafka, khi không khai báo `@DltHandler`, framework có thể cung cấp hành vi xử lý DLT mặc định, chẳng hạn ghi log. Điều này **không tương đương** với một quy trình lưu ticket hoặc đối soát nghiệp vụ.

Không nên dựa vào default logging để kết luận rằng record trong DLT đã được quản lý đầy đủ. Hãy xác định rõ ownership của DLT, retention, cơ chế cảnh báo và cách replay.

## 3. Ví dụ @RetryableTopic kết hợp @DltHandler

Ví dụ ứng dụng thanh toán tiêu thụ sự kiện tạo đơn hàng. Lỗi dependency tạm thời được retry; payload sai nghiệp vụ được chuyển sang recovery nhanh hơn.

~~~java
@Component
public class BillingOrderListener {

    private final BillingService billingService;
    private final DltAuditService dltAuditService;

    public BillingOrderListener(
            BillingService billingService,
            DltAuditService dltAuditService) {
        this.billingService = billingService;
        this.dltAuditService = dltAuditService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1_000,
                    multiplier = 2.0,
                    maxDelay = 10_000),
            include = {
                    TemporaryPaymentGatewayException.class
            },
            exclude = {
                    InvalidOrderEventException.class
            },
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders.events",
            groupId = "billing")
    public void onOrder(OrderEvent event) {
        billingService.processIdempotently(event);
    }

    @DltHandler
    public void onDlt(
            ConsumerRecord<String, OrderEvent> record) {
        dltAuditService.persistIfAbsent(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value());
    }
}
~~~

Ví dụ giả định các domain class và service đã được định nghĩa. `DltAuditService.persistIfAbsent(...)` là phương thức nghiệp vụ do ứng dụng tự xây dựng, không phải API có sẵn của Spring Kafka. Trong hệ thống thật, nên sử dụng event id, nguồn record và ràng buộc dữ liệu để bảo đảm tác vụ ghi audit idempotent.

Trong cấu hình minh họa, `attempts = "4"` là **tổng số lần thử theo non-blocking retry policy**, bao gồm lần xử lý ban đầu. Nếu record thất bại liên tục bằng exception được phép retry, nó có thể trải qua một lần tại topic chính và tối đa ba lần tại các retry endpoint trước khi vào DLT. Exception nằm trong `exclude` có thể được chuyển thẳng tới DLT mà không phải sử dụng tất cả lượt retry.

### 3.1. Tại sao đặt @DltHandler trong cùng class?

`@DltHandler` hoạt động gắn với endpoint được thiết lập bởi `@RetryableTopic`. Đặt nó trong cùng bean chứa `@KafkaListener` và cấu hình retry giúp framework xác định handler DLT tương ứng.

Không nên tạo một class độc lập chỉ có `@DltHandler` rồi kỳ vọng framework tự liên kết nó với mọi listener. Nếu muốn một service xử lý DLT chung, hãy gọi service ấy từ các DltHandler tương ứng, hoặc thiết kế một listener DLT độc lập với subscription và ownership rõ ràng.

Nếu ứng dụng có nhiều listener và nhiều retry topology, hãy xác định chính xác DltHandler nào xử lý từng DLT. Tùy phiên bản và cách đăng ký, các ràng buộc về số lượng/phạm vi phương thức `@DltHandler` có thể khác; đừng giả định một handler sẽ tự áp dụng toàn cục.

## 4. DltHandler nhận được dữ liệu gì?

DltHandler là một message listener. Nó có thể nhận payload được deserializer chuyển đổi hoặc `ConsumerRecord`, tùy cách khai báo method và container factory.

Các thông tin thường cần khi phục hồi:

- Topic DLT hiện tại.
- Partition và offset của record trên DLT.
- Key và payload record.
- Headers có thông tin nguồn gốc, exception và metadata retry.
- Event id/correlation id do producer cung cấp.
- Timestamp ghi nhận lỗi và thời điểm DLT consumer xử lý.

`ConsumerRecord.topic()` trong DltHandler trả về **tên DLT hiện tại**, không phải mặc định topic gốc. Tương tự, `record.offset()` là offset trên DLT; nó không bằng offset của record nguồn vì mỗi topic có log và offset riêng.

Muốn biết topic/partition/offset gốc, hãy đọc những header DLT tương ứng.

## 5. Các header thường gặp ở DLT

Spring Kafka sử dụng header để lưu thông tin record gốc và nguyên nhân lỗi khi publish đến DLT. Những constant thường dùng nằm trong `KafkaHeaders`.

| Header | Nội dung | Ứng dụng |
|---|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic gốc của record | Truy nguyên nguồn |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition gốc | Khoanh vùng partition lỗi |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset gốc | Đối soát/replay |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group gốc nếu metadata này có sẵn | Xác định consumer chịu trách nhiệm |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên class đầy đủ của exception | Nhóm lỗi |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message | Chẩn đoán nguyên nhân |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace | Điều tra chi tiết |

**Lưu ý về phiên bản:** Tên và sự hiện diện của từng header có thể thay đổi theo phiên bản Spring Kafka, loại exception và cách cấu hình recoverer. Một header có thể vắng mặt, được thay thế hoặc có nhiều bản trong chuỗi retry. Code vận hành phải xử lý null.

Không nên lưu nguyên exception message hoặc stack trace dài vào metrics tag. Chúng có cardinality cao và có thể chứa dữ liệu nhạy cảm.

### 5.1. Đọc header chuỗi an toàn

Ví dụ ghi lại topic nguồn và exception class trong DltHandler:

~~~java
@DltHandler
public void onDlt(ConsumerRecord<String, OrderEvent> record) {

    String originalTopic = utf8Header(
            record.headers(),
            KafkaHeaders.DLT_ORIGINAL_TOPIC);

    String exceptionClass = utf8Header(
            record.headers(),
            KafkaHeaders.DLT_EXCEPTION_FQCN);

    log.error(
            "DLT received: currentTopic={}, " +
            "dltPartition={}, dltOffset={}, " +
            "originalTopic={}, exceptionClass={}",
            record.topic(),
            record.partition(),
            record.offset(),
            originalTopic,
            exceptionClass);

    dltAuditService.persistIfAbsent(record, originalTopic);
}

private static String utf8Header(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(
            header.value(), StandardCharsets.UTF_8);
}
~~~

Trong một class Java đầy đủ, helper `utf8Header` cần được đặt đúng phạm vi, và các import như `Headers`, `Header`, `StandardCharsets` phải được bổ sung. Đoạn code minh họa cách đọc header chuỗi; **không** dùng cách giải mã UTF-8 cho mọi header dạng số.

### 5.2. Đọc offset/partition gốc

Offset và partition là dữ liệu số. Không giả định các header này chứa chữ số UTF-8. Hãy đọc theo định dạng mà Spring Kafka đang dùng ở phiên bản triển khai, hoặc dùng header mapper/argument conversion đã được kiểm chứng.

Ví dụ về nguyên tắc đọc raw bytes:

~~~java
private static Long originalOffset(Headers headers) {
    Header header = headers.lastHeader(
            KafkaHeaders.DLT_ORIGINAL_OFFSET);

    if (header == null ||
            header.value() == null ||
            header.value().length != Long.BYTES) {
        return null;
    }

    return ByteBuffer.wrap(header.value()).getLong();
}
~~~

Ví dụ giả định offset gốc được mã hóa dưới dạng `long` 8 byte theo byte order của giao thức header trong phiên bản tương ứng. Hãy kiểm tra encoding trước khi đưa số này vào hệ thống đối soát, đặc biệt nếu có custom serializer/recoverer.

### 5.3. Có nên dùng @Header không?

Có thể khai báo tham số `@Header` khi Spring Messaging hỗ trợ chuyển đổi header tương ứng:

~~~java
@DltHandler
public void onDlt(
        OrderEvent event,
        @Header(
                name = KafkaHeaders.DLT_ORIGINAL_TOPIC,
                required = false)
        String originalTopic) {

    dltAuditService.persistEvent(event, originalTopic);
}
~~~

Trong một số cấu hình, header vẫn là `byte[]` và việc chuyển đổi sang `String` phụ thuộc message converter. Đối với DLT quan trọng, hãy dùng cách đọc đã kiểm thử trên hệ thống thực tế, và luôn xử lý header thiếu hoặc không đúng định dạng.

## 6. Cấu hình chính sách DLT

`@RetryableTopic` cho phép điều chỉnh chiến lược xử lý khi lỗi ở DLT. Các lựa chọn thuộc `DltStrategy` được Spring Kafka cung cấp trong những phiên bản hỗ trợ, thường gồm:

| Chiến lược | Ý nghĩa ở mức vận hành | Cần lưu ý |
|---|---|---|
| `ALWAYS_RETRY_ON_ERROR` | Có thể publish lại record về DLT khi xử lý DLT thất bại | Nguy cơ lặp DLT và tăng tải nếu handler lỗi liên tục |
| `FAIL_ON_ERROR` | Không dùng chiến lược publish lại DLT như trên khi handler lỗi | Phải xác định cách container xử lý lỗi và offset để tránh bỏ sót |
| `NO_DLT` | Không cấu hình DLT cho topology tương ứng | Không có endpoint DLT để gắn DltHandler theo luồng đó |

Ví dụ chọn chiến lược theo yêu cầu vận hành:

~~~java
@RetryableTopic(
        attempts = "3",
        dltStrategy = DltStrategy.FAIL_ON_ERROR,
        dltTopicSuffix = "-dlt")
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void listen(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

Giá trị mặc định của chiến lược và hành vi với exception fatal có thể khác theo phiên bản. Với Spring Kafka đời mới, một số exception được xem là fatal có thể không được tiếp tục republish vào DLT ngay cả khi đang dùng chiến lược tự retry trên DLT. Hãy xác nhận trong phiên bản đang chạy.

**Quan trọng:** `FAIL_ON_ERROR` không mặc nhiên có nghĩa record sẽ được bỏ qua vĩnh viễn hay container sẽ dừng hoàn toàn. Hành vi cụ thể còn tùy error handler, acknowledgement, cấu hình DLT và phiên bản. Cần kiểm thử đường lỗi trước khi áp dụng trong production.

## 7. Điều gì xảy ra khi DltHandler ném exception?

DltHandler cũng là một listener nên có thể lỗi khi ghi database audit, gọi hệ thống ticket hoặc gửi notification. Nếu exception bị ném ra, cơ chế xử lý DLT sẽ áp dụng chính sách lỗi đã cấu hình.

Ví dụ:

~~~text
DLT record đến DltHandler
         |
         +--- Audit commit thành công
         |           |
         |           v
         |    Handler trả thành công
         |           |
         |           v
         |    DLT offset được container
         |    xử lý theo ack policy
         |
         +--- Audit database timeout
                     |
                     v
                Exception
                     |
                     v
             DLT error policy
               /         \
       Publish lại DLT   Error handling khác
       (nếu cấu hình)    (theo strategy/version)
~~~

Nếu mặc định hoặc cấu hình cho phép republish về chính DLT, một lỗi persistent trong DltHandler có thể khiến cùng một sự kiện được phát lại nhiều lần. Điều này tạo thêm record DLT và có thể làm retention, lag, storage và alert tăng nhanh.

Để giảm rủi ro:

- Giữ DltHandler đơn giản, ngắn và có khả năng idempotent.
- Tránh gọi nhiều dependency phức tạp trong DltHandler nếu không cần thiết.
- Cấu hình timeout và giới hạn retry rõ ràng ở các dependency.
- Dùng unique event id hoặc source identity để ghi audit một lần.
- Cảnh báo khi DLT handler liên tục ném exception.
- Có đường phục hồi thủ công nếu hệ thống audit/ticket đang không khả dụng.

## 8. DltHandler nên làm gì?

Một DltHandler có thể thực hiện nhiều công việc, nhưng nên tách **ghi nhận an toàn** khỏi **phục hồi nghiệp vụ phức tạp**.

### 8.1. Ghi nhận record lỗi

Nội dung bản ghi audit có thể gồm:

- Event id và business key.
- Topic/partition/offset gốc.
- Topic/partition/offset trên DLT.
- Exception class và nhóm nguyên nhân.
- Timestamp phát hiện lỗi.
- Số attempt nếu metadata phù hợp có mặt.
- Trạng thái hiện tại: `NEW`, `UNDER_REVIEW`, `READY_FOR_REPLAY`, `REPLAYED` hoặc `IGNORED_WITH_REASON`.
- Người phụ trách hoặc liên kết ticket.

Không nên lưu toàn bộ stack trace không giới hạn vào một cột ngắn hoặc một metric tag; có thể lưu bản đầy đủ vào kho log bảo mật và tham chiếu bằng correlation id.

### 8.2. Gửi cảnh báo có giới hạn

DltHandler có thể phát một sự kiện cảnh báo hoặc tạo ticket. Nhưng nếu mỗi record DLT tạo một email hoặc pager alert, một lỗi schema trên hàng nghìn record có thể làm ngập kênh cảnh báo.

Nên nhóm theo:

- Service và listener.
- Exception class.
- Topic nguồn.
- Khoảng thời gian.
- Mức độ ảnh hưởng của sự kiện nghiệp vụ.

Ví dụ, gửi một alert cho “1.200 sự kiện thuộc topic orders.events bị validation error trong 5 phút” sẽ hữu ích hơn 1.200 alert riêng biệt.

### 8.3. Chuyển sang workflow review

Một pattern phổ biến:

1. DltHandler lưu metadata với trạng thái `NEW`.
2. Một job hoặc dashboard nội bộ hiển thị danh sách record cần xử lý.
3. Người vận hành điều tra và phân loại nguyên nhân.
4. Nếu có thể phục hồi, ghi quyết định `READY_FOR_REPLAY`.
5. Công cụ replay độc lập phát lại có kiểm soát.
6. Hệ thống đối soát kết quả và đánh dấu `REPLAYED`.

Thiết kế này giữ DltHandler nhẹ và tránh lẫn xử lý sự cố với logic nghiệp vụ chính.

## 9. DltHandler không nên làm gì?

### 9.1. Không tự động phát lại vô hạn

Nếu handler vừa nhận record DLT đã publish ngay về topic chính, một record lỗi không thay đổi có thể chạy vòng:

~~~text
Topic chính -> retry -> DLT -> topic chính -> retry -> DLT ...
~~~

Vòng lặp tiêu tốn tài nguyên, làm tăng số record và có thể che khuất nguyên nhân. Chỉ replay khi có bằng chứng dữ liệu, code hoặc dependency đã được sửa; có giới hạn số lần và một quy trình kiểm soát.

### 9.2. Không ack trước khi lưu kết quả phục hồi bền vững

Nếu thiết kế yêu cầu DltHandler ghi audit vào database, listener chỉ nên trả về thành công sau khi database transaction đã commit. Việc chỉ gửi task sang executor rồi trả về có thể khiến offset DLT tiến lên trong khi audit task chưa chạy.

Không coi “log.info đã được gọi” là một giao dịch bền vững. Log shipping có thể thất bại hoặc log retention không đáp ứng chính sách lưu dữ liệu.

### 9.3. Không làm thay đổi kết quả nghiệp vụ tùy tiện

Một record vào DLT có thể đã thực hiện một phần side effect trước khi thất bại. Nếu DltHandler tự “chữa” bằng cách gửi lệnh bồi hoàn hoặc gọi lại API mà không đối soát, tác động có thể bị nhân đôi.

Đối với tài chính, thanh toán hoặc tồn kho, cần trạng thái nghiệp vụ, idempotency key và quy trình đối soát trước khi thực hiện lại thao tác.

## 10. Thiết kế idempotent cho DltHandler

Kafka và DLT thường vận hành theo at-least-once. Một record DLT có thể được giao lại sau khi handler đã ghi audit nhưng offset chưa commit; DLT cũng có thể nhận nhiều bản của cùng sự kiện nếu quá trình publish/recovery được thực hiện lại.

Do đó, DltHandler cần có khóa idempotency.

### 10.1. Dùng event id

Nếu producer gửi event id ổn định, có thể dùng event id kết hợp consumer role hoặc business operation làm khóa:

~~~sql
CREATE TABLE dlt_cases (
    event_id VARCHAR(120) NOT NULL,
    consumer_group VARCHAR(120) NOT NULL,
    original_topic VARCHAR(255),
    original_partition INTEGER,
    original_offset BIGINT,
    exception_class VARCHAR(255),
    status VARCHAR(40) NOT NULL,
    first_seen_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    PRIMARY KEY (event_id, consumer_group)
);
~~~

Ví dụ khóa trên có ý nghĩa nếu mỗi event chỉ cần một case DLT cho từng consumer group. Nếu cùng event có thể xuất hiện trên nhiều topic hoặc nhiều flow nghiệp vụ độc lập, cần mở rộng composite key theo hợp đồng thực tế.

Không nên tạo khóa bằng **offset DLT** nếu mục tiêu là deduplicate cùng event được publish lại nhiều lần: các bản republish có thể nhận offset DLT khác nhau.

### 10.2. Nếu không có event id?

Có thể dùng một tổ hợp identity phù hợp với nghiệp vụ, ví dụ topic + partition + offset nguồn **và** consumer group, nếu metadata nguồn đáng tin cậy và đủ duy nhất cho phạm vi cần theo dõi.

Nhưng trong một số luồng replay hoặc copy dữ liệu, source identity có thể thay đổi. Vì vậy, một event id do producer tạo và giữ nguyên qua retry/DLT thường dễ quản lý hơn.

## 11. Ngữ nghĩa offset ở DLT

Có hai nhóm offset cần phân biệt:

1. **Offset nguồn**: vị trí record trong topic chính hoặc topic đã phát sinh lỗi.
2. **Offset DLT**: vị trí record sau khi được publish vào DLT.

Một record có thể:

~~~text
Topic: orders.events, partition 2, offset 847
                    |
                    v
Retry topic: orders.events-retry-..., offset 58
                    |
                    v
DLT topic: orders.events-dlt, partition 2, offset 310
~~~

Các offset trên là ví dụ; Kafka không duy trì cùng số offset qua các topic. DLT handler được gọi với record của DLT, nên `record.offset()` trong ví dụ sẽ là 310, không phải 847.

Commit offset DLT chỉ xác nhận **tiến độ tiêu thụ trên DLT** theo container/ack policy. Nó không có tác dụng “rollback” committed offset của consumer group trên topic chính. Nếu muốn phát lại nghiệp vụ, thường phải publish một record mới sang topic phù hợp hoặc dùng một workflow replay có kiểm soát.

### 11.1. Tránh coi tiêu thụ DLT là xóa dữ liệu

Kafka không tự xóa record khi consumer commit offset. Dữ liệu DLT vẫn tồn tại cho đến khi retention/compaction policy áp dụng. Tuy nhiên, consumer group của DLT có thể không đọc lại record đó theo offset hiện tại.

Vì vậy, nếu DltHandler chỉ log rồi trả thành công, record có thể vẫn nằm trong Kafka nhưng không được DLT consumer đọc lại ở các lần poll tiếp theo. Khi cần xử lý lâu dài, phải có storage/index hoặc quy trình truy xuất DLT độc lập với committed offset.

## 12. Serializer và deserializer khi nhận DLT

DLT record có thể chứa payload không còn deserialize được theo kiểu domain object bình thường. Đặc biệt, lỗi gốc có thể xuất hiện **trước khi listener chính chạy**, ví dụ:

- Bytes không đúng định dạng JSON/Avro/Protobuf.
- Payload không phù hợp với schema.
- Header type hoặc class mapping không hợp lệ.
- Converter không tạo được Java object.

Nếu DltHandler khai báo `ConsumerRecord<String, OrderEvent>`, nhưng DLT consumer không thể deserialize value thành `OrderEvent`, handler có thể không nhận được record. Khi đó DLT consumer lại gặp lỗi deserialize.

### 12.1. ErrorHandlingDeserializer

Spring Kafka cung cấp `ErrorHandlingDeserializer` để xử lý lỗi tại tầng deserialize và đưa thông tin lỗi cho cơ chế recovery. Cấu hình delegate serializer/deserializer và DLT publisher phải hỗ trợ kiểu payload lỗi.

Một số record DLT có thể mang raw bytes thay vì domain object nếu lỗi gốc là deserialization. Do đó, đừng mặc định rằng mọi DLT record đều có cùng payload type.

### 12.2. Khi cần giữ raw bytes

Nếu môi trường thường nhận payload lỗi schema, có thể xây dựng một DLT consumer hoặc handler chuyên biệt nhận `byte[]`, sau đó lưu raw payload (có kiểm soát bảo mật), schema metadata và exception. Cần thiết kế topic, converter và serializer nhất quán.

Không cố convert một payload không hợp lệ thành domain object bằng cách retry vô hạn. Hãy giữ bằng chứng và sửa producer/schema/consumer trước khi replay.

## 13. Bảo mật dữ liệu DLT

DLT thường chứa các record lỗi khó xử lý, có thể bao gồm dữ liệu nhạy cảm, key định danh, exception message và stack trace. Vì vậy:

- Chỉ cấp quyền đọc DLT cho service và nhân sự được phép.
- Hạn chế quyền publish hoặc replay.
- Không log payload chứa thông tin nhạy cảm.
- Mã hóa và áp dụng retention theo chính sách dữ liệu.
- Tránh đưa dữ liệu cá nhân vào metric label.
- Kiểm tra stack trace có chứa secret, URL nội bộ hoặc token không.
- Ghi audit khi một người thực hiện replay hoặc quyết định bỏ qua record.

Nếu dữ liệu không được phép lưu ngoài một số vùng bảo mật, DLT và hệ thống audit/ticket phải tuân thủ cùng ranh giới dữ liệu.

## 14. Cấu hình DLT handler không tự chạy

Một số hệ thống muốn publish vào DLT tự động nhưng **không tiêu thụ DLT ngay**, vì record cần được đội vận hành review trước. Các phiên bản Spring Kafka hỗ trợ có thuộc tính như `autoStartDltHandler` trên `@RetryableTopic` để điều khiển việc khởi động listener DLT.

Ví dụ:

~~~java
@RetryableTopic(
        attempts = "4",
        autoStartDltHandler = "false")
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void handle(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

Trong cấu hình dạng này, DLT vẫn là đích publish nếu topology tạo DLT, nhưng DLT endpoint không tự động tiêu thụ cho đến khi được khởi động bằng lifecycle management phù hợp.

Tên property, giá trị string/boolean, cách điều khiển endpoint và phạm vi hỗ trợ phụ thuộc Spring Kafka version. Khi áp dụng, cần kiểm tra danh sách listener container thực tế, không chỉ dựa vào annotation.

### 14.1. Hậu quả của việc không chạy DLT consumer

- DLT backlog sẽ tăng khi có record mới.
- DLT consumer lag không phải lúc nào cũng là sự cố; nó có thể phản ánh chính sách review.
- Cần monitoring về tuổi record và khoảng thời gian trước khi retention xóa dữ liệu.
- Phải có công cụ hoặc lịch xử lý DLT được chủ động vận hành.
- Không nhầm “DLT handler không chạy” với “DLT publisher đã thất bại”.

## 15. DLT có cần cùng số partition với topic chính?

Khi publish DLT, recoverer có thể cố giữ partition gốc nếu topology và cấu hình hỗ trợ. Để làm được điều này, DLT thường cần có partition tương ứng. Nếu DLT ít partition hơn hoặc tên partition không phù hợp, publish có thể thất bại.

Một số cấu hình recoverer cho phép trả về partition không xác định để producer chọn partition thay thế. Điều này giúp publish linh hoạt hơn nhưng có thể làm thay đổi khả năng truy vết theo partition.

Trước production, xác nhận:

1. DLT topic tồn tại hoặc có cơ chế provisioning được kiểm soát.
2. DLT có partition count đủ cho chiến lược routing.
3. Replication factor và min.insync.replicas phù hợp độ bền yêu cầu.
4. Producer publish DLT có ACL và serializer đúng.
5. Retention DLT đủ dài cho quy trình xử lý.
6. Có cảnh báo khi DLT publish lỗi.

Không nên chỉ tăng partition DLT mà không cân nhắc tính nhất quán với routing và quy trình replay.

## 16. Recovery thành công có nghĩa gì?

Cần định nghĩa chính xác từ “thành công” trong hệ thống:

- **Đã publish vào DLT:** Record đã được broker DLT xác nhận theo producer configuration.
- **Đã tiêu thụ ở DLT:** DLT listener đã nhận record.
- **Đã ghi audit:** DltHandler đã lưu một bản ghi bền vững.
- **Đã được điều tra:** Người/phần mềm đã phân loại nguyên nhân.
- **Đã replay:** Record đã được publish lại theo quyết định recovery.
- **Đã hoàn tất nghiệp vụ:** Side effect cuối cùng đã thành công và được đối soát.

Các trạng thái không đồng nghĩa. Một DltHandler trả về bình thường có thể chỉ chứng minh “đã ghi audit”, chứ không chứng minh sự kiện đã được xử lý thành công ở tầng nghiệp vụ.

Hãy thể hiện các trạng thái này riêng trong database hoặc dashboard. Không dùng duy nhất một trường `success = true` mà không mô tả thành công của bước nào.

## 17. Replay từ DLT

Replay là quá trình xử lý lại record đã được chuyển sang DLT, thường sau khi nguyên nhân thất bại đã được sửa.

Quy trình tham khảo:

1. Xác định event, topic nguồn, exception và trạng thái nghiệp vụ.
2. Kiểm tra record đã có side effect một phần hay chưa.
3. Xác nhận bản sửa code/schema/dependency đã triển khai.
4. Chọn tập record để replay và giới hạn tốc độ.
5. Duy trì event id/correlation id gốc.
6. Publish tới topic hoặc workflow recovery đã được thiết kế.
7. Theo dõi retry/DLT mới phát sinh.
8. Đối soát kết quả nghiệp vụ.
9. Ghi audit người hoặc hệ thống đã quyết định replay.

### 17.1. Không replay nguyên xi mọi record

Một record sai schema có thể cần được chuyển đổi sang schema mới. Một sự kiện thanh toán có kết quả không rõ có thể cần đối soát trước khi gọi API. Một event đã được xử lý thành công qua đường khác nên được đánh dấu hoàn tất chứ không nhất thiết gửi lại.

Replay thiếu kiểm soát có thể tái tạo lỗi, phá thứ tự nghiệp vụ hoặc nhân đôi side effect.

### 17.2. Metadata replay

Khi phát lại, có thể bổ sung metadata:

- Event id gốc.
- Replay request id.
- Thời điểm replay.
- Nguồn DLT và lý do replay.
- Phiên bản code/schema sau sửa.
- Người hoặc automation phê duyệt.

Các header DLT của lần lỗi cũ không nhất thiết nên được đưa nguyên xi làm “nguyên nhân hiện tại”. Phân biệt metadata **nguồn gốc** và metadata **của lần xử lý mới** để tránh nhầm khi record tiếp tục lỗi.

## 18. Metrics và alert dành cho DltHandler

Một dashboard phục hồi không nên chỉ đếm số record DLT. Cần nhìn được record đi qua những bước nào và đang bị kẹt ở đâu.

| Metric | Ý nghĩa |
|---|---|
| DLT incoming rate | Tốc độ record mới đi vào DLT |
| DLT consumer lag | Số record DLT còn chưa được listener tiêu thụ |
| DltHandler processing duration | Thời gian xử lý một record DLT |
| DltHandler failure rate | Tỷ lệ handler thất bại |
| DLT republish rate | Dấu hiệu handler lỗi và phát lại trong DLT |
| Recovery case backlog | Số case chưa điều tra hoặc chưa replay |
| Oldest unresolved case age | Thời gian case chưa được giải quyết |
| DLT publish failure count | Lỗi chuyển record từ retry sang DLT |
| Replay success/failure | Kết quả quy trình replay |

### 18.1. Alert gợi ý

- Có record mới vào DLT của luồng nghiệp vụ quan trọng.
- DLT incoming rate tăng bất thường so với baseline.
- DltHandler failure rate tăng sau deploy.
- DLT republish liên tục cùng một event id.
- Recovery case chưa xử lý vượt SLA.
- DLT retention còn lại ngắn hơn thời gian cần cho việc điều tra.
- Replay thất bại hoặc tạo thêm DLT liên tục.

Không phải mọi record DLT đều cần page ngay. Có thể định nghĩa mức độ nghiêm trọng theo topic, nhóm exception, tuổi record và tác động nghiệp vụ. Một validation error lẻ có thể là ticket; lỗi gửi DLT hàng loạt hoặc mất khả năng lưu record có thể là sự cố nghiêm trọng.

### 18.2. Cardinality

Metrics tag phù hợp thường gồm service, topic thuộc tập hữu hạn, exception class đã nhóm và trạng thái recovery. Không đưa offset, event id, customer id, order id hoặc nguyên exception message vào tag.

Dùng structured logging và trace để tìm record cụ thể; dùng metrics để quan sát xu hướng.

## 19. Runbook: DLT có dữ liệu nhưng DltHandler không chạy

1. Xác nhận record thực sự đã được publish vào đúng DLT.
2. Kiểm tra DLT endpoint có được tạo bởi retry-topic infrastructure không.
3. Kiểm tra `autoStartDltHandler` hoặc cấu hình lifecycle có chủ động tắt DLT listener không.
4. Xác nhận đúng class và method có `@DltHandler`.
5. Kiểm tra consumer group, subscription và partition assignment.
6. Kiểm tra serializer/deserializer hoặc message converter có lỗi trước khi method chạy không.
7. Kiểm tra consumer lag và logger của DLT container.
8. Nếu DLT consumer được tắt theo quy trình, xác nhận có owner và lịch xử lý khác.

Không tự khởi động lại hàng loạt DLT listener trong production khi chưa xác định nó có được tắt có chủ đích hay không.

## 20. Runbook: DltHandler xử lý lặp cùng một record

1. Kiểm tra log theo event id và source identity.
2. Xác định có cùng một offset DLT được giao lại hay có nhiều record DLT với offset khác nhau.
3. Nếu cùng offset, kiểm tra committed offset, restart và error handling.
4. Nếu nhiều offset, kiểm tra DLT republish strategy và DltHandler exception.
5. Kiểm tra database audit có unique constraint và idempotency không.
6. Kiểm tra downstream timeout, vì thao tác có thể đã thành công trước khi handler báo lỗi.
7. Điều chỉnh chiến lược DLT và timeout có kiểm soát.
8. Đối soát số case thực sự với số record DLT, không coi chúng luôn bằng nhau.

Nếu lỗi DltHandler gây publish lại về DLT liên tục, cần xử lý nguyên nhân và giới hạn vòng lặp. Việc tăng retention đơn thuần không chữa được vấn đề.

## 21. Runbook: Record sai schema gây lỗi cả DLT

1. Xác định exception đầu tiên là deserialize, conversion hay validation.
2. Kiểm tra bytes/headers đã được publish tới DLT hay chưa.
3. Kiểm tra serializer của producer DLT có chấp nhận payload lỗi không.
4. Kiểm tra DLT consumer đang dùng deserializer kiểu domain object hay raw bytes.
5. Chọn cách đọc phù hợp để giữ lại dữ liệu mà không phải convert thất bại lần nữa.
6. Kiểm tra quyền truy cập, retention và masking của raw payload.
7. Sửa schema/consumer, kiểm thử record đại diện rồi replay có kiểm soát.

Một DLT chứa record không deserialize được mà consumer chỉ có phương thức nhận `OrderEvent` sẽ không tự nhiên hoạt động. Thiết kế recovery phải xử lý cả trường hợp dữ liệu hỏng.

## 22. Runbook: DLT publish thất bại

Trường hợp này xảy ra **trước** khi DltHandler nhận record.

1. Kiểm tra lỗi producer khi publish vào DLT.
2. Xác nhận DLT topic tồn tại, leader/ISR đủ khỏe và partition routing hợp lệ.
3. Kiểm tra ACL, bootstrap servers, serializer và message size.
4. Kiểm tra producer timeout, retries và cấu hình acks.
5. Xác nhận recoverer/error handler không coi recovery thành công khi publish thất bại.
6. Xác định offset topic nguồn đã được commit hay chưa.
7. Sau khi sửa nguyên nhân, xác nhận record được xử lý lại hoặc xuất hiện trên DLT.

Không tăng concurrency của DltHandler để chữa lỗi publish vào DLT; handler chưa nhận được record. Cần kiểm tra phía producer/recoverer.

## 23. Kiểm thử tích hợp DltHandler

Một bộ kiểm thử tốt phải xác nhận cả đường thành công lẫn đường lỗi ở từng giai đoạn. Có thể dùng Kafka test broker hoặc Testcontainers theo công cụ của dự án.

### 23.1. Retryable exception đến DLT sau khi hết lượt

1. Cấu hình `@RetryableTopic(attempts = "3")` với backoff ngắn.
2. Gửi một record có event id ổn định.
3. Cho listener ném exception retryable ở mọi lần.
4. Xác nhận số lần xử lý phù hợp với policy.
5. Xác nhận record vào DLT.
6. Xác nhận DltHandler được gọi.
7. Xác nhận audit record lưu event id, metadata nguồn và exception.

### 23.2. Non-retryable exception

1. Gửi record có payload nghiệp vụ không hợp lệ.
2. Cho listener ném exception đã được phân loại non-retryable.
3. Xác nhận record được recovery theo chính sách mà không bị retry vô ích.
4. Xác nhận DltHandler ghi nhận nguyên nhân chính xác.

### 23.3. DltHandler lỗi rồi chạy lại

1. Làm database audit trả về lỗi tạm thời.
2. Xác nhận DltHandler ném exception.
3. Quan sát `DltStrategy` đang áp dụng.
4. Xác nhận behavior publish lại DLT hoặc error handling phù hợp cấu hình.
5. Khôi phục database.
6. Xác nhận audit chỉ tạo một case cho cùng event id, dù nhận nhiều lần.

### 23.4. Deserialize lỗi

1. Gửi record không phù hợp serializer/schema.
2. Kiểm tra error handling ở tầng deserialize.
3. Xác nhận recoverer gửi payload theo format DLT có thể lưu.
4. Xác nhận handler hoặc consumer DLT có thể nhận/ghi nhận raw record.

### 23.5. Replay có idempotency

1. Xử lý một event thành công ở database nhưng mô phỏng crash trước khi offset commit.
2. Đưa event vào luồng recovery/replay theo kịch bản test.
3. Xác nhận event id được giữ nguyên.
4. Xác nhận side effect nghiệp vụ không bị thực hiện hai lần.
5. Xác nhận case DLT chuyển trạng thái đúng.

Kiểm thử nên đo **offset committed thực tế, topic nhận record, số lần handler được gọi và trạng thái database**. Chỉ kiểm tra một dòng log “DLT received” là chưa đủ để bảo đảm recovery đáng tin cậy.

## 24. Những lỗi triển khai thường gặp

**Nhầm @DltHandler với recoverer.** Handler không chịu trách nhiệm publish record đầu tiên vào DLT; recoverer hoặc retry-topic infrastructure thực hiện bước đó.

**Cho rằng record vào DLT đã được xử lý nghiệp vụ.** Record mới chỉ được lưu hoặc định tuyến tới nơi điều tra; side effect chưa chắc hoàn tất.

**DltHandler chỉ log rồi tự coi recovery hoàn tất.** Với quy trình cần audit/ticket, phải lưu trạng thái bền vững trước khi trả thành công.

**Tự replay ngay trong DltHandler.** Có thể tạo vòng lặp vô hạn và phá thứ tự nghiệp vụ. Nên tách quy trình replay.

**Không xử lý DltHandler exception.** Một lỗi audit có thể làm DLT republish liên tục hoặc kẹt tùy strategy.

**Không phân biệt offset DLT với offset nguồn.** Đối soát và replay dễ nhắm sai record.

**Giả định mọi DLT value là domain object.** Deserialization error có thể khiến record chỉ ở dạng raw bytes.

**Không có idempotency.** Record DLT bị giao lại có thể tạo nhiều ticket hoặc side effect.

**Thiếu owner và retention policy.** Record DLT có thể bị xóa trước khi được điều tra.

**Dùng exception message làm metric tag.** Cardinality cao và có nguy cơ rò rỉ dữ liệu.

## 25. Checklist trước khi đưa DltHandler vào production

### Retry topology

- [ ] `@RetryableTopic` hoặc retry-topic configuration đã được khai báo đúng.
- [ ] Số attempt, backoff và exception classification phù hợp SLA.
- [ ] DLT topic, partition, replication, retention và ACL được provisioning đúng.
- [ ] DLT publish failure được phát hiện và không gây xác nhận nguồn sai.
- [ ] `DltStrategy` được chọn có chủ đích và đã được kiểm thử.

### DltHandler

- [ ] Method `@DltHandler` nằm trong đúng bean/topology.
- [ ] Biết DLT endpoint được auto-start hay chủ động dừng.
- [ ] Handler nhận được payload hoặc raw bytes đúng cách.
- [ ] Header nguồn/exception được đọc an toàn khi vắng mặt.
- [ ] Audit được lưu bền vững trước khi handler trả thành công.
- [ ] Handler idempotent khi record DLT được giao lại.
- [ ] Dependency của handler có timeout và failure policy rõ ràng.

### Vận hành và replay

- [ ] Có dashboard cho DLT rate, lag, handler failure và recovery backlog.
- [ ] Có cảnh báo theo mức độ quan trọng nghiệp vụ.
- [ ] Có owner xử lý case DLT và SLA điều tra.
- [ ] Không replay vô hạn; có cơ chế phê duyệt và giới hạn tốc độ.
- [ ] Replay giữ event id và hỗ trợ đối soát kết quả.
- [ ] Log/headers/payload được bảo vệ theo chính sách dữ liệu.

### Kiểm thử

- [ ] Đã thử hết retry -> DLT -> DltHandler.
- [ ] Đã thử exception non-retryable.
- [ ] Đã thử handler lỗi và DLT republish strategy.
- [ ] Đã thử lỗi deserialize/conversion.
- [ ] Đã thử crash, redelivery, duplicate và idempotency.
- [ ] Đã thử replay sau khi sửa nguyên nhân.

## Kết luận

`@DltHandler` là điểm xử lý record từ dead-letter topic trong cơ chế non-blocking retry của Spring Kafka. Nó hoạt động **sau** bước publish vào DLT, thường để ghi nhận lỗi, lưu audit và hỗ trợ quy trình điều tra hoặc replay. Một thiết kế tin cậy cần phân biệt recoverer với DltHandler, đọc đúng metadata nguồn và exception, xác định DLT strategy khi handler thất bại, đồng thời bảo đảm idempotency và lưu trạng thái bền vững. Không nên coi việc DltHandler đã chạy là bằng chứng nghiệp vụ hoàn tất. Khi kết hợp DLT lifecycle, monitoring, retention, bảo mật và replay có kiểm soát, hệ thống có thể giữ lại record lỗi và phục hồi mà không tạo vòng lặp retry vô hạn hoặc làm mất khả năng đối soát.
