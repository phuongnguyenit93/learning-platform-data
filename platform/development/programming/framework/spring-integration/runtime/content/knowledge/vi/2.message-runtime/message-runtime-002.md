# MessageHeaders, message id và timestamp

Trong Spring Integration, một message đi qua channel và các endpoint luôn mang theo hai phần: **payload** chứa dữ liệu cần xử lý và **headers** chứa metadata mô tả message. Payload trả lời câu hỏi “đang xử lý dữ liệu gì”; headers giúp runtime và ứng dụng biết message đến từ đâu, cần được định tuyến hoặc tương quan ra sao, và đang được quan sát dưới định danh nào.

`MessageHeaders` là nơi lưu metadata đó. Hai header mặc định cần hiểu rõ là `id` và `timestamp`: `id` định danh một message instance, còn `timestamp` ghi lại thời điểm message được tạo. Hiểu đúng vòng đời của hai giá trị này giúp đọc log, lần theo message qua flow và tránh dùng nhầm chúng làm mã nghiệp vụ hoặc thời gian phát sinh sự kiện.

Sau bài này, bạn có thể:

- Đọc payload và headers từ `Message<T>`.
- Giải thích vai trò, kiểu dữ liệu và vòng đời của `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP`.
- Tạo message mới, sao chép headers và nhận biết khi nào ID/timestamp được tạo lại.
- Phân biệt message ID, correlation ID, business ID và event time khi theo dõi một flow.

## 1. Message gồm payload và headers

Spring Messaging định nghĩa message qua interface `Message<T>`. Một message có payload kiểu `T` và một đối tượng `MessageHeaders`:

```text
Message<T>
├── payload: T
└── headers: MessageHeaders
    ├── id
    ├── timestamp
    └── các header khác
```

Ví dụ, khi một flow nhận đơn hàng, payload có thể là `Order`; headers có thể chứa `source`, `tenantId`, `correlationId` hoặc thông tin phục vụ định tuyến. Những thông tin này bổ sung ngữ cảnh cho payload mà không cần biến chúng thành thuộc tính của đối tượng nghiệp vụ.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("source", "checkout")
        .setHeader("tenantId", "tenant-01")
        .build();

Order payload = message.getPayload();
MessageHeaders headers = message.getHeaders();
```

Channel truyền `Message<?>` giữa producer và consumer. Một `DirectChannel`, `QueueChannel` hay `ExecutorChannel` có cách phân phối và ảnh hưởng đến luồng thực thi khác nhau, nhưng message mà endpoint nhận vẫn có cả payload lẫn headers. Vì vậy, headers là metadata gắn với message trong quá trình điều phối, không phải một kho trạng thái dùng chung của channel.

## 2. MessageHeaders là metadata bất biến

`MessageHeaders` triển khai `Map<String, Object>` nên có thể đọc header theo tên. Tuy nhiên, map này là **immutable**: không thể gọi `put`, `remove` hoặc thay đổi trực tiếp một header sau khi message đã được tạo. Thao tác sửa map sẽ thất bại với `UnsupportedOperationException`.

Để thay đổi metadata, hãy dựng một message mới bằng `MessageBuilder` hoặc dùng endpoint chuyên dụng như header enricher. Cách này giữ mô hình message bất biến: một message đã được phát đi không bị consumer âm thầm thay đổi nội dung metadata của nó.

```java
String source = message.getHeaders().get("source", String.class);
Object tenant = message.getHeaders().get("tenantId");
```

Khi biết kiểu dữ liệu mong muốn, nên dùng overload `get(name, Type.class)`. Cách đọc này thể hiện rõ kiểu kỳ vọng và tránh ép kiểu thủ công. Với header do ứng dụng tự định nghĩa, hãy thống nhất tên, kiểu dữ liệu và ý nghĩa giữa producer với consumer.

Map headers bất biến không có nghĩa mọi object được đặt bên trong đều tự động bất biến. Nếu một header chứa `List`, `Map` hoặc object tùy chỉnh có thể thay đổi, nơi khác vẫn có thể sửa object đó nếu còn giữ tham chiếu. Ưu tiên giá trị đơn giản, bất biến và có thể serialize khi message cần đi qua message store hoặc ranh giới hệ thống.

## 3. Hai header mặc định: id và timestamp

Spring Messaging cung cấp tên header chuẩn qua các hằng số trong `MessageHeaders`, tránh viết chuỗi tùy ý:

| Header | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `MessageHeaders.ID` | `UUID` | Định danh của một message instance. |
| `MessageHeaders.TIMESTAMP` | `Long` | Thời điểm message được tạo, tính bằng milliseconds từ Unix epoch. |

Có thể đọc hai giá trị này qua getter chuyên dụng:

```java
import java.time.Instant;
import java.util.UUID;

