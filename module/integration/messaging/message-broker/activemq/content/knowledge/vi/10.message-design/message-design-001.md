# Cấu trúc header, properties và body của JMS Message

> **Chương:** Thiết kế thông điệp  
> **Bối cảnh:** Apache ActiveMQ Classic/Artemis, producer và consumer Java dùng JMS/Jakarta Messaging để trao đổi thông điệp qua queue/topic. Bài này tập trung vào **cấu trúc và hợp đồng dữ liệu của từng message**, không đi sâu vào cách cấu hình routing, acknowledgment hay DLQ.

## 1. Một message được tổ chức thành ba phần

Khi gửi sự kiện `OrderCreated`, ứng dụng cần mô tả **gửi đi đâu**, **metadata nào giúp broker/client xử lý**, và **dữ liệu nghiệp vụ thực sự là gì**. Trong JMS, đối tượng `Message` có ba vùng thông tin:

```text
JMS Message
├── Headers (trường JMS được chuẩn hóa)
│   ├── JMSMessageID, JMSTimestamp, JMSDestination
│   ├── JMSDeliveryMode, JMSPriority, JMSExpiration, JMSDeliveryTime
│   └── JMSCorrelationID, JMSReplyTo, JMSType, JMSRedelivered
├── Properties (metadata có tên, kiểu giá trị đơn giản)
│   ├── eventType = "OrderCreated"          (String)
│   ├── schemaVersion = 2                   (int)
│   ├── region = "VN"                       (String)
│   └── JMSXDeliveryCount = 1               (do provider cung cấp)
└── Body (payload)
    └── TextMessage: {"eventId":"evt-1001","orderId":"O-1001",...}
```

- **Headers** có ý nghĩa chuẩn của JMS. Một số do producer chỉ định, một số do **JMS provider** gán khi gửi hoặc giao thông điệp.
- **Properties** là cặp *tên → giá trị có kiểu*, tiện để lọc message bằng **message selector** và chuyển metadata nhẹ giữa producer/consumer.
- **Body** chứa nội dung nghiệp vụ: văn bản, bytes, map, stream, đối tượng Java serializable hoặc không có body.

Ví dụ, `JMSMessageID` là định danh do provider cấp cho lần gửi; `eventId` bên trong JSON là định danh **sự kiện nghiệp vụ** do ứng dụng quản lý. Hai ID có thể cùng xuất hiện nhưng **không thay thế nhau**.

## 2. Headers: ý nghĩa, nguồn gốc và thời điểm có giá trị

Các tên header JMS viết hoa theo chuẩn; không thể tự tạo header mới chỉ bằng cách đặt tên biến `JMSFoo`. Metadata riêng của ứng dụng phải nằm trong **properties** hoặc **body**.

| Header | Chức năng chính | Ai thường quyết định? | Lưu ý khi đọc |
| --- | --- | --- | --- |
| `JMSDestination` | Destination mà message được gửi đến | Provider thiết lập khi `send` | Là `Destination`, không nhất thiết là chuỗi queue name |
| `JMSDeliveryMode` | `PERSISTENT` hoặc `NON_PERSISTENT` | Producer chọn; provider đặt lên message | Chỉ thể hiện delivery mode, không thay thế kiểm thử độ bền |
| `JMSExpiration` | Thời điểm hết hạn (epoch milliseconds) | Provider tính từ TTL khi gửi | `0` nghĩa là không có expiration theo JMS |
| `JMSPriority` | Độ ưu tiên từ `0` đến `9` | Producer chọn; mặc định `4` | Broker không bắt buộc luôn giao đúng thứ tự ưu tiên tuyệt đối |
| `JMSMessageID` | Định danh message do provider tạo | Provider khi gửi | Có thể `null` nếu chức năng tạo ID bị tắt có chủ đích |
| `JMSTimestamp` | Thời điểm provider gửi message (epoch milliseconds) | Provider khi gửi | Không nhất thiết là thời gian tạo sự kiện nghiệp vụ |
| `JMSCorrelationID` | Liên hệ message với request/transaction ở tầng ứng dụng | Ứng dụng gửi | Thường dùng cho request–reply; không phải cơ chế khớp tự động |
| `JMSReplyTo` | Destination mà ứng dụng nhận muốn gửi phản hồi về | Ứng dụng gửi | Provider không tự tạo reply hay tự trả lời |
| `JMSType` | Chuỗi phân loại message tùy quy ước ứng dụng | Ứng dụng gửi | Không tự bảo đảm schema, routing hay Java type |
| `JMSRedelivered` | Message có khả năng đã được giao trước đó | Provider khi phân phối | Một chỉ dấu redelivery, không phải định danh lần xử lý |
| `JMSDeliveryTime` | Mốc sớm nhất message đủ điều kiện giao (JMS 2.0+) | Provider tính từ delivery delay khi gửi | Không bảo đảm được giao đúng chính xác tại mốc đó |

