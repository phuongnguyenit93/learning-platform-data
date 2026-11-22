# Poison pill message

Trong Kafka, **poison pill message** là một record khiến consumer liên tục thất bại mỗi khi đọc hoặc xử lý. Lỗi có thể nằm ở byte payload không thể deserialize, schema không tương thích, kiểu dữ liệu sai, hoặc một điều kiện nghiệp vụ mà record hiện tại không bao giờ thỏa mãn. Nếu không có chính sách xử lý rõ ràng, consumer có thể mắc kẹt ở cùng offset, lặp lỗi, tăng consumer lag và không xử lý được các record phía sau partition.

Trong chủ đề **Deserialization và schema**, poison pill đặc biệt nguy hiểm vì lỗi có thể xảy ra **trong Consumer.poll(), trước khi phương thức @KafkaListener nhận được record**. Khi đó, việc thêm try/catch quanh logic trong listener không xử lý được nguyên nhân. Spring Kafka cung cấp **ErrorHandlingDeserializer** để đóng gói lỗi deserialization, đưa thông tin lỗi cho listener container và phối hợp với **DefaultErrorHandler** cùng **DeadLetterPublishingRecoverer** để phục hồi record.

Mục tiêu không phải là “bỏ qua cho hết lỗi” mà là **ngăn một record không hợp lệ làm ngừng cả partition, giữ được dữ liệu để điều tra và chỉ cho offset tiến lên theo chính sách phục hồi đã chọn**.

## 1. Poison pill khác record lỗi thông thường như thế nào?

Một record có thể thất bại một lần vì database vừa mất kết nối hoặc HTTP API tạm thời trả về 503. Đây thường là lỗi transient: retry có backoff có thể thành công.

Poison pill thường có đặc điểm khác:

- Cùng record, cùng payload và cùng cấu hình luôn tạo cùng một lỗi.
- Retry không thay đổi nguyên nhân, do đó không giúp record thành công.
- Consumer có thể luôn quay lại cùng topic/partition/offset.
- Record phía sau partition bị trì hoãn hoặc không được xử lý.
- Nếu consumer restart hoặc rebalance, lỗi tiếp tục xuất hiện ở offset đó.

Ví dụ producer gửi:

~~~json
{
  "orderId": "O-202",
  "amount": "not-a-number",
  "currency": "VND"
}
~~~

Trong khi consumer chờ **amount** kiểu decimal. Nếu deserializer hoặc converter không thể chuyển chuỗi này thành số, mọi lần poll lại record cũ với cùng schema đều có thể thất bại.

Không phải mọi record bị retry nhiều lần đều là poison pill. Một dependency có thể ngừng hoạt động lâu, rồi phục hồi; khi đó cùng record sẽ thành công. Cần dựa trên root cause, dữ liệu, schema và thời gian phục hồi để phân loại.

## 2. Poison pill có thể xuất hiện ở những tầng nào?

| Tầng | Ví dụ | Lỗi xuất hiện ở đâu? | Cách xử lý phù hợp |
|---|---|---|---|
| Kafka key deserializer | Key không đúng encoding hoặc kiểu | Trong poll() | ErrorHandlingDeserializer cho key |
| Kafka value deserializer | JSON hỏng, Avro/Protobuf không tương thích | Trong poll() | ErrorHandlingDeserializer cho value |
| Schema Registry / schema resolution | Không tìm được schema ID, registry lỗi | Trong quá trình deserialize | Phân biệt lỗi transient và schema sai thực sự |
| Spring message conversion | Payload byte hợp lệ nhưng không chuyển được sang argument | Sau poll, trước hoặc khi gọi listener | Error handler với classification phù hợp |
| Listener business validation | Trạng thái, field hoặc invariant không hợp lệ | Trong @KafkaListener | Ném domain exception, recover DLT |
| Side effect | Database/API từ chối dữ liệu | Trong service gọi từ listener | Phân loại transient/permanent, idempotency |

Điểm phân biệt quan trọng: **lỗi trong Kafka Deserializer thường xảy ra trước khi listener được gọi**. Một annotation retry trên listener hoặc một try/catch trong listener không tự giải quyết được mọi lỗi tại poll boundary.

## 3. Điều gì xảy ra nếu consumer không xử lý được deserialization?

