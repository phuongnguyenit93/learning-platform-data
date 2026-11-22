# Phân biệt retry tại client, redelivery từ broker và gửi lại thủ công

> **Chương:** Gửi lại và DLQ  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic, ActiveMQ Artemis và Java/JMS.  
> **Phạm vi chính:** Một message thất bại có thể được thử lại **ngay trong ứng dụng**, được **broker giao lại** hoặc được **operator phát lại như một message mới**. Ba cơ chế này có điểm bắt đầu, định danh, bộ đếm và trách nhiệm vận hành khác nhau.

## 1. Ba hành động nhìn giống nhau nhưng có hệ quả khác nhau

Giả sử consumer nhận lệnh `PrepareShipment` với `eventId = E-100` và gọi hệ thống kho. Lần gọi đầu bị HTTP 503. Có ba cách xử lý:

1. **Retry tại client (local retry):** Giữ nguyên message đang được giao cho consumer; gọi lại API kho một vài lần trước khi quyết định `commit()` hoặc `rollback()` JMS.
2. **Broker redelivery:** Kết thúc lần xử lý thất bại bằng `rollback()`, `Session.recover()` khi phù hợp hoặc mất kết nối khi chưa xác nhận; message đủ điều kiện được broker/client cấp lại cho một consumer theo chính sách redelivery.
3. **Gửi lại thủ công (manual replay):** Message đã vào DLQ hoặc nằm trong nguồn lưu trữ khác, người vận hành điều tra nguyên nhân rồi **chủ động gửi lại** vào destination xử lý. Thường đây là một lượt publish mới, tạo `JMSMessageID` mới.

~~~mermaid
flowchart TD
    A[(Main queue)] --> B[Consumer nhận E-100]
    B --> C{Xử lý thành công?}
    C -->|Có| D[Commit / ACK]
    C -->|Lỗi tạm thời| E{Local retry còn ngân sách?}
    E -->|Có| F[Gọi lại nghiệp vụ trong cùng delivery]
    F --> C
    E -->|Hết| G[Rollback / không ACK]
    G --> H[Redelivery theo chính sách broker/client]
    H --> I{Đã vượt giới hạn?}
    I -->|Chưa| A
    I -->|Đủ điều kiện dead-letter| J[(DLQ)]
    J --> K[Điều tra và sửa nguyên nhân]
    K --> L[Manual replay có kiểm soát]
    L --> A
~~~

**Mục tiêu của bài:** Sau khi quan sát ba trường hợp, phải trả lời chính xác *ai quyết định thử lại*, *message có được giao lại hay chỉ còn ở consumer*, *khi nào delivery count thay đổi*, *cái gì được ACK/commit* và *làm sao tránh side effect trùng*.

### Ma trận nhận diện

| Tiêu chí | Client retry bên trong handler | Broker redelivery | Manual replay |
|---|---|---|---|
| Ai quyết định? | Code của ứng dụng đang xử lý message | Chu kỳ giao/không ACK/rollback cùng chính sách broker/provider | Operator, runbook hoặc công cụ replay được kiểm soát |
| Có một delivery JMS mới? | **Không** giữa các local attempt | **Có thể có** delivery mới của message chưa được ACK | **Có**, thường là message mới được publish |
| `JMSMessageID` | Giữ nguyên trong cùng delivery | Thường là cùng message broker đang lưu | Thường **đổi** do publish lại thành message mới |
| `eventId` nghiệp vụ | Phải giữ nguyên | Phải giữ nguyên | Nên **giữ nguyên** nếu vẫn là cùng sự kiện/command |
| `JMSXDeliveryCount` | Không tăng chỉ vì retry function nội bộ | Có thể tăng theo những lần broker/provider giao lại | Bắt đầu theo đời message publish mới; không phải bộ đếm lịch sử |
| Delay/backoff | Code client điều khiển | Chính sách broker/provider điều khiển | Quy trình vận hành, rate limit và thời điểm replay |
| Khi lỗi kéo dài | Có nguy cơ giữ worker/in-flight quá lâu | Có thể đưa message sang DLQ theo max attempts | Có thể tạo vòng lặp `DLQ → main → DLQ` nếu replay sai |
| Ranh giới ACK | Sau local attempt thành công; hoặc rollback khi cạn ngân sách | ACK/commit ở lần giao thành công | Sau khi publish lại thành công và xử lý an toàn bản gốc trong DLQ |

**Lưu ý thuật ngữ:** “Retry tại client” còn có nghĩa thứ hai là **producer gửi lại khi `send()/commit()` trả lỗi hoặc timeout**. Đó là *producer-side retry*, khác với consumer-local retry bên trong handler. Phần 3 phân biệt cả hai để không bỏ sót rủi ro gửi trùng.

## 2. State machine của một message sau lần xử lý thất bại

Một message có thể ở các trạng thái logic:

~~~text
AVAILABLE  ── delivery ──> IN_FLIGHT
                              │
                 ┌────────────┼───────────────┐
                 │            │               │
           ACK / commit    rollback       mất kết nối
                 │            │               │
                 ▼            └───────┬───────┘
               DONE                   │
                                      ▼
                         WAITING_FOR_REDELIVERY
                                      │
                     ┌────────────────┴───────────────┐
                     ▼                                ▼
            AVAILABLE (lần tiếp)             DLQ khi đủ điều kiện
                                                      │
                                              điều tra + replay
                                                      │
                                                      ▼
                                            NEW MESSAGE vào main
~~~

Đây là **mô hình khái niệm**, không phải tập tên trạng thái nội bộ cố định của Artemis. Message có thể đã được client prefetch/buffer, bị delivery cancel, expire hoặc đi qua chính sách đặc thù của provider. Điều quan trọng là: **mỗi lần ứng dụng gọi lại API kho không mặc nhiên là một lần broker redelivery**, còn **manual replay không phải rollback của cùng JMS delivery**.

### Ví dụ đếm cho ba cơ chế

Giả sử `eventId=E-100`, `max-delivery-attempts=3` trên Artemis, không có consumer khác, không có expiry:

| Thao tác | Gọi API nghiệp vụ | Lần giao broker nhìn thấy | `JMSRedelivered` / `JMSXDeliveryCount` quan sát |
|---|---:|---:|---|
| Nhận lần đầu, handler local retry 3 lần rồi thành công | 3 | 1 | Trên message đang giữ, thông tin giao hàng vẫn là delivery đầu |
| Nhận lần đầu, handler lỗi và rollback; nhận lại và rollback tiếp | 2 (mỗi lần giao gọi một lần) | 2 | Delivery tiếp theo thường có `JMSRedelivered=true`, delivery count tăng |
| Message độc, rollback đến giới hạn; operator replay từ DLQ | Có thể đã thử nhiều lần | Những lần đầu kết thúc ở DLQ; một message mới khi replay | Message replay thường có `JMSMessageID` mới và delivery count bắt đầu lại |

Các con số là hướng dẫn quan sát, **không thay cho cấu hình/thực nghiệm**: timing của redelivery, client prefetch, failover, acknowledgement mode và cách tính `max-delivery-attempts` phải đối chiếu đúng Artemis/Classic và version. Bộ đếm broker không đo số HTTP request do handler tự retry.

## 3. Retry tại client: consumer-local và producer-side là hai đường lỗi

### 3.1. Consumer-local retry khi giữ message chưa ACK

Trong một **transacted JMS session**:

~~~java
Message message = consumer.receive(5000);
if (message == null) {
    return;
}

for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        callWarehouseApi(message); // Cần timeout và idempotency key.
        context.commit();         // JMS ACK khi xử lý thành công.
        return;
    } catch (TransientWarehouseException failure) {
        if (attempt == 3) {
            context.rollback();   // Nhường lần thử tiếp cho redelivery.
            return;
        }
        Thread.sleep(200L * attempt);
    }
}
~~~

Đoạn trên minh họa **cơ chế**, chưa là chương trình standalone: `TransientWarehouseException` và `callWarehouseApi` là các thành phần nghiệp vụ giả định.

Ba vòng gọi `callWarehouseApi()` diễn ra **trong cùng một lần broker giao message**. Nếu cả ba lần thất bại, `rollback()` khiến message đủ điều kiện redelivery. Giữ message quá lâu để retry khiến worker không nhận thêm job, tăng thời gian chờ và có thể kéo dài quá deadline shutdown; vì vậy phải đặt ngân sách: số lần local attempt, timeout mỗi request, backoff và tổng thời gian chiếm consumer.

**Lỗi nên retry local:** HTTP 503 ngắn, mất kết nối tạm thời, DB deadlock có khả năng hết sau một khoảng ngắn. **Lỗi không nên retry local:** schema hỏng, field thiếu bắt buộc, quyền truy cập vĩnh viễn không hợp lệ, trạng thái nghiệp vụ không thể chuyển đổi. Lỗi vĩnh viễn cần hướng xử lý riêng, tránh retry nóng.

### 3.2. Producer-side retry sau lỗi gửi có kết quả không chắc chắn

Xét hai bước:

~~~text
1. Producer gửi eventId=E-100
2. Broker đã lưu message và trả xác nhận
3. Kết nối mất đúng lúc client chờ kết quả
4. Producer nhìn thấy timeout
~~~

Producer **không biết chắc** lần gửi đã commit hay chưa. Nếu gửi lại một message mới với `eventId=E-101`, consumer sẽ không nhận ra E-100 và E-101 là cùng yêu cầu. Hướng an toàn:

- Gắn **một eventId cố định** với sự kiện nghiệp vụ, lưu trong outbox hoặc dữ liệu gửi chờ.
- Khi retry send, **giữ nguyên eventId**; coi việc publish trùng là tình huống có thể xảy ra.
- Consumer thực thi idempotency dựa trên `(consumerName, eventId)` hoặc khóa nghiệp vụ tương ứng.
- Nếu cần đảm bảo lưu DB và phát message đi đôi, dùng **transactional outbox**; đừng coi database commit và JMS commit trên hai hệ thống tự động nguyên tử.

Producer retry **có thể tạo hai message broker khác nhau**, cả hai cùng `eventId`, vì nó là *resend*, không phải redelivery của một message đang tồn. Khi phân tích log hãy đối chiếu cả **JMSMessageID** và **eventId**, tránh nhầm “message mới do retry producer” với “message cũ do broker giao lại”.

### 3.3. Local retry và broker redelivery có thể nhân số lần gọi thực tế

Nếu handler retry local **3 lần cho mỗi delivery**, còn broker cho tối đa **3 deliveries**, một message độc có thể khiến downstream bị gọi khoảng **9 lần** trước khi đi DLQ. Đây chỉ là phép tính minh họa với các giới hạn cụ thể; nó không phụ thuộc số message ban đầu.

Do đó đừng cấu hình đồng thời `localAttempts=10`, `max-delivery-attempts=20` và không có delay: số request downstream có thể bùng nổ trong lúc downstream đang hỏng. Hãy quản lý **retry budget** theo thời gian, rate limit/circuit breaker và thời hạn của công việc.

## 4. Broker redelivery: trigger, delay, delivery count và DLQ

### 4.1. Khi nào bắt đầu một chu kỳ redelivery?

Các nguyên nhân thường gặp với JMS:

1. Consumer trong transacted session gọi `rollback()`.
2. Session/connection đóng hoặc process chết khi message chưa được xác nhận.
3. Một phiên nhận dùng acknowledgment mode phù hợp gọi `Session.recover()` để bắt đầu giao lại các message chưa ACK.
4. Broker failover hoặc client reconnect dẫn đến những delivery chưa xác nhận được giao lại.

Phản ứng phụ thuộc chế độ ACK. Ví dụ, với synchronous consumer dùng `AUTO_ACKNOWLEDGE`, message có thể đã được ACK khi `receive()` trả về thành công, nên `throw exception` sau đó **không tự làm broker giao lại**. Để minh họa chính xác, phần lab dùng **`JMSContext.SESSION_TRANSACTED`** và gọi `commit()/rollback()` rõ ràng.

