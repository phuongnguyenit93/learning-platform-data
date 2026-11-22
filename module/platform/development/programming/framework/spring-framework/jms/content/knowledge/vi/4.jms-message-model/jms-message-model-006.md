# ObjectMessage và sự phụ thuộc vào tuần tự hóa Java

> **Mục tiêu:** Hiểu `jakarta.jms.ObjectMessage` truyền gì qua broker, vì sao payload phụ thuộc vào Java Serialization và class của producer/consumer, cách Spring JMS tự chọn `ObjectMessage` khi gặp `Serializable`, rủi ro tương thích và bảo mật, cùng cách thiết kế định dạng message ổn định hơn cho hệ thống tích hợp.

## 1. ObjectMessage là gì?

**`ObjectMessage` là một loại `Message` của JMS/Jakarta Messaging có phần body chứa một đối tượng Java triển khai `java.io.Serializable`.** API được định nghĩa trong `jakarta.jms.ObjectMessage` (Spring Framework 6+ dùng `jakarta.jms`; tài liệu Spring 5/JMS cũ có thể dùng `javax.jms`).

Các API trọng tâm:

~~~java
// Mảnh mã API Jakarta Messaging, cần một jakarta.jms.Session hợp lệ.
ObjectMessage message = session.createObjectMessage();
message.setObject(aSerializableObject);
Serializable body = message.getObject();

// Cách tạo ngắn hơn:
ObjectMessage other = session.createObjectMessage(aSerializableObject);
~~~

Hai dòng `setObject` / `getObject` lần lượt ghi và lấy Java object. Biến `aSerializableObject` phải được khai báo/tạo trong ứng dụng; đoạn trên là minh họa API, **không phải chương trình Java độc lập**.

Điều cần nắm:

- Đây là **JMS message body type**, không phải một định dạng dữ liệu độc lập với ngôn ngữ.
- `setObject(Serializable)` nhận **một object**; object đó có thể chứa cả đồ thị tham chiếu (nested objects, collections) nếu có khả năng tuần tự hóa phù hợp.
- JMS headers (`JMSMessageID`, `JMSCorrelationID`, `JMSRedelivered`...) và message properties tồn tại **ngoài body**; `ObjectMessage` không biến header thành field của Java object.
- `setObject` lưu **snapshot** của trạng thái object tại thời điểm gọi; sửa object gốc sau đó không làm body message đổi theo. Provider có thể có cơ chế lưu trữ/transfer riêng nhưng phải đáp ứng hợp đồng này.
- `getObject()` trả về `Serializable`; caller có thể ép kiểu, hoặc dùng `message.getBody(ExpectedType.class)` khi phù hợp. Cả hai đều có bước khôi phục Java object và không giải quyết rủi ro của deserialization.
- Body nhận về ở chế độ read-only; gọi lại `setObject` trên message đã nhận có thể gây `MessageNotWriteableException` trừ khi `clearBody` được gọi theo API.

**Phân biệt với các loại body khác:**

| Loại JMS message | Body | Độ phụ thuộc vào Java class |
| --- | --- | --- |
| `TextMessage` | Một chuỗi văn bản (thường JSON/XML) | Thấp nếu dùng schema độc lập ngôn ngữ |
| `BytesMessage` | Các byte theo định dạng đã thỏa thuận (ví dụ Protobuf/Avro) | Phụ thuộc vào codec/schema, không bắt buộc Java Serialization |
| `MapMessage` | Các trường name/value thuộc kiểu JMS cho phép | Phụ thuộc schema field; không phải một object graph bất kỳ |
| `StreamMessage` | Dòng các giá trị kiểu JMS hỗ trợ | Cần biết chính xác thứ tự/kiểu trường |
| **`ObjectMessage`** | `Serializable` Java object | **Cao**: class, package, serial form, classloader và Java runtime |

Không phải payload nào có dạng “đối tượng nghiệp vụ” cũng cần `ObjectMessage`. Có thể gửi **dữ liệu của object** dưới dạng JSON trong `TextMessage` hoặc schema binary trong `BytesMessage`.

## 2. Điều gì thực sự xảy ra trong Java Serialization?

Một Java object trong bộ nhớ có tham chiếu, fields và type runtime. Broker không chia sẻ vùng heap với producer/consumer. Khi truyền `ObjectMessage`, provider xử lý biểu diễn đối tượng thích hợp cho lưu trữ/truyền tải; ở phía nhận, Java object phải được khôi phục theo các quy tắc tương thích Java Serialization.

~~~text
Producer JVM (class com.acme.events.InvoiceCreated)
    |
    | session.createObjectMessage(payload)
    | hoặc JmsTemplate.convertAndSend(payload)
    v
ObjectMessage: body là snapshot của Serializable object
    |
    | JMS provider/client mã hóa và chuyển qua broker
    v
Broker: lưu/định tuyến message theo semantics và cấu hình
    |
    v
Consumer JMS client / Java classloader
    |
    | deserialize: cần class tương thích + graph được phép khôi phục
    v
InvoiceCreated object trong consumer JVM
    |
    v
