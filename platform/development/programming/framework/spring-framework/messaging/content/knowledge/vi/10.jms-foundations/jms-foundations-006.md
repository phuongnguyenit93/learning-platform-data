# Selector và điều kiện lọc phía bộ môi giới trong JMS

## 1. Message selector giải quyết vấn đề gì?

Trong hệ thống JMS, một destination có thể chứa nhiều loại message. Ví dụ, queue orders.queue có thể nhận đơn hàng từ nhiều quốc gia, nhiều mức ưu tiên và nhiều loại nghiệp vụ. Một consumer chỉ xử lý đơn hàng giao tại EU có thể dùng message selector để yêu cầu provider chỉ giao những message phù hợp.

**Message selector** là biểu thức điều kiện dạng String được gắn với một consumer hoặc topic subscription. Jakarta Messaging provider đánh giá biểu thức dựa trên header và message properties trước khi giao message. Consumer chỉ nhận message mà biểu thức cho kết quả TRUE.

Mục tiêu là chuyển việc lọc từ code ứng dụng sang messaging provider:

- Giảm message không liên quan được chuyển đến ứng dụng.
- Tránh để mỗi listener nhận mọi message rồi tự kiểm tra và bỏ qua.
- Cho phép nhiều consumer cùng đọc một destination nhưng nhận các nhóm message khác nhau.
- Với topic, cho phép mỗi subscription nhận đúng nhóm sự kiện mà subscriber quan tâm.

Selector không phải truy vấn SQL đầy đủ, không đọc nội dung body và không thay thế phân quyền truy cập destination.

## 2. Selector đọc được những dữ liệu nào?

Selector chỉ tham chiếu đến:

1. Một số trường header JMS được đặc tả cho phép.
2. Các message property do ứng dụng hoặc provider thiết lập.

Selector **không thể truy cập message body**. Nếu cần lọc theo thông tin nằm trong payload JSON, XML hoặc một đối tượng Java, hãy đưa trường cần lọc thành message property trước khi gửi.

Ví dụ producer gửi một TextMessage với body là mã đơn hàng và properties như sau:

~~~java
message.setStringProperty("region", "EU");
message.setIntProperty("priority", 7);
message.setStringProperty("orderType", "EXPRESS");
~~~

Consumer có thể dùng selector:

~~~sql
region = 'EU' AND priority >= 5 AND orderType = 'EXPRESS'
~~~

Provider có thể đánh giá selector mà không cần gọi listener để đọc body. Đây là lý do nên thiết kế các property phục vụ định tuyến ngay từ lúc producer tạo message.

### 2.1. Header JMS được phép tham chiếu

Jakarta Messaging giới hạn các header field có thể xuất hiện trực tiếp trong selector:

| Header | Kiểu/ý nghĩa thường dùng |
| --- | --- |
| JMSDeliveryMode | Chế độ giao bền vững; trong selector dùng giá trị PERSISTENT hoặc NON_PERSISTENT |
| JMSPriority | Mức ưu tiên dạng số |
| JMSMessageID | Mã định danh message |
| JMSTimestamp | Thời điểm gửi, dạng mili giây |
| JMSCorrelationID | Mã liên kết request/reply hoặc luồng nghiệp vụ |
| JMSType | Kiểu message do ứng dụng đặt |

Không phải mọi header JMS đều dùng được trong selector. Ví dụ, đừng giả định có thể tham chiếu JMSDestination, JMSReplyTo hoặc JMSRedelivered như một identifier selector thông thường.

Các property bắt đầu bằng JMSX là nhóm property được Jakarta Messaging định nghĩa. Những property bắt đầu bằng JMS_ dành cho provider. Property ứng dụng nên dùng tên riêng không bắt đầu bằng JMS, chẳng hạn region, orderType hoặc tenantCode.

## 3. Cú pháp selector: một tập con của SQL-92

Selector là một biểu thức String có cú pháp dựa trên một tập con của điều kiện SQL-92. Đây không phải SQL query: không có SELECT, FROM, JOIN, subquery hoặc truy cập cột trong body.

### 3.1. So sánh và toán tử logic

Các toán tử so sánh thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| = | Bằng | region = 'EU' |
| <> | Khác | status <> 'CANCELLED' |
| >, >= | Lớn hơn, lớn hơn hoặc bằng | priority >= 5 |
| <, <= | Nhỏ hơn, nhỏ hơn hoặc bằng | amount < 1000 |

