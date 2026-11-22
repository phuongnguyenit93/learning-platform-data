# PERSISTENT và NON_PERSISTENT delivery mode trong Spring JMS

> **Chủ đề:** Chất lượng gửi thông điệp với Jakarta Messaging (JMS) và Spring Framework `JmsTemplate`.  
> **Mục tiêu:** Chọn đúng `DeliveryMode.PERSISTENT` hoặc `DeliveryMode.NON_PERSISTENT` dựa trên chi phí mất message; cấu hình QoS thực sự có hiệu lực; phân biệt tính bền của message với queue/topic, durable subscription, thời hạn lưu, ACK, transaction và tính đúng đắn nghiệp vụ.

## 1. Hai chế độ delivery mode là gì?

Jakarta Messaging định nghĩa **hai giá trị** của `jakarta.jms.DeliveryMode`:

~~~java
DeliveryMode.PERSISTENT      // int 2
DeliveryMode.NON_PERSISTENT  // int 1
~~~

`PERSISTENT` yêu cầu JMS provider thực hiện thêm các biện pháp để **bảo vệ message trước lỗi của provider/broker**, thường bao gồm ghi dữ liệu vào bộ nhớ bền vững. `NON_PERSISTENT` có overhead thấp hơn vì provider không bắt buộc lưu message vào stable storage và **có thể mất message khi provider gặp sự cố**.

Điều cần hiểu ngay:

- Hai mode là **chính sách chất lượng vận chuyển một message khi gửi**, không phải kiểu message (chúng dùng được với `TextMessage`, `BytesMessage`, `ObjectMessage`...) và cũng không phải loại destination.
- Chúng **không quyết định** “một consumer hay nhiều consumer” — đó là Queue/Topic và subscription.
- Chúng **không tự xác định** message còn sống bao lâu — đó là TTL/expiration, retention, broker capacity và hành vi acknowledgement.
- Chúng **không xác nhận** một bước nghiệp vụ như ghi DB, gọi API thanh toán hoặc gửi email đã hoàn thành.
- Chúng **không thay thế** xử lý trùng, transactions, retry và DLQ.
- Default delivery mode của JMS producer/message thường là **`PERSISTENT`**, nhưng cấu hình của JMS provider, producer hay JmsTemplate có thể thay đổi hoặc ghi đè giá trị mặc định.

**Quy tắc lựa chọn:** Nếu mất một message tạo ra thiệt hại nghiệp vụ hoặc trạng thái không thể tái dựng, chọn `PERSISTENT` cùng cơ chế retention/transaction thích hợp. Nếu message chỉ là dữ liệu nhất thời có thể bỏ lỡ hoặc tái tạo, `NON_PERSISTENT` là lựa chọn có thể cân nhắc để giảm overhead.

## 2. Bảng so sánh cốt lõi

| Khía cạnh | `PERSISTENT` | `NON_PERSISTENT` |
| --- | --- | --- |
| Giá trị hằng số | `DeliveryMode.PERSISTENT = 2` | `DeliveryMode.NON_PERSISTENT = 1` |
| Ý định của producer | Ưu tiên độ bền khi provider gặp lỗi | Ưu tiên hiệu năng nếu mất một số message chấp nhận được |
| Lưu vào stable storage | Yêu cầu provider sử dụng kỹ thuật lưu bền phù hợp để chống lỗi provider | Không bắt buộc ghi stable storage |
| Khi broker/process bị crash | Có mức bảo vệ cao hơn **nếu broker thực sự cấu hình persistence/retention đáp ứng yêu cầu** | Có thể mất những message chưa nhận hoặc chưa xử lý |
| Chi phí tài nguyên | Thường thêm journal/disk I/O, đồng bộ và replication tùy broker | Thường ít chi phí ghi bền hơn |
| Được gửi vào Queue? | Có | Có |
| Được publish vào Topic? | Có | Có |
| Consumer offline có tự được lưu? | Queue/durable subscription và retention phải phù hợp; không tự tạo subscription | Cũng phụ thuộc queue/subscription; không có bảo đảm sống qua provider failure |
| TTL/expiration có áp dụng? | Có | Có |
| Nếu đã ACK/commit thành công thì sao? | Provider có thể loại message khỏi backlog theo hợp đồng nhận | Tương tự |
| Có bảo đảm database side effect exactly once? | **Không** | **Không** |
| Có thể dùng cùng destination? | Có | Có |
| Cần kiểm thử broker restart/persistence policy? | **Có** | **Có**, để thấy rủi ro thực tế thay vì suy đoán |

**Lưu ý thuật ngữ:** đặc tả Jakarta Messaging diễn đạt các bảo đảm delivery cấp provider bằng các từ “once-and-only-once” đối với persistent và “at-most-once” đối với non-persistent khi xét lỗi provider. Đây là **bảo đảm chuyển giao thuộc tầng JMS và kèm điều kiện về chính sách lưu giữ**, **không tương đương** exactly-once thực hiện nghiệp vụ. Một thông điệp chưa được ACK, hoặc transaction bị rollback, có thể được **giao lại** để xử lý theo chính sách hợp lệ.

## 3. Bảo đảm thực sự của đặc tả — và giới hạn của nó

### 3.1. Định nghĩa ở tầng JMS provider

Phần *Message delivery mode* của Jakarta Messaging 3.1 quy định:

- **`NON_PERSISTENT`:** provider không buộc phải ghi ổn định; message có thể bị mất khi provider thất bại. Trong phạm vi bảo đảm delivery của provider, đây là lựa chọn *at-most-once*.
- **`PERSISTENT`:** provider phải tăng cường biện pháp bảo vệ để message không bị mất do lỗi provider thông thường. Đặc tả gọi đây là *once-and-only-once* ở tầng truyền tải, với điều kiện destination có chính sách lưu giữ thích hợp.
- **Không có mode nào** tự bảo đảm mọi subscriber dự kiến đều đã tồn tại, message chưa hết hạn, client đã hoàn thành side effect, database đã commit, hay broker còn vô hạn dung lượng.
- Provider có thể áp dụng hạn chế tài nguyên; lưu trữ đầy, chính sách broker, lỗi phương tiện lưu trữ nghiêm trọng hoặc sự cố ngoài phạm vi cấu hình có thể làm yêu cầu bảo đảm không đạt.

