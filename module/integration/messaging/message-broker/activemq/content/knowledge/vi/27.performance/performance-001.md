# Thiết kế phép đo theo thông lượng, độ trễ p95/p99 và tỷ lệ lỗi

> **Chương:** Hiệu năng  
> **Phạm vi:** Apache ActiveMQ Classic và Artemis; producer/consumer JMS, persistent delivery, transaction, broker storage, queue backlog và protocol/network.  
> **Mục tiêu:** Thiết kế benchmark có thể lặp lại và giải thích được, đo riêng **throughput**, **latency percentiles p95/p99** và **error rate**; phân biệt message được gửi, được broker commit, được consumer nhận và được ACK; tránh các phép đo “messages/second” không phản ánh SLA thực tế.

## 1. Một con số messages/second không đủ để kết luận broker nhanh

Giả sử benchmark cho kết quả:

```text
Run A: 80,000 messages/s
Run B: 62,000 messages/s
```

Run A có thể gửi message NON_PERSISTENT, không transaction, consumer tắt; Run B có thể gửi PERSISTENT, commit theo batch, consumer ACK sau xử lý. So sánh hai con số này không có ý nghĩa về hiệu năng cùng một workload.

Một báo cáo có giá trị phải trả lời:

- **Thông lượng:** bao nhiêu message hoặc byte được hoàn tất trong một giây?
- **Độ trễ:** một message mất bao lâu từ mốc nào đến mốc nào; p95/p99 là bao nhiêu?
- **Tỷ lệ lỗi:** bao nhiêu message/operation thất bại, timeout, rollback, duplicate hoặc không hoàn thành trong SLA?
- **Bảo đảm đã đo:** persistent hay non-persistent; ACK/transaction; một hay nhiều producer/consumer; cùng broker hay qua network bridge?
- **Điều kiện tải:** payload size, batch, concurrency, protocol, storage, TLS, prefetch, queue depth và thời gian chạy?

Benchmark không chỉ đo tốc độ tối đa. Nó phải cho thấy **broker đạt được thông lượng nào mà vẫn giữ latency/error trong giới hạn**.

## 2. Định nghĩa ba nhóm số liệu trước khi chạy

### 2.1. Throughput: phân biệt offered, accepted và completed

Có ít nhất ba tốc độ khác nhau:

| Chỉ số | Tử số | Ý nghĩa |
| --- | --- | --- |
| **Offered throughput** | Message mà load generator dự định phát | Tải ứng dụng yêu cầu hệ thống nhận |
| **Producer committed throughput** | Message thuộc các transaction producer đã commit thành công | Dữ liệu producer được broker xác nhận theo cấu hình đang đo |
| **Consumer completed throughput** | Message được consumer xử lý và ACK/commit thành công | Công việc thực sự đi qua toàn pipeline |

Công thức:

\[
T_{\text{producer}} =
\frac{N_{\text{producer committed}}}{t_{\text{end}}-t_{\text{start}}}
\]

\[
T_{\text{completed}} =
\frac{N_{\text{consumer ACK committed}}}{t_{\text{end}}-t_{\text{start}}}
\]

Đơn vị thường là message/giây. Với payload có kích thước khác nhau, bổ sung payload throughput:

\[
B_{\text{payload}} =
\frac{\sum \text{payload bytes đã hoàn tất}}{\Delta t}
\]

Có thể biểu diễn bằng MB/s (1 MB = 1.000.000 bytes) hoặc MiB/s (1 MiB = 1.048.576 bytes); báo cáo phải ghi rõ đơn vị.

**Không đếm lời gọi `send()` là message committed.** Với transacted JMS session, `send()` chỉ đưa message vào transaction hiện tại; mốc xác nhận là `session.commit()` trả thành công. Tương tự, consumer receive chưa đồng nghĩa công việc đã ACK.

### 2.2. Latency: p95/p99 phụ thuộc điểm bắt đầu và điểm kết thúc

Không có “latency của broker” duy nhất. Cần đặt tên theo phép đo:

| Tên phép đo | Bắt đầu | Kết thúc | Bao gồm |
| --- | --- | --- | --- |
| Producer send latency | Trước `send()` | `send()` trả về | Client serialization, network/provider và phản hồi send; tùy sync mode |
| Producer commit latency | Trước `commit()` | `commit()` trả về | Commit transaction, persistence/round trip theo provider |
| Queue delivery latency | Broker nhận/commit message | Consumer nhận | Queue wait, dispatch, prefetch, network |
| **End-to-end delivery latency** | Producer tạo/gửi event | Consumer nhận event | Producer send/commit + queue wait + dispatch/network |
| Consumer processing latency | Consumer bắt đầu xử lý | Business operation kết thúc | Deserialize, validation, DB/API |
| **End-to-end completion latency** | Producer phát event | Consumer business + ACK commit xong | Toàn pipeline đến điểm xác nhận xử lý |

Một phép đo p99 không ghi rõ mốc thời gian là không thể so sánh. Ví dụ “p99 = 20 ms” có thể là `send()` p99, trong khi consumer phải chờ queue 5 giây.

### 2.3. Error rate: chọn đúng mẫu số

Tách ba loại tỷ lệ:

**Operation error rate**

\[
E_{\text{operation}} =
\frac{\text{Số operation thất bại}}{\text{Tổng operation đã thử}}
\]

Operation gồm send, commit, receive, ACK/commit, reconnect. Một message retry ba lần có thể sinh nhiều operation failures.

**Message terminal failure rate**

\[
E_{\text{message}} =
\frac{\text{Unique eventId kết thúc ở trạng thái failed}}{\text{Unique eventId đã offer}}
\]

Chỉ tính failed khi đã có kết quả cuối cùng theo deadline/policy. Message còn pending phải báo riêng, không lặng lẽ bỏ khỏi mẫu số.

**Deadline miss rate**

\[
E_{\text{deadline}} =
\frac{\text{Unique eventId chưa completed trong SLA}}{\text{Unique eventId đã offer}}
\]

Ngoài ra cần báo **duplicate delivery rate**, **redelivery rate**, **rollback rate** và **unknown commit outcome**. Đây là các tín hiệu quan trọng nhưng không nên cộng bừa vào một error rate duy nhất.

## 3. Percentile quan trọng hơn trung bình khi đánh giá tail latency

Giả sử có 100.000 mẫu latency đã sắp xếp tăng dần:

- **p50:** 50% message có latency không lớn hơn giá trị này; gần median.
- **p95:** 95% message hoàn thành trong hoặc dưới giá trị này; 5% chậm hơn.
- **p99:** 99% message hoàn thành trong hoặc dưới giá trị này; 1% chậm hơn.
- **p99.9:** tail sâu hơn; cần số mẫu đủ lớn và đo ổn định.

