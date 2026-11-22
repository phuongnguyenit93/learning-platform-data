# Đăng ký Topic bền vững, không bền vững và chia sẻ

Trong mô hình publish/subscribe của JMS, publisher gửi message tới một Topic và subscriber nhận các message thông qua một subscription. Subscription quyết định message nào được giữ lại và consumer nào có thể nhận chúng. Vì vậy, cần phân biệt Topic, subscription và consumer trước khi chọn cách đăng ký.

Jakarta Messaging định nghĩa hai trục độc lập cho subscription:

- **Durable / non-durable:** subscription có tiếp tục tồn tại và tích lũy message khi không có consumer hoạt động hay không.
- **Shared / unshared:** một subscription có cho phép một hay nhiều consumer hoạt động đồng thời.

Kết hợp hai trục này tạo ra bốn kiểu: unshared non-durable, unshared durable, shared non-durable và shared durable. Bài này giải thích vòng đời, cách định danh, cách dùng API Jakarta Messaging và cách cấu hình listener trong Spring Framework.

## 1. Topic, subscription và consumer

Ba khái niệm có vai trò khác nhau:

**Topic** là destination mà publisher gửi message tới. Topic đại diện cho luồng sự kiện, chẳng hạn orders.events hoặc inventory.updates.

**Subscription** là trạng thái nhận message do messaging provider quản lý. Nó xác định một consumer hoặc một nhóm consumer quan tâm tới Topic nào, có thể kèm message selector và các thuộc tính khác.

**Consumer** là đối tượng trong ứng dụng dùng để nhận message từ subscription. Consumer có thể được tạo, đóng và tạo lại; vòng đời của subscription phụ thuộc vào kiểu đăng ký.

Có thể hình dung:

~~~text
Publisher
    |
    | publish M1, M2, M3
    v
  Topic: orders.events
    |
    +--------------------------+
    |                          |
    v                          v
Subscription A             Subscription B
    |                          |
    v                          v
Consumer A                 Consumer B
    |                          |
    v                          v
Nhận M1, M2, M3            Nhận M1, M2, M3
~~~

Mỗi subscription độc lập nhận một bản sao của message phù hợp với subscription đó. Nếu có hai subscription khác nhau trên cùng Topic, mỗi subscription có thể nhận cùng một message.

Nếu một subscription là shared và có nhiều consumer, mỗi message thuộc subscription đó chỉ được giao cho một consumer trong nhóm. Các consumer cùng chia sẻ công việc xử lý message của một subscription.

Đây là điểm quan trọng: **nhiều subscription trên cùng Topic tạo ra nhiều luồng nhận độc lập; nhiều consumer trên cùng shared subscription chia nhau một luồng nhận.**

## 2. Hai trục phân loại subscription

### Durable và non-durable

**Non-durable subscription** chỉ tồn tại khi có consumer hoạt động. Message được gửi tới Topic khi không có consumer thuộc subscription sẽ không được lưu cho lần đăng ký sau. Khi consumer cuối cùng đóng, subscription non-durable bị xóa cùng các message chưa giao còn lại.

**Durable subscription** được messaging provider lưu lại ngay cả khi không có consumer hoạt động. Message gửi tới Topic trong thời gian subscriber offline có thể được tích lũy để giao khi consumer kết nối lại. Subscription tiếp tục tồn tại cho tới khi ứng dụng xóa nó bằng thao tác unsubscribe, hoặc theo chính sách quản trị của provider.

Durable subscription phù hợp với consumer cần tiếp tục nhận sự kiện sau khi ứng dụng tạm dừng, triển khai lại hoặc mất kết nối.

### Shared và unshared

**Unshared subscription** chỉ cho phép một consumer hoạt động tại một thời điểm. Nếu consumer khác cố gắng mở cùng unshared subscription trong lúc consumer hiện tại chưa đóng, provider sẽ từ chối.

**Shared subscription** cho phép nhiều consumer cùng tham gia một subscription. Provider phân phối mỗi message của subscription cho một consumer trong nhóm. Cơ chế phân phối cụ thể giữa các consumer phụ thuộc provider; đặc tả Jakarta Messaging không quy định thuật toán cân bằng tải cụ thể.

Shared subscription hữu ích khi cần tăng khả năng xử lý bằng nhiều consumer mà vẫn duy trì một subscription logic.

## 3. Bốn kiểu đăng ký Topic

