# Record bị lỗi trước khi vào listener trong Spring Kafka

Trong Spring Kafka, không phải mọi record lỗi đều đi tới thân hàm @KafkaListener rồi mới ném exception. Có những record thất bại **ngay trong lúc KafkaConsumer.poll() deserialize key/value**, khi Spring chuyển đổi payload sang kiểu Java mà listener yêu cầu, hoặc khi framework kiểm tra tham số trước khi gọi method. Kết quả thường thấy là **listener không được gọi**, mặc dù record vẫn tồn tại ở một topic/partition và consumer có thể liên tục gặp lại cùng offset.

Trong chương **Deserialization và schema** của Spring Kafka Reliability Operations, đây là một tình huống reliability rất quan trọng. Nếu xử lý sai, một record hỏng (poison pill) có thể giữ partition không tiến, làm consumer lag tăng, tạo vòng retry vô ích hoặc bị bỏ qua mà không có dấu vết. Nếu xử lý đúng, hệ thống có thể ghi nhận lỗi, đưa record vào dead-letter topic (DLT), rồi tiếp tục xử lý những record hợp lệ mà vẫn giữ đủ metadata để điều tra.

Bài học tập trung vào ranh giới giữa Kafka client, Spring Kafka listener container, message converter và listener method; cách sử dụng ErrorHandlingDeserializer; cách chuyển lỗi tới DefaultErrorHandler/DeadLetterPublishingRecoverer; cùng những lưu ý về schema, batch listener, offset và vận hành.

## 1. Record đi qua những tầng nào trước khi chạy @KafkaListener?

Một record Kafka đi từ byte[] trên broker tới object domain theo nhiều bước:

~~~text
Kafka broker
    |
    | topic / partition / offset / key bytes / value bytes / headers
    v
KafkaConsumer.poll()
    |
    +--> key deserializer
    |
    +--> value deserializer
    |        |
    |        +--> có thể ném SerializationException
    |
    v
ConsumerRecord<K, V>
    |
    v
Spring Kafka listener container
    |
    v
RecordMessagingMessageListenerAdapter
    |
    +--> message conversion / header mapping
    |
    +--> resolve method arguments
    |
    +--> validation nếu được cấu hình
    |
    v
@KafkaListener method
    |
    +--> business logic
~~~

Vị trí lỗi quyết định cơ chế nào có thể nhìn thấy exception và nên khôi phục bằng cách nào.

Ví dụ, cùng là JSON không hợp lệ nhưng biểu hiện khác nhau:

- Nếu JsonDeserializer trực tiếp ném exception trong poll, @KafkaListener chưa hề được gọi.
- Nếu ErrorHandlingDeserializer bọc JsonDeserializer, lỗi được gắn vào record dưới dạng thông tin exception để container có cơ sở xử lý.
- Nếu deserialize ra String thành công nhưng message converter không tạo được OrderCreated, lỗi xảy ra ở tầng conversion/argument resolution.
- Nếu method được gọi rồi domain service từ chối amount âm, đó là lỗi nghiệp vụ bên trong listener.

Không nên gộp cả bốn trường hợp vào một vòng retry duy nhất.

## 2. Các loại lỗi xuất hiện trước thân hàm listener

| Giai đoạn | Ví dụ | Listener method đã chạy chưa? | Hướng xử lý |
|---|---|---|---|
| Key deserialization | Key là bytes không phù hợp deserializer | Chưa | ErrorHandlingDeserializer cho key |
| Value deserialization | JSON sai cú pháp, Avro schema ID không hợp lệ | Chưa | ErrorHandlingDeserializer cho value |
| Type resolution | JSON type header trỏ tới class không được tin cậy | Chưa | Hạn chế type mapping và phân loại lỗi |
| Message conversion | String hoặc Map không chuyển được sang OrderCreated | Thường chưa | CommonErrorHandler và conversion policy |
| Argument resolution | Không khớp tham số method hoặc thiếu dữ liệu bắt buộc | Thường chưa | Sửa listener contract, phân loại fatal |
| Validation trước lời gọi | Constraint trên payload không đạt | Có thể chưa | DLT/quarantine nếu lỗi dữ liệu cố định |
| Business processing | Database mất kết nối sau khi method chạy | Đã chạy | Retry có giới hạn, idempotency |
| Consumer poll/network | Coordinator hoặc broker lỗi tạm thời | Chưa | Container lifecycle và consumer error handling |

Một lỗi dữ liệu cố định thường sẽ **không** biến thành hợp lệ nếu đọc lại cùng bytes vài trăm lần. Ngược lại, lỗi không liên hệ được schema registry hoặc dependency do mạng có thể là sự cố tạm thời. Cần phân loại theo nguyên nhân thực tế, không chỉ tên exception bọc ngoài.

