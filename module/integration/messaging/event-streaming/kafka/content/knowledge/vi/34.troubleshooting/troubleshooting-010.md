# Lỗi deserialization, schema không tương thích và bản ghi độc hại

Kafka lưu key, value và header dưới dạng byte. Broker không kiểm tra nội dung đó có phải JSON hợp lệ, Avro đúng schema hay một đối tượng Java mà consumer mong đợi hay không. Vì vậy, producer có thể ghi thành công nhưng consumer vẫn thất bại khi chuyển byte thành object. Nếu bản ghi lỗi luôn được đọc lại, một partition có thể bị kẹt tại cùng offset và các sự kiện phía sau không được xử lý.

Bài học thuộc chương **Chẩn đoán sự cố** của module **KAFKA**. Nội dung hướng dẫn phân biệt lỗi serialize ở producer với lỗi deserialize ở consumer, kiểm tra schema và Schema Registry, xử lý poison pill bằng Spring Kafka, đưa bản ghi lỗi vào dead-letter topic (DLT), rồi phát lại an toàn sau khi sửa nguyên nhân.

Sau bài học, người học có thể:

- Nhận diện lỗi serializer, deserializer, schema và dữ liệu đầu vào không hợp lệ.
- Xác định topic, partition, offset và bản ghi khiến consumer dừng tiến trình.
- Giải thích các chế độ tương thích schema và tác động khi triển khai producer/consumer khác phiên bản.
- Cấu hình ErrorHandlingDeserializer và error handler của Spring Kafka.
- Bảo toàn byte gốc, metadata và thông tin lỗi khi chuyển bản ghi sang DLT.
- Phân biệt lỗi tạm thời với poison pill không thể xử lý bằng retry.
- Xây dựng quy trình kiểm tra payload, phát lại và chống tác dụng phụ trùng lặp.

## 1. Kafka truyền byte, ứng dụng chịu trách nhiệm giải mã

Producer gọi serializer để chuyển key và value thành byte trước khi gửi. Broker lưu và chuyển tiếp byte theo partition. Consumer gọi deserializer để chuyển byte nhận được thành kiểu dữ liệu mà ứng dụng sử dụng.

Luồng xử lý có thể hình dung như sau:

    Producer object
        |
        v
    Serializer -> byte[]
        |
        v
    Kafka broker: topic / partition / offset
        |
        v
    Consumer poll()
        |
        v
    Deserializer -> object
        |
        v
    Listener / business logic

Lỗi ở mỗi ranh giới có biểu hiện khác nhau:

| Vị trí | Ví dụ | Hệ quả thường gặp |
|---|---|---|
| Producer serializer | Không chuyển được object thành JSON hoặc Avro | Gửi thất bại trước khi broker nhận bản ghi |
| Producer schema registry | Không đăng ký được schema, bị từ chối do compatibility hoặc không kết nối được registry | Future gửi lỗi; bản ghi có thể chưa được gửi |
| Consumer deserializer | Byte không hợp lệ, sai định dạng hoặc schema id không tồn tại | poll() hoặc listener container báo lỗi trước khi logic nghiệp vụ chạy |
| Consumer schema registry | Không tải được schema hoặc không có quyền đọc schema | Consumer không thể giải mã dù byte trong Kafka vẫn còn |
| Business validation | JSON giải mã được nhưng thiếu trường bắt buộc hoặc giá trị sai miền | Listener nhận object nhưng từ chối xử lý |

Không nên kết luận broker làm hỏng dữ liệu chỉ vì consumer deserialize thất bại. Hãy kiểm tra byte thực tế, serializer của producer, deserializer của consumer và schema được dùng ở hai phía.

### Các dạng lỗi thường gặp

- **Sai định dạng:** producer gửi JSON nhưng consumer dùng Avro deserializer, hoặc hai phía dùng serializer khác nhau.
- **Payload hỏng:** byte bị cắt cụt, mã hóa ký tự sai, JSON không hợp lệ hoặc dữ liệu không đúng wire format.
- **Schema không tương thích:** consumer mới không đọc được dữ liệu được ghi theo schema cũ, hoặc producer phát hành schema vi phạm chính sách compatibility.
- **Schema id không hợp lệ:** payload chứa schema id không tồn tại, thuộc registry khác hoặc consumer không thể truy xuất.
- **Kiểu dữ liệu không khớp:** JSON có chuỗi ở trường số, enum mới chưa được consumer cũ nhận diện, hoặc cấu trúc lồng nhau thay đổi ngoài dự kiến.
- **Bản ghi độc hại hoặc bất thường:** payload quá lớn, cấu trúc lồng sâu, trường chứa giá trị gây tốn tài nguyên hoặc dữ liệu được tạo nhằm khai thác lỗi parser/deserializer.