**`JMSRedelivered`** là tín hiệu provider đánh dấu message có thể đã giao trước; **`JMSXDeliveryCount`** là thuộc tính JMSX chỉ số lần delivery được provider báo. Dùng hai tín hiệu để chẩn đoán, không dùng như khóa idempotency hay như bằng chứng đã ghi DB thành công. Khi manual replay tạo message mới, chúng không theo dõi lịch sử của event nghiệp vụ xuyên các lần publish.

### 4.2. Broker Artemis và client Classic khác nơi đặt policy

**Artemis** cung cấp các chính sách theo address trong `broker.xml`:

~~~xml
<address-setting match="lab.retry.orders">
    <dead-letter-address>lab.retry.dlq</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
</address-setting>
~~~

Đây là cơ chế **broker-side** thường dùng trong Artemis: sau những lần giao thất bại đủ điều kiện, broker trì hoãn redelivery hoặc chuyển vào dead-letter address theo cấu hình. Ý nghĩa chính xác của bộ đếm khi consumer disconnect, timeout, failover còn phụ thuộc phiên bản và hành vi client; quan sát trên broker thật.

**ActiveMQ Classic** có nét khác: client ActiveMQ có `RedeliveryPolicy`, cấu hình `maximumRedeliveries`, delay/backoff. Khi client xác định số lần giao lại đã vượt chính sách, nó có thể gửi **poison ACK** để broker áp dụng dead-letter strategy, thường vào `ActiveMQ.DLQ` nếu chưa đổi policy. Ví dụ bằng Java với ActiveMQ Classic client tương ứng:

~~~java
// Minh họa ActiveMQ Classic client; không dùng với Artemis JMS factory.
ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

RedeliveryPolicy policy = factory.getRedeliveryPolicy();
policy.setInitialRedeliveryDelay(1000);
policy.setMaximumRedeliveries(3);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
~~~

Đoạn trên cần import `org.apache.activemq.ActiveMQConnectionFactory` và `org.apache.activemq.RedeliveryPolicy`, tương thích đúng nhánh client Classic. Nó **không phải** cấu hình Artemis `broker.xml` và không tự đặt DLQ của Artemis.

| Điểm so sánh | ActiveMQ Artemis | ActiveMQ Classic |
|---|---|---|
| Chính sách retry/redelivery phổ biến | `address-settings` của broker: `redelivery-delay`, `max-delivery-attempts` | `RedeliveryPolicy` của ActiveMQ client và chính sách destination/broker |
| Cơ chế đưa đến DLQ thường gặp | Broker đưa message sang `dead-letter-address` đã cấu hình | Poison ACK + broker dead-letter strategy |
| Tên DLQ | Do người quản trị cấu hình; nhiều template có address/queue `DLQ` | Thường `ActiveMQ.DLQ` theo default policy, có thể dùng individual DLQ |
| Công cụ xác minh | Queue count, delivering, delivery count, DLQ address/queue | Redelivery policy client, broker advisory/JMX, DLQ strategy |
| Điều phải tránh | Giả định sửa policy client Classic sẽ tác động lên Artemis | Giả định `max-delivery-attempts` của Artemis là setting Classic |

Hai dòng broker đều cần xử lý duplicate, poison message và kiểm soát backoff. **“Redelivery từ broker” trong sơ đồ là hành vi logic hệ thống tiếp tục giao một message chưa ACK; thời điểm, quyết định và protocol handshakes có thể do cả broker lẫn client provider phối hợp**, đặc biệt trên Classic.

### 4.3. Không đồng nhất DLQ với “message đã hết giá trị nghiệp vụ”

DLQ là nơi lưu các message **đã thất bại theo chính sách xử lý**, không phải nơi chứa mọi message “sai dữ liệu”. Một message có thể vào DLQ vì:

- Consumer luôn ném lỗi schema.
- API downstream hỏng lâu hơn retry budget.
- Consumer không có đủ quyền hoặc dùng sai version schema.
- Một lỗi code tạm thời biến thành poison message.

Có message chỉ cần sửa code và replay; có message cần sửa payload hoặc được từ chối vĩnh viễn theo nghiệp vụ. Operator phải phân loại trước khi chuyển message ra khỏi DLQ.

## 5. Cấu hình Artemis cho một lab quan sát ba cơ chế

Mục tiêu là có **queue chính** và **queue DLQ riêng**, đủ để xem delivery count và lần publish mới khi replay.

Giả sử Artemis instance đã chạy trên `tcp://127.0.0.1:61616` với Core acceptor, account có quyền `send`/`consume`. Trong `ARTEMIS_INSTANCE/etc/broker.xml`, thêm nội dung sau **bên trong `<addresses>` hiện hữu**, nếu chưa có tên trùng:

~~~xml
<address name="lab.retry.orders">
    <anycast>
        <queue name="lab.retry.orders">
            <durable>true</durable>
        </queue>
    </anycast>
</address>

<address name="lab.retry.dlq">
    <anycast>
        <queue name="lab.retry.dlq">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Trong `<address-settings>` hiện hữu, đặt:

~~~xml
<address-setting match="lab.retry.orders">
    <dead-letter-address>lab.retry.dlq</dead-letter-address>
    <max-delivery-attempts>3</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
</address-setting>
~~~

Giải thích:

- `lab.retry.orders` là queue chính nhận command qua anycast.
- `lab.retry.dlq` là address dead-letter có queue cùng tên để **giữ message đã được chuyển sang DLQ**.
- `redelivery-delay=1000` là độ trễ cơ bản một giây giữa các lần giao lại theo chính sách này, không phải thời gian consumer tự sleep.
- `max-delivery-attempts=3` giới hạn số lần giao thất bại theo cơ chế của Artemis. Khi đủ điều kiện dead-letter, message được đưa tới `lab.retry.dlq` thay vì tiếp tục thử vô hạn.
- Không có chuyện mọi queue trên broker đều dùng chính sách này: `match` áp dụng cho address được chỉ định. Nếu có các `address-setting` khớp cụ thể hơn, phải kiểm tra thứ tự và kết quả áp dụng.
- Không tự gắn `dead-letter-address=lab.retry.dlq` cho **chính DLQ** theo chính policy này, tránh vòng lặp khi consumer DLQ gặp lỗi.

