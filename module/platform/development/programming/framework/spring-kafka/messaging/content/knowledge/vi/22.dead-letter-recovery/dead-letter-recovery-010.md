# Tránh vòng lặp dead letter

Dead Letter Topic (DLT) là nơi lưu những record đã hết lượt retry hoặc không thể xử lý theo chính sách hiện tại. DLT thường là điểm kết thúc của luồng xử lý tự động để đội vận hành kiểm tra, sửa dữ liệu hoặc quyết định redrive. Nếu consumer của DLT tiếp tục áp dụng cùng chính sách lỗi và gửi record trở lại chính DLT, hoặc một listener vô tình đọc cả topic DLT, record có thể quay vòng liên tục.

Một vòng lặp dead letter không chỉ làm tăng chi phí broker. Nó còn khiến DLT tăng nhanh, tạo log và alert liên tục, làm record lỗi khó được phân biệt với record mới, đồng thời có thể làm phình header đến mức producer không thể gửi record nữa.

Nguyên tắc thiết kế là xác định rõ điểm kết thúc của từng luồng. Retry topic dành cho lần thử tự động có giới hạn; DLT dành cho record cần cách ly; quarantine là nơi cuối cùng nếu việc xử lý DLT cũng thất bại; redrive là thao tác có kiểm soát sau khi nguyên nhân đã được khắc phục.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện các kiểu vòng lặp phát sinh từ source topic, retry topic và DLT.
- Phân biệt retry tự động, dead-letter recovery và redrive thủ công.
- Cấu hình listener chỉ nhận đúng topic nghiệp vụ.
- Thiết kế destination resolver có allowlist và chặn route không hợp lệ.
- Chọn chính sách xử lý khi DLT handler thất bại.
- Dùng DltStrategy.FAIL_ON_ERROR với non-blocking retry khi cần ngăn forward trở lại DLT.
- Phân tách error handler của source listener, DLT listener và quarantine listener.
- Kiểm soát số lần redrive và giữ idempotency theo eventId.
- Quản lý DLT headers để tránh tăng kích thước record qua nhiều lần chuyển tiếp.
- Kiểm thử để chứng minh record không đi qua một chu trình vô hạn.

## 1. Vòng lặp dead letter hình thành như thế nào?

Một luồng cơ bản thường có source topic, một hoặc nhiều retry topic và DLT:

~~~text
orders
  |
  | xử lý lỗi
  v
orders-retry-1000
  |
  | vẫn lỗi
  v
orders-retry-5000
  |
  | hết attempts
  v
orders-dlt
~~~

Luồng này kết thúc khi record đến orders-dlt. Vòng lặp xuất hiện khi record ở DLT lại bị đưa vào một chính sách tự động không có điểm dừng rõ ràng.

Có bốn tình huống thường gặp.

### DLT listener lỗi rồi gửi record lại DLT

~~~text
orders-dlt
    |
    v
DLT listener
    |
    | xử lý DLT thất bại
    v
Error handler
    |
    | publish lại orders-dlt
    +----------------------> orders-dlt
~~~

Với Spring Kafka non-blocking retry, DLT failure strategy mặc định là ALWAYS_RETRY_ON_ERROR. Khi DLT handler thất bại, record được forward trở lại DLT để không chặn các record DLT khác. Nếu lỗi của handler là lỗi cố định, record có thể quay lại DLT nhiều lần.

### Listener nghiệp vụ vô tình subscribe cả DLT

~~~text
@KafkaListener(topicPattern = "orders.*")
        |
        +--> orders
        +--> orders-retry-1000
        +--> orders-dlt
        +--> orders-dlt-dlt
~~~

Pattern rộng có thể khớp cả topic retry và DLT. Record lỗi bị đọc lại như một event nghiệp vụ mới, rồi lại đi qua error handler.

### Destination resolver nối suffix theo topic hiện tại

Giả sử resolver luôn tạo đích bằng cách nối hậu tố -dlt:

~~~text
orders          -> orders-dlt
orders-dlt      -> orders-dlt-dlt
orders-dlt-dlt  -> orders-dlt-dlt-dlt
~~~

Nếu topic pattern tiếp tục nhận các topic mới được tạo, chuỗi này có thể phát triển không giới hạn. Nếu resolver luôn trả về cùng một topic DLT dựa trên metadata gốc, record có thể được gửi lại chính topic mà listener đang đọc.

### Redrive tự động không có giới hạn

Một DLT consumer đọc record, gửi lại source topic, rồi source listener thất bại và gửi record về DLT. Nếu DLT consumer tự động gửi lại source lần nữa, hai topic tạo thành một chu trình.

~~~text
orders -> orders-dlt -> orders -> orders-dlt -> ...
~~~

Redrive chỉ nên chạy sau khi nguyên nhân lỗi đã được xử lý và phải có giới hạn số lần, event identity và audit trail.

## 2. Phân biệt retry, DLT, quarantine và redrive

Các thành phần này có vai trò khác nhau. Nếu gộp tất cả vào một error handler, rất khó xác định record đã hết retry hay đang bị gửi vòng quanh.

