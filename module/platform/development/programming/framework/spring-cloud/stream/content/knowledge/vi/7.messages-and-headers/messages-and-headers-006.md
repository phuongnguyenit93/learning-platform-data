# Ánh xạ header giữa Spring Messaging và giao thức broker

Trong Spring Cloud Stream, một message không chỉ có payload. Nó còn có headers chứa metadata như loại sự kiện, correlation ID, content type, khóa phân vùng hoặc thông tin truy vết. Khi message đi qua binding, binder cần chuyển những metadata này sang cấu trúc mà broker hỗ trợ; khi nhận message, binder thực hiện chiều ánh xạ ngược để ứng dụng có thể đọc header qua Spring Messaging.

Cách ánh xạ không hoàn toàn giống nhau giữa Kafka, RabbitMQ và Pulsar. Mỗi giao thức có mô hình metadata riêng: Kafka dùng header dạng key/value nhị phân, RabbitMQ có các AMQP properties và field table, còn Pulsar có message properties cùng các trường metadata riêng. Hiểu sự khác biệt này giúp thiết kế header có tính di động, tránh mất dữ liệu khi đổi binder và xác định đúng thông tin nào thuộc message, thông tin nào do broker tạo ra.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt payload, Spring Message headers và metadata do broker quản lý.
- Tạo và đọc header bằng Spring Messaging `Message<T>` và `MessageBuilder`.
- Giải thích cách binder ánh xạ header giữa Spring Messaging và Kafka, RabbitMQ hoặc Pulsar.
- Phân biệt header với Kafka key, RabbitMQ routing key và Pulsar message key.
- Chọn header cần truyền qua binding và kiểm soát việc sao chép metadata.
- Nhận biết giới hạn kiểu dữ liệu, kích thước và quy tắc chuyển đổi của từng giao thức.
- Kiểm thử header ở cấp hàm, binding và broker thực tế.

## 1. Payload, message và header

Spring Messaging biểu diễn một thông điệp bằng interface `Message<T>`. Message có hai phần:

- **Payload**: nội dung chính mà ứng dụng muốn truyền, ví dụ một đối tượng `OrderCreated`.
- **Headers**: metadata mô tả message hoặc hỗ trợ định tuyến, tương quan, định dạng và xử lý.

Ví dụ payload:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total
) {}
~~~

Tạo message có payload và metadata:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-2026-001")
        .setHeader("tenantId", "tenant-a")
        .setHeader("schemaVersion", 2)
        .build();
~~~

Trong ví dụ:

- Payload là dữ liệu đơn hàng.
- `eventType` cho biết loại sự kiện.
- `correlationId` liên kết message với một luồng xử lý hoặc yêu cầu ban đầu.
- `tenantId` xác định tenant trong hệ thống nhiều khách hàng.
- `schemaVersion` là metadata mô tả phiên bản hợp đồng trong ví dụ này.

Các header trên là metadata do ứng dụng định nghĩa. Chúng không tự trở thành một phần của JSON payload. Khi binder gửi message, binder hoặc message converter sẽ xử lý payload và ánh xạ header theo khả năng của broker.

### MessageHeaders và các header framework

`MessageHeaders` là cấu trúc map bất biến chứa header của Spring Message. Một số header thường gặp:

| Header | Mục đích |
|---|---|
| `id` | Định danh message trong Spring Messaging |
| `timestamp` | Thời điểm tạo message theo Spring Messaging |
| `contentType` | Gợi ý định dạng payload để chuyển đổi |
| `correlationId` | Liên kết các message trong cùng một luồng xử lý |
| `replyChannel` | Kênh phản hồi trong các mô hình messaging nội bộ có hỗ trợ |
| `errorChannel` | Kênh xử lý lỗi trong hệ sinh thái Spring Integration |

Không phải header nào của Spring cũng được gửi nguyên vẹn qua broker. Các header như `id`, `timestamp`, `replyChannel` hoặc `errorChannel` có ý nghĩa nội bộ trong tiến trình; chúng có thể được tạo lại, loại bỏ hoặc không thể biểu diễn trong giao thức đích. Header `contentType` có thể được dùng trong quá trình chuyển đổi và được ánh xạ theo quy tắc của binder.

