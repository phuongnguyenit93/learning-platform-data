# Cấu hình selector, concurrency và subscription với @JmsListener trong Spring JMS

## 1. Mục tiêu bài học

`@JmsListener` cho phép Spring Framework đăng ký một method Java để **nhận và xử lý JMS message bất đồng bộ**. Tuy nhiên, việc method đã có `@JmsListener(destination = "...")` mới chỉ giải quyết một phần nhỏ của thiết kế consumer. Để chạy đúng trên broker thật, ta còn phải trả lời ba câu hỏi:

1. **Selector:** Consumer được nhận những message nào trong destination?
2. **Concurrency:** Tại một thời điểm có bao nhiêu JMS consumer/session cùng nhận message cho listener này?
3. **Subscription:** Nếu destination là Topic, application đang sở hữu subscription nào, có giữ backlog khi offline không, và nhiều instance có cùng chia một subscription hay mỗi instance nhận bản sao riêng?

Ba lựa chọn này tương tác trực tiếp. Ví dụ:
- Một Queue có hai nhóm worker dùng selector `region = 'EU'` và `region = 'APAC'`.
- Worker EU dùng `concurrency = "2-4"` để xử lý song song, còn worker APAC chỉ cần `"1-1"`.
- Một Topic phát event `order.paid`; Billing và Notification phải nhận **hai bản sao độc lập**, nhưng ba replica của Billing phải **chia tải trong cùng một subscription**, không xử lý một event ba lần.
- Billing phải giữ message khi không có replica nào online: cần **durable subscription** được nhận diện ổn định qua các lần deploy.

Bài học thuộc phần **@JmsListener** của Spring Framework – JMS. Các ví dụ sử dụng Java 17+, Spring Framework 6.x, Spring Boot 3.x và `jakarta.jms.*`. Khi gặp vendor khác Artemis, cần kiểm tra đặc tính của broker/client và triển khai trên chính môi trường đó.

### Sau bài học bạn có thể

- Đọc đúng ý nghĩa các thuộc tính `id`, `destination`, `containerFactory`, `selector`, `concurrency` và `subscription`.
- Viết selector hợp lệ cho JMS headers/message properties, hiểu NULL và kiểu giá trị.
- Chọn concurrency theo Queue/Topic, thông lượng, khả năng thread-safe và độ quan trọng của ordering.
- Phân biệt bốn subscription: non-durable/unshared, non-durable/shared, durable/unshared, durable/shared.
- Cấu hình `DefaultJmsListenerContainerFactory` riêng cho Queue và Topic; hiểu `pubSubDomain`, `subscriptionDurable`, `subscriptionShared` và `clientId`.
- Chạy demo Queue với hai listener selector khác nhau, kiểm tra message không khớp vẫn nằm trong Queue.
- Thiết kế migration, monitoring, retry/transaction và scale mà không tự tạo subscription trùng hoặc mất backlog.

## 2. Ba trục cấu hình là ba vấn đề khác nhau

~~~text
                           JMS broker
                              |
             +----------------+----------------+
             |                                 |
         Queue orders.jobs                Topic sales.events
             |                                 |
       selector trên consumer             selector trên subscription
             |                                 |
       concurrency = 2-4                 durable? shared?
             |                                 |
       N consumers cùng Queue           subscription billing
       cạnh tranh lấy job               subscription notification
                                               |
                                    Billing: có thể shared 3 replicas
                                    Notification: subscription riêng
~~~

| Trục | Câu hỏi | Thường được cấu hình ở đâu? | Không tự giải quyết |
|---|---|---|---|
| **Selector** | Message có được chọn không? | `@JmsListener(selector=...)` hoặc endpoint/container. | Không parse JSON body, không phân quyền, không ACK/retry. |
| **Concurrency** | Bao nhiêu consumer/session chạy đồng thời? | `@JmsListener(concurrency=...)`; `DefaultJmsListenerContainerFactory.setConcurrency(...)`. | Không biến Queue thành Topic; không tạo exactly-once. |
| **Subscription** | Nhận bản sao Topic nào, có durable/shared không? | `@JmsListener(subscription=...)` và factory `setPubSubDomain`/`setSubscriptionDurable`/`setSubscriptionShared`/`setClientId`. | Không bảo đảm một consumer xử lý đúng giờ, không tự di chuyển backlog khi đổi tên. |

**Một lỗi cấu hình ở trục subscription có thể khiến concurrency hoạt động ngược ý định**. Nếu mỗi replica Topic tạo subscription độc lập, mọi replica có thể nhận cùng event. Trong khi đó, Queue có nhiều consumer cạnh tranh thì mỗi delivery thông thường chỉ đến một consumer, dù redelivery vẫn có thể làm cùng business event được xử lý lại.

## 3. Thuộc tính quan trọng của @JmsListener

~~~java
@JmsListener(
    id = "euInvoiceWorker",
    destination = "orders.jobs",
    containerFactory = "queueListenerFactory",
    selector = "eventType = 'INVOICE' AND region = 'EU'",
    concurrency = "2-4"
)
public void processInvoice(String payload) {
    // Business handler
}
~~~

Đây là mảnh code trong một `@Component` có cấu hình Spring JMS phù hợp.

| Thuộc tính | Mục đích | Giá trị/giới hạn |
|---|---|---|
| `destination` | Tên Queue/Topic cần nhận, resolve qua `DestinationResolver`. | Bắt buộc; một chuỗi tên không tự xác định Queue hay Topic. |
| `id` | ID duy nhất của listener container trong registry Spring. | Nên đặt ổn định để quan sát, stop/start và chẩn đoán. |
| `containerFactory` | Bean `JmsListenerContainerFactory` xây container cho listener. | Nếu bỏ trống, mặc định tìm bean `jmsListenerContainerFactory` hoặc default được chỉ định. |
| `selector` | Biểu thức lọc message theo cú pháp JMS selector. | Chỉ TRUE mới match; không đọc body JSON. |
| `concurrency` | Giới hạn consumer/session cho endpoint cụ thể. | Ghi đè concurrency của factory; hỗ trợ dạng `"2-4"` hoặc `"4"`. |
| `subscription` | Tên subscription khi listener chạy trên Topic có subscription được đặt tên. | Không phải tên Topic, không phải tên Queue. Nên đặt tường minh cho durable/shared. |

**Không có** các thuộc tính `pubSubDomain`, `subscriptionShared` hoặc `subscriptionDurable` trực tiếp trên `@JmsListener`. Những lựa chọn đó đến từ listener container factory. Việc chỉ thêm `subscription="billing"` mà không bật Topic/durable/shared thích hợp không tạo ra mô hình mong muốn.

`@JmsListener` có thể dùng nhiều lần trên một method nếu cần nhiều endpoint. Mỗi annotation tạo listener endpoint riêng; việc một method được reuse không có nghĩa các endpoint cùng chung subscription hoặc transaction.

### Ưu tiên cấu hình

- Factory đặt default chung cho nhiều listener, ví dụ `setConcurrency("1-3")`, `setSessionTransacted(true)`.
- Annotation `@JmsListener(concurrency="2-4")` **ghi đè concurrency** cho endpoint đó.
- Annotation `containerFactory="topicSharedFactory"` chọn factory Topic thay vì dùng factory Queue mặc định.
- Annotation `subscription="billing-ledger-v1"` đặt **tên** subscription; factory vẫn quyết định shared/durable/Topic.
- Có thể dùng placeholder cấu hình từ `application.yml`. Giá trị cuối cùng phải được resolve trước khi container tạo JMS consumer.

