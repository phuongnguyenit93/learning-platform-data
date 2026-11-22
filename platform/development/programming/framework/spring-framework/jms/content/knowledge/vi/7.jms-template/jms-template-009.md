# Tái sử dụng JmsTemplate sau khi cấu hình xong

## Mục tiêu học tập

Trong Spring Framework JMS, `JmsTemplate` là công cụ trung tâm để gửi và nhận message đồng bộ mà không phải tự viết lặp lại mã mở connection, tạo session, producer/consumer và giải phóng tài nguyên. Bài học này tập trung vào **vòng đời và cách dùng chung một `JmsTemplate` sau khi cấu hình hoàn tất**.

Sau bài này, bạn có thể:

1. Giải thích vì sao `JmsTemplate` **thread-safe sau khi cấu hình**, và ý nghĩa chính xác của cụm “once configured”.
2. Tạo **một bean singleton** rồi inject vào nhiều service, kể cả khi những service đó được gọi đồng thời.
3. Phân biệt chia sẻ template với chia sẻ `jakarta.jms.Session`, `MessageProducer`, `MessageConsumer`, `Connection` và `ConnectionFactory`.
4. Biết cấu hình nào phải ổn định trước khi bean được sử dụng; cách thay đổi destination, headers hoặc nội dung **theo từng lời gọi** mà không sửa cấu hình chung.
5. Hiểu vai trò riêng của `CachingConnectionFactory`, connection pool, transaction manager và listener container.
6. Viết ví dụ Java 17 với Spring Boot, Artemis và hai producer service cùng sử dụng một `JmsTemplate`; xác minh bản thân đối tượng được dùng chung và các message vẫn được gửi/nhận.
7. Nhận biết những lỗi về thread safety, transaction, tài nguyên và hiệu năng có thể phát sinh khi áp dụng sai nguyên tắc tái sử dụng.

> **Quy tắc cốt lõi:** cấu hình `JmsTemplate` **một lần khi khởi tạo ứng dụng**, sau đó **tái sử dụng instance ấy cho các thao tác**. Mỗi lời gọi sử dụng session/tài nguyên JMS phù hợp với ngữ cảnh và được Spring quản lý. Đừng giữ `Session` hoặc thay đổi các thuộc tính template giữa những request đồng thời.

## 1. Vì sao nên tái sử dụng `JmsTemplate`?

Giả sử một ứng dụng có ba service cần gửi message: `OrderService`, `BillingService` và `NotificationService`. Cả ba dùng cùng JMS broker, cùng quy tắc Queue và cùng message converter. Nếu mỗi request tự tạo một `JmsTemplate` mới, ứng dụng làm tăng mã cấu hình, khó kiểm soát chính sách và không thu được lợi ích tương ứng. Spring cho phép khai báo một template dưới dạng bean và chia sẻ cho nhiều thành phần.

~~~text
                   Spring ApplicationContext
                            |
                            v
                   JmsTemplate (singleton)
                      cấu hình ổn định
                     /       |        \
                    /        |         \
            OrderService BillingService NotificationService
                 |            |               |
                 +------------+---------------+
                           send(...)
                              |
                   ConnectionFactory được quản lý
                              |
                JMS Connection/Session/Producer
                              |
                           Broker
~~~

Một `JmsTemplate` chứa các **thuộc tính cấu hình**, như connection factory, destination resolver, message converter, default destination, receive timeout và QoS. Nó **không giữ “cuộc hội thoại đang xử lý” của từng request** trong một field dùng chung. Vì vậy nhiều collaborator có thể dùng chung reference đến template sau khi việc cấu hình hoàn tất.

Tài liệu Spring Framework nói rõ `JmsTemplate` **thread-safe once configured**. Điều này là cam kết ở cấp **template operation**, không phải bảo đảm rằng mọi collaborator, converter tự viết hay provider-specific extension đều tự động thread-safe.

### Những lợi ích thực tế

- **Nhất quán:** mọi service dùng cùng broker, policy chuyển đổi message và cách resolve destination.
- **Dễ quản trị:** thay cấu hình bằng profile/property/bean definition lúc startup, thay vì có các template được dựng ở nhiều nơi.
- **Giảm mã lặp:** các service chủ yếu gọi `convertAndSend`, `send` hoặc `receive`.
- **Dễ kiểm thử:** inject một abstraction Spring đã cấu hình sẵn, có thể mock/spying ở mức service.
- **Dễ quan sát:** có điểm thống nhất để gắn observation/interceptor hoặc custom converter phù hợp.
- **Dễ tối ưu nguồn lực:** dùng một `ConnectionFactory` được quản lý, có thể kết hợp pooling/caching. **Không nhầm** điều này với việc template tự duy trì một pool session.

Không nên kết luận rằng “một template là nhanh nhất trong mọi hoàn cảnh”. Hiệu năng phụ thuộc broker, network, connection/session caching, kích thước message, QoS và concurrency. Lợi ích chính của nguyên tắc này là **đúng vòng đời và an toàn khi dùng chung**.

## 2. “Thread-safe once configured” nghĩa là gì?

Hãy chia vòng đời `JmsTemplate` thành hai pha:

~~~text
PHA A — CONFIGURE (startup)
  tạo JmsTemplate
  setConnectionFactory(...)
  setMessageConverter(...)
  setDestinationResolver(...)
  setDefaultDestinationName(...)
  setPubSubDomain(...)
  setReceiveTimeout(...)
  set QoS / transaction defaults
  hoàn tất khai báo Spring bean
           |
           v
PHA B — USE (runtime)
  Thread A ──► convertAndSend(...)
  Thread B ──► convertAndSend(...)
  Thread C ──► receive(...) hoặc send(...)
           |
           v
  Template không bị cấu hình lại giữa các lời gọi
~~~

### Phân biệt ba nhóm trạng thái

| Loại trạng thái | Ví dụ | Có dùng chung trong template không? |
|---|---|---|
| **Cấu hình lâu dài** | `ConnectionFactory`, `MessageConverter`, `DestinationResolver`, QoS, default destination, receive timeout | Có; thiết lập trước khi bean được xuất bản cho các thread. |
| **Dữ liệu của một lời gọi** | Payload, destination được truyền vào method, `MessagePostProcessor`, correlation ID, custom JMS properties | Truyền qua tham số/callback; không cần ghi vào field cấu hình chung. |
| **Tài nguyên JMS đang hoạt động** | `Session`, `MessageProducer`, `MessageConsumer`, message đang nhận, JMS transaction | Được lấy và quản lý theo thao tác/transaction; **không chia sẻ bừa bãi** giữa thread. |

