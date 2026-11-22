# Xử lý dữ liệu không deserialize được

Kafka lưu record dưới dạng byte. Khi consumer đọc record, deserializer chuyển key và value từ byte thành kiểu dữ liệu mà ứng dụng hiểu được. Nếu payload không đúng định dạng, schema không tương thích hoặc cấu hình deserializer sai, bước chuyển đổi này có thể thất bại trước khi phương thức listener được gọi.

Một record lỗi kiểu này thường được gọi là **poison pill**: chỉ cần consumer gặp lại record đó, quá trình đọc có thể tiếp tục thất bại và làm chậm hoặc chặn tiến độ của partition. Ứng dụng cần nhận diện lỗi, giữ được dữ liệu gốc để điều tra, quyết định retry khi lỗi có khả năng phục hồi và chuyển record không thể xử lý sang dead-letter topic (DLT).

Bài học thuộc chương **Serialization** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách Spring Kafka xử lý lỗi deserialize, kết hợp ErrorHandlingDeserializer với error handler, lưu record lỗi vào DLT và xây dựng quy trình khôi phục an toàn.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vì sao lỗi deserialize xảy ra trước khi listener xử lý nghiệp vụ.
- Phân biệt lỗi deserialize với lỗi trong logic listener.
- Nhận diện poison pill và tác động tới consumer poll, offset và partition.
- Cấu hình ErrorHandlingDeserializer cho key và value.
- Kết hợp DefaultErrorHandler với DeadLetterPublishingRecoverer.
- Chọn retry hoặc DLT dựa trên khả năng phục hồi của nguyên nhân.
- Giữ raw bytes, key, header và metadata để điều tra record lỗi.
- Xử lý JSON type header, trusted packages và schema evolution.
- Kiểm thử lỗi deserialize, DLT và quy trình replay bằng broker thật.

## 1. Deserialize xảy ra ở đâu trong luồng consumer?

Producer serialize key và value thành byte trước khi gửi record tới Kafka. Broker lưu và chuyển tiếp byte; broker không cần biết payload là JSON, Avro hay một class Java cụ thể.

Khi consumer poll dữ liệu, Kafka client dùng deserializer đã cấu hình để chuyển byte thành object. Spring Kafka listener container sau đó chuyển record đã giải mã cho phương thức @KafkaListener.

~~~mermaid
flowchart LR
    P[Producer object] --> S[Serializer]
    S --> B[Kafka broker stores bytes]
    B --> C[Consumer poll]
    C --> D[Deserializer]
    D -->|Success| L["@KafkaListener"]
    D -->|Failure| E[Deserialization exception]
    E --> H[Error handling]
    H --> R[Retry or DLT]
~~~

Nếu deserializer ném exception trong lúc consumer poll, listener thường chưa nhận được record để tự bắt lỗi. Đây là khác biệt quan trọng so với lỗi nghiệp vụ phát sinh bên trong phương thức listener.

Nếu consumer không có cơ chế chuyển lỗi deserialize tới listener container, record lỗi có thể khiến poll thất bại lặp lại. Ứng dụng có thể không tiến tới các record tiếp theo của partition như mong đợi. Cách xử lý cần diễn ra đủ sớm để container biết record nào lỗi và có thể áp dụng retry hoặc recovery.

## 2. Những nguyên nhân thường gặp

Lỗi deserialize có thể xuất phát từ producer, hợp đồng dữ liệu, schema hoặc cấu hình consumer.

