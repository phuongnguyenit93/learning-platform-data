# So sánh Classic và Artemis với cùng ngữ nghĩa bảo đảm và điều kiện đo

## 1. Benchmark broker phải so sánh cùng một hợp đồng xử lý

Một phép đo “Classic xử lý được 80.000 message/s, Artemis 120.000 message/s” không có nhiều giá trị nếu hai bên đang dùng **ngữ nghĩa giao nhận khác nhau**. Ví dụ, một bên gửi message persistent và chờ transaction commit xuống journal, bên kia gửi non-persistent hoặc bật asynchronous send; kết quả cao hơn có thể chỉ phản ánh mức bảo đảm thấp hơn.

Bài toán so sánh **ActiveMQ Classic** và **ActiveMQ Artemis** phải đặt trên một workload có điều kiện tương đương:

- Cùng **delivery mode**, queue durability, transaction boundary và ACK semantics.
- Cùng số producer/consumer, payload, batch size, concurrency và thời gian chạy.
- Cùng yêu cầu về **message ordering, redelivery và persistence** trong từng scenario.
- Cùng phần cứng, filesystem, storage, JVM, network và trạng thái broker.
- Đo riêng **producer commit throughput**, **consumer commit throughput**, **end-to-end latency**, tài nguyên và độ ổn định.

Không có một con số benchmark đại diện cho mọi hệ thống. Một queue nhỏ với message 100 byte, một luồng 10 producer và một queue có payload 64 KiB, transaction batch 500, nhiều consumer là hai workload rất khác nhau. Kết luận phải gắn với **scenario, cấu hình, phiên bản và điều kiện đo cụ thể**.

~~~mermaid
flowchart TD
    SPEC["Định nghĩa semantics và SLA"] --> ENV["Cố định môi trường, broker và storage"]
    ENV --> LOAD["Cùng workload: producer, consumer, payload, batch"]
    LOAD --> RUN["Warm-up + nhiều lần đo độc lập"]
    RUN --> METRIC["Throughput, latency, backlog, CPU, disk, GC"]
    METRIC --> VALID["Kiểm tra message count, sequence, redelivery, persistence"]
    VALID --> COMPARE["So sánh theo từng scenario và percentile"]
    COMPARE --> REPORT["Báo cáo kết quả kèm cấu hình và giới hạn"]
~~~

Trong module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**, Classic và Artemis đều được nghiên cứu về queue/topic, routing, JMS, transaction, acknowledgment, redelivery, bảo mật và vận hành. Bài này tập trung vào **điều kiện benchmark công bằng**: không dùng thông số throughput đơn lẻ để suy ra broker nào luôn nhanh hơn.

## 2. Chốt ngữ nghĩa bảo đảm trước khi đo

Một baseline phù hợp cho bài so sánh persistent queue:

| Thuộc tính | Giá trị baseline | Điều cần giữ tương đương |
| --- | --- | --- |
| Destination | Queue ANYCAST/queue | Một message được một consumer xử lý trong mô hình queue |
| Queue durability | Durable queue | Queue tồn tại qua broker restart theo cấu hình |
| Message delivery | **PERSISTENT** | Broker lưu message theo chính sách persistence |
| Producer transaction | **JMS transacted session** | Commit theo cùng batch size |
| Producer completion | Chờ **Session.commit()** hoàn tất | Không tính send async chưa xác nhận như commit thành công |
| Consumer transaction | **JMS transacted session** | Commit sau khi nhận và kiểm tra đủ batch |
| ACK | Transaction commit | Không dùng AUTO_ACKNOWLEDGE ở một bên và transacted ở bên kia |
| Redelivery | Tách scenario riêng | Cùng rollback count/backoff/max attempts khi đo retry |
| Message order | Một producer/consumer trong baseline | Tăng concurrency là scenario riêng |
| Expiration | TTL=0 / không hết hạn trong thời gian test | Không để broker loại message âm thầm |
| Selector | Cùng selector hoặc không dùng | Không so một bên lọc message, bên kia đọc toàn queue |
| Security | Cùng TLS/auth hoặc cùng môi trường cách ly | Không đo một bên TLS và bên kia plaintext rồi gọi là so broker |

**Persistent** là thuộc tính delivery của từng message; **durable queue** là thuộc tính destination. Muốn kiểm tra persistence qua restart phải có **cả hai**, cùng một storage policy phù hợp. Một message persistent gửi vào destination tạm thời hoặc queue tự xóa không tương đương với message persistent trong durable queue.

### 2.1. Transaction boundary quyết định ý nghĩa throughput

Giả sử mỗi batch có **100 message**:

~~~text
Producer:
    send M1 ... M100 trong JMS transacted session
    commit()
    Chỉ sau khi commit hoàn tất mới tính batch đã được xác nhận

Consumer:
    receive M1 ... M100
    validate/handle
    commit()
    Chỉ sau commit mới tính batch đã ACK
~~~

Đo producer bằng số lần gọi **send()** mà không chờ **commit()** có thể chỉ đo tốc độ client buffer message. Đo consumer bằng số lần **receive()** mà không commit transacted session có thể chỉ đo tốc độ dispatch. Cần báo cáo riêng:

- **Send-call throughput**: tốc độ gọi API send; chỉ là chỉ số phụ.
- **Producer commit throughput**: số message thuộc các transaction đã commit mỗi giây.
- **Consumer receive throughput**: số message nhận được mỗi giây; chưa đồng nghĩa ACK.
- **Consumer commit throughput**: số message được ACK qua transaction commit mỗi giây.
- **End-to-end latency**: từ lúc producer bắt đầu gửi đến lúc consumer nhận/commit theo định nghĩa đã công bố.

Trong baseline dưới đây, producer và consumer đều dùng **persistent + transacted batch commit**, để phép đo thể hiện chi phí persistence và transaction theo cùng một hợp đồng.

### 2.2. At-least-once và exactly-once không thể suy từ broker throughput

JMS transaction giúp gom send hoặc receive/ACK trong một session. Nó không tự làm side effect của DB/HTTP và broker commit thành một giao dịch nguyên tử. Nếu client mất kết nối đúng lúc commit, kết quả có thể **UNKNOWN**; message có thể được giao lại hoặc producer có thể retry.

Benchmark phải kiểm tra **đủ số sequence và không thiếu message**, nhưng khi đánh giá ứng dụng thật cần thêm **eventId/idempotency**. Không ghi “exactly-once” chỉ vì test một lần không thấy duplicate.

## 3. Các scenario phải tách riêng

Không gộp mọi phép đo vào một bài speed test duy nhất. Ít nhất nên có các workload sau:

| Scenario | Workload | Mục đích | Kết quả chính |
| --- | --- | --- | --- |
| **S1 — Persistent transactional throughput** | Persistent, durable queue, producer/consumer transacted, batch cố định | Baseline bảo đảm | Producer/consumer commit msg/s, latency |
| **S2 — Small batch latency** | Batch 1 hoặc nhỏ, một producer/consumer | Đo độ trễ commit/dispatch | p50/p95/p99 latency, commit time |
| **S3 — Large payload throughput** | Payload 4 KiB, 16 KiB, 64 KiB | Đo byte throughput, disk/network | MiB/s, CPU, journal/network |
| **S4 — Concurrency scaling** | Tăng producer/consumer từ 1 lên 2/4/8 | Xem khả năng scale | Throughput, p99, fairness |
| **S5 — Slow consumer/backpressure** | Consumer giới hạn tốc độ, producer nhanh hơn | Đo backlog, paging, flow control | Oldest age, disk, in-flight |
| **S6 — Redelivery** | Rollback có chủ đích, cùng max attempts/backoff | Đo chi phí retry và DLQ | Redelivery rate, retry latency |
| **S7 — Restart durability** | Persistent send + commit, broker restart, consume sau restart | Kiểm tra message còn tồn tại | Missing/duplicate sequence, recovery time |
| **S8 — HA/failover** | Primary/backup hoặc broker topology có HA | Đo thời gian gián đoạn và outcome | Reconnect time, RPO, duplicate/loss |
| **S9 — TLS/mTLS** | Cùng protocol security và certificate validation | Đo chi phí mã hóa/handshake | Throughput/latency và CPU TLS |

**Không so sánh S1 của Artemis với S6 của Classic** rồi kết luận. Một broker có thể nhanh hơn trong batch throughput nhưng chậm hơn ở p99 của single-message commit; đó là trade-off có ý nghĩa, không phải mâu thuẫn.

### Workload baseline minh họa

- **1 producer**, **1 consumer**, queue durable ANYCAST.
- **100.000 message**, mỗi payload **1 KiB**.
- **Batch commit 100 message** cho producer và consumer.
- Producer bắt đầu sau khi consumer đã đăng ký.
- Consumer xác minh **runId** và **sequence**, commit mỗi 100 message.
- Không TTL, không priority, selector chỉ dùng để cô lập runId.
- Không TLS trong baseline local lab; TLS đo riêng S9.
- Cùng một filesystem/storage class và broker sync policy phù hợp durable commit.

Đây chỉ là workload minh họa. Trong ứng dụng thực tế, hãy dùng phân bố payload và số producer/consumer gần traffic production; thêm scenario khác nếu workload có message lớn, topic fan-out hoặc transaction DB.

## 4. Kiểm soát môi trường đo và cấu hình broker

### 4.1. Cố định phần cứng và runtime

| Hạng mục | Phải ghi lại |
| --- | --- |
| CPU | Model, physical/logical cores, governor/power mode, quota container |
| Memory | RAM, JVM Xms/Xmx, container memory limit, swap |
| OS/kernel | Version, filesystem, mount options, file descriptor limit |
| Storage | SSD/NVMe/HDD, volume type, IOPS/throughput, fsync latency |
| Network | Loopback/LAN/WAN, NIC speed, RTT, packet loss |
| JVM | Vendor/version, GC, heap, GC flags, container awareness |
| Broker | Classic/Artemis exact version, config checksum, plugins |
| Client | JMS API namespace, client version, JVM options |
| Topology | Broker local/remote, Docker/native, number of nodes, HA state |

Không chạy broker Classic trên NVMe host và Artemis trong container giới hạn IOPS rồi so throughput. Cũng không chạy cả hai đồng thời nếu chúng tranh cùng disk/CPU; tốt hơn là chạy **lần lượt trong môi trường được reset giống nhau**, hoặc dùng hai host đồng nhất và đảo vị trí broker để phát hiện bias.

### 4.2. Persistence phải có semantics tương đương

Classic thường dùng **KahaDB**; Artemis dùng **journal** riêng. Cấu trúc file và batching khác nhau, nhưng benchmark phải giữ cùng yêu cầu: persistent messages và transaction commit được xác nhận theo durable storage policy.

Ví dụ Classic KahaDB trong activemq.xml:

~~~xml
<persistenceAdapter>
    <kahaDB
        directory="/var/lib/activemq/kahadb"
        journalDiskSyncStrategy="always"/>
</persistenceAdapter>
~~~

Đoạn trên đặt sync strategy ở chế độ chặt cho KahaDB; xác minh tùy chọn theo phiên bản Classic đang dùng. Không đổi sang periodic hoặc never chỉ để tăng tốc rồi so với Artemis đang sync journal khi commit.

Ví dụ Artemis trong broker.xml, phần core configuration hiện hữu:

~~~xml
<journal-type>NIO</journal-type>
<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
~~~

Đây là các thuộc tính journal ở phần cấu hình core tương ứng; xác minh schema và effective configuration của release Artemis. **journal-sync-transactional=true** quan trọng với baseline JMS transacted. Giữ policy durable phù hợp; không tắt sync để đạt con số đẹp.

Hai cấu hình trên **không làm cho KahaDB và Artemis journal có cùng implementation hoặc cùng số lần ghi vật lý**. Chúng giúp đặt cùng mục tiêu ở mức ứng dụng: message persistent và transaction commit được xác nhận theo storage policy đã chọn. Phải kiểm tra thêm restart/crash scenario và thiết bị lưu trữ; write cache của controller/volume cũng ảnh hưởng durability thực tế.

**Lưu ý:** NIO hay AIO là lựa chọn implementation/OS; không nhất thiết ép hai broker dùng cùng một cơ chế file I/O nội bộ. Cần so **cùng storage device và cùng yêu cầu durability**, sau đó có thể chạy thêm một lượt tuned cho mỗi broker theo khuyến nghị riêng của vendor.

### 4.3. Destination phải tương đương

Artemis queue ANYCAST durable:

~~~xml
<address name="benchmark.persistent">
    <anycast>
        <queue name="benchmark.persistent" durable="true"/>
    </anycast>
</address>
~~~

Classic cần queue durable/được broker quản lý phù hợp; queue tạo qua JMS có thể auto-create theo policy broker. Trước mỗi lần đo, kiểm tra destination tồn tại, không có backlog cũ và policy không tự xóa queue. Đừng để một bên dùng topic multicast còn bên kia queue point-to-point.

### 4.4. Client buffering/prefetch không có đơn vị giống nhau

Classic thường điều khiển prefetch bằng **số message** (ví dụ queuePrefetch=1); Artemis **consumerWindowSize** dùng **byte**. Không thể gán cùng số 100 cho hai cấu hình rồi kết luận chúng tương đương.

