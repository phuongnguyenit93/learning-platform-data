# Filter trên queue và selector phía consumer

> **Chương:** Định tuyến Artemis  
> **Phạm vi:** Apache ActiveMQ Artemis, cấu hình `broker.xml`, filter expression của Core broker và JMS/Jakarta Messaging selector. Ví dụ dùng Java 17 với Artemis JMS client.  
> **Mục tiêu:** Hiểu *message có được đưa vào queue không* và *consumer nào được nhận message đã nằm trong queue* là hai quyết định khác nhau.

## 1. Bài toán: cùng một sự kiện nhưng hai lớp lọc

Một ứng dụng thương mại điện tử phát sự kiện `OrderCreated` lên address `lab.orders.events`. Bộ phận vận hành Việt Nam chỉ muốn lưu các đơn có `country = 'VN'`; trong bộ phận này, worker gửi email giá trị cao chỉ muốn xử lý đơn có `channel = 'EMAIL'` và `amount >= 1000`. Song song, một bộ phận kiểm toán muốn lưu mọi sự kiện bất kể quốc gia.

Có hai câu hỏi độc lập:

1. **Lúc message đến broker:** có nên ghi message này vào queue `lab.orders.vn` không? Đây là việc của **queue filter**.
2. **Sau khi message đã vào queue:** worker email nào được nhận message đó? Đây là việc của **consumer selector**.

Trong Artemis, filter của queue chạy ở **bước routing vào queue**; selector của consumer được áp dụng **sau khi message đã được route vào queue**. Vì thế một message bị queue filter loại bỏ **chưa từng nằm trong queue đó**, trong khi một message không khớp selector **vẫn có thể nằm trong queue** cho consumer khác hoặc cho lần xử lý sau. Đây là khác biệt có tác động trực tiếp đến khả năng khôi phục và tiêu thụ backlog.

~~~mermaid
flowchart TD
    P[Java producer: OrderCreated] --> A[Artemis address: lab.orders.events]
    A -->|multicast: mọi event| Q2[(Queue: lab.orders.audit)]
    A --> F{Queue filter: country = VN?}
    F -->|Khớp| Q1[(Queue: lab.orders.vn)]
    F -->|Không khớp| X[Không thêm vào queue VN]
    Q1 --> S{Consumer selector: EMAIL và amount >= 1000?}
    S -->|Khớp| C[Email VIP consumer]
    S -->|Không khớp| W[Vẫn chờ trong queue VN]
    Q2 --> D[Audit consumer]
~~~

Chúng ta chọn một **multicast address với hai queue vật lý** để minh họa việc fan-out đến hai nhóm nghiệp vụ. Các queue có thể có filter riêng; việc consumer dùng selector không làm thay đổi quy tắc đưa message vào queue của nhóm khác.

## 2. Queue filter và consumer selector: ma trận so sánh

| Tiêu chí | Queue filter | Consumer selector |
|---|---|---|
| Khai báo ở đâu? | Trong `<queue>` của `ARTEMIS_INSTANCE/etc/broker.xml`, hoặc thông qua API quản lý/tạo queue hỗ trợ filter | Tại thời điểm ứng dụng tạo consumer, ví dụ `JMSContext.createConsumer(queue, selector)` |
| Thời điểm đánh giá | **Trước khi** message được route vào queue tương ứng | **Sau khi** message đã được route vào queue, trong quá trình lựa chọn để phát cho consumer |
| Đơn vị ảnh hưởng | **Một queue** và mọi consumer dùng queue đó | **Một consumer cụ thể** và tiêu chí nhận của nó |
| Message không khớp | **Không được đưa vào queue đó** | **Không được giao cho consumer đó**; vẫn có thể nằm trong queue |
| Có thể sửa cho message đã đi qua không? | Đổi filter **không tự truy hồi** những message trước đây đã bị loại | Tạo consumer với selector khác có thể nhận message tồn trong queue nếu phù hợp |
| Khi dùng hợp lý | Phân luồng lưu trữ cố định theo tenant/quốc gia/loại event | Mỗi worker nhận tập message phù hợp trong cùng một queue |
| Chi phí vận hành | Giảm số message được lưu/đánh giá trong queue không liên quan | Linh hoạt theo consumer nhưng có thể cần tìm/đọc qua backlog không khớp |
| Phạm vi portability | Artemis Core filter expression, có các identifier riêng của Artemis | JMS/Jakarta Messaging selector chuẩn, cộng các mở rộng provider nếu dùng |

**Một câu dễ nhớ:** Queue filter quyết định **message thuộc queue nào**; consumer selector quyết định **consumer được phép nhận những message nào từ queue đã chọn**. Cả hai đều là công cụ *lọc dữ liệu*, không thay cho phân quyền broker.