| Thành phần | Mục đích | Có tự động thử lại? |
|---|---|---|
| Source topic | Luồng event chính | Listener xử lý lần đầu |
| Blocking retry | Thử lại tại consumer hiện tại | Có, theo BackOff |
| Retry topic | Thử lại sau một khoảng thời gian bằng consumer riêng | Có, theo attempts đã cấu hình |
| DLT | Cách ly record đã hết retry hoặc không thể xử lý | Không nên tự redrive vô hạn |
| Quarantine | Giữ record khi cả DLT processing hoặc recovery cũng thất bại | Không; thường cần điều tra |
| Redrive | Đưa record đã được sửa hoặc phê duyệt trở lại luồng xử lý | Có thể, nhưng phải có giới hạn và audit |

Một thiết kế rõ ràng có thể dùng topology:

~~~text
orders
  |
  +--> orders-retry-1000
  |
  +--> orders-retry-5000
  |
  +--> orders-dlt
           |
           +--> xử lý DLT thành công -> incident store / archive
           |
           +--> DLT handler lỗi -> orders-quarantine
                                      |
                                      +--> điều tra thủ công
                                      |
                                      +--> redrive có kiểm soát
~~~

Quarantine là điểm dừng tự động. Không gắn cùng một recoverer gửi record quay lại quarantine cho consumer của chính quarantine.

## 3. Không để listener chính đọc topic retry và DLT

Cách đơn giản nhất để ngăn loop là giới hạn subscription của listener nghiệp vụ vào đúng topic cần xử lý.

Ví dụ nên dùng danh sách topic rõ ràng:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Listener chỉ nhận topic orders. Retry topic và DLT được quản lý bởi các endpoint riêng của Spring Kafka hoặc listener vận hành riêng.

Không nên dùng pattern rộng như:

~~~java
@KafkaListener(
    topicPattern = "orders.*",
    groupId = "orders-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Pattern này có thể khớp orders-dlt và các topic retry có prefix orders. Khi DLT record được deserialize thành cùng kiểu OrderEvent, listener có thể xử lý nó như một event mới rồi gửi lại DLT khi lỗi.

### Nếu bắt buộc dùng topicPattern

Hãy loại trừ suffix của retry và DLT theo quy ước đặt tên của hệ thống. Ví dụ pattern minh họa:

~~~java
@KafkaListener(
    topicPattern = "orders(?!-retry-.*|-dlt$|\\\\.DLT$).*",
    groupId = "orders-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Biểu thức này loại trừ các topic kết thúc theo các suffix minh họa -retry-..., -dlt và .DLT. Tên retry/DLT mặc định có thể khác theo phiên bản Spring Kafka và cấu hình. Hãy điều chỉnh regex theo tên topic thực tế và kiểm thử danh sách topic được match.

Ưu tiên khai báo topics tường minh nếu tập topic không cần khám phá động. Regex sai một ký tự có thể khiến listener nhận nhầm DLT hoặc bỏ sót topic nghiệp vụ.

## 4. Destination resolver phải có allowlist

DeadLetterPublishingRecoverer cho phép cung cấp destination resolver để chọn topic và partition đích. Không nên xây dựng route bằng cách nối suffix một cách vô điều kiện với record.topic(), vì record đầu vào của recoverer có thể đã đến từ DLT.

Hãy ánh xạ rõ source topic sang DLT tương ứng và DLT sang quarantine nếu muốn có một tầng cách ly cuối cùng.

Ví dụ:

~~~java
@Bean
public DeadLetterPublishingRecoverer ordersRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> {
                        if ("orders".equals(record.topic())) {
                            // Event lỗi từ source topic.
                            return new TopicPartition(
                                    "orders-dlt",
                                    record.partition()
                            );
                        }

                        if ("orders-dlt".equals(record.topic())) {
                            // DLT handler cũng lỗi: chuyển sang quarantine.
                            return new TopicPartition(
                                    "orders-quarantine",
                                    -1
                            );
                        }

                        // Topic không nằm trong bảng route thì fail closed.
                        throw new IllegalStateException(
                                "No DLT route configured for topic "
                                        + record.topic()
                        );
                    }
            );

    // Chờ kết quả gửi và ném exception nếu publish DLT thất bại.
    recoverer.setFailIfSendResultIsError(true);

    return recoverer;
}
~~~

Trong ví dụ:

- Record từ orders được gửi đến orders-dlt và giữ partition gốc.
- Record từ orders-dlt nếu tiếp tục lỗi được gửi đến orders-quarantine; partition âm nghĩa là không chỉ định partition để producer chọn.
- Record từ topic không được khai báo sẽ làm recovery thất bại thay vì tự tạo một chuỗi topic mới.
- Quarantine không có route tự động trong resolver này, nên cần một chính sách vận hành riêng.

Khi dùng default destination resolver, Spring Kafka hiện dùng topic có suffix -dlt và cùng partition với record gốc. Topic DLT vì vậy cần có ít nhất số partition bằng topic nguồn. Các phiên bản cũ có thể dùng suffix mặc định khác; hãy kiểm tra version đang chạy.

