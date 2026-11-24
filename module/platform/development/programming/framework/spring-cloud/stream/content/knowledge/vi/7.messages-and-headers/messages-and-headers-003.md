# Header contentType, id và timestamp

Trong Spring Cloud Stream, một thông điệp không chỉ chứa payload. Nó còn có các header mô tả cách diễn giải payload và cung cấp metadata cho quá trình xử lý. Ba header thường gặp là `contentType`, `id` và `timestamp`. Hiểu đúng vai trò của chúng giúp producer và consumer thống nhất định dạng dữ liệu, theo dõi một message trong quá trình xử lý và phân biệt thời điểm tạo message với thời điểm nghiệp vụ xảy ra.

`contentType` mô tả kiểu nội dung để framework chọn cách chuyển đổi payload. `id` nhận diện một message instance trong mô hình Spring Messaging. `timestamp` ghi thời điểm message được tạo theo metadata của Spring. Hai header `id` và `timestamp` do framework quản lý; chúng không thay thế mã sự kiện nghiệp vụ ổn định như `eventId` hoặc thời điểm sự kiện xảy ra như `occurredAt`.

## 1. Cấu trúc Message trong Spring

Spring Messaging biểu diễn một thông điệp bằng payload và headers:

```java
public record OrderItem(String productId, int quantity) {}

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt,
        List<OrderItem> items) {}

public record OrderValidated(String eventId, String orderId, BigDecimal total) {}

OrderCreated orderCreated = new OrderCreated(
        "evt-001", "ord-100", new BigDecimal("29.90"), Instant.now(), List.of());

Message<OrderCreated> message = MessageBuilder
        .withPayload(orderCreated)
        .setHeader("eventId", orderCreated.eventId())
        .build();
```

- **Payload** là dữ liệu chính mà consumer xử lý, ví dụ `OrderCreated`.
- **Headers** là metadata đi kèm, ví dụ `contentType`, `id`, `timestamp`, `correlationId` hoặc khóa định tuyến.

Trong Spring, `Message<T>` cung cấp `getPayload()` và `getHeaders()`. `MessageHeaders` là cấu trúc chỉ đọc sau khi message được tạo. Khi cần tạo message mới hoặc thay đổi header, hãy dùng `MessageBuilder` để tạo một message mới thay vì sửa trực tiếp map header của message hiện có.

```java
OrderCreated payload = message.getPayload();
MessageHeaders headers = message.getHeaders();

UUID messageId = headers.getId();
Long createdAtMillis = headers.getTimestamp();
Object contentType = headers.get(MessageHeaders.CONTENT_TYPE);
```

Một message có thể đi qua nhiều thành phần trong ứng dụng. Mỗi thành phần nên biết rõ dữ liệu nào thuộc payload và metadata nào thuộc header. Các trường nghiệp vụ cần được lưu bền vững và trao đổi giữa nhiều hệ thống thường nên có mặt trong schema payload hoặc một header nghiệp vụ được chuẩn hóa, không nên phụ thuộc vào metadata nội bộ chỉ tồn tại trong JVM.

## 2. Header `contentType`: định dạng của payload

`contentType` mô tả media type của payload, thường theo cú pháp MIME. Spring Cloud Stream sử dụng thông tin này trong quá trình chuyển đổi message giữa kiểu Java và dạng dữ liệu được truyền qua binder.

Một số giá trị thường gặp:

| Content type | Ý nghĩa | Ví dụ payload |
|---|---|---|
| `application/json` | Dữ liệu JSON | Object đơn hàng được serialize thành JSON |
| `text/plain` | Văn bản thuần | Mã đơn hàng hoặc thông báo ngắn |
| `application/octet-stream` | Dữ liệu nhị phân | Mảng byte hoặc nội dung file |
| `application/avro` | Dữ liệu Avro | Record được serialize theo schema Avro và cấu hình tương ứng |
| `application/x-protobuf` | Dữ liệu Protocol Buffers | Message được serialize theo schema Protobuf và cấu hình tương ứng |

Content type không tự chuyển đổi một payload bất kỳ thành định dạng tương ứng. Framework cần converter phù hợp; với Avro hoặc Protobuf, ứng dụng còn cần thư viện và quy tắc schema/serialization tương ứng. Khai báo sai content type có thể khiến consumer chọn nhầm converter hoặc không giải mã được dữ liệu.