Do đó, hãy xem header của message nhận được là metadata đã được binder diễn giải, không phải bản sao byte-for-byte của toàn bộ `MessageHeaders` ở phía gửi.

## 2. Tạo, đọc và biến đổi header

### Tạo message bằng MessageBuilder

`MessageBuilder` tạo một message mới từ payload và các header cần thiết:

~~~java
Message<OrderCreated> outbound =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", correlationId)
        .setHeader("sourceService", "order-service")
        .build();
~~~

Có thể dùng `MessageBuilder.fromMessage(existing)` khi cần tạo message mới dựa trên message có sẵn. Tuy nhiên, sao chép toàn bộ header có thể mang theo metadata nội bộ, dữ liệu nhạy cảm hoặc giá trị không tương thích với broker đích. Trong luồng tích hợp giữa các hệ thống, nên chọn rõ header được phép chuyển tiếp.

### Đọc header trong Consumer

Consumer có thể nhận payload thuần nếu chỉ cần dữ liệu nghiệp vụ:

~~~java
@Bean
Consumer<OrderCreated> inventory() {
    return event -> updateInventory(event);
}
~~~

Khi cần metadata, khai báo Consumer nhận `Message<OrderCreated>`:

~~~java
@Bean
Consumer<Message<OrderCreated>> inventory() {
    return message -> {
        OrderCreated event = message.getPayload();
        String correlationId =
            message.getHeaders().get("correlationId", String.class);

        updateInventory(event, correlationId);
    };
}
~~~

Dùng `getPayload()` để đọc dữ liệu nghiệp vụ và `getHeaders()` để truy cập metadata. Khi đọc header có kiểu cụ thể, nên yêu cầu kiểu mong đợi hoặc kiểm tra kiểu trước khi ép kiểu; giá trị nhận về có thể đã được chuyển đổi bởi binder.

### Chỉ chuyển tiếp header cần thiết

Function thường nhận message, biến đổi payload và phát ra message mới. Ví dụ:

~~~java
@Bean
Function<Message<OrderCreated>, Message<EnrichedOrder>> enrichOrder() {
    return input -> {
        OrderCreated event = input.getPayload();
        EnrichedOrder result = enrich(event);

        MessageBuilder<EnrichedOrder> output =
            MessageBuilder.withPayload(result)
                .setHeader("eventType", "EnrichedOrder");

        Object correlationId =
            input.getHeaders().get("correlationId");

        if (correlationId != null) {
            output.setHeader("correlationId", correlationId);
        }

        Object tenantId = input.getHeaders().get("tenantId");
        if (tenantId != null) {
            output.setHeader("tenantId", tenantId);
        }

        return output.build();
    };
}
~~~

Ví dụ chỉ chuyển tiếp `correlationId` và `tenantId`, đồng thời cập nhật `eventType`. Cách làm này tạo ra hợp đồng header rõ ràng ở đầu ra. Không nên sao chép mù quáng tất cả header đầu vào vì một số header chỉ có ý nghĩa ở chặng trước hoặc chứa thông tin không được phép công bố.

## 3. Quá trình ánh xạ giữa Spring Messaging và broker

Ở phía gửi, luồng xử lý khái quát như sau:

1. Function hoặc service tạo `Message<T>` gồm payload và headers.
2. Spring Cloud Stream chọn output binding và binder.
3. Message converter chuyển payload sang dạng dữ liệu truyền tải phù hợp.
4. Header mapper hoặc cơ chế tích hợp của binder chọn header có thể truyền và chuyển giá trị sang kiểu dữ liệu của giao thức.
5. Broker lưu hoặc định tuyến message theo metadata native của nó.

Ở phía nhận, quá trình diễn ra theo chiều ngược lại:

1. Broker giao message cùng metadata native cho binder.
2. Binder đọc metadata và ánh xạ các trường được hỗ trợ thành Spring Message headers.
3. Message converter giải mã payload theo content type và kiểu dữ liệu của function.
4. Consumer nhận payload cùng những header được ánh xạ.

~~~mermaid
flowchart LR
    A["Function / Service"] --> B["Spring Message<br/>payload + headers"]
    B --> C["Output binding"]
    C --> D["Binder + header mapper"]
    D --> E["Broker native message<br/>payload + metadata"]
    E --> F["Binder + header mapper"]
    F --> G["Input binding"]
    G --> H["Spring Message"]
    H --> I["Consumer / Function"]
