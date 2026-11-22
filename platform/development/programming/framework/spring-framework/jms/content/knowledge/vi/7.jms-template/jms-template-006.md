# MessageCreator và Session được callback cung cấp trong JmsTemplate

## 1. Vấn đề mà MessageCreator giải quyết

Khi gửi message bằng Spring JMS, ứng dụng thường muốn tạo **JMS Message** theo đúng định dạng mà hệ thống nhận yêu cầu: nội dung `TextMessage`, `MapMessage` hoặc `BytesMessage`; thêm các property như `eventType`, `schemaVersion`; gắn `JMSCorrelationID` để theo dõi giao dịch. Những đối tượng này được tạo bằng API `jakarta.jms.Session`.

Nếu làm thuần Jakarta Messaging, mã ứng dụng thường phải làm việc với `ConnectionFactory`, `Connection`, `Session` và `MessageProducer`, xử lý `JMSException` và quản lý tài nguyên. Spring cung cấp `JmsTemplate` để thực hiện các bước nền đó. Ứng dụng chỉ cung cấp một **callback** làm đúng nhiệm vụ tạo message.

Ví dụ cốt lõi:

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage message = session.createTextMessage("ORDER-1001");
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

Trong đoạn này:

- `jmsTemplate.send(...)` là thao tác gửi đồng bộ được gọi bởi ứng dụng; nó sẽ tạo và gửi JMS message.
- `"orders.in"` là tên destination cần gửi; Spring phân giải tên thành `Destination` theo cấu hình.
- `session -> { ... }` là một `MessageCreator` viết bằng lambda. **Spring truyền `Session` vào callback**, không phải ứng dụng truyền một `Session` do mình tự tạo.
- `session.createTextMessage(...)` dùng chính session mà Spring cấp để tạo một `jakarta.jms.TextMessage`.
- `return message` trao đối tượng đã chuẩn bị cho `JmsTemplate`; template tiếp tục gửi qua JMS provider.

Ví dụ này là lời gọi đặt **bên trong method có `JmsTemplate` được inject**; đây chưa phải một class Java độc lập.

### Kết quả học tập

Sau bài này, bạn sẽ giải thích được hợp đồng `MessageCreator`, biết `Session` đến từ đâu và chỉ tồn tại trong phạm vi sử dụng nào; tạo và chỉnh header/property của nhiều loại message; hiểu khác biệt giữa `send`, `convertAndSend` và các callback khác; xử lý lỗi, giao dịch và kiểm thử callback một cách có chủ đích.

## 2. Hợp đồng chính xác của MessageCreator

`org.springframework.jms.core.MessageCreator` là functional interface của Spring JMS, có một phương thức trừu tượng:

```java
@FunctionalInterface
public interface MessageCreator {
    jakarta.jms.Message createMessage(jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
```

Đây là **mô tả chữ ký API**; trong dự án thực tế hãy sử dụng interface từ thư viện Spring, không định nghĩa lại.

Ý nghĩa:

| Thành phần | Diễn giải |
| --- | --- |
| `createMessage(Session session)` | Callback do `JmsTemplate` gọi để tạo một message |
| `Session` | Đối tượng Jakarta Messaging có sẵn cho lần thao tác hiện tại, dùng làm factory để tạo message |
| `Message` trả về | Đối tượng message hoàn chỉnh mà template sẽ gửi; ví dụ `TextMessage`, `MapMessage`, `BytesMessage` |
| `throws JMSException` | Cho phép gọi các API JMS có checked exception ngay trong callback |
| `@FunctionalInterface` | Có thể viết bằng lambda, method reference hoặc anonymous class |

Khai báo lambda này:

```java
MessageCreator creator = session -> session.createTextMessage("hello");
```

tương đương về ý tưởng với anonymous class:

```java
MessageCreator creator = new MessageCreator() {
    @Override
    public Message createMessage(Session session) throws JMSException {
        return session.createTextMessage("hello");
    }
};
```

Đối với hai ví dụ trên, các import cần có là `jakarta.jms.JMSException`, `jakarta.jms.Message`, `jakarta.jms.Session` và `org.springframework.jms.core.MessageCreator`.

