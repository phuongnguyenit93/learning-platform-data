# MessageHeaders và truy cập metadata của thông điệp

## Mục tiêu

Trong Spring Messaging, payload chứa dữ liệu nghiệp vụ chính, còn headers chứa metadata mô tả cách message được tạo, theo dõi, định tuyến hoặc xử lý. Biết cách đọc và xây dựng headers giúp các thành phần giao tiếp với nhau mà không phải nhồi thông tin vận chuyển vào payload.

Sau bài này, bạn có thể:

- Giải thích vai trò của `MessageHeaders` trong một `Message`.
- Đọc header an toàn bằng tên hoặc kiểu dữ liệu.
- Tạo và sao chép headers bằng `MessageBuilder`.
- Phân biệt `MessageHeaders` bất biến với `MessageHeaderAccessor` dùng để thay đổi metadata trong giai đoạn xây dựng message.
- Dùng `@Header` và `@Headers` để nhận metadata trong handler.
- Nhận biết header của Spring Messaging, Spring Integration và protocol bên ngoài.
- Tránh lỗi khi sao chép, truyền qua broker, ghi log hoặc xử lý dữ liệu không đáng tin cậy.

## 1. Message gồm payload và headers

Spring biểu diễn một thông điệp bằng interface `Message<T>`. Một message có hai phần:

- **Payload:** nội dung chính, ví dụ `OrderCreated`, chuỗi văn bản, byte array hoặc một đối tượng nghiệp vụ.
- **Headers:** một tập cặp khóa–giá trị `String → Object`, cung cấp metadata đi kèm payload.

Ví dụ về mặt khái niệm:

~~~text
Message<OrderCreated>
  payload:
    orderId = "ORD-42"
    total = 250000

  headers:
    id = 4c1...
    timestamp = 1794020000000
    contentType = application/json
    traceId = "trace-2026-001"
    source = "checkout-service"
~~~

Payload trả lời câu hỏi “thông điệp mang dữ liệu gì?”. Headers trả lời “thông điệp có thông tin gì để hệ thống theo dõi, định tuyến hoặc xử lý?”.

Một số ví dụ:

- `traceId`: nối các log/span của cùng một request qua nhiều service.
- `correlationId`: liên kết request với reply hoặc liên kết các message thuộc cùng một luồng nghiệp vụ.
- `contentType`: mô tả định dạng nội dung, chẳng hạn JSON hoặc văn bản.
- `replyChannel`: địa chỉ trả lời trong một luồng request/reply của Spring.
- `priority`: mức ưu tiên khi channel hoặc adapter có hỗ trợ xử lý theo độ ưu tiên.

Không phải mọi header đều được mọi module sử dụng. Ý nghĩa của một header phụ thuộc API, channel, adapter và protocol đang chạy.

## 2. MessageHeaders là gì?

`org.springframework.messaging.MessageHeaders` là lớp chứa headers của một message. Lớp này triển khai `Map<String, Object>`, nên có thể đọc bằng các thao tác Map quen thuộc:

~~~java
MessageHeaders headers = message.getHeaders();

Object traceId = headers.get("traceId");
boolean hasTenant = headers.containsKey("tenantId");
Set<String> names = headers.keySet();
~~~

Tuy nhiên, `MessageHeaders` là **bất biến**. Các thao tác thay đổi Map như `put`, `putAll`, `remove` hoặc `clear` sẽ ném `UnsupportedOperationException`.

~~~java
// Không hợp lệ: MessageHeaders không cho sửa trực tiếp.
message.getHeaders().put("traceId", "new-value");
~~~

Muốn thêm, thay hoặc xóa header, hãy tạo message mới bằng `MessageBuilder` hoặc dùng `MessageHeaderAccessor`. Thiết kế bất biến giúp message có thể được truyền qua nhiều thành phần mà metadata không bị một consumer tùy ý thay đổi.

Lưu ý: tính bất biến của `MessageHeaders` áp dụng cho cấu trúc Map. Nếu bạn đặt một object có thể thay đổi vào header, object đó vẫn có thể bị thay đổi thông qua reference của nó. Vì vậy, nên ưu tiên giá trị bất biến như String, số, UUID, MimeType hoặc các kiểu dữ liệu đơn giản có hợp đồng rõ ràng.

