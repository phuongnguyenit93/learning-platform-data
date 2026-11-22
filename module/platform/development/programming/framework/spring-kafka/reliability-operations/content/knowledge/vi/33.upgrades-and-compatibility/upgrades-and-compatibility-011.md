# Rollback version an toàn trong Spring Kafka Reliability Operations

## 1. Bài toán: rollback ứng dụng không có nghĩa rollback dữ liệu

Giả sử dịch vụ `orders-consumer` chạy Spring Kafka, đọc topic `orders.events` và ghi đơn hàng vào PostgreSQL. Nhóm phát triển nâng cấp từ image `1.8.2` lên `1.9.0` với một số thay đổi:

- Thêm trường `paymentMethod` vào event.
- Thay logic retry và DLT.
- Thay cấu trúc bảng `orders`.
- Nâng thư viện Spring Kafka/Kafka client.
- Điều chỉnh số consumer và thời điểm commit offset.

Sau triển khai, độ trễ tăng và một số record bị xử lý sai. Người vận hành muốn chạy `kubectl rollout undo` để quay về image cũ. Lệnh đó có thể khôi phục **Pod template của Deployment**, nhưng không tự khôi phục:

- **Committed offsets** của Kafka consumer group.
- **Thông điệp** đã được producer/consumer phiên bản mới gửi vào topic.
- **Schema/serialization contract** đã đăng ký hoặc đã phát hành.
- **Dữ liệu database** và các side effect ngoài Kafka đã commit.
- **ConfigMap/Secret** được chỉnh độc lập với Deployment.
- **Kafka Streams state stores/changelogs** đã được phiên bản mới ghi.
- **Topic partitions, broker ACL, broker configuration** đã thay đổi.

Vì vậy, **rollback version an toàn** là một phương án đã được chuẩn bị trước cho việc **đưa code/cấu hình trở lại phiên bản ổn định mà vẫn bảo toàn tính đúng đắn của dữ liệu**.

Bài học thuộc **Nâng cấp và tương thích** của *Spring Kafka Reliability Operations*. Bạn sẽ học:

1. Xác định loại rollback: application, client library, Kafka Streams hay broker.
2. Thiết lập compatibility contract để phiên bản cũ đọc được record do bản mới tạo ra.
3. Giữ nguyên consumer group identity và đánh giá committed offsets khi rollback.
4. Thiết kế idempotent consumer, outbox và database migration có đường quay lại.
5. Tổ chức canary, rolling update, freeze, rollback, resume và đối soát.
6. Xử lý rủi ro retry/DLT, transactions, listener concurrency và Kafka Streams state.
7. Dùng Kubernetes rollout history đúng phạm vi, không nhầm với rollback cấu hình/dữ liệu.
8. Viết integration/recovery test kiểm dữ liệu, không chỉ kiểm status hoặc process exit code.

Ví dụ dùng **Spring Boot 3.x, Spring Kafka 3.x, Kafka broker tương thích và Java 17+**. Khi nâng lên major version khác, cần đối chiếu release notes và compatibility matrix của chính các phiên bản được triển khai.

## 2. Phân loại rollback trước khi ra lệnh

Từ “Kafka version” có thể chỉ nhiều lớp khác nhau:

| Lớp | Ví dụ thay đổi | Có thể dùng Deployment rollback? | Điều phải kiểm |
| --- | --- | --- | --- |
| **Ứng dụng consumer** | Logic Java, listener, retry | Có thể khôi phục image cũ | Schema, offsets, side effects, config. |
| **Ứng dụng producer** | Event payload, serializer | Có thể khôi phục image cũ | Message phiên bản mới đã xuất bản. |
| **Spring Kafka dependency** | Spring Kafka 3.x → bản khác | Thường rollback theo image/BOM | API semantics, error handler, listeners. |
| **Kafka Java client** | Client version mới | Thường rollback theo image | Broker/client protocol compatibility. |
| **Kafka Streams app** | Topology, state store, serde | Image rollback **chưa đủ** | State/changelog/snapshot format và topology. |
| **Kafka broker** | Cluster software/protocol version | **Không** dùng rollout app | Metadata format, cluster feature level, broker compatibility. |
| **Schema Registry** | Compatibility mode/schema mới | Registry có vòng đời riêng | Reader/writer compatibility; dữ liệu đã tồn tại. |
| **Kafka topic/ACL** | Partitions, retention, policy | Không | Thay đổi hạ tầng, offsets, record availability. |
| **Database schema** | Thêm/bỏ cột, đổi kiểu | Không | Migration và dữ liệu được version mới ghi. |

**Trọng tâm bài này là rollback ứng dụng Spring Kafka**. Broker downgrade là công việc hạ tầng với quy tắc phiên bản/metadata rất nghiêm ngặt; không được tự xem là thao tác đối xứng của broker upgrade. Phải dựa vào tài liệu chính thức của bản Kafka và kế hoạch thử nghiệm cluster cụ thể.

## 3. Ba câu hỏi cần trả lời trước rollback

Trước khi đổi image về bản cũ, xác minh:

**1. Phiên bản cũ có còn đọc được dữ liệu mới không?**

- Consumer cũ có deserialize được schema mới không?
- Các enum/event type mới có bị nó từ chối không?
- Một record mới có thể làm consumer cũ lặp lỗi vô hạn không?
- File/table/state mà bản mới tạo có tương thích bản cũ không?

**2. Khi chạy lại, dữ liệu có bị xử lý thiếu hoặc trùng không?**

- Consumer group đã commit offset tới đâu?
- Đã có message được xử lý rồi nhưng chưa commit offset hay ngược lại?
- Side effects bên ngoài Kafka đã commit chưa?
- ID nghiệp vụ/idempotency key có ổn định qua nhiều phiên bản không?

**3. Cấu hình và hạ tầng có còn phù hợp với binary cũ không?**

- ConfigMap, Secret, environment và feature flags của bản mới có được rollback cùng không?
- Database còn các cột/table mà binary cũ cần không?
- ACL, topic names, serializer class và SASL/TLS settings còn hợp lệ không?
- Retention/compaction có làm mất dữ liệu cần replay không?

Chỉ khi câu trả lời đã được chứng minh bằng compatibility test hoặc phương án điều hành có kiểm soát mới nên coi rollback là an toàn.

## 4. Ví dụ luồng dữ liệu trước và sau nâng cấp

