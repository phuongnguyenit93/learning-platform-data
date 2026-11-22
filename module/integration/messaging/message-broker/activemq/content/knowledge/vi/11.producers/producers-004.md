# Ranh giới giữa send thành công và nghiệp vụ phía consumer hoàn tất

> **Chương:** Producer  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ bằng queue/topic, định tuyến, JMS; thực hành producer/consumer, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi bài:** Làm rõ chính xác **producer đã hoàn thành thao tác nào** khi `send()` trả về hoặc giao dịch JMS commit, và **chưa thể khẳng định điều gì** về consumer hay tác dụng nghiệp vụ. Ví dụ chạy trên Artemis với `jakarta.jms`; các nguyên tắc được đối chiếu với ActiveMQ Classic khi cần.

## 1. Một lệnh `send()` thành công nói lên điều gì?

Một API nhận yêu cầu tạo vận đơn, gửi message `shipping.create` vào ActiveMQ rồi trả kết quả:

~~~java
producer.send(queue, message);
return "Đã tạo vận đơn"; // Phát biểu quá mức
~~~

Lỗi thiết kế ở đây là **đánh đồng hai sự kiện**:

- **Sự kiện A — gửi/ghi nhận yêu cầu:** phần mềm phía producer hoàn thành thao tác publish theo contract của JMS provider, hoặc đã commit transaction gửi message.
- **Sự kiện B — hoàn tất nghiệp vụ:** một consumer đã nhận được yêu cầu, áp dụng thay đổi vào hệ thống nghiệp vụ, và hệ thống có thể chứng minh kết quả đó.

A không kéo theo B. Consumer có thể đang offline, queue có backlog, message chưa tới consumer, callback lỗi, message hết hạn, bị chuyển DLQ, hoặc nghiệp vụ đã commit nhưng ACK JMS vẫn chưa được xác nhận.

Ví dụ: trong ngày cao điểm, API tạo yêu cầu shipping và broker nhận message trong 15 ms; worker phải chờ 30 phút do hãng vận chuyển bị giới hạn tốc độ. `send()` có thể trả thành công từ lâu nhưng vận đơn chưa tồn tại. Nếu frontend hiển thị **"Đã tạo vận đơn"** ngay, trạng thái cung cấp cho khách không phản ánh thực tế.

**Hợp đồng phản hồi hợp lý:** `202 Accepted` hoặc trạng thái `PENDING` khi chỉ mới ghi nhận yêu cầu; chỉ công bố `COMPLETED` sau khi có bằng chứng nghiệp vụ thực sự hoàn tất. Nếu một HTTP API trả `201 Created`, phải nói rõ **đã tạo resource nào** (ví dụ bản ghi yêu cầu) chứ không ngầm hứa tác vụ nền đã hoàn tất.

## 2. Các mốc xác nhận trên một đường đi

~~~mermaid
sequenceDiagram
    participant API as Order API / Producer
    participant B as ActiveMQ broker
    participant W as Shipping consumer
    participant DB as Business DB

    API->>B: send shipping.create (eventId=E42)
    Note over API,B: Mốc P: send/producer transaction thành công
    B-->>API: Xác nhận theo client/protocol/transaction
    Note over API,W: Consumer có thể chưa online
    B->>W: Deliver E42
    Note over B,W: Mốc D: message được giao, chưa chứng minh đã xử lý
    W->>DB: Ghi vận đơn + eventId trong DB transaction
    DB-->>W: DB commit thành công
    Note over W,DB: Mốc B: tác dụng nghiệp vụ đã được DB commit
    W->>B: JMS ACK/commit
    Note over W,B: Mốc A: broker ghi nhận việc hoàn tất delivery
    W-->>API: Không có phản hồi tự động qua JMS send
~~~

| Mốc | Bằng chứng quan sát | Có thể khẳng định | Chưa thể khẳng định |
|---|---|---|---|
| **P0 — producer gọi `send`** | Hàm được gọi | Ứng dụng đã thử publish | Broker đã nhận hay chưa |
| **P1 — `send` trả bình thường** | Không có exception từ thao tác send | Thao tác gửi hoàn tất theo semantics của client/provider tại thời điểm đó | Message đã được worker nhận hoặc xử lý |
| **P2 — producer JMS transaction commit trả thành công** | `session.commit()` / `JMSContext.commit()` thành công | Giao dịch JMS phía producer được provider xác nhận commit | Consumer đã hoàn tất, DB của consumer đã commit |
| **Q — message đã vào queue phù hợp** | Queue/binding, enqueue count hoặc message trong queue | Broker đã route/lưu message vào destination theo cấu hình | Có consumer nào đang nhận hoặc xử lý thành công |
| **D — broker giao message** | Message delivery/in-flight hoặc `receive()` / `onMessage()` | Consumer nhận một delivery | Nghiệp vụ đã commit |
| **B — business commit** | DB transaction commit + trạng thái nghiệp vụ được đọc xác nhận | Tác dụng nghiệp vụ thuộc transaction đó đã hoàn thành | Broker đã nhận ACK; side effect bên ngoài DB luôn hoàn tất |
| **A — JMS ACK/commit hoàn thành** | Commit/ACK phía consumer và broker state | Broker có thể đánh dấu delivery đã được xử lý theo JMS | Mọi hệ thống bên ngoài đều đạt trạng thái mong muốn |

