# Đánh đổi giữa at-most-once và at-least-once

Khi một Kafka consumer nhận record, ứng dụng cần quyết định thời điểm xác nhận offset đã xử lý. Nếu commit offset trước khi chạy nghiệp vụ, record có thể bị mất khi ứng dụng dừng giữa hai bước. Nếu xử lý nghiệp vụ trước rồi mới commit, record có thể được giao lại khi ứng dụng dừng sau xử lý nhưng trước commit. Đây là đánh đổi cơ bản giữa hai ngữ nghĩa delivery: **at-most-once** và **at-least-once**.

Trong Spring Kafka, thời điểm commit được điều khiển bởi cấu hình consumer, `AckMode` của listener container, cách listener xác nhận và chính sách xử lý lỗi. Chọn đúng ngữ nghĩa cần dựa trên mức độ chấp nhận mất dữ liệu, khả năng xử lý trùng, yêu cầu thứ tự và chi phí commit.

## 1. Offset biểu diễn tiến độ đọc như thế nào?

Kafka lưu offset theo từng partition và từng consumer group. Khi consumer xử lý record ở offset `n`, offset được commit thường là `n + 1`, tức vị trí tiếp theo cần đọc. Offset commit không phải cờ đánh dấu riêng trên record và cũng không có nghĩa broker xóa record đó.

Ví dụ một partition có các record:

```text
Partition 0
  offset 0
  offset 1
  offset 2
  offset 3
  offset 4
```

Nếu consumer đã xử lý đến offset 2 và commit offset 3, lần khởi động sau group sẽ tiếp tục từ offset 3. Nếu ứng dụng dừng trước khi commit offset 3, group có thể đọc lại offset 2.

Hai thời điểm quan trọng trong một lần xử lý:

1. **Business processing:** ứng dụng thực hiện tác vụ với record, ví dụ cập nhật trạng thái đơn hàng hoặc ghi dữ liệu vào database.
2. **Offset commit:** consumer group lưu vị trí tiếp theo cần đọc.

Delivery semantics được quyết định chủ yếu bởi thứ tự giữa hai thời điểm này.

## 2. At-most-once: commit trước, xử lý sau

At-most-once có nghĩa một record được xử lý không quá một lần theo tiến độ consumer group. Để đạt cách xử lý này, consumer xác nhận offset trước khi thực hiện tác vụ nghiệp vụ.

```text
Poll record
    |
    v
Commit offset
    |
    v
Xử lý nghiệp vụ
    |
    v
Poll tiếp
```

Nếu ứng dụng dừng sau khi commit nhưng trước khi xử lý xong, group sẽ không đọc lại record đó. Kết quả là tác vụ nghiệp vụ có thể bị bỏ sót.

| Tình huống lỗi | Kết quả |
| --- | --- |
| Dừng trước khi commit | Record có thể được đọc lại; chưa đạt đặc tính at-most-once cho lần xử lý này |
| Commit thành công, sau đó dừng trước khi xử lý | Record không được đọc lại; tác vụ có thể bị mất |
| Xử lý hoàn tất | Record được xử lý một lần theo tiến độ đã commit |

At-most-once phù hợp khi mất một phần dữ liệu ít nghiêm trọng hơn việc xử lý lặp, ví dụ một số chỉ số telemetry không quan trọng, dữ liệu đo lường có thể tái tạo hoặc thông báo best-effort. Không phù hợp với nghiệp vụ mà một record bị bỏ qua có thể gây sai lệch tiền, tồn kho hoặc trạng thái đơn hàng.

## 3. At-least-once: xử lý trước, commit sau

At-least-once có nghĩa consumer tiếp tục thử xử lý cho đến khi tiến độ được xác nhận. Ứng dụng xử lý record trước; chỉ khi xử lý thành công mới commit offset.

```text
Poll record
    |
    v
Xử lý nghiệp vụ
    |
    v
Commit offset
    |
    v
Poll tiếp
```

Nếu ứng dụng dừng sau khi tác vụ nghiệp vụ hoàn tất nhưng trước khi commit, record sẽ được đọc lại. Vì vậy, tác vụ nghiệp vụ có thể chạy nhiều lần. Đây là nguồn gốc của duplicate trong at-least-once.

