# Cấu hình retry topic trong Spring Kafka

Khi một consumer xử lý Kafka message thất bại do API downstream timeout, database tạm mất kết nối hoặc hệ thống đích đang giới hạn lưu lượng, có hai lựa chọn phổ biến: **thử lại ngay trên consumer thread** hoặc **chuyển message sang một topic retry để xử lý lại sau một khoảng thời gian**. Lựa chọn thứ hai giúp tránh giữ consumer thread chờ quá lâu, nhưng đòi hỏi cấu hình topic, consumer, DLT, quyền Kafka và chính sách vận hành đúng.

Bài **“Cấu hình retry topic”** thuộc **Spring Kafka Reliability Operations → Deployment và cấu hình**. Đây không chỉ là hướng dẫn thêm annotation `@RetryableTopic`: một hệ thống production phải biết **bao nhiêu lần retry, trì hoãn bao lâu, lỗi nào được retry, retry và DLT topics được tạo ở đâu, ai có quyền publish/consume, theo dõi backlog thế nào và làm gì khi chuyển tiếp message thất bại**.

```text
Producer
   |
   v
orders.events  ----> listener chính
                          |
                     xử lý thất bại
                          |
                   retryable exception?
                     /            \
                   Có             Không
                    |               |
                    v               v
 orders.events-retry-0              DLT
        |                             ^
   đợi backoff                      |
        v                           |
   listener retry                   |
        |                           |
    vẫn lỗi? -------- Có --> retry topic kế tiếp
        |                           |
       Không                        +-- hết attempts --> DLT
        |
        v
  xử lý thành công
```

Tên topic trong sơ đồ là ví dụ khi chọn cách đặt suffix bằng **attempt index**. Topic thực tế có thể mang suffix theo delay hoặc dùng chung một topic cho nhiều khoảng retry, tùy chính sách và phiên bản Spring Kafka.

## 1. Phân biệt blocking retry, retry topic và DLT

| Khái niệm | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| **Blocking retry** | Cùng consumer container xử lý lại record với `BackOff`, có thể giữ hoặc hoãn tiến độ partition hiện tại | Lỗi ngắn, số lần thử ít, cần giữ thứ tự chặt hơn |
| **Non-blocking retry topic** | Khi lỗi, record được **publish sang topic khác** cùng thông tin về thời điểm đủ điều kiện xử lý; listener retry tiêu thụ sau delay | Downstream có thể phục hồi sau vài giây/phút, không muốn chặn consumer chính |
| **Dead Letter Topic (DLT)** | Nơi chứa record không xử lý được sau khi hết policy retry hoặc khi gặp lỗi không retryable | Cần điều tra, cảnh báo, lưu bằng chứng và reprocess có kiểm soát |
| **Application quarantine** | Kho lỗi nghiệp vụ riêng như database/object storage | Cần workflow xử lý dữ liệu, trạng thái review, mã lỗi và audit |
| **Replay/reprocess** | Chủ động chạy lại từ DLT hoặc nguồn gốc sau khi sửa lỗi | Một quy trình nghiệp vụ mới, cần chống duplicate |

Trong Spring Kafka, `@RetryableTopic` và `RetryTopicConfiguration` hỗ trợ mô hình **non-blocking retry**. Spring Kafka thường tạo/đăng ký các listener dành cho retry và DLT, đồng thời dùng một `KafkaTemplate` để chuyển tiếp record qua các topic.

**Retry topic không phải queue nội bộ JVM.** Message được ghi vào Kafka; vì vậy tồn tại qua restart của process khi broker, replication và retention được vận hành đúng. Ngược lại, trạng thái callback hoặc biến `AtomicInteger` trong JVM không bền vững.

### 1.1. Những giới hạn phải biết ngay

- **Không giữ bảo đảm thứ tự của topic gốc.** Một record bị chuyển sang retry topic có thể được xử lý sau các record đến sau trên topic chính.
- **Non-blocking retry topic không hỗ trợ batch listener** theo mô hình `List<ConsumerRecord<...>>`; sử dụng record listener nếu muốn áp dụng `@RetryableTopic` trực tiếp.
- **Không kết hợp non-blocking retries với Kafka container transactions.** Nếu đang dùng container transaction / EOS, cần đánh giá phương án retry khác phù hợp.
- Retry không tạo **exactly-once side effect** cho database, HTTP API hoặc hệ thống thanh toán. Consumer có thể xử lý lại một event; business handler cần idempotency.
- Message có thể bị chuyển tiếp nhiều lần; DLT không phải cơ chế loại trùng và không tự sửa dữ liệu lỗi.

Đặc biệt, khi nghiệp vụ bắt buộc A phải xử lý xong trước B trong cùng partition, chuyển A sang retry topic và tiếp tục xử lý B trên topic gốc có thể làm sai logic. Khi đó cân nhắc blocking retry ngắn, dừng/pause partition có điều phối hoặc thiết kế state machine chịu được out-of-order.

## 2. Mô hình hoạt động của non-blocking retries

Giả sử listener xử lý `orders.events`, `attempts=4` và exponential backoff `2s, 4s, 8s`:

```text
T0              orders.events: order-123
                attempt 1 -> RemoteUnavailableException
                      |
                      v
T0 + khoảng 2s  orders.events-retry-0
                attempt 2 -> vẫn lỗi
                      |
                      v
T0 + khoảng 6s  orders.events-retry-1
                attempt 3 -> vẫn lỗi
                      |
                      v
T0 + khoảng 14s orders.events-retry-2
                attempt 4 -> vẫn lỗi
                      |
                      v
                orders.events-dlt
```

Các mốc là **minh họa độ trễ cộng dồn**, không phải SLA thời điểm chính xác. Broker I/O, consumer lag, partition bị pause vì record chưa đến hạn, scheduler và downtime có thể làm thời gian thực dài hơn. Non-blocking retries dựa trên timestamp/backoff để xác định thời điểm record đủ điều kiện xử lý; trong lúc chưa đến hạn, consumer của retry topic có thể **pause partition** rồi tiếp tục poll để duy trì consumer group.

Một `attempt` thường bao gồm **lần xử lý ban đầu**. Với `attempts="4"` trong ví dụ, một record có thể được listener thử tối đa bốn lần theo policy non-blocking: một lần ở topic gốc và ba lần qua retry topics, trừ các tình huống timeout/exclusion/fatal classification khiến chuyển DLT sớm.

### 2.1. Commit offset ở topic gốc không đồng nghĩa business success

Khi bản ghi được chuyển tiếp thành công từ topic gốc sang retry topic, container có thể hoàn tất xử lý nhánh lỗi ở topic gốc theo cơ chế error handler và tiếp tục với record khác. Điều đó **không có nghĩa yêu cầu nghiệp vụ đã thành công**; nó mới được chuyển sang một trạng thái chờ retry.

```text
orders.events offset 20
    |
    +-- publish orders.events-retry-0 thành công
    |
    +-- consumer chính tiếp tục offset 21, 22, ...

order-123 vẫn chưa hoàn thành nghiệp vụ
```

Vì vậy khi đối soát, cần phân biệt **processed successfully**, **scheduled for retry**, **pending in DLT** và **reprocessed after manual review**. Chỉ nhìn consumer lag của topic gốc có thể khiến dashboard báo “không còn backlog” trong khi nhiều bản ghi vẫn nằm ở retry topics.

## 3. Chuẩn bị project và dependency

Các đoạn code dưới đây dùng **Java 17+, Spring Boot 3.x và Spring Kafka 3.3.x** làm mốc minh họa. Cơ chế retry topic còn tồn tại ở các phiên bản mới hơn, nhưng default topic reuse, API hoặc package có thể thay đổi theo major/minor release. Luôn đối chiếu Spring Kafka version do Spring Boot BOM của dự án quản lý.

Trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}
```

Không tự thêm một phiên bản `spring-kafka` khác hoàn toàn dependency management của Spring Boot chỉ để dùng annotation mới. Spring Retry là thành phần liên quan tới backoff; trong một số cấu hình/version, nó có thể cần hiện diện dưới dạng dependency phù hợp, hãy dùng BOM và tài liệu của phiên bản thực tế.

### 3.1. Cấu hình kết nối Kafka

`application.yml` cho message dạng string:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: orders-service
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true

    listener:
      ack-mode: record
```

`acks: all` và producer idempotence tăng độ tin cậy publish trong phạm vi Kafka producer, nhưng **không bảo đảm một business transaction chỉ được thực hiện một lần** hoặc tự tạo transaction chung với database bên ngoài.

`auto-offset-reset=earliest` có ích khi group chưa có committed offset; nó không buộc mọi lần khởi động đọc lại tất cả message khi group đã có offset. Trong production, lựa chọn `earliest`/`latest` phải thống nhất với chính sách bootstrap và backfill.

`ack-mode: record` là lựa chọn thường được gợi ý cho mô hình retry topic. Nếu dùng manual acknowledgment hoặc `asyncAcks`, phải xem xét thêm cấu hình error handler tương ứng phiên bản và kiểm thử commit/replay thực tế.

## 4. Cách đơn giản nhất: `@RetryableTopic`

Giả sử ứng dụng nhận order ID dạng string, gọi downstream và có thể gặp hai nhóm lỗi:

- `RemoteTemporaryException`: timeout, 503 hoặc nguồn phụ thuộc tạm thời, **được phép retry**.
- `InvalidOrderException`: message sai quy tắc, **không có ích khi retry mà chưa sửa payload**.

Exception nghiệp vụ:

```java
package com.example.kafka;

public class RemoteTemporaryException extends RuntimeException {
    public RemoteTemporaryException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

```java
package com.example.kafka;

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Trong `OrderService`, các ngoại lệ đó do ứng dụng chủ động chuyển đổi từ lỗi HTTP/validation. Không dùng `catch (Exception ex) { throw new RemoteTemporaryException(...); }` cho mọi trường hợp: cách đó có thể biến lỗi lập trình hoặc payload sai thành lỗi retry được, tạo vòng retry không cần thiết.

Listener minh họa:

```java
package com.example.kafka;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.retry.annotation.Backoff;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(OrderConsumer.class);

    private final OrderService orderService;
    private final OrderDeadLetterService deadLetterService;

    public OrderConsumer(
            OrderService orderService,
            OrderDeadLetterService deadLetterService) {
        this.orderService = orderService;
        this.deadLetterService = deadLetterService;
    }

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2000, multiplier = 2.0, maxDelay = 8000),
        include = {RemoteTemporaryException.class},
        exclude = {InvalidOrderException.class},
        retryTopicSuffix = "-retry",
        dltTopicSuffix = "-dlt",
        topicSuffixingStrategy =
            org.springframework.kafka.retrytopic.TopicSuffixingStrategy
                .SUFFIX_WITH_INDEX_VALUE,
        autoCreateTopics = "false",
        kafkaTemplate = "kafkaTemplate"
    )
    @KafkaListener(
        id = "ordersConsumer",
        topics = "orders.events",
        groupId = "orders-service"
    )
    public void consume(
            String orderId,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String receivedTopic) {
        log.info("event=order.consume topic={} orderId={}",
            receivedTopic, orderId);

        orderService.processIdempotently(orderId);
    }

    @DltHandler
    public void onDlt(
            String orderId,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String dltTopic) {
        deadLetterService.recordForReview(orderId, dltTopic);
    }
}
```

`OrderService` và `OrderDeadLetterService` là **service ứng dụng do người học tự triển khai**. Method `processIdempotently` phải ghi kết quả theo business key, ví dụ unique constraint hoặc trạng thái đã xử lý; không phải API sẵn có của Spring Kafka. `recordForReview` nên lưu bản ghi DLT vào một kho audit/quarantine có phân quyền và cơ chế chống ghi lặp.

Trong ví dụ, `autoCreateTopics="false"` có nghĩa **topic phải được platform provision trước khi ứng dụng chạy**. Đây là hướng phù hợp cho các môi trường production giới hạn quyền tạo topic. Nếu chỉ học/demo, có thể đặt `"true"` và cấu hình partition/replication theo broker test.

### 4.1. `attempts` và `@Backoff`

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `attempts` | `"4"` | Số lần thử tổng cộng theo chính sách non-blocking, bao gồm lần đầu |
| `backoff.delay` | `2000` | Độ trễ ban đầu, tính bằng milliseconds |
| `backoff.multiplier` | `2.0` | Nhân độ trễ khi dùng exponential backoff |
| `backoff.maxDelay` | `8000` | Trần độ trễ |
| `include` | `RemoteTemporaryException` | Nhóm exception muốn retry |
| `exclude` | `InvalidOrderException` | Nhóm exception không retry, chuyển theo terminal strategy |
| `retryTopicSuffix` | `"-retry"` | Tiền tố suffix cho topic retry |
| `dltTopicSuffix` | `"-dlt"` | Suffix của DLT |
| `topicSuffixingStrategy` | `SUFFIX_WITH_INDEX_VALUE` | Đặt tên retry topics theo số thứ tự attempt |
| `autoCreateTopics` | `"false"` | Không yêu cầu framework tạo topics qua admin ở startup |
| `kafkaTemplate` | `"kafkaTemplate"` | Bean dùng để publish sang retry topics và DLT |

Mã `@RetryableTopic` có thể sử dụng placeholder, ví dụ `attempts = "${app.kafka.retry.attempts}"`, để tách chính sách từ code sang cấu hình deployment. Tuy vậy, thay các giá trị làm thay đổi **số lượng/tên topic và listener topology**; rollout phải đi kèm thay đổi topic provisioning và kế hoạch xử lý backlog cũ.

### 4.2. Vì sao cần `KafkaTemplate` phù hợp?

Retry infrastructure phải có **producer** để forward record sang topic retry/DLT. Trong cấu hình Spring Boot thông thường với string serializer, `KafkaTemplate<String, String>` mặc định có thể được đăng ký dưới tên `kafkaTemplate`.

Nếu dùng JSON/Avro/Protobuf, phải bảo đảm producer dùng để retry có serializer tương thích với record chuyển tiếp. Đặc biệt khi dùng `ErrorHandlingDeserializer`, payload của record lỗi deserialization có thể là **raw `byte[]`**; một KafkaTemplate chỉ biết serialize DTO thông thường sẽ không gửi được record đó vào DLT. Trường hợp này cần cấu hình serializer theo nhiều kiểu payload, ví dụ `DelegatingByTypeSerializer`, và kiểm thử cụ thể.

Đừng coi `@RetryableTopic` là cách tự sửa một producer factory sai serializer. Việc forward cũng có thể thất bại vì ACL, timeout, broker unavailable hoặc message vượt giới hạn kích thước.

## 5. Xác định các retry topics cần provision

