# Thực hành giới hạn lưu lượng khi consumer chậm và backlog tăng

> **Chương:** Bài tập tổng hợp  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Mục tiêu:** Dựng một queue thử nghiệm, tạo tải nhanh hơn năng lực xử lý, đo backlog, giới hạn consumer bằng token bucket, sau đó bật broker back-pressure để producer bị điều tiết khi address gần đầy. Lab dùng Artemis 2.40.0, Java 17 và Jakarta JMS; cuối bài đối chiếu ActiveMQ Classic.

## 1. Bài toán và kết quả cần đạt

Một dịch vụ nhận 40 message/giây nhưng downstream database chỉ xử lý ổn định 5 message/giây. Nếu để consumer chạy hết tốc độ, database có thể quá tải; nếu cố định consumer ở 5 message/giây, backlog tăng khi producer tiếp tục gửi 40 message/giây.

Bài thực hành kiểm tra ba điều:

1. **Giới hạn tốc độ consumer:** ứng dụng chỉ nhận/xử lý tối đa một số message mỗi giây để bảo vệ downstream.
2. **Giới hạn message đang giữ:** prefetch/client window nhỏ để message không bị dồn vào bộ nhớ client ngoài khả năng quan sát.
3. **Back-pressure lên producer:** khi address chạm ngưỡng dung lượng, broker chặn send để producer tự giảm tốc; message không bị âm thầm bỏ.

Kết quả mong đợi:

- Consumer có tốc độ mục tiêu 5 message/giây trong khi producer gửi nhanh hơn.
- Queue depth và oldest-message age phản ánh backlog đang tăng hoặc giảm.
- Khi đạt ngưỡng **max-size-bytes**, Artemis **BLOCK** làm send của producer chờ đến khi dung lượng được giải phóng.
- Consumer lỗi xử lý rollback; broker redeliver và chuyển poison message tới DLQ theo policy.
- Phân biệt được **throttle, prefetch, broker flow control, paging và slow-consumer notification**.

Không đặt mục tiêu queue luôn bằng 0. Queue có thể có backlog có kiểm soát; điều quan trọng là backlog nằm trong capacity, age không vượt SLA và producer/consumer phản ứng đúng khi tải thay đổi.

## 2. Tính backlog trước khi chỉnh cấu hình

Ký hiệu:

- \(\lambda\): tốc độ message đến (arrival rate), message/giây.
- \(\mu\): tốc độ consumer hoàn tất (service rate), message/giây.
- \(B(t)\): số message chưa được xử lý tại thời điểm \(t\).

Khi producer và consumer chạy ổn định:

\[
\frac{dB}{dt} \approx \lambda - \mu
\]

Nếu \(\lambda > \mu\), backlog tăng. Nếu \(\lambda < \mu\), backlog giảm. Nếu hai tốc độ bằng nhau, hệ thống không có dư địa hấp thụ burst.

Ví dụ producer gửi 40 message/giây, consumer xử lý 5 message/giây:

\[
\Delta B = 40 - 5 = 35 \text{ message/giây}
\]

Sau 10 phút, nếu không có giới hạn khác:

\[
B \approx 35 \times 600 = 21.000 \text{ message}
\]

Khi producer dừng, consumer 5 message/giây cần:

\[
T_{\text{drain}} = \frac{21.000}{5} = 4.200 \text{ giây} = 70 \text{ phút}
\]

Nếu producer tiếp tục gửi 40 message/giây, consumer 5 message/giây **không bao giờ drain được backlog**. Tăng consumer rate, giảm producer rate, bổ sung capacity downstream hoặc chấp nhận load shedding là những quyết định phải có chủ đích.

### 2.1. Phân biệt backlog count và backlog age

Hai queue có cùng 10.000 message nhưng mức độ rủi ro khác nhau:

- Queue A nhận đều 100 message/giây và xử lý 100 message/giây: backlog có thể gần như không đổi.
- Queue B có 10.000 message cũ từ 30 phút trước, consumer gần như không tiến triển: đây là dấu hiệu tắc nghẽn.

Theo dõi tối thiểu:

| Chỉ số | Câu hỏi trả lời |
|---|---|
| Queue message count | Có bao nhiêu message đang chờ? |
| Oldest message age | Message cũ nhất đã chờ bao lâu? |
| Messages added/sec | Producer đang đưa vào bao nhiêu message/giây? |
| Messages acknowledged/sec | Consumer hoàn tất bao nhiêu message/giây? |
| Delivering count | Có bao nhiêu message đã dispatch nhưng chưa ACK? |
| Consumer count | Có bao nhiêu consumer đang hoạt động? |
| DLQ count | Có bao nhiêu message đã vượt retry policy? |

Queue depth giảm không nhất thiết có nghĩa business đã hoàn tất nếu message đang nằm trong trạng thái delivering/in-flight. Đối chiếu ACK rate và business commit rate.

## 3. Chọn đúng cơ chế điều tiết

Các cơ chế sau giải quyết những điểm khác nhau; không thay thế lẫn nhau.

