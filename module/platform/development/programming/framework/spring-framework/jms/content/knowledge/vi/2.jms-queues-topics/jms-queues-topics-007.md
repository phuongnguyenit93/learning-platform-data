# Durable subscription và thông điệp tồn tại bền vững là hai khái niệm khác nhau

> **Module:** Spring Framework – JMS  
> **Nhóm kiến thức:** Queue và Topic  
> **Trọng tâm:** Phân biệt *tuổi thọ của một topic subscription* với *chế độ giao nhận của từng message* trong JMS/Jakarta Messaging, rồi cấu hình đúng trong Spring.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `durable subscription`, `non-durable subscription`, `PERSISTENT` và `NON_PERSISTENT`; chỉ ra chúng thuộc **hai trục cấu hình độc lập**.
2. Dự đoán điều gì xảy ra khi một topic consumer tạm ngừng, khi broker khởi động lại, khi subscription chưa từng được tạo hoặc khi message hết hạn.
3. Đọc được bảng bốn tổ hợp durable/non-durable × persistent/non-persistent mà không nhầm "đã lưu thông điệp" với "đã đăng ký nhận thông điệp".
4. Cấu hình một durable topic listener và một persistent producer bằng Spring JMS; biết vai trò của `clientId`, `subscription`, `pubSubDomain`, transaction và acknowledgment.
5. Thiết kế phép thử vận hành và xử lý trường hợp mất kết nối, gửi lại, nhận trùng, thay đổi định danh subscription.

## 1. Hai câu hỏi khác nhau bị gọi chung là “bền vững”

**Câu hỏi A — Vòng đời subscription:** Khi ứng dụng không có consumer đang kết nối, broker có tiếp tục biết *ai* đã đăng ký topic và giữ thông điệp cho người đó hay không?

- Đây là lựa chọn **durable subscription** hay **non-durable subscription**.
- Nó nằm ở **phía subscription/consumer** của một **topic**.
- Một durable subscription có **định danh ổn định** trong provider, tiếp tục tồn tại khi consumer tắt, và cho phép consumer sau này nhận những message phù hợp đã đến trong khoảng vắng mặt, theo các điều kiện giao nhận và lưu giữ.

**Câu hỏi B — Mức bảo đảm giao nhận message:** Khi producer gửi *một thông điệp*, broker có phải dùng cơ chế đáng tin cậy hơn để thông điệp chống chịu sự cố provider hay không?

- Đây là **delivery mode**: `PERSISTENT` hoặc `NON_PERSISTENT`.
- Nó thuộc **từng lần gửi/từng message**, do producer yêu cầu; broker thực thi theo đặc tả và chính sách lưu giữ.
- `PERSISTENT` nâng mức bảo vệ của việc vận chuyển và lưu message trước lỗi provider; nó **không tự tạo một subscription đang vắng mặt**.

Một câu ngắn để nhớ:

> **Durable subscription giữ “người nhận đã đăng ký” qua lúc offline; persistent delivery bảo vệ “thông điệp được gửi” trước lỗi hạ tầng.**

Với trường hợp **topic consumer offline + broker gặp sự cố**, muốn độ tin cậy cao thường cần **cả durable subscription và PERSISTENT delivery**, cộng với chính sách retention, TTL, transaction và hạ tầng broker phù hợp. Hai tùy chọn không thay thế nhau.

## 2. Nhắc lại topic: message được ghi nhận theo subscription

Producer gửi vào một `Topic`; người nhận không trực tiếp “rút” một bản chung của topic như queue. Provider quản lý **subscription**: mỗi subscription đủ điều kiện có thể nhận một bản sao của message được publish sau khi subscription tồn tại.

```text
                                   TOPIC: orders.events
                                      |
                    +-----------------+-----------------+
                    |                                   |
           Subscription: audit                 Subscription: analytics
                    |                                   |
               Audit Consumer                       Analytics Consumer
```

Nếu `audit` và `analytics` là hai subscription độc lập, việc consumer Audit xác nhận message **không** đồng nghĩa Analytics đã xác nhận bản của mình. Trong một **shared subscription**, nhiều consumer có thể chia công việc của **cùng subscription**; mỗi message thuộc subscription đó được giao cho một consumer, chứ không tự nhân bản cho mọi worker trong nhóm.

Thông thường, subscription chỉ thấy message được publish **sau khi nó được tạo**. Durable subscription không phải cơ chế “replay toàn bộ lịch sử topic” cho một subscriber mới đăng ký. Nếu muốn replay dữ liệu trước thời điểm đăng ký, cần một tính năng hoặc luồng lưu trữ lịch sử riêng do hệ thống thiết kế.