Với ví dụ:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2000, multiplier = 2.0, maxDelay = 8000),
    topicSuffixingStrategy =
        TopicSuffixingStrategy.SUFFIX_WITH_INDEX_VALUE,
    retryTopicSuffix = "-retry",
    dltTopicSuffix = "-dlt",
    autoCreateTopics = "false"
)
```

Trong mô hình **mỗi lần retry dùng một topic riêng**, danh sách topic dự kiến:

```text
orders.events
orders.events-retry-0
orders.events-retry-1
orders.events-retry-2
orders.events-dlt
```

Có ba retry attempts sau lần xử lý đầu nên cần ba destinations retry. Nếu chuyển sang suffix theo delay, tên có thể chứa `2000`, `4000`, `8000`; nếu dùng **reuse topic** cho cùng khoảng delay, số topic thay đổi. **Không hard-code danh sách trên mà không cố định `topicSuffixingStrategy`, reuse strategy và Spring Kafka version**.

### 5.1. Version ảnh hưởng đến số retry topics

Chính sách dùng chung retry topic cho các attempts có cùng delay đã được mở rộng qua các phiên bản. Ví dụ Spring Kafka **4.1** thay đổi default theo hướng **reuse một retry topic cho cùng interval**, trong khi các phiên bản 3.x có những mặc định/chiến lược khác. Vì thế khi upgrade:

- Kiểm tra topic graph thực tế được framework suy ra.
- Provision những topic mới cần dùng trước deployment.
- Không xóa retry topics cũ khi chúng còn backlog.
- Cân nhắc thời gian giữ lại listener/consumer cho topology cũ trong giai đoạn migration.
- Test record được gửi từ phiên bản trước vẫn được xử lý/điều tra đúng sau rollout.

Với cùng backoff policy, **mỗi lần thay chiến lược topic reuse có thể thay đổi naming và luồng xử lý**; đây là thay đổi deployment chứ không chỉ là refactor annotation.

## 6. Tạo retry topics và DLT ở môi trường production

Trong cluster production, platform team thường quản lý Kafka topics bằng IaC hoặc thủ tục có phê duyệt. Lý do là tạo topic liên quan **partition count, replication factor, retention, ACL, quota, monitoring và data ownership**.

Ví dụ Kafka CLI minh họa (chạy từ host có Kafka CLI và kết nối được cluster):

```bash
KAFKA_BOOTSTRAP=broker1:9092

for topic in \
  orders.events \
  orders.events-retry-0 \
  orders.events-retry-1 \
  orders.events-retry-2 \
  orders.events-dlt
do
  kafka-topics.sh \
    --bootstrap-server "$KAFKA_BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 3 \
    --replication-factor 3
done
```

Lệnh minh họa giả định cluster có **ít nhất ba brokers** hỗ trợ replication factor 3 và không yêu cầu auth CLI bổ sung. Ở local một broker, `--replication-factor 3` sẽ thất bại; phải giảm xuống giá trị cluster cho phép. Với SASL_SSL/mTLS, thêm cấu hình `--command-config` phù hợp; không ghi password/token vào command history nếu môi trường yêu cầu bảo mật.

**Không tự giảm replication factor ở production chỉ để script tạo topic thành công.** Cần cấu hình đúng khả năng và SLA của cluster.

### 6.1. Có cần `partitions` bằng topic gốc?

Kafka topic retry chứa bản ghi cùng key và thông tin nguồn. Nếu recoverer giữ nguyên partition khi forward, **partition đích phải tồn tại**. Vì vậy một nguyên tắc thực tế là số partitions của retry/DLT **ít nhất bằng số partitions của topic gốc**, hoặc phải có chiến lược ánh xạ partition rõ ràng.

Nếu topic gốc có 12 partitions mà retry topic chỉ có 1 partition, producer gửi tới partition số 7 có thể bị lỗi *invalid partition*, tùy cấu hình recoverer. Đừng mặc định `numPartitions="1"` của auto-create luôn phù hợp production.

Tăng số partitions của topic gốc sau deployment cũng có thể yêu cầu tăng partitions ở toàn bộ retry/DLT topics, cập nhật monitoring và kiểm tra thứ tự/idempotency. Kafka không cho giảm số partitions một cách đơn giản; chọn partition topology có kế hoạch dài hạn.

### 6.2. Retention riêng cho retry và DLT

| Loại topic | Mục đích | Cân nhắc retention |
| --- | --- | --- |
| Main | Luồng message chính | SLA replay từ nguồn và dung lượng |
| Retry | Lưu message đang chờ backoff/chờ downstream hồi phục | Phải dài hơn tổng thời gian delay tối đa **cộng downtime và thời gian drain** |
| DLT | Lưu message chưa xử lý được, chờ phân loại/reprocess | Theo quy trình incident, SLA review và nghĩa vụ lưu trữ |

Không thiết lập retention retry topic chỉ bằng đúng `maxDelay`. Một record có thể đến retry topic rồi phải chờ vì consumer đang pause, lag tăng, cluster failover hoặc deploy bị rollback. Với DLT, nếu không có người xử lý mà retention quá ngắn, bằng chứng lỗi có thể biến mất trước khi kịp review.

Tránh bật compaction trên retry/DLT chỉ để “tiết kiệm dung lượng” khi nghiệp vụ cần **giữ từng event lỗi**. Compaction có thể loại bản ghi cùng key; chỉ dùng khi dữ liệu và quy tắc retention thực sự cho phép.

### 6.3. Auto-create ở dev/test và pre-provision ở production

| Cách làm | Ưu điểm | Rủi ro |
| --- | --- | --- |
| `autoCreateTopics="true"` | Đơn giản trong demo và integration test | App cần quyền tạo topic; dễ sai partition/replication/retention |
| `autoCreateTopics="false"` + IaC/CLI | Chủ động cấu hình/ACL và kiểm soát thay đổi | Phải bảo đảm các topic tồn tại trước rollout |
| Spring `NewTopic` beans + `KafkaAdmin` | Quản lý bằng Java config | Vẫn cần quyền Create/Alter; tránh trùng chính sách với IaC |

Đừng nhầm `@RetryableTopic.autoCreateTopics` với Kafka client `allow.auto.create.topics`: chúng liên quan hai cơ chế khác nhau. Khi production đã giao platform quản lý topics, không dựa vào broker auto-create ngầm để tạo đủ retry/DLT topics.

## 7. Quyền truy cập ACL/IAM cho retry topic

Khi một record thất bại, Spring Kafka dùng Kafka producer để **publish sang retry topic hoặc DLT**, đồng thời tạo các consumer container riêng đọc từ chúng. Vì vậy quyền chỉ `READ` main topic là không đủ.

| Principal | Quyền thường cần | Phạm vi |
| --- | --- | --- |
| Consumer ứng dụng | `READ` topic gốc và retry/DLT topics theo policy | `orders.events`, `orders.events-retry-*`, `orders.events-dlt` |
| Consumer group | Quyền `READ`/group management theo Kafka ACL | Group chính và các group phụ được tạo cho retry/DLT |
| Retry forwarding producer | `WRITE` trên retry/DLT topics | Chỉ các destinations tương ứng |
| Kafka admin/provisioning | `CREATE`, `DESCRIBE`, `ALTER` khi cần | Cluster/topic resources theo policy |
| DLT review/reprocess service | `READ` DLT, `WRITE` topic đích được phép | Chỉ những topic của workflow xử lý lỗi |

Danh sách hành động cụ thể phụ thuộc Kafka broker/provider và nền tảng cloud (MSK, Confluent Cloud, v.v.). Một số môi trường có quyền `DESCRIBE`, `CREATE`, `WRITE`, `READ`, quyền transactional ID hoặc schema registry riêng. Cần kiểm tra policy thực tế thay vì sao chép nguyên một bộ ACL cho mọi cluster.

### 7.1. Triệu chứng khi ACL thiếu

```text
Main listener nhận order-123.
Handler ném RemoteTemporaryException.
Forwarder muốn publish orders.events-retry-0.
Broker từ chối: TopicAuthorizationException.

=> Message chưa chắc đã được chuyển sang retry topic.
=> Container error-handling có thể tiếp tục thất bại.
=> Không được ghi nhận order-123 là "đã an toàn trong retry".
```

Khi kiểm tra deployment, đừng chỉ test producer gửi message lên main topic. Cần **gây lỗi có chủ đích để thử chính xác đường forward** sang retry và DLT bằng principal của ứng dụng production-like.

## 8. Chọn backoff cho đúng tính chất lỗi

Retry policy nên xuất phát từ **khả năng phục hồi của downstream** và **SLA xử lý**, không phải chỉ chọn số lớn để “thử cho chắc”.

### 8.1. Fixed backoff

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 5000)
)
```

Ví dụ dùng delay cố định khoảng 5 giây giữa các attempts. Phù hợp khi hệ thống đích phục hồi nhanh hoặc có rate limit đơn giản. Nếu hàng triệu message lỗi cùng lúc, fixed backoff có thể khiến chúng cùng quay lại ở một thời điểm và tiếp tục gây tải đột biến.

