# clientId, tên subscription và vòng đời bên nhận trong Spring JMS

## 1. Bức tranh tổng thể

Trong JMS, bên nhận có thể tiêu thụ message từ queue hoặc subscribe topic. Với queue, message thường được phân phối cho một consumer phù hợp theo semantics của provider. Với topic, mỗi subscription là một luồng nhận riêng; nhiều subscription có thể nhận bản sao của cùng một publication.

Khi dùng **durable topic subscription**, broker cần nhận diện subscription qua một danh tính ổn định để tiếp tục giữ message khi consumer tạm thời offline. Hai khái niệm quan trọng là:

- **clientID:** định danh JMS client ở cấp connection. Nó giúp provider nhận diện client và tham gia vào danh tính của durable subscription theo quy tắc JMS/provider.
- **subscription name:** tên logic của durable subscription. Nó nhận diện subscription mà ứng dụng muốn tiếp tục sử dụng qua các lần kết nối.

Trong JMS cổ điển, durable subscription không chỉ là một consumer đang mở. Subscription có thể tồn tại trên broker sau khi consumer đóng, để message được giữ lại trong thời gian consumer vắng mặt theo chính sách của broker.

Sau bài học, bạn cần có thể:

- Phân biệt clientID, subscription name và tên destination.
- Giải thích durable và non-durable topic subscription.
- Quản lý start, stop, close và unsubscribe đúng mục đích.
- Cấu hình durable listener trong Spring JMS.
- Hiểu shared và unshared durable subscription trong JMS 2.0.
- Tránh xung đột clientID khi triển khai nhiều instance.
- Thiết kế quyền, selector, lưu trữ và xử lý message tồn đọng khi consumer hoạt động trở lại.

## 2. Queue, topic và subscription

### 2.1 Queue

Queue thường được dùng cho mô hình point-to-point. Một message trong queue được giao cho một consumer để xử lý theo cơ chế phân phối của provider. Nếu nhiều worker cùng đọc một queue, chúng thường cạnh tranh nhận công việc.

Queue không cần durable topic subscription name để lưu message. Việc message còn tồn tại khi không có consumer phụ thuộc delivery mode, queue policy, expiration, broker persistence và cấu hình provider.

### 2.2 Topic

Topic dùng mô hình publish-subscribe. Publisher gửi một publication tới topic; các subscription phù hợp có thể nhận bản sao của publication đó.

Mỗi subscription có trạng thái nhận riêng. Hai ứng dụng khác nhau subscribe cùng topic bằng hai subscription độc lập thì mỗi subscription có thể nhận bản sao của message. Đây là điểm khác với nhiều consumer cùng đọc một queue.

### 2.3 Non-durable subscription

Non-durable subscription tồn tại trong thời gian consumer/subscription hoạt động. Khi consumer đóng, subscription bị hủy. Publication phát ra trong khoảng thời gian subscriber offline không được giữ lại cho subscription đó.

Dùng non-durable subscription khi ứng dụng chỉ cần nhận sự kiện trong lúc đang hoạt động và có thể bỏ lỡ sự kiện khi offline, hoặc khi ứng dụng có cơ chế đồng bộ trạng thái riêng sau khi reconnect.

### 2.4 Durable subscription

Durable subscription được broker ghi nhận như một subscription có danh tính ổn định. Khi consumer ngừng hoạt động, broker có thể giữ các message phù hợp để giao lại khi consumer đăng ký lại cùng durable subscription, tùy retention, expiration, quota và policy.

Durable subscription phù hợp khi subscriber cần nhận lại các publication đã phát trong thời gian tạm offline. Nó không có nghĩa message được giữ vô thời hạn hoặc được bảo đảm giao nếu broker hết dung lượng, message hết TTL hay subscription bị xóa.

## 3. clientID và subscription name

### 3.1 clientID là định danh client JMS

clientID là thuộc tính của JMS connection hoặc JMSContext. Nó thường được đặt trước khi connection được dùng để tạo consumer hoặc bắt đầu nhận message.

Đối với durable subscription không chia sẻ theo mô hình unshared, client identifier và subscription name kết hợp để nhận diện subscription. Vì vậy, ứng dụng cần giữ clientID ổn định qua các lần restart nếu muốn tiếp tục sử dụng đúng subscription đã tạo.

Một clientID đang được dùng bởi một connection khác thường không thể được một connection khác chiếm đồng thời. Quy tắc cụ thể và phạm vi uniqueness được provider thực thi; cần kiểm tra tài liệu broker đang dùng.

