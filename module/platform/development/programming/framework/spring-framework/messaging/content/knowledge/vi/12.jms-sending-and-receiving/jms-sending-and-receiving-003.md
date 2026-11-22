# Nhận đồng bộ bằng receive và receiveAndConvert

Trong Spring JMS, ứng dụng có thể chủ động lấy một message từ queue hoặc topic bằng **JmsTemplate**. Hai cách nhận phổ biến là:

- **receive(...)** lấy nguyên đối tượng **jakarta.jms.Message** để ứng dụng tự đọc body, headers và properties.
- **receiveAndConvert(...)** nhận message rồi dùng **MessageConverter** đã cấu hình để chuyển body thành object Java.

Cả hai là thao tác nhận đồng bộ: thread gọi phương thức sẽ chờ message xuất hiện hoặc chờ hết thời gian nhận. Vì vậy, phải hiểu rõ destination, timeout, converter và acknowledgment trước khi dùng chúng trong luồng nghiệp vụ.

## 1. JmsTemplate và mô hình nhận đồng bộ

**JmsTemplate** là helper của Spring JMS, cung cấp API gửi, nhận, chuyển đổi và request/reply trên Jakarta Messaging. Nó sử dụng một **ConnectionFactory** để tạo connection/session và làm việc với destination thông qua **DestinationResolver**.

Luồng nhận đồng bộ có thể hình dung:

~~~text
Ứng dụng gọi JmsTemplate.receive(...)
             |
             v
JmsTemplate mở/nhận JMS Session
             |
             v
Tạo MessageConsumer cho destination
             |
             v
Consumer chờ message theo receiveTimeout
             |
       +-----+------+
       |            |
    Có message    Hết timeout
       |            |
       v            v
Trả Message      Trả null
       |
       v
Ứng dụng xử lý body và metadata
~~~

Các phương thức nhận thường dùng:

| Phương thức | Kết quả |
|---|---|
| **receive()** | Nhận một JMS Message từ default destination. |
| **receive(destination)** | Nhận một JMS Message từ đối tượng Destination được truyền vào. |
| **receive(destinationName)** | Nhận một JMS Message từ destination được phân giải theo tên. |
| **receiveSelected(destination, selector)** | Nhận message thỏa JMS message selector. |
| **receiveAndConvert(destination)** | Nhận message rồi chuyển body thành object bằng MessageConverter. |
| **receiveSelectedAndConvert(destination, selector)** | Lọc bằng selector, sau đó chuyển body thành object. |

Các overload không truyền destination chỉ hoạt động khi JmsTemplate đã có default destination hoặc default destination name. Nếu chưa cấu hình mặc định, hãy truyền destination rõ ràng.

## 2. receive(): lấy nguyên JMS Message

Dùng **receive(...)** khi cần kiểm soát chi tiết message nhận được. Kết quả là **jakarta.jms.Message**, vì vậy ứng dụng có thể kiểm tra loại message trước khi đọc body.

Ví dụ với TextMessage:

~~~java
Message message = jmsTemplate.receive("orders.queue");

if (message == null) {
    System.out.println("No message before timeout");
}
else if (message instanceof TextMessage textMessage) {
    String body = textMessage.getText();
    String correlationId = textMessage.getJMSCorrelationID();

    System.out.println("body=" + body);
    System.out.println("correlationId=" + correlationId);
}
else {
    throw new IllegalArgumentException(
            "Unsupported JMS message type: " + message.getClass().getName()
    );
}
~~~

Phương thức trả về **null** khi không có message trong khoảng chờ đã cấu hình. Nếu nhận được message, ứng dụng phải đọc body theo đúng subtype:

- **TextMessage:** gọi getText().
- **BytesMessage:** reset nếu cần rồi đọc bằng readBytes().
- **MapMessage:** đọc field qua getString(), getInt(), getBoolean() và các getter tương ứng.
- **StreamMessage:** đọc tuần tự bằng các read method đúng thứ tự producer đã ghi.
- **ObjectMessage:** gọi getObject() và kiểm tra kiểu object được phép.
- **Message:** có thể không có body ứng dụng; đọc headers và properties nếu cần.

Không ép kiểu mọi message thành TextMessage. Nếu producer gửi BytesMessage hoặc MapMessage, ép kiểu trực tiếp sẽ gây ClassCastException.

### Đọc headers và properties

