# MessageHeaders.ID, TIMESTAMP và vòng đời định danh

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích ý nghĩa và kiểu dữ liệu của `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP`.
- Theo dõi cách hai header này được tạo mới khi một Spring Message được xây dựng hoặc biến đổi.
- Phân biệt message ID với business ID, event ID, correlation ID, trace ID và ID do broker cấp.
- Dùng `MessageBuilder` và `MessageHeaderAccessor` để đọc, sao chép và bổ sung header đúng cách.
- Chọn timestamp phù hợp cho thời điểm tạo message, thời điểm nghiệp vụ và đo thời gian xử lý.
- Tránh lỗi khi chuyển message qua transformer, splitter, aggregator, retry và transport bên ngoài.

## 1. Message và MessageHeaders

Trong Spring Messaging, `Message<T>` là một wrapper gồm payload và headers:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

- **Payload** chứa dữ liệu chính mà consumer cần xử lý, ví dụ một DTO đơn hàng, chuỗi JSON hoặc một record.
- **Headers** chứa metadata đi kèm message, ví dụ định danh, timestamp, content type, correlation information hoặc thông tin transport.

Hai header chuẩn cần hiểu rõ:

| Header | Hằng số | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|---|
| Message ID | `MessageHeaders.ID` | `java.util.UUID` | Định danh của một Spring Message instance |
| Timestamp | `MessageHeaders.TIMESTAMP` | `java.lang.Long` | Thời điểm message được tạo |

Có thể truy cập qua getter:

~~~java
UUID messageId = message.getHeaders().getId();
Long timestamp = message.getHeaders().getTimestamp();
~~~

Hoặc truy cập theo tên hằng số:

~~~java
Object id = message.getHeaders().get(MessageHeaders.ID);
Object createdAt = message.getHeaders().get(MessageHeaders.TIMESTAMP);
~~~

Dùng getter có kiểu rõ ràng thường dễ đọc và giảm ép kiểu. `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` là tên header chuẩn; không cần tự viết chuỗi `"id"` hoặc `"timestamp"`.

## 2. MessageHeaders.ID: định danh của một message instance

### Ý nghĩa

`MessageHeaders.ID` có kiểu `UUID` và được Spring tạo tự động khi xây dựng một message thông thường. Nó định danh instance message đang được xử lý trong Spring Messaging.

Ví dụ:

~~~java
Message<String> message = MessageBuilder.withPayload("hello").build();

UUID id = message.getHeaders().getId();
System.out.println(id);
~~~

Giá trị thực tế là một UUID nên mỗi lần chạy có thể khác nhau. Không nên ghi cứng UUID vào ví dụ hoặc dựa vào một giá trị cụ thể trong log.

ID này trả lời câu hỏi: **“Đây là instance message nào?”** Nó không mặc nhiên trả lời:

- Sự kiện nghiệp vụ nào đã xảy ra?
- Message này thuộc request hoặc workflow nào?
- Broker đã lưu message với ID nào?
- Lần giao nhận này là lần thử thứ mấy?
- Request này thuộc distributed trace nào?

Đây là các khái niệm định danh khác nhau và cần header hoặc trường dữ liệu riêng.

### Vì sao ID thay đổi khi message được biến đổi?

Message và MessageHeaders được thiết kế theo hướng bất biến. Khi một endpoint tạo message mới, message mới có ID riêng. Trong Spring Integration, mỗi lần message bị biến đổi, ví dụ qua transformer, framework gán một message ID mới. Timestamp của message mới cũng phản ánh thời điểm tạo message mới. `ID` và `TIMESTAMP` là các header chỉ đọc và không được ghi đè khi copy header bằng `MessageBuilder`.

Ví dụ về vòng đời:

~~~text
Tạo message A
  ID = id-A
  TIMESTAMP = time-A
       |
       v
Chuyển tiếp A mà không thay đổi
  Vẫn là message A
       |
       v