### 8.2. Exponential backoff

```java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1000,
        multiplier = 2.0,
        maxDelay = 16000
    )
)
```

Các khoảng delay tăng dần (ví dụ 1, 2, 4, 8 giây cho bốn retry attempts). Hữu ích khi downstream cần thời gian hồi phục và việc thử liên tục làm trầm trọng thêm sự cố. Nhưng không nên dùng exponent vô hạn; cần ngưỡng tổng thời gian và một điểm kết thúc là DLT/cảnh báo.

### 8.3. Random/jitter backoff

Khi nhiều consumer cùng retry sau outage, jitter giúp giảm **retry storm**. Spring Kafka hỗ trợ các chính sách backoff khác nhau, trong đó có random exponential hoặc custom backoff qua cấu hình. API cụ thể phụ thuộc phiên bản; với chính sách đặc thù, có thể dùng `RetryTopicConfigurationBuilder` hoặc cấu hình mở rộng theo tài liệu tương ứng.

Tránh dùng một lịch retry quá dày nếu hệ thống đích có rate limit cứng. Với HTTP 429/`Retry-After`, cần cân nhắc hợp đồng phản hồi và lịch xử lý được phép; không mặc định annotation tự hiểu mọi header downstream.

### 8.4. Total timeout và giới hạn attempts

Ngoài số lần thử, có thể đặt **timeout toàn bộ chuỗi retry**:

```java
@RetryableTopic(
    attempts = "10",
    timeout = "60000",
    backoff = @Backoff(delay = 1000, multiplier = 2.0, maxDelay = 10000)
)
```

Trong Spring Kafka, `timeout` xác định ngưỡng thời gian từ khi bắt đầu xử lý retry để quyết định có nên tiếp tục retry sau khi lỗi xảy ra hay chuyển DLT. Nó không phải cam kết toàn bộ record sẽ xử lý xong trong chính xác 60 giây và không phải TTL vật lý của Kafka message. Backlog/consumer outage có thể khiến thời điểm xử lý tiếp theo muộn hơn nhiều.

Lựa chọn `attempts` và `timeout` cần thống nhất với SLA, tốc độ downstream, khả năng vận hành DLT và retention. Với lỗi không bao giờ phục hồi nếu payload không đổi, không nên kéo dài chuỗi retry chỉ vì muốn tránh đưa vào DLT.

## 9. Phân loại exception: retry được hay không?

Đây là quyết định quan trọng nhất của retry topic. Một `RuntimeException` bất kỳ không tự chứng minh cần retry.

| Loại lỗi | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Tạm thời | HTTP 503, connection timeout, rate limiting có thể phục hồi | Retry có giới hạn và backoff |
| Tranh chấp ngắn | Deadlock/optimistic lock conflict trong tình huống cụ thể | Retry an toàn nếu handler idempotent |
| Dữ liệu sai | Schema invalid, required field thiếu, amount âm | DLT/quarantine sớm; sửa payload hoặc source |
| Sai cấu hình | Topic không tồn tại, credential lỗi, schema registry sai | Cảnh báo, xử lý deployment; retry record thường không giải quyết được |
| Lỗi serialization/deserialization | Payload không đọc được, unknown schema | Điều tra serializer, error handler/DLT với raw payload |
| Lỗi lập trình | `NullPointerException`, xử lý sai trạng thái | Fail/cảnh báo và sửa code; tránh retry tràn lan |
| Lỗi không rõ kết quả | API timeout sau khi server đã commit | Retry **chỉ khi** có idempotency hoặc kiểm tra trạng thái đích |

Trong code, nên dùng exception lớp ứng dụng để phân loại:

```java
try {
    downstreamClient.reserve(orderId);
} catch (DownstreamUnavailableException ex) {
    throw new RemoteTemporaryException(
        "Temporary downstream failure", ex);
}
```

Mẫu minh họa giả định `DownstreamUnavailableException` và `downstreamClient` do dự án cung cấp. Nếu một request có thể đã tạo side effect, `reserve` nên dùng **idempotency key ổn định** để retry không nhân đôi giữ hàng/thanh toán.

### 9.1. Nested exception và `traversingCauses`

Đôi khi một exception retryable bị bọc:

```text
ListenerExecutionFailedException
    └── ApplicationException
          └── RemoteTemporaryException
```

Spring Kafka cho phép cấu hình `traversingCauses` để classifier xét cause chain theo policy. Khi cần, đặt:

```java
@RetryableTopic(
    include = {RemoteTemporaryException.class},
    traversingCauses = "true"
)
```

Đừng bật một cách máy móc khi wrapper exception có ý nghĩa nghiệp vụ khác. Test cả trường hợp exception trực tiếp và exception lồng nhau, để chắc chắn record không vào DLT ngoài ý muốn.

### 9.2. Fatal exceptions mặc định

Spring Kafka có nhóm exception được xem là **fatal** đối với non-blocking retries, ví dụ một số lỗi deserialization/conversion/argument resolution. Dạng lỗi này thường không tự biến mất sau vài giây nên có thể được chuyển DLT không qua các retry topic. Danh sách và cách customize phụ thuộc phiên bản; không nên tuyên bố rằng `include` sẽ luôn override tất cả fatal classifications trong mọi cấu hình.

Với hệ thống cần behavior đặc thù, có thể mở rộng `RetryTopicConfigurationSupport` và điều chỉnh danh sách fatal theo API version; phải có integration test chứng minh đường định tuyến thực tế.

## 10. DLT: nơi điều tra, không phải thùng rác bỏ mặc

Sau khi hết attempts hoặc gặp lỗi không retryable, record được đưa tới **Dead Letter Topic** theo policy.

```text
orders.events
    |
    +--> 503 timeout -> retry -> retry -> success
    |
    +--> invalid currency -> orders.events-dlt
    |
    +--> 503 timeout -> retry hết -> orders.events-dlt
```

DLT nên có một trong hai chính sách rõ ràng:

1. **Ứng dụng đang chạy DLT consumer** để lưu record vào kho quản lý lỗi, phát alert hoặc tạo ticket.
2. **DLT consumer không tự start**; một dịch vụ review/reprocess riêng đọc và quyết định sau khi được phê duyệt.

Ví dụ handler:

```java
@DltHandler
public void handleDlt(
        String payload,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
    quarantineStore.saveIfAbsent(
        payload,
        topic
    );
}
```

`quarantineStore.saveIfAbsent` là abstraction ứng dụng, phải tự định nghĩa business key/event ID và lưu đủ metadata nguồn. Trong production nên ghi thêm original topic, partition, offset, key, exception class/reason code, timestamps, retry attempts và correlation ID; không log toàn bộ payload nhạy cảm.

### 10.1. Nếu DLT handler cũng lỗi?

Một DLT handler có thể bị lỗi do database lưu quarantine không khả dụng. Spring Kafka có các chiến lược xử lý lỗi DLT, bao gồm **retry lại trên DLT** hoặc **fail** theo cấu hình/version. Không giả định `@DltHandler` chỉ chạy đúng một lần.

Nếu thiết kế DLT consumer lưu dữ liệu rồi gửi email, nên tách phần ghi bền vững và thông báo để tránh một email lỗi làm record bị xử lý lại nhiều lần. Quarantine store cũng cần idempotency.

### 10.2. Không muốn tự động tiêu thụ DLT

Trong Spring Kafka có thuộc tính `autoStartDltHandler`:

```java
@RetryableTopic(
    attempts = "4",
    autoStartDltHandler = "false"
)
@KafkaListener(topics = "orders.events")
public void process(String payload) {
    // ...
}
```

Khi DLT handler không auto-start, message vẫn được publish vào DLT nếu định tuyến và permissions thành công, nhưng ứng dụng không tự chạy container DLT lúc startup. Cần có cơ chế alert/monitoring và runbook để start/review; không dùng cấu hình này rồi bỏ quên DLT không ai đọc.

