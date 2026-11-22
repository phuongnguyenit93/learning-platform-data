# Canary consumer instance trong Spring Kafka: triển khai từng bước và kiểm soát rủi ro

## 1. Bài toán và mục tiêu

Một service Spring Kafka đang chạy ổn định với ba replica, cùng tiêu thụ topic `orders.events`. Nhóm phát triển vừa sửa logic xử lý đơn hàng và muốn đưa phiên bản mới lên production, nhưng chưa muốn thay thế toàn bộ consumer đang hoạt động. Giải pháp thường được nhắc đến là triển khai **canary consumer instance**: chỉ cho một số ít instance chạy phiên bản mới, quan sát hành vi thực tế rồi mới mở rộng.

Với HTTP service, canary thường điều hướng một tỷ lệ request qua ingress hoặc service mesh. **Kafka consumer không hoạt động giống HTTP load balancing.** Trong cùng một consumer group, Kafka phân chia **partition ownership**, không định tuyến “1% message” theo tỷ lệ canary do chúng ta chỉ định. Thêm một consumer mới vào group có thể kích hoạt rebalance và chuyển quyền đọc một hoặc nhiều partition từ bản ổn định sang bản canary.

Đây là điểm xuất phát quan trọng của bài học **“Canary consumer instance”**, thuộc nhóm **Deployment và cấu hình** của module **Spring Kafka Reliability Operations**.

Sau bài học, bạn sẽ biết cách:

1. Phân biệt canary **cùng group xử lý thật** với canary **shadow group độc lập**.
2. Chọn phương án tùy mức độ an toàn của nghiệp vụ, tác động phụ và yêu cầu quan sát.
3. Thiết lập Spring Kafka consumer cùng group ID, điều chỉnh concurrency và nhận diện revision.
4. Triển khai một stable Deployment và một canary Deployment trong Kubernetes.
5. Quan sát partition assignment, consumer lag, retry, DLT, lỗi nghiệp vụ và độ trễ trước khi mở rộng.
6. Áp dụng idempotency, quy tắc version và ranh giới offset commit để tránh kết quả sai khi rebalance.
7. Thiết kế điều kiện tăng tỷ lệ triển khai, rollback, xử lý crash và kiểm thử thực tế.
8. Giải thích vì sao một canary không nhận partition **không phải** bằng chứng phiên bản mới an toàn.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka và Kubernetes. Các API, cách phân công partition và hành vi consumer group cụ thể cần được xác minh với phiên bản Kafka client, broker và group protocol đang sử dụng.

## 2. Canary ở consumer khác canary ở HTTP

Canary deployment nghĩa là triển khai một phiên bản mới cho **phạm vi tác động có kiểm soát**, thu thập tín hiệu chất lượng rồi quyết định tăng phạm vi hay rollback.

Với HTTP:

```text
                  HTTP ingress
                      |
                 routing 95/5
                 /          \
           stable 95%     canary 5%
```

Với Kafka consumer dùng chung group:

```text
Topic orders.events
  partitions: P0 P1 P2 P3 P4 P5
                  |
                  v
       Group: orders-processors
                  |
         Kafka group coordinator
             /             \
        Stable pods      Canary pod
          v1               v2
       P0 P1 P2 P3       P4 P5
```

Sơ đồ chỉ là một ví dụ assignment. **Không có bảo đảm Kafka sẽ giao chính xác P4–P5 cho canary hoặc chia theo số message.** Partition assignment còn phụ thuộc số member, subscription, assignor và trạng thái group.

Các hệ quả:

- Một canary có thể nhận 0 partition nếu số consumer lớn hơn số partition.
- Một canary có thể nhận một partition rất “nóng” chứa phần lớn event của hệ thống.
- Cùng một partition chỉ được một consumer trong group ổn định sở hữu; stable và canary không cùng xử lý mỗi record.
- Khi canary gia nhập hoặc rời group, có thể xảy ra rebalance, pause ngắn và redelivery quanh offset commit.
- Khi canary xử lý thật, bug của nó có thể ảnh hưởng trực tiếp dữ liệu production.

**Canary cùng group không phải cơ chế chia chính xác 1%, 5% hoặc 10% event.** Nếu sản phẩm cần phần trăm routing chặt chẽ theo business key, phải thiết kế cơ chế routing/topic/partition hoặc nguồn sự kiện riêng và chứng minh tính đúng đắn, chứ không dựa vào số replica.

## 3. Hai mô hình canary cần phân biệt

### 3.1. Canary cùng consumer group: xử lý production thật

Stable và canary cùng `group.id=orders-processors`:

```text
               Topic orders.events
                       |
              Consumer group G
                /           \
           Stable v1       Canary v2
           xử lý thật      xử lý thật
                \           /
                  Business DB
```

Canary nhận một phần partition và **chịu trách nhiệm xử lý thật** các record của chúng.

Ưu điểm:

- Kiểm tra được luồng xử lý, offset commit, retry và hệ thống đích thực tế.
- Dùng gần đúng tải production, không tiêu thụ lại toàn bộ topic.
- Rollout sang stable/new revision có thể tiến hành từng bước bằng thay đổi replica.

Rủi ro:

- Mã canary lỗi có thể ghi sai dữ liệu hoặc đẩy record vào DLT.
- Không điều khiển chính xác tỷ lệ message.
- Rebalance có thể gây tăng lag hoặc redelivery.
- Nếu canary không được gán partition, test không có giá trị đại diện.
- Dữ liệu canary nhận được có thể không đại diện cho toàn bộ event types/key distribution.

### 3.2. Shadow canary: consumer group riêng, không gây side effect

Canary đăng ký **group ID khác**, ví dụ `orders-processors-shadow-v2`:

```text
                  Topic orders.events
                    /           \
                   v             v
        Group orders-processors  Group orders-shadow-v2
            Stable v1               Canary v2
          xử lý thật           kiểm tra/đo đạc
               |                    |
           Business DB         Không ghi DB thật,
                               không phát event thật
```

Cả hai group độc lập có thể đọc toàn bộ các partition của cùng topic. Shadow canary chạy parser, validation hoặc xử lý thử trên dữ liệu có kiểm soát nhưng **không tác động lên hệ thống production**.

Ưu điểm:

- An toàn hơn khi thay đổi logic có nguy cơ ghi sai dữ liệu.
- Có thể quan sát nhiều loại message mà không tranh quyền với stable group.
- Không làm offset của stable group thay đổi.
- Có thể so sánh kết quả bằng một kho kết quả test tách biệt.

Giới hạn:

- Tăng số request/fetch và CPU tiêu thụ từ broker.
- Nếu shadow đọc từ đầu, có thể phát sinh khối lượng rất lớn.
- Không tự chứng minh được side effect production của phiên bản mới.
- Code phải thực sự ngăn **mọi** tác động phụ: ghi DB, gọi HTTP, gửi email, publish Kafka, tạo DLT production...
- Offset của shadow group tách biệt, không dùng để xác định progress của stable group.

### Ma trận chọn mô hình

