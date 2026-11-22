# Bài tập xử lý incident tổng hợp trong Spring Kafka Reliability Operations

## 1. Mục tiêu của bài thực hành

Một Kafka consumer có thể vẫn ở trạng thái `RUNNING`, pod Kubernetes vẫn `Ready` và các offset vẫn được commit, nhưng hệ thống nghiệp vụ đang mất tiến độ: record lỗi bị đẩy hàng loạt vào Dead Letter Topic (DLT), dữ liệu ở database chưa được cập nhật, một số partition bị chuyển quyền liên tục, và nhóm vận hành chỉ nhận được những cảnh báo rời rạc.

Trong production, incident kiểu này hiếm khi chỉ có một nguyên nhân hoặc một metric rõ ràng. Cần ghép nhiều bằng chứng để hiểu **đang xảy ra gì**, **những sự kiện nào bị ảnh hưởng**, **điều gì có thể xử lý ngay**, và **khi nào có thể tuyên bố đã phục hồi**.

Bài **“Bài tập xử lý incident tổng hợp”** thuộc nhóm **Thực hành vận hành** của module **Spring Kafka Reliability Operations**. Đây là một bài tập mô phỏng từ đầu đến cuối dành cho developer, SRE, người trực on-call và người thiết kế hệ thống sự kiện.

Sau khi hoàn thành, người học có thể:

1. Nhận diện tình huống Kafka incident qua lag, error rate, DLT, rebalance, database metrics và kết quả nghiệp vụ.
2. Dựng timeline sự cố và phân biệt **triệu chứng**, **nguyên nhân trực tiếp**, **nguyên nhân gốc** và **hậu quả**.
3. Đưa ra giả thuyết, kiểm tra bằng chứng trước khi thay đổi cấu hình hoặc reset offset.
4. Chọn cách giảm thiểu an toàn khi canary consumer lỗi, database quá tải và retry policy tạo DLT storm.
5. Kiểm tra committed offset, partition ownership và khả năng replay sau crash/rebalance.
6. Đối soát các event đã xử lý, bị DLT, duplicate delivery và side effect trong database.
7. Lập kế hoạch replay DLT có phê duyệt, idempotency và kiểm tra kết quả sau replay.
8. Viết báo cáo incident với mốc thời gian, đánh giá tác động, action items và kiểm thử hồi quy.

**Mọi hệ thống, log, metric, timestamp và số liệu trong bài đều là dữ liệu mô phỏng.** Không có incident production thực nào được xác nhận. Các lệnh thay đổi trạng thái chỉ được thực hiện trong môi trường lab/staging thuộc quyền kiểm soát; trên production phải tuân thủ quyền hạn và quy trình thay đổi của tổ chức.

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka, PostgreSQL, Kubernetes và JUnit 5. Cú pháp và option thực tế cần được điều chỉnh theo phiên bản client, broker và công cụ đang dùng.

## 2. Tổng quan tình huống incident

Hệ thống thương mại điện tử tiêu thụ sự kiện từ topic `orders.events` để cập nhật trạng thái đơn hàng vào bảng `order_projection`.

Kiến trúc mô phỏng:

```text
                   Order Service
                        |
                        v
               Kafka topic orders.events
                  4 partitions (P0-P3)
                        |
                        v
            Group: order-projection
               /               \
        Stable consumer      Canary consumer
        version 1.8.0        version 1.9.0
        2 pods, 1 thread     1 pod, 1 thread
               \               /
                \             /
                 v           v
                 PostgreSQL cluster
                     |
                     v
              order_projection
                     |
                     v
             API/dashboard đơn hàng

           Các record không xử lý được
                        |
                        v
               orders.events.DLT
                        |
                        v
                 DLT audit/replay
```

Ở thời điểm bình thường:

- Topic có 4 partition và lượng sự kiện trung bình khoảng 100 record/giây.
- Hai pod stable chia nhau công việc trong cùng consumer group.
- Consumer dùng `enable.auto.commit=false` và container `AckMode.RECORD`.
- Handler ghi database bằng JDBC transaction, có marker chống duplicate theo `eventId`.
- `DefaultErrorHandler` thử lại các lỗi transient rồi publish DLT sau khi cạn retry.
- Dashboard theo dõi lag, lỗi handler, số record đi DLT, thời gian xử lý và database pool.
- Có cơ chế triển khai canary cùng group để thử version 1.9.0.

Sự cố mô phỏng xảy ra ngay sau khi đưa canary lên production. Trong cùng khoảng thời gian, schema của event thay đổi và database bắt đầu thiếu kết nối. Một số bản ghi không được xử lý; khi lag tăng, các pod có rebalance và có khả năng nhận lại record đã xử lý trước đó.

### Mục tiêu khôi phục

Trong lab, coi các mục tiêu sau là ràng buộc:

| Ràng buộc | Ý nghĩa |
| --- | --- |
| Không mất âm thầm event | Mọi event phải có outcome: đã xử lý, đang chờ, hoặc được cách ly có truy vết |
| Không nhân đôi side effect | Một `eventId` hợp lệ không làm thay đổi dữ liệu nghiệp vụ nhiều lần ngoài quy tắc |
| Không reset group offset tùy tiện | Offset chỉ thay đổi theo quy trình kiểm soát và đánh giá dữ liệu đích |
| DLT có chủ sở hữu | Mọi case DLT cần điều tra và resolution |
| Có thể rollback | Có version stable được kiểm chứng và đường rollback không xóa lịch sử |
| Có bằng chứng phục hồi | Consumer progress, DLT backlog và business reconciliation đạt điều kiện đã định |
| Không che giấu lỗi | Một consumer xanh nhưng đang bỏ record vào DLT không được coi là phục hồi toàn diện |

Đây là tiêu chuẩn đánh giá trong bài, không phải SLA áp dụng mặc định cho mọi doanh nghiệp.

## 3. Phân biệt kỹ thuật của các tín hiệu

Trước khi điều tra, cần thống nhất ý nghĩa các khái niệm thường thấy trên dashboard.

| Tín hiệu | Điều nó cho biết | Điều không thể tự kết luận |
| --- | --- | --- |
| Consumer lag | Chênh lệch giữa vị trí cuối và tiến độ tiêu thụ/commit theo metric | Không trực tiếp bằng số event nghiệp vụ thất bại |
| Committed offset | Vị trí tiếp tục của consumer group cho một partition | Không chứng minh side effect ở DB chính xác |
| Retry attempts | Một record/operation bị gọi lại theo policy | Không bằng số event duy nhất lỗi |
| DLT publish count | Record đã chuyển sang DLT theo policy | Không chứng minh event đã được xử lý nghiệp vụ |
| Rebalance count | Group membership/assignment thay đổi | Không tự chứng minh mất message |
| Handler exception | Có lỗi trong một lần xử lý | Không tự chứng minh job/consumer cuối cùng thất bại |
| Pod readiness | Ứng dụng đáp ứng tiêu chí health đã định nghĩa | Không đảm bảo consumer sở hữu partition hoặc đang tiến triển |
| DB connection pool pending | Có request đang đợi connection | Không tự chứng minh nguyên nhân là Kafka |
| Duplicate delivery | Một Kafka record/event có thể được xử lý lại | Không đồng nghĩa đã ghi duplicate business result |
| Business reconciliation mismatch | Đầu ra khác kết quả kỳ vọng | Cần điều tra offset, validation, DLT, nguồn và DB để giải thích |

**Đặc biệt:** lag có thể giảm vì record lỗi được publish thành công tới DLT và source offset tiếp tục tiến. Nếu dashboard chỉ xem lag, đội vận hành có thể tuyên bố hồi phục trong khi hàng nghìn đơn hàng chưa được áp dụng.

## 4. Baseline của hệ thống trước incident

Dữ liệu giả lập tại 08:55, khi chưa triển khai canary:

| Chỉ số | Baseline |
| --- | ---: |
| Message ingress | 100 record/s |
| Consumer processing | ~100 record/s |
| Group lag tổng | 35 record |
| p95 handler latency | 120 ms |
| Retryable error rate | 0,2% delivery |
| DLT rate | 0–1 record/giờ |
| Rebalance | 0 trong 30 phút gần nhất |
| PostgreSQL pool active/max | 7/20 |
| Connection acquisition pending | 0 |
| Số stable pods | 2 |
| Số canary pods | 0 |
| Business reconciliation | Chưa có chênh lệch được phát hiện |

Những con số chỉ để làm **mốc so sánh**. Không phải hệ thống có throughput 100 record/s thì luôn cần pool 20 hay p95 120 ms.

### Quy ước dữ liệu bài tập

Topic nguồn:

```text
orders.events
  partitions: 0, 1, 2, 3
  key: orderId
  value: OrderEvent JSON
```

Một event hợp lệ:

```json
{
  "eventId": "evt-701",
  "orderId": "order-1092",
  "version": 5,
  "status": "PAID",
  "occurredAt": "2026-11-16T01:00:05Z"
}
```

Một event mà version mới chưa hỗ trợ:

```json
{
  "eventId": "evt-702",
  "orderId": "order-1093",
  "version": 6,
  "status": "RETURN_REQUESTED",
  "occurredAt": "2026-11-16T01:00:06Z"
}
```

Tình huống giả định: producer đã bắt đầu phát status `RETURN_REQUESTED` theo thay đổi hợp đồng, trong khi validation của canary version 1.9.0 lại dùng enum cũ và coi trạng thái này là lỗi không retryable. Đây là một giả thuyết cần kiểm chứng bằng evidence, không phải kết luận trước khi điều tra.

## 5. Bộ dữ liệu incident: timeline mô phỏng