| Tình huống lỗi | Kết quả |
| --- | --- |
| Dừng trước khi xử lý hoàn tất | Offset chưa được commit; record có thể được đọc lại |
| Xử lý thành công, dừng trước commit | Record có thể được giao lại và nghiệp vụ có thể chạy lần nữa |
| Xử lý và commit thành công | Group chuyển sang offset tiếp theo |

At-least-once phù hợp với nghiệp vụ cần tránh bỏ sót record, chẳng hạn xử lý đơn hàng, cập nhật tồn kho hoặc ghi nhận thanh toán. Đổi lại, consumer cần chịu được việc nhận trùng bằng idempotency hoặc cơ chế deduplication.

## 4. So sánh hai ngữ nghĩa

| Tiêu chí | At-most-once | At-least-once |
| --- | --- | --- |
| Thời điểm commit | Trước xử lý nghiệp vụ | Sau khi xử lý thành công |
| Nguy cơ mất tác vụ | Có, nếu dừng sau commit trước xử lý | Thấp hơn nếu record còn trong retention và retry tiếp tục |
| Nguy cơ xử lý trùng | Được giảm bằng cách commit trước | Có thể xảy ra khi xử lý xong nhưng commit chưa thành công |
| Yêu cầu idempotency | Ít hơn ở consumer, nhưng vẫn có thể cần ở nguồn khác | Rất quan trọng |
| Phù hợp | Dữ liệu best-effort, mất một phần có thể chấp nhận | Nghiệp vụ cần xử lý đầy đủ và có thể chống trùng |
| Đánh đổi chính | Ưu tiên tránh lặp, chấp nhận bỏ sót | Ưu tiên tránh bỏ sót, chấp nhận retry/duplicate |

Không có lựa chọn nào tự động bảo đảm tác vụ nghiệp vụ “đúng một lần” trong mọi hệ thống. At-most-once ưu tiên không xử lý lại sau commit; at-least-once ưu tiên đọc lại khi chưa xác nhận. Để có kết quả đáng tin cậy, phải kết hợp delivery semantics với transaction, idempotency và thiết kế lưu trữ phù hợp.

## 5. Cấu hình commit trong Spring Kafka

Spring Kafka listener container quản lý vòng poll và commit offset. Từ Spring Kafka 2.3, nếu `enable.auto.commit` không được khai báo, framework đặt giá trị này thành `false` để container kiểm soát commit. `AckMode` mặc định phổ biến là `BATCH`.

Ví dụ cấu hình at-least-once thông thường:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: order-service
    listener:
      ack-mode: record
```

Với `AckMode.RECORD`, container commit sau khi listener xử lý thành công từng record. Nếu dùng `BATCH`, container commit sau khi xử lý thành công tất cả record nhận được trong một lần poll. Cả hai đều theo hướng xử lý trước rồi commit, nên có thể giao lại record nếu tiến trình dừng giữa hai bước.

Một số `AckMode` thường dùng:

| AckMode | Thời điểm commit |
| --- | --- |
| `RECORD` | Sau khi listener xử lý thành công từng record |
| `BATCH` | Sau khi tất cả record trong poll được xử lý thành công |
| `TIME` | Khi đạt khoảng thời gian commit đã cấu hình, sau khi record được xử lý |
| `COUNT` | Khi đạt số lượng record đã xử lý được cấu hình |
| `COUNT_TIME` | Khi đạt điều kiện thời gian hoặc số lượng |
| `MANUAL` | Listener gọi `acknowledge()`; commit được xử lý theo chu kỳ của container sau khi batch liên quan hoàn tất |
| `MANUAL_IMMEDIATE` | Commit ngay khi listener gọi `acknowledge()` trên consumer thread |

Các chế độ manual vẫn cần đặt `enable.auto.commit=false`. Hành vi chi tiết của batch, partial batch và commit phụ thuộc loại listener cùng phiên bản Spring Kafka; hãy kiểm tra tài liệu đúng phiên bản khi dùng manual acknowledgement.

## 6. At-least-once với @KafkaListener

Đây là cách đơn giản thường dùng cho consumer nghiệp vụ: listener hoàn tất bình thường thì container mới commit theo `AckMode`.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-service")
    public void onMessage(String eventJson) {
        orderService.createOrderProjection(eventJson);
    }
}
```

