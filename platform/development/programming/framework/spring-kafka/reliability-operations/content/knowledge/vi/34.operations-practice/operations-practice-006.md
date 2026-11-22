# Mô phỏng broker mất kết nối trong Spring Kafka

## 1. Mục tiêu của bài thực hành

Trong môi trường production, một ứng dụng Spring Kafka có thể mất kết nối tới broker trong lúc gửi hoặc nhận message. Nguyên nhân có thể là broker được restart, mạng giữa Pod và Kafka gặp sự cố, DNS/route sai, load balancer đóng kết nối, một broker leader chết hoặc một phần cluster bị cô lập. Kafka client có cơ chế reconnect/retry, nhưng **khả năng tự kết nối lại không đồng nghĩa mọi thông điệp đã được xử lý chính xác một lần và không có trường hợp kết quả chưa rõ ràng**.

Ví dụ service `payment-events` nhận message `eventId=evt-103`, cập nhật bảng nghiệp vụ và chuẩn bị commit Kafka offset. Ngay sau khi database commit, kết nối broker bị ngắt. Khi kết nối phục hồi, consumer khác có thể đọc lại chính event đó nếu offset chưa được commit thành công. Nếu không thiết kế idempotency, một sự cố kết nối ngắn có thể tạo xử lý trùng.

```text
Producer app                       Kafka cluster                 Consumer app
     |                                   |                             |
     |--- send(eventId=evt-103) -------->|                             |
     |<-- ACK hoặc kết quả chưa rõ ------|--- poll(event) ------------>|
     |                                   |                             |-- DB commit
     |                     [MẤT KẾT NỐI BROKER]                       X-- offset commit?
     |                                   |                             |
     |                   [KẾT NỐI ĐƯỢC KHÔI PHỤC]                    |
     |                                   |--- possible redelivery ---->|
     |                                   |                             |-- kiểm tra idempotency
```

Bài thực hành này hướng tới sáu kết quả cụ thể:

1. **Tạo được sự cố có kiểm soát**: dừng một broker local hoặc cắt đường mạng client qua proxy trong môi trường test.
2. **Nhìn thấy phản ứng producer**: reconnect, retry, future hoàn tất thành công/thất bại hoặc hết deadline.
3. **Nhìn thấy phản ứng consumer**: polling, group rebalancing, pause trong kết nối lỗi và khả năng tiêu thụ lại sau phục hồi.
4. **Đánh giá durability/offset**: phân biệt broker đã lưu record, producer đã nhận ACK, consumer đã hoàn thành nghiệp vụ và offset đã commit.
5. **Kiểm chứng kết quả nghiệp vụ**: không bỏ sót event đã xác nhận và không tạo side effect trùng ngoài dự kiến.
6. **Viết runbook vận hành**: biết khi nào chờ tự hồi phục, khi nào xử lý configuration/ACL và khi nào cần can thiệp hệ thống.

**Giới hạn an toàn:** các lệnh stop/kill/cắt mạng trong bài **chỉ dành cho Kafka test cô lập, container/local cluster hoặc môi trường chaos testing đã được cho phép**. Không chạy trên Kafka production, cluster dùng chung hay máy có dịch vụ ngoài phạm vi bài thực hành.

## 2. Không phải mọi trường hợp “mất broker” đều giống nhau

| Kịch bản | Broker có thật sự chết? | Hành vi có thể xảy ra |
|---|---|---|
| Docker container broker dừng | Có, process broker dừng. | Client thử reconnect, leader/coordinator có thể biến mất. |
| Chỉ đường mạng từ **một ứng dụng** tới Kafka bị cắt | Không; broker vẫn phục vụ client khác. | Chỉ client đó không truy cập được; các group members khác có thể tiếp tục. |
| Một broker trong cluster ba node chết | Có, một node dừng. | Partitions có replica đủ điều kiện có thể có leader mới; client chuyển sang broker khác. |
| Toàn bộ broker nodes không thể truy cập | Cluster không khả dụng từ góc nhìn client. | Produce/poll/commit bị trì hoãn hoặc lỗi theo deadline. |
| Broker còn sống nhưng `advertised.listeners` sai | Không. | Bootstrap có thể thành công rồi client nhận endpoint không kết nối được. |
| DNS không resolve được broker hostname | Không nhất thiết. | Client không tới được host/không tạo kết nối mới theo DNS policy. |
| ACL hoặc credentials không hợp lệ | Không. | Authentication/authorization error, có thể là lỗi fatal thay vì transient network. |
| Consumer không có message mới | Không. | Idle bình thường; không chứng minh Kafka down. |

**Phân biệt ba lớp cần kiểm chứng:** (1) broker process/cluster health; (2) đường kết nối tới đúng broker từ **network namespace của client**; (3) tính đúng đắn của business processing và offset sau khôi phục. Test chỉ kiểm tra `ping`/TCP port mở không xác nhận hoàn chỉnh ba lớp này.

### 2.1. Một broker khác một Kafka cluster có replication

Trong lab một broker với replication factor bằng 1, tắt broker gần như làm toàn bộ topic không khả dụng. Trong cluster ba broker với topic `replication.factor=3`, tắt một node có thể chỉ gây leader election ngắn nếu các replicas còn lại đủ điều kiện. Vì vậy:

- Lab **một broker** phù hợp để học producer timeout, client reconnect và recovery sau outage toàn broker.
- Lab **nhiều brokers** mới kiểm tra được failover leader, in-sync replicas (ISR), `acks=all`, `min.insync.replicas` và phản ứng mất một phần cluster.
- Lab **cắt mạng theo client** phù hợp để xem một service bị cô lập trong khi broker vẫn hoạt động, nhất là với Toxiproxy hoặc proxy mạng tương đương.

Không được diễn giải test thành công với một broker là bằng chứng production cluster có khả năng chịu mất một node, và ngược lại.

## 3. Hiểu `bootstrap.servers` và `advertised.listeners` trước khi gây lỗi

Kafka client dùng `bootstrap.servers` để kết nối ban đầu và lấy **cluster metadata**. Sau đó producer/consumer kết nối tới các broker leader/coordinator dựa trên địa chỉ mà broker công bố trong `advertised.listeners`.

```text
Spring Kafka app
  bootstrap.servers = broker-a:9092,broker-b:9092
                |
                v
         Bootstrap broker
                |
          Metadata response:
            node 1 = kafka-a:9092
            node 2 = kafka-b:9092
            node 3 = kafka-c:9092
                |
                v
     Client mở kết nối theo các địa chỉ đã advertise
```

Những hệ quả quan trọng cho bài thực hành:

- Nếu chỉ đưa **cổng bootstrap** qua proxy nhưng broker lại advertise địa chỉ Kafka **đi thẳng**, client có thể bỏ qua proxy sau metadata lookup. Test cắt mạng sẽ cho kết quả giả.
- Khi dùng Docker, hostname `kafka:9092` chỉ resolve trong Docker network phù hợp; ứng dụng trên host Windows/Linux có thể cần `localhost:<mapped-port>` hoặc advertised endpoint khác.
- Đưa nhiều bootstrap servers giúp client có nhiều điểm vào cluster, **không làm broker topic tự có replication** và không bảo đảm failover khi leaders/ISR không đủ.
- `bootstrap.servers` không cần liệt kê mọi broker, nhưng trong production nên có nhiều endpoints hợp lệ để tránh phụ thuộc một bootstrap host.

**Điều kiện test mạng thật:** tất cả đường kết nối Kafka mà client có thể sử dụng trong phạm vi thí nghiệm phải đi qua điểm gây lỗi. Hãy kiểm tra bootstrap, advertised endpoints, leader/coordinator addresses và các đường kết nối dự phòng, không chỉ thấy một socket bị đóng rồi kết luận toàn Kafka unreachable.

## 4. Chuẩn bị môi trường thí nghiệm có thể lặp lại

### 4.1. Phạm vi tối thiểu

Một cấu hình gọn gồm:

| Thành phần | Cấu hình gợi ý | Mục đích |
|---|---|---|
| Kafka broker local | Một container Apache Kafka 3.9.1 chạy trên Docker | Thực hành outage đơn broker. |
| Spring Boot app | Java 17+, Spring Boot 3.x, Spring Kafka 3.x | Producer, listener và quan sát client. |
| Topic | `orders.outage.lab`, một partition, replication factor 1 | Dễ quan sát offset và thứ tự. |
| Consumer group | `outage-lab-workers` | Giữ offset qua restart process nếu broker storage còn. |
| Business store | Database test có unique `eventId` hoặc fake idempotent store | Kiểm tra duplicate effects. |
| Monitoring | Logs có timestamp, counters, Kafka client/consumer metrics | So sánh trước, trong và sau outage. |

Không dùng lại topic/group đang phục vụ job production. Với CI hoặc nhóm nhiều người dùng cùng máy, chọn tên topic và group riêng cho từng test run để tránh offset từ test khác.

### 4.2. Chạy broker local bằng Docker

Theo hướng dẫn Docker của Apache Kafka 3.9.x, image JVM chính thức có thể khởi chạy local bằng cấu hình mặc định. Trong môi trường shell hỗ trợ Docker:

```bash
docker run -d --name kafka-outage-lab \
  -p 9092:9092 \
  apache/kafka:3.9.1

docker ps --filter name=kafka-outage-lab
docker logs --tail=100 kafka-outage-lab
```