| Yêu cầu | Cùng group xử lý thật | Shadow group độc lập |
| --- | --- | --- |
| Kiểm thử đường commit offset production | Phù hợp | Không đại diện hoàn toàn |
| Đảm bảo không ghi dữ liệu nghiệp vụ | Không, trừ khi có lớp bảo vệ riêng | Phù hợp nếu code thật sự read-only |
| Không làm stable group rebalance | Không | Có thể tránh thay đổi membership của stable group |
| Xử lý toàn bộ loại message để kiểm tra | Không bảo đảm | Có thể theo dõi toàn bộ topic trong phạm vi offset đã chọn |
| Chi phí đọc từ Kafka | Ít tăng do chia partition | Thêm một consumer group đọc độc lập |
| Đo performance writer production | Có | Không, nếu side effect bị vô hiệu hóa |
| Blast radius khi parser/validator lỗi | Có thể ảnh hưởng partition mà canary sở hữu | Thường cô lập ở shadow group |
| Rollout từng bước đến phiên bản mới | Trực tiếp hơn | Nên dùng shadow trước, rồi chuyển sang cùng group |

**Hướng tiếp cận an toàn thường là:** shadow để xác minh parsing/validation và compatibility; sau đó triển khai một canary cùng group để kiểm tra end-to-end với idempotency, guardrail và cơ chế rollback sẵn sàng. Không phải hệ thống nào cũng cần cả hai giai đoạn.

## 4. Canary cùng group không đồng nghĩa “một replica = một phần trăm cố định”

Giả sử topic có 12 partition, stable có 3 consumer thread, canary có 1 consumer thread:

```text
Total consumers in group = 4
Total topic partitions   = 12
Average                 = 3 partitions/member
```

Nếu partition có khối lượng tương đương và assignor phân phối gần đều, canary có thể nhận khoảng 25% số partition. Nhưng điều đó không đồng nghĩa 25% **message**, **CPU**, **doanh thu**, hay **rủi ro nghiệp vụ**.

Ví dụ tải lệch:

| Partition | Message/giây |
| --- | ---: |
| P0 | 50 |
| P1 | 60 |
| P2 | 40 |
| P3 | 1.500 |
| P4 | 50 |
| P5 | 70 |

Nếu canary nhận P3, nó có thể xử lý phần lớn traffic dù chỉ sở hữu một partition. Vì vậy hãy quan sát **message rate và business key distribution theo partition**, thay vì chỉ đếm số partition.

Trong một số nhóm có nhiều consumer hơn partition, canary có thể được assign 0 partition. Khi đó `pod Ready` và `Kafka listener running` vẫn chưa chứng minh logic mới đã xử lý một record nào.

### Nếu cần tỷ lệ rollout chính xác?

Cân nhắc các thiết kế riêng, ví dụ:

- Định tuyến một tập business key đã xác định sang topic thử nghiệm bằng producer/router được kiểm soát.
- Tạo nguồn sự kiện copy cho canary và tách hoàn toàn side effect.
- Phân vùng dữ liệu/tác vụ theo tenant hoặc key range được chỉ định trước.

Mỗi lựa chọn thay đổi kiến trúc và có thể ảnh hưởng ordering, idempotency hoặc event distribution. Không nên gán thủ công một partition cho canary trong khi cùng group vẫn subscribe topic đó mà chưa thiết kế quyền sở hữu, vì explicit assignment và group subscription là hai cơ chế phân phối khác nhau.

## 5. Điều kiện tiên quyết trước khi triển khai

Trước khi đưa consumer revision mới vào production, cần xác định:

1. **Topic và schema:** version mới đọc được event đang tồn tại và event do producer hiện tại phát ra.
2. **Business effect:** writer có idempotency key và quy tắc version để tránh tác động trùng/kết quả quay ngược.
3. **Offset strategy:** dùng auto-commit, container ack mode, manual ack hay Kafka transaction? Ranh giới commit nào được bảo vệ?
4. **Error recovery:** retry policy, backoff, DLT, quyết định record nào có thể bị bỏ qua.
5. **Group protocol:** assignor, cooperative/eager rebalance, static membership và compatibility với stable version.
6. **Observability:** dashboard/alert có phân biệt stable và canary bằng label release/pod.
7. **Rollback:** image cũ có thể chạy lại; biết cách dừng canary và chuyển partition về stable.
8. **Security:** canary có quyền Kafka/DB cần thiết nhưng không được cấp quyền thừa.
9. **Capacity:** broker, DB, connection pool và consumer threads còn đủ headroom để xử lý rebalance.
10. **Bằng chứng triển khai:** biết canary đang sở hữu partition nào và đã xử lý bao nhiêu event có kết quả.

Nên đặt mục tiêu đo được trước khi bắt đầu. Ví dụ “canary xử lý tối thiểu 10.000 event duy nhất đại diện cho các loại sự kiện mục tiêu, không làm tăng error rate/lag vượt ngưỡng, không ghi trùng dữ liệu và không tạo DLT bất thường”. Các con số là **ngưỡng minh họa**, không phải tiêu chuẩn chung.

## 6. Cấu hình cơ sở cho một Spring Kafka consumer

Giả sử ứng dụng đọc event order từ topic `orders.events`. Các cấu hình cần thiết trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${APP_KAFKA_GROUP_ID:orders-processors}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 200
    listener:
      ack-mode: record
      concurrency: 1

app:
  kafka:
    orders:
      topic: ${APP_KAFKA_TOPIC:orders.events}
  release:
    track: ${APP_RELEASE_TRACK:stable}
    version: ${APP_RELEASE_VERSION:unknown}
```

Giải thích:

- `group-id`: quy định hai instance có cùng group hay tách thành shadow.
- `enable-auto-commit=false`: để Spring Kafka listener container điều phối offset theo ack mode.
- `ack-mode: record`: commit tiến độ theo vòng đời xử lý từng record của container; khi dùng handler đồng bộ và trả về thành công, container có cơ sở ghi nhận record đã xử lý.
- `concurrency: 1`: mỗi application instance có một consumer thread trong ví dụ; tăng concurrency tạo thêm member và có thể làm phân phối partition thay đổi.
- `max-poll-records`: ảnh hưởng số record mỗi lần poll và thời gian xử lý; không định nghĩa tỷ lệ traffic của canary.
- `auto-offset-reset: earliest`: chỉ có ý nghĩa khi group/partition chưa có committed offset hợp lệ; không bắt stable group đang chạy quay về đầu topic.
- `track`/`version`: metadata release dùng cho log, trace và dashboard, không phải thuộc tính Kafka group mặc định.

Trong production, cần cấu hình SSL/SASL, secret, topic authorization, retry và error handler theo hạ tầng. Không lưu mật khẩu Kafka trong YAML commit vào git.

**Lưu ý về shadow group:** group mới với `earliest` có thể tiêu thụ toàn bộ dữ liệu còn trong retention, tạo khối lượng lớn ngoài dự kiến. Nếu chỉ muốn quan sát dữ liệu mới, dùng `latest` trước khi group có offset và khởi động consumer trước khi phát corpus kiểm thử; đồng thời hiểu rằng những event trước lúc assignment có thể không được đọc.

## 7. Listener xử lý thật với @KafkaListener

Một consumer dùng chung group có thể triển khai:

```java
package com.example.orders.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventConsumer.class);

    private final ObjectMapper mapper;
    private final OrderEventService service;
    private final String releaseTrack;
    private final String releaseVersion;

    public OrderEventConsumer(
            ObjectMapper mapper,
            OrderEventService service,
            @Value("${app.release.track}") String releaseTrack,
            @Value("${app.release.version}") String releaseVersion) {

        this.mapper = mapper;
        this.service = service;
        this.releaseTrack = releaseTrack;
        this.releaseVersion = releaseVersion;
    }

    @KafkaListener(
        id = "orders-processor",
        topics = "${app.kafka.orders.topic}",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    public void onMessage(ConsumerRecord<String, String> record)
            throws Exception {

        OrderEvent event =
            mapper.readValue(record.value(), OrderEvent.class);

        service.apply(event);

        log.info(
            "event=order.consumed releaseTrack={} version={} " +
            "partition={} offset={} eventId={}",
            releaseTrack,
            releaseVersion,
            record.partition(),
            record.offset(),
            event.eventId()
        );
    }
}
```

Event model minh họa:

```java
package com.example.orders.kafka;

