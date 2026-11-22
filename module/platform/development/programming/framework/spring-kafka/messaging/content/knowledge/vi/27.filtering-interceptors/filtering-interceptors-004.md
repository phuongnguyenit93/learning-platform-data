# Producer interceptor

Kafka `ProducerInterceptor` là một điểm mở rộng ở phía producer, cho phép quan sát hoặc điều chỉnh record ngay trước khi Kafka producer gửi đi và nhận thông báo khi lần gửi có kết quả. Trong Spring Kafka, interceptor được cấu hình trên Kafka `ProducerFactory`; vì vậy các producer do factory tạo, bao gồm producer được `KafkaTemplate` sử dụng, sẽ chạy interceptor.

Producer interceptor phù hợp cho các xử lý dùng chung như bổ sung header nguồn gửi, gắn metadata kỹ thuật, đo lường hoặc quan sát lỗi gửi. Nó không thay thế serializer, không quản lý retry nghiệp vụ và không phải cơ chế lọc record phía consumer.

## 1. ProducerInterceptor nằm ở đâu trong luồng gửi?

Khi ứng dụng gọi `KafkaTemplate.send(...)`, template lấy Kafka producer từ `ProducerFactory` rồi gọi API `KafkaProducer.send()`. Producer interceptor được gọi ở tầng Kafka client trước khi key/value được serialize thành byte và trước khi record được gửi tới broker.

```text
Application
    |
    v
KafkaTemplate.send(topic, key, value)
    |
    v
ProducerFactory lấy KafkaProducer
    |
    v
KafkaProducer.send(ProducerRecord)
    |
    v
ProducerInterceptor.onSend(record)
    |
    v
Serializer + partition selection
    |
    v
Kafka broker
    |
    v
Broker acknowledgement / send failure
    |
    v
ProducerInterceptor.onAcknowledgement(metadata, exception)
    |
    v
KafkaTemplate callback / CompletableFuture
```

`onSend()` nhìn thấy `ProducerRecord<K,V>` trước khi serializer chuyển key/value thành bytes. Nếu record chưa chỉ định partition, interceptor không thể biết chắc partition cuối cùng sẽ được chọn. Sau khi broker phản hồi, `onAcknowledgement()` nhận `RecordMetadata` với topic, partition, offset và exception nếu gửi thất bại.

## 2. Vòng đời của ProducerInterceptor

Kafka định nghĩa interface `org.apache.kafka.clients.producer.ProducerInterceptor<K,V>` với bốn phương thức:

| Phương thức | Khi nào được gọi | Mục đích |
| --- | --- | --- |
| `configure(Map<String, ?> configs)` | Khi Kafka client khởi tạo interceptor | Đọc cấu hình producer và cấu hình riêng của interceptor |
| `onSend(ProducerRecord<K,V> record)` | Khi ứng dụng gọi `send()` | Quan sát hoặc trả về record đã điều chỉnh trước khi serialize |
| `onAcknowledgement(RecordMetadata metadata, Exception exception)` | Khi lần gửi có kết quả thành công hoặc thất bại | Quan sát metadata broker hoặc lỗi gửi |
| `close()` | Khi producer đóng | Giải phóng tài nguyên interceptor đã tạo |

Kafka client khởi tạo interceptor từ danh sách class trong cấu hình `interceptor.classes`. Interceptor thường được tạo bởi Kafka client, không phải Spring container. Vì vậy không mặc định rằng có thể dùng constructor injection hoặc `@Autowired` như một Spring bean thông thường.

## 3. Ví dụ: thêm header nguồn gửi

Một ứng dụng có thể muốn mỗi record gửi ra đều có header `source-service` để phục vụ tracing hoặc điều tra. Thay vì lặp lại thao tác thêm header ở mọi nơi gọi `KafkaTemplate`, có thể dùng interceptor:

```java
package com.example.messaging.kafka;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerInterceptor;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.header.internals.RecordHeader;

public class SourceServiceProducerInterceptor
        implements ProducerInterceptor<String, String> {

    private volatile String sourceService = "unknown";

    @Override
    public void configure(Map<String, ?> configs) {
        Object configured = configs.get("app.producer.source-service");
        if (configured != null) {
            sourceService = configured.toString();
        }
    }

    @Override
    public ProducerRecord<String, String> onSend(
            ProducerRecord<String, String> record) {

        if (record.headers().lastHeader("source-service") == null) {
            record.headers().add(new RecordHeader(
                    "source-service",
                    sourceService.getBytes(StandardCharsets.UTF_8)));
        }

        return record;
    }

    @Override
    public void onAcknowledgement(
            RecordMetadata metadata,
            Exception exception) {
        // Ví dụ tối giản: chỉ quan sát kết quả, không chặn luồng I/O.
        if (exception != null) {
            System.err.println("Kafka send failed: " + exception.getMessage());
        }
        else if (metadata != null) {
            System.out.printf(
                    "Kafka record acknowledged: %s-%d offset=%d%n",
                    metadata.topic(), metadata.partition(), metadata.offset());
        }
    }

    @Override
    public void close() {
        // Đóng tài nguyên riêng nếu interceptor có tạo.
    }
}
```

Trong ví dụ, interceptor chỉ thêm header khi header chưa tồn tại. Cách kiểm tra này tránh tạo nhiều header `source-service` nếu record đã được gắn metadata từ phía gọi. Header Kafka lưu value dạng byte array; consumer cần giải mã UTF-8 khi đọc.

Đoạn `System.err`/`System.out` chỉ để minh họa callback. Ứng dụng thực tế nên dùng logger và metric không blocking, tránh ghi log đồng bộ quá nhiều trên luồng gửi/nhận.

## 4. Đăng ký interceptor bằng Spring Boot

Khai báo class interceptor trong producer properties:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      properties:
        "[interceptor.classes]": com.example.messaging.kafka.SourceServiceProducerInterceptor
        "[app.producer.source-service]": order-service