~~~

Không phải mọi header đều được truyền qua từng bước. Một số metadata được ánh xạ sang trường native của broker; một số header tùy chỉnh được lưu như thuộc tính mở rộng; một số header nội bộ bị bỏ qua. Nếu cần giữ metadata qua nhiều broker, hãy định nghĩa một tập header ứng dụng có kiểu đơn giản, tên ổn định và được kiểm thử ở cả hai đầu.

## 4. Ánh xạ header với Kafka

Kafka record có payload value, record key, timestamp, partition và danh sách headers. Kafka header có dạng key/value, trong đó value là byte array. Một record có thể chứa nhiều header cùng tên; vì vậy, mô hình header Kafka có thể biểu diễn nhiều giá trị cho một key.

Spring Cloud Stream Kafka binder kết hợp với các cơ chế header mapping của Spring Kafka để chuyển header giữa Spring Message và Kafka record. Header có kiểu đơn giản như chuỗi hoặc byte array thường dễ ánh xạ. Các kiểu object khác có thể cần cơ chế serialize/deserialize hoặc thông tin kiểu do mapper sử dụng. Chi tiết mapping phụ thuộc phiên bản Spring Kafka, binder và cấu hình header mapper.

### Header không giống record key

Cần phân biệt những trường sau:

| Thành phần Kafka | Vai trò |
|---|---|
| Record key | Thường được dùng bởi partitioner để chọn partition; có thể tham gia compaction |
| Record headers | Metadata dạng key/byte value gắn với record |
| Record timestamp | Thời điểm của record theo chính sách timestamp của producer/broker |
| Partition và offset | Vị trí record do Kafka quản lý |
| Consumer group | Nhóm consumer chia partition và lưu tiến độ offset |

Nếu muốn mọi sự kiện của cùng một đơn hàng đi vào cùng partition, hãy cấu hình key theo `orderId`. Đặt `orderId` trong một header tùy chỉnh không tự động làm Kafka dùng nó làm record key.

Ví dụ tạo message có header tương quan:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("correlationId", "corr-order-1001")
        .setHeader("eventType", "OrderCreated")
        .build();
~~~

Nếu cần đặt Kafka key, hãy dùng thuộc tính producer hoặc API/binder hỗ trợ để truyền key theo cách được tài liệu của phiên bản đó quy định. Không giả định custom header `key` hoặc `partitionKey` sẽ tự động thay thế record key.

### Header mapper và kiểu dữ liệu

Kafka chỉ lưu byte array trong header. Khi gửi một giá trị Java khác byte array, header mapper cần chuyển đổi giá trị đó thành byte. Khi nhận, mapper có thể khôi phục kiểu dựa trên quy tắc và metadata của nó. Nếu producer và consumer dùng mapper khác nhau, header có thể trở thành chuỗi, byte array hoặc không được khôi phục về kiểu ban đầu.

Đối với hợp đồng liên dịch vụ, ưu tiên giá trị đơn giản như:

- Chuỗi UTF-8 cho `correlationId`, `eventType`, `tenantId`.
- Chuỗi số hoặc số nguyên đã thống nhất cách biểu diễn cho version.
- Byte array khi ứng dụng thật sự cần metadata nhị phân.

Không truyền một object Java tùy ý rồi phụ thuộc vào việc consumer có cùng class hoặc cùng cơ chế deserialization. Không bật cơ chế deserialize object không tin cậy chỉ để giữ nguyên kiểu header.

## 5. Ánh xạ header với RabbitMQ

RabbitMQ sử dụng AMQP message properties và headers table. Một số metadata phổ biến được biểu diễn thành AMQP properties chuẩn, ví dụ:

- `contentType` và `contentEncoding`: mô tả định dạng và mã hóa payload.
- `correlationId`: liên kết request và response hoặc các message liên quan.
- `messageId`: định danh message ở cấp ứng dụng.
- `replyTo`: địa chỉ hoặc routing destination dùng cho phản hồi.
- `type`: loại message do ứng dụng xác định.
- `timestamp`: thời điểm message theo metadata AMQP.
- `priority`, `expiration`, `deliveryMode`: thuộc tính điều khiển hoặc vận chuyển message.