Đây là **broker phục vụ local lab**; nếu port 9092 đang có dịch vụ khác, phải đổi/chuẩn hóa cả listener mapping theo cách image hỗ trợ, không chỉ đổi host port rồi tin metadata vẫn đúng. Với Docker Desktop hoặc hệ điều hành khác, kiểm tra địa chỉ bootstrap thực tế mà Spring app sử dụng.

Tạo topic bằng CLI nằm trong container image:

```bash
docker exec kafka-outage-lab /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders.outage.lab \
  --partitions 1 \
  --replication-factor 1

docker exec kafka-outage-lab /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic orders.outage.lab
```

CLI path `/opt/kafka/bin` minh họa layout của Apache Kafka image; nếu dùng image khác, xác nhận lại vị trí binaries. Thực hiện producer/consumer qua **Spring Boot process chạy bên ngoài broker container**; nếu đặt test client bên trong chính container rồi stop broker container, client cũng chết và không quan sát được reconnect.

### 4.3. Lưu dữ liệu và cleanup

`docker stop`/`docker start` **cùng một container** thường giữ writable layer và các volumes đã gắn, nên phù hợp thử phục hồi ngắn. Nhưng `docker rm`, `docker compose down -v` hoặc tạo container mới mà không giữ data volume có thể **làm mất logs và committed offsets**. Nếu muốn test persistence qua việc tạo lại broker process/container, phải dùng volume phù hợp và cùng metadata cluster/KRaft configuration.

Khi xong lab:

```bash
docker stop kafka-outage-lab
docker rm kafka-outage-lab
```

Chỉ chạy cleanup này khi chắc chắn container `kafka-outage-lab` là container thử nghiệm vừa tạo, không chứa dữ liệu cần giữ. Không dùng wildcard/xóa Docker volumes của môi trường chia sẻ.

## 5. Spring Boot cấu hình producer và consumer để dễ quan sát

Ví dụ `src/main/resources/application-lab.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 15000
        request.timeout.ms: 3000
        max.block.ms: 5000
        retry.backoff.ms: 200
        reconnect.backoff.ms: 200

    consumer:
      group-id: outage-lab-workers
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        session.timeout.ms: 10000
        max.poll.interval.ms: 300000

    listener:
      ack-mode: record
      idle-event-interval: 10s

logging:
  level:
    root: INFO
    org.apache.kafka.clients.NetworkClient: WARN
    org.springframework.kafka: INFO
```

Các timeout nhỏ nhằm cho test nhanh; **không copy nguyên vào production**. `delivery.timeout.ms` cần lớn hơn hoặc bằng `request.timeout.ms + linger.ms` và đủ cho outage mà ứng dụng dự kiến chịu đựng. Nếu giảm quá thấp, một sự cố mạng ngắn có thể làm producer fail ngay dù broker sớm khôi phục.

Spring Boot chỉ nạp file `application-lab.yml` khi profile `lab` được kích hoạt (`spring.profiles.active=lab` hoặc tham số tương ứng). Với consumer group và offset, `auto-offset-reset=earliest` chỉ áp dụng khi không có committed offset hợp lệ; nó không bắt một group đang có offset đọc lại từ đầu.

**Cảnh báo bảo mật:** cấu hình chỉ dùng PLAINTEXT và String serializers trong lab. Với Kafka dùng SASL/TLS, secrets/keystore phải nằm trong hệ thống secret management tương ứng. Không tắt TLS verification hoặc log credentials để “chữa” lỗi kết nối.

### 5.1. Producer với tín hiệu thành công/thất bại rõ ràng

Spring Kafka 3.x trả về `CompletableFuture<SendResult<K,V>>` từ `KafkaTemplate.send(...)`:

```java
import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OutageLabProducer {

    private static final Logger log =
            LoggerFactory.getLogger(OutageLabProducer.class);

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OutageLabProducer(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String eventId, String payload) {

        CompletableFuture<SendResult<String, String>> send =
                kafkaTemplate.send("orders.outage.lab", eventId, payload);

        send.whenComplete((result, error) -> {
            if (error != null) {
                log.warn("kafka.produce.failed eventId={} errorType={}",
                        eventId, error.getClass().getSimpleName());
            } else {
                log.info("kafka.produce.acked eventId={} partition={} offset={}",
                        eventId,
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset());
            }
        });

        return send;
    }
}
```

Phải lưu ý hai tầng kết quả:

- `KafkaTemplate.send(...)` có thể block/throw **trước khi trả future** khi chờ metadata/buffer hoặc lỗi cấu hình; `max.block.ms` giới hạn một số trường hợp đó.
- Khi đã có future, kết quả **asynchronous** phụ thuộc producer ACK/retry/delivery timeout. `.whenComplete(...)` cho phép quan sát outcome. Chỉ gọi `send()` không chứng minh record đã tới broker.
- Khi client code gọi `future.get(3, TimeUnit.SECONDS)` và nhận `TimeoutException`, đây chỉ là **hết thời gian chờ của caller**; producer future có thể tiếp tục thực hiện hoặc hoàn tất về sau. Không được coi mọi caller timeout là Kafka chắc chắn không ghi record.
- Producer nhận exception sau timeout vẫn có tình huống **ACK/result ambiguous** ở biên mạng. Nếu ứng dụng retry ở tầng business, phải dùng event ID ổn định và downstream idempotency.

### 5.2. Consumer xử lý nghiệp vụ trước khi ACK

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OutageLabConsumer {

    private final IdempotentOrderService orderService;

    public OutageLabConsumer(IdempotentOrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "outageLabConsumer",
            topics = "orders.outage.lab",
            groupId = "outage-lab-workers")
    public void consume(ConsumerRecord<String, String> record) {
        String eventId = record.key();

        // Method này phải commit nghiệp vụ trước khi trả về.
        orderService.applyOnce(eventId, record.value());

        // AckMode.RECORD: container xử lý commit offset sau callback.
    }
}
```

`IdempotentOrderService` là thành phần ứng dụng tự xây dựng, không phải class có sẵn của Spring Kafka. Ví dụ với PostgreSQL, có thể dùng unique constraint trên `event_id`, lưu marker và business update **trong cùng transaction**; nếu marker đã tồn tại thì bỏ qua side effect trùng theo business rule.

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trong cùng transaction với business update:
INSERT INTO processed_event (event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;
```

Service phải kiểm tra insert có tạo row mới hay không. Chỉ thêm unique marker rồi vẫn luôn cập nhật số dư là **không idempotent**. Nếu payload của cùng event ID khác nhau, cần chính sách phát hiện mâu thuẫn chứ không tự nuốt.

## 6. Producer sẽ làm gì khi broker mất kết nối?

Kafka producer có metadata, buffer, request retry/backoff và giới hạn delivery. Nó thường thử kết nối lại khi gặp lỗi mạng có thể phục hồi; nhưng tùy khoảng outage và các deadline, một số `send` có thể thất bại.

| Property | Tác động | Không được hiểu sai |
|---|---|---|
| `bootstrap.servers` | Các endpoint để client khởi tạo thông tin cluster. | Không phải danh sách broker duy nhất mà producer sử dụng suốt đời. |
| `acks=all` | Yêu cầu ACK theo điều kiện ISR/durability của topic. | Không tự bảo đảm side effect ở consumer exactly-once. |
| `enable.idempotence=true` | Chống duplicate do **retries nội bộ của cùng producer session** trong phạm vi producer protocol. | Không loại bỏ duplicate do ứng dụng tự gọi `send()` lần nữa với cùng business event. |
| `delivery.timeout.ms` | Deadline tổng thể để producer báo thành công/thất bại cho một record sau khi send được chấp nhận. | Không giống timeout của `future.get()`. |
| `request.timeout.ms` | Thời gian đợi response của một request; có thể retry nếu phù hợp. | Không phải deadline tổng của mọi retries. |
| `max.block.ms` | Giới hạn chờ metadata/buffer trong `send()` và một số API producer đồng bộ. | Không giới hạn thời gian callback nghiệp vụ. |
| `reconnect.backoff.ms` | Trì hoãn giữa các nỗ lực tạo kết nối lại. | Không bảo đảm lập tức có kết nối khi broker khởi động. |
| `retry.backoff.ms` | Trì hoãn giữa requests có thể retry. | Không thay thế `delivery.timeout.ms`/giới hạn nghiệp vụ. |
| `max.in.flight.requests.per.connection` | Số requests chưa ACK trên một connection. | Với idempotence, cần tuân thủ ràng buộc client; cấu hình sai có thể gây lỗi hoặc đổi ordering. |

### 6.1. Timeline minh họa

```text
T+0s:  producer.send(event-1) -> ACK thành công
T+2s:  mất kết nối tới broker
T+3s:  producer.send(event-2) -> được buffer hoặc chờ metadata
T+4s:  Kafka client bắt đầu reconnect/retry
T+18s: event-2 hết delivery timeout (ví dụ 15 giây từ lúc send)
        -> future hoàn tất exceptionally
T+20s: broker có kết nối lại
T+21s: producer.send(event-3) -> có thể ACK thành công
```

Timeline chỉ minh họa, thời điểm thực phụ thuộc metadata, batch queue, network, broker startup và client config. Đặc biệt, **không thể suy ra event-2 chắc chắn không tồn tại trong Kafka** chỉ vì caller nhận timeout: nếu ACK bị mất sau khi broker đã ghi, kết quả phía producer có thể không rõ ràng.