Transformer tạo message B
  ID = id-B
  TIMESTAMP = time-B
  Các header nghiệp vụ khác có thể được giữ lại
       |
       v
Handler tạo message C
  ID = id-C
  TIMESTAMP = time-C
~~~

Không phải mọi endpoint đều tạo message mới. Một bridge hoặc router chỉ chuyển tiếp message mà không sửa đổi có thể giữ nguyên instance và ID. Điều quan trọng là phân biệt thao tác chuyển tiếp với thao tác tạo message đầu ra.

### Không tự đặt ID cho message thông thường

Không nên dùng `setHeader(MessageHeaders.ID, ...)` hoặc tự chèn `id` vào map header để biến ID thành mã nghiệp vụ. Javadoc của Spring Framework quy định ID là UUID được tự động sinh; chỉ trong tình huống deserialize một Message đã serialize và cần khôi phục UUID đã sinh trước đó mới có ngoại lệ cho việc khôi phục giá trị này.

Nếu cần một mã ổn định qua các bước xử lý, hãy tạo header riêng như `eventId`, `requestId`, `orderId` hoặc `correlationId`.

## 3. MessageHeaders.TIMESTAMP: thời điểm tạo message

### Ý nghĩa và cách đọc

`MessageHeaders.TIMESTAMP` có kiểu `Long`, biểu diễn thời điểm tạo message. Với message được xây dựng theo cách thông thường, giá trị là thời gian epoch milliseconds: số mili giây kể từ 1970-01-01T00:00:00Z.

~~~java
Long timestamp = message.getHeaders().getTimestamp();

if (timestamp != null) {
    Instant createdAt = Instant.ofEpochMilli(timestamp);
    System.out.println(createdAt);
}
~~~

Có thể định dạng thành thời gian UTC hoặc múi giờ hiển thị bằng API `java.time`. Nên giữ giá trị epoch trong header để trao đổi và chỉ định dạng khi hiển thị hoặc ghi log.

### Timestamp thay đổi theo vòng đời message

Khi một transformer hoặc handler tạo message đầu ra mới, timestamp phản ánh thời điểm tạo message đầu ra đó. Nó không phải một mốc bất biến đại diện cho toàn bộ hành trình của event nghiệp vụ.

Ví dụ:

- `time-A`: thời điểm Spring tạo message ban đầu.
- `time-B`: thời điểm transformer tạo message đã chuẩn hóa payload.
- `time-C`: thời điểm một handler tạo message kết quả.

Timestamp có độ phân giải mili giây. Hai message được tạo rất sát nhau vẫn có thể có cùng giá trị timestamp nếu được tạo trong cùng một mili giây. Vì vậy, không dùng điều kiện `timestampA != timestampB` để chứng minh hai message khác nhau; dùng ID để nhận biết message instance.

### Timestamp không đồng nghĩa thời gian nghiệp vụ

Một event `PaymentCaptured` có thể được phát sau khi thao tác thanh toán đã xảy ra. Timestamp của Spring Message là thời điểm wrapper message được tạo, có thể muộn hơn thời điểm nghiệp vụ.

Nếu cần lưu thời điểm nghiệp vụ, hãy đưa trường riêng vào payload hoặc header có tên rõ nghĩa:

- `occurredAt`: thời điểm sự kiện nghiệp vụ thực sự xảy ra.
- `publishedAt`: thời điểm producer phát sự kiện ra ngoài.
- `receivedAt`: thời điểm consumer nhận được dữ liệu.
- `MessageHeaders.TIMESTAMP`: thời điểm Spring Message instance được tạo.

Không dùng một tên chung như `timestamp` cho nhiều khái niệm nếu hệ thống cần phân biệt chúng.

Timestamp là thời gian đồng hồ hệ thống. Khi so sánh timestamp từ nhiều máy, cần lưu ý độ lệch đồng hồ giữa các máy. Để đo khoảng thời gian trong cùng một process, dùng đồng hồ monotonic như `System.nanoTime()`; không lấy hai timestamp epoch từ các máy không đồng bộ làm phép đo latency tuyệt đối.