### 2.1. Khai báo content type ở binding

Có thể đặt content type mặc định cho từng binding trong `application.yml`:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/json
        processOrder-in-0:
          destination: orders
          group: inventory-service
          content-type: application/json
```

`publishOrder-out-0` là binding đầu ra của hàm producer; `processOrder-in-0` là binding đầu vào của consumer. Cả hai phía cần thống nhất hợp đồng dữ liệu. Khai báo `content-type` giúp việc chọn converter rõ ràng theo binding và dễ quản lý giữa các profile môi trường.

Ví dụ producer phát một message JSON:

```java
@Bean
Supplier<Message<OrderCreated>> publishOrder() {
    return () -> {
        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(),
                "ord-100",
                new BigDecimal("29.90"),
                Instant.now(),
                List.of(new OrderItem("book-01", 2)));

        return MessageBuilder.withPayload(event)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .setHeader("eventId", event.eventId())
                .setHeader("occurredAt", event.occurredAt().toString())
                .build();
    };
}
```

Định nghĩa `OrderCreated` ở đây chỉ minh họa cấu trúc dữ liệu. Trong ứng dụng thật, event ID nên được tạo tại nơi phát sinh sự kiện và giữ ổn định qua retry hoặc phát lại. Không tạo một event ID mới mỗi lần retry cùng một sự kiện.

### 2.2. Đặt content type trực tiếp trên message

Khi một binding cần phát nhiều loại nội dung hoặc một hàm tạo message có metadata riêng, có thể gắn content type qua `MessageBuilder`:

```java
Message<byte[]> binaryMessage = MessageBuilder
        .withPayload(serializedBytes)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_OCTET_STREAM)
        .build();
```

`MessageHeaders.CONTENT_TYPE` là tên header chuẩn của Spring Messaging; `MimeTypeUtils` cung cấp các giá trị MIME thông dụng. Header có thể được đặt bằng một `MimeType` hoặc giá trị tương thích mà converter/binder hỗ trợ. Với binding thông thường, cấu hình content type ở binding thường dễ đọc và quản lý hơn; đặt trực tiếp trên message hữu ích khi cần metadata cụ thể cho từng message.

### 2.3. Content type và native encoding

Spring Cloud Stream có thể thực hiện chuyển đổi payload trong framework hoặc để client/broker serializer xử lý theo cấu hình native encoding/decoding của binder. Khi bật chế độ native, ứng dụng phải cấu hình serializer/deserializer và kiểu dữ liệu phù hợp với broker. Chỉ gắn header `contentType` không tự cấu hình serializer native, schema registry hay cơ chế tương thích schema.

Hãy xác định rõ bên nào chịu trách nhiệm serialize và deserialize. Không nên để producer serialize JSON thành chuỗi rồi khai báo payload là object chưa serialize, hoặc để consumer vừa giải mã native vừa yêu cầu framework chuyển đổi lần nữa. Kiểm thử round-trip qua broker thật để xác nhận bytes được tạo ra và đọc lại theo đúng hợp đồng.

## 3. Header `id`: nhận diện message instance

Spring Messaging cung cấp metadata `id` cho một message. Khi tạo message bằng `MessageBuilder`, Spring thường tự sinh một UUID nếu chưa có ID hợp lệ được giữ trong metadata. Có thể đọc giá trị bằng:

```java
UUID messageId = message.getHeaders().getId();
```

ID của Spring giúp nhận diện message instance trong quá trình xử lý ở ứng dụng. Header `id` và `timestamp` là metadata do framework quản lý; không nên cố gắng gán chúng như custom header. Header `id` không phải mã đơn hàng, mã giao dịch hay mã sự kiện nghiệp vụ. Khi một message được tạo mới trong bước biến đổi, message mới có thể có ID khác. Vì vậy, không dùng Spring message ID làm khóa idempotency lâu dài hoặc làm định danh nghiệp vụ xuyên suốt nhiều lần phát lại.

### 3.1. Phân biệt `id` và `eventId`

`eventId` là metadata do ứng dụng định nghĩa để nhận diện một sự kiện nghiệp vụ. Nó cần được tạo một lần tại nguồn phát sinh sự kiện và giữ ổn định khi message được retry, giao lại hoặc phát lại. `id` là định danh của message trong mô hình Spring Messaging.

| Thuộc tính | `id` | `eventId` |
|---|---|---|
| Chủ sở hữu | Spring Messaging/framework | Ứng dụng và hợp đồng sự kiện |
| Mục đích | Nhận diện message instance | Nhận diện sự kiện nghiệp vụ |
| Tính ổn định khi tạo message mới | Có thể thay đổi | Phải giữ nguyên nếu vẫn là cùng một sự kiện |
| Dùng làm idempotency key | Không nên | Có thể, nếu được tạo duy nhất và lưu/kiểm tra đúng cách |
| Nơi khai báo | Header `id` do framework quản lý | Trường payload hoặc custom header `eventId` |

Ví dụ consumer dùng event ID để chống xử lý lặp:

```java
@Bean
Consumer<Message<OrderCreated>> handleOrder() {
    return message -> {
        OrderCreated event = message.getPayload();
        String eventId = event.eventId();

        inventoryService.reserveOnce(eventId, event);
    };
}
```

`reserveOnce` cần lưu dấu xử lý bằng ràng buộc duy nhất hoặc giao dịch phù hợp trong kho dữ liệu. Chỉ kiểm tra một collection trong bộ nhớ hoặc so sánh Spring message ID không đủ để chống trùng giữa nhiều instance và qua lần khởi động lại.

## 4. Header `timestamp`: thời điểm tạo message

Spring Messaging cung cấp `timestamp` để ghi nhận thời điểm message được tạo, thường được biểu diễn bằng số mili giây kể từ Unix epoch (UTC). Có thể đọc giá trị bằng:

```java
Long timestampMillis = message.getHeaders().getTimestamp();
Instant messageCreatedAt = timestampMillis == null
        ? null
        : Instant.ofEpochMilli(timestampMillis);
