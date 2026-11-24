# Phân biệt header do ứng dụng tạo với metadata do broker cung cấp

## Mục tiêu

Một message trong Spring Cloud Stream có thể mang payload cùng nhiều headers. Một số header do ứng dụng chủ động tạo để mô tả sự kiện hoặc liên kết các bước xử lý; số khác do broker hoặc binder cung cấp khi message được gửi, lưu trữ hay giao đến consumer. Ngoài ra, Spring Messaging còn có metadata do framework tạo, chẳng hạn ID và timestamp của đối tượng Message.

Ba nhóm này có nguồn gốc và mục đích khác nhau. Nếu coi mọi header đều là dữ liệu ứng dụng, code có thể vô tình phụ thuộc vào Kafka, RabbitMQ hoặc Pulsar; nếu sao chép metadata giao nhận sang message mới, ứng dụng có thể gửi lại những giá trị không còn đúng. Bài học này giúp nhận diện từng nhóm và đặt chúng ở đúng ranh giới.

Sau bài học, bạn có thể:

- Phân biệt application headers, broker-provided metadata và framework metadata.
- Tạo custom headers cho message đầu ra bằng Spring Messaging.
- Đọc metadata giao nhận ở inbound adapter theo binder đang sử dụng.
- Phân biệt routing key/record key do producer cung cấp với partition hoặc delivery metadata do broker gán.
- Chọn headers cần truyền tiếp và tránh sao chép metadata không còn hiệu lực.
- Kiểm thử header mapping trên Spring Cloud Stream và broker đích.

## 1. Một Message có payload và headers

Spring Messaging định nghĩa `Message<T>` gồm payload có kiểu `T` và một tập headers:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total
) {}

Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated(
                "evt-100", "order-42", new BigDecimal("125.50")
        ))
        .setHeader("correlationId", "corr-900")
        .setHeader("tenantId", "tenant-a")
        .build();
