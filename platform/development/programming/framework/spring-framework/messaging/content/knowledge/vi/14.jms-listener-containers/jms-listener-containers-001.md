# Vai trò container trong đăng ký, nhận và gọi listener

Trong ứng dụng JMS, một listener là thành phần thực hiện nghiệp vụ khi có message đến. Listener thường chỉ cần biết cách xử lý payload, kiểm tra dữ liệu và gọi các dịch vụ nghiệp vụ. Việc kết nối tới broker, đăng ký consumer, chờ message, quản lý Session, acknowledgment, transaction, concurrency và phục hồi kết nối thuộc về một thành phần khác: **message listener container**.

Spring JMS cung cấp listener container để đứng giữa JMS provider và listener của ứng dụng. Container quản lý vòng đời nhận message, sau đó gọi listener trong đúng ngữ cảnh mà nó đã cấu hình. Khi dùng annotation, ứng dụng khai báo endpoint bằng @JmsListener; Spring tạo container từ một JmsListenerContainerFactory và quản lý container qua JmsListenerEndpointRegistry.

Bài này đi theo toàn bộ đường đi từ đăng ký listener đến lúc một message được nhận và phương thức nghiệp vụ được gọi. Ta cũng sẽ phân biệt hai implementation chính của Spring, hiểu transaction và acknowledgment, cấu hình concurrency, xử lý lỗi và dựng một ứng dụng Java có thể chạy với broker Artemis.

## 1. Listener container giải quyết vấn đề gì?

Nếu tự viết JMS bằng API thấp, ứng dụng phải thực hiện nhiều bước:

1. Lấy ConnectionFactory.
2. Tạo Connection và Session.
3. Tìm hoặc tạo Queue/Topic.
4. Tạo MessageConsumer.
5. Đăng ký MessageListener hoặc tự gọi receive().
6. Chuyển message tới code nghiệp vụ.
7. Quản lý acknowledgment hoặc transaction.
8. Đóng consumer, session và connection khi dừng.
9. Xử lý mất kết nối, khởi động lại và lỗi khi nhận.

Nếu mỗi service tự thực hiện các bước này, code nghiệp vụ sẽ bị trộn với code hạ tầng. Việc thay đổi concurrency, transaction hoặc provider cũng trở nên khó khăn.

Spring listener container gom phần hạ tầng đó vào một nơi. Listener chỉ tập trung vào message mà nó nhận được.

~~~text
                 Spring Application
                         |
              @EnableJms / endpoint scan
                         |
                    @JmsListener
                         |
              JmsListenerEndpointFactory
                         |
             JmsListenerContainerFactory
                         |
                         v
              MessageListenerContainer
                         |
              +----------+-----------+
              |                      |
         JMS Connection          JMS Destination
              |                  Queue / Topic
           Session                    ^
              |                      |
         MessageConsumer -------------+
              |
         Nhận JMS Message
              |
       Message conversion
              |
        Listener adapter
              |
       Phương thức listener
              |
       Xử lý nghiệp vụ
~~~

Container là thành phần điều phối nhận message. Nó chịu trách nhiệm đăng ký nhận message, cấp phát và giải phóng tài nguyên, quản lý thread, tham gia transaction và chuyển lỗi tới cơ chế xử lý tương ứng.

## 2. Phân biệt listener, endpoint, factory và container

Các tên này thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Listener method | Phương thức nghiệp vụ được gọi khi có message |
| Listener endpoint | Mô tả nơi nhận, listener cần gọi và các thuộc tính của điểm nhận |
| JmsListenerContainerFactory | Tạo container từ endpoint và áp dụng cấu hình |
| MessageListenerContainer | Quản lý consumer, nhận message và gọi listener |
| JmsListenerEndpointRegistry | Lưu và quản lý vòng đời các container được tạo từ endpoint annotation |
| ConnectionFactory | Tạo JMS Connection tới provider |
| MessageConverter | Chuyển JMS Message thành payload Java và ngược lại |

Ví dụ:

~~~java
@JmsListener(destination = "orders.queue")
public void handleOrder(String payload) {
    // Xử lý nghiệp vụ của đơn hàng.
}
~~~

