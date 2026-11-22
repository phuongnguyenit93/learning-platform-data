# Duplicate detection của Artemis và giới hạn so với chống lặp nghiệp vụ

> **Chương:** Độ tin cậy  
> **Công nghệ:** Apache ActiveMQ Artemis, Java/JMS; đối chiếu với idempotency của ứng dụng khi một message bị gửi hoặc xử lý lặp.

Một producer gửi lệnh vào broker, mạng ngắt ngay lúc broker đang trả kết quả, producer không chắc message đã đến hay chưa. Gửi lại là cách phục hồi tự nhiên, nhưng có thể khiến **hai bản của cùng một message** cùng được đưa vào queue. Artemis cung cấp **duplicate detection** để nhận biết lần gửi lặp theo một ID do phía gửi cung cấp. Cơ chế này hữu ích, song **không thay thế được chống xử lý trùng trong nghiệp vụ**: consumer có thể bị giao lại message, hoặc hai message hợp lệ về mặt broker vẫn yêu cầu cùng một hiệu ứng thanh toán.

Bài này chỉ tập trung vào **cách Artemis phát hiện message gửi trùng, phạm vi và độ bền của bộ nhớ ID, cách gửi ID qua Java/JMS, giới hạn qua transaction/HA/bridge, và cách kết hợp với idempotent consumer**. Những kiến thức queue/topic, JMS session hoặc DLQ chỉ được nhắc lại khi thật sự cần giải thích duplicate detection.

## 1. Hai loại “lặp” phải được tách ra

Đặt một lệnh thanh toán có **paymentAttemptId = pay-741**. Có ít nhất hai vấn đề khác nhau:

**Lặp khi publish (ingress duplicate):** cùng một lệnh logic được gửi vào address Artemis nhiều lần vì producer retry.

**Lặp khi consume (delivery hoặc business duplicate):** broker đã có một message, nhưng consumer nhận lại sau rollback/crash; hoặc có **hai message khác nhau** cùng yêu cầu trừ tiền cho pay-741.

| Trường hợp | Artemis duplicate detection có xử lý được? | Lớp bảo vệ cần thiết |
|---|---|---|
| Producer gửi lại **cùng duplicate ID**, cùng address, ID vẫn trong cache | **Có**, broker có thể chặn lần gửi lặp trước khi đưa vào queue | Duplicate detection + kiểm tra cấu hình |
| Consumer xử lý DB thành công, crash trước ACK; message được broker giao lại | **Không**, đây là redelivery của message đã được chấp nhận | Inbox/idempotency + ACK/transaction |
| Hai producer tạo hai message với **hai duplicate ID khác nhau** cho một paymentAttemptId | **Không** | Khóa nghiệp vụ/idempotency key |
| Producer gửi lại cùng ID nhưng cache đã quên ID vì eviction/restart cấu hình không persist | **Không bảo đảm phát hiện** | Cache được cấu hình phù hợp + idempotent consumer |
| Một message multicast được định tuyến tới nhiều subscription | **Không phải gửi trùng** | Mỗi subscription cần xử lý phần việc của mình |
| Message được gửi lại sang **address khác** với cùng duplicate ID | Không được dựa vào cache của address cũ | Hợp đồng định tuyến và idempotency xuyên address |

### 1.1. Vị trí duplicate detection trong đường đi

~~~mermaid
flowchart LR
    P["Producer / Outbox Publisher"] --> S["Artemis: nhận message"]
    S --> H{"Có _AMQ_DUPL_ID?"}
    H -->|Không| R["Định tuyến bình thường"]
    H -->|Có| C{"ID đã có trong cache<br/>của address?"}
    C -->|Chưa có| N["Ghi nhận ID theo cơ chế broker"] --> R
    C -->|Đã có| X["Không route bản gửi trùng"]
    R --> Q["Queue / subscription"]
    Q --> D["Consumer: kiểm tra<br/>business idempotency"]
    D --> DB["DB / side effect"]
~~~

Sơ đồ mang tính **logic**: trạng thái ID, transaction và journal có chi tiết triển khai riêng; không suy luận rằng broker ghi ID trước hay sau một disk write cụ thể. Điều quan trọng là **duplicate detection kiểm tra ở đầu vào broker, trước khi bản gửi lặp được xử lý như một message mới trong queue**.

### 1.2. Mức đảm bảo thực tế

Duplicate detection là cơ chế **best-effort có bộ nhớ hữu hạn và phạm vi xác định**. Khi ID phù hợp còn trong cache của Artemis, bản gửi lại được nhận diện. Nó **không phải** bảo đảm “một nghiệp vụ thực thi đúng một lần vĩnh viễn”.

Thay vì mô tả mơ hồ là exactly-once, nên ghi yêu cầu kiểm chứng:

- **At most one enqueue** cho các lần gửi lại cùng duplicate ID vào cùng address **khi ID còn được broker ghi nhớ**.
- **At-least-once handling** vẫn có thể xảy ra ở consumer tùy ACK/transaction và lỗi.
- **Exactly-once business effect** đòi hỏi quy tắc duy nhất của nghiệp vụ cùng cơ chế idempotency/transaction phù hợp.

## 2. Gắn duplicate ID bằng thuộc tính nào?

Artemis nhận diện thông điệp có **duplicate detection ID** thông qua thuộc tính đặc biệt **_AMQ_DUPL_ID**. Đây là thuộc tính do **producer/client** gửi tới broker, **không phải JMSMessageID do provider cấp**.

Với Artemis **Core API**, hằng số liên quan thường được gọi là **Message.HDR_DUPLICATE_DETECTION_ID**. Với Artemis **JMS client**, có thể đặt JMS String property bằng đúng tên **_AMQ_DUPL_ID**:

~~~java
TextMessage message = context.createTextMessage(payload);
message.setStringProperty("_AMQ_DUPL_ID", "payment-command-cmd-991");
producer.send(queue, message);
~~~

**Nguyên tắc gán ID:**

1. Cùng **một message logic** được publisher phát lại → dùng **cùng _AMQ_DUPL_ID**.
2. Hai event/command **khác nhau** cùng gửi vào một address → dùng **hai duplicate ID khác nhau**.
3. ID phải được tạo **trước lần gửi đầu tiên**, lưu cùng bản ghi nguồn/outbox và tái sử dụng khi retry. UUID được sinh lại trong vòng retry là sai.
4. ID phải đủ duy nhất giữa **các producer cùng gửi vào một address**. Chỉ dùng số đếm cục bộ như “1, 2, 3” có thể đụng ID sau restart hoặc giữa nhiều instance.
5. **Không sửa ID chỉ vì thay connection, failover hoặc resend.** Lỗi kết nối không biến yêu cầu cũ thành command mới.
6. Tránh ID chứa secret/PII. Dùng chuỗi ngắn, ổn định và có cấu trúc nếu cần, chẳng hạn **eventId** từ outbox.

**Định dạng:** với Java/JMS, ví dụ này dùng **String property**. Core protocol có thể hỗ trợ biểu diễn ID khác tùy API; khi có JMS/AMQP/bridge, hãy kiểm tra mapping và chọn định dạng ID chung dễ bảo toàn. Không tự mặc định một custom JMS property tùy ý như **eventId** sẽ kích hoạt cơ chế của broker; Artemis cần đúng thuộc tính được duplicate detection nhận diện.

### 2.1. Đừng dùng JMSMessageID để phát hiện publisher retry

~~~text
Lần gửi đầu:
    JMSMessageID       = ID:provider-A
    _AMQ_DUPL_ID       = evt-42
    eventId            = evt-42

Lần retry là một thao tác send mới:
    JMSMessageID       = ID:provider-B
    _AMQ_DUPL_ID       = evt-42
    eventId            = evt-42
~~~

Broker sử dụng **_AMQ_DUPL_ID** để xem lần gửi thứ hai có trùng theo cache không. **JMSMessageID** của hai lần gửi có thể khác, vì đó là ID do provider cấp cho từng message. **eventId** nằm trong hợp đồng ứng dụng để consumer chống lặp ngay cả khi broker không chặn được.

### 2.2. Khi nào không nên tái sử dụng một duplicate ID?

Ví dụ người dùng thanh toán lại sau khi một lần thử **được xác nhận từ chối** và nghiệp vụ thật sự sinh **paymentAttemptId mới**:

~~~text
attempt #1: paymentAttemptId=pay-741
            duplicateId=cmd-991

attempt #2: paymentAttemptId=pay-742
            duplicateId=cmd-992
~~~

Nếu dùng cùng duplicate ID cho hai command hợp lệ, broker có thể **loại bỏ command thứ hai**, dù đó là thao tác nghiệp vụ mới. Quy tắc đúng không phải “một đơn hàng = một duplicate ID”, mà là **“một lần publish logic cần tái gửi = một duplicate ID”**.

## 3. Cache duplicate ID của Artemis: phạm vi, dung lượng, độ bền

Artemis lưu những ID đã thấy trong **duplicate ID cache**. Điều quan trọng khi cấu hình là **bộ nhớ này có giới hạn và được quản lý theo address**.

### 3.1. Phạm vi theo address

Ví dụ:

~~~text
Address: billing.payment.commands.v1
    duplicate ID: cmd-991 → đã thấy

Address: notifications.email.commands.v1
    duplicate ID: cmd-991 → chưa chắc đã thấy
~~~

Gửi lại **cmd-991** vào cùng address **billing.payment.commands.v1** khi cache còn ID có thể bị loại. Nhưng nếu gửi vào address khác, không thể coi ID đã có ở address thanh toán là lá chắn cho address email.

Một address **MULTICAST** có thể route một lần publish hợp lệ tới nhiều queue/subscription. Cache phục vụ **phát hiện lần gửi trùng tới address**, không phải “đảm bảo chỉ một subscription được nhận event”. Vì vậy:

~~~text
orders.lifecycle.events.v1  [MULTICAST]
    ├── inventory.subscription  ← một bản của event hợp lệ
    └── notification.subscription ← một bản của event hợp lệ
~~~

Hai queue nhận cùng eventId **không phải lỗi duplicate publish**. Nếu event được phát lại cùng _AMQ_DUPL_ID khi cache còn ID, broker có thể không route thêm bản sao vào cả hai queue. Mỗi consumer group vẫn phải có idempotency của riêng nó.

### 3.2. Dung lượng cache quyết định cửa sổ phát hiện

Cache là **hữu hạn**. Sau khi lưu đủ nhiều ID mới, ID cũ có thể bị đẩy ra để nhường chỗ. Khi một duplicate ID đã bị eviction, bản resend cũ **có thể được coi như message mới**.

Ví dụ minh họa một cache chỉ giữ được ba ID:

~~~text
Thời điểm       ID mới đến       Các ID còn được nhớ (minh họa)
t1              A                A
t2              B                A, B
t3              C                A, B, C
t4              D                B, C, D
t5              A (retry cũ)     A không còn trong cache trước t5
                                 → không thể chặn dựa vào lịch sử đã mất
~~~

Đây là sơ đồ về **giới hạn lưu giữ**, không phải cam kết thuật toán eviction chính xác của mọi phiên bản Artemis. Phải kiểm chứng hành vi và cấu hình với broker thực tế.

