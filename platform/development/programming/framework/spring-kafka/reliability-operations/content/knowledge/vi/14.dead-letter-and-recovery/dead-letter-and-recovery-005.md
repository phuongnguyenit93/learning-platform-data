# Giữ original topic và offset

Khi một record của Kafka thất bại sau các lần xử lý hoặc retry, ứng dụng Spring Kafka thường chuyển nó sang **dead-letter topic (DLT)** để có thể điều tra và xử lý lại sau này. Record trên DLT mang một offset mới trong một topic mới; nếu chỉ quan sát topic và offset hiện tại, người vận hành không còn biết record lỗi bắt nguồn từ đâu. Vì vậy, cần giữ **original topic**, **original partition** và **original offset** cùng thông tin liên quan dưới dạng metadata.

Trong Spring Kafka, **DeadLetterPublishingRecoverer** có thể thêm các header mô tả record nguồn và exception khi publish record sang DLT. Các header này giúp truy vết sự cố, định vị bản ghi gốc, phân biệt các chặng retry và hỗ trợ replay có kiểm soát. Tuy nhiên, metadata truy vết không tự tạo bảo đảm exactly-once và không thay thế event ID nghiệp vụ.

## 1. Vì sao không thể chỉ dùng topic và offset hiện tại?

Kafka phân chia dữ liệu thành các log độc lập theo topic và partition. Offset là vị trí trong log của **một partition cụ thể**, không phải số thứ tự toàn cluster. Khi record được gửi sang topic khác, broker cấp offset mới cho record ở topic đích.

Ví dụ:

~~~text
Topic orders
  partition 3, offset 1254
          |
          | listener thất bại
          v
Topic orders-retry-1000
  partition 3, offset 87
          |
          | retry vẫn thất bại
          v
Topic orders.DLT
  partition 3, offset 12
~~~

Ba offset 1254, 87 và 12 chỉ là ba vị trí thuộc ba log khác nhau. Không thể kết luận offset 12 trên orders.DLT tương đương offset 12 trên orders, hoặc lấy offset 87 của retry topic để seek trực tiếp trên topic gốc.

Một định danh vị trí Kafka cần đầy đủ ít nhất:

~~~text
(topic, partition, offset)

Ví dụ:
  (orders, 3, 1254)       -- vị trí record gốc
  (orders.DLT, 3, 12)     -- vị trí record trên DLT
~~~

Khi cần truy vết từ DLT về record gốc, ứng dụng phải giữ bộ ba nguồn và phân biệt nó với bộ ba của record DLT hiện tại.

## 2. Metadata gốc gồm những gì?

Với Spring Kafka DeadLetterPublishingRecoverer, các header thường được sử dụng để lưu thông tin nguồn bao gồm:

| Header Spring Kafka | Ý nghĩa | Dạng dữ liệu thường gặp |
|---|---|---|
| **KafkaHeaders.DLT_ORIGINAL_TOPIC** | Topic của record được ghi nhận là nguồn trong luồng recovery | Chuỗi UTF-8 |
| **KafkaHeaders.DLT_ORIGINAL_PARTITION** | Partition nguồn | Số nguyên 32-bit ở dạng bytes |
| **KafkaHeaders.DLT_ORIGINAL_OFFSET** | Offset nguồn | Số nguyên 64-bit ở dạng bytes |
| **KafkaHeaders.DLT_ORIGINAL_TIMESTAMP** | Timestamp của record nguồn | Số nguyên 64-bit ở dạng bytes |
| **KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE** | Kiểu timestamp nguồn như CREATE_TIME hoặc LOG_APPEND_TIME | Metadata biểu diễn dạng bytes |
| **KafkaHeaders.DLT_EXCEPTION_FQCN** | Tên class của exception được ghi nhận khi recovery | Chuỗi |
| **KafkaHeaders.DLT_EXCEPTION_MESSAGE** | Thông điệp exception khi được cung cấp | Chuỗi |
| **KafkaHeaders.DLT_EXCEPTION_STACKTRACE** | Stack trace phục vụ điều tra khi được bật/cung cấp | Chuỗi, có thể dài |

Tùy phiên bản Spring Kafka và cách tạo recoverer, còn có thể có header về consumer group, exception cause hoặc các metadata bổ sung. Không nên giả định mọi header kể trên luôn hiện diện, hay tên/hành vi của chúng giống nhau ở mọi version. Hãy dựa vào các constant và API của đúng Spring Kafka dependency đang sử dụng.

Đặc biệt:

- **Original topic** không phải tên DLT.
- **Original partition** không nhất thiết bằng partition của DLT nếu record được định tuyến lại.
- **Original offset** không phải consumer group committed offset.
- **Original timestamp** không phải thời điểm record được ghi vào DLT.
- **Exception metadata** giải thích một lần thất bại, không phải bằng chứng chắc chắn về trạng thái nghiệp vụ.