**Chú ý:** tên biến `session` do người viết lambda tự đặt; nó không phải tên bean để Spring tìm kiếm. Kiểu tham số được suy ra từ chữ ký `MessageCreator`. Lambda được thực thi **khi `JmsTemplate` gọi callback trong quá trình `send`**, không phải khi broker tiêu thụ message và cũng không phải một `@JmsListener`.

## 3. Luồng hoạt động bên trong JmsTemplate.send

Ví dụ `jmsTemplate.send("orders.in", creator)` có thể được hiểu qua luồng khái quát sau:

```text
Code ứng dụng gọi JmsTemplate.send(destinationName, creator)
                 |
                 v
      JmsTemplate lấy JMS Connection/Session
      hoặc tham gia Session gắn với transaction phù hợp
                 |
                 v
      Phân giải tên "orders.in" thành Destination
                 |
                 v
      Gọi creator.createMessage(session)
                 |
                 v
      Callback dùng session.createXxxMessage(...)
      đặt body / headers / properties, rồi return Message
                 |
                 v
      JmsTemplate dùng MessageProducer để gửi Message
                 |
                 v
      Spring hoàn tất xử lý tài nguyên và transaction
      theo cấu hình đang có; trả về hoặc báo lỗi
```

Đây là **sơ đồ hành vi**, không phải mã nguồn nội bộ đầy đủ hoặc cam kết về mọi bước tối ưu hóa của provider.

Ba ranh giới quan trọng:

1. **`MessageCreator` chỉ tạo message.** Nó không tự chọn một broker, không nhận message từ consumer và không thay thế `MessageProducer`.
2. **`Session` là tài nguyên do template cung cấp.** Không gọi `session.close()`, `commit()` hay `rollback()` bên trong `MessageCreator`; việc đóng và quản lý giao dịch nằm ở lớp điều phối.
3. **`send` trả về không có nghĩa là nghiệp vụ phía consumer đã hoàn thành.** Trong giao dịch JMS, kết quả cuối còn phụ thuộc commit; trong hệ thống bất đồng bộ, message có thể chưa được consumer xử lý khi method gửi kết thúc.

`JmsTemplate` xử lý `JMSException` và chuyển thành ngoại lệ Spring JMS dạng unchecked `org.springframework.jms.JmsException`. Vì vậy lambda có thể gọi API ném checked `JMSException` mà method nghiệp vụ gọi `send` không cần khai báo `throws JMSException`. Một `IllegalArgumentException` do chính code ứng dụng ném ra vẫn là lỗi lập trình riêng, không nên coi là lỗi kết nối broker.

## 4. Vì sao callback phải dùng Session được cung cấp?

`jakarta.jms.Session` là ngữ cảnh làm việc của JMS: nó biết provider, connection, cách tạo các kiểu message, và tham gia ngữ cảnh transaction/acknowledgment phù hợp. Các factory method thường dùng:

| Phương thức trên `Session` | Đối tượng trả về | Tình huống |
| --- | --- | --- |
| `createTextMessage(String text)` | `TextMessage` | Chuỗi ký tự, JSON hoặc XML được biểu diễn thành text |
| `createMapMessage()` | `MapMessage` | Một tập giá trị có tên với các kiểu được hỗ trợ |
| `createBytesMessage()` | `BytesMessage` | Payload dạng byte theo giao ước riêng |
| `createStreamMessage()` | `StreamMessage` | Chuỗi giá trị đọc/ghi tuần tự theo giao ước JMS |
| `createObjectMessage(Serializable object)` | `ObjectMessage` | Object Java có thể tuần tự hóa; cần cân nhắc tương thích và rủi ro deserialization |

Đặc biệt, **`jakarta.jms.Message` là interface**, không thể tạo bằng `new Message()`. Không nên tự tạo `Connection`/`Session` thứ hai trong callback rồi dùng message từ một ngữ cảnh khác; làm vậy phá cách quản lý tài nguyên/giao dịch của `JmsTemplate` và có thể gây lỗi provider-specific.