**Chọn dung lượng thế nào?** Tối thiểu cân nhắc số **duplicate ID khác nhau đi qua cùng address trong cửa sổ mà producer có thể retry**.

Ví dụ có trung bình 300 message/giây, producer có thể retry sau tối đa 10 phút:

~~~text
300 IDs/giây × 600 giây = 180.000 IDs
~~~

Đó là **ước lượng sàn về dung lượng ID cần giữ theo lưu lượng trung bình**, chưa cộng burst, nhiều producer, lệch đồng hồ, replay outbox, downtime, transaction hoặc margin. **Cần đo thực tế** vì bộ đệm có chi phí RAM/disk và không thể biến cache hữu hạn thành lịch sử nghiệp vụ vĩnh viễn.

### 3.3. Cấu hình bộ nhớ ID trong broker.xml

Trong cấu hình **Apache ActiveMQ Artemis**, các phần tử sau thuộc vùng cấu hình **core** của broker, **không** nằm trong **address-settings**:

~~~xml
<!-- Fragment cấu hình core của Artemis broker.xml -->
<id-cache-size>20000</id-cache-size>
<persist-id-cache>true</persist-id-cache>
~~~

- **id-cache-size:** số ID mà cache giữ theo chính sách của broker. Giá trị **20000** ở đây là ví dụ; chọn theo throughput/cửa sổ retry và giới hạn tài nguyên, không coi là con số tối ưu chung.
- **persist-id-cache:** cho phép lưu trạng thái duplicate ID cache theo cơ chế persistence của broker để nó có thể được khôi phục khi broker khởi động lại. Cần bật persistence tổng thể và xác minh hành vi phiên bản đang dùng.

**Chú ý:** persistence của message và persistence của duplicate ID cache là những thành phần cấu hình liên quan nhưng **không nên đồng nhất**. Nếu message store còn message sau restart mà duplicate ID cache không được khôi phục, một producer có thể resend bản cũ và broker nhận thêm bản mới.

Đừng tắt persistence hoặc đặt cache quá nhỏ chỉ vì thử nghiệm cho thấy send nhanh hơn; phải đo tác động đến duplicate ingress sau downtime và replay.

### 3.4. Restart, failover và cluster

| Tình huống | Điều có thể xảy ra | Biện pháp |
|---|---|---|
| Restart cùng broker, cache được persist và khôi phục | Các ID còn được lưu có thể tiếp tục được nhận diện | Test bằng cùng ID trước/sau restart |
| Restart khi không persist ID cache | Lịch sử duplicate ID có thể không còn | Idempotency ở consumer; cân nhắc persist |
| Failover sang backup / node khác | Khả năng nhìn thấy ID cũ phụ thuộc topology, replication/shared store và phiên bản | Test failover thật, không suy luận từ mỗi cờ persist |
| Producer đổi đích từ address A sang B | Cache theo address A không tự áp sang B | Business ID xuyên address, kiểm soát routing |
| Thay broker bằng instance mới không có trạng thái cũ | Duplicate ID history có thể mất | Recovery/replay an toàn bằng inbox và outbox |

**Không viết yêu cầu “cache tồn tại vĩnh viễn qua mọi failover”** nếu chưa kiểm chứng cơ chế lưu/replicate của topology cụ thể. HA, cluster routing và duplicate cache là các trách nhiệm khác nhau.

## 4. Broker xử lý một lần gửi trùng như thế nào?

Giả sử producer gửi message với **_AMQ_DUPL_ID = evt-42** vào **billing.payment.commands.v1**.

1. **Lần đầu:** broker chưa có ID này trong cache của address → message được xử lý/định tuyến bình thường theo transaction/routing policy; ID được ghi nhớ.
2. **Lần retry:** broker nhận message khác mang cùng duplicate ID khi cache còn hiệu lực → xem là duplicate và **không route thêm bản gửi trùng** vào queue.
3. **Không có _AMQ_DUPL_ID:** Artemis không có khóa duplicate detection tương ứng để phát hiện bằng cơ chế này; message được xét theo routing bình thường.
4. **ID cũ đã bị eviction:** broker không còn đủ lịch sử để phân biệt bản retry với message mới theo cache.

Một điểm vận hành dễ gây nhầm: việc broker **nhận diện rồi bỏ qua** một bản gửi trùng **không nhất thiết là một lỗi JMS làm producer nhận exception**. Tùy protocol và đường gửi, producer có thể thấy thao tác hoàn tất mà queue **không tăng thêm message**. Vì vậy khi kiểm thử, phải đo **enqueue/routed count và nội dung queue**, không chỉ nhìn lệnh send trả về.

### 4.1. Gửi trong transaction

Khi producer gửi một nhóm message trong **JMS transacted session**, trạng thái duplicate ID và transaction có tương tác. Với Artemis, một duplicate ID phát hiện trong transaction có thể khiến **cả transaction bị bỏ qua** theo quy tắc duplicate detection của broker; không nên thiết kế một transaction chứa nhiều tác vụ không liên quan rồi giả định những message không trùng vẫn luôn được route.

**Quy tắc thực hành:** đối với ví dụ cần kiểm chứng, dùng **mỗi transaction chỉ một message logic** và một duplicate ID. Nếu bài toán bắt buộc publish batch nhiều message/transaction, kiểm thử rõ tác động của duplicate ID đến **toàn batch**, hoặc thiết kế unit of work và retry sao cho tất cả message trong transaction thuộc cùng một lần publish logic. Không đặt một duplicate ID giống nhau cho nhiều message khác nhau một cách tùy tiện.

### 4.2. Phân biệt duplicate detection với DLQ và expiry