Metadata trên thường nằm ở **Kafka record headers**, tách khỏi key và value của record. Đây là lý do không nên ghi đè payload nghiệp vụ bằng một JSON lỗi tùy tiện nếu vẫn muốn giữ khả năng deserialize và replay record ban đầu.

## 3. Luồng giữ metadata khi chuyển sang DLT

Một quá trình xử lý lỗi thường gồm:

~~~text
Consumer group orders-service
         |
         v
poll orders/P3/1254
         |
         v
OrderListener.process(record)
         |
         +----- thành công ------> tiếp tục
         |
         v
Ném exception
         |
         v
DefaultErrorHandler + BackOff
         |
         +----- retry còn hiệu lực --> listener xử lý lại
         |
         v
Hết retry / lỗi non-retryable
         |
         v
DeadLetterPublishingRecoverer
         |
         +-- giữ key/value/header cần thiết
         +-- bổ sung original topic/partition/offset
         +-- bổ sung metadata về exception
         |
         v
Kafka producer publish orders.DLT
         |
         v
Broker cấp DLT offset mới
         |
         v
DLT consumer / hệ thống điều tra
~~~

Nếu record đi qua nhiều retry topic trước khi đến DLT, còn có các bước publish/consume trung gian. Mỗi bước là một record trên log riêng, và việc giữ metadata về record **đầu tiên** hay **chặng gần nhất** phải được xác định theo cách infrastructure và recoverer cấu hình headers.

Không nên tự suy luận rằng một header mang tên original luôn là vị trí đầu tiên của toàn bộ hành trình nếu record đã được chuyển qua nhiều topic, nhiều recoverer tùy biến hoặc đã được replay. Việc chọn header nào làm nguồn chuẩn cần được xác minh bằng cấu hình và dữ liệu thực tế của topology.

## 4. DefaultErrorHandler và DeadLetterPublishingRecoverer

Với listener container không sử dụng Kafka transaction, một cấu hình thường gặp là kết hợp **DefaultErrorHandler** với **DeadLetterPublishingRecoverer**.

~~~java
@Configuration
public class KafkaRecoveryConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, backOff);

        handler.addNotRetryableExceptions(
                InvalidOrderException.class);

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        return factory;
    }
}
~~~

Các kiểu OrderEvent và InvalidOrderException là ví dụ của ứng dụng. Trong môi trường thật, cần cấu hình đúng producer factory, key/value serializer, consumer deserializer, bảo mật và số partition. Đoạn mã minh họa Spring Kafka API; các import và cách wiring cụ thể phụ thuộc phiên bản thư viện.

Khi record không thể xử lý tiếp, DeadLetterPublishingRecoverer tạo record gửi sang DLT và bổ sung các header DLT theo chính sách mặc định hoặc cấu hình tùy biến. Nhờ đó, bản ghi đích có thể chứa đồng thời **vị trí hiện tại trên DLT** và **metadata vị trí nguồn**.

DefaultErrorHandler không tự chuyển mọi lỗi sang DLT ngay. Nó dựa vào classifier, BackOff và recoverer. Nếu lỗi được retry thành công, không cần record DLT. Nếu recoverer thất bại, việc ghi DLT có thể chưa thành công; đó là tình huống riêng phải có chính sách xử lý.

## 5. Cấu hình đích DLT và partition mapping

Một mặc định thường gặp của DeadLetterPublishingRecoverer là chuyển record từ topic **orders** sang **orders.DLT**, với partition đích bằng partition nguồn. Ví dụ orders/P3/1254 sẽ được gửi đến orders.DLT/P3.

Muốn mô tả định tuyến tường minh, có thể truyền destination resolver:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) ->
                        new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()));
~~~

Với cách này, topic DLT phải có đủ partition để chứa partition đích. Ví dụ nếu orders có sáu partition thì orders.DLT phải có ít nhất sáu partition để định tuyến đúng P0 đến P5.

Khi muốn để Kafka producer chọn partition đích theo partitioner thay vì giữ đúng chỉ số nguồn, có thể dùng destination resolver trả về một TopicPartition với partition âm theo ngữ nghĩa API recoverer mà phiên bản Spring Kafka hỗ trợ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) ->
                        new TopicPartition(
                                record.topic() + ".DLT", -1));
~~~

Khi không chỉ định partition cố định ở record được publish, Kafka producer chọn partition theo key và partitioner. Trong trường hợp này, **current DLT partition có thể khác original partition**. Header nguồn càng quan trọng để truy vết.

Không nên cấu hình DLT thiếu partition hoặc giả định việc thêm partition làm thay đổi cách hiểu của original offset. Original offset vẫn thuộc partition nguồn, không phải partition đích.

### Tạo DLT có kiểm soát

Ví dụ ứng dụng chủ động đăng ký topic:

~~~java
@Bean
NewTopic ordersDlt() {
    return TopicBuilder.name("orders.DLT")
            .partitions(6)
            .replicas(3)
            .build();
}
~~~