Các toán tử logic là NOT, AND và OR. Độ ưu tiên theo thứ tự NOT trước AND, rồi OR. Dùng dấu ngoặc để biểu thức rõ ràng:

~~~sql
region = 'EU' AND (priority >= 8 OR orderType = 'EXPRESS')
~~~

Các từ khóa và toán tử được viết không phân biệt chữ hoa/chữ thường, nhưng tên identifier thì phân biệt chữ hoa/chữ thường. Vì vậy region và Region là hai property name khác nhau.

### 3.2. Literal và kiểu dữ liệu

Selector hỗ trợ:

- String literal đặt trong dấu nháy đơn, ví dụ 'EU'.
- Số nguyên, ví dụ 7 hoặc -3.
- Số gần đúng, ví dụ 10.5 hoặc 7E3.
- Boolean TRUE và FALSE.

Nếu một string literal cần chứa dấu nháy đơn, viết dấu nháy đơn đó thành hai ký tự liên tiếp:

~~~sql
customerName = 'O''Reilly'
~~~

Property phải được thiết lập bằng kiểu dữ liệu phù hợp với phép so sánh. Selector không tự chuyển chuỗi thành số như một số API getter của JMS có thể làm.

Ví dụ producer dùng:

~~~java
message.setStringProperty("priority", "7");
~~~

Selector sau không phải cách so sánh hợp lệ theo kiểu dữ liệu mong muốn:

~~~sql
priority >= 5
~~~

Property priority là String, còn literal 5 là số. Hãy dùng setIntProperty("priority", 7) nếu muốn so sánh số.

Chỉ so sánh được các kiểu tương thích. String và Boolean chỉ hỗ trợ phép bằng hoặc khác; số nguyên và số gần đúng có thể so sánh theo quy tắc chuyển kiểu số của Java.

### 3.3. BETWEEN và IN

BETWEEN kiểm tra một giá trị số trong khoảng, bao gồm cả hai đầu mút:

~~~sql
priority BETWEEN 3 AND 7
~~~

Biểu thức trên tương đương:

~~~sql
priority >= 3 AND priority <= 7
~~~

IN kiểm tra một property String có nằm trong danh sách giá trị hay không:

~~~sql
region IN ('EU', 'UK', 'SG')
~~~

Có thể dùng NOT BETWEEN và NOT IN để phủ định điều kiện. IN/NOT IN trong selector áp dụng cho identifier kiểu String hoặc NULL, không phải cú pháp danh sách số tùy ý.

### 3.4. LIKE và ESCAPE

LIKE dùng để so khớp chuỗi theo mẫu:

- % khớp với không hoặc nhiều ký tự.
- _ khớp với đúng một ký tự.
- ESCAPE khai báo ký tự dùng để vô hiệu hóa ý nghĩa đặc biệt của % hoặc _.

Ví dụ:

~~~sql
customerCode LIKE 'VIP-%'
~~~

Chọn mã khách hàng bắt đầu bằng VIP-.

~~~sql
phone LIKE '84_123%'
~~~

Chọn số điện thoại có tiền tố 84, tiếp theo một ký tự, rồi đến 123 và phần còn lại bất kỳ.

Nếu cần tìm ký tự % hoặc _ theo nghĩa đen, dùng ESCAPE với ký tự thoát phù hợp. Không giả định LIKE hỗ trợ regex; nó chỉ dùng hai wildcard % và _ theo đặc tả.

### 3.5. IS NULL và IS NOT NULL

Nếu một property không tồn tại trên message, giá trị của nó được xem là NULL khi selector đánh giá:

~~~sql
campaignCode IS NULL
~~~

Chọn message không có campaignCode hoặc có giá trị header/property được đánh giá là NULL.

~~~sql
campaignCode IS NOT NULL
~~~

Chỉ chọn message có campaignCode khác NULL.

Không dùng phép bằng với NULL:

~~~sql
campaignCode = NULL
~~~

Hãy dùng IS NULL hoặc IS NOT NULL.

## 4. Logic ba giá trị: TRUE, FALSE và UNKNOWN

Selector dùng quy tắc NULL của SQL. Khi một property không tồn tại, phép so sánh với property đó thường tạo kết quả UNKNOWN thay vì TRUE hoặc FALSE.

Ví dụ message không có property region:

~~~sql
region = 'EU'
~~~

Biểu thức cho kết quả UNKNOWN nên message không khớp selector. Chỉ kết quả TRUE mới được coi là match; FALSE và UNKNOWN đều không được giao.

Các toán tử AND, OR và NOT cũng áp dụng logic ba giá trị:

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