### Trường hợp kết hợp hai bộ lọc

Gọi:

- `Q(m)` là biểu thức queue filter trên message `m`;
- `S(m)` là biểu thức selector của một consumer;
- `R(m)` là điều kiện message được route đúng address và routing type.

Consumer chỉ có thể nhận `m` nếu `R(m) AND Q(m) AND S(m)` đều đúng, và message còn đủ điều kiện giao (chưa ACK, chưa hết hạn, có quyền nhận, không bị lock/in-flight ở consumer khác…).

Điều này **không có nghĩa** broker duy trì một hàng đợi con vật lý cho mỗi selector. Nhiều consumer với selector khác nhau có thể cùng đọc một queue và mỗi consumer chỉ chọn phần phù hợp của backlog hiện có.

## 3. Cấu hình queue filter đúng cấu trúc broker.xml

Trong instance Artemis được tạo bằng `artemis create`, mở tệp:

~~~text
<ARTEMIS_INSTANCE>/etc/broker.xml
~~~

Tìm section `<addresses>` **đã có trong thẻ `<core>`**. Nếu address `lab.orders.events` chưa tồn tại, thêm **một** phần tử `<address>` vào section đó:

~~~xml
<address name="lab.orders.events">
    <multicast>
        <queue name="lab.orders.vn">
            <filter string="country = 'VN'"/>
            <durable>true</durable>
        </queue>
        <queue name="lab.orders.audit">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
~~~

**Ý nghĩa từng phần:**

- `<address name="lab.orders.events">`: địa chỉ message sẽ được producer gửi đến.
- `<multicast>`: một message phù hợp có thể được đưa vào **mỗi queue** thuộc address, khác với cạnh tranh giữa nhiều anycast queue.
- `lab.orders.vn`: queue chỉ chấp nhận những message mà **property `country` là chuỗi `VN`**.
- `lab.orders.audit`: queue không có filter nên nhận mọi message được route đến address với kiểu multicast.
- `<durable>true</durable>`: queue được cấu hình bền vững; message bền vững cần gửi với `DeliveryMode.PERSISTENT` và broker phải bật persistence phù hợp để tồn tại khi restart/crash.

**Không thay thế toàn bộ `broker.xml` bằng đoạn trên.** Đây là mảnh cấu hình nằm trong `<addresses>`; giữ nguyên root XML, namespace, acceptors, security-settings và các phần khác do instance tạo ra. Không tạo hai address trùng tên hoặc hai queue trùng tên (Artemis yêu cầu tên queue duy nhất trên broker).

Một số trường hợp Artemis tự tạo address/queue khi client kết nối. Trong lab này khai báo **tường minh** để chắc chắn queue `lab.orders.vn` thực sự có filter và queue `lab.orders.audit` không có filter. Trước khi thử, xem console/management để xác nhận broker đang dùng đúng định nghĩa queue.

### Tại sao dùng multicast, không khai báo hai anycast queue?

Mục tiêu là **audit nhận tất cả**, còn nhánh VN nhận một tập con. Multicast đưa mỗi message vào tất cả queue phù hợp; sau đó queue filter kiểm soát từng bản sao. Với anycast, broker chỉ chọn một queue trong các queue anycast phù hợp, nên không nên dùng nó để giả lập fan-out độc lập hai nhóm.

### XML escaping cho biểu thức filter

Filter nằm trong **giá trị attribute XML**, vì thế các ký tự đặc biệt phải escape. Ví dụ muốn queue chỉ nhận đơn VN và số tiền ít nhất 1.000:

~~~xml
<queue name="lab.orders.vn.high-value">
    <filter string="country = 'VN' AND amount &gt;= 1000"/>
</queue>
~~~

Ở đây `&gt;` được XML parser giải mã thành `>`. Tương tự, `<` cần viết `&lt;`, còn `&` viết `&amp;`. Dùng `AND` của filter expression; đừng đưa toán tử Java `&&` nguyên văn vào attribute XML.

**Quan trọng:** Đoạn trên minh họa một *queue khác* có filter kết hợp. Bài lab chính tiếp tục dùng queue `lab.orders.vn` chỉ lọc `country = 'VN'` để quan sát riêng hiệu ứng của selector phía consumer.

### Cập nhật filter của queue đang có

Trên các bản Artemis hiện đại, cấu hình queue filter trong `broker.xml` nằm trong nhóm có thể được reload theo cơ chế configuration reload. Tuy nhiên, không nên mặc định một lần lưu file sẽ thay đổi lập tức mọi broker, vì thời gian reload, thay đổi schema và chính sách vận hành có thể khác. Trong lab, dừng broker, chỉnh file rồi khởi động lại để xác thực cấu hình.