Số partition và replication factor ở đây chỉ minh họa. Cluster cần đủ broker để đáp ứng replication factor. Với production, nên thống nhất tên topic, retention, replication, min.insync.replicas, ACL và quota với quy trình vận hành Kafka.

## 6. Đọc original topic, partition và offset trong DLT consumer

Khi đọc record trên DLT, có thể dùng ConsumerRecord và KafkaHeaders để truy xuất metadata gốc. Ví dụ một handler dùng Spring Kafka:

~~~java
@DltHandler
public void handleDlt(ConsumerRecord<String, OrderEvent> record) {
    Headers headers = record.headers();

    String originalTopic = readUtf8Header(
            headers, KafkaHeaders.DLT_ORIGINAL_TOPIC);

    Integer originalPartition = readIntHeader(
            headers, KafkaHeaders.DLT_ORIGINAL_PARTITION);

    Long originalOffset = readLongHeader(
            headers, KafkaHeaders.DLT_ORIGINAL_OFFSET);

    log.error(
            "DLT record current={}/{}/{}, original={}/{}/{}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            originalTopic,
            originalPartition,
            originalOffset,
            record.key());

    failureAuditService.recordFailure(
            record.key(),
            originalTopic,
            originalPartition,
            originalOffset);
}
~~~

Trong đoạn ví dụ, **readUtf8Header**, **readIntHeader** và **readLongHeader** là helper của ứng dụng, không phải API có sẵn của Kafka. Có thể triển khai:

~~~java
private static String readUtf8Header(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(header.value(), StandardCharsets.UTF_8);
}

private static Integer readIntHeader(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null
            || header.value().length != Integer.BYTES) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getInt();
}

private static Long readLongHeader(
        Headers headers, String headerName) {
    Header header = headers.lastHeader(headerName);
    if (header == null || header.value() == null
            || header.value().length != Long.BYTES) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getLong();
}
~~~

Ví dụ dùng byte order mặc định của ByteBuffer và quy ước encode số nguyên của các header DLT phổ biến trong Spring Kafka. Không nên giải mã partition hoặc offset như chuỗi ASCII, vì chúng thường là số nguyên dạng bytes. Nếu ứng dụng sử dụng custom recoverer hoặc custom header encoding, cần giải mã theo chính quy ước đã sử dụng khi publish.

Khi dùng **@DltHandler**, method được cấu hình cùng topology @RetryableTopic, và record được giao từ DLT listener container. Nếu ứng dụng tạo consumer DLT độc lập bằng @KafkaListener, cách đọc headers trên ConsumerRecord vẫn tương tự.

Lưu ý thực tế: phương thức **lastHeader()** lấy giá trị cuối cùng nếu một header có nhiều bản. Đây không phải lúc nào cũng là vị trí nguồn đầu tiên của toàn bộ retry chain. Với workflow có nhiều lần chuyển tiếp, hãy xem lại chính sách thêm/giữ headers trước khi chọn bản đầu hay bản cuối.

## 7. Original metadata và current metadata phải được lưu riêng

Một record DLT có hai tập thông tin:

| Trường | Current record | Original record |
|---|---|---|
| Topic | record.topic() | Header DLT_ORIGINAL_TOPIC |
| Partition | record.partition() | Header DLT_ORIGINAL_PARTITION |
| Offset | record.offset() | Header DLT_ORIGINAL_OFFSET |
| Timestamp | record.timestamp() | Header DLT_ORIGINAL_TIMESTAMP, nếu được giữ |
| Consumer group | Group đang đọc DLT | Group xử lý ban đầu nếu có metadata riêng |

Ví dụ log đúng:

~~~text
eventId=E-2871
currentTopic=orders.DLT
currentPartition=3
currentOffset=12
originalTopic=orders
originalPartition=3
originalOffset=1254
exception=TemporaryPaymentException
~~~

Tránh log theo dạng mơ hồ:

~~~text
topic=orders.DLT offset=1254
~~~

Đoạn log mơ hồ trên trộn topic đích với offset nguồn, có thể khiến người vận hành seek nhầm hoặc kết luận record DLT không tồn tại.

Một mô hình dữ liệu audit nên đặt tên riêng:

~~~text
FailureAudit
  eventId
  originalTopic
  originalPartition
  originalOffset
  dltTopic
  dltPartition
  dltOffset
  exceptionClass
  firstFailureAt
  recoveredAt
  recoveryStatus
~~~

Vị trí Kafka rất hữu ích cho vận hành, nhưng event ID nghiệp vụ mới là khóa phù hợp hơn khi cần chống trùng hoặc liên kết với database và các hệ thống bên ngoài.

## 8. Giữ header qua nhiều retry topic

Trong non-blocking retry, record có thể đi qua nhiều topic:

~~~text
orders/P3/1254
       |
       v
orders-retry-1000/P3/87
       |
       v
orders-retry-2000/P3/24
       |
       v
orders.DLT/P3/12
~~~