### 6.2. Retry ở Kafka client và retry ở tầng ứng dụng

Trong Kafka client, retries nội bộ cùng với idempotent producer được thiết kế để tránh duplicate do resend batch khi có lỗi transient. Nhưng nếu ứng dụng bắt exception rồi gọi `publish(eventId, payload)` lần nữa bằng một producer operation mới, đó là **một lần gửi nghiệp vụ riêng** và có thể tạo record mới trong topic.

Vì vậy, đối với sự kiện quan trọng:

- Gắn **business event ID bất biến** vào key/header/payload.
- Ghi nhận trạng thái publish ở outbox hoặc hệ thống điều phối bền, không chỉ ở RAM.
- Cho phép consumer xử lý lại cùng event ID an toàn.
- Khi cần reconciliation, kiểm tra kết quả ở hệ thống đích thay vì suy đoán từ callback timeout.

## 7. Consumer sẽ làm gì khi mất broker?

Một `@KafkaListener` chạy trên Spring Kafka container, dùng Kafka client `poll()` để lấy records. Khi kết nối broker bị cắt, consumer có thể log lỗi connection và thử kết nối lại, tiếp tục poll hoặc tham gia lại group khi broker có mặt. Nhưng **không có một callback duy nhất luôn được phát ngay lúc broker mất kết nối**.

Những thành phần liên quan:

| Thành phần | Vai trò khi outage |
|---|---|
| `KafkaConsumer.poll()` | Vòng lấy dữ liệu và duy trì group; phản ứng tùy kết nối/metadata. |
| Group coordinator | Quản lý membership và committed offsets; có thể chuyển coordinator nếu node mất. |
| Partition leader | Broker xử lý read/fetch cho partition; leader chết có thể cần election. |
| `session.timeout.ms` | Thời gian group có thể coi một member mất heartbeat trong các điều kiện áp dụng. |
| `max.poll.interval.ms` | Kiểm soát khoảng tối đa giữa lần poll; xử lý business quá lâu cũng có thể gây rebalance. |
| `enable.auto.commit` và `AckMode` | Quyết định khi nào offset được xác nhận. |
| `DefaultErrorHandler` | Xử lý exceptions của listener/record theo policy, không phải cơ chế chuyên biệt xử lý mọi lỗi kết nối broker. |
| `KafkaListenerEndpointRegistry` | Xem/điều khiển trạng thái listener containers. |

### 7.1. Khi kết nối phục hồi, consumer đọc lại từ đâu?

Consumer tiếp tục dựa trên trạng thái assignment, position và **committed offset**; nếu mất group membership hoặc phải khởi tạo lại consumer, nó có thể bắt đầu lại từ offset đã commit hợp lệ. Điều này tạo *at-least-once*: một record đã gây side effect nhưng offset commit thất bại có thể được giao lại.

```text
offset 40: business DB đã xử lý, Kafka committed offset = 41
offset 41: business DB đã xử lý, offset commit 42 chưa thành công
                      |
                 broker outage
                      |
           consumer group phục hồi
                      |
           có thể redeliver offset 41
```

Không lấy số lần `@KafkaListener` được gọi làm số business events duy nhất. So sánh **tập event IDs** đã được xác nhận ở nguồn với bảng output/marker idempotency, đồng thời kiểm tra lag/committed offsets trong môi trường test.

### 7.2. Đừng nhầm idle với mất broker

Spring Kafka có thể phát `ListenerContainerIdleEvent` nếu bật `idleEventInterval` và không nhận records. Nhưng **topic rỗng hợp lệ cũng tạo idle event**. `NonResponsiveConsumerEvent` là tín hiệu khác: `poll()` có vẻ không quay lại theo monitor threshold, không phải tiêu chuẩn chung để phát hiện mọi outage.

Một broker mất mạng **không nhất thiết khiến container phát `ConsumerStoppedEvent`**. Consumer có thể tiếp tục chạy và reconnect; `ConsumerStoppedEvent` thường liên quan container thực sự dừng hoặc các lý do stop khác. Vì vậy không thể dùng một event Spring duy nhất làm cơ chế health hoàn chỉnh.

### 7.3. Authentication/authorization khác network lỗi

`AuthenticationException` và `AuthorizationException` thường cần điều tra secret, ACL, certificate và policy; mặc định có thể khiến container dừng nếu không bật cơ chế retry auth phù hợp. Spring Kafka có property `authExceptionRetryInterval` dành cho trường hợp xác thực/phân quyền có thể được sửa trong lúc container sống, **không phải cấu hình tự động giải quyết network outage**.

Đừng tăng retry vô hạn cho credentials sai hoặc tắt TLS validation để nhìn thấy consumer reconnect. Phải phân loại lỗi ở logs và kiểm tra endpoint/ACL thật.

## 8. Bài thực hành A — dừng broker local rồi khởi động lại

Đây là kịch bản đơn giản nhất để quan sát outage **toàn broker** khi dùng lab một node.

### 8.1. Trước khi gây lỗi

1. Khởi động container `kafka-outage-lab` và tạo topic theo mục 4.
2. Khởi động Spring Boot app với profile `lab` (client phải chạy bên ngoài broker container).
3. Gửi message `eventId=before-001`, chờ producer future ACK thành công.
4. Chờ consumer xử lý và xác minh business marker `before-001` chỉ được tạo một lần.
5. Ghi lại Kafka client metrics, consumer group lag, logs thời điểm và đường bootstrap đang dùng.

### 8.2. Gây outage

Trong terminal quản lý **container test**:

```bash
# Dừng broker bằng đường shutdown thông thường:
docker stop kafka-outage-lab

docker ps -a --filter name=kafka-outage-lab
```

`docker stop` gửi tín hiệu dừng và có deadline trước khi kill nếu process không thoát. Nếu cần mô phỏng **broker crash đột ngột** trong một bài riêng, dùng:

```bash
# CHỈ container thí nghiệm; khác với graceful stop:
docker kill kafka-outage-lab
```

Không cần chạy cả hai lệnh nối tiếp để mô phỏng cùng một sự cố. Nếu container đã được `docker stop`, `docker kill` không có thêm ý nghĩa. Broker crash có thể cho thời gian leader/coordinator recovery khác graceful shutdown; chọn kịch bản nào phải ghi rõ trong kết quả test.

### 8.3. Quan sát producer và consumer trong outage

Trong lúc container dừng:

- Gọi `publish("during-001", payload)` từ Spring app và quan sát thời điểm future hoàn tất hoặc timeout.
- Kiểm tra exception class/logs; phân biệt `TimeoutException` phía caller với future hoàn tất exceptionally do producer.
- Quan sát consumer vẫn running hay đã dừng, có warnings về connection/node, group assignment và offset commit hay không.
- Không suy ra số records bị mất chỉ vì thiếu ACK; kiểm tra lại sau khi broker phục hồi.
- Nếu `KafkaTemplate.send(...)` block ở metadata/buffer, quan sát `max.block.ms` và thread pool thay vì tạo vô hạn parallel send requests.

**Không bắt buộc mọi send thất bại ngay** tại thời điểm broker dừng; producer có buffer/retries và timeout. Kỳ vọng hợp lý cho outage dài hơn delivery deadline là có các sends kết thúc thất bại, nhưng lỗi cụ thể phụ thuộc thời điểm và cấu hình.

### 8.4. Phục hồi và đối soát

```bash
docker start kafka-outage-lab
docker ps --filter name=kafka-outage-lab
docker logs --tail=100 kafka-outage-lab
```

Sau khi broker báo sẵn sàng:

1. Chờ producer gửi **một message mới** `after-001` và nhận ACK.
2. Chờ consumer đọc `after-001` và business store xác nhận xử lý xong.
3. Kiểm tra `during-001`: nó có thể thất bại rõ ràng, được ghi thành công trước/đúng lúc outage hoặc rơi vào trạng thái chưa rõ từ phía ứng dụng. Đối soát bằng event ID và business protocol.
4. Xem consumer committed offset có tiến lên sau processing không; nếu consumer group bị rebalanced, ghi nhận thời gian.
5. Quan sát lag có quay về baseline trong thời gian phù hợp không.

**Tuyên bố hoàn tất bài lab:** producer đã gửi thành công message sau recovery, consumer đã tiếp tục xử lý, output không thiếu các event đã được xác nhận theo hợp đồng và không có business side effect trùng. Việc logs hết cảnh báo reconnect chỉ là dấu hiệu hỗ trợ, không phải assertion cuối duy nhất.

## 9. Bài thực hành B — chỉ cắt mạng client bằng Toxiproxy

Trong lab A, broker thực sự chết. Nhưng production cũng có tình huống **broker vẫn hoạt động, chỉ một ứng dụng bị mất kết nối** do firewall, route, sidecar hoặc network partition. Để tái hiện có kiểm soát, có thể dùng Toxiproxy làm trung gian TCP giữa ứng dụng và Kafka.

```text
Spring Boot client
    |
    | bootstrap + mọi broker connections trong phạm vi test
    v
Toxiproxy (port TCP có thể cắt/độ trễ)
    |
    v
Kafka broker trong Docker network

T+0: proxy hoạt động => producer/consumer bình thường
T+1: cắt upstream và downstream => client không thấy Kafka
T+2: producer timeout / consumer reconnect
T+3: khôi phục proxy => client kết nối lại
```

