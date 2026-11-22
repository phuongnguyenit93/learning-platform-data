# Contract test cho schema và tương thích producer, consumer

Trong hệ thống event streaming, producer và consumer thường được phát triển, triển khai và mở rộng độc lập. Một producer có thể phát hành phiên bản sự kiện mới trong khi nhiều consumer vẫn đang chạy phiên bản cũ; consumer cũng có thể đọc lại dữ liệu đã tồn tại từ nhiều ngày hoặc nhiều tháng trước. Vì vậy, việc một thông điệp được ghi thành công vào Kafka chưa chứng minh rằng các dịch vụ còn lại có thể hiểu và xử lý nó.

Contract test xác định và kiểm tra thỏa thuận giữa các bên trao đổi sự kiện: topic, key, schema của value, headers, ý nghĩa dữ liệu và các hành vi mà consumer được phép dựa vào. Với Kafka, contract còn phải tính đến partition, thứ tự trong từng partition, consumer group, retry và khả năng phát lại sự kiện. Bài học này thuộc chương **Kiểm thử** của module **KAFKA**, tập trung vào việc kiểm tra schema và khả năng tương thích giữa producer, consumer trong các ứng dụng Java/Spring Kafka.

## 1. Contract nằm ở đâu trong luồng Kafka?

Kafka lưu trữ key, value, headers và metadata của record dưới dạng byte cùng thông tin phân phối. Broker không tự hiểu ý nghĩa nghiệp vụ của JSON, Avro, Protobuf hay một object Java. Việc kiểm tra cấu trúc thường nằm ở serializer/deserializer, Schema Registry hoặc logic của ứng dụng.

Một contract sự kiện nên mô tả ít nhất các thành phần sau:

| Thành phần | Nội dung cần thống nhất | Ví dụ |
|---|---|---|
| Topic | Tên topic và mục đích của sự kiện | orders.created |
| Key | Định danh dùng để chọn partition và gom thứ tự theo thực thể | orderId |
| Value | Schema, kiểu dữ liệu, trường bắt buộc và ý nghĩa trường | OrderCreated |
| Headers | Metadata mà consumer cần đọc | event-type, correlation-id |
| Thứ tự | Phạm vi bảo đảm thứ tự | Các sự kiện cùng orderId đi cùng partition |
| Lỗi | Cách xử lý record không hợp lệ | Retry có giới hạn rồi chuyển DLQ |
| Tiến hóa | Chính sách tương thích schema | BACKWARD_TRANSITIVE |

Ví dụ, producer của dịch vụ đơn hàng phát sự kiện OrderCreated lên orders.created. Consumer của dịch vụ kho cần biết orderId là định danh ổn định, items chứa các mặt hàng đã xác nhận, occurredAt là thời điểm sự kiện xảy ra và currency xác định đơn vị của totalAmount. Nếu producer đổi totalAmount từ đơn vị đồng sang đơn vị nghìn đồng mà vẫn giữ kiểu decimal, schema có thể vẫn hợp lệ nhưng ý nghĩa contract đã bị phá vỡ. Vì vậy, contract test phải kiểm tra cả cấu trúc lẫn các quy ước nghiệp vụ quan trọng.

Nên lưu schema và ví dụ record chuẩn trong repository cùng mã nguồn, có review và version rõ ràng. Tài liệu contract cần cho biết subject trên Schema Registry, chiến lược đặt tên subject, chính sách tương thích và phiên bản consumer đang hỗ trợ.

## 2. Phân biệt ba lớp kiểm tra

Không nên gộp mọi lỗi producer/consumer vào một bài kiểm thử duy nhất. Có ba lớp cần được kiểm tra riêng:

1. **Schema hợp lệ:** record có đúng cấu trúc, kiểu dữ liệu, trường bắt buộc, giới hạn và quy tắc định dạng hay không.
2. **Schema tương thích:** schema mới có thể phối hợp với schema cũ theo chiều triển khai và phát lại dữ liệu mà hệ thống yêu cầu hay không.
3. **Contract lúc chạy:** producer có thực sự gửi đúng topic, key, headers và payload; consumer có deserialize và xử lý được record đó hay không.

