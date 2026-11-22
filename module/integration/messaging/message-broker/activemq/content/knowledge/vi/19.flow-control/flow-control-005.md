# consumerWindowSize, producerWindowSize và cơ chế credit của Artemis Core client

> **Chương:** Điều tiết lưu lượng  
> **Phạm vi:** Apache ActiveMQ **Artemis 2.57.x**, giao thức **Core** với Java/JMS (`jakarta.jms`). Bài tập trung vào window/credit giữa Artemis broker và Core client, không đi sâu lại vào acknowledgment, transaction, paging hay DLQ. ActiveMQ Classic/OpenWire và AMQP có cơ chế flow control khác; không dùng trực tiếp các quy tắc credit này để suy diễn hành vi của chúng.

## 1. Hai hướng truyền dữ liệu, hai ngân sách credit khác nhau

Trong một luồng queue bất đồng bộ, backlog có thể xuất hiện tại broker, nhưng cũng có thể nằm trong bộ đệm client. Nếu một consumer chậm đã nhận trước hàng trăm message vào buffer, consumer nhanh khác **không thể lấy ngay** những message đó dù broker vẫn còn sức xử lý. Ở hướng ngược lại, một producer có thể gửi nhanh hơn tốc độ broker lưu/xử lý; nếu không có cơ chế hãm, các bộ đệm mạng và server tăng không kiểm soát.

Artemis Core xử lý hai tình huống bằng **credit theo byte**:

```text
                 DÒNG CONSUMER (broker -> client)
      broker queue  ──── messages (tốn credit) ────▶ [client buffer] -> receive()
                    ◀── bổ sung consumer credit ──
                       consumerWindowSize

                 DÒNG PRODUCER (client -> broker)
      producer      ──── messages (tốn credit) ────▶ broker address/queue
                    ◀── cấp thêm producer credit ───
                       producerWindowSize
```

| Thuộc tính | Hướng được điều tiết | Phạm vi | Trả lời câu hỏi |
|---|---|---|---|
| `consumerWindowSize` | **Broker → consumer** | Buffer/credit cho từng Core consumer | Broker được đẩy trước bao nhiêu **byte** đến một consumer? |
| `producerWindowSize` | **Producer → broker** | Credit của Core producer theo address | Producer được gửi bao nhiêu **byte** trước khi phải xin thêm credit? |
| `max-size-bytes` + `address-full-policy` | Broker kiểm soát tài nguyên **address** | Mọi queue/binding thuộc address | Khi address đầy, broker **PAGE/BLOCK/FAIL/DROP** như thế nào? |

**Không nhầm các đơn vị:** window là **byte**, không phải số message, số lần giao hay mili giây. Payload 2 KiB không nhất thiết chiếm chính xác 2.048 byte credit vì còn phần header/encoding và cách implementation định lượng message. Window cũng không phải giới hạn cứng cho toàn bộ heap của client hoặc tổng bộ nhớ broker.

## 2. Consumer credit: vì sao broker có thể giao trước khi Java gọi receive?

### 2.1. Vòng đời của credit

Core consumer có một ngân sách credit. Khi consumer được phép nhận message, broker dispatch các message tương ứng với credit còn lại; phía client đưa chúng vào **buffer** để `receive()` hoặc `MessageListener` lấy khi sẵn sàng. Khi client lấy/xử lý dữ liệu và giải phóng phần buffer đã dùng, client bổ sung credit để broker tiếp tục đẩy message.

```text
Thời điểm          Credit giả định       Hành động
-----------------------------------------------------------------------
t0                 64 KiB               client đăng ký consumer
t1                 48 KiB               broker đã giao ~16 KiB dữ liệu
t2                 16 KiB               broker giao thêm ~32 KiB
t3                 gần hết              client tạm thời không nhận thêm
t4                 tăng trở lại          Java nhận dữ liệu, client cấp thêm credit
t5                 được phép dispatch   broker tiếp tục gửi
```

Đây là **sơ đồ cơ chế**, không phải công thức chính xác cho từng gói tin. Artemis có thể gom credit request, hỗ trợ message lớn và đặt ngưỡng tối ưu nhằm tránh mỗi message cần một lượt mạng. Điểm quan trọng: **credit điều khiển việc dispatch vào client buffer**, còn **commit/ACK điều khiển thời điểm broker coi message đã được xử lý**. Hai khái niệm này không đồng nhất.