```

Trong ví dụ:

- Payload là `OrderCreated`, chứa dữ liệu nghiệp vụ của sự kiện.
- `correlationId` và `tenantId` là custom headers do ứng dụng tạo.
- Spring Messaging tạo và quản lý một số metadata của đối tượng Message, chẳng hạn ID và timestamp.

Khi message đi qua Spring Cloud Stream, binder chuyển đổi giữa abstraction của Spring và giao thức broker. Message ở phía consumer vì vậy có thể chứa payload đã được deserialize, custom headers được ánh xạ và metadata giao nhận do binder đưa vào. Tập headers cụ thể phụ thuộc broker, binder, phiên bản và cấu hình.

Có thể chia nguồn gốc header thành ba nhóm:

| Nhóm | Ai tạo hoặc gán? | Ví dụ | Cách sử dụng |
|---|---|---|---|
| Application headers | Code ứng dụng hoặc producer theo hợp đồng sự kiện | `eventId`, `correlationId`, `tenantId`, `eventType` | Mang ngữ cảnh ứng dụng cần truyền qua các bước |
| Broker-provided metadata | Broker hoặc binder khi gửi/nhận message | Topic, partition, offset, queue, routing key nhận được, delivery tag, message ID của broker | Quan sát delivery, định tuyến, chẩn đoán và thao tác tích hợp ở biên |
| Framework metadata | Spring Messaging khi tạo đối tượng Message | Message ID, timestamp của Spring Message | Theo dõi vòng đời đối tượng Message trong phạm vi framework |

Không phải header nào xuất hiện trong `MessageHeaders` cũng là một phần của hợp đồng nghiệp vụ. Hãy xác định nguồn gốc trước khi quyết định lưu, truyền tiếp hoặc dùng header để ra quyết định.

## 2. Application headers: metadata do ứng dụng chủ động định nghĩa

Application headers mang thông tin có ý nghĩa đối với các thành phần ứng dụng phối hợp với nhau. Ví dụ:

- `eventId`: định danh ổn định của một sự kiện để deduplication và đối soát.
- `correlationId`: liên kết các message hoặc thao tác trong cùng một luồng nghiệp vụ.
- `causationId`: định danh sự kiện hoặc lệnh trực tiếp gây ra sự kiện hiện tại.
- `tenantId`: phạm vi tenant nếu ứng dụng có mô hình đa tenant.
- `eventType` hoặc `schemaVersion`: mô tả loại sự kiện và phiên bản hợp đồng khi kiến trúc chọn đặt chúng trong header.

Các tên này là quy ước do hệ thống định nghĩa, không phải header tự động có sẵn của mọi broker. Nhóm phát triển cần thống nhất tên, kiểu dữ liệu, ý nghĩa, khả năng bắt buộc và quy tắc tương thích.

### Tạo application headers ở message đầu ra

Dùng `MessageBuilder` để tạo message và thêm các header thuộc hợp đồng ứng dụng:

```java
@Bean
Supplier<Message<OrderCreated>> orderEvents(OrderEventSource source) {
    return () -> {
        OrderCreated event = source.nextEvent();

        return MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId())
                .setHeader("correlationId", source.correlationId())
                .setHeader("eventType", "order.created")
                .build();
    };
}
```

Supplier tạo message ở phía ứng dụng. Binder tiếp nhận message và gửi payload cùng những headers được hỗ trợ đến broker. Broker có thể bổ sung metadata của riêng nó sau khi tiếp nhận hoặc khi giao message đến consumer.

Không đặt trước các giá trị mà broker có trách nhiệm gán, ví dụ offset Kafka, partition thực tế được chọn, delivery tag RabbitMQ hay message ID do Pulsar broker tạo. Những giá trị đó chỉ có ý nghĩa sau khi broker xử lý message.

### Đặt header trong Function

Function có thể nhận payload rồi tạo output message với application headers mới:

```java
@Bean
Function<OrderCreated, Message<OrderAccepted>> acceptOrder(
        OrderService service) {
    return event -> {
        OrderAccepted accepted = service.accept(event);

        return MessageBuilder
                .withPayload(accepted)
                .setHeader("eventId", accepted.eventId())
                .setHeader("correlationId", event.eventId())
                .setHeader("eventType", "order.accepted")
                .build();
    };
}
```

Trong hệ thống thực tế, `correlationId` thường được lấy từ ngữ cảnh đầu vào đã xác thực hoặc được tạo ở bước bắt đầu luồng. Ví dụ trên minh họa việc tạo header; không nên mặc định event ID của sự kiện đầu vào luôn là correlation ID.

### Header hay payload?

Không phải metadata nào cũng nên đặt ở header. Hãy đặt thông tin trong payload nếu nó là một phần thiết yếu của sự kiện nghiệp vụ, cần được lưu trữ lâu dài, replay hoặc sử dụng độc lập với transport. Header phù hợp với metadata điều phối và ngữ cảnh truyền tin đã được quy ước.

Ví dụ, nếu `eventId` là định danh chính thức của sự kiện, nhóm có thể đặt nó trong payload, header hoặc cả hai theo hợp đồng rõ ràng. Nếu xuất hiện ở cả hai nơi, phải xác định một nguồn là chuẩn và kiểm tra hai giá trị nhất quán. Không để producer và consumer tự chọn nơi đọc khác nhau.

## 3. Broker-provided metadata: thông tin do hệ thống truyền tin gán

Broker lưu trữ và giao message theo cơ chế riêng. Trong quá trình đó, broker hoặc binder có thể cung cấp metadata để consumer biết message đến từ đâu và đang ở trạng thái giao nhận nào.

Metadata thường có các đặc điểm:

- Được gán hoặc xác định bởi broker/binder, không phải do ứng dụng tự quyết định.
- Có thể chỉ tồn tại khi message được nhận hoặc trong một lần delivery cụ thể.
- Có ý nghĩa theo giao thức và binder cụ thể.
- Không nhất thiết được giữ nguyên khi message được gửi sang destination khác.
- Thường chỉ nên được đọc ở adapter, log, metric hoặc lớp vận hành.

### Kafka

Kafka lưu record trong topic và partition. Khi consumer đọc record, binder có thể cung cấp metadata như:

| Metadata | Ý nghĩa |
|---|---|
| Topic nhận | Topic chứa record |
| Partition nhận | Partition mà broker đã lưu record |
| Offset | Vị trí record trong partition |
| Timestamp nhận/record | Mốc thời gian liên quan đến record theo chính sách timestamp |
| Record key | Key mà producer gửi và broker lưu cùng record |

Partition và offset là thông tin vị trí do Kafka xác định. Record key thường do producer cung cấp; nó có thể được dùng để chọn partition, nhưng không phải partition number. Consumer group offset lại là tiến độ tiêu thụ được commit, khác với offset của record hiện tại.

Trong Kafka binder, một adapter có thể đọc metadata nhận bằng các hằng số Kafka-specific, ví dụ:

```java
import org.springframework.kafka.support.KafkaHeaders;