Baseline single-consumer có thể giới hạn in-flight gần một message bằng:

- Classic: **queuePrefetch=1**.
- Artemis: **consumerWindowSize=0**.

Đây là baseline hạn chế buffer, không bảo đảm hai implementation có chi phí/dispatch giống nhau. Sau baseline, chạy thêm tuning riêng, ghi rõ prefetch/window thực tế, số message delivering và throughput. Không so một bên buffer hàng nghìn message với bên kia chỉ có một message in-flight mà bỏ qua ảnh hưởng đó.




## 5. Tạo hai môi trường client tách biệt

ActiveMQ Classic 5.x và Artemis hiện đại có thể dùng **hai namespace JMS khác nhau**:

- Classic 5.x thường dùng **javax.jms**.
- Artemis Jakarta client dùng **jakarta.jms**.

Không đưa hai client/API vào cùng một Maven module rồi kỳ vọng chúng có cùng kiểu ConnectionFactory. Cách benchmark rõ ràng là **hai module riêng**, dùng cùng logic JMS 1.1/JMS transacted và thay namespace/provider adapter.

### 5.1. Maven dependency cho Classic

Ví dụ module **classic-bench** dùng Java 17 và ActiveMQ Classic client:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>5.18.3</version>
</dependency>
~~~

Factory và baseline prefetch:

~~~java
import javax.jms.ConnectionFactory;
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;

ConnectionFactory connectionFactory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

ActiveMQConnectionFactory classic =
        (ActiveMQConnectionFactory) connectionFactory;
ActiveMQPrefetchPolicy prefetch = classic.getPrefetchPolicy();
prefetch.setQueuePrefetch(1);
classic.setPrefetchPolicy(prefetch);
~~~

Prefetch queue bằng **một message** hạn chế lượng dispatch trước. Khi benchmark throughput tối đa, chạy thêm profile prefetch lớn hơn và ghi rõ giá trị; không dùng prefetch=1 như thông số tối ưu mặc định.

### 5.2. Maven dependency cho Artemis Jakarta client

Module **artemis-bench**:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-client</artifactId>
    <version>2.42.0</version>
</dependency>
~~~

Factory và baseline consumer window:

~~~java
import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ConnectionFactory connectionFactory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61626");

ActiveMQConnectionFactory artemis =
        (ActiveMQConnectionFactory) connectionFactory;
artemis.setConsumerWindowSize(0);
~~~

**consumerWindowSize=0** hạn chế buffering phía client theo semantics Artemis. Đây là baseline cho ít message in-flight, không phải thông số tối ưu throughput. Khi chạy tuned profile, thử window lớn hơn và đo lại backlog/latency/heap.

Các version trên là **bộ version minh họa để pin môi trường lab**. Khi benchmark thật, ghi đầy đủ broker version và client version tương ứng; không nâng một bên mà quên bên kia trong cùng bộ kết quả.

**Wire protocol cũng khác trong native stack:** Classic JMS client thường dùng **OpenWire**, còn Artemis Jakarta client dùng **Artemis Core protocol**. Kết quả ở đây là so sánh **broker + native JMS client stack** theo cùng semantics ứng dụng; không cô lập riêng thuật toán broker. Ghi protocol vào report. Nếu mục tiêu là so cùng wire protocol, phải thiết kế một scenario riêng với protocol mà cả hai broker hỗ trợ và xác minh mapping JMS/ACK/transaction tương đương trước khi đo.

### 5.3. Tách broker data và kết quả

~~~text
bench/
  classic/
    broker-data/
    activemq.xml
    results/
  artemis/
    broker-data/
    broker.xml
    results/
  client/
    classic-bench/
    artemis-bench/
~~~

Mỗi broker phải có **data directory/journal riêng**. Không khởi động hai broker cùng trỏ vào một journal folder. Mỗi lần đo cần reset queue backlog và dữ liệu benchmark theo quy trình; không xóa journal đang được broker sử dụng. Dừng broker sạch trước khi dọn dữ liệu lab và lưu bản sao cấu hình để kết quả tái lập được.

## 6. Java JMS harness: producer và consumer chạy đồng thời

Đoạn harness dùng API JMS chung: **Connection, Session transacted, MessageProducer và MessageConsumer**. Thuật toán giống nhau; module Classic dùng **javax.jms**, module Artemis dùng **jakarta.jms**. Chạy mỗi module riêng, không đặt hai namespace trên cùng classpath.

### 6.1. Hai import/provider block

Đầu file **PersistentBatchBenchmark.java** của module Classic:

~~~java
import javax.jms.*;
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;
~~~

Đầu file của module Artemis:

~~~java
import jakarta.jms.*;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
~~~

Phần class bên dưới dùng API JMS chung. Để biên dịch module Artemis, thay đúng các import và provider-specific method như mục 7.

### 6.2. Source PersistentBatchBenchmark.java

Tạo file **src/main/java/PersistentBatchBenchmark.java** trong từng module. Code dưới đây trình bày bản Classic; bản Artemis giữ nguyên logic, chỉ thay namespace/provider adapter như đã nêu.

~~~java
import javax.jms.*;
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;