Với `AckMode.RECORD`, nếu `createOrderProjection` ném exception, listener container không commit offset của record như một xử lý thành công. Error handler có thể retry, phục hồi hoặc chuyển record sang DLT theo cấu hình. Nếu xử lý đã ghi database nhưng tiến trình dừng trước commit, record có thể được giao lại; `OrderService` cần có khả năng chống xử lý trùng.

Nếu listener trả về bình thường nhưng logic nghiệp vụ chỉ ghi log lỗi và bỏ qua, container có thể xem record là thành công rồi commit offset. Không nuốt exception nếu muốn container retry.

## 7. At-most-once với manual immediate acknowledgement

Để thể hiện at-most-once, listener có thể commit offset trước khi gọi nghiệp vụ bằng `MANUAL_IMMEDIATE`:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: telemetry-processor
    listener:
      ack-mode: manual_immediate
```

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class TelemetryListener {

    private final TelemetryService telemetryService;

    public TelemetryListener(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @KafkaListener(topics = "telemetry.samples")
    public void onMessage(String payload, Acknowledgment acknowledgment) {
        acknowledgment.acknowledge(); // Commit trước khi xử lý.
        telemetryService.recordBestEffort(payload);
    }
}
```

Trong `MANUAL_IMMEDIATE`, khi `acknowledge()` được gọi trên consumer thread, container thực hiện commit ngay theo cấu hình commit sync/async. Nếu tiến trình dừng sau acknowledgement nhưng trước khi `recordBestEffort` hoàn tất, record sẽ không được phát lại cho group. Đây chính là rủi ro mất tác vụ của at-most-once.

Chỉ dùng cách này khi nghiệp vụ chấp nhận bỏ sót. Nếu cần commit trước một cách có kiểm soát, hãy xem xét commit failure, rebalance và shutdown; không giả định lời gọi `acknowledge()` luôn đồng nghĩa broker đã lưu offset nếu commit thất bại.

## 8. Vì sao auto commit không phải lựa chọn an toàn mặc định?

Kafka consumer client có thuộc tính `enable.auto.commit`. Khi bật, client tự commit offset theo chu kỳ `auto.commit.interval.ms`, không gắn chặt thời điểm commit với việc listener đã hoàn tất xử lý nghiệp vụ hay chưa.

Ví dụ rủi ro:

1. Consumer poll một batch gồm 100 record.
2. Ứng dụng mới xử lý xong 20 record.
3. Auto commit ghi offset của batch đã poll.
4. Ứng dụng dừng trước khi xử lý 80 record còn lại.

Khi khởi động lại, group có thể bắt đầu sau offset đã commit; các record chưa xử lý bị bỏ qua. Ở chiều ngược lại, nếu xử lý xong nhưng dừng trước lần auto commit tiếp theo, record có thể được giao lại.

Vì vậy, bật auto commit không tự động mang lại at-most-once hay at-least-once cho business processing. Với Spring Kafka listener container, nên để `enable.auto.commit=false` và dùng `AckMode`/transaction để gắn commit với vòng xử lý.

## 9. Retry ảnh hưởng đến delivery semantics

Retry là một phần của at-least-once. Khi listener ném exception, container có thể thử lại record theo error handler. Nếu retry vẫn thất bại, ứng dụng có thể:

- Tiếp tục retry với backoff.
- Dừng hoặc pause việc xử lý partition tùy chiến lược.
- Chuyển record sang dead-letter topic (DLT) sau khi hết số lần thử.
- Ghi nhận trạng thái lỗi để xử lý thủ công.

Khi retry, cùng một record có thể đi qua listener nhiều lần. Nếu lần xử lý trước đã tạo side effect nhưng chưa commit offset, lần thử tiếp theo có thể lặp lại side effect đó. Vì vậy, retry chỉ an toàn khi tác vụ idempotent hoặc có cơ chế chống trùng.

Chuyển record sang DLT là một dạng recovery. Khi recover thành công và offset gốc được commit, group tiếp tục tiến lên. Cần giám sát DLT và có quy trình xử lý/phát lại; DLT không tự khôi phục tác động nghiệp vụ đã xảy ra một phần.

## 10. Idempotency: cách làm at-least-once an toàn hơn

Idempotency nghĩa là thực hiện cùng một yêu cầu nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương một lần. Với Kafka event, cách phổ biến là gán `eventId` duy nhất cho mỗi event và lưu dấu đã xử lý cùng transaction database với cập nhật nghiệp vụ.