### 2.2. Ba chế độ của `consumerWindowSize`

| Giá trị | Hành vi | Trường hợp sử dụng |
|---|---|---|
| `-1` | Không giới hạn buffer prefetch bằng window (unbounded) | Chỉ cân nhắc với consumer rất nhanh, message/lưu lượng đã được kiểm soát; có nguy cơ cạn heap |
| `0` | Không prefetch vào buffer của consumer; lấy message theo nhu cầu | Consumer xử lý chậm, nhiều competing consumers, muốn hạn chế message bị giữ ở client |
| `> 0` | Cấp một window theo byte, có prefetch giới hạn | Thường là lựa chọn cân bằng throughput/heap/độ công bằng |

**Mặc định Artemis Core 2.57.0 là 1.048.576 byte (1 MiB)** nếu không bị override bởi `default-consumer-window-size` trên address hoặc cấu hình explicit ở client. Không có một window tối ưu chung: message vài trăm byte, payload 64 KiB và consumer gọi HTTP 200 ms có đặc tính rất khác nhau.

`consumerWindowSize=0` **không có nghĩa không bao giờ có message in-flight**. Nó ngăn việc *giữ trước hàng loạt message trong client buffer*; một message vẫn có thể đã được dispatch và đang được `receive()`/listener xử lý. Khi transaction chưa commit hoặc client rớt mạng, broker vẫn phải xử lý redelivery theo chính sách.

### 2.3. Ví dụ hai competing consumers: một nhanh, một chậm

Giả sử cùng queue `lab.flow.share` có hai consumer:

- **Fast** xử lý mỗi message rất nhanh.
- **Slow** mất 120 ms cho mỗi message vì một công việc giả lập.

Với window 1 MiB, broker có thể prefetch lượng message đáng kể vào buffer Slow trước khi nó kịp xử lý. Lúc đó Fast có thể rảnh trong khi Slow vẫn giữ backlog **đã dispatch**. Với `consumerWindowSize=0`, Slow không giữ trước nhiều message; những message chưa giao còn trên broker để Fast có cơ hội nhận.

| Chỉ số | Window lớn | Window 0 |
|---|---|---|
| Throughput khi **một consumer nhanh** | Thường cao nhờ ít round trip | Có thể thấp hơn do lấy message theo nhu cầu |
| Competing consumers khác tốc độ | Có thể xảy ra phân phối lệch, client chậm ôm backlog | Thường công bằng với năng lực xử lý hơn |
| Bộ nhớ client | Tăng theo số consumer, kích thước window và metadata | Giảm prefetch; không xóa các bộ nhớ khác |
| Message đang delivering nhưng chưa ACK | Có thể nhiều vì prefetch/transaction | Thường ít hơn |

**Phân phối không được bảo đảm theo một tỷ lệ 50/50.** Với consumer có tốc độ xử lý khác nhau, mục tiêu thường là **không để consumer nhanh ngồi chờ vì message đã bị giao trước cho consumer chậm**, chứ không buộc mỗi consumer phải nhận bằng nhau. Từ đó phải benchmark trên workload thật.

## 3. Producer credit: khi nào send bị hãm?

Core producer tiêu thụ **byte credit** khi gửi message tới một address. Khi sắp cạn, client xin thêm; broker phân bổ credit dựa trên cấu hình address và tài nguyên khả dụng. Khi không được cấp đủ, lời gọi `send` có thể **chờ** cho đến khi nhận được thêm credit.

```text
Producer                  Broker (address lab.flow.block)
   | -- request credits --> |
   | <-- grant credits ---- |
   | -- SEND bytes -------> |  address dùng thêm bộ nhớ
   | -- SEND bytes -------> |  address gần max-size-bytes
   | -- request credits --> |
   |    (không cấp tiếp khi address đang đầy + BLOCK)
   | [producer chờ]         |  consumer chưa giải phóng chỗ
   |                        |
   |           consumer ACK -> address có thêm headroom
   | <-- grant credits ---- |
   | -- SEND tiếp --------> |
```

### 3.1. Mặc định và các giá trị hợp lệ