Phương thức handleOrder là listener. Annotation mô tả endpoint nhận từ destination orders.queue. Factory cung cấp cấu hình container. Container tạo consumer trên destination, nhận message rồi gọi phương thức này thông qua listener adapter.

Không nên xem JmsListenerContainerFactory là container đang chạy. Factory là đối tượng tạo container; mỗi endpoint được đăng ký sẽ có container riêng được tạo từ factory.

## 3. Cách Spring đăng ký listener bằng annotation

Để bật annotation-driven listener, khai báo @EnableJms trên một lớp cấu hình Spring:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
}
~~~

Spring đăng ký hạ tầng phát hiện các phương thức @JmsListener trên những bean được quản lý trong ApplicationContext.

Một listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Khi ApplicationContext khởi tạo:

1. Spring phát hiện bean OrderListener.
2. Hạ tầng JMS tìm phương thức có @JmsListener.
3. Spring tạo metadata cho endpoint, bao gồm destination, listener method và các thuộc tính annotation.
4. Endpoint được đăng ký với JmsListenerEndpointRegistrar.
5. Registrar yêu cầu JmsListenerContainerFactory tạo container cho endpoint.
6. JmsListenerEndpointRegistry quản lý container được tạo.
7. Container khởi động theo lifecycle của ứng dụng và bắt đầu nhận message.

Mỗi phương thức @JmsListener là một endpoint. Nếu một class có ba listener method, Spring thường tạo ba container độc lập, mỗi container nhận cấu hình và destination của endpoint tương ứng.

Có thể chỉ định factory riêng trên annotation:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "ordersListenerFactory"
)
public void receiveOrder(String payload) {
    // Xử lý đơn hàng.
}
~~~

Nếu không chỉ định containerFactory, Spring tìm bean có tên mặc định jmsListenerContainerFactory. Vì vậy, tên bean factory cần thống nhất với annotation hoặc cấu hình mặc định.

## 4. JmsListenerContainerFactory và cấu hình container

Factory là nơi cấu hình các thuộc tính chung cho endpoint:

- ConnectionFactory dùng để kết nối provider.
- Loại container sẽ tạo.
- Destination resolver.
- Transaction và acknowledgment.
- Số consumer đồng thời.
- ErrorHandler.
- Recovery interval và các thiết lập vòng đời.
- MessageConverter và các adapter liên quan.

Ví dụ cấu hình DefaultJmsListenerContainerFactory:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-5");

        return factory;
    }
}
~~~

Trong ví dụ này:

- ConnectionFactory cung cấp kết nối tới JMS provider.
- sessionTransacted bật transaction cục bộ trên JMS Session.
- concurrency đặt mức consumer tối thiểu là 2 và tối đa là 5 đối với DefaultMessageListenerContainer.

Một factory có thể được dùng bởi nhiều endpoint. Mỗi endpoint vẫn có container riêng, nhưng các container có thể dùng chung những cấu hình như ConnectionFactory, transaction và concurrency.

Nếu hai nhóm listener cần chính sách khác nhau, hãy tạo hai factory có tên riêng:

~~~java
@Bean
public DefaultJmsListenerContainerFactory auditListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");

    return factory;
}

@Bean
public DefaultJmsListenerContainerFactory workerListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("3-8");

    return factory;
}
~~~

Audit listener có một consumer để giữ thứ tự xử lý dễ dự đoán. Worker listener có thể tăng số consumer khi tải tăng nếu sử dụng DefaultMessageListenerContainer và nhận từ queue.

## 5. Hai implementation container chính

Spring cung cấp hai implementation tiêu chuẩn:

- SimpleMessageListenerContainer (SMLC).
- DefaultMessageListenerContainer (DMLC).

Cả hai đều nhận message và gọi listener, nhưng cách nhận message và khả năng quản lý tải khác nhau.

