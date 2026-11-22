# DeserializationException trong header

## 1. Tổng quan

Trong Spring Kafka, producer gửi key và value tới broker dưới dạng byte. Khi consumer đọc record, Kafka client phải dùng deserializer để chuyển các byte đó thành đối tượng Java trước khi chuyển dữ liệu tới listener.

Nếu producer gửi JSON không hợp lệ, thay đổi schema không tương thích hoặc consumer cấu hình sai class/type mapping, delegate deserializer có thể ném exception ngay trong lời gọi poll. Lỗi này xảy ra **trước khi phương thức @KafkaListener được gọi**, nên một try/catch nằm bên trong listener không thể tự xử lý.

**ErrorHandlingDeserializer** giải quyết khó khăn đó bằng cách bọc deserializer thật. Khi delegate thất bại, wrapper ghi thông tin **DeserializationException dưới dạng bytes trong Kafka record header**, đồng thời cung cấp giá trị fallback như null. Spring Kafka container và error handler nhờ vậy có thông tin cần thiết để retry, recover hoặc chuyển record lỗi sang dead-letter topic (DLT).

~~~text
Producer
   |
   | key bytes + value bytes
   v
Kafka topic
   |
   v
KafkaConsumer.poll()
   |
   v
ErrorHandlingDeserializer
   |
   +-- delegate deserialize thành công --> Java value --> listener
   |
   +-- delegate ném exception
             |
             +--> tạo DeserializationException
             +--> ghi serialized exception vào header
             +--> trả null / fallback
             |
             v
       ConsumerRecord mang error header
             |
             v
       Spring Kafka error handling
~~~

Bài học tập trung vào ý nghĩa header lỗi, cách phát hiện đúng ở record listener và batch listener, cấu hình ErrorHandlingDeserializer, cách giữ dữ liệu thô khi publish DLT và các lưu ý reliability liên quan tới schema.

## 2. Vì sao cần đặt DeserializationException vào header?

Nếu dùng JsonDeserializer trực tiếp và payload bị lỗi, KafkaConsumer có thể ném exception khi poll, trước khi tạo ra record Java mà listener có thể tiếp nhận. Khi không có cơ chế hỗ trợ, một record không đọc được có thể khiến consumer mắc kẹt tại vị trí đó và liên tục gặp cùng lỗi.

Đưa thông tin vào header cho phép client giữ được bối cảnh của record lỗi:

1. **Vị trí:** topic, partition và offset của record vẫn có thể được xác định.
2. **Đầu vào gốc:** bytes lỗi được lưu trong DeserializationException để phục vụ recovery.
3. **Nguồn lỗi:** biết lỗi thuộc key hay value.
4. **Nguyên nhân:** exception gốc được giữ làm cause.
5. **Chính sách:** error handler có thể quyết định retry, skip có ghi nhận hoặc DLT.
6. **Không đánh đồng record lỗi với null hợp lệ:** listener có thể dựa vào header chứ không chỉ payload.

Điều quan trọng là header ở đây **không phải một exception Java object gắn trực tiếp vào Kafka record**. Kafka header chứa byte array. Spring Kafka serialize DeserializationException vào mảng byte và dùng công cụ tương ứng để đọc lại.

### 2.1. Thông tin trong DeserializationException

Tùy phiên bản Spring Kafka, DeserializationException có thể cung cấp các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| Raw data | Byte gốc của key hoặc value không deserialize được |
| Cause | Exception từ deserializer delegate hoặc validator |
| isKey | Lỗi xảy ra ở key hay ở value |
| Message | Thông điệp mô tả lỗi |
| Stack trace | Ngữ cảnh lỗi phục vụ chẩn đoán |

Raw data có thể là dữ liệu nhạy cảm như email, số điện thoại, địa chỉ hoặc thông tin đơn hàng. Không log hoặc gửi tùy tiện dữ liệu này vào metric, alert hoặc hệ thống log có phạm vi truy cập rộng.

### 2.2. Header được tạo tại consumer, không phải sửa record trên broker

ErrorHandlingDeserializer thêm header khi consumer deserialize record. Việc đó **không có nghĩa record gốc lưu trên Kafka broker được sửa lại**.

Nếu dùng một raw Kafka consumer khác không cấu hình ErrorHandlingDeserializer, công cụ đó có thể không nhìn thấy header nội bộ mà Spring Kafka consumer tạo ra trong quá trình đọc. Đây là điểm quan trọng khi so sánh output giữa ứng dụng và công cụ console consumer.