**Thứ tự giữa B và A cần được thiết kế:** khi dùng DB transaction và JMS transaction tách rời, thường **DB commit trước, JMS ACK commit sau**. Khoảng cách giữa hai mốc tạo khả năng redelivery. Nếu đảo lại và ACK trước DB commit, process crash có thể làm mất yêu cầu dù nghiệp vụ chưa hoàn tất.

Một message không nhất thiết đi hết đường này: nó có thể bị expire, không được route tới queue, bị rollback nhiều lần rồi vào DLQ, hoặc chờ rất lâu khi consumer offline. Vì vậy số `sent` không thể dùng làm số `business completed`.

### 2.1. `send()` trả về không phải ACK nghiệp vụ

Một số thư viện hoặc cấu hình client có cơ chế xác nhận gửi đồng bộ với broker; cơ chế khác có thể buffer/asynchronous send, hay hoãn kết quả bền vững cho tới transaction commit. Mức khẳng định **phụ thuộc vào**:

- Sync/async send và chính sách chờ response của client/provider.
- `DeliveryMode.PERSISTENT` hay `NON_PERSISTENT`.
- Session có transaction hay không, và thao tác **commit** đã xảy ra chưa.
- Chính sách persistence, journal, sync, replication, HA và trạng thái broker.
- Việc address/queue tồn tại, routing, security, expiry và chính sách khi không route được.

Không suy từ chữ “success” ra “đã ghi ổn định trên nhiều broker và worker hoàn thành”. Cần nêu rõ **success của thao tác nào**, ở **mức bảo đảm nào**.

## 3. Ba lớp transaction độc lập cần phân biệt

### 3.1. Producer-side JMS transaction

Trong một session JMS transacted:

~~~java
producer.send(queue, message); // Đưa thao tác send vào JMS transaction
session.commit();              // Commit transaction gửi
~~~

`send()` trả bình thường **trước** `commit()` không đủ để kết luận message đã được publish như một giao dịch hoàn tất. Nếu `rollback()`, send trong transaction chưa commit sẽ bị hủy theo JMS contract. Nếu mạng lỗi tại thời điểm commit, client có thể không biết chắc broker đã commit hay chưa; retry có thể tạo bản message thứ hai.

### 3.2. Business database transaction

Transaction DB của Order API lưu đơn hàng; transaction DB của Shipping worker tạo vận đơn. Hai transaction này **không tự nằm trong cùng giao dịch với JMS transaction**, dù cùng chạy trong một phương thức Java.

Ví dụ:

~~~text
Order API DB COMMIT ----> Producer JMS COMMIT
        ^                         ^
        |                         |
       DB riêng             Broker/JMS riêng
~~~

Sau DB commit, trước JMS commit, ứng dụng có thể chết. Đơn hàng tồn tại nhưng chưa có request shipping. Ngược lại, nếu publish trước DB commit rồi DB rollback, worker có thể nhận một `orderId` không hợp lệ. Đây là bài toán **dual write**; giải pháp thông dụng là **transactional outbox**.

### 3.3. Consumer-side JMS transaction

Consumer nhận message, chạy business handler, rồi ACK trong session transacted:

~~~text
Consumer RECEIVE -> Business DB COMMIT -> JMS ACK COMMIT
                             |                 |
                       tác dụng nghiệp vụ     trạng thái delivery
~~~

Nếu chết sau DB commit nhưng trước JMS ACK commit, broker có thể redeliver. Vì vậy cần **idempotent consumer** dựa vào một `eventId` ổn định đã được lưu/kiểm tra trong cùng DB transaction với tác dụng nghiệp vụ.

**Không có một transaction JMS đơn lẻ nào tự bao phủ DB + broker + API hãng vận chuyển.** XA có thể phối hợp một số resource tương thích nhưng tăng yêu cầu tích hợp và vận hành; không nên hứa exactly-once cho các side effect ngoài phạm vi transaction.

## 4. Delivery mode, timeout và sự mơ hồ sau sự cố

### 4.1. `PERSISTENT` là yêu cầu lưu bền, không phải bằng chứng nghiệp vụ

Với JMS:

~~~java
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.send(message);
~~~

`PERSISTENT` yêu cầu provider xử lý message theo chế độ bền vững. Giá trị này có ích khi broker restart, nhưng **không cho biết** worker đã làm gì và cũng không thay thế cấu hình broker storage/replication. Một queue không bền vững, chính sách expiry, thiếu routing hoặc sự cố mất cả storage đều ảnh hưởng đến kết quả.

Muốn xác minh độ bền của broker phải có bài test **broker restart và recovery**, gắn với cấu hình storage cụ thể. Muốn xác minh nghiệp vụ đã hoàn tất phải kiểm tra **business state**.

### 4.2. “Exception khi gửi” không đồng nghĩa chắc chắn chưa nhận

~~~text
Producer                       Broker
   |  send(E42)                  |
   |---------------------------->|
   |                             | Accept/commit E42
   |    phản hồi commit OK       |
   X<----------------------------| mạng đứt trước khi client thấy phản hồi
   |
   | retry E42 ---> có thể xuất hiện thêm một delivery