Ưu điểm so với `docker stop`:

- Broker vẫn sống, log và state cluster không bị dừng.
- Có thể cắt riêng đường mạng của producer A, consumer B hoặc một subset clients.
- Mô phỏng được latency, jitter, timeout, packet fragmentation hoặc bandwidth giới hạn.
- Có thể khôi phục ngay bằng cách gỡ toxics mà không mất thời gian broker boot.

### 9.1. Điều kiện quan trọng nhất: Kafka `advertised.listeners`

Kafka không sử dụng bootstrap server làm đích duy nhất. Nếu app bootstrap qua `toxiproxy:8666` nhưng broker advertise `broker:9092` và app kết nối được trực tiếp tới `broker:9092`, test **không còn cắt được toàn bộ Kafka traffic**.

```text
Sai:
  client -> proxy -> broker bootstrap
  client <- metadata broker=broker:9092
  client -----------------> broker:9092 (đi vòng proxy)

Đúng:
  client -> proxy -> broker bootstrap
  client <- metadata broker=proxy-address
  client -> proxy -> broker leader/coordinator
```

Do đó, dùng một listener riêng trên broker với **advertised endpoint trỏ về proxy** cho test clients. Trong cluster nhiều broker, phải định tuyến/kiểm soát **từng advertised broker endpoint** cần thử, không chỉ một proxy TCP rồi giả định đã cắt toàn group.

### 9.2. Dependencies cho Spring Boot integration test

Ví dụ Gradle Groovy, dùng BOM của Spring Boot và Testcontainers tương thích với project:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers-kafka'
    testImplementation 'org.testcontainers:testcontainers-toxiproxy'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Artifact names, package namespaces và overloads của Testcontainers thay đổi theo major version. Ví dụ phần tiếp dùng API Testcontainers hỗ trợ `org.testcontainers.kafka.KafkaContainer.withListener(listener, advertisedListenerSupplier)` và `ToxiproxyContainer`. Cần **đồng bộ tất cả module Testcontainers theo cùng BOM/version**, đồng thời đối chiếu `withListener` với version đang chạy; không trộn Testcontainers 1.x và 2.x không tương thích.

### 9.3. Fixture Toxiproxy minh họa

Đoạn Java sau thể hiện **cách dựng fixture**, không phải test class độc lập có thể chạy mà không có thêm Spring context, topic, assertions và lifecycle cleanup. Mục đích là cho thấy broker listener được advertise về chính proxy:

```java
import eu.rekawek.toxiproxy.Proxy;
import eu.rekawek.toxiproxy.ToxiproxyClient;
import eu.rekawek.toxiproxy.model.ToxicDirection;

import org.testcontainers.containers.Network;
import org.testcontainers.containers.ToxiproxyContainer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

// Trong fixture/setup integration test; cần đóng resources bằng finally.
Network network = Network.newNetwork();

ToxiproxyContainer proxyContainer = new ToxiproxyContainer(
        DockerImageName.parse("ghcr.io/shopify/toxiproxy:2.5.0")
                .asCompatibleSubstituteFor("shopify/toxiproxy"))
        .withNetwork(network);

// Proxy cần start trước để biết host/mapped port.
proxyContainer.start();

KafkaContainer broker = new KafkaContainer(
        DockerImageName.parse("apache/kafka:3.9.1"))
        .withNetwork(network)
        .withListener(
                "kafka:19092",
                () -> proxyContainer.getHost() + ":"
                        + proxyContainer.getMappedPort(8666));

broker.start();

ToxiproxyClient toxiproxyClient = new ToxiproxyClient(
        proxyContainer.getHost(), proxyContainer.getControlPort());

Proxy kafkaProxy = toxiproxyClient.createProxy(
        "kafka-proxy", "0.0.0.0:8666", "kafka:19092");

String clientBootstrap = proxyContainer.getHost() + ":"
        + proxyContainer.getMappedPort(8666);

// Dùng clientBootstrap cho Spring producer/consumer under test.
```

Với `@DynamicPropertySource`, nên dựng fixture **trước khi Spring ApplicationContext tạo `ProducerFactory`/`ConsumerFactory`**, rồi đăng ký `spring.kafka.bootstrap-servers` bằng `clientBootstrap`. Các test cần tạo topic riêng qua `NewTopic`/`KafkaAdmin`, hoặc qua AdminClient phù hợp; không giả định broker Testcontainers tự tạo mọi topic trong ứng dụng.

**Lưu ý thứ tự:** `broker.start()` chạy sau khi proxy container đã có mapped port để supplier có thể trả về advertised address. Proxy TCP có thể được tạo sau broker startup nhưng phải sẵn sàng **trước khi client dưới test kết nối**. Nếu Testcontainers version không hỗ trợ advertised-listener supplier, dùng fixture/network topology tương đương được document cho version đó thay vì cố override một env var bị Testcontainers ghi đè.

### 9.4. Cắt và khôi phục mạng

Sau khi producer/consumer đã chứng minh có thể trao đổi qua proxy, gây lỗi hai chiều:

```java
// Tạo toxics cho đúng Proxy mà app đang sử dụng.
kafkaProxy.toxics().bandwidth(
        "cut-up", ToxicDirection.UPSTREAM, 0);
kafkaProxy.toxics().bandwidth(
        "cut-down", ToxicDirection.DOWNSTREAM, 0);

// Tại đây test quan sát send/poll/timeout/reconnect.

// Luôn gỡ cả hai toxics trong finally.
kafkaProxy.toxics().get("cut-up").remove();
kafkaProxy.toxics().get("cut-down").remove();
```

Toxic bandwidth bằng 0 mô phỏng đường truyền bị cắt; có thể dùng `timeout` toxic để chủ động đóng connection sau một delay. Với các connections đã tồn tại, test cần xác nhận kết nối thực sự bị ảnh hưởng, không chỉ tin rằng một API `create toxic` đã được gọi.

**Dọn lỗi trong `finally`:** nếu test thất bại giữa chừng và không gỡ toxics, các bước tiếp theo có thể tiếp tục thấy broker unreachable, làm test suite bị nhiễu. Nếu dùng static/shared containers, càng phải bảo đảm mỗi test tự reset network conditions.

### 9.5. Kịch bản kiểm thử bằng proxy

1. Producer gửi `before-proxy-001`, consumer nhận và ghi marker nghiệp vụ.
2. Bật toxic hai chiều; xác minh một request qua proxy không thành công trong khoảng chờ hợp lý.
3. Trong outage, gọi `publish("during-proxy-001", ...)` và theo dõi future **theo deadline**; đừng tự cancel rồi suy ra broker không ghi.
4. Gỡ toxics trong `finally`.
5. Đợi producer **gửi message mới** `after-proxy-001` và nhận ACK; consumer xử lý message này.
6. Đối soát record `during-proxy-001`: có thể thành công sau reconnect nếu outage ngắn hơn delivery timeout, hoặc thất bại nếu deadline hết.
7. Xác minh business store không mất event đã xác nhận và không ghi trùng theo `eventId`.

Nếu muốn kiểm tra producer **hết hạn delivery**, để network cut lâu hơn `delivery.timeout.ms` của profile test và chờ future kết thúc trong timeout rộng hơn. Nếu muốn kiểm tra **tự hồi phục trước deadline**, gỡ toxic sớm hơn và xem future có ACK; không dùng cùng một timeline để đòi cả hai kết quả trái nhau.

## 10. Integration test: phân biệt ACK, timeout và kết quả mơ hồ

Một test chỉ có assertion `assertThrows(TimeoutException.class, () -> send.get(1000ms))` chưa chứng minh producer thực sự thất bại. Nó chỉ chứng minh test thread không nhận kết quả trong một giây.

### 10.1. Kiểm tra future hoàn tất exceptionally

Khi timeout producer được đặt ngắn cho môi trường test và mạng bị cắt đủ lâu:

```java
CompletableFuture<SendResult<String, String>> send =
        producer.publish("outage-event-1", "sample-payload");

try {
    send.get(30, TimeUnit.SECONDS);
    throw new AssertionError("Expected send to fail during long outage");
} catch (ExecutionException expected) {
    // Producer future đã hoàn tất exceptionally.
    // Kiểm tra cause/exception category theo Kafka client version.
} catch (TimeoutException waitingTooLong) {
    // Chỉ test timeout; chưa chứng minh producer future đã fail.
    throw new AssertionError(
            "Future did not reach a terminal state within test budget",
            waitingTooLong);
}
```

Những import chính: `CompletableFuture`, `ExecutionException`, `TimeUnit`, `TimeoutException`, `SendResult`. Cần đặt producer test `delivery.timeout.ms` nhỏ hơn tổng timeout test, có tính đến broker startup và `max.block.ms`. Tùy failure, `send(...)` có thể ném exception đồng bộ trước khi trả future; khi muốn bao quát cả hai, bọc cả lời gọi `publish(...)` trong code kiểm thử và phân loại riêng.

**Không assert cố định một exception cụ thể cho mọi đứt mạng.** Tùy thời điểm, client có thể trả `TimeoutException`, `NetworkException`, `NotLeaderOrFollowerException` hoặc lỗi khác qua callback/future. Điều quan trọng là fail/timeout được phân loại và business workflow không đánh dấu message đã được bảo đảm lưu nếu chưa có xác nhận phù hợp.