## 3. Tên header cho lỗi key và value

Spring Kafka phân biệt hai trường hợp:

| Header nội bộ thường gặp | Ý nghĩa |
|---|---|
| springDeserializerExceptionKey | Key deserializer thất bại |
| springDeserializerExceptionValue | Value deserializer thất bại |

Khi viết code, nên dùng hằng số do Spring Kafka cung cấp thay vì lặp tên chuỗi khắp ứng dụng:

~~~java
SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER
SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
~~~

Trong các phiên bản Spring Kafka phù hợp, những hằng số này thuộc package **org.springframework.kafka.support.serializer**. Nếu API của phiên bản đang chạy khác ví dụ, hãy đối chiếu JavaDoc của dependency thực tế và sử dụng hằng số tương ứng.

Đừng coi tên header này là hợp đồng sự kiện mà producer phải gửi. Đây là metadata xử lý lỗi ở phía consumer.

### 3.1. Lỗi key và lỗi value có tác động khác nhau

**Lỗi value:** consumer không thể tạo payload Java hợp lệ để xử lý nghiệp vụ. Thường cần DLT với raw bytes hoặc thay đổi serializer/schema tương thích.

**Lỗi key:** ứng dụng không thể khôi phục key Java. Nếu key quyết định entity ID, ordering hoặc deduplication, việc thay key lỗi bằng một giá trị mặc định có thể làm sai nghiệp vụ.

Ví dụ:

~~~text
Record A:
  topic=orders.created
  partition=1
  offset=130
  key=order-17
  value=null
  header=springDeserializerExceptionValue

Record B:
  topic=orders.created
  partition=1
  offset=131
  key=null
  value=OrderCreated(...)
  header=springDeserializerExceptionKey
~~~

Hai record cần được phân loại riêng. Không mặc định mọi DeserializationException đều là lỗi value.

## 4. So sánh authentication, schema và deserialization

Không phải mọi exception trong consumer đều liên quan tới payload:

| Lỗi | Xảy ra ở đâu? | Biểu hiện thường gặp |
|---|---|---|
| Authentication failure | Kết nối tới broker | Client không xác thực được |
| Authorization failure | Broker kiểm tra quyền | Topic/group operation bị từ chối |
| Deserialization failure | Deserializer trong consumer poll | Không chuyển được bytes thành Java object |
| Message conversion failure | Spring converter sau poll | Value đã deserialize nhưng không chuyển được sang kiểu listener yêu cầu |
| Business processing failure | Trong listener/service | DB, HTTP, validation nghiệp vụ |

**DeserializationException header** là tín hiệu của lỗi ở tầng deserializer, thường chỉ có khi consumer sử dụng ErrorHandlingDeserializer hoặc cơ chế tương đương đã được cấu hình.

Đừng dùng lỗi authorization hoặc network để kết luận producer đã gửi schema sai. Trước hết, xác định đúng tầng phát sinh exception.

## 5. Cấu hình ErrorHandlingDeserializer với Spring Boot

Giả sử topic **orders.created** có key String, value là JSON ứng với Java class **OrderCreated**. Có thể cấu hình như sau:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-reader
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.events.OrderCreated
        "[spring.json.use.type.headers]": false
        "[spring.json.trusted.packages]": com.example.orders.events
    listener:
      ack-mode: batch
~~~

Ý nghĩa:

- **key-deserializer / value-deserializer:** Spring Kafka wrapper bắt lỗi delegate.
- **spring.deserializer.key.delegate.class:** deserializer thật cho key.
- **spring.deserializer.value.delegate.class:** deserializer thật cho value.
- **spring.json.value.default.type:** class Java dùng khi không lấy kiểu từ type header.
- **spring.json.use.type.headers=false:** ví dụ chọn không dùng Spring JSON type headers cho type resolution.
- **spring.json.trusted.packages:** phạm vi package được phép deserialize thành class.

Package **com.example.orders.events** trong ví dụ phải được thay bằng class thực tế. Nếu hệ thống dùng type headers, Schema Registry, Avro hoặc Protobuf, delegate configuration sẽ khác; không áp dụng máy móc JSON type mapping.

### 5.1. Có cần bọc cả key và value?

Có thể chỉ bọc value nếu cần xử lý lỗi payload. Tuy nhiên, key cũng có thể hỏng do thay đổi định dạng, encoding hoặc schema. Bọc cả key và value giúp nhận diện lỗi hai phía.