public record OrderEvent(
    String eventId,
    String orderId,
    long version,
    String status
) {}
```

Những điểm cần hiểu:

- Các replica stable và canary có thể dùng **cùng code listener và cùng group ID** nhưng chạy image version khác nhau.
- `id="orders-processor"` là ID container ở cấp application instance, không yêu cầu mỗi pod có ID KafkaListener khác nhau. Mỗi pod có runtime JVM/context riêng.
- Release metadata được đưa vào log để tách hoạt động canary khỏi stable.
- Handler không bắt exception rồi âm thầm trả về thành công. Nếu xử lý thất bại, cần để error handler của container có cơ hội áp dụng retry/recovery policy.
- Ghi log một dòng cho mỗi event ở mức `INFO` chỉ có tính minh họa; ở tải lớn nên chuyển sang metric/tổng hợp hoặc sampling để tránh tăng CPU/I/O.
- Không log toàn bộ payload, token, thông tin nhạy cảm hoặc dữ liệu cá nhân.

### Dùng chung group có nghĩa dùng chung offset

Stable và canary có cùng `group.id` thì cùng chia sẻ committed offsets của group theo từng topic-partition. Khi một partition chuyển từ stable sang canary, canary tiếp tục từ offset đã commit của group chứ không tự động đọc lại từ đầu theo `auto-offset-reset`.

Ngược lại, nếu canary chuyển sang group shadow khác, group đó có committed offsets riêng. **Không chuyển group ID của consumer production chỉ vì muốn rollback hay tránh lỗi**, bởi điều đó thay đổi cả mô hình phân phối công việc và vị trí đọc.

## 8. Idempotent business handler để giới hạn tác động của canary

Khi rebalance, crash hoặc offset commit thất bại, Kafka có thể giao lại một record đã được business service xử lý. Với at-least-once processing, canary phải an toàn với redelivery.

Ví dụ PostgreSQL có hai bảng:

```sql
CREATE TABLE processed_order_event (
    consumer_projection VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_projection, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(120) PRIMARY KEY,
    last_version BIGINT NOT NULL,
    current_status VARCHAR(40) NOT NULL
);
```

Service:

```java
package com.example.orders.kafka;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventService {

    private final JdbcTemplate jdbc;

    public OrderEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {

        int inserted = jdbc.update(
            """
            INSERT INTO processed_order_event (
                consumer_projection, event_id
            ) VALUES ('orders-main', ?)
            ON CONFLICT (consumer_projection, event_id)
            DO NOTHING
            """,
            event.eventId()
        );

        if (inserted == 0) {
            // Event đã được ghi nhận trước đây.
            return;
        }

        jdbc.update(
            """
            INSERT INTO order_projection (
                order_id, last_version, current_status
            ) VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                last_version = EXCLUDED.last_version,
                current_status = EXCLUDED.current_status
            WHERE order_projection.last_version
                < EXCLUDED.last_version
            """,
            event.orderId(),
            event.version(),
            event.status()
        );
    }
}
```

Ví dụ này giả định `JdbcTemplate` sử dụng datasource được quản lý bởi transaction manager ứng dụng. Marker và projection thay đổi trong **cùng transaction database**. Khi process crash trước commit, cả hai có thể rollback; khi record được giao lại sau database commit nhưng trước Kafka offset commit, marker giúp bỏ qua tác động lặp.

`last_version` bổ sung điều kiện không cho event version cũ ghi đè dữ liệu mới. Nó không bảo đảm mọi yêu cầu nghiệp vụ về xử lý các phiên bản thiếu hoặc thứ tự bắt buộc: nếu business cần xử lý tuần tự mọi event, phải có thêm quy tắc phát hiện gap và recovery.

**Quan trọng:** Database transaction và Kafka offset commit không mặc định nằm trong cùng một distributed transaction. Vì vậy vẫn có cửa sổ redelivery; thiết kế idempotent mới bảo vệ kết quả cuối. Kafka transaction có thể hỗ trợ exactly-once trong phạm vi xử lý Kafka-to-Kafka phù hợp, nhưng không tự làm API hoặc database ngoài Kafka trở thành exactly-once.

## 9. Rebalance xảy ra khi canary gia nhập group

Khi canary cùng group khởi động:

```text
Stable A, B, C đang đọc partitions
                 |
            Canary D join
                 |
                 v
       Group membership thay đổi
                 |
                 v
       Partition assignment cập nhật
                 |
            +----+----+
            |         |
          Stable     Canary
       tiếp tục đọc  nhận partition
```

Tùy giao thức và assignor, Kafka có thể sử dụng eager hoặc cooperative rebalance. Với cooperative assignment, không nhất thiết tất cả partition đều bị revoke; chỉ những partition cần chuyển mới có thể thay owner.

Điều cần vận hành:

- Theo dõi partition nào bị revoke và assign cho canary.
- Đặt timeout/handler duration sao cho consumer vẫn poll đúng yêu cầu.
- Không chặn rebalance callback bằng lời gọi mạng dài hoặc lock không có timeout.
- Kiểm tra record xử lý xong trước/sau revoke theo ack/transaction policy.
- Theo dõi duplicate business effect, retry và committed offsets.

### Cấu hình assignor (khi phù hợp)

Trong môi trường sử dụng consumer group protocol/assignment phù hợp với client, có thể cấu hình `CooperativeStickyAssignor`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Không thay assignor chỉ trên canary rồi giả định cả group sẽ tự sử dụng cùng chiến lược. Các member phải có cấu hình tương thích; khi chuyển từ eager sang cooperative có thể cần phương án nâng cấp theo từng giai đoạn, tùy phiên bản client và protocol.

Trong các phiên bản Kafka sử dụng broker-side assignment của consumer group protocol mới, một số thuộc tính assignment có ý nghĩa khác. Hãy xác minh group protocol hiện hành trước khi đổi cấu hình.

## 10. Cấu hình deployment stable và canary trong Kubernetes

Một cách triển khai cùng group là duy trì Deployment stable và tạo Deployment canary riêng, với số replica, image và nhãn release khác nhau.

Ví dụ stable Deployment rút gọn:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer-stable
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-consumer
      track: stable
  template:
    metadata:
      labels:
        app: order-consumer
        track: stable
    spec:
      containers:
        - name: consumer
          image: registry.example.com/order-consumer:1.8.0
          env:
            - name: SPRING_KAFKA_BOOTSTRAP_SERVERS
              value: "kafka-bootstrap:9092"
            - name: APP_KAFKA_GROUP_ID
              value: "orders-processors"
            - name: APP_RELEASE_TRACK
              value: "stable"
            - name: APP_RELEASE_VERSION
              value: "1.8.0"
          resources:
            requests:
              cpu: "250m"
              memory: "384Mi"
            limits:
              memory: "768Mi"
```