Schema Registry hỗ trợ quản lý phiên bản schema và từ chối đăng ký schema không tương thích theo chính sách đã cấu hình. Tuy nhiên, kiểm tra tương thích ở Registry không xác nhận ý nghĩa nghiệp vụ của trường, cách chọn Kafka key, quy tắc retry hoặc việc consumer có xử lý đúng sự kiện hay không. Những điều đó vẫn cần test ở ứng dụng.

## 3. Hiểu đúng các chế độ tương thích schema

Với Schema Registry, các chế độ phổ biến được hiểu theo hướng đọc dữ liệu:

| Chế độ | Điều được bảo đảm | Tình huống triển khai thường phù hợp |
|---|---|---|
| BACKWARD | Consumer dùng schema mới đọc được dữ liệu được ghi bằng schema cũ gần nhất | Triển khai consumer mới trước producer mới |
| BACKWARD_TRANSITIVE | Schema mới đọc được dữ liệu của tất cả phiên bản cũ | Consumer có thể replay dữ liệu từ toàn bộ lịch sử |
| FORWARD | Consumer dùng schema cũ đọc được dữ liệu được ghi bằng schema mới gần nhất | Triển khai producer mới trước consumer mới |
| FORWARD_TRANSITIVE | Schema cũ tương thích với dữ liệu của mọi phiên bản mới hơn theo phạm vi kiểm tra của Registry | Cần duy trì khả năng đọc chéo nhiều phiên bản |
| FULL | Đáp ứng cả chiều backward và forward với phiên bản được so sánh | Hai nhóm dịch vụ được nâng cấp độc lập |
| FULL_TRANSITIVE | Đáp ứng cả hai chiều với toàn bộ các phiên bản trước đó | Cần tương thích hai chiều trong lịch sử dài |
| NONE | Registry không kiểm tra tương thích | Chỉ dùng khi có chủ đích và có kiểm soát riêng |

Các chế độ không có hậu tố TRANSITIVE thường so sánh schema mới với phiên bản mới nhất của subject. Chế độ transitive kiểm tra với toàn bộ các phiên bản trước đó. Với topic có retention dài hoặc consumer thường xuyên replay, chỉ tương thích với phiên bản mới nhất có thể chưa đủ: schema hiện tại có thể đọc được bản ghi gần nhất nhưng không đọc được bản ghi rất cũ.

Hai chiều tương thích thường bị nhầm lẫn:

- **Backward:** reader mới đọc được dữ liệu cũ. Đây là điều cần có khi cập nhật consumer trước, trong lúc producer cũ vẫn đang phát sự kiện.
- **Forward:** reader cũ đọc được dữ liệu mới. Đây là điều cần có khi cập nhật producer trước, trong lúc consumer cũ vẫn đang chạy.
- **Full:** hỗ trợ cả hai chiều, giúp triển khai theo nhiều thứ tự hơn.

Ví dụ với subject orders.created-value, nếu schema mới thêm trường currency với giá trị mặc định phù hợp trong Avro, reader mới có thể đọc record cũ chưa có trường này. Điều đó hỗ trợ backward compatibility. Nhưng để reader cũ đọc record mới, schema reader cũ cũng phải xử lý được dữ liệu mới theo quy tắc của định dạng; không thể suy ra khả năng forward chỉ từ việc schema mới có trường mặc định.

Chọn chính sách dựa trên cách triển khai thật. Nếu triển khai consumer mới trước producer mới, kiểm tra backward compatibility. Nếu producer có thể phát record mới khi consumer cũ còn hoạt động, cần forward compatibility. Nếu cần cả hai trường hợp, dùng full. Nếu dữ liệu cũ có thể được phát lại sau nhiều lần thay đổi schema, cân nhắc chế độ transitive.

## 4. Tiến hóa schema mà không phá vỡ consumer

Quy tắc tương thích phụ thuộc định dạng. Không áp dụng máy móc quy tắc của Avro cho JSON Schema hoặc Protobuf.

### Ví dụ Avro: thêm trường có default

Schema phiên bản 1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "double" }
  ]
}
~~~

