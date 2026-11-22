# Thiết kế hành vi khi service khởi động lại

Một service tiêu thụ Kafka phải tiếp tục xử lý đúng sau khi process dừng, pod được thay thế hoặc máy chủ khởi động lại. Muốn làm được điều đó, cần thiết kế rõ consumer group, offset đã commit, thời điểm xác nhận record, cách dừng listener và cách xử lý một event có thể được giao lại.

Khi service khởi động lại với cùng `group.id`, Kafka consumer tiếp tục từ offset đã commit gần nhất của từng partition, nếu offset đó vẫn còn hợp lệ. Record đã xử lý xong nhưng offset chưa commit có thể được giao lại. Vì vậy, service cần chịu được việc xử lý lặp, đặc biệt khi đã ghi database hoặc gọi hệ thống bên ngoài trước lúc commit offset.

Hành vi khôi phục không đến từ một cấu hình duy nhất. Nó là kết quả phối hợp giữa Kafka consumer group, Spring Kafka listener container, `AckMode`, error handler, lifecycle của ứng dụng và tính idempotent của nghiệp vụ.

## 1. Service restart cần bảo đảm điều gì?

Khi một service dừng rồi chạy lại, thiết kế nên đạt các mục tiêu:

- Tiếp tục đọc từ tiến độ đã commit của consumer group.
- Không bỏ qua event chưa được xử lý thành công.
- Chấp nhận event có thể được giao lại sau lỗi hoặc restart.
- Dừng consumer có kiểm soát để giảm số record đang xử lý dở.
- Phục hồi retry và dead-letter theo chính sách đã chọn.
- Có log, metric và dấu vết đủ để biết service đã dừng ở đâu và tiếp tục từ đâu.

Kafka lưu record trong topic theo retention policy. Consumer group lưu offset đã commit để xác định vị trí đọc tiếp theo. Restart service không xóa topic và cũng không tự đặt offset về đầu topic.

## 2. Cùng group ID thì tiếp tục từ committed offset

Kafka lưu offset theo cặp consumer group và partition. Khi consumer khởi động, nó tham gia group bằng `group.id`. Sau khi nhận partition assignment, consumer dùng committed offset của group để tiếp tục đọc.

Ví dụ group `billing-service` đã commit partition 0 đến offset 125:

```text
Topic: orders.events
Group: billing-service

Partition 0
  Offset 120 ... 124: đã được xử lý và commit
  Offset 125: vị trí tiếp theo cần đọc
  Offset 126 ...: các record tiếp theo
```

Nếu process restart và committed offset vẫn còn hợp lệ, consumer tiếp tục từ offset 125. Nó không đọc lại các record trước vị trí đó theo cách vận hành thông thường.

Các điều kiện quan trọng:

- Giữ nguyên `group.id` giữa các lần deploy/restart nếu muốn tiếp tục cùng tiến độ.
- Không xóa hoặc reset offset group trong quy trình deploy thông thường.
- Bảo đảm committed offset vẫn nằm trong phạm vi log còn tồn tại của partition.
- Để Spring Kafka container quản lý consumer lifecycle và commit offset theo `AckMode` đã chọn.

Nếu mỗi lần khởi động lại tạo một group ID mới, Kafka xem đó là một consumer group khác. Group mới không có committed offset cũ và sẽ áp dụng `auto.offset.reset`.

## 3. Cấu hình consumer để có thể phục hồi

Ví dụ cấu hình một service xử lý event đơn hàng:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event
        "[spring.json.value.default.type]": com.example.messaging.event.OrderCreated
    listener:
      ack-mode: record
