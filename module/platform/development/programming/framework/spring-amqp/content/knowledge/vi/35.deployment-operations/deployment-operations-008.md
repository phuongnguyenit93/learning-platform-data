# RabbitMQ cluster, quorum và tác động khi node mất kết nối

Một ứng dụng Spring Boot gửi `OrderCreated` qua `RabbitTemplate` và xử lý bằng `@RabbitListener` có thể chạy ổn trên RabbitMQ một node. Nhưng khi triển khai production, chuyện gì xảy ra nếu node giữ **queue leader** bị tắt, hai node mất kết nối mạng, hoặc ứng dụng vẫn mở TCP connection nhưng **queue không còn đủ quorum** để nhận message?

Câu trả lời phụ thuộc vào **cluster membership**, **queue type**, **số replica thực tế của từng quorum queue**, **phe còn đa số khi có partition** và **các xác nhận chưa hoàn tất ở publisher/consumer**. Một broker node còn sống không đồng nghĩa mọi queue mà nó biết đều đang khả dụng.

Bài thuộc chương **Triển khai và vận hành** của module **SPRING_AMQP**. Ta kết nối lý thuyết RabbitMQ cluster và quorum queues với cấu hình exchange–queue–binding, `RabbitTemplate`, `@RabbitListener`, publisher confirms/returns, ACK/NACK, retry, DLQ, transaction, observability và runbook bảo trì. Trọng tâm: **xây hệ thống bất đồng bộ có khả năng chịu lỗi và biết khi nào không còn đủ điều kiện an toàn để tiếp tục**.

**Phạm vi phiên bản:** Quorum queues dùng Raft trong RabbitMQ hiện đại. Từ RabbitMQ 4.3, hệ thống cluster metadata và quy tắc delivery-count có thay đổi so với các bản trước. Phần triển khai Spring minh họa Java 17+, Spring Boot 3.x và Spring AMQP 3.x; những tham số nhạy cảm phiên bản phải được đối chiếu với broker đang chạy.

## 1. Cluster có nghĩa gì và không có nghĩa gì?

Một **RabbitMQ cluster** là tập các RabbitMQ nodes có thể trao đổi thông tin và quản lý tài nguyên trong một hệ thống logic: virtual host, exchange, queue, binding, quyền truy cập và routing. Client AMQP 0-9-1 thông thường **mở một connection tới một node tại một thời điểm**; node đó có thể chuyển thao tác tới leader của queue nằm ở node khác.

```text
          Spring Boot publisher / consumer applications
                            |
                    DNS / load balancer
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
      RabbitMQ A        RabbitMQ B        RabbitMQ C
          |                 |                 |
          +-----------------+-----------------+
                   RabbitMQ cluster
          metadata, exchanges, queues, routing

     Mỗi connection của AMQP client bám một node cụ thể.
```

Tuy nhiên, **cluster không mặc định sao chép dữ liệu message của mọi queue lên mọi node**.

| Tài nguyên | Đặc trưng | Điều cần kiểm tra khi node lỗi |
|---|---|---|
| **Classic queue** | Queue thông thường, không giả định có các replicas khác node | Node giữ queue còn hoạt động không, dữ liệu được bảo vệ bằng gì? |
| **Quorum queue** | Queue replicated dùng **Raft**, có leader và follower members | Queue có **đa số members** online và kết nối được với nhau không? |
| **Stream** | Log có retention/replay và replication tùy cấu hình | Replica/leader/offset có semantics riêng, không giống queue ACK |
| **Cluster metadata** | Metadata lưu/đồng thuận theo cơ chế phụ thuộc version | Metadata quorum/cluster health có thể tác động vận hành, declaration, membership |

Quorum queue thường phù hợp sự kiện nghiệp vụ cần độ an toàn dữ liệu cao và phải chịu lỗi một node, nhưng tiêu thụ thêm I/O, network và disk để replicate. Không lựa chọn theo tên “quorum” mà bỏ qua throughput, latency, retention, message size và loại queue thực sự cần thiết.

### 1.1. Ba trạng thái cần phân biệt

1. **Node alive:** process RabbitMQ còn chạy hoặc còn mở cổng mạng.
2. **Cluster peers reachable:** các nodes liên lạc được và các cơ chế đồng thuận liên quan có khả năng tiến triển.
3. **Quorum queue available:** **riêng queue cụ thể** còn leader và đa số members cần thiết để xử lý các thao tác.

Một node trả lời health check **không chứng minh** queue Orders đang có quorum. Ngược lại, khi node X chết, những queue không có member trên X có thể vẫn hoạt động bình thường. Vì thế monitoring phải theo **per-queue quorum** chứ không chỉ đếm số process RabbitMQ.

## 2. Quorum queue: leader, followers và majority

### 2.1. Mô hình Raft

Một quorum queue có các thành viên (*members/replicas*) đặt trên những RabbitMQ nodes khác nhau. Một member được bầu làm **leader**, các member còn lại là **followers**. Việc ghi queue state cần đồng thuận theo Raft.

```text
                  Quorum queue: orders.created.qq

             Node A          Node B          Node C
             LEADER          FOLLOWER        FOLLOWER
                |                |                |
 publish ------>|-- replicate -->|                |
                |-- replicate ------------------->|
                |<-- Raft log / acknowledgments --|
                |
                +-- quorum commit
                +-- publisher confirm
```

Client có thể kết nối vào B dù leader hiện ở A. Broker xử lý tuyến đường cần thiết tới queue leader; **đừng hard-code client kết nối tới leader** vì leader có thể chuyển sang node khác sau sự cố.

Publisher confirms là cơ chế quan trọng để ứng dụng nhận biết broker đã xác nhận publish theo cam kết của queue. Khi message đã được quorum queue xác nhận, RabbitMQ cung cấp data-safety guarantee với điều kiện **đa số nodes giữ queue members không bị mất vĩnh viễn**. Những message **chưa được confirm** không có bảo đảm tương tự.

### 2.2. Công thức quorum

Với queue có \(N\) members, quorum là số member tối thiểu chiếm đa số:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