Các mốc thời gian tính theo giờ địa phương của lab. Chỉ số là các snapshot mẫu; tốc độ ingress/processing tại một thời điểm không phải giá trị trung bình của toàn khoảng giữa hai snapshot.

| Thời điểm | Diễn biến quan sát được | Lag tổng | DLT tăng mới trong 5 phút gần nhất | DB pool active/max |
| --- | --- | ---: | ---: | ---: |
| 08:55 | Stable v1.8.0 chạy bình thường | 35 | 0 | 7/20 |
| 09:00 | Canary v1.9.0 bắt đầu join group | 80 | 0 | 8/20 |
| 09:02 | Rebalance hoàn tất, canary nhận P3 | 140 | 0 | 9/20 |
| 09:04 | Log canary xuất hiện lỗi unknown status | 420 | 12 | 12/20 |
| 09:07 | Connection acquisition timeout tăng | 2.300 | 55 | 20/20 |
| 09:10 | Retry rate tăng, có lần chuyển quyền partition tiếp | 6.400 | 310 | 20/20 |
| 09:13 | Business write rate thấp hơn ingest đáng kể | 13.900 | 920 | 20/20 |
| 09:16 | Giảm phạm vi canary và xử lý connection pressure | 16.100 | 1.050 | 15/20 |
| 09:20 | Stable tăng processing, lag bắt đầu giảm | 12.700 | 30 | 11/20 |
| 09:32 | Nguồn tiến triển gần baseline | 480 | 0 | 9/20 |
| 09:40 | Lag gần baseline, DLT cases còn tồn | 55 | 0 | 8/20 |

Bảng chỉ mô tả **tín hiệu hệ thống** và thời điểm bắt đầu mitigation. Nó không xác nhận tất cả lỗi đã được sửa ở 09:16 hoặc tất cả case nghiệp vụ đã được giải quyết ở 09:40.

### Những câu hỏi cần trả lời từ timeline

1. Vì sao lag bắt đầu tăng sau canary join?
2. Lỗi status mới là nguồn gây toàn bộ lag hay chỉ một phần?
3. Database pool saturation là nguyên nhân gốc, hệ quả của canary, hay một sự cố đồng thời?
4. Vì sao có nhiều DLT record trong lúc DB không sẵn sàng?
5. Rebalance lúc 09:10 có khả năng làm record được giao lại không?
6. Khi lag trở về 55 ở 09:40, liệu incident có thể đóng ngay không?
7. Cần lưu bằng chứng nào để biết canary đã xử lý event nào trước khi rollback?

Câu trả lời phải dựa trên log, metric, Kafka group và dữ liệu nghiệp vụ ở các phần tiếp theo.

## 6. Mẫu log đã thu thập

Đây là log giả lập được dùng làm evidence của bài tập.

### 6.1. Canary gia nhập group

```text
09:00:11 INFO  event=consumer.start
  app=order-projection version=1.9.0 track=canary
  groupId=order-projection

09:00:13 INFO  event=kafka.rebalance.revoked
  pod=order-projection-stable-b
  partitions=[orders.events-3]

09:02:02 INFO  event=kafka.rebalance.assigned
  pod=order-projection-canary
  partitions=[orders.events-3]
```

Đây là bằng chứng canary được giao P3 tại thời điểm đó. Nó **chưa** chứng minh canary nhận đúng tỷ lệ lưu lượng vì các partition có thể có độ nóng khác nhau.

### 6.2. Lỗi schema/validation

```text
09:04:19 WARN  event=order.consume.failed
  track=canary topic=orders.events
  partition=3 offset=8112
  exception=InvalidOrderEventException
  reason=UNKNOWN_STATUS

09:04:19 INFO  event=order.dlt.publish.requested
  sourceTopic=orders.events sourcePartition=3
  sourceOffset=8112 target=orders.events.DLT

09:04:20 INFO  event=order.dlt.publish.confirmed
  sourceTopic=orders.events sourcePartition=3
  sourceOffset=8112 targetPartition=3
```

Chỉ log `publish.confirmed` khi producer đã xác nhận gửi thành công. Một dòng `publish.requested` đơn lẻ chưa chứng minh record đã tồn tại trên DLT.

### 6.3. Database pool lỗi

```text
09:07:03 ERROR event=order.consume.failed
  track=stable topic=orders.events
  partition=0 offset=15120
  exception=CannotGetJdbcConnectionException
  cause=Connection is not available,
        request timed out after 3000ms

09:07:05 WARN  event=order.retry
  topic=orders.events partition=0 offset=15120
  attempt=2 reason=DB_CONNECTION_TIMEOUT

09:07:09 ERROR event=order.dlt.publish.confirmed
  sourceTopic=orders.events sourcePartition=0
  sourceOffset=15120
  exception=CannotGetJdbcConnectionException
```

Đoạn này cho thấy cả stable version gặp lỗi database; nó phản bác cách giải thích quá đơn giản “mọi lỗi đều do parser v1.9.0”. Đồng thời nó gợi ý retry budget đang đưa cả lỗi phụ thuộc hạ tầng diện rộng vào DLT.

### 6.4. Rebalance và redelivery

```text
09:10:32 WARN  event=kafka.poll.progress.warning
  pod=order-projection-canary
  elapsedSinceSuccessfulPollMs=306000

09:10:35 WARN  event=kafka.partitions.lost
  pod=order-projection-canary
  partitions=[orders.events-3]

09:10:38 INFO  event=kafka.partitions.assigned
  pod=order-projection-stable-a
  partitions=[orders.events-3]

09:10:41 INFO  event=order.duplicate.suppressed
  pod=order-projection-stable-a
  eventId=evt-698
  sourcePartition=3
```

Đây là tình huống có thể xảy ra nếu poll loop bị giữ quá lâu hoặc consumer mất membership. Cần đọc cấu hình `max.poll.interval.ms`, listener processing, heartbeat và group protocol trước khi kết luận chính xác lý do mất assignment.

Log duplicate suppression chứng minh handler phát hiện một event đã có marker, **không phải** bằng chứng DB đã bị ghi sai hai lần.

## 7. Trạng thái Kafka consumer group

Các dữ liệu giả lập từ một truy vấn group tại 09:13:

```text
GROUP             TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-projection  orders.events  0          15700           18700           3000
order-projection  orders.events  1          16200           19400           3200
order-projection  orders.events  2          14300           18100           3800
order-projection  orders.events  3          8250            12150           3900
TOTAL                                                                     13900
```

Các offset là **committed offsets của group theo partition**, không phải số lượng record đã ghi vào database. Không dùng `CURRENT-OFFSET=15700` để suy ra đã thành công với đúng 15.700 event nghiệp vụ.

Có thể dùng lệnh read-only:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection
```

Và xem topic:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events
```

Trong production, địa chỉ bootstrap, SASL/TLS client properties và quyền Kafka phải lấy từ runbook hiện hành. Không đưa credentials vào lịch sử shell hoặc tài liệu incident.

### Khi group đang rebalance

Trong lúc rebalance, owner/offset/lag có thể biến động nhanh. Một snapshot `--describe` không đủ kết luận group đã ổn định. Cần so sánh nhiều lần hoặc dựa vào assignment/event metric để biết diễn biến thực tế.

Nếu group không có committed offset, công cụ có thể hiển thị giá trị không có hoặc dấu gạch; không biến các giá trị đó thành số 0 mà không hiểu ngữ cảnh.

## 8. Tài liệu cấu hình ban đầu của consumer

Một phần cấu hình được cung cấp cho bài tập:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all

    listener:
      ack-mode: record
      concurrency: 1

app:
  kafka:
    topic: orders.events
    dlt-topic: orders.events.DLT
```

Các điểm cần đánh giá:

- `enable-auto-commit=false` và `ack-mode=record` cho container quản lý tiến độ theo record.
- `max.poll.interval.ms=300000` là 5 phút; nếu xử lý đồng bộ vượt giới hạn này, consumer có thể mất membership theo behavior của client/protocol.
- `max-poll-records=100` ảnh hưởng số record mỗi poll, nhưng không giới hạn trực tiếp tổng thời gian xử lý từng record.
- `auto-offset-reset=earliest` chỉ liên quan khi không có committed offset hợp lệ; nó không làm group tự đọc lại toàn topic sau rollback.
- `acks=all` làm producer chờ xác nhận theo Kafka, nhưng không tự tạo exactly-once business effect trong PostgreSQL.
- Các pod cùng group chia **partition**, không chia lưu lượng theo tỷ lệ HTTP.

Trong lab, cấu hình môi trường phải đảm bảo bootstrap servers trỏ tới Kafka test, không tới cluster production.

## 9. Retry và DLT policy trước incident

Code chính của error handler trong tình huống:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class ConsumerErrorConfiguration {

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<String, String> template) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                template,
                (record, exception) -> new TopicPartition(
                    "orders.events.DLT",
                    record.partition()
                )
            );

        recoverer.setFailIfSendResultIsError(true);

        DefaultErrorHandler errorHandler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
            );

        errorHandler.addNotRetryableExceptions(
            InvalidOrderEventException.class
        );

        return errorHandler;
    }
}
```

`InvalidOrderEventException` là exception do ứng dụng định nghĩa. Các lỗi khác, bao gồm nhiều lỗi kết nối database, có thể được retry theo classification mặc định rồi gọi recoverer sau khi hết attempts.

**Vấn đề cần phát hiện:** policy hiện tại đưa cả transient database outage diện rộng vào DLT sau vài lần retry. Điều đó có thể hợp lệ cho một số nghiệp vụ, nhưng trong bài tập này yêu cầu business event chỉ được cách ly do **lỗi dữ liệu/record không thể xử lý**, còn outage hạ tầng cần ngăn việc commit/đẩy hàng loạt sang DLT nếu chưa có quyết định vận hành. Vì vậy đây là một **khoảng trống chính sách cần sửa**, không chỉ là vấn đề tăng retry count.

