# SimpleMessageConverter của Spring JMS và các kiểu dữ liệu hỗ trợ

## 1. Vai trò của SimpleMessageConverter

JMS định nghĩa nhiều loại message để truyền các dạng dữ liệu khác nhau. Spring JMS cung cấp `SimpleMessageConverter` để chuyển payload Java thành loại JMS Message phù hợp và chuyển ngược lại khi nhận.

Converter này thuộc package `org.springframework.jms.support.converter`. Nó ánh xạ dựa trên kiểu Java thực tế của payload:

- `String` thành `TextMessage`.
- `byte[]` thành `BytesMessage`.
- `Map` thành `MapMessage`.
- Đối tượng `Serializable` thành `ObjectMessage`.

Khi nhận, converter đọc loại JMS Message tương ứng và trả về kiểu Java phù hợp. Cách ánh xạ này thuận tiện cho ứng dụng gửi text, byte array, map hoặc object Java có thể serialize.

Đây là converter của **Spring JMS**, làm việc với API JMS và `jakarta.jms.Message` trong Spring Framework 6 trở lên. Nó có hợp đồng khác với `org.springframework.messaging.converter.MessageConverter` của Spring Messaging.

Sau bài học, bạn cần có thể:

- Mô tả hợp đồng `MessageConverter` của Spring JMS.
- Biết kiểu Java nào được chuyển thành từng loại JMS Message.
- Hiểu giới hạn kiểu dữ liệu của MapMessage và rủi ro của ObjectMessage.
- Dùng converter với JmsTemplate và @JmsListener.
- Phân biệt body của message với JMS properties.
- Chọn converter JSON hoặc custom converter khi payload cần schema rõ ràng.
- Kiểm thử mapping, serialization và dữ liệu không hỗ trợ.

## 2. Hợp đồng MessageConverter trong Spring JMS

Interface `org.springframework.jms.support.converter.MessageConverter` có hai phương thức:

~~~java
jakarta.jms.Message toMessage(Object object, jakarta.jms.Session session)
        throws jakarta.jms.JMSException;

Object fromMessage(jakarta.jms.Message message)
        throws jakarta.jms.JMSException;
~~~

- `toMessage` nhận object Java và JMS Session để tạo một JMS Message.
- `fromMessage` nhận JMS Message và chuyển body về object Java.
- Converter có thể ném `MessageConversionException` khi không thể chuyển đổi payload hoặc message.

Khác với converter của Spring Messaging, API JMS này không nhận `MessageHeaders` làm tham số. Nó tập trung vào payload và loại JMS Message. Các JMS properties như correlation ID hoặc metadata ứng dụng thường được thiết lập riêng bằng JMS Message API hoặc `MessagePostProcessor` của JmsTemplate.

Luồng gửi:

~~~text
Java object
    |
    v
SimpleMessageConverter.toMessage(...)
    |
    v
TextMessage / BytesMessage / MapMessage / ObjectMessage
    |
    v
JMS provider và broker
~~~

Luồng nhận:

~~~text
JMS Message từ broker
    |
    v
SimpleMessageConverter.fromMessage(...)
    |
    v
String / byte[] / Map / Serializable object
    |
    v
Listener hoặc ứng dụng
~~~

## 3. Bảng ánh xạ kiểu dữ liệu

| Java payload khi gửi | JMS Message được tạo | Java object khi nhận |
|---|---|---|
| `String` | `TextMessage` | `String` |
| `byte[]` | `BytesMessage` | `byte[]` |
| `Map` với key String và value được JMS hỗ trợ | `MapMessage` | `Map<String, Object>` |
| `Serializable` | `ObjectMessage` | Đối tượng đã deserialize |
| JMS Message đã có | Có thể được chuyển tiếp trực tiếp theo implementation | Message không thuộc nhóm trên được trả về dưới dạng JMS Message |

`SimpleMessageConverter` kiểm tra kiểu payload theo các nhánh cụ thể trước khi dùng nhánh Serializable. Byte array cũng có thể serialize trong Java, nhưng được nhận diện riêng để ánh xạ thành BytesMessage.

