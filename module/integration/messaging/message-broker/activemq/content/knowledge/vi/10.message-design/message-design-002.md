# TextMessage, BytesMessage, MapMessage, StreamMessage và ObjectMessage

> **Chương:** Thiết kế thông điệp  
> **Bối cảnh:** ActiveMQ Classic và ActiveMQ Artemis; producer/consumer Java sử dụng JMS.  
> **Trọng tâm:** Chọn đúng **kiểu body** theo dữ liệu, cách đọc/ghi, khả năng nâng cấp schema và mức độ tương thích giữa các ứng dụng.

## 1. Cùng là JMS Message, nhưng phần body rất khác nhau

JMS định nghĩa một kiểu `Message` cơ sở và nhiều kiểu con biểu diễn **dữ liệu trong body**. Chọn sai kiểu khiến producer và consumer phải dựa vào những giả định ngầm: thứ tự trường, kiểu dữ liệu, thư viện Java, hoặc cách provider serialize. Khi hai hệ thống phát triển độc lập, những giả định đó dễ trở thành lỗi production.

| Kiểu JMS | Body chứa gì? | Cách đọc tiêu biểu | Hợp với | Hạn chế quan trọng |
|---|---|---|---|---|
| **TextMessage** | Một `String` (có thể là JSON, XML hoặc text) | `getText()` | JSON sự kiện, dữ liệu dễ quan sát, tích hợp liên ngôn ngữ | Cần **tự** quy định schema/định dạng và validate |
| **BytesMessage** | Chuỗi byte; API hỗ trợ đọc/ghi primitive theo thứ tự | `readBytes(...)`, `readInt()` | Protobuf, Avro, payload binary, format tự định nghĩa | Consumer phải biết encoding, framing và version |
| **MapMessage** | Tập cặp tên trường → giá trị thuộc các kiểu JMS hỗ trợ | `getString("orderId")` | Message dạng record phẳng, nhiều trường có tên | Không phải JSON object tổng quát; hạn chế kiểu và cấu trúc lồng nhau |
| **StreamMessage** | Dãy giá trị có kiểu theo thứ tự ghi | `readString()`, `readLong()` | Giao thức positional cố định, legacy integration | Thay đổi thứ tự/thêm trường dễ làm hỏng consumer |
| **ObjectMessage** | Biểu diễn serialized của một `Serializable` Java object | `getObject()` | Hệ thống Java cũ có DTO dùng chung và kiểm soát chặt | Ràng buộc lớp Java/phiên bản, rủi ro Java deserialization; **không khuyến nghị cho thiết kế mới** |

Đừng nhầm tên **BytesMessage** với yêu cầu “mọi byte đều chứa file hoặc dữ liệu binary”, hay **TextMessage** với “broker hiểu JSON”. Broker chủ yếu chuyển và lưu message; **ý nghĩa business của body là hợp đồng giữa producer và consumer**.

### 1.1. Body không phải header hay message property

Cả năm kiểu đều kế thừa phần **header** và **properties** của `Message`. Ví dụ:

```java
message.setJMSCorrelationID("request-789");
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
message.setStringProperty("contentType", "application/json");
```

- `JMSCorrelationID` là header chuẩn cho tương quan request/reply hoặc luồng nghiệp vụ.
- `eventType`, `schemaVersion` và `contentType` ở đây là **application properties do ta tự đặt**; `contentType` không phải header JMS chuẩn có khả năng khiến broker tự parse JSON.
- **Message selector** thường hoạt động trên header/property theo JMS selector semantics, **không** tự truy vấn nội dung JSON nằm trong `TextMessage`.
- Properties chỉ hỗ trợ một tập kiểu chuẩn như boolean, byte, short, int, long, float, double, String; đừng đặt một object Java tùy ý vào property.

Nếu cần lọc `tenant` hay `eventType` ở broker, nên cung cấp property được chuẩn hóa, đồng thời giữ body chứa dữ liệu nghiệp vụ đầy đủ. Tránh duy trì hai giá trị mâu thuẫn cho cùng một ý nghĩa.

## 2. TextMessage: thuận tiện cho hợp đồng sự kiện có schema

`TextMessage` lưu một chuỗi, cho phép gửi JSON/XML hoặc một định dạng text khác. Nó **không** bảo đảm body là JSON hợp lệ hoặc tự thực thi JSON Schema; consumer phải deserialize và validate.

### 2.1. Gửi và đọc JSON