### 2.1. Header do ứng dụng chủ động đặt và header do provider quản lý

Những header ứng dụng thường **đặt trực tiếp** trước `send`:

```java
// message là một jakarta.jms.TextMessage đã được tạo.
message.setJMSCorrelationID("request-42");
message.setJMSType("OrderCreated");
// Nếu có cơ chế request–reply:
// message.setJMSReplyTo(replyQueue);
```

Những trường được thiết lập bằng **cấu hình producer**, thay vì tùy tiện gọi setter header:

```java
context.createProducer()
       .setDeliveryMode(DeliveryMode.PERSISTENT)
       .setPriority(7)
       .setTimeToLive(60_000L)
       .setDeliveryDelay(2_000L)
       .send(queue, message);
```

Ví dụ này dùng `JMSProducer` của JMS 2.0+/Jakarta Messaging. Nó yêu cầu provider gửi dạng persistent, priority `7`, TTL `60 giây` và delivery delay `2 giây`. Provider tính các header như `JMSTimestamp`, `JMSExpiration`, `JMSDeliveryTime` khi thực hiện `send`.

**Không đặt `JMSMessageID` bằng tay để làm định danh nghiệp vụ.** Nếu cần tracking xuyên retry, hãy dùng `eventId` hoặc `idempotencyKey` trong body/properties. Một message nghiệp vụ được gửi lại có thể nhận **`JMSMessageID` mới**.

### 2.2. Phân biệt ba mốc thời gian

Giả sử producer gửi lúc **12:00:00**, delay **2 giây**, TTL **60 giây**:

| Trường | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `JMSTimestamp` | 12:00:00 | Mốc gửi do provider gán |
| `JMSDeliveryTime` | 12:00:02 | Message chưa nên được giao trước mốc này |
| `JMSExpiration` | 12:01:00 | Message không còn hợp lệ để giao sau thời hạn |

Đây là ví dụ lý tưởng để phân biệt trường, **không phải bảo đảm scheduling theo mili giây**. Nếu đặt TTL ngắn hơn delivery delay, message có thể hết hạn trước khi được giao. Thời điểm business event xảy ra có thể sớm hơn `JMSTimestamp`, nên có thể ghi `occurredAt` trong body.

Khi message đến consumer, `JMSRedelivered` và property `JMSXDeliveryCount` (nếu provider cung cấp theo đặc tả/phiên bản) phản ánh lịch sử giao ở broker, chứ không nói consumer đã commit nghiệp vụ bên ngoài.

### 2.3. Header không phải nội dung tùy ý

Không đưa JSON hoặc dữ liệu nhạy cảm vào `JMSType`, `JMSCorrelationID` hay tên queue chỉ để tiện debug. Header có semantics chuẩn và có thể xuất hiện trong logging/management. Hợp đồng ứng dụng nên quy định rõ:

- **`eventId`:** ID của sự kiện nghiệp vụ (ổn định khi retry).
- **`JMSCorrelationID`:** ID liên kết một chuỗi request–reply hoặc trace theo quy ước đã thống nhất.
- **`JMSMessageID`:** ID của message trên broker, dùng quan sát và chẩn đoán, không là business key mặc định.

## 3. Properties: metadata có kiểu, có tên và có thể lọc

Properties được truy cập qua `Message.set<Type>Property` và `get<Type>Property`:

```java
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
message.setStringProperty("region", "VN");
message.setBooleanProperty("requiresReview", false);
message.setLongProperty("amountVnd", 125_000L);
```