Khi forward, framework có thể giữ header gốc, cập nhật header lỗi và thêm thông tin về attempt, delay hoặc chặng hiện tại. Vì Kafka headers cho phép nhiều header trùng tên, một record có thể có nhiều giá trị liên quan đến quá trình xử lý.

Các nguyên tắc thiết kế:

- Phải phân biệt **record gốc của nghiệp vụ** với **record làm nguồn trực tiếp của lần publish gần nhất**.
- Không tự giả định header original có một giá trị duy nhất khi có nhiều lần forward.
- Nếu cần vị trí gốc xuyên suốt toàn bộ pipeline, hãy đặt các header ứng dụng riêng như x-origin-topic, x-origin-partition và x-origin-offset ngay từ bước đầu hoặc dùng một event ID bất biến.
- Khi custom recoverer tạo ProducerRecord mới, phải giữ metadata nguồn một cách có chủ đích; đừng chỉ copy value mà bỏ quên headers.
- Tránh thêm stack trace quá nhiều lần làm kích thước record phình to qua mỗi chặng.

Spring Kafka có các tùy chọn của DeadLetterPublishingRecoverer để điều khiển việc thêm original headers hoặc giữ/bỏ exception headers cũ, chẳng hạn các API liên quan đến append original headers và strip previous exception headers tùy phiên bản. Hãy sử dụng cơ chế tương ứng với dependency thực tế thay vì dựa vào tên method không được kiểm tra.

### Header ứng dụng bất biến khi cần nguồn đầu tiên

Nếu kiến trúc yêu cầu truy xuất record đầu tiên sau nhiều bước chuyển topic, có thể định nghĩa quy ước riêng:

~~~text
x-event-id:       E-2871
x-origin-topic:   orders
x-origin-part:    3
x-origin-offset:  1254
~~~

Các tên trên là **header tự định nghĩa của ứng dụng**, không phải constant bắt buộc của Spring Kafka. Khi record chuyển tiếp, chỉ set chúng nếu chưa tồn tại, và không ghi đè ở các chặng sau. Cần thống nhất encode/decode các số nguyên giữa producer và consumer.

Không nên thay thế hoàn toàn header DLT của framework bằng header ứng dụng nếu những công cụ điều tra hiện tại đang dựa trên KafkaHeaders.DLT_ORIGINAL_*. Tốt nhất là thiết kế một quy ước rõ: metadata framework phục vụ recovery, metadata ứng dụng phục vụ correlation end-to-end.

## 9. Khi nào header có thể vắng mặt hoặc sai?

Không phải mọi record trên một topic tên DLT đều do DeadLetterPublishingRecoverer tạo ra. Chẳng hạn:

- Một service tự publish trực tiếp vào DLT.
- Một batch job replay copy value nhưng không copy headers.
- Một ứng dụng cũ không dùng các constant/header hiện tại.
- Custom recoverer thay đổi hoặc lọc metadata.
- Dữ liệu được chuyển từ cluster khác qua pipeline không giữ toàn bộ headers.
- Một hệ thống dùng JSON wrapper riêng thay vì Kafka record headers.

Vì vậy, DLT consumer cần kiểm tra:

1. Header original topic có tồn tại không?
2. Partition và offset có đúng độ dài bytes không?
3. Topic nguồn có phải một topic được phép truy xuất/replay không?
4. Partition nguồn có tồn tại không?
5. Offset nguồn có nằm trong retention hiện tại không?
6. Có nhiều header trùng tên cần chọn bản đầu hay bản cuối không?

Nếu metadata thiếu, không nên tự gán original topic bằng tên DLT bỏ hậu tố rồi coi đó là sự thật. Quy tắc tên topic có thể bị tùy biến và retry topology có nhiều chặng. Hãy đánh dấu trạng thái **missing origin metadata** để người vận hành xem xét.

## 10. Vị trí record gốc không phải committed offset

Original offset chỉ ra vị trí **record gây lỗi** trong log nguồn. Committed offset của consumer group lại biểu thị vị trí tiếp theo group sẽ đọc khi tiếp tục hoạt động.

Ví dụ:

~~~text
Record lỗi:
  original topic: orders
  partition: 3
  offset: 1254

Consumer group committed offset:
  orders/P3 = 1255
~~~

Trong ví dụ, group đã đi qua vị trí 1254 theo chính sách xử lý lỗi và recovery. Header original offset vẫn là 1254 để có thể điều tra record lỗi, dù committed offset đã tiến đến 1255.

Không nên dùng original offset để tự động đặt lại toàn bộ consumer group về offset 1254 khi replay một record. Seek/offset reset có thể khiến group đọc lại các record sau đó, tạo side effect trùng và làm ảnh hưởng các partition khác.

Nếu cần replay một record từ DLT, cách phổ biến là tạo một luồng replay riêng hoặc publish record đã được phê duyệt sang topic xử lý phù hợp, với event ID ổn định và idempotency. Việc reset group offset chỉ nên thực hiện trong một quy trình được thiết kế rõ, có đánh giá phạm vi và thời điểm downtime.