**Đổi queue filter không phải thao tác xử lý dữ liệu quá khứ:** message từng bị từ chối không được tự động gửi lại; message đã được đưa vào queue trước đó cũng không được coi là đã tái tạo hoàn toàn theo quy tắc mới. Khi đổi điều kiện lọc, cần lập kế hoạch dữ liệu tồn và phát bù từ nguồn sự kiện nếu nghiệp vụ yêu cầu.

## 4. Dữ liệu mẫu để kiểm chứng chính xác

Producer sẽ gửi sáu sự kiện, mỗi sự kiện có một định danh `eventId`, body bất kỳ và **ba message properties**: `country` (String), `channel` (String), `amount` (int).

| Event | `country` | `channel` | `amount` | Vào `lab.orders.vn`? | Khớp selector EMAIL và amount ≥ 1000? |
|---|---|---|---:|---|---|
| E1 | VN | EMAIL | 1500 | Có | Có |
| E2 | VN | SMS | 1500 | Có | Không |
| E3 | US | EMAIL | 2000 | Không | Có, **nhưng không vào queue VN** |
| E4 | VN | EMAIL | 700 | Có | Không |
| E5 | VN | EMAIL | 1800 | Có | Có |
| E6 | TH | EMAIL | 2100 | Không | Có, **nhưng không vào queue VN** |

Trước khi consumer chạy (và với giả định queue trống từ đầu):

- `lab.orders.vn` chứa chính xác **E1, E2, E4, E5**: 4 message.
- `lab.orders.audit` chứa **E1, E2, E3, E4, E5, E6**: 6 message.
- Consumer nối vào queue VN với selector `channel = 'EMAIL' AND amount >= 1000` chỉ có thể nhận **E1 và E5**.
- Sau khi E1/E5 được ACK/commit, queue VN vẫn còn **E2 và E4**. Cả hai không tự biến mất do không khớp selector.
- Queue audit vẫn có 6 message cho đến khi consumer audit nhận và ACK.

Đây là kết quả kiểm tra quan trọng nhất: **E3 và E6 vượt qua consumer selector về mặt giá trị nhưng không thể “xuyên qua” queue filter để xuất hiện ở queue VN**.

## 5. Ngôn ngữ biểu thức: SQL-92 subset, JMS selector và Core filter

Artemis dùng ngôn ngữ filter dựa trên một **tập con của SQL-92**. Cú pháp hai loại biểu thức tương tự nhau, nhưng **các identifier hệ thống có thể khác**: JMS selector đánh giá một JMS message; queue filter của Artemis đánh giá một Core message.

### Ví dụ phổ biến

| Biểu thức | Ý nghĩa |
|---|---|
| `country = 'VN'` | Property `country` có giá trị chuỗi `VN` |
| `channel IN ('EMAIL', 'SMS')` | Chỉ nhận kênh EMAIL hoặc SMS |
| `amount >= 1000 AND country = 'VN'` | Kết hợp điều kiện số và chuỗi |
| `amount BETWEEN 1000 AND 5000` | Khoảng số có hai đầu, theo semantics selector |
| `eventType LIKE 'Order%'` | Tên sự kiện bắt đầu bằng `Order` |
| `region IS NULL` | Property vắng mặt/giá trị null theo ngữ nghĩa selector |
| `active = TRUE` | Property boolean là true |
| `NOT (country = 'VN')` | Loại khỏi tập khớp các message có `country = 'VN'`; cần chú ý trường hợp null |

**String literal** dùng dấu nháy đơn, ví dụ `'EMAIL'`. Tên property không đặt trong nháy đơn. Biểu thức phải viết cho **message properties/headers**, không phải một thuộc tính tùy ý nằm sâu trong JSON body.

### Thiếu property và logic ba giá trị

Nếu producer gửi event không có property `amount`, biểu thức `amount >= 1000` không trở thành `TRUE` hay tự mặc định 0; nó thường có trạng thái **UNKNOWN**. Chỉ kết quả `TRUE` mới được coi là khớp selector/filter. Điều kiện `country <> 'VN'` cũng không đương nhiên khớp một message không có `country`.

Nếu muốn bắt message thiếu metadata, viết chính sách rõ ràng: reject/validate ở producer, hoặc lọc bằng `IS NULL` nếu tình huống cho phép. Đừng dùng `NOT (country = 'VN')` như cách mặc định nhận mọi message thiếu `country`.

### Sai kiểu dữ liệu là nguyên nhân thường gặp

Hai đoạn sau có hành vi khác nhau:

~~~java
message.setIntProperty("amount", 1500);        // Kiểu số
message.setStringProperty("amount", "1500");  // Kiểu String
~~~