Vì receive trả về JMS Message gốc, ứng dụng có thể đọc metadata trước hoặc sau khi đọc body:

~~~java
String messageId = message.getJMSMessageID();
String correlationId = message.getJMSCorrelationID();
Destination replyTo = message.getJMSReplyTo();
boolean redelivered = message.getJMSRedelivered();

String eventType = message.getStringProperty("eventType");
int schemaVersion = message.getIntProperty("schemaVersion");
~~~

Các JMS headers tiêu chuẩn như JMSMessageID, JMSCorrelationID, JMSReplyTo và JMSRedelivered có API getter riêng. Metadata do ứng dụng định nghĩa được đọc qua property getter với kiểu phù hợp.

## 3. receiveAndConvert(): nhận và chuyển body thành object

Dùng **receiveAndConvert(...)** khi ứng dụng muốn làm việc với payload Java thay vì tự xử lý subtype của JMS Message.

Ví dụ:

~~~java
Object payload = jmsTemplate.receiveAndConvert("orders.queue");

if (payload == null) {
    System.out.println("No message before timeout");
}
else if (payload instanceof String body) {
    System.out.println("body=" + body);
}
else {
    System.out.println("payloadType=" + payload.getClass().getName());
}
~~~

Phương thức thực hiện hai bước:

1. Gọi cơ chế receive để lấy JMS Message.
2. Gọi MessageConverter đã cấu hình để chuyển message thành object Java.

Kiểu object trả về phụ thuộc vào message subtype và converter. Với **SimpleMessageConverter** mặc định của Spring JMS, các ánh xạ thông dụng là:

| JMS message nhận được | Object trả về |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | java.util.Map |
| ObjectMessage | Serializable object chứa trong body |
| Message cơ sở không có body | Thường là null |

Vì vậy, với TextMessage chứa JSON, SimpleMessageConverter trả về String JSON. Nó không tự parse JSON thành DTO. Muốn nhận DTO, cần cấu hình converter JSON phù hợp, chẳng hạn **MappingJackson2MessageConverter** của Spring JMS.

### receiveAndConvert không nhận target class

API **JmsTemplate.receiveAndConvert(...)** trả về **Object**, không có tham số targetClass. Ứng dụng cần biết converter đang dùng để kiểm tra hoặc ép kiểu kết quả an toàn.

Ví dụ khi converter trả String:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.queue");

if (result instanceof String json) {
    OrderCreated event = objectMapper.readValue(json, OrderCreated.class);
    orderService.process(event);
}
~~~

Nếu đã cấu hình một JSON converter để trả trực tiếp OrderCreated, có thể kiểm tra kiểu trước khi dùng:

~~~java
Object result = jmsTemplate.receiveAndConvert("orders.queue");

if (result instanceof OrderCreated event) {
    orderService.process(event);
}
~~~

Không ép kiểu mù quáng nếu destination có thể chứa nhiều loại message. Hãy xác định contract của queue hoặc dùng type mapping có kiểm soát.

### Khi cần target type rõ ràng

**JmsMessagingTemplate** cung cấp API Spring Messaging có overload nhận target class, ví dụ **receiveAndConvert(destinationName, OrderCreated.class)**. API này thuộc abstraction khác với JmsTemplate; cần cấu hình message converter tương ứng cho JmsMessagingTemplate/JMS bridge.

Dù dùng API nào, converter phải biết cách chuyển payload của JMS message sang kiểu đích. Tham số class không tự biến JSON thành DTO nếu converter không hỗ trợ JSON.

## 4. receiveTimeout: giới hạn thời gian chờ

Nhận đồng bộ có thể giữ thread ở trạng thái chờ. **JmsTemplate.setReceiveTimeout(long)** cấu hình thời gian chờ theo milliseconds cho các thao tác receive.

Trong Spring Framework 6.2, các giá trị có ý nghĩa:

| Giá trị | Ý nghĩa |
|---|---|
| Số dương, ví dụ 2.000 | Chờ tối đa số milliseconds đã chỉ định. |
| **0** | Chờ vô thời hạn cho đến khi có message. Đây là mặc định của JmsTemplate. |
| Số âm, ví dụ **-1** | Kiểm tra message có sẵn ngay lập tức, không chờ. |

Ví dụ cấu hình chờ tối đa 2 giây:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000L);
~~~

Sau đó:

~~~java
Message message = jmsTemplate.receive("orders.queue");