Message bị broker chặn như **duplicate ingress** thông thường không trải qua vòng đời “consumer nhận → rollback → max delivery attempts → DLQ” của một poison message. Nó cũng không phải message hết TTL.

| Cơ chế | Kích hoạt khi | Ý nghĩa |
|---|---|---|
| **Duplicate detection** | Broker nhận bản publish có duplicate ID đã ghi nhớ | Ngăn bản gửi lại vào queue |
| **Redelivery** | Message đã vào queue nhưng chưa được ACK/commit khi consumer thất bại | Giao lại message đang tồn tại |
| **DLQ** | Retry/delivery lỗi theo policy đến ngưỡng | Cách ly message không xử lý được |
| **Expiry** | Message hết thời hạn hữu ích theo TTL/policy | Loại bỏ/chuyển theo expiry policy |

Nếu metric **send attempts** phía producer tăng nhưng queue count không tăng, hãy cân nhắc **duplicate suppression** trước khi kết luận broker làm rơi message ngẫu nhiên. Nhưng cũng phải kiểm tra sai routing, TTL, authorization và transaction.

## 5. Ví dụ Java/JMS: send hai lần với cùng _AMQ_DUPL_ID

Ví dụ sau dùng **Artemis JMS client** với **javax.jms** (API JMS 2.x). Không áp dụng trực tiếp nội dung về _AMQ_DUPL_ID sang ActiveMQ Classic như một tính năng chung không cần cấu hình: **đây là cơ chế của Artemis**.

### 5.1. Điều kiện lab

- Artemis broker thử nghiệm, URL ví dụ **tcp://localhost:61616** với Core acceptor tương ứng.
- Đã provision **address ANYCAST + queue billing.payment.commands.v1**; hoặc bật auto-create cho namespace lab theo quyền phù hợp.
- Java dependency **org.apache.activemq:artemis-jms-client** tương thích với broker/JDK và namespace **javax.jms**. Với **jakarta.jms**, chọn client Jakarta phù hợp và đổi import đồng bộ.
- Biến môi trường **MQ_URL**, **MQ_USER**, **MQ_PASSWORD**; không hardcode credential.
- Kiểm tra queue đang trống trước mỗi loạt thử hoặc dùng **duplicate ID mới** cho lần lab mới, tránh lẫn dữ liệu cũ.

Ví dụ provision queue bằng Artemis **broker.xml**:

~~~xml
<!-- Fragment trong <addresses> của Artemis -->
<addresses>
    <address name="billing.payment.commands.v1">
        <anycast>
            <queue name="billing.payment.commands.v1" durable="true"/>
        </anycast>
    </address>
</addresses>
~~~

Đây là fragment cấu hình Artemis, không phải cú pháp của Classic.

### 5.2. Chương trình gửi và nhận

