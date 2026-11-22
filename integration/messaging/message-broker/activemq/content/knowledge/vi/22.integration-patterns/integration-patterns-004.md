# Message selector, bộ lọc và định tuyến theo thuộc tính

> **Chương:** Mẫu tích hợp  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic/Artemis, queue/topic, routing và Java/JMS.  
> **Trọng tâm:** Triển khai *Content-Based Router*, *Recipient List* và *Selective Consumer* bằng **JMS message properties**, **Artemis queue filter**, **consumer selector** và **filtered divert**. Ví dụ chính dùng Artemis 2.x, Java 17 và Jakarta Messaging.

## 1. Bài toán: một sự kiện, nhiều người nhận có điều kiện

Dịch vụ thanh toán công bố sự kiện `PaymentCaptured`. Ba nhóm xử lý có hợp đồng khác nhau:

- **Billing Việt Nam**: chỉ lưu thanh toán thành công khi `countryCode = 'VN'`.
- **Risk**: chỉ lưu thanh toán thành công có `amountMinor >= 10000000`, bất kể quốc gia.
- **Audit**: lưu tất cả sự kiện, kể cả `OrderCancelled`.
- Trong billing, **CARD worker** chỉ xử lý thanh toán có `channel = 'CARD'`; các message kênh TRANSFER/WALLET vẫn phải chờ worker khác.

Một message có thể cần **hai hoặc ba bản sao nghiệp vụ** ở các queue độc lập, nhưng bên trong một queue chỉ một worker được ACK một message. Ta cần phân biệt **route vào queue** và **chọn message cho consumer**.

~~~mermaid
flowchart LR
    P["Java publisher"] --> A["Artemis multicast: lab.route.events"]
    A -->|PaymentCaptured AND VN| B[("lab.route.billing.vn")]
    A -->|PaymentCaptured AND amount >= 10M| R[("lab.route.risk.high")]
    A -->|không filter| U[("lab.route.audit")]
    B -->|selector: channel = CARD| C["Billing CARD consumer"]
    B -->|selector khác / không selector| W["Billing other consumer"]
    R --> X["Risk consumer"]
    U --> Y["Audit consumer"]
~~~

Bốn quyết định khác nhau:

1. **Routing type multicast**: một message có thể được xét cho **mỗi queue** thuộc address.
2. **Queue filter**: trước khi message được đưa vào một queue, broker kiểm tra thuộc tính của message.
3. **Consumer selector**: sau khi message đã thuộc queue, chỉ consumer có selector phù hợp mới được nhận.
4. **Acknowledgment/commit**: consumer nhận xong, xử lý và ACK; việc ACK một queue không xóa bản sao ở queue của nhóm khác.

E1 xuất hiện ở cả billing/risk/audit là **bản sao có chủ đích**, không phải lỗi gửi trùng. Nhưng nếu billing xử lý E1 hai lần do rollback/retry, đó là duplicate **trong cùng consumer group**, cần idempotency.

## 2. Chọn vị trí của bộ lọc theo yêu cầu kiến trúc

| Cơ chế | Cấu hình ở đâu? | Thời điểm tác dụng | Không khớp thì sao? | Pattern |
|---|---|---|---|---|
| **Queue filter** | `<queue><filter string="..."/></queue>` trong `broker.xml` | **Trước khi** message vào queue đó | Không thêm vào queue; vẫn có thể vào queue khác | Content-Based Router / Recipient List |
| **Consumer selector** | `JMSContext.createConsumer(queue, selector)`, `Session.createConsumer` | **Sau khi** message đã route vào queue | Message vẫn trong queue, trừ khi consumer khác nhận/ACK | Selective Consumer |
| **Filtered divert** | `<divert>` là con trực tiếp của Artemis `<core>` | Khi message tới address nguồn | Không divert, tiếp tục routing gốc theo quy tắc | Chuyển/nhân message sang **address khác** |
| **Application router** | Java/Spring service | Khi service parse/validate, tra dữ liệu và quyết định | Theo code: reject, quarantine, fallback hay gửi ra một đích | Content-Based Router có logic phức tạp |

**Không dùng hai consumer selector trên cùng một queue để làm fan-out hai nhóm.** Trong một queue, các consumer cạnh tranh nhau; một message phù hợp đồng thời với selector billing và risk chỉ được một consumer ACK. Nếu hai nhóm đều phải xử lý, phải có **hai queue** hoặc một router gửi thành hai bản sao.

Ngược lại, **không cần tạo queue riêng cho mỗi worker CARD/WALLET** nếu billing muốn quản trị backlog chung và có nhóm worker xử lý phần dư. Consumer selector cho phép phân công mềm trong queue đó, với điều kiện có consumer phủ hết những message có thể đến.

## 3. Tập sự kiện cố định và truth table

Ta publish năm message:

| Event ID | `eventType` | `countryCode` | `channel` | `amountMinor` | Billing VN | Risk ≥ 10M | Audit |
|---|---|---|---|---:|---|---|---|
| **E1** | PaymentCaptured | VN | CARD | 12.000.000 | Có | Có | Có |
| **E2** | PaymentCaptured | VN | TRANSFER | 500.000 | Có | Không | Có |
| **E3** | PaymentCaptured | US | CARD | 25.000.000 | Không | Có | Có |
| **E4** | OrderCancelled | VN | CARD | 20.000.000 | Không | Không | Có |
| **E5** | PaymentCaptured | VN | WALLET | 15.000.000 | Có | Có | Có |

Sau publish trên broker sạch:

- Queue `lab.route.billing.vn` có **E1, E2, E5** → 3 message.
- Queue `lab.route.risk.high` có **E1, E3, E5** → 3 message.
- Queue `lab.route.audit` có **E1, E2, E3, E4, E5** → 5 message.

Nếu chạy một consumer billing với selector `channel = 'CARD'`, nó nhận **E1**, còn **E2, E5 vẫn chờ trong queue billing**.

**Hai hàng kiểm chứng quan trọng:** E3 có `channel='CARD'` và amount lớn nhưng **không vào queue billing** vì country US. E4 có amount lớn nhưng **không vào queue risk** vì không phải `PaymentCaptured`. Chỉ lọc amount mà quên eventType sẽ tạo quyết định nghiệp vụ sai.

## 4. Broker-side Content-Based Routing bằng filtered multicast queues

Trong `ARTEMIS_INSTANCE/etc/broker.xml`, tìm **section `<addresses>` đang có trong `<core>`**. Nếu address chưa tồn tại, thêm đúng một phần tử:

~~~xml
<address name="lab.route.events">
    <multicast>
        <queue name="lab.route.billing.vn">
            <filter string="eventType = 'PaymentCaptured' AND countryCode = 'VN'"/>
            <durable>true</durable>
        </queue>

        <queue name="lab.route.risk.high">
            <filter string="eventType = 'PaymentCaptured' AND amountMinor &gt;= 10000000"/>
            <durable>true</durable>
        </queue>

        <queue name="lab.route.audit">
            <durable>true</durable>
        </queue>
    </multicast>
</address>
~~~

**Giải thích:**

- Producer gửi vào **JMS Topic** `lab.route.events`, được Artemis ánh xạ tới multicast address cùng tên.
- Filter của từng queue đánh giá **JMS/Core message properties** tại lúc routing vào queue. Một message có thể khớp cả billing và risk, nên hai queue đều nhận bản sao.
- Queue audit không có filter. Nó giữ mọi event được route đúng multicast, kể cả event bị các queue khác loại.
- `<durable>true</durable>` giúp queue bền vững; để message tồn tại qua broker restart, cần thêm `DeliveryMode.PERSISTENT` và broker persistence phù hợp.
- Trong XML attribute, `<` phải escape `&lt;`, `&` thành `&amp;`. Có thể viết `&gt;=` để biểu diễn `>=` cho nhất quán.
- Không tạo thêm `<addresses>` thứ hai hoặc lặp tên queue; Artemis yêu cầu queue name duy nhất trên broker.

**Không thay toàn bộ `broker.xml` bằng đoạn trên.** Giữ root, acceptors, security, các policy khác; trong lab restart broker sau khi sửa và xác minh các queue/filter bằng console. Việc gọi `createTopic(...)` từ Java không có nghĩa tự sinh ba filtered queues theo ý mình: chúng được provision ở broker trước khi publish.

### Vì sao là multicast, không phải anycast?

Anycast chọn **một queue** trong tập queue anycast phù hợp theo quy tắc broker. Nó không tự fan-out cùng một message cho ba nhóm độc lập. Multicast đưa message vào **mỗi multicast queue phù hợp** và áp filter riêng trên từng queue, nên đúng với pattern recipient list.

### Khi nào filter theo queue không phải lựa chọn phù hợp?

Nếu routing phụ thuộc một API ngoài, trạng thái khách hàng trong DB hoặc cần biến đổi payload cho từng nhóm, queue filter SQL đơn giản không đủ; xem application router ở mục 10. Nếu cần chuyển message tới **address khác** mà không sửa producer, xem filtered divert ở mục 9.

## 5. JMS selector / Artemis filter expression: cú pháp và kiểu dữ liệu

Artemis hỗ trợ filter expression dựa trên một tập con của **SQL-92**. Ngôn ngữ tương đồng JMS selectors, nhưng biểu thức Core filter và JMS selector **không luôn dùng cùng identifier cho provider headers**.