if (message == null) {
    // Không có message trong 2 giây.
}
~~~

Nếu dùng timeout mặc định bằng 0, một lệnh receive có thể giữ thread vô thời hạn khi queue trống. Điều này thường không phù hợp với request HTTP, thread xử lý tác vụ có deadline hoặc thread pool có số lượng hữu hạn.

### Chọn timeout theo mục đích

- **Timeout hữu hạn:** phù hợp với polling có chu kỳ hoặc thao tác cần giới hạn thời gian.
- **No-wait:** phù hợp khi chỉ muốn kiểm tra nhanh queue có message sẵn hay không.
- **Indefinite wait:** chỉ nên dùng khi thread được dành riêng cho việc chờ và vòng đời của nó được quản lý rõ ràng.

Không nên dùng một vòng lặp receive vô thời hạn trong thread xử lý request web. Nếu cần consumer chạy liên tục, listener container của Spring thường phù hợp hơn.

## 5. Default destination và destination tường minh

Có hai cách xác định nơi nhận message.

### Truyền destination trong từng lần gọi

~~~java
Message message = jmsTemplate.receive("orders.queue");
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
~~~

Tên destination được DestinationResolver phân giải thành JMS Destination. Cách này rõ ràng khi một template nhận từ nhiều queue.

### Cấu hình default destination

~~~java
jmsTemplate.setDefaultDestinationName("orders.queue");

Message message = jmsTemplate.receive();
Object payload = jmsTemplate.receiveAndConvert();
~~~

Default destination phù hợp khi template chủ yếu thao tác với một queue. Nếu không có default destination mà gọi receive() không tham số, JmsTemplate không biết cần nhận từ đâu và sẽ báo lỗi cấu hình.

Có thể cấu hình default destination bằng đối tượng **jakarta.jms.Destination** thay vì tên chuỗi. Việc chọn cách nào phụ thuộc ứng dụng quản lý destination qua JNDI, cấu hình broker hay tên logical.

## 6. Nhận message có điều kiện bằng selector

JMS message selector cho phép consumer chỉ nhận message thỏa một biểu thức dựa trên JMS headers và application properties.

Ví dụ producer đặt properties:

~~~java
message.setStringProperty("eventType", "OrderCreated");
message.setIntProperty("schemaVersion", 2);
~~~

Consumer nhận message phù hợp:

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.queue",
        "eventType = 'OrderCreated' AND schemaVersion >= 2"
);
~~~

Có thể kết hợp selector với conversion:

~~~java
Object payload = jmsTemplate.receiveSelectedAndConvert(
        "orders.queue",
        "eventType = 'OrderCreated'"
);
~~~

Selector được xử lý ở phía JMS provider khi tạo consumer. Nó lọc theo headers và properties được JMS hỗ trợ; selector không parse JSON trong TextMessage hoặc truy vấn field bên trong BytesMessage.

Nếu không có message phù hợp trước timeout, kết quả vẫn là null. Message không thỏa selector không được consumer này nhận chỉ vì nó đang nằm trong cùng queue.

## 7. Ví dụ Java 17 với JmsTemplate và Artemis

Ví dụ sau gửi hai chuỗi vào queue rồi minh họa hai cách nhận:

- Lần đầu dùng receive() để lấy TextMessage và tự đọc body.
- Lần thứ hai dùng receiveAndConvert() để nhận String thông qua SimpleMessageConverter.

Ví dụ kết nối tới một Apache ActiveMQ Artemis broker đang chạy tại localhost. Queue orders.queue cần tồn tại hoặc broker phải được cấu hình tự tạo queue. Tài khoản và địa chỉ broker được truyền qua system properties.

