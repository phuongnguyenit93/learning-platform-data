# TextMessage, BytesMessage, MapMessage, StreamMessage và ObjectMessage

Jakarta Messaging (JMS) định nghĩa nhiều kiểu message để biểu diễn phần body theo nhu cầu trao đổi. Năm kiểu thường gặp là **TextMessage**, **BytesMessage**, **MapMessage**, **StreamMessage** và **ObjectMessage**. Ngoài ra còn có kiểu **Message** cơ sở, thường dùng khi chỉ cần headers và properties mà không cần body ứng dụng.

Các kiểu này cùng kế thừa hợp đồng của **jakarta.jms.Message**. Chúng có chung phần metadata như message ID, correlation ID, destination, reply destination và application properties, nhưng khác nhau ở cách lưu và đọc body.

Chọn đúng kiểu message giúp producer và consumer thống nhất định dạng dữ liệu, tránh phụ thuộc không cần thiết vào Java serialization, đồng thời giảm lỗi khi các service được viết bằng ngôn ngữ hoặc phiên bản thư viện khác nhau.

## 1. Phần chung của một JMS Message

Một JMS message có thể được nhìn thành ba phần:

~~~text
JMS Message
   |
   +-- Headers
   |     JMSMessageID
   |     JMSTimestamp
   |     JMSCorrelationID
   |     JMSReplyTo
   |     JMSDestination
   |     JMSDeliveryMode / JMSPriority / JMSExpiration
   |
   +-- Properties
   |     eventType
   |     schemaVersion
   |     tenantId
   |     contentType
   |
   +-- Body
         TextMessage / BytesMessage /
         MapMessage / StreamMessage / ObjectMessage
~~~

**Headers** là metadata tiêu chuẩn của JMS. Một số trường do provider quản lý, ví dụ JMSMessageID và JMSTimestamp; một số trường có thể được producer đặt, ví dụ JMSCorrelationID, JMSReplyTo hoặc JMSType.

**Properties** là metadata do ứng dụng định nghĩa. Chúng phù hợp cho các giá trị ngắn như eventType, schemaVersion hoặc tenantId. Property phải thuộc các kiểu dữ liệu được JMS hỗ trợ; không thể tùy ý đặt một object Java bất kỳ vào property. Properties cũng có thể được dùng trong message selector để broker chọn message theo điều kiện.

**Body** chứa nội dung ứng dụng. Loại message quyết định API đọc/ghi body và các kiểu dữ liệu được phép.

Delivery mode, priority, expiration, redelivery và acknowledgment là các khía cạnh giao nhận. Chúng không phải loại body. Ví dụ, một TextMessage vẫn có thể được gửi ở chế độ persistent hoặc non-persistent tùy producer và provider.

### Message cơ sở không có body ứng dụng

Có thể tạo message không có body bằng phương thức createMessage() của Session. Kiểu này hữu ích cho tín hiệu điều khiển hoặc thông điệp chỉ cần metadata:

~~~java
Message heartbeat = session.createMessage();
heartbeat.setStringProperty("command", "PING");
heartbeat.setStringProperty("source", "inventory-service");
~~~

Consumer có thể đọc properties mà không cần giải mã body. Nếu cần dữ liệu nghiệp vụ như mã đơn hàng hoặc trạng thái, nên dùng một trong các kiểu body bên dưới.

## 2. TextMessage: body là chuỗi văn bản

**TextMessage** chứa một giá trị String. Đây là lựa chọn phổ biến khi payload là văn bản, JSON, XML, CSV hoặc một định dạng text khác.

### API chính

- **setText(String):** đặt nội dung text trước khi gửi.
- **getText():** đọc nội dung text ở phía consumer.

Ví dụ:

~~~java
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-1001\",\"status\":\"CREATED\"}"
);
message.setStringProperty("contentType", "application/json");
message.setStringProperty("schemaVersion", "1");
~~~

Consumer đọc:

~~~java
TextMessage received = (TextMessage) consumer.receive();
String json = received.getText();
~~~