“Sau khi cấu hình xong” không có nghĩa object bị Java `final` hóa. `JmsTemplate` vẫn có setter công khai. Nó nghĩa là **ứng dụng phải tự coi các setter là thao tác dành cho giai đoạn cấu hình**. Không tự ý gọi setter trên template đang phục vụ nhiều request.

Ví dụ có rủi ro:

~~~java
// SAI: service/request thread thay đổi cấu hình chung.
public void publishForTenant(String tenantId, String text) {
    sharedTemplate.setDefaultDestinationName("tenant." + tenantId);
    sharedTemplate.convertAndSend(text);
}
~~~

Nếu hai thread cùng gọi, Thread A có thể set tên queue A, Thread B set tên queue B rồi Thread A lại gửi vào B. Không có gì bảo đảm kiểu “set rồi send” trở thành một thao tác nguyên tử.

Cách đúng: để template cố định và truyền destination vào từng lời gọi.

~~~java
// ĐÚNG: caller chọn destination cho từng send.
public void publishForTenant(String destination, String text) {
    sharedTemplate.convertAndSend(destination, text);
}
~~~

Đây là snippet nằm trong một service có field `sharedTemplate` đã inject. Tên destination thực tế vẫn phải được kiểm tra/allowlist để tránh tạo queue tùy tiện hoặc vượt quyền tenant.

### Một số setter cần thiết lập trước lúc startup hoàn tất

- `setConnectionFactory(...)`: nguồn kết nối JMS.
- `setDestinationResolver(...)`, `setPubSubDomain(...)`: chiến lược và loại destination (Queue/Topic).
- `setMessageConverter(...)`: chuyển giữa Java object và JMS message.
- `setDefaultDestinationName(...)` hoặc `setDefaultDestination(...)`: destination mặc định cho overload không nhận tên.
- `setReceiveTimeout(...)`: thời gian chờ của thao tác receive đồng bộ.
- `setExplicitQosEnabled(...)`, `setDeliveryMode(...)`, `setPriority(...)`, `setTimeToLive(...)`: cấu hình QoS nếu ứng dụng dùng.
- `setSessionTransacted(...)` và `setSessionAcknowledgeMode(...)`: hành vi session do template tạo khi không có transaction do môi trường quản lý.

Danh sách này là những ví dụ điển hình, không phải tất cả thuộc tính của mọi phiên bản Spring. Đừng trộn `setSessionTransacted` trên template với cấu hình transaction của **listener container**: đó là hai luồng hoạt động khác nhau.

## 3. Dùng singleton bean trong Spring

### 3.1. Khai báo một lần trong `@Configuration`

~~~java
@Configuration
public class MessagingConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false); // Queue
        template.setDefaultDestinationName("app.orders");
        template.setReceiveTimeout(2_000L);
        return template;
    }
}
~~~

Đoạn là **một class cấu hình** (cần import `jakarta.jms.ConnectionFactory`, `org.springframework.jms.core.JmsTemplate`, `@Bean` và `@Configuration`). Bean có scope mặc định là singleton trong một Spring `ApplicationContext`. Spring tạo bean, chạy method cấu hình và quản lý reference cho các collaborator.

Nếu dùng Spring Boot và `spring-boot-starter-artemis`, Boot có thể **tự cấu hình `JmsTemplate`** theo properties. Khi đã có template đáp ứng yêu cầu, không cần tạo bean thủ công. Ví dụ bên trên phù hợp khi muốn kiểm soát rõ policy hoặc demo; tránh vô tình có nhiều template cùng loại dẫn đến lỗi injection ambiguity.

### 3.2. Inject cùng một bean vào nhiều service

~~~java
@Service
public class OrderService {
    private final JmsTemplate jmsTemplate;

    public OrderService(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishOrder(String orderId) {
        jmsTemplate.convertAndSend("app.orders", orderId);
    }
}
~~~

~~~java
@Service
public class AuditService {
    private final JmsTemplate jmsTemplate;