### 2.1. Non-durable subscription

Một non-durable subscription chỉ tồn tại khi còn consumer hoạt động theo vòng đời mà JMS định nghĩa. Khi subscription ngừng tồn tại, message mới publish lúc đó **không được tích lũy** để một consumer cùng tên quay lại lấy sau.

```text
t0       t1            t2             t3
|--------|-------------|--------------|
         consumer OFF  publish M1     consumer ON
         sub biến mất  không có sub   không nhận M1 từ thời gian offline
```

Ngay cả khi producer gửi M1 với `PERSISTENT`, điều đó **không giữ hộ M1 cho một non-durable subscription đã biến mất**. Đây là trường hợp hiểu sai rất phổ biến.

### 2.2. Durable subscription

Durable subscription là một thực thể được provider lưu giữ, **không bị xóa chỉ vì consumer đóng kết nối**. Nếu không có consumer đang hoạt động, subscription ở trạng thái *inactive*; provider tiếp tục quản lý những message phù hợp đi vào subscription, chịu các điều kiện như message expiration, chế độ delivery và chính sách broker.

```text
t0                  t1                  t2                 t3
|-------------------|-------------------|------------------|
tạo durable sub     consumer OFF        publish M1         consumer ON
(clientId + name)   sub còn tồn tại     cho sub đã có     tiếp tục từ sub cũ
```

Trên đường phục hồi đáng tin cậy, M1 nên được gửi `PERSISTENT` và chưa hết hạn. Nếu gửi `NON_PERSISTENT`, **không được coi việc giữ message qua thời gian inactive hoặc broker failure là bảo đảm**.

Durable subscription **không có nghĩa mọi lần gửi đều được lưu mãi mãi**: message có thể đã được tiêu thụ/xác nhận, hết hạn, không khớp selector hoặc chịu chính sách giới hạn tài nguyên của broker. Subscription vẫn có thể tồn tại nhưng không còn message đang chờ.

## 3. “Persistent message” thực sự là gì?

JMS/Jakarta Messaging có hai giá trị chuẩn trong `jakarta.jms.DeliveryMode`:

| Delivery mode | Ý nghĩa chính | Điều không được suy diễn |
| --- | --- | --- |
| `PERSISTENT` | Provider phải áp dụng bảo đảm giao nhận chống lỗi provider mạnh hơn, thường liên quan ghi log/storage bền vững; lựa chọn ưu tiên độ tin cậy | Không tự tạo durable subscription; không bảo đảm lưu vô hạn, bỏ qua expiration, hay hoàn thành nghiệp vụ đúng một lần |
| `NON_PERSISTENT` | Cho phép đường giao nhận ít overhead hơn; message có thể mất khi provider gặp lỗi | Không có nghĩa broker bắt buộc làm rơi ngay lập tức; thực tế có thể vẫn được giao nếu hệ thống đang chạy ổn định |

Trong API đơn giản, producer có thể chọn:

```java
JMSProducer producer = context.createProducer();
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.send(topic, "OrderCreated: ORD-42");
```

Đây là **đoạn minh họa trong ứng dụng đã có** `JMSContext context`, `Topic topic`, dependency `jakarta.jms` và provider thật. Không thể chạy riêng bằng `javac` khi thiếu các thành phần đó. Với classic API, lựa chọn tương đương đặt trên `MessageProducer` hoặc tham số của `send(...)`; **không** dùng `message.setJMSDeliveryMode(...)` để yêu cầu mode gửi.

### “Persistent” không đồng nghĩa “không bao giờ mất”

Bảo đảm delivery mode theo đặc tả giả định destination có chính sách giữ thông điệp đủ phù hợp. Các yếu tố cần xét:

- `timeToLive` và `JMSExpiration`: message hết hạn có thể không còn được giao, kể cả `PERSISTENT`.
- **Message selector:** subscription chỉ tích lũy message khớp điều kiện lọc; message khác không thuộc subscription đó.
- **Retention, quota, disk, broker policy:** nếu không đủ tài nguyên, nhà vận hành phải quyết định hành vi và theo dõi cảnh báo. Persistent không biến broker thành kho lưu vô hạn.
- **Acknowledgment/transaction:** một message đã được nhận, xác nhận hoặc commit đúng cách không phải tiếp tục lưu chờ consumer mãi.
- **Độ bền cấu hình provider:** cơ chế lưu bền vững, cụm broker, replication và khôi phục thảm họa phụ thuộc provider và cách triển khai; `PERSISTENT` không thay thế chiến lược vận hành.