Có thể thêm quyền cho role `retry-lab` trong section `<security-settings>` đang có:

~~~xml
<security-setting match="lab.retry.#">
    <permission type="send" roles="retry-lab"/>
    <permission type="consume" roles="retry-lab"/>
</security-setting>
~~~

Trong production nên tách quyền consumer chính, operator xem DLQ và operator replay, không cấp quyền publish lại hàng loạt cho mọi consumer. **Không thay toàn bộ file `broker.xml` bằng các đoạn trên**, cũng không tạo section root trùng; khởi động lại instance trong lab và xác nhận hai queue cùng chính sách bằng console/JMX/management.

### 5.1. Nếu DLQ chưa có queue

Chỉ khai báo `<dead-letter-address>` **chưa đủ** để một operator đọc message từ queue. Artemis có khái niệm **address** và **queue**; hãy bảo đảm address DLQ có ít nhất một queue phù hợp như XML trên hoặc cấu hình auto-create thích hợp. Nếu broker dùng wildcard DLQ/auto-create khác thì phải đối chiếu cấu hình thực tế. Nếu sai, có thể không có nơi lưu message như kỳ vọng.

### 5.2. Vì sao cần tách queue DLQ riêng trong lab?

Nhiều template Artemis cung cấp sẵn `DLQ` chung, nhưng dùng `lab.retry.dlq` giúp quan sát đúng một workflow, không làm lẫn message lỗi của những ứng dụng khác. Cấu hình DLQ tập trung và DLQ riêng từng address đều có trường hợp sử dụng; chọn theo yêu cầu phân quyền, monitoring, retention và replay.

## 6. Java/JMS: thực nghiệm có thể phân biệt được bằng log

### 6.1. Điều kiện biên dịch và chạy

Ví dụ dùng Java 17 và Jakarta Messaging (`jakarta.jms.*`) qua client Artemis Jakarta. Trong project Maven thực hành, chọn một phiên bản client tương thích broker/JDK:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.33.0</artemis.version>
</properties>
<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

`2.33.0` là phiên bản minh họa; cần xác nhận client và broker/JDK thực tế tương thích. Nếu dùng ActiveMQ Classic với `javax.jms.*` hoặc `jakarta.jms.*` ở nhánh khác, thay dependency/package và chính sách broker tương ứng. Không ghép client Classic trực tiếp vào mã Artemis mà không thay ConnectionFactory.