## 11. Original offset có thể không còn đọc được

Kafka topic có retention và cleanup policy. Sau khi record gốc hết retention, vị trí original topic/partition/offset vẫn có thể được giữ trong DLT header nhưng record gốc không còn ở log để fetch lại.

Ví dụ:

~~~text
Thứ Hai:
  orders/P3/1254 thất bại
  record được chuyển vào orders.DLT/P3/12

Hai tuần sau:
  orders retention đã xóa đoạn chứa offset 1254
  orders.DLT vẫn giữ record lỗi

Kết quả:
  Có metadata original offset
  Nhưng không thể fetch payload gốc tại offset cũ
~~~

Header vì vậy là **đường dẫn truy vết lịch sử**, không phải bảo đảm record nguồn luôn tồn tại. DLT cần có retention đủ dài để phục vụ điều tra, và không nên chỉ dựa vào topic gốc để khôi phục payload.

Với topic dùng compaction, một record ở offset cũ cũng có thể bị compact khỏi log. Với topic có truncate do sự cố và thao tác vận hành, offset hoặc log history có thể thay đổi. Hãy coi original topic/partition/offset là metadata chẩn đoán gắn với thời điểm sự cố.

## 12. Cách liên kết DLT với log và tracing

Một hệ thống đáng tin cậy cần nối được ba lớp dữ liệu:

1. **Kafka location:** topic, partition, offset ở mỗi chặng.
2. **Business identity:** event ID, order ID hoặc transaction ID.
3. **Execution context:** trace ID, span ID, exception category và application instance.

Ví dụ:

~~~text
eventId=EVT-552
traceId=trace-abc
orderId=ORD-1009
origin=orders/P3/1254
dlt=orders.DLT/P3/12
attempt=4
exception=DownstreamTimeoutException
consumerGroup=orders-service
~~~

Với event ID, có thể tìm tất cả lần xử lý của một sự kiện qua nhiều topic và instance. Với original offset, có thể tìm record nguồn nếu retention còn. Với trace ID, có thể điều tra call tới service và database.

Không dùng original offset làm khóa idempotency toàn hệ thống nếu record có thể bị republish sang topic khác hoặc nhiều cluster. Offset là định danh vị trí Kafka, không phải định danh nghiệp vụ bất biến qua mọi lần chuyển tiếp.

Nếu dùng metrics, tránh gắn event ID, offset hoặc trace ID làm metric label có cardinality cao. Dùng chúng trong log/trace và dùng exception category, outcome, listener ID làm nhãn metric.

## 13. Recovery thất bại và vấn đề publish DLT

Ghi metadata đúng chưa đủ để bảo đảm recovery thành công. DeadLetterPublishingRecoverer sử dụng Kafka producer; thao tác publish có thể lỗi do:

- DLT chưa được tạo hoặc sai tên.
- Partition đích không tồn tại.
- ACL không cho phép produce.
- Broker hoặc mạng unavailable.
- Serializer không xử lý được value đã deserialize lỗi.
- Record quá lớn do payload và exception headers.
- Timeout hoặc replication không đáp ứng điều kiện acknowledge.

Khi recoverer lỗi, ứng dụng cần chính sách rõ về việc giao lại record hoặc tiếp tục retry. **Không được commit/ack bỏ qua record lỗi một cách thiếu kiểm soát chỉ vì đã cố publish sang DLT.**

Ngoài ra, việc publish DLT thành công và commit offset nguồn là hai thao tác khác nhau. Nếu crash ở ranh giới giữa chúng, record nguồn có thể được đọc lại và publish sang DLT lần nữa. Hai record DLT có thể mang cùng original topic/partition/offset nhưng có **DLT offset khác nhau**.

~~~text
DLT record 1:
  currentOffset=12
  original=orders/P3/1254

DLT record 2:
  currentOffset=13
  original=orders/P3/1254

Hai bản ghi DLT có thể cùng nguồn,
nhưng không phải cùng vị trí trên DLT.
~~~

Điều này cho thấy bộ ba original location hữu ích để phát hiện các lần recovery lặp, nhưng cần kết hợp event ID và quy tắc nghiệp vụ để quyết định có bỏ qua một record hay không.

## 14. Trường hợp deserialization thất bại

Một số record lỗi trước khi vào được listener, chẳng hạn bytes không giải mã được thành OrderEvent. Khi đó, error handling cần có khả năng nhận thông tin lỗi ở tầng deserializer.

Spring Kafka thường dùng ErrorHandlingDeserializer để truyền thông tin deserialization failure cho container/error handler. Tùy cách cấu hình, record cần chuyển sang DLT có thể chứa raw bytes của value bị lỗi thay vì một object kiểu OrderEvent.

Các điểm cần chú ý:

- Không được giả định DLT value luôn deserialize được bằng cùng class như topic gốc.
- DLT producer cần serializer tương thích với cả payload bình thường và payload bytes của record bị lỗi.
- Header original topic/partition/offset vẫn quan trọng, đặc biệt khi business listener chưa từng được gọi.
- Exception header có thể chứa stack trace, class và message; cần giới hạn lộ lọt dữ liệu nhạy cảm.
- Khi DLT consumer nhận bytes, phải có đường điều tra hoặc công cụ hiển thị payload an toàn, không tiếp tục deserialize mù quáng bằng schema đã gây lỗi.

Đối với lỗi schema không thể phục hồi, retry nhiều lần thường không giúp ích. Có thể chuyển thẳng DLT theo classifier, giữ raw bytes và metadata đủ để khắc phục schema hoặc reprocess có kiểm soát.

## 15. Replay từ DLT mà không làm mất provenance

Replay là quá trình đưa record DLT quay trở lại luồng xử lý sau khi lỗi được khắc phục. Khi replay, cần quyết định giữ cả lịch sử nguồn và lịch sử DLT như thế nào.

Một quy trình an toàn:

1. Chọn record DLT theo event ID hoặc current DLT topic/partition/offset.
2. Đọc original headers và xác minh event ID, kiểu payload, nguyên nhân lỗi.
3. Xác định lỗi đã được khắc phục và hệ thống downstream sẵn sàng.
4. Kiểm tra record đã được xử lý thành công ở nơi khác chưa.
5. Publish record sang topic replay phù hợp, giữ event ID và provenance cần thiết.
6. Gắn metadata về hành động replay: người vận hành, lý do, thời điểm, lần replay.
7. Theo dõi kết quả xử lý và tránh vòng DLT → replay → DLT vô hạn.
8. Ghi nhận trạng thái audit mà không nhầm current offset với original offset.

Ví dụ metadata audit:

~~~text
eventId=EVT-552
original=orders/P3/1254
firstDlt=orders.DLT/P3/12
replayedTo=orders-replay/P1/42
replayAttempt=1
replayReason=payment-service-recovered
~~~

Không ghi đè original topic/partition/offset bằng vị trí replay nếu trường đó có ý nghĩa là **nguồn đầu tiên của sự kiện**. Dùng trường hoặc header riêng cho replay location. Nếu pipeline đã có cơ chế append original headers của framework, cần phân biệt provenance bất biến với các chặng recovery gần nhất.

Một record đã xử lý một phần trước khi lỗi vẫn có thể tạo side effect trùng khi replay. Vì vậy, phải sử dụng idempotency key, unique constraint hoặc business state check. Metadata original offset chỉ giúp truy vết, không tự chống trùng.

## 16. DLT consumer cần phản ứng thế nào với metadata?

Không nên để DLT handler tự động replay toàn bộ record ngay khi nhận được. DLT thường là nơi tập trung các lỗi cần quan sát; nếu DLT handler lại gọi service đang lỗi, hệ thống có thể rơi vào vòng retry mới.

Một lựa chọn an toàn là DLT handler ghi lại sự cố vào failure store để vận hành điều tra:

~~~java
@DltHandler
public void handleDlt(ConsumerRecord<String, OrderEvent> record) {
    String originTopic = readUtf8Header(
            record.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC);
    Integer originPartition = readIntHeader(
            record.headers(), KafkaHeaders.DLT_ORIGINAL_PARTITION);
    Long originOffset = readLongHeader(
            record.headers(), KafkaHeaders.DLT_ORIGINAL_OFFSET);

    failureAuditService.upsertByEventId(
            record.value().eventId(),
            originTopic,
            originPartition,
            originOffset,
            record.topic(),
            record.partition(),
            record.offset());
}
~~~

Ví dụ giả định value đã deserialize thành OrderEvent và có eventId(). Với lỗi deserialize, cần handler khác xử lý byte[] hoặc payload thô. Nếu upsert dùng event ID, cần quyết định cách lưu nhiều lần DLT cùng event ID; không nên làm mất lịch sử lỗi nếu dữ liệu audit cần cho điều tra.

Từ DLT handler, cũng có thể gửi cảnh báo hoặc tạo ticket, nhưng phải tránh chèn toàn bộ payload/stack trace nhạy cảm vào các hệ thống có phạm vi truy cập rộng.

## 17. Bảo vệ tính toàn vẹn và bảo mật của metadata

Header là một phần dữ liệu của Kafka record. Tùy hệ thống, producer và consumer có thể đọc, sửa hoặc ghi lại chúng. Vì vậy, không nên coi original headers như một chữ ký chống giả mạo.

Với workflow có yêu cầu kiểm toán cao:

- Kiểm soát ACL của producer ghi DLT và consumer đọc DLT.
- Giới hạn người có quyền thay đổi retry/DLT routing.
- Ghi audit bên ngoài Kafka khi record chuyển sang trạng thái lỗi nghiêm trọng.
- Dùng event ID và chữ ký dữ liệu khi cần bảo đảm tính toàn vẹn vượt qua trust boundary.
- Giới hạn dữ liệu cá nhân trong exception message và stack trace.
- Không cho phép replay tùy ý từ một DLT có dữ liệu không được kiểm chứng.