Trong điều kiện có destination retention phù hợp, đặc tả mô tả mức bảo đảm của `PERSISTENT` ở **giao nhận phía provider** mạnh hơn `NON_PERSISTENT`. Điều đó không phải lời hứa “business side effect exactly once”: database có thể đã commit trước khi consumer kịp ack, dẫn đến xử lý nghiệp vụ lặp khi message redeliver.

## 4. Bảng bốn tổ hợp — trọng tâm của bài

Bảng sau giả định đang publish vào **topic**, subscription đã được tạo trước thời điểm gửi, message khớp selector và chưa hết hạn.

| Subscription | Message mode | Consumer offline lúc publish | Broker/provider gặp sự cố | Kết luận |
| --- | --- | --- | --- | --- |
| **Non-durable** | `NON_PERSISTENT` | Không có subscription để tích lũy message; bỏ lỡ | Message cũng có thể mất do mode yếu hơn | Hợp với dữ liệu bỏ lỡ được |
| **Non-durable** | `PERSISTENT` | **Vẫn bỏ lỡ** nếu subscription đã không còn | PERSISTENT bảo vệ việc gửi tới destination/subscription đủ điều kiện, không khôi phục subscriber đã biến mất | **PERSISTENT không thay thế durable** |
| **Durable** | `NON_PERSISTENT` | Subscription vẫn tồn tại, nhưng **không có bảo đảm** mọi non-persistent message được giữ tới lúc quay lại | NON_PERSISTENT có thể mất khi provider lỗi | **Durable không thay thế PERSISTENT** |
| **Durable** | `PERSISTENT` | Có cơ sở để tích lũy message phù hợp trong thời gian consumer vắng mặt | Bảo đảm mạnh hơn trước sự cố provider theo đặc tả và chính sách lưu giữ | Lựa chọn thông thường cho sự kiện quan trọng cần nhận sau khi offline |

**Đọc bảng theo hai trục**, không diễn giải “durable” hoặc “persistent” thành một công tắc duy nhất mang tên “reliable”.

### 4.1. Ví dụ A: persistent nhưng non-durable vẫn mất sự kiện

- `Analytics` tạo **non-durable** subscription trên `orders.events` khi chạy.
- 10:00 Analytics dừng, subscription không còn.
- 10:05 Order Service gửi `OrderCreated(42)` với `DeliveryMode.PERSISTENT`.
- 10:10 Analytics khởi động lại.

Analytics **không có quyền mặc định nhận lại** sự kiện 10:05: thời điểm đó không tồn tại subscription của Analytics. Việc message được gửi PERSISTENT có thể bảo vệ message cho **các subscription khác** đã tồn tại và đủ điều kiện, nhưng không “tạo bản sao hồi tố” cho Analytics.

### 4.2. Ví dụ B: durable nhưng non-persistent vẫn có thể mất

- `Audit` đã tạo durable subscription `audit-orders`; sau đó consumer dừng.
- Producer gửi `OrderCreated(43)` bằng `NON_PERSISTENT`.
- Trong thời gian Audit offline, provider bị dừng đột ngột và khởi động lại.
- Audit kết nối lại bằng **cùng định danh subscription**.

Dù durable subscription vẫn còn, **không được kết luận** message 43 chắc chắn được phục hồi. Đặc tả cho phép rủi ro mất message `NON_PERSISTENT`; tình huống không mất trong một lần thử không nâng nó thành bảo đảm chung.

### 4.3. Ví dụ C: durable + persistent cho sự kiện quan trọng

- `Audit` đã đăng ký durable subscription, lưu định danh ổn định.
- Consumer dừng; producer gửi `OrderCreated(44)` bằng `PERSISTENT` với TTL phù hợp.
- Broker hoạt động bình thường hoặc được phục hồi trong phạm vi bảo đảm, retention đủ khả năng giữ message.
- Audit quay lại đúng subscription, nhận và xử lý message, rồi commit/ack.

Đây là thiết kế thông thường để hạn chế mất sự kiện trong thời gian consumer không online. Vẫn cần **idempotency**, vì message có thể được redeliver khi ranh giới ack/commit chưa hoàn tất.

## 5. Định danh durable subscription: vì sao “quay lại cùng tên” quan trọng?

Durable subscription được lưu theo một định danh; consumer cần khôi phục **đúng subscription cũ** để nhận backlog thay vì đăng ký một subscription mới.

### Unshared durable subscription

Trong Jakarta Messaging, **unshared durable subscription** được nhận diện bằng **client identifier (`clientId`) và subscription name**, cùng các thuộc tính phù hợp như topic, selector và `noLocal`.

