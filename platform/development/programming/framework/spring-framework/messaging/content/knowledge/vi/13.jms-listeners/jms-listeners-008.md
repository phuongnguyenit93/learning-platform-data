# Phản hồi từ listener bằng giá trị trả về và @SendTo trong Spring JMS

## 1. Từ listener một chiều đến request-reply

Một method gắn `@JmsListener` thường được dùng để nhận message và thực hiện xử lý nghiệp vụ. Method có thể khai báo kiểu trả về `void` nếu chỉ cần xử lý message. Khi method trả về một giá trị, Spring JMS có thể đóng gói giá trị đó thành JMS message và gửi phản hồi tới một destination.

Spring hỗ trợ ba cách xác định nơi gửi phản hồi:

- **`JMSReplyTo` trên request:** destination do bên gửi yêu cầu chỉ định cho từng message. Nếu header này có mặt, listener adapter gửi reply tới destination đó.
- **`@SendTo`:** destination mặc định được khai báo trên method hoặc class listener. Spring dùng destination này khi request không có `JMSReplyTo`.
- **`JmsResponse<T>`:** kết quả bao gồm payload phản hồi và destination được chọn tại runtime. Cách này phù hợp khi destination phụ thuộc nội dung request hoặc kết quả xử lý.

Điều này giúp listener tập trung vào xử lý request và tạo kết quả. Spring JMS quản lý việc chuyển kết quả thành JMS message và gửi tới destination đã xác định.

Sau bài học, bạn cần có thể:

- Phân biệt listener một chiều với listener có reply.
- Dùng kiểu trả về khác void để tạo phản hồi.
- Chọn destination qua JMSReplyTo hoặc @SendTo.
- Dùng JmsResponse khi cần chọn destination động.
- Trả về Spring Message để bổ sung header cho phản hồi.
- Cấu hình converter và QoS cho reply.
- Kết hợp listener reply với JmsTemplate request-reply.
- Xử lý timeout, lỗi gửi reply, correlation và bảo mật destination.

## 2. Cơ chế xử lý giá trị trả về

Spring JMS dùng hạ tầng listener adapter để gọi method được đánh dấu `@JmsListener`. Khi method trả về một object, adapter chuyển object đó thành `jakarta.jms.Message` bằng `MessageConverter` đã cấu hình, sau đó gửi message tới response destination.

Luồng tổng quát:

~~~text
Request producer
      |
      | JMS Message
      | có thể kèm JMSReplyTo
      v
Request destination / queue
      |
      v
Spring JMS listener container
      |
      v
@JmsListener method
      |
      | trả về object
      v
MessageConverter
      |
      v
JMS reply message
      |
      v
JMSReplyTo hoặc destination mặc định từ @SendTo
      |
      v
Reply consumer
~~~

Cần phân biệt hai nhiệm vụ:

- Method listener tạo **kết quả nghiệp vụ**.
- Listener adapter thực hiện **vận chuyển phản hồi** qua JMS.

Nếu method trả về `void`, Spring không có giá trị trả về để tự động gửi reply. Nếu method có kiểu trả về khác void, hãy cấu hình destination phù hợp để phản hồi có nơi đến rõ ràng.

Cơ chế này thuộc Spring JMS. Annotation `@SendTo` được tái sử dụng từ package `org.springframework.messaging.handler.annotation`, nhưng ở đây nó cấu hình response destination cho JMS listener.

## 3. @SendTo: destination phản hồi mặc định

### 3.1 Ví dụ cơ bản

`@SendTo` khai báo destination mặc định cho kết quả trả về:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class OrderRequestListener {

    private final OrderService orderService;

    public OrderRequestListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(destination = "orders.request")
    @SendTo("orders.reply")
    public OrderStatus process(OrderCommand command) {
        return orderService.process(command);
    }
}
~~~

`OrderCommand`, `OrderStatus` và `OrderService` là các kiểu thuộc ứng dụng. Listener nhận command từ `orders.request`, gọi service và trả về trạng thái. Spring chuyển kết quả thành JMS message rồi gửi tới `orders.reply` nếu request không cung cấp `JMSReplyTo`.

Ví dụ này cần:

- `@EnableJms` để bật annotation-driven listener infrastructure.
- Một `ConnectionFactory` hợp lệ.
- Listener container factory phù hợp.
- MessageConverter có khả năng chuyển đổi kiểu request và response.
- Queue hoặc destination có quyền truy cập theo cấu hình broker.

### 3.2 @SendTo là default destination

Nếu request có header `JMSReplyTo`, Spring gửi phản hồi tới destination được chỉ định trong header đó. `@SendTo` được dùng làm destination mặc định khi request không có `JMSReplyTo`.

Có thể hiểu thứ tự lựa chọn:

1. Request có `JMSReplyTo`: gửi reply tới destination đó.
2. Request không có `JMSReplyTo` nhưng listener có `@SendTo`: dùng destination từ `@SendTo`.
3. Không có destination phản hồi được cấu hình: ứng dụng chưa xác định được nơi gửi reply; cần bổ sung route rõ ràng nếu muốn dùng automatic reply.

Vì vậy, `@SendTo` không ép mọi request phải nhận phản hồi ở cùng một queue. Bên gửi có thể chỉ định destination riêng theo từng request bằng `JMSReplyTo`.

### 3.3 Đặt @SendTo ở cấp class

Nếu nhiều method listener cùng dùng một response destination mặc định, có thể đặt `@SendTo` ở class:

~~~java
@Component
@SendTo("orders.reply")
public class OrderListenerGroup {

    @JmsListener(destination = "orders.create")
    public OrderStatus create(CreateOrder command) {
        return createOrder(command);
    }

    @JmsListener(destination = "orders.cancel")
    public CancelStatus cancel(CancelOrder command) {
        return cancelOrder(command);
    }
}
~~~

Class-level annotation cung cấp default reply destination cho các listener method trong class. Nếu một method cần destination mặc định riêng, có thể khai báo `@SendTo` ở method đó để thể hiện rõ hợp đồng của method.

## 4. JMSReplyTo: destination do bên gửi yêu cầu chọn

### 4.1 Ý nghĩa của JMSReplyTo

`JMSReplyTo` là header chuẩn của JMS, chứa một `Destination` mà consumer có thể dùng để gửi phản hồi. Header này thuộc request message; nó không phải tên queue dạng text đơn thuần trong mọi trường hợp.

Bên gửi có thể chỉ định reply destination khi tạo request. Listener adapter đọc header này và dùng destination đó cho kết quả trả về.

Mô hình:

~~~text
Client                         Listener
  |                                |
  | Request                        |
  | JMSReplyTo = reply destination |
  |------------------------------->|
  |                                | xử lý
  |                                |
  |<-------------------------------|
  | Reply tới JMSReplyTo            |
~~~

Điểm mạnh của cách này là một listener có thể phục vụ nhiều caller, mỗi caller có reply destination riêng. Listener không cần hard-code queue phản hồi của từng client.

### 4.2 JmsTemplate tự tạo temporary reply queue

`JmsTemplate` cung cấp thao tác request-reply `sendAndReceive`. Trong thao tác này, Spring tạo một `TemporaryQueue` cho request, đặt queue đó vào `JMSReplyTo` rồi chờ phản hồi trên queue tạm.

Khi dùng biến thể convert, caller có thể làm việc với object Java:

~~~java
import org.springframework.jms.core.JmsTemplate;

public class OrderRequestClient {

    private final JmsTemplate jmsTemplate;

    public OrderRequestClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public String requestStatus(String orderId) {
        Object reply = jmsTemplate.convertSendAndReceive(
                "orders.request",
                orderId
        );

        if (reply == null) {
            throw new IllegalStateException("No reply received in time");
        }

        return (String) reply;
    }
}
~~~

Ví dụ dùng String để phù hợp với converter mặc định phổ biến của Spring JMS. Nếu request hoặc reply là DTO, hãy cấu hình MessageConverter tương thích, chẳng hạn converter JSON, ở cả phía gửi và listener.

Có thể cấu hình `receiveTimeout` trên JmsTemplate để giới hạn thời gian caller chờ phản hồi. Giá trị timeout hết hạn có thể khiến phương thức trả về null. Việc caller ngừng chờ không tự hủy công việc mà listener đã nhận.

### 4.3 Temporary destination và destination dùng chung