JMS property hỗ trợ các kiểu giá trị cơ bản: `boolean`, `byte`, `short`, `int`, `long`, `float`, `double` và `String`. `setObjectProperty` chỉ chấp nhận những kiểu wrapper tương ứng hoặc `String` được đặc tả hỗ trợ; không dùng nó để nhét tùy ý `List`, `Map`, `BigDecimal`, DTO hay byte array. Những dữ liệu phức tạp thuộc về **body**.

Các quy tắc quan trọng:

1. Tên property tuân theo quy tắc định danh của JMS selector (kiểu Java identifier) và phải tránh những từ khóa/tên dành riêng. Ưu tiên tên đơn giản như `eventType`, `schemaVersion`, `tenantId`.
2. Phân biệt chữ hoa/chữ thường: `region` và `Region` là hai tên khác nhau.
3. Property không tồn tại khác với giá trị rỗng. Dùng `message.propertyExists("region")` trước khi xử lý trường tùy chọn.
4. Getter typed chỉ có một số phép chuyển kiểu được JMS cho phép. Ví dụ property chuỗi `"12"` không nên dùng thay cho `int 12` trong hợp đồng selector.
5. Đừng dùng properties làm nơi chứa toàn bộ JSON. Metadata lớn gây chi phí serialize, index/filter và truyền mạng không cần thiết.
6. Tên bắt đầu `JMSX` được dành cho nhóm properties JMS-defined; `JMS_<provider>` và một số tên đặc biệt thuộc phạm vi provider. Ứng dụng không nên tự chiếm tên đó để chứa dữ liệu riêng.

### 3.1. Properties chuẩn mở rộng và properties của provider

Bên cạnh thuộc tính ứng dụng, JMS có nhóm **`JMSX...`**:

| Property | Dùng để làm gì | Lưu ý |
| --- | --- | --- |
| `JMSXDeliveryCount` | Đếm số lần message được giao | JMS 2.0+ chuẩn hóa yêu cầu provider cung cấp; quan sát số lần giao, không dùng làm business ID |
| `JMSXGroupID` | Nhóm các message liên quan để hỗ trợ message grouping | Cách pin group vào consumer và rebalance tùy provider |
| `JMSXGroupSeq` | Số thứ tự/báo hiệu trong nhóm | Quy ước kết thúc nhóm có thể có phần mở rộng của provider |
| `JMSXUserID` | Thông tin định danh producer theo khả năng/provider | Không nên coi giá trị tùy chọn này là bằng chứng xác thực độc lập |

Trong ActiveMQ Classic/Artemis, `JMSXGroupID` thường được dùng khi muốn cùng nhóm công việc được một consumer xử lý có thứ tự tương đối. Đây là cơ chế dispatch của broker, không phải khả năng serialize object Java.

Một số tên property riêng của broker, ví dụ thuộc tính scheduling/duplicate detection, **không thuộc hợp đồng JMS portable**. Khi dùng chúng, ghi rõ phiên bản Classic/Artemis và protocol; không kỳ vọng một JMS provider khác sẽ hiểu.

### 3.2. Message selectors chỉ đọc header/properties, không phân tích body

Consumer có thể yêu cầu broker chỉ giao message có metadata phù hợp:

```sql
eventType = 'OrderCreated'
AND schemaVersion >= 2
AND region = 'VN'
```

Tạo selector bằng JMS:

```java
String selector =
        "eventType = 'OrderCreated' AND schemaVersion >= 2 AND region = 'VN'";
JMSConsumer consumer = context.createConsumer(queue, selector);
```

Điểm quan trọng:

- Selector dùng một tập cú pháp tương tự SQL, với so sánh, `AND`/`OR`/`NOT`, `IS NULL`, `IN`, `LIKE`… nhưng **không phải một câu SQL chạy trên database**.
- Selector làm việc với **properties** và các header được JMS cho phép; không tự parse JSON trong `TextMessage`. Nếu cần lọc theo `region`, producer phải đặt property `region` hoặc kiến trúc phải có bước phân loại riêng.
- So sánh có quan hệ với **kiểu**: `schemaVersion = 2` so sánh số; `schemaVersion = '2'` so sánh chuỗi và không tương đương.
- Property chưa đặt được coi là `NULL` trong biểu thức selector, khiến biểu thức như `region = 'VN'` không khớp; dùng `IS NULL` khi muốn bắt trường hợp thiếu.
- Selector chỉ lọc **delivery** đến consumer. Với queue, message không khớp có thể **vẫn nằm chờ** consumer khác, dẫn đến backlog. Selector không phải ACL hay cơ chế phân quyền tenant.

