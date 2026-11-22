# Thiết kế replay có giới hạn tốc độ và không lặp tác dụng phụ

## Mục tiêu

Replay là việc đọc lại các record Kafka đã được ghi trước đó để dựng lại projection, bổ sung dữ liệu, sửa lỗi xử lý hoặc phục hồi consumer. Replay có thể tạo tải lớn lên broker và hệ thống downstream. Nếu consumer phát lại event rồi thực hiện side effect như trừ tiền, gửi email hoặc tạo đơn hàng lần nữa, một thao tác nghiệp vụ có thể bị lặp dù Kafka chỉ đang đọc lại dữ liệu cũ.

Một quy trình replay an toàn cần xác định rõ phạm vi record, tốc độ đọc, cách lưu checkpoint, chính sách xử lý side effect và cách dừng/tiếp tục. Bài học này tập trung vào cách thiết kế replay có giới hạn tốc độ và bảo đảm việc đọc lại không tạo tác động nghiệp vụ trùng.

Sau bài học này, bạn có thể:

- Phân biệt replay với retry và consumer restart thông thường.
- Chọn replay bằng group riêng, reset offset group hiện tại hoặc topic replay tùy mục tiêu.
- Xác định phạm vi replay theo partition, offset hoặc timestamp.
- Thiết kế rate limit theo record/giây, byte/giây và năng lực downstream.
- Dùng bounded queue, worker pool, `pause()`/`resume()` để tạo backpressure mà vẫn tiếp tục poll.
- Ngăn side effect lặp bằng event ID, inbox/deduplication và idempotency key.
- Theo dõi tiến độ, checkpoint, lỗi và khả năng dừng/tiếp tục replay.
- Thực hiện replay có kiểm soát bằng Kafka CLI, Java consumer và Spring Kafka.

## 1. Replay là gì và khi nào cần dùng?

Replay là đọc lại một phần hoặc toàn bộ record đã tồn tại trong Kafka. Consumer có thể đọc lại bằng cách thay đổi offset, dùng một consumer group mới hoặc đọc từ một topic đã được sao chép. Kafka không tự biết lần đọc này là replay nghiệp vụ; với broker, đây vẫn là các lần fetch record bình thường.

Các tình huống thường gặp:

- Dựng lại read model/projection sau khi sửa bug trong consumer.
- Nạp dữ liệu lịch sử cho một service mới.
- Chạy lại một khoảng thời gian để bổ sung dữ liệu bị bỏ sót.
- Kiểm tra logic xử lý mới trên dữ liệu cũ.
- Phục hồi một consumer group sau khi xác định offset commit bị tiến quá sớm.
- Chạy lại dữ liệu từ dead-letter topic sau khi sửa lỗi.

Replay khác retry ở phạm vi và mục đích:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Retry | Thử lại một thao tác thất bại trong quá trình xử lý hiện tại | Consumer retry record do database tạm thời unavailable |
| Restart/resume | Consumer khởi động lại và tiếp tục từ committed offset | Pod restart, consumer đọc tiếp record kế tiếp |
| Replay | Chủ động đọc lại record đã tồn tại trong log | Dựng lại projection từ offset đầu hoặc một mốc thời gian |
| Reprocess từ DLT | Đọc lại record đã được chuyển sang dead-letter topic | Sửa dữ liệu lỗi rồi đưa lại vào luồng xử lý |

Replay có thể thực hiện hàng triệu record và đi qua nhiều ngày dữ liệu. Vì vậy cần một kế hoạch tải, phạm vi và tác động nghiệp vụ rõ ràng trước khi chạy.

## 2. Chọn chiến lược replay

Ba cách triển khai phổ biến là dùng group ID riêng, reset offset group hiện tại hoặc tạo luồng/topic replay riêng.

| Chiến lược | Cách hoạt động | Phù hợp khi | Rủi ro/chú ý |
|---|---|---|---|
| Consumer group riêng | Tạo group mới, đọc lại topic độc lập với production group | Backfill, dựng projection mới, kiểm tra logic | Có thể tạo side effect trùng nếu dùng chung đích ghi |
| Reset offset group hiện tại | Dừng consumer group, reset committed offset rồi chạy lại | Phục hồi chính consumer group đó | Làm thay đổi vị trí đọc production và có thể phát lại tác động nghiệp vụ |
| Replay topic/stream riêng | Chuyển record cần replay sang topic riêng hoặc pipeline riêng | Cần kiểm soát quyền, tốc độ, audit và routing | Phải giữ metadata nguồn và tránh tạo vòng lặp publish/consume |

### 2.1. Ưu tiên group riêng cho backfill độc lập

