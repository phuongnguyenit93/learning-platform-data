# Cấu hình ConnectionFactory do nhà cung cấp JMS triển khai trong Spring

## 1. ConnectionFactory nằm ở đâu trong kiến trúc JMS?

JMS định nghĩa các interface chuẩn để ứng dụng gửi và nhận message. Trong đó, `ConnectionFactory` là điểm khởi đầu để tạo connection hoặc context tới hệ thống messaging. Bản thân interface không quyết định cách kết nối tới broker; nhà cung cấp JMS (JMS provider) triển khai interface này và bổ sung các thiết lập đặc thù cho sản phẩm của họ.

Ví dụ về provider gồm ActiveMQ Classic, ActiveMQ Artemis, IBM MQ và các hệ thống JMS khác. Mỗi provider có implementation, thư viện client, cách khai báo endpoint, xác thực, TLS, failover và pooling riêng. Spring JMS làm việc với interface chuẩn `jakarta.jms.ConnectionFactory` (Spring Framework 6 trở lên), nên có thể dùng các provider khác nhau mà không phải viết lại `JmsTemplate` hoặc listener nghiệp vụ.

Luồng tổng quát:

~~~text
Spring application
    |
    +-- JmsTemplate / @JmsListener container
                 |
                 v
       jakarta.jms.ConnectionFactory
                 |
                 v
       Provider implementation
                 |
                 v
        JMS broker / messaging server
~~~

Spring quản lý cách ứng dụng sử dụng ConnectionFactory. Provider implementation quản lý chi tiết giao tiếp với broker. Cấu hình cần tách rõ hai phần này để có thể đổi broker hoặc môi trường mà không làm thay đổi logic nghiệp vụ.

Sau bài học, bạn cần có thể:

- Phân biệt interface ConnectionFactory với implementation do provider cung cấp.
- Giải thích connection, session, producer, consumer và JMSContext.
- Cấu hình provider bằng Java, properties hoặc JNDI theo môi trường.
- Đưa ConnectionFactory vào JmsTemplate và listener container.
- Chọn cache hoặc pool phù hợp với vòng đời kết nối.
- Cấu hình xác thực, TLS, failover và transaction ở đúng lớp.
- Kiểm thử kết nối và giao nhận bằng broker mục tiêu.

## 2. Phân biệt các thành phần JMS

### 2.1 ConnectionFactory

`ConnectionFactory` là interface chuẩn của JMS. Nó tạo các đối tượng làm việc với provider, chẳng hạn:

- `Connection`: kết nối tới JMS provider; một connection có thể chứa nhiều session.
- `JMSContext`: API JMS 2.0 kết hợp connection và session trong một đối tượng, hỗ trợ try-with-resources.
- `Session`: ngữ cảnh tạo message, producer, consumer và transaction theo mô hình JMS.
- `MessageProducer` / `JMSProducer`: gửi message tới destination.
- `MessageConsumer` / `JMSConsumer`: nhận message từ destination.

ConnectionFactory không phải là broker và cũng không phải một connection đang mở. Nó là factory tạo các tài nguyên kết nối.

### 2.2 Provider implementation

Provider cung cấp class triển khai `ConnectionFactory` hoặc biến thể có khả năng XA. Implementation đó biết cách:

- Kết nối tới broker qua protocol và transport của sản phẩm.
- Xác thực bằng username/password, token hoặc cơ chế identity được hỗ trợ.
- Thiết lập TLS, truststore, keystore và hostname verification.
- Chọn virtual host, namespace hoặc địa chỉ broker nếu sản phẩm có khái niệm tương ứng.
- Cấu hình reconnect, failover, heartbeat, timeout và client identifier.
- Áp dụng các tùy chọn hiệu năng như prefetch, producer flow control và connection pooling.

Tên class và property không được chuẩn hóa chung giữa các provider. Hãy dùng tài liệu đúng phiên bản client library của broker đang triển khai.

### 2.3 Spring JMS sử dụng factory

Spring JMS nhận một ConnectionFactory thông qua dependency injection. Các thành phần thường gặp:

- `JmsTemplate`: gửi và nhận message theo kiểu template; quản lý việc lấy và giải phóng tài nguyên JMS trong mỗi thao tác.
- `DefaultMessageListenerContainer`: listener container quản lý consumer, session, connection recovery và lifecycle.
- `DefaultJmsListenerContainerFactory`: tạo listener container cho các method `@JmsListener`.
- `JmsTransactionManager`: quản lý transaction JMS cục bộ trên một ConnectionFactory.
- `CachingConnectionFactory`: wrapper của Spring để chia sẻ connection và cache một số tài nguyên JMS theo cấu hình.