| Nguyên nhân | Ví dụ | Hướng kiểm tra |
|---|---|---|
| Payload sai định dạng | Consumer mong JSON nhưng nhận chuỗi hoặc byte không phải JSON | Kiểm tra serializer và payload thực tế. |
| JSON không hợp lệ | Thiếu dấu ngoặc, dấu phẩy sai hoặc payload bị cắt | Kiểm tra raw bytes và nguồn phát record. |
| Sai kiểu dữ liệu | Field amount là chuỗi nhưng DTO mong BigDecimal | So sánh JSON với event contract. |
| Thiếu hoặc đổi field | Producer đổi cấu trúc nhưng consumer chưa tương thích | Kiểm tra schema evolution và phiên bản producer. |
| Type header không khớp | Header chỉ tới class consumer không có hoặc không được phép | Kiểm tra type mapping và trusted packages. |
| Sai serializer/deserializer | Producer dùng Avro nhưng consumer dùng JsonDeserializer | Đồng bộ định dạng và cấu hình hai phía. |
| Schema Registry hoặc dịch vụ schema lỗi | Consumer không lấy được schema cần thiết | Kiểm tra kết nối, xác thực và trạng thái registry. |
| Dữ liệu cũ còn trong topic | Consumer mới đọc record được phát bởi phiên bản cũ | Kiểm tra compatibility và dữ liệu lịch sử. |
| Key deserialize lỗi | Key có encoding hoặc định dạng khác dự kiến | Kiểm tra key serializer và key deserializer. |

Không phải mọi lỗi deserialize đều có cùng khả năng phục hồi. JSON bị sai cấu trúc thường là lỗi xác định, retry cùng payload sẽ tiếp tục thất bại. Lỗi truy cập Schema Registry do timeout có thể là lỗi tạm thời và cần chính sách retry khác.

## 3. Phân biệt lỗi deserialize và lỗi nghiệp vụ

Hai loại lỗi này xảy ra ở các giai đoạn khác nhau nên cần cơ chế xử lý phù hợp.

| Tiêu chí | Lỗi deserialize | Lỗi nghiệp vụ trong listener |
|---|---|---|
| Thời điểm | Trong lúc consumer chuyển byte thành object | Sau khi listener nhận được record/object |
| Listener được gọi | Thường chưa được gọi với record lỗi | Đã được gọi |
| Ví dụ | JSON sai, schema không tương thích, sai type | Không đủ tồn kho, database tạm thời không truy cập được |
| Dữ liệu có thể dùng | Raw bytes, key, headers và thông tin exception | Object đã deserialize và context nghiệp vụ |
| Cơ chế xử lý | ErrorHandlingDeserializer và container error handler | DefaultErrorHandler, retry, recovery theo lỗi nghiệp vụ |
| Khả năng retry | Tùy nguyên nhân; payload sai thường không retry được | Lỗi phụ thuộc dịch vụ có thể phục hồi sau retry |

Không nên bắt mọi lỗi vào cùng một chính sách retry. Nếu payload sai định dạng, retry nhiều lần chỉ làm tăng thời gian xử lý và lag. Nếu Schema Registry tạm thời không truy cập được, chuyển record sang DLT ngay có thể làm tăng lượng record cần replay không cần thiết.

## 4. ErrorHandlingDeserializer giải quyết vấn đề gì?

Spring Kafka cung cấp **ErrorHandlingDeserializer** để bọc deserializer thực tế. Nó gọi delegate deserializer để giải mã dữ liệu. Nếu delegate ném exception, ErrorHandlingDeserializer giữ thông tin lỗi và dữ liệu gốc trong header của record, rồi trả về giá trị null cho phần key hoặc value bị lỗi.

Listener container có thể phát hiện header lỗi deserialize và chuyển record tới error handler. Nhờ đó, ứng dụng có thể áp dụng retry hoặc recover record thay vì để lỗi chỉ xuất hiện bên trong poll.

Cấu trúc:

~~~mermaid
flowchart TD
    K[Kafka record bytes] --> E[ErrorHandlingDeserializer]
    E --> D[Delegate deserializer]
    D -->|Success| V[Decoded key/value]
    D -->|Failure| X[Store exception and raw bytes in header]
    X --> N[Return null for failed field]
    N --> C[Spring listener container detects failure]
    C --> H[Common error handler]
    H --> R[Retry or Dead-letter recoverer]
~~~