Với selector chuẩn `amount >= 1000`, property số thỏa điều kiện; **chuỗi "1500" không tự động được chuyển thành số**. Artemis có mở rộng filter expression `convert_string_expressions:` cho một số tình huống protocol gửi property dưới dạng chuỗi, nhưng đây là **mở rộng không portable**, không nên dùng làm hợp đồng tích hợp JMS chuẩn nếu có thể sửa producer.

Ví dụ mở rộng riêng Artemis (không dùng trong code lab):

~~~text
convert_string_expressions:amount >= 1000
~~~

Hướng bền vững là chuẩn hóa loại property ở producer và đặt kiểm thử schema. Đừng suy đoán kiểu từ cách hiển thị JSON hoặc log.

### JMS header và Artemis Core identifier không thay thế tùy tiện

Khi viết **JMS selector**, các tên header theo API JMS như `JMSPriority`, `JMSCorrelationID` và `JMSType` có ý nghĩa theo chuẩn JMS. Khi viết **Artemis Core filter**, những thuộc tính broker có tên riêng, ví dụ:

| Identifier trong Core filter | Ý nghĩa |
|---|---|
| `AMQPriority` | Ưu tiên của message, số nguyên từ 0 đến 9 |
| `AMQDurable` | `'DURABLE'` hoặc `'NON_DURABLE'` |
| `AMQAddress` | Address message được gửi đến |
| `AMQTimestamp` | Timestamp của message |
| `AMQSize` | Kích thước message, đơn vị byte |
| `AMQUserID` | ID của message được đặt ở phía Core |

Ví dụ filter queue dựa trên Core priority:

~~~xml
<queue name="lab.priority">
    <filter string="AMQPriority &gt;= 7"/>
</queue>
~~~

Trong khi ví dụ JMS selector theo priority là:

~~~java
JMSConsumer priorityConsumer =
    context.createConsumer(queue, "JMSPriority >= 7");
~~~

Dù hai biểu thức có thể nhằm lọc message ưu tiên cao, cách map header phụ thuộc API/giao thức. Trong bài lab chính nên ưu tiên **property do ứng dụng đặt**, chẳng hạn `country` và `amount`, để tránh ràng buộc chặt với representation của Core/JMS.

### Có lọc được JSON body không?

JMS selector tiêu chuẩn **không truy vấn nội dung JSON body**. Nếu body là:

~~~json
{"orderId":"E1","country":"VN","amount":1500}
~~~

nhưng producer không gọi `setStringProperty("country", "VN")` và `setIntProperty("amount", 1500)`, selector `country = 'VN' AND amount >= 1000` sẽ **không khớp**. Artemis có extension XPath cho **XML body** trong một số protocol, nhưng không nên dùng như cơ chế chung để lọc JSON và cần cân nhắc chi phí parse/lượng message lớn. Khi cần routing, thiết kế metadata quan trọng thành message properties ngay tại nguồn phát.

## 6. Thực hành Java/JMS trên Artemis

### 6.1. Điều kiện và dependency

Lab giả sử:

- Broker instance Artemis đã chạy ở `tcp://127.0.0.1:61616`, acceptor hỗ trợ **CORE**.
- Trong `broker.xml` đã khai báo multicast address và **hai queue** như phần 3.
- User có quyền gửi vào address và tiêu thụ từ hai queue; không hardcode mật khẩu.
- Java 17 trở lên; dùng **Jakarta Messaging** namespace `jakarta.jms.*` và client `artemis-jakarta-client` tương thích với broker.

Ví dụ trong `pom.xml` cho một project thực hành độc lập (chọn phiên bản thích hợp với broker đang sử dụng):

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