Business handler kiểm tra ID, schema và xử lý
~~~

**`Serializable` là marker interface**, không có method mà class buộc phải triển khai. Java serialization có quy tắc riêng về instance fields, đối tượng lồng nhau, class hierarchy, `serialVersionUID`, `writeObject`/`readObject`, `Externalizable` hoặc serialization proxy. Đối tượng triển khai `Serializable` nhưng chứa field tham chiếu đến một object không serializable vẫn có thể thất bại khi serialize.

Ví dụ:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class InvoiceEvent implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String invoiceId;
    private final long totalMinor;

    public InvoiceEvent(String invoiceId, long totalMinor) {
        this.invoiceId = invoiceId;
        this.totalMinor = totalMinor;
    }

    public String invoiceId() {
        return invoiceId;
    }

    public long totalMinor() {
        return totalMinor;
    }
}
~~~

Đây là **class Java 17+ độc lập hợp lệ** được lưu ở `InvoiceEvent.java`. `String` serializable, `long` là primitive nên payload đơn giản này có thể được Java Serialization mã hóa. Việc đánh dấu `implements Serializable` **không** tự tạo JSON và **không** xác định một schema version dùng chung cho các ngôn ngữ khác.

### 2.1. Những thành phần nào được lưu?

- Instance fields có thể được serialize theo quy tắc của lớp; fields `static` không phải trạng thái instance trong serialized stream.
- Field `transient` thường không được lưu theo cơ chế mặc định; sau deserialize nó có giá trị mặc định trừ khi code/phương thức đặc biệt khôi phục. `transient` không phải biện pháp bảo mật duy nhất; secret vẫn có thể lộ qua field khác hoặc logic tùy biến.
- Object graph gồm các field tham chiếu phải đáp ứng yêu cầu serialization hoặc được xử lý bằng custom serialization. `implements Serializable` chỉ ở lớp ngoài không bảo đảm mọi nested field hợp lệ.
- Serialization có thể giữ cấu trúc tham chiếu/chia sẻ tham chiếu trong một object graph; **không** bảo đảm object nhận và object gửi là cùng instance trong hai JVM.
- Đối tượng được khôi phục cần đúng class; với class thông thường, việc gọi constructor trong deserialize không giống cách `new` tạo mọi object. Đừng dựa vào constructor/setter business validation luôn chạy khi nhận Java serialization.
- Collections, enums, records và một số JDK class có quy tắc riêng. Record trong Java hiện đại hỗ trợ `Serializable` nhưng có cơ chế khôi phục/phiên bản khác class thông thường; không áp dụng máy móc mọi mẹo `serialVersionUID` của class thường lên record.

### 2.2. Snapshot không phải live object

~~~java
// Minh họa với class MutablePayload implements Serializable
MutablePayload data = new MutablePayload("draft");
ObjectMessage message = session.createObjectMessage(data);
data.setStatus("approved");

// message vẫn phản ánh trạng thái "draft" tại thời điểm set/createObjectMessage.
// Không dựa vào việc thay đổi biến data sau đó để cập nhật message đã tạo.
~~~

Đây là mảnh minh họa, cần định nghĩa `MutablePayload` và `Session`. Sự kiện đã gửi nên được coi là **dữ liệu bất biến có ý nghĩa tại thời điểm phát hành**, không phải con trỏ tới aggregate còn thay đổi.

## 3. Ví dụ chạy được chỉ với Java 17: serialization và lỗi nested field

Ví dụ thuần JDK giúp quan sát **phần phụ thuộc cốt lõi** mà không cần broker hay Spring. Nó dùng `ObjectOutputStream` / `ObjectInputStream` trên byte array của một **đối tượng được tạo tại chỗ và tin cậy**. Đoạn này không nhận dữ liệu từ mạng hoặc đầu vào bên ngoài.