| Cấu hình | Header lỗi được wrapper tạo |
|---|---|
| Chỉ bọc key | Key failure header |
| Chỉ bọc value | Value failure header |
| Bọc cả hai | Tương ứng với phía deserializer gặp lỗi |

Đây không phải cơ chế tự sửa dữ liệu. Wrapper chỉ cho phép lỗi đi tới recovery path một cách có kiểm soát.

### 5.2. Vì sao cần kiểm tra trusted packages?

JsonDeserializer có chính sách type trust để hạn chế những class được tạo từ dữ liệu type metadata. Không mở tất cả package bằng wildcard chỉ vì consumer đang gặp lỗi, đặc biệt khi topic có producer không hoàn toàn tin cậy.

Cần xác định producer có gửi type header không, consumer có sử dụng type header không và Java DTO có tương thích schema thực tế không.

## 6. Cấu hình bằng ConsumerFactory

Với ứng dụng chủ động tạo ConsumerFactory, có thể bọc delegate bằng code:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Bean
public ConsumerFactory<String, OrderCreated> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-reader");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    var keyDeserializer =
        new ErrorHandlingDeserializer<>(new StringDeserializer());

    var valueDeserializer =
        new ErrorHandlingDeserializer<>(
            new JsonDeserializer<>(OrderCreated.class, false)
        );

    return new DefaultKafkaConsumerFactory<>(
        props,
        keyDeserializer,
        valueDeserializer
    );
}
~~~

Đây là ví dụ minh họa cách bọc delegate; ứng dụng còn phải có class OrderCreated, cấu hình security và thiết lập JSON type/trust tương thích với phiên bản đang chạy.

Nếu Spring Boot đã auto-configure factory, hãy ưu tiên application.yml để giảm nguy cơ hai factory có cấu hình không nhất quán. Nếu tự tạo factory, bảo đảm @KafkaListener thực sự sử dụng factory này.

## 7. Điều gì xảy ra khi delegate deserialize thất bại?

Một dòng xử lý điển hình:

1. KafkaConsumer nhận key bytes, value bytes và headers.
2. ErrorHandlingDeserializer gọi delegate.
3. Delegate ném exception.
4. Wrapper tạo DeserializationException chứa raw bytes và cause.
5. Wrapper thêm serialized exception vào header tương ứng.
6. Wrapper trả null hoặc fallback value nếu có cấu hình.
7. Spring Kafka container nhận ConsumerRecord với error header.
8. Container hoặc batch listener xác định recovery path.

~~~text
Input value bytes: {invalid-json
          |
          v
      JsonDeserializer
          |
          X  JSON parsing exception
          |
          v
  ErrorHandlingDeserializer
          |
          +-- exception cause
          +-- raw data bytes
          +-- isKey=false
          |
          v
ConsumerRecord(
  key="order-1",
  value=null,
  headers=[springDeserializerExceptionValue=...]
)
~~~

Đừng dùng **new String(header.value(), UTF_8)** để tìm nội dung thông báo lỗi: header value là serialized exception bytes, không phải một chuỗi UTF-8 thông thường.

## 8. Khác biệt giữa record listener và batch listener

### 8.1. Record listener

Với record listener, Spring Kafka container có thể kiểm tra header lỗi do ErrorHandlingDeserializer tạo và chuyển record thất bại tới CommonErrorHandler thay vì gọi listener như thể đã có payload hợp lệ.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "orders-reader"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

Một malformed JSON có thể được xử lý bởi DefaultErrorHandler và recoverer đã cấu hình. Listener không cần một try/catch để bắt lỗi xảy ra trước khi nó được gọi.

Cơ chế kiểm tra header cụ thể thay đổi theo phiên bản, nên cần xác nhận behavior thực tế trong môi trường triển khai.

### 8.2. Batch listener

Với batch listener, một batch có thể chứa cả record hợp lệ và record không deserialize được:

~~~text
index 0: valid OrderCreated
index 1: valid OrderCreated
index 2: value=null + error header
index 3: valid OrderCreated
~~~

Ở các cấu hình Spring Kafka batch listener phổ biến, ứng dụng cần kiểm tra error header của từng record. Nếu gặp header lỗi, listener nên thông báo index thất bại cho DefaultErrorHandler qua **BatchListenerFailedException**.

Nếu chỉ nhìn payload null, listener có thể nhầm deserialization failure với Kafka tombstone hợp lệ. Nếu chỉ ném exception chung, handler không biết record nào lỗi và có thể retry toàn batch.

## 9. Phát hiện header trong batch listener

Ví dụ listener nhận ConsumerRecord để giữ metadata:

~~~java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.kafka.support.serializer.SerializationUtils;

@KafkaListener(
    topics = "orders.created",
    groupId = "orders-reader",
    containerFactory = "ordersBatchContainerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        var record = records.get(index);

        Header keyFailure = record.headers().lastHeader(
            SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER
        );

        Header valueFailure = record.headers().lastHeader(
            SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
        );

        if (keyFailure != null || valueFailure != null) {
            throw new BatchListenerFailedException(
                "Record cannot be deserialized",
                new IllegalArgumentException(
                    keyFailure != null
                        ? "Key deserialization failed"
                        : "Value deserialization failed"
                ),
                index
            );
        }

        orderService.process(record.value());
    }
}
~~~