`2.57.0` là phiên bản ví dụ theo tài liệu Artemis được đối chiếu, không phải chỉ thị phải nâng broker production lên phiên bản đó. Nếu dùng `javax.jms.*` thì phải chọn đúng dòng client tương thích; không trộn namespace `javax.jms` với `jakarta.jms` trong cùng đoạn code. Hãy dùng các biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` từ cấu hình chạy local.

### 6.2. Mã nguồn: một producer, ba loại consumer

Lớp dưới đây có bốn chế độ chạy độc lập:

- `publish`: gửi sáu message qua JMS topic `lab.orders.events`.
- `vip`: nhận từ **queue VN** với **selector phía consumer**.
- `vn-all`: nhận các message còn lại từ **queue VN** không selector.
- `audit`: nhận toàn bộ message từ **queue audit** không selector.

Mỗi chế độ tạo `JMSContext` riêng. Dùng `SESSION_TRANSACTED` để chỉ ACK khi logic nhận đã thành công. Mọi lần test với queue còn dữ liệu cũ sẽ có số đếm thay đổi; cần kiểm soát trạng thái ban đầu trước khi so sánh bảng kỳ vọng.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class FilterSelectorLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String ADDRESS = "lab.orders.events";
    private static final String VN_QUEUE = "lab.orders.vn";
    private static final String AUDIT_QUEUE = "lab.orders.audit";
    private static final String VIP_SELECTOR =
        "channel = 'EMAIL' AND amount >= 1000";

    private record Event(
        String eventId, String country, String channel, int amount) {}

    private static final Event[] DATA = {
        new Event("E1", "VN", "EMAIL", 1500),
        new Event("E2", "VN", "SMS",   1500),
        new Event("E3", "US", "EMAIL", 2000),
        new Event("E4", "VN", "EMAIL",  700),
        new Event("E5", "VN", "EMAIL", 1800),
        new Event("E6", "TH", "EMAIL", 2100)
    };

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                "Cách dùng: FilterSelectorLab publish|vip|vn-all|audit");
            return;
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        switch (args[0]) {
            case "publish" -> publish(factory, user, password);
            case "vip" -> consume(
                factory, user, password, VN_QUEUE, VIP_SELECTOR);
            case "vn-all" -> consume(
                factory, user, password, VN_QUEUE, null);
            case "audit" -> consume(
                factory, user, password, AUDIT_QUEUE, null);
            default -> throw new IllegalArgumentException(
                "Chế độ không hợp lệ: " + args[0]);
        }
    }

    private static void publish(
        ActiveMQConnectionFactory factory,
        String user, String password) {

        try (JMSContext context = factory.createContext(
            user, password, JMSContext.SESSION_TRANSACTED)) {

            Topic topic = context.createTopic(ADDRESS);

            try {
                for (Event event : DATA) {
                    TextMessage message = context.createTextMessage(
                        "{\"eventId\":\"" + event.eventId() + "\"}");

                    // Metadata để queue filter và selector đánh giá:
                    message.setStringProperty(
                        "eventId", event.eventId());
                    message.setStringProperty(
                        "country", event.country());
                    message.setStringProperty(
                        "channel", event.channel());
                    message.setIntProperty(
                        "amount", event.amount());

                    context.createProducer()
                        .setDeliveryMode(DeliveryMode.PERSISTENT)
                        .send(topic, message);
                }

                context.commit();
                System.out.println("Đã publish đủ 6 message.");
            } catch (Exception ex) {
                context.rollback();
                throw new IllegalStateException("Gửi thất bại", ex);
            }
        }
    }

    private static void consume(
        ActiveMQConnectionFactory factory,
        String user,
        String password,
        String queueName,
        String selector) throws Exception {

        try (JMSContext context = factory.createContext(
            user, password, JMSContext.SESSION_TRANSACTED)) {

            // FQQN: chỉ thẳng vào queue vật lý thuộc multicast address.
            Queue queue = context.createQueue(
                ADDRESS + "::" + queueName);

            JMSConsumer consumer = selector == null
                ? context.createConsumer(queue)
                : context.createConsumer(queue, selector);

            int count = 0;
            try {
                // Timeout chỉ kết thúc lượt thử; không chứng minh queue rỗng.
                while (true) {
                    Message message = consumer.receive(1200);
                    if (message == null) {
                        break;
                    }

                    try {
                        if (!(message instanceof TextMessage text)) {
                            throw new IllegalArgumentException(
                                "Chỉ hỗ trợ TextMessage trong bài lab");
                        }

                        System.out.printf(
                            "queue=%s event=%s country=%s channel=%s "
                            + "amount=%d body=%s%n",
                            queueName,
                            text.getStringProperty("eventId"),
                            text.getStringProperty("country"),
                            text.getStringProperty("channel"),
                            text.getIntProperty("amount"),
                            text.getText()
                        );

                        // Trong hệ thống thật: ghi hiệu ứng nghiệp vụ
                        // và xử lý idempotent theo eventId trước ACK.
                        context.commit();
                        count++;
                    } catch (Exception ex) {
                        context.rollback();
                        throw ex; // Tránh vòng lặp retry nóng trong lab.
                    }
                }
                System.out.println("Đã xử lý " + count + " message.");
            } finally {
                consumer.close();
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + name);
        }
        return value;
    }
}
~~~

**Vì sao dùng FQQN?** Queue `lab.orders.vn` và `lab.orders.audit` là hai queue vật lý trên cùng multicast address. Artemis cho phép JMS consumer truy cập trực tiếp queue bằng cú pháp `address::queue`, ví dụ `lab.orders.events::lab.orders.vn`. Lúc publish, chúng ta vẫn gửi **JMS Topic** `lab.orders.events` để sử dụng routing **multicast**. Nếu gửi sai destination/routing type, cả bảng kết quả có thể sai dù selector đúng.

**Vì sao không dùng `createDurableConsumer(topic, ...)` trong ví dụ?** API đó tạo/đăng ký một JMS topic subscription, thường dẫn đến queue subscription khác do provider quản lý. Bài này chủ đích quan sát **hai queue đã khai báo trong broker.xml**, nên đọc trực tiếp bằng FQQN là cách rõ ràng nhất. Không tạo thêm một subscription queue khác rồi nhầm nó với `lab.orders.vn`.

### 6.3. Trình tự chạy để tái hiện kết quả

Dùng IDE hoặc cấu hình chạy Java của dự án để chạy `FilterSelectorLab` với từng argument. Đừng chạy song song ba chế độ consumer trong lần quan sát đầu.

1. Khởi động Artemis instance sau khi thêm address/queue. Xác nhận trong console có `lab.orders.vn` với filter `country = 'VN'` và `lab.orders.audit` không filter; cả hai bắt đầu với **0 message**.
2. Chạy `publish` **một lần**. Kỳ vọng hai queue có lần lượt **4** và **6** message trước khi consumer nào kết nối.
3. Chạy `vip`. Kỳ vọng in ra **E1, E5**, tổng **2 message**. Sau đó queue VN còn **E2, E4**.
4. Chạy `audit`. Kỳ vọng **E1 đến E6**, tổng **6 message**; queue audit về 0 sau khi commit đủ.
5. Chạy `vn-all`. Kỳ vọng **E2, E4**, tổng **2 message**; queue VN về 0 sau khi commit đủ.

| Thời điểm | Count queue VN | Count queue audit | Giải thích |
|---|---:|---:|---|
| Trước publish | 0 | 0 | Hai queue rỗng |
| Sau `publish` | 4 | 6 | Queue filter đã loại E3, E6 khỏi nhánh VN |
| Sau `vip` | 2 | 6 | Selector chỉ cho consumer nhận E1, E5 |
| Sau `audit` | 2 | 0 | Audit ACK đủ cả sáu |
| Sau `vn-all` | 0 | 0 | Consumer không selector nhận nốt E2, E4 |

Các số trên giả định không có message cũ, không có consumer khác, không có TTL/expiry, không có lỗi gửi hoặc rollback, và tất cả lệnh `commit()` hoàn tất. Console có thể hiển thị số *delivering* tách khỏi số *ready* khi consumer đang chạy; đọc số sau khi process đã kết thúc để giảm nhiễu.

### 6.4. Thí nghiệm đối chứng: bỏ queue filter

Khi queue đã rỗng, sửa `lab.orders.vn` trong `broker.xml` để **không còn thẻ `<filter>`**, rồi đảm bảo broker đã áp dụng cấu hình (với lab đơn giản có thể restart). Publish lô E1–E6 mới.

- Queue VN lúc này nhận đủ **6 message**.
- Consumer `vip` có selector vẫn chỉ nhận **E1, E3, E5, E6** vì đều `channel='EMAIL' AND amount>=1000`.
- Sau khi consumer VIP ACK 4 message, queue VN còn **E2 và E4**.

Đối chứng này cho thấy consumer selector **không thay thế** queue filter: nó có thể chọn E3/E6 khi các message được giữ trong queue, nhưng không thể lấy E3/E6 từ queue đã bị queue filter từ chối ngay ở bước routing.

### 6.5. Thí nghiệm ngược: queue filter chặt hơn selector

Dùng một queue riêng (hoặc reset đúng queue lab khi không còn backlog), đặt:

~~~xml
<filter string="country = 'VN' AND amount &gt;= 1000"/>
~~~

Sau khi publish, queue chỉ có **E1, E2, E5**. Consumer VIP nhận E1 và E5; E2 vẫn chờ vì `channel='SMS'`. Một consumer chọn `amount < 1000` sẽ không nhận được E4 từ queue này, dù E4 có thật trong sự kiện đã publish: queue filter đã loại từ trước.

Lưu ý không sửa quy tắc trên broker đang phục vụ ứng dụng thật chỉ để thực hành, và không coi việc thay filter là một thao tác lọc lại backlog lịch sử.

## 7. Consumer selector khi nhiều worker dùng chung queue

Cho hai worker cùng lấy từ `lab.orders.vn`:

~~~java
JMSConsumer email = context.createConsumer(
    queue, "channel = 'EMAIL'");

JMSConsumer sms = context.createConsumer(
    queue, "channel = 'SMS'");
~~~

Cả hai consumer có thể cùng gắn vào **một queue**, nhưng mỗi message trong queue chỉ đủ điều kiện giao cho consumer có selector phù hợp. Nếu chỉ chạy consumer EMAIL, các message SMS **chưa ACK và còn lại**, không bị xóa do thiếu consumer.

### Hai hệ quả khó nhìn ra

1. **Selector có thể gây backlog không ai nhận.** Nếu producer bắt đầu gửi `channel='PUSH'` mà không có consumer PUSH (và không có consumer tổng quát), các message đó tiếp tục tích lũy trong queue. Việc thêm consumer EMAIL không giúp xử lý chúng.
2. **Selector quá khắt khe có thể ảnh hưởng đến paging.** Tài liệu Artemis cảnh báo trường hợp hàng triệu message không khớp nằm trước message cần tìm trong queue đang paging: consumer với selector rất hẹp có thể không đọc được message phía sâu cho đến khi backlog phía trước được xử lý. Cần theo dõi đặc tính paging và cân nhắc **tách queue bằng filter lúc routing** nếu workload lớn và các tập message tương đối độc lập.

**Không nhầm selector với partition hay một cam kết thứ tự toàn cục.** Khi nhiều consumer cạnh tranh, prefetch/consumer window, transaction, retry và thời gian xử lý khác nhau có thể làm thứ tự hoàn tất không giống thứ tự publish. Nếu nghiệp vụ phải tuần tự theo `orderId`, thiết kế cơ chế thứ tự riêng.

### Shared subscription và selector của subscription

Với JMS Topic, selector cũng có thể gắn khi tạo subscription (bao gồm shared/durable nếu provider hỗ trợ). Nhưng mỗi subscription của topic thường là **một queue riêng** trong Artemis; selector ở thời điểm tạo subscription và filter ở queue preconfigured có thể có kết quả giống nhau ở một số trường hợp mà **khác nhau về vòng đời quản trị, danh tính subscription và backlog**. Trong bài này, để không lẫn hai cơ chế, ta chỉ so sánh **queue filter tĩnh** và **selector trên JMS Queue consumer qua FQQN**.

## 8. Trường hợp biên và lỗi thực tế

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
|---|---|---|
| Sau publish, queue VN có 0 message | Producer không gửi vào `lab.orders.events`, routing type sai, property `country` không khớp, queue chưa được nạp | Kiểm tra address/routing, filter hiện hành, message properties của producer |
| E3 lọt vào queue VN | Filter chưa được nạp, khác tên queue, đang đọc nhầm subscription queue | Xem thông số filter của queue vật lý trong console/management |
| Consumer VIP không nhận E1 | `amount` là String, thiếu `channel`, selector sai tên/case, thiếu quyền consume | Log property type; thử consumer không selector trên queue lab |
| Queue VN có message nhưng `receive(1200)` trả null | Những message còn lại không khớp selector hoặc đang được consumer khác giữ | So sánh selector với metadata; kiểm tra ready/delivering count |
| Thêm consumer mới thì thấy message cũ | Message đã vào queue trước đó nhưng không khớp selector cũ | Đây là hành vi kỳ vọng; selector không xóa message không khớp |
| Đổi queue filter xong không thấy message trước đây | Message cũ từng không được route vào queue, không có bản sao ở đó | Cần nguồn phát/replay từ nơi lưu khác nếu muốn backfill |
| Có message không ai nhận, queue tăng mãi | Tập selector hiện tại không bao phủ tập dữ liệu producer gửi | Mở consumer phù hợp, chỉnh hợp đồng metadata hoặc tách queue |
| Selector hoạt động chậm lúc backlog lớn | Nhiều message không khớp, paging và đọc qua backlog | Giảm độ chọn lọc quá mức, phân queue ở routing, quan sát paging |
| Java báo thiếu class JMS | Mix `javax.jms.*` và `jakarta.jms.*`, version client sai | Kiểm tra dependency thực tế, namespace và broker/client compatibility |
| Error authorization | Role chưa có quyền send/consume, broker từ chối tạo queue | Xem `security-settings` của address và role; filter không cấp quyền |
| Có hai lần xử lý cùng `eventId` | Consumer crash trước ACK, rollback/redelivery, publish trùng | Idempotency key theo nghiệp vụ; transaction DB và ACK đúng thứ tự |

### Vấn đề ACK, transaction và redelivery

Queue filter chỉ chạy khi message được route vào queue; khi consumer rollback, broker giao lại message **đã nằm trong queue**, không “gửi lại về address rồi áp queue filter từ đầu” như một producer mới. Consumer selector khi đó tiếp tục giới hạn consumer nào đủ điều kiện nhận redelivery.

Nếu worker cập nhật DB rồi chết trước khi `JMSContext.commit()`, hiệu ứng DB có thể đã xảy ra và message vẫn được giao lại. Giải pháp thường là kiểm tra `eventId` trong transaction DB với unique constraint, áp dụng side effect đúng một lần, sau đó commit JMS. Không coi queue filter hay selector là cơ chế bảo đảm exactly-once.

### Filter và selector không thay cho bảo mật

Bộ lọc định tuyến dữ liệu không bảo đảm một consumer khác không thể tạo selector rộng hơn hoặc truy cập một queue khác nếu được cấp quyền. Phải dùng **authentication, authorization** và cấu hình `security-settings` của Artemis để giới hạn send/consume/create queue theo role; chỉ đưa metadata không nhạy cảm vào message property, vì tên/value property có thể hiện trên công cụ quản trị.

## 9. Chọn queue filter hay consumer selector trong thiết kế thực tế

**Dùng queue filter khi** ranh giới nghiệp vụ tương đối ổn định, nhóm muốn một queue chỉ lưu loại message của mình, số message bị loại lớn và không cần replay từ queue đó. Ví dụ queue dành riêng cho sự kiện VN, queue dành riêng cho `OrderCancelled`, hoặc mỗi phòng ban có tập dữ liệu khác nhau trên multicast address.

**Dùng consumer selector khi** một queue phải giữ đầy đủ backlog nhưng từng worker chọn phần việc theo khả năng, selector thay đổi theo worker/deployment và message chưa khớp cần có cơ hội được worker khác nhận sau. Ví dụ worker SMS và EMAIL cùng queue có chiến lược drain riêng; cần có người chịu trách nhiệm đối với message không thuộc bất kỳ selector nào.

**Kết hợp hai lớp khi** queue filter đặt ranh giới lưu trữ/định tuyến lớn, còn consumer selector đặt tiêu chí chọn việc trong một nhóm. Đảm bảo các selector trong cùng queue **phủ đủ** các message có thể đến hoặc có cơ chế xử lý phần dư, nếu không queue sẽ tích backlog.

### Câu hỏi tự đánh giá

1. Vì sao E3 thỏa `channel='EMAIL' AND amount>=1000` nhưng consumer VIP của queue VN vẫn không nhận được?
2. Nếu `amount` của E1 được gửi bằng `setStringProperty("amount", "1500")`, kết quả selector có còn như bảng dự kiến không? Vì sao?
3. Queue VN đã nhận E1/E2/E4/E5. Nếu consumer VIP xử lý hết rồi dừng, message nào còn trong queue, và làm sao nhận tiếp?
4. Một message không có property `country` có khớp `country <> 'VN'` không? Khi cần nhận message thiếu metadata, phải làm thế nào?
5. Khi message không khớp queue filter, bạn có thể thay selector consumer để đọc lại từ queue ấy không? Nếu không, cần nguồn dữ liệu nào?
6. Bạn sẽ chọn queue filter hay consumer selector cho 10 triệu message/ngày với 99% message không liên quan đến một worker và broker thường vào chế độ paging?
7. Đoạn XML `<filter string="amount < 1000"/>` có vấn đề gì? Viết lại cú pháp attribute XML đúng.
8. Nếu audit queue vẫn giữ E1 sau khi queue VN đã ACK E1, điều này có phải xử lý trùng do lỗi không?

**Đáp án gợi ý:** (1) E3 bị loại ở bước đưa vào queue VN; (2) không theo selector chuẩn vì không ép String thành số; (3) còn E2/E4, dùng consumer không selector hoặc selector phù hợp; (4) điều kiện thường UNKNOWN, xác thực metadata hoặc dùng `IS NULL`; (5) không, cần replay/phát lại từ nguồn có bản sao; (6) cân nhắc route vào queue chuyên biệt bằng queue filter; (7) escape `<` thành `&lt;`; (8) không, đó là hai bản sao logic ở hai queue multicast độc lập.

## 10. Tài liệu đối chiếu

- [Apache ActiveMQ Artemis — Address Model, mục Queue Filter và Consumer Filters](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): khẳng định thứ tự áp dụng filter và ví dụ XML/JMS chính thức.
- [Apache ActiveMQ Artemis — Filter Expressions](https://artemis.apache.org/components/artemis/documentation/latest/filter-expressions.html): cú pháp SQL-92 subset, predefined identifiers `AMQ*`, type conversion và extension XPath.
- [Apache ActiveMQ Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging.html): các giới hạn đặc biệt khi consumer dùng selector rất chọn lọc với backlog đang paging.
- [Apache ActiveMQ Artemis — Configuration Reload](https://artemis.apache.org/components/artemis/documentation/latest/config-reload.html): cơ chế cập nhật filter cấu hình queue trong `broker.xml`.

**Điểm chốt:** Trong ActiveMQ Artemis, **queue filter lọc trước khi lưu vào queue**, còn **consumer selector lọc sau khi đã route vào queue**. Hai cơ chế đều có ích nhưng khác nhau ở **vị trí áp dụng, tác động đến dữ liệu còn lại và khả năng backfill**. Muốn hiểu đúng một kết quả lọc, hãy theo dấu cùng một `eventId` qua ba bước: *producer gắn property đúng kiểu → broker route vào queue theo filter → consumer nhận theo selector và ACK*.
