# Điều chỉnh prefetch, window và kích thước lô giao dịch

> **Chương:** Hiệu năng  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis; giao tiếp bất đồng bộ qua JMS, acknowledgment, transaction, redelivery, DLQ và vận hành broker.  
> **Mục tiêu:** Điều chỉnh **consumer prefetch**, **Core consumer/producer/confirmation windows** và **transaction batch size** dựa trên throughput, latency p95/p99, fairness, bộ nhớ và mức rủi ro rollback; không đổi các bảo đảm bền vững chỉ để có một kết quả benchmark đẹp.

## 1. Ba nút điều chỉnh trông giống nhau nhưng hoàn toàn khác phạm vi

Một queue `shipment.jobs` phục vụ hai worker. Worker A cần 25 ms cho mỗi job, worker B cần 5 ms. Producer gửi persistent JMS messages với payload trung bình 2 KiB qua mạng có RTT khoảng 30 ms. Có ba quyết định:

1. **ActiveMQ Classic prefetch:** cho phép broker dispatch/buffer trước **bao nhiêu message trên mỗi consumer**.
2. **Artemis Core consumer window:** cho phép broker gửi trước **bao nhiêu byte trên mỗi consumer**.
3. **JMS transaction batch:** ứng dụng thực hiện **bao nhiêu sends hoặc receives trước một lần commit/ACK**.

Hai window bổ sung của Artemis cũng cần phân biệt:

- `producerWindowSize` giới hạn **producer credit tính bằng byte** khi gửi dữ liệu tới broker.
- `confirmationWindowSize` kiểm soát **buffer confirmation cho Core command/session reattachment**; không phải consumer prefetch hoặc số message mỗi JMS transaction.

~~~mermaid
flowchart LR
    P["Producer: send batch N"] --> PW["Producer credits: window bytes"]
    PW --> Q[("Broker queue")]
    Q --> CW["Consumer: Classic prefetch count / Artemis window bytes"]
    CW --> W["Worker xử lý message"]
    W --> TX["commit sau N deliveries"]
    TX -.->|"ACK/transaction"| Q
~~~

Nếu worker B nhanh hơn A, prefetch/window quá lớn có thể giữ nhiều message tại A trong khi B rảnh. Nếu window quá nhỏ, mỗi message tốn thêm lần lấy dữ liệu từ broker. Nếu transaction batch quá lớn, một crash có thể làm nhiều message **chưa ACK** bị redeliver dù side effect đã thực thi.

**Không tồn tại một bộ thông số luôn tối ưu** cho throughput, fairness, latency, memory và recovery. Phải chọn theo ngữ nghĩa nghiệp vụ rồi xác minh.

### Kết quả cần đạt

Sau bài học, bạn có thể:

- Chọn đúng option trên **Classic 5.x** so với **Artemis Core/Jakarta JMS**.
- Giải thích đơn vị: **messages** với Classic prefetch; **bytes** với Artemis consumer/producer windows.
- Biết chính xác điểm `JMSContext.commit()` hoặc `Session.commit()` có vai trò gì khi gửi/nhận theo lô.
- Đo throughput, phân vị **commit duration**, queue `delivering/unacknowledged`, fairness giữa hai workers và lượng message bị replay khi crash.
- Dựng benchmark giữ nguyên payload, số consumer, persistence, journal, network, security và ACK semantics.

## 2. Classic prefetch: message-count buffer của consumer

### 2.1. Dispatch trước và vấn đề consumer giữ message

ActiveMQ Classic dùng cơ chế push: broker dispatch message trước tới client để tránh một round trip mạng cho từng lần `receive()`. `prefetchSize` là số **message trên mỗi consumer**, không phải byte.

Tài liệu chính thức Classic nêu mặc định **queue prefetch = 1000**, nhưng default cho topic/durable topic khác theo version và một số trang tài liệu của Classic có số khác nhau. Do vậy chỉ chốt con số sau khi xem **broker + client Classic đúng phiên bản**.

~~~text
Queue backlog có 2.000 jobs.
    ├── Worker A: chậm, có thể giữ nhiều jobs đã dispatch.
    └── Worker B: nhanh, có thể đang rảnh vì message nằm ở A.

High prefetch -> ít request hơn, nhưng in-flight/hoarding lớn hơn.
Low prefetch  -> tăng fairness, nhưng tốn thêm round trips.
~~~

**Lưu ý:** Một consumer được prefetch 1000 message không có nghĩa code Java xử lý 1000 message đồng thời. Một session/worker có thể vẫn xử lý lần lượt; các message kia chỉ nằm trong buffer hoặc trạng thái dispatched.

Theo mô tả Classic, khi đã dispatch đủ mức prefetch, broker cần consumer ACK một phần (tài liệu nêu khoảng 50% prefetch) mới top-up thêm. Cơ chế này giảm overhead network nhưng khiến consumer xử lý chậm giữ nhiều message chưa được worker khác nhận.

### 2.2. Cấu hình ConnectionFactory với Classic 5.x

Ví dụ ActiveMQ Classic OpenWire client; các phiên bản Classic **5.x** dùng `javax.jms.*`:

~~~java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

ActiveMQPrefetchPolicy prefetch = new ActiveMQPrefetchPolicy();
prefetch.setQueuePrefetch(10);
factory.setPrefetchPolicy(prefetch);

// Sau đây mới tạo Connection/Session/MessageConsumer.
~~~

Cũng có thể đặt trên connection URI:

~~~text
tcp://127.0.0.1:61616?jms.prefetchPolicy.queuePrefetch=10
~~~

Hoặc dùng destination option riêng của Classic trên đúng consumer queue:

~~~java
import javax.jms.Queue;
import javax.jms.Session;

Queue q = session.createQueue(
    "shipment.jobs?consumer.prefetchSize=10");
var consumer = session.createConsumer(q);
~~~

**Không dùng** URI `?jms.prefetchPolicy.queuePrefetch=10` của Classic với Artemis Core Jakarta client và mong điều chỉnh byte-window. Đây là hai API/provider khác nhau.

### 2.3. Prefetch 0, 1, 10 và 1000 dùng khi nào?

| Classic queue prefetch | Tác dụng | Trường hợp đáng thử |
|---:|---|---|
| **0** | Pull một message mỗi lần theo nhu cầu | Consumer rất chậm, hạn chế buffer; có chi phí request |
| **1** | Hạn chế dispatch trước | Job lâu, nhiều replica không đồng tốc |
| **10** | Buffer nhỏ, bớt round trip | Workload vài ms, ưu tiên fairness |
| **100–1000** | Buffer lớn để tăng throughput | Consumer nhanh, network RTT đáng kể |
| **Rất lớn** | Client giữ nhiều message hơn | Chỉ sau benchmark heap, fairness, failover |

**Prefetch=1 không phải distributed lock** và không cam kết business FIFO qua crash/redelivery. Nếu một consumer đã nhận nhưng chưa ACK, consumer khác vẫn có thể nhận/commit message khác tùy dispatch, rollback, priority và số worker.

### 2.4. Optimized ACK và prefetch không thay thế transaction

Classic có `optimizeAcknowledge` cho AUTO_ACKNOWLEDGE. Tùy client/version, nó có thể gom ACK thay vì gửi một xác nhận cho mỗi message; các tài liệu Classic khác nhau về ngưỡng chính xác. Đây **không** phải `Session.SESSION_TRANSACTED`.

Cần phân biệt:

- `AUTO_ACKNOWLEDGE`: session/provider tự ACK theo semantics của JMS.
- `DUPS_OK_ACKNOWLEDGE`: cho phép ACK lười hơn, có thể tăng duplicate.
- `CLIENT_ACKNOWLEDGE`: `Message.acknowledge()` thường xác nhận **cộng dồn** những message đã nhận trong cùng session.
- `SESSION_TRANSACTED`: **chỉ `commit()` hoặc `rollback()`** mới kết thúc transaction; prefetch không thay đổi điều này.

Nếu muốn benchmark **transaction batch**, bắt buộc tạo transacted session và thực sự gọi `commit()`; đừng đếm số lần `receive()` rồi tự nhận tất cả đã được ACK.

### 2.5. Pooled consumer và cân bằng tải

Trong ứng dụng dùng consumer cache/pool, một consumer đã được dispatch nhiều message có thể tiếp tục giữ buffer dù business code tạm dừng. Đóng wrapper consumer trong pool không nhất thiết nhả ngay các message đã prefetch. Với Spring JMS DMLC, số consumer, cache level, thread pool và prefetch cùng tác động lên phân phối.

Khi so sánh hai mức prefetch, **giữ nguyên số consumer connections và số worker threads thật**, không chỉ giữ nguyên số pods.

## 3. Artemis consumerWindowSize: flow control theo byte

### 3.1. Ý nghĩa và giá trị

ActiveMQ Artemis Core/JMS client nhận message qua consumer-side buffer. Tham số `consumerWindowSize` tính bằng **byte message**:

| Giá trị | Ý nghĩa | Đánh đổi |
|---:|---|---|
| `-1` | Không giới hạn client-side consumer buffer theo window | Có thể tăng throughput nhưng dễ OOM/hoarding khi consumer chậm |
| `0` | Không buffer trước; client nhận theo nhu cầu | Fairness tốt hơn cho slow consumers nhưng round trips tăng |
| `65536` | Window khoảng 64 KiB | Dải thử nhỏ |
| `262144` | Window khoảng 256 KiB | Dải thử trung bình |
| `1048576` | Window 1 MiB | Default Core thông dụng, nếu client/broker không override |

Dưới điều kiện message body 2 KiB và không tính metadata, window 1 MiB có thể tương đương khoảng **512 message** trong buffer. Nếu mỗi message 64 KiB thì khoảng **16 message**. **Không lấy đây là giới hạn chính xác**: Core tính size/credits theo representation, overhead, buffer state và batching.

### 3.2. Cấu hình Artemis Jakarta ConnectionFactory

~~~java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

factory.setConsumerWindowSize(64 * 1024);  // 64 KiB, BYTES
factory.setProducerWindowSize(256 * 1024); // 256 KiB, BYTES

// Tạo JMSContext/consumers sau khi cấu hình factory.
~~~

Artemis connection URI cũng có thể dùng:

~~~text
tcp://127.0.0.1:61616?consumerWindowSize=65536
~~~

**Không nhầm `consumerWindowSize=10` với Classic `queuePrefetch=10`.** 10 byte không có ý nghĩa giống 10 message; với message lớn, buffer byte có ngưỡng và cơ chế xử lý sizing khác.

### 3.3. Giá trị mặc định tại address-setting của broker

Trong `ARTEMIS_INSTANCE/etc/broker.xml`, bên trong **section `<address-settings>` đã có**:

~~~xml
<address-setting match="perf.orders">
    <default-consumer-window-size>65536</default-consumer-window-size>
</address-setting>
~~~

- Chỉ là default consumer Core window cho address match, không phải giới hạn memory của broker.
- Client đặt `setConsumerWindowSize(...)` hoặc URL explicit có thể **override** broker default.
- Không tạo address-setting khác cùng match khiến quy tắc bị mâu thuẫn; giữ nguyên DLQ/expiry/paging policy trên instance khi thí nghiệm.
- Với AMQP/STOMP hoặc giao thức khác, kiểm tra option riêng; không suy tên và đơn vị tương đương.

### 3.4. Vì sao window nhỏ cải thiện fairness?

Hai consumers tranh queue; worker A xử lý 25 ms/job, B xử lý 5 ms/job:

- Window lớn: A có thể giữ nhiều message được dispatch. B xử lý xong buffer của mình nhưng không lấy lại ngay message còn in-flight ở A.
- Window nhỏ/0: ít message bị đẩy trước sang A, broker giữ nhiều job ready cho B; thường tăng fairness và giảm client memory.
- Đổi lại, request/response network thường nhiều hơn khi client phải xin message theo nhu cầu.

**Window 0 không tạo exclusive consumer.** Nó cũng không điều khiển số thread do application tự tạo; nếu callback đưa dữ liệu vào executor song song, business commit vẫn có thể đảo thứ tự.

## 4. Artemis producerWindowSize và confirmationWindowSize: không phải một cửa sổ

### 4.1. Producer window: credits lúc gửi

Core producer nhận credits để gửi message tới broker. `producerWindowSize` là lượng byte có thể gửi trong một cửa sổ trước khi cần thêm credits; nó hạn chế producer dồn dữ liệu lên kết nối hay broker khi destination chậm.

~~~java
factory.setProducerWindowSize(256 * 1024);
~~~

Nếu window quá nhỏ, `send()` phải chờ credits nhiều hơn. Nếu quá lớn hoặc `-1` (tắt giới hạn cửa sổ này), lượng dữ liệu in-flight/buffer lớn có thể làm memory pressure cao, đặc biệt khi broker đang paging hoặc dùng `address-full-policy=BLOCK`.

**Không được hiểu:** `producerWindowSize=256 KiB` không làm queue chỉ chứa tối đa 256 KiB. Quota của một address là `max-size-bytes`/`max-size-messages` bên broker, và giới hạn disk là chuyện khác.

### 4.2. Confirmation window: khôi phục lệnh Core sau mất kết nối

Artemis Core `confirmationWindowSize` kiểm soát vùng đệm commands chưa được remote xác nhận để phục vụ **session reattachment**. Đây không phải window tiêu thụ message hay kích thước lô JMS transaction:

~~~java
// Chỉ cấu hình sau khi xem yêu cầu reconnection/reattachment.
factory.setConfirmationWindowSize(256 * 1024);
~~~

Theo manual Artemis, giá trị mặc định `-1` tắt việc giữ buffer phục vụ reattachment; client phải reconnect thay vì reattach transparent trong tình huống tương ứng. Tăng kích thước confirmation window không đồng nghĩa giảm số lần `commit()`.

| Cấu hình | Đơn vị | Tầng | Thực sự ảnh hưởng |
|---|---|---|---|
| Classic `queuePrefetch` | Message count | Classic consumer | Prefetched messages mỗi consumer |
| Artemis `consumerWindowSize` | Byte | Core consumer | Message buffering trước lúc nhận |
| Artemis `producerWindowSize` | Byte | Core producer | In-flight credits khi gửi |
| Artemis `confirmationWindowSize` | Byte | Core connection | Command confirmation/re-attachment |
| `JMSContext.commit()` mỗi N | Message count/time | JMS application | Transaction boundary, ACK/rollback |

**Không copy confirmation-window-size của Core bridge** để thay consumer window: bridge có đường forwarding và confirmation flow control riêng.

### 4.3. Không suy đồng nhất giữa Core, OpenWire, AMQP, STOMP

AMQP 1.0 dùng link credit với semantics theo delivery, trong khi Artemis Core consumer window tính byte. Artemis STOMP có header `consumer-window-size` theo byte; legacy `activemq.prefetchSize` có thể được Artemis chấp nhận nhưng vẫn **diễn giải theo byte** cho STOMP. Vì vậy luôn ghi **broker, client, protocol, version và đơn vị** bên cạnh các benchmark numbers.

## 5. Transaction batch: số sends/receives trước một lần commit

### 5.1. Producer: batch persistent sends

Trong JMS `SESSION_TRANSACTED`:

~~~java
var producer = context.createProducer()
    .setDeliveryMode(DeliveryMode.PERSISTENT);

for (int seq = 1; seq <= 100; seq++) {
    producer.send(queue, context.createTextMessage("job-" + seq));
}
context.commit(); // 100 sends nằm trong một transaction.
~~~

Nếu `commit()` thành công, broker xác nhận transaction gửi theo durability policy. Nếu sender chết trước commit, không được tính cả lô là đã publish xong. Nếu sender mất response **đúng lúc commit**, outcome có thể **chưa xác định từ phía client**: broker có thể đã commit mà client tưởng chưa xong.

**Lợi:** giảm round trips/chi phí journal sync tính trên mỗi message.  
**Hại:** message đầu batch phải chờ tới commit, transaction giữ dữ liệu lâu hơn, lỗi cuối batch có thể ảnh hưởng cả lô.

### 5.2. Consumer: gom xác nhận trong một transaction

~~~java
// context đã được tạo ở chế độ SESSION_TRANSACTED.
for (int i = 0; i < 20; i++) {
    Message message = consumer.receive(1000);
    if (message == null) break;
    processIdempotently(message);
}
context.commit(); // ACK cho deliveries nhận trong transaction.
~~~

Khi consumer chết hoặc rollback trước commit, broker có thể redeliver **toàn bộ những message chưa ACK** trong transaction. Nếu code đã ghi DB cho 19/20 message thì side effect có thể bị lặp sau restart; luôn dùng idempotency key nghiệp vụ.

**Không gọi `Message.acknowledge()` thay cho `commit()` trong transacted session rồi tưởng batch đã hoàn tất.** Đó là sai lầm đo hiệu năng: bạn có thể báo “đã nhận” hàng nghìn message nhưng queue chưa được ACK thật, gặp paging/depage stall hoặc rollback khi session đóng.

### 5.3. Batch size nên có ba giới hạn

Chọn lô theo **message count**, **estimated bytes** và **wall-clock time**:

~~~java
// Pseudocode, chạy trên chính thread sở hữu JMS session.
if (pendingCount >= 50
        || pendingBytes >= 512 * 1024
        || System.nanoTime() - batchStartedAt >= 200_000_000L) {
    session.commit();
    resetBatchCounters();
}
~~~

Dùng timeout `receive(...)` để có dịp commit khi workload nhàn; **không** tạo timer thread đồng thời gọi `Session.commit()` vào session đang nhận message trên thread khác.

Ví dụ lựa chọn:

| Tải | Lô 1 | Lô 20 | Lô 200 |
|---|---|---|---|
| Message 1 KiB, xử lý 0 ms | Nhiều overhead commit | Có thể cân bằng | Có thể tăng throughput, cần đo latency |
| Message 64 KiB, xử lý 5 ms | Ít giữ memory | 1.25 MiB payload/100 ms processing | 12.5 MiB payload/1 s processing |
| Message 1 KiB, xử lý 50 ms | ~50 ms + commit | ~1 s + commit | ~10 s + commit, replay scope lớn |

Các phép nhân là **ước lượng payload/processing**, không phải thời gian transaction chính xác, và không tính broker/network latency.

### 5.4. Cẩn trọng khi window quá nhỏ nhưng batch quá lớn

Consumer window 0 hoặc Classic prefetch 1 nhằm hạn chế message đang dispatch. Trong một số tổ hợp client/protocol/policy, lấy 100 messages nhưng **chưa ACK/commit** có thể chờ credits, timeout hoặc phải dựa vào prefetch extension. Không nên mặc định rằng broker luôn cho phép transaction vượt window.

**Quy tắc lab:** Khi Artemis `consumerWindowSize=0`, dùng **consumer batch=1**. Khi muốn batch 20–100, dùng window dương và benchmark tương tác ACK/credits. Lô cuối phải được commit khi idle/end-of-stream; không close session còn dữ liệu nhận chưa commit.

## 6. Ước lượng buffer, throughput và rollback exposure

### 6.1. Dựa vào throughput × RTT để chọn dải test

Giả sử mục tiêu một consumer 1.000 msg/s, RTT 150 ms, body trung bình 2 KiB:

~~~text
In-flight messages (network-only estimate):
  1000 msg/s × 0.150 s = 150 messages

In-flight payload:
  150 × 2 KiB = 300 KiB
~~~

Đây chỉ là **xấp xỉ lower bound** cho ý nghĩa network buffering, không phải công thức chọn window tuyệt đối. Sizing còn phụ thuộc metadata, encoding, ACK cadence, store latency, consumer processing và số sessions. Benchmark với 64 KiB, 256 KiB, 1 MiB đáng tin hơn việc đặt 64 MiB ngẫu nhiên.

### 6.2. Client memory không được bỏ qua

Classic: 12 consumers × 1000 prefetched messages × 4 KiB payload ≈ 46.9 MiB **chỉ payload**, chưa tính Java objects, protocol buffers, deserialization, tracing, threads. Artemis: 12 Core consumers × 1 MiB window có thể giữ khoảng 12 MiB message buffers theo cửa sổ danh nghĩa, nhưng không phải heap cap chính xác.

Nếu container memory thấp, tăng queue prefetch có thể khiến consumer JVM chịu GC/OOM trước khi broker báo đầy address.

### 6.3. Rollback exposure tăng khi batch lớn

200 messages × 50 ms processing tuần tự ≈ **10 giây giữ transaction** trước commit. Crash ở giây thứ 9 có thể khiến hàng trăm message chưa ACK phải xử lý lại, dù DB đã ghi nhiều side effects.

Đối với lệnh thanh toán, batch 1–5 có thể an toàn hơn batch 200 dù thông lượng thấp hơn; điều kiện quyết định là **SLO và business idempotency**. Không dùng throughput làm thước đo duy nhất.

## 7. Java 17 / Jakarta JMS lab: đo window, số commit và throughput thật

### 7.1. Artemis broker và ứng dụng thử

Mô hình: Artemis instance ở `tcp://127.0.0.1:61616`, Core acceptor bật, persistence phù hợp và một anycast queue riêng cho thử nghiệm. Trong `ARTEMIS_INSTANCE/etc/broker.xml`, **bên trong section `<addresses>` đã tồn tại**:

~~~xml
<address name="perf.orders">
    <anycast>
        <queue name="perf.orders">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Không tạo một section `<addresses>` thứ hai; không thử trên queue chứa dữ liệu cần giữ. Producer/consumer cần tài khoản có quyền send/consume; cung cấp `ARTEMIS_USER` và `ARTEMIS_PASSWORD` qua environment, không hardcode.

POM ví dụ cho Java 17, Jakarta JMS và Artemis Jakarta client tương thích broker:

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

Chọn client version hợp với broker/JDK thực tế. Các giá trị window/batch được đặt **trước khi tạo JMSContext**. Java code dưới đây dùng `SESSION_TRANSACTED`, có `commit()` thật cho **cả producer lẫn consumer**, không đánh lừa benchmark bằng việc chỉ đếm `receive()`.

### 7.2. Cú pháp

~~~text
PerfWindowBatchLab send <runId> <count> <batch> <payloadChars> <producerWindowBytes>
PerfWindowBatchLab recv <runId> <maxCount> <batch> <consumerWindowBytes> <workMs>

Ví dụ:
PerfWindowBatchLab send P01 2000 10 1024 262144
PerfWindowBatchLab recv P01 2000 10 65536 0
~~~

- `runId` có chữ/số, gạch nối hoặc gạch dưới, dài tối đa 40 ký tự; dùng runId khác cho mỗi lượt benchmark.
- `count` tối đa 5000 trong demo; `batch` 1..500; `payloadChars` 256..16384. ASCII `x` làm mỗi ký tự tương đương một byte UTF-8 payload; **wire size có overhead**.
- `producerWindowBytes >= 1` để không tắt flow control ở producer trong bài thử.
- `consumerWindowBytes` có thể `-1`, `0` hoặc số byte dương; `workMs` 0..100. Khi consumer window=0, batch phải là 1 để test không phụ thuộc tín dụng ACK chưa phát.
- `maxCount` ở `recv` là **giới hạn message một process sẽ nhận**, không phải bảo đảm broker đã có đủ message. Khi có hai consumers, số message được chia theo dispatch thực tế.

### 7.3. Một lớp mã nguồn hoàn chỉnh

File `PerfWindowBatchLab.java`:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class PerfWindowBatchLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String QUEUE = "perf.orders";

    public static void main(String[] args) throws Exception {
        if (args.length != 6 ||
                !("send".equals(args[0]) || "recv".equals(args[0])) ||
                !args[1].matches("[A-Za-z0-9_-]{1,40}")) {
            usage();
            return;
        }

        String mode = args[0];
        String runId = args[1];
        int count = Integer.parseInt(args[2]);
        int batch = Integer.parseInt(args[3]);
        int param = Integer.parseInt(args[4]);
        int extra = Integer.parseInt(args[5]);

        if (count < 1 || count > 5000 ||
                batch < 1 || batch > 500) {
            throw new IllegalArgumentException(
                "count phải 1..5000, batch phải 1..500");
        }

        boolean sending = "send".equals(mode);

        if (sending && (param < 256 || param > 16_384 ||
                extra < 1)) {
            throw new IllegalArgumentException(
                "send: payloadChars=256..16384, producerWindowBytes>=1");
        }
        if (!sending && (param < -1 || extra < 0 ||
                extra > 100 || (param == 0 && batch != 1))) {
            throw new IllegalArgumentException(
                "recv: consumerWindowBytes=-1/0/positive, "
                + "workMs=0..100, batch=1 khi window=0");
        }

        String user = requiredEnv("ARTEMIS_USER");
        String password = requiredEnv("ARTEMIS_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        if (sending) {
            factory.setProducerWindowSize(extra);
        } else {
            factory.setConsumerWindowSize(param);
        }

        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            if (sending) {
                send(ctx, runId, count, batch, param);
            } else {
                receive(ctx, runId, count, batch, extra);
            }
        }
    }

    private static void send(
            JMSContext ctx, String runId, int count, int batch,
            int payloadChars) throws Exception {

        Queue queue = ctx.createQueue(QUEUE);
        var producer = ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        String body = "x".repeat(payloadChars);
        List<Long> commitDurations = new ArrayList<>();
        int pending = 0;
        int committed = 0;
        long started = System.nanoTime();

        try {
            for (int seq = 1; seq <= count; seq++) {
                String eventId = runId + ":" + seq;
                TextMessage message = ctx.createTextMessage(body);
                message.setStringProperty("runId", runId);
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("seq", seq);

                producer.send(queue, message);
                pending++;

                if (pending >= batch) {
                    commitDurations.add(commitTimed(ctx));
                    committed += pending;
                    pending = 0;
                }
            }

            // Rất quan trọng: commit batch cuối chưa đủ N.
            if (pending > 0) {
                commitDurations.add(commitTimed(ctx));
                committed += pending;
                pending = 0;
            }
        } catch (Exception failure) {
            try {
                ctx.rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            // Commit timeout có thể là outcome bất định.
            throw failure;
        }

        report("send", committed, started, commitDurations);
    }

    private static void receive(
            JMSContext ctx, String runId, int limit, int batch,
            int workMs) throws Exception {

        Queue queue = ctx.createQueue(QUEUE);
        // runId đã được validate, không có dấu quote.
        JMSConsumer consumer = ctx.createConsumer(
            queue, "runId = '" + runId + "'");

        List<Long> commitDurations = new ArrayList<>();
        int pending = 0;
        int committed = 0;
        long started = System.nanoTime();

        try {
            while (committed + pending < limit) {
                Message message = consumer.receive(500);

                if (message == null) {
                    // Không đợi mãi để đủ batch nếu producer dừng.
                    break;
                }

                if (!(message instanceof TextMessage text)) {
                    throw new IllegalArgumentException(
                        "Lab chỉ nhận TextMessage");
                }

                String eventId =
                    text.getStringProperty("eventId");
                int seq = text.getIntProperty("seq");

                // Mô phỏng side effect tuần tự; production phải có
                // transaction DB + idempotency theo eventId.
                if (workMs > 0) {
                    Thread.sleep(workMs);
                }

                pending++;

                if (pending >= batch) {
                    commitDurations.add(commitTimed(ctx));
                    committed += pending;
                    pending = 0;
                }

                if (seq % 100 == 0) {
                    System.out.printf(
                        "pid=%d eventId=%s localCount=%d%n",
                        ProcessHandle.current().pid(),
                        eventId, committed + pending);
                }
            }

            // Không close session khi còn delivery uncommitted.
            if (pending > 0) {
                commitDurations.add(commitTimed(ctx));
                committed += pending;
            }
        } catch (Exception failure) {
            try {
                ctx.rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            consumer.close();
        }

        report("recv", committed, started, commitDurations);
    }

    private static long commitTimed(JMSContext ctx) {
        long before = System.nanoTime();
        ctx.commit();
        return System.nanoTime() - before;
    }

    private static void report(
            String mode, int count, long started,
            List<Long> commitNs) {

        double seconds =
            (System.nanoTime() - started) / 1_000_000_000.0;
        double rate = seconds > 0 ? count / seconds : 0.0;

        Collections.sort(commitNs);
        System.out.printf(
            "RESULT mode=%s committed=%d elapsed=%.3fs "
            + "rate=%.1f msg/s commits=%d "
            + "p50CommitMs=%.3f p95CommitMs=%.3f "
            + "p99CommitMs=%.3f%n",
            mode, count, seconds, rate, commitNs.size(),
            percentileMs(commitNs, 0.50),
            percentileMs(commitNs, 0.95),
            percentileMs(commitNs, 0.99)
        );
    }

    private static double percentileMs(
            List<Long> sortedNs, double quantile) {
        if (sortedNs.isEmpty()) return Double.NaN;

        int index = Math.max(0,
            (int) Math.ceil(quantile * sortedNs.size()) - 1);
        return sortedNs.get(index) / 1_000_000.0;
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu env " + key);
        }
        return value;
    }

    private static void usage() {
        System.out.println(
            "PerfWindowBatchLab send runId count batch "
            + "payloadChars producerWindowBytes");
        System.out.println(
            "PerfWindowBatchLab recv runId maxCount batch "
            + "consumerWindowBytes workMs");
    }
}
~~~

### 7.4. Diễn giải chỉ số do chương trình in

- `rate` là **số message mà process này đã nhận kết quả commit thành công chia cho thời gian chạy**, không phải throughput tối đa của toàn broker.
- `p50/p95/p99CommitMs` là **phân vị của thời gian mỗi lệnh `commit()`**, không phải p99 end-to-end latency của từng message. Một transaction 100 messages đóng góp **một lần đo commit**, không phải 100 mẫu latency.
- `commits` là số lô đã commit; nếu `batch=500` và `count=500` thì chỉ có **một mẫu latency**, p99 không có ý nghĩa thống kê.
- `receive(500)==null` chỉ nói chưa có message phù hợp trong 500 ms, không khẳng định queue rỗng. Với phép đo dài, cần harness có barrier, warm-up và expected count.
- Hai receiver cạnh tranh không có cam kết chia đều message; từng receiver sẽ log `committed` riêng. Tính tổng sau khi tất cả kết thúc.
- `JMSContext.close()` không dùng thay commit: nếu quên commit phần còn lại, message có thể bị rollback/redeliver và số liệu benchmark sai.
- Bài dùng `TextMessage` ASCII để đơn giản hóa; payload phải được sinh theo phân phối kích thước thật của production khi ra quyết định.

## 8. Thí nghiệm A: batch và chi phí commit

Giữ window giống nhau; mỗi lượt thử dùng runId mới và queue sạch:

| Lượt | Producer batch | Consumer batch | Consumer window | Payload | Work |
|---|---:|---:|---:|---:|---:|
| A1 | 1 | 1 | 1 MiB | 1 KiB | 0 ms |
| A2 | 10 | 10 | 1 MiB | 1 KiB | 0 ms |
| A3 | 50 | 50 | 1 MiB | 1 KiB | 0 ms |
| A4 | 200 | 200 | 1 MiB | 1 KiB | 0 ms |

Ví dụ chạy A2:

~~~text
PerfWindowBatchLab send A2 2000 10 1024 262144
PerfWindowBatchLab recv A2 2000 10 1048576 0
~~~

**Kỳ vọng để kiểm chứng, không phải kết quả đo sẵn:**

- Batch 1 tạo nhiều round trips/sync points, thường có overhead cao cho nhiều persistent messages nhỏ.
- Batch 10–50 có thể giảm overhead commit và tăng throughput.
- Batch 200 có thể không tốt hơn nhiều nếu journal/DB/network hoặc process memory đã nghẽn; message đầu batch chờ lâu và rollback scope tăng.
- Nếu consumer xử lý 20–100 ms/message, batch lớn giữ transaction nhiều giây; p99 business completion có thể xấu dù tốc độ commit tăng.

**Không thay** `journal-sync-transactional`, `persistence-enabled`, security, delivery mode hoặc connection count giữa A1–A4; nếu thay durability, throughput không còn so sánh công bằng.

## 9. Thí nghiệm B: window và fairness giữa hai worker

### 9.1. So consumer windows có cùng batch

| Lượt | Artemis consumerWindowSize | Consumer batch | Mục đích |
|---|---:|---:|---|
| B1 | 0 | 1 | Không buffer, ưu tiên fairness |
| B2 | 65536 | 1 | Buffer nhỏ để so cùng batch |
| B3 | 262144 | 1 | Buffer trung bình |
| B4 | 1048576 | 1 | Window 1 MiB |
| B5 | -1 | 1 | **Chỉ lab disposable**: memory/fairness khi không giới hạn |

Thử với batch=1 cho cả B1–B5 để **chỉ thay một biến**. Sau đó có thể lặp B2–B4 với batch=10 để xem tương tác batch/window; không lấy khác biệt B1 batch1 và B4 batch10 rồi quy hết cho window.

### 9.2. Dùng hai processes chậm và nhanh

1. Start worker chậm: `PerfWindowBatchLab recv FAIR01 200 1 1048576 20`.
2. Start worker nhanh: `PerfWindowBatchLab recv FAIR01 200 1 1048576 0`.
3. Khi cả hai đã đăng ký consumer, gửi: `PerfWindowBatchLab send FAIR01 200 10 1024 262144`.
4. Ghi mỗi PID đã commit bao nhiêu message, queue delivering count, oldest age và thời gian hoàn tất.
5. Lặp với runId mới `FAIR02`, đổi cả hai window xuống 65536 hoặc 0; batch vẫn 1, số worker/size/workload giữ nguyên.

**Giả thuyết:** window nhỏ hạn chế worker chậm giữ quá nhiều message trong buffer, giúp worker nhanh được phân phối thêm công việc. Nhưng không mặc định phải đạt **50/50**: phân phối hợp lý có thể lệch về worker nhanh, tùy broker dispatch, thời điểm connect và service time.

**Hạn chế của demo:** Worker `receive` có timeout 500 ms và có thể kết thúc trước khi producer bắt đầu nếu khởi chạy chậm. Trong phép đo nghiêm túc, dùng barrier/start signal và chờ đủ lâu; không coi timeout demo là dấu hiệu không có backlog.

### 9.3. Tại sao không để consumer window bằng -1 trong production?

Nếu consumer xử lý 25 ms/message, tăng buffer từ 1 MiB tới unbounded **không làm API kho nhanh hơn**. Nó chỉ có thể tăng message đang giữ bên client, RAM/GC và làm giảm khả năng worker khác nhận. Với message lớn hoặc stop-the-world GC, nguy cơ OOM và tăng p99 latency rõ rệt. B5 chỉ là thí nghiệm có monitor bộ nhớ và giới hạn message.

## 10. Thí nghiệm C: producer credits và backpressure

Giữ consumer window 256 KiB, send batch 10, payload 1 KiB, thử:

| Lượt | producerWindowBytes | Lý do |
|---|---:|---|
| C1 | 65536 (64 KiB) | Ít data in-flight, có thể nhiều lần xin credit |
| C2 | 262144 (256 KiB) | Điểm giữa |
| C3 | 1048576 (1 MiB) | Cửa sổ rộng hơn, có thể giảm credit waits |

Trong mạng local và broker đủ tài nguyên, khác biệt có thể nhỏ. Khi target đang paging, policy `BLOCK` hoặc RTT cao, hiệu ứng credit rõ hơn. Phải đo riêng `send()`/`commit()` latency, producer blocked time, queue age, broker address-full state và memory.

**Không nhầm:** producerWindowSize=64 KiB không giới hạn queue ở 64 KiB, cũng không thay thế `max-size-bytes` tại broker. Đừng tắt producer flow control chỉ để “đạt chỉ tiêu benchmark”.

## 11. Failure injection: batch và window cần được kiểm chứng khi lỗi

### 11.1. Consumer crash khi đã xử lý 49/50 message

Một consumer dùng batch=50 đã ghi DB cho 49 message nhưng chưa gọi JMS commit. Tiến trình chết:

1. Broker vẫn coi các delivery đó **chưa ACK** và có thể redeliver.
2. Những side effects đã commit ở DB không tự rollback cùng JMS.
3. Nếu không có unique business key/idempotency, các side effects có thể được làm lại.
4. Số message bị replay tối đa theo transaction chưa ACK có thể rất lớn nếu batch quá lớn.
5. Cần idempotency theo `(consumerGroup,eventId)`, kiểm tra version và DLQ/redelivery policy thích hợp.

### 11.2. Producer commit outcome bất định

Sender gửi 100 messages trong một transaction; broker nhận và commit, nhưng reply bị mất. Client ném exception; retry bằng eventIds mới tạo message nghiệp vụ trùng. Vì vậy phải:

- Giữ **eventId** của cùng lệnh qua retry.
- Dùng transactional outbox hoặc duplicate detection phù hợp để giảm duplicate producer.
- Cho consumer idempotent vì broker dedup không thay DB exactly-once.
- Ghi rõ batch nào **được client xác nhận** và batch nào có trạng thái không chắc chắn.

### 11.3. Window nhỏ + batch lớn gây chờ credits hoặc timeout

Nếu consumer chờ 100 deliveries rồi mới commit nhưng window không cho dispatch đủ khi thiếu ACK, nó có thể dừng ở receive timeout. Với Classic có prefetch extension tùy policy; với Artemis window 0, tránh batch lớn trong lab. Không phụ thuộc không kiểm chứng vào khả năng vượt prefetch/window.

Khi xử lý batch production, dùng **count + bytes + time cap**, commit phần còn lại khi idle, và giữ toàn bộ thao tác trên chính thread sở hữu session.

### 11.4. Prefetch không bảo đảm business FIFO

Consumer A được prefetched message 11–20 rồi crash; B có thể đã commit những message khác, còn 11–20 bị redeliver. Cần sequence number/grouping và idempotency để bảo vệ business ordering. Prefetch=1 hoặc window=0 chỉ thay số message đang bay, **không cấp exactly-once hoặc strict FIFO** khi nhiều consumers và failover.

## 12. Chẩn đoán: đừng nhầm nghẽn ở queue với nghẽn ở window

| Triệu chứng | Nghi vấn | Cách đo | Thay đổi thử |
|---|---|---|---|
| Worker nhanh rảnh, worker chậm giữ backlog | High prefetch/consumer window | Delivering count từng consumer, client buffer | Hạ Classic prefetch / Artemis window |
| Rate thấp khi RTT cao, CPU rảnh | Window quá nhỏ, nhiều round trips | RTT, receive wait p95/p99 | Tăng window từng mức |
| Client JVM heap/GC tăng | Window/prefetch quá lớn, message objects | Heap/GC profiling, in-flight | Hạ window/prefetch |
| Commit p99 tăng mạnh | Journal/DB sync hoặc batch size | Commit histogram, disk latency, batch bytes | Batch nhỏ hơn, xem store bottleneck |
| Producer send block | Thiếu credits hoặc broker `BLOCK` | Address-full, credit waits, paging | Phân biệt producer window và address quota |
| Consumer batch cuối không ACK | Quên commit remainder | Ready/delivering, transaction logs | Flush cuối, idle/timeout commit |
| Tốc độ có vẻ cao nhưng queue không giảm | Chỉ đo receive, không commit | Broker acknowledged count, redelivery | Sửa transacted benchmark |
| Crash làm nhiều message redeliver | Transaction consumer quá lớn | Delivery count, commit frequency | Giảm batch, idempotency |
| Setting Classic không có hiệu lực | Sai provider, consumer đã tạo/pool | Factory config, client protocol | Tạo lại consumer, dùng đúng option |
| Artemis default window không có hiệu lực | Client explicit override, wildcard khác | Actual client factory, broker config | Đồng bộ default/override |
| Throughput không tăng khi batch lớn | DB/API/CPU là bottleneck thật | Downstream p99, CPU, queue age | Tối ưu downstream/capacity |
| Latency kinh doanh xấu dù msg/s cao | Batch giữ message quá lâu | End-to-end event age, batch duration | Giảm time cap, batch size |

### 12.1. Metrics tối thiểu

**Producer:** send/commit rate, p50/p95/p99 commit duration, message size distribution, batch count/bytes, blocked time, retry/unknown outcomes.

**Broker:** queue ready/delivering, ACK/redelivery, address memory, paging, journal/DB flush latency, disk usage, consumer count, oldest message age.

**Consumer:** messages committed/s, processing duration, pending/unacked, commit frequency, client heap/GC, redelivery/DLQ, duplicate count.

**End-to-end:** eventId, thời điểm gửi committed, DB business committed và elapsed time. Dùng monotonic clock cho duration trong một process; nếu so timestamp giữa hosts, cần clock sync.

### 12.2. Quy trình benchmark đáng tin

1. Đặt SLO cụ thể: ví dụ throughput ≥ 2.000 msg/s, business p99 ≤ 300 ms, heap ≤ 512 MiB, rollback exposure ≤ 20 messages.
2. Ghi rõ broker/client/JDK/protocol, payload distribution, persistence, transactions/ACK, journal/DB backend, TLS, queue count, concurrency, RTT.
3. Chạy warm-up trước mỗi lượt; giữ queue lab sạch, không purge dữ liệu người dùng. Dùng runId riêng.
4. Thay từng biến **một lần**: window/prefetch, rồi batch, rồi producer window. Sau đó mới thử các tương tác.
5. Chạy đủ transactions để p99 có ý nghĩa; lặp nhiều lượt và ghi variance, không chọn lần nhanh bất thường.
6. So **số message thực được commit và ACK**, không chỉ số lần gọi send/receive.
7. Test failure injection trên môi trường disposable cho một số cấu hình tốt nhất; ghi khả năng recovery/duplicate.
8. Chọn cấu hình đáp ứng SLO với headroom và runbook revert, không tối đa throughput bằng mọi giá.

## 13. Điểm thử ban đầu theo workload

| Workload | Classic queue prefetch | Artemis consumer window | Consumer batch | Ưu tiên |
|---|---:|---:|---:|---|
| Consumer chậm, nhiều replicas | 1–10 | 0, 64 KiB | 1, 5 | Fairness, giảm giữ buffer |
| Consumer nhanh, message nhỏ | 100, 1000 | 256 KiB, 1 MiB | 10, 50 | Throughput/commit overhead |
| Message lớn 64 KiB–1 MiB | 1–10 | 64–256 KiB | 1–10 | Memory/GC, large-message path |
| Side effect nhạy cảm | 1, 10 | 0, 64 KiB | 1, 5 | Rollback risk, idempotency |
| RTT cao, CPU còn rảnh | 10, 100 | 256 KiB, 1 MiB | 10, 50 | Round trips vs in-flight |
| Producer thường gặp `BLOCK` | Không giải quyết trực tiếp | Đánh giá consumer độc lập; producer window 64–256 KiB | Theo SLO | Backpressure/credits |

Đây là **các giá trị khởi đầu để lập test**, không phải kết quả benchmark hay khuyến nghị production tuyệt đối.

### Spring JMS cần chú ý

- Với Classic, prefetch cấu hình trên **ActiveMQConnectionFactory/destination option**, không phải `@JmsListener` tự động có option portable.
- Với Artemis Core, cấu hình `consumerWindowSize` trên ConnectionFactory/URL, không copy `queuePrefetch` của Classic.
- `sessionTransacted=true` ở listener container thường quản lý **transaction mỗi listener invocation**, **không** tự gom 50 callbacks thành một JMS transaction chỉ vì prefetch=50.
- Muốn batch consumer thật cần một consumer loop/session transacted do bạn quản lý hoặc framework batch-capable có semantics được kiểm chứng; đừng gọi `commit()` trên JMS Session do container callback khác đang sở hữu.
- Thay Spring listener concurrency đồng thời thay số consumers và tổng buffer, nên phải ghi như một biến benchmark riêng.

## 14. Câu hỏi tự kiểm tra

1. Classic queue prefetch=100 còn Artemis consumerWindowSize=100 có tương đương không? **Không**: message count vs bytes.
2. Khi Artemis consumerWindowSize=0, nên thử batch 1 hay 100 trước? **1**, không phụ thuộc credit/ACK phức tạp.
3. `producerWindowSize=256 KiB` có làm queue chỉ lưu tối đa 256 KiB? **Không**, nó giới hạn send credits.
4. `confirmationWindowSize=256 KiB` có gây commit mỗi 256 KiB? **Không**, nó là confirmation/reattachment buffer.
5. Vì sao batch 200 có thể tăng throughput nhưng làm business p99 xấu? Message đầu chờ cả lô mới commit.
6. Consumer đã ghi DB cho 49/50 messages rồi crash trước JMS commit. Broker có thể redeliver những message nào? **Tất cả deliveries chưa ACK trong transaction**.
7. Producer mất commit reply, có nên gửi lại cùng nghiệp vụ với eventId mới không? **Không**, outcome bất định và cần dedup/outbox.
8. Worker B nhanh rảnh trong khi A giữ buffer lớn: thử chỉnh gì? **Giảm prefetch/window, đo fairness**.
9. Tăng prefetch trong Spring `@JmsListener` có tự tạo batch JMS transaction không? **Không**.
10. Vì sao benchmark đếm nhận mà không commit là sai? Queue vẫn pending, ACK/transaction chưa hoàn tất.
11. Prefetch=1 có bảo đảm strict FIFO qua nhiều worker/failover không? **Không**.
12. Muốn so 64 KiB và 1 MiB windows, phải giữ cố định những gì? **Payload, batch, concurrency, ack, storage, network, producer rate và load duration**.

## 15. Tài liệu chính thức và kết luận

- [ActiveMQ Classic — What is the Prefetch Limit For?](https://activemq.apache.org/components/classic/documentation/what-is-the-prefetch-limit-for): prefetch là message count, prefetch 0/1, destination option, fairness.
- [ActiveMQ Classic — Performance Tuning](https://activemq.apache.org/components/classic/documentation/performance-tuning): prefetch và optimized acknowledgment; đối chiếu số mặc định/threshold với phiên bản đang dùng.
- [ActiveMQ Classic — Per-Destination Policies](https://activemq.apache.org/components/classic/documentation/per-destination-policies): usePrefetchExtension và tương tác transaction.
- [Apache ActiveMQ Artemis — Flow Control](https://artemis.apache.org/components/artemis/documentation/latest/flow-control.html): consumerWindowSize theo byte, producer credits, rate limit.
- [Apache ActiveMQ Artemis — Performance Tuning](https://artemis.apache.org/components/artemis/documentation/latest/perf-tuning.html): batch sends/ACKs trong JMS transaction, journal/performance trade-off.
- [Apache ActiveMQ Artemis — Client Reconnection](https://artemis.apache.org/components/artemis/documentation/latest/client-reconnection.html): confirmationWindowSize và reattachment.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): default-consumer-window-size.
- [Apache ActiveMQ Artemis — Message Grouping](https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html): bảo vệ thứ tự theo group key khi có nhiều consumers.

**Kết luận:** **Classic prefetch** giới hạn **số message** có thể dispatch trước trên từng consumer; **Artemis Core consumerWindowSize** giới hạn **byte** được buffer, **producerWindowSize** giới hạn credits gửi, còn **confirmationWindowSize** dùng cho command confirmations/reattachment. **Transaction batch size** do ứng dụng đặt qua số send/receive giữa hai lần `commit()`, chi phối round trips, độ trễ và rủi ro rollback/redelivery. Chọn bằng phép đo có kiểm soát của **throughput, p99, fairness, memory và duplicate/recovery**, không bằng cách tăng vô điều kiện các tham số.
