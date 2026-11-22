# JMS và vai trò của Spring JMS đối với hệ thống dùng bộ môi giới

## Mục tiêu

JMS (Java Message Service, tên chuẩn hiện nay là Jakarta Messaging) cung cấp API chuẩn để các ứng dụng Java gửi, nhận và xử lý message thông qua một messaging provider. Spring JMS xây dựng lớp hỗ trợ trên API đó để ứng dụng Spring làm việc với broker dễ hơn: quản lý tài nguyên, gửi message, nhận message bất đồng bộ, chuyển đổi payload và tham gia transaction.

Sau bài này, bạn có thể:

- Phân biệt JMS API, JMS provider và broker.
- Hiểu queue, topic, producer, consumer, destination, session và connection.
- Giải thích Spring JMS đứng ở đâu trong kiến trúc.
- Dùng `JmsTemplate` để gửi và nhận đồng bộ.
- Dùng `@JmsListener` và listener container để nhận message bất đồng bộ.
- Hiểu acknowledgement, redelivery, persistence và transaction.
- Chọn converter, destination và connection factory phù hợp.
- Nhận biết các API mới của Spring Framework 7 như `JmsClient`.
- Xây dựng một ứng dụng Spring Boot gửi và nhận message qua ActiveMQ Artemis.

## 1. JMS, provider và broker là ba khái niệm khác nhau

JMS là một **đặc tả API**, không phải một message broker. Đặc tả định nghĩa các interface và semantics để chương trình Java có thể gửi/nhận message theo một hợp đồng chung.

Một hệ thống JMS thường có ba phần:

1. **Ứng dụng Java:** tạo message, gửi tới destination và xử lý message nhận được.
2. **JMS provider/client library:** triển khai các interface `jakarta.jms` và cho ứng dụng kết nối tới messaging system.
3. **Broker/server:** tiếp nhận, định tuyến, lưu trữ và phân phối message theo queue, topic, subscription, policy và cấu hình của sản phẩm.

Ví dụ các sản phẩm thường được dùng với JMS gồm Apache ActiveMQ Artemis và IBM MQ. Sản phẩm phải cung cấp JMS provider tương thích để ứng dụng sử dụng API JMS. Một broker có thể chạy riêng như một dịch vụ, hoặc chạy embedded trong tiến trình ứng dụng cho mục đích phát triển và kiểm thử.

~~~text
Producer application
        |
        | jakarta.jms API
        v
JMS ConnectionFactory / provider client
        |
        | protocol / network connection
        v
Message broker
        |
        | queue, topic, subscription
        v
JMS provider client
        |
        | jakarta.jms API
        v
Consumer application
~~~

JMS chuẩn hóa cách ứng dụng Java làm việc với messaging provider. Nó không bắt buộc mọi broker phải có cùng cách quản trị, giao thức mạng, cơ chế HA, dead-letter queue hay cấu hình bảo mật. Những phần đó vẫn phụ thuộc sản phẩm.

Spring JMS cũng không phải broker và không thay thế provider. Spring cung cấp API tiện dụng và hạ tầng để ứng dụng sử dụng provider thông qua `ConnectionFactory`.

## 2. Các thành phần cơ bản trong Jakarta Messaging

| Thành phần | Vai trò |
|---|---|
| `ConnectionFactory` | Điểm vào để tạo kết nối tới JMS provider; chứa cấu hình endpoint, credential, TLS và các thuộc tính vendor-specific. |
| `Connection` | Kết nối logic giữa ứng dụng và provider. |
| `Session` | Ngữ cảnh tạo producer/consumer/message; quản lý thứ tự xử lý, acknowledgement và transaction của một chuỗi thao tác. |
| `Destination` | Địa chỉ logic nhận message, thường là `Queue` hoặc `Topic`. |
| `MessageProducer` | Gửi message tới destination. |
| `MessageConsumer` | Nhận message từ destination hoặc subscription. |
| `MessageListener` | Callback được gọi khi consumer nhận message bất đồng bộ. |
| `Message` | Đối tượng message theo JMS, gồm headers, properties và body. |

Luồng gửi ở mức API thấp thường có dạng:

~~~text
ConnectionFactory
    -> Connection
        -> Session
            -> MessageProducer
                -> send(Destination, Message)
~~~

Ứng dụng cũng cần đóng tài nguyên đúng vòng đời. Spring JMS giảm phần boilerplate này bằng template và listener container; provider vẫn chịu trách nhiệm kết nối và vận chuyển.

### Session có vai trò đặc biệt