Nếu object không thuộc các kiểu được hỗ trợ, thao tác chuyển đổi outbound thất bại với lỗi chuyển đổi. Việc một class compile thành công không đồng nghĩa nó có thể được SimpleMessageConverter chuyển thành JMS Message.

## 4. String thành TextMessage

### 4.1 Cơ chế

Khi payload là `String`, converter tạo `TextMessage` và đặt nội dung chuỗi vào body.

Phù hợp với text thuần, lệnh hoặc sự kiện dạng chuỗi, và nội dung JSON/XML khi ứng dụng chủ động truyền dưới dạng String.

Ví dụ:

~~~java
jmsTemplate.convertAndSend("orders.queue", "order.created");
~~~

Nếu dùng SimpleMessageConverter, payload String được chuyển thành TextMessage. Listener có thể nhận lại String:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    System.out.println(payload);
}
~~~

Kết quả khi message được giao thành công:

~~~text
order.created
~~~

### 4.2 JSON dạng String không tự trở thành DTO

Nếu gửi một chuỗi JSON:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "{\"orderId\":\"ORD-42\",\"status\":\"CREATED\"}");
~~~

SimpleMessageConverter tạo TextMessage chứa chuỗi JSON. Khi nhận, kết quả vẫn là String. Converter không tự parse JSON thành class Java.

Nếu listener muốn nhận DTO, cần converter JSON phù hợp hoặc chủ động parse chuỗi bằng ObjectMapper trong lớp adapter/service. Không giả định String và object JSON là cùng một kiểu payload.

## 5. byte[] thành BytesMessage

### 5.1 Cơ chế

Khi payload là `byte[]`, converter tạo `BytesMessage` và ghi các byte vào body. Khi nhận, converter đọc body thành byte array.

Phù hợp với file, ảnh, nội dung nén, payload đã mã hóa hoặc dữ liệu từ thiết bị và protocol nhị phân.

Ví dụ:

~~~java
byte[] payload = new byte[] {0, 1, 2, (byte) 255};
jmsTemplate.convertAndSend("files.queue", payload);
~~~

Listener nhận byte array:

~~~java
@JmsListener(destination = "files.queue")
public void receive(byte[] content) {
    System.out.println("Received bytes: " + content.length);
}
~~~

Với payload trên, số byte nhận được là:

~~~text
Received bytes: 4
~~~

Byte array là dữ liệu nhị phân. Không chuyển nó thành String chỉ để gửi qua TextMessage nếu chưa có quy ước encoding rõ ràng. Nếu cần truyền text ở dạng byte, hai phía phải thống nhất charset, thường là UTF-8. Nếu payload là file hoặc binary protocol, giữ nguyên byte[].

Cần giới hạn kích thước message. Payload lớn có thể gây áp lực bộ nhớ ở ứng dụng và broker; cân nhắc truyền tham chiếu tới object storage nếu file quá lớn.

## 6. Map thành MapMessage

### 6.1 Cơ chế

Khi payload là Java `Map`, SimpleMessageConverter tạo `MapMessage`. Mỗi entry được ghi thành một trường trong body.

~~~java
import java.util.Map;

Map<String, Object> event = Map.of(
        "orderId", "ORD-42",
        "attempt", 2,
        "confirmed", true
);

jmsTemplate.convertAndSend("orders.queue", event);
~~~

Listener có thể nhận Map:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(Map<String, Object> event) {
    System.out.println(event.get("orderId"));
    System.out.println(event.get("attempt"));
}
~~~

Kết quả:

~~~text
ORD-42
2
~~~

### 6.2 Giới hạn kiểu dữ liệu trong MapMessage

MapMessage không phải một Java object graph tổng quát. JMS quy định các kiểu dữ liệu được hỗ trợ cho từng entry, gồm:

- Boolean và các kiểu số: byte, short, int, long, float, double.
- `char`.
- `String`.
- `byte[]`.

Key của MapMessage là String. Giá trị phải thuộc kiểu JMS hỗ trợ; không thể đưa tùy ý DTO, Map lồng nhau hoặc object không thuộc tập kiểu được JMS cho phép rồi kỳ vọng provider serialize chúng như Java object.