| Số members của **một queue** | Số cần để đạt quorum | Số members có thể lỗi mà vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

**Với 3 members, cần 2; với 5, cần 3.** Số lẻ thường có lợi hơn số chẵn: queue bốn members chỉ chịu một lỗi, không hơn queue ba members trong tình huống đơn giản.

Cần hiểu **N là số members của queue, không phải tổng số nodes cluster**. Ví dụ cluster có 5 nodes A/B/C/D/E, nhưng queue chỉ có 3 members trên A/B/C. Nếu A và B cùng offline, queue chỉ còn C = 1/3 nên mất quorum **dù cluster vẫn có 3/5 nodes online**.

### 2.3. Vì sao cluster hai nodes không đạt mục tiêu chịu một lỗi?

Hai members cần 2/2 để đạt đa số. Mất một member khiến queue không thể tiến hành. Với yêu cầu chịu lỗi một node, mô hình 3 members trên 3 nodes ở những failure domains phù hợp thường hợp lý hơn.

Tăng queue group size từ 3 lên 5 có thể tăng khả năng chịu lỗi lên hai members, nhưng kéo theo chi phí replication, ổ đĩa, mạng và ảnh hưởng confirm latency. Quyết định cần dựa trên SLO/RPO/RTO, vị trí đặt members và benchmark, không phải tăng replica count càng lớn càng tốt.

## 3. Node bị lỗi: những kịch bản rất khác nhau

Giả sử cluster A/B/C và quorum queue `orders.created.qq` có 3 members, một trên mỗi node, leader ban đầu ở A.

### 3.1. Mất follower C

```text
A (leader) <--------> B (follower)       X C (follower)
        \_____________/
            quorum 2/3
```

Queue còn **2/3** nên có thể tiếp tục publish, confirm và delivery. Nhưng hệ thống đã mất một lớp redundancy: nếu thêm A hoặc B bị lỗi trước khi C hồi phục, queue sẽ mất quorum.

Cần theo dõi: online members, publisher confirm RTT, disk/network, số message ready/unacked và thời điểm C bắt kịp replicated log sau khi quay lại. **Không** tiến hành rolling restart node khác khi queue chỉ còn vừa đủ đa số.

### 3.2. Mất leader A

```text
Trước: A=LEADER; B,C=FOLLOWERS
         |
         X A disconnected
         |
       B + C = 2/3
         |
     Raft election
         |
   B hoặc C trở thành LEADER
         |
   publish / delivery tiếp tục
```

Vì B/C vẫn chiếm đa số, chúng có thể elect leader mới. Trong thời gian chưa có leader:

- Publish có thể bị trì hoãn, timeout, hoặc một số lần gửi bị NACK tùy thời điểm và đường kết nối.
- Queue có thể tạm ngưng phát **delivery mới** cho consumers.
- Những delivery đã gửi nhưng chưa ACK có thể bị requeue và giao lại sau leader election.
- Client Spring đang kết nối vào A cần reconnect node B/C; client kết nối B/C vẫn có thể thấy gián đoạn ngắn ở thao tác liên quan tới queue.

Thời gian bầu leader thường tính bằng giây trong nhiều trường hợp vận hành bình thường, **không phải deadline cố định**. Khi tải cao, network latency hoặc nhiều node không khỏe, thời gian thực có thể lớn hơn.

### 3.3. Mất A và B, chỉ còn C

```text
A: OFFLINE       B: OFFLINE        C: ONLINE
   X               X                  |
                                      |
                                     1/3
                           < quorum required 2/3
                                      |
                             QUEUE UNAVAILABLE
```

Không đạt đa số thì quorum queue không thể phục vụ hoạt động ghi/giao message như bình thường. Management endpoint ở C có thể vẫn phản hồi, nhưng queue không có majority. Publisher có thể timeout/NACK, consumer có thể ngừng nhận delivery, outbox pending tăng.

**Đừng tạo lại queue trên C hoặc ép một replica thiểu số trở thành hệ thống độc lập** để “chữa cháy”: có thể gây mất dữ liệu hoặc làm phức tạp recovery. Phải khôi phục đủ members hoặc thực hiện runbook disaster recovery có kiểm chứng, backup và chấp nhận rõ RPO/RTO.

### 3.4. Mạng bị partition: A | B,C

```text
       Partition 1                            Partition 2
       +-----------+             X            +-----------+
       | A         |--------------------------| B --- C   |
       | 1/3       |                          | 2/3       |
       +-----------+                          +-----------+
       MINORITY                               MAJORITY
       không đủ quorum                       bầu/duy trì leader
                                             và tiếp tục khi an toàn
```

Ngay cả khi A từng giữ leader, phía A không được tự tiếp tục ghi queue nếu không còn majority. Phía B/C có thể phục vụ sau khi có leader hợp lệ.

**Điểm phiên bản quan trọng:** Từ **RabbitMQ 4.3**, tài liệu cluster partition được thay đổi: metadata store Raft-based Khepri là lựa chọn duy nhất và các khóa partition-handling thời Mnesia như `cluster_partition_handling` được chấp nhận nhưng **không còn hiệu lực**. Các cluster RabbitMQ cũ có cơ chế khác. Phải dùng tài liệu đúng **phiên bản đang chạy**, không sao chép tham số xử lý partition từ bài viết 3.x rồi mong nó có tác dụng trên 4.3.

### 3.5. Mất node không giữ member của queue

Một cluster 5 nodes có thể giữ queue ba members trên A/B/C. Nếu D lỗi, quorum của queue này có thể vẫn khỏe, nhưng các AMQP client **đang kết nối vào D** sẽ mất connection và phải reconnect. Những queue khác, stream khác hoặc metadata vẫn có thể bị ảnh hưởng. Đây là lý do phải xem **queue membership**, **client connectivity** và **cluster health** riêng biệt.

## 4. Bảng phân loại lỗi cho vận hành

