# Độ bền của message và subscription khi bên nhận ngắt kết nối

Trong JMS, việc bên nhận tạm ngắt kết nối không tự động làm mọi message được giữ lại. Kết quả phụ thuộc vào kiểu destination, subscription, delivery mode của message và cách consumer xác nhận xử lý.

Có hai tình huống cần phân biệt:

- **Queue:** queue là nơi lưu message của mô hình point-to-point. Queue có thể giữ message khi chưa có consumer đang kết nối; một message được phân phối cho một consumer.
- **Topic:** mỗi subscription nhận một bản sao message. Subscription không bền vững chỉ tồn tại khi consumer đang hoạt động. Muốn giữ message được publish trong lúc subscriber offline, phải tạo durable subscription.

Ngoài ra, delivery mode PERSISTENT và durable subscription là hai cơ chế riêng. PERSISTENT yêu cầu provider lưu message bền vững theo hợp đồng JMS; durable subscription giữ trạng thái đăng ký và backlog của một subscriber trên topic. Chỉ bật một trong hai chưa đủ cho mọi tình huống mất kết nối.

## 1. Hiểu đúng queue, topic, consumer và subscription

### 1.1. Queue giữ message cho consumer chưa sẵn sàng

Trong mô hình queue, producer gửi message vào một destination. Consumer có thể nhận message khi đang hoạt động. Nếu hiện tại không có consumer, queue vẫn có thể giữ message chờ lần kết nối tiếp theo.

Nếu có nhiều consumer cùng đọc một queue, mỗi message được giao cho một consumer. Broker phân phối công việc giữa các consumer theo cơ chế của provider; JMS không quy định thuật toán chia tải cụ thể.

Queue phù hợp khi một công việc chỉ cần được xử lý một lần bởi một worker trong nhóm, ví dụ:

- Xử lý đơn hàng.
- Gửi email hoặc tạo hóa đơn.
- Tạo báo cáo nền.
- Thực hiện một tác vụ cần retry khi worker gặp sự cố.

Queue không cần durable subscription. Tính bền vững của message trên queue phụ thuộc delivery mode, acknowledgement/transaction, expiration và cấu hình lưu trữ của broker.

### 1.2. Topic tạo một bản sao cho từng subscription

Trong mô hình publish-subscribe, producer gửi message tới topic. Consumer không đọc trực tiếp một hàng đợi chung; nó nhận message thông qua subscription.

Mỗi subscription phù hợp nhận một bản sao riêng của message. Việc một subscriber xử lý hoặc acknowledge bản sao của nó không acknowledge bản sao ở subscription khác.

Ví dụ topic orders.events có ba subscriber:

- billing-service nhận bản sao để tạo hóa đơn.
- analytics-service nhận bản sao để cập nhật số liệu.
- notification-service nhận bản sao để gửi thông báo.

Nếu notification-service dùng non-durable subscription và không có consumer hoạt động khi event được publish, subscription không tồn tại để nhận bản sao đó. Hai subscriber còn lại vẫn có thể nhận message bình thường.

### 1.3. Consumer khác subscription

Consumer là đối tượng nhận message đang hoạt động trong ứng dụng. Subscription là trạng thái đăng ký do JMS provider quản lý.

Với topic:

- Non-durable subscription bị xóa khi consumer cuối cùng đóng.
- Durable subscription tồn tại ngay cả khi không có consumer đang kết nối.
- Consumer mới có thể mở lại một durable subscription đã tồn tại và tiếp tục nhận backlog còn lại.

Phân biệt hai khái niệm này giúp giải thích vì sao đóng listener container không nhất thiết xóa durable subscription.

## 2. Delivery mode: PERSISTENT và NON_PERSISTENT

Delivery mode mô tả mức độ bền vững mà producer yêu cầu cho từng message.

| Delivery mode | Ý nghĩa | Đánh đổi |
|---|---|---|
| PERSISTENT | Provider phải áp dụng cơ chế lưu bền vững theo hợp đồng JMS | Tốn tài nguyên lưu trữ và I/O hơn |
| NON_PERSISTENT | Provider được phép dùng cách giao nhận nhẹ hơn, có thể mất message khi provider gặp sự cố | Thường có overhead thấp hơn |