ErrorHandlingDeserializer không tự sửa payload và cũng không tự quyết định record nên được bỏ qua hay gửi DLT. Nó cung cấp thông tin cần thiết để listener container và error handler xử lý lỗi có kiểm soát.

Nếu chỉ dùng JsonDeserializer trực tiếp và deserialize thất bại trong poll, container có thể không có record đã giải mã để chuyển cho error handler theo cách thông thường. Vì vậy, khi cần xử lý poison pill bằng Spring Kafka error handler, hãy cấu hình ErrorHandlingDeserializer làm lớp ngoài.

## 5. Cấu hình ErrorHandlingDeserializer trong Spring Boot

Ví dụ consumer dùng String key và JSON value:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreatedEvent
        spring.json.trusted.packages: com.example.events
        spring.json.use.type.headers: false
~~~

Giải thích:

- ErrorHandlingDeserializer là deserializer được Kafka client gọi trực tiếp.
- spring.deserializer.key.delegate.class chỉ định deserializer thực tế cho key.
- spring.deserializer.value.delegate.class chỉ định JsonDeserializer cho value.
- spring.json.value.default.type khai báo kiểu mặc định khi không dùng type header.
- spring.json.trusted.packages giới hạn package được phép deserialize.
- spring.json.use.type.headers=false yêu cầu consumer dùng kiểu mặc định thay vì lấy kiểu từ header.

Các thuộc tính delegate và JsonDeserializer được truyền qua consumer properties. Tên property và khả năng binding cần được đối chiếu với phiên bản Spring Kafka/Spring Boot của dự án.

Nếu ứng dụng dùng type header để hỗ trợ nhiều loại event, có thể cấu hình type mapping thay vì tắt header. Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.events
        spring.json.type.mapping: orderCreated:com.example.events.OrderCreatedEvent
        spring.json.use.type.headers: true
~~~

Producer và consumer cần thống nhất type mapping. Không mở trusted packages quá rộng chỉ để làm mất lỗi cấu hình; chỉ tin cậy package chứa các kiểu dữ liệu thực sự được phép deserialize.

## 6. Kết hợp DefaultErrorHandler và DeadLetterPublishingRecoverer

Sau khi ErrorHandlingDeserializer chuyển lỗi thành thông tin mà container nhận biết được, Spring Kafka có thể dùng DefaultErrorHandler để quyết định retry hoặc recover.

DeadLetterPublishingRecoverer là thành phần phổ biến để publish record lỗi sang một topic khác, thường có hậu tố .DLT.

Ví dụ cấu hình:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
            )
    );
}

@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    // Không retry payload lỗi xác định; chuyển sang recoverer ngay.
    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(0L, 0L)
    );
}
~~~

Gắn error handler vào listener container factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Dòng cuối cần được đặt trong cấu hình bean factory thực tế của ứng dụng. Nếu dùng Spring Boot auto-configuration, hãy bảo đảm factory mà @KafkaListener đang sử dụng thực sự nhận common error handler này.

Trong ví dụ, FixedBackOff với số retry bằng 0 phù hợp để minh họa payload lỗi xác định được chuyển sang recoverer mà không retry. Với lỗi tạm thời, hãy phân loại exception và dùng backoff phù hợp. Không áp dụng một chính sách duy nhất cho mọi nguyên nhân.

DefaultErrorHandler có phân loại một số exception được xem là fatal/non-retryable theo mặc định, trong đó có lỗi deserialize của Spring Kafka. Hành vi phân loại chi tiết có thể thay đổi theo phiên bản; nếu cần retry một lỗi đặc biệt, hãy cấu hình classifier có chủ đích và kiểm thử nguyên nhân gốc.

## 7. DLT cần giữ được raw bytes

Một điểm quan trọng khi xử lý lỗi deserialize là value gốc có thể chưa bao giờ trở thành object Java. ErrorHandlingDeserializer lưu dữ liệu gốc trong DeserializationException để framework có thể phục hồi và publish record lỗi.