| Đặc điểm | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
|---|---|---|
| Cách nhận | Đăng ký callback bằng MessageConsumer.setMessageListener() | Vòng lặp gọi MessageConsumer.receive() |
| Số consumer | Cố định khi khởi tạo | Có thể cố định hoặc tăng/giảm động |
| Phục hồi broker | Có cơ chế xử lý lỗi nhưng ít linh hoạt hơn | Tự phục hồi khi broker tạm thời không khả dụng |
| External transaction manager | Không hỗ trợ đầy đủ | Hỗ trợ |
| Native JMS transaction | Có | Có |
| Cấu hình concurrency | Số consumer cố định | Hỗ trợ min/max |
| Mục tiêu | Cấu hình đơn giản, ít yêu cầu runtime | Ứng dụng cần recovery và điều khiển linh hoạt |

### 5.1. SimpleMessageListenerContainer

SMLC tạo một số lượng Session và MessageConsumer cố định khi khởi động. Nó đăng ký listener thông qua API JMS:

~~~java
consumer.setMessageListener(messageListener);
~~~

Sau đó JMS provider gọi callback khi có message.

Đặc điểm:

- Cấu hình tương đối đơn giản.
- Số consumer được tạo cố định.
- Không tự động tăng giảm số consumer theo tải.
- Hỗ trợ native JMS transaction thông qua sessionTransacted.
- Không hỗ trợ tham gia external transaction manager theo cách DMLC hỗ trợ.
- Hành vi nhận message phụ thuộc callback của provider.

SMLC phù hợp với trường hợp cần một listener container đơn giản và provider có khả năng callback ổn định. Cần kiểm tra khả năng tương thích với giới hạn của application server và Jakarta EE runtime.

Không nên bật TaskExecutor để chạy listener đồng thời mà không hiểu tác động đến acknowledgment. Với SMLC, nếu listener được thực thi trên executor khác, message có thể được acknowledge trước khi listener chạy và Session có thể được dùng lại. Cách kết hợp đó không phù hợp với sessionTransacted hoặc CLIENT_ACKNOWLEDGE.

### 5.2. DefaultMessageListenerContainer

DMLC dùng vòng lặp gọi MessageConsumer.receive() để lấy message. Spring quản lý các tác vụ nhận bất đồng bộ thông qua TaskExecutor.

Đặc điểm:

- Có thể khởi chạy một số lượng consumer cố định.
- Có thể cấu hình min/max consumer để tự tăng giảm theo tải.
- Có cơ chế tự phục hồi khi broker tạm thời không khả dụng.
- Hỗ trợ native JMS transaction.
- Hỗ trợ external transaction manager như JTA.
- Quản lý việc lấy lại Connection, Session và MessageConsumer khi cần.
- Cho phép dừng, khởi động lại và thay đổi cấu hình khi ứng dụng đang chạy.

DMLC thường là lựa chọn mặc định phù hợp cho ứng dụng Spring JMS cần khả năng phục hồi và quản lý concurrency.

Ví dụ đặt giới hạn concurrency:

~~~java
factory.setConcurrency("2-8");
~~~

Container duy trì tối thiểu hai consumer và có thể tăng lên tối đa tám consumer khi tải tăng. Khi tải giảm, nó có thể thu hẹp về mức cơ bản.

Với queue, nhiều consumer có thể chia nhau message. Khi tăng consumer, thứ tự xử lý tổng thể có thể thay đổi vì nhiều message được xử lý đồng thời.

Với Topic, không nên tùy tiện tăng consumer. Trong cấu hình thông thường, nhiều consumer trên cùng node có thể nhận bản sao của cùng message. Nếu cần chia tải trên Topic, hãy thiết kế shared subscription và kiểm tra hỗ trợ của provider.

## 6. Đường đi của một message từ broker tới listener

Khi container đã chạy, quá trình nhận một message thường diễn ra như sau:

**Bước 1 — Mở tài nguyên JMS**

Container sử dụng ConnectionFactory để lấy Connection, tạo Session và đăng ký MessageConsumer với destination. Tùy container và cache level, các tài nguyên có thể được tái sử dụng trong suốt vòng đời consumer.

**Bước 2 — Chờ message**

DMLC gọi receive() trong các invoker task. SMLC đăng ký callback để provider gọi khi message đến.

**Bước 3 — Nhận JMS Message**

Provider chuyển một JMS Message tới container. Message có thể là TextMessage, BytesMessage, MapMessage, ObjectMessage hoặc loại message khác.

**Bước 4 — Chuyển đổi message**