| Sự cố | Trạng thái queue có thể xảy ra | Tác động Spring app |
|---|---|---|
| Client mất TCP tới một node, cluster/queue vẫn khỏe | Queue vẫn phục vụ | Publisher outstanding confirms unknown; listener reconnect |
| Follower mất, quorum còn đủ | Queue vẫn có thể phục vụ | Có thể tăng latency, giảm redundancy |
| Leader mất, followers còn majority | Tạm gián đoạn election rồi phục hồi | Confirm trễ/NACK/timeout; delivery pause/redelivery |
| Hai trong ba queue members offline | Queue mất quorum | Publish/consume không tiến triển; app cần backoff/outbox |
| App kết nối vào node minority | Node có thể còn online nhưng queue không phục vụ | Connect OK không chứng minh publish/consume OK |
| Node mới thêm vào cluster | Queue cũ chưa chắc có replica mới | Không suy ra replication factor tự tăng |
| Consumer DB commit nhưng broker chưa nhận ACK | Message có thể redeliver | Tác dụng phụ trùng nếu không có idempotency |

## 5. Publisher confirms và những kết quả không chắc chắn

### 5.1. Broker ACK khác consumer ACK

```text
Spring publisher           RabbitMQ quorum queue       Spring consumer
     |                              |                        |
     |--- publish ----------------->| replicate/commit       |
     |<-- publisher confirm ACK ----|                        |
     |                              |--- delivery ---------->|
     |                              |                     DB commit
     |                              |<-- consumer ACK --------|
```

Publisher confirm cho biết broker đã xử lý publish theo semantics của queue; **không xác nhận consumer đã commit database**. Khi leader thay đổi giữa hai bước, message đã publisher confirm vẫn có thể được giao lại nếu consumer ACK chưa được broker nhận.

| Tín hiệu publisher | Diễn giải | Hành động |
|---|---|---|
| Confirm ACK + không return | Broker xác nhận publish được định tuyến theo contract | Có thể đánh dấu publish completed, không gọi business completed |
| Confirm ACK + mandatory return | Exchange xử lý publish nhưng không có queue route phù hợp | Sửa routing/topology, không đánh dấu delivered |
| Negative confirm | Broker/client báo không xác nhận thành công | Retry có phân loại/backoff, giữ event ID |
| Future confirm timeout | **UNKNOWN**: broker có thể đã nhận hoặc chưa | Giữ intent bền vững, retry idempotent |
| Connection mất trước confirm | UNKNOWN, future/callback RAM có thể mất khi app crash | Outbox/reconciliation khi hồi phục |

**Đừng coi timeout là NACK.** Nếu broker đã lưu message nhưng ACK publisher bị mất trên network, producer retry có thể sinh bản message thứ hai. Consumer phải dùng `eventId` bất biến để deduplicate.

### 5.2. Spring Boot có nhiều endpoints của cùng cluster

```yaml
spring:
  rabbitmq:
    addresses: rabbit-a.internal:5672,rabbit-b.internal:5672,rabbit-c.internal:5672
    username: orders-app
    password: REPLACE_FROM_SECRET_MANAGER
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
```

Các endpoints thuộc **cùng một RabbitMQ cluster**. Danh sách addresses hỗ trợ việc chọn endpoint và phục hồi kết nối; nó **không** có nghĩa một `convertAndSend` phát ba bản sang ba broker độc lập.

Trong production cần cấu hình authentication/TLS/secret rotation phù hợp. Nếu ứng dụng kết nối qua load balancer thay vì nhiều addresses, health checks và routing của load balancer phải tránh node không sẵn sàng, nhưng một node TCP-healthy vẫn có thể không phục vụ được một quorum queue cụ thể.

Spring AMQP cung cấp cơ chế quản lý connection/channel recovery và `RabbitAdmin` có thể khai báo lại những topology beans phù hợp sau khi kết nối được tái lập. **Recovery của client không thể tạo majority cho queue đã mất quorum**.

### 5.3. Ví dụ chờ correlated publisher confirm

```java
@Service
public class OrderEventPublisher {
    private final RabbitTemplate template;

    public OrderEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void send(OrderCreated event) throws Exception {
        CorrelationData correlation = new CorrelationData(
                UUID.randomUUID().toString());

        template.convertAndSend(
                "orders.events",
                "orders.created",
                event.toJson(),
                message -> {
                    MessageProperties props = message.getMessageProperties();
                    props.setMessageId(event.eventId().toString());
                    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
                    props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                correlation);

        CorrelationData.Confirm result =
                correlation.getFuture().get(10, TimeUnit.SECONDS);

        if (!result.isAck()) {
            throw new IllegalStateException(
                    "NACK: " + result.getReason());
        }
        if (correlation.getReturn() != null) {
            throw new IllegalStateException(
                    "Message bị trả lại do không có route");
        }
    }
}
```

Các imports chính thuộc `org.springframework.amqp.rabbit.core.RabbitTemplate`, `org.springframework.amqp.rabbit.connection.CorrelationData`, `org.springframework.amqp.core.MessageProperties`, `org.springframework.amqp.core.MessageDeliveryMode`, `java.util.UUID`, `java.util.concurrent.TimeUnit` và `org.springframework.stereotype.Service`. `OrderCreated` là DTO minh họa có `eventId()` và `toJson()`.

Code minh họa cách phân loại kết quả, **chưa phải outbox/relay hoàn chỉnh**. Với thông lượng cao, nên xử lý confirms bất đồng bộ qua `getFuture().whenComplete(...)`, có giới hạn số publish đang chờ để tránh hết bộ nhớ khi failover. Với timeout cần ghi trạng thái **UNKNOWN**, không quên event intent.

## 6. Khai báo quorum queue từ Spring AMQP

### 6.1. Queue type phải được cấu hình ở chính queue