~~~

Nếu client nhận timeout hoặc exception tại ranh giới network, kết quả có thể **không xác định**: broker có thể đã commit, có thể chưa. Vì thế:

- Không tạo **eventId mới** mỗi lần retry cùng một yêu cầu nghiệp vụ.
- Bên nhận phải dedup theo eventId hoặc khóa nghiệp vụ ổn định.
- Producer nên có trạng thái trung gian như `UNKNOWN` / `RETRY_PENDING` khi thiếu bằng chứng, thay vì ghi cứng “gửi thất bại và chắc chắn chưa tới broker”.
- Nếu cần chứng minh kết quả đầu cuối, tạo cơ chế theo dõi trạng thái nghiệp vụ độc lập.

### 4.3. Gửi bất đồng bộ có nhiều loại “completion”

JMS 2.0+ có API asynchronous send qua `JMSProducer.setAsync(CompletionListener)`. Callback `onCompletion` cho biết **thao tác send** đã hoàn tất theo JMS provider, còn `onException` báo lỗi thao tác đó. Nó **không** cho biết consumer chạy xong, không thay thế commit transaction và không phải ACK nghiệp vụ.

Đặc biệt với session transacted, cần phân biệt callback hoàn tất send với **transaction commit** và tránh điều khiển transaction/session sai luồng từ callback. Trong bài lab ta dùng **transacted send đồng bộ** để các mốc rõ ràng hơn.

Với **ActiveMQ Classic 5.x**, các tùy chọn client như `useAsyncSend` hoặc `alwaysSyncSend` cũng ảnh hưởng thời điểm producer chờ broker. Những tùy chọn là chi tiết của Classic client, **không phải chuẩn JMS**, và dù đặt `alwaysSyncSend=true` cũng **không đồng nghĩa consumer đã hoàn thành**. Không bê nguyên tùy chọn Classic sang client Artemis.

## 5. Thực hành: thấy producer thành công trước khi consumer chạy

Bài lab dùng **Artemis 2.40.0**, **JDK 17**, API **Jakarta Messaging 3.1**, queue `shipping.commands` kiểu ANYCAST. Cần một broker Artemis đang chạy, endpoint `tcp://127.0.0.1:61616` hỗ trợ client Artemis native, và user có quyền `send` / `consume`.

### 5.1. Cấu hình broker: route vào đúng queue

Trích đoạn **đặt bên trong `<addresses>` hiện hữu** của Artemis `broker.xml`:

~~~xml
<address name="shipping.commands">
    <anycast>
        <queue name="shipping.commands" durable="true"/>
    </anycast>
</address>
<address name="DLQ">
    <anycast>
        <queue name="DLQ"/>
    </anycast>
</address>
~~~

Nếu đã có address/queue, kiểm tra binding thay vì thêm trùng. Với Artemis, producer gửi tới **address** và queue chịu quyết định routing; trong ví dụ JMS queue tên `shipping.commands` ánh xạ đến address/queue cùng tên.

Trích đoạn **đặt trong `<address-settings>` hiện hữu** và hợp nhất với rule cùng `match` nếu có:

~~~xml
<address-setting match="shipping.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>2000</redelivery-delay>
</address-setting>
~~~

Cấu hình này cho phép quan sát: sau khi consumer rollback nhiều lần, message có thể chuyển DLQ. Phải có queue/binding DLQ phù hợp và chính sách được nạp. **Đừng nhầm DLQ với gửi thất bại:** producer có thể đã commit JMS rất sớm, còn DLQ xuất hiện sau hàng loạt lỗi xử lý về sau.

### 5.2. Maven

Cấu trúc:

~~~text
producer-boundary-lab/
├── pom.xml
└── src/main/java/lab/BoundaryLab.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>producer-boundary-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

API và package ở đây là **`jakarta.jms`**. Với Classic 5.x thường dùng `org.apache.activemq:activemq-client` và `javax.jms`; phải chọn client theo broker và phiên bản thực tế, không trộn hai namespace trong cùng ví dụ.

### 5.3. Java gửi/nhận có các mốc log riêng

Tạo `src/main/java/lab/BoundaryLab.java`:

~~~java
package lab;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class BoundaryLab {
    private static final String QUEUE = "shipping.commands";

    private BoundaryLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            throw new IllegalArgumentException(
                    "Dùng: send <eventId> <orderId> | receive");
        }

        String user = requiredEnv("BROKER_USER");
        String password = requiredEnv("BROKER_PASSWORD");
        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");

        ConnectionFactory factory = new ActiveMQConnectionFactory(url);
        switch (args[0]) {
            case "send" -> {
                if (args.length != 3) {
                    throw new IllegalArgumentException(
                            "send cần <eventId> <orderId>");
                }
                send(factory, user, password, args[1], args[2]);
            }
            case "receive" -> receive(factory, user, password);
            default -> throw new IllegalArgumentException("Mode không hợp lệ");
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu " + key);
        }
        return value;
    }

    private static void send(ConnectionFactory factory,
                             String user, String password,
                             String eventId, String orderId)
            throws Exception {

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue(QUEUE);
            TextMessage message = context.createTextMessage(orderId);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("schemaVersion", "1");

            context.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .setTimeToLive(0)
                   .send(queue, message);

            System.out.println("SEND_CALLED eventId=" + eventId);
            // Send nằm trong JMS transaction; đây mới là mốc commit.
            context.commit();

            System.out.println("PRODUCER_JMS_COMMITTED eventId=" + eventId);
            System.out.println("JMSMessageID=" + message.getJMSMessageID());
            System.out.println(
                    "CHUA_BIET: consumer da hoan tat nghiep vu hay chua");
        }
    }

    private static void receive(ConnectionFactory factory,
                                String user, String password)
            throws Exception {

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            JMSConsumer consumer =
                    context.createConsumer(context.createQueue(QUEUE));

            Message message = consumer.receive(5000);
            if (message == null) {
                System.out.println("NO_DELIVERY_IN_5_SECONDS");
                return;
            }

            try {
                String eventId = message.getStringProperty("eventId");
                String orderId = message.getBody(String.class);
                if (eventId == null || eventId.isBlank()) {
                    throw new IllegalArgumentException("Thiếu eventId");
                }

                System.out.println("DELIVERED eventId=" + eventId
                        + " orderId=" + orderId);

                if (orderId.startsWith("FAIL:")) {
                    throw new IllegalStateException(
                            "Mô phỏng business handler lỗi");
                }

                // LAB: chỉ mô phỏng xử lý, KHÔNG ghi business database.
                // Production: thay bằng DB transaction + idempotency.
                System.out.println("BUSINESS_SIMULATED eventId=" + eventId);

                context.commit(); // Consumer JMS ACK commit.
                System.out.println("CONSUMER_JMS_COMMITTED eventId=" + eventId);

            } catch (Exception failure) {
                System.err.println("BUSINESS_ERROR " + failure.getMessage());
                context.rollback(); // Để broker redeliver theo policy.
                throw failure;
            }
        }
    }
}
~~~

**Diễn giải trung thực kết quả:**

- `PRODUCER_JMS_COMMITTED`: thao tác transaction gửi phía JMS đã được provider xác nhận. **Không có thông báo tự động ngược về producer khi consumer hoàn thành.**
- `DELIVERED`: consumer nhận message. Đây chỉ là mốc giao nhận.
- `BUSINESS_SIMULATED`: code ví dụ **không có DB**. Không được dùng dòng log này làm bằng chứng tạo vận đơn production.
- `CONSUMER_JMS_COMMITTED`: consumer đã commit transaction JMS tương ứng với ACK. Trong production, phải hoàn thành DB transaction trước mốc này và xử lý trùng.
- `JMSMessageID` do provider sinh không thay thế `eventId` được tạo từ nghiệp vụ và được giữ ổn định qua retry.
- `JMSContext` ở simplified API được auto-start mặc định theo JMS; consumer ở đây không cần gọi `Connection.start()` như dạng classic API.

### 5.4. Chạy và quan sát ranh giới

Trong PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "mat-khau-cua-lab"
mvn -q -DskipTests package
~~~

Từ thư mục Maven:

**Bước A — chỉ chạy producer, không chạy consumer:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.BoundaryLab" "-Dexec.args=send evt-042 order-042"
~~~

Đầu ra kỳ vọng:

~~~text
SEND_CALLED eventId=evt-042
PRODUCER_JMS_COMMITTED eventId=evt-042
JMSMessageID=ID:...
CHUA_BIET: consumer da hoan tat nghiep vu hay chua
~~~

Mở management console và kiểm tra queue `shipping.commands`. Nếu không có consumer khác, broker cho phép route, và message chưa expired, nó đang chờ trong queue. **Producer đã xong nhưng nghiệp vụ chưa được thử xử lý**.

**Bước B — chạy consumer:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.BoundaryLab" "-Dexec.args=receive"
~~~

Đầu ra kỳ vọng:

~~~text
DELIVERED eventId=evt-042 orderId=order-042
BUSINESS_SIMULATED eventId=evt-042
CONSUMER_JMS_COMMITTED eventId=evt-042
~~~

Queue depth có thể về 0 sau khi ACK, nhưng **đó vẫn chưa phải bằng chứng DB shipping được cập nhật** vì bài lab chỉ mô phỏng.

**Bước C — lỗi consumer sau send thành công:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.BoundaryLab" "-Dexec.args=send evt-043 FAIL:simulated"
mvn -q exec:java "-Dexec.mainClass=lab.BoundaryLab" "-Dexec.args=receive"
~~~

Producer vẫn có thể in `PRODUCER_JMS_COMMITTED`. Consumer sẽ log lỗi, gọi `rollback()`, và chương trình thoát với exception. Nếu tiếp tục nhận và policy broker có hiệu lực, message có thể được redeliver, rồi chuyển DLQ sau giới hạn số lần. **Một mốc send success cùng tồn tại với business failure** là kết quả muốn quan sát.

Nếu queue trước đó còn message, việc chạy `receive` không bảo đảm sẽ nhận đúng `evt-043`; cần dùng queue lab sạch hoặc đối chiếu event ID và trạng thái trên console. Không sửa trực tiếp dữ liệu queue đang phục vụ người dùng chỉ để tái hiện demo.

## 6. Giao thức phản hồi trạng thái nghiệp vụ: làm sao producer thực sự biết hoàn tất?