### 10.2. Kiểm tra tự phục hồi trước delivery deadline

Kịch bản thứ hai sử dụng deadline đủ lớn (ví dụ 30 giây), cắt mạng khoảng ngắn rồi khôi phục **trước** hạn:

```text
send(eventId=short-outage-1)
    |
    +-- client đang retry / chờ metadata
    |
    +-- proxy restored
    |
    +-- future có thể hoàn tất success nếu điều kiện broker đáp ứng
```

Không bảo đảm future cụ thể chắc chắn thành công chỉ vì mạng phục hồi trước deadline: broker còn phải có leader/ISR, metadata/producer state phù hợp. Test nên quan sát outcome thật và có assertion trên khả năng gửi **message mới sau restore**, còn các in-flight messages được đối soát theo contract.

### 10.3. Chứng minh kết quả nghiệp vụ là idempotent

Giả sử database test có:

```sql
CREATE TABLE account_event_result (
    event_id VARCHAR(128) PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    applied_amount NUMERIC(14,2) NOT NULL
);
```

Cho consumer nhận cùng event ID hai lần (có thể publish thử hai records khác nhau với **cùng event ID** để mô phỏng duplicate delivery có kiểm soát). Service phải ghi **một** kết quả nghiệp vụ theo policy và không cộng tiền lần hai. Đây là test idempotency độc lập với sự cố mạng và nên chạy ngay cả khi integration test outage không ngẫu nhiên tạo được duplicate.

Khi broker outage giữa commit DB và commit offset, có thể xem duplicate là **hành vi bình thường của at-least-once**. Kiểm thử đúng là chứng minh kết quả nghiệp vụ cuối cùng đúng, không phải chứng minh method listener luôn được gọi đúng một lần.

## 11. Integration test consumer: hồi phục sau mất kết nối

Một test consumer cần chứng minh ứng dụng **thật sự tiêu thụ lại được** sau khi broker có mặt, không chỉ `ApplicationContext` vẫn sống.

### 11.1. Probe có giới hạn thời gian

Trong test configuration, có thể dùng một `BlockingQueue`/`ConcurrentLinkedQueue` được consumer listener cập nhật khi business processing **đã hoàn tất**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

final class ProcessedEventProbe {
    final BlockingQueue<String> completedIds = new LinkedBlockingQueue<>();

    void onCommitted(String eventId) {
        completedIds.offer(eventId);
    }