    public AuditService(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void logOrder(String orderId) {
        jmsTemplate.convertAndSend("app.audit", "created:" + orderId);
    }
}
~~~

Hai class ở trên là **mã minh họa của hai file riêng**, cần import `org.springframework.stereotype.Service` và `JmsTemplate`. Nếu cả hai nằm trong cùng context và chỉ có một bean `JmsTemplate`, Spring inject **cùng instance**.

### 3.3. Bean singleton vẫn có thể được gọi đồng thời

Spring không tự đặt khóa quanh từng lời gọi của một bean singleton. Với hai HTTP request, hai scheduler hoặc hai worker, các method có thể chạy cùng lúc. Chính `JmsTemplate` được thiết kế để sử dụng như vậy sau cấu hình; service dùng nó vẫn phải giữ trạng thái của **chính service** an toàn nếu nhiều thread cùng gọi.

Ví dụ một counter không thread-safe trong service vẫn có race:

~~~java
// Anti-pattern: template an toàn không làm trường counter an toàn.
private int sentCount;

public void send(String payload) {
    sentCount++; // Race nếu nhiều thread gọi.
    jmsTemplate.convertAndSend("app.orders", payload);
}
~~~

Khi cần đếm, dùng `AtomicLong` hoặc metrics phù hợp; không phụ thuộc một mutable field thường. Đừng dùng `synchronized` trên toàn bộ service chỉ để “bảo vệ `JmsTemplate`”, vì nó có thể tạo nút thắt không cần thiết và không giải quyết độ tin cậy của broker.

## 4. Chia sẻ template KHÔNG đồng nghĩa chia sẻ một Session

### Cách JMS vận hành ở tầng dưới

Một send đơn giản có dạng khái niệm:

~~~text
JmsTemplate.convertAndSend(...)
  ├─ chọn MessageConverter / DestinationResolver
  ├─ lấy Connection/Session từ ConnectionFactory hoặc transaction hiện tại
  ├─ tạo/thuê MessageProducer
  ├─ tạo TextMessage và send()
  └─ release/return tài nguyên phù hợp
~~~

Spring xử lý tài nguyên và chuyển các `JMSException` thông thường thành ngoại lệ runtime thuộc họ Spring `JmsException`. Không nên tự thêm `try-with-resources` vào `JmsTemplate`, vì template là bean và không đại diện trực tiếp cho một session hay connection cần đóng sau từng send.

### JMS Session là đơn luồng

Jakarta Messaging quy định `Session` được sử dụng tuần tự bởi một luồng điều khiển tại một thời điểm. `MessageProducer` và `MessageConsumer` được tạo bởi session cũng thuộc quy tắc sử dụng đó.

~~~text
Thread A ─► JmsTemplate (chung) ─► Session A ─► Producer A
Thread B ─► JmsTemplate (chung) ─► Session B ─► Producer B
Thread C ─► JmsTemplate (chung) ─► Session C ─► Consumer C
                          |
                 cùng ConnectionFactory
~~~

Hình minh họa **mô hình hợp lệ**, không bắt buộc mỗi call luôn tạo một physical connection/session mới: pool có thể tái sử dụng session **khi không còn được dùng**, hoặc transaction manager cho một thread tái sử dụng session đang được bind trong cùng transaction.

**Sai lầm:** nhận `Session` trong callback của template rồi lưu vào field cho thread khác:

~~~java
// SAI: Session chỉ thuộc phạm vi callback/template operation.
private Session savedSession;

void captureSession() {
    jmsTemplate.execute(session -> {
        savedSession = session;
        return null;
    });
}
~~~

Sau khi callback kết thúc, Spring có thể đóng hoặc trả session về cache. Việc dùng lại `savedSession` trong request sau có thể gây lỗi lifecycle, concurrent access hoặc transaction sai phạm vi. Mọi tác vụ với session được Spring cấp trong callback nên hoàn thành **ngay trong callback**.

### Reuse diễn ra ở những cấp nào?

| Cấp | Có nên chia sẻ? | Ai quản lý? |
|---|---|---|
| `JmsTemplate` | **Có**, sau khi cấu hình | Spring container. |
| `ConnectionFactory` | Thông thường **có** | Spring/managed JMS provider/connection pool. |
| JMS `Connection` | Có thể được chia sẻ qua wrapper/pool, tùy provider | Connection factory/pool/container. |
| JMS `Session` | **Không sử dụng đồng thời** | Mỗi operation/transaction/worker và pooling layer. |
| `MessageProducer` | Không tự giữ một producer chung cho mọi thread | Tạo/lấy trong session, có thể được cache nội bộ an toàn theo ownership. |
| `MessageConsumer` | Không biến thành global consumer dùng chung | Listener container hoặc code sở hữu session. |
| `Message` | Message đang xây dựng/nhận có ngữ cảnh một operation | Caller/listener; đừng dùng một mutable message instance để gửi đồng thời. |

## 5. Phân biệt tái sử dụng `JmsTemplate` với resource caching/pooling

Một template singleton **không tự là pool**. Nếu `ConnectionFactory` luôn tạo connection/session/producer mới cho mỗi call, việc dùng lại template vẫn đúng nhưng có thể tốn chi phí kết nối. Để tối ưu, Spring có `SingleConnectionFactory`, `CachingConnectionFactory` và có thể dùng pool chuyên dụng từ provider.

### 5.1. `SingleConnectionFactory`

`SingleConnectionFactory` bọc một `ConnectionFactory` khác và cố gắng sử dụng một connection dùng chung. Nó giảm overhead mở connection khi các thao tác gửi/nhận lặp lại, nhưng **không đồng nghĩa** giữ một session duy nhất dùng đồng thời cho tất cả thread.

### 5.2. `CachingConnectionFactory`

`CachingConnectionFactory` mở rộng `SingleConnectionFactory` và có thể cache:

- `Session`.
- `MessageProducer`.
- `MessageConsumer` (tùy cấu hình và lưu ý semantics).

Tài liệu Spring chỉ ra `sessionCacheSize` mặc định là **1**. Cache có phân loại theo acknowledgement/transaction mode; số session thực tế được giữ có thể nhiều hơn một khi ứng dụng dùng nhiều mode. Khi nhiều thread đang hoạt động hơn số slot cache, tầng cache có thể tạo thêm session khi cần và giải phóng khi trả; đừng hiểu `sessionCacheSize=1` là “chỉ được một thread gọi template”.

Ví dụ cấu hình thủ công (chỉ chọn khi **chưa có** wrapping tương đương):

~~~java
@Bean
ConnectionFactory cachingConnectionFactory(
        @Qualifier("nativeConnectionFactory") ConnectionFactory nativeFactory) {
    CachingConnectionFactory cache =
            new CachingConnectionFactory(nativeFactory);
    cache.setSessionCacheSize(8);
    cache.setCacheProducers(true);
    return cache;
}
~~~

Snippet này cần import `org.springframework.jms.connection.CachingConnectionFactory`, `jakarta.jms.ConnectionFactory` và các annotation; giả định đã có bean raw `nativeConnectionFactory`. **Không dùng nguyên xi** nếu nó tạo vòng tham chiếu hay bọc chồng connection factory đã được Spring Boot tự cấu hình.

Trong Spring Boot 3.5, `spring-boot-starter-artemis` thường được auto-configure cùng `CachingConnectionFactory`. Có thể điều chỉnh qua properties:

~~~properties
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=8
spring.jms.cache.producers=true
~~~

Cấu hình này tác động đến **cache tài nguyên JMS** trong tầng connection factory, không thay đổi số lượng bean `JmsTemplate`. Tăng cache size chỉ nên thực hiện sau khi đo tải; điều kiện đúng còn phụ thuộc provider và số thread, transaction, consumer.

### 5.3. Pool không phải thread safety của Session

Một pool đúng chỉ phát một session đang được thuê cho một owner tại một thời điểm. Khi owner release/close logical handle, session mới trở lại pool. Nếu tự lưu reference session rồi cho nhiều thread dùng, bạn đã vượt khỏi cơ chế này.

### 5.4. Lưu ý với listener container

Listener container có cách lấy, cache và đóng consumer/session riêng; có thể kết hợp transaction manager. Đừng giả định đổi `spring.jms.cache.session-cache-size` sẽ tự đổi số thread của `@JmsListener`. Concurrency listener được điều chỉnh bằng cấu hình container, còn `JmsTemplate` thường đại diện phía producer hoặc receive đồng bộ.

## 6. Đổi dữ liệu theo lời gọi mà giữ template ổn định

Có rất nhiều nhu cầu động **không cần** chỉnh setter của template.

### 6.1. Destination được truyền vào method

~~~java
// JmsTemplate giữ nguyên pubSubDomain, resolver và connection factory.
jmsTemplate.convertAndSend("orders.commands", "order-42");
jmsTemplate.convertAndSend("payments.commands", "payment-42");
~~~

Hai lời gọi sử dụng các destination name khác nhau nhưng cùng cấu hình. Vì `JmsTemplate` không tự kiểm tra tên hợp lệ theo nghiệp vụ, production nên dùng constants/allowlist hoặc mapping được quản trị. Việc gọi resolver thành công cũng không đảm bảo broker đã provision queue vật lý.

### 6.2. Header và property riêng của message

Dùng `MessagePostProcessor` trong từng call:

~~~java
jmsTemplate.convertAndSend(
    "orders.commands",
    "order-42",
    message -> {
        message.setStringProperty("eventId", "evt-42");
        message.setJMSCorrelationID("order-42");
        return message;
    }
);
~~~

Callback nhận message **của lời gọi hiện tại** và trả lại message đã chỉnh sửa; template vẫn giữ các setting cũ. Việc gắn correlation/event ID nên dùng dữ liệu ổn định trong request và tránh chia sẻ mutable object giữa các callback.

### 6.3. `MessageCreator` cho logic tạo message đặc thù

~~~java
jmsTemplate.send("orders.commands", session -> {
    TextMessage message = session.createTextMessage("order-42");
    message.setStringProperty("schemaVersion", "1");
    return message;
});
~~~

`Session` do template cấp ở đúng thời điểm; thao tác trên session hoàn tất trong callback. Code này là snippet trong bean đã import `jakarta.jms.TextMessage` và inject template; không phải một chương trình độc lập.

### 6.4. Khi muốn Queue và Topic đồng thời

Nếu hai luồng nghiệp vụ đòi hỏi `pubSubDomain` khác nhau, hãy dùng **hai bean template** được cấu hình từ đầu:

~~~java
@Bean("queueJmsTemplate")
JmsTemplate queueJmsTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setPubSubDomain(false);
    return template;
}

@Bean("topicJmsTemplate")
JmsTemplate topicJmsTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setPubSubDomain(true);
    return template;
}
~~~