TextMessage không tự xác thực JSON. Nó chỉ chứa chuỗi. Muốn biến chuỗi thành DTO, consumer cần JSON parser như Jackson, Gson hoặc JSON-B và cần thống nhất schema.

### Khi nào nên dùng?

- JSON hoặc XML trao đổi giữa nhiều service.
- Nội dung cần dễ quan sát khi debug.
- Các hệ thống có thể đọc text mà không phụ thuộc Java class.
- Payload nhỏ hoặc vừa, có cấu trúc văn bản rõ ràng.

### Lưu ý

TextMessage lưu nội dung dạng String; nó không đảm bảo nội dung là UTF-8 JSON hoặc bất kỳ schema cụ thể nào. Hãy quy định content type, charset nếu giao thức cần và phiên bản schema trong hợp đồng ứng dụng. Không nhầm việc tạo TextMessage với việc serialize object tự động.

## 3. BytesMessage: body là chuỗi byte

**BytesMessage** dùng cho dữ liệu nhị phân hoặc payload mà ứng dụng muốn tự kiểm soát cách serialize. Body được đọc/ghi theo thứ tự byte.

### API chính

- **writeBytes(byte[]):** ghi bytes vào body.
- **readBytes(byte[]):** đọc một phần bytes vào buffer; trả về số byte đã đọc, hoặc -1 khi hết dữ liệu.
- **getBodyLength():** lấy độ dài body theo byte.
- **reset():** chuyển body sang chế độ đọc và đưa vị trí đọc về đầu.

Ví dụ producer:

~~~java
byte[] payload = "{\"orderId\":\"ORD-1001\"}"
        .getBytes(StandardCharsets.UTF_8);

BytesMessage message = session.createBytesMessage();
message.writeBytes(payload);
message.setStringProperty("contentType", "application/json");
message.setStringProperty("charset", "UTF-8");
~~~

Consumer có thể đọc từng phần để không cần cấp phát một mảng lớn ngay từ đầu:

~~~java
BytesMessage received = (BytesMessage) consumer.receive();
received.reset();

ByteArrayOutputStream output = new ByteArrayOutputStream();
byte[] buffer = new byte[1024];
int count;

while ((count = received.readBytes(buffer)) != -1) {
    if (count > 0) {
        output.write(buffer, 0, count);
    }
}

byte[] payload = output.toByteArray();
String json = new String(payload, StandardCharsets.UTF_8);
~~~

### Khi nào nên dùng?

- File, ảnh, âm thanh hoặc dữ liệu nhị phân.
- Payload đã serialize thành Avro, Protobuf hoặc định dạng nhị phân riêng.
- Dữ liệu nén hoặc mã hóa.
- Khi producer và consumer muốn kiểm soát rõ byte layout.

### Lưu ý

BytesMessage không biết bytes biểu diễn loại dữ liệu nào. Producer và consumer phải thống nhất charset, content type, schema/version và cách giải mã. Nếu payload là JSON bytes, consumer vẫn cần parse JSON sau khi đọc bytes.

Với payload lớn, nên đọc theo buffer thay vì giả định toàn bộ body luôn vừa một mảng trong bộ nhớ. Cần kiểm tra giới hạn kích thước message của broker và ứng dụng.

## 4. MapMessage: body là tập trường có tên

**MapMessage** lưu dữ liệu dưới dạng các cặp tên/giá trị. Consumer truy cập theo tên trường, không cần đọc theo thứ tự ghi.

### API chính

- **setString(name, value), setInt(name, value), setBoolean(name, value)** và các setter kiểu tương ứng để ghi field.
- **getString(name), getInt(name), getBoolean(name)** để đọc field.
- **getMapNames():** liệt kê tên các field.
- **itemExists(name):** kiểm tra field có tồn tại không.
- **setObject(name, value):** đặt giá trị thuộc kiểu được JMS hỗ trợ.

Ví dụ:

~~~java
MapMessage message = session.createMapMessage();
message.setString("orderId", "ORD-1001");
message.setString("total", "125.50");
message.setBoolean("priority", true);
message.setInt("itemCount", 3);
~~~