Ví dụ:

```text
Run X: p50 = 4 ms, p95 = 12 ms, p99 = 25 ms
Run Y: p50 = 3 ms, p95 = 18 ms, p99 = 240 ms
```

Run Y có median thấp hơn nhưng tail rất xấu. Nếu API cần phản hồi trong 100 ms, p99 = 240 ms có thể không chấp nhận được dù average rất đẹp.

### 3.1. Vì sao không chỉ báo cáo average?

Giả sử 99 message mất 5 ms và một message mất 2.000 ms:

\[
\text{average} = \frac{99 \times 5 + 2000}{100}
= 24.95\text{ ms}
\]

Average 24,95 ms che mất một message bị trễ 2 giây. p99 sẽ thể hiện tail này rõ hơn (tùy cách percentile và số mẫu).

### 3.2. Số lượng mẫu ảnh hưởng độ tin cậy của p99

- 100 mẫu: p99 gần như chỉ phản ánh một điểm cuối, rất nhiễu.
- 1.000 mẫu: chỉ có khoảng 10 mẫu ở 1% tail.
- 100.000 mẫu: có khoảng 1.000 mẫu ở 1% tail, hữu ích hơn để quan sát phân bố.
- 1.000.000 mẫu: tail có nhiều dữ liệu hơn, nhưng vẫn cần các lần chạy độc lập và điều kiện ổn định.

**Đừng công bố p99 với vài chục message.** Với benchmark ngắn, có thể báo p50/p95 cùng số lượng mẫu và đánh dấu p99 chưa đủ tin cậy.

### 3.3. Histogram phải giữ độ phân giải tail

Lưu mọi latency vào một list rồi sort có thể tốn RAM lớn. Dùng histogram có độ chính xác cấu hình rõ, ví dụ HDR Histogram, để ghi nhận phân bố theo logarithmic buckets.

Cần báo:
- Số mẫu.
- p50, p95, p99, p99.9 nếu đủ mẫu.
- min/max và mean (chỉ để bổ sung).
- Đơn vị, độ phân giải và phạm vi histogram.
- Số mẫu bị overflow/không ghi nhận, nếu có.

**Không chỉ ghi p99 từ một histogram bị reset giữa chừng hoặc có overflow mà không báo.**

## 4. Chống coordinated omission: load generator cũng có thể che mất latency

### 4.1. Closed-loop test

Một producer gửi một message, đợi kết quả/ACK rồi mới gửi message tiếp. Khi broker chậm, producer tự giảm tốc. Không có request mới được phát trong thời gian broker bị nghẽn, nên histogram có thể bỏ qua những thời điểm đáng lẽ hệ thống phải phục vụ thêm request.

Đây là **coordinated omission**: load generator phối hợp giảm tải theo độ trễ của hệ thống, làm tail latency nhìn tốt hơn thực tế.

Closed-loop vẫn hữu ích để đo **saturation throughput** và hiệu năng khi producer bị backpressure, nhưng không đại diện cho traffic có tốc độ đến độc lập với thời gian phản hồi.

### 4.2. Open-loop/rate-controlled test

Một generator phát message theo lịch cố định, ví dụ 5.000 message/s, bất kể message trước đã hoàn tất hay chưa:

```text
Expected arrival:
t=0ms    M1
t=0.2ms  M2
t=0.4ms  M3
...
t=200ms  M1001

Actual broker slow:
M1 hoàn tất 3ms
M2 hoàn tất 4ms
M3 hoàn tất 250ms
...
```

Open-loop giúp trả lời: “Nếu ứng dụng tiếp tục offer 5.000 message/s, p99 và backlog sẽ ra sao?” Cần ghi cả:
- **Scheduled/expected arrival time**.
- Actual send start/completion.
- Deadline miss và queue backlog.
- Số lần generator không kịp phát đúng lịch.

Có thể dùng HdrHistogram `recordValueWithExpectedInterval(...)` để hiệu chỉnh coordinated omission trong các harness closed-loop, nhưng cách tốt hơn cho SLA là lưu cả **scheduled arrival** và **actual completion** để phân tích đúng khoảng trễ. Không dùng hiệu chỉnh histogram như cách thay thế một load generator được thiết kế đúng.

## 5. Chốt workload contract trước khi tuning

Một benchmark chỉ có ý nghĩa khi các lần chạy giữ cùng điều kiện. Ghi lại ít nhất:

| Nhóm | Thông số cần cố định/ghi nhận |
| --- | --- |
| Broker | Classic/Artemis, version, JVM, heap, GC, persistence adapter/journal, broker config |
| Client | Client version, JMS namespace, protocol (OpenWire/Core/AMQP), connection count |
| Delivery | Persistent/non-persistent, priority, TTL, transaction, ACK mode |
| Payload | Bytes/message, phân bố kích thước, entropy/compressibility, body type |
| Concurrency | Producer count, consumer count, session/thread count, prefetch/window |
| Queue | Queue/topic, routing type, selectors, durable subscriptions, queue depth đầu/cuối |
| Transaction | Batch size, commit frequency, XA/local transaction |
| Storage | Disk/volume, filesystem, IOPS, fsync latency, journal settings, paging |
| Network | RTT, bandwidth, packet loss, TLS, container/VM topology |
| Consumer | Handler CPU, DB/API calls, processing delay, idempotency |
| Load | Offered rate, duration, warm-up, measurement window, run count |
| Outcome | Throughput, p50/p95/p99, operation/message error, duplicate, redelivery |

**So sánh Classic với Artemis phải cùng semantics**, không chỉ cùng payload. Nếu Classic dùng persistent+transaction+ACK còn Artemis dùng non-persistent+auto-ack, kết quả không thể dùng để kết luận broker nào nhanh hơn cho workload production.

## 6. Thiết kế ma trận benchmark thay vì chỉ chạy một kịch bản

### 6.1. Baseline tuần tự

Bắt đầu với:
- Một producer.
- Một consumer.
- Một queue.
- Một payload size.
- Một broker.
- Một transaction batch.
- Không selector, không priority, không network bridge.

Mục đích là kiểm tra harness và tìm baseline. Không dùng baseline đơn luồng làm kết luận năng lực tối đa của broker.

### 6.2. Thay đổi một biến tại một thời điểm