| Cơ chế | Giới hạn cái gì? | Nơi cấu hình | Tác dụng |
|---|---|---|---|
| Application token bucket | Tốc độ consumer xử lý | Consumer application | Bảo vệ DB/API hoặc downstream |
| Producer rate limiter | Tốc độ message được gửi | Producer application/gateway | Làm phẳng ingress trước khi broker nhận |
| Consumer prefetch/window | Số/bytes message broker đẩy trước tới client | JMS client | Giới hạn in-flight và buffer phía client |
| Artemis address BLOCK | Dung lượng address trước khi producer bị chặn | Broker address-settings | Back-pressure từ broker về producer |
| Artemis PAGE | Dung lượng giữ trong memory trước khi page ra disk | Broker | Cho phép tiếp tục nhận tải nhưng dùng disk |
| Slow-consumer detection | Phát hiện consumer thấp hơn ngưỡng | Broker monitoring | Notification/policy; không tự đặt tốc độ mong muốn |
| Autoscaling | Số consumer instance | Platform/orchestrator | Tăng capacity nếu downstream cho phép |

### 3.1. Token bucket

Token bucket nạp token với tốc độ \(r\) token/giây, giới hạn số token tích lũy ở capacity \(C\). Mỗi message cần một token. Khi không còn token, consumer chờ đến khi có token mới.

Với \(r=5\) message/giây và \(C=1\), consumer bắt đầu xử lý ngay một message rồi trung bình chờ khoảng 200 ms giữa các lần nhận tiếp theo. Capacity 1 giảm burst; capacity lớn hơn cho phép xử lý một burst ngắn nhưng vẫn giữ tốc độ trung bình dài hạn.

### 3.2. Prefetch không phải rate limit

Prefetch/window điều khiển số message broker có thể giao trước cho client. Nó không đảm bảo consumer xử lý đúng 5 message/giây.

Nếu client nhận trước hàng trăm message rồi giữ trong memory, queue depth phía broker có thể thấp hơn số công việc thực sự chưa xử lý. Với consumer chậm, giảm prefetch/window giúp giảm lượng message in-flight, hạn chế buffer phía client và làm queue metrics phản ánh backlog rõ hơn.

Đổi lại, window quá nhỏ có thể tăng round-trip và giảm throughput tối đa. Trong lab, dùng window 0 để quan sát rõ; production nên benchmark một giá trị nhỏ phù hợp payload, latency và số consumer.

### 3.3. Broker back-pressure

Artemis **address-full-policy=BLOCK** chặn producer khi address đạt ngưỡng **max-size-bytes**. Khi consumer ACK và broker giải phóng dung lượng, producer có thể tiếp tục gửi.

**PAGE** có semantics khác: broker ghi message ra page store để tiếp tục nhận tải. Nó bảo vệ memory nhưng **không giới hạn tốc độ ingress**; backlog vẫn có thể lớn lên trên disk. **DROP** loại message và **FAIL** từ chối send khi đầy; chỉ dùng khi business contract cho phép.

### 3.4. Slow-consumer detection không phải throttle

Artemis có thể kiểm tra tốc độ consumer và phát notification hoặc xử lý consumer bị coi là chậm. **NOTIFY** hỗ trợ quan sát; nó không tự giới hạn consumer ở 5 message/giây. Token bucket trong ứng dụng mới là cơ chế đặt rate mục tiêu trong bài lab này.

## 4. Kiến trúc lab

~~~mermaid
flowchart LR
    P["Producer<br/>burst hoặc 20 msg/s"] --> A["Artemis address lab.slow<br/>ANYCAST queue"]
    A --> Q["Queue backlog"]
    Q --> C["Consumer<br/>token bucket 5 msg/s"]
    C --> DB["Downstream giả lập<br/>50 ms/message"]
    A -. "max-size-bytes + BLOCK" .-> P
    A -. "slow consumer NOTIFY" .-> M["Management / metrics"]
    C -. "rollback sau lỗi" .-> DLQ["DLQ sau max delivery attempts"]
~~~

Thành phần:

- Broker Artemis 2.40.0, queue **lab.slow**.
- Producer có hai mode: gửi burst và gửi liên tục.
- Một consumer transacted, token bucket 5 message/giây, xử lý giả lập 50 ms/message.
- Address policy có giới hạn dung lượng, BLOCK, slow-consumer notification và DLQ.
- Metrics lấy từ Artemis management/console hoặc JMX/Prometheus integration đang dùng.

Bài lab chạy trên broker riêng. Không thử làm đầy address production hoặc cố tình làm chậm consumer đang phục vụ nghiệp vụ thật.

## 5. Provision queue và policy trên Artemis

Trong **broker.xml**, hợp nhất các fragment sau vào phần **core** hiện hữu. Nếu queue/address đã được provision bằng management API hoặc automation, tránh tạo trùng.

### 5.1. ANYCAST address và queue

