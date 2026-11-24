# Test concurrency và ordering trong Spring Integration Adapters

## 1. Vấn đề thực tế: message đến đúng thứ tự nhưng kết quả vẫn sai

Trong module **SPRING_INTEGRATION_ADAPTERS**, Spring Integration nối các hệ thống ngoài bằng **inbound/outbound adapter**, **gateway**, **poller** và **MessageChannel**, đi qua File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Các flow có thể nhận nhiều thông điệp đồng thời, tách message sang những thread khác nhau, xử lý bất đồng bộ hoặc thử lại khi lỗi.

Giả sử đối tác gửi ba trạng thái cho đơn hàng O-274:

~~~text
sequence=1  CREATED
sequence=2  PAID
sequence=3  SHIPPED
~~~

Hệ thống nhận cả ba đúng thứ tự nhưng cho các worker xử lý song song:

~~~text
Nhận:       CREATED(1) --- PAID(2) --- SHIPPED(3)
Worker A:   CREATED(1) ---------------------- commit
Worker B:               PAID(2) -- commit
Worker C:                         SHIPPED(3) --- commit
Kết quả:   2, 3, 1
~~~

Nếu handler chỉ cập nhật trạng thái đơn theo sự kiện hoàn tất cuối cùng, kết quả có thể là CREATED dù đơn đã SHIPPED. Đây là một **ordering bug do concurrency**. Không thể sửa bằng cách kiểm tra mỗi MessageChannel có nhận đủ ba message hay không; cần chứng minh **thứ tự có ý nghĩa đối với nghiệp vụ** và **kết quả khi các bước hoàn tất lệch thứ tự**.

**Test concurrency và ordering** là việc kiểm tra khi nhiều message, nhiều producer/consumer, poller hoặc adapter chạy đồng thời, hệ thống có thỏa **quy tắc thứ tự, tính độc lập, nguyên tử, idempotency, giới hạn song song và phục hồi sau lỗi** hay không.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt thứ tự **arrival, enqueue, dequeue, start, completion, commit và observation**.
2. Mô tả bảo đảm ordering thực sự của **DirectChannel, QueueChannel, ExecutorChannel, PublishSubscribeChannel** và polling endpoint.
3. Chọn yêu cầu đúng: **global order**, **per-key order**, **causal order** hoặc **không cần order**.
4. Dùng **CountDownLatch, Semaphore, ExecutorService, QueueChannel, JUnit 5** để tạo test có điều khiển, ít phụ thuộc vào sleep.
5. Kiểm tra race condition, interleaving, duplicate, retry, crash/restart, backpressure và thread safety.
6. Đánh giá ordering của File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC trong luồng tích hợp.
7. Xây dựng một ma trận test, bằng chứng quan sát, runbook và checklist trước production.

## 2. Concurrency và ordering không đồng nghĩa

**Concurrency** nghĩa là nhiều công việc có thể cùng tồn tại hoặc tiến triển trong khoảng thời gian chồng lấp. **Parallelism** nghĩa là thực thi cùng lúc trên nhiều luồng/CPU. **Ordering** nghĩa là các sự kiện phải tuân theo một quan hệ trước–sau được định nghĩa.

| Khái niệm | Câu hỏi kiểm thử | Ví dụ |
|---|---|---|
| Arrival order | Sự kiện vào hệ thống theo thứ tự nào? | HTTP request A đến trước B |
| Enqueue order | Message được đưa vào channel/queue theo thứ tự nào? | send(M1) trước send(M2) |
| Dequeue order | Consumer lấy message theo thứ tự nào? | QueueChannel trả M1 rồi M2 |
| Start order | Handler bắt đầu xử lý theo thứ tự nào? | Worker 2 bắt đầu trước Worker 1 |
| Completion order | Handler hoàn tất theo thứ tự nào? | M2 xong trước M1 |
| Commit order | Thay đổi đã commit vào DB theo thứ tự nào? | Cập nhật version 2 trước version 1 |
| Publish order | Outbound gửi lên broker/topic theo thứ tự nào? | Kafka producer phát event A rồi B |
| Observation order | Hệ thống khác nhìn thấy kết quả theo thứ tự nào? | Client đọc được SHIPPED trước CREATED |

Hai message được dequeue theo FIFO **không bảo đảm** hai xử lý bất đồng bộ sẽ commit FIFO. Tương tự, hoàn tất handler không tự bảo đảm downstream HTTP hoặc Kafka đã nhận thành công.

### 2.1. Các kiểu yêu cầu thứ tự

| Kiểu | Ý nghĩa | Khi phù hợp |
|---|---|---|
| **Global order** | Mọi message có một thứ tự tổng thể duy nhất | Log đơn luồng, một số workflow toàn cục |
| **Per-key order** | Thứ tự phải giữ cho cùng orderId/accountId/tenantId | Trạng thái đơn hàng, số dư tài khoản |
| **Causal order** | Sự kiện phụ thuộc phải xảy ra sau điều kiện tiên quyết | Không SHIP trước PAYMENT_CONFIRMED |
| **Event-time order** | Xử lý theo thời gian nghiệp vụ trong payload | Sensor event đến muộn |
| **No ordering requirement** | Kết quả có thể độc lập với thứ tự | Xử lý thumbnail cho các ảnh độc lập |

Thường không cần global order cho hàng triệu đơn: **per-key ordering** có thể giữ chính xác trạng thái từng đơn mà cho phép các đơn khác xử lý song song. Nhưng phải thiết kế rõ cách xác định key và cách xử lý nhiều event có cùng sequence hoặc đến trễ.

### 2.2. Một thông điệp không phải một giao dịch

Spring Message có payload/headers; channel đưa Message tới endpoint. **Transaction** có thể bao một số bước DB/broker, còn network/HTTP/SFTP có side effect ngoài transaction đó. Test concurrency phải kiểm tra **quyết định nghiệp vụ đã commit** chứ không dừng ở việc channel đã nhận message.

### 2.3. Ordering và consistency

Ngay cả khi không có ordering guarantee ở transport, ứng dụng có thể vẫn đạt consistency nhờ **optimistic locking, expected version, idempotency, key-based partitioning, deduplication hoặc state machine**. Ngược lại, FIFO tại queue không bảo vệ được ứng dụng ghi đè dữ liệu cũ nếu nhiều thread cập nhật cùng bản ghi không kiểm tra version.

## 3. Xác định một hợp đồng ordering có thể kiểm thử

Trước khi viết test, trả lời bằng tài liệu yêu cầu:

1. **Key nào phải có thứ tự?** orderId, customerId, accountId hay global stream?
2. **Nguồn xác định thứ tự?** Sequence number, aggregate version, Kafka offset, timestamp hay counter nghiệp vụ?
3. **Thứ tự phải giữ đến điểm nào?** Dequeue, handler start, commit DB, publish event hay consumer observation?
4. **Cho phép message trùng không?** Nếu có, dedupe theo eventId hay key + version?
5. **Nếu thiếu một sequence?** Chờ, timeout, request replay, quarantine hay bỏ qua?
6. **Nếu message cũ đến muộn?** Bỏ qua nếu version cũ, lưu audit hay trigger compensation?
7. **Có thể xử lý song song các key khác nhau không?** Giới hạn tối đa bao nhiêu?
8. **Retry, crash và redelivery có thay thứ tự không?** Recovery nào chịu trách nhiệm?

### 3.1. Hợp đồng ví dụ cho OrderEvent

~~~json
{
  "eventId": "evt-274-3",
  "orderId": "order-274",
  "version": 3,
  "type": "SHIPPED",
  "occurredAt": "2026-11-23T08:00:00Z",
  "payload": {
    "trackingId": "track-274"
  }
}
~~~

Chính sách minh họa:

- Với mỗi orderId, version phải tiến **đơn điệu** từ version đã commit.
- Hai event có cùng eventId chỉ tạo hiệu ứng nghiệp vụ một lần.
- Version cũ không ghi đè state mới.
- Nếu thiếu version trung gian, lựa chọn chờ/quarantine/request replay được nêu rõ.
- Các orderId khác nhau được phép xử lý đồng thời.

Không lấy occurredAt làm thứ tự chính nếu đồng hồ giữa các producer không đồng bộ và network có thể làm message đến trễ. Timestamp hữu ích cho quan sát nhưng không đủ để chứng minh một trình tự nghiệp vụ.

### 3.2. Ký hiệu tiêu chí kiểm thử

Với cùng key K, các event được chấp nhận có version 1, 2, 3:

~~~text
Accepted(K, 1) precedes Accepted(K, 2) precedes Accepted(K, 3)
No final state transition from version 3 back to version 1.
Duplicate(K, eventId=X) does not duplicate side effects.
Unrelated(K2) may complete in parallel with K.
~~~

**Thứ tự được kiểm thử phải là thứ tự có bằng chứng ở điểm cam kết**: ví dụ committedVersion theo DB. Ghi log các lời gọi handler vào list trong bộ nhớ chưa đủ để suy ra DB transaction thực sự commit theo cùng thứ tự.

## 4. MessageChannel ảnh hưởng thứ tự như thế nào?

### 4.1. DirectChannel

DirectChannel thường gọi handler **đồng bộ trên thread gửi**. Với một producer tuần tự, các lời gọi send trả về theo thứ tự có thể giữ thứ tự xử lý cho đến khi flow chuyển sang async. Nhưng nếu **hai producer threads cùng send**, các lời gọi có thể xen kẽ. DirectChannel không biến mọi producer của cả ứng dụng thành một hàng đợi FIFO toàn cục.

### 4.2. QueueChannel

QueueChannel là **PollableChannel** có ngữ nghĩa hàng đợi. Với một producer và một consumer tuần tự, nó thuận tiện kiểm tra FIFO trong điều kiện queue không bị thay bởi priority/ordering policy khác. Khi **nhiều consumer cùng poll và xử lý**, thứ tự nhận không bảo đảm thứ tự hoàn tất/commit. Cũng phải xét capacity, timeout và độ bền của MessageStore.

### 4.3. ExecutorChannel

ExecutorChannel chuyển dispatch sang task executor. Nếu executor có nhiều worker, message có thể được xử lý đồng thời và **không có bảo đảm completion order**. FIFO ở work queue của executor (nếu có) chưa đủ chứng minh handler kết thúc FIFO. Task rejection, pool saturation và exception handling cũng ảnh hưởng test.

### 4.4. PublishSubscribeChannel

PublishSubscribeChannel có thể gửi cùng message tới nhiều subscribers. Nếu không cấu hình executor bất đồng bộ, việc dispatch thường diễn ra đồng bộ trong call stack sender; nếu có executor, các subscriber có thể chạy song song. **Không có một thứ tự nghiệp vụ duy nhất giữa các side effect của nhiều subscribers** trừ khi ứng dụng áp đặt điều kiện khác.