~~~text
                     Kafka topic
                   orders.events
                         |
                         v
                 Consumer group G
                         |
            +------------+-------------+
            |                          |
         Version A                  Version B
         (ổn định)                 (mới triển khai)
            |                          |
            v                          v
       Deserialize v1             Deserialize v1/v2
            |                          |
            v                          v
       PostgreSQL                  PostgreSQL
            |                          |
            +-------------+------------+
                          |
                          v
                 Business side effects
~~~

Trong **rolling deployment**, một số Pod cũ và mới có thể cùng tồn tại. Nếu chúng cùng `group.id`, Kafka phân phối các partition cho các consumer thuộc group theo cơ chế rebalance; chúng **không phải** hai hệ thống độc lập cùng nhận mọi record. Phân vùng được gán cho phiên bản nào có thể thay đổi khi rebalance.

Điều đó có nghĩa:

- Producer chỉ được phát message theo schema mà cả A và B có thể xử lý trong giai đoạn overlap.
- B có thể xử lý partition đang gán cho nó; khi rollback A phải xử lý được các record được phát trong thời gian B hoạt động.
- Một consumer group mới với group ID khác là luồng xử lý **độc lập** với committed offsets riêng, không phải rollback đơn thuần.

## 5. Định nghĩa kế hoạch rollback trước release

Mỗi release nên có một bản ghi cấu hình đủ để tái tạo:

| Thành phần release | Dữ liệu lưu trong manifest triển khai |
| --- | --- |
| Artifact | Image tag **và immutable digest**. |
| Dependency | Spring Boot BOM, Spring Kafka, Kafka clients, Java runtime. |
| Deployment | Replicas, container args, resource requests, rollout strategy. |
| Kafka config | Bootstrap cluster, topic names, consumer group, client properties. |
| Security | Auth mechanism, secret reference/version, TLS truststore, ACL changes. |
| Serialization | Event schema versions, serde configuration, compatibility mode. |
| Data | Database migration revision, feature flags và data contract. |
| Recovery | Listener ack mode, retry/DLT policy, transactions, idempotency. |
| Observability | Dashboard và release marker dùng khi điều tra. |
| Rollback artifact | Image cũ còn tồn tại, migration path và cách revert config. |

Chỉ lưu một dòng “previous version=1.8.2” là chưa đủ. Nếu Deployment trỏ tới ConfigMap/Secret theo tên cố định, việc rollback Pod template **không tự rollback nội dung** của những resource này.

Nên dùng GitOps/Helm/Kustomize với versioned manifest và snapshot cấu hình, giữ bản build cũ còn kéo được từ registry, và có quy trình phê duyệt riêng cho dữ liệu/offset.

### Chọn thời điểm rollback

Có thể đưa ra một số trigger:

- Tốc độ business failures tăng sau deploy.
- Consumer lag tăng liên tục và tốc độ xử lý giảm.
- Tỉ lệ DLT tăng, các record không có recovery path.
- Producer send errors/latency tăng hoặc mất khả năng nhận ACK.
- Tỉ lệ deadlock/duplicate/idempotency conflict vượt ngưỡng.
- Lỗi deserialization/authorization sau nâng cấp.
- Output sai dữ liệu, kể cả khi các Pod vẫn báo Ready.

Tùy mức độ, cần **stop/freeze producer hoặc consumer có kiểm soát** trước khi rollout, không phải luôn rollback ngay trong khi vẫn có message không tương thích được tạo ra.

## 6. Compatibility: nguyên tắc “old reader, new data”

Một bản rollback an toàn đòi hỏi **phiên bản cũ có khả năng đọc dữ liệu do phiên bản mới tạo ra trong cửa sổ rollout**. Đây là tiêu chí quan trọng hơn việc binary cũ có còn khởi động.

Có ba kiểu compatibility liên quan:

| Kiểu | Câu hỏi |
| --- | --- |
| **Backward compatibility** | Code/schema **mới** có đọc được dữ liệu **cũ** không? |
| **Forward compatibility** | Code/schema **cũ** có đọc được dữ liệu **mới** không? |
| **Full compatibility** | Cả hai chiều có được hỗ trợ không? |

Tên chính sách “BACKWARD/FORWARD/FULL” trong Schema Registry còn có quy tắc cụ thể theo **format** và biến thể transitive/non-transitive. Không được chỉ suy luận từ tên rồi coi mọi đổi schema đều hợp lệ. Một field mới có default trong Avro có thể hỗ trợ một chiều, trong khi đổi required field/enum/field type thường cần phân tích riêng.

### 6.1. Một ví dụ JSON event v1/v2

Version A chỉ biết:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-501",
  "amount": 1200
}
~~~

Version B dự kiến bổ sung field:

~~~json
{
  "eventId": "evt-1002",
  "orderId": "order-502",
  "amount": 2300,
  "paymentMethod": "CARD"
}
~~~

Nếu version A dùng Jackson DTO **bỏ qua unknown properties**, field mới có thể không làm nó fail:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV1(
        String eventId,
        String orderId,
        long amount) {
}
~~~

Nhưng điều này **không bảo đảm semantic compatibility**. Nếu version B đổi ý nghĩa `amount` từ đơn vị cent sang VND, version A có thể đọc được JSON nhưng xử lý **sai tiền**. Nếu B dùng `paymentMethod` để quyết định nghiệp vụ quan trọng, A bỏ qua field có thể không được phép.

Một contract tốt phải kiểm:

- **Schema**: deserialize được không?
- **Semantics**: các field cũ còn cùng ý nghĩa không?
- **Validation**: version cũ có chấp nhận dữ liệu mới theo nghiệp vụ không?
- **Side effects**: xử lý bằng version cũ có an toàn không?
- **Tính toàn vẹn**: có giữ nguyên event ID và business key không?

## 7. Quy tắc tiến hóa schema cho khả năng rollback

Các lựa chọn thường có:

1. **Additive field**: thêm field mới có default/optional, không thay nghĩa field cũ.
2. **New event type**: chỉ phát sau khi tất cả consumer liên quan đã hỗ trợ.
3. **Dual read**: consumer mới đọc cả v1 và v2 trong thời gian chuyển tiếp.
4. **Dual write có kiểm soát**: nếu phải phát hai dạng, dùng idempotency và version phân biệt rõ; không tự phát duplicate business event.
5. **Schema registry policy**: chọn compatibility đúng định hướng rollback và test tất cả readers/writers liên quan.
6. **Deprecation window**: chỉ bỏ field cũ khi không còn consumer phụ thuộc, hết retention/replay window phù hợp.

~~~text
Release A:
  Consumer reads v1
  Producer writes v1

Release B phase 1:
  Consumer reads v1 + v2
  Producer still writes v1