Nếu endpoint là phương thức @JmsListener nhận String hoặc DTO, Spring dùng MessageConverter để chuyển payload sang kiểu Java. Nếu listener nhận trực tiếp jakarta.jms.Message, nó có thể truy cập các thuộc tính JMS gốc.

**Bước 5 — Gọi listener**

Spring adapter chuẩn bị đối số phương thức, ánh xạ payload, header và các tham số được chú thích, sau đó gọi phương thức listener.

**Bước 6 — Hoàn tất transaction/acknowledgment**

Sau khi listener chạy xong, container thực hiện commit hoặc acknowledgment theo cấu hình. Nếu listener ném exception trong một JMS transaction, container có thể rollback để provider giao lại message.

**Bước 7 — Tiếp tục nhận**

Consumer tiếp tục chờ message tiếp theo cho tới khi container dừng hoặc cần tái tạo tài nguyên.

~~~text
Broker
  |
  | JMS Message
  v
MessageConsumer
  |
  v
Listener Container
  |
  | nhận message qua receive() hoặc callback
  v
Message conversion / listener adapter
  |
  v
@JmsListener method
  |
  | xử lý nghiệp vụ
  v
Transaction / acknowledgment
  |
  +---- commit ----> Broker xác nhận
  |
  +---- rollback --> Broker có thể giao lại
~~~

Container thực hiện việc điều phối. Phương thức listener vẫn là nơi ứng dụng quyết định nghiệp vụ thành công hay thất bại.

## 7. Cách listener nhận dữ liệu và headers

Spring hỗ trợ nhiều kiểu tham số cho phương thức @JmsListener.

Nhận payload String:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    System.out.println(payload);
}
~~~

Nhận DTO:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(OrderCreated event) {
    System.out.println(event.orderId());
}
~~~

Nhận Spring Message:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        org.springframework.messaging.Message<OrderCreated> message) {

    System.out.println(message.getPayload().orderId());
    System.out.println(message.getHeaders());
}
~~~

Nhận JMS Message gốc:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(jakarta.jms.Message message) throws JMSException {
    System.out.println(message.getJMSMessageID());
    System.out.println(message.getJMSRedelivered());
}
~~~

Lấy header hoặc property:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        String payload,
        @Header("eventType") String eventType,
        @Header(name = "priority", required = false) Integer priority) {

    System.out.println(eventType + ": " + payload);
    System.out.println("priority = " + priority);
}
~~~

Spring có thể ánh xạ JMS properties và headers vào tham số listener. Kiểu chuyển đổi phụ thuộc MessageConverter và các converter đã cấu hình. Nếu property không tồn tại, tham số required mặc định có thể gây lỗi ánh xạ; dùng required=false hoặc giá trị mặc định phù hợp khi property là tùy chọn.

Với payload DTO, cần cấu hình converter tương ứng, chẳng hạn JSON MessageConverter. Không nên mặc định mọi JMS provider đều tự hiểu một object Java tùy ý.

## 8. MessageListener, MessageListenerAdapter và @JmsListener

Có ba cách thường gặp để nối message với code ứng dụng.

### Triển khai MessageListener trực tiếp

~~~java
public class OrderMessageListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        System.out.println("Received a JMS message");
    }
}
~~~

Sau đó gắn listener vào container bằng setMessageListener(). Cách này gần với JMS API và phù hợp khi cần làm việc trực tiếp với Message.

### Dùng MessageListenerAdapter

MessageListenerAdapter cho phép ủy quyền xử lý cho một POJO method. Nó chuyển payload và gọi phương thức delegate theo cấu hình.

~~~java
@Bean
public MessageListenerAdapter orderAdapter(OrderDelegate delegate) {
    MessageListenerAdapter adapter =
            new MessageListenerAdapter(delegate);

    adapter.setDefaultListenerMethod("handleOrder");
    return adapter;
}
~~~

~~~java
public class OrderDelegate {

    public void handleOrder(String payload) {
        System.out.println("Order: " + payload);
    }
}
~~~

Cách này hữu ích khi muốn tái sử dụng POJO và tách nó khỏi JMS API.

### Dùng @JmsListener

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handleOrder(String payload) {
        System.out.println("Order: " + payload);
    }
}
~~~