Temporary reply queue thuận tiện cho request-reply đồng bộ vì mỗi thao tác có một destination tạm do Spring quản lý. Nó phù hợp với caller đang chờ một phản hồi trong thời gian hữu hạn.

Nếu dùng một reply queue cố định cho nhiều request đồng thời, cần cơ chế phân biệt reply thuộc request nào. `JMSCorrelationID` thường được dùng để liên kết response với request. Caller cần kiểm tra correlation theo hợp đồng đã thiết kế; không nhận reply chỉ dựa vào việc nó xuất hiện trên cùng queue.

Temporary destination cũng có vòng đời gắn với connection/session và provider. Không xem nó là nơi lưu kết quả lâu dài để client truy vấn sau khi timeout hoặc restart.

## 5. Chọn response destination tại runtime bằng JmsResponse

### 5.1 Khi nào cần destination động?

`@SendTo` phù hợp khi một listener có một destination mặc định ổn định. Nếu nơi nhận phản hồi phụ thuộc vào tenant, loại request, vùng xử lý hoặc kết quả nghiệp vụ, cần chọn destination tại runtime.

Spring JMS cung cấp `JmsResponse<T>` trong package `org.springframework.jms.listener.adapter`. Đối tượng này đóng gói response payload cùng destination đích.

Ví dụ:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.listener.adapter.JmsResponse;
import org.springframework.stereotype.Component;

@Component
public class RegionalOrderListener {

    @JmsListener(destination = "orders.request")
    public JmsResponse<OrderStatus> process(OrderCommand command) {
        OrderStatus status = processOrder(command);

        String destination = "orders.reply." + command.region();

        return JmsResponse.forQueue(status, destination);
    }
}
~~~

`JmsResponse.forQueue` tạo response hướng tới queue có tên được cung cấp. Nếu cần gửi tới topic, API có biến thể `forTopic`. Destination có thể được quyết định dựa trên dữ liệu request hoặc kết quả xử lý.

### 5.2 Kiểm soát destination được phép

Destination động cần được kiểm soát. Không ghép tùy tiện một chuỗi do client gửi trực tiếp thành tên queue/topic. Nếu làm vậy, client có thể khiến ứng dụng gửi response tới destination ngoài phạm vi được phép.

Nên ánh xạ dữ liệu request qua danh sách destination đã được cấu hình hoặc một resolver có kiểm tra quyền. Ví dụ, chỉ chấp nhận các region code thuộc danh sách hợp lệ và tạo destination từ cấu hình đã được kiểm soát.

Cũng cần bảo đảm broker cấp quyền send cho connection của listener trên các destination mà ứng dụng được phép dùng.

### 5.3 JmsResponse và @SendTo

Hai cách có mục đích khác nhau:

| Cách | Khi nào dùng |
|---|---|
| `@SendTo("orders.reply")` | Destination mặc định cố định, khai báo rõ trên listener |
| `JmsResponse.forQueue(payload, name)` | Destination queue được quyết định khi xử lý request |
| `JmsResponse.forTopic(payload, name)` | Destination topic được quyết định khi xử lý request |
| `JMSReplyTo` | Bên gửi request chỉ định destination phản hồi cho từng message |

Khi cần một response route động theo nghiệp vụ, JmsResponse làm rõ destination cùng payload trong giá trị trả về của method.

## 6. Trả về Spring Message để bổ sung header

Listener có thể trả về `org.springframework.messaging.Message<T>` thay vì chỉ trả payload. Cách này cho phép bổ sung metadata theo abstraction messaging trước khi adapter chuyển thành JMS Message.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.support.MessageBuilder;

@JmsListener(destination = "orders.request")
@SendTo("orders.reply")
public Message<OrderStatus> process(OrderCommand command) {
    OrderStatus status = processOrder(command);

    return MessageBuilder
            .withPayload(status)
            .setHeader("app.responseCode", "OK")
            .setHeader("app.schemaVersion", 1)
            .build();
}
~~~

Các header trong Spring Message là metadata ở tầng Spring. Adapter ánh xạ chúng theo cơ chế JMS message conversion và header mapping. Hãy kiểm tra kết quả thực tế nếu cần một JMS property cụ thể để consumer dùng trong selector hoặc công cụ quản trị broker.

Không đưa password, token hoặc thông tin bí mật vào header phản hồi. Metadata được truyền qua broker có thể xuất hiện trong log hoặc công cụ vận hành.