```

Ý nghĩa:

- `group-id` phải ổn định giữa các lần restart để group dùng lại committed offset.
- `enable-auto-commit: false` để Spring Kafka container kiểm soát thời điểm commit.
- `ack-mode: record` commit sau khi từng record listener xử lý thành công.
- `auto-offset-reset: earliest` chỉ có tác dụng khi group không có offset hợp lệ cho partition; nó không ghi đè committed offset đang còn hợp lệ.

`earliest` là lựa chọn ví dụ, không phải giá trị bắt buộc cho mọi service. Một số luồng nghiệp vụ có thể cần `latest` hoặc cấu hình khác tùy cách khởi tạo group mới. Hãy chọn dựa trên yêu cầu dữ liệu và khả năng replay.

## 4. auto.offset.reset không phải lệnh đọc lại từ đầu

`auto.offset.reset` quyết định consumer bắt đầu từ đâu khi không tìm được committed offset hợp lệ cho một partition. Nó không quyết định vị trí đọc mỗi lần service restart nếu group vẫn có offset hợp lệ.

| Giá trị | Hành vi khi không có offset hợp lệ |
| --- | --- |
| `earliest` | Bắt đầu từ offset sớm nhất còn tồn tại trong partition |
| `latest` | Bắt đầu ở cuối log và nhận record mới được ghi sau đó |
| `none` | Ném lỗi vì không có offset hợp lệ |

Ví dụ:

- Service restart, group còn committed offset: tiếp tục từ offset đã commit; `earliest` không làm nó đọc lại từ đầu.
- Service dùng group ID mới: chưa có offset; `earliest` đọc từ record cũ nhất còn giữ, `latest` bắt đầu ở cuối log.
- Offset group đã hết hạn hoặc nằm ngoài phạm vi log còn giữ: consumer áp dụng reset policy tương ứng.

Vì vậy, thay `auto-offset-reset` từ `latest` sang `earliest` không phải cách an toàn để replay một group đang hoạt động. Muốn replay có chủ đích, cần dùng group mới hoặc reset offset theo quy trình vận hành được kiểm soát.

## 5. Offset có thể hết hạn trong thời gian service ngừng

Committed offset được lưu trong internal topic `__consumer_offsets`. Broker có chính sách giữ offset của group không hoạt động trong một khoảng thời gian, thường được điều khiển bởi `offsets.retention.minutes` ở broker (cấu hình và hành vi chi tiết tùy phiên bản Kafka).

Nếu service ngừng lâu hơn thời gian giữ offset, group có thể không còn committed offset khi service quay lại. Khi đó `auto.offset.reset` được áp dụng. Nếu chọn `latest`, service có thể bỏ qua các record cũ còn trong topic; nếu chọn `earliest`, service có thể phải xử lý lại nhiều dữ liệu còn giữ.

Đối với service có thể ngừng dài ngày:

- Hiểu cấu hình offset retention của Kafka cluster.
- Đặt cảnh báo khi consumer group inactive quá lâu.
- Kiểm tra committed offset trước khi khởi động lại sau thời gian dài.
- Có quy trình replay/reconciliation nếu offset không còn.
- Đánh giá retention của topic để bảo đảm dữ liệu cần phục hồi vẫn còn.

Offset retention và topic retention là hai chính sách khác nhau. Group có thể mất offset trong khi record vẫn còn; ngược lại, offset có thể tồn tại nhưng record ở vị trí đó đã bị retention xóa, khiến offset không còn hợp lệ.

## 6. Restart có thể khiến record được giao lại

Điểm quyết định là quan hệ giữa side effect nghiệp vụ và commit offset.

### 6.1. Restart trước khi xử lý xong

```text
Consumer nhận offset 125
        |
        v
Đang xử lý nghiệp vụ
        |
        X  Process bị kill
        |
        v
Offset 125 chưa commit
        |
        v
Service khởi động lại
        |
        v
Consumer nhận lại offset 125
```

Record chưa được commit có thể được giao lại cho consumer group sau khi group phục hồi và partition được assign. Đây là hành vi cần thiết để tránh bỏ qua record chưa hoàn tất.

### 6.2. Nghiệp vụ thành công nhưng process dừng trước commit

```text
Consumer nhận offset 125
        |
        v
Database transaction commit thành công
        |
        X  Process bị kill trước commit offset Kafka
        |
        v
Offset 125 vẫn chưa commit
        |
        v
Restart -> record 125 được giao lại
```

Database đã có thay đổi, nhưng Kafka chưa biết consumer đã hoàn tất record. Lần xử lý thứ hai có thể lặp side effect nếu service không idempotent.

### 6.3. Commit trước khi nghiệp vụ hoàn tất

```text
Consumer nhận offset 125
        |
        v
Commit offset tiếp theo: 126
        |
        X  Process bị kill trước khi cập nhật database
        |
        v