## 3. Poison pill gây ra vòng lặp ở cùng offset như thế nào?

Giả sử partition 2 của topic orders.events có:

~~~text
offset 100: JSON hợp lệ
offset 101: bytes JSON bị cắt
offset 102: JSON hợp lệ
offset 103: JSON hợp lệ
~~~

Nếu consumer dùng JsonDeserializer trực tiếp và record 101 gây exception trong poll:

~~~text
poll() đọc đến offset 101
          |
          v
JsonDeserializer ném exception
          |
          v
Không tạo được ConsumerRecord domain hợp lệ
          |
          v
Listener không được gọi
          |
          v
Poll tiếp / khôi phục sai cách
          |
          v
Lại gặp offset 101
          |
          +--> consumer lag tăng
          +--> log lặp liên tục
          +--> record 102, 103 bị chặn
~~~

Với Kafka client, lỗi deserialization thông thường xảy ra trước khi Spring có một record đầy đủ để chuyển cho listener. Một CommonErrorHandler thông thường không thể tùy tiện coi đây là listener exception của ConsumerRecord nếu không có thông tin record phù hợp. Spring Kafka có thể ghi thông báo đề nghị cấu hình ErrorHandlingDeserializer để xử lý loại lỗi này.

Đây là lý do chỉ viết try/catch trong @KafkaListener không giải quyết được poison pill do deserialize: code ấy chưa có cơ hội chạy.

Đừng xử lý bằng cách tăng max.poll.interval.ms hoặc đổi số lần retry một cách máy móc. Cần làm cho container **nhận diện được record lỗi** và áp dụng chính sách recovery có thể tiến offset sau khi record đã được lưu hoặc xử lý an toàn.

## 4. ErrorHandlingDeserializer giải quyết vấn đề gì?

ErrorHandlingDeserializer là wrapper deserializer của Spring Kafka. Nó gọi **delegate deserializer** thực sự để biến bytes thành object Java. Nếu delegate thất bại, wrapper giữ thông tin lỗi và raw bytes trong metadata/header để container có thể phát hiện và chuyển record đến error handler.

~~~text
KafkaConsumer.poll()
          |
          v
ErrorHandlingDeserializer
          |
          +--> Delegate JsonDeserializer thành công
          |             |
          |             v
          |       ConsumerRecord<OrderCreated>
          |             |
          |             v
          |         Listener
          |
          +--> Delegate JsonDeserializer thất bại
                        |
                        v
              Ghi thông tin DeserializationException
              vào header / record metadata
                        |
                        v
              Container nhận biết lỗi
                        |
                        v
              DefaultErrorHandler / recoverer
                        |
                        v
                  DLT / recovery
~~~

Khi không cấu hình fallback function, một giá trị không deserialize được thường trở thành null ở tầng kết quả delegate, kèm header ghi lỗi. Với record listener, container có thể kiểm tra header deserialization exception **trước khi gọi listener** và chuyển lỗi cho cơ chế xử lý phù hợp.

**Đừng giả định mọi null payload đều là deserialize lỗi.** Kafka cho phép record với value null (tombstone) để biểu thị xóa key trong compacted topic. Một tombstone hợp lệ không có cùng deserialization-exception header. Cần phân biệt null hợp lệ với record lỗi bằng metadata lỗi, không chỉ bằng biểu thức value == null.

Có thể cấu hình fallback function để tạo một giá trị thay thế khi deserialize lỗi trong một số trường hợp, nhưng đây phải là quyết định nghiệp vụ có chủ đích. Không nên để fallback âm thầm biến dữ liệu hỏng thành một event “hợp lệ” giả tạo.

## 5. Cấu hình ErrorHandlingDeserializer trong Spring Boot

Với JSON key dạng String và value dạng OrderCreated:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
    listener:
      ack-mode: record
~~~

Ý nghĩa:

- key-deserializer và value-deserializer dùng wrapper để bắt lỗi của delegate.
- spring.deserializer.key.delegate.class chọn StringDeserializer.
- spring.deserializer.value.delegate.class chọn JsonDeserializer.
- spring.json.value.default.type xác định kiểu event mặc định nếu phù hợp với chiến lược type header đang dùng.
- spring.json.trusted.packages chỉ cho phép các package Java được tin cậy.
- enable-auto-commit: false để container quản lý commit offset theo acknowledgement mode.

Cấu hình tương đương bằng application.properties:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=order-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
spring.kafka.listener.ack-mode=record
~~~

Tên property cụ thể cần tương thích với Spring Boot/Spring Kafka version của ứng dụng. Nếu tự tạo ConsumerFactory, hãy cấu hình đúng deserializer wrapper và delegate tại factory đang được @KafkaListener sử dụng.

### Có cần bọc cả key và value?