### 4.5. Những channel khác

| Channel | Khả năng đáng chú ý | Điều không nên suy ra |
|---|---|---|
| PriorityChannel | Ưu tiên message theo comparator/priority | FIFO tuyệt đối hoặc không starvation |
| RendezvousChannel | Trao message qua đồng bộ sender–receiver | Thứ tự commit ở downstream |
| FluxMessageChannel | Kết nối reactive streams | Ordering khi dùng flatMap hoặc scheduler song song |
| DirectChannel | Đồng bộ ở ranh giới gửi | Global order giữa nhiều senders |
| QueueChannel | Queue lưu message trước khi receive | Global completion order nếu nhiều workers |
| ExecutorChannel | Bàn giao qua executor | FIFO khi completion/commit |
| PublishSubscribeChannel | Fan-out tới nhiều subscribers | Một message chỉ có một consumer hoặc side effects có thứ tự |

Với reactive pipeline, các operator như concatMap và flatMap có ngữ nghĩa ordering khác nhau; khi dùng Spring Integration với Reactor cần kiểm chứng operator/scheduler thực tế thay vì suy theo tên channel.

### 4.6. Sơ đồ một ranh giới async

~~~mermaid
flowchart LR
    IN["Inbound message"] --> DC["DirectChannel"]
    DC --> TRANS["Transformer"]
    TRANS --> EC["ExecutorChannel"]
    EC --> W1["Worker 1"]
    EC --> W2["Worker 2"]
    EC --> W3["Worker 3"]
    W1 --> DB["DB / external side effect"]
    W2 --> DB
    W3 --> DB
~~~

Ở đoạn đầu, các bước có thể chạy tuần tự trong sender thread. Sau ExecutorChannel, **completion/commit order** phụ thuộc scheduling, thời gian xử lý, lock và transaction. Kiểm thử phải đặt assertion ở DB/outbound result khi đó là mục tiêu nghiệp vụ.

## 5. Poller và concurrency: maxMessagesPerPoll không phải maxThreads

Polling endpoint chủ động lấy message theo lịch, ví dụ File/SFTP/JDBC inbound source hoặc consumer của QueueChannel.

| Cấu hình | Liên quan tới | Không đồng nghĩa |
|---|---|---|
| fixedDelay/fixedRate/cron | Lịch đánh thức poller | Message được xử lý đúng order nguồn |
| maxMessagesPerPoll | Số message tối đa được lấy mỗi chu kỳ theo cấu hình | Giới hạn thread/parallelism |
| taskExecutor | Cách công việc được phân cho thread | FIFO completion |
| receiveTimeout | Chờ lấy message từ PollableChannel | Retry timeout của HTTP |
| transactional advice | Ranh giới transaction được bao | Atomicity trên mọi hệ thống ngoài |
| errorChannel/error handler | Nơi lỗi được publish nếu cơ chế hỗ trợ | Retry hoặc rollback tự động |

Nếu có nhiều pollers/instances trên cùng nguồn, dữ liệu có thể được claim theo thứ tự khác nhau. Với JDBC, thứ tự ORDER BY trong SELECT **không** thay cho cơ chế claim/locking. Với File/SFTP, thứ tự duyệt danh sách file hoặc thời điểm tải về chưa chắc thể hiện trình tự nghiệp vụ.

### 5.1. Kiểm tra chu kỳ poll

Test cần quan sát: số lần tick, message mỗi lần receive, số công việc đang chạy, thời gian kết thúc, trường hợp null receive và cách error handler phản ứng. Nếu poller không có dữ liệu hoặc bị dừng, sẽ không nhất thiết có ErrorMessage; cần heartbeat/last-successful-poll ngoài error counting.

### 5.2. Giới hạn đồng thời

Đặt một **giới hạn concurrency** có thể xác minh (ví dụ tối đa 4 công việc đang xử lý), rồi kiểm thử peak in-flight dưới tải. Đừng chỉ kiểm tra cấu hình threadPoolSize = 4: một flow có thể còn task executors khác, HTTP async callbacks hoặc nhiều application instances.

### 5.3. Thứ tự ở boundary cần được tuyên bố

Nếu File adapter phải xử lý lần lượt theo tên, cần ràng buộc nguồn, sorting/ready check, một consumer cho key tương ứng và không tách thread trái yêu cầu. Nếu chỉ cần final state đúng version, có thể xử lý song song và dùng optimistic concurrency trên DB.

## 6. Làm thế nào để test concurrency có thể lặp lại?

Kiểm thử concurrency khác unit test tuần tự vì lỗi thường phụ thuộc **interleaving**: một worker đọc state trước khi worker khác commit, một callback đến muộn hoặc một queue bị tranh chấp. Test đáng tin nên điều khiển các thời điểm quan trọng, không hy vọng hệ điều hành tình cờ tạo race.

### 6.1. Đồng bộ hóa có chủ đích

| Công cụ | Dùng để | Lưu ý |
|---|---|---|
| CountDownLatch | Chờ N bước hoặc mở cổng cho worker | Có timeout để test không treo vô hạn |
| CyclicBarrier | Buộc nhiều thread cùng đến một điểm trước khi tiếp tục | Xử lý broken barrier và timeout |
| Semaphore | Giới hạn hoặc quan sát concurrency | Không thay thế lock dữ liệu nghiệp vụ |
| ExecutorService | Chạy tác vụ đồng thời với pool định trước | Shutdown trong finally/teardown |
| AtomicInteger/AtomicLong | Đếm chính xác số task đang xử lý | Không thay DB transaction |
| ConcurrentHashMap | Giữ trạng thái thread-safe trong test | Không khẳng định cluster-wide consistency |
| QueueChannel.receive(timeout) | Đợi message từ channel có giới hạn | Chỉ assert loại và dữ liệu hợp lệ khi nhận |
| Awaitility hoặc polling assertion | Chờ eventual outcome nếu test có dependency phù hợp | Chờ có điều kiện, tránh sleep cố định |
| Fake service có gate/latch | Giả lập latency và thứ tự hoàn tất | Bảo đảm đóng gate ngay cả khi assert thất bại |

**Không dùng Thread.sleep(100) như một bằng chứng thứ tự.** Trên máy tải nặng, 100 ms có thể không đủ; trên máy nhanh test có thể pass vì may mắn dù implementation sai.

### 6.2. Hai cấp độ test

**Test kênh và handler:** xác minh behavior của DirectChannel, QueueChannel, ExecutorChannel trong Spring context hoặc trực tiếp bằng class channel. Nó tương đối nhanh và dễ điều khiển.

**Integration test adapter thật:** xác minh filesystem, SFTP server, HTTP server, broker hay database với cùng topology, transaction, concurrency và retry production. Bài test channel đơn lẻ không chứng minh Kafka offset, JMS acknowledgment hoặc JDBC commit đúng.

### 6.3. Định nghĩa oracle trước khi chạy

Một test tốt không chỉ ghi “kết quả có vẻ đúng”. Cần có **oracle** là điều kiện quan sát được:

- Hoàn tất đúng số lượng event được chấp nhận, trong deadline;
- Không có duplicate side effects dù input có redelivery;
- Với cùng key, committedVersion không giảm;
- Nếu policy đòi xử lý liên tiếp, version n+1 chỉ được commit sau n;
- Có tối đa N request đồng thời tới API;
- Với các key độc lập, hệ thống vẫn có throughput song song;
- Khi lỗi và restart, không mất event đã được đảm bảo durability;
- Với timeout chưa biết kết quả, không tạo side effect lần hai.

### 6.4. Chạy lặp và khuấy nhiễu

Sau các test có latch xác định, nên thêm **repeated/stress tests** với nhiều interleavings và số key lớn. Seed cố định giúp tái hiện dữ liệu; lưu seed trong báo cáo khi phát hiện lỗi. Tuy nhiên test 1.000 lần pass không chứng minh race không thể xảy ra: cần đi cùng **invariant, kiểm soát thread và transaction isolation**.

## 7. Test FIFO ở QueueChannel: điều đã được bảo đảm và điều chưa

Đầu tiên hãy kiểm chứng **thứ tự lấy message** trong trường hợp đơn giản một producer, một consumer. Đây là test cho hàng đợi, **không phải** chứng minh thứ tự completion của các worker.

### 7.1. JUnit 5: gửi và nhận tuần tự

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QueueChannelOrderingTest {

    @Test
    void oneProducerOneConsumerReceivesInFifoOrder() {
        QueueChannel input = new QueueChannel(3);

        for (int sequence = 1; sequence <= 3; sequence++) {
            assertTrue(input.send(
                    MessageBuilder.withPayload(sequence).build()));
        }

        for (int expected = 1; expected <= 3; expected++) {
            Message<?> actual = input.receive(1_000);
            assertNotNull(actual);
            assertEquals(expected, actual.getPayload());
        }
    }
}
~~~

Ví dụ dùng QueueChannel in-memory với capacity 3 và không có consumer khác. Nếu có nhiều producer, bản thân thứ tự enqueue phụ thuộc việc các lời gọi send được thực thi ra sao; không thể suy “event được tạo trước” chắc chắn được enqueue trước.

### 7.2. Khi thêm hai polling consumers

Hai consumer có thể lấy sequence=1 và sequence=2 theo FIFO nhưng consumer thứ hai hoàn tất sớm hơn:

~~~text
Queue: [1, 2]
Consumer A: receive 1 ---- slow DB write -------- commit(1)
Consumer B: receive 2 -- fast DB write -- commit(2)

Dequeue order: 1, 2
Commit order:  2, 1
~~~

Test phải đo **commit order** hoặc version cuối nếu đó là điều nghiệp vụ quan tâm. Tăng maxMessagesPerPoll hoặc task executor không tự giải quyết yêu cầu cùng key phải tuần tự.

### 7.3. Test nhiều producer

Nếu producer A và B cùng send, hãy gắn từng message một **producerId, sequenceInProducer** và một event ID. Đừng assert global order giữa A và B nếu không có sequencer trung tâm. Điều hợp lệ có thể là:

- Order per-producer được giữ trong điều kiện mà producer có cơ chế serial gửi;
- Mỗi message được nhận một lần trong phạm vi test không lỗi;
- Không mất/trùng khi backpressure và send timeout;
- Consumer không vi phạm invariant per-key đã định nghĩa.

### 7.4. QueueChannel và durability

QueueChannel in-memory thuận tiện cho unit test, nhưng không tự bảo đảm message sống qua process restart. Nếu production dùng MessageStore hoặc broker bền vững, cần test độ bền, transaction synchronization và receive/ack khi lỗi; **không thay test production bằng test trên queue in-memory**.

## 8. Test ExecutorChannel: cố ý buộc message 2 xong trước message 1