| Kiểu | Định danh | Consumer đồng thời | Khi consumer cuối cùng đóng |
|---|---|---:|---|
| Unshared non-durable | Không có tên subscription | 1 | Subscription và message chưa giao bị xóa |
| Unshared durable | Client ID + subscription name | 1 | Subscription tiếp tục tồn tại, tích lũy message |
| Shared non-durable | Subscription name và client ID tùy chọn | Nhiều | Subscription và message chưa giao bị xóa |
| Shared durable | Subscription name và client ID tùy chọn | Nhiều | Subscription tiếp tục tồn tại, tích lũy message |

### 3.1. Unshared non-durable

Đây là kiểu đăng ký đơn giản nhất. Ứng dụng tạo consumer trên Topic; provider tạo một subscription riêng cho consumer đó.

Đặc điểm:

- Không cần đặt subscription name.
- Chỉ một consumer gắn với subscription.
- Message chỉ được thêm vào subscription khi consumer đang hoạt động.
- Đóng consumer sẽ xóa subscription và các message chưa giao.

Phù hợp với màn hình theo dõi trực tiếp, thông báo tạm thời hoặc client chỉ quan tâm sự kiện trong lúc đang kết nối.

Nếu người dùng mở lại ứng dụng sau khi đã offline, ứng dụng không nhận lại những message đã phát trong thời gian không có consumer.

### 3.2. Unshared durable

Ứng dụng tạo một subscription có tên và gắn nó với client identifier. Provider lưu trạng thái subscription khi consumer đóng.

Đặc điểm:

- Cần một subscription name ổn định.
- Client ID phải được thiết lập trước khi tạo consumer.
- Chỉ có một consumer hoạt động trên subscription tại một thời điểm.
- Đóng consumer không xóa subscription.
- Message gửi trong thời gian không có consumer được giữ lại theo chính sách retention, expiration và khả năng của provider.
- Ứng dụng phải gọi unsubscribe để xóa subscription khi không còn sử dụng.

Đây là lựa chọn phù hợp cho một dịch vụ audit hoặc một ứng dụng cần nhận lại các sự kiện đã phát trong thời gian dịch vụ tạm dừng.

Subscription name phải ổn định qua các lần restart. Nếu mỗi lần khởi động ứng dụng lại tạo một tên ngẫu nhiên, provider sẽ xem đó là subscription mới; subscription cũ có thể tiếp tục tích lũy message và chiếm tài nguyên.

### 3.3. Shared non-durable

Kiểu này cho phép nhiều consumer cùng đọc một subscription nhưng subscription chỉ tồn tại khi có ít nhất một consumer hoạt động.

Đặc điểm:

- Có subscription name.
- Client ID có thể được bỏ trống; nếu đã được dùng khi tạo subscription thì consumer sau phải dùng cùng client ID.
- Có thể có nhiều consumer đồng thời.
- Mỗi message thuộc subscription chỉ được giao cho một consumer trong nhóm.
- Khi consumer cuối cùng đóng, subscription và các message chưa giao bị xóa.

Kiểu này phù hợp khi cần chia tải xử lý trong lúc ứng dụng đang hoạt động, nhưng không cần lưu message khi toàn bộ consumer dừng.

### 3.4. Shared durable

Đây là kết hợp giữa khả năng lưu subscription khi offline và khả năng chia tải cho nhiều consumer.

Đặc điểm:

- Có subscription name.
- Client ID là tùy chọn theo Jakarta Messaging; nếu subscription được tạo với client ID thì consumer sau phải dùng cùng client ID.
- Nhiều consumer có thể hoạt động đồng thời trên cùng subscription.
- Mỗi message chỉ được giao cho một consumer trong nhóm.
- Khi toàn bộ consumer đóng, subscription vẫn tồn tại và tiếp tục tích lũy message cho tới khi được unsubscribe hoặc message hết hạn.

Shared durable phù hợp với một nhóm worker cần cùng xử lý một luồng sự kiện, đồng thời vẫn muốn giữ backlog trong thời gian cả nhóm tạm dừng.

## 4. Phân biệt broadcast và chia tải

Một Topic có thể có nhiều subscription độc lập. Mỗi subscription nhận bản sao của các message phù hợp:

~~~text
                    Topic: orders.events
                       |
             +---------+---------+
             |                   |
             v                   v
       Subscription A      Subscription B
       Audit service        Analytics service
             |                   |
             v                   v
        Consumer A           Consumer B
        Nhận M1, M2           Nhận M1, M2