Có thể chỉ bọc value nếu contract đảm bảo key luôn được giải mã an toàn. Tuy nhiên, **key cũng có thể bị hỏng**. Nếu key deserializer ném exception trực tiếp trước khi value được xử lý, consumer vẫn có thể gặp vòng lỗi poll. Bọc cả key và value giúp error handler có dữ liệu cần thiết cho cả hai loại lỗi.

Nếu dùng Avro hoặc Protobuf, delegate deserializer không nhất thiết là JsonDeserializer. Vẫn có thể dùng ErrorHandlingDeserializer bên ngoài deserializer theo wire format/schema registry thực tế, miễn delegate tương thích với Kafka Deserializer API.

## 6. Lỗi xuất hiện trước và sau deserialize khác nhau thế nào?

Giả sử topic lưu JSON:

~~~json
{"eventId":"evt-100","orderId":"O-100","amount":120}
~~~

Listener mong đợi:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-service"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

### Trường hợp A: raw bytes không parse thành JSON

~~~text
{"eventId":"evt-101","orderId":
~~~

JsonDeserializer thất bại ngay trong poll. ErrorHandlingDeserializer có thể lưu thông tin lỗi để container xử lý. Method onOrder chưa chạy.

### Trường hợp B: JSON hợp lệ nhưng kiểu dữ liệu sai

~~~json
{"eventId":"evt-102","orderId":"O-102","amount":"not-a-number"}
~~~

Nếu OrderCreated.amount là số, việc deserialize object hoặc conversion có thể thất bại, tùy deserializer và message converter đang sử dụng. Trong cả hai trường hợp, listener có thể chưa được gọi.

### Trường hợp C: JSON và kiểu hợp lệ nhưng vi phạm nghiệp vụ

~~~json
{"eventId":"evt-103","orderId":"O-103","amount":-50}
~~~

Object có thể tạo thành công. Listener hoặc validation layer mới phát hiện amount âm. Đây là lỗi domain, không phải deserialization error, và cần được phân loại bằng exception nghiệp vụ.

### Trường hợp D: payload null hợp lệ

Một tombstone mang key O-104 và value null. Nếu compacted topic dùng tombstone, consumer phải có contract rõ ràng cho null payload. Không gửi mọi null vào DLT nếu không xác định có deserialization error header.

## 7. Message conversion và method argument resolution

Không phải lúc nào deserializer cũng tạo trực tiếp object domain. Một consumer có thể deserialize value thành String hoặc byte[], sau đó Spring Kafka MessageConverter chuyển nó sang tham số mà @KafkaListener khai báo.

~~~text
Kafka byte[]
   |
   v
StringDeserializer
   |
   v
String payload
   |
   v
Spring MessageConverter
   |
   +--> convert sang OrderCreated
             |
             +--> thành công --> method được gọi
             |
             +--> lỗi -------> error handler
~~~

Ví dụ listener nhận OrderCreated nhưng factory đang dùng một RecordMessageConverter tạo object từ JSON. Nếu payload không khớp kiểu, lỗi conversion xảy ra **sau poll nhưng trước thân listener**. Lúc này, ErrorHandlingDeserializer không tự giải quyết vì delegate deserializer đã thành công.

Spring Kafka container có thể chuyển các lỗi conversion, argument resolution hoặc validation sang CommonErrorHandler. DefaultErrorHandler có thể phân loại một số loại exception như DeserializationException, MessageConversionException, ConversionException hoặc MethodArgumentResolutionException là fatal/non-retryable theo mặc định phiên bản. Khi xây policy, cần kiểm tra danh sách classifier thực tế và bổ sung exception domain được dùng trong ứng dụng.

Không để mọi exception bọc ngoài biến thành RuntimeException chung rồi retry vô hạn. Giữ nguyên cause chain để xác định lỗi nằm ở deserializer, converter hay logic nghiệp vụ.

## 8. DefaultErrorHandler và DeadLetterPublishingRecoverer

Một error handler thường dùng với record listener:

~~~java
@Configuration
public class KafkaConsumerErrorConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidEventException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        return factory;
    }
}
~~~

Trong ví dụ:

- FixedBackOff(1_000L, 2L) cho phép tối đa hai lần retry sau lần xử lý đầu tiên đối với lỗi retryable.
- InvalidEventException đại diện lỗi nghiệp vụ không nên retry cùng payload.
- DeadLetterPublishingRecoverer nhận record không phục hồi được rồi publish sang DLT.
- Factory sử dụng CommonErrorHandler được cấu hình.

Lưu ý: các lỗi deserialization thường được xem là fatal/non-retryable bởi DefaultErrorHandler trong các phiên bản Spring Kafka hiện đại, nhưng hành vi cụ thể có thể bị thay đổi bởi classifier. Một record JSON hỏng thường nên được chuyển recovery sớm; retry vài lần không sửa được bytes.