Không nên viết trong tài liệu thiết kế rằng “`PERSISTENT` luôn sống sót qua mọi hỏng hóc” hoặc “`NON_PERSISTENT` chắc chắn biến mất sau restart”. Cả hai kết luận quá mạnh.

### 3.2. Ba lớp thường bị đánh đồng

~~~text
PRODUCER                                  BROKER                            CONSUMER
   |                                         |                                  |
   | send(message, deliveryMode)             |                                  |
   +---------------------------------------->|                                  |
   |                                         | storage / retention / routing    |
   |                                         +--------------------------------->|
   |                                         |                                  | process DB/API
   |                                         |<------- ACK / COMMIT -------------+
   |                                         |  hoặc rollback / redelivery      |
   v                                         v                                  v

Lớp A: transport/send durability       Lớp B: retention/destination          Lớp C: business outcome
         (delivery mode)                 + subscription + TTL                 + ACK/transactions
~~~

- **Lớp A — Delivery mode:** producer yêu cầu provider vận chuyển và lưu message với mức độ bền nào.
- **Lớp B — Retention:** destination giữ các message đã nhận được bao lâu; queue có thể chờ consumer, durable topic subscription có thể giữ backlog, TTL có thể xóa message.
- **Lớp C — Completion:** consumer có thực hiện xong nghiệp vụ trước khi ACK/commit không? Nếu chưa xong hoặc commit thất bại thì redelivery và idempotency xử lý thế nào?

Muốn có quy trình tin cậy phải thiết kế **cả ba lớp**, không chỉ đặt mode `PERSISTENT`.

### 3.3. Những tình huống PERSISTENT vẫn không cứu được

1. **Topic non-durable không có subscriber lúc publish:** message không được tích lũy cho một subscriber chưa tồn tại; gửi persistent không biến non-durable thành durable.
2. **TTL đã hết:** message đủ điều kiện hết hạn và bị loại bỏ theo semantics/cấu hình, dù ban đầu persistent.
3. **ACK trước khi xử lý xong:** consumer xác nhận message rồi app crash khi ghi DB; broker tin đã hoàn tất, nên không còn message để nhận lại.
4. **Broker bị cấu hình không có persistence:** môi trường lab có thể nhận header mode 2 nhưng không thực sự bảo toàn journal qua restart.
5. **Retention/resource policy:** chính sách giới hạn dung lượng, purge, DLQ, administrative delete hoặc lỗi storage có thể khiến message không còn trong queue.
6. **Producer chưa thực sự hoàn tất send/commit:** một lời gọi gửi bất đồng bộ hoặc gửi trong transaction chưa commit không đồng nghĩa message đã được chấp nhận bền vững.
7. **Publisher/consumer không đồng bộ với DB:** persistence chỉ bảo vệ message mà broker đã nhận; không tạo atomic transaction giữa hệ thống dữ liệu và broker.

Do đó bài kiểm thử cần xác định **thời điểm send thành công, transaction commit, broker restart, subscription tồn tại, TTL và ACK**, thay vì chỉ nhìn một header.

## 4. Delivery mode không phải durable subscription

Trong JMS có hai khái niệm mang chữ “durable” nhưng khác trục:

| Khái niệm | Phạm vi áp dụng | Trả lời câu hỏi |
| --- | --- | --- |
| **`DeliveryMode.PERSISTENT`** | **Từng message** khi producer gửi | “Provider cần bảo vệ message tới mức nào khi gặp sự cố?” |
| **Durable Topic Subscription** | **Nhóm đăng ký** trên Topic | “Khi consumer của nhóm offline, subscription có giữ lại các message publish sau khi subscription đã được tạo không?” |

Ví dụ một Topic `orders.paid.events` có hai nhóm nhận:

~~~text
                 Topic: orders.paid.events
                /                         \
   billing-v1 (durable)                live-ui (non-durable)
       |                                    |
    Billing                              Dashboard
       |                                    |
   offline vẫn có                       offline có thể
   backlog hợp lệ                       bỏ lỡ event
~~~

- Nếu producer gửi **PERSISTENT** nhưng nhóm `live-ui` là **non-durable** và đã offline, nhóm đó không tự được nhận lại message lúc khởi động.
- Nếu nhóm `billing-v1` là **durable subscription đã tạo trước**, broker có thể giữ backlog cho Billing khi offline theo retention/TTL; persistent delivery mode tăng mức bảo vệ qua broker failure.
- Nếu producer dùng **NON_PERSISTENT** vào durable subscription, nhóm đó vẫn có thể nhận message khi đang online, và có thể thấy backlog khi offline trên broker còn sống, nhưng không được dựa vào tính sống sót qua broker failure.
- Việc **tạo durable subscription sau khi event đã phát** không mặc nhiên cho phép replay lịch sử đã qua.
- Subscription còn phải có danh tính, chính sách shared/unshared và broker support phù hợp nếu chạy nhiều replica.

**Tổ hợp cần nhớ:** “persistent message + durable subscription + broker persistence + retention đúng + transacted/ack consumer” giúp tăng độ tin cậy, nhưng **vẫn** cần idempotency và đối soát nghiệp vụ.

## 5. Queue và Topic: ví dụ chọn mode theo hợp đồng

### Tình huống A — Queue giao công việc không được bỏ lỡ

Checkout phát command `GenerateInvoice(invoiceId)` cho nhóm InvoiceWorker; worker có thể offline trong đợt triển khai.

**Lựa chọn thường phù hợp:**
- Queue riêng cho InvoiceWorker.
- `DeliveryMode.PERSISTENT`.
- Broker storage, quota, retention, backup/recovery phù hợp.
- Consumer dùng transacted session hoặc ACK sau khi xử lý an toàn.
- Idempotency key theo `invoiceId`; có retry và DLQ.

Lý do: nếu broker crash rồi mất command, hóa đơn có thể không bao giờ được tạo. Lưu ý nếu DB checkout commit rồi JVM crash **trước khi gửi** command, mode persistent không giải quyết được: dùng transactional outbox.

### Tình huống B — Telemetry thường xuyên, bỏ một mẫu chấp nhận được

Một sensor publish nhiệt độ mỗi vài giây; dashboard chỉ hiển thị số liệu hiện thời và có thể lấy lại từ lần đo kế tiếp.