Annotation là cách khai báo endpoint gọn nhất. Spring tự đăng ký endpoint, tạo container và kết nối listener method với message adapter.

## 9. Transaction và acknowledgment trong listener container

Một message được nhận chưa có nghĩa nghiệp vụ đã hoàn tất. Container cần xác định khi nào provider được phép xem message là đã xử lý.

Các chế độ thường gặp:

| Cấu hình | Ý nghĩa |
|---|---|
| AUTO_ACKNOWLEDGE | Provider/container tự xác nhận theo ngữ nghĩa của container |
| CLIENT_ACKNOWLEDGE | Acknowledgment do phía client/container điều khiển |
| DUPS_OK_ACKNOWLEDGE | Cho phép acknowledgment theo nhóm và có thể có duplicate |
| sessionTransacted=true | Nhận message trong JMS Session transaction |

Cần đặc biệt chú ý: AUTO_ACKNOWLEDGE có ngữ nghĩa khác nhau giữa DMLC và SMLC. Với DMLC, acknowledgment mặc định diễn ra trước khi listener thực thi, nên exception từ listener không làm message được redeliver. Với SMLC, acknowledgment diễn ra sau listener invocation, nhưng exception nghiệp vụ vẫn không đảm bảo redelivery trong mọi tình huống.

Nếu cần độ tin cậy và muốn listener exception làm message được giao lại, Spring khuyến nghị dùng sessionTransacted=true hoặc external transaction manager phù hợp.

Ví dụ:

~~~java
factory.setSessionTransacted(true);
~~~

Khi listener hoàn tất bình thường, container commit transaction. Nếu listener ném exception, container rollback; provider có thể giao lại message theo chính sách redelivery của broker.

### Transaction JMS và database

Nếu listener vừa cập nhật database vừa xử lý JMS message, một local JMS transaction không tự động bao gồm database transaction.

Ví dụ có thể xảy ra:

1. Database commit thành công.
2. JMS commit thất bại.
3. Broker giao lại message.
4. Listener cập nhật database lần nữa.

Vì vậy, cần idempotency hoặc duplicate detection. Nếu cần atomic transaction qua nhiều tài nguyên, có thể dùng XA/JTA khi provider, database và transaction manager hỗ trợ. XA có chi phí và yêu cầu vận hành cao hơn, nên cần lựa chọn theo yêu cầu nhất quán.

## 10. Xử lý exception và ErrorHandler

Mặc định, listener container thường bắt exception từ listener và ghi log ở mức WARN. Exception không nhất thiết được truyền ngược tới JMS provider như một tín hiệu listener thất bại.

Có thể cấu hình ErrorHandler để ghi log có cấu trúc, phát metric hoặc chuyển lỗi tới hệ thống giám sát:

~~~java
factory.setErrorHandler(error ->
        System.err.println("[listener-error] " + error.getMessage()));
~~~

ErrorHandler quan sát lỗi phát sinh trong listener container. Nó không thay thế transaction rollback, acknowledgment hoặc broker dead-letter policy.

Cần phân biệt:

- Lỗi nghiệp vụ: ví dụ đơn hàng không hợp lệ. Có thể là kết quả từ chối hợp lệ, không nhất thiết retry.
- Lỗi tạm thời: ví dụ database tạm thời không truy cập được. Có thể rollback để retry theo chính sách.
- Lỗi cấu hình: ví dụ destination không tồn tại hoặc credential sai. Retry liên tục có thể chỉ tạo log và tải không cần thiết.
- Lỗi kết nối JMS: container có thể phục hồi theo cơ chế recovery của nó.

Hãy xác định lỗi nào cần rollback, lỗi nào cần chuyển dead-letter và lỗi nào cần dừng listener để xử lý cấu hình.

## 11. Concurrency và thứ tự xử lý

Concurrency là số consumer hoạt động đồng thời trên một endpoint.

Với DMLC:

~~~java
factory.setConcurrency("2-8");
~~~

- 2 là số consumer tối thiểu.
- 8 là số consumer tối đa.
- Container có thể tăng consumer khi tải tăng và giảm khi tải giảm.

Với SMLC, số consumer là cố định:

~~~java
factory.setConcurrency("3");
~~~