Các header tùy chỉnh có thể được lưu trong AMQP headers table. RabbitMQ và client AMQP chỉ hỗ trợ những kiểu giá trị nằm trong tập kiểu dữ liệu mà giao thức cho phép. Không phải object Java nào cũng có thể chuyển trực tiếp thành một field table hợp lệ.

### Routing key không phải header tùy chỉnh

Với exchange kiểu direct hoặc topic, routing key quyết định queue nào nhận message theo binding. Header tùy chỉnh như `tenantId` hoặc `eventType` chỉ là metadata, trừ khi ứng dụng dùng exchange kiểu headers và cấu hình binding dựa trên các header đó.

Ví dụ một message có metadata:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-order-1001")
        .setHeader("tenantId", "tenant-a")
        .build();
~~~

Message có thể được gửi tới exchange và routing key do binding/binder cấu hình. Những header tùy chỉnh không tự thay đổi routing key. Nếu cần định tuyến theo tenant hoặc loại sự kiện, hãy cấu hình exchange, routing key và binding phù hợp; với headers exchange, phải bảo đảm tên và kiểu header khớp điều kiện binding.

### Kiểm tra trên RabbitMQ

RabbitMQ Management UI hoặc công cụ quản trị có thể hiển thị exchange, queue, binding, số message và metadata của message khi xem được nội dung. Khi kiểm tra header, hãy xác nhận cả tên, kiểu và giá trị. Một số giá trị có thể được biểu diễn dưới dạng AMQP field type thay vì kiểu Java ban đầu.

Nếu header không xuất hiện ở consumer, kiểm tra:

1. Producer có thực sự đặt header trước khi gửi.
2. Header mapper/binder có cho phép ánh xạ tên header đó không.
3. Kiểu giá trị có được AMQP headers table hỗ trợ không.
4. Có cấu hình nào loại bỏ hoặc ghi đè header ở binding hay không.
5. Consumer có đang đọc đúng queue và message tương ứng không.

## 6. Ánh xạ metadata với Apache Pulsar

Pulsar message có payload và metadata native. Ngoài các trường do broker quản lý, Pulsar hỗ trợ message properties dưới dạng cặp key/value chuỗi. Message còn có các trường chuyên biệt như key, ordering key, event time, sequence ID, schema version và message ID.

Các khái niệm cần phân biệt:

| Trường hoặc cấu trúc liên quan | Vai trò |
|---|---|
| Properties | Map key/value dạng chuỗi do ứng dụng đính kèm |
| Key | Khóa message, có thể tham gia định tuyến hoặc xử lý theo khóa |
| Ordering key | Khóa dùng để duy trì thứ tự theo cách broker hỗ trợ |
| Event time | Thời điểm sự kiện xảy ra do producer cung cấp |
| Sequence ID | Số thứ tự do producer sử dụng |
| Message ID | Định danh vị trí message do broker cấp |
| Publish time | Thời điểm broker ghi nhận message |
| Subscription | Cấu trúc theo dõi tiến độ tiêu thụ của một nhóm subscriber trên topic; không phải property của từng message |

Spring Cloud Stream Pulsar binder ánh xạ những header và thuộc tính được hỗ trợ sang metadata native của Pulsar. Quy tắc cụ thể phụ thuộc phiên bản binder và cấu hình. Không nên giả định mọi Spring Message header đều trở thành Pulsar property, hoặc header tùy chỉnh có thể giữ nguyên kiểu Java.

Ví dụ metadata dạng chuỗi:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-order-1001")
        .setHeader("tenantId", "tenant-a")
        .build();
~~~

Khi được ánh xạ thành Pulsar properties, các giá trị cần có cách biểu diễn chuỗi rõ ràng. Nếu một header cần điều khiển partitioning hoặc ordering, hãy dùng thuộc tính key/ordering key mà binder hỗ trợ thay vì chỉ đặt một custom property có tên tương tự.

### Kiểm tra metadata Pulsar

Dùng công cụ quản trị hoặc client phù hợp để xem topic, subscription và thống kê. Khi cần xác minh properties, có thể dùng một consumer kiểm thử riêng để đọc message và in ra metadata. Tránh dùng subscription của ứng dụng production để thử nghiệm vì thao tác đọc có thể thay đổi cursor hoặc trạng thái tiêu thụ.

## 7. Header chuẩn và header tùy chỉnh