Artemis 2.57.0 đặt `ActiveMQClient.DEFAULT_PRODUCER_WINDOW_SIZE = 65536` (**64 KiB**). Giá trị này có thể đặt ở URI `producerWindowSize` hoặc `ServerLocator.setProducerWindowSize(...)`:

| Giá trị | Ý nghĩa |
|---|---|
| `-1` | Vô hiệu hóa cơ chế producer flow control theo window; rủi ro client đẩy quá nhanh, không nên dùng để “chữa” nghẽn broker |
| `> 0` | Kích thước byte credit được request cho producer; điều chỉnh mức dữ liệu đang truyền/chờ trên connection |
| `0` | **Không phải giá trị hợp lệ** của `setProducerWindowSize`; đừng suy diễn từ consumerWindowSize=0 |

Window nhỏ làm credit request diễn ra thường xuyên hơn, tăng chi phí điều phối và có thể giảm throughput. Window lớn giảm một số round trip nhưng làm tăng lượng dữ liệu **có khả năng đã được phép gửi** trước khi broker dừng cấp thêm credit. Không lấy nó làm giới hạn tuyệt đối cho số message đã lưu trên disk.

### 3.2. Cần `address-full-policy=BLOCK` để quan sát blocking thật

Trong `broker.xml` của **broker Artemis lab**, đặt policy dành riêng cho một address:

```xml
<!-- Fragment bên trong <address-settings> đã có. -->
<address-setting match="lab.flow.block">
    <max-size-bytes>65536</max-size-bytes>
    <address-full-policy>BLOCK</address-full-policy>
</address-setting>
```

Và queue ANYCAST tường minh trong `<addresses>`:

```xml
<address name="lab.flow.block">
    <anycast>
        <queue name="lab.flow.block"/>
    </anycast>
</address>
```

Ở ví dụ này, khi broker thấy address đạt giới hạn 64 KiB và không còn khả năng cấp thêm credit, producer có thể bị **block**. Nếu consumer xử lý/ACK message, address giải phóng tài nguyên và broker cấp credit để producer tiếp tục.

**Chính sách đầy address là cơ chế riêng:** `PAGE` cho phép broker đẩy message ra paging store thay vì chủ động chặn theo ngưỡng memory; `FAIL` trả lỗi; `DROP` bỏ message. Tài liệu bản cũ có thể mô tả default khác. Với bài thử, **đặt `BLOCK` rõ ràng**, không suy từ mặc định; đọc cấu hình hiệu lực của phiên bản triển khai.

#### Credit không phải một hàng rào cứng bảo đảm `AddressSize ≤ max-size-bytes`

Vì credit được cấp cho **từng producer**, các producer đồng thời có thể đã nhận credit rồi cùng gửi trong khi address chỉ vừa đạt ngưỡng. Tài liệu Artemis đưa ra mức vượt xấp xỉ có thể phụ thuộc:

```text
số producer trên address × producerWindowSize
```

Ví dụ bốn producer với window 16 KiB có thể làm lượng message đã được phép gửi lớn hơn ngưỡng khoảng vài chục KiB trong một số thời điểm. Đây là **ước lượng tình huống**, không phải phép cộng luôn đúng hoặc cam kết giá trị chính xác; kích thước message, thời điểm cấp credit và cơ chế tính tài nguyên còn ảnh hưởng.

Khi yêu cầu hard limit, cần policy và quy trình bảo vệ riêng; không sử dụng window credit như một quota bảo mật. Broker cũng giả định client Core tuân thủ credit; một client không tuân thủ giao thức có thể gây tải ngoài dự kiến.

## 4. Cấu hình Core client: URI, JNDI và API

Hai thuộc tính được cấu hình **phía client**, không đặt vào `<acceptor>` của `broker.xml`. Tạo factory **trước khi** tạo connection/session/consumer để các consumer và producer mới dùng cấu hình mong muốn.

### 4.1. Java/JMS — cấu hình URI trực tiếp

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