Release B phase 2:
  Consumer reads v1 + v2
  Producer writes v2 only AFTER A rollback no longer needed
  OR old A has proven v2 compatibility
~~~

Điểm quyết định: nếu rollback tới A vẫn là yêu cầu bắt buộc, **không phát v2-only records mà A không đọc được**. Có thể giữ B ở chế độ backward-compatible qua feature flag cho đến khi cửa sổ rollback kết thúc.

### Khi schema đã thay đổi không tương thích

Một rollout undo image có thể không còn đủ. Bạn có thể phải:

- Tiếp tục chạy B và hotfix thay vì rollback A.
- Tạo compatibility adapter/consumer mới để đọc v2 rồi chuyển đổi hợp lệ.
- Tách topic versioned với migration plan và kiểm dữ liệu.
- Dừng phát v2, đánh giá những v2 records đã tồn tại và có phương án xử lý trước khi khôi phục A.

Không xóa records hoặc reset offsets tùy tiện để che lỗi schema.

## 8. Consumer group ID và offsets: điều cần giữ nguyên

Consumer group ID là **danh tính của vị trí đọc**. Với cùng group, committed offsets được lưu theo topic-partition.

~~~text
topic orders.events, partition 0

offset:      100  101  102  103  104  105
                \----- processed ----/
                         |
                  committed offset 104
                   (next record 104)
~~~

Trong Kafka, committed offset thường biểu thị **offset kế tiếp** consumer sẽ đọc. Nếu commit 104, record offset 104 có thể là record sẽ được đọc tiếp (tùy vị trí/flow). Đừng nhầm “đã commit tới 104” với “record 104 đã xử lý xong”.

Khi rollback A:

- Giữ nguyên `group.id` nếu muốn tiếp tục vị trí group hiện hành.
- Không đổi `auto.offset.reset` chỉ để khiến consumer chạy được.
- Không reset offset trừ khi có **quyết định replay/data repair được phê duyệt**.
- Kiểm group đã commit tới đâu và lag theo từng partition.
- Xác minh các offset còn đọc được trong retention của topic.

**Rollback image không kéo committed offset lùi về thời điểm trước deploy.**

### 8.1. Ví dụ một cửa sổ mất tính nguyên tử

~~~text
T1: B xử lý record offset 200
T2: B COMMIT thay đổi vào PostgreSQL
T3: Pod bị kill trước offset commit Kafka
T4: A được rollout và đọc lại offset 200
T5: A có thể ghi trùng side effect
~~~

Đây là đặc tính **at-least-once** thường gặp khi transaction database và commit offset Kafka không thuộc một transaction chung. Giải pháp là **idempotency ở tầng nghiệp vụ** và đối soát, không phải một lệnh `kubectl`.

### 8.2. Đổi group ID làm gì?

Giả sử release B vô tình đặt `group.id=orders-worker-v2`, trong khi A dùng `orders-worker-v1`. Hai group có offsets độc lập.

| Chính sách group mới | Rủi ro |
| --- | --- |
| `auto.offset.reset=earliest` | Có thể replay nhiều record cũ. |
| `auto.offset.reset=latest` | Có thể bỏ qua record đã có trước khi group tham gia. |
| `auto.offset.reset=none` | Consumer sẽ fail khi không có offset hợp lệ, giúp phát hiện cấu hình ngoài ý định. |

Do vậy, thay `group.id` là thay đổi **data-processing identity**. Nó cần kế hoạch migration/cutover riêng, không phải phương án sửa lỗi nhanh.

## 9. Bất biến nghiệp vụ: idempotent consumer

Để rollback chịu được redelivery, áp dụng khóa dedup ổn định theo **business event**.

Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders_projection (
    order_id VARCHAR(100) PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

Trong một transaction JDBC, ứng dụng thử insert event ID; chỉ áp dụng nghiệp vụ nếu insert thành công:

~~~java
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
    public void apply(OrderCreated event) {
        int inserted = jdbc.update(
            "INSERT INTO processed_events(event_id, order_id) " +
            "VALUES (?, ?) ON CONFLICT (event_id) DO NOTHING",
            event.eventId(), event.orderId());

        if (inserted == 0) {
            // Event đã được commit ở một lần xử lý trước.
            return;
        }

        jdbc.update(
            "INSERT INTO orders_projection(order_id, amount) " +
            "VALUES (?, ?) " +
            "ON CONFLICT (order_id) DO UPDATE SET amount=EXCLUDED.amount",
            event.orderId(), event.amount());
    }
}
~~~

Mẫu trên dành cho **PostgreSQL**; dialect SQL khác cần cú pháp tương ứng. `OrderCreated` là model nghiệp vụ do ứng dụng khai báo với accessor `eventId()`, `orderId()`, `amount()`.

Điều kiện quan trọng:

- Insert `processed_events` và update projection phải nằm **trong cùng transaction database**.
- Khóa `eventId` phải ổn định qua cả hai phiên bản A/B và qua retry/restart.
- Dedup theo event ID không giải quyết được các event **khác ID nhưng trùng cùng ý nghĩa nghiệp vụ**; cần thêm business constraints nếu bài toán yêu cầu.
- Upsert phải tương thích quy tắc version/order: nếu event đến sai thứ tự, cập nhật amount cuối có thể không đúng. Có thể cần sequence/version check.
- Gửi HTTP/email ngoài transaction vẫn cần cơ chế idempotency/outbox tương ứng.

### Listener Spring Kafka 3.x

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final OrderEventService service;

    public OrderConsumer(OrderEventService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "${app.kafka.orders-topic}",
        groupId = "${spring.kafka.consumer.group-id}")
    public void receive(String payload) throws Exception {
        // deserialize + validate bằng codec theo contract.
        OrderCreated event = parseAndValidate(payload);
        service.apply(event);
    }

    private OrderCreated parseAndValidate(String payload) {
        // Pseudocode ứng dụng: dùng ObjectMapper/serde có validation.
        throw new UnsupportedOperationException(
            "Implement schema-aware decoding");
    }
}
~~~

`parseAndValidate` là **điểm mở rộng minh họa**, không phải đoạn app runnable đầy đủ: cần implement decoder, validation và error handling trước khi triển khai. Không swallow exception trong listener rồi vẫn để container commit offset; lỗi cần được đưa qua error handler theo policy.

Với `AckMode.RECORD`, `enable.auto.commit=false` và container/error handler được cấu hình đúng, việc commit offset gắn với xử lý listener. Tuy nhiên **không có transaction ACID xuyên Kafka offset và PostgreSQL** chỉ từ lựa chọn ack mode.