Đặt biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` trong cấu hình chạy; không hardcode secret.

### 6.2. Chương trình minh họa từng mode

Lớp `RetryModesLab` nhận các mode:

- `send-local`: gửi message mà một consumer sẽ retry **ba lần bên trong một delivery**.
- `client`: xử lý message bằng local retry, thành công sau hai lần lỗi giả lập rồi JMS commit.
- `send-poison`: gửi message luôn thất bại khi xử lý.
- `broker`: nhận message poison, rollback để quan sát broker redelivery và chuyển DLQ.
- `replay <eventId>`: sau khi **đã xác nhận nguyên nhân được sửa**, lấy đúng message từ DLQ và phát **một message mới** tới queue chính trong **một JMS transaction**.
- `consume-ok`: nhận message đã replay, xác nhận xử lý và commit.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;

public final class RetryModesLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String MAIN_QUEUE = "lab.retry.orders";
    private static final String DLQ = "lab.retry.dlq";

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
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
                case "send-local" -> send(ctx, "local");
                case "send-poison" -> send(ctx, "poison");
                case "client" -> localRetry(ctx);
                case "broker" -> brokerRedelivery(ctx);
                case "replay" -> {
                    if (args.length != 2) {
                        throw new IllegalArgumentException(
                            "Cần eventId: replay <eventId>");
                    }
                    replayOne(ctx, args[1]);
                }
                case "consume-ok" -> consumeFixed(ctx);
                default -> usage();
            }
        }
    }

    private static Queue mainQueue(JMSContext ctx) {
        return ctx.createQueue(MAIN_QUEUE);
    }

    private static void send(JMSContext ctx, String scenario)
            throws JMSException {
        String eventId = "E-" + UUID.randomUUID();

        TextMessage message = ctx.createTextMessage(
            "{\"eventId\":\"" + eventId + "\"," +
            "\"operation\":\"PrepareShipment\"}");
        message.setStringProperty("eventId", eventId);
        message.setStringProperty("scenario", scenario);
        message.setIntProperty("manualReplayCount", 0);

        try {
            ctx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(mainQueue(ctx), message);
            ctx.commit();
            System.out.println("PUBLISHED eventId=" + eventId +
                " JMSMessageID=" + message.getJMSMessageID());
        } catch (Exception failure) {
            ctx.rollback();
            throw failure;
        }
    }

    // Nhiều local attempts, nhưng chỉ một lần nhận từ broker.
    private static void localRetry(JMSContext ctx) throws Exception {
        JMSConsumer consumer = ctx.createConsumer(mainQueue(ctx));
        try {
            Message message = consumer.receive(5000);
            if (message == null) {
                System.out.println("Queue rỗng.");
                return;
            }
            if (!"local".equals(
                    message.getStringProperty("scenario"))) {
                ctx.rollback();
                throw new IllegalStateException(
                    "Hãy dùng send-local trước khi chạy client.");
            }

            printDelivery("FIRST_DELIVERY", message);

            for (int attempt = 1; attempt <= 3; attempt++) {
                try {
                    // Giả lập API tạm lỗi hai lần, thành công lần ba.
                    if (attempt < 3) {
                        throw new IllegalStateException("HTTP 503 (demo)");
                    }

                    System.out.println(
                        "BUSINESS_OK localAttempt=" + attempt);
                    ctx.commit(); // JMS ACK chỉ một lần sau thành công.
                    return;
                } catch (IllegalStateException transientFailure) {
                    System.out.println(
                        "LOCAL_RETRY attempt=" + attempt +
                        " error=" + transientFailure.getMessage());
                    if (attempt == 3) {
                        ctx.rollback();
                        return;
                    }
                    Thread.sleep(200L * attempt);
                }
            }
        } finally {
            consumer.close();
        }
    }

    // Mỗi rollback tạo điều kiện cho một delivery khác của cùng message.
    private static void brokerRedelivery(JMSContext ctx)
            throws JMSException {
        JMSConsumer consumer = ctx.createConsumer(mainQueue(ctx));
        try {
            for (int observed = 0; observed < 8; observed++) {
                Message message = consumer.receive(3500);
                if (message == null) {
                    System.out.println(
                        "Không còn message chính trong thời gian chờ.");
                    break;
                }

                printDelivery("BROKER_DELIVERY", message);

                if (!"poison".equals(
                        message.getStringProperty("scenario"))) {
                    ctx.rollback();
                    throw new IllegalStateException(
                        "Hãy dùng send-poison trước khi chạy broker.");
                }

                // Lỗi không hồi phục để kiểm tra DLQ của broker.
                System.out.println(
                    "SIMULATED_FAILURE: rollback, không local retry");
                ctx.rollback();
            }
        } finally {
            consumer.close();
        }
    }

    private static void replayOne(JMSContext ctx, String eventId)
            throws JMSException {
        // Giới hạn ký tự trước khi đưa vào selector JMS.
        if (!eventId.matches("[A-Za-z0-9_-]{1,100}")) {
            throw new IllegalArgumentException("eventId không hợp lệ");
        }

        Queue dlq = ctx.createQueue(DLQ);
        Queue main = mainQueue(ctx);

        JMSConsumer consumer = ctx.createConsumer(
            dlq, "eventId = '" + eventId + "'");

        try {
            Message old = consumer.receive(5000);
            if (old == null) {
                System.out.println("Không tìm thấy eventId trong DLQ.");
                return;
            }
            if (!(old instanceof TextMessage oldText)) {
                ctx.rollback();
                throw new IllegalArgumentException(
                    "Demo chỉ replay TextMessage.");
            }

            int previous = old.propertyExists("manualReplayCount")
                ? old.getIntProperty("manualReplayCount") : 0;

            if (previous > 0) {
                ctx.rollback();
                throw new IllegalStateException(
                    "Đã replay trước đó; cần người vận hành kiểm tra.");
            }

            // Demo giả lập: nguyên nhân code/payload đã được sửa.
            // Production cần review nguyên nhân thật trước khi replay.
            TextMessage newer = ctx.createTextMessage(oldText.getText());
            newer.setStringProperty("eventId",
                old.getStringProperty("eventId"));
            newer.setStringProperty("scenario", "fixed");
            newer.setStringProperty("originalJmsMessageId",
                old.getJMSMessageID());
            newer.setIntProperty(
                "manualReplayCount", previous + 1);

            ctx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(main, newer);

            // Một transaction JMS: nhận khỏi DLQ và gửi lại main.
            ctx.commit();

            System.out.println(
                "REPLAY_COMMITTED eventId=" + eventId);
            System.out.println(
                "oldJMSMessageID=" + old.getJMSMessageID());
            System.out.println(
                "newJMSMessageID=" + newer.getJMSMessageID());
        } catch (Exception failure) {
            ctx.rollback();
            throw failure;
        } finally {
            consumer.close();
        }
    }

    private static void consumeFixed(JMSContext ctx)
            throws JMSException {
        JMSConsumer consumer = ctx.createConsumer(mainQueue(ctx));
        try {
            Message message = consumer.receive(5000);
            if (message == null) {
                System.out.println("Queue rỗng.");
                return;
            }
            printDelivery("AFTER_REPLAY", message);

            if (!"fixed".equals(
                    message.getStringProperty("scenario"))) {
                ctx.rollback();
                throw new IllegalStateException(
                    "Chỉ xử lý message đã kiểm tra để replay.");
            }

            // Chỉ in log để minh họa; nghiệp vụ thật cần
            // idempotency và điều kiện thành công trước JMS commit.
            System.out.println("BUSINESS_OK eventId=" +
                message.getStringProperty("eventId"));
            ctx.commit();
        } finally {
            consumer.close();
        }
    }

    private static void printDelivery(String label, Message message)
            throws JMSException {
        int deliveryCount = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount") : -1;

        System.out.printf(
            "%s eventId=%s JMSMessageID=%s redelivered=%s " +
            "JMSXDeliveryCount=%d%n",
            label,
            message.getStringProperty("eventId"),
            message.getJMSMessageID(),
            message.getJMSRedelivered(),
            deliveryCount
        );
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + key);
        }
        return value;
    }

    private static void usage() {
        System.out.println("RetryModesLab send-local");
        System.out.println("RetryModesLab client");
        System.out.println("RetryModesLab send-poison");
        System.out.println("RetryModesLab broker");
        System.out.println("RetryModesLab replay <eventId>");
        System.out.println("RetryModesLab consume-ok");
    }
}
~~~

**Lưu ý về mã:** Đây là demo cố tình đơn giản và dùng một consumer tại một thời điểm. Phương thức `localRetry()` nhận một message trước vòng for; `JMSXDeliveryCount` không tăng do hai lần thử HTTP giả lập. Phương thức `brokerRedelivery()` gọi `rollback()` sau **mỗi lần nhận** để broker xử lý redelivery. Phương thức `replayOne()` **không chuyển lại cùng JMS message object**: nó tạo `TextMessage` mới, giữ `eventId` và ghi `originalJmsMessageId` để điều tra.

Trong production, cần thêm giới hạn thời gian, dừng consumer có trật tự, circuit breaker, retry policy phân loại lỗi, retry budget và validation trước replay. `ctx.rollback()` sau lỗi có thể thất bại nếu connection đã mất; khi đó phải xử lý connection failure và theo dõi trạng thái broker thay vì giả định transaction được rollback chắc chắn.

### 6.3. Ràng buộc quan trọng khi replay từ DLQ

Code `replayOne()` dùng **cùng một JMSContext transacted** để:

1. Receive message cũ từ DLQ (chưa ACK).
2. Tạo message mới từ payload đã kiểm chứng.
3. Send message mới vào main queue.
4. `commit()` một JMS local transaction để ACK message DLQ và publish message mới.

Khi source và target thuộc cùng broker/connection/session, đây là cách giảm nguy cơ “xóa DLQ xong nhưng publish thất bại” hoặc “publish thành công rồi quên ACK DLQ”. Nó **không** bao gồm transaction DB/HTTP ngoài broker và không đảm bảo manual replay giữa hai broker khác nhau là nguyên tử.

Không dùng trực tiếp `consumer.receive()` với `AUTO_ACKNOWLEDGE` rồi thực hiện `producer.send()` trên connection khác nếu muốn bảo đảm chuyển message DLQ → main mà không mất message ở giữa. Với nhiều message, cần batch hữu hạn và giới hạn tốc độ.

## 7. Kịch bản chạy và kết quả cần ghi

Bắt đầu với hai queue `lab.retry.orders` và `lab.retry.dlq` **rỗng**. Dừng các consumer khác, xác nhận setting `max-delivery-attempts=3` và `redelivery-delay=1000` được nạp.

### Kịch bản A — Client local retry, chỉ một delivery

1. Chạy `RetryModesLab send-local`, ghi `eventId` và `JMSMessageID`.
2. Chạy `RetryModesLab client`. Log cho thấy một lần nhận `FIRST_DELIVERY` và hai dòng `LOCAL_RETRY`, sau đó `BUSINESS_OK localAttempt=3`.
3. Quan sát queue chính về 0 khi JMS commit thành công; DLQ vẫn 0.

Kết quả kỳ vọng: **một broker delivery**, ba lần thử nghiệp vụ nội bộ, một JMS commit. Bộ đếm broker **không tăng lên 3 chỉ vì handler gọi API ba lần**.

### Kịch bản B — Broker redelivery và DLQ

1. Chạy `RetryModesLab send-poison`, ghi `eventId` và `JMSMessageID`.
2. Chạy `RetryModesLab broker`.
3. Mỗi lần nhận, quan sát nhãn `BROKER_DELIVERY` và các trường `JMSRedelivered`, `JMSXDeliveryCount`. Handler rollback ngay thay vì sleep/gọi lại tại client.
4. Với policy minh họa, message thất bại nhiều lần và cuối cùng đủ điều kiện chuyển vào `lab.retry.dlq`. Quan sát queue chính về 0 và DLQ lên 1; thời điểm chính xác chịu tác động của policy/delay.
5. Nếu quá thời hạn mà chưa thấy DLQ, kiểm tra broker có nạp đúng policy, số lần delivery thực tế, tình trạng in-flight, có consumer khác hoặc lỗi routing tới DLQ.

Kết quả kỳ vọng: **cùng message broker** được giao lại trước khi vào DLQ; không tạo một event mới ở producer, không đổi `eventId`. Nếu provider hiển thị `JMSXDeliveryCount` từ 1 trở lên, sau rollback và redelivery nó thường tăng lên theo số lần giao; tránh dùng con số này như bảo đảm exactly-once.

### Kịch bản C — Operator phát lại từ DLQ

1. Đọc `eventId` của message poison trong DLQ, ví dụ `E-...`.
2. Giả định nguyên nhân đã được sửa ở code xử lý hoặc dữ liệu (demo thay `scenario=poison` bằng `scenario=fixed`).
3. Chạy `RetryModesLab replay <eventId>` để chuyển một message sang main.
4. Ghi log `oldJMSMessageID`, `newJMSMessageID` và `eventId`.
5. Chạy `RetryModesLab consume-ok`. Message mới được nhận và commit; queue chính về 0.
6. Kiểm tra DLQ đã giảm 1 sau transaction replay thành công.

Kết quả kỳ vọng: **JMSMessageID thay đổi**, `eventId` nghiệp vụ giữ nguyên, `manualReplayCount=1` và broker bắt đầu tính lại đời delivery của message mới. Nếu gửi lại mà lỗi gốc chưa sửa, message sẽ quay lại DLQ và tạo vòng lặp; vì vậy replay phải được kiểm soát.

### Bảng đối chiếu những gì phải thấy

| Chỉ số | Local retry | Broker redelivery | Manual replay |
|---|---|---|---|
| `eventId` | Giữ nguyên | Giữ nguyên | Giữ nguyên |
| `JMSMessageID` | Không đổi trong delivery | Không đổi trên message giao lại | Thường là ID mới |
| Số log gọi nghiệp vụ | 3 trong một lần nhận (demo) | Một lần mỗi delivery (demo) | Phụ thuộc việc xử lý message mới |
| `JMSXDeliveryCount` | Không tăng chỉ do local attempts | Tăng khi có redelivery, nếu provider báo | Bắt đầu trên message mới |
| Trigger DLQ | Không trực tiếp | Có thể sau max attempts | Chỉ nếu message replay thất bại trở lại |
| Điểm ACK/commit | Sau local success | Ở delivery thành công; thất bại rollback | Transaction ack DLQ + send main, rồi consumer main commit |

**Nguyên tắc quan sát:** Đếm *business attempts* bằng metric của ứng dụng, *broker deliveries* bằng delivery count và *manual replays* bằng một trường audit riêng. Không dùng một loại counter thay cho cả ba.

## 8. Quy trình manual replay an toàn hơn thao tác “Move messages” tùy tiện

Manual replay cần quy trình vận hành chặt hơn nhiều so với việc mở console và bấm chuyển message:

### 8.1. Phân loại trước khi thao tác

- **Poison payload:** JSON lỗi, thiếu field, sai phiên bản schema. Sửa dữ liệu (nếu được phép và có chứng cứ) hoặc sửa consumer; không replay y nguyên nếu chắc chắn thất bại.
- **Lỗi phụ thuộc:** DB/API downstream từng unavailable nhưng nay phục hồi. Xác nhận downstream đã ổn định và retry budget phù hợp.
- **Lỗi nghiệp vụ:** đơn đã hủy, trạng thái chuyển tiếp không hợp lệ. Có thể cần quyết định bỏ message có audit, không phải replay.
- **Không rõ nguyên nhân:** giữ ở DLQ, thu thập payload hash, eventId, stack trace và lịch sử delivery; đừng phát lại hàng loạt.

### 8.2. Các điều kiện trước replay

1. Xác minh event chưa tạo side effect hoặc side effect **idempotent**.
2. Biết chính xác source DLQ, destination main, routing type, message selector/ID và queue đang có.
3. Xác định version schema, tenant, quyền truy cập và mã handler đã sửa.
4. Đặt giới hạn số lượng, tốc độ và số lần replay tối đa cho mỗi event.
5. Ghi audit: người kích hoạt, lý do, thời điểm, original JMSMessageID, new JMSMessageID, eventId, payload hash, trạng thái kết quả.
6. Có thể dừng replay và giữ lại message chưa xử lý khi phát hiện tỷ lệ lỗi tăng.

**Không dùng thao tác “copy message” rồi ACK bản gốc ở DLQ theo hai connection độc lập** mà không có cơ chế bù: mất kết nối giữa hai bước có thể gây duplicate hoặc mất message. Nếu muốn cả hai cùng nằm trong JMS transaction, cần cùng broker/session như mã lab; giữa nhiều hệ thống cần thiết kế khác.

### 8.3. Giữ lại khóa nghiệp vụ, không tái sử dụng provider headers bừa bãi

Khi tạo message replay:

- **Giữ:** `eventId/commandId` gốc, `aggregateId`, version/schema, correlation/trace ID nếu dùng.
- **Ghi thêm:** `manualReplayCount`, `replayReason`, `originalJmsMessageId`, actor/time trong audit.
- **Không copy mù:** `JMSMessageID`, `JMSRedelivered`, `JMSXDeliveryCount`, delivery timestamp, internal Artemis/ActiveMQ headers, ACK token hoặc các thuộc tính quản trị của broker.
- **Kiểm tra lại:** TTL, priority, delivery mode, selector-required properties và JMS message type. Nếu TTL gốc đã hết, sao chép TTL mà không hiểu ý nghĩa có thể khiến message replay expire tức thì.

Manual replay giúp đưa công việc quay lại pipeline, **không hủy lịch sử redelivery và không chứng minh kết quả nghiệp vụ đã thành công**.

## 9. Idempotency: nơi ba cơ chế gặp nhau

Giả sử consumer đã ghi DB thành công nhưng mất kết nối trước `JMSContext.commit()`:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Business DB
    B->>C: Delivery E-100
    C->>DB: Ghi đơn hàng / vận đơn
    DB-->>C: DB commit thành công
    Note over C: Kết nối mất trước JMS commit
    B->>C: Redelivery E-100
    C->>DB: Kiểm tra E-100 đã xử lý
    DB-->>C: Đã xử lý, bỏ qua side effect
    C->>B: JMS commit / ACK
~~~

Producer resend và manual replay cũng có thể đưa **eventId E-100** trở lại pipeline. Do đó idempotency phải ở **cấp nghiệp vụ**, không chỉ dựa vào `JMSRedelivered`:

~~~sql
BEGIN;

-- Cần UNIQUE(consumer_name, event_id).
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('fulfillment', 'E-100');

-- Chỉ chạy khi insert chống trùng thành công.
UPDATE orders
SET status = 'READY_FOR_SHIPPING'
WHERE order_id = 'ORD-100'
  AND status = 'PAID';

COMMIT;
~~~

Nếu insert gặp lỗi unique của event đã xử lý, handler không thực hiện side effect lần nữa rồi có thể ACK message hiện tại. Đảm bảo câu lệnh insert idempotency và update nghiệp vụ nằm trong **cùng DB transaction**; một cặp `SELECT/INSERT` tách rời có thể race khi hai consumer song song.

Nếu nghiệp vụ gọi API ngoài như tạo vận đơn/gửi email, dùng idempotency key do API hỗ trợ hoặc outbox/saga, vì transaction DB/JMS không tự bao trùm tác động bên ngoài.

**Vấn đề khóa đếm:** `manualReplayCount` hữu ích cho vận hành nhưng một message mới có thể bị producer resend hoặc broker replay mà vẫn thiếu trường này; nó không thay thế unique constraint trên `eventId`.

## 10. Giám sát để phân biệt sự cố

| Tín hiệu | Gợi ý nguyên nhân | Hành động đầu tiên |
|---|---|---|
| Business attempt rate tăng nhưng `JMSXDeliveryCount` không tăng | Client-local retry nhiều lần trong cùng delivery | Kiểm tra số lần thử, backoff, timeout và circuit breaker |
| `JMSXDeliveryCount`, rollback và redelivery tăng | Consumer fail/rollback, broker giao lại | Xem lỗi xử lý, max attempts, redelivery delay và DLQ |
| DLQ count tăng | Poison message hoặc dependency không hồi phục trong retry budget | Phân loại lỗi trước khi replay |
| Queue chính tăng ngay sau batch operator chạy | Manual replay đang nạp lại backlog | Rate limit replay, quan sát throughput consumer |
| Nhiều `JMSMessageID` nhưng cùng `eventId` | Producer retry hoặc manual replay/new publish | So audit/outbox/replay metadata; bảo vệ idempotency |
| `JMSMessageID` giữ nguyên, `JMSRedelivered=true` | Message chưa ACK được provider giao lại | Kiểm tra transaction và crash window |
| Một event lặp tại downstream dù JMS ACK thành công | Consumer xử lý trùng trước ACK hoặc side effect không idempotent | Xem khóa nghiệp vụ và trạng thái commit thực tế |

Nên đo đồng thời:

- `client_local_attempts_total{operation,outcome}` (không cần chứa eventId trong nhãn metric vì cardinality cao).
- `jms_redelivery_observed_total{queue}` và tỷ lệ rollback/commit.
- `dlq_messages{queue}`, tuổi message cũ nhất, lý do lỗi.
- `manual_replay_total{operator,reason}` với trường operator phải được xử lý theo chính sách nhãn metric phù hợp.
- `idempotency_duplicate_detected_total{consumer}`.
- Downstream 5xx, timeout, circuit breaker open, tốc độ xử lý so với tốc độ enqueue.

Để truy vết một sự kiện cụ thể, log có cấu trúc nên dùng `eventId`, `JMSMessageID`, delivery count, replay count, exception class, correlation ID và duration. Tránh log payload nhạy cảm hoặc mật khẩu.

## 11. Lỗi thiết kế và cách sửa

| Sai lầm | Vì sao nguy hiểm? | Sửa bằng |
|---|---|---|
| Catch exception trong consumer rồi ACK để “không lặp” | Mất công việc dù nghiệp vụ thất bại | ACK chỉ khi xử lý thành công hoặc có quyết định loại bỏ được audit |
| Local retry vô hạn trong một delivery | Worker giữ in-flight, không chạm giới hạn DLQ của broker | Local retry budget hữu hạn rồi rollback |
| Client và broker đều retry hàng chục lần không có backoff | Khuếch đại lỗi downstream | Điều tiết tổng retry budget, backoff, circuit breaker |
| Dùng `JMSRedelivered=false` làm bằng chứng chưa xử lý | Producer resend/manual replay là message mới nhưng cùng nghiệp vụ | Dùng eventId và unique constraint |
| Dùng `JMSMessageID` làm khóa idempotency | Manual replay và producer retry có thể sinh ID mới | Dùng eventId/commandId ổn định |
| Tự động replay DLQ không giới hạn | Tạo vòng lặp độc không dứt | Cần điều tra, remediation, rate limit và audit |
| Sao chép mọi property/header của message DLQ | Mang theo metadata nội bộ/TTL không hợp lệ | Tạo message mới với các field được allowlist |
| Di chuyển DLQ bằng hai transaction độc lập | Crash giữa nhận DLQ và publish gây mất/trùng | Dùng một transacted JMS session khi cùng broker hoặc quy trình an toàn tương đương |
| Dùng `AUTO_ACKNOWLEDGE` rồi `throw` sau `receive()` để mong rollback | Message có thể đã ACK từ lúc receive trả về | Dùng transacted session hoặc acknowledgment mode phù hợp |
| Thấy DLQ trống nên kết luận hết lỗi | DLQ có thể cấu hình thiếu queue hoặc message expire | Kiểm tra route DLQ, queue/expiry, broker logs và chỉ số lỗi |

## 12. Bài tập kiểm chứng hiểu đúng

1. Worker nhận E-100 một lần, gọi API ba lần rồi JMS commit. `JMSXDeliveryCount` có bắt buộc tăng thành 3 không? Vì sao?
2. Một message poison được broker giao lại ba lần rồi vào DLQ. Nếu operator gửi lại bằng `createTextMessage()`, trường nào nên giữ nguyên, trường nào thường thay đổi?
3. Producer gửi E-100, broker commit nhưng phản hồi mất; producer gửi lại. Đây là **broker redelivery** hay **producer-side retry**? Vì sao có thể có hai `JMSMessageID`?
4. Nếu Artemis cấu hình `max-delivery-attempts=3` nhưng consumer local retry 5 lần mỗi delivery, số request downstream có thể đến mức nào? Cần giảm ở đâu?
5. Một message thất bại do JSON thiếu field bắt buộc. Nên local retry, rollback nhiều lần hay đưa sang quy trình sửa lỗi/replay? Hãy nêu điều kiện quyết định.
6. Nếu operator copy 1.000 message từ DLQ sang main bằng cùng một session transaction rồi client timeout trước khi biết kết quả commit, phải dựa trên bằng chứng nào để tránh replay lại vô điều kiện?
7. Trong Classic, vì sao setting `RedeliveryPolicy` ở client và poison ACK có thể quan trọng hơn khi giải thích việc chuyển DLQ?
8. Tại sao consumer đã gửi email thành công nhưng JMS rollback vẫn có nguy cơ gửi email lần hai dù message không bị producer resend?

**Đáp án định hướng:** (1) Không, vẫn là một delivery; (2) giữ eventId, tạo JMSMessageID mới, ghi audit replay; (3) producer retry, có thể tạo bản sao message; (4) đến khoảng 15 lần trong giả định 3 deliveries, cần tổng retry budget/backoff; (5) lỗi vĩnh viễn không retry nóng, xử lý cách ly/điều tra; (6) kiểm tra trạng thái broker, DLQ/main queue, audit/idempotency, không kết luận từ timeout; (7) Classic client tham gia quyết định redelivery và gửi poison ACK; (8) HTTP/email nằm ngoài JMS transaction, nên phải idempotent.

## 13. Tài liệu tham khảo

- [Apache ActiveMQ Artemis — Message Redelivery and Undelivered Messages](https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages.html): `redelivery-delay`, `max-delivery-attempts` và DLQ.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, queue, routing và cấu hình dead-letter.
- [Apache ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling): `RedeliveryPolicy`, poison ACK và broker DLQ strategy.
- [Jakarta Messaging — JMSContext / Session / Message](https://jakarta.ee/specifications/messaging/): transaction/rollback, message headers và JMSX delivery properties.

**Kết luận:** **Client-local retry** thử lại logic trong cùng một delivery; **broker redelivery** là chu kỳ giao lại một message chưa được xác nhận; **manual replay** là hành động vận hành phát lại message sau khi điều tra, thường tạo một message broker mới. Producer retry khi kết quả gửi không chắc chắn lại là một con đường có thể phát sinh duplicate khác. Hãy giữ `eventId` ổn định, phân biệt counter cho từng cơ chế, kiểm soát retry budget và chỉ ACK sau khi nghiệp vụ an toàn. DLQ là điểm cách ly để sửa nguyên nhân, không phải chiếc nút “thử lại vô hạn”.