Một Kafka consumer thông thường thực hiện:

~~~text
Broker trả record bytes
       |
       v
KafkaConsumer.poll()
       |
       +-- KeyDeserializer.deserialize()
       |
       +-- ValueDeserializer.deserialize()
       |
       v
ConsumerRecords<K,V>
       |
       v
Spring Kafka container gọi @KafkaListener
~~~

Nếu deserializer ném exception, poll có thể không tạo ra một ConsumerRecord<K,V> đã deserialize thành công để giao cho listener. Kafka client có thể trả về **RecordDeserializationException** hoặc **SerializationException** bao quanh lỗi gốc, tùy phiên bản và ngữ cảnh.

Một failure loop thường thấy:

~~~text
Topic orders, partition 0, offset 52
          |
          v
poll() đọc bytes của offset 52
          |
          v
Deserializer ném lỗi
          |
          v
Listener chưa được gọi
          |
          v
Consumer không tiến lên theo cách mong muốn
          |
          v
poll() hoặc quá trình xử lý tiếp tục gặp offset 52
~~~

Một error handler chỉ biết xử lý exception sau khi listener đã nhận record có thể không có đủ record metadata/payload để chuyển DLT. Với Spring Kafka, một đường giải quyết tiêu chuẩn là đặt **ErrorHandlingDeserializer** ở key/value deserializer để biến lỗi poll-time thành dữ liệu lỗi mà container xử lý được.

## 4. ErrorHandlingDeserializer giải quyết ranh giới poll như thế nào?

**ErrorHandlingDeserializer** của Spring Kafka bọc một deserializer thực tế, gọi là delegate. Nếu delegate deserialize thành công, giá trị được trả như bình thường. Nếu delegate ném exception, ErrorHandlingDeserializer ghi nhận lỗi vào record headers và trả giá trị phù hợp cho container theo cơ chế của framework.

Khái niệm:

~~~text
KafkaConsumer.poll()
        |
        v
ErrorHandlingDeserializer
        |
        +-- delegate deserialize thành công
        |             |
        |             v
        |         Record bình thường
        |
        +-- delegate ném exception
                      |
                      v
             Header chứa thông tin lỗi
                      |
                      v
             Spring Kafka container
                      |
                      v
               DefaultErrorHandler
                      |
                      v
               Recoverer / DLT
~~~

Container có thể nhận diện thông tin lỗi deserialization từ header trước khi gọi listener. Nếu có lỗi, container đưa record qua error handler, thường bỏ qua việc gọi listener với một object không hợp lệ. Khi cấu hình đúng, recoverer có thể gửi original raw bytes sang DLT để điều tra và replay.

**Không nên tự parse header lỗi bằng một cách không kiểm soát hoặc phụ thuộc tên header tự đặt.** Spring Kafka có các header và tiện ích nội bộ với semantics theo phiên bản; sử dụng API do framework cung cấp sẽ ít rủi ro hơn khi nâng cấp.

## 5. Cấu hình ErrorHandlingDeserializer trong Spring Boot

Ví dụ topic chứa key chuỗi và value JSON của OrderEvent:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
~~~

Ở đây:

- Kafka consumer dùng ErrorHandlingDeserializer cho cả **key** và **value**.
- StringDeserializer là delegate để chuyển key bytes thành String.
- JsonDeserializer là delegate để chuyển value bytes thành OrderEvent.
- Default type và trusted packages là ví dụ; cần cấu hình theo producer contract và mức tin cậy dữ liệu thực tế.
- Auto commit tắt để Spring Kafka listener container điều khiển offset theo AckMode.

Nếu producer dùng Avro, Protobuf hoặc định dạng có Schema Registry, delegate cần là deserializer tương ứng của định dạng đó; không dùng JsonDeserializer nếu bytes không phải JSON.

### 5.1. Vì sao phải bọc cả key?

Nếu chỉ bọc value nhưng key deserializer ném exception, consumer vẫn có thể kẹt tại poll(). Trong nhiều ứng dụng, key là String và ít lỗi hơn value, nhưng key vẫn có thể sai encoding, version hoặc bị producer gửi sai serializer.