## 4. Phân biệt các loại định danh

Các loại ID có thể cùng xuất hiện trên một message nhưng có vòng đời và mục đích khác nhau:

| Loại định danh | Ví dụ | Vòng đời và mục đích |
|---|---|---|
| Spring message ID | `MessageHeaders.ID` | UUID cho một Spring Message instance; đổi khi tạo message mới |
| Message timestamp | `MessageHeaders.TIMESTAMP` | Thời điểm tạo Spring Message instance; đổi khi tạo message mới |
| Business ID | `orderId`, `paymentId` | Định danh thực thể nghiệp vụ; ổn định theo vòng đời thực thể |
| Event ID | `eventId` | Định danh một sự kiện nghiệp vụ; giữ ổn định khi phát lại hoặc retry cùng event |
| Correlation ID | `correlationId`, `requestId` | Liên kết các message thuộc cùng request, workflow hoặc nhóm xử lý |
| Trace ID | `traceId` | Liên kết các span trong một distributed trace |
| Transport message ID | `JMSMessageID`, AMQP messageId | Định danh theo hệ thống vận chuyển; do producer, broker hoặc provider quản lý tùy giao thức |

Ví dụ một message có thể mang đồng thời:

~~~text
MessageHeaders.ID = UUID của Spring Message hiện tại
MessageHeaders.TIMESTAMP = thời điểm Spring tạo instance hiện tại
eventId = evt-2026-00042
correlationId = checkout-9001
orderId = ORD-1001
traceId = 4bf92f3577b34da6a3ce929d0e0e4736
~~~

Khi transformer tạo message mới, Spring ID và timestamp thay đổi; `eventId`, `correlationId`, `orderId` và trace context có thể được giữ lại theo chính sách propagation.

### Message ID không phải khóa chống xử lý trùng

Một broker có thể giao lại cùng một message khi consumer lỗi hoặc acknowledgement chưa hoàn tất. Tùy adapter và cách tạo message inbound, mỗi lần nhận có thể được bọc thành một Spring Message instance mới. Do đó, `MessageHeaders.ID` không phải khóa deduplication ổn định qua retry hoặc redelivery.

Nếu cần chống xử lý nghiệp vụ trùng, producer nên tạo `eventId` ổn định và consumer lưu dấu event đã xử lý theo khóa đó hoặc theo khóa nghiệp vụ duy nhất. Nếu cùng một event được phát lại, giữ nguyên `eventId`; đừng tạo eventId mới chỉ vì tạo một Spring Message wrapper mới.

### Correlation ID trong Spring Integration

Spring Integration có hằng số `IntegrationMessageHeaderAccessor.CORRELATION_ID` cho header tương quan. Header này được dùng để liên kết các message, chẳng hạn các message được tạo từ splitter và chờ aggregator ghép lại.

Với request/reply, request ID hoặc correlation ID cần được giữ theo contract của ứng dụng. Đừng dùng `MessageHeaders.ID` làm correlation ID vì ID thay đổi khi tạo message mới.

### Trace ID

Trace ID thuộc hệ thống tracing như Micrometer Tracing hoặc OpenTelemetry. Nó liên kết các span qua nhiều service và process. Message ID có thể xuất hiện trong log của một span để hỗ trợ điều tra, nhưng không thay thế trace ID hoặc span ID.

## 5. Header propagation khi message đi qua flow

Spring Integration thường chuyển tiếp các header đầu vào sang message đầu ra do endpoint tạo ra, để metadata nghiệp vụ và routing tiếp tục có mặt trong flow.

Có một số quy tắc cần nắm:

1. Khi service activator hoặc message-producing endpoint tạo message đầu ra, inbound headers thường được propagate.
2. Header đã có trên message đầu ra được ưu tiên; header inbound chỉ được copy nếu tên đó chưa tồn tại ở đầu ra.
3. `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` là read-only, không được ghi đè bằng giá trị của message nguồn.
4. Nếu transformer trả về một payload đơn thuần, framework có thể propagate inbound headers.
5. Nếu transformer tự trả về một `Message` hoàn chỉnh, code transformer chịu trách nhiệm xây dựng toàn bộ header cần có trên message đầu ra.
6. Có thể cấu hình endpoint để không propagate một số header thông qua `setNotPropagatedHeaders()`, `addNotPropagatedHeaders()` hoặc tùy chọn `notPropagatedHeaders()` trong Java DSL.

### Splitter và Aggregator

Khi splitter tạo nhiều message con từ một message đầu vào:

- Mỗi message con là một message instance mới và có ID riêng.
- Các message con cần được liên kết bằng correlation ID.
- Spring Integration có thể bổ sung sequence number và sequence size để aggregator biết vị trí và số lượng message trong nhóm.
- Khi aggregator tạo message tổng hợp, kết quả có ID mới; correlation metadata được quản lý theo semantics của aggregator.

Không dùng ID của message đầu tiên để đại diện cho tất cả message con. ID là định danh từng instance; correlation ID mới biểu diễn quan hệ nhóm.

### Transformer trả về Message hay payload?

Hai cách trả về có ý nghĩa khác nhau:

~~~java
// Trả về payload: framework có thể propagate inbound headers.
String normalize(String payload) {
    return payload.trim();
}