Canary Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer-canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-consumer
      track: canary
  template:
    metadata:
      labels:
        app: order-consumer
        track: canary
    spec:
      containers:
        - name: consumer
          image: registry.example.com/order-consumer:1.9.0
          env:
            - name: SPRING_KAFKA_BOOTSTRAP_SERVERS
              value: "kafka-bootstrap:9092"
            - name: APP_KAFKA_GROUP_ID
              value: "orders-processors"
            - name: APP_RELEASE_TRACK
              value: "canary"
            - name: APP_RELEASE_VERSION
              value: "1.9.0"
          resources:
            requests:
              cpu: "250m"
              memory: "384Mi"
            limits:
              memory: "768Mi"
```

Ví dụ giả định image và Kafka bootstrap service đã tồn tại, đồng thời các credential/TLS được cung cấp bằng secret hoặc cơ chế riêng của cluster. Đây là phần manifest tối thiểu để minh họa topology, **chưa phải manifest production hoàn chỉnh**: cần bổ sung security context, health probes, termination grace period, service account, topology spread và policy phù hợp.

### Những đặc điểm quan trọng

- **Cùng group ID:** stable và canary cạnh tranh sở hữu partition và cùng commit vào một tập group offsets.
- **Khác nhãn track/version:** giúp giám sát, lọc log và lựa chọn pod khi rollback.
- **Không cần Service/Ingress để phân traffic Kafka:** các consumer chủ động kết nối đến broker.
- **Một pod canary không nhất thiết là một consumer member** nếu trong pod cấu hình `concurrency > 1` hoặc có nhiều listener cùng group.
- **replicas: 1** giúp kiểm soát số process canary ban đầu, không đảm bảo một tỷ lệ event cố định.
- Nếu stable có HPA hoặc operator tự mở rộng replica, hãy tính tổng consumer threads trong group và bảo đảm việc quan sát canary còn đủ dữ liệu.

Đối với production, nên pin image bằng digest hoặc quy tắc provenance rõ ràng để rollback dùng đúng artifact đã kiểm chứng.

## 11. Consumer concurrency và sức chứa của topic

Trong Spring Kafka, `ConcurrentKafkaListenerContainerFactory.setConcurrency(n)` hoặc property tương ứng có thể tạo nhiều consumer threads.

Giả sử:

```text
Stable: 3 pods × concurrency 2 = 6 consumers
Canary: 1 pod × concurrency 2 = 2 consumers
Topic:  6 partitions
```

Tổng 8 member cạnh tranh 6 partition. Một số consumer có thể không nhận assignment nào. Việc canary không xử lý dữ liệu có thể đến từ topology này chứ không phải code canary bị hỏng.

Các bước điều tra:

1. Xác nhận group ID của tất cả member.
2. Đếm số partition và số consumer threads thực sự.
3. Đọc assignment thực tế, không chỉ `kubectl get pods`.
4. Đối chiếu số event/giây canary đã xử lý.
5. Nếu cần quan sát vững hơn, dùng topic/partition test đủ lớn hoặc shadow group.

**Không tăng concurrency chỉ để “canary nhận nhiều traffic hơn”** nếu chưa tính rebalance, DB load, ordering và số partition. Kafka phân phối theo partition, không chia nhỏ một partition cho nhiều consumer cùng group.

## 12. Shadow canary: cấu hình group riêng và xử lý read-only

Nếu muốn chạy thử mà không ghi dữ liệu production, dùng một deployment khác với group riêng:

```yaml
env:
  - name: APP_KAFKA_GROUP_ID
    value: "orders-processors-shadow-v2"
  - name: APP_CONSUMER_MODE
    value: "shadow"
  - name: SPRING_KAFKA_CONSUMER_AUTO_OFFSET_RESET
    value: "latest"
  - name: APP_RELEASE_TRACK
    value: "shadow"
  - name: APP_RELEASE_VERSION
    value: "1.9.0"
```

Với group mới, `latest` giúp bắt đầu từ cuối log khi chưa có committed offsets. Nhưng nó **không đảm bảo đọc các event được phát trước khi consumer hoàn tất assignment**. Để test trên một corpus nhất định, hãy chốt thời điểm/corpus hoặc dùng group và offset reset được quản lý riêng.

### Bảo vệ side effect trong code

Một mẫu đơn giản là dùng consumer riêng cho shadow và không inject business writer production:

```java
package com.example.orders.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    name = "app.consumer.mode",
    havingValue = "shadow"
)
public class ShadowOrderConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(ShadowOrderConsumer.class);

    private final ObjectMapper mapper;
    private final ShadowOrderValidator validator;

    public ShadowOrderConsumer(
            ObjectMapper mapper,
            ShadowOrderValidator validator) {
        this.mapper = mapper;
        this.validator = validator;
    }

    @KafkaListener(
        id = "orders-shadow",
        topics = "${app.kafka.orders.topic}",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    public void validate(ConsumerRecord<String, String> record)
            throws Exception {

        OrderEvent event =
            mapper.readValue(record.value(), OrderEvent.class);

        validator.validateWithoutSideEffects(event);

        log.debug(
            "event=orders.shadow.validated partition={} offset={}",
            record.partition(), record.offset()
        );
    }
}
```

Service validator có thể kiểm tra schema, phân loại event, tính toán dự kiến hoặc ghi metric; **không được gọi repository cập nhật dữ liệu thật, gửi event mới hoặc tạo DLT production theo mặc định**.

Nếu ứng dụng có cả `OrderEventConsumer` xử lý thật ở phần trước, hãy đặt điều kiện bổ sung cho listener xử lý thật:

```java
@Component
@ConditionalOnProperty(
    name = "app.consumer.mode",
    havingValue = "active",
    matchIfMissing = true
)
public class OrderEventConsumer {
    // Nội dung listener xử lý thật như phần trước.
}
```

Trong bản cấu hình thực tế, chỉ một trong hai listener được tạo cho mỗi mode, tránh tình huống shadow pod vẫn chạy consumer side-effecting do auto-config khác.

### Không chỉ dùng if để ngăn side effect

Một nhánh:

```java
if (shadowMode) {
    return;
}
businessService.apply(event);
```

có thể dễ bị bỏ sót nếu handler gọi service khác trước khi kiểm tra flag, hoặc nếu có `@RetryableTopic`/DLT publisher phát sinh side effect. Với môi trường nhạy cảm, tốt hơn nên dùng **cấu trúc bean tách biệt**, credentials read-only, database sandbox hoặc quyền Kafka chỉ cho phép READ ở topic nguồn.

Shadow group mới có thể làm tăng tải broker và deserialization CPU; vẫn cần giới hạn throughput và quan sát lag cho group riêng.

## 13. Tình huống tương thích schema/event khi hai phiên bản chạy song song

Khi stable v1 và canary v2 cùng group, producer vẫn phát event theo một schema chung. Hai consumer versions có thể cùng tồn tại vài phút hoặc lâu hơn. Điều này đòi hỏi **khả năng tương thích hai chiều theo hành vi triển khai**, không chỉ code canary đọc được event mới.

Ví dụ:

```json
{
  "eventId": "evt-912",
  "orderId": "ord-42",
  "version": 7,
  "status": "PAID",
  "currency": "VND"
}
```

Nếu v2 yêu cầu trường `currency` nhưng producer hiện tại vẫn có event cũ thiếu trường, canary có thể fail khi nhận partition chứa record cũ. Nếu v2 ghi schema mới vào cùng database, stable v1 có thể đọc không được hoặc ghi đè trường mới.

Trước rollout cần kiểm tra:

- Consumer mới đọc được event hiện hữu trong retention, gồm trường optional/unknown.
- Consumer cũ tiếp tục hoạt động khi producer hoặc consumer mới xuất hiện.
- Database migration tương thích với cả hai phiên bản đang chạy.
- Dữ liệu do v2 ghi không làm v1 xử lý sai khi một partition chuyển owner.
- Event key, partitioning logic, serializer và group/offset policy không thay đổi ngoài dự kiến.

Một canary chỉ đọc vài loại event không thể thay thế test schema compatibility trên toàn bộ event corpus. Nếu thiếu coverage, dùng shadow/replay với dữ liệu được ẩn thông tin nhạy cảm hoặc fixture đủ đại diện.

## 14. Quan sát partition assignment để biết canary thật sự đang làm việc

Có ít nhất ba trạng thái khác nhau:

1. Pod canary đã được Kubernetes tạo và được đánh dấu ready.
2. Spring Kafka listener container đã khởi động và tham gia group.
3. Consumer thực sự **được assign partition và xử lý record**.

Chỉ trạng thái thứ ba mới cho thấy phiên bản canary đã nhận workload phù hợp.

Với `@KafkaListener`, có thể đọc container từ `KafkaListenerEndpointRegistry`:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ConsumerAssignmentInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerAssignmentInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isListenerRunning() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-processor");

        return container != null && container.isRunning();
    }
}
```