## 4. Selector trong @JmsListener

Selector là **biểu thức điều kiện**, không phải lệnh SQL có `SELECT` hay truy vấn JSON. Provider đánh giá biểu thức trên JMS message headers hợp lệ và properties.

### 4.1. Ví dụ hợp lệ

~~~sql
eventType = 'INVOICE'
region = 'EU' AND amount >= 100
eventType IN ('INVOICE', 'REFUND')
amount BETWEEN 100 AND 500
priorityLevel >= 7 AND ready = TRUE
JMSCorrelationID = 'request-42'
region IS NULL OR region <> 'EU'
~~~

Dùng nháy đơn cho String; literal String phân biệt chữ hoa/thường; tên property cũng phân biệt chữ hoa/thường. `setStringProperty("amount","100")` không tương đương `setIntProperty("amount",100)` khi selector thực hiện phép so sánh numeric.

Spring không tự chuyển JSON body thành JMS properties. Producer phải gắn property cần lọc khi gửi:

~~~java
jmsTemplate.convertAndSend("orders.jobs", "issue-invoice-42", m -> {
    m.setStringProperty("eventType", "INVOICE");
    m.setStringProperty("region", "EU");
    m.setIntProperty("amount", 200);
    m.setBooleanProperty("ready", true);
    m.setJMSCorrelationID("request-42");
    return m;
});
~~~

Đoạn code là mảnh code trong service có `JmsTemplate` được inject. Các property nằm trên `jakarta.jms.Message`; nếu chúng chỉ có trong payload JSON, selector `region = 'EU'` sẽ không thấy.

### 4.2. Header chuẩn có thể dùng

Theo Jakarta Messaging 3.1, sáu header JMS được tham chiếu trực tiếp trong selector chuẩn là:

| Header | Loại trong selector | Ví dụ |
|---|---|---|
| `JMSDeliveryMode` | String: `'PERSISTENT'` hoặc `'NON_PERSISTENT'` | `JMSDeliveryMode = 'PERSISTENT'` |
| `JMSPriority` | Số nguyên 0..9 | `JMSPriority >= 7` |
| `JMSMessageID` | String | `JMSMessageID = 'ID:message-42'` |
| `JMSTimestamp` | Số epoch milliseconds | `JMSTimestamp > 1700000000000` |
| `JMSCorrelationID` | String | `JMSCorrelationID = 'request-42'` |
| `JMSType` | String | `JMSType = 'invoice.v1'` |

Các tên `JMSReplyTo`, `JMSDestination`, `JMSExpiration`, `JMSDeliveryTime` và `JMSRedelivered` **không thuộc danh sách header selector chuẩn**, dù API `Message` có thể đọc chúng. `JMSXDeliveryCount` là property được provider đặt lúc nhận; hiệu ứng chọn theo property loại này không được định nghĩa portable, vì vậy không dùng selector `JMSXDeliveryCount > 3` để thay redelivery/DLQ policy.

### 4.3. NULL, UNKNOWN và message không khớp

Khi message không có `region`, điều kiện `region = 'EU'` cho kết quả UNKNOWN. `NOT UNKNOWN` vẫn UNKNOWN; chỉ TRUE được giao.

| Selector | Message thiếu `region` |
|---|---|
| `region = 'EU'` | Không khớp |
| `region <> 'EU'` | Không khớp |
| `region IS NULL` | Khớp |
| `region = 'EU' OR region IS NULL` | Khớp |

Nếu producer đổi tên property hoặc đổi kiểu String thành số, consumer có thể **âm thầm không nhận message** mà không có exception trong listener. Cần giám sát Queue depth, tuổi message và selector/version.

### 4.4. Selector và bảo mật

**Không sử dụng selector như ranh giới bảo mật.** Producer có quyền gửi message có thể đặt `tenantId` hoặc `region` tùy ý. ACL broker, namespace isolation và xác minh quyền nghiệp vụ phải độc lập với việc selector match.

Đừng nối dữ liệu input không kiểm tra vào selector động. JMS selector không có bind parameter giống prepared statement JDBC; ưu tiên biểu thức cố định hoặc whitelist/escaping đúng.

## 5. Concurrency thực sự điều khiển cái gì?

Với `DefaultMessageListenerContainer`, concurrency tương ứng với **số consumer/session** mà container có thể giữ để gọi method listener. Nhiều consumer có thể xử lý message đồng thời trên **các thread khác nhau**, nhưng một JMS `Session` vẫn có quy tắc sử dụng tuần tự riêng.

Ví dụ:

~~~java
@JmsListener(
    destination = "orders.jobs",
    containerFactory = "queueListenerFactory",
    concurrency = "2-4"
)
public void handle(String payload) {
    // Một invocation xử lý một message.
}
~~~

Với container hỗ trợ scale, `"2-4"` mô tả **ít nhất 2 và tối đa 4** consumer; số thực tế phụ thuộc tải và cơ chế scheduling. Mỗi lời gọi method có thể chạy song song, do đó field mutable dùng chung trong class listener phải an toàn đa luồng.

### 5.1. Phân biệt "4", "2-4" và "4-4"

| Chuỗi | Ý nghĩa trên `DefaultMessageListenerContainer` |
|---|---|
| `"1-1"` | Cố định một consumer. |
| `"4"` | Trần concurrency là 4; lower bound mặc định là 1. Không đồng nghĩa cố định 4. |
| `"2-4"` | Core/concurrent consumer tối thiểu 2, có thể scale tới 4. |
| `"4-4"` | Cố định 4 consumer. |
| `""` (không khai báo) | Kế thừa cấu hình từ listener factory. |

Các giới hạn này là **ý định cấu hình**, không phải cam kết mọi lúc đạt đúng số thread như bảng. Provider quota, pool, thread scheduling, số kết nối, recovery và broker load có thể thay đổi số active consumers thực tế.

### 5.2. Scale theo bản sao triển khai

Nếu một listener có `concurrency="2-4"` và triển khai **3 replica**, tổng số consumer của endpoint đó trong cụm có thể tăng tới:

~~~text
maxConsumersCluster ≈ 3 replicas × 4 consumers/replica = 12 consumers
~~~

Đây là **ngân sách lý thuyết** trước khi tính session/connection pool, quyền broker, task executor và các listener khác. Không nhầm "concurrency=4" với bốn job trên toàn cluster. Nếu đồng thời có nhiều endpoint và replica, tổng tiêu thụ tài nguyên có thể tăng rất nhanh.

### 5.3. Tăng concurrency có làm nhanh hơn không?

Có thể, với Queue có nhiều message độc lập và handler làm I/O. Nhưng không bảo đảm:
- Broker prefetch nhiều message cho một consumer, khiến consumer khác bị thiếu việc.
- DB pool và downstream API trở thành bottleneck.
- Message group/order/key affinity giới hạn khả năng phân phối song song.
- Consumer tranh lock hoặc xử lý cùng một business entity.
- Thêm thread làm tăng redelivery khi container restart, hoặc làm mất tính tuần tự.