Ví dụ này kiểm tra sự tồn tại của header lỗi và chuyển index tới handler. Cause tạo trong ví dụ chỉ mô tả lỗi; nguyên nhân gốc vẫn được lưu trong header. Để đọc cause gốc, hãy sử dụng API tiện ích của Spring Kafka phù hợp với version.

### 9.1. Index không phải offset

| Dữ liệu | Ví dụ | failedIndex |
|---|---|---|
| Vị trí danh sách | records.get(2) | 2 |
| Kafka offset | record.offset() = 94 | Không dùng 94 |
| Partition | record.partition() = 4 | Không dùng 4 |
| Event ID | order-94 | Không dùng event ID |

Một poll có thể chứa record từ nhiều partition. Handler phải tính tiến độ offset cho từng partition, không dùng một offset chung cho toàn batch.

### 9.2. Không chỉ kiểm tra value == null

Value null có thể là:

- Tombstone hợp lệ trên compacted topic.
- Kết quả của ErrorHandlingDeserializer khi value deserialize thất bại.
- Một fallback được cấu hình bởi failed-deserialization function.

Header giúp phân biệt các trường hợp. Nếu topic cho phép tombstone, listener cần định nghĩa rõ cách xử lý null value không có error header.

## 10. Cách đọc DeserializationException từ header

Error header mang serialized exception. Khi muốn đọc raw data, isKey, message hoặc cause, nên dùng utility chính thức của Spring Kafka, thay vì tự giải mã bằng ObjectInputStream từ bytes không được kiểm soát.

Một số phiên bản cung cấp phương thức hỗ trợ chuyển exception header trở lại DeserializationException trong **ListenerUtils**. Signature cụ thể cần được xác định theo JavaDoc của dependency thực tế.

Luồng logic:

~~~text
header = record.headers().lastHeader(
    SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
)

nếu header có mặt:
    exception = Spring Kafka utility chuyển header thành exception
    originalBytes = exception.getData()
    originalCause = exception.getCause()
    failedOnKey = exception.isKey()

    classify, observe, recover
~~~

Đây là pseudocode mô tả cách đọc chứ không phải snippet Java biên dịch trực tiếp.

Không tự viết logic deserialize Java object tùy ý cho headers nhận từ nguồn không đáng tin cậy. Ngoài rủi ro bảo mật, cách tự giải mã còn dễ hỏng khi thay đổi thư viện.

### 10.1. An toàn thông tin khi log

Chỉ log những metadata cần điều tra:

- Topic, partition, offset.
- Key failure hay value failure.
- Exception/cause class.
- Raw byte length.
- Schema ID hoặc event type nếu có metadata hợp lệ.
- Correlation ID không nhạy cảm, nếu có.

Tránh log raw payload mặc định vì record lỗi có thể chứa PII hoặc thông tin bí mật dù không parse được. Với dữ liệu nhạy cảm, DLT cũng cần encryption, ACL và retention thích hợp.

## 11. DefaultErrorHandler xử lý deserialization failure

**DefaultErrorHandler** quyết định retry và recovery khi record xử lý thất bại. Với lỗi deserialize, cần phân biệt hai loại cause:

| Cause | Retry có thể hữu ích? |
|---|---|
| JSON syntax hỏng | Thường không; bytes không tự sửa |
| Schema không tương thích | Thường cần sửa producer/consumer |
| Schema registry timeout | Có thể hữu ích sau khi dependency phục hồi |
| Registry thiếu quyền | Cần sửa credential/quyền |
| Dữ liệu sai wire format | Thường không |
| Custom validator tạm thời phụ thuộc service | Tùy policy của ứng dụng |