**Lựa chọn có thể phù hợp:**
- `DeliveryMode.NON_PERSISTENT`.
- TTL ngắn để tránh hiển thị dữ liệu cũ.
- Non-durable topic subscriber nếu chỉ cần dữ liệu live.
- Metrics đo packet loss và data freshness; không dùng nếu thiếu một mẫu gây mất báo động an toàn.

Lý do: chi phí ghi bền mọi sample có thể không đáng, nhưng cần **chứng minh** app thật sự chấp nhận bỏ lỡ; hệ thống cảnh báo an toàn có thể cần thiết kế khác.

### Tình huống C — Event thanh toán cho nhiều nhóm

Payment service phát `PaymentCaptured`; Fulfillment, Accounting và Fraud phải xử lý riêng, kể cả lúc deploy.

**Lựa chọn thường phù hợp:** Topic, **mỗi nhóm một durable subscription**, event `PERSISTENT`, broker HA/persistence, idempotent consumer cho từng nhóm, schema version và DLQ riêng. Không coi `PERSISTENT` là lệnh “gửi cho mọi process”; cấu trúc subscription mới quy định ai nhận bản.

### Tình huống D — Thông báo người dùng có thể tái tạo

Notification service gửi “có email mới” cho web client; nếu client không online, lần mở trang kế tiếp sẽ tải danh sách từ database.

Có thể dùng `NON_PERSISTENT` trên live notifications, bởi **nguồn sự thật là DB**. Nhưng event `EmailReceived` dùng để cập nhật audit/billing có thể cần persistent trên một luồng khác. Quyết định phải dựa trên hợp đồng của *từng message*, không đặt một mode chung vô điều kiện cho cả hệ thống.

### Tình huống E — Hệ thống vận hành phải duy trì thứ tự

Nếu một destination trộn message persistent và non-persistent, **không suy ra thứ tự tuyệt đối giữa hai mode**. Đặc tả cho phép một message NON_PERSISTENT gửi sau được nhận trước một message PERSISTENT gửi trước, dù các điều kiện khác như priority cũng ảnh hưởng. Với giao dịch phụ thuộc thứ tự, cần contract ordering riêng, kiểm soát concurrency/producer sessions và không mặc định mixing modes giữ FIFO toàn cục.

## 6. API Jakarta Messaging: đặt mode ở producer

### 6.1. Classic API — MessageProducer

Đối với `jakarta.jms.MessageProducer`:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;

// Mảnh Java 17+; session đã được tạo và destination đã được định nghĩa.
MessageProducer producer = session.createProducer(destination);

// Những message sau sẽ dùng NON_PERSISTENT trừ khi send override:
producer.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
Message msg = session.createTextMessage("sample");
producer.send(msg);
~~~

Đây là **mảnh code**, cần `destination`, `session`, broker/ConnectionFactory và lifecycle cleanup. Không copy nó thành file Java độc lập.

Có thể đặt mode **cho từng lần send** thông qua overload classic API:

~~~java
producer.send(
    msg,
    DeliveryMode.PERSISTENT,
    Message.DEFAULT_PRIORITY,
    Message.DEFAULT_TIME_TO_LIVE);
~~~

Overload bốn tham số cho phép ghi đè delivery mode, priority và TTL **của lần send đó**. Không dùng cùng một `MessageProducer` bị chia sẻ không an toàn giữa các thread và thay mode tùy ý theo request; nên dùng công cụ Spring/template hoặc producer được quản lý đúng lifecycle.

### 6.2. Simplified API — JMSContext/JMSProducer

Java 17+ với Jakarta Messaging 3.1, có provider hỗ trợ JMSContext:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public final class DirectDeliveryModeExample {
    private DirectDeliveryModeExample() {}

    public static void sendStatus(
            ConnectionFactory factory, String payload) {
        try (JMSContext context = factory.createContext()) {
            Queue queue = context.createQueue("telemetry.live");
            context.createProducer()
                    .setDeliveryMode(DeliveryMode.NON_PERSISTENT)
                    .send(queue, payload);
        }
    }
}
~~~

Lưu tại `DirectDeliveryModeExample.java`. Đây là **class Java 17+ hợp lệ khi classpath có Jakarta Messaging và client/provider**; không có `main` nên không tự chạy, cần một `ConnectionFactory` đã cấu hình và broker hoạt động. `JMSContext` được đóng khi thoát try-with-resources; `JMSProducer` không có `close()` riêng.

Để chuyển yêu cầu sang persistent, thay `DeliveryMode.NON_PERSISTENT` bằng `DeliveryMode.PERSISTENT`; việc thay một hằng số không tự cấu hình storage, DLQ hay retention.

### 6.3. Đừng sửa header để mong thay chính sách gửi

Những lời gọi như:

~~~java
message.setJMSDeliveryMode(DeliveryMode.PERSISTENT);
~~~

chỉ tác động header của một `Message` object trước send; **provider bỏ qua giá trị header do client gán ở thời điểm gửi và thay bằng mode của lần send/producer**. Cách đúng là `producer.setDeliveryMode(...)`, overload `send(..., deliveryMode, priority, ttl)` hoặc cấu hình QoS đúng trong Spring.

Sau khi send/receive, `message.getJMSDeliveryMode()` cho biết mode header do provider gắn; nó dùng để **quan sát**, không phải cách thiết lập chính sách broker khi consumer đọc message.

### 6.4. Các mặc định khác

Ngoài delivery mode, một `MessageProducer` còn có:

- Priority mặc định thường là **4** (0 thấp nhất, 9 cao nhất).
- TTL mặc định thường là **0** (không đặt thời điểm hết hạn từ client).
- Delivery delay mặc định là **0**.
- Các chế độ delivery mode, TTL, priority có thể được cấu hình trực tiếp trên producer hoặc theo send overload.

Default persistent **không đồng nghĩa** với “không bao giờ hết hạn” nếu broker áp chính sách expiry/retention ở phía server.

## 7. Spring JmsTemplate: bẫy setDeliveryMode nhưng không bật QoS

Với Spring Framework 6.x, `org.springframework.jms.core.JmsTemplate` có các setter:

~~~java
jmsTemplate.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
jmsTemplate.setDeliveryPersistent(false);
jmsTemplate.setExplicitQosEnabled(true);
~~~