Nên tune dựa trên **throughput, p95/p99 handler latency, Queue depth, consumer utilization, DB pool, prefetch** và memory. Không chỉ nhìn số thread.

### 5.4. Concurrency và ordering

Một Queue có một consumer, không priority hoặc xử lý đặc biệt, thường dễ duy trì thứ tự hơn. Khi có nhiều consumer, `@JmsListener(concurrency="4-4")` không bảo đảm **thứ tự hoàn tất nghiệp vụ** giống thứ tự gửi. Hai message A, B có thể được giao theo thứ tự nhưng B hoàn thành trước vì A gọi database chậm.

Nếu cần thứ tự theo `orderId`, cân nhắc:
- Giữ concurrency thấp ở nhóm dữ liệu cần tuần tự.
- Message grouping hoặc partitioning theo key nếu broker hỗ trợ, kiểm chứng bằng integration test.
- Sequence number và idempotency ở tầng business.
- Không dùng sleep hoặc synchronized toàn bộ handler để sửa một cách ngẫu nhiên.

## 6. Queue và Topic: concurrency không mang cùng ý nghĩa

| Khía cạnh | Queue | Topic non-shared | Topic shared subscription |
|---|---|---|---|
| Một message đến bao nhiêu consumer? | Thường **một** consumer được chọn từ nhóm đủ điều kiện. | Mỗi subscription riêng có thể nhận **một bản sao**. | Một message được giao cho **một consumer trong cùng subscription**. |
| Scale consumer | Tăng concurrency thường chia tải trên Queue. | Tăng consumer/subscription độc lập có thể dẫn tới **bản sao trùng** ở mỗi consumer. | Nhiều consumer chia tải trong cùng subscription. |
| Selector | Chọn message cho consumer; message không match có thể còn trong Queue. | Chọn message vào subscription khi publish. | Cùng selector áp dụng cho subscription được share. |
| Backlog khi offline | Queue thường giữ message theo retention/expiry. | Không nếu subscription non-durable đã bị hủy. | Có nếu subscription **durable** và broker policy cho phép. |
| Tình huống điển hình | Job/command cần một worker xử lý. | Fan-out đến các dịch vụ độc lập. | Fan-out giữa các service, sau đó load-balance nhiều replica của từng service. |

**Không bật `pubSubDomain=true` rồi tăng `concurrency="5-10"` một cách máy móc.** Với Topic non-shared, các consumer có thể là các subscription độc lập, dẫn tới số lần handler được gọi nhiều hơn dự kiến. Với unshared durable subscription, nhiều consumer đồng thời trên cùng subscription thường **không hợp lệ** và có thể bị broker từ chối. Chỉ scale Topic theo subscription shared khi đúng contract/provider.

## 7. Bốn kiểu subscription Topic cần phân biệt

Jakarta Messaging 2.0+ (trong Spring 6 là Jakarta Messaging 3.x) phân biệt:

| Kiểu | Durable? | Shared? | Số consumer đồng thời trong cùng subscription | Khi tất cả consumer offline |
|---|---|---|---|---|
| **Unshared non-durable** | Không | Không | 1 | Subscription kết thúc, không giữ bản tin mới. |
| **Shared non-durable** | Không | Có | Nhiều | Subscription chấm dứt khi consumer cuối đóng; không giữ backlog tương lai. |
| **Unshared durable** | Có | Không | 1 | Subscription tồn tại, message phù hợp có thể được giữ lại đến khi ACK/expire. |
| **Shared durable** | Có | Có | Nhiều | Subscription vẫn tồn tại và giữ backlog phù hợp khi không có consumer. |

*Durable* nói về **vòng đời subscription**, *shared* nói về **khả năng nhiều consumer cùng tiêu thụ một subscription**. Hai thuộc tính độc lập; shared không tự động durable và durable không tự động shared.

### 7.1. Topic non-durable/unshared

Mặc định nếu chỉ đặt `setPubSubDomain(true)` và không bật shared/durable, mỗi consumer có thể sở hữu một subscription non-durable riêng. Nếu bạn triển khai ba replica, mỗi replica có thể nhận một bản sao message. Điều này phù hợp trong một số trường hợp fan-out theo instance nhưng **không** phù hợp nếu chỉ cần một Billing event xử lý một lần cho cả nhóm replica.

Consumer đóng và subscription non-durable không còn tồn tại thì message publish trong thời gian đó không được tích lũy để nhận bù sau. Persistent message trên Topic không tự biến subscription non-durable thành durable.

### 7.2. Topic shared non-durable

Một subscription có **tên** và có thể có nhiều consumer cùng chia message. Trong suốt lúc có ít nhất một consumer active, một message phù hợp chỉ được giao cho một consumer thuộc cùng subscription (trừ redelivery). Khi consumer cuối đóng, subscription bị xóa và không giữ backlog của những lần publish sau đó.

Đây là lựa chọn khi muốn chia tải trên Topic nhưng chấp nhận bỏ qua message lúc toàn bộ ứng dụng offline. Không có chuyện shared subscription tự đảm bảo exactly-once ở tầng database.

### 7.3. Topic durable/unshared

Subscription có identity gồm **subscription name + client identifier**. Jakarta Messaging yêu cầu client ID cho **unshared durable**. Chỉ một consumer active được phép dùng subscription này tại một thời điểm; cùng một client ID không được tùy tiện dùng đồng thời trên nhiều connection/instance.

Dùng khi consumer cần giữ message gửi trong lúc offline nhưng chỉ cần một consumer active. **Concurrency="1-1"** là lựa chọn an toàn; scale bằng failover tuần tự/active-passive, không phải cho năm replica cùng dùng client ID rồi hy vọng broker tự chia tải.

### 7.4. Topic shared durable

Subscription có tên ổn định, nhiều consumer chia tải trong một nhóm, và broker tiếp tục giữ message phù hợp khi nhóm offline. Theo Jakarta Messaging, **client ID có thể được bỏ qua** với shared durable subscription; nếu có đặt, các consumer tham gia cùng subscription phải sử dụng identity phù hợp. Tránh cấu hình client ID cứng giống nhau trên nhiều connection độc lập khiến provider báo trùng identity.

Đây thường là lựa chọn thích hợp cho nhóm service có nhiều replica cần mỗi event đến **một replica trong nhóm** và cần giữ backlog khi nhóm offline. Những nhóm nghiệp vụ khác phải dùng **subscription name khác nhau** để mỗi nhóm có bản sao riêng.

~~~text
Topic: sales.order.paid
   |
   +-- shared durable subscription "billing-ledger-v1"
   |       +-- billing replica A (consumer 1)
   |       +-- billing replica B (consumer 2)
   |       +-- billing replica C (consumer 3)
   |       -> mỗi delivery chỉ vào một consumer của nhóm Billing
   |
   +-- shared durable subscription "notification-mail-v1"
           +-- notification replica A
           +-- notification replica B
           -> mỗi delivery chỉ vào một consumer của nhóm Notification

Cùng một event có thể có hai bản sao:
một cho Billing và một cho Notification.
~~~

**Nhận diện subscription sai có thể làm mất backlog.** Đổi tên, thay selector/destination hoặc chuyển giữa shared và unshared cần kế hoạch migration. Ở một số trường hợp provider coi đây là subscription mới hoặc từ chối vì identity hiện tại không tương thích; không phải thao tác cập nhật chuỗi an toàn.

