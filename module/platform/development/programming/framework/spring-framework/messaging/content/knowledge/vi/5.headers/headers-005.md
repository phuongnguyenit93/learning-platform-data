# CONTENT_TYPE và vai trò của kiểu nội dung

> Mục tiêu: hiểu `Content-Type` mô tả định dạng dữ liệu của payload như thế nào, biết cách biểu diễn kiểu nội dung trong Spring Messaging, hiểu mối liên hệ giữa header và message converter, đồng thời tránh nhầm kiểu nội dung với kiểu Java, loại message hoặc phiên bản schema.

## 1. Kiểu nội dung trả lời câu hỏi gì?

Khi một hệ thống gửi message, bên nhận cần biết payload được biểu diễn theo định dạng nào để đọc và chuyển đổi đúng. Một chuỗi có thể là văn bản thuần, JSON, XML hoặc dữ liệu nhị phân; chỉ nhìn vào các byte không phải lúc nào cũng xác định được cách diễn giải an toàn.

`Content-Type` là metadata mô tả kiểu media của phần nội dung. Trong HTTP, nó là header chuẩn cho biết representation trong request hoặc response. Trong Spring Messaging, kiểu nội dung thường được biểu diễn bằng header `MessageHeaders.CONTENT_TYPE` của message.

Ví dụ:

| Content-Type | Ý nghĩa thường gặp |
|---|---|
| `text/plain` | Văn bản thuần |
| `text/plain;charset=UTF-8` | Văn bản thuần với charset UTF-8 |
| `application/json` | Dữ liệu JSON |
| `application/xml` | Dữ liệu XML |
| `application/octet-stream` | Dữ liệu nhị phân không gắn với định dạng ứng dụng cụ thể |
| `application/pdf` | Tài liệu PDF |
| `application/vnd.example.order+json` | JSON theo media type riêng của ứng dụng hoặc nhà cung cấp |

Kiểu nội dung giúp consumer chọn parser hoặc converter phù hợp. Nó mô tả **cách biểu diễn payload**, không tự mô tả ý nghĩa nghiệp vụ của message.

## 2. Cấu trúc MIME type và tham số

Một media type thường có dạng:

```text
type/subtype; parameter=value
```

Ví dụ `text/plain;charset=UTF-8` gồm:

- `type`: `text` — nhóm nội dung.
- `subtype`: `plain` — định dạng cụ thể trong nhóm.
- `parameter`: `charset=UTF-8` — tham số bổ sung cho cách diễn giải nội dung.

Một số subtype có hậu tố `+json` hoặc `+xml`, ví dụ `application/problem+json` hay `application/vnd.example.order+json`. Hậu tố này cho biết representation dựa trên cú pháp JSON hoặc XML, trong khi subtype vẫn có thể mang ý nghĩa chuyên biệt.

Tham số có thể biểu diễn charset, boundary hoặc phiên bản theo quy ước của media type. Không phải mọi tham số đều có cùng ý nghĩa với mọi subtype. JSON hiện đại thường được trao đổi bằng UTF-8; khi thiết kế hợp đồng, tránh thêm tham số charset không cần thiết nếu hệ thống hai bên đã thống nhất.

Trong Java, Spring dùng abstraction `MimeType` và các hằng tiện ích như `MimeTypeUtils.APPLICATION_JSON`, `MimeTypeUtils.TEXT_PLAIN` để biểu diễn media type. Việc dùng object có kiểu giúp tránh so sánh chuỗi MIME tùy tiện.

## 3. CONTENT_TYPE trong Spring Messaging

Spring Messaging cung cấp `Message<T>` để mang payload và headers. `MessageHeaders.CONTENT_TYPE` là tên header chuẩn dành cho kiểu nội dung. Giá trị header thường là một `MimeType`.

Ví dụ tạo một message chứa object Java và khai báo payload sẽ được biểu diễn dưới dạng JSON:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

record OrderCreated(String orderId, int itemCount) {}

OrderCreated event = new OrderCreated("ORD-100", 2);

Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .build();