Đây là một **deterministic test** để chứng minh điều không được phép giả định: ExecutorChannel với nhiều worker **không bảo đảm completion FIFO**.

### 8.1. Kịch bản có gate

1. Gửi M1 và để worker 1 bắt đầu nhưng **chặn ở một latch**.
2. Sau khi chắc M1 đã bắt đầu, gửi M2.
3. Đợi M2 xử lý xong.
4. Mở latch của M1.
5. Kết quả hoàn tất quan sát được phải là M2, rồi M1.

### 8.2. JUnit 5: ví dụ chạy với 2 worker

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;

class ExecutorChannelOrderingTest {

    @Test
    void completionCanDifferFromSendOrder() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondCompleted = new CountDownLatch(1);
        CountDownLatch bothCompleted = new CountDownLatch(2);
        List<Integer> observed = new CopyOnWriteArrayList<>();

        try {
            ExecutorChannel channel = new ExecutorChannel(pool);
            channel.subscribe(message -> {
                int sequence = (Integer) message.getPayload();
                try {
                    if (sequence == 1) {
                        firstStarted.countDown();
                        if (!releaseFirst.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("Gate timeout");
                        }
                    }
                    observed.add(sequence);
                    if (sequence == 2) {
                        secondCompleted.countDown();
                    }
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted while testing", exception);
                } finally {
                    bothCompleted.countDown();
                }
            });

            assertTrue(channel.send(MessageBuilder.withPayload(1).build()));
            assertTrue(firstStarted.await(5, TimeUnit.SECONDS));
            assertTrue(channel.send(MessageBuilder.withPayload(2).build()));
            assertTrue(secondCompleted.await(5, TimeUnit.SECONDS));

            releaseFirst.countDown();
            assertTrue(bothCompleted.await(5, TimeUnit.SECONDS));
            assertEquals(List.of(2, 1), observed);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

**Giới hạn của test:** nó chứng minh **khả năng** hoàn tất lệch thứ tự bằng một interleaving được kiểm soát. Nó không chứng minh mọi lần gửi đều đảo thứ tự, cũng không tự kiểm tra DB commit; cần một test riêng nếu invariant nằm ở database.

### 8.3. Vì sao latch tốt hơn sleep?

Test **biết chắc** M1 đã bắt đầu trước khi gửi M2; **biết chắc** M2 đã hoàn tất trước khi giải phóng M1. Không cần ước lượng tốc độ CPU hoặc network. Timeout hữu hạn giúp phát hiện deadlock và tránh CI treo.

### 8.4. Trường hợp production dùng một thread

Nếu executor chỉ có một worker và cùng một queue FIFO trong điều kiện không restart/retry, completion thường tuần tự. Nhưng điều đó có thể giảm throughput; đồng thời nhiều application instances hoặc một async boundary phía sau vẫn có thể phá thứ tự toàn hệ thống. Kiểm thử toàn topology thay vì chỉ xem pool size.

## 9. Test giới hạn concurrency và race condition

### 9.1. Đo số handler đang thực thi, không chỉ nhìn cấu hình

Muốn xác minh concurrency limit N, dùng AtomicInteger để đếm:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

void processOne() {
    int current = active.incrementAndGet();
    peak.accumulateAndGet(current, Math::max);
    try {
        // Business operation, controlled gate hoặc fake downstream.
        doBusinessWork();
    } finally {
        active.decrementAndGet();
    }
}
~~~

Đây là **mẫu code**, không phải class độc lập: doBusinessWork() cần triển khai. Trong test, nhiều request phải thật sự chồng lấp; nếu các request chạy quá nhanh, peak=1 dù executor có khả năng xử lý N đồng thời. Dùng latch/barrier để giữ N worker ở cùng một điểm, rồi assert peak không vượt giới hạn và hệ thống tiến triển khi release.

### 9.2. Race condition của read–modify–write

Một đoạn code như:

~~~java
int current = repository.readCounter();
repository.writeCounter(current + 1);
~~~

không được bảo vệ bằng việc MessageChannel là thread-safe. Hai worker có thể cùng đọc current=10 rồi cùng ghi 11, trong khi đúng phải là 12. Test cần **buộc hai worker đọc trước khi ghi** bằng barrier hoặc fake repository, rồi assert final value và chỉ ra sai lệch. Sau đó sửa bằng atomic update/transaction hoặc optimistic locking trong kho dữ liệu thật.

### 9.3. Các lỗi thread safety khác

- Handler singleton giữ **mutable field** dùng chung mà không đồng bộ;
- Dùng HashMap/ArrayList không thread-safe để lưu trạng thái nhiều worker;
- Chia sẻ mutable payload object và sửa nội dung từ nhiều subscribers;
- Reuse HTTP client/session/formatter không an toàn theo tài liệu thư viện;
- Ghi log/metrics side effect theo thứ tự thiếu tương quan;
- Đặt dữ liệu request trong ThreadLocal rồi chuyển ExecutorChannel mà không propagate context.

Message headers trong Spring là cấu trúc metadata của một Message, nhưng **payload object có thể mutable**. Đừng suy rằng việc đưa object vào channel tự khiến mọi thao tác trên nó trở nên an toàn giữa threads.

### 9.4. Test đóng executor và không rò rỉ thread

Mỗi test tự tạo ExecutorService cần shutdown hoặc cleanup. Đối với integration tests chạy Spring context, đóng lifecycle endpoints, broker connections và nguồn File/SFTP theo teardown. Thread leak có thể khiến test sau thất bại không ổn định hoặc build không kết thúc.

## 10. Khi thứ tự completion không được bảo đảm: kiểm tra version ở nơi commit

Một thiết kế có thể cho M2 hoàn tất trước M1 mà **vẫn đúng nghiệp vụ** nếu data store không cho event cũ ghi đè mới.

### 10.1. Ví dụ update version có điều kiện

~~~sql
UPDATE order_projection
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version < :incomingVersion;
~~~

Mẫu trên bảo vệ **đơn điệu version** khi các event đến không đúng thứ tự, nếu điều kiện update được DB thực thi atomically. Nhưng nó có thể **bỏ qua một event trung gian** (ví dụ version 3 đến trước version 2); chỉ phù hợp nếu projection chỉ cần trạng thái mới nhất và có đủ dữ liệu để cập nhật trực tiếp.

Nếu nghiệp vụ yêu cầu mọi chuyển trạng thái hợp lệ (CREATED → PAID → SHIPPED), chỉ kiểm tra version lớn hơn **chưa đủ**. Cần kiểm tra **expectedVersion = incomingVersion - 1**, state transition và xử lý missing event.

### 10.2. Test chống ghi đè state mới

~~~text
Given: order-274 version=0
When:  process event version=3, commit thành công theo chính sách latest-wins
Then:  version=3, status=SHIPPED
When:  event version=1 đến muộn
Then:  không ghi đè version=3
And:   ghi audit stale event theo policy
~~~

Đây là một **test kịch bản**. Nếu policy của hệ thống là sequential state machine thay vì latest-wins, version=3 đến đầu tiên phải được giữ trong pending/resequencing và không commit trước version=1,2.

### 10.3. Dedupe event và side effect

Đừng chỉ kiểm tra final status: một duplicate PAID có thể khiến **thanh toán hai lần** dù trạng thái cuối vẫn là PAID. Cần assert số lần gọi API/ghi ledger/outbox theo eventId hoặc business transaction ID. Unique constraint hoặc idempotency store giúp chống chạy lại khi broker redelivery.

### 10.4. Kiểm thử tính nguyên tử của dedupe + update

Nếu hệ thống ghi “eventId đã xử lý” **sau** khi gửi HTTP hoặc ghi DB mà không có transaction phù hợp, crash giữa hai bước có thể tạo side effect lặp. Test fault injection tại các điểm **trước commit, sau commit, trước ack và sau ack** để chứng minh recovery an toàn.

## 11. Splitter, aggregator và resequencer: thứ tự ở mức nhóm message

Spring Integration có các mẫu xử lý **Splitter, Aggregator và Resequencer** dành cho message liên quan. Chúng hữu ích khi một message lớn được tách thành nhiều phần rồi xử lý đồng thời. Tuy nhiên, cần khai báo rõ thông tin nhóm và kỳ vọng release.

### 11.1. Message sequence headers

Khi splitter được cấu hình để bổ sung correlation/sequence metadata, các message phần có thể mang:

| Header | Ý nghĩa |
|---|---|
| correlationId | Nhận diện nhóm các message liên quan |
| sequenceNumber | Vị trí của message trong nhóm |
| sequenceSize | Số phần dự kiến khi xác định được |
| messageId | Nhận diện message cụ thể, không nhất thiết bằng eventId nghiệp vụ |

Không nên giả định mọi inbound File/HTTP/JMS/Kafka message đều được gắn sẵn headers này. **Sequence metadata của splitter** không tự là **version nghiệp vụ của đơn hàng**; chúng chỉ nói về vị trí phần tử trong một nhóm cụ thể.

### 11.2. Resequencer giải quyết điều gì?

~~~mermaid
flowchart LR
    SPLIT["Splitter: 1, 2, 3"] --> A["Worker A: part 1 chậm"]
    SPLIT --> B["Worker B: part 2 nhanh"]
    SPLIT --> C["Worker C: part 3 nhanh"]
    A --> R["Resequencer group"]
    B --> R
    C --> R
    R --> O["Release 1, 2, 3"]
~~~

Resequencer có thể sắp xếp lại **những phần đã tới** theo sequence và release theo chiến lược được cấu hình. Nó **không thể tạo ra một phần bị mất** và không bảo đảm thông điệp đã release được downstream commit thành công nếu phía sau lại có ExecutorChannel hoặc asynchronous send.

### 11.3. Các trường hợp cần test

1. Các phần đến 3, 1, 2 nhưng downstream nhận 1, 2, 3 theo yêu cầu;
2. Thiếu sequence=2; group chờ, hết timeout, expire hoặc có partial release đúng policy;
3. Duplicate sequenceNumber hoặc duplicate eventId;
4. Hai group A/B xen kẽ, không trộn phần của hai group;
5. Group lớn vượt memory/capacity và được lưu trong MessageGroupStore phù hợp;
6. Restart giữa lúc group chưa hoàn chỉnh;
7. Message đến sau khi group đã hoàn tất/expired;
8. Resequencer đã release đúng nhưng downstream async làm commit lệch thứ tự.

### 11.4. Không giải tất cả lỗi ordering bằng resequencer

Nếu event source thiếu version đáng tin, resequencer không thể biết CREATED nào trước CREATED nào. Nếu dữ liệu được phát từ nhiều producer độc lập, cần giao thức version/sequence nghiệp vụ tại nguồn. Nếu yêu cầu chỉ là không ghi đè version mới bởi version cũ, **optimistic concurrency** có thể đơn giản và hiệu quả hơn việc buộc mọi event đi qua một điểm xếp hàng.

### 11.5. Aggregator và thứ tự kết quả

Aggregator tập hợp các message thành nhóm dựa trên **correlation strategy** và **release strategy**. Thứ tự các phần trong output không nên được suy từ thứ tự chúng đến nếu không có cấu hình thích hợp. Test nên assert **tính đầy đủ và danh tính các phần**, thêm assertion ordering chỉ khi business contract thật sự yêu cầu.

## 12. File adapter: thứ tự danh sách file chưa phải thứ tự nghiệp vụ

### 12.1. Những nguồn thứ tự khác nhau

Một file adapter có thể quan sát:

- Thứ tự filesystem trả kết quả listing;
- Thứ tự tên file theo lexical/natural sort nếu được cấu hình;
- Last modified time hoặc mốc file ready;
- Thứ tự FileListFilter chấp nhận file;
- Thứ tự poller nhận file và đưa message vào channel;
- Thứ tự handler nhập dữ liệu hoặc commit vào database.

Không tự giả định **filesystem listing = business sequence**. Một file file-10.csv có thể được sắp trước file-2.csv khi so sánh chuỗi; timestamp có thể không phản ánh việc bên gửi đã ghi xong.

### 12.2. Thiết kế test thứ tự file

Chuẩn bị các tệp:

~~~text
orders-001.csv -> businessSequence=1
orders-003.csv -> businessSequence=3
orders-002.csv -> businessSequence=2
~~~

Kiểm thử hai hợp đồng khác nhau:

1. Nếu ứng dụng yêu cầu **nhận theo tên đã sắp**, cấu hình comparator/selector có chủ đích, một consumer phù hợp, assert thứ tự receive.
2. Nếu ứng dụng cần **commit theo businessSequence**, assert thứ tự tại database hoặc theo state version; việc sắp tên ở đầu vào không đủ nếu downstream chạy song song.

### 12.3. File chưa hoàn chỉnh và thay đổi trong lúc poll

Một producer đang ghi file lớn; poller có thể thấy nó trước khi ghi xong. Cần contract như **write-to-temp rồi rename**, marker file, age/size stabilization hoặc locking phù hợp. Test tạo file dở, xác minh adapter không đưa vào xử lý như file hoàn chỉnh.

### 12.4. Duplicate và restart

Accept-once hoặc persistent filter có thể đánh dấu một file đã nhận. Nếu handler lỗi sau khi filter cập nhật state, file có thể không được poll lại. Ngược lại, nếu metadata chưa lưu bền vững trước crash, file có thể được nhận lần nữa. Test cả **crash sau receive trước commit** và **crash sau commit trước archive**; xác minh business key chống trùng.

### 12.5. Nhiều instance cùng xem thư mục

Khi hai application instances đều poll một directory, mỗi instance có thể chọn cùng file. File locking, shared metadata/claim và idempotency cần được thiết kế theo storage thực tế. Bài test một JVM/QueueChannel không xác nhận shared file ownership trong cluster.

### 12.6. Một thứ tự dễ kiểm tra nhưng sai

Test có thể quan sát:

~~~text
File channel received: 1, 2, 3   (PASS)
DB committed:         2, 3, 1   (FAIL business ordering)
~~~

Đừng kết luận end-to-end ordering chỉ vì assertion trên input channel thành công. **Đặt assertion ở ranh giới commit** nếu tính đúng đắn phụ thuộc dữ liệu sau cùng.

## 13. SFTP adapter: listing, download, remote rename và concurrency

### 13.1. SFTP thường có hai vòng đời

**Remote lifecycle:** đối tác upload file, đổi tên/đánh dấu ready, file được liệt kê, có thể rename/delete khi đồng bộ.

**Local lifecycle:** ứng dụng tải file về, filter local chấp nhận, poller phát Message, handler xử lý và lưu kết quả.

Thứ tự remote listing, download completion và local message delivery có thể khác nhau, nhất là khi có latency, kích thước file khác nhau hoặc nhiều poller.

### 13.2. Ma trận lỗi cần chủ động tạo

| Kịch bản | Cách tạo trong môi trường test | Điều cần assert |
|---|---|---|
| Hai file A/B cùng xuất hiện | Upload theo thứ tự có chủ đích | Đúng quy tắc chọn, không suy global order |
| File B tải nhanh hơn A | Điều khiển kích thước/độ trễ | Downstream ordering tuân contract |
| Remote file upload dở | Tạo temp file rồi rename | Không ingest trước khi ready |
| Mất kết nối giữa download | Ngắt session trong test | Không parse file dở; retry/resume đúng |
| Hai poller cùng xem một remote path | Chạy hai instances hoặc hai consumers | Không xử lý trùng ngoài policy |
| File cùng tên nhưng nội dung mới | Thay nội dung/version có kiểm soát | Metadata filter xử lý đúng hợp đồng |
| Restart giữa receive và commit | Fault injection | Không mất và không tạo side effect trùng |

### 13.3. Kiểm thử độc lập với đồng hồ máy chủ

Remote mtime có thể lệch timezone/clock hoặc có độ chính xác hạn chế. Nếu ordering nghiệp vụ quan trọng, nên dùng **businessSequence trong manifest/payload** hoặc protocol rõ ràng; không dựa tuyệt đối vào mtime để quyết định phiên bản đơn hàng.

### 13.4. Khi lỗi SFTP đến errorChannel

Lỗi connect/list có thể xảy ra trước khi có Spring Message nên failedMessage có thể null. Lỗi parse sau khi tải có thể có File payload. Test phải chứng minh hệ thống vẫn biết **file nào đã tải/đã được chấp nhận và có được retry không**, chứ không chỉ kiểm tra số ErrorMessage.

## 14. HTTP inbound/outbound: request order và response order độc lập

### 14.1. HTTP inbound gateway không tạo global FIFO

Hai client gửi request A rồi B gần nhau. Thread pool web server, network, gateway, downstream executor và DB locks có thể khiến B hoàn tất trước A. **Thứ tự bắt đầu network request không phải hợp đồng ordering toàn cục** nếu API không quy định.

Nếu hai request cập nhật cùng account, cần version/precondition hoặc serialization theo key. Nếu là hai account khác nhau, cho phép song song thường tốt hơn.

### 14.2. HTTP outbound gateway

Một polling flow có thể gọi HTTP outbound đồng bộ, tạo backpressure tại sender. Nhưng khi phía đích xử lý request trong cụm nhiều node, thứ tự **HTTP response** không chứng minh thứ tự commit của hệ thống đích.

Với async HTTP client hoặc gateway có executor, callback B có thể đến trước callback A. Test cần ghi nhận stable request ID và correlate response, không gán kết quả theo “response thứ nhất tương ứng request thứ nhất”.

### 14.3. Test timeout với kết quả chưa biết

~~~text
Client sends POST orderId=274, requestId=R1
Server commits order
Response is lost
Client sees timeout
Retry may occur
~~~

Assert:

- Retry cùng một ý định sử dụng idempotency key ổn định khi API hỗ trợ;
- Downstream chỉ có một side effect nghiệp vụ;
- Order response được correlate bằng requestId, không theo vị trí callback;
- Nếu không thể xác minh kết quả, state là RESULT_UNKNOWN/NEEDS_RECONCILIATION;
- Lỗi tạm thời có giới hạn retry/backoff, không tạo storm.

### 14.4. Mô phỏng out-of-order response

Dùng mock HTTP server có khả năng giữ response cho request A, trả B trước, sau đó mở gate A. Nếu ứng dụng dùng async callbacks, assert mỗi result liên hệ đúng correlation. Với workflow order state, assert version/transaction ở DB chứ không chỉ response list.

### 14.5. HTTP 429 và concurrent requests

Test gửi nhiều message đồng thời tới mock downstream áp dụng rate limit. Nếu API trả 429/Retry-After, handler phải điều phối retry phù hợp, không để tất cả worker retry cùng lúc. Đo **in-flight calls** và **total attempts**; một taskExecutor giới hạn concurrency ở đoạn flow này có thể không giới hạn các HTTP clients khác trong hệ thống.

## 15. JMS và AMQP: message group, prefetch và redelivery

### 15.1. Điều cần phân biệt

Trong broker messaging có ít nhất ba thứ tự:

1. Producer gửi hoặc broker chấp nhận message theo thứ tự nào;
2. Broker giao message cho consumer nào, theo thứ tự nào;
3. Listener xử lý và **commit side effect** theo thứ tự nào.

Nếu có nhiều consumers, prefetch hoặc message redelivery, điều kiện 3 có thể khác điều kiện 1 hoặc 2.

### 15.2. JMS

JMS có các bảo đảm thứ tự trong những điều kiện cụ thể của session/producer/consumer và provider, nhưng không nên suy **global order với nhiều producer, session và consumer đồng thời**. Một số broker hỗ trợ **message grouping**, thường dùng thuộc tính JMSXGroupID để điều phối message cùng group về một consumer; cần kiểm tra capability và semantics của broker/provider.

Test nên kiểm tra:

- Cùng group/orderId, event được xử lý đúng business sequence;
- Hai group độc lập có thể tiến triển đồng thời;
- Consumer chết, group được reassigned và vẫn đúng chính sách redelivery;
- Transaction rollback tạo lại delivery mà không nhân đôi side effect;
- Poison message và DLQ có thể tạo gap; quy tắc với các event sau gap là gì.

### 15.3. AMQP/RabbitMQ

Trong một queue, thứ tự enqueue và thứ tự delivery có thể có tính FIFO trong một số điều kiện, nhưng **nhiều consumers, prefetch, nack/requeue, priority, multiple publishers và redelivery** có thể làm thứ tự completion khác. Một consumer với prefetch 1 là một cách giảm độ song song để dễ giữ trình tự, không phải chứng minh mọi hệ thống downstream đã commit theo FIFO.

| Cấu hình | Kỳ vọng kiểm thử |
|---|---|
| Một queue, một consumer, xử lý tuần tự | Quan sát thứ tự xử lý trong điều kiện bình thường |
| Một queue, nhiều consumers | Test out-of-order completion |
| Prefetch lớn | Nhiều message đang in-flight, kiểm tra ack/commit |
| Nack/requeue message đầu | Kiểm tra message sau có vượt trước không |
| DLX/DLQ | Xác định policy khi một sequence bị cách ly |
| Single active consumer nếu dùng | Test failover và redelivery trên broker được chọn |

**Đưa message vào DLQ không tương đương hoàn tất chuỗi nghiệp vụ.** Với cùng orderId, nếu version 2 vào DLQ nhưng version 3 vẫn được xử lý, cần quyết định chờ, bỏ qua có chứng cứ hoặc reconciliation.

### 15.4. Acknowledgment và transaction

Spring Integration AMQP/JMS adapters phối hợp với listener container. Nếu handler ném exception, behavior redelivery/rollback phụ thuộc transaction/ack mode và error handling. Nếu error flow bắt lỗi rồi trả về như success, broker có thể xem message đã xử lý xong. Test phải quan sát **broker state và DB state**, không chỉ ErrorMessage.

### 15.5. Những assertion không nên dùng

Đừng assert mọi message từ hai producer độc lập được xử lý đúng thứ tự wall-clock. Thay vào đó xác định **per-group key, sequence nghiệp vụ, dedupe và commit policy**; giữ những assertion mà contract thực sự yêu cầu.

## 16. Kafka: ordering theo partition, không phải toàn topic

### 16.1. Những bảo đảm cơ bản

Kafka lưu record **theo thứ tự offset trong từng partition**. Consumer có thể đọc các record của một partition theo thứ tự offset; **không có một global order được cam kết giữa các partition**. Nhiều producer gửi cùng key có thể tạo record theo thứ tự append khác thứ tự nghiệp vụ dự kiến nếu không có coordination.

Để các event cùng orderId thường nằm chung partition, producer cần chọn **partitioning key ổn định** và giữ partition count/partitioner behavior theo thiết kế. Thay đổi số partition hoặc chiến lược phân vùng có thể ảnh hưởng key routing theo thời gian; cần có kế hoạch migration.

### 16.2. Spring Integration Kafka adapter và worker concurrency

Kafka inbound message-driven adapter làm việc với **listener container**. Việc đọc record có thứ tự offset tại partition **không bảo đảm** completion/DB commit theo offset nếu flow tách việc xử lý sang ExecutorChannel hoặc service async không await kết quả.

~~~mermaid
flowchart TD
    K["Kafka partition P0: offsets 11,12,13"] --> L["Kafka listener"]
    L --> X["ExecutorChannel 3 workers"]
    X --> W11["Offset 11 slow"]
    X --> W12["Offset 12 fast"]
    X --> W13["Offset 13 fast"]
    W11 --> DB["DB commit"]
    W12 --> DB
    W13 --> DB
~~~

Test phải phân biệt **listener đã nhận** và **business processing được xác nhận**, đồng thời kiểm tra offset commit/ack ở cấu hình thực tế. Đừng để offset được commit như đã hoàn tất nếu side effect còn đang chạy mà recovery contract không bảo vệ.

### 16.3. Lỗi và retry có thể tạo gap

| Kịch bản | Cần kiểm tra |
|---|---|
| Offset 12 lỗi tạm thời | Container retry/pause/seek hay các record sau tiếp tục? |
| Offset 12 vào DLT | Version 13 được phép xử lý không nếu thiếu 12? |
| Consumer rebalance | In-flight jobs hoàn tất/commit có còn hợp lệ? |
| Producer retry | Có duplicate hoặc thay đổi thứ tự được quan sát không? |
| Idempotent producer/transaction | Bảo đảm của Kafka có bao được HTTP/JDBC không? |
| Async handler hoàn tất sau khi listener đã ack | Có cơ chế durability/retry cho công việc chưa xong không? |

Spring for Apache Kafka có các cơ chế container error handling (như DefaultErrorHandler ở những phiên bản tương ứng). Cách seek, retry, DLT và commit phụ thuộc phiên bản, ack mode và cấu hình. **Không mặc định một global Spring Integration errorChannel quyết định Kafka offset**.

### 16.4. Mẫu test per-key Kafka

Gửi ít nhất hai key A/B, mỗi key có sequence 1..N. Cho consumer xử lý với latency khác nhau và fault injection:

- Với A, state cuối đúng version N và không lùi;
- Với B, state cuối đúng version N;
- A và B có thể xen kẽ nếu không cần global order;
- Duplicate eventId không tạo thêm side effect;
- Sau rebalance/restart, dữ liệu không mất/trùng ngoài policy;
- Nếu pipeline yêu cầu sequential state transition, không commit version sau khi thiếu version trước.

### 16.5. Producer và business sequence

**Offset tăng không tự chứng minh event có ý nghĩa nghiệp vụ đúng**. Producer có thể publish PAID rồi CREATED vì application code bị race. Test nên giữ **aggregate version hoặc business sequence** trong payload/headers, đối chiếu với state nguồn và không lấy offset làm chuẩn duy nhất cho mọi nghiệp vụ.

## 17. JDBC inbound/outbound: ORDER BY không thay cho transaction và claim

### 17.1. Polling nhiều worker

Một JDBC inbound adapter có thể đọc công việc:

~~~sql
SELECT id, order_id, event_version, payload_ref
FROM integration_work
WHERE state = 'PENDING'
ORDER BY created_at, id;
~~~

ORDER BY làm rõ **thứ tự rows trong một kết quả truy vấn**, nhưng không bảo đảm rằng hai pollers chạy đồng thời sẽ claim công việc theo một thứ tự toàn cục, hay DB commits sẽ theo đúng thứ tự đó. Với hai app instances, cả hai có thể đọc cùng row nếu thiếu locking/claim.

### 17.2. Atomic claim và optimistic concurrency

Một mô hình đơn giản:

~~~sql
UPDATE integration_work
SET state = 'CLAIMED',
    claimed_by = :workerId,
    version = version + 1
WHERE id = :workId
  AND state = 'PENDING'
  AND version = :expectedVersion;
~~~

Chỉ worker nhận **đúng một row affected** mới được xem là claim thành công. Câu lệnh là mẫu minh họa, chưa giải quyết chọn batch, lease timeout, dead worker, isolation/locking và race tại source query. Nếu dùng **SELECT ... FOR UPDATE SKIP LOCKED**, kiểm tra cú pháp và mức hỗ trợ của DB, đồng thời hiểu rằng skip locked có thể làm **completion order không còn FIFO** vì worker bỏ qua row đang bị khóa.

### 17.3. Test lost update với hai transactions

Một bài test có giá trị:

1. DB có account balance=100, version=1.
2. Hai workers cùng đọc balance=100 trước khi cập nhật.
3. Worker A và B đều muốn cộng 10.
4. Nếu code ghi đè không bảo vệ, kết quả có thể 110 thay vì 120.
5. Sửa bằng atomic SQL update/locking hoặc optimistic compare-and-set có retry.
6. Test lại trên DB thực, xác minh balance=120 và đúng số transaction đã commit.

**Không dùng in-memory H2 rồi mặc định kết luận concurrency/locking giống PostgreSQL, MySQL hoặc Oracle**; những khác biệt isolation, lock wait, SKIP LOCKED và deadlock cần integration test trên hệ quản trị đích hoặc một bản tương thích.

### 17.4. Per-order event version

Khi xử lý cùng orderId, nên có một transaction atomically:

- Kiểm tra eventId đã xử lý chưa;
- Xác minh version hợp lệ với business rule;
- Thực hiện state transition;
- Ghi eventId đã xử lý hoặc outbox event;
- Commit.

Nếu dedupe và update không nằm trong cùng transaction phù hợp, có thể xuất hiện duplicate hoặc mất event khi crash.

### 17.5. Outbox và thứ tự publish

Outbox giúp giữ thông tin cần publish cùng transaction DB. Tuy nhiên, hai publisher workers có thể lấy các outbox rows cùng key rồi gửi song song, làm **publish order** khác thứ tự commit. Test phải xác định:

- Outbox claim theo orderId/version hay global ID?
- Có bao nhiêu workers được phép xử lý cùng key?
- Nếu publish offset/version 2 lỗi, version 3 có được gửi không?
- Retry record có giữ idempotency key và correlation không?
- Sau crash giữa publish và mark-sent, consumer có dedupe được không?

Outbox **không tự cung cấp exactly-once end-to-end** với HTTP hoặc broker; cần dedupe và kiểm tra invariant tại consumer.

## 18. Khi lỗi, retry và dead-letter làm thay đổi thứ tự

### 18.1. Ba tình huống sau lỗi

~~~text
Source: 1 -> 2 -> 3

Policy A: Stop-and-retry
  1 success, 2 fails, 2 retries, 3 waits
  -> preserves sequential policy but may block

Policy B: Skip-to-DLQ
  1 success, 2 fails -> DLQ, 3 continues
  -> progress, but creates a gap

Policy C: Concurrent retry
  1 success, 2 fails and retries asynchronously, 3 succeeds
  -> 3 can commit before 2
~~~

Không có lựa chọn nào luôn đúng; business contract quyết định liệu **sequence gap** có thể chấp nhận. Ví dụ telemetry có thể xử lý bản mới nhất, trong khi ledger chuyển tiền thường cần kiểm soát chặt thứ tự và tính đúng đắn của mọi giao dịch.

### 18.2. ErrorMessage không phải rollback

Trong Spring Integration, một exception có thể đi đến **errorChannel** dưới dạng ErrorMessage khi có error publisher phù hợp. Điều đó **không tự hoàn tác** việc poller đã lấy file, consumer đã ack JMS, Kafka đã commit offset hoặc DB đã ghi một phần.

Test phải có **hai assertion khác nhau**:

1. Error notification xuất hiện đúng channel, chứa safe context;
2. Trạng thái source/target phù hợp với retry, rollback, quarantine hay compensation policy.

### 18.3. Kiểm thử retry budget

Giả sử handler có retry 3 lần và broker/container redelivery tối đa 4 lượt. Không nên chỉ assert mỗi component đúng cấu hình; kiểm tra **tổng số lần gọi downstream** và tác động khi hai lớp retry kết hợp. Dùng mock service đếm calls và bắt tình huống retry storm.

### 18.4. Poison message và head-of-line blocking

Nếu per-key order đòi version 2 hoàn tất trước 3, message 2 lỗi vĩnh viễn có thể chặn key đó. Cần policy:

- Giữ key trong trạng thái BLOCKED và alert;
- Quarantine version 2, sau đó chạy reconciliation hoặc nghiệp vụ sửa;
- Cho phép skip nếu domain contract hỗ trợ và ghi audit;
- Không chặn vô hạn các key độc lập khác.

Test phải xác minh **đúng key bị chặn**, trong khi những key khác vẫn xử lý được nếu kiến trúc cho phép.

### 18.5. Retry về đầu hàng đợi

Việc requeue vào đầu/cuối, seek offset, delay queue hoặc publish lại Kafka thường ảnh hưởng thứ tự. Không tự giả định message được redeliver ở đúng vị trí ban đầu trên mọi broker/adapter. Cần test với cấu hình retry thực tế và kiểm tra sequence tại điểm commit.

### 18.6. Crash giữa side effect và acknowledgment

Một worker xử lý event 2, ghi DB thành công, rồi crash trước broker ack. Broker có thể redeliver event 2 sau restart. Nếu idempotency xử lý đúng, kết quả nghiệp vụ vẫn như một lần; nếu không, side effect có thể lặp. Test có fault injection chính xác ở ranh giới này là quan trọng hơn việc chỉ đo receive order.

### 18.7. Compensation và event đến muộn

Nếu đã gửi CancelOrder và một callback cũ của CreateOrder đến sau, state machine không được chuyển đơn về CREATED. Test late callback và version/expected-state check. **Thứ tự thời gian nhận callback không quyết định quyền sửa trạng thái nghiệp vụ**.

## 19. Ma trận kiểm thử concurrency và ordering

### 19.1. Phân tầng phạm vi

| Cấp độ | Đối tượng | Mục tiêu | Bằng chứng |
|---|---|---|---|
| Unit | Version guard, dedupe, state machine | Quy tắc business đúng ở interleavings | State/version, duplicate count |
| Channel | Queue/Executor/Direct/PubSub | Topology và dispatch semantics | Receive/start/completion order |
| Flow integration | IntegrationFlow, poller, advice | Thread boundary, retry, error routing | Handled events + ErrorMessage |
| Adapter integration | File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC | Protocol và state thật | Remote file, broker offset/ack, DB commit |
| System/end-to-end | Nhiều service, nhiều instances | Per-key consistency và throughput | Business state, outbox, external effects |
| Recovery/chaos | Crash, failover, partition, slow downstream | Không mất message/trùng effect ngoài policy | Replay audit, final state, lag |

### 19.2. Các kịch bản tối thiểu

| ID | Tình huống | Điều phải kiểm tra |
|---|---|---|
| C01 | 1 producer, 1 QueueChannel consumer | Receive FIFO theo điều kiện xác định |
| C02 | ExecutorChannel 2 workers | M2 có thể hoàn tất trước M1 |
| C03 | N producers cùng key | Không vi phạm version policy |
| C04 | N producers khác key | Parallelism mà không trộn state |
| C05 | Cùng eventId được gửi hai lần | Một side effect nghiệp vụ |
| C06 | Version 3 đến trước 2 | Chờ/skip/commit theo policy rõ |
| C07 | Version 2 bị lỗi tạm thời | Retry không khiến state lùi |
| C08 | Version 2 bị poison | Key blocked/quarantine theo quy định |
| C09 | Worker crash trước DB commit | Retry an toàn, không loss |
| C10 | Worker crash sau DB commit trước ack | Dedupe khi redelivery |
| C11 | Two JDBC pollers claim cùng row | Một claim hợp lệ hoặc dedupe |
| C12 | File/SFTP upload dở | Không ingest file chưa ready |
| C13 | HTTP response B đến trước A | Correlation đúng, state đúng |
| C14 | JMS/AMQP consumer failover | Ack/redelivery và per-group policy |
| C15 | Kafka partition rebalance | Không xử lý trùng side effect |
| C16 | Outbox publisher retry/callback muộn | Đúng eventId, version và state |
| C17 | Error handler fail | Recovery không mất, có alert |
| C18 | Queue/executor quá tải | Rejection/backpressure được xử lý |
| C19 | Application restart | Pending state/group recovery đúng |
| C20 | Không có dữ liệu tới poller | Heartbeat/freshness alert đúng |

### 19.3. Assertion chống flakiness

Thay vì “đợi 2 giây rồi kiểm tra”, ưu tiên latch và eventual assertions có deadline. Nếu cần kiểm tra **không có side effect** sau một khoảng thời gian, phải hiểu đó chỉ là bằng chứng trong **observation window**; kết hợp với version guard/invariant và kiểm tra trạng thái queue hoặc worker đang in-flight.

### 19.4. Cấu hình phù hợp với production

Không nên chạy test với pool 1 thread rồi kết luận pool 16 threads an toàn. Cố gắng có một nhóm integration tests dùng đúng các thông số quan trọng như consumer concurrency, prefetch, Kafka partitions, poller schedule, retries, transaction mode và MessageStore của production.

### 19.5. Dữ liệu test và khả năng tái hiện

Mỗi event nên có eventId, businessKey, sequence/version, source, timestamp, attempt và correlation. Lưu seed, topology và exception injection point khi phát hiện lỗi. Dọn database, queue, thư mục và topic theo phạm vi test để tránh dữ liệu cũ làm false failure.

## 20. Case study: hai đơn song song, một đơn có event đến lệch thứ tự

### 20.1. Bối cảnh

Nền tảng A nhận file đặt hàng từ SFTP và sự kiện cập nhật từ Kafka. Sau khi validate, flow cập nhật JDBC projection và gọi HTTP logistics. Các trạng thái:

~~~text
Order A: CREATED(v1), PAID(v2), SHIPPED(v3)
Order B: CREATED(v1), PAID(v2), SHIPPED(v3)
~~~

Yêu cầu: đúng thứ tự **trong mỗi order**, nhưng A/B có thể chạy song song. Duplicate/retry không được tạo shipment hoặc charge hai lần.

### 20.2. Topology có nguy cơ

~~~mermaid
flowchart TD
    F["SFTP inbound / File poller"] --> N["Normalize OrderEvent"]
    K["Kafka inbound"] --> N
    N --> Q["QueueChannel"]
    Q --> P["Polling consumer"]
    P --> E["ExecutorChannel"]
    E --> W1["Worker 1"]
    E --> W2["Worker 2"]
    E --> W3["Worker 3"]
    W1 --> DB["JDBC order projection"]
    W2 --> DB
    W3 --> DB
    DB --> OUT["Outbox / HTTP logistics"]
~~~

Ngay cả khi QueueChannel nhận A1, A2, A3 theo FIFO, ExecutorChannel có thể khiến A3 hoàn tất trước A2. Kafka chỉ giúp ordering trong partition nếu producer key/routing và xử lý sau listener không phá trình tự.

### 20.3. Test đỏ ban đầu

Cho Worker 1 xử lý A1 nhưng chặn trước DB commit, Worker 2 xử lý A2 và Worker 3 xử lý A3. Với implementation chỉ ghi “status mới nhất được xử lý”, kết quả:

~~~text
Commit order: A2 -> A3 -> A1
Final A status: CREATED   (SAI)
Final B status: SHIPPED   (ĐÚNG)
~~~

Test phải cố ý tạo lịch này bằng gate/latch hoặc service giả có thể kiểm soát. Không dùng các dòng log nhận Kafka để suy commit order.

### 20.4. Hai hướng khắc phục

**Hướng A — Serialization theo key:** route cùng orderId vào worker/partition/queue có xử lý tuần tự phù hợp; key B có thể ở worker khác. Thử nghiệm cả failover, restart và retry gap để chắc cùng key không bị thực thi đồng thời ngoài policy.

**Hướng B — Concurrency control tại DB:** mỗi event có version; update atomically và từ chối event cũ. Nếu nghiệp vụ yêu cầu mọi trạng thái trung gian, chỉ cho transition từ expected version, giữ event đến sớm trong pending store và request replay khi thiếu version.

Không nên áp dụng cả hai một cách thiếu cân nhắc: serialization có thể giảm throughput; optimistic locking tạo retry conflict. Chọn theo business ordering requirement và sức tải.

### 20.5. Test sau sửa

| Điều kiện kiểm thử | Kỳ vọng |
|---|---|
| A3 nhận trước A2 | A final state vẫn đúng policy |
| A1 callback đến muộn | Không ghi đè version mới |
| A2 được retry 3 lần | Chỉ một payment side effect |
| A2 vào DLT | A3 chờ hoặc có xử lý gap có căn cứ |
| A và B chạy song song | Không chặn B vì A bị lỗi |
| HTTP shipment timeout | Không tạo shipment trùng |
| Restart khi A đang pending | Có thể resume đúng version |
| Kafka rebalance trong lúc xử lý | Không mất/nhân đôi side effect |
| SFTP file chứa duplicate A1 | Dedupe theo eventId/businessKey |
| Bất kỳ message lỗi | Error flow không đánh dấu giả thành công |

### 20.6. Chỉ số hiệu năng cần kèm correctness

Thông lượng cao không bù được dữ liệu sai. Báo cáo test gồm:

- Throughput (messages/s) và p95/p99 processing latency;
- Peak in-flight theo endpoint và theo key;
- Số version conflicts, retries, duplicates đã chặn;
- Count reorder giữa arrival/start/completion/commit;
- Backlog/lag theo File, QueueChannel, Kafka và outbox;
- Số message bị bỏ rơi, poison và manual reconciliation;
- Error rate và số lần handler có side effect ngoài policy.

Không tự tạo số liệu benchmark nếu chưa chạy test. Các thước đo là **đề xuất cần đo trong môi trường kiểm thử**, không phải kết quả thực nghiệm của bài viết.

## 21. Một integration test với PollableChannel và Spring Integration flow

### 21.1. Mục tiêu

Khác với test QueueChannel trực tiếp ở phần 7, bài test này tạo **Spring application context** và cho polling consumer thật lấy message từ QueueChannel. Nó phù hợp để xác nhận wiring cơ bản và thứ tự receive khi **một poller, một handler tuần tự**, trước khi đưa thêm ExecutorChannel hoặc nhiều consumers.

### 21.2. Mẫu test Spring + JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SinglePollerFlowTest.Config.class)
class SinglePollerFlowTest {

    @Autowired
    QueueChannel inputQueue;

    @Autowired
    QueueChannel outputQueue;

    @Test
    void onePollingConsumerRelaysThreeMessagesInOrder() {
        for (int version = 1; version <= 3; version++) {
            assertTrue(inputQueue.send(
                    MessageBuilder.withPayload(version).build()));
        }

        for (int version = 1; version <= 3; version++) {
            Message<?> actual = outputQueue.receive(5_000);
            assertNotNull(actual);
            assertEquals(version, actual.getPayload());
        }
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        QueueChannel inputQueue() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel outputQueue() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow relayFlow() {
            return IntegrationFlow.from(inputQueue(),
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofMillis(50))
                                    .maxMessagesPerPoll(1)))
                    .channel(outputQueue())
                    .get();
        }
    }
}
~~~