## 8. Cấu hình DefaultJmsListenerContainerFactory đúng loại đích

Container factory là nơi quyết định ngữ nghĩa của endpoint. Một ứng dụng có thể có **nhiều factory**, ví dụ Queue command và Topic event.

### 8.1. Factory cho Queue có session transaction

`src/main/java/example/jms/QueueConsumerConfiguration.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class QueueConsumerConfiguration {

    @Bean("queueListenerFactory")
    DefaultJmsListenerContainerFactory queueListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-4");
        factory.setReceiveTimeout(1_000L);
        return factory;
    }
}
~~~

Giải thích:
- `setPubSubDomain(false)` nghĩa là khi resolve tên động, listener làm việc với **Queue**.
- `setSessionTransacted(true)` tạo JMS local transaction cho việc nhận/xử lý message. Exception thoát khỏi handler thường khiến session rollback; broker quyết định redelivery policy.
- `setConcurrency("1-4")` là cấu hình chung; `@JmsListener(concurrency="2-2")` có thể ghi đè cho một endpoint.
- `setReceiveTimeout(1_000L)` điều khiển receive polling của container, **khác `JmsTemplate.setReceiveTimeout`** dành cho receive đồng bộ.
- Factory không định nghĩa một Queue vật lý cụ thể: tên đến từ `@JmsListener(destination=...)`.

### 8.2. Factory cho Topic shared durable

`src/main/java/example/jms/SharedDurableTopicConfiguration.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class SharedDurableTopicConfiguration {

    @Bean("sharedDurableTopicFactory")
    DefaultJmsListenerContainerFactory sharedDurableTopicFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);          // Topic, không phải Queue
        factory.setSubscriptionDurable(true);   // Giữ backlog khi offline
        factory.setSubscriptionShared(true);    // Nhiều consumer cùng sub
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-2");
        return factory;
    }
}
~~~

Đây là class cấu hình đầy đủ khi đặt trong project có JMS infrastructure. Bạn cần **một broker/client hỗ trợ shared durable subscription** (Jakarta Messaging 2.0+ semantics). Không gọi `setClientId` trong ví dụ vì shared durable có thể không cần client ID theo chuẩn; khi provider yêu cầu cấu hình bổ sung, hãy làm theo compatibility matrix của chính provider, không gán cùng một client ID cho nhiều replica một cách ngẫu nhiên.

Listener đi kèm:

`src/main/java/example/jms/BillingTopicListener.java`:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BillingTopicListener {

    @JmsListener(
            id = "billingPaidEvents",
            destination = "sales.order.paid",
            containerFactory = "sharedDurableTopicFactory",
            subscription = "billing-ledger-v1",
            selector = "eventType = 'ORDER_PAID'",
            concurrency = "2-2")
    public void onOrderPaid(String json) {
        // Ví dụ minh họa điểm tiếp nhận; trong dự án thật,
        // gọi một service idempotent để cập nhật ledger.
        System.out.println("Billing event: " + json);
    }
}
~~~

Cùng một binary ứng dụng trên nhiều replica dùng **cùng topic, subscription name, selector và shared-durable policy** để gia nhập cùng nhóm. Mỗi subscription name khác là **một nhóm nhận bản sao**. Nếu triển khai vào broker thật, provision Topic/ACL/retention và kiểm tra cấu hình routing của provider.

**Không chạy đồng thời** lớp Billing Topic listener này với demo Queue ở phần 11 chỉ bằng cách copy file mà chưa provision Topic/định tuyến tương ứng. Đây là ví dụ Topic riêng, độc lập với lab Queue.

### 8.3. Factory cho unshared durable Topic

Nếu yêu cầu **một active consumer** và lưu backlog khi offline, cấu hình khác:

~~~java
@Bean("unsharedDurableTopicFactory")
DefaultJmsListenerContainerFactory unsharedDurableTopicFactory(
        ConnectionFactory cf) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setSubscriptionShared(false);
    factory.setClientId("billing-exclusive-client");
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-1");
    return factory;
}
~~~

Mảnh code này nằm trong `@Configuration` đã import `@Bean`, `ConnectionFactory` và `DefaultJmsListenerContainerFactory`. Trên endpoint Topic phải đặt một `subscription` ổn định, chẳng hạn `"billing-exclusive-v1"`. Client ID bắt buộc cho unshared durable và **không được** bị dùng đồng thời trên connection của replica khác. Nếu service cần active-active replicas, chọn shared durable được broker hỗ trợ thay vì dùng một client ID unshared chung trên mọi replica.

### 8.4. Factory khác nhau cho những contract khác nhau

Không bắt buộc mọi listener dùng một factory. Phân tách:
- `queueListenerFactory`: Queue, có thể scale concurrency.
- `sharedDurableTopicFactory`: Topic, durable/shared, có thể nhiều consumer cùng subscription.
- `unsharedDurableTopicFactory`: Topic, durable/unshared, concurrency 1 và client identity riêng.

Điều này an toàn hơn việc sửa `factory.setPubSubDomain(...)` trên một bean đang chạy cho từng listener. Container factory tạo ra container; hãy quyết định semantics trước khi endpoint được đăng ký.

## 9. Cấu hình theo môi trường với placeholders

Hard-code production Queue/Topic và selector thường gây lỗi khi deploy. Có thể tách thành:

~~~yaml
app:
  jms:
    queue:
      orders: "dev.orders.jobs"
      eu-selector: "eventType = 'INVOICE' AND region = 'EU'"
    topic:
      paid-events: "dev.sales.order.paid"
      billing-subscription: "billing-ledger-v1"
~~~

Annotation tham chiếu:

~~~java
@JmsListener(
    id = "euInvoiceWorker",
    destination = "${app.jms.queue.orders}",
    selector = "${app.jms.queue.eu-selector}",
    containerFactory = "queueListenerFactory",
    concurrency = "2-4")
public void handle(String payload) {
    // Code nghiệp vụ
}
~~~

Đây là mảnh method minh họa thuộc một `@Component`. Spring hỗ trợ property placeholders trong annotation attributes. Với một Topic subscription **durable**, tên subscription thường phải **ổn định qua deploy** trong cùng nhóm và broker namespace; đừng tự nối pod ID, thời điểm triển khai hoặc một giá trị ngẫu nhiên vào `subscription`.

Thay selector của durable subscription có thể khiến provider coi hợp đồng đã thay đổi, yêu cầu unsubscribe/recreate hoặc tạo subscription khác. Đừng nghĩ reload YAML đang chạy sẽ tự động cập nhật mọi JMS consumer và giữ backlog cũ. Nếu cần chuyển selector, tổ chức migration và kiểm thử với broker.

## 10. Concurrency và subscription khi triển khai nhiều replica

Giả sử có 3 bản sao ứng dụng:

| Cấu hình | Ý nghĩa khi scale |
|---|---|
| Queue listener `"2-4"` | Tối đa khoảng 12 consumers cho **một endpoint** trong cluster; cùng cạnh tranh Queue. |
| Topic non-durable/unshared, mỗi replica một consumer | Mỗi replica có thể nhận **bản sao** message riêng; không phải load-balanced group. |
| Topic durable/unshared, cùng client ID/subscription name | Có xung đột nếu nhiều consumer/connection active; không được scale theo cách này. |
| Topic shared non-durable, cùng subscription identity | Nhiều consumer chia tải khi nhóm đang online; offline hoàn toàn không giữ message mới. |
| Topic shared durable, cùng subscription identity | Nhiều consumer chia tải; giữ message phù hợp trong lúc nhóm offline. |