Consumer:

~~~java
MapMessage received = (MapMessage) consumer.receive();

String orderId = received.getString("orderId");
String total = received.getString("total");
boolean priority = received.getBoolean("priority");
int itemCount = received.getInt("itemCount");
~~~

Dùng String cho số tiền trong ví dụ để giữ biểu diễn thập phân theo contract. Nếu dùng kiểu số dấu phẩy động, cần hiểu sai số và quy tắc chuyển đổi của kiểu đó.

### Kiểu dữ liệu được hỗ trợ

MapMessage không phải một Map Java tùy ý. Các giá trị phải thuộc tập kiểu JMS hỗ trợ, gồm các kiểu primitive tương ứng như boolean, byte, short, char, int, long, float, double, String và byte array. Các phép chuyển đổi kiểu khi đọc có giới hạn; dữ liệu không tương thích có thể gây MessageFormatException.

Không thể đưa tùy ý một DTO, collection lồng nhau hoặc object graph vào field của MapMessage như thể đó là một HashMap tổng quát.

### Khi nào nên dùng?

- Một message có số lượng field đơn giản và có tên rõ ràng.
- Consumer cần đọc một số field mà không phụ thuộc thứ tự.
- Tích hợp hệ thống cần một tập thuộc tính phẳng.
- Payload nhỏ và schema tương đối ổn định.

### Lưu ý

MapMessage không phù hợp với cấu trúc JSON lồng nhau hoặc schema phức tạp. Nếu cần object lồng nhau, mảng phức tạp hoặc versioning linh hoạt, JSON trong TextMessage hoặc một schema nhị phân trong BytesMessage thường phù hợp hơn.

## 5. StreamMessage: body là chuỗi giá trị có thứ tự

**StreamMessage** lưu một dãy giá trị được ghi và đọc theo thứ tự. Consumer phải đọc đúng thứ tự và dùng kiểu đọc tương ứng với dữ liệu đã ghi.

### API chính

- **writeString, writeInt, writeLong, writeBoolean** và các phương thức write kiểu tương ứng.
- **readString, readInt, readLong, readBoolean** để đọc tuần tự.
- **reset():** chuyển sang chế độ đọc và đưa vị trí đọc về đầu.
- **writeObject/readObject:** dùng với những kiểu được JMS cho phép trong stream.

Ví dụ producer:

~~~java
StreamMessage message = session.createStreamMessage();
message.writeString("ORD-1001");
message.writeLong(3L);
message.writeString("CREATED");
message.writeBoolean(true);
~~~

Consumer phải đọc đúng thứ tự và kiểu:

~~~java
StreamMessage received = (StreamMessage) consumer.receive();
received.reset();

String orderId = received.readString();
long revision = received.readLong();
String status = received.readString();
boolean priority = received.readBoolean();
~~~

Nếu consumer đọc sai thứ tự hoặc dùng kiểu không tương thích, JMS có thể ném MessageFormatException. Nếu đọc vượt quá phần tử cuối, API có thể ném MessageEOFException.

### Khi nào nên dùng?

- Một record tuần tự có schema đơn giản và cố định.
- Các trường được xử lý theo đúng thứ tự ghi.
- Giao thức nội bộ đã thống nhất thứ tự và kiểu dữ liệu.

### Lưu ý

StreamMessage không có tên field như MapMessage. Consumer phải biết trước vị trí và kiểu của từng giá trị. Thêm một trường vào giữa stream có thể làm consumer cũ đọc sai toàn bộ phần còn lại. Vì vậy, cần version schema rõ ràng và cân nhắc kỹ trước khi thay đổi thứ tự.

StreamMessage cũng không phải Java InputStream hoặc file stream. Nó là một kiểu JMS message có quy tắc đọc/ghi riêng.

## 6. ObjectMessage: body là một Java Serializable object

**ObjectMessage** chứa một object Java triển khai **java.io.Serializable**. Producer đặt object bằng setObject(); consumer lấy object bằng getObject().

Ví dụ:

~~~java
public record OrderSnapshot(
        String orderId,
        BigDecimal total,
        String status
) implements Serializable {
    private static final long serialVersionUID = 1L;
}

ObjectMessage message = session.createObjectMessage(
        new OrderSnapshot(
                "ORD-1001",
                new BigDecimal("125.50"),
                "CREATED"
        )
);
~~~

Consumer:

~~~java
ObjectMessage received = (ObjectMessage) consumer.receive();
OrderSnapshot snapshot = (OrderSnapshot) received.getObject();
~~~

### Ưu điểm

- Ít mã chuyển đổi khi hai phía đều là Java và dùng cùng contract class.
- Có thể truyền object graph Serializable mà không tự viết JSON mapping.
- Phù hợp với một số hệ thống Java nội bộ đã kiểm soát chặt class và phiên bản.

### Hạn chế và rủi ro

- Producer và consumer phụ thuộc vào class Java, package và khả năng tương thích serialization.
- Thay đổi class có thể gây lỗi tương thích giữa các phiên bản.
- Hệ thống viết bằng ngôn ngữ khác khó đọc Java serialization.
- Java native deserialization từ nguồn không tin cậy có thể tạo rủi ro bảo mật nghiêm trọng.

Không dùng ObjectMessage để nhận object tùy ý từ bên ngoài hoặc broker không tin cậy. Nếu buộc phải dùng, hãy giới hạn kiểu được phép deserialize bằng cơ chế filter/allowlist của runtime và provider, đồng thời kiểm soát nguồn gửi. Với tích hợp nhiều service hoặc nhiều ngôn ngữ, ưu tiên JSON, Avro hoặc Protobuf qua TextMessage/BytesMessage.

## 7. So sánh nhanh năm loại message

| Loại | Body | Cách truy cập | Điểm mạnh | Hạn chế chính |
|---|---|---|---|---|
| **TextMessage** | String | Đọc/ghi toàn bộ text | Dễ quan sát, phù hợp JSON/XML | Cần parser và schema riêng |
| **BytesMessage** | byte[] theo luồng | Đọc/ghi tuần tự bytes | Phù hợp binary, file, serialization | Consumer phải biết cách giải mã |
| **MapMessage** | Field có tên | Truy cập theo key | Không phụ thuộc thứ tự field | Chỉ hỗ trợ tập kiểu dữ liệu giới hạn, không phù hợp object lồng nhau |
| **StreamMessage** | Dãy giá trị có kiểu | Đọc/ghi theo thứ tự | Hợp với record tuần tự đơn giản | Phụ thuộc chặt thứ tự và kiểu |
| **ObjectMessage** | Serializable object | getObject/setObject | Thuận tiện giữa các ứng dụng Java | Phụ thuộc class và rủi ro native deserialization |

Một cách ghi nhớ:

- TextMessage: nội dung là text.
- BytesMessage: nội dung là bytes.
- MapMessage: nội dung là các trường có tên.
- StreamMessage: nội dung là các giá trị có thứ tự.
- ObjectMessage: nội dung là một Java object đã serialize.

## 8. Ví dụ tạo đủ các loại message bằng Jakarta Messaging

Ví dụ sau tạo một message cho mỗi kiểu. Đây là đoạn tích hợp biên dịch được với Jakarta Messaging API; phương thức nhận một Session đã được provider JMS tạo. Nó không tự khởi động broker hoặc tạo ConnectionFactory, vì những thành phần đó phụ thuộc provider triển khai trong môi trường thực tế.

### Maven dependency

~~~xml
<dependency>
    <groupId>jakarta.jms</groupId>
    <artifactId>jakarta.jms-api</artifactId>
    <version>3.1.0</version>
</dependency>
~~~

### Java source

Tạo file JmsMessageExamples.java:

~~~java
package com.example.messaging;

import java.io.Serializable;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import jakarta.jms.BytesMessage;
import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;
import jakarta.jms.Message;
import jakarta.jms.ObjectMessage;
import jakarta.jms.Session;
import jakarta.jms.StreamMessage;
import jakarta.jms.TextMessage;