Không nên giả định key an toàn chỉ vì topic thường chứa key hợp lệ. Bọc cả hai khi cần một cơ chế phục hồi nhất quán cho dữ liệu đầu vào không tin cậy.

### 5.2. Giá trị null không mặc định là poison pill

Kafka hỗ trợ record có value null, thường gọi là **tombstone**, đặc biệt với compacted topics. Value null hợp lệ không giống deserialization failure.

Nếu ứng dụng dùng compacted topic, listener và deserializer cần xử lý tombstone đúng contract. Không chuyển mọi value null sang DLT mà không kiểm tra có header lỗi deserialization hay đó là tombstone hợp lệ.

## 6. Recovery bằng DefaultErrorHandler và DeadLetterPublishingRecoverer

Với record listener non-transactional, **DefaultErrorHandler** chịu trách nhiệm retry và recovery. **DeadLetterPublishingRecoverer** có thể publish record không thể xử lý sang DLT.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(dltTemplate);
    recoverer.setFailIfSendResultIsError(true);
    return recoverer;
}

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
        InvalidOrderEventException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

Ví dụ dùng ba lần blocking retry với delay 1 giây cho các exception được phép retry. Các domain exception permanent được đánh dấu non-retryable để đưa tới recovery nhanh hơn.

**DeserializationException**, **MessageConversionException** và một số lỗi định dạng khác thường nằm trong danh sách fatal/non-retryable mặc định của DefaultErrorHandler ở các phiên bản Spring Kafka hiện đại. Danh sách và API chính xác cần xem theo phiên bản đang chạy; không giả định một config chung áp dụng cho mọi version.

Đặt **setFailIfSendResultIsError(true)** giúp tránh coi recovery đã thành công trong khi producer DLT báo lỗi. Nếu DLT publish thất bại, recovery phải được báo thất bại để giữ cơ hội redelivery theo cấu hình, thay vì âm thầm commit offset.

### 6.1. Gắn error handler vào container factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    factory.getContainerProperties()
           .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
~~~

Listener sử dụng factory tương ứng:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "order-projection",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderEvent event) {
    projectionService.apply(event);
}
~~~

Nếu record bị lỗi deserialize và ErrorHandlingDeserializer đã ghi nhận header lỗi, listener thường không được gọi để xử lý một object không hợp lệ. Error handler nhận record và có thể định tuyến DLT.

Các đoạn code là cấu trúc minh họa; ứng dụng cần thêm imports phù hợp, bean producer/consumer factory, domain classes, KafkaTemplate và topic DLT. Đảm bảo bean error handler thực tế được sử dụng bởi container, không chỉ được khai báo trong Spring context.

## 7. DLT phải lưu được raw bytes của poison pill

Khi deserialization thất bại, object OrderEvent không tồn tại. Dữ liệu duy nhất có thể dùng để sửa lỗi có thể là **original bytes** của record.

ErrorHandlingDeserializer và DeadLetterPublishingRecoverer trong các phiên bản Spring Kafka phù hợp có thể chuyển raw bytes từ record lỗi sang DLT. Nhưng KafkaTemplate dùng để publish DLT phải có serializer hiểu được kiểu dữ liệu này.

Ví dụ:

~~~text
Topic gốc: value bytes hỏng
         |
         v
ErrorHandlingDeserializer không tạo được OrderEvent
         |
         v
DeadLetterPublishingRecoverer tạo record DLT
         |
         v
Value trong DLT có thể là byte[]
         |
         v
Producer serializer chỉ hỗ trợ JSON object?
         |
         +-- Có -> Có thể báo SerializationException
         |
         +-- Hỗ trợ byte[] -> Có thể giữ nguyên raw payload
~~~

Một hướng cấu hình là **DelegatingByTypeSerializer**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();
serializers.put(byte[].class, new ByteArraySerializer());
serializers.put(OrderEvent.class, new JsonSerializer<OrderEvent>());

DelegatingByTypeSerializer valueSerializer =
    new DelegatingByTypeSerializer(serializers, true);
~~~

Ví dụ chọn ByteArraySerializer cho raw byte[] và JsonSerializer cho OrderEvent. Cần cấu hình **key serializer** tương ứng nếu key cũng có thể bị lỗi deserialize và trở thành byte[] khi đi vào DLT. Không thể dùng chung một serializer cho mọi kiểu mà không kiểm tra kiểu dữ liệu thật.