**Không đánh đồng thread pool và số consumers.** Một container có thể quản lý số JMS Sessions/consumers và dùng task executor để chạy polling/dispatch; tăng thread pool của ứng dụng không tự tạo thêm JMS consumer nếu concurrency giới hạn thấp. Ngược lại, tăng concurrency nhưng broker/DB pool không đủ capacity cũng không tạo thêm thông lượng.

### 10.1. Listener object phải thread-safe

Các lời `@JmsListener` của cùng bean singleton có thể chạy đồng thời. Sai:

~~~java
private int processedCount;

@JmsListener(destination = "orders.jobs", concurrency = "4-4")
public void process(String payload) {
    processedCount++; // Race condition: phép ++ không atomic.
}
~~~

Đây là mảnh class. Cách an toàn hơn là xử lý thông tin per-message bằng local variables, gọi service stateless/idempotent, hoặc dùng `AtomicLong` khi chỉ cần metric đơn giản:

~~~java
private final java.util.concurrent.atomic.AtomicLong processedCount =
        new java.util.concurrent.atomic.AtomicLong();

@JmsListener(destination = "orders.jobs", concurrency = "4-4")
public void process(String payload) {
    processedCount.incrementAndGet();
}
~~~

Dù vậy, `AtomicLong` không thay thế transaction/database uniqueness cho tính chính xác nghiệp vụ khi cùng event được redeliver. Đếm “số lần callback” và “số business event xử lý thành công duy nhất” là hai metric khác nhau.

### 10.2. Quy tắc kích thước

Ước lượng ban đầu:
- `replicaCount × maxConcurrentConsumersPerReplica` là trần số JMS consumer của **một endpoint**.
- Nếu có N listener riêng, tổng consumer có thể là tổng các trần qua từng endpoint; các listener khác nhau có Queue/Topic/subscription semantics khác nhau.
- Broker prefetch, DB pool, broker connection limit, thread executor và CPU phải được kiểm tra cùng nhau.
- Không tăng vô hạn vì Queue depth nhất thời; cần dự trù rate, transaction duration và downstream quotas.

## 11. Lab chạy được: Queue với selector và concurrency khác nhau

Lab sử dụng **Java 17 + Spring Boot 3.5.16 + Artemis embedded**. Hai `@JmsListener` cùng dùng Queue `demo.orders` nhưng mỗi endpoint có selector riêng:
- `euOrderListener`: nhận `kind='ORDER'` và `region='EU'`, với concurrency cố định `"2-2"`.
- `refundListener`: nhận `kind='REFUND'`, với concurrency cố định `"1-1"`.

Ứng dụng gửi **bốn message**; ba cái match hai listener, một message `region='US'` không match và vẫn nằm trong Queue cho một lần `receiveSelected` riêng. Một `CountDownLatch` và `ConcurrentHashMap.newKeySet()` dùng để chờ/xác minh mà **không phụ thuộc thứ tự chạy thread**.

Không có Topic listener trong project lab này; Topic shared durable được minh họa bằng code cấu hình riêng ở mục 8 để không đánh lừa người học về subscription identity, backlog và thời điểm tạo Topic.

### 11.1. Cấu trúc

~~~text
jms-listener-routing-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/RoutingLabApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-listener-routing-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Spring Boot dependency management quản lý phiên bản `spring-jms`/Jakarta JMS/Artemis phù hợp nhánh Boot. Phiên bản fixed để demo có thể tái lập; với production nên dùng nhánh Boot đang được hỗ trợ và sửa theo advisories mới. Cần JDK 17+ và một Gradle version tương thích với Spring Boot plugin.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.orders
      persistent: false
~~~

`persistent: false` chỉ để lab nhẹ, **không** chứng minh tính bền vững khi broker restart.

### 11.2. Một file Java hoàn chỉnh

`src/main/java/example/jms/RoutingLabApplication.java`:

~~~java
package example.jms;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class RoutingLabApplication {
    private static final String QUEUE = "demo.orders";

    public static void main(String[] args) {
        SpringApplication.run(RoutingLabApplication.class, args);
    }

    @Bean("queueRoutingFactory")
    DefaultJmsListenerContainerFactory queueRoutingFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    static final class Results {
        private final Set<String> entries =
                ConcurrentHashMap.newKeySet();
        private final CountDownLatch latch =
                new CountDownLatch(3);

        void record(String value) {
            if (entries.add(value)) {
                latch.countDown();
            }
        }

        List<String> sortedResults() {
            return entries.stream().sorted().toList();
        }

        void awaitThree() throws InterruptedException {
            if (!latch.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for three matching messages");
            }
        }
    }

    @Bean
    Results results() {
        return new Results();
    }

    @Bean
    RoutingListener routingListener(Results results) {
        return new RoutingListener(results);
    }

    static final class RoutingListener {
        private final Results results;

        RoutingListener(Results results) {
            this.results = results;
        }

        @JmsListener(
                id = "euOrderListener",
                destination = QUEUE,
                containerFactory = "queueRoutingFactory",
                selector = "kind = 'ORDER' AND region = 'EU'",
                concurrency = "2-2")
        public void onEuOrder(String payload) {
            results.record("EU_ORDER=" + payload);
        }

        @JmsListener(
                id = "refundListener",
                destination = QUEUE,
                containerFactory = "queueRoutingFactory",
                selector = "kind = 'REFUND'",
                concurrency = "1-1")
        public void onRefund(String payload) {
            results.record("REFUND=" + payload);
        }
    }

    @Bean
    ApplicationRunner runCases(JmsTemplate template, Results results) {
        return args -> {
            send(template, "eu-01", "ORDER", "EU");
            send(template, "eu-02", "ORDER", "EU");
            send(template, "refund-03", "REFUND", "EU");
            send(template, "order-us-04", "ORDER", "US");

            results.awaitThree();

            List<String> observed = results.sortedResults();
            List<String> expected = List.of(
                    "EU_ORDER=eu-01",
                    "EU_ORDER=eu-02",
                    "REFUND=refund-03");

            if (!observed.equals(expected)) {
                throw new IllegalStateException(
                        "Unexpected listener result: " + observed);
            }

            for (String entry : observed) {
                System.out.println(entry);
            }

            // Message ORDER/US không match hai listener trên.
            Message remaining = template.receiveSelected(
                    QUEUE, "kind = 'ORDER' AND region = 'US'");

            if (!(remaining instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "ORDER/US message was not retained in the Queue");
            }
            System.out.println("UNMATCHED=" + text.getText());
        };
    }

    private static void send(
            JmsTemplate template, String payload,
            String kind, String region) {

        template.convertAndSend(QUEUE, payload, message -> {
            message.setStringProperty("kind", kind);
            message.setStringProperty("region", region);
            return message;
        });
    }
}
~~~

### 11.3. Vì sao demo không dựa vào thứ tự bất đồng bộ?