| Biểu thức | Ý nghĩa |
|---|---|
| `eventType = 'PaymentCaptured'` | Chọn đúng event type |
| `countryCode IN ('VN', 'TH')` | Chọn một trong hai quốc gia |
| `amountMinor >= 10000000` | Ngưỡng số tiền với numeric property |
| `channel = 'CARD' AND countryCode = 'VN'` | Hai điều kiện đồng thời |
| `eventType LIKE 'Payment%'` | Tên event type có prefix `Payment` |
| `riskFlag = TRUE` | Boolean property true |
| `region IS NULL` | Property thiếu/không có giá trị theo selector |
| `NOT (channel = 'WALLET')` | Phủ định với logic ba giá trị cần lưu ý |

### 5.1. Property phải được gắn vào JMS message, không chỉ nằm trong JSON body

Ví dụ body:

~~~json
{"eventId":"E1","eventType":"PaymentCaptured",
 "countryCode":"VN","channel":"CARD","amountMinor":12000000}
~~~

Nếu producer chỉ gửi body JSON thì filter `countryCode='VN'` không tự parse JSON. Cần đặt message properties riêng:

~~~java
TextMessage message = context.createTextMessage(json);
message.setStringProperty("eventId", "E1");
message.setStringProperty("eventType", "PaymentCaptured");
message.setStringProperty("countryCode", "VN");
message.setStringProperty("channel", "CARD");
message.setLongProperty("amountMinor", 12000000L);
~~~

Broker dùng properties để lọc; consumer dùng JSON/schema để xử lý nghiệp vụ. Nếu sao chép trường vừa ở body vừa ở property, phải **kiểm tra chúng nhất quán**. Không biến properties thành một bản dữ liệu nghiệp vụ thứ hai thiếu kiểm soát.

### 5.2. Không chuyển String sang number một cách ngầm định

Hai property sau khác nhau:

~~~java
message.setLongProperty("amountMinor", 12000000L);     // Numeric
message.setStringProperty("amountMinor", "12000000"); // String
~~~

Selector chuẩn `amountMinor >= 10000000` cần so sánh numeric đúng kiểu. Nếu amount là String, không nên kỳ vọng phép so số tự ép kiểu. Artemis có mở rộng `convert_string_expressions:` cho một số trường hợp protocol chỉ truyền string properties; đó là **mở rộng riêng của broker**, không nên dùng như hợp đồng JMS portable.

**Null/UNKNOWN:** Nếu `countryCode` không tồn tại, `countryCode = 'VN'` không TRUE. `countryCode <> 'VN'` cũng không tự TRUE: SQL selector dùng logic ba giá trị, message thiếu property thường không khớp cả hai. Muốn xử lý trường hợp thiếu, dùng `IS NULL` hoặc reject/quarantine từ producer.

### 5.3. JMS headers và Core identifiers không nhất thiết trùng

| Ý nghĩa | JMS selector | Artemis Core queue filter |
|---|---|---|
| Application property | `eventType = 'PaymentCaptured'` | Cùng biểu thức nếu property được truyền đúng |
| Priority header | `JMSPriority >= 7` | `AMQPriority >= 7` |
| Message address | Không mặc định là JMS property ứng dụng | `AMQAddress` là identifier Core |
| Durable header | Theo JMS delivery mode / provider semantics | `AMQDurable` = `'DURABLE'` hoặc `'NON_DURABLE'` |

Trong lab chỉ dùng **application properties** để tránh phụ thuộc cách Core/JMS/AMQP/STOMP ánh xạ header. Với provider khác hoặc client dùng protocol khác, hãy đo kiểu property thực tế ở bên nhận.

### 5.4. Tên property và nội dung filter

Dùng tên như `countryCode`, `amountMinor`, `eventType`. Tên `country-code` hoặc `payment.amount` có ký tự không thuộc identifier JMS selector thông thường; Artemis có một số cú pháp quoted identifier riêng, nhưng làm giảm portability. String literal dùng nháy đơn, ví dụ `'CARD'`, không được viết `"CARD"` như Java string literal trong chính selector.

**Không** nối input HTTP tùy ý vào selector string. Nếu cần lọc theo tenant do người dùng chọn, validate/allowlist giá trị, escape literal theo contract và giới hạn quyền xem queue. Selector là cơ chế lọc, **không phải authorization**.

## 6. Java/JMS thực hành: một lần publish, ba queue nhận độc lập

### 6.1. Dependency và điều kiện

Lab dùng Java 17, Jakarta Messaging `jakarta.jms.*` và Artemis Jakarta client cùng broker Core acceptor tại `tcp://127.0.0.1:61616`. Trong project Maven riêng:

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

Version minh họa cần được kiểm tra với broker/JDK của bạn. Cung cấp `ARTEMIS_USER` và `ARTEMIS_PASSWORD` bằng environment, không hardcode secret. Đảm bảo address và cả ba queue tồn tại **trước khi publish**, không có consumer khác trong lúc đo.