NOT UNKNOWN vẫn là UNKNOWN.

Điều này quan trọng khi viết selector phủ định. Ví dụ:

~~~sql
NOT (region = 'EU')
~~~

Không tự động chọn message thiếu region, vì biểu thức bên trong là UNKNOWN và NOT UNKNOWN vẫn là UNKNOWN. Nếu muốn nhận mọi message ngoài EU, kể cả message không có region, viết rõ:

~~~sql
region <> 'EU' OR region IS NULL
~~~

## 5. Điều kiện lọc được áp dụng ở đâu?

Selector được tạo cùng consumer hoặc subscription. Provider đánh giá selector trước khi giao message cho consumer. Hành vi của message không khớp phụ thuộc destination là queue hay topic.

### 5.1. Queue: consumer cạnh tranh cùng một hàng đợi

Trong mô hình point-to-point, nhiều consumer có thể đọc cùng một queue nhưng mỗi message chỉ được giao cho một consumer.

Nếu consumer có selector, chỉ message phù hợp mới được giao cho consumer đó. Message không phù hợp vẫn ở queue hoặc có thể được giao cho một consumer khác có selector phù hợp.

Ví dụ có hai consumer:

| Consumer | Selector |
| --- | --- |
| Consumer EU | region = 'EU' |
| Consumer US | region = 'US' |

Message có region = 'EU' chỉ phù hợp consumer EU. Nếu không có consumer nào phù hợp, message có thể tiếp tục nằm trong queue và làm tăng backlog.

Selector không biến queue thành pub/sub. Một message trong queue không được sao chép cho tất cả consumer; nó được giao cho một consumer phù hợp.

### 5.2. Topic: selector thuộc về từng subscription

Trong mô hình publish/subscribe, mỗi subscription của topic nhận một bản sao riêng của message. Nếu subscription có selector, chỉ message phù hợp mới được thêm vào subscription đó.

Ví dụ hai subscriber cùng đăng ký topic order-events:

| Subscription | Selector | Message được nhận |
| --- | --- | --- |
| EU reports | region = 'EU' | Đơn hàng EU |
| High priority alerts | priority >= 8 | Đơn hàng có ưu tiên từ 8 trở lên |

Một message có thể khớp nhiều subscription và được phân phối thành nhiều bản sao. Việc acknowledge ở một subscription không acknowledge bản sao ở subscription khác.

### 5.3. Durable topic subscription

Durable subscription được provider lưu lại kể cả khi consumer tạm thời không hoạt động. Provider tiếp tục giữ các message phù hợp với subscription cho đến khi được nhận và acknowledge hoặc hết hạn.

Selector là một phần cấu hình của subscription:

- Khi durable subscription đang có consumer hoạt động, không thể mở thêm consumer cùng identity nhưng dùng selector khác; provider có thể ném JMSException hoặc JMSRuntimeException.
- Khi durable subscription không có consumer hoạt động, tạo lại subscription cùng identity nhưng selector khác tương đương xóa subscription cũ và tạo subscription mới.
- Khi đổi selector, các message đang chờ trong subscription cũ có thể bị loại bỏ cùng subscription cũ. Cần đánh giá tác động trước khi thay đổi.

Vì vậy, selector của topic cần được xem như một phần của hợp đồng subscription, không phải một điều kiện tạm thời có thể thay đổi tùy ý mà không ảnh hưởng trạng thái.

## 6. Thiết lập selector bằng Jakarta Messaging API

Trong API đơn giản, selector được truyền khi tạo consumer:

~~~java
JMSContext context = connectionFactory.createContext();
Queue queue = context.createQueue("orders.queue");

JMSConsumer consumer = context.createConsumer(
    queue,
    "region = 'EU' AND priority >= 5"
);
~~~

Consumer chỉ nhận message khớp cả hai điều kiện. Có thể dùng API classic tương đương với Session.createConsumer(destination, selector).

Selector được kiểm tra cú pháp khi consumer được tạo. Nếu biểu thức sai cú pháp, provider ném InvalidSelectorException trong classic API hoặc exception runtime tương ứng trong simplified API.

Ví dụ producer phải thiết lập property trước khi gửi:

~~~java
context.createProducer()
    .setProperty("region", "EU")
    .setProperty("priority", 7)
    .send(queue, "order-42");
~~~

Ở đây region là String và priority là số nguyên. Message body là order-42; selector chỉ đọc hai property, không đọc chuỗi body.

## 7. Dùng selector trong Spring JMS