### Số lần retry

`new FixedBackOff(1_000L, 2L)` có nghĩa:

```text
Lần handler đầu: attempt 1
  nếu lỗi -> chờ 1 giây

Retry 1: attempt 2
  nếu lỗi -> chờ 1 giây

Retry 2: attempt 3
  nếu lỗi -> recoverer (DLT)
```

Nếu handler bị redeliver sau rebalance hoặc process crash, có thể có thêm các lần xử lý trong execution khác. Không coi tổng ba lời gọi là bảo đảm exactly-once của Kafka.

## 10. Database schema và quy tắc idempotency

Để không ghi trùng trạng thái nghiệp vụ, ứng dụng lưu một marker cho mỗi event và projection theo version.

Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_order_event (
    projection_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(120) PRIMARY KEY,
    last_event_version BIGINT NOT NULL,
    current_status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_processed_order_event_time
    ON processed_order_event (processed_at);
```

Một handler hợp lệ có thể dùng transaction:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {

        int inserted = jdbc.update(
            """
            INSERT INTO processed_order_event (
                projection_name, event_id
            ) VALUES ('order-projection', ?)
            ON CONFLICT (projection_name, event_id)
            DO NOTHING
            """,
            event.eventId()
        );

        if (inserted == 0) {
            return;
        }

        jdbc.update(
            """
            INSERT INTO order_projection (
                order_id, last_event_version, current_status
            ) VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                last_event_version = EXCLUDED.last_event_version,
                current_status = EXCLUDED.current_status,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_projection.last_event_version
                < EXCLUDED.last_event_version
            """,
            event.orderId(),
            event.version(),
            event.status()
        );
    }
}
```

Ví dụ giả định record `OrderEvent` có các accessor `eventId()`, `orderId()`, `version()`, `status()` và bean `JdbcTemplate` hoạt động trên cùng datasource với transaction manager JDBC.

**Phạm vi bảo đảm:**

- Nếu database transaction rollback, marker và projection rollback cùng nhau.
- Nếu database commit rồi consumer chết trước Kafka offset commit, record có thể được giao lại, marker giúp bỏ qua.
- Điều kiện version tránh một event cũ ghi đè trạng thái mới.
- Nếu một nghiệp vụ cần xử lý mọi version liên tục, còn phải kiểm tra gap và thứ tự; chỉ `last_event_version` chưa đủ.
- Nếu có HTTP call, gửi email hoặc Kafka publish nằm ngoài transaction, cần cơ chế idempotency/outbox riêng.

**Không dùng Kafka offset làm khóa duy nhất cho nghiệp vụ** khi một business event có thể xuất hiện từ nhiều nguồn/replay. Offset hữu ích để truy vết một record, còn idempotency key cần theo ý nghĩa của event/operation.

## 11. Vai trò trong buổi diễn tập

Nên phân vai thay vì một người tự làm mọi việc:

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident Commander (IC) | Điều phối, xác định mức độ, chọn mitigation, quyết định đóng incident |
| Kafka investigator | Group state, partition assignment, offsets, broker/producer errors |
| Application investigator | Release diff, exception classes, retry/DLT behavior, handler latency |
| Database investigator | Pool, timeout, lock, slow query, committed business rows |
| Scribe/communications | Timeline, giả thuyết, quyết định, thời điểm thay đổi, cập nhật stakeholder |
| Reviewer/observer | Quan sát quy trình, yêu cầu bằng chứng, chấm rubric sau diễn tập |

Với nhóm ít người, một người có thể giữ nhiều vai trò, nhưng vẫn nên tách **người đề xuất thay đổi** và **người xác nhận tác động** với thao tác rủi ro cao.

Trước khi bắt đầu, cả nhóm phải biết môi trường lab, namespace, Kafka bootstrap, database test, cách dọn tài nguyên và rollback.

## 12. Khởi tạo môi trường lab an toàn

Bài tập có thể chạy theo hai mức:

**Mức A — Phân tích evidence trên giấy:** không cần khởi động Kafka. Người học dùng timeline, log và snapshot metric giả lập để lập kế hoạch, chọn hành động và viết postmortem.

**Mức B — Fault injection thật trong lab:** sử dụng Embedded Kafka/Testcontainers hoặc một cluster Kafka/PostgreSQL staging có sẵn. Không áp dụng lỗi lên production để hoàn thành bài.

### Topology đề xuất cho lab

```text
Lab orchestrator
  |
  +-- Kafka broker / Kafka test cluster
  |     orders.events.lab (4 partitions)
  |     orders.events.lab.DLT (4 partitions)
  |
  +-- PostgreSQL test
  |     order_projection
  |     processed_order_event
  |
  +-- stable-consumer-v1 (2 instances)
  |
  +-- canary-consumer-v2 (1 instance)
  |
  +-- load-generator
  |
  +-- metrics/log collector
```

Đối với topic tên `orders.events.lab`, tất cả group, database và credentials phải được tách biệt với production. Nếu muốn thử lỗi rebalance và process crash, consumer nên chạy ở process/container độc lập; việc `container.stop()` từ test JVM chủ yếu mô phỏng graceful leave, không hoàn toàn tương đương SIGKILL/mất mạng.

### Dữ liệu thử nghiệm

Chuẩn bị tối thiểu:

- 1.000 event hợp lệ với eventId duy nhất và orderId phân bố trên cả bốn partition.
- 20 event có status mới `RETURN_REQUESTED`.
- 10 event JSON không hợp lệ.
- 20 event được gửi lặp cùng eventId để kiểm tra idempotency.
- Một số event version cũ đến sau version mới.
- Một nhóm event có handler giả lập DB timeout trong khoảng được kiểm soát.

Mỗi nhóm event cần biết trước số lượng và business key, từ đó có thể đối soát mà không dựa duy nhất vào số callback Kafka.

## 13. Pha 1 — Phát hiện và mở incident

### Bài tập cho người trực on-call

Giả sử lúc 09:07 nhận ba cảnh báo:

```text
ALERT 1: kafka_consumer_lag_total > 2000
         group=order-projection

ALERT 2: jdbc_pool_pending_connections > 20
         service=order-projection

ALERT 3: dlt_publish_rate_5m > 50
         topic=orders.events.DLT
```

Các tên metric chỉ là mẫu minh họa. Ứng dụng thực có thể dùng Kafka client metrics, Micrometer, JMX exporter hoặc metric tự định nghĩa.

Người học cần thực hiện:

1. Ghi thời điểm phát hiện, nhóm ảnh hưởng và người phụ trách.
2. Xác định phạm vi khách hàng/đơn hàng hoặc business flow bị ảnh hưởng.
3. Kiểm tra dashboard có đang hiển thị dữ liệu mới, hay metrics đã stale.
4. Nhìn trạng thái consumer group và tỷ lệ xử lý thành công, không chỉ nhìn pod health.
5. Đánh giá mức độ nghiêm trọng theo SLO của hệ thống, không chỉ theo số lượng log.
6. Ghi một thông điệp incident ban đầu: biết gì, chưa biết gì, hành động tiếp theo.

### Bản thông báo mẫu

> Từ khoảng 09:04, nhóm consumer `order-projection` có lag và DLT rate tăng, đồng thời hệ thống database ghi nhận connection acquisition timeout. Các bản ghi lỗi có thể chưa được áp dụng vào trạng thái đơn hàng. Nhóm đang xác định phạm vi impact, tách lỗi schema và hạ tầng, đồng thời chuẩn bị giảm phạm vi canary. Chưa có bằng chứng mất dữ liệu vĩnh viễn; không reset offsets trong khi điều tra.

Thông báo có chủ đích phân biệt **rủi ro** với **sự kiện đã được xác nhận**. Không tuyên bố mất dữ liệu hay đã phục hồi trước khi có evidence.

## 14. Pha 2 — Thu thập bằng chứng theo lớp

Tạo một bảng evidence, ghi nguồn và thời gian:

| Cần biết | Công cụ/nguồn | Đầu ra cần lưu |
| --- | --- | --- |
| Topic có bao nhiêu partition? | Kafka Admin/CLI | Partition count, leaders, ISR nếu phù hợp |
| Group đang sở hữu partition nào? | Consumer group description, rebalance logs | Member → topic-partition |
| Lag tăng ở partition nào? | Kafka metrics/group describe | Lag theo partition và thời điểm |
| Có record nào đi DLT? | DLT consumer/audit | Original topic/partition/offset, exception type |
| Listener lỗi ở stage nào? | Application log/trace | Deserialize, validate, DB, external API |
| DB có quá tải? | HikariCP/DB metrics | Active/idle/pending, locks, slow queries |
| Canary có chạy bản code mới? | Deployment/release metadata | Image digest/version, start time |
| Có duplicate delivery? | Application log/DB marker | eventId và số lần nhận/áp dụng |
| Producer có vấn đề? | Producer metrics/broker logs | Send failures, auth errors, delivery latency |
| Source offset đã commit tới đâu? | Kafka group metadata | Committed offset theo partition |
| Dữ liệu nghiệp vụ có đúng? | SQL/API reconciliation | eventId marker, order status, version |

**Không gom mọi nguồn log theo một timestamp rồi mặc định đồng hồ của các node đồng bộ tuyệt đối.** Nếu cần dựng timeline chính xác, xác minh timezone, clock skew và timestamp source.

### Read-only Kafka commands

Ví dụ:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events.lab

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection-lab

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

Lệnh `--list` có thể trả nhiều group không liên quan; chỉ dùng trong lab hoặc môi trường được cấp quyền.

### Read-only Kubernetes commands

```bash
kubectl -n kafka-lab get deployments
kubectl -n kafka-lab get pods -l app=order-projection
kubectl -n kafka-lab describe deployment/order-projection-canary
kubectl -n kafka-lab logs deployment/order-projection-canary --since=30m
```

Lệnh chỉ nhằm thu thập thông tin. Trong production, nên xác minh đúng kube-context, namespace và quyền truy cập trước khi làm gì tiếp theo.

## 15. Pha 3 — Xây giả thuyết và kiểm chứng

Không nên chọn ngay một lời giải chỉ vì log gần thời điểm deploy. Hãy liệt kê giả thuyết có thể bác bỏ.

| Giả thuyết | Evidence ủng hộ | Evidence cần thu thập để bác bỏ/xác nhận |
| --- | --- | --- |
| H1: Parser v1.9.0 không hỗ trợ status mới | Unknown-status chỉ xuất hiện ở canary, DLT P3 | So sánh schema/enum release diff, source event types, stable behavior |
| H2: Database thiếu connection làm mọi member chậm | Cả stable và canary đều có timeout; pool 20/20 | Query pool metrics theo pod, DB connection count, locks/slow queries |
| H3: Retry policy biến outage thành DLT storm | DLT tăng mạnh kèm lỗi JDBC transient | Audit DLT exception distribution và error handler config |
| H4: Rebalance gây mất dữ liệu | Partition lost/assigned, duplicate delivery | Committed offsets và marker/DB reconciliation; có thực sự mất key không? |
| H5: Kafka broker bị lỗi nên lag tăng | Lag tăng và rebalance | Broker health, replication, producer errors, coordinator logs |
| H6: DB query mới ở canary làm connection giữ quá lâu | Lỗi xảy ra sau deploy, pool saturate | SQL trace, transaction duration, thread dump, version diff |
| H7: DLT producer thiếu quyền ghi | DLT exception nhưng source không tiến | Kiểm tra publish confirmation và ACL error; ở evidence hiện tại có confirmed sends |

Từ mẫu log ở phần trước:

- Có căn cứ cho H1, nhưng cần xác nhận event enum và mức độ ảnh hưởng.
- H2 được hỗ trợ mạnh vì cả stable cũng gặp DB timeout.
- H3 là một **vấn đề chính sách rõ ràng** nếu outage diện rộng không được phép đưa vào DLT.
- Rebalance và duplicate suppression **chưa đủ** để kết luận mất business event.
- Evidence `dlt.publish.confirmed` với offset 8112 làm H7 kém phù hợp cho record đó, nhưng không loại trừ lỗi DLT producer tại thời điểm khác.

Cần phân biệt **nguyên nhân phát sinh sự cố** với **cơ chế làm sự cố nặng hơn**. Một change ở canary có thể gây tăng DB latency; retry policy lại làm DLT backlog tăng; rebalance có thể là hệ quả của handler bị chặn.

## 16. Pha 4 — Xác định tác động và mức độ nghiêm trọng

### Không dùng riêng consumer lag để đánh giá impact

Tại 09:13, lag là 13.900. Con số này biểu thị backlog theo offsets ở thời điểm đó. Nó **không** cho biết chính xác có bao nhiêu đơn hàng bị mất hay bao nhiêu trạng thái chưa cập nhật, vì:

- Có event lỗi đang chờ retry.
- Có event đã được commit nguồn nhưng đang nằm ở DLT.
- Có event duplicate delivery nhưng đã được chặn ở DB.
- Một order có thể có nhiều event/version.
- Có event chưa đủ điều kiện xử lý theo policy.

Cần đánh giá ít nhất:

1. Số **event ID duy nhất** đã phát trong khoảng ảnh hưởng.
2. Số event ID được ứng dụng xử lý thành công ở business store.
3. Số event đang chờ trong source group (theo offset/range).
4. Số event được đưa vào DLT và chưa được giải quyết.
5. Số event có outcome không xác định, cần đối soát.
6. Số khách hàng/order có trạng thái hiển thị chưa khớp nguồn.

### Ví dụ reconciliation theo event ID

Giả sử trong cửa sổ điều tra, publisher có danh sách 20.000 event IDs duy nhất:

```text
Published unique events:           20,000
Processed marker unique events:   18,700
DLT source event IDs not applied:  1,000
Pending / unknown at snapshot:       300
-----------------------------------------
Accounting total:                 20,000
```

Đây là **mẫu số liệu minh họa đã được phân nhóm không chồng lấn tại cùng một snapshot**. Trên hệ thống thực, phải deduplicate eventId, giải quyết trường hợp một event nằm cả DLT lẫn DB, và chỉ công bố tổng khi nguồn danh sách event ID đủ đáng tin cậy.

Nếu published event index không có, có thể cần đối chiếu producer outbox, event catalog, topic records trong retention hoặc audit upstream. Không tự lấy `LOG-END-OFFSET` rồi xem đó là số business event toàn hệ thống.

## 17. Pha 5 — Quyết định mitigation an toàn

Một phương án giảm thiểu thường gồm **hai hướng song song**:

- Giảm hoặc loại bỏ regression do canary.
- Giảm pressure lên database và tránh retry/DLT storm.

### 17.1. Dừng canary có kiểm soát

Trong lab:

```bash
kubectl -n kafka-lab scale deployment/order-projection-canary \
  --replicas=0
```

Lệnh thay đổi hệ thống và chỉ nên dùng trong lab/staging được phép. Nếu đây là production, cần xác minh namespace/context, quyền thao tác và quy trình incident change.

Sau khi canary dừng:

1. Chờ group rebalance.
2. Xác nhận stable consumer nhận lại các partition cần thiết.
3. Theo dõi consumer lag và processing rate.
4. Kiểm tra sự kiện có thể được redeliver khi ownership đổi.
5. Không xem rollback image là rollback dữ liệu đã commit.

**Không reset offset chỉ vì canary đã lỗi.** Offset của cùng group vẫn thuộc group, không thuộc riêng pod canary.

### 17.2. Xử lý DB connection pressure

Tùy nguyên nhân:

- Giảm concurrency hoặc số consumer đang phát nhiều request DB.
- Giới hạn số request in-flight và kiểm tra timeout của DB connection acquisition.
- Tạm dừng/stop tiêu thụ theo runbook nếu backend không thể nhận thêm tải.
- Kiểm tra long-running transaction, connection leak, slow query hoặc thay đổi logic v1.9.0.
- Khôi phục database/downstream theo quyền hạn và cơ chế sẵn có.

**Tăng pool từ 20 lên 200 không phải lời giải mặc định.** Nếu database chỉ chịu được 30 connections hữu ích, việc tăng pool có thể khiến nó suy yếu hơn. Cần đo database server capacity và nguyên nhân giữ connection.

### 17.3. Tránh DLT storm cho lỗi hạ tầng diện rộng

Nếu policy được định nghĩa rằng **lỗi DB tạm thời không được recover sang DLT hàng loạt**, có thể:

1. Dừng/tạm dừng xử lý trong lúc outage, giữ source offsets chưa tiến đối với record chưa xử lý.
2. Bổ sung circuit breaker/backoff dài, retry budget và alert hạ tầng.
3. Phân biệt invalid data với dependency outage ở tầng exception classification.
4. Chọn fail-stop hoặc resume có kiểm soát cho lỗi hạ tầng thay vì coi DLT là recovery mặc định.
5. Dành DLT cho lỗi dữ liệu/record không xử lý được hoặc theo chính sách được phê duyệt.

Việc `DefaultErrorHandler` hiện tại publish DLT khi retry cạn là hành vi theo cấu hình, không tự phân biệt “DB outage lan rộng” với “record poison”. **Muốn đổi semantics phải sửa policy và test hồi quy**, không chỉ đổi nhãn trong log.

### Khi nào không nên mitigation bằng canary rollback?

Nếu cùng lỗi đã xuất hiện trước canary, lỗi đến từ database cluster chung hoặc producer đổi schema không tương thích với cả stable, rollback có thể không giải quyết được toàn bộ sự cố. Nên xem nó là một giả thuyết có tác động đo được, rồi kiểm tra kết quả sau khi thực hiện.

## 18. Pha 6 — Quan sát hệ thống sau mitigation

Sau mọi thay đổi, phải kiểm tra **tín hiệu phục hồi**, không chỉ chờ log error giảm.

| Tín hiệu | Điều kiện tạm xem cải thiện | Điều cần tiếp tục kiểm |
| --- | --- | --- |
| Consumer group | Assignment ổn định, không rebalance liên tục | Member có thực sự poll và process không |
| Lag | Giảm theo thời gian khi ingress ổn định | Giảm do xử lý thành công hay do DLT recovery |
| Processing throughput | Vượt ingress đủ lâu để drain backlog | DB có ổn định dưới tải catch-up không |
| DLT rate | Không còn tăng bất thường | DLT tồn cũ đã có kế hoạch xử lý chưa |
| DB pool | Active/pending/latency giảm | Có connection leak hoặc long transaction ẩn không |
| Handler errors | Retryable error giảm | Có unknown status/validation error còn lại không |
| Business reconciliation | Mismatch giảm, event pending được giải quyết | Version/order correctness, duplicate side effect |
| App resources | CPU/heap/GC ổn định | Có retry queue hoặc thread backlog tồn không |

### Ví dụ tính thời gian drain backlog

Nếu sau mitigation có 16.000 record lag, ingress trung bình 100 record/s và consumer xử lý trung bình 160 record/s, tốc độ giảm backlog lý thuyết là:

```text
Net drain rate = 160 - 100 = 60 records/second
Estimated drain duration = 16,000 / 60 ≈ 267 seconds
                        ≈ 4.4 minutes
```

Đây là một phép ước lượng **khi tốc độ và điều kiện giữ ổn định**, không phải thời hạn cam kết. Nếu retry/DLT, partition skew hoặc database throughput thay đổi, thời gian thực sẽ khác. Khi consumer lag giảm, vẫn phải kiểm tra business outcomes.

## 19. Pha 7 — Đối soát offset và dữ liệu nghiệp vụ

### 19.1. SQL kiểm tra marker theo thời gian

```sql
SELECT
    DATE_TRUNC('minute', processed_at) AS minute_bucket,
    COUNT(*) AS unique_processed_events
FROM processed_order_event
WHERE processed_at >= TIMESTAMPTZ '2026-11-16 02:00:00+00'
  AND processed_at <  TIMESTAMPTZ '2026-11-16 03:00:00+00'
GROUP BY 1
ORDER BY 1;
```

Mốc thời gian chỉ để minh họa lab. Chú ý so sánh timestamp UTC với timezone hiển thị của hệ thống giám sát.

### 19.2. Kiểm tra khả năng duplicate trong bảng marker

Với primary key theo `projection_name, event_id`, bảng không thể chứa hai row có khóa giống nhau nếu constraint hoạt động. Có thể truy vấn để xác minh dữ liệu hiện tại:

```sql
SELECT projection_name, event_id, COUNT(*) AS row_count
FROM processed_order_event
GROUP BY projection_name, event_id
HAVING COUNT(*) > 1;
```

Kết quả rỗng chỉ chứng minh không có duplicate **trong bảng marker**, không chứng minh không có hai email hoặc HTTP requests đã được gửi. Cần kiểm tra từng downstream side effect tương ứng.

### 19.3. Đối soát version trạng thái

```sql
SELECT
    order_id,
    last_event_version,
    current_status,
    updated_at
FROM order_projection
WHERE order_id IN ('order-1092', 'order-1093')
ORDER BY order_id;
```

Nếu upstream có một bảng/tracking đáng tin cậy về trạng thái cuối của từng order, có thể so sánh với projection. Trường hợp một order có event version 7 ở source nhưng projection chỉ tới version 5 cần xác định event 6/7 đang chờ, đã DLT hoặc đã bị lọc bởi policy.

### 19.4. Đừng đối chiếu số offset bằng COUNT(*) một cách mù quáng

Kafka offset có thể có lỗ trống do records bị xóa theo retention/compaction hoặc transaction control/batches tùy cách đọc. Một event có thể không ánh xạ 1:1 với một business marker. Vì vậy, kiểm tra theo business key/eventId cùng phạm vi thời gian/source snapshot đáng tin cậy là phương pháp mạnh hơn so với so sánh raw offset với row count.

## 20. Pha 8 — Điều tra và xử lý DLT

Trong incident này, DLT có ít nhất hai nhóm cần tách:

- **Nhóm A:** `InvalidOrderEventException: UNKNOWN_STATUS` — lỗi compatibility/validation.
- **Nhóm B:** `CannotGetJdbcConnectionException` — lỗi phụ thuộc hạ tầng và retry policy không phù hợp với outage diện rộng.

Hai nhóm không nên được replay cùng lúc mà không có điều kiện.

### 20.1. Thu thập DLT case

Bảng case gợi ý:

```sql
CREATE TABLE order_dlt_case (
    source_topic VARCHAR(200) NOT NULL,
    source_partition INTEGER NOT NULL,
    source_offset BIGINT NOT NULL,
    event_id VARCHAR(120),
    error_category VARCHAR(80) NOT NULL,
    state VARCHAR(30) NOT NULL DEFAULT 'NEW',
    first_seen_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    replay_request_id VARCHAR(120),
    PRIMARY KEY (
        source_topic, source_partition, source_offset
    )
);
```

Các headers DLT từ `DeadLetterPublishingRecoverer` thường có thông tin nguồn và exception; cần đọc đúng constants/header format của Spring Kafka version đang chạy. Nếu một record nguồn bị gửi DLT nhiều lần ở các DLT offsets khác nhau, khóa theo **original source topic-partition-offset** giúp tránh lập case trùng (trong một consumer scope được xác định).

Nếu nhiều consumer groups hoặc services cùng dùng kho audit, khóa cần có thêm projection/group identity để tránh hợp nhất nhầm các case khác nhau.

### 20.2. Ưu tiên theo khả năng xử lý

| Nhóm lỗi | Điều kiện trước khi replay | Rủi ro |
| --- | --- | --- |
| Unknown status | Deploy consumer hỗ trợ status hoặc có migration/validation rule mới | Replay quá sớm sẽ đi DLT lần nữa |
| DB timeout | Database ổn định, retry/circuit breaker phù hợp | Replay đồng loạt có thể làm DB quá tải lại |
| Malformed JSON | Sửa payload có audit hoặc chuyển xử lý thủ công | Không thể tự sửa bằng retry cùng payload |
| Permission failure | Sửa quyền/secret theo quy trình | Có thể phát lại khi vẫn thiếu quyền |
| Unknown exception | Phân loại root cause và xác nhận xử lý được | Tạo vòng replay không giới hạn |

### 20.3. Replay có giới hạn

Quy trình vận hành:

1. Chốt danh sách case theo nhóm lỗi, source coordinate và eventId.
2. Xác minh version consumer đã hỗ trợ dữ liệu và backend đang ổn định.
3. Đối chiếu marker để không phát lại sự kiện đã được xử lý hợp lệ nếu policy cho phép skip.
4. Có người phê duyệt phạm vi và giới hạn số event/tốc độ.
5. Publish vào replay topic riêng hoặc source theo thiết kế, kèm correlation/replay request ID.
6. Quan sát outcome thực ở business store, không chỉ Kafka send acknowledgment.
7. Đánh dấu case `RESOLVED` sau khi xác nhận kết quả.
8. Giữ audit về payload version và lý do replay; không chỉnh sửa âm thầm original record.

**Không tự reset toàn bộ consumer group offsets về đầu topic.** Reset sai phạm vi có thể tạo tải lớn và side effect trùng ở hàng triệu event đã được xử lý. Replay theo danh sách case giúp kiểm soát blast radius.

### DLT record có thể bị lặp

Nếu DLT publish thành công nhưng source offset chưa commit vì crash, Kafka có thể giao lại source record và recoverer lại publish vào DLT. Vì vậy cần dedupe theo source coordinate/event ID trong audit. Một DLT offset mới **không nhất thiết là một business failure mới**.

## 21. Bài toán phụ: DLT producer cũng lỗi

Giả sử khi outage xảy ra, Kafka DLT topic bị sai partition count hoặc service account không có quyền WRITE.

Dấu hiệu mô phỏng:

```text
ERROR event=orders.dlt.publish.failed
  sourceTopic=orders.events
  sourcePartition=3 sourceOffset=8175
  target=orders.events.DLT
  exception=TopicAuthorizationException
```

Nếu recoverer không được cấu hình xác nhận lỗi publish, hệ thống có thể hiểu nhầm record đã được cách ly và cho source tiến tiếp theo cách không mong muốn.

Với Spring Kafka 3.x, `DeadLetterPublishingRecoverer` có tùy chọn như:

```java
recoverer.setFailIfSendResultIsError(true);
```

Nó giúp coi lỗi send result là recovery failure. Tuy nhiên cách container retry, seek, xác nhận offset và chuyển trạng thái còn phụ thuộc cấu hình `DefaultErrorHandler` và KafkaTemplate. Cần integration test đúng version, không chỉ dựa vào việc method này tồn tại.

### Câu hỏi phụ

- Có nên tạo topic DLT thủ công ngay giữa incident không?
- Topic DLT phải có số partition nào nếu recoverer dùng `record.partition()`?
- Nếu DLT mất WRITE permission, nên tiếp tục commit source offsets không?
- Nếu một nửa records đã được publish DLT rồi, làm sao tránh audit/replay trùng?

Trả lời phải dựa trên mô hình đảm bảo dữ liệu và quyền vận hành, không chỉ dựa vào việc làm cho log lỗi biến mất.

## 22. Bài toán phụ: Rebalance và duplicate delivery

Sau khi canary rời group, stable tiếp quản P3. Nếu canary đã commit DB nhưng chưa commit Kafka offset cho một record, stable có thể đọc lại record đó.

```text
Consumer canary:
  poll P3 offset 8109
       |
       v
  DB transaction COMMIT
       |
       X process loses partition
       |
       v
  Kafka offset commit chưa thành công

Consumer stable:
  assigned P3
       |
       v
  đọc lại offset 8109
       |
       v
  processed_order_event đã có eventId
       |
       v
  Không áp dụng duplicate side effect
```

Điều này không bất thường với at-least-once. Cần phân biệt:

- **Duplicate delivery:** cùng record/event được handler nhận lại.
- **Duplicate processing attempt:** handler chạy logic nhiều lần, có thể trước commit hoặc sau rollback.
- **Duplicate business side effect:** dữ liệu/tiền/email thực sự bị tác động lặp.

Chỉ trường hợp cuối là sai về kết quả nếu nghiệp vụ không cho phép. Một marker idempotency duy nhất có thể chặn duplicate ở DB nhưng không tự bảo vệ HTTP/email bên ngoài.

### Cách kiểm tra

Trong lab, tạo một event với eventId cố định, cho handler ghi DB thành công rồi mô phỏng replay. Kỳ vọng DB marker không nhân đôi và projection không bị thay đổi trái quy tắc. Muốn tái hiện crash đúng ranh giới **DB commit nhưng chưa offset commit**, cần fault injection hoặc một process độc lập; không giả định `container.stop()` tử tế tạo cùng tình huống.

## 23. Pha 9 — Cập nhật retry policy sau incident

Root cause review có thể đề xuất đổi chính sách, không phải chỉ tăng giới hạn retry.

### 23.1. Chính sách mới theo loại lỗi

| Loại lỗi | Tính chất | Chính sách mục tiêu |
| --- | --- | --- |
| Validation/unsupported schema | Record-specific, không tự hồi phục | DLT/quarantine có audit; sửa consumer/schema rồi replay |
| DB timeout đơn lẻ | Có thể transient | Retry hữu hạn có backoff, giới hạn thời gian |
| DB outage diện rộng | Hạ tầng không sẵn sàng | Circuit breaker/pause/fail-stop, alert; tránh DLT storm theo yêu cầu nghiệp vụ |
| Serialization/producer error | Phụ thuộc payload và producer | Không commit sai khi publish DLT thất bại |
| Unknown programming bug | Không chắc transient | Escalate, tránh retry vô hạn |
| External API 429 | Có thể cần Retry-After | Backoff/rate limit theo hợp đồng API |
| Duplicate event ID | Có thể là redelivery hợp lệ | Bỏ qua side effect theo idempotency marker, không DLT mặc định |

Một số hệ thống tài chính có thể quyết định **không bao giờ skip/commit nguồn** chỉ vì record được gửi DLT, trong khi các hệ thống analytics cho phép DLT quarantine để giữ throughput. Cần ghi rõ quyết định về dữ liệu thay vì áp cùng một policy cho mọi workload.

### 23.2. Tránh retry lồng nhau

Một handler có thể dùng Spring Retry hoặc HTTP client retry, trong khi `DefaultErrorHandler` lại retry chính listener. Nếu client retry 3 lần và container retry 3 lần, một business operation có thể phát nhiều request hơn mong đợi.

Để điều tra retry storm, cần thống kê số attempts ở **từng tầng**:

```text
Kafka record delivery
    |
    +-- DefaultErrorHandler retry budget
            |
            +-- Service method
                    |
                    +-- HTTP/JDBC client retry budget
```

Thiết kế mục tiêu phải xác định tổng retry budget, timeout và cách phối hợp backoff. Không cho hai tầng cùng retry vô hạn.

## 24. Non-blocking retry có phải lời giải ngay cho incident này?

Spring Kafka có `@RetryableTopic`, chuyển record lỗi sang retry topic để không giữ source partition quá lâu. Tuy nhiên nó không tự giải quyết database outage hoặc schema incompatibility.

Ví dụ cơ chế:

```text
orders.events
   |
   +-- normal success
   |
   +-- temporary failure -> orders.events-retry-...
                              |
                              +-- retry later
                              |
                              +-- exhausted -> DLT
```

Ưu điểm là poison record không giữ source partition liên tục. Nhưng:

- Có thêm retry topics, consumers, offsets và ACL.
- Record phía sau ở source có thể được xử lý trước record đang ở retry topic.
- Với workload yêu cầu order theo key, cần versioning/ordering policy.
- Khi DB outage ảnh hưởng tất cả record, retry topics vẫn có thể chứa lượng lớn backlog.
- Nếu kết hợp `@RetryableTopic` với blocking retry, tổng số attempts có thể lớn hơn dự kiến.

Vì vậy, trong lúc incident đang xảy ra, **không nên đổi sang một retry topology mới chưa test** chỉ để giảm lag. Ưu tiên biện pháp đơn giản, có khả năng rollback và có bằng chứng an toàn. Sau incident mới cân nhắc kiến trúc non-blocking retry qua thử nghiệm.

## 25. Test kịch bản incident bằng Embedded Kafka

Embedded Kafka phù hợp để xác minh retry, DLT và luồng processing cơ bản trong JVM test. Nó không tái hiện đầy đủ broker outage, cluster ISR, process crash hay network partition.

Dependency Gradle minh họa:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Với ví dụ PostgreSQL `ON CONFLICT`, cần dùng PostgreSQL test hoặc Testcontainers nếu kiểm thử đúng business SQL. H2 chỉ phù hợp khi test code đã có cú pháp tương thích hoặc khi mock tầng nghiệp vụ.

### 25.1. Tạo broker test và topic

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=order-projection-it",
    "spring.kafka.consumer.auto-offset-reset=earliest",
    "app.kafka.topic=orders.events.lab",
    "app.kafka.dlt-topic=orders.events.lab.DLT"
})
@EmbeddedKafka(
    partitions = 4,
    topics = {
        "orders.events.lab",
        "orders.events.lab.DLT"
    },
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@DirtiesContext
class OrderIncidentIntegrationTest {
    // Viết test ở các mục dưới.
}
```

Nếu ứng dụng có topic configuration hoặc KafkaAdmin, tránh tạo các topic trùng tên với số partition khác trong cùng test context. Nên đặt group ID riêng cho từng suite để không dùng lại committed offsets không mong muốn.

### 25.2. Test non-retryable event đi DLT

Giả sử listener parse JSON và ném `InvalidOrderEventException` cho unknown status.

```java
@Autowired
KafkaTemplate<String, String> producer;

@Autowired
EmbeddedKafkaBroker broker;

@Test
void unknownStatusIsQuarantined() throws Exception {

    String payload = """
        {
          "eventId":"evt-it-invalid-1",
          "orderId":"order-it-1",
          "version":1,
          "status":"UNKNOWN_TEST_STATUS"
        }
        """;

    producer.send(
        "orders.events.lab",
        3,
        "order-it-1",
        payload
    ).get(10, TimeUnit.SECONDS);

    Map<String, Object> props = new HashMap<>(
        KafkaTestUtils.consumerProps(
            "dlt-verifier-" + UUID.randomUUID(),
            "false",
            broker
        )
    );

    props.put("auto.offset.reset", "earliest");

    try (Consumer<String, String> verifier =
            new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new StringDeserializer()
            ).createConsumer()) {

        ConsumerRecord<String, String> dlt =
            KafkaTestUtils.getSingleRecord(
                verifier,
                "orders.events.lab.DLT",
                Duration.ofSeconds(20)
            );

        assertEquals(payload, dlt.value());
        assertEquals("order-it-1", dlt.key());
        assertEquals(3, dlt.partition());
    }
}
```

Đây là một method minh họa; cần imports cho JUnit, Spring Kafka, Kafka client, Map, UUID, Duration, TimeUnit và các test beans tương ứng. Muốn test độc lập và ổn định, chờ source listener được assign partition trước khi publish, sử dụng topic/group dữ liệu cô lập, và bảo đảm không có nhiều DLT record ngoài corpus của test.

**Mục đích:** chứng minh record cụ thể được recover vào DLT, không chỉ thấy exception log. Đồng thời phải xác minh DB projection không được cập nhật cho record invalid.

### 25.3. Test retry tạm thời rồi thành công

Sử dụng fake dependency:

```java
AtomicInteger attempts = new AtomicInteger();