### 6.2. Mã nguồn Java 17 đầy đủ

Lớp `AttributeRoutingLab` hỗ trợ năm mode:

- `publish`: gửi E1–E5 vào JMS Topic `lab.route.events`.
- `billing-card`: đọc queue billing với selector `channel = 'CARD'`.
- `billing-rest`: đọc các message còn lại trong billing queue không selector.
- `risk` và `audit`: đọc queue tương ứng không selector.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class AttributeRoutingLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String ADDRESS = "lab.route.events";
    private static final String BILLING = "lab.route.billing.vn";
    private static final String RISK = "lab.route.risk.high";
    private static final String AUDIT = "lab.route.audit";

    private record Event(
        String eventId, String eventType, String countryCode,
        String channel, long amountMinor) {}

    private static final Event[] EVENTS = {
        new Event("E1", "PaymentCaptured", "VN", "CARD",     12000000L),
        new Event("E2", "PaymentCaptured", "VN", "TRANSFER",   500000L),
        new Event("E3", "PaymentCaptured", "US", "CARD",     25000000L),
        new Event("E4", "OrderCancelled",  "VN", "CARD",     20000000L),
        new Event("E5", "PaymentCaptured", "VN", "WALLET",   15000000L)
    };

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            usage();
            return;
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            switch (args[0]) {
                case "publish" -> publish(ctx);
                case "billing-card" -> consume(
                    ctx, BILLING, "channel = 'CARD'");
                case "billing-rest" -> consume(ctx, BILLING, null);
                case "risk" -> consume(ctx, RISK, null);
                case "audit" -> consume(ctx, AUDIT, null);
                default -> usage();
            }
        }
    }

    private static void publish(JMSContext ctx) throws Exception {
        Topic topic = ctx.createTopic(ADDRESS);
        var producer = ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        try {
            for (Event event : EVENTS) {
                String json = """
                    {"eventId":"%s","eventType":"%s",
                     "countryCode":"%s","channel":"%s",
                     "amountMinor":%d}
                    """.formatted(
                        event.eventId(), event.eventType(),
                        event.countryCode(), event.channel(),
                        event.amountMinor());

                TextMessage message = ctx.createTextMessage(json);

                // Broker filters KHÔNG truy vấn trực tiếp JSON body.
                message.setStringProperty(
                    "eventId", event.eventId());
                message.setStringProperty(
                    "eventType", event.eventType());
                message.setStringProperty(
                    "countryCode", event.countryCode());
                message.setStringProperty(
                    "channel", event.channel());
                message.setLongProperty(
                    "amountMinor", event.amountMinor());

                producer.send(topic, message);
                System.out.println("SENT " + event.eventId());
            }

            ctx.commit();
            System.out.println("PUBLISH_COMMITTED 5 events.");
        } catch (Exception failure) {
            ctx.rollback();
            throw failure;
        }
    }

    private static void consume(
            JMSContext ctx, String queueName, String selector)
            throws Exception {

        // Artemis FQQN: access queue vật lý trong multicast address.
        Queue queue = ctx.createQueue(ADDRESS + "::" + queueName);
        JMSConsumer consumer = selector == null
            ? ctx.createConsumer(queue)
            : ctx.createConsumer(queue, selector);

        int committed = 0;
        try {
            while (true) {
                Message message = consumer.receive(1200);
                if (message == null) {
                    break; // Timeout không chứng minh queue rỗng.
                }

                try {
                    if (!(message instanceof TextMessage text)) {
                        throw new IllegalArgumentException(
                            "Expected TextMessage JSON");
                    }

                    String id = text.getStringProperty("eventId");
                    long amount =
                        text.getLongProperty("amountMinor");

                    // Production: validate JSON/properties, xử lý
                    // idempotent trước khi commit JMS.
                    System.out.printf(
                        "queue=%s event=%s country=%s "
                        + "channel=%s amount=%d body=%s%n",
                        queueName, id,
                        text.getStringProperty("countryCode"),
                        text.getStringProperty("channel"),
                        amount, text.getText());

                    ctx.commit();
                    committed++;
                } catch (Exception failure) {
                    ctx.rollback();
                    throw failure;
                }
            }
        } finally {
            consumer.close();
        }
        System.out.println("COMMITTED=" + committed);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Thiếu biến môi trường " + key);
        }
        return value;
    }

    private static void usage() {
        System.out.println(
            "AttributeRoutingLab publish|billing-card|"
            + "billing-rest|risk|audit");
    }
}
~~~

### 6.3. Vì sao publish Topic nhưng consume Queue?

JMS Topic được Artemis ánh xạ tới **multicast address**. Mỗi subscription của topic thường là một queue, nhưng bài này đã provision sẵn ba queue chứa filter. Để đọc **đúng queue vật lý**, ta dùng Artemis **Fully Qualified Queue Name (FQQN)**:

~~~java
Queue billing = ctx.createQueue(
    "lab.route.events::lab.route.billing.vn");
~~~

Cú pháp `address::queue` là tính năng của Artemis, **không portable** với mọi JMS provider. Nếu đổi sang `ctx.createConsumer(ctx.createTopic(ADDRESS))`, một subscription mới có thể được tạo, làm số queue và kết quả không còn giống lab.

### 6.4. Transaction và ranh giới an toàn

- Producer gửi năm message trong **một JMS transaction** rồi `commit()`. Trước commit, log `SENT` chỉ nói các lệnh send đã được thực hiện, **chưa** khẳng định broker đã commit batch.
- Consumer `commit()` từng message sau xử lý. Nếu lỗi trước commit, rollback khiến message đủ điều kiện giao lại theo policy.
- Consumer khác cùng queue có thể nhận message nếu phù hợp và đủ điều kiện; không chạy nhiều consumer lúc muốn quan sát bảng kỳ vọng.
- `eventId` E1–E5 là dữ liệu cố định trong lab. Nếu publish lại, các bản sao mới chứa cùng eventId; phải reset queue hoặc chọn runId riêng để tránh nhầm. Production giữ eventId ổn định qua retry và dùng idempotency.

## 7. Trình tự chạy và bảng kiểm chứng

**Điều kiện trước thử:** ba queue đều rỗng, broker đã nạp XML, không có consumer khác, không có TTL/expiry làm message biến mất.

1. Chạy `AttributeRoutingLab publish` **một lần**; chờ `PUBLISH_COMMITTED 5 events.`
2. Kiểm tra trong Artemis Console:
   - Billing queue: **3** message (E1, E2, E5).
   - Risk queue: **3** message (E1, E3, E5).
   - Audit queue: **5** message (E1, E2, E3, E4, E5).
3. Chạy `AttributeRoutingLab billing-card`. Chỉ E1 được nhận: `COMMITTED=1`.
4. Kiểm tra billing còn E2/E5 (**2 message**), không tự xóa vì không khớp selector CARD.
5. Chạy `billing-rest`: nhận E2/E5, `COMMITTED=2`.
6. Chạy `risk`: E1/E3/E5, `COMMITTED=3`.
7. Chạy `audit`: E1–E5, `COMMITTED=5`.

| Thời điểm | Billing VN | Risk | Audit |
|---|---:|---:|---:|
| Trước publish | 0 | 0 | 0 |
| Sau publish | 3 | 3 | 5 |
| Sau `billing-card` | 2 | 3 | 5 |
| Sau `billing-rest` | 0 | 3 | 5 |
| Sau `risk` | 0 | 0 | 5 |
| Sau `audit` | 0 | 0 | 0 |

Con số giả định queue sạch, send/commit thành công và không có consumer khác. Trong console có thể tách `ready` và `delivering/in-flight`; đo sau khi process thoát để tránh hiểu nhầm. `receive(1200)==null` chỉ nói **không có message phù hợp sẵn trong thời gian chờ**, không chứng minh queue rỗng tuyệt đối.

### Thử phản chứng: thay đổi nơi lọc

- Nếu dùng `billing-rest` ngay sau publish mà không chạy `billing-card`, nó nhận **E1/E2/E5**. Điều này chứng minh queue billing có cả ba, selector chỉ là lựa chọn của consumer.
- Nếu bỏ filter billing trong **một queue lab mới đã reset**, billing có thể chứa cả E3/E4; selector CARD khi ấy có thể nhận E1/E3/E4. Không suy rằng sửa filter sẽ tự thêm các message cũ đã bị loại trước đây.
- Nếu đổi property `amountMinor` thành String nhưng giữ filter risk so số, kết quả không còn bảo đảm giống bảng chuẩn. Hãy đo đúng representation và sửa producer.

## 8. Content-Based Router và Recipient List: lựa chọn đúng ngữ nghĩa

**Content-Based Router** quyết định destination dựa trên nội dung/metadata, ví dụ `PaymentCaptured AND countryCode=VN` vào nhánh billing.

**Recipient List** quyết định một message có **nhiều người nhận**. Trong multicast, E1 vào billing/risk/audit vì cả ba queue độc lập đều phù hợp.

### Khi phải chọn chính xác một trong hai nhánh

Nếu workflow muốn:

~~~text
PaymentCaptured amount >= 10M → high-value
PaymentCaptured amount <  10M → standard
~~~

thì cần **hai điều kiện loại trừ nhau**, không chỉ hai worker cạnh tranh:

~~~xml
<queue name="lab.route.high">
    <filter string="eventType = 'PaymentCaptured' AND amountMinor &gt;= 10000000"/>