Spring JMS cung cấp hai cách cấu hình selector phổ biến:

1. Thuộc tính selector trên annotation @JmsListener.
2. Phương thức setMessageSelector trên listener container, chẳng hạn DefaultMessageListenerContainer.

Spring chuyển selector đến JMS consumer mà container tạo. Việc lọc vẫn do Jakarta Messaging provider thực hiện theo hợp đồng JMS.

### 7.1. @JmsListener(selector = ...)

Ví dụ listener chỉ nhận đơn hàng EU có priority từ 5 trở lên:

~~~java
@Component
public class EuOrderListener {

    @JmsListener(
        destination = "orders.queue",
        selector = "region = 'EU' AND priority >= 5"
    )
    public void receive(String orderId) {
        System.out.println("Accepted order: " + orderId);
    }
}
~~~

Cần bật annotation listener bằng @EnableJms và cấu hình một JmsListenerContainerFactory mặc định hoặc chỉ định containerFactory trên annotation.

Selector ở đây là biểu thức JMS, không phải Java expression và cũng không phải SpEL. Không viết điều kiện dựa trên tham số method hoặc truy cập field của payload.

### 7.2. Gửi property bằng JmsTemplate

Producer dùng MessagePostProcessor để thêm property sau khi Spring chuyển payload thành JMS Message:

~~~java
@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String orderId, String region, int priority) {
        jmsTemplate.convertAndSend(
            "orders.queue",
            orderId,
            message -> {
                message.setStringProperty("region", region);
                message.setIntProperty("priority", priority);
                return message;
            }
        );
    }
}
~~~

Với producer gọi:

~~~java
publisher.publish("order-42", "EU", 7);
publisher.publish("order-43", "US", 9);
publisher.publish("order-44", "EU", 2);
~~~

Listener EU ở mục trước chỉ nhận order-42. Hai message còn lại không khớp selector.

### 7.3. Cấu hình listener container bằng Java

Nếu muốn cấu hình selector cho container thay vì đặt trên annotation, có thể dùng AbstractMessageListenerContainer.setMessageSelector. Ví dụ:

~~~java
@Bean
public DefaultMessageListenerContainer euOrdersContainer(
        ConnectionFactory connectionFactory,
        Destination ordersQueue,
        MessageListener euOrderMessageListener) {

    DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestination(ordersQueue);
    container.setMessageListener(euOrderMessageListener);
    container.setMessageSelector("region = 'EU' AND priority >= 5");
    return container;
}
~~~

Selector trong ví dụ chỉ áp dụng cho consumer do container euOrdersContainer tạo. Với các endpoint @JmsListener, đặt selector riêng trên annotation; factory chung dùng để cấu hình các thuộc tính container như ConnectionFactory và concurrency.

Ví dụ trên giả định ConnectionFactory đã được cấu hình bởi JMS provider hoặc application infrastructure. JmsTemplate và listener container phải dùng đúng destination domain. Với queue, cấu hình pubSubDomain mặc định là false; nếu chuyển sang topic, hãy cấu hình cả template và listener container phù hợp với topic.

## 8. Ví dụ tích hợp Spring JMS: các thành phần cần có

Một ứng dụng thực tế cần có các thành phần sau:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1-4");
        return factory;
    }
}
~~~

ConnectionFactory là adapter kết nối đến broker cụ thể như ActiveMQ Artemis hoặc một JMS provider khác. Cần cấu hình endpoint, credentials, destination và dependency client của provider trong ứng dụng.

Ví dụ này minh họa cấu hình Spring JMS; để chạy thực tế phải có broker đang hoạt động và ConnectionFactory bean do provider cung cấp. Không có stdout cố định cho mọi provider vì delivery bất đồng bộ, concurrency, acknowledgement và lịch xử lý do container/broker điều phối.

## 9. Selector và hiệu năng

Selector có thể giảm lượng message được giao đến ứng dụng, nhưng hiệu năng cụ thể phụ thuộc provider, cấu hình destination và số lượng consumer/subscription.

Một số nguyên tắc:

- Chỉ đưa vào selector các property thật sự cần để định tuyến.
- Đặt property ngay khi producer tạo message, tránh dựa vào việc consumer đọc body để phân loại.
- Dùng kiểu dữ liệu thống nhất giữa producer và selector.
- Giữ biểu thức đơn giản, tránh quá nhiều nhánh logic khó kiểm thử.
- Kiểm tra selector trên đúng JMS provider đang chạy; khả năng tối ưu nội bộ và chỉ mục property không được chuẩn hóa bởi JMS.
- Theo dõi queue depth, số message không khớp, tốc độ giao, độ trễ và số lần redelivery.
- Nếu không có consumer nào khớp selector của queue, message có thể tồn tại lâu trong queue. Cần cảnh báo backlog và có consumer xử lý dự phòng nếu nghiệp vụ yêu cầu.