DefaultErrorHandler chỉ giải quyết đúng lỗi nếu exception có thể được container truyền đến nó. Với lỗi deserialize trong KafkaConsumer.poll(), ErrorHandlingDeserializer là cơ chế quan trọng để đưa thông tin record lỗi tới luồng error handler thay vì để poll bị lỗi liên tục.

## 9. DLT nhận payload gì khi deserialization thất bại?

Khi deserializer không tạo được OrderCreated, recoverer không thể xuất một object domain hợp lệ. Spring Kafka có thể dùng raw bytes được ErrorHandlingDeserializer lưu lại để đưa record gốc vào DLT. Vì thế, DLT producer cần xử lý được hai dạng value:

1. Object đã deserialize thành công, chẳng hạn OrderCreated, nhưng listener ném lỗi nghiệp vụ.
2. Raw byte[] của record thất bại ở tầng deserialization.

Sơ đồ:

~~~text
Record value JSON hợp lệ
       |
       v
OrderCreated object
       |
       +--> lỗi domain
                |
                v
           DLT value: OrderCreated

Record value JSON hỏng
       |
       v
ErrorHandlingDeserializer
       |
       +--> lỗi deserialize
                |
                v
           DLT value: raw byte[]
~~~

Nếu KafkaTemplate cho DLT chỉ dùng JsonSerializer dành cho object domain, nó có thể không giữ nguyên raw bytes theo cách mong muốn. Hãy cấu hình serializer lựa chọn theo loại value hoặc dùng các KafkaTemplate riêng phù hợp.

### Ví dụ ý tưởng về serializer theo loại

Với phiên bản Spring Kafka hỗ trợ DelegatingByTypeSerializer, có thể chuẩn bị map serializer cho các kiểu value:

~~~java
Map<Class<?>, Serializer<?>> serializers = new LinkedHashMap<>();

serializers.put(
        byte[].class,
        new ByteArraySerializer()
);

serializers.put(
        OrderCreated.class,
        new JsonSerializer<OrderCreated>()
);

Serializer<Object> dltValueSerializer =
        new DelegatingByTypeSerializer(serializers);
~~~

Ví dụ minh họa cách lựa chọn serializer cho byte[] và object. Khi wiring ProducerFactory/KafkaTemplate thực tế, cần dùng generic type phù hợp, serializer cho key, Kafka producer properties và xử lý thêm những payload type khác nếu topic có nhiều event class.

Nếu một DLT dùng chung cho nhiều domain, hãy bảo đảm mọi value type có serializer tương ứng. Cũng nên kiểm tra việc serialize headers và giới hạn kích thước message DLT, vì exception metadata có thể làm record tăng kích thước.

## 10. DLT topic và partition cần được chuẩn bị

DeadLetterPublishingRecoverer mặc định thường chọn tên DLT là tên topic nguồn cộng hậu tố .DLT, cùng số partition nguồn.

~~~text
orders.events / partition 0 --> orders.events.DLT / partition 0
orders.events / partition 1 --> orders.events.DLT / partition 1
orders.events / partition 2 --> orders.events.DLT / partition 2
~~~

Nếu source topic có tám partition mà DLT chỉ có ba partition, việc ép partition cao hơn số partition hiện có có thể gây lỗi gửi. Nên provision DLT với partition tương thích hoặc sử dụng destination resolver trả về partition âm (-1) để producer tự chọn partition.

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        -1
                )
        );
~~~

Partition -1 không tồn tại trên broker; ở đây nó biểu thị việc không chỉ định partition đích, để producer chọn partition theo cơ chế của Kafka client.

Nếu publish DLT thất bại vì serializer, topic, partition, ACL hoặc broker, recovery không được xem như đã hoàn tất an toàn. Hãy bảo đảm lỗi publish được báo về và không tiến offset nguồn như thể record lỗi đã lưu thành công.

## 11. ErrorHandlingDeserializer và record listener

Với record listener, lời gọi method thường nhận trực tiếp object domain:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-service",
        containerFactory = "orderListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Nếu ErrorHandlingDeserializer phát hiện lỗi value, container có thể đưa exception tới error handler **mà không gọi onOrder**. Không cần viết try/catch cho JSON parsing bên trong onOrder vì lỗi xảy ra trước đó.

Nếu method onOrder ném lỗi vì database, error handler xử lý exception đó theo chính sách retry nghiệp vụ. Hai trường hợp dùng chung error handler nhưng khác phân loại lỗi và đường khôi phục dữ liệu.

Trường hợp cần tùy biến cách log/route lỗi, hãy thực hiện ở error handler, recoverer hoặc một thành phần xử lý lỗi riêng. Không biến dữ liệu bất hợp lệ thành object domain giả chỉ để gọi method listener.

