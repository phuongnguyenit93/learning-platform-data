# Buffer khi mất mạng trong Java Logging

## 1. Vì sao log cần buffer khi đường truyền gián đoạn?

Một dịch vụ Java có thể tạo hàng nghìn log mỗi giây trong khi hệ thống thu thập ở xa tạm thời không nhận được dữ liệu: mạng bị ngắt, DNS lỗi, TLS handshake thất bại, collector quá tải, backend bảo trì hoặc endpoint trả 429/503. Nếu mỗi lần gọi logger.info đều phải chờ một network request, ứng dụng nghiệp vụ có thể chậm nghiêm trọng. Nếu log chưa gửi được bị bỏ ngay, dấu vết điều tra sẽ biến mất đúng lúc hệ thống gặp sự cố.

**Buffer khi mất mạng** là cơ chế giữ log tạm thời trong queue hoặc storage có giới hạn, áp dụng retry/backoff và gửi bù khi đích phục hồi. Một hệ thống đúng còn phải trả lời: **buffer đầy thì làm gì, process chết thì dữ liệu còn không, retry có gây duplicate không, log có chứa dữ liệu riêng tư không, và bằng cách nào ta biết đã mất sự kiện?**

~~~text
Java application
    |
    v
Logger / encoder
    |
    v
Bounded buffer (RAM hoặc disk)
    |                      |
    | backend offline      | backend online
    v                      v
  retry later          send -> ACK
    |                      |
    +--> metrics/drop      +--> remove/checkpoint
              |
              v
       monitoring/alert
~~~

Bài nằm trong nhóm **Thu thập và vận chuyển** của module **Java Core Logging**. Nó không tập trung vào cú pháp logger.info đơn thuần mà đi sâu vào cơ chế transport, giới hạn tài nguyên và độ tin cậy của toàn đường đi.

### Mục tiêu học tập

- Phân biệt buffering, retry, acknowledgment (ACK), durability và retention.
- Biết buffer ở cấp Java JVM, local file, log agent/collector và broker có guarantee khác nhau.
- Chọn queue có giới hạn và overflow policy: block, reject/drop-new, drop-old, shed mức thấp, disk spill.
- Giải thích at-most-once, at-least-once, duplicate và ACK ambiguity.
- Viết chương trình Java 17 độc lập mô phỏng mạng offline, buffer đầy và gửi bù.
- Tính dung lượng buffer và tốc độ drain backlog khi mạng phục hồi.
- Dùng retry có timeout, exponential backoff, jitter và xử lý lỗi permanent.
- Hiểu giới hạn của Logback AsyncAppender, OpenTelemetry Collector, Fluent Bit và KafkaProducer.
- Thiết kế metrics, runbook, kiểm thử failure/recovery, security và quyền riêng tư.

## 2. Những vị trí có thể buffer log

Không phải mọi queue đều có cùng chức năng.

| Tầng | Lưu trữ | Chịu mất mạng? | Còn sau restart? |
| --- | --- | --- | --- |
| Queue trong ứng dụng Java | RAM của JVM | Có, trong capacity | Không tự bảo đảm |
| Logback AsyncAppender | RAM queue | Tách caller khỏi appender chậm | Không bảo đảm sau JVM crash |
| stdout và container runtime log | File/runtime tại node | Có thể làm nguồn để collector đọc lại | Phụ thuộc node/rotation/volume |
| Local rolling FileAppender | File cục bộ | Có log trên disk khi đích xa lỗi | Phụ thuộc filesystem, flush, retention |
| Collector in-memory queue | RAM collector | Có, đến khi đầy hoặc hết retry budget | Không bảo đảm |
| Collector persistent queue | Disk spool | Có nếu còn dung lượng và policy | Có thể phục hồi nếu volume còn nguyên |
| Kafka producer buffer.memory | RAM của client | Có trong thời gian chờ send | Không bảo vệ record chưa ACK khi process chết |
| Kafka broker lưu record đã ACK | Broker storage | Tùy cluster/quorum/retention | Theo durability/replication của broker |
| Transactional outbox | Database transaction | Có thể giữ event đến khi publisher gửi | Theo tính bền vững DB |

Một local log file **không tự là reliable spool**. Nếu collector không biết đã gửi tới đâu, không có checkpoint và ACK, file chỉ là bản dữ liệu để có thể khôi phục thủ công hoặc đọc lại theo cơ chế riêng.

Một buffer RAM cũng **không phải dữ liệu bền vững**. Khi pod/JVM bị kill, mọi item chưa được chuyển đi có thể biến mất. Cơ chế durable queue cần ghi dữ liệu ra disk/DB trước khi báo accepted theo contract, đồng thời có recovery logic.

### Chọn buffer theo mục tiêu

- **Giảm độ trễ request:** dùng async logging hoặc ghi stdout và để transport ở tầng khác; quan sát nguy cơ queue full làm block.
- **Chịu collector/backend mất mạng:** dùng agent/collector có queue và retry, cân nhắc persistent storage.
- **Chịu JVM crash:** ghi event vào durable store/spool trước khi báo đã lưu theo yêu cầu.
- **Bảo vệ audit bắt buộc:** ưu tiên hệ thống giao dịch/outbox/audit store được thiết kế riêng; log best effort không thay thế commit nghiệp vụ.