</queue>
<queue name="lab.route.standard">
    <filter string="eventType = 'PaymentCaptured' AND amountMinor &lt; 10000000"/>
</queue>
~~~

Đây là mảnh cấu hình cho **một address multicast khác**, không thêm hai queue đó vào lab chính nếu chưa có yêu cầu. Message không có `amountMinor` hoặc eventType khác `PaymentCaptured` sẽ không khớp cả hai; cần fallback/quarantine hoặc validation producer.

**Không xem anycast + filter như một if/else router tuyệt đối** nếu cần bằng chứng chính xác nhánh nào nhận: anycast còn có quy tắc chọn queue riêng của broker. Multicast với filter loại trừ nhau, hoặc application router, thường dễ lý giải hơn.

### Khi một message cần hai service cùng xử lý

Trong bảng E1, billing và risk đều cần làm việc, nên **hai queue** là chủ ý. Đừng đổi thành hai selector consumer trên cùng một queue, vì chúng có ngữ nghĩa competing consumers, không phải publish-subscribe độc lập.

## 9. Filtered divert: chuyển sang address khác mà producer không thay đổi

Artemis có cơ chế **divert** để chuyển message từ một address sang address khác theo filter. Đây là giải pháp broker-side khác với queue filter và hữu ích khi hệ thống cũ đã cố định destination producer.

### 9.1. Ví dụ non-exclusive divert, độc lập với lab chính

Giả sử producer cũ gửi JMS Queue `lab.route.commands`. Muốn copy chỉ những message `PaymentCaptured` sang audit address khác mà **không** làm mất message ở queue gốc.

Trong `<addresses>` hiện có, tạo hai anycast address:

~~~xml
<address name="lab.route.commands">
    <anycast>
        <queue name="lab.route.commands">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
<address name="lab.route.command.audit">
    <anycast>
        <queue name="lab.route.command.audit">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Tại **cấp `<core>`** (không ở trong `<addresses>`), cấu hình:

~~~xml
<divert name="audit-payment-command">
    <routing-name>audit-payment-command</routing-name>
    <address>lab.route.commands</address>
    <forwarding-address>lab.route.command.audit</forwarding-address>
    <filter string="eventType = 'PaymentCaptured'"/>
    <exclusive>false</exclusive>
    <routing-type>ANYCAST</routing-type>
</divert>
~~~

**Phân tích:**

- `address` là nguồn; `forwarding-address` là đích khác trên **cùng broker**.
- `filter` chỉ chọn message có eventType PaymentCaptured.
- `exclusive=false` giữ đường gốc và thêm một bản sao ở audit.
- `exclusive=true` chuyển message khớp **chỉ sang address đích**, không route message đó vào address gốc. Đây không phải cùng nghĩa với `exclusive queue` cho consumer tuần tự.
- `routing-type=ANYCAST` yêu cầu routing đích phù hợp với queue anycast đã khai báo, không dựa vào routing type mặc định khi forward.

**Không tự động kết hợp divert này với ba filtered queues của lab chính**: nếu cùng một nhóm đã nhận bản sao qua multicast, divert có thể tạo bản sao thứ hai ngoài ý định. Với nhiều exclusive/non-exclusive diverts, thứ tự áp dụng còn ảnh hưởng đường đi; phải test khi có quy tắc chồng lấn.

Divert chỉ làm việc **trong cùng server**. Nếu đích thuộc broker khác, cần thêm bridge/federation hoặc forwarding component thích hợp. Theo tài liệu Artemis, sửa nội dung divert đang chạy không nhất thiết có hiệu lực qua hot reload; trong lab hãy restart và xác minh trong management.

## 10. Khi cần định tuyến trong application

Queue filter và JMS selector chỉ làm việc tốt với metadata có kiểu ổn định, điều kiện đơn giản và ít thay đổi. Một service **application router** hợp lý hơn khi cần:

- Gọi API tra danh sách quyền nhận theo tenant hoặc account.
- Đọc body JSON phức tạp, validate chữ ký số/schema rồi định tuyến.
- Chuyển đổi thông tin trước khi gửi; ví dụ bản audit phải xóa PII, bản fraud được phép nhận một tập field khác.
- Kết hợp nhiều sự kiện hoặc tra trạng thái DB theo thời gian.
- Áp dụng quota, preference hoặc danh sách người nhận thay đổi liên tục.

Ví dụ Java chọn queue theo domain event **trước khi publish**:

~~~java
// Mảnh code trong service đã có context, event, objectMapper.
Destination target = event.amountMinor() >= 10000000L
    ? context.createQueue("orders.manual-review")
    : context.createQueue("orders.standard");

TextMessage message = context.createTextMessage(
    objectMapper.writeValueAsString(event));
message.setStringProperty("eventId", event.eventId());
message.setLongProperty("amountMinor", event.amountMinor());