Object contentType = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);
```

Đoạn mã trên tạo một message trong bộ nhớ. Payload vẫn là object `OrderCreated`; việc đặt header `application/json` **không tự serialize object thành chuỗi JSON hoặc byte array**. Converter hoặc adapter phải thực hiện bước chuyển đổi khi message được gửi qua ranh giới cần representation JSON.

Headers của message được Spring quản lý như metadata chỉ đọc sau khi message được tạo. Khi cần thay đổi header, hãy tạo message mới bằng `MessageBuilder` hoặc cơ chế accessor phù hợp thay vì sửa trực tiếp map headers.

## 4. CONTENT_TYPE và MessageConverter

`MessageConverter` là abstraction chuyển đổi giữa object và message. Ở chiều gửi, converter có thể biến payload Java thành representation phù hợp; ở chiều nhận, converter đọc payload và tạo object đích. `Content-Type` giúp converter xác định định dạng dữ liệu và kiểm tra converter có hỗ trợ định dạng đó hay không.

Ví dụ với `MappingJackson2MessageConverter` trong Spring Messaging:

```java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

MessageHeaders headers = new MessageHeaders(Map.of(
        MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON
));

Message<?> encoded = converter.toMessage(event, headers);
OrderCreated decoded = (OrderCreated)
        converter.fromMessage(encoded, OrderCreated.class);
```

Đây là ví dụ minh họa API chuyển đổi, giả sử converter có Jackson trên classpath và media type JSON được hỗ trợ. Trong mã production, cần xử lý trường hợp converter không tạo được message hoặc không chuyển đổi được payload, đồng thời cấu hình `ObjectMapper`, kiểu payload và danh sách media type theo yêu cầu ứng dụng. `MappingJackson2MessageConverter` dùng Jackson 2; hãy chọn converter tương ứng với phiên bản Jackson và Spring mà dự án đang sử dụng.

Luồng khái quát:

1. Producer có object Java làm payload.
2. Producer hoặc adapter cung cấp `Content-Type` phù hợp.
3. Message converter chọn cách serialize, ví dụ JSON.
4. Dữ liệu được gửi qua transport hoặc broker.
5. Consumer nhận bytes hoặc payload đã chuyển đổi.
6. Converter đọc content type và deserialize thành kiểu đích.

Nếu content type không được đặt, converter có thể dùng default hoặc suy luận theo cấu hình. Không nên phụ thuộc vào default ngầm khi nhiều định dạng cùng tồn tại; hãy thống nhất và khai báo rõ hợp đồng.

## 5. Phân biệt Content-Type, Accept, Content-Encoding và schema version

Các metadata này liên quan nhưng trả lời các câu hỏi khác nhau:

| Metadata | Câu hỏi | Ví dụ |
|---|---|---|
| `Content-Type` | Payload hiện tại được biểu diễn theo định dạng nào? | `application/json` |
| `Accept` | Bên nhận có thể tiếp nhận hoặc mong muốn representation nào? | `application/json, application/xml` |
| `Content-Encoding` | Payload đã được mã hóa/nén theo cách nào ở tầng representation? | `gzip` |
| Schema version | Payload tuân theo phiên bản cấu trúc dữ liệu nào? | `schemaVersion=2` |
| Message type/name | Message mang ý nghĩa nghiệp vụ nào? | `OrderCreated` |

`Accept` thường được dùng trong HTTP để thương lượng representation. Nó không thay thế `Content-Type`: một header thể hiện khả năng hoặc lựa chọn mong muốn, header còn lại mô tả nội dung thực tế đang được gửi.

`Content-Encoding` cũng khác charset. Ví dụ payload JSON có thể được nén gzip; khi đó content type vẫn là `application/json`, còn content encoding mô tả lớp nén. Không đặt `gzip` vào `Content-Type`.

`application/json` không cho biết JSON đó là schema phiên bản 1 hay 2, cũng không cho biết đó là event `OrderCreated` hay command `CreateOrder`. Có thể dùng media type riêng, header version hoặc trường version trong envelope, nhưng cần chọn một quy ước nhất quán và tài liệu hóa rõ.

## 6. Kiểu nội dung không phải kiểu Java

Một kiểu Java có thể được serialize theo nhiều định dạng. Ví dụ `OrderCreated` có thể được biểu diễn thành JSON, XML hoặc Avro tùy hệ thống. Ngược lại, cùng một media type `application/json` có thể chứa nhiều kiểu payload khác nhau.

| Kiểu Java | Representation có thể dùng | Content-Type tương ứng |
|---|---|---|
| `OrderCreated` | JSON object | `application/json` hoặc vendor JSON type |
| `String` | Văn bản thuần | `text/plain;charset=UTF-8` |
| `byte[]` | Dữ liệu nhị phân | `application/octet-stream` hoặc media type cụ thể |
| `ProblemDetails` | JSON theo hợp đồng lỗi | `application/problem+json` |

Không nên chọn converter chỉ bằng cách nhìn tên class Java hoặc tự đoán từ chuỗi JSON. Hợp đồng cần quy định cả media type, schema và kiểu đích. Nếu consumer nhận `application/json` nhưng payload thực tế là XML, lỗi chuyển đổi có thể xảy ra trước khi logic nghiệp vụ được gọi.

## 7. CONTENT_TYPE qua các transport khác nhau

Spring Messaging là abstraction trong ứng dụng. Khi message đi qua HTTP, JMS, RabbitMQ hoặc Kafka, adapter sẽ ánh xạ headers sang metadata của transport theo khả năng và cấu hình tích hợp. Không phải broker nào cũng có một trường Content-Type chuẩn giống HTTP.

### HTTP

HTTP định nghĩa header `Content-Type` cho request và response. Ví dụ:

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"orderId":"ORD-100","itemCount":2}
```