Ví dụ dùng các API Java DSL và Spring Test phổ biến; **cần đối chiếu chữ ký overload của DSL với phiên bản Spring Integration** trong dự án. Test giả định không có component khác cùng tiêu thụ inputQueue, không thêm executor giữa source và output và bean lifecycle được Spring context quản lý.

### 21.3. Test này chứng minh điều gì?

Nó kiểm tra **đường đi qua polling consumer tới output queue** trong một topology đơn giản. Nó không chứng minh:

- QueueChannel là durable sau restart;
- HTTP/JDBC/Kafka side effect đã commit đúng thứ tự;
- Nhiều pollers hoặc application instances vẫn nhận đúng một lần;
- Retry hoặc error-channel không làm đảo message;
- Concurrency lớn vẫn an toàn.

### 21.4. Mở rộng từ một sang nhiều workers

Giữ nguyên inputQueue nhưng thay hoặc thêm executor sau poller; cho handler có latch gây M2 hoàn tất trước M1. Test phải **thay assertion** từ global completion FIFO sang **invariant của business state** nếu topology chủ đích xử lý song song.

### 21.5. Kiểm tra thread identity

Trong test, có thể ghi Thread.currentThread().getName() vào một thread-safe observation collector. Nó giúp chứng minh có ranh giới executor và nhiều threads được sử dụng. Tuy nhiên, thread names chỉ là bằng chứng hỗ trợ; **tính đúng đắn phải được kiểm tra bằng state/side effects**.

