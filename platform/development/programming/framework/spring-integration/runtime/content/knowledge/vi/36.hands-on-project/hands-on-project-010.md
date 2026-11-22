# Hồ sơ hoàn chỉnh: topology, lifecycle, state, recovery và vận hành

Một flow Spring Integration không thể được xem là **sẵn sàng vận hành** chỉ vì chạy đúng với một message trên máy cá nhân. Trong production, nó còn phải trả lời được: message đang ở channel nào, khi nào được coi là đã nhận, lỗi ở worker sẽ đi đâu, state nào cần giữ qua restart, ai được quyền stop flow, và làm thế nào chứng minh không làm mất hoặc xử lý trùng dữ liệu trong một sự cố.

Đây là bài **Thực hành tổng hợp** của module **SPRING_INTEGRATION_RUNTIME**. Ta xây dựng **một hồ sơ thiết kế và nghiệm thu hoàn chỉnh** cho hệ thống nhận sự kiện đơn hàng, xử lý bằng consumer/poller, lưu trạng thái bền vững, điều khiển lifecycle, retry/recovery, correlation và vận hành. Bài kết nối trực tiếp các chủ đề channel, endpoint, executor, transaction, message store, error handling, observability, performance và testing. Mã ví dụ hướng đến **Java 17+, Spring Integration 6.5.x, Spring Framework 6.x và PostgreSQL**; phiên bản dependency thực tế phải được khóa nhất quán bằng BOM của dự án.

> **Tiêu chuẩn thành công:** Một message có thể được *accepted*, *processed*, *committed*, *acknowledged* và *published* tại **những thời điểm khác nhau**. Hồ sơ chỉ đạt yêu cầu khi nêu rõ mốc nào là thành công của từng API, đồng thời có test chứng minh đường phục hồi trong trường hợp process chết hoặc dependency không đáp ứng.

## 1. Bài toán và phạm vi dự án

Một dịch vụ **Order Intake Runtime** nhận sự kiện `OrderEvent` từ HTTP gateway hoặc message broker. Dịch vụ cần ghi nhận event một cách đáng tin cậy, xử lý trạng thái đơn hàng trong PostgreSQL và tạo một outbox record để hệ thống khác nhận kết quả.

Giả định nghiệp vụ:

1. Một `eventId` định danh một **logical event**; producer có thể gửi lại cùng event do timeout hoặc redelivery.
2. Một event thuộc `tenantId` và `orderId`; thứ tự các event trên cùng order có thể quan trọng nhưng không được giả định tự động bởi mọi channel.
3. Chỉ trả `202 Accepted` cho HTTP client **sau khi event đã được ghi bền vững** ở một điểm nhận được thiết kế rõ. Nếu không ghi được, caller phải biết để retry.
4. Khi xử lý thành công, trạng thái order và outbox record phải commit trong cùng một database transaction.
5. Lỗi tạm thời được thử lại có giới hạn; dữ liệu sai cố định được đưa vào quarantine/DLQ, không retry vô hạn.
6. Shutdown hoặc rolling deploy không được mặc nhiên xóa queue hay làm mất event đã nhận.
7. Hệ thống phải công bố được topology, lifecycle state, backlog, error/retry, message correlation và các bước recovery.

**Không nằm trong phạm vi bảo đảm:** Exactly-once end-to-end giữa PostgreSQL và remote HTTP/broker. Ta dùng **at-least-once delivery ở những biên phù hợp + idempotent business transaction + outbox/reconciliation**. Nếu một remote consumer không hỗ trợ idempotency, không thể hứa exactly-once chỉ bằng một annotation Spring.

### Hồ sơ bàn giao cần có

| Artifact trong hồ sơ | Câu hỏi phải trả lời |
|---|---|
| Topology manifest + sơ đồ | Message đi qua component và thread nào? |
| Contract đầu vào/đầu ra | Accepted, completed, failed nghĩa là gì? |
| State inventory + DDL | State nào nằm trong heap, JDBC store, bảng nghiệp vụ, DLQ? |
| Lifecycle state machine | Khi nào mở ingress, khi nào drain và stop? |
| Recovery matrix | Crash/rollback/retry dẫn tới phát lại hay mất message? |
| Java DSL + service idempotent | Các endpoint, queue, poller và transaction được wire ra sao? |
| Test evidence | Test nào chứng minh behavior sync/async và sau restart? |
| Dashboard, alert, runbook | On-call khoanh vùng queue đầy, executor reject, error spike thế nào? |
| ADR + danh sách rủi ro | Vì sao chọn những trade-off hiện tại và giới hạn là gì? |

Toàn bộ hồ sơ được mô tả ngay trong bài. Tên file/code block là **bản thiết kế để áp dụng vào dự án**, không phải khẳng định đã tạo thêm file hoặc đã chạy build trong workspace này.

## 2. Các bất biến phải giữ trong toàn bộ flow

Một hồ sơ dễ nghiệm thu hơn khi bắt đầu bằng **invariants** thay vì danh sách công nghệ:

| Mã | Invariant | Bằng chứng |
|---|---|---|
| INV-01 | Một business event ID được apply vào business DB tối đa một lần | Unique constraint + test duplicate/redelivery |
| INV-02 | Trả accepted cho HTTP sau khi durable intake commit, không trước đó | Test commit/rollback và status của API |
| INV-03 | Poller transactional xử lý một logical event trong một transaction nhất quán khi cùng DataSource | Test rollback của message receive và business write |
| INV-04 | Không ACK/mark completed nếu chưa đạt terminal outcome đã định nghĩa | Adapter test + DB/outbox reconciliation |
| INV-05 | Mọi retry có giới hạn; poison event có quarantine và owner | Test exhaustion, DLQ metadata, runbook |
| INV-06 | Ingress đóng trước khi stop consumer, work đã nhận được drain hoặc có recovery path | Lifecycle/race tests |
| INV-07 | Stop một flow/tenant không destroy resource shared | Ownership map + test nhiều tenant |
| INV-08 | Crash không xóa state đã lưu bền vững; startup không tự replay event đã terminal | Restart test dùng lại database |
| INV-09 | Correlation và tracing là các định danh khác nhau; không dùng raw event ID làm metric tag | Contract headers + metric validation |
| INV-10 | Operator có dashboard/alert để phân biệt queue, worker và downstream bottleneck | Runbook drill/metrics |

`INV-03` **chỉ đúng** nếu polling, `JdbcChannelMessageStore` và business write thực sự tham gia **cùng** JDBC transaction manager/DataSource, exception không bị recoverer nuốt trước commit và không có async handoff cắt transaction. Hồ sơ sẽ chỉ ra ranh giới này tường minh.

## 3. Topology tổng thể

~~~mermaid
flowchart LR
    subgraph ING["Ingress"]
      H["HTTP / Broker adapter"]
      G["Admission gate + validation"]
    end
    subgraph SI["Spring Integration runtime"]
      Q["orders.pending<br/>QueueChannel / JDBC store"]
      P["orders.worker<br/>PollingConsumer + TX advice"]
      V["OrderProcessor<br/>idempotency + business write"]
      E["errorChannel<br/>ErrorMessage"]
    end
    subgraph DB["PostgreSQL"]
      S["INT_CHANNEL_MESSAGE<br/>durable pending state"]
      I["processed_events<br/>unique eventId"]
      O["orders + outbox_events"]
      D["quarantine / replay ledger"]
    end
    R["Outbox relay"] --> X["External broker/API"]
    H --> G --> Q
    Q <--> S
    Q --> P --> V
    V --> I
    V --> O
    O --> R
    P -. "exception / ErrorMessage" .-> E
    E -. "diagnostic / recovery" .-> D
~~~

Các đường nét đứt mô tả **cơ chế quan sát/recovery**, không phải lời hứa rằng mỗi lỗi đều tự được Spring Integration đẩy sang cùng một `errorChannel`.

### Manifest component: tên bean là hợp đồng vận hành

| Bean/ID đề xuất | Loại | Thread | State | Lifecycle owner | Khi lỗi |
|---|---|---|---|---|---|
| `orders.admission` | API/gate do ứng dụng định nghĩa | HTTP/broker listener | Gate OPEN/CLOSED, không bền vững | Application ingress | Không nhận mới; caller retry/NACK |
| `orders.pending` | `QueueChannel` backed by `MessageGroupQueue` | Sender enqueue; poller dequeue | `JdbcChannelMessageStore` | Application context | JDBC fail hoặc queue wait; không coi send thành công nếu TX fail |
| `orders.worker` | `PollingConsumer` | Scheduler/poller thread | Lifecycle running + in-flight | Spring context | TX rollback/recovery policy |
| `orders.processor` | Service activator/handler | Cùng poller thread ở thiết kế chính | Bảng business/inbox/outbox | Spring bean | Runtime exception phải dẫn tới rollback hoặc recovery được ghi bền vững |
| `orders.outbox.relay` | Worker/flow riêng | Scheduler/worker riêng | `outbox_events` | Outbox service | Retry publish; at-least-once |
| `errorChannel` | Error publish/subscribe | Theo thread/error publisher | `ErrorMessage` không mặc định bền vững | Application context | Logging/metric; không tự có DLQ |
| `orders.dynamic.<tenant>` | Optional `IntegrationFlowRegistration` | Tùy endpoint | Registration, generation | Tenant runtime manager | Quiesce/drain/destroy đúng owner |

**Quan trọng:** `orders.pending` đã được dequeue không có nghĩa `orders.processor` đã commit. `orders.outbox.relay` hoàn tất publish cũng không chắc chắn remote consumer apply thành công; outbox cần giữ đủ metadata để retry.

## 4. Lựa chọn channel và ranh giới thread

| Lựa chọn | Khi phù hợp | Giới hạn / hệ quả transaction |
|---|---|---|
| `DirectChannel` | Validation, routing, handler đồng bộ nhanh | Caller cùng thread; lỗi có thể truyền ngược, dễ kéo dài latency ingress |
| `QueueChannel(128)` | Bài test hoặc buffer bounded trong một JVM | Message in-memory có thể mất khi crash |
| `QueueChannel` + `MessageGroupQueue(JdbcChannelMessageStore)` | Dự án minh họa durable intake trong PostgreSQL | JDBC I/O, serializer/schema, concurrency; **DB làm queue có trade-off hiệu năng** |
| `ExecutorChannel` | Tách bước CPU/IO khỏi sender, giới hạn worker | Async handoff cắt transaction thread-bound và có nguy cơ task reject |
| `PublishSubscribeChannel` | Broadcast notifications/audit phụ | Mặc định có thể chấp nhận send khi không subscriber; không phải durable fan-out |
| Kafka/JMS/AMQP inbound | Tải cao, lưu bền vững ở broker, cần replay | Phải xác định ACK/offset, retry và container lifecycle riêng |

Thiết kế chính cố ý giữ **poller → processor đồng bộ**, tránh đặt `ExecutorChannel` **bên trong** transaction chứa dequeue. Nếu thay bằng executor mà poller coi việc submit thành công là completion, có thể commit loại message khỏi JDBC queue khi handler vẫn chưa làm xong.

Với hệ thống production lưu lượng lớn, Spring Integration docs khuyến cáo cân nhắc broker thay vì database-as-queue. Ở đây chọn JDBC queue để học rõ **cùng DataSource và transaction scope**; có thể thay bằng Kafka/AMQP/JMS nhưng phải viết lại ACK/recovery tests.

### Timeline của một message hợp lệ

~~~mermaid
sequenceDiagram
    participant C as Client / Broker
    participant G as Admission
    participant Q as JDBC Queue
    participant P as Poller + TX
    participant B as Business DB
    participant R as Outbox relay
    C->>G: OrderEvent(eventId=E42)
    G->>Q: send(event) trong intake transaction
    Q-->>G: accepted vào store
    Note over G,Q: Commit thành công mới được xác nhận accepted
    G-->>C: 202 Accepted / ACK theo contract
    P->>Q: receive trong TX
    Q-->>P: OrderEvent E42
    P->>B: INSERT dedupe + UPDATE order + INSERT outbox
    B-->>P: commit cùng TX với dequeue
    R->>B: lấy outbox chưa publish
    R->>C: publish business event
    Note over R,C: Nếu publish xong nhưng mark chưa xong, có thể gửi lại