DLT producer phải serialize được cả:

- Object bình thường của record đã deserialize thành công nhưng lỗi ở bước xử lý sau đó.
- byte[] gốc của record không deserialize được.

Nếu DLT KafkaTemplate chỉ dùng JsonSerializer hoặc serializer chỉ hiểu một DTO cụ thể, việc publish raw byte[] có thể thất bại hoặc làm thay đổi nội dung gốc. Hãy cấu hình serializer có thể xử lý cả byte[] và các kiểu object hợp lệ, ví dụ dùng DelegatingByTypeSerializer hoặc một DLT template riêng cho raw bytes.

Khi thiết kế DLT, cần xác minh:

- Key gốc có được giữ nguyên hay không.
- Value gốc có còn đúng byte sequence hay không.
- Header lỗi deserialize được giữ lại để điều tra.
- Metadata nguồn như topic, partition, offset được đính kèm.
- Serializer DLT xử lý đúng cả byte[] và object thông thường.
- DLT topic tồn tại và có đủ partition cho chiến lược định tuyến.

Trong ví dụ resolver ở phần trước, record được chuyển tới cùng số partition của topic gốc. Vì vậy DLT cần có số partition ít nhất bằng topic nguồn. Nếu muốn dùng một partition DLT tập trung hoặc một topic DLT riêng cho mỗi loại lỗi, hãy thay destination resolver cho phù hợp.

## 8. Thông tin nào cần giữ trong dead-letter record?

Một DLT hữu ích phải cho phép xác định record đến từ đâu, vì sao lỗi và cách khôi phục.

Các thông tin nên giữ:

| Thông tin | Mục đích |
|---|---|
| Original topic | Xác định luồng dữ liệu nguồn. |
| Original partition | Xác định partition nguồn. |
| Original offset | Tìm đúng record trong log nguồn. |
| Original key/value bytes | Điều tra payload và thử deserialize lại. |
| Exception class/message | Phân loại nguyên nhân lỗi. |
| Stack trace | Hỗ trợ điều tra lỗi phức tạp. |
| Timestamp | Xác định thời điểm record được tạo hoặc ghi. |
| Correlation ID/event ID | Liên kết log giữa producer, consumer và downstream. |

Spring Kafka bổ sung các DLT headers chứa metadata nguồn và thông tin exception. Hãy dùng các hằng số KafkaHeaders tương ứng theo phiên bản Spring Kafka thay vì tự viết tên header rải rác trong ứng dụng.

DLT có thể chứa dữ liệu nhạy cảm giống topic nguồn. Áp dụng ACL, retention, mã hóa và chính sách truy cập phù hợp. Không gửi raw payload hoặc stack trace chứa thông tin nhạy cảm vào log công khai.

## 9. Phân loại lỗi để quyết định retry hay DLT

Quyết định retry cần dựa vào nguyên nhân, không chỉ dựa vào việc exception xảy ra trong deserializer.

| Nguyên nhân | Khả năng phục hồi | Hướng xử lý |
|---|---|---|
| JSON sai cấu trúc | Thấp nếu payload không thay đổi | Không retry hoặc retry rất hạn chế; chuyển DLT. |
| Sai kiểu dữ liệu hoặc field contract | Thấp nếu consumer và payload không đổi | DLT, sửa contract hoặc consumer rồi replay. |
| Type header trỏ tới class không tồn tại | Thấp cho tới khi sửa mapping/deployment | DLT hoặc tạm dừng luồng để sửa cấu hình. |
| Payload không được trusted package cho phép | Thấp nếu cấu hình không đổi | Sửa allowlist có kiểm soát rồi replay. |
| Schema Registry tạm thời mất kết nối | Có thể phục hồi | Retry có backoff và giới hạn thời gian nếu phân loại được lỗi tạm thời. |
| Schema không tương thích | Thường không tự phục hồi | DLT, điều chỉnh schema/consumer và replay. |
| Lỗi database trong listener sau deserialize | Có thể phục hồi tùy nguyên nhân | Retry theo error handler nghiệp vụ, không coi là lỗi deserialize. |