Theo Jakarta Messaging, provider phải giao message PERSISTENT theo semantics once-and-only-once ở cấp provider; message NON_PERSISTENT có semantics at-most-once. Tuy nhiên, các semantics này có ngoại lệ quan trọng như expiration, giới hạn tài nguyên và việc quản trị viên xóa message.

PERSISTENT không có nghĩa là mọi consumer đều chắc chắn nhận message. Nếu topic chỉ có non-durable subscription, message publish trong lúc không có subscription hoạt động vẫn có thể bị bỏ lỡ.

### 2.1. Cấu hình delivery mode trong Spring

JmsTemplate có thuộc tính deliveryMode, nhưng để template truyền QoS do nó cấu hình vào lời gọi send, cần bật explicitQosEnabled.

~~~java
@Bean
public JmsTemplate persistentQueueTemplate(
        ConnectionFactory connectionFactory) {

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setExplicitQosEnabled(true);
    template.setDeliveryMode(DeliveryMode.PERSISTENT);
    template.setTimeToLive(0L);

    return template;
}
~~~

Trong ví dụ:

- DeliveryMode.PERSISTENT yêu cầu lưu message bền vững.
- Time-to-live bằng 0 nghĩa là message không có thời hạn hết hạn do TTL của lần gửi này.
- explicitQosEnabled bảo đảm JmsTemplate sử dụng các giá trị QoS đã cấu hình thay vì chỉ dựa vào default của provider.

Nếu dùng destination name cho topic, JmsTemplate cần được cấu hình pubSubDomain=true hoặc nhận một Destination object đại diện topic. Không dùng nhầm queue template để phân giải tên topic.

### 2.2. Expiration vẫn có thể loại bỏ message

Message có thể hết hạn trước khi consumer quay lại. TTL lớn hơn 0 tạo giới hạn thời gian message được giữ để giao.

Ví dụ, message có TTL 10 phút có thể hết hạn trong lúc service offline 30 phút. Durable subscription không biến message hết hạn thành message được giữ vô thời hạn.

Chọn TTL theo yêu cầu nghiệp vụ:

- Event cần xử lý muộn vẫn có giá trị: TTL dài hoặc không hết hạn, đồng thời giám sát backlog.
- Thông tin trạng thái chỉ hữu ích trong thời gian ngắn: TTL ngắn.
- Lệnh đã cũ không còn an toàn để thực hiện: cần expiration hoặc kiểm tra thời điểm hiệu lực ở consumer.

## 3. Durable và non-durable topic subscription

### 3.1. Non-durable subscription

Non-durable subscription chỉ tồn tại khi consumer còn hoạt động. Khi consumer đóng, subscription bị xóa cùng các message chưa được giao của subscription đó.

Đây là lựa chọn phù hợp khi:

- Subscriber chỉ cần dữ liệu mới trong lúc đang online.
- Có thể lấy lại trạng thái bằng một API hoặc snapshot khác.
- Mất một số event khi ứng dụng dừng không gây sai lệch nghiệp vụ.
- Ứng dụng không muốn duy trì backlog riêng cho từng subscriber.

Ví dụ dashboard hiển thị số liệu realtime có thể không cần durable subscription nếu khi mở lại dashboard, client tải snapshot hiện tại từ API.

### 3.2. Durable subscription

Durable subscription được provider lưu lại và tiếp tục tích lũy message cho subscription ngay cả khi không có consumer hoạt động.

Khi ứng dụng kết nối lại bằng cùng định danh subscription, consumer mới tiếp tục nhận những message đã được giữ trong thời gian offline, miễn là message chưa được acknowledge, chưa hết hạn và không bị loại bỏ bởi chính sách quản trị/tài nguyên của broker.

Một durable subscription cần được tạo trước khi các message muốn nhận được publish. Durable subscription không phải cơ chế replay toàn bộ lịch sử topic từ lúc topic ra đời. Nó nhận các message phù hợp được publish sau khi subscription đã tồn tại.

### 3.3. So sánh

| Đặc điểm | Non-durable | Durable |
|---|---|---|
| Subscription tồn tại khi consumer đóng | Không | Có |
| Nhận message publish khi offline | Không bảo đảm | Có, nếu subscription đã tồn tại và message còn hiệu lực |
| Lưu backlog riêng cho subscriber | Không | Có |
| Cần tên subscription ổn định | Không | Có |
| Cần client ID | Không theo yêu cầu của non-durable unshared | Bắt buộc với durable unshared; shared durable có thể không cần |
| Chi phí broker | Thấp hơn | Cao hơn do giữ trạng thái và backlog |
| Phù hợp | Realtime có thể bỏ lỡ | Event cần được xử lý sau khi subscriber quay lại |

