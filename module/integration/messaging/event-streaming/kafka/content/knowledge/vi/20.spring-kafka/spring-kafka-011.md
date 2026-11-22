# @RetryableTopic và giới hạn của retry không chặn

Spring Kafka cung cấp cơ chế non-blocking retry bằng annotation @RetryableTopic. Khi listener xử lý một record và gặp lỗi cần retry, framework chuyển record sang retry topic có thời điểm xử lý tiếp theo. Consumer của topic gốc có thể tiếp tục đọc các record khác thay vì chờ record lỗi. Sau số lần thử đã cấu hình, record được chuyển sang Dead Letter Topic (DLT) để điều tra hoặc xử lý riêng.

Cơ chế này tăng khả năng tiếp tục tiêu thụ partition khi lỗi downstream kéo dài, nhưng có một đánh đổi quan trọng: record phía sau có thể được xử lý trước record đang chờ retry. Vì vậy, non-blocking retry không giữ thứ tự nghiệp vụ nghiêm ngặt. Nếu cần thứ tự theo aggregate hoặc partition, phải chọn blocking retry hoặc thiết kế sequence guard, reorder buffer và idempotency ở tầng nghiệp vụ.

Bài này hướng dẫn cấu hình @RetryableTopic, attempts, backoff, phân loại exception, retry topics, DLT, partition/key, replay và monitoring trong Java/Spring Kafka. Phần cuối có lab để quan sát event bị lỗi đi qua retry topic trong khi event kế tiếp vẫn được xử lý trên topic chính.

## 1. Blocking retry và non-blocking retry

Spring Kafka có hai cách tiếp cận thường gặp:

| Cơ chế | Cách hoạt động | Tác động tới ordering |
|---|---|---|
| Blocking retry | Listener/container thử lại record lỗi ngay trên luồng xử lý hiện tại; partition bị chặn trong thời gian retry | Giữ thứ tự trên partition tốt hơn vì record sau phải chờ |
| Non-blocking retry | Chuyển record lỗi sang retry topic; consumer topic gốc tiếp tục đọc | Record sau có thể hoàn tất trước record đang retry |

Ví dụ topic orders.events có ba record cùng partition:

1. Sequence 10: cập nhật đơn hàng bị lỗi do database tạm thời không kết nối.
2. Sequence 11: thanh toán đơn hàng.
3. Sequence 12: đóng gói đơn hàng.

Với blocking retry, consumer giữ partition ở record sequence 10 cho đến khi thành công hoặc chuyển DLT. Sequence 11 và 12 phải chờ.

Với non-blocking retry, sequence 10 được chuyển sang retry topic. Consumer topic chính tiếp tục xử lý sequence 11 và 12. Khi retry topic đến thời điểm xử lý, sequence 10 mới được thử lại. Trạng thái nghiệp vụ có thể quan sát theo thứ tự 11, 12, 10.

~~~mermaid
flowchart TD
    A[orders.events: sequence 10] --> B{Listener xử lý}
    B -- Thành công --> C[Commit offset topic chính]
    B -- Lỗi cần retry --> D[Publish retry topic]
    D --> E[Commit offset topic chính]
    E --> F[Consumer topic chính đọc sequence 11, 12]
    D --> G[Đến thời điểm retry]
    G --> H{Thử lại}
    H -- Thành công --> I[Hoàn tất sequence 10]
    H -- Hết attempts --> J[Dead Letter Topic]
~~~

Non-blocking retry có nghĩa partition topic gốc không bị giữ lại bởi record lỗi trong thời gian backoff. Nó không có nghĩa việc xử lý record retry là tức thời, không có duplicate, hoặc bảo đảm ordering xuyên suốt các topic.

## 2. Luồng hoạt động của @RetryableTopic

Với một listener dùng @RetryableTopic, Spring Kafka thiết lập các listener container cho topic chính, các retry topic và DLT. Khi listener chính ném exception thuộc nhóm cần retry:

1. Framework xác định retry policy và số lần đã thử.
2. Framework publish record sang retry topic phù hợp với backoff.
3. Record retry mang theo metadata/header về lần thử, topic gốc, partition, offset và thời điểm được phép xử lý.
4. Offset của record trên topic gốc được xác nhận sau khi việc chuyển tiếp được thực hiện thành công theo cơ chế framework.
5. Consumer topic chính tiếp tục nhận record tiếp theo.
6. Retry listener chỉ xử lý record khi backoff timestamp đã đến.
7. Nếu retry thất bại, record được chuyển sang retry topic tiếp theo hoặc DLT khi hết attempts.

Retry topics là Kafka topics bình thường. Spring Kafka dùng header thời gian backoff và cơ chế pause/resume partition để tránh xử lý record trước thời điểm cho phép; Kafka không tự có một loại topic delay riêng trong mô hình này.