Đây chỉ là kiểm tra trạng thái listener, **không phải** xác nhận đã được assign partition. Với `ConcurrentMessageListenerContainer`, có thể xem `getAssignedPartitions()` khi dùng API đó trong môi trường phù hợp; hoặc theo dõi sự kiện rebalance và Kafka client metrics.

Một listener quan sát rebalance có thể đặt trên container factory:

```java
import java.util.Collection;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

public class CanaryRebalanceObserver
        implements ConsumerAwareRebalanceListener {

    private static final Logger log =
        LoggerFactory.getLogger(CanaryRebalanceObserver.class);

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info(
            "event=kafka.assigned partitions={}",
            partitions
        );
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info(
            "event=kafka.revoked partitions={}",
            partitions
        );
    }
}
```

Gắn observer qua `ConcurrentKafkaListenerContainerFactory.getContainerProperties().setConsumerRebalanceListener(...)`.

Lưu ý:

- Không lưu assignment vào biến singleton rồi giả định mọi callback thuộc cùng member; có thể có nhiều consumer threads.
- Callback có thể xuất hiện theo cách khác nhau với eager/cooperative rebalance hoặc khi mất ownership.
- Nếu dùng metric assignment từ Kafka/AdminClient, cần phân biệt nhóm đang rebalance với nhóm đã ổn định.
- Log callback không thay thế số event đã được xử lý và dữ liệu nghiệp vụ đúng.

## 15. Những metric cần theo dõi khi canary chạy

Mục tiêu không chỉ “không có exception”. Cần biết canary có thực sự nhận traffic và xử lý an toàn.

| Nhóm | Ví dụ chỉ số | Diễn giải |
| --- | --- | --- |
| **Exposure** | Số partition canary sở hữu; event/giây; số event duy nhất | Canh được canary có nhận dữ liệu đại diện |
| **Liveness** | Consumer running, assignment, lần poll, tiến độ offset | Phát hiện canary kẹt dù pod vẫn sống |
| **Latency** | p50/p95/p99 processing duration, time-in-queue | Theo dõi tác động tới SLA |
| **Errors** | Parse error, business exception, retry rate, DLT rate | Phân biệt lỗi tạm thời và lỗi cuối |
| **Lag** | Consumer lag theo group/topic/partition | Phát hiện canary không bắt kịp |
| **Rebalance** | Số lần rebalance, thời gian chuyển quyền, revoked/lost partitions | Đánh giá ổn định khi rollout |
| **Business correctness** | Duplicate suppression, invalid transition, reconciliation mismatch | Phát hiện ghi sai dù job/consumer “thành công” |
| **Resources** | CPU, heap, GC, threads, DB pool utilization | Phát hiện regression hiệu năng và quá tải |
| **Downstream** | DB latency, HTTP error, outbound Kafka send failure | Phân biệt lỗi handler với lỗi hệ thống đích |

Nên gắn nhãn `service`, `releaseVersion`, `releaseTrack`, `groupId` và topic khi cardinality cho phép. Không đưa `eventId`, `orderId` hoặc mỗi consumer instance ID biến động cao vào label metric dạng time series một cách tùy tiện.

**Cẩn thận khi so sánh stable và canary:** hai nhóm pod có thể nhận partition với độ nóng và loại event khác nhau. Chỉ so sánh “canary 20 lỗi, stable 100 lỗi” không có ý nghĩa nếu volume chênh lệch. Hãy chuẩn hóa theo số event, loại event, độ phức tạp và phân phối key.

Đối với shadow group, lag và read rate độc lập với stable group. Đừng nhầm shadow lag với tình trạng backlog của production group.

## 16. Chọn quality gates cho giai đoạn quan sát

Một bộ gate minh họa:

| Gate | Điều kiện minh họa | Nếu không đạt |
| --- | --- | --- |
| Exposure | Canary đã xử lý ít nhất 10.000 event duy nhất và có traffic đại diện | Tiếp tục quan sát, chưa promote |
| Assignment | Canary có ít nhất một partition phù hợp hoặc có bằng chứng shadow coverage | Điều tra topology |
| Processing errors | Error rate canary không cao hơn baseline sau khi chuẩn hóa | Dừng mở rộng/rollback |
| DLT | Không có tăng bất thường của DLT business-critical | Chặn rollout |
| Lag | Lag không tăng liên tục và hồi phục sau rebalance trong SLA | Giảm tải/rollback |
| Latency | p95 latency không vượt ngân sách SLA đã đặt | Chặn rollout |
| Duplicate effects | Không có duplicate side effect trong kết quả đối soát | Rollback và điều tra dữ liệu |
| Schema | Không có parse error mới trên event types mục tiêu | Rollback/fix tương thích |
| Resource | CPU, heap và connection pool còn headroom | Giảm concurrency, tối ưu |
| Stability | Không có rebalance lặp bất thường do canary | Kiểm tra config/timeouts |

Các giá trị như 10.000 event hay p95 ngưỡng cụ thể cần được điều chỉnh theo hệ thống. Với topic có rất ít event, cần bổ sung corpus kiểm thử hoặc shadow/replay thay vì vội promote dựa trên vài phút không có lỗi.

Một thời gian quan sát 30 phút với **0 event trên canary** không chứng minh chất lượng mã. Gate exposure phải có tín hiệu từ số message và coverage nghiệp vụ, không chỉ từ thời gian.

### Phân loại sự cố

- **Canary không có assignment:** không đủ dữ liệu để đánh giá, chưa phải lỗi business.
- **Canary có assignment nhưng lag tăng:** có thể bị chậm, poll không tiến triển, retry loop hoặc DB contention.
- **Canary parse error:** nghi ngờ schema compatibility hoặc dữ liệu đặc thù partition.
- **Canary DLT nhiều:** policy recovery hoặc nghiệp vụ thay đổi; cần điều tra có mất nghiệp vụ hay không.
- **Stable cũng cùng lỗi:** có thể là outage chung, không phải regression riêng của canary.
- **Canary ghi sai dữ liệu:** rollback image không hoàn tác tác động đã commit; cần compensation/reconciliation.