```text
Topic:           orders.events
Client ID:       audit-service
Subscription:    audit-orders-v1

=> một durable subscription cụ thể phía provider
```

Consumer khởi động lần đầu và tạo subscription, sau đó dừng. Ở lần khởi động tiếp theo, dùng cùng `clientId` + `subscriptionName` để mở lại; chỉ **một consumer hoạt động** được gắn với một unshared durable subscription tại một thời điểm.

Nếu vô tình đổi `audit-orders-v1` thành `audit-orders-v2`, đó là **subscription khác**: backlog cũ không tự được chuyển sang tên mới. Subscription cũ có thể tiếp tục giữ tài nguyên cho tới khi xóa theo quy trình thích hợp.

Một lỗi triển khai hay gặp là chạy hai replica với **cùng client ID** cho unshared durable subscription và mong cả hai đọc song song. JMS hạn chế việc dùng client ID trùng đồng thời và chỉ cho một consumer hoạt động với unshared durable subscription. Muốn tăng tải, phải chọn đúng kiểu **shared durable** hoặc phân tách những subscription có mục đích độc lập.

### Shared durable subscription

JMS 2.0/Jakarta Messaging hỗ trợ **shared durable subscription**: cùng subscription có thể có nhiều consumer cùng tiêu thụ; một message thuộc subscription này được giao cho một consumer trong nhóm. Shared durable được định danh bằng subscription name và client ID **nếu được thiết lập**; quy tắc chia tải phụ thuộc provider.

Khác biệt:

- **Hai durable subscription độc lập** (`audit` và `analytics`): mỗi nhóm được một bản sao sự kiện phù hợp.
- **Hai consumer cùng một shared durable subscription** (`audit-worker-1` và `audit-worker-2`): cùng chia công việc của một nhóm; mỗi message không mặc nhiên đến cả hai worker.

Đừng chuyển giữa shared và unshared bằng cách đổi một flag tùy tiện khi subscription đang hoạt động. Kiểm tra khả năng hỗ trợ của provider, identity, selector, quá trình thay đổi cấu hình và dữ liệu chờ trước khi triển khai.

### Thay đổi selector hoặc topic cũng có thể ảnh hưởng backlog

Với **unshared durable**, đặc tả quy định khi subscription không hoạt động mà client tạo lại với cùng client ID + name nhưng **khác topic, message selector hoặc `noLocal`**, hành vi tương đương bỏ subscription cũ và tạo subscription mới. Backlog của subscription cũ có thể mất. Vì vậy không xem việc đổi filter hay tên topic là “chỉ sửa cấu hình vô hại”.

## 6. Ranh giới khác: queue không dùng khái niệm topic durable subscription

`Queue` có mô hình chia công việc giữa các consumer. Message được gửi vào queue có thể chờ đến khi một consumer đủ điều kiện nhận; không cần tạo **durable topic subscription** cho từng consumer đang tắt. Chế độ `PERSISTENT`/`NON_PERSISTENT` vẫn áp dụng cho message ở queue.

```text
QUEUE:                                TOPIC:

Producer --> [Queue] --> Worker      Producer --> [Topic]
                                               |
                                      +--------+--------+
                                      |                 |
                                 Durable sub A     Non-durable sub B
                                      |                 |
                                    Worker A          Worker B
```

| Câu hỏi | Queue | Topic |
| --- | --- | --- |
| Khi mọi consumer đang offline, message còn chờ không? | Thường có, theo delivery mode/retention của queue | Chỉ subscription tồn tại (durable) mới có cơ sở giữ message cho lúc offline |
| Có cần `clientId + durable subscription name`? | Không cho cách consume queue thông thường | Có với **unshared durable subscription** |
| `PERSISTENT` có còn quan trọng? | Có | Có |
| “Một message cho nhiều nhóm độc lập” thực hiện thế nào? | Cần nhiều queue hoặc thiết kế fan-out riêng | Nhiều subscription độc lập trên một topic |

Trong cả hai mô hình, **sống sót qua broker failure** và **lưu đến khi consumer hoàn thành** phải được kiểm tra cùng với ack/transaction, TTL và resource policy.

## 7. Cách cấu hình trong Spring JMS (Jakarta Messaging)

Spring Framework 6+ sử dụng `jakarta.jms`. Hai trục có vị trí cấu hình khác nhau:

- **Phía listener:** `DefaultJmsListenerContainerFactory.setPubSubDomain(true)`, `setSubscriptionDurable(true)`, `setClientId(...)`; method `@JmsListener` khai báo `subscription`.
- **Phía producer:** `JmsTemplate.setPubSubDomain(true)` để gửi topic, `setDeliveryPersistent(true)` / `setDeliveryMode(DeliveryMode.PERSISTENT)` để chọn chế độ; **phải bật `setExplicitQosEnabled(true)`** nếu muốn `JmsTemplate` áp dụng các QoS override thay vì phụ thuộc mặc định provider.

### 7.1. Ví dụ Spring: durable topic consumer và persistent producer

Giả sử ứng dụng Spring đã có dependency `spring-jms`, provider JMS tương thích, `jakarta.jms.ConnectionFactory` trỏ tới broker thật, destination `orders.events` được cấu hình và ứng dụng có component scanning. Đoạn mã dưới dùng Java 17+; **đây là ví dụ các lớp nằm trong một Spring project**, không phải một tệp standalone có thể chạy chỉ bằng `javac`.

**File `DurableTopicJmsConfig.java`**:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class DurableTopicJmsConfig {

    @Bean
    public DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);            // Destination là Topic
        factory.setSubscriptionDurable(true);     // Giữ subscription khi offline
        factory.setClientId("audit-service");     // Ổn định qua các lần restart
        factory.setConcurrency("1");              // Unshared: một consumer hoạt động
        factory.setSessionTransacted(true);       // Commit/rollback việc nhận JMS
        return factory;
    }

    @Bean
    public JmsTemplate persistentTopicTemplate(ConnectionFactory connectionFactory) {
        var template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true);           // Gửi vào Topic
        template.setExplicitQosEnabled(true);     // Áp dụng QoS tự cấu hình
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setTimeToLive(0);                // 0 = không đặt thời hạn JMS
        return template;
    }
}
```

**File `OrderEventPublisher.java`**:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate persistentTopicTemplate;

    public OrderEventPublisher(
            @Qualifier("persistentTopicTemplate") JmsTemplate persistentTopicTemplate) {
        this.persistentTopicTemplate = persistentTopicTemplate;
    }

    public void publishOrderCreated(String orderId) {
        persistentTopicTemplate.convertAndSend("orders.events", orderId);
    }
}
```