## 12. Batch listener cần xử lý lỗi deserialize cẩn thận

Batch listener nhận nhiều record trong một lần gọi. Nếu dùng ErrorHandlingDeserializer, các record có lỗi deserialize có thể được biểu diễn bằng value null hoặc fallback value kèm deserialization-exception header, tùy cách cấu hình và phiên bản.

~~~text
poll batch:
  record 0: hợp lệ
  record 1: hợp lệ
  record 2: lỗi deserialize, value có thể null
  record 3: hợp lệ
        |
        v
Batch listener
        |
        +--> phát hiện record 2 lỗi bằng header
        |
        +--> ném BatchListenerFailedException(index=2)
        |
        v
DefaultErrorHandler xử lý phần lỗi theo batch policy
~~~

Một hướng xử lý là nhận List<ConsumerRecord<...>> để có quyền truy cập đầy đủ tới headers và offset:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-batch",
        containerFactory = "batchFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record =
                records.get(index);

        // Trước khi gọi domain logic, kiểm tra record có
        // deserialization-exception header hay không.
        // Có thể dùng KafkaUtils.getExceptionFromHeader(...)
        // với SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
        // theo API Spring Kafka đang sử dụng.

        if (hasDeserializationFailure(record)) {
            throw new BatchListenerFailedException(
                    "Invalid record in batch",
                    index
            );
        }

        orderService.process(record.value());
    }
}
~~~

Hàm hasDeserializationFailure đại diện logic truy xuất deserialization-exception header qua helper phù hợp của Spring Kafka; đây là điểm mở rộng của ứng dụng. Trong triển khai thật, có thể dùng KafkaUtils.getExceptionFromHeader với header name và LogAccessor tương ứng để lấy DeserializationException mà không tự deserialize Java object từ header không tin cậy.

BatchListenerFailedException cho phép thông báo vị trí record lỗi trong batch cho error handler. Với các phiên bản Spring Kafka hỗ trợ overload nhận index, ví dụ trên diễn đạt ý định xử lý. Cần xác nhận API và batch error-handler semantics của dependency khi triển khai.

Nếu batch listener bỏ qua null payload mà không kiểm tra header, nó có thể vô tình coi record deserialize lỗi là tombstone hợp lệ. Nếu ném exception chung mà không chỉ ra record lỗi, error handler có thể phải retry cả batch, khiến các record hợp lệ trước vị trí lỗi bị xử lý lại.

### Phân biệt batch processing failure

Nếu record 2 deserialize tốt nhưng orderService.process ném exception, hãy bắt lỗi nghiệp vụ ở đúng index và dùng BatchListenerFailedException để cho handler biết record lỗi. Những record đã thành công trước đó cần idempotent vì có thể được giao lại tùy commit/recovery policy.

## 13. Schema registry và lỗi deserialize dữ liệu có schema

Với Avro hoặc Protobuf, deserializer có thể cần đọc schema ID từ record rồi liên hệ schema registry hoặc dùng cache schema để giải mã bytes. Lỗi xảy ra trước listener có thể là:

- Schema ID không tồn tại hoặc dữ liệu được mã hóa sai định dạng.
- Schema không tương thích với model được consumer mong đợi.
- Schema registry không sẵn sàng do lỗi kết nối.
- Thiếu credential/ACL với schema registry.
- Type mapping không khớp với listener signature.
- Bytes bị hỏng hoặc producer ghi sai serializer.

Cùng một exception wrapper có thể xuất phát từ nguyên nhân khác nhau. Ví dụ schema registry timeout có thể tạm thời, còn schema ID không có thật có thể là lỗi dữ liệu cố định. Phân loại cần dựa trên nguyên nhân gốc và cách delegate deserializer báo lỗi.

Một cấu hình cơ bản có thể bọc deserializer Avro bằng ErrorHandlingDeserializer tương tự JSON, thay delegate.class bằng deserializer Avro tương ứng của thư viện đang dùng. Không nên sao chép spring.json.* properties sang một delegate Avro/Protobuf không hiểu những thuộc tính đó.

Với dữ liệu có schema, cần:

1. Thiết lập schema compatibility policy phù hợp.
2. Version hóa event contract.
3. Kiểm soát schema registry availability và caching.
4. Kiểm thử producer mới với consumer đang chạy.
5. Phân biệt lỗi contract cố định với lỗi registry/network tạm thời.
6. Giữ raw bytes và metadata nếu record cần được đưa vào DLT.

Schema hợp lệ không chứng minh event hợp lệ về nghiệp vụ. Một order có amount âm vẫn có thể tuân thủ schema nhưng bị domain validation từ chối.

## 14. Type headers và an toàn deserialization

Spring Kafka JsonDeserializer có thể sử dụng type information trong Kafka headers để xác định class Java. Nếu producer gửi type header sai hoặc header bị giả mạo, deserialization có thể bị từ chối trước listener.