Một cấu hình DefaultErrorHandler có recoverer:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Ví dụ dùng FixedBackOff 1 giây giữa các lần retry và hai lượt retry sau lần đầu. Trong thực tế, lỗi schema deterministic thường nên recovery sớm để không giữ consumer liên tục thử một payload không thể xử lý.

### 11.1. BatchListenerFailedException giúp tránh retry cả batch

Nếu batch listener biết record lỗi ở index 2, DefaultErrorHandler có thể xử lý phần thành công trước lỗi và redeliver phần còn lại theo policy.

~~~text
Batch: [R0, R1, R2, R3]
        OK  OK  X   ?

BatchListenerFailedException(index=2)
              |
              v
       DefaultErrorHandler
              |
        retry/recover R2
        và xử lý phần còn lại
~~~

Nếu listener ném exception chung mà không có failed index, fallback batch retry có thể khiến cả batch được xử lý lại, kể cả các record đã hoàn tất side effect.

Để an toàn, side effect nghiệp vụ vẫn cần idempotency vì crash có thể xảy ra sau DB commit nhưng trước Kafka offset commit.

## 12. Cấu hình batch factory với error handler

Ví dụ một factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersBatchContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler ordersErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(ordersErrorHandler);

    return factory;
}
~~~

Một cấu hình Spring Boot tương ứng cho consumer:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-reader
      enable-auto-commit: false
      max-poll-records: 100
    listener:
      type: batch
      ack-mode: batch
~~~

Nếu ứng dụng dùng factory custom, property Boot ở listener không đảm bảo tự được áp dụng hết vào factory đó. Hãy cấu hình factory một cách chủ đích và bảo đảm @KafkaListener trỏ đúng tên factory.

## 13. DLT phải giữ được raw bytes

Khi deserialization thất bại, value trong ConsumerRecord có thể là null nhưng DeserializationException có raw byte data. **DeadLetterPublishingRecoverer** trong Spring Kafka có khả năng khôi phục bytes của record lỗi khi gửi DLT theo behavior được hỗ trợ.

Điểm cần chú ý: DLT publisher có thể nhận:

- Java object bình thường với record hợp lệ nhưng lỗi nghiệp vụ.
- Byte array từ payload không deserialize được.
- Null key hoặc key bytes gốc khi key deserialize thất bại.

Do đó một KafkaTemplate chỉ dùng JsonSerializer cho OrderCreated có thể không đáp ứng đầy đủ yêu cầu DLT nếu recoverer cần publish raw byte[].

Ví dụ lựa chọn serializer theo runtime type:

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();

delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(OrderCreated.class, new JsonSerializer<>());

var valueSerializer = new DelegatingByTypeSerializer(
    delegates,
    true
);
~~~

Đoạn mã minh họa cách chọn serializer value; ứng dụng còn phải cấu hình key serializer, producer factory, KafkaTemplate và security tương ứng. Nếu DLT có thêm nhiều loại event, cần khai báo các type hợp lệ hoặc một chính sách serializer rõ ràng.

### 13.1. DLT header có thể thay đổi

Recoverer có thể thêm metadata nguồn và thông tin exception vào DLT record. Header nội bộ chứa serialized DeserializationException có thể được bỏ hoặc biến đổi trong quá trình publish DLT, tùy phiên bản/cấu hình.

Không thiết kế consumer DLT dựa trên giả định header nội bộ trên ConsumerRecord ban đầu luôn còn nguyên. Hãy coi hợp đồng DLT là raw payload, source topic/partition/offset và thông tin lỗi mà recovery thực tế cam kết cung cấp.

### 13.2. Tránh recovery giả

Một số nguyên nhân DLT publish thất bại:

- Topic DLT chưa tồn tại.
- DLT partition mapping không phù hợp.
- Producer thiếu quyền WRITE.
- Serializer không xử lý được byte[].
- Broker hoặc network không khả dụng.
- Delivery timeout.

Nếu DLT publish thất bại, không được coi record đã recover chỉ vì code gọi publish. Handler cần xử lý kết quả publish đúng và giữ cơ hội redelivery theo policy.

## 14. Lỗi conversion khác lỗi deserialization

Trong Spring Kafka có thể có hai bước chuyển kiểu:

1. Kafka deserializer chuyển bytes thành String, Json object hoặc một kiểu Java khác.
2. Spring message converter chuyển value đã deserialize thành kiểu tham số mà listener yêu cầu.

Ví dụ Kafka StringDeserializer đọc JSON thành String thành công, nhưng message converter không chuyển được String đó thành OrderCreated. Đây là **message conversion failure**, không phải lỗi Kafka deserializer.