## 17. Kế hoạch rollout từng giai đoạn

Một kế hoạch vận hành có thể gồm:

### Giai đoạn 0 — Preflight

- Test schema compatibility và read/write compatibility với phiên bản stable.
- Test handler bằng fixture edge cases, duplicate event và replay.
- Kiểm tra commit/retry/DLT policy.
- Xác định nguồn metrics, logs và dashboard.
- Chuẩn bị rollback image và quy trình xử lý dữ liệu sai.
- Kiểm tra group ID, static membership ID (nếu có), ACL và số partition.

### Giai đoạn 1 — Shadow (khi cần)

- Start một shadow consumer với group ID riêng và side effect bị tắt.
- Kiểm tra đọc được event thực tế, deserialization và validation.
- Ghi số event quan sát được, type coverage và lỗi.
- Không so sánh latency của shadow với writer production nếu shadow không gọi writer.

### Giai đoạn 2 — Một canary cùng group

- Tạo một canary pod version mới với cùng group ID stable.
- Chờ rebalance hoàn tất; đọc partition assignment của canary.
- Kiểm tra exposure: đã xử lý event thật chưa, các event thuộc loại nào.
- Theo dõi business output và lỗi đối chiếu với baseline.
- Không tăng rollout nếu group liên tục rebalance, canary không được gán việc hoặc dữ liệu không đủ đại diện.

### Giai đoạn 3 — Tăng phạm vi theo bằng chứng

Có thể mở rộng số consumer chạy phiên bản mới từng bước, ví dụ 1 → 2 → nhiều instance, đồng thời thu hẹp stable deployment. Mỗi lần thay đổi membership có thể lại gây rebalance. **Tỷ lệ replica không phải tỷ lệ message**, nên phải dựa vào traffic thực.

Ở mỗi giai đoạn, chỉ promote khi các gate được xác nhận lại cho phạm vi mới. Nếu topic có ít partition hơn số member, tăng replicas có thể không tăng exposure.

### Giai đoạn 4 — Hoàn tất rollout

- Thay stable version bằng version mới theo chính sách deploy.
- Kiểm tra group có đủ partition ownership và tổng lag hồi phục.
- Giữ dashboard so sánh sau rollout để phát hiện lỗi chỉ xuất hiện ở lưu lượng lớn.
- Xóa shadow consumer khi không còn cần, đồng thời quản lý offset/group metadata theo chính sách vận hành.

Một rollout đã promote vẫn cần quan sát; performance regression có thể chỉ lộ ra khi 100% partition được chuyển về version mới.

## 18. Rollback canary cùng group

Nếu phát hiện lỗi nghiêm trọng:

1. **Dừng mở rộng** và ghi lại version đang chạy cùng phạm vi ảnh hưởng.
2. **Dừng canary deployment** hoặc chuyển replica canary về 0 theo quy trình vận hành.
3. Chờ group rebalance và xác nhận stable đã tiếp quản các partition.
4. Quan sát lag, retry, DLT và lỗi sau chuyển quyền.
5. Đối soát dữ liệu đã được canary ghi; nếu sai, áp dụng compensation hoặc reprocess có kiểm soát.
6. Lưu log/audit về điều kiện rollback và nguyên nhân.

Ví dụ lệnh Kubernetes:

```bash
kubectl scale deployment/order-consumer-canary \
  --replicas=0 \
  --namespace=production
```

Lệnh có tính minh họa, cần quyền vận hành và xác minh đúng namespace/cluster trước khi thực thi.

**Không tự reset Kafka committed offsets về đầu topic khi rollback.** Một canary có thể đã xử lý và commit hợp lệ hàng nghìn event. Reset offset không theo kế hoạch sẽ làm stable nhận lại chúng; nếu handler không idempotent, có thể tạo side effect trùng. Việc reset/replay cần thủ tục riêng với kiểm tra downstream data và khả năng tái xử lý.

### Rollback mã không tương đương rollback dữ liệu

Nếu canary version mới đã ghi cột hoặc trạng thái mà stable version cũ không hiểu, stable có thể tiếp tục lỗi sau khi canary dừng. Vì vậy schema/database changes cần theo mô hình expand-and-contract, hoặc chọn phiên bản rollback tương thích dữ liệu mới. Không thực hiện destructive migration khi còn hai phiên bản consumer cùng hoạt động.

## 19. Shutdown và Kubernetes readiness

Consumer cần có cơ hội đóng tài nguyên một cách có kiểm soát khi pod bị dừng. Trong Kubernetes, quá trình termination thường gửi SIGTERM rồi chờ một khoảng trước khi SIGKILL. Spring Kafka container có thể dừng listener, hoàn tất xử lý theo chính sách và rời consumer group.

Điều cần xem xét:

- `terminationGracePeriodSeconds` đủ cho thời gian hoàn tất một record/chunk đang xử lý.
- Timeout HTTP/DB và retry của handler có giới hạn.
- Poll thread không bị chặn vô hạn.
- Application shutdown hook thực sự stop listener container.
- Rebalance callback không thực hiện thao tác quá chậm.
- Rolling deployment không dừng quá nhiều stable members đồng thời.

Ví dụ bổ sung trong pod spec:

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: consumer
      image: registry.example.com/order-consumer:1.9.0
      # Các thuộc tính env/resources cần điền đầy đủ như manifest.
```

Một readiness probe xanh xác nhận ứng dụng đáp ứng điều kiện health do bạn định nghĩa, **không tự bảo đảm consumer đã được assign partition hoặc xử lý đủ event**. Nếu tự biến “phải được assign ít nhất một partition” thành điều kiện readiness, consumer thừa hợp lệ có thể luôn bị đánh dấu not-ready. Điều này cần được cân nhắc theo topology.

Với Kubernetes Deployment, bạn có thể dùng startup/liveness/readiness probes cho lỗi ứng dụng, nhưng canary promotion cần **gate Kafka-specific** ngoài probe cơ bản.

## 20. Static membership và group.instance.id

Kafka hỗ trợ static membership trong các cấu hình/protocol phù hợp, thông qua `group.instance.id` ổn định cho logical member. Nó có thể giảm một số lần rebalance khi cùng instance khởi động lại nhanh, nhưng phải cấu hình đúng.

Sai lầm nguy hiểm:

```yaml
spring:
  kafka:
    consumer:
      properties:
        group.instance.id: "orders-consumer"