Spring không yêu cầu handler nghiệp vụ biết class cụ thể của provider. Handler chỉ làm việc với payload và service ứng dụng.

## 3. Cấu hình ConnectionFactory theo provider

Không có một bộ thuộc tính kết nối JMS duy nhất áp dụng cho mọi broker. Có ba cách phổ biến để đưa provider implementation vào Spring.

### 3.1 Khởi tạo implementation bằng Java

Nếu ứng dụng tự quản lý kết nối, tạo bean từ class của provider. Ví dụ về cấu trúc cấu hình:

~~~java
@Configuration
public class ProviderJmsConfiguration {

    @Bean
    public ConnectionFactory providerConnectionFactory(
            JmsProviderProperties properties) {

        // Khởi tạo factory class do provider cung cấp.
        // Đặt broker URL, credentials, TLS và các tùy chọn
        // theo API riêng của provider.
        return createProviderFactory(properties);
    }
}
~~~

`JmsProviderProperties` và `createProviderFactory` trong ví dụ là kiểu/helper thuộc ứng dụng, không phải API chuẩn của Spring hoặc JMS. Phần tạo object thực tế phải gọi constructor hoặc setter của provider client library đang dùng.

Cách này phù hợp khi cần kiểm soát rõ các thiết lập provider hoặc khi ứng dụng chạy ngoài application server. Nhược điểm là lớp cấu hình phụ thuộc thư viện và API của provider; hãy cô lập dependency đó trong một module hạ tầng.

### 3.2 Lấy ConnectionFactory qua JNDI

Trong application server hoặc môi trường đã quản lý JMS resource, ConnectionFactory thường được tạo và cấu hình bên ngoài ứng dụng, sau đó đăng ký trong JNDI.

Ứng dụng lookup resource theo JNDI name, ví dụ `java:/JmsXA` hoặc tên do nền tảng triển khai quy định. Tên cụ thể không phải chuẩn chung và phải lấy từ cấu hình của môi trường.

Lợi ích của JNDI:

- Broker URL và credentials được quản trị tập trung.
- Application server có thể quản lý pool, security identity và lifecycle.
- Ứng dụng không cần biết class khởi tạo của provider.
- Có thể đổi endpoint hoặc credential qua cấu hình triển khai.

Khi dùng JNDI, cần xác định resource trả về là ConnectionFactory thường hay XA-capable factory, và ai chịu trách nhiệm đóng hoặc quản lý connection. Không tự tạo thêm pool trong ứng dụng nếu application server đã quản lý pooling.

### 3.3 Spring Boot auto-configuration

Spring Boot có thể tự cấu hình ConnectionFactory khi có starter/client library phù hợp và property của provider. Ví dụ các nhóm cấu hình phổ biến:

| Provider | Prefix cấu hình Spring Boot thường gặp | Ví dụ thiết lập |
|---|---|---|
| ActiveMQ Classic | `spring.activemq.*` | `broker-url`, `user`, `password` |
| ActiveMQ Artemis | `spring.artemis.*` | `mode`, `broker-url`, `user`, `password` |
| JNDI JMS resource | `spring.jms.*` | `jndi-name` |

Tên property và hành vi auto-configuration có thể thay đổi theo phiên bản Spring Boot và dependency được thêm vào. Đọc reference documentation đúng phiên bản trước khi sao chép cấu hình. Nếu dùng Spring Framework thuần, không có auto-configuration của Boot; cần tự khai báo provider ConnectionFactory bean hoặc lookup qua JNDI.

Ví dụ cấu hình Boot cho một môi trường ActiveMQ Classic:

~~~yaml
spring:
  activemq:
    broker-url: ${JMS_BROKER_URL:tcp://localhost:61616}
    user: ${JMS_USERNAME}
    password: ${JMS_PASSWORD}
~~~

Đây là ví dụ property của Spring Boot khi dùng tích hợp ActiveMQ Classic tương ứng. Với Artemis hoặc provider khác, dùng prefix và thuộc tính riêng của provider đó. Không chuyển nguyên YAML này sang một broker khác rồi giả định nó có cùng semantics.

Credentials không nên được hard-code hoặc commit vào repository. Hãy cấp chúng qua environment, secret manager hoặc cơ chế bảo mật của nền tảng.

## 4. Đưa ConnectionFactory vào Spring JMS

Khi provider ConnectionFactory đã được tạo hoặc lookup và đăng ký thành bean, các thành phần Spring JMS có thể nhận nó qua constructor hoặc factory method.

Ví dụ dưới đây dùng Jakarta Messaging và Spring Framework 6+. Bean `connectionFactory` được cung cấp bởi provider configuration, JNDI hoặc auto-configuration của Spring Boot.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class SpringJmsConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setTimeToLive(60_000L);
        return template;
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Các thiết lập minh họa:

- `JmsTemplate` dùng queue domain vì `setPubSubDomain(false)`.
- `DeliveryMode.PERSISTENT` yêu cầu delivery mode persistent; việc lưu bền vững thực tế còn phụ thuộc broker và cấu hình destination.
- `setTimeToLive(60_000L)` đặt thời gian sống 60 giây cho message được gửi qua template này.
- Listener container dùng từ 2 đến 8 consumer theo tải và khả năng của broker.
- `setSessionTransacted(true)` bật JMS session transaction cho listener container.

Ví dụ là một lớp cấu hình Spring, không phải chương trình standalone. Nó cần dependency Spring JMS, Jakarta Messaging API và một ConnectionFactory bean hợp lệ do provider hoặc nền tảng cung cấp.

Một listener có thể dùng factory này:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void receive(String payload) {
        // Chuyển payload tới service nghiệp vụ.
    }
}
~~~

Handler chỉ xử lý payload. Nó không tạo connection, mở session hoặc tự đọc broker URL. Spring listener container quản lý việc tiêu thụ message.

## 5. Cấu hình các thuộc tính kết nối quan trọng

### 5.1 Endpoint và topology

Provider thường cần broker URL hoặc host/port. Một số sản phẩm dùng URI có scheme riêng, một số dùng danh sách địa chỉ failover, một số dùng JNDI hoặc resource name.

Phân biệt:

- **Broker endpoint:** địa chỉ kết nối tới server.
- **Destination:** queue hoặc topic mà ứng dụng gửi/nhận.
- **Virtual host / namespace:** phạm vi tài nguyên nếu provider hỗ trợ.
- **Client ID:** định danh JMS client, có thể ảnh hưởng durable subscription.
- **Subscription name:** tên durable subscription, không phải địa chỉ broker.

Không đưa queue name vào vị trí broker URL hoặc dùng destination làm client identity.

### 5.2 Authentication và authorization

ConnectionFactory có thể nhận credentials hoặc cơ chế identity do container cung cấp. Cần:

- Dùng tài khoản riêng cho từng ứng dụng hoặc nhóm dịch vụ.
- Cấp quyền tối thiểu: connect, send, consume và quyền quản lý destination khi thật sự cần.
- Không dùng tài khoản admin cho listener hoặc publisher thông thường.
- Lưu secret ngoài source code và tránh ghi chúng vào log.
- Có quy trình rotate credential và kiểm tra kết nối sau khi rotate.

Xác thực kết nối không tự cấp quyền đọc mọi queue/topic. Broker vẫn cần authorization policy cho destination.

### 5.3 TLS và bảo vệ transport

Nếu broker yêu cầu TLS, cấu hình truststore, keystore, client certificate và hostname verification theo tài liệu provider. Một số provider nhận SSL options qua URI; provider khác dùng object cấu hình hoặc system properties.

Không tắt certificate validation để “sửa nhanh” lỗi kết nối production. Khi gặp lỗi TLS, kiểm tra certificate chain, hostname, thời hạn chứng thư, truststore và cấu hình protocol.

### 5.4 Timeout, heartbeat và reconnect

Các thiết lập provider thường có:

- Connection establishment timeout.
- Read/write timeout.
- Heartbeat hoặc inactivity timeout.
- Reconnect/failover delay và số lần thử.
- Maximum reconnect attempts hoặc retry interval.
- Client failure detection.

Đây là thiết lập của transport/provider, khác với send timeout của channel hoặc receive timeout của ứng dụng. Reconnect thành công cũng không tự bảo đảm message đang xử lý được khôi phục đúng; cần hiểu acknowledgement và redelivery của provider.

### 5.5 Prefetch và flow control

Một số provider gửi trước một số lượng message cho consumer để tăng throughput. Prefetch quá lớn có thể làm message bị giữ ở một consumer chậm, giảm tính công bằng hoặc tăng memory usage. Prefetch quá nhỏ có thể giảm throughput.

Chọn giá trị dựa trên thời gian xử lý, số consumer, kích thước message và khả năng broker. Các tên property và đơn vị cấu hình khác nhau theo provider.

## 6. ConnectionFactory, cache và pool