Tên topic được tạo phụ thuộc naming strategy và phiên bản Spring Kafka. Với Spring Kafka 3.3, exponential backoff thường tạo retry topic có suffix theo delay; fixed-delay với nhiều topic có thể dùng suffix theo index. Có thể cấu hình chiến lược suffix tường minh. Một cấu hình minh họa có thể tạo các topic dạng:

| Vai trò | Tên minh họa |
|---|---|
| Topic gốc | orders.events |
| Retry sau 1 giây | orders.events-retry-1000 |
| Retry sau 2 giây | orders.events-retry-2000 |
| Retry sau 4 giây | orders.events-retry-4000 |
| DLT | orders.events-dlt |

Đây là tên minh họa theo exponential delay; tên thực tế có thể là retry-0, retry-1... nếu dùng index suffix hoặc naming strategy tùy chỉnh. Hãy kiểm tra tên topic do ứng dụng tạo ra trước khi provision ACL, retention và dashboard.

## 3. Ý nghĩa của attempts và backoff

Thuộc tính attempts biểu thị tổng số lần giao thử, bao gồm lần gọi listener đầu tiên. Ví dụ attempts = 4 có nghĩa:

- Lần 1: listener trên topic chính.
- Lần 2: retry lần thứ nhất.
- Lần 3: retry lần thứ hai.
- Lần 4: retry lần thứ ba.
- Nếu lần 4 vẫn thất bại, record được chuyển DLT.

Backoff xác định khoảng chờ giữa các lần thử. Một số kiểu thường dùng:

| Kiểu | Ví dụ khoảng chờ | Khi dùng |
|---|---|---|
| Fixed | 1s, 1s, 1s | Lỗi tạm thời có thời gian phục hồi ngắn và ổn định |
| Exponential | 1s, 2s, 4s, 8s | Downstream cần thời gian phục hồi tăng dần |
| Exponential có max delay | 1s, 2s, 4s, 8s, 10s, 10s | Cần tăng khoảng chờ nhưng không muốn vượt ngưỡng |
| Random/jitter | Khoảng chờ có dao động | Tránh nhiều consumer cùng retry tại một thời điểm |

Với exponential backoff, khoảng chờ cơ bản sau lần thử thứ n tăng theo multiplier. Ví dụ delay 1.000 ms và multiplier 2 tạo chuỗi 1.000, 2.000, 4.000 ms, cho đến maxDelay nếu có cấu hình giới hạn.

Backoff chỉ quyết định thời điểm thử lại. Nó không sửa lỗi dữ liệu, không bảo đảm downstream đã phục hồi và không thay thế timeout/circuit breaker của HTTP hoặc database client.

## 4. Thêm dependency Spring Kafka

Trong ứng dụng Spring Boot, thường dùng starter:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
~~~

Nếu dùng Spring Boot, để dependency management của Boot chọn phiên bản Spring Kafka tương thích. Không tự nâng riêng kafka-clients hoặc Spring Retry mà không kiểm tra ma trận tương thích.

Các ví dụ trong bài dùng API Spring Kafka 3.x và Kafka client hiện đại. Với phiên bản khác, xác minh import, annotation attributes và giới hạn tính năng trong tài liệu của đúng phiên bản.

## 5. Định nghĩa event và exception

Event cần có eventId ổn định và aggregate key để hỗ trợ deduplication và ordering guard:

~~~java
package com.example.orders.event;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderEvent(
        String eventId,
        String orderId,
        long sequence,
        String eventType,
        BigDecimal amount,
        Instant occurredAt
) {
}
~~~

eventId không được tạo mới mỗi lần retry. Cùng một sự kiện nghiệp vụ phải giữ nguyên eventId qua producer retry, retry topic và DLT.

Tạo exception để phân loại lỗi:

~~~java
package com.example.orders.error;

