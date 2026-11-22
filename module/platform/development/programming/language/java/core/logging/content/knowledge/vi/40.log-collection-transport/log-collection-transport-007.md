# Batch vận chuyển log trong Java: gom lô, flush, retry và kiểm soát mất dữ liệu

## 1. Batch vận chuyển là gì?

**Batch vận chuyển** (batched log shipping / batched exporting) là cơ chế **gom nhiều log records thành một lô** trước khi gửi từ ứng dụng, agent hoặc collector đến hệ thống nhận log. Thay vì mở/ghi một request mạng cho mỗi sự kiện, thành phần vận chuyển tích lũy records theo số lượng hoặc kích thước rồi gửi cả lô khi đạt ngưỡng hoặc hết thời gian chờ.

Ví dụ luồng vận chuyển:

```text
Java application
  |
  | INFO/WARN/ERROR events
  v
Logging API / appender / OpenTelemetry log bridge
  |
  v
Queue hoặc buffer có giới hạn
  |
  +---- đủ số record / byte ---> tạo batch
  |                                  |
  +---- đến hạn thời gian ----------+
  |                                  |
  +---- forceFlush/shutdown --------+
                                     |
                                     v
                              Exporter / sender
                                     |
                           HTTP/gRPC/OTLP/TLS
                                     |
                                     v
                         Collector / log storage
                                     |
                                 Dashboard
```

Gom lô nhằm **giảm số lần gọi mạng, syscall, header/protocol overhead**, tăng cơ hội compression và cải thiện throughput. Đổi lại, records có thể **chờ trong buffer lâu hơn**, chiếm memory, bị từ chối/drop khi đầy, và có thể mất khi tiến trình dừng đột ngột trước khi gửi.

Mục tiêu của bài trong nhóm **Thu thập và vận chuyển**:
- Hiểu batch là lô vận chuyển chứ không phải một log event lớn do ứng dụng tự ghép.
- Phân biệt batching trong JVM, logging backend, agent và OpenTelemetry Collector.
- Chọn ngưỡng số lượng, bytes, timeout, max queue, concurrency và cách flush.
- Thiết kế retry/backoff, tránh duplicate và phân tích mức bảo đảm at-most-once/at-least-once.
- Biết khi nào cần disk-backed queue, durable storage, circuit breaker và shutdown drain.
- Cấu hình thực tế cho OpenTelemetry Java Logs SDK, Collector và Grafana Alloy/Loki.
- Chạy ví dụ Java 17+ mô phỏng failure, bounded queue, size/time trigger và force flush.
- Kiểm thử, quan sát và xử lý sự cố vận chuyển mà không làm lộ dữ liệu nhạy cảm.

## 2. Đừng nhầm batch với async logging

**Async logging** và **batch vận chuyển** là hai quyết định khác nhau:

| Cơ chế | Câu hỏi giải quyết | Có thể không có cơ chế kia? |
| --- | --- | --- |
| Async logging | Thread nào xử lý công việc logging/I/O? | Có. Async worker vẫn có thể gửi mỗi record riêng |
| Batching | Gửi bao nhiêu records trong một lần export? | Có. Một batcher có thể đồng bộ, chặn thread gọi |
| Queue | Records chờ xử lý được giữ ở đâu, giới hạn thế nào? | Có. Một buffer batch nằm trong process mà không có queue async tổng quát |
| Retry | Gửi lỗi sẽ được thử lại theo cách nào? | Có. Batcher có thể fail/drop ngay, hoặc exporter retry |
| Compression | Biểu diễn bytes gửi qua mạng được nén ra sao? | Có. Batch có thể không nén và một payload đơn lẻ vẫn có thể nén |
| Durable buffering | Records tồn tại qua process crash/restart không? | Có hoặc không. Queue RAM không có độ bền |

Ví dụ: một JUL `Handler` đồng bộ có thể đợi tới 100 records rồi gọi API HTTP. Đó là **batching nhưng producer bị block** trong lần gửi. Ngược lại, Logback `AsyncAppender` thường cho phép một worker xử lý events; chỉ gắn AsyncAppender **không chứng minh** đích mạng gửi đúng 100 events/lần.

Đừng bật thêm nhiều tầng queue/batch một cách máy móc. Một hệ thống có thể xếp records ở JVM, sidecar/agent, Collector và exporter, khiến tổng độ trễ lớn hơn dự đoán và làm khó xác định nơi mất log.

## 3. Những thành phần trong pipeline thu thập và vận chuyển

Có thể chia trách nhiệm như sau:

```text
[Ứng dụng]
 logger -> encoder/LogRecordProcessor -> batch/queue A
                                            |
                                            v
[Agent / runtime]
 nhận stdout, file hoặc OTLP -> buffer/batch B
                                            |
                                            v
[OpenTelemetry Collector]
 receiver -> memory_limiter -> batch processor -> exporter queue
                                            |
                                            v
[Backend]
 Loki / hệ thống lưu log / SIEM
```

### 3.1. Batching ngay trong ứng dụng Java

OpenTelemetry Logs SDK có cơ chế `BatchLogRecordProcessor`. Ứng dụng có thể export các `LogRecord` đã được SDK nhận theo batch. Ưu điểm: giảm số lần export; nhược điểm: buffered logs trong memory của process, nên crash/kill có thể làm mất những records chưa xuất.

Với ứng dụng dùng JUL/SLF4J/Logback, **cần bridge/appender/instrumentation phù hợp** nếu muốn event đi vào OpenTelemetry Logs SDK. Chỉ khai báo properties của SDK **không tự bảo đảm** mọi `logger.info(...)` trong Java đang được OTel thu.

### 3.2. Batching ở agent hoặc collector

Agent đọc file/stdout hoặc nhận log từ SDK; nó có thể có buffer, retry, disk spool và cơ chế export riêng. Collector có processor `batch` để gom telemetry trước exporter, có thể phục vụ logs, metrics và traces theo pipeline tương ứng.

Ưu điểm của tầng này: nhiều ứng dụng chia sẻ việc vận chuyển, dễ kiểm soát mạng, auth, retry và thay đổi backend. Cần nhớ dữ liệu đã rời JVM nhưng **chưa chắc đã được backend lưu**; failure vẫn có thể xảy ra ở agent/collector/exporter.

### 3.3. Batching ở client đích

Ví dụ Grafana Alloy `loki.write` có `batch_size` và `batch_wait`. Một agent có thể gom log lines và gửi đến Loki khi đủ bytes hoặc tới hạn. `batch_size` ở công cụ này là **kích thước bytes**, trong khi `max.export.batch.size` của OTel Java là **số log records**. Trộn lẫn hai đơn vị khi tinh chỉnh cấu hình có thể gây sai lệch lớn.

## 4. Khi nào một batch được gửi?

Ba loại trigger thường gặp:

1. **Theo số record:** tích lũy đến `maxBatchCount` (ví dụ 512 records) thì gửi.
2. **Theo tổng bytes:** kích thước gần/đạt `maxBatchBytes` (ví dụ 1 MiB) thì gửi để tránh request quá lớn.
3. **Theo thời gian:** dù lô chưa đầy, gửi sau một `maxWait` hoặc `scheduleDelay` để giới hạn độ trễ của traffic ít.

Ngoài ra còn có:
- **Manual flush/forceFlush:** ứng dụng/SDK đề nghị đẩy dữ liệu đang chờ theo một API và deadline.
- **Shutdown:** cố gắng drain trước khi đóng processor/exporter.
- **Backpressure/queue pressure:** có thể buộc gửi, block, drop hoặc từ chối records; tùy triển khai.
- **Retry timer:** sau lỗi, thử gửi lại theo backoff hoặc lịch do exporter quản lý.

Trong một chính sách “size hoặc time, điều kiện nào đến trước”:

```text
t=0ms:  event A -> queue 1/3
t=100:  event B -> queue 2/3
t=200:  event C -> queue 3/3 -> gửi batch A,B,C
t=300:  event D -> queue 1/3
...
t=1300: D chưa đủ 3 records, tới hạn -> gửi D
```

Sơ đồ là minh họa về một batcher dùng **tuổi của record đầu tiên**. Những implementation thực tế có thể tính timer từ lần export gần nhất, tick cố định hoặc lần enqueue đầu tiên; **không suy semantics chỉ từ tên `timeout`**. Ví dụ Java mục 8 sẽ dùng tuổi record đầu tiên được lưu và đồng hồ mô phỏng để có kết quả xác định. OTel SDK/Collector có quy tắc timer theo triển khai của chúng.

### Trigger không phải giới hạn hard limit

Đặc biệt trong **OpenTelemetry Collector**:
- `send_batch_size` là **ngưỡng kích hoạt gửi**, có thể không phải giới hạn tuyệt đối của một batch đầu ra.
- `send_batch_max_size` mới nhằm giới hạn số record/data points/spans của batch và chia phần lớn thành các lô nhỏ hơn.
- `timeout` là trigger theo thời gian.

Điều này khác với API tự viết trong ví dụ, nơi `maxBatch` được dùng như giới hạn cứng cho số records mỗi lần gửi. Luôn xem đúng tài liệu cấu hình **của thành phần** bạn đang sửa.

## 5. Các tham số và cách lựa chọn

| Tham số | Ảnh hưởng | Nếu quá nhỏ | Nếu quá lớn |
| --- | --- | --- | --- |
| `max_batch_count` | Số events/lần gửi | Nhiều request và overhead | Lô nặng, khó retry/split |
| `max_batch_bytes` | Payload tối đa, thường trước/sau nén phải phân biệt | Kém hiệu quả kết nối | Lỗi 413/payload cap, spike memory |
| `max_wait` | Trì hoãn trước khi gửi lô chưa đầy | Overhead lớn khi traffic thấp | Log hiện muộn trên dashboard |
| `max_queue_records` | Sức chứa backlog trong memory | Drop/block sớm khi burst | Heap/GC tăng, OOM khi sink chết |
| `export_timeout` | Deadline cho mỗi lần gửi | Timeout nhầm khi mạng chậm | Worker kẹt quá lâu khi outage |
| `max_retries`/retry budget | Thời gian nỗ lực gửi lại | Dễ mất log khi lỗi ngắn | Queue phình và chậm phục hồi |
| `backoff_initial/max` | Nhịp retry | Storm/gây áp lực backend | Phục hồi chậm sau outage |
| `concurrent_exports` | Số lô in flight | Throughput thấp | Reordering, memory và áp lực backend |
| `compression` | Giảm bytes trên wire | Không nén tốn băng thông | Nén mạnh tốn CPU, cần tương thích |

Không có cấu hình “tối ưu chung” cho mọi dịch vụ. Cần đo lưu lượng, kích thước record, độ trễ chấp nhận, bộ nhớ, chi phí mạng, giới hạn receiver và hành vi failure.

### Ví dụ ước lượng

Giả sử service phát **10.000 log records/giây**, mỗi record có kích thước payload trung bình **400 bytes** trước compression:
- Raw payload khoảng **4.000.000 bytes/giây** (xấp xỉ 4 MB/giây, chưa tính metadata).
- Nếu gom **500 records/lô**, lý tưởng cần khoảng **20 lô/giây** ở tải đều.
- Mỗi lô trung bình chứa **200.000 bytes payload**; trên wire còn có envelope/header/encoding và compression.
- Một queue tối đa **5.000 records** giữ khoảng **2 MB raw payload**, nhưng **heap sử dụng thực tế lớn hơn** vì object headers, Strings, collections, serialization và runtime.

Các con số này chỉ để **ước lượng công suất**, không phải kết quả benchmark. Khi sink dừng 30 giây, nguồn 10.000 records/giây có thể tạo **300.000 records backlog** nếu không giảm tải. Queue 5.000 không đủ giữ toàn bộ. Bật queue RAM lớn hơn vô hạn không giải quyết vấn đề; cần backpressure, disk buffering, throughput headroom, chính sách drop hoặc đường lưu bền vững nếu cần.

### Sizing theo bytes thường quan trọng hơn count

Nếu mỗi record có kích thước rất khác nhau (stack trace, JSON, blob), chỉ giới hạn `500 records` có thể tạo lô 50 KB hoặc 20 MB. Với receiver có request-size limit, nên kết hợp ngưỡng số lượng + bytes hoặc dùng exporter có giới hạn payload hợp lệ. Đặc biệt: batch bytes **trước nén** không nhất thiết bằng payload bytes sau encoding/nén.

## 6. Ba thời điểm quan trọng: emit, enqueue và confirmed export

Một log event đi qua nhiều mốc:

```text
(1) Application emitted event
       |
       v
(2) Accepted by local queue
       |
       v
(3) Export attempt started
       |
       +--> timeout/error -> retry/drop/fallback theo policy
       |
       v
(4) Exporter reports success
       |
       v
(5) Receiver/collector processed, rồi lưu ở backend
       |
       v
(6) Có thể truy vấn trên dashboard
```

**Không đồng nhất những mốc này.**
- `logger.info(...)` trả về không chứng minh event đã vào queue.
- Queue chấp nhận không chứng minh exporter đã gửi.
- Gọi `send()` không chứng minh remote đã ACK.
- Exporter báo success **không nhất thiết** chứng minh backend đã index, lưu bền vững và có thể truy vấn ngay.
- Dashboard chưa thấy event có thể vì ingestion delay, filter, quyền, timestamp hoặc retention, không nhất thiết vì client không log.