clientID không phải username, password hay danh tính người dùng cuối. Xác thực kết nối vẫn dùng credential hoặc cơ chế bảo mật của provider. Không dùng clientID làm cơ chế phân quyền.

### 3.2 subscription name là tên logic của subscription

Subscription name là tên do ứng dụng đặt cho durable subscription. Nó nên:

- Ổn định giữa các lần deploy nếu muốn tiếp tục subscription cũ.
- Có ý nghĩa theo mục đích nhận, ví dụ `orders-projection-v1`.
- Không bị thay đổi tùy tiện theo mỗi lần khởi động.
- Được quản lý như một phần của cấu hình triển khai.

Đổi subscription name thường có nghĩa tạo một durable subscription khác. Subscription cũ có thể vẫn tồn tại trên broker cùng backlog của nó cho tới khi được unsubscribe hoặc bị quản trị viên xóa theo chính sách broker.

### 3.3 Phân biệt ba tên

| Giá trị | Ý nghĩa | Ví dụ |
|---|---|---|
| Destination/topic name | Nơi publisher gửi publication | `orders.events` |
| clientID | Định danh JMS client/connection | `orders-projection-node-01` |
| Subscription name | Danh tính logic của durable subscription | `orders-projection-v1` |

Không dùng destination làm subscription name. Một topic có thể có nhiều durable subscription với mục đích và trạng thái nhận khác nhau.

## 4. Tạo durable subscription bằng JMS 2.0

JMS 2.0 cung cấp API `JMSContext` và `JMSConsumer`. Với durable topic consumer không chia sẻ, có thể tạo consumer bằng `createDurableConsumer`.

Ví dụ dưới đây minh họa lifecycle cơ bản. `ConnectionFactory` được cung cấp bởi JMS provider hoặc cấu hình Spring; ví dụ cần dependency API Jakarta Messaging và implementation broker tương ứng.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSConsumer;
import jakarta.jms.Message;
import jakarta.jms.Topic;

public class DurableTopicReceiver {

    public void receiveOne(ConnectionFactory connectionFactory) {
        try (JMSContext context = connectionFactory.createContext()) {
            // Đặt clientID trước khi tạo consumer hoặc bắt đầu nhận.
            context.setClientID("orders-projection-node-01");

            Topic topic = context.createTopic("orders.events");

            try (JMSConsumer consumer = context.createDurableConsumer(
                    topic,
                    "orders-projection-v1")) {

                context.start();

                Message message = consumer.receive(1_000);

                if (message == null) {
                    System.out.println("No message within timeout");
                    return;
                }

                System.out.println("Received a durable topic message");
            }
        }
    }
}
~~~

Luồng thực hiện:

1. Tạo JMSContext từ ConnectionFactory.
2. Đặt clientID trước khi tạo durable consumer.
3. Tạo hoặc kết nối lại durable subscription với topic và subscription name.
4. Bắt đầu nhận message.
5. Đóng consumer và context khi kết thúc thao tác.

Đóng consumer/context kết thúc consumer đang hoạt động. Với durable subscription, việc đóng consumer không đồng nghĩa xóa subscription trên broker. Subscription có thể tiếp tục tồn tại để nhận publication khi client offline.

Ví dụ dùng package `jakarta.jms`, phù hợp với Jakarta Messaging trong các thế hệ Spring hiện đại. Dự án Spring Framework 5 và JMS cũ có thể dùng package `javax.jms`; không trộn hai namespace trong cùng một ứng dụng.

## 5. Shared và unshared durable subscription

JMS 2.0 bổ sung shared subscription để nhiều consumer có thể cùng tiêu thụ một subscription.

### 5.1 Unshared durable subscription

Unshared durable subscription được thiết kế cho một consumer hoạt động tại một thời điểm đối với subscription đó. Nếu nhiều consumer cố mở đồng thời cùng một unshared durable subscription, provider có thể từ chối.

Đây là lựa chọn phù hợp khi một logical subscriber cần nhận toàn bộ publication theo một luồng duy nhất, và ứng dụng kiểm soát việc chỉ có một consumer hoạt động cho subscription đó.

### 5.2 Shared durable subscription

Shared durable subscription cho phép nhiều consumer cùng tham gia một durable subscription theo hỗ trợ của JMS 2.0 và provider. Trong nhóm consumer dùng chung subscription, mỗi message được phân phối cho một consumer phù hợp trong nhóm, thay vì broadcast bản sao tới tất cả consumer.