Khi có yêu cầu lọc phức tạp hoặc lưu lượng lớn, nên đo độ trễ thực tế: nhiều selector trên một queue có thể tạo gánh nặng xét điều kiện và khó vận hành hơn phân tách queue/routing rõ ràng.

## 4. Body: chọn kiểu message theo hợp đồng dữ liệu

JMS hỗ trợ các kiểu message sau; lựa chọn ảnh hưởng tới cách đọc/ghi trong Java và tính tương thích giữa producer/consumer.

| Kiểu | Body chứa | Khi nên dùng | Rủi ro/cân nhắc |
| --- | --- | --- | --- |
| `TextMessage` | `String` | JSON, XML, văn bản có schema | JMS không tự kiểm tra JSON/schema/encoding trên wire |
| `BytesMessage` | Chuỗi byte và dữ liệu primitive ghi/đọc tuần tự | Protobuf, Avro binary, file chunk, codec tùy chọn | Hai đầu phải thống nhất codec, version và cách giải mã |
| `MapMessage` | Map tên → giá trị primitive, `String`, `byte[]` | Payload nhỏ có cấu trúc đơn giản trong hệ sinh thái JMS | Không phải JSON; kiểu và tương thích cross-protocol có thể khác |
| `StreamMessage` | Dãy giá trị primitive/`String` theo thứ tự | Các format theo luồng legacy | Cần biết đúng thứ tự/kiểu đọc; ít phù hợp schema thay đổi |
| `ObjectMessage` | Java `Serializable` object | Tương thích hệ thống Java legacy kiểm soát hoàn toàn | Java deserialization có nguy cơ bảo mật và lệ thuộc class/version; tránh cho tích hợp ngoài |
| `Message` | Không có body | Tín hiệu/trigger mà chỉ metadata có ý nghĩa | Phải quy định ý nghĩa rõ ràng để tránh “empty message” mơ hồ |

### 4.1. `TextMessage` với JSON: lựa chọn dễ quản lý hợp đồng

```java
TextMessage event = context.createTextMessage(
    "{\"eventId\":\"evt-1001\","
    + "\"orderId\":\"O-1001\","
    + "\"totalVnd\":125000,"
    + "\"occurredAt\":\"2026-11-17T07:00:00Z\"}"
);
event.setStringProperty("contentType", "application/json");
event.setIntProperty("schemaVersion", 2);
```

`contentType` ở đây là **property do ứng dụng quy ước**, không phải một header chuẩn bắt buộc của JMS. JMS không tự parse JSON; consumer phải dùng thư viện JSON tương ứng và xác thực schema. Không đặt dữ liệu như số tài khoản, token hay secret trong properties chỉ để lọc.

Cần định nghĩa ý nghĩa của `occurredAt` trong JSON và phân biệt với `JMSTimestamp`: timestamp nghiệp vụ có thể được tạo trước khi bắt đầu gửi broker, ví dụ khi lưu transaction log hoặc outbox.

### 4.2. `BytesMessage` khi payload có codec riêng

```java
byte[] encoded = encodeOrderEvent(); // Ví dụ: serialize Protobuf.

BytesMessage binary = context.createBytesMessage();
binary.writeBytes(encoded);
binary.setStringProperty("contentType", "application/x-protobuf");
binary.setIntProperty("schemaVersion", 3);
```

Ở phía consumer:

```java
if (message instanceof BytesMessage) {
    BytesMessage bytesMessage = (BytesMessage) message;
    long length = bytesMessage.getBodyLength();

    if (length < 0 || length > 1_000_000) {
        throw new IllegalArgumentException("Unexpected binary payload size");
    }

    byte[] data = new byte[(int) length];
    int read = bytesMessage.readBytes(data);
    if (read != data.length) {
        throw new IllegalStateException("Incomplete binary payload");
    }

    // OrderEvent parsed = decodeProtobuf(data);
}
```