`Session` cũng **không an toàn cho truy cập đồng thời từ nhiều thread** theo quy tắc của Jakarta Messaging. Không lưu `Session` trong field `static`, singleton hay cache, không chuyển nó sang `CompletableFuture`/`Executor`, không sử dụng lại sau khi callback kết thúc. Nếu muốn gửi bất đồng bộ từ một task khác, task đó tự gọi `JmsTemplate.send(...)` để Spring cung cấp session phù hợp cho lần gửi của chính nó.

Một `JmsTemplate` đã được cấu hình xong có thể được các service chia sẻ. Quy tắc này **không có nghĩa** một đối tượng `Session` cụ thể được phép dùng đồng thời giữa các thread.

## 5. Ví dụ đầy đủ với Spring Boot 3.x và Java 17+

Tình huống: broker đã có queue `orders.in`. Khi người dùng đặt hàng, producer gửi mã đơn hàng dưới dạng `TextMessage`, gắn `eventType`, phiên bản schema và correlation ID.

Ví dụ cần một ứng dụng Spring Boot 3.x dùng Java 17+ và **broker ActiveMQ Artemis đang chạy, truy cập được, có queue `orders.in`**. Phần cấu hình là dành cho một dự án Gradle Spring Boot có sẵn, không phải chương trình Java SE chỉ dùng lệnh `javac`.

### 5.1. Dependency