String brokerUri = "tcp://127.0.0.1:61616"
        + "?consumerWindowSize=0"
        + "&producerWindowSize=16384";

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory(brokerUri);
try {
    // Tạo JMSContext/JMSProducer/JMSConsumer từ factory tại đây.
} finally {
    factory.close();
}
```

Chỉ dùng factory **Artemis Core**. Client OpenWire của ActiveMQ Classic và AMQP JMS provider có cách flow control khác. `consumerWindowSize`/`producerWindowSize` không phải option được gắn vào từng `Queue` object.

### 4.2. Cấu hình JNDI trong ứng dụng Java SE

```properties
java.naming.factory.initial=org.apache.activemq.artemis.jndi.ActiveMQInitialContextFactory
connectionFactory.FlowCF=tcp://127.0.0.1:61616?consumerWindowSize=0&producerWindowSize=16384
queue.flowShare=lab.flow.share
queue.flowBlock=lab.flow.block
```

Ứng dụng tra cứu `context.lookup("FlowCF")` để lấy factory, sau đó `context.lookup("flowShare")` hoặc `flowBlock`. Trong Java `.properties`, ký tự `&` trên cùng dòng là **phần của giá trị URI**; nếu viết URI bên trong attribute XML phải encode thành `&amp;`.

### 4.3. Core API thuần

Với `org.apache.activemq.artemis.api.core.client.ServerLocator` đã được tạo:

```java
// Đặt trước khi createSessionFactory/createSession.
locator.setConsumerWindowSize(0);
locator.setProducerWindowSize(16 * 1024);
```

`ServerLocator` là nơi cấu hình Core session factory; nó không tạo một `jakarta.jms.JMSContext` từ chính các lệnh setter này. Ở ứng dụng JMS, ưu tiên URI/`ActiveMQConnectionFactory` để tránh trộn Core API và JMS API không cần thiết.

### 4.4. Override mặc định phía broker cho Core consumer

Artemis hỗ trợ default theo **address** nếu Core consumer **không** khai báo window:

```xml
<!-- Fragment bên trong <address-settings>. -->
<address-setting match="lab.flow.share">
    <default-consumer-window-size>65536</default-consumer-window-size>
</address-setting>
```

Đây là **default được broker áp dụng khi client không đặt tường minh**, không thay thế giá trị `consumerWindowSize=0` đã chọn rõ trong URI. Không nhầm `default-consumer-window-size` với một broker-side `producerWindowSize` tương tự: producer window trong bài này cấu hình ở Core client.

## 5. Bốn cơ chế thường bị nhầm với window credit

| Cơ chế | Đơn vị | Tác dụng | Không nên suy diễn |
|---|---|---|---|
| `consumerWindowSize` | Byte | Giới hạn prefetch vào buffer Core consumer | Không quyết định ACK/commit |
| `producerWindowSize` | Byte | Giới hạn credit request/in-flight trước khi xin thêm | Không thay max-size của broker |
| `consumerMaxRate` / `producerMaxRate` | Message/giây | Rate limiting ở phía client | Không giới hạn trực tiếp byte trong buffer; mặc định `-1` (tắt) |
| `confirmationWindowSize` | Byte | Bộ đệm lệnh phục vụ replay/confirmation khi reconnect/failover của Core client | Không phải credit window producer |
| `blockOnDurableSend` | Boolean | Có chờ broker xác nhận gửi durable hay không | Không thay chính sách cấp credit |
| `callTimeout` | Mili giây | Timeout cho blocking Core call theo hợp đồng API | Không bảo đảm luôn ngắt một producer đang đợi credit ở mọi tình huống |
| `max-size-bytes` + `address-full-policy` | Byte + policy | Chọn hành động khi address đầy | Không quyết định lượng prefetch của consumer |

**Điểm vận hành:** nếu thread producer đang chờ cấp credit, tăng `callTimeout` chưa chắc giải quyết; nếu send đợi ACK bền vững, tăng `producerWindowSize` chưa chắc giảm latency journal. Luôn xác định nó bị chậm **ở credit, broker memory/page, network hay durability** trước khi chỉnh.

**Khác biệt AMQP:** credit của AMQP link được tính theo **số message** (bên cạnh các giới hạn của broker), còn Core producer credit trong bài được tính theo **byte**. Không đưa `producerWindowSize` vào Qpid JMS rồi kỳ vọng cùng semantics.

## 6. Bài thực hành A: consumer nhanh và chậm cạnh tranh trên một queue

Mục tiêu: so sánh `consumerWindowSize=1048576` và `consumerWindowSize=0` trong khi giữ producer, payload, broker và tốc độ xử lý không đổi. Không đặt `address-full-policy=BLOCK` cho queue này, tránh producer bị nghẽn khiến khó quan sát phân phối cho consumer.

**Broker lab:** khai báo queue riêng `lab.flow.share`:

```xml
<!-- Trong <addresses> hiện hữu. -->
<address name="lab.flow.share">
    <anycast>
        <queue name="lab.flow.share"/>
    </anycast>