```java
// Session, producer và consumer được tạo trước đó.
String json = "{"
        + "\"schemaVersion\":2,"
        + "\"eventId\":\"evt-100\","
        + "\"eventType\":\"OrderCreated\","
        + "\"orderId\":\"O-100\","
        + "\"amountMinor\":129900,"
        + "\"currency\":\"VND\""
        + "}";

TextMessage outgoing = session.createTextMessage(json);
outgoing.setStringProperty("contentType", "application/json");
outgoing.setIntProperty("schemaVersion", 2);
outgoing.setStringProperty("eventType", "OrderCreated");
producer.send(outgoing);

// Phía nhận:
Message incoming = consumer.receive(5000);
if (!(incoming instanceof TextMessage)) {
    throw new IllegalArgumentException("Expected TextMessage");
}
String text = ((TextMessage) incoming).getText();
// Parse + validate bằng Jackson/Gson hoặc thư viện JSON phù hợp.
```

Trong ứng dụng thật, **serialize DTO qua thư viện JSON** thay vì ghép chuỗi thủ công. Định nghĩa schema theo phiên bản và một quy tắc rõ ràng cho trường bắt buộc, giá trị null, thời gian, tiền và những trường mở rộng.

### 2.2. Những chi tiết dễ sai

- `getText()` có thể trả về `null` nếu text chưa được đặt; **null body** khác chuỗi rỗng `""`.
- Java `String` là chuỗi ký tự; cách provider biểu diễn trên wire/storage phụ thuộc giao thức. Đừng tuyên bố mọi `TextMessage` luôn là JSON UTF-8 bytes nguyên xi.
- Dữ liệu tiền như `129900` nên quy ước **số đơn vị nhỏ nhất** (`amountMinor`) hoặc decimal string theo hợp đồng, tránh suy diễn từ floating point.
- Với JSON có nhiều consumer khác ngôn ngữ, kiểm thử Unicode, số nguyên lớn, time zone và tương thích khi thêm trường.
- Body rất lớn làm tăng độ trễ parse, memory, pressure của broker; các file lớn thường phù hợp hơn với object storage + message tham chiếu có checksum và quyền truy cập phù hợp.

**Chọn TextMessage khi:** tích hợp sự kiện JSON giữa Java và hệ thống Python/Node/.NET, cần quan sát payload dễ dàng và có kế hoạch thay đổi schema.

## 3. BytesMessage: xác định chính xác format và framing

`BytesMessage` là vùng body chứa byte. JMS cho phép ghi trực tiếp mảng byte hoặc các primitive theo thứ tự, ví dụ `writeInt`, `writeLong`, `writeUTF`. Phía nhận phải biết **đã ghi theo format nào**.

### 3.1. Gửi binary có metadata định dạng

```java
byte[] protobufBytes = encodeOrderWithProtobuf(order); // Hàm của ứng dụng

BytesMessage outgoing = session.createBytesMessage();
outgoing.writeBytes(protobufBytes);
outgoing.setStringProperty("contentType", "application/x-protobuf");
outgoing.setStringProperty("schemaName", "OrderCreated");
outgoing.setIntProperty("schemaVersion", 3);
producer.send(outgoing);
```

`encodeOrderWithProtobuf` ở đây là hàm của ứng dụng, không phải API JMS. Nếu gửi Protobuf, phía nhận cần đúng schema/generated code hoặc registry tương thích.

Khi đọc, phải giới hạn kích thước **trước khi** cấp phát bộ nhớ:

```java
BytesMessage incoming = (BytesMessage) consumer.receive(5000);
if (incoming == null) {
    throw new IllegalStateException("No message");
}
long bodyLength = incoming.getBodyLength();
final long maxPayloadBytes = 1024 * 1024; // Giới hạn ứng dụng: 1 MiB

if (bodyLength > maxPayloadBytes) {
    throw new IllegalArgumentException("Payload too large");
}

java.io.ByteArrayOutputStream buffer =
        new java.io.ByteArrayOutputStream((int) bodyLength);

byte[] chunk = new byte[4096];
int count;
while ((count = incoming.readBytes(chunk)) != -1) {
    if (count == 0) {
        throw new IllegalStateException("No read progress");
    }
    buffer.write(chunk, 0, count);
}
byte[] payload = buffer.toByteArray();
// decodeOrderWithProtobuf(payload) theo schemaVersion thực tế.
```

Ở đây producer đã ghi **một trường byte array** qua `writeBytes`, nên ví dụ đọc tuần tự theo chunk là phù hợp. Nếu body chứa nhiều primitive/byte-array fields xen kẽ, consumer phải đọc đúng cấu trúc đã ghi, không tùy tiện ghép toàn bộ thành Protobuf bytes.