Lưu cả metadata nguồn: original topic, partition, offset, timestamp, exception class và schema version nếu xác định được. Raw payload có thể chứa dữ liệu nhạy cảm; áp dụng ACL, retention, encryption và quy trình truy cập phù hợp cho DLT.

## 8. Schema mismatch tạo poison pill như thế nào?

Một record có thể hợp lệ với producer nhưng không tương thích với consumer hiện tại.

Các tình huống:

- Producer thay kiểu trường, ví dụ số thành chuỗi.
- Producer đổi tên hoặc xóa trường mà consumer yêu cầu.
- Consumer cũ không hỗ trợ enum value mới.
- Producer sử dụng schema version mới nhưng consumer chưa được cập nhật.
- Schema ID trong payload không được registry nhận diện.
- Deserializer bị cấu hình sai subject naming strategy hoặc registry endpoint.
- Dữ liệu từ một serializer khác được đưa nhầm vào topic.

Ví dụ consumer trông đợi:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "O-100",
  "amount": 125000
}
~~~

Nhưng producer gửi:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "O-100",
  "amount": {"value": 125000, "currency": "VND"}
}
~~~

Nếu consumer vẫn kỳ vọng amount là number, Jackson hoặc converter có thể thất bại. Retry cùng bytes không làm schema tự tương thích trở lại.

Hướng phòng ngừa:

1. Đặt schema contract rõ ràng và quản lý version.
2. Kiểm tra compatibility khi thay đổi schema.
3. Dùng consumer tolerant với thay đổi tương thích có chủ đích.
4. Thử nghiệm producer/consumer với schema cũ và mới trước rollout.
5. Ghi nhận event schema version hoặc schema ID để điều tra.
6. Có quy trình nâng cấp consumer trước hoặc cùng với producer tùy dạng thay đổi.

Một lỗi schema thật sự thường nên được đưa tới DLT hoặc quy trình chờ sửa contract thay vì retry blocking vô hạn.

## 9. Schema Registry outage không nhất thiết là poison pill permanent

Khi dùng Avro/Protobuf hoặc các serializer tích hợp Schema Registry, consumer có thể cần registry để tra cứu schema ID và deserialize record.

Hai sự cố khác nhau:

**Schema ID không tồn tại hoặc payload hỏng:** cùng bytes thường sẽ không thể giải mã dù registry khỏe. Đây có thể là poison pill permanent.

**Registry đang mất kết nối hoặc tạm thời quá tải:** record có thể hợp lệ, nhưng deserializer chưa tải được schema. Nếu registry phục hồi, retry có thể thành công.

Vì vậy, không nên đưa mọi exception từ deserializer sang DLT ngay mà không phân biệt root cause. Nếu library bọc lỗi registry timeout trong một DeserializationException, classification mặc định của Spring Kafka có thể xem lỗi đó là fatal. Có thể cần chính sách riêng ở tầng registry/client hoặc error handler để cho phép retry có giới hạn, tùy phiên bản và cách lỗi được chuyển tiếp.

Đặt timeout hữu hạn cho registry client, quan sát registry availability và cấu hình cache schema phù hợp. Không retry vô hạn trên consumer thread nếu registry không phục hồi trong thời gian dài.

## 10. Poison pill ở listener không giống lỗi poll-time

Không phải poison pill nào cũng nằm ở deserializer. Một event có thể deserialize thành object hoàn toàn hợp lệ nhưng vi phạm một quy tắc nghiệp vụ.

Ví dụ:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    if (event.totalAmount().signum() < 0) {
        throw new InvalidOrderEventException(
            "Order amount must not be negative"
        );
    }
    projectionService.apply(event);
}
~~~

Trong trường hợp này, listener đã được gọi nên DefaultErrorHandler có thể nhận exception của listener trực tiếp. Không cần ErrorHandlingDeserializer để bắt lỗi validation này, nhưng vẫn nên dùng nếu nguồn dữ liệu có thể sai bytes.

Nên phân biệt:

| Lỗi | Listener có được gọi? | Hướng xử lý |
|---|---|---|
| JSON syntax hỏng ngay trong deserializer | Thường không | ErrorHandlingDeserializer + container error handler |
| Không tải được schema ID | Có thể không | Phân loại registry/transient vs schema permanent |
| Spring message converter thất bại | Có thể chưa vào method | Error handler và converter/classification |
| Business validation exception | Có | Domain exception + error handler/DLT |
| Database timeout | Có | Retry có backoff, kiểm soát timeout |

Việc xác định đúng boundary giúp tránh sửa listener khi lỗi thật nằm trong poll hoặc cấu hình serialization.

## 11. Vì sao retry vô hạn thường làm poison pill nguy hiểm hơn?

Nếu một record không thể parse, dùng **FixedBackOff.UNLIMITED_ATTEMPTS** hoặc non-blocking retry không giới hạn có thể làm cùng payload được xử lý lại mãi mà không có điều kiện kết thúc.

Hậu quả:

- Consumer lag theo partition tăng.
- Một partition không tiến triển qua record hỏng.
- Retry log và metric tăng mạnh.
- Container có thể dành tài nguyên cho lỗi không thể tự hết.
- Với backoff blocking dài, consumer có thể gặp vấn đề max.poll.interval.ms tùy cơ chế xử lý.
- Nếu retry topic được dùng, backlog chuyển sang retry topic mà chưa giải quyết nguyên nhân.

Phân loại lỗi permanent, đặt retry budget hữu hạn cho lỗi có thể phục hồi và đưa poison pill vào DLT là hướng dễ vận hành hơn.

Không nên dựa vào việc restart consumer hoặc tăng số consumer để sửa poison pill. Một partition tại một thời điểm chỉ thuộc về một consumer trong cùng group; member mới có thể gặp lại cùng lỗi tại offset đó.

## 12. Offset commit và sự an toàn dữ liệu

Poison pill thường xuất hiện với delivery semantics at-least-once. Khi listener không xử lý được record, cần quyết định lúc nào offset nguồn được phép tiến lên.

| Trạng thái | Điều đã hoàn tất | Hành động offset |
|---|---|---|
| Listener xử lý thành công | Nghiệp vụ hoàn tất | Commit theo AckMode |
| Poison pill được xác nhận lưu bền vững tại DLT | Recovery hoàn tất theo policy | Offset có thể tiến lên theo cơ chế recovery |
| DLT publish thất bại | Chưa có recovery an toàn | Không cố ý đánh dấu đã recover |
| DLT send timeout, kết quả chưa rõ | Có thể broker đã ghi hoặc chưa | Giữ khả năng replay, chống duplicate |
| DLT publish thành công nhưng commit offset nguồn lỗi | DLT có record; group chưa ghi nhận tiến độ | Record nguồn có thể được đọc lại |

Không được tự commit offset chỉ để consumer lag giảm nếu poison pill chưa được xử lý hoặc lưu ở nơi phục hồi bền vững.

Một sai lầm:

~~~java
try {
    // Cố parse/validate record
    process(event);
} catch (Exception ex) {
    log.error("Invalid event", ex);
    // Nuốt lỗi rồi trả về bình thường
}
~~~

Nếu listener nuốt exception rồi trả về thành công, container có thể commit offset theo AckMode, dù record chưa được xử lý và không được lưu ở DLT. Hãy để exception đến error handler hoặc tự triển khai một recovery protocol bảo đảm durability.

## 13. DLT publish cũng có thể thất bại

Ngay khi đã cấu hình ErrorHandlingDeserializer, DLT vẫn là một Kafka producer flow và có thể thất bại do:

- DLT topic không tồn tại.
- Topic có ít partition hơn destination resolver yêu cầu.
- KafkaTemplate DLT thiếu Write ACL.
- Serializer không hỗ trợ raw bytes hoặc key type.
- Payload quá lớn hoặc header lỗi làm request vượt giới hạn.
- Broker/ISR không ổn định.
- Producer delivery timeout hoặc lỗi network.

Với các phiên bản có API tương ứng, **DeadLetterPublishingRecoverer.setFailIfSendResultIsError(true)** giúp recoverer báo lỗi nếu kết quả gửi DLT không thành công. Chỉ gửi bất đồng bộ rồi trả về ngay có thể khiến error handler xem recovery thành công quá sớm.