~~~xml
<addresses>
    <address name="lab.slow">
        <anycast>
            <queue name="lab.slow"/>
        </anycast>
    </address>

    <address name="DLQ.lab">
        <anycast>
            <queue name="DLQ.lab"/>
        </anycast>
    </address>
</addresses>
~~~

ANYCAST phù hợp với queue worker pool: các consumer cạnh tranh trên cùng backlog, mỗi message được giao cho một consumer tại một thời điểm.

### 5.2. Giới hạn address và producer back-pressure

~~~xml
<address-settings>
    <address-setting match="lab.slow">
        <max-size-bytes>1048576</max-size-bytes>
        <address-full-policy>BLOCK</address-full-policy>

        <max-delivery-attempts>5</max-delivery-attempts>
        <redelivery-delay>1000</redelivery-delay>
        <dead-letter-address>DLQ.lab</dead-letter-address>

        <slow-consumer-check-period>5</slow-consumer-check-period>
        <slow-consumer-threshold>8</slow-consumer-threshold>
        <slow-consumer-policy>NOTIFY</slow-consumer-policy>
    </address-setting>
</address-settings>
~~~

Giải thích:

- **max-size-bytes=1048576:** ngưỡng dung lượng address khoảng 1 MiB cho lab. Đây không phải quota chính xác theo kích thước payload; broker còn có message/reference overhead.
- **address-full-policy=BLOCK:** producer chịu back-pressure khi address đầy. Producer send có thể chờ cho đến khi dung lượng được giải phóng.
- **max-delivery-attempts=5:** sau số lần delivery tối đa theo policy, message lỗi được chuyển tới dead-letter address.
- **redelivery-delay=1000:** đợi khoảng 1 giây trước redelivery.
- **slow-consumer-check-period=5:** chu kỳ kiểm tra slow consumer, tính bằng giây.
- **slow-consumer-threshold=8:** ngưỡng tốc độ consumer, tính bằng message/giây.
- **slow-consumer-policy=NOTIFY:** phát notification để operator quan sát consumer chậm; không throttle consumer.

Với consumer được giới hạn 5 message/giây, ngưỡng 8 có thể làm broker đánh dấu nó chậm theo policy/version đang dùng. Nếu không muốn notification trong bài đo rate, tăng threshold hoặc tạm bỏ phần slow-consumer settings. Đừng nhầm notification với lỗi xử lý.

### 5.3. Kiểm tra routing và policy

Sau khi restart/reload theo quy trình broker:

1. Xác nhận **lab.slow** là queue ANYCAST.
2. Xác nhận queue được bind vào address **lab.slow**.
3. Xác nhận address settings match đúng **lab.slow**.
4. Xác nhận user lab có quyền send/consume và xem management metrics.
5. Xác nhận DLQ tồn tại và có quyền browse.

Không bật auto-create rộng chỉ để bài lab chạy được; provision destination rõ ràng giúp tránh gõ sai tên và tạo queue ngoài ý muốn.

## 6. Tạo project Java/Jakarta JMS

Dùng Java 17, Jakarta JMS 3.1 và Artemis Jakarta client 2.40.0.

Cấu trúc:

~~~text
slow-consumer-lab/
├── pom.xml
└── src/main/java/lab/SlowConsumerLab.java
~~~

**pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lab</groupId>
    <artifactId>slow-consumer-lab</artifactId>
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

## 7. Viết producer và consumer có giới hạn tốc độ

Tạo file **src/main/java/lab/SlowConsumerLab.java**:

~~~java
package lab;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class SlowConsumerLab {
    private static final String QUEUE = "lab.slow";

    private SlowConsumerLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "burst [count] [bodyBytes] | stream [count] [bodyBytes] [intervalMs]"
                    + " | consume [messagesPerSecond]");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL",
                "tcp://127.0.0.1:61616?consumerWindowSize=0");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        try {
            switch (args[0]) {
                case "burst" -> send(
                        factory, user, password,
                        intArg(args, 1, 200),
                        intArg(args, 2, 2048),
                        0);
                case "stream" -> send(
                        factory, user, password,
                        intArg(args, 1, 600),
                        intArg(args, 2, 1024),
                        intArg(args, 3, 50));
                case "consume" -> consume(
                        factory, user, password,
                        doubleArg(args, 1, 5.0));
                default -> throw new IllegalArgumentException(
                        "Unknown mode: " + args[0]);
            }
        } finally {
            factory.close();
        }
    }

    private static void send(
            ConnectionFactory factory,
            String user,
            String password,
            int count,
            int bodyBytes,
            int intervalMs) throws Exception {

        if (count <= 0 || bodyBytes <= 0 || intervalMs < 0) {
            throw new IllegalArgumentException("Invalid producer arguments");
        }

        String runId = UUID.randomUUID().toString();
        String body = "x".repeat(bodyBytes);
        long started = System.nanoTime();

        try (JMSContext context = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(QUEUE);
            var producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT);

            for (int i = 1; i <= count; i++) {
                TextMessage message = context.createTextMessage(body);
                message.setStringProperty("eventId", runId + "-" + i);
                message.setIntProperty("sequence", i);
                message.setLongProperty(
                        "publishedAt", System.currentTimeMillis());

                // Không dùng một JMS transaction lớn cho toàn bộ stream:
                // message đã gửi có thể được consumer xử lý ngay.
                producer.send(queue, message);

                if (intervalMs > 0) {
                    Thread.sleep(intervalMs);
                }
            }
        }

        double elapsedSeconds =
                (System.nanoTime() - started) / 1_000_000_000.0;
        System.out.printf(
                "PRODUCER_DONE runId=%s count=%d elapsed=%.2fs rate=%.2f msg/s%n",
                runId, count, elapsedSeconds, count / elapsedSeconds);
    }

    private static void consume(
            ConnectionFactory factory,
            String user,
            String password,
            double messagesPerSecond) throws Exception {

        if (messagesPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "messagesPerSecond must be positive");
        }

        TokenBucket limiter = new TokenBucket(messagesPerSecond, 1.0);

        try (JMSContext context = factory.createContext(
                    user, password, JMSContext.SESSION_TRANSACTED);
             JMSConsumer consumer = context.createConsumer(
                    context.createQueue(QUEUE))) {

            System.out.printf(
                    "CONSUMER_READY queue=%s limit=%.2f msg/s%n",
                    QUEUE, messagesPerSecond);

            while (!Thread.currentThread().isInterrupted()) {
                // Lấy permit trước receive để không chủ động giữ thêm
                // message in-flight trong lúc đang chờ token.
                limiter.acquire();

                Message message = consumer.receive(1000);
                if (message == null) {
                    continue;
                }

                String eventId = message.getStringProperty("eventId");
                int sequence = message.getIntProperty("sequence");

                try {
                    process(message);
                    context.commit();

                    System.out.printf(
                            "ACK eventId=%s sequence=%d deliveryCount=%d%n",
                            eventId, sequence, deliveryCount(message));
                } catch (Exception processingFailure) {
                    context.rollback();
                    System.err.printf(
                            "ROLLBACK eventId=%s reason=%s%n",
                            eventId, processingFailure.getMessage());
                    Thread.sleep(500);
                }
            }
        }
    }

    private static void process(Message message) throws Exception {
        // Giả lập DB/API mất 50 ms. Rate limiter 5 msg/s sẽ chậm hơn
        // năng lực giả lập này và là giới hạn chi phối.
        Thread.sleep(50);

        if (message.propertyExists("forceFailure")
                && message.getBooleanProperty("forceFailure")) {
            throw new IllegalStateException("Injected processing failure");
        }
    }

    private static int deliveryCount(Message message) throws Exception {
        return message.propertyExists("JMSXDeliveryCount")
                ? message.getIntProperty("JMSXDeliveryCount")
                : 1;
    }

    private static int intArg(
            String[] args, int index, int defaultValue) {
        return args.length > index
                ? Integer.parseInt(args[index])
                : defaultValue;
    }

    private static double doubleArg(
            String[] args, int index, double defaultValue) {
        return args.length > index
                ? Double.parseDouble(args[index])
                : defaultValue;
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return value;
    }

    private static final class TokenBucket {
        private final double ratePerSecond;
        private final double capacity;
        private final Object lock = new Object();

        private double tokens;
        private long lastRefillNanos = System.nanoTime();

        private TokenBucket(double ratePerSecond, double capacity) {
            if (ratePerSecond <= 0 || capacity < 1) {
                throw new IllegalArgumentException(
                        "Rate must be positive and capacity >= 1");
            }
            this.ratePerSecond = ratePerSecond;
            this.capacity = capacity;
            this.tokens = capacity;
        }

        private void acquire() throws InterruptedException {
            while (true) {
                long waitNanos;

                synchronized (lock) {
                    long now = System.nanoTime();
                    double elapsedSeconds =
                            (now - lastRefillNanos) / 1_000_000_000.0;

                    tokens = Math.min(
                            capacity,
                            tokens + elapsedSeconds * ratePerSecond);
                    lastRefillNanos = now;

                    if (tokens >= 1.0) {
                        tokens -= 1.0;
                        return;
                    }

                    waitNanos = (long) Math.ceil(
                            (1.0 - tokens) * 1_000_000_000.0
                                    / ratePerSecond);
                }

                TimeUnit.NANOSECONDS.sleep(Math.max(1L, waitNanos));
            }
        }
    }
}
~~~

### 7.1. Cách token bucket hoạt động

- **ratePerSecond=5:** tốc độ nạp 5 token/giây.
- **capacity=1:** bucket chứa tối đa một token, hạn chế burst.
- **acquire()** lấy một token trước khi gọi receive.
- Nếu chưa có token, consumer ngủ đúng khoảng thời gian cần thiết rồi thử lại.
- Khi xử lý thành công, consumer commit JMS transaction.
- Khi xử lý lỗi, consumer rollback để broker redeliver theo policy.