### 6.1 Dùng trực tiếp provider ConnectionFactory

Dùng trực tiếp factory phù hợp khi provider đã quản lý connection hoặc khi workload không cần thêm caching/pooling ở lớp Spring. Spring JMS vẫn quản lý tài nguyên cho từng thao tác hoặc listener container.

Không tạo connection mới trong mỗi lần xử lý message bằng cách gọi provider factory thủ công. Việc mở connection thường tốn kém hơn tạo message hoặc sử dụng session đã được quản lý.

### 6.2 SingleConnectionFactory

`SingleConnectionFactory` của Spring chia sẻ một JMS Connection cho nhiều thao tác. Nó hữu ích trong một số môi trường không có pool và cần giảm số connection vật lý.

Tuy nhiên, chia sẻ một connection không đồng nghĩa mọi session có thể được dùng đồng thời từ nhiều thread. JMS session có quy tắc concurrency riêng; để Spring template hoặc listener container quản lý session thay vì chia sẻ session tùy tiện.

### 6.3 CachingConnectionFactory

`CachingConnectionFactory` mở rộng cơ chế chia sẻ connection và cache một số session, producer và consumer theo cấu hình. Nó có thể giảm chi phí tạo tài nguyên trong các workload phù hợp.

Cần lưu ý:

- Cache size và loại tài nguyên được cache phải phù hợp với concurrency.
- Durable subscription, selector và consumer identity có lifecycle riêng; không bật cache consumer tùy tiện.
- Cache không thay thế persistence hoặc failover của broker.
- Khi ứng dụng shutdown, wrapper cần được đóng đúng lifecycle để giải phóng tài nguyên.
- Không lồng nhiều lớp cache/pool nếu chưa hiểu thứ tự quản lý tài nguyên.

### 6.4 Connection pool

Pool giữ một số connection/session hoặc wrapper resource để tái sử dụng. Có thể dùng pool do provider cung cấp, thư viện pooling tương thích JMS hoặc application server quản lý.

Hãy xác định pool ở một lớp duy nhất. Nếu application server đã cung cấp pooled ConnectionFactory, không tự bọc thêm pool khác theo mặc định. Kiểm tra giới hạn connection, session, idle timeout, validation và hành vi khi broker mất kết nối.

## 7. Transaction và acknowledgement

ConnectionFactory là một phần của đường đi transaction, nhưng transaction được cấu hình ở tầng session, listener container hoặc transaction manager.

- **Session transaction:** listener có thể chạy trong JMS session transaction. Commit xác nhận xử lý; rollback cho phép broker redeliver theo semantics provider.
- **JmsTransactionManager:** quản lý transaction JMS cục bộ cho một ConnectionFactory.
- **JtaTransactionManager:** phối hợp transaction phân tán khi môi trường và tài nguyên XA được cấu hình phù hợp.
- **XA ConnectionFactory:** provider cần cung cấp resource hỗ trợ XA nếu muốn enlist JMS vào XA transaction.

Không giả định mọi ConnectionFactory đều hỗ trợ XA. Một ConnectionFactory thường không thể tự biến thành XA chỉ bằng cách bật một flag trong Spring.

Nếu transaction chỉ bao phủ JMS session mà còn cập nhật database, hai hệ thống có thể không cùng commit nguyên tử. Cần cân nhắc JTA/XA hoặc thiết kế outbox/inbox và idempotency theo yêu cầu nhất quán.

## 8. Quản lý vòng đời kết nối

Trong ứng dụng Spring:

- `JmsTemplate` quản lý việc lấy và giải phóng connection/session theo cơ chế của ConnectionFactory.
- Listener container giữ tài nguyên tiêu thụ trong thời gian listener hoạt động và quản lý start/stop/recovery.
- Application context quản lý lifecycle bean và có thể đóng wrapper/pool khi shutdown.
- Khi dùng JMSContext trực tiếp, hãy đóng bằng try-with-resources hoặc quản lý lifecycle rõ ràng.

Không đóng provider ConnectionFactory đang được nhiều bean sử dụng. Cũng không tự đóng connection/session mà listener container đang sở hữu.

Khi broker restart, listener container và provider có thể thử reconnect theo cấu hình. Hãy kiểm thử hành vi recovery thực tế: consumer có được tạo lại không, subscription có được giữ không, message chưa acknowledge có được redeliver không và transaction có bị rollback không.

## 9. Lựa chọn ConnectionFactory theo môi trường