Nếu DLT publish thành công nhưng commit offset nguồn thất bại, record nguồn có thể được giao lại và DLT nhận duplicate. Thiết kế DLT consumer cần chống duplicate theo event ID hoặc original topic/partition/offset.

## 14. DLT chứa những gì để có thể điều tra?

Một poison pill cần được lưu kèm thông tin nguồn và nguyên nhân:

- Original topic, partition và offset.
- Key và raw value bytes hoặc payload có khả năng khôi phục.
- Timestamp nguồn.
- Exception class, root cause và thông tin vị trí lỗi nếu có.
- Schema ID/version và producer application version nếu xác định được.
- Correlation ID và event ID/business key.
- Thời điểm phát hiện, consumer group và application build.
- Retry/recovery metadata nếu có.

DLT không nhất thiết cần chứa mọi exception stack trace trong header nếu header quá lớn hoặc tiết lộ dữ liệu nhạy cảm. Có thể lưu một thông báo lỗi đã làm sạch và correlation ID trỏ tới log/trace.

Một record ở DLT là **record chưa hoàn tất nghiệp vụ**; việc nó có mặt trong DLT chỉ cho biết pipeline đã có một đường phục hồi. Cần có owner xử lý, alert và quy trình replay.

## 15. Replay sau khi sửa schema hoặc dữ liệu

Sau khi sửa producer schema, consumer deserializer hoặc dữ liệu lỗi, cần replay poison pill có kiểm soát.

Quy trình gợi ý:

1. Xác nhận root cause đã được sửa; nếu không, replay sẽ tạo poison pill lần nữa.
2. Đọc DLT record và giữ original metadata.
3. Xác định có thể replay nguyên raw bytes hay phải chuyển đổi payload sang schema hợp lệ.
4. Đặt event ID/idempotency key ổn định qua lần replay.
5. Chọn topic đích, key và partitioning phù hợp với ordering nghiệp vụ.
6. Publish replay record và chờ producer xác nhận.
7. Quan sát consumer xử lý và side effect hoàn tất.
8. Ghi nhận trạng thái replay để tránh phát lại nhiều lần.

Không tự động publish mọi DLT record trở lại topic gốc theo vòng lặp. Nếu payload không được sửa, record lại thất bại và tạo thêm DLT record.

Một record lỗi có thể đã được ứng dụng xử lý một phần trước khi ném exception, ví dụ gọi API thành công rồi fail commit. Vì vậy, replay cần **idempotency** ngay cả khi payload đã được sửa.

### 15.1. Ordering sau replay

Record replay có thể xuất hiện sau các record mới hơn cùng key. Nếu nghiệp vụ yêu cầu thứ tự event, cần thiết kế aggregate version, sequence number hoặc state machine để từ chối cập nhật đến muộn và phục hồi theo quy trình riêng.

Không coi DLT replay là tái chèn record chính xác tại offset cũ; Kafka không hỗ trợ ghi lại một record mới vào offset trước đó của partition.

## 16. Chống duplicate khi phục hồi

Một cách phổ biến là **consumer inbox** hoặc bảng processed_events sử dụng event ID duy nhất:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong một database transaction, consumer cố ghi event ID rồi cập nhật nghiệp vụ:

- Nếu event ID chưa tồn tại, ghi nhận và áp dụng side effect.
- Nếu event ID đã tồn tại, không áp dụng side effect lần thứ hai.
- Nếu transaction thất bại, rollback cả dấu processed và cập nhật nghiệp vụ.

Chỉ SELECT kiểm tra event ID trước khi update không đủ để tránh race condition khi hai consumer cùng xử lý một event. Dùng unique constraint và transaction.

Với HTTP API, truyền idempotency key ổn định nếu API hỗ trợ; nếu kết quả call chưa rõ do timeout, tra cứu trạng thái trước khi thử lại request gây side effect.

**Producer idempotence** của Kafka không tự xử lý duplicate ở tầng consumer business logic hoặc DLT replay. Đây là hai phạm vi khác nhau.

## 17. Poison pill trong batch listener và transaction

### 17.1. Batch listener

Với batch listener, một lần poll có thể chứa nhiều record. Nếu một record poison nằm giữa batch, lỗi của nó ảnh hưởng cách recover và commit cả batch theo cấu hình.