`@JmsListener` chạy trên listener threads; hai consumer EU có thể nhận `eu-01` và `eu-02` song song. Cái nào xử lý xong trước không được bảo đảm. Vì vậy:
- `Results.entries` dùng concurrent set, không phải `HashSet` không thread-safe.
- `CountDownLatch(3)` đợi ba message hợp lệ được callback xử lý.
- `sortedResults()` sắp kết quả trước khi in.
- Message US vẫn ở Queue và được `receiveSelected` nhận sau đó; nó không bị hai listener khác lấy mất vì không match selector.

`Results.record` chỉ chứng minh callback đã được gọi và đặt vào bộ nhớ; nó **không phải** database commit nghiệp vụ, không thay cho outbox/idempotency. Demo đặt `setSessionTransacted(true)` để minh họa listener transaction, nhưng thực tế redelivery, max attempts và DLQ là cấu hình broker riêng.

### 11.4. Chạy và kiểm tra stdout

Từ thư mục `jms-listener-routing-lab`, với Gradle Wrapper đã có:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có Wrapper, với Gradle cài sẵn tương thích:

~~~bash
gradle bootRun
~~~

Sau log startup Spring Boot/Artemis, các dòng **do chương trình tự in** khi chạy thành công:

~~~text
EU_ORDER=eu-01
EU_ORDER=eu-02
REFUND=refund-03
UNMATCHED=order-us-04
~~~

Code có kiểm tra kết quả trước khi in. Việc in đã được sắp xếp, nên thứ tự stdout xác định theo code, **không có nghĩa broker bảo đảm hoàn tất message theo thứ tự producer gửi**.

Một môi trường bị nghẽn có thể hết 15 giây trước khi cả ba listener xử lý xong, khiến Runner ném exception; khi đó kiểm tra log Artemis, số listener consumers, cấu hình Queue và thread scheduling. Đây là timeout của bài lab, không phải hành vi JMS chuẩn.

### 11.5. Thí nghiệm điều chỉnh

1. Đổi selector EU thành `region = 'APAC'` nhưng giữ nguyên messages: hai order EU không còn match và Runner timeout.
2. Đổi `concurrency = "2-2"` thành `"1-1"`: hai EU message được xử lý qua một consumer; kết quả vẫn đúng nhưng số hoạt động đồng thời thay đổi.
3. Thêm consumer thứ ba **không selector** lên cùng Queue: có thể giành message từ hai listener; demo không còn output xác định.
4. Thay `setStringProperty("region", region)` thành property tên `Region`: selector `region` không khớp vì identifier phân biệt chữ hoa.
5. Gây exception trong một listener và đo redelivery/DLQ theo broker policy; đừng coi việc có `sessionTransacted=true` là cấu hình đủ cho poison messages.

## 12. Ví dụ Topic end-to-end về mặt hợp đồng

Khi dùng Topic, **publisher và subscriber** phải thống nhất:
- Physical Topic name: `sales.order.paid`.
- Message type/selector properties: `eventType = 'ORDER_PAID'`.
- Subscription identities: `billing-ledger-v1` và `notification-mail-v1`.
- Kiểu subscription: shared durable nếu nhiều replica mỗi nhóm, cần giữ backlog lúc offline.
- Client ID policy: không tự gán trùng tùy tiện khi nhiều replica dùng shared subscriptions.
- Transaction/ACK, retention, expiry, redelivery, DLQ và replay.

Publisher Topic trong Spring JMS có thể được cấu hình riêng:

~~~java
@Bean("topicPublisher")
JmsTemplate topicPublisher(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setPubSubDomain(true);
    return template;
}
~~~

Mảnh code này thuộc một `@Configuration` có các import `@Bean`, `ConnectionFactory` và `JmsTemplate`. Gửi event:

~~~java
topicPublisher.convertAndSend(
        "sales.order.paid", jsonPayload, m -> {
            m.setStringProperty("eventType", "ORDER_PAID");
            return m;
        });
~~~

Mảnh gửi này yêu cầu biến `topicPublisher` và `jsonPayload` hợp lệ trong ứng dụng. **Dùng Topic publisher thật**: không lấy mặc định `JmsTemplate` đang dùng Queue rồi gửi cùng chuỗi tên và giả định broker tự hiểu. Với Artemis, Topic cần multicast address/subscription queue/routing chính xác; có thể provision qua `spring.artemis.embedded.topics` cho lab riêng hoặc cấu hình broker quản lý.

### Khi nào subscriber được nhận?

- Billing và Notification là hai subscription độc lập: mỗi nhóm có thể nhận một bản sao event phù hợp.
- Trong shared subscription Billing, các replica chia các bản tin đã vào backlog Billing; không phải mọi replica cùng nhận một bản sao.
- Với non-durable subscription đã bị xóa do offline, event publish sau đó không tự xuất hiện khi group online trở lại.
- Với durable subscription, broker lưu backlog theo policy cho subscription đã tồn tại, nhưng **không hồi tố** những event publish trước khi subscription được tạo.
- Thay selector sau khi subscription tồn tại có thể dẫn đến lỗi hoặc tạo lại subscription, tùy kiểu/subscription và provider; cần kế hoạch cutover cụ thể.

## 13. Tạo subscription, đổi selector và quản lý vòng đời

Một thay đổi trông nhỏ:

~~~text
Trước: selector = eventType = 'ORDER_PAID'
Sau:   selector = eventType IN ('ORDER_PAID', 'ORDER_REFUNDED')
~~~

đối với Topic durable **không đơn giản là đổi câu điều kiện để lấy lại tất cả message trong quá khứ**.

Quy trình nên áp dụng:

1. Xác định Topic, subscription name, client identity, shared/durable policy, selector và bản sao ứng dụng nào đang sử dụng.
2. Kiểm tra broker backlog và retention của subscription cũ; xác minh producer đang gửi property/kiểu dữ liệu nào.
3. Nếu cần đổi selector không tương thích, tạo subscription phiên bản mới (ví dụ `billing-ledger-v2`) theo quy trình đã phê duyệt, hoặc dừng consumer và dùng cơ chế subscription reconfiguration được provider hỗ trợ.
4. Khi hai subscription cùng active trong giai đoạn chuyển đổi, lưu ý **cùng business event có thể được gửi cho cả hai**, do đó consumer phải idempotent và có chiến lược tránh side effect lặp.
5. Xác minh consumer nhận đúng những event mới, backlog cũ đã xử lý/drain đúng và metric của subscription mới ổn định.
6. Chỉ delete/unsubscribe subscription cũ sau khi có bằng chứng không cần backlog nữa và owner đồng ý; đừng tự xoá trong startup một cách im lặng.

Một vấn đề rất dễ bỏ qua: khi không đặt `subscription` tường minh, Spring có thể tạo tên mặc định dựa trên **fully-qualified listener method name**. Refactor package/class/method có thể làm identity mặc định thay đổi. Vì vậy với durable/shared subscriptions, nên dùng tên **ổn định có chủ sở hữu**, không phụ thuộc method Java hoặc replica ID.

### Client ID và replicas

Với unshared durable subscription, client ID là một phần identity và cần được cấu hình. Việc hai ứng dụng đang active cùng dùng client ID có thể bị provider từ chối hoặc gây xung đột quyền truy cập state. Với shared durable subscription, client ID không bắt buộc theo chuẩn; nếu có, phải thống nhất identity và cách broker quản lý connections. Hãy kiểm tra thực tế cả sự kiện một replica restart, toàn bộ replica offline và thay đổi số replica.