Nên chia header thành hai nhóm về mục đích:

**Header chuẩn hoặc header vận chuyển** có ý nghĩa rộng trong messaging, ví dụ content type, correlation ID, message ID hoặc reply destination. Binder có thể ánh xạ một số header này sang trường native của broker.

**Header tùy chỉnh của ứng dụng** mô tả ngữ cảnh nghiệp vụ hoặc xử lý, ví dụ `eventType`, `tenantId`, `sourceService` hoặc `traceparent`. Các header này cần được định nghĩa rõ ràng và thống nhất giữa producer với consumer.

Không nên dùng một tên header tùy chỉnh trùng với tên trường dành riêng của broker nếu ý nghĩa khác nhau. Ví dụ, một custom header tên `timestamp` có thể bị nhầm với timestamp vận chuyển; dùng tên rõ hơn như `businessOccurredAt` khi muốn biểu diễn thời điểm nghiệp vụ.

### Quy ước đặt tên

Một quy ước đơn giản giúp giảm lỗi khi chuyển broker:

- Dùng tên ASCII ổn định, dễ đọc, nhất quán chữ hoa/thường.
- Chọn một dạng tên duy nhất, ví dụ `correlationId` hoặc `correlation-id`, và dùng thống nhất.
- Định nghĩa kiểu dữ liệu và cách biểu diễn cho từng header.
- Ghi rõ header bắt buộc, tùy chọn và header chỉ có ý nghĩa trong một chặng.
- Tránh nhúng payload lớn vào header.
- Không dùng header làm nơi lưu dữ liệu nghiệp vụ cốt lõi cần bảo đảm lâu dài.

Tên header có thể phân biệt chữ hoa/chữ thường tùy map và giao thức. Một số broker hoặc client có thể chuẩn hóa cách biểu diễn. Vì vậy, nên tránh tạo hai header chỉ khác nhau ở chữ hoa/chữ thường.

## 8. HeaderMode và khả năng hỗ trợ của binder

Spring Cloud Stream có các cơ chế điều khiển cách header được truyền qua binding. Tùy binder, có thể gặp các chế độ như:

| Chế độ | Ý nghĩa khái quát |
|---|---|
| `headers` | Sử dụng cơ chế header native của broker khi binder hỗ trợ |
| `embeddedHeaders` | Đóng gói metadata header cùng payload theo định dạng embedded header |
| `none` | Không truyền header theo cơ chế header của Spring Cloud Stream |

Không phải mọi binder đều hỗ trợ các chế độ theo cùng cách hoặc có cùng giá trị mặc định. Một số binder có native header support; binder khác có thể cần embedded headers. Hãy kiểm tra tài liệu đúng phiên bản của binder và binding đang dùng trước khi đặt `headerMode`.

Nếu dùng embedded headers, consumer phải hiểu cùng định dạng đóng gói. Một consumer native của broker hoặc ứng dụng ngoài Spring Cloud Stream có thể nhìn thấy phần metadata đóng gói như một phần payload nếu không giải mã theo đúng quy tắc.

Nếu chọn `none`, không nên trông đợi custom header được giữ lại ở phía nhận. Hãy giữ thông tin thiết yếu trong payload hoặc dùng một kênh metadata khác có hợp đồng rõ ràng.

## 9. Chọn lọc header và bảo vệ dữ liệu

Header được truyền qua broker có thể đi tới nhiều ứng dụng và nhiều môi trường lưu trữ. Không nên coi header là vùng dữ liệu riêng tư hoặc đáng tin cậy.

Một số nguyên tắc quan trọng:

- Chỉ chuyển tiếp những header cần thiết cho chặng tiếp theo.
- Không đưa access token, mật khẩu, cookie phiên hoặc dữ liệu xác thực vào header tùy chỉnh.
- Không tin giá trị `tenantId`, `userId` hoặc `role` từ message bên ngoài nếu chưa xác minh quyền.
- Không deserialize Java object tùy ý từ header không tin cậy.
- Giới hạn kích thước và số lượng header để tránh tăng chi phí lưu trữ, truyền tải và log.
- Tránh ghi toàn bộ header vào log nếu có thể chứa dữ liệu nhạy cảm.

Correlation ID và trace context rất hữu ích để quan sát luồng xử lý, nhưng cần thống nhất chính sách tạo, xác thực và truyền tiếp. Không dùng trace header làm bằng chứng xác thực người dùng hoặc phân quyền nghiệp vụ.

### Header allowlist

Có thể tạo một allowlist ở tầng ứng dụng để quyết định header nào được chuyển tiếp:

~~~java
private static final Set<String> FORWARDED_HEADERS =
    Set.of("correlationId", "tenantId", "traceparent");

MessageBuilder<EnrichedOrder> copyAllowedHeaders(
        Message<?> input,
        EnrichedOrder payload) {

    MessageBuilder<EnrichedOrder> output =
        MessageBuilder.withPayload(payload);

    for (String name : FORWARDED_HEADERS) {
        Object value = input.getHeaders().get(name);
        if (value != null) {
            output.setHeader(name, value);
        }
    }

    return output;
}
~~~

Allowlist giúp kiểm soát metadata đi qua ranh giới dịch vụ. Khi thêm header mới, cần cập nhật hợp đồng và kiểm thử để tránh vô tình truyền dữ liệu nội bộ.

## 10. Kiểm thử ánh xạ header

Nên kiểm tra header ở ba cấp độ.

### Unit test cho logic message

Kiểm tra function tạo và chuyển tiếp đúng header:

Giả sử hàm `enrich` là function đang được kiểm thử, nhận một Spring Message và trả về message kết quả sau khi áp dụng allowlist header.

~~~java
@Test
void preservesCorrelationId() {
    OrderCreated event = new OrderCreated(
        "evt-1", "order-1", new BigDecimal("100.00")
    );

    Message<OrderCreated> input =
        MessageBuilder.withPayload(event)
            .setHeader("correlationId", "corr-1")
            .setHeader("tenantId", "tenant-a")
            .build();

    Message<EnrichedOrder> output = enrich(input);

    assertEquals(
        "corr-1",
        output.getHeaders().get("correlationId")
    );
    assertEquals(
        "tenant-a",
        output.getHeaders().get("tenantId")
    );
}
~~~

Unit test chứng minh logic ứng dụng giữ hoặc thay đổi header đúng như thiết kế. Nó chưa chứng minh binder đã chuyển header qua broker.

### Binding test

Dùng test binder để gửi message vào binding, nhận message ở output channel hoặc destination kiểm thử, rồi kiểm tra payload và header. Test binder phù hợp để xác minh tích hợp ở cấp Spring Cloud Stream mà không cần broker thật.

### Broker integration test

Với Kafka, RabbitMQ hoặc Pulsar thật, gửi message qua binder và đọc lại bằng consumer kiểm thử. Kiểm tra:

- Header tùy chỉnh có xuất hiện ở phía nhận không.
- Tên header có bị đổi hoặc chuẩn hóa không.
- Kiểu giá trị có được giữ nguyên hay chuyển thành chuỗi/byte không.
- Header trùng tên có được giữ, gộp hoặc chỉ lấy một giá trị không.
- Các metadata native như key, routing key, event time hoặc message ID có được thiết lập đúng không.
- Header nội bộ nào bị loại bỏ theo thiết kế.

Khi kiểm thử round-trip, dùng một group/subscription kiểm thử riêng để tránh làm thay đổi tiến độ tiêu thụ của ứng dụng. Ghi lại phiên bản binder và broker vì kết quả ánh xạ có thể khác giữa các phiên bản.

## 11. Lỗi thường gặp khi ánh xạ header

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Header có ở producer nhưng mất ở consumer | Binder không ánh xạ header đó, header bị lọc hoặc header mode không phù hợp | Kiểm tra mapper, cấu hình binding và khả năng native header |
| Header nhận về thành byte array | Giao thức lưu giá trị dưới dạng byte hoặc mapper không khôi phục kiểu | Kiểm tra serializer/deserializer và quy ước kiểu |
| Header object không deserialize được | Producer và consumer không thống nhất kiểu hoặc metadata kiểu | Dùng kiểu scalar/chuỗi hoặc schema rõ ràng |
| Header bị ghi đè | Cùng tên header được đặt ở nhiều tầng hoặc broker có trường chuẩn tương ứng | Xác định nguồn header và quy tắc ưu tiên |
| Correlation ID bị mất giữa các function | Function tạo message mới nhưng không chuyển tiếp header cần thiết | Dùng allowlist để copy header |
| Kafka partition không theo header partitionKey | Record key chưa được cấu hình; header không tự quyết định partition | Thiết lập Kafka key bằng cơ chế producer/binder phù hợp |
| RabbitMQ message vào sai queue | Routing key hoặc exchange binding không đúng | Kiểm tra exchange, routing key và queue binding |
| Pulsar không giữ kiểu header | Properties của Pulsar là key/value chuỗi | Chuẩn hóa cách serialize và parse giá trị |
| Consumer ngoài Spring không hiểu metadata | Dùng embedded headers hoặc định dạng riêng của mapper | Thống nhất giao thức và kiểm thử bằng client ngoài |
| Message tăng kích thước bất thường | Quá nhiều header hoặc header chứa dữ liệu lớn | Giảm số lượng, kích thước và chỉ giữ metadata cần thiết |

Khi header bị mất, hãy xác định nó mất ở tầng nào: trước khi gửi, trong quá trình mapping, tại broker hay khi binder tạo Spring Message ở phía nhận. Kiểm tra tuần tự payload, native metadata và Spring headers sẽ giúp khoanh vùng chính xác hơn.

## 12. Quy trình thực hành: truyền correlation ID qua ba broker

Tạo một luồng xử lý sự kiện đơn hàng có publisher, function và consumer:

1. Publisher tạo `Message<OrderCreated>` với `eventType`, `correlationId` và `tenantId`.
2. Function nhận `Message<OrderCreated>`, biến đổi payload thành `EnrichedOrder`.
3. Function tạo message đầu ra mới và chỉ chuyển tiếp các header nằm trong allowlist.
4. Consumer nhận `Message<EnrichedOrder>`, đọc `correlationId` và ghi log cùng `orderId`.
5. Chạy unit test để xác minh payload và header ở từng bước.
6. Chạy binding test để xác minh message đi qua binding.
7. Chạy integration test với Kafka, rồi kiểm tra record headers và record key riêng biệt.
8. Lặp lại với RabbitMQ, kiểm tra AMQP properties, headers table và routing key.
9. Lặp lại với Pulsar, kiểm tra message properties, key và event time.
10. So sánh header nào được giữ nguyên, header nào được ánh xạ sang metadata native và header nào không được hỗ trợ.
11. Thử gửi một header có kiểu không được hỗ trợ hoặc có kích thước quá lớn trong môi trường kiểm thử để quan sát lỗi và cách hệ thống xử lý.
12. Hoàn thiện bảng hợp đồng header dùng chung cho producer và consumer.

Bảng hợp đồng mẫu:

| Tên header | Kiểu biểu diễn | Bắt buộc | Mục đích |
|---|---|---|---|
| `eventType` | Chuỗi | Có | Phân loại sự kiện |
| `correlationId` | Chuỗi | Có trong luồng cần truy vết | Liên kết các bước xử lý |
| `tenantId` | Chuỗi | Theo mô hình tenant | Xác định ngữ cảnh tenant |
| `traceparent` | Chuỗi | Theo chính sách tracing | Truyền trace context |
| `sourceService` | Chuỗi | Tùy hợp đồng | Xác định dịch vụ phát hành |

Khi hoàn thành, bạn cần giải thích được vì sao một Spring Message header không nhất thiết trở thành một trường native giống hệt trên mọi broker, đồng thời biết cách thiết kế tập header ứng dụng có thể truyền qua các binder một cách ổn định.

## Kết luận

Spring Messaging biểu diễn message bằng payload và headers, còn Kafka, RabbitMQ và Pulsar có các mô hình metadata khác nhau. Binder và header mapper đảm nhiệm việc chuyển đổi giữa hai thế giới đó; vì vậy, một header của Spring không được bảo đảm sẽ xuất hiện nguyên vẹn ở mọi giao thức.

Hãy tách payload khỏi metadata, phân biệt header với key và thông tin định tuyến của broker, chuẩn hóa tên và kiểu header, chỉ chuyển tiếp dữ liệu cần thiết và kiểm thử round-trip trên broker thực tế. Thiết kế như vậy giúp correlation, tracing và ngữ cảnh nghiệp vụ được truyền đúng qua các function và binding mà không phụ thuộc quá mức vào một broker cụ thể.