## 3. Buffering, retry, ACK và delivery semantics

Phải phân biệt:

~~~text
EVENT_CREATED
     |
     v
BUFFER_ACCEPTED  <- có thể mới chỉ là RAM
     |
     v
SEND_ATTEMPT
     |
     +--> failure -> retry_wait
     |
     v
REMOTE_ACKNOWLEDGED
     |
     v
REMOVE_FROM_QUEUE / CHECKPOINT
~~~

**Buffer accepted** không có nghĩa remote đã lưu. **Network send returned** không có nghĩa một async send đã thành công. **ACK** từ collector có thể chỉ chứng minh collector đã nhận, không nhất thiết remote index đã lưu bền vững. Muốn có một SLA chính xác phải định nghĩa ACK ở tầng nào.

| Mô hình | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| Best effort | Cố gửi khi có thể, không bảo đảm mọi event | Đơn giản, có thể mất |
| At-most-once | Theo phạm vi contract, không gửi lại sau một attempt | Ít duplicate, mất khi lỗi |
| At-least-once | Retry trong điều kiện đã thiết kế cho tới khi có ACK | Có thể duplicate |
| Exactly-once | Hiệu ứng chỉ một lần theo giao thức/transaction cụ thể | Không đạt được chỉ bằng retry + queue |

**ACK ambiguity:** nếu backend đã ghi event nhưng response ACK bị mất, sender sẽ timeout và có thể gửi lại. Nếu xóa event trước ACK, có nguy cơ mất. Nếu giữ đến sau ACK, có nguy cơ trùng.

~~~text
Sender                        Receiver
  |--- event_id=evt-7 --------->|
  |                            | persist evt-7
  |<---------- ACK ------------X  response lost
  |--- retry evt-7 ------------>|
  |                            | evt-7 may be duplicated
~~~

Dùng event_id ổn định xuyên các attempts và dedup/idempotent ingestion ở đích nếu được hỗ trợ. Correlation ID không thay thế event_id: hàng trăm log trong cùng một request có thể có cùng correlation ID.

## 4. Queue đầy: quyết định không thể bỏ qua

Buffer phải giới hạn số item và/hoặc tổng byte; một unbounded queue khi mất mạng có thể gây OutOfMemoryError hoặc làm đầy disk.

| Overflow policy | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Block producer | Giảm mất log tạm thời | Request chậm, cascading failure |
| Wait bounded rồi reject | Giới hạn latency | Event không được nhận khi timeout |
| Drop-new | Giữ log cũ | Mất thông tin mới nhất |
| Drop-old | Giữ log gần hiện tại | Mất nguyên nhân đầu outage |
| Shed DEBUG/TRACE | Giảm tải bằng cách ưu tiên sự kiện quan trọng | Không giữ được mọi chi tiết |
| Spill sang disk | Kéo dài thời gian chịu outage | Disk quota, latency, persistence, security |
| Fail nghiệp vụ nếu audit không lưu được | Bảo vệ invariant audit khi được thiết kế đúng | Giảm availability |

**Không drop âm thầm.** Nếu enqueue bị reject, caller/collector phải ghi nhận rejected count, outcome và alert. Một dòng remote log báo "dropped event" cũng có thể bị mất khi đường remote đó đang lỗi; metrics/cảnh báo cần đủ độc lập.

INFO không tự đồng nghĩa dữ liệu kém quan trọng; một audit event có thể dùng INFO. Phân loại log theo mục đích và yêu cầu nghiệp vụ, không chỉ level.

### Queue chỉ đo bằng item chưa đủ

Một event 100 bytes và một event 50 KB đều được tính là một item nhưng chiếm bộ nhớ rất khác nhau. Nếu queue_size của Collector tính theo requests/batches, phải biết mỗi batch chứa bao nhiêu log. Nếu heap queue lưu Java Strings/objects, overhead ngoài payload cũng đáng kể.

Đừng dùng ConcurrentLinkedQueue không giới hạn để tránh block rồi xem là an toàn. Không có backpressure, hệ thống chỉ dời lỗi từ network sang RAM/GC.

## 5. Demo Java 17 hoàn chỉnh: mất mạng, giữ tối đa ba event, gửi bù

Chương trình dùng **JDK 17 thuần** và JUL Logger để ghi chẩn đoán cục bộ. FakeSender mô phỏng remote endpoint offline/online: không cần mạng thật, không cần Kafka, Maven, Logback hay server. BoundedBuffer dùng ArrayDeque cho mô hình **đơn luồng**, capacity=3; event thứ tư bị từ chối.

**Tệp: NetworkBufferDemo.java**