### 10.3. DLT theo loại exception

Ở những Spring Kafka version hỗ trợ, có thể route từng nhóm lỗi sang DLT riêng, ví dụ schema errors sang `orders.events-schema-dlt`, business errors sang `orders.events-business-dlt`. Cơ chế exception-based DLT routing được bổ sung từ dòng 3.2; triển khai nên dùng annotation/configuration phù hợp version và provision cả custom DLT topics.

Đừng tạo quá nhiều DLT topics chỉ vì mỗi exception class khác nhau: rất nhiều topic làm tăng chi phí vận hành và có thể phân mảnh quy trình xử lý. DLT theo **nhóm xử lý có người chịu trách nhiệm** thường hữu ích hơn DLT theo toàn bộ tên class Java.

## 11. Cấu hình bằng `RetryTopicConfigurationBuilder`

`@RetryableTopic` phù hợp khi mỗi listener có chính sách tương đối đơn giản. Nếu muốn áp dụng cấu hình theo một tập topics hoặc tạo các policy có lựa chọn khác nhau, Spring Kafka cung cấp `RetryTopicConfiguration` và builder.

Ví dụ Spring Kafka 3.x:

```java
package com.example.kafka;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.retrytopic.RetryTopicConfiguration;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationBuilder;

@Configuration
public class RetryTopicPolicyConfiguration {

    @Bean
    RetryTopicConfiguration paymentRetries(
            KafkaTemplate<String, String> kafkaTemplate) {
        return RetryTopicConfigurationBuilder
            .newInstance()
            .exponentialBackoff(1000, 2, 8000)
            .maxAttempts(4)
            .concurrency(2)
            .includeTopics(List.of("payments.events"))
            .retryOn(RemoteTemporaryException.class)
            .notRetryOn(InvalidOrderException.class)
            .create(kafkaTemplate);
    }
}
```

**Chọn một cơ chế cấu hình cho một listener/topic policy** để tránh không rõ annotation hay bean nào quyết định topology. Trong Spring Kafka, khi có nhiều `RetryTopicConfiguration` áp dụng một topic, không nên giả định chúng tự động được gộp mọi thuộc tính. Hãy xác định một owner của policy và test tên topics/listeners được tạo.

Ở production, nếu topics đã pre-provision và cần custom naming/auto-create, hãy bổ sung các builder methods tương ứng phiên bản hoặc dùng annotation được kiểm soát bằng property. Đừng sao chép mỗi giá trị `attempts` mà bỏ qua số partitions/replicas và quyền Kafka.

### 11.1. Cấu hình global nâng cao

Spring Kafka có hai cách cấu hình infrastructure ở mức rộng:

- Dùng `@EnableKafkaRetryTopic` để import các infrastructure beans và có thể truy cập/customize khi cần.
- Hoặc mở rộng `RetryTopicConfigurationSupport` trong một `@Configuration` để override hooks cấu hình global.

**Không dùng đồng thời hai cách global một cách tùy tiện**, và không tạo nhiều class cùng mở rộng `RetryTopicConfigurationSupport` như thể chúng sẽ tự merge. Với phần lớn ứng dụng, chỉ `@RetryableTopic` là đủ để bootstrap retry topics theo cơ chế mặc định.

Một lý do cần global support là phối hợp **blocking retries ngắn** cho vài exception và non-blocking retries dài cho những exception khác, hoặc customize fatal exceptions và error handlers. Đây là phần có nhiều khác biệt phiên bản, cần đọc đúng tài liệu release đang chạy.

## 12. Retry topics khác nhau cần bao nhiêu concurrency?

Khi cấu hình non-blocking retries, các consumer container cho retry/DLT có thể có concurrency khác listener chính. Từ các phiên bản 3.x, có thể đặt thuộc tính `concurrency` cho retry containers.

Ví dụ:

```java
@RetryableTopic(
    attempts = "4",
    concurrency = "2"
)
@KafkaListener(
    topics = "orders.events",
    concurrency = "6"
)
public void handle(String payload) {
    // ...
}
```

Ý nghĩa: listener chính có nhiều consumer threads hơn, trong khi các retry/DLT consumers dùng concurrency riêng nếu cấu hình được hỗ trợ. Số consumer thực sự có assignment còn phụ thuộc **partitions, group IDs và số instances**.

Không tăng retry concurrency vô hạn: khi downstream đang lỗi, tăng nhiều retry workers có thể làm hệ thống đích tiếp tục quá tải. Hãy đo backlog, tốc độ hồi phục, rate limit và tính idempotent của writer.

### 12.1. Consumer groups của retry topics

Spring Kafka có thể cấu hình nhóm consumer cho các retry topics bằng cách dựa trên group ID của main listener cộng suffix topic. Điều này giúp tránh những rebalance không cần thiết giữa retry và main. Khi triển khai ACL, phải cấp quyền **trên cả các group IDs được sinh ra**, không chỉ `orders-service`.

Một lỗi thường gặp: application kết nối và đọc main topic bình thường, nhưng retry listener không join được group vì principal chưa được cấp quyền cho group tương ứng. Nên kiểm tra log assignment của từng retry/DLT container trong quá trình smoke test.

## 13. Mất ordering: ví dụ lỗi nghiệp vụ

Giả sử partition chứa hai events theo thứ tự:

```text
offset 50: order-123 CREATED
offset 51: order-123 CANCELLED
```

Listener xử lý `CREATED` lỗi 503 và forward sang retry topic. Trong khi đó `CANCELLED` ở main topic có thể được xử lý thành công trước khi `CREATED` được retry.

```text
Main: CREATED (lỗi) -> forward retry
Main: CANCELLED (thành công)
Retry: CREATED (thành công muộn)

Kết quả sai nếu CREATED xử lý muộn ghi đè trạng thái CANCELLED.
```

Các chiến lược phòng ngừa:

- Thiết kế consumer **idempotent và version-aware**: lưu `eventVersion`, chỉ cập nhật nếu version mới hơn.
- Dùng state machine kiểm soát transition, reject một `CREATED` muộn khi trạng thái hiện hành đã `CANCELLED`.
- Với luồng yêu cầu strict per-key ordering, cân nhắc blocking retry hoặc pause partition thay vì chuyển record sang topic khác.
- Với event sourcing, áp dụng sequence number và cơ chế hold/reorder có kiểm soát nếu nghiệp vụ yêu cầu.

Đừng coi Kafka key giống nhau là bảo đảm thứ tự **xuyên qua nhiều topics**. Ordering chỉ có ý nghĩa trong phạm vi partition của từng topic; retry topic là một log khác.

## 14. Publish sang retry/DLT cũng có thể thất bại

Điểm quan trọng trong deployment: **failure path có thể fail tiếp**.

```text
Consumer chính nhận order-123
          |
     xử lý lỗi
          |
     publish sang retry
          |
      +---+---+
      |       |
    thành    lỗi publish
    công      |
      |       +-- ACL denied / broker timeout /
      v           serializer mismatch / invalid partition
   chờ retry
```

Không được tuyên bố “record đã an toàn trong retry topic” chỉ vì handler đã ném exception hoặc log `retry scheduled`. Cần xác nhận nhánh publish thực sự thành công theo framework error-handling và broker ack.

Các failure cases cần kiểm thử:

1. Producer chuyển tiếp không có quyền `WRITE` retry topic.
2. Retry topic bị xóa/chưa provision hoặc partitions không đủ.
3. Serializer của forwarding KafkaTemplate không hỗ trợ payload.
4. Broker tạm unavailable đúng lúc forward.
5. Message lớn hơn `max.message.bytes` hoặc producer request size.
6. Schema registry không truy cập được khi serialize payload.

Trong những tình huống đó, error handler và offset commit behavior cần được kiểm chứng theo version/config. Đừng tự `acknowledge()` một record lỗi trước khi xác nhận nó đã được forward vào Kafka, vì có thể tạo khoảng trống dữ liệu.