### Không dùng metadata gốc để route một cách thiếu kiểm soát

DLT record có header mô tả topic nguồn ban đầu. Header này hữu ích cho audit và phân tích, nhưng không có nghĩa mọi lần recover phải gửi lại topic ban đầu hoặc cùng DLT.

Nếu resolver dùng DLT_ORIGINAL_TOPIC để chọn đích, hãy kiểm tra cả topic hiện tại, loại lỗi và trạng thái redrive. Route phải là quyết định có chủ đích, không phải một phép nối chuỗi từ header.

## 5. Cấu hình error handler cho source và DLT

Với record listener dùng DefaultErrorHandler, có thể cấu hình số lần retry và recoverer. Ví dụ dưới đây có một lần xử lý ban đầu và hai lần retry, mỗi lần cách nhau một giây.

~~~java
@Bean
public DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer ordersRecoverer) {

    DefaultErrorHandler errorHandler =
            new DefaultErrorHandler(
                    ordersRecoverer,
                    new FixedBackOff(1000L, 2L)
            );

    errorHandler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedEventVersionException.class
    );

    return errorHandler;
}
~~~

Gắn error handler vào factory của source listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                DefaultErrorHandler ordersErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(ordersErrorHandler);

    return factory;
}
~~~

Nếu DLT listener cũng cần retry hữu hạn rồi chuyển record sang quarantine, nó có thể dùng cùng resolver và error handler đã định tuyến orders-dlt sang orders-quarantine. DLT listener phải có consumer group riêng để quản lý offset độc lập:

~~~java
@KafkaListener(
    id = "orders-dlt-listener",
    topics = "orders-dlt",
    groupId = "orders-dlt-operations",
    containerFactory = "ordersDltListenerFactory"
)
public void inspectDlt(ConsumerRecord<String, OrderEvent> record) {
    incidentStore.record(
            record.value(),
            record.headers(),
            record.topic(),
            record.partition(),
            record.offset()
    );
}
~~~

Nếu incidentStore ghi nhận thành công, listener trả về bình thường và container commit offset theo AckMode. Nếu ghi nhận thất bại, error handler có thể retry hữu hạn rồi gửi record đến orders-quarantine theo route đã cấu hình.

Quarantine không nên dùng lại cùng error handler để gửi record về chính nó. Có thể để topic này chỉ dành cho operator hoặc dùng một container riêng với CommonContainerStoppingErrorHandler để dừng khi xử lý lỗi, giữ record chưa được xác nhận cho đến khi có can thiệp.

Tách group ID giúp phân biệt tiến độ của DLT consumer với source consumer. Nó không tự ngăn vòng lặp; route và subscription vẫn phải được giới hạn.

## 6. Kiểm tra kết quả publish DLT

Một lỗi khác dễ bị hiểu nhầm là vòng lặp dead letter: recoverer gọi KafkaTemplate gửi DLT nhưng broker không nhận được record. Nếu ứng dụng coi recovery thành công dù publish thất bại, source offset có thể được xác nhận và record bị mất khỏi luồng xử lý.

DeadLetterPublishingRecoverer hỗ trợ:

- setFailIfSendResultIsError(true): chờ kết quả gửi và ném exception nếu publish thất bại.
- setWaitForSendResultTimeout(...): đặt thời gian chờ kết quả gửi.
- setThrowIfNoDestinationReturned(true): yêu cầu resolver phải trả về destination hợp lệ.

Ví dụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                destinationResolver
        );

recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(30));
recoverer.setThrowIfNoDestinationReturned(true);
~~~

Các API trên có từ những phiên bản Spring Kafka tương ứng, trong đó các thiết lập xác nhận publish được bổ sung từ 2.7. Kiểm tra Javadoc theo dependency của dự án.

Nếu publish DLT thất bại và recoverer ném exception, record gốc chưa được xem là recovered; error handler có thể redeliver và thử recovery lại. Đây là cơ chế bảo vệ để không commit offset khi DLT chưa được ghi thành công. Nó có thể lặp lại trong thời gian DLT broker hoặc serializer gặp sự cố, vì vậy cần backoff, alert và giám sát recovery failure.

Không tắt xác nhận publish chỉ để consumer tiếp tục chạy. Điều đó có thể biến lỗi DLT thành mất dữ liệu.

## 7. Dùng DltStrategy.FAIL_ON_ERROR với @RetryableTopic

Spring Kafka non-blocking retry có thể tạo retry topics và DLT cho listener có @RetryableTopic. DLT handler được khai báo bằng @DltHandler hoặc cấu hình qua RetryTopicConfigurationBuilder.

Điểm cần chú ý: DLT failure strategy mặc định là ALWAYS_RETRY_ON_ERROR. Nếu DLT handler ném exception, record được forward trở lại DLT để không chặn các record DLT khác. Với lỗi cố định, đây có thể là vòng lặp tự gửi về DLT.

Khi không muốn forward record lỗi trở lại DLT, cấu hình DltStrategy.FAIL_ON_ERROR:

~~~java
@Component
public class OrderRetryListener {

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1000,
                multiplier = 2.0
        ),
        dltTopicSuffix = "-dlt",
        retryTopicSuffix = "-retry",
        dltProcessingFailureStrategy = DltStrategy.FAIL_ON_ERROR
    )
    @KafkaListener(
        topics = "orders",
        groupId = "orders-service"
    )
    public void consume(OrderEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void processDlt(
            OrderEvent event,
            @Header(KafkaHeaders.DLT_ORIGINAL_TOPIC) String originalTopic,
            @Header(KafkaHeaders.DLT_ORIGINAL_PARTITION) Integer originalPartition,
            @Header(KafkaHeaders.DLT_ORIGINAL_OFFSET) Long originalOffset,
            @Header(KafkaHeaders.DLT_EXCEPTION_FQCN) String exceptionType) {

        incidentStore.record(
                event,
                originalTopic,
                originalPartition,
                originalOffset,
                exceptionType
        );
    }
}
~~~

Trong ví dụ, attempts = 4 gồm lần xử lý ban đầu và các lần thử tiếp theo theo cấu hình retry-topic. Khi hết attempts, record được chuyển đến DLT. Nếu DLT handler ghi incident thành công và trả về bình thường, record được xử lý theo cơ chế offset của DLT listener.

Nếu DLT handler ném exception, FAIL_ON_ERROR ngăn hành vi forward record trở lại DLT. Record lỗi không được xử lý thành công; cần theo dõi container và quyết định dừng, điều tra hoặc phục hồi theo chính sách vận hành.

Với ALWAYS_RETRY_ON_ERROR, hành vi mặc định là forward record về DLT khi DLT processing lỗi. Với NO_DLT, framework không cấu hình DLT sau khi retry hết; chỉ chọn khi hệ thống chấp nhận kết thúc luồng mà không lưu record trong DLT.

Nếu không khai báo @DltHandler, Spring Kafka dùng handler mặc định chỉ ghi log. Khi cần lưu incident, archive hoặc điều tra, hãy triển khai DLT handler có idempotency và giám sát kết quả ghi.

## 8. DLT handler phải là bước xử lý cuối, không phải source listener thứ hai

Một DLT handler tốt thường thực hiện một hoặc nhiều công việc:

- Ghi incident vào database hoặc hệ thống ticket.
- Lưu payload, eventId và metadata Kafka để điều tra.
- Gửi thông báo vận hành theo cơ chế có kiểm soát.
- Đánh dấu trạng thái record là cần sửa hoặc chờ phê duyệt.
- Kết thúc thành công sau khi đã lưu bền vững.

Không nên để DLT handler gọi trực tiếp lại cùng service xử lý source rồi ném exception nếu source xử lý thất bại. Cách đó dễ tạo chu trình source-DLT-source.

Ví dụ handler lưu incident theo eventId:

~~~java
@Service
public class DltIncidentService {

    private final IncidentRepository repository;

    public void record(
            OrderEvent event,
            String originalTopic,
            Integer originalPartition,
            Long originalOffset,
            String exceptionType) {

        Incident incident = new Incident(
                event.eventId(),
                originalTopic,
                originalPartition,
                originalOffset,
                exceptionType,
                "PENDING_REVIEW"
        );

        // eventId có unique constraint để DLT redelivery không tạo incident trùng.
        repository.saveIfAbsent(incident);
    }
}
~~~

Nếu DLT listener nhận lại cùng record do offset chưa commit hoặc consumer restart, unique eventId giúp tránh tạo nhiều incident giống nhau.

Nếu việc ghi incident vào database thất bại, không được giả vờ thành công và commit offset. Để container retry hoặc dừng theo chính sách đã cấu hình, sau đó phát alert để đội vận hành biết DLT consumer đang bị chặn.

## 9. Không gắn cùng retry policy lên quarantine

Quarantine là tầng cuối để lưu record cần can thiệp. Nếu quarantine consumer dùng cùng error handler với source và DLT, khi quarantine processing lỗi, resolver có thể route sang một topic khác hoặc quay lại quarantine.

Ví dụ topology không nên có:

~~~text
orders-quarantine
       |
       | lỗi
       v
orders-quarantine-dlt
       |
       | listener pattern vẫn match
       v
orders-quarantine-dlt-dlt
       |
       v
       ...
~~~

Các lựa chọn an toàn:

1. Không tạo consumer tự động cho quarantine; dùng công cụ vận hành đọc và xuất record.
2. Nếu có consumer quarantine, dùng factory riêng với CommonContainerStoppingErrorHandler.
3. Ghi lỗi xử lý quarantine vào hệ thống ngoài Kafka và dừng container khi không thể xử lý.
4. Chỉ redrive sau khi có thao tác phê duyệt và giới hạn attempts.

Ví dụ factory dừng container khi quarantine handler lỗi:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        quarantineListenerFactory(
                ConsumerFactory<String, OrderEvent> quarantineConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(quarantineConsumerFactory);
    factory.setCommonErrorHandler(
            new CommonContainerStoppingErrorHandler()
    );

    return factory;
}
~~~