~~~

Nếu Subscription A là shared với ba consumer, ba consumer không nhận ba bản sao của mỗi message. Chúng chia nhau message thuộc Subscription A:

~~~text
               Subscription A (shared)
                         |
              +----------+----------+
              |          |          |
              v          v          v
          Consumer 1 Consumer 2 Consumer 3
              \          |          /
               \         |         /
                M1, M2, M3 được
                phân phối trong nhóm
~~~

Đặc tả không quy định message nào nhất định phải tới consumer nào. Không nên dựa vào việc một consumer cụ thể luôn nhận một partition hoặc một phần cố định của luồng nếu provider không có bảo đảm riêng.

## 5. Định danh subscription: client ID và subscription name

### Client identifier

Client ID định danh một client JMS ở cấp Connection. Với unshared durable subscription, client ID là bắt buộc và phải được đặt trước khi tạo consumer.

Client ID cần:

- Duy nhất giữa các Connection đang hoạt động của cùng provider.
- Ổn định khi ứng dụng muốn mở lại durable subscription cũ.
- Được đặt trước khi tạo session/consumer liên quan.
- Không bị gán trùng bởi cấu hình sẵn có của ConnectionFactory.

Một Connection đã có client ID không thể tùy tiện đổi sang ID khác. Nếu dùng Spring listener container, client ID có thể được cấu hình trên container factory hoặc container.

### Subscription name

Subscription name là tên logic do ứng dụng chọn. Với unshared durable subscription, identity được tạo từ client ID và subscription name. Với shared subscription, identity dựa trên subscription name và client ID tùy chọn.

Quy tắc đặt tên tốt:

- Dùng tên ổn định, có ý nghĩa nghiệp vụ.
- Phân biệt các nhóm nhận khác nhau, ví dụ orders-audit-v1 và orders-workers-v1.
- Không tạo tên ngẫu nhiên mỗi lần restart.
- Không để hai ứng dụng vô tình dùng chung identity khi chúng cần nhận độc lập.
- Thay đổi tên có chủ đích khi muốn tạo subscription mới hoặc thay đổi hợp đồng nhận.

Một durable subscription có thể tiếp tục tích lũy message sau khi ứng dụng đã dừng. Nếu không còn cần nó, phải dừng consumer và xóa subscription đúng cách.

## 6. API Jakarta Messaging để tạo consumer

Jakarta Messaging 3.1 cung cấp các phương thức cho bốn kiểu subscription. Các phương thức tương ứng có trên JMSContext và Session.

| Kiểu subscription | JMSContext API |
|---|---|
| Unshared non-durable | createConsumer(topic) |
| Unshared durable | createDurableConsumer(topic, name) |
| Shared non-durable | createSharedConsumer(topic, name) |
| Shared durable | createSharedDurableConsumer(topic, name) |

Các phương thức shared được bổ sung từ JMS 2.0. Broker/provider cần hỗ trợ shared subscription. Nếu provider chỉ hỗ trợ JMS 1.1 hoặc không triển khai tính năng shared, các phương thức này có thể không hoạt động.

### 6.1. Tạo unshared non-durable consumer

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    JMSConsumer consumer = context.createConsumer(topic);
    // Consumer chỉ nhận message khi đang hoạt động.
}
~~~

Không có subscription name. Consumer đóng thì subscription bị xóa.

### 6.2. Tạo unshared durable consumer

~~~java
try (JMSContext context =
        connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

    context.setClientID("orders-audit-service");

    try (JMSConsumer consumer =
            context.createDurableConsumer(topic, "orders-audit-v1")) {

        Message message = consumer.receive(5000);

        if (message instanceof TextMessage textMessage) {
            System.out.println(textMessage.getText());
        }
    }
}
~~~

Client ID được đặt trước khi tạo consumer. Nếu ứng dụng đóng consumer rồi khởi động lại, nó phải dùng cùng client ID và subscription name để mở lại durable subscription.

Ví dụ sử dụng AUTO_ACKNOWLEDGE để ngắn gọn. Với xử lý nghiệp vụ cần độ tin cậy cao, hãy cân nhắc transaction và acknowledgment phù hợp.

### 6.3. Tạo shared non-durable consumer

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    JMSConsumer consumer =
            context.createSharedConsumer(topic, "orders-live-workers");

    // Có thể tạo thêm consumer khác dùng cùng subscription name.
}
~~~