Tạo file `SerializationProbe.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.NotSerializableException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public final class SerializationProbe {

    public static void main(String[] args) throws Exception {
        InvoiceDraft original = new InvoiceDraft("INV-7", 5500);

        byte[] encoded;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            out.flush();
            encoded = buffer.toByteArray();
        }

        InvoiceDraft restored;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(encoded))) {
            restored = (InvoiceDraft) in.readObject();
        }

        System.out.println("same reference: " + (original == restored));
        System.out.println("restored: " + restored);

        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(new BadPayload());
        } catch (NotSerializableException e) {
            System.out.println("nested field failure: "
                    + e.getClass().getSimpleName());
        }
    }

    static final class InvoiceDraft implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String invoiceId;
        private final int amountMinor;

        InvoiceDraft(String invoiceId, int amountMinor) {
            this.invoiceId = invoiceId;
            this.amountMinor = amountMinor;
        }

        @Override
        public String toString() {
            return "InvoiceDraft(" + invoiceId + "," + amountMinor + ")";
        }
    }

    static final class BadPayload implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final Object unconvertible = new Object();
    }
}
~~~

Chạy trong thư mục chứa file:

~~~bash
javac SerializationProbe.java
java SerializationProbe
~~~

`javac` và `java` phải dùng JDK 17+; ví dụ không cần thư viện ngoài. **Stdout dự kiến chính xác:**

~~~text
same reference: false
restored: InvoiceDraft(INV-7,5500)
nested field failure: NotSerializableException
~~~

Bài học: object sau deserialize có **danh tính mới**; `BadPayload` đã đánh dấu `Serializable` nhưng trường `new Object()` của nó không serializable, nên `ObjectOutputStream` ném `NotSerializableException`. Trong JMS, lỗi bên dưới có thể được provider gói thành `MessageFormatException` / `JMSException`, sau đó Spring gói thành lỗi của lớp chuyển đổi hoặc `JmsException`; **đừng viết code dựa vào một chuỗi exception cố định xuyên mọi provider**.

## 4. Vì sao ObjectMessage tạo coupling mạnh giữa các service?

Đối với JSON message, consumer thường chỉ cần hiểu **schema dữ liệu**. Với Java-serialized object, consumer thường cần cả **định nghĩa class Java tương thích** với class được serialize:

1. **Tên class đầy đủ (package + tên) và classloader:** producer serialize `com.example.billing.InvoiceEvent`; consumer chưa có class đó hoặc đổi tên thành `com.example.contract.InvoiceEvent` thì việc deserialize có thể gặp `ClassNotFoundException`.
2. **`serialVersionUID`:** nhiều class serializable thông thường chứa số định danh serialized form. Nếu bên nhận và stream có UID không khớp, Java thường ném `InvalidClassException`.
3. **Fields và kiểu fields:** đổi tên, đổi kiểu, thêm/xóa field có quy tắc tương thích; một số thay đổi được phép nhưng dữ liệu cũ có thể nhận default value, gây sai business semantics.
4. **Nested class dependencies:** payload chứa `Money`, `Customer`, `Address`... khiến consumer cần biết cả graph, thậm chí thư viện dependency tương ứng.
5. **Custom serialization hooks:** `writeObject`, `readObject`, `writeReplace`, `readResolve` hoặc `Externalizable` có thể làm serialized form phụ thuộc code triển khai cụ thể.
6. **Thời gian lưu message:** bản ghi vẫn còn trên broker sau deploy; consumer mới phải đọc được object do phiên bản producer cũ phát.
7. **Giới hạn ngôn ngữ:** Python, Go, JavaScript không có hợp đồng Java Serialization tương đương chỉ nhờ được kết nối cùng broker.

**Một lớp Java có cùng tên không đồng nghĩa mọi phiên bản của lớp tương thích.** `serialVersionUID` giữ nguyên chỉ vượt qua một phần kiểm tra phiên bản; vẫn có thể không tương thích cấu trúc, thiếu dependency hoặc sai logic. Đổi `serialVersionUID` một cách tùy tiện để “sửa lỗi” còn có thể chặn hoàn toàn backlog cũ.

### 4.1. Nâng version và hàng đợi còn thông điệp cũ

Giả sử hôm qua producer phát:

~~~text
com.shop.events.InvoiceReady
serialVersionUID = 1L
fields: invoiceId:String, amountMinor:long
~~~

Hôm nay consumer triển khai class mới, thay đổi kiểu `amountMinor` thành `BigDecimal` hoặc đổi class sang package mới. Message trong queue chưa xử lý vẫn mang serialized form cũ. Khi client nhận, việc khôi phục có thể lỗi **trước khi business handler được gọi**.

Hậu quả dễ gặp: một message poison bị redeliver nhiều lần rồi vào DLQ; producer mới gửi thành công nhưng consumer không thể đọc backlog; test chỉ chạy với producer/consumer cùng build không phát hiện vấn đề.

Chiến lược an toàn hơn nếu buộc phải dùng `ObjectMessage`:
- Dùng DTO truyền tin riêng, ít fields, không đưa entity ORM/proxy, bean Spring, socket, connection hay domain aggregate đầy dependency vào payload.
- Giữ bộ thư viện contract dùng chung được version hóa và kiểm tra producer–consumer cross-version.
- Khai báo `serialVersionUID` ổn định khi serialized form tương thích **thực sự**; lưu ý quy tắc đặc biệt của record.
- Thử nghiệm **consumer mới nhận message do producer cũ serialize** và chiều ngược lại nếu có rolling deployment.
- Xác định lifecycle của backlog, TTL, DLQ và thời điểm được phép loại bỏ class cũ.

### 4.2. So sánh tính tương thích với JSON

| Nhu cầu | ObjectMessage | JSON trong TextMessage |
| --- | --- | --- |
| Bên nhận không dùng Java | Khó vì phải hiểu serialized Java object | Dễ hơn vì định dạng độc lập ngôn ngữ |
| Thay đổi package/class Java | Có thể làm deserialize không được | Có thể giữ schema JSON không đổi |
| Thêm trường tùy chọn | Phụ thuộc Java serialization compatibility và code | Thường có thể giữ backward compatibility nếu schema và consumer xử lý field thiếu |
| Debug message trong broker | Binary Java stream khó đọc và cần class | Dễ xem payload text bằng công cụ đã cấp quyền |
| An toàn khi nhận payload độc hại | Có rủi ro deserialization gadget/chạy code từ classpath | Không dùng Java native deserialization; vẫn phải xác thực, giới hạn schema/size và cấu hình JSON parser an toàn |
| Typed Java DTO trong ứng dụng | Nhận trực tiếp nếu đã deserialized | Deserialize JSON có kiểm soát sang DTO cụ thể |
| Quản lý contract dài hạn | Coupling Java implementation | Khuyến khích schema độc lập ngôn ngữ với versioning |

JSON không tự bảo đảm backward compatibility: vẫn cần hợp đồng về kiểu dữ liệu, optional/required fields, thời gian, số tiền, enum, xử lý unknown fields, schema version và kiểm thử.

## 5. Bảo mật: deserialization là ranh giới tin cậy

**Không deserialize `ObjectMessage` từ nguồn không tin cậy.** Java native deserialization có thể gọi logic của class khi tái tạo object graph. Khi có gadget classes thích hợp trên classpath, payload độc hại có thể gây hậu quả nghiêm trọng; ngay cả dữ liệu không độc hại cũng có thể tiêu tốn tài nguyên qua graph quá lớn hoặc lồng sâu.

Đặc biệt nguy hiểm nếu:
- Broker/queue cho nhiều client mà bạn không kiểm soát được publish.
- Producer và consumer có version classpath lệch nhau.
- Dữ liệu lưu lâu trên DLQ rồi được replay mà không kiểm soát nguồn gốc.
- Handler nhận `Object` tùy ý và dùng cast/reflection sau khi deserialization đã diễn ra.
- Cấu hình “tin cậy mọi package” để vượt lỗi không tương thích.

**`instanceof` sau `getObject()` không ngăn deserialization nguy hiểm**: class đã được khôi phục trước khi bạn kiểm tra kiểu.

Cần nhiều lớp bảo vệ:

1. **Giảm attack surface:** ưu tiên `TextMessage`/`BytesMessage` với codec/schema phù hợp; không phụ thuộc Java object deserialization khi tích hợp liên dịch vụ.
2. **ACL broker:** chỉ cho phép producer đã xác thực gửi tới destination; hạn chế quyền publish/consume, bật TLS và tách môi trường.
3. **Class/package allowlist của JMS provider:** kiểm tra cấu hình đặc thù của provider, áp dụng danh sách class/package thực sự được phép và kiểm thử nested object graph.
4. **Serialization filters của JVM (JEP 290, `ObjectInputFilter`)** nếu phần deserialization tương ứng sử dụng stream/filter do bạn kiểm soát; **không mặc định** một cấu hình filter trong app sẽ bao phủ mọi provider/client library.
5. **Resource limits:** hạn chế độ lớn message, độ sâu object graph, số tham chiếu, backlog và số lần retry; cảnh báo khi deserialize lỗi.
6. **Cập nhật phụ thuộc:** loại bỏ gadget libraries không cần thiết; cập nhật broker/client/JDK và kiểm thử chính sách deserialization khi nâng cấp.
7. **Quy trình DLQ/replay:** không khôi phục mọi payload thô vào app bằng Java deserialization chỉ để hiển thị/quan sát; cần công cụ kiểm tra an toàn, metadata và quyền truy cập.

### 5.1. Khác nhau giữa ActiveMQ Artemis và ActiveMQ Classic

Đây là **cấu hình của sản phẩm**, không phải setting chung của JMS:

- **Apache ActiveMQ Artemis** có allowlist/denylist cho `ObjectMessage` deserialization, ví dụ system properties `org.apache.activemq.artemis.jms.deserialization.allowlist` và `org.apache.activemq.artemis.jms.deserialization.denylist`; cấu hình ở `ConnectionFactory` có thể ghi đè các system properties. Kiểm tra phiên bản client/broker thực tế và các class lồng nhau cần cho application.
- **ActiveMQ Classic** có chính sách trusted packages khác, tiêu biểu `org.apache.activemq.SERIALIZABLE_PACKAGES`. **Không sao chép property của Classic cho Artemis** rồi mặc định cho rằng nó có hiệu lực.

Ví dụ minh họa property name Artemis (chưa phải cấu hình production hoàn chỉnh):

~~~properties
org.apache.activemq.artemis.jms.deserialization.allowlist=com.example.contract
~~~

Không áp dụng máy móc: nếu object graph chứa class hợp lệ nằm ở package khác, nó cũng có thể bị từ chối. Trong production, quản lý chính sách theo phiên bản client, thử deserialize bộ payload hợp lệ và thử payload không nằm allowlist. Nếu không còn bắt buộc dùng Java serialization, **di chuyển sang TextMessage/BytesMessage** là hướng thiết kế đơn giản hơn.

## 6. Spring JMS tương tác với ObjectMessage như thế nào?

Spring Framework cung cấp `JmsTemplate` và `@JmsListener` trên API Jakarta Messaging. **Lớp chuyển đổi `MessageConverter` quyết định object nghiệp vụ được đưa vào JMS message type nào**, không phải việc method tên là `send` hay `convertAndSend`.

Trong Spring 6.x, `SimpleMessageConverter` mặc định chuyển:

| Java value đưa vào `convertAndSend` | JMS body type |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` với kiểu field hỗ trợ | `MapMessage` |
| Object `Serializable` khác (ví dụ `InvoiceEvent`) | **`ObjectMessage`** |
| Loại object không hỗ trợ | Có thể ném `MessageConversionException` |