### 3.2. Ghi primitive khác với ghi raw bytes

Hai producer sau tạo **hai format body khác nhau**:

```java
// Format A: một chuỗi được ghi bằng writeUTF của JMS.
BytesMessage a = session.createBytesMessage();
a.writeUTF("xin chào");

// Format B: UTF-8 bytes thông thường.
BytesMessage b = session.createBytesMessage();
b.writeBytes("xin chào".getBytes(
        java.nio.charset.StandardCharsets.UTF_8));
```

`writeUTF` có framing/encoding theo quy tắc ghi UTF của JMS/DataOutput, bao gồm length prefix, và **không nên** được coi là raw UTF-8 bytes giống `String.getBytes(UTF_8)`. Nếu ứng dụng ngoài Java mong JSON UTF-8, hãy dùng cùng format raw bytes được mô tả trong contract, không dùng `writeUTF` ngầm.

### 3.3. Read mode, write mode, vị trí đọc

- Khi mới tạo, `BytesMessage` ở **write-only body mode**; sau khi nhận, body ở **read-only mode**.
- `reset()` chuyển body sang read-only và đưa con trỏ đọc về đầu; có thể dùng khi producer muốn tự kiểm tra body trước khi gửi.
- `clearBody()` xóa body cũ và cho phép ghi lại (cẩn thận không vô tình bỏ message đang chuẩn bị).
- `readBytes(byte[])` dùng bộ đệm phía caller và có thể trả `-1` khi hết phần byte array/stream theo semantics JMS; không được lặp vô hạn hoặc hiểu nhầm số byte đọc với `getBodyLength()` trong một message chứa nhiều trường.
- Với API primitive như `writeInt` rồi `writeUTF`, consumer phải đọc `readInt` rồi `readUTF` đúng thứ tự.

**Chọn BytesMessage khi:** cần dữ liệu binary compact (Protobuf/Avro), ảnh/âm thanh có kích thước phù hợp giới hạn broker, hoặc tích hợp qua chuẩn định dạng byte đã thống nhất.

## 4. MapMessage: record phẳng, trường có tên và kiểu rõ ràng

`MapMessage` chứa map của **tên trường dạng String** tới các giá trị được JMS hỗ trợ: primitive, wrapper tương ứng, `String` và `byte[]`. Nó không phải `Map<String, Object>` tổng quát có thể chứa danh sách lồng nhau, map lồng nhau hoặc DTO tự định nghĩa.

```java
MapMessage outgoing = session.createMapMessage();
outgoing.setString("orderId", "O-100");
outgoing.setLong("amountMinor", 129900L);
outgoing.setString("currency", "VND");
outgoing.setBoolean("priority", false);
outgoing.setBytes("hash", new byte[] { 0x01, 0x02 });
producer.send(outgoing);

// Phía nhận:
MapMessage incoming = (MapMessage) consumer.receive(5000);
String orderId = incoming.getString("orderId");
long amountMinor = incoming.getLong("amountMinor");
String currency = incoming.getString("currency");
boolean priority = incoming.getBoolean("priority");
byte[] hash = incoming.getBytes("hash");
```

### 4.1. Khác biệt so với TextMessage JSON

| Tiêu chí | MapMessage | TextMessage chứa JSON |
|---|---|---|
| Tên field | Truy cập bằng `getString("key")`, `getLong("key")` | Deserialize JSON object rồi truy cập key |
| Kiểu | Chỉ những kiểu JMS MapMessage hỗ trợ | JSON object/array/null/number/string/boolean; schema phải bổ sung ràng buộc |
| Dữ liệu lồng nhau | Không dùng object/map tùy ý trực tiếp | Có thể biểu diễn cấu trúc lồng nhau |
| Tích hợp ngoài Java | Phụ thuộc JMS/provider protocol mapping | Dễ hơn khi các bên thống nhất JSON text/binary |
| Schema evolution | Có thể thêm field tùy chọn, nhưng phải quy định mặc định/kiểu | Có thể version hóa schema rõ ràng và dùng validator |
| Cách debug | Công cụ cần hiểu JMS map body | Text JSON dễ đọc/log (khi đã lọc dữ liệu nhạy cảm) |

### 4.2. Các quy tắc cần tôn trọng