Các nguyên tắc an toàn:

- Giới hạn spring.json.trusted.packages tới các package event thực sự cần thiết.
- Không dùng wildcard tin cậy toàn bộ class nếu dữ liệu không hoàn toàn được kiểm soát.
- Với topic chỉ có một event type, cân nhắc cấu hình default type tường minh và không sử dụng arbitrary type headers.
- Dùng schema/type mapping allowlist cho các topic nhiều event type.
- Không deserialize Java native object từ nguồn không tin cậy.
- Không lấy class name tự do từ payload làm kiểu cần khởi tạo.
- Cấp ACL Kafka tối thiểu cho producer ghi vào topic.

Một record thất bại vì type header không được tin cậy không nên được sửa bằng cách mở trusted packages ra toàn bộ chỉ để “hết lỗi”. Điều đó có thể làm giảm an toàn hệ thống. Cần kiểm tra producer contract và source principal.

## 15. Error classification và giới hạn retry

Lỗi trước listener không đồng nghĩa mọi lỗi đều non-retryable. Cần tách các nhóm:

| Loại lỗi | Có tự phục hồi khi retry cùng bytes? | Chính sách thường phù hợp |
|---|---|---|
| JSON bị cắt/sai cú pháp | Không | DLT/quarantine |
| Schema ID không tồn tại | Thường không, cần sửa producer/registry | DLT và điều tra |
| Class/type header không được tin cậy | Không nên cho retry tùy ý | Quarantine, kiểm tra contract |
| Type conversion không phù hợp | Thường không | DLT hoặc sửa converter/contract |
| Validation cố định thất bại | Không | DLT, sửa data |
| Schema registry mất kết nối tạm thời | Có thể | Retry có giới hạn và cảnh báo |
| Database tạm mất kết nối trong listener | Có thể | Blocking/non-blocking retry có backoff |
| Lỗi lập trình cấu hình converter | Thường không tự sửa | Sửa ứng dụng, hạn chế retry |
| Tombstone hợp lệ | Không phải lỗi | Xử lý theo contract |

DefaultErrorHandler có thể dùng classifier để tránh retry lỗi dữ liệu cố định. Với lỗi đáng chờ phục hồi, đặt số lần và thời gian hữu hạn; không để một record giữ partition vô thời hạn.

Nếu lỗi xảy ra trong chính delegate deserializer vì một dependency tạm thời, hãy đánh giá khả năng thực sự retry được trước khi đưa vào DLT. Với một số hệ thống, việc tạm dừng consumer và phục hồi dependency có thể phù hợp hơn việc đẩy hàng loạt record hợp lệ vào DLT.

## 16. Offset, acknowledgement và cửa sổ duplicate

Khi record không vào listener mà được chuyển tới recoverer, hành vi offset vẫn quan trọng.

~~~text
record offset 200: hợp lệ --> listener thành công
record offset 201: JSON hỏng --> ErrorHandlingDeserializer
                                      |
                                      v
                                  DLT publish
                                      |
                                      +--> thành công
                                      |       |
                                      |       v
                                      |   container xử lý recovered
                                      |
                                      +--> thất bại
                                              |
                                              v
                                      chưa recovery an toàn
~~~

Nếu DLT publish thành công và error handler coi record đã recovered, container có thể tiến offset theo ack/error-handler policy. Nếu DLT publish thất bại, không nên commit offset nguồn như thể dữ liệu đã được lưu.

Có một cửa sổ duplicate: DLT publish thành công nhưng ứng dụng dừng trước khi commit offset nguồn. Khi consumer khác nhận partition, offset 201 có thể được đọc lại và chuyển DLT lần nữa. Vì vậy, DLT consumer và công cụ replay cần idempotency.

Nếu một listener đã thực hiện side effect database trước khi lỗi conversion/processing phát sinh ở bước khác, record có thể được giao lại. Cần dùng event ID, unique constraint hoặc inbox/processed-events table để tránh xử lý lặp.

AckMode RECORD, BATCH hay MANUAL quyết định khi nào container commit offset; chúng **không sửa được bytes JSON hỏng**. Chọn ack mode và error handler cùng nhau để xác định chính xác lúc một record lỗi được skip/recovered.

## 17. Log và metric để chẩn đoán lỗi trước listener

Khi listener method không chạy, các log bên trong method cũng không xuất hiện. Hãy quan sát ở consumer container và error handler.

Nên ghi nhận:

- Consumer group ID.
- Topic, partition và offset gốc.
- Key ở dạng đã xử lý an toàn hoặc hash.
- Exception class và error code.
- Loại lỗi: key deserialization, value deserialization, conversion hay validation.
- Producer version/schema version nếu có.
- DLT destination và kết quả publish.
- Attempt count và thời gian xử lý.
- Thời điểm lỗi đầu tiên và lần cuối.