## 2. Phân biệt lỗi deserialize với lỗi schema

### Lỗi serializer/deserializer

Serializer và deserializer phải thống nhất về wire format. Ví dụ, StringSerializer tạo byte UTF-8 của chuỗi; StringDeserializer phù hợp để đọc dạng này. Nếu producer dùng JSON serializer nhưng consumer dùng StringDeserializer, consumer có thể nhận chuỗi JSON nguyên bản và tự parse sau đó. Nếu consumer dùng Avro deserializer để đọc byte JSON thuần, giải mã sẽ thất bại.

Hãy ghi lại cấu hình serializer/deserializer hiệu lực của cả producer và consumer. Với Spring Boot, kiểm tra các thuộc tính spring.kafka.producer.key-serializer, spring.kafka.producer.value-serializer, spring.kafka.consumer.key-deserializer và spring.kafka.consumer.value-deserializer, kể cả các thuộc tính được override trong profile hoặc cấu hình runtime.

### Lỗi Schema Registry

Với Avro, Protobuf hoặc JSON Schema dùng Schema Registry, byte trên Kafka thường mang thông tin để deserializer tìm schema tương ứng. Khi không tìm thấy schema id, registry không truy cập được, xác thực thất bại hoặc schema không thể được dùng để tạo object, consumer sẽ không giải mã được bản ghi.

Kiểm tra:

1. Producer và consumer có trỏ tới đúng Schema Registry environment hay không.
2. Schema id trong payload có tồn tại ở registry mà consumer đang dùng không.
3. Subject được dùng để đăng ký schema có đúng chiến lược đặt tên không.
4. Tài khoản consumer có quyền đọc schema và registry có khả dụng không.
5. Phiên bản serializer/deserializer có tương thích với định dạng và schema đã phát hành không.

Lỗi kết nối hoặc quyền truy cập registry có thể là lỗi hạ tầng tạm thời. Schema id không tồn tại hoặc byte không đúng wire format thường cần điều tra dữ liệu hoặc cấu hình triển khai. Phân loại đúng giúp tránh đưa toàn bộ bản ghi hợp lệ vào DLT chỉ vì registry tạm thời mất kết nối.

## 3. Schema evolution và compatibility

Schema thay đổi theo thời gian khi nghiệp vụ thêm trường, đổi kiểu, bỏ trường hoặc mở rộng tập giá trị enum. Một schema mới được đăng ký thành công chưa chắc tương thích với mọi producer và consumer đang chạy.

### Các chế độ compatibility phổ biến

| Chế độ | Ý nghĩa khái quát | Trường hợp triển khai |
|---|---|---|
| BACKWARD | Consumer dùng schema mới có thể đọc dữ liệu được ghi theo schema trước đó | Triển khai consumer mới trước, sau đó producer mới |
| FORWARD | Consumer dùng schema cũ có thể đọc dữ liệu được ghi theo schema mới | Triển khai producer mới trong khi consumer cũ còn chạy |
| FULL | Hỗ trợ cả chiều backward và forward | Producer và consumer được nâng cấp theo thứ tự linh hoạt hơn |
| BACKWARD_TRANSITIVE | Kiểm tra backward với các phiên bản trước trong lịch sử subject | Cần đọc dữ liệu từ nhiều thế hệ schema |
| FORWARD_TRANSITIVE | Kiểm tra forward với các phiên bản trước trong lịch sử subject | Cần bảo đảm consumer cũ có thể đọc schema mới qua nhiều lần nâng cấp |
| FULL_TRANSITIVE | Kiểm tra cả hai chiều với các phiên bản trước trong lịch sử subject | Cần khả năng tương thích dài hạn giữa nhiều thế hệ |