## 14. Giao dịch, ACK, retry và DLQ không phụ thuộc selector

**Selector match không có nghĩa message đã xử lý thành công.** Một message có thể được chọn, callback ném exception rồi broker giao lại cùng message. Concurrency cao làm tình huống duplicate business side effect phức tạp hơn.

Trong `DefaultJmsListenerContainerFactory`:

~~~java
factory.setSessionTransacted(true);
~~~

tạo một **local JMS transaction** cho listener. Nếu handler ném exception và transaction rollback, provider có thể redeliver theo policy. Với `AUTO_ACKNOWLEDGE` mặc định của `DefaultMessageListenerContainer`, acknowledgment có thể xảy ra trước khi method thực thi, không có bảo đảm redelivery khi handler ném exception. Do đó production cần cấu hình transaction/ack có chủ ý.

Quan trọng:
- Transaction JMS không tự động gộp với database transaction. Commit DB rồi lỗi JMS commit có thể dẫn đến redelivery và side effect lặp.
- Cần business event ID, unique constraint hoặc inbox/idempotent consumer cho các thao tác không được lặp.
- Broker thiết lập max delivery attempts, backoff và DLQ; `@JmsListener(selector=...)` không giải quyết poison message.
- Không nuốt mọi exception trong handler rồi trả bình thường, nếu nghiệp vụ cần rollback/retry.
- Với shared durable subscription, mỗi delivery tới một consumer trong subscription **không** đồng nghĩa exactly-once ở toàn bộ hệ thống; transaction failure/redelivery vẫn có thể dẫn tới xử lý lại.
- Selector trên message có property thiếu có thể tạo backlog mãi không match; nếu không có monitoring, bạn có thể nhầm rằng hệ thống đã hết việc.

## 15. Quan sát listener container và thay đổi trạng thái

Một endpoint có `id` tường minh:

~~~java
@JmsListener(
    id = "euOrderListener",
    destination = "orders.jobs",
    concurrency = "2-4")
public void handle(String payload) {
    // Business handler
}
~~~

có thể được quản lý qua `JmsListenerEndpointRegistry`:

~~~java
package example.jms;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerControl {
    private final JmsListenerEndpointRegistry registry;

    public ListenerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        return container != null && container.isRunning();
    }
}
~~~

Code này là một class đầy đủ trong Spring context có JMS infrastructure. `id` là **Spring listener container ID**, không phải subscription name và không phải tên Queue/Topic. Việc gọi `stop()/start()` được dùng khi cần điều khiển lifecycle có kiểm soát; **không tự xóa durable subscription**. Không khởi động/dừng container theo HTTP request tự do nếu chưa có authorization, graceful shutdown và kiểm tra backlog.

### Metrics nên có

| Metric/trường | Dùng để |
|---|---|
| `listenerId` / factory / destination | Xác định chính xác endpoint và Queue/Topic. |
| selector ID / version | Biết property/filter nào đang active sau deploy. |
| active consumers, scheduled consumers | So sánh với cấu hình `concurrency`. |
| queue depth, oldest message age, prefetch | Xác định backlog và phân phối không đều. |
| subscription name, durable/shared, online consumers | Phân biệt mất subscriber và thiếu capacity. |
| xử lý thành công/thất bại, latency, redelivery count | Đo nghiệp vụ và reliability. |
| DLQ count / expiry count | Phát hiện poison và quá hạn. |
| DB pool/external API latency | Chẩn đoán bottleneck trước khi tăng consumers. |

Không đưa user ID/tenant ID động vô hạn vào tên metric label hoặc subscription; tránh cardinality explosion. Cẩn thận log payload nhạy cảm.

## 16. Tuning throughput, prefetch và tài nguyên

Bắt đầu bằng workload và SLA, không bắt đầu bằng con số concurrency lớn.

| Tín hiệu | Hành động đánh giá |
|---|---|
| Queue backlog cao, handler nhanh, DB còn capacity | Tăng concurrency có giới hạn, đo throughput. |
| Consumer nhiều nhưng DB pool luôn cạn | Giảm số consumer hoặc tăng downstream capacity/queueing, không chỉ thêm thread. |
| Một consumer có nhiều message prefetched | Tune prefetch/pooling của provider; theo dõi fairness. |
| Topic handler nhận nhiều bản sao trên cùng node | Kiểm tra có phải nhiều **unshared subscriptions** thay vì shared subscription. |
| Durable Topic không nhận sau restart | Kiểm tra client ID/subscription name/topic/selector và backlog cũ. |
| Sau đổi selector, subscription báo conflict | Kiểm tra active consumers và thay đổi contract; lên kế hoạch tạo phiên bản mới. |
| Ordering business bị phá khi tăng replica | Xem message group/partition và idempotency/sequence. |
| Một broker chứa nhiều tenant nhạy cảm | Đừng dùng selector làm phân quyền; đánh giá namespace/ACL riêng. |

### Concurrency là chi phí thật

Mỗi JMS consumer cần session/connection hoặc tài nguyên cached theo thiết lập container và provider. Một Queue listener có maxConcurrency 8 nhân với 5 replica có thể lên đến 40 consumers; ba endpoints như vậy sẽ cần một ngân sách đáng kể cho broker/thread scheduling. Đừng lấy `maxConcurrency` làm số CPU core; nó là giới hạn số consumer hoạt động, còn CPU, I/O và pool capacity quyết định hiệu quả.

Với Topic không shared, tăng concurrency có thể **tạo bản sao không mong muốn**; với shared durable, tăng concurrency đúng có thể chia tải nhưng vẫn cần giới hạn downstream và đảm bảo một message không xử lý lặp side effect khi redeliver.

## 17. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa/kiểm tra |
|---|---|---|
| `@JmsListener(selector=...)` không nhận message dù JSON có trường đó | Property chỉ nằm trong body, không được gắn trên JMS message. | Gắn `setStringProperty`/`setIntProperty` trước send, kiểm tra trên broker. |
| Selector numeric không khớp | Producer gắn `String` cho số. | Chuẩn hóa property type trong contract. |
| `concurrency="4"` không tạo bốn consumer ngay | Dạng một số là upper bound, lower default 1. | Dùng `"4-4"` nếu thực sự muốn fixed 4; test active consumer count. |
| Topic được nhận nhiều lần mỗi replica | Mỗi replica có unshared subscription độc lập. | Dùng shared subscription cùng identity khi chỉ cần một delivery trong group. |
| Unshared durable Topic không scale active-active | Một subscription chỉ cho một active consumer/client ID conflict. | Dùng shared durable nếu provider hỗ trợ và business cần scale. |
| Có `subscription="billing"` mà vẫn mất message khi offline | Chưa bật `setPubSubDomain(true)` và `setSubscriptionDurable(true)`. | Kiểm tra Topic factory và đúng subscription lifecycle. |
| Đổi tên method rồi mất backlog Topic cũ | Dùng tên subscription mặc định dựa vào fully qualified method. | Đặt subscription name tường minh, có kế hoạch migration. |
| Đổi selector Topic nhưng không nhận event cũ | Selector chọn message khi publish vào subscription; không hồi tố lịch sử. | Tạo/cutover subscription có kiểm soát và replay nếu cần. |
| Tăng concurrency làm xử lý sai thứ tự | Nhiều consumer hoàn tất bất đồng bộ. | Partition/group theo business key, sequence/idempotency. |
| Listener báo thành công nhưng DB ghi trùng | Redelivery sau partial commit, không có idempotency. | Unique event ID, inbox/outbox hoặc transaction phù hợp. |
| Có consumer nhưng Queue backlog vẫn tăng | Selector không match hoặc thiếu capacity/prefetch lệch. | Kiểm tra raw JMS properties, active selectors, broker metrics. |
| Cùng client ID trên nhiều replica bị lỗi | Unshared durable identity hoặc connection policy bị trùng. | Phân biệt shared/unshared, quản lý client identity đúng chuẩn/provider. |

