# Đọc và xử lý dead-letter record

Dead-letter topic (DLT) lưu những record consumer không thể xử lý thành công theo chính sách retry và recovery. Record được chuyển sang DLT vẫn là một Kafka record: nó giữ key, value và các header được chuyển tiếp, đồng thời thường có thêm metadata cho biết record xuất phát từ topic, partition, offset nào và lỗi gì đã khiến nó bị đưa vào DLT.

Đọc DLT không chỉ là viết một listener subscribe vào topic có hậu tố `.DLT`. Consumer cần hiểu dữ liệu có thể là object đã deserialize hoặc raw bytes chưa deserialize được, đọc đúng metadata nguồn, phân loại nguyên nhân, lưu bằng chứng đủ để điều tra và quyết định có thể replay hay cần xử lý thủ công. Khi replay, phải kiểm soát idempotency, thứ tự, offset và tác động nghiệp vụ để không biến việc khôi phục thành một lần xử lý trùng.

Bài học thuộc chương **Dead letter và recoverer** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách đọc dead-letter record, điều tra lỗi, lưu trữ và khôi phục dữ liệu bằng Spring Kafka.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích DLT record được tạo ra và mang theo những thông tin nào.
- Phân biệt metadata của record trong DLT với metadata của record gốc.
- Tạo DLT consumer với group ID và deserializer phù hợp.
- Đọc raw bytes khi record gốc không deserialize được.
- Trích xuất original topic, partition, offset và exception headers.
- Phân loại lỗi để quyết định sửa dữ liệu, sửa consumer hay replay.
- Lưu dead-letter record bền vững và chống lưu trùng.
- Replay record về topic gốc hoặc luồng recovery có kiểm soát.
- Bảo toàn key, header cần thiết và cân nhắc partition ordering.
- Vận hành DLT với retention, ACL, monitoring, ownership và runbook.

## 1. Dead-letter record là gì?

Khi listener xử lý record thất bại, error handler có thể retry. Nếu record vẫn không xử lý được sau số lần thử hoặc được phân loại là không retry, recoverer có thể publish record sang một topic riêng, thường có tên nguồn cộng hậu tố `.DLT`.

Ví dụ:

~~~text
orders.created
      |
      | listener fails
      v
DefaultErrorHandler
      |
      | retry exhausted / non-retryable
      v
DeadLetterPublishingRecoverer
      |
      v
orders.created.DLT
~~~

Record trong DLT thường mang:

- Key và value của record được recover, có thể là object hoặc raw bytes tùy nơi lỗi xảy ra và cấu hình serializer.
- Các application headers đã có trên record.
- Header metadata do Spring Kafka bổ sung để lưu nguồn gốc và thông tin exception.
- Metadata mới của chính record DLT như topic, partition, offset và timestamp do Kafka cấp khi ghi DLT.

DLT là vùng cách ly để điều tra và recovery. Việc record đã vào DLT không có nghĩa nghiệp vụ đã được xử lý thành công; nó chỉ có nghĩa luồng chính đã chuyển record sang một nơi khác theo chính sách đã cấu hình.

## 2. Phân biệt metadata DLT và metadata record gốc

Một record được đọc từ `orders.created.DLT` có hai nhóm metadata khác nhau:

| Thông tin | Ý nghĩa |
|---|---|
| DLT topic | Topic mà consumer DLT đang đọc. |
| DLT partition | Partition của record trong topic DLT. |
| DLT offset | Offset của record trong topic DLT. |
| DLT timestamp | Timestamp của bản ghi DLT. |
| Original topic | Topic nơi record gặp lỗi ban đầu. |
| Original partition | Partition nguồn của record gốc. |
| Original offset | Offset của record gốc. |
| Exception headers | Lớp exception, message và thông tin lỗi được recoverer ghi lại. |

Không dùng offset của DLT thay cho original offset. Ví dụ record có `orders.created.DLT-2@15`, nhưng header có thể chỉ ra record nguồn là `orders.created-2@841`. Đây là hai vị trí độc lập trong hai log khác nhau.

Thông tin nguồn rất quan trọng khi đối chiếu log producer, consumer lag, dữ liệu gốc hoặc tìm record trong retention của topic nguồn.

## 3. Các header metadata thường gặp