Phiên bản 2 bổ sung currency:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "double" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
~~~

Khi reader dùng schema phiên bản 2 đọc record được ghi theo phiên bản 1, Avro dùng default của trường currency để hoàn thiện giá trị còn thiếu. Đây là một cách tiến hóa thường dùng để duy trì backward compatibility. Default của Avro phục vụ quá trình phân giải schema khi đọc; ứng dụng producer vẫn nên gán giá trị rõ ràng khi tạo event mới để dữ liệu mới có ý nghĩa chính xác.

Một số lưu ý khi thay đổi Avro:

- Khi thêm trường, cung cấp default nếu reader mới phải đọc được record cũ.
- Khi bỏ trường, kiểm tra reader cũ có thể đọc record mới hay không; chiều forward có thể cần default trong schema reader cũ.
- Đổi tên trường cần xem xét alias và khả năng tương thích của mọi consumer đang triển khai.
- Đổi kiểu dữ liệu chỉ an toàn trong những trường hợp được quy tắc phân giải Avro hỗ trợ; phải chạy kiểm tra với Registry thay vì phỏng đoán.
- Không đổi ý nghĩa của trường mà vẫn giữ nguyên tên và kiểu. Việc đổi đơn vị, múi giờ, quy ước làm tròn hoặc ý nghĩa trạng thái là thay đổi contract nghiệp vụ.

### JSON Schema và Protobuf

Với JSON Schema, kiểm tra kỹ required, kiểu dữ liệu, enum, giới hạn giá trị và additionalProperties. Chẳng hạn, một consumer từ chối mọi thuộc tính chưa biết bằng additionalProperties: false có thể bị ảnh hưởng khi producer thêm trường. Thay đổi một trường từ tùy chọn thành bắt buộc cũng có thể làm record cũ không còn hợp lệ.

Với Protobuf, số hiệu field là một phần của wire format. Không tái sử dụng số hiệu của field đã xóa; hãy reserve số hiệu và tên đã ngừng dùng. Tránh thay đổi kiểu field nếu không hiểu rõ wire compatibility và ý nghĩa dữ liệu. Schema Registry có thể kiểm tra tương thích theo định dạng, nhưng test ứng dụng vẫn phải xác nhận consumer diễn giải đúng giá trị.

## 5. Kiểm tra subject và cấu hình Schema Registry

Schema Registry kiểm tra tương thích theo **subject**. Với chiến lược đặt tên mặc định thường gặp là TopicNameStrategy, subject cho value có dạng **&lt;topic&gt;-value**, còn subject cho key có dạng **&lt;topic&gt;-key**. Ví dụ, value của orders.created được quản lý dưới subject orders.created-value.

Các chiến lược khác như RecordNameStrategy hoặc TopicRecordNameStrategy tạo subject theo record name hoặc kết hợp topic và record name. Producer và consumer phải thống nhất chiến lược này. Nếu producer đăng ký schema dưới subject khác với subject mà nhóm vận hành đang kiểm tra, bài kiểm tra tương thích có thể xanh trong khi luồng triển khai thực tế vẫn gặp lỗi.

Khi thiết lập contract, ghi lại:

- Tên topic và subject key/value chính xác.
- Định dạng schema: Avro, Protobuf hay JSON Schema.
- Chiến lược đặt tên subject được cấu hình ở serializer.
- Chính sách compatibility áp dụng ở global hoặc subject level.
- Registry URL và cơ chế xác thực của môi trường kiểm thử.
- Cách quản lý đăng ký schema: tự đăng ký khi chạy ứng dụng hay đăng ký qua pipeline triển khai.

Không kiểm tra hoặc thay đổi compatibility trên Schema Registry production trong bài test CI. Dùng Registry riêng cho môi trường test hoặc container dùng một lần. Pipeline nên gửi schema ứng viên đến đúng subject, yêu cầu Registry kiểm tra với chính sách đã chọn và làm thất bại build nếu schema không tương thích.

## 6. Xây dựng contract test cho producer

Producer test cần xác nhận payload được tạo đúng và record được gửi theo contract đã công bố.

Ở lớp unit test, kiểm tra mapper và logic tạo event:

- Trường định danh có giá trị và không bị thay đổi ngoài ý muốn.
- Trường thời gian dùng quy ước đã thống nhất, ví dụ UTC và ISO-8601.
- Số tiền đi kèm đơn vị tiền tệ; không chỉ kiểm tra kiểu số.
- Trường bắt buộc không bị null hoặc bỏ sót.
- Event type và schema version được gắn đúng nơi theo contract.
- Dữ liệu nhạy cảm không bị đưa vào event nếu contract không cho phép.

Ở lớp schema test, serialize event thành dạng wire format rồi kiểm tra bằng schema đã phát hành. Với JSON Schema, có thể chuyển object thành JsonNode và đưa qua validator. Với Avro hoặc Protobuf, nên dùng serializer thật để phát hiện lỗi mapping, field name, union, enum hoặc cấu hình schema.

Ví dụ minh họa một test cho JSON Schema:

~~~java
@Test
void orderCreatedMustMatchPublishedSchema() throws Exception {
    OrderCreated event = new OrderCreated(
        "order-1001",
        new BigDecimal("125000"),
        "VND"
    );

    JsonNode payload = objectMapper.valueToTree(event);

    Set<ValidationMessage> violations =
        schemaValidator.validate(payload);

    assertThat(violations).isEmpty();
}
~~~

schemaValidator trong ví dụ là adapter của dự án, được khởi tạo từ schema contract đã version hóa. Không nên tạo schema từ chính class Java đang được kiểm tra, vì khi class và schema cùng thay đổi sai theo một cách, test có thể không phát hiện contract bị phá vỡ.

Tiếp theo, kiểm tra record được gửi lên đúng topic với key ổn định. Ví dụ dưới đây minh họa phần tích hợp bằng Spring Kafka, EmbeddedKafka và value dạng JSON string; phần cấu hình KafkaTemplate, ObjectMapper, schemaValidator và topic được khai báo trong test fixture:

~~~java
@Test
void producerPublishesRecordWithContractKey() throws Exception {
    OrderCreated event = new OrderCreated(
        "order-1001",
        new BigDecimal("125000"),
        "VND"
    );
    String payload = objectMapper.writeValueAsString(event);

    Map<String, Object> consumerProps =
        KafkaTestUtils.consumerProps("contract-test", "false", embeddedKafka);
    consumerProps.put(
        ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
        "earliest"
    );

    try (Consumer<String, String> consumer =
             new DefaultKafkaConsumerFactory<String, String>(
                 consumerProps,
                 new StringDeserializer(),
                 new StringDeserializer()
             ).createConsumer()) {

        embeddedKafka.consumeFromAnEmbeddedTopic(consumer, TOPIC);

        kafkaTemplate.send(TOPIC, event.orderId(), payload)
            .get(10, TimeUnit.SECONDS);

        ConsumerRecord<String, String> record =
            KafkaTestUtils.getSingleRecord(consumer, TOPIC);

        assertThat(record.key()).isEqualTo(event.orderId());
        assertThat(record.topic()).isEqualTo(TOPIC);

        JsonNode actualPayload = objectMapper.readTree(record.value());
        assertThat(schemaValidator.validate(actualPayload)).isEmpty();
    }
}
~~~

Test này kiểm tra đường đi thực tế qua broker và xác nhận key, topic, payload. Nếu ứng dụng dùng Avro, Protobuf hoặc JSON Schema serializer tích hợp Schema Registry, cấu hình test phải dùng serializer/deserializer tương ứng và một Schema Registry test riêng. Chỉ dùng EmbeddedKafka không thay thế được Schema Registry.

Với producer có nhiều event type, tạo test theo từng contract và kiểm tra cả headers. Không chỉ gọi method publish rồi xác nhận không ném exception: record có thể được gửi nhầm topic, thiếu key hoặc chứa payload không đúng schema mà lời gọi vẫn hoàn tất.

## 7. Xây dựng contract test cho consumer

Consumer test phải xác nhận ứng dụng đọc được dữ liệu hợp lệ từ những phiên bản producer mà contract cam kết hỗ trợ. Một bộ fixture hữu ích gồm:

- Record mẫu từ phiên bản schema hiện tại.
- Record được tạo theo một hoặc nhiều phiên bản cũ còn nằm trong retention.
- Record có trường tùy chọn bị thiếu hoặc có giá trị default.
- Record có enum hoặc trường mở rộng theo đúng quy tắc tương thích của định dạng.
- Record không hợp lệ để xác nhận đường xử lý lỗi.

Các fixture cũ phải được giữ nguyên như dữ liệu đã từng được phát hành. Không serialize fixture cũ bằng class Java mới, vì cách đó vô tình biến dữ liệu cũ thành dữ liệu mới và làm mất mục đích kiểm tra replay.

Một consumer contract test nên đi qua deserializer thật của ứng dụng, sau đó kiểm tra:

1. Record được deserialize thành event hoặc domain object mong đợi.
2. Trường được bổ sung có default đúng khi đọc record cũ.
3. Trường không còn được dùng được xử lý theo chính sách đã thống nhất.
4. Event thiếu dữ liệu bắt buộc bị từ chối hoặc chuyển sang luồng lỗi có kiểm soát.
5. Consumer không làm mất key, event ID hoặc metadata cần cho idempotency và tracing.
6. Việc xử lý lại cùng một event không gây tác động nghiệp vụ lặp ngoài ý muốn.

Có thể tổ chức test bằng parameterized test để chạy cùng consumer với từng fixture:

~~~java
@ParameterizedTest
@ValueSource(strings = {
    "contracts/orders-created/v1.json",
    "contracts/orders-created/v2.json"
})
void consumerMustReadEverySupportedEventVersion(String fixturePath) {
    String rawRecord = loadFixture(fixturePath);

    OrderCreated event = productionEventDeserializer.deserialize(rawRecord);

    assertThat(event.orderId()).isNotBlank();
    assertThat(event.totalAmount()).isPositive();
    assertThat(event.currency()).isNotBlank();
}
~~~

Đây là khung minh họa; loadFixture và productionEventDeserializer là thành phần test của dự án. Nếu deserializer dùng Schema Registry, Registry trong test cần có các schema ID tương ứng hoặc fixture phải được tạo trong môi trường test theo cách giữ được metadata schema. Một JSON thuần không đại diện đầy đủ cho Avro wire format có schema ID.

Ngoài khả năng đọc, test consumer cần xác nhận hành vi nghiệp vụ và xử lý lỗi. Ví dụ, khi record lỗi tạm thời do dịch vụ phụ thuộc không sẵn sàng, consumer retry theo chính sách; khi record sai schema hoặc dữ liệu không thể khôi phục, consumer chuyển record sang dead-letter topic (DLT/DLQ) cùng thông tin gốc cần thiết. Test phải xác nhận số lần retry có giới hạn, lỗi được ghi nhận và record lỗi không làm consumer lặp vô hạn.

## 8. Kiểm tra ma trận tương thích producer và consumer

Schema compatibility và khả năng phối hợp giữa các phiên bản ứng dụng có liên quan nhưng không đồng nhất. Hãy lập ma trận dựa trên thứ tự triển khai thực tế:

| Producer | Consumer | Mục tiêu kiểm tra |
|---|---|---|
| v1 | v1 | Luồng cơ sở hoạt động |
| v1 | v2 | Consumer mới đọc được dữ liệu cũ; cần backward compatibility |
| v2 | v1 | Consumer cũ đọc được dữ liệu mới; cần forward compatibility |
| v2 | v2 | Phiên bản mới phối hợp bình thường |
| v1 và v2 cùng phát | v2 | Consumer mới xử lý được dữ liệu từ các producer đang rolling deploy |
| dữ liệu v1 được replay | consumer hiện tại | Consumer hiện tại đọc được dữ liệu lịch sử còn được hỗ trợ |

Không phải mọi hệ thống đều phải hỗ trợ mọi ô trong ma trận. Hãy ghi rõ phiên bản nào còn được phép chạy đồng thời, dữ liệu cũ nào còn trong retention và thời gian hỗ trợ replay. Nếu producer và consumer có thể được nâng cấp độc lập, kiểm tra các tổ hợp phiên bản có thể xuất hiện trong quá trình rolling deployment.