~~~

Trong diagram, mũi tên relay tới client/broker là **đích outbound độc lập**; không phải HTTP response `202` của lời gọi intake ban đầu. Hệ thống cần dashboard/bảng tra cứu riêng cho trạng thái `PROCESSING`, `APPLIED`, `PUBLISHED` hoặc `QUARANTINED`.

## 5. State inventory: dữ liệu nào phải sống qua restart?

| State | Nơi lưu | Có bền vững không? | Ai được sửa/xóa? |
|---|---|---|---|
| Event pending | `INT_CHANNEL_MESSAGE` qua `JdbcChannelMessageStore` | Có **sau commit** | Poller đúng region/group + transaction |
| Event đã apply | `processed_events(event_id PK)` | Có | Business transaction, retention có kiểm soát |
| Order projection | `orders` | Có | Business transaction, có version/ordering policy |
| Event cần phát ra | `outbox_events` | Có | Business TX tạo; relay cập nhật publish state |
| Poison event | `quarantined_events` hoặc broker DLQ | Nếu đã thiết kế và commit | Recovery service, operator có quyền |
| Queue depth trong app | JMX/Micrometer/snapshot | Không thay cho database | Observability |
| Endpoint running, executor active | Memory của process | Không | Lifecycle processor |
| Active admission gate | Memory + trạng thái điều phối | Memory một node không đủ multi-node | Runtime coordinator |
| Tenant generation/flow config | Bảng cấu hình bền vững | Có | Provisioning/reconciler |
| `correlationId`, `traceId` | Message headers/tracing backend | Tùy serializer/header mapper | Producer, middleware, tracing |
| Retry attempt | Retry context / durable retry ledger | Tùy cách cấu hình | Retry/recovery policy |

Đừng nhầm **state tồn tại** và **state đã commit**. Một row có thể đã được insert trong transaction nhưng chưa visible/committed. Đừng coi metric “queue depth = 0” là bằng chứng không còn in-flight; poller có thể đã dequeue rồi vẫn đang xử lý.

### DDL nghiệp vụ do ứng dụng sở hữu

Các bảng dưới đây do ứng dụng quản lý; chúng **không thay thế** schema Spring Integration JDBC chính thức:

~~~sql
-- PostgreSQL, minh họa schema nghiệp vụ.
CREATE TABLE processed_events (
    event_id        VARCHAR(120) PRIMARY KEY,
    tenant_id       VARCHAR(120) NOT NULL,
    order_id        VARCHAR(120) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    tenant_id       VARCHAR(120) NOT NULL,
    order_id        VARCHAR(120) NOT NULL,
    amount_cents    BIGINT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE outbox_events (
    outbox_id       VARCHAR(120) PRIMARY KEY,
    event_id        VARCHAR(120) NOT NULL UNIQUE,
    payload_json    JSONB NOT NULL,
    state           VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_pending
  ON outbox_events (state, next_attempt_at, created_at);
~~~

**Chú ý ordering:** Ví dụ chỉ giả định event biểu diễn giá trị đơn hàng cần upsert, không yêu cầu thứ tự cập nhật phức tạp. Nếu một order có nhiều phiên bản thay đổi, cần thêm `eventVersion` và cập nhật có điều kiện (hoặc partition/lock theo order) để không cho event cũ overwrite event mới. Không dùng thứ tự enqueue của nhiều producer làm bảo đảm ordering toàn cục.

**Chú ý duplicate:** Dedupe theo `event_id` hoạt động khi cùng ID thực sự mang cùng nội dung nghiệp vụ. Production cần thêm fingerprint/hash để nhận biết một ID bị sử dụng với payload khác: đó là **conflicting duplicate** cần quarantine và điều tra, không im lặng coi là xử lý thành công.

### Schema của message store phải đến từ đúng phiên bản

Module `spring-integration-jdbc` cung cấp `schema-postgresql.sql` mẫu cho các bảng `INT_...`. Trước khi bật queue ở môi trường mới:

1. Chạy migration tương thích với **phiên bản Spring Integration** đang dùng, không viết tay lại DDL từ trí nhớ.
2. Xác nhận query provider, indexes, `tablePrefix`/`region` và các loại payload/header serializer.
3. Test đọc bản tin đã lưu bằng **version mới** trước khi rolling upgrade.
4. Quản lý backup, retention, bloat/vacuum và connection pool như dữ liệu nghiệp vụ.
5. Từ Spring Integration 6.2, JDBC stores có kiểm tra bảng khi start; lỗi schema có thể khiến application context không start — đây là cảnh báo đúng cần sửa, không tự tắt kiểm tra chỉ để deploy.

## 6. Chuẩn bị runtime và các biến thể triển khai

Tối thiểu có Spring Integration Core, Spring JDBC, Spring Transaction, PostgreSQL driver và test framework. Với Spring Boot, sử dụng BOM tương thích để tránh trộn các phiên bản Spring:

~~~kotlin
// Đoạn bên trong dependencies { ... } của Gradle Kotlin DSL.
implementation("org.springframework.boot:spring-boot-starter")
implementation("org.springframework.boot:spring-boot-starter-jdbc")
implementation("org.springframework.integration:spring-integration-core")
implementation("org.springframework.integration:spring-integration-jdbc")
implementation("com.fasterxml.jackson.core:jackson-databind")
runtimeOnly("org.postgresql:postgresql")

testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.integration:spring-integration-test")
testImplementation("org.testcontainers:postgresql")
~~~

Đây là **danh sách dependency minh họa**, chưa gồm Spring Boot plugin/BOM và repositories của build hoàn chỉnh. Không thêm version số học tùy ý vào từng dependency nếu đã dùng BOM.

Hai profile thể hiện **hai hợp đồng durability khác nhau**:

| Profile | Kiểu hàng đợi | Mục tiêu |
|---|---|---|
| `workshop` | `QueueChannel(128)` in-memory | Chạy ví dụ unit/flow test nhanh, không giả vờ hỗ trợ restart |
| `durable` | `QueueChannel(new MessageGroupQueue(store, groupId))` | Thực hành JDBC transaction/restart |

Chỉ bật **một** profile ở mỗi context để không có hai bean trùng `orders.pending`. Để trả 202 theo **INV-02**, chỉ profile `durable` đáp ứng nếu message đã được commit ở store; profile `workshop` không được quảng bá tương đương API bền vững.

### Domain event có thể serialize

~~~java
import java.io.Serializable;

public record OrderEvent(
        String eventId,
        String tenantId,
        String orderId,
        long amountCents) implements Serializable {

    public OrderEvent {
        if (eventId == null || eventId.isBlank()
                || tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || amountCents <= 0) {
            throw new IllegalArgumentException("OrderEvent không hợp lệ");
        }
    }
}
~~~

Payload là record có các field serializable. Việc sử dụng Java serialization trong một JDBC message store cần **quy tắc versioning/allowlist/security của serializer**; với dữ liệu từ nguồn không đáng tin cậy, tuyệt đối không deserialize object tùy ý mà không kiểm soát. Trong production nên cân nhắc serializer ổn định theo schema JSON/Avro/Protobuf và migration.

## 7. Cấu hình QueueChannel in-memory và JDBC

~~~java
@Configuration
@Profile("workshop")
class WorkshopQueueConfig {

    @Bean(name = "orders.pending")
    QueueChannel pending() {
        return new QueueChannel(128);
    }
}
~~~

Phiên bản JDBC, dùng **cùng PostgreSQL DataSource** với bảng nghiệp vụ:

~~~java
@Configuration
@Profile("durable")
class DurableQueueConfig {

    @Bean
    JdbcChannelMessageStore ordersChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
            new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
            new PostgresChannelMessageStoreQueryProvider());
        store.setRegion("orders-intake-v1");
        return store;
    }

    @Bean(name = "orders.pending")
    QueueChannel pending(JdbcChannelMessageStore store) {
        MessageGroupQueue persistentQueue =
            new MessageGroupQueue(store, "orders.pending.v1");
        return new QueueChannel(persistentQueue);
    }
}
~~~

Các kiểu và package:

| Kiểu | Package |
|---|---|
| `QueueChannel` | `org.springframework.integration.channel` |
| `JdbcChannelMessageStore` | `org.springframework.integration.jdbc.store` |
| `PostgresChannelMessageStoreQueryProvider` | `org.springframework.integration.jdbc.store.channel` |
| `MessageGroupQueue` | `org.springframework.integration.store` |
| `DataSource` | `javax.sql` |
| `@Profile`, `@Bean`, `@Configuration` | `org.springframework.context.annotation` |

**Hai khóa phải ổn định:** `region` và `groupId`. Nếu thay bất ngờ khi restart, consumer mới có thể nhìn như queue rỗng vì dữ liệu cũ đang ở vùng/nhóm khác. Các bản chạy nhiều node dùng chung queue phải thống nhất store schema, region, group, serializer và phối hợp polling transaction.

Ví dụ durable trên **không** đặt capacity in-memory. Cần admission/rate-limit, alert độ sâu, quota và retention từ đầu. `MessageGroupQueue` có overload constructor nhận capacity nhưng năng lực kiểm soát giới hạn trong nhiều node phải được thử thực tế, không suy ra có hard global cap chỉ vì có tham số capacity.

**Không dùng lẫn** `JdbcChannelMessageStore` và `JdbcMessageStore` theo tên gần giống: loại đầu tối ưu cho channel queue; loại thứ hai phù hợp với aggregator/claim-check. JDBC queue có chi phí và contention; framework còn khuyến cáo cân nhắc broker chuyên dụng cho traffic lớn.

## 8. Java DSL: một PollingConsumer có transaction boundary rõ

Định nghĩa runtime flow ở **một chỗ** để người vận hành có thể tìm đúng endpoint ID. Chỉ poller mới là điểm kích hoạt xử lý, không mở HTTP/broker listener trước khi nó ready.

~~~java
@Configuration
@EnableIntegration
public class OrderProcessingFlow {

    @Bean
    IntegrationFlow ordersWorkerFlow(
            OrderProcessor processor,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from("orders.pending")
            .handle(processor, "apply", endpoint -> endpoint
                .id("orders.worker")
                .autoStartup(false)
                .poller(Pollers.fixedDelay(250)
                    .maxMessagesPerPoll(1)
                    .receiveTimeout(0)
                    .transactional(transactionManager)))
            .get();
    }
}
~~~

Các import đáng chú ý:

~~~java
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

**Vì sao cấu hình này quan trọng?**

- `IntegrationFlow.from("orders.pending")` trỏ tới **bean channel đã tạo**; nếu là `QueueChannel`, endpoint tiêu thụ phải có poller.
- `id("orders.worker")` tạo tên endpoint ổn định để start/stop và chẩn đoán trong log/graph.
- `autoStartup(false)` giúp runtime coordinator đợi database/store/recovery sẵn sàng mới start.
- `fixedDelay(250)` là khoảng trễ sau mỗi poll task, không phải thông lượng bảo đảm.
- `maxMessagesPerPoll(1)` giúp test transaction và diễn giải lỗi theo từng lần receive. Muốn tăng throughput phải đo và kiểm tra tranh chấp DB/ordering trước.
- `transactional(transactionManager)` tạo transaction bao quanh **poll task, bao gồm receive và downstream đồng bộ**. Với durable profile, chỉ khi store và business write dùng cùng DataSource/transaction manager thì receive rollback mới có khả năng khôi phục đúng.

**Chủ ý không thêm `ExecutorChannel` giữa poller và processor.** Nếu thêm handoff bất đồng bộ, poller có thể commit dequeue sau khi chỉ submit task, còn lỗi trong worker xảy ra ngoài transaction cũ.

### Mốc trạng thái ở từng thread