**Phần then chốt:** `setDeliveryMode(...)` hoặc `setDeliveryPersistent(false)` **một mình không đủ**. Theo Javadoc của Spring, chỉ khi `isExplicitQosEnabled()` là `true` thì template mới truyền các thuộc tính QoS tường minh vào lời gọi send. Nếu không, provider có thể áp dụng default/administrative delivery mode.

### 7.1. Ví dụ cấu hình hai JmsTemplate khác nhau

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class DeliveryModeConfiguration {

    @Bean("persistentJmsTemplate")
    JmsTemplate persistentJmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        return template;
    }

    @Bean("volatileJmsTemplate")
    JmsTemplate volatileJmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.NON_PERSISTENT);
        return template;
    }
}
~~~

Đây là class Spring hoàn chỉnh nếu project có dependencies phù hợp. Có thể inject bằng `@Qualifier("persistentJmsTemplate")` hoặc `@Qualifier("volatileJmsTemplate")` vào service. Các factory cùng dùng `ConnectionFactory` được Spring quản lý, nhưng message do từng template phát có mode yêu cầu khác nhau. Không cần tự đóng `Session`/`Connection` bên trong `convertAndSend`.

**Lưu ý quan trọng:** Bật `explicitQosEnabled` còn khiến template gửi tường minh **priority** và **TTL** theo giá trị cấu hình của template, thay vì dùng mặc định do quản trị broker đặt. Đừng bật nó mà không kiểm tra priority/TTL đang mong đợi. Nếu hệ thống có policy QoS riêng của broker, hãy đối chiếu và quyết định rõ.

### 7.2. Gửi message với từng mode

~~~java
// Mảnh code trong một Spring @Service:
persistentJmsTemplate.convertAndSend(
        "invoices.commands", "invoice-2026-001");

volatileJmsTemplate.convertAndSend(
        "metrics.live", "cpu=63");
~~~

Đây là **hai message ở hai destination khác nhau**, không phải hai lần gửi cùng một công việc. Với `SimpleMessageConverter`, dữ liệu `String` sẽ thành `TextMessage`, nhưng **body type độc lập với delivery mode**.

### 7.3. Spring Boot 3.5 cấu hình JmsTemplate tự động

Trong Spring Boot 3.5, các property cấu hình bean template do Boot quản lý bao gồm:

~~~properties
# Ví dụ cho một Spring Boot JmsTemplate auto-configured:
spring.jms.template.delivery-mode=non_persistent
spring.jms.template.receive-timeout=2s
~~~

Đối với Boot 3.5, khi đặt `spring.jms.template.delivery-mode`, Boot **tự bật explicit QoS** cho JmsTemplate auto-configured. Nếu cấu hình một bean `JmsTemplate` riêng bằng `new` hoặc một factory tùy chỉnh, các property của Boot **không mặc nhiên** tác động lên bean đó; phải cấu hình trực tiếp hoặc dùng configurer tương thích phiên bản.

**Không nên đặt global non-persistent** cho cả app nếu trong cùng app vừa phát job quan trọng vừa phát metrics bỏ lỡ được. Dùng hai template có tên và hợp đồng riêng, hoặc thao tác send được cấu hình QoS per message qua API thích hợp.

### 7.4. Lời gọi được áp dụng ở đâu?

`JmsTemplate.convertAndSend(...)`:
1. Lấy Connection/Session từ factory.
2. Chuyển Java object qua `MessageConverter` thành JMS `Message`.
3. Tạo/thuê `MessageProducer`.
4. **Gửi** với QoS tường minh nếu `explicitQosEnabled=true`; nếu false dùng send mặc định của producer.
5. Thực hiện cleanup/transaction boundary theo Spring/broker config.

Nhờ vậy bạn có thể giữ nguyên message schema và thay QoS theo độ quan trọng của từng loại công việc mà không tự thao tác chi tiết low-level JMS.

## 8. Lab Spring Boot 3.5 + Artemis: kiểm tra JMSDeliveryMode thực nhận

Lab này chứng minh **header `JMSDeliveryMode` đã gửi đúng**. Nó **không** chứng minh persistent sống qua restart, bởi broker nhúng bên dưới được cấu hình **không lưu persistent data** và tự dừng cùng app. Bài thử durability thật sự ở phần 9.

### 8.1. Khởi tạo project

Tạo dự án tại https://start.spring.io/ với:

- Project: Maven / Java.
- Spring Boot **3.5.x**, Java **17**.
- Group `com.example`; artifact `delivery-mode-demo`; package `com.example.deliverymodedemo`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Thêm vào `pom.xml` (đang dùng parent/BOM của Spring Boot để quản lý version):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=delivery-mode-demo
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=qos.persisted,qos.volatile
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Hai queue demo độc lập để bài lab không cần cạnh tranh consumer hoặc selector. `persistent=false` là **bảo đảm lab không dùng storage bền**, nhằm dạy rằng **header mode 2 không đủ để kiểm chứng durability của broker**.

### 8.2. Java class hoàn chỉnh

Tạo `src/main/java/com/example/deliverymodedemo/DeliveryModeDemoApplication.java`:

~~~java
package com.example.deliverymodedemo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class DeliveryModeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryModeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner compareDeliveryModes(ConnectionFactory factory) {
        return args -> {
            JmsTemplate durableSender = createSender(
                    factory, DeliveryMode.PERSISTENT);
            JmsTemplate fastSender = createSender(
                    factory, DeliveryMode.NON_PERSISTENT);

            JmsTemplate receiver = new JmsTemplate(factory);
            receiver.setReceiveTimeout(2_000L);

            durableSender.convertAndSend("qos.persisted", "invoice-42");
            fastSender.convertAndSend("qos.volatile", "temperature-24");

            Message durable = receiver.receive("qos.persisted");
            Message fast = receiver.receive("qos.volatile");

            if (!(durable instanceof TextMessage durableText)) {
                throw new IllegalStateException(
                        "Missing persistent TextMessage");
            }
            if (!(fast instanceof TextMessage fastText)) {
                throw new IllegalStateException(
                        "Missing non-persistent TextMessage");
            }

            System.out.println("PERSISTENT mode="
                    + durableText.getJMSDeliveryMode()
                    + " body=" + durableText.getText());
            System.out.println("NON_PERSISTENT mode="
                    + fastText.getJMSDeliveryMode()
                    + " body=" + fastText.getText());
        };
    }

    private static JmsTemplate createSender(
            ConnectionFactory factory, int mode) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setPubSubDomain(false);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(mode);
        return template;
    }
}
~~~