Server dùng `Content-Type` để diễn giải body nhận được; `Accept` thể hiện representation mà client có thể nhận. Trong Spring MVC, message converters của HTTP xử lý chuyển đổi body cho controller và response. Đây là hệ converter HTTP; không nên mặc định nó giống hệt converter của Spring Messaging.

### JMS

JMS có các thuộc tính chuẩn như `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo` và `JMSType`, nhưng `JMSType` là định danh kiểu message theo hợp đồng JMS, không phải MIME Content-Type. Việc truyền MIME type thường phụ thuộc converter hoặc custom property mà ứng dụng và adapter thống nhất. Vì vậy, không được coi `JMSType` và `MessageHeaders.CONTENT_TYPE` là cùng một trường.

Nếu producer gửi JSON qua JMS, producer và consumer cần thống nhất serializer, encoding và metadata để consumer chọn converter phù hợp. Cần kiểm thử ánh xạ headers trên đúng provider JMS được triển khai.

### RabbitMQ / AMQP

AMQP 0-9-1 có basic property `content_type`, thường được dùng để mô tả media type của body. Spring AMQP có thể ánh xạ thông tin này qua `MessageProperties` và message converter tương ứng. Ví dụ giá trị thường gặp là `application/json` hoặc `text/plain`.

Dù broker có lưu content type, consumer vẫn cần converter phù hợp và phải kiểm tra payload thực tế. Broker không tự biến JSON bytes thành object Java chỉ vì property ghi `application/json`.

### Kafka

Kafka record có key, value và headers; bản thân record không có một trường MIME Content-Type chuẩn bắt buộc. Ứng dụng có thể đặt header theo quy ước, chẳng hạn `contentType=application/json`, hoặc dùng converter/serializer của Spring Kafka để ánh xạ metadata. Producer và consumer phải thống nhất tên header, kiểu bytes và serializer.

Không nên giả định header `contentType` trong Spring Messaging sẽ tự xuất hiện đúng định dạng trên mọi Kafka record hoặc JMS message. Hãy xác nhận mapping của adapter và kiểm tra message thực tế trên broker.

## 8. Chọn media type cho hợp đồng message

Khi thiết kế hợp đồng, hãy chọn media type theo representation thực tế:

- Dùng `application/json` cho JSON thông thường có schema được hai bên thống nhất.
- Dùng `text/plain` cho văn bản thuần; khai báo charset khi giao thức hoặc hệ thống yêu cầu.
- Dùng `application/octet-stream` cho bytes không có định dạng chuyên biệt.
- Dùng media type chuyên biệt như `application/pdf` nếu payload thực sự là PDF.
- Cân nhắc vendor media type có hậu tố `+json` hoặc `+xml` khi cần phân biệt representation của một API hoặc domain cụ thể.

Không dùng `application/json` chỉ vì payload là một Java object. Phải bảo đảm converter thực sự serialize thành JSON và consumer hiểu đúng schema. Nếu dùng định dạng nhị phân như Avro hoặc Protobuf, hãy chọn media type hoặc quy ước được hệ thống hỗ trợ và tài liệu hóa.

Ví dụ tạo message có content type JSON và schema version riêng:

```java
Message<OrderCreated> eventMessage = MessageBuilder
        .withPayload(event)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .setHeader("schemaVersion", 2)
        .setHeader("eventType", "OrderCreated")
        .build();
```

Ở ví dụ này, `contentType` mô tả cú pháp JSON, `schemaVersion` mô tả phiên bản hợp đồng và `eventType` mô tả ý nghĩa nghiệp vụ. Các header tùy chỉnh chỉ có tác dụng nếu producer, adapter và consumer cùng thống nhất cách sử dụng.

## 9. Kiểm tra và xử lý content type

Consumer không nên tin tưởng mù quáng vào metadata từ bên gửi. Cần kiểm tra content type có thuộc danh sách cho phép không, payload có kích thước hợp lệ không và nội dung có parse được theo schema mong đợi không.

Một quy trình nhận message có thể gồm:

1. Đọc content type từ header hoặc metadata transport đã được adapter ánh xạ.
2. Kiểm tra media type có được consumer hỗ trợ không.
3. Kiểm tra kích thước payload và encoding trước khi deserialize nếu có thể.
4. Chọn converter phù hợp và deserialize vào kiểu đích.
5. Validate dữ liệu sau khi deserialize: field bắt buộc, miền giá trị, schema version và quy tắc nghiệp vụ.
6. Nếu sai định dạng, phân loại thành lỗi conversion/technical và áp dụng error handling; không retry vô hạn payload không thể parse.

Ví dụ, consumer chỉ nhận JSON:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