**File `OrderAuditListener.java`**:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @JmsListener(
            destination = "orders.events",
            subscription = "audit-orders-v1",
            containerFactory = "durableTopicFactory")
    public void onOrderCreated(String orderId) {
        // Ứng dụng thật: kiểm tra eventId, cập nhật nghiệp vụ có transaction.
        System.out.println("Audit received order: " + orderId);
    }
}
```

Nếu `publishOrderCreated("ORD-42")` được gọi khi broker, publisher và listener chạy đúng cấu hình, listener **có thể** in:

```text
Audit received order: ORD-42
```

Đây chỉ là **kết quả minh họa khi consumer thực sự nhận và xử lý message**; không thể cam kết log xuất hiện đúng một lần hoặc xuất hiện ngay sau lời gọi gửi. Message có thể ở trạng thái chờ trong broker, bị retry, hoặc không đến do lỗi cấu hình/điều kiện delivery.

### 7.2. Vai trò từng dòng trong hai trục

| Dòng cấu hình | Trục quyết định | Bỏ hoặc đặt sai có thể gây gì? |
| --- | --- | --- |
| Listener `setPubSubDomain(true)` | Chọn Topic | Có thể bị hiểu thành queue với cùng tên logic |
| Listener `setSubscriptionDurable(true)` | Vòng đời subscription | Khi không còn consumer, subscription không còn giữ backlog |
| Listener `setClientId("audit-service")` | Định danh unshared durable | Khởi động lại với ID khác sẽ không mở lại đúng subscription; ID trùng giữa replica gây lỗi |
| `@JmsListener(subscription="audit-orders-v1")` | Tên subscription | Đổi tên sẽ không tự kế thừa backlog cũ |
| Producer `setPubSubDomain(true)` | Chọn Topic | Có thể gửi sang queue thay vì topic |
| Producer `setExplicitQosEnabled(true)` | Áp dụng QoS override | `setDeliveryMode` có thể không chi phối send như tưởng |
| Producer `setDeliveryMode(PERSISTENT)` | Độ tin cậy của message | Chọn NON_PERSISTENT sẽ cho phép mất message khi provider lỗi |
| Listener `setSessionTransacted(true)` | Ack/commit JMS | Chỉ cấu hình durable chưa đủ để xử lý lỗi đáng tin cậy |

**Phạm vi transaction:** `setSessionTransacted(true)` đặt việc nhận JMS trong local JMS transaction. Nó **không tự gộp transaction database** với transaction broker. Nếu DB đã commit rồi JVM chết trước khi JMS commit, message có thể trở lại; consumer phải xử lý trùng an toàn hoặc dùng cơ chế transaction phối hợp phù hợp.

**Triển khai nhiều instance:** ví dụ dùng **unshared durable** và một `clientId` cố định. Đừng chạy đồng thời hai replica cùng client ID như hai consumer riêng. Nếu cần scale, cân nhắc `setSubscriptionShared(true)` trên provider có hỗ trợ shared durable và lên kế hoạch lại identity, hoặc chia consumer theo trách nhiệm.

**Không phụ thuộc vào giá trị mặc định:** JMS thường mặc định producer gửi `PERSISTENT`, nhưng QoS có thể được đặt phía provider hoặc Spring. Khi nội dung yêu cầu độ tin cậy cụ thể, cấu hình rõ và xác minh `JMSDeliveryMode`/metadata thực tế ở broker thay vì đoán từ code.

### 7.3. Tại sao không nên bật durable cho mọi listener?

Durable subscription giữ tài nguyên và có thể tạo backlog ngày càng lớn khi consumer lâu không hoạt động. Nếu mỗi lần deploy lại tạo subscription mới theo tên instance ngẫu nhiên, broker sẽ tích lũy nhiều subscription “mồ côi”. Hãy dùng durable khi dữ liệu cần được giữ cho nhóm đó, đặt tên có quản trị, có cảnh báo backlog, và quy trình `unsubscribe` khi subscription thật sự không còn được dùng.

## 8. Kịch bản thử nghiệm để chứng minh hai trục

Một thử nghiệm tốt phải **tách consumer offline** khỏi **broker failure**. Đừng chỉ gửi một message trong lúc tất cả đang online rồi suy ra có độ bền.

### Thử nghiệm 1 — Durable khi consumer offline

1. Khởi động broker; chạy listener durable `audit-service/audit-orders-v1` ít nhất một lần để tạo subscription.
2. Dừng listener/ứng dụng **nhưng không xóa subscription**.
3. Giữ broker chạy; publish `M1` bằng `PERSISTENT` vào `orders.events`.
4. Xác minh broker hiển thị subscription inactive và có message phù hợp đang chờ (cách quan sát tùy provider).
5. Khởi động listener trở lại bằng **cùng client ID + subscription name**; xác minh nhận `M1` rồi ack/commit.

Kết quả mong đợi trong điều kiện thông thường: message đã publish trong thời gian offline được giữ để listener nhận sau. Nếu không nhận, kiểm tra tạo subscription trước khi gửi, topic, selector, TTL, retention, quyền truy cập và identity.

### Thử nghiệm 2 — PERSISTENT không cứu non-durable

1. Tạo **non-durable** topic consumer, xác minh nhận `M0` khi online.
2. Đóng consumer; bảo đảm non-durable subscription không còn.
3. Publish `M2` bằng `PERSISTENT` trong lúc consumer offline.
4. Tạo lại non-durable consumer.

Không kỳ vọng nhận hồi tố `M2`. Nếu một tính năng broker-specific cho phép replay, hãy ghi rõ đó là tính năng riêng, **không phải bảo đảm của JMS non-durable subscription**.

### Thử nghiệm 3 — Broker restart

1. Giữ một **durable** subscription đã được tạo; dừng consumer.
2. Publish `M3` bằng `PERSISTENT`; xác minh broker đã chấp nhận, message chưa expire.
3. Cho broker dừng/khởi động lại theo kịch bản kiểm thử hạ tầng, với persistence/retention được cấu hình phù hợp.
4. Khởi động consumer bằng định danh cũ và xác minh xử lý `M3`.

Nếu lặp với `NON_PERSISTENT`, **không đặt tiêu chí bắt buộc “phải mất”**: mode đó cho phép mất khi lỗi provider, chứ không yêu cầu mọi provider đánh rơi message trong mọi lần restart. Tiêu chí đúng là **không dựa vào kết quả may mắn để hứa độ tin cậy**.

### Thử nghiệm 4 — TTL và acknowledgment

- Gửi `PERSISTENT` nhưng đặt TTL rất ngắn, để consumer offline quá lâu: message có thể hết hạn, không thể dùng ví dụ này để kết luận durable bị lỗi.
- Trong listener có transaction, cố tình gây lỗi sau khi nhận: quan sát rollback/redelivery theo cấu hình của provider; sau đó bảo đảm idempotency khi thử lại.
- Kiểm tra lại message vừa bị nhận chưa ack khi consumer chết: durable subscription cần lưu/recover những message chưa được ack theo các điều kiện của JMS.

### Ma trận kiểm chứng cần ghi lại

| Phép thử | Subscription | Send mode | Điều cần khẳng định |
| --- | --- | --- | --- |
| Offline + quay lại | Durable | PERSISTENT | Tiếp tục nhận backlog phù hợp, chưa expire |
| Offline + quay lại | Non-durable | PERSISTENT | Không có backlog được bảo toàn cho subscription đã biến mất |
| Broker restart | Durable | PERSISTENT | Khả năng phục hồi theo bảo đảm JMS và cấu hình storage/retention |
| Broker restart | Durable | NON_PERSISTENT | Không được **bảo đảm** phục hồi; kết quả một lần test có thể khác nhau |
| Listener xử lý lỗi | Durable | PERSISTENT | Ack/transaction quyết định redelivery; cần idempotency |

## 9. Các lỗi thực tế và cách nhận diện

### Lỗi 1: “Producer đã bật PERSISTENT, vậy topic listener offline sẽ không mất message”

**Sai ở trục subscription.** Nếu listener chỉ dùng non-durable subscription và đã đóng, không có nơi ghi nhận quyền nhận message trong thời gian offline. Cần durable subscription đã được đăng ký trước, phù hợp với trách nhiệm nghiệp vụ.

### Lỗi 2: “Đã bật durable nên không quan tâm delivery mode”

**Sai ở trục message.** Durable giữ danh tính subscription và backlog theo mô hình; `NON_PERSISTENT` vẫn mang rủi ro mất do provider failure và không được bảo đảm khi durable consumer inactive. Với sự kiện quan trọng, gửi `PERSISTENT` và kiểm tra retention.

### Lỗi 3: “Đổi tên subscription khi deploy chỉ để dễ đọc log”

Tên subscription là một phần của định danh và ảnh hưởng backlog. Khi đổi tên, consumer mới có thể không nhận message đang chờ ở subscription cũ. Cần quy trình migration, quan sát số message chưa xử lý, và chủ động quản lý subscription cũ.

### Lỗi 4: “Chạy hai replica cùng client ID là có hai worker chia tải”

Với unshared durable, đó không phải mô hình scale hợp lệ. Chọn shared durable khi cần nhiều consumer trong cùng subscription và provider hỗ trợ; hoặc tách thành các subscription khác nhau nếu cần fan-out độc lập.

### Lỗi 5: “Chỉ cần durable + PERSISTENT là đủ exactly-once cho hệ thống”

Không. Khi listener ghi DB thành công rồi mất kết nối trước khi JMS commit/ack, message có thể được gửi lại; nếu thực hiện gửi email, cộng điểm hoặc trừ tiền không có khóa idempotency, side effect có thể nhân đôi. Durable và PERSISTENT giải quyết các đoạn khác của bài toán độ tin cậy, không thay thế thiết kế transaction/khử trùng lặp.

### Lỗi 6: “Consumer không nhận message thì chắc chắn provider đã làm mất”

Không hẳn. Kiểm tra theo thứ tự: đúng broker và topic, subscription đã tồn tại trước khi publish, đúng `clientId`/subscription name, listener có thực sự active, selector/noLocal, TTL, broker destination policy, producer delivery mode, transaction send đã commit, authorization, và backlog/dead-letter của broker.

### Lỗi 7: “PERSISTENT nghĩa là thông điệp sống mãi”

`PERSISTENT` liên quan mức bảo đảm giao nhận trước lỗi provider. Message vẫn có thể hết hạn hoặc được xử lý/ack; broker có chính sách quản trị và giới hạn tài nguyên. Muốn lưu trữ sự kiện lâu dài để truy vấn lại lịch sử, đó là yêu cầu lưu trữ dữ liệu riêng, không nên ngầm giao cho topic.

## 10. Những quyết định cần chốt khi thiết kế

Trước khi đưa sự kiện quan trọng lên JMS topic, tự trả lời:

1. **Ai cần bản sao?** Mỗi hệ thống quan tâm có subscription độc lập hay đang chia tải trong cùng shared subscription?
2. **Có chấp nhận bỏ lỡ lúc offline không?** Có thì non-durable có thể phù hợp; không thì phải tạo durable subscription trước thời điểm publish.
3. **Có chấp nhận mất khi broker lỗi không?** Nếu không, cân nhắc `PERSISTENT` cùng hạ tầng và retention phù hợp.
4. **Định danh cố định là gì?** Với unshared durable, chốt `clientId` + subscription name; không thay đổi tùy phiên chạy.
5. **Message tồn tại bao lâu?** Chọn TTL, quy tắc backlog, quota, cảnh báo, cách xử lý subscription inactive lâu ngày.
6. **Khi xử lý lỗi ai ack?** Chọn local JMS transaction hoặc cơ chế phù hợp; thiết kế retry và idempotency cho database/side effects.
7. **Thay đổi topic/selector/schema ra sao?** Có kế hoạch migration backlog, tương thích payload và rollback.
8. **Quan sát điều gì?** Số subscription active/inactive, pending messages theo subscription, tuổi message, redelivery count, dead-letter và thời gian xử lý.

## 11. Tự kiểm tra

**Câu 1.** Một consumer dùng non-durable subscription. Producer phát message `PERSISTENT` trong lúc consumer tắt. Consumer có thể đòi nhận lại message theo bảo đảm JMS không?

**Đáp án:** Không. PERSISTENT không tạo hoặc giữ hộ non-durable subscription trong khoảng không có consumer.

**Câu 2.** Audit tạo durable subscription nhưng producer gửi `NON_PERSISTENT`. Khi broker chết rồi chạy lại, Audit có được bảo đảm nhận đủ không?

**Đáp án:** Không. Subscription còn danh tính nhưng mode của message cho phép mất khi provider failure; việc khôi phục thành công một lần không biến thành bảo đảm.

**Câu 3.** Hai nhóm Audit và Analytics đều cần mỗi sự kiện. Dùng hai consumer trong cùng shared durable subscription được không?

**Đáp án:** Không đạt yêu cầu mỗi nhóm đều có bản sao. Chúng sẽ chia nhau các message của **một** subscription. Cần hai subscription độc lập, có thể mỗi nhóm dùng nhiều worker bên trong shared subscription của nhóm.

**Câu 4.** Consumer durable chạy lại với client ID khác nhưng tên subscription giống cũ. Có tự nhận backlog cũ không?

**Đáp án:** Với **unshared durable**, không: định danh gồm client ID và subscription name. Phải mở lại đúng identity.

**Câu 5.** Durable + PERSISTENT + TTL 1 phút. Consumer quay lại sau 24 giờ và không nhận message. Có chắc hệ thống sai đặc tả không?

**Đáp án:** Không. Message có thể đã hết hạn theo `JMSExpiration`.

**Câu 6.** Spring listener có `setSubscriptionDurable(true)`; producer dùng `JmsTemplate.setDeliveryMode(PERSISTENT)` nhưng không bật `setExplicitQosEnabled(true)`. Đã chắc send dùng QoS được chỉ định chưa?

**Đáp án:** Chưa. `JmsTemplate` có thể dùng giá trị mặc định/được cấu hình phía provider khi explicit QoS chưa được bật. Cần cấu hình và kiểm tra delivery mode thật.

**Câu 7.** Listener commit DB rồi crash trước JMS ack. Thiết lập durable + PERSISTENT có chống ghi DB hai lần không?

**Đáp án:** Không tự động. Message có thể redeliver; phải thiết kế idempotency (ví dụ unique event ID đã xử lý) hoặc transaction phối hợp đúng phạm vi.

## Kết luận kiến thức

- **Durable subscription** trả lời: “Subscription của ai còn tồn tại để nhận message khi consumer ngắt kết nối?”
- **PERSISTENT delivery mode** trả lời: “Thông điệp này được broker giao nhận với mức bảo vệ nào trước lỗi provider?”
- Với topic sự kiện quan trọng cần nhận trong lúc consumer offline, **cả hai trục đều cần đúng**: durable subscription đã tồn tại và message PERSISTENT, cùng retention/TTL/ack/transaction phù hợp.
- Ngay cả như vậy, **không suy ra exactly-once nghiệp vụ**: phải thiết kế xử lý trùng, giám sát backlog, lỗi và vòng đời subscription.

### Tham khảo chính thức

1. [Jakarta Messaging 3.1 Specification — Topic semantics (`4.2.2)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — durable/non-durable, shared/unshared, client ID và identity.
2. [Jakarta Messaging 3.1 — Reliability (`4.2.11; `7.7; `9.1)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — bảng mode và điều kiện bảo đảm.
3. [Spring Framework — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener` và container factory.
4. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — giao dịch, acknowledgment và listener.
5. [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate`, chuyển đổi và QoS.
6. [Spring Javadoc — `JmsTemplate.setExplicitQosEnabled`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — ghi rõ điều kiện áp dụng `deliveryMode`.