Error handler này không tự publish record sang một DLT khác. Khi listener thất bại, container dừng theo cơ chế của handler; record chưa được xác nhận có thể được đọc lại khi container khởi động. Hệ thống cần alert và quy trình can thiệp trước khi restart.

## 10. Redrive phải có giới hạn và audit

Redrive là đưa một record từ DLT trở lại source topic sau khi đã sửa nguyên nhân lỗi. Đây là thao tác có chủ đích, không phải một phần của retry tự động.

Một quy trình redrive nên:

1. Xác định eventId và vị trí record gốc.
2. Đọc exception metadata và nguyên nhân lỗi.
3. Sửa dữ liệu hoặc triển khai bản sửa tương thích.
4. Phê duyệt record đủ điều kiện redrive.
5. Tăng redriveCount và tạo redriveId mới.
6. Gửi lại record vào source hoặc một topic redrive riêng.
7. Ghi audit gồm người thực hiện, thời gian, lý do và kết quả.
8. Dừng nếu vượt giới hạn redrive.

Ví dụ luồng có giới hạn:

~~~text
orders-dlt
    |
    v
Operator kiểm tra incident
    |
    +--> chưa sửa nguyên nhân -> giữ trong DLT
    |
    +--> đã sửa, đủ điều kiện
              |
              v
       redriveCount < 3 ?
          /          \
        Có            Không
        |               |
        v               v
   orders-redrive   orders-quarantine
        |
        v
   xử lý có kiểm soát
~~~

Có thể gửi record vào topic redrive riêng để phân biệt luồng replay với event mới. Consumer redrive có thể dùng cùng nghiệp vụ nhưng phải kiểm tra redriveId, eventId và số lần replay.

### Header redrive không thay thế audit bền vững

Có thể gắn các header như:

| Header | Mục đích |
|---|---|
| x-redrive-id | Định danh một lần redrive |
| x-redrive-count | Số lần record đã được redrive |
| x-redrive-by | Người hoặc service yêu cầu redrive |
| x-redrive-reason | Lý do redrive |
| x-original-event-id | Định danh event nghiệp vụ ban đầu |

Kafka header có thể bị mất hoặc bị thay đổi bởi producer, converter hay quy trình export/import. Với quy trình vận hành quan trọng, hãy lưu lịch sử redrive trong database hoặc hệ thống audit. Dùng eventId làm khóa idempotency để ngăn side effect bị nhân đôi.

### Ví dụ kiểm tra số lần redrive

~~~java
public void redrive(
        ConsumerRecord<String, OrderEvent> failedRecord,
        int currentRedriveCount) {

    if (currentRedriveCount >= 3) {
        throw new IllegalStateException(
                "Redrive limit reached for event "
                        + failedRecord.value().eventId()
        );
    }

    int nextCount = currentRedriveCount + 1;

    ProducerRecord<String, OrderEvent> replay =
            new ProducerRecord<>(
                    "orders-redrive",
                    failedRecord.key(),
                    failedRecord.value()
            );

    replay.headers().add(
            new RecordHeader(
                    "x-redrive-count",
                    ByteBuffer.allocate(Integer.BYTES)
                            .putInt(nextCount)
                            .array()
            )
    );

    replay.headers().add(
            new RecordHeader(
                    "x-redrive-id",
                    UUID.randomUUID().toString()
                            .getBytes(StandardCharsets.UTF_8)
            )
    );

    kafkaTemplate.send(replay);
}
~~~

Đoạn code minh họa cách gửi sang topic redrive riêng. Trong production, cần đọc redriveCount từ header hoặc incident store, kiểm tra quyền phê duyệt, ghi audit trước/sau khi gửi và xác nhận kết quả publish. Không dùng một giá trị đếm mặc định luôn bằng 0 cho mọi lần redrive.

## 11. Giữ idempotency khi record quay lại source

Một record được gửi lại source có thể được consumer xử lý lần nữa dù lần xử lý trước đã tạo side effect một phần. Điều này xảy ra khi listener ghi database xong nhưng commit offset thất bại, hoặc redrive gửi lại event đã từng được xử lý.

Hãy dùng eventId ổn định và inbox/idempotency store:

~~~java
@Transactional
public void process(OrderEvent event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderService.apply(event);

    inboxRepository.save(
            new InboxEntry(event.eventId(), Instant.now())
    );
}
~~~

Trong ví dụ, cập nhật nghiệp vụ và ghi inbox phải nằm trong cùng database transaction. Unique constraint trên eventId bảo vệ thêm trước hai lần xử lý đồng thời.

Nếu event đã được xử lý thành công, redrive không được tạo lại thanh toán, gửi email hoặc trừ tồn kho lần thứ hai. Redrive phải giữ eventId gốc; chỉ redriveId là định danh cho lần phát lại.

## 12. Quản lý DLT headers để không làm record phình ra

DeadLetterPublishingRecoverer giữ các header gốc và thêm metadata như:

- DLT_EXCEPTION_FQCN: loại exception.
- DLT_EXCEPTION_MESSAGE: thông báo lỗi.
- DLT_EXCEPTION_STACKTRACE: stack trace.
- DLT_ORIGINAL_TOPIC: topic nguồn.
- DLT_ORIGINAL_PARTITION: partition nguồn.
- DLT_ORIGINAL_OFFSET: offset nguồn.
- DLT_ORIGINAL_TIMESTAMP: timestamp nguồn.
- DLT_ORIGINAL_CONSUMER_GROUP: consumer group đã gặp lỗi.

Khi một record được publish nhiều lần qua retry hoặc DLT, Kafka có thể giữ nhiều header cùng tên. Stack trace và metadata lỗi có thể làm record lớn dần.

Spring Kafka cung cấp các tùy chọn:

- appendOriginalHeaders: quyết định có thêm original headers khi header đó đã tồn tại hay không; mặc định true.
- stripPreviousExceptionHeaders: loại các exception headers cũ trước khi thêm thông tin lỗi mới; mặc định true từ Spring Kafka 2.8.
- excludeHeader(...): loại một số header chuẩn, ví dụ stack trace nếu không cần truyền qua nhiều tầng.

Ví dụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltKafkaTemplate);

recoverer.setAppendOriginalHeaders(false);
recoverer.setStripPreviousExceptionHeaders(true);

// Nếu không cần stack trace trong DLT:
recoverer.excludeHeader(
        DeadLetterPublishingRecoverer.HeaderNames.HeadersToAdd.EX_STACKTRACE
);
~~~

Tên API và enum cần đối chiếu version Spring Kafka đang dùng. Khi appendOriginalHeaders=false, chỉ giữ original header đầu tiên thay vì thêm một giá trị mới cho mỗi lần chuyển tiếp. Nếu cần lịch sử đầy đủ, hãy lưu lịch sử trong incident store thay vì dựa vào một chuỗi header tăng mãi.

Kafka hỗ trợ nhiều header trùng tên. Khi đọc metadata, dùng lastHeader() nếu cần giá trị mới nhất hoặc duyệt toàn bộ headers nếu cần lịch sử. Không giả định headers().lastHeader() luôn là thông tin đầu tiên của event.

## 13. Không nhầm retry topic với DLT

Non-blocking retry chuyển record qua các retry topic theo backoff timestamp. Khi hết attempts, record được gửi đến DLT nếu DLT đã được cấu hình.

Ví dụ:

~~~text
orders
  |
  +--> orders-retry-1000
  |
  +--> orders-retry-2000
  |
  +--> orders-retry-4000
  |
  +--> orders-dlt
~~~

Đây là một chuỗi tiến về phía trước. Nó không phải vòng lặp nếu:

- attempts hữu hạn.
- mỗi retry topic có một bước tiếp theo xác định.
- DLT không được đưa vào danh sách source topic.
- DLT handler không forward record về DLT vô hạn.
- không có listener pattern nào vô tình đọc lại retry topic cũ.

Spring Kafka có thể tự tạo retry topic và consumer tương ứng khi dùng @RetryableTopic. Consumer group của retry topic/DLT được tạo theo group ID và suffix của topic để tách tiến độ khỏi source group. Với cấu hình tùy chỉnh, cần xác nhận group ID và topic routing thực tế.

Non-blocking retry có thể làm mất ordering giữa các record trong topic vì record lỗi được chuyển sang retry topic và record sau vẫn có thể tiếp tục. Nếu thứ tự nghiệp vụ quan trọng, cần cân nhắc blocking retry hoặc thiết kế version guard.

## 14. Chọn lỗi nào retry, lỗi nào đưa DLT ngay

Không phải lỗi nào cũng cần retry nhiều lần. Lỗi tạm thời có thể hồi phục; lỗi dữ liệu hoặc schema thường không tự hết khi thử lại.

Ví dụ:

| Lỗi | Chiến lược thường phù hợp |
|---|---|
| Database timeout ngắn | Retry có backoff |
| HTTP 503 từ dependency | Retry hữu hạn, có backoff |
| ValidationException | Không retry; đưa DLT |
| Event version không hỗ trợ | Không retry; DLT để xử lý tương thích |
| JSON không parse được | Không retry vô ích; DLT hoặc quarantine |
| Broker DLT tạm thời unavailable | Giữ source record chưa recovered và retry publish DLT |
| DLT incident store tạm thời lỗi | Retry DLT processing hoặc dừng container theo chính sách |

Có thể thêm exception vào nhóm không retry của DefaultErrorHandler:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1000L, 2L)
        );

errorHandler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
);
~~~

Khi lỗi không thể giải quyết bằng việc thử lại cùng payload, retry liên tục chỉ kéo dài thời gian trước khi record đến DLT. Phân loại exception đúng giúp record đến điểm cách ly nhanh và giảm áp lực lên consumer.

## 15. Kiểm tra DLT topic và partition