| Trục | Các mức thử gợi ý | Câu hỏi |
| --- | --- | --- |
| Payload | 256 B, 1 KiB, 10 KiB, 100 KiB | Chi phí per-message hay bytes/network đang giới hạn? |
| Producer | 1, 2, 4, 8, 16 | Broker scale ingress tới đâu? |
| Consumer | 1, 2, 4, 8, 16 | Dispatch/ACK có scale theo worker không? |
| Batch commit | 1, 10, 50, 100, 500 | Throughput tăng bao nhiêu, latency tail tăng bao nhiêu? |
| Delivery mode | NON_PERSISTENT vs PERSISTENT | Chi phí durability là bao nhiêu? |
| ACK | AUTO_ACK vs transacted commit | Chi phí ACK/transaction ảnh hưởng ra sao? |
| Protocol | Classic OpenWire, Artemis Core, AMQP 1.0 | Adapter/network stack ảnh hưởng thế nào? |
| Storage | Local SSD, volume thật, network storage | fsync/IOPS có phải bottleneck? |
| TLS | Off/on theo production | Chi phí mã hóa/handshake/CPU? |
| Network | Localhost, cùng AZ, cross-zone/WAN | RTT và throughput link tác động thế nào? |

Đổi nhiều biến cùng lúc khiến không thể biết nguyên nhân. Khi đã xác định baseline và bottleneck, chạy thêm factorial/load matrix để kiểm tra tương tác giữa concurrency, payload và storage.

### 6.3. Warm-up, measurement window và lặp lại

Một quy trình cơ bản:

1. Khởi động broker, đợi recovery/storage/acceptor ổn định.
2. Tạo queue chuyên dụng, kiểm tra queue trống.
3. Chạy **warm-up** 30–120 giây (hoặc số message cố định), không đưa vào báo cáo chính.
4. Đợi queue drain và hệ thống trở lại trạng thái ổn định.
5. Chạy measurement 60–300 giây ở mức tải đã định.
6. Lặp ít nhất 3–5 lần, cùng cấu hình và seed workload.
7. Báo median/range giữa các lần chạy, không chỉ chọn run tốt nhất.
8. Thu metric broker/JVM/disk/network cùng thời gian đo.
9. Kiểm tra queue backlog cuối; nếu chưa drain, throughput consumer không được gọi là completed workload.
10. Chụp config/version và log để người khác tái lập.

Warm-up quan trọng vì JIT, class loading, connection creation, disk cache và broker recovery có thể làm vài giây đầu khác steady state. Không đưa thời gian start broker vào throughput message nếu mục tiêu là steady-state; nếu đo cold-start, đó là benchmark riêng.

## 7. Đo p95/p99 đúng đồng hồ và đúng ranh giới

### 7.1. Cùng JVM: dùng `System.nanoTime()`

`System.nanoTime()` phù hợp đo duration vì monotonic, không bị đồng hồ hệ thống nhảy do NTP/time adjustment. Có thể ghi timestamp producer vào property và consumer đọc lại **nếu producer/consumer chạy cùng JVM**:

```java
long sentNanos = System.nanoTime();
message.setLongProperty("sentNanos", sentNanos);
producer.send(message);

// Consumer thread trong CÙNG JVM:
long latencyNanos =
        System.nanoTime() - message.getLongProperty("sentNanos");
```

Phép đo này bao gồm khoảng từ trước khi producer gọi send tới lúc consumer nhận message. Nếu producer transaction commit theo batch, nó còn bao gồm thời gian chờ commit batch — điều đó cần được ghi trong báo cáo.

### 7.2. Khác JVM/máy: không trừ hai `nanoTime()` với nhau

Giá trị `System.nanoTime()` chỉ có ý nghĩa so sánh trong cùng tiến trình/JVM; không truyền nó từ máy A sang máy B rồi trừ như một timestamp toàn cục.

Các lựa chọn:
- Đo **producer latency** ở producer và **consumer processing latency** ở consumer như hai histogram riêng.
- Đồng bộ wall clocks bằng NTP/PTP, đo sai số clock và tính end-to-end với sai số đã biết.
- Ghi scheduled arrival ở load generator và correlate event bằng `eventId`; thu timestamp ở các hop.
- Dùng tracing có clock correction khi cần phân tích distributed spans.

**Không báo p99 end-to-end xuyên máy với clock skew chưa được kiểm soát.**

### 7.3. Timestamp trước send hay sau send?

- Ghi trước `send()` → gồm thời gian serialization/send/commit và queue wait.
- Ghi sau `send()` trả về → bỏ phần thời gian send invocation; nếu producer transacted, message có thể chưa commit.
- Ghi sau producer `commit()` → đo từ broker-confirmed producer transaction đến consumer receive, nhưng timestamp phải được truyền/correlate chính xác.
- Ghi sau consumer ACK commit → đo completion latency thay vì receive latency.

Báo cáo phải nói rõ chọn mốc nào. Không đổi mốc giữa hai run rồi so p99.

## 8. Cấu hình broker để benchmark không vô tình đo sai

### 8.1. Artemis: queue ANYCAST và acceptor Core

Ví dụ fragment trong `broker.xml` của Artemis:

```xml
<acceptors>
    <acceptor name="core">tcp://0.0.0.0:61616?protocols=CORE</acceptor>
</acceptors>

<addresses>
    <address name="bench.orders">
        <anycast>
            <queue name="bench.orders" durable="true"/>
        </anycast>
    </address>
</addresses>
```

- `ANYCAST` phù hợp queue work distribution.
- Queue được provision trước để tránh lần đo đầu bao gồm auto-create/binding overhead.
- Dùng cùng journal/persistence configuration cho mọi run có mục tiêu so sánh durable.
- Ghi rõ `address-full-policy`/`max-size-bytes` và trạng thái paging. Nếu một run bắt đầu paging còn run khác không, latency/throughput không cùng điều kiện.
- Nếu dùng TLS/AMQP, cấu hình acceptor/client theo đúng protocol và đo handshake riêng hoặc tái sử dụng connection nhất quán.

### 8.2. Classic: OpenWire và KahaDB

Ví dụ fragment trong `activemq.xml` của ActiveMQ Classic:

```xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="bench-classic"
        persistent="true">
    <persistenceAdapter>
        <kahaDB directory="${activemq.data}/bench-kahadb"/>
    </persistenceAdapter>
    <transportConnectors>
        <transportConnector name="openwire"
                            uri="tcp://0.0.0.0:61616"/>
    </transportConnectors>
</broker>
```

Dùng store riêng cho từng run nếu cần cô lập; không xóa file KahaDB giữa lúc broker đang chạy. Nếu đo persistent throughput, giữ cùng delivery mode, transaction batch và disk policy.

### 8.3. Không để queue backlog cũ làm sai kết quả

Trước mỗi run:
- Queue phải trống hoặc có baseline backlog được ghi rõ.
- Không có consumer ngoài benchmark đang cạnh tranh.
- Không có durable subscription/topic khác giữ message.
- Không có bridge/network connector vô tình forward message ra broker khác.
- Không có scheduled/expired/DLQ message lẫn trong queue đo.
- Sau run phải biết số message đã enqueue, dequeue, pending và in-flight.

Nếu queue cuối run còn 2 triệu message, producer có thể đang nhanh hơn consumer; **producer throughput cao không đồng nghĩa hệ thống hoàn tất được workload**.

## 9. Maven và Java/Jakarta JMS benchmark baseline

Ví dụ dùng Artemis 2.50.0 Jakarta client và HdrHistogram. Chọn một phiên bản Artemis/client tương thích và cố định bằng BOM hoặc dependency management của dự án:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.artemis</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>2.50.0</version>
    </dependency>
    <dependency>
        <groupId>org.hdrhistogram</groupId>
        <artifactId>HdrHistogram</artifactId>
        <version>2.2.2</version>
    </dependency>
</dependencies>
```

Artemis 2.50.0 sử dụng Maven groupId `org.apache.artemis` và client artifact Jakarta. Code bên dưới dùng `jakarta.jms`. Nếu benchmark ActiveMQ Classic 5.18.x, client thường dùng `javax.jms`; cần adapter/source tương ứng và đúng client version. **Không trộn `javax.jms` với `jakarta.jms` trong cùng compile classpath rồi coi đó là cùng API.**

### 9.1. Baseline harness: một producer, một consumer, persistent, transacted

Mục tiêu:
- Một queue đã provision.
- Một producer gửi `BytesMessage` với payload kích thước cố định.
- Producer commit mỗi batch.
- Consumer đọc và kiểm tra payload, commit ACK theo batch.
- Latency histogram ghi từ **trước send** đến **consumer receive**, cùng một JVM.
- Throughput hoàn tất đo từ trước message đầu tiên đến sau consumer commit cuối.

```java
import jakarta.jms.BytesMessage;
import jakarta.jms.Connection;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.HdrHistogram.Histogram;

import java.util.Arrays;
import java.util.Random;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public final class BrokerPerformanceProbe {

    private static void require(boolean ok, String reason) {
        if (!ok) throw new IllegalStateException(reason);
    }

    private static void consume(
            ActiveMQConnectionFactory factory,
            String queueName,
            String runId,
            int count,
            int payloadBytes,
            int batchSize,
            byte[] expectedPayload,
            Histogram latency,
            CountDownLatch ready,
            CountDownLatch done,
            AtomicBoolean producerDone,
            AtomicBoolean abort,
            AtomicReference<Exception> consumerFailure,
            AtomicLong consumerEndNanos) throws Exception {

        try (Connection connection = factory.createConnection()) {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            MessageConsumer consumer = null;

            try {
                Queue queue = session.createQueue(queueName);
                consumer = session.createConsumer(queue);
                connection.start();
                ready.countDown();

                boolean[] seen = new boolean[count];
                int received = 0;
                int emptyPollsAfterProducerDone = 0;

                while (received < count && !abort.get()) {
                    Message raw = consumer.receive(1000);

                    if (raw == null) {
                        if (abort.get()) break;

                        if (producerDone.get()) {
                            emptyPollsAfterProducerDone++;
                            if (emptyPollsAfterProducerDone >= 30) {
                                throw new IllegalStateException(
                                    "Missing messages after producer completed");
                            }
                        }
                        continue;
                    }

                    emptyPollsAfterProducerDone = 0;
                    require(raw instanceof BytesMessage,
                            "Expected BytesMessage");

                    BytesMessage message = (BytesMessage) raw;
                    require(runId.equals(
                            message.getStringProperty("runId")),
                            "runId mismatch");

                    int sequence = message.getIntProperty("sequence");
                    require(sequence >= 0 && sequence < count,
                            "sequence out of range: " + sequence);
                    require(!seen[sequence],
                            "duplicate sequence: " + sequence);
                    seen[sequence] = true;

                    long bodyLength = message.getBodyLength();
                    require(bodyLength == payloadBytes,
                            "payload length mismatch: " + bodyLength);

                    byte[] actual = new byte[payloadBytes];
                    int read = message.readBytes(actual);
                    require(read == payloadBytes,
                            "BytesMessage truncated");
                    require(Arrays.equals(actual, expectedPayload),
                            "payload content mismatch");

                    long sentNanos =
                            message.getLongProperty("sentNanos");
                    long elapsedNanos =
                            System.nanoTime() - sentNanos;
                    require(elapsedNanos > 0,
                            "Invalid same-JVM latency sample");
                    latency.recordValue(elapsedNanos);

                    received++;
                    if (received % batchSize == 0
                            || received == count) {
                        session.commit();
                    }
                }

                if (received == count) {
                    consumerEndNanos.set(System.nanoTime());
                } else {
                    session.rollback();
                }

            } catch (Exception failure) {
                try {
                    session.rollback();
                } catch (Exception rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                if (consumer != null) consumer.close();
                session.close();
            }
        } finally {
            ready.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 6,
                "Usage: <brokerUrl> <queue> <runId> "
                + "<count> <payloadBytes> <batchSize>");

        String brokerUrl = args[0];
        String queueName = args[1];
        String runId = args[2];
        int count = Integer.parseInt(args[3]);
        int payloadBytes = Integer.parseInt(args[4]);
        int batchSize = Integer.parseInt(args[5]);

        require(runId.matches("[A-Za-z0-9_-]{1,32}"),
                "runId must be safe ASCII");
        require(count > 0 && count <= 1_000_000,
                "count out of range");
        require(payloadBytes > 0 && payloadBytes <= 1_048_576,
                "payloadBytes out of range");
        require(batchSize > 0 && batchSize <= count,
                "batchSize out of range");

        byte[] payload = new byte[payloadBytes];
        new Random(42).nextBytes(payload);

        Histogram latency =
                new Histogram(TimeUnit.HOURS.toNanos(1), 3);

        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(1);
        AtomicBoolean producerDone = new AtomicBoolean(false);
        AtomicBoolean abort = new AtomicBoolean(false);
        AtomicReference<Exception> consumerFailure =
                new AtomicReference<>();
        AtomicLong consumerEndNanos = new AtomicLong();

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        Thread consumerThread = new Thread(() -> {
            try {
                consume(factory, queueName, runId, count,
                        payloadBytes, batchSize, payload,
                        latency, ready, done, producerDone, abort,
                        consumerFailure, consumerEndNanos);
            } catch (Exception failure) {
                consumerFailure.set(failure);
                abort.set(true);
            } finally {
                done.countDown();
            }
        }, "benchmark-consumer");

        consumerThread.start();

        Exception producerFailure = null;

        try (Connection producerConnection =
                     factory.createConnection()) {

            Session producerSession = producerConnection.createSession(
                    true, Session.SESSION_TRANSACTED);
            MessageProducer producer = null;

            try {
                Queue queue = producerSession.createQueue(queueName);
                producer = producerSession.createProducer(queue);
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                require(ready.await(10, TimeUnit.SECONDS),
                        "Consumer did not become ready");

                require(!abort.get(),
                        "Consumer failed before measurement");

                // Connection/session/consumer setup nằm ngoài cửa sổ đo.
                long startNanos = System.nanoTime();

                try {
                    for (int i = 0; i < count; i++) {
                        require(!abort.get(),
                                "Consumer requested benchmark abort");

                        BytesMessage message =
                                producerSession.createBytesMessage();
                        message.writeBytes(payload);
                        message.setStringProperty("runId", runId);
                        message.setIntProperty("sequence", i);

                        // Chỉ so sánh nanoTime trong cùng JVM.
                        message.setLongProperty(
                                "sentNanos", System.nanoTime());

                        producer.send(message);

                        if ((i + 1) % batchSize == 0
                                || i + 1 == count) {
                            producerSession.commit();
                        }
                    }
                } catch (Exception failure) {
                    try {
                        producerSession.rollback();
                    } catch (Exception rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                    throw failure;
                } finally {
                    producerDone.set(true);
                }

                require(done.await(2, TimeUnit.MINUTES),
                        "Consumer did not finish within deadline");

                if (consumerFailure.get() != null) {
                    throw new IllegalStateException(
                            "Consumer failed", consumerFailure.get());
                }

                long endNanos = consumerEndNanos.get();
                long elapsedNanos = endNanos - startNanos;
                require(elapsedNanos > 0,
                        "Invalid measurement duration");

                double seconds = elapsedNanos / 1_000_000_000.0;
                double messagesPerSecond = count / seconds;
                double mibPerSecond =
                        (count * (double) payloadBytes)
                        / (1024.0 * 1024.0) / seconds;

                System.out.printf(
                    "completed=%d duration=%.3fs "
                    + "throughput=%.1f msg/s payload=%.2f MiB/s%n",
                    count, seconds, messagesPerSecond, mibPerSecond);

                System.out.printf(
                    "latency p50=%.3fms p95=%.3fms "
                    + "p99=%.3fms max=%.3fms samples=%d%n",
                    latency.getValueAtPercentile(50.0) / 1_000_000.0,
                    latency.getValueAtPercentile(95.0) / 1_000_000.0,
                    latency.getValueAtPercentile(99.0) / 1_000_000.0,
                    latency.getMaxValue() / 1_000_000.0,
                    latency.getTotalCount());

            } catch (Exception failure) {
                producerFailure = failure;
                abort.set(true);
                producerDone.set(true);
            } finally {
                if (producer != null) producer.close();
                producerSession.close();
            }

        } finally {
            producerDone.set(true);
        }

        if (!done.await(30, TimeUnit.SECONDS)) {
            abort.set(true);
            consumerThread.interrupt();
            throw new IllegalStateException("Consumer thread did not stop");
        }
        if (consumerFailure.get() != null) {
            throw new IllegalStateException(
                    "Consumer failed", consumerFailure.get());
        }
        if (producerFailure != null) {
            throw producerFailure;
        }
    }
}
```

### 9.2. Cách chạy và điều kiện bắt buộc

Ví dụ đối số `main`:

```text
tcp://localhost:61616 bench.orders run-001 100000 1024 100
```

Ý nghĩa:
- 100.000 message.
- Payload 1.024 bytes.
- Producer và consumer commit mỗi 100 message.
- Delivery mode PERSISTENT.
- Producer transaction commit và consumer transaction ACK.
- Một producer thread, một consumer thread.
- Timestamp producer/consumer ở cùng JVM.
- Throughput kết thúc sau khi consumer commit batch cuối.

**Queue phải được provision và trống trước run.** Nếu broker tắt auto-create, `session.createQueue()` chỉ tạo destination object phía client và có thể không tạo queue bền vững như bạn mong muốn. Hãy khai báo queue trên broker và xác nhận đúng routing/durability.

### 9.3. Đọc kết quả của harness đúng cách

`throughput` là **consumer-completed throughput** trong cửa sổ đo, vì đồng hồ kết thúc sau consumer commit cuối. Nó không phải maximum producer send rate.

`payload MiB/s` chỉ tính body bytes. Nó không phải network wire throughput: chưa cộng protocol headers, TLS framing, TCP/IP, retransmissions hoặc broker journal writes.

`latency p50/p95/p99` đo từ timestamp ngay trước `producer.send()` tới lúc consumer nhận body. Nó **không bao gồm thời gian consumer xử lý nghiệp vụ hoặc commit ACK cuối cùng**. Throughput có bao gồm consumer commit cuối; vì vậy hai metric có ranh giới khác nhau và cần ghi rõ.

`batchSize` ảnh hưởng cả throughput và latency:
- Batch lớn giảm số lần commit, thường tăng throughput.
- Message đầu batch chờ lâu hơn trước khi transaction producer commit, làm latency tăng.
- Consumer ACK theo batch cũng làm tăng thời gian message ở trạng thái delivering trước khi commit.
- Không chọn batch lớn nhất chỉ vì throughput cao; cần so p95/p99 và error rate.

**Giới hạn của code:** baseline một producer/consumer, closed-loop/saturation-style, không phải open-loop fixed-rate generator. Nó không đo operation error rate trong một run thất bại; khi có lỗi nó fail fast để không đưa một kết quả dở dang thành throughput hợp lệ. Phần 12 trình bày cách ghi error metrics cho harness tải thực.

## 10. Mở rộng lên nhiều producer/consumer mà không phá tính đúng của benchmark

### 10.1. Không chia sẻ JMS Session giữa threads

JMS `Session` và các producer/consumer được tạo từ session không phải đối tượng để nhiều thread dùng tùy ý. Mỗi worker nên có:
- Connection/Session riêng hoặc connection pool đã cấu hình rõ.
- Producer/consumer riêng.
- Transaction/ACK riêng.
- Worker ID và sequence riêng, event ID duy nhất.
- Histogram cục bộ, sau run mới merge.

Không tạo 16 threads rồi chia sẻ một `Session`; race và lock contention của client có thể làm benchmark đo lỗi sử dụng API thay vì năng lực broker.

### 10.2. Mẫu event identity khi nhiều producer

```text
runId = run-42
producerId = p-03
sequence = 000001234
eventId = run-42:p-03:000001234
```

Nếu chỉ dùng sequence bắt đầu từ 0 cho mọi producer, consumer không thể phân biệt message cùng số thứ tự. Dùng unique `eventId` và track count theo từng producer.

### 10.3. Gộp histogram

Với một consumer thread, `Histogram` có một writer nên không cần concurrent writes. Với nhiều consumer:
- Dùng một histogram riêng mỗi consumer, rồi merge sau khi dừng workers; hoặc
- Dùng `Recorder`/`ConcurrentHistogram` đúng API HdrHistogram để hỗ trợ ghi đồng thời.
- Không cộng p99 của từng worker để ra p99 toàn hệ thống. Phải **merge phân bố/sample buckets** rồi tính percentile trên histogram hợp nhất.

Ví dụ, worker A p99 = 10 ms và worker B p99 = 100 ms; average của hai p99 là 55 ms **không phải p99 của toàn bộ message**.

## 11. Đo open-loop theo tốc độ offer cố định

Khi SLA quy định “5.000 event/s với p99 < 100 ms”, cần generator có thể giữ tốc độ offer ngay cả khi broker chậm. Mỗi event có:
- `scheduledAtNanos`: mốc generator dự kiến phát.
- `actualSendAtNanos`: thời điểm thực tế bắt đầu send.
- `eventId` duy nhất.
- `deadlineNanos` hoặc deadline tương đối.

Pseudocode:

```java
long intervalNanos = 1_000_000_000L / targetRate;
long nextScheduled = System.nanoTime();

for (long sequence = 0; sequence < total; sequence++) {
    long scheduled = nextScheduled;
    waitUntil(scheduled); // park/scheduler có kiểm soát, không busy-spin
    long actual = System.nanoTime();

    if (actual - scheduled > allowedScheduleLatenessNanos) {
        scheduleLateCounter.increment();
    }

    sendWithProperties(sequence, scheduled, actual);
    nextScheduled += intervalNanos;
}
```

Đây là **pseudocode**, cần triển khai `waitUntil` bằng scheduler/park phù hợp và đo chính độ trễ của generator. Nếu producer send đồng bộ chặn lâu, generator có thể không đạt lịch; phải báo **offered rate**, **actual rate**, **schedule lateness** và backlog. Đừng ghi “target 5.000/s” như thể đã thực sự phát đủ 5.000/s.

Để đo end-to-end latency cùng JVM:

\[
L_{\text{scheduled}} = t_{\text{consumer receive}} - t_{\text{scheduled arrival}}
\]

Đây là latency từ thời điểm workload đáng lẽ được offer. So với:

\[
L_{\text{actual}} = t_{\text{consumer receive}} - t_{\text{actual send}}
\]

`L_scheduled` phản ánh cả thời gian generator bị trễ vì hệ thống bận; `L_actual` có thể bỏ qua phần đó và nhìn đẹp giả tạo.

## 12. Thiết kế error counters và phân loại kết quả

### 12.1. Counter tối thiểu

| Counter | Tăng khi | Không nhầm với |
| --- | --- | --- |
| `sendAttempts` | Bắt đầu một lần send | Unique message |
| `sendFailures` | `send()` ném lỗi | Commit transaction thất bại |
| `producerCommitFailures` | Commit transaction producer lỗi/timeout | Chắc chắn message chưa được ghi |
| `receiveTimeouts` | Receive hết deadline không có message | Message terminal failure |
| `validationFailures` | Sai body/type/sequence/schema/checksum | Broker transport failure |
| `consumerCommitFailures` | ACK/transaction commit lỗi | Chắc chắn message sẽ redeliver ngay |
| `redeliveries` | Delivery flag/count cho biết giao lại | Business duplicate |
| `duplicateEventIds` | Cùng eventId được quan sát nhiều lần | Nhiều operation retry |
| `reconnects` | Client kết nối lại | Broker crash duy nhất |
| `deadlineMisses` | Event chưa hoàn tất trong SLA | Terminal failure nếu còn pending |

Khi `commit()` timeout hoặc connection reset, kết quả có thể **unknown**: broker có thể đã commit nhưng client chưa nhận phản hồi. Không tự ghi nó là “message failed chắc chắn”; giữ trạng thái riêng và đối soát bằng `eventId`.

### 12.2. Tính error rate đúng

Ví dụ:
- 1.000.000 unique event IDs được offer.
- 999.500 được consumer ACK commit trong deadline.
- 300 unique IDs terminally failed.
- 200 IDs vẫn pending khi hết deadline.
- 500 operation retries đã thất bại tạm thời nhưng cuối cùng được xử lý.

Kết quả nên báo:

\[
E_{\text{terminal}} = 300/1{,}000{,}000 = 0.03\%
\]

\[
E_{\text{deadline}} = (300+200)/1{,}000{,}000 = 0.05\%
\]

Operation retry failures là **500 operation errors**, nhưng không có nghĩa 500 unique messages thất bại. Duplicate delivery được báo riêng.

### 12.3. Không loại bỏ timeout/exception khỏi histogram rồi tuyên bố p99 đẹp

Nếu chỉ ghi latency cho message hoàn tất nhanh và bỏ các message timeout:
- p99 có thể giảm giả tạo.
- Tỷ lệ deadline miss biến mất khỏi báo cáo.
- Run có broker lỗi nặng có thể nhìn “nhanh” vì chỉ vài message sống sót được đo.

Cần báo **latency của completed messages + deadline miss/timeout count + pending backlog**. Nếu muốn một SLA metric duy nhất, định nghĩa rõ event timeout là latency censored/deadline miss, không tự gán latency bằng 0.

## 13. Broker và JVM metrics phải thu đồng thời với load metrics

### 13.1. Broker metrics

**ActiveMQ Classic:**
- Queue `QueueSize`, `EnqueueCount`, `DequeueCount`, `InFlightCount`.
- Consumer count, producer count, dispatch rate.
- Store usage, temp usage, memory usage, KahaDB disk usage.
- NetworkConnector state, bridge reconnect, advisory demand nếu dùng network of brokers.
- JMX Broker/Queue/NetworkConnector MBeans.

**ActiveMQ Artemis:**
- Address/queue message count, delivering count, consumer count.
- Address memory usage và paging state/page store size.
- Journal/storage throughput, large-message store, disk usage.
- Acceptor/connection count, protocol/client metrics.
- Management API/JMX/console theo đúng version.

Không so trực tiếp tên metric khác nhau nếu semantics khác; mapping metric phải ghi trong benchmark report.

### 13.2. JVM/host metrics

- CPU user/system, run queue, context switch.
- Heap used/committed, allocation rate, GC pause/time.
- Direct/native memory và thread count.
- Disk IOPS, throughput, fsync/write latency, queue depth.
- Network bytes/s, RTT, packet loss/retransmit.
- Container CPU/memory throttling và cgroup limits.

Nếu CPU 25% nhưng disk fsync p99 tăng, persistent throughput vẫn có thể bị disk giới hạn. Nếu broker CPU thấp nhưng client CPU cao, load generator hoặc serialization có thể là bottleneck.

### 13.3. Đừng thu metric bằng cách làm benchmark chậm hơn

- JMX scrape quá dày hoặc dump thread/heap liên tục có thể gây overhead.
- Debug/TRACE protocol log có thể làm thay đổi latency đáng kể.
- Payload logging làm tăng CPU, allocation và I/O.
- Metrics exporter cần cùng cấu hình giữa các run.
- Nếu bật tracing, sampling và export path phải được ghi nhận; benchmark “tracing on” là workload khác “tracing off”.

## 14. Tìm bottleneck từ hình dạng throughput/latency

| Dấu hiệu | Nguyên nhân có thể | Phép thử tiếp theo |
| --- | --- | --- |
| Throughput tăng theo producer rồi plateau, CPU broker cao | CPU/dispatch/serialization bottleneck | Profile, tăng consumer/producer riêng, đo CPU per message |
| Throughput plateau, disk latency/fsync cao | Persistent journal/storage bottleneck | So sánh local SSD vs production volume, kiểm tra sync/IOPS |
| Producer nhanh, queue depth tăng liên tục | Consumer throughput thấp hơn ingress | Tăng consumer, đo handler, DB và ACK |
| p50 ổn nhưng p99 tăng mạnh | Queue buildup, GC pause, disk tail, network jitter, batch lớn | Correlate latency histogram với GC/disk/queue metrics |
| p95/p99 tăng cùng batch size | Chờ commit batch hoặc ACK batch | Giảm batch, đo throughput trade-off |
| Throughput giảm khi thêm consumer | Lock contention, DB downstream, prefetch, shared resource | Scale từng thành phần và profile |
| CPU client cao, broker thấp | Generator/serialization/hash/TLS/client thread | Chạy load generator riêng, giảm instrumentation, nhiều generator |
| Network bytes gần giới hạn link | Payload/headers/TLS/protocol overhead | Đo bytes/message, compression và network path |
| Paging bắt đầu rồi latency tail tăng | Address memory threshold vượt, disk page reads/writes | Đo page store, queue backlog và disk I/O |
| Error rate tăng ở tải cao | Timeout, resource limit, connection churn, broker overload | Giảm offered rate, tìm saturation point và error class |

**Bottleneck phải có bằng chứng tương quan**. Chỉ thấy p99 cao không đủ để kết luận disk là nguyên nhân; chỉ thấy CPU cao không đủ để kết luận tăng heap sẽ giải quyết.

## 15. So sánh ActiveMQ Classic và Artemis công bằng

### 15.1. Cố định semantics trước khi so

| Yếu tố | Classic run | Artemis run |
| --- | --- | --- |
| Message body | Cùng bytes/payload | Cùng bytes/payload |
| Delivery mode | PERSISTENT | PERSISTENT |
| Producer | Cùng số worker và transaction batch | Cùng số worker và transaction batch |
| Consumer | Cùng concurrency/handler | Cùng concurrency/handler |
| ACK | Cùng local transaction hoặc ACK mode | Cùng local transaction hoặc ACK mode |
| Storage | KahaDB và disk được ghi rõ | Artemis journal/paging và disk được ghi rõ |
| Protocol | OpenWire/client version ghi rõ | Core hoặc AMQP/client version ghi rõ |
| TLS/network | Cùng topology và policy | Cùng topology và policy |
| Workload | Cùng offered rate/payload distribution | Cùng offered rate/payload distribution |

Classic và Artemis có kiến trúc store, client, protocol adapter và metric khác nhau. Không kết luận “Artemis nhanh hơn X%” nếu:
- Một bên persistent, bên kia non-persistent.
- Một bên fsync mỗi commit, bên kia dùng policy khác.
- Một bên client chạy cùng máy broker, bên kia qua network.
- Một bên có consumer thật, bên kia chỉ đo send.
- Một bên đã paging, bên kia chưa paging.
- Client/JMS namespace/version hoặc batch size không tương đương.

### 15.2. Hai nhóm benchmark nên báo riêng

**Broker transport/persistence benchmark:** producer → broker → consumer, đo protocol, journal, ACK, storage.

**Application integration benchmark:** Spring/JMS, JSON serialization, validation, DB side effects, tracing, retries, network dependencies.

Không dùng một số liệu application end-to-end để tuyên bố riêng broker engine nhanh/chậm hơn; ngược lại không dùng microbenchmark broker để dự báo SLA business workflow.

## 16. Báo cáo benchmark nên có cấu trúc cố định

Mẫu báo cáo:

```text
Run ID:
Date/time:
Broker product/version:
Client library/version:
JMS namespace / wire protocol:
Host/VM/container and JVM:
Persistence/store and disk:
Queue/address and routing type:

Workload:
  producers:
  consumers:
  payload bytes distribution:
  delivery mode:
  transaction batch:
  consumer ACK mode:
  offered rate:
  duration / warm-up:
  TLS / network RTT:

Results:
  offered messages:
  producer committed:
  consumer ACK committed:
  throughput completed (msg/s):
  payload throughput (MiB/s):
  latency p50 / p95 / p99 / max:
  operation error rate:
  terminal message failure rate:
  deadline miss rate:
  duplicate / redelivery:
  pending / in-flight at end:

Resource:
  broker CPU / heap / GC:
  client CPU:
  disk IOPS / fsync latency:
  network throughput / retransmit:
  queue depth / paging / store usage:

Conclusion:
  saturation point:
  p99 target met?:
  error budget met?:
  bottleneck evidence:
  known limitations:
```

Ghi thêm **run count, median/range giữa các lần chạy, histogram sample count và raw result artifact**. Báo cáo không có workload/config thì không thể tái lập.

## 17. Ma trận kiểm thử nghiệm thu

| ID | Kịch bản | Tiêu chí PASS |
| --- | --- | --- |
| P1 | 1 producer/1 consumer, payload 1KiB | Count send commit = receive/ACK commit; không duplicate/missing |
| P2 | Warm-up rồi measurement độc lập | Warm-up không nằm trong histogram/report chính |
| P3 | Payload 256B/1KiB/10KiB/100KiB | Throughput message/s và MiB/s ghi cùng nhau |
| P4 | Batch 1/10/100/500 | p95/p99 và throughput đều được so, không chỉ max throughput |
| P5 | Producer concurrency tăng dần | Offered và achieved rate được phân biệt |
| P6 | Consumer concurrency tăng dần | Queue depth/in-flight/ACK throughput được ghi |
| P7 | Persistent vs non-persistent | Hai kết quả tách biệt, không so như cùng guarantee |
| P8 | Producer/consumer transacted | Commit/ACK boundary được xác định |
| P9 | Broker storage latency tăng | p95/p99 và throughput có tương quan metric disk |
| P10 | Broker paging/backlog tăng | Paging state, disk growth và latency tail được ghi |
| P11 | Open-loop fixed rate | Scheduled rate, actual rate, lateness và deadline misses được ghi |
| P12 | Error injection (broker restart/network reset) | Operation errors, unknown commit, redelivery và duplicate được phân loại |
| P13 | 3–5 repeated runs | Median/range, không chọn run tốt nhất |
| P14 | Classic vs Artemis | Delivery/ACK/persistence/protocol semantics tương đương |
| P15 | Queue cuối run | Pending/in-flight được báo, không giả định tất cả đã hoàn tất |
| P16 | p99 sample count | Đủ mẫu hoặc ghi rõ percentile không đủ tin cậy |

## 18. Checklist trước khi công bố “broker đạt X msg/s”

- [ ] Đã định nghĩa offered, producer committed và consumer completed throughput.
- [ ] Đã chốt điểm bắt đầu/kết thúc của từng latency metric.
- [ ] Có p50/p95/p99 và sample count; không chỉ average.
- [ ] Đã xem xét coordinated omission và loại load generator.
- [ ] Cùng-JVM `nanoTime` hoặc clock synchronization được xử lý đúng.
- [ ] Payload, body type, size distribution và delivery mode được cố định.
- [ ] Producer transaction/commit và consumer ACK boundary được đo.
- [ ] Queue được provision, sạch trước run; queue depth cuối được ghi.
- [ ] Không có consumer/bridge/background traffic ngoài ý muốn.
- [ ] Warm-up riêng, measurement window ổn định, nhiều lần chạy.
- [ ] Broker/JVM/disk/network metrics thu cùng thời gian.
- [ ] Operation errors, terminal failures, deadline misses, duplicate và redelivery tách riêng.
- [ ] Nếu commit timeout, kết quả unknown được giữ riêng, không tự tính là success/failure.
- [ ] Classic/Artemis dùng client, protocol và persistence semantics tương đương.
- [ ] Báo cáo có version/config/run ID để tái lập.

## 19. Câu hỏi tự kiểm tra

1. Vì sao `send()` trả về không nhất thiết là producer transaction đã committed?
2. Throughput producer committed khác consumer completed throughput ở đâu?
3. p99 = 30 ms có nghĩa mọi message đều dưới 30 ms không?
4. Vì sao p99 từ 100 message không đáng tin như p99 từ 100.000 message?
5. Coordinated omission làm closed-loop latency histogram lệch theo hướng nào?
6. Vì sao không được trừ `System.nanoTime()` từ hai JVM khác nhau?
7. Nếu queue cuối run còn 1 triệu message, có thể gọi producer rate là completed throughput không?
8. Tại sao operation error rate và message terminal failure rate có mẫu số khác nhau?
9. Một producer commit timeout có chắc chắn message chưa vào broker không?
10. Vì sao phải giữ cùng persistence, transaction và ACK semantics khi so Classic với Artemis?
11. Batch lớn thường tạo trade-off nào giữa throughput và p99?
12. Một run có p50 tốt nhưng p99 tăng đột biến cần kiểm tra những metric nào?
13. Payload MiB/s có phải network wire throughput không?
14. Vì sao histogram p99 của nhiều workers không thể lấy trung bình để ra p99 tổng?

**Gợi ý:** (1) transaction commit là ranh giới khác; (2) producer acceptance vs consumer ACK completion; (3) 99% không lớn hơn, 1% có thể chậm hơn; (4) tail sample quá ít; (5) thường đánh giá thấp tail khi generator ngừng offer lúc hệ thống chậm; (6) monotonic clock chỉ so duration trong cùng process; (7) không; (8) một message có thể có nhiều operation retry; (9) không, outcome có thể unknown; (10) tránh so workload khác nhau; (11) giảm commit overhead nhưng tăng chờ batch/tail; (12) GC, disk fsync, queue backlog, network, paging, timeout; (13) không; (14) percentile không tuyến tính, cần merge histogram.

## 20. Tài liệu tham khảo

- [Apache ActiveMQ Classic — Performance](https://activemq.apache.org/components/classic/documentation/performance): các yếu tố ảnh hưởng throughput/latency, persistence, batching và client tuning.
- [Apache ActiveMQ Classic — Producer Flow Control](https://activemq.apache.org/components/classic/documentation/producer-flow-control): backpressure, memory/store limits và hành vi producer.
- [Apache ActiveMQ Classic — JMX](https://activemq.apache.org/components/classic/documentation/jmx): broker/destination/queue metrics để đối chiếu.
- [Apache ActiveMQ Artemis — Performance Tuning](https://artemis.apache.org/components/artemis/documentation/latest/perf-tuning.html): journal, disk, batching, thread và tuning broker.
- [Apache ActiveMQ Artemis — Persistence](https://artemis.apache.org/components/artemis/documentation/latest/persistence.html): journal và durability settings.
- [Apache ActiveMQ Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging.html): address memory limit, page store và tác động của backlog.
- [HdrHistogram](https://github.com/HdrHistogram/HdrHistogram): histogram độ trễ, percentile và coordinated omission correction.
- [OpenJDK — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo elapsed time bằng đồng hồ monotonic.
- [JMS/Jakarta Messaging specification](https://jakarta.ee/specifications/messaging/): send, transaction, acknowledgment và semantics API.

> **Ghi nhớ:** Một benchmark đáng tin cậy phải đo **đúng workload và đúng ranh giới**. Throughput phải phân biệt message được offer, producer commit và consumer ACK; latency phải ghi p95/p99 với timestamp/clock hợp lệ; error rate phải tách operation failures, message failures, deadline misses và duplicate. Chỉ khi payload, persistence, transaction, concurrency, protocol, storage và measurement window được cố định, kết quả mới đủ cơ sở để so sánh ActiveMQ Classic với Artemis và đưa ra quyết định capacity/SLA.