```

Khi message được tạo bằng `MessageBuilder`, Spring thường tự điền timestamp nếu metadata chưa có giá trị. Đây là thời điểm tạo message trong mô hình Spring; nó không nhất thiết là thời điểm sự kiện nghiệp vụ đã xảy ra, thời điểm producer ghi record vào broker hoặc thời điểm consumer nhận message.

### 4.1. Phân biệt `timestamp` và `occurredAt`

Một đơn hàng có thể được tạo lúc 09:00 nhưng đến 09:03 mới được phát thành message vì ứng dụng phải chờ một giao dịch hoàn tất. Consumer có thể nhận message lúc 09:04. Ba mốc thời gian này có ý nghĩa khác nhau:

| Mốc | Ý nghĩa | Ví dụ |
|---|---|---|
| `occurredAt` | Thời điểm nghiệp vụ xảy ra, do domain event ghi nhận | Đơn hàng được tạo lúc 09:00 |
| Spring `timestamp` | Thời điểm message được tạo trong ứng dụng | Producer dựng message lúc 09:03 |
| Thời điểm nhận/ingest | Thời điểm broker hoặc consumer quan sát message | Consumer nhận lúc 09:04 |

Nếu cần phân tích độ trễ nghiệp vụ, phát hiện sự kiện đến muộn hoặc sắp xếp theo thời gian nghiệp vụ, hãy đưa `occurredAt` vào payload hoặc custom header với quy ước timezone rõ ràng. Nên dùng ISO-8601 UTC, ví dụ `2026-11-24T02:00:00Z`, để tránh hiểu nhầm múi giờ. Nếu cần thời điểm broker nhận record, hãy dùng metadata do broker cung cấp và hiểu đúng ngữ nghĩa của broker đó.

Không dùng Spring `timestamp` thay cho `occurredAt` trong báo cáo nghiệp vụ. Sự khác nhau giữa event time và processing time đặc biệt quan trọng với dữ liệu đến trễ, retry kéo dài và xử lý theo cửa sổ thời gian.

## 5. Tạo message với metadata rõ ràng

Ví dụ sau nhận một message, tạo kết quả mới và giữ lại các header nghiệp vụ cần thiết:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderValidated>> validateOrder() {
    return input -> {
        OrderCreated event = input.getPayload();
        OrderValidated result = new OrderValidated(
                event.eventId(),
                event.orderId(),
                event.total());

        MessageBuilder<OrderValidated> builder = MessageBuilder
                .withPayload(result)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .setHeader("eventId", event.eventId())
                .setHeader("occurredAt", event.occurredAt().toString());

        String correlationId = input.getHeaders().get("correlationId", String.class);
        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }

        return builder.build();
    };
}
```