Spring Kafka có cơ chế xử lý batch failures và **BatchListenerFailedException** để chỉ ra record lỗi trong các trường hợp phù hợp. Tuy nhiên, lỗi deserialization xảy ra tại poll boundary khác với lỗi listener đã nhận batch object. Cần cấu hình ErrorHandlingDeserializer và xem các header lỗi có được batch listener xử lý đúng hay không.

Không tự động skip cả batch vì một record hỏng nếu dữ liệu khác vẫn có giá trị. Cũng không commit cả batch trước khi xác định policy cho record lỗi.

### 17.2. Transactional listener

Với Kafka transaction do listener container quản lý, exception có thể làm transaction abort và record được đọc lại. **DefaultAfterRollbackProcessor** thường là thành phần phục hồi sau rollback.

Không giả định cấu hình DefaultErrorHandler cho non-transactional listener sẽ tự áp dụng nguyên trạng với transactional listener. Cần kiểm tra:

- Offset nguồn được đưa vào transaction nào?
- DLT publish có nằm trong recovery transaction đúng yêu cầu không?
- Nếu transaction abort, record có được giao lại không?
- Side effect ngoài Kafka (database/HTTP) có được bảo vệ bằng idempotency không?

Kafka transaction bảo đảm trong phạm vi Kafka được cấu hình, không tự rollback mọi hệ thống bên ngoài.

## 18. Những sai lầm hay gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Chỉ bắt exception trong @KafkaListener | Không bắt được deserialization failure trước listener | Bọc delegate bằng ErrorHandlingDeserializer |
| Chỉ dùng ErrorHandlingDeserializer cho value | Poison key vẫn có thể làm poll thất bại | Cấu hình cả key khi cần |
| Retry mọi DeserializationException vô hạn | Poison pill chặn partition và lag tăng | Phân loại permanent, DLT nhanh |
| Xem null value luôn là lỗi | Tombstone hợp lệ bị gửi DLT | Phân biệt tombstone và header deserialization error |
| DLT KafkaTemplate chỉ dùng JSON serializer | Raw byte[] không publish được | Dùng serializer xử lý cả object và bytes |
| Coi gửi DLT thành công ngay sau KafkaTemplate.send() | Future có thể lỗi sau đó; offset đã tiến | Xác nhận send result và xử lý recovery failure |
| Commit offset trước khi DLT được lưu | Silent loss của record lỗi | Commit theo recovery policy an toàn |
| Reset offset để bỏ record | Có thể bỏ qua nhiều record chưa xử lý | Ưu tiên DLT/recovery, chỉ reset có kiểm soát |
| Tăng consumer concurrency để chữa poison pill | Partition lỗi vẫn giao cho một member | Sửa dữ liệu/serializer và policy |
| Replay DLT không giữ event ID | Duplicate side effect | Dùng idempotency key ổn định |
| Không theo dõi Schema Registry | Nhầm outage registry với payload permanent | Phân loại root cause và metrics registry |
| Không bảo vệ payload DLT | Rò rỉ dữ liệu nhạy cảm | ACL, retention, mã hóa và hạn chế log |

## 19. Quan sát và cảnh báo

Consumer lag cao là triệu chứng, không phải bằng chứng chắc chắn có poison pill. Cần xem cùng lỗi deserialize và tiến độ từng partition.

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Deserialization failure count | Payload/key nào không giải mã được? |
| Exception theo root cause | Lỗi JSON, schema, registry hay conversion? |
| Topic/partition/offset bị lặp | Consumer có kẹt cùng vị trí? |
| Consumer lag theo partition | Partition nào không tiến triển? |
| Retry count và duration | Record đã thất bại bao lâu? |
| DLT publish attempts/success/failures | Recovery có lưu record được không? |
| DLT lag và oldest record age | Record lỗi tồn đọng bao lâu? |
| Rebalance count | Lỗi/poll delay có gây churn group không? |
| Schema Registry error rate/latency | Registry đang outage hay contract sai? |
| Processing success rate sau replay | Lỗi đã được khắc phục thật chưa? |

Log nên chứa topic, partition, offset, exception class, root cause, schema version, consumer group và correlation ID. Không log nguyên raw bytes nếu chứa dữ liệu nhạy cảm; có thể log checksum và lưu payload tại DLT được phân quyền.