JMS `send()` không có cơ chế mặc định thông báo “consumer đã commit business DB”. Để producer, API hoặc frontend biết được, **phải thiết kế một hợp đồng ứng dụng riêng**.

### 6.1. Phương án 1 — API trả requestId, client hỏi trạng thái

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Shipping API
    participant DB as Status DB
    participant MQ as ActiveMQ
    participant W as Worker

    U->>A: POST /shipping-requests
    A->>DB: Tạo request PENDING
    A-->>U: 202 Accepted + requestId
    A->>MQ: Publish qua outbox relay
    MQ->>W: Giao command
    W->>DB: Thực hiện nghiệp vụ, ghi COMPLETED
    W->>MQ: ACK sau DB commit
    U->>A: GET /shipping-requests/{requestId}
    A->>DB: Đọc trạng thái
    A-->>U: COMPLETED / FAILED / PENDING
~~~

Trạng thái ví dụ:

| Trạng thái | Ý nghĩa | Cần bằng chứng gì? |
|---|---|---|
| `PENDING` | Đã ghi nhận yêu cầu, chưa có kết quả nghiệp vụ | DB transaction tạo request đã commit |
| `QUEUED` (tùy chọn) | Relay có bằng chứng publish theo hợp đồng đã chọn | JMS send/commit và quy trình cập nhật outbox |
| `PROCESSING` (tùy chọn) | Worker đã bắt đầu, nhưng có thể chết/retry | Lease/timestamp có thời hạn; cần reconciliation |
| `COMPLETED` | Kết quả nghiệp vụ được commit, có thể truy vấn | Dữ liệu nghiệp vụ và status nhất quán trong DB transaction |
| `FAILED` | Hệ thống chốt lỗi nghiệp vụ theo policy | Lỗi được phân loại, có nguyên nhân/nhật ký và cơ chế re-drive phù hợp |

`QUEUED` và `PROCESSING` không phải trạng thái bắt buộc. Nếu dùng, phải giải thích ai cập nhật và làm sao xử lý stale state. Nhiều hệ thống chỉ cần `PENDING`, `COMPLETED`, `FAILED` và một `requestId` có thể truy vấn.

**Đây là cách thường hợp lý cho HTTP API:** trả `202 Accepted` có `requestId`/đường dẫn trạng thái, không chờ một consumer có thể xử lý sau vài phút.

### 6.2. Phương án 2 — consumer phát kết quả hoàn thành riêng

Consumer có thể phát event `shipping.completed` hoặc `shipping.failed` sau khi ghi nghiệp vụ. Bên quan tâm subscribe event này, đối chiếu theo `correlationId` hoặc `requestId`.

Tuy nhiên publish kết quả cũng gặp **dual write** với việc cập nhật business DB. Vì thế nên ghi **kết quả nghiệp vụ và outbox event kết quả trong cùng DB transaction**, sau đó relay phát event kết quả. Event phản hồi cũng có thể bị trùng/đến muộn; consumer phía nhận kết quả cần idempotency.

### 6.3. `JMSReplyTo` và `JMSCorrelationID` có tự giải quyết được không?

Không. Hai trường này giúp **định tuyến reply và liên hệ request–reply**:

- `JMSReplyTo`: destination mà consumer có thể gửi reply về.
- `JMSCorrelationID`: ID để client ghép reply với request.

Chúng **không ép consumer gửi reply** và **không bảo đảm reply được gửi sau khi DB commit**. Nếu dùng request–reply cho nghiệp vụ lâu, vẫn cần timeout, correlation, trạng thái bền vững, idempotency và xử lý reply mất/trùng/đến muộn. Với tác vụ kéo dài, polling status hoặc event completion thường rõ nghĩa hơn chờ một JMS reply tức thì.

## 7. Transactional outbox: đóng khoảng trống giữa producer DB và JMS

Ví dụ Order API phải vừa lưu đơn, vừa phát `shipping.create`. Nếu thực hiện:

~~~text
BEGIN DB
INSERT orders
COMMIT DB
JMS SEND
~~~

Process chết sau `COMMIT DB` nhưng trước `JMS SEND` → đơn hàng đã tạo, không có command shipping. Đảo thứ tự cũng không giải quyết được: JMS publish thành công nhưng DB rollback có thể tạo command không còn căn cứ.

**Transactional outbox** đổi hợp đồng: API commit **order + outbox row** trong một DB transaction. Một relay riêng gửi từ outbox sang broker.

~~~mermaid
flowchart LR
    API["Order API"] -->|"Một DB transaction"| DB[("orders + outbox")]
    DB -->|"outbox PENDING"| R["Outbox relay"]
    R -->|"JMS send + commit"| Q[("shipping.commands")]
    Q --> W["Shipping consumer"]
    W -->|"idempotent DB transaction"| S[("shipping + processed_events")]
    S -->|"JMS ACK/commit sau DB"| Q
~~~

### 7.1. Ví dụ schema PostgreSQL tối thiểu

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    shipping_state VARCHAR(32) NOT NULL DEFAULT 'PENDING'
);