Ở đây:

- Payload đầu ra có kiểu `OrderValidated`, không sửa payload đầu vào.
- `contentType` cho biết payload đầu ra là JSON.
- `eventId` giữ định danh của sự kiện gốc nếu đây vẫn là cùng sự kiện được biến đổi.
- `occurredAt` giữ thời điểm nghiệp vụ, còn Spring quản lý `id` và `timestamp` của message được tạo.
- `correlationId` được sao chép có chủ đích để liên kết các bước xử lý trong cùng một luồng nghiệp vụ.

Nếu bước xử lý tạo ra một sự kiện nghiệp vụ mới, hãy tạo `eventId` mới cho sự kiện đó và có thể giữ `correlationId` hoặc thêm `causationId` để truy vết quan hệ với sự kiện nguồn. Không sao chép toàn bộ header một cách máy móc: một số header có thể mang thông tin điều khiển nội bộ, routing hoặc kênh trả lời chỉ có ý nghĩa trong phạm vi message channel của ứng dụng.

## 6. Header tùy chỉnh và khả năng ánh xạ qua broker

Ứng dụng có thể định nghĩa các header như `eventId`, `correlationId`, `causationId`, `occurredAt`, `tenantId` hoặc `schemaVersion`. Trước khi dùng, nhóm nên thống nhất tên, kiểu dữ liệu, ý nghĩa, nguồn tạo và quy tắc giữ lại khi message đi qua nhiều dịch vụ.

Không phải mọi header Spring đều được truyền qua broker theo cùng một cách. Binder phải ánh xạ metadata của Spring sang cấu trúc header/property của broker và ngược lại. Mỗi broker có giới hạn về kiểu dữ liệu, kích thước, encoding và tên header:

| Broker | Cơ chế metadata ở mức broker | Điều cần kiểm tra |
|---|---|---|
| Kafka | Record headers, giá trị header ở dạng byte array | Mapper chuyển kiểu dữ liệu Spring thành bytes và khôi phục đúng giá trị khi consumer nhận |
| RabbitMQ | AMQP message properties và headers field table | Kiểu giá trị được AMQP hỗ trợ, tên header và cấu hình header mapper |
| Pulsar | Message properties gắn với message | Kiểu dữ liệu và cách binder chuyển header thành property, đặc biệt với giá trị không phải chuỗi |

Vì vậy, nên ưu tiên giá trị header đơn giản như chuỗi, số, boolean hoặc byte array theo khả năng binder. Tránh đưa object Java tùy ý, collection lớn hoặc dữ liệu nhạy cảm vào header. Một custom header có thể tồn tại trong message nội bộ nhưng bị bỏ qua, chuyển đổi kiểu hoặc không được bảo toàn khi đi qua broker nếu binder không hỗ trợ mapping đó.

Nếu cần một giá trị có ý nghĩa lâu dài đối với consumer, hãy cân nhắc đưa nó vào payload schema. Header phù hợp hơn với metadata điều khiển, định tuyến, correlation hoặc thông tin biểu diễn nội dung. Dù chọn payload hay header, hợp đồng phải được tài liệu hóa và kiểm thử tương thích.

## 7. Kiểm tra header trong ứng dụng

Có thể kiểm tra metadata ở mức đơn vị mà không cần broker:

```java
@Test
void messageContainsContentTypeAndFrameworkMetadata() {
    OrderCreated payload = sampleOrder();

    Message<OrderCreated> message = MessageBuilder.withPayload(payload)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventId", payload.eventId())
            .build();

    assertThat(message.getPayload()).isEqualTo(payload);
    assertThat(message.getHeaders().get(MessageHeaders.CONTENT_TYPE))
            .isEqualTo(MimeTypeUtils.APPLICATION_JSON);
    assertThat(message.getHeaders().getId()).isNotNull();
    assertThat(message.getHeaders().getTimestamp()).isNotNull();
    assertThat(message.getHeaders().get("eventId")).isEqualTo(payload.eventId());
}
```