Các consumer khác có thể dùng cùng Topic và subscription name để tham gia subscription. Mỗi message thuộc subscription sẽ được giao cho một consumer trong nhóm.

### 6.4. Tạo shared durable consumer

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    JMSConsumer consumer =
            context.createSharedDurableConsumer(topic, "orders-workers-v1");

    // Consumer khác có thể tham gia cùng shared durable subscription.
}
~~~

Shared durable subscription có thể được mở lại sau khi toàn bộ consumer đã đóng. Client ID có thể không cần thiết theo đặc tả; nếu ứng dụng/provider dùng client ID khi tạo subscription, phải dùng lại cùng giá trị.

Đây là các đoạn API minh họa. Chúng cần một ConnectionFactory và Topic đã được cấu hình bởi JMS provider. Chúng không phải chương trình độc lập có thể chạy mà không có broker.

## 7. Cấu hình subscription bằng Spring Framework

Spring JMS cung cấp JmsTemplate để gửi message và listener container để nhận message. Với annotation-driven listener, có thể dùng @JmsListener và DefaultJmsListenerContainerFactory.

Các thuộc tính liên quan:

- pubSubDomain: xác định listener làm việc với Topic.
- subscriptionDurable: bật durable subscription.
- subscriptionShared: bật shared subscription.
- clientId: client identifier cho Connection được listener container sử dụng.
- subscription: tên subscription trên @JmsListener.
- concurrency: số consumer đồng thời mà listener container tạo.

Ví dụ cấu hình Spring:

~~~java
@Configuration
@EnableJms
public class TopicMessagingConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setClientId("orders-audit-service");
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setSubscriptionShared(true);
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory sharedNonDurableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionShared(true);
        factory.setSessionTransacted(true);

        return factory;
    }

    @Bean
    public JmsTemplate topicJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);
        return template;
    }
}
~~~

Tên subscription được khai báo trên listener:

~~~java
@Component
public class OrderTopicListeners {

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-audit-v1",
            containerFactory = "durableTopicFactory"
    )
    public void audit(OrderEvent event) {
        System.out.println("[audit] " + event.orderId());
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-workers-v1",
            containerFactory = "sharedDurableTopicFactory",
            concurrency = "3-8"
    )
    public void process(OrderEvent event) {
        System.out.println("[worker] " + event.orderId());
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-live-workers",
            containerFactory = "sharedNonDurableTopicFactory",
            concurrency = "2-4"
    )
    public void updateLiveView(OrderEvent event) {
        System.out.println("[live] " + event.orderId());
    }
}
~~~

Ví dụ trên minh họa ba subscription độc lập trên cùng Topic:

- orders-audit-v1 là durable unshared, có client ID ổn định và một consumer.
- orders-workers-v1 là shared durable, có thể có nhiều consumer cùng chia tải.
- orders-live-workers là shared non-durable, nhiều consumer chia tải khi nhóm đang hoạt động.

Mỗi subscription độc lập có thể nhận bản sao của cùng một event. Các consumer trong shared subscription chỉ chia nhau message thuộc subscription của chính nhóm đó.

Ứng dụng phải cung cấp ConnectionFactory tương thích với Jakarta Messaging 3.1 hoặc JMS 2.0 trở lên cho các tính năng shared. Broker cụ thể, destination và cách cấu hình kết nối phụ thuộc provider. Đoạn Spring trên là cấu hình tích hợp; nó không tự khởi động broker.

Có thể gửi event qua Topic bằng JmsTemplate:

~~~java
topicJmsTemplate.convertAndSend(
        "orders.events",
        new OrderEvent("ORD-1024")
);
~~~

Ví dụ DTO:

~~~java
public record OrderEvent(String orderId) {
}
~~~

Spring sử dụng MessageConverter để chuyển payload Java thành JMS Message và chuyển ngược lại ở listener. Cần cấu hình converter phù hợp nếu provider hoặc ứng dụng dùng định dạng JSON riêng.

## 8. Acknowledgment, transaction và độ bền dữ liệu

Durable subscription và message delivery mode là hai khái niệm khác nhau.

**Durable subscription** quyết định subscription có tồn tại và tích lũy message khi không có consumer hay không.

**DeliveryMode.PERSISTENT / NON_PERSISTENT** quyết định mức bảo đảm lưu trữ message của provider khi có sự cố. Durable subscription không tự biến mọi message thành persistent message.