## 10. Database migration: dùng expand–contract

Rollback rất dễ thất bại khi release B **xóa cột** mà A vẫn cần. Thiết kế migration hai giai đoạn:

~~~text
Release A
    |
    v
Migration EXPAND
  - thêm cột nullable/default
  - thêm index mới
  - giữ cột cũ
    |
    v
Release B
  - đọc được format cũ
  - dần viết format mới
  - tương thích schema expand
    |
    +----> Rollback A vẫn đọc/ghi được
    |
    v
Sau cửa sổ rollback
Migration CONTRACT
  - bỏ cột cũ, thay đổi constraint không tương thích
  - đây là thời điểm rollback về A có thể không còn an toàn
~~~

| Thay đổi DB | Phù hợp rollback A? | Lưu ý |
| --- | --- | --- |
| Thêm cột nullable | Thường có | A có thể bỏ qua cột mới. |
| Thêm index | Thường có | Cân nhắc thời gian tạo index, locks. |
| Thêm cột NOT NULL không có default | Có thể không | A INSERT thiếu cột sẽ lỗi. |
| Rename/xóa cột A đang đọc | Không | A không còn chạy được. |
| Đổi ý nghĩa field `amount` | Nguy hiểm | A đọc được nhưng tính sai. |
| Data backfill một chiều | Có điều kiện | Phải có đường đối soát/khôi phục nếu sai. |

**Rollback schema database không luôn là “chạy migration xuống”.** Nếu B đã ghi dữ liệu theo schema mới, down-migration có thể mất thông tin. Tốt hơn dùng expand–contract, feature flags và duy trì backward compatibility đến khi cửa sổ rollback kết thúc.

### Tương tác với schema registry

Schema của message và schema database là hai contract riêng. Việc giữ bảng DB tương thích **không** bảo đảm consumer A deserialize được message B. Phải test cả hai.

## 11. Retry, DLT và error handler khi quay về A

Trong Spring Kafka, các release có thể thay đổi:

- `DefaultErrorHandler`, số lần retry và `BackOff`.
- `DeadLetterPublishingRecoverer` và đích DLT.
- `@RetryableTopic` với retry topics và naming convention.
- Deserialization exception handling.
- Header, trace/context và format của DLT message.
- Acknowledgment/seek/commit behavior.

Một phiên bản mới có thể gửi event lỗi vào DLT kèm payload/headers mà **phiên bản cũ không hiểu**. Rollback A rồi tự động reprocess DLT có thể gặp poison-message loop.

### Luồng failure cần xét

~~~text
Source topic record
        |
        v
Release B consumer
        |
        +-- retry thành công --> DB side effect
        |
        +-- hết retry --> DLT (schema/headers mới)
                                  |
                             rollback A
                                  |
                                  v
                         A reprocess DLT?
                            compatible?
~~~

Để rollback an toàn:

1. Giữ DLT format tương thích hoặc có adapter.
2. Không tự replay toàn bộ DLT khi lỗi chính chưa được giải quyết.
3. Theo dõi DLT count/lag, phân loại error.
4. Kiểm không có message bị xử lý hai lần khi rollback giữa retry.
5. Có chính sách quarantine/parking cho các payload mà A không hiểu.
6. Đối soát idempotency key khi replay DLT.

Không cho rằng mọi error handler có cùng số retry attempts qua các phiên bản; test boundary theo đúng thư viện đang dùng.

## 12. Kafka transactions và producer transactional.id

Nếu ứng dụng dùng Kafka transactions hoặc consume-transform-produce với Exactly Once Semantics của Spring Kafka, rollback phải xem xét:

- Producer transaction được bắt đầu/commit/abort ở đâu.
- `transactional.id` prefix có ổn định và unique theo instance cần thiết không.
- Producer fencing khi một producer mới sử dụng cùng transactional.id.
- Transaction markers và bản tin chưa commit.
- Consumer `isolation.level=read_committed` khi cần.
- Side effects database ngoài Kafka transaction không tự được bảo vệ.

~~~text
Release B transactional producer
         |
         +-- Begin Kafka transaction
         +-- Produce output
         +-- Commit offsets in transaction
         |
       (Pod shutdown)
         |
         v
Release A producer comes up
  transaction identity/epoch rules apply
  unfinished transactions must be resolved
~~~

Không tự chọn lại `transactional.id` tùy ý nhằm “khắc phục” fencing; có thể khiến hai producer hoạt động song song và làm hỏng assumptions của EOS. Đồng thời, không tái sử dụng **cùng một transactional.id** giữa hai instance hoạt động đồng thời.

Khi cần rollback transactional apps, sử dụng khả năng lifecycle/fencing do Spring Kafka và Kafka client của phiên bản tương thích cung cấp, dừng instances cũ đúng cách và test rolling overlap. Các chi tiết chính xác của EOS mode và factory configuration cần theo tài liệu phiên bản Spring Kafka/Broker được chọn.

## 13. Kafka Streams: rollback còn liên quan state stores

Kafka Streams khác record listener thông thường vì ứng dụng có thể lưu **local state stores** và dùng **changelog topics** để khôi phục.

Ví dụ:

~~~text
orders.events
     |
     v
Kafka Streams topology
     |
     +-- aggregate by account
     |
     v
RocksDB local state
     |
     v