Với hệ thống nhiều bước, thiết kế metric ở từng giai đoạn và định nghĩa rõ mốc nào được ghi là `sent`, `accepted`, `exported` hay `delivered`. Không dùng tên `published_successfully` cho một yêu cầu mới được enqueue.

### At-most-once, at-least-once và exactly-once

- **At-most-once:** không retry sau failure/timeout không rõ kết quả, nên giảm duplicate nhưng có thể mất event.
- **At-least-once (khi có đủ persistence/ack/retry phù hợp):** cố gửi lại cho đến khi nhận ACK theo chính sách, có thể phát sinh bản ghi trùng.
- **Exactly-once:** cần hợp đồng end-to-end rất cụ thể với receiver, idempotency/deduplication, transaction hoặc protocol thích hợp; **không có mặc định chỉ vì bật batch/retry**.

Một ACK có thể **bị mất** sau khi receiver đã chấp nhận lô. Producer thấy timeout và retry, từ đó receiver có thể nhận hai bản sao. Vì vậy batching cùng retry thường yêu cầu **stable event ID** hoặc chính sách deduplication khi duplicates ảnh hưởng business/audit.

Không nên coi log bình thường là hệ thống giao dịch có bảo đảm exactly-once. Nếu sự kiện audit/pháp lý yêu cầu độ bền, cần kênh ghi có hợp đồng reliability riêng, được thiết kế và kiểm chứng.

## 7. Retry, backoff và backpressure

### 7.1. Thất bại khi gửi một batch

Ví dụ exporter gửi 100 records; network timeout:
- Không biết chắc receiver đã nhận được bao nhiêu, hay đã ACK nhưng kết nối bị mất.
- Nếu bỏ batch, có thể mất nhiều records một lúc.
- Nếu retry toàn bộ batch, có thể trùng records đã được receiver chấp nhận.
- Nếu retry liên tục không giới hạn, queue tăng, tài nguyên bị chiếm, backend đang lỗi càng bị tấn công bởi retry storm.

Một chính sách production có thể áp dụng:
1. Chỉ retry **lỗi có khả năng hồi phục** như timeout hoặc một số status rate-limit/server errors, theo hợp đồng backend.
2. Dùng **exponential backoff + jitter**, tôn trọng `Retry-After` nếu protocol/backend quy định.
3. Giới hạn retry attempts/elapsed time, tổng backlog và số request đồng thời.
4. Khi receiver gửi **HTTP 413 Payload Too Large**, cần giảm kích thước/bẻ nhỏ batch hoặc điều chỉnh limit; retry nguyên lô vô hạn không có tác dụng.
5. Với **HTTP 400 schema invalid** hoặc **401/403 auth**, sửa dữ liệu/cấu hình/quyền; không coi tất cả 4xx đều retryable.
6. Nếu vượt budget, ghi **metric dropped/failed**, chuyển sang durable local spool/dead-letter path khi kiến trúc cho phép, hoặc thực thi policy chấp nhận mất logs.
7. Giữ log nội bộ về exporter lỗi **không chứa token/payload nhạy cảm**, tránh vòng lặp tự log lỗi rồi lại đưa vào chính exporter bị hỏng.

Không có một danh sách status retryable đúng cho mọi backend; SDK/exporter/protocol có thể có quy tắc riêng. Đọc tài liệu công cụ đang vận hành.

### 7.2. Khi queue đầy

Ba nhóm chính sách:

| Chính sách | Hành vi | Rủi ro |
| --- | --- | --- |
| Drop mới | Giữ backlog cũ, bỏ event mới | Mất lỗi vừa xảy ra khi hệ thống quá tải |
| Drop cũ | Ưu tiên log gần đây, loại backlog cũ | Mất chuỗi sự kiện trước đó, khó điều tra nguyên nhân |
| Block/backpressure | Chờ có chỗ trước khi trả về | Làm chậm request hoặc gây deadlock nếu dùng sai |
| Spill to disk | Ghi backlog sang durable buffer | Thêm I/O/disk quota, cần recovery/ACL/retention |
| Fail fast | Báo lỗi cho caller | Không phù hợp nếu chỉ vì logging mà request nghiệp vụ thất bại |

Chọn theo **mức độ quan trọng** của log. Debug có thể được sampling/drop; ERROR thường cần ưu tiên quan sát, nhưng không được tạo ưu tiên không công bằng khiến pipeline chết. Audit cần đường ghi bền vững phù hợp thay vì dùng queue RAM cho mọi trường hợp.

### 7.3. Disk spool khác queue RAM

Queue RAM mất khi JVM/agent crash hoặc host bị kill. Disk spool có thể giữ backlog qua restart nếu được triển khai đúng, nhưng cần:
- Quyền file/thư mục và encryption, không để lộ log chứa dữ liệu riêng tư.
- Dung lượng tối đa, retention, cleanup và recovery khi volume đầy/hỏng.
- Quy tắc ACK/offset checkpoint để không mất dữ liệu khi gửi được nhưng crash trước khi xóa bản spool.
- Khả năng duplicate sau restart, nên downstream có thể cần dedup.
- Tránh cùng nhiều process ghi một spool không được thiết kế đồng thời.

Disk buffering không tự tạo exactly-once; nó chỉ cải thiện khả năng sống sót của backlog qua một số loại failure.

## 8. Java 17+ chạy độc lập: mô phỏng batch theo kích thước, thời gian, retry và shutdown

Chương trình dưới đây chỉ dùng JDK 17, không yêu cầu broker, HTTP endpoint hoặc thư viện ngoài. Nó dùng **đồng hồ mô phỏng** (`nowMs`), cho kết quả stdout ổn định. Cấu trúc:
- `Event` chứa ID và event type đã được kiểm soát.
- `Pending` giữ event cùng thời điểm enqueue.
- `Batcher` có hàng đợi tối đa **3 records** và batch tối đa **3 records**.
- `DemoSender` giả lập lần gửi đầu tiên lỗi **trước khi receiver nhận**, những lần sau thành công.
- `offer` kích hoạt gửi khi đủ count; `onTick` gửi khi record đầu chờ đủ 1.000 ms; `flushForShutdown` gửi phần dư.
- Một lần enqueue khi queue đã đầy bị **từ chối minh bạch**, không âm thầm drop.

Tạo file **`BatchTransportDemo.java`**:

```java
import java.io.IOException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.stream.Collectors;

public final class BatchTransportDemo {
    record Event(String id, String type) {}
    record Pending(Event event, long queuedAtMs) {}

    interface Sender {
        void send(List<Event> batch) throws IOException;
    }

    static final class DemoSender implements Sender {
        int calls;
        final List<String> receivedIds = new ArrayList<>();

        @Override
        public void send(List<Event> batch) throws IOException {
            calls++;
            if (calls == 1) {
                throw new IOException("simulated_network_failure");
            }
            batch.forEach(event -> receivedIds.add(event.id()));
            System.out.println("exported="
                    + batch.stream().map(Event::id)
                        .collect(Collectors.joining(",")));
        }
    }

    static final class Batcher {
        final Deque<Pending> pending = new ArrayDeque<>();
        final Sender sender;
        final int maxBatch;
        final int maxQueue;
        final long maxDelayMs;
        int accepted;
        int rejected;

        Batcher(Sender sender, int maxBatch,
                int maxQueue, long maxDelayMs) {
            if (maxBatch <= 0 || maxQueue < maxBatch
                    || maxDelayMs <= 0) {
                throw new IllegalArgumentException(
                        "Invalid batch policy");
            }
            this.sender = sender;
            this.maxBatch = maxBatch;
            this.maxQueue = maxQueue;
            this.maxDelayMs = maxDelayMs;
        }

        void offer(Event event, long nowMs) {
            if (pending.size() >= maxQueue) {
                rejected++;
                throw new IllegalStateException("queue_full");
            }
            pending.addLast(new Pending(event, nowMs));
            accepted++;

            if (pending.size() >= maxBatch) {
                tryExport();
            }
        }

        void onTick(long nowMs) {
            if (!pending.isEmpty()
                    && nowMs - pending.peekFirst().queuedAtMs()
                       >= maxDelayMs) {
                tryExport();
            }
        }

        boolean tryExport() {
            int size = Math.min(pending.size(), maxBatch);
            if (size == 0) {
                return true;
            }

            List<Event> batch = pending.stream()
                    .limit(size)
                    .map(Pending::event)
                    .toList();

            try {
                sender.send(batch);
                for (int i = 0; i < size; i++) {
                    pending.removeFirst();
                }
                return true;
            } catch (IOException failure) {
                System.out.println("export_failed_size=" + size);
                return false;
            }
        }

        void flushForShutdown() {
            while (!pending.isEmpty()) {
                if (!tryExport()) {
                    throw new IllegalStateException("unsent_events");
                }
            }
        }
    }

    public static void main(String[] args) {
        DemoSender sender = new DemoSender();
        Batcher batcher = new Batcher(sender, 3, 3, 1_000);

        batcher.offer(new Event(
                "evt01", "order_created"), 0);
        batcher.offer(new Event(
                "evt02", "order_updated"), 100);
        batcher.offer(new Event(
                "evt03", "order_failed"), 200);

        try {
            batcher.offer(new Event(
                    "overflow", "test"), 300);
            throw new AssertionError(
                    "Expected bounded queue rejection");
        } catch (IllegalStateException expected) {
            if (!"queue_full".equals(expected.getMessage())) {
                throw expected;
            }
            System.out.println("queue_full_rejected=true");
        }

        batcher.onTick(999);
        batcher.onTick(1_000);

        batcher.offer(new Event(
                "evt04", "order_retried"), 1_300);
        batcher.onTick(2_299);
        batcher.onTick(2_300);

        batcher.offer(new Event(
                "evt05", "shutdown_notice"), 2_400);
        batcher.flushForShutdown();

        if (!sender.receivedIds.equals(
                List.of("evt01", "evt02", "evt03",
                        "evt04", "evt05"))
                || sender.calls != 4
                || !batcher.pending.isEmpty()
                || batcher.accepted != 5
                || batcher.rejected != 1) {
            throw new AssertionError(
                    "Batch delivery contract failed");
        }

        System.out.println(
                "accepted=" + batcher.accepted);
        System.out.println(
                "rejected=" + batcher.rejected);
        System.out.println(
                "delivered=" + sender.receivedIds.size());
        System.out.println(
                "send_attempts=" + sender.calls);
        System.out.println(
                "queue_remaining=" + batcher.pending.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac BatchTransportDemo.java
java BatchTransportDemo
```

**Standard output chính xác của chương trình:**

```text
export_failed_size=3
queue_full_rejected=true
exported=evt01,evt02,evt03
exported=evt04
exported=evt05
accepted=5
rejected=1
delivered=5
send_attempts=4
queue_remaining=0
```

### 8.1. Phân tích từng giai đoạn

**Giai đoạn A — size trigger và lỗi gửi đầu tiên.**

Khi enqueue `evt01`, `evt02`, `evt03`, queue có đủ 3 records và `tryExport()` chạy. `DemoSender` cố ý ném `IOException` ở lần gọi đầu. Batcher **không xóa** ba phần tử khi send lỗi; stdout in `export_failed_size=3`.

**Giai đoạn B — queue đầy.**

Một event `overflow` cố thêm khi còn 3 records pending, vượt `maxQueue=3`, nên `offer` ném `IllegalStateException("queue_full")`. Caller ghi `queue_full_rejected=true`, bộ đếm `rejected` tăng lên 1. Event này **không nằm trong delivered**.

**Giai đoạn C — retry do tick sau timeout.**

`onTick(999)` chưa đủ tuổi 1.000 ms của event đầu, nên không gửi. `onTick(1000)` gọi `tryExport`, lần này sender thành công, xác nhận batch `evt01,evt02,evt03` và queue được xóa ba items.

**Giai đoạn D — timeout flush lô nhỏ.**

`evt04` được enqueue lúc `1300`. `onTick(2299)` chưa đủ 1000 ms; `onTick(2300)` đã đủ, nên gửi một phần tử `evt04`. Batch **không cần đạt đủ 3 records** nếu time trigger đã tới hạn.

**Giai đoạn E — shutdown flush.**

`evt05` được enqueue lúc `2400` nhưng không đủ size/time. `flushForShutdown()` chủ động gửi phần dư. Tổng cộng `accepted=5`, `delivered=5`, `send_attempts=4` (1 lỗi + 3 lần thành công); không còn pending.

### 8.2. Những giới hạn cần hiểu của demo

Đây là **trình mô phỏng đơn luồng, đồng bộ**, không phải exporter production:
- `nowMs` được caller truyền vào; không có scheduler thật. Không nên đưa elapsed test clock như vậy vào production rồi tin timer tự chạy.
- `ArrayDeque` **không thread-safe**; không sử dụng Batcher từ nhiều producer threads nếu chưa đồng bộ hoặc thay bằng kiến trúc queue/worker an toàn.
- `sender.send` đồng bộ và có thể chặn caller; trong hệ thống lớn cần worker và timeout.
- Lỗi giả đầu tiên xảy ra **trước khi ghi receivedIds**; không mô phỏng trường hợp receiver đã nhận nhưng ACK bị mất. Real retry có thể dẫn đến duplicate.
- Không có exponential backoff, jitter, TLS, OTLP, HTTP, WAL, persistent storage, metrics ngoài stdout hoặc lifecycle deadline.
- `flushForShutdown` có thể ném lỗi nếu sender không hồi phục. Trong production cần timeout hữu hạn, chính sách backup/drop phù hợp và báo số records còn lại.
- Thời điểm đầu được đánh dấu bằng `0` trong đồng hồ mô phỏng; chương trình không dựa vào wall clock thực.
- `Event` chỉ chứa metadata an toàn và không giữ raw message payload/secret; dữ liệu log thực phải được minimize/validate tương tự.