Hai bean trên có thể dùng chung `ConnectionFactory` nếu provider/configuration phù hợp. Khi inject, chọn rõ bằng `@Qualifier("queueJmsTemplate")` hoặc `@Qualifier("topicJmsTemplate")`. Đây là cách **tách cấu hình cố định**, không phải tạo template mới cho mỗi message.

### 6.5. Khi muốn QoS khác nhau

`JmsTemplate` có `setDeliveryMode`, `setPriority`, `setTimeToLive` và `setExplicitQosEnabled(true)`. Đây là những thuộc tính thiết lập ở **cấp template**, nên nếu có hai chính sách QoS cố định khác nhau, dùng hai bean có cấu hình rõ hoặc chọn một API có tùy chỉnh theo operation nếu phiên bản Spring hỗ trợ. Đừng đổi `setTimeToLive` trên singleton trước mỗi call.

## 7. Thời điểm cấu hình và quy tắc khởi tạo Spring

### Cách chuẩn

- Đặt properties trong `application.properties` hoặc `application.yml` theo môi trường.
- Spring Boot auto-configure template, hoặc method `@Bean` tạo template và set đủ thuộc tính.
- Inject bean qua **constructor injection** vào các service.
- Sử dụng template khi application context đã khởi tạo.

### Các cách dễ gây lỗi

**Gọi setter trong method request:**

~~~java
public void sendToQueue(String queue, String payload) {
    jmsTemplate.setDefaultDestinationName(queue); // Race!
    jmsTemplate.convertAndSend(payload);
}
~~~

**Tạo template trong mỗi method rồi tự cấu hình:**

~~~java
public void send(String text) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.convertAndSend("orders.commands", text);
}
~~~

Mã thứ hai thường hoạt động nhưng làm cấu hình phân tán, khó theo dõi/review và có thể bỏ sót timeout, converter, QoS. Nó không giúp việc gửi tránh cạnh tranh tài nguyên một cách tự nhiên; tài nguyên vẫn lấy từ connection factory.

**Lưu một mutable `MessageConverter` dùng chung mà không đảm bảo thread safety:** nếu converter có field đang cập nhật trong `toMessage/fromMessage`, template an toàn nhưng converter có thể race. Custom converters nên stateless hoặc thread-safe và cấu hình trước khi template hoạt động.

### Khi thực sự cần đổi cấu hình production

Ví dụ đổi broker endpoint, credentials, TLS hoặc policy từ Queue sang Topic là **thay đổi cấu hình toàn cục**. Nên triển khai thông qua cấu hình môi trường và vòng đời bean/context (refresh/redeploy, quản lý reconnect/failover tùy provider); không giả định gọi setter giữa các thread đã ổn định và mọi session cũ sẽ tự đổi sang broker mới.

## 8. Ví dụ hoàn chỉnh Java 17: một template, nhiều service, nhiều thread

Ví dụ dưới đây dùng Spring Boot **3.5.5**, Java **17+**, Maven và ActiveMQ Artemis. Mục tiêu chính là chứng minh:

- `OrderPublisher` và `AuditPublisher` nhận **cùng bean `JmsTemplate`**.
- Hai task được gửi trên hai thread mà **không thay đổi** cấu hình template.
- Listener nhận hai message trong một queue thử nghiệm.
- Mã sử dụng `@Bean` và constructor injection, không cất giữ JMS `Session` trong singleton.

### 8.1. Khởi động broker cục bộ

Cần Docker chạy được và port `61616` chưa dùng. Dùng image Artemis chính thức:

~~~bash
docker run --detach --rm --name reuse-jms-demo \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Broker khởi động với user/password demo. Console quản trị thường ở `http://localhost:8161`. Dùng broker rỗng của riêng bài, tránh chạy hai instance ứng dụng cùng queue nếu bạn muốn so sánh output.

### 8.2. Cấu trúc file

~~~text
reuse-jms-template/
├── pom.xml
└── src/main/
    ├── java/example/ReuseJmsTemplateApplication.java
    └── resources/application.properties
~~~

### 8.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>reuse-jms-template</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-artemis</artifactId>
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