@Bean
Consumer<Message<OrderCreated>> inspectKafkaRecord(
        OrderService service) {
    return message -> {
        OrderCreated event = message.getPayload();

        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        service.handle(event);

        // topic, partition, offset phù hợp cho log/metric ở adapter.
    };
}
```

Tên và kiểu header được ánh xạ có thể phụ thuộc phiên bản Kafka binder và Spring Kafka. Chỉ dùng các constant có trong phiên bản dependency của ứng dụng; kiểm tra header thực tế bằng integration test. Không đưa topic, partition hoặc offset vào entity nghiệp vụ chỉ để lưu lại thông tin kỹ thuật của một lần nhận.

### RabbitMQ

RabbitMQ định tuyến message qua exchange và queue. Consumer có thể nhận được metadata như:

| Metadata | Ý nghĩa |
|---|---|
| Queue nhận | Queue mà consumer nhận message |
| Routing key nhận | Routing key được dùng trong quá trình định tuyến |
| Delivery tag | Định danh delivery trong channel, dùng cho thao tác acknowledgment |
| Redelivered | Dấu hiệu message đã từng được giao trước đó |
| Exchange | Exchange liên quan đến message |

Routing key thường do producer chỉ định khi publish và được broker dùng để định tuyến; queue nhận và delivery tag gắn với quá trình giao nhận. Delivery tag có phạm vi channel và không phải event ID nghiệp vụ. Không sao chép nó vào message mới hoặc dùng lại khi phát sang queue khác.

Trong Rabbit binder, các header cụ thể có thể được ánh xạ từ Spring AMQP. Adapter có thể đọc các constant tương ứng, chẳng hạn `AmqpHeaders.CONSUMER_QUEUE`, `AmqpHeaders.RECEIVED_ROUTING_KEY` hoặc `AmqpHeaders.DELIVERY_TAG`, nếu binder/phiên bản đang dùng cung cấp chúng. Cần kiểm tra tài liệu và kiểu dữ liệu thực tế trước khi sử dụng.

### Pulsar

Pulsar message có thể mang key, properties, event time và metadata do broker quản lý. Consumer cũng làm việc trong một subscription; trạng thái acknowledgment và redelivery phụ thuộc subscription type cùng cấu hình.

Các thông tin có thể quan sát gồm:

- Topic và partition liên quan đến message.
- Message ID do Pulsar tạo.
- Publish time và event time.
- Key hoặc properties do producer đặt.
- Redelivery/acknowledgment context theo subscription.

Không phải mọi trường của Pulsar client đều được expose thành Spring Message header trong mọi phiên bản binder. Hãy kiểm tra tài liệu binder và message thực tế. Nếu cần metadata Pulsar-specific, giữ phần đọc nó trong adapter để use case không phụ thuộc API Pulsar.

## 4. Phân biệt giá trị do producer đặt và giá trị broker gán

Một số trường nhìn giống nhau nhưng nguồn gốc khác nhau. Phân biệt đúng giúp tránh lỗi khi partitioning hoặc replay.

| Trường | Nguồn phổ biến | Vai trò |
|---|---|---|
| Kafka record key | Producer | Dữ liệu đầu vào cho partitioner và key của record |
| Kafka partition | Broker/partitioner khi record được ghi | Vị trí lưu record |
| Kafka offset | Broker | Vị trí record trong partition |
| Rabbit routing key | Producer | Chỉ dẫn định tuyến đến exchange |
| Rabbit queue nhận | Broker/topology | Queue thực tế giao message cho consumer |
| Rabbit delivery tag | Broker/channel | Nhận diện delivery để ack/nack |
| Pulsar message key | Producer | Key của message, có thể ảnh hưởng định tuyến/phân vùng |
| Pulsar message ID | Broker | Định danh vị trí message trong Pulsar |
| Application event ID | Ứng dụng/producer theo hợp đồng | Định danh nghiệp vụ ổn định qua retry và replay |

Ví dụ: ứng dụng gửi một record Kafka với key `order-42`. Kafka partitioner chọn partition 3 và broker gán offset 128. Key là dữ liệu producer gửi; partition và offset là metadata của record đã được lưu. Khi consumer đọc record, binder có thể đưa cả ba thông tin vào context của message, nhưng chúng không thể thay thế cho nhau.

Tương tự, producer RabbitMQ chọn routing key `orders.created`; exchange định tuyến đến queue phù hợp. Delivery tag chỉ được gán khi message được giao qua channel cho consumer. Khi publish một message mới, delivery tag cũ không còn ý nghĩa.

## 5. Đọc metadata ở adapter, giữ lõi nghiệp vụ độc lập

Inbound adapter là nơi phù hợp để đọc metadata broker. Adapter có thể dùng metadata cho log, metric, tracing hoặc chuyển một giá trị có ý nghĩa ứng dụng vào command sau khi kiểm tra.

Ví dụ tách việc xử lý nghiệp vụ và quan sát metadata:

```java
@Bean
Consumer<Message<OrderCreated>> orderCreated(
        OrderCreatedUseCase useCase,
        MessageObservation observation) {
    return message -> {
        OrderCreated event = message.getPayload();

        String correlationId = message.getHeaders()
                .get("correlationId", String.class);

        observation.recordReceived(
                event.eventId(),
                correlationId,
                message.getHeaders()
        );

        useCase.handle(new CreateOrderCommand(
                event.eventId(),
                event.orderId(),
                event.total()
        ));
    };
}
```

Trong ví dụ, `MessageObservation` là adapter hỗ trợ log/metric; nó có thể trích metadata broker theo binder. Use case nhận command nghiệp vụ và không cần biết topic, offset, queue hoặc delivery tag.

Nếu nghiệp vụ cần một giá trị như tenant ID hoặc correlation ID, adapter phải xác thực giá trị đó rồi chuyển thành field rõ ràng trong command hoặc execution context. Đừng truyền nguyên `MessageHeaders` vào application service, vì như vậy application sẽ phụ thuộc vào abstraction vận chuyển và có thể vô tình sử dụng metadata không ổn định.

Một quy tắc dễ áp dụng:

- Metadata dùng để quan sát hoặc chẩn đoán: giữ ở adapter/telemetry.
- Metadata có ý nghĩa nghiệp vụ đã được xác thực: chuyển thành dữ liệu rõ ràng của command.
- Metadata chỉ có ý nghĩa cho ack, offset, partition hoặc delivery: giữ ở adapter và binder.
- Dữ liệu cần replay hoặc lưu lâu dài: đặt trong payload hoặc kho dữ liệu có hợp đồng rõ ràng.

## 6. Chọn lọc headers khi phát message tiếp theo

Khi một consumer nhận message rồi phát message mới, không nên sao chép toàn bộ headers đầu vào một cách vô điều kiện. Message đầu vào có thể chứa metadata của broker, framework hoặc lần delivery trước.

Ví dụ tạo output message chỉ với headers ứng dụng cần truyền tiếp:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderService service) {
    return input -> {
        OrderCreated event = input.getPayload();
        OrderAccepted accepted = service.accept(event);

        String correlationId = input.getHeaders()
                .get("correlationId", String.class);

        MessageBuilder<OrderAccepted> builder =
                MessageBuilder.withPayload(accepted)
                        .setHeader("eventId", accepted.eventId())
                        .setHeader("eventType", "order.accepted");

        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }

        return builder.build();
    };
}
```