Ví dụ production đang dùng `orders-projection`. Muốn dựng lại projection từ đầu, tạo group mới như `orders-projection-replay-20261120`. Group replay có committed offset riêng, nên việc đọc lại không làm thay đổi offset của production group.

Hai group vẫn đọc cùng partition log vật lý của topic `orders`. Điều đó không nhân đôi dữ liệu trong Kafka, nhưng tạo thêm fetch traffic, network và tải xử lý ở broker. Nếu replay chạy cùng production, phải giới hạn tốc độ để không chiếm hết năng lực cluster.

Group riêng cũng không tự ngăn side effect trùng. Nếu production và replay cùng ghi vào bảng nghiệp vụ hoặc gọi cùng một API, cả hai có thể áp dụng cùng event. Hãy cô lập đích replay hoặc dùng idempotency/deduplication.

### 2.2. Reset group hiện tại khi cần khôi phục chính consumer đó

Reset offset của group production có thể hữu ích khi cần đọc lại một khoảng record trong chính group đó. Tuy nhiên, mọi consumer member của group phải dừng trước khi reset. Nếu reset khi consumer còn chạy, consumer có thể tiếp tục commit offset mới và ghi đè kết quả reset.

Quy trình an toàn gồm:

1. Thông báo cửa sổ bảo trì và dừng toàn bộ member của group.
2. Ghi lại committed offset hiện tại cho từng partition để có thể đối chiếu.
3. Chạy `--dry-run` và xác nhận offset đích.
4. Thực hiện reset.
5. Kiểm tra lại offset đã thay đổi.
6. Khởi động consumer và giám sát lag, side effect cùng lỗi xử lý.

Nếu mục tiêu là dựng một projection mới trong khi production vẫn hoạt động, group riêng thường dễ kiểm soát hơn reset group đang phục vụ production.

### 2.3. Replay topic riêng

Một pipeline có thể đọc topic nguồn, lọc phạm vi cần phát lại rồi publish sang `orders.replay`. Consumer replay đọc topic này với group riêng. Khi sao chép, nên giữ metadata nguồn như `originalTopic`, `originalPartition`, `originalOffset`, `originalTimestamp`, `eventId` và `replayRunId` trong header hoặc envelope.

Không publish record replay trở lại topic nguồn mà consumer đang đọc nếu không có điều kiện chặn vòng lặp. Không xóa dấu nguồn hoặc tạo `eventId` mới cho cùng một event chỉ vì nó được đưa sang replay topic.

## 3. Xác định phạm vi replay

Replay phải có điểm bắt đầu và điểm kết thúc rõ ràng. Kafka lưu offset theo từng partition, vì vậy không có một offset toàn cục cho cả topic.

Các kiểu xác định phạm vi:

- **Từ đầu log còn giữ:** bắt đầu ở earliest offset hiện còn trong partition.
- **Từ một offset cụ thể:** dùng khi đã biết vị trí cần đọc lại của một partition.
- **Từ timestamp:** tìm offset đầu tiên có timestamp phù hợp trong từng partition.
- **Theo khoảng thời gian:** chọn timestamp bắt đầu và kết thúc, rồi xác định offset tương ứng ở mỗi partition.
- **Theo danh sách key/event ID:** consumer đọc trong khoảng offset hợp lý rồi lọc theo dữ liệu nghiệp vụ; lọc theo key không tự động bỏ qua các offset khác trong log.

| Phạm vi | Cách chọn | Điều cần nhớ |
|---|---|---|
| Toàn topic | Tất cả partition từ earliest | Chỉ đọc được dữ liệu còn trong retention/compaction |
| Một partition | Partition ID và offset/timestamp | Phải giữ đúng partition khi đối chiếu checkpoint |
| Từ thời điểm | Timestamp theo từng partition | Timestamp không phải thứ tự toàn cục và có thể không chính xác tuyệt đối |
| Một đoạn offset | Start/end offset cho từng partition | Offset cuối thường được xem là exclusive khi thiết kế vòng lặp đọc |
| Một tập event ID | Lọc payload hoặc index phụ trợ | Có thể phải scan nhiều record; cần ước lượng tải |

### 3.1. Retention và log compaction giới hạn replay

Replay chỉ có thể đọc dữ liệu Kafka còn lưu. Nếu record đã bị xóa do `retention.ms`/`retention.bytes`, consumer không thể tua về record đó bằng cách reset offset. Với topic compacted, Kafka có thể giữ lại giá trị mới nhất cho mỗi key và loại bỏ các phiên bản cũ hơn. Topic compacted vì vậy không nhất thiết chứa đầy đủ mọi event lịch sử.