### 14.1. Transaction và outbox

Non-blocking retry **không kết hợp với Kafka container transactions**. Nếu handler ghi DB rồi cần publish một event khác, transaction giữa DB và Kafka không tự atomic chỉ nhờ `@RetryableTopic`.

Với side effect quan trọng, cân nhắc:

- Unique business key trong database.
- Transactional outbox để publish event sau khi DB commit.
- Consumer dedup/inbox để xử lý redelivery.
- Đối soát các bản ghi còn pending/retry/DLT theo business key.

Nếu yêu cầu EOS trong Kafka transaction là bắt buộc, phải chọn một retry/error-handling architecture tương thích, không cố ép `@RetryableTopic` lên một transactional batch listener.

## 15. Triển khai có kiểm soát qua nhiều môi trường

Một bảng cấu hình vận hành tối thiểu:

| Thuộc tính | Dev/test | Staging | Production |
| --- | --- | --- | --- |
| Main topic | Có thể auto-create | Provision theo IaC | Provision được duyệt |
| Retry/DLT topics | Auto-create cho test | Pre-provision + ACL | Pre-provision + ACL/retention |
| Replication factor | Theo số brokers test | Theo cluster | Theo SLA/cluster |
| Retry attempts/backoff | Ngắn để test nhanh | Gần production | Theo SLA downstream và retry budget |
| DLT | Queue/test probe | Review thử | Review workflow, alerts, retention |
| Permissions | Test principals | Service principal tương tự prod | Least privilege |
| Monitoring | Log + test assertions | Consumer lag và error alerts | Lag, retry age, DLT size, SLO |
| Idempotency | Test bằng business key | Failure injection | Constraint/outbox/reconciliation |

### 15.1. Rollout khi thay retry attempts hoặc delays

Ví dụ production đang dùng ba retries với topics `-retry-0`, `-retry-1`, `-retry-2`; bản deploy mới dùng một retry topic chung hoặc suffix theo delay.

Nếu chỉ deploy code mới và xóa listeners cũ:

```text
Retry topic cũ còn 50.000 records
              |
              v
Deploy version mới không còn listener cho topic cũ
              |
              v
Backlog bị bỏ quên, dù main consumer vẫn chạy
```

Quy trình thay đổi an toàn:

1. Inventory chính xác topic graph và lag hiện tại.
2. Provision topic mới cùng partitions/retention/ACL.
3. Xác định kế hoạch **drain hoặc migration** cho backlog retry cũ.
4. Deploy tương thích hoặc giữ consumer cho topic cũ đến khi không còn pending records.
5. Kiểm tra DLT handler, serializer, offset group và key idempotency giữa hai version.
6. Theo dõi lag, age và số records xử lý thành công; chỉ xóa topics cũ sau khi xác nhận không còn dữ liệu cần thiết.

Đừng thay nhiều yếu tố (attempts, naming, serializer, groupId) cùng lúc nếu không có kế hoạch chuyển tiếp, bởi rất khó truy tìm mất message giữa các version.

### 15.2. Không tạo topic với cùng suffix cho nhiều listeners bất kể group

Nếu hai `@KafkaListener` độc lập cùng nghe một main topic nhưng có retry policy khác nhau, chúng cần **retry/DLT topic naming được cô lập**. Nếu cùng dùng mặc định không kiểm soát, cấu hình của một listener có thể áp dụng ngoài ý muốn cho listener khác hoặc tạo các consumer khó phân biệt.

Spring Kafka có hỗ trợ nhiều listener trên cùng topic từ các phiên bản 3.x, nhưng cần thiết kế suffix/topic naming và configuration owner rõ ràng. Hãy đưa listener ID/purpose vào suffix khi cần, ví dụ `-billing-retry` và `-reporting-retry`, với DLT riêng nếu policy xử lý lỗi khác nhau.

## 16. Tích hợp kiểm thử retry topic bằng `@EmbeddedKafka`

Một integration test nên chứng minh:

1. Lần đầu listener thất bại với exception retryable.
2. Record được chuyển sang retry topic và xử lý lại.
3. Thành công sau một số lần thì **không vào DLT**.
4. Nếu luôn lỗi, message tới DLT sau khi hết attempts.
5. Nếu lỗi non-retryable, message vào DLT theo policy mà **không đi hết các retry topics**.
6. Khi KafkaTemplate không gửi được retry, test phát hiện lỗi thay vì báo thành công giả.

Ví dụ sau là một **fixture Spring Boot 3.x/Spring Kafka 3.x** có thể dùng làm nền cho integration test, tập trung vào record listener và DLT. Để bài test chạy ổn định, cần isolation topic/group giữa test cases và chờ producer ack.

### 16.1. Test listener có failure injection

```java
package com.example.kafka;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.kafka.annotation.DltHandler;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;

public class RetryProbeListener {

    final AtomicInteger deliveryCount = new AtomicInteger();
    final BlockingQueue<String> successes = new LinkedBlockingQueue<>();
    final BlockingQueue<String> deadLetters = new LinkedBlockingQueue<>();

    @RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 250),
        autoCreateTopics = "true",
        numPartitions = "1",
        replicationFactor = "1"
    )
    @KafkaListener(
        id = "retryProbeListener",
        topics = "payments.retry.test",
        groupId = "payments-retry-test-group"
    )
    public void handle(String payload) {
        int attempt = deliveryCount.incrementAndGet();

        if (payload.equals("always-fail")) {
            throw new RemoteTemporaryException(
                "Injected failure", null);
        }
        if (payload.equals("fail-once") && attempt == 1) {
            throw new RemoteTemporaryException(
                "Injected transient failure", null);
        }
        successes.add(payload);
    }

    @DltHandler
    public void onDlt(String payload) {
        deadLetters.add(payload);
    }
}
```

Đây là fixture dành cho **hai kịch bản chạy tách biệt**: “fail once” và “always fail”. `AtomicInteger` đếm **tổng mọi callback**, vì vậy nếu dùng một listener bean cho nhiều test messages đồng thời, con số attempts sẽ bị lẫn. Trong suite thật, nên dùng map keyed theo message ID hoặc chạy từng scenario trên topic/group/context riêng, reset state có kiểm soát.

### 16.2. Test nhận message tại DLT

```java
@SpringBootTest(
    classes = RetryTopicIntegrationTest.TestApplication.class,
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
    topics = "payments.retry.test",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class RetryTopicIntegrationTest {

    @Autowired KafkaTemplate<String, String> template;
    @Autowired RetryProbeListener listener;
    @Autowired KafkaListenerEndpointRegistry registry;

    @Test
    void sendsToDltAfterRetriesAreExhausted() throws Exception {
        MessageListenerContainer container =
            registry.getListenerContainer("retryProbeListener");
        assertThat(container).isNotNull();

        ContainerTestUtils.waitForAssignment(container, 1);
        template.send("payments.retry.test", "always-fail")
            .get(10, TimeUnit.SECONDS);

        assertThat(listener.deadLetters.poll(15, TimeUnit.SECONDS))
            .isEqualTo("always-fail");
        assertThat(listener.successes).isEmpty();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableKafka
    static class TestApplication {
        @Bean
        RetryProbeListener retryProbeListener() {
            return new RetryProbeListener();
        }
    }
}
```

Các imports thường dùng: JUnit Jupiter `@Test`, Spring Boot Test `@SpringBootTest`, `@SpringBootConfiguration`, `@EnableAutoConfiguration`, Spring Kafka `@EmbeddedKafka`, `KafkaTemplate`, `KafkaListenerEndpointRegistry`, `MessageListenerContainer`, `ContainerTestUtils`; Java `TimeUnit`; AssertJ `assertThat`. Đây là ví dụ **test class được rút gọn phần imports** để tập trung vào luồng.

`@EmbeddedKafka` chỉ tạo main topic trong annotation. Với `autoCreateTopics="true"`, retry/DLT infrastructure cần Kafka admin và quyền tạo topic trên embedded broker; Spring Kafka sẽ cấu hình chúng theo policy đã khai báo. Không đưa cấu hình test `replicationFactor="1"` sang cluster production nhiều broker nếu SLA yêu cầu replication cao.