**Bài học chính:** chỉ xóa các records khỏi queue sau mốc sender báo thành công **theo contract của sender**; có chiến lược minh bạch khi queue đầy; cần flush lô chưa đầy theo thời gian và trước shutdown. Nhưng **thành công ở sender không tự đảm bảo end-to-end durability**.

## 9. OpenTelemetry Java: BatchLogRecordProcessor

OpenTelemetry Logs SDK chuẩn hóa việc xử lý records trước khi xuất qua `LogRecordExporter`. Có hai họ phổ biến:
- **SimpleLogRecordProcessor:** chuyển record cho exporter khi sự kiện sẵn sàng, phù hợp một số tình huống phát ít log hoặc test; không có batching size/time kiểu batch processor.
- **BatchLogRecordProcessor:** gom records vào queue và export theo lô. SDK specification yêu cầu cơ chế batch cùng xử lý forceFlush/shutdown và kiểm soát các giới hạn.

Khi dùng **OpenTelemetry Java SDK autoconfigure** hoặc agent có hỗ trợ logs exporter, các properties phổ biến là:

```properties
otel.logs.exporter=otlp
otel.blrp.schedule.delay=1000
otel.blrp.max.queue.size=2048
otel.blrp.max.export.batch.size=512
otel.blrp.export.timeout=30000
```

Giải thích:
- `otel.blrp.schedule.delay`: khoảng thời gian scheduling xuất batch, tính bằng **milliseconds**.
- `otel.blrp.max.queue.size`: số log records tối đa được xếp vào queue của BatchLogRecordProcessor.
- `otel.blrp.max.export.batch.size`: giới hạn số records trong một export batch; phải chọn phù hợp với queue.
- `otel.blrp.export.timeout`: timeout của export operation, tính bằng milliseconds.
- `otel.logs.exporter=otlp`: chỉ định exporter logs theo cấu hình OTel hỗ trợ.

Đây là **đoạn cấu hình minh họa**; trên một số bản SDK/autoconfigure, các giá trị ví dụ trùng default được tài liệu công bố. Không hardcode một bộ defaults cho mọi bản Java agent/SDK hoặc giả định appender bất kỳ đọc được file properties này.

**Quan trọng:** Các dòng trên tự chúng **không làm cho JUL/SLF4J tự đi vào OTel**. Phải có bridge/instrumentation/Logback appender/Log4j 2 appender đúng version, resource metadata, endpoint/credentials và network policy. Xem đường log thực tế: `logger.info` → appender/bridge → SDK → exporter → receiver.

### ForceFlush và Shutdown

`forceFlush` là yêu cầu SDK/processor cố gắng export các records đã nhận trước thời điểm gọi, với thời gian chờ theo API; nó **không phải cam kết rằng backend đã lập chỉ mục** hoặc dữ liệu bền vững. `shutdown` nên flush/đóng các processor/exporter, nhưng có thể trả lỗi/timeout khi sink không đáp ứng. Đừng:
- gọi `forceFlush` cho từng log record, vì điều đó làm mất hiệu quả batching và chặn request;
- bỏ qua kết quả timeout/failure rồi báo “đã giao hàng”;
- đợi vô hạn trong shutdown hook khiến triển khai không thể kết thúc.

Một chính sách hợp lý thường flush ở **shutdown có kiểm soát**, trong một số **FaaS invocation** hoặc lúc cần đảm bảo một ranh giới quan sát quan trọng, với deadline hữu hạn.

## 10. OpenTelemetry Collector: batch processor và exporter

Collector có processor `batch` dùng cho logs/spans/metrics. Nó được đặt trong pipeline sau các bước có thể từ chối/drop, thường **sau `memory_limiter`**, để không batch dữ liệu sau đó lại bị bỏ một cách không cần thiết.

Ví dụ cấu hình **OTel Collector minh họa** (không phải cấu hình có thể chạy nguyên xi nếu chưa có receiver/network/exporter cụ thể):

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    send_batch_size: 512
    send_batch_max_size: 1024
    timeout: 200ms