Durable subscription có thể tạo backlog lớn nếu subscriber offline lâu hoặc xử lý chậm. Cần giám sát dung lượng, số lượng message pending, tốc độ tiêu thụ và chính sách expiration.

## 4. PERSISTENT và durable subscription phối hợp thế nào?

Hai cơ chế giải quyết hai lớp vấn đề khác nhau:

- Delivery mode quyết định provider xử lý độ bền của một message.
- Durable subscription quyết định provider có duy trì bản sao message cho một subscriber khi consumer không hoạt động hay không.

Bảng sau mô tả kết quả phổ biến khi subscriber offline hoặc provider khởi động lại:

| Destination / subscription | Message PERSISTENT | Message NON_PERSISTENT |
|---|---|---|
| Queue | Queue giữ message chờ consumer; provider phải áp dụng semantics bền vững | Có thể được giữ khi broker còn hoạt động nhưng có thể mất khi provider gặp sự cố |
| Topic, non-durable subscription | Không có subscription hoạt động để nhận bản sao trong thời gian offline; message bị bỏ lỡ | Bị bỏ lỡ khi offline và có thể mất khi provider gặp sự cố |
| Topic, durable subscription | Backlog được giữ khi subscription inactive cho tới khi acknowledge hoặc expire | Không được bảo đảm nếu subscription inactive hoặc provider shutdown/restart |

Với event quan trọng trên topic, cấu hình thường cần cả PERSISTENT và durable subscription. Với queue, dùng PERSISTENT để yêu cầu provider lưu message bền vững; queue vốn đã tồn tại độc lập với consumer.

Không nên suy ra rằng bật PERSISTENT trên producer sẽ tự tạo subscription cho mọi service. Mỗi subscriber cần có durable subscription riêng nếu cần nhận event khi offline.

## 5. Định danh durable subscription

### 5.1. Durable unshared: client ID và subscription name

Một durable subscription không chia sẻ được định danh bởi:

- Client ID của JMS Connection.
- Tên subscription.

Client ID phải được thiết lập và phải duy nhất giữa các Connection đang hoạt động trên cùng provider. Khi ứng dụng khởi động lại để tiếp tục subscription, nó phải dùng lại cùng client ID và tên subscription.

Ví dụ:

~~~text
clientId          = billing-service-client
subscriptionName  = billing-events-v1
topic             = billing.events
~~~

Nếu đổi client ID hoặc tên subscription, JMS có thể xem đó là một subscription khác. Consumer mới khi đó không tự động nhận backlog thuộc subscription cũ.

### 5.2. Một durable unshared chỉ có một consumer hoạt động

Durable unshared subscription chỉ cho phép một consumer hoạt động tại một thời điểm. Nếu hai instance ứng dụng cùng mở một subscription với cùng client ID và tên subscription, thao tác tạo consumer thứ hai không hợp lệ.

Điều này ảnh hưởng đến triển khai nhiều replica:

- Dùng durable unshared khi muốn một consumer active và các instance còn lại chỉ đóng vai trò failover.
- Dùng shared durable khi muốn nhiều consumer cùng chia sẻ một subscription, nếu provider hỗ trợ JMS 2.0 trở lên.

Không đặt concurrency lớn hơn 1 cho một durable unshared subscription. Nếu cần mở rộng song song, hãy cân nhắc shared durable subscription hoặc chia thành nhiều subscription độc lập theo thiết kế nghiệp vụ.

### 5.3. Shared durable subscription

Shared durable subscription vẫn giữ backlog khi không có consumer, nhưng cho phép nhiều consumer cùng đọc một subscription. Mỗi message của subscription được giao cho một consumer trong nhóm; không phải mọi consumer đều nhận bản sao riêng.

Shared durable subscription được hỗ trợ từ JMS 2.0. Định danh là subscription name và client ID tùy chọn. Nếu client ID được dùng khi tạo subscription, các consumer tiếp theo phải dùng cùng client ID đó.