### 21.6. Fault injection vào polling flow

Thêm handler ném exception có chủ đích và cấu hình poller error-channel riêng; assert ErrorMessage được publish và source state phù hợp. Khi Message đã rời QueueChannel, đừng mặc định nó tự quay lại. Với bài test File/SFTP, xác minh source filter và file reference để replay.

## 22. Runbook điều tra lỗi ordering và concurrency

### Bước A — Chốt định nghĩa “sai thứ tự”

Hỏi rõ:

- Sai thứ tự **arrival**, **dequeue**, **start**, **finish**, **DB commit** hay **client observation**?
- Yêu cầu là global order hay per-key?
- Event có **version đáng tin** và **eventId** chưa?
- Hệ thống cho phép gap hay cần mọi version nối tiếp?
- Có duplicate, retry hoặc callback đến muộn không?

Nếu không chốt điểm quan sát, có thể mất nhiều thời gian sửa QueueChannel dù lỗi nằm ở JDBC/outbound async.

### Bước B — Vẽ ranh giới đồng bộ/bất đồng bộ

Với từng endpoint, ghi:

1. Channel là Direct, Queue, Executor, PublishSubscribe, Priority hay reactive;
2. Poller/scheduler, maxMessagesPerPoll, task executor và số instances;
3. Điểm handler chuyển sang HTTP async, Kafka producer hoặc service khác;
4. Broker partition/group/consumer concurrency/prefetch và retry behavior;
5. Ranh giới transaction DB, broker acknowledgment hoặc file filter;
6. ErrorMessage được gửi tới channel nào khi thất bại.