## 3. Các header chuẩn của Spring Messaging

`MessageHeaders` định nghĩa các hằng số tên header cốt lõi:

| Hằng số | Ý nghĩa | Kiểu/giá trị thường gặp |
|---|---|---|
| `MessageHeaders.ID` | Định danh của message | `UUID` được tạo tự động |
| `MessageHeaders.TIMESTAMP` | Thời điểm tạo message | `Long` |
| `MessageHeaders.CONTENT_TYPE` | Kiểu nội dung payload | `MimeType`, ví dụ `application/json` |
| `MessageHeaders.REPLY_CHANNEL` | Nơi nhận reply | `MessageChannel` hoặc tên channel tùy cách cấu hình |
| `MessageHeaders.ERROR_CHANNEL` | Nơi chuyển lỗi trong messaging flow | `MessageChannel` hoặc tên channel tùy cách cấu hình |

### ID và timestamp

Khi tạo `MessageHeaders`, Spring tự thêm ID và timestamp. ID mặc định là UUID. Đây là metadata do framework quản lý:

- Không tự đặt `MessageHeaders.ID` như một business ID.
- Không dùng ID của message để thay thế order ID, event ID hoặc correlation ID.
- Không ghi đè ID/timestamp khi copy headers bằng `MessageBuilder`; các giá trị này được bảo vệ và message mới sẽ có metadata tạo mới theo cơ chế của framework.
- Nếu nghiệp vụ cần thời điểm sự kiện thực sự xảy ra, hãy tạo header riêng như `occurredAt` hoặc đưa thời điểm nghiệp vụ vào payload. Timestamp của message là thời điểm tạo message trong ứng dụng, không nhất thiết là thời điểm sự kiện nghiệp vụ phát sinh.

ID trả lời “đây là message instance nào?”. Correlation ID trả lời “message này thuộc cùng request hoặc workflow nào?”. Trace ID trả lời “các thao tác phân tán này thuộc cùng một trace nào?”. Ba giá trị có thể khác nhau và không nên dùng thay thế tùy tiện.

### Content type

`CONTENT_TYPE` mô tả định dạng nội dung. Ví dụ:

~~~java
.setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
~~~

Hoặc dùng `MessageHeaderAccessor.setContentType(MimeType)`.

Header này là metadata để các converter hoặc adapter có thể chọn cách xử lý phù hợp. Chỉ đặt `application/json` không tự biến một object Java thành JSON; việc chuyển đổi vẫn phụ thuộc `MessageConverter`, serializer và cấu hình của transport.

### Reply channel và error channel

Hai header này hỗ trợ một số mô hình xử lý trong Spring:

- `REPLY_CHANNEL` cho biết nơi chuyển kết quả trả lời.
- `ERROR_CHANNEL` cho biết nơi chuyển thông điệp lỗi trong một flow có cấu hình error handling.

Giá trị có thể là một channel object hoặc tên channel, tùy API. Một `MessageChannel` trong bộ nhớ thường chỉ có ý nghĩa bên trong ứng dụng. Khi message đi qua broker hoặc được serialize, không nên giả định object channel cục bộ có thể truyền nguyên trạng sang tiến trình khác. Với hệ thống phân tán, hãy dùng địa chỉ hoặc cơ chế reply/routing mà protocol và adapter hỗ trợ.

## 4. Đọc header và kiểm tra kiểu dữ liệu

Có thể đọc giá trị theo hai cách:

~~~java
Object raw = headers.get("retryCount");
Integer retryCount = headers.get("retryCount", Integer.class);
~~~

Cách thứ hai giúp thể hiện kiểu dữ liệu mong đợi ngay tại vị trí đọc. Nó không phải là cơ chế chuyển đổi tùy ý từ chuỗi sang số. Producer và consumer cần thống nhất kiểu của header.

Một số thao tác hữu ích:

~~~java
String traceId = headers.get("traceId", String.class);

if (headers.containsKey("tenantId")) {
    String tenantId = headers.get("tenantId", String.class);
}

Object replyChannel = headers.getReplyChannel();
UUID messageId = headers.getId();
Long createdAt = headers.getTimestamp();
~~~

Khi header có thể vắng mặt, hãy xử lý trường hợp `null`:

~~~java
String traceId = headers.get("traceId", String.class);
if (traceId == null || traceId.isBlank()) {
    // Dùng fallback hoặc từ chối message theo quy tắc nghiệp vụ.
}
~~~

Đừng ép kiểu trực tiếp khi chưa kiểm tra hợp đồng dữ liệu:

~~~java
// Dễ gây ClassCastException nếu producer gửi retryCount dưới dạng String.
Integer retryCount = (Integer) headers.get("retryCount");
~~~

Nên quy định rõ tên header, kiểu dữ liệu, đơn vị đo, giá trị mặc định và ý nghĩa của nó. Ví dụ, `timeoutMs` dễ hiểu hơn `timeout` nếu giá trị là mili giây.

## 5. Tạo message và gắn metadata bằng MessageBuilder

Cách thông dụng để tạo message là `MessageBuilder.withPayload(...)`. Builder cho phép thêm, thay hoặc xóa header trước khi gọi `build()`.

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("traceId", "trace-2026-001")
        .setHeader("source", "checkout-service")
        .setHeader("tenantId", "tenant-a")
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();
~~~

Một số phương thức quan trọng:

| Phương thức | Hành vi |
|---|---|
| `setHeader(name, value)` | Thêm hoặc thay giá trị header. Nếu value là `null`, header đó bị loại bỏ. |
| `setHeaderIfAbsent(name, value)` | Chỉ đặt nếu header chưa có giá trị. |
| `copyHeaders(map)` | Copy các cặp khóa–giá trị; giá trị hiện có có thể bị ghi đè. ID và timestamp vẫn được bảo vệ. |
| `copyHeadersIfAbsent(map)` | Chỉ copy các header chưa tồn tại, không ghi đè giá trị hiện có. |
| `removeHeader(name)` | Xóa một header khỏi message mới đang xây dựng. |
| `removeHeaders(patterns)` | Xóa các header khớp mẫu tên được hỗ trợ. |
| `build()` | Tạo message mới với payload và headers đã cấu hình. |

Ví dụ về khác biệt giữa copy có ghi đè và copy nếu chưa có:

~~~java
Map<String, Object> incoming = Map.of(
        "traceId", "trace-from-upstream",
        "source", "gateway"
);

Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("traceId", "trace-created-here")
        .copyHeaders(incoming)
        .build();

// traceId = "trace-from-upstream"
// source  = "gateway"
~~~

Nếu đổi `copyHeaders(incoming)` thành `copyHeadersIfAbsent(incoming)`, giá trị `traceId` đã được đặt trước đó vẫn là `trace-created-here`.

Để tạo message mới từ message cũ:

~~~java
Message<String> enriched = MessageBuilder.fromMessage(message)
        .setHeader("processedBy", "order-handler")
        .build();
~~~

`fromMessage` khởi tạo builder với payload và headers đã copy từ message gốc. Đây vẫn là message mới; ID và timestamp do framework quản lý, còn các metadata nghiệp vụ như trace ID hoặc correlation ID thường được giữ lại nếu không chủ động thay đổi.

## 6. MessageHeaderAccessor: truy cập và thay đổi headers có kiểm soát

`MessageHeaderAccessor` là lớp bao quanh `MessageHeaders`, cung cấp API có kiểu và cơ chế quản lý trạng thái mutable/immutable.

Dùng accessor khi:

- Muốn xây dựng nhiều header theo từng bước.
- Muốn cập nhật hoặc xóa header bằng API thay vì sửa Map.
- Muốn dùng các phương thức có kiểu như `setContentType`, `setReplyChannel`, `setErrorChannel`.
- Muốn lấy lại accessor gắn với message trong một flow vẫn giữ nguyên metadata accessor.

Ví dụ tạo message qua accessor:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("traceId", "trace-2026-001");
accessor.setHeader("tenantId", "tenant-a");
accessor.setContentType(MimeTypeUtils.APPLICATION_JSON);

MessageHeaders headers = accessor.getMessageHeaders();
Message<String> message = MessageBuilder.createMessage("order-42", headers);
~~~

Mặc định, khi gọi `getMessageHeaders()`, accessor hoàn tất việc xây dựng headers và không cho accessor đó tiếp tục sửa chúng. Đây là cách mặc định để tạo ra message có headers bất biến.

### Khi nào cần setLeaveMutable(true)?