Spring Kafka định nghĩa các hằng số trong `KafkaHeaders` để đọc metadata dead-letter. Những tên thường dùng gồm:

| Hằng số | Nội dung |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Tên topic gốc. |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition gốc. |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset gốc. |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Timestamp gốc. |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE` | Loại timestamp gốc. |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên đầy đủ của lớp exception. |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Thông điệp exception. |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace được lưu trong header. |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group nguồn trong các phiên bản hỗ trợ. |

Bộ header chính xác phụ thuộc phiên bản Spring Kafka và cấu hình `DeadLetterPublishingRecoverer`. Hãy dùng các hằng số có trong dependency thực tế của dự án, thay vì hardcode tên header hoặc giả định mọi phiên bản đều có cùng tập metadata.

Header Kafka có giá trị dạng `byte[]`. Một số header metadata là text UTF-8; các giá trị số được mã hóa theo định dạng của Spring Kafka. Khi đọc trực tiếp `ConsumerRecord`, cần giải mã theo đúng kiểu của header. Khi nhận qua Spring `MessageHeaders`, mapper có thể đã chuyển đổi giá trị thành kiểu Java.

## 4. DLT consumer nên có group ID riêng

Consumer xử lý DLT thường là một chức năng vận hành riêng: phân loại, lưu trữ, sửa dữ liệu hoặc replay. Vì vậy nên dùng group ID riêng, ví dụ `orders-dlt-review`.

Các replica của cùng một DLT handler dùng chung group ID để chia nhau partition. Một consumer group khác có thể đọc DLT độc lập cho mục đích audit hoặc analytics.

Ví dụ:

~~~java
@Component
public class OrdersDeadLetterListener {

    @KafkaListener(
            topics = "orders.created.DLT",
            groupId = "orders-dlt-review"
    )
    public void inspect(ConsumerRecord<byte[], byte[]> record) {
        // Lưu record lỗi để điều tra và phân loại.
    }
}
~~~

Group ID của DLT consumer không nên vô tình trùng với group xử lý topic nguồn. Offset của DLT cần độc lập để việc đọc và điều tra DLT không làm thay đổi tiến độ của consumer nghiệp vụ.

Nếu DLT consumer mới chưa có offset, `auto.offset.reset` quyết định vị trí bắt đầu. Với DLT cần điều tra backlog hiện có, thường phải chủ động chọn `earliest` hoặc dùng quy trình seek phù hợp. `auto.offset.reset` chỉ áp dụng khi group chưa có offset hợp lệ; nó không tua lại group đã commit.

## 5. Vì sao nên đọc DLT dưới dạng raw bytes?

DLT có thể chứa nhiều dạng value:

- Record đã deserialize thành object nhưng listener xử lý nghiệp vụ thất bại.
- Record không deserialize được, do đó value gốc vẫn chỉ là byte[].
- Record được chuyển tiếp qua nhiều service hoặc retry stage với serializer khác nhau.

Nếu dùng một DTO deserializer cho toàn bộ DLT, consumer có thể lại thất bại khi gặp record vốn đã vào DLT vì lỗi deserialize. Một cách an toàn để xây dựng công cụ điều tra là đọc key và value dưới dạng `byte[]`, sau đó chỉ deserialize thủ công khi đã xác định định dạng.

Ví dụ tạo consumer factory raw bytes:

~~~java
@Bean
ConsumerFactory<byte[], byte[]> dltRawConsumerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers) {

    Map<String, Object> props = new HashMap<>();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    return new DefaultKafkaConsumerFactory<>(
            props,
            new ByteArrayDeserializer(),
            new ByteArrayDeserializer()
    );
}
~~~

Tạo listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<byte[], byte[]>
dltRawListenerFactory(
        ConsumerFactory<byte[], byte[]> dltRawConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<byte[], byte[]>();

    factory.setConsumerFactory(dltRawConsumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Listener sử dụng factory riêng:

~~~java
@KafkaListener(
        topics = "orders.created.DLT",
        groupId = "orders-dlt-review",
        containerFactory = "dltRawListenerFactory"
)
public void inspect(ConsumerRecord<byte[], byte[]> record) {
    // record.key() và record.value() vẫn là byte[].
}
~~~

Factory raw bytes giúp lưu nguyên payload để điều tra, không phụ thuộc class Java hiện tại. Nếu DLT chỉ chứa một loại event có schema ổn định và DLT serializer được kiểm soát, có thể dùng deserializer typed. Tuy nhiên, công cụ quarantine/recovery tổng quát thường nên giữ được raw bytes.

ByteArrayDeserializer chỉ quyết định cách DLT consumer đọc dữ liệu. Nó không sửa được lỗi serialize ở phía publish DLT. Nếu cùng một DLT chứa cả raw `byte[]` từ lỗi deserialize và object đã giải mã từ lỗi nghiệp vụ, KafkaTemplate dùng bởi `DeadLetterPublishingRecoverer` phải serialize được cả hai dạng. Có thể dùng serializer phân loại theo kiểu hoặc các KafkaTemplate riêng; cần kiểm thử cả hai đường đi trước khi triển khai.

## 6. Đọc metadata nguồn từ ConsumerRecord

Có thể lấy header bằng `record.headers().lastHeader(name)`. Ví dụ helper đọc giá trị text UTF-8:

~~~java
private String headerAsString(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(header.value(), StandardCharsets.UTF_8);
}
~~~

Đọc một số metadata:

~~~java
String originalTopic =
        headerAsString(record.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC);

String exceptionType =
        headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_FQCN);

String exceptionMessage =
        headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_MESSAGE);
~~~

Với partition và offset, cần giải mã số theo định dạng header của phiên bản Spring Kafka đang dùng. Ví dụ nếu header số được mã hóa thành integer/long theo dạng big-endian:

~~~java
private Integer headerAsInt(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getInt();
}

private Long headerAsLong(Headers headers, String name) {
    Header header = headers.lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return ByteBuffer.wrap(header.value()).getLong();
}
~~~

Các helper trên minh họa cách giải mã header số dạng binary; phải đối chiếu encoding của phiên bản Spring Kafka thực tế và xử lý trường hợp header sai độ dài. Không ép mọi header thành String rồi parse số nếu framework lưu số dưới dạng binary.

Nếu cần xem toàn bộ header trùng tên, dùng `record.headers().headers(name)`. Một record có thể đã qua nhiều lần dead-letter/recover nên có header trùng tên; `lastHeader` chỉ lấy giá trị cuối.

## 7. Đọc raw payload mà không làm lộ dữ liệu

Raw bytes giúp điều tra lỗi deserialize, nhưng không nên ghi toàn bộ payload ra log. Payload có thể chứa thông tin cá nhân, token hoặc dữ liệu thanh toán.

Một listener có thể tạo envelope để lưu vào kho quarantine:

~~~java
@KafkaListener(
        topics = "orders.created.DLT",
        groupId = "orders-dlt-review",
        containerFactory = "dltRawListenerFactory"
)
public void inspect(ConsumerRecord<byte[], byte[]> record) {
    DltEnvelope envelope = new DltEnvelope(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            record.value(),
            headerAsString(record.headers(), KafkaHeaders.DLT_ORIGINAL_TOPIC),
            headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_FQCN),
            headerAsString(record.headers(), KafkaHeaders.DLT_EXCEPTION_MESSAGE)
    );

    deadLetterRepository.saveIfAbsent(envelope);
}
~~~

`saveIfAbsent` là thao tác minh họa. Trong triển khai, nên có khóa duy nhất để tránh lưu cùng một DLT record nhiều lần, ví dụ DLT topic + partition + offset. Nếu cần nhận diện record nguồn, lưu thêm original topic + partition + offset.

Log chỉ nên chứa định danh, loại lỗi và metadata cần thiết. Raw key/value nên được lưu trong kho có ACL, encryption và retention phù hợp.

## 8. Phân loại record trước khi quyết định xử lý

Không nên replay mọi record trong DLT theo cùng một cách. Cần xác định nguyên nhân và khả năng phục hồi.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Payload không hợp lệ | JSON sai cấu trúc, byte bị cắt | Lưu raw bytes, xác minh nguồn phát; sửa hoặc loại bỏ theo quyết định nghiệp vụ. |
| Schema không tương thích | Producer thêm/đổi field không tương thích | Sửa consumer/schema rồi kiểm thử trước khi replay. |
| Type mapping sai | Header trỏ tới class không tồn tại hoặc không được phép | Sửa type mapping hoặc trusted packages có kiểm soát. |
| Lỗi dependency tạm thời | Database hoặc HTTP service bị timeout kéo dài | Kiểm tra dependency đã phục hồi rồi replay có giới hạn. |
| Lỗi nghiệp vụ | Trạng thái đơn hàng không cho phép chuyển bước | Đối chiếu trạng thái hiện tại; có thể cần thao tác nghiệp vụ thay vì replay nguyên trạng. |
| Lỗi cấu hình | Sai endpoint, credential, ACL | Sửa cấu hình và xác minh consumer hoạt động trước khi replay. |
| Record không còn cần thiết | Event hết hạn theo nghiệp vụ | Đóng case với lý do rõ ràng và lưu audit. |

Một record có thể đã vào DLT từ lâu. Trạng thái nghiệp vụ hiện tại có thể đã thay đổi, vì vậy payload cũ không nhất thiết còn hợp lệ để chạy lại. Người xử lý cần xác minh cả nguyên nhân kỹ thuật lẫn trạng thái nghiệp vụ.

## 9. Quy trình xử lý dead-letter record

Một quy trình vận hành có thể gồm các bước:

1. Nhận record từ DLT bằng consumer group chuyên trách.
2. Ghi nhận DLT topic, partition, offset và original topic/partition/offset.
3. Lưu raw key, value và headers vào kho quarantine bền vững.
4. Phân loại lỗi dựa trên exception, schema/version và log liên quan.
5. Gắn trạng thái case: NEW, INVESTIGATING, READY_TO_REPLAY, RESOLVED hoặc REJECTED.
6. Xác định owner và người phê duyệt nếu replay có side effect.
7. Sửa nguyên nhân: payload, schema, code, cấu hình hoặc dependency.
8. Chạy test với chính raw bytes và metadata của record lỗi.
9. Replay một record thử nghiệm hoặc một nhóm nhỏ.
10. Xác minh kết quả nghiệp vụ, ordering và idempotency.
11. Mở rộng replay theo batch có giới hạn.
12. Đóng case và lưu audit trail.

DLT consumer nên thực hiện lưu trữ bền vững trước khi offset của DLT được xác nhận. Nếu listener lưu vào database rồi process dừng trước khi Kafka commit offset, DLT record có thể được giao lại. Vì vậy thao tác lưu cần idempotent, chẳng hạn unique key theo DLT topic/partition/offset.

## 10. Replay record về topic gốc

Sau khi sửa nguyên nhân, có thể publish record trở lại topic nguồn. Có hai cách thường gặp:

- Replay raw bytes: phù hợp khi muốn giữ nguyên byte key/value, nhất là record từng lỗi deserialize.
- Deserialize rồi publish object: phù hợp khi đã xác minh schema và muốn chuyển record sang contract mới.

Với raw replay, dùng producer có `ByteArraySerializer` cho cả key và value. Ví dụ:

~~~java
ProducerRecord<byte[], byte[]> replay = new ProducerRecord<>(
        originalTopic,
        originalPartition,
        null,
        dltRecord.key(),
        dltRecord.value(),
        replayHeaders
);

rawBytesKafkaTemplate.send(replay);
~~~

`originalTopic`, `originalPartition` và `replayHeaders` được tạo từ metadata đã xác minh. Chỉ chỉ định original partition nếu partition đó vẫn tồn tại và quyết định kiến trúc là giữ record ở đúng partition. Nếu partition count đã thay đổi hoặc partition cũ không còn hợp lệ, cần chọn partitioning mới có chủ đích.

Không sao chép mù quáng toàn bộ DLT headers sang topic nguồn. Hãy tạo bộ header mới, giữ correlation ID/event ID/trace context cần thiết và thêm metadata như `replay_id`, `replayed_from` hoặc `replay_timestamp`. Các header exception và original DLT có thể gây nhầm lẫn nếu tiếp tục xuất hiện như lỗi hiện tại của record đã được sửa.

Nếu dùng typed replay, hãy deserialize bằng phiên bản schema đã xác minh rồi gửi qua KafkaTemplate có serializer đúng với topic nguồn. Không gửi một chuỗi JSON qua JsonSerializer nếu điều đó làm JSON bị serialize thành chuỗi JSON lồng nhau.

## 11. Replay không tự khôi phục thứ tự cũ

DLT là một luồng riêng, có offset và thời điểm xử lý riêng. Trong thời gian record gốc nằm ở DLT, các record phía sau trong topic nguồn có thể đã được xử lý. Khi replay record cũ, nó có thể đến sau những sự kiện mới hơn.

Ví dụ:

~~~text
Topic nguồn:
offset 40: OrderCreated
offset 41: OrderPaid
offset 42: OrderShipped

Record offset 41 lỗi và được chuyển DLT.
Consumer nguồn tiếp tục xử lý offset 42 sau recovery.

Sau đó replay offset 41 về topic nguồn:
record replay được ghi ở offset mới, ví dụ 57.
~~~

Record replay ở offset 57 không tự quay lại vị trí 41. Kafka không chèn record vào giữa log đã tồn tại. Vì vậy, replay có thể tạo thứ tự vật lý mới và listener cần kiểm tra sequence/version hoặc trạng thái aggregate trước khi áp dụng.

Nếu thứ tự nghiệp vụ bắt buộc, hãy cân nhắc:

- Dừng hoặc cô lập luồng liên quan trước khi replay.
- Replay theo aggregate/key với thứ tự sequence được kiểm soát.
- Dùng version hoặc sequence number trong event để từ chối cập nhật cũ.
- Gửi vào topic recovery riêng và hợp nhất theo logic nghiệp vụ.
- Xác minh trạng thái hiện tại trước khi thực hiện side effect.

Giữ nguyên partition number khi replay chỉ giúp chọn cùng partition, không khôi phục offset cũ và không tự bảo đảm thứ tự với các record đã được xử lý sau đó.

## 12. Idempotency và chống xử lý trùng khi replay

Replay là một lần giao record mới từ góc nhìn consumer, ngay cả khi payload giống hệt record cũ. Nếu listener đã tạo side effect trước khi record bị đưa vào DLT hoặc trong lần xử lý trước, replay có thể lặp thao tác.

Dùng event ID ổn định để chống trùng:

~~~java
@Transactional
public void handle(OrderCreatedEvent event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderService.createOrder(event);

    processedEventRepository.save(
            new ProcessedEvent(event.eventId())
    );
}
~~~

Trong production, unique constraint trên event ID cần bảo vệ thao tác kiểm tra và ghi nhận trong cùng transaction database với thay đổi nghiệp vụ. Chỉ kiểm tra trước bằng `existsById` mà không có ràng buộc duy nhất có thể bị race khi hai consumer xử lý đồng thời.

Nếu cần replay một sự kiện đã xử lý nhưng muốn tạo hành động mới, hãy dùng một command/recovery workflow có định danh riêng và quy tắc nghiệp vụ rõ ràng. Không xóa dấu idempotency tùy tiện để ép event chạy lại.

## 13. DLT consumer cần commit offset khi nào?

Offset của DLT consumer chỉ nên tiến lên sau khi record đã được xử lý an toàn theo chính sách của ứng dụng. Ví dụ listener lưu envelope vào kho quarantine thành công rồi mới return; container có thể commit theo AckMode đã cấu hình.

Nếu listener ghi log rồi return dù database lưu trữ thất bại, offset có thể được commit và record không còn được giao lại. Nếu listener lưu thành công nhưng commit offset thất bại, record có thể được giao lại; thao tác lưu cần idempotent.

Các nguyên tắc:

- Không acknowledge record trước khi dữ liệu cần bảo toàn đã được ghi bền vững.
- Dùng unique key để chống lưu trùng.
- Phân biệt lỗi lưu DLT record với lỗi xử lý/replay nghiệp vụ.
- Giới hạn retry của chính DLT consumer và có DLT cấp hai hoặc cảnh báo nếu cần.
- Không để DLT handler thất bại lặp vô hạn mà không có owner.

Nếu DLT consumer chỉ phục vụ dashboard hoặc quan sát, vẫn cần quyết định rõ có lưu archive hay chỉ đọc tạm. Offset commit không thay thế retention của topic DLT.

## 14. Retention, partition và quyền truy cập DLT

DLT thường chứa dữ liệu lỗi cần giữ lâu hơn luồng chính để điều tra, nhưng retention vô hạn cũng gây chi phí và rủi ro dữ liệu.

Cần xác định:

- Retention đủ dài cho thời gian phát hiện và xử lý sự cố.
- Dung lượng dự kiến theo tỷ lệ lỗi và kích thước payload.
- Số partition và replication factor phù hợp.
- ACL chỉ cho service/operator có trách nhiệm đọc hoặc replay.
- Chính sách encryption và xử lý dữ liệu cá nhân.
- Quy trình archive hoặc xóa record sau khi case đóng.
- Owner chịu trách nhiệm DLT backlog.

Nếu DeadLetterPublishingRecoverer gửi record sang cùng partition number của topic nguồn, DLT cần có số partition tương ứng. Nếu DLT ít partition hơn, publish có thể thất bại với partition không hợp lệ. Nếu dùng destination resolver tập trung, cần đánh giá liệu một partition có chịu nổi lượng record lỗi hay không.

DLT cũng cần được giám sát như topic production: under-replicated partitions, disk usage, bytes in/out và consumer lag.

## 15. Metadata DLT có thể bị lặp khi record được chuyển tiếp nhiều lần

Một record có thể qua nhiều tầng retry hoặc DLT. Khi đó headers có thể chứa nhiều giá trị cùng tên hoặc thông tin exception từ các lần xử lý trước.

Không nên giả định header đầu tiên hoặc cuối cùng luôn đại diện cho toàn bộ lịch sử. Hãy:

- Đọc tất cả header trùng tên khi cần audit.
- Ghi lại metadata của lần DLT hiện tại cùng metadata nguồn trước đó.
- Dùng DLT topic/partition/offset làm định danh duy nhất cho từng bản ghi DLT.
- Dùng original topic/partition/offset để liên kết với record nguồn.
- Ghi replay ID cho mỗi lần replay.
- Tránh log stack trace hoặc payload nhạy cảm không cần thiết.

Nếu dùng Spring Kafka header mapper, kiểm tra cách mapper chuyển đổi byte[] và header lặp. Nếu đọc ConsumerRecord trực tiếp, ứng dụng có thể duyệt Kafka Headers mà không phụ thuộc Spring MessageHeaders.

## 16. Kiểm thử đọc và xử lý DLT

Nên kiểm thử với broker thật trong EmbeddedKafka hoặc Testcontainers, vì unit test thuần không xác minh được serialization, header và offset thực tế.

| Kịch bản | Điều cần xác minh |
|---|---|
| Đọc DLT record | Listener nhận đúng key, value và headers. |
| Raw bytes | Payload lỗi deserialize được giữ nguyên byte sequence. |
| Original metadata | Đọc đúng topic, partition, offset nguồn. |
| Exception headers | Có exception class/message phù hợp. |
| Mixed payload | DLT consumer đọc được cả raw bytes và JSON bytes. |
| Persist envelope | DLT record được lưu bền vững và chống trùng. |
| Persist failure | Offset DLT không được xác nhận nhầm khi lưu thất bại. |
| Replay raw | Key/value bytes được gửi lại mà không serialize hai lần. |
| Replay typed | Event được deserialize và serialize theo contract đã xác minh. |
| Ordering | Replay cũ không làm aggregate lùi version hoặc đảo trạng thái. |
| Idempotency | Replay không lặp side effect. |
| DLT retention/ACL | Consumer và operator có quyền đúng, record được giữ theo chính sách. |

Khi test original offset, hãy phân biệt offset nguồn nằm trong header với offset của DLT record. Dùng AdminClient để kiểm tra committed offset của DLT group và chờ bằng Awaitility/latch có timeout, không dùng `Thread.sleep` cố định.

## 17. Quan sát và runbook cho DLT

Các chỉ số vận hành nên có:

- Số record được publish vào DLT theo source topic và exception class.
- DLT consumer lag và backlog theo partition.
- Số record đang NEW, INVESTIGATING, READY_TO_REPLAY và RESOLVED trong kho quarantine.
- Thời gian trung bình từ lúc vào DLT đến lúc xử lý.
- Số replay thành công/thất bại.
- Số lần replay của cùng event ID.
- Số lỗi khi publish DLT hoặc khi đọc DLT.
- Dung lượng topic, retention và under-replicated partitions.

Runbook nên trả lời:

1. Ai là owner của DLT?
2. Khi nào cần dừng replay?
3. Cách tra cứu record bằng source topic/partition/offset?
4. Cách lấy raw bytes mà không ghi dữ liệu nhạy cảm ra log?
5. Ai phê duyệt replay có side effect?
6. Cách thử một record trước khi replay hàng loạt?
7. Cách kiểm soát tốc độ replay?
8. Cách đánh dấu record đã xử lý hoặc từ chối?
9. Khi nào cần giữ record để điều tra lâu hơn?
10. Cách đóng case và lưu audit trail?

Không tự động replay mọi record vừa xuất hiện trong DLT. Một đợt lỗi schema hoặc lỗi nghiệp vụ có thể tạo ra hàng nghìn record; replay trước khi sửa nguyên nhân chỉ làm DLT và topic chính lặp lại cùng lỗi.

## 18. Bài tập tổng hợp: xây dựng DLT review và replay

Hãy xây dựng luồng xử lý cho topic `orders.created` và DLT `orders.created.DLT`.

Yêu cầu:

1. Tạo DLT consumer với group ID `orders-dlt-review`.
2. Dùng ByteArrayDeserializer cho key và value để giữ raw payload.
3. Đọc DLT topic, partition, offset và original topic/partition/offset.
4. Đọc exception class/message và correlation ID nếu có.
5. Lưu DltEnvelope vào kho quarantine với unique key.
6. Phân loại record lỗi JSON, schema, database và business validation.
7. Tạo trạng thái case để operator biết record đang điều tra hay sẵn sàng replay.
8. Replay raw bytes cho một record lỗi deserialize sau khi sửa consumer.
9. Replay typed event cho một record lỗi nghiệp vụ sau khi xác minh trạng thái.
10. Tạo replay ID và lưu audit trail.
11. Giữ key và các application headers cần thiết; bỏ header exception cũ khỏi record mới.
12. Kiểm tra partition count và quyết định có giữ original partition hay dùng partitioner.
13. Dùng eventId/version để chống xử lý trùng và cập nhật cũ.
14. Thử lỗi khi persist envelope và xác minh offset DLT chưa commit nhầm.
15. Đo lag, backlog, replay throughput và thời gian xử lý.
16. Viết runbook và chính sách retention/ACL cho DLT.

Bài tập hoàn thành khi operator có thể tìm một record lỗi, xác định nguồn gốc và nguyên nhân, lưu bằng chứng, sửa nguyên nhân, replay có kiểm soát và xác minh kết quả nghiệp vụ mà không làm mất dữ liệu hoặc lặp side effect.

## 19. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. DLT model | Dead-letter record và metadata | Phân biệt record DLT với record nguồn. |
| 2. DLT consumer | Group ID và listener container | Đọc được DLT bằng consumer group riêng. |
| 3. Raw payload | ByteArrayDeserializer | Giữ được payload chưa deserialize. |
| 4. Metadata | Original topic/partition/offset và exception headers | Truy ra được nguồn và lỗi. |
| 5. Quarantine | Persist và case lifecycle | Lưu bền vững, chống trùng và có owner. |
| 6. Replay | Raw/typed publish | Gửi lại đúng contract và metadata cần thiết. |
| 7. Ordering | Partition, sequence và aggregate version | Không giả định replay khôi phục offset/thứ tự cũ. |
| 8. Reliability | Commit và idempotency | Không mất record khi lưu thất bại, không lặp side effect. |
| 9. Operations | Retention, ACL, monitoring, runbook | Quản lý backlog DLT an toàn. |
| 10. Testing | EmbeddedKafka/Testcontainers | Kiểm tra raw bytes, headers, offset và replay. |

Bài học hoàn thành khi bạn có thể đọc dead-letter record bằng consumer riêng, giữ nguyên raw payload, giải mã metadata nguồn, phân loại nguyên nhân và thực hiện recovery có kiểm soát. DLT chỉ hữu ích khi record có thể được điều tra, có owner và có quy trình replay an toàn.

Dead-letter record là bằng chứng về một lần xử lý thất bại. Hãy bảo toàn dữ liệu gốc, phân biệt metadata của DLT với metadata nguồn, sửa nguyên nhân trước khi replay và luôn kiểm tra idempotency cùng thứ tự nghiệp vụ.