Một trình tự triển khai thường dùng:

- Với backward compatibility: triển khai consumer mới trước, chờ các consumer cũ được thay thế, rồi mới triển khai producer mới.
- Với forward compatibility: triển khai producer mới trước, bảo đảm consumer cũ đọc được record mới, rồi mới triển khai consumer mới.
- Với full compatibility: cả hai chiều đều được kiểm tra, nhưng vẫn phải kiểm thử hành vi trong giai đoạn chạy đồng thời.

Đừng xem ma trận schema là đủ cho toàn bộ hệ thống. Hai phiên bản có thể deserialize cùng payload nhưng xử lý nghiệp vụ khác nhau, ví dụ một phiên bản hiểu trạng thái CANCELLED là đã hoàn tiền trong khi phiên bản khác chỉ hiểu là đơn hàng đã hủy. Các trạng thái, đơn vị, quy tắc thời gian và ý nghĩa trường cần được kiểm tra bằng assertion nghiệp vụ.

## 9. Contract của Kafka còn bao gồm key, partition và giao nhận

Schema hợp lệ không đảm bảo thứ tự sự kiện. Kafka chỉ bảo đảm thứ tự trong một partition. Nếu các sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, producer cần dùng key ổn định như orderId để các record của đơn hàng đó được đưa vào cùng partition.

Contract test nên xác nhận:

- Key có mặt, đúng kiểu và ổn định giữa các event cùng thực thể.
- Những event cần thứ tự dùng cùng quy tắc partitioning.
- Consumer không giả định có thứ tự toàn cục giữa nhiều partition.
- Thay đổi số partition được đánh giá vì có thể làm thay đổi ánh xạ key sang partition và ảnh hưởng thứ tự khi dữ liệu cũ, mới cùng tồn tại.
- Header quan trọng như event type, correlation ID hoặc trace context được giữ nguyên qua producer và consumer.
- Consumer xử lý duplicate theo event ID hoặc khóa idempotency đã thống nhất.
- Retry, DLT/DLQ và transaction được kiểm tra theo semantics thực tế của ứng dụng.

Kafka thường được dùng với delivery semantics at-least-once; do đó một consumer có thể nhận lại record khi xử lý hoặc commit offset gặp lỗi. Nếu contract yêu cầu tác động nghiệp vụ chỉ xảy ra một lần, ứng dụng cần idempotency hoặc cơ chế giao dịch phù hợp. Không nên kết luận exactly once chỉ vì producer bật idempotence hoặc dùng transaction: phạm vi bảo đảm còn phụ thuộc cách consumer commit offset và cách cập nhật hệ thống đích.

Nếu event được chuyển qua Kafka Connect hoặc xử lý bằng Kafka Streams, contract cần được kiểm tra ở biên tích hợp: tên topic đầu vào/đầu ra, schema, key, headers và hành vi khi task hoặc stream được khởi động lại. Test transform đơn lẻ không thay thế kiểm tra record thực tế qua connector hoặc topology.

## 10. Tổ chức contract test trong CI/CD

Một pipeline có thể chạy theo trình tự sau:

1. **Kiểm tra schema:** parse schema, kiểm tra quy ước tên, trường bắt buộc và các quy tắc lint.
2. **Kiểm tra compatibility:** gửi schema ứng viên tới Schema Registry test và xác nhận subject chấp nhận theo policy.
3. **Unit test producer:** kiểm tra mapping, validation, key và headers.
4. **Unit test consumer:** kiểm tra mapping, nghiệp vụ, idempotency và xử lý lỗi.
5. **Integration test:** khởi chạy Kafka test broker, và Schema Registry nếu serializer cần nó; gửi record thật rồi đọc lại bằng consumer.
6. **Version matrix:** chạy consumer hiện tại với fixture lịch sử và các tổ hợp producer/consumer cần hỗ trợ.
7. **Kiểm tra cấu hình triển khai:** xác nhận topic, partition, security, registry URL và subject strategy ở môi trường mục tiêu.