Với batch listener dùng message converter, có thể có metadata riêng về conversion failures, chẳng hạn **KafkaHeaders.CONVERSION_FAILURES** trong các phiên bản hỗ trợ.

| Tầng lỗi | Tín hiệu điển hình |
|---|---|
| Kafka deserializer | DeserializationException header khi dùng ErrorHandlingDeserializer |
| Spring message converter | ConversionException / conversion failures metadata |
| Business listener | Domain exception hoặc dependency exception |

Không cố tìm deserializer exception header khi lỗi thật sự phát sinh trong message converter hoặc service nghiệp vụ.

## 15. Schema evolution và khả năng tương thích

Một nguyên nhân phổ biến của DeserializationException là producer đổi schema nhưng consumer chưa tương thích.

Ví dụ payload cũ:

~~~json
{"orderId":"o-101","total":125.5}
~~~

Payload mới:

~~~json
{"orderId":"o-101","total":{"currency":"USD","amount":125.5}}
~~~

Consumer cũ đang mong total là number có thể thất bại khi gặp object. Retry cùng bytes bằng cùng model không giúp ích.

Quản lý schema nên bao gồm:

- Quy tắc backward/forward compatibility.
- Thứ tự deploy producer và consumer.
- Field nullable, default value và yêu cầu bắt buộc.
- Kiểu dữ liệu, enum, rename và deprecation.
- Type headers và quy tắc mapping Java class.
- Schema registry khi dùng Avro, Protobuf hoặc JSON Schema.
- Test contract trong pipeline release.
- Kế hoạch replay record đã ghi theo schema cũ/mới.

Header lỗi là một bằng chứng giúp phân loại incompatibility; nó không thay thế quản trị schema.

### 15.1. Registry timeout khác malformed payload

Nếu dùng Schema Registry, exception có thể xuất phát từ registry timeout, unknown schema ID, authorization error hoặc wire format sai.

| Nguyên nhân | Hướng xử lý |
|---|---|
| Registry tạm thời không khả dụng | Retry/backoff giới hạn và quan sát registry |
| Schema ID sai hoặc không tồn tại | Xem producer/registry config, kiểm tra ID |
| Consumer model không tương thích | Sửa model/schema, rollout theo kế hoạch |
| Sai wire format | Xác định producer và serializer thực tế |
| Registry authorization failure | Sửa credential, ACL của registry |
| Registry endpoint trỏ nhầm cluster | Điều chỉnh endpoint/configuration |

Hãy đọc cause gốc trước khi quyết định retry hay DLT. Hai record đều có DeserializationException nhưng nguyên nhân và khả năng phục hồi có thể khác nhau.

## 16. FailedDeserializationFunction và fallback

ErrorHandlingDeserializer có thể hỗ trợ một **failed-deserialization function** để trả object thay thế khi delegate thất bại. Tính năng này hữu ích khi muốn đưa dữ liệu lỗi tới một luồng xử lý đặc biệt.

Tuy nhiên, nếu listener nhận fallback object và coi nó là OrderCreated bình thường, hệ thống có thể commit record chưa được xử lý đúng.

Khi dùng fallback:

1. Định nghĩa rõ kiểu dữ liệu fallback.
2. Giữ metadata lỗi và raw bytes cần thiết.
3. Kiểm tra header trước khi xử lý nghiệp vụ.
4. Phân biệt fallback với DTO hợp lệ.
5. Quyết định recovery và offset commit minh bạch.
6. Thử trường hợp fallback không tạo được hoặc cũng thất bại.

Một custom validator tại tầng ErrorHandlingDeserializer cũng có thể khiến record bị đánh dấu lỗi khi không đáp ứng quy tắc validation mà wrapper hỗ trợ. Cần phân biệt lỗi syntax/schema với lỗi validation nghiệp vụ.

## 17. Tombstone và null value

Trong compacted topic, producer có thể gửi tombstone với value null để biểu diễn việc xóa key. Tombstone là record hợp lệ, không phải lỗi.

~~~text
Tombstone:
  key=customer-81
  value=null
  deserialization error header: absent

Malformed value:
  key=customer-81
  value=null
  deserialization error header: present
~~~

Nếu listener kiểm tra mỗi value null rồi ném exception, tombstone có thể bị chuyển nhầm sang DLT và consumer không áp dụng được hành vi xóa.