### 8.4. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Demo: cache các session rảnh để có thể tái sử dụng.
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=4
~~~

`CachingConnectionFactory` là tầng connection/session caching riêng; dù đổi cache size, hai publisher **vẫn inject cùng template bean**. Với production, không hard-code password mà dùng secret manager.

### 8.5. `ReuseJmsTemplateApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

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
public class ReuseJmsTemplateApplication {

    private static final String QUEUE = "lesson.jms.template.reuse";

    public static void main(String[] args) {
        SpringApplication.run(ReuseJmsTemplateApplication.class, args);
    }

    // Tạo đúng một bean, cấu hình ổn định từ lúc startup.
    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false); // JMS Queue
        template.setDefaultDestinationName(QUEUE);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Component
    public static class OrderPublisher {
        private final JmsTemplate template;

        public OrderPublisher(JmsTemplate template) {
            this.template = template;
        }

        void publish(String orderId) {
            // Không gọi template.setDefaultDestinationName() ở đây.
            template.convertAndSend("order:" + orderId);
        }

        JmsTemplate sharedTemplate() {
            return template;
        }
    }

    @Component
    public static class AuditPublisher {
        private final JmsTemplate template;

        public AuditPublisher(JmsTemplate template) {
            this.template = template;
        }

        void publish(String eventId) {
            template.convertAndSend("audit:" + eventId);
        }

        JmsTemplate sharedTemplate() {
            return template;
        }
    }

    @Component
    public static class DemoReceiver {
        private final CountDownLatch received = new CountDownLatch(2);

        @JmsListener(destination = QUEUE)
        public void onMessage(String body) {
            System.out.println("received=" + body);
            received.countDown();
        }

        boolean awaitTwoMessages() throws InterruptedException {
            return received.await(15, TimeUnit.SECONDS);
        }
    }

    @Bean
    ApplicationRunner runDemo(OrderPublisher orders,
                              AuditPublisher audits,
                              DemoReceiver receiver) {
        return args -> {
            boolean same = orders.sharedTemplate()
                    == audits.sharedTemplate();
            System.out.println("sameJmsTemplate=" + same);

            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                Future<?> orderTask =
                        pool.submit(() -> orders.publish("42"));
                Future<?> auditTask =
                        pool.submit(() -> audits.publish("evt-42"));

                orderTask.get(15, TimeUnit.SECONDS);
                auditTask.get(15, TimeUnit.SECONDS);
            } finally {
                pool.shutdown();
            }

            System.out.println(
                    "bothReceived=" + receiver.awaitTwoMessages());
        };
    }
}
~~~

Đây là **một file Java đầy đủ**, với một public class và ba nested static components được Spring phát hiện. `CountDownLatch` là thread-safe và chỉ dùng để quan sát hai lần callback trong demo; nó **không** phải cơ chế xác nhận message, idempotency hoặc transaction.

### 8.6. Biên dịch/chạy

Ở thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Với broker rỗng, quyền truy cập đúng, queue có thể được auto-create theo policy Artemis và không có consumer khác, các dòng do code ứng dụng in ra có dạng:

~~~text
sameJmsTemplate=true
received=order:42
received=audit:evt-42
bothReceived=true
~~~

**Lưu ý chính xác về output:** hai dòng `received=...` có thể đổi thứ tự (hai task gửi đồng thời); Spring Boot còn in startup logs. `bothReceived=true` chỉ cho thấy listener demo gọi hai lần trong thời hạn chờ, **không chứng minh exactly-once** khi có retry/crash. Nếu queue đã chứa message cũ hoặc có consumer khác tranh nhận thì kết quả cần điều chỉnh.

### 8.7. Đọc đúng điều demo chứng minh

1. Trong `@Bean`, template được tạo **một lần** rồi được container giữ làm bean singleton.
2. Hai service đều dùng constructor injection của cùng kiểu `JmsTemplate`; in `sameJmsTemplate=true` cho biết cùng reference.
3. Mỗi service chạy trong một task khác nhau, dùng cùng method `convertAndSend(Object)`, cùng destination mặc định đã cấu hình.
4. `JmsTemplate` quản lý operation-specific JMS resources; hai thread **không** chia sẻ một raw `Session` bằng field.
5. `DemoReceiver` do listener container điều khiển và có lifecycle/concurrency **riêng**, không phải “một send làm callback trên đúng thread của producer”.
6. `CachingConnectionFactory` ở tầng dưới có thể cache session/producer nhàn rỗi, nhưng không làm thay đổi nguyên tắc template reusable.

Nếu muốn kiểm tra ở broker, vào Artemis console, xem `lesson.jms.template.reuse`, consumer count và message count. Khi listener commit/ack thành công và không có traffic khác, queue thường trở về depth 0.

Dừng ứng dụng bằng `Ctrl+C`, dừng broker:

~~~bash
docker stop reuse-jms-demo
~~~

Do container dùng `--rm` và không mount volume, dữ liệu broker demo sẽ không được giữ khi dừng. Không dùng cấu hình disposable này cho production.

## 9. Trường hợp transaction: template singleton, Session theo thread/transaction

Spring có `JmsTransactionManager` để quản lý **local JMS transaction** cho một `ConnectionFactory`. Khi một thread tham gia transaction JMS do Spring quản lý, `JmsTemplate` tìm session đã được bind với thread/transaction hiện tại và tham gia giao dịch ấy. Ở thread khác hoặc transaction khác, nó sử dụng ngữ cảnh tài nguyên phù hợp khác.

~~~text
JmsTemplate (một bean chung)
  |
  +-- Thread A [JMS Tx A] ──► Session A (thread-bound)
  |                            send(M1)
  |                            commit/rollback A
  |
  +-- Thread B [JMS Tx B] ──► Session B (thread-bound)
                               send(M2)
                               commit/rollback B
~~~

Không có session hoặc transaction instance chung cho mọi người chỉ vì họ dùng cùng template.

### 9.1. Ví dụ cấu hình JMS transaction manager

~~~java
@Bean
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Trong service dùng Spring transaction AOP:

~~~java
@Transactional("jmsTransactionManager")
public void publishBatch() {
    jmsTemplate.convertAndSend("orders.commands", "cmd-1");
    jmsTemplate.convertAndSend("orders.commands", "cmd-2");
    // Nếu cả hai dùng cùng local JMS transaction,
    // transaction manager quyết định commit/rollback khi method kết thúc.
}
~~~