Nếu một service không tin cậy có quyền publish trực tiếp vào DLT, original topic và offset do nó gửi có thể không phản ánh vị trí tồn tại thực tế. Hệ thống điều tra nên kiểm tra provenance và quyền truy cập trước khi ra quyết định quan trọng.

## 18. Quan sát và vận hành

Các log/metric nên giúp trả lời ba câu hỏi: record lỗi bắt nguồn từ đâu, đã đi qua bước retry nào và kết quả recovery là gì?

Nên ghi log có cấu trúc:

~~~text
eventId=EVT-552
listener=orders-listener
consumerGroup=orders-service
currentTopic=orders.DLT
currentPartition=3
currentOffset=12
originalTopic=orders
originalPartition=3
originalOffset=1254
exceptionClass=DownstreamTimeoutException
outcome=published_to_dlt
~~~

Nên theo dõi:

- Số record được publish sang DLT, theo topic nguồn và exception category.
- DLT publish error rate và latency.
- DLT consumer lag và tuổi record lâu nhất.
- Tỷ lệ record thiếu original topic/partition/offset headers.
- Số bản ghi DLT lặp cùng event ID hoặc cùng original location.
- Số yêu cầu replay, replay thành công và replay lại thất bại.
- Thời gian từ lỗi đầu tiên đến lúc record được xử lý thành công hoặc đóng sự cố.
- Dung lượng DLT, retention và nguy cơ record hết hạn.

Topic/partition/offset và event ID nên có trong log hoặc trace, không nên dùng offset làm metric label. Để thống kê theo topic nguồn, có thể dùng một nhãn có tập giá trị được kiểm soát; cần bảo vệ dashboard khỏi cardinality tăng ngoài dự kiến.

Khi thấy record trên DLT, quy trình điều tra có thể bắt đầu từ **current DLT location**, đọc các header original, tìm event ID và trace, sau đó đối chiếu log của listener gốc. Nếu origin record đã hết retention, sử dụng payload trên DLT và audit store làm dữ liệu điều tra chính.

## 19. Các tình huống lỗi thường gặp

### Không có DLT_ORIGINAL_TOPIC

Có thể record được publish thủ công, copy sai headers hoặc không dùng recoverer của Spring Kafka. Đánh dấu missing metadata; không tự tạo topic nguồn từ tên DLT rồi khẳng định kết quả chính xác.

### Original partition khác current partition

Có thể destination resolver hoặc partitioner định tuyến lại record. Đừng xem đây là lỗi tự động. Hãy đọc đúng original partition header và kiểm tra chiến lược routing.

### Original offset lớn hơn DLT offset

Hoàn toàn bình thường. Offset được cấp độc lập trong từng partition của từng topic; không có quan hệ so sánh thứ tự giữa hai offset ở hai log khác nhau.

### Hai record DLT có cùng original offset

Có thể phát sinh do retry sau crash giữa publish và commit, do replay hoặc do custom recovery. Dùng event ID và audit để xác định liệu cùng event đã được xử lý một lần hay nhiều lần.

### Seek original offset nhưng không tìm được record

Có thể record gốc đã hết retention hoặc bị compact, topic/partition không đúng, hoặc metadata bị thay đổi. Không suy ra record DLT chắc chắn sai; kiểm tra log start offset và chính sách cleanup.

### Không giải mã được original offset

Kiểm tra header có tồn tại và có đúng tám bytes theo encoding mong đợi không. Custom recoverer có thể ghi chuỗi hoặc format khác. Không dùng Long.parseLong trên bytes nhị phân khi chưa biết cách encode.

### Record qua nhiều retry topic nên có nhiều original headers

Kiểm tra chính sách append/strip và cách chọn firstHeader hay lastHeader. Nếu cần nguồn đầu tiên bất biến, dùng event ID và origin metadata riêng xuyên suốt topology.

### Replay thành công nhưng record lại vào DLT

Có thể lỗi gốc chưa được khắc phục, replay sai kiểu payload hoặc mất idempotency/state. Xem log theo event ID và chặng retry, không chỉ current DLT offset.

## 20. Kiểm thử khả năng giữ original metadata

Nên có bài kiểm thử tích hợp dùng Kafka broker test hoặc môi trường tương đương để xác nhận record thật được publish sang DLT cùng headers dự kiến.

Các kịch bản cần bao phủ:

1. Listener ném exception non-retryable: record xuất hiện ở DLT với original topic, partition và offset đúng.
2. Listener retry vài lần rồi thất bại: metadata nguồn vẫn truy được sau khi chuyển chặng.
3. Destination resolver đổi partition: original partition khác current partition nhưng vẫn được đọc chính xác.
4. Custom recoverer copy headers: không mất original metadata.
5. Record được xử lý bởi @RetryableTopic qua nhiều retry topic: chính sách chọn header nguồn được giữ đúng.
6. Payload lỗi deserialize: raw bytes và metadata gốc vẫn phục vụ điều tra theo cấu hình.
7. DLT publish thất bại: không ghi nhận nhầm recovery thành công.
8. Crash hoặc replay gây hai record DLT cùng nguồn: audit phát hiện được trùng.
9. Record gốc đã hết retention: quy trình điều tra vẫn dùng được dữ liệu DLT.
10. Header thiếu hoặc sai độ dài: DLT consumer không crash ngoài kiểm soát, có cảnh báo metadata thiếu.