- **Tên field là case-sensitive**: `orderId` khác `orderID`.
- `itemExists("field")` giúp phân biệt field không tồn tại với field có giá trị null.
- Các phương thức getter có quy tắc chuyển đổi một số kiểu nguyên thủy/chuỗi theo JMS, nhưng **không nên** dựa vào ép kiểu ngầm giữa producer và consumer. Hợp đồng phải ghi rõ `amountMinor` là `long`, `priority` là `boolean`.
- `setObject` chỉ chấp nhận những kiểu MapMessage hỗ trợ; `setObject("order", new OrderDto(...))` không phải cách gửi DTO tùy ý.
- JMS selector xem **message properties**, không tự lọc trực tiếp trường body `MapMessage`. Nếu broker cần lọc theo `currency`, đặt thêm property `currency` theo contract.

**Chọn MapMessage khi:** có record phẳng, các field có kiểu đơn giản, toàn bộ luồng trao đổi nằm trong hệ JMS/provider đã được kiểm thử và không cần nested schema.

## 5. StreamMessage: các giá trị có thứ tự, không có tên field

`StreamMessage` lưu một **chuỗi giá trị có kiểu** theo đúng thứ tự ghi. Nó khác `BytesMessage` ở chỗ API mang theo khái niệm typed field, nhưng giống ở yêu cầu producer và consumer phải thống nhất thứ tự.

```java
// Producer quy ước: field 1 = orderId, 2 = amountMinor, 3 = urgent.
StreamMessage outgoing = session.createStreamMessage();
outgoing.writeString("O-100");
outgoing.writeLong(129900L);
outgoing.writeBoolean(true);
producer.send(outgoing);

// Consumer bắt buộc đọc cùng thứ tự:
StreamMessage incoming = (StreamMessage) consumer.receive(5000);
String orderId = incoming.readString();
long amountMinor = incoming.readLong();
boolean urgent = incoming.readBoolean();
```

### 5.1. Vì sao dễ gãy khi nâng version?

Version 1:

```text
[orderId:String] [amountMinor:long] [urgent:boolean]
```

Nếu version 2 chèn `currency:String` vào giữa mà không thay đổi consumer:

```text
[orderId:String] [currency:String] [amountMinor:long] [urgent:boolean]
```

Consumer cũ vẫn đọc phần tử 2 bằng `readLong()`, nhưng thực tế đó là `String "VND"`. Kết quả có thể là `MessageFormatException` hoặc lỗi chuyển đổi, tùy phép chuyển đổi được JMS hỗ trợ. Không có key để nhận diện “đây là currency”.

Cách phòng tránh khi bắt buộc dùng StreamMessage: đóng băng thứ tự, ghi rõ type table, thêm version field ở vị trí đầu tiên và thiết lập decoder theo version; sau đó kiểm thử cả producer mới/consumer cũ và ngược lại.

### 5.2. Byte-array field trong StreamMessage

`writeBytes(byte[])` ghi một trường byte array. Khi đọc bằng `readBytes(byte[])`, có thể cần nhiều lần gọi để lấy hết trường này; sau khi phần bytes hết, JMS báo `-1` và consumer mới tiếp tục đọc trường kế tiếp theo thứ tự. Không được đọc nhầm byte-array thành một kiểu scalar khác.

**Chọn StreamMessage khi:** hợp đồng tích hợp đã thống nhất một chuỗi positional rất ổn định, thường là hệ thống legacy. Với event mới có nhiều field thay đổi theo thời gian, JSON/Protobuf có schema thường rõ ràng hơn.

## 6. ObjectMessage: tiện trong Java legacy, nhưng ràng buộc và rủi ro cao

`ObjectMessage` mang biểu diễn serialized của một object triển khai `java.io.Serializable`. Nó hấp dẫn vì producer có thể gửi DTO mà không tự viết serializer:

```java
public final class OrderSnapshot
        implements java.io.Serializable {

    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final long amountMinor;

    public OrderSnapshot(String orderId, long amountMinor) {
        this.orderId = orderId;
        this.amountMinor = amountMinor;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getAmountMinor() {
        return amountMinor;
    }
}

// Producer:
ObjectMessage outgoing = session.createObjectMessage(
        new OrderSnapshot("O-100", 129900L));
producer.send(outgoing);

// Consumer Java có cùng lớp tương thích:
ObjectMessage incoming = (ObjectMessage) consumer.receive(5000);
OrderSnapshot order = (OrderSnapshot) incoming.getObject();
```

### 6.1. Ba lớp ràng buộc