Vì vậy, khi một record có value null, hãy kiểm tra xem có DeserializationException value header không, sau đó mới áp dụng nghiệp vụ cho tombstone hoặc fallback.

## 18. Offset commit và recovery

Kafka lưu offset kế tiếp mà consumer group cần đọc. Khi record lỗi chưa được xử lý hoặc recover thành công, đừng cố tình commit vượt qua record đó nếu nghiệp vụ không cho phép skip.

Ví dụ:

~~~text
Partition 0:
  offset 10 -> processed OK
  offset 11 -> deserialization failure
  offset 12 -> chưa xử lý
~~~

Nếu không có recovery hợp lệ cho offset 11, commit 13 có thể khiến group tiếp tục sau record lỗi khi restart. Đây không chỉ là lỗi metrics; nó có thể làm mất cơ hội xử lý dữ liệu.

Các tình huống cần phân biệt:

- Recovery/DLT thành công và policy cho phép skip: handler có thể tiến offset.
- DLT publish thất bại: giữ khả năng retry/recovery.
- JVM crash trước commit: record có thể được giao lại.
- Listener nuốt lỗi và trả về bình thường: container có thể commit nhầm như thành công.

Nếu record hợp lệ đã tạo side effect trước khi gặp record lỗi, cần idempotency vì record đã xử lý vẫn có thể được giao lại sau crash hoặc rebalance.

## 19. Test malformed message có kiểm soát

Một thử nghiệm hữu ích là gửi value bytes không phải JSON hợp lệ qua producer dùng ByteArraySerializer:

~~~java
byte[] malformed = "{not-valid-json".getBytes(
    StandardCharsets.UTF_8
);

rawTemplate.send(
    "orders.created",
    "order-bad-1",
    malformed
);
~~~

Trong thử nghiệm, consumer phải được cấu hình ErrorHandlingDeserializer bọc JsonDeserializer. Kết quả cần quan sát:

1. Event JSON hợp lệ vẫn xử lý được.
2. Event malformed tạo DeserializationException value header.
3. Record listener hoặc batch listener đi qua error handler phù hợp.
4. Batch listener xác định được failed index.
5. DLT nhận dữ liệu lỗi và metadata.
6. Raw bytes được bảo toàn theo chính sách DLT.
7. Offset commit không bỏ qua record nếu recovery thất bại.
8. Event hợp lệ phía sau còn được xử lý khi recovery hoàn tất.
9. Lỗi key deserializer cũng được nhận diện.
10. Tombstone null hợp lệ không bị coi là malformed record.

Nếu dùng Schema Registry, bổ sung test registry timeout, missing schema ID và authorization failure. Không dùng dữ liệu sản xuất có PII để thử lỗi nếu chưa có biện pháp bảo vệ dữ liệu.

## 20. Metrics và log vận hành

Các chỉ số nên theo dõi:

| Tín hiệu | Mục đích |
|---|---|
| Deserialization failure count/rate | Phát hiện tăng lỗi dữ liệu theo topic |
| Key vs value failure | Phân biệt loại lỗi |
| Exception class | Nhận diện parser, schema hoặc registry failure |
| DLT publish success/failure | Xác nhận recovery |
| DLT backlog | Lượng record chờ điều tra/replay |
| Consumer lag by partition | Partition có bị kẹt tại record lỗi không |
| Event freshness | Event hợp lệ sau record lỗi có bị chậm không |
| Schema version distribution | Phát hiện producer phát schema không đồng nhất |

Log có thể có cấu trúc:

~~~text
listener=orders-reader
topic=orders.created
partition=4
offset=28012
stage=deserialization
part=value
cause=JsonMappingException
rawSizeBytes=241
action=published-to-dlt
~~~

Không dùng raw payload, event ID hoặc offset làm metric label cardinality cao. Offset có thể xuất hiện trong log để hỗ trợ điều tra từng record, nhưng không nên biến mỗi offset thành một time series.

### 20.1. Alert thực tế

Có thể alert khi tỷ lệ deserialization failure tăng vượt baseline, đặc biệt nếu đi cùng consumer lag hoặc DLT ingress. Khi xảy ra cảnh báo, đối chiếu với thời điểm producer release, consumer deploy, schema registry thay đổi hoặc credential rotation.

## 21. Runbook xử lý DeserializationException trong header