Thêm vào `build.gradle` của dự án Spring Boot (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dự án phải đã áp dụng plugin và quản lý phiên bản Spring Boot tương ứng. Starter Artemis cung cấp tích hợp JMS; không cần tự thêm dependency `javax.jms`. Spring Framework 6 / Boot 3 dùng namespace **`jakarta.jms`**.

### 5.2. Cấu hình kết nối và destination

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    orders:
      input: "${JMS_ORDERS_QUEUE:orders.in}"
```

Các biến môi trường `JMS_USER`, `JMS_PASSWORD` phải được thiết lập cho broker; `JMS_BROKER_URL` và `JMS_ORDERS_QUEUE` có giá trị mặc định để thực hành. Không đặt credentials thật trong mã nguồn. Tên queue phải khớp tài nguyên do broker quản lý; cấu hình này **không bảo đảm queue vật lý được tạo**.

### 5.3. Lớp khởi động

File `src/main/java/demo/jms/DemoApplication.java`:

```java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Một producer chỉ dùng `JmsTemplate` không cần `@EnableJms`. Annotation đó dành cho cơ sở hạ tầng nhận bằng `@JmsListener` nếu ứng dụng có listener.

### 5.4. Producer dùng MessageCreator

File `src/main/java/demo/jms/OrderPublisher.java`:

```java
package demo.jms;

import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate jmsTemplate;
    private final String destinationName;

    public OrderPublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.jms.orders.input}") String destinationName) {
        this.jmsTemplate = jmsTemplate;
        this.destinationName = destinationName;
    }

    public void publishOrderCreated(String orderId, String correlationId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException("correlationId must not be blank");
        }

        jmsTemplate.send(destinationName, session -> {
            TextMessage message = session.createTextMessage(orderId);
            message.setStringProperty("eventType", "ORDER_CREATED");
            message.setIntProperty("schemaVersion", 1);
            message.setJMSCorrelationID(correlationId);
            return message;
        });
    }
}
```

Phân tích theo thứ tự:

1. `OrderPublisher` nhận `JmsTemplate` và tên queue qua constructor injection; không tự tạo connection hoặc session.
2. `publishOrderCreated(...)` kiểm tra dữ liệu đầu vào **trước khi gọi `send`**, tránh thao tác broker cho request không hợp lệ.
3. Tham số `session` của lambda được **`JmsTemplate` cung cấp lúc gửi**.
4. `session.createTextMessage(orderId)` tạo message có body là mã đơn hàng. `setStringProperty` và `setIntProperty` thêm application properties có kiểu rõ ràng.
5. `setJMSCorrelationID(correlationId)` gắn standard JMS header phục vụ correlation. Đây là ID do ứng dụng chọn, ví dụ `corr-1001`; không bắt đầu bằng tiền tố dành cho provider-generated message ID là `ID:`.
6. `return message` trao `TextMessage` về template để gửi. **Không cần và không nên tạo `MessageProducer` trong callback này.**

Khi consumer đọc JMS message, nó có thể lấy `getText()` từ `TextMessage`, `getStringProperty("eventType")`, `getIntProperty("schemaVersion")` và `getJMSCorrelationID()`. Những API này khác với việc tự mã hóa toàn bộ metadata vào JSON body.

### 5.5. Chạy thử có kiểm soát

Thêm một runner chỉ hoạt động khi bật profile `demo`, trong file `src/main/java/demo/jms/DemoSendRunner.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("demo")
public class DemoSendRunner implements ApplicationRunner {
    private final OrderPublisher publisher;

    public DemoSendRunner(OrderPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publishOrderCreated("ORDER-1001", "corr-1001");
        System.out.println("Đã gọi gửi JMS cho ORDER-1001");
    }
}
```

Khi broker, queue và thông tin đăng nhập đã sẵn sàng, ở môi trường shell có biến môi trường tương ứng, chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo'
```

Nếu `send` hoàn tất không ném ngoại lệ, runner in dòng của **ứng dụng**:

```text
Đã gọi gửi JMS cho ORDER-1001
```

Đó không phải toàn bộ stdout của Spring Boot. Không có bảo đảm consumer đã xử lý message trước dòng này. Hãy kiểm tra queue metrics/message browser hoặc consumer thử nghiệm để xác nhận payload `ORDER-1001` và ba metadata đã đặt. Nếu broker chưa có hoặc thiếu quyền, thao tác gửi có thể thất bại và **không xuất hiện** dòng trên.

Runner gửi một message mỗi lần khởi động với profile `demo`. Không bật profile này trong production.

## 6. Những kiểu Message khác cùng một callback

### 6.1. Tạo MapMessage

Khi hai bên thống nhất dùng JMS `MapMessage`, callback có thể trả về kiểu này:

```java
jmsTemplate.send(destinationName, session -> {
    jakarta.jms.MapMessage message = session.createMapMessage();
    message.setString("orderId", "ORDER-1001");
    message.setInt("quantity", 2);
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

Đây là đoạn minh họa **bên trong class có `jmsTemplate` và `destinationName`**. Các field `orderId`/`quantity` thuộc **body MapMessage**; `eventType` là **message property**, không phải cùng vùng dữ liệu. Consumer phải biết loại message dự kiến.

### 6.2. Tạo BytesMessage

```java
byte[] payload = "ORDER-1001"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

jmsTemplate.send(destinationName, session -> {
    jakarta.jms.BytesMessage message = session.createBytesMessage();
    message.writeBytes(payload);
    message.setStringProperty("contentType", "text/plain; charset=utf-8");
    return message;
});
```

Ứng dụng nhận cần thống nhất cách giải mã bytes. Thuộc tính `contentType` trong ví dụ là **quy ước ứng dụng**, không phải JMS tự hiểu hay tự chuyển bytes thành text.

### 6.3. Chỉnh header và property khác với body

- **Body** là dữ liệu chính, ví dụ `ORDER-1001` trong `TextMessage`.
- **JMS standard header** là metadata có ý nghĩa trong chuẩn, ví dụ `JMSCorrelationID`, `JMSReplyTo`, `JMSType`.
- **Application property** là cặp tên/giá trị do ứng dụng tự định nghĩa, ví dụ `eventType`, `schemaVersion`; có thể được consumer đọc hoặc dùng trong JMS selector.

`JMSMessageID` thường do provider gán trong quá trình gửi; không dùng nó như một ID bạn chủ động đặt trước trong callback. Tham số QoS của producer như `deliveryMode`, `priority`, `timeToLive` nên cấu hình theo cơ chế của `JmsTemplate`/`MessageProducer`. Chỉ gọi setter trên một số header của `Message` không tương đương việc thiết lập chính sách QoS khi gửi. Chẳng hạn, nếu cần yêu cầu template dùng `setTimeToLive(...)`, phải xem cả `setExplicitQosEnabled(true)` và chính sách broker.

## 7. Khi nào chọn send, convertAndSend hay callback khác?

| Cơ chế | Điểm nhận vào | Dùng khi |
| --- | --- | --- |
| `send(String, MessageCreator)` | Callback nhận `Session` rồi trả `Message` | Cần chủ động tạo loại JMS message, cấu trúc body, headers/properties |
| `convertAndSend(String, Object)` | Object ứng dụng, đi qua `MessageConverter` | Muốn Spring chuyển `String`, `byte[]`, `Map` hoặc object qua converter cấu hình |
| `convertAndSend(String, Object, MessagePostProcessor)` | Converter tạo message trước, processor sửa message sau | Chỉ cần bổ sung header/property sau khi đã chuyển đổi body |
| `execute(SessionCallback<T>)` | Callback làm việc trực tiếp với `Session` và trả kết quả | Cần nhiều thao tác JMS tùy chỉnh ngoài một message đơn |
| `execute(ProducerCallback<T>)` | Callback nhận cả `Session` và `MessageProducer` | Cần logic producer mức thấp, điều khiển gửi nhiều message theo thao tác của mình |

**Ví dụ tương đương mục đích đơn giản:**

```java
// MessageCreator: chính bạn dùng Session để tạo TextMessage.
jmsTemplate.send("orders.in", session ->
        session.createTextMessage("ORDER-1001"));

// MessageConverter: Spring chuyển String thành TextMessage
// khi dùng SimpleMessageConverter mặc định.
jmsTemplate.convertAndSend("orders.in", "ORDER-1001");

// MessagePostProcessor: chuyển body trước, bổ sung property sau.
jmsTemplate.convertAndSend(
        "orders.in",
        "ORDER-1001",
        message -> {
            message.setStringProperty("eventType", "ORDER_CREATED");
            return message;
        });
```

Đoạn trên minh họa ba cách gọi trong một method đã có `jmsTemplate`. Đối với `String`, `SimpleMessageConverter` mặc định thường tạo `TextMessage`; nếu ứng dụng thay `MessageConverter`, kết quả phụ thuộc converter đó.

Chọn `MessageCreator` khi bạn **thực sự cần kiểm soát việc tạo JMS Message bằng Session**. Nếu chỉ gắn thêm vài property vào message do converter đã tạo đúng loại, `MessagePostProcessor` thường gọn hơn. `MessagePostProcessor` nhận `Message`, **không nhận `Session`**, nên không dùng nó để tự gọi `session.createMapMessage()`.

Các overload của `JmsTemplate.send`:

```java
send(MessageCreator creator);                       // destination mặc định
send(String destinationName, MessageCreator creator); // tên destination
send(Destination destination, MessageCreator creator); // đối tượng đích
```

Đây là các chữ ký rút gọn để đọc, không phải một class độc lập. Overload không truyền destination chỉ hoạt động khi template đã thiết lập `defaultDestination` hoặc `defaultDestinationName`. Một tên `String` được ánh xạ qua `DestinationResolver`; tùy cấu hình, nó có thể là tên đích động hoặc tên lookup JNDI.

## 8. Vòng đời, transaction, lỗi và điều không nên làm

### 8.1. Session là tài nguyên có phạm vi, không phải dữ liệu để giữ lại

Sai:

```java
// PHẢN VÍ DỤ: không lưu Session từ callback để dùng ngoài vòng đời.
private jakarta.jms.Session storedSession;

void brokenSend() {
    jmsTemplate.send("orders.in", session -> {
        storedSession = session; // Sai: giữ tài nguyên do Spring quản lý.
        return session.createTextMessage("hello");
    });
}
```

Đây chỉ là đoạn phản ví dụ trong một class giả định. Sau khi `send` kết thúc, `storedSession` không còn là một tài nguyên ứng dụng được quyền sử dụng tùy ý; nếu là session gắn với transaction, vòng đời còn do transaction manager quyết định. Đừng dùng `Session` ở thread khác hoặc tự đóng session trong callback.

Đúng: giữ **dữ liệu nghiệp vụ** ngoài callback và để mỗi lần `jmsTemplate.send(...)` nhận session phù hợp tại thời điểm thực hiện.

### 8.2. Callback không tự commit hoặc rollback

Khi không bật transaction JMS, send sử dụng cấu hình session/provider tương ứng. Nếu ứng dụng dùng `JmsTransactionManager` hoặc transaction coordinator phù hợp, `JmsTemplate` có thể tham gia session gắn transaction; message sẽ chịu ảnh hưởng của commit/rollback. Vì vậy:

- Không gọi `session.commit()`/`rollback()` ngay trong `MessageCreator`.
- `@Transactional` chỉ có ý nghĩa theo **transaction manager thực sự đang áp dụng**; không mặc định cho rằng một annotation bảo đảm thao tác database và broker là atomic.
- Nếu cần DB + JMS nhất quán xuyên hệ thống, hãy thiết kế transaction/outbox hoặc cơ chế điều phối theo yêu cầu hệ thống; đó là bài toán khác với tạo message trong callback.

### 8.3. Checked exception ở trong callback

`Session.createTextMessage(...)` và setter trên JMS message có thể ném `JMSException`; interface đã khai báo `throws JMSException`. Trong đoạn lambda:

```java
jmsTemplate.send("orders.in", session -> {
    TextMessage message = session.createTextMessage("ORDER-1001");
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

không cần bắt `JMSException` thủ công chỉ để biên dịch. Khi thao tác `send` qua `JmsTemplate`, Spring chuyển lỗi JMS phù hợp sang unchecked `JmsException`. Tùy nguyên nhân thực tế, cũng có thể có lỗi kết nối, định tuyến, quyền, converter hoặc exception của chính ứng dụng. Không bắt rộng rồi âm thầm coi là gửi thành công.

### 8.4. Tránh làm việc không thuộc trách nhiệm callback

Không thực hiện HTTP call chậm, truy vấn database không cần thiết, tạo thread, lặp lại gửi hoặc gọi `session.createProducer()` bên trong `MessageCreator` chỉ để tạo một message. Callback nên **ngắn, xác định và chỉ tạo message**; gửi thật do template thực hiện. Nếu cần nhiều thao tác với `Session`/`MessageProducer`, sử dụng callback mức phù hợp và quản lý transaction rõ ràng.

### 8.5. Message chưa được gửi chỉ vì callback trả về

`return message` kết thúc bước *tạo* message. `JmsTemplate` còn phải gửi qua producer và provider. Một lỗi sau khi callback trả về vẫn có thể khiến `send` thất bại. Tương tự, nếu việc gửi nằm trong transaction chưa commit, không được coi message đã hiện diện vĩnh viễn trên broker chỉ vì callback tạo xong.

## 9. Kiểm thử rằng MessageCreator sử dụng Session được cấp

Unit test có thể bắt `MessageCreator` truyền vào `JmsTemplate.send`, tự gọi callback với `Session` giả lập rồi xác minh chính session đó được dùng để tạo message. Không cần broker cho phép thử này; đồng thời phải hiểu rằng **test chỉ kiểm tra logic tạo message, không kiểm tra JMS send thật**.

File `src/test/java/demo/jms/OrderPublisherTest.java`:

```java
package demo.jms;

import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.MessageCreator;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderPublisherTest {

    @Mock
    JmsTemplate jmsTemplate;

    @Mock
    Session session;

    @Mock
    TextMessage textMessage;

    @Test
    void callbackCreatesMessageUsingProvidedSession() throws Exception {
        OrderPublisher publisher =
                new OrderPublisher(jmsTemplate, "orders.in");

        publisher.publishOrderCreated("ORDER-1001", "corr-1001");

        ArgumentCaptor<MessageCreator> captor =
                ArgumentCaptor.forClass(MessageCreator.class);
        verify(jmsTemplate).send(eq("orders.in"), captor.capture());

        when(session.createTextMessage("ORDER-1001"))
                .thenReturn(textMessage);

        Message result = captor.getValue().createMessage(session);

        assertSame(textMessage, result);
        verify(session).createTextMessage("ORDER-1001");
        verify(textMessage).setStringProperty("eventType", "ORDER_CREATED");
        verify(textMessage).setIntProperty("schemaVersion", 1);
        verify(textMessage).setJMSCorrelationID("corr-1001");
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.jms.OrderPublisherTest
```

**Kết quả mong đợi:** Gradle báo `BUILD SUCCESSFUL` nếu các assertion đạt và dự án có dependency test hợp lệ. Không đưa ra stdout cố định cho mọi phiên bản Gradle/JUnit vì log phụ thuộc cấu hình. `jmsTemplate` được mock nên không gửi message; chính test gọi `createMessage(session)` trên callback đã bắt được. Với integration test, phải có broker thật hoặc môi trường JMS test phù hợp để xác minh luồng gửi/nhận.

Lợi ích của test: nó phát hiện các lỗi như hardcode sai queue, quên đặt property, đặt correlation ID sai, tạo payload không đúng, hoặc không sử dụng session mà callback được cấp. Nó không thay thế kiểm thử tương thích broker, transaction hoặc consumer.

## 10. Các lỗi thường gặp

| Dấu hiệu / cách viết | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không hiểu `session` từ đâu ra trong lambda | Nhầm callback với một method tự gọi | `JmsTemplate` sẽ gọi `createMessage(Session)` và cung cấp session |
| Cố truyền `Session` vào `jmsTemplate.send(...)` | Nhầm chữ ký API | Truyền `MessageCreator`; nhận `Session` qua tham số lambda |
| Dùng `new TextMessage(...)` | JMS message là interface/provider object | Gọi `session.createTextMessage(...)` |
| Gọi `session.close()` hoặc `commit()` trong callback | Can thiệp tài nguyên/transaction do Spring quản lý | Để template/transaction manager điều phối |
| Lưu `Session` trong field rồi dùng ở thread khác | Session không hỗ trợ dùng đồng thời và có vòng đời hữu hạn | Dùng session ngay trong callback; mỗi luồng thao tác gọi template riêng |
| Callback trả `null` | Không tạo được JMS message hợp lệ để gửi | Luôn trả một `Message` được tạo phù hợp hoặc ném exception |
| Message đúng body nhưng thiếu header/property | Dùng `convertAndSend` mà không post-process, hoặc quên setter | Chọn `MessageCreator` hay `MessagePostProcessor` theo nhu cầu |
| Chỉ gắn `JMSPriority` vào message rồi kỳ vọng QoS đã áp dụng | Nhầm message metadata với tham số gửi của producer | Cấu hình `JmsTemplate` QoS và kiểm tra `explicitQosEnabled` |
| Lỗi `JMSException` buộc phải catch trong lambda? | Bỏ qua chữ ký `MessageCreator` | Interface đã khai báo `throws JMSException`, template xử lý và chuyển đổi |
| `send` không lỗi nhưng consumer chưa xử lý | Nhầm send với xử lý nghiệp vụ bất đồng bộ | Theo dõi broker và acknowledgment/consumer riêng |
| Tên queue sai hoặc quyền thiếu | Vấn đề broker/destination ngoài callback | Xác minh broker URL, tên destination, loại queue/topic và ACL |

## 11. Câu hỏi tự kiểm tra

1. Với `jmsTemplate.send("orders.in", session -> session.createTextMessage("OK"))`, ai tạo và cung cấp `session`? Tại sao không cần gọi `new Session()`?
2. Tại sao `return message` chỉ hoàn tất callback mà chưa đủ để khẳng định consumer đã xử lý?
3. Khi đã có `String` và chỉ cần gắn một property `eventType`, bạn chọn `MessageCreator` hay `MessagePostProcessor`? Giải thích.
4. Vì sao unit test mock `Session` trong mục 9 chứng minh được callback dùng đúng factory, nhưng không chứng minh queue trên broker tồn tại?
5. Những thao tác nào trên `Session` không nên xuất hiện trong `MessageCreator`, và transaction manager ảnh hưởng thế nào?

**Ghi nhớ:** `MessageCreator` là phần mã ứng dụng cung cấp để *tạo message*; `Session` là tài nguyên JMS do `JmsTemplate` truyền vào callback. Tạo message bằng chính session đó, trả message cho template, và để template chịu trách nhiệm gửi cũng như quản lý tài nguyên.

### Tài liệu tham khảo

- Spring Framework 6.2 — Using `JmsTemplate`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Sending a Message và `MessageCreator`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — API `MessageCreator`: https://www.javadoc.io/static/org.springframework/spring-jms/6.2.13/org/springframework/jms/core/MessageCreator.html
- Jakarta Messaging 3.1 — `Session`, threading và message headers: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