public class TemporaryPaymentException extends RuntimeException {
    public TemporaryPaymentException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

TemporaryPaymentException đại diện lỗi tạm thời như timeout hoặc downstream unavailable. InvalidOrderException đại diện dữ liệu nghiệp vụ không hợp lệ, thường không nên retry vì thử lại cùng payload không làm dữ liệu tự hợp lệ.

Trong Java, mỗi public top-level class cần file riêng. Tách TemporaryPaymentException.java và InvalidOrderException.java nếu đặt cả hai là public.

## 6. Cấu hình Kafka consumer và JSON

Ví dụ application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.event
        spring.json.value.default.type: com.example.orders.event.OrderEvent
    listener:
      ack-mode: record
~~~

Trong production, cấu hình trusted packages càng hẹp càng tốt; không dùng wildcard nếu không cần. Thay bootstrap-servers bằng external configuration hoặc environment override của Spring khi triển khai từng môi trường. Với serializer/deserializer JSON, thống nhất schema và version giữa producer, consumer, retry topic và DLT consumer.

Retry topic chứa payload được chuyển tiếp từ record gốc. Vì vậy các topic retry và DLT cần tương thích serializer/deserializer với topic chính.

## 7. Cấu hình @RetryableTopic cơ bản

Ví dụ listener retry khi gặp lỗi tạm thời, tối đa bốn lần giao thử tổng cộng:

~~~java
package com.example.orders.listener;

import com.example.orders.event.OrderEvent;
import com.example.orders.error.InvalidOrderException;
import com.example.orders.error.TemporaryPaymentException;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @RetryableTopic(
            attempts = "4",
            backoff = @Backoff(
                    delay = 1000,
                    multiplier = 2.0,
                    maxDelay = 10000),
            include = {TemporaryPaymentException.class},
            exclude = {InvalidOrderException.class},
            autoCreateTopics = "false",
            numPartitions = "3",
            replicationFactor = "1",
            dltTopicSuffix = "-dlt")
    @KafkaListener(
            topics = "orders.events",
            groupId = "order-service")
    public void onOrderEvent(OrderEvent event) {
        orderService.process(event);
    }

    @DltHandler
    public void onDlt(
            OrderEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
        orderService.recordFailure(event, topic);
    }
}
~~~

OrderService là service nghiệp vụ do ứng dụng cung cấp. Trong ví dụ, chỉ TemporaryPaymentException thuộc nhóm retry được khai báo; InvalidOrderException bị loại trừ. Nếu một exception không thuộc nhóm retry được cấu hình, hành vi sẽ theo exception classification của cấu hình retry và có thể chuyển thẳng đến DLT. Hãy khai báo rõ các exception có thể retry và các exception không retry thay vì để mọi lỗi đều được thử lại.

autoCreateTopics = false yêu cầu topic retry và DLT đã được tạo trước. numPartitions và replicationFactor chỉ dùng cho cơ chế tạo topic tự động; nếu topic được provision ngoài ứng dụng, bảo đảm retry topic có số partition và replication phù hợp với topic gốc.

Với ví dụ topic gốc có ba partition, retry topic nên có tối thiểu ba partition nếu muốn giữ mapping partition theo đường retry. DLT cũng nên được provision theo throughput và yêu cầu điều tra. replicationFactor = 1 chỉ dành cho lab một broker, không phải cấu hình production.

Spring Kafka mặc định dùng group ID retry/DLT được tạo từ groupId của @KafkaListener kết hợp với suffix topic. Nên khai báo groupId rõ ràng như ví dụ để consumer retry không vô tình dùng chung group ID với consumer topic chính; nếu dùng chung group ID, rebalance ở retry topic có thể gây rebalance không cần thiết ở topic gốc.

## 8. Exception classification: lỗi nào nên retry?

Không nên retry tất cả exception. Phân loại theo khả năng lỗi tự phục hồi:

| Loại lỗi | Ví dụ | Chính sách gợi ý |
|---|---|---|
| Lỗi tạm thời | HTTP 503, timeout, connection reset, database failover ngắn | Retry với backoff và giới hạn attempts |
| Lỗi giới hạn tốc độ | HTTP 429, quota exceeded | Retry theo Retry-After nếu ứng dụng hỗ trợ; backoff có jitter |
| Lỗi dữ liệu | JSON sai, thiếu trường bắt buộc, amount âm | Không retry; chuyển DLT hoặc quarantine |
| Lỗi nghiệp vụ vĩnh viễn | Order đã hủy, trạng thái không hợp lệ | Không retry tự động; ghi nhận kết quả nghiệp vụ |
| Lỗi cấu hình/quyền | Authentication failed, topic authorization denied | Dừng/alert và sửa cấu hình; retry liên tục thường không hữu ích |
| Lỗi không xác định | RuntimeException không phân loại | Chính sách rõ ràng; tránh vô hạn retry |

Một HTTP timeout không luôn chứng minh request chưa được thực hiện. Downstream có thể đã commit side effect nhưng response bị mất. Khi retry, gửi idempotency key hoặc eventId để downstream không áp dụng tác động hai lần.

## 9. Topic retry và DLT phải được provision đúng

Khi không dùng auto-create, tạo topic chính, retry và DLT trước khi triển khai listener. Tên chính xác phụ thuộc naming strategy, suffix và backoff intervals. Với ví dụ delay 1s, 2s và 4s, có thể provision các topic minh họa:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.events --partitions 3 --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.events-retry-1000 --partitions 3 --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.events-retry-2000 --partitions 3 --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.events-retry-4000 --partitions 3 --replication-factor 1

kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.events-dlt --partitions 3 --replication-factor 1
~~~

Các tên topic trên chỉ là ví dụ. Trước khi tạo thủ công, chạy ứng dụng trên môi trường lab hoặc kiểm tra naming strategy để biết chính xác tập retry topics cần có; tránh thiếu topic hoặc tạo nhầm tên.

Mỗi retry topic và DLT cần được cấu hình:

- Partition count tương thích với topic gốc và yêu cầu routing.
- Replication factor/min.insync.replicas phù hợp durability.
- Retention đủ dài cho thời gian lỗi và điều tra.
- ACL cho principal của listener publish/consume.
- Monitoring cho incoming rate, retry age, consumer lag và DLT count.
- Quy trình replay có kiểm soát sau khi khắc phục nguyên nhân.

Retry topic không nên có retention quá ngắn. Nếu record chưa được xử lý do backlog hoặc downtime kéo dài hơn retention, dữ liệu có thể hết hạn trước khi retry.

## 10. Giữ key và partition qua retry

Key của record thường được giữ khi chuyển sang retry topic, giúp event của cùng aggregate tiếp tục dùng key tương ứng. Tuy nhiên, điều đó không khôi phục thứ tự tổng thể vì record bị lỗi nằm ở topic retry trong khi record sau vẫn được xử lý ở topic chính.

Nếu retry topic có số partition khác topic gốc hoặc partitioner khác, mapping có thể thay đổi. Khi cần đối chiếu thứ tự, giữ các metadata gốc:

| Metadata | Mục đích |
|---|---|
| eventId | Nhận diện cùng event qua mọi lần retry |
| aggregateId/orderId | Key nghiệp vụ |
| sequence | Thứ tự logic của aggregate |
| original-topic | Topic phát sinh record |
| original-partition | Partition ban đầu |
| original-offset | Offset ban đầu |
| delivery-attempt | Số lần giao thử |
| exception class/message | Lý do retry |
| backoff timestamp | Thời điểm được phép thử lại |

Không dựa riêng vào offset của retry topic để suy ra thứ tự với topic chính. Offset chỉ có ý nghĩa trong phạm vi một partition của một topic.

## 11. Giới hạn ordering của non-blocking retry

Non-blocking retry không giữ thứ tự nghiêm ngặt trên partition gốc. Ví dụ:

| Thời điểm | Topic | Event | Kết quả |
|---|---|---|---|
| T0 | orders.events | sequence 20 | Thất bại, chuyển retry |
| T1 | orders.events | sequence 21 | Thành công |
| T2 | orders.events | sequence 22 | Thành công |
| T3 | orders.events-retry | sequence 20 | Retry thành công |

Downstream đã quan sát sequence 21 và 22 trước sequence 20. Key giống nhau không thay đổi kết quả này vì record đã đi qua các topic khác nhau và được consumer khác xử lý.

Non-blocking retry phù hợp khi:

- Event độc lập hoặc thứ tự hoàn tất không quan trọng.
- Consumer dùng sequence/version guard để từ chối event stale.
- Có thể buffer event đến sai thứ tự trong một khoảng giới hạn.
- Kết quả là trạng thái có thể reconcile từ source of truth.
- Throughput và khả năng tiếp tục xử lý quan trọng hơn strict ordering.

Không phù hợp nếu mọi event của một aggregate bắt buộc được áp dụng theo đúng sequence và event sau không được vượt event trước.

## 12. Cách giữ thứ tự khi nghiệp vụ yêu cầu

Có một số lựa chọn:

### 12.1. Dùng blocking retry

Listener/container giữ partition tại record lỗi trong thời gian retry. Record sau cùng partition phải chờ. Đây là lựa chọn đơn giản khi strict ordering quan trọng và thời gian retry được kiểm soát.

Đánh đổi: một poison record có thể chặn tất cả key khác cùng partition. Tăng partition có thể giảm phạm vi ảnh hưởng nhưng không giải quyết ordering cho cùng key.

### 12.2. Kiểm tra sequence theo aggregate

Lưu lastAppliedSequence cho mỗi orderId. Khi event mới đến:

| Sequence nhận | Sequence hiện tại | Hành động |
|---:|---:|---|
| 11 | 10 | Áp dụng event 11 |
| 11 | 11 | Duplicate; bỏ qua theo eventId/sequence |
| 10 | 11 | Stale event; audit và bỏ qua theo chính sách |
| 13 | 11 | Gap sequence 12; buffer, retry hoặc reconcile |

Sequence phải được cấp tại nguồn có thẩm quyền. Không dùng timestamp làm sequence nếu đồng hồ giữa producer có thể lệch.