CREATE TABLE outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL REFERENCES orders(order_id),
    event_type VARCHAR(64) NOT NULL,
    payload TEXT NOT NULL,
    published_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE processed_events (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

Trong một **DB transaction** của Order API:

~~~sql
BEGIN;

INSERT INTO orders (order_id, shipping_state)
VALUES ('order-042', 'PENDING');

INSERT INTO outbox (event_id, order_id, event_type, payload)
VALUES ('evt-042', 'order-042', 'shipping.create', 'order-042');

COMMIT;
~~~

Relay lấy các bản ghi `published_at IS NULL`, gửi message mang **chính `event_id` đã lưu** qua JMS persistent/transaction, rồi cập nhật `published_at`. Để chạy nhiều relay, cần cơ chế claim/lease hoặc khóa phù hợp (ví dụ `FOR UPDATE SKIP LOCKED` với chiến lược transaction rõ ràng); không để hai relay tự do lấy cùng hàng.

### 7.2. Sau JMS commit, relay chết trước khi đánh dấu published

~~~text
Relay lấy evt-042
   -> JMS send + commit thành công
   -> Process crash
   -> published_at vẫn NULL
   -> Relay restart và gửi lại evt-042
~~~

Outbox giải quyết **mất sự kiện do dual write**, nhưng **không tự bảo đảm không có bản gửi trùng**. Vì vậy người nhận phải dedup theo `eventId`. Việc dùng `JMSMessageID` làm khóa dedup là thiếu ổn định trong trường hợp retry tạo message mới; dùng khóa nghiệp vụ persisted ở outbox.

**Lưu ý:** chỉ đánh dấu `published_at` sau khi có kết quả publish/commit theo hợp đồng producer. Nếu broker trả timeout hoặc trạng thái không chắc chắn, không vội đánh dấu đã gửi chắc chắn; phát lại phải chịu được duplicate.

## 8. Consumer idempotent: hoàn tất tác dụng nghiệp vụ trước ACK

Trong DB shipping, `processed_events(event_id)` và thay đổi trạng thái shipping nên được commit **cùng một transaction**. Một đoạn Java/JDBC mô phỏng cách áp dụng, giả sử đã có `DataSource` được cấu hình:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ShippingHandler {
    private final DataSource dataSource;

    public ShippingHandler(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void handleIdempotently(String eventId, String orderId)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO processed_events (event_id) "
                        + "VALUES (?) ON CONFLICT DO NOTHING")) {
                    statement.setString(1, eventId);
                    inserted = statement.executeUpdate();
                }

                if (inserted == 1) {
                    try (PreparedStatement statement =
                            connection.prepareStatement(
                                    "UPDATE orders "
                                    + "SET shipping_state = 'READY' "
                                    + "WHERE order_id = ?")) {
                        statement.setString(1, orderId);
                        if (statement.executeUpdate() != 1) {
                            throw new SQLException(
                                    "Không tìm thấy order " + orderId);
                        }
                    }
                }

                // Nếu inserted == 0: eventId đã xử lý; không làm lại.
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                connection.rollback();
                throw failure;
            }
        }
    }
}
~~~

Đoạn này minh họa **idempotency trong cùng PostgreSQL database** với `orders`. Nó không tạo vận đơn thực qua API ngoài, và giả định `order_id` duy nhất, cập nhật `shipping_state='READY'` là hành vi nghiệp vụ đúng. Với dữ liệu đa database hoặc side effect ngoài DB, cần workflow/idempotency key/outbox đối ứng và đối soát riêng.

Trong consumer transacted:

~~~java
Message message = consumer.receive(5000);
if (message != null) {
    try {
        String eventId = message.getStringProperty("eventId");
        String orderId = message.getBody(String.class);

        if (eventId == null || eventId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Message thiếu định danh");
        }

        handler.handleIdempotently(eventId, orderId); // DB COMMIT bên trong
        context.commit();                             // JMS ACK COMMIT sau
    } catch (Exception failure) {
        context.rollback();
        throw failure;
    }
}
~~~

Nếu consumer chết **sau** DB commit nhưng **trước** JMS ACK, lần giao lại thấy `eventId` đã tồn tại và không cập nhật shipping lần thứ hai; sau đó vẫn commit JMS để gỡ message khỏi queue. Đây là cách tạo **tác dụng nghiệp vụ một lần** trong phạm vi transaction DB cụ thể dù delivery có thể at-least-once.

**Một cảnh báo về thứ tự:** nếu quy trình cập nhật trạng thái nghiệp vụ dựa trên nhiều event theo cùng `orderId`, idempotency theo eventId chưa đủ chống **event cũ ghi đè trạng thái mới**. Khi đó cần version/sequence và điều kiện cập nhật theo aggregate, hoặc xử lý tuần tự phù hợp.

## 9. Bảng lỗi tại từng thời điểm: producer thấy gì, nghiệp vụ có thể ra sao?

