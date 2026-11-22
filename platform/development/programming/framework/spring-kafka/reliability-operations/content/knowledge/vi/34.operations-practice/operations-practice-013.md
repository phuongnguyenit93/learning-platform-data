# Checklist production readiness cho Spring Kafka

Một hệ thống dùng Spring Kafka có thể hoạt động tốt trên máy phát triển nhưng vẫn gặp sự cố ngay sau khi đưa lên production: producer không ghi được vào topic vì thiếu ACL, consumer tăng lag khi một Pod được thay thế, message bị xử lý hai lần sau rebalance, retry topic chưa được provision, hoặc DLT nhận lỗi mà không có ai xử lý. **Production readiness** là mức độ sẵn sàng **về thiết kế, kiểm chứng kỹ thuật, giám sát và quy trình vận hành**, không chỉ là khả năng ứng dụng khởi động thành công.

Đây là bài **“Checklist production readiness”** thuộc **Spring Kafka Reliability Operations → Thực hành vận hành**. Nội dung là một tài liệu có thể dùng cho buổi review trước go-live, cùng với hướng dẫn cách thu thập bằng chứng, xác định điều kiện **GO/NO-GO**, kiểm thử tình huống lỗi và chuẩn bị runbook khi sự cố xảy ra.

> **Nguyên tắc chấp nhận:** Một mục checklist chỉ được đánh dấu `PASS` khi có **bằng chứng ở môi trường đủ đại diện**, người chịu trách nhiệm và điều kiện chấp nhận rõ ràng. `Ứng dụng chạy không lỗi trong 10 phút` không phải bằng chứng rằng message không bị mất hoặc nhân đôi khi một broker, consumer hoặc database gặp sự cố.

## 1. Mục tiêu, phạm vi và nguyên tắc đánh giá

Một hệ thống Kafka production cần trả lời được những câu hỏi tối thiểu:

1. **Nhận dữ liệu:** Producer có ghi được message với độ bền theo SLA, bao gồm lúc broker thay leader?
2. **Xử lý dữ liệu:** Consumer có commit offset đúng sau khi hoàn tất side effect nghiệp vụ?
3. **Gặp lỗi:** Record nào được retry, record nào vào DLT, ai là người xử lý và có mất record lúc forwarding lỗi không?
4. **Chạy lại:** Khi process chết, rebalance hoặc message bị giao lại, business effect có còn chính xác không?
5. **Vận hành:** Có dashboard, cảnh báo, on-call, runbook và cách biết backlog có kịp xử lý trước retention không?
6. **Bảo mật:** App và automation có đúng quyền topic/group/transactional ID, không lộ secret và không làm sai tenant isolation?
7. **Thay đổi:** Có thể rolling deploy, scale, nâng client/broker và rollback mà không làm mất backlog hay phá payload compatibility?

### 1.1. Đối tượng cần review

```text
               Ingress / Business API
                         |
                         v
                Producer / Outbox
                         |
                         v
                Main Kafka topics
                         |
          +--------------+---------------+
          |                              |
          v                              v
    Spring Kafka consumer          Consumer group khác
          |
       Business DB / API
          |
     +----+----------+
     |               |
  Success      Error handling
                     |
          +----------+----------+
          |                     |
      Retry path               DLT
          |                     |
    Backoff / retry        Review / replay
          |
     Success / DLT

Cross-cutting: IAM/ACL, schema, capacity, observability,
deployment, incident response, backup và rollback.
```

Nếu hệ thống chỉ có producer, bỏ qua các mục consumer **có lý do ghi nhận**. Nếu dùng Kafka Streams hoặc Connect, cần thêm checklist riêng về internal topics, changelog, task restart, connector offsets và state restoration. Không đánh dấu `PASS` một mục ngoài phạm vi; dùng `N/A` kèm giải thích.

### 1.2. Mức độ quyết định

| Kết quả | Ý nghĩa | Quyết định |
| --- | --- | --- |
| `PASS` | Có bằng chứng đáp ứng tiêu chí đã thỏa thuận | Có thể tiếp tục review |
| `FAIL` | Tiêu chí không đạt; có failure path chưa được kiểm soát | Sửa và kiểm tra lại |
| `NOT_TESTED` | Chưa có bằng chứng hoặc test chưa chạy trong môi trường phù hợp | Không coi là đạt |
| `N/A` | Hạng mục không thuộc kiến trúc, có lý do và owner xác nhận | Không chặn nếu được chấp thuận |
| `RISK_ACCEPTED` | Có sai lệch đã lượng hóa, được người có thẩm quyền phê duyệt, có biện pháp bù và thời hạn | Chỉ cho phép nếu chính sách tổ chức chấp nhận |

**GO** khi mọi hạng mục mức chặn phát hành đều `PASS` hoặc có ngoại lệ được phê duyệt theo đúng quy trình, các cảnh báo quan trọng đang hoạt động và rollback có thể thực hiện. **NO-GO** nếu còn rủi ro mất dữ liệu chưa hiểu, retry/DLT không hoạt động, thiếu quyền truy cập production, không kiểm chứng được idempotency hoặc không có phương án phục hồi.

## 2. Phiếu thông tin trước khi bắt đầu review

Trước khi đánh dấu checklist, điền một phiếu có cùng phạm vi với bản release:

| Trường | Giá trị minh họa | Tại sao cần |
| --- | --- | --- |
| Service / Release | `orders-worker` / `1.14.0` | Xác định image/code được kiểm tra |
| Spring Boot / Spring Kafka | Boot 3.x / Spring Kafka 3.x | Giới hạn tương thích API và behavior |
| Kafka Java client | Version từ `runtimeClasspath` | Bản thực sự đang chạy, không chỉ version khai báo |
| Kafka cluster | `kafka-prod-a` | Broker, region, quorum và policy |
| Topics chính | `orders.events` | Danh sách input/output có chủ sở hữu |
| Retry/DLT | `orders.events-retry-*`, `orders.events-dlt` | Nhận diện toàn bộ pipeline lỗi |
| Consumer group | `orders-service` | Định danh offset và assignment |
| Business key | `tenantId + orderId + eventVersion` | Định nghĩa tính duy nhất nghiệp vụ |
| SLA/SLO | Ví dụ: 99,9% hợp lệ được xử lý trong 5 phút | Chuyển thành ngưỡng đo và cảnh báo |
| Môi trường kiểm chứng | Staging Kafka tương tự production | Đánh giá độ tin cậy của test |
| Deployment strategy | Rolling 1 Pod/lượt | Hiểu tác động rebalance |
| Người chịu trách nhiệm | App owner, Kafka platform, Security, On-call | Không bỏ trống khoảng giao trách nhiệm |
| Rollback target | Image release trước và config tương thích | Tránh rollback code nhưng phá schema |

SLO ở đây là **ví dụ**, không phải ngưỡng do Spring Kafka quy định. Khi tính SLA, cần định nghĩa rõ mẫu số: tất cả messages nhận vào, chỉ messages hợp lệ, hay messages đã được producer ack? Định nghĩa đó ảnh hưởng trực tiếp đến dashboard và cách tính thành công.

### 2.1. Ranh giới transaction và ownership

Vẽ rõ tác động Kafka và dữ liệu nghiệp vụ:

```text
Kafka record
   |
   v
@KafkaListener
   |
   +--> validate / deserialize
   |
   +--> BusinessService @Transactional
   |          |
   |          v
   |       Database commit
   |
   +--> callback kết thúc thành công
   |
   v
Container commit Kafka offset theo AckMode
```

Với sơ đồ này, database commit và Kafka offset commit **không phải một transaction nguyên tử**. Nếu process chết ở giữa, record có thể được giao lại. Vì vậy idempotent business effect là yêu cầu cốt lõi. Đừng ghi trên tài liệu rằng `AckMode.RECORD` tự bảo đảm exactly-once đối với database bên ngoài.

## 3. Checklist nhanh cho buổi GO/NO-GO

Đây là bảng điều hành ngắn. Các phần sau giải thích tiêu chí và ví dụ kiểm chứng.

| Mã | Cổng kiểm soát | Điều kiện chặn go-live | Owner thường gặp |
| --- | --- | --- | --- |
| `G01` | Hợp đồng event và idempotency | Chưa định nghĩa business key, version, replay và xử lý trùng | App / Domain |
| `G02` | Kafka topics | Thiếu topic, partition, retention hoặc replication theo SLA | Kafka Platform |
| `G03` | Producer durability | Không thử leader restart, thiếu `acks`/idempotence hoặc không xử lý publish failure | App / Platform |
| `G04` | Consumer offset & failure | Offset có thể commit trước business success hoặc không xử lý poison message | App |
| `G05` | Retry & DLT | Retry topics/DLT/ACL thiếu hoặc forwarding lỗi nhưng record vẫn bị coi là xử lý xong | App / Platform |
| `G06` | Security | Principal quyền quá rộng, secret không được bảo vệ hoặc TLS/auth thất bại | Security / Platform |
| `G07` | Observability | Thiếu metric lag, error, retry/DLT; alert không đến on-call | SRE / App |
| `G08` | Capacity & resilience | Chưa có load test, rebalance/crash/scale test, backlog không có giới hạn | App / SRE |
| `G09` | Deployment & rollback | Không có image pin, canary gate hoặc rollback plan cho schema/topic changes | Release owner |
| `G10` | Runbook & ownership | Không rõ ai xử lý DLT, offset reset, incident và backfill | On-call / Domain |

Một mục `G01`–`G10` chưa có evidence thường nên được coi là **NO-GO** cho luồng nghiệp vụ quan trọng. Điều chỉnh mức chặn theo mức độ rủi ro và quy định tổ chức, không giảm mức chỉ vì gần tới giờ release.

## 4. Checklist hợp đồng dữ liệu và schema

Kafka broker lưu record theo bytes; tính đúng nghiệp vụ nằm ở schema và cách producer/consumer diễn giải bytes đó. Một rollout có thể không làm broker lỗi nhưng vẫn phá consumer vì thay payload.

### 4.1. Những điều phải đạt

- [ ] **Topic ownership rõ ràng:** topic có owner nghiệp vụ, owner vận hành, phân loại dữ liệu và SLA.
- [ ] **Event identity ổn định:** có `eventId`/business key không thay đổi giữa các lần publish lại cùng logical event.
- [ ] **Event version có ý nghĩa:** phân biệt thay đổi trạng thái với bản ghi trùng, xử lý đúng thứ tự update.
- [ ] **Message key được lựa chọn có chủ đích:** các events cần thứ tự cùng entity được route tới partition theo key phù hợp.
- [ ] **Schema evolution được thử hai chiều khi cần:** consumer cũ đọc dữ liệu mới và consumer mới đọc dữ liệu cũ theo hợp đồng rollout.
- [ ] **Không làm lộ PII/secret:** chỉ trường cần thiết được publish; masking/encryption và retention phù hợp.
- [ ] **Giới hạn kích thước record:** payload không vượt broker/topic/producer limits; có chiến lược external blob reference khi dữ liệu lớn.
- [ ] **Tương thích serializer:** key/value serializer, deserializer, headers, Schema Registry và subject naming được kiểm chứng.
- [ ] **Poison payload có đường xử lý:** deserialization failure không làm consumer lặp vô hạn không quan sát được.
- [ ] **Reprocess contract được định nghĩa:** gửi lại cùng event có tạo effect mới không, và version/source nào được chọn?

### 4.2. Ví dụ thay schema cần chuẩn bị

Payload cũ:

```json
{
  "eventId": "ev-301",
  "orderId": "O-301",
  "amount": 1200
}
```

Payload mới:

```json
{
  "eventId": "ev-301",
  "orderId": "O-301",
  "amount": 1200,
  "currency": "VND",
  "eventVersion": 2
}
```

Thêm field mới có thể tương thích nếu consumer cũ bỏ qua field lạ và consumer mới có default phù hợp. Nhưng điều đó phụ thuộc serializer/parser và schema rules; **không mặc định mọi JSON consumer đều bỏ qua unknown properties**. Với Avro/Protobuf/JSON Schema, dùng compatibility policy của Schema Registry và fixture từ release cũ.

Ví dụ test cần có: đọc payload cũ bằng consumer mới, đọc payload mới bằng consumer cũ (nếu giai đoạn mixed version yêu cầu), và kiểm thử record sai cấu trúc thực sự được đưa vào cơ chế lỗi phù hợp.

## 5. Checklist Kafka cluster, topics và capacity

Một ứng dụng đúng code nhưng dùng topic replication factor 1 hoặc retention quá ngắn vẫn có thể mất dữ liệu khi gặp lỗi.

### 5.1. Topic provisioning

- [ ] Topic chính, retry topics và DLT đã tồn tại trước deployment nếu production không cho auto-create.
- [ ] Partition count đáp ứng **mức song song mong muốn** nhưng không tăng vô hạn gây metadata overhead.
- [ ] Replication factor phù hợp khả năng cluster và dữ liệu/SLA (ví dụ RF=3 trên cluster đủ brokers, không coi là giá trị bắt buộc cho mọi môi trường).
- [ ] `min.insync.replicas` được chốt với `acks=all`, có chính sách khi ISR giảm.
- [ ] Retention của main/retry/DLT đủ cho downtime, backlog, reprocess và thời gian review.
- [ ] Cleanup policy (`delete`, `compact`, hoặc kết hợp) phù hợp event semantics.
- [ ] Topic config có owner và thay đổi qua IaC/change management; không phụ thuộc broker auto-create ngầm.
- [ ] Retry topic có **đủ partitions cho routing** nếu recoverer giữ nguyên source partition.
- [ ] Topic có quota/ACL phù hợp producer, consumer, reprocess và admin tasks.
- [ ] Cross-region/DR policy được định nghĩa nếu có yêu cầu phục hồi thảm họa.

### 5.2. Kiểm tra cơ bản bằng CLI

Các lệnh dưới đây dành cho người vận hành trên môi trường được cấp quyền:

```bash
# Tên topic và các brokers/partitions/replicas
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders.events

# Trạng thái consumer group, partition offsets và lag
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service

# Khả năng Kafka API mà brokers công bố
kafka-broker-api-versions.sh \
  --bootstrap-server broker1:9092
```

Với SASL_SSL/mTLS, bổ sung `--command-config` trỏ tới cấu hình CLI đã được bảo mật. **Không đưa password vào câu lệnh/log/ticket** nếu môi trường không cho phép. Một bootstrap server kết nối được chưa chứng minh client có thể tới mọi broker qua `advertised.listeners`; cần thử các partition leaders và kiểm tra mạng/cert tương ứng.

### 5.3. Năng lực xử lý và backlog

Đo hai đại lượng:

- **Input rate**: số messages/s hoặc bytes/s thực tế ở tải bình thường và tải đỉnh.
- **Processing throughput**: số messages/s consumer xử lý **thành công** sau side effect và offset strategy, không chỉ poll count.

Nếu tốc độ input kéo dài vượt throughput, consumer lag sẽ tăng dù cluster chưa báo lỗi. Đánh giá thêm **thời gian drain backlog**, đủ thời gian trước khi topic retention xóa dữ liệu cũ.

Ví dụ minh họa:

```text
Input rate cao điểm      = 5.000 messages/s
Consumer capacity        = 6.000 messages/s
Backlog sau downtime     = 3.600.000 messages

Capacity dành cho drain  = 1.000 messages/s
Thời gian drain ước tính = 3.600 giây ≈ 1 giờ
```

Đây là **ước lượng lý tưởng**, chưa tính retry/DLT, rebalances, warm-up, DB limits và throughput giảm khi queue lớn. Trong capacity test, dùng số đo thực tế theo payload distribution, partition skew và tình trạng downstream để có buffer an toàn.

### 5.4. Các giới hạn cần đo, không đoán

| Resource | Dấu hiệu quá tải | Gợi ý kiểm chứng |
| --- | --- | --- |
| Broker disk | Disk usage tăng, retention không đủ, I/O latency | Kiểm tra peak throughput và lưu trữ theo SLA |
| Broker network | Produce/fetch latency tăng | Load test với nén/payload thật |
| Partitions | Một partition lag cao dù group có nhiều consumers | Xem key skew, hot partition |
| Consumer CPU/heap | GC pause, processing latency tăng | Profiling và heap/GC metrics |
| Consumer group | Rebalances liên tục, partitions idle | Kiểm tra assignment, poll interval, deploy strategy |
| Database | Pool cạn, deadlock, transaction timeout | Test downstream khi load tăng |
| External API | Rate-limit, timeout và retry storm | Backoff, bulkhead, idempotency, capacity agreement |

## 6. Checklist producer reliability

Producer phải ghi message vào Kafka với semantics rõ ràng: thành công khi nào, lỗi nào retry, khi callback timeout phải làm gì?

### 6.1. Các mục bắt buộc

- [ ] `acks` và durability policy được chọn theo SLA; thường `acks=all` cho dữ liệu quan trọng.
- [ ] `enable.idempotence` được bật hoặc có lý do rõ ràng nếu không dùng.
- [ ] `retries`, `delivery.timeout.ms`, `request.timeout.ms`, `linger.ms` và `batch.size` được kiểm soát, đo tại tải thực.
- [ ] `max.in.flight.requests.per.connection` không xung đột yêu cầu idempotence/ordering.
- [ ] Mọi `KafkaTemplate.send()` có cơ chế **quan sát success/failure**, không fire-and-forget rồi coi là thành công.
- [ ] Record key/event ID ổn định khi ứng dụng phải publish lại một logical event.
- [ ] Không gửi payload trước khi transaction nghiệp vụ cần thiết commit nếu có rủi ro lệch state; cân nhắc transactional outbox.
- [ ] Khi broker leader đổi, producer retry và error handling theo chính sách.
- [ ] Có alert khi publish errors, timeout hoặc backlog outbox tăng.
- [ ] Producer serializer và security principal có quyền ghi tất cả topics liên quan.

### 6.2. Mẫu cấu hình Spring Boot 3.x / Spring Kafka 3.x

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000

    consumer:
      group-id: orders-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest

    listener:
      ack-mode: record
```

Đây là **cấu hình tham khảo**, không phải cấu hình production dùng nguyên xi. Điều chỉnh serializer, retry/transaction, broker addresses, security và thresholds theo SLA. `auto-offset-reset=earliest` chỉ quyết định hành vi khi **group chưa có committed offset hoặc offset không còn hợp lệ** theo chính sách client; nó không ép consumer đọc lại toàn bộ topic mỗi lần restart.

`enable-auto-commit=false` để Spring Kafka container quản lý commit theo acknowledgment mode. `AckMode.RECORD` phù hợp cho ví dụ record listener không dùng container transactions; với manual ack hoặc Kafka transactions, thiết kế commit semantics khác.

Producer idempotence là một bảo vệ ở phạm vi Kafka producer protocol; nó **không tự deduplicate hai logical `send()` độc lập** nếu ứng dụng retry publish bằng event mới sau timeout. Để bảo đảm nghiệp vụ, cần stable event identity ở tầng ứng dụng.

### 6.3. Mẫu publish có quan sát lỗi

```java
package com.example.kafka;

import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> template;

    public OrderEventPublisher(KafkaTemplate<String, String> template) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String eventId, String payload) {
        return template.send("orders.events", eventId, payload);
    }
}
```

Caller cần xử lý `CompletableFuture`:

```java
publisher.publish(eventId, payload)
    .whenComplete((result, error) -> {
        if (error != null) {
            // Record publish failure, alert/retry theo event ID ổn định.
        } else {
            // Kafka đã acknowledge theo producer config.
        }
    });
```

Trong Spring Kafka 3.x, `KafkaTemplate.send` trả `CompletableFuture`; nếu dự án còn Spring Kafka 2.x, API có khác biệt. **Không đổi KafkaTemplate version chỉ để copy ví dụ** mà bỏ qua compatibility với Spring Boot, JDK và broker.

Callback thành công nghĩa là broker đã ack theo producer config, **không** chứng minh consumer nghiệp vụ đã xử lý xong. Nên lưu eventId và thông tin publish để đối soát.

### 6.4. Database → Kafka: cân nhắc outbox

Nếu một API vừa ghi order vào database vừa publish event:

```text
Business transaction:
  UPDATE orders
  INSERT outbox(event_id, payload, status=PENDING)
  COMMIT

Outbox publisher:
  read pending
  publish Kafka event
  mark published (có retry)

Consumer:
  dedup event_id/business key
  apply side effect idempotently
```

Outbox tránh trường hợp database đã commit nhưng process chết trước khi kịp gọi `send`. Tuy nhiên publisher có thể gửi lại event khi mất response/mark status thất bại. **Outbox là mô hình at-least-once publish**, nên consumer vẫn phải chống xử lý trùng. Không quảng bá outbox như chứng minh exactly-once end-to-end không cần dedup.

## 7. Checklist consumer và offset correctness

Consumer cần cam kết rõ **khi nào một message được coi là xử lý thành công**. Nếu commit offset trước khi business transaction hoàn tất, có thể mất tác động nghiệp vụ. Nếu business transaction commit trước offset, crash có thể dẫn tới message được giao lại.

### 7.1. Những mục phải xác nhận

- [ ] `group.id` ổn định qua rolling deployment; thay group chỉ khi có migration/backfill chủ đích.
- [ ] `auto-offset-reset` đúng policy khi group chưa có committed offsets.
- [ ] `enable-auto-commit` và Spring Kafka `AckMode` được kiểm soát, không có hai nơi cùng quản lý offset sai kỳ vọng.
- [ ] Listener chỉ trả thành công/ack **sau khi** business effect cần thiết đã được commit.
- [ ] Handler có idempotency để chịu được replay khi DB đã commit nhưng Kafka offset chưa commit.
- [ ] Deserialization errors đi vào error handler/recovery path có kiểm soát, không kẹt vô hạn.
- [ ] Error classification phân biệt lỗi tạm thời, payload sai, lỗi code và lỗi hạ tầng.
- [ ] `max.poll.interval.ms`, `max.poll.records`, thời gian xử lý và concurrency được đo cùng nhau.
- [ ] Consumer không block vô hạn trên downstream; có timeout/circuit breaker/bulkhead phù hợp.
- [ ] Rebalance callbacks và shutdown không làm mất in-flight business state.
- [ ] Listener container startup/shutdown semantics đã được kiểm thử khi Pod restart.
- [ ] Khi pause/resume, team phân biệt requested state và actual paused state.
- [ ] Không dùng `autoStartup=false` hoặc pause state cục bộ mà quên điều phối trên các replicas.

### 7.2. Offset: cách hiểu đúng

```text
Partition orders.events-0
Offset:        100 101 102 103 104

Handler đã xử lý qua record 101
Committed offset = 102  (offset của record tiếp theo)
```

Kafka committed offset thường là **vị trí tiếp theo cần đọc**. Một record nhận được qua listener chưa chắc đã commit. Nếu process bị kill sau khi xử lý 101 nhưng trước khi commit offset 102, record 101 có thể được giao lại. Đây là đặc tính phải test, không phải tự động là bug của Kafka.

### 7.3. Thời gian xử lý và `max.poll.interval.ms`

Nếu listener mất quá lâu trước khi consumer quay lại poll loop, consumer có thể bị coi là không đáp ứng, gây rebalance và replay. Đặt `max.poll.interval.ms` lớn hơn một cách vô hạn chỉ che triệu chứng; cần đo throughput và xác định nguyên nhân: DB lock, external API timeout, quá nhiều records/poll hoặc CPU/GC.

Các điều chỉnh cần đánh giá cùng nhau:

| Thuộc tính | Tác động | Rủi ro khi chỉnh sai |
| --- | --- | --- |
| `max.poll.records` | Số record tối đa được trả về trong một poll | Poll quá lớn, callback chậm và rebalance |
| `max.poll.interval.ms` | Giới hạn khoảng thời gian giữa hai poll | Quá ngắn gây rebalance; quá dài làm phát hiện process kẹt chậm |
| `session.timeout.ms` | Phát hiện mất consumer theo group protocol | Không đồng nghĩa thời gian business handler được phép chạy |
| `heartbeat.interval.ms` | Nhịp heartbeat với classic protocol | Phải phù hợp broker/client protocol; không áp dụng máy móc cho group protocol mới |
| `concurrency` | Nhiều consumer threads/containers | Không tăng throughput nếu số partitions ít hoặc DB đã chạm trần |
| `ack-mode` | Khi nào container commit offset | Sai contract có thể gây replay hoặc mất effect |

Với các Kafka releases mới, **consumer group protocol classic và protocol mới** có cấu hình heartbeat/session khác nhau. Chỉ áp dụng các property tương ứng đúng mode/broker/client version.

## 8. Idempotency và ranh giới transaction

Đây thường là hạng mục quyết định có được go-live với dữ liệu quan trọng hay không.

### 8.1. Tình huống phải chịu được

```text
Consumer nhận eventId=ev-101
        |
        v
Ghi business DB thành công
        |
        v
Process chết trước Kafka offset commit
        |
        v
Consumer mới nhận lại ev-101
        |
        v
Business effect phải không bị nhân đôi
```

`@Transactional` trên service xử lý database giúp rollback các thay đổi DB cùng transaction, nhưng **không ràng buộc nguyên tử Kafka offset** nếu không thiết kế giao dịch liên quan. Ngoài ra, side effect HTTP/email ở ngoài database transaction không được rollback tự động.

### 8.2. Ví dụ PostgreSQL: inbox/dedup trong cùng DB transaction

Schema minh họa:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id       VARCHAR(80) PRIMARY KEY,
    latest_version BIGINT NOT NULL,
    state          VARCHAR(32) NOT NULL
);
```

Business service:

```java
package com.example.kafka;

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
    public void applyOnce(String eventId, String orderId,
                          long version, String state) {

        int inserted = jdbc.update("""
            INSERT INTO processed_event (consumer_name, event_id)
            VALUES ('order-projection', ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """, eventId);

        if (inserted == 0) {
            return; // Cùng event đã được xử lý thành công trước đó.
        }

        jdbc.update("""
            INSERT INTO order_projection(order_id, latest_version, state)
            VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                latest_version = EXCLUDED.latest_version,
                state = EXCLUDED.state
            WHERE order_projection.latest_version < EXCLUDED.latest_version
            """, orderId, version, state);
    }
}
```

Đây là **ví dụ PostgreSQL**, không dùng nguyên SQL cho mọi database dialect. Giả định `eventId` thực sự định danh một logical event, và hai lệnh SQL cùng được quản lý bởi một database transaction. Nếu lệnh ghi projection thất bại, transaction rollback **cả record dedup**, giúp retry không bị coi sai là đã hoàn tất. Đồng thời `latest_version` ngăn event cũ ghi đè trạng thái mới khi non-blocking retries đảo thứ tự.

`ON CONFLICT DO NOTHING` cũng có mặt trái: nếu hai payload khác nhau dùng cùng `eventId`, dữ liệu sai có thể bị che. Với hệ thống yêu cầu audit nghiêm ngặt, lưu thêm checksum/tenant/source, phát cảnh báo khi trùng khóa nhưng khác nội dung thay vì im lặng bỏ qua.

Listener record:

```java
@KafkaListener(
    id = "orderProjectionListener",
    topics = "orders.events",
    groupId = "order-projection"
)
public void handle(String jsonPayload) {
    OrderEvent event = parseAndValidate(jsonPayload);

    projectionService.applyOnce(
        event.eventId(),
        event.orderId(),
        event.version(),
        event.state()
    );
}
```

`OrderEvent`, `parseAndValidate` và `projectionService` là những thành phần ứng dụng cần triển khai; đoạn mã listener này minh họa vị trí transaction boundary. Khi `AckMode.RECORD` được cấu hình, container ghi nhận việc callback hoàn thành, còn offset commit có thể được Kafka thực hiện sau đó. Nếu commit offset thất bại, idempotency trong business service giúp chịu replay.

**Checklist acceptance cho idempotency:** test cùng `eventId` được gửi hai lần, test process chết sau DB commit trước offset commit và test hai consumer attempt cạnh tranh; output cuối phải đúng theo business key, không chỉ đếm số lần callback.

## 9. Checklist retry, backoff và DLT

Một poison message không được làm consumer xử lý mãi một offset mà không có cảnh báo. Nhưng cũng không nên retry vô hạn một record sai schema vì nó không tự trở thành hợp lệ.

### 9.1. Các lựa chọn

| Cơ chế | Đặc tính | Khi cân nhắc |
| --- | --- | --- |
| Blocking retry trong container | Xử lý lại tại luồng chính với backoff/error handler | Lỗi ngắn, muốn giữ thứ tự partition tốt hơn |
| Non-blocking retry topics | Forward sang retry topic, xử lý sau delay | Downstream tạm thời chậm, muốn giải phóng main consumer |
| DLT | Ghi nhận record không xử lý được theo policy | Cần review/quarantine/reprocess |
| Pause/resume | Tạm dừng nhận thêm record từ partition/container | Bảo trì/downstream overload diện rộng |
| Backfill/replay | Chạy lại tập input sau khi xử lý nguyên nhân | Recovery có chủ đích, cần idempotency và audit |

**Non-blocking retries làm mất bảo đảm thứ tự xử lý xuyên các topics.** Ví dụ `ORDER_CREATED` bị chuyển sang retry, trong khi `ORDER_CANCELLED` được xử lý trên main topic; event CREATED xử lý muộn có thể làm state sai nếu projection không kiểm tra version. Không dùng non-blocking retry cho batch listener hoặc trong cấu hình container transactions không được Spring Kafka hỗ trợ.

### 9.2. Những mục phải đạt

- [ ] Exception được phân loại: transient, permanent/validation, deserialization, code/config, security.
- [ ] Có retry budget: attempts, delays, total timeout, backoff/jitter khi cần.
- [ ] Không retry mãi `NullPointerException`, schema invalid hoặc unauthorized config như lỗi hạ tầng tạm thời.
- [ ] Retry topics và DLT có đúng tên, partitions, retention, replication và quyền produce/consume.
- [ ] Forwarding `KafkaTemplate` serialize đúng cả payload thường và raw bytes của lỗi deserialization (nếu dùng).
- [ ] Có test lỗi forwarding: broker unavailable, ACL denied, serializer mismatch, invalid partition.
- [ ] Không coi record đã “an toàn trong retry” trước khi forward được broker xác nhận theo cơ chế phù hợp.
- [ ] DLT handler hoặc DLT review service có owner, SLA, runbook, retention và dedup.
- [ ] Có quy trình reprocess DLT theo event/business key, không gửi lại bừa bãi tạo side effect trùng.
- [ ] Có metric trên **từng retry stage**, DLT arrival và oldest pending age.
- [ ] Đã test thay đổi retry topic naming giữa hai release mà không bỏ quên backlog cũ.

### 9.3. Cấu hình minh họa với `@RetryableTopic`

Ví dụ Spring Kafka 3.x, listener **theo từng record**:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 2000,
        multiplier = 2.0,
        maxDelay = 8000
    ),
    include = {TemporaryDownstreamException.class},
    exclude = {InvalidOrderException.class},
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    autoCreateTopics = "false"
)
@KafkaListener(
    id = "ordersListener",
    topics = "orders.events",
    groupId = "orders-service"
)
public void onOrder(String eventPayload) {
    orderService.applyIdempotently(eventPayload);
}

@DltHandler
public void onDeadLetter(String eventPayload) {
    quarantineService.saveForReview(eventPayload);
}
```

Các exception/service/import cần được khai báo trong ứng dụng thực. Ví dụ **không phải class Java hoàn chỉnh**; mục đích là minh họa policy. `attempts=4` thường gồm lần xử lý ban đầu và số lần retry còn lại theo non-blocking policy. Với `autoCreateTopics=false`, platform phải tạo đầy đủ topics tương ứng **trước khi deploy**.

Tên retry topics phụ thuộc `topicSuffixingStrategy`, backoff, topic reuse và phiên bản Spring Kafka. Không tự chốt tên `orders.events-retry-0` cho production chỉ dựa trên ví dụ mà không xác nhận topic graph thực tế. Nếu sử dụng transaction, Kafka Streams hoặc batch listener, chọn retry architecture khác phù hợp.

### 9.4. DLT không đồng nghĩa xử lý xong nghiệp vụ

Một event ở DLT thường có trạng thái nghiệp vụ **chưa hoàn thành**. Nên theo dõi:

```text
eventId
sourceTopic / sourcePartition / sourceOffset
originalKey
errorCategory / exceptionClass
firstFailureAt / lastFailureAt / attempts
DLTTopic / DLTOffset
reviewStatus / reviewedBy
reprocessEventId / resolvedAt
```

Đừng chỉ lưu payload raw vào log rồi xóa message khỏi DLT. Payload có thể chứa PII; quarantine cần phân quyền, redaction/encryption và retention được xác nhận với domain owner.

## 10. Checklist bảo mật, danh tính và quyền

Kafka production thường yêu cầu nhiều quyền hơn `READ` trên main topic. Cùng service principal có thể cần `WRITE` vào retry/DLT, đọc từ các group được sinh ra, quyền transactional ID hoặc Schema Registry tùy kiến trúc.

### 10.1. Những mục cần xác nhận

- [ ] TLS/SASL/mTLS/OAuth được cấu hình đúng theo cluster và được kiểm tra bằng image runtime thật.
- [ ] `bootstrap.servers` và mọi advertised broker addresses có thể truy cập; cert hostname verification không bị tắt.
- [ ] Secrets được cấp qua secret manager, workload identity hoặc phương thức được phê duyệt; không có token trong Git/log.
- [ ] Producer principal chỉ `WRITE` đúng topics cần thiết và `DESCRIBE` theo policy.
- [ ] Consumer principal có `READ` main, retry/DLT khi cần, cùng quyền consumer group tương ứng.
- [ ] DLT replay tool có credential riêng, audit và quyền hẹp, không dùng principal quản trị cluster.
- [ ] Transactional producer có quyền trên transactional ID/resource tương ứng.
- [ ] ACL được kiểm tra với **cùng loại identity như production**, không chỉ bằng admin credentials.
- [ ] Access vào Schema Registry/KMS phù hợp payload format và encryption.
- [ ] Event payload và log có data classification, không lộ PII và không gửi nhầm tenant.
- [ ] NetworkPolicy/firewall/egress phù hợp broker advertised endpoints và dependency.
- [ ] Key/cert rotation, revoke và incident response đã được thử hoặc có runbook.

### 10.2. Ma trận quyền gợi ý

| Principal | Topic/Resource | Quyền điển hình | Ghi chú |
| --- | --- | --- | --- |
| API producer | `orders.events` | `WRITE`, có thể `DESCRIBE` | Không cần quyền xóa topic |
| Order consumer | `orders.events` | `READ` + group | Không cần `ALTER` topic |
| Retry forwarding producer | `orders.events-retry-*`, `orders.events-dlt` | `WRITE` | Cần test nhánh lỗi thật |
| Retry consumers | Retry topics + các group tương ứng | `READ` + group | Group IDs có thể được suffix tự động |
| DLT review service | DLT topic + store/quarantine | `READ`, quyền dữ liệu giới hạn | Reprocess phải có approval |
| Provisioning pipeline | Topics và ACL IaC | `CREATE/ALTER/DESCRIBE` khi cần | Không nên cấp vào runtime app |

Quyền thực tế phụ thuộc Kafka broker/distribution/cloud (MSK, Confluent Cloud...) và cơ chế ACL/IAM. Không sao chép nguyên policy giữa các providers mà không xác nhận action/resource mapping.

### 10.3. Một smoke test security thường bị bỏ qua

Khởi động listener thành công **không chứng minh** forwarding sang retry/DLT có quyền. Trong staging:

1. Chạy app với service principal tương đương production.
2. Gửi một record gây lỗi transient.
3. Xác nhận record được forward sang retry destination đúng.
4. Cho lỗi kéo dài để record đến DLT.
5. Xác nhận DLT consumer/quarantine nhận record.
6. Đọc logs để đảm bảo không có `TopicAuthorizationException`, `GroupAuthorizationException` hoặc lỗi serializer bị che.

Đây là test riêng cho **failure path authorization**, không thể thay bằng producer test trên topic chính.

## 11. Checklist deployment, resource và cấu hình Kubernetes

Một ứng dụng consumer có thể tạo tác động trùng khi rolling deploy nếu hai instance xử lý lại những records chưa commit offset. Phải đánh giá readiness/liveness, shutdown, consumer group và capacity cùng nhau.

### 11.1. Các mục cần đạt

- [ ] Container image được pin version/digest và có SBOM/scanning theo policy.
- [ ] Java/JDK, Spring Boot, Spring Kafka và `kafka-clients` runtime versions đã được ghi nhận.
- [ ] Resources requests/limits đủ cho peak load, GC và số consumer threads.
- [ ] Consumer `concurrency` phù hợp partition assignment và downstream concurrency limits.
- [ ] Liveness không kill Pod chỉ vì consumer bị pause có chủ đích hoặc backlog tăng.
- [ ] Readiness thể hiện khả năng phục vụ nghiệp vụ đúng nghĩa; không chỉ kiểm tra process còn chạy.
- [ ] Deployment strategy giới hạn số Pods mất cùng lúc; có `maxUnavailable`/capacity headroom phù hợp.
- [ ] `terminationGracePeriodSeconds` cho phép xử lý/stop in-flight trong tình huống thông thường.
- [ ] Không giả định `SIGTERM` luôn bảo đảm Kafka offset được commit trước khi process kết thúc.
- [ ] Scale-out và scale-in đã được test với rebalance, idempotency và lag recovery.
- [ ] HPA/autoscaling metric dựa vào backlog/capacity phù hợp, không tạo oscillation liên tục.
- [ ] Không có hai consumer instances dùng trùng `group.instance.id` nếu bật static membership.
- [ ] Pod security context, secrets và network policy phù hợp.
- [ ] Có canary rollout và điều kiện dừng phát hành nếu error/lag vượt ngưỡng.

### 11.2. Ví dụ cấu hình deployment Kubernetes

Fragment minh họa:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: orders-worker
          image: registry.example.com/orders-worker:1.14.0
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
          env:
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: orders-worker-config
                  key: bootstrapServers
```

Đây không phải manifest đầy đủ cho production: còn cần service account, image pull policy, security context, secrets, probes và các biến ứng dụng thực. Các giá trị `replicas`, memory, CPU và `terminationGracePeriodSeconds` chỉ là **ví dụ**; phải dựa trên load test, pod startup, thời gian xử lý record dài nhất và SLA.

**Không dùng liveness probe khiến một consumer bị kill chỉ vì DLT backlog hoặc downstream pause.** Health cần phân biệt `process alive`, `Kafka connection`, `business readiness` và `processing lag`; có thể phát cảnh báo mà không làm Pod restart liên tục.

### 11.3. Graceful shutdown cần chứng minh bằng test

```text
Kubernetes gửi SIGTERM
       |
       v
Spring context shutdown / Kafka listener container stop
       |
       v
Hoàn tất hoặc giải phóng phần đang xử lý theo timeout
       |
       v
Commit offset theo contract khi xử lý thành công
       |
       v
Consumer rời group / partitions được reassigned
```

Nếu Pod bị kill vì hết grace period hoặc OOM, record xử lý dở có thể bị giao lại. **Đây là lý do phải test idempotency**, không phải lý do nên tăng thời gian grace period vô hạn.

## 12. Checklist observability và cảnh báo

Hệ thống production cần phân biệt **thành công nghiệp vụ** với **chỉ đọc được message từ Kafka**.

### 12.1. Dashboard tối thiểu

| Nhóm | Metric hoặc tín hiệu | Điều cần nhìn |
| --- | --- | --- |
| Producer | send success/failure, retries, request latency p95/p99 | Kafka có nhận message ổn định không? |
| Consumer | lag per group/topic/partition | Backlog tập trung ở đâu? |
| Handler | processed success/failure, processing latency | Business logic có chậm hoặc lỗi không? |
| Retry | arrivals, pending lag, oldest pending age | Có record chờ retry quá SLA? |
| DLT | arrival rate, unreviewed count, age | Có poison events chưa được xử lý? |
| Offset | commit errors, rebalances, assigned partitions | Consumer group có ổn định không? |
| Broker | offline/under-replicated partitions, ISR, controller health | Có vấn đề về availability/durability? |
| Database | connection pool usage, transaction failures | Downstream có trở thành bottleneck? |
| Idempotency | duplicates detected, conflicting payloads | Có replay hoặc publisher trùng nhiều bất thường? |
| Deployment | image/version, active instances, recent rollout | Sự cố có tương quan với release không? |

Metric names phụ thuộc Spring Kafka/Kafka client/Micrometer/exporter đang dùng. **Không giả định tất cả metric này tự động được Spring Boot xuất ra**; một số là custom application metrics, một số cần broker exporter hoặc control-plane monitoring.

### 12.2. Một log có cấu trúc nên có gì?

```text
event=kafka.message.processing.failed
service=orders-worker
release=1.14.0
listenerId=ordersListener
groupId=orders-service
topic=orders.events
partition=2
offset=98321
errorCategory=DOWNSTREAM_TIMEOUT
retryDecision=RETRY
correlationId=trace-7cf8
```

Không log raw payment card, token, password, full JWT, signed URLs hoặc PII không cần thiết. Nếu log `eventId`/business key, đảm bảo data policy cho phép. Trong metrics, tránh dùng topic offset, order ID, eventId hoặc correlationId làm labels vì **cardinality rất cao**; giữ các ID chi tiết ở audit/log có phân quyền.

### 12.3. Cảnh báo cần có chủ sở hữu

- [ ] Producer error rate/timeout vượt ngưỡng.
- [ ] Consumer lag tăng liên tục hoặc ước tính thời gian drain vượt SLA.
- [ ] Một partition có lag bất thường khi các partition khác bình thường.
- [ ] Retry pending age cao hoặc retry rate tăng sau downstream incident.
- [ ] DLT arrival rate tăng, DLT chưa review quá SLA.
- [ ] Forwarding sang retry/DLT lỗi.
- [ ] Consumer group mất members, rebalances liên tục hoặc offset commits thất bại.
- [ ] Broker offline partitions/ISR/quorum có tín hiệu bất thường.
- [ ] Business output reconciliation thất bại dù main lag thấp.
- [ ] Mọi alert đã thử **đường giao đến on-call**, không chỉ thấy rule tồn tại trong dashboard.

Ví dụ ngưỡng cần do hệ thống tự chốt: cảnh báo nếu oldest retry record vượt 70% thời gian SLA, hoặc drain time ước tính vượt cửa sổ retention còn lại. Không dùng một ngưỡng `lag > 1000` cho mọi topic bất kể rate, partition và kích thước message.

## 13. Checklist kiểm thử trước production

Kiểm thử độ tin cậy phải bao gồm failure path. `@EmbeddedKafka` phù hợp kiểm tra wiring listener và basic retries; Testcontainers hoặc staging Kafka cluster giúp đo hệ thống thực hơn. Các bài về multi-broker ISR, KRaft quorum, ACL cloud cần môi trường đại diện; không thể chứng minh đầy đủ bằng mock `KafkaTemplate`.

### 13.1. Ma trận kiểm thử

| Test ID | Tình huống | Điều kiện PASS |
| --- | --- | --- |
| `T01` | Producer gửi message hợp lệ | Producer ack; consumer nhận payload và output đúng |
| `T02` | Listener nhận message cùng eventId hai lần | Business side effect chỉ một lần theo key |
| `T03` | Crash sau DB commit trước offset commit | Record có thể replay, output không duplicate |
| `T04` | Crash trước DB commit | Không tạo output nửa vời; record xử lý lại |
| `T05` | Broker leader restart | Producer/consumer hồi phục, lag trở lại ngưỡng |
| `T06` | Consumer Pod bị kill khi đang xử lý | Rebalance/replay có kiểm soát; output cuối đúng |
| `T07` | Database timeout trong callback | Retry/backoff theo policy; không commit business success giả |
| `T08` | Payload invalid | Vào DLT/quarantine hoặc policy dừng đã định nghĩa |
| `T09` | Lỗi transient rồi phục hồi | Xử lý thành công sau retries, không bị vào DLT sai |
| `T10` | Hết retry attempts | DLT nhận record và metadata nguồn, có alert |
| `T11` | Retry/DLT forwarding bị ACL denied | Test phát hiện, không thừa nhận success |
| `T12` | Schema cũ và mới cùng tồn tại | Consumer xử lý đúng cả hai theo rollout contract |
| `T13` | Rolling deploy 1 Pod mỗi lượt | Group phục hồi assignment, không mất business output |
| `T14` | Scale-out rồi scale-in | Lag, throughput và idempotency phù hợp kỳ vọng |
| `T15` | Pause/resume khi downstream chậm | Sau paused thật sự không delivery mới; resume xử lý backlog |
| `T16` | Retry topic backlog khi deploy version mới | Không bỏ quên topic cũ |
| `T17` | Kafka cluster unavailable tạm thời | App fail/recover theo policy, không mất events đã được commit |
| `T18` | DLT review/reprocess một event | Event được xử lý lại đúng, audit đầy đủ, không nhân đôi |
| `T19` | Load test p95/p99 và burst | Đáp ứng SLO và có capacity headroom |
| `T20` | Rollback image/config | Consumer tiếp tục đọc payload và topics còn pending |

Các test trên là danh mục đề xuất, cần phân loại theo kiến trúc. Ví dụ producer-only service không cần `T15`; transactional Streams pipeline cần test khác. Mỗi test nên có `setup`, `injection point`, `expected result`, `actual result`, evidence, owner và ticket khi fail.

### 13.2. `@EmbeddedKafka` smoke test tối thiểu

Ví dụ dưới đây minh họa cách chờ broker ack và callback listener thay vì dùng `Thread.sleep` tùy tiện:

```java
@SpringBootTest(
    classes = KafkaSmokeTest.TestApplication.class,
    properties = {
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer="
            + "org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer"
    }
)
@EmbeddedKafka(
    partitions = 1,
    topics = "readiness.smoke",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class KafkaSmokeTest {

    @Autowired KafkaTemplate<String, String> template;
    @Autowired KafkaListenerEndpointRegistry registry;
    @Autowired Probe probe;

    @Test
    void publishesAndConsumes() throws Exception {
        MessageListenerContainer container = Objects.requireNonNull(
            registry.getListenerContainer("readinessListener"));

        ContainerTestUtils.waitForAssignment(container, 1);

        String payload = "ready-" + UUID.randomUUID();
        template.send("readiness.smoke", payload)
            .get(10, TimeUnit.SECONDS);

        assertThat(probe.received.poll(10, TimeUnit.SECONDS))
            .isEqualTo(payload);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {
        @Bean Probe probe() { return new Probe(); }
    }

    static class Probe {
        final BlockingQueue<String> received =
            new LinkedBlockingQueue<>();

        @KafkaListener(
            id = "readinessListener",
            topics = "readiness.smoke",
            groupId = "readiness-test-group"
        )
        void receive(String payload) {
            received.add(payload);
        }
    }
}
```

Imports dùng trong test gồm: Spring Boot Test, Spring Kafka `@EmbeddedKafka`, `@KafkaListener`, `@EnableKafka`, `KafkaTemplate`, registry, `MessageListenerContainer`, `ContainerTestUtils`, Spring beans/config annotations, `@Test`, JUnit, AssertJ, `Objects`, `UUID`, `BlockingQueue`, `LinkedBlockingQueue` và `TimeUnit`. Đoạn code cố ý lược imports để làm rõ cấu trúc, không phải file Java sẵn sàng copy nguyên văn.

**Giới hạn:** Test này chỉ kiểm tra producer/consumer round-trip trong embedded broker. Nó không chứng minh transaction với database, multi-broker durability, ACL, runtime TLS, rolling upgrade hay DLT workflow. Những điều đó phải có test riêng.

### 13.3. Test idempotency đúng ranh giới crash

Để chứng minh `T03`, dùng fixture có event ID ổn định và một điểm chặn sau DB commit:

```text
Producer gửi event ev-101
Consumer A nhận ev-101
Business DB commit output
Kafka offset chưa commit
Kill consumer A có kiểm soát trong test
Consumer B nhận lại ev-101

Assert:
  - event đã được xử lý nghiệp vụ đúng một lần
  - duplicate attempt được nhận diện trong audit
  - offset sau đó được commit đúng
```

Đừng chỉ chạy `listener.onMessage(...)` hai lần rồi kết luận restart/rebalance an toàn. Unit test hai lần gọi có ích nhưng không kiểm chứng Kafka offsets và container lifecycle.

### 13.4. Test chuyển tiếp retry/DLT

Trong integration/staging test, gửi record làm handler ném exception được phân loại là retryable. Chờ producer ack ở main, quan sát đúng **retry destination**, đủ số attempts và DLT nếu lỗi kéo dài. Dùng message ID riêng để phân biệt nhiều test chạy đồng thời. Với đường ACL-denied hoặc serializer error, dùng principal/topic test riêng; không cố phá cấu hình của cluster production để kiểm thử.

### 13.5. Test hiệu năng và soak

Load test phải mô phỏng:

- Payload size distribution thật và partition skew.
- Input steady-state, burst và backlog sau outage.
- Downstream API/DB latency p95/p99.
- Batch of records per poll, listener concurrency và GC.
- Retry storm khi một dependency tạm unavailable.
- Rolling deploy giữa lúc có tải và backlog.
- DLT backlog lớn nhưng không che mất tình trạng nghiệp vụ.

Kết quả cần ghi throughput thành công, error/timeout rate, consumer lag, drain time, CPU/memory, broker network/disk, DB pool, rebalances, output reconciliation. **Không đánh giá chỉ bằng messages/s cao nhất khi không có failure injection**.

## 14. Checklist offset, retention và replay operations

Offset reset và replay là thao tác nhạy cảm vì có thể khiến một số message được xử lý lại hoặc bị bỏ qua.

### 14.1. Những mục phải đạt

- [ ] Có runbook tra `group.id`, partitions, committed offsets, end offsets và lag.
- [ ] Có chính sách ai được phép thay offset, ai phê duyệt và yêu cầu evidence/backup.
- [ ] Có kế hoạch replay với business key/idempotency; không dùng group ID mới vô tội vạ trên dữ liệu production.
- [ ] Input còn trong retention hoặc có nguồn lưu trữ khác để backfill khi cần.
- [ ] Khi reset offsets, consumer group được đưa vào trạng thái phù hợp với yêu cầu của Kafka CLI/managed platform.
- [ ] Có cách đối soát tập event IDs đã được xử lý trước/sau replay.
- [ ] Có alert khi oldest pending lag có nguy cơ vượt retention.
- [ ] Nếu topic compacted, đội nghiệp vụ hiểu không thể kỳ vọng replay toàn bộ lịch sử events đã bị compact.

### 14.2. Quan sát offset bằng CLI

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service
```

Output giúp xem current offset/log end offset/lag theo partitions. Đừng dùng một lần lag=0 để kết luận xử lý nghiệp vụ hoàn tất: record có thể đang ở retry topics, DLT hoặc side effect chưa được công nhận.

Nếu cần lập kế hoạch reset offsets, phải dùng **dry-run/describe/approval** theo công cụ và Kafka release tương ứng trước khi thực hiện thay đổi thực. Không cung cấp trong runbook một lệnh reset-to-earliest có thể bị copy chạy nhầm vào production mà không có guardrail.

### 14.3. Mất record do retention vẫn có thể xảy ra

Kafka retention là chính sách dọn log. Khi consumer pause quá lâu hoặc backlog lớn, dữ liệu có thể bị Kafka xóa trước khi group đọc kịp. Khi committed offset bị xóa khỏi log, hành vi resume phụ thuộc `auto.offset.reset`/client error policy. **Không được coi `earliest` là cách khôi phục record đã bị retention xóa.**

Cần đặt SLO về thời gian backlog được drain, alert trước cửa sổ retention và giải pháp external archive nếu có nhu cầu backfill dài hạn.

## 15. Checklist upgrade, compatibility và rollback

Một hệ thống ready cho production không chỉ chạy được version hôm nay, mà còn **có thể cập nhật mà không gây downtime hoặc mất message ngoài mức SLA**.

### 15.1. Các điều cần xác nhận

- [ ] Kafka broker release, KRaft metadata feature level và Java client versions được ghi nhận riêng.
- [ ] Spring Boot/Spring Kafka/Kafka clients runtime versions tương thích theo release docs.
- [ ] Đã test broker hiện tại với client mục tiêu và broker mục tiêu với client hiện tại, nếu có nâng độc lập.
- [ ] Group protocol/assignment strategy tương thích trong giai đoạn mixed client versions.
- [ ] Rolling deployment gây rebalance có thể chấp nhận và lag phục hồi trong SLA.
- [ ] Payload schema phiên bản mới không phá consumer cũ khi hai release cùng tồn tại.
- [ ] Retry topic suffix/naming không bỏ quên messages còn trong topics cũ.
- [ ] Rollback image không yêu cầu hạ DB schema hoặc đọc message format mới mà client cũ không hỗ trợ.
- [ ] Nếu nâng broker, kế hoạch có gate về controller quorum/ISR và hiểu **điểm hạn chế rollback sau feature finalization**.
- [ ] Có canary, soak period và tiêu chí tự dừng rollout khi error/lag/duplicate tăng.

### 15.2. Một quy trình phát hành có kiểm soát

```text
P0: Freeze contract + inventory versions/topic graph
          |
          v
P1: Staging tests + failure injection
          |
          v
P2: Provision ACL/topics/secrets/schema migration tương thích
          |
          v
P3: Canary subset of Pods/traffic
          |
          v
P4: Observe go/no-go gates
          |
   +------+------+
   |             |
  FAIL          PASS
   |             |
Rollback       Rolling deployment
or mitigate       |
                  v
             Soak + reconciliation
                  |
                  v
               Close change
```

Đặc biệt, nếu release thay đổi Kafka topic naming, schema hoặc business database format, **rollback code không có nghĩa rollback dữ liệu**. Chuẩn bị migration tiến/lùi và một cách tiếp tục consume backlog cũ, thay vì chỉ lưu image trước đó.

## 16. Checklist runbook và người trực vận hành

Một dashboard đẹp nhưng không có người nhận alert, quyền truy cập và cách xử lý thì chưa đủ production-ready.

### 16.1. Các runbook tối thiểu

| Sự cố | Điều runbook phải trả lời | Chủ sở hữu |
| --- | --- | --- |
| Producer liên tục timeout | Broker/ISR/ACL/network hay payload? Retry an toàn thế nào? | App + Kafka Platform |
| Consumer lag tăng | Partition skew, DB bottleneck, rebalances hay pause? | On-call + App |
| Retry backlog lớn | Downstream còn lỗi? Có retry storm? Có cần pause main? | App + Downstream owner |
| DLT tăng đột biến | Có lỗi schema, payload, auth hay code? Ai phân loại/reprocess? | Domain + App |
| `TopicAuthorizationException` | Principal/resource/action nào thiếu? Ai sửa ACL? | Security + Platform |
| Group rebalance liên tục | Deployment, static membership, poll interval hoặc broker coordinator? | App + SRE |
| Poison message kẹt | Cách chuyển DLT/quarantine mà không mất evidence? | App + Domain |
| Replay/backfill | Phạm vi offsets/source version, approval và đối soát? | Domain + On-call |
| Broker/controller sự cố | ISR/quorum, failover, producer impact, data durability? | Kafka Platform |
| Rollback release | Có thể quay code về không? Retry topics/schema có còn tương thích? | Release owner |

### 16.2. Runbook mẫu: consumer lag tăng đột biến

**Dấu hiệu:** lag của `orders-service` tăng liên tục 15 phút, processing throughput thấp hơn input rate.

1. **Đánh giá tác động nghiệp vụ:** backlog tương ứng bao nhiêu minutes of delay? SLA nào có nguy cơ vi phạm?
2. **Xác định phạm vi:** toàn group hay một partition? Main topic hay retry topic? Các groups khác có bị không?
3. **Xác nhận cluster:** broker health, ISR/offline partitions, producer errors, network và recent changes.
4. **Xác nhận consumer:** assigned partitions, rebalances, container paused/requested state, poll/processing latency và GC.
5. **Xác nhận downstream:** database pool, deadlocks, external API rate limit, 429/503.
6. **Chọn biện pháp có kiểm soát:** khôi phục downstream, giảm input khi có thể, scale consumer trong giới hạn partitions, thay retry budget theo change process hoặc rollback deployment.
7. **Không reset offset để “xóa lag”**: hành động này có thể bỏ qua messages chưa xử lý.
8. **Đối soát sau phục hồi:** backlog drain, pending retry/DLT, output business keys và error rates.
9. **Ghi incident timeline:** thời điểm bắt đầu, bước xử lý, các message ảnh hưởng, owner và hành động phòng ngừa.

Nếu tăng số replicas mà số Kafka partitions ít hơn, thêm Pods có thể không tăng số active consumers xử lý. Nếu bottleneck là một external API rate limit, scale-out có thể làm sự cố nặng hơn.

### 16.3. Runbook mẫu: DLT có record chưa review

1. Xác định DLT topic, event ID, original topic/partition/offset và reason code.
2. Phân biệt payload sai với lỗi tạm thời của hệ thống đích; nếu thuộc sự cố toàn hệ thống, ưu tiên khắc phục nguyên nhân trước.
3. Đảm bảo chỉ người có quyền mới xem raw payload chứa dữ liệu nhạy cảm.
4. Ghi quyết định `RETRY_AFTER_FIX`, `REJECT_PERMANENTLY` hoặc `WAIT_FOR_REFERENCE_DATA`.
5. Reprocess theo version/correlation riêng, giữ stable business identity/idempotency.
6. Kiểm tra thành công tại business output, không chỉ việc producer gửi lại lên main topic.
7. Cập nhật trạng thái review, execution/offset của lần tái xử lý và audit.

Đừng xóa DLT messages chỉ vì dashboard cần về zero. Việc xóa/retention phải theo chính sách dữ liệu và phải biết chính xác những records nào đã được xử lý.

## 17. Bảng bằng chứng cho buổi production readiness review

Đây là một biểu mẫu có thể copy vào ticket release hoặc ADR:

| Hạng mục | Owner | Bằng chứng chấp nhận | Trạng thái |
| --- | --- | --- | --- |
| Business event identity và idempotency | Domain/App | ADR + test duplicate/replay | `PENDING` |
| Topic config/retention/RF/ISR | Kafka Platform | IaC diff + topic describe | `PENDING` |
| Producer durability và publish failures | App | Config + leader restart test | `PENDING` |
| Consumer ack/commit và crash recovery | App | Test process kill + DB reconciliation | `PENDING` |
| Retry/backoff/DLT routing | App | Staging test + topic graph | `PENDING` |
| Retry/DLT ACL | Security/Platform | Principal-based smoke test | `PENDING` |
| Schema backward/forward compatibility | Data/App | Schema Registry check + fixture tests | `PENDING` |
| Load/burst/soak | SRE/App | Load report với p95/p99, lag và drain time | `PENDING` |
| Monitoring/alerts/on-call | SRE | Dashboard link + thử gửi cảnh báo | `PENDING` |
| Rolling deploy/canary | Release owner | Deployment rehearsal + metrics | `PENDING` |
| Rollback với backlog cũ | Release owner/App | Rollback rehearsal + compatibility evidence | `PENDING` |
| Incident/DLT/replay runbooks | On-call/Domain | Runbook links + drill record | `PENDING` |

Các trạng thái `PENDING` là placeholder của mẫu; người review phải thay bằng `PASS`, `FAIL`, `NOT_TESTED`, `N/A` hoặc `RISK_ACCEPTED` cùng link evidence. Không để template `PENDING` mà đánh dấu GO.

### 17.1. Định dạng một evidence record

```yaml
release: orders-worker-1.14.0
environment: staging-kafka
testId: T03
scenario: "DB commit succeeds, process crashes before Kafka offset commit"
owner: orders-team
status: PASS
date: 2026-11-16
artifacts:
  - "link-to-test-report"
  - "link-to-dashboard"
  - "link-to-db-reconciliation"
notes: "Event ev-101 was replayed; business side effect remained unique"
```

Đây là **YAML minh họa trong nội dung bài học**, không phải file QA hoặc summary của workflow sinh bài. Trong thực tế, `artifacts` phải trỏ tới report/log/dashboard có thể truy xuất được, không dùng các link placeholder.

### 17.2. Bảng GO/NO-GO cuối cùng

| Gate | Kết quả mong muốn | Người ký |
| --- | --- | --- |
| Data correctness | Không có đường mất/nhân đôi business effect chưa kiểm soát | Domain + App |
| Kafka availability | Broker/topic/ACL/retention đáp ứng policy | Kafka Platform |
| Resilience | Crash/rebalance/retry/DLT tests pass | App + SRE |
| Security | Secrets, TLS, ACL, PII policy pass | Security |
| Operations | Dashboard, alert delivery, runbooks, on-call ready | SRE/On-call |
| Release | Canary, rollback và version compatibility pass | Release owner |

**Không nên cho GO chỉ vì hầu hết ô đã `PASS`** nếu còn một vấn đề chặn như “DLT không có quyền ghi” hoặc “consumer có thể commit offset trước DB transaction”. Trường hợp ngoại lệ phải nêu chính xác tác động, phạm vi, thời hạn, người chấp thuận và guardrail.

## 18. Diễn tập tình huống tổng hợp

Một bài diễn tập cuối nên kết hợp nhiều thành phần thay vì mỗi test chỉ kiểm tra một class.

### Tình huống: downstream database mất kết nối 5 phút

Giả định:

- Producer vẫn gửi `orders.events` thành công.
- Consumer gọi database để tạo order projection.
- Các lỗi mất kết nối được phân loại retryable theo policy.
- Có retry topic hoặc blocking retry/DLT phù hợp.
- Listener chạy trên ba Pods.

Tiến trình diễn tập:

```text
T0  Baseline khỏe: Kafka lag thấp, DB update thành công.
T1  Inject DB outage trong staging.
T2  Consumer lỗi; retry/backoff và alert hoạt động.
T3  Producer tiếp tục đưa records; main/retry lag phản ánh backlog.
T4  DB hồi phục.
T5  Retry drain, business output dần bắt kịp nguồn.
T6  Kiểm tra DLT, idempotency conflicts và business reconciliation.
T7  Rolling restart một consumer khi vẫn còn backlog.
T8  Xác nhận không mất/nhân đôi business effect.
```

### Tiêu chí pass

1. Không mất message đã được broker ack do error handler commit nhầm hoặc forwarding failure.
2. Không có infinite retry storm gây quá tải DB vừa phục hồi.
3. Business output phản ánh đủ event IDs hợp lệ theo hợp đồng, hoặc những item chưa hoàn tất còn có thể truy vết ở retry/DLT.
4. DLT chứa đúng các record thực sự vượt retry policy; có thể review/reprocess.
5. Rebalances/rolling restart không khiến output bị duplicate vượt hợp đồng idempotency.
6. Lag và pending age trở về ngưỡng đã thống nhất trong cửa sổ SLO.
7. Alert đến đúng owner và incident runbook có thể thực hiện.

**Không làm outage thật trên production chỉ để chứng minh checklist** nếu chưa có phê duyệt, cách cô lập phạm vi và phương án rollback. Dùng staging/chaos environment có thể tái lập, bảo đảm không phát sinh thanh toán/email/API calls thật.

## 19. Những sai lầm production readiness thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ test message thành công | Không biết retry/crash/rebalance sẽ ra sao | Thêm failure injection và output reconciliation |
| Coi `acks=all` là exactly-once nghiệp vụ | Retry app có thể tạo event/effect trùng | Stable event ID, outbox, inbox/dedup |
| Chỉ xem main consumer lag | Retry/DLT backlog bị che | Dashboard toàn bộ topology |
| Dùng `auto.offset.reset=earliest` làm “backup” | Message đã hết retention không thể phục hồi | Archive/backfill policy và retention đủ |
| DLT tồn tại nhưng không có owner | Error records bị bỏ quên | SLA review, alert và runbook reprocess |
| Không thử principal/ACL khi forward | Main listener chạy, retry/DLT thất bại | Smoke test failure path với identity thật |
| Tăng replicas vượt số partitions để tăng throughput | Pod idle, DB vẫn là bottleneck | Đo per-partition lag, downstream capacity |
| Đổi group ID trong deploy thường | Consumer đọc lại hoặc bỏ dữ liệu theo reset policy | Giữ group ID ổn định, migration có chủ đích |
| Chỉ monitor `isPauseRequested()` | Pause chưa có hiệu lực nhưng tưởng đã dừng | Quan sát actual container pause và callback |
| Retry mọi `Exception` | Poison record lặp vô hạn, tăng chi phí | Classify transient/permanent, DLT policy |
| Non-blocking retry cho sự kiện cần strict ordering | Event sau xử lý trước event trước | Version-aware state hoặc chọn retry architecture khác |
| Giữ DLT retention ngắn hơn SLA review | Mất bằng chứng lỗi trước khi người xử lý | Tính cả outage và thời gian xử lý backlog |
| Deploy thay retry naming khi backlog còn | Topic cũ không còn consumer đọc | Drain/migrate và giữ compatibility |
| Liveness kill consumer khi DB chậm | Crash/rebalance lặp, lag tăng | Probe thể hiện đúng health và tránh restart storm |
| Hạ `min.insync.replicas` để tránh producer error | Giảm durability đúng lúc cluster có sự cố | Khôi phục ISR, giữ data safety policy |
| Rollback chỉ bằng image cũ | Code cũ không đọc được schema/new topics | Compatibility plan cả payload và state |
| Không ghi evidence/owner | Buổi review mang tính cảm tính | PASS/FAIL kèm artifact, owner và thời hạn |

## 20. Checklist bàn giao vận hành dạng có thể đánh dấu

Danh sách dưới đây thích hợp để đưa trực tiếp vào release ticket. Các checkbox chỉ được đánh dấu sau khi có bằng chứng đã kiểm tra.

### A. Hợp đồng dữ liệu

- [ ] A01. Business key/event ID và dedup strategy đã được review.
- [ ] A02. Schema evolution và serializer compatibility đã được kiểm chứng.
- [ ] A03. Message key/partitioning bảo vệ ordering mà nghiệp vụ cần.
- [ ] A04. Replay, tombstone, compaction và retention được định nghĩa.
- [ ] A05. Payload security, PII và tenant isolation đã được phê duyệt.

### B. Kafka infrastructure

- [ ] B01. Main/retry/DLT topics được provision đầy đủ.
- [ ] B02. Replication, min ISR, partitions, cleanup và retention phù hợp SLA.
- [ ] B03. Broker/controller health và metrics có baseline.
- [ ] B04. Client tới được broker advertised listeners qua TLS/network.
- [ ] B05. Capacity, quota, partition skew và thời gian drain đã được đo.

### C. Producer

- [ ] C01. Producer acks/idempotence/timeouts được cấu hình có chủ đích.
- [ ] C02. Send failures và callback/timeouts có logging/alert/retry policy.
- [ ] C03. Outbox hoặc cơ chế consistency giữa DB và Kafka được đánh giá.
- [ ] C04. Producer chịu được leader change và temporary broker outage.
- [ ] C05. Không publish duplicate business events khi retry request.

### D. Consumer

- [ ] D01. Offset/ack mode/auto commit contract được xác nhận.
- [ ] D02. DB/API side effects có idempotency khi record replay.
- [ ] D03. Listener exceptions được phân loại và xử lý đúng.
- [ ] D04. Poll interval, concurrency, rebalance và shutdown đã được thử.
- [ ] D05. Duplicate delivery, crash và rolling restart tests pass.

### E. Retry và DLT

- [ ] E01. Blocking vs non-blocking retry được chọn theo ordering/transaction needs.
- [ ] E02. Backoff, attempts, timeout và retry budget có SLA.
- [ ] E03. Retry/DLT topics, serializer và ACL hoạt động với principal thật.
- [ ] E04. DLT review/reprocess workflow có owner và audit.
- [ ] E05. Có test forwarding failure, exhaustion và recovery.

### F. Security

- [ ] F01. TLS/SASL/IAM/ACL áp dụng least privilege.
- [ ] F02. Secrets không nằm trong code, plaintext log hoặc artifacts.
- [ ] F03. Schema Registry/KMS/transaction IDs có quyền phù hợp.
- [ ] F04. Data classification và PII retention đã được xác nhận.
- [ ] F05. Service account, network policy và certificate rotation sẵn sàng.

### G. Monitoring và vận hành

- [ ] G01. Producer errors/latency và consumer lag được theo dõi.
- [ ] G02. Retry/DLT backlog, oldest age và reconciliation có metrics.
- [ ] G03. Alerts được thử tới on-call thật.
- [ ] G04. Runbook incident, pause/resume, replay và DLT được duyệt.
- [ ] G05. Có trách nhiệm phân loại và khắc phục vấn đề ngoài giờ.

### H. Deployment và resilience

- [ ] H01. Runtime dependency/JDK/Kafka client versions đã kiểm tra.
- [ ] H02. Rolling deployment/canary và rollback plan đã diễn tập.
- [ ] H03. Resource requests/limits và scale behavior được load test.
- [ ] H04. Pod termination, rebalance và state replay đã được thử.
- [ ] H05. Đã đối soát kết quả cuối sau outage và một vòng deploy.

### I. Phê duyệt

- [ ] I01. Mọi blocker có `PASS` hoặc ngoại lệ được phê duyệt đúng thẩm quyền.
- [ ] I02. Evidence links, owner và release ticket đã cập nhật.
- [ ] I03. Kafka Platform, App, Security và On-call đã review các mục thuộc trách nhiệm.
- [ ] I04. Rollout window, rollback trigger và người quyết định STOP/GO rõ ràng.
- [ ] I05. Kế hoạch post-deploy soak và đối soát nghiệp vụ đã được đặt lịch.

## 21. Sau go-live: checklist không kết thúc ở nút Deploy

Sau khi phát hành, tiếp tục giám sát để biết hệ thống **vận hành ổn định** chứ không chỉ khởi động:

1. **Trong canary:** xác nhận Kafka produce/consume success, offset commits, retries, DLT và các lỗi authentication/serialization.
2. **Trong rolling rollout:** theo dõi rebalances, lag, message latency, CPU/GC và downstream pressure; dừng rollout khi vượt gate.
3. **Sau rollout:** đối chiếu business output, event IDs, processing freshness và pending retry/DLT.
4. **Trong soak window:** theo dõi lag phục hồi và hiệu năng dưới tải bình thường/đỉnh; tránh đóng change quá sớm.
5. **Trong postmortem nếu có sự cố:** lưu evidence, xác định failure boundary, cập nhật tests và runbooks thay vì chỉ tăng retry count.
6. **Định kỳ:** diễn tập replay/backfill, kiểm tra owner DLT, retention, ACL rotation, upgrade compatibility và khả năng phục hồi khi process chết.

Một service có thể được đưa lên production thành công nhưng **chưa production-ready ở trạng thái ổn định** nếu cảnh báo chưa đến người trực, backlog xử lý chậm hơn retention hoặc DLT còn records chưa được review.

## 22. Kết luận

**Checklist production readiness** cho Spring Kafka là một **hợp đồng vận hành có thể chứng minh**. Cần xác nhận đồng thời: hợp đồng event, Kafka cluster/topic durability, producer ack/idempotence, consumer offset/transaction, retry/DLT, bảo mật, capacity, monitoring, failure tests, deployment và runbook.

Với các hệ thống quan trọng, câu hỏi cuối cùng trước GO không phải “`@KafkaListener` đã chạy chưa?” mà là: **Khi một broker, Pod hoặc downstream chết đúng lúc đang xử lý, hệ thống có nhận ra sự cố, không mất dữ liệu đã cam kết, tránh tác động nghiệp vụ trùng, xử lý được backlog và có người chịu trách nhiệm phục hồi hay không?**

Nếu câu trả lời được hỗ trợ bằng **test, dữ liệu đối soát, dashboard và quy trình đã diễn tập**, release có nền tảng tin cậy hơn. Nếu chưa có bằng chứng, trạng thái đúng là `NOT_TESTED` hoặc `NO-GO`, không phải `PASS` dựa trên kỳ vọng.

## Tài liệu tham khảo

- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): listener containers, `KafkaTemplate`, offset acknowledgments, error handling, retry và transactions.
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): poll loop, ack modes, commits, concurrency và lifecycle.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, backoff và dead-letter recoverer.
- [Spring Kafka — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): retry topics, DLT và các giới hạn về ordering/transactions.
- [Spring Kafka — Pausing and Resuming Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): pause/resume an toàn ở container.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi EOS của Kafka transactions.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `ContainerTestUtils` và integration testing.
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): auto-configuration, Kafka properties và runtime integration.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): producer, consumer group, offset, security, topics, retention và operations.
- [Kubernetes Documentation — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination và container lifecycle khi rolling deploy.