Limiter trong ví dụ là **per process**. Nếu chạy 4 consumer instance, mỗi instance 5 message/giây thì tổng rate có thể gần 20 message/giây. Muốn giới hạn toàn hệ thống ở 5 message/giây, cần chia quota theo replica hoặc dùng distributed rate limiter/quota service. Autoscaling cũng làm tổng rate thay đổi nếu không tính lại quota.

### 7.2. Vì sao permit được lấy trước receive?

Nếu nhận message trước rồi mới chờ token, consumer đã giữ delivery trong transaction/in-flight trong lúc chờ. Nhiều consumer có thể giữ nhiều message như vậy, khiến message không được worker khác xử lý và làm tăng delivering count.

Lấy permit trước receive làm cho ứng dụng chỉ xin message khi có capacity xử lý. Kết hợp Artemis **consumerWindowSize=0** trong lab để giảm client-side buffering. Production có thể dùng window nhỏ thay vì 0 sau khi benchmark round-trip và throughput.

### 7.3. Ranh giới transaction

**context.commit()** xác nhận transaction JMS của session. Nó không tự commit transaction DB hoặc HTTP side effect. Nếu DB đã commit nhưng JMS commit chưa thành công, message có thể redeliver. Consumer production cần inbox/idempotency theo **eventId**, hoặc mô hình tích hợp transaction phù hợp; không dựa vào token bucket để chống duplicate.

## 8. Chạy lab và quan sát backlog

### 8.1. Cấu hình môi trường

PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616?consumerWindowSize=0"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "LAB_ONLY_PASSWORD"

mvn -q -DskipTests package
~~~

Đảm bảo queue **lab.slow** và policy Artemis ở mục 5 đã được nạp.

### 8.2. Thử A — gửi burst rồi xử lý ở 5 message/giây

Terminal 1, gửi 200 message, mỗi body khoảng 2 KiB:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.SlowConsumerLab" "-Dexec.args=burst 200 2048"
~~~

Terminal 2, bắt đầu consumer giới hạn 5 message/giây:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.SlowConsumerLab" "-Dexec.args=consume 5"
~~~

Quan sát:

- Producer hoàn tất nhanh hơn consumer.
- Queue message count ban đầu tăng gần 200 rồi giảm dần.
- ACK rate của consumer gần 5 message/giây, thấp hơn năng lực giả lập 20 message/giây do sleep 50 ms.
- Nếu không có producer mới, backlog drain trong khoảng 40 giây (200 / 5), cộng overhead khởi động/commit.
- Oldest-message age tăng trong lúc chờ rồi giảm về 0 khi queue drain.

Không dùng số liệu thời gian của một lần chạy làm benchmark. JVM warm-up, disk, broker load và scheduler đều ảnh hưởng kết quả.

### 8.3. Thử B — ingress liên tục cao hơn consumer

Dừng hoặc để consumer chạy, rồi mở Terminal 3:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.SlowConsumerLab" "-Dexec.args=stream 600 1024 50"
~~~

Producer gửi khoảng 20 message/giây trong 30 giây. Consumer xử lý 5 message/giây.

Ước lượng backlog tăng:

\[
(20 - 5) \times 30 = 450 \text{ message}
\]

Nếu producer kết thúc, consumer cần khoảng 90 giây để xử lý 450 message. Nếu tiếp tục gửi 20 message/giây, backlog vẫn tăng khoảng 15 message/giây.

Ghi lại queue depth mỗi 5 giây. Tính slope:

\[
\text{backlog slope} =
\frac{B(t_2)-B(t_1)}{t_2-t_1}
\]

Slope dương kéo dài cho thấy ingress đang lớn hơn service rate. Slope âm cho thấy consumer đang drain backlog.

### 8.4. Thử C — quan sát broker BLOCK producer

Thử này mô phỏng address gần đầy. Trên broker lab, tạm hạ:

~~~xml
<max-size-bytes>262144</max-size-bytes>
<address-full-policy>BLOCK</address-full-policy>
~~~

Dừng consumer, sau đó chạy producer burst với payload lớn hơn:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.SlowConsumerLab" "-Dexec.args=burst 200 4096"
~~~

Producer có thể dừng tiến triển ở send khi address đầy. Đây là dấu hiệu back-pressure; vì producer không dùng một JMS transaction lớn, các message đã được broker nhận vẫn có thể được consumer đọc.

Bây giờ khởi động consumer:

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.SlowConsumerLab" "-Dexec.args=consume 5"
~~~

Khi consumer ACK và broker giải phóng dung lượng, producer có thể tiếp tục gửi. Quan sát thời gian producer hoàn tất dài hơn và queue depth không vượt ngưỡng một cách không kiểm soát.

Kết thúc thử nghiệm, khôi phục **max-size-bytes** về giá trị phù hợp, ví dụ 1 MiB. Không để ngưỡng 256 KiB chỉ vì nó giúp lab dễ nhìn; production cần sizing theo peak traffic và outage window.

### 8.5. Thử D — so sánh PAGE và BLOCK

Trên môi trường lab, thay policy lần lượt:

~~~xml
<address-full-policy>PAGE</address-full-policy>
~~~

và:

~~~xml
<address-full-policy>BLOCK</address-full-policy>
~~~

Với PAGE, broker có thể page message ra disk để tiếp tục nhận producer traffic. Producer ít bị chặn hơn nhưng disk usage và backlog vẫn có thể tăng. Với BLOCK, producer bị chặn khi address đầy và chỉ tiếp tục khi consumer giải phóng capacity.

Không so sánh hai policy chỉ bằng producer send latency. Ghi thêm disk/page usage, queue depth, oldest age, producer blocked time và thời gian drain.

## 9. Đo và diễn giải metrics

Dùng Artemis management console, JMX hoặc metrics integration đang có để lấy chỉ số queue/address. Tên metric cụ thể có thể khác theo exporter/version; ánh xạ về các khái niệm sau:

| Metric | Đo ở đâu | Diễn giải |
|---|---|---|
| messageCount | Queue | Message đang chờ |
| deliveringCount | Queue | Message đã dispatch nhưng chưa ACK |
| consumerCount | Queue | Số consumer đang đăng ký |
| messagesAdded | Queue | Tổng message được thêm |
| messagesAcknowledged | Queue | Tổng message đã ACK |
| Address size/usage | Address | Dung lượng address và thời điểm chạm ngưỡng |
| Page bytes / disk free | Broker/storage | Backlog đang chiếm bao nhiêu disk |
| Producer blocked time | Client/app metric | Producer bị flow control bao lâu |
| Oldest message age | App/management metric | Message cũ nhất chờ bao lâu |
| Processing latency | Consumer | Thời gian xử lý business |

Tốc độ trong một cửa sổ đo:

\[
\lambda \approx
\frac{\Delta messagesAdded}{\Delta t}
\]

\[
\mu \approx
\frac{\Delta messagesAcknowledged}{\Delta t}
\]

Nếu \(\lambda > \mu\), backlog sẽ tăng trừ khi có expiry, DLQ, purge hoặc cơ chế loại message khác. Vì vậy, khi thấy queue depth giảm, kiểm tra xem message được ACK hay bị chuyển DLQ/expiry.

### 9.1. Phân biệt queue backlog và in-flight

Nếu messageCount giảm nhưng deliveringCount tăng, broker đã dispatch message ra consumer/client nhưng chúng chưa ACK. Đây không phải business completion.

Với consumer window lớn, nhiều message có thể nằm trong client buffer. Để điều tra:

- Giảm window/prefetch tạm thời.
- So sánh messageCount + deliveringCount.
- Theo dõi ACK rate và business commit rate.
- Kiểm tra consumer thread có đang block ở DB/API không.

### 9.2. Cảnh báo theo slope và age

Rule cảnh báo có ích thường kết hợp:

- Queue depth vượt ngưỡng trong một khoảng thời gian.
- Backlog slope dương liên tục.
- Oldest-message age vượt SLA.
- ACK rate thấp hơn ingress rate.
- Delivering count cao trong khi ACK rate thấp.
- Disk/page usage tiến gần watermark.
- Producer blocked time tăng kéo dài.

Không chỉ cảnh báo khi queue depth vượt một con số cố định. Một queue xử lý 50.000 message/giây có thể có depth 10.000 bình thường; queue xử lý 2 message/giây với depth 1.000 có thể đã quá SLA.

## 10. Tuning theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động |
|---|---|---|
| Queue tăng đều, consumer ACK rate ổn định thấp | \(\lambda > \mu\) | Giảm producer rate, tăng capacity downstream hoặc thay đổi SLA |
| Queue depth thấp nhưng delivering cao | Prefetch/window lớn hoặc handler giữ message | Giảm consumer window, kiểm tra transaction duration |
| Producer send bị block | Address đầy, consumer không drain | Kiểm tra BLOCK, consumer health, disk/flow-control |
| PAGE bytes tăng liên tục | Ingress lớn hơn egress | Giới hạn producer, tăng consumer capacity có kiểm soát, đặt disk watermark |
| Consumer rate thấp hơn token limit | DB/API chậm hoặc processing time dài | Profiling downstream, tối ưu batch/query, không tăng token mù quáng |
| Nhiều redelivery/DLQ | Handler lỗi, rollback hoặc poison message | Phân loại lỗi, retry/backoff, sửa payload/consumer |
| Consumer tăng nhưng throughput không tăng | Downstream bottleneck, hot key hoặc lock contention | Kiểm tra DB pool, partition/group và concurrency |
| Producer block quá lâu | Không còn consumer, queue đầy hoặc address policy sai | Alert, dừng ingress có kiểm soát, khôi phục consumer |

### 10.1. Chọn rate mục tiêu

Không chọn rate chỉ dựa vào khả năng broker. Đo downstream:

- Database transaction/giây ổn định.
- API quota/rate limit.
- Thread pool và connection pool.
- p95/p99 latency khi tăng concurrency.
- Error/timeout rate khi tải tăng.