OrderDependency fake = event -> {
    int call = attempts.incrementAndGet();

    if (call <= 2) {
        throw new TemporaryOrderDependencyException(
            "Controlled transient outage",
            new IllegalStateException("test-only")
        );
    }
};
```

Với `FixedBackOff(1000L, 2L)` và policy retryable phù hợp, assertion:

1. Event cuối cùng được xử lý thành công.
2. Không có DLT record cho event đó.
3. Service được gọi lại theo policy trong scenario một record cô lập.
4. Business side effect chỉ được commit một lần.
5. Group vẫn có thể xử lý event hợp lệ đứng sau.

Không chỉ dựa vào `attempts==3` để kết luận thành công; business DB và DLT outcome mới là bằng chứng chính.

### 25.4. Test retry cạn và recoverer thất bại

Hai scenario độc lập:

- Dependency luôn ném lỗi transient: xác minh chính sách hiện tại recover vào DLT sau retry budget.
- DLT producer không gửi được: xác minh lỗi recovery được phản ánh, hệ thống không **âm thầm** đánh dấu record nguồn đã xử lý thành công.

Không xóa topic thật hoặc vô hiệu hóa quyền ở production. Dùng mock KafkaTemplate/Testcontainers hoặc topic/credentials lab để tạo failure có kiểm soát. Khi mock lỗi send, cần mô phỏng cả asynchronous future failure tùy phiên bản producer API; chỉ mock method ném exception ngay có thể chưa bao phủ lỗi send result.

## 26. Test rebalance và consumer crash

Một bài incident tổng hợp phải kiểm tra cả đường chuyển quyền partition.

### Kiểm thử graceful leave trong lab

1. Tạo topic 4 partition và hai consumer containers A/B cùng group.
2. Start A, chờ A được assign đủ partition.
3. Start B, chờ Kafka phân lại partition.
4. Kiểm tra hợp assignment bằng toàn bộ partition, giao hai tập rỗng khi group ổn định.
5. Stop B và chờ A nhận lại partition.
6. Gửi event mới, kiểm tra handler tiếp tục xử lý.

Ví dụ điều kiện chờ bằng Awaitility:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        Set<TopicPartition> pa = assigned(a);
        Set<TopicPartition> pb = assigned(b);

        assertFalse(pa.isEmpty());
        assertFalse(pb.isEmpty());
        assertTrue(Collections.disjoint(pa, pb));

        Set<TopicPartition> all =
            new HashSet<>(pa);
        all.addAll(pb);

        assertEquals(4, all.size());
    });
```