void validateContentType(Message<?> message) {
    Object value = message.getHeaders().get(MessageHeaders.CONTENT_TYPE);
    if (!(value instanceof MimeType mimeType)
            || !MimeTypeUtils.APPLICATION_JSON.isCompatibleWith(mimeType)) {
        throw new IllegalArgumentException("Unsupported message content type");
    }
}
```

Đây là ví dụ kiểm tra header trước bước chuyển đổi. Trong ứng dụng thực tế, cần quyết định rõ có chấp nhận header bị thiếu hay không, có cho phép các subtype `+json` hay không và cách trả lỗi. `isCompatibleWith` hỗ trợ so sánh theo quy tắc MIME; nếu hợp đồng chỉ chấp nhận đúng một media type, hãy kiểm tra chặt hơn.

Không dựa vào Content-Type như một biện pháp bảo mật. Kẻ gửi có thể khai báo `application/json` nhưng gửi dữ liệu không hợp lệ hoặc payload độc hại. Hãy giới hạn kích thước, xác thực nguồn gửi, validate schema và cấu hình parser an toàn.

## 10. Content type và lỗi chuyển đổi

Lỗi có thể xảy ra ở nhiều thời điểm:

- **Không hỗ trợ media type:** không có converter nào nhận định dạng đã khai báo.
- **Payload không khớp media type:** header ghi JSON nhưng bytes không phải JSON hợp lệ.
- **Schema không tương thích:** JSON hợp lệ nhưng thiếu field bắt buộc hoặc sai kiểu dữ liệu.
- **Không tương thích phiên bản:** payload đúng định dạng nhưng consumer chưa hiểu schema version mới.
- **Transport mapping sai:** producer đặt header ở một nơi nhưng adapter không chuyển metadata sang transport mà consumer đang đọc.

Trong Spring Messaging, lỗi chuyển đổi có thể xuất hiện dưới dạng `MessageConversionException` hoặc exception liên quan đến converter. Với Spring Integration, lỗi ở transformer hoặc handler có thể đi qua error handling flow tùy loại endpoint. Với broker, acknowledgement, retry và dead-letter phụ thuộc integration và cấu hình broker.

Nên ghi nhận content type, schema version, message ID và correlation ID cùng loại lỗi để điều tra. Không ghi toàn bộ payload nếu có dữ liệu nhạy cảm.

## 11. Lỗi thường gặp

- **Nghĩ rằng đặt header là đã serialize:** `MessageBuilder.setHeader(CONTENT_TYPE, ...)` chỉ gắn metadata; converter hoặc adapter mới chuyển payload sang wire format.
- **Nhầm Content-Type với kiểu Java:** `OrderCreated` có thể được biểu diễn bằng JSON, XML hoặc định dạng khác.
- **Nhầm Content-Type với event type:** `application/json` không cho biết payload là `OrderCreated` hay `PaymentDeclined`.
- **Nhầm Content-Type với schema version:** hai payload cùng là JSON nhưng có thể khác cấu trúc; cần versioning riêng.
- **Nhầm Accept và Content-Type:** một header mô tả representation mong muốn, header kia mô tả nội dung thực tế.
- **Dùng `JMSType` như MIME type:** hai metadata có mục đích khác nhau trong JMS.
- **Giả định mọi broker có trường content type giống HTTP:** Kafka, JMS và AMQP có mô hình metadata khác nhau.
- **Tin header mà không validate payload:** media type do producer khai báo không chứng minh dữ liệu hợp lệ hoặc an toàn.
- **Retry vô hạn lỗi conversion:** payload sai định dạng thường không tự trở nên hợp lệ sau khi retry.
- **Không kiểm thử mapping header:** ứng dụng có thể hoạt động trong unit test nhưng mất content type khi đi qua adapter hoặc broker thật.

## 12. Quy trình thiết kế và kiểm thử

1. Xác định representation thực tế của payload: JSON, XML, text, bytes hay định dạng khác.
2. Chọn media type chuẩn hoặc vendor type phù hợp và thống nhất các tham số cần thiết.
3. Quy định riêng event/command type và schema version; không nhồi tất cả ý nghĩa vào Content-Type.
4. Đặt `MessageHeaders.CONTENT_TYPE` khi tạo message và cấu hình converter hỗ trợ media type đó.
5. Xác định adapter ánh xạ header sang HTTP, JMS, AMQP hoặc Kafka như thế nào.
6. Ở consumer, kiểm tra media type, giới hạn payload, deserialize và validate schema.
7. Kiểm thử cả chiều gửi và nhận qua broker thật hoặc môi trường tích hợp: header có được giữ, payload có đúng bytes và converter có tạo đúng kiểu không.
8. Kiểm thử content type thiếu, không hỗ trợ, sai payload, schema cũ/mới và lỗi converter; xác định retry hoặc dead-letter phù hợp.

## 13. Kết luận

`CONTENT_TYPE` mô tả định dạng representation của payload để converter hoặc consumer biết cách diễn giải dữ liệu. Trong Spring Messaging, metadata này thường được đặt qua `MessageHeaders.CONTENT_TYPE` bằng một `MimeType`; `MessageConverter` thực hiện chuyển đổi object và representation.

Content type khác với kiểu Java, event/command type, schema version, `Accept` và `Content-Encoding`. Khi message đi qua HTTP, JMS, RabbitMQ hoặc Kafka, cách ánh xạ metadata phụ thuộc transport và adapter. Hãy định nghĩa hợp đồng rõ ràng, validate payload và kiểm thử mapping trên đúng hạ tầng để tránh lỗi chuyển đổi và sai lệch dữ liệu.