```java
@Configuration
public class OrderTopology {

    @Bean
    Declarables orderMessagingTopology() {
        DirectExchange events = new DirectExchange("orders.events");
        DirectExchange deadExchange = new DirectExchange("orders.dlx");

        Queue work = QueueBuilder.durable("orders.created.qq")
                .withArgument("x-queue-type", "quorum")
                .withArgument("x-quorum-initial-group-size", 3)
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("orders.failed")
                .build();

        Queue dead = QueueBuilder.durable("orders.created.dead")
                .withArgument("x-queue-type", "quorum")
                .build();

        Binding workBinding = BindingBuilder.bind(work)
                .to(events).with("orders.created");
        Binding deadBinding = BindingBuilder.bind(dead)
                .to(deadExchange).with("orders.failed");

        return new Declarables(
                events, work, deadExchange, dead,
                workBinding, deadBinding);
    }
}
```

Imports từ `org.springframework.amqp.core.*` và `org.springframework.context.annotation.*`.

**Những điểm phải kiểm tra:**

- `x-queue-type=quorum` chọn queue type; `x-quorum-initial-group-size=3` chỉ định initial target group size, không phải bảo đảm ba replicas thực sự khỏe tại mọi thời điểm.
- Tạo queue sau khi cluster/node configuration sẵn sàng và xác minh **actual members, leader và online state** bằng CLI/Management.
- Quorum queue cần topology bền vững; không dùng nó để thay queue tạm thời exclusive/auto-delete của RPC reply-to.
- Không chuyển **classic queue đang tồn tại** thành quorum bằng cách redeclare cùng tên với argument mới. RabbitMQ có thể báo inequivalent args; cần migration/cutover rõ ràng.
- `RabbitAdmin` khai báo queue/exchange/binding; nó **không** tự thay đổi membership hoặc sửa partition khi mất quorum.
- Quorum queue có các policies về delivery limit, dead-letter-strategy, overflow, TTL và max-length cần quản lý phù hợp workload.

### 6.2. Định tuyến và nơi giữ leader

Một publisher kết nối node B có thể gửi tới exchange rồi RabbitMQ xử lý đường tới queue leader trên A. Không đặt cứng tên leader vào publisher/consumer config; leader là **đối tượng có thể thay đổi sau election**.

Nếu một queue mới chỉ có hai thành viên khi hệ thống đang gặp lỗi khởi tạo, đừng coi “declare OK” là đã đạt HA theo thiết kế ba replicas. Hãy kiểm tra membership online và thực hiện quy trình reconcile khi cluster ổn định.

## 7. Consumer ACK, retry và sự kiện bị xử lý lại

### 7.1. Tình huống commit DB nhưng mất ACK

```text
RabbitMQ leader A                     Spring consumer
       |                                    |
       |---- deliver event E -------------->|
       |                                    | DB transaction
       |                                    | COMMIT OK
       X  node A mất kết nối                |
       |                              ACK không chắc tới
       |                                    |
    B/C elect leader                       |
       |---- redeliver E ------------------>|
       |                                    | nhận diện E đã xử lý
       |<------------- ACK -----------------|
```

Quorum replication **không tạo exactly-once processing** cho database. Nếu broker chưa biết ACK đã hoàn tất, message có thể được phát lại. Vì vậy consumer phải **idempotent**, kể cả khi publisher đã dùng confirms.

### 7.2. Idempotent consumer trong PostgreSQL