```

Nếu nhiều pod cùng dùng giá trị đó trong một group, coordinator có thể fencing/đẩy một member ra khỏi group. Không thể cấp chung một static membership ID cho mọi stable/canary pod.

Một lựa chọn là để **dynamic membership** trong giai đoạn rollout đầu tiên. Nếu dùng static membership, ID phải là duy nhất và ổn định theo logical instance, với chiến lược đặt tên đáp ứng vòng đời workload như StatefulSet hoặc nền tảng cho stable pod identity. Cần tính cả KafkaListener concurrency và quy tắc tạo suffix member ID của container.

Static membership không loại bỏ nhu cầu test rebalance/crash; trong một số kịch bản, việc mất member có thể cần chờ timeout lâu hơn trước khi partition được chuyển quyền.

## 21. Error handler, retry và DLT trong canary

Một canary thường là nơi đầu tiên gặp lỗi mới do schema hoặc business logic khác. Chính sách retry và DLT cần được thống nhất trước rollout.

| Tình huống | Nếu canary cùng group | Điều cần quyết định |
| --- | --- | --- |
| Lỗi tạm thời trong DB | Partition có thể bị chậm trong quá trình retry | Giới hạn retry, backoff, timeout |
| Parse exception | Có thể không vào được method listener | Error handler/deserialization strategy |
| Lỗi nghiệp vụ không retryable | Có thể chuyển DLT hoặc dừng xử lý | DLT policy, điều kiện skip |
| Record được gửi DLT rồi commit nguồn | Stable sẽ không tự nhận lại record đã được recover/commit theo policy | Có đủ bằng chứng và xử lý DLT không? |
| Crash trước offset commit | Có thể redeliver sau rebalance | Idempotency cho side effect |
| Retry topic không đồng bộ | Có thể thay đổi thứ tự end-to-end | Versioning/ordering constraints |

**Không bật cùng lúc một thay đổi lớn của business code và một thay đổi lớn của retry/DLT policy** nếu mục tiêu là đánh giá regression của canary. Khi nhiều thứ đổi cùng lúc, khó quy trách nhiệm và có thể làm record bị commit/skip ngoài dự kiến.

Trong shadow mode, hãy xem lại mọi recoverer và DLT publisher: một shadow consumer không được phép vô tình đẩy message thật sang DLT production hoặc kích hoạt workflow cảnh báo gây side effect.

### Không đánh đồng “không có error” với thành công

Nếu error handler bắt exception rồi recover một record sang DLT, listener group có thể tiếp tục chạy và Kafka lag giảm. Nhưng tác vụ nghiệp vụ vẫn **chưa được hoàn tất thành công**. Canary gate phải đo DLT/recovery outcome cùng business reconciliation, không chỉ đo application exception count.

## 22. Kiểm thử trước triển khai bằng embedded Kafka

Với `spring-kafka-test`, có thể tạo topic nhiều partition và hai consumer container cùng group để kiểm chứng topology canary.

Dependency Gradle ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Một mô hình test:

```text
Embedded Kafka: topic "orders.canary.test", 6 partitions
Group: "orders-canary-test-group"

Start stable A
    |
    v
Wait until A owns 6 partitions
    |
    v
Start canary B, same group
    |
    v
Wait until assignment stable:
    union(partitions A,B) = all 6 partitions
    intersection(A,B) = empty
    canary B owns >= 1 partition
    |
    v
Publish event corpus
    |
    v
Check all event IDs handled;
check canary handled at least one;
check business results and retries
    |
    v
Stop B
    |
    v
Wait A owns all partitions again
```

Ví dụ assertion dùng Awaitility và API container thích hợp:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        Set<TopicPartition> stableParts =
            Set.copyOf(stable.getAssignedPartitions());

        Set<TopicPartition> canaryParts =
            Set.copyOf(canary.getAssignedPartitions());

        assertFalse(canaryParts.isEmpty());

        Set<TopicPartition> all =
            new HashSet<>(stableParts);

        all.addAll(canaryParts);

        assertEquals(6, all.size());
        assertTrue(
            Collections.disjoint(stableParts, canaryParts)
        );
    });
```

Đoạn này giả định `stable` và `canary` là hai `ConcurrentMessageListenerContainer` đã start và có non-null assignment. Trong test hoàn chỉnh nên chuyển `null` thành tập rỗng trước khi gọi `Set.copyOf()` và cô lập group ID/topic cho mỗi test. Đừng kỳ vọng canary sở hữu một partition cụ thể: assignment là kết quả của group coordinator và assignor.

**Đây là phép thử rebalance và exposure cơ bản, không phải phép thử canary production hoàn chỉnh.** Cần thêm các assertion về xử lý dữ liệu, DLT, offset và transaction khi business handler có side effect.

## 23. Kiểm thử shadow không ghi dữ liệu thật

Một integration test khác dùng **hai consumer groups**:

```text
Group stable-test: đọc topic test -> business DB test
Group shadow-test: đọc topic test -> validation metrics only
```

Test có thể:

1. Tạo topic test với vài partition và một tập event đại diện.
2. Start stable consumer group và shadow consumer group độc lập.
3. Chờ cả hai group được assign partition.
4. Publish N event có eventId duy nhất.
5. Xác nhận stable đã tạo N business results đúng.
6. Xác nhận shadow đã validate N event mà **không tạo thêm business output**.
7. Cho shadow throw parse/validation error; kiểm tra stable vẫn tiếp tục xử lý.
8. Xác nhận committed offsets của hai group được quản lý độc lập.

Nếu shadow dùng `auto.offset.reset=latest`, test phải start/đợi assignment rồi mới publish event corpus; nếu publish trước khi group có vị trí đọc, có thể bị bỏ qua.

Với side effect nhạy cảm, nên cho shadow dùng quyền database read-only hoặc không cấp credential ghi. Khi đó test có thể chứng minh ngay cả lỗi code vô tình gọi write cũng bị ngăn bởi tầng hạ tầng.

## 24. Kiểm thử crash, rollback và dữ liệu trùng

Embedded broker kết hợp graceful `container.stop()` không mô phỏng đầy đủ process crash. Để đánh giá bảo đảm at-least-once thực tế, cần test độc lập:

```text
Kafka broker test
        |
   Consumer canary process
        |
        +-- business DB commit event X
        |
        X process kill trước Kafka offset commit
        |
        v
Stable consumer tiếp quản partition
        |
        v
X có thể được giao lại
        |
        v
Idempotent handler nhận diện X đã xử lý
```

Test cần biết chính xác fault được chèn ở đâu; nếu chỉ kill ở thời điểm ngẫu nhiên, có thể process đã commit offset trước đó và không có replay.

Một bộ test đủ mạnh cần xác nhận:

- Tập partition trước/sau crash và thời gian tiếp quản.
- Committed offset của group trước khi crash.
- Event X được xử lý lại nếu committed offset chưa vượt qua X.
- Business table/side effect cuối cùng không có duplicate.
- Nếu DLT đã nhận record, có quy trình theo dõi và xử lý.
- Khi deploy version cũ trở lại, data schema vẫn tương thích.

Dùng Testcontainers, ứng dụng chạy trong process riêng, network fault injection hoặc staging/chaos testing khi cần. Không dùng broker production để chủ động kill consumer/đổi offsets chỉ phục vụ thử nghiệm.

## 25. Phân tích tình huống rollout thất bại

### 25.1. Canary ready nhưng không xử lý event nào

**Triệu chứng:** Pod xanh, không có lỗi, nhưng metric event rate bằng 0.

**Nguyên nhân có thể:** số member lớn hơn số partition, assignor không cấp partition, group ID sai, listener chưa subscribe hoặc topic trống.

**Phản ứng:** kiểm tra assignment, group, topic, broker metadata; chưa promote. Nếu cần kiểm tra parser trên corpus, chạy shadow group với offset/corpus được kiểm soát.

### 25.2. Canary nhận nhiều traffic hơn dự kiến

**Triệu chứng:** một pod canary xử lý gần bằng tổng stable.