Trong suite thật nên dùng `@DirtiesContext`, group/topic cách ly giữa các test và một cách xác định message ID chính xác. Nếu tất cả test gửi tới cùng listener với shared `deliveryCount`, thứ tự test có thể làm assertions về attempts sai dù retry framework hoạt động đúng.

### 16.3. Test transient failure rồi thành công

Kịch bản bổ sung dùng **một instance/probe mới**:

```java
template.send("payments.retry.test", "fail-once")
    .get(10, TimeUnit.SECONDS);

assertThat(listener.successes.poll(10, TimeUnit.SECONDS))
    .isEqualTo("fail-once");
assertThat(listener.deadLetters).isEmpty();
```

Để xác nhận thực sự có retry, cần assert callback count theo **message ID** hoặc quan sát `KafkaHeaders.RECEIVED_TOPIC` của lần xử lý sau. Không chỉ assert thành công: nếu exception injection không xảy ra, test vẫn có thể pass mà không hề sử dụng retry topic.

### 16.4. Những test triển khai cần có thêm

| Test | Thiết lập | Kết quả kỳ vọng |
| --- | --- | --- |
| Retryable exception | Listener lỗi hai lần, thành công lần ba | Không DLT; business output một lần |
| Non-retryable exception | `InvalidOrderException` | DLT sớm theo classifier |
| Hết attempts | Luôn ném lỗi tạm thời | DLT nhận record và metadata nguồn |
| Producer không có `WRITE` retry | Tắt quyền trong cluster test | Forward báo lỗi, không âm thầm commit như thành công |
| Retry topic thiếu partition | Main có nhiều partitions, retry ít hơn | Phát hiện routing/publish failure |
| Deserialization failure | Value bytes sai format với `ErrorHandlingDeserializer` | DLT forwarding serializer xử lý raw bytes đúng |
| Service restart | Có backlog retry, restart app | Backlog vẫn được xử lý theo Kafka offsets/retention |
| Rebalance | Thêm/bớt consumers khi retry topic có backlog | Không mất record, idempotent khi replay |
| Upgrade retry naming | Backlog ở topics cũ khi rollout | Có kế hoạch drain/migration |
| DLT handler lỗi | Kho quarantine không khả dụng | DLT failure policy đúng, có alert |
| Nhiều message cùng key | Record trước vào retry, record sau xử lý main | Kiểm tra nghiệp vụ chịu được out-of-order |

## 17. Observability: đừng chỉ xem main consumer lag

Một dashboard hữu ích nên trả lời: có bao nhiêu record đã thành công, bao nhiêu đang chờ retry, bao nhiêu ở DLT và **oldest pending record** đã chờ bao lâu?

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Main consumer lag | Tiến độ đọc topic gốc, không bao gồm toàn bộ work đang retry |
| Retry topic lag theo destination | Record còn pending trong các retry stages |
| Retry age/backoff delay | Thời gian từ lần thất bại đầu tới hiện tại |
| Failure count theo exception category | Hệ thống đích đang outage hay dữ liệu sai? |
| DLT arrival rate | Record đã vượt policy retry hoặc non-retryable |
| DLT unreviewed count | Backlog của đội vận hành/xử lý dữ liệu |
| Forward failures | Không gửi được record sang retry/DLT |
| Consumer rebalance rate | Phát hiện group không ổn định |
| Retry recovery rate | Tỷ lệ message lỗi nhưng hồi phục ở attempt sau |
| Duplicate/idempotency conflicts | Redelivery tạo nhiều attempt hoặc input trùng |

Nếu message đang ở retry topic, **main consumer lag có thể bằng 0**. Không nên dùng đó làm tiêu chí “tất cả đơn hàng trong ngày đã xử lý xong”. Báo cáo nghiệp vụ nên đối chiếu input business keys với **success state + pending retry + DLT/quarantine** theo một hợp đồng rõ ràng.

### 17.1. Logging có cấu trúc

Ví dụ:

```text
event=kafka.retry.scheduled
messageId=order-123-v4
originalTopic=orders.events
originalPartition=2
originalOffset=17621
retryTopic=orders.events-retry-1
exceptionCategory=DOWNSTREAM_TIMEOUT
retryAttempt=2
correlationId=order-123-v4
```

Các trường này là gợi ý instrumentation, **không mặc định đều có sẵn qua một annotation**. Spring Kafka chuyển tiếp một số headers phục vụ nguồn gốc, exception và retry metadata; tên header cụ thể cần đọc đúng phiên bản. Không in payload chứa PII, access token, presigned URL hoặc thông tin thanh toán trong log.

Đối với metrics Prometheus/Micrometer, chỉ dùng nhãn cardinality thấp như `topicGroup`, `exceptionCategory`, `result`. Không đưa `orderId`, `messageId` hoặc `originalOffset` của từng message vào metric labels. Những định danh chi tiết thuộc log/audit store có phân quyền.

### 17.2. Cảnh báo và SLO

Có thể đặt cảnh báo cho:

- Retry lag tăng liên tục trong khi downstream đã hồi phục.
- DLT arrival rate tăng đột biến theo reason code.
- Record retry lâu hơn SLA; oldest pending age gần retention.
- Kafka forwarding producer bị `TopicAuthorizationException`/serialization error.
- DLT handler không hoạt động hoặc DLT không có consumer review.
- Một deployment mới ngừng đọc retry topics cũ.

Khi sự cố downstream dài, đôi khi **pause main listener có điều phối** giúp tránh tạo hàng đợi retry tăng không kiểm soát; tuy vậy pause cũng làm main lag tăng. Cần quyết định dựa trên storage/retention/capacity và yêu cầu nhận dữ liệu.

## 18. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không có retry topic | `@RetryableTopic` chưa được bootstrap, policy không match, auto-create tắt | Kiểm tra annotation/config bean, topic provisioning và logs |
| App startup báo topic không tồn tại | `autoCreateTopics=false`, thiếu retry/DLT topics hoặc admin policy | Provision đủ topics trước deploy |
| Retry producer `TopicAuthorizationException` | Thiếu `WRITE` retry/DLT | Cấp ACL hẹp cho forwarding principal |
| Retry consumer không join được | Thiếu group/topic `READ`, sai group ID | Kiểm tra generated groups và ACL |
| `SerializationException` khi forward | KafkaTemplate serializer không hỗ trợ payload/raw bytes | Dùng serializer tương thích, test deserialization path |
| Message từ main vào DLT ngay | Exception không retryable/fatal hoặc timeout | Kiểm tra classifier và cause chain |
| Message retry quá nhiều | `attempts`, blocking+non-blocking combination hoặc policy đang thay đổi | Phân biệt tổng attempts và tầng retry |
| Backoff không đúng từng millisecond | Backlog, poll scheduling, partition paused hoặc clock | Đo mốc thực tế, không kỳ vọng timer tuyệt đối |
| Main đã hết lag nhưng nghiệp vụ chưa xong | Record đang retry/DLT | Theo dõi toàn bộ topology và business state |
| Retry topic có backlog không giảm sau deploy | Topic naming thay đổi, listener cũ không còn | Drain/migrate topics cũ |
| DLT có record nhưng không ai xử lý | DLT handler chưa start hoặc thiếu workflow | Tạo owner, alert, review/reprocess |
| Dữ liệu ghi trùng sau retry | DB/API side effect xảy ra trước offset commit | Idempotency key, unique constraint, outbox |
| Message sai thứ tự | Non-blocking retry chuyển record sang topic khác | Thiết kế version-aware hoặc chọn cơ chế khác |
| `@RetryableTopic` dùng với batch listener | Cơ chế không hỗ trợ batch listeners | Chuyển sang record listener hoặc đổi error handling |
| Non-blocking retry với transactional container | Cấu hình không tương thích | Chọn kiến trúc retry phù hợp transaction |
| Topics có ít partitions hơn main | Forward giữ partition ngoài phạm vi topic đích | Đồng bộ topology partitions hoặc custom routing rõ ràng |
| Nhiều listeners cùng main topic bị dùng chung retry naming | Cấu hình chồng lấp policy/topics | Cô lập suffix và xác định owner |