Dù API cấu hình có thể nhận chuỗi lower-upper để tương thích, SMLC giữ số consumer ở mức cố định và không tự scale động. Thường nên dùng setConcurrentConsumers() khi cấu hình trực tiếp SMLC.

Tăng consumer có thể tăng throughput của queue, nhưng có các tác động:

- Thứ tự xử lý tổng thể không còn được bảo đảm khi nhiều message chạy song song.
- Database/API phía sau phải chịu được nhiều tác vụ đồng thời.
- Số Session và consumer tăng, làm tăng tài nguyên broker.
- Retry có thể khiến message được xử lý lại song song với message khác.
- Với Topic, nhiều consumer độc lập có thể nhận bản sao của cùng message.

Nếu cần thứ tự theo một khóa nghiệp vụ, có thể phân vùng destination hoặc thiết kế cơ chế tuần tự theo key. Chỉ đặt concurrency bằng 1 không giải quyết được mọi thứ tự giữa nhiều producer hoặc nhiều destination, nhưng nó giúp đơn giản hóa thứ tự trong một consumer.

## 12. Quản lý vòng đời và giám sát container

Các container do @JmsListener tạo được JmsListenerEndpointRegistry quản lý. Registry triển khai lifecycle của Spring, vì vậy nó có thể khởi động và dừng các container theo vòng đời ApplicationContext.

Có thể truy cập registry để quản lý:

~~~java
@Component
public class ListenerLifecycleManager {

    private final JmsListenerEndpointRegistry registry;

    public ListenerLifecycleManager(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderListener");

        if (container != null) {
            container.stop();
        }
    }

    public void startOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderListener");

        if (container != null) {
            container.start();
        }
    }
}
~~~

Để tìm container theo ID, khai báo id trên annotation:

~~~java
@JmsListener(
        id = "orderListener",
        destination = "orders.queue"
)
public void handle(String payload) {
    // xử lý
}
~~~

Các container được registry quản lý không phải bean riêng trong ApplicationContext và không thể autowire trực tiếp như một bean thông thường. Hãy dùng registry để tìm và điều khiển chúng.

Các thuộc tính hữu ích:

- autoStartup: có tự khởi động endpoint khi context bắt đầu hay không.
- phase: thứ tự lifecycle tương đối khi khởi động và dừng.
- concurrency: số consumer.
- recoveryInterval: khoảng thời gian thử khôi phục khi kết nối lỗi.
- shutdownTimeout: thời gian chờ khi dừng container trong các cấu hình hỗ trợ.

Trong vận hành, nên theo dõi số consumer đang hoạt động, queue depth, message age, thời gian xử lý, số lần redelivery, lỗi listener, lỗi kết nối và thời gian recovery.

## 13. Cấu hình thủ công khi không dùng @JmsListener

Có thể tạo container trực tiếp bằng Java config:

~~~java
@Bean
public DefaultMessageListenerContainer orderContainer(
        ConnectionFactory connectionFactory,
        OrderMessageListener listener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(listener);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(2);

    return container;
}
~~~

Cách này phù hợp khi cần tạo endpoint động, cấu hình đặc biệt hoặc muốn khai báo container tường minh. Spring quản lý lifecycle của bean container và gọi start/stop theo cấu hình.

Nếu chỉ cần một listener method thông thường, @JmsListener thường ít boilerplate hơn. Cả hai cách đều dựa trên cùng abstraction MessageListenerContainer.

## 14. Ví dụ hoàn chỉnh: @JmsListener với Artemis và DMLC

Ví dụ dưới đây tạo một Spring ApplicationContext, đăng ký listener bằng @JmsListener, gửi một message qua JmsTemplate và chờ listener xử lý. Spring sử dụng DefaultJmsListenerContainerFactory để tạo DMLC.

Chương trình dùng Java 17, Spring Framework 6.2.19 và Artemis Jakarta JMS client 2.40.0. Nó cần một Artemis broker đang chạy, có queue tên orders.queue và thông tin đăng nhập phù hợp. Ví dụ không tự khởi động broker.

Cấu trúc dự án:

~~~text
listener-container-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── JmsConfiguration.java
                ├── OrderListener.java
                └── ListenerContainerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>listener-container-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/JmsConfiguration.java