public final class JmsMessageExamples {

    public record OrderSnapshot(
            String orderId,
            BigDecimal total,
            String status
    ) implements Serializable {
        private static final long serialVersionUID = 1L;
    }

    private JmsMessageExamples() {
    }

    public static List<Message> createExamples(Session session)
            throws JMSException {

        List<Message> messages = new ArrayList<>();

        TextMessage text = session.createTextMessage(
                "{\"orderId\":\"ORD-1001\",\"status\":\"CREATED\"}"
        );
        text.setStringProperty("contentType", "application/json");
        messages.add(text);

        BytesMessage bytes = session.createBytesMessage();
        bytes.writeBytes(
                "{\"orderId\":\"ORD-1002\"}".getBytes(StandardCharsets.UTF_8)
        );
        bytes.setStringProperty("contentType", "application/json");
        bytes.setStringProperty("charset", "UTF-8");
        messages.add(bytes);

        MapMessage map = session.createMapMessage();
        map.setString("orderId", "ORD-1003");
        map.setString("total", "125.50");
        map.setBoolean("priority", true);
        messages.add(map);

        StreamMessage stream = session.createStreamMessage();
        stream.writeString("ORD-1004");
        stream.writeLong(3L);
        stream.writeString("CREATED");
        messages.add(stream);

        ObjectMessage object = session.createObjectMessage(
                new OrderSnapshot(
                        "ORD-1005",
                        new BigDecimal("125.50"),
                        "CREATED"
                )
        );
        messages.add(object);

        Message control = session.createMessage();
        control.setStringProperty("command", "PING");
        messages.add(control);

        return List.copyOf(messages);
    }
}
~~~

Ứng dụng có thể gửi các message được tạo ra bằng một MessageProducer gắn với destination phù hợp:

~~~java
MessageProducer producer = session.createProducer(queue);
for (Message message : JmsMessageExamples.createExamples(session)) {
    producer.send(message);
}
producer.close();
~~~

Đoạn gửi trên giả định biến queue là Destination đã được cấu hình và session đang hoạt động. Trong ứng dụng thực tế, cần quản lý vòng đời Connection, Session và producer theo provider, transaction và mô hình concurrency của JMS.

### Đọc từng kiểu ở consumer

Sau khi nhận message, consumer kiểm tra kiểu cụ thể rồi gọi API tương ứng:

~~~java
Message message = consumer.receive();

if (message instanceof TextMessage text) {
    String body = text.getText();
    System.out.println("text=" + body);
}
else if (message instanceof BytesMessage bytes) {
    bytes.reset();
    System.out.println("bytesLength=" + bytes.getBodyLength());
}
else if (message instanceof MapMessage map) {
    System.out.println("orderId=" + map.getString("orderId"));
}
else if (message instanceof StreamMessage stream) {
    stream.reset();
    String orderId = stream.readString();
    long revision = stream.readLong();
    String status = stream.readString();
    System.out.println(orderId + ":" + revision + ":" + status);
}
else if (message instanceof ObjectMessage object) {
    OrderSnapshot snapshot = (OrderSnapshot) object.getObject();
    System.out.println("object=" + snapshot.orderId());
}
else {
    System.out.println("control=" + message.getStringProperty("command"));
}
~~~

Đoạn consumer minh họa cách phân nhánh theo loại body; nó cần một MessageConsumer và message đã nhận từ provider. Với BytesMessage, ví dụ chỉ in độ dài; ứng dụng đọc bytes thực tế bằng readBytes theo buffer như phần trước.

## 9. Spring JMS và SimpleMessageConverter

Nếu ứng dụng dùng Spring JMS, **org.springframework.jms.support.converter.MessageConverter** là abstraction chuyển đổi giữa object ứng dụng và **jakarta.jms.Message**. Đây là converter thuộc Spring JMS, khác với **org.springframework.messaging.converter.MessageConverter** của Spring Messaging.

Spring JMS cung cấp **SimpleMessageConverter** với các ánh xạ thông dụng:

| Object phía ứng dụng | JMS message được tạo |
|---|---|
| String | TextMessage |
| byte[] | BytesMessage |
| Map | MapMessage |
| Serializable object | ObjectMessage |

Ví dụ gửi qua JmsTemplate:

~~~java
jmsTemplate.convertAndSend("orders.queue", "Order ORD-1001 created");
jmsTemplate.convertAndSend("orders.queue", payloadBytes);
jmsTemplate.convertAndSend("orders.queue", Map.of(
        "orderId", "ORD-1001",
        "status", "CREATED"
));
~~~

Các lời gọi này phụ thuộc converter đang được cấu hình cho JmsTemplate. Với converter mặc định, object Serializable có thể được chuyển thành ObjectMessage; Map được chuyển thành MapMessage nhưng giá trị trong Map phải phù hợp với các kiểu JMS hỗ trợ.

### Khi cần JSON DTO

Không nên gửi DTO Serializable bằng SimpleMessageConverter rồi mặc định rằng nó sẽ thành JSON. Nếu contract cần JSON, hãy cấu hình một JSON-based JMS MessageConverter, ví dụ converter Jackson của Spring JMS, để tạo TextMessage hoặc BytesMessage theo lựa chọn.

JSON giúp producer và consumer ít phụ thuộc vào class Java cụ thể hơn. Dù vậy, vẫn cần thống nhất content type, schema version, naming strategy, date/time format và chính sách tương thích.

### StreamMessage không phải ánh xạ mặc định của SimpleMessageConverter

SimpleMessageConverter không tự động chọn StreamMessage cho một List hoặc một sequence bất kỳ. Nếu ứng dụng cần StreamMessage, hãy tạo message qua Session hoặc viết converter chuyên biệt để xác định rõ thứ tự và kiểu dữ liệu.

## 10. Vòng đời body: read-only, write-only và reset

Các JMS message thường có quy tắc trạng thái body:

- Trước khi gửi, producer ghi body qua các setter hoặc writer tương ứng.
- Sau khi gửi, body message chuyển sang chế độ chỉ đọc.
- Consumer đọc body qua các getter hoặc reader.
- **clearBody()** xóa body và đưa message về chế độ có thể ghi lại; thao tác này không xóa JMS headers hoặc properties.

BytesMessage và StreamMessage còn có con trỏ đọc/ghi. Gọi **reset()** chuyển body sang chế độ đọc và đưa con trỏ về đầu. Đừng nhầm reset với clearBody: reset để đọc lại body, còn clearBody xóa body để ghi mới.

MapMessage cho phép truy cập field theo tên, còn TextMessage và ObjectMessage đọc body qua phương thức tương ứng. Hành vi cụ thể cần theo trạng thái message và API JMS.

## 11. Message selectors và properties

Broker có thể dùng message selector để lọc message dựa trên headers và properties. Selector không truy vấn tùy ý các field bên trong TextMessage JSON, BytesMessage hoặc ObjectMessage.

Ví dụ producer đặt property:

~~~java
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
~~~

Consumer có thể tạo selector:

~~~java
MessageConsumer consumer = session.createConsumer(
        queue,
        "eventType = 'OrderCreated' AND schemaVersion >= 2"
);
~~~

Nếu broker cần lọc theo eventType, hãy đưa eventType vào property thay vì chỉ đặt bên trong JSON body. Properties nên là metadata ngắn, có kiểu dữ liệu được JMS hỗ trợ; không sao chép toàn bộ payload vào properties.

## 12. Chọn loại message theo bài toán

| Nhu cầu | Loại nên cân nhắc | Lý do |
|---|---|---|
| JSON, XML, CSV hoặc text | TextMessage | Dễ đọc và tương thích nhiều ngôn ngữ. |
| Ảnh, file, dữ liệu nhị phân hoặc Protobuf | BytesMessage | Body là bytes, phù hợp serialization riêng. |
| Một tập field đơn giản, có tên | MapMessage | Consumer đọc field theo key, không phụ thuộc thứ tự. |
| Một record tuần tự có schema cố định | StreamMessage | Đọc/ghi theo thứ tự và kiểu đã thống nhất. |
| Object Java nội bộ, hai phía kiểm soát chặt class | ObjectMessage | Ít mã chuyển đổi, nhưng phụ thuộc Java serialization. |
| Chỉ cần tín hiệu hoặc metadata điều khiển | Message | Không cần body ứng dụng. |