Selector giúp provider lọc trước khi giao message; nó không tự đảm bảo thông lượng cao hoặc độ bền message. Persistence, acknowledgement, transaction, retry và dead-letter queue vẫn cần được cấu hình riêng.

## 10. Giới hạn và lưu ý bảo mật

Selector chỉ là cơ chế chọn message để giao. Không dùng nó làm ranh giới bảo mật.

- Quyền đọc destination phải được cấu hình ở broker/provider.
- Client có thể tự tạo consumer với selector khác nếu họ có quyền truy cập destination.
- Không đưa dữ liệu nhạy cảm vào property với suy nghĩ selector sẽ che giấu dữ liệu khỏi consumer khác.
- Không cho phép người dùng cuối truyền selector tùy ý nếu ứng dụng cần giới hạn phạm vi dữ liệu.
- Validate property và payload ở server; selector không thay thế validation nghiệp vụ.
- Dùng tenant identity đã được xác thực để quyết định destination và quyền subscription.

Selector cũng không thay thế dead-letter queue, retry hay transaction. Một message bị selector loại khỏi consumer không đồng nghĩa message đã được acknowledge hoặc xử lý thành công.

## 11. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener không nhận message | Property không tồn tại hoặc điều kiện trả về FALSE/UNKNOWN | Kiểm tra property thực tế được producer đặt |
| So sánh số nhưng không match | Property được đặt dưới kiểu String | Dùng setIntProperty/setLongProperty đúng kiểu |
| Selector không đọc được dữ liệu trong JSON body | Selector không hỗ trợ body field | Đưa trường cần lọc thành JMS property |
| InvalidSelectorException | Cú pháp sai, sai kiểu toán tử hoặc thiếu dấu nháy | Kiểm tra cú pháp selector và tạo consumer lại |
| Consumer queue giữ backlog | Không consumer nào có selector phù hợp | Kiểm tra selector của mọi consumer và thêm luồng xử lý dự phòng |
| Subscriber topic bỏ lỡ event | Selector của subscription loại event đó | Kiểm tra selector gắn với subscription, đặc biệt với durable subscription |
| Đổi selector durable subscription bị lỗi | Subscription cũ đang có consumer hoạt động hoặc identity không tương thích | Dừng consumer, quản lý vòng đời subscription và thay đổi có kế hoạch |
| Selector LIKE không hoạt động như regex | LIKE chỉ hỗ trợ % và _ | Dùng đúng wildcard của JMS hoặc xử lý ở tầng ứng dụng |
| Dùng tên property sai chữ hoa/thường | Identifier phân biệt chữ hoa/chữ thường | Chuẩn hóa tên property giữa producer và consumer |
| Dùng selector để bảo vệ tenant | Consumer khác vẫn có thể tạo selector riêng nếu có quyền đọc destination | Phân quyền tại broker và xác thực ở ứng dụng |

## 12. Checklist thiết kế selector

- [ ] Xác định selector áp dụng cho queue consumer hay topic subscription.
- [ ] Xác định rõ property cần lọc và thiết lập chúng trước khi gửi.
- [ ] Chọn đúng kiểu String, số hoặc Boolean cho từng property.
- [ ] Không tham chiếu message body trong selector.
- [ ] Kiểm tra tên header JMS được phép dùng; ưu tiên application properties cho điều kiện nghiệp vụ.
- [ ] Dùng IS NULL/IS NOT NULL khi cần xử lý property thiếu.
- [ ] Dùng ngoặc để biểu thức AND/OR dễ hiểu.
- [ ] Kiểm tra trường hợp selector FALSE và UNKNOWN.
- [ ] Với durable subscription, quản lý selector như một phần cấu hình lâu dài của subscription.
- [ ] Theo dõi backlog và message không được consumer nào chọn.
- [ ] Dùng broker authorization và application authorization cho bảo mật; không dựa vào selector.

## 13. Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Message Selector](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#message-selector)
- [Jakarta Messaging 3.1 Specification — Queue Semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#queue-semantics)
- [Jakarta Messaging 3.1 Specification — Topic Semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#topic-semantics)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework API — JmsListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework API — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