Đây là **hai snippet cấu hình và service**, không phải project độc lập. Cần import `org.springframework.jms.connection.JmsTransactionManager`, `org.springframework.transaction.annotation.Transactional` và tên transaction manager khớp cấu hình thực tế. `@Transactional` có hiệu lực khi method được gọi qua Spring proxy đúng cách; self-invocation không áp dụng như lời gọi qua proxy.

### 9.2. Không tự “chia sẻ transaction” qua executor

~~~java
@Transactional("jmsTransactionManager")
public void badExample() {
    // Không giả định transaction JMS của thread gọi
    // tự truyền sang thread trong executor.
    executor.submit(
        () -> jmsTemplate.convertAndSend("orders.commands", "x"));
}
~~~

Đây là anti-pattern minh họa khi người viết mong tất cả nằm trong cùng transaction; mã không phải lớp Java độc lập. `JmsTransactionManager` ràng buộc session với thread, nên công việc mới trên executor có thể không tham gia cùng transaction. Nếu cần atomicity, tổ chức ranh giới thực thi và transaction đúng hoặc dùng cơ chế messaging/outbox khác phù hợp.

### 9.3. JMS transaction khác DB transaction

Một local `JmsTransactionManager` không tự commit/rollback database. Nếu đã cập nhật DB nhưng send JMS thất bại, trạng thái có thể lệch. Dùng transactional outbox/idempotency hoặc JTA/XA khi thật sự cần giao dịch phân tán và hạ tầng hỗ trợ. “Template thread-safe” không hề đồng nghĩa “toàn bộ chuỗi side effect exactly-once”.

## 10. Spring Boot auto-configuration và nguyên tắc tránh bean trùng

Khi có `spring-boot-starter-artemis` và cấu hình kết nối, Boot có thể tự tạo:

- `ConnectionFactory` và wrapper caching/pooling phù hợp.
- `JmsTemplate` (khi chưa có bean loại này do ứng dụng khai báo).
- Cấu hình hỗ trợ `@JmsListener` nếu JMS infrastructure được kích hoạt.

Nếu chỉ cần mặc định, có thể để Boot tạo template và inject trực tiếp:

~~~java
@Service
public class EventPublisher {
    private final JmsTemplate template;

    public EventPublisher(JmsTemplate template) {
        this.template = template;
    }

    public void publish(String eventId) {
        template.convertAndSend("events.queue", eventId);
    }
}
~~~

Trong `application.properties` có thể dùng:

~~~properties
spring.jms.pub-sub-domain=false
spring.jms.template.default-destination=events.queue
spring.jms.template.receive-timeout=2s
spring.jms.cache.session-cache-size=5
~~~

Các property này được Boot áp dụng trong auto-configuration; khi **tự khai báo `@Bean JmsTemplate`**, hãy kiểm tra xem những property Boot định thiết lập có còn được bind tự động không. Đừng mặc định template do chính bạn `new JmsTemplate(...)` sẽ nhận mọi setter từ `spring.jms.template.*` nếu không tự cấu hình.

### Khi có nhiều template

Nếu dùng hai broker hoặc hai chính sách cố định, nhiều template là hợp lý. Nhưng injection phải phân biệt:

~~~java
public EventPublisher(
        @Qualifier("ordersJmsTemplate") JmsTemplate template) {
    this.template = template;
}
~~~

Đây là **constructor snippet**. Nếu không có qualifier hoặc `@Primary` phù hợp, Spring có thể báo nhiều bean `JmsTemplate` và không biết chọn cái nào.

**Kết luận kỹ thuật ở đây:** “Tái sử dụng một template” được hiểu là **mỗi tập cấu hình ổn định chia sẻ một instance**. Không phải mọi ứng dụng bắt buộc chỉ có đúng một template cho mọi broker, mọi destination domain và mọi chính sách.

## 11. Synchronous receive và request-reply cũng tuân theo nguyên tắc

### 11.1. `receive` cần timeout

`JmsTemplate.receive(...)` và `receiveAndConvert(...)` là thao tác đồng bộ, có thể chặn thread cho đến khi có message. Nếu ứng dụng sử dụng template chung để cả send lẫn receive, hãy cấu hình `receiveTimeout` trước khi sử dụng. Ví dụ:

~~~java
@Bean
JmsTemplate pollingTemplate(ConnectionFactory cf) {
    JmsTemplate template = new JmsTemplate(cf);
    template.setReceiveTimeout(3_000L);
    return template;
}
~~~

Ở đây `receiveTimeout` là setting **chung của bean**. Không đổi nó trước từng lần receive nếu bean được chia sẻ. Nếu hai use case cần timeout khác nhau cố định, khai báo hai template hoặc lựa chọn API có override theo operation theo version đang dùng.

### 11.2. Tách polling khỏi listener container khi phù hợp

Một `@JmsListener` do container quản lý có concurrency và vòng đời nhận message riêng. `JmsTemplate.receive()` tạo một consumer nhận đồng bộ cho operation. Nếu vô tình vừa polling vừa tạo listener trên cùng Queue, chúng có thể **cạnh tranh nhận** message. Đây là semantics của queue, không phải lỗi thread-safe của template.

### 11.3. Request-reply

`JmsTemplate` có thao tác request-reply đồng bộ như `sendAndReceive(...)`, có thể tạo temporary queue cho phản hồi. Nó có thể block theo cấu hình reply timeout/API cụ thể; cần correlation, timeout và xử lý tình huống reply đến muộn. Tái sử dụng template vẫn hợp lệ sau cấu hình; không nên đặt state của từng request-reply vào mutable field chung trên bean.

## 12. MessageConverter và MessagePostProcessor phải phù hợp concurrent calls

Default `SimpleMessageConverter` có thể xử lý một số dạng message chuẩn (như text/bytes/serializable object). Để truyền JSON và object nghiệp vụ, ứng dụng thường định nghĩa converter khác.

Khi converter là một bean được nhiều thread gọi qua template:

- Ưu tiên converter **stateless** hoặc có thành phần thread-safe.
- Các cấu hình serializer, schema và mapping nên được khởi tạo trước.
- Không lưu “payload hiện tại”, “tenant hiện tại”, “requestId hiện tại” trong field mutable của converter.
- Nếu converter phụ thuộc registry hoặc cache riêng, kiểm tra thread-safety của registry/cache đó.
- Không giả định gửi một object Java tùy ý sẽ tự chuyển thành JSON theo đúng contract; phải cấu hình converter, content type và schema.