Trong một số flow, ứng dụng cần khởi tạo message trước, rồi hoàn tất metadata trong cùng một giai đoạn xử lý. Có thể gọi:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("traceId", "trace-2026-001");
accessor.setLeaveMutable(true);

Message<String> message = MessageBuilder.createMessage(
        "order-42",
        accessor.getMessageHeaders()
);

// Trong giai đoạn khởi tạo cùng thread:
MessageHeaderAccessor current = MessageHeaderAccessor.getAccessor(message);
if (current != null && current.isMutable()) {
    current.setHeader("processedBy", "order-handler");
    current.setImmutable();
}
~~~

`setLeaveMutable(true)` giữ headers ở trạng thái có thể được thay đổi thông qua accessor sau khi tạo message. Khi hoàn tất, gọi `setImmutable()` để khóa việc chỉnh sửa.

Cơ chế này được thiết kế cho giai đoạn khởi tạo trong cùng một thread. Không nên phát tán một message có headers mutable qua nhiều thread hoặc cho nhiều thành phần cùng sửa. Nếu message đã immutable, hãy tạo accessor mutable mới bằng `MessageHeaderAccessor.getMutableAccessor(message)`, cập nhật rồi tạo message mới với headers đó.

`MessageHeaderAccessor.getAccessor(message)` có thể trả về `null` nếu accessor ban đầu không còn gắn với message hoặc không được giữ qua các bước xử lý. Vì vậy, không giả định mọi message nhận từ broker đều có thể khôi phục accessor gốc.

### Các phương thức cần nhớ

| Phương thức | Mục đích |
|---|---|
| `setHeader(name, value)` | Thêm/thay header; value null sẽ xóa header. |
| `setHeaderIfAbsent(name, value)` | Chỉ đặt nếu chưa có giá trị. |
| `getHeader(name)` | Đọc giá trị header. |
| `removeHeader(name)` | Xóa một header. |
| `removeHeaders(patterns)` | Xóa header theo mẫu tên. |
| `copyHeaders(map)` | Copy và ghi đè các header trùng tên. |
| `copyHeadersIfAbsent(map)` | Copy nhưng giữ nguyên giá trị đã tồn tại. |
| `getMessageHeaders()` | Lấy MessageHeaders hiện tại; mặc định hoàn tất và khóa accessor. |
| `setLeaveMutable(true)` | Giữ khả năng sửa qua accessor sau khi lấy MessageHeaders. |
| `setImmutable()` | Kết thúc giai đoạn chỉnh sửa. |
| `getMutableAccessor(message)` | Tạo accessor mutable để cập nhật một message đã có. |
| `toMap()` | Trả về bản copy của headers dưới dạng Map. |

## 7. Nhận header trong handler bằng @Header và @Headers

Trong các messaging handler được Spring hỗ trợ, có thể bind metadata trực tiếp vào tham số phương thức.

- `@Header("traceId")` lấy một header cụ thể.
- `@Headers` bind toàn bộ headers vào một `Map<String, Object>`.
- `@Payload` chỉ rõ tham số nhận payload.

Ví dụ minh họa một handler của Spring Messaging/WebSocket:

~~~java
@MessageMapping("/orders")
public void handleOrder(
        @Payload OrderCreated order,
        @Header("traceId") String traceId,
        @Header(value = "tenantId", required = false) String tenantId,
        @Headers Map<String, Object> allHeaders) {

    System.out.println("orderId=" + order.orderId());
    System.out.println("traceId=" + traceId);
    System.out.println("tenantId=" + tenantId);
}
~~~

Đây là đoạn handler minh họa; nó cần cấu hình messaging endpoint tương ứng. `@Header` có `required=true` mặc định. Nếu header có thể thiếu, đặt `required=false` hoặc cung cấp `defaultValue`. `@Headers` yêu cầu kiểu tham số tương thích với `Map<String, Object>`.

Không cần nhận cả `Message<?>` nếu phương thức chỉ cần payload và một vài metadata. Dùng tham số cụ thể giúp thể hiện rõ hợp đồng mà handler mong đợi.

## 8. Header của Spring Messaging, Spring Integration và protocol

Không phải mọi header đều do `MessageHeaders` định nghĩa. Cần phân biệt nguồn của metadata:

| Nhóm | Ví dụ | Nơi định nghĩa |
|---|---|---|
| Header cốt lõi | ID, TIMESTAMP, CONTENT_TYPE, REPLY_CHANNEL, ERROR_CHANNEL | Spring Messaging: `MessageHeaders` |
| Header tùy chỉnh | traceId, tenantId, source, eventType | Do ứng dụng quy ước |
| Header của Spring Integration | CORRELATION_ID, SEQUENCE_NUMBER, SEQUENCE_SIZE, PRIORITY, EXPIRATION_DATE | `IntegrationMessageHeaderAccessor` |
| Header của protocol/adapter | JMS properties, AMQP headers, Kafka record headers, STOMP native headers | Module tích hợp hoặc protocol tương ứng |

Ví dụ, Spring Integration có `IntegrationMessageHeaderAccessor.CORRELATION_ID` và các header phục vụ nhóm message như `SEQUENCE_NUMBER` và `SEQUENCE_SIZE`. Những hằng số đó thuộc Spring Integration, không phải danh sách header cốt lõi của `MessageHeaders`.

Với WebSocket/STOMP, các lớp như `SimpMessageHeaderAccessor` và `StompHeaderAccessor` cung cấp API chuyên biệt để làm việc với metadata của phiên và native STOMP headers. Với JMS, AMQP hoặc Kafka, module tương ứng có thể cung cấp constants và mapper riêng.

Khi message đi qua một adapter hoặc broker, headers nội bộ của Spring có thể được ánh xạ sang metadata protocol. Việc ánh xạ phụ thuộc mapper và giới hạn của protocol:

- Một số header có thể được đổi tên hoặc chuyển kiểu.
- Một số header nội bộ không có biểu diễn tương ứng trên wire.
- Header có giá trị là object Java tùy chỉnh có thể không serialize được.
- Protocol có thể giới hạn kiểu dữ liệu, kích thước hoặc tên header.

Không nên giả định toàn bộ `MessageHeaders` sẽ tự động đi qua broker và xuất hiện nguyên vẹn ở consumer. Hãy cấu hình header mapper/serializer và kiểm thử bằng message thực tế.

## 9. Sao chép và truyền header trong flow

Khi một thành phần nhận message và tạo message mới, cần quyết định metadata nào được giữ lại.

Có ba cách phổ biến:

1. **Tạo message mới từ đầu:** chỉ đặt những header mà thành phần hiện tại sở hữu.
2. **Copy từ message đầu vào:** dùng `MessageBuilder.fromMessage` hoặc `copyHeaders` nếu cần giữ metadata.
3. **Copy có điều kiện:** dùng `copyHeadersIfAbsent` để giữ giá trị mà thành phần trước đã đặt.

Trong Spring Integration, nhiều endpoint message-producing có cơ chế truyền tiếp các inbound headers sang outbound message. Header đã có ở message đầu ra có thể được ưu tiên; một số endpoint cho phép cấu hình loại header không được truyền tiếp. Nếu transformer trả về một `Message` hoàn chỉnh, mã transformer chịu trách nhiệm về headers của message đó. Đây là quy tắc của endpoint/flow Spring Integration, không phải bảo đảm chung cho mọi broker hoặc mọi module Spring.

Hãy đặt chính sách rõ ràng cho các nhóm header:

- **Giữ lại:** trace ID, correlation ID, tenant ID nếu còn đúng phạm vi.
- **Tạo mới:** message ID, timestamp hoặc thông tin về component vừa xử lý.
- **Loại bỏ:** dữ liệu nội bộ không còn ý nghĩa, header chỉ dùng cho bước trước, thông tin không được phép truyền sang ranh giới tin cậy khác.

Không copy mọi header một cách mù quáng. Một header được tạo trong request HTTP hoặc trong adapter đầu vào có thể không phù hợp khi phát ra event công khai.

## 10. Thiết kế custom header tốt

Một custom header nên có hợp đồng rõ ràng:

| Thuộc tính | Ví dụ |
|---|---|
| Tên | `traceId`, `tenantId`, `eventType` |
| Kiểu | `String`, `UUID`, `Integer`, `MimeType` |
| Ý nghĩa | ID tương quan, tenant xử lý, loại sự kiện |
| Chủ sở hữu | Producer nào tạo và component nào được phép thay đổi |
| Phạm vi | Nội bộ một service, một flow hay qua broker |
| Quy tắc thiếu giá trị | Bắt buộc, optional hay có default |
| Quy tắc truyền tiếp | Giữ, thay, ánh xạ hoặc loại bỏ tại adapter nào |

Một số nguyên tắc:

- Dùng tên nhất quán và tránh trùng với header chuẩn hoặc header của adapter. Với hệ thống lớn, có thể dùng prefix như `acme.traceId`.
- Quy định kiểu dữ liệu và đơn vị đo. Dùng `timeoutMs` thay cho tên mơ hồ `timeout`.
- Ưu tiên String, số, boolean, UUID hoặc kiểu đơn giản có thể serialize rõ ràng.
- Giữ correlation ID ổn định xuyên suốt workflow; không tạo lại ở mỗi handler nếu mục đích là nối request với reply.
- Không dùng header để thay thế payload nghiệp vụ. Nếu consumer cần dữ liệu để thực hiện nghiệp vụ, dữ liệu đó thường thuộc payload.
- Không dùng header làm nơi chứa password, access token, secret hoặc dữ liệu nhạy cảm. Header có thể bị log, copy và truyền qua nhiều adapter.
- Xem mọi header nhận từ bên ngoài là dữ liệu không đáng tin cậy. Kiểm tra kiểu, độ dài, tập giá trị hợp lệ và quyền sử dụng trước khi định tuyến hoặc cấp quyền.

## 11. Logging và bảo mật metadata

Headers hữu ích cho observability, nhưng log toàn bộ headers có thể làm lộ thông tin hoặc tạo log quá lớn.

Nên:

- Ghi trace ID, correlation ID và message ID khi chúng hữu ích cho việc điều tra.
- Che hoặc loại bỏ authorization token, cookie, credential và dữ liệu cá nhân.
- Giới hạn độ dài header do client bên ngoài cung cấp.
- Không dùng header do client tự gửi làm căn cứ duy nhất để xác thực danh tính hoặc phân quyền.
- Không ghi payload/header nhạy cảm ở mức DEBUG trong production nếu chưa có chính sách redaction.
- Tránh đưa object phức tạp vào header vì `toString()` hoặc serialization có thể làm log phình to hoặc gây lộ dữ liệu.

Một trace ID có thể hỗ trợ tìm log giữa nhiều service, nhưng nó không chứng minh message là hợp lệ hoặc đến từ một sender đáng tin cậy.

## 12. Ví dụ Java 17+ chạy được

Ví dụ dưới đây tạo message, thêm custom headers, đặt content type, rồi đọc metadata bằng API kiểu. Nó chỉ dùng module `spring-messaging`, không cần broker.

Cấu trúc project:

~~~text
message-headers-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageHeadersDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-headers-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>7.0.10</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### MessageHeadersDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

public class MessageHeadersDemo {

    public static void main(String[] args) {
        Message<String> message = MessageBuilder.withPayload("order-42")
                .setHeader("traceId", "trace-2026-001")
                .setHeader("tenantId", "tenant-a")
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
                .build();

        MessageHeaders headers = message.getHeaders();

        System.out.println("payload=" + message.getPayload());
        System.out.println("traceId=" + headers.get("traceId", String.class));
        System.out.println("tenantId=" + headers.get("tenantId", String.class));
        System.out.println("contentType="
                + headers.get(MessageHeaders.CONTENT_TYPE, MimeType.class));
        System.out.println("idPresent=" + (headers.getId() != null));
        System.out.println("timestampPresent=" + (headers.getTimestamp() != null));
    }
}
~~~

Chạy từ thư mục project bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageHeadersDemo
~~~

Kết quả stdout:

~~~text
payload=order-42
traceId=trace-2026-001
tenantId=tenant-a
contentType=text/plain
idPresent=true
timestampPresent=true
~~~

ID và timestamp thực tế thay đổi theo mỗi lần tạo message, nhưng chương trình chỉ in ra việc chúng có tồn tại nên stdout vẫn ổn định.

### Đọc và làm giàu message bằng MessageHeaderAccessor

Đoạn sau minh họa cập nhật metadata của message đã tồn tại. Đây là đoạn độc lập để tham khảo API; project Maven ở trên chưa cần thêm đoạn này vào `main`.