Một log có cấu trúc:

~~~text
event_type=kafka_record_rejected
group=order-service
topic=orders.events
partition=2
offset=201
stage=value_deserialization
exception=RecordDeserializationException
action=publish_dlt
destination=orders.events.DLT
~~~

Tên exception trong log chỉ là minh họa; Spring Kafka có thể bọc lỗi dưới những class khác tùy nơi phát sinh và version.

Không log toàn bộ raw bytes, secret hoặc headers tùy ý. Payload hỏng có thể chứa dữ liệu nhạy cảm hoặc ký tự điều khiển gây log forging. Giới hạn kích thước message và sanitize những trường có thể đưa vào log.

Các tín hiệu monitoring:

| Tín hiệu | Ý nghĩa |
|---|---|
| Deserialization failure rate | Số record không giải mã được |
| Conversion failure rate | Số payload không chuyển được sang listener parameter |
| DLT publish rate | Số record lỗi được chuyển đi |
| DLT publish errors | Có record không thể lưu an toàn tại DLT |
| Consumer lag theo partition | Poison pill có giữ partition không |
| Rebalance count | Consumer có bị thay đổi assignment khi lỗi không |
| Schema registry error rate | Có phải lỗi hạ tầng registry không |
| Failed record size | Payload bất thường hoặc quá lớn |
| Exception classification | Lỗi cố định hay tạm thời |
| Oldest DLT record age | Record lỗi tồn đọng bao lâu |

Một số metric cần ứng dụng bổ sung; tên và availability của Kafka/Micrometer metrics thay đổi theo phiên bản và exporter.

## 18. Quy trình điều tra khi @KafkaListener không được gọi

Có thể dùng các bước sau để phân tích một incident:

1. **Xác nhận record tồn tại.** Xác định topic, partition, offset và consumer group.
2. **Kiểm tra log trước listener.** Tìm SerializationException, DeserializationException, MessageConversionException, type mapping hoặc schema registry errors.
3. **Xác định key hay value lỗi.** Deserializer cho key và value có thể có lỗi độc lập.
4. **Kiểm tra deserializer thực tế.** ConsumerFactory có đang dùng ErrorHandlingDeserializer hay JsonDeserializer trực tiếp?
5. **Kiểm tra delegate.** Đúng wire format JSON/Avro/Protobuf và đúng type/schema?
6. **Kiểm tra header/type mapping.** Trusted packages, default type và contract đã đồng bộ?
7. **Kiểm tra converter.** Có chuyển từ String/Map sang event class trước lời gọi listener không?
8. **Phân loại nguyên nhân.** Bytes hỏng cố định hay dependency/schema registry tạm lỗi?
9. **Kiểm tra error handler.** CommonErrorHandler có được đăng ký trên đúng listener factory không?
10. **Kiểm tra DLT.** Topic có tồn tại, serializer nhận raw bytes, ACL và partition có hợp lệ không?
11. **Xác nhận offset.** Record được recovered theo policy hay vẫn đang block partition?
12. **Theo dõi sau phục hồi.** Consumer lag và tỷ lệ deserialization errors có giảm không?

Không vội reset offset để bỏ qua poison pill. Việc skip không có DLT hoặc audit có thể làm mất sự kiện nghiệp vụ quan trọng. Chỉ can thiệp offset thủ công theo quy trình có kiểm soát, sau khi có quyết định về dữ liệu cần giữ.

## 19. Các tình huống lỗi thực tế

### Listener không chạy nhưng consumer lag tăng

Kiểm tra deserializer exception trong poll, group assignment và converter. Nếu cùng offset lỗi lặp lại, bọc deserializer bằng ErrorHandlingDeserializer và cấu hình recovery, thay vì tăng concurrency vô hạn.

### Container báo không xử lý được SerializationException trực tiếp

Đây là dấu hiệu lỗi xảy ra trước khi có ConsumerRecord mà error handler cần. Dùng ErrorHandlingDeserializer với delegate đúng định dạng để lỗi có thể được biểu diễn bằng record/header và được recover.

### Key deserialize lỗi, value vẫn hợp lệ

Nếu chỉ bọc value deserializer, lỗi key vẫn có thể ngăn poll trả record. Hãy cân nhắc bọc key và value; DLT producer cũng cần hỗ trợ key raw bytes trong trường hợp cần giữ dữ liệu lỗi gốc.

### Listener nhận null và xử lý sai

Phân biệt tombstone hợp lệ với null do ErrorHandlingDeserializer có header exception. Với batch listener, kiểm tra từng record và vị trí lỗi trước khi gọi domain service.

### Message converter sai cấu hình