Chi tiết kiểm tra phụ thuộc định dạng schema và phiên bản Schema Registry. Không nên suy ra một thay đổi luôn tương thích chỉ từ tên chế độ; hãy kiểm tra quy tắc của Avro, Protobuf hoặc JSON Schema đang sử dụng.

### Ví dụ thay đổi schema an toàn

Giả sử event OrderCreated ban đầu có orderId và amount. Phiên bản sau thêm currency.

    {
      "type": "record",
      "name": "OrderCreated",
      "fields": [
        { "name": "orderId", "type": "string" },
        { "name": "amount", "type": "double" },
        { "name": "currency", "type": "string", "default": "VND" }
      ]
    }

Trong Avro, default của trường mới giúp reader schema mới đọc record cũ không có trường currency. Tuy nhiên, xóa trường, đổi kiểu hoặc thay đổi union/enum cần được phân tích theo quy tắc resolution của Avro. Default không tự làm cho mọi thay đổi schema trở nên tương thích.

Với JSON Schema, cần xem xét required, kiểu dữ liệu và các ràng buộc như additionalProperties. Với Protobuf, cần giữ nguyên field number, tránh tái sử dụng số field đã xóa và dùng reserved cho field number hoặc tên đã bỏ. Một thay đổi có vẻ nhỏ trong mã nguồn có thể phá vỡ wire compatibility nếu thay đổi sai quy tắc của định dạng.

### Trình tự triển khai schema

Một trình tự phổ biến khi cần hỗ trợ producer và consumer chạy lệch phiên bản:

1. Thiết kế schema mới theo compatibility policy của subject.
2. Kiểm tra schema với registry hoặc công cụ CI trước khi phát hành.
3. Triển khai consumer có khả năng đọc cả dữ liệu cũ và mới.
4. Sau khi consumer mới hoạt động ổn định, triển khai producer phát dữ liệu theo schema mới.
5. Theo dõi lỗi deserialize, tỷ lệ DLT và phân bố schema id.
6. Chỉ loại bỏ khả năng đọc schema cũ sau khi hết thời hạn lưu giữ và replay yêu cầu dữ liệu cũ.

Đừng triển khai producer mới trước consumer cũ nếu thay đổi không có forward compatibility. Với dữ liệu lưu lâu trong Kafka, cần tính cả việc replay từ offset cũ: consumer mới phải đọc được những schema từng được producer phát hành trong khoảng retention, không chỉ schema hiện tại.

## 4. Poison pill và vì sao một partition có thể bị kẹt

Poison pill là bản ghi khiến consumer liên tục thất bại khi xử lý. Ví dụ một record tại offset 120 có JSON hỏng. Consumer đọc đến offset 120, deserializer ném exception; nếu error handler retry vô hạn và không có cách phục hồi, consumer có thể lặp lại cùng record. Các record offset 121 trở đi trong partition đó không được xử lý.

Một số biểu hiện:

- Log lặp lại cùng topic, partition và offset.
- Consumer lag tăng dù tốc độ gửi vào topic không cao.
- Listener không được gọi hoặc không đến được business handler.
- Consumer group không tiến committed offset qua bản ghi lỗi.
- Các partition khác vẫn chạy bình thường, trong khi một partition liên tục báo lỗi.

Phải xác định lỗi là tạm thời hay dữ liệu không thể giải mã:

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Tạm thời | Schema Registry timeout, DNS lỗi, registry đang khởi động | Retry có giới hạn và backoff; tiếp tục khi dịch vụ hồi phục |
| Có thể sửa cấu hình | Consumer trỏ nhầm registry, thiếu quyền, sai subject | Sửa cấu hình/quyền rồi đọc lại record |
| Dữ liệu vĩnh viễn không hợp lệ | JSON hỏng, schema id không tồn tại, wire format sai | Lưu bản gốc vào DLT hoặc kho cách ly, sau đó xử lý record tiếp theo theo chính sách |
| Nghiệp vụ từ chối | Giá trị ngoài miền, thiếu định danh bắt buộc | Xử lý như validation failure; DLT hoặc luồng từ chối nghiệp vụ |

Không retry liên tục một lỗi dữ liệu chắc chắn không thể tự sửa. Retry chỉ làm tăng log, tải hệ thống và độ trễ của các bản tin phía sau.

## 5. Xử lý deserialization trong Spring Kafka