Khi nhận, converter này cũng làm chiều ngược lại; với `ObjectMessage` nó gọi cơ chế lấy/deserializing object. **Điểm bất ngờ:** sửa mã từ `jmsTemplate.send(...)` sang `jmsTemplate.convertAndSend("orders", invoiceEvent)` có thể khiến hệ thống tự dùng Java serialization nếu converter đang là `SimpleMessageConverter`.

~~~java
// Mảnh mã nằm trong Spring-managed service có JmsTemplate template
InvoiceEvent event = new InvoiceEvent("INV-7", 5500);

// Cách 1: converter mặc định có thể tạo ObjectMessage vì InvoiceEvent Serializable.
template.convertAndSend("invoices.object", event);

// Cách 2: yêu cầu ObjectMessage tường minh, không cần dự đoán converter.
template.send("invoices.object",
        session -> session.createObjectMessage(event));
~~~

Hai cách trên là **hai lựa chọn**, không nên chạy liên tiếp nếu bạn chỉ muốn phát một event. Với `JmsTemplate.send` callback, việc tạo message do bạn kiểm soát; với `convertAndSend`, hãy luôn kiểm tra converter thực sự đang gắn vào template.

### 6.1. Khôi phục xảy ra ở tầng nào?

Listener dạng:

~~~java
@JmsListener(destination = "invoices.object")
public void handle(InvoiceEvent event) {
    System.out.println("Received invoice: " + event.invoiceId());
}
~~~