`Session` không chỉ là nơi tạo message. Nó còn:

- Tạo producer, consumer và message.
- Xác định acknowledgement mode khi session không transacted.
- Gom các thao tác gửi/nhận trong session thành một transaction cục bộ nếu session được cấu hình transacted.
- Xác định thứ tự thao tác message trong phạm vi session.
- Quản lý việc giữ message chưa được acknowledge và redelivery khi session được phục hồi.

Không chia sẻ một JMS `Session` tùy tiện giữa nhiều thread. Hãy để Spring quản lý session qua `JmsTemplate` hoặc listener container, hoặc tuân theo quy tắc thread-safety của JMS API nếu sử dụng API thấp trực tiếp.

## 3. Queue và Topic: hai messaging domain

Jakarta Messaging định nghĩa hai mô hình chính.

### Queue — point-to-point

Producer gửi message vào một queue. Một hoặc nhiều consumer có thể lắng nghe cùng queue, nhưng mỗi message được giao cho một consumer trong nhóm competing consumers.

~~~text
Producer A ----                                 > Queue: orders.queue ---> Consumer 1
                /                    ----> Consumer 2
Producer B ----/
~~~

Queue phù hợp với công việc cần phân phối cho worker:

- Xử lý đơn hàng.
- Tạo hóa đơn.
- Gửi email.
- Chạy tác vụ nền.
- Tách producer khỏi thời điểm consumer xử lý.

Khi có nhiều consumer trên cùng queue, provider quyết định cách phân phối message theo các quy tắc của sản phẩm và message selector. Không giả định tất cả consumer đều nhận một bản sao.

### Topic — publish/subscribe

Producer publish message tới topic. Mỗi subscription phù hợp nhận một bản sao message riêng. Nhiều subscriber độc lập có thể cùng quan tâm một sự kiện.

~~~text
                    +---- Subscription A ---> Consumer A
Producer ---> Topic |
                    +---- Subscription B ---> Consumer B
                    |
                    +---- Subscription C ---> Consumer C
~~~

Topic phù hợp với thông báo sự kiện:

- OrderCreated được gửi tới inventory, analytics và notification.
- Một sự kiện thay đổi trạng thái được nhiều hệ thống quan tâm.
- Các subscriber có vòng đời độc lập.

Cần phân biệt **subscription** và **consumer**: subscription là thực thể do provider quản lý; consumer là đối tượng trong ứng dụng dùng để nhận message từ subscription.

### Durable và non-durable subscription

- **Non-durable subscription:** thường chỉ nhận message trong thời gian subscription đang hoạt động. Subscriber offline có thể bỏ lỡ message.
- **Durable subscription:** provider giữ message phù hợp cho subscription khi consumer tạm thời offline, theo cấu hình và chính sách lưu trữ của broker.

Durable subscription không đồng nghĩa với việc mọi message đều được giữ vô hạn. Thời gian lưu, quota, expiry, policy và cách xóa subscription phụ thuộc provider.

Queue/topic là abstraction JMS; tên destination và cấu hình vật lý của broker cần được quản trị nhất quán. JMS không chuẩn hóa toàn bộ thao tác quản trị queue/topic lâu dài.

## 4. JMS Message gồm những gì?

JMS message có ba nhóm dữ liệu:

1. **Headers:** metadata chuẩn do JMS định nghĩa, ví dụ `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, `JMSDestination`, `JMSExpiration`, `JMSRedelivered`.
2. **Properties:** các cặp tên–giá trị do ứng dụng hoặc provider bổ sung, có thể dùng trong message selector.
3. **Body:** nội dung chính của message.

Các kiểu body chuẩn thường gặp:

| Kiểu message | Nội dung |
|---|---|
| `TextMessage` | Văn bản, thường dùng cho JSON/XML/text. |
| `BytesMessage` | Dữ liệu nhị phân. |
| `MapMessage` | Tập các cặp tên–giá trị kiểu dữ liệu được JMS hỗ trợ. |
| `ObjectMessage` | Một object Java Serializable. |
| `StreamMessage` | Chuỗi giá trị được đọc tuần tự theo kiểu dữ liệu. |
| `Message` | Message không có body, chỉ dùng headers/properties. |

Với hệ thống mới, `TextMessage` chứa JSON hoặc `BytesMessage` chứa định dạng nhị phân có schema thường dễ tích hợp đa ngôn ngữ hơn `ObjectMessage`. Không nên deserialize Java object từ nguồn không đáng tin cậy; hãy dùng serializer có schema và giới hạn kiểu rõ ràng.

### Headers, properties và selector

Ví dụ một message có:

- `JMSCorrelationID = "REQ-2026-17"`
- Property `tenantId = "tenant-a"`
- Property `eventType = "OrderCreated"`
- Body là JSON chứa thông tin đơn hàng.

Consumer có thể dùng message selector để chỉ nhận các message thỏa điều kiện trên JMS headers/properties, chẳng hạn:

~~~sql
eventType = 'OrderCreated' AND tenantId = 'tenant-a'
~~~

Selector không phải truy vấn JSON body. Chỉ các header/property hợp lệ theo JMS mới được dùng trong selector. Cần thống nhất kiểu dữ liệu property giữa producer và consumer.

## 5. Độ bền, delivery mode và acknowledgement

JMS cung cấp các cơ chế giúp provider quản lý giao nhận. Cần hiểu rõ từng khái niệm vì chúng không tự tạo ra bảo đảm “exactly once” cho toàn bộ nghiệp vụ.

### Persistent và non-persistent

| Delivery mode | Ý nghĩa |
|---|---|
| `PERSISTENT` | Yêu cầu provider lưu message theo chính sách bền vững để chịu được lỗi provider/server theo semantics JMS. |
| `NON_PERSISTENT` | Cho phép provider tối ưu hiệu năng; message có thể mất khi provider gặp sự cố. |

Persistent message vẫn có thể được giao lại nếu consumer lỗi hoặc transaction rollback. Vì vậy, consumer nên idempotent và có cơ chế phát hiện message đã xử lý.

### Acknowledgement mode

Với session không transacted, JMS định nghĩa các mode chính:

- **AUTO_ACKNOWLEDGE:** provider tự acknowledge sau khi consumer nhận message theo semantics của API.
- **CLIENT_ACKNOWLEDGE:** ứng dụng gọi acknowledge; acknowledgement có thể áp dụng cho các message đã giao bởi cùng session chứ không chỉ một message đơn lẻ.
- **DUPS_OK_ACKNOWLEDGE:** provider có thể acknowledge lười hơn để giảm overhead; consumer phải chấp nhận khả năng nhận trùng.
- **Transacted session:** acknowledgement được quản lý thông qua commit/rollback của session, không dùng một acknowledgement mode độc lập.

Nếu listener xử lý xong rồi acknowledge, provider có thể loại message khỏi luồng giao nhận. Nếu xử lý thất bại và message chưa được commit/acknowledge, provider có thể giao lại tùy mode và policy.

### Redelivery và duplicate

Khi message được giao lại, provider có thể đánh dấu `JMSRedelivered` và cập nhật `JMSXDeliveryCount`. Số lần thử, khoảng cách retry, backoff, expiry và dead-letter policy phụ thuộc provider.

Không được giả định message chỉ xuất hiện đúng một lần. Có thể xảy ra tình huống:

1. Consumer cập nhật database thành công.
2. Process chết trước khi acknowledge/commit JMS.
3. Provider giao lại message.
4. Consumer chạy nghiệp vụ lần nữa.

Cách xử lý phổ biến là idempotency: dùng event ID/business key để kiểm tra message đã được áp dụng trước khi thực hiện side effect lần nữa.

## 6. Spring JMS đứng ở đâu?

Spring JMS thuộc module `spring-jms` của Spring Framework. Nó làm việc với Jakarta Messaging API và provider client, cung cấp các lớp tiện ích:

| Thành phần Spring | Vai trò |
|---|---|
| `JmsTemplate` | Gửi và nhận message đồng bộ; quản lý Connection/Session/Producer/Consumer và giải phóng tài nguyên. |
| `@JmsListener` | Khai báo phương thức nhận message. |
| `DefaultMessageListenerContainer` | Listener container hỗ trợ quản lý thread, consumer, transaction, recovery và scaling. |
| `SimpleMessageListenerContainer` | Listener container đơn giản với số consumer cố định và callback do provider gọi. |
| `JmsListenerContainerFactory` | Tạo và cấu hình listener container cho các endpoint. |
| `JmsMessagingTemplate` | Cầu nối giữa Spring `Message<?>` và JMS. |
| `JmsClient` | Fluent API mới trong Spring Framework 7.0 cho thao tác JMS. |
| `JmsTransactionManager` | Quản lý transaction cục bộ cho một JMS ConnectionFactory. |
| `DestinationResolver` | Phân giải tên destination thành JMS `Destination`. |
| `MessageConverter` | Chuyển object ứng dụng thành JMS Message và ngược lại. |

Spring JMS giúp ứng dụng tập trung vào nghiệp vụ. Nó không tự cung cấp broker; ứng dụng vẫn cần một JMS provider và broker/server phù hợp.

## 7. Gửi message bằng JmsTemplate

`JmsTemplate` là lớp trung tâm của Spring JMS. Nó quản lý vòng đời tài nguyên JMS khi gửi hoặc nhận đồng bộ.

Một số thao tác phổ biến:

~~~java
jmsTemplate.send("orders.queue", session -> {
    TextMessage message = session.createTextMessage("order-42");
    message.setStringProperty("eventType", "OrderCreated");
    return message;
});

jmsTemplate.convertAndSend("orders.queue", "order-42");

jmsTemplate.convertAndSend("orders.queue", orderCreated);
~~~

Khác biệt:

- `send` nhận một `MessageCreator`, cho phép tạo JMS Message trực tiếp bằng JMS Session.
- `convertAndSend` nhận object; JMS `MessageConverter` chuyển object thành JMS Message.
- `receive` nhận JMS Message đồng bộ và có thể block thread.
- `receiveAndConvert` nhận rồi chuyển payload thành object.
- `sendAndReceive` hỗ trợ request/reply cơ bản, thường sử dụng temporary queue cho reply nếu phù hợp.

Có thể cấu hình QoS như delivery mode, priority và time-to-live. Khi muốn `JmsTemplate` chủ động dùng các giá trị QoS đã cấu hình thay cho default do provider quyết định, bật `explicitQosEnabled`.

`JmsTemplate` thread-safe sau khi đã cấu hình. Có thể inject một instance dùng chung vào nhiều service; không cần tạo một template mới cho mỗi request.

### Nhận đồng bộ

`JmsTemplate.receive(...)` chờ message trong thread gọi. Hãy cấu hình `receiveTimeout` để tránh block vô thời hạn:

~~~java
jmsTemplate.setReceiveTimeout(2_000);
Message message = jmsTemplate.receive("orders.reply");
~~~

Với ứng dụng xử lý liên tục, listener container thường phù hợp hơn receive đồng bộ vì nó nhận message bất đồng bộ và quản lý consumer/thread.

## 8. Nhận bất đồng bộ bằng @JmsListener

Spring cho phép viết Message-Driven POJO (MDP) mà không cần class phải implement trực tiếp `jakarta.jms.MessageListener`.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("received=" + orderId);
    }
}
~~~

`@JmsListener` khai báo destination và phương thức xử lý. Listener container sẽ đăng ký consumer, nhận message và gọi phương thức.

Có thể nhận payload, JMS Message hoặc các tham số metadata được Spring hỗ trợ. Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        String payload,
        @Header(JmsHeaders.MESSAGE_ID) String messageId) {
    // Xử lý payload và metadata.
}
~~~

Đoạn trên minh họa khả năng bind header của Spring JMS; khi dùng tham số header, cần import đúng annotation và constants của Spring JMS.

Trong ứng dụng Spring Framework thuần, bật listener endpoint bằng `@EnableJms` và cấu hình `JmsListenerContainerFactory`. Với Spring Boot khi JMS auto-configuration hoạt động, hạ tầng listener được cấu hình tự động và thường không cần khai báo `@EnableJms` riêng.

Nếu container chạy nhiều consumer song song, bean listener phải thread-safe. Tránh lưu trạng thái mutable theo từng message trong field dùng chung; ưu tiên biến cục bộ, service stateless và cơ chế đồng bộ phù hợp.

## 9. SimpleMessageListenerContainer và DefaultMessageListenerContainer

Spring cung cấp hai listener container tiêu chuẩn:

| Đặc điểm | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
|---|---|---|
| Cách nhận | Đăng ký listener bằng `MessageConsumer.setMessageListener`; provider gọi callback | Container chủ động nhận message và điều phối listener bằng task |
| Consumer | Số lượng cố định khi khởi động | Có thể cấu hình concurrency và điều chỉnh theo tải |
| External transaction | Không tham gia external transaction theo cách DMLC hỗ trợ | Có thể tham gia transaction bên ngoài, ví dụ JTA/XA |
| Recovery | Gần với callback provider | Có khả năng tự phục hồi/reconnect khi broker gián đoạn |
| Trường hợp dùng | Cấu hình đơn giản, yêu cầu thấp | Phần lớn ứng dụng cần quản lý concurrency, recovery và transaction |

`DefaultMessageListenerContainer` thường là lựa chọn phù hợp cho ứng dụng production. Nó hỗ trợ local JMS transaction và external transaction khi cấu hình đúng.

### Lưu ý về AUTO_ACKNOWLEDGE

Tài liệu Spring cảnh báo không nên mặc định coi `AUTO_ACKNOWLEDGE` là đủ tin cậy cho listener processing. Với một số cách chạy listener, message có thể được acknowledge dù nghiệp vụ listener thất bại hoặc container đang dừng.

Nếu cần bảo đảm xử lý tin cậy, hãy cân nhắc transacted session. Khi listener ném exception trong một transaction cục bộ, container có thể rollback session và provider giao lại message.

Redelivery có thể tạo duplicate. Hãy kết hợp transaction với idempotent consumer và dead-letter/retry policy phù hợp. Không đặt kỳ vọng rằng chỉ đổi acknowledgement mode là tự động có exactly-once business processing.

## 10. Transaction trong Spring JMS

Có hai cấp transaction cần phân biệt.

### Local JMS transaction

`JmsTransactionManager` quản lý transaction cho một `ConnectionFactory`. Nó gắn cặp JMS Connection/Session với thread; `JmsTemplate` tự phát hiện và dùng tài nguyên transactional đó.

Một local JMS transaction có thể gom nhiều thao tác JMS trong cùng session thành một commit/rollback. Nó không tự động tạo transaction phân tán với database.

Ví dụ:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publishOrderEvents(Order order) {
    jmsTemplate.convertAndSend("orders.created", order.getId());
    jmsTemplate.convertAndSend("audit.events", "created:" + order.getId());
}
~~~

Ví dụ này yêu cầu cấu hình `JmsTransactionManager` và các destination. Khi transaction rollback, các thao tác JMS trong session đó có thể được rollback cùng nhau.

### XA/JTA transaction

Nếu cần phối hợp JMS và database trong cùng một distributed transaction, cần:

- JTA transaction manager.
- JMS ConnectionFactory có XA capability.
- DataSource/provider được cấu hình XA.
- Transaction coordinator và cấu hình deployment tương ứng.

XA có chi phí và độ phức tạp cao. Với nhiều hệ thống, transactional outbox và idempotent consumer là lựa chọn thực tế hơn: ghi dữ liệu nghiệp vụ và outbox record trong một database transaction, sau đó publisher chuyển outbox event sang broker.

### Không đồng nhất ba sự kiện

- `send` trả về thành công: thao tác gửi qua API/provider đã được chấp nhận theo contract.
- Broker lưu message: phụ thuộc delivery mode, persistence và cấu hình broker.
- Consumer hoàn tất nghiệp vụ: cần được xác nhận riêng bằng reply/status/event hoặc dữ liệu nghiệp vụ.

Không suy ra consumer đã commit database chỉ từ việc `JmsTemplate.convertAndSend` không ném exception.

## 11. Destination và DestinationResolver

JMS destination có thể là queue hoặc topic. Trong ứng dụng, destination có thể được tham chiếu bằng object `Destination` hoặc tên.

Spring dùng `DestinationResolver` để phân giải tên destination thành đối tượng JMS:

- Có thể lookup destination được quản trị sẵn qua JNDI.
- Có thể phân giải destination theo tên bằng resolver.
- Một số provider hỗ trợ dynamic destination creation, nhưng cơ chế tạo queue/topic vật lý là vendor-specific.

`pubSubDomain` xác định domain mặc định cho việc phân giải destination theo tên. Mặc định Spring JMS dùng queue (point-to-point). Nếu dùng topic, cấu hình sender và listener container phải thống nhất pub/sub domain.

Với Spring Framework 7, default resolver đã được thay đổi sang `SimpleDestinationResolver`, có khả năng cache các Queue/Topic được resolve từ Session. Nếu cần hành vi resolve động trên mỗi lần gọi, có thể cấu hình resolver phù hợp như `DynamicDestinationResolver`.

Tên destination phải khớp với cấu hình broker. Một tên queue trong code không bảo đảm queue đã được tạo hoặc ứng dụng có quyền gửi/nhận.

## 12. Message conversion: object Java và JMS Message

JMS API có các kiểu message cụ thể như `TextMessage`, `BytesMessage`, `MapMessage` và `ObjectMessage`. Spring JMS `MessageConverter` giúp chuyển object nghiệp vụ sang một trong các dạng đó.

Default `SimpleMessageConverter` hỗ trợ các kiểu cơ bản như String, byte array, Map và Serializable. Với POJO không Serializable, cần converter riêng, ví dụ Jackson JSON converter để tạo `TextMessage`.

Cần phân biệt hai interface cùng tên:

- `org.springframework.jms.support.converter.MessageConverter`: chuyển object với JMS `Message`.
- `org.springframework.messaging.converter.MessageConverter`: chuyển payload với Spring `Message<?>`.

`JmsMessagingTemplate` và `JmsClient` tích hợp Spring common messaging abstraction; `JmsTemplate` làm việc ở lớp JMS. Hãy dùng converter thuộc đúng package mà API yêu cầu.

Khi chuyển object qua broker, nên dùng định dạng rõ ràng như JSON/bytes và quản lý schema. Tránh phụ thuộc vào Java native serialization và tránh nhận `ObjectMessage` từ nguồn không đáng tin.

## 13. JmsMessagingTemplate và JmsClient trong Spring Framework 7

### JmsMessagingTemplate

`JmsMessagingTemplate` xây dựng trên `JmsTemplate`, nhưng làm việc với Spring `Message<?>` và các abstraction của `spring-messaging`. Nó hữu ích khi ứng dụng đã dùng `MessageHeaders`, `MessageChannel` hoặc Spring Messaging converter và muốn nối flow đó với JMS.

### JmsClient

Spring Framework 7.0 giới thiệu `JmsClient`, một fluent API cho thao tác JMS. Nó xây dựng trên `JmsTemplate`, cung cấp các operation handle có thể cấu hình theo từng lần gửi/nhận và có thể tạo từ `ConnectionFactory` hoặc một `JmsTemplate` đã cấu hình.

Ví dụ:

~~~java
JmsClient jmsClient = JmsClient.create(connectionFactory);

jmsClient.destination("orders.queue")
        .withTimeToLive(30_000)
        .send("order-42");
~~~

Có thể dùng builder để cấu hình `MessageConverter` và `MessagePostProcessor`. Nếu đã có `JmsTemplate` với các thiết lập chung, tạo `JmsClient` từ template giúp tái sử dụng cấu hình đó.

`JmsClient` là API mới trong Framework 7; dự án trên Framework 6.x tiếp tục sử dụng `JmsTemplate` và `JmsMessagingTemplate` theo phiên bản tương ứng.

## 14. Kết nối, cache và pooling

Một thao tác JMS có thể cần Connection, Session, Producer và Consumer. Tạo/hủy các đối tượng này cho mọi message có thể gây overhead.

Spring cung cấp:

- `SingleConnectionFactory`: tái sử dụng một JMS Connection, phù hợp với một số standalone/test use case.
- `CachingConnectionFactory`: mở rộng khả năng cache session, producer và consumer.
- Provider-specific pool: ví dụ pooled connection factory của vendor hoặc pooled-jms.

Trong Jakarta EE/application server, nên dùng ConnectionFactory do container quản lý để tham gia transaction và pooling theo cấu hình môi trường. Trong ứng dụng standalone, dùng caching hoặc pool phù hợp với provider.

Không tự chia sẻ một JMS Session cho nhiều thread. Hãy để template/container quản lý session theo đúng vòng đời và mô hình thread.

## 15. Spring Boot và cấu hình broker

Spring Boot tự động cấu hình JMS infrastructure khi phát hiện starter/provider phù hợp trên classpath.

Với ActiveMQ Artemis:

- `spring-boot-starter-artemis` cung cấp client và Spring infrastructure để kết nối Artemis.
- Thêm `artemis-jakarta-server` nếu muốn chạy embedded broker.
- `spring.artemis.mode=embedded` yêu cầu broker embedded.
- `spring.artemis.mode=native` kết nối tới broker chạy riêng.
- `spring.artemis.embedded.queues` và `spring.artemis.embedded.topics` khai báo destination cần tạo cho embedded broker.
- `spring.jms.cache.session-cache-size` cấu hình cache session.
- `spring.jms.pub-sub-domain` điều khiển domain mặc định queue/topic.

Ví dụ kết nối broker riêng:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://broker.example:61616
spring.artemis.user=${JMS_USER}
spring.artemis.password=${JMS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

Credential nên được lấy từ secret manager hoặc environment variable. Không commit password thật vào source control.

## 16. Ví dụ Java 17+ chạy được: gửi và nhận qua embedded Artemis

Ví dụ dùng Spring Boot 4.1.2, Spring JMS và ActiveMQ Artemis embedded. Producer gửi một String vào queue; phương thức `@JmsListener` nhận message bất đồng bộ. Ví dụ chỉ minh họa queue và payload String nên không cần JSON converter.

Cấu trúc project:

~~~text
spring-jms-artemis-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          JmsBrokerDemoApplication.java
          OrderListener.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-jms-artemis-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Embedded broker ở đây dùng bộ nhớ cho mục đích demo. Không dùng cấu hình này để kết luận dữ liệu được lưu bền vững khi process hoặc máy chủ dừng.

### JmsBrokerDemoApplication.java

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsBrokerDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(JmsBrokerDemoApplication.class, args)) {
            // ApplicationRunner waits for the asynchronous listener before shutdown.
        }
    }

    @Bean
    ApplicationRunner sendOrder(JmsTemplate jmsTemplate, OrderListener listener) {
        return args -> {
            String orderId = "ORD-42";
            System.out.println("sending=" + orderId);

            jmsTemplate.convertAndSend("orders.queue", orderId);

            if (!listener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for the JMS listener");
            }
        };
    }
}
~~~

### OrderListener.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final CountDownLatch received = new CountDownLatch(1);

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("received=" + orderId);
        received.countDown();
    }

    public boolean await(long timeout, TimeUnit unit) throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

Chạy từ thư mục project bằng Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Các dòng stdout do ứng dụng in ra (bỏ qua log khởi động của Spring Boot):

~~~text
sending=ORD-42
received=ORD-42
~~~

Cách đọc ví dụ:

1. Spring Boot phát hiện Artemis và cấu hình `ConnectionFactory`, `JmsTemplate` cùng listener infrastructure.
2. Artemis embedded khởi tạo queue `orders.queue`.
3. `ApplicationRunner` gọi `JmsTemplate.convertAndSend` để gửi String; default converter ánh xạ String thành JMS `TextMessage`.
4. Listener container đăng ký consumer và gọi `OrderListener.receive` khi có message.
5. `CountDownLatch` chỉ dùng để ví dụ chờ listener hoàn tất trước khi đóng application context.
6. Đây là ví dụ embedded trong một JVM; khi triển khai thực tế, chuyển cấu hình sang `native` và kết nối tới broker ngoài.

## 17. Spring Integration và JMS

Nếu ứng dụng dùng Spring Integration, module `spring-integration-jms` cung cấp:

- Inbound channel adapter để nhận message từ JMS và đưa vào Spring Integration channel.
- Outbound channel adapter để gửi message từ channel sang JMS destination.
- Inbound/outbound gateway cho request/reply.
- Cấu hình dựa trên `JmsTemplate` và message listener container của Spring JMS.

Adapter thích hợp khi muốn nối JMS với các endpoint, transformer, router, filter và channel trong một integration flow. Nếu chỉ cần gửi/nhận trong service Spring thông thường, `JmsTemplate` và `@JmsListener` thường đơn giản hơn.

JMS adapter không biến queue/topic thành Spring `MessageChannel`; adapter là cầu nối giữa hai abstraction.

## 18. Bảo mật và vận hành

Khi kết nối broker trong production, cần chú ý:

- Dùng TLS và xác thực phù hợp; không truyền credential dạng rõ trên mạng không tin cậy.
- Cấp quyền tối thiểu: service chỉ được gửi/nhận destination mà nó cần.
- Quản lý destination, expiry, max size, redelivery và dead-letter policy ở broker.
- Giới hạn concurrency và consumer count để không làm quá tải database hoặc downstream service.
- Theo dõi queue depth, enqueue/dequeue rate, consumer count, redelivery, DLQ, connection recovery và processing latency.
- Dùng persistent delivery khi cần durability và cấu hình broker tương ứng.
- Thiết kế consumer idempotent để xử lý duplicate/redelivery.
- Tránh Java native deserialization từ nguồn không tin cậy; ưu tiên JSON/bytes với schema được kiểm soát.
- Không log toàn bộ message body nếu có thông tin cá nhân, token hoặc dữ liệu bí mật.
- Kiểm thử tình huống broker restart, listener exception, transaction rollback, queue đầy, message hết hạn và consumer dừng đột ngột.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không kết nối được broker | Sai URL, port, credential, TLS hoặc broker chưa chạy | ConnectionFactory, broker logs, network và TLS truststore |
| Destination not found | Queue/topic chưa được tạo hoặc tên không khớp | Cấu hình broker, JNDI hoặc DestinationResolver |
| Listener không nhận message | Sai destination/domain, listener chưa start hoặc selector không khớp | `@JmsListener`, container factory, queue/topic và selector |
| Consumer nhận duplicate | Redelivery sau rollback/crash hoặc nhiều lần publish | JMSRedelivered, delivery count, idempotency key |
| Message mất khi listener lỗi | Acknowledge mode/transaction không phù hợp | `sessionTransacted`, acknowledgement mode và container behavior |
| Listener bị block | Gọi receive đồng bộ hoặc xử lý nghiệp vụ quá lâu | Receive timeout, listener concurrency, downstream latency |
| Throughput thấp | Tạo quá nhiều connection/session hoặc thiếu cache/pool | CachingConnectionFactory, provider pool và consumer count |
| Conversion exception | Payload type, charset, converter hoặc schema không khớp | MessageConverter, raw message type, content và headers |
| Queue tăng liên tục | Consumer không đủ năng lực hoặc xử lý lỗi liên tục | Queue depth, concurrency, DLQ, retry và downstream |
| Gửi được nhưng consumer không xử lý | Broker nhận message nhưng route/selector/subscription không khớp | Destination, selector, permissions và consumer state |

## 20. Phân biệt JMS với Kafka và các broker API khác

JMS là API Java chuẩn. Nó phù hợp khi cần tích hợp với các provider triển khai Jakarta Messaging.

Kafka có protocol, client API, topic/partition, offset và consumer group riêng. Kafka không tự động trở thành JMS provider chỉ vì nó là một hệ thống messaging. Muốn kết nối JMS với Kafka cần bridge/connector hoặc một integration layer cụ thể.

Tương tự, Spring AMQP dùng API AMQP/RabbitMQ riêng; Spring JMS dùng Jakarta Messaging. Một broker có thể hỗ trợ nhiều protocol, nhưng semantics của các protocol vẫn khác nhau. Không đổi `JmsTemplate` thành `RabbitTemplate` hoặc `KafkaTemplate` chỉ bằng cách đổi tên destination.

## 21. Checklist chọn Spring JMS

- [ ] Broker/provider có triển khai Jakarta Messaging và có client tương thích.
- [ ] Ứng dụng dùng đúng namespace `jakarta.jms` (Spring 6/7); không trộn với `javax.jms` của thế hệ cũ.
- [ ] Chọn queue hay topic theo mô hình phân phối.
- [ ] Destination đã được tạo/quản trị và service có quyền truy cập.
- [ ] Producer/consumer thống nhất message type, converter, schema và headers.
- [ ] Dùng `JmsTemplate` cho gửi/nhận đồng bộ; dùng listener container cho nhận bất đồng bộ.
- [ ] Chọn `DefaultMessageListenerContainer` hoặc `SimpleMessageListenerContainer` theo yêu cầu transaction và concurrency.
- [ ] Acknowledgement, session transaction, redelivery và DLQ đã được xác định.
- [ ] Consumer idempotent để xử lý duplicate.
- [ ] ConnectionFactory có cache/pool phù hợp.
- [ ] TLS, authentication, authorization và secret management đã được cấu hình.
- [ ] Có kiểm thử khi broker restart, listener lỗi và transaction rollback.

## Ghi nhớ

- **JMS/Jakarta Messaging là API chuẩn; provider triển khai API và broker thực hiện lưu trữ, định tuyến, phân phối.**
- Queue là point-to-point: mỗi message được giao cho một consumer; topic là publish/subscribe: mỗi subscription nhận một bản sao.
- `JmsTemplate` là API gửi/nhận đồng bộ; `@JmsListener` dùng listener container để nhận bất đồng bộ.
- `DefaultMessageListenerContainer` phù hợp với phần lớn use case cần concurrency, recovery và transaction.
- Acknowledgement, persistent delivery và transaction quyết định cách message được giữ hoặc giao lại; chúng không tự đảm bảo exactly-once business processing.
- `JmsTransactionManager` quản lý local JMS transaction cho một ConnectionFactory; XA/JTA cần cấu hình provider và transaction coordinator.
- Spring Framework 7 bổ sung `JmsClient`; `JmsMessagingTemplate` kết nối JMS với Spring `Message<?>`.
- Spring JMS không phải broker và không làm cho Kafka/AMQP tự động trở thành JMS.
- Production cần idempotency, observability, security, retry policy và dead-letter handling.

## Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 7.0.10 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference: Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference: JMS Namespace and Listener Containers](https://docs.spring.io/spring-framework/reference/integration/jms/namespace.html)
- [Spring Boot 4.1.2 Reference: JMS](https://docs.spring.io/spring-boot/4.1/reference/messaging/jms.html)
- [Spring Boot Getting Started: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Spring Integration Reference: JMS Support](https://docs.spring.io/spring-integration/reference/jms.html)