Một assertion đơn giản với ConsumerRecord DLT:

~~~java
String originalTopic = readUtf8Header(
        dltRecord.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC);

Integer originalPartition = readIntHeader(
        dltRecord.headers(), KafkaHeaders.DLT_ORIGINAL_PARTITION);

Long originalOffset = readLongHeader(
        dltRecord.headers(), KafkaHeaders.DLT_ORIGINAL_OFFSET);

assertThat(originalTopic).isEqualTo("orders");
assertThat(originalPartition).isEqualTo(3);
assertThat(originalOffset).isEqualTo(1254L);
~~~

Giá trị 1254L chỉ là ví dụ; test thật cần lấy topic/partition/offset của record nguồn từ metadata produce hoặc consumer đã được xác nhận, không hardcode offset tùy ý vì Kafka cấp offset theo trạng thái log thực tế.

## 21. Những hiểu nhầm thường gặp

**Record được gửi sang DLT vẫn giữ nguyên offset Kafka.** Không đúng. DLT là topic/log khác và broker cấp offset mới. Original offset được giữ trong metadata.

**Original offset là offset đã commit của group.** Không đúng. Original offset chỉ vị trí record lỗi. Committed offset là vị trí tiếp theo group sẽ đọc.

**Chỉ cần original offset là có thể tìm record gốc.** Không đúng. Cần original topic và partition; hơn nữa record có thể đã hết retention.

**DLT partition luôn bằng original partition.** Không đúng nếu destination resolver hoặc partitioner chọn partition khác; phải đọc metadata nguồn.

**Dùng offset nguồn làm idempotency key nghiệp vụ là đủ.** Không đúng cho mọi trường hợp. Event có thể được republish hoặc chuyển cluster; event ID ổn định thường phù hợp hơn.

**Header DLT chắc chắn có trên mọi record của một topic tên DLT.** Không đúng. Custom publisher có thể không bổ sung chúng; DLT consumer cần xử lý trường hợp thiếu.

**Chuyển sang DLT nghĩa là xử lý nghiệp vụ đã hoàn thành.** Không đúng. DLT là luồng recovery/điều tra và không chứng minh side effect nghiệp vụ thành công.

**Header original luôn trỏ về record đầu tiên bất kể bao nhiêu lần retry.** Không nên giả định. Cần xác minh cấu hình append headers và các lần forward.

**Có original topic/offset là có bảo đảm exactly-once.** Không đúng. Metadata chỉ phục vụ truy vết; publish và commit có thể tạo bản sao, side effect vẫn cần idempotency.

**Có thể replay bằng cách reset offset group về original offset mà không ảnh hưởng gì.** Không đúng. Reset có thể làm đọc lại hàng loạt record và tái thực hiện side effect.

## 22. Quy trình triển khai khuyến nghị

Khi thiết kế dead-letter recovery cho một listener Spring Kafka, cần xác định cách giữ metadata ngay từ đầu, thay vì đợi khi có sự cố mới bổ sung.

1. Chọn DLT naming, retention, partition count và ACL phù hợp.
2. Dùng DeadLetterPublishingRecoverer hoặc recoverer tự viết có chính sách giữ metadata rõ ràng.
3. Bổ sung các header original topic, partition và offset theo đúng encoding.
4. Giữ event ID nghiệp vụ bất biến để đối chiếu qua main topic, retry topic và DLT.
5. Nếu qua nhiều chặng, quyết định cách lưu first origin và most recent hop, tránh dùng một field cho cả hai.
6. Cấu hình producer ghi DLT đáng tin cậy và quan sát lỗi publish.
7. Xây DLT handler có khả năng đọc header vắng mặt hoặc sai format một cách an toàn.
8. Lưu current DLT location và original Kafka location vào các field tách biệt của audit log.
9. Thiết kế replay có phê duyệt, idempotency và theo dõi kết quả.
10. Kiểm thử mất header, partition mapping khác, record trùng, crash và record gốc đã hết retention.

**Giữ original topic và offset** là nền tảng để biến DLT từ một nơi chứa record lỗi thành một cơ chế recovery có thể điều tra và truy vết. Cần giữ cả original topic, original partition và original offset, phân biệt chúng với vị trí record trên DLT, đồng thời kết hợp event ID, headers, log, audit và idempotency. Khi đó, nhóm vận hành có thể xác định record lỗi đến từ đâu, đã xử lý qua những bước nào và nên replay ra sao mà không đánh đồng metadata truy vết với bảo đảm xử lý đúng một lần.