1. **Java classpath và binary compatibility.** Consumer cần class phù hợp và thường là `serialVersionUID` tương thích. `serialVersionUID` **không** thay thế kế hoạch schema evolution hay bảo đảm field mới/cũ có nghĩa đúng.
2. **Tính liên ngôn ngữ thấp.** Một consumer Python/Node không tự giải mã Java native serialization thành DTO nghiệp vụ chỉ vì broker hỗ trợ AMQP 1.0; cần mapping/decoder chuyên biệt và thỏa thuận format.
3. **Rủi ro bảo mật deserialization.** Deserialization object từ dữ liệu chưa tin cậy có thể kích hoạt gadget chain hoặc lỗi runtime. ActiveMQ Classic client có cơ chế trusted packages, Artemis cũng có cấu hình allow/deny deserialization; cơ chế cụ thể phụ thuộc client/broker version.

**Không bật các tùy chọn “trust all packages” chỉ để làm demo chạy.** Với hệ thống legacy buộc dùng ObjectMessage, chỉ allowlist package nhỏ cần thiết, kiểm soát quyền publish, cập nhật dependency và kiểm tra chính sách deserialize của cả sender/receiver/broker.

### 6.2. Chi phí và hậu quả khi thay DTO

Nếu producer nâng DTO từ `OrderSnapshot(String orderId, long amountMinor)` sang cấu trúc có thêm `BigDecimal total`, consumer cũ có thể đọc sai/ngầm nhận null/không deserialize được. Khả năng tương thích thực tế còn phụ thuộc kiểu field, `serialVersionUID`, custom serialization và phiên bản code.

**Lựa chọn cho hệ thống mới:** chuyển sang `TextMessage` với JSON schema hoặc `BytesMessage` với Protobuf/Avro, để hợp đồng độc lập với JVM class internals.

## 7. Ví dụ chạy đủ năm loại với Java JMS

Bài thực hành dưới đây dùng **ActiveMQ Classic JMS client 5.x** (OpenWire) để dễ chạy trên Classic hoặc Artemis có **OpenWire acceptor**. Nó giúp quan sát ngay kiểu body nhận được và cách đọc đúng từng loại. Lưu ý: **ObjectMessage là phần legacy minh họa**, không phải khuyến nghị dùng nó trong luồng sản xuất mới.

### 7.1. Dependency và điều kiện

Maven dependency:

```xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>activemq-client</artifactId>
  <version>5.18.5</version>
</dependency>
```

Dùng `javax.jms` theo client 5.x. Broker cần chạy tại `tcp://localhost:61616`, hoặc truyền URL khác bằng argument; tài khoản (nếu cần) lấy từ `BROKER_USER`/`BROKER_PASSWORD`. Queue có tên riêng cho mỗi lần chạy, do đó cần quyền tạo tài nguyên phù hợp; dùng broker thử nghiệm không có consumer khác.

Với phiên bản ActiveMQ Classic client này, phần `ObjectMessage` dùng một allowlist package cụ thể `demo.messaging`. Một số broker cũng kiểm soát deserialization ở phía server và có thể cần cấu hình phù hợp; nếu tổ chức cấm ObjectMessage, **hãy bỏ mục ObjectMessage trong demo và không nới lỏng policy bảo mật**.

### 7.2. Chương trình producer/consumer hoàn chỉnh

Đặt file `src/main/java/demo/messaging/MessageBodyTypesDemo.java`:

```java
package demo.messaging;

import java.io.ByteArrayOutputStream;
import java.io.Serializable;
import java.util.Arrays;
import java.util.UUID;
import javax.jms.*;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class MessageBodyTypesDemo {

    public static final class OrderSnapshot implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String orderId;
        private final long amountMinor;

        public OrderSnapshot(String id, long amount) {
            this.orderId = id;
            this.amountMinor = amount;
        }

        @Override
        public String toString() {
            return orderId + ":" + amountMinor;
        }
    }

    public static void main(String[] args) throws Exception {
        String url = args.length > 0 ? args[0] : "tcp://localhost:61616";
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);

        // Allowlist cho ObjectMessage legacy; tránh trustAllPackages.
        factory.setTrustedPackages(Arrays.asList(
                "demo.messaging", "java.lang", "java.util"));

        String user = System.getenv("BROKER_USER");
        String pass = System.getenv("BROKER_PASSWORD");
        Connection connection = (user == null || user.isEmpty())
                ? factory.createConnection()
                : factory.createConnection(user, pass);

        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                String queueName = "demo.bodytypes." + UUID.randomUUID();
                Queue queue = session.createQueue(queueName);
                MessageProducer producer = session.createProducer(queue);
                MessageConsumer consumer = session.createConsumer(queue);

                try {
                    TextMessage text = session.createTextMessage(
                            "{\"orderId\":\"O-100\",\"amountMinor\":129900}");
                    text.setStringProperty("bodyFormat", "json");
                    producer.send(text);

                    BytesMessage bytes = session.createBytesMessage();
                    bytes.writeBytes(new byte[] {1, 2, (byte) 255});
                    bytes.setStringProperty(
                            "bodyFormat", "application/octet-stream");
                    producer.send(bytes);

                    MapMessage map = session.createMapMessage();
                    map.setString("orderId", "O-100");
                    map.setLong("amountMinor", 129900L);
                    producer.send(map);

                    StreamMessage stream = session.createStreamMessage();
                    stream.writeString("O-100");
                    stream.writeLong(129900L);
                    stream.writeBoolean(true);
                    producer.send(stream);

                    ObjectMessage object = session.createObjectMessage(
                            new OrderSnapshot("O-100", 129900L));
                    producer.send(object);

                    session.commit(); // Commit cả năm lần gửi.
                    connection.start();

                    for (int i = 0; i < 5; i++) {
                        Message incoming = consumer.receive(10_000L);
                        if (incoming == null) {
                            session.rollback();
                            throw new IllegalStateException(
                                    "Expected five messages");
                        }

                        try {
                            printBody(incoming);
                            session.commit(); // ACK lần nhận này.
                        } catch (Exception ex) {
                            session.rollback();
                            throw ex;
                        }
                    }
                } finally {
                    try {
                        producer.close();
                    } finally {
                        consumer.close();
                    }
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void printBody(Message m) throws Exception {
        if (m instanceof TextMessage) {
            String text = ((TextMessage) m).getText();
            System.out.println("TextMessage: " + text);

        } else if (m instanceof BytesMessage) {
            BytesMessage bytes = (BytesMessage) m;
            long length = bytes.getBodyLength();
            if (length > 1024 * 1024) {
                throw new IllegalArgumentException("Oversized bytes");
            }

            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] chunk = new byte[1024];
            int n;
            while ((n = bytes.readBytes(chunk)) != -1) {
                if (n <= 0) {
                    throw new IllegalStateException("No read progress");
                }
                out.write(chunk, 0, n);
            }
            System.out.println("BytesMessage: " +
                    Arrays.toString(out.toByteArray()));

        } else if (m instanceof MapMessage) {
            MapMessage map = (MapMessage) m;
            System.out.printf("MapMessage: %s %d%n",
                    map.getString("orderId"),
                    map.getLong("amountMinor"));

        } else if (m instanceof StreamMessage) {
            StreamMessage stream = (StreamMessage) m;
            System.out.printf("StreamMessage: %s %d %s%n",
                    stream.readString(),
                    stream.readLong(),
                    stream.readBoolean());

        } else if (m instanceof ObjectMessage) {
            Object value = ((ObjectMessage) m).getObject();
            if (!(value instanceof OrderSnapshot)) {
                throw new IllegalArgumentException("Unexpected class");
            }
            System.out.println("ObjectMessage: " + value);

        } else {
            throw new IllegalArgumentException(
                    "Unsupported JMS message type");
        }
    }
}
```

**Dòng xử lý chính:** gửi năm message khác body type tới cùng queue → commit producer transaction → nhận từng message → phân nhánh theo kiểu JMS thực tế → commit sau khi đọc thành công. Các lần `session.commit()` phía consumer ở đây chỉ minh họa xử lý JMS; nếu có database hoặc side effect thật, vẫn phải áp dụng idempotency/transaction design.

### 7.3. Điều quan sát được

Với broker thử nghiệm, không có consumer khác và các message có priority mặc định, kết quả đại ý:

```text
TextMessage: {"orderId":"O-100","amountMinor":129900}
BytesMessage: [1, 2, -1]
MapMessage: O-100 129900
StreamMessage: O-100 129900 true
ObjectMessage: O-100:129900
```

`-1` trong kết quả bytes là cách Java in **byte 0xFF có dấu**, không phải lỗi `readBytes()`. Các bài toán binary thường nên hiển thị hex hoặc Base64 cho người vận hành để tránh nhầm.

Không sử dụng việc **một producer đơn lẻ** quan sát thứ tự gửi làm bảo đảm thứ tự toàn cục cho toàn hệ thống với nhiều producer, consumer song song, priority và redelivery.

Nếu test ObjectMessage trên broker/client có policy chặn deserialization, đó là **chính sách bảo mật đang hoạt động**; không nên xử lý bằng cách tin cậy mọi package.