**Vẽ từ source tới side effect cuối**, không dừng tại message channel ở giữa.

### Bước C — Thu thập bằng chứng

Ghi cho mỗi event:

~~~text
eventId, businessKey, version,
sourceAdapter, sourceReference,
arrivalAt, enqueuedAt, handlerStartAt,
handlerFinishedAt, committedAt, publishedAt,
threadName, instanceId, attempt,
correlationId, failureCategory, disposition
~~~

Không phải endpoint nào cũng cung cấp mọi timestamp. Các mốc này là **schema quan sát đề xuất**; thời gian đo trên máy khác nhau có thể lệch. Để chứng minh quan hệ thứ tự, ưu tiên sequence/version và **commit log/correlation** hơn so sánh timestamp từ nhiều đồng hồ độc lập.

### Bước D — Tái tạo lỗi

1. Tạo hai event cùng key và ít nhất một key độc lập;
2. Chặn worker A bằng latch/barrier;
3. Cho worker B chạy trước và ghi lại commit;
4. Thêm duplicate và một event đến trễ;
5. Inject timeout hoặc crash tại ranh giới ack/commit;
6. Test cả recover/restart và broker rebalance nếu có;
7. Lưu seed, topology và thông số pool/partition/prefetch.

Nếu lỗi chỉ xuất hiện production, lấy dữ liệu metadata đã giảm nhạy cảm và tái tạo pattern trong staging; không tự xuất dữ liệu khách hàng ra môi trường test không được phép.