```

`interceptor.classes` là cấu hình Kafka producer. Có thể khai báo nhiều interceptor bằng danh sách class name phân tách theo cú pháp list mà Kafka client hỗ trợ. Các thuộc tính riêng như `app.producer.source-service` được truyền trong map cấu hình cho interceptor để đọc ở `configure()`.

Vì interceptor được Kafka client khởi tạo, class cần có constructor không tham số truy cập được. Nếu interceptor cần thông tin cấu hình, hãy truyền qua producer properties hoặc dùng một cơ chế cấu hình tĩnh phù hợp; không phụ thuộc vào Spring bean injection nếu chưa tự xây dựng adapter riêng.

Khi Spring Boot auto-configure `ProducerFactory`, cấu hình trên được đưa vào producer properties. `KafkaTemplate` dùng factory đó sẽ sử dụng interceptor tự động.

## 5. Đăng ký interceptor bằng ProducerFactory

Nếu tự tạo `DefaultKafkaProducerFactory`, thêm `ProducerConfig.INTERCEPTOR_CLASSES_CONFIG` vào map:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.INTERCEPTOR_CLASSES_CONFIG,
                List.of(SourceServiceProducerInterceptor.class.getName()));
        properties.put("app.producer.source-service", "order-service");

        return new DefaultKafkaProducerFactory<>(properties);
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Ví dụ minh họa cấu hình producer factory độc lập. Trong ứng dụng thực tế, bổ sung bảo mật, client ID, retry, idempotence, transaction và các thuộc tính môi trường cần thiết. Nếu producer factory được dùng cho nhiều `KafkaTemplate`, các template đó sẽ chia sẻ chính sách interceptor của factory.

## 6. Dùng interceptor để điều chỉnh record

`onSend()` có thể trả về record ban đầu hoặc một `ProducerRecord` mới. Ví dụ có thể thêm header, chuẩn hóa metadata hoặc thay đổi timestamp/key/value nếu thiết kế ứng dụng cho phép.

Khi tạo record mới, cần giữ lại các thuộc tính không muốn thay đổi như topic, partition, timestamp, key, value và headers. Thông thường chỉ nên chỉnh `record.headers()` rồi trả về record gốc để tránh vô tình làm mất metadata.

Một số use case phù hợp:

- Thêm `source-service`, `correlation-id` hoặc trace metadata mặc định.
- Gắn version của producer hoặc tên ứng dụng vào header.
- Đo số lần ứng dụng gọi `send()` và phân loại theo topic.
- Ghi nhận kết quả gửi thành công/thất bại ở mức kỹ thuật.
- Chuẩn hóa header kỹ thuật dùng chung cho nhiều producer trong cùng service.

Không nên dùng interceptor để thực hiện nghiệp vụ như cập nhật đơn hàng, trừ tiền, gọi HTTP hoặc ghi dữ liệu quan trọng vào database. Những thao tác đó cần nằm trong application service với transaction/retry/idempotency rõ ràng.

## 7. onSend và onAcknowledgement khác nhau thế nào?

Hai callback có thời điểm và thông tin khác nhau:

| Callback | Có thể biết | Không thể kết luận |
| --- | --- | --- |
| `onSend(record)` | Topic, partition được chỉ định nếu có, key, value, timestamp và headers trước serialize | Broker đã nhận record hay offset cuối cùng |
| `onAcknowledgement(metadata, exception)` | Kết quả gửi, metadata broker nếu thành công, exception nếu thất bại | Nghiệp vụ downstream đã xử lý record hay chưa |

`onSend()` không phải callback xác nhận broker. Không ghi metric “đã gửi thành công” tại đây; chỉ có thể ghi nhận ý định gửi hoặc số lần gọi API send.

`onAcknowledgement()` được gọi khi gửi có kết quả. Với record thành công, `RecordMetadata` cung cấp partition và offset thực tế. Với lỗi, kiểm tra `exception`; metadata có thể không có. Callback này không thay thế `KafkaTemplate` callback hoặc `CompletableFuture` mà application code dùng để quyết định nghiệp vụ tiếp theo.

## 8. Thứ tự và nhiều interceptor

Kafka producer cho phép cấu hình nhiều interceptor. Danh sách `interceptor.classes` xác định chuỗi interceptor của producer. Khi dùng nhiều interceptor, thứ tự rất quan trọng nếu một interceptor tạo header mà interceptor khác đọc hoặc thay đổi header đó.

Ví dụ:

```text
ProducerRecord
    |
    v
SourceHeaderInterceptor
    |
    v
CorrelationHeaderInterceptor
    |
    v
MetricsProducerInterceptor
    |
    v