exporters:
  otlphttp:
    endpoint: https://collector.example.invalid

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp]
```

Ý nghĩa:
1. Receiver giả định nhận **OTLP/gRPC** trên loopback; cần kiểm tra certificate/network/namespace trong deployment thực tế.
2. `memory_limiter` thực thi cơ chế giới hạn bộ nhớ trên pipeline, không phải đảm bảo tuyệt đối mọi queue downstream sẽ không đầy.
3. `send_batch_size=512` là **ngưỡng kích hoạt**; `send_batch_max_size=1024` giới hạn batch xuất theo config, không nhỏ hơn trigger.
4. `timeout=200ms` làm batch được gửi theo thời gian khi chưa đủ size; actual scheduling theo implementation.
5. `otlphttp` gửi đến địa chỉ **example.invalid**, cố ý không có backend thật; phải thay bằng endpoint, TLS/auth, timeout/retry policy thực tế.
6. `batch` đặt **trước exporter**, còn exporter có thể có `sending_queue` và `retry_on_failure` riêng, cần xem config support của phiên bản Collector/distribution cụ thể.

Tài liệu của Collector lưu ý rõ: `send_batch_size` **không phải hard limit**; muốn giới hạn kích thước cần `send_batch_max_size`. Nếu đang cố sửa lỗi receiver 413, đừng chỉ giảm trigger mà quên giới hạn thực của payload ở exporter.

### Batching theo metadata và tenant

Một số pipeline cần tách batch theo client metadata/tenant hoặc header để không trộn nhiều nhóm dữ liệu. Collector hỗ trợ `metadata_keys`/`metadata_cardinality_limit` ở batch processor, nhưng mỗi giá trị kết hợp metadata có thể tạo thêm batcher và chiếm bộ nhớ. Đừng chọn raw request ID, token, user ID hay high-cardinality field làm khóa tạo batcher; cũng không tin tenant ID từ header client khi chưa xác thực.

Nếu hệ thống multi-tenant, **tính cô lập dữ liệu phải nằm ở auth/routing/backend policy**, không chỉ ở tên batch hoặc dashboard variable.

## 11. Grafana Alloy và Loki: batch theo bytes và thời gian

Grafana Alloy có component `loki.write` để vận chuyển log entries tới Loki. Các tham số của `endpoint` như:
- `batch_size`: kích thước lô tối đa (ví dụ `"1MiB"`), **đơn vị bytes**.
- `batch_wait`: thời gian chờ lô trước khi gửi (ví dụ `"1s"`).
- `url`: Loki push endpoint.
- Các tùy chọn khác cho TLS, authentication, timeout, retry hoặc queue tùy phiên bản/config.

Ví dụ **đoạn cấu hình Alloy**, cần nối nguồn log vào `loki.write.default.receiver` và đặt đúng credentials/backend:

```hcl
loki.write "default" {
  endpoint {
    url        = "https://loki.example.invalid/loki/api/v1/push"
    batch_size = "1MiB"
    batch_wait = "1s"
  }
}
```

Đừng copy cấu hình này sang Grafana Loki server rồi nghĩ nó tạo ingester; `loki.write` là **client/agent component**, cần một nguồn logs với `forward_to` phù hợp ở phía trên.

Trong Grafana Alloy, một số metrics liên quan batch có thể gồm `loki_write_batch_retries_total`, `loki_write_dropped_entries_total`, `loki_write_sent_entries_total` và histogram batch/request size. Tên metrics/availability phụ thuộc phiên bản, deployment và cách scrape; hãy kiểm tra dữ liệu thực thay vì mặc định mọi metric đều tồn tại.

### Cẩn thận với nhiều tầng batching

Giả sử Java SDK có delay 1 giây, Collector có timeout 200ms và Alloy `batch_wait=1s`. Tổng độ trễ **không đơn giản luôn bằng 2,2 giây**, vì các timer và ngưỡng size có thể đánh thức sớm hoặc không đồng bộ. Nhưng ở tải thấp, có thể **tích lũy độ trễ** trên nhiều buffer. Đo end-to-end từ event timestamp đến lúc searchable, thay vì chỉ nhìn từng `schedule.delay`.

## 12. Compression và giới hạn payload

Compression thường giúp batch đạt hiệu quả mạng tốt hơn so với từng record riêng, nhưng cần hiểu:
- Nén giảm bytes **trên wire**, không xóa chi phí cấp phát object/serialization ban đầu.
- Lô lớn có thể tạo spike memory/CPU trong serialization hoặc compression.
- Receiver có giới hạn request bytes hoặc decompressed size; lỗi 413 hoặc reject vẫn có thể xảy ra.
- Payload của stack traces dài, JSON hoặc binary đã nén thường có đặc tính compression khác nhau.
- Không tự chọn compression algorithm chỉ vì “nhỏ nhất” nếu latency/CPU trở thành nút thắt.

Bảng so sánh khái niệm:

| Kiểu gửi | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| 1 record/request | Độ trễ gửi thấp khi không queue | Nhiều overhead request, băng thông |
| Batch 100 records | Giảm số request, dễ nén | Tăng đợi trước gửi, retry cả batch |
| Batch 1000 records | Ít request hơn | Rủi ro lô quá lớn, đòi memory |
| Batch có giới hạn bytes + count | Điều chỉnh khi record size không đều | Cần accounting chính xác trước/sau encoding |
| Batch + compression | Giảm wire bytes khi dữ liệu nén tốt | CPU/latency nén, config receiver |

Một test tốt ghi **uncompressed batch bytes**, **encoded request bytes**, latency, CPU và tỷ lệ lỗi của receiver. Đừng kết luận “batch=1000” luôn tốt hơn “batch=100” nếu payload/đích mạng thay đổi.

## 13. Thứ tự, concurrency và đồng hồ trong batch shipping

Batch thường là collection có thứ tự tại sender, nhưng **thứ tự hiển thị trong backend không có bảo đảm chung**:

- Nhiều producer threads có thể enqueue gần đồng thời; thứ tự call site và thứ tự queue có thể khác.
- Có nhiều in-flight batches; batch gửi sau có thể ACK trước batch gửi trước.
- Retry một batch cũ có thể khiến events đến backend **sau** events mới hơn.
- Một collector có thể gắn ingestion timestamp muộn hoặc đổi sort order.
- Log service khác nhau có clock skew; dấu timestamp không tạo thứ tự toàn cục.
- Restart hoặc disk replay có thể đưa lại events từng được gửi.

Vì vậy log cần **timestamp**, source/service/instance khi hợp lệ, event ID hoặc correlation ID được kiểm soát. Với nghiệp vụ yêu cầu thứ tự chặt, không dựa vào thứ tự dòng log vận chuyển như cơ chế đồng bộ dữ liệu; dùng queue/transaction/broker với guarantee đúng contract.

### Context propagation khi async/batch

SLF4J MDC, Log4j ThreadContext hoặc request-scoped data có thể được lưu ở thread gửi log. Nếu exporter worker đọc lại context từ thread của nó, có thể mất/wrong request ID. Đúng cách là **capture những field bất biến khi tạo LogRecord**, rồi truyền vào event/structured attributes. Không truyền tham chiếu đến request object mutable và tin rằng nó còn đúng khi batch được gửi sau vài giây.

## 14. Quyền riêng tư và an toàn dữ liệu trong buffer

Batch vận chuyển làm nhiều log events cùng tồn tại trong memory, trên wire, agent spool và backend. Rủi ro:
- Cùng batch có thể chứa token, cookie hoặc dữ liệu nhạy cảm nếu application log sai.
- Retry hoặc debug exporter có thể vô tình dump nguyên batch lỗi.
- Disk buffer/backup giữ dữ liệu lâu hơn retention chính.
- Multi-tenant batching sai có thể gửi event giữa các tenant hoặc dùng nhầm credentials.
- Compression/encryption không thay thế minimization/redaction.

Nên:
1. Chỉ log các field cần thiết; không đưa password, API key, Authorization, Cookie, request body hoặc payload riêng tư không cần.
2. Dùng structured encoder và giới hạn độ dài các field.
3. Redact tại nguồn; filter tại collector chỉ là **phòng vệ bổ sung**, vì dữ liệu thô đã đi qua tầng trước.
4. Kết nối qua TLS, xác thực exporter/receiver và giới hạn quyền backend.
5. Disk spool phải có ACL/ownership, quota, encryption/retention và cleanup.
6. Đừng log nguyên HTTP response body của collector khi lỗi, vì phản hồi có thể chứa thông tin nội bộ.
7. Test với canary giả (không phải secret thật) ở nguồn và backend.
8. Review logs của **chính telemetry pipeline**, tránh vòng phản hồi exporter-error tạo thêm lỗi vô hạn.

**Batch lớn không làm một field nhạy cảm trở nên ít nguy hiểm hơn.** Nếu một log line có token, việc gom lô và nén chỉ chuyển token đó đi cùng nhiều records khác.

## 15. Monitoring: làm sao biết batch pipeline đang khỏe?

### 15.1. Golden signals cho pipeline logs

| Metric/signal | Ý nghĩa | Cần cảnh báo khi |
| --- | --- | --- |
| `log_records_emitted_total` | Số event ứng dụng tạo | Giảm bất thường khi traffic vẫn bình thường |
| `queue_size` và `queue_capacity` | Backlog hiện tại và giới hạn | Queue liên tục gần đầy |
| `queue_oldest_age_ms` | Event lâu nhất chưa export | Vượt mục tiêu log freshness |
| `batch_records`/`batch_bytes` | Quy mô lô | Lô quá nhỏ gây overhead hoặc quá lớn |
| `export_attempts_total` | Số lần gọi exporter | Tăng mạnh trong khi receiver không nhận |
| `export_success_total`/`export_fail_total` | Kết quả gửi | Lỗi tăng hoặc success ngừng |
| `export_retry_total` | Số lần retry | Backoff storm hoặc outage kéo dài |
| `logs_dropped_total` | Records bị bỏ vì queue/full/retry limit | Bất kỳ drop bất thường ở log quan trọng |
| `export_duration_ms` | Latency gửi batch | Receiver/network chậm |
| `ingestion_lag_ms` | Event time đến searchable | Dashboard quan sát trễ |
| Disk spool used/free | Mức sử dụng buffer bền vững | Sắp đầy, không còn khả năng nhận |

Đây là **tên metric mô tả**, không khẳng định SDK/Collector/Alloy mặc định tạo các tên này. Dùng metrics chính thức của component/version thực tế, mapping vào dashboard và đặt threshold theo SLO nội bộ.

### 15.2. Dashboard cho batch shipping

Một dashboard vận hành nên có:
- Traffic đầu vào: records/s, bytes/s theo service/env.
- Export thành công: records/s, batches/s, average batch size.
- Export failures, retry rate, HTTP/gRPC status và timeout.
- Queue usage %, oldest record age, disk spool headroom.
- Dropped records theo lý do và severity khi công cụ hỗ trợ.
- Ingest latency p95/p99 và chênh lệch accepted vs exported.
- Backend throttle/429, receiver request size/413, TLS/auth failures.
- Deployment annotations; thay config batch nào gần thời điểm sự cố?
- Runbook/owner, link đến log exporter và trạng thái collector.

**Đừng theo dõi chỉ “số batch thành công”**. Ví dụ 100 batches/s có thể chỉ chứa 1 record/batch hoặc 500 records/batch. Đo cả số records và bytes. Khi sampling hoặc log level thay đổi, records/s thay đổi không nhất thiết là lỗi exporter.

### 15.3. End-to-end test freshness

Tạo một event canary an toàn với `event_id` và event timestamp, ghi ở application, chờ đến khi backend có thể query. Đo:
- Thời gian từ emit đến exporter ACK.
- Thời gian từ ACK đến searchable.
- Tổng freshness delay.
- Số canary mất/trùng qua retry, restart và collector outage.

Một canary chỉ chứng minh một đường thử ở thời điểm đó hoạt động; không thể bảo đảm mọi log đều được giao hàng. Với observability SLO quan trọng, cần đo liên tục và giám sát collector health.

## 16. Kiểm thử batch vận chuyển

### 16.1. Unit test không phụ thuộc đồng hồ thật

Cách ổn định là inject clock hoặc truyền `nowMs` như demo. Test:
1. Enqueue nhỏ hơn `maxBatch`: chưa gửi.
2. Đạt `maxBatch`: gọi sender một lần với đúng tập record.
3. Chưa đạt size nhưng quá `maxWait`: gửi một lô nhỏ.
4. Lỗi sender: không xóa records chưa được xác nhận.
5. Queue đầy: chính sách throw/drop/block thực sự xảy ra và có số đếm.
6. Lần retry thành công: backlog được xóa một lần trong bộ nhớ.
7. Shutdown flush: records chưa đủ batch được đẩy đi.
8. Batch cuối nhỏ hơn ngưỡng giữ nguyên thứ tự và không bị thêm phần tử giả.

Đừng kiểm tra bằng `Thread.sleep(1000)` rồi hy vọng scheduler đúng lúc; CI có thể chậm hoặc bị pause. Dùng fake clock/fake sender/test executor để test deterministic.

### 16.2. Failure injection và network tests

Trong môi trường thử nghiệm:
- Sender trả timeout, 429, 503, 413, 400, 401/403; xác nhận policy tương ứng.
- Receiver nhận batch nhưng ACK mất: retry tạo duplicate hay không, backend xử lý thế nào?
- Thay đổi latency và bandwidth; đo throughput, CPU, heap, queue.
- Kill JVM hoặc collector **trước flush**: xác nhận mất dữ liệu RAM theo contract.
- Restart với disk spool: kiểm tra recover/duplicate/checkpoint.
- Collector chậm hơn producer: queue tới limit, ứng dụng có block/drop theo policy không?
- Tắt network 30 giây rồi bật lại: độ trễ để xả backlog và tình trạng retry storm.
- Gửi record có stack trace dài: batch có vượt bytes limit không?
- Test trường timestamp muộn, trace/context và thứ tự trong backend.

Nếu sử dụng OTLP exporter và Collector, gắn receiver test thay cho endpoint production, quan sát metadata và exact count. **Không diễn giải số log lines đã enqueue thành số lines đã được backend chấp nhận**.

### 16.3. Stress test và benchmark

So sánh các cấu hình nhỏ/vừa/lớn với **cùng workload**:
- Producer rate cố định; kích thước record trung bình và percentile.
- Tỷ lệ INFO/WARN/ERROR, mức sampling và log level.
- Network RTT, packet loss, throttle, TLS/compression mode.
- Exporter queue, batch byte limit, maxWait, concurrency, retry budget.
- Heap/GC và p95/p99 application latency.
- Backend accepted records/s và end-to-end log freshness.

Tăng batch size có thể cải thiện throughput trong một vùng nhất định nhưng làm latency và heap tăng. Không tuyên bố con số speedup cho mọi môi trường khi chưa đo.

## 17. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi `logger.info` = đã lưu backend | Mất events mà không phát hiện | Đo từng mốc queue/export/ingest |
| Chỉ batch theo count, không theo time | Traffic thấp chờ lâu hoặc không flush | Có timeout và shutdown flush |
| `max_wait` quá cao | Dashboard hiện log trễ | Đo freshness, chọn SLO |
| Queue không giới hạn | OOM và GC khi receiver outage | Giới hạn queue, disk spool/backpressure |
| Drop thầm lặng khi đầy | Mất dấu vết lúc sự cố | Metric/alert dropped và policy |
| Gửi retry ngay lập tức liên tục | Retry storm, tăng lỗi backend | Exponential backoff + jitter |
| Retry không phân biệt 413/400/429 | Lỗi không hồi phục lặp vô ích | Phân loại và split/sửa config |
| Không có event ID/dedup khi retry | Trùng record khi ACK bị mất | Idempotency/dedup theo contract |
| ForceFlush mỗi event | Vô hiệu hóa batching | Chỉ flush ở ranh giới cần |
| Shutdown không có deadline | Process treo lâu hoặc mất buffer | Drain có timeout và report pending |
| Cấu hình `send_batch_size` như hard max | Batch vẫn quá lớn | Dùng `send_batch_max_size` |
| Nhầm count và bytes giữa công cụ | Payload/request size sai | Đọc đơn vị từng tham số |
| Batching nhiều tầng mà không đo | Latency cộng dồn khó thấy | Đo end-to-end, tối giản tầng |
| Dùng raw user ID làm batch metadata key | Memory/cardinality, rủi ro privacy | Dùng key tenant được auth/giới hạn |
| Async worker đọc MDC thread khác | Sai correlation ID | Snapshot context ở call site |
| Chỉ theo dõi số request HTTP gửi đi | Không biết số records/batch đã mất | Đo records, bytes, failures, drops |
| Dùng queue RAM cho audit bắt buộc | Crash có thể mất bằng chứng | Kênh bền vững/audit riêng |
| Bật debug exporter và dump batch | Lộ PII/token vào chính log debug | Redact, hạn chế debug và RBAC |

## 18. Checklist triển khai production

- [ ] Xác định các tầng batch: JVM, agent, Collector, exporter; biết event đi qua đâu.
- [ ] Chọn trigger theo count/bytes/time; không nhầm ngưỡng kích hoạt với max batch.
- [ ] Thiết lập queue/buffer có giới hạn và chính sách rõ khi đầy.
- [ ] Giới hạn export timeout, retry attempts/elapsed time và backoff/jitter.
- [ ] Chỉ coi record đã gửi theo đúng ACK contract; không gộp mốc enqueue với delivery.
- [ ] Có phương án xử lý ACK ambiguity, duplicates và ordering nếu quan trọng.
- [ ] Có shutdown flush/drain với deadline và metric pending/drop.
- [ ] Kiểm tra quyền riêng tư, TLS/auth, multi-tenancy, disk spool và retention.
- [ ] Dùng đúng config/phiên bản cho OTel Java, Collector và Alloy/Loki.
- [ ] Đo throughput, batch sizes, backlog, drop rate và end-to-end freshness.
- [ ] Test 429, 503, 413, auth error, network partition, crash/restart và receiver chậm.
- [ ] Với audit, thiết kế đường ghi có bảo đảm phù hợp, không dựa queue RAM.
- [ ] Không thay config batch chỉ vì một dòng log “sent” mà thiếu dữ liệu backend.
- [ ] Có runbook khi queue đầy, lỗi export, spool gần hết dung lượng hoặc log delay.

## 19. Bài tập thực hành

1. Chạy `BatchTransportDemo`. Giải thích vì sao `send_attempts=4` nhưng `delivered=5`, và vì sao `rejected=1` không nằm trong lô đã giao.
2. Đổi `maxBatch=2` và cấu hình `maxQueue` phù hợp. Dự đoán thứ tự/số batch trước khi chạy.
3. Thay `maxDelayMs=500`, mô phỏng event đến cách nhau ít hơn timeout và kiểm tra flush sớm.
4. Cho `DemoSender` fail **hai lần**. Thiết kế thêm retry trigger, deadline và bảo đảm không xóa queue khi chưa ACK.
5. Giả lập receiver đã nhận lô nhưng sender báo timeout; hãy giải thích vì sao retry có thể gây duplicate và cần event ID/dedup.
6. Đổi `maxQueue` nhỏ hơn tốc độ tạo log, thử drop-new và block. Đo ảnh hưởng đối với logic nghiệp vụ.
7. Thêm thống kê `pending_oldest_age_ms`, `batch_size_records` và `export_attempts_total` vào demo, rồi vẽ dashboard giả.
8. Đo kích thước encoded bytes cho 10 records ngắn và 10 records có stack trace dài. Vì sao count threshold không đủ ngăn 413?
9. Trong một ứng dụng dùng OTel Java SDK, thử `otel.blrp.max.export.batch.size` và `otel.blrp.schedule.delay`, xem logs thật đi qua bridge/exporter nào.
10. Dựng Collector test với `memory_limiter` → `batch` → exporter, kiểm tra tác dụng của `send_batch_size` so với `send_batch_max_size`.
11. Trong Alloy test, thay `batch_wait` và `batch_size`, đo request rate và độ trễ đến Loki; xác minh cả credentials và source `forward_to`.
12. Thử dừng JVM trước khi flush và so với shutdown có kiểm soát. Đánh giá điều gì có thể mất trong RAM và khi nào cần durable spool.
13. Thiết kế retry/backoff với `Retry-After` cho 429 và split batch khi 413 trong môi trường test, có counter failed/dropped.
14. Tạo canary log an toàn, đo emit-to-searchable p95 qua nhiều giờ; giải thích vì sao thành công của exporter chưa đảm bảo searchable ngay.

## 20. Ghi nhớ

- **Batch vận chuyển** gom nhiều log records thành một lần export nhằm giảm overhead và tăng throughput, đổi lại thêm độ trễ/queue/memory.
- Có thể kích hoạt gửi theo **size, bytes, thời gian hoặc flush**; thiết kế phải có giới hạn và deadline.
- **Async logging không tự đồng nghĩa batching**; retry/compression/durable buffering là các cơ chế riêng.
- `send_batch_size` của OpenTelemetry Collector là **trigger**, `send_batch_max_size` mới là giới hạn kích thước batch; cần kiểm tra từng phiên bản.
- Batching giảm số request, nhưng **không tự tạo at-least-once hay exactly-once**; timeout/ACK loss và retry có thể mất/trùng log.
- Cần backpressure/drop policy, retry với backoff/jitter, metrics queue/export/drop, shutdown drain và test failure injection.
- Java SDK, Collector và Alloy/Loki có tham số count/bytes/time khác nhau; không sao chép cấu hình thiếu đơn vị.
- Bảo mật payload ngay tại nguồn, bảo vệ transport/spool, phân quyền tenant và không dump batch khi lỗi.
- Đánh giá chất lượng bằng **records accepted/exported/searchable**, không chỉ số lần gọi logger hoặc số batch thành công.

### Tài liệu tham khảo

- OpenTelemetry — *Logs SDK Specification*, Batch LogRecordProcessor, ForceFlush, Shutdown: https://opentelemetry.io/docs/specs/otel/logs/sdk/
- OpenTelemetry Java — *Configure SDK*, các properties `otel.blrp.*`: https://opentelemetry.io/docs/languages/java/configuration/
- OpenTelemetry Collector — *Batch processor README* (`send_batch_size`, `send_batch_max_size`, `timeout`): https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor
- OpenTelemetry Collector — *Processor batch config*: https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/batchprocessor/config.go
- Grafana Alloy — `loki.write`, `batch_size`, `batch_wait` và metrics: https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/
- OWASP — *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