</address>
```

Có thể dùng một policy riêng `address-full-policy=PAGE` với `max-size-bytes` đủ lớn, nhưng **không** dùng namespace/queue `lab.flow.block` trong bài so sánh consumer. Ứng dụng có quyền send/consume và không có competing consumer nào khác.

### 6.1. Dependency và mã Java

JDK 17, chọn client Artemis Jakarta:

```xml
<!-- Fragment trong <dependencies> của pom.xml. -->
<dependency>
    <groupId>org.apache.artemis</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.57.0</version>
</dependency>
```

**`ConsumerWindowLab.java`** — một queue, hai worker độc lập, mỗi worker có **JMSContext/Session riêng**:

```java
import jakarta.jms.BytesMessage;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ConsumerWindowLab {
    private static final String QUEUE = "lab.flow.share";
    private static final int TOTAL = 240;

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return value;
    }

    private static int work(ConnectionFactory cf, String user, String pass,
                            String runId, int workMs, String label,
                            CountDownLatch ready, AtomicInteger finished)
                            throws Exception {
        // Không chia sẻ JMSContext giữa hai thread.
        try (JMSContext ctx = cf.createContext(
                user, pass, JMSContext.SESSION_TRANSACTED)) {
            String selector = "labRunId = '" + runId + "'";
            JMSConsumer consumer = ctx.createConsumer(ctx.createQueue(QUEUE), selector);
            ctx.start();
            ready.countDown();

            int local = 0;
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(40);
            while (System.nanoTime() < deadline && finished.get() < TOTAL) {
                Message msg = consumer.receive(300);
                if (msg == null) {
                    continue;
                }
                if (workMs > 0) {
                    Thread.sleep(workMs);
                }
                ctx.commit(); // chỉ tính đã xử lý sau commit thành công
                finished.incrementAndGet();
                local++;
            }
            System.out.println(label + " committed=" + local);
            return local;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: ConsumerWindowLab <consumerWindowSize>");
        }
        int window = Integer.parseInt(args[0]);
        if (window < -1) {
            throw new IllegalArgumentException("Invalid window");
        }
        String user = requireEnv("BROKER_USER");
        String pass = requireEnv("BROKER_PASSWORD");
        String runId = UUID.randomUUID().toString();

        String url = "tcp://127.0.0.1:61616?consumerWindowSize=" + window
                     + "&producerWindowSize=16384";
        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(url);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        AtomicInteger finished = new AtomicInteger();
        CountDownLatch ready = new CountDownLatch(2);
        long start = System.nanoTime();
        try {
            Future<Integer> slow = pool.submit(() ->
                work(factory, user, pass, runId, 120, "slow", ready, finished));
            Future<Integer> fast = pool.submit(() ->
                work(factory, user, pass, runId, 0, "fast", ready, finished));

            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Consumers not ready");
            }
            // Đợi cả hai đăng ký rồi mới gửi để giảm thiên lệch startup.
            try (JMSContext sender = factory.createContext(user, pass)) {
                JMSProducer producer = sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT);
                Queue destination = sender.createQueue(QUEUE);
                byte[] payload = new byte[2048];
                for (int i = 0; i < TOTAL; i++) {
                    BytesMessage m = sender.createBytesMessage();
                    m.writeBytes(payload);
                    m.setStringProperty("labRunId", runId);
                    producer.send(destination, m);
                }
            }

            int slowCount = slow.get(50, TimeUnit.SECONDS);
            int fastCount = fast.get(50, TimeUnit.SECONDS);
            long ms = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
            System.out.printf(
                "window=%d fast=%d slow=%d committed=%d/%d elapsedMs=%d%n",
                window, fastCount, slowCount, finished.get(), TOTAL, ms);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
            factory.close();
        }
    }
}
```

**Cách thử:**

1. Dùng queue lab rỗng, chạy `ConsumerWindowLab 1048576`; ghi `fast/slow`, thời gian hoàn tất, số message **delivering** qua management.
2. Với **một lượt dữ liệu mới**, chạy `ConsumerWindowLab 0` trên cùng broker, JDK, payload và số consumer; ghi chỉ số tương ứng.
3. Nếu còn message từ lần trước do test ngắt giữa chừng, **không purge queue nghiệp vụ**; dùng queue lab riêng và dọn theo quy trình được phép. Chương trình gắn `labRunId` để phân biệt từng lượt.

**Kỳ vọng, không phải output đã chạy:** với window 0, Fast thường nhận được phần việc lớn hơn và độ trễ hoàn tất giảm khi Slow thực sự chậm; với window 1 MiB, Slow có thể giữ message đã dispatch. Kết quả phụ thuộc scheduling, thời điểm dispatch, tốc độ broker và policy. Không đặt assertion `fastCount > slowCount` như quy tắc bắt buộc của giao thức.

**Lưu ý về tài nguyên:** phần thử nghiệm tạo hai task rồi gửi 240 message từ một factory. `JMSContext` không được chia sẻ giữa các task; factory có thể được dùng để tạo nhiều context. Nếu timeout kết thúc trước khi xử lý hết, những transaction chưa commit phải được broker xử lý khi context/connection đóng; kiểm tra queue trước lần thử kế tiếp.

## 7. Bài thực hành B: producer chờ credit khi address đầy

Mục tiêu: với `producerWindowSize` hữu hạn và `address-full-policy=BLOCK`, chứng minh producer **bị hãm do broker không cấp thêm credit** khi không có consumer rút message.

### 7.1. Chuẩn bị broker

Áp dụng `lab.flow.block` ở mục 3.2 với `max-size-bytes=65536`, `BLOCK` và queue ANYCAST cùng tên. Đảm bảo không có consumer. Kiểm tra lại cấu hình đang hiệu lực bằng management/broker log; `max-size-bytes` là **byte usage do broker tính**, không phải đúng 16 message 4 KiB rồi dừng.

### 7.2. Producer minh họa

```java
import jakarta.jms.BytesMessage;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.concurrent.TimeUnit;