Serializer / Kafka producer
```

Hãy giữ mỗi interceptor tập trung vào một trách nhiệm và kiểm thử thứ tự thực tế trong cấu hình. Tránh để nhiều interceptor cùng ghi một header nhưng dùng quy tắc khác nhau.

## 9. Thread safety và hiệu năng

Kafka producer thread-safe và có thể được gọi từ nhiều application thread. Interceptor instance được producer sử dụng cũng có thể nhận lời gọi đồng thời. Vì vậy:

- Không dùng field mutable không đồng bộ để lưu trạng thái theo từng record.
- Dùng cấu trúc thread-safe cho counter hoặc metric; ưu tiên Micrometer thay vì tự tăng biến `long` dùng chung.
- Không giữ payload/record vào collection không giới hạn.
- Không gọi database, HTTP hoặc thao tác I/O blocking trong `onSend()` hay `onAcknowledgement()`.
- Không chờ `Future.get()` hoặc chờ callback khác bên trong interceptor.
- Không tạo producer mới hoặc gọi `KafkaTemplate.send()` đệ quy từ interceptor.
- Giữ `close()` an toàn khi producer đóng.

`onSend()` chạy trên thread gọi producer send; `onAcknowledgement()` thường chạy trên producer I/O thread. Callback acknowledgement cần rất nhanh vì công việc blocking có thể làm chậm xử lý phản hồi của producer và ảnh hưởng throughput.

## 10. Exception bên trong interceptor

Interceptor không phải nơi phù hợp để từ chối record bằng cách ném exception. Kafka client bắt và ghi log exception phát sinh từ interceptor; exception đó không được truyền ngược như một lỗi send thông thường để application dựa vào.

Vì vậy:

- Validate dữ liệu nghiệp vụ trước khi gọi `KafkaTemplate.send()`.
- Dùng serializer để kiểm soát việc chuyển đổi payload.
- Dùng callback/future của `KafkaTemplate` để xử lý kết quả gửi.
- Chỉ dùng interceptor cho metadata và quan sát kỹ thuật có thể chịu được lỗi.

Nếu interceptor gặp lỗi khi thêm header, hãy ghi metric/log phù hợp và quyết định fallback an toàn. Không giả định ném exception từ `onSend()` sẽ hủy việc gửi record.

## 11. Interceptor trong transactional producer

Producer interceptor cũng được áp dụng khi Kafka producer được cấu hình transaction. `onSend()` chạy cho lần gọi send từ ứng dụng; việc producer tự retry batch ở tầng Kafka không đồng nghĩa interceptor được gọi lại cho mỗi lần retry nội bộ.

Nếu `KafkaTemplate` gửi trong transaction của listener container, interceptor có thể bổ sung header cho output record. Tuy nhiên, các side effect riêng của interceptor như ghi log, đẩy metric hoặc gọi hệ thống ngoài Kafka không nằm trong Kafka transaction. Transaction rollback không thể xóa một log đã ghi hoặc hoàn tác một HTTP call đã thực hiện.

Với luồng EOS, interceptor nên giữ vai trò kỹ thuật, không thực hiện nghiệp vụ cần atomicity. Nếu cần audit bền vững về event đã commit, hãy ghi nhận dựa trên kết quả commit hoặc thiết kế audit event/outbox phù hợp; không coi `onSend()` là bằng chứng transaction đã commit.

## 12. Phân biệt ProducerInterceptor, ProducerListener và consumer RecordInterceptor

Các API có tên gần nhau nhưng nằm ở các tầng khác nhau:

| Thành phần | Vị trí | Mục đích |
| --- | --- | --- |
| Kafka `ProducerInterceptor` | Kafka producer client | Quan sát/điều chỉnh `ProducerRecord` trước send và nhận acknowledgement |
| Spring Kafka `ProducerListener` | `KafkaTemplate` | Callback Spring khi gửi thành công hoặc thất bại |
| Spring Kafka `RecordInterceptor` | Consumer listener container | Quan sát hoặc điều chỉnh record trước khi gọi listener |
| `RecordFilterStrategy` | Consumer listener container | Lọc record không cần chuyển tới listener |

Nếu mục tiêu là thêm header trước khi gửi, dùng `ProducerInterceptor` hoặc tạo header trong application code. Nếu cần xử lý callback theo từng lệnh `KafkaTemplate.send()`, dùng `ProducerListener` hoặc future của send. Nếu muốn lọc record khi consumer nhận, dùng `RecordFilterStrategy`; producer interceptor không thực hiện vai trò đó.

## 13. Kiểm thử ProducerInterceptor

Nên kiểm thử riêng logic interceptor và kiểm thử tích hợp qua producer factory.

### Unit test cho onSend

Tạo `ProducerRecord`, gọi `configure()` với map cấu hình, sau đó gọi `onSend()` và xác minh header:

```java
package com.example.messaging.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;

class SourceServiceProducerInterceptorTest {