Không nên retry vô hạn poison pill. Một record sai định dạng không tự trở nên hợp lệ sau vài giây; retry liên tục chỉ giữ partition bận và làm tăng lag.

Ngược lại, nếu nguyên nhân là dịch vụ schema tạm thời không truy cập được, chuyển ngay tất cả record sang DLT có thể khiến lượng dữ liệu cần replay tăng nhanh. Cần phân loại nguyên nhân gốc và kiểm soát thời gian retry.

## 10. Key deserialize cũng có thể thất bại

Nhiều ví dụ chỉ chú ý value, nhưng key cũng là byte và có deserializer riêng. Nếu key sai encoding hoặc producer thay đổi định dạng key, consumer có thể gặp lỗi trước khi listener nhận record.

ErrorHandlingDeserializer cần được cấu hình cho cả key và value nếu cả hai có khả năng lỗi. Khi key deserialize thất bại, key trong ConsumerRecord có thể là null trong khi thông tin lỗi và raw key bytes được giữ trong header tương ứng.

Khi điều tra, hãy phân biệt:

- Value deserialize thất bại.
- Key deserialize thất bại.
- Cả key và value đều lỗi.
- Key null hợp lệ theo hợp đồng producer.

Không được coi mọi key null là lỗi. Nếu hệ thống cho phép key null, cần dùng exception header để xác định key null do deserialize thất bại hay là giá trị null hợp lệ.

## 11. Batch listener và record lỗi

Với record listener, container có thể chuyển record lỗi tới error handler theo cơ chế xử lý lỗi của nó. Với batch listener, một lần gọi phương thức có thể nhận nhiều record từ poll; nếu một record lỗi deserialize, container phải xác định và xử lý phần record lỗi theo thông tin exception header và chính sách batch error handling.

Nếu batch listener gặp lỗi nghiệp vụ trong một record, có thể dùng BatchListenerFailedException để chỉ rõ record hoặc index thất bại. Điều này giúp error handler phân biệt phần batch đã xử lý với phần cần retry/recover.

Không nên bắt exception deserialize bằng cách kiểm tra value == null rồi mặc định coi đó là poison pill. Null có thể là giá trị hợp lệ nếu hợp đồng producer cho phép. Hãy kiểm tra deserialization exception header để phân biệt chính xác.

Nếu batch listener tự xử lý danh sách, cần thiết kế rõ cách ghi nhận partial success. Khi một phần batch đã tạo side effect nhưng phần sau thất bại, record được giao lại có thể lặp tác động. Dùng eventId và idempotency để bảo vệ nghiệp vụ.

## 12. Sửa nguyên nhân và replay record từ DLT

DLT không phải nơi lưu lỗi vô thời hạn mà không có quy trình. Một luồng recovery nên có các bước:

1. Phân loại record lỗi theo exception, source topic và phiên bản event.
2. Xác định lỗi do payload, schema, type mapping, serializer hay cấu hình.
3. Sửa producer contract hoặc consumer deserializer.
4. Viết test với raw bytes thực tế của record lỗi.
5. Chọn record có thể replay và xác định side effect sẽ xảy ra.
6. Replay sang topic nguồn hoặc topic recovery theo quy trình kiểm soát.
7. Dùng eventId/idempotency để tránh tác động trùng.
8. Theo dõi kết quả và ghi nhận record đã được khôi phục.

Có thể tạo một recovery consumer đọc DLT dưới dạng byte[] để phân tích payload trước khi deserialize lại. Cách này đặc biệt hữu ích khi class hoặc schema gốc không còn tương thích với ứng dụng hiện tại.

Không replay toàn bộ DLT vào production ngay sau khi sửa một lỗi. Hãy thử một nhóm nhỏ, xác minh schema, ordering và side effect, sau đó mới mở rộng.