Với triển khai nhiều instance, cần kiểm tra cách provider quản lý client ID và shared subscription. Không cấu hình cùng một client ID trên nhiều JMS Connection đang hoạt động nếu provider yêu cầu client ID duy nhất cho mỗi connection. Một cách triển khai phổ biến là dùng shared durable subscription với subscription name ổn định và không đặt client ID nếu provider cho phép.

## 6. Cấu hình durable topic listener bằng Spring Framework

Spring JMS cung cấp DefaultJmsListenerContainerFactory để cấu hình listener container. Factory mặc định tạo DefaultMessageListenerContainer, phù hợp với phần lớn ứng dụng cần khả năng phục hồi kết nối và điều chỉnh consumer.

Ví dụ tạo durable unshared topic listener:

~~~java
@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setClientId("billing-service-client");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Listener dùng tên subscription ổn định:

~~~java
@Component
public class BillingEventListener {

    @JmsListener(
            destination = "billing.events",
            subscription = "billing-events-v1",
            containerFactory = "durableTopicFactory"
    )
    public void receive(BillingEvent event) {
        billingService.process(event);
    }
}
~~~

Các cấu hình quan trọng:

- pubSubDomain=true cho biết listener nhận từ topic.
- subscriptionDurable=true bật durable subscription.
- clientId đặt định danh client cho durable unshared subscription.
- subscription trong @JmsListener là tên subscription.
- sessionTransacted=true dùng JMS transaction cho lần nhận và xử lý message.

Trong Spring Framework, bật durable subscription cũng chuyển listener container sang pub-sub domain. Việc đặt pubSubDomain=true tường minh giúp người đọc cấu hình hiểu rõ destination là topic.

### 6.1. Tạo shared durable subscription

Nếu broker hỗ trợ JMS 2.0 trở lên và cần nhiều consumer cùng đọc một durable subscription, cấu hình shared:

~~~java
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
    factory.setConcurrency("2-6");

    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
        destination = "billing.events",
        subscription = "billing-events-workers",
        containerFactory = "sharedDurableTopicFactory"
)
public void receive(BillingEvent event) {
    billingService.process(event);
}
~~~

Trong cấu hình này, nhiều consumer cùng chia sẻ backlog của subscription. Mỗi message được phân phối cho một consumer trong nhóm. Concurrency cụ thể còn phụ thuộc container và JMS provider.

Shared durable subscription yêu cầu provider hỗ trợ API shared subscription của JMS 2.0. Hãy kiểm thử khả năng này với broker và client library đang dùng; không chỉ dựa vào việc code Spring biên dịch thành công.

## 7. Cấu hình queue listener bền vững

Queue không cần durable subscription. Chỉ cần destination queue tồn tại và producer gửi message với delivery mode phù hợp.

~~~java
@Bean
public DefaultJmsListenerContainerFactory queueListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);

    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "queueListenerFactory"
)
public void receive(OrderCommand command) {
    orderService.process(command);
}
~~~

Producer có thể dùng JmsTemplate đã bật persistent QoS như phần trước. Khi consumer offline, queue tiếp tục giữ message chờ xử lý theo chính sách broker.

Nếu queue có nhiều consumer, một message chỉ được giao cho một consumer. Consumer nào nhận được phụ thuộc broker và trạng thái của nhóm; JMS không quy định thuật toán chia tải cụ thể.

## 8. Acknowledgement và transaction quyết định message có bị xóa hay giao lại

Lưu message bền vững mới chỉ là một phần của reliability. Sau khi consumer nhận message, provider cần biết message đã được xử lý và acknowledge hay chưa.

Các chế độ thường gặp:

- AUTO_ACKNOWLEDGE: provider tự acknowledge theo semantics của Session. Cấu hình mặc định này không đủ để bảo đảm reliability trong mọi tình huống listener lỗi hoặc container dừng.
- CLIENT_ACKNOWLEDGE: ứng dụng chủ động acknowledge; cần hiểu phạm vi acknowledge và cách recover của Session.
- Transacted Session: consumer xử lý message rồi commit transaction; nếu rollback, message chưa được xác nhận và có thể được redeliver.

Spring khuyến nghị dùng transacted Session cho xử lý queue và durable topic subscription khi cần reliability.

### 8.1. Bật transaction trong listener container