import java.util.Arrays;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public final class PersistentBatchBenchmark {
    public static void main(String[] args) throws Exception {
        String url = env("BROKER_URL", "tcp://127.0.0.1:61616");
        String user = env("BROKER_USER", "bench_user");
        String password = env("BROKER_PASSWORD", "bench_password");
        String queueName = env("QUEUE_NAME", "benchmark.persistent");
        int total = Integer.parseInt(env("TOTAL_MESSAGES", "100000"));
        int batch = Integer.parseInt(env("BATCH_SIZE", "100"));
        int payloadBytes = Integer.parseInt(env("PAYLOAD_BYTES", "1024"));

        if (total <= 0 || batch <= 0 || payloadBytes < 0) {
            throw new IllegalArgumentException("Invalid benchmark parameters");
        }

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        configureProvider(factory);

        String runId = UUID.randomUUID().toString();
        String selector = "runId = '" + runId + "'";
        String payload = "x".repeat(payloadBytes);

        CountDownLatch consumerReady = new CountDownLatch(1);
        CountDownLatch startGate = new CountDownLatch(1);
        AtomicReference<Throwable> consumerFailure =
                new AtomicReference<>();
        AtomicLong consumerElapsedNanos = new AtomicLong();
        long[] latencyNanos = new long[total];
        boolean[] seen = new boolean[total];

        Thread consumerThread = new Thread(() -> {
            Connection connection = null;
            Session session = null;
            MessageConsumer consumer = null;
            try {
                connection = factory.createConnection(user, password);
                session = connection.createSession(
                        true, Session.SESSION_TRANSACTED);
                Queue queue = session.createQueue(queueName);
                consumer = session.createConsumer(queue, selector);
                connection.start();

                consumerReady.countDown();
                startGate.await();

                long started = System.nanoTime();
                long deadline = started + TimeUnit.MINUTES.toNanos(10);
                int received = 0;

                while (received < total) {
                    if (Thread.currentThread().isInterrupted()) {
                        throw new InterruptedException("Consumer interrupted");
                    }
                    if (System.nanoTime() > deadline) {
                        throw new JMSException(
                                "Timed out waiting for benchmark messages");
                    }

                    Message message = consumer.receive(1000L);
                    if (message == null) {
                        continue;
                    }

                    if (!runId.equals(message.getStringProperty("runId"))) {
                        throw new JMSException("Unexpected runId");
                    }

                    long sequence = message.getLongProperty("sequence");
                    if (sequence < 0 || sequence >= total
                            || seen[(int) sequence]) {
                        throw new JMSException(
                                "Invalid or duplicate sequence: " + sequence);
                    }

                    long sentAt = message.getLongProperty("sentNanos");
                    latencyNanos[(int) sequence] =
                            System.nanoTime() - sentAt;
                    seen[(int) sequence] = true;
                    received++;

                    if (received % batch == 0) {
                        session.commit();
                    }
                }

                if (received % batch != 0) {
                    session.commit();
                }
                consumerElapsedNanos.set(System.nanoTime() - started);
            } catch (Throwable failure) {
                consumerFailure.set(failure);
                consumerReady.countDown();
            } finally {
                closeQuietly(consumer);
                closeQuietly(session);
                closeQuietly(connection);
            }
        }, "benchmark-consumer");

        consumerThread.start();

        if (!consumerReady.await(30, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Consumer did not become ready");
        }
        if (consumerFailure.get() != null) {
            throw new IllegalStateException(
                    "Consumer startup failed", consumerFailure.get());
        }

        Connection producerConnection = null;
        Session producerSession = null;
        MessageProducer producer = null;
        long producerElapsedNanos;

        try {
            producerConnection = factory.createConnection(user, password);
            producerSession = producerConnection.createSession(
                    true, Session.SESSION_TRANSACTED);
            Queue queue = producerSession.createQueue(queueName);
            producer = producerSession.createProducer(queue);
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);
            producer.setTimeToLive(0L);

            startGate.countDown();
            long started = System.nanoTime();

            for (int i = 0; i < total; i++) {
                TextMessage message =
                        producerSession.createTextMessage(payload);
                message.setStringProperty("runId", runId);
                message.setLongProperty("sequence", i);
                // Same JVM: nanoTime is monotonic across these threads.
                message.setLongProperty("sentNanos", System.nanoTime());

                producer.send(message);

                if ((i + 1) % batch == 0) {
                    producerSession.commit();
                }
            }

            if (total % batch != 0) {
                producerSession.commit();
            }
            producerElapsedNanos = System.nanoTime() - started;
        } catch (Exception failure) {
            consumerThread.interrupt();
            throw failure;
        } catch (Error failure) {
            consumerThread.interrupt();
            throw failure;
        } finally {
            startGate.countDown();
            closeQuietly(producer);
            closeQuietly(producerSession);
            closeQuietly(producerConnection);
        }

        consumerThread.join(TimeUnit.MINUTES.toMillis(11));
        if (consumerThread.isAlive()) {
            consumerThread.interrupt();
            throw new IllegalStateException("Consumer thread did not finish");
        }
        if (consumerFailure.get() != null) {
            throw new IllegalStateException(
                    "Consumer benchmark failed", consumerFailure.get());
        }

        for (int i = 0; i < total; i++) {
            if (!seen[i]) {
                throw new IllegalStateException("Missing sequence " + i);
            }
        }

        long[] sortedLatency = latencyNanos.clone();
        Arrays.sort(sortedLatency);

        printResult("producer_commit", total, producerElapsedNanos,
                payloadBytes);
        printResult("consumer_commit", total, consumerElapsedNanos.get(),
                payloadBytes);

        System.out.printf(
                "runId=%s messages=%d batch=%d payloadBytes=%d "
                + "latency_receive_p50_ms=%.3f "
                + "latency_receive_p95_ms=%.3f "
                + "latency_receive_p99_ms=%.3f%n",
                runId, total, batch, payloadBytes,
                percentileMs(sortedLatency, 0.50),
                percentileMs(sortedLatency, 0.95),
                percentileMs(sortedLatency, 0.99));
    }

    private static void configureProvider(
            ActiveMQConnectionFactory factory) {
        // Classic baseline: prefetch queue bằng một message.
        ActiveMQPrefetchPolicy policy = factory.getPrefetchPolicy();
        policy.setQueuePrefetch(1);
        factory.setPrefetchPolicy(policy);
    }

    private static void printResult(
            String name, int messages, long elapsedNanos, int payloadBytes) {
        double seconds = elapsedNanos / 1_000_000_000.0;
        double messagesPerSecond = messages / seconds;
        double mebibytesPerSecond =
                (messages * (double) payloadBytes / (1024.0 * 1024.0))
                / seconds;

        System.out.printf(
                "%s elapsed_ms=%.3f messages_per_second=%.2f "
                + "payload_MiB_per_second=%.2f%n",
                name, elapsedNanos / 1_000_000.0,
                messagesPerSecond, mebibytesPerSecond);
    }

    private static double percentileMs(long[] sorted, double percentile) {
        int index = Math.max(0,
                (int) Math.ceil(percentile * sorted.length) - 1);
        return sorted[index] / 1_000_000.0;
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static void closeQuietly(MessageConsumer value) {
        if (value != null) try { value.close(); } catch (Exception ignored) { }
    }

    private static void closeQuietly(MessageProducer value) {
        if (value != null) try { value.close(); } catch (Exception ignored) { }
    }

    private static void closeQuietly(Session value) {
        if (value != null) try { value.close(); } catch (Exception ignored) { }
    }

    private static void closeQuietly(Connection value) {
        if (value != null) try { value.close(); } catch (Exception ignored) { }
    }
}
~~~


## 7. Provider-specific adapter: cùng workload, khác namespace và client setting

Trong source chung ở mục 6, **module Classic** giữ nguyên ba import:

~~~java
import javax.jms.*;
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;
~~~

và giữ nguyên nội dung **configureProvider**:

~~~java
private static void configureProvider(
        ActiveMQConnectionFactory factory) {
    ActiveMQPrefetchPolicy policy = factory.getPrefetchPolicy();
    policy.setQueuePrefetch(1);
    factory.setPrefetchPolicy(policy);
}
~~~

Với **module Artemis**, thay import bằng:

~~~java
import jakarta.jms.*;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
~~~

và thay duy nhất implementation của provider adapter:

~~~java
private static void configureProvider(
        ActiveMQConnectionFactory factory) {
    factory.setConsumerWindowSize(0);
}
~~~

Phần còn lại dùng cùng API JMS 1.1: tạo Connection, Session transacted, queue, producer/consumer; gửi persistent; commit theo batch. **Không biên dịch đồng thời cả hai import block**. Mỗi module chỉ có một namespace và một client provider.

### 7.1. Cấu hình broker và client URL phải khớp

| Thành phần | Classic lab | Artemis lab |
| --- | --- | --- |
| Core/JMS port | 61616 | 61626 |
| Queue | benchmark.persistent | benchmark.persistent |
| Queue semantics | Point-to-point | ANYCAST |
| Store | KahaDB | Artemis journal |
| Client namespace | javax.jms | jakarta.jms |
| Client buffering baseline | queuePrefetch=1 message | consumerWindowSize=0 byte |
| Message delivery | PERSISTENT | PERSISTENT |
| Transaction | Session transacted | Session transacted |

Cả hai broker phải có queue tương ứng và không bật policy xóa queue không hoạt động giữa test. Nếu dùng Docker, URL client phải là hostname/port nhìn thấy từ container client; host port mapping không nhất thiết bằng port nội bộ.

### 7.2. Giới hạn của harness

Harness là **một producer và một consumer trong cùng JVM**, chạy song song để đo pipeline cơ bản. Nó dùng một selector theo runId để tránh đọc message cũ của lần chạy trước, kiểm tra từng sequence và tính latency từ timestamp monotonic của cùng JVM.

Các kết quả:

- **producer_commit**: số message đã được producer gửi và commit transaction mỗi giây.
- **consumer_commit**: số message consumer nhận và commit ACK mỗi giây.
- **latency_receive_p50/p95/p99**: từ lúc tạo timestamp ngay trước send đến lúc consumer nhận; bao gồm chờ batch commit và dispatch, nhưng **chưa bao gồm thời gian commit consumer**.
- **payload_MiB_per_second**: chỉ tính kích thước body khai báo; chưa cộng JMS headers/properties, protocol framing, journal overhead hay network overhead.

Vì producer và consumer dùng một JVM, **System.nanoTime()** có thể so sánh giữa hai thread. Nếu tách client thành nhiều JVM/host, không được so nanoTime giữa máy; dùng clock đồng bộ và timestamp UTC, hoặc một tracing/histogram có clock discipline.

Harness không triển khai nhiều producer/consumer, DB side effect, retry policy, DLQ, TLS hay HA. Các mục đó phải là scenario độc lập; không dùng kết quả harness nhỏ để tuyên bố benchmark toàn hệ thống.


## 8. Chạy benchmark có kiểm soát

Trước khi chạy harness, mỗi broker phải có queue **benchmark.persistent** durable và user có quyền send/consume. Chạy từng broker **lần lượt**, dùng cùng cấu hình workload và JVM.

### 8.1. Classic

Trong PowerShell tại module Maven Classic:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "bench_user"
$env:BROKER_PASSWORD = "<lab-password>"
$env:QUEUE_NAME = "benchmark.persistent"
$env:TOTAL_MESSAGES = "100000"
$env:BATCH_SIZE = "100"
$env:PAYLOAD_BYTES = "1024"

mvn -q compile exec:java "-Dexec.mainClass=PersistentBatchBenchmark"
~~~

### 8.2. Artemis

Trong module Maven Artemis, giữ nguyên tham số workload và đổi URL:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61626"
$env:BROKER_USER = "bench_user"
$env:BROKER_PASSWORD = "<lab-password>"
$env:QUEUE_NAME = "benchmark.persistent"
$env:TOTAL_MESSAGES = "100000"
$env:BATCH_SIZE = "100"
$env:PAYLOAD_BYTES = "1024"

mvn -q compile exec:java "-Dexec.mainClass=PersistentBatchBenchmark"
~~~

POM cần có plugin sau nếu dùng mục tiêu **exec:java**:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
~~~

Hoặc chạy class bằng IDE/Java launcher với classpath module đã build. Không đưa mật khẩu thật vào command history, log CI hoặc file kết quả. Với Docker, thay host port bằng service DNS và port nội bộ nếu client chạy trong container.

### 8.3. Warm-up và các lần đo

Một quy trình có thể tái lập:

1. Khởi động broker, đợi journal/recovery ổn định và xác minh queue trống.
2. Chạy **2–3 lượt warm-up** không lấy kết quả làm số liệu chính để JIT, class loading và cache ổn định.
3. Chạy **ít nhất 5 lượt đo độc lập**, tốt hơn 7–10 nếu thời gian cho phép.
4. Xen kẽ thứ tự broker, ví dụ **Classic → Artemis → Artemis → Classic**, để giảm bias do nhiệt độ, cache hoặc tải nền.
5. Ghi kết quả từng lượt, không chỉ ghi trung bình cuối.
6. Dừng broker sạch, reset dữ liệu lab theo cùng quy trình và xác minh cấu hình trước lượt tiếp theo.

Đừng chạy cả hai broker cùng lúc trên một ổ NVMe rồi kết luận broker nào nhanh hơn. Nếu bắt buộc dùng hai host, hoán đổi vị trí/host giữa các đợt đo để nhận diện chênh lệch phần cứng.

### 8.4. Thay đổi một biến mỗi lượt

| Lượt | Biến thay đổi | Ví dụ |
| --- | --- | --- |
| Baseline | Không đổi | 1 producer, 1 consumer, 1 KiB, batch 100 |
| Batch | Chỉ batch size | 1, 10, 100, 500 |
| Payload | Chỉ body size | 128 B, 1 KiB, 16 KiB, 64 KiB |
| Producer concurrency | Chỉ producer count | 1, 2, 4, 8 |
| Consumer concurrency | Chỉ consumer count | 1, 2, 4, 8 |
| Prefetch/window | Chỉ client buffer | Classic 1/100/1000; Artemis 0/64 KiB/1 MiB |
| TLS | Bật cùng TLS policy | Cùng TLS version/cert/auth ở hai broker |
| Persistence profile | Chỉ thay sync policy có chủ đích | Durable baseline so với tuned profile riêng |

**Không đổi cùng lúc batch, prefetch, JVM heap và storage policy** rồi không biết yếu tố nào làm kết quả đổi. Sau khi tìm được điểm tối ưu từng broker, báo cáo hai loại kết quả: **same-semantics baseline** và **provider-tuned result**.

## 9. Thu thập metrics ngoài output của harness

Output Java cho biết throughput/latency của client harness. Muốn hiểu nguyên nhân, phải thu thập broker và OS metrics trong cùng cửa sổ thời gian.

### 9.1. Client và broker

| Metric | Đo ở đâu | Câu hỏi trả lời |
| --- | --- | --- |
| Producer commit msg/s | Harness | Broker xác nhận bao nhiêu message mỗi giây theo batch |
| Consumer commit msg/s | Harness | Bao nhiêu message được ACK qua commit mỗi giây |
| Receive latency p50/p95/p99 | Harness | Phần lớn message được giao trong bao lâu |
| Commit latency p95/p99 | Histogram quanh Session.commit | Transaction batch có đuôi latency cao không |
| Queue pending/message count | Artemis management hoặc Classic JMX | Backlog có tăng trong lúc đo không |
| Delivering/in-flight | Broker management/JMX | Có bao nhiêu message dispatch nhưng chưa ACK |
| Enqueue/dequeue/ack count | Broker management | Client counters có khớp broker counters không |
| Redelivery/DLQ | Broker management | Có retry hoặc poison message ngoài ý muốn không |
| Journal/store write latency | OS/broker metrics | Persistence có phải nút thắt không |
| Connection/consumer count | Broker management | Client đã tạo đủ consumers chưa |

Tên JMX object, management attribute và metric exporter khác nhau giữa Classic và Artemis. Ghi **tên thực tế và đơn vị** của từng broker; không copy tên metric của Artemis sang Classic hoặc ngược lại rồi cho rằng số liệu tương đương.

Để đo commit latency trong harness, bọc từng lần commit bằng đồng hồ monotonic và lưu mẫu riêng cho producer/consumer:

~~~java
long commitStarted = System.nanoTime();
session.commit();
long commitLatencyNanos = System.nanoTime() - commitStarted;
// Ghi commitLatencyNanos vào histogram/mảng mẫu của harness.
~~~

Trong ví dụ trên, **commitLatencySamples** là histogram hoặc mảng mẫu do harness bổ sung; không cộng thời gian commit vào receive latency trước khi định nghĩa rõ metric. Tính p50/p95/p99 riêng cho producer commit và consumer ACK commit.

### 9.2. Host metrics

Thu thập theo chu kỳ 1–5 giây trong warm-up và đo:

- CPU process broker/client và CPU toàn host.
- RSS, heap used/committed, GC pause count/time, allocation rate.
- Disk read/write bytes/s, IOPS, queue depth, fsync latency, utilization.
- Network bytes/s, packet retransmission, RTT, socket count.
- Thread count, context switch, file descriptors, connection count.
- Container CPU throttling, memory pressure và I/O limits nếu chạy Docker/Kubernetes.

Nếu broker dùng 100% một CPU core nhưng disk còn rảnh, nút thắt có thể ở serialization, lock hoặc routing. Nếu CPU thấp nhưng fsync latency cao, tăng consumer thường không giải quyết được journal bottleneck.

### 9.3. Đối chiếu số message để phát hiện benchmark không hợp lệ

Với S1, điều kiện sau phải đúng:

~~~text
producer_committed = TOTAL_MESSAGES
consumer_committed = TOTAL_MESSAGES
unique_sequence_count = TOTAL_MESSAGES
missing_sequence_count = 0
duplicate_sequence_count = 0
unexpected_run_id_count = 0
unexpected_expired_count = 0
unexpected_DLQ_count = 0
~~~

Harness kiểm tra sequence và duplicate trong consumer; người vận hành vẫn cần đối chiếu **broker queue count**, DLQ và expiration sau lượt chạy. Nếu broker counter khác vì metric tính thời điểm enqueue/dequeue khác, giải thích semantics của counter, không chỉnh số liệu cho khớp bằng tay.

## 10. Cách tính và đọc kết quả

### 10.1. Throughput

Với N message được xác nhận trong khoảng thời gian T giây:

\[
\text{throughput}=\frac{N}{T}\quad \text{messages/s}
\]

Payload throughput:

\[
\text{MiB/s}=
\frac{N\times \text{payloadBytes}}{T\times 1024^2}
\]

**Payload MiB/s** trong harness không tính header, properties, protocol frame, journal record, replication traffic hay TLS overhead. Không gọi nó là network throughput.

Producer và consumer có thời gian đo riêng. Consumer throughput bao gồm receive và commit. End-to-end receive latency được đo từ **sentNanos** tới lúc consumer nhận, còn **không bao gồm commit consumer**; nếu cần latency ACK end-to-end, ghi thêm thời điểm consumer commit batch và liên kết message với batch commit.

### 10.2. Percentile quan trọng hơn average đơn lẻ

- **p50** phản ánh message điển hình.
- **p95** cho biết phần chậm đáng kể.
- **p99/p99.9** giúp thấy tail latency, nhất là lúc fsync, GC hoặc paging.
- **max** dễ bị một outlier chi phối; ghi kèm số sample và percentile.

Không lấy trung bình p99 của nhiều lượt như thể đó là p99 tổng hợp. Cách đơn giản: lưu **raw latency samples hoặc histogram có cùng bucket**, gộp theo phương pháp thống kê đúng, đồng thời báo cáo median và khoảng dao động throughput giữa các lượt.

### 10.3. Ví dụ đọc kết quả

Giả sử một bộ đo cho ra số liệu giả định:

| Broker | Producer commit | Consumer commit | Receive p50 | Receive p99 | CPU broker |
| --- | ---: | ---: | ---: | ---: | ---: |
| Classic | 42.000 msg/s | 39.000 msg/s | 2,1 ms | 18 ms | 72% |
| Artemis | 48.000 msg/s | 46.000 msg/s | 1,8 ms | 24 ms | 78% |

Không thể kết luận Artemis “tốt hơn toàn diện”: producer/consumer throughput cao hơn nhưng **p99 receive latency cao hơn**. Cần kiểm tra disk fsync, batch timing, GC, queue backlog và số sample. Đây là số minh họa để diễn giải, **không phải kết quả benchmark thực tế hoặc khuyến nghị hiệu năng của hai sản phẩm**.

### 10.4. So sánh mức cải thiện theo tỷ lệ

\[
\text{speedup}=
\frac{\text{throughput}_{Artemis}}
     {\text{throughput}_{Classic}}
\]

\[
\text{latency ratio}=
\frac{p99_{Artemis}}{p99_{Classic}}
\]

Speedup lớn hơn 1 cho thấy throughput Artemis cao hơn trong **scenario đang xét**. Latency ratio lớn hơn 1 cho thấy p99 Artemis cao hơn. Luôn ghi giá trị gốc và điều kiện đo bên cạnh tỷ lệ; không chỉ công bố phần trăm tăng.

## 11. Tuning sau baseline: không làm mất semantics

Sau khi baseline công bằng đã ổn định, có thể tune từng broker theo khuyến nghị riêng. Kết quả tuned là **phép so sánh khác**, không được ghi như cùng một cấu hình.

| Hạng mục | Classic | Artemis | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Prefetch/buffer | Queue prefetch theo message | Consumer window theo byte | In-flight, fairness, memory |
| Persistence | KahaDB journal/sync | Artemis journal/NIO/AIO/sync | Commit latency và durability |
| Producer batching | JMS transaction batch | JMS transaction batch | Same batch size và commit completion |
| Consumer concurrency | Consumer/session count | Consumer/session count | Thread/CPU/ordering |
| Paging/backpressure | Store/system usage và producer flow control | Address full policy/paging/block | Backlog, disk và producer latency |
| Large messages | Classic message/store config | Artemis large-message settings | Payload throughput và disk |
| Network/TLS | SSL transport, socket settings | Netty TLS/connector settings | RTT, CPU và handshake |
| JVM | Heap/GC/threading | Heap/GC/threading | Cùng JVM baseline, sau đó tune riêng |

**Không tắt durability, transaction hoặc TLS để tăng throughput trong cùng baseline.** Nếu muốn đo non-persistent/async send, đặt tên scenario riêng như **S1-fast-nondurable** và nói rõ semantics yếu hơn.

### 11.1. Batching là một trade-off

Batch 1 giảm thời gian một message phải chờ đủ batch nhưng tạo nhiều commit hơn, có thể tăng fsync/round trips. Batch 500 giảm số commit trên mỗi message nhưng tăng lượng dữ liệu chưa được xác nhận và tail latency. Chọn batch dựa trên SLA latency và giới hạn transaction size, không chỉ nhìn msg/s.

### 11.2. Prefetch/window là một trade-off

Buffer lớn có thể tăng throughput bằng cách giảm round trips, nhưng làm tăng message in-flight và memory, có thể giảm fairness khi nhiều consumer cùng queue. Buffer nhỏ giúp backpressure sát hơn nhưng có thể làm broker/client tương tác nhiều hơn. So sánh theo **cùng giới hạn in-flight quan sát được**, sau đó tune riêng theo provider.

### 11.3. Persistence và fsync

Nếu kết quả nhanh khác thường, kiểm tra journal/store sync policy. **Persistent + transacted** chỉ có giá trị so sánh khi cả hai broker thực hiện cam kết durability theo cấu hình đã ghi. Không dùng chế độ **never sync** ở một bên rồi so với bên kia sync commit.


## 12. Persistence, redelivery và restart phải đo bằng scenario riêng

Throughput cao không chứng minh dữ liệu bền qua crash hoặc message được giao lại đúng policy. Các kiểm tra này thường làm giảm throughput nhưng xác nhận **ngữ nghĩa bảo đảm** mà benchmark baseline đang tuyên bố.

### 12.1. Restart durability

Một kịch bản kiểm tra cơ bản:

1. Tạo durable queue và gửi **N persistent messages** trong transacted session.
2. Chờ **producer Session.commit()** hoàn tất; ghi lại runId và toàn bộ sequence đã gửi.
3. Xác nhận queue chứa backlog, sau đó dừng broker theo phương thức được định nghĩa.
4. Khởi động lại cùng broker với **cùng data directory/journal** và cùng destination policy.
5. Consume và commit tất cả message.
6. Đối chiếu **unique sequence**, missing, duplicate, expired và DLQ.

**Graceful restart** kiểm tra việc đóng broker bình thường; nó không mô phỏng mất điện. **Kill -9/process crash** kiểm tra process crash nhưng OS có thể vẫn flush page cache. Muốn kiểm chứng power-loss durability thực sự cần môi trường fault-injection phù hợp (VM/hardware/storage test), không suy từ một lần restart sạch.

Khi báo cáo phải ghi rõ failure model: graceful stop, process kill, VM reset hay power-loss simulation. Một con số RPO không có failure model đi kèm là không đầy đủ.

### 12.2. Redelivery và DLQ

Dùng một scenario khác với baseline throughput:

- Consumer nhận message trong transacted session rồi **rollback** có chủ đích.
- Đếm số lần giao, kiểm tra cờ **JMSRedelivered** và **JMSXDeliveryCount** nếu provider expose.
- Đặt cùng mục tiêu **maximum deliveries**, delay/backoff và DLQ semantics ở hai broker.
- Xác minh message cuối cùng được xử lý hoặc chuyển đúng DLQ.
- Đo **redelivery latency**, số lần delivery và thời gian drain, không chỉ đo msg/s.

**Classic và Artemis có thể cấu hình retry ở các lớp khác nhau** (client redelivery policy, broker policy, dead-letter strategy). Không chỉ đặt cùng con số “5 lần” trong hai file config mà kết luận semantics bằng nhau; hãy chạy test và xác minh số lần delivery thực tế trước khi so throughput retry.

### 12.3. HA/failover là một phép so sánh riêng

Classic và Artemis có thể dùng những mô hình HA khác nhau. Classic shared-store master/slave, network of brokers và Artemis primary/backup replication **không có cùng failure model**. Không lấy network-of-brokers làm tương đương trực tiếp với HA replication của Artemis.

Nếu so HA, phải chốt cùng yêu cầu:

| Điều kiện | Cần ghi rõ |
| --- | --- |
| Failure domain | Process, host, rack, availability zone hay site |
| RPO | Message nào được coi là đã commit và có thể mất đến mức nào |
| RTO | Thời gian client reconnect và tiếp tục xử lý |
| Split-brain | Cơ chế lock/quorum/fencing |
| Client failover | URI/topology, retry interval, timeout, duplicate handling |
| Transaction outcome | Commit có thể UNKNOWN; cách đối soát eventId |
| Storage | Shared store hay replicated journal; latency/bandwidth |
| Test | Tắt primary, mất network, mất storage, backup activation, failback |

So sánh HA theo **SLO quan sát được**: số message persistent đã commit trước failure có được khôi phục, bao lâu consumer hoạt động trở lại, có duplicate/loss không và writer cũ có bị fence không. Không dùng tên tính năng để suy ra hai kiến trúc bảo đảm như nhau.

## 13. Lỗi thường gặp làm benchmark mất giá trị

| Lỗi | Vì sao kết quả sai lệch | Cách sửa |
| --- | --- | --- |
| Một bên persistent, một bên non-persistent | So sánh mức bảo đảm khác nhau | Cùng delivery mode và persistence policy |
| Một bên commit mỗi message, bên kia commit mỗi 100 | Chi phí fsync/transaction khác | Cùng transaction batch |
| Chỉ đo send() chưa commit | Đo client buffering thay vì xác nhận transaction | Đo đến khi commit hoàn tất |
| Consumer AUTO_ACK bên này, transacted bên kia | ACK semantics khác nhau | Cùng Session transacted và commit |
| Queue một bên durable, bên kia temporary/auto-delete | Restart behavior khác | Destination durable và cùng retention |
| Một bên có TLS, một bên plaintext | CPU và network cost khác | Tách scenario TLS hoặc bật cùng policy |
| Một bên chạy trên NVMe, bên kia trên HDD | Storage latency chi phối kết quả | Cùng storage class và host condition |
| Không warm-up JVM | JIT/class loading làm lệch lượt đầu | Warm-up riêng, bỏ lượt warm-up |
| Chỉ chạy một lần | Noise và background load chi phối | Nhiều lượt, xen kẽ thứ tự |
| Chỉ báo average | Che tail latency | Báo p50/p95/p99 và raw/histogram |
| Không kiểm tra sequence | Có thể nhanh do mất/duplicate message | Kiểm tra runId, sequence, count |
| So broker khi queue còn backlog cũ | Consumer có thể nhận nhầm message | Queue riêng, selector/runId và reset đúng |
| Tăng concurrency nhưng không tăng worker thực | Cấu hình không phản ánh workload | Đếm connection/session/consumer thật |
| Tune prefetch chỉ một phía | In-flight và buffer khác nhau | Baseline có kiểm soát, tuned profile riêng |
| Tắt journal sync | Throughput tăng nhờ giảm durability | Giữ sync policy cho baseline durable |
| Đo hai broker đồng thời trên cùng host | CPU/disk contention | Chạy tuần tự hoặc đảo host |
| Gọi payload MiB/s là network throughput | Bỏ qua headers, protocol và journal | Đo network interface riêng |
| So Classic network of brokers với Artemis HA | Topology/failure model khác | Chốt RPO/RTO và test semantics trước |

### Cảnh báo về selector và harness

Harness dùng selector theo **runId** để tránh đọc message cũ. Selector cũng có chi phí đánh giá và có thể làm kết quả khác một consumer đọc trực tiếp queue. Nếu cần đo raw queue throughput, tạo **queue riêng cho từng lượt** và bỏ selector ở cả hai broker; sau đó dọn queue theo quy trình. Không bỏ selector ở một bên mà giữ ở bên kia.

Harness hiện chạy **một producer và một consumer**. Để thử nhiều worker, mỗi worker phải có **Connection/Session/Consumer riêng**; không chia sẻ một JMS Session giữa nhiều thread. Cần dùng **runId chung**, sequence toàn cục và tổng expected count; không chỉ chạy nhiều bản harness độc lập với runId riêng rồi cộng số liệu nếu mục tiêu là đo cùng một queue và một workload liên hợp.

## 14. Mẫu báo cáo benchmark và điều kiện kết luận

### 14.1. Thông tin phải lưu cho mỗi lần đo

~~~text
Scenario:
Broker:
Broker version:
Client artifact/version:
JMS namespace:
JDK/vendor:
OS/kernel:
CPU/RAM/container limits:
Storage/filesystem:
Network/RTT:
Queue/routing type:
Queue durable:
Delivery mode:
Producer transaction:
Consumer transaction/ACK:
Batch size:
Producer count:
Consumer count:
Payload bytes:
Prefetch/window:
TLS/auth:
Journal/store sync policy:
Warm-up count:
Measured run:
Messages committed:
Missing/duplicate:
Producer commit msg/s:
Consumer commit msg/s:
Receive p50/p95/p99:
Commit p50/p95/p99:
CPU/heap/GC:
Disk/fsync:
Network:
Queue backlog/oldest age:
Redelivery/DLQ:
Failure model:
Notes/config checksum:
~~~

### 14.2. Cách kết luận đúng

Một kết luận hữu ích có dạng:

> Với S1 (1 producer, 1 consumer, persistent queue, transacted batch 100, payload 1 KiB, cùng host/storage/JDK), Artemis có producer commit throughput cao hơn trong các lượt đo, trong khi Classic có p99 receive latency thấp hơn. Cả hai đều xử lý đủ sequence, không phát hiện missing/duplicate và dùng persistence sync policy đã ghi. Kết quả chỉ áp dụng cho workload/configuration này; S4 concurrency và S7 restart durability cần kết luận riêng.

Tránh câu như **“Artemis nhanh hơn Classic 30%”** nếu không nói scenario, transaction, payload, storage, phiên bản và percentile. Một broker có thể tốt hơn cho workload throughput cao, broker còn lại phù hợp hơn với yêu cầu latency hoặc hệ sinh thái hiện có.

### 14.3. Tiêu chí nghiệm thu

| Câu hỏi | Điều kiện PASS |
| --- | --- |
| Ngữ nghĩa gửi giống nhau? | Persistent, durable queue, transacted send và cùng batch |
| ACK giống nhau? | Transacted consumer commit, không so lẫn AUTO_ACK |
| Destination giống nhau? | Queue semantics tương đương, không lẫn topic/temporary |
| Môi trường đo có kiểm soát? | Cùng CPU, RAM, disk, JVM, network và broker state |
| Workload có tái lập? | Payload, N, concurrency, batch, warm-up và run order được lưu |
| Đo throughput đúng? | Producer/consumer tính đến commit hoàn tất |
| Đo latency đúng? | Định nghĩa receive vs ACK latency rõ, percentile có sample |
| Dữ liệu có đủ? | Sequence count đầy đủ, duplicate/missing/expired/DLQ được kiểm tra |
| Storage policy có tương đương? | Không tắt sync hoặc hạ persistence một bên |
| Tuning có minh bạch? | Baseline và tuned result tách riêng |
| Kết quả có thống kê? | Nhiều lượt, raw result, median/percentile và điều kiện đo |
| HA/restart có đúng failure model? | RPO/RTO, failover, fencing và crash mode được mô tả |

**Kết luận:** So sánh ActiveMQ Classic và Artemis chỉ có ý nghĩa khi hai broker thực hiện **cùng hợp đồng bảo đảm** và được đo trong **cùng điều kiện**. Persistent delivery, durable queue, transaction commit và ACK semantics phải được giữ tương đương; throughput cần tính sau commit, latency cần báo percentile, còn restart/redelivery/HA phải là các scenario riêng. Baseline công bằng giúp trả lời broker nào phù hợp với workload đã đo; tuning riêng sau đó cho biết mỗi broker có thể đạt gì mà vẫn giữ yêu cầu durability và SLA của hệ thống.