Nếu cần truyền cấu trúc lồng nhau hoặc schema phức tạp, hãy dùng JSON, Avro, Protobuf hoặc format có schema rõ ràng thay vì ép cấu trúc đó vào MapMessage.

### 6.3 MapMessage body và JMS properties

Các entry trong MapMessage thuộc body của message. Chúng khác với JMS properties, vốn là metadata có thể dùng cho selector hoặc định tuyến theo khả năng broker.

Ví dụ, `orderId` trong MapMessage body không tự động trở thành JMS property tên `orderId`. Nếu cần selector theo event type hoặc tenant, hãy thiết lập JMS property riêng và xác minh broker hỗ trợ kiểu property cần dùng.

## 7. Serializable thành ObjectMessage

### 7.1 Cơ chế

Nếu payload không phải String, byte[] hoặc Map nhưng implement `java.io.Serializable`, SimpleMessageConverter tạo `ObjectMessage`.

Ví dụ DTO:

~~~java
import java.io.Serializable;

public record OrderNotice(
        String orderId,
        String status
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Gửi object:

~~~java
OrderNotice notice = new OrderNotice("ORD-42", "CREATED");
jmsTemplate.convertAndSend("orders.queue", notice);
~~~

Converter tạo ObjectMessage chứa object đã serialize. Khi nhận, nó deserialize và trả về object tương ứng nếu class cần thiết có sẵn và dữ liệu có thể được đọc.

### 7.2 Serializable không có nghĩa mọi object đều serialize được

Một class implement Serializable nhưng chứa field tham chiếu tới object không serialize được vẫn có thể thất bại khi serialize. Tính serializable phải áp dụng cho toàn bộ object graph được ghi vào stream, trừ các field được xử lý riêng như transient hoặc custom serialization.

Thay đổi class giữa các lần deploy cũng có thể gây lỗi tương thích khi deserialize message cũ. `serialVersionUID` giúp kiểm soát một phần compatibility check nhưng không tự bảo đảm schema evolution an toàn.

### 7.3 Rủi ro bảo mật của ObjectMessage

ObjectMessage dựa trên Java serialization. Deserialization dữ liệu không đáng tin cậy có thể mở ra rủi ro thực thi hành vi ngoài dự kiến thông qua class trong classpath.

Vì vậy:

- Tránh nhận ObjectMessage từ nguồn không tin cậy.
- Giới hạn các class được phép deserialize bằng cơ chế filter/allow-list phù hợp với JDK và provider.
- Kiểm soát quyền publish vào destination.
- Có kế hoạch tương thích class khi nâng cấp ứng dụng.
- Cân nhắc JSON, Avro hoặc Protobuf cho message cần trao đổi giữa nhiều ngôn ngữ hoặc nhiều phiên bản dịch vụ.

ObjectMessage có thể tiện cho hệ thống Java được kiểm soát chặt, nhưng tạo coupling vào class Java và cơ chế serialization của Java.

## 8. Cấu hình SimpleMessageConverter với JmsTemplate

`JmsTemplate` dùng MessageConverter cho các phương thức như `convertAndSend` và `receiveAndConvert`. Spring JMS thường sử dụng SimpleMessageConverter làm converter mặc định; có thể cấu hình tường minh để hành vi dễ nhận biết.

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.SimpleMessageConverter;

@Configuration
public class JmsTemplateConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(new SimpleMessageConverter());
        return template;
    }
}
~~~

Ví dụ này cần một ConnectionFactory bean do JMS provider hoặc cấu hình Spring Boot/JNDI cung cấp.

Các phương thức thường dùng:

- `convertAndSend(destination, object)`: chuyển object thành JMS Message rồi gửi.
- `convertAndSend(destination, object, messagePostProcessor)`: chuyển object rồi cho phép bổ sung JMS headers/properties.
- `receiveAndConvert(destination)`: nhận JMS Message và chuyển body thành object Java.
- `receiveSelectedAndConvert(destination, selector)`: nhận message theo selector rồi chuyển đổi, nếu API và cấu hình đang dùng hỗ trợ.

`send` và `receive` làm việc với JMS Message trực tiếp; các biến thể `convert...` sử dụng converter.