UUID messageId = message.getHeaders().getId();
Long timestampMillis = message.getHeaders().getTimestamp();

Instant createdAt = timestampMillis == null
        ? null
        : Instant.ofEpochMilli(timestampMillis);
```

Thông thường framework tự sinh hai header khi tạo message. `id` mặc định là UUID được sinh bởi cơ chế ID generator đang cấu hình. `timestamp` là thời gian theo đồng hồ hệ thống tại thời điểm headers được dựng. Getter có thể được khai báo nullable, vì vậy code dùng chung hoặc làm việc với message được deserialize nên xử lý trường hợp thiếu giá trị.

Hai header này là header chỉ đọc trong luồng tạo message thông thường. Không dùng `setHeader("id", ...)` hoặc `setHeader("timestamp", ...)` để gán giá trị tùy ý. `MessageBuilder` không cho ghi đè các header chỉ đọc này; khi tạo message mới, framework quản lý ID và timestamp của instance mới.

### 3.1. Message ID định danh một instance

Message ID trả lời câu hỏi: **đây là instance message nào?** Nó hữu ích khi ghi log, đối chiếu một lần giao nhận hoặc nhận biết message nào đã được một endpoint xử lý.

ID không phải mã đơn hàng, mã khách hàng hay khóa idempotency. Một đơn hàng có thể tạo ra nhiều message trong suốt vòng đời xử lý; mỗi message instance có ID riêng. Ngược lại, nếu cần nhận biết nhiều message cùng thuộc một nghiệp vụ, hãy dùng business ID hoặc correlation ID có ý nghĩa ổn định.

Message ID cũng không phải thứ tự xử lý. UUID không biểu thị message nào đến trước hoặc sau, và không nên dùng ID để sắp xếp message.

### 3.2. Timestamp ghi thời điểm tạo message

Timestamp được biểu diễn bằng số milliseconds kể từ `1970-01-01T00:00:00Z` (Unix epoch). Có thể chuyển sang `Instant` để log hoặc hiển thị:

```java
Long value = message.getHeaders().getTimestamp();
if (value != null) {
    log.debug("message createdAt={}", Instant.ofEpochMilli(value));
}
```

Timestamp này là thời điểm message được tạo trong runtime, không mặc nhiên là thời điểm người dùng tạo đơn hàng, thời điểm sự kiện xảy ra ở hệ thống nguồn hoặc thời điểm consumer bắt đầu xử lý. Nếu cần giữ thời gian nghiệp vụ, hãy truyền một header riêng như `eventCreatedAt` hoặc lưu thời gian đó trong payload.

Timestamp dùng đồng hồ thời gian thực của máy. Đồng hồ có thể được đồng bộ hoặc điều chỉnh, và hai node có thể lệch giờ. Vì vậy, không dùng timestamp làm đồng hồ đo thời lượng có độ chính xác cao hoặc làm cơ sở duy nhất để sắp thứ tự message trên nhiều máy.

## 4. ID và timestamp thay đổi khi tạo message mới

Điểm quan trọng trong Spring Integration là message được xem như bất biến. Khi một component tạo message mới dựa trên message cũ, đó là một message instance mới. `id` và `timestamp` được tạo lại cho instance mới; các header nghiệp vụ khác có thể được sao chép tùy API và cấu hình.

Ví dụ, `MessageBuilder.fromMessage(...)` khởi tạo builder từ payload và headers của message đầu vào. Khi `build()`, builder tạo message mới. Hai header chỉ đọc `id` và `timestamp` không được sao chép để ghi đè giá trị của message mới:

```java
Message<Order> normalized = MessageBuilder
        .fromMessage(message)
        .setHeader("validated", true)
        .build();