## 18. Bộ kiểm thử nên có trong CI và staging

1. **Khởi tạo endpoint:** từng `@JmsListener` resolve đúng destination, factory, selector, concurrency và subscription. Selector sai cú pháp phải bị phát hiện khi tạo consumer.
2. **Chọn message:** gửi event match và không match; kiểm tra unfiltered consumer không giành message ngoài ý muốn.
3. **Kiểu property:** gửi String, int, boolean đúng và sai kiểu, property thiếu/NULL; xác minh selector có kết quả dự kiến.
4. **Queue concurrency:** gửi hàng trăm job độc lập, tăng replicas; đo throughput, in-flight, active consumers, prefetch, ordering.
5. **Concurrency & thread safety:** nhiều listener invocation đồng thời không làm race trên mutable state hoặc duplicate database side effect.
6. **Topic fan-out:** hai subscription nghiệp vụ độc lập cùng nhận một event phù hợp; nhiều replica trong một shared subscription không tự mỗi replica nhận một bản sao.
7. **Durability:** tạo durable subscription **trước** khi publish, ngắt toàn bộ consumers rồi publish; sau khi nối lại, verify backlog/retention/expiry.
8. **Identity:** thử active-active với shared durable; thử unshared durable có hai consumers và xác nhận broker xử lý đúng ràng buộc.
9. **Selector migration:** đổi selector/version theo kế hoạch, kiểm tra backlog cũ, duplicate, replay và cleanup.
10. **Failure:** ném exception, kill process, network disconnect, rollback; xác minh retry/redelivery, DLQ, idempotency và eventual state.
11. **Security:** producer khác tenant không thể vượt ACL, kể cả khi đặt property trông như một tenant hợp lệ.
12. **Resource budget:** số consumer thực tế theo replica, broker limits, DB connection pool và latency trong giờ cao điểm.

Các test này cần **broker/client thực** nếu muốn kết luận về durable/shared semantics, performance và failure mode. Unit test Java của method handler không đủ để xác nhận subscription name hay transaction recovery.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Queue có listener `concurrency="2-4"` trên 3 replicas. Trần số JMS consumers cho endpoint này là bao nhiêu?

**Đáp án:** Khoảng `3 × 4 = 12` consumers nếu mọi replica scale tới giới hạn; con số thực tế phụ thuộc resource/broker. Không phải 4 consumers cho toàn cluster.

**Câu 2.** Một Topic có Billing và Notification; mỗi service có 3 replicas, cần **mỗi event một lần cho mỗi service** và không mất event khi toàn bộ nhóm offline. Chọn subscription nào?

**Đáp án:** Hai **shared durable subscriptions** tách biệt, ví dụ `billing-ledger-v1` và `notification-mail-v1`. Mỗi subscription có nhiều consumers chia tải trong nhóm; broker giữ message cho subscription khi offline theo durability/expiry policy.

**Câu 3.** Đặt `@JmsListener(subscription="billing")` và `concurrency="3-3"` trên factory Queue có tạo Topic shared durable không?

**Đáp án:** Không. Cần `setPubSubDomain(true)`, `setSubscriptionDurable(true)` và `setSubscriptionShared(true)` ở factory phù hợp, Topic tồn tại và broker hỗ trợ kiểu subscription đó.

**Câu 4.** Vì sao `concurrency="4"` có thể ban đầu chỉ có một active consumer?

**Đáp án:** Một số biểu diễn upper bound, lower mặc định 1; container có thể scale khi tải tăng. Dùng `"4-4"` nếu cần fixed 4, và kiểm tra active consumers thực tế.

**Câu 5.** Consumer Topic shared non-durable có giữ message publish khi không consumer nào online không?

**Đáp án:** Không. Shared xác định cách chia tải, không xác định lưu backlog offline. Cần durable subscription khi muốn giữ các message mới publish lúc nhóm offline.

**Câu 6.** Thay selector của durable subscription đang có backlog có tự cập nhật cách chọn message cũ không?

**Đáp án:** Không. Selector quyết định message vào subscription tại thời điểm publish; thay hợp đồng có thể bị từ chối hoặc tạo lại subscription. Cần migration và replay có kiểm soát.

**Câu 7.** Một listener có concurrency=8 nhận hai event cùng `orderId`; event sau hoàn tất trước event trước. Đó là bug của Spring?

**Đáp án:** Không nhất thiết. Xử lý song song không bảo đảm thứ tự hoàn tất; thiết kế cần nhóm/partition theo key, sequence và state machine/idempotency.

**Câu 8.** `@JmsListener(id="billingPaidEvents")` có đồng nghĩa JMS subscription cũng mang tên đó không?

**Đáp án:** Không. `id` nhận diện Spring listener container, còn `subscription` xác định subscription identity trên Topic. Hai tên có vòng đời, mục đích khác nhau.

## 20. Checklist triển khai và tài liệu chính thức

- [ ] Đã xác định rõ destination là Queue hay Topic, không dựa vào chuỗi tên.
- [ ] Selector tham chiếu JMS properties/header hợp lệ; producer gửi đúng kiểu và consistent schema.
- [ ] Factory đúng `pubSubDomain`, transaction/ACK, concurrency, QoS/recovery; annotation chọn đúng factory.
- [ ] Hiểu `"4"` khác `"4-4"` và concurrency trên mỗi endpoint/replica.
- [ ] Listener handler thread-safe và idempotent theo yêu cầu nghiệp vụ.
- [ ] Với Topic, đã chọn đúng shared/unshared và durable/non-durable; subscription name ổn định.
- [ ] Unshared durable có client ID phù hợp và không có nhiều active consumers.
- [ ] Với shared durable, client identity và broker support đã được thử; các replica thực sự tham gia cùng một subscription.
- [ ] Có kế hoạch thay selector/subscription, giữ/drain backlog và xử lý duplicate lúc migration.
- [ ] Đã thử concurrency, Queue/Topic semantics, broker restart, recovery, redelivery/DLQ và ACL.
- [ ] Có metrics active consumers, Queue depth, subscription backlog và alert cho selector không match.

**Tài liệu chính thức:**

- [Spring Framework — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework 6.2 — @JmsListener Javadoc: selector, concurrency, subscription, id](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html).
- [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html).
- [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc: concurrency và Topic caution](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html).
- [Spring Framework — Receiving messages và transaction](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html).
- [Jakarta Messaging 3.1 specification — Topic subscriptions, shared/durable, selector semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Spring Boot 3.5 — JMS Artemis integration](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Spring Boot 3.5 — Artemis embedded properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/).