Changelog topic + checkpoint
```

Nếu release B thay topology, SerDe hoặc định dạng state store, bản A có thể không đọc được state đã được B ghi. Rollback image có thể fail hoặc tạo state không nhất quán.

Trước khi nâng cấp một Streams app:

- Kiểm topology/state-store names và backward compatibility của SerDe.
- Đánh giá thay đổi Kafka Streams DSL và processor API.
- Nếu có state migration, dùng quy trình được tài liệu Kafka Streams hỗ trợ.
- Giữ bản snapshot/backup, retention và dữ liệu nguồn cần rebuild.
- Không xóa state directory/changelog topic trong production như một thao tác đầu tiên.
- Cân nhắc chạy topology mới cạnh topology cũ với application.id khác để so sánh output, nhưng phải bảo đảm **không phát side effect trùng**.
- Dùng `application.id` cẩn thận: đổi nó ảnh hưởng group identity, internal topics và state, không phải chỉ đổi tên ứng dụng.

**Rollback Kafka Streams có thể cần kế hoạch state migration ngược hoặc rebuild từ input immutable**, không chỉ rolling update.

## 14. Broker downgrade khác hoàn toàn app rollback

Một lệnh rollback Deployment Java **không** đưa Kafka broker về version cũ. Broker upgrade có thể thay đổi:

- Metadata format và cluster feature level.
- Inter-broker protocol hoặc cách broker sử dụng feature flags.
- Raft/KRaft controller metadata, tùy phiên bản/cấu hình cluster.
- Log/message format, feature activation.
- Client/broker protocol compatibility windows.
- Quá trình di chuyển metadata/topic/ACL.

Không tự downgrade broker chỉ vì Spring Kafka consumer mới lỗi. Trước tiên xác định đây là **app regression**, **client compatibility** hay **broker incident**.

Đối với broker:

1. Đọc upgrade/downgrade documentation đúng **từ version X sang version Y**.
2. Kiểm metadata/feature levels và xem có đường downgrade được hỗ trợ hay không.
3. Có backup, capacity và quy trình cluster health.
4. Thử nghiệm trước trong môi trường giống production.
5. Chỉ triển khai qua runbook của đội sở hữu Kafka infrastructure.

Nếu Kafka đã nâng feature level đến mức không thể quay về, một yêu cầu “downgrade ngay” có thể **không an toàn hoặc không được hỗ trợ**. Lúc đó phải dùng forward-fix hoặc khôi phục theo kế hoạch disaster recovery riêng, không thử một lệnh ngẫu nhiên.

## 15. Chiến lược rollout để rollback thật sự có tác dụng

### 15.1. Rolling deployment

~~~text
T0: A A A
T1: A A B
T2: A B B
T3: B B B

Rollback:
T4: A B B
T5: A A B
T6: A A A
~~~

Trong cửa sổ overlap, A và B phải xử lý tương thích cùng topic/group và side effects. Những lỗi chỉ xuất hiện khi A và B cùng chạy cũng cần được test.

### 15.2. Canary một Pod

Một Pod B có thể được chạy trước để quan sát metrics. Nhưng với Kafka consumer group, một canary trong cùng group **không nhận theo phần trăm traffic HTTP cố định**. Nó chỉ nhận các partition được Kafka coordinator phân công.

Nếu topic chỉ có một partition, canary có thể được gán toàn bộ partition hoặc không có partition nào. Vì vậy đừng tuyên bố “1 Pod canary = 10% Kafka traffic”. Cần theo dõi partition assignment và volume thật.

### 15.3. Shadow consumer

Một consumer B dùng **group ID khác** có thể đọc bản sao logic của event stream để so sánh kết quả mà không chặn group A. Nhưng nó cũng có offsets riêng và có thể đọc toàn bộ backlog; phải:

- Đặt shadow B ở chế độ **read-only hoặc side effects cách ly**.
- Đảm bảo không gửi request thanh toán/email/DB mutation thật.
- Có giới hạn throughput và quyền truy cập phù hợp.
- Không nhầm trạng thái shadow group với committed offsets của production group.

Shadow giúp kiểm schema và logic, nhưng không thay thế canary/rollback test khi B nhận partition thật của group production.

## 16. Kubernetes rollout history và giới hạn của `rollout undo`

Giả sử Deployment tên `orders-worker` trong namespace `production`.

### 16.1. Quan sát trước khi can thiệp

~~~bash
kubectl get deployment orders-worker -n production
kubectl rollout history deployment/orders-worker -n production
kubectl rollout status deployment/orders-worker -n production
kubectl get pods -n production -l app=orders-worker
~~~

Đọc output để biết revision, image và số Pod Ready. Lưu ý Deployment revision chủ yếu phản ánh **Pod template**, không phải một snapshot đầy đủ của database, offsets, ConfigMap và Secret.

### 16.2. Rollback image/Pod template

~~~bash
# Chỉ sau khi đã quyết định rollback theo runbook:
kubectl rollout undo deployment/orders-worker -n production

# Theo dõi kết quả Pod rollout:
kubectl rollout status deployment/orders-worker -n production
~~~

Có thể chọn revision rõ ràng:

~~~bash
kubectl rollout undo deployment/orders-worker \
    -n production --to-revision=12
~~~

**Những lệnh trên chỉ là ví dụ tài liệu, không được thực thi trong bài học.** Phải kiểm revision 12 chứa image/config reference gì trước khi áp dụng. Khi dùng GitOps, controller có thể tự đưa Deployment trở lại trạng thái Git mong muốn; do đó rollback cần đồng bộ với source-of-truth GitOps.

### 16.3. ConfigMap/Secret có rollback theo không?

Không tự động. Nếu Pod template vẫn reference `orders-config` với tên không đổi, nội dung ConfigMap hiện tại có thể vẫn là bản B, kể cả khi image đã quay về A. Tương tự Secret được rotate có thể không còn phù hợp với client A.

Cần khôi phục **cặp image + config version tương thích**, gồm:

- Kafka `bootstrap-servers`, topic names và `group-id`.
- Serializer/deserializer classes và schema version references.
- SASL/TLS settings hoặc secret versions.
- Listener concurrency, ack mode, retry/DLT policies.
- Feature flags và database migration compatibility.

Trong GitOps/Helm, pin một commit/release có toàn bộ non-secret values; secret vẫn có lifecycle riêng và rotation policy.

## 17. Quiesce consumer và xử lý in-flight work

Một rollback nhạy cảm có thể yêu cầu **tạm ngừng nhận message mới** để giảm số side effects đang phát sinh, nhưng tránh giết Pod đột ngột.

Mục tiêu quiesce:

1. Không giao thêm việc mới cho phiên bản lỗi ngoài ý định.
2. Cho record đang xử lý hoàn tất/rollback theo policy.
3. Đảm bảo container/producer flush và ack/transaction lifecycle phù hợp.
4. Quan sát consumer group rebalance và committed offsets.
5. Bắt đầu A ở trạng thái đã xác minh và tiếp tục xử lý.

Spring Kafka hỗ trợ quản lý listener containers (pause/resume/stop) qua `KafkaListenerEndpointRegistry` hoặc API container tương ứng. Ví dụ khái niệm:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

public final class ConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        if (container == null) {
            throw new IllegalArgumentException("Unknown listener");
        }
        container.pause();
    }

    public void resume(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        if (container == null) {
            throw new IllegalArgumentException("Unknown listener");
        }
        container.resume();
    }
}
~~~

Ví dụ này giả định ứng dụng đã khai báo `@KafkaListener(id="ordersListener", ...)` và có API điều hành được bảo vệ để gọi control. `pause()`/`resume()` có semantics không hoàn toàn tức thời; phải theo dõi trạng thái container/assignment thật. Không mở endpoint pause/resume công khai hoặc dùng thao tác thủ công thiếu audit.

Một lệnh `kubectl scale deployment --replicas=0` có thể khiến consumer ngừng nhưng **không bảo đảm mọi record/transaction đã hoàn tất đúng**. Muốn đảm bảo graceful shutdown, cần cấu hình termination grace period, listener stop và producer close phù hợp; sau đó đối soát.

## 18. Observability: xác định có nên rollback không

Đừng chỉ dùng liveness/readiness hoặc CPU để đánh giá. Một Pod có thể Ready nhưng consumer không nhận record do lỗi group authorization.

Các tín hiệu nên theo dõi:

| Tín hiệu | Nguồn | Câu hỏi |
| --- | --- | --- |
| Consumer lag theo group/topic/partition | Kafka metrics/exporter | Backlog có tăng sau deploy? |
| Records consumed/s | Kafka client metrics | Có xử lý được record? |
| Listener failure/retry rate | Application metrics | Lỗi nghiệp vụ tăng? |
| DLT volume/rate | DLT topic và app metrics | Record bị parking nhiều hơn? |
| Commit latency/rebalance | Kafka client metrics | Consumer có bị thu hồi partition? |
| Producer send errors/latency | Producer metrics | Kết quả gửi có được broker ACK? |
| DB duplicate/idempotency conflicts | Business metrics/audit | Có side effect trùng? |
| Business totals/checksum | Application DB/audit | Có thiếu/sai dữ liệu? |
| Version label | Deployment/observability | Metric thuộc release nào? |
| Authentication/ACL failures | Kafka client logs/metrics | Config/security có sai không? |

Các tên metric chính xác thay đổi tùy Spring Kafka, Micrometer, Kafka client và exporter. Đừng hard-code PromQL cho một metric chưa được xác nhận đang có ở môi trường thực.

### Canary success criteria mẫu

~~~text
Trong cửa sổ quan sát đã định:
- Consumer có partition assignment thực tế.
- Error rate không tăng quá ngưỡng đã thống nhất.
- Consumer lag không tăng liên tục do lỗi xử lý.
- DLT không có nhóm lỗi mới.
- Producer send failures không tăng.
- Không có record nghiệp vụ bị mất/trùng ngoài semantics.
- DB migration/serializer tương thích với A.
- Có đường rollback A đã test.
~~~

Một canary không nhận record nào thì **chưa đủ bằng chứng** để tăng rollout, dù Pod Healthy và metrics error bằng 0.

## 19. Checklist quyết định rollback

| Hạng mục | Câu hỏi chốt |
| --- | --- |
| Release artifact | Image A còn trong registry, digest đã xác nhận? |
| Config | A có chạy được với cấu hình hiện tại hay cần revert values/secret? |
| Schema | A đọc được record do B đã phát? |
| Kafka offsets | Giữ đúng group ID, hiểu committed positions, không reset tùy tiện? |
| Database | Schema chưa contract phá A? Dữ liệu do B viết tương thích? |
| Side effects | Đã có idempotency hoặc kế hoạch đối soát? |
| Retry/DLT | A hiểu payload trên retry/DLT topics và có cách parking? |
| Kafka transactions | Transactional ID/prefix/fencing và shutdown đã được kiểm? |
| Streams | State/changelog/topology của B có đọc được bởi A? |
| Infra | Broker version/protocol/ACL vẫn tương thích? |
| Monitoring | Có số liệu trước/sau và release marker? |
| Freeze | Có cần dừng producer hoặc pause consumer để giữ hợp đồng dữ liệu? |
| Rollback authority | Ai được phép quyết định và ai sở hữu dữ liệu? |
| Validation | Có integration/canary recovery test? |

Nếu không chắc A xử lý được message đã phát từ B, đừng rollback A chỉ vì đó là hành động nhanh nhất. Có thể cần **roll forward** bằng bản hotfix tương thích để tránh làm hỏng dữ liệu.

## 20. Runbook thực tế: ứng dụng consumer lỗi sau deploy

Giả sử A ổn định, B gây lỗi deserialization và DLT rate tăng.

### Giai đoạn A — Triage

1. Ghi release revision, timestamp, image digest và commit config.
2. Xác minh group/topic/cluster không bị thay đổi ngoài ý định.
3. Tìm record/sample **đã loại bỏ secret/PII** gây lỗi.
4. Kiểm B đã phát loại event/schema mới chưa.
5. Xác định phạm vi database mutation và DLT records.
6. Kiểm A có thể xử lý record hiện còn chờ và những record B tạo ra.

### Giai đoạn B — Containment

1. Nếu producer B đang phát schema không tương thích, dùng feature flag hoặc kế hoạch tạm dừng để ngăn phát thêm.
2. Nếu consumer B đang ghi sai dữ liệu, pause/stop theo runbook; kiểm in-flight work.
3. Giữ nguyên dữ liệu và offset, không xóa topic/DLT để “làm sạch”.
4. Lưu snapshot/audit/metrics cần đối soát.
5. Chốt A image và config phiên bản tương ứng.

### Giai đoạn C — Rollback

1. Revert GitOps/Helm values hoặc xác nhận Deployment revision chứa đúng A.
2. Khôi phục **cấu hình không nhạy cảm** và secret reference tương thích, không đưa credential cũ đã bị thu hồi trở lại.
3. Rollout A theo chiến lược đã test, theo dõi readiness và Kafka assignment.
4. Xác minh A không gặp deserialization failure với backlog hiện tại.
5. Theo dõi retry/DLT, consumer lag và throughput.

### Giai đoạn D — Verify dữ liệu

1. Đối soát event IDs theo kỳ nghiệp vụ.
2. Kiểm duplicate business side effects và idempotency audit.
3. Kiểm records trên DLT có cần repair/replay.
4. Kiểm số record chưa xử lý theo lag và output count.
5. Chốt incident status; chỉ mở lại producer/các luồng đang freeze khi đã kiểm xong.

### Giai đoạn E — Prevention

1. Bổ sung contract test A đọc được payload B tạo.
2. Cập nhật upgrade plan/data migration.
3. Ghi lại thay đổi group ID/config/feature flag nếu có.
4. Tăng observability và khả năng quiesce.
5. Ghi runbook cho chính lớp sự cố đã xảy ra.

## 21. Kiểm thử compatibility bằng producer B và consumer A

Một test hiệu quả là cho code/schema **mới phát record**, rồi bắt phiên bản **cũ đọc** nó.

~~~text
Test fixture:
  B serializer -> Kafka topic test -> A deserializer

Expect:
  A parse success
  A validation success
  A business output correct
  A no extra/duplicate side effects
~~~

Nếu không dễ chạy hai binary trong cùng JVM, dùng hai process/container image khác nhau với một Kafka broker test, hoặc lưu **golden payloads** được producer B tạo ra và dùng contract test bên A.

### Golden payload tests

~~~java
// Pseudocode minh họa contract test, không phụ thuộc format cố định.
byte[] producedByB = loadFixture("order-created-v2.bin");

OrderEvent event = decoderFromReleaseA.decode(producedByB);

assertEquals("evt-1002", event.eventId());
assertEquals("order-502", event.orderId());
assertEquals(2300L, event.amount());
~~~

Với Avro/Protobuf/JSON Schema, phải đi qua **serializer và deserializer thật**, versioned schema/reference đúng, không chỉ JSON parse thủ công rồi coi là tương thích.

Nên test thêm:

- B đọc event A.
- A đọc event B khi rollback được yêu cầu.
- A xử lý error headers/DLT do B tạo ra.
- Schema Registry compatibility theo subject/format phù hợp.
- Unknown fields, default, enum mới, field type và semantic units.
- Event được ghi trước, trong và sau cửa sổ overlap.

## 22. Integration test rollback bằng Testcontainers

Testcontainers Kafka + PostgreSQL có thể dựng một kịch bản end-to-end cách ly:

~~~text
Kafka test broker + PostgreSQL test DB
            |
            v
Seed records v1
            |
            v
Start consumer A
  assert output + committed offsets
            |
            v
Stop A gracefully
            |
            v
Start consumer B
  produce/consume v1,v2 theo contract
            |
            v
Stop B gracefully hoặc inject crash
            |
            v
Start A with SAME group.id
            |
            v
Assert:
  A can read remaining messages
  no duplicate rows/side effects
  offsets progress as expected
  DLT/retry semantics match policy
~~~

Mỗi phiên bản nên được chạy từ artifact tương ứng thay vì chỉ đổi một feature flag trong cùng code nếu mục tiêu là kiểm **binary compatibility**. Testcontainers Kafka broker dùng image phù hợp và API theo version Testcontainers đã pin.

### Ma trận test theo loại lỗi

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Canary B tiêu thụ thành công | B có assignment và output đúng, không chỉ Pod Ready. |
| B phát schema additive | A deserialize, validate và xử lý được. |
| B phát enum mới | A không xử lý sai hoặc có fallback được duyệt. |
| B commit DB rồi crash trước offset commit | A redelivery không tạo duplicate. |
| B thay retry policy | DLT và retry topics không bị kẹt khi A quay lại. |
| B đổi group ID | Test phát hiện identity/offset khác, không coi là rollback. |
| Database đã expand schema | A vẫn ghi/đọc đúng với schema mới. |
| Database đã contract xóa cột | Test chặn rollback A hoặc yêu cầu alternative plan. |
| Producer B gửi uncommitted Kafka transaction | A theo isolation policy không xử lý dữ liệu chưa commit. |
| Secret rotate từ A sang B | A binary dùng được credential hiện hành hoặc có kế hoạch tương thích. |
| Rollback giữa rebalance | Không mất dữ liệu; kiểm idempotency. |
| Kafka Streams topology đổi | Có test state/changelog compatible hoặc migration riêng. |

## 23. Quan sát offsets không đồng nghĩa tự reset offsets

Khi cần điều tra consumer lag hoặc position, có thể dùng Kafka CLI trên môi trường được cấp quyền.

~~~bash
# Cú pháp minh họa khi có Kafka CLI và auth config phù hợp:
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9093 \
  --command-config client.properties \
  --group orders-worker-v1 \
  --describe
~~~

`client.properties` cần được cấp qua secret manager hoặc file an toàn; không in JAAS/password trong log hoặc command-line args.

Lệnh `--describe` giúp xem committed offset, end offset, lag và membership theo tùy bản Kafka CLI. Đây là **quan sát**, không đổi offsets.

**Không chạy `--reset-offsets --execute` làm bước rollback mặc định.** Reset offsets có thể replay một khối dữ liệu lớn hoặc bỏ qua records; nó phải đi kèm kế hoạch data repair, idempotency, maintenance window, preview và approval riêng.

Nếu offset cần được thay đổi vì sự cố dữ liệu, cần ngăn consumer group đang xử lý, chốt topic-partition-offset, kiểm retention và đối soát output; bản thân việc reset không hoàn tác transaction đã commit.

## 24. Tại sao config rollback phải đi kèm image rollback?

Giả sử B bổ sung:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-worker-v2
    properties:
      isolation.level: read_committed
app:
  kafka:
    orders-topic: orders.events.v2
~~~

Quay image về A nhưng vẫn dùng config này có thể khiến A:

- Tiếp tục đọc từ group v2 không có offsets của A.
- Đọc topic v2 với schema mà A không hỗ trợ.
- Nhận lượng data khác kỳ vọng hoặc không đọc được record nào.
- Dùng TLS/SASL config/secret mà dependency cũ không hỗ trợ.

Vì vậy image + config phải được xem là **một đơn vị phát hành**. Khi dùng Helm, không dựa vào `helm rollback` để kết luận dữ liệu/Kafka offsets cũng đã được revert; Helm chỉ quản lý những resource của release, và các state nằm ngoài manifest vẫn còn.

Feature flags phải có quy trình rollback riêng. Một flag B đổi default true trong config service có thể tiếp tục bật khi binary A trở lại.

## 25. Khi nào chọn roll forward thay vì rollback?

Không phải lỗi nào cũng nên rollback:

| Tình huống | Hướng tiếp cận thường an toàn hơn |
| --- | --- |
| B có bug Java nhưng schema/data giữ tương thích A | Rollback A có thể phù hợp. |
| B đã phát event không đọc được bởi A | Hotfix B hoặc compatibility adapter; chưa rollback A ngay. |
| Database contract đã xóa cột A cần | Roll forward/hotfix hoặc migration khôi phục được kiểm chứng. |
| Kafka Streams state đã đổi format | Có thể cần forward-fix hoặc state migration riêng. |
| Credential cũ đã bị revoke | Giữ credential mới và bảo đảm A tương thích, không phục hồi secret bị thu hồi. |
| Broker cluster đã bật feature level mới không hỗ trợ downgrade | Không hạ broker bừa; đánh giá forward-fix/DR. |
| Dữ liệu nghiệp vụ B đã ghi sai | Containment và data repair riêng; image rollback không sửa dữ liệu đã sai. |

**Rollback là lựa chọn có điều kiện**, không phải phản xạ áp dụng mọi lỗi production.

## 26. Lưu ý bảo mật khi rollback

Khi điều tra sự cố phiên bản:

- Không copy JAAS password, token hoặc TLS private key vào ticket/log.
- Không bật debug dump toàn bộ Spring Environment/Kafka Properties.
- Không rollback secret thành credential đã bị revoke hoặc nghi ngờ lộ.
- Giới hạn quyền thao tác Kubernetes Deployment, group offsets, topic ACL.
- Audit ai đã quyết định rollback, revision nào, lúc nào và thay đổi gì.
- Bảo vệ golden payloads và production samples có dữ liệu cá nhân.
- Không dùng token trong Prometheus labels; dùng release version, group, topic và error category phù hợp cardinality.
- Đảm bảo các lệnh quan sát Kafka dùng cấu hình auth được cấp an toàn.

Một cách triển khai tốt cần cả **reliability** và **security**: sửa outage bằng cách tắt TLS hoặc cấp quyền Cluster All thường chỉ tạo một sự cố mới nghiêm trọng hơn.

## 27. Các sai lầm thường gặp

**1. “Rollback image là quay về toàn bộ trạng thái trước deploy.”** Sai: DB, Kafka offsets, topics, Schema Registry và external side effects còn nguyên.

**2. “Đổi group ID để bỏ consumer lag.”** Sai: tạo consumer identity khác; có thể replay hoặc bỏ backlog.

**3. “Reset offset để dữ liệu đúng lại.”** Sai: reset không hoàn tác side effect, dễ gây duplicate/loss.

**4. “B đọc được event A, vậy A chắc chắn đọc được event B.”** Sai: backward compatibility không đồng nghĩa forward compatibility.

**5. “Serializer parse thành công tức schema an toàn.”** Sai: field semantics, required validation và business rules có thể thay đổi.

**6. “Mọi migration DB đều có down script.”** Data đã được B ghi có thể không tương thích A; down-migration có thể mất dữ liệu.

**7. “Một canary Pod nghĩa là 10% Kafka traffic.”** Không đúng với partition assignment của Kafka consumer group.

**8. “Rollback ConfigMap/Secret cũng được Kubernetes Deployment revision quản lý.”** Không tự động.

**9. “DLT của release B chắc chắn A đọc được.”** Headers/payload, serializer hoặc retry topic names có thể thay đổi.

**10. “acks=all + idempotence giải quyết database duplicate.”** Producer idempotence không thay thế application idempotency.

**11. “Stop Pod cưỡng bức là đã kết thúc transaction.”** In-flight work và commit phải được đối soát.

**12. “Có thể downgrade Kafka broker giống như roll back consumer JAR.”** Broker metadata/feature level có giới hạn hỗ trợ riêng.

**13. “Kafka Streams state luôn đọc ngược được.”** Đổi topology/serde/changelog có thể làm bản cũ không phục hồi được.

**14. “Readiness xanh nên không cần rollback.”** Business output có thể sai dù Pod Ready.

**15. “Triển khai lại A sau B rồi chỉ kiểm exit code.”** Test phải kiểm record IDs, output totals, idempotency, lag và DLT.

## 28. Bài tập thực hành

### Bài 1 — Tách rollback app với rollback dữ liệu

Mô tả release A/B của một Kafka consumer có PostgreSQL. Liệt kê những thành phần Kubernetes Deployment rollback được và những thành phần không thể tự hoàn tác. Thiết kế bảng release manifest gồm image digest, config, schema và DB revision.

### Bài 2 — Old consumer đọc new payload

Tạo hai DTO/serde v1/v2, thêm một trường optional trong v2. Cho v2 serializer tạo event, dùng v1 deserializer đọc. Sau đó đổi ý nghĩa `amount` nhưng giữ kiểu số và chứng minh parser thành công chưa đủ để bảo đảm nghiệp vụ đúng.

### Bài 3 — Crash sau DB commit

Trong Testcontainers Kafka/PostgreSQL, xử lý event E1 và commit database, sau đó mô phỏng crash trước Kafka offset commit. Khởi động lại consumer cùng group và xác minh event E1 được redeliver nhưng business side effect chỉ xuất hiện một lần.

### Bài 4 — Group ID drift

Thử consumer group v1 và v2 trong broker test. So sánh committed offsets và hành vi khi dùng `earliest`, `latest` hoặc `none`. Giải thích tại sao rollback binary cần giữ identity của group đúng.

### Bài 5 — Expand–contract DB

Cho A ghi bảng `orders(id, amount)`. Thêm cột `currency` nullable/default rồi triển khai B. Test A vẫn chạy sau khi B ghi dữ liệu hợp lệ. Tiếp đó xóa cột A cần dùng trong test để chứng minh contract phá rollback.

### Bài 6 — DLT compatibility

Cho B dùng một header và schema mới trên DLT. Viết test A reprocess DLT hoặc parking an toàn. Không tự chuyển tất cả DLT records vào source topic mà chưa có idempotency/replay plan.

### Bài 7 — Canary phân vùng

Tạo Kafka topic 3 partitions, A có 2 consumers, B canary có 1 consumer trong cùng group. Quan sát assignment trước/sau rebalance và chứng minh B không nhận một phần trăm traffic cố định.

### Bài 8 — Kafka Streams state

Xây hai topology với state store/SerDe khác nhau trong môi trường test, mô phỏng nâng cấp rồi khởi động bản cũ. Ghi lại điều kiện cần migration hoặc rebuild; không xóa changelog/state trên production.

### Bài 9 — Runbook Kubernetes

Trong namespace test, triển khai A, rollout B rồi quay về A bằng `kubectl rollout undo`. Chứng minh ConfigMap và dữ liệu DB vẫn giữ giá trị đã thay đổi nếu không rollback riêng. Kiểm output sau hai lần rollout.

### Bài 10 — Disaster drill

Mô phỏng release B tạo event v2 không tương thích A. Quyết định dừng producer, rollback, hotfix hay adapter; ghi lý do, data impact, cách đối soát và tiêu chí mở lại traffic.

## 29. Tài liệu tham khảo chính thức

- [Spring Kafka — Reference](https://docs.spring.io/spring-kafka/reference/)
- [Spring Kafka — Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka — Non-blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/)
- [Apache Kafka — Upgrade and Compatibility](https://kafka.apache.org/documentation/#upgrade)
- [Apache Kafka — Kafka Streams Developer Guide](https://kafka.apache.org/documentation/streams/)
- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Kubernetes — Deployments and Rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)