Nếu chỉ cần gửi một DTO đơn giản, trả DTO trực tiếp sẽ dễ đọc hơn. Chỉ trả Spring Message khi thực sự cần metadata bổ sung.

## 7. Chuyển đổi response thành JMS Message

Giá trị trả về của listener phải được chuyển thành loại JMS Message mà provider hỗ trợ. Listener container factory có thể cấu hình `MessageConverter` cho cả việc đọc request và tạo reply.

Ví dụ với converter JSON:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(new MappingJackson2MessageConverter());

        return factory;
    }
}
~~~

Đây là cấu hình minh họa cho Spring JMS với dependency Jackson phù hợp. Hãy cấu hình type mapping và content type theo hợp đồng message của ứng dụng, đặc biệt khi producer và consumer chạy các phiên bản khác nhau.

Nếu dùng SimpleMessageConverter mặc định:

- String thường được chuyển thành TextMessage.
- byte[] được chuyển thành BytesMessage.
- Map với các giá trị JMS hỗ trợ được chuyển thành MapMessage.
- Object Serializable có thể được chuyển thành ObjectMessage.

Một DTO không Serializable không tự động được SimpleMessageConverter chuyển thành JMS Message. Với DTO, nên dùng JSON hoặc converter có schema rõ ràng.

Cần bảo đảm converter tương thích ở hai chiều: request phải được chuyển thành kiểu tham số listener, và response phải được chuyển thành kiểu JMS Message mà caller có thể đọc.

## 8. Cấu hình Quality of Service cho reply

Spring cho phép cấu hình QoS riêng cho phản hồi của listener container thông qua `setReplyQosSettings` trên `DefaultJmsListenerContainerFactory`.

Các giá trị có thể cấu hình gồm:

- **Priority:** mức ưu tiên của response.
- **Time to live:** thời gian phản hồi còn hiệu lực.
- **Delivery mode:** chế độ giao nhận theo cấu hình QoS và khả năng provider.

Ví dụ:

~~~java
import org.springframework.jms.support.QosSettings;

QosSettings replyQos = new QosSettings();
replyQos.setPriority(2);
replyQos.setTimeToLive(10_000L);

factory.setReplyQosSettings(replyQos);
~~~

Đoạn cấu hình này được thêm vào factory tạo listener container. TTL 10.000 milliseconds nghĩa là reply có thời gian sống 10 giây theo QoS đã cấu hình. Nếu reply đến sau khi hết TTL, broker có thể loại bỏ message theo semantics của provider.

QoS response không thay thế timeout chờ reply ở caller. Caller có thể timeout trước khi TTL hết hạn; ngược lại, reply có thể hết hạn trước khi caller kịp nhận. Hai chính sách cần được thiết kế cùng nhau.

## 9. Kết hợp listener reply và JmsTemplate

Một luồng request-reply hoàn chỉnh có thể dùng JmsTemplate ở phía client và @JmsListener ở phía server.

Listener:

~~~java
@Component
public class PriceListener {

    @JmsListener(destination = "price.request")
    @SendTo("price.reply")
    public String quote(String productCode) {
        return "PRICE:" + productCode + ":100";
    }
}
~~~

Client dùng request-reply:

~~~java
public String getQuote(JmsTemplate jmsTemplate, String productCode) {
    Object reply = jmsTemplate.convertSendAndReceive(
            "price.request",
            productCode
    );

    if (reply == null) {
        throw new IllegalStateException("Price service did not reply");
    }

    return (String) reply;
}
~~~

Trong ví dụ này, JmsTemplate tạo temporary reply queue và đặt nó vào JMSReplyTo của request. Vì vậy, response được gửi tới queue tạm đó; @SendTo("price.reply") chỉ là destination mặc định khi request không có JMSReplyTo.

Để dùng destination cố định `price.reply`, caller có thể gửi request thông thường và tự tạo consumer trên reply queue theo hợp đồng ứng dụng. Khi có nhiều request đồng thời, cần correlation ID để ghép đúng response với request. Không dùng một reply queue dùng chung mà không có cơ chế tương quan.

## 10. Xử lý timeout, lỗi và phản hồi đến muộn