    boolean await(String eventId, long timeoutSeconds) throws InterruptedException {
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(timeoutSeconds);

        while (System.nanoTime() < deadline) {
            long remaining = deadline - System.nanoTime();
            String received = completedIds.poll(
                    Math.max(1, remaining), TimeUnit.NANOSECONDS);
            if (eventId.equals(received)) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là **test utility minh họa**; nên đóng gói thời gian chờ và reset probe theo từng test, không dùng queue shared của nhiều test chạy song song. `onCommitted(...)` chỉ được gọi sau khi business transaction hoàn tất, nếu mục tiêu assertion là dữ liệu bền vững; callback ngay lúc listener bắt đầu nhận record chưa chứng minh xử lý hoàn thành.

### 11.2. Trình tự assert

```text
[A] Kafka hoạt động
    send(before-id) -> producer ACK
    wait business committed(before-id)

[B] Cut network / stop broker
    xác minh Kafka path lỗi theo profile
    không yêu cầu listener ngừng lập tức

[C] Restore
    send(after-id) -> producer ACK
    wait business committed(after-id)

[D] Đối soát
    event IDs đã được xác nhận phải tồn tại trong output
    không có duplicate business side effects
    group lag quay về mức phù hợp
```

Các assertions cần **timeout hữu hạn**, ví dụ 10–30 giây cho local broker; trong CI chậm hoặc cluster nhiều broker cần budget lớn hơn. Tránh `Thread.sleep(...)` cố định để đoán lúc broker phục hồi hoặc group đã hoàn tất rebalance.

### 11.3. Khi consumer tự phục hồi nhưng service vẫn có lỗi

Kafka connection có thể hồi phục mà business handler vẫn tiếp tục thất bại do schema, database hoặc downstream API. Đừng kết luận Kafka lỗi chỉ vì `@KafkaListener` chưa tạo output. Kiểm tra:

- Producer event đã ACK chưa, topic/partition/offset nào?
- Consumer group đã được assign partition và fetch records chưa?
- Deserialization có lỗi không? Có DLT/retry topic không?
- Database transaction đã commit hay rollback?
- Error handler có recover record theo policy hay vẫn retry/backoff?

`DefaultErrorHandler` xử lý exceptions trong listener theo cấu hình, **không biến broker outage thành message-level DLT mặc định**. Nếu consumer không lấy được record do broker unavailable, không có record cụ thể để gửi DLT theo đường xử lý thông thường.

## 12. Lab nâng cao — một broker mất trong cluster nhiều brokers

Để kiểm tra khả năng chịu lỗi cấp cluster, cần ít nhất một Kafka cluster thử nghiệm có **nhiều brokers độc lập**, topic có replication factor phù hợp và điều kiện ISR rõ ràng.

Giả sử cluster có ba brokers, một topic được tạo với:

```text
partitions=3
replication.factor=3
min.insync.replicas=2
producer acks=all
```

Trong cấu hình truyền thống, nếu leader một partition chết nhưng còn **hai replicas trong ISR** và một replica đủ điều kiện được chọn làm leader, cluster có thể tiếp tục nhận writes sau election. Nếu ISR xuống dưới ngưỡng `min.insync.replicas`, writes `acks=all` có thể thất bại. Hành vi chi tiết phụ thuộc phiên bản Kafka, group/leader election protocol và những tính năng mới liên quan replication, nên phải quan sát **leader/ISR thực tế** chứ không suy từ số broker sống.

### 12.1. Mất một follower

```text
Partition P0: leader=B1, ISR=[B1,B2,B3]
Kill B3 (follower)
Partition P0: leader=B1, ISR có thể còn [B1,B2]
Producer acks=all, minISR=2 -> thường vẫn có thể ghi
```

Điểm cần đo: ISR shrink, producer latency trong lúc mất replica, under-replicated partitions, tốc độ replica catch-up khi B3 trở lại. Không yêu cầu consumer rebalance chỉ vì follower mất nếu consumer group coordinator và leader partitions vẫn ổn định.

### 12.2. Mất leader

```text
Partition P1: leader=B2, ISR=[B1,B2,B3]
Kill B2 (leader)
Election -> B1 hoặc B3 có thể thành leader (nếu đủ điều kiện)
Producer refresh metadata/retry -> có thể tiếp tục gửi
Consumer fetch từ leader mới
```

Trong khoảng leader election, producer có thể nhận lỗi retriable hoặc thấy latency tăng; không nên ngay lập tức restart mọi producers/consumers. Client có cơ chế làm mới metadata và retry; điều quan trọng là delivery deadline đủ và kết quả nghiệp vụ được đối soát.

### 12.3. Mất quorum/ISR đủ để ghi

```text
Partition P2: replica set=[B1,B2,B3], minISR=2
Chỉ còn một replica khả dụng trong ISR
Producer acks=all -> có thể bị NotEnoughReplicas...
```

Hành vi consumer reads, availability và durability cần được đánh giá theo topic state/cấu hình; **đừng sửa `min.insync.replicas` xuống 1 trong production chỉ để test có vẻ xanh** mà chưa chấp nhận rủi ro durability. Bật unclean leader election cũng có thể đặt dữ liệu vào nguy cơ mất record đã ACK trong một số failure modes; đây là quyết định vận hành nghiêm trọng, không phải giải pháp mặc định để “sửa” lab.

### 12.4. Bảng kỳ vọng theo cluster

| Thí nghiệm | Producer | Consumer | Điều cần xác nhận |
|---|---|---|---|
| Kill follower, ISR vẫn đủ | Có thể tiếp tục gửi; latency thay đổi. | Thường tiếp tục nếu leader/coordinator ổn. | ISR và replication catch-up. |
| Kill leader, replicas đủ | Có thể retry trong election, rồi tiếp tục. | Tạm gián đoạn fetch, rồi chuyển leader. | Không mất committed data, recovery duration. |
| Mất nhiều brokers, ISR thiếu | `acks=all` có thể fail/timeout. | Tùy partition availability và leader. | Không báo thành công khi chưa đạt durability contract. |
| Broker trở lại | Có thể hồi phục khi leader/ISR phù hợp. | Group tiếp tục, backlog giảm. | Catch-up, lag và đối soát dữ liệu. |
| Network chỉ từ một consumer bị cắt | Producer khác có thể bình thường. | Consumer đó không fetch; group có thể reassign. | Liveness của các members khác và redelivery. |

## 13. Các metric và log nên thu trong suốt thí nghiệm

Một thí nghiệm có ích cần ghi được mốc `before → outage injected → outage observed → restored → business caught up`.

| Nhóm | Tín hiệu | Cách diễn giải |
|---|---|---|
| Producer | Sends/second, error rate, request latency | Xem throughput và lỗi trong outage. |
| Producer | Failed futures, delivery timeout, record retries | Phân biệt retry đang chờ với lỗi terminal. |
| Producer | Buffer available/wait time, max.block timeouts | Xem buffer bị đầy khi broker down kéo dài. |
| Consumer | Records consumed/s, poll time, commit latency/failures | Xem có còn xử lý/commit offset được không. |
| Consumer group | Member count, partition assignment, rebalance duration | Phát hiện group membership thay đổi. |
| Backlog | Consumer lag theo topic/partition | Đo khả năng catch-up sau restore. |
| Cluster | Broker health, leader election, under-replicated partitions, ISR shrink | Phân biệt network client lỗi với broker cluster failover. |
| Spring | Container `isRunning`, `ListenerContainerIdleEvent`, `NonResponsiveConsumerEvent` | Tín hiệu bổ sung, không là kết luận duy nhất. |
| Business | Số event IDs đã ghi, duplicate suppression, pending outbox | Bằng chứng đúng/sai về kết quả nghiệp vụ. |

### 13.1. Log theo event ID và không in payload nhạy cảm

Ví dụ:

```text
2026-11-16T03:00:01Z kafka.produce.acked eventId=evt-001 partition=0 offset=103
2026-11-16T03:00:05Z chaos.kafka.disconnected scope=producer-test case=network-cut
2026-11-16T03:00:20Z kafka.produce.failed eventId=evt-002 errorType=TimeoutException
2026-11-16T03:00:30Z chaos.kafka.restored scope=producer-test
2026-11-16T03:00:32Z kafka.produce.acked eventId=evt-003 partition=0 offset=104
2026-11-16T03:00:33Z business.event.applied eventId=evt-003 status=COMMITTED
```

Các timestamp và values chỉ là **ví dụ format**. Không log toàn bộ JSON payload, headers chứa token, keystore credentials hoặc nội dung dữ liệu cá nhân để debug outage. Một event ID/trace ID ổn định giúp đối soát tốt hơn nhiều so với hàng nghìn dòng exception giống nhau.

### 13.2. Đừng chỉ đếm warnings của Kafka NetworkClient

Trong outage, client có thể log các cảnh báo như không kết nối được node hoặc mất coordinator. Một số warnings là bình thường trong lúc retry/failover. Dùng logs cùng với **end-to-end metrics** và business output; số warnings giảm không chứng minh backlog đã được xử lý hết.

### 13.3. Consumer idle không đồng nghĩa cluster down

Nếu không có messages mới, `ListenerContainerIdleEvent` có thể xuất hiện cả khi broker hoàn toàn khỏe. Nếu network làm `poll()` không quay lại trong thời gian dài, `NonResponsiveConsumerEvent` có thể giúp phát hiện theo monitor threshold. Mỗi tín hiệu cần được diễn giải cùng partition assignment, lag, broker connectivity và producer health.

## 14. Readiness, liveness và restart policy khi Kafka unavailable

Với Spring Boot chạy trên Kubernetes, cách cấu hình health probes có thể làm một outage Kafka tạm thời **trầm trọng hơn** nếu mọi Pods liên tục bị restart.

| Tình huống | Chính sách nên cân nhắc | Rủi ro nếu xử lý sai |
|---|---|---|
| Kafka down ngắn, client vẫn retry | Giữ process sống, monitor backlog và reconnect. | Liveness kill hàng loạt làm tăng rebalance và startup pressure. |
| Consumer đã dừng do fatal auth error | Alert và sửa credentials/ACL, cân nhắc restart theo policy. | Retry network vô hạn không sửa được ACL sai. |
| Kafka unavailable kéo dài, chức năng không thể phục vụ | Readiness có thể phản ánh unavailability tùy vai trò service. | Readiness `false` không tự dừng Kafka poll; cần hiểu impact HTTP/Kafka. |
| Producer backlog lớn trong RAM | Backpressure, bounded buffer, reject/defer requests. | OOM hoặc mất events khi process chết. |
| Consumer group không có assignment sau broker phục hồi | Kiểm tra group/metadata/rebalance và container state. | Restart mù có thể làm churn nhiều hơn. |

Spring Boot Actuator `liveness` được thiết kế phản ánh khả năng process tự hoạt động; dùng Kafka connection làm điều kiện kill process cần được cân nhắc kỹ. Với một consumer service có retry/reconnect là cơ chế bình thường, việc Kafka tạm thời down **không đồng nghĩa JVM bị hỏng**. Nếu cần liveness thực sự, phải phân biệt process deadlock/fatal state với external dependency outage.

## 15. Những rủi ro riêng của retry, DLT và transactions

### 15.1. `DefaultErrorHandler` và retry trên record

`DefaultErrorHandler` xử lý exceptions phát sinh trong record listener theo policy. Khi broker không reachable và **không có record mới được delivery**, đây không phải một lỗi item thông thường mà error handler có thể skip/DLT ngay lập tức.

Ngược lại, nếu listener đã nhận record, gọi database/API và gặp lỗi, error handler có thể retry record hoặc gửi DLT theo cấu hình. **Một outage Kafka và một outage downstream không nên dùng chung kết luận:** cần biết failure xảy ra trước khi poll, trong xử lý hay khi commit/publish recovery message.

### 15.2. DLT không tự giải quyết broker unavailable

Nếu DLT cùng Kafka cluster đang down, dead-letter producer cũng có thể không publish được. Không được catch exception của DLT publisher rồi commit source offset như thể record đã được recover, trừ khi có một cơ chế lưu trữ bền khác và policy chấp nhận rõ ràng.

Đối với message quan trọng, muốn tránh mất khi Kafka unavailable có thể dùng transactional outbox, hàng đợi bền phía producer hoặc cơ chế durable retry ở tầng ứng dụng. **Queue RAM** và log console không phải nơi lưu bảo đảm khi process crash.

### 15.3. Kafka transactions / transactional producer

Nếu ứng dụng dùng Kafka transaction cho consume-transform-produce, khi coordinator/broker mất kết nối có thể xảy ra transaction timeout, abort, retry hoặc producer fencing. Exactly-once semantics của Kafka có phạm vi Kafka transaction phù hợp; **không tự làm HTTP/DB side effects exactly-once**.

Khi chạy thí nghiệm transactions, cần quan sát producer state sau lỗi fatal. Một producer bị fenced/fatal có thể phải được đóng và tạo lại theo cách Spring Kafka quản lý; không chỉ lặp `send` vô hạn trên cùng producer instance. Đồng thời, `transactional.id` không được trùng giữa nhiều replicas active ngoài chủ đích protocol.

### 15.4. `read_committed` và transaction chưa hoàn tất

Một consumer với `isolation.level=read_committed` chỉ đọc records từ transactions đã commit theo semantics Kafka. Trong outage, transactions đang dở có thể chưa được phân giải cho tới khi coordinator/brokers hồi phục hoặc transaction timeout. Điều này có thể làm lag/visibility khác `read_uncommitted`; không nên suy từ việc “topic có offset mới nhưng consumer không đọc” rằng consumer luôn bị lỗi.

## 16. Ma trận chaos test để không bỏ sót trường hợp quan trọng

Không nên chỉ chạy một lần `docker stop` rồi kết luận ứng dụng đã resilient. Một ma trận thực hành có thể gồm:

| Test ID | Fault injection | Thời điểm inject | Kỳ vọng chính |
|---|---|---|---|
| `B1` | Stop broker một node | Khi producer/consumer idle | Clients reconnect khi broker trở lại. |
| `B2` | Kill broker một node | Trong lúc producer đang gửi | Future thành công/thất bại/ambiguous được xử lý theo contract; không mất business event đã xác nhận. |
| `B3` | Cut proxy hai chiều | Sau consumer đã xử lý DB nhưng trước offset commit | Có thể redelivery; idempotency ngăn side effect trùng. |
| `B4` | Cut proxy rồi restore nhanh | Trước `delivery.timeout.ms` | Producer có cơ hội hoàn tất send; new send sau restore thành công. |
| `B5` | Cut proxy lâu hơn delivery deadline | Khi gửi nhiều messages | Các futures terminal failure được quan sát; bounded retry/backpressure. |
| `B6` | Tăng latency/jitter proxy | Khi có traffic | Đo p95/p99 latency, request timeouts, retry rate. |
| `B7` | Kill follower trong cluster nhiều node | Khi leader khỏe và ISR đủ | Ghi/đọc có thể tiếp tục; ISR giảm rồi hồi phục. |
| `B8` | Kill leader partition | Khi topic có replicas đủ | Leader election, clients refresh metadata và tiếp tục. |
| `B9` | Mất đủ brokers làm ISR thấp hơn minISR | Khi producer `acks=all` | Writes fail/retry theo durability policy, không đánh dấu thành công giả. |
| `B10` | Thay `advertised.listeners` sai trong lab | Khi bootstrap thành công | Client có thể fail ở metadata endpoints; chẩn đoán đúng cấu hình. |
| `B11` | ACL/credential bị từ chối trong test | Khi startup consumer | Phân loại auth error, không kết luận là network outage. |
| `B12` | Broker phục hồi nhưng DB downstream vẫn down | Sau network restore | Kafka connection khỏe nhưng business processing chưa hoàn thành; error handler tiếp tục theo policy. |

Trong mọi bài test phải giữ: topic, partition count, replication factor, `min.insync.replicas`, producer acks, consumer ack mode, key/event ID và thời điểm inject. Nếu thay nhiều yếu tố cùng lúc, rất khó chứng minh cấu hình nào tạo ra hành vi quan sát được.

### 16.1. Tạo record IDs bất biến để đối soát

Ví dụ test producer phát các events:

```text
before-0001
before-0002
inflight-0003
during-0004
after-0005
```

Mỗi event có `eventId` ổn định làm Kafka key và business deduplication key. Trước test, ghi lại **tập events dự kiến** theo loại:

- `ACKED`: producer có xác nhận từ Kafka theo cấu hình acks.
- `FAILED`: producer future hoàn tất exceptionally; cần policy retry/reconciliation, không tự suy ra record chắc chắn vắng mặt.
- `UNKNOWN`: caller timeout hoặc process chết trước khi biết outcome.

Sau restore, phải đối chiếu các nhóm này theo contract. Một test không mất dữ liệu thường yêu cầu mọi `ACKED` event được xử lý nghiệp vụ đúng, trong khi `UNKNOWN` được giải quyết qua reconciliation hoặc retry có idempotency. **Không ép tất cả attempted sends đều phải xuất hiện**, vì một số lần gửi có thể chưa được Kafka chấp nhận khi broker down.

### 16.2. Đo recovery time

Ghi các mốc thời gian:

```text
t0: lỗi được inject
t1: client/monitor phát hiện vấn đề
t2: mạng/broker được phục hồi
t3: producer có successful ACK đầu tiên sau lỗi
t4: consumer có business commit đầu tiên sau lỗi
t5: lag quay về baseline / backlog được xử lý hết
```

Từ đó đo **detection latency**, **reconnect time**, **time-to-first-success** và **time-to-catch-up**. Các mốc nên dùng đồng hồ nhất quán và event trace có correlation ID. Nếu broker hồi phục ở `t2` nhưng `t5` lâu hơn, có thể backlog quá lớn hoặc throughput tiêu thụ chưa đủ; đừng đổ lỗi riêng cho reconnect.

## 17. Runbook vận hành khi Kafka broker không truy cập được

Khi có cảnh báo producer timeout hoặc consumer lag tăng, một runbook có thể theo thứ tự sau:

### Bước 1 — Xác định phạm vi sự cố

1. Chỉ một service/Pod bị lỗi hay mọi clients đều bị lỗi?
2. Một broker node, một partition leader hay toàn cluster không truy cập được?
3. Producer không gửi được, consumer không fetch được, commit không thành công, hay chỉ không có dữ liệu mới?
4. Có thay đổi gần đây với DNS, certificate, ACL, network policy, service mesh hoặc advertised listener không?
5. Kafka broker có đang restart/rolling upgrade theo kế hoạch không?

Nếu chỉ một Pod lỗi còn các Pods khác bình thường, kiểm tra network namespace/sidecar/egress policy của Pod đó trước khi coi toàn Kafka cluster down.

### Bước 2 — Thu bằng chứng có kiểm soát

- Ghi thời điểm và client IDs, bootstrap hosts, topics/partitions, consumer groups, không ghi credentials.
- Kiểm tra broker process health, cluster metadata, leader/ISR và coordinator.
- Xem Kafka client logs cho disconnect, timeout, auth/authorization hoặc deserialization failures.
- Thu `consumer lag`, producer error rate, retries, timeouts, commit failures và buffer metrics.
- Kiểm tra trạng thái side effects, outbox và business database để biết event nào đã commit.

Không chuyển sang `DEBUG` toàn bộ Kafka client trên workload lớn trong thời gian dài nếu không có kế hoạch hạn chế log, vì lượng log network/record có thể tăng mạnh.

### Bước 3 — Chờ cơ chế tự hồi phục hay can thiệp?

| Điều kiện | Hành động gợi ý |
|---|---|
| Lỗi mạng ngắn, Kafka cluster đã khỏe, clients đang reconnect | Theo dõi với timeout/SLO phù hợp, tránh restart hàng loạt. |
| Hostname advertise sai | Sửa listener/DNS/route đúng nguồn lỗi; restart client đơn thuần không giải quyết. |
| Broker leader unavailable nhưng ISR đủ | Theo dõi leader election/metadata refresh và producer deadlines. |
| ISR thiếu, writes không đáp ứng durability | Xử lý broker/replica health và capacity; không âm thầm hạ durability policy. |
| Auth/ACL sai | Sửa identity/permissions/certificate; tránh retry vô hạn hoặc disable security. |
| Consumer container dừng vì lỗi fatal | Điều tra `ConsumerStoppedEvent`/logs trước khi khởi động lại đúng phạm vi. |
| Producer buffer quá tải | Bật backpressure, queue bền hoặc reject requests có kiểm soát. |
| Lỗi commit offset sau DB success | Chấp nhận replay theo idempotency và đối soát kết quả. |

### Bước 4 — Xác nhận hồi phục bằng dữ liệu

1. Producer có thể gửi **event mới** và nhận ACK theo `acks` đã chọn.
2. Consumer group có assignment hoạt động và tiêu thụ được event mới.
3. Business store phản ánh đúng events đã xác nhận.
4. Duplicate suppression không tăng thành lỗi nghiệp vụ; không có thiếu dữ liệu ngoài policy.
5. Lag/throughput/timeout rate ổn định trong khoảng thời gian đã định.
6. Nếu dùng transactional producers, trạng thái transaction/fencing được xử lý đúng.

### Bước 5 — Tổng kết sự cố và cải thiện

Ghi nguyên nhân, thời lượng mất kết nối, events ambiguous, policy xử lý retry, tình trạng ISR/leader, tốc độ catch-up và những khoảng chờ vượt SLA. Sử dụng kết quả để điều chỉnh cấu hình timeout/retry, backpressure, idempotency và alert thresholds; tránh chỉ “tăng tất cả timeouts” mà không có bằng chứng.

## 18. Những lỗi phổ biến khi mô phỏng broker mất kết nối

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Dừng container nhưng Spring app cũng dừng | Đặt ứng dụng test cùng broker container/process. | Chạy test client bên ngoài broker container. |
| Cắt Toxiproxy nhưng producer vẫn gửi thành công | Metadata advertise địa chỉ broker trực tiếp, đi vòng proxy. | Định tuyến cả bootstrap và advertised broker endpoints qua proxy. |
| Đổi host port Docker nhưng Kafka client vẫn dùng port cũ | `advertised.listeners` chưa khớp địa chỉ client truy cập. | Kiểm tra listener config/mapped port và metadata. |
| Gửi message khi Kafka down không throw ngay | Producer buffer/retry bất đồng bộ, `.send()` trả future. | Chờ terminal outcome hoặc đo `max.block`/`delivery.timeout`. |
| `future.get(1s)` timeout, test kết luận record thất bại | Timeout của caller khác producer delivery timeout. | Kiểm tra completion callback/future terminal state. |
| Broker restart xong vẫn không thấy record trước đó | Broker container bị tạo mới, dữ liệu không persist hoặc group offset khác. | Dùng container/volume đúng, đối chiếu topic, group, key và retention. |
| `auto-offset-reset=earliest` không đọc từ đầu | Consumer group đã có committed offset. | Dùng group test mới hoặc seek/reprocess có kiểm soát, không sửa offset tùy tiện. |
| Consumer có log idle nên tưởng broker down | Topic thật sự không có record mới. | Kết hợp lag, broker connectivity và producer rate. |
| Không có `ConsumerStoppedEvent` khi broker down | Container vẫn chạy và tự reconnect. | Theo dõi network/consumer metrics, không kỳ vọng stop event. |
| Kafka connection phục hồi nhưng DB output vẫn thiếu | Downstream/database/handler lỗi hoặc offset commit sai. | Đối soát events, transaction và error handler. |
| Record bị xử lý trùng | DB side effect commit trước Kafka offset commit. | Consumer idempotency theo business event ID. |
| Producer publish trùng sau retry | Ứng dụng tự gửi lại cùng sự kiện bằng request mới. | Durable outbox, event ID ổn định và consumer dedupe. |
| Thử cluster failover bằng topic RF=1 | Không có replica thay leader. | Dùng cluster 3 brokers/topic RF=3 và minISR phù hợp. |
| `acks=all` fail khi một broker chết | ISR thấp hơn policy hoặc đang election; phụ thuộc topic state. | Xem ISR/leader/minISR thay vì hạ acks không có đánh giá. |
| CI thỉnh thoảng fail dù mạng đã restore | Test dựa `Thread.sleep`, topic/group chia sẻ, group rebalance chưa xong. | Dùng bounded await, fixture cô lập, kiểm tra assignment và output. |
| Test đang chạy mà Docker data bị xóa | Cleanup dùng `docker rm -v`/`down -v` không kiểm soát. | Chỉ cleanup resources được gắn nhãn lab, có xác nhận dữ liệu không cần giữ. |
| Liveness probe restart mọi Pods khi Kafka chập chờn | Kafka dependency bị dùng như tín hiệu process fatal. | Tách external outage khỏi JVM liveness, tránh restart storm. |
| DLT publish cũng timeout | DLT broker cùng cluster outage. | Dùng durable pending/outbox hoặc tiếp tục retry/reconciliation đúng policy. |
| Toxiproxy test chặn sai client | Nhiều client factories/advertised endpoints, chỉ một path qua proxy. | Định danh client IDs, cấu hình tất cả producer/consumer factories theo test bootstrap. |
| Broker khởi động lại nhưng chưa có leader | Metadata/leader election/controller chưa ổn định. | Chờ cluster/topic readiness đúng, không chỉ TCP port mở. |

## 19. Kịch bản kiểm thử tự động được khuyến nghị

### 19.1. Unit test: phân loại lỗi, không cần Kafka broker

Một service xử lý kết quả publish nên tách policy khỏi `KafkaTemplate`:

```text
send ACK thành công -> đánh dấu CONFIRMED
future terminal exception -> đánh dấu FAILED/RETRYABLE theo loại lỗi
caller timeout nhưng future chưa terminal -> UNKNOWN/PENDING
crash giữa Kafka ACK và lưu trạng thái -> reconcile theo event ID
```

Unit test có thể mock một `CompletableFuture` hoàn tất thành công/thất bại để kiểm tra policy. Không cần broker thật nếu đang kiểm thử cách phân loại kết quả và cập nhật outbox. Với trạng thái `UNKNOWN`, không được tự đánh dấu `NOT_PUBLISHED` rồi gửi lại mà không có chiến lược idempotency.

### 19.2. Integration test: broker reachable và unreachable

Với Testcontainers/Toxiproxy hoặc local Docker lab, kiểm tra:

1. Khi mạng bình thường, `KafkaTemplate.send` nhận ACK và listener nhận record.
2. Khi mạng bị cắt đủ lâu, một số send futures báo failure theo cấu hình deadline.
3. Khi mạng phục hồi, producer gửi record mới thành công mà không cần rebuild toàn ApplicationContext trong kịch bản tự hồi phục.
4. Consumer xử lý event mới, group lag quay về mức mục tiêu.
5. Dữ liệu nghiệp vụ có đúng tập event IDs và không có side effect trùng.

Không viết test yêu cầu **mọi in-flight future đều thất bại** khi network cut ngắn, vì producer có thể retry thành công. Với test dài hơn delivery timeout, chờ terminal outcome thay vì dùng sleep cố định rồi suy đoán.

### 19.3. Integration test: broker crash và restart

Tạo test setup có broker local/cluster do test sở hữu và storage bền qua restart. Tiêm crash khi một record đang được xử lý; sau phục hồi kiểm tra business marker và committed offsets. Nếu test cần kill process thật, chạy producer/consumer và broker theo các process/containers riêng để không làm chết JUnit runner. Không chạy chaos testing trên Kafka cluster dùng chung.

### 19.4. Đảm bảo cleanup

- Gỡ toxics Toxiproxy trong `finally`.
- Dừng/đóng đúng Testcontainers resources sau test.
- Không để shared static `BlockingQueue` chứa events từ test trước.
- Dùng topic/group IDs test riêng và reset fixture business DB.
- Bảo đảm không có background producer task tiếp tục viết vào topic của test kế tiếp.
- Không chạy parallel chaos tests trên cùng một broker/container khi các ca cần kiểm soát toàn bộ network state.

## 20. Bài tập thực hành

### Bài tập 1 — Dừng broker và tự phục hồi

Khởi động Kafka local với Docker, Spring Boot producer và consumer như các ví dụ trên. Gửi hai events trước outage, dừng broker bằng `docker stop`, theo dõi producer futures/consumer logs, sau đó `docker start`. Gửi event mới và xác minh consumer hoàn tất. Viết timeline theo mốc thời gian và phân biệt `caller timeout` với `producer delivery timeout`.

### Bài tập 2 — Cắt mạng mà không giết broker

Dùng Toxiproxy chặn hai chiều giữa client và broker. Xác minh client không đi vòng proxy nhờ `advertised.listeners`, trong khi Kafka broker vẫn healthy. Restore proxy rồi đo thời gian producer ACK đầu tiên, consumer business commit đầu tiên và lag catch-up.

### Bài tập 3 — Outage ngắn so với dài

Thử network cut 3 giây và 25 giây, profile producer có `delivery.timeout.ms=15.000`. So sánh outcome của in-flight futures, sends mới sau khi mạng được khôi phục và thời gian chờ của caller. Không viết assertion rằng cut 3 giây luôn thành công; giải thích các yếu tố broker readiness/metadata/retry.

### Bài tập 4 — Idempotency sau offset commit không rõ kết quả

Thiết kế service ghi database và marker `event_id` trong cùng transaction, rồi cho cùng event được consume hai lần. Xác minh business result chỉ được áp dụng một lần. Sau đó mô phỏng mất broker ngay sau DB commit nhưng trước offset ACK để quan sát khả năng redelivery; kiểm tra bằng dữ liệu cuối, không chỉ callback count.

### Bài tập 5 — Leader/follower failure trong cluster ba brokers

Tạo topic RF=3, `min.insync.replicas=2`, producer `acks=all`. Thử dừng follower rồi dừng leader ở hai bài riêng, quan sát leader election, ISR, latency và tính liên tục của consumer. Sau đó giảm số replicas sẵn sàng xuống dưới minISR trong cluster test và ghi lại producer errors. Giải thích vì sao không nên hạ durability policy trong production để “sửa” bài test.

### Bài tập 6 — Phân biệt Kafka unavailable và lỗi xác thực

Thử hai kịch bản trên môi trường lab: broker không truy cập được do network, và một principal test bị từ chối bởi ACL. Quan sát exception family, container state, `ConsumerStoppedEvent` nếu có và hành động sửa phù hợp. Không tắt TLS/ACL production để mô phỏng.

### Bài tập 7 — Xây dựng dashboard phục hồi

Tạo dashboard có producer error rate, consumer lag, group assignments, retry count, broker ISR/under-replicated partitions và duplicate suppression count. Đánh dấu các mốc outage/restore. Đề xuất ngưỡng cảnh báo phân biệt mất broker thật, Kafka topic rỗng hợp lệ và downstream xử lý chậm.

### Bài tập 8 — Viết runbook và báo cáo chaos test

Soạn báo cáo theo mẫu:

```text
Experiment: kafka-network-cut-478
Environment: isolated test
Kafka topology: 1 broker / 1 partition / RF=1
Fault: proxy upstream+downstream blocked
Duration: <recorded seconds>
Producer config: acks=all, idempotence=true, delivery.timeout.ms=15000
Consumer config: auto-commit=false, AckMode.RECORD

Before: produced/acked/processed event IDs
During: errors, unknown outcomes, commit failures, lag
After: new producer ACK, consumer resumed, lag caught up
Business: missing IDs, duplicates suppressed, unresolved ambiguous IDs
Recovery time: measured timestamps
Conclusion: pass/fail against declared acceptance criteria
```

**Mẫu là dữ liệu minh họa**, cần điền số đo thật. Đừng ghi `PASS` chỉ vì Kafka container đã `running` trở lại; tiêu chí cuối phải kiểm tra dữ liệu nghiệp vụ và năng lực tiếp tục xử lý.

## 21. Những nguyên tắc cần nhớ

1. **Mất broker, mất mạng theo client và mất leader trong cluster là ba tình huống khác nhau.** Phải chọn đúng kiểu fault injection để kiểm tra điều cần chứng minh.
2. **`bootstrap.servers` chỉ giúp lấy metadata ban đầu; `advertised.listeners` quyết định các kết nối tiếp theo.** Một proxy chỉ đứng ở bootstrap có thể bị đi vòng.
3. **Producer `.send()` không đồng nghĩa ACK.** Quan sát future/callback và phân biệt caller wait timeout với producer delivery timeout.
4. **Retry và idempotent producer không thay thế business idempotency.** Ứng dụng gửi lại một event như operation mới vẫn có thể tạo thêm Kafka record.
5. **Consumer có thể tự reconnect và đọc lại records.** Offset commit và business DB commit không tự atomic với nhau nếu dùng các transaction độc lập.
6. **Không dùng `ListenerContainerIdleEvent` làm kết luận Kafka down.** Idle hợp lệ và poll không phản hồi là những trường hợp khác nhau.
7. **Không ép `DefaultErrorHandler`/DLT giải quyết một broker outage thuần network.** Khi không poll được record, record-level recovery chưa có gì để xử lý.
8. **Cluster có replication/ISR mới kiểm tra failover broker đúng nghĩa.** Một broker RF=1 chỉ phù hợp outage toàn dịch vụ.
9. **Kết nối được phục hồi không có nghĩa business output đã đúng.** Cần đối soát ACKed events, ambiguous outcomes, lag và idempotency.
10. **Mọi thí nghiệm phải cô lập, có timeout và cleanup rõ ràng.** Không chạy stop/kill/netem lên hạ tầng Kafka production khi chưa có một quy trình chaos testing được phê duyệt.

## 22. Tài liệu tham khảo chính thức

- [Spring Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): `AckMode`, offset commits, rebalance và listener container lifecycle.
- [Spring Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html): idle, non-responsive và consumer stop events.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retry và recovery khi listener lỗi.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi Kafka transactions và EOS.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` và integration testing.
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): `spring.kafka.*`, factories, `KafkaTemplate`, tests.
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs): `acks`, idempotence, delivery timeout, retries và reconnect.
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): group membership, offset và polling configuration.
- [Apache Kafka — Topic Configuration](https://kafka.apache.org/documentation/#topicconfigs): replication, ISR và min ISR constraints.
- [Apache Kafka 3.9 — Docker](https://kafka.apache.org/39/getting-started/docker/): chạy image Apache Kafka JVM chính thức trong local lab.
- [Testcontainers for Java — Kafka Module](https://java.testcontainers.org/modules/kafka/): Kafka container và custom listeners cho test networks.
- [Testcontainers for Java — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): fault injection bằng network proxy, latency và connection cut.