~~~java
import java.io.IOException;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class NetworkBufferDemo {
    private static final Logger LOG =
            Logger.getLogger("example.logging.transport");

    record Event(String id, String message) { }

    interface Sender {
        void send(Event event) throws IOException;
    }

    static final class FakeSender implements Sender {
        boolean online;
        final Set<String> deliveredIds = new LinkedHashSet<>();

        @Override
        public void send(Event event) throws IOException {
            if (!online) {
                throw new IOException("network offline");
            }
            if (deliveredIds.add(event.id())) {
                LOG.info("REMOTE_ACCEPTED id=" + event.id());
            } else {
                LOG.info("REMOTE_DUPLICATE id=" + event.id());
            }
        }
    }

    static final class BoundedBuffer {
        private final int capacity;
        private final Deque<Event> queue = new ArrayDeque<>();

        BoundedBuffer(int capacity) {
            if (capacity < 1) {
                throw new IllegalArgumentException("capacity");
            }
            this.capacity = capacity;
        }

        boolean offer(Event event) {
            if (queue.size() >= capacity) {
                LOG.warning("BUFFER_REJECTED id=" + event.id());
                return false;
            }
            queue.addLast(event);
            LOG.info("BUFFERED id=" + event.id());
            return true;
        }

        void drain(Sender sender) {
            while (!queue.isEmpty()) {
                Event oldest = queue.peekFirst();
                try {
                    sender.send(oldest);
                    // Chỉ remove sau khi ACK được mô phỏng.
                    queue.removeFirst();
                } catch (IOException error) {
                    LOG.warning("RETRY_LATER id=" + oldest.id());
                    return;
                }
            }
        }

        int pendingCount() {
            return queue.size();
        }
    }

    public static void main(String[] args) {
        Handler output = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public synchronized void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(output);

        try {
            BoundedBuffer buffer = new BoundedBuffer(3);
            FakeSender sender = new FakeSender();

            buffer.offer(new Event("evt-1", "login"));
            buffer.offer(new Event("evt-2", "payment"));
            buffer.drain(sender); // Offline: giữ evt-1, evt-2.

            buffer.offer(new Event("evt-3", "inventory"));
            buffer.offer(new Event("evt-4", "notification"));
            // evt-4 bị reject: queue đã có ba item.

            sender.online = true;
            buffer.drain(sender); // Online: gửi ba item.
            LOG.info("PENDING " + buffer.pendingCount());
        } finally {
            LOG.removeHandler(output);
            output.flush();
            output.close();
        }
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac -encoding UTF-8 NetworkBufferDemo.java
java NetworkBufferDemo
~~~

**Stdout chính xác:**

~~~text
BUFFERED id=evt-1
BUFFERED id=evt-2
RETRY_LATER id=evt-1
BUFFERED id=evt-3
BUFFER_REJECTED id=evt-4
REMOTE_ACCEPTED id=evt-1
REMOTE_ACCEPTED id=evt-2
REMOTE_ACCEPTED id=evt-3
PENDING 0
~~~

### Giải thích

1. Hai sự kiện đầu được nhận vào queue khi sender chưa kết nối.
2. drain thử gửi evt-1; IOException khiến queue **không remove**, vì chưa nhận ACK.
3. evt-3 được nhận, chiếm slot cuối.
4. evt-4 bị BUFFER_REJECTED: không nằm trong buffer. Trong sản phẩm thật, caller phải xử lý boolean false và ghi counter riêng.
5. Khi sender.online=true, drain gửi FIFO evt-1, evt-2, evt-3 rồi queue rỗng.
6. FakeSender giữ Set deliveredIds để minh họa receiver có thể nhận diện ID; dữ liệu trong Set cũng chỉ là RAM, chưa là durable dedup.
7. JUL Logger được đưa qua Handler local stdout, không dùng remote sender để thông báo lỗi transport, tránh log lỗi của hệ thống log lại vào chính hệ thống đang lỗi.
8. Thứ tự output ổn định do code không dùng thread, scheduler hay network socket thực.

**Giới hạn:** Demo không xử lý thread safety (ArrayDeque đơn luồng), disk spool, retry timer/backoff, network timeout, ACK mất, process crash hoặc durable ingestion. Chỉ nên dùng để hiểu cơ chế. Một chương trình production cần queue concurrent phù hợp, worker lifecycle, timeouts, metrics, và chính sách khi đầy.

## 6. Retry với timeout, exponential backoff và jitter

Nếu network unreachable, thử send liên tục có thể tạo retry storm. Dùng **backoff tăng dần**:

~~~text
attempt 1: ngay lập tức
attempt 2: khoảng 1 s
attempt 3: khoảng 2 s
attempt 4: khoảng 4 s
attempt 5: khoảng 8 s
...
cap theo max interval, thêm jitter
~~~

Đây là ví dụ chính sách, không phải mặc định cho mọi exporter. Một công thức full jitter:

~~~text
delayCap = min(initialDelay * 2^(attempt - 1), maxDelay)
actualDelay = random(0, delayCap)
~~~

Trong implementation, tránh overflow số nguyên, dùng ScheduledExecutorService/scheduler thay vì sleep trên request thread, và đảm bảo dừng worker/shutdown đúng cách.

### Phân loại lỗi

- Transient: timeout, TCP reset, backend overload, một số 429/5xx. Retry có timeout/backoff.
- Lỗi cần sửa: invalid credentials 401/403, schema không hợp lệ, payload quá lớn, TLS certificate sai. Không retry vĩnh viễn chỉ vì code bắt được Exception.
- Rate limiting: xem Retry-After khi phù hợp.
- Permanent record failure: quarantine/DLQ theo policy và ghi counter, tránh một event lỗi chặn cả queue.
- Retry budget: giới hạn attempts/max elapsed time, xử lý event quá tuổi theo retention và priority.

**Retry không vô hạn trên tài nguyên hữu hạn.** Dù cho phép attempts vô hạn, disk/heap vẫn có giới hạn. Cần policy rõ khi hết chỗ, event quá cũ hoặc backlog gây nguy cơ cho ứng dụng.

### Jitter giúp gì?

Nếu hàng trăm pods cùng retry đúng mỗi 5 giây, backend vừa khôi phục có thể bị dồn tải lại. Jitter phân tán thời điểm retry. Khi phục hồi phải kiểm soát cả **recovery throughput**, không chỉ retry interval.

## 7. Persistent disk buffer và WAL

Memory queue mất dữ liệu khi JVM/collector process chết. Disk queue hoặc WAL có thể giúp phục hồi pending events sau restart, nhưng phải được triển khai/kiểm thử đúng.

~~~text
Encode event + immutable event_id
    |
    v
Append into disk segment/WAL
    |
    v
Persist according to fsync/durability policy
    |
    v
Network worker sends event
    |
    +--> on ACK: persist checkpoint/progress
    |
    +--> on retryable error: keep pending
    |
    v
Compact fully acknowledged segments
~~~

Một spool có độ tin cậy thực tế cần:

- Record framing với length/version/checksum và xử lý partial write.
- Kiểm soát concurrency, locking/ownership nếu có nhiều processes.
- fsync/flush policy: write() thành công chưa chắc an toàn sau mất điện.
- Checkpoint phản ánh những event đã ACK, recovery được sau crash.
- Replays có thể gây duplicate nếu checkpoint chưa kịp persist.
- Compaction/delete segment an toàn, không xóa nhầm item đang pending.
- Disk quota, inode limits, free-space reservation và overflow policy.
- TTL/retention của data nhạy cảm trong spool; ACL/encryption khi cần.
- Xử lý corrupted/truncated segments có metric/alert thay vì silently ignore.
- Volume lifecycle: Kubernetes ephemeral storage khác persistent volume.

Đừng tự xây "durable spool" chỉ bằng Files.writeString(..., APPEND). Một file append thiếu checkpoint/CRC/recovery không bảo đảm giao hàng đúng qua crash. Ưu tiên persistent queue của collector/agent được bảo trì khi phù hợp.

### Race sau ACK

~~~text
1. Backend lưu event.
2. ACK đến collector.
3. Collector chuẩn bị checkpoint.
4. Collector chết trước khi checkpoint bền vững.
5. Restart -> event có thể được gửi lại.
~~~

Có thể tồn tại duplicate dù disk buffer và receiver đều hoạt động đúng. Cần giao thức định nghĩa rõ ACK và idempotency ở nơi sử dụng log.

## 8. Buffer sizing và thời gian drain

Ước lượng lượng log phát sinh trong outage:

~~~text
raw_bytes = events_per_second
          × average_encoded_bytes_per_event
          × outage_seconds

required_bytes ≈ raw_bytes × headroom_factor
~~~

Ví dụ 1000 events/s, mỗi event 500 bytes, outage 10 phút (600 giây): **300.000.000 bytes, khoảng 300 MB dữ liệu thô**. Thực tế còn overhead queue/index/chunks và đỉnh tải.

Một thiết kế sizing cần biết:

1. Event rate theo giờ bình thường và peak; không dùng average duy nhất.
2. Encoded bytes/event, phân vị p95/max, không phải số ký tự Java String.
3. Mức outage mong muốn chịu được.
4. RAM/disk quota, reserved free space và TTL.
5. Tốc độ ingest phục hồi của backend, giới hạn retry/drain.
6. Event classes nào bắt buộc giữ và cái nào có thể sample/drop.
7. Số collector instances cùng gửi lại một lúc.
8. Retention và quyền riêng tư đối với backlog lâu ngày.

**Tính thời gian drain:** nếu sau hồi phục backend nhận 1100 events/s nhưng app vẫn sinh 1000 events/s, tốc độ giảm backlog ròng là 100 events/s. Backlog 600.000 events sẽ cần **6000 giây (100 phút)** mới hết, giả sử các tốc độ không đổi.

Buffer lớn nhưng đích không có năng lực nhận hơn nguồn phát sẽ không bao giờ drain hết. Phải tính đồng thời queue capacity và recovery throughput.

## 9. Logback AsyncAppender: không phải durable network buffer

Logback AsyncAppender thường đặt queue RAM giữa thread nghiệp vụ và appender sink.

Ví dụ config **Logback**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>1024</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

Đây chỉ là **snippet cấu hình**, không bảo đảm đúng cho mọi hệ thống.

- queueSize=1024 đếm event, không phải bytes hay thời gian outage.
- discardingThreshold=0 tắt cơ chế shedding tự động mặc định tại ngưỡng đối với các mức thấp, không làm queue vô hạn.
- neverBlock=false có nghĩa producer có thể chờ khi queue đầy, ảnh hưởng latency.
- maxFlushTime=5000 giới hạn thời gian chờ drain khi stop; event vẫn có thể còn và bị mất khi timeout.
- Đích ConsoleAppender ghi stdout. Mất kết nối của collector ở một process khác không được giải quyết bằng queue RAM của Logback.
- JVM chết đột ngột vẫn có thể mất queue chưa drain.
- Default AsyncAppender có thể bỏ một số event mức thấp gần capacity; phải test chính config đang triển khai.

Với Log4j 2, async logging có queue/disruptor và overflow semantics riêng; không sao chép tham số Logback sang Log4j 2. Đọc tài liệu đúng phiên bản.

## 10. OpenTelemetry Collector: sending_queue và file_storage

Một số Collector exporters dùng exporter helper hỗ trợ sending_queue và retry_on_failure. Bật storage extension có thể cho queue bền vững trên disk.

**Ví dụ YAML tham khảo** (yêu cầu binary có otlp receiver, batch processor, otlp exporter và file_storage extension; endpoint/volume/certificates là mẫu):

~~~yaml
extensions:
  file_storage/logqueue:
    directory: /var/lib/otelcol/log-queue

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp/backend:
    endpoint: logs.example.internal:4317
    tls:
      insecure: false
    sending_queue:
      enabled: true
      storage: file_storage/logqueue
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m

service:
  extensions: [file_storage/logqueue]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/backend]
~~~

### Hiểu đúng cấu hình

- sending_queue.queue_size có thể tính theo requests/batches mặc định, **không tự là số log records**; một số phiên bản cho sizer items/bytes.
- storage: file_storage/logqueue chọn persistent queue trên disk, với extension được build và khai báo đúng.
- Retry với max_elapsed_time=10m là hữu hạn; khi vượt hạn, batch có thể bị từ bỏ theo exporter semantics. Nó không tự giữ vĩnh viễn.
- Khi queue/disk đầy hoặc I/O lỗi, enqueue có thể thất bại và dữ liệu có thể mất nếu upstream không xử lý.
- Directory phải writable, có volume phù hợp. Ephemeral volume bị xóa sẽ làm mất spool.
- Bảo vệ spool bằng ACL, giới hạn truy cập/retention và encryption khi cần.
- Monitoring queue_size/capacity, dropped/send_failed, retry và disk usage.
- Một số context do auth extensions thêm không được duy trì qua persistent queue; cần xem cách authentication hoạt động sau replay.

**Không copy trực tiếp vào production:** phải thay endpoint thực, TLS/auth, resource limits, disk quota, và validate config bằng bản Collector cụ thể. Bản Collector lõi/minimal có thể không có extension file_storage; thường cần distribution hỗ trợ.

## 11. Fluent Bit: filesystem buffering

Fluent Bit có input storage.type filesystem và các tham số storage path/queue limits. Ví dụ file **fluent-bit.conf** để hiểu cấu trúc:

~~~ini
[SERVICE]
    Flush                   1
    Log_Level               info
    storage.path            /var/lib/fluent-bit/buffer
    storage.sync            normal
    storage.max_chunks_up   128

[INPUT]
    Name                    tail
    Tag                     app.logs
    Path                    /var/log/app/*.log
    DB                      /var/lib/fluent-bit/tail.db
    storage.type            filesystem

[OUTPUT]
    Name                    http
    Match                   app.logs
    Host                    logs.example.internal
    Port                    443
    URI                     /ingest
    Format                  json
    tls                     On
    Retry_Limit             False
    storage.total_limit_size 1G
~~~

Đây là snippet, chưa có credentials/endpoint thực và không phải deployment được xác nhận.

- storage.type filesystem cho phép buffer chunks trên disk.
- storage.max_chunks_up chủ yếu giới hạn chunks được giữ ở trạng thái up trong memory, **không phải dung lượng disk tổng**.
- storage.total_limit_size giới hạn logical queue cho output; khi đạt ngưỡng có thể drop các chunks cũ để ưu tiên dữ liệu mới theo tài liệu sản phẩm.
- Retry_Limit False có thể cho retry không giới hạn số lần, nhưng disk và nguồn log vẫn hữu hạn.
- Tail input DB checkpoint không giống output spool. Nếu file nguồn bị rotate/xóa trước khi Fluent Bit tail kịp, spool không phục hồi phần chưa ingest.
- Volume ephemeral khi pod/node mất cũng có thể làm mất chunks.

Để kiểm tra đúng, dùng một test endpoint trả 503 rồi 200, theo dõi disk queue/chunks, discarded count, retry và event IDs nhận sau khôi phục.

## 12. KafkaProducer: buffer.memory không phải outbox

Khi Java gửi log/event qua Kafka, client producer có buffer RAM. Một mẫu config:

~~~properties
buffer.memory=33554432
max.block.ms=60000
delivery.timeout.ms=120000
acks=all
enable.idempotence=true
~~~

Giá trị chỉ để minh họa; xem đúng version Kafka client.

- buffer.memory giới hạn gần đúng RAM dùng chứa records pending send; không phải hard cap của mọi cấp phát producer.
- max.block.ms giới hạn một số thao tác chờ buffer/metadata; timeout có thể báo lỗi.
- delivery.timeout.ms đặt giới hạn thời gian giao và báo kết quả qua producer API theo contract.
- acks=all là mức xác nhận broker theo replication semantics, không chứng minh downstream xử lý thành công.
- enable.idempotence giúp hạn chế duplicate từ producer retries trong phạm vi Kafka, không tạo exactly-once end-to-end.
- Producer process crash có thể làm mất records trong RAM chưa được broker xác nhận.

Snippet callback (cần kafka-clients, logger và biến ứng dụng; **không độc lập bằng JDK thuần**):

~~~java
producer.send(record, (metadata, error) -> {
    if (error == null) {
        logger.info("publish_ack topic={} offset={}",
                metadata.topic(), metadata.offset());
    } else {
        logger.error("publish_failed", error);
    }
});
~~~

Đừng in publish_success ngay sau một lời gọi send async. Cũng không nên đưa logger của chính producer đang lỗi vào vòng lặp log gửi thất bại: callback lỗi tạo một log mới gửi tiếp qua cùng producer có thể làm queue lớn thêm mãi. Dùng local status/metrics đã giới hạn.

Với audit events cần durable coupling với DB transaction, cân nhắc **transactional outbox**: ghi event trong cùng transaction với state, publisher phát lại có kiểm soát, consumer deduplicate theo event ID.

## 13. Chồng nhiều buffer: không phải càng nhiều càng an toàn

Một pipeline có thể là:

~~~text
Java AsyncAppender (RAM)
  -> stdout / node log file
  -> Fluent Bit filesystem chunks
  -> OpenTelemetry Collector persistent queue
  -> remote backend
~~~

Nó có thể hợp lý, nhưng có các trường hợp khó phát hiện:

- Queue app rỗng nhưng Collector còn backlog nhiều giờ.
- Một tầng drop-new, tầng khác drop-old, không còn bảo toàn chuỗi sự kiện.
- Local rolling logs bị xóa trước khi collector tail tới.
- Nhiều tầng retry cùng lúc làm dồn traffic khi backend phục hồi.
- Khi network lỗi, app vẫn log bình thường nhưng collector disk đã đầy và drop.
- Event được phát lại qua nhiều hop vì ACK ambiguity.
- Mỗi spool chứa bản sao dữ liệu nhạy cảm với retention khác nhau.

Hãy định nghĩa mỗi tầng nhằm mục đích gì; thu thập metrics của cả pipeline. Một queue bền vững được kiểm thử có thể tốt hơn nhiều queue không có owner và không biết khi nào mất dữ liệu.

## 14. Shutdown, crash, restart, disk full

**Graceful shutdown:** stop nhận event mới hoặc áp policy, drain trong thời gian hữu hạn, flush/close exporter và báo pending count. Nhưng shutdown hook có thể không chạy khi kill -9, OOM hay node mất điện.

**Crash recovery:** với durable spool, restart phải xác minh segment/checksum, đọc checkpoint, replay pending và xử lý duplicates. Crash sau ACK nhưng trước checkpoint bền vững có thể khiến đã gửi thành công mà vẫn replay.

**Disk full:** khi volume không ghi thêm được, persistent queue có thể reject/drop/block theo cơ chế sản phẩm. Cần quota, reserved space, alert và runbook, không để disk buffer lấp đầy node đến mức ảnh hưởng cả ứng dụng.

**Pod lifecycle:** nếu log buffer ở filesystem ephemeral, xóa pod/node có thể mất nó. PersistentVolume không tự giải quyết mọi crash consistency; còn cần cơ chế storage/queue thực sự hỗ trợ.

**Retention:** log trong spool vẫn là dữ liệu phải quản lý, có thể chứa IP, user ID, trace ID và thông tin nhạy cảm. Tránh retries vô hạn giữ một event quá lâu trái policy.

### Diagnostic feedback loop

Nếu remote appender gửi thất bại và lập tức tạo một ERROR log lại qua chính remote appender, có thể sinh vòng lặp:

~~~text
send fails
  -> log failure
  -> enqueue failure log
  -> send fails again
  -> queue grows faster
~~~

Nên dùng metrics hoặc một local diagnostic channel độc lập, giới hạn tần suất và không in raw payload/credential trong lỗi.

## 15. Metrics, alert và quyền riêng tư

Những **tên metric minh họa** có thể dùng:

| Metric | Câu hỏi |
| --- | --- |
| log_buffer_pending_events | Bao nhiêu events đang chờ? |
| log_buffer_pending_bytes | Bao nhiêu bytes pending? |
| log_buffer_capacity_bytes | Gần đầy chưa? |
| log_buffer_oldest_age_seconds | Event già nhất đã chờ bao lâu? |
| log_buffer_rejected_total | Bao nhiêu events không được nhận? |
| log_buffer_dropped_total | Bao nhiêu events bị drop? |
| log_delivery_attempts_total | Có retry storm không? |
| log_delivery_failures_total | Loại lỗi nào tăng? |
| log_delivery_ack_total | Bao nhiêu events/batches được ACK? |
| log_delivery_latency_seconds | Từ lúc tạo tới ACK mất bao lâu? |
| log_spool_used_bytes | Disk spool còn trống bao nhiêu? |
| log_spool_corrupt_total | Có corrupted segment không? |

OpenTelemetry Collector có exporter queue metrics, ví dụ otelcol_exporter_queue_size và otelcol_exporter_queue_capacity tùy bản phát hành. Luôn kiểm tra đơn vị requests/batches/items/bytes.

**Alert** khi occupancy cao, oldest age tăng quá SLA, rejected/drop > 0 đối với log quan trọng, disk quota cao, backend unavailable kéo dài, retries liên tục hoặc backlog không giảm sau khi online.

**Bảo mật:** không log token/cookie/password vào buffer; redact trước enqueue; đặt ACL/encryption khi cần, giới hạn retention và scope truy vấn. Không dùng user_id/event_id/correlation_id làm metric labels có cardinality rất lớn. Alert nên hoạt động ngay cả khi remote logging mất kết nối, không chỉ dựa vào query backend đang hỏng.

## 16. Test matrix cho outage và recovery

| Tình huống | Assert cần thiết |
| --- | --- |
| Endpoint online | Queue giảm và ACK theo contract |
| Offline ngắn | Buffer giữ dữ liệu trong capacity |
| Offline dài vượt capacity | Overflow policy đúng, rejected/drop có metric |
| Backend chậm | Request latency/backpressure đúng budget |
| HTTP 429 hoặc 503 | Retry/backoff điều tiết đúng |
| HTTP 401/403, schema invalid | Không retry vô hạn, có alert/quarantine |
| ACK mất sau remote persist | Retry cùng event_id, duplicate có thể phát hiện |
| JVM crash | RAM queue không được coi là durable |
| Collector restart | Disk queue phục hồi nếu volume/format hỗ trợ |
| Pod bị xóa | Không giả định ephemeral storage giữ được |
| Disk full | Reject/drop/block theo policy, không im lặng |
| Corrupt/truncated spool | Recovery/quarantine, status rõ |
| Hai processes dùng spool | Ownership/locking không làm hỏng file |
| Network flap | Retry jitter/backoff, không busy-loop |
| Shutdown với pending events | Deadline/flush/remaining count rõ |
| Payload quá lớn | Giới hạn bytes và lỗi có kiểm soát |
| PII/token trong payload | Redaction trước buffer |
| Nhiều producer threads | Thread-safety, count và ID không lẫn |
| Recovery throughput thấp | Queue age/drain time cảnh báo |

### Kiểm thử đơn vị cho Java demo

1. Gửi evt-1 và evt-2 vào buffer; pending=2.
2. Drain khi offline; pending vẫn 2, không có item bị remove.
3. Thêm evt-3 thành công; evt-4 bị reject khi capacity=3.
4. Chuyển online; drain; receiver nhận evt-1/2/3 theo FIFO.
5. Xác nhận evt-4 không được nhận, pending=0.
6. Mở rộng FakeSender cho tình huống đã lưu evt-2 nhưng ném IOException (ACK mất); retry cùng event_id rồi so sánh duplicate.

### Test tích hợp bằng endpoint stub

Tạo test HTTP server trả 503, 429, 200, hoặc timeout theo lịch. Đừng ngắt mạng chung của developer/production:

1. Phát N event IDs riêng và ghi timestamp gốc.
2. Cho endpoint offline; kiểm tra queue size/bytes/oldest age.
3. Restart exporter khi có pending để kiểm tra disk persistence.
4. Khôi phục endpoint; đếm events/duplicates ở receiver.
5. Test overflow, disk quota và error classification.
6. Kiểm tra volume khi pod/node bị thay.
7. So sánh event IDs trước/sau outage và thống kê mất/trùng.
8. Dọn test artifacts và restore cấu hình.

Không tạo disk full bằng cách ghi tới cạn ổ đĩa CI runner dùng chung. Dùng test volume/sandbox có quota.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Log mất khi offline | RAM buffer đầy/drop | Kiểm tra counters và overflow policy |
| Mất log sau restart | Queue chỉ ở RAM/ephemeral | Cân nhắc durable store, verify volume |
| Log có duplicate | ACK lost/retry batch | event_id/dedup, contract của receiver |
| JVM request bị chậm | Queue đầy và block producer | Điều chỉnh neverBlock/overflow/capacity có chủ đích |
| Disk tăng không dừng | Spool/retention sai | Quota, age limit, compaction, metrics |
| Collector quay lại nhưng không gửi | TLS/auth sai, payload bad, retry exhausted | Status/error class, quarantine |
| Fluent Bit còn thiếu records | Tail file rotate trước khi ingest | Tail checkpoint và source retention |
| Kafka send timeout | Buffer/metadata/broker unavailable | buffer.memory, max.block, delivery.timeout |
| OTLP queue_size còn thấp nhưng RAM cao | Queue tính batches, overhead khác | Sizer, event size, process memory |
| Recovery cực lâu | Đích chỉ nhanh hơn nguồn một chút | Tính drain throughput và throttle |
| Logging tự tạo log storm | Diagnostic cùng remote sink | Local metrics/status with rate limit |
| PII tồn tại trong spool | Redaction quá muộn | Redact trước enqueue, ACL/retention |

### Runbook khuyến nghị

1. Xác định service/exporter/endpoint và thời điểm bắt đầu outage.
2. Đo queue pending, oldest event age, disk usage, retry failures, drop count.
3. Phân loại nguyên nhân: network/DNS, TLS, credentials, backend, rate limit hay payload.
4. Bảo vệ ứng dụng bằng overflow policy đã được phê duyệt; không tự xóa spool có audit bắt buộc.
5. Sửa kết nối hoặc backend capacity.
6. Drain có giới hạn, theo dõi tăng tải và duplicate.
7. Đối soát event IDs/trace IDs theo khoảng thời gian outage.
8. Cập nhật alert, capacity, retention, backoff và integration tests.

## 18. Những sai lầm cần tránh

**1. Dùng queue vô hạn.** Mất mạng lâu biến thành OOM; luôn có capacity và monitoring.

**2. Coi async logging là durable.** Logback AsyncAppender RAM mất khi JVM chết.

**3. Coi gửi một lần là thành công.** API async trả Future chưa phải ACK; cần callback/contract.

**4. Retry quá nhanh.** Có thể gây storm; dùng backoff và jitter.

**5. Retry mãi một lỗi permanent.** 401, bad schema hoặc payload quá lớn cần alert/quarantine.

**6. Xóa pending trước ACK.** Có thể mất event khi send fail.

**7. Nghĩ ACK bảo đảm exactly-once.** ACK lost có thể dẫn tới duplicate.

**8. Coi disk queue không giới hạn.** Disk đầy hoặc ephemeral volume mất vẫn làm mất log.

**9. Không tính tốc độ drain.** Buffer sẽ tiếp tục tăng nếu destination không nhanh hơn source.

**10. Chỉ log lỗi remote qua chính remote đang lỗi.** Tạo feedback loop.

**11. Không kiểm thử crash/ACK lost.** Happy path không nói lên guarantee.

**12. Giữ log PII mãi trong spool.** Buffer vẫn phải tuân thủ security/retention.

## 19. Bài tập thực hành

**Bài 1 – Thay drop-new bằng drop-old.** Sửa BoundedBuffer để khi đầy sẽ bỏ event cũ nhất, nhận evt-4. So sánh những ID backend nhận và lý do drop-old có thể làm mất nguồn gốc outage.

**Bài 2 – ACK bị mất.** Cho FakeSender thêm evt-2 vào deliveredIds rồi ném IOException một lần. Lần retry sau cùng ID sinh duplicate; đề xuất receiver idempotency.

**Bài 3 – Concurrent queue.** Thay ArrayDeque bằng ArrayBlockingQueue, dùng ScheduledExecutorService cho retry; kiểm tra concurrency, interrupt và shutdown.

**Bài 4 – Tính byte capacity.** Với 1000 events/s, 500 bytes/event, outage 10 phút và headroom 1,5 lần, tính disk quota; so sánh với buffer đo theo batch.

**Bài 5 – OTel file_storage.** Trong môi trường test có Collector hỗ trợ extension, gửi OTLP logs, stop backend, restart collector rồi bật backend; kiểm tra pending queue, volume, retry deadline và duplicates.

**Bài 6 – Fluent Bit.** Tail file với event IDs, cho HTTP output trả 503 rồi 200. Quan sát storage chunks, quota và skipped records.

**Bài 7 – Kafka.** Với test broker, thay đổi buffer.memory/max.block.ms/delivery.timeout.ms, quan sát callback khi broker unavailable; không cho rằng producer RAM survives process death.

**Bài 8 – Security.** Gửi token giả/CRLF qua pipeline test, assert được redaction/escaping trước khi vào buffer, có ACL và retention.

**Bài 9 – Incident.** Giả lập 20 pods cùng offline, thiết kế jitter và giới hạn drain, đưa metrics/alerts sao cho backend bị hỏng không chặn khả năng cảnh báo.

## 20. Ghi nhớ

**Buffer khi mất mạng là sự đánh đổi giữa availability, durability, latency, tài nguyên và loss/duplicate.** Memory queue hỗ trợ outage ngắn, còn disk spool/persistent queue có thể giữ log qua restart khi storage và recovery đủ điều kiện, nhưng không miễn trừ disk full, retry budget, corruption hay retention. Queue đầy phải có hành vi rõ; retry phải có timeout, backoff, jitter và phân biệt lỗi transient/permanent.

Sau outage, ACK mơ hồ có thể khiến event bị gửi lại; event_id ổn định và idempotent ingestion là cơ chế quan trọng. Hãy tính **thời gian drain backlog**, đặt metrics/alerts độc lập và kiểm thử cả mất mạng, ACK lost, disk full, crash, restart, shutdown và dữ liệu nhạy cảm.

Logback AsyncAppender, Kafka producer buffer.memory, Fluent Bit filesystem buffering và OpenTelemetry Collector sending_queue/file_storage không cùng có một độ bền. Đối với audit bắt buộc lưu chắc chắn, cần durable event store hoặc outbox theo transaction nghiệp vụ thay vì chỉ tin vào một queue trong logger.

### Tài liệu tham khảo

- OpenTelemetry Collector Resiliency: https://opentelemetry.io/docs/collector/resiliency/
- OpenTelemetry Collector Exporter Helper: https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper
- OpenTelemetry Collector file_storage: https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/storage/filestorage
- Fluent Bit Buffering and Storage: https://docs.fluentbit.io/manual/administration/buffering-and-storage
- Fluent Bit Backpressure: https://docs.fluentbit.io/manual/administration/backpressure
- Logback AsyncAppender: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html
- Apache Kafka Producer Configs: https://kafka.apache.org/42/configuration/producer-configs/
- Oracle Java 17 BlockingQueue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Oracle Java 17 ScheduledExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