Nếu downstream ổn định ở 30 transaction/giây và có 3 consumer instance, có thể chia quota 10 message/giây mỗi instance làm điểm khởi đầu. Sau đó benchmark và điều chỉnh theo p95/p99 cùng backlog age.

### 10.2. Rate limit theo tenant hoặc loại công việc

Một token bucket toàn queue có thể để tenant tải lớn chiếm toàn bộ capacity. Nếu cần fairness, tách queue theo tenant/class hoặc dùng scheduler/quota riêng. Selector chỉ lọc message; nó không tự bảo đảm mỗi tenant có một phần capacity.

### 10.3. Autoscaling không được vượt downstream quota

Nếu backlog tăng, autoscaler có thể tăng consumer replicas. Nhưng nếu mỗi replica có token bucket riêng, tổng rate tăng theo số replica. Cần:

\[
r_{\text{instance}} =
\frac{r_{\text{global}}}{N_{\text{replicas}}}
\]

hoặc dùng limiter phân tán để duy trì quota toàn cục. Khi scale down, bảo đảm consumer đóng session/rollback delivery đang xử lý đúng cách.

## 11. Đối chiếu ActiveMQ Classic

Bài lab Java dùng Artemis Jakarta client. Với Classic, ý tưởng token bucket ở application vẫn áp dụng, nhưng client/broker controls có tên và semantics khác.

### 11.1. Prefetch policy của Classic

Classic client có prefetch theo số message. Ví dụ đặt queue prefetch thấp trong broker URL:

~~~text
tcp://classic-broker:61616?jms.prefetchPolicy.queuePrefetch=1
~~~

Giá trị 1 giúp consumer chỉ giữ rất ít message chưa xử lý phía client, phù hợp khi xử lý lâu hoặc cần phân phối công việc đều. Đây là prefetch count, không phải giới hạn message/giây. Tăng prefetch có thể cải thiện throughput khi network latency cao nhưng làm tăng in-flight và có thể giảm fairness.

### 11.2. Producer flow control của Classic

Mảnh policy minh họa trong activemq.xml:

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">"
                         producerFlowControl="true"
                         memoryLimit="1mb"/>
        </policyEntries>
    </policyMap>
</destinationPolicy>
~~~

producerFlowControl và memoryLimit điều tiết producer khi destination usage chạm giới hạn. Kết quả cụ thể phụ thuộc broker usage limits, store/temp usage và client send behavior. Kiểm tra systemUsage, destination policy và producer logs trên đúng Classic release.

Classic queue prefetch và Artemis consumer window không cùng đơn vị: Classic thường tính theo **số message**, Artemis consumerWindowSize tính theo **byte**. Không chuyển nguyên giá trị số từ cấu hình này sang cấu hình kia.

## 12. Bài tập mở rộng

### Bài 1 — Tìm điểm cân bằng

Giữ producer 20 message/giây. Chạy consumer lần lượt ở 2, 5, 10 và 25 message/giây. Mỗi lượt ghi queue depth, oldest age, ACK rate và thời gian drain.

**Câu hỏi:** mức nào làm backlog tăng, mức nào drain được và mức nào khiến downstream giả lập bắt đầu chậm?

### Bài 2 — Burst capacity

Giữ rate 5 message/giây nhưng thay token bucket capacity từ 1 lên 10 rồi 50.

**Câu hỏi:** tốc độ trung bình có đổi không? Burst ban đầu và queue latency p99 thay đổi ra sao?

### Bài 3 — Prefetch/window

Chạy consumer window 0, 10 KiB, 100 KiB và 1 MiB. Không thay token bucket.

**Câu hỏi:** delivering count và queue message count thay đổi ra sao? Khi consumer dừng đột ngột, lượng message phải redeliver có khác không?

### Bài 4 — Nhiều consumer instance

Chạy 3 process, mỗi process giới hạn 5 message/giây.

**Câu hỏi:** tổng ACK rate có thể đạt gần bao nhiêu? Nếu downstream chỉ cho phép 8 message/giây, cần phân phối quota thế nào?

### Bài 5 — Poison message

Sửa producer để một message có property forceFailure=true; consumer rollback message đó.

**Câu hỏi:** JMSXDeliveryCount tăng ra sao? Khi vượt max-delivery-attempts, message đi đâu? Có cần tách DLQ theo tenant/event type không?

### Bài 6 — Producer BLOCK

Hạ max-size-bytes xuống 256 KiB, dừng consumer và gửi payload lớn. Sau khi producer bị block, bật consumer.

**Câu hỏi:** producer send tiếp tục lúc nào? BLOCK khác PAGE thế nào về disk usage và producer latency?

## 13. Ma trận nghiệm thu