Điều này có thể dùng để mở rộng năng lực xử lý của một subscription. Tuy nhiên, cần kiểm tra provider hỗ trợ shared durable subscription, giới hạn clientID, selector, ordering và concurrency ra sao.

### 5.3 Không nhầm shared subscription với nhiều subscription riêng

Giả sử có ba instance:

- Nếu mỗi instance dùng một clientID/subscription identity riêng, chúng tạo các durable subscription riêng. Mỗi subscription có thể nhận một bản sao của mọi publication phù hợp.
- Nếu các instance cùng tham gia một shared durable subscription, chúng cạnh tranh nhận message trong cùng subscription; mỗi publication được phân phối cho một consumer trong nhóm.

Hai mô hình có mục tiêu khác nhau. Tạo subscription riêng cho từng replica không tự động tạo competing consumers; nó có thể khiến mọi replica xử lý cùng một sự kiện.

## 6. Cấu hình durable topic listener trong Spring JMS

Spring JMS cung cấp listener container để quản lý connection, session, consumer và lifecycle của listener. Với annotation-driven listener, có thể cấu hình một `DefaultJmsListenerContainerFactory` riêng cho topic durable subscription.

Ví dụ:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class DurableJmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setClientId("orders-projection-node-01");
        factory.setSubscriptionDurable(true);
        factory.setConcurrency("1");

        return factory;
    }
}
~~~

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    @JmsListener(
            destination = "orders.events",
            subscription = "orders-projection-v1",
            containerFactory = "durableTopicListenerFactory")
    public void handle(OrderEvent event) {
        // Gọi service nghiệp vụ để cập nhật projection.
    }
}
~~~

Ý nghĩa các thiết lập:

- `setPubSubDomain(true)` cấu hình listener container theo mô hình topic.
- `setClientId(...)` đặt client identifier dùng cho durable subscription.
- `setSubscriptionDurable(true)` yêu cầu durable subscription.
- `subscription` trong `@JmsListener` cung cấp tên subscription.
- `setConcurrency("1")` giữ một consumer cho unshared durable subscription trong ví dụ.

Đây là cấu hình minh họa cho một listener unshared durable. Mỗi listener container dùng clientID cần được quản lý để không tạo xung đột với một connection đang hoạt động khác. Không dùng cùng một clientID tùy tiện cho nhiều container độc lập.

Nếu cần shared durable subscription, hãy dùng cấu hình shared subscription được Spring và JMS provider hỗ trợ ở phiên bản đang dùng, rồi kiểm thử với broker thực tế. Không chỉ tăng concurrency mà bỏ qua semantics shared/unshared.

`OrderEvent` là DTO thuộc ứng dụng và cần được cấu hình message conversion phù hợp. Listener method chỉ nên gọi service nghiệp vụ; clientID và subscription lifecycle thuộc lớp hạ tầng.

## 7. Vòng đời consumer và durable subscription

Cần phân biệt vòng đời của consumer đang chạy với vòng đời của durable subscription được broker lưu.

### 7.1 Start

Khi listener container start, Spring tạo hoặc khởi động tài nguyên JMS cần thiết, thiết lập clientID theo cấu hình, tạo consumer và bắt đầu nhận message.

Với durable subscription, broker xác định subscription hiện có hoặc tạo mới nếu chưa có. Subscription name và client identity phải nhất quán để reconnect vào đúng subscription.

### 7.2 Stop

Khi container stop, consumer ngừng nhận message và tài nguyên tiêu thụ đang hoạt động được dừng theo lifecycle của container.

Đối với durable subscription, stop listener không đồng nghĩa xóa subscription. Broker có thể tiếp tục giữ publication cho subscription trong thời gian subscriber offline, theo policy và giới hạn của broker.

Điều này hữu ích khi bảo trì hoặc deploy lại ứng dụng: dừng consumer tạm thời nhưng giữ danh tính subscription để tiếp tục sau khi khởi động.

### 7.3 Close

Đóng JMSConsumer hoặc JMSContext giải phóng tài nguyên client. Với durable subscription, subscription vẫn có thể tồn tại trên broker sau khi consumer đóng.

Với non-durable subscription, đóng consumer sẽ kết thúc subscription tạm thời đó.

### 7.4 Unsubscribe

Unsubscribe là thao tác xóa durable subscription khỏi broker. Trong JMS 2.0, `JMSContext.unsubscribe(subscriptionName)` cung cấp API tương ứng; JMS API phiên bản cũ có `Session.unsubscribe(subscriptionName)`.