```sql
CREATE TABLE processed_order_events (
    consumer_name varchar(100) NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Service xử lý domain và marker trong cùng transaction:

```java
@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderCreated event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_order_events (consumer_name, event_id)
            VALUES ('orders-projection', ?)
            ON CONFLICT DO NOTHING
            """, event.eventId());

        if (inserted == 0) {
            return; // Sự kiện này đã commit trước đó.
        }

        jdbc.update("""
            INSERT INTO order_projection (order_id, state)
            VALUES (?, 'CREATED')
            ON CONFLICT (order_id)
            DO UPDATE SET state = EXCLUDED.state
            """, event.orderId());
    }
}
```

Listener:

```java
@Component
public class OrderCreatedListener {
    private final OrderProjectionService projection;
    private final ObjectMapper mapper;

    public OrderCreatedListener(
            OrderProjectionService projection, ObjectMapper mapper) {
        this.projection = projection;
        this.mapper = mapper;
    }

    @RabbitListener(queues = "orders.created.qq")
    public void handle(Message message) throws Exception {
        OrderCreated event =
                mapper.readValue(message.getBody(), OrderCreated.class);
        projection.applyOnce(event);
    }
}
```

Imports chính: `org.springframework.amqp.rabbit.annotation.RabbitListener`, `org.springframework.amqp.core.Message`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.stereotype.Service`, `org.springframework.stereotype.Component` và `com.fasterxml.jackson.databind.ObjectMapper`.

Phương thức `projection.applyOnce` gọi qua bean/proxy Spring, nên DB transaction hoàn tất trước khi listener trả về bình thường; container `AcknowledgeMode.AUTO` có thể ACK sau đó. ACK của RabbitMQ **không nguyên tử với DB commit**, vì vậy marker phải có unique constraint và được ghi cùng business effect.

Ví dụ projection dùng phép cập nhật snapshot đơn giản. Nếu có các event khác nhau như `OrderPaid`, `OrderCancelled`, vẫn cần `aggregateVersion` và validation state transitions; dedup event ID không giải quyết sai thứ tự nghiệp vụ.

### 7.3. Listener factory và recovery

```java
@Bean("ordersListenerFactory")
SimpleRabbitListenerContainerFactory ordersListenerFactory(
        ConnectionFactory cf) {
    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
    factory.setConcurrentConsumers(2);
    factory.setMaxConcurrentConsumers(4);
    factory.setPrefetchCount(10);
    factory.setDefaultRequeueRejected(false);
    return factory;
}
```

`@RabbitListener(queues="orders.created.qq", containerFactory="ordersListenerFactory")` chọn factory này. Các tham số chỉ minh họa. `defaultRequeueRejected(false)` đòi hỏi DLX/handling phù hợp nếu không muốn mất message lỗi. Lỗi DB tạm thời cần retry hữu hạn/backoff, còn poison message cần quarantine có kiểm soát.

Khi node failover, nhiều delivery chưa ACK do `prefetch` có thể được broker giao lại. Prefetch quá cao tăng số message in-flight và memory, không giúp queue đạt quorum. Theo dõi `messages_unacknowledged`, consumer count, retry rate, DB transaction latency và duplicate events.

## 8. Poison message, delivery limit và DLX: lưu ý RabbitMQ 4.3

Quorum queue hỗ trợ delivery limit để chặn việc một event lỗi bị gửi đi xử lý vô hạn:

- Từ **RabbitMQ 4.0**, default delivery limit của quorum queues là **20**.
- Từ **RabbitMQ 4.3**, `delivery-count` khác cách đếm ở 4.2 về trước: `basic.nack(requeue=true)` **không làm tăng `delivery-count`**, trong khi `basic.reject` và một số lần kết thúc channel/session với delivery chưa ACK được tính là failure.
- RabbitMQ 4.3 cung cấp `x-acquired-count` để theo dõi số lần broker giao message; không dùng `x-delivery-count` thay thế số lần được giao trong mọi tình huống.
- Khi vượt delivery limit, broker có thể **drop** message nếu không có dead-letter setup hợp lệ. Cần kiểm tra DLX/DLQ và chính sách retention.
- Vì khác biệt version, không được dựa vào “`nack requeue liên tục cuối cùng sẽ tự vào DLQ ở ngưỡng 20`” trên RabbitMQ 4.3.

**Quorum queue không có nghĩa đường dead-letter mặc định at-least-once.** Quorum queues hỗ trợ chế độ **at-least-once dead-lettering** khi được cấu hình phù hợp với `dead-letter-strategy=at-least-once`, `overflow=reject-publish` và dead-letter exchange/target. Mặc định vẫn có đường dead-letter **at-most-once**, có nguy cơ mất message khi đích unavailable.

Khi bật at-least-once dead-lettering, source quorum queue giữ message đã chết chờ target xác nhận. Điều đó tăng độ an toàn nhưng cũng tăng tài nguyên và có thể làm source bị backlog/backpressure nếu DLQ mất quorum hoặc sai routing. Sau phục hồi, message ở target vẫn có thể trùng; consumer DLQ/replay cũng cần idempotency.

**Không chọn cấu hình DLQ bằng cách đoán.** Kiểm tra chính xác policy, queue type nguồn/đích, overflow và tác động nếu target bị mất majority.

## 9. Quorum membership khác với số nodes cluster

Thêm RabbitMQ node mới không mặc định làm tất cả quorum queues hiện hữu tăng replica count. Ví dụ:

```text
Cluster trước: A B C
orders.created.qq: A, B, C (3 members)

Cluster sau:   A B C D E
orders.created.qq: A, B, C (vẫn 3 members nếu chưa có reconciliation)
```

Một số RabbitMQ phiên bản hỗ trợ **Continuous Membership Reconciliation (CMR)** khi được bật/cấu hình, nhưng không nên mặc định CMR đang hoạt động hay sẽ tự thay node down tạm thời. Khi node được decommission vĩnh viễn, membership thường cần thao tác có chủ đích.

### 9.1. CLI để quan sát

```bash
# Tình trạng cluster nhìn từ node chạy lệnh:
rabbitmq-diagnostics cluster_status

# Queue leader, followers và trạng thái replica:
rabbitmq-queues quorum_status -p / orders.created.qq

# Kiểm tra nếu dừng node này sẽ làm queue/stream mất majority:
rabbitmq-diagnostics check_if_node_is_quorum_critical

# Backlog và consumer counts trong vhost:
rabbitmqctl list_queues -p / name type messages_ready messages_unacknowledged consumers
```

CLI và các trường đầu ra cần được đối chiếu với bản RabbitMQ đang dùng, quyền tài khoản, vhost và node mà CLI truy cập. Trong khi partition, **khung nhìn từ một node có thể không phải toàn bộ cluster**; nên đối chiếu logs/nhiều nodes.

### 9.2. Lệnh quản lý members: chỉ dùng với change plan

```bash
# Ví dụ thay đổi membership (KHÔNG tự chạy trên production):
rabbitmq-queues add_member -p / orders.created.qq rabbit@node-d
rabbitmq-queues delete_member -p / orders.created.qq rabbit@node-c

# Rebalance LEADERS; không thay replica membership:
rabbitmq-queues rebalance quorum
```

Các thay đổi membership là Raft state changes, cần quorum còn hoạt động để commit. Không thể “thêm một node mới” như thao tác ma thuật nếu queue đã mất toàn bộ majority. Cần chờ member mới catch up, xác nhận số online members rồi mới decommission member cũ.

**Leader rebalancing ≠ member reallocation.** Lệnh rebalance có thể phân bố lại lãnh đạo để giảm hot spots; không làm queue có thêm replica trên node khác.

### 9.3. Placement theo availability zones

Ba members đặt trên ba VMs cùng một physical host **không** chịu được host failure. Nếu muốn chịu lỗi một availability zone, cần đặt members theo các failure domains thực sự độc lập.

Một số RabbitMQ phiên bản mới hỗ trợ placement theo node tags/AZ, có thể kiểm tra thông tin với `quorum_status`. Trên Kubernetes, dùng Cluster Operator/StatefulSet, persistent volumes, pod anti-affinity/topology spread và PodDisruptionBudget phù hợp. Đừng thiết kế một cluster kéo dài qua mạng WAN có partition thường xuyên mà không cân nhắc Raft latency và data-safety tradeoffs.

## 10. Maintenance runbook: trước, trong và sau khi dừng node

Chỉ thực hiện trong change window được phê duyệt, với người vận hành có quyền và biết phương án rollback.

### 10.1. Trước khi bảo trì

1. Xác định **node mục tiêu**, cluster version, các queues business-critical và members đang online.
2. Chạy `cluster_status`, `quorum_status` và `check_if_node_is_quorum_critical` ở vị trí phù hợp.
3. Xác nhận không có follower/node khác đang offline làm một lần dừng nữa khiến queue mất majority.
4. Ghi baseline queue ready/unacked, consumer ACK rate, publisher confirm p95/p99, outbox pending age, broker disk/memory alarms.
5. Xác nhận clients có endpoint khác để reconnect; load balancer health checks và TLS/DNS phù hợp.
6. Kiểm tra backup/DR procedures và có một incident owner rõ ràng.
7. **Không tiếp tục** nếu node được báo quorum-critical hoặc queue đã degraded đến mức mất an toàn.

### 10.2. Trong khi bảo trì

- Dừng/restart **mỗi lần một node**, không rolling đồng thời khiến nhiều members cùng biến mất.
- Theo dõi leader election, connection reconnect, publisher NACK/timeout, consumer redelivery, queue backlog.
- Giữ backpressure cho outbox relay khi RabbitMQ tạm unavailable; không retry vô hạn tốc độ cao.
- Sau khi node quay lại, chờ member catch-up và redundancy phục hồi trước khi tới node kế tiếp.
- Không kết hợp xóa queue, đổi group size, cưỡng ép force-start với routine restart nếu không thuộc change plan.

### 10.3. Sau bảo trì

- Queue có leader và đủ majority/replicas như thiết kế.
- Client publisher/consumer đã reconnect và throughput đang tiến triển.
- Publisher confirms/returns bình thường, timeout và DLQ không tăng bất thường.
- Outbox/retry backlog đang giảm về mức bình thường, event IDs được đối soát với business effects.
- Có báo cáo failover duration, confirmed/unknown publish attempts, redelivery và dữ liệu cần điều tra.

**“Node up lại” không đồng nghĩa “đã phục hồi hoàn toàn”.** Một member vừa online có thể chưa bắt kịp replicated log. Cần quan sát redundancy và queue health trước lần bảo trì tiếp.

## 11. Mất quorum nghiêm trọng: nguyên tắc khôi phục

Khi mất hai trong ba members và không thể đưa một member trở lại ngay, ưu tiên **giữ nguyên dữ liệu và cô lập tác động**:

1. Xác minh tình trạng nodes, network, disks, Erlang cookie/cluster membership, logs và lịch sử sự cố.
2. Xác định member nào đã chứa queue data và có thể **khôi phục nguyên trạng**.
3. Không xóa queue/redeclare sang type khác để “đánh lừa” publisher hết lỗi.
4. Không dùng `reset`, `force_boot` hoặc `forget_cluster_node` một cách cảm tính; có thể hủy khả năng recovery hoặc làm mất dữ liệu.
5. Khôi phục đủ các members cũ khi có thể; kiểm tra họ đã catch up hay chưa.
6. Nếu đa số mất vĩnh viễn, sử dụng runbook **disaster recovery chính thức** theo broker version, backup/snapshot và các nguồn sự thật của nghiệp vụ.
7. Sau khôi phục, đối soát outbox, confirmed/unknown publisher attempts, consumer processed-event ledger, aggregate versions và business states.
8. Ghi rõ dữ liệu đã xác minh, dữ liệu outcome chưa chắc chắn và mức mất mát nếu có. Không suy từ “messages_ready=0” rằng mọi dữ liệu đã xử lý.

Quorum queue nâng mức data safety nhưng **không thay thế backup**. Khi đa số node chứa các thành viên queue bị mất vĩnh viễn, không được khẳng định mọi dữ liệu từng confirmed vẫn có thể phục hồi chỉ từ replica thiểu số.

## 12. Observability: cần theo dõi cả quorum lẫn nghiệp vụ

| Nhóm | Chỉ số/dữ liệu | Điều giải thích |
|---|---|---|
| Cluster | Reachable peers, node down, partition/election logs | Mất kết nối ở cấp node |
| Quorum queue | Leader ID, số online members, configured group size | Queue có majority không? |
| Availability | Quorum-critical nodes | Node nào không nên bảo trì tiếp |
| Publisher | ACK/NACK/return/timeout và confirm latency | Broker có xác nhận publish không? |
| Consumer | Active listeners, deliveries, ACK rates, redeliveries | Consumer có xử lý tiến triển không? |
| Queue | Ready, unacknowledged, DLQ depth | Backlog, delivery đang chờ ACK |
| Storage | Disk/memory alarm, log replication/catch-up, I/O | Replication có bị bottleneck? |
| App recovery | Spring connection recovery và listener restarts | Client có kết nối và đăng ký lại được không? |
| Business | Oldest outbox age, end-to-end event age, duplicate IDs | Mức ảnh hưởng tới người dùng/đơn hàng |

Cần đặt alerts theo **tầng**:

- **Critical:** business-critical quorum queue mất majority.
- **Warning:** 3-member queue chỉ còn 2 online — vẫn phục vụ nhưng không còn dư khả năng chịu thêm một lỗi.
- **Critical:** publisher confirm timeouts + outbox age vượt SLA.
- **Warning:** leader elections lặp lại, quorum replicas flapping hoặc network partition tái diễn.
- **Critical:** consumer ACK rate gần 0 trong khi queue ready tăng và event age tăng.
- **Warning:** DLQ/retry tăng, delivery limit loại bỏ/đẩy message đi sai policy.
- **Critical:** disk/memory alarm và storage không đủ để chịu failover/catch-up.

Đừng chỉ giám sát `rabbitmq_up` hay số nodes online. Một node khỏe có thể đứng ở minority; một quorum queue mất majority có thể không phục vụ message trong khi management vẫn mở được.

## 13. Chaos tests trong lab: chứng minh failover chứ không đoán

Các thí nghiệm chỉ dành cho **cluster test cô lập** có khả năng rollback. Không áp lệnh stop/partition lên production chỉ để “thử nghiệm”.

### 13.1. Chuẩn bị lab

Tạo A/B/C, một quorum queue ba members, exchange/binding ở mục 6. Publisher phát event IDs duy nhất từ outbox; consumer commit database idempotently. Trước khi fault injection, kiểm tra `quorum_status` thấy đủ replicas online và baseline throughput/confirm latency.

### Thí nghiệm 1 — Dừng follower

Dừng một follower trong lab, giữ leader và follower còn lại online. Xác nhận queue còn quorum 2/3 và vẫn xử lý. Quan sát redundancy giảm, confirm RTT, ACK rates; khôi phục node và xác nhận catch-up.

### Thí nghiệm 2 — Dừng leader

Dừng leader đã xác định, giữ hai followers kết nối. Quan sát bầu leader mới, khoảng dừng delivery/confirm, các lần publish timeout/NACK và redelivery. Khi queue hoạt động lại, đối soát event IDs và DB state.

### Thí nghiệm 3 — Partition A | B,C

Tạo sự chia cắt mạng ở lab, không xóa thành viên. Xác nhận phía majority có thể elect leader và tiếp tục; phía minority không được ghi theo quorum. Kết nối client tới A chưa đủ để bảo đảm queue hoạt động.

### Thí nghiệm 4 — Mất hai members

Dừng/cô lập hai members của queue trong lab. Quan sát queue unavailable, publisher outcomes UNKNOWN/NACK và consumer ngừng tiến triển. App không được làm mất outbox intent hay sinh retry storm. Đưa đủ members trở lại và đối soát.

### Thí nghiệm 5 — Mất kết nối riêng của publisher

Giữ broker cluster khỏe, cắt connection publisher tới node đang chọn. Spring reconnect endpoint khác; các publish trước khi nhận confirm có thể UNKNOWN. Retry cùng `eventId`, dùng `attemptId` mới; dedup ở consumer.

### Thí nghiệm 6 — Consumer commit trước ACK

Cho listener commit DB thành công nhưng mất connection trước broker ACK. Sau redelivery, unique marker ngăn nghiệp vụ ghi hai lần; kiểm tra ACK rates, duplicate count và queue unacked.

### Thí nghiệm 7 — Thêm node không tự tăng group size

Thêm node D, xác minh queue vẫn chỉ có members A/B/C khi không cấu hình reconcile. Học viên phân biệt cluster membership với queue membership. Nếu thực hành add member, phải có change plan và xác nhận trạng thái catch-up.

### Thí nghiệm 8 — Rolling maintenance gate

Mô phỏng follower C offline rồi muốn dừng B. `check_if_node_is_quorum_critical` hoặc checklist phải ngăn thao tác khiến queue mất majority. Sau C phục hồi, mới tiếp tục.

### Thí nghiệm 9 — DLX target unavailable

Tạo poison message, cấu hình DLX và làm target quorum queue mất majority trong lab. Quan sát chính sách at-most-once vs at-least-once dead-lettering nếu broker hỗ trợ: backpressure source, retry nội bộ và duplicate khi target hồi phục.

### Thí nghiệm 10 — Thay đổi phiên bản delivery limit

Đối chiếu hành vi requeue `basic.nack` trong RabbitMQ 4.2 so với 4.3 bằng hai môi trường lab/version docs tương ứng. Xác nhận `delivery-count` không tăng trên nack requeue ở 4.3, không phụ thuộc nhầm vào delivery limit để kết thúc loop.

**Tiêu chí đạt:** Hiểu quorum theo queue membership, quan sát được leader election/mất majority, publisher không đánh đồng timeout với thất bại chắc chắn, consumer chịu redelivery, và runbook không dừng node làm mất đa số.

## 14. Bảng chẩn đoán sự cố thực tế

| Triệu chứng | Giả thuyết cần kiểm tra | Bước kiểm chứng |
|---|---|---|
| RabbitMQ port mở nhưng publish timeout | Queue mất quorum, leader chưa được bầu, broker alarm | `quorum_status`, election logs, disk alarm |
| Một node offline, queue vẫn nhận message | Vẫn còn majority | Online members và leader state |
| Mất leader, delivery dừng ngắn | Đang elect leader | Logs, leader changes, confirm latency |
| Confirm có nhưng consumer ghi trùng | ACK consumer cũ bị mất, redelivery | Processed-event ledger, redelivered |
| Cluster còn 3/5 nodes nhưng queue không phục vụ | Hai trong ba queue members đã down | Member placement và quorum status |
| App reconnect được nhưng vẫn lỗi message | Quorum queue không khả dụng | Per-queue quorum, không chỉ TCP |
| Outbox backlog lớn trong outage | Relay thiếu confirm, backpressure/retry | Confirm timeouts, pending age |
| Thêm node mới nhưng queue không an toàn hơn | Chưa mở rộng membership | CMR/member group size |
| DLQ tăng sau reconnect | Redelivery/poison handling | Delivery-count version, retry policy |
| Node online lại nhưng readiness vẫn xấu | Member catch-up hoặc metadata/resource chưa ổn | Replica state, I/O, alarms |

**Không tăng `concurrentConsumers` làm “sửa lỗi mất quorum”.** Concurrency chỉ tác động throughput khi queue đã phục vụ bình thường; không làm Raft đạt đa số.

## 15. Checklist production trước go-live

- [ ] Cluster và quorum queue members được phân bố theo failure domains/AZ phù hợp RPO/RTO.
- [ ] Kiểm tra queue thực tế có kiểu `quorum`, leader và đúng số online members.
- [ ] Publisher có correlated confirms, returns và chiến lược xử lý UNKNOWN.
- [ ] Event intent quan trọng có transactional outbox/durable store.
- [ ] Consumer idempotent trong DB transaction, có event ID ổn định qua retries.
- [ ] Retry, poison message, delivery limit và DLX đúng với RabbitMQ version.
- [ ] Không giả định quorum DLX mặc định at-least-once.
- [ ] Spring app có cluster endpoints/load balancer và reconnect policy phù hợp.
- [ ] Monitoring phân biệt node health, queue quorum, publisher confirms, consumer ACK và business lag.
- [ ] Runbook có `cluster_status`, `quorum_status` và `check_if_node_is_quorum_critical`.
- [ ] Rolling upgrades không khiến thêm node khác bị dừng khi redundancy chưa phục hồi.
- [ ] Đã kiểm thử mất leader, mất follower, network partition, client reconnect và ACK loss.
- [ ] Có backup/DR và quy trình đối soát sự kiện sau outage.

## 16. Các ngộ nhận thường gặp

- **“Cluster ba node nghĩa là mọi queue có ba replicas.”** Không; phải kiểm tra queue type/membership.
- **“Chỉ cần 3/5 nodes online thì tất cả queues sống.”** Không; quorum của **một queue** dựa trên members của nó.
- **“Mất leader thì message đã confirm đều mất.”** Không; majority còn lại có thể bầu leader và phục hồi.
- **“Queue leader thay đổi mà publisher/consumer không bao giờ thấy gián đoạn.”** Có thể có election, confirm delay và redelivery.
- **“Kết nối được vào node nghĩa là publish chắc chắn thành công.”** Không; queue có thể ở minority hoặc unavailable.
- **“Publisher confirm ACK chứng minh consumer đã commit.”** Không; producer confirm khác consumer ACK.
- **“Timeout nghĩa là broker chưa lưu message.”** Không; outcome unknown, cần idempotency.
- **“Quorum queue đảm bảo exactly-once.”** Không; delivery có thể lặp.
- **“Thêm node D tự sao chép mọi queue sang D.”** Không mặc định; cần membership management/CMR.
- **“Rebalance leader chính là thêm replica.”** Không; leader placement khác member set.
- **“Dead-letter từ quorum queue mặc định at-least-once.”** Không; phụ thuộc policy.
- **“Delivery limit 4.3 hoạt động giống 4.2 cho basic.nack.”** Không; phải đọc docs version.
- **“Mất quorum cứ reset/delete queue để phục hồi nhanh.”** Có thể phá dữ liệu; phải theo runbook chính thức.

## 17. Câu hỏi tự kiểm tra

1. Cluster membership khác quorum queue membership ở điểm nào?
2. Với queue có 3 members cần bao nhiêu members để đạt quorum? Queue 5 members thì sao?
3. Cluster 5 nodes vẫn có thể có queue unavailable khi 3 nodes còn online như thế nào?
4. Mất follower khác mất leader ở tác động tức thời ra sao?
5. Khi A bị cô lập khỏi B/C, phe nào có thể tiếp tục với queue A/B/C?
6. Publisher confirm ACK và consumer ACK thể hiện hai bước nào?
7. Vì sao một event đã DB commit vẫn có thể redeliver khi node leader failover?
8. `spring.rabbitmq.addresses` hỗ trợ điều gì nhưng không thể giải quyết được mất quorum nào?
9. Thêm node mới vào cluster có tự tạo replica mới cho mọi queue không?
10. Check nào nên chạy trước khi dừng node cho rolling maintenance?
11. Tại sao không nên dựa vào `basic.nack(requeue=true)` để kích hoạt delivery limit trên RabbitMQ 4.3?
12. At-least-once dead-lettering có thể làm source queue chịu backpressure khi nào?
13. Nếu mất quorum vĩnh viễn, tại sao cần DR/backup thay vì tự redeclare queue?
14. Tại sao publisher confirms vẫn cần đi kèm outbox và consumer idempotency?
15. Những metrics nào giúp phân biệt lỗi cluster, queue quorum và business processing?

**Đáp án gợi ý:** (1) Cluster nodes và thành viên replicas của một queue khác nhau. (2) 2/3, 3/5. (3) Hai trong ba members của queue có thể down. (4) Mất leader cần election, mất follower vẫn có thể hoạt động nếu quorum. (5) B/C majority. (6) Broker xác nhận publish; consumer xác nhận delivery. (7) ACK consumer chưa được broker ghi nhận. (8) Reconnect tới node khác, không tạo majority cho queue. (9) Không mặc định. (10) `check_if_node_is_quorum_critical` và `quorum_status`. (11) Không tăng `delivery-count` như trước. (12) Target không confirm/routing sai, source giữ dead letters. (13) Có thể mất dữ liệu và chỉ có recovery có kiểm soát mới bảo toàn bằng chứng. (14) Unknown publish và duplicate redelivery. (15) Members/leader, confirms, ACK rates, queue depth, outbox age.

## 18. Tổng kết

**RabbitMQ cluster** giúp phối hợp nhiều nodes, nhưng độ sẵn sàng của một luồng message quan trọng phụ thuộc vào **queue type và số member thật sự của quorum queue**. Với ba members, queue cần hai nodes đạt đa số; khi follower mất, redundancy giảm; khi leader mất nhưng majority còn, queue có thể elect leader mới; khi mất majority, queue ngừng tiến triển dù một node nào đó vẫn chạy.

Phía **Spring AMQP**, cần cấu hình endpoints phù hợp, correlated publisher confirms/returns, retry an toàn khi outcome UNKNOWN, outbox để không mất ý định publish và consumer idempotent để chịu redelivery. Phía vận hành, phải kiểm tra `quorum_status`, quorum-critical nodes, leader election, queue ready/unacked, confirm latency, disk/network và business event age; không bảo trì thêm node khi vừa đủ majority.

**HA không phải chỉ là “ba RabbitMQ processes còn sống”, mà là queue thật sự có quorum, ứng dụng xử lý đúng ACK/timeout, và dữ liệu có thể được đối soát sau sự cố.**

### Tài liệu tham khảo

- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): Raft, members, majority, publisher confirms, delivery limit, dead-lettering và membership.
- [RabbitMQ — Clustering Guide](https://www.rabbitmq.com/docs/clustering): node counts, khách hàng kết nối và failover.
- [RabbitMQ — Clustering and Network Partitions](https://www.rabbitmq.com/docs/partitions): leader election, majority/minority, lưu ý RabbitMQ 4.3.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-lettering safety và chính sách.
- [RabbitMQ — Cluster Formation](https://www.rabbitmq.com/docs/cluster-formation): peer discovery, Kubernetes.
- [RabbitMQ — Quorum Status Monitoring](https://www.rabbitmq.com/kubernetes/operator/quorum-status): quorum-critical nodes và vận hành rolling.
- [Spring AMQP — Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): `CachingConnectionFactory` và recovery.
- [Spring AMQP — RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html): correlated confirms, returns và publish reliability.