Ví dụ anti-pattern:

~~~java
// Chỉ minh họa lỗi — class converter rút gọn.
class UnsafeConverter {
    private String currentTenant;

    void setTenant(String tenant) {
        currentTenant = tenant;
    }

    String convert(String payload) {
        return currentTenant + ":" + payload;
    }
}
~~~

Nếu Thread A đặt tenant A rồi Thread B đặt tenant B, dữ liệu có thể bị gắn nhãn sai dù `JmsTemplate` an toàn. Hãy đưa tenant vào payload/header **theo mỗi lời gọi**, hoặc dùng context propagation được thiết kế rõ và kiểm thử đúng thread.

## 13. Lỗi thường gặp khi tái sử dụng `JmsTemplate`

| Anti-pattern | Hậu quả có thể xảy ra | Cách xử lý |
|---|---|---|
| Gọi `setDefaultDestinationName` trong mỗi request | Hai thread có thể gửi sai queue | Truyền destination vào `convertAndSend(name, payload)`. |
| Gọi `setPubSubDomain` trước từng send | Queue/Topic semantics có thể bị đổi giữa các call | Tách các bean template theo domain. |
| Tạo một template mới cho từng message | Cấu hình lặp, khó quan sát, policy không nhất quán | Inject singleton đã cấu hình. |
| Lưu `Session`/`MessageProducer` do callback template cấp vào field | Resource hết vòng đời hoặc bị dùng đồng thời | Chỉ dùng trong callback, để Spring quản lý. |
| Cho rằng template singleton có một Session singleton | Dễ thiết kế ack/transaction sai | Phân biệt template state với per-operation resources. |
| Tăng `sessionCacheSize` để tăng listener concurrency | Hai tham số ở tầng khác nhau | Điều chỉnh listener container và cache riêng theo tải. |
| Tạo custom converter có mutable request state | Race, lộ/nhầm payload giữa request | Converter thread-safe và per-message headers. |
| Chia sẻ template giữa nhiều tenant nhưng không ràng quyền | Gửi sang sai namespace hoặc broker | Allowlist, ACL broker và tách factory theo boundary bảo mật. |
| Đổi credentials/CF qua setter lúc runtime | Không xác định resource cũ/mới dùng policy nào | Quản lý lifecycle/reconfiguration rõ ràng. |
| Giả định `convertAndSend` trả về là consumer đã xử lý | Không phát hiện xử lý lỗi hoặc message tồn | Theo dõi broker/consumer ack, retry, DLQ, idempotency. |
| Chạy async trong method `@Transactional` rồi nghĩ cùng transaction | Thread mới không mang session/tx bound của thread trước | Giữ transaction boundary hoặc tổ chức outbox/JTA phù hợp. |
| Dùng mutable counter/collection trong sender service | Race ở logic service | Local variables, concurrent structures hoặc metrics. |

### Vì sao đồng thời có thể lỗi dù template là thread-safe?

Khi gặp exception dưới tải, cần phân tích **đúng lớp**: JMS broker mất kết nối, pool cạn session, custom converter không an toàn, transaction timeout, listener redelivery, message quá lớn, consumer chậm... Đây có thể là lỗi hạ tầng/logic không phải do template dùng chung. Đừng vội chuyển bean sang `prototype`; làm vậy có thể che bớt triệu chứng nhưng không sửa nguyên nhân.

## 14. Thiết kế nhiều broker hoặc nhiều mức bảo mật

Một `JmsTemplate` có một `ConnectionFactory` tham chiếu ở cấu hình. Nếu ứng dụng cần gửi đến **hai broker khác nhau**, tạo các factory và template riêng được đặt tên rõ:

~~~text
ordersConnectionFactory ─► ordersJmsTemplate ─► OrderService
auditConnectionFactory  ─► auditJmsTemplate  ─► AuditService
~~~

Một broker dùng hai destination nhưng cùng policy có thể dùng một template và tên khác nhau theo call. Hai broker/credentials/transaction policy khác nhau thường là hai template. Với multi-tenant:

- Nếu nhiều tenant cùng dùng queue vật lý và phân vùng bằng metadata, dùng per-message tenantId có validation và broker/app ACL phù hợp.
- Nếu mỗi tenant cần broker identity riêng, không chuyển credentials bằng cách sửa `ConnectionFactory` của shared template đang chạy.
- Nếu tenant route đổi thường xuyên, cân nhắc routing service/registry và các template đã cấu hình trước; giới hạn số kết nối/resource cùng tồn tại.
- Đừng dùng String destination từ HTTP input không kiểm tra, vì broker có thể tự tạo queue hoặc chấp nhận gửi vào tenant khác tùy cấu hình.

Điểm cần quyết định luôn là **ranh giới cấu hình ổn định**: một template có thể phục vụ nhiều tác vụ, nhưng không phải phép thay thế cho isolation, authorization và resource governance.

## 15. Quan sát và kiểm tra khả năng dùng chung trong thực tế

### 15.1. Kiểm tra identity của bean

Trong bài demo, biểu thức `orders.sharedTemplate() == audits.sharedTemplate()` trả `true` khi cả hai được inject cùng bean. Đây là phép kiểm tra **identity**, không phải đánh giá tải hoặc độ an toàn của provider.

### 15.2. Tải đồng thời

Dùng nhiều sender task gửi những message có ID duy nhất, đợi kết quả và quan sát message count. Chỉ xác nhận “không exception” chưa đủ: cần so số message đã gửi, nhận, ack, DLQ và các lỗi. Dưới tải, broker có thể áp dụng hạn mức hoặc network timeout; test phải xác định capacity và SLA riêng.

### 15.3. Đo các tài nguyên thực sự

Các metrics hữu ích:

- Số active/idle connection và session của pool/provider (nếu exposed).
- Producer send latency, error rate và timeout.
- Queue depth, consumer count, redelivery, dead-letter.
- Listener processing latency và transaction failures.
- Resource churn (tạo/đóng session quá nhiều) khi cache size thấp.
- Cache hit/miss hoặc session reuse (nếu implementation có số liệu).

Không dùng hashcode của `JmsTemplate` để suy ra đang có đúng một connection hoặc một session; identity bean và physical resource count là hai phép đo khác nhau.