Restart -> consumer bắt đầu từ 126
```

Trong tình huống này, record 125 có thể không được giao lại dù nghiệp vụ chưa hoàn tất. Đây là nguy cơ mất tác động nghiệp vụ do commit quá sớm.

Với consumer xử lý database hoặc HTTP API, thông thường nên hoàn tất side effect trước rồi mới xác nhận offset, đồng thời làm side effect idempotent để chịu được redelivery.

## 7. AckMode ảnh hưởng hành vi sau restart

Spring Kafka `AckMode` quyết định thời điểm container commit offset:

| AckMode | Ranh giới commit | Hành vi có thể thấy sau restart |
| --- | --- | --- |
| `RECORD` | Sau mỗi record listener xử lý thành công | Record đã commit ít có khả năng bị đọc lại; record chưa commit có thể được giao lại |
| `BATCH` | Sau khi xử lý thành công các record của một lần poll | Các record đã xử lý trong batch nhưng batch chưa commit có thể được giao lại |
| `TIME` / `COUNT` / `COUNT_TIME` | Theo ngưỡng thời gian hoặc số lượng tại điểm an toàn của container | Một nhóm record kể từ lần commit trước có thể được giao lại |
| `MANUAL` | Listener gọi `acknowledge()`, container gom commit theo semantics batch | Record chưa được commit có thể được giao lại |
| `MANUAL_IMMEDIATE` | Ack trên consumer thread yêu cầu commit ngay | Khoảng chờ commit có thể ngắn hơn, nhưng vẫn có thể redeliver nếu process dừng trước khi broker ghi nhận commit |

`RECORD` thường dễ hiểu khi muốn commit sát từng record. `BATCH` có thể giảm số lần commit nhưng phạm vi replay sau crash có thể lớn hơn. Manual mode hữu ích khi listener phải kiểm soát điều kiện xác nhận, nhưng vị trí gọi `acknowledge()` phải nằm sau ranh giới nghiệp vụ.

Không có `AckMode` nào tự tạo transaction nguyên tử giữa Kafka offset và database transaction thông thường.

## 8. Viết listener chịu được restart và redelivery

Ví dụ listener xử lý event bằng một service có transaction database:

```java
package com.example.billing.consumer;

import com.example.messaging.event.OrderCreated;
import com.example.billing.service.BillingService;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final BillingService billingService;

    public OrderCreatedListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
            id = "billingOrdersListener",
            topics = "orders.events",
            groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.processIdempotently(event);
    }
}
```

Với `AckMode.RECORD`, container commit offset sau khi method trả về thành công. Nếu `processIdempotently` ném exception, container chuyển lỗi đến error handler; offset không được commit như một record thành công ở đường đi thông thường.

Điều quan trọng nằm trong `processIdempotently`: service phải nhận diện một `eventId` đã xử lý trước đó và tránh tạo lại side effect.

## 9. Idempotency bảo vệ side effect khi event được giao lại

Một cách phổ biến là lưu `eventId` vào bảng inbox với unique constraint trong cùng transaction database với thay đổi nghiệp vụ.

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Service xử lý theo một transaction:

```java
@Transactional
public void processIdempotently(OrderCreated event) {
    boolean inserted = processedEventRepository.insertIfAbsent(
            event.eventId(), Instant.now()
    );

    if (!inserted) {
        // Event đã được áp dụng trong transaction trước đó.
        return;
    }

    billingRepository.createInvoice(event.orderId(), event.total());
}
```

`insertIfAbsent` phải được triển khai bằng thao tác database nguyên tử, ví dụ `INSERT ... ON CONFLICT DO NOTHING` trên PostgreSQL hoặc cơ chế tương đương có unique constraint. Không dùng thao tác “query rồi insert” không khóa vì hai consumer/process có thể chạy đồng thời và cùng thấy event chưa tồn tại.

Nếu database transaction rollback, bản ghi inbox và thay đổi invoice cùng rollback. Nếu transaction commit thành công nhưng Kafka offset chưa commit, event có thể được giao lại; lần sau unique constraint phát hiện event đã xử lý và listener có thể trả về thành công để container commit offset.

Idempotency cần dựa trên ID event ổn định do producer tạo. Không dùng offset đơn lẻ làm khóa idempotency nếu event có thể được phát lại sang topic/partition khác hoặc được publish lại với offset mới.

## 10. Graceful shutdown trước khi process dừng

Một service thường dừng vì deployment rollout, scale-in, bảo trì hoặc shutdown host. Dừng có kiểm soát giúp giảm số listener invocation bị cắt giữa chừng.

Spring Kafka listener container được quản lý bởi Spring lifecycle. Khi application context đóng bình thường, Spring dừng các bean theo lifecycle; container sẽ dừng consumer và giải phóng tài nguyên. Cần cấp đủ thời gian cho shutdown để listener đang chạy có cơ hội hoàn tất.

Ví dụ cấu hình thời gian dừng cho các lifecycle phase của Spring Boot:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Trong môi trường container, `terminationGracePeriodSeconds` của Kubernetes cần đủ dài cho thời gian dừng ứng dụng và listener đang xử lý. Nếu orchestrator gửi SIGKILL trước khi ứng dụng kết thúc, quá trình shutdown graceful không thể hoàn tất.

`server.shutdown: graceful` của Spring Boot điều khiển graceful shutdown của embedded web server. Nó không thay thế lifecycle shutdown của Kafka listener container. Kafka listener được quản lý bởi Spring context và cần được kiểm soát qua lifecycle/timeout phù hợp.

### 10.1. Dừng listener có chủ đích

Có thể quản lý listener container qua `KafkaListenerEndpointRegistry` khi cần tạm dừng nhận event trước một thao tác bảo trì:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("billingOrdersListener");
        if (container != null) {
            container.stop();
        }
    }
}
```