**Nguyên nhân có thể:** key skew, hot partition hoặc cấu hình concurrency/assignment khác dự tính.

**Phản ứng:** đánh giá số message theo partition, rate limit ở application khi thích hợp, giảm phạm vi hoặc đổi mô hình canary. Không chỉ dựa vào replicas ratio.

### 25.3. Lag tăng mạnh ngay khi canary join

**Triệu chứng:** group lag tăng, log có nhiều lần revoked/assigned.

**Nguyên nhân có thể:** rebalance kéo dài, xử lý record quá chậm, retry loop, consumer mất heartbeat/poll hoặc DB bottleneck.

**Phản ứng:** kiểm tra rebalance duration, max poll interval, handler latency, error handler và DB metrics; nếu không hồi phục trong SLA, rollback.

### 25.4. Canary tạo nhiều DLT messages

**Triệu chứng:** canary không crash, offset vẫn tiến nhưng business output thiếu.

**Nguyên nhân có thể:** parser lỗi, policy recover/skip không phù hợp hoặc bản ghi đặc biệt chỉ xuất hiện ở partition canary.

**Phản ứng:** chặn promote, phân loại DLT theo error code/event type, điều tra có mất dữ liệu nghiệp vụ không, quyết định replay an toàn.

### 25.5. Rollback xong vẫn lỗi

**Triệu chứng:** Stable version cũ nhận lại partition nhưng tiếp tục fail.

**Nguyên nhân có thể:** canary đã ghi dữ liệu không tương thích, đổi schema phá backward compatibility, hoặc dữ liệu đã bị side effect ngoài Kafka.

**Phản ứng:** giữ rollback image ổn định, xử lý compatibility/migration và business compensation, không reset offsets bừa bãi.

## 26. Checklist triển khai canary consumer

| Hạng mục | Câu hỏi cần trả lời trước promote |
| --- | --- |
| Group topology | Canary cùng group hay shadow riêng? |
| Partition coverage | Canary có assignment và event exposure đủ đại diện không? |
| Consumer concurrency | Tổng member có vượt số partition không? |
| Schema compatibility | Stable và canary cùng đọc/ghi được các version event liên quan không? |
| Error handling | Retry, DLT, parse failure và commit offsets có được hiểu rõ không? |
| Idempotency | Replay sau rebalance có gây duplicate business effect không? |
| Side effects | Shadow mode có bị vô hiệu hóa quyền ghi, publish, email/API không? |
| Metrics | Có tách release track/version, normalized event error rates và lag không? |
| Rollback | Có thể dừng canary và tiếp quản partition mà không sửa offsets tùy tiện không? |
| Data compatibility | Stable code có xử lý được DB/data sau khi canary đã chạy không? |
| Shutdown | SIGTERM, termination grace period và in-flight processing được quản lý ra sao? |
| Capacity | Kafka, DB, CPU, memory và connection pool có đủ headroom? |
| Security | Quyền Kafka/DB của canary và shadow có đúng mức cần thiết? |
| Audit | Có lưu version, thời điểm, người triển khai, gate results và lý do rollback? |
| Validation | Đã test join/leave, crash/offset window, idempotency và DLT trên môi trường phù hợp? |

Checklist giúp quyết định vận hành, không thay thế thử nghiệm và đánh giá thực tế ở từng hệ thống.

## 27. Bài tập thực hành

Tạo topic `orders.canary.lab` có sáu partition, một ứng dụng Spring Kafka tiêu thụ `OrderEvent` và bảng projection PostgreSQL/H2 trong môi trường test.

### Phần A — Canary cùng group

1. Start hai stable consumer instances cùng `groupId=orders-lab`, mỗi instance concurrency 1.
2. Gửi các event có key và version rõ ràng, xác nhận projection đúng.
3. Start một canary instance version mới, dùng cùng group ID và concurrency 1.
4. Chờ group assignment ổn định bằng Awaitility; ghi lại tập partition stable/canary.
5. Publish thêm 60 event vào các partition, xác nhận không mất business key.
6. Đo canary đã nhận bao nhiêu event; so sánh với partition traffic thực tế.
7. Dừng canary và kiểm tra stable tiếp quản các partition, không mất tiến độ.

### Phần B — Shadow group

1. Tạo shadow instance có `groupId=orders-lab-shadow`.
2. Chỉ cho phép parse/validate, không được ghi bảng projection production/test chính.
3. Gửi corpus có bản ghi hợp lệ, thiếu trường, version cũ và status không nhận diện.
4. Xác nhận stable tiếp tục xử lý theo policy, shadow báo cáo lỗi độc lập.
5. Kiểm tra shadow group có offset riêng và không làm stable rebalance.

### Phần C — Retry và tính đúng đắn

1. Tạo lỗi tạm thời ở DB, kiểm tra retry/backoff và committed offsets.
2. Cho record đã được DB commit nhưng offset Kafka chưa commit rồi gây crash có kiểm soát.
3. Xác nhận record có thể replay và marker idempotency ngăn ghi trùng.
4. Tạo event version cũ sau version mới, đảm bảo projection không bị ghi lùi.
5. Tạo lỗi non-retryable, kiểm tra DLT policy và không tuyên bố record đã xử lý thành công.

### Phần D — Quyết định rollout

Lập một báo cáo với các cột:

| Stage | Version | Group | Assigned partitions | Unique events | Error rate | DLT | Lag | Quyết định |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Stable baseline | v1 | orders-lab | Theo thực tế | ... | ... | ... | ... | Baseline |
| Shadow | v2 | orders-lab-shadow | Theo thực tế | ... | ... | ... | ... | Go/No-go |
| Canary one pod | v2 | orders-lab | Theo thực tế | ... | ... | ... | ... | Go/No-go |
| Rollout mở rộng | v2 | orders-lab | Theo thực tế | ... | ... | ... | ... | Promote/Rollback |

Hãy giải thích vì sao phần trăm pod canary khác với phần trăm event mà nó xử lý, tại sao shadow không chứng minh transaction end-to-end, và vì sao rollback image không xóa tác động nghiệp vụ đã commit.

## 28. Tổng kết

**Canary consumer instance** trong Spring Kafka là chiến lược triển khai phiên bản mới với phạm vi tác động có kiểm soát, nhưng cách kiểm soát khác đáng kể so với HTTP. Khi stable và canary dùng **cùng consumer group**, Kafka phân phối **partition**, không bảo đảm chia phần trăm message. Canary thực sự xử lý event production, có thể gây rebalance và phải có chính sách offset, retry, DLT, idempotency và rollback chặt chẽ.

Khi dùng **shadow group riêng**, canary có thể đọc dữ liệu thực để đánh giá parser/validation mà không làm stable group thay đổi partition ownership; đổi lại nó tiêu tốn tài nguyên riêng, có offset riêng và chỉ an toàn nếu mọi side effect production bị vô hiệu hóa. Shadow là bước đệm hữu ích, nhưng không thay thế bước kiểm tra xử lý thật.

Quy trình đáng tin cậy là xác định blast radius và topology → kiểm chứng schema/transaction/idempotency → triển khai một instance mới có quan sát release-specific → xác nhận assignment và event exposure thực → đánh giá lag, errors, DLT, latency và business correctness → promote hoặc rollback có kiểm soát. **Một canary thành công phải chứng minh dữ liệu vẫn đúng sau chuyển quyền và lỗi, chứ không chỉ chứng minh pod đã chạy.**