Một điểm quan trọng là deserialization thường diễn ra trong KafkaConsumer.poll() trước khi listener nhận được ConsumerRecord. Nếu deserializer ném exception trực tiếp, error handler ở tầng listener có thể không có đủ record đã giải mã để xử lý như lỗi nghiệp vụ thông thường.

### Dùng ErrorHandlingDeserializer

ErrorHandlingDeserializer bọc deserializer thực tế. Khi delegate deserialize thất bại, wrapper lưu thông tin exception và byte gốc vào header của record để Spring Kafka có thể chuyển lỗi tới container error handler.

Ví dụ cấu hình consumer dùng JSON:

    spring:
      kafka:
        consumer:
          key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
          value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
          properties:
            spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
            spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
            spring.json.value.default.type: com.example.events.OrderEvent
            spring.json.trusted.packages: com.example.events
            spring.json.use.type.headers: false

Chỉ tin cậy package chứa kiểu event đã kiểm soát. Tránh cấu hình trusted packages quá rộng hoặc cho phép payload quyết định tùy ý kiểu Java cần khởi tạo. Với Avro hoặc Protobuf, thay delegate bằng deserializer tương ứng và cấu hình Schema Registry theo đúng thư viện đang dùng.

ErrorHandlingDeserializer không tự sửa payload. Nó giúp framework giữ lại ngữ cảnh lỗi và chuyển record tới cơ chế xử lý lỗi thay vì để lỗi deserialize thoát ra mà không có record để phục hồi.

### Đưa bản ghi lỗi vào dead-letter topic

Spring Kafka có thể dùng DefaultErrorHandler kết hợp DeadLetterPublishingRecoverer để chuyển record không xử lý được sang DLT. Ví dụ khung cấu hình:

    @Bean
    DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> template) {
        return new DeadLetterPublishingRecoverer(
                template,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()));
    }

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {
        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(0L, 0L));
    }

Đây là cấu hình minh họa; cần khai báo bean theo phiên bản Spring Kafka và container factory của ứng dụng. Tạo DLT trước, với số partition đủ để nhận các partition nguồn nếu recoverer giữ nguyên partition. Cần cấu hình producer của DLT để serialize được cả object đã giải mã lẫn byte[] gốc được phục hồi từ header của ErrorHandlingDeserializer. Có thể dùng DelegatingByTypeSerializer hoặc một KafkaTemplate riêng phù hợp với kiểu dữ liệu của DLT.

Với lỗi deserialization có tính xác định, retry nhiều lần thường không giúp ích. Có thể chuyển thẳng sang DLT sau một lần xử lý. Với lỗi truy cập Schema Registry hoặc lỗi mạng tạm thời, nên phân loại exception để retry có giới hạn trước khi recover. Đừng áp dụng cùng một chính sách retry cho mọi exception.

### Lưu ý về offset và commit

Khi recoverer gửi thành công record tới DLT, error handler có thể đánh dấu record nguồn đã được xử lý theo cơ chế acknowledgment/commit của container. Nếu gửi DLT thất bại, không nên commit record nguồn như thể đã cách ly thành công. Kiểm tra cấu hình ackAfterHandle, commitRecovered, acknowledgment mode và transaction nếu ứng dụng dùng chúng.

Với listener batch, xử lý record lỗi và commit offset có thể phức tạp hơn vì một poll trả nhiều record. Hãy cấu hình batch error handling phù hợp và kiểm tra chính xác record nào được retry, record nào được recover, và offset nào được commit. Không suy ra rằng một lỗi trong batch luôn chỉ ảnh hưởng một record.

## 6. Xử lý bằng consumer thuần Kafka hoặc giải mã thủ công

Nếu muốn kiểm soát hoàn toàn dữ liệu gốc, consumer có thể đọc byte[] bằng ByteArrayDeserializer, sau đó gọi decoder trong code ứng dụng:

    Properties props = new Properties();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-reader");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName());
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class.getName());
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    try (KafkaConsumer<String, byte[]> consumer =
                 new KafkaConsumer<>(props)) {
        consumer.subscribe(List.of("orders"));

        while (running) {
            ConsumerRecords<String, byte[]> records =
                    consumer.poll(Duration.ofMillis(500));

            for (ConsumerRecord<String, byte[]> record : records) {
                try {
                    OrderEvent event = decoder.decode(record.value());
                    process(event);
                }
                catch (InvalidPayloadException ex) {
                    publishToDeadLetter(record, ex);
                    // Chỉ đánh dấu hoàn tất sau khi DLT đã xác nhận.
                }
            }
            // Commit đồng bộ sau khi mọi record trong poll đã được xử lý
            // hoặc cách ly thành công theo chính sách ứng dụng.
            consumer.commitSync();
        }
    }