Ví dụ bảng inbox:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Pseudo-code xử lý trong một transaction database:

```java
@Transactional
public void handle(OrderCreatedEvent event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return; // Event đã được xử lý trước đó.
    }

    orderRepository.createProjection(event);
}
```

`insertIfAbsent` cần được triển khai bằng unique constraint hoặc câu lệnh insert/upsert nguyên tử, không chỉ bằng thao tác `SELECT` rồi `INSERT` vì hai consumer có thể chạy đồng thời. Việc ghi dấu event và cập nhật nghiệp vụ phải nằm trong cùng database transaction; nếu tách hai thao tác, ứng dụng có thể ghi dấu thành công nhưng cập nhật nghiệp vụ thất bại, hoặc ngược lại.

Khi listener hoàn tất, container commit Kafka offset. Nếu ứng dụng dừng sau database commit nhưng trước Kafka offset commit, record được giao lại; lần sau `eventId` đã tồn tại nên business update không bị thực hiện lần nữa.

Các chiến lược idempotency khác gồm:

- Upsert theo aggregate ID và version.
- Cập nhật trạng thái có điều kiện, ví dụ chỉ chuyển đơn hàng từ `CREATED` sang `PAID` nếu trạng thái hiện tại đúng.
- Dùng event ID làm unique key cho các lệnh tạo dữ liệu.
- Dùng inbox/outbox khi cần phối hợp database với Kafka.

## 11. Phân biệt offset commit với độ bền dữ liệu producer

At-most-once và at-least-once ở consumer mô tả quan hệ giữa xử lý nghiệp vụ và offset commit. Chúng không thay thế cấu hình durability của producer và broker.

Nếu producer gửi record với `acks=0`, producer không đợi broker xác nhận. Nếu broker chưa nhận được record, consumer không thể xử lý record đó. Với dữ liệu quan trọng, thường cần cân nhắc `acks=all`, replication factor phù hợp và `min.insync.replicas` để tăng độ bền khi ghi.

Retention cũng ảnh hưởng đến khả năng at-least-once. Nếu consumer ngừng hoạt động lâu hơn thời hạn lưu dữ liệu và record chưa đọc đã bị xóa, group không thể retry record đó. Do đó, at-least-once giả định dữ liệu còn tồn tại và consumer có thể tiếp tục đọc.

## 12. Exactly-once có thay thế at-least-once không?

Kafka transaction và Spring Kafka hỗ trợ EOS cho luồng read-process-write giữa các topic Kafka: output record và offset input được commit trong cùng transaction. Consumer downstream nên dùng `isolation.level=read_committed` để chỉ đọc output đã commit.

EOS không có nghĩa phương thức listener chỉ được gọi một lần. Listener vẫn có thể chạy lại sau rollback hoặc lỗi. Nó cũng không tự bao gồm database, HTTP service, email hoặc side effect ngoài Kafka. Với database, thường cần transactional outbox/inbox hoặc idempotency để bảo đảm nhất quán.

Có thể nhìn mối quan hệ như sau:

| Cơ chế | Bảo đảm chính |
| --- | --- |
| At-most-once | Không xử lý lại sau khi offset đã được xác nhận; có thể bỏ sót tác vụ |
| At-least-once | Có thể đọc lại cho đến khi commit; cần xử lý duplicate |
| Kafka EOS | Output Kafka và offset input được commit nguyên tử trong transaction; code vẫn có thể chạy lại |
| Business idempotency | Nhiều lần giao cùng event không tạo nhiều tác động nghiệp vụ |

Trong nhiều hệ thống, at-least-once kết hợp idempotency là lựa chọn đơn giản và thực tế. EOS phù hợp khi cần nguyên tử giữa offset và output Kafka, nhưng không loại bỏ nhu cầu idempotency cho side effect bên ngoài.

## 13. Chọn AckMode theo yêu cầu

| Yêu cầu | Cách tiếp cận gợi ý |
| --- | --- |
| Muốn at-least-once đơn giản cho record listener | `enable.auto.commit=false`, `AckMode.RECORD` |
| Muốn commit theo batch poll để giảm số lần commit | `enable.auto.commit=false`, `AckMode.BATCH` |
| Cần listener quyết định thời điểm xác nhận sau xử lý | `MANUAL` hoặc `MANUAL_IMMEDIATE`, gọi acknowledge sau khi nghiệp vụ thành công |
| Chấp nhận mất record để giảm nguy cơ xử lý lại | Commit trước xử lý bằng `MANUAL_IMMEDIATE`, hiểu rõ rủi ro |
| Đọc, xử lý rồi ghi Kafka với offset/output nguyên tử | Container transaction và EOS V2 |