Nếu cần replay dài hạn, hãy thiết kế archive hoặc event store phù hợp, kiểm tra retention trước khi bắt đầu và lưu checkpoint theo từng partition. `auto.offset.reset=earliest` có nghĩa bắt đầu từ earliest offset còn tồn tại, không phục hồi record đã bị xóa.

### 3.2. Timestamp và offset

Kafka hỗ trợ tìm offset theo timestamp cho từng partition. Timestamp có thể là `CreateTime` do producer cung cấp hoặc `LogAppendTime` do broker gán tùy cấu hình topic. Không nên dùng timestamp như một thứ tự toàn cục giữa partition, và không nên giả định mọi partition có record đúng tại mốc thời gian được yêu cầu.

Khi replay từ timestamp, ghi lại offset thực tế tìm được cho từng partition. Đối chiếu với `beginningOffsets()` và `endOffsets()` để biết phạm vi còn khả dụng.

## 4. Tách replay khỏi tác động nghiệp vụ

Đọc lại một event là thao tác kỹ thuật. Áp dụng event vào hệ thống đích là thao tác nghiệp vụ. Hai việc này cần được thiết kế tách biệt.

Ví dụ `PaymentCaptured` đã được production consumer xử lý và ghi nhận thanh toán. Nếu replay event này qua handler cũ, ứng dụng có thể gọi cổng thanh toán hoặc cộng doanh thu lần nữa. Đây là lỗi thiết kế nếu replay được coi như một lệnh thực hiện lại hành động.

Trước khi chạy replay, phân loại tác động của consumer:

| Loại xử lý | Ví dụ | Chính sách replay phù hợp |
|---|---|---|
| Dựng projection có thể thay thế | Bảng thống kê, search index, cache | Dùng bảng/index replay riêng rồi swap hoặc rebuild có kiểm soát |
| Cập nhật trạng thái có thể deduplicate | Cập nhật đơn hàng từ event ID | Lưu event ID đã xử lý nguyên tử với cập nhật trạng thái |
| Gửi thông báo | Email, SMS, push notification | Chặn gửi trùng hoặc chạy replay ở chế độ không gửi thông báo |
| Thao tác tài chính/không thể đảo ngược | Capture/refund, chuyển tiền, trừ tồn kho | Không gọi lại hành động; đối soát hoặc chỉ dựng projection từ sự thật đã có |
| Gọi API bên ngoài | Tạo ticket, tạo shipment | Dùng idempotency key của hệ thống đích hoặc chế độ dry-run |

Một event mô tả sự thật đã xảy ra; replay event không có nghĩa là phát lại command. Nếu consumer thực hiện command hoặc side effect không idempotent, phải bổ sung ranh giới bảo vệ trước khi replay.

## 5. Idempotency và deduplication bằng event ID

Mỗi event nghiệp vụ nên có `eventId` ổn định. Khi cùng một event được đọc lại, producer/replay pipeline giữ nguyên ID đó. Consumer lưu dấu event đã xử lý để chỉ áp dụng side effect một lần.

### 5.1. Bảng inbox/processed events

Ví dụ bảng trong PostgreSQL:

```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Consumer thực hiện insert event ID và cập nhật projection trong cùng database transaction:

```sql
BEGIN;

INSERT INTO processed_events (event_id, event_type)
VALUES (:event_id, :event_type)
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ khi INSERT thêm được một dòng mới mới áp dụng projection.
-- Nếu event_id đã tồn tại, bỏ qua side effect của event này.