`readBytes` đọc theo vị trí hiện tại của stream. Trong ứng dụng thật, kiểm tra giới hạn message size, codec, dữ liệu lỗi và hành vi khi payload vượt bộ nhớ; với message lớn, cân nhắc truyền object storage URI và checksum thay vì đẩy blob không giới hạn qua broker.

### 4.3. `MapMessage` và `ObjectMessage` khác nhau căn bản

```java
MapMessage map = context.createMapMessage();
map.setString("orderId", "O-1001");
map.setLong("totalVnd", 125_000L);
map.setBoolean("paid", false);
```

`MapMessage` định nghĩa tập field có kiểu đơn giản, **không tạo instance một Java DTO** ở consumer. Ngược lại, `ObjectMessage` thực sự liên quan tới Java `Serializable` và cơ chế serialize/deserialize của Java. Vì rủi ro deserialization, thay đổi package/class và classloader, nên tránh `ObjectMessage` với message từ nguồn không hoàn toàn tin cậy. ActiveMQ Classic/Artemis có chính sách và tùy chọn kiểm soát trusted/allowlisted class theo phiên bản; đừng tắt cơ chế bảo vệ chỉ để deserialize một object cũ.

### 4.4. Body và properties sau khi nhận

Với nhiều provider, message được nhận sẽ có body/properties ở trạng thái **read-only** theo JMS. Gọi setter trên dữ liệu này có thể ném `MessageNotWriteableException`. JMS cung cấp:

- `clearBody()`: xóa body và cho phép ghi lại body theo kiểu message.
- `clearProperties()`: xóa properties và cho phép đặt lại properties.
- Hai phương thức **không được hiểu là xóa toàn bộ header chuẩn** hoặc tự tạo một message nghiệp vụ mới.

Trong hệ thống có forwarding/enrichment, cách rõ ràng hơn thường là **tạo message mới** và sao chép những trường có chủ đích, để không vô tình mang theo routing, reply-to, correlation hay thông tin dành riêng của provider.

## 5. Ví dụ thực hành: Artemis Jakarta JMS producer/consumer

Giả định broker **Artemis** đang lắng nghe `tcp://localhost:61616`, có queue `orders.events` và tài khoản được cấp quyền gửi/nhận. Nếu broker không auto-create, operator phải tạo queue theo cấu hình trước khi chạy.

Maven dependency minh họa (dùng phiên bản được quản lý tương thích với broker của dự án):

```xml
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.50.0</version>
</dependency>
```

Các ví dụ dùng `jakarta.jms`; nếu dùng Classic 5.x với `javax.jms`, thay artifact bằng `activemq-client` tương ứng và đổi import theo đúng API, còn khái niệm header/properties/body vẫn giữ.

### 5.1. Producer: cấu hình header, properties và body một cách tường minh

File `OrderEventProducer.java`:

```java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class OrderEventProducer {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(required("ARTEMIS_URL"));

        try (JMSContext context = factory.createContext(
                required("ARTEMIS_USER"),
                required("ARTEMIS_PASSWORD"))) {

            Queue queue = context.createQueue("orders.events");

            String json = "{\"eventId\":\"evt-1001\","
                    + "\"orderId\":\"O-1001\","
                    + "\"totalVnd\":125000,"
                    + "\"occurredAt\":\"2026-11-17T07:00:00Z\"}";

            TextMessage message = context.createTextMessage(json);
            message.setJMSType("OrderCreated");
            message.setJMSCorrelationID("trace-42");

            message.setStringProperty("eventType", "OrderCreated");
            message.setIntProperty("schemaVersion", 2);
            message.setStringProperty("region", "VN");
            message.setStringProperty("contentType", "application/json");

            context.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .setPriority(4)
                   .setTimeToLive(60_000L)
                   .send(queue, message);

            // Provider thường đặt các header phát sinh sau send.
            System.out.println("Message ID: " + message.getJMSMessageID());
            System.out.println("Timestamp: " + message.getJMSTimestamp());
            System.out.println("Expiration: " + message.getJMSExpiration());
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }
}
```

Cấu hình môi trường ví dụ:

```text
ARTEMIS_URL=tcp://localhost:61616
ARTEMIS_USER=orders_app
ARTEMIS_PASSWORD=<secret do môi trường cung cấp>
```

Đoạn code cho thấy ba việc riêng biệt: `TextMessage` tạo **body** JSON, các `set...Property` tạo metadata có thể lọc, còn `setDeliveryMode`/`setPriority`/`setTimeToLive` điều khiển **headers/behavior khi gửi**. `JMSType` mang nhãn do ứng dụng chọn, không làm Artemis tự validate JSON theo `OrderCreated`.

### 5.2. Consumer: lọc theo properties, đọc header và body

File `OrderEventConsumer.java`:

```java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class OrderEventConsumer {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(required("ARTEMIS_URL"));

        try (JMSContext context = factory.createContext(
                required("ARTEMIS_USER"),
                required("ARTEMIS_PASSWORD"))) {

            Queue queue = context.createQueue("orders.events");
            String selector = "eventType = 'OrderCreated'"
                    + " AND schemaVersion >= 2"
                    + " AND region = 'VN'";

            JMSConsumer consumer = context.createConsumer(queue, selector);
            Message received = consumer.receive(5_000L);

            if (received == null) {
                System.out.println("No matching event within 5 seconds");
                return;
            }
            if (!(received instanceof TextMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage, got " + received.getClass());
            }

            TextMessage text = (TextMessage) received;
            String eventType = received.getStringProperty("eventType");
            int version = received.getIntProperty("schemaVersion");

            System.out.println("JMSMessageID: " + received.getJMSMessageID());
            System.out.println("JMSCorrelationID: "
                    + received.getJMSCorrelationID());
            System.out.println("JMSType: " + received.getJMSType());
            System.out.println("JMSRedelivered: " + received.getJMSRedelivered());

            if (received.propertyExists("JMSXDeliveryCount")) {
                System.out.println("Delivery count: "
                        + received.getIntProperty("JMSXDeliveryCount"));
            }

            System.out.println("Event type: " + eventType);
            System.out.println("Schema version: " + version);
            System.out.println("JSON body: " + text.getText());

            // Bước thực tế tiếp theo: parse JSON, validate schema và
            // kiểm tra eventId trước khi cập nhật dữ liệu nghiệp vụ.
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }
}
```

Ở đây `AUTO_ACKNOWLEDGE` mặc định giúp tập trung vào cấu trúc message; ứng dụng thật cần thiết kế xử lý lỗi và commit/ack phù hợp. Không suy ra “consumer không nhận” là lỗi kết nối: một selector không khớp vẫn khiến `receive(timeout)` trả `null`.

**Lưu ý thiết kế:** Vì có cả `JMSType="OrderCreated"` và property `eventType="OrderCreated"`, hai giá trị dễ lệch nếu được set độc lập. Chọn một quy ước thống nhất cho contract và kiểm thử nhất quán; chỉ duy trì cả hai khi có nhu cầu tích hợp cụ thể.

## 6. Hợp đồng message bền vững qua nhiều phiên bản

Khi producer và consumer được triển khai độc lập, các trường message là một **API contract**. Ví dụ hợp đồng đề xuất:

```json
{
  "eventId": "evt-1001",
  "orderId": "O-1001",
  "totalVnd": 125000,
  "occurredAt": "2026-11-17T07:00:00Z"
}
```

| Vùng | Trường | Mục đích | Quy ước khuyến nghị |
| --- | --- | --- | --- |
| Header | `JMSMessageID` | Chẩn đoán/tracing ở tầng broker | Do provider cấp, không dùng làm business ID |
| Header | `JMSCorrelationID` | Liên kết request/trace | Có định nghĩa rõ (ví dụ `trace-42`) |
| Property | `eventType` | Selector và nhận dạng loại event | Enum/string ổn định |
| Property | `schemaVersion` | Định tuyến/giải mã đúng schema | **Số nguyên**, tăng khi thay contract |
| Property | `region` | Lọc message theo vùng | String chuẩn hóa, có danh sách giá trị |
| Property | `contentType` | Gợi ý codec | `application/json` hoặc MIME type quy ước |
| Body | `eventId` | Chống xử lý trùng nghiệp vụ | ID ổn định khi producer retry |
| Body | `orderId`, `totalVnd` | Dữ liệu nghiệp vụ | Có ràng buộc kiểu, đơn vị và validation |
| Body | `occurredAt` | Thời gian sự kiện phát sinh | Chuẩn UTC ISO 8601 |