Ví dụ chỉ thể hiện ý tưởng. Trong ứng dụng thực tế, cần quản lý rebalance, partition assignment, commit offset theo từng partition và xử lý lỗi DLT. Nếu commitSync toàn bộ sau một poll, phải chắc chắn mọi record thuộc poll đã xử lý hoặc cách ly thành công; nếu một record thất bại giữa chừng, commit quá cao có thể bỏ qua record chưa xử lý.

Với Kafka client thuần và deserializer trực tiếp ném lỗi trong poll(), một số phiên bản client cung cấp RecordDeserializationException kèm topic-partition và offset. Có thể dùng thông tin đó để điều tra hoặc chủ động seek/commit theo chính sách. Tuy nhiên, bỏ qua offset lỗi sẽ làm mất record khỏi luồng xử lý thông thường; chỉ làm sau khi đã lưu byte gốc hoặc có quyết định nghiệp vụ rõ ràng. Đọc byte[] rồi giải mã trong ứng dụng thường giúp kiểm soát lỗi và bảo toàn payload dễ hơn.

## 7. Bảo toàn bản gốc và vận hành DLT

Một DLT hữu ích phải giữ đủ thông tin để điều tra và phát lại:

| Thông tin | Mục đích |
|---|---|
| Byte value gốc | Giải mã lại sau khi sửa serializer, schema hoặc parser |
| Key gốc | Giữ định danh và quy tắc partitioning nghiệp vụ |
| Topic, partition, offset nguồn | Truy vết về bản ghi ban đầu |
| Timestamp và headers nguồn | Khôi phục ngữ cảnh và correlation |
| Exception class và thông điệp lỗi | Phân loại nguyên nhân |
| Consumer group và thời điểm xử lý | Biết luồng consumer nào đã cách ly record |
| Event id/correlation id | Chống xử lý trùng khi replay |

Không ghi toàn bộ payload vào log ứng dụng nếu payload có dữ liệu cá nhân, bí mật hoặc thông tin thanh toán. Log nên chứa định danh, kích thước, hash và metadata cần thiết; byte gốc được giữ trong DLT với quyền truy cập và retention phù hợp.

Quy trình xử lý DLT:

1. Phân nhóm lỗi theo exception, topic nguồn, schema id và phiên bản producer.
2. Xác định nguyên nhân gốc: cấu hình, registry, schema evolution, byte hỏng hay dữ liệu độc hại.
3. Sửa deserializer/schema hoặc quy tắc validation và kiểm thử với bản ghi mẫu đã được kiểm soát.
4. Xác minh consumer mới đọc được record cũ và mới theo phạm vi retention.
5. Replay từ DLT về topic đích hoặc topic replay riêng, giữ event id và nguồn gốc.
6. Kiểm tra kết quả nghiệp vụ để bảo đảm replay không tạo tác dụng phụ trùng lặp.
7. Đóng DLT theo retention và chính sách lưu trữ sau khi xử lý xong.

Không tự động chuyển DLT về topic gốc ngay khi record vừa được ghi vào DLT. Nếu lỗi chưa được sửa, record sẽ quay lại và tạo vòng lặp vô hạn. Không replay đồng thời nhiều lần cùng một event nếu consumer đích chưa có idempotency.

## 8. Kiểm tra payload độc hại và giới hạn parser

Kafka không tự thực thi payload, nhưng ứng dụng có thể gọi parser hoặc deserializer trên dữ liệu không đáng tin cậy. Hãy coi mọi byte từ topic là input cần xác thực, kể cả topic nội bộ.

Các biện pháp cần cân nhắc:

- Giới hạn kích thước message ở producer, broker và consumer phù hợp với nghiệp vụ; không chỉ tăng giới hạn khi gặp record lớn bất thường.
- Đặt giới hạn độ sâu lồng nhau, số phần tử, độ dài chuỗi và kích thước collection của parser nếu thư viện hỗ trợ.
- Kiểm tra kiểu dữ liệu, trường bắt buộc, miền giá trị và version trước khi gọi business logic.
- Không dùng Java native deserialization cho payload không đáng tin cậy. Ưu tiên định dạng dữ liệu có schema và kiểu được kiểm soát.
- Không cho payload điều khiển class name hoặc kiểu Java tùy ý; cấu hình trusted packages cụ thể.
- Cập nhật parser và thư viện serializer/deserializer khi có bản vá bảo mật.
- Giới hạn quyền đọc DLT vì dữ liệu gốc có thể chứa thông tin nhạy cảm hoặc nội dung độc hại.
- Tránh ghi payload đầy đủ vào log, dashboard hoặc ticket hỗ trợ.

Nếu record quá lớn, xác định producer nào tạo ra nó, kích thước byte thực tế và giới hạn của từng tầng. Kafka có các giới hạn message/fetch khác nhau; tăng một giới hạn đơn lẻ không bảo đảm toàn bộ producer, broker và consumer đều có thể xử lý message đó.

## 9. Kịch bản chẩn đoán thực tế

**Tình huống A: consumer dừng tại một offset với lỗi JSON.** Ghi lại topic, partition và offset; lấy byte gốc bằng consumer đọc byte[] hoặc DLT; kiểm tra JSON và phiên bản producer. Nếu payload hỏng vĩnh viễn, cách ly record và xác nhận committed offset chỉ tiến sau khi DLT nhận thành công.

**Tình huống B: consumer mới không đọc được record cũ sau khi schema thay đổi.** Xác định schema id của record cũ, schema reader hiện tại và compatibility mode của subject. Kiểm thử đọc dữ liệu từ các schema còn nằm trong retention; sửa schema hoặc triển khai reader tương thích trước khi replay.

**Tình huống C: Schema Registry không truy cập được.** Kiểm tra DNS, TLS, credential, quyền subject và trạng thái registry. Nếu đây là lỗi tạm thời, retry có backoff; tránh kết luận payload sai hoặc chuyển hàng loạt record hợp lệ sang DLT trong thời gian registry gián đoạn.

**Tình huống D: một event làm parser tiêu thụ CPU hoặc bộ nhớ bất thường.** Cách ly record, giới hạn quyền truy cập byte gốc, kiểm tra kích thước và cấu trúc payload trong môi trường an toàn. Bổ sung giới hạn parser và validation trước khi phát lại.

## 10. Checklist phòng ngừa

- [ ] Producer và consumer thống nhất serializer/deserializer và wire format.
- [ ] Schema được kiểm tra compatibility trong CI trước khi đăng ký hoặc phát hành.
- [ ] Consumer mới đọc được các schema còn tồn tại trong thời hạn retention và replay.
- [ ] Có cảnh báo lỗi deserialization theo topic, partition và exception class.
- [ ] Spring Kafka dùng ErrorHandlingDeserializer khi cần chuyển lỗi deserialize tới container error handler.
- [ ] DLT giữ byte gốc, key, headers, source offset và thông tin exception.
- [ ] Producer DLT có thể serialize cả byte[] gốc và object hợp lệ nếu cùng dùng một template.
- [ ] Retry có giới hạn và phân biệt lỗi tạm thời với lỗi dữ liệu vĩnh viễn.
- [ ] Offset chỉ được commit sau khi xử lý hoặc cách ly record thành công.
- [ ] Replay giữ event id và có kiểm tra idempotency ở tầng nghiệp vụ.
- [ ] Parser có giới hạn kích thước và cấu trúc; không dùng Java native deserialization cho dữ liệu không tin cậy.
- [ ] Payload nhạy cảm không bị ghi nguyên văn vào log và DLT có quyền truy cập phù hợp.

Khi gặp lỗi deserialization, cần giữ lại bản ghi gốc và xác định chính xác lỗi phát sinh ở serializer, schema, parser hay validation. Một quy trình DLT và replay được kiểm soát giúp partition tiếp tục tiến, dữ liệu lỗi vẫn có thể điều tra, và việc khôi phục consumer không làm mất dấu hoặc nhân đôi tác dụng phụ nghiệp vụ.