| Thời điểm xảy ra lỗi | Producer/relay có thể thấy | Broker/consumer có thể đang ở đâu | Biện pháp |
|---|---|---|---|
| API DB commit xong, chưa JMS send | API đã trả ghi nhận order | Chưa có command trên broker | Transactional outbox |
| JMS send trong transacted session, chưa commit | `send()` đã trả | Transaction gửi chưa commit, consumer chưa được bảo đảm nhận | Chỉ coi thành công gửi khi JMS commit hoàn thành |
| Broker commit nhưng response mất | Timeout/exception, kết quả không rõ | Message có thể đã nằm trong queue | Giữ eventId, retry có kiểm soát, consumer dedup |
| JMS commit thành công, chưa có consumer | Producer thấy commit OK | Message chờ nếu đã route/lưu và chưa expired | Theo dõi queue age, consumer count, SLA |
| Broker giao message, worker chưa xử lý | Producer không nhận update tự động | Message có thể in-flight | Theo dõi processing status/metric |
| Worker xử lý DB thất bại | Producer send vẫn có thể thành công | Consumer rollback, redelivery hoặc DLQ | Retry/DLQ, phân loại lỗi |
| Worker DB commit, JMS ACK chưa commit | Producer send thành công | Message có thể được giao lại | Idempotent consumer |
| Worker ACK sớm, DB thất bại sau đó | Producer send thành công | Broker có thể đã gỡ message, mất việc | Commit nghiệp vụ trước ACK |
| Worker xử lý xong, reply completion bị mất | Producer không thấy reply | Business DB có thể đã COMPLETED | Truy vấn status canonical, reply event outbox |
| Message hết TTL hoặc không route | Producer tùy contract có thể không thấy lỗi nghiệp vụ | Worker không nhận | Routing/expiry/DLQ, monitor, kiểm thử cấu hình |

Một thiết kế **an toàn quan sát** không dùng mỗi biến boolean `sent=true`. Nên có các mốc được định nghĩa rõ và timestamp/ID cho từng bước.

## 10. Đặt tên trạng thái, log và metric để tránh nhầm lẫn

Không nên đặt tên metric như `shipping_success` ngay khi producer send. Phân tách:

| Metric hoặc log | Sự kiện được đếm | Không đại diện cho |
|---|---|---|
| `outbox_created_total` | DB commit ra một bản ghi outbox | Broker đã nhận |
| `jms_publish_committed_total` | Transaction publish phía producer thành công | Consumer đã xử lý |
| `jms_publish_unknown_total` | Kết quả gửi/commit không chắc chắn do timeout | Broker chắc chắn không nhận |
| `queue_depth` / `oldest_message_age` | Backlog hiện tại từ broker | Tổng kết quả nghiệp vụ |
| `consumer_delivery_total` | Consumer được giao message | Nghiệp vụ commit thành công |
| `business_committed_total` | DB transaction nghiệp vụ commit | Broker đã ACK |
| `jms_consumer_commit_total` | Consumer JMS ACK/transaction commit | Hệ thống ngoài DB đã đồng bộ hết |
| `redelivery_total` | Delivery bị lặp do rollback/lỗi/khôi phục | Toàn bộ message là độc hại |
| `dlq_message_count` | Message chờ xử lý tại DLQ | Producer gửi thất bại |

### 10.1. Correlation ID là xương sống cho điều tra

Mỗi yêu cầu nên có:

- `requestId`: ID public cho người dùng truy vấn trạng thái.
- `eventId`: ID nghiệp vụ bất biến của command/event, được giữ lại khi retry.
- `orderId`: khóa aggregate hoặc tài nguyên.
- `JMSMessageID`: ID do JMS provider gán cho một message gửi cụ thể, hữu ích để đối chiếu broker log.
- `traceId`: ID trace cho log/observability nếu có tracing.

Mẫu log có ý nghĩa:

~~~text
2026-11-17T07:00:00Z requestId=req-42 eventId=evt-042 stage=OUTBOX_COMMITTED
2026-11-17T07:00:01Z requestId=req-42 eventId=evt-042 stage=JMS_PUBLISH_COMMITTED
2026-11-17T07:00:02Z requestId=req-42 eventId=evt-042 stage=CONSUMER_DELIVERED attempt=1
2026-11-17T07:00:03Z requestId=req-42 eventId=evt-042 stage=BUSINESS_COMMITTED
2026-11-17T07:00:03Z requestId=req-42 eventId=evt-042 stage=JMS_ACK_COMMITTED
~~~

Các timestamp chỉ minh họa. Không log toàn bộ payload nếu chứa dữ liệu nhạy cảm. Khi truy vết sự cố, **khoảng thời gian giữa outbox commit, publish commit, business commit và ACK commit** cho biết tắc nghẽn đang ở đâu. Nếu `business_committed` tăng mà `jms_ack` giảm hoặc redelivery tăng, cần điều tra lỗi ACK/reconnect thay vì kết luận business handler chưa chạy.

### 10.2. SLA dành cho producer khác SLA nghiệp vụ

Ví dụ hai SLO độc lập:

- **SLO ghi nhận yêu cầu:** 99,9% request được DB chấp nhận và lưu outbox trong tối đa X ms.
- **SLO hoàn thành shipping:** 99% yêu cầu đạt `COMPLETED` trong tối đa Y phút tính từ lúc nhận yêu cầu.

Một broker có độ trễ send thấp không đủ chứng minh SLO shipping. Nếu Y bị vi phạm, cần xem queue age, consumer capacity, downstream rate limit, retry, DLQ, lỗi payload và trạng thái đối tác.

## 11. Kiểm thử ranh giới bằng fault injection

Các phép thử dưới đây dùng **môi trường lab**, không ngắt broker phục vụ production. Đừng chỉ assert `send() == success`; cần kiểm tra trạng thái theo từng bước.