Nguyên tắc tiến hóa schema:

1. Đừng đổi âm thầm nghĩa hoặc kiểu của field đã phát hành. Ví dụ `totalVnd` là số tiền **VND nguyên**, không đổi thành giá trị thập phân USD nhưng giữ tên cũ.
2. Khi thêm field tùy chọn, định nghĩa giá trị mặc định ở consumer và xử lý message phiên bản cũ.
3. Với thay đổi không tương thích, tăng `schemaVersion` và cung cấp consumer/codec cho nhiều phiên bản trong giai đoạn chuyển đổi.
4. Không dùng thứ tự JSON object fields hoặc kiểu Java DTO cụ thể như một phần hợp đồng xuyên service.
5. Đừng coi `JMSTimestamp` hoặc `JMSMessageID` là dữ liệu nguồn duy nhất; dữ liệu nghiệp vụ có thể được phát lại từ outbox hoặc migrate sang broker khác.

### 6.1. Những gì nên để trong property và body

Một quy tắc áp dụng tốt:

- **Property:** field nhỏ, ổn định, có thể dùng để chọn consumer/routing/quan sát; ví dụ `eventType`, `schemaVersion`, `region`.
- **Body:** dữ liệu cần để thực thi nghiệp vụ; ví dụ danh sách sản phẩm, địa chỉ giao hàng, số tiền, thời gian sự kiện.
- **Header chuẩn:** chỉ dùng đúng semantics JMS; không ghi đè bằng một quy ước riêng không tương thích.

Không nên đưa dữ liệu cá nhân hoặc secret vào metadata chỉ vì nó dễ hiển thị trong công cụ quản trị. Với body cũng cần kiểm soát access, thời hạn lưu và logging.

## 7. Các lỗi phổ biến khi thiết kế message

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Consumer selector không thấy message | `schemaVersion` gửi dạng `String` nhưng selector so sánh số, hoặc property sai chữ hoa/thường | Dùng setter typed nhất quán và kiểm tra `propertyExists` |
| JMS ID thay đổi sau retry | `JMSMessageID` là ID của mỗi lần gửi | Dùng `eventId` nghiệp vụ ổn định để deduplicate |
| Mở message thấy body JSON nhưng selector `orderId = ...` không lọc | `orderId` chỉ nằm trong body | Đưa metadata cần lọc vào property có kiểu, hoặc thay thiết kế routing |
| JSON bị parse sai | Hai phía không thống nhất schema/field/version | `schemaVersion`, schema validation và contract test |
| Message hết hạn trước khi worker đọc | TTL ngắn; delivery delay hoặc backlog kéo dài | Điều chỉnh TTL theo nghiệp vụ và latency thực đo |
| Topic/queue xuất hiện message không đúng loại | `JMSType`/`eventType` không tự quyết định routing trong mọi provider | Kiểm tra destination/routing và các rule cụ thể |
| Consumer lỗi khi đọc `ObjectMessage` | Class khác phiên bản, thiếu class hoặc trusted class policy | Đổi sang format dữ liệu có schema; kiểm soát deserialization |
| Chuyển provider thì custom property không còn tác dụng | Dựa trên thuộc tính mở rộng của Classic/Artemis | Phân biệt portable JMS properties và provider extensions |
| Forward message và mang theo metadata cũ | Tái sử dụng message nhận mà không chủ động chọn headers/properties | Tạo message mới, copy dữ liệu có chủ đích |

## 8. Bài thực hành kiểm chứng

**Chuẩn bị:** một Artemis broker test, queue `orders.events`, hai chương trình Java ở mục 5 và tài khoản có quyền gửi/nhận. Ghi lại cả log của producer/consumer và những trường hiển thị trong console broker.