Request-reply đồng bộ khiến caller chờ response. Cần đặt receive timeout phù hợp và xử lý trường hợp không có reply.

Các tình huống cần phân biệt:

- Listener chưa nhận được request.
- Listener đã nhận nhưng xử lý lâu.
- Listener xử lý xong nhưng gửi reply thất bại.
- Reply đã được gửi nhưng caller hết thời gian chờ.
- Reply bị broker loại bỏ do TTL.
- Converter không thể tạo hoặc đọc response.
- Caller nhận response nhưng correlation không khớp request đang chờ.

Timeout phía caller không tự hủy method listener. Nếu listener tiếp tục xử lý sau khi caller timeout, response có thể tới một temporary destination đã hết vòng đời hoặc không còn consumer. Với temporary queue, caller không có nơi lưu trữ lâu dài để truy vấn lại kết quả.

Với tác vụ dài, nên cân nhắc mô hình bất đồng bộ:

1. Caller gửi command có request ID.
2. Hệ thống trả trạng thái accepted hoặc pending.
3. Worker xử lý độc lập.
4. Kết quả được lưu hoặc phát thành event.
5. Caller nhận event khi online hoặc truy vấn kết quả bằng request ID.

Cách này phù hợp hơn khi thời gian xử lý không dự đoán được hoặc caller không thể giữ kết nối chờ lâu.

## 11. Correlation ID và ghép request với response

Khi dùng temporary reply queue riêng cho mỗi request, destination đã giúp giới hạn nơi nhận. Khi dùng reply queue chung cho nhiều request, correlation trở nên quan trọng.

`JMSCorrelationID` có thể được dùng để liên kết response với request. Một hợp đồng phổ biến là response mang correlation ID tham chiếu tới request ID hoặc JMSMessageID của request. Cả producer và consumer phải thống nhất quy tắc này.

Các nguyên tắc:

- Dùng một request ID ổn định cho mỗi thao tác logic.
- Không tạo ID mới cho cùng một thao tác khi retry.
- Xác minh correlation ID trước khi hoàn tất một future hoặc promise đang chờ.
- Xử lý reply không có correlation ID hoặc có ID không tồn tại.
- Có thời hạn lưu trạng thái request đang chờ và dọn dẹp khi timeout.
- Không dùng correlation ID làm token xác thực hoặc bằng chứng quyền truy cập.

Đối với request-reply dùng API tích hợp sẵn của JmsTemplate, hãy để API quản lý temporary reply queue. Nếu tự triển khai shared reply queue, cần thiết kế consumer, selector và lifecycle correlation rõ ràng.

## 12. Transaction và tính đúng đắn của phản hồi

Listener có thể chạy trong JMS session transaction tùy cấu hình container. Tuy nhiên, không nên suy luận rằng việc method trả về response tự bảo đảm toàn bộ nghiệp vụ và các hệ thống liên quan commit nguyên tử.

Cần xác định:

- Khi listener xử lý thành công, thời điểm acknowledge request là khi nào?
- Nếu gửi reply thất bại, request có rollback và được redeliver không?
- Nếu cập nhật database thành công nhưng gửi reply thất bại, retry có gây tác dụng phụ lặp không?
- Response có cần được phát bền vững qua broker không?
- Có cần outbox/inbox hoặc idempotency để bảo đảm kết quả nhất quán không?

Với nghiệp vụ có tác dụng phụ như thanh toán hoặc tạo đơn, hãy thiết kế service idempotent. Việc gửi reply và việc commit database có thể thuộc các transaction khác nhau nếu không cấu hình cơ chế phối hợp phù hợp.

## 13. Bảo mật response destination

Destination trong JMSReplyTo có thể do bên gửi request cung cấp. Ứng dụng cần kiểm soát destination mà listener được phép gửi phản hồi.

Không nên mặc định tin mọi destination do client gửi lên. Hãy cân nhắc:

- Broker authorization cho quyền send vào queue/topic.
- Chỉ chấp nhận destination nằm trong phạm vi ứng dụng.
- Dùng destination resolver hoặc allow-list nếu cần kiểm tra.
- Không cho phép client điều khiển destination nội bộ tùy ý.
- Kiểm tra quyền đọc reply destination của caller.
- Không để response chứa dữ liệu nhạy cảm ngoài quyền của người gọi.