ID truyền vào `getListenerContainer` phải trùng với `id` của `@KafkaListener`. Việc gọi `stop()` yêu cầu container dừng theo lifecycle của nó; không tự đóng Kafka consumer do Spring quản lý. Nếu cần dừng đồng bộ với một workflow bảo trì, hãy chờ callback/hoàn tất shutdown theo API của phiên bản Spring Kafka đang dùng.

### 10.2. Đừng đóng tài nguyên trước listener

Nếu listener phụ thuộc database connection pool, HTTP client hoặc executor do ứng dụng quản lý, các tài nguyên này phải còn sẵn sàng trong lúc listener dừng và hoàn tất công việc đang chạy. Hãy sắp xếp lifecycle/shutdown phase để listener ngừng trước khi đóng dependency mà nó cần.

Không dùng `@PreDestroy` để tự gọi `consumer.close()` trên consumer do Spring Kafka container quản lý. Container chịu trách nhiệm tạo, poll, commit, dừng và đóng consumer.

## 11. Readiness và liveness khi khởi động

Trong môi trường Kubernetes hoặc orchestrator, cần phân biệt:

- **Liveness:** process còn sống và không bị treo đến mức cần restart.
- **Readiness:** instance đã sẵn sàng nhận traffic hoặc công việc theo tiêu chí của ứng dụng.
- **Kafka listener startup:** listener container đã bắt đầu và tham gia consumer group.

Một process có thể đã mở HTTP port nhưng Kafka listener chưa nhận partition assignment. Nếu service chỉ sẵn sàng sau khi listener tham gia group, có thể dùng trạng thái container/group assignment trong readiness indicator. Không nên báo readiness chỉ dựa vào việc JVM đã khởi động.

Nếu cần chờ dependency trước khi listener nhận event, có thể đặt `autoStartup=false` trên listener rồi khởi động container sau khi dependency sẵn sàng:

```java
@KafkaListener(
        id = "billingOrdersListener",
        topics = "orders.events",
        groupId = "billing-service",
        autoStartup = "false"
)
public void onOrderCreated(OrderCreated event) {
    billingService.processIdempotently(event);
}
```

Sau khi điều kiện khởi động được đáp ứng, có thể lấy container từ `KafkaListenerEndpointRegistry` và gọi `start()`. Cần tránh để listener bắt đầu nhận record trước khi database migration, cache hoặc dependency thiết yếu đã sẵn sàng.

## 12. Rebalance khi service restart hoặc scale

Khi consumer rời group, Kafka phải phân phối lại partition cho các member còn lại. Restart một pod thường làm phát sinh membership change và rebalance. Khi instance mới khởi động, nó tham gia group và có thể khiến assignment thay đổi lần nữa.

Trong thời gian rebalance:

- Consumer có thể tạm ngừng nhận record trong lúc group đồng bộ assignment.
- Partition được thu hồi từ member cũ và giao cho member mới.
- Record chưa commit có thể được đọc lại sau khi assignment mới hoàn tất.
- Consumer lag có thể tăng tạm thời.

Để giảm tác động:

- Dùng rolling deployment với số instance thay đổi có kiểm soát.
- Tránh restart đồng loạt mọi replica nếu không cần thiết.
- Theo dõi rebalance count/duration và consumer lag.
- Cân nhắc cooperative sticky assignor nếu phù hợp với cluster/client version để giảm số partition phải di chuyển.
- Giữ listener xử lý trong giới hạn poll interval và thiết kế idempotent.

Không nên cố ngăn mọi rebalance bằng cách giữ consumer sống mãi. Rebalance là cơ chế bình thường để phục hồi và phân phối partition khi membership thay đổi.

## 13. Static membership và group.instance.id

Kafka hỗ trợ static membership qua `group.instance.id`. Static member có thể giảm rebalance trong một số trường hợp restart ngắn vì broker có thể chờ member quay lại thay vì lập tức phân phối lại partition.

Ví dụ cấu hình consumer client:

```yaml
spring:
  kafka:
    consumer:
      properties:
        group.instance.id: ${KAFKA_GROUP_INSTANCE_ID}
```

Giá trị `group.instance.id` phải ổn định cho cùng một instance khi restart và duy nhất giữa các consumer đồng thời trong group. Không dùng cùng một ID cố định cho tất cả pod; các instance trùng ID có thể bị fencing hoặc không thể cùng hoạt động như mong muốn.

Nếu listener dùng concurrency lớn hơn một, cần bảo đảm static member ID của từng Kafka consumer thực sự duy nhất. Cách Spring Kafka tạo/suffix ID cho child consumer có thể phụ thuộc phiên bản và cấu hình; hãy kiểm tra hành vi của phiên bản đang dùng trước khi bật static membership.

Static membership không thay thế committed offset, graceful shutdown hay idempotency. Nó chỉ thay đổi cách group xử lý member tạm thời rời khỏi group; nếu instance không quay lại trong thời gian cấu hình, partition vẫn có thể được phân phối lại.

## 14. Retry và dead-letter sau restart

Khi listener ném exception, Spring Kafka error handler có thể retry record theo backoff, recover record hoặc gửi sang dead-letter topic (DLT). Khi service restart trong lúc retry, cần hiểu retry state được lưu ở đâu.

### 14.1. Blocking retry trong listener container

Blocking retry thường thực hiện retry trong luồng xử lý của consumer/container. Nếu process dừng giữa các lần thử, record chưa được commit có thể được giao lại khi service phục hồi. Bộ đếm retry trong memory không nên được coi là lịch sử retry bền vững qua restart.

Vì vậy:

- Thiết kế handler có thể chạy lại an toàn.
- Giới hạn retry/backoff để không giữ partition quá lâu.
- Phân loại lỗi transient và lỗi không thể khắc phục bằng retry.
- Theo dõi số lần giao lại bằng metadata/log phù hợp nếu cần kiểm toán lâu dài.

### 14.2. Retry topic và DLT

Với non-blocking retry topics (`@RetryableTopic`) hoặc cơ chế retry lưu record sang topic khác, thông tin retry được thể hiện trong Kafka record và có thể tồn tại qua restart theo retention của retry topic. Tuy nhiên, cần cấu hình rõ số lần thử, backoff, routing về DLT và cách phục hồi record từ DLT.

Không giả định retry topic tự bảo đảm đúng thứ tự toàn cục với topic gốc. Khi event của cùng aggregate được chuyển sang retry topic, các event sau trong partition gốc có thể tiếp tục được xử lý tùy mô hình retry; hãy đánh giá ordering requirement.

### 14.3. Record trong DLT cần quy trình replay

DLT nên lưu đủ metadata để điều tra: topic gốc, partition, offset, exception, timestamp, event ID và correlation ID. Replay cần kiểm tra event có còn hợp lệ, có duplicate hay không và có thể gây side effect lặp hay không.

Không tự động chuyển toàn bộ DLT về topic gốc theo vòng lặp vô hạn. Hãy có thao tác replay được kiểm soát, ghi nhận người/tiến trình thực hiện và theo dõi kết quả.