context.createProducer()
    .setDeliveryMode(DeliveryMode.PERSISTENT)
    .send(target, message);
context.commit();
~~~

Trong ví dụ, hai destination phải được provision và phân quyền phù hợp; code trên chỉ là phần của một phương thức có context transacted và phải xử lý rollback khi gửi lỗi. **Không lấy tên broker destination tùy ý từ HTTP request rồi tạo queue động** mà không có allowlist và quota.

Nếu router **nhận từ input queue rồi phát sang output queue**, tránh xử lý kiểu “ACK input trước → send output sau”, vì crash giữa hai bước làm mất công việc. Khi cả input/output cùng broker và session, dùng JMS transaction receive/send/commit; khi có DB/broker khác, xem outbox, retry và idempotency.

## 11. Khi filter và selector tạo backlog hoặc mất đường đến đích

### 11.1. Message không khớp selector vẫn nằm trong queue

Giả sử tất cả billing worker đều chỉ có selector `channel='CARD'`. Các message TRANSFER/WALLET tích lũy **vô hạn** nếu không có consumer phù hợp và TTL/DLQ khác không xử lý chúng. Không ai tự “đẩy qua audit” thay billing. Đo **ready count và oldest message age** của billing queue để phát hiện phần dư.

### 11.2. Queue filter sai làm mất bản sao của một nhóm

Nếu risk filter sai kiểu `amountMinor` hoặc bỏ sót một event type mới, những message bị từ chối **không được route vào risk queue**. Sửa filter **không hồi tố** các message trước đó; muốn backfill phải replay từ nguồn sự kiện còn giữ bản gốc như audit/outbox/event log, kèm kiểm soát duplicate.

### 11.3. Selectors và paging

Khi một queue có hàng triệu message nhưng selector chỉ chọn 1%, broker/client có thể phải kiểm tra lượng backlog không khớp và gặp giới hạn khi paging. Các consumer với selector rất hẹp có thể đọc chậm hoặc không tiến triển theo kỳ vọng nếu message phù hợp nằm sâu trong backlog. Với nhóm xử lý ổn định và tải lớn, **lọc trước khi đưa vào queue** có thể tiết kiệm I/O và giảm backlog so với lưu tất cả rồi mới lọc tại consumer.

### 11.4. Không cam kết thứ tự xử lý giữa các queue

Multicast giữ các queue độc lập; billing ACK E1 không có nghĩa risk cũng đã ACK E1. Một consumer có thể nhanh hơn nhóm khác; retry/redelivery và DLQ cũng khác nhau. Nếu nghiệp vụ cần thứ tự theo `orderId`, dùng sequence/version hoặc message grouping tại đúng queue, không dựa trên thứ tự fan-out toàn hệ thống.

## 12. Bảo mật và quan sát

**Queue filter không phải access control.** Một client được cấp quyền consume từ audit queue có thể xem những sự kiện không thuộc billing/risk. Phân quyền Artemis theo address/queue FQQN khi cần:

~~~xml
<!-- Mảnh cấu hình của <security-settings>; role phải được tạo trước. -->
<security-setting match="lab.route.events">
    <permission type="send" roles="event-publisher"/>
</security-setting>
<security-setting match="lab.route.events::lab.route.billing.vn">
    <permission type="consume" roles="billing-reader"/>
</security-setting>
<security-setting match="lab.route.events::lab.route.risk.high">
    <permission type="consume" roles="risk-reader"/>
</security-setting>
<security-setting match="lab.route.events::lab.route.audit">
    <permission type="consume" roles="audit-reader"/>
</security-setting>
~~~

Đây là cấu hình ý tưởng, không phải bộ permission production hoàn chỉnh: vẫn cần xét wildcard rules, quyền tạo queue/browse, authentication và quyền quản lý. Quyền `send` trên address không được nhầm với quyền `consume` riêng queue qua FQQN.

**Các metric nên có:**

- Publish count theo `eventType` và address.
- Enqueue/dequeue, ready/delivering count và oldest message age theo từng queue.
- Count message bị từ chối bởi schema/metadata validation.
- Selector coverage: số message mỗi channel và tồn đọng nhóm không có consumer.
- Redelivery/DLQ theo consumer group, idempotency duplicate count theo `(group,eventId)`.
- Paging/flow-control và producer commit latency.