### Test A — Producer gửi khi consumer chưa chạy

1. Dừng mọi consumer của queue lab.
2. Gửi durable message trong JMS transacted session và commit.
3. Kiểm tra queue có message chờ, `business_state` chưa đổi.
4. Khởi động consumer, đợi DB commit, xác minh trạng thái chuyển `COMPLETED`/giá trị kỳ vọng.
5. Đối chiếu ACK commit và queue depth.

**Kết quả:** producer thành công xảy ra trước business completion.

### Test B — Relay chết sau JMS commit

1. Tạo outbox `evt-201`.
2. Cho relay publish và commit JMS rồi mô phỏng crash **trước khi cập nhật `published_at`**.
3. Khởi động lại relay; nó gửi lại cùng `evt-201`.
4. Xác minh consumer có thể nhận trùng nhưng DB chỉ áp dụng nghiệp vụ **một lần**.

**Kết quả:** outbox cần idempotent consumer; `publish_committed_total` có thể lớn hơn số event nghiệp vụ duy nhất.

### Test C — Consumer chết giữa DB commit và JMS ACK

1. Gửi `evt-202`.
2. Cho consumer ghi `processed_events` và cập nhật DB, commit.
3. Dừng process trước `context.commit()` của JMS.
4. Khởi động lại consumer, quan sát redelivery.
5. Xác minh handler bỏ qua tác dụng phụ lần hai và vẫn ACK message.

**Kết quả:** business commit không đồng nghĩa broker ACK; duplicate delivery là tình huống cần xử lý có chủ đích.

### Test D — Poison message chuyển DLQ

1. Gửi một message có schema lỗi cố định.
2. Consumer validate, rollback.
3. Để broker thử lại theo giới hạn delay/attempts.
4. Kiểm tra DLQ và nguyên nhân lỗi, bảo toàn payload/id để điều tra.
5. Chỉ re-drive sau khi có quy trình sửa dữ liệu và đảm bảo idempotency.

**Kết quả:** producer có thể gửi thành công nhưng business **không bao giờ hoàn tất** nếu không có can thiệp thích hợp.

### Test E — Không có queue/binding phù hợp

1. Trong broker lab riêng, đổi tên address/queue cho không khớp hoặc tắt tự tạo theo chính sách.
2. Thử gửi tới address không có routing phù hợp.
3. Quan sát **exception/response theo client/provider** và trạng thái message thực tế ở broker.
4. Bật lại binding hợp lệ rồi thử lại.

**Kết quả:** hãy kiểm tra broker routing và chính sách no-route, không chỉ đọc log producer. Cách xử lý message không route được có thể khác giữa Artemis/Classic và tùy cấu hình.

## 12. Câu hỏi cần trả lời khi review một producer

1. **`send()` thành công nghĩa là mốc nào?** Non-transacted send hoàn tất, transacted JMS commit, broker durable acknowledgment, hay chỉ enqueue nội bộ phía client? Nêu đúng API và cấu hình.
2. **Message đã tới queue nào?** Address, routing type, destination, selector/expiry và chính sách no-route có khớp không?
3. **Producer có dữ liệu DB phải commit không?** Nếu có, có outbox hoặc phương án phối hợp transaction đủ tin cậy chưa?
4. **Nếu timeout sau send/commit, retry thế nào?** Có eventId ổn định và consumer dedup chưa?
5. **Ai sở hữu trạng thái `COMPLETED`?** Có bản ghi business DB, status endpoint hoặc completion event thật hay chỉ log producer?
6. **Consumer ACK khi nào?** Có nguy cơ ACK trước DB commit, hoặc tạo side effect trùng khi redelivery không?
7. **Nếu consumer offline 30 phút thì sao?** TTL, persistence, queue capacity, backlog SLA, retry policy và DLQ đã được kiểm tra?
8. **Có biết công việc thất bại vĩnh viễn không?** Từ DLQ/cảnh báo/status thay vì lặng lẽ để yêu cầu `PENDING` mãi.
9. **Có phân biệt Classic và Artemis không?** Tên chính sách redelivery, semantics client sync/async, XML configuration, JMS namespace và protocol có đúng dòng broker không?
10. **Đã thử các điểm crash quan trọng chưa?** Trước send, sau broker commit, sau business DB commit và trước ACK.

## 13. Kết luận theo phạm vi producer

**Producer send thành công chỉ xác nhận một bước ở phía gửi theo hợp đồng JMS provider/broker cụ thể.** Nếu send ở trong JMS transaction, cần xét cả **producer commit**; nếu gửi persistent, cần hiểu cấu hình độ bền; nếu gặp timeout, phải chấp nhận trạng thái không chắc chắn.

**Consumer hoàn tất nghiệp vụ là một mốc khác**, cần được xác nhận bằng DB/business state và báo ngược qua cơ chế của ứng dụng, không suy từ `send()`, `JMSMessageID`, queue depth hay ACK đơn lẻ. Thiết kế đáng tin cậy kết hợp **transactional outbox ở producer, eventId ổn định, consumer idempotent, commit nghiệp vụ trước JMS ACK, redelivery/DLQ có kiểm soát và trạng thái có thể truy vấn**.
