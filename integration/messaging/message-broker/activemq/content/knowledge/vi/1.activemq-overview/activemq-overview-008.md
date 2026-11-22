# Kiến thức nền và trình tự học: từ một broker đến hệ thống nhiều broker

> **Phạm vi:** Apache ActiveMQ Classic và Apache ActiveMQ Artemis trong tích hợp bất đồng bộ bằng Java/JMS. Bài này xây dựng mô hình tư duy, thứ tự thực hành và tiêu chí kiểm chứng khi đi từ một broker đơn lẻ đến hệ thống có dự phòng và nhiều broker. Các bài cấu hình chuyên sâu có thể triển khai sau dựa trên nền tảng này.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

1. Giải thích vai trò của **producer, broker, destination, consumer** và phân biệt **queue** với **topic**.
2. Hiểu ActiveMQ Classic và Artemis cùng hỗ trợ giao tiếp bất đồng bộ nhưng khác nhau ở mô hình định tuyến, cấu hình lưu trữ và kết nối nhiều broker.
3. Tạo luồng Java/JMS đơn giản, rồi chứng minh được điều gì xảy ra khi consumer lỗi, rollback, broker khởi động lại hoặc message bị gửi đến dead-letter queue (DLQ).
4. Phân biệt **độ bền dữ liệu (durability)**, **khả dụng cao (HA)** và **mở rộng tải (scaling)**; lựa chọn đúng bước phát triển từ một broker đến nhiều broker.
5. Thiết kế thông điệp có thể xử lý lặp, theo dõi trạng thái queue, bảo vệ broker và kiểm tra phương án phục hồi thay vì chỉ kiểm tra “gửi được, nhận được”.

**Tình huống xuyên suốt:** hệ thống bán hàng phát sự kiện đơn hàng mới. Dịch vụ thanh toán, kho và thông báo cần xử lý ở thời điểm khác nhau. Nếu một dịch vụ tạm dừng, hệ thống cần biết thông điệp còn ở đâu, có được giao lại không và phải làm gì nếu lỗi lặp nhiều lần.

## 2. Mô hình tư duy tối thiểu của hệ thống messaging

~~~mermaid
flowchart LR
    P["Order Service<br/>Producer"] -->|JMS send| B["ActiveMQ Broker"]
    B -->|Queue: mỗi message cho một consumer| C1["Payment Worker A"]
    B -->|Cùng queue, cạnh tranh nhận việc| C2["Payment Worker B"]
    B -->|Topic: sự kiện đến từng subscription| S1["Inventory Subscription"]
    B -->|Topic: sự kiện đến từng subscription| S2["Notification Subscription"]
~~~

Sơ đồ minh họa **hai kiểu destination logic**. Trong thiết kế thực tế, payment thường nhận lệnh qua queue riêng, còn inventory và notification nhận sự kiện qua các subscription của topic; không mặc định chuyển cùng một message từ một queue sang mọi nhánh như một cơ chế phát tán.

Các khái niệm phải phân biệt rõ:

| Khái niệm | Ý nghĩa thực tế | Câu hỏi cần trả lời |
|---|---|---|
| **Producer** | Ứng dụng tạo và gửi message | Khi nào coi một lần gửi đã thành công? |
| **Broker** | Nhận, lưu trữ khi được cấu hình, định tuyến và giao message | Broker lưu dữ liệu ở đâu và mất kết nối thì sao? |
| **Destination** | Đích logic mà producer gửi tới | Đây là queue, topic hay address có các queue phía sau? |
| **Consumer** | Ứng dụng nhận và xử lý message | Khi nào xử lý xong và xác nhận với broker? |
| **Queue** | Một message thông thường được giao cho **một** consumer trong nhóm cạnh tranh trên queue đó | Cần phân phối công việc cho nhiều worker hay không? |
| **Topic / subscription** | Mỗi subscription phù hợp nhận một bản sao logic của sự kiện | Những nhóm nghiệp vụ nào cần nhận độc lập? |
| **Persistent message** | Message yêu cầu provider lưu bền vững theo hợp đồng và cấu hình tương ứng | Khởi động lại broker có làm mất message chưa xử lý không? |
| **Acknowledgment (ack)** | Xác nhận phía consumer đã nhận/xử lý ở mức mà ứng dụng quyết định | Nếu tiến trình chết trước ack thì có giao lại không? |
| **Transaction** | Nhóm thao tác JMS được commit hoặc rollback cùng nhau trong phạm vi session | Đã gửi/nhận xong nhưng chưa commit thì điều gì xảy ra? |
| **DLQ** | Đích chứa message không xử lý được sau các lần thử theo chính sách | Ai theo dõi, sửa nguyên nhân và phát lại? |

**JMS (Java Message Service / Jakarta Messaging)** là API/lớp hợp đồng lập trình Java, không phải bản thân một giao thức truyền qua mạng. Ứng dụng dùng API JMS nhưng vẫn cần **client library tương thích với broker và transport protocol**. Không thể mặc định mọi cổng TCP hoặc mọi client của Classic/Artemis đều giao tiếp lẫn nhau.

### Queue và topic trong bài toán đơn hàng

- **Queue – giao việc:** Order Service gửi lệnh “xử lý thanh toán” vào queue **payment.commands**; hai payment worker cùng subscribe queue để chia tải. Mỗi message được một worker xử lý tại một thời điểm bình thường, nhưng **có thể giao lại** khi lỗi.
- **Topic – công bố sự kiện:** Order Service phát **OrderCreated** tới topic **orders.events**. Inventory và Notification có subscription riêng nên cùng một sự kiện có thể phục vụ hai nhu cầu. Với subscriber không bền vững, sự kiện phát trong lúc subscriber offline có thể không được giữ cho subscriber đó.
- **Durable subscription:** dùng khi một subscriber cần nhận lại những message phù hợp trong khoảng offline, với định danh subscription, lưu trữ và điều kiện phù hợp. “Persistent message” và “durable subscription” là **hai điều kiện khác nhau**; chỉ bật một trong hai không bảo đảm replay như mong đợi.
- **Message selector:** consumer có thể lọc theo property; chỉ nên dùng khi cần, vì biểu thức lọc và số lượng subscription làm thay đổi chi phí vận hành.

## 3. ActiveMQ Classic và ActiveMQ Artemis: giống mục tiêu, khác mô hình

Cả hai là message broker thuộc hệ sinh thái Apache ActiveMQ, nhưng **không phải hai tên gọi của cùng một implementation**.

| Góc nhìn | ActiveMQ Classic | ActiveMQ Artemis |
|---|---|---|
| Tư duy JMS thường gặp | Queue và topic là các destination quen thuộc | **Address** nhận message; một hoặc nhiều **queue** gắn vào address để lưu/phân phối message |
| Routing | Cơ chế queue/topic của Classic | **ANYCAST** thường dùng cho hàng đợi cạnh tranh; **MULTICAST** dùng để phát đến nhiều queue/subscription |
| Kết nối broker | **Network of Brokers** dùng network connector để chuyển tiếp message theo nhu cầu/subscription và cấu hình | **Cluster connection**, **HA policy**, **federation** và các cơ chế liên kết khác tùy mục tiêu |
| Lưu trữ | Thường gặp **KahaDB** trong cấu hình Classic | Journal, paging và các chính sách address/queue của Artemis |
| Protocol/client | Thường gắn với OpenWire và client Classic; có thêm kết nối khác tùy cấu hình | Hỗ trợ nhiều protocol như Core, AMQP, OpenWire tùy phiên bản/cấu hình; dùng đúng client với acceptor |
| Cấu hình retry/DLQ | Thường qua redelivery policy và dead-letter strategy/policy của Classic | Thường qua address-settings: redelivery delay, max delivery attempts, dead-letter address |

Trong **Artemis**, có thể hình dung:

~~~text
Address: orders.events        [MULTICAST]
    ├── Queue: inventory-sub
    └── Queue: notification-sub

Address: payment.commands     [ANYCAST]
    └── Queue: payment.commands
            ├── Payment Worker A
            └── Payment Worker B
~~~

Với MULTICAST, mỗi queue đăng ký phù hợp có thể nhận bản sao của message. Với ANYCAST, broker chọn một queue phù hợp để định tuyến message; các consumer gắn trên **cùng queue** tiếp tục cạnh tranh nhận. Không được nhầm “nhiều consumer cùng queue” với “nhiều queue trên cùng address”.

**Quy tắc học:** trước hết mô tả hành vi ở cấp JMS (gửi, nhận, ack, commit). Khi cấu hình broker mới chuyển sang thuật ngữ riêng của Classic hoặc Artemis. Không sao chép nguyên xi cấu hình cluster, DLQ hay security giữa hai sản phẩm.

## 4. Những bảo đảm cần hiểu trước khi viết code

### 4.1. Bất đồng bộ thay đổi ranh giới thành công

Một HTTP request thường trả về kết quả ngay; với messaging, bước **gửi message thành công** chỉ xác nhận phần gửi theo hợp đồng provider và giao dịch hiện tại. Nó **không** đồng nghĩa bên nhận đã hoàn thành nghiệp vụ. Người dùng có thể nhận mã đơn hàng ngay, trong khi thanh toán hoặc gửi email xử lý sau.

Cần ghi rõ ít nhất ba trạng thái:

1. **Đã ghi nhận yêu cầu**: nghiệp vụ nguồn đã lưu trạng thái, hoặc producer đã có cơ chế công bố đáng tin cậy.
2. **Broker đã chấp nhận message**: tùy delivery mode, transaction và persistence của broker.
3. **Consumer đã hoàn thành nghiệp vụ**: ví dụ payment worker đã commit kết quả vào database rồi mới ack.

### 4.2. Vì sao message có thể bị xử lý hai lần?

Giả sử consumer đã cập nhật database thành công nhưng mất kết nối **trước khi ack**. Broker không chắc ứng dụng đã xử lý xong nên có thể phát lại message. Một worker mới đọc cùng sự kiện và nếu code không chống trùng, đơn hàng bị trừ tiền hoặc trừ tồn kho lần thứ hai.

Giải pháp ứng dụng: gắn **eventId** ổn định cho từng sự kiện, dùng bảng inbox hoặc unique constraint để xử lý **idempotent**:

~~~text
Bắt đầu transaction database
  Thử ghi eventId vào bảng processed_events (unique key)
  Nếu eventId đã tồn tại: coi như đã xử lý trước đó
  Nếu chưa có: cập nhật nghiệp vụ và ghi processed_events
Commit database
Ack message với broker
~~~

Nếu lỗi sau database commit nhưng trước ack, lần giao lại chỉ xác nhận “đã xử lý”, không áp dụng hiệu ứng nghiệp vụ lần hai. Ví dụ PostgreSQL có thể dùng **INSERT ... ON CONFLICT DO NOTHING** và dựa vào số dòng thực sự được chèn; ở database khác cần câu lệnh tương đương.

**Đừng đồng nhất “exactly-once delivery” với “exactly-once business effect”.** Một transaction JMS đơn lẻ không tự động bao trùm transaction của database khác. Pattern **transactional outbox** ở producer và **idempotent inbox** ở consumer thường là cơ sở dễ kiểm soát hơn trong hệ thống phân tán; XA/2PC có thể dùng trong hoàn cảnh riêng nhưng phải cân nhắc chi phí và khả năng vận hành.

### 4.3. Ack, transaction, TTL và thứ tự

| Cơ chế | Hành vi cần biết | Sai lầm phổ biến |
|---|---|---|
| **AUTO_ACKNOWLEDGE** | JMS provider tự xác nhận theo quy tắc của chế độ nhận/listener | Tưởng rằng database xử lý thành công là điều kiện bắt buộc của auto ack |
| **CLIENT_ACKNOWLEDGE** | Ứng dụng chủ động ack; trong một session, ack thường xác nhận **tất cả** message đã tiêu thụ chưa ack của session đó | Ack một message và nghĩ chỉ message ấy được xác nhận |
| **SESSION_TRANSACTED** | Các thao tác JMS trong session được hoàn tất khi commit; rollback khiến message nhận có thể được giao lại | Vừa gọi commit vừa kỳ vọng một rollback sau đó thu hồi message |
| **PERSISTENT** | Yêu cầu lưu bền vững theo hợp đồng JMS và cấu hình storage | Tưởng persistent tự tạo backup broker hay chống mọi loại sự cố |
| **TTL / expiration** | Message có thể hết hạn trước khi consumer nhận | Tưởng mọi message nhất định phải vào DLQ; expired thường có chính sách/đích riêng |
| **Message ordering** | Có thể phụ thuộc queue, concurrency, phân phối, retry và broker topology | Tưởng thứ tự toàn cục vẫn giữ nguyên khi nhiều consumer xử lý song song |

Với cùng một queue, broker có thể phát message theo thứ tự, nhưng **thứ tự hoàn thành nghiệp vụ** khác khi các worker xử lý song song hoặc khi message cũ phải redeliver. Nếu phải giữ thứ tự theo **orderId**, có thể thiết kế phân vùng/key hoặc message grouping (chẳng hạn property **JMSXGroupID** nếu provider hỗ trợ), đồng thời kiểm tra tác động tới thông lượng.

## 5. Lab đầu tiên: một Artemis broker và Java/JMS

### 5.1. Chuẩn bị

Chọn một phiên bản **Artemis** phù hợp môi trường; tạo một broker instance với persistent storage, tài khoản ứng dụng và một acceptor tương thích client. Thường gặp cổng messaging **61616** và cổng quản trị web **8161** trong thiết lập mẫu, nhưng **phải đối chiếu cấu hình broker thực tế**; đây không phải hai cổng được bảo đảm trong mọi triển khai.

Chuẩn bị:

- JDK phù hợp với phiên bản client đã chọn, Maven hoặc IDE Java.
- Broker chạy local; broker dùng tài khoản có quyền send/consume trên **orders.in**.
- Queue **orders.in** tồn tại, hoặc broker được cấu hình cho phép tự tạo address/queue theo yêu cầu.
- Biến môi trường **MQ_URL**, **MQ_USER**, **MQ_PASSWORD**, ví dụ URL local dạng **tcp://localhost:61616**.
- Dùng dependency **org.apache.activemq:artemis-jms-client** của cùng nhánh tương thích và API **javax.jms** cho ví dụ bên dưới. Nếu dự án đã dùng **jakarta.jms**, chọn **client Jakarta** tương ứng rồi đổi import; không trộn javax và jakarta trong một chương trình.

Việc gọi **createQueue** trong API JMS tạo **đối tượng Destination phía client**. Tùy cấu hình broker, nó không nhất thiết tạo sẵn queue bền vững ở phía server. Luôn xác minh queue trong giao diện quản trị hoặc cấu hình broker.

### 5.2. Chương trình producer/consumer có ack và rollback

~~~java
import java.util.UUID;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class ArtemisOneBrokerLab {
    private static final String DESTINATION = "orders.in";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Chon mot lenh: send | consume | rollback");
        }

        String url = env("MQ_URL");
        String user = env("MQ_USER");
        String password = env("MQ_PASSWORD");

        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        switch (args[0]) {
            case "send":
                send(factory, user, password);
                break;
            case "consume":
                consume(factory, user, password);
                break;
            case "rollback":
                rollback(factory, user, password);
                break;
            default:
                throw new IllegalArgumentException("Lenh khong hop le");
        }
    }

    private static void send(ConnectionFactory factory,
                             String user, String password) throws Exception {
        try (JMSContext context = factory.createContext(user, password)) {
            Queue queue = context.createQueue(DESTINATION);
            TextMessage message = context.createTextMessage(
                "{\"orderId\":\"OD-1001\",\"type\":\"OrderCreated\"}");
            message.setStringProperty("eventId", UUID.randomUUID().toString());

            context.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .send(queue, message);

            System.out.println("Sent eventId="
                + message.getStringProperty("eventId"));
        }
    }

    private static void consume(ConnectionFactory factory,
                                String user, String password) throws Exception {
        try (JMSContext context = factory.createContext(
                 user, password, JMSContext.CLIENT_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(DESTINATION);
            Message message = context.createConsumer(queue).receive(5000);

            if (message == null) {
                System.out.println("Khong co message trong 5 giay");
                return;
            }

            System.out.println("Processing eventId="
                + message.getStringProperty("eventId")
                + ", redelivered=" + message.getJMSRedelivered());

            // Trong he thong that: commit thay doi database theo eventId.
            // Chi ack sau khi thuc hien nghiep vu thanh cong.
            message.acknowledge();
            System.out.println("Acknowledged");
        }
    }

    private static void rollback(ConnectionFactory factory,
                                 String user, String password) throws Exception {
        try (JMSContext context = factory.createContext(
                 user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(DESTINATION);
            Message message = context.createConsumer(queue).receive(5000);

            if (message == null) {
                System.out.println("Khong co message de rollback");
                return;
            }

            System.out.println("Received but intentionally rolling back "
                + message.getStringProperty("eventId"));
            context.rollback(); // Chua ack: broker co the redeliver.
        }
    }

    private static String env(String key) {
        String value = System.getenv(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Mã dùng API JMS 2.x theo namespace **javax.jms** và client Artemis tương ứng; phiên bản thư viện phải được chọn theo broker/JDK của dự án. Để chạy, biên dịch class với dependency đã khai báo, thiết lập ba biến môi trường, rồi truyền lần lượt argument **send**, **consume** hoặc **rollback** khi chạy hàm main. **Không** đưa mật khẩu môi trường thật vào source code.

Chạy thử theo thứ tự:

1. Chạy **send** một lần, kiểm tra queue có một message chờ nếu chưa có consumer.
2. Chạy **consume**: thấy eventId, message được ack; queue về trạng thái không còn message pending.
3. Chạy **send**, rồi **rollback**, rồi **consume**: kiểm tra message đã được giao lại. Property **JMSRedelivered** có thể cho biết đây là lần giao lại; thời điểm và số lần thử phụ thuộc cấu hình.
4. Chạy **send** khi consumer đang offline; kiểm tra tồn đọng. Với queue bền vững và persistent storage phù hợp, dừng broker **đúng quy trình**, khởi động lại và thử **consume**.
5. Tăng số worker cùng đọc queue và đo sự phân chia message. Lặp lại với topic có hai subscription để thấy khác biệt về fan-out.

**Giới hạn chủ ý của lab:** phần “xử lý nghiệp vụ” hiện chỉ in log. Để đạt at-least-once có hiệu ứng nghiệp vụ an toàn, thay comment bằng transaction database và idempotency key; không xem lệnh in log là một hệ thống xử lý đơn hàng hoàn chỉnh.

## 6. Từ lỗi tạm thời đến redelivery và DLQ

Consumer có thể thất bại vì timeout database, API bên ngoài không phản hồi, dữ liệu không hợp lệ hoặc bug. Không nên xử lý mọi lỗi bằng retry vô hạn.

~~~mermaid
flowchart TD
    Q["Message ở queue"] --> C["Consumer nhận"]
    C --> D{"Xử lý thành công?"}
    D -->|Có| A["Commit nghiệp vụ rồi ack/commit JMS"]
    D -->|Không| R["Rollback / không ack"]
    R --> N{"Còn lượt thử theo policy?"}
    N -->|Có| W["Chờ redelivery delay"] --> Q
    N -->|Không| DLQ["Dead-letter queue"]
    DLQ --> I["Quan sát, sửa lỗi, phát lại có kiểm soát"]
~~~

Với Artemis, chính sách được đặt theo **address-settings**, ví dụ về mặt cấu trúc:

~~~xml
<address-setting match="orders.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>2000</redelivery-delay>
</address-setting>
~~~

Ví dụ mang tính minh họa cấu hình Artemis, không áp dụng cho Classic. Cần bảo đảm **address và queue đích DLQ** đã được provision hoặc có cơ chế auto-create phù hợp; xác minh quy tắc match wildcard theo phiên bản/cấu hình broker. Tại đây, broker được yêu cầu tối đa ba lần thử theo semantics của policy và trì hoãn giao lại 2.000 ms. Không giả định các lần retry diễn ra chính xác theo đồng hồ nếu broker/client có tải hoặc thay đổi kết nối.

**Classic** dùng mô hình cấu hình redelivery policy và dead-letter strategy khác. Một số hệ thống Classic dùng đích chung **ActiveMQ.DLQ**, nhưng cấu hình có thể chuyển sang DLQ theo từng destination. Không hardcode tên này khi đang làm việc với Artemis.

Phân loại lỗi giúp chọn chính sách:

| Loại lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| **Tạm thời** | Database timeout, dịch vụ downstream 503 | Retry có trì hoãn/backoff và số lần giới hạn |
| **Dữ liệu không hợp lệ** | Thiếu orderId, schema version không hỗ trợ | Gửi vào DLQ/quarantine sớm, cảnh báo để sửa producer hoặc chuyển đổi dữ liệu |
| **Lỗi nghiệp vụ đã biết** | Đơn hàng bị hủy trước khi thanh toán | Ghi kết quả hợp lệ cho trạng thái này; không retry mù quáng |
| **Poison message** | Luôn gây exception ở một consumer | Cách ly để queue chính không bị kẹt |
| **Hạ tầng kéo dài** | Database dừng lâu | Hạn chế retry dồn dập, giám sát backlog, chủ động điều chỉnh nhịp consume |

Khi xử lý DLQ cần lưu **eventId, JMSMessageID, loại lỗi, thời điểm, số lần thử, version schema** và công cụ phát lại. Phát lại phải có giới hạn tốc độ, kiểm tra idempotency và giữ log kiểm toán. **DLQ không phải nơi lưu lỗi rồi bỏ quên**.

## 7. Khi nào một broker là đủ và khi nào cần nhiều broker?

### 7.1. Một broker: bước khởi đầu đúng

~~~mermaid
flowchart LR
    P["Nhiều producer"] --> B["Broker A<br/>Persistent storage"]
    B --> W1["Worker 1"]
    B --> W2["Worker 2"]
    B --> W3["Worker 3"]
~~~

Một broker vẫn có thể hỗ trợ **nhiều queue, topic, connection và consumer**. Trước khi thêm broker, đo thông lượng, độ trễ, tỷ lệ lỗi, backlog, disk I/O và CPU. Tăng số consumer không tự động cải thiện tốc độ nếu một database hoặc API downstream đã là nút nghẽn.

Rủi ro cần ghi nhận: broker đơn lẻ có thể trở thành **single point of failure**. **Persistent storage** giúp giữ message khi restart hợp lệ nhưng không tự giải quyết việc broker, host hoặc volume bị mất hoàn toàn.

### 7.2. HA: một broker hoạt động, một broker dự phòng

~~~mermaid
flowchart LR
    APP["JMS Clients<br/>Failover/reconnect"] --> L["Active Broker"]
    L <-->|Replication hoặc shared storage| BK["Backup Broker"]
    L --> S["Queue / message processing"]
~~~

Trong Artemis, HA có thể thiết kế theo **replication** hoặc **shared-store** (phụ thuộc phiên bản và chính sách). Mục tiêu: một broker khác có thể tiếp nhận phục vụ khi broker active lỗi. Cấu hình cần xem xét **quorum, fencing, storage, network partition** và cách client kết nối lại để giảm nguy cơ hai bên cùng nhận vai trò active (**split brain**).

**HA không mặc định nhân đôi throughput.** Backup có thể ở trạng thái chờ; nếu cần phân phối tải xử lý trên nhiều broker active, phải thiết kế cluster/routing bổ sung. Đồng thời, **client reconnect** không chứng minh một transaction trước lúc mất mạng đã commit hay chưa: ứng dụng vẫn phải chịu được kết quả mơ hồ và message lặp.

### 7.3. Cluster: nhiều broker cùng nhận tải

~~~mermaid
flowchart LR
    P1["Producer A"] --> A["Broker A"]
    P2["Producer B"] --> B["Broker B"]
    A <-->|Cluster routing| B
    A --> CA["Consumers A"]
    B --> CB["Consumers B"]
~~~

Ở Artemis, cluster connection cho phép các node phối hợp định tuyến/distribution theo topology, queue binding và chính sách tương ứng. Việc đặt hai broker vào cluster **không** đồng nghĩa mỗi message đã được sao chép bền vững đến mọi node. Phải xác minh **queue tồn tại trên node nào**, consumer kết nối ở đâu, message được forward thế nào và xử lý ra sao khi mất một node.

Nếu cần **cả HA và scale**, có thể dùng nhiều cặp active/backup với cluster ở tầng active theo thiết kế đã thử nghiệm. Không coi việc có hai process broker là đủ bằng chứng cho cả hai mục tiêu.

### 7.4. Network of Brokers ở Classic và federation

ActiveMQ **Classic** thường liên kết các broker bằng **network connector**. Broker có thể forward message theo demand/subscription, giúp kết nối các nhóm producer/consumer ở các broker khác nhau. Cần thử riêng **dynamic/static network connectors**, vòng lặp tuyến đường, TTL/hop limit, subscriptions và cách hàng đợi hoạt động khi đường nối bị gián đoạn. Đây không phải cơ chế HA giống một cặp active/backup.

Với **Artemis federation**, các broker/site có thể trao đổi message hoặc demand theo policy, phục vụ liên kết vùng hoặc miền vận hành. Federation, cluster và replication giải quyết các bài toán khác nhau; cùng từ “nhiều broker” không đủ để quyết định công nghệ.

### 7.5. Bảng chọn hướng mở rộng

| Nhu cầu quan sát được | Hướng ưu tiên | Phép thử quyết định |
|---|---|---|
| Một broker chưa quá tải, cần giảm rủi ro mất dịch vụ | HA + client failover | Kill active broker; đo thời gian phục hồi, mất/lặp message |
| Broker quá tải khi nhiều destination/connection, cần trải lưu lượng | Cluster hoặc phân vùng workload | Benchmark routing, consumer locality và backlog từng node |
| Hai trung tâm dữ liệu cần trao đổi sự kiện với độ trễ mạng đáng kể | Federation/bridge theo chính sách | Ngắt WAN, nối lại; kiểm tra thứ tự, trùng và độ trễ |
| Nhiều nhóm muốn độc lập triển khai, quản lý quyền và vòng đời | Tách broker/namespace theo ranh giới vận hành phù hợp | Kiểm tra ownership, access control, quota và quy trình thay đổi |
| Downstream chậm làm backlog tăng | Tối ưu consumer/backpressure trước | Đo throughput thực tế sau khi tăng/giảm số consumer |

## 8. Những thay đổi bắt buộc khi đi từ một đến nhiều broker

### 8.1. Client không thể giả định kết nối luôn sống

Thử nghiệm reconnect/failover phải trả lời:

- Client có kết nối lại được khi host chết hoặc broker chuyển vai trò không?
- Producer gửi trong thời điểm chuyển đổi nhận được lỗi, timeout hay kết quả thành công nhưng chưa chắc chắn? Ứng dụng giải quyết lần gửi lại bằng **messageId nghiệp vụ/eventId** ra sao?
- Consumer đang xử lý transaction khi ngắt mạng sẽ rollback, giao lại hay cần kiểm tra trạng thái chưa rõ?
- Mỗi endpoint, protocol, TLS và cơ chế xác thực có nhất quán không?

Dùng cấu hình reconnect/failover **đúng theo client và sản phẩm**; ví dụ URI failover của Classic không mặc nhiên áp dụng cho Artemis. Kiểm thử thực sự bằng kill process, ngắt mạng và restart, không chỉ xem cấu hình có tên “failover”.

### 8.2. Nơi đặt queue và đường đi của message trở thành một phần hợp đồng

Ở một broker, producer/consumer cùng nhìn thấy một queue nên thiếu sót routing dễ bị che khuất. Trong nhiều broker cần tài liệu rõ:

- Tên address, queue, routing type, durable/non-durable.
- Node nào có queue, node nào có consumer, khi nào message chuyển broker.
- Subscription nào độc lập, có giữ message khi offline không.
- Chính sách retry, DLQ, TTL/expiry và giới hạn kích thước.
- Hệ quả khi cluster link mất: queue cục bộ có tích tụ không, khi nối lại có forward/duplicate không.

### 8.3. Transaction không mở rộng tự động qua nhiều hệ thống

Transaction JMS thông thường áp dụng trên session/provider tương ứng. Việc có thêm broker, database hoặc HTTP service làm tăng các cửa sổ lỗi. Dùng:

- **Transactional outbox:** trong cùng transaction database, ghi nghiệp vụ và một bản ghi outbox; publisher gửi từ outbox rồi đánh dấu đã phát. Publisher có thể gửi lặp khi crash, vì thế consumer phải idempotent.
- **Inbox/dedup:** khi nhận, dùng eventId và unique constraint để xác nhận xử lý một lần về mặt hiệu ứng nghiệp vụ.
- **Correlation ID:** liên kết các message của một workflow để truy vết.
- **Retry có giới hạn và DLQ:** biến lỗi kéo dài thành tín hiệu vận hành có chủ sở hữu.

Nếu workflow gồm nhiều bước như đặt hàng → thanh toán → giữ hàng → giao vận, hãy xác định ai điều phối kết quả, retry ở đâu và sự kiện bù trừ nào cần phát. Message broker không tự trở thành transaction coordinator nghiệp vụ.

## 9. Bảo mật, vận hành và hiệu năng là một phần của bài học

### Bảo mật

1. Dùng tài khoản riêng cho ứng dụng, cấp tối thiểu quyền **send/consume/create** theo destination; tài khoản quản trị tách biệt.
2. Chỉ bật các protocol/acceptor thực sự cần. Hạn chế cổng quản trị vào mạng tin cậy; tránh mở dashboard và port broker công khai.
3. Bật TLS cho kết nối ngoài môi trường local phù hợp; kiểm chứng chứng chỉ, hostname và cơ chế secret rotation.
4. Không ghi username/password/token vào source, message body hay log. Với message chứa dữ liệu cá nhân, xác định yêu cầu mã hóa, retention và quyền truy cập.
5. Cấu hình authorization riêng theo Classic hoặc Artemis; cùng dùng JMS API không làm policy của hai broker giống nhau.

### Quan sát và cảnh báo

| Tín hiệu | Nó trả lời điều gì? | Tình huống cần cảnh báo |
|---|---|---|
| **Queue depth / message count** | Bao nhiêu message đang chờ? | Backlog tăng liên tục ngoài ngưỡng hệ thống |
| **Enqueue vs dequeue/ack rate** | Tốc độ nhập có vượt tốc độ xử lý không? | Ingress cao kéo dài, consumer không theo kịp |
| **Message age / end-to-end latency** | Message phải đợi bao lâu mới hoàn tất? | Vi phạm SLO dù queue depth chưa lớn |
| **Consumer count / connection health** | Có consumer nào đang phục vụ? | Mất hết consumer hoặc reconnect liên tục |
| **Redelivery / DLQ / expiry** | Message nào bị lỗi hoặc hết hạn? | DLQ tăng, tỷ lệ retry bất thường |
| **Disk, memory, journal, paging** | Broker có đủ tài nguyên lưu và phân phối không? | Đĩa gần đầy, paging kéo dài, I/O latency cao |
| **HA/cluster link status** | Các node còn đúng vai trò và nhìn thấy nhau không? | Backup không sẵn sàng, link cluster gãy |

Chỉ số cụ thể, API lấy metric và ý nghĩa counter phụ thuộc phiên bản và broker. Đặt ngưỡng từ **SLO và baseline thực đo**, không sao chép ngưỡng cố định từ môi trường khác.

### Các điểm thường gây nghẽn

- Message quá lớn khiến disk/memory/network tốn kém; cân nhắc giữ payload nhỏ và dùng tham chiếu tới object storage khi thích hợp.
- Prefetch/consumer window lớn tăng thông lượng nhưng làm message nằm sẵn ở client, ảnh hưởng fairness, retry và số message đang in-flight.
- Quá nhiều consumer có thể làm database downstream nghẽn hơn.
- Persistence, transaction và journal sync tăng an toàn nhưng có chi phí I/O. Luôn benchmark với cấu hình thực tế.
- DLQ, expiry queue và paging không được giới hạn dung lượng có thể biến sự cố nhỏ thành hết đĩa.

## 10. Trình tự học đề xuất: đi từng bậc và kiểm chứng

Không chuyển bước chỉ vì chạy được ví dụ “hello world”. Mỗi bước phải có **một giả thuyết**, **một lỗi được tiêm có chủ đích** và **một tiêu chí đạt**.

| Bước | Kiến thức trọng tâm | Bài thực hành | Điều kiện hoàn thành |
|---|---|---|---|
| **1. Nền tảng** | Producer, consumer, destination, queue/topic, JMS, địa chỉ Artemis | Vẽ hai luồng payment queue và orders topic | Giải thích được ai nhận message khi có 2 worker và 2 subscription |
| **2. Một broker** | Connection, session/JMSContext, persistent send, provisioning queue | Chạy chương trình Java ở mục 5 | Gửi/nhận ổn định; đọc được trạng thái queue |
| **3. Delivery và lỗi** | Ack, transacted session, rollback, redelivery, TTL | Kill consumer trước ack, dùng rollback và restart broker | Chỉ ra được trường hợp giao lại và message còn ở đâu |
| **4. Chống trùng và DLQ** | Idempotency, inbox/outbox, retry, poison message | Tạo lỗi 3 lần, theo dõi DLQ, replay có kiểm soát | Không cập nhật nghiệp vụ hai lần; DLQ được quan sát |
| **5. Vận hành một broker** | ACL, TLS, backup, disk, paging, metrics | Giới hạn tài khoản, tạo backlog, tăng số consumer | Có dashboard/alert cơ bản và đo được throughput |
| **6. HA** | Active/backup, replication/shared store, reconnect, quorum | Ngắt active broker khi đang phát và nhận | Đo RTO, phát hiện transaction mơ hồ, không bỏ sót kiểm tra trùng |
| **7. Nhiều broker active** | Artemis cluster/routing hoặc Classic Network of Brokers | Hai broker, producer và consumer ở khác node | Giải thích đường đi message, đo backlog từng broker, thử đứt liên kết |
| **8. Hoàn thiện** | Federation khi cần, DR, nâng cấp, giám sát, runbook | Diễn tập downtime, khôi phục, replay DLQ và nâng cấp có kế hoạch | Có kết quả đo, sơ đồ topology, cảnh báo và quy trình khôi phục |

**Thứ tự này có lý do:** nếu chưa hiểu ack/rollback ở một broker, khi xảy ra message lặp trong cluster sẽ không phân biệt được lỗi ứng dụng với hành vi bình thường của broker. Nếu chưa có metric ở một broker, thêm node sẽ chỉ làm bài toán chẩn đoán khó hơn.

### Bài tập tích hợp cuối lộ trình

Thiết kế hệ thống xử lý đơn hàng với các yêu cầu:

- Order Service ghi đơn hàng và công bố **OrderCreated** mà không bỏ sót khi process crash.
- Payment Service có hai instance cùng xử lý queue, không thu tiền hai lần khi message redeliver.
- Inventory và Notification có subscription riêng; một service offline 10 phút vẫn nhận đúng sự kiện theo chính sách durable subscription đã chọn.
- Thông điệp sai schema phải tới DLQ sau một số lần thử hữu hạn; có người nhận cảnh báo và cách replay.
- Khi broker active ngừng đột ngột, client kết nối lại; phải trình bày điều gì được giữ, điều gì có thể lặp và cách kiểm chứng.
- Khi bổ sung broker thứ hai, vẽ rõ mỗi queue ở node nào, route của message, kết nối của worker và cách tách HA khỏi mục tiêu tăng throughput.

**Sản phẩm cần nộp:** sơ đồ topology; bảng tên destination/address/queue; hợp đồng message có eventId, correlationId, version và timestamp; code Java; các trường hợp lỗi và kết quả kiểm chứng; ảnh/chỉ số backlog, redelivery, DLQ; runbook phục hồi ngắn.

## 11. Những ngộ nhận cần tự kiểm tra

1. **“Có queue nên không mất message.”** Sai nếu cấu hình durability, transaction, storage và phục hồi chưa được xác minh.
2. **“Một message luôn được xử lý đúng một lần.”** Không có bảo đảm tổng quát cho hiệu ứng nghiệp vụ qua broker và database; consumer phải tính tới redelivery.
3. **“Topic nghĩa là mỗi process luôn nhận.”** Số bản sao phụ thuộc subscription, durable hay non-durable, selector, trạng thái kết nối và routing policy.
4. **“Hai broker là HA và scale cùng lúc.”** Cần chứng minh riêng failover, dữ liệu và phân phối tải theo topology cụ thể.
5. **“Thêm consumer luôn tăng tốc.”** Có thể chỉ đẩy nghẽn sang database hoặc làm tăng xử lý trùng và mất thứ tự.
6. **“DLQ giải quyết lỗi.”** DLQ giữ lại đối tượng thất bại; vẫn cần người chịu trách nhiệm phân tích và khôi phục.
7. **“Classic và Artemis đều dùng ActiveMQ nên copy config được.”** Không đúng: mô hình destination, connector, HA, persistence và policy khác nhau.
8. **“Message đã được gửi là nghiệp vụ đã xong.”** Producer gửi thành công và consumer commit nghiệp vụ là hai mốc độc lập.

## 12. Checklist trước khi công nhận một topology đã sẵn sàng

- [ ] Đã ghi rõ **broker là Classic hay Artemis**, version, protocol/client và namespace **javax.jms/jakarta.jms** tương ứng.
- [ ] Đã có bảng destination, queue/topic hoặc address/routing type, durable subscription và chính sách auto-create.
- [ ] Producer có quy tắc công bố message đáng tin cậy; consumer idempotent theo eventId.
- [ ] Đã thử rollback, mất kết nối, crash consumer, restart broker, expiry và retry tới DLQ.
- [ ] Đã chứng minh không có hiệu ứng nghiệp vụ lặp khi DB commit thành công nhưng ack thất bại.
- [ ] Có tài khoản tối thiểu quyền, TLS phù hợp và bảo vệ giao diện quản trị.
- [ ] Đã đo backlog, tuổi message, throughput, tỷ lệ redelivery, DLQ và sử dụng tài nguyên.
- [ ] Nếu có HA: đã thử failover và split-brain prevention theo HA policy.
- [ ] Nếu có cluster/network/federation: đã thử mất liên kết, routing, reconnect và giới hạn thông lượng.
- [ ] Có owner, runbook, backup/restore và tiêu chí RTO/RPO rõ ràng.

**Ý chính cần giữ:** Học ActiveMQ hiệu quả là học **đường đi và trạng thái của từng message khi mọi thứ bình thường lẫn khi có lỗi**. Bắt đầu với một broker để làm rõ contract JMS và idempotency, sau đó mới thêm HA, cluster hoặc federation theo nhu cầu được đo và kiểm chứng.