Ví dụ trên tạo message mới bằng allowlist headers. Nó không mang theo partition, offset, delivery tag, queue nhận hoặc message ID do framework tạo từ input.

Có thể dùng `MessageBuilder.fromMessage(input)` để bắt đầu từ message hiện tại, nhưng khi đó cần chủ động loại bỏ metadata không còn hợp lệ và kiểm tra mọi header được giữ lại. Đối với luồng đi qua nhiều broker, tạo message mới với tập headers cho phép thường dễ kiểm soát hơn.

Không tự đặt header có tên trùng với header dành riêng cho binder hoặc framework. Nếu cần truyền metadata tùy chỉnh, dùng tên do ứng dụng quản lý và ghi rõ hợp đồng. Tránh các tên chung chung như `id`, `timestamp`, `partition` nếu chúng có thể xung đột với metadata của framework/broker.

## 7. Headers và bảo mật

Headers có thể đến từ producer bên ngoài hoặc được broker chuyển tiếp. Vì vậy, không xem custom header là bằng chứng đáng tin cậy.

Ví dụ, một producer có thể gửi `tenantId=tenant-a`. Consumer không được chỉ dựa vào giá trị này để cấp quyền truy cập dữ liệu tenant-a. Adapter cần xác thực nguồn gửi, chữ ký hoặc thông tin định danh theo cơ chế bảo mật của hệ thống. Sau khi xác thực, application mới nhận tenant context phù hợp.