Ví dụ, build phải thất bại nếu schema mới bị Registry từ chối, producer phát record thiếu key bắt buộc, hoặc consumer hiện tại không đọc được fixture cũ trong phạm vi hỗ trợ. Lỗi cần chỉ rõ subject, phiên bản schema, fixture và assertion bị vi phạm để nhóm phát triển có thể xử lý.

Integration test nên dùng phiên bản Kafka và Schema Registry tương thích với môi trường triển khai. Nếu cụm chạy KRaft, có thể dùng image Kafka hỗ trợ KRaft trong môi trường kiểm thử; contract của record vẫn phải được kiểm tra độc lập với cơ chế quản lý metadata của broker. Không cần dựng cả cụm production cho mọi test, nhưng cần có một số kiểm tra môi trường gần production cho cấu hình bảo mật, replication, transaction và kết nối Registry.

Không để test phụ thuộc vào topic hoặc schema còn sót lại từ lần chạy trước. Dùng topic, consumer group và subject riêng cho test, hoặc dọn trạng thái test một cách xác định. Khi test song song, tránh dùng chung group ID và topic nếu các test có thể tiêu thụ record của nhau.

## 11. Đọc lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Registry từ chối đăng ký schema | Thay đổi không tương thích với policy của subject | Xem diff schema, chiều backward/forward và phiên bản đang so sánh |
| Consumer báo lỗi deserialize | Serializer và deserializer khác định dạng, subject strategy hoặc Registry URL | Kiểm tra cấu hình hai phía và schema ID của record |
| Consumer đọc được JSON nhưng xử lý sai | Schema chỉ kiểm tra kiểu, ý nghĩa nghiệp vụ đã thay đổi | Bổ sung assertion cho đơn vị, trạng thái, thời gian và quy tắc domain |
| Consumer mới đọc được record mới nhưng replay record cũ thất bại | Policy chỉ tương thích với latest, thiếu transitive hoặc fixture lịch sử | Kiểm tra các phiên bản schema cũ còn trong retention |
| Event cùng thực thể bị xử lý sai thứ tự | Key không ổn định, số partition thay đổi hoặc consumer giả định thứ tự toàn cục | Kiểm tra key, partition và cách xử lý song song |
| Record lỗi bị retry vô hạn | Phân loại lỗi và giới hạn retry chưa rõ | Kiểm tra retry policy, DLT/DLQ và offset commit |
| Test chạy riêng thành công nhưng CI thất bại | Dùng chung topic/group, Registry state không sạch hoặc cấu hình môi trường khác nhau | Cô lập tài nguyên test và ghi rõ phiên bản dịch vụ phụ thuộc |

Khi gặp lỗi, lưu lại raw record, key, headers, topic, partition, offset, schema ID và exception gốc. Các thông tin này giúp phân biệt lỗi schema, lỗi cấu hình và lỗi nghiệp vụ.

## 12. Checklist trước khi phát hành

- [ ] Contract đã xác định topic, key, value, headers và ý nghĩa nghiệp vụ.
- [ ] Schema được version hóa và gắn đúng subject.
- [ ] Producer và consumer dùng đúng serializer/deserializer cùng subject strategy.
- [ ] Compatibility policy phù hợp thứ tự triển khai và nhu cầu replay.
- [ ] Schema ứng viên đã được kiểm tra trên Registry test.
- [ ] Producer test xác nhận payload, key, headers và topic.
- [ ] Consumer test đọc được fixture của các phiên bản còn được hỗ trợ.
- [ ] Integration test đi qua Kafka broker; có Registry test khi serializer yêu cầu.
- [ ] Retry, duplicate, idempotency và DLT/DLQ có kiểm thử.
- [ ] Thay đổi partition hoặc key đã được đánh giá về ordering.
- [ ] CI báo rõ subject, schema version và fixture khi contract test thất bại.

Contract test hiệu quả khi nó phản ánh những gì producer thực sự gửi và những gì consumer thực sự đọc. Kết hợp kiểm tra schema, ma trận tương thích, fixture lịch sử và integration test qua Kafka giúp phát hiện sớm lỗi tiến hóa event trước khi chúng xuất hiện trong luồng xử lý đang chạy.