## 9. Dùng converter với @JmsListener

Listener container cũng cần MessageConverter để chuyển JMS Message thành tham số method. Có thể cấu hình qua `DefaultJmsListenerContainerFactory`:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.SimpleMessageConverter;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(new SimpleMessageConverter());
        return factory;
    }
}
~~~

Listener nhận kiểu tương ứng:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderTextListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void receive(String payload) {
        // Xử lý text payload.
    }
}
~~~

Nếu producer gửi String, tham số String phù hợp. Nếu producer gửi byte[], Map hoặc ObjectMessage, method cần kiểu nhận tương ứng hoặc nhận JMS Message để tự xử lý.

Hãy bảo đảm producer và consumer thống nhất kiểu dữ liệu. Một method nhận DTO không thể tự động nhận TextMessage chứa JSON chỉ vì JSON có các trường giống DTO.

## 10. Bổ sung JMS properties bằng MessagePostProcessor

SimpleMessageConverter chuyển payload thành body. Nếu cần metadata như correlation ID, event type hoặc tenant identifier ở JMS properties, hãy bổ sung riêng bằng `MessagePostProcessor`.

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "order.created",
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setStringProperty("correlationId", "corr-42");
            return message;
        }
);
~~~

Trong ví dụ, body vẫn là TextMessage chứa `order.created`. Hai giá trị `eventType` và `correlationId` là JMS properties.

JMS properties thường có thể dùng trong message selector, nhưng kiểu property bị giới hạn theo JMS và provider. Không đưa password, token hoặc dữ liệu nhạy cảm vào properties; chúng có thể được log, truy vấn hoặc hiển thị qua công cụ quản trị broker.

## 11. Khi nào nên dùng converter khác?

SimpleMessageConverter phù hợp với các kiểu payload cơ bản. Hãy cân nhắc converter chuyên biệt khi:

- Cần DTO JSON thay vì ObjectMessage.
- Cần schema evolution giữa nhiều phiên bản producer/consumer.
- Cần giao tiếp giữa Java và ngôn ngữ khác.
- Payload có cấu trúc lồng nhau hoặc dữ liệu phức tạp.
- Cần kiểm soát type metadata và mapping field.
- Cần serializer có schema như Avro hoặc Protobuf.

Spring JMS cung cấp lựa chọn như `MappingJackson2MessageConverter` cho JSON khi có dependency Jackson phù hợp. Có thể cấu hình target message type, type ID property và mapper theo hợp đồng ứng dụng.

Ví dụ khái quát:

~~~java
MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

// Cấu hình type metadata và message type theo hợp đồng JSON.
// Đăng ký converter vào JmsTemplate hoặc listener factory.
~~~

Đây là đoạn minh họa cách chọn converter, không phải cấu hình hoàn chỉnh cho mọi phiên bản. API cụ thể và cách ánh xạ type ID cần được đối chiếu với phiên bản Spring JMS/Jackson đang dùng.

Nếu hệ thống cần kiểm soát format chặt chẽ, có thể tự implement `MessageConverter` để quyết định cách serialize, deserialize, đặt properties và kiểm tra schema.

## 12. Xử lý kiểu dữ liệu không được hỗ trợ

Khi outbound payload không thuộc các kiểu hỗ trợ, SimpleMessageConverter không thể tự đoán cách serialize. Ví dụ:

~~~java
public class NonSerializableOrder {
    private String orderId;
}
~~~

Nếu gửi object này trực tiếp:

~~~java
jmsTemplate.convertAndSend("orders.queue", new NonSerializableOrder());
~~~

thao tác chuyển đổi thất bại vì class không phải String, byte[], Map hoặc Serializable. Hãy chuyển object thành format được hỗ trợ hoặc cấu hình converter chuyên biệt.

Khi inbound message là loại JMS Message không được SimpleMessageConverter ánh xạ sang object cụ thể, converter có thể trả lại chính Message để caller xử lý trực tiếp. Vì vậy, code nhận nên biết rõ hợp đồng destination và kiểu message dự kiến.