Chỉ unsubscribe khi ứng dụng thực sự muốn xóa subscription và backlog gắn với nó. Provider thường yêu cầu không còn consumer hoạt động trên subscription tại thời điểm unsubscribe.

Unsubscribe không phải bước cleanup thông thường mỗi lần ứng dụng shutdown. Nếu gọi unsubscribe khi chỉ muốn restart, ứng dụng có thể mất backlog mà broker đã giữ cho subscriber.

## 8. Message tồn đọng khi consumer offline

Khi durable subscriber offline, broker có thể giữ các publication phù hợp. Khi consumer kết nối lại cùng subscription, broker tiếp tục giao các message đang chờ theo policy.

Cần tính tới:

- **Message expiration / TTL:** message hết hạn có thể bị loại bỏ trước khi consumer quay lại.
- **Persistent delivery mode:** quyết định mức độ lưu trữ bền vững của message theo provider.
- **Broker quota:** backlog lớn có thể chạm giới hạn dung lượng.
- **Subscription selector:** chỉ các message phù hợp selector mới được giao cho subscription.
- **Acknowledgement:** message đã giao nhưng chưa được acknowledge có thể được redeliver theo session/acknowledgement semantics.
- **Dead-letter policy:** message không thể xử lý có thể được chuyển sang nơi khác theo cấu hình broker.
- **Unsubscribe:** xóa durable subscription có thể làm mất trạng thái backlog của subscription.

Durable subscription không tự bảo đảm mọi message luôn được giữ. Hãy kiểm tra delivery mode, TTL, persistence, quota, retention và redelivery policy của broker.

## 9. Triển khai nhiều instance và tránh xung đột clientID

clientID cần được quản lý như một định danh hạ tầng có phạm vi rõ ràng.

### 9.1 Một unshared durable subscriber

Nếu chỉ có một logical consumer cho subscription, dùng một clientID ổn định và bảo đảm không có hai connection đồng thời cùng chiếm clientID đó. Khi deploy rolling update, cần điều phối instance cũ dừng consumer trước khi instance mới kết nối với cùng identity nếu provider không cho phép takeover.

### 9.2 Mỗi instance có subscription riêng

Nếu mỗi instance dùng clientID riêng và subscription name riêng, mỗi instance có durable subscription riêng. Khi publisher phát một message tới topic, mọi subscription riêng phù hợp có thể nhận một bản sao. Điều này phù hợp khi mỗi instance đại diện cho một hệ thống subscriber độc lập, nhưng không phù hợp nếu mục tiêu chỉ là chia tải cùng một công việc.

### 9.3 Shared durable subscription

Nếu muốn nhiều consumer cùng xử lý một subscription, dùng shared durable subscription theo JMS 2.0 và khả năng broker. Các consumer tham gia cùng một logical subscription và cạnh tranh nhận message.

Cần xác minh:
- Provider hỗ trợ shared durable subscription.
- Cách provider xác định client identity và subscription name.
- Có giới hạn số consumer đồng thời hay không.
- Ordering được bảo đảm ở phạm vi nào.
- Selector và acknowledgement hoạt động thế nào khi có nhiều consumer.
- Spring listener container phiên bản đang dùng cấu hình shared subscription ra sao.

Không giả định tăng số replica hoặc tăng concurrency tự động tạo ra mô hình shared subscription đúng.

## 10. Selector và noLocal

Durable subscription có thể được giới hạn bằng message selector để chỉ nhận message có header/property thỏa điều kiện. Selector cần ổn định giữa các lần reconnect; thay đổi selector có thể bị provider từ chối nếu subscription hiện tại đã được tạo với selector khác, hoặc yêu cầu unsubscribe rồi tạo lại subscription theo quy tắc provider.

JMS durable consumer API cũng có tùy chọn `noLocal` để tránh nhận message do cùng connection/client phát ra trong các trường hợp được JMS hỗ trợ. Hãy hiểu rõ semantics của provider và connection identity trước khi bật.

Selector và noLocal là bộ lọc giao nhận. Chúng không thay thế authorization. Không dùng selector như cơ chế phân quyền tenant hoặc người dùng nếu server chưa xác minh dữ liệu định tuyến.

## 11. Xác nhận, redelivery và idempotency

Khi consumer nhận message, acknowledgement và transaction quyết định khi nào broker xem message đã được xử lý. Nếu consumer lỗi trước khi acknowledge hoặc transaction rollback, message có thể được giao lại.

Vì vậy, listener cần xử lý message lặp một cách an toàn:

- Dùng event ID hoặc business key ổn định để nhận diện message.
- Ghi nhận kết quả xử lý theo transaction phù hợp.
- Thiết kế service idempotent.
- Phân biệt lỗi tạm thời có thể retry với dữ liệu không hợp lệ cần chuyển dead-letter.
- Theo dõi redelivery count nếu provider cung cấp.
- Không coi durable subscription là bảo đảm exactly-once cho toàn bộ nghiệp vụ.

Durability giúp giữ message khi subscriber offline. Acknowledgement/transaction kiểm soát việc giao nhận. Idempotency bảo vệ tác dụng phụ khi message được xử lý lại. Đây là các lớp bảo đảm khác nhau.

## 12. Kiểm thử lifecycle

Nên có integration test với JMS provider thật hoặc Testcontainers phù hợp để kiểm tra semantics durable subscription.

Các tình huống quan trọng:

1. Tạo durable subscription lần đầu và nhận publication.
2. Dừng consumer nhưng giữ subscription; publish message khi consumer offline.
3. Khởi động lại với cùng clientID và subscription name; xác minh message còn hiệu lực được nhận lại.
4. Khởi động với clientID khác; xác minh provider tạo identity khác hoặc xử lý theo cấu hình dự kiến.
5. Thử hai connection cùng clientID và xác nhận hành vi xung đột của provider.
6. Thử shared durable subscription với nhiều consumer nếu hệ thống dùng chế độ này.
7. Đóng consumer và kiểm tra durable subscription vẫn tồn tại.
8. Unsubscribe khi không có consumer hoạt động và xác minh subscription được xóa.
9. Thử message hết TTL, selector và redelivery.
10. Kiểm tra shutdown/restart không vô tình unsubscribe.

Unit test cho service nghiệp vụ không cần broker. Nhưng lifecycle, durable identity, shared subscription và backlog là hành vi của JMS provider, nên cần integration test trên broker mục tiêu.

## 13. Lỗi thường gặp

- **Nhầm clientID với subscription name:** một giá trị nhận diện client connection, giá trị kia đặt tên durable subscription.
- **Nhầm subscription name với topic name:** một topic có thể có nhiều subscription.
- **Thay clientID hoặc subscription name sau mỗi lần restart:** có thể tạo subscription mới và để lại subscription cũ cùng backlog.
- **Dùng cùng clientID cho nhiều connection đồng thời:** provider có thể từ chối kết nối.
- **Dùng nhiều subscription riêng để chia tải:** mỗi subscription có thể nhận bản sao của cùng publication, khiến mọi instance xử lý cùng event.
- **Nhầm shared durable với broadcast:** shared subscription phân phối message giữa các consumer; nó không gửi mỗi message tới mọi consumer trong nhóm.
- **Cho rằng stop/close xóa durable subscription:** subscription thường vẫn tồn tại cho tới khi unsubscribe hoặc bị quản trị viên xóa.
- **Unsubscribe khi chỉ muốn restart:** có thể xóa subscription và backlog.
- **Cho rằng durable giữ message vô thời hạn:** TTL, quota, persistence và broker policy vẫn có hiệu lực.
- **Tăng concurrency cho unshared durable:** có thể xung đột với quy tắc chỉ một consumer hoạt động trên subscription.
- **Không idempotent:** redelivery có thể tạo tác dụng phụ lặp.
- **Không kiểm thử trên broker thực tế:** semantics shared subscription và clientID có thể khác giữa provider.

## 14. Checklist vận hành

Trước khi triển khai durable JMS listener, hãy xác nhận:

- Destination là queue hay topic?
- Consumer cần non-durable, unshared durable hay shared durable?
- clientID có ổn định và không bị dùng đồng thời bởi connection khác không?
- Subscription name có ổn định và có versioning rõ ràng không?
- Spring listener container đã cấu hình pub-sub domain và durable subscription đúng chưa?
- Concurrency có tương thích với shared/unshared mode không?
- Stop và close có giữ subscription khi cần không?
- Unsubscribe chỉ được thực hiện khi muốn xóa subscription thực sự không?
- TTL, persistence, quota, selector và dead-letter policy đã được kiểm tra chưa?
- Listener có idempotent và xử lý redelivery an toàn không?
- Rolling deployment có điều phối clientID để tránh xung đột không?
- Integration test đã xác minh offline backlog, reconnect, shared mode và unsubscribe trên broker mục tiêu chưa?

Khi quản lý đúng clientID, subscription name và lifecycle, ứng dụng Spring JMS có thể duy trì trạng thái nhận message qua các lần restart, tránh tạo subscription rác và mở rộng consumer theo đúng semantics của provider.