// Trả về Message: code tự chịu trách nhiệm với các header cần giữ.
Message<String> normalizeMessage(Message<String> input) {
    return MessageBuilder.withPayload(input.getPayload().trim())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

Trong ví dụ thứ hai, `copyHeaders` giữ các header tùy chỉnh như `eventId` hoặc `correlationId`, còn ID và timestamp của message nguồn không được copy đè lên hai header chỉ đọc. Message đầu ra có định danh và thời điểm tạo của riêng nó.

## 6. Tạo message mới đúng cách bằng MessageBuilder

`MessageHeaders` triển khai `Map` nhưng là map bất biến. Gọi `put`, `remove`, `clear` trực tiếp trên map sẽ gây `UnsupportedOperationException`.

Không sửa trực tiếp:

~~~java
message.getHeaders().put("stage", "validated"); // UnsupportedOperationException
~~~

Dùng `MessageBuilder` để tạo message mới:

~~~java
Message<String> next = MessageBuilder.fromMessage(message)
        .setHeader("stage", "validated")
        .build();
~~~

Các phương thức hữu ích:

- `MessageBuilder.withPayload(payload)`: tạo builder với payload mới.
- `MessageBuilder.fromMessage(message)`: tạo builder từ payload và các header của message nguồn.
- `copyHeaders(map)`: copy header tùy chỉnh; không ghi đè ID và timestamp.
- `copyHeadersIfAbsent(map)`: chỉ copy những header chưa có.
- `setHeader(name, value)`: thêm hoặc thay đổi header tùy chỉnh.
- `removeHeader(name)`: loại bỏ header tùy chỉnh.

Không dùng `setHeader` hoặc `copyHeaders` để ép ID/timestamp của message cũ lên message mới.

### Dùng MessageHeaderAccessor

Khi cần thao tác với nhiều header hoặc cần API truy cập có kiểu, dùng `MessageHeaderAccessor`:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("correlationId", "checkout-9001");
accessor.setHeader("eventId", "evt-2026-00042");

MessageHeaders headers = accessor.getMessageHeaders();
Message<String> message =
        MessageBuilder.createMessage("payment-captured", headers);
~~~

Mặc định, khi gọi `getMessageHeaders()`, accessor được chuyển sang trạng thái không thể sửa tiếp và headers trả về là immutable. Nếu đặt `setLeaveMutable(true)`, cần gọi `setImmutable()` khi hoàn tất trước khi chuyển message sang thành phần khác hoặc thread khác. Cơ chế mutable chỉ nên dùng trong giai đoạn khởi tạo message trên một thread.

Có thể lấy accessor gắn với một message bằng `MessageHeaderAccessor.getAccessor(message)`; phương thức này có thể trả về `null` nếu message không được tạo qua accessor tương ứng. Nếu chỉ cần đọc ID và timestamp, getter trực tiếp trên `MessageHeaders` đơn giản hơn.

## 7. Ví dụ Java 17: theo dõi ID và timestamp qua biến đổi

Ví dụ dùng Spring Framework 6.2.18 và chỉ cần module `spring-messaging`. Chương trình tạo message ban đầu, tạo một message mới với payload đã chuẩn hóa, giữ lại các header nghiệp vụ và so sánh hai ID.

Cấu trúc thư mục:

~~~text
message-identity-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MessageIdentityDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-identity-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/MessageIdentityDemo.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageIdentityDemo {

    public static void main(String[] args) {
        Message<String> original = MessageBuilder
                .withPayload("  invoice-paid  ")
                .setHeader("eventId", "evt-2026-00042")
                .setHeader("correlationId", "checkout-9001")
                .build();

        Message<String> normalized = MessageBuilder
                .withPayload(original.getPayload().trim())
                .copyHeaders(original.getHeaders())
                .setHeader("normalized", true)
                .build();

        UUID originalId = original.getHeaders().getId();
        UUID normalizedId = normalized.getHeaders().getId();
        Long timestamp = normalized.getHeaders().getTimestamp();

        Instant createdAt = Instant.ofEpochMilli(timestamp);

        System.out.println("payload=" + normalized.getPayload());
        System.out.println("newMessageId=" + !originalId.equals(normalizedId));
        System.out.println("eventId=" + normalized.getHeaders().get("eventId"));
        System.out.println("correlationId=" + normalized.getHeaders().get("correlationId"));
        System.out.println("normalized=" + normalized.getHeaders().get("normalized"));
        System.out.println("timestampPresent=" + (timestamp != null));
        System.out.println("timestampType=" + timestamp.getClass().getSimpleName());
        System.out.println("createdAtParsed=" + (createdAt != null));
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.MessageIdentityDemo
~~~

Kết quả stdout:

~~~text
payload=invoice-paid
newMessageId=true
eventId=evt-2026-00042
correlationId=checkout-9001
normalized=true
timestampPresent=true
timestampType=Long
createdAtParsed=true
~~~

Giải thích:

- Message ban đầu nhận một UUID và timestamp do Spring tạo.
- Message `normalized` là instance mới nên có UUID mới.
- `copyHeaders` giữ lại `eventId` và `correlationId`.
- Hai header ID và TIMESTAMP của message ban đầu không được copy đè lên message mới.
- Timestamp được đọc dưới dạng `Long` và chuyển sang `Instant` bằng `Instant.ofEpochMilli(...)`.
- Chương trình không in giá trị UUID hoặc thời gian cụ thể, vì vậy stdout ở trên ổn định giữa các lần chạy.

## 8. Định danh khi đi qua broker và protocol

Khi message rời khỏi ứng dụng, adapter có thể ánh xạ Spring headers sang thuộc tính của transport. Không nên giả định mọi transport đều giữ nguyên toàn bộ header hoặc dùng cùng một tên.

### RabbitMQ / AMQP

Spring AMQP có các header riêng trong `AmqpHeaders`, ví dụ `AmqpHeaders.MESSAGE_ID` và `AmqpHeaders.CORRELATION_ID`. Header mapper quyết định giá trị nào được chuyển giữa Spring Message và AMQP MessageProperties.

Với `DefaultAmqpHeaderMapper` của Spring Integration, từ Spring Integration 5.1, nếu outbound message chưa có header AMQP message ID hoặc timestamp tương ứng, mapper có thể dùng `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` làm giá trị dự phòng cho thuộc tính `MessageProperties.messageId` và `MessageProperties.timestamp`. Ở chiều inbound, các thuộc tính native được ánh xạ vào các header AMQP có tiền tố riêng.

Vì vậy, cần phân biệt:

- `MessageHeaders.ID`: ID của Spring Message.
- `AmqpHeaders.MESSAGE_ID`: header thể hiện message ID ở lớp AMQP.
- `eventId`: ID nghiệp vụ do producer quy định và giữ ổn định.

Việc hai giá trị có thể được mapper liên kết trong một cấu hình cụ thể không biến chúng thành cùng một khái niệm. Kiểm tra header mapper và phiên bản thư viện trước khi dựa vào hành vi mapping.

### JMS

Spring JMS có `JmsHeaders.MESSAGE_ID`, `JmsHeaders.CORRELATION_ID` và các header khác để truy cập thuộc tính của JMS message. JMS provider có thể cấp `JMSMessageID`; ứng dụng không nên nhầm giá trị native này với Spring `MessageHeaders.ID`.

Header mapper chịu trách nhiệm chuyển đổi giữa Spring headers và JMS properties. Ví dụ, `JMSCorrelationID` được dùng phổ biến để liên kết request/reply; Spring Integration cũng có khái niệm `correlationId` để nhóm các message liên quan, và hai khái niệm này có thể được map theo chính sách riêng.

### Qua ranh giới service

Khi gửi event qua HTTP, Kafka, RabbitMQ hoặc JMS, hãy định nghĩa contract rõ ràng:

~~~json
{
  "eventId": "evt-2026-00042",
  "eventType": "PaymentCaptured",
  "schemaVersion": 1,
  "occurredAt": "2026-11-07T03:00:00Z",
  "correlationId": "checkout-9001",
  "paymentId": "PAY-1001"
}
~~~

Payload trên chứa định danh và thời gian nghiệp vụ. Khi consumer tạo Spring Message mới, Spring có thể gán một `MessageHeaders.ID` và `TIMESTAMP` mới cho wrapper cục bộ. `eventId` và `occurredAt` vẫn giữ nguyên theo contract.

## 9. Tùy chỉnh ID generation và lưu ý nâng cao

Spring cung cấp abstraction `org.springframework.util.IdGenerator` để tùy chỉnh chiến lược sinh UUID. Spring Integration cho phép khai báo bean triển khai interface này để thay đổi chiến lược sinh ID của message.

Cần cân nhắc kỹ trước khi tùy chỉnh:

- Chiến lược ID mặc định đã được tối ưu cho việc sinh UUID.
- Một classloader chỉ dùng một chiến lược UUID. Nhiều ApplicationContext trong cùng classloader chia sẻ chiến lược đó.
- Nếu nhiều context cùng khai báo `IdGenerator`, chúng phải dùng cùng implementation class; các cấu hình tham số khác nhau không tạo ra chiến lược độc lập theo context.
- Không dùng bộ đếm tăng dần làm ID phân tán nếu có nhiều process cùng phát message; bộ đếm cục bộ không bảo đảm duy nhất giữa các process.
- Việc thay đổi ID generator không thay thế event ID, correlation ID hoặc trace ID.

`MessageHeaderAccessor` và `IdTimestampMessageHeaderInitializer` cung cấp cơ chế tùy chỉnh việc sinh ID/timestamp trong một số luồng tạo header hoặc protocol integration. Chỉ tắt tự động sinh ID/timestamp khi adapter hoặc contract thật sự yêu cầu và toàn bộ consumer đã được thiết kế cho trường hợp đó.

## 10. Lỗi thường gặp

1. **Dùng `MessageHeaders.ID` làm event ID.** ID đổi khi message được tạo mới; retry hoặc adapter có thể tạo wrapper khác. Hãy tạo `eventId` riêng.
2. **Dùng ID làm correlation ID.** Các message con hoặc message đầu ra có ID riêng. Dùng correlation ID ổn định để liên kết chúng.
3. **Dùng timestamp làm thời điểm nghiệp vụ.** Timestamp của Spring là thời điểm tạo wrapper message. Lưu `occurredAt` riêng trong event.
4. **Cố ghi đè ID/timestamp bằng MessageBuilder.** Đây là header read-only trong Spring Integration và không được copy đè theo cách thông thường.
5. **Sửa trực tiếp MessageHeaders.** Map header là immutable. Dùng `MessageBuilder` hoặc `MessageHeaderAccessor`.
6. **Cho rằng mọi endpoint đều tạo ID mới.** Endpoint chỉ chuyển tiếp message không sửa đổi có thể giữ nguyên instance. ID mới xuất hiện khi một message mới được tạo.
7. **Cho rằng mọi header đều tự động được giữ.** Transformer trả về một Message hoàn chỉnh phải tự cung cấp các header cần thiết; endpoint cũng có thể được cấu hình để lọc header propagation.
8. **Dùng timestamp epoch từ nhiều máy để tính latency mà không đồng bộ clock.** Clock skew có thể làm sai kết quả. Dùng tracing hoặc phép đo phù hợp.
9. **Dùng native broker ID như business ID.** Broker ID có thể do provider cấp và chịu quy tắc của transport. Giữ eventId riêng trong contract nếu cần dedup xuyên hệ thống.
10. **Đặt object mutable trong header rồi sửa sau khi gửi.** Map header bất biến không làm sâu bất biến các object bên trong. Ưu tiên giá trị bất biến như String, UUID, số và Instant.

## 11. Checklist khi thiết kế message identity

- [ ] Đọc `MessageHeaders.ID` bằng `getId()` và xem nó là ID của Spring Message instance.
- [ ] Đọc `MessageHeaders.TIMESTAMP` bằng `getTimestamp()` và chuyển epoch milliseconds sang `Instant` khi cần.
- [ ] Không tự gán ID/timestamp cho message thông thường.
- [ ] Tạo `eventId` ổn định nếu cần dedup hoặc replay event.
- [ ] Dùng correlation ID để liên kết request/reply, splitter/aggregator hoặc workflow.
- [ ] Dùng trace context để theo dõi luồng qua nhiều process.
- [ ] Xác định rõ header nào cần propagate qua transformer và adapter.
- [ ] Kiểm tra mapping giữa Spring headers và native AMQP/JMS headers.
- [ ] Không giả định retry/redelivery giữ nguyên Spring Message ID.
- [ ] Ghi log cả message ID, event ID và correlation ID khi cần điều tra; tránh log payload nhạy cảm.
- [ ] Dùng timestamp nghiệp vụ riêng khi cần biết lúc sự kiện thực sự xảy ra.

## 12. Kết luận

`MessageHeaders.ID` định danh một Spring Message instance bằng UUID; `MessageHeaders.TIMESTAMP` ghi lại thời điểm instance đó được tạo. Khi flow tạo message mới, hai giá trị này thuộc về message mới và có thể thay đổi, trong khi event ID, business ID, correlation ID và trace context được giữ theo mục đích riêng. Hãy dùng `MessageBuilder` hoặc `MessageHeaderAccessor` để tạo và chỉnh header, phân biệt thời gian tạo wrapper với thời gian nghiệp vụ, và kiểm tra quy tắc mapping khi message đi qua broker.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2.18 Javadoc: MessageHeaders](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/MessageHeaders.html) — kiểu dữ liệu, hằng số ID/TIMESTAMP và quy tắc ID tự sinh.
- [Spring Framework 6.2.18 Javadoc: MessageBuilder](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/MessageBuilder.html) — tạo message mới, copy header và quy tắc không ghi đè ID/timestamp.
- [Spring Framework 6.2.18 Javadoc: MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html) — accessor, trạng thái mutable/immutable và đọc header.
- [Spring Integration Reference: Message](https://docs.spring.io/spring-integration/reference/message.html) — message ID generation, read-only headers, propagation, splitter/aggregator metadata và MessageBuilder.
- [Spring Integration Reference: AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html) — ánh xạ Spring headers với AMQP MessageProperties.
- [Spring Integration Reference: JMS Support](https://docs.spring.io/spring-integration/reference/jms.html) — ánh xạ Spring headers với JMS headers/properties.