~~~java
import java.util.regex.Pattern;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisDuplicateIdLab {

    private static final String QUEUE =
        "billing.payment.commands.v1";

    private static final String DUPLICATE_ID_PROPERTY =
        "_AMQ_DUPL_ID";

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._:-]{1,80}");

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            usage();
            return;
        }

        String url = requiredEnv("MQ_URL");
        String user = requiredEnv("MQ_USER");
        String pass = requiredEnv("MQ_PASSWORD");
        ConnectionFactory factory =
            new ActiveMQConnectionFactory(url);

        switch (args[0]) {
            case "send":
                if (args.length != 3) {
                    usage();
                    return;
                }
                send(factory, user, pass, args[1], args[2]);
                break;
            case "receive":
                if (args.length != 1) {
                    usage();
                    return;
                }
                receive(factory, user, pass);
                break;
            default:
                usage();
        }
    }

    private static void send(
            ConnectionFactory factory,
            String user,
            String pass,
            String duplicateId,
            String paymentAttemptId) throws Exception {

        validateId(duplicateId);
        validateId(paymentAttemptId);

        try (JMSContext ctx = factory.createContext(
                user, pass, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue(QUEUE);
            String body =
                "{\"type\":\"ChargePayment\","
                + "\"paymentAttemptId\":\""
                + paymentAttemptId + "\"}";

            TextMessage message = ctx.createTextMessage(body);

            // Artemis broker duplicate detection header/property.
            message.setStringProperty(
                DUPLICATE_ID_PROPERTY, duplicateId);

            // ID nghiệp vụ được consumer sử dụng độc lập.
            message.setStringProperty(
                "paymentAttemptId", paymentAttemptId);

            ctx.createProducer()
               .setDeliveryMode(DeliveryMode.PERSISTENT)
               .send(queue, message);

            ctx.commit();

            // Đây KHÔNG phải bằng chứng có một message mới trong queue;
            // broker có thể đã bỏ qua một bản gửi trùng.
            System.out.println(
                "send/commit completed, duplicateId="
                + duplicateId + ", providerMessageId="
                + message.getJMSMessageID());
        }
    }

    private static void receive(
            ConnectionFactory factory,
            String user,
            String pass) throws Exception {

        try (JMSContext ctx = factory.createContext(
                user, pass, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue(QUEUE);
            JMSConsumer consumer = ctx.createConsumer(queue);
            try {
                Message message = consumer.receive(5000);

                if (message == null) {
                    System.out.println("No message available");
                    return;
                }

                System.out.println("paymentAttemptId="
                    + message.getStringProperty("paymentAttemptId"));
                System.out.println("duplicateId="
                    + message.getStringProperty(
                        DUPLICATE_ID_PROPERTY));
                System.out.println("JMSMessageID="
                    + message.getJMSMessageID());
                System.out.println("JMSRedelivered="
                    + message.getJMSRedelivered());

                // Lab: chưa thay đổi database/payment provider.
                // Production: commit transaction idempotent trước.
                ctx.commit();
                System.out.println("receive committed");
            } catch (Exception ex) {
                ctx.rollback();
                throw ex;
            } finally {
                consumer.close();
            }
        }
    }

    private static void validateId(String id) {
        if (!SAFE_ID.matcher(id).matches()) {
            throw new IllegalArgumentException(
                "Use 1..80 ASCII letters/digits/._:-");
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(
                "Missing env: " + key);
        }
        return value;
    }

    private static void usage() {
        System.out.println(
            "send <duplicateId> <paymentAttemptId> | receive");
    }
}
~~~

**Lưu ý:** đoạn trên chỉ gửi/nhận để quan sát việc chặn duplicate, **không thực hiện thanh toán thật**. Việc đặt **paymentAttemptId** trong property để đọc đơn giản không có nghĩa trường này tự kích hoạt duplicate detection; chỉ **_AMQ_DUPL_ID** đảm nhiệm phần việc ở ingress.

### 5.3. Bài thử A: cùng duplicate ID hai lần

Giả sử chạy chương trình với các argument sau:

~~~text
Lần 1: send evt-42 pay-741
Lần 2: send evt-42 pay-741
Sau đó: receive
Tiếp theo: receive
~~~

**Kỳ vọng** khi hai lần gửi đến **cùng address**, cache đã hoạt động và ID chưa bị quên:

- Cả hai lần gửi có thể hoàn tất ở client tùy cơ chế trả kết quả, nhưng **chỉ một bản** được route vào queue.
- Lần **receive** đầu nhận **pay-741** và commit.
- Lần **receive** thứ hai trả về **No message available** nếu không có message khác và không phát sinh redelivery.
- Kiểm tra management/console: **message added/enqueued** chỉ tăng tương ứng bản hợp lệ, không phải cứ một lời gọi send là một message mới.

Đừng dựa vào chuỗi **JMSMessageID** của lần retry làm tiêu chí broker đã chấp nhận bản đó. Tiêu chí là **số message được route/enqueue và nội dung consumer nhận**.

### 5.4. Bài thử B: cùng business ID nhưng duplicate ID khác

~~~text
Lần 1: send evt-43 pay-741
Lần 2: send evt-44 pay-741
Sau đó: receive
Tiếp theo: receive
~~~

**Kỳ vọng:** có thể nhận **hai message**, vì Artemis thấy hai duplicate ID khác nhau. Cả hai vẫn yêu cầu xử lý **paymentAttemptId=pay-741**, nên consumer phải có idempotency theo **pay-741** hoặc khóa nghiệp vụ tương đương để không trừ tiền hai lần.

Đây là phép thử quan trọng nhất để thấy **duplicate detection không thể thay thế chống lặp nghiệp vụ**.

### 5.5. Bài thử C: không có _AMQ_DUPL_ID

Sửa một bản copy lab trong môi trường thử nghiệm để **không set property _AMQ_DUPL_ID**, giữ cùng body/business ID, rồi gửi hai lần. Nếu không có cơ chế khác, cả hai có thể được nhận như hai message mới. **Đừng dùng bài thử này để tự suy ra rằng Artemis không có duplicate detection**; chính producer đã không cung cấp khóa cho nó.

## 6. Producer phải giữ duplicate ID qua retry và restart thế nào?

Trong production, producer thường không thể chỉ tạo một UUID trong RAM ngay trước send và hy vọng nó sống sót khi process crash. Một mô hình phổ biến là **transactional outbox**.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as Database + Outbox
    participant P as Outbox Publisher
    participant B as Artemis
    API->>DB: Transaction: lưu nghiệp vụ + eventId=evt-42
    DB-->>API: Commit
    P->>DB: Đọc outbox evt-42
    P->>B: Send _AMQ_DUPL_ID=evt-42
    B-->>P: Kết quả send/commit
    Note over P,B: Có thể mất mạng trước khi P ghi đã gửi
    P->>DB: Chưa đánh dấu published
    P->>DB: Đọc lại evt-42
    P->>B: Resend _AMQ_DUPL_ID=evt-42
    B->>B: Dedupe nếu ID còn trong cache
~~~

### 6.1. Một schema outbox tối giản

~~~sql
CREATE TABLE outbox_events (
    event_id       UUID PRIMARY KEY,
    destination    TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    payload_json   JSONB NOT NULL,
    published_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Khi tạo event:

1. Tạo **event_id** một lần, trong phạm vi của yêu cầu nghiệp vụ.
2. Trong **cùng transaction database**, cập nhật thực thể nghiệp vụ và ghi outbox row chứa **event_id**.
3. Publisher đọc bản ghi chưa published, set **_AMQ_DUPL_ID = event_id.toString()** và gửi.
4. Chỉ đánh dấu published khi đã có kết quả gửi/commit theo contract; nếu kết quả mơ hồ, **phát lại cùng event_id**.
5. Consumer phải vẫn idempotent vì cache có giới hạn và redelivery còn có thể xảy ra.

**Không xóa outbox row ngay sau một lần send không rõ kết quả.** Tùy yêu cầu vận hành, outbox còn là bằng chứng để retry, audit và đối soát khi broker downtime.

### 6.2. Mối quan hệ giữa duplicateId và businessId

| ID | Đề xuất tạo khi nào? | Phạm vi chống trùng |
|---|---|---|
| **_AMQ_DUPL_ID** | Khi định nghĩa một lần publish logic/outbox row | Bản gửi lại vào **cùng address** trong cửa sổ cache |
| **eventId** | Khi tạo sự kiện nghiệp vụ | Sự kiện logic xuyên broker, replay và consumer |
| **commandId** | Khi nhận một command logic | Một tác vụ yêu cầu thay đổi trạng thái |
| **paymentAttemptId** | Khi xác lập lần thử thanh toán | Một hiệu ứng thanh toán theo quy tắc nghiệp vụ |

Có thể dùng **eventId** làm duplicateId khi một outbox row tương ứng đúng một publish logic vào một address. Nếu một event phải phát vào **nhiều address**, việc dùng cùng eventId ở mỗi address có thể hợp lý vì cache tách theo address; nếu phát nhiều **message logic khác nhau vào cùng address**, phải cấp duplicate ID khác nhau.

## 7. Consumer idempotency: lớp bảo vệ không thể bỏ

Artemis duplicate detection chỉ có thể chặn **bản publish lặp tại đầu vào** trong điều kiện cache. Sau khi message đã vào queue, consumer vẫn có thể xử lý lại vì:

- Database đã commit nhưng **JMS ACK/commit bị mất** khi client crash.
- Consumer chủ động rollback vì một bước xử lý không thành công.
- Broker failover/connection reconnect làm kết quả commit chưa rõ.
- Một nghiệp vụ bị tạo thành **hai message khác nhau** với duplicate ID khác nhau.
- Message được replay thủ công từ DLQ hoặc nguồn dữ liệu lịch sử.

### 7.1. Cùng database: inbox + unique constraint

Một bảng inbox theo **consumer group và eventId**:

~~~sql
CREATE TABLE processed_events (
    consumer_name TEXT NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Luồng xử lý đúng khi side effect là **cập nhật trong cùng database**:

~~~text
BEGIN DB TRANSACTION
  INSERT processed_events(consumer_name, event_id)
  ON CONFLICT DO NOTHING

  Nếu INSERT tạo row mới:
      kiểm tra command/event và cập nhật nghiệp vụ
  Nếu row đã có:
      bỏ qua side effect; đọc kết quả cũ nếu cần
COMMIT DB TRANSACTION

ACK / COMMIT JMS
~~~

**Điều kiện bắt buộc:** việc ghi inbox và thay đổi nghiệp vụ phải cùng transaction database. Nếu phần nghiệp vụ rollback mà marker inbox đã commit, lần redelivery sau sẽ bị bỏ qua sai. Nếu có nhiều consumer cùng thấy eventId, unique constraint và transaction isolation xử lý xung đột; ứng dụng phải tính đến trạng thái transaction đang diễn ra.

**Phạm vi khóa:** mỗi consumer group độc lập có thể cần xử lý cùng một event, vì vậy **(consumer_name, event_id)** là ví dụ hợp lý. Với lệnh thanh toán, khóa **(tenant_id, payment_attempt_id)** ở bảng nghiệp vụ có thể quan trọng hơn, đặc biệt khi cùng một paymentAttemptId xuất hiện trong nhiều event/command.

### 7.2. Side effect nằm ngoài database

Nếu consumer gọi cổng thanh toán, gửi email hoặc kích hoạt hệ thống ngoài, một transaction SQL không thể tự rollback hiệu ứng bên thứ ba.

Ví dụ: hai command có cùng paymentAttemptId nhưng eventId khác nhau. Inbox theo eventId cho phép cả hai đi qua, trong khi **business uniqueness** phải từ chối khoản thu thứ hai.

Biện pháp:

1. Dùng **paymentAttemptId** làm idempotency key của payment provider nếu họ hỗ trợ.
2. Lưu trạng thái **PENDING / SUCCEEDED / FAILED / UNKNOWN** và kết quả provider trong hệ thống của mình.
3. Nếu mất mạng sau khi gọi provider, **query/reconcile** theo cùng key, không tạo attempt mới chỉ vì không thấy reply.
4. Chỉ ACK JMS sau khi kết quả cần thiết được lưu bền vững; nếu vẫn chưa rõ, giữ trạng thái xử lý phù hợp và tránh gọi charge một lần nữa với khóa mới.
5. Khi một duplicate tới, trả về hoặc dùng lại kết quả đã lưu thay vì thực hiện side effect thứ hai.

Duplicate detection ở broker **không thể nhìn thấy payment provider**; do đó nó không thể chứng minh “chỉ trừ tiền một lần”.

### 7.3. Dùng business ID ổn định, không phải JMSMessageID

~~~text
Message A:
   JMSMessageID = ID:broker-A
   duplicateId  = evt-43
   paymentId    = pay-741

Message B:
   JMSMessageID = ID:broker-B
   duplicateId  = evt-44
   paymentId    = pay-741

Consumer:
   paymentId pay-741 đã SUCCEEDED → không charge lại
~~~

Broker **đúng khi chấp nhận hai message** vì hai duplicate ID khác nhau. Hệ nghiệp vụ mới là nơi biết **hai message không được tạo hai khoản thu**.

## 8. Những cửa sổ lỗi cần thử, không chỉ đọc cấu hình

### 8.1. Broker đã nhận nhưng producer chưa biết

~~~text
t1: Publisher gửi evt-42 tới address billing.payment.commands.v1
t2: Artemis đã commit/enqueue bản đầu
t3: Network đứt trước khi publisher nhận kết quả
t4: Publisher retry evt-42 với _AMQ_DUPL_ID không đổi
t5: Artemis còn ID trong cache → suppress duplicate
t6: Consumer vẫn phải có idempotency khi nhận bản đầu
~~~

Đây là use case chính của duplicate detection. **Nếu retry lại bằng ID khác, cơ chế không thể giúp**.

### 8.2. Cache không còn nhớ ID khi replay

~~~text
t1: Message evt-42 được chấp nhận
t2: Có rất nhiều ID mới đi qua address
t3: evt-42 bị eviction khỏi duplicate cache
t4: Nhiều giờ sau publisher replay evt-42
t5: Artemis có thể chấp nhận bản replay
t6: Consumer inbox/eventId từ chối side effect trùng
~~~

Nếu hệ thống có **replay lịch sử kéo dài hàng ngày**, cache không nên được coi như kho lưu vĩnh viễn cho event IDs. Hãy xác định retention của inbox theo cửa sổ retry/replay nghiệp vụ, chứ không chỉ theo kích thước cache broker.

### 8.3. Crash sau DB commit, trước JMS ACK

~~~text
t1: Consumer nhận evt-42
t2: DB commit kết quả và processed_events(evt-42)
t3: Consumer crash, JMS ACK chưa hoàn tất
t4: Broker redeliver evt-42
t5: Consumer thấy processed_events đã có
t6: Không cập nhật nghiệp vụ lần hai; ACK JMS
~~~

Lần redelivery này **không đi lại qua cơ chế duplicate detection tại ingress**. Nó được broker phát lại từ message đã tồn tại; phải có inbox.

### 8.4. Resend sau failover

Sau failover, broker mới có thể hoặc không thể nhận diện duplicate ID cũ tùy **trạng thái cache được chuyển/khôi phục**. Kiểm thử:

- Send bản đầu rồi xác nhận queue đang có message.
- Làm failover theo topology dự kiến.
- Send lại **cùng _AMQ_DUPL_ID**.
- Quan sát enqueue count, duplicate log/metric và số message nhận.
- Lặp bài thử khi message được publish trong transaction và khi producer gặp lỗi giữa send/commit.

**Không dùng một lần failover thành công làm bằng chứng toàn bộ thứ tự crash/restart đều an toàn.** Cần test nhiều điểm cắt: trước commit, sau commit nhưng chưa nhận phản hồi, trong reconnect.

## 9. Bảng lỗi cấu hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Phép kiểm chứng |
|---|---|---|
| Gửi cùng body hai lần đều vào queue | Không gắn **_AMQ_DUPL_ID**, hoặc ID khác nhau | Đọc message properties của mỗi lần send |
| Gắn cùng ID nhưng broker vẫn nhận hai bản | Khác address, cache eviction, restart/failover không có state, mapping protocol sai | Xác minh address thực tế, cấu hình cache và timeline |
| Producer báo send thành công nhưng queue không tăng | Có thể bị duplicate suppression, cũng có thể do routing/transaction khác | Quan sát server log, enqueue counter, address binding |
| Message khác nghiệp vụ bị bỏ qua | Producer tái sử dụng cùng duplicate ID | Kiểm tra thuật toán cấp ID và outbox rows |
| Retry sau restart tạo bản mới | Cache không persist/không được khôi phục hoặc ID đã bị quên | Test trước/sau restart, inspect cấu hình broker |
| Một event tới nhiều subscription | Đây là fan-out hợp lệ, không phải duplicate ingress | Xem routing MULTICAST và subscription queues |
| Consumer trừ tiền hai lần dù ingress chỉ có một bản | Redelivery hoặc side effect chưa idempotent | Kiểm tra ACK/DB commit và business key |
| Nhiều consumer group đều xử lý cùng eventId | Hợp lệ nếu mỗi group có trách nhiệm riêng | Đặt khóa inbox theo consumer group |
| Duplicate publish không xuất hiện trong DLQ | Duplicate bị loại ở ingress, chưa tới consumer | Đọc duplicate detection diagnostics, không tìm trong DLQ |
| Giảm cache size làm phát sinh bản lặp ở giờ cao điểm | Cửa sổ giữ ID quá ngắn so với retry/replay | Đo throughput unique IDs và retry horizon |

### 9.1. Quan sát tối thiểu

Nên có các chỉ số và trường log sau:

- Producer: **eventId/commandId**, _AMQ_DUPL_ID, address/destination, attempt number, send/commit result.
- Broker: duplicate detection logs/management nếu phiên bản cung cấp; queue enqueued, delivering, acknowledged, scheduled, DLQ.
- Consumer: **JMSMessageID**, eventId/commandId, paymentAttemptId, redelivered/delivery count, inbox hit/miss, kết quả nghiệp vụ.
- Hạ tầng: broker restart, failover, cache configuration change, disk/journal health, topology và phiên bản.

**Không suy luận duplicate count = số lần producer retry trong mọi trường hợp.** Một số lần retry có thể không đến broker, bị lỗi kết nối, khác ID hoặc vượt cửa sổ cache. Một số message có thể bị bỏ vì ID vô tình trùng dù chúng là nghiệp vụ khác nhau.

### 9.2. Không dùng queue count làm phép đo duy nhất

Queue count không tăng có thể do:

1. Broker chặn duplicate.
2. Message bị route sang address/queue khác.
3. Producer chưa commit transaction.
4. TTL/expiry hoặc policy khác đã tác động.
5. Consumer đã nhận và ACK rất nhanh.

Khi kiểm chứng duplicate detection, **dừng consumer**, dùng queue lab sạch, đo **enqueue/routed counter** và message IDs. Kết hợp server log với property **_AMQ_DUPL_ID** và cấu hình routing để tách các nguyên nhân.

## 10. Quy tắc thiết kế và cấu hình production

Một pipeline tin cậy nên có **hai lớp bảo vệ bổ sung**:

~~~mermaid
flowchart TD
    A["Database transaction + Outbox<br/>eventId cố định"] --> B["Publisher: gửi _AMQ_DUPL_ID = eventId"]
    B --> C["Artemis duplicate ID cache<br/>theo address"]
    C --> D["Queue / subscription"]
    D --> E["Consumer: inbox / business unique key"]
    E --> F["DB transaction / external idempotency"]
    F --> G["JMS ACK / commit"]
~~~

**Lớp broker:** giảm số message được enqueue do retry của publisher, đặc biệt trong cửa sổ gửi mơ hồ.

**Lớp consumer/business:** bảo vệ hiệu ứng trước redelivery, cache eviction, cross-address, duplicated business intent và side effect ngoài broker.

### 10.1. Checklist trước go-live

- [ ] Mỗi lần publish logic có **duplicate ID ổn định**, đủ duy nhất cho address và producer pool.
- [ ] Producer gắn đúng thuộc tính **_AMQ_DUPL_ID**; đã test đường JMS/Core/AMQP/bridge thực tế, không suy luận mapping.
- [ ] Outbox hoặc nguồn lưu trạng thái đảm bảo retry **giữ nguyên duplicate ID** sau process crash.
- [ ] Đã xác định phạm vi address, bao gồm ANYCAST/MULTICAST, cluster và bridge.
- [ ] Đã đo unique IDs/giây, burst và **retry horizon**; cấu hình **id-cache-size** đủ phù hợp với nguồn lực.
- [ ] Đã quyết định **persist-id-cache** theo yêu cầu restart/HA, có bài test recovery.
- [ ] Không dùng một duplicate ID cho hai message nghiệp vụ khác nhau vào cùng address.
- [ ] Batch JMS transaction được kiểm thử khi có khả năng một message mang ID trùng; không giả định ảnh hưởng chỉ cục bộ từng message.
- [ ] Consumer có **eventId/commandId** và inbox/unique constraint phù hợp; transaction DB đảm bảo marker và side effect cùng commit.
- [ ] Khi gọi API ngoài, dùng idempotency key, trạng thái đối soát và xử lý UNKNOWN.
- [ ] Phân biệt **duplicate detection ingress**, **consumer redelivery**, **DLQ** và **expiry** trong log/monitoring.
- [ ] Đã thực hành retry cùng ID, retry khác ID, eviction, restart, failover và consumer crash trước ACK.
- [ ] Có cảnh báo khi gửi nhiều ID trùng bất thường; không ẩn producer bug sau cơ chế suppression.

## 11. Bài tập cuối bài: chứng minh giới hạn

### Bài A — Cùng duplicate ID qua hai send

Từ chương trình ở mục 5, gửi **evt-201/pay-801** hai lần vào cùng queue; sau đó nhận tới khi trống.

**Kết quả mong đợi:** một message được route nếu ID còn trong cache. Phải giải thích vì sao hai lời gọi send/commit thành công ở phía client không nhất thiết tạo hai message.

### Bài B — Hai duplicate ID, cùng paymentAttemptId

Gửi **evt-202/pay-801** và **evt-203/pay-801**. Đọc cả hai message.

**Kết quả mong đợi:** Artemis không có lý do coi hai duplicate ID là một, trong khi nghiệp vụ phải ngăn charge **pay-801** hai lần. Viết unique constraint hoặc idempotency rule giải quyết được trường hợp này.

### Bài C — Cache nhỏ và eviction

Trong **broker lab riêng**, giảm **id-cache-size** xuống giá trị rất nhỏ phù hợp thí nghiệm; gửi đủ nhiều ID mới để ID đầu bị đẩy ra. Gửi lại ID cũ, đo số message được enqueue. Hoàn nguyên cấu hình sau bài thử.

**Kết quả mong đợi:** duplicate detection không duy trì một tập ID vĩnh viễn. Nêu rõ số ID và thứ tự gửi thực tế, không khẳng định thuật toán eviction ngoài điều đo được.

### Bài D — Restart và persisted cache

Chạy hai lượt trong sandbox: một lượt cache được persist, một lượt không persist, có restart broker giữa send đầu và resend. Ghi nhận cấu hình, log khôi phục và số lần enqueue.

**Kết quả mong đợi:** chỉ ra sự khác biệt giữa **message persistence** và **duplicate ID cache persistence**, đồng thời giải thích giới hạn khi HA chuyển node.

### Bài E — Consumer xử lý xong DB nhưng mất ACK

Gửi một message hợp lệ, consumer ghi inbox + thay đổi DB trong một transaction, rồi crash trước commit JMS. Cho broker redeliver.

**Kết quả mong đợi:** message có thể được giao hơn một lần nhưng **chỉ một hiệu ứng DB**. Artemis duplicate detection không tham gia vào lần redelivery này.

### Bài F — Lỗi reuse ID

Cố tình gắn **_AMQ_DUPL_ID giống nhau** cho hai command **thực sự khác nhau** vào một address, khi cache còn ID.

**Kết quả mong đợi:** command thứ hai có thể bị broker chặn như duplicate dù nội dung khác. Giải thích vì sao **ID collision là nguy cơ mất message hợp lệ**, không chỉ nguy cơ tăng duplicate.

---

**Kết luận:** Duplicate detection của **ActiveMQ Artemis** là lớp phòng vệ hiệu quả trước **producer resend** khi message mang **_AMQ_DUPL_ID** ổn định và ID đó còn được cache của **address** ghi nhớ. Cache có giới hạn, phụ thuộc cấu hình persistence/topology và không giải quyết **consumer redelivery** hay **hai message khác ID nhưng cùng ý nghĩa nghiệp vụ**. Do đó giải pháp thực tế là **outbox với ID ổn định → Artemis duplicate detection → consumer inbox/business idempotency → ACK/commit có kiểm soát**. Đây mới là thiết kế có thể giải thích và kiểm chứng về độ tin cậy khi dùng Java/JMS với Artemis.