Với default DeadLetterPublishingRecoverer resolver, record thường được gửi đến topic DLT có cùng partition number với record gốc. Nếu source có 12 partition, DLT cần ít nhất 12 partition để giữ mapping này.

Khi dùng custom resolver:

- Nếu muốn giữ partition, bảo đảm DLT có partition tương ứng.
- Nếu destination partition âm, producer tự chọn partition.
- Nếu route sang quarantine, có thể chọn partition tự động hoặc một partition theo quy tắc riêng.
- Nếu topic đích không tồn tại, kiểm tra chính sách auto-create và quyền ACL.
- Nếu DLT producer không có quyền ghi, recoverer phải báo lỗi để source record chưa bị xem là recovered.

Không tạo DLT topic ít partition hơn source rồi giả định Kafka sẽ tự chuyển đúng partition. Kiểm tra topic metadata và quyền ghi trong integration test.

## 16. Kiểm thử không có vòng lặp

Kiểm thử cần theo dõi đường đi của một event qua nhiều topic, không chỉ kiểm tra listener đã ném exception.

Nên tạo event có eventId duy nhất, gửi vào source topic và ghi lại topic, partition, offset, retry count, DLT headers ở mỗi bước.

Các kịch bản quan trọng:

1. Source event xử lý thành công: không có record trong retry hoặc DLT.
2. Source event lỗi tạm thời rồi thành công: chỉ đi qua số retry cần thiết, không vào DLT.
3. Source event hết attempts: xuất hiện đúng một record trong DLT.
4. DLT handler thành công: record được lưu incident và không publish lại DLT.
5. DLT handler thất bại với DltStrategy.FAIL_ON_ERROR: record không được forward trở lại DLT.
6. DLT handler thất bại với ALWAYS_RETRY_ON_ERROR: xác nhận hành vi forward về DLT và chứng minh vì sao không phù hợp với lỗi cố định.
7. Listener chính dùng topicPattern: xác nhận pattern không match retry, DLT và quarantine.
8. Destination resolver nhận record từ DLT: route sang quarantine, không tạo orders-dlt-dlt ngoài thiết kế.
9. Destination resolver nhận topic không nằm trong allowlist: recovery fail closed.
10. DLT publish thất bại: source record chưa được commit như một record đã recover.
11. Redrive count đạt giới hạn: không gửi thêm record về source.
12. Redrive cùng eventId nhiều lần: side effect chỉ được áp dụng một lần nhờ idempotency.
13. Record đi qua nhiều DLT/retry: header không tăng vô hạn và vẫn giữ được original metadata.
14. Restart DLT consumer khi incident store unavailable: record chưa được xác nhận và có thể phục hồi.
15. Quarantine listener lỗi: container dừng hoặc record được giữ theo chính sách cuối cùng, không phát sinh topic mới liên tục.

Không chỉ dùng sleep để chờ kết quả. Hãy dùng Kafka test utilities, Awaitility hoặc latch có timeout, rồi truy vấn record theo eventId trên từng topic.

## 17. Theo dõi và cảnh báo vòng lặp

Một DLT có thể tăng nhanh do một lỗi schema hoặc do loop. Cần đo đủ để phân biệt hai trường hợp.

Các chỉ số nên theo dõi:

| Chỉ số | Điều cần phát hiện |
|---|---|
| DLT publish rate | Số record mới bị chuyển sang DLT |
| DLT consumer lag | DLT handler đang xử lý chậm hoặc bị dừng |
| DLT failure count | DLT handler liên tục thất bại |
| Recovery failure count | Không thể publish record đến DLT |
| Retry topic lag | Record bị giữ ở retry topic quá lâu |
| Quarantine count | Record đã vượt khỏi quy trình tự động |
| Redrive count | Một event bị phát lại nhiều lần |
| Repeated eventId | Cùng một event xuất hiện qua nhiều vòng xử lý |
| DLT header size | Metadata tăng bất thường qua nhiều lần chuyển tiếp |

Một số cảnh báo có thể đặt:

- Một eventId xuất hiện nhiều lần trong cùng DLT trong khoảng thời gian ngắn.
- DLT publish rate tăng đột biến so với traffic source.
- DLT consumer lag tăng liên tục.
- Quarantine có record mới.
- Một DLT handler thất bại liên tiếp.
- Một event vượt giới hạn redrive.

Log nên chứa eventId, source topic, partition, offset, DLT destination, exception type và redriveId. Không log toàn bộ payload nhạy cảm hoặc stack trace quá lớn ở mọi lần retry.

## 18. Quy trình vận hành khi phát hiện DLT loop

Khi phát hiện record đang quay vòng, cần dừng nguồn tạo thêm record trước khi điều tra sâu.

Quy trình tham khảo:

1. Xác định eventId và topic hiện tại của record.
2. Kiểm tra DLT headers để tìm source topic, partition, offset và consumer group gốc.
3. Kiểm tra topic pattern của listener đang đọc DLT.
4. Kiểm tra destination resolver có route DLT về chính nó hoặc tạo suffix vô hạn không.
5. Kiểm tra DltStrategy nếu đang dùng @RetryableTopic.
6. Tạm dừng DLT handler hoặc listener pattern gây loop nếu cần.
7. Lưu incident và payload vào nơi có thể truy xuất.
8. Sửa route, subscription hoặc DLT failure policy.
9. Kiểm thử bằng eventId mới trong môi trường test.
10. Chỉ redrive record cũ sau khi đã có giới hạn attempts và idempotency.

Không xóa DLT topic để làm mất dấu loop. Record trong DLT là dữ liệu phục vụ điều tra; hãy giữ nguyên hoặc snapshot theo quy trình lưu trữ của hệ thống trước khi dọn dẹp.

## 19. Những lỗi thiết kế thường gặp

**Listener chính subscribe pattern quá rộng.** Listener đọc cả retry và DLT như event mới. Dùng topic list tường minh hoặc regex loại trừ các suffix nội bộ.

**Destination resolver nối -dlt vào topic hiện tại.** DLT record tiếp tục tạo topic DLT mới. Dùng allowlist source-to-DLT và route DLT failure sang quarantine.

**DltStrategy mặc định không được xem xét.** DLT handler lỗi có thể forward record trở lại DLT với ALWAYS_RETRY_ON_ERROR. Chọn FAIL_ON_ERROR khi cần dừng forward và thiết kế cách xử lý lỗi DLT.

**DLT handler gửi lại source ngay khi gặp lỗi.** Source và DLT tạo chu trình tự động. Chỉ redrive sau khi sửa nguyên nhân, có phê duyệt và giới hạn.

**Dùng chung error handler cho quarantine.** Quarantine lỗi lại được gửi sang topic khác hoặc quay về quarantine. Dùng handler dừng container hoặc quy trình vận hành riêng.

**Không xác nhận kết quả publish DLT.** Source offset có thể được xác nhận dù record chưa vào DLT. Bật failIfSendResultIsError và kiểm tra timeout.

**Redrive không có giới hạn.** Một poison event có thể quay lại source nhiều lần. Dùng redriveCount, redriveId và audit store.

**Không có idempotency.** Event được phát lại gây side effect trùng. Dùng eventId ổn định và inbox/unique constraint.

**Giữ mọi exception header qua nhiều vòng.** Record có thể phình và lỗi RecordTooLargeException. Quản lý appendOriginalHeaders, stripPreviousExceptionHeaders và stack trace.

**Dùng DLT làm nơi retry không thời hạn.** DLT mất vai trò cách ly và vận hành không thể phân biệt record cần xử lý. Dùng retry topic cho retry tự động, DLT/quarantine cho điều tra.

## 20. Checklist tránh vòng lặp dead letter

- [ ] Source listener chỉ subscribe topic nghiệp vụ cần xử lý.
- [ ] Topic pattern không match retry, DLT và quarantine.
- [ ] Retry attempts là hữu hạn và backoff được cấu hình rõ.
- [ ] DLT là điểm kết thúc của retry tự động.
- [ ] DLT failure strategy được chọn có chủ đích.
- [ ] DLT handler không tự gửi lại source khi chưa có redrive approval.
- [ ] Destination resolver dùng allowlist và xử lý rõ topic không được hỗ trợ.
- [ ] Record từ DLT được route sang quarantine hoặc dừng theo chính sách riêng.
- [ ] Quarantine không dùng cùng recoverer để gửi về chính nó.
- [ ] DLT publish được xác nhận trước khi source record được xem là recovered.
- [ ] DLT topic có partition và ACL phù hợp.
- [ ] DLT headers được quản lý để không tăng vô hạn.
- [ ] Redrive có giới hạn, audit và eventId ổn định.
- [ ] Consumer idempotent để xử lý record được phát lại.
- [ ] Có integration test xác nhận không có chu trình source-retry-DLT.
- [ ] Có metrics và alert cho DLT failure, quarantine và repeated eventId.

## Kết luận

Tránh vòng lặp dead letter bằng cách coi DLT là điểm cách ly cuối của luồng tự động. Listener nghiệp vụ chỉ nên đọc topic nguồn; destination resolver cần allowlist rõ ràng; DLT handler phải có failure strategy riêng; quarantine không được tự gửi record quay lại chính nó. Với @RetryableTopic, hãy cân nhắc DltStrategy.FAIL_ON_ERROR khi DLT handler lỗi để ngăn forward trở lại DLT theo mặc định ALWAYS_RETRY_ON_ERROR. Redrive chỉ thực hiện sau khi sửa nguyên nhân, có giới hạn và audit. Kết hợp eventId, idempotency, xác nhận publish DLT và giám sát header/lag sẽ giúp luồng recovery có điểm kết thúc rõ ràng.

## Tài liệu tham khảo

- [Spring Kafka – Handling Exceptions and Publishing Dead-letter Records](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka – DLT Strategies](https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html)
- [Spring Kafka – How the Non-Blocking Retry Pattern Works](https://docs.spring.io/spring-kafka/reference/retrytopic/how-the-pattern-works.html)
- [Spring Kafka – Retry Topic Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html)