Alert hữu ích:

- Cùng offset thất bại nhiều lần trong một khoảng thời gian.
- Lỗi deserialize tăng đột biến sau deploy producer/consumer.
- DLT publish failure lớn hơn 0 kéo dài.
- Oldest DLT record age vượt SLO.
- Lag tăng chỉ ở một partition trong khi các partition khác vẫn tiến triển.

## 20. Runbook xử lý poison pill

### Bước 1: Xác định loại lỗi

Đọc exception gốc: phát sinh trong poll/deserializer, message converter hay listener business logic? Đừng chỉ nhìn dòng exception wrapper cuối cùng.

### Bước 2: Xác định vị trí record

Ghi topic, partition, offset, key identifier và thời điểm xuất hiện. Kiểm tra consumer group có đang lặp lại cùng offset hay đã chuyển record sang DLT.

### Bước 3: Kiểm tra schema và raw payload

Xác định producer serializer, consumer delegate deserializer, schema ID/version, nội dung bytes và khả năng tương thích. Với Registry, xác định registry đang lỗi tạm thời hay schema ID thật sự không tồn tại.

### Bước 4: Kiểm tra ErrorHandlingDeserializer

Đảm bảo cả key/value cần thiết đều được bọc; delegate class đúng; container dùng đúng consumer factory; header lỗi được error handler xử lý.

### Bước 5: Xác minh DLT

Kiểm tra topic, partition, ACL, serializer cho raw bytes, kết quả producer send và độ bền publish. Nếu DLT chưa lưu được, không đánh dấu record đã recover.

### Bước 6: Chọn hành động an toàn

- Nếu lỗi permanent: DLT và sửa payload/schema.
- Nếu Registry hoặc dependency tạm lỗi: retry có backoff và giới hạn.
- Nếu cấu hình sai: sửa consumer/producer trước khi resume.
- Nếu side effect chưa rõ: đối soát theo event ID để tránh duplicate.

### Bước 7: Phục hồi và xác nhận

Sau khi sửa lỗi, replay có kiểm soát. Xác minh consumer xử lý thành công, offset tiến lên hợp lệ, lag giảm, DLT backlog được quản lý và không có side effect lặp.

## 21. Checklist trước production

1. Producer và consumer đã thống nhất format, encoding và schema evolution rules chưa?
2. Deserializer có thể gặp byte không hợp lệ từ bên ngoài không?
3. ErrorHandlingDeserializer đã được gắn ở key và value cần thiết chưa?
4. Lỗi parse trong poll có được chuyển cho container error handler không?
5. DefaultErrorHandler phân loại deserialization/permanent exception phù hợp chưa?
6. DLT KafkaTemplate có serializer xử lý được original raw bytes không?
7. DLT topic có tồn tại, đủ partition, ACL, replication và retention phù hợp không?
8. Recoverer có báo lỗi nếu producer DLT publish thất bại không?
9. Offset nguồn chỉ tiến khi xử lý hoặc recovery thành công theo policy chưa?
10. Có metric phát hiện cùng offset bị lỗi lặp và DLT publish failures không?
11. Có quy trình xác định lỗi schema permanent hay Registry outage transient không?
12. DLT replay có giữ event ID và bảo đảm idempotency không?
13. Có quy trình sửa/replay mà không phá ordering nghiệp vụ không?
14. Dữ liệu lỗi trong DLT và log đã được bảo vệ phù hợp chưa?
15. Các tình huống tombstone, key lỗi, value lỗi, batch listener và transactional listener đã được đánh giá chưa?

**Kết luận:** Poison pill message không chỉ là một exception được ném nhiều lần. Đó là một record có thể phá vỡ khả năng tiến triển của partition, đặc biệt khi deserialization thất bại ngay trong poll(). Với Spring Kafka, kết hợp ErrorHandlingDeserializer, exception classification, DefaultErrorHandler, DLT đáng tin cậy và idempotent replay tạo ra một lối thoát an toàn: record lỗi được giữ lại để điều tra thay vì bị bỏ qua, còn consumer có thể tiếp tục xử lý dữ liệu hợp lệ theo chính sách vận hành rõ ràng.