Đây là file Java 17+ đầy đủ; lớp cần Spring Boot 3.5, Spring JMS, Jakarta Messaging và Artemis embedded như phần 8.1. `ApplicationRunner` không có `@JmsListener`, nên không cần `@EnableJms`. Với cấu hình này, `TextMessage.getText()` và `getJMSDeliveryMode()` có thể được đọc sau khi `JmsTemplate.receive` trả về.

Chạy từ thư mục dự án:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Bỏ qua log khởi động của Spring/Artemis, **stdout nghiệp vụ dự kiến**:

~~~text
PERSISTENT mode=2 body=invoice-42
NON_PERSISTENT mode=1 body=temperature-24
~~~

Hai dòng trên xuất hiện theo thứ tự trong một `ApplicationRunner` nếu broker nhúng chạy, hai queue ban đầu trống và không có consumer cạnh tranh. Nếu template không bật `explicitQosEnabled`, lần gửi từ `fastSender` **có thể** dùng mode mặc định 2 thay vì mode 1, cho thấy việc gọi setter một mình không đủ.

**Điều lab xác thực:** mode do JMS provider gắn lên hai message và được nhận lại đúng. **Điều lab không xác thực:** chịu tải, độ trễ fsync, provider failover, broker restart, non-persistent loss hay exactly-once nghiệp vụ. Không dùng số dòng log để suy ra chất lượng lưu trữ.

### 8.3. Vì sao không dùng cùng queue để đối chiếu “bên nào nhanh”?

Nếu gửi hai message vào cùng queue rồi có consumer cạnh tranh, thứ tự/overhead không được xác định từ một lần chạy nhỏ. Kiểm thử hiệu năng cần tạo tải đồng nhất, chia nhóm riêng, quan sát throughput/latency/storage trên **broker thật** và đủ mẫu; `PERSISTENT` thường đắt hơn nhưng không thể công bố một con số tốc độ chung cho mọi provider.

## 9. Lab độ bền thật: broker ngoài, restart và retention

Để kiểm chứng behavior sau restart, **không dùng** embedded broker bị tắt cùng ứng dụng. Chuẩn bị một Artemis broker **độc lập** với journal/persistence có hiệu lực, đường dữ liệu được giữ nguyên giữa các lần khởi động, queue durable và quyền publish/consume phù hợp.

Quy trình kiểm thử ở môi trường tách biệt:

1. Tạo hai queue riêng `test.persisted` và `test.volatile`; không có consumer nhận khi thực hiện gửi. Đặt retention/TTL đủ lớn, không bật policy tự xóa để kết quả không bị nhiễu.
2. Gửi cùng số lượng message có ID duy nhất vào queue thứ nhất với mode `PERSISTENT`, queue thứ hai với mode `NON_PERSISTENT`; log kết quả send thành công và transaction commit nếu có.
3. Đọc broker metrics để xác nhận message count và message durable trước khi restart. Giữ nguyên storage volume và cấu hình.
4. Dừng broker theo cách **có kiểm soát**; khởi động lại. Kiểm tra số message còn trong cả hai queue. Sau đó lặp thí nghiệm ở staging với **process crash** (không phải production) nếu hạ tầng và quyền vận hành cho phép.
5. Khởi động consumer có ACK/transaction đúng, đối chiếu ID nhận, message expired, DLQ và backlog. Ghi nhận số lần delivery attempt khác với số business outcome thành công.
6. Lặp lại với broker HA/replication nếu production có failover; đừng suy từ một broker đơn sang một cluster.

**Kỳ vọng phải diễn đạt đúng:** Trong broker được cấu hình bền phù hợp, persistent messages chưa ack/hết hạn được kỳ vọng sống qua lỗi provider nằm trong phạm vi bảo đảm. Non-persistent messages **có thể** không sống qua crash/restart, nhưng một số provider/policy có thể giữ lại chúng; **một lần thấy non-persistent còn tồn tại không tạo ra bảo đảm tiêu chuẩn**.

Nếu broker đang chạy với `persistence-enabled=false`, cả hai mode có thể bị mất dữ liệu khi restart — đó là **giới hạn cấu hình môi trường**, không thể dùng để kết luận hai hằng số `DeliveryMode` tương đương trong JMS.

## 10. Spring Boot/Artemis: các yếu tố hệ thống ảnh hưởng độ bền

### 10.1. Journal, store và đồng bộ dữ liệu

Apache ActiveMQ Artemis có journal lưu message và bindings, hoặc các tùy chọn lưu trữ khác. Khi cấu hình persistent, broker thường ghi trạng thái quan trọng vào stable storage. Nhưng độ bền quan sát được còn phụ thuộc:

- Storage volume có giữ nguyên sau restart/Pod recreation không?
- Journaling/file sync/replication được bật và điều chỉnh thế nào?
- Disk flush/batching có ảnh hưởng độ trễ send/commit không?
- Broker dùng paging khi tải cao; paging-to-disk **không tương đương** cam kết durable của mọi non-persistent message.
- Có HA/failover hay broker đơn? Các sự cố node, volume, network split có chính sách khác nhau.
- Destination có expiry address/DLQ, max-size, address-full-policy, auto-delete?
- Transaction có được commit trước khi producer công bố nghiệp vụ gửi thành công?

**PERSISTENT là yêu cầu chất lượng gửi**, không phải lời khẳng định rằng broker bất kỳ đã có persistent disk/replicas đầy đủ. Cần kiểm tra cấu hình server và thử nghiệm dưới fault scenarios.

### 10.2. NON_PERSISTENT không đồng nghĩa không bao giờ xuống đĩa

Provider có thể paging, buffer, snapshot hoặc lưu dữ liệu nhất thời theo chính sách. Vì vậy dữ liệu non-persistent **có thể** xuất hiện trong storage ở một hoàn cảnh cụ thể, nhưng không nhận được cam kết bền vững của persistent mode. Đừng tìm “kiểm chứng” bằng cách chỉ quan sát không có file journal mới.