~~~java
package demo;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean(destroyMethod = "close")
    public ActiveMQConnectionFactory connectionFactory() {
        String url = System.getenv().getOrDefault(
                "JMS_BROKER_URL", "tcp://localhost:61616");

        String user = System.getenv("JMS_BROKER_USER");
        String password = System.getenv("JMS_BROKER_PASSWORD");

        if (user != null && password != null) {
            return new ActiveMQConnectionFactory(url, user, password);
        }

        return new ActiveMQConnectionFactory(url);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ActiveMQConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");

        return factory;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ActiveMQConnectionFactory connectionFactory) {

        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public OrderListener orderListener() {
        return new OrderListener();
    }
}
~~~

### src/main/java/demo/OrderListener.java

~~~java
package demo;

import org.springframework.jms.annotation.JmsListener;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class OrderListener {

    private final CountDownLatch received = new CountDownLatch(1);

    @JmsListener(
            id = "ordersListener",
            destination = "orders.queue"
    )
    public void handle(String payload) {
        System.out.println("[listener] received = " + payload);
        received.countDown();
    }

    public boolean awaitMessage(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

### src/main/java/demo/ListenerContainerDemo.java

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jms.core.JmsTemplate;

import java.util.concurrent.TimeUnit;

public class ListenerContainerDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JmsConfiguration.class)) {

            JmsTemplate jmsTemplate = context.getBean(JmsTemplate.class);
            OrderListener listener = context.getBean(OrderListener.class);

            jmsTemplate.convertAndSend(
                    "orders.queue",
                    "Order #1024 created"
            );

            if (!listener.awaitMessage(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for the listener");
            }

            System.out.println("[main] listener completed");
        }
    }
}
~~~

Chạy trong thư mục chứa pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.ListenerContainerDemo
~~~

Nếu broker đang chạy ở localhost:61616, queue đã tồn tại và không yêu cầu credential riêng, output dự kiến:

~~~text
[listener] received = Order #1024 created
[main] listener completed
~~~

Nếu broker yêu cầu đăng nhập, đặt biến môi trường trước khi chạy. Ví dụ PowerShell:

~~~powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_BROKER_USER = "your-user"
$env:JMS_BROKER_PASSWORD = "your-password"
mvn -q compile exec:java -Dexec.mainClass=demo.ListenerContainerDemo
~~~

### Phân tích ví dụ

1. JmsConfiguration bật @EnableJms để Spring phát hiện listener endpoint.
2. ConnectionFactory tạo kết nối tới Artemis broker.
3. jmsListenerContainerFactory cung cấp cấu hình cho DMLC: JMS transaction và concurrency từ 1 đến 3.
4. OrderListener có @JmsListener nên được đăng ký thành một endpoint.
5. JmsListenerEndpointRegistry tạo và quản lý container cho endpoint này.
6. Container tạo consumer trên orders.queue và chờ message.
7. JmsTemplate gửi chuỗi vào queue.
8. Container nhận JMS TextMessage, chuyển payload thành String và gọi OrderListener.handle().
9. Listener in payload rồi giảm CountDownLatch.
10. Main thread nhận tín hiệu và in thông báo hoàn tất.
11. Khi ApplicationContext đóng, registry dừng listener container và Spring đóng các bean theo lifecycle.

Ví dụ dùng sessionTransacted=true. Nếu listener ném exception, container rollback JMS transaction và broker có thể giao lại message. Trong ví dụ thành công, transaction được commit sau khi listener hoàn tất.

Ví dụ yêu cầu broker thực tế để kiểm tra đường truyền. Nếu chỉ chạy Maven compile, ta mới xác nhận dependency và source code biên dịch; cần integration test với broker để xác nhận kết nối, quyền truy cập, queue và transaction.

## 15. Những lỗi thường gặp

**Quên @EnableJms:** Spring không kích hoạt hạ tầng phát hiện @JmsListener, nên phương thức listener không được đăng ký.

**Bean listener không thuộc ApplicationContext:** annotation chỉ được phát hiện trên Spring-managed bean. Tạo listener bằng new trong code không tự đăng ký endpoint.