Các nguyên tắc nên áp dụng:

- Kiểm tra định dạng, độ dài và tập giá trị được phép của custom headers.
- Xác thực tenant, actor hoặc scope trước khi dùng chúng cho truy cập dữ liệu.
- Không đưa access token, mật khẩu, session ID hoặc bí mật vào headers.
- Không ghi toàn bộ headers vào log nếu có nguy cơ chứa thông tin nhạy cảm.
- Không dùng broker metadata như partition, delivery tag hoặc message ID để xác thực người gửi.
- Giới hạn danh sách headers được truyền tiếp qua ranh giới dịch vụ.

Broker metadata cũng không phải lúc nào cũng là dữ liệu có thể tin cậy ngoài ngữ cảnh của nó. Ví dụ, delivery tag chỉ có nghĩa trong channel cụ thể; offset chỉ xác định vị trí trong một partition; message ID của broker không thay thế ID nghiệp vụ.

## 8. Header mapping qua Spring Cloud Stream và các binder

Spring Cloud Stream cung cấp abstraction chung, nhưng broker có khả năng lưu và truyền metadata khác nhau. Binder thực hiện việc ánh xạ headers giữa Spring Message và message native của broker.

Khi thiết kế hợp đồng, cần xác minh:

1. Custom header nào được binder truyền ra broker?
2. Header nào được ánh xạ khi nhận lại?
3. Giá trị có giữ nguyên kiểu dữ liệu hay được chuyển thành chuỗi/byte?
4. Header nào là metadata native do broker gán?
5. Có giới hạn tên, kích thước hoặc kiểu header không?
6. Header nào bị loại bỏ, đổi tên hoặc được binder dành riêng?
7. Cơ chế native header hay embedded header được sử dụng trong cấu hình đó?

Một số binder hỗ trợ native headers của broker; một số tình huống hoặc binder có thể dùng cơ chế embedded headers. Cách cấu hình và mặc định phụ thuộc binder/phiên bản. Không giả định custom header được truyền nguyên trạng chỉ vì nó tồn tại trong đối tượng `Message` ở phía producer.

Với Kafka, native record headers là cơ chế phổ biến để mang metadata. Với RabbitMQ, message properties và headers có kiểu dữ liệu theo khả năng AMQP/client. Với Pulsar, properties và key có quy tắc riêng. Binder có thể chuẩn hóa một phần metadata thành Spring headers, nhưng không có nghĩa mọi trường native đều có mapping giống nhau.