### 10.3. Ghi bền không đồng nghĩa ACK của consumer

Message được producer gửi persistent và nằm an toàn trên broker vẫn có thể:
- Chưa được consumer nào nhận.
- Đã được nhận nhưng consumer chưa ACK.
- Đang chờ retry vì consumer rollback.
- Đã hết TTL hoặc bị chuyển đến expiry/DLQ.
- Đã ACK thành công nhưng business side effect bị lỗi do thiết kế transaction.

Đó là lý do phải giám sát trạng thái delivery/ack và nghiệp vụ độc lập.

## 11. Acknowledgement, transaction, redelivery và “exactly once”

### 11.1. Minh họa cửa sổ lỗi

~~~text
Producer ----- send(PERSISTENT) -----> Broker stores message
                                          |
                                          v
                                  Consumer receives
                                          |
                                    DB COMMIT OK
                                          |
                                  [JVM CRASH HERE]
                                          |
                               JMS ACK chưa thực hiện
                                          |
                               Broker may REDLIVER
                                          |
                                  DB xử lý lần nữa?
~~~

Nếu message chưa được ACK/commit ở phía broker, việc giao lại sau restart/failover là hành vi cần được thiết kế chấp nhận. Chính vì vậy hai khái niệm cần tách:

- **Provider-level delivery guarantee:** provider chịu trách nhiệm vận chuyển và cung cấp message theo hợp đồng JMS, có điều kiện về failure và retention.
- **Business exactly once:** hiệu ứng như “trừ tiền 100.000 VND” hoặc “gửi một email” chỉ xảy ra một lần. Điều này **không được bảo đảm** chỉ bằng `PERSISTENT`.

Cách làm đúng trong hệ thống cần tin cậy là kết hợp persistent publish, transaction/ACK đúng thời điểm, **idempotent consumer** và kiểm soát side effects.

### 11.2. Transacted JMS Session

Trong listener Spring:

~~~java
// Mảnh Bean method của @Configuration:
@Bean("businessListenerFactory")
DefaultJmsListenerContainerFactory businessListenerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Cần imports `jakarta.jms.ConnectionFactory`, Spring `@Bean` và `DefaultJmsListenerContainerFactory`. Đây không phải file class đầy đủ. Với `sessionTransacted=true`, khi listener xử lý thành công, session transaction được commit theo lifecycle của container; nếu handler ném exception, rollback có thể khiến message được giao lại theo provider policy. Nếu handler ghi DB ngoài cùng JMS transaction, **JMS local transaction không tự bao gồm DB transaction**.

Để hạn chế side effect lặp:
- Dùng `eventId`/`commandId`/business key bất biến.
- Lưu trạng thái đã xử lý trong bảng inbox/dedup với unique constraint.
- Chỉ tạo side effect khi key chưa được xử lý; xác định transactional boundary với DB.
- Nếu publish sau DB commit, dùng transactional outbox để tránh lỗi “DB có dữ liệu nhưng message chưa gửi”.
- Có retry giới hạn, backoff, DLQ và quy trình replay/đối soát.
- Thiết kế consumer chịu được các lần delivery attempt khác nhau.

### 11.3. PERSISTENT không tự giữ được message nếu consumer ACK sớm

Nếu listener xác nhận trước khi nghiệp vụ thành công, broker có thể loại message khỏi backlog. Sau đó code lỗi, message không tự quay lại. Hãy xác định **ack mode** và **loại listener container**; đặc biệt với cấu hình `AUTO_ACKNOWLEDGE`, behavior giữa API trực tiếp và Spring listener container có thể khác. Đối với công việc quan trọng, transacted session thường là điểm xuất phát an toàn hơn.

### 11.4. Producer commit cũng quan trọng

Nếu producer gửi message persistent trong local JMS transaction, ứng dụng phải `commit()` trước khi coi message đã được publish. Close session chưa commit sẽ rollback, dù delivery mode là persistent. Khi vừa ghi database vừa gửi JMS, không mặc định cả hai thao tác được commit atomically; cần outbox hoặc giải pháp giao dịch phối hợp đã được thẩm định.

## 12. TTL, expiration, priority và thứ tự khi trộn hai mode

### 12.1. TTL có thể “thắng” persistence

`setTimeToLive(10_000)` nghĩa là message có thể hết hạn sau khoảng 10 giây kể từ thời điểm send, theo quy tắc `JMSExpiration`. Message persistent **không phải vật thể lưu vĩnh viễn**. Một queue có consumer offline 30 phút và TTL 10 giây không còn nghĩa vụ giao message đã hết hạn khi consumer quay lại.

~~~java
// Mảnh cấu hình, các setters có hiệu lực khi explicit QoS được bật.
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setTimeToLive(10_000L);
jmsTemplate.setPriority(4);
~~~

Nhớ rằng bật explicit QoS gửi **cả ba** thông số priority/TTL/mode với giá trị của template, có thể ghi đè admin defaults. TTL nên là kết quả của business SLA/retention, không phải con số sao chép từ một tutorial.

### 12.2. Delivery delay là chuyện khác

`deliveryDelay` chỉ thời điểm sớm nhất provider có thể giao message đến consumer; nó không đảm bảo message có mặt trong broker từ quá khứ không tồn tại, và không đồng nghĩa retention. Nếu đặt delay 30 giây nhưng TTL 10 giây, cần kiểm tra tương tác timestamp/expiry và broker policy thay vì khẳng định mọi subscriber sẽ nhận.

### 12.3. Priority và trộn mode có thể ảnh hưởng ordering

Với cùng destination, giữa các message khác priority, delivery time hoặc mode, JMS không hứa FIFO tuyệt đối. Đặc biệt **đơn đặt hàng cần thứ tự** không nên dựa vào việc “tôi send persistent trước rồi non-persistent sau” để suy ra chắc chắn receive theo đúng thứ tự đó.

Nếu cần ordering:
- Định nghĩa phạm vi theo `accountId`/`orderId`, không chỉ theo tên queue.
- Hạn chế concurrency hoặc dùng message grouping/partitioning mà broker thực sự hỗ trợ.
- Tránh trộn mode có semantics khác nhau trong cùng một luồng nghiệp vụ phụ thuộc thứ tự.
- Kiểm thử failover, rollback/redelivery và priority.