Không ghi payload nhạy cảm hoặc password trong log chỉ để debug. Cần log có cấu trúc theo `eventId`, `countryCode`, `eventType` và `consumerGroup` ở mức được cho phép, nhưng hạn chế high-cardinality labels trong metrics.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
|---|---|---|
| E1 không vào billing/risk | Quên gắn JMS properties; gửi sai routing type | Kiểm tra type/property, dùng JMS Topic vào multicast address |
| E3 lại vào billing | Queue filter không được nạp, sai FQQN hoặc đọc nhầm queue | Kiểm tra filter thực tế trong Artemis Console |
| E4 vào risk | Filter chỉ có amount, quên `eventType` | Kiểm tra lại truth table |
| CARD consumer chỉ thấy E1, queue còn E2/E5 | Message không khớp selector vẫn ở queue | Chạy worker TRANSFER/WALLET hoặc consumer không selector |
| Billing và risk cùng dùng một queue nhưng không cùng nhận E1 | Competing consumers, không fan-out | Dùng queue riêng qua multicast |
| Selector số không khớp | `amountMinor` kiểu String hoặc thiếu | Dùng `setLongProperty` và kiểm tra runtime property type |
| Audit thấy hai E1 khác JMSMessageID | Có thêm divert hoặc publish lặp | Kiểm tra đường route và eventId, không nhân bản vô ý |
| Sửa queue filter không có message lịch sử | Filter không route message vào queue từ đầu | Backfill từ nguồn lưu khác, idempotency |
| Queue tăng dù consumer không có lỗi | Selector không phủ các loại message mới | Quan sát age và định nghĩa fallback |
| Gửi thành công nhưng consumer không nhận | Không có queue phù hợp, quyền thiếu, selector quá hẹp, message expire | Kiểm tra routing, security, ready/delivering và expiry |
| Một nhóm xử lý E1 hai lần | Redelivery sau DB commit nhưng trước JMS ACK | Unique constraint / idempotency theo (group,eventId) |
| Dữ liệu tenant ngoài phạm vi lộ qua queue audit | Coi filter là bảo mật | Authorization theo FQQN, payload transformation/redaction |

## 14. Bài tập tự đánh giá

1. E6 có `PaymentCaptured, VN, CARD, amountMinor=9999999`. E6 sẽ nằm trong queue nào? **Billing và audit**, không thuộc risk.
2. E7 có JSON body amount lớn nhưng không có JMS property `amountMinor`. Risk filter có tự parse JSON không? **Không**.
3. Billing và risk dùng hai selector trên cùng queue. Có bảo đảm cả hai cùng xử lý một E1 không? **Không**, đây là competing consumers.
4. Sau khi billing-card ACK E1, billing queue còn E2/E5. Message đã mất? **Không**, cần consumer phù hợp.
5. Nếu cần cả queue gốc và audit address mới nhận `PaymentCaptured` qua divert, dùng `exclusive=true` hay `false`? **False**.
6. Nếu cần một message chỉ đi **một** trong hai nhánh high/standard, làm gì? Dùng hai filter **loại trừ nhau** và có đường xử lý property thiếu hoặc ứng dụng router.
7. Vì sao `amountMinor >= 10000000` không portable nếu bên gửi STOMP chỉ có string header? Vì numeric property có thể bị chuyển thành String.
8. Khi nào cần router Java thay cho queue filter? Khi routing phụ thuộc schema phức tạp, tra DB/API hoặc biến đổi payload.
9. Vì sao idempotency key nên là `(consumerGroup, eventId)`? Vì E1 phải được billing và risk xử lý độc lập, nhưng mỗi nhóm không được lặp side effect do redelivery.
10. Sửa filter billing sang cho phép TH có tự đưa lại các event TH trước đây bị loại không? **Không**, cần replay từ nguồn lưu gốc.

## 15. Tài liệu tham khảo và kết luận

- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): multicast/anycast, FQQN và thời điểm queue filter/consumer selector.
- [Apache ActiveMQ Artemis — Filter Expressions](https://artemis.apache.org/components/artemis/documentation/latest/filter-expressions.html): SQL-92 subset, Core identifier, property types và extension.
- [Apache ActiveMQ Artemis — Diverts](https://artemis.apache.org/components/artemis/documentation/latest/diverts.html): filtered divert, exclusive/non-exclusive, forwarding address.
- [Apache ActiveMQ Artemis — Security](https://artemis.apache.org/components/artemis/documentation/latest/security.html): quyền consume theo FQQN.
- [Apache ActiveMQ Artemis — Configuration Reload](https://artemis.apache.org/components/artemis/documentation/latest/config-reload.html): thay đổi divert đã triển khai không nhất thiết được reload tự động.
- [Jakarta Messaging — Message Selectors](https://jakarta.ee/specifications/messaging/): biểu thức selector và các JMS message properties.

**Kết luận:** Queue filter xác định **bản sao nào được lưu trong queue**, consumer selector quyết định **consumer nào được nhận từ queue đã có**, còn filtered divert chuyển/nhân message **giữa các address** theo điều kiện; application router phù hợp khi cần logic ngoài filter tĩnh. Với yêu cầu nhiều recipient, hãy tách queue đúng, giữ properties đủ và đúng kiểu, kiểm chứng eventId → queue → consumer, đồng thời bảo vệ bằng authorization, redelivery và idempotency.