## 15. Kafka transaction và database transaction khi restart

Kafka transaction có thể phối hợp output record và consumed offset trong cùng transaction Kafka khi ứng dụng được cấu hình đúng. Nếu transaction abort, offset gửi trong transaction cũng không được commit cùng output record.

Tuy nhiên, Kafka transaction không tự động bao gồm JDBC transaction hoặc HTTP call. Nếu listener cập nhật database rồi commit offset Kafka, vẫn có khoảng lỗi giữa hai hệ thống.

Với nghiệp vụ cần nhất quán giữa database và event:

- **Inbox/idempotency:** ghi nhận event đã xử lý trong cùng DB transaction với thay đổi nghiệp vụ.
- **Transactional outbox:** ghi thay đổi nghiệp vụ và event cần phát vào cùng DB transaction, sau đó relay outbox sang Kafka.
- **Reconciliation:** đối soát trạng thái nghiệp vụ với event/offset khi có sự cố dài hạn.

Hãy chọn pattern theo yêu cầu nhất quán. Không mô tả một listener là exactly-once cho database chỉ vì nó dùng Kafka `AckMode` hoặc Kafka transaction.

## 16. Kiểm thử hành vi restart

Test restart cần xác minh offset, side effect và trạng thái consumer group. Một test chỉ xác nhận application context khởi động lại thành công là chưa đủ.

Một kịch bản integration test với Testcontainers hoặc `@EmbeddedKafka`:

1. Tạo topic có ít nhất một partition và group ID cố định, ví dụ `billing-restart-test`.
2. Gửi ba event có `eventId` khác nhau.
3. Khởi chạy listener với `AckMode.RECORD` và chờ hai event đầu được xử lý/commit.
4. Tạo một điểm dừng có kiểm soát trước khi event thứ ba được xác nhận, hoặc dừng process test trong lúc handler đang xử lý.
5. Khởi động lại listener với cùng group ID.
6. Xác minh listener tiếp tục từ committed offset và event chưa commit được giao lại.
7. Lặp lại trường hợp database commit thành công nhưng offset chưa commit; xác minh inbox/unique constraint ngăn side effect trùng.
8. Kiểm tra trường hợp group ID mới để chứng minh `auto.offset.reset` được áp dụng khi chưa có committed offset.
9. Kiểm tra retry/DLT và log/metric sau khi restart.

Khi dùng embedded broker trong cùng JVM, có thể dừng và khởi động lại listener container qua `KafkaListenerEndpointRegistry` để mô phỏng một phần lifecycle. Để kiểm thử crash thực tế, Testcontainers hoặc process test riêng phù hợp hơn vì có thể kill process giữa các bước.

Hãy đồng bộ bằng `CountDownLatch`, `BlockingQueue`, container callback hoặc polling offset với timeout. Tránh dùng `Thread.sleep()` cố định làm bằng chứng listener đã commit.

## 17. Quan sát service trước và sau restart

Nên lưu các thông tin sau trong log/metric:

| Thông tin | Mục đích |
| --- | --- |
| Application instance/pod ID | Biết instance nào đang xử lý |
| Consumer group ID | Xác định tiến độ group |
| Consumer/client ID | Phân biệt member trong group |
| Topic, partition, offset | Xác định chính xác record và vị trí đọc |
| Event ID / aggregate ID | Truy vết và kiểm tra idempotency |
| Processing result | Phân biệt thành công, retry, recover và DLT |
| Commit failure | Phát hiện side effect đã xong nhưng offset chưa được lưu |
| Rebalance count/duration | Đánh giá tác động của restart/scale |
| Consumer lag | Xác định group có bắt kịp producer không |

Các chỉ số nên có cảnh báo:

- Consumer lag tăng liên tục sau khi service đã sẵn sàng.
- Consumer group không có member trong khi service được kỳ vọng đang chạy.
- Rebalance lặp lại trong thời gian ngắn.
- Commit failure hoặc lỗi deserialize tăng đột biến.
- Retry topic/DLT tăng bất thường.
- Thời gian shutdown vượt termination grace period.