Hàm `assigned(...)` là helper trả về tập partition hiện tại, chuyển `null` thành tập rỗng; `a` và `b` đại diện cho container đã start. Không assert consumer A phải luôn nhận đúng partition số 0/1; điều đó phụ thuộc assignor.

### Kiểm thử process crash

Nếu mục tiêu là tạo cửa sổ DB commit thành công nhưng Kafka offset chưa commit, cần:

- Consumer chạy trong process/container độc lập.
- Fault injection xác nhận DB đã commit event X.
- Dừng mạnh consumer trước khi offset commit.
- Xác minh committed offset còn cũ.
- Cho member khác tiếp quản và quan sát redelivery.
- Xác minh idempotency marker chặn duplicate side effect.

`container.stop()` tử tế thường cho consumer cơ hội hoàn tất/commit nên **không phải** test crash tương đương. Testcontainers hoặc môi trường staging thích hợp hơn.

## 27. Bài tập decision-making theo từng pha

Để không biến buổi diễn tập thành thao tác máy móc, người học phải ghi lại **quyết định** ở mỗi pha.

| Pha | Câu hỏi ra quyết định | Bằng chứng tối thiểu |
| --- | --- | --- |
| Detect | Có incident hay chỉ là spike ngắn? | Lag/DLT/DB metrics, timestamp |
| Triage | Ảnh hưởng nhóm khách hàng nào? | Business KPI và event ID window |
| Hypothesize | Có một hay nhiều failure modes? | Log từ stable/canary, DB, Kafka |
| Mitigate | Rollback canary hay giảm tải DB trước? | Impact, tốc độ lỗi, khả năng rollback |
| Stabilize | Hệ thống đã tiến triển ổn định chưa? | Assignment, throughput, lag trend |
| Recover | Case DLT nào có thể replay? | Root cause đã sửa, idempotency, approval |
| Verify | Đầu ra đã đúng chưa? | Business reconciliation và DLT case status |
| Close | Có thể đóng incident chưa? | SLO, owner sign-off, unresolved risks |
| Prevent | Cần sửa policy và test gì? | Root cause, action items, deadline |