| Môi trường | Cách cung cấp factory thường phù hợp |
|---|---|
| Local development | Provider client library với endpoint local hoặc broker container |
| Integration test | Broker test riêng hoặc Testcontainers |
| Spring Boot application | Provider starter và auto-configuration theo properties |
| Application server | JNDI resource do server quản lý |
| Spring Framework thuần | Tự tạo provider factory bean hoặc lookup JNDI |
| Hạ tầng cần XA | XA-capable provider resource và transaction manager tương ứng |

Đừng đưa credentials production vào profile local. Dùng endpoint, secret và quyền riêng cho từng môi trường. Hãy kiểm tra startup fail-fast khi các thuộc tính bắt buộc thiếu hoặc endpoint không hợp lệ.

## 10. Kiểm thử cấu hình ConnectionFactory

Nên chia kiểm thử theo phạm vi:

1. **Kiểm thử cấu hình properties:** xác nhận broker URL, port, credentials và các tùy chọn được bind đúng.
2. **Kiểm thử bean wiring:** xác nhận JmsTemplate và listener factory nhận đúng ConnectionFactory.
3. **Kiểm thử kết nối:** mở kết nối tới broker thử nghiệm và xác minh authentication/TLS.
4. **Kiểm thử gửi/nhận:** gửi message tới queue hoặc topic rồi xác minh consumer nhận đúng payload.
5. **Kiểm thử transaction:** tạo lỗi có chủ đích và xác minh rollback/redelivery theo cấu hình.
6. **Kiểm thử recovery:** restart broker hoặc ngắt mạng để xác minh reconnect và listener recovery.
7. **Kiểm thử pooling:** đo giới hạn connection/session và xác minh tài nguyên được giải phóng sau shutdown.

Unit test nghiệp vụ có thể mock JmsTemplate hoặc service; không cần broker thật. Nhưng các thuộc tính provider như TLS, failover, durable subscription, XA và redelivery cần integration test với đúng broker/version sẽ triển khai.

## 11. Lỗi thường gặp

- **Nhầm ConnectionFactory với connection:** factory tạo connection; nó không phải một socket/connection đang mở.
- **Tự tạo ConnectionFactory trong handler:** trộn hạ tầng vào nghiệp vụ và gây overhead.
- **Dùng property của sai provider:** mỗi broker có prefix, URI và client option riêng.
- **Trộn javax.jms và jakarta.jms:** API namespace phải tương thích với thế hệ Spring và client library.
- **Dùng JNDI nhưng vẫn tự tạo pool:** có thể tạo hai lớp pooling và gây khó quản lý lifecycle.
- **Chia sẻ session giữa thread:** JMS session có giới hạn concurrency; hãy để template/container quản lý.
- **Tạo connection mỗi message:** làm tăng latency và áp lực broker.
- **Bật cache consumer không cân nhắc durable subscription:** có thể giữ consumer/subscription lâu hơn dự kiến.
- **Nhầm persistent delivery với transaction:** delivery mode persistent không tự bảo đảm nghiệp vụ và database commit nguyên tử.
- **Giả định mọi factory hỗ trợ XA:** cần provider resource đúng loại và transaction manager tương ứng.
- **Hard-code credentials:** làm lộ secret qua Git, build hoặc log.
- **Không kiểm thử reconnect:** cấu hình kết nối ban đầu thành công chưa chứng minh recovery hoạt động.

## 12. Checklist trước khi triển khai

- Provider và phiên bản client library có tương thích với JMS namespace của Spring không?
- ConnectionFactory bean được tạo bởi provider config, Boot auto-configuration hay JNDI?
- Broker URL, destination và clientID có được phân biệt rõ không?
- Credentials được cấp từ secret manager/environment và có quyền tối thiểu chưa?
- TLS, hostname verification và certificate chain đã được kiểm tra chưa?
- Timeout, heartbeat, reconnect và failover phù hợp với broker chưa?
- Có cần cache hoặc pool không, và lớp nào chịu trách nhiệm quản lý?
- Concurrency của listener có phù hợp với giới hạn connection/session không?
- Transaction là local hay XA? Provider resource có hỗ trợ không?
- Lifecycle start/stop/shutdown có giải phóng tài nguyên đúng cách không?
- Integration test đã kiểm tra authentication, send/receive, rollback và recovery trên broker mục tiêu chưa?

Khi ConnectionFactory do provider triển khai được cấu hình đúng và được Spring quản lý qua một ranh giới rõ ràng, ứng dụng có thể tận dụng đặc tính của broker mà vẫn giữ JmsTemplate, listener và logic nghiệp vụ ít phụ thuộc vào nhà cung cấp.