## 18. Lỗi thường gặp khi thiết kế restart

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Restart xong đọc lại nhiều event | Offset chưa commit hoặc `BATCH` chưa commit poll trước | Kiểm tra AckMode và committed offset; làm handler idempotent |
| Restart xong bỏ qua event cũ | Dùng group ID mới với `auto.offset.reset=latest`, hoặc commit trước side effect | Giữ group ID ổn định; kiểm tra reset policy và vị trí ack |
| Event bị áp dụng hai lần | Database commit xong nhưng Kafka offset chưa commit | Dùng event ID và inbox/unique constraint |
| Service khởi động nhưng không nhận event | Container chưa start, group đang rebalance, topic/group config sai hoặc listener chưa có assignment | Kiểm tra registry, group membership, subscription và log |
| Service ngừng lâu rồi đọc sai vị trí | Committed offset hết hạn hoặc nằm ngoài log retention | Kiểm tra offset retention, topic retention và `auto.offset.reset` |
| Deploy gây lag tăng mạnh | Restart đồng loạt và rebalance | Rolling deployment, graceful shutdown, theo dõi rebalance |
| Listener bị kill giữa lúc xử lý | Shutdown timeout quá ngắn hoặc process bị SIGKILL | Tăng grace period hợp lý, rút ngắn handler và thiết kế idempotent |
| Retry bắt đầu lại sau restart | Retry state blocking không được lưu bền vững | Dùng retry topic hoặc lưu attempt state nếu nghiệp vụ yêu cầu |
| Static member bị fencing | `group.instance.id` bị trùng giữa các instance | Cấp ID duy nhất và ổn định cho từng consumer member |
| Replay DLT tạo side effect lặp | Replay không kiểm tra event đã áp dụng | Kiểm tra idempotency và ghi nhận replay operation |

## 19. Checklist triển khai

Trước khi đưa service Kafka vào production, hãy xác nhận:

1. `group.id` ổn định giữa các lần restart và các replica của cùng consumer group.
2. `enable.auto.commit=false` khi để Spring Kafka container quản lý offset.
3. `AckMode` phù hợp với ranh giới xử lý và batch/record listener.
4. Side effect nghiệp vụ hoàn tất trước khi xác nhận offset.
5. Handler idempotent theo `eventId` hoặc khóa nghiệp vụ phù hợp.
6. Topic retention và consumer offset retention đáp ứng thời gian service có thể ngừng.
7. `auto.offset.reset` được chọn có chủ đích cho group chưa có offset.
8. Spring lifecycle có đủ thời gian dừng listener; orchestrator grace period phù hợp.
9. Dependency của listener chỉ đóng sau khi listener dừng.
10. Retry, retry topic và DLT có chính sách phục hồi rõ ràng.
11. Readiness phản ánh trạng thái listener nếu service chỉ sẵn sàng khi đã tham gia group.
12. Monitoring có group member, assignment, lag, commit failure, retry và rebalance.
13. Có integration test cho restart trước xử lý, sau side effect nhưng trước commit và group mới.

Service khởi động lại an toàn khi nó tiếp tục từ committed offset đúng group, dừng listener có kiểm soát và có thể xử lý lại event mà không lặp tác động nghiệp vụ. Kafka cung cấp cơ chế lưu tiến độ và phân phối lại partition; ứng dụng phải thiết kế commit boundary, idempotency và quy trình vận hành để biến các cơ chế đó thành khả năng phục hồi đáng tin cậy.

## 20. Tự kiểm tra

1. Vì sao service phải giữ cùng `group.id` giữa các lần restart nếu muốn tiếp tục từ committed offset?
2. `auto.offset.reset=earliest` có làm group đang có offset hợp lệ đọc lại từ đầu không?
3. Điều gì xảy ra nếu database commit thành công nhưng process dừng trước khi commit offset Kafka?
4. Vì sao `AckMode.RECORD` và `BATCH` có phạm vi redelivery khác nhau?
5. Làm thế nào để inbox table ngăn một event tạo side effect hai lần?
6. Vì sao cần phân biệt topic retention và consumer offset retention?
7. Graceful shutdown của Kafka listener khác `server.shutdown=graceful` ở điểm nào?
8. Khi nào static membership với `group.instance.id` hữu ích và vì sao ID phải duy nhất?
9. Retry state của blocking retry có được mặc định lưu bền vững qua process restart không?
10. Cần kiểm thử những tình huống nào để chứng minh service phục hồi đúng sau restart?