public final class ProducerWindowLab {
    public static void main(String[] args) {
        String user = System.getenv("BROKER_USER");
        String pass = System.getenv("BROKER_PASSWORD");
        if (user == null || pass == null) {
            throw new IllegalArgumentException("Missing broker credentials");
        }
        int producerWindow = args.length == 0 ? 16384
            : Integer.parseInt(args[0]);
        if (producerWindow == 0 || producerWindow < -1) {
            throw new IllegalArgumentException("Use -1 or a positive window");
        }

        String uri = "tcp://127.0.0.1:61616?producerWindowSize="
                     + producerWindow;
        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(uri);
        try {
            try (JMSContext ctx = factory.createContext(user, pass)) {
                JMSProducer producer = ctx.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT);
                Queue destination = ctx.createQueue("lab.flow.block");
                byte[] body = new byte[4096];
                for (int i = 1; i <= 1000; i++) {
                    BytesMessage message = ctx.createBytesMessage();
                    message.writeBytes(body);
                    long before = System.nanoTime();
                    producer.send(destination, message);
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - before);
                    System.out.printf("sent=%d sendMs=%d%n", i, elapsedMs);
                }
            }
        } finally {
            factory.close();
        }
    }
}
```

Chạy trên **lab cô lập** và dùng **timeout của process/terminal** (ví dụ lệnh `timeout` trên Linux), vì với `BLOCK` và không có consumer, một `send()` **có thể chờ lâu không xác định**. Nếu hết thời gian chờ ngoài, đó là **bằng chứng cần kết hợp với metrics**, không khẳng định message cuối bị mất hay chưa được broker nhận. Không dựa vào việc interrupt thread hay `Future.get(timeout)` như một cơ chế hủy send an toàn.

Lặp lần thử với **producerWindowSize=8192** và **65536**, cùng queue lab đã được trả về trạng thái trống và cùng policy. Quan sát tốc độ gửi, vị trí producer bắt đầu block, `addressSize`, `messageCount`, paging state và metrics I/O. Cửa sổ lớn có thể cho phép nhiều byte được gửi trước khi producer chờ; **không bảo đảm** message thứ N cố định sẽ là message bị block. Sau đó khởi động một consumer để ACK message, quan sát producer có thể tiếp tục khi broker cấp thêm credit. Nếu không biết queue còn chứa dữ liệu gì, **không** purge tùy tiện.

## 8. Đo và chẩn đoán: credit đang hết hay broker đang nghẽn?

| Triệu chứng | Tín hiệu cần xem | Hướng xử lý |
|---|---|---|
| Consumer nhanh nhưng `receive()` thường đợi mạng | Window quá nhỏ/0, RTT cao, client không prefetch | Thử 64 KiB → 1 MiB; đo throughput và heap |
| Nhiều consumer mà một worker chậm giữ backlog | `deliveringCount` cao ở queue, buffer client lớn, worker chậm | Thử window 0 hoặc nhỏ; đánh giá fairness |
| Heap consumer tăng khi producer đẩy nhanh | Client prefetch không giới hạn `-1` hoặc quá nhiều consumer | Giảm window và giới hạn concurrency/payload |
| Producer `send()` đứng chờ ở địa chỉ đầy | `addressSize` sát `max-size-bytes`, policy `BLOCK`, consumer không ACK | Bổ sung consumer, xử lý backlog, xem policy/storage |
| Producer nhanh nhưng broker paging quá nhiều | Address policy `PAGE`, tốc độ consume thấp | Tối ưu throughput/consumer và storage; không chỉ tăng window |
| Gửi chậm dù address chưa đầy | Journal fsync, network RTT, blockOnDurableSend, credit quá nhỏ | Đo latency từng lớp, thử window mà không tắt durability |
| Chỉnh window nhưng không thay đổi hành vi | Kết nối cũ vẫn hoạt động, sai provider/protocol, config chưa có hiệu lực | Tạo factory/connection mới, xác minh URI Core, đọc broker metrics |
| Tăng producerWindowSize làm address vượt memory limit | Nhiều producer đã có credit outstanding | Giảm window/concurrency; không coi window là hard quota |

**Chỉ số nên thu thập theo cùng khoảng thời gian:** `AddressControl.addressSize`, queue `messageCount` và `deliveringCount`, `consumerCount`, số producer/connection, gửi/nhận mỗi giây, p95/p99 `send` latency, p95 `receive` latency, heap/GC client, paging/disk I/O. Lưu ý `messageCount` có thể **bao gồm cả message đang delivering**; không lấy `messageCount - deliveringCount` làm công thức phổ quát cho backlog ở mọi phiên bản/topology mà không xác minh semantics.

### Kế hoạch benchmark có kiểm soát

| Tham số | Bộ thử A | Bộ thử B | Bộ thử C |
|---|---:|---:|---:|
| `consumerWindowSize` | 0 | 65536 | 1048576 |
| `producerWindowSize` | 16384 | 16384 | 16384 |
| Số consumer | 2 (một nhanh, một chậm) | 2 | 2 |
| Payload / tổng message | 2 KiB / 240 | Giữ nguyên | Giữ nguyên |
| Broker address policy | Không `BLOCK` | Giữ nguyên | Giữ nguyên |

Đo **tổng thời gian xử lý, độ lệch số message đã commit giữa fast/slow, heap client và số delivering**. Sau đó cố định consumer window và chỉ thay `producerWindowSize` ở thí nghiệm B. **Không thay đồng thời hai window** khi muốn suy ra nguyên nhân.

## 9. Những kết luận sai cần tránh

1. **“consumerWindowSize=0 thì consumer không nhận message.”** Sai: consumer vẫn nhận theo nhu cầu, chỉ không buffer trước nhiều message.
2. **“Cửa sổ 1 MiB tức là broker chỉ giao tối đa 1 MiB message toàn hệ thống.”** Sai: đó là kích thước tính **trên mỗi consumer** (với điều kiện và overhead riêng).
3. **“producerWindowSize là kích thước queue hoặc hạn mức disk.”** Sai: nó là ngân sách cấp credit khi producer gửi, không thay policy/persistence của address.
4. **“Đặt producerWindowSize=0 giống consumerWindowSize=0.”** Sai: `0` không hợp lệ cho API producer window này.
5. **“Cứ send block là network hỏng.”** Sai: broker có thể cố tình ngừng cấp credit vì `BLOCK` hoặc một nút thắt khác.
6. **“Tăng window chữa được message loss.”** Sai: reliability thuộc send confirmation, persistence, transaction và xử lý lỗi; flow control giải quyết sức chứa/tốc độ.
7. **“ACK = trả một credit.”** Sai: đơn vị credit là **byte**, việc replenish client-buffer và ACK/commit là hai trục xử lý khác nhau.
8. **“AMQP credit cũng tính bằng byte như Core.”** Sai: AMQP link credit thường tính theo **message**, cần tài liệu/gateway AMQP riêng.
9. **“Window đủ lớn thì không có backpressure.”** Sai: nó chỉ cho phép thêm dữ liệu in-flight trước khi giới hạn address/protocol khiến producer chậm lại.

## 10. Checklist trước khi áp dụng vào môi trường thực

- [ ] Đã xác định client dùng **Artemis Core**, không nhầm Classic OpenWire hoặc AMQP.
- [ ] `consumerWindowSize` được đặt theo throughput và tốc độ xử lý; tránh `-1` khi không có giới hạn dữ liệu và heap.
- [ ] Với competing consumers có tốc độ khác nhau, đã thử `consumerWindowSize=0` và đo fairness, throughput, `deliveringCount`.
- [ ] `producerWindowSize` là số byte dương; hiểu `-1` vô hiệu hóa producer window, `0` không hợp lệ.
- [ ] Nếu cần backpressure khi address đầy, đã khai báo tường minh `max-size-bytes` + `address-full-policy=BLOCK` và kiểm tra hành vi thực.
- [ ] Không dùng window thay quota bộ nhớ, durability, confirmation timeout, rate limit hoặc JMS transaction.
- [ ] Đã đo p95/p99 latency, throughput, heap, address size và paging trên đúng topology/container/storage.
- [ ] Mỗi worker dùng session/context riêng; shutdown/exception không làm mất message chưa commit.

**Kết luận:** `consumerWindowSize` quyết định khả năng **prefetch** từ broker vào Core consumer, ảnh hưởng hiệu năng và phân phối giữa các consumer. `producerWindowSize` quyết định lượng **byte credit** Core producer dùng khi gửi, ảnh hưởng mức dữ liệu in-flight và backpressure khi broker không cấp thêm credit. Hiểu đúng chiều và đơn vị của từng window, kết hợp với `address-full-policy` và kiểm chứng trên workload thật, là cách điều tiết lưu lượng mà không đánh đổi độ tin cậy.

## Tài liệu chính thức

1. [Apache Artemis 2.57.0 — Flow Control](https://artemis.apache.org/components/artemis/documentation/latest/flow-control.html): prefetch phía consumer, byte credit phía producer, `BLOCK`, rate limiting và khác biệt với AMQP.
2. [Apache Artemis 2.57.0 — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): `default-consumer-window-size`, `max-size-bytes`, `address-full-policy` và quy tắc match address.
3. [Apache Artemis 2.57.0 Javadoc — ActiveMQClient](https://artemis.apache.org/components/artemis/documentation/javadocs/javadoc-latest/org/apache/activemq/artemis/api/core/client/ActiveMQClient.html): hằng số `DEFAULT_CONSUMER_WINDOW_SIZE` và `DEFAULT_PRODUCER_WINDOW_SIZE`.
4. [Apache Artemis 2.57.0 Javadoc — ServerLocator](https://artemis.apache.org/components/artemis/documentation/javadocs/javadoc-latest/org/apache/activemq/artemis/api/core/client/ServerLocator.html): giá trị hợp lệ và setter `setConsumerWindowSize`/`setProducerWindowSize`.
5. [Apache Artemis — The Client Classpath](https://artemis.apache.org/components/artemis/documentation/latest/client-classpath.html): dependency `artemis-jakarta-client` tương ứng với `jakarta.jms`.