## 8. Schema evolution: cùng dữ liệu, độ linh hoạt khác nhau

Giả sử sự kiện phiên bản đầu có `orderId` và `amountMinor`; phiên bản tiếp theo thêm `currency`, sau đó thêm danh sách sản phẩm.

| Kiểu | Thêm `currency` | Thêm `items[]` | Chiến lược tương thích |
|---|---|---|---|
| TextMessage JSON | Thường thêm property trong object; consumer cũ có thể bỏ qua field | JSON array hỗ trợ tự nhiên | `schemaVersion`, optional/default, JSON Schema, contract tests |
| BytesMessage Protobuf | Thêm field với tag mới theo quy tắc Protobuf | Repeated field, nested messages | Giữ tag/kiểu ổn định, quản lý schema và generated code |
| MapMessage | Thêm key có tên mới | Không biểu diễn list object lồng nhau trực tiếp | Chỉ dùng record phẳng; định nghĩa getter type và default |
| StreamMessage | Append có thể khả thi nếu consumer cũ chỉ đọc prefix, nhưng cần thử | Phải tự đặt encoding và vị trí | Đặt version và parser theo thứ tự cụ thể |
| ObjectMessage | Thay lớp/serialVersionUID có thể gây lỗi version | Bị ràng buộc Java class graph | Tránh dùng làm contract công khai, lên kế hoạch chuyển format |

**Nguyên tắc:** chọn một **schema contract độc lập với việc broker dùng Classic hay Artemis**. Khi cần cross-language hoặc nhiều team cùng cập nhật, ưu tiên format rõ nghĩa, có version và kiểm thử compatibility giữa producer/consumer version.

### 8.1. Kế hoạch kiểm thử khi thay message type

Không nên đổi `MapMessage` sang `TextMessage` mà vẫn dùng chung tên destination rồi giả định consumer cũ hiểu được. Lộ trình an toàn hơn:

1. Định nghĩa schema mới, content type, version và chuyển đổi từ dữ liệu cũ.
2. Kiểm tra consumer cũ có thể nhận type mới không; thường **không** nếu đang cast cứng.
3. Nếu không tương thích, dùng destination/topic version mới hoặc adapter được kiểm thử.
4. Triển khai consumer mới trước, kiểm thử replay/rollback với từng loại bản tin.
5. Chuyển producer sau khi đã có khả năng đọc; quan sát message format errors và backlog.
6. Hạn chế trộn hai body type trên một queue khi downstream chưa có dispatcher phân biệt version/type.

## 9. Chọn nhanh theo tình huống thực tế

| Tình huống | Lựa chọn gợi ý | Vì sao |
|---|---|---|
| Java → Node.js/Python, cần JSON dễ debug | **TextMessage + JSON schema** | Dễ tích hợp, có field name, có thể version hóa |
| Payload binary compact, nhiều thông điệp/giây | **BytesMessage + Protobuf/Avro** | Format rõ ràng, payload compact; cần schema registry/version |
| Đơn hàng dạng record phẳng, JMS thuần Java | **MapMessage** | Getter có tên và kiểu, không cần parser JSON |
| Định dạng positional đã được cố định trong legacy | **StreamMessage** | Đọc tuần tự phù hợp với hợp đồng có thứ tự |
| Hệ thống Java cũ đã dùng Serializable DTO | **ObjectMessage**, giới hạn cho legacy | Phải kiểm soát deserialization, class version và quyền truy cập |
| File rất lớn hoặc object nhiều MB/GB | **Message tham chiếu tới object storage** | Giảm áp lực bộ nhớ, journal và băng thông broker |

Nếu phân vân giữa **MapMessage** và **TextMessage JSON** cho một hệ thống mới, tiêu chí quyết định là **có cần đọc từ công nghệ ngoài JMS, có dữ liệu lồng nhau và cần schema tooling hay không**. Nếu có, JSON hoặc binary schema thường là lựa chọn linh hoạt hơn.