Ngoài ra, message có thể hết hạn theo time-to-live hoặc bị ảnh hưởng bởi giới hạn lưu trữ, chính sách retention và quản trị của broker. Vì vậy, durable không nên được diễn giải thành bảo đảm giữ message vô thời hạn.

Acknowledgment quyết định khi nào provider xem message đã được xử lý:

- AUTO_ACKNOWLEDGE: provider tự xác nhận theo quy tắc của session.
- CLIENT_ACKNOWLEDGE: ứng dụng chủ động xác nhận message.
- DUPS_OK_ACKNOWLEDGE: cho phép provider xác nhận theo nhóm và có thể phát lại message.
- SESSION_TRANSACTED: thao tác nhận và acknowledgment nằm trong transaction của JMS session.

Với Spring listener container, cấu hình sessionTransacted=true giúp exception trong listener dẫn tới rollback session và cho phép provider giao lại message theo chính sách của nó.

Không nên dựa vào durable subscription để thay thế transaction, acknowledgment hoặc idempotency. Consumer vẫn cần chịu được việc message được giao lại sau lỗi hoặc rollback.

## 9. Selector và các thuộc tính subscription

Một subscription có thể dùng message selector để chỉ nhận message có property phù hợp.

Ví dụ:

~~~java
JMSConsumer consumer = context.createDurableConsumer(
        topic,
        "priority-orders-v1",
        "priority = 'HIGH'",
        false
);
~~~

Selector lọc theo message properties, không phải tùy ý truy vấn payload Java. Publisher cần đặt property tương ứng trên JMS Message.

Khi tạo lại consumer trên durable subscription hiện có, ứng dụng phải tuân thủ các thuộc tính định nghĩa subscription như Topic và selector. Không nên cho rằng có thể thay selector tùy ý trên một subscription đang tồn tại.

Một số API unshared còn hỗ trợ noLocal để ngăn consumer nhận message được publish từ chính connection của nó. noLocal không phải tham số dùng chung cho mọi kiểu shared subscription; hãy kiểm tra overload tương ứng của Jakarta Messaging API.

## 10. Vòng đời và xóa durable subscription

Đóng consumer và xóa durable subscription là hai thao tác khác nhau.

- Đóng consumer chỉ giải phóng consumer object.
- Durable subscription vẫn còn và tiếp tục tích lũy message.
- Unsubscribe xóa durable subscription cùng trạng thái message chưa giao của nó.

Ví dụ xóa một unshared durable subscription:

~~~java
try (JMSContext context = connectionFactory.createContext()) {
    context.setClientID("orders-audit-service");
    context.unsubscribe("orders-audit-v1");
}
~~~

Trước khi unsubscribe:

1. Dừng listener container hoặc đóng tất cả consumer đang sử dụng subscription.
2. Bảo đảm không còn transaction hoặc message chưa acknowledgment liên quan.
3. Dùng đúng client ID và subscription name.
4. Chỉ xóa khi nghiệp vụ không còn cần backlog của subscription.

Nếu subscription đang có consumer hoạt động hoặc còn message thuộc transaction chưa hoàn tất, provider có thể từ chối thao tác xóa.

Shared durable subscription cũng cần được quản lý vòng đời có chủ đích. Nếu không còn cần subscription, hãy dừng toàn bộ consumer trong nhóm rồi unsubscribe theo identity mà provider sử dụng.

## 11. Chọn kiểu subscription theo nhu cầu

| Nhu cầu | Kiểu phù hợp | Lý do |
|---|---|---|
| Client chỉ nhận sự kiện khi đang mở | Unshared non-durable | Đơn giản, không giữ backlog offline |
| Một service phải nhận lại sự kiện sau restart | Unshared durable | Subscription tồn tại khi consumer offline |
| Nhiều worker chia tải trong lúc hệ thống hoạt động | Shared non-durable | Nhiều consumer cùng một subscription, không giữ backlog khi nhóm dừng |
| Nhiều worker chia tải và cần backlog khi toàn nhóm offline | Shared durable | Kết hợp chia tải và lưu subscription |

Một vài ví dụ thực tế:

**Audit service:** dùng durable unshared nếu chỉ có một consumer logic và cần nhận lại event sau khi triển khai lại.

**Notification dashboard:** dùng non-durable nếu chỉ cần cập nhật khi client đang kết nối. Người dùng mở lại dashboard không nhất thiết phải nhận toàn bộ sự kiện cũ.

**Image processing workers:** dùng shared durable nếu nhiều worker cần chia tải và message cần được giữ khi toàn bộ worker tạm dừng.