Ví dụ:

~~~java
factory.setSessionTransacted(true);
~~~

Khi listener xử lý thành công, container commit JMS Session. Nếu listener ném exception và transaction bị rollback, provider có thể giao lại message.

Không nuốt exception rồi trả về bình thường nếu muốn rollback. Nếu bắt exception để ghi log, hãy ném lại hoặc chủ động đánh dấu transaction rollback theo cơ chế transaction đang dùng.

### 8.2. Redelivery và xử lý lặp

Một message có thể được giao lại khi:

- Listener ném exception và transaction rollback.
- JVM dừng trước khi commit.
- Connection bị mất trong lúc xử lý.
- Provider chưa nhận được acknowledgement/commit thành công.

JMS cung cấp JMSRedelivered và JMSXDeliveryCount để hỗ trợ nhận biết redelivery. Số lần retry trước khi provider chuyển message sang trạng thái khác hoặc ngừng giao phụ thuộc cấu hình provider.

Vì vậy, consumer nên idempotent. Có thể dùng eventId duy nhất và bảng inbox/processed_events để bảo đảm cùng một event không tạo tác dụng nghiệp vụ hai lần.

Ví dụ logic:

~~~java
@Transactional
public void process(BillingEvent event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    billingService.apply(event);
    processedEventRepository.save(
            new ProcessedEvent(event.eventId())
    );
}
~~~

Ví dụ này chỉ bảo đảm idempotency khi việc kiểm tra, cập nhật nghiệp vụ và lưu event ID nằm trong cùng transaction database phù hợp. Cần có unique constraint trên eventId để xử lý hai lần nhận đồng thời.

## 9. Kết nối lại khi broker hoặc consumer gặp sự cố

Khi consumer process dừng hoặc mất kết nối, kết quả phụ thuộc subscription và destination:

- Queue vẫn giữ message trong khi không có consumer.
- Durable topic subscription tiếp tục giữ backlog.
- Non-durable topic subscription bị đóng cùng consumer và không giữ message publish trong thời gian offline.

Spring DefaultMessageListenerContainer có khả năng phục hồi khi broker ngừng hoạt động. Mặc định container thử kết nối lại theo chu kỳ BackOff đơn giản khoảng 5 giây; có thể cấu hình BackOff riêng cho nhu cầu vận hành.

Khi kết nối trở lại, listener container đăng ký lại consumer. Nếu durable subscription được cấu hình với đúng topic, client ID và subscription name, consumer tiếp tục đọc subscription đã tồn tại.

Việc container tự reconnect không thay thế durable subscription. Nếu listener topic dùng non-durable subscription, container có thể kết nối lại thành công nhưng vẫn không nhận được các event đã publish trong thời gian subscription không tồn tại.

### 9.1. DMLC và SMLC

Spring có hai listener container phổ biến:

| Container | Đặc điểm | Khi phù hợp |
|---|---|---|
| DefaultMessageListenerContainer | Có khả năng phục hồi, điều chỉnh consumer và tham gia transaction được quản lý bên ngoài | Phần lớn ứng dụng production |
| SimpleMessageListenerContainer | Tạo số consumer cố định khi khởi động, để provider thực hiện callback | Tình huống đơn giản, số consumer cố định và provider phù hợp |

DefaultMessageListenerContainer thường là lựa chọn tốt khi cần tự phục hồi sau broker outage. SimpleMessageListenerContainer vẫn hỗ trợ native JMS transaction, nhưng không hỗ trợ tham gia externally managed transaction theo cách của DMLC.

## 10. Xóa durable subscription khi không còn sử dụng

Durable subscription tiếp tục tồn tại ngay cả khi ứng dụng dừng. Chỉ đóng consumer hoặc stop listener container không có nghĩa là xóa subscription.

Muốn xóa durable subscription, JMS cung cấp Session.unsubscribe(subscriptionName). Với durable unshared subscription, thao tác này phải dùng đúng client ID đã gắn với subscription.

Không thể unsubscribe khi subscription còn consumer đang hoạt động hoặc còn message chưa acknowledge/đang nằm trong transaction. Hãy dừng consumer, bảo đảm không còn xử lý đang diễn ra rồi mới xóa.

Không xóa subscription chỉ để xử lý lỗi kết nối. Xóa và tạo lại có thể làm mất backlog mà subscriber đang chờ nhận.