## 10. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ClassCastException` khi nhận | Consumer giả định sai subtype `Message` | Kiểm tra `instanceof`/body type và thống nhất contract |
| `MessageFormatException` | `StreamMessage` đọc sai thứ tự, hoặc đọc sai kiểu theo JMS conversion | Kiểm tra field order, schema version và kiểu getter |
| `MessageEOFException` | Đọc vượt body của Bytes/Stream | Dùng framing rõ ràng, chặn đọc quá số trường |
| JSON parse lỗi | TextMessage chứa plain text hoặc schema khác | Kiểm tra `contentType` property, schemaVersion và payload mẫu |
| Selector không lọc theo trường body | Body không phải message property | Đặt property cần filter ngay khi publish |
| Đọc binary ra text bị lỗi ký tự | Producer/consumer không thống nhất charset/body section | Chốt binary format, UTF-8 policy hoặc Protobuf decoder |
| ObjectMessage bị từ chối | Package/class không được tin cậy hoặc class không tồn tại | Xem policy, allowlist chặt; không bật trust-all |
| Consumer cũ không hiểu field mới | Schema evolution sai hoặc đổi body type | Contract test, thêm version và xử lý fallback |
| Message quá lớn gây chậm/OOM | Cấp phát trọn payload, broker paging hoặc consumer parse quá tải | Đặt giới hạn message, streaming phù hợp hoặc pointer tới object storage |

### 10.1. Bảng kiểm thử đầu cuối tối thiểu

- **Kiểu chính xác:** gửi lần lượt cả năm subtype; receiver không cast sai.
- **Boundary:** text rỗng/null, `MapMessage` field thiếu, binary rỗng, StreamMessage thiếu field, ObjectMessage class thay đổi.
- **Dữ liệu quốc tế:** Unicode tiếng Việt trong Text/Map/Stream; xác nhận không mất ký tự.
- **Version:** producer v1/v2 tương tác với consumer v1/v2 theo ma trận compatibility.
- **Giới hạn tài nguyên:** message gần size limit, timeout parse, memory của consumer.
- **Interoperability:** JSON/Protobuf từ client ngoài Java nếu dự án yêu cầu; thử cả Artemis và Classic theo protocol thực tế.
- **Bảo mật:** dữ liệu nhạy cảm không in log nguyên payload; ObjectMessage không bypass deserialize allowlist.

## 11. Câu hỏi vận dụng

1. Vì sao gửi JSON trong `TextMessage` không khiến JMS selector lọc được `orderId` nằm trong JSON?
2. Hai BytesMessage cùng hiển thị text “xin chào” khi decode thủ công, nhưng một bên dùng `writeUTF`, bên kia `writeBytes(UTF_8)`. Format on-wire/body có tương đương không?
3. Một MapMessage có `amountMinor` kiểu `long` và consumer cũ đọc bằng `getString`. Rủi ro của ép kiểu ngầm là gì? Nên xác định contract ra sao?
4. Một StreamMessage v2 chèn một field mới trước `amountMinor`. Consumer v1 có thể gặp lỗi gì?
5. Vì sao `serialVersionUID=1L` không bảo đảm ObjectMessage được dùng an toàn và tương thích giữa hai ứng dụng Java?
6. Thiết kế một event `InventoryReserved` cần nhiều dòng item và được Python đọc: chọn loại JMS body nào, schema version và application properties gì?
7. Khi migration từ Classic sang Artemis, cần xác minh điều gì nếu consumer mới đọc message qua AMQP 1.0 thay vì OpenWire, đặc biệt với MapMessage và ObjectMessage?

## 12. Tài liệu tham khảo

- [Jakarta Messaging Specification](https://jakarta.ee/specifications/messaging/) — định nghĩa `Message` và các body subtype, mode đọc/ghi, chuyển đổi kiểu và acknowledgment API.
- [Apache ActiveMQ Classic — JMS](https://activemq.apache.org/components/classic/documentation/jms) — khả năng JMS của ActiveMQ Classic.
- [Apache ActiveMQ Artemis — Using JMS or Jakarta Messaging](https://artemis.apache.org/components/artemis/documentation/latest/using-jms.html) — client JMS/Jakarta và kết nối.
- [Apache ActiveMQ Classic — ObjectMessage security](https://activemq.apache.org/components/classic/documentation/objectmessage) — cơ chế trusted packages khi deserialize ObjectMessage.
- [Apache ActiveMQ Artemis — AMQP](https://artemis.apache.org/components/artemis/documentation/latest/amqp.html) — mapping/tích hợp khi client không chỉ nói Artemis Core.

**Ghi nhớ:** **TextMessage** phù hợp text/JSON có schema; **BytesMessage** thích hợp binary format đã định nghĩa rõ; **MapMessage** là record phẳng có tên trường; **StreamMessage** là dãy field theo thứ tự; **ObjectMessage** ràng buộc vào Java serialization và cần kiểm soát bảo mật nghiêm ngặt. Khi chọn kiểu body, ưu tiên **hợp đồng dữ liệu và khả năng nâng cấp** hơn sự tiện tay của API.