~~~mermaid
sequenceDiagram
    participant P as Scheduler / Poller thread
    participant Q as JDBC Queue
    participant H as OrderProcessor
    participant D as PostgreSQL TX
    P->>D: begin transaction
    P->>Q: receive
    Q-->>P: OrderEvent
    P->>H: apply(event) đồng bộ
    H->>D: INSERT dedupe + UPSERT order + INSERT outbox
    alt hoàn tất
      H-->>P: return void
      P->>D: commit (dequeue + business)
    else ném exception chưa được recover
      H--xP: exception
      P->>D: rollback
      Note over P,Q: Hành vi re-delivery phải được test với store và policy
    end
~~~

Một `MessagePublishingErrorHandler` có thể publish `ErrorMessage` ở boundary poller; điều đó **không tự chứng minh transaction đã rollback hoặc message được redeliver**. Recovery advice có thể nuốt exception và làm thay đổi outcome. Phải kiểm thử đúng version, advice order và cách error handler kết thúc.

## 9. Business handler idempotent và outbox trong cùng transaction

Lớp sau chỉ cần một `JdbcTemplate` và Jackson `ObjectMapper`; transaction **đã được mở ở poller**, nên các lệnh JDBC tham gia cùng transaction thông qua Spring JDBC/transaction manager.

~~~java
@Component
public class OrderProcessor {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public OrderProcessor(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public void apply(OrderEvent event) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_events (event_id, tenant_id, order_id)
            VALUES (?, ?, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(), event.tenantId(), event.orderId());

        if (inserted == 0) {
            // Duplicate của logical event đã commit từ lần xử lý trước.
            return;
        }

        jdbc.update(
            """
            INSERT INTO orders (tenant_id, order_id, amount_cents)
            VALUES (?, ?, ?)
            ON CONFLICT (tenant_id, order_id)
            DO UPDATE SET amount_cents = EXCLUDED.amount_cents,
                          updated_at = now()
            """,
            event.tenantId(), event.orderId(), event.amountCents());

        final String json;
        try {
            json = mapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize outbox", ex);
        }

        jdbc.update(
            """
            INSERT INTO outbox_events
                (outbox_id, event_id, payload_json, state)
            VALUES (?, ?, CAST(? AS jsonb), 'PENDING')
            """,
            "order-applied:" + event.eventId(),
            event.eventId(),
            json);
    }
}
~~~

Các kiểu: `JdbcTemplate` thuộc `org.springframework.jdbc.core`; `ObjectMapper` và `JsonProcessingException` thuộc Jackson; `@Component` thuộc Spring stereotype. Nếu Spring Boot không cung cấp `ObjectMapper`, đăng ký một bean Jackson phù hợp. Vì text block Java được hỗ trợ từ Java 15, ví dụ yêu cầu Java 17+ như đã công bố.

**Tính nguyên tử cần hiểu đúng:**

1. Lần đầu xử lý E42: `processed_events` insert một row, `orders` upsert và `outbox_events` insert. Nếu cả ba thành công và poller commit, E42 được apply.
2. Nếu SQL thứ hai hoặc thứ ba ném exception, transaction rollback cả dấu dedupe lẫn business state và thao tác dequeue JDBC trong cùng scope.
3. Nếu broker/client gửi lại E42 sau commit, `ON CONFLICT DO NOTHING` trả 0; handler không ghi lại side effect hay outbox record.
4. Nếu E42 bị **trùng ID nhưng payload khác**, ví dụ này chưa kiểm tra fingerprint; cần bổ sung digest và một nhánh conflict/quarantine trước khi coi hệ thống đủ điều kiện production.
5. Nếu có **nhiều event hợp lệ trên cùng order**, SQL upsert theo last-writer-wins và chưa bảo đảm version order; phải thiết kế contract ordering/version khi mở rộng bài toán.

Không thay logic trên bằng `if (!repository.existsById(id)) insert(...)` rồi tin rằng nó chống trùng trên nhiều node. Read-then-write không nguyên tử; **unique constraint** ở database mới là điểm phân xử cạnh tranh.

### Giới hạn của annotation @Transactional

Có thể dùng `@Transactional` trên method nghiệp vụ, nhưng nếu handler chạy ở thread khác (executor/async) hoặc method tự gọi nhau không qua Spring proxy thì transaction scope có thể khác kỳ vọng. Ở thiết kế này, **poller transaction advice** là boundary chính bao receive/handler; business JDBC dùng cùng transaction manager. Test phải đọc dữ liệu từ transaction độc lập sau completion để kiểm tra commit thật.

## 10. Ingress gate: chỉ trả Accepted sau durable commit

Ví dụ API nội bộ bảo vệ cutoff bằng `ReentrantReadWriteLock` và sử dụng `TransactionTemplate` để bảo đảm response được trả **sau khi enqueue transaction đã kết thúc**. Đây là gate của **một JVM**, không thay thế admission phân tán.

~~~java
@Component
public class OrderIngress {
    private final MessageChannel pending;
    private final TransactionTemplate transactions;
    private final ReadWriteLock lock = new ReentrantReadWriteLock(true);
    private boolean accepting = false;

    public OrderIngress(
            @Qualifier("orders.pending") MessageChannel pending,
            PlatformTransactionManager txManager) {
        this.pending = pending;
        this.transactions = new TransactionTemplate(txManager);
        // Commit intake phải độc lập với transaction ngoài (nếu có).
        this.transactions.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public boolean accept(OrderEvent event) {
        lock.readLock().lock();
        try {
            if (!accepting) {
                return false; // Chưa nhận; caller phải retry theo policy.
            }

            Boolean committed = transactions.execute(status -> {
                Message<OrderEvent> message = MessageBuilder
                    .withPayload(event)
                    .setHeader("businessEventId", event.eventId())
                    .setHeader("correlationId",
                        event.tenantId() + ":" + event.orderId())
                    .setHeader("tenantId", event.tenantId())
                    .build();
                if (!pending.send(message, 300)) {
                    throw new IllegalStateException("Intake queue unavailable");
                }
                return Boolean.TRUE;
            });
            return Boolean.TRUE.equals(committed);
        } finally {
            lock.readLock().unlock();
        }
    }

    public void open() {
        lock.writeLock().lock();
        try {
            accepting = true;
        } finally {
            lock.writeLock().unlock();
        }
    }

    public void close() {
        lock.writeLock().lock();
        try {
            accepting = false;
        } finally {
            lock.writeLock().unlock();
        }
    }
}
~~~

Các kiểu: `org.springframework.messaging.MessageChannel`, `org.springframework.integration.support.MessageBuilder`, `org.springframework.transaction.support.TransactionTemplate`, `org.springframework.transaction.TransactionDefinition`, `java.util.concurrent.locks.ReadWriteLock`/`ReentrantReadWriteLock`.

**Chứng cứ cho INV-02:** Trong profile durable, `pending.send(...)` ghi vào JDBC store trong transaction này. `PROPAGATION_REQUIRES_NEW` tạo physical transaction độc lập ngay cả khi adapter đã mở transaction ngoài; `TransactionTemplate.execute(...)` chỉ trả về bình thường sau khi kết thúc transaction intake. Vì vậy `accept(...) == true` có thể được ánh xạ thành HTTP 202 **nếu** store và manager cùng DataSource, và không có thao tác khác ACK sớm. Nếu commit ném lỗi, exception phải được phản hồi thành failure cho caller. `REQUIRES_NEW` cần thêm JDBC connection nếu caller đang giữ outer transaction; phải đo pool capacity và tránh starvation.

Nếu đang dùng **profile workshop in-memory**, cùng method chỉ chứng minh enqueue vào RAM, **không** chứng minh durability. API thực tế phải từ chối công bố SLO durability hoặc chỉ bật nhận production dưới profile durable.

Với HTTP gateway tùy chọn (thêm `spring-boot-starter-web` nếu cần), có thể ánh xạ:

~~~java
@RestController
@Profile("durable")
@RequestMapping("/api/orders")
public class OrderIngressController {
    private final OrderIngress ingress;

    public OrderIngressController(OrderIngress ingress) {
        this.ingress = ingress;
    }

    @PostMapping("/events")
    public ResponseEntity<Void> accept(@RequestBody OrderEvent event) {
        if (!ingress.accept(event)) {
            return ResponseEntity.status(503)
                .header("Retry-After", "2")
                .build();
        }
        return ResponseEntity.accepted().build();
    }
}
~~~

Trong sản phẩm thật, xử lý exception tại HTTP boundary để phân biệt 400 (validation), 409 (conflicting event ID) và 503 (hạ tầng chưa nhận được), không trả 202 khi commit thất bại. Nếu client timeout **sau** commit nhưng trước khi nhận response, client có thể gửi lại E42; xử lý duplicate bằng event ID là bắt buộc.

### Race giữa accept và close

Lời gọi `accept()` giữ read lock qua cả transaction commit. `close()` lấy write lock chỉ sau khi những lời gọi đang accepted trả về; các lời gọi bắt đầu sau khi close hoàn thành sẽ bị từ chối. Không cấp reference đến `orders.pending` cho một sender khác rồi tưởng gate có thể bảo vệ sender ấy.

Giữ lock qua JDBC có thể khiến shutdown chờ lâu nếu DB treo; cần timeout hữu hạn ở DataSource/JDBC, transaction và API. Multi-node còn cần admission state dùng chung, broker pause hoặc owner fencing.

## 11. Lifecycle dossier: READY, QUIESCE, DRAIN, STOP

Một runtime cần **state machine vận hành riêng**. <code>SmartLifecycle.isRunning()</code> chỉ cho biết trạng thái lifecycle của bean được hỏi, không cho biết toàn bộ database transaction hay outbox đã hoàn tất.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> STARTING: schema, dependencies và flow ready
    STARTING --> READY: start worker và pass readiness
    READY --> QUIESCING: ngừng nhận message mới
    QUIESCING --> DRAINING: đóng gate + pause nguồn ngoài
    DRAINING --> STOPPING: pending settled hoặc có durable replay
    STOPPING --> STOPPED: stop endpoint theo ownership
    STOPPED --> CLEANING: destroy resource riêng
    CLEANING --> TERMINATED: kiểm tra leak và checkpoint
    STARTING --> FAILED: bean/store start lỗi
    DRAINING --> FAILED: drain timeout
    STOPPING --> FAILED: lifecycle stop lỗi
    FAILED --> QUIESCING: điều tra/khôi phục an toàn
~~~

Đây là **mô hình do ứng dụng định nghĩa**, không phải enum của Spring Integration. Cần lưu durable state riêng nếu startup mới phải tiếp tục một operation cleanup chưa hoàn tất.

### Start sequence — consumer trước, ingress sau

~~~text
1. PostgreSQL và schema migration sẵn sàng
2. JdbcChannelMessageStore start / kiểm tra table, query provider, serializer
3. Idempotency / outbox / error-recovery sink ready
4. Spring context đăng ký orders.pending và orders.worker
5. Start orders.worker khi còn ở trạng thái quiesced
6. Verify isRunning, store access và dependency health
7. Mở gate; công bố READY; start/pause-resume broker listener nếu có
~~~

Nếu sử dụng Spring Boot readiness probe, việc HTTP server đã mở cổng **không tự đồng nghĩa** <code>orders.worker</code> chạy. Gate mục 10 vẫn phải trả “chưa nhận” tới khi coordinator hoàn tất start. Với broker listener, start/pause/ACK được điều khiển theo API adapter, không suy từ trạng thái HTTP readiness.

### Stop sequence — ngăn nhận trước khi dừng worker

~~~text
1. Đóng gate và pause inbound adapter
2. Đợi send/transaction của ingress đang chạy được commit/rollback
3. Để poller tiếp tục tiêu thụ backlog nếu muốn drain
4. Xác nhận pending + in-flight/retry ở terminal state
5. Stop orders.worker, rồi stop outbox relay nếu phù hợp
6. Đóng executor/scheduler do flow sở hữu; giữ shared resources
7. Xác nhận persistent state vẫn có recovery owner
8. Ghi checkpoint và cho ApplicationContext shutdown
~~~

**Không stop poller trước bước 3** nếu poller là consumer duy nhất có thể drain queue. Nếu hết grace period và đã có durable queue + safe replay, có thể dừng sau khi chuyển trạng thái còn pending cho instance mới; phải ghi rõ những gì chưa hoàn tất.

### Hợp đồng WorkDrainProbe

~~~java
public interface WorkDrainProbe {
    /**
     * Chỉ true khi mọi work đã accepted cho worker hiện tại
     * đã commit, quarantine bền vững hoặc có durable replay.
     */
    boolean safeToStop();
    long pendingQueue();
    long inFlight();
}
~~~

Đây là **interface của ứng dụng**, không có sẵn trong Spring Integration. Một implementation không thể chỉ trả <code>queue.getQueueSize() == 0</code>: poller có thể đã lấy message ra khỏi queue nhưng transaction chưa commit, hoặc một task ở executor đang chạy. Với JDBC store, cần xem transaction active, work-state ledger và điều kiện replay. Với broker cần thêm offset/ACK state. Nên có bộ đếm outstanding đăng ký **trước** khi async work có thể hoàn tất, hoặc ledger dựa trên durable business event IDs.

### Ví dụ coordinator tối giản

~~~java
public final class OrderRuntimeCoordinator {
    private final OrderIngress ingress;
    private final SmartLifecycle worker;
    private final WorkDrainProbe probe;