1. **Kiểm tra ba phần:** chạy producer rồi consumer; phân biệt `JMSMessageID`/`JMSTimestamp` thuộc header, `schemaVersion`/`region` thuộc properties, và `eventId`/`orderId` thuộc body.
2. **Thay kiểu property:** sửa producer thành `setStringProperty("schemaVersion", "2")`, giữ selector `schemaVersion >= 2`; quan sát message không khớp hoặc kết quả provider theo type semantics. Khôi phục `setIntProperty` sau thử nghiệm.
3. **Kiểm tra selector:** đổi `region` thành `SG` ở producer; consumer đang lọc `VN` sẽ không nhận. Kiểm tra queue backlog để thấy message có thể vẫn còn đó.
4. **Kiểm tra TTL:** đặt TTL rất ngắn, dừng consumer đủ lâu rồi chạy lại; so sánh kết quả và `JMSExpiration`. Thử delivery delay lớn hơn TTL để hiểu thông điệp có thể hết hạn trước khi đủ điều kiện giao.
5. **Kiểm tra version:** gửi một message `schemaVersion=1` và một message `schemaVersion=2`; dùng hai selector khác nhau, quan sát nhận đúng phiên bản.
6. **Đối chiếu JMS ID với event ID:** gửi lại cùng JSON `eventId` trong một message JMS mới; kiểm tra ID do provider sinh khác nhau, từ đó giải thích vai trò idempotency key.
7. **Kiểm tra dạng body:** thay `TextMessage` bằng `MapMessage`, sau đó dùng consumer mong đợi TextMessage để nhận ra vì sao contract type phải rõ ràng.

**Câu hỏi tự kiểm tra:**

- **`JMSMessageID` và `eventId` có cùng mục đích không?** Không; một do provider cấp, một do nghiệp vụ định nghĩa.
- **Có thể dùng selector lọc trường JSON chỉ nằm trong `TextMessage` không?** Không trực tiếp theo JMS selector chuẩn.
- **`JMSExpiration=0` nghĩa là gì?** Không có thời hạn hết hạn JMS.
- **`JMSReplyTo` có làm broker tự gửi câu trả lời không?** Không; responder phải tự thực hiện gửi reply.
- **`JMSDeliveryTime` có nghĩa broker bắt buộc giao đúng giây đó không?** Không; đó là mốc sớm nhất đủ điều kiện.
- **`setObjectProperty("x", new OrderDto())` có phải cách gửi object JMS hợp lệ?** Không; property không hỗ trợ DTO tùy ý. Body `ObjectMessage` có cơ chế riêng nhưng nên tránh cho tích hợp mới.
- **Dùng `MapMessage` có tương đương gửi JSON không?** Không; `MapMessage` là JMS-defined body với các kiểu dữ liệu riêng.

## 9. Checklist thiết kế JMS Message

- [ ] Đã phân biệt header chuẩn, property metadata và payload body.
- [ ] Không dùng `JMSMessageID` như business ID duy nhất cho retry/dedup.
- [ ] Đã quy định type/đơn vị/ý nghĩa của properties và các field body.
- [ ] Các property cần filter là kiểu đơn giản, tên ổn định và không chứa secret.
- [ ] Selector đã kiểm tra trường thiếu, type mismatch và ảnh hưởng backlog.
- [ ] Đã chọn `TextMessage`/`BytesMessage`/`MapMessage` theo codec và consumer thực tế.
- [ ] Có `schemaVersion` và chiến lược đọc message cũ khi thay contract.
- [ ] TTL, priority và delivery delay có ý nghĩa nghiệp vụ, không đặt tùy tiện.
- [ ] Đã kiểm thử dữ liệu nhận qua broker, gồm header provider tự sinh.
- [ ] Đã xác định những properties mở rộng phụ thuộc ActiveMQ Classic/Artemis.

## Tài liệu tham khảo

1. [Jakarta Messaging 3.1 — đặc tả JMS Message, headers, properties và body](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
2. [Jakarta Messaging 3.1 API — `Message`](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message).
3. [Jakarta Messaging 3.1 API — `TextMessage`](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/textmessage).
4. [Apache ActiveMQ Artemis — Using JMS](https://artemis.apache.org/components/artemis/documentation/latest/using-jms.html).
5. [Apache ActiveMQ Classic — Message Features](https://activemq.apache.org/components/classic/documentation/message-features).
