# Thêm metadata hoặc trace context

Kafka record có thể mang metadata bên cạnh key và payload thông qua **headers**. Ứng dụng thường dùng headers để truyền `correlation-id`, loại sự kiện, phiên bản schema, tenant hoặc trace context giữa producer và consumer. Spring Kafka còn cung cấp `ProducerInterceptor`, `RecordInterceptor`, `KafkaHeaderMapper` và Micrometer Observation để chuẩn hóa việc bổ sung, đọc và quan sát metadata trong luồng messaging.

Điều quan trọng là phân biệt metadata nghiệp vụ với trace context. `correlation-id` giúp liên kết các thao tác thuộc cùng một yêu cầu nghiệp vụ; `traceparent` và `tracestate` mang thông tin theo chuẩn distributed tracing. Có thể dùng cả hai trên cùng record, nhưng không nên tự dùng một giá trị thay thế cho giá trị còn lại.

## 1. Kafka headers lưu trữ dữ liệu như thế nào?

Một Kafka record gồm topic, partition, offset, key, value, timestamp và headers. Mỗi header có tên cùng giá trị kiểu `byte[]`. Một record có thể chứa nhiều header cùng tên, vì vậy khi đọc cần xác định rõ muốn lấy giá trị đầu tiên, cuối cùng hay tất cả giá trị.

Ví dụ một sự kiện đơn hàng:

```text
Topic: order-events
Key:   order-42
Value: { "orderId": "order-42", "status": "CONFIRMED" }
Headers:
  event-type       = OrderConfirmed
  schema-version   = 2
  correlation-id   = req-8f31
  tenant-id        = tenant-17
  traceparent      = 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Headers phù hợp với thông tin bổ trợ để định tuyến, truy vết, tương thích schema hoặc xử lý xuyên suốt nhiều service. Payload nên chứa dữ liệu nghiệp vụ chính. Key thường dùng để xác định partition và giữ thứ tự theo thực thể; không nên nhét toàn bộ metadata vào key vì việc đó ảnh hưởng partitioning.

Một số tên metadata thường gặp:

| Header | Mục đích | Ví dụ |
|---|---|---|
| `correlation-id` | Liên kết các thao tác của cùng yêu cầu nghiệp vụ | `req-8f31` |
| `event-type` | Nhận biết loại sự kiện | `OrderConfirmed` |
| `schema-version` | Xác định phiên bản cấu trúc payload | `2` |
| `tenant-id` | Phân biệt tenant trong ứng dụng multi-tenant | `tenant-17` |
| `traceparent` | Mang trace context theo W3C Trace Context | `00-...-...-01` |
| `tracestate` | Mang trạng thái mở rộng của nhà cung cấp tracing | `vendor=value` |

Header không được Kafka tự động mã hóa thành String hay JSON. Ứng dụng phải thống nhất cách mã hóa giữa producer và consumer; cách phổ biến cho metadata văn bản là UTF-8.

## 2. Thêm metadata khi gửi bằng KafkaTemplate

Khi cần thêm metadata theo từng sự kiện, cách trực tiếp nhất là tạo `ProducerRecord`, thêm header rồi gửi bằng `KafkaTemplate`:

```java
ProducerRecord<String, OrderConfirmed> record =
        new ProducerRecord<>("order-events", event.orderId(), event);