Nếu một header là bắt buộc đối với hợp đồng ứng dụng, hãy viết contract test trên binder đích để chứng minh nó được truyền và nhận đúng. Nếu header chỉ phục vụ log nội bộ, đừng yêu cầu mọi broker phải hỗ trợ nó như một phần của hợp đồng nghiệp vụ.

## 9. Kiểm thử nguồn gốc và hành vi headers

Nên kiểm thử riêng ba nhóm:

### Unit test cho application headers

Tạo message bằng `MessageBuilder` và xác minh custom header được đặt đúng:

```java
@Test
void shouldCreateApplicationHeaders() {
    OrderCreated event = new OrderCreated(
            "evt-100", "order-42", new BigDecimal("125.50")
    );

    Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", "corr-900")
            .build();

    assertEquals("evt-100", message.getHeaders().get("eventId"));
    assertEquals("corr-900", message.getHeaders().get("correlationId"));
}
```

Test này xác minh logic tạo message của ứng dụng, không chứng minh broker đã lưu hoặc truyền các headers đó.

### Integration test cho broker metadata

Dùng Test Binder để kiểm tra mapping ở mức Spring Cloud Stream, sau đó dùng Testcontainers hoặc broker test phù hợp để xác minh metadata thật. Với mỗi binder, kiểm tra các giá trị mà ứng dụng dự kiến đọc, ví dụ:

- Kafka: topic, partition, offset và record key.
- RabbitMQ: queue nhận, routing key nhận và delivery context nếu được expose.
- Pulsar: topic, message ID, key hoặc properties được binder hỗ trợ.

Không hardcode giả định rằng các header có cùng tên và kiểu trên mọi binder. Test adapter riêng cho từng binder nếu code đọc metadata native.

### Test khi chuyển tiếp message

Tạo message đầu vào có cả application header và metadata giả lập, sau đó gọi adapter tạo message đầu ra. Xác minh:

- Application headers cần giữ lại được truyền tiếp.
- Metadata delivery của message đầu vào không xuất hiện trong message mới.
- Header không hợp lệ bị từ chối hoặc loại bỏ theo chính sách.
- Payload và event ID vẫn nhất quán.
- Binder đích nhận được đúng các custom headers được hợp đồng cho phép.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng broker message ID làm event ID nghiệp vụ | ID thay đổi khi publish lại hoặc qua broker khác | Tạo event ID ổn định trong ứng dụng |
| Sao chép offset/partition/delivery tag sang message mới | Metadata cũ không còn đúng với lần gửi mới | Tạo message mới và chỉ giữ application headers cần thiết |
| Dùng routing key như partition | Nhầm giữa chỉ dẫn định tuyến và vị trí lưu | Phân biệt key do producer đặt với partition do broker chọn |
| Giả định mọi custom header đều được truyền qua binder | Consumer không nhận được metadata mong đợi | Kiểm thử header mapping trên binder đích |
| Dùng tenant header chưa xác thực để truy cập database | Có nguy cơ truy cập sai tenant | Xác thực nguồn và giá trị ở adapter/security boundary |
| Đưa toàn bộ MessageHeaders vào domain | Domain phụ thuộc framework và metadata vận chuyển | Chuyển các giá trị cần thiết thành command/context rõ ràng |
| Ghi toàn bộ headers vào log | Có thể làm lộ token hoặc dữ liệu nhạy cảm | Chọn allowlist trường log an toàn |

## Kết luận

Application headers do ứng dụng định nghĩa để truyền ngữ cảnh như event ID, correlation ID hoặc tenant ID. Broker-provided metadata mô tả nơi lưu trữ và cách message được giao, chẳng hạn topic, partition, offset, queue hoặc delivery tag. Spring Messaging còn có metadata riêng của đối tượng Message như ID và timestamp.

Trong Spring Cloud Stream, hãy đọc metadata broker ở adapter, xác thực custom headers đến từ bên ngoài và chỉ truyền tiếp những application headers cần thiết. Không tái sử dụng metadata của lần delivery cũ khi tạo message mới. Vì Kafka, RabbitMQ và Pulsar có cách biểu diễn metadata khác nhau, hãy kiểm thử header mapping trên đúng binder và broker triển khai.