### 18.1. Không nên xử lý bằng cách retry mọi exception

Một cấu hình như:

```java
@RetryableTopic(attempts = "100")
```

không tự tăng độ tin cậy. Nếu payload sai schema không bao giờ được sửa, 100 attempts chỉ tạo thêm tải, tăng số topics hoặc lag và trì hoãn review. Với 503/timeout thực sự tạm thời, rất nhiều attempts vẫn phải nằm trong retry budget, retention, rate limit và SLA.

Một cấu hình tốt có **phân loại lỗi, giới hạn thử, điểm kết thúc và người chịu trách nhiệm với DLT**.

## 19. Quy trình deployment an toàn

Một rollout retry topic nên thực hiện theo thứ tự:

1. **Chốt hợp đồng nghiệp vụ:** message key/idempotency, event version, ordering requirement và policy lỗi.
2. **Chốt phiên bản Spring Kafka:** xác định API, naming, topic reuse mặc định, limitation với batch listener/transactions.
3. **Chọn retry budget:** attempts, backoff, timeout và DLT behavior theo downstream SLA.
4. **Lập sơ đồ topic graph:** tên main, các retries, DLT, partitions/replicas và consumer groups.
5. **Provision hạ tầng:** topics, ACL/IAM, serializer/schema registry, retention, quotas, monitoring.
6. **Triển khai listeners:** cấu hình `@RetryableTopic` hoặc builder, DLT handler và idempotent business service.
7. **Chạy smoke tests có failure injection:** lỗi tạm thời rồi hồi phục, lỗi không retryable, hết attempts và lỗi forward.
8. **Kiểm tra backlog và rollback plan:** khi thay naming, giữ đường đọc topics cũ hoặc drain có kiểm soát.
9. **Quan sát sau deploy:** retry lag, DLT arrivals, downstream load, duplicate conflicts và age của work chưa xử lý.
10. **Diễn tập reprocess:** đưa một DLT record đã được duyệt trở lại luồng xử lý mà không ghi trùng side effect.

Không nên rollback code bằng cách xóa toàn bộ retry/DLT topics: chúng có thể đang chứa message chưa được xử lý. Việc dọn topic phải là một thao tác quản trị dữ liệu với quy trình đối soát riêng.

## 20. Mẫu cấu hình theo môi trường

Một cách quản lý tham số retry trong `application.yml`:

```yaml
app:
  kafka:
    retry:
      attempts: ${KAFKA_RETRY_ATTEMPTS:4}
      initial-delay-ms: ${KAFKA_RETRY_INITIAL_DELAY_MS:2000}
      max-delay-ms: ${KAFKA_RETRY_MAX_DELAY_MS:8000}
      auto-create-topics: ${KAFKA_RETRY_AUTO_CREATE_TOPICS:false}
```

Sử dụng các thuộc tính trong annotation:

```java
@RetryableTopic(
    attempts = "${app.kafka.retry.attempts}",
    backoff = @Backoff(
        delayExpression = "${app.kafka.retry.initial-delay-ms}",
        multiplier = 2.0,
        maxDelayExpression = "${app.kafka.retry.max-delay-ms}"
    ),
    autoCreateTopics = "${app.kafka.retry.auto-create-topics}"
)
@KafkaListener(topics = "orders.events")
public void consume(String orderId) {
    // ...
}
```

Ví dụ `@Backoff.delayExpression`/`maxDelayExpression` là thuộc tính annotation của Spring Retry; việc resolve placeholder cần được kiểm tra với phiên bản đang chạy. Nếu cấu hình deployment dùng cùng `attempts` nhưng backoff/delay khác, tên topics có thể thay đổi nếu naming strategy dùng suffix theo delay. **Không dùng external properties mà quên cập nhật topology IaC**.

Trong production, chỉ cho phép đổi retry budget qua một quy trình review và rollout có kiểm soát. Không nên để một biến môi trường thay đổi số retry topics nhưng team Kafka platform không biết.

## 21. Checklist trước khi go-live

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Listener có phải record listener không? | Không dùng non-blocking retry cho batch listener |
| Container có dùng Kafka transactions không? | Không kết hợp cấu hình không được hỗ trợ |
| Có mất ordering nếu message đi retry không? | Nghiệp vụ chấp nhận hoặc có bảo vệ version/state |
| `attempts` có bao gồm lần đầu không? | Policy tính rõ số attempts và số retry stages |
| Backoff/timeout phù hợp SLA không? | Có retry budget, giới hạn và đo lường |
| Exception được phân loại chưa? | Retryable, non-retryable và fatal cases có tests |
| Retry/DLT topics có đúng tên/version không? | Topic graph được chốt và provision đủ |
| Partitions/replicas có đáp ứng cluster không? | Không thiếu destination partition và đúng SLA |
| Retention có đủ cho outage/backlog không? | Có headroom cho downtime và review |
| Principal có đủ quyền trên cả retry/DLT không? | Smoke test bằng identity production-like |
| KafkaTemplate forward serialize đúng không? | Kiểm tra payload thường và raw bytes khi cần |
| DLT có owner và workflow không? | Alert, review, reprocess và retention rõ ràng |
| Business handler có idempotent không? | Replay/retry không tạo side effect trùng |
| Có biết message đang pending ở đâu không? | Dashboard main + retries + DLT |
| Có migration plan khi đổi naming không? | Không bỏ quên retry backlog của version trước |
| Đã test lỗi forward và broker failure chưa? | Không thừa nhận success khi message chưa được lưu bền vững |

## Kết luận

**Cấu hình retry topic** trong Spring Kafka là một quyết định về **topology, độ trễ và trách nhiệm vận hành**, không chỉ là việc thêm `@RetryableTopic`. Non-blocking retry giúp consumer chính tránh bị giữ lâu bởi một message lỗi, nhưng đổi lại **mất ordering xuyên topics**, tạo thêm topics/consumer groups và cần kiểm soát việc forwarding.

Một triển khai đáng tin cậy phải bảo đảm: **topic và ACL được provision đúng, backoff có giới hạn, exception được phân loại, DLT có người xử lý, message không bị bỏ quên qua deployment và side effect là idempotent**. Cuối cùng, hãy kiểm chứng bằng integration test có lỗi thật — bao gồm lần retry thành công, lần hết attempts và lần publish retry/DLT thất bại — rồi giám sát cả main topic, retry topics lẫn DLT trong production.

## Tài liệu tham khảo

- [Spring Kafka Reference — Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html): tổng quan, giới hạn với batch listeners và container transactions.
- [Spring Kafka Reference — How the Pattern Works](https://docs.spring.io/spring-kafka/reference/retrytopic/how-the-pattern-works.html): forward, timestamp/backoff, retry partitions và DLT.
- [Spring Kafka Reference — Configuration](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-config.html): `@RetryableTopic`, `RetryTopicConfigurationBuilder` và cấu hình toàn cục.
- [Spring Kafka Reference — Features](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html): backoff, classifier, timeout và exception routing.
- [Spring Kafka Reference — Topic Naming](https://docs.spring.io/spring-kafka/reference/retrytopic/topic-naming.html): suffixes, topic reuse và khác biệt phiên bản.
- [Spring Kafka Reference — DLT Strategies](https://docs.spring.io/spring-kafka/reference/retrytopic/dlt-strategies.html): DLT handler, failure strategy và auto-start.
- [Spring Kafka Reference — Combining Blocking and Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic/retry-topic-combine-blocking.html): phối hợp hai loại retry.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka`, `ContainerTestUtils` và integration tests.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): topics, partitions, retention, ACL, consumer groups và delivery semantics.