record.headers()
        .add("event-type", "OrderConfirmed".getBytes(StandardCharsets.UTF_8))
        .add("schema-version", "2".getBytes(StandardCharsets.UTF_8))
        .add("correlation-id", correlationId.getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

Producer gửi các giá trị header dưới dạng byte. Serializer của key và value vẫn hoạt động riêng; serializer JSON của payload không tự động quyết định định dạng của header.

Nếu ứng dụng đã dùng Spring Messaging `Message`, có thể thêm metadata bằng `MessageBuilder`:

```java
Message<OrderConfirmed> message = MessageBuilder
        .withPayload(event)
        .setHeader("event-type", "OrderConfirmed")
        .setHeader("schema-version", "2")
        .setHeader("correlation-id", correlationId)
        .build();

kafkaTemplate.send(message);
```

Ở cách này, `KafkaHeaderMapper` của converter chịu trách nhiệm ánh xạ `MessageHeaders` sang Kafka headers. Cách gửi bằng `ProducerRecord` hữu ích khi cần kiểm soát chính xác byte hoặc khi giao tiếp với consumer không dùng Spring.

## 3. Đọc metadata ở consumer

Khi nhận `ConsumerRecord`, đọc header theo tên. Vì header có thể không tồn tại hoặc có nhiều giá trị, hãy xử lý trường hợp thiếu và chọn cách đọc phù hợp:

```java
@KafkaListener(topics = "order-events", groupId = "order-projection")
public void consume(ConsumerRecord<String, OrderConfirmed> record) {
    Header header = record.headers().lastHeader("correlation-id");

    String correlationId = header == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);

    orderProjection.update(record.value(), correlationId);
}
```

`lastHeader()` trả về header cuối cùng có tên tương ứng. Nếu hợp đồng cho phép nhiều giá trị cùng tên, dùng `headers().headers(name)` để duyệt toàn bộ thay vì âm thầm lấy một giá trị.

Spring Kafka cũng đưa metadata của record vào các header dành riêng như `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION`, `KafkaHeaders.OFFSET`, `KafkaHeaders.RECEIVED_TIMESTAMP` và `KafkaHeaders.RECEIVED_KEY`. Có thể lấy chúng bằng `@Header` trong listener hoặc nhận `ConsumerRecordMetadata`. Đây là metadata do framework ánh xạ từ record Kafka; chúng khác với custom header do ứng dụng tự thêm.

Ví dụ nhận metadata qua annotation:

```java
@KafkaListener(topics = "order-events")
public void consume(
        OrderConfirmed event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info("Received order event from {}-{} at offset {}",
            topic, partition, offset);
    orderProjection.update(event);
}
```

## 4. KafkaHeaderMapper và tương thích giữa các service

Khi dùng `Message<?>`, Spring Kafka sử dụng `KafkaHeaderMapper` để chuyển đổi giữa `MessageHeaders` và native Kafka `Headers`. Có hai mapper phổ biến:

- `SimpleKafkaHeaderMapper` giữ giá trị ở dạng `byte[]`; có thể cấu hình chuyển đổi String theo charset. Đây là lựa chọn dễ dự đoán khi trao đổi với ứng dụng không dùng Spring.
- `JsonKafkaHeaderMapper` hỗ trợ header có kiểu dữ liệu phong phú. Mapper ghi thêm header `spring_json_header_types` để mô tả kiểu cần khôi phục khi nhận.

Ví dụ cấu hình mapper:

```java
@Bean
MessagingMessageConverter kafkaMessageConverter() {
    MessagingMessageConverter converter = new MessagingMessageConverter();
    JsonKafkaHeaderMapper mapper = new JsonKafkaHeaderMapper();
    mapper.setRawMappedHeaders(Map.of("correlation-id", true, "event-type", true));
    converter.setHeaderMapper(mapper);
    return converter;
}
```

Đặt converter này làm converter cho `KafkaTemplate` và listener container nếu ứng dụng tự cấu hình chúng; trong Spring Boot, converter bean phù hợp có thể được dùng bởi auto-configuration. Với `rawMappedHeaders`, các String có tên được cấu hình sẽ được ánh xạ thành byte theo charset thay vì JSON encode. Ở chiều nhận, giá trị byte tương ứng có thể được chuyển lại thành String. Cách này hữu ích khi các service cần trao đổi header văn bản theo định dạng đơn giản.

`JsonKafkaHeaderMapper` chỉ tin cậy một số package mặc định khi deserialize header có kiểu. Nếu cần hỗ trợ kiểu riêng, chỉ thêm đúng package cần thiết bằng `addTrustedPackages()`. Không cấu hình `*` cho nguồn dữ liệu không đáng tin cậy vì điều đó cho phép deserialize kiểu bất kỳ có trên classpath. Khi trao đổi với hệ thống đa ngôn ngữ, nên ưu tiên String hoặc byte có schema rõ ràng thay vì gửi object Java trong header.

## 5. Dùng interceptor ở đúng vị trí

Interceptor phù hợp cho hành vi xuyên suốt nhiều record như bổ sung metadata mặc định, kiểm tra header bắt buộc, ghi dấu vết xử lý hoặc thu thập thông tin. Có hai vị trí chính:

| Loại | Chạy ở đâu | Trường hợp phù hợp |
|---|---|---|
| `ProducerInterceptor` của Kafka client | Trên producer khi gửi và khi nhận acknowledgement | Chính sách chung cho nhiều lần gửi từ cùng producer |
| `RecordInterceptor` của Spring Kafka | Trong listener container, trước listener và có callback sau khi listener thành công/thất bại | Kiểm tra hoặc quan sát record tại một listener cụ thể |

`ProducerInterceptor` thuộc Kafka client, không do Spring quản lý. Vì vậy, Spring dependency injection không tự hoạt động trong interceptor này. Nếu cần truyền dependency, phải cấu hình qua map trong `configure()` hoặc cơ chế khởi tạo riêng. Callback `onSend()` nằm trên đường gửi, nên xử lý thật nhanh, không chờ I/O và không gọi ngược Kafka producer.

Ví dụ bổ sung metadata tĩnh `source-service` cho mọi record đi qua một producer:

```java
public class SourceServiceProducerInterceptor
        implements ProducerInterceptor<String, OrderConfirmed> {

    @Override
    public ProducerRecord<String, OrderConfirmed> onSend(
            ProducerRecord<String, OrderConfirmed> record) {

        if (record.headers().lastHeader("source-service") == null) {
            record.headers().add(
                    "source-service",
                    "order-service".getBytes(StandardCharsets.UTF_8));
        }
        return record;
    }

    @Override
    public void onAcknowledgement(RecordMetadata metadata, Exception exception) {
        // Chỉ ghi nhận kết quả gửi; không thực hiện I/O đồng bộ ở đây.
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
```

Đăng ký interceptor trong producer properties bằng `ProducerConfig.INTERCEPTOR_CLASSES_CONFIG`. Metadata theo từng yêu cầu như `correlation-id` vẫn nên được thêm ở nơi tạo `ProducerRecord`, vì interceptor dùng chung không biết ngữ cảnh nghiệp vụ của từng lần gửi.

`RecordInterceptor` được gọi trước listener. Nếu trả về `null`, listener sẽ bị bỏ qua. Từ Spring Kafka 2.7, interceptor có callback khi listener thành công hoặc ném exception; có thể dùng chúng để ghi nhận kết quả. Nếu mục tiêu duy nhất là lọc record theo điều kiện nghiệp vụ, `RecordFilterStrategy` thể hiện ý định rõ hơn.

Ví dụ đăng ký `RecordInterceptor` để kiểm tra correlation ID và ghi nhận kết quả:

```java
factory.setRecordInterceptor(new RecordInterceptor<String, OrderConfirmed>() {

    @Override
    public ConsumerRecord<String, OrderConfirmed> intercept(
            ConsumerRecord<String, OrderConfirmed> record,
            Consumer<String, OrderConfirmed> consumer) {

        Header correlation = record.headers().lastHeader("correlation-id");
        if (correlation == null) {
            log.warn("Record has no correlation-id: {}-{}",
                    record.topic(), record.partition());
        }
        return record;
    }

    @Override
    public void success(ConsumerRecord<String, OrderConfirmed> record,
                        Consumer<String, OrderConfirmed> consumer) {
        log.debug("Listener processed {} at offset {}",
                record.topic(), record.offset());
    }

    @Override
    public void failure(ConsumerRecord<String, OrderConfirmed> record,
                        Exception exception,
                        Consumer<String, OrderConfirmed> consumer) {
        log.warn("Listener failed for {} at offset {}",
                record.topic(), record.offset(), exception);
    }
});
```

Không gọi `seek()`, `commitSync()` hoặc các thao tác làm thay đổi vị trí consumer trong interceptor; listener container phải quản lý offset. Nếu interceptor trả về một `ConsumerRecord` mới, topic, partition và offset phải giữ nguyên để tránh mất hoặc lặp record. Với container transaction, interceptor mặc định được gọi trước khi transaction bắt đầu từ Spring Kafka 2.8; có thể đặt `interceptBeforeTx = false` nếu interceptor cần chạy bên trong transaction. Nếu interceptor có thể ném exception và bạn muốn exception đó làm rollback transaction của container, không để interceptor chạy trước transaction.

## 6. Truyền trace context bằng Micrometer Observation

Trace context giúp liên kết span gửi message ở service nguồn với span nhận và xử lý ở service đích. Chuẩn W3C Trace Context định nghĩa `traceparent` và `tracestate`; baggage có thể mang một số giá trị ngữ cảnh được phép truyền giữa service.

Từ Spring Kafka 3.0, `KafkaTemplate` và listener container hỗ trợ Micrometer Observation. Bật observation ở cả hai phía:

```java
@Bean
KafkaTemplate<String, OrderConfirmed> kafkaTemplate(
        ProducerFactory<String, OrderConfirmed> producerFactory) {

    KafkaTemplate<String, OrderConfirmed> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderConfirmed> orderListenerFactory(
        ConsumerFactory<String, OrderConfirmed> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderConfirmed>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}
```

Để có trace propagation thực sự, ứng dụng còn cần Micrometer Tracing, một tracer implementation như OpenTelemetry hoặc Brave, và các tracing observation handler/propagator được đăng ký trong `ObservationRegistry`. Spring Boot có thể tự cấu hình các thành phần này khi có dependency và cấu hình tracing phù hợp. Chỉ bật Observation với `micrometer-core` có thể tạo metric/observation, nhưng chưa đủ để tạo và truyền trace context nếu không có tracing handler.

Khi sender và receiver observation được cấu hình đúng, tracing handler ghi context vào carrier của message lúc gửi và khôi phục context lúc nhận. Nếu dùng W3C propagator, các header như `traceparent` và `tracestate` được truyền qua Kafka. Service nhận tạo span tiếp nối cùng trace; trace ID được giữ, còn parent/span ID thay đổi theo quan hệ cha-con. Không cần tự tạo `traceparent` trong `ProducerInterceptor` khi Micrometer Tracing đã quản lý propagation.

Có thể thêm thuộc tính vào span bằng `KafkaTemplateObservationConvention` hoặc `KafkaListenerObservationConvention`. Từ Spring Kafka 3.0.6, observation context cung cấp `ProducerRecord` hoặc `ConsumerRecord` để tạo tag động. Chỉ đưa giá trị có số lượng hữu hạn như `event-type` hoặc `listener-id` vào metric tag; không dùng `correlation-id`, order ID hay user ID làm low-cardinality metric tag vì chúng tạo cardinality rất lớn. Các ID chi tiết phù hợp hơn với trace hoặc log.

## 7. Phân biệt correlation ID và trace context

Hai loại thông tin này có thể cùng xuất hiện trong một record nhưng trả lời hai câu hỏi khác nhau:

| Thuộc tính | Correlation ID | Trace context |
|---|---|---|
| Mục đích | Liên kết một yêu cầu hoặc quy trình nghiệp vụ | Theo dõi đường đi và quan hệ thời gian của các thao tác phân tán |
| Ai tạo | Ứng dụng hoặc gateway theo hợp đồng nghiệp vụ | Tracing instrumentation/propagator |
| Định dạng | Do hệ thống quy định, ví dụ UUID | Theo chuẩn propagator như W3C hoặc B3 |
| Vòng đời | Có thể giữ nguyên qua nhiều sự kiện cùng một quy trình | Trace ID được giữ trong trace; mỗi span có span ID riêng |
| Nơi tra cứu | Log, audit, nghiệp vụ | Hệ thống tracing như Zipkin hoặc Jaeger |

Ví dụ, một đơn hàng có `correlation-id=order-flow-42` trong nhiều sự kiện liên quan. Mỗi lần service gửi hoặc nhận message có thể tạo span riêng nhưng vẫn thuộc cùng trace. Khi một quy trình nghiệp vụ kéo dài nhiều phút hoặc tạo nhiều nhánh xử lý, correlation ID giúp tìm toàn bộ sự kiện nghiệp vụ còn trace context giúp xem quan hệ nhân quả và thời gian của từng lần gọi.

## 8. Kiểm tra metadata và trace context

Nên kiểm tra cả nội dung header và khả năng tiếp nối trace giữa producer với consumer:

1. Gửi `ProducerRecord` có `correlation-id`, `event-type` và `schema-version`.
2. Đọc record bằng `ConsumerRecord` và xác nhận tên header, giá trị UTF-8 cùng hành vi khi header bị thiếu.
3. Gửi qua listener có bật Observation; xác nhận `traceparent` có mặt khi Micrometer Tracing và W3C propagator đã được cấu hình.
4. Kiểm tra trace ở backend: span gửi và span nhận có cùng trace ID, với quan hệ parent-child phù hợp.
5. Gửi record không có custom header để xác nhận ứng dụng xử lý trường hợp thiếu theo hợp đồng, không ném `NullPointerException`.
6. Thử header lặp tên để xác nhận consumer chọn `lastHeader()` hay duyệt toàn bộ đúng như yêu cầu.

Ví dụ kiểm tra nhanh header sau khi nhận record:

```java
assertThat(record.headers().lastHeader("correlation-id")).isNotNull();
assertThat(new String(
        record.headers().lastHeader("correlation-id").value(),
        StandardCharsets.UTF_8)).isEqualTo("req-8f31");

assertThat(record.headers().lastHeader("event-type")).isNotNull();
```

Với trace, không nên chỉ assert một chuỗi `traceparent` cố định vì trace ID và parent ID được tạo động. Hãy kiểm tra header tồn tại, có cấu trúc hợp lệ và trace backend ghi nhận các span thuộc cùng trace.

## 9. Lỗi thường gặp khi truyền metadata

**Đọc header như String trực tiếp.** Giá trị Kafka header là `byte[]`; phải giải mã đúng charset hoặc dùng mapper đã cấu hình.

**Giả định header luôn tồn tại.** Producer cũ, ứng dụng khác ngôn ngữ hoặc record được tạo thủ công có thể không có header. Xác định header nào bắt buộc và xử lý thiếu rõ ràng.

**Dùng header thay cho xác thực.** `tenant-id`, `user-id` hoặc role trong header do producer gửi không tự trở thành thông tin đáng tin cậy. Consumer phải xác minh nguồn và quyền truy cập theo cơ chế bảo mật riêng.

**Đưa dữ liệu nhạy cảm vào header.** Header có thể xuất hiện trong log, công cụ quan sát, DLT hoặc hệ thống trung gian. Không gửi access token, mật khẩu, dữ liệu cá nhân nhạy cảm hay bí mật dịch vụ.

**Để header tăng không giới hạn.** Header lớn làm tăng kích thước record và chi phí mạng/lưu trữ. Chỉ truyền giá trị ngắn cần thiết; không sao chép toàn bộ HTTP request headers vào Kafka.

**Tự ghi đè trace context.** Nếu Micrometer Tracing đang quản lý propagation, không thêm `traceparent` thủ công bằng interceptor. Ghi đè hoặc tạo header không hợp lệ có thể làm đứt trace hoặc tạo quan hệ span sai.

**Dùng JSON header cho mọi hệ thống.** `JsonKafkaHeaderMapper` có metadata kiểu riêng và quy tắc trusted package. Với consumer không dùng Spring, header raw UTF-8 hoặc schema byte rõ ràng thường dễ tương thích hơn.

**Làm công việc nặng trong interceptor.** Interceptor chạy trên đường gửi hoặc đường nhận. Không gọi REST, truy vấn database hoặc chờ tác vụ dài trong callback; điều đó làm giảm throughput và tăng độ trễ xử lý.

## 10. Ghi nhớ

- Kafka headers là các cặp tên và `byte[]`; một record có thể có nhiều header cùng tên.
- Dùng `ProducerRecord.headers()` hoặc `MessageBuilder` để thêm metadata; dùng `ConsumerRecord.headers()` hoặc `@Header` để đọc.
- `KafkaHeaderMapper` ánh xạ `MessageHeaders` sang Kafka headers; chọn raw String/byte cho hợp đồng đa ngôn ngữ và giới hạn trusted packages khi dùng JSON.
- `ProducerInterceptor` áp dụng ở cấp Kafka producer; `RecordInterceptor` áp dụng trong listener container và có callback trước/sau listener.
- Không thay đổi topic, partition, offset hoặc vị trí consumer trong `RecordInterceptor`.
- Spring Kafka 3.0+ hỗ trợ Observation cho `KafkaTemplate` và listener container; trace propagation cần Micrometer Tracing cùng propagator/observation handlers.
- Dùng `correlation-id` cho liên kết nghiệp vụ và `traceparent`/`tracestate` cho distributed tracing; không tự ghi đè trace context do instrumentation quản lý.
- Giữ metadata nhỏ, không nhạy cảm, có quy ước tên và xử lý được trường hợp thiếu hoặc lặp.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Message Listener Containers, Record Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Monitoring and Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring for Apache Kafka — Producer and Consumer Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/interceptors.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