### 12.4. JMS selector có thể quan sát delivery mode

JMS selector xử lý `JMSDeliveryMode` dưới dạng chuỗi:

~~~sql
JMSDeliveryMode = 'PERSISTENT'
~~~

Đây là cú pháp selector JMS, không phải SQL query DB. Consumer có thể lọc theo chế độ delivery mode, nhưng **selector không thay thế broker ACL hoặc định nghĩa hợp đồng message**. Nếu muốn route theo loại nghiệp vụ, thường tốt hơn đặt application property như `kind` hoặc dùng destination phù hợp.

## 13. Hiệu năng: đừng đánh đổi bảo đảm bằng niềm tin

### 13.1. Vì sao persistent thường có overhead cao hơn?

Broker có thể phải:
- Ghi vào journal/store và quản lý sync/batch.
- Đồng bộ message với replica hoặc đợi quorum tùy kiến trúc.
- Lưu metadata để khôi phục hàng đợi và trạng thái transaction.
- Ghi nhận ACK/xóa message để storage không tăng vô hạn.
- Tổ chức paging/large-message files khi backlog hoặc payload lớn.

`NON_PERSISTENT` không bắt buộc các bước ghi bền đó, nên throughput có thể cao hơn và latency thấp hơn. **Không có tỷ lệ nhanh hơn cố định**: chi phí còn phụ thuộc payload size, I/O, cấu hình broker, batching, HA, mạng và consumer speed.

### 13.2. Cách benchmark có ý nghĩa

Để đánh giá việc chọn mode, chạy cùng phần mềm broker, cùng cấu hình storage, cùng kích thước payload, cùng tải producer/consumer và cùng cơ chế ACK:

1. Dùng queue riêng cho từng mode hoặc chạy tuần tự để tránh cạnh tranh storage/CPU.
2. Warm up và giữ số message đủ lớn.
3. Đo throughput (msg/s), producer send latency p50/p95/p99, consumer end-to-end latency, CPU, disk IOPS/fsync và backlog.
4. Lặp khi có tải cao, consumer offline, retry và broker restart trong staging.
5. Quan sát DLQ, expiry, loss và doanh thu/độ trễ nghiệp vụ, không chỉ tốc độ.
6. Ghi rõ broker version, storage, journal sync, HA, transaction và persistence mode để người khác tái lập.

Nếu message không được phép mất, **không chọn NON_PERSISTENT chỉ vì benchmark nhanh hơn**; hãy xem tối ưu batching, cấu trúc event, volume/IOPS, producer/consumer concurrency và thiết kế workload.

## 14. Hợp đồng chất lượng gửi cần ghi gì?

Một message contract tốt nên ghi rõ:

| Trường | Ví dụ hoặc câu hỏi |
| --- | --- |
| `messageType` | `GenerateInvoice` hay `TelemetrySample`? Command/event có ý nghĩa gì? |
| `destination` + `domain` | Queue `invoices.commands` hay Topic `telemetry.live`? |
| **Delivery mode** | `PERSISTENT`/`NON_PERSISTENT` theo yêu cầu nghiệp vụ nào? |
| **Producer send/commit** | Ai publish, khi nào tính thành công? Có transaction hay outbox không? |
| **Consumer subscription** | Queue/group nào nhận? Topic subscription có durable/shared không? |
| **TTL và retention** | Mất hiệu lực khi nào? Broker giữ tối đa bao lâu? |
| **ACK/transaction** | Điều kiện ACK/commit và rollback là gì? DB có transaction riêng không? |
| **Idempotency key** | `eventId`, `requestId`, khóa nghiệp vụ nào ngăn side effect trùng? |
| **Retry/DLQ** | Số lần retry, delay, poison-message policy, quy trình replay/đối soát? |
| **Availability** | Broker persistence, volume, replication/failover, RPO/RTO như thế nào? |
| **Ordering** | Có yêu cầu thứ tự theo khóa không? Có trộn mode/priority? |
| **Observability** | Message count theo mode, ack, DLQ, expiry, age, send errors, p99 latency? |
| **Versioning** | Consumer version cũ nhận được payload đang lưu lâu trên broker chứ? |

### Contract ví dụ: hóa đơn quan trọng

~~~yaml
kind: command
type: GenerateInvoice
destination: invoices.commands
domain: queue
deliveryMode: PERSISTENT
eventId: "invoice-request-id"
sourceOfTruth: checkout-db
publisherSafety: transactional-outbox
subscriberGroup: invoice-workers
acknowledge: transacted-after-success
idempotency: unique business key invoice-request-id
ttl: business-reviewed, not a short arbitrary default
failure: bounded retries with DLQ and reconciliation
storage: broker persistence/retention/HA verified
~~~

### Contract ví dụ: số liệu realtime bỏ lỡ được

~~~yaml
kind: event
type: LiveCpuSample
destination: telemetry.live
domain: topic
deliveryMode: NON_PERSISTENT
consumer: live dashboard, no guaranteed offline replay
ttl: short, determined by UI freshness SLA
lossTolerance: missing occasional samples is acceptable
historicalSource: metrics database (not live topic)
observability: sample-age, publish-failures, drop-rate
~~~

Đây là **file YAML mô tả hợp đồng để thảo luận**, không phải `application.yml` chạy tự động. Mỗi tổ chức cần hiện thực policy bằng mã Spring, cấu hình broker, quyền truy cập và các bài kiểm thử tích hợp.

## 15. Các sai lầm thường gặp và cách sửa