**Thiếu container factory:** nếu không khai báo containerFactory trên annotation, Spring tìm bean mặc định jmsListenerContainerFactory. Sai tên bean có thể làm ApplicationContext khởi tạo thất bại.

**Destination sai hoặc không tồn tại:** provider có thể từ chối tạo consumer hoặc gửi message. Kiểm tra queue/topic và chính sách auto-create của broker.

**Dùng nhầm queue và topic:** factory mặc định dùng queue domain. Nếu nhận Topic, cấu hình pubSubDomain=true hoặc factory riêng phù hợp.

**Tăng concurrency mà không xét thứ tự:** nhiều consumer có thể xử lý song song và hoàn thành theo thứ tự khác thứ tự gửi.

**Tăng consumer trên Topic không có shared subscription:** mỗi consumer có thể nhận bản sao riêng. Kiểm tra subscription mode và khả năng của provider trước khi tăng concurrency.

**Dựa vào AUTO_ACKNOWLEDGE để đảm bảo redelivery:** ngữ nghĩa khác nhau giữa DMLC và SMLC. Dùng sessionTransacted=true hoặc external transaction manager khi cần hành vi rollback nhất quán.

**Cho rằng exception listener luôn làm broker gửi lại message:** exception có thể chỉ được ghi log hoặc chuyển tới ErrorHandler. Redelivery phụ thuộc transaction, acknowledgment và broker policy.

**Nhầm listener container với JmsTemplate:** JmsTemplate phục vụ thao tác gửi/nhận đồng bộ; listener container quản lý nhận message bất đồng bộ và gọi listener.

**Không dừng container đúng vòng đời:** container giữ Connection, Session và consumer. Hãy để Spring quản lý lifecycle hoặc gọi stop/destroy nếu tự tạo thủ công.

**Bỏ qua duplicate processing:** message có thể được giao lại sau rollback, mất kết nối hoặc lỗi ở thời điểm commit. Listener nên idempotent hoặc có cơ chế phát hiện xử lý trùng.

## 16. Checklist thiết kế và vận hành listener

- ConnectionFactory đã trỏ tới đúng JMS provider và broker.
- Queue/Topic và destination resolver đã được cấu hình.
- @EnableJms được bật và listener là Spring-managed bean.
- Mỗi endpoint dùng đúng container factory.
- Container type được chọn theo yêu cầu recovery, transaction và concurrency.
- Số consumer phù hợp với tải và giới hạn broker.
- MessageConverter chuyển đổi đúng payload và headers.
- Transaction và acknowledgment có chính sách rõ ràng.
- ErrorHandler, retry, redelivery và dead-letter policy đã được kiểm thử.
- Listener có xử lý idempotent nếu message có thể được giao lại.
- Registry và container được dừng đúng lifecycle.
- Metric theo dõi consumer count, queue depth, message age, processing time và recovery.
- Integration test chạy với provider/broker tương thích môi trường triển khai.

## 17. Ghi nhớ

- Listener là code nghiệp vụ; listener container quản lý việc kết nối, đăng ký consumer, nhận message và gọi listener.
- @JmsListener khai báo endpoint trên Spring-managed bean; @EnableJms bật hạ tầng phát hiện annotation.
- JmsListenerContainerFactory tạo container theo cấu hình cho từng endpoint.
- JmsListenerEndpointRegistry quản lý lifecycle và cho phép tìm container theo endpoint ID.
- SimpleMessageListenerContainer dùng callback của JMS provider và giữ số consumer cố định.
- DefaultMessageListenerContainer dùng vòng lặp receive(), có recovery và hỗ trợ concurrency động cùng external transaction manager.
- Message được chuyển đổi qua MessageConverter trước khi vào listener method nếu method nhận payload Java.
- sessionTransacted=true giúp rollback khi listener thất bại và hỗ trợ redelivery theo chính sách broker.
- Tăng concurrency có thể tăng throughput của queue nhưng ảnh hưởng thứ tự; với Topic phải xem xét subscription và khả năng nhận bản sao.
- Container không bảo đảm exactly-once nghiệp vụ; listener cần chịu được redelivery và xử lý trùng.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using Spring JMS and listener containers](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [SimpleMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