Mỗi quyết định nên ghi rõ: **ai quyết**, **lúc nào**, **dựa trên dữ liệu nào**, **rủi ro nào được chấp nhận**, và **kế hoạch rollback của quyết định**.

## 28. Bộ câu hỏi dành cho người học

### Nhóm A — Chẩn đoán

1. Từ timeline, chỉ ra ít nhất ba triệu chứng và hai giả thuyết nguyên nhân khác nhau.
2. DLT count tăng sau DB outage nói gì về retry policy?
3. Tại sao `pod Ready` không chứng minh consumer đang xử lý đúng?
4. Có thể khẳng định các event ở P3 bị mất khi canary mất partition không?
5. Vì sao một event có thể xuất hiện ở DLT nhưng consumer lag của source vẫn giảm?
6. Cần xem metric gì để phân biệt pool exhaustion do connection leak với DB query chậm?

### Nhóm B — Mitigation

7. Trường hợp nào nên tạm dừng hoặc stop consumption thay vì tăng retry attempts?
8. Tại sao không tăng Hikari pool size lên gấp mười ngay lập tức?
9. Sau rollback canary, cần kiểm tra những gì trước khi tuyên bố ổn định?
10. Nếu DLT producer lỗi, có được tiếp tục commit source offset không?
11. Nếu status `RETURN_REQUESTED` là thay đổi schema hợp lệ, biện pháp ngắn hạn và dài hạn là gì?
12. Khi nhiều stable pods cùng bị DB timeout, chỉ rollback canary có thể đủ không?

### Nhóm C — Data correctness

13. Sự khác nhau giữa duplicate delivery và duplicate side effect là gì?
14. Tại sao DLT có thể có hai record cho cùng source topic-partition-offset?
15. Tại sao `eventId` thường phù hợp hơn `JobExecution ID` hoặc Kafka offset để idempotency nghiệp vụ?
16. Nếu projection version là 7 nhưng record retry version 6 được nhận lại, handler cần làm gì?
17. Một SQL query trả về “không có duplicate marker” đã chứng minh không có email gửi trùng chưa?
18. Vì sao reset offsets về earliest không phải kế hoạch replay DLT an toàn?

### Nhóm D — Recovery và hậu kiểm

19. Điều kiện nào cho phép replay lỗi DB, và điều kiện nào cho phép replay lỗi schema?
20. Khi lag trở về baseline nhưng còn 1.000 DLT case `NEW`, có thể đóng incident chưa?
21. Cần những số liệu nào để tính thời gian backlog hồi phục sau mitigation?
22. Postmortem phải nêu đâu là trigger, đâu là contributing factors?
23. Cần những integration tests nào để ngăn sự cố tái diễn?
24. Cần alert mới nào để phát hiện DLT storm sớm hơn?
25. Nếu cùng incident xảy ra khi consumer dùng `@RetryableTopic`, những khác biệt nào về offset và ordering cần điều tra?

## 29. Mẫu báo cáo incident cần nộp

Người học nên tạo một báo cáo có thể copy vào hệ thống incident management.

### 29.1. Executive summary

```text
Incident ID: LAB-KAFKA-20261116-01
Severity: [SEV level theo chính sách lab]
Start: 09:04
Detected: 09:07
Mitigation start: 09:16
Service: order-projection
Group: order-projection
Source topic: orders.events
DLT topic: orders.events.DLT

Summary:
  [Mô tả 2–4 câu: hệ thống nào, khách hàng nào,
   tác động gì, vì sao cần khôi phục]
```

### 29.2. Timeline

| Thời điểm | Evidence | Hành động/quan sát | Owner |
| --- | --- | --- | --- |
| 09:00 | Canary deploy log | v1.9.0 join group | Release owner |
| 09:04 | InvalidOrderEventException | DLT bắt đầu tăng | On-call |
| 09:07 | Hikari pool metrics | Connection timeout tăng | DBA |
| 09:10 | Rebalance/lag | Có chuyển quyền P3 | Kafka owner |
| 09:16 | Mitigation record | Canary dừng, DB pressure được xử lý | IC |
| 09:32 | Lag/throughput metrics | Backlog gần được xử lý | On-call |
| 09:40 | Business reconciliation | Còn DLT cases chưa giải quyết | Business owner |

Đây là mốc gợi ý từ bộ dữ liệu giả lập; nếu người học thực hiện lab thật, thay bằng thời gian và evidence thực tế.

### 29.3. Impact assessment

Phải ghi:

- Số event IDs trong cửa sổ ảnh hưởng.
- Số event IDs đã xử lý thành công.
- Số event IDs nằm ở DLT, phân loại theo lỗi.
- Số event pending/unknown và phương pháp xác định.
- Số order/khách hàng có trạng thái bị chậm hoặc sai.
- Số business side effects trùng đã được xác nhận (nếu có).
- Thời gian service xử lý dưới SLO và thời gian backlog drain.

Nếu chưa đủ dữ liệu, viết `unknown, đang đối soát` thay vì bịa ra con số.

### 29.4. Root cause và contributing factors

Cấu trúc:

```text
Trigger:
  [Sự kiện khởi phát có bằng chứng]

Direct causes:
  [Ví dụ parser không hỗ trợ enum mới, connection timeout]

Contributing factors:
  [Ví dụ retry-to-DLT policy cho DB outage,
   thiếu canary coverage gate, thiếu timeout]

Detection gap:
  [Ví dụ chỉ alert lag, không alert DLT rate theo exception]

Recovery gap:
  [Ví dụ DLT chưa có owner và runbook replay]

What went well:
  [Các bước giúp giảm impact]

What to improve:
  [Các thay đổi có chủ sở hữu và thời hạn]
```

Không quy lỗi cho một cá nhân chỉ vì họ thực hiện deployment. Postmortem cần tập trung vào cơ chế hệ thống, guardrails và quyết định dựa trên thông tin lúc đó.

### 29.5. Action items

| Action | Loại | Ưu tiên | Owner | Bằng chứng hoàn thành |
| --- | --- | --- | --- | --- |
| Thêm test enum/status compatibility | Prevention | High | Application team | Integration test pass trên corpus |
| Tách policy DB outage khỏi poison DLT | Prevention | High | Kafka team | Failure-mode test và runbook |
| Alert DLT rate theo exception class | Detection | High | SRE | Alert test có tín hiệu |
| Bổ sung business reconciliation | Detection | High | Data/Backend | Dashboard theo eventId |
| Test canary nhận workload đại diện | Deployment | Medium | Release team | Canary gate có exposure |
| Test process crash giữa DB/offset commit | Reliability | Medium | QA/SRE | Test lab có redelivery và idempotency |
| Tạo DLT replay workflow có approval | Recovery | High | Operations | Replay lab có audit |
| Tuning DB connection acquisition/SQL | Capacity | Theo evidence | DBA | Metrics sau load test |

Mỗi action cần owner rõ, thời hạn và tiêu chí xác minh; đừng chỉ ghi “cải thiện monitoring”.

## 30. Thang đánh giá bài tập

Tổng 100 điểm:

| Tiêu chí | Điểm tối đa | Yêu cầu |
| --- | ---: | --- |
| Chẩn đoán từ nhiều nguồn | 20 | Dùng Kafka, DB, app, release và business metrics; không kết luận quá sớm |
| Phân loại nguyên nhân | 15 | Tách lỗi schema, DB, retry/DLT và rebalance |
| Mitigation an toàn | 15 | Có rollback/circuit breaker, không reset offset tùy tiện |
| Data correctness | 15 | Phân biệt lag, DLT, replay, duplicate delivery và side effect |
| Recovery và replay | 15 | Có approval, rate limit, idempotency, đối soát outcome |
| Kiểm thử độ tin cậy | 10 | Coverage retry, DLT failure, crash/rebalance |
| Giao tiếp và postmortem | 10 | Timeline, impact, owner, action items, evidence |

**Điều kiện bắt buộc để đạt:** không đưa ra phương án có thể làm mất âm thầm record, không xóa metadata hoặc reset group offsets bừa bãi, và không tuyên bố phục hồi chỉ dựa trên pod readiness/consumer lag.

Không phải câu trả lời nào cũng cần lựa chọn mitigation giống nhau. Điểm đánh giá nằm ở cách sử dụng evidence, kiểm soát rủi ro, đo tác động và xác nhận kết quả.

## 31. Gợi ý hướng giải cho tình huống mô phỏng

Phần này là hướng tham khảo sau khi người học đã tự thực hiện triage.

### 31.1. Các vấn đề nổi bật

Từ evidence:

- Canary v1.9.0 được assign P3 và gặp lỗi unknown status ở record cụ thể, gợi ý vấn đề schema compatibility.
- Stable cũng gặp DB connection timeout, nên sự cố DB không chỉ giới hạn ở canary.
- DLT tăng mạnh cùng lỗi JDBC transient, cho thấy chính sách retry cạn rồi DLT có thể biến outage ngắn thành backlog cách ly lớn.
- Rebalance và duplicate suppression là dấu hiệu cần đối soát; chúng chưa chứng minh mất dữ liệu hoặc side effect trùng.
- Lag giảm sau mitigation là tín hiệu hệ thống tiến triển, nhưng DLT tồn đọng cần quy trình riêng.

### 31.2. Hướng xử lý hợp lý

1. Mở incident, phân vai, xác nhận phạm vi và lưu baseline.
2. Thu thập group assignment, per-partition lag, canary/stable errors và DB metrics.
3. Chặn mở rộng canary; cân nhắc dừng canary vì có evidence lỗi schema riêng.
4. Giảm áp lực lên DB theo nguyên nhân thực (query/connection/throughput), không chỉ tăng pool vô điều kiện.
5. Ngăn DLT storm do DB outage theo chính sách nghiệp vụ, giữ record chưa xử lý để retry/resume sau khi backend ổn định.
6. Chờ group ổn định; xác minh business throughput và lag thực sự hồi phục.
7. Phân nhóm DLT thành schema failure và DB outage, kiểm tra marker trước replay.
8. Replay có giới hạn sau khi đã sửa parser/schema và DB, đối soát business outcome.
9. Chỉ đóng incident khi dữ liệu và SLO đạt ngưỡng đã thống nhất, các case chưa giải quyết có owner/plan rõ.
10. Tạo action items: compatibility tests, retry policy, DLT alert, crash-window test, business reconciliation.

Không thể xác nhận riêng từ bảng giả lập liệu canary đã trực tiếp gây DB pool exhaustion hay một query/sự cố DB khác xảy ra đồng thời. **Điều đó phải được đánh dấu là chưa xác định nếu chưa có SQL traces hoặc DB evidence bổ sung.**

### 31.3. Điều không nên làm

- Tăng `retryLimit` lên vô hạn với hy vọng DB tự phục hồi.
- Đánh dấu incident xong khi lag bằng 0 nhưng DLT còn hàng nghìn records.
- Dùng `kubectl delete pod` liên tục để “tăng tốc rebalance”.
- Reset source group offsets về earliest mà không có kế hoạch idempotency/reconciliation.
- Xóa DLT topic vì cho rằng mọi record là “lỗi kỹ thuật không cần quan tâm”.
- Thay toàn bộ consumer sang v1.9.0 khi canary mới xử lý một partition và đang lỗi.
- Giả định `@KafkaListener` trả về thành công đồng nghĩa HTTP/email/DB side effect đã được đảm bảo exactly-once.
- Tăng Hikari pool size vượt quá khả năng DB mà không đo.
- Tuyên bố “không có duplicate” chỉ vì marker table không có khóa trùng, nếu còn những side effect ngoài database.

## 32. Biến thể nâng cao cho nhóm SRE/Backend

Khi nhóm đã làm xong kịch bản cơ bản, có thể mở rộng theo những dạng failure thường gặp.

### Biến thể A — DLT publish bị từ chối

Đổi quyền WRITE của DLT trong **môi trường lab**, cho recoverer gặp `TopicAuthorizationException`. Yêu cầu người học chứng minh source record không bị đánh dấu xử lý thành công một cách giả và có alert đúng.

### Biến thể B — Broker coordinator thay đổi

Trong lab có nhiều broker, mô phỏng coordinator disruption theo công cụ test được hỗ trợ. Quan sát rebalance, thời gian ổn định, member ownership và redelivery. Không kiểm chứng hành vi cluster bằng một broker embedded rồi suy rộng thành HA của production.

### Biến thể C — HTTP downstream có timeout nhưng request đã thực hiện

Handler gọi API cập nhật trạng thái đơn hàng. API đã commit nhưng response timeout; Kafka consumer retry. Yêu cầu dùng idempotency key ở API và đối soát trạng thái bên đích, không chỉ marker database local.

### Biến thể D — Non-blocking retry làm đảo thứ tự

Thay `DefaultErrorHandler` bằng retry topic. Event version 5 bị retry, version 6 được xử lý trước. Yêu cầu thiết kế version guard hoặc cơ chế per-key ordering phù hợp.

### Biến thể E — Hot partition

Một partition nhận 80% tổng messages trong khi ba partition còn lại ít tải. Canary nhận hot partition và xử lý chậm, mặc dù số partition assignment nhìn có vẻ cân bằng. Yêu cầu đánh giá partition skew và không so sánh stable/canary chỉ theo pod count.

### Biến thể F — Static membership trùng group.instance.id

Tạo hai consumer trong lab cùng một static member ID. Quan sát fencing/rebalance theo group protocol/assignor thực tế, rồi sửa cách tạo identity ổn định, duy nhất theo consumer instance.

### Biến thể G — DLT chứa dữ liệu nhạy cảm

Thêm trường PII trong event, yêu cầu đưa ra phương án giữ bằng chứng lỗi mà không gửi payload thô vào log/email, có ACL, retention và truy cập có audit.

### Biến thể H — Producer outbox và replay

Upstream sử dụng outbox. So sánh danh sách event IDs ở outbox với những event đã tiêu thụ, nằm ở DLT hoặc đang pending; tính impact chính xác hơn thay vì dùng log-end offsets như số event nghiệp vụ.

## 33. Checklist kết thúc diễn tập

Trước khi xem bài là hoàn tất, xác nhận:

- [ ] Có timeline từ khi phát hiện đến khi ổn định.
- [ ] Có phân biệt lỗi schema, lỗi database, retry/DLT policy và rebalance.
- [ ] Có ít nhất một giả thuyết được kiểm chứng hoặc bác bỏ bằng evidence.
- [ ] Không thực hiện thao tác thay đổi offset/topic/database production để thử nghiệm.
- [ ] Có bản ghi rõ các quyết định mitigation, người thực hiện và đường rollback.
- [ ] Có chứng minh consumer group tiến triển sau khi ổn định assignment.
- [ ] Có đối chiếu DLT cases và event IDs, không chỉ báo cáo lag.
- [ ] Có kiểm tra tác động lặp ở DB và các hệ thống ngoài (nếu có).
- [ ] Có quy trình replay DLT được kiểm soát và audit.
- [ ] Có test hoặc đề xuất test cho lỗi DLT publish, crash-window và unknown status.
- [ ] Có report impact với số liệu và định nghĩa mẫu số rõ ràng.
- [ ] Có action items kèm owner, priority và điều kiện hoàn thành.
- [ ] Có ghi rõ những gì chưa xác định, thay vì giả định đã tìm đủ root cause.
- [ ] Có thống nhất điều kiện đóng incident với business owner/on-call.

Checklist giúp người học tự kiểm tra phạm vi thực hành; nó không thay cho việc xác minh đúng thực tế của từng tổ chức.

## 34. Tổng kết

**Xử lý incident tổng hợp trong Spring Kafka** là bài toán kết nối nhiều lớp: producer, broker, consumer group, assignment/rebalance, retry, DLT, offset commit, database transaction, idempotency, deployment và kết quả nghiệp vụ. Một tín hiệu đơn lẻ có thể đánh lừa: consumer lag giảm không có nghĩa mọi event đã được áp dụng; pod Ready không có nghĩa listener đang tiến triển; DLT publish thành công không có nghĩa nghiệp vụ thành công.

Trong tình huống mô phỏng, canary làm lộ lỗi tương thích dữ liệu, database pool bị quá tải, retry policy đẩy quá nhiều lỗi hạ tầng sang DLT và rebalance dẫn đến khả năng redelivery. Hướng phục hồi phải cân bằng **giảm tác động ngay**, **bảo vệ dữ liệu khỏi mất/trùng**, **giữ bằng chứng để điều tra**, và **đối soát sau khi xử lý DLT**. Không nên chữa sự cố bằng cách tăng retry vô hạn, reset offset bừa bãi hoặc bỏ qua DLT backlog.

Thói quen cần rèn luyện là: **phát hiện → khoanh vùng → thu thập evidence → phân loại failure → mitigation có thể rollback → xác minh tiến độ → phục hồi/replay → đối soát nghiệp vụ → postmortem và test hồi quy**. Khi mỗi bước có bằng chứng cụ thể và một người chịu trách nhiệm, hệ thống Spring Kafka có thể vượt qua các sự cố nhiều nguyên nhân mà vẫn duy trì độ tin cậy của dữ liệu.