### Bước E — Khoanh vùng lỗi

| Quan sát | Nguyên nhân cần kiểm tra |
|---|---|
| M1 và M2 enqueue sai order | Nhiều producers, source listing, network hoặc publisher race |
| Enqueue đúng nhưng dequeue khác | Priority channel, group/partition, nhiều consumers, replay |
| Dequeue đúng nhưng commit sai | Executor/async handlers, DB lock, HTTP latency |
| Commit đúng nhưng read model lùi | Consumer projection và stale event |
| Dữ liệu đúng nhưng callback sai request | Thiếu correlation ID hoặc map response theo vị trí |
| Lặp side effect sau retry | Idempotency/dedupe hoặc ack timing sai |
| Có gap v2 nhưng v3 vẫn chạy | Retry/DLQ policy không phù hợp sequential rule |
| Message “mất” sau poller lỗi | Filter/queue state không được replay bền vững |
| Latency tăng bất thường | Lock contention, head-of-line blocking, queue backlog |

### Bước F — Chọn biện pháp có phạm vi nhỏ nhất

- **Serialization per-key** khi business logic bắt buộc tuần tự;
- **Optimistic locking/version check** khi cho phép out-of-order arrival;
- **Resequencer/pending store** khi phải chờ đủ sequence;
- **Idempotency/dedupe** cho duplicate và redelivery;
- **Transactional outbox/inbox** cho nhất quán giữa DB state và message;
- **Bounded executor/backpressure** khi số công việc in-flight vượt giới hạn;
- **Quarantine/manual reconciliation** cho poison/gap không giải quyết tự động.

Đừng lập tức chuyển toàn bộ ứng dụng sang một thread để “sửa thứ tự” nếu chỉ một nhóm key nhạy cảm; cách đó có thể làm giảm đáng kể throughput các công việc độc lập.

### Bước G — Xác minh và đóng sự cố

Chạy lại test xác định, stress test và fault injection với topology mục tiêu. Kết quả cuối cần có:

- Invariant được duy trì trên DB/target service;
- Duplicate được xử lý an toàn;
- Không có message mất ngoài policy;
- Retry/ack/recovery đúng trạng thái;
- Throughput, latency và backlog nằm trong giới hạn đã đặt;
- Có log, metric, owner và regression test ngăn lỗi tái phát.

## 23. Các anti-pattern thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Cho rằng send(M1) trước send(M2) ⇒ commit M1 trước M2 | Stale state ghi đè state mới | Đo/kiểm soát commit order |
| Chỉ test một producer, một thread | Không phát hiện race production | Test nhiều producers/consumers |
| Tăng ExecutorChannel pool size nhưng vẫn assert FIFO completion | Test sai hợp đồng | Assert per-key invariant hoặc serialize |
| Dùng Thread.sleep để “đồng bộ” test | Flaky và phụ thuộc CI | CountDownLatch/barrier + timeout |
| Dựa vào timestamp làm business sequence | Clock skew, event đến muộn | Sequence/version đáng tin |
| Coi QueueChannel in-memory là durable | Mất message sau restart | MessageStore/broker phù hợp |
| Cho rằng maxMessagesPerPoll giới hạn concurrency | Overload và race | Kiểm tra executor, số instances và in-flight |
| Coi ORDER BY JDBC là global processing order | Multi-worker commit lệch | Claim/locking và version guard |
| Tin SFTP listing theo đúng thứ tự upload | Xử lý sai file phụ thuộc | Manifest/sequence, ready protocol |
| Tin Kafka có global order cả topic | Sai trạng thái cross-partition | Per-key partition và business version |
| Cho rằng broker FIFO thì HTTP/DB commit FIFO | Side effects lệch vì concurrency | Assert ở target, kiểm soát async |
| Cho Kafka listener ack khi async job chưa durable | Message mất sau crash | Cơ chế ack/work persistence phù hợp |
| Bỏ qua retry làm vượt sequence | Gap phá state machine | Retry/hold/resequence theo key |
| Skip poison message nhưng không ghi gap | Version sau bị xử lý sai | Quarantine và reconciliation |
| Chỉ check final status, không check side effect count | Double charge/shipment bị bỏ sót | Idempotency assertion |
| Dùng mutable singleton state không thread-safe | Lost update và data race | Immutable message, atomic DB state |
| Chia sẻ ThreadLocal qua ExecutorChannel | Mất tenant/correlation | Explicit context propagation |
| Không giới hạn outstanding tasks | Memory/queue tăng không giới hạn | Bounded executor, backpressure |
| Test trên H2 và suy lock semantics production | Sai khi chạy DB thật | Integration test DB đích |
| Không test crash sau commit trước ack | Duplicate sau restart | Fault injection + dedupe |
| Chỉ quan sát ErrorMessage khi có lỗi | Không nhận biết poller bị ngừng | Health, last-success, backlog |
| Dùng một khóa global cho mọi đơn | Throughput thấp, head-of-line blocking | Per-key serialization hoặc optimistic concurrency |
| Ghi metric label theo orderId/eventId | High cardinality | Aggregate metrics, tra ID bằng logs |

## 24. Checklist thiết kế và kiểm thử

### A. Hợp đồng thứ tự

- [ ] Xác định global/per-key/causal/event-time hoặc no-order.
- [ ] Định nghĩa arrival/dequeue/start/finish/commit/observation mà bài toán yêu cầu.
- [ ] Có business key, eventId và version/sequence phù hợp.
- [ ] Có policy cho duplicate, stale event, thiếu sequence và late callback.
- [ ] Phân biệt thứ tự source với thứ tự commit/side effect.

### B. Spring Integration topology

- [ ] Ghi rõ DirectChannel, QueueChannel, ExecutorChannel và PubSub boundaries.
- [ ] Biết poller source hay consumer, lịch, maxMessagesPerPoll và task executor.
- [ ] Có giới hạn in-flight và backpressure theo endpoint.
- [ ] Nếu dùng splitter/aggregator/resequencer, có group/correlation/timeout/release policy.
- [ ] Hiểu channel dùng in-memory hay MessageStore bền vững.
- [ ] Khi lỗi, có error channel và recovery policy phù hợp.

### C. Adapter và transaction

- [ ] File/SFTP có ready protocol, filter và kiểm thử duplicate/restart.
- [ ] HTTP có correlation, timeout, idempotency key hoặc reconciliation.
- [ ] JMS có group/consumer concurrency, transaction/ack và redelivery test.
- [ ] AMQP có prefetch, requeue/DLQ và test consumer failover.
- [ ] Kafka có key partition, consumer concurrency, offset/DLT và retry policy.
- [ ] JDBC có claim/version/transaction phù hợp với DB production.
- [ ] Outbox/inbox và side effect được kiểm tra tại nơi commit.

### D. Test concurrency

- [ ] Có test một producer/consumer và nhiều producers/consumers.
- [ ] Có test buộc out-of-order completion bằng latch/gate.
- [ ] Có test peak in-flight và giới hạn concurrency.
- [ ] Có test lost update, optimistic conflict và version không lùi.
- [ ] Có test duplicate eventId, retry, poison/gap và late callback.
- [ ] Có test crash trước/sau DB commit và trước/sau ack.
- [ ] Có test nhiều instances, rebalance/failover khi áp dụng.
- [ ] Mọi test async có timeout và cleanup executor/resources.