COMMIT;
```

Trong ứng dụng thực tế, kiểm tra số dòng được insert hoặc dùng `RETURNING` để biết event mới hay đã xử lý. Chỉ áp dụng cập nhật projection khi insert thành công. Cả thao tác deduplication và cập nhật projection phải nằm trong cùng transaction database để tránh trường hợp lưu dấu thành công nhưng cập nhật nghiệp vụ thất bại, hoặc ngược lại.

### 5.2. Ví dụ xử lý với JDBC

```java
public void applyOnce(EventEnvelope<OrderCreated> event) {
    transactionTemplate.executeWithoutResult(status -> {
        int inserted = jdbcTemplate.update("""
                INSERT INTO processed_events (event_id, event_type)
                VALUES (?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                event.eventId(), event.eventType());

        if (inserted == 0) {
            // Event đã được áp dụng; replay không tạo side effect lần nữa.
            return;
        }

        orderProjection.apply(event.data());
    });
}
```

Ví dụ giả định database hỗ trợ `ON CONFLICT DO NOTHING` như PostgreSQL và `transactionTemplate` dùng cùng transaction manager với `jdbcTemplate`. Với hệ quản trị khác, thay cú pháp insert-if-absent tương ứng. Không dùng một transaction manager độc lập cho hai thao tác nếu muốn tính nguyên tử.

### 5.3. Side effect bên ngoài database

Nếu consumer gọi API ngoài, transaction database không thể nguyên tử với hệ thống bên ngoài. Hãy dùng idempotency key ổn định, thường là `eventId`, nếu API đích hỗ trợ. Nếu không có idempotency ở phía đích, cần outbox/command state machine, đối soát hoặc quy trình xử lý thủ công cho các trường hợp kết quả không xác định.

Không xóa bảng `processed_events` chỉ để chạy replay lại toàn bộ. Nếu cần rebuild projection, dùng namespace/bảng mới cho replay rồi xác minh và chuyển traffic; giữ bảng dedup production theo retention phù hợp.

## 6. Chế độ replay và routing side effect

Một consumer có thể nhận biết replay qua cấu hình deployment, group ID, header hoặc metadata của replay run. Không dựa duy nhất vào tên group để quyết định an toàn; hãy dùng cấu hình rõ ràng và kiểm soát quyền triển khai.

Ví dụ envelope/header:

```json
{
  "eventId": "8b8a4d9f-6d9a-4d8b-9e75-3c8a5c7e4f10",
  "eventType": "OrderCreated",
  "aggregateId": "ORD-1001",
  "occurredAt": "2026-11-20T08:00:00Z",
  "replay": {
    "runId": "orders-backfill-20261120-01",
    "originalTopic": "orders.events",
    "originalPartition": 2,
    "originalOffset": 48120
  },
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-01",
    "totalAmount": 125000
  }
}
```

Thông tin `replay` có thể được đặt trong Kafka headers thay vì payload nếu schema nghiệp vụ không nên chứa metadata vận hành. `eventId` và dữ liệu sự kiện gốc phải giữ nguyên; `runId` chỉ định danh lần replay.

Một số chế độ routing hữu ích:

- **Projection rebuild:** ghi vào projection mới, không gửi email hoặc gọi API nghiệp vụ.
- **Validation/dry-run:** chạy logic và ghi kết quả so sánh, không commit side effect.
- **Repair:** chỉ cập nhật các bản ghi đã xác định sai, có idempotency key và audit.
- **Re-drive DLT:** chạy lại record lỗi sau khi sửa nguyên nhân, vẫn giữ event ID gốc.

Nên có cờ cấu hình riêng cho side effect nguy hiểm và mặc định tắt trong replay. Không cho replay consumer dùng chung credential có quyền capture payment, gửi tiền hoặc thực hiện thao tác không thể đảo ngược nếu nhiệm vụ chỉ là dựng projection.

## 7. Giới hạn tốc độ replay

Replay có thể đọc nhanh hơn production consumer vì không phải chờ dữ liệu mới. Nếu chạy không giới hạn, nó có thể chiếm network, disk read, CPU broker, database connection pool hoặc API quota.

Hãy đặt giới hạn theo nhiều đơn vị:

- **Records/second:** phù hợp khi record có kích thước tương đối đồng đều.
- **Bytes/second:** bảo vệ network và hệ thống khi payload lớn/không đồng đều.
- **Concurrent in-flight:** giới hạn số tác vụ đang chờ xử lý ở worker/downstream.
- **Per-partition rate:** tránh một partition hoặc key nóng chiếm toàn bộ quota.
- **Downstream budget:** giữ số request/transaction dưới năng lực database/API.

Ví dụ replay mục tiêu 200 record/giây nhưng mỗi record có kích thước khác nhau. Nếu chỉ giới hạn record/s, một đợt payload 2 MB có thể tạo băng thông lớn hơn nhiều so với payload 2 KB. Cần giới hạn cả byte/s hoặc đo kích thước batch.

### 7.1. Token bucket

Token bucket là cách phổ biến để giới hạn tốc độ. Bucket có capacity `B`, refill `R` token mỗi giây. Mỗi record tiêu thụ một token; record lớn có thể tiêu thụ số token tỷ lệ với byte size. Bucket cho phép burst ngắn tối đa theo capacity, nhưng duy trì tốc độ trung bình gần `R`.

\[
tokens(t) = \min(B, tokens(t_0) + R \times (t-t_0))
\]

Ví dụ capacity 40 token, refill 200 token/giây. Replay có thể burst tối đa 40 record nếu bucket đầy, sau đó duy trì trung bình khoảng 200 record/giây.

Nếu có nhiều worker hoặc nhiều pod replay, limiter trong từng process không giới hạn tổng tốc độ toàn cluster. Ví dụ bốn pod, mỗi pod giới hạn 200 record/giây có thể tạo tổng 800 record/giây. Muốn có quota toàn cục, cần phân chia quota cho từng instance hoặc dùng rate limiter phân tán/điều phối tập trung.

### 7.2. Backpressure bằng bounded queue

Không poll vô hạn rồi đẩy mọi record vào queue. Dùng bounded queue để giới hạn memory. Khi queue gần đầy, poll thread pause các partition liên quan. Khi worker xử lý xong và queue xuống dưới ngưỡng resume, poll thread tiếp tục fetch.

`pause()` không rời group và không thay đổi assignment. Consumer vẫn phải tiếp tục gọi `poll()` để xử lý group protocol, heartbeat/rebalance và sự kiện khác. Không block poll thread bằng `Thread.sleep()` dài hoặc chờ token vô hạn.

Nếu worker pool dùng rate limiter, có thể để worker chờ token trong giới hạn queue; poll thread vẫn tiếp tục poll. Cần giới hạn số tác vụ in-flight và xử lý kết quả hoàn tất theo từng partition trước khi commit offset.

### 7.3. Giới hạn thời gian và tốc độ đồng thời

Replay nên có cả rate limit và deadline vận hành. Rate limit điều khiển tốc độ; deadline điều khiển khoảng thời gian cho phép chạy. Nếu downstream latency tăng hoặc error rate vượt ngưỡng, giảm quota hoặc pause replay. Khi production lag hoặc latency vượt SLO, replay nên nhường tài nguyên.

## 8. Java Kafka Consumer: replay group riêng và giới hạn tốc độ

Ví dụ dưới đây minh họa consumer chạy với group ID riêng và dùng Guava `RateLimiter` trong worker. Poll thread duy nhất sở hữu `KafkaConsumer`; worker không gọi API consumer. Phần ví dụ tập trung vào ranh giới kiến trúc, còn completion tracker, bounded dispatch và transaction dedup phải được hiện thực hóa đầy đủ theo ứng dụng.

```java
import com.google.common.util.concurrent.RateLimiter;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-replay-20261120-01");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
RateLimiter rateLimiter = RateLimiter.create(200.0); // record/giây toàn process
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        4, 4, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(400));

consumer.subscribe(List.of("orders.events"));

try {
    while (running) { // running do lifecycle ứng dụng quản lý
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(100));

        for (ConsumerRecord<String, String> record : records) {
            TopicPartition tp = new TopicPartition(
                    record.topic(), record.partition());
            registerDispatched(tp, record.offset());

            try {
                workers.execute(() -> {
                    try {
                        rateLimiter.acquire(); // Chờ trong worker, không block poll thread
                        ReplayEvent event = deserialize(record.value());
                        processedEventService.applyOnce(event); // Inbox/dedup transaction
                        completed.offer(new Completed(tp, record.offset(), null));
                    } catch (Exception ex) {
                        completed.offer(new Completed(tp, record.offset(), ex));
                    }
                });
            } catch (RejectedExecutionException full) {
                // Production implementation phải giữ record trong pending buffer
                // có giới hạn và pause partition; không được bỏ record.
                pendingDispatch.add(new PendingRecord(tp, record));
                consumer.pause(Set.of(tp));
            }
        }

        drainCompletedAndAdvanceContiguousOffsets(completed);
        dispatchPendingWhenCapacityAvailable(consumer, workers, pendingDispatch);
        commitOnlyContiguousCompletedOffsets(consumer);

        resumePartitionsBelowBacklogThreshold(consumer, workers, pendingDispatch);
    }
} finally {
    // Ngừng dispatch, drain task có giới hạn, commit prefix đã hoàn tất,
    // rồi đóng consumer trên chính poll thread.
    stopDispatchAndDrainWorkers(workers);
    commitOnlyContiguousCompletedOffsets(consumer);
    consumer.close(Duration.ofSeconds(30));
    workers.shutdown();
}
```

Các kiểu `ReplayEvent`, `Completed`, `PendingRecord` và hàm `registerDispatched`, `drainCompletedAndAdvanceContiguousOffsets`, `dispatchPendingWhenCapacityAvailable`, `commitOnlyContiguousCompletedOffsets`, `resumePartitionsBelowBacklogThreshold`, `processedEventService` là phần logic minh họa. Cần lưu ý:

- `pendingDispatch` phải là queue có giới hạn; khi gần đầy, pause partition để ngừng nhận thêm record.
- Nếu poll đã trả về một batch lớn hơn số slot worker còn trống, giữ toàn bộ record chưa dispatch trong pending queue. Không bỏ record và không commit vượt qua record đó.
- `RateLimiter` ở trên giới hạn record/giây trong một JVM. Nếu cần giới hạn byte/s, tiêu thụ token theo kích thước payload hoặc dùng limiter thứ hai.
- Chỉ commit offset của prefix record đã xử lý thành công theo từng partition. Không commit offset lớn nhất vừa hoàn tất nếu record trước đó còn pending.
- Nếu record thất bại, giữ trạng thái chưa hoàn tất; áp dụng retry/DLT hoặc dừng partition theo chính sách. Không đánh dấu complete chỉ để replay tiếp.
- Nếu cần giữ ordering nghiệp vụ trong partition, dùng serial executor theo partition hoặc xử lý tuần tự trong từng partition. Completion tracker chỉ bảo vệ commit offset, không tự giữ thứ tự side effect.
- Khi rebalance revoke partition, dừng dispatch partition đó, drain task có giới hạn và chỉ commit khi còn quyền sở hữu. Worker hoàn tất muộn phải được bảo vệ bằng idempotency.

Trong ứng dụng production, có thể dùng worker pool riêng cho replay, nhưng poll thread vẫn phải duy trì poll thường xuyên để không vượt `max.poll.interval.ms`. Không đặt `rateLimiter.acquire()` trên poll thread nếu thời gian chờ có thể kéo dài.

## 9. Spring Kafka cho replay

Với Spring Kafka, tạo deployment replay riêng và override `group-id`. Giữ `enable-auto-commit=false` để container quản lý commit theo acknowledgment mode đã chọn.

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-replay-20261120-01
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
    listener:
      concurrency: 2
      ack-mode: record
```

Với listener đơn giản, có thể dùng idempotent service để ngăn side effect lặp:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-replay-20261120-01"
)
public void replay(ConsumerRecord<String, String> record) {
    ReplayEvent event = objectMapper.readValue(
            record.value(), ReplayEvent.class);
    replayService.applyProjectionOnce(event);
}
```

Nếu cần rate limit đơn giản, có thể giới hạn tốc độ trong tầng service, nhưng không để listener thread block quá lâu đến mức vượt `max.poll.interval.ms`. Với replay tải lớn, hãy dùng cơ chế pause/resume của listener container, bounded worker queue và acknowledgment/async processing được Spring Kafka hỗ trợ ở đúng phiên bản. Cần kiểm tra semantics của `AckMode`, `asyncAcks`, retry và rebalance trước khi chuyển listener sang xử lý bất đồng bộ.

Không thay group ID production chỉ để chạy replay. Giữ group replay riêng, ghi `replayRunId` trong log/metrics và đặt quyền truy cập riêng cho deployment replay.

## 10. Dùng Kafka CLI để chuẩn bị replay

Các lệnh dưới đây dùng `localhost:9092` làm bootstrap server. Thay bằng địa chỉ cluster lab. Tên option có thể khác nhẹ theo phiên bản Kafka CLI; hãy dùng công cụ cùng phiên bản với cluster.

### 10.1. Xem committed offset hiện tại

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group orders-projection
```

Lưu lại `CURRENT-OFFSET`, `LOG-END-OFFSET` và lag theo từng partition trước khi replay.

### 10.2. Tạo group replay riêng và đọc từ earliest

Với group ID mới chưa có committed offset, chỉ cần khởi động consumer bằng `group.id` riêng và `auto.offset.reset=earliest`; consumer bắt đầu từ earliest offset còn được giữ trong mỗi partition, không cần reset trước khi group có committed offset. Các lệnh reset bên dưới dành cho replay group đã từng chạy và có committed offset. Dừng tất cả member của group trước khi reset:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group orders-replay-20261120-01 \
  --topic orders.events \
  --reset-offsets --to-earliest --dry-run
```

Nếu kết quả đúng, thực hiện:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group orders-replay-20261120-01 \
  --topic orders.events \
  --reset-offsets --to-earliest --execute
```

Sau đó khởi động consumer với đúng group ID này và `enable.auto.commit=false` hoặc commit theo chính sách replay đã thiết kế.

### 10.3. Replay từ timestamp

Dry run để kiểm tra offset được chọn cho mỗi partition:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group orders-replay-20261120-01 \
  --topic orders.events \
  --reset-offsets --to-datetime 2026-11-01T00:00:00.000 \
  --dry-run
```

Nếu phạm vi đúng, thay `--dry-run` bằng `--execute`. Timestamp phải được diễn giải theo định dạng/timezone mà CLI phiên bản đang dùng hỗ trợ. Đối chiếu offset kết quả với beginning/end offset trước khi chạy.

### 10.4. Replay từ offset cụ thể

Có thể reset một partition cụ thể về offset đã xác định bằng cú pháp `--topic topic:partition` được CLI hỗ trợ:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group orders-replay-20261120-01 \
  --topic orders.events:2 \
  --reset-offsets --to-offset 48120 --dry-run
```

Chỉ thực hiện `--execute` sau khi xác minh partition, offset nằm trong phạm vi log còn lưu và event tương ứng đúng với mục tiêu replay.

### 10.5. Reset group đang chạy

Nếu cần reset `orders-projection` hiện tại, trước tiên dừng tất cả consumer member. Lưu committed offset cũ, chạy dry run, sau đó mới execute. Không reset group production đang hoạt động. Khi khởi động lại, consumer sẽ đọc lại record theo offset mới và có thể tạo side effect lặp nếu không có idempotency.

## 11. Checkpoint, dừng và tiếp tục replay

Replay dài có thể bị dừng do deploy, sự cố broker hoặc downstream. Để tiếp tục đúng vị trí, cần lưu checkpoint theo từng partition.

Checkpoint tối thiểu nên gồm:

| Trường | Ý nghĩa |
|---|---|
| `replayRunId` | ID duy nhất của lần replay |
| `sourceTopic` | Topic nguồn |
| `partition` | Partition đang đọc |
| `startOffset` | Offset bắt đầu đã chọn |
| `targetEndOffset` | Giới hạn kết thúc dự kiến (exclusive) |
| `lastContiguousCompletedOffset` | Offset cuối cùng của prefix record đã xử lý thành công |
| `committedNextOffset` | Vị trí tiếp tục đọc sau checkpoint |
| `status` | Pending, running, paused, completed hoặc failed |
| `updatedAt` | Thời điểm cập nhật checkpoint |

Không checkpoint offset lớn nhất vừa hoàn tất nếu có record trước đó chưa xong. Khi có worker song song, phải track contiguous completion theo từng partition.

Khi dừng replay:

1. Ngừng dispatch record mới và pause partition.
2. Cho worker hoàn tất các tác vụ đã nhận trong thời gian giới hạn.
3. Commit/checkpoint chỉ phần đã hoàn tất liên tục.
4. Lưu trạng thái replay run và lỗi còn lại.
5. Đóng consumer và worker pool đúng lifecycle.

Khi tiếp tục, dùng cùng `replayRunId` hoặc một run mới có liên kết tới run trước, kiểm tra checkpoint và dedup store trước khi tiếp tục. Nếu không chắc một side effect đã hoàn tất hay chưa, dựa vào event ID/idempotency key để đối soát.

## 12. Theo dõi replay và bảo vệ production

Replay cần dashboard riêng để phân biệt tải backfill với traffic production.

| Metric | Mục đích |
|---|---|
| Replay records/sec | Xác nhận tốc độ đọc thực tế |
| Replay bytes/sec | Theo dõi băng thông và kích thước payload |
| Replay lag / remaining records | Ước lượng tiến độ và thời gian hoàn tất |
| In-flight task count | Kiểm soát số tác vụ đang chờ |
| Worker queue depth | Phát hiện downstream chậm và backpressure |
| Processing latency | Theo dõi thời gian xử lý record |
| Deduplicated event count | Đo số event đã được áp dụng trước đó |
| Side-effect error rate | Phát hiện lỗi API/database |
| Retry/DLT count | Theo dõi record không xử lý được |
| Production consumer lag | Đảm bảo replay không làm production tụt lại |
| Broker request latency/network/disk | Phát hiện replay gây tải lên cluster |

Đặt các ngưỡng dừng hoặc giảm tốc độ:

- Production consumer lag tăng liên tục hoặc oldest record age vượt SLO.
- Database connection pool gần bão hòa hoặc query latency vượt ngưỡng.
- API downstream trả 429/5xx hoặc rate limit gần chạm.
- Broker request latency, network hoặc disk utilization tăng bất thường.
- Replay error rate hoặc DLT count tăng nhanh.
- Worker queue đạt ngưỡng cao trong thời gian dài.

Replay nên có nút pause/resume hoặc cơ chế điều chỉnh quota khi vận hành. Không để job replay chạy vô hạn mà không có deadline, owner và tiêu chí hoàn tất.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Replay làm production lag tăng | Replay dùng hết broker/network/downstream capacity | Giảm records/s và bytes/s, chạy ngoài giờ cao điểm hoặc tách hạ tầng |
| Email/đơn hàng/thanh toán bị lặp | Replay gọi lại side effect không idempotent | Deduplicate theo event ID, dùng idempotency key hoặc tắt side effect |
| Reset offset không có tác dụng | Consumer group vẫn đang hoạt động và tiếp tục commit | Dừng toàn bộ member trước reset |
| Replay không đọc được dữ liệu rất cũ | Record đã hết retention hoặc bị compaction | Kiểm tra beginning offset; dùng archive nếu có |
| Một partition replay chậm hơn hẳn | Key skew, record lớn hoặc downstream xử lý không đều | Theo dõi per-partition rate, chia quota và kiểm tra payload |
| Worker queue tăng liên tục | Poll nhanh hơn xử lý, không có backpressure | Dùng bounded queue, pause/resume và giới hạn in-flight |
| Offset checkpoint nhảy qua record chưa xong | Commit offset lớn nhất hoàn tất thay vì contiguous prefix | Track completion theo từng partition |
| Replay tạo vòng lặp vô hạn | Consumer đọc topic rồi publish lại vào chính topic nguồn | Dùng replay topic riêng và giữ metadata nguồn |
| Replay chạy lại nhưng bỏ sót record | Checkpoint ghi sai partition/offset hoặc reset nhầm phạm vi | Lưu checkpoint theo topic-partition và xác minh dry run |
| Nhiều pod vượt quota dự kiến | Mỗi pod áp dụng rate limiter cục bộ với cùng quota | Chia quota hoặc dùng limiter toàn cục |

## 14. Checklist trước khi chạy replay

- [ ] Có mục tiêu replay rõ ràng: rebuild, backfill, repair hay re-drive DLT.
- [ ] Đã xác định topic, partition, start offset/timestamp và end boundary.
- [ ] Đã kiểm tra retention, compaction và beginning/end offset.
- [ ] Đã chọn group replay riêng hoặc có kế hoạch dừng group hiện tại nếu reset.
- [ ] Đã giữ nguyên event ID và metadata nguồn.
- [ ] Đã phân loại side effect và tắt/điều hướng các hành động không an toàn.
- [ ] Có inbox/deduplication hoặc idempotency key ở hệ thống đích.
- [ ] Có giới hạn records/s, bytes/s, concurrency và queue depth.
- [ ] Poll thread tiếp tục poll; pause/resume được gọi từ đúng owner thread.
- [ ] Commit/checkpoint theo contiguous completed offset của từng partition.
- [ ] Có cơ chế pause, resume, shutdown và tiếp tục replay.
- [ ] Có metric riêng cho replay và production, cùng ngưỡng bảo vệ downstream.
- [ ] Có người chịu trách nhiệm, deadline và tiêu chí xác nhận hoàn tất.

## 15. Câu hỏi tự kiểm tra

1. Replay khác retry ở phạm vi và mục đích nào?
2. Vì sao group riêng không tự ngăn side effect bị lặp?
3. Khi nào nên dùng group riêng và khi nào reset offset group hiện tại?
4. Vì sao phải dừng toàn bộ member trước khi reset offset của group đang hoạt động?
5. `auto.offset.reset=earliest` có đọc lại record đã bị retention xóa không?
6. Vì sao topic compacted có thể không chứa đầy đủ lịch sử để replay event sourcing?
7. Token bucket giới hạn tốc độ trung bình và burst như thế nào?
8. Vì sao rate limiter cục bộ trên từng pod không tạo quota toàn cluster?
9. Vì sao không nên block poll thread bằng `sleep()` hoặc chờ token vô hạn?
10. Làm thế nào lưu event ID và cập nhật projection trong cùng transaction để tránh side effect trùng?
11. Vì sao completion tracker phải commit contiguous prefix theo từng partition?
12. Những metric nào cho biết replay đang ảnh hưởng tới production hoặc downstream?

## Tài liệu tham khảo

- [Apache Kafka — Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs): `auto.offset.reset`, `enable.auto.commit`, `max.poll.records` và consumer settings.
- [Apache Kafka — Consumer API](https://kafka.apache.org/documentation/#consumerapi): `seek`, `beginningOffsets`, `endOffsets`, `offsetsForTimes`, `pause`, `resume` và commit.
- [Apache Kafka — Consumer Group CLI](https://kafka.apache.org/documentation/#basic_ops_consumer_group): mô tả group, reset offset và các tùy chọn dry-run/execute.
- [Apache Kafka — Log Compaction](https://kafka.apache.org/documentation/#compaction): retention, compacted topic và giới hạn lưu trữ lịch sử.
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): concurrency, acknowledgment, pause/resume và lifecycle.

> Replay an toàn không chỉ là tua offset về trước. Hãy giới hạn tải, giữ checkpoint theo partition, bảo vệ side effect bằng idempotency và quan sát production trong suốt quá trình chạy.