Với hệ thống phân tán hoặc nhiều ngôn ngữ, lựa chọn phổ biến thường là TextMessage chứa JSON hoặc BytesMessage chứa định dạng nhị phân có schema. ObjectMessage chỉ phù hợp khi phạm vi tin cậy, class compatibility và cách deserialize được kiểm soát chặt.

## 13. Những lỗi thường gặp

1. **Dùng TextMessage rồi cho rằng JMS tự parse JSON.** TextMessage chỉ trả về String; consumer phải dùng JSON parser.
2. **Dùng BytesMessage nhưng không ghi charset hoặc schema.** Consumer không biết bytes cần giải mã theo cách nào.
3. **Đặt object tùy ý vào MapMessage.** MapMessage chỉ hỗ trợ tập kiểu JMS quy định, không phải Map Java tổng quát.
4. **Đọc StreamMessage sai thứ tự.** Consumer phải đọc đúng trình tự và kiểu mà producer đã ghi.
5. **Thêm field giữa StreamMessage mà không version schema.** Consumer cũ có thể diễn giải sai những field tiếp theo.
6. **Dùng ObjectMessage cho dữ liệu từ nguồn không tin cậy.** Java native deserialization có thể tạo rủi ro bảo mật; ưu tiên JSON hoặc định dạng có schema.
7. **Cho rằng SimpleMessageConverter luôn tạo JSON.** Converter mặc định ánh xạ String, byte[], Map và Serializable sang các JMS message tương ứng; DTO Serializable có thể thành ObjectMessage.
8. **Nhầm body với JMS properties.** Selector thường lọc theo headers/properties, không parse nội dung body.
9. **Nhầm reset với clearBody.** reset đưa BytesMessage/StreamMessage về đầu để đọc; clearBody xóa body và cho phép ghi lại.
10. **Trộn javax.jms và jakarta.jms.** Spring Framework 5.x dùng namespace javax.jms; Spring Framework 6.x chuyển sang jakarta.jms. API và provider phải tương thích cùng namespace.
11. **Quên body có trạng thái chỉ đọc sau send.** Muốn thay đổi body, phải tạo message mới hoặc clearBody theo đúng vòng đời.
12. **Cho rằng loại message quyết định delivery guarantee.** Persistent delivery, acknowledgment, transaction, redelivery và expiration là các thuộc tính giao nhận riêng.

## 14. Ghi nhớ

- **TextMessage** chứa String, phù hợp JSON/XML và dữ liệu văn bản.
- **BytesMessage** chứa bytes, phù hợp file, binary và serialization do ứng dụng kiểm soát.
- **MapMessage** chứa các field có tên với kiểu dữ liệu giới hạn của JMS.
- **StreamMessage** chứa các giá trị có kiểu theo thứ tự; producer và consumer phải thống nhất thứ tự.
- **ObjectMessage** chứa Serializable object; tránh dùng với nguồn không tin cậy và hệ thống cần tương thích đa ngôn ngữ.
- **Message** cơ sở không có body ứng dụng, nhưng vẫn mang headers và properties.
- Spring JMS SimpleMessageConverter ánh xạ String, byte[], Map và Serializable sang các loại JMS tương ứng; JSON DTO cần converter JSON được cấu hình.
- Chọn message type theo contract, tính tương thích, kích thước payload, bảo mật và cách consumer xử lý dữ liệu.

Khi thiết kế một luồng JMS, hãy xác định body format trước, thống nhất schema và metadata với consumer, rồi mới chọn message type. Một hợp đồng rõ ràng giúp giảm phụ thuộc giữa producer, broker và consumer khi hệ thống được nâng cấp.