1. Xác định listener type: record hay batch.
2. Ghi nhận topic, partition, offset, consumer group và client ID.
3. Xác định header key/value và exception cause.
4. Kiểm tra ErrorHandlingDeserializer và delegate thực tế được cấu hình.
5. So sánh producer format/schema với Java model của consumer.
6. Kiểm tra type headers, trusted packages và schema registry.
7. Phân loại lỗi deterministic hay transient.
8. Nếu transient, chọn retry/backoff có giới hạn.
9. Nếu deterministic, recover/DLT theo policy thay vì retry vô hạn.
10. Xác nhận DLT serializer hỗ trợ raw byte[].
11. Xác nhận DLT publish và offset commit đúng.
12. Replay có kiểm soát sau khi sửa schema, kèm idempotency.
13. Ghi lại nguyên nhân và bổ sung test contract.

Quy trình nên cho phép đội vận hành xác nhận recovery bằng dữ liệu thật, không chỉ dựa vào log cho biết phương thức recoverer đã được gọi.

## 22. Những nhầm lẫn thường gặp

**Chỉ dùng JsonDeserializer rồi mong listener bắt được lỗi.** Delegate có thể ném exception trong poll; listener chưa được gọi.

**Đọc header như UTF-8 text.** DeserializationException header là serialized bytes; dùng utility Spring Kafka phù hợp để đọc.

**Cho rằng header lỗi nằm sẵn trong Kafka log.** Wrapper ở consumer thêm header khi deserialize, không sửa record gốc trên broker.

**Dựa vào value null để nhận diện lỗi.** Tombstone cũng có value null; cần kiểm tra header.

**Quên kiểm tra key failure.** Key deserializer có thể hỏng độc lập với value.

**Dùng batch listener nhưng không kiểm tra header theo từng record.** Có thể bỏ sót malformed record hoặc retry cả batch không cần thiết.

**Truyền Kafka offset thay failed index.** BatchListenerFailedException cần index zero-based của danh sách listener.

**Tự giải mã Java object header từ nguồn không tin cậy.** Dùng API chính thức và tránh Java deserialization tùy ý.

**DLT producer không serialize được byte[].** Recoverer có thể cần publish raw bytes của record lỗi.

**Giả định DLT giữ nguyên mọi header nội bộ.** Cần xác nhận metadata contract của DLT sau recovery.

**Retry vô hạn một schema mismatch vĩnh viễn.** Retry không biến dữ liệu sai schema thành hợp lệ.

**Commit offset khi recovery chưa thành công.** Có thể khiến record không được xử lý lại.

**Log raw payload lỗi.** Malformed bytes vẫn có thể chứa thông tin nhạy cảm.

## 23. Checklist triển khai

- [ ] ErrorHandlingDeserializer được bật cho key/value cần bảo vệ.
- [ ] Delegate deserializer và type mapping được khai báo đúng.
- [ ] Consumer không auto commit độc lập với container error handling.
- [ ] Record listener có DefaultErrorHandler/recoverer thích hợp.
- [ ] Batch listener kiểm tra key/value error header từng record.
- [ ] BatchListenerFailedException nhận index zero-based chính xác.
- [ ] Tombstone null được phân biệt với deserialize failure.
- [ ] Lỗi schema deterministic không retry vô hạn.
- [ ] Lỗi registry/network transient có retry/backoff phù hợp.
- [ ] DLT serializer có thể publish raw byte[].
- [ ] DLT giữ metadata nguồn và dữ liệu cần điều tra.
- [ ] DLT publish failure không bị coi recovery success.
- [ ] Dashboard theo dõi failure rate, lag, DLT, event freshness.
- [ ] Có test malformed key, malformed value, tombstone và DLT failure.
- [ ] Có runbook xử lý schema compatibility và replay.

## 24. Ghi nhớ

**DeserializationException trong header** là cơ chế ErrorHandlingDeserializer dùng để bảo toàn thông tin lỗi chuyển đổi bytes ở phía consumer. Header chứa serialized exception, gồm dữ liệu gốc và nguyên nhân lỗi, chứ không phải chuỗi text hoặc JSON payload.

Record listener có thể được container chuyển trực tiếp sang error handler. Batch listener thường cần kiểm tra từng record, phát hiện key/value exception header và báo failed index để DefaultErrorHandler xử lý phần lỗi đúng phạm vi.

Để hệ thống bền vững, cần kết hợp đúng deserializer, schema compatibility, DLT serializer cho raw bytes, offset commit, idempotent side effect và công cụ quan sát. Recovery chỉ hoàn tất khi dữ liệu lỗi được xử lý hoặc cô lập theo policy và consumer có thể tiếp tục mà không bỏ sót nghiệp vụ.