Không bắt lỗi chuyển đổi rồi bỏ qua message âm thầm. Ghi nhận destination, message ID hoặc correlation ID phù hợp, phân loại lỗi dữ liệu và áp dụng error handling/dead-letter theo cấu hình broker.

## 13. Kiểm thử SimpleMessageConverter

Nên kiểm thử cả hai chiều chuyển đổi:

| Trường hợp | Điều cần xác minh |
|---|---|
| String | Tạo TextMessage và nhận lại String giống nội dung gốc |
| byte[] | Tạo BytesMessage và giữ nguyên toàn bộ byte |
| Map | Tạo MapMessage; key và value thuộc kiểu JMS hỗ trợ |
| Serializable | Tạo ObjectMessage và deserialize được class tương ứng |
| Object không hỗ trợ | Chuyển đổi outbound thất bại rõ ràng |
| JMS Message khác | Hành vi fallback được xử lý theo hợp đồng |
| JMS properties | Metadata được thiết lập riêng và đọc lại đúng |
| Listener | Tham số method khớp với kiểu payload sau conversion |

Unit test converter có thể dùng JMS Session mock hoặc test support thích hợp. Integration test nên dùng broker thực tế hoặc Testcontainers để xác minh provider hỗ trợ message type, serialization, persistence và redelivery như mong đợi.

Đối với ObjectMessage, cần test cả tình huống consumer dùng class version khác producer. Đối với MapMessage, test kiểu value không hợp lệ. Đối với byte[], dùng assertArrayEquals để xác minh byte không thay đổi.

## 14. Các lỗi thường gặp

- **Cho rằng mọi POJO đều được hỗ trợ:** chỉ object Serializable mới đi theo nhánh ObjectMessage; POJO thông thường có thể bị từ chối.
- **Nghĩ String JSON tự thành DTO:** SimpleMessageConverter trả về String; cần JSON converter để deserialize thành object.
- **Đưa nested object vào MapMessage:** body MapMessage chỉ hỗ trợ các kiểu được JMS quy định.
- **Dùng ObjectMessage cho dữ liệu không tin cậy:** Java deserialization có rủi ro bảo mật.
- **Không kiểm tra compatibility của Serializable class:** message tồn đọng có thể được đọc bởi phiên bản ứng dụng mới và thất bại.
- **Nhầm MapMessage body với JMS properties:** hai vùng dữ liệu có mục đích và API khác nhau.
- **Nhầm JMS MessageConverter với Spring Messaging MessageConverter:** hai interface nằm ở package và ranh giới khác nhau.
- **Cho rằng converter tự đặt correlation ID:** metadata cần được thiết lập riêng bằng JMS properties hoặc message post processor.
- **Không cấu hình listener factory:** JmsTemplate có converter đúng nhưng listener có thể dùng converter khác.
- **Gửi payload quá lớn:** message body có thể gây áp lực bộ nhớ và giới hạn broker.
- **Bỏ qua lỗi conversion:** consumer có thể liên tục nhận lại message lỗi nếu transaction rollback mà không có error policy.

## 15. Checklist lựa chọn và vận hành

Trước khi dùng SimpleMessageConverter, hãy kiểm tra:

- Payload là String, byte[], Map hay Serializable?
- Kiểu JMS Message được tạo có đúng với consumer mong đợi không?
- Map có String key và value thuộc kiểu JMS hỗ trợ không?
- ObjectMessage có thật sự cần thiết và nguồn gửi có đáng tin cậy không?
- Producer và consumer có class/schema tương thích không?
- JSON cần được deserialize thành DTO bằng converter chuyên biệt chưa?
- JmsTemplate và listener factory đã dùng converter thống nhất chưa?
- JMS properties như correlation ID và event type đã được đặt riêng chưa?
- Có xử lý lỗi cho payload không hỗ trợ hoặc deserialize thất bại không?
- Có integration test với provider/broker thực tế không?

Khi hiểu rõ ánh xạ giữa Java payload và JMS Message, bạn có thể dùng SimpleMessageConverter đúng phạm vi, tránh nhầm lẫn giữa text, binary, map và serialized object, đồng thời chọn serializer có schema rõ ràng khi ứng dụng cần tương thích lâu dài.