Nếu thay đổi topic, selector hoặc noLocal của một durable subscription hiện có, cần hiểu semantics của provider. Với một số trường hợp subscription inactive, JMS xem thay đổi này tương đương xóa subscription cũ và tạo subscription mới. Hãy coi topic, selector và tên subscription là một phần của contract cần quản lý version.

## 11. Giới hạn lưu trữ và backlog

Durable subscription giúp không bỏ lỡ event khi subscriber offline, nhưng backlog phải được lưu ở broker. Một subscriber chậm hoặc offline dài ngày có thể tiêu thụ lượng storage đáng kể.

Các chỉ số nên theo dõi:

- Số lượng message pending trên từng queue và durable subscription.
- Dung lượng lưu trữ và tốc độ tăng backlog.
- Tuổi của message cũ nhất.
- Tốc độ publish so với tốc độ consume.
- Số lần redelivery và số message vào dead-letter queue.
- Trạng thái kết nối và số lần listener container recover.
- Message hết hạn hoặc bị loại bỏ bởi resource policy.

Broker có thể giới hạn dung lượng, số message hoặc thời gian lưu. JMS không định nghĩa một mức dung lượng vô hạn. Khi hết tài nguyên, provider có thể áp dụng policy như block producer, reject, expire hoặc drop theo cấu hình vendor.

Vì vậy, cần phối hợp durable subscription với retention policy, TTL, cảnh báo backlog và quy trình xử lý subscriber đã ngừng hoạt động lâu ngày.

## 12. Tình huống minh họa: subscriber offline 30 phút

Giả sử producer publish event E1, E2 và E3 trong lúc billing-service mất kết nối.

### Trường hợp A: Topic với non-durable subscription

Khi billing-service offline, subscription bị đóng. E1, E2, E3 không được lưu cho subscriber này. Khi service khởi động lại, nó chỉ nhận các event được publish sau khi subscription mới được tạo.

### Trường hợp B: Topic với durable subscription

Subscription billing-events-v1 vẫn tồn tại. Provider lưu các message phù hợp trong thời gian consumer offline. Khi billing-service kết nối lại bằng cùng client ID và subscription name, nó nhận E1, E2, E3 nếu chúng chưa hết hạn và chưa bị xóa theo policy.

### Trường hợp C: Queue với persistent message

Producer gửi E1, E2, E3 vào queue bằng PERSISTENT. Queue giữ chúng khi billing-service offline. Khi consumer quay lại, nó nhận các message còn hiệu lực theo thứ tự và quy tắc phân phối của broker.

### Trường hợp D: Durable topic nhưng message NON_PERSISTENT

Subscription tồn tại, nhưng message NON_PERSISTENT không được bảo đảm nếu subscription inactive hoặc provider shutdown/restart. Nếu event quan trọng cần tồn tại qua broker failure, dùng PERSISTENT.

## 13. Kiểm thử độ bền và phục hồi

Unit test chỉ kiểm tra được logic ứng dụng. Cần integration test với JMS provider thật hoặc broker container để xác nhận hành vi lưu trữ, subscription và redelivery.

Các bài kiểm thử nên có:

1. Tạo durable subscription, dừng consumer, publish message, khởi động lại consumer và xác nhận nhận được backlog.
2. Lặp lại thử nghiệm với non-durable subscription để chứng minh message lúc offline không được giữ cho subscriber đó.
3. Gửi persistent message vào queue khi không có consumer, sau đó khởi động consumer và nhận message.
4. Restart broker khi có persistent message đang chờ, sau đó kiểm tra message còn tồn tại theo cấu hình provider.
5. Cho listener ném exception trong transacted Session và xác nhận message được redeliver.
6. Commit thành công và xác nhận message không bị giao lại như một message chưa acknowledge.
7. Kiểm tra JMSRedelivered và JMSXDeliveryCount khi redelivery xảy ra.
8. Kiểm tra message TTL hết hạn khi consumer vẫn offline.
9. Kiểm tra durable subscription không bị xóa khi listener container stop.
10. Kiểm tra unsubscribe chỉ thành công sau khi consumer đã dừng và message không còn trong transaction.
11. Kiểm tra shared durable subscription với nhiều consumer và xác nhận mỗi message chỉ được giao cho một consumer trong nhóm.
12. Kiểm tra nhiều instance cùng mở durable unshared subscription để phát hiện xung đột client ID/consumer.