### 15.4. Một kiểm thử tích hợp có giá trị

Một bài integration test thực sự nên khởi động broker riêng, inject hai sender, gửi đồng thời n message với unique event ID, rồi chờ consumer thu đủ ID duy nhất trong thời gian giới hạn. Kiểm tra:

1. Hai sender có cùng template bean.
2. Không có lỗi concurrency của custom converter/logic service.
3. Destination/Queue và transaction policy đúng.
4. Message được xử lý với dữ liệu không bị trộn giữa các thread.
5. Resource counts không tăng không kiểm soát sau khi hoàn tất tải.

Không cần viết unit test chỉ để đếm bao nhiêu lần setter được gọi khi đã có cấu hình đơn giản; kiểm thử end-to-end giải quyết rủi ro thực hơn.

## 16. Checklist áp dụng production

Trước khi công bố một bean `JmsTemplate` dùng chung, hãy xác nhận:

1. **Khai báo bean:** template là singleton Spring, được cấu hình đầy đủ qua Boot/`@Configuration` trước khi có sender nào sử dụng.
2. **ConnectionFactory:** đúng broker, credentials, TLS, pool/cache, recovery và lifecycle.
3. **Namespace:** Queue/Topic, destination resolver, default destination và allowlist được xác định rõ.
4. **Converter:** serializer/schema thread-safe, không giữ request context trong mutable fields.
5. **QoS/receive:** priority, TTL, delivery mode, reply/receive timeout phù hợp, không thay setters trong runtime path.
6. **Transactions:** xác định khi nào có JmsTransactionManager/JTA và điều gì không được bao phủ (DB, HTTP API).
7. **Concurrency:** không lưu `Session`/`Producer`/`Consumer` cho nhiều thread; listener/service cũng xử lý state thread-safe.
8. **Giám sát:** có metrics/log cho send error, queue backlog, consumer ack, retry/DLQ và session pool.
9. **Khả năng phục hồi:** lỗi mạng và provider failover được kiểm thử, không giả định send success là exactly-once.
10. **Thay đổi cấu hình:** deploy/refresh có quy trình kiểm soát; template mới được khởi tạo và thay thế theo lifecycle đúng.
11. **Đa tenant/broker:** tách template theo khác biệt thật sự của connection/policy, không dùng setters để hoán đổi danh tính.
12. **Resource sizing:** cache/pool được đo và điều chỉnh; không gắn “một bean” với “một session”.

## 17. Câu hỏi tự kiểm tra

**1. Hai controller khác nhau có thể cùng inject một `JmsTemplate` và gọi `convertAndSend` song song không?** Có, khi template đã cấu hình xong và các dependency/callback tùy chỉnh được thiết kế an toàn cho concurrent calls.

**2. Dùng một template có nghĩa chỉ có một JMS Session không?** Không. Spring lấy session phù hợp theo thao tác/transaction; pooling có thể tái sử dụng session khi rảnh nhưng session không được dùng đồng thời.

**3. Muốn thay queue trong mỗi request có cần `setDefaultDestinationName` không?** Không. Dùng overload `convertAndSend(destinationName, payload)` và kiểm tra destination name.

**4. Muốn một template gửi Queue và một template gửi Topic thì làm gì?** Cấu hình hai bean ổn định với `pubSubDomain` khác nhau và inject rõ bằng qualifier.

**5. Vì sao không tạo template mới trong mỗi lần gửi?** Nó làm policy phân tán và khó quản lý, trong khi Spring đã thiết kế template dùng chung an toàn sau cấu hình.

**6. `CachingConnectionFactory.sessionCacheSize=1` có ngăn hai thread gọi template cùng lúc không?** Không. Cache size giới hạn số session nhàn rỗi được giữ theo loại, không phải một khóa tuần tự hóa mọi template call.

**7. Template thread-safe có làm custom `MessageConverter` có mutable field thành thread-safe không?** Không. Converter cũng phải stateless hoặc đồng bộ hóa đúng, và tốt nhất nhận metadata theo message.

**8. Hai method có `@Transactional("jmsTransactionManager")` gọi từ hai thread có dùng một JMS Session chung không?** Không. Giao dịch và session được gắn với thread/transaction tương ứng.

**9. Một sender dùng `convertAndSend` rồi thấy không có exception; có chắc consumer đã xử lý thành công không?** Không. Phải theo dõi broker, subscriber/consumer, ack, retry, DLQ hoặc cơ chế xác nhận ở tầng nghiệp vụ.

**10. Vì sao trong ví dụ có một template mà vẫn cần `CachingConnectionFactory`?** Template và cache giải quyết hai việc riêng: một cấu hình thao tác có thể dùng chung; một tầng tối ưu chi phí tạo/đóng JMS resource.

**11. Nếu đổi broker URL trong shared template bằng setter khi đang chạy có an toàn không?** Không có cam kết an toàn theo thiết kế “once configured”. Hãy dùng reconfiguration/lifecycle có kiểm soát.

**12. Spring Framework 7 có gì mới liên quan?** Có `JmsClient` fluent API, có thể xây trên `JmsTemplate` để dùng các setting đã cấu hình; nó không làm mất nguyên tắc phân biệt template configuration với per-operation resources. Với Spring Boot 3.5/Framework 6.2 trong ví dụ, `JmsTemplate` là API dùng trực tiếp.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — tuyên bố thread-safe once configured, lifecycle template, callback, caching và transactions.
- [Spring Framework — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — method `convertAndSend`, `send`, `receive`, setters và callback.
- [Spring Framework — CachingConnectionFactory API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html) — session cache và resource reuse.
- [Spring Framework — JmsTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html) — thread-bound JMS transaction resources.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html) — Artemis starter, ConnectionFactory auto-configuration và caching.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — `spring.jms.cache.*`, `spring.jms.template.*`, `spring.artemis.*`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/) — threading restrictions của JMS Session và nguyên tắc giao nhận.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html) — broker cục bộ dành cho demo.

**Ghi nhớ:** **Một `JmsTemplate` được cấu hình ổn định có thể được nhiều service và thread gọi chung.** Tài nguyên JMS của từng call vẫn có vòng đời/transaction riêng do Spring và `ConnectionFactory` quản lý. Khi cần thay dữ liệu, hãy dùng tham số và callback theo call; khi cần thay chính sách lâu dài, hãy tạo/cấu hình bean thích hợp trong lifecycle của ứng dụng.