### Maven dependencies

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>synchronous-jms-receive</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.14</spring.version>
        <artemis.version>2.57.0</artemis.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>\${spring.version}</version>
        </dependency>

        <dependency>
            <groupId>org.apache.artemis</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>\${artemis.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Java source

Tạo file src/main/java/com/example/jms/SynchronousReceiveExample.java:

~~~java
package com.example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

public class SynchronousReceiveExample {

    public static void main(String[] args) throws Exception {
        String brokerUrl = System.getProperty(
                "broker.url", "tcp://localhost:61616"
        );
        String username = System.getProperty("broker.user", "artemis");
        String password = System.getProperty("broker.password", "artemis");

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(brokerUrl, username, password);

        try {
            JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
            jmsTemplate.setReceiveTimeout(2_000L);

            // Gửi TextMessage để tạo dữ liệu thử nghiệm.
            jmsTemplate.convertAndSend("orders.queue", "ORD-1001");

            // Cách 1: nhận JMS Message gốc.
            Message rawMessage = jmsTemplate.receive("orders.queue");

            if (rawMessage == null) {
                throw new IllegalStateException("Raw receive timed out");
            }
            if (!(rawMessage instanceof TextMessage textMessage)) {
                throw new IllegalStateException(
                        "Expected TextMessage but received "
                                + rawMessage.getClass().getName()
                );
            }

            System.out.println("receive=" + textMessage.getText());

            // Gửi message thứ hai để minh họa receiveAndConvert.
            jmsTemplate.convertAndSend("orders.queue", "ORD-1002");

            // Cách 2: converter mặc định chuyển TextMessage thành String.
            Object converted = jmsTemplate.receiveAndConvert("orders.queue");

            if (!(converted instanceof String body)) {
                throw new IllegalStateException(
                        "Expected String but received "
                                + (converted == null
                                ? "null"
                                : converted.getClass().getName())
                );
            }

            System.out.println("receiveAndConvert=" + body);
        }
        finally {
            connectionFactory.close();
        }
    }
}
~~~

### Chạy chương trình

Bảo đảm broker đang hoạt động, queue đã được tạo và thông tin đăng nhập đúng. Từ thư mục chứa pom.xml, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.jms.SynchronousReceiveExample -Dbroker.url=tcp://localhost:61616 -Dbroker.user=artemis -Dbroker.password=artemis
~~~

Với queue rỗng trước khi chạy và broker nhận được hai message theo đúng thứ tự, output là:

~~~text
receive=ORD-1001
receiveAndConvert=ORD-1002
~~~

Diễn giải:

1. ActiveMQConnectionFactory kết nối tới Artemis qua Jakarta Messaging API.
2. JmsTemplate dùng ConnectionFactory đó và chờ tối đa 2.000 milliseconds cho mỗi lần nhận.
3. convertAndSend gửi String; SimpleMessageConverter tạo TextMessage.
4. receive trả về TextMessage để ứng dụng tự đọc getText().
5. receiveAndConvert nhận message tiếp theo và SimpleMessageConverter chuyển TextMessage thành String.
6. ConnectionFactory được đóng trong finally để giải phóng tài nguyên phía client.

Output phụ thuộc broker, queue và dữ liệu đang có. Nếu queue còn message cũ, consumer có thể nhận message cũ trước hai message thử nghiệm. Hãy dùng queue riêng hoặc làm sạch queue trước khi kiểm tra.

## 8. MessageConverter khi dùng receiveAndConvert

JmsTemplate mặc định sử dụng **SimpleMessageConverter**. Converter này phù hợp với các kiểu JMS cơ bản:

- TextMessage thành String.
- BytesMessage thành byte[].
- MapMessage thành Map.
- ObjectMessage thành Serializable object.

Nếu consumer cần DTO JSON, hãy cấu hình một converter JSON cho JmsTemplate. Spring JMS cung cấp **MappingJackson2MessageConverter** để chuyển giữa object Java và TextMessage hoặc BytesMessage bằng Jackson 2.

Khi cấu hình JSON converter, cần thống nhất:

- Content type và dạng body.
- Tên property chứa type ID nếu dùng type mapping.
- Mapping type ID sang các class được phép.
- Định dạng ngày giờ, enum, số tiền và chính sách field thiếu/thừa.
- Schema version giữa producer và consumer.

Không bật polymorphic deserialization tùy ý cho dữ liệu đến từ nguồn không tin cậy. Chỉ cho phép các kiểu đã được xác định trong contract.

### Conversion lỗi khác với timeout

Hai tình huống cần được phân biệt:

- **Timeout:** không có message phù hợp trước thời hạn; receiveAndConvert trả về null.
- **Conversion failure:** đã nhận message nhưng converter không thể chuyển body thành object; Spring ném exception thuộc hệ thống JmsException/conversion exception.

Không coi mọi kết quả null là lỗi JSON. Null thường biểu thị không có message được nhận trong khoảng chờ hoặc converter không có payload theo kiểu message đó; cần kiểm tra contract cụ thể.

## 9. Acknowledgment và transaction khi nhận đồng bộ

Nhận được message và xử lý xong nghiệp vụ là hai thời điểm khác nhau. Cần hiểu khi nào provider xem message đã được xác nhận.

JmsTemplate mặc định tạo session không transacted với **AUTO_ACKNOWLEDGE**. Trong chế độ này, message được acknowledge theo quy tắc JMS khi thao tác nhận hoàn tất. Ứng dụng không nên giả định rằng phần xử lý business code chạy sau lệnh receive vẫn nằm trong cùng thời điểm xác nhận.

Đặc biệt, **receiveAndConvert** thực hiện nhận message trước rồi mới chuyển đổi payload. Với AUTO_ACKNOWLEDGE, việc acknowledge có thể đã xảy ra khi receive trả về, trước khi converter hoặc business code chạy xong. Nếu conversion hoặc xử lý phía sau thất bại, message không nhất thiết được redeliver.

### setSessionTransacted(true) không bao trùm business code sau receive

JmsTemplate có thể cấu hình session transacted. Tuy nhiên, với thao tác receive đồng bộ, template quản lý transaction ngắn quanh lần nhận và hoàn tất transaction trước khi trả message cho caller. Vì vậy, việc đặt sessionTransacted=true không tự động giữ transaction mở trong lúc caller xử lý payload sau khi receive() hoặc receiveAndConvert() trả về.

Nếu cần transaction bao trùm cả việc nhận và xử lý nghiệp vụ, thường nên dùng message listener container với session transacted và **@JmsListener**, hoặc thiết kế một luồng transaction phù hợp với transaction manager của ứng dụng.

### CLIENT_ACKNOWLEDGE

Có thể cấu hình session acknowledge mode là CLIENT_ACKNOWLEDGE, nhưng JmsTemplate quản lý acknowledge trong vòng đời receive của nó. Không nên cho rằng caller có thể giữ raw Message từ receive() rồi gọi acknowledge() ở một thời điểm tùy ý để điều khiển toàn bộ business transaction.

Nếu cần quyết định commit/rollback dựa trên kết quả xử lý, hãy chọn listener container hoặc mô hình transaction hỗ trợ đúng phạm vi đó.

## 10. Khi nào nên dùng receive và khi nào nên dùng listener?

Nhận đồng bộ phù hợp khi ứng dụng chủ động lấy một message theo nhu cầu, chẳng hạn:

- Công cụ quản trị cần đọc một message để kiểm tra.
- Một job chạy định kỳ lấy một lượng message nhỏ.
- Một bước tích hợp cần chờ kết quả trong một khoảng thời gian xác định.
- Một tác vụ nền thực hiện polling có kiểm soát.

Với consumer chạy liên tục hoặc tải lớn, cân nhắc **@JmsListener** và listener container. Listener container quản lý consumer, threading, lifecycle, concurrency, transaction và recovery tốt hơn một vòng lặp tự gọi receive.

| Tiêu chí | JmsTemplate receive | @JmsListener |
|---|---|---|
| Kiểu nhận | Chủ động pull, đồng bộ. | Provider/container dispatch message đến listener. |
| Thread | Thread gọi receive bị block. | Container quản lý thread nhận message. |
| Timeout | Cấu hình qua receiveTimeout. | Container có receive/recovery settings riêng. |
| Xử lý liên tục | Cần tự tổ chức vòng lặp/polling. | Phù hợp consumer chạy dài hạn. |
| Transaction | Phạm vi của thao tác template cần được hiểu rõ. | Có thể cấu hình session transacted và transaction manager quanh listener. |
| Trường hợp phù hợp | Polling có kiểm soát, công cụ, tác vụ theo yêu cầu. | Consumer production liên tục, cần concurrency và lifecycle. |

Không nên tạo một vòng lặp vô hạn gọi receive() trên thread HTTP hoặc thread dùng chung của framework. Nếu cần chạy polling, hãy đặt nó trong scheduler hoặc worker thread có shutdown, backoff và timeout rõ ràng.

## 11. Hiệu năng và quản lý tài nguyên

Mỗi thao tác receive của JmsTemplate cần làm việc với JMS Session và MessageConsumer. Template quản lý việc đóng consumer/session/connection theo cấu hình và ConnectionFactory. Khi gọi receive liên tục với ConnectionFactory không pooling/caching, chi phí tạo và đóng tài nguyên có thể đáng kể.

Một số điểm cần cân nhắc:

- Dùng ConnectionFactory có pooling hoặc Spring CachingConnectionFactory khi phù hợp với provider và transaction model.
- Dùng một JmsTemplate đã cấu hình ổn định và chia sẻ giữa các collaborator; JmsTemplate thread-safe sau khi cấu hình.
- Đặt receiveTimeout hữu hạn để polling có thể dừng hoặc kiểm tra điều kiện shutdown.
- Không dùng quá nhiều thread cùng polling một queue nếu chưa thiết kế rõ thứ tự, cạnh tranh và throughput.
- Đo độ trễ, số lần timeout, số message nhận được và lỗi conversion.
- Với tải liên tục, đánh giá listener container thay cho polling thủ công.

Đối với topic, cần hiểu subscription semantics. Một consumer được tạo tạm thời trong mỗi lần receive không tự động trở thành durable subscription. Nếu cần nhận message khi ứng dụng offline, phải cấu hình durable subscription phù hợp với JMS provider.

## 12. Lỗi thường gặp

1. **Gọi receive() nhưng chưa cấu hình default destination.** Dùng receive(destinationName) hoặc cấu hình default destination trước.
2. **Để timeout mặc định vô thời hạn trong thread request.** Cấu hình receiveTimeout hữu hạn để tránh giữ thread không giới hạn.
3. **Không kiểm tra null.** Không có message trước timeout thì receive trả null; truy cập body ngay sẽ gây NullPointerException.
4. **Ép kiểu mọi message thành TextMessage.** Kiểm tra subtype hoặc dùng converter phù hợp.
5. **Cho rằng receiveAndConvert luôn trả DTO.** SimpleMessageConverter mặc định thường trả String, byte[], Map hoặc Serializable object tùy JMS subtype.
6. **Nhầm JSON conversion với TextMessage conversion.** TextMessage chứa String; cần JSON converter hoặc parser riêng để tạo DTO.
7. **Không hiểu selector.** Selector lọc JMS headers/properties, không truy vấn field trong JSON body.
8. **Dùng receive vô hạn trong thread pool nhỏ.** Các thread có thể bị giữ hết và làm hệ thống ngừng xử lý công việc khác.
9. **Cho rằng xử lý business sau receive vẫn nằm trong JMS transaction.** Với JmsTemplate synchronous receive, transaction/acknowledgment được quản lý trong lần gọi template; cần listener container nếu muốn transaction bao trùm listener processing.
10. **Cho rằng conversion failure luôn khiến message được gửi lại.** Với AUTO_ACKNOWLEDGE, message có thể đã được acknowledge trước khi conversion chạy.
11. **Dùng polling để thay listener consumer tải lớn.** Tạo consumer liên tục có thể làm tăng overhead; listener container phù hợp hơn cho luồng nhận liên tục.
12. **Không quản lý tài nguyên ConnectionFactory/provider.** Đóng tài nguyên do ứng dụng tạo và dùng pooling/caching theo khuyến nghị provider.

## 13. Ghi nhớ

- **receive(...)** trả về JMS Message gốc để ứng dụng tự đọc body, headers và properties.
- **receiveAndConvert(...)** dùng MessageConverter của JmsTemplate để chuyển body thành object Java.
- JmsTemplate mặc định dùng SimpleMessageConverter; TextMessage thành String, BytesMessage thành byte[], MapMessage thành Map và ObjectMessage thành Serializable object.
- **receiveTimeout** tính bằng milliseconds: giá trị dương là thời gian chờ, 0 là chờ vô thời hạn, giá trị âm là no-wait.
- Không có message trước timeout thì kết quả là null.
- **receiveSelected(...)** và **receiveSelectedAndConvert(...)** lọc message bằng JMS selector trên headers/properties.
- Với JSON DTO, cấu hình converter JSON phù hợp; không nhầm String conversion với JSON deserialization.
- Hiểu rõ acknowledgment và transaction trước khi xử lý nghiệp vụ sau khi nhận.
- Dùng @JmsListener/listener container cho consumer chạy liên tục, cần concurrency và transaction bao trùm xử lý.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [JmsTemplate Javadoc — Spring Framework 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [JmsOperations Javadoc — Spring Framework 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsOperations.html)
- [Using Spring JMS — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Apache Artemis — Jakarta Messaging client dependencies](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath)