Với `TIME`, `COUNT` và `COUNT_TIME`, container gom commit theo điều kiện thời gian/số lượng sau khi xử lý. Chúng vẫn thuộc mô hình xử lý trước commit; khoảng thời gian hoặc số record chưa commit càng lớn thì cửa sổ có thể đọc lại càng rộng khi tiến trình gặp sự cố.

## 14. Kiểm thử delivery semantics

Không nên chỉ kiểm thử listener được gọi một lần trong điều kiện bình thường. Cần mô phỏng các điểm dừng giữa business processing và offset commit.

### Kiểm thử at-least-once

1. Gửi một event có `eventId` cố định.
2. Listener ghi kết quả nghiệp vụ vào database.
3. Làm cho listener thất bại hoặc tiến trình dừng trước khi offset được commit.
4. Khởi động lại consumer và xác nhận record được giao lại.
5. Xác nhận unique event ID khiến business update chỉ có hiệu lực một lần.

### Kiểm thử at-most-once

1. Gửi một event vào topic.
2. Listener commit offset trước khi gọi business service.
3. Làm cho business service thất bại sau commit.
4. Khởi động lại consumer.
5. Xác nhận group không đọc lại record đã commit và tác vụ bị bỏ sót theo đúng trade-off.

### Kiểm thử EOS

1. Gửi record vào input topic.
2. Listener gửi output trong Kafka transaction.
3. Kiểm tra consumer `read_committed` thấy output khi transaction commit.
4. Ép listener ném exception sau khi gửi output.
5. Xác nhận output của transaction abort không hiển thị với consumer `read_committed`.

Các kiểm thử này cần chờ assignment, commit và redelivery bằng điều kiện có timeout. Tránh dùng `Thread.sleep` cố định ngắn để kết luận về offset hoặc transaction.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Commit trước business processing nhưng kỳ vọng không mất record | Record có thể bị bỏ qua sau crash | Dùng xử lý trước commit nếu không chấp nhận mất |
| Xử lý trước commit nhưng không có idempotency | Side effect có thể lặp | Dùng event ID, unique constraint hoặc upsert |
| Bật auto commit trong listener xử lý lâu | Offset có thể tiến trước business completion | Để Spring container quản lý commit |
| Bắt exception rồi trả về bình thường | Container có thể commit record lỗi | Ném lại exception hoặc dùng recovery có chủ đích |
| Nghĩ DLT có nghĩa lỗi đã được xử lý | Record lỗi có thể bị bỏ quên | Giám sát DLT và xây quy trình replay |
| Cho rằng Kafka EOS bao gồm database | DB và Kafka vẫn có thể lệch | Dùng outbox/inbox hoặc idempotency |
| Retention quá ngắn | Record chưa đọc có thể bị xóa trước khi consumer quay lại | Chọn retention lớn hơn thời gian outage và backlog drain |

## 16. Kết luận

At-most-once commit offset trước khi xử lý: giảm nguy cơ xử lý lặp nhưng có thể bỏ sót tác vụ nếu ứng dụng dừng sau commit. At-least-once xử lý trước rồi commit: giảm nguy cơ bỏ sót khi record còn trong retention và retry hoạt động, nhưng có thể giao lại record nếu tiến trình dừng trước commit.

Với Spring Kafka, `AckMode.RECORD` hoặc `BATCH` cùng `enable.auto.commit=false` thường là nền tảng cho at-least-once. Chỉ dùng commit trước xử lý khi nghiệp vụ thực sự chấp nhận mất dữ liệu. Với luồng cần xử lý đầy đủ, hãy kết hợp retry với idempotency/deduplication; khi cần output Kafka và offset input nguyên tử, cân nhắc container transaction với EOS V2. Delivery semantics, durability của producer/broker và tính nhất quán của database cần được thiết kế cùng nhau.

## Tài liệu tham khảo

- [Spring Kafka — Message Listener Container: Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/documentation/#consumerapi)