Nếu consumer deserialize String thành công nhưng listener cần OrderCreated mà converter không đúng, hãy sửa message converter/type mapping. Đây không phải lỗi có thể phục hồi bằng retry cùng payload.

### Schema registry mất kết nối

Phân biệt lỗi tạm thời của registry với schema ID không tồn tại. Tránh chuyển hàng loạt record hợp lệ vào DLT khi dependency registry ngắn hạn bị outage nếu retry/backpressure hợp lý hơn.

### DLT publish thất bại vì raw bytes

Kiểm tra value/key serializer của DLT producer. Cần hỗ trợ byte[] từ record deserialize lỗi, không chỉ JSON object.

### Publish DLT thành công nhưng duplicate xuất hiện

Có thể consumer crash giữa publish DLT và commit offset nguồn. Dùng event ID và cơ chế idempotent để kiểm soát duplicate; không giả định recovery chuyển topic là exactly once end-to-end.

## 20. Kiểm thử các kịch bản trước khi đưa vào production

Một bộ test tích hợp nên bao gồm:

| Input | Kỳ vọng |
|---|---|
| JSON hợp lệ và đúng contract | Listener được gọi đúng một lần trong luồng bình thường |
| JSON bị cắt | Listener không chạy; error handler nhận lỗi; DLT lưu raw bytes |
| Key bytes sai | Lỗi key được bắt, không giữ partition vô hạn |
| JSON đúng cú pháp nhưng field sai kiểu | Lỗi deserialize/conversion được phân loại và recover |
| Header type không nằm trong trusted packages | Không tự mở rộng class trust; record được xử lý an toàn |
| Tombstone value null | Xử lý theo contract, không mặc định coi là poison pill |
| Lỗi validation | Exception domain được phân loại non-retryable |
| Database unavailable tạm thời | Retry có giới hạn và backoff |
| DLT không tồn tại hoặc không có ACL | Recovery báo lỗi, không đánh dấu thành công giả |
| DLT serializer chỉ hỗ trợ object | Kiểm tra handling raw bytes hoặc sửa serializer |
| Crash sau DLT publish trước offset commit | Có thể redelivery; replay/idempotency an toàn |
| Batch có một record lỗi ở giữa | Xử lý đúng vị trí lỗi và bảo vệ record đã xử lý |

Test nên dùng embedded Kafka/Testcontainers hoặc môi trường tích hợp phù hợp với version ứng dụng; mục đích là xác nhận toàn bộ đường đi từ bytes qua consumer, error handler tới DLT. Một unit test chỉ gọi trực tiếp method listener không kiểm tra được lỗi phát sinh trước method.

## 21. Checklist cấu hình và vận hành

- Xác định lỗi có xảy ra ở poll/deserializer, conversion/argument mapping hay trong method.
- Có ErrorHandlingDeserializer cho các key/value delegate có khả năng gặp dữ liệu lỗi.
- Delegate.class khớp wire format và schema registry thực tế.
- Trusted packages/type mapping được giới hạn.
- MessageConverter và method signature có contract rõ ràng.
- Không nhầm tombstone null với null do deserialize error.
- DefaultErrorHandler được gắn vào đúng listener factory.
- Lỗi dữ liệu cố định được phân loại non-retryable.
- Retry cho lỗi hạ tầng có giới hạn attempts, backoff và deadline.
- DeadLetterPublishingRecoverer dùng đúng KafkaTemplate và serializers.
- DLT hỗ trợ raw byte[] khi deserialize thất bại.
- DLT topic/partition, replication, retention và ACL đã được chuẩn bị.
- DLT publish failure không được coi là recovery thành công.
- Batch listener kiểm tra deserialization exception headers và báo vị trí lỗi.
- Event ID được giữ ổn định qua recovery và replay.
- Listener/database/API side effects có cơ chế idempotency.
- Log có topic, partition, offset và exception nhưng không lộ raw secrets.
- Có metric và cảnh báo cho poison pill, DLT errors, consumer lag và schema registry.
- Quy trình replay/quarantine có quyền kiểm soát và audit.
- Đã chạy thử các trường hợp malformed payload, schema mismatch và lỗi DLT trước khi triển khai.

**Kết luận:** Khi một record lỗi trước khi vào @KafkaListener, try/catch trong method không phải điểm sửa lỗi. Cần xác định lỗi phát sinh ở deserializer, converter hay argument resolution; dùng ErrorHandlingDeserializer khi lỗi xảy ra trong poll; chuyển lỗi có đủ metadata vào CommonErrorHandler/DeadLetterPublishingRecoverer; rồi đảm bảo raw bytes, topic/partition/offset và kết quả recovery được xử lý an toàn. Cách này giúp consumer vượt qua poison pill mà không im lặng làm mất record hoặc tạo vòng retry vô hạn.