## 13. Kiểm thử lỗi deserialize và DLT

Unit test có thể kiểm tra logic phân loại lỗi hoặc callback, nhưng để xác minh ErrorHandlingDeserializer và container error handler, cần integration test với broker.

Các tình huống nên có:

| Test | Điều cần xác minh |
|---|---|
| JSON hợp lệ | Delegate deserialize thành object đúng. |
| JSON sai định dạng | ErrorHandlingDeserializer giữ exception và raw bytes. |
| Type header không hợp lệ | Consumer xử lý lỗi mapping theo chính sách. |
| Key sai encoding | Lỗi key được phân biệt với key null hợp lệ. |
| Value schema không tương thích | Record được retry hoặc recover theo classifier. |
| DLT publish | Record lỗi tới đúng topic/partition DLT. |
| Raw bytes preservation | Value trong DLT giữ đúng byte gốc. |
| DLT headers | Có original topic, partition, offset và exception details. |
| Retry limit | Số lần retry đúng với backoff đã cấu hình. |
| Replay | Record đã sửa có thể được đọc lại và xử lý idempotent. |

Ví dụ tạo payload sai định dạng trong integration test:

~~~java
ProducerRecord<String, byte[]> badRecord =
        new ProducerRecord<>(
                "orders.raw",
                "order-1001",
                "{invalid-json".getBytes(StandardCharsets.UTF_8)
        );

KafkaTemplate<String, byte[]> rawProducer =
        rawBytesKafkaTemplate;

rawProducer.send(badRecord).get(10, TimeUnit.SECONDS);
~~~

Producer test dùng ByteArraySerializer để gửi raw bytes, không serialize lại chuỗi thành JSON. Consumer test dùng ErrorHandlingDeserializer bọc JsonDeserializer. Sau khi error handler recover, test đọc DLT bằng ByteArrayDeserializer và so sánh byte array với payload đã gửi.

Để kiểm tra không bị treo, dùng Awaitility hoặc polling có timeout để chờ DLT nhận record. Không dùng Thread.sleep cố định để đoán thời điểm recover hoàn tất.

## 14. Quan sát và vận hành poison pill

Một poison pill có thể làm consumer lag tăng dù broker vẫn khỏe. Cần quan sát riêng lỗi deserialize và lỗi nghiệp vụ.

Các metric nên có:

- Số lỗi deserialize theo topic và loại exception.
- Số record được retry.
- Số record được recover vào DLT.
- Số lần DLT publish thất bại.
- Consumer lag theo partition.
- Số record replay thành công/thất bại.
- Thời gian từ lúc phát hiện lỗi tới lúc recovery hoàn tất.

Log cần có topic, partition, offset, eventId nếu đọc được từ key/header, exception class và source metadata. Nếu value không deserialize được, eventId có thể không lấy được từ payload; nên cân nhắc đặt correlation ID ở Kafka header để vẫn truy vết được.

Cần cảnh báo khi:

- Tỷ lệ deserialize failure tăng đột ngột.
- Một partition có cùng lỗi lặp lại.
- DLT publish thất bại.
- DLT backlog tăng mà chưa có owner xử lý.
- Một phiên bản producer phát schema không tương thích.
- Consumer group lag tăng dù CPU và broker load bình thường.

DLT cần có owner, retention, ACL, dashboard và quy trình xử lý. Nếu không, DLT chỉ chuyển vấn đề ra khỏi luồng chính nhưng không khôi phục được dữ liệu nghiệp vụ.

## 15. Checklist cấu hình an toàn

Trước khi triển khai consumer xử lý dữ liệu không deserialize được, hãy xác nhận:

- Key/value deserializer được bọc bởi ErrorHandlingDeserializer ở nơi cần bắt lỗi.
- Delegate deserializer đúng với serializer của producer.
- JSON type header hoặc default type được cấu hình nhất quán.
- Trusted packages được giới hạn theo model hợp lệ.
- DefaultErrorHandler được gắn vào đúng listener container factory.
- Lỗi xác định không retry vô hạn.
- Lỗi tạm thời có backoff và retry limit rõ ràng.
- DeadLetterPublishingRecoverer định tuyến đúng topic/partition.
- DLT serializer hỗ trợ raw byte[] và object nếu cần.
- DLT có đủ partition cho resolver đang dùng.
- DLT headers và raw bytes được giữ để điều tra.
- ACL, retention và dữ liệu nhạy cảm được quản lý phù hợp.
- Có test cho lỗi key, value, type header, DLT và replay.
- Có dashboard và owner xử lý DLT.

## 16. Bài tập tổng hợp: xử lý poison pill trong orders.created

Hãy xây dựng consumer cho topic orders.created, dùng JSON deserializer và ErrorHandlingDeserializer.

Yêu cầu:

1. Cấu hình key và value deserializer với ErrorHandlingDeserializer.
2. Gửi một event JSON hợp lệ và xác minh listener nhận đúng OrderCreatedEvent.
3. Gửi raw bytes chứa JSON sai định dạng.
4. Xác minh listener không xử lý payload lỗi như một event hợp lệ.
5. Cấu hình DefaultErrorHandler và DeadLetterPublishingRecoverer.
6. Định tuyến record lỗi tới orders.created.DLT.
7. Đọc DLT dưới dạng byte[] và so sánh payload gốc.
8. Kiểm tra DLT headers có topic, partition, offset và exception.
9. Gửi một event có type header sai để kiểm tra type mapping.
10. Mô phỏng lỗi schema service tạm thời và phân biệt với payload hỏng cố định.
11. Sửa dữ liệu hoặc schema rồi replay một record DLT trong môi trường test.
12. Xác minh replay không lặp side effect nhờ eventId/idempotency.
13. Theo dõi consumer lag, retry count và DLT backlog.
14. Viết runbook xử lý poison pill cho đội vận hành.

Bài tập hoàn thành khi bạn có thể chuyển record không deserialize được ra khỏi luồng chính mà vẫn giữ raw bytes và metadata, phân biệt lỗi có thể retry với lỗi phải DLT, rồi replay có kiểm soát sau khi sửa nguyên nhân.

## 17. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Deserialize flow | Serializer, bytes và deserializer | Mô tả được lỗi xảy ra trước listener. |
| 2. Error types | Payload, schema, type, key/value | Phân loại được nguyên nhân và khả năng phục hồi. |
| 3. ErrorHandlingDeserializer | Delegate và exception headers | Container nhận diện được record lỗi. |
| 4. Error handler | DefaultErrorHandler và retry | Cấu hình retry có giới hạn theo nguyên nhân. |
| 5. DLT | DeadLetterPublishingRecoverer | Publish được record lỗi và giữ raw bytes. |
| 6. Schema | JSON type headers, schema evolution | Consumer đọc được dữ liệu tương thích. |
| 7. Recovery | DLT replay và idempotency | Khôi phục record mà không lặp side effect. |
| 8. Testing | Raw bytes, headers, DLT integration test | Xác minh được cả payload và metadata nguồn. |
| 9. Operations | Metrics, ACL, retention, runbook | Theo dõi và xử lý được backlog DLT. |

Bài học hoàn thành khi bạn có thể cấu hình ErrorHandlingDeserializer, kết nối error handler với DLT, giữ lại raw bytes và metadata, đồng thời quyết định đúng lúc nào retry và lúc nào recover. Mục tiêu là để một record hỏng không làm luồng consumer mất kiểm soát, trong khi dữ liệu lỗi vẫn có thể được điều tra và khôi phục.

Kafka broker lưu byte; producer và consumer phải thống nhất hợp đồng serialization. Khi hợp đồng bị phá vỡ, hãy giữ nguyên dữ liệu gốc, xác định nguyên nhân, áp dụng retry có chọn lọc và dùng DLT như một phần của quy trình recovery có owner.