Khi dùng JmsResponse để chọn destination động, áp dụng cùng nguyên tắc allow-list và phân quyền.

## 14. Các lỗi thường gặp

- **Trả về object nhưng không có reply destination:** listener không có route rõ ràng để gửi phản hồi.
- **Nghĩ @SendTo luôn ghi đè JMSReplyTo:** JMSReplyTo trên request được ưu tiên; @SendTo là default.
- **Dùng @SendTo cho destination thay đổi theo request:** dùng JmsResponse nếu cần chọn destination runtime.
- **Nhầm destination phản hồi với destination request:** @JmsListener(destination=...) là nơi nhận request; @SendTo là default nơi gửi reply.
- **Method trả void nhưng mong có reply tự động:** không có giá trị trả về để adapter gửi.
- **Converter không hỗ trợ kiểu trả về:** response không thể chuyển thành JMS Message.
- **Nhận JSON như DTO khi chỉ dùng SimpleMessageConverter:** cần converter JSON phù hợp.
- **Dùng reply queue chung không có correlation:** response có thể bị ghép nhầm request.
- **Caller timeout nhưng listener vẫn tiếp tục:** reply có thể đến muộn hoặc không còn consumer.
- **Dùng temporary queue như nơi lưu kết quả lâu dài:** destination tạm có lifecycle riêng và không phù hợp truy vấn sau restart.
- **Không kiểm soát JMSReplyTo do client cung cấp:** listener có thể gửi dữ liệu tới destination ngoài phạm vi cho phép.
- **Nhầm QoS reply với receive timeout:** TTL quyết định thời gian message còn hiệu lực; receive timeout quyết định caller chờ bao lâu.
- **Giả định response và database commit nguyên tử:** cần transaction strategy rõ ràng.

## 15. Kiểm thử response management

Nên có integration test với JMS provider/broker mục tiêu để kiểm tra:

1. Listener trả String và response được chuyển thành TextMessage.
2. Listener trả DTO và converter JSON tạo message đúng schema.
3. @SendTo được dùng khi request không có JMSReplyTo.
4. JMSReplyTo trên request được ưu tiên so với default @SendTo.
5. JmsTemplate.sendAndReceive hoặc convertSendAndReceive nhận được response từ temporary queue.
6. JmsResponse gửi tới queue/topic được chọn tại runtime.
7. Spring Message trả về có các header cần thiết sau khi mapping.
8. Reply QoS priority và TTL được áp dụng theo cấu hình.
9. Không có reply thì caller xử lý timeout/null đúng cách.
10. Reply đến muộn được xử lý theo chính sách.
11. Nhiều request đồng thời được ghép đúng bằng correlation.
12. Listener lỗi hoặc gửi reply thất bại được xử lý theo transaction/error policy.
13. Destination không được phép bị từ chối theo broker authorization.

Unit test có thể gọi service nghiệp vụ và kiểm tra object trả về. Nhưng việc tạo JMS Message, chọn destination, gửi reply và nhận qua broker cần integration test.

## 16. Checklist thiết kế

Trước khi dùng giá trị trả về và @SendTo, hãy kiểm tra:

- Listener có thực sự cần request-reply hay chỉ cần xử lý một chiều?
- Method trả về kiểu dữ liệu nào và converter có hỗ trợ không?
- Request có JMSReplyTo hay listener cần @SendTo mặc định?
- Có cần destination động và nên dùng JmsResponse không?
- Có cần trả Spring Message để bổ sung header không?
- JmsTemplate caller có timeout và xử lý null không?
- Reply queue dùng riêng hay dùng chung? Nếu dùng chung, correlation được quản lý thế nào?
- Reply QoS priority và TTL có phù hợp với deadline của caller không?
- Listener và broker có quyền gửi tới reply destination không?
- Destination do client cung cấp đã được kiểm soát chưa?
- Retry, redelivery và transaction có thể gây tác dụng phụ lặp không?
- Có integration test cho JMSReplyTo, @SendTo, JmsResponse, converter và timeout không?

Khi hiểu rõ quan hệ giữa giá trị trả về, JMSReplyTo, @SendTo và JmsResponse, bạn có thể xây dựng request-reply trong Spring JMS với destination minh bạch, payload đúng định dạng và lifecycle phản hồi có thể kiểm soát.