    public OrderRuntimeCoordinator(
            OrderIngress ingress,
            SmartLifecycle worker,
            WorkDrainProbe probe) {
        this.ingress = ingress;
        this.worker = worker;
        this.probe = probe;
    }

    public synchronized void startWhenReady() {
        // Caller phải kiểm tra DB/store/recovery health trước khi gọi.
        if (!worker.isRunning()) {
            worker.start();
        }
        if (!worker.isRunning()) {
            throw new IllegalStateException("Worker chưa sẵn sàng");
        }
        ingress.open();
    }

    public synchronized boolean quiesceDrainStop(Duration budget)
            throws InterruptedException {
        ingress.close();
        long deadline = System.nanoTime() + budget.toNanos();
        while (!probe.safeToStop()) {
            if (System.nanoTime() >= deadline) {
                return false; // Giữ gate đóng; không destroy khi chưa an toàn.
            }
            Thread.sleep(25); // Chỉ trên management thread.
        }
        worker.stop();
        return !worker.isRunning();
    }
}
~~~

Để wire coordinator, lấy endpoint bằng ID đã khai báo:

~~~java
@Bean
OrderRuntimeCoordinator orderRuntimeCoordinator(
        OrderIngress ingress,
        @Qualifier("orders.worker") SmartLifecycle worker,
        WorkDrainProbe probe) {
    return new OrderRuntimeCoordinator(ingress, worker, probe);
}
~~~

<code>SmartLifecycle</code> thuộc <code>org.springframework.context</code>; <code>Duration</code> thuộc <code>java.time</code>. Trong ứng dụng thật phải đăng ký implementation <code>WorkDrainProbe</code>; ví dụ trên **không** tự cấp một bộ đếm durable. Dùng event/condition hoặc completion signals sẽ tốt hơn polling <code>Thread.sleep(25)</code> khi cần nhiều instance; bài dùng deadline hữu hạn để tránh treo vô hạn.

**Trường hợp timeout:** Giá trị <code>false</code> **không** có nghĩa message bị mất. Gate vẫn đóng, worker còn running, operator cần xem queue/transaction/recovery. Nếu process bị platform kill sau grace period, độ bền của PostgreSQL queue và idempotency là biện pháp chính để phục hồi.

## 12. Threading, phase và shutdown: đừng đóng resource sai thứ tự

Với <code>SmartLifecycle</code>, phase thấp start trước và stop sau, phase cao start sau và stop trước **trong cùng lifecycle processor**. Điều đó giúp sắp thứ tự tương đối giữa dependency, consumer và producer nhưng **không thay thế** readiness gate, transaction settlement hoặc adapter-specific ACK.

| Thành phần | Khi start | Khi stop | Không được làm |
|---|---|---|---|
| Database và message store | Trước poller và ingress | Sau khi không còn work cần DB | Tắt datasource trong lúc TX đang commit |
| Worker poller | Khi schema/handler sẵn sàng | Sau drain hoặc khi durable recovery đã được chứng minh | Dừng consumer duy nhất trước khi drain còn backlog |
| HTTP/broker ingress | Sau readiness | Trước worker | Tiếp tục ACK khi chưa durable accept |
| Executor riêng flow | Sau dependency và trước consumer cần nó | Sau khi không còn submit/in-flight | Shutdown trước khi xử lý accepted task xong |
| Shared scheduler/connection | Do application owner quản lý | Theo toàn application | Destroy vì một tenant bị gỡ |
| Error/recovery sink | Sẵn sàng trước khi xử lý | Sau khi publisher/worker đã ngừng | Đóng trước khi last ErrorMessage được xử lý |

Nếu cần <code>ExecutorChannel</code> cho outbound khác, đặt nó **sau transaction/outbox boundary** và cho worker riêng; không chuyển business JDBC write vào executor rồi nghĩ poller transaction vẫn bao nó. <code>CallerRunsPolicy</code> khi executor bão hòa cũng có thể thay đổi thread/latency/transaction semantics không đoán trước.

### Readiness và shutdown trong Kubernetes

Ứng dụng có thể phối hợp các bước:

1. Khi <code>SIGTERM</code> hoặc pre-stop: chuyển readiness sang không nhận mới.
2. Đóng gate cục bộ và pause listener broker tương ứng.
3. Đợi in-flight ingress transactions kết thúc; để poller xử lý phần backlog theo grace period.
4. Sau khi đạt condition hoặc xác nhận durable replay, stop poller rồi đóng owned resources.
5. Thoát process, để instance kế tiếp chạy reconciliation.

Một hook <code>@PreDestroy</code> có thể dùng để cleanup ngắn, nhưng **không bảo đảm được gọi khi kill -9/OOM**. Nếu Spring context đã bắt đầu destroy dependencies, việc cố drain tại <code>@PreDestroy</code> cũng có thể quá muộn. Thiết kế orchestrator quiesce **trước khi context close** sẽ rõ ràng hơn.

## 13. Recovery dossier: crash ở điểm nào, xử lý ra sao?

| Điểm crash/failure | State còn lại | Khi restart/caller retry | Cần kiểm chứng |
|---|---|---|---|
| Trước khi enqueue TX commit | Không có accepted durable | Caller gửi lại; không trả 202 | Không có orphan business state |
| Sau enqueue commit, trước HTTP response | Queue đã có E42, client không chắc | Client có thể gửi lại E42; processor phải idempotent | Không có hai business updates/outbox |
| Poller đã receive, processor chưa commit | JDBC dequeue và business TX chưa terminal | Rollback và event lại eligible nếu store hỗ trợ đúng | Test với cùng DB/manager |
| Sau business TX commit, trước outbox relay | Processed marker, order, outbox pending | Không apply lại E42; relay tiếp tục từ outbox | Check row state sau restart |
| Outbox publish thành công, trước mark PUBLISHED | Remote có event, outbox vẫn pending/in-flight | Relay có thể gửi lại | Remote dedupe theo stable outbox ID |
| Dependency HTTP/DB timeout | Event còn queue hoặc được xử lý theo recovery policy | Retry có giới hạn/backoff, không storm | Attempt count + circuit breaker |
| Payload/schema sai cố định | Có thể bị retry vô hạn nếu không phân loại | Quarantine với reason, owner và replay policy | Không làm kẹt toàn queue |
| Shutdown giữa in-flight | Task đang chạy hoặc TX chưa kết thúc | Database rollback/replay hoặc đối soát commit | Side effect không nhân đôi |
| Dynamic tenant flow bị xóa | Bean flow mất, DB store có thể còn | Reconciler quyết định rebuild/replay/quarantine | Không resurrect tenant DELETED |

**Lưu ý đặc biệt:** Đối với JDBC queue, câu “message sẽ được trả lại sau rollback” phụ thuộc transaction đúng phạm vi, serializer/query provider và lỗi không bị swallow. Không hứa điều đó cho <code>QueueChannel(128)</code> in-memory, <code>ExecutorChannel</code> hay một nguồn broker với ACK đã gửi trước khi task hoàn tất.

### Retry policy theo loại lỗi

| Nhóm lỗi | Có retry không? | Recovery |
|---|---|---|
| Timeout hoặc 503 downstream transient | Có, bounded + exponential backoff/jitter | Giữ event bền vững, pause poller hoặc retry scheduler có deadline |
| JDBC connection tạm mất | Có, nhưng tránh quay vòng quá nhanh | Chờ dependency healthy, giảm concurrency |
| Validation/unsupported schema | Không hoặc rất giới hạn | Quarantine/DLQ có payload metadata an toàn |
| Vi phạm thứ tự/version | Tùy contract | Reorder buffer hoặc reject event stale |
| Không có subscriber do flow stop | Retry ở producer/adapter khi flow ready | Chặn ingress trong lúc stop, không thêm dummy handler |
| Executor task rejected | Retry ở boundary submit nếu chưa accepted | Bounded backlog/broker; tránh DiscardPolicy |
| Unknown commit outcome | Không đoán đã thất bại | Đối soát event ID và outbox trước replay |

<code>RequestHandlerRetryAdvice</code> chỉ bao những **lần gọi handler đã bắt đầu**. Nó không tự retry lỗi phát sinh trước handler (ví dụ executor reject hoặc queue send fail). Nếu retry advice hết N attempt rồi vẫn ném lỗi, JDBC poller có thể rollback và poll lại message ở chu kỳ kế tiếp — tạo **retry storm không giới hạn qua nhiều poll cycles**. Muốn có ngân sách retry toàn hệ thống, cần durable attempt ledger, delayed retry/retry topic hoặc pause/poll filter phù hợp.

### Quarantine an toàn không phải là nuốt exception

Một nhánh recovery đúng phải có giao dịch/quy trình:

~~~text
BEGIN TX
  nhận đúng E42 từ persistent queue
  xác định lỗi terminal, với attempt budget/exception class
  INSERT quarantined_events(eventId, reason, payloadRef, owner)
  ghi terminal marker hoặc replay checkpoint
  commit dequeue và quarantine theo cùng transaction nếu thiết kế cho phép
COMMIT
~~~

Nếu việc lưu quarantine thất bại, không được âm thầm trả “handled” để poller commit dequeue. Nếu message/side effect nằm trên hai hệ thống không có transaction chung, phải dùng outbox/saga và cơ chế reconciliation. Không log full PII hoặc lưu plaintext secret trong quarantine.

Một bảng bổ sung có thể thiết kế:

~~~sql
CREATE TABLE quarantined_events (
    event_id      VARCHAR(120) PRIMARY KEY,
    tenant_id     VARCHAR(120) NOT NULL,
    reason_code   VARCHAR(64) NOT NULL,
    payload_json  JSONB NOT NULL,
    attempts      INTEGER NOT NULL,
    state         VARCHAR(24) NOT NULL DEFAULT 'OPEN',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Những SQL trên là **schema ứng dụng**. Gắn mã lỗi low-cardinality, owner, thời điểm hết retention và policy replay riêng; không xóa message trực tiếp khỏi <code>INT_CHANNEL_MESSAGE</code> để làm dashboard hết đỏ mà chưa có bằng chứng quarantine đã commit.

## 14. Outbox relay: gửi một lần theo logic, chấp nhận redelivery

Trong thiết kế này, business transaction **không** gọi trực tiếp remote HTTP endpoint hoặc broker producer rồi coi cả hai tài nguyên commit nguyên tử. Thay vào đó:

1. Business write và outbox insert cùng commit trong PostgreSQL.
2. Relay độc lập lấy các outbox record đến hạn gửi.
3. Relay publish event bằng **idempotency key ổn định**, ví dụ <code>outbox_id</code>.
4. Chỉ mark <code>PUBLISHED</code> khi có kết quả đủ tin cậy từ adapter; nếu kết quả không chắc chắn, để record được retry theo deadline/lease.
5. Remote consumer chịu trách nhiệm dedupe theo event/outbox ID.

### Claim một batch theo lease, không giữ TX trong lúc gọi mạng

Mở rộng bảng outbox từ mục 5:

~~~sql
ALTER TABLE outbox_events
  ADD COLUMN lease_owner VARCHAR(120),
  ADD COLUMN lease_until TIMESTAMPTZ;
~~~

Một giao dịch ngắn để **claim** có thể dùng PostgreSQL:

~~~sql
WITH picked AS (
    SELECT outbox_id
    FROM outbox_events
    WHERE
        (state IN ('PENDING', 'RETRY') AND next_attempt_at <= now())
        OR (state = 'IN_PROGRESS' AND lease_until < now())
    ORDER BY created_at, outbox_id
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE outbox_events AS o
SET state = 'IN_PROGRESS',
    lease_owner = :worker_id,
    lease_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM picked
WHERE o.outbox_id = picked.outbox_id
RETURNING o.outbox_id, o.event_id, o.payload_json, o.attempts;
~~~

Đây là **SQL minh họa thuật toán**, cần bind parameter <code>:worker_id</code> (ví dụ dùng <code>NamedParameterJdbcTemplate</code>) và kiểm tra index/transaction isolation phù hợp. Giao dịch claim phải **commit trước** khi gọi broker; sau publish, mở transaction mới và kiểm tra owner/lease trước khi mark <code>PUBLISHED</code> hoặc lên lịch retry.

~~~mermaid
flowchart TD
    A["PENDING / RETRY"] --> B["Claim với SKIP LOCKED + lease"]
    B --> C["Publish external với outbox_id"]
    C -->|ACK xác định| D["Mark PUBLISHED bằng owner token"]
    C -->|Timeout / kết quả chưa biết| E["Lease expire → retry"]
    E --> B
    C -->|Permanent failure| F["QUARANTINED / human review"]
~~~

**Trade-off quan trọng:** Nếu publish thành công nhưng process chết **trước** khi mark <code>PUBLISHED</code>, relay mới sẽ gửi lại. Đây là lý do kiến trúc outbox **không** tự cho exactly-once ở remote receiver. Receiver phải idempotent; nếu không thể, cần một quy trình reconciliation theo transaction/business ID.

Không mark record <code>PUBLISHED</code> trước khi publish được ACK theo contract. Không tạo lease vô hạn: nếu worker chết, record sẽ mắc kẹt. Ngược lại, lease quá ngắn có thể làm hai relay publish đồng thời; cần token fencing, deadline và idempotency. Với HTTP không có ACK chắc chắn, timeout không phân biệt được request chưa đến hay đã hoàn tất.

### Outbox relay có phải IntegrationFlow không?

Có thể viết relay bằng Spring Integration JDBC inbound adapter/poller và outbound adapter, hoặc một service scheduler. **Mọi cách đều phải giữ cùng contract** claim, lease, publish, ACK, retry và mark. Một <code>SourcePollingChannelAdapter</code> chạy đều đặn không tự tạo transaction xuyên broker và PostgreSQL. Đừng nhầm trigger mỗi 500 ms với năng lực hoàn tất 2 event/giây; throughput còn phụ thuộc batch size và downstream.

## 15. Correlation và message group: phần mở rộng có điều kiện

Hồ sơ chính xử lý event độc lập theo <code>eventId</code>. Nếu sản phẩm có yêu cầu **gom nhiều line items thành một đơn hàng**, có thể thêm splitter/aggregator, nhưng lúc đó phải thiết kế state riêng:

~~~mermaid
flowchart LR
    A["Order batch"] --> S["Splitter"]
    S --> C["Correlation: tenantId + batchId"]
    C --> G["Aggregator / MessageGroupStore"]
    G --> R["ReleaseStrategy đủ fragments"]
    R --> O["Persist business outcome"]
    G -. "timeout" .-> E["Expire / discard / quarantine"]
~~~

| Câu hỏi thiết kế group | Quyết định cần ghi |
|---|---|
| Group key | <code>tenantId + ":" + batchId</code>, không chỉ <code>batchId</code> nếu nhiều tenant |
| Điều kiện release | Đủ <code>sequenceSize</code>, terminal marker hoặc rule nghiệp vụ |
| Fragment trùng/lệch | Có dedupe fragment ID và chính sách late arrival |
| Store | <code>JdbcMessageStore</code> cho message group, **khác** <code>JdbcChannelMessageStore</code> của queue |
| Concurrency | LockRegistry phù hợp phạm vi node; khi multi-node dùng lock/store được hỗ trợ và kiểm chứng |
| Timeout | Group expired ra đâu? Có xóa hay giữ partial state? |
| Restart | Rehydrate group còn pending theo region/serializer |
| Cleanup | Chỉ purge group đã terminal theo retention, không xóa khi endpoint stop |

Trong Spring Integration, <code>correlationId</code> là header phục vụ ghép nhóm/business context, **không tự là trace ID, message ID hay idempotency key**. Với hệ thống multi-tenant, header ở ingress nên dùng tenant + order làm correlation logic nếu cross-tenant order IDs có thể trùng. Mở rộng định danh mà không đổi <code>eventId</code> dedupe.

**Cảnh báo:** Một <code>DefaultLockRegistry</code> trong một JVM không tự tạo khóa phân tán. Aggregator dùng nhiều node có thể cần <code>JdbcLockRegistry</code>/Redis/ZooKeeper LockRegistry và store sharing, kèm chính sách lease TTL, unlock trong <code>finally</code>, xử lý owner bị mất khóa. Release một group trong transaction chưa chứng minh outbound ACK đã xong.

## 16. Dynamic runtime: nhiều tenant và ownership của resource

Một yêu cầu thường gặp trong bài tổng hợp là tạo/gỡ flow riêng cho tenant ở runtime. <code>IntegrationFlowContext</code> cho phép register một flow với ID, điều khiển start/stop/destroy và xem registration; đây là **lifecycle topology**, không phải kho lưu cấu hình bền vững.

~~~java
@Component
public class TenantDynamicFlowManager {
    private final IntegrationFlowContext flowContext;

    public TenantDynamicFlowManager(IntegrationFlowContext flowContext) {
        this.flowContext = flowContext;
    }

    public String install(String tenantId, long generation,
                          MessageHandler handler) {
        String flowId = "tenant.audit." + tenantId + "." + generation;
        if (flowContext.getRegistrationById(flowId) != null) {
            throw new IllegalStateException("Already registered: " + flowId);
        }

        IntegrationFlow flow = IntegrationFlow
            .from(new DirectChannel())
            .handle(handler)
            .get();

        flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();
        return flowId;
    }

    public void stopAndRemoveAfterDrain(String flowId) {
        var registration = flowContext.getRegistrationById(flowId);
        if (registration != null) {
            registration.stop();
            registration.destroy();
        }
    }
}
~~~

Các kiểu: <code>IntegrationFlowContext</code> thuộc <code>org.springframework.integration.dsl.context</code>; <code>MessageHandler</code> thuộc <code>org.springframework.messaging</code>; <code>DirectChannel</code> thuộc <code>org.springframework.integration.channel</code>.

Ví dụ là **nhánh audit bổ sung**, không được thay đường intake durable của dự án chính bằng cách gửi thẳng HTTP vào <code>DirectChannel</code> mới tạo. Nó cũng **chưa** triển khai admission gate, durable checkpoint và ownership phân tán: trong production, chỉ được gọi <code>stopAndRemoveAfterDrain()</code> sau khi coordinator đã chặn nhận mới và chứng minh pending được xử lý/quarantine.

### Resource ownership matrix

| Resource | Thuộc flow/tenant riêng? | Khi xóa tenant |
|---|---|---|
| Dynamic <code>IntegrationFlowRegistration</code> | Có | Stop/destroy đúng ID/generation |
| Per-tenant subscription, timer, scheduler task | Có nếu được tạo riêng | Cancel theo handle, kiểm tra callback còn chạy không |
| Shared <code>TaskExecutor</code>/<code>TaskScheduler</code> | Không | **Không shutdown** vì một tenant |
| Shared JDBC <code>DataSource</code>, broker connection factory | Không | **Không close** khi tenant khác còn dùng |
| Tenant credentials/cache | Có thể | Thu hồi sau khi in-flight/recovery phù hợp kết thúc |
| JDBC queue/aggregator state | Có thể phân vùng theo tenant/group | Giữ để replay hoặc purge theo policy có kiểm toán |
| DLQ/outbox/audit records | Dữ liệu riêng nhưng storage chung | Retention theo compliance, không mặc định xóa khi destroy flow |

Race nguy hiểm:

~~~text
T0: tenant A có generation=7, flow ACTIVE
T1: cleanup generation=7 bắt đầu
T2: tenant A tạo lại generation=8
T3: cleanup cũ xóa resource chỉ theo tenantId
→ Lỡ xóa resource đang thuộc generation=8
~~~

Giải pháp cần **generation fencing**, owner token và điều kiện so sánh phiên bản ở DB/lock trước mỗi thao tác cleanup. Kiểm tra <code>getRegistrationById(...) == null</code> rồi register không nguyên tử giữa nhiều thread/node; cần coordinator/CAS cho quyền provision. Sau crash, runtime registry sẽ mất và phải rebuild từ config state bền vững, không coi <code>IntegrationFlowContext</code> là database.

## 17. Observability: mapping từ topology sang bằng chứng vận hành

Không thể điều tra một sự cố bằng câu “Spring Integration không xử lý message” nếu không có số liệu ở từng boundary. Đặt tên bean/endpoint ổn định như bảng ở mục 3 rồi instrument **có chọn lọc**.

~~~java
@Configuration
@EnableIntegrationManagement(
    defaultLoggingEnabled = "false",
    observationPatterns = {
        "orders.pending",
        "orders.worker",
        "orders.*"
    })
public class OrderObservabilityConfig {
}
~~~

<code>@EnableIntegrationManagement</code> thuộc <code>org.springframework.integration.config</code>. Cần có <code>ObservationRegistry</code> và handler/exporter Micrometer/Tracing đã cấu hình thì observation mới trở thành metric/span có thể xem ở backend. Với Spring Boot Actuator, kiểm tra auto-configuration trước khi tự tạo registry/handlers lần hai. Pattern phải khớp **tên component runtime**, không phải một label suy đoán.

Nếu dùng history trong phiên điều tra, có thể bật hẹp:

~~~java
@EnableMessageHistory({"orders.pending", "orders.worker"})
~~~

Chỉ nên đặt annotation trên một configuration được quản lý có chủ đích. <code>MessageHistory</code> là header ghi những hop đã được theo dõi; nó **không** là audit bền vững hoặc bằng chứng transaction đã commit. History tăng payload header size và chi phí serialization khi message lưu vào JDBC queue.

### Telemetry contract

| Tín hiệu | Nguồn | Câu hỏi trả lời |
|---|---|---|
| Accepted events/s và rejected-before-acceptance/s | Ingress gate | Có thể nhận mới không? Có báo nhầm 202 không? |
| JDBC queue pending count + oldest age | JDBC store hoặc query/adapter đo được | Có backlog, event nào chờ lâu? |
| Poller running/poll count/errors | Endpoint + poller instrumentation | Worker đã start, có đang receive? |
| Business apply successes/s | Transactionally applied events | Throughput nghiệp vụ, không chỉ dequeue |
| Duplicate events skipped/s | Unique constraint logic | Redelivery/timeout có tăng không? |
| Outbox pending, in-progress, retry, oldest age | Bảng <code>outbox_events</code> | Đã apply nhưng chưa publish bao nhiêu? |
| Error rate theo nhóm | Error handler/recovery ledger | Lỗi tạm thời, poison hay downstream outage? |
| Executor active/queued/rejected | Executor binder hoặc custom metric | Có bão hòa ở relay/dynamic branch không? |
| Drain pending/in-flight/remaining | <code>WorkDrainProbe</code> | Đã có thể stop an toàn chưa? |
| Transaction/DB pool latency | DataSource/DB metrics | Nút cổ chai nằm ở SQL, lock, pool hay framework? |

Tên như <code>accepted_events_total</code>, <code>outbox_oldest_age_seconds</code> là **metric do ứng dụng đề xuất**. Spring Integration có các meter/observation riêng khi được cấu hình, nhưng **không** tự đo được transactionally settled logical events cho mô hình nghiệp vụ trên. Legacy Micrometer và Observation API còn có những tên meter khác nhau; kiểm tra meter thật trước khi viết query dashboard.

### Các header và định danh

| Định danh | Ví dụ | Mục đích |
|---|---|---|
| Message ID | UUID do framework tạo | Một message instance cụ thể |
| Business event ID | E42 | Dedupe/idempotency qua redelivery |
| Correlation ID | tenantA:order123 | Nối các thao tác cùng order/batch |
| Trace/span ID | Do tracing system tạo | Chẩn đoán latency xuyên thread/process |
| Outbox ID | order-applied:E42 | Dedupe outbound side effect |
| Flow generation | tenantA:v8 | Fencing lifecycle/cleanup cũ |

Không đưa raw eventId, orderId hoặc tenant UUID có cardinality lớn làm **metric tag** cho mọi message. Đưa vào trace/log có che thông tin nhạy cảm, retention và phân quyền. Tách **business identity** khỏi **telemetry identity** giúp giữ chi phí collector và khả năng tìm kiếm phù hợp.

### Runtime topology graph

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

var snapshot = graphServer.rebuild();
log.info("Integration graph snapshot: {}", snapshot);
~~~

<code>IntegrationGraphServer</code> thuộc <code>org.springframework.integration.graph</code>. Đoạn code giả định bean server đã được tạo trong context. Sau khi register/remove flow động, <code>rebuild()</code> cập nhật graph cache. Graph **không phải distributed trace** và không chứng minh một message cụ thể đã đi qua một cạnh tại thời điểm hiện tại.

## 18. Performance budget và capacity planning

Hồ sơ phải có ngân sách về latency, throughput, queue age, database load và giới hạn recovery; những con số dưới đây **là ngưỡng giả định phục vụ bài tập**, không phải SLA mặc định của Spring.

| SLI/SLO ví dụ | Mục tiêu giả định | Khi vượt ngưỡng |
|---|---|---|
| Intake durable commit p99 | Nhỏ hơn 300 ms | Kiểm tra DB connection pool, disk, lock và serialization |
| Business apply completion p99 | Nhỏ hơn 2 giây | Kiểm tra poll lag, TX duration và query |
| Oldest pending age | Nhỏ hơn 60 giây ở steady state | Throttle ingress hoặc tăng capacity sau khi hiểu bottleneck |
| Outbox publish lag p99 | Nhỏ hơn 30 giây | Kiểm tra relay lease, remote ACK và retry |
| Duplicate side effect count | Bằng 0 | Dừng replay thiếu an toàn và điều tra idempotency |
| Unowned quarantine records | Bằng 0 | Giao owner/replay deadline trước khi đóng incident |

Đo các giá trị ở **boundary nghiệp vụ**: một <code>QueueChannel.send()</code> thành công không phải completion; một handler timer kết thúc có thể chưa bao gồm commit hoặc outbound ACK.

### Công thức ước lượng backlog

Ký hiệu <code>λ</code> là tốc độ event mới đến mỗi giây, <code>μ</code> là tốc độ **terminal completion** mỗi giây, <code>B</code> là backlog. Khi hai tốc độ ổn định:

\[
\Delta B/\Delta t \approx \lambda - \mu.
\]

Nếu <code>μ > λ</code> và không có burst/retry bất thường:

\[
t_{\text{drain}} \approx \frac{B}{\mu-\lambda}.
\]

Ví dụ giả định: backlog 4.000 event, giảm ingress xuống 250 event/s, có khả năng hoàn tất 450 event/s; thời gian drain xấp xỉ 20 giây. Nếu downstream giảm còn 200 event/s, backlog **không drain** mà còn tăng. Công thức này là **capacity estimate**, không phải cam kết thời gian khôi phục; cần quan sát p95/p99, oldest age, retry amplification và transaction contention.

### Những giới hạn cần đo trước khi scale

1. Tăng <code>maxMessagesPerPoll</code> có thể kéo dài lần poll; nếu thiết kế transaction cho cả batch, lock duration có thể tăng.
2. Tăng polling thread/concurrency có thể làm cạn DB pool hoặc tăng contention ở JDBC message store.
3. Thêm <code>ExecutorChannel</code> trước business commit làm thay đổi durability contract, không chỉ performance.
4. Bật <code>MessageHistory</code>, <code>WireTap</code>, log full payload và trace từng hop có chi phí CPU/heap/network.
5. Khi dùng broker, partitioning/consumer group quyết định khả năng mở rộng; tăng worker JVM không tự tăng throughput của một partition có ordering.
6. Retry storm có thể làm workload thực gấp nhiều lần số logical event ingress; cần đo **attempts/s** riêng.

Nếu chỉ tăng queue size để xử lý slow consumer, có thể chỉ kéo dài thời gian trước OOM hoặc JDBC store bloat. Scale đúng dựa trên bottleneck được đo: DB, remote dependency, CPU, lock/hot key, poller hoặc network.

## 19. Verification dossier: bộ test bắt buộc trước nghiệm thu

Một test gọi trực tiếp <code>OrderProcessor.apply()</code> chỉ chứng minh logic JDBC dưới transaction của test. Nó **không chứng minh** adapter/gateway, queue send, polling receive, worker thread và ACK. Vì thế chia test thành các lớp rõ ràng:

| Lớp | Dữ liệu/cơ chế | Điều chứng minh |
|---|---|---|
| Unit | <code>QueueChannel(1)</code>, fake handler, latch | Channel capacity, send/receive, exception sync và race |
| Spring flow | <code>@SpringIntegrationTest</code>, endpoint ID, mock | Wiring, poller auto-start, header propagation, message handler |
| PostgreSQL integration | JDBC store + business schema thật qua Testcontainers | Commit/rollback dequeue, idempotency, outbox và restart |
| Adapter contract | HTTP hoặc broker container thật | 202/ACK/NACK/redelivery và timeout |
| Failure injection | DB unavailable, worker kill, poison event, outbox crash | Recovery không mất/trùng side effect |
| Game day | Tải, rolling deploy, stop/drain, deadlock | Runbook và SLO có thể thực thi |

### 19.1. Unit test: QueueChannel bounded và completion boundary

~~~java
@Test
void queueAcceptsOneMessageAndRejectsWhenFull() {
    QueueChannel queue = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("one").build();
    Message<String> second = MessageBuilder.withPayload("two").build();

    assertTrue(queue.send(first, 0));
    assertEquals(1, queue.getQueueSize());
    assertFalse(queue.send(second, 0));

    assertEquals("one", queue.receive(0).getPayload());
    assertNull(queue.receive(0));
}
~~~

Đoạn này chỉ xác nhận behavior của **in-memory QueueChannel**, không chứng minh durability. <code>send(message, 0)</code> không chờ khi queue đầy. Trong production phải định nghĩa phản ứng khi <code>false</code> thay vì bỏ qua và trả 202.

### 19.2. Test khung PostgreSQL end-to-end

Các đoạn trước có thể ghép vào một Spring Boot application:

~~~java
@SpringBootApplication
public class OrderRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderRuntimeApplication.class, args);
    }
}
~~~

Các class và configuration phải nằm trong **phạm vi component scan** của application; chỉ bật profile <code>durable</code> khi kiểm thử JDBC. Để dùng Testcontainers JUnit Jupiter và chờ assertion, thêm các dependency test tương thích BOM:

~~~kotlin
testImplementation("org.testcontainers:junit-jupiter")
testImplementation("org.awaitility:awaitility")
~~~

Skeleton minh họa:

~~~java
@SpringBootTest(classes = OrderRuntimeApplication.class)
@ActiveProfiles("durable")
@Testcontainers
class DurableOrderFlowIT {

    @Container
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void jdbcProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.datasource.url", db::getJdbcUrl);
        properties.add("spring.datasource.username", db::getUsername);
        properties.add("spring.datasource.password", db::getPassword);
    }

    @Autowired OrderIngress ingress;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("orders.worker")
    SmartLifecycle worker;

    @BeforeEach
    void start() {
        worker.start();
        ingress.open();
    }

    @AfterEach
    void stop() {
        ingress.close();
        worker.stop();
    }

    @Test
    void duplicateIntakeAppliesOnlyOneBusinessEvent() {
        OrderEvent e = new OrderEvent(
            "E-IT-001", "tenant-A", "order-42", 12500);

        assertTrue(ingress.accept(e));
        assertTrue(ingress.accept(e)); // Hai message được enqueue.

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            Integer processed = jdbc.queryForObject(
                "SELECT count(*) FROM processed_events WHERE event_id=?",
                Integer.class, e.eventId());
            Integer outbox = jdbc.queryForObject(
                "SELECT count(*) FROM outbox_events WHERE event_id=?",
                Integer.class, e.eventId());
            assertEquals(1, processed);
            assertEquals(1, outbox);
        });
    }
}
~~~

Các annotation chính: <code>@SpringBootTest</code> của Spring Boot Test, <code>@Testcontainers</code>/<code>@Container</code> của Testcontainers Jupiter, <code>@DynamicPropertySource</code> của Spring Test, <code>@ActiveProfiles</code>, <code>@BeforeEach</code>/<code>@AfterEach</code> của JUnit 5. <code>await()</code> được import tĩnh từ Awaitility.

**Điều kiện tiên quyết tuyệt đối:** PostgreSQL test container phải được **migrate các bảng Spring Integration JDBC và bảng nghiệp vụ** trước lúc <code>JdbcChannelMessageStore</code> start. Dùng Flyway/Liquibase hoặc SQL initializer được cấu hình theo đúng version; đoạn test trên là **khung test** chứ không tự chạy migration. Một application mới chưa có migration sẽ fail khi context start — đây là tín hiệu đúng để sửa fixture.

Không dùng <code>@Transactional</code> trên chính test khi cần quan sát commit độc lập của poller: outer test transaction có thể che giấu kết quả hoặc rollback fixtures ở thời điểm khác với production.

### 19.3. Hai application context liên tiếp — kiểm tra restart thật

Test durable restart phải dùng **cùng database đã tồn tại sau khi context thứ nhất đóng**, không tạo lại schema hoặc xóa queue ở giữa:

~~~text
Context A:
  1. Boot ở profile durable, để orders.worker STOPPED.
  2. Mở admission và accept E-RESTART-1.
  3. Xác nhận enqueue TX commit, business chưa apply.
  4. Đóng context A mà KHÔNG xóa database.

Context B:
  5. Boot cùng DataSource schema, region, groupId và serializer.
  6. Start worker; đợi processed_events + outbox_events có E-RESTART-1.
  7. Gửi lại cùng E-RESTART-1 để mô phỏng client không nhận 202.
  8. Xác nhận chỉ có một row processed và một outbox event.
~~~

Nếu restart làm thay <code>region</code>, <code>groupId</code> hoặc class serialization mà không migration, test có thể trông như không có pending message dù DB còn row. Đây là lý do persistence contract phải được lưu trong kiến trúc và release checklist.

### 19.4. Failure injection matrix

| Mã test | Cách tạo tình huống | Assertion tối thiểu |
|---|---|---|
| FT-01 | Hỏng DB trước enqueue commit | Không trả accepted; client có thể retry; không có half-committed event |
| FT-02 | Client timeout sau durable intake commit | Retry cùng event ID không tạo business/outbox duplicate |
| FT-03 | Handler ném exception sau khi insert dedupe nhưng trước outbox | Transaction rollback; message còn recoverable theo JDBC policy |
| FT-04 | Dừng context sau receive nhưng trước commit | Context mới xử lý lại không tạo double side effect |
| FT-05 | Outbox publish ACK rồi kill trước DB mark | Relay gửi lại có cùng outbox ID; consumer idempotent |
| FT-06 | Poison event luôn thất bại | Không tạo retry vô hạn; quarantine durable có owner |
| FT-07 | Poller <code>autoStartup=false</code> | Queue có thể chứa pending, business chưa chạy; readiness vẫn đóng |
| FT-08 | Đóng gate khi HTTP threads còn submit | Không có accepted mới sau cutoff; request cũ commit/rollback rõ |
| FT-09 | Nhiều context cùng poll một region/group | Không hai business commit cho cùng event; kiểm tra lock/concurrency |
| FT-10 | Executor reject ở outbox/dynamic branch | Không coi task rejected là published; có retry/backlog |
| FT-11 | Tenant generation 7 cleanup khi generation 8 tạo lại | Không destroy resource của generation 8 |
| FT-12 | Schema upgrade đổi serializer | Pending message version cũ đọc/recover được hoặc migration thất bại có kiểm soát |

**Nguyên tắc test bất đồng bộ:** Dùng <code>CountDownLatch</code>, completion future hoặc Awaitility có **deadline rõ**, không dùng <code>Thread.sleep(5000)</code> rồi suy ra một flow đã hoàn tất. Với business transaction, assert từ **connection/transaction độc lập** sau completion; với broker, kiểm tra ACK/offset thực chứ không chỉ log handler.

### 19.5. Test lỗi không có subscriber và errorChannel

Nếu thay <code>orders.pending</code> bằng <code>DirectChannel</code> cho một nhánh khác, stop consumer có thể khiến <code>MessageDispatchingException</code> xuất hiện khi send. Nhưng với <code>QueueChannel</code>, thiếu polling consumer **không** có nghĩa channel thiếu subscriber; triệu chứng đúng là backlog tăng.

Nếu xử lý lỗi của poller phát <code>ErrorMessage</code> tới một error channel, test phải xác nhận **cả** exception gốc, kết quả rollback của dequeue và liệu error handler/recoverer có trả về bình thường hay không. Một error message đã được log không tự chứng minh transaction rollback.

## 20. Runbook on-call: cùng một topology, ba hướng xử lý sự cố

### Bước T0 — khoanh vùng trong những phút đầu

Thu thập incident ID, thời gian lỗi đầu tiên, phiên bản deploy, tenant/partition bị ảnh hưởng, trạng thái readiness/gate và các số liệu sau:

~~~text
flowId / endpointId: orders.worker
inputChannel: orders.pending  (durable / workshop?)
queue_group: orders.pending.v1
queue_region: orders-intake-v1
gate: OPEN / CLOSED
poller_running: true / false
ingress_accepted_per_sec:
business_applied_per_sec:
queue_pending / oldest_age:
outbox_pending / in_progress / oldest_age:
error_attempts / unique_business_events:
db_pool_active / waiting / timeout:
retry_budget / quarantine_count:
deployment_version / owner:
~~~

Nếu chưa biết event đã commit vào JDBC store hay chưa, **không restart/xóa queue hàng loạt**. Nếu đang dùng broker, kiểm tra chính xác ACK/offset/requeue của adapter; nếu dùng in-memory profile, đánh giá rủi ro mất pending khi process chết.

### A. Queue đầy hoặc backlog tăng

| Triệu chứng | Kiểm tra | Hành động có điều kiện |
|---|---|---|
| In-memory queue đầy, send timeout | <code>QueueChannel.getQueueSize()</code>, capacity, consumer state | Giảm ingress, giữ poller chạy, không block sender vô hạn |
| JDBC queue pending tăng | DB I/O/locks, poller, completion throughput, oldest age | Throttle intake, tìm slow handler; không chỉ tăng worker |
| Poller không running | <code>SmartLifecycle.isRunning()</code>, <code>autoStartup</code>, deployment | Start khi dependency/tenant còn hợp lệ, gate vẫn đóng đến khi ready |
| Queue gần trống nhưng latency cao | In-flight TX, DB wait, outbox relay | Đo terminal completion; không suy từ queue depth |
| Một order/tenant bị nghẽn | Lock contention, ordering, correlation hot key | Điều chỉnh partition/concurrency theo business key |

**Không dùng** cách xóa raw rows trong <code>INT_CHANNEL_MESSAGE</code> hoặc thay <code>region</code> để làm queue “trống”. Muốn purge phải có bản đối soát, quyền phê duyệt và recovery plan; nếu đang xử lý, có thể tạo dữ liệu mất/trùng.

### B. Executor reject

Flow chính dùng poller đồng bộ; lỗi <code>TaskRejectedException</code> thường xuất hiện ở **outbox relay, adapter, dynamic branch hoặc custom executor** nếu các phần đó sử dụng worker pool.

1. Xác định executor bean, core/max pool, queue capacity, active/queued/rejected và <code>isShutdown</code>.
2. Phân biệt rejection vì shutdown/lifecycle với rejection vì saturation.
3. Tìm worker đang block ở DB connection pool, HTTP timeout, lock hoặc future chờ task cùng pool.
4. Giảm tốc độ submit, bảo toàn pending trong outbox/durable source.
5. Không chuyển sang <code>DiscardPolicy</code> chỉ để hết lỗi; nó có thể bỏ task im lặng.
6. Cân nhắc <code>CallerRunsPolicy</code> chỉ sau khi kiểm chứng backpressure **và** thay đổi thread/transaction.
7. Mở lại dần khi completed throughput tăng ổn định, queue executor giảm và remote dependency có headroom.

**Không ACK outbound event chỉ vì task đã được executor chấp nhận.** Lời gọi publish có thể lỗi sau handoff. Khi relay ghi <code>PUBLISHED</code> phải dựa vào outcome/ACK của adapter đúng hợp đồng.

### C. Error spike và retry storm

Nhìn **exception gốc đầu tiên** theo timeline, thay vì đếm số dòng log:

| Loại lỗi | Dấu hiệu | Hành động |
|---|---|---|
| Validation/schema | Cùng payload lỗi lặp | Quarantine, không retry vô hạn |
| Dependency 503/timeout | Error attempts tăng, DB/API latency cao | Throttle, bounded retry/backoff, kiểm tra circuit breaker |
| DB lock/transaction timeout | Lock wait, rollback, pending tăng | Đọc DB wait graph/transaction duration, giảm concurrency |
| No-subscriber | Endpoint đã stop hoặc dynamic flow remove | Kiểm tra topology/lifecycle, sửa admission trước stop |
| Error flow failure | Lỗi thứ cấp khi publish <code>ErrorMessage</code> | Giữ cause gốc, sửa error sink và recovery |
| Outbox relay failure | <code>IN_PROGRESS</code> hết lease, pending không giảm | Kiểm tra lease owner, remote ACK, retry state |

Một business event có thể tạo 3 retry attempt, mỗi attempt có thể xuất hiện ở nhiều loggers. Cần đếm **unique event IDs** riêng với attempts. Không đưa eventId làm tag metric để tránh cardinality explosion; sử dụng trace/log và bảng recovery theo ID.

### D. Crash/restart và kiểm tra sau deploy

Trước khi mở ingress ở instance mới:

1. Xác nhận migration schema, serializer version và query provider.
2. Dùng lại đúng JDBC store <code>region</code> và <code>groupId</code>; không reset bảng.
3. Start poller và kiểm tra recovery sink, outbox relay và transaction manager.
4. Reconcile processed event IDs, outbox pending và quarantine theo durable state.
5. Nếu có dynamic tenant flows, rebuild từ config DB cùng generation fencing.
6. Chỉ mở gate khi worker, dependency và telemetry tối thiểu ready.
7. Theo dõi duplicated event skips, backlog age và remote publish lag sau restart.

### SQL dashboard tối thiểu

Không đoán tên cột của bảng Spring Integration <code>INT_</code> ngoài schema phiên bản đã triển khai. Các truy vấn sau chỉ dùng **bảng nghiệp vụ do bài học định nghĩa**:

~~~sql
-- Trạng thái outbox và tuổi record cũ nhất theo từng nhóm.
SELECT state,
       count(*) AS records,
       min(created_at) AS oldest_created_at
FROM outbox_events
GROUP BY state
ORDER BY state;

-- Throughput business commit trong 5 phút.
SELECT count(*) AS applied_events
FROM processed_events
WHERE processed_at >= now() - interval '5 minutes';

-- Những event đang đợi người xử lý thủ công.
SELECT reason_code, count(*) AS events
FROM quarantined_events
WHERE state = 'OPEN'
GROUP BY reason_code;
~~~

Không đưa raw event payload, secret, token hoặc full headers vào incident ticket/log collector. Lưu correlation và ID được phép, thêm quyền truy cập đúng mức.

### Bằng chứng trước khi đóng incident

- Error attempts và reject rate giảm về ngưỡng vận hành;
- Queue pending/oldest age và outbox lag có xu hướng hồi phục;
- Completed business throughput đủ lớn để drain backlog còn lại;
- Không có ACK/commit bất định chưa được đối soát;
- Mọi quarantine/DLQ record còn mở có owner và kế hoạch replay;
- Readiness và dynamic flow state đúng theo config bền vững;
- Ghi rõ bước rollback nếu tăng tải trở lại gây sự cố.

## 21. Mẫu hồ sơ bàn giao ca trực

~~~text
INCIDENT_ID:
PRIMARY_SYMPTOM: QUEUE_BACKLOG | EXECUTOR_REJECT | ERROR_SPIKE | RESTART
FIRST_SEEN_AT:
SERVICE_VERSION / INSTANCES:
FLOW_ID / CHANNEL / ENDPOINT:
TENANT_OR_PARTITION_SCOPE:
MESSAGE_DURABILITY: IN_MEMORY | JDBC | BROKER
INGRESS_RATE / COMMITTED_RATE / OUTBOX_PUBLISHED_RATE:
PENDING / OLDEST_AGE / IN_FLIGHT:
ERROR_CLASS_GROUP / UNIQUE_EVENTS / ATTEMPT_COUNT:
DB_POOL / BROKER / REMOTE_DEPENDENCY_STATUS:
ACK_TRANSACTION_REPLAY_VERIFIED:
MITIGATION / RISKS / ROLLBACK_PLAN:
RECONCILIATION_OWNER / NEXT_CHECK:
RECOVERY_CRITERIA / FINAL_OUTCOME:
~~~

Mẫu cố ý tách **số attempts** khỏi **số event nghiệp vụ** và tách ba mốc durable acceptance, business completion, outbound publishing. Một report “hết lỗi sau restart” không đủ nếu queue in-memory đã mất message hoặc outbox vẫn có pending không owner.

## 22. Architecture Decision Records (ADR)

Một hồ sơ “hoàn chỉnh” không chỉ nêu công nghệ đã chọn mà còn ghi lại **vì sao không chọn phương án khác** và điều kiện để xem xét lại.

| ADR | Quyết định hiện tại | Vì sao | Khi nào cần xét lại |
|---|---|---|---|
| ADR-01 | Java DSL với bean/endpoint ID ổn định | Debug graph/lifecycle/test dễ hơn ID tự sinh | Khi cần topology tenant dynamic hoặc cấu hình bên ngoài |
| ADR-02 | JDBC-backed QueueChannel cho bài thực hành durable | Minh họa rõ receive + business TX cùng PostgreSQL | Khi throughput, lock/contention hoặc chi phí DB vượt budget |
| ADR-03 | Polling consumer xử lý đồng bộ trong TX | Dequeue và business write có thể rollback cùng transaction | Khi xử lý cần async/long-running; phải thiết kế durable handoff khác |
| ADR-04 | Unique business event ID | Chống apply lại khi replay/redelivery | Khi phát hiện ID reuse/conflicting payload; thêm fingerprint/version |
| ADR-05 | Transactional outbox | DB write và event-to-publish cùng commit | Khi có nền tảng CDC/outbox hoặc transaction broker chuyên biệt |
| ADR-06 | Admission gate mặc định CLOSED | Không nhận sớm hoặc sau shutdown | Với nhiều node cần distributed fencing và broker pause |
| ADR-07 | Bounded retry và durable quarantine | Không tạo retry storm khi có poison message | Theo error budget và hợp đồng dịch vụ bên ngoài |
| ADR-08 | Observation chọn lọc, metric low-cardinality | Tránh overhead, cardinality và lộ payload | Khi cần debug theo sự cố, chỉ mở tạm có thời hạn |
| ADR-09 | Flow riêng tenant chỉ cho nhánh tùy chọn | Tránh nhân hàng nghìn endpoints nếu không cần | Khi isolation/security/SLA thực sự cần per-tenant flow |

**ADR-02 cần sự tỉnh táo về scale:** Spring Integration JDBC channel là lựa chọn hỗ trợ persistence/rollback nhưng tài liệu không khuyến nghị database-as-queue như giải pháp mặc định cho tải lớn. Trước khi scale hàng nghìn message/giây hoặc nhiều node, phải benchmark với broker/JMS/AMQP/Kafka, đánh giá MVCC, indexes, vacuum và partition/ordering.

### Risk register và việc phải hoàn thành trước production

| Rủi ro | Hiện trạng code minh họa | Hardening bắt buộc |
|---|---|---|
| Conflicting duplicate ID | Processor chỉ dedupe theo event ID | Lưu canonical payload fingerprint, quarantine nếu ID trùng nhưng nội dung khác |
| Order updates lệch thứ tự | Upsert last-writer-wins | Thêm version/conditional update hoặc partition theo order |
| Outbox relay chưa có class chạy đầy đủ | Đã mô tả claim SQL + state machine | Viết relay, lease fencing, remote ACK, retry/backoff và test kill-point |
| Poison message retry mãi | Đã thiết kế quarantine và policy | Triển khai durable attempts ledger/recovery atomic, test không storm |
| Drain probe chỉ là interface | Coordinator phụ thuộc probe | Implement theo queue, in-flight TX, adapter ACK/recovery ledger; test race |
| Multi-node admission | Read/write lock chỉ trong JVM | Distributed owner state, broker pause và fencing |
| Message serialization qua deploy | Java record/serializer minh họa | Version compatibility, secure deserialization và migration |
| Queue capacity trong profile durable | Chưa có hard global cap | Throttle ingress, storage quota, oldest age alert, scale/test |
| Dữ liệu nhạy cảm trong log/DLQ | Chưa thể hiện chính sách tổ chức | Redaction, encryption, retention, access control |
| Migration trong integration test | Test skeleton cần schema | Flyway/Liquibase trước store startup, checksum và rollback plan |
| Exactly-once outbound | Outbox cho at-least-once | Remote idempotency/reconciliation theo outbox ID |

Những hàng còn “phải triển khai” là **đầu việc thực tế**, không nên tự đánh dấu PASS chỉ vì bài học có ví dụ. Đây là cách giữ hồ sơ trung thực: phần code là reference implementation, còn production readiness cần bài test và đối soát phù hợp môi trường.

### Chính sách retention tối thiểu

| Dữ liệu | Khi nào mới được xóa? |
|---|---|
| <code>processed_events</code> | Sau khi vượt mọi cửa sổ redelivery/replay được hỗ trợ; phải tính cả outbox và client retry |
| <code>outbox_events</code> | Sau khi publish terminal và vượt thời gian cần remote dedupe/reconciliation |
| <code>quarantined_events</code> | Sau khi có quyết định xử lý và retention/compliance cho phép |
| <code>INT_CHANNEL_MESSAGE</code> | Qua API/store mechanism phù hợp; không raw DELETE trong lúc poller chạy |
| <code>MessageGroupStore</code> fragments | Sau release/expire theo policy, xử lý late fragment rõ ràng |
| Message history/traces/logs | Theo mục đích điều tra và chính sách bảo mật, không lưu payload vô hạn |
| Tenant flow config/generation | Sau khi cleanup/reconciler xác nhận resource và work không còn cần |

Nếu giữ dedupe marker ít hơn thời gian client có thể retry, một event cũ có thể được apply lại sau khi marker bị purge. Nếu xóa outbox trước khi remote ACK/đối soát, hệ thống mất khả năng publish lại. Retention là **business contract**, không phải chỉ là job dọn database.

## 23. Lộ trình thực hành theo năm vòng

### Vòng 1 — Topology chạy được

Tạo domain event, in-memory <code>QueueChannel</code>, poller và handler test. Ghi manifest bean IDs, vẽ hai ranh giới sync/async và test gửi/nhận. Chưa quảng bá dữ liệu là bền vững.

**Đạt vòng 1 khi:** Event hợp lệ đi qua đúng endpoint, endpoint có thể start/stop, queue full được xử lý và exception không bị coi là success.

### Vòng 2 — Durable state và idempotency

Chạy PostgreSQL migration, chuyển sang <code>JdbcChannelMessageStore</code>, thêm transaction advice cho poller, <code>processed_events</code>, <code>orders</code> và outbox. Đối soát với event ID.

**Đạt vòng 2 khi:** Đã kiểm chứng commit/rollback JDBC thật và cùng event ID không tạo hai business side effect dù intake bị lặp.

### Vòng 3 — Recovery và lifecycle

Thêm admission, readiness, WorkDrainProbe, retry policy, quarantine và restart reconciliation. Gây lỗi DB, kill process giữa transaction, thử startup từ queue cũ.

**Đạt vòng 3 khi:** Có bằng chứng không báo accepted trước durable commit; pending có thể recover; stop không phá hủy dữ liệu chưa settled.

### Vòng 4 — Outbox và correlation

Triển khai relay lease/claim, remote idempotency và test crash sau publish trước DB mark. Nếu cần batch, bổ sung aggregator store và group timeout riêng.

**Đạt vòng 4 khi:** Outbox tồn tại sau business commit, publish được thử lại và remote consumer không xử lý trùng theo outbox/event ID.

### Vòng 5 — Observability và vận hành

Thêm metric accepted/applied/outbox, trace/header propagation, graph snapshot, alert lag, runbook và game day. Chạy benchmark baseline với cùng workload trước/sau thay đổi concurrency/logging.

**Đạt vòng 5 khi:** On-call có thể phân biệt queue backlog, executor reject và error spike; có timeline/snapshot để đối soát sau sự cố.

### Mẫu cấu trúc bài nộp của học viên

~~~text
01-topology.md             sơ đồ + manifest channel/endpoint/thread
02-contracts.md            input/output, accepted/committed/published
03-state-and-schema.md     table, region/group, retention, serializer
04-lifecycle.md            state machine, readiness/drain/shutdown
05-recovery-matrix.md      crash-point, retry, DLQ, replay
06-tests.md                unit/integration/restart/game-day results
07-observability.md        metrics, logs, trace, dashboard
08-operations-runbook.md   queue, executor, error, deployment
09-adr.md                  decisions, tradeoffs, risk register
~~~

Danh sách trên là **gợi ý artifact khi làm bài tập**, không phải các file mà worker đã tạo trong module. Hồ sơ kiến thức hiện tại vẫn được lưu dưới dạng một bài Markdown đúng đường dẫn được giao.

## 24. Acceptance gate cuối bài

### Ma trận nghiệm thu

| ID | Điều kiện để PASS | Cách kiểm chứng | Mức ưu tiên |
|---|---|---|---|
| AC-01 | Có topology manifest nêu channel, endpoint, owner và thread | Review sơ đồ + Spring Integration graph | Bắt buộc |
| AC-02 | Client chỉ nhận accepted sau durable intake commit | Test DB fail/timeout và retry client | Bắt buộc |
| AC-03 | Poller transaction chứa receive + business write đồng bộ | JDBC rollback integration test | Bắt buộc |
| AC-04 | Duplicate event không làm tăng số business/outbox records | Concurrent/restart idempotency test | Bắt buộc |
| AC-05 | Retry transient có giới hạn; poison vào durable quarantine | Exhaustion + poison event tests | Bắt buộc |
| AC-06 | Outbox publish được replay, remote consumer chống trùng | Crash after-publish-before-mark test | Bắt buộc |
| AC-07 | Gate đóng trước stop; pending còn recovery path | Shutdown/race test | Bắt buộc |
| AC-08 | Restart cùng region/group/serializer khôi phục queue | Hai Spring contexts, cùng PostgreSQL | Bắt buộc |
| AC-09 | Tenant flow cleanup không ảnh hưởng shared resource | Multi-tenant generation fencing test | Khi có dynamic flows |
| AC-10 | Metric/log/trace định vị được queue, worker, error và outbox | Dashboard + game-day evidence | Bắt buộc |
| AC-11 | Có benchmark latency/throughput/DB load ở workload mục tiêu | Load test và capacity report | Bắt buộc trước production |
| AC-12 | Retention, serializer upgrade và rollback đã được phê duyệt | Migration rehearsal + ADR | Bắt buộc trước production |

**Cách ghi trạng thái:** Với mỗi mục, điền <code>NOT_RUN</code>, <code>PASS</code>, <code>FAIL</code> hoặc <code>BLOCKED</code> kèm bằng chứng. Nội dung bài là **thiết kế và ví dụ**, không phải log chạy test. Tuyệt đối không tự chuyển thành PASS nếu chưa chạy bài kiểm thử ở môi trường tương ứng.

### Checklist tổng hợp

- [ ] Phân biệt <code>send()</code>, durable accepted, handler completed, transaction committed và outbound ACK.
- [ ] Có tên channel/endpoint ổn định và sơ đồ thread, error channel, recovery.
- [ ] Dùng đúng store cho queue và aggregator; region/groupId giữ ổn định qua restart.
- [ ] Database migration hoàn thành trước store startup; serializer có quy trình tương thích phiên bản.
- [ ] Ingress đóng mặc định, chỉ mở khi consumer, DB và recovery đã sẵn sàng.
- [ ] Poller transaction đã được kiểm chứng với cùng DataSource/manager và không cắt ngang bằng async handoff.
- [ ] Event ID có unique constraint; conflicting duplicate và ordering có chính sách.
- [ ] Outbox được commit cùng business state; relay có lease, ACK và idempotent remote consumer.
- [ ] Retry bounded qua mọi lần poll/restart, không chỉ vài attempt trong handler advice.
- [ ] Poison messages được quarantine bền vững; error flow không nuốt lỗi trước khi recovery an toàn.
- [ ] Drain không chỉ nhìn queue size mà xác minh in-flight, TX và durable replay.
- [ ] Shutdown không đóng scheduler/executor/DataSource shared khi tenant còn dùng.
- [ ] Dynamic flows có generation/owner fencing và reconciler từ state bền vững.
- [ ] Metrics/trace/log chỉ thu dữ liệu cần thiết, tránh high-cardinality tags và lộ payload nhạy cảm.
- [ ] Có test crash, duplicate, schema drift, rolling deploy, queue overload và outbox replay.
- [ ] Có runbook on-call, người sở hữu DLQ/quarantine và điều kiện đóng incident.

**Kết luận:** Một hồ sơ Spring Integration runtime hoàn chỉnh là sự kết hợp của **topology có tên và ranh giới thread rõ ràng; lifecycle có readiness–quiesce–drain; state bền vững có transaction và idempotency; recovery có retry/quarantine/outbox; observability đủ để chẩn đoán; và runbook có bằng chứng nghiệm thu**. Bài thực hành thành công khi người học có thể chứng minh message ở đâu và sẽ được xử lý ra sao **sau một lỗi bất kỳ**, chứ không chỉ khi flow chạy đúng trong tình huống lý tưởng.

## Tài liệu tham khảo chính thức

- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html)
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration — Advice Chain and Retry](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Spring Integration — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