Kiểm thử đơn vị xác nhận message được tạo đúng trong JVM. Nó không chứng minh binder đã truyền tất cả header qua Kafka, RabbitMQ hoặc Pulsar. Cần có kiểm thử tích hợp để:

1. Publish một message có `contentType`, `eventId`, `correlationId` và `occurredAt`.
2. Nhận message ở consumer qua broker thật.
3. Kiểm tra payload được deserialize đúng kiểu và nội dung.
4. Kiểm tra các custom header quan trọng còn nguyên giá trị và đúng kiểu.
5. Quan sát `id` và `timestamp` sau khi message đi qua binder, không giả định chúng được bảo toàn giống hệt giữa mọi broker.
6. Kiểm tra trường hợp header không hỗ trợ, sai content type hoặc payload không tương thích schema.

Khi debug, có thể log `eventId`, `correlationId`, `contentType`, message ID và timestamp. Tránh log toàn bộ payload hoặc header chứa token, thông tin xác thực và dữ liệu cá nhân. Log cần phân biệt message ID với event ID để nhóm vận hành không nhầm một lần tạo message mới thành một sự kiện nghiệp vụ mới.

## 8. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer không deserialize được payload | `contentType` không khớp định dạng thực tế hoặc thiếu converter | Đồng bộ content type, serializer và converter giữa producer/consumer |
| JSON bị nhận như chuỗi hoặc byte array | Binding/native encoding được cấu hình khác với mong đợi | Kiểm tra content type và cấu hình native encoding/decoding ở cả hai phía |
| Header `eventId` không có ở consumer | Binder không map header, tên header khác hoặc header bị lọc | Kiểm tra header mapper và kiểm thử qua broker thực |
| Dùng `id` để chống trùng nhưng vẫn xử lý lặp | Message mới có ID khác hoặc broker redelivery không giữ metadata như dự kiến | Dùng `eventId` ổn định do ứng dụng quản lý và lưu dấu xử lý bền vững |
| Timestamp không phản ánh thời điểm nghiệp vụ | Đang đọc thời điểm tạo message thay vì `occurredAt` | Thêm event time vào payload hoặc custom header theo định dạng UTC |
| Header có kiểu khác khi nhận | Broker/binder chuyển đổi giá trị theo kiểu được hỗ trợ | Chuẩn hóa kiểu header, ví dụ ISO-8601 string hoặc số, rồi kiểm thử mapping |
| Message mới mất correlation ID | Hàm tạo message đầu ra không sao chép header cần thiết | Chọn và truyền tiếp các header nghiệp vụ/trace cần giữ một cách có chủ đích |

## 9. Quy tắc thiết kế header trước khi triển khai

- [ ] `contentType` được khai báo rõ ở binding hoặc message và khớp với cách serialize payload.
- [ ] Producer và consumer thống nhất schema, converter hoặc native serializer/deserializer.
- [ ] `id` được hiểu là định danh message của Spring, không dùng làm khóa nghiệp vụ lâu dài.
- [ ] `eventId` ổn định qua retry và phát lại; consumer dùng nó cho idempotency khi phù hợp.
- [ ] `timestamp` được hiểu là metadata thời điểm tạo message; event time được biểu diễn riêng bằng `occurredAt`.
- [ ] `correlationId` và `causationId` có quy ước rõ để truy vết qua nhiều dịch vụ.
- [ ] Header tùy chỉnh có tên, kiểu, kích thước và ý nghĩa được tài liệu hóa.
- [ ] Header quan trọng được kiểm thử mapping qua đúng binder và broker triển khai.
- [ ] Không đưa bí mật hoặc payload lớn vào header; không sao chép header điều khiển nội bộ một cách tùy tiện.

`contentType`, `id` và `timestamp` giúp Spring Cloud Stream xử lý và mô tả message, nhưng mỗi header có phạm vi riêng. Content type hỗ trợ chọn cách chuyển đổi payload; ID nhận diện message instance; timestamp ghi thời điểm tạo message. Ứng dụng vẫn cần định nghĩa event ID, event time và correlation metadata theo hợp đồng nghiệp vụ, đồng thời kiểm thử việc ánh xạ header qua broker thực tế để bảo đảm consumer nhận được đúng dữ liệu cần thiết.