**Live telemetry processors:** dùng shared non-durable nếu nhiều consumer chia tải dữ liệu trong phiên hoạt động, nhưng dữ liệu cũ không cần phát lại sau khi nhóm dừng.

## 12. Những lỗi thường gặp

**Nhầm Topic với subscription:** Topic là destination phát message; subscription là trạng thái nhận. Nhiều subscription trên một Topic có thể nhận cùng message độc lập.

**Cho rằng shared nghĩa là broadcast tới tất cả consumer:** sai. Shared subscription giao mỗi message cho một consumer trong nhóm. Muốn nhiều nhóm độc lập cùng nhận event, tạo nhiều subscription.

**Cho rằng durable có nghĩa giữ message vô thời hạn:** sai. Message có thể hết hạn, bị giới hạn bởi dung lượng hoặc chính sách broker. Durable subscription vẫn cần quản trị backlog.

**Dùng cùng durable subscription name nhưng client ID khác:** với unshared durable, identity gồm cả client ID và subscription name. Client khác có thể vô tình tạo subscription khác thay vì tiếp tục subscription cũ.

**Tạo subscription name ngẫu nhiên mỗi lần chạy:** provider xem mỗi tên là subscription mới. Subscription cũ có thể còn tồn tại và tích lũy message.

**Mở nhiều consumer trên unshared durable:** chỉ một consumer hoạt động được phép. Muốn chia tải, dùng shared durable subscription.

**Tăng concurrency trên Topic không có shared subscription:** có thể tạo các subscription/consumer độc lập hoặc vi phạm ràng buộc của subscription, dẫn tới nhận message lặp hoặc lỗi khởi tạo. Chỉ tăng concurrency khi cấu hình shared subscription và provider hỗ trợ.

**Cho rằng Spring tự tạo broker:** Spring JMS chỉ cung cấp template, listener container và adapter. Ứng dụng vẫn cần JMS ConnectionFactory và provider.

**Cho rằng durable subscription tự bảo đảm xử lý đúng một lần:** message có thể được giao lại. Hãy dùng transaction, acknowledgment và xử lý idempotent theo yêu cầu nghiệp vụ.

**Quên xóa subscription cũ:** durable subscription không biến mất khi consumer đóng. Subscription không còn dùng có thể tiếp tục tích lũy message và tiêu thụ tài nguyên broker.

## 13. Checklist trước khi triển khai

- Topic và subscription đã được phân biệt rõ trong thiết kế chưa?
- Dữ liệu có cần được giữ khi consumer offline không?
- Một subscription cần một consumer hay nhiều consumer chia tải?
- Subscription name đã ổn định và duy nhất theo identity chưa?
- Client ID đã được đặt đúng và không trùng với Connection đang hoạt động chưa?
- Provider có hỗ trợ shared durable/shared non-durable không?
- Message selector và các thuộc tính subscription đã thống nhất giữa các consumer chưa?
- Delivery mode, expiration, acknowledgment và transaction đã được cấu hình chưa?
- Consumer có xử lý được message redelivery không?
- Có metric cho số durable subscription, backlog, message age và consumer active không?
- Quy trình dừng consumer và unsubscribe đã được xác định chưa?

## 14. Ghi nhớ

- Topic là nơi publisher phát message; subscription là trạng thái nhận; consumer là đối tượng đọc message.
- Durable subscription tiếp tục tồn tại và tích lũy message khi không có consumer, cho tới khi được unsubscribe hoặc message hết hạn.
- Non-durable subscription chỉ tồn tại khi có consumer hoạt động.
- Unshared subscription chỉ có một consumer hoạt động tại một thời điểm.
- Shared subscription cho phép nhiều consumer; mỗi message được giao cho một consumer trong nhóm.
- Unshared durable được định danh bằng client ID và subscription name; shared subscription dùng subscription name và client ID tùy chọn theo đặc tả.
- Jakarta Messaging 2.0 trở lên cung cấp API tạo shared consumer; provider phải hỗ trợ tính năng này.
- Spring JMS hỗ trợ cấu hình durable/shared subscription qua listener container và @JmsListener.
- Durable subscription không thay thế persistent delivery mode, transaction, acknowledgment hoặc idempotency.
- Đóng consumer không xóa durable subscription; cần unsubscribe khi không còn sử dụng.

## Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Topic subscriptions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta EE Tutorial — Messaging concepts](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework 6.2 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