Một test reconnect nên chờ điều kiện message được nhận thay vì sleep một khoảng thời gian cố định. Dùng latch, polling có timeout hoặc cơ chế đồng bộ của test để giảm flaky test.

## 14. Lỗi thường gặp

### 14.1. Chỉ đặt delivery mode PERSISTENT rồi nghĩ topic đã durable

PERSISTENT không tạo subscription. Topic cần durable subscription nếu subscriber phải nhận event được publish trong lúc offline.

### 14.2. Tạo durable subscription sau khi event đã publish

Durable subscription không tự replay lịch sử topic. Chỉ message publish sau khi subscription được tạo mới thuộc backlog của subscription.

### 14.3. Đổi client ID hoặc subscription name sau mỗi lần restart

Provider xem đây là định danh khác. Consumer mới có thể tạo backlog mới trong khi backlog cũ vẫn còn ở subscription cũ.

### 14.4. Dùng durable unshared với nhiều consumer đồng thời

Durable unshared chỉ có một consumer hoạt động. Dùng shared durable nếu cần nhiều consumer trên cùng subscription và broker hỗ trợ JMS 2.0.

### 14.5. Dùng AUTO_ACKNOWLEDGE cho xử lý quan trọng

Listener lỗi hoặc container dừng có thể làm message bị acknowledge quá sớm. Dùng transacted Session hoặc acknowledgement strategy phù hợp.

### 14.6. Không xử lý duplicate

Redelivery có thể khiến cùng một event được xử lý lại. Dùng event ID ổn định, idempotent consumer và unique constraint phù hợp.

### 14.7. Không đặt TTL hoặc không giám sát backlog

Durable subscription có thể tích lũy message rất lâu. Nếu không giám sát, broker có thể hết dung lượng hoặc message quá cũ vẫn được xử lý sau khi không còn ý nghĩa.

### 14.8. Xóa subscription để sửa lỗi kết nối

Xóa subscription có thể xóa backlog. Hãy kiểm tra client ID, subscription name, broker connection và recovery trước khi thực hiện thao tác unsubscribe.

### 14.9. Dùng cùng client ID trên nhiều Connection đang hoạt động

Client ID phải đáp ứng quy tắc duy nhất của provider. Với nhiều instance cần chia sẻ tải, xem xét shared durable subscription và cấu hình client ID phù hợp.

### 14.10. Nghĩ JMS once-and-only-once bảo đảm tác dụng nghiệp vụ exactly-once

Guarantee của provider không tự làm cho database update, HTTP call hoặc side effect bên ngoài trở thành exactly-once. Dùng transaction phù hợp và idempotency ở tầng nghiệp vụ.

## 15. Checklist thiết kế

- Destination là queue hay topic?
- Queue có tồn tại độc lập với consumer không?
- Topic subscriber có cần nhận event khi offline không?
- Durable subscription đã được tạo trước khi publish chưa?
- Producer có dùng PERSISTENT cho event quan trọng không?
- TTL có phù hợp với thời gian offline tối đa không?
- Client ID và subscription name có ổn định không?
- Durable unshared hay shared durable phù hợp với số consumer?
- Broker/client có hỗ trợ JMS 2.0 nếu dùng shared subscription không?
- Listener container có dùng transacted Session không?
- Listener có xử lý idempotent khi message được redeliver không?
- Backlog, oldest message age, expiry và DLQ có được giám sát không?
- Recovery/backoff khi broker outage có phù hợp không?
- Có quy trình an toàn để unsubscribe subscription cũ không?
- Integration test đã mô phỏng consumer offline, broker restart và redelivery chưa?

## 16. Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 Specification — Durable subscriptions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#consuming-messages)
- [Jakarta Messaging 3.1 Specification — Reliability](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 6.1 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.1 — JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)

Để subscriber nhận được event sau khi offline, hãy thiết kế đúng cả subscription lẫn message: queue giữ message cho consumer chưa sẵn sàng; topic cần durable subscription để giữ bản sao cho subscriber; producer dùng PERSISTENT cho dữ liệu quan trọng; listener xử lý trong transaction và có idempotency để chịu được redelivery.