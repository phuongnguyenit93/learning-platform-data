# Shared subscription và giới hạn hỗ trợ của từng broker, client và phiên bản

> **Chương:** Queue và Topic  
> **Phạm vi:** Apache ActiveMQ Classic, ActiveMQ Artemis và Java/JMS trong hệ thống phân phối sự kiện bất đồng bộ. Bài này tập trung vào việc **nhiều consumer cùng chia tải trên một subscription của topic**, các loại subscription, ràng buộc API và tính tương thích theo phiên bản.

## 1. Mục tiêu và tình huống cần giải quyết

Giả sử một hệ thống phát sự kiện `OrderCreated` lên JMS topic `orders.events`. Hai hệ thống độc lập cần nhận **tất cả** sự kiện:

- **Notification**: gửi email hoặc thông báo cho khách.
- **Analytics**: cập nhật báo cáo theo đơn hàng.

Khi lưu lượng tăng, mỗi hệ thống muốn chạy nhiều bản sao worker để chia tải. Mong muốn chính xác là:

1. Với mỗi sự kiện, **Notification nhận một bản sao** và **Analytics nhận một bản sao**.
2. Bên trong mỗi nhóm, **chỉ một worker xử lý một lần giao** của sự kiện đó; worker khác sẽ lấy việc tiếp theo.
3. Nếu toàn bộ worker của một nhóm tạm dừng, các sự kiện vẫn được giữ để xử lý sau, trong giới hạn cấu hình và độ bền.
4. Khi worker lỗi sau khi đã tạo hiệu ứng nghiệp vụ nhưng trước khi xác nhận, hệ thống chấp nhận khả năng **redelivery** và chống xử lý lặp.

Đó là trường hợp điển hình của **shared durable subscription** theo JMS 2.0/Jakarta Messaging, với điều kiện broker, thư viện client và giao thức đều hỗ trợ.

~~~mermaid
flowchart LR
    P[Order Service] --> T[(Topic orders.events)]
    T --> N[(Shared durable subscription: notification)]
    T --> A[(Shared durable subscription: analytics)]
    N --> N1[Email worker 1]
    N --> N2[Email worker 2]
    N --> N3[Email worker 3]
    A --> A1[Analytics worker 1]
    A --> A2[Analytics worker 2]
~~~

**Đọc sơ đồ:** Topic nhân bản thông điệp **theo subscription**; nhiều consumer của **cùng một subscription** cạnh tranh nhận thông điệp từ bản sao dành cho nhóm đó. Hai nhóm nhận hai luồng logic độc lập. Không có yêu cầu rằng các worker trong một nhóm phải được chia đều 50/50 hoặc đảm bảo thứ tự xử lý hoàn toàn giống nhau.

### Kỳ vọng khi phát 100 sự kiện

| Thành phần | Số thông điệp nghiệp vụ cần xử lý |
|---|---:|
| Notification, tổng ba worker | 100 message |
| Analytics, tổng hai worker | 100 message |
| Mỗi worker riêng lẻ | Phụ thuộc lịch phân phối/prefetch; không suy ra 100 / số worker |
| Tổng bản sao logic cho hai subscription | 200 lượt xử lý nếu không có lọc, hết hạn hay lỗi |
| Nếu có rollback/redelivery | Số **lần giao** có thể lớn hơn 200 |

Số liệu này mô tả trường hợp vận hành bình thường: hai subscription đã tồn tại trước khi publish, selector đều khớp, không có message hết hạn và mọi thông điệp cuối cùng được xác nhận. Một hệ thống khác cần nhận cùng sự kiện phải dùng **subscription riêng**, không tham gia chung subscription của Notification.

## 2. Bốn kiểu subscription: shared và durable là hai trục khác nhau

`Shared` nghĩa là nhiều consumer đang hoạt động có thể lấy message từ **cùng một subscription**. `Durable` nghĩa là subscription vẫn tồn tại và giữ message đủ điều kiện khi không còn consumer kết nối. Hai tính chất kết hợp thành bốn trường hợp.

| Kiểu subscription | API JMS/Jakarta Messaging | Số consumer đồng thời | Khi tất cả consumer dừng |
|---|---|---|---|
| **Unshared, non-durable** | `context.createConsumer(topic)` | Một consumer trên một subscription vô danh; mỗi lần tạo consumer lại là subscription khác | Subscription biến mất; những message được phát sau đó không được tích lũy cho nó |
| **Shared, non-durable** | `context.createSharedConsumer(topic, "name")` | Nhiều consumer trên một subscription có tên | Khi consumer cuối cùng đóng, subscription bị xóa; message chưa nhận của nó mất |
| **Unshared, durable** | `context.createDurableConsumer(topic, "name")` | Chỉ một consumer đang hoạt động trên subscription | Subscription và backlog được giữ; cần `clientID` theo chuẩn |
| **Shared, durable** | `context.createSharedDurableConsumer(topic, "name")` | Nhiều consumer trên một subscription có tên | Subscription vẫn tồn tại cho đến khi `unsubscribe`, nên có thể tích lũy message mới |

Các API shared ở trên được giới thiệu trong **JMS 2.0** và tiếp tục có mặt trong Jakarta Messaging. Chỉ import được kiểu `JMSContext` không chứng minh broker/client hỗ trợ các phương thức shared cụ thể.

### Tình huống theo dòng thời gian

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    participant G as Shared durable group
    Note over G: Tạo subscription, rồi đóng mọi consumer
    P->>B: Publish E1
    B->>B: Giữ E1 cho group đã tồn tại
    P->>B: Publish E2
    B->>B: Giữ E2
    G->>B: Worker A, B kết nối lại
    B-->>G: Phân phối E1 và E2 giữa A/B
    G-->>B: Commit/Acknowledge
~~~

Nếu thay nhóm trên bằng **shared non-durable**, khi consumer cuối cùng đã đóng thì các sự kiện E1, E2 sẽ **không được giữ** để chờ nhóm đó. Nếu một nhóm shared durable hoàn toàn **chưa từng được tạo** trước E1 thì tạo mới nhóm sau E1 cũng không giúp đọc lại E1 từ quá khứ. JMS topic không mặc nhiên có tính năng replay vô hạn như một event log.

**Durability và persistence không đồng nghĩa:** durable subscription tồn tại khi consumer offline; để message tồn tại bền vững qua broker restart/crash, producer cần gửi `DeliveryMode.PERSISTENT` và broker phải có persistence cấu hình phù hợp. Message TTL, quota, address-full policy và chính sách quản trị vẫn có thể giới hạn thời gian/số lượng message giữ lại.

## 3. Danh tính subscription và những va chạm khó phát hiện

Một shared subscription trong JMS được nhận diện bởi **subscription name** và **JMS client identifier nếu có đặt**. Topic và message selector là những thuộc tính phải tương thích khi nhiều consumer muốn tham gia **cùng** subscription.

Ví dụ:

~~~text
Topic: orders.events

Subscription "notification":
  Consumer N1
  Consumer N2
  Consumer N3

Subscription "analytics":
  Consumer A1
  Consumer A2
~~~

Để N1/N2/N3 chia một backlog, tất cả phải sử dụng cùng topic, cùng subscription name, cùng loại shared durable hoặc shared non-durable và cùng selector. Một số hệ thống dùng tên nhóm theo `namespace/environment/service`, ví dụ `prod.notification.v1`, để tránh nhóm khác vô tình tham gia.

### ClientID: nên đặt hay không?

- **Unshared durable:** cần clientID; sự độc quyền clientID trên connection khiến nhiều replica thường không thể dùng chung clientID đang hoạt động.
- **Shared durable / shared non-durable:** chuẩn cho phép clientID **không được đặt**. Đó là cách đơn giản để các replica dùng cùng tên subscription mà không gặp lỗi hai connection cùng dùng một clientID.
- Nếu **có đặt clientID**, các consumer muốn tham gia cùng subscription phải dùng cùng định danh theo quy định provider. Đồng thời phải tôn trọng hạn chế về tính duy nhất của clientID trên kết nối; do đó đừng copy một cấu hình clientID cố định sang nhiều pod rồi giả định chúng vẫn kết nối đồng thời.
- Nếu hai nhóm vô tình tạo cùng subscription name mà không clientID, chúng có nguy cơ **chia tải lẫn nhau**, tức mỗi nhóm không nhận đủ sự kiện. Nếu dùng hai clientID khác nhau, chúng lại có thể tạo **hai subscription khác nhau** và nhận các bản sao độc lập.

Đừng tự sinh subscription name từ `workerId` hoặc `podName` nếu mục tiêu là shared subscription: cách đó tạo ra nhiều subscription độc lập, gây nhân bản thông điệp cho từng worker.

### Selector phải được quản lý như một phần của hợp đồng

Giả sử nhóm Notification chỉ xử lý `eventType = 'OrderCreated'`. Tất cả replica nên gọi:

~~~java
JMSConsumer consumer = context.createSharedDurableConsumer(
    topic,
    "notification",
    "eventType = 'OrderCreated'"
);
~~~

Nếu một replica dùng selector khác hoặc đổi sang topic khác khi subscription đang có consumer hoạt động, provider có thể từ chối theo chuẩn. Với **shared durable** không còn consumer hoạt động, việc tạo lại cùng tên với topic/selector khác có thể được hiểu tương đương **xóa subscription cũ và tạo lại**, khiến backlog cũ không còn. Vì vậy **không đổi selector bằng rollout tùy tiện**; hãy tạo tên subscription mới, kiểm tra backlog cũ và có kế hoạch chuyển đổi.

Selector chỉ thấy **JMS message properties/headers** mà provider hỗ trợ, không tự lọc JSON body bằng biểu thức SQL. Ví dụ phải đặt `eventType` vào property ở producer; viết `eventType` chỉ trong chuỗi JSON không đủ để selector trên hoạt động.

### Shared không đồng nghĩa với exactly-once

Một message được cấp cho một consumer tại một thời điểm thông thường, nhưng nếu consumer chết trước ACK hoặc transaction rollback, message có thể được giao lại cho consumer khác. Với nghiệp vụ gửi email, trừ tiền hoặc tạo vận đơn, dùng `eventId` cố định cùng unique constraint/idempotency key; không kỳ vọng tên “shared durable” tự loại bỏ mọi hiệu ứng trùng lặp.

## 4. Ma trận hỗ trợ: JMS API, client, broker và giao thức

**Kiểm tra tại ngày 17/11/2026:** Trang hỗ trợ JMS 2.0/Jakarta Messaging của ActiveMQ Classic vẫn liệt kê **Shared Topic Consumer** (AMQ-8323) ở mục đang phát triển, mục tiêu phiên bản `7.0.0` nhưng chưa có phiên bản hoàn tất. Trang download Classic tại thời điểm kiểm tra liệt kê dòng sản phẩm phát hành `6.4.x` và `5.19.x`, chưa liệt kê `7.0.0`. Đừng diễn giải “target version” thành “feature đã ra mắt”.

| Broker / client / API | Có thể dùng JMS shared subscription chuẩn? | Kết luận thực hành |
|---|---|---|
| **ActiveMQ Artemis** với Artemis JMS/Jakarta client tương thích, kết nối bằng giao thức được client hỗ trợ | **Có**, các phương thức JMS 2.0 shared được Artemis triển khai | Lựa chọn trực tiếp cho `createSharedConsumer` và `createSharedDurableConsumer` |
| **ActiveMQ Classic 5.18.x–5.19.x** và dòng client Classic `javax.jms` tương ứng | **Không nên giả định hỗ trợ**; bảng JMS 2.0 của Classic ghi shared topic consumer chưa hoàn tất | Dùng virtual topics/queue consumers nếu cần chia tải |
| **ActiveMQ Classic 6.x** với `activemq-client` dùng `jakarta.jms` | **Không nên giả định hỗ trợ**; Classic 6.x hỗ trợ một phần Jakarta Messaging 3.1, shared topic consumer vẫn được liệt kê chưa hoàn tất | Phải smoke-test đúng phương thức; virtual topics vẫn là phương án phổ biến |
| **Client hoặc ứng dụng chỉ có JMS 1.1 API** | **Không có các phương thức shared trong chuẩn JMS 1.1** | Nâng client/API nếu broker hỗ trợ, hoặc dùng queue/virtual topics |
| **Artemis broker + ActiveMQ Classic OpenWire JMS client** | **Không được suy từ broker Artemis mà kết luận client cũ hỗ trợ phương thức JMS shared** | Kiểm tra cả client và mapping giao thức; cân nhắc Artemis JMS client hoặc Artemis FQQN |
| **STOMP, MQTT, AMQP client không thông qua JMS API** | Không có bảo đảm tương đương phương thức `createSharedDurableConsumer` | Dùng cơ chế subscription, shared subscription hoặc queue riêng của từng protocol và kiểm thử broker tương ứng |

**Vấn đề cốt lõi:** khả năng hỗ trợ là giao điểm của **phiên bản API** × **implementation trong client** × **broker/provider** × **giao thức truyền** × **cấu hình destination/authorization**. Một phương thức có mặt lúc biên dịch vẫn có thể ném `UnsupportedOperationException` ở runtime; tài liệu Classic nêu rõ loại ngoại lệ này cho những chức năng JMS 2.0 chưa triển khai.

### Tránh nhầm phiên bản thư viện với namespace

| Thư viện/môi trường tiêu biểu | Namespace | Ý nghĩa |
|---|---|---|
| ActiveMQ Classic `activemq-client` 5.18.x | `javax.jms.*` | Một phần JMS 2.0; thiếu tính năng không được suy là đã hỗ trợ |
| ActiveMQ Classic `activemq-client-jakarta` ở nhánh chuyển tiếp 5.18.1+ | `jakarta.jms.*` | Phục vụ chuyển namespace cho remote client; **không biến** phương thức shared chưa triển khai thành có hỗ trợ |
| ActiveMQ Classic `activemq-client` 6.x | `jakarta.jms.*` | Một phần Jakarta Messaging 3.1; không còn dùng module chuyển tiếp `activemq-client-jakarta` như nhánh 5.18.x |
| Artemis `artemis-jms-client` ở nhánh API javax tương thích | `javax.jms.*` | Chọn theo phiên bản Artemis/JMS tương ứng |
| Artemis `artemis-jakarta-client` ở nhánh Jakarta tương thích | `jakarta.jms.*` | Dùng cho ví dụ Java 17 trong bài |

Các dòng trên mô tả **các nhánh điển hình theo tài liệu sản phẩm**, không thay thế bảng dependency của ứng dụng đang chạy. Maven có thể kéo lẫn `javax.jms` và `jakarta.jms` qua transitive dependency. Kiểm tra cây dependency và package import; không ép cast giữa hai API.

### Thủ tục xác nhận hỗ trợ trước khi triển khai

1. Ghi lại **broker product + phiên bản chạy**, **JMS provider jar + phiên bản**, **API package (javax/jakarta)** và **protocol/URL**.
2. Xác nhận compile được `createSharedDurableConsumer` trên client thực tế.
3. Chạy **hai process consumer** cùng tên subscription, cùng selector, không gán clientID cố định; cả hai phải đăng ký thành công.
4. Publish N message, kiểm tra mỗi `eventId` được nhóm đó xử lý một lần trong điều kiện không lỗi, và nhóm độc lập thứ hai cũng nhận đủ N message.
5. Dừng tất cả consumer, publish N message khác rồi khởi động lại; kiểm tra backlog dành cho **durable** subscription.
6. Cố tình rollback một message, quan sát redelivery, ACK, DLQ, số lượt giao và cách idempotency hoạt động.
7. Lặp lại kiểm tra sau mỗi lần nâng phiên bản broker hoặc client. Với Classic, kiểm tra riêng release notes/AMQ-8323 thay vì dựa vào số version.

Nếu kiểm tra số 2 thành công nhưng số 3 ném `UnsupportedOperationException`, chưa đủ điều kiện triển khai shared JMS API. Việc broker có chức năng queue nhiều consumer không tự làm cho phương thức shared JMS của client hoạt động.

## 5. Cấu hình Artemis để shared durable được tạo đúng

Bài lab giả định broker Artemis chạy local ở `tcp://127.0.0.1:61616`, chấp nhận CORE protocol và có user/password với quyền gửi, nhận, tạo durable queue. Đừng thay toàn bộ file `broker.xml`; chỉ đặt các **mảnh cấu hình vào đúng section có sẵn**.

### 5.1. Địa chỉ multicast cho JMS topic

Bên trong `<addresses>` của `ARTEMIS_INSTANCE/etc/broker.xml`:

~~~xml
<address name="orders.events">
    <multicast/>
</address>
~~~

Khi consumer dùng JMS API shared subscription, Artemis ánh xạ **mỗi subscription thành một multicast queue** trên address của topic. Các consumer cùng shared subscription kết nối vào **cùng queue**; subscription khác có queue riêng.

Không dùng `<anycast>` cho topic này chỉ vì bên trong subscription có nhiều worker: multicast quyết định nhân bản thông điệp **giữa các subscription**, còn queue và các consumer trên queue quyết định chia tải **trong subscription**.

~~~mermaid
flowchart TB
    T[(Artemis address: orders.events, multicast)]
    T --> Q1[(Queue: subscription notification)]
    T --> Q2[(Queue: subscription analytics)]
    Q1 --> W1[notification-1]
    Q1 --> W2[notification-2]
    Q2 --> W3[analytics-1]
    Q2 --> W4[analytics-2]
~~~

### 5.2. Quyền của ứng dụng

Nếu muốn hạn chế theo role `order-workers`, trong phần `<security-settings>` hiện có có thể cần các quyền tương ứng:

~~~xml
<security-setting match="orders.events">
    <permission type="send" roles="order-workers"/>
    <permission type="consume" roles="order-workers"/>
    <permission type="createDurableQueue" roles="order-workers"/>
    <permission type="deleteDurableQueue" roles="order-workers"/>
</security-setting>
~~~

Đây là ví dụ minh họa **quyền tối thiểu theo tác vụ thử nghiệm**, chưa bao gồm các quyền/role khác mà template broker có thể cần. Role phải được khai báo trong hệ thống xác thực của instance. Trong production nên tách quyền publisher, worker và operator; đặc biệt không cấp `deleteDurableQueue` cho worker thường nếu không cần quản lý vòng đời subscription.

Khi nhận lỗi không được phép tạo subscription, hãy kiểm tra quyền `createDurableQueue` trước khi cố xóa dữ liệu hay thay tên queue thủ công.

### 5.3. Có nên tự khai báo queue của shared subscription?

Đối với ứng dụng dùng JMS shared API, **thường nên để provider tạo subscription queue** và quản lý vòng đời qua `createSharedDurableConsumer`/`unsubscribe`. Queue name nội bộ có thể phụ thuộc clientID, subscription name và cơ chế ánh xạ của phiên bản; không tự đoán tên vật lý rồi đưa vào file.

Nếu cần **kiểm soát queue vật lý** hoặc tích hợp client legacy, Artemis có phương án khác qua **FQQN** (phần 8), nơi queue được định nghĩa tường minh. Phương án FQQN và shared JMS API có thể tạo cùng hiệu ứng phân phối nhưng **không đồng nhất về tên, đăng ký và vòng đời**.

## 6. Java/JMS thực hành: hai nhóm, mỗi nhóm nhiều worker

Để quan sát hành vi thật, triển khai một chương trình Java với bốn mode:

- `init`: tạo **hai shared durable subscription** rồi đóng consumer, giữ subscription tồn tại.
- `publish`: gửi 20 sự kiện trong một JMS transaction.
- `work <group> <workerName>`: một worker thuộc nhóm `notification` hoặc `analytics`; có thể chạy nhiều process cùng nhóm.
- `cleanup`: chỉ xóa subscription sau khi **mọi consumer đã dừng**, có quyết định bỏ backlog và quyền quản trị phù hợp.

### 6.1. Dependency và điều kiện

Ví dụ dùng Java 17, `jakarta.jms.*` và Artemis JMS client tương thích. Trong `pom.xml`, đặt một **phiên bản Artemis client thực tế** cho biến Maven `artemis.version`, ví dụ khớp bản đang kiểm chứng trong lab:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.57.0</artemis.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Số phiên bản trên dùng để định hướng môi trường thực hành theo tài liệu Artemis 2.57.0; khi sử dụng bản khác, đối chiếu mức Java yêu cầu, dependency Jakarta và broker compatibility trước khi chạy. Không sử dụng dependency `activemq-client` của Classic thay thế một cách tùy tiện.

Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` tương ứng với tài khoản đã được cấp quyền. Với cùng tên subscription shared, **không đặt clientID riêng theo worker**.

### 6.2. Mã nguồn đầy đủ

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Topic;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Set;
import java.util.UUID;

public final class SharedSubscriptionLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String TOPIC = "orders.events";
    private static final String SELECTOR = "eventType = 'OrderCreated'";
    private static final Set<String> GROUPS =
        Set.of("notification", "analytics");

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            usage();
            return;
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        switch (args[0]) {
            case "init":
                requireArgs(args, 1);
                for (String group : GROUPS) {
                    register(factory, user, password, group);
                }
                break;
            case "publish":
                requireArgs(args, 1);
                publish(factory, user, password, 20);
                break;
            case "work":
                requireArgs(args, 3);
                checkGroup(args[1]);
                work(factory, user, password, args[1], args[2]);
                break;
            case "cleanup":
                requireArgs(args, 1);
                cleanup(factory, user, password);
                break;
            default:
                usage();
        }
    }

    // Đăng ký trước để nhận sự kiện publish lúc không có worker.
    private static void register(
            ActiveMQConnectionFactory factory,
            String user, String password, String group) {
        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            Topic topic = ctx.createTopic(TOPIC);
            JMSConsumer consumer = ctx.createSharedDurableConsumer(
                topic, group, SELECTOR);
            consumer.close(); // Durable subscription vẫn tồn tại.
            System.out.println("Đã tạo shared durable group: " + group);
        }
    }

    private static void publish(
            ActiveMQConnectionFactory factory,
            String user, String password, int count) throws JMSException {
        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Topic topic = ctx.createTopic(TOPIC);
            try {
                for (int i = 1; i <= count; i++) {
                    TextMessage msg = ctx.createTextMessage(
                        "{\"orderId\":\"ORD-" + i + "\"}");

                    msg.setStringProperty(
                        "eventId", UUID.randomUUID().toString());
                    msg.setStringProperty("eventType", "OrderCreated");
                    msg.setIntProperty("seq", i);

                    ctx.createProducer()
                        .setDeliveryMode(DeliveryMode.PERSISTENT)
                        .send(topic, msg);
                }
                ctx.commit(); // Commit lô 20 message.
                System.out.println("Đã publish " + count + " sự kiện.");
            } catch (RuntimeException ex) {
                ctx.rollback();
                throw ex;
            }
        }
    }

    private static void work(
            ActiveMQConnectionFactory factory,
            String user, String password,
            String group, String workerName) throws Exception {
        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Topic topic = ctx.createTopic(TOPIC);
            JMSConsumer consumer = ctx.createSharedDurableConsumer(
                topic, group, SELECTOR);

            int idlePolls = 0;
            while (idlePolls < 8) {
                Message msg = consumer.receive(1500);
                if (msg == null) {
                    idlePolls++;
                    continue;
                }
                idlePolls = 0;

                try {
                    if (!(msg instanceof TextMessage)) {
                        throw new IllegalArgumentException(
                            "Chỉ hỗ trợ TextMessage trong ví dụ");
                    }

                    TextMessage body = (TextMessage) msg;
                    String eventId = body.getStringProperty("eventId");
                    int seq = body.getIntProperty("seq");

                    // Chỉ ghi log trong lab; production cần
                    // idempotency với eventId trong transaction nghiệp vụ.
                    System.out.printf(
                        "[%s/%s] seq=%d eventId=%s body=%s%n",
                        group, workerName, seq, eventId, body.getText());

                    Thread.sleep(60); // Giả lập xử lý.
                    ctx.commit(); // Xác nhận xử lý thành công.
                } catch (Exception ex) {
                    ctx.rollback(); // Cho phép redelivery.
                    System.err.println("Rollback: " + ex.getMessage());
                }
            }
            consumer.close();
        }
    }

    // Chỉ chạy sau khi đã dừng tất cả worker trong mọi group
    // và chủ động quyết định xóa backlog còn lại.
    private static void cleanup(
            ActiveMQConnectionFactory factory,
            String user, String password) {
        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            for (String group : GROUPS) {
                ctx.unsubscribe(group);
                System.out.println("Đã unsubscribe " + group);
            }
        }
    }

    private static void checkGroup(String group) {
        if (!GROUPS.contains(group)) {
            throw new IllegalArgumentException("Group không hợp lệ: " + group);
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + name);
        }
        return value;
    }

    private static void requireArgs(String[] args, int expected) {
        if (args.length != expected) {
            throw new IllegalArgumentException(
                "Cần đúng " + (expected - 1) + " đối số cho " + args[0]);
        }
    }

    private static void usage() {
        System.out.println("SharedSubscriptionLab init");
        System.out.println("SharedSubscriptionLab publish");
        System.out.println(
            "SharedSubscriptionLab work <notification|analytics> <workerName>");
        System.out.println("SharedSubscriptionLab cleanup");
    }
}
~~~

**Cần lưu ý khi chạy code:**

- Mỗi tiến trình `work` tạo **JMSContext và kết nối riêng**. Không chia sẻ một `JMSContext` hoặc `Session` giữa nhiều thread vì API session thông thường không an toàn để gọi đồng thời.
- Các lời gọi `createSharedDurableConsumer` luôn dùng cùng `TOPIC`, cùng tên group và cùng `SELECTOR`. Không gán clientID để các process có thể tham gia cùng subscription.
- `publish` dùng transaction và persistent delivery. Nếu process lỗi trước `commit`, gửi không được xác nhận là thành công. Nếu lỗi kết nối xảy ra đúng lúc commit, bên gửi có thể không biết chắc kết quả; idempotency vẫn cần thiết.
- Hai worker cùng nhóm đều có thể nhận message; **không yêu cầu mỗi worker đúng 10 message**. Phân phối phụ thuộc timing, prefetch/window, tốc độ worker và chính sách broker.
- Phần `work` dùng idle timeout để demo kết thúc tự động. Trong dịch vụ thật, consumer thường chạy liên tục và có vòng đời graceful shutdown.
- Phương thức `cleanup` xóa durable subscription cùng backlog chưa nhận; không chạy nếu vẫn còn consumer hoặc còn giao dịch/ack chưa hoàn tất.

### 6.3. Kịch bản chạy và kết quả cần quan sát

Sau khi build/run lớp trên bằng IDE hoặc công cụ Java của dự án:

1. Chạy một process với `init`. Hai subscription `notification` và `analytics` được tạo rồi đóng consumer.
2. Khi **không có worker** đang chạy, gọi `publish`. Mỗi nhóm durable có thể giữ 20 message phù hợp với selector.
3. Khởi động gần như đồng thời bốn process:
   - `work notification N1`
   - `work notification N2`
   - `work analytics A1`
   - `work analytics A2`
4. Tổng các dòng log cho `notification` phải đại diện cho 20 `eventId` được xử lý; `analytics` cũng đại diện cho 20 `eventId`. Mỗi nhóm có hai process nhưng hai process **không được cùng xử lý một event như hai subscription khác nhau** trong đường đi thành công, không có retry.
5. Chạy `publish` lần nữa lúc hai worker của mỗi nhóm đang hoạt động để quan sát phân phối trực tiếp. Quan sát queue depth, consumer count và ACK trong console/JMX của broker.
6. Sau khi tất cả worker dừng, có thể publish thêm một lô; durable subscription giữ backlog. Đối chiếu với shared non-durable ở phần 7.
7. Chỉ khi không cần giữ dữ liệu thử nghiệm nữa, dừng mọi worker rồi gọi `cleanup`.

Khi xác minh, sử dụng **eventId** làm khóa đối chiếu, không chỉ đếm số log. Một event có thể xuất hiện hai lần vì rollback và redelivery; tổng log lớn hơn 20 không tự chứng minh nhóm nhận nhiều hơn một bản sao logic.

## 7. Thử shared non-durable để thấy ranh giới vòng đời

Không cần viết lại chương trình đầy đủ. Thay lời gọi tạo consumer trong nhánh worker:

~~~java
JMSConsumer consumer = ctx.createSharedConsumer(
    topic, "lab.live.notification", SELECTOR);
~~~

Cho **hai consumer hoạt động đồng thời** với cùng tên `lab.live.notification`, publish 10 message và quan sát hai consumer chia tải. Sau đó đóng **cả hai** consumer; publish tiếp 5 message. Khi tạo lại shared non-durable consumer cùng tên, **5 message đã gửi lúc không consumer nào hoạt động không thuộc backlog của subscription cũ**.

Điều này khác với shared durable subscription: đóng consumer cuối **không** xóa subscription durable; nó tiếp tục giữ message phù hợp cho lần kết nối tiếp theo.

| Trạng thái | Shared non-durable | Shared durable |
|---|---|---|
| Publish khi còn ít nhất một consumer của nhóm | Có thể nhận và phân phối trong nhóm | Có thể nhận và phân phối trong nhóm |
| Publish khi consumer cuối đã đóng | Không tích lũy cho nhóm | Tích lũy nếu subscription tồn tại và message còn hợp lệ |
| Tạo lại cùng tên sau khi nhóm đã vắng mặt | Tạo subscription mới, không có lịch sử cũ | Tiếp tục subscription đã có |
| Muốn xóa hẳn | Thường đóng consumer cuối là đủ | Gọi `unsubscribe` khi không còn consumer/ACK/transaction pending |
| Muốn scale nhiều worker | Cả hai hỗ trợ khi broker/client triển khai shared API | Cả hai hỗ trợ khi broker/client triển khai shared API |

## 8. Khi không dùng được JMS 2.0 shared API: Classic Virtual Topic và Artemis FQQN

### 8.1. ActiveMQ Classic: Virtual Topic + competing queue consumers

ActiveMQ Classic có cơ chế **Virtual Topics** để mô phỏng ý tưởng fan-out giữa nhóm và chia tải trong nhóm bằng queue, phù hợp khi client/broker Classic chưa hỗ trợ phương thức shared JMS 2.0.

Với quy ước mặc định thường gặp:

- Publisher gửi JMS Topic `VirtualTopic.Orders`.
- Worker Notification cùng consume JMS Queue `Consumer.Notification.VirtualTopic.Orders`.
- Worker Analytics cùng consume JMS Queue `Consumer.Analytics.VirtualTopic.Orders`.

~~~mermaid
flowchart LR
    P[Classic JMS producer] --> T[(VirtualTopic.Orders)]
    T --> QN[(Consumer.Notification.VirtualTopic.Orders)]
    T --> QA[(Consumer.Analytics.VirtualTopic.Orders)]
    QN --> N1[Notification 1]
    QN --> N2[Notification 2]
    QA --> A1[Analytics 1]
    QA --> A2[Analytics 2]
~~~

Mã consumer ở Classic dùng **JMS Queue** thay vì gọi shared topic API:

~~~java
// Mã minh họa với javax.jms.* và ActiveMQ Classic client phù hợp:
Queue queue = session.createQueue(
    "Consumer.Notification.VirtualTopic.Orders");

MessageConsumer consumer = session.createConsumer(queue);
~~~

Bên Analytics thay `Notification` bằng `Analytics`. Mỗi queue logic nhận bản sao sự kiện từ Virtual Topic và nhiều consumer trên queue cạnh tranh lấy việc. Đây là tính năng **Classic Virtual Destinations**, không phải chính API `createSharedDurableConsumer` của JMS 2.0.

**Cần kiểm tra trước khi dùng:** broker phải bật/giữ đúng quy tắc Virtual Topic; tên destination có thể đã được tùy chỉnh; queue của nhóm nên được tạo/đăng ký trước lúc publisher gửi message cần giữ; selector-aware policy có thể ảnh hưởng backlog khi consumer offline. Ở hệ thống có nhiều Classic brokers, cần kiểm tra network bridge để tránh chuyển tiếp cả virtual topic lẫn consumer queues gây xử lý lặp.

### 8.2. Artemis: multicast subscription queue + FQQN

Nếu client cũ không dùng được JMS shared API nhưng broker đích là Artemis, có thể khai báo tường minh **queue trên multicast address** và truy cập queue bằng Fully Qualified Queue Name (FQQN).

Bên trong `<addresses>` của `broker.xml`:

~~~xml
<address name="orders.events">
    <multicast>
        <queue name="orders.notification" max-consumers="4">
            <durable>true</durable>
        </queue>
        <queue name="orders.analytics">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
~~~

Hai Java consumers của Notification có thể dùng:

~~~java
// Dùng với provider/client JMS tương thích FQQN của Artemis:
Queue subscriptionQueue =
    session.createQueue("orders.events::orders.notification");

MessageConsumer consumer =
    session.createConsumer(subscriptionQueue);
~~~

Nhóm Analytics dùng `orders.events::orders.analytics`. Với cấu hình trên, mỗi message multicast được chuyển vào hai queue, và các consumer trên mỗi queue chia tải như queue thông thường.

**Ba khác biệt phải nêu rõ:**

1. FQQN là **cú pháp truy cập trực tiếp queue** qua Artemis address model, không bảo đảm queue được xem là một JMS shared subscription tạo bằng API cùng tên.
2. `max-consumers="4"` là giới hạn số consumer đồng thời của queue, không phải lệnh “chia đều 4 phần” và không bắt buộc dùng giá trị 4.
3. Tuổi thọ, tạo/xóa queue và phân quyền được quản lý theo **queue vật lý**. Không tùy tiện gọi `unsubscribe("orders.notification")` rồi mong broker xóa queue khai báo thủ công giống như một subscription JMS.

Artemis có hướng dẫn migration Virtual Topics từ Classic sang FQQN/OpenWire wildcard mapping. Khi chuyển hệ thống, phải kiểm tra naming và cơ chế bridge bằng integration test; không chỉ đổi connection URL rồi coi mọi consumer giữ nguyên semantics.

### 8.3. Chọn phương án theo điều kiện

| Điều kiện thực tế | Phương án ưu tiên |
|---|---|
| Artemis broker + Artemis JMS 2.0/Jakarta client hỗ trợ | `createSharedDurableConsumer` (hoặc `createSharedConsumer` nếu chấp nhận không giữ lúc offline) |
| Classic broker + Classic client 5.x/6.x chưa có shared API theo matrix | Virtual Topic, mỗi nhóm một queue, nhiều worker trên queue |
| Artemis broker nhưng app dùng JMS 1.1 hoặc cần tên queue cố định | Multicast queue + FQQN, kiểm chứng giao thức client |
| Chỉ một nhóm xử lý công việc, không cần phát cho nhiều nhóm | JMS Queue + competing consumers có thể đơn giản hơn topic shared |
| Đòi hỏi replay sự kiện theo offset ở nhiều thời điểm tùy ý | Đánh giá event log/bus khác hoặc cơ chế lưu trữ sự kiện riêng; durable JMS subscription không tự cung cấp replay tùy ý |

## 9. Giới hạn vận hành ngay cả khi shared subscription hoạt động

### 9.1. Tăng consumer không làm mất giới hạn throughput

Shared subscription giúp song song hóa việc xử lý nhưng tổng throughput vẫn bị chặn bởi CPU, DB, API downstream, khả năng broker và tốc độ producer. Nếu publisher tăng 3.000 event/giây còn nhóm Notification chỉ xử lý 2.000 event/giây, backlog của **subscription Notification** tăng khoảng 1.000 event/giây dù Analytics xử lý kịp. Hai nhóm phải có chỉ số SLA, backlog và cảnh báo riêng.

### 9.2. Không mặc định đảm bảo thứ tự xử lý toàn cục

Khi hai worker nhận event số 11 và 12 gần nhau, event 12 có thể xử lý/commit trước 11. Có thể dùng `JMSXGroupID` hoặc cấu hình grouping của provider để định tuyến các message cùng khóa vào cùng consumer trong một số trường hợp, nhưng cần kiểm tra hỗ trợ/version, failover và tác động đến throughput; nhóm message không tự đảm bảo thứ tự tổng quát khi có nhiều nguồn xuất bản.

Nghiệp vụ phụ thuộc thứ tự nên xác minh `aggregateId`/`version` ở nơi ghi trạng thái và xử lý sự kiện đến muộn. Chẳng hạn `OrderCancelled` đến sau `OrderShipped` không được âm thầm ghi đè trạng thái đã giao hàng.

### 9.3. Acknowledgment, transaction và redelivery

Với một shared subscription, ACK từ consumer chỉ xác nhận message đã được xử lý trong **subscription đó**, không xác nhận message đã được nhóm khác xử lý. Khi worker rollback/crash, cùng message có thể được giao lại cho worker khác trong **cùng nhóm**.

Một quy trình an toàn ở bên nhận có thể là:

1. Lấy `eventId` và dữ liệu cần xử lý từ message.
2. Trong transaction DB, ghi `processed_messages(event_id, group_name)` với unique constraint **và** thực hiện tác động nghiệp vụ.
3. DB commit thành công thì JMS commit/ACK.
4. Nếu message bị giao lại, transaction DB phát hiện cặp `(eventId, groupName)` đã xử lý và bỏ qua tác động lần hai rồi ACK.

Không lấy `eventId` riêng lẻ làm khóa dùng chung cho mọi nhóm nếu hai nhóm có bảng idempotency dùng chung: Notification đã xử lý không được khiến Analytics bỏ qua event hợp lệ của mình.

Nếu consumer thực hiện hành động ngoài DB như gửi email hoặc gọi API đối tác, cần idempotency key mà downstream hiểu, hoặc cơ chế outbox riêng cho side effect. Một transaction JMS **không tự làm** HTTP request và DB transaction trở thành nguyên tử.

### 9.4. Retry, poison message và DLQ theo nhóm

Nếu một event không hợp lệ khiến Notification rollback liên tục, DLQ/giới hạn redelivery cần bảo vệ nhóm Notification mà không khiến Analytics bị kẹt. Trên Artemis, các queue subscription cùng một address có thể chịu address-settings chung; khi cần chính sách phân loại lỗi khác nhau, cân nhắc queue/route riêng theo kiến trúc và khả năng cấu hình thực tế.

Theo dõi tối thiểu:

- Số queue/subscription đang tồn tại và số consumer trên từng subscription.
- Message count/backlog và **tuổi message cũ nhất** của từng queue.
- Enqueue/dequeue/ACK rate, redelivery count và DLQ growth.
- Số lượng message được xử lý **duy nhất theo eventId + group**, không chỉ lượt nhận.
- Dung lượng broker, address-full policy, paging/journal và độ trễ từ publish đến hoàn tất ở từng nhóm.

Tránh tự động tạo subscription name khác nhau cho từng lần deploy hoặc từng pod. Với durable subscription, những subscription bị bỏ quên có thể giữ message liên tục, tiêu tốn đĩa mà không consumer nào tiêu thụ.

## 10. Các lỗi đặc thù và cách phân biệt

| Triệu chứng | Khả năng xảy ra | Kiểm tra |
|---|---|---|
| `UnsupportedOperationException` ngay tại `createSharedDurableConsumer` | Client Classic chưa triển khai JMS shared API dù compile được | Đối chiếu provider jar/version với Classic JMS2 feature matrix; dùng Artemis provider hoặc Virtual Topics |
| `ClassNotFoundException` / `NoSuchMethodError` / lỗi import | Dependency JMS 1.1 hoặc trộn `javax.jms`/`jakarta.jms` | Maven dependency tree và version thực sự trong runtime |
| Hai worker “cùng nhóm” mỗi người nhận đủ mọi event | Chúng đã tạo **hai subscription khác nhau** | Kiểm tra clientID, subscription name, loại durable và topic |
| Worker không được tạo thêm subscription | Trùng clientID, selector/topic khác, loại shared/unshared không khớp | Kiểm tra identity và consumer đang hoạt động |
| Shared subscription được tạo nhưng không nhận sự kiện cũ | Subscription được tạo **sau** khi publish | Khởi tạo durable group trước khi phát event; không coi topic là event log |
| Sau restart mất message | Dùng shared non-durable, non-persistent message hoặc cấu hình lưu trữ không bền | Xác nhận `createSharedDurableConsumer`, persistent delivery, broker persistence/TTL |
| Chỉ một worker bận, các worker khác ít việc | Prefetch/window, nhóm quá nhỏ, chi phí xử lý khác nhau | Quan sát consumer counts/rates; không suy chia đều |
| Khi thêm worker, throughput giảm | DB/API downstream bị quá tải hoặc tranh chấp | Điều tiết concurrency, connection pool, rate limit |
| Lỗi permission khi tạo subscription | Thiếu quyền tạo durable queue trên Artemis | Kiểm tra `security-settings` và role của user |
| Unsubscribe không được | Còn consumer đang mở hoặc message unacked/transaction pending | Đóng worker, xử lý transaction và quyết định bỏ backlog trước khi xóa |

## 11. Bài tập kiểm chứng kiến thức

**Bài 1 — Chẩn đoán nhân bản:** Một publisher phát 30 sự kiện. Hai service chạy cùng topic với tên subscription là `email-v1` và `email-v2`. Mỗi service xử lý được 30 event. Đây có phải “shared group hai worker” không? Hãy chỉ ra cách đổi tên subscription và cấu hình để hai worker **cộng lại** xử lý 30 message.

**Bài 2 — Mất message khi offline:** Một nhóm dùng `createSharedConsumer`, toàn bộ process dừng 10 phút trong khi producer vẫn publish. Tại sao khi bật lại nhóm chỉ nhận sự kiện mới? Thay sang `createSharedDurableConsumer` cần lưu ý điều gì về thời điểm tạo subscription, persistence và việc xóa subscription?

**Bài 3 — So sánh broker:** Một ứng dụng `javax.jms` chạy ActiveMQ Classic 5.18.x, compile được phương thức shared nhưng runtime ném `UnsupportedOperationException`. Tại sao nâng dependency lên nhánh có JMS 2.0 API chưa đủ? Nêu hai đường đi: nâng cả stack đã kiểm chứng hoặc dùng Virtual Topic + queue consumers.

**Bài 4 — Không thấy queue trong Artemis:** Một producer gửi vào `orders.events` nhưng chưa có subscription/queue nào cho nhóm Analytics. Theo mô hình multicast, message có được giữ đợi Analytics đến sau không? Hãy đề xuất cách đăng ký durable subscription trước khi publish.

**Bài 5 — Duplicate và ordering:** Worker N1 xử lý `OrderCreated/E-42` thành công trong DB nhưng chết trước JMS commit; N2 nhận lại E-42. Phác thảo transaction DB có unique constraint `(event_id, consumer_group)` và một phương án bảo vệ việc gửi email thực tế.

### Tiêu chí hoàn thành

Bạn chỉ nên kết luận “ứng dụng hỗ trợ shared durable subscription” khi đã chứng minh được **hai consumer đồng thời trên cùng subscription, một bản sao logic mỗi event trong nhóm, fan-out độc lập giữa nhóm, giữ message lúc mọi worker offline và phục hồi sau rollback**. Đồng thời ghi nhận rõ broker/client/protocol/version của phép thử; câu trả lời “JMS 2.0 nên chắc chắn có” là chưa đủ.

## Tài liệu chính thức để đối chiếu phiên bản

- [ActiveMQ Classic — Jakarta Messaging 3.1 & JMS 2.0 Support](https://activemq.apache.org/components/classic/documentation/jms2): bảng tiến độ và tình trạng AMQ-8323.
- [ActiveMQ Classic — Download](https://activemq.apache.org/components/classic/download/): các dòng Classic đã phát hành.
- [ActiveMQ Classic — Virtual Destinations](https://activemq.apache.org/components/classic/documentation/virtual-destinations): convention của Virtual Topic và consumer queues.
- [ActiveMQ Artemis — Virtual Topics Migration](https://artemis.apache.org/components/artemis/migration-documentation/VirtualTopics.html): shared subscriptions và đường chuyển sang FQQN.
- [ActiveMQ Artemis — Mapping JMS Concepts to the Core API](https://artemis.apache.org/components/artemis/documentation/latest/jms-core-mapping.html): một subscription topic tương ứng một multicast queue.
- [ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): multicast queues, FQQN, `max-consumers`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): ràng buộc shared/non-shared, durable/non-durable, identity, selector và vòng đời subscription.

**Kết luận thực hành:** Shared subscription mang lại mô hình “**mỗi nhóm nhận một bản sao, nhiều worker cùng nhóm chia tải**”. Để dùng đúng, bạn phải chọn shared hay unshared, durable hay non-durable, xác định rõ danh tính subscription và kiểm chứng tính năng trên **cả client lẫn broker**. Artemis hỗ trợ các API shared JMS; với ActiveMQ Classic 5.x/6.x cần dựa vào bảng hỗ trợ chính thức và ưu tiên Virtual Topics khi shared API chưa có. Dù chọn phương án nào, reliability vẫn phụ thuộc message persistence, idempotency, retry/DLQ và quan sát vận hành.