    @Test
    void addsSourceHeaderWhenMissing() {
        var interceptor = new SourceServiceProducerInterceptor();
        interceptor.configure(Map.of(
                "app.producer.source-service", "order-service"));

        var record = new ProducerRecord<>(
                "orders.created", "order-42", "payload");

        var result = interceptor.onSend(record);

        assertThat(result.headers().lastHeader("source-service").value())
                .isEqualTo("order-service".getBytes(StandardCharsets.UTF_8));
    }
}
```

Thêm test cho trường hợp header đã tồn tại để bảo đảm interceptor không ghi đè giá trị do caller cung cấp. Cũng nên kiểm tra cấu hình source bị thiếu, giá trị rỗng và record có nhiều header cùng tên nếu ứng dụng cho phép.

### Integration test

1. Tạo producer factory có đăng ký interceptor.
2. Gửi record qua `KafkaTemplate` đến topic kiểm thử.
3. Consume record từ broker và xác minh `source-service` header tồn tại với encoding đúng.
4. Xác minh interceptor nhận callback acknowledgement khi gửi thành công.
5. Mô phỏng broker/send failure để kiểm tra nhánh `exception` và bảo đảm callback không làm treo producer I/O thread.
6. Nếu có nhiều interceptor, xác minh thứ tự và kết quả header cuối cùng.

Không chỉ gọi trực tiếp `onSend()` rồi kết luận cấu hình Spring Boot đã đúng. Integration test xác minh class name, producer factory và Kafka client thực sự sử dụng interceptor.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Interceptor không được gọi | Chưa khai báo `interceptor.classes` trên producer factory đang dùng | Kiểm tra đúng `ProducerFactory` của `KafkaTemplate` |
| `@Autowired` trong interceptor là null | Kafka client tự khởi tạo class, không qua Spring bean lifecycle | Truyền cấu hình qua `configure()` hoặc thiết kế adapter riêng |
| Header bị lặp | Interceptor luôn thêm header mà không kiểm tra header cũ | Kiểm tra `lastHeader()` trước khi thêm |
| Header consumer đọc không đúng | Encoding byte không thống nhất | Dùng UTF-8 nhất quán và kiểm thử header bytes |
| Exception trong interceptor không làm send thất bại | Kafka client bắt/log exception interceptor | Validate trước send và dùng callback/future để xử lý lỗi |
| Throughput giảm mạnh | Callback thực hiện I/O blocking hoặc log quá nhiều | Dùng metric non-blocking và xử lý ngoài producer I/O thread |
| Counter sai khi chạy nhiều thread | Dùng mutable field không thread-safe | Dùng Micrometer hoặc `LongAdder` |
| Audit ghi nhận record chưa commit | Dùng `onSend()` như bằng chứng thành công | Ghi nhận trạng thái commit qua transaction-aware flow/outbox |
| Muốn lọc record consumer nhưng dùng producer interceptor | Chọn sai tầng mở rộng | Dùng `RecordFilterStrategy` hoặc consumer `RecordInterceptor` |

## 15. Checklist triển khai

- [ ] Interceptor có constructor không tham số và cấu hình qua `configure()`.
- [ ] Đã đăng ký class trong `interceptor.classes` của đúng producer factory.
- [ ] `onSend()` chỉ làm xử lý nhanh, không blocking.
- [ ] Header được thêm có điều kiện, không ghi đè metadata caller nếu không có chủ đích.
- [ ] Header value dùng encoding thống nhất.
- [ ] Interceptor thread-safe khi nhiều thread cùng gửi.
- [ ] `onAcknowledgement()` xử lý được cả success và failure, kể cả metadata không có.
- [ ] Không dùng exception interceptor để validate hoặc hủy send.
- [ ] Không đặt business side effect cần atomicity trong interceptor.
- [ ] Đã integration test qua `KafkaTemplate` và broker kiểm thử.

## 16. Kết luận

`ProducerInterceptor` là extension point của Kafka producer, được Spring Kafka sử dụng thông qua cấu hình trên `ProducerFactory`. `configure()` nhận cấu hình, `onSend()` quan sát hoặc điều chỉnh record trước khi serialize, `onAcknowledgement()` nhận kết quả gửi và `close()` giải phóng tài nguyên.

Hãy dùng producer interceptor cho metadata kỹ thuật, header chung, metric và quan sát gửi. Giữ callback ngắn, thread-safe, không blocking và không đặt nghiệp vụ quan trọng vào đó. Với Spring Kafka, cấu hình `interceptor.classes` trên đúng producer factory mà `KafkaTemplate` sử dụng; nếu cần callback theo từng lần gửi hãy cân nhắc `ProducerListener` hoặc future, còn lọc record phía consumer thuộc `RecordFilterStrategy`.

## Tài liệu tham khảo

- [Apache Kafka — ProducerInterceptor API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/ProducerInterceptor.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring for Apache Kafka — Filtering Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/filtering.html)