| ID | Kịch bản | PASS khi |
|---|---|---|
| RATE-01 | Consumer token bucket 5 msg/s | ACK rate ổn định xấp xỉ mục tiêu sau warm-up |
| RATE-02 | Capacity 1 so với capacity 20 | Burst behavior đúng với cấu hình bucket |
| RATE-03 | Nhiều consumer instance | Tổng rate phản ánh tổng quota, không nhầm per-process với global |
| BACKLOG-01 | Producer 20/s, consumer 5/s | Backlog slope xấp xỉ +15 msg/s trong cửa sổ ổn định |
| BACKLOG-02 | Dừng producer | Backlog giảm và drain time gần B/μ |
| PREFETCH-01 | Artemis window 0 | Delivering/client buffer được giới hạn; throughput trade-off được ghi |
| PREFETCH-02 | Classic queue prefetch 1 | Consumer giữ ít message in-flight phía client |
| FLOW-01 | Artemis address BLOCK | Producer send bị back-pressure khi address đầy và tiếp tục khi có capacity |
| FLOW-02 | Artemis PAGE | Producer tiếp tục nhận tải trong khi page/disk usage tăng |
| FLOW-03 | Classic producerFlowControl | Producer chịu flow control theo destination/system usage policy |
| SLOW-01 | Consumer dưới slow-consumer threshold | Broker phát notification theo cấu hình; không coi đó là throttle |
| DLQ-01 | Consumer rollback poison message | Redelivery tăng và message chuyển DLQ sau policy |
| OBS-01 | Queue metrics | Có messageCount, deliveringCount, consumerCount, added/acknowledged rate |
| OBS-02 | Backlog age | Alert phát hiện message cũ vượt SLA |
| SAFE-01 | Consumer crash/restart | Message chưa commit được redeliver; business effect idempotent |

PASS cần dựa trên số đo và event ID, không chỉ dựa trên việc chương trình không ném exception.

## 14. Lỗi thường gặp trong bài lab

- **Đặt token bucket sau receive:** consumer đã giữ message trong khi chờ token; delivering count tăng dù business không tiến triển.
- **Prefetch quá lớn:** client giữ nhiều message ngoài queue depth, che khuất backlog và giảm fairness.
- **Dùng PAGE rồi nghĩ đã giới hạn backlog:** PAGE chỉ chuyển tải sang disk; disk vẫn có thể đầy.
- **Dùng BLOCK mà không có alert:** producer có thể chờ lâu và request thread cạn.
- **Tăng consumer replicas không tính global quota:** tổng rate vượt khả năng DB/API.
- **Commit JMS trước business DB:** message biến mất khỏi queue dù business update chưa bền vững.
- **Rollback mọi lỗi vô hạn:** poison message tạo redelivery storm; phải có max attempts, backoff và DLQ.
- **Chỉ nhìn queue depth:** bỏ qua delivering count, ACK rate, oldest age và expiry/DLQ.
- **Dùng consumer rate limit để xử lý producer burst không giới hạn:** backlog vẫn tăng; cần producer shaping hoặc broker back-pressure.
- **Bật slow-consumer KILL để thay token bucket:** consumer bị ngắt, không được điều tiết theo rate nghiệp vụ.

## 15. Checklist vận hành sau bài thực hành

- [ ] Đã đo ingress rate và ACK/business completion rate riêng.
- [ ] Đã tính backlog growth và thời gian drain theo tải thực.
- [ ] Token bucket có rate và burst capacity phù hợp downstream.
- [ ] Đã xác định limiter là per-process hay global.
- [ ] Consumer window/prefetch đủ nhỏ để kiểm soát in-flight.
- [ ] Transaction chỉ commit sau khi xử lý thành công; DB side effect có idempotency.
- [ ] Artemis max-size-bytes và address-full-policy có headroom rõ.
- [ ] Đã phân biệt BLOCK, PAGE, DROP và FAIL.
- [ ] Slow-consumer notification được dùng cho monitoring, không nhầm là rate limiter.
- [ ] Có DLQ, max delivery attempts và redelivery delay.
- [ ] Có dashboard queue depth, delivering, consumer count, ingress/ACK rate, oldest age, disk/page và producer blocked time.
- [ ] Có alert theo backlog slope, age và storage watermark.
- [ ] Có quy trình giảm ingress hoặc dừng producer khi downstream không phục hồi.
- [ ] Đã thử burst, continuous load, consumer restart và producer back-pressure trên môi trường lab.

## 16. Kết luận

Khi consumer chậm, queue backlog tăng theo chênh lệch giữa ingress rate và service rate. **Token bucket** đặt giới hạn tốc độ xử lý của ứng dụng; **prefetch/window** giới hạn message được giữ trước ở client; **Artemis BLOCK** truyền back-pressure về producer khi address đầy. **PAGE** bảo vệ memory bằng disk nhưng không làm backlog biến mất, còn slow-consumer NOTIFY là tín hiệu quan sát chứ không phải throttle.

Bài lab chứng minh được cả chiều consumer và producer: consumer xử lý ở tốc độ đã chọn, queue age/depth phản ánh tải chờ, producer bị chặn khi broker hết capacity và tiếp tục khi consumer giải phóng dung lượng. Trong production, kết hợp rate limit theo quota downstream, bounded in-flight, broker storage watermark, DLQ/idempotency và metrics theo backlog slope để hệ thống hấp thụ burst mà không làm quá tải dịch vụ phụ thuộc.