~~~java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(message);

accessor.setHeader("processedBy", "order-handler");

Message<String> enriched = MessageBuilder.createMessage(
        message.getPayload(),
        accessor.getMessageHeaders()
);
~~~

Accessor tạo một vùng headers có thể chỉnh sửa. `createMessage` tạo message mới dùng headers đã cập nhật. Nếu tự quản lý trạng thái mutable bằng `setLeaveMutable(true)`, hãy gọi `setImmutable()` sau khi hoàn tất và trước khi chia sẻ message sang thành phần hoặc thread khác.

## 13. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `UnsupportedOperationException` khi gọi `put` hoặc `remove` | Đang sửa trực tiếp `MessageHeaders`. | Dùng `MessageBuilder` hoặc `MessageHeaderAccessor`. |
| `ClassCastException` khi đọc header | Producer và consumer không thống nhất kiểu. | Quy định kiểu header và đọc bằng `get(name, Type.class)`. |
| Header bị mất sau broker | Adapter không map header đó hoặc protocol không hỗ trợ kiểu dữ liệu. | Kiểm tra header mapper, serializer và giới hạn protocol. |
| Header cũ ghi đè header mới | Dùng `copyHeaders` sau khi đã đặt giá trị mới. | Đổi thứ tự hoặc dùng `copyHeadersIfAbsent`. |
| Trace ID thay đổi giữa các bước | Tạo trace ID mới ở mỗi handler hoặc không copy header. | Định nghĩa chính sách truyền tiếp trace/correlation ID. |
| Không lấy lại được accessor | Message không còn giữ accessor gốc hoặc đã qua serialization/adapter. | Dùng `getMutableAccessor(message)` để tạo accessor mới. |
| Header bị thiếu làm handler lỗi | `@Header` mặc định yêu cầu header phải tồn tại. | Dùng `required=false`, `defaultValue` hoặc kiểm tra hợp đồng producer. |
| Log chứa token hoặc dữ liệu riêng tư | Ghi toàn bộ headers không lọc. | Redact hoặc allowlist các header được phép log. |

## 14. Checklist khi thiết kế headers

- [ ] Payload và metadata được tách đúng mục đích.
- [ ] Tên header có quy ước và không xung đột.
- [ ] Mỗi header có kiểu dữ liệu, đơn vị và ý nghĩa rõ ràng.
- [ ] ID/timestamp của Spring được để framework quản lý.
- [ ] Correlation ID và trace ID được truyền tiếp đúng workflow.
- [ ] Header có thể thiếu được xử lý rõ ràng.
- [ ] Header được copy có chủ đích, không copy toàn bộ một cách máy móc.
- [ ] Header mapper và serializer đã được kiểm tra ở ranh giới broker.
- [ ] Message không bị chia sẻ trong trạng thái mutable ngoài giai đoạn khởi tạo.
- [ ] Log không chứa token, credential hoặc dữ liệu nhạy cảm.
- [ ] Header từ nguồn bên ngoài được xác thực trước khi dùng để định tuyến hoặc phân quyền.

## Ghi nhớ

- `MessageHeaders` là Map chứa metadata nhưng **bất biến**.
- Spring tự quản lý `ID` và `TIMESTAMP`; đừng dùng chúng làm business ID hoặc correlation ID.
- Dùng `MessageBuilder` để tạo message mới và copy headers có chủ đích.
- Dùng `MessageHeaderAccessor` để đọc/ghi headers qua API có kiểm soát; mặc định accessor khóa headers khi lấy `MessageHeaders`.
- `@Header` nhận một metadata cụ thể; `@Headers` nhận Map chứa tất cả headers.
- Header cốt lõi, header Spring Integration và native protocol header thuộc các nhóm khác nhau.
- Khi đi qua broker, header cần được map và serialize theo protocol; không phải header nào cũng tự động được truyền đi.

## Tài liệu chính thức

- [Spring Framework Javadoc: MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework Javadoc: MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework Javadoc: MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework Javadoc: @Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html)
- [Spring Framework Javadoc: @Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html)
- [Spring Integration Reference: Message and Message Headers](https://docs.spring.io/spring-integration/reference/message.html)
- [Spring Integration Reference: Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html)