UUID originalId = message.getHeaders().getId();
UUID normalizedId = normalized.getHeaders().getId();
// normalized là message instance mới, có ID mới.
```

Các header như `source` hoặc `tenantId` được sao chép từ message đầu vào nếu builder không loại bỏ hoặc thay thế chúng. Header `validated` được thêm vào message mới. Map headers của message ban đầu vẫn không đổi.

Ngược lại, nếu một endpoint chuyển tiếp nguyên message mà không dựng instance mới, ID và timestamp hiện tại vẫn gắn với message đó. Khi đọc log, hãy xác định endpoint có tạo message mới hay chỉ chuyển tiếp message trước khi kết luận vì sao ID hoặc timestamp thay đổi.

Quy tắc này cũng giải thích vì sao timestamp không phải lúc nào cũng đo được tổng thời gian từ đầu flow. Nếu một transformer hoặc enricher tạo message mới giữa flow, timestamp phản ánh lần tạo mới đó. Muốn đo latency, nên dùng metrics/observation hoặc cơ chế tracing; nếu tự đo, cần xác định rõ mốc bắt đầu và mốc kết thúc.

## 5. Phân biệt message ID, correlation ID và mã nghiệp vụ

Ba loại định danh thường xuất hiện cạnh nhau nhưng phục vụ các mục đích khác nhau:

| Giá trị | Câu hỏi được trả lời | Ví dụ sử dụng |
|---|---|---|
| Message ID (`id`) | Đây là message instance nào? | Đối chiếu log của một lần giao nhận. |
| Correlation ID (`correlationId`) | Message này thuộc nhóm hoặc luồng nghiệp vụ nào? | Gom các message do splitter tạo ra để aggregator tổng hợp. |
| Business ID (`orderId`) | Đối tượng nghiệp vụ nào đang được xử lý? | Tra cứu đơn hàng trong database hoặc API nghiệp vụ. |
| Trace ID | Các thao tác phân tán này thuộc trace nào? | Theo dõi request qua nhiều service và span. |

Spring Integration có các header phục vụ correlation và sequence, chẳng hạn `CORRELATION_ID`, `SEQUENCE_NUMBER` và `SEQUENCE_SIZE` trong `IntegrationMessageHeaderAccessor`. Với một nhóm message được tạo bởi splitter, correlation ID giúp nhận biết chúng thuộc cùng nhóm; sequence number và sequence size mô tả vị trí và kích thước nhóm. Các giá trị này không thay thế message ID của từng phần tử.

Ví dụ một đơn hàng `order-42` có thể tạo ba message con:

```text
orderId = order-42
correlationId = group-7
├── message id = UUID-A, sequenceNumber = 1
├── message id = UUID-B, sequenceNumber = 2
└── message id = UUID-C, sequenceNumber = 3
```

Ba message có ID khác nhau nhưng cùng correlation ID và business ID. Khi aggregator phát message kết quả, kết quả đó lại là một message instance với ID và timestamp của chính nó. Vì thế, log vận hành nên ghi các định danh cần thiết cùng nhau thay vì chỉ ghi `id`.

## 6. Quan sát headers trong message flow

Có thể nhận toàn bộ `Message<?>` ở một consumer để quan sát payload và metadata:

```java
@ServiceActivator(inputChannel = "orders")
public void handle(Message<Order> message) {
    UUID id = message.getHeaders().getId();
    Long timestamp = message.getHeaders().getTimestamp();
    String tenantId = message.getHeaders().get("tenantId", String.class);

    log.info("received messageId={}, timestamp={}, tenantId={}, orderId={}",
            id,
            timestamp,
            tenantId,
            message.getPayload().getId());

    // Xử lý payload của đơn hàng.
}
```

Khi chẩn đoán flow, so sánh ID ở các điểm nhận message:

1. Ghi ID, timestamp, correlation ID và business ID tại điểm vào flow.
2. Ghi lại các giá trị tương tự sau transformer, enricher hoặc handler có tạo message mới.
3. Nếu ID thay đổi, kiểm tra component vừa tạo message mới và cách nó sao chép headers.
4. Nếu timestamp tăng ở một chặng, xác định đó là thời điểm message mới được tạo hay mốc thời gian nghiệp vụ.
5. Nếu message đi qua adapter hoặc broker, kiểm tra mapping headers của adapter; không mặc định mọi header nội bộ đều được chuyển nguyên vẹn sang giao thức bên ngoài.

Channel ảnh hưởng đến thời điểm consumer nhận và xử lý message. Với `DirectChannel`, consumer thường được gọi đồng bộ trong luồng gửi. Với `QueueChannel` hoặc `ExecutorChannel`, message có thể chờ hoặc được xử lý ở luồng khác. Timestamp của message vẫn là timestamp được tạo trước đó, trừ khi có component dựng lại message. Vì vậy, một message chờ lâu trong queue không tự động có timestamp mới khi consumer bắt đầu chạy.

Khi message được lưu vào message store hoặc chuyển qua giao thức ngoài, khả năng lưu/chuyển header còn phụ thuộc kiểu dữ liệu và cấu hình serializer/header mapper. Nên dùng header có kiểu dữ liệu ổn định, có thể serialize, và xác minh rõ những header nào được giữ lại qua ranh giới hệ thống.

## 7. Lỗi thường gặp và cách tránh

| Cách làm dễ gây lỗi | Vì sao không phù hợp | Cách xử lý |
|---|---|---|
| Dùng `id` làm `orderId` hoặc khóa chống xử lý trùng | ID nhận diện message instance và có thể đổi khi tạo message mới. | Dùng business ID hoặc idempotency key riêng. |
| Dùng `timestamp` làm thời điểm phát sinh nghiệp vụ | Timestamp ghi thời điểm tạo message trong runtime. | Truyền `eventCreatedAt` riêng và quy định rõ timezone/format. |
| Gán trực tiếp `headers.put(...)` | `MessageHeaders` là immutable. | Dùng `MessageBuilder` hoặc header enricher. |
| Cố gắng tự gán `id`/`timestamp` | Đây là các header chỉ đọc được framework quản lý. | Dùng header riêng nếu cần một mã hoặc mốc thời gian do ứng dụng kiểm soát. |
| Chỉ log message ID | Không thể hiện các message có cùng thuộc một nghiệp vụ hay không. | Log thêm correlation ID, business ID và trace ID khi có. |
| Đặt object mutable hoặc dữ liệu nhạy cảm vào header | Có thể gây thay đổi ngoài dự kiến, lỗi serialize hoặc lộ dữ liệu trong log. | Ưu tiên metadata nhỏ, bất biến; chỉ log các trường cần thiết. |

Một lưu ý khi điều tra lỗi: hai log có cùng message ID thường cho thấy cùng message instance được quan sát ở nhiều điểm; hai log có ID khác nhau chưa đủ để kết luận là hai nghiệp vụ khác nhau. Hãy đối chiếu thêm correlation ID và business ID.

## 8. Tự kiểm tra

**Tình huống:** Một flow nhận `Order`, thêm header `validated=true`, sau đó gửi message đến `QueueChannel`. Consumer ghi log thấy ID khác ID được ghi ở đầu flow.

1. Nếu bước thêm header tạo message bằng `MessageBuilder.fromMessage(...).build()`, ID mới có phải là hành vi bình thường không?
2. Nếu consumer nhận message sau vài giây chờ queue, timestamp có tự động chuyển thành thời điểm consumer bắt đầu xử lý không?
3. Nếu muốn tìm tất cả message liên quan đến cùng một đơn hàng, nên đối chiếu header nào?

**Gợi ý trả lời:** (1) Có. Builder tạo message instance mới nên ID và timestamp được tạo lại. (2) Không. Timestamp vẫn là thời điểm tạo message gần nhất, trừ khi có bước tạo message mới tiếp theo. (3) Dùng business ID như `orderId`; nếu cần nhóm các message trong một nhánh xử lý, dùng correlation ID. Message ID vẫn hữu ích để lần theo từng instance.

## Tài liệu tham khảo

- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html)
- [Spring Framework Javadoc — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