là mảnh phương thức trong một Spring bean. Khi sử dụng conversion tương ứng, container/adapter có thể khôi phục ObjectMessage thành `InvoiceEvent` **trước khi gọi `handle`**. Vì vậy, một lỗi `ClassNotFoundException`, UID hoặc allowlist có thể làm method **không chạy lần nào**; try/catch bên trong handler không giải quyết được lỗi deserialize ở tầng trước. Quan sát error handler, transaction/ack và broker redelivery/DLQ.

Sự khác biệt này không phụ thuộc mạnh vào cách bạn lấy `JMSContext` hay `Session`: nếu body vẫn là native Java serialized object, rủi ro vẫn tồn tại.

## 7. Lab Spring Boot 3.x, Java 17+: ObjectMessage end-to-end

Đây là lab **trong môi trường tin cậy** nhằm chỉ ra Spring JMS thực tế truyền Java-serialized object. Dùng Java 17+, **Spring Boot 3.x / Spring Framework 6.x** có `jakarta.jms`, Maven, và Artemis embedded. Trong production hãy dùng broker ngoài, ACL và định dạng message được version hóa.

### 7.1. Khởi tạo dependencies

Với Spring Initializr (https://start.spring.io/), tạo Maven project:

- Group: `com.example`
- Artifact: `objectmessagelab`
- Package: `com.example.objectmessagelab`
- Java: `17` hoặc mới hơn được phiên bản Boot chọn hỗ trợ
- Dependency: **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`)

Thêm dependency broker embedded vào phần `<dependencies>` của `pom.xml`:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Với Spring Boot parent/BOM do Initializr tạo, để dependency management chọn version tương thích; không tự đặt version Artemis không khớp client. Đây là cấu hình dành cho Boot 3.x, **không phải tuyên bố mọi version Boot mới nhất có API/auto-configuration hoàn toàn giống nhau**.

### 7.2. Broker cho lab

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=invoices.object
spring.jms.pub-sub-domain=false
~~~

Tên `invoices.object` chỉ là tên queue demo. Bạn không cần tự mở Artemis server riêng khi nhúng thành công. Embedded broker demo không phải cấu hình bảo mật/persistence production.

### 7.3. Một file ứng dụng Java hoàn chỉnh

Lưu tại `src/main/java/com/example/objectmessagelab/ObjectMessageLabApplication.java`:

~~~java
package com.example.objectmessagelab;

import java.io.Serial;
import java.io.Serializable;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class ObjectMessageLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObjectMessageLabApplication.class, args);
    }

    @Bean
    ApplicationRunner publisher(JmsTemplate template) {
        return args -> {
            InvoiceEvent event = new InvoiceEvent("INV-7", 5500);
            template.convertAndSend("invoices.object", event);
            System.out.println("Published: " + event.invoiceId());
        };
    }

    public static final class InvoiceEvent implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String invoiceId;
        private final long amountMinor;

        public InvoiceEvent(String invoiceId, long amountMinor) {
            this.invoiceId = invoiceId;
            this.amountMinor = amountMinor;
        }

        public String invoiceId() {
            return invoiceId;
        }

        public long amountMinor() {
            return amountMinor;
        }
    }

    @Component
    public static class InvoiceReceiver {
        @JmsListener(destination = "invoices.object")
        public void receive(InvoiceEvent event) {
            System.out.println("Consumed: "
                    + event.invoiceId() + " / " + event.amountMinor());
        }
    }
}
~~~

Điều kiện lab: không khai báo một `MessageConverter` tùy biến thay thế `SimpleMessageConverter`; broker/client cho phép deserialize class demo; dependency phù hợp với Boot 3.x. `InvoiceEvent` nằm trong namespace `com.example.objectmessagelab` ở cả sender và receiver (trong lab chúng cùng một app).

Chạy trong thư mục gốc project:

~~~bash
./mvnw spring-boot:run
~~~

Trên PowerShell Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Bên cạnh log Spring/Artemis, mong đợi có các dòng:

~~~text
Published: INV-7
Consumed: INV-7 / 5500
~~~

**Thứ tự hai dòng không được bảo đảm** vì listener chạy trên thread khác. `Published` là việc template đã gửi message; `Consumed` đến sau khi Spring consumer deserialize và gọi listener. Trong trường hợp có retry, shutdown hoặc cấu hình lại, log không đủ chứng minh exactly-once delivery.

### 7.4. Từng bước từ code đến broker

1. `ApplicationRunner` tạo một instance `InvoiceEvent` (đã `Serializable`).
2. `JmsTemplate.convertAndSend` hỏi `SimpleMessageConverter` chuyển object; converter tạo `ObjectMessage` dựa trên Jakarta Messaging.
3. JMS provider biến object thành dữ liệu có thể đi qua broker; broker lưu/route vào queue.
4. Spring listener container nhận message và chuyển body thành `InvoiceEvent` thông qua converter.
5. `InvoiceReceiver.receive` in data được khôi phục.

Nếu cố tình đổi field thành đối tượng `new Object()` không serializable, hoặc thay đổi UID/class trong một consumer riêng, bạn có thể quan sát lỗi ở tầng serialization/deserialization. Chỉ làm thí nghiệm này trong môi trường local; không dùng một broker production để thử payload hỏng.

### 7.5. Vì sao không biến ví dụ thành mẫu production?

Ứng dụng lab là **producer và consumer cùng codebase/classpath**; cấu hình ấy che phần lớn coupling khi tách hai service triển khai độc lập. Nó cũng không áp dụng ACL, package allowlist chặt chẽ, schema migration, idempotency hay quản lý backlog. Với môi trường nhiều service, Java Serialization thường là lựa chọn kém bền vững cho event contract.

## 8. Hướng thay thế: JSON TextMessage với DTO có version

Để truyền dữ liệu nghiệp vụ giữa service, thường nên định nghĩa **contract độc lập với Java implementation**, ví dụ JSON:

~~~json
{
  "eventId": "evt-001",
  "eventType": "InvoiceCreated",
  "schemaVersion": 1,
  "invoiceId": "INV-7",
  "amountMinor": 5500
}
~~~

Một event có thể được mã hóa trong `TextMessage`, giữ các metadata quan trọng trong body (và khi hữu ích có thể lặp type/version trong JMS properties có kiểm soát). Hai bên phải thống nhất schema và các quy tắc compatibility, đặc biệt khi thêm/xóa/đổi field.

### 8.1. Gửi chuỗi JSON với Spring JMS

Trong một Spring service có `JmsTemplate template`:

~~~java
String json = """
        {"eventId":"evt-001","eventType":"InvoiceCreated",
         "schemaVersion":1,"invoiceId":"INV-7","amountMinor":5500}
        """;

template.convertAndSend("invoices.json", json, message -> {
    message.setStringProperty("contentType", "application/json");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
~~~

Đây là **mảnh mã Java 17+**; cần bean `JmsTemplate` và queue tương ứng. Với `SimpleMessageConverter`, `String` được chuyển thành `TextMessage`. Property `contentType` là convention của ứng dụng (không phải header MIME bắt buộc của chuẩn JMS). Consumer nhận `String` rồi parse bằng JSON library sang một DTO rõ kiểu, kiểm tra version và dữ liệu; **không gọi `ObjectInputStream`**.

### 8.2. Khi dùng MappingJackson2MessageConverter

Trên Spring Framework 6.x với Jackson 2, bạn cũng có thể gắn `MappingJackson2MessageConverter` vào `JmsTemplate` **và** listener factory/container cùng contract để tự serialize DTO thành JSON dưới dạng `TextMessage` hoặc `BytesMessage`. Ví dụ cấu hình (mảnh Bean trong `@Configuration`, cần import `Bean`, `MessageType`, `MappingJackson2MessageConverter`, `Map` và DTO tương ứng):

~~~java
@Bean
MappingJackson2MessageConverter jsonConverter() {
    var converter = new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(Map.of("invoice-created-v1",
            InvoiceCreatedDto.class));
    return converter;
}
~~~

Điều quan trọng:
- Đăng ký converter với **đúng** template/listener container; chỉ khai báo một bean chưa bảo đảm cấu hình mọi factory tự tạo đã sử dụng nó.
- `setTargetType(MessageType.TEXT)` cần thiết nếu muốn JSON **TextMessage**, vì converter có thể mặc định dùng BytesMessage.
- `_type` / mapping cần thỏa thuận giữa producer–consumer và tránh phát tán raw Java class name; chỉ cho phép các target DTO dự kiến.
- Sử dụng chính sách JSON parser an toàn; tránh bật default polymorphic typing rộng hoặc deserialize payload tùy ý sang `Object` mà không có allowlist.
- Khi dùng Spring Framework thế hệ khác (ví dụ Spring 7/Jackson 3), **kiểm tra converter tương ứng theo phiên bản** thay vì copy class name không có trên classpath.

Nếu không cần converter tự động, cách gửi `String` + parse JSON tường minh dễ audit hơn và không làm hành vi chuyển đổi message phụ thuộc cấu hình ẩn.

### 8.3. Khi nào dùng BytesMessage?

`BytesMessage` hữu ích nếu tổ chức đã chọn Avro, Protobuf hoặc binary schema khác: message body là mảng byte, consumer dùng schema/codec tương thích. Những binary format này **không đồng nghĩa** với Java native serialized stream. Quy định schema registry/versioning, encoding, content type, maximum size và tương thích giữa phiên bản vẫn cần thiết.

## 9. Chiến lược chuyển từ ObjectMessage sang TextMessage

Một lỗi thường gặp là đổi publisher sang JSON rồi cập nhật consumer ngay, trong khi queue đang có backlog `ObjectMessage`. Consumer mới có thể không xử lý được message cũ; ngược lại consumer cũ không hiểu `TextMessage` mới.

Quy trình triển khai có kiểm soát:

1. **Lập bản đồ**: xác định tất cả producer/consumer, queue/topic, class/payload đang dùng, serialVersionUID, message TTL, retry, DLQ, thời gian message tồn tại dài nhất, khả năng rollback deploy.
2. **Định nghĩa contract mới**: event type, schema version, DTO, contentType, idempotency key, bảo mật và mã hóa (JSON/Avro/Protobuf).
3. **Thêm phiên bản consumer mới**: đọc được định dạng mới, kiểm thử message phát từ producer cũ; nếu muốn hỗ trợ dual-format cùng queue thì phải phân luồng dựa trên type an toàn và giữ class cần thiết cho backlog cũ.
4. **Chuyển producer có kế hoạch**: sử dụng destination/version mới như `invoices.v2` khi thuận lợi, để đường đi cũ/ mới không lẫn nhau; nếu dual-publish thì phải thiết kế tránh tạo hai business effects.
5. **Drain/reconcile backlog và DLQ**: chỉ xóa dependencies cũ sau khi không còn object message cần đọc hoặc đã migrate theo quy trình được kiểm chứng.
6. **Giám sát và loại bỏ đường cũ**: theo dõi số message theo format, conversion failures, redelivery/DLQ, độ trễ xử lý. Khi contract mới ổn, ngừng publish format cũ và thu hồi quyền.
7. **Kiểm thử rolling deployment**: producer v1 → consumer v2, producer v2 → consumer v1 (nếu có overlap), restart trong lúc queue có backlog, replay DLQ, failure giữa publish và ack.

Trong khi chuyển, giữ nguyên cơ chế **idempotency** và transaction boundary. Việc thay encoding không thay bảo đảm giao nhận hay concurrency. Một message được publish hai lần vì dual-publish không được tự coi là một nghiệp vụ duy nhất.

## 10. Các sự cố thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `NotSerializableException` khi gửi | Một nested field không `Serializable` | Kiểm tra graph thực tế; tránh serialize whole aggregate/ORM entity |
| `InvalidClassException` khi nhận | `serialVersionUID`/serialized form không tương thích | So sánh artifact versions, UID và dữ liệu backlog; tránh đổi UID tùy tiện |
| `ClassNotFoundException` lúc deserialize | Consumer thiếu class/package/version | Kiểm tra deployment classpath và namespace của serialized class |
| Lỗi allowlist/denylist | JMS client từ chối class trong graph | Xem chính sách của **đúng provider**, chỉ cho phép class thực sự cần |
| `ClassCastException` sau nhận | Payload không có kiểu mà handler kỳ vọng | Gắn type/version đúng, sửa producer–consumer contract; cast không bảo vệ bước deserialize |
| `MessageConversionException` / `JmsException` | Converter không hiểu body hoặc lớp dưới lỗi | Kiểm tra message type thực, converter bean, root cause và DLQ |
| Listener không vào code nhưng queue bị retry | Lỗi xảy ra trước listener (deserialization/conversion) | Quan sát container error log, broker delivery count, error handler và DLQ |
| Consumer mới đọc sai message cũ | Đổi class/fields khi queue còn backlog | Compatibility test với payload cũ, drain/migrate có kiểm soát |
| Consumer không phải Java | Không hỗ trợ native Java serialized form | Thiết kế contract schema text/binary độc lập ngôn ngữ |
| Message nhìn thấy là binary khó debug | Đây là Java-serialized graph | Dùng metadata/broker inspection an toàn; không deserialize dữ liệu lạ để “xem thử” |
| Sau retry có hai business side effects | Redelivery, transaction/ack rời business DB | Idempotency key, inbox/outbox, phân tích transaction boundary |
| Payload chứa dữ liệu nhạy cảm | Serialize cả object graph ngoài ý định | Dùng DTO tối giản, giới hạn fields, ACL/TLS, masking và retention |

**Lưu ý lỗi trong Spring:** exception từ broker/client/JMS API có thể được wrapper nhiều tầng; log root cause và `JMSRedelivered`/delivery count (nếu provider hỗ trợ). Không giả định một exception class hay thông điệp lỗi giống nhau trên mọi broker.

## 11. Checklist chọn ObjectMessage hay một định dạng khác

**Chỉ cân nhắc `ObjectMessage` khi** có lý do rõ ràng: cả producer lẫn consumer là Java, cùng ranh giới tin cậy, cùng lifecycle contract, hiểu và kiểm soát được mọi class trong object graph, không cần tích hợp đa ngôn ngữ, có test cross-version và broker/client hỗ trợ chính sách deserialization cần thiết.

Trước khi chấp nhận trong thiết kế thực tế, tự trả lời:

- Có producer nào ngoài quyền kiểm soát của nhóm không? Broker ACL và quyền publish đã chặt chưa?
- Consumer có luôn có class phù hợp với object graph đang nằm ở broker/DLQ không?
- `serialVersionUID` và quy tắc compatibility qua rolling deployment đã được thử nghiệm chưa?
- Có fields `transient`, circular reference, nested library class, ORM entity, lazy proxy hay object có state không nên truyền không?
- Client/provider đã áp dụng allowlist và giới hạn kích thước/độ sâu phù hợp? Có biết rõ phần nào do JVM filter kiểm soát?
- Lỗi deserialize trước handler có được ghi log, retry có giới hạn và đưa vào DLQ đúng cách không?
- Có yêu cầu consumer Node.js/Python/Go, quan sát payload hoặc giữ event nhiều tháng không?
- Có cách thay bằng JSON `TextMessage` hoặc schema binary `BytesMessage` mà giảm coupling không?
- Nếu message đã được publish thì có cần duy trì khả năng đọc backlog trong nhiều phiên bản app không?
- Message schema/idempotency key và ownership của producer–consumer có được mô tả rõ không?

**Kết luận thiết kế:** `ObjectMessage` có thể thuận tiện khi nhiều Java component tin cậy cần chuyển một DTO nội bộ rất ngắn hạn, nhưng nó mang theo **định dạng serialization và phụ thuộc class Java vào hợp đồng messaging**. Với integration/event giữa service có vòng đời triển khai riêng, định dạng có schema và không lệ thuộc Java implementation thường dễ kiểm soát, an toàn và nâng cấp hơn.

## 12. Bài tập củng cố

1. Dùng ví dụ `SerializationProbe` thêm một field `transient String ephemeral = "abc"`; sau deserialize dự đoán giá trị và giải thích vì sao.
2. Thay `InvoiceDraft` bằng object chứa `java.net.Socket` hoặc một đối tượng tùy chỉnh không `Serializable`. Giải thích lỗi nằm ở đâu và vì sao chỉ thêm `implements Serializable` cho lớp ngoài chưa đủ.
3. Có 50 `ObjectMessage` của lớp `com.shop.v1.InvoiceCreated` trong queue, đội phát triển vừa đổi class thành `com.shop.v2.InvoiceCreated`. Phân tích bước migrate an toàn không làm mất backlog.
4. Kiểm tra `JmsTemplate.convertAndSend` với `String`, `byte[]`, `Map` và một `Serializable` DTO. Dự đoán message body type dưới `SimpleMessageConverter`.
5. Viết JSON schema/contract cho `InvoiceCreated` v1 và v2. Định nghĩa quy tắc field mới optional, schemaVersion, idempotency key và cách consumer version cũ xử lý.
6. Giả sử JMS client chặn class do allowlist. Tại sao đổi handler sang `receive(Object obj)` hoặc kiểm tra `instanceof` sau nhận không sửa được ranh giới deserialization?
7. Một producer gửi thành công nhưng consumer chết sau ghi database và trước ack. Giải thích vì sao **đổi `ObjectMessage` sang `TextMessage` không tự loại bỏ duplicate delivery**.

## 13. Tài liệu để đối chiếu

- Jakarta Messaging 3.1 `ObjectMessage` API: https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/objectmessage
- Jakarta Messaging 3.1 Specification, message bodies/object messages: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Oracle Java 17 `Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle Java Serialization, versioning: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html
- Spring Framework 6.2 `SimpleMessageConverter` API: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html
- Spring Framework JMS sending/converting: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework 6.2 `MappingJackson2MessageConverter` API: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Apache ActiveMQ Artemis security/ObjectMessage deserialization: https://artemis.apache.org/components/artemis/documentation/latest/security.html
- Apache ActiveMQ Classic ObjectMessage security: https://activemq.apache.org/components/classic/documentation/objectmessage