1. **Chỉ gọi `setDeliveryMode(NON_PERSISTENT)` trên `JmsTemplate`.** Nếu không bật explicit QoS, setter có thể bị bỏ qua. Bật `setExplicitQosEnabled(true)` hoặc dùng property Boot có cơ chế QoS tương ứng.
2. **Sửa `message.setJMSDeliveryMode(...)` trước khi send.** JMS provider bỏ qua giá trị header do caller sửa khi gửi; đặt mode trên producer hoặc send operation.
3. **Gọi NON_PERSISTENT là “không bao giờ ghi disk”.** Provider vẫn có thể paging/store tạm; chỉ không có nghĩa vụ durability của persistent.
4. **Gọi PERSISTENT là “không bao giờ mất”.** TTL, retention, resource limits, subscription và storage failure vẫn áp dụng.
5. **Tin PERSISTENT = exactly-once nghiệp vụ.** Broker delivery và DB side effect là hai tầng khác nhau; vẫn cần idempotency.
6. **Cho rằng durable Topic subscription và persistent mode là một.** Một cái thuộc subscription, cái kia thuộc message.
7. **Gửi persistent Topic khi subscriber chưa đăng ký rồi đòi lấy toàn bộ lịch sử.** Subscription không tồn tại không tự tích backlog cho tương lai.
8. **Test persistence bằng embedded broker tắt storage.** Mode header vẫn có giá trị nhưng không chứng minh sống qua restart.
9. **Dùng NON_PERSISTENT cho payment/invoice mà không có đường tái tạo.** Nếu rớt message sẽ thiếu business outcome; chọn mode theo loss budget.
10. **Mặc định queue luôn FIFO tuyệt đối.** Priority, delay, concurrency, redelivery và trộn mode có thể thay đổi thứ tự thực tế.
11. **Bật explicit QoS rồi bỏ quên TTL/priority.** Nó tác động cả ba thuộc tính; đối chiếu admin defaults.
12. **Nhầm message được send với transaction đã commit.** Một JMS session transacted có thể rollback sau send.
13. **ACK message trước khi DB xử lý xong.** Broker tin đã hoàn tất, có nguy cơ mất hiệu ứng nghiệp vụ.
14. **Không đo quota/disk/expiry/DLQ.** Persistent backlog có thể làm storage đầy; cần alert và giới hạn có chủ đích.
15. **Lưu event dài hạn mà không kiểm soát schema version.** Backlog bền khiến consumer mới phải đọc được event cũ.
16. **Không thử lỗi broker/restart.** Log "sent successfully" chỉ một lát sau publish không chứng minh provider behavior dưới fault.

## 16. Checklist kiểm thử trước khi đưa production

- **Mặc định**: Với config thực tế, message gửi không khai báo mode nhận `getJMSDeliveryMode()` là bao nhiêu?
- **Explicit QoS**: Sau `setExplicitQosEnabled(true)`, header của message là 1 hay 2 đúng như mong đợi?
- **Template khác nhau**: Có chắc business publisher dùng persistent template còn telemetry publisher dùng non-persistent?
- **TTL/priority**: Bật explicit QoS có vô tình đổi TTL/priority trong broker policy không?
- **Broker persistence**: Journal/store, volume và fsync/replication thực tế được bật đúng?
- **Topic**: Subscription cần offline delivery đã được tạo durable từ trước chưa?
- **Failure**: Trong staging, broker restart/crash với message chưa ACK; số message còn được đối chiếu?
- **Transactions**: JMS send commit và receive ACK/commit xảy ra lúc nào?
- **Consumer crash**: Sau business side effect nhưng trước JMS ACK, có duplicate không? Handler idempotent chứ?
- **Resource limits**: Khi queue lớn hoặc disk đầy, broker áp policy gì? Có cảnh báo hay mất message?
- **Monitoring**: Ghi lại sent/confirmed count, backlog, redelivery, expiry, DLQ, latency và storage?
- **Ordering**: Nếu trộn hai mode trên cùng queue, test thứ tự với priority/concurrency thực tế?
- **Deployment**: Consumer version mới còn đọc được message persistent của version cũ?
- **Runbook**: Khi publisher timeout hoặc broker failover, hệ thống đối soát duplicate/loss như thế nào?

## 17. Bài tập củng cố

1. Cho queue `invoices.commands` và live topic `telemetry.live`: hãy chọn delivery mode và giải thích bằng **chi phí mất message** chứ không bằng tên destination.
2. Tạo hai `JmsTemplate` như phần 7. Gỡ `setExplicitQosEnabled(true)` ở template NON_PERSISTENT rồi chạy lab; kiểm tra header, giải thích vì sao setter không đủ.
3. Broker có persistence nhưng Topic consumer không có durable subscription và offline lúc publish. Một message PERSISTENT có được giao lại khi consumer đến sau không? Giải thích.
4. Một queue tồn 20 phút, message có TTL 30 giây. Vì sao `PERSISTENT` không làm message sống đến khi consumer online?
5. Chạy broker độc lập có storage và hai queue test. Gửi 100 messages mode persistent/volatile, restart broker trong staging rồi so sánh số ID còn lại. Vì sao kết quả non-persistent còn nguyên một lần không biến thành cam kết?
6. Consumer ghi DB thành công rồi crash trước JMS commit. Hãy mô tả tình huống redelivery, bảng inbox idempotency và lý do mode persistent không bảo đảm một side effect duy nhất.
7. Đọc metadata một message nhận bằng `getJMSDeliveryMode()`. Giá trị 2/1 chứng minh điều gì và **chưa** chứng minh điều gì về broker?
8. Thiết kế bộ đo benchmark trên Artemis: những biến nào phải cố định, cần metrics nào ngoài msg/s, và vì sao không nêu tỉ lệ performance chung?
9. Producer cùng session gửi message PERSISTENT rồi NON_PERSISTENT vào cùng destination. Có nên yêu cầu consumer xử lý toàn cục đúng thứ tự gửi không? Vì sao?
10. Viết checklist go-live cho payment event Topic với nhiều durable subscriptions: QoS, retention, ACL, outbox, idempotency, retry/DLQ, schema và test failover.

## Tài liệu tham khảo chính thức

- **Jakarta Messaging 3.1 Specification**, đặc biệt `7.7 Message delivery mode`, `9.1 Reliability`, `3.4.2 JMSDeliveryMode` và `6.2.9.2 Order of message sends`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- **Jakarta Messaging DeliveryMode API**, giá trị hằng số và giới hạn của retention: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/deliverymode
- **Jakarta EE Tutorial**, message delivery modes, mặc định và trade-off: https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html
- **Spring Framework 6.2 JmsTemplate Javadoc**, `setDeliveryMode`, `setDeliveryPersistent` và `setExplicitQosEnabled`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- **Spring Framework 6.2 JMS sending**, Quality of Service: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- **Spring Boot 3.5 Common Application Properties**, `spring.jms.template.delivery-mode` và QoS: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- **Apache ActiveMQ Artemis — Persistence**, journal, storage và policy: https://artemis.apache.org/components/artemis/documentation/latest/persistence