### 12.3. Reorder buffer

Lưu event đến sớm vào buffer theo aggregateId và sequence. Chỉ phát event kế tiếp khi sequence trước đã có mặt. Buffer cần giới hạn:

- Số event tối đa cho mỗi aggregate.
- Tổng dung lượng và số aggregate đang chờ.
- Thời gian chờ tối đa.
- Chính sách khi gap không được lấp: alert, reconcile hoặc DLT.

Nếu không có giới hạn, một event bị mất có thể khiến buffer tăng vô hạn.

### 12.4. Tách luồng theo loại nghiệp vụ

Nếu một số event cần strict ordering còn các event khác độc lập, có thể tách topic hoặc consumer flow theo aggregate/lifecycle. Thiết kế partition key ổn định và quy tắc retry tương ứng cho từng luồng.

## 13. DLT là gì và xử lý thế nào?

Dead Letter Topic nhận record đã hết retry attempts hoặc được phân loại không retry. DLT không phải nơi tự động sửa dữ liệu. Nó là vùng cách ly để:

- Lưu event không xử lý được.
- Ghi nhận exception và nguồn gốc record.
- Phát cảnh báo và tạo ticket xử lý.
- Phân tích schema, dữ liệu hoặc dependency lỗi.
- Replay sau khi nguyên nhân đã được sửa.

Ví dụ handler:

~~~java
@DltHandler
public void onDlt(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.error("DLT eventId={} orderId={} topic={} offset={}",
            event.eventId(), event.orderId(), topic, offset);

    dltAuditService.store(event, topic, offset);
}
~~~

DLT handler cần idempotent vì DLT record cũng có thể được giao lại nếu handler xử lý xong nhưng chưa commit offset. Không ghi credential hoặc payload nhạy cảm đầy đủ vào log; lưu dữ liệu theo chính sách bảo mật và retention.

Nếu DLT handler thất bại, hành vi tiếp theo phụ thuộc DLT strategy. Cần quyết định rõ có retry xử lý DLT, dừng consumer để giữ record chưa commit hay bỏ qua theo chính sách. Không nuốt exception rồi commit như thể event đã được xử lý thành công.

Spring Kafka 3.3 cung cấp các lựa chọn DLT failure:

| Strategy | Hành vi khi DLT handler ném lỗi |
|---|---|
| ALWAYS_RETRY_ON_ERROR | Forward record trở lại DLT để không chặn các record DLT khác; đây là mặc định |
| FAIL_ON_ERROR | Không forward record lỗi trở lại DLT; consumer dừng xử lý record đó và cần được vận hành/recovery theo chính sách offset |
| NO_DLT | Không cấu hình DLT; sau khi hết retry attempts, luồng xử lý kết thúc theo cấu hình này |

Cấu hình ví dụ:

~~~java
import org.springframework.kafka.retrytopic.DltStrategy;

@RetryableTopic(
        attempts = "4",
        dltProcessingFailureStrategy = DltStrategy.FAIL_ON_ERROR)
@KafkaListener(topics = "orders.events", groupId = "order-service")
public void onOrderEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

Import DltStrategy từ org.springframework.kafka.retrytopic. Nếu cùng một class có nhiều listener gắn @RetryableTopic, một phương thức @DltHandler trong class đó được dùng chung cho các listener; nếu cần xử lý DLT khác nhau, tách listener class hoặc cấu hình handler bằng RetryTopicConfigurationBuilder.

## 14. Replay record từ DLT

Replay là một thao tác vận hành có thể tạo side effect lần nữa. Trước khi replay:

1. Xác định nguyên nhân ban đầu đã được sửa.
2. Kiểm tra eventId, key, sequence và schema.
3. Quyết định replay vào topic gốc hay topic phục hồi riêng.
4. Giữ nguyên eventId và metadata gốc.
5. Kiểm tra consumer idempotency để tránh áp dụng lại side effect.
6. Ghi audit ai replay, lúc nào, số lượng bao nhiêu và từ DLT nào.
7. Theo dõi lag và kết quả sau replay.

Không replay toàn bộ DLT nhiều lần bằng cách copy record thủ công mà không có manifest. Cần lưu danh sách eventId đã replay để có thể đối chiếu và tránh lặp ngoài ý muốn.

## 15. Retry topic và consumer concurrency

Retry topics có listener container riêng. Concurrency của topic chính và retry listener có thể được cấu hình theo năng lực xử lý, nhưng tăng concurrency không đảm bảo ordering. Với retry topic có nhiều partition, các member chia partition theo consumer group của framework.

Điều cần chú ý:

- Đừng để retry consumer có concurrency lớn hơn khả năng downstream; retry có thể tạo một đợt tải dồn khi dependency phục hồi.
- Dùng backoff/jitter để tránh retry storm.
- Theo dõi retry topic lag và tuổi record cũ nhất.
- Bảo đảm partition count và key routing phù hợp.
- Giới hạn max.poll.records và thời gian xử lý để tránh rebalance không cần thiết.
- Không giả định record cùng key ở main và retry topic được xử lý tuần tự bởi cùng một thread.

## 16. Các giới hạn kỹ thuật của non-blocking retry

@RetryableTopic có những giới hạn cần kiểm tra trước khi chọn:

| Giới hạn | Tác động |
|---|---|
| Không giữ ordering của topic gốc | Record sau có thể vượt record đang retry |
| Không hỗ trợ batch listener | Không dùng trực tiếp cho listener nhận cả batch ConsumerRecords/List payload |
| Không kết hợp với container transactions | Không dùng non-blocking retry như một phần của container transaction consume-process-commit |
| Cần retry/DLT topics | Tăng số topic, partition, ACL, retention và chi phí vận hành |
| Có thể tạo retry storm | Downstream phục hồi có thể nhận nhiều retry cùng lúc |
| Retry có thể phát lại side effect | Consumer/service phải idempotent |
| Delay phụ thuộc scheduler/backoff và tải consumer | Thời gian thực tế có thể muộn hơn delay cấu hình |
| Replay DLT không tự bảo đảm ordering | Cần quy trình replay và sequence guard |

Non-blocking retry được thiết kế cho record listener. Nếu ứng dụng dùng batch listener, container transaction hoặc cần strict ordering, chọn chiến lược khác hoặc thiết kế riêng sau khi xác minh khả năng của phiên bản Spring Kafka đang chạy.

## 17. Phân biệt @RetryableTopic với DefaultErrorHandler

| Tiêu chí | @RetryableTopic | DefaultErrorHandler blocking retry |
|---|---|---|
| Cách retry | Chuyển record sang retry topic | Thử lại trong container hiện tại |
| Partition gốc | Tiếp tục đọc sau khi chuyển record | Bị chặn trong lúc retry |
| Ordering | Có thể thay đổi | Giữ thứ tự partition tốt hơn |
| Hạ tầng | Cần retry topics và DLT | Có thể dùng recoverer/DLT nhưng không cần delay topics cho retry |
| Backoff dài | Không giữ partition gốc trong thời gian chờ | Partition bị chặn |
| Phù hợp | Event độc lập, throughput cần tiếp tục | Strict ordering hoặc lỗi ngắn hạn |

Ví dụ blocking retry với DefaultErrorHandler:

~~~java
import com.example.orders.event.OrderEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class BlockingRetryConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {
        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);
        FixedBackOff backOff = new FixedBackOff(1000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
~~~

Đoạn code minh họa thử lại hai lần sau lần giao đầu, mỗi lần chờ một giây; sau đó recoverer gửi record sang topic có hậu tố .DLT theo resolver mặc định. Listener muốn dùng factory này khai báo containerFactory = "orderListenerFactory". Kiểm tra exception classification và seek/ack behavior theo phiên bản Spring Kafka.

## 18. Retry và idempotency

Một record có thể được giao lại vì:

- Listener thất bại và Spring Kafka chuyển record sang retry topic.
- Retry listener xử lý xong nhưng chết trước khi commit offset.
- DLT handler xử lý xong nhưng chết trước khi commit.
- Consumer group rebalance hoặc process restart.
- Người vận hành replay DLT.

Vì vậy, handler phải idempotent. Một mẫu phổ biến là lưu eventId trong bảng inbox với unique constraint, rồi cập nhật dữ liệu nghiệp vụ trong cùng database transaction:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong transaction:

1. Insert eventId bằng INSERT ... ON CONFLICT DO NOTHING.
2. Nếu insert thành công, thực hiện side effect.
3. Nếu eventId đã tồn tại, bỏ qua side effect.
4. Commit database transaction rồi để listener hoàn tất acknowledgement.

Không tách insert inbox và cập nhật nghiệp vụ thành hai transaction. Nếu event được đánh dấu processed trước nhưng side effect chưa commit, retry sau có thể bị bỏ qua dù nghiệp vụ chưa hoàn tất.

## 19. Retry với external service và circuit breaker

Retry topic không nên là cơ chế duy nhất để bảo vệ downstream. Nếu HTTP service đang lỗi diện rộng, mọi event chuyển sang retry có thể tạo đợt gọi lại lớn khi service phục hồi.

Kết hợp:

- Timeout hữu hạn cho HTTP/database.
- Circuit breaker để ngừng gọi dependency đang lỗi.
- Backoff exponential và jitter.
- Giới hạn concurrency và bulkhead.
- Idempotency key theo eventId.
- Retry budget và DLT khi vượt ngưỡng.
- Rate limit khi drain retry backlog.

Không retry lỗi authentication, invalid payload hoặc lỗi cấu hình vô hạn. Các lỗi này cần alert và can thiệp thay vì tăng số lần gọi.

## 20. Quan sát retry pipeline

Dashboard nên có metric riêng cho từng topic chính, retry topic và DLT:

| Metric | Ý nghĩa |
|---|---|
| main_listener_success_total | Số record xử lý thành công trên topic chính |
| main_listener_failure_total | Số record lỗi trên topic chính |
| retry_publish_total | Số record được chuyển sang retry |
| retry_consume_total | Số lần retry listener nhận record |
| retry_topic_lag | Khoảng cách offset của retry consumer |
| retry_record_age | Tuổi của record retry lâu nhất |
| retry_attempt_count | Phân bố số lần thử |
| dlt_publish_total | Số record chuyển DLT |
| dlt_consumer_lag | DLT backlog chưa được xử lý/audit |
| dlt_handler_failure_total | Lỗi trong DLT handler |
| processing_latency | Thời gian xử lý nghiệp vụ |
| duplicate_event_total | Số eventId đã xử lý trước đó |
| sequence_gap_total | Số lần phát hiện sequence gap |

Consumer lag của topic chính có thể thấp trong khi retry backlog đang tăng. Vì vậy, không chỉ theo dõi group của topic gốc; cần theo dõi cả retry topics và DLT. Cảnh báo theo tuổi record và tốc độ tăng backlog, không chỉ theo tổng số offset.

## 21. Lab: chứng minh non-blocking retry làm thay đổi thứ tự

Mục tiêu: tạo một event lỗi tạm thời, xác nhận nó được chuyển retry topic và event tiếp theo vẫn được xử lý trên topic chính.

### Bước 1: tạo topic

Tạo orders.events và các retry/DLT topics theo tên thực tế mà ứng dụng sinh ra. Trong lab một broker, replication factor có thể là 1; môi trường nhiều broker cần replication factor phù hợp.

### Bước 2: viết service mô phỏng lỗi

~~~java
import com.example.orders.event.OrderEvent;
import com.example.orders.error.TemporaryPaymentException;
import org.springframework.stereotype.Service;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class OrderService {
    private final Set<String> failedOnce = ConcurrentHashMap.newKeySet();

    public void process(OrderEvent event) {
        if (event.sequence() == 10 && failedOnce.add(event.eventId())) {
            throw new TemporaryPaymentException(
                    "Simulated downstream timeout", null);
        }

        System.out.printf("PROCESSED order=%s sequence=%d eventId=%s%n",
                event.orderId(), event.sequence(), event.eventId());
    }
}
~~~

Trong lab, failedOnce mô phỏng event chỉ lỗi một lần trong cùng process. Restart ứng dụng có thể reset set này; nếu muốn mô phỏng lỗi bền vững hoặc nhiều lần, dùng database/test stub với trạng thái rõ ràng.

### Bước 3: gửi event cùng key

Gửi sequence 10, 11 và 12 cho cùng orderId. Bảo đảm producer dùng orderId làm Kafka key và gửi theo thứ tự.

### Bước 4: quan sát listener

Kết quả mong đợi:

- Sequence 10 lỗi ở lần đầu và được chuyển retry topic.
- Topic chính tiếp tục xử lý sequence 11 và 12.
- Sau backoff, sequence 10 được retry và xử lý thành công.
- Log thể hiện thứ tự hoàn tất 11, 12, 10.

### Bước 5: thử strict ordering

Thay @RetryableTopic bằng blocking retry phù hợp và chạy lại. Khi sequence 10 lỗi, partition topic chính chờ retry; sequence 11 và 12 không được xử lý trước khi sequence 10 thành công hoặc được recover.

### Bước 6: kiểm tra DLT

Thay service để sequence 10 luôn lỗi. Sau khi hết attempts, xác nhận record xuất hiện ở DLT cùng eventId, key và metadata gốc. Sửa dependency rồi replay có kiểm soát.

### Bước 7: kiểm tra duplicate

Cho listener thực hiện side effect thành công rồi mô phỏng process dừng trước khi offset được xác nhận. Khi record được giao lại, xác nhận inbox/idempotency ngăn side effect bị áp dụng lần hai.

## 22. Troubleshooting

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
|---|---|---|
| Retry topic không được tạo | autoCreateTopics=false hoặc thiếu quyền Create | Provision topic trước và cấp ACL đúng |
| Listener không nhận retry record | Retry topic thiếu partition, group/container chưa khởi động hoặc backoff chưa đến hạn | Kiểm tra topic, assignment, header thời gian và retry lag |
| Record đi thẳng DLT | Exception bị phân loại non-retryable hoặc attempts đã hết | Kiểm tra include/exclude và cause traversal |
| Event sau xử lý trước event lỗi | Non-blocking retry giải phóng partition gốc | Dùng blocking retry hoặc sequence-aware consumer |
| Retry backlog tăng đột biến | Downstream phục hồi và nhiều record đến hạn cùng lúc | Thêm jitter, giới hạn concurrency/rate và theo dõi retry age |
| DLT handler lặp lại | Handler thất bại trước commit hoặc side effect không idempotent | Dùng inbox/audit idempotency và xử lý lỗi DLT rõ ràng |
| Duplicate side effect | Replay/retry nhưng nghiệp vụ không idempotent | Dùng eventId và unique constraint |
| Retry topic không giữ đúng partition mapping | Partition count hoặc routing không tương thích | Kiểm tra số partition, key và naming/topology |
| Listener startup báo lỗi cấu hình | Phiên bản Spring Kafka không hỗ trợ thuộc tính hoặc loại listener đang dùng | Đối chiếu API version và giới hạn batch/transaction |

## 23. Cấu hình nâng cao và tài liệu chính thức

Với cấu hình đơn giản, gắn @RetryableTopic trực tiếp vào phương thức @KafkaListener là đủ để Spring Kafka tạo retry infrastructure và các listener tương ứng. Khi cần cấu hình dùng chung hoặc tùy chỉnh component, có thể dùng RetryTopicConfiguration bean hoặc mở rộng RetryTopicConfigurationSupport. Trong Spring Kafka 3.3, @EnableKafkaRetryTopic có thể được dùng để đưa retry infrastructure vào application context; nếu chọn cách mở rộng RetryTopicConfigurationSupport thì không đồng thời bật @EnableKafkaRetryTopic để tránh tạo bean trùng.

Chỉ chọn một cơ chế cấu hình global. Với nhiều listener cùng topic, thống nhất retry configuration và naming để tránh nhiều annotation xung đột hoặc cùng dùng chung retry topics ngoài ý muốn.

Tài liệu đối chiếu theo Spring Kafka 3.3:

- [Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic.html)
- [How the Pattern Works](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic/how-the-pattern-works.html)
- [Configuration](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic/retry-config.html)
- [Topic Naming](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic/topic-naming.html)
- [DLT Strategies](https://docs.spring.io/spring-kafka/reference/3.3/retrytopic/dlt-strategies.html)

## 24. Tiêu chí hoàn thành

- Giải thích được khác biệt giữa blocking và non-blocking retry.
- Cấu hình @RetryableTopic với attempts và backoff.
- Phân loại exception retryable và non-retryable.
- Tạo và cấu hình retry topics cùng DLT.
- Giữ eventId, key, sequence và metadata gốc qua retry.
- Giải thích vì sao non-blocking retry không giữ ordering.
- Chọn blocking retry hoặc sequence guard khi nghiệp vụ yêu cầu strict ordering.
- Xử lý DLT và replay có audit.
- Thiết kế consumer idempotent và giám sát retry backlog.
- Nêu được giới hạn batch listener và container transaction của non-blocking retry.

## 25. Ghi nhớ

| Khái niệm | Vai trò |
|---|---|
| @RetryableTopic | Chuyển record lỗi sang retry topic để xử lý sau |
| attempts | Tổng số lần giao thử, bao gồm lần đầu |
| Backoff | Khoảng chờ giữa các lần thử |
| Retry topic | Nơi lưu record chờ lần thử tiếp theo |
| DLT | Nơi cách ly record hết retry hoặc không retry |
| Non-blocking | Topic gốc tiếp tục xử lý record sau khi record lỗi được chuyển đi |
| Ordering limit | Event sau có thể hoàn tất trước event đang retry |
| Idempotency | Ngăn side effect lặp khi event được giao lại |
| Sequence guard | Bảo vệ thứ tự nghiệp vụ theo aggregate |
| Blocking retry | Giữ partition chờ xử lý record lỗi, phù hợp hơn với strict ordering |

@RetryableTopic giúp ứng dụng tiếp tục tiêu thụ khi một record gặp lỗi tạm thời, nhưng đổi lại record có thể được xử lý ngoài thứ tự ban đầu. Hãy phân loại exception, đặt attempts/backoff hợp lý, provision retry/DLT topics, giữ eventId và sequence, rồi chọn blocking retry hoặc cơ chế ordering riêng khi nghiệp vụ yêu cầu thứ tự nghiêm ngặt.