### E. Quan sát và vận hành

- [ ] Có correlationId, eventId, business key và stage theo scope phù hợp.
- [ ] Có metrics throughput, in-flight, lag, retry, conflict, stale event.
- [ ] Có cảnh báo khi poller/consumer không tiến triển dù error count bằng 0.
- [ ] Log không chứa payload nhạy cảm, token hay secret không cần thiết.
- [ ] Có runbook và owner cho gap, DLQ/quarantine, replay và reconciliation.
- [ ] Mỗi thay đổi concurrency/partition/prefetch đều chạy regression tests.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Message M1 được send trước M2. Vì sao không thể kết luận M1 sẽ commit trước M2?

**Đáp án:** Sau ranh giới ExecutorChannel, consumer song song, HTTP async hoặc DB transaction, M2 có thể hoàn tất/commit trước M1. Thứ tự send không tự là thứ tự side effect.

**Câu 2.** DirectChannel có bảo đảm global order khi hai producer threads cùng gửi không?

**Đáp án:** Không. DirectChannel thường gọi handler đồng bộ trên thread sender, nhưng nhiều sender có thể interleave. Cần serialization hoặc version policy nếu business yêu cầu thứ tự toàn cục.

**Câu 3.** QueueChannel nhận 1, 2, 3 theo FIFO. Nếu có ba polling consumers, có thể 3 hoàn tất trước 1 không?

**Đáp án:** Có. FIFO dequeue không đồng nghĩa FIFO completion khi nhiều consumers xử lý và commit khác thời gian.

**Câu 4.** maxMessagesPerPoll(10) có nghĩa tối đa 10 handler chạy đồng thời không?

**Đáp án:** Không. Nó giới hạn số message được poll trong một chu kỳ theo cấu hình, không trực tiếp đặt giới hạn concurrency; cần xét task executor và số instances.

**Câu 5.** Vì sao dùng Thread.sleep trong test ordering dễ gây flaky?

**Đáp án:** Sleep chỉ ước lượng tiến trình scheduling; CI tải khác nhau làm timing thay đổi. Latch/barrier cho phép chốt những điểm interleaving và đợi với timeout hữu hạn.

**Câu 6.** Một test ExecutorChannel cần chứng minh out-of-order completion. Có thể làm thế nào?

**Đáp án:** Chặn M1 ở latch sau khi handler bắt đầu, gửi M2, đợi M2 hoàn tất, rồi thả M1; assert observed completion là M2 rồi M1.

**Câu 7.** Global order và per-key order khác nhau thế nào?

**Đáp án:** Global order áp dụng trên mọi message. Per-key order chỉ yêu cầu thứ tự trong cùng orderId/accountId; key khác có thể xử lý song song.

**Câu 8.** Nếu event version 3 đến trước version 2, update DB theo version lớn hơn đã đủ chưa?

**Đáp án:** Chỉ đủ cho projection latest-wins nếu có thể bỏ qua trạng thái trung gian. Nếu nghiệp vụ yêu cầu tuần tự mọi transition, phải chờ version 2 hoặc xử lý gap theo policy.

**Câu 9.** Có thể dùng timestamp từ hai producer làm chuẩn ordering không?

**Đáp án:** Không nên khi cần bảo đảm chính xác: clock skew, độ phân giải timestamp và network delay có thể làm sai. Nên dùng version/sequence đáng tin từ domain.

**Câu 10.** Splitter có sequenceNumber thì đã bảo đảm downstream commit theo thứ tự chưa?

**Đáp án:** Chưa. Sequence headers giúp nhận diện vị trí phần trong group; resequencer có thể phát theo thứ tự, nhưng async stage phía sau vẫn có thể commit lệch.

**Câu 11.** File adapter có mặc định đọc file theo thứ tự upload hay business sequence không?

**Đáp án:** Không được giả định. Listing, comparator, mtime, filter và readiness có thể khác. Với nghiệp vụ quan trọng, cần explicit sequence/manifest và kiểm thử đến điểm commit.

**Câu 12.** Vì sao SFTP file tải xong thứ hai có thể được xử lý trước file tải xong đầu tiên?

**Đáp án:** Kích thước file, network latency, nhiều pollers, remote/local filters và worker concurrency có thể ảnh hưởng receive/completion. Cần contract và điều phối riêng.

**Câu 13.** HTTP request A được gửi trước B. Có bảo đảm response A về trước B không?

**Đáp án:** Không. Network, downstream workers và async callbacks có thể đảo thứ tự response. Correlation ID/request ID phải gắn đúng kết quả với yêu cầu.

**Câu 14.** Trong JMS, thuộc tính JMSXGroupID có ý nghĩa gì?

**Đáp án:** Trên những provider hỗ trợ, nó thường được dùng để điều phối các message cùng group về một consumer theo cơ chế message grouping. Cần kiểm tra implementation, failover và transaction semantics; không suy global order toàn broker.

**Câu 15.** Trong AMQP, nếu một consumer requeue message đầu tiên, những message sau có thể được xử lý trước không?

**Đáp án:** Có thể, tùy queue, prefetch, số consumer và requeue/redelivery. Test ordering phải bao gồm nack/requeue và commit outcome.

**Câu 16.** Kafka có bảo đảm ordering giữa hai partition không?

**Đáp án:** Không có global order chung. Kafka có ordering theo offset trong mỗi partition, còn business ordering cần key/partition strategy và giữ đúng sequence sau khi listener xử lý.

**Câu 17.** Kafka inbound giữ thứ tự offset nhưng handler dùng ExecutorChannel. Có thể DB commit sai thứ tự không?

**Đáp án:** Có. Async workers có thể hoàn tất lệch nhau. Cần serialization per-key hoặc version check/resequencing tại nơi side effect xảy ra.

**Câu 18.** JDBC SELECT ORDER BY created_at có đủ bảo đảm hai workers commit đúng thứ tự không?

**Đáp án:** Không. Concurrent claim, lock, transaction duration và retry quyết định commit order. Cần atomic claim/optimistic version cùng policy nghiệp vụ.

**Câu 19.** Vì sao dedupe theo eventId quan trọng dù final order status vẫn đúng?

**Đáp án:** Duplicate có thể tạo side effect như charge, shipment hoặc notification hai lần dù trạng thái cuối nhìn giống nhau. Test phải đếm cả side effects.

**Câu 20.** Khi một message bị đưa vào DLT, có thể cho version sau cùng key chạy bình thường không?

**Đáp án:** Tùy business contract. Nếu cần mọi transition tuần tự, phải giữ key, xử lý gap hoặc reconciliation. Nếu latest-wins, có thể tiếp tục theo quy tắc rõ và audit.

**Câu 21.** Một worker ghi DB thành công rồi crash trước broker ack. Lần nhận lại cần điều kiện gì?

**Đáp án:** Dedupe/idempotency và trạng thái commit bền vững để không lặp side effect; test fault injection tại ranh giới commit–ack.

**Câu 22.** Một QueueChannel test pass có chứng minh SFTP inbound cluster không xử lý trùng file không?

**Đáp án:** Không. Cluster cần test remote/local filter, shared metadata/claim, locking, restarts và business dedupe trên SFTP thật hoặc môi trường tương thích.

**Câu 23.** Khi test không thấy ErrorMessage, có thể kết luận poller hoạt động tốt không?

**Đáp án:** Không. Poller có thể ngừng chạy hoặc không nhận dữ liệu mà không phát exception. Cần last poll, last non-empty poll, backlog và health metrics.

**Câu 24.** Nên chọn một worker toàn cục hay xử lý song song theo key để giữ order?

**Đáp án:** Tùy yêu cầu và tải. Một worker giảm concurrency nhưng có thể tạo bottleneck. Serialization theo key hoặc optimistic version cho phép các key độc lập tiến triển song song.

**Câu 25.** Điều gì mới là bằng chứng đáng tin nhất cho tính đúng đắn end-to-end?

**Đáp án:** Invariant nghiệp vụ và side effects ở nơi commit/target, kèm audit retry, duplicate, recovery và correlation. Thứ tự log hoặc nhận message trên một channel đơn lẻ chỉ là bằng chứng cục bộ.

## 26. Kết luận

**Concurrency** làm hệ thống Spring Integration xử lý nhiều message hiệu quả hơn, nhưng đồng thời làm rõ sự khác biệt giữa **thứ tự nhận, thứ tự dispatch, thứ tự hoàn tất và thứ tự commit**. Một DirectChannel, QueueChannel, polling endpoint hay Kafka partition chỉ bảo đảm những gì topology và protocol thực sự hỗ trợ; chúng không tự định nghĩa toàn bộ ordering của nghiệp vụ.

Để kiểm thử đáng tin, cần đi từ **business contract**: hệ thống yêu cầu global order, per-key order, causal order hay chỉ một state version không lùi? Sau đó dùng **latch/barrier để tạo interleaving có chủ đích**, chạy **integration tests ở adapter thật**, xác minh **transaction, acknowledgment, retry, redelivery và side effects**, đồng thời kiểm tra **idempotency, state machine, optimistic locking hoặc resequencer** nếu cần.

Với File/SFTP, chú ý thứ tự listing/download, file readiness và filter. Với HTTP, chú ý request–response correlation và kết quả chưa rõ sau timeout. Với JMS/AMQP, kiểm tra message grouping, consumer concurrency, prefetch, ack và DLQ. Với Kafka, phân biệt **thứ tự trong partition** với **thứ tự xử lý/commit sau listener**. Với JDBC, ORDER BY chỉ định thứ tự tập kết quả, không thay cho **transactional claim, version check và concurrency control**.

Một bài test ordering tốt không chỉ chứng minh một danh sách message được sắp đúng. Nó phải chứng minh rằng **khi message đến trễ, bị lặp, retry, đi qua nhiều thread hoặc một worker crash, hệ thống vẫn giữ đúng trạng thái nghiệp vụ và không tạo side effect sai**.

### Tài liệu tham khảo chính thức

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): MessageChannel, endpoint, poller, aggregator, resequencer, adapter và testing.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): listener container, concurrency, acknowledgment, retry và dead-letter topics.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): RabbitMQ listener containers, acknowledgment, concurrency và retry.
- [Spring Framework TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): integration testing với Spring context.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter, assertions, parameterized và repeated tests.

Các ví dụ Java, SQL, JSON và Mermaid trong bài mang tính giáo dục. API Java DSL, mức hỗ trợ transaction, thread scheduling và broker ordering có thể khác theo phiên bản và cách cấu hình. Cần đối chiếu dependency thực tế và chạy kiểm thử trên môi trường đại diện production trước khi khẳng định bảo đảm concurrency/ordering.
