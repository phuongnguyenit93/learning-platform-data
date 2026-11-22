# Phân tách flow stateless và stateful trong Spring Integration runtime

## 1. Mục tiêu thiết kế: state nằm ở đâu, ai sở hữu và ai khôi phục?

Trong module **SPRING_INTEGRATION_RUNTIME**, message được điều phối qua channel, endpoint, consumer, poller và executor. Các thành phần này có thể chạy đồng bộ, bất đồng bộ, qua broker hoặc dựa vào message store. Một thiết kế tốt không chỉ trả lời “message đi đâu?” mà còn trả lời **“state cần để xử lý message được giữ ở đâu, trong bao lâu và điều gì xảy ra khi instance restart?”**

Chủ đề **Thiết kế runtime → Phân tách flow stateless và stateful** tập trung vào hai loại xử lý:

- **Stateless processing:** kết quả của mỗi lần gọi được quyết định bởi input và dependencies tại lần gọi đó, không cần giữ tiến độ riêng của từng logical workflow trong bộ nhớ của handler qua các message. Ví dụ chuẩn hóa payload, validate schema, map field, áp dụng routing rule thuần.
- **Stateful processing:** phải lưu/tham chiếu thông tin từ message khác, các lần thử trước, hoặc trạng thái nghiệp vụ qua thời gian. Ví dụ aggregator chờ đủ các phần, resequencer giữ messages ngoài thứ tự, dedupe bằng metadata store, process manager chờ callback, delayed message scheduler, idempotent receiver.

**Điểm cốt lõi:** *stateless handler* không đồng nghĩa *stateless end-to-end flow*. Một transformer thuần có thể nhận message từ `QueueChannel` bền vững và phát sang một aggregator có `MessageGroupStore`; flow tổng thể vẫn có state ở queue, group store, lock registry và các tài nguyên nghiệp vụ. Ngược lại, một handler không có `Map` field vẫn có thể phụ thuộc database state và vì thế không phải phép biến đổi thuần theo nghĩa nghiệp vụ.

### Câu hỏi thiết kế cần trả lời trước khi viết code

1. Một message có thể xử lý độc lập, hay cần **nhiều message cùng correlation key**?
2. State chỉ cần trong thời gian xử lý một invocation, hay phải sống qua message tiếp theo?
3. Khi pod restart, state có phải được phục hồi không?
4. Có nhiều JVM cùng xử lý một group/key hay không; ai khóa và ai phát hành kết quả?
5. Cần giữ thứ tự, chống duplicate, timeout hay giải phóng group không bao giờ hoàn thành?
6. Message được ack/commit ở thời điểm nào; lỗi/retry có thể làm side effect lặp không?
7. State tăng đến bao nhiêu, được dọn khi nào, và ai chịu chi phí lưu trữ/khóa?

~~~mermaid
flowchart LR
    P["Producer / ingress"] --> N["Stateless island\nnormalize • validate • route"]
    N --> Q["Durable queue / channel\nkhi cần"]
    Q --> S["Stateful island\naggregate • resequence • dedupe"]
    S --> O["Stateless island\nformat • dispatch"]
    D[("MessageGroupStore / MetadataStore")] <--> S
    L["LockRegistry / transaction"] -.-> S
    O --> R["Outbound adapter"]
    M["Metrics / traces / operations"] -.-> N
    M -.-> S
    M -.-> O
~~~

Đây là **sơ đồ phân tách trách nhiệm**, không có nghĩa mọi flow đều cần một queue bền vững hay database. Với workload nhỏ, có thể dùng toàn bộ trong một JVM; với yêu cầu durability và multi-node, đường tách state cần rõ ngay từ thiết kế.

## 2. Định nghĩa chính xác: stateless theo đơn vị nào?

| Phạm vi | “Không có state” có nghĩa gì? | Ví dụ và lưu ý |
| --- | --- | --- |
| **Method invocation** | Không dùng giá trị còn lại từ invocation trước | `trim`, decode JSON, validate dữ liệu |
| **Handler object** | Bean không giữ business progress mutable giữa messages | Stateless `@Transformer`, `@ServiceActivator` |
| **Message pipeline** | Một message đi qua flow không cần message khác | Simple enrichment và one-to-one conversion |
| **Runtime infrastructure** | Không có pending queue, retry state hoặc channel storage | Rất hiếm khi hoàn toàn đúng với flow async |
| **Business process** | Không cần truy trạng thái workflow lâu dài | Gửi một thông báo độc lập |
| **Distributed system** | Không có state cần đồng bộ giữa JVM | Có thể stateless tại app nhưng DB/broker vẫn stateful |

Đừng dùng từ “stateless” mà không nói **scope**. Ví dụ:

~~~java
String normalize(String value) {
    return value.trim().toUpperCase(Locale.ROOT);
}
~~~

Hàm trên *gần như thuần* với input `String` và `Locale.ROOT`. Nhưng:

~~~java
Order enrich(Order order) {
    Customer customer = customerRepository.findById(
            order.customerId()).orElseThrow();
    return order.withCustomerTier(customer.tier());
}
~~~

Bean vẫn không giữ mutable field giữa requests nhưng kết quả phụ thuộc **state của database**. Handler ở đây *application-instance stateless* nhưng *business-state-dependent*. Cần đánh giá transaction, consistency và cache khi replay.

### `Message` là dữ liệu, không phải state store

Spring Messaging sử dụng `Message<T>` gồm payload và immutable `MessageHeaders` ở mức API. Headers như `correlationId`, `sequenceNumber`, `replyChannel` là metadata đi cùng một message. Chúng **không tự tạo persistent workflow state**.

Một message giữ `correlationId=batch-42` chỉ là **khóa tra cứu state**; các parts đã đến chưa phải nằm trong `MessageGroupStore` hay hệ thống khác.

## 3. Dấu hiệu để nhận biết bước xử lý cần state

Một bước processing là **stateful theo logical workflow** nếu phải trả lời bất kỳ câu hỏi nào sau:

- “Đã nhận đủ N thành phần của batch chưa?”
- “Sequence 3 đã đến, có cần đợi sequence 2 không?”
- “Event ID này đã xử lý trước đây chưa?”
- “Đã gửi request và đang chờ callback/timeout từ service khác chưa?”
- “Correlation group đã hết hạn hoặc được đánh dấu hoàn tất chưa?”
- “Nhóm message nào cần release sau một khoảng thời gian?”
- “Lần thử trước đã commit nhưng acknowledgement bị mất chưa?”
- “Sau restart, pending work cần tiếp tục ở trạng thái nào?”

Những câu trả lời này thường không nên nằm trong một `HashMap` field của handler chạy nhiều pods, nếu mất state sau restart là không chấp nhận được.

### Bảng phân loại nhanh các EIP trong Spring Integration

| Component / pattern | Tính chất | State nằm ở đâu? |
| --- | --- | --- |
| Transformer thuần | Thường stateless | Payload/headers trong invocation |
| Filter với predicate thuần | Thường stateless | Input và routing decision |
| Router theo header/payload | Thường stateless | Quy tắc chọn channel |
| Enricher gọi DB | Bean có thể stateless, nghiệp vụ dựa trên state | DB/cache phía dependency |
| Service activator thuần | Có thể stateless | Invocation |
| `DirectChannel` | Không phải persistent message queue | Dispatcher/subscription runtime |
| `ExecutorChannel` | Bất đồng bộ; có pending tasks | Executor queue và active workers |
| `QueueChannel` | Stateful về chờ xử lý | In-memory queue hoặc store cấu hình |
| Aggregator | **Stateful** | `MessageGroupStore`, correlation groups |
| Resequencer | **Stateful** | Message group và sequence state |
| Delayer | **Stateful** | Scheduler/delayed messages, store nếu cấu hình |
| Idempotent receiver | **Stateful** | `MetadataStore`/dedupe store |
| Accept-once file filter | **Stateful** | Memory hoặc persistent metadata store |
| Gateway đang đợi reply | Stateful tạm thời về request/reply | Pending reply context/correlation |
| Outbound TCP client | **Connection stateful**, dù business handler stateless | Socket/session/connection factory |
| Transactional handler | State tài nguyên trong transaction | DB/broker/transaction manager |

**Không nhất thiết dùng stateful EIP để xử lý mọi logic có đọc database.** Có thể tách: stateless validation/enrichment ở trước; stateful aggregation hoặc workflow coordination ở một boundary độc lập.

## 4. Vì sao cần phân tách “stateless island” và “stateful island”?

Giả sử xử lý các line item của nhiều đơn hàng. Mỗi line item cần chuẩn hóa và validate độc lập, sau đó phải **gom đủ ba item** của cùng `batchId` trước khi xuất một kết quả.

Một flow nguyên khối dễ có dạng:

~~~java
class BadOrderHandler {
    private final Map<String, List<String>> parts = new HashMap<>();

    void handle(Message<String> message) {
        String batchId = (String) message.getHeaders().get("batchId");
        String normalized = message.getPayload().trim().toUpperCase();
        parts.computeIfAbsent(batchId, key -> new ArrayList<>())
             .add(normalized);

        if (parts.get(batchId).size() == 3) {
            sendBatch(parts.remove(batchId));
        }
    }
}
~~~

Đoạn trên là **anti-pattern minh họa**; không import đầy đủ. Những vấn đề:

1. `HashMap`/`ArrayList` không thread-safe khi có `ExecutorChannel`, nhiều consumers hoặc poller concurrency.
2. Restart process làm mất toàn bộ parts chưa đủ batch.
3. Trong nhiều pods, mỗi instance chỉ nhìn thấy một phần event.
4. “Đủ 3” tính cả duplicate nếu broker redeliver.
5. `remove()` trước khi downstream commit có thể làm mất output khi lỗi.
6. Không có expiry, memory có thể tăng mãi với group chưa đủ.
7. Khó quan sát group age, group size, retry attempts và lock contention.
8. Không có hợp đồng rõ về arrival order, invalid event và partial batch.

Thay vì đặt tất cả vào một singleton mutable handler, tách thành:

~~~mermaid
flowchart LR
    I["rawItems"] --> T["Stateless transformer"]
    T --> V["Stateless validation"]
    V --> C["normalizedItems channel"]
    C --> A["Stateful Aggregator"]
    A --> B["completedBatches"]
    B --> O["Stateless output formatter"]
    O --> X["Outbound sender"]
    G[("MessageGroupStore")] <--> A
    K["LockRegistry"] -.-> A
    E["Error / discard flow"] -.-> V
    E -.-> A
~~~

### Lợi ích của ranh giới rõ

- **Scale riêng:** CPU cho normalize có thể scale bằng stateless workers; aggregator bị ràng buộc bởi correlation key và message store.
- **Đổi hạ tầng:** từ in-memory `SimpleMessageStore` trong demo sang store bền vững mà không viết lại transformer.
- **Thử lỗi:** cho aggregator chết giữa batch, xác minh recovery; phần stateless vẫn test unit dễ dàng.
- **Quan sát:** thống kê input rate, group pending, group expiration, output rate ở đúng đoạn.
- **Phân quyền state:** không cho một handler nghiệp vụ tự mutate một map ngoài transaction và lock policy.

## 5. Phân loại state theo vòng đời và độ bền

| Loại state | Sống bao lâu | Công cụ có thể dùng | Rủi ro |
| --- | --- | --- | --- |
| Local invocation | Vài microseconds/seconds | Biến local | Không cần chia sẻ; không persist |
| Ephemeral session | Trong vòng đời socket/connection | TCP connection factory, adapter | Disconnect làm mất session |
| In-memory queue/group | Tới khi JVM dừng hoặc cleanup | `QueueChannel`, `SimpleMessageStore` | Restart mất pending data |
| Persistent message group | Qua nhiều invocations/restart | `JdbcMessageStore`, Redis/Mongo store tùy module | Serializer/migration/expiry/locking |
| Deduplication metadata | Theo retention window | `MetadataStore` persistent | TTL sai gây trùng hoặc giữ state mãi |
| Business transaction | Đến commit/rollback | RDBMS + transaction manager | Partial side effect/replay |
| Long-running saga state | Giờ/ngày/tuần | Durable workflow store/process manager | Timeout/cancel/versioning |
| Observation state | Theo trace/span hoặc history retention | Micrometer, logs, trace backend | Mất correlation hoặc cardinality cao |

Không phải cứ dùng Redis là có transaction semantics mong muốn. **Store type, transaction manager, lock registry, serialization và retry** phải được kiểm chứng cùng nhau.

### `MessageStore` và `MetadataStore` khác nhau

- **`MessageStore` / `MessageGroupStore`:** lưu message hoặc tập messages theo group; aggregator/resequencer cần xem members, count, release và expiry.
- **`MetadataStore`:** key-value nhỏ dùng giữ metadata, ví dụ marker file đã xử lý hoặc event ID đã được chấp nhận.
- **Database nghiệp vụ:** lưu order/payment state thực tế; không thay bằng `MessageGroupStore` chỉ vì nó đã lưu vài messages.
- **Broker:** giữ backlog và delivery/ack state; không tự quản lý correlation/release strategy của aggregator trong JVM.

Dùng đúng loại store để giữ invariant nghiệp vụ, không gom tất cả vào một `Map<String, Object>` dùng chung.

## 6. Ba nguyên tắc thiết kế state boundary

### Nguyên tắc A: ranh giới rõ ràng giữa pure transform và group coordination

Ở phần stateless:

- Input và output types/headers rõ ràng.
- Không giữ mutable per-order state trong singleton bean.
- Kết quả deterministic nếu có thể.
- Nếu có external lookup, ghi rõ consistency/caching và timeout.
- Khi exception, caller/error flow biết xử lý lại message đơn.

Ở phần stateful:

- Có **correlation strategy** được công bố.
- Có **release condition** và **expiry/timeout policy**.
- Có owner của group state và concurrency control.
- Có store durability, recovery/replay và dedupe nếu bắt buộc.
- Output được phát dưới transaction/ack contract rõ.
- Late message và duplicate được xử lý có chủ đích.

### Nguyên tắc B: không đưa state qua channel mà không biết nghĩa của channel

`DirectChannel` thường chạy handler đồng bộ; `ExecutorChannel` tạo async thread boundary; `QueueChannel` giữ message chờ poller; broker tách process. Mỗi lựa chọn thay đổi transaction propagation, failure visibility, queue wait và lifecycle.

### Nguyên tắc C: xác định tính nhất quán trước khi tối ưu throughput

Một group kết thúc khi đủ N messages **chỉ đúng nếu N là số phần độc nhất hợp lệ**, không phải số deliveries. Khi có at-least-once transport, phần bị redeliver có thể tính hai lần nếu không dedupe. Thiết kế luôn bắt đầu từ business invariant, sau đó mới tính concurrency và scale.

## 7. Correlation key: định danh logical group

Aggregator cần biết message nào thuộc cùng group. Trong Spring Integration, `correlationId` header thường được dùng để liên kết messages; splitter cũng có thể gắn `sequenceNumber` và `sequenceSize` cho các phần được tạo.

Ví dụ message:

~~~java
Message<String> part = MessageBuilder
        .withPayload("  line-1  ")
        .setHeader("batchId", "batch-42")
        .setHeader("eventId", "evt-line-1")
        .setHeader("sequenceNumber", 1)
        .setHeader("sequenceSize", 3)
        .build();
~~~

Các string `"batchId"`, `"sequenceNumber"`, `"sequenceSize"` trên là headers ứng dụng trong snippet. Trong code sản xuất, nếu cần dùng các hằng chuẩn nên tham chiếu `IntegrationMessageHeaderAccessor.CORRELATION_ID`, `IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER` và `...SEQUENCE_SIZE` thay vì tự đánh vần để tránh sai tên. Khi dùng splitter chuẩn, nhiều header sequence/correlation được tạo tự động.

Câu hỏi cần trả lời:

- `batchId` có **duy nhất trong retention window** không?
- Nếu một order gồm 3 line items, số 3 được lấy từ đâu?
- Message có thể đến ngoài thứ tự không?
- Nếu batch `batch-42` đã hoàn tất và một duplicate đến muộn, có mở group mới không?
- Nếu một batch không bao giờ đủ, expire theo thời gian hay gửi partial result?
- Nếu consumer chuyển giữa pods, state theo `batchId` ở store nào?

### Tránh collision

Một ID kiểu `"42"` có thể trùng giữa tenants/years. Nên ghép namespace có ý nghĩa hoặc dùng globally unique logical key như:

~~~text
correlationKey = tenantId + ":" + orderId + ":" + batchVersion
~~~

Không chứa thông tin bí mật trong raw correlation header nếu header có thể đi ra broker/log. ID phải ổn định qua retry và redelivery.

## 8. Aggregator: phần stateful đầu tiên

Spring Integration Aggregator là EIP thu thập messages cùng correlation group trong `MessageGroupStore`, áp dụng `ReleaseStrategy` và tạo output khi điều kiện thỏa.

~~~mermaid
flowchart TD
    M1["part A / batch-42"] --> AG["Aggregator"]
    M2["part B / batch-42"] --> AG
    M3["part C / batch-42"] --> AG
    AG <--> ST[("MessageGroupStore\nbatch-42 -> members")]
    AG --> R{"ReleaseStrategy?"}
    R -->|Chưa| W["Giữ group pending"]
    R -->|Đủ| OP["Build aggregate result"]
    OP --> OUT["completedBatches"]
    OUT --> ACK["Output processing + business commit"]
~~~

### CorrelationStrategy

Hàm chọn group ID phải ổn định, null handling rõ ràng. Ví dụ lấy header:

~~~java
CorrelationStrategy byBatchId =
        message -> message.getHeaders().get("batchId");
~~~

Nếu header null, không tạo một group chung `null` cho tất cả unknown messages. Route invalid messages sang discard/error flow hoặc reject trước aggregator.

### ReleaseStrategy

Một release strategy có thể dựa vào số phần đã nhận:

~~~java
ReleaseStrategy fixedThreeParts =
        group -> group.size() >= 3;
~~~

Đây là **quy tắc demo**, không an toàn khi duplicate delivery được tính như một phần độc lập. Với nghiệp vụ, cần kiểm tra **distinct sequence numbers/event IDs**, expected count và invariant trước release.

### OutputProcessor

Khi release, `MessageGroupProcessor` tạo output từ các phần. Có thể dùng default processor của aggregator cho demo, hoặc custom processor quyết định thứ tự và dữ liệu cần giữ. Không suy rằng aggregation output nhất định là một string, một list có thứ tự đã chuẩn hóa hay một message giữ toàn bộ headers gốc; phải kiểm tra processor và API version.

## 9. Java 17 + Spring Boot: phân tách hai IntegrationFlow

Ví dụ sau chạy với Spring Boot có dependency Spring Integration core/starter tương thích. Tạo file `StatelessStatefulFlowDemoApplication.java` trong package `demo.integration`.

**Mục tiêu kỹ thuật:** một flow stateless chuẩn hóa từng line; một flow stateful gom đúng **ba messages cùng `batchId`**; output được đưa vào `QueueChannel` cho `ApplicationRunner` nhận. Dùng `SimpleMessageStore` in-memory để minh họa; **không** coi đây là giải pháp bền vững qua restart.

~~~java
package demo.integration;

import java.util.List;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class StatelessStatefulFlowDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StatelessStatefulFlowDemoApplication.class, args);
    }

    @Bean("rawLines")
    MessageChannel rawLines() {
        return new DirectChannel();
    }

    @Bean("normalizedLines")
    MessageChannel normalizedLines() {
        return new DirectChannel();
    }

    @Bean("completedBatches")
    PollableChannel completedBatches() {
        return new QueueChannel();
    }

    @Bean
    MessageGroupStore batchGroups() {
        // Demo only: reset state when JVM restarts.
        return new SimpleMessageStore();
    }

    @Bean
    IntegrationFlow normalizationFlow() {
        return IntegrationFlow.from("rawLines")
                .transform(String.class,
                        value -> value.trim().toUpperCase(Locale.ROOT))
                .channel("normalizedLines")
                .get();
    }

    @Bean
    IntegrationFlow aggregationFlow(MessageGroupStore batchGroups) {
        return IntegrationFlow.from("normalizedLines")
                .aggregate(spec -> spec
                        .correlationStrategy(m ->
                                m.getHeaders().get("batchId"))
                        .releaseStrategy(group -> group.size() >= 3)
                        .messageStore(batchGroups)
                        .expireGroupsUponCompletion(true))
                .channel("completedBatches")
                .get();
    }

    @Bean
    ApplicationRunner demonstrate(
            @Qualifier("rawLines") MessageChannel input,
            @Qualifier("completedBatches") PollableChannel output) {

        return args -> {
            String batchId = "batch-42";

            for (String value : List.of(
                    " red ", " blue ", " green ")) {

                boolean accepted = input.send(
                        MessageBuilder.withPayload(value)
                                .setHeader("batchId", batchId)
                                .setHeader("eventId",
                                        "evt-" + value.trim())
                                .build());

                if (!accepted) {
                    throw new IllegalStateException(
                            "Input channel rejected a part");
                }
            }

            Message<?> result = output.receive(2_000);
            if (result == null) {
                throw new IllegalStateException(
                        "Batch was not released");
            }

            System.out.println(
                    "AGGREGATED payload=" + result.getPayload());
        };
    }
}
~~~

### Lưu ý khi dùng với phiên bản Spring Integration mới

Ví dụ sử dụng `IntegrationFlow.from(...)` và các endpoint specs của Java DSL. Không thêm import `org.springframework.integration.dsl.IntegrationFlows` theo các hướng dẫn đời cũ nếu API này không có ở version đang dùng. Các overload `aggregate`, `correlationStrategy`, `releaseStrategy` và cấu hình `MessageGroupStore` cần được kiểm chứng với Spring Integration BOM thực tế trong quá trình chạy build/QA.

### Điều gì xảy ra ở mỗi event?

1. `ApplicationRunner` gửi ba line messages lên `rawLines`.
2. `DirectChannel` dispatch đồng bộ qua stateless transform.
3. Transformer tạo payload chữ hoa đã `trim` và chuyển tiếp headers (bao gồm `batchId`) theo contract của Spring Integration.
4. Stateful aggregator chọn group bằng `batchId`.
5. `SimpleMessageStore` giữ các parts cho tới khi đủ ba.
6. `ReleaseStrategy` trả true, aggregator tạo kết quả và gửi tới `completedBatches`.
7. `QueueChannel.receive(timeout)` nhận output.
8. Sau release, cấu hình `expireGroupsUponCompletion(true)` yêu cầu cleanup group theo implementation; **late duplicate policy vẫn cần thiết trong production**.

Kết quả có thể có dạng:

~~~text
AGGREGATED payload=[RED, BLUE, GREEN]
~~~

**Không hardcode exact payload string hoặc order nếu code dùng concurrent delivery**. Default aggregation processor, headers và thứ tự output có thể thay đổi theo flow/config. Trong demo gửi tuần tự cùng JVM, kết quả list được diễn giải theo ý tưởng tổng quát.

### Ghi chú production

- `SimpleMessageStore` ở đây chỉ giữ state trong memory, **mất khi restart**.
- Một group với 2/3 parts sẽ treo nếu không có timeout/expiry policy.
- Duplicate event có thể làm `size() == 3` sai logic.
- Không đặt `QueueChannel` in-memory trước outbound side effect nếu cần persistence qua restart.
- Cần ownership/locking khi nhiều nodes cùng xử lý một group trong shared store.
- Cần transaction hoặc outbox/durable workflow nếu việc release và gửi output không được phép mất.

## 10. Chuẩn bị dependency và chạy demo

Nếu dùng dự án Spring Boot 3.x tương thích Spring Integration 6.x, có thể khai báo các dependencies theo BOM do Spring Boot quản lý:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Không tự ghép Spring Integration major version khác với Spring Boot/Spring Framework đang chạy. Khi chạy lớp `StatelessStatefulFlowDemoApplication`, kỳ vọng một message được nhận trên `completedBatches` sau part thứ ba. Thử đổi `batchId` của part thứ ba: group đầu sẽ chỉ có hai messages và kết quả phải chưa được release.

Trong STEP 4, ví dụ chỉ được viết vào Markdown; chưa chạy Gradle hoặc QA học thuật. Khi đưa vào project, cần compilation test và integration test theo dependency thực tế.

## 11. Tách flow bằng channel boundary: nên chọn DirectChannel hay queue?

Hai flow stateless/stateful trong ví dụ được nối qua `DirectChannel`, nghĩa là thông điệp đi từ transformer tới aggregator trên **cùng call stack**. Trong demo điều này tiện để thấy hành vi và lỗi.

Khi triển khai, chọn boundary theo SLA:

| Boundary | Khi phù hợp | Rủi ro/chi phí |
| --- | --- | --- |
| `DirectChannel` | Cần xử lý sync, transaction có thể đi qua caller | Tải handler chậm làm producer chậm |
| `ExecutorChannel` | Muốn tách thread và tăng concurrency | Queue/task in-memory, transaction context tách |
| `QueueChannel` + poller | Muốn điều tiết bằng polling, giữ backlog | Delay, queue capacity, durability phụ thuộc store |
| Broker channel adapter | Tách service/process, at-least-once delivery | Ack/replay/schema, duplicate, network costs |
| Reactive channel | Nonblocking/demand-aware flow | Subscription/error/transaction semantics khác |

**Câu hỏi phân tách đúng:** nếu phần stateless khỏe nhưng stateful store bị chậm, có nên cho producer tiếp tục gửi? Chỉ khi có bounded/durable buffer phù hợp, chính sách backpressure và message retention rõ.

~~~mermaid
flowchart TD
    P["Stateless preprocess workers"] --> C{"Boundary?"}
    C -->|sync| D["DirectChannel\nproducer chịu backpressure của aggregator"]
    C -->|async in-memory| E["ExecutorChannel\nhợp cho non-durable tasks"]
    C -->|durable buffer| Q["Broker hoặc persistent queue"]
    D --> S["Stateful aggregator"]
    E --> S
    Q --> S
    S --> O["Downstream"]
~~~

Dùng executor để tăng throughput không giải quyết một correlation key đang bị khóa tuần tự, và có thể làm nhiều writers cùng tranh chấp stateful store.

## 12. State ownership và scale-out theo correlation key

Một stateless transformer thường có thể xử lý message ở instance bất kỳ. Nhưng một aggregator cần mọi parts cùng group có thể truy cập **cùng state**.

### Ba chiến lược thường gặp

**Chiến lược A — single owner theo partition key.**

Broker phân vùng theo `batchId`/`correlationId`; mọi parts cùng key được xử lý bởi cùng một consumer/partition owner tại một thời điểm theo contract. Điều này giảm tranh chấp nhưng vẫn phải xử lý rebalance, failover và state recovery.

**Chiến lược B — shared MessageGroupStore + distributed lock.**

Nhiều JVM cùng truy cập một shared durable store; khi mutate một message group cần phối hợp lock và transaction phù hợp. Spring Integration cung cấp các `LockRegistry` implementations (JDBC/Redis/Zookeeper tùy module); cấu hình đúng lock key, lease và failure handling.

**Chiến lược C — external workflow coordinator.**

Với saga dài và callbacks kéo dài nhiều ngày, lưu state trong business DB/workflow engine; Spring Integration chỉ vận chuyển events, transform, route và gọi coordinator. Phù hợp khi lifecycle phức tạp hơn một aggregator message group.

| Chiến lược | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Partition-key owner | Ít write contention | Hot key, rebalance, recovery khó |
| Shared store + lock | Failover linh hoạt, multi-node | Lock latency, contention, consistency |
| Durable coordinator | State business rõ, timeout/versioning | Phức tạp triển khai, chi phí vận hành |
| Local in-memory state | Đơn giản, nhanh | Restart mất group, scale-out sai nếu phân tán key |

**Một shared `MessageGroupStore` không tự chứng minh multi-node correctness.** Xem implementation, serialization, transaction isolation và lock registry của cùng ứng dụng. Nếu chỉ dùng `SimpleMessageStore`, nó không chia sẻ state giữa JVMs.

## 13. LockRegistry, transaction và critical section

Khi hai workers nhận parts của cùng `batchId`, chúng có thể cùng:

1. Đọc group size = 2;
2. Thêm part thứ ba hoặc trùng;
3. Quyết định release;
4. Phát output;
5. Mark group complete/remove.

Nếu không có đồng bộ, output có thể thiếu hoặc phát hai lần. Khóa và transaction cần bảo vệ **business invariant**, không chỉ một lệnh `addMessageToGroup()` riêng lẻ.

~~~mermaid
sequenceDiagram
    participant W1 as Worker A
    participant W2 as Worker B
    participant L as LockRegistry
    participant S as MessageGroupStore
    W1->>L: lock(batch-42)
    W2->>L: lock(batch-42) [wait]
    W1->>S: add part + check release
    W1->>S: mark group / cleanup
    W1->>L: unlock(batch-42)
    L-->>W2: acquired
    W2->>S: load current group state
    W2->>L: unlock(batch-42)
~~~

### Lock contention ảnh hưởng throughput

- Correlation key tập trung (hot group) khiến updates bị tuần tự.
- Lock lease/TTL quá ngắn có thể cho nhiều owners xử lý cùng key nếu task kéo dài.
- Lock TTL quá dài hoặc không release khi lỗi có thể làm group kẹt.
- Distributed lock phụ thuộc network/store, có thể tăng p95/p99 latency.
- Không mở concurrency vô hạn nếu chủ yếu tranh chấp cùng một critical section.

### Không nhầm transaction của sender với transaction của aggregator

`DirectChannel` đồng bộ có thể giữ một transaction trên call stack nếu được cấu hình đúng. `ExecutorChannel`/poller/broker tạo asynchronous boundary và có thể cần transaction riêng trên worker. Imperative Spring transaction thường gắn thread, không tự vượt async boundary.

Nếu muốn **atomic** giữa state store và business DB, phải xác định chúng có dùng chung transaction manager/resource hay không. Nếu không có distributed transaction, nên cân nhắc **outbox/inbox/idempotency** để giảm mất/trùng output khi crash giữa các bước.

## 14. Persistence: MessageStore bền vững chưa đủ nếu ack sai

Giả sử ứng dụng nhận part từ broker, lưu vào `JdbcMessageStore` rồi muốn ack source:

~~~text
broker receive(part)
    -> add part to group store
    -> broker ack
    -> later release full group -> downstream
~~~

Nếu app ack trước khi state store commit, crash có thể làm mất part. Nếu store commit rồi broker ack thất bại, source redeliver part, có thể tạo **duplicate group member**. Vì vậy cần:

- Định nghĩa transaction/ack boundary và thứ tự commit.
- Stable `eventId` hoặc `partId` cho từng logical part.
- Deduplication trước khi cộng phần vào group, không dùng raw group size như số phần duy nhất khi at-least-once.
- Durable group state và retention đủ dài cho retry/late parts.
- Xác nhận output được gửi sau release bằng outbox hoặc recoverable workflow.
- Khả năng replay khi state store hỏng hoặc schema version thay đổi.

`JdbcMessageStore` là một lựa chọn persistence, nhưng tính đúng đắn phụ thuộc schema, serializer, indexes, transaction manager và read/write semantics. Redis/Mongo/other stores cũng có những điểm khác nhau; không thay API/class mà giả định semantics giống nhau.

## 15. Group timeout, expiry và partial results

Một stateful flow không thể giữ group chưa hoàn thành mãi mãi. Giả sử batch cần ba line items nhưng một event bị mất; aggregator đã giữ hai parts, chờ vô hạn sẽ làm:

- Message group count tăng qua nhiều batch.
- Store phình to, retention không xác định.
- Lock registry/metadata giữ nhiều keys không còn cần.
- Người dùng không biết order đang pending hay thất bại.
- Alert “flow vẫn running” nhưng business SLA không được đáp ứng.

Spring Integration aggregator hỗ trợ các khái niệm **group timeout**, **expire groups**, **send partial result on expiry** và **discard/expiry handling** tùy API/config/version. Cần xác định rõ:

| Tình huống | Chính sách có thể chọn | Hệ quả |
| --- | --- | --- |
| Đủ ba parts hợp lệ | Release full group | Tạo output và mark completed |
| Chưa đủ sau 2 phút | Expire và gửi lỗi/timeout event | Cần lưu nguyên nhân và khả năng replay |
| Chưa đủ nhưng partial result hợp lệ | Send partial result on expiry | Chỉ dùng khi nghiệp vụ thực sự chấp nhận |
| Part tới sau expiry | Reject/quarantine/reopen theo policy | Không được làm trùng output im lặng |
| Duplicate sau completed | Dedupe/reply previous outcome | Đừng tạo batch mới ngoài ý muốn |
| State store tạm thời lỗi | Retry bounded, không ack vô điều kiện | Tránh mất message |

### Tại sao group timeout không phải request timeout?

Một HTTP gateway timeout có thể kết thúc yêu cầu caller, nhưng aggregator group vẫn lưu state và có thể release sau đó. Ngược lại, group có thể expire dù caller vẫn đang giữ connection. Đặt timeout ở **đúng scope**: gateway reply, aggregator lifetime, broker delivery attempt và business SLA là bốn thứ khác nhau.

### Không “send partial result” chỉ để giải phóng bộ nhớ

Nếu đơn hàng cần đủ ba line items để tính tổng, phát list hai items thành thành công là sai nghiệp vụ. Khi timeout, có thể tạo **failure/compensation event** chứa group key, expected/received part IDs và timestamp, rồi đưa vào durable recovery channel. Sau đó cleanup state theo runbook, không silently drop.

## 16. Late messages và tombstone/closed-group marker

Với at-least-once delivery, một part có thể đến **sau khi aggregator đã release**. Nếu bạn bật `expireGroupsUponCompletion(true)` và group bị remove, late part có thể mở lại group mới với cùng `batchId`.

Vì thế cần một chính sách **closed group** độc lập nếu business không cho phép re-open:

~~~text
batchId=batch-42
expectedPartIds={P1,P2,P3}
received: P1,P2,P3 -> release -> commit output
closedGroupStore[batch-42] = completed
late arrival P2 -> reject/dedupe; do not open new group
~~~

Một marker như vậy có thể nằm trong metadata store, inbox hoặc business DB có TTL/retention tối thiểu bằng khoảng redelivery tối đa. Nhưng `closedGroupStore.put` và `output commit` cần được **phối hợp**: nếu đánh dấu completed trước khi output thực sự commit rồi crash, lần retry có thể bị bỏ qua.

### Retention không được tính bằng cảm giác

Giả sử broker có thể replay trong 7 ngày, còn closed marker chỉ giữ 1 giờ. Sau 2 ngày, một duplicate có thể đi vào batch mới. Cần policy retention tương ứng với source và business semantics; với một số event quan trọng, trạng thái complete ở business DB tồn tại lâu dài.

## 17. Idempotent receiver: stateless handler cần state để chống duplicate

Giả sử một service activator chỉ làm:

~~~java
void chargeCard(Payment payment) {
    paymentGateway.charge(payment);
}
~~~

Bean không có mutable field, nhưng nếu broker redeliver cùng `eventId` thì charge có thể xảy ra **hai lần**. Vì vậy **business statelessness không thay thế idempotency**.

Spring Integration có **Idempotent Receiver** pattern và `IdempotentReceiverInterceptor`, có thể dựa trên metadata store và key selector. Một chính sách cơ bản là lưu marker theo stable event ID.

Ví dụ minh họa logic CAS trên `ConcurrentMetadataStore`:

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;

final class DedupGate {

    private final ConcurrentMetadataStore metadataStore;

    DedupGate(ConcurrentMetadataStore metadataStore) {
        this.metadataStore = metadataStore;
    }

    boolean firstSeen(String eventId) {
        return metadataStore.putIfAbsent(
                "event:" + eventId, "claimed") == null;
    }
}
~~~

Đoạn trên chứng minh **atomic claim per key của store hỗ trợ contract**, chưa phải một xử lý đúng toàn bộ khi crash. Nếu claim thành công rồi handler lỗi trước DB commit, mọi retry sau bị từ chối dù side effect chưa thực hiện. Để đúng nghiệp vụ cần:

1. Transactional inbox hoặc state machine `NEW/PROCESSING/COMPLETED/FAILED`.
2. Atomicity giữa claim và effect nếu cùng resource/transaction.
3. Retry/lease/reconciliation cho `PROCESSING` lâu.
4. Retention, cleanup và unique key ổn định.
5. Một reply hợp lệ khi nhận duplicate đã completed.

### Dedup trước aggregator

Với batch `P1,P2,P3`, nếu `P2` redeliver:

~~~text
P1 -> group size 1
P2 -> group size 2
P2 duplicate -> group size 3 (sai!)
P3 -> tới muộn, group đã release
~~~

Đặt dedupe theo **part ID** trước khi group addition hoặc dùng release strategy kiểm tra distinct members thay vì `group.size()` thô. Đừng dùng `MessageHeaders.ID` nếu adapter tạo ID mới khi redelivery; chọn logical part/event ID từ source.

## 18. Resequencer: giữ state để phục hồi thứ tự

Một handler stateless có thể xử lý các messages độc lập và không quan tâm arrival order. Nhưng một **resequencer** phải giữ message đi trước để chờ message có sequence nhỏ hơn:

~~~text
Arrival:   seq=3, seq=1, seq=2
Expected:  seq=1, seq=2, seq=3
~~~

Để reorder, resequencer cần state theo correlation group:

- Group ID;
- Những sequence numbers đã nhận;
- Expected size hoặc điều kiện flush;
- Store/lock;
- Timeout khi thiếu sequence;
- Dedupe và gap policy.

Bảng khác biệt:

| Bài toán | Aggregator | Resequencer |
| --- | --- | --- |
| Nhiều messages thành một result | **Có** | Thường không |
| Giữ một group pending | Có | Có |
| Cần correlation/sequence | Có thể | Thường có |
| Cần release strategy | Có | Có |
| Output | Một aggregated message hoặc kết quả | Nhiều messages theo thứ tự |
| Late/duplicate gap | Phải xử lý | Phải xử lý |

**Đừng giải bài toán out-of-order chỉ bằng cách tăng executor threads.** Việc tăng concurrency có thể khiến thứ tự đến còn khó dự đoán hơn. Nếu ordering là business invariant, partition theo key, stateful resequencing và bounded gap policy phải được thiết kế rõ.

## 19. Delayer, scheduler và deferred work cũng là stateful

`Delayer` giữ message tới thời điểm release. Stateful ở đây không nhất thiết là `List` trong một handler — nó có thể là scheduler task, message group/store và deadline.

Một restart process có thể làm mất delayed tasks nếu chúng chỉ nằm trong memory. Nếu nghiệp vụ cần gửi notification sau 24 giờ, cần persisted schedule/workflow/outbox. Trong ứng dụng production:

- Xác định deadline theo **business timestamp**, không chỉ `Thread.sleep`.
- Persist pending message và trạng thái deadline.
- Có cancellation/update deadline contract.
- Có executor/scheduler capacity và timeouts.
- Có idempotency khi task đã chạy nhưng ack bị mất.
- Có expiry/cleanup và replay khi application restart.

Một cron/poller chưa tự đủ để triển khai saga/long-running workflow có độ bền cao. Đừng cố “giữ state” bằng singleton map khi yêu cầu vượt process lifetime.

## 20. Statefulness ẩn trong filter, router, cache và adapter

Không chỉ aggregator mới có state. Một số component có thể trông stateless nhưng chứa state ẩn:

| Thành phần | Khi nào stateless? | Khi nào trở thành stateful? |
| --- | --- | --- |
| Filter | Predicate `amount > 0` | Filter giữ “seen IDs”, rate limit counters |
| Router | `payload.type` chọn channel | Router dùng sticky assignment, mutable rule table |
| Transformer | Map fields thuần | Transformer cache mutable hoặc tăng sequence |
| Enricher | Lookup không side effect | Cache với refresh/expiry, network state |
| File inbound adapter | Chỉ đọc nguồn mới theo source contract | Accept-once filter lưu file names/metadata |
| HTTP outbound | Không giữ progress nghiệp vụ | Connection pool vẫn có connection state |
| TCP client-mode | Handler có thể không giữ workflow state | Connection factory/adapter giữ socket/session |
| Retrying advice | Invocation có thể retry độc lập | Retry context/attempt state, stateful retry |
| Claim-check | Payload thay bằng claim token | Claim-check message store giữ payload |

**Phân biệt connection state với workflow state:** có một TCP socket hoặc connection pool **không khiến mọi handler phía sau phải chạy trên một stateful node**. Tuy nhiên adapter phải quản lý reconnect, pending replies và failure semantics ở đúng layer.

## 21. Quản lý state bằng cấu trúc “stateless → durable queue → stateful”

Một thiết kế tham khảo cho nghiệp vụ batch:

~~~mermaid
flowchart LR
    IN["Kafka/JMS inbound"] --> S1["Stateless validate + normalize"]
    S1 -->|Invalid| ERR["Quarantine/DLQ"]
    S1 -->|Valid| Q[("Durable staging queue")]
    Q --> D["Part dedupe by eventId"]
    D --> A["Stateful aggregator by batchId"]
    A <--> MS[("Durable MessageGroupStore")]
    A -.-> LR["LockRegistry"]
    A --> OUT[("Outbox / committed result")]
    OUT --> S2["Stateless format + send"]
    S2 --> REM["Remote API / broker"]
    S2 --> REC["Retry / recovery path"]
~~~

### Vì sao đặt durable queue ở giữa?

Nó tạo một boundary để tách sức tải:

- Stateless preprocess có thể scale độc lập và nhanh.
- Khi aggregator/store chậm, queue giữ pending messages theo retention.
- Downstream stateful workers có thể tăng/giảm theo concurrency contract.
- Khi restart stateful workers, pending messages còn trong broker/store **nếu ack/transaction đúng**.
- Có thể đo queue dwell, queue age và backlog.

**Nhưng** queue bền vững không biến toàn flow thành exactly-once. Một producer có thể publish vào queue rồi crash trước khi ack source; message có thể xuất hiện lần nữa. Một consumer có thể commit state rồi crash trước khi ack queue. Dedup và outbox vẫn cần.

### Khi nào không nên chèn queue?

- Latency yêu cầu rất thấp, một synchronous transaction scope đủ và được kiểm chứng.
- Workload nhỏ, stateless và không cần durability qua restart.
- Bổ sung queue làm phức tạp ordering/error/reply semantics mà không mang lợi ích rõ.
- Không có một owner của retry/ack sau queue.

Đặt channel dựa vào **SLO và failure boundary**, không phải nguyên tắc “mỗi bước cần một queue”.

## 22. Transaction và retry: scope sai gây mất hoặc nhân đôi state

Những trường hợp khác nhau:

| Case | Chuyện xảy ra | Rủi ro |
| --- | --- | --- |
| Stateless validate throw trước enqueue | Message chưa vào stateful store | Có thể retry từng message |
| Aggregator store add rồi source ack mất | Part được lưu, source redeliver | Duplicate member |
| Aggregator release rồi output send fail | Group có thể đã complete | Output mất nếu không có outbox/retry |
| Handler ghi DB rồi throw trước broker ack | Business commit đã xảy ra | Duplicate side effect khi redelivery |
| Error được `onErrorResume` nuốt ở reactive chain | Publisher complete bình thường | Adapter có thể ack dù chưa persist recovery |
| Poller stop trong transaction | In-flight có thể tiếp tục hoặc rollback | Không suy stop == rollback |

### Vị trí retry phải khớp đơn vị công việc

- Retry một **stateless transform** thường không cần giữ workflow progress; nếu transient dependency lỗi thì retry bounded hợp lý.
- Retry một **stateful group mutation** phải bảo vệ idempotency của part và transaction; không nên add cùng part nhiều lần.
- Retry **outbound side effect** phải giữ business key để receiver dedupe.
- Retry toàn **outer Flux** có thể resubscribe source và replay những messages đã hoàn tất; muốn theo event thì đặt retry trong inner publisher.

Với `RequestHandlerRetryAdvice`, cần xác định advice bọc handler nào; nếu toàn bộ group release/side effect nằm cùng advice, nhiều attempts có thể tạo duplicate output. Không tính số lần advice retry bằng số messages duy nhất.

### `ErrorMessage` không phải compensation

Khi stateful aggregator lỗi, error handler có thể tạo `ErrorMessage` với `MessagingException.failedMessage`/original message. Điều đó giúp chẩn đoán, nhưng **không tự rollback state store** hoặc dọn incomplete group. Cần policy cụ thể: retry add, expire group, quarantine part, replay, hoặc compensation transaction.

## 23. Message headers và correlation phải sống qua boundary

Khi chuyển từ stateless flow sang stateful flow, hãy giữ đủ metadata:

| Header/field | Mục đích | Rủi ro nếu mất |
| --- | --- | --- |
| `eventId` / `partId` | Dedupe logical part | Duplicate không nhận ra |
| `batchId` / `correlationId` | Chọn message group | Parts vào group khác hoặc không có group |
| `sequenceNumber` | Xác định thứ tự/position | Resequencer/release không đúng |
| `sequenceSize` | Số phần dự kiến | Group không release hoặc release sớm |
| `traceId` | Quan sát xuyên thread/process | Không nối được logs |
| `schemaVersion` | Decode/migrate persisted messages | Store không đọc được sau deploy |
| `replyChannel`/`errorChannel` | Điều phối reply và lỗi | Mất reply hoặc không route lỗi như ý |
| `tenantId`/namespace | Phân biệt khóa giữa tenant | Correlation collision |

Các headers như `replyChannel` có thể chứa reference đến bean/channel object, không phải lúc nào serializer của broker cũng hỗ trợ. **Không truyền nguyên mọi internal header qua network**; mapping theo contract, dùng durable reply address/correlation key phù hợp.

Nếu dùng `MessageBuilder.fromMessage(...)`, hãy xác minh việc giữ các headers quan trọng qua transformer, split/aggregate và broker adapter. Không gửi raw `MessageHeaders.ID` làm idempotency key giữa retries vì mỗi lần rebuild message có thể sinh UUID mới.

## 24. Quan sát stateful island bằng metrics và traces

Một application có thể chạy 100% endpoint ở trạng thái `isRunning()==true` trong khi 80% groups đang chờ phần cuối và queue backlog tăng. Cần quan sát **progress**, không chỉ lifecycle.

| Metric (gợi ý, không mặc định) | Vì sao quan trọng |
| --- | --- |
| `flow.stateless.received.total` | Tổng messages đã vào preprocess |
| `flow.stateless.invalid.total` | Số messages bị reject/quarantine |
| `flow.stateful.part.accepted.total` | Số parts được nhận vào group |
| `flow.stateful.part.duplicate.total` | Phát hiện duplicate/replay |
| `flow.stateful.group.pending` | Số groups chưa hoàn thành |
| `flow.stateful.group.oldest.age` | Group bị treo lâu nhất |
| `flow.stateful.group.completed.total` | Throughput theo logical group |
| `flow.stateful.group.expired.total` | Timeout/partial/missing parts |
| `flow.stateful.lock.wait` | Lock contention theo key |
| `flow.stateful.store.read/write.duration` | Storage bottleneck |
| `flow.queue.depth/oldest.age` | Producer vượt consumer capacity |
| `flow.output.confirmed.total` | Kết quả đã có ack/commit |
| `flow.output.unknown.total` | Outcome không xác định |
| `flow.retry.attempts` | Retry pressure |
| `flow.error.recovered.total` | Recovery đã persist thành công |

Không dùng raw `eventId`, `batchId`, customer ID hoặc full payload làm **metric tags** vì cardinality vô hạn. Dùng endpoint name, event type, outcome, exception class; logical IDs xuất hiện trong trace/log có retention và privacy policy.

### Message History khác group state

`MessageHistory` header cho biết message đã qua các tracked components. Nó không lưu toàn bộ members của aggregator group và không chứng minh output đã commit. Muốn debug batch treo, xem cả:

1. `correlationId` và sequence metadata;
2. `MessageGroupStore` group size/age;
3. LockRegistry/DB lock wait;
4. Poller/executor active và queue age;
5. Error/retry/dlq records;
6. Trace spans và business completion state.

## 25. Tối ưu throughput: scale stateless khác scale stateful

### Stateless throughput

Với một transformer CPU-bound độc lập, throughput gần như có thể tăng theo số workers đến khi gặp CPU, scheduler hoặc downstream bottleneck. Nếu handler có I/O blocking, concurrency còn bị giới hạn bởi connection pool và timeout.

### Stateful throughput

Nếu tất cả messages cùng `batchId`, một critical section bảo vệ group có thể phải tuần tự. Tăng worker từ 4 lên 40 đôi khi **chỉ tăng lock wait**.

Một mô hình đơn giản:

\[
L = \lambda W
\]

Little’s Law trong steady state, với `L` là số items trung bình trong phạm vi quan sát, `λ` là throughput trung bình, `W` là thời gian lưu trú trung bình. Nếu stateful stage xử lý 50 parts/s và thời gian chờ trung bình 2 s thì trung bình khoảng 100 parts in-flight/queued trong phạm vi đó, **với điều kiện hệ thống ổn định**.

Khi input 100 parts/s nhưng stateful store chỉ hoàn tất 50/s, backlog tăng xấp xỉ 50 parts/s, không thể lấy công thức steady-state một cách máy móc để dự đoán time-to-drain.

### Đo đúng bottleneck

| Hiện tượng | Khả năng nguyên nhân | Can thiệp |
| --- | --- | --- |
| Stateless CPU 100%, stateful store nhẹ | Normalize/validation CPU-bound | Scale workers, tối ưu CPU |
| Stateless idle, stateful lock wait cao | Hot correlation key | Partition, giảm contention, thiết kế key |
| State group age cao, queue depth thấp | Thiếu parts/timeout policy | Expiry, source validation, fault recovery |
| Queue depth tăng, store write chậm | Backend storage/serializer/transaction | Index, batch, tune DB |
| Retry tăng khi output API 503 | Downstream outage | Backoff, circuit breaker, durable outbox |
| Completion count thấp dù group release nhiều | Output commit/ack lỗi | Outbox, reconciliation |
| OOM do group chưa expire | Unbounded state retention | Timeout, cleanup, capacity alert |

**Không coi mọi bài toán stateful đều giải được bằng nhiều threads.** Phải biết key distribution, lock contention, store throughput, release condition và downstream completion.

## 26. Kiểm thử: ba cấp độ bắt buộc

### 26.1. Unit test phần stateless

Với hàm thuần, test dễ dàng và không cần Spring context:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;

import org.junit.jupiter.api.Test;

class NormalizeLineTest {

    @Test
    void trimsAndUppercasesInput() {
        String result = " green "
                .trim()
                .toUpperCase(Locale.ROOT);

        assertEquals("GREEN", result);
    }
}
~~~

Thực tế nên gọi đúng method/bean transformer thay vì viết lại logic trong test; đoạn trên chỉ minh họa tính deterministic.

### 26.2. Spring Integration context test phần stateful

Dùng chính flow ở mục 9 trong một test context **không chạy ApplicationRunner demo** để không có state/samples từ lần chạy khác:

~~~java
@Test
void releasesOnlyAfterThreeParts() {
    for (int i = 1; i <= 2; i++) {
        assertTrue(input.send(
                MessageBuilder.withPayload("p" + i)
                        .setHeader("batchId", "batch-test")
                        .setHeader("eventId", "evt-" + i)
                        .build()));
    }

    assertNull(completed.receive(100));

    assertTrue(input.send(
            MessageBuilder.withPayload("p3")
                    .setHeader("batchId", "batch-test")
                    .setHeader("eventId", "evt-3")
                    .build()));

    Message<?> result = completed.receive(2_000);
    assertNotNull(result);
}
~~~

Đây là **JUnit fragment**, cần inject `MessageChannel input`, `PollableChannel completed`, test context riêng và imports. Không assert exact string of aggregated payload trước khi xác định output processor và order policy.

Cần thêm negative tests:

- Header `batchId` bị thiếu;
- Duplicate `eventId` trước phần thứ ba;
- Parts đến ngoài thứ tự;
- Hai batch keys xen kẽ;
- Group timeout và late arrival;
- Handler/output ném exception sau release.

### 26.3. Fault integration test với persistent store/broker

Nếu yêu cầu hoạt động đúng qua restart/multi-node, phải có test dùng storage/broker thật hoặc Testcontainers:

1. Gửi 2/3 parts và xác nhận group được persist;
2. Stop/kill ứng dụng tại thời điểm kiểm soát;
3. Start instance khác với cùng store/schema;
4. Gửi part cuối, xác nhận batch release **đúng một logical result**;
5. Redeliver một part cũ, xác nhận idempotency;
6. Mô phỏng output commit rồi ack thất bại; kiểm tra replay/dedupe;
7. Mô phỏng group timeout và expiry;
8. Quan sát lock lease, deadlock hoặc multi-node conflict;
9. Đảm bảo không có ghost/incomplete group mãi không dọn.

**Không kết luận durable từ test `SimpleMessageStore` in-memory.** Test unit thành công chỉ chứng minh behavior trong context hiện tại.

## 27. Ma trận fault injection và trạng thái kỳ vọng

| Thời điểm lỗi | State đã có? | Điều phải kiểm chứng |
| --- | --- | --- |
| Trước stateless transform | Chưa có group part | Source redelivery/retry nếu cần |
| Sau normalize nhưng trước durable queue ack | Part có thể bị publish trùng | Stable partId, broker dedupe |
| Khi group mới nhận 1/3 | One pending member | Recovery khi restart |
| Khi group đã có 2/3 | Pending group | Resume với part thứ ba |
| Hai consumers add cùng key | Lock contention | Không mất member hoặc release trùng |
| Khi vừa đủ parts nhưng trước output commit | Group có thể completed | Outbox/release retry |
| Sau DB commit nhưng trước source ack | Business result có rồi | Duplicate không tạo side effect lần hai |
| Part đến sau group expiry | Group đã expired | Late event/quarantine policy |
| Store schema nâng cấp giữa hai phần | Old serialized messages tồn tại | Deserialization/version migration |
| Error flow bị down | Recovery không persist được | Propagate failure, không ack im lặng |
| Redis/JDBC lock bị mất lease | Shared state có hai owners | Business invariant/reconciliation |
| Cluster rebalance giữa batch | Owner của key đổi | Shared/durable state/replay |

### Cách đọc kết quả

Không chỉ assert `send()` trả true; với `ExecutorChannel` nó có thể là task handoff, với `QueueChannel` có thể là enqueue. Cần kiểm tra:

- Final business output;
- Group store state;
- Source ack/offset;
- Idempotency outcome;
- Retry/expired/recovered counts;
- Duplicate side effects ở remote system.

## 28. Runbook vận hành stateful stage

### Khi stateless stage khỏe nhưng stateful stage nghẽn

1. Xác định input rate và output completion rate theo cùng time window.
2. Kiểm tra queue depth, oldest message age, pending message groups và oldest group age.
3. Đo lock wait/hold time theo endpoint, không tag theo raw correlation key.
4. Kiểm tra DB/Redis availability, transaction retry và serializer errors.
5. Phân biệt nhóm thiếu parts với nhóm bị deadlock/lock contention.
6. Nếu cần giảm tải, pause ingress hoặc đặt bounded rate limit; **không xóa queue/group tùy tiện**.
7. Xác định safe group expiration/replay policy theo business invariant.
8. Khi phục hồi, tăng consumer throughput từ từ; theo dõi duplicate và tail latency.

### Khi cần rolling restart

~~~mermaid
flowchart TD
    A["Plan restart"] --> B["Pause ingress hoặc giảm tải"]
    B --> C["Drain current transactions / tasks"]
    C --> D["Verify group store durability"]
    D --> E["Restart một instance"]
    E --> F["Recover group state, locks, subscriptions"]
    F --> G["Send synthetic parts / check output"]
    G --> H{"No duplicates/missing?"}
    H -->|Có| I["Resume gradually"]
    H -->|Không| J["Escalate + quarantine / reconcile"]
~~~

Không chuyển đổi một `SimpleMessageStore` in-memory sang một shared JDBC store bằng cách “đổi bean tại runtime” mà bỏ qua migration của in-flight groups. Cần một migration plan và tương thích serializer/schema.

## 29. Các anti-pattern phổ biến

| Anti-pattern | Sai ở đâu? | Phương án phù hợp |
| --- | --- | --- |
| Singleton `HashMap` giữ batch state | Không bền, không multi-node safe | `MessageGroupStore` + lock + timeout |
| `synchronized` trên một instance rồi scale nhiều pods | Lock chỉ ở JVM đó | Partition ownership hoặc distributed lock |
| `group.size()==N` trong hệ thống có redelivery | Duplicate có thể làm đủ giả | Dedup theo unique part IDs |
| `expireGroupsUponCompletion` rồi tưởng không còn late duplicates | Closed marker có thể bị xóa | Durable completed group/idempotency marker |
| Không có group timeout | Leaked pending state | Expiry/quarantine/partial policy |
| Dùng `QueueChannel` in-memory như durable store | Restart mất backlog | Persistent store/broker |
| Dùng `MessageStore` như database nghiệp vụ | Không biểu diễn domain invariant | Business DB/outbox |
| Retry whole stream vô hạn | Replay mọi side effects | Bounded retry per-event/group |
| Tăng executor threads để sửa lock contention | Key vẫn tuần tự | Key distribution và critical section |
| Dùng raw `MessageHeaders.ID` làm idempotency key | ID đổi khi message rebuilt | Stable business eventId |
| Ack trước khi store commit | Crash làm mất part | Đúng transactional boundary |
| Đánh dấu dedupe trước khi commit rồi crash | Retry bị bỏ dù effect chưa có | Inbox state machine/atomic claim |
| Xóa incomplete group khi còn late messages | Mất khả năng phục hồi | Explicit timeout/retention |
| Không đo stateful metrics | Endpoint running nhưng business không tiến | Pending/oldest group, lock wait, completion |
| Coi durable store là exactly-once | Side effects ngoài store có thể trùng | Idempotency/outbox/reconciliation |

## 30. Bài thực hành

1. **State classification:** với mười endpoint trong dự án, xác định stateless invocation, stateful infrastructure và stateful business owner.
2. **Tách flow:** viết hai `IntegrationFlow` nối qua channel như ví dụ mục 9; đặt tên endpoint/channel rõ.
3. **Two batches:** gửi parts xen kẽ cho `batch-A` và `batch-B`; xác nhận không gộp nhầm.
4. **Missing part:** gửi 2/3 parts rồi dừng; kiểm tra group pending và thiết kế timeout.
5. **Duplicate:** gửi `P1,P2,P2`, chứng minh release theo size có thể sai; thêm dedupe.
6. **Out of order:** gửi `P3,P1,P2`; chọn aggregator hoặc resequencer tùy output contract.
7. **Concurrency:** dùng `ExecutorChannel` với concurrency 8; gửi parts cùng key đồng thời, đo lock wait và output count.
8. **Persistent store:** thay `SimpleMessageStore` bằng store bền vững trong integration test; restart sau 2/3.
9. **Cluster:** dùng 2 nodes truy cập shared store có locking; kiểm tra một batch release một lần theo business ID.
10. **Expiry:** cho group thiếu part quá timeout, ghi failure event và kiểm tra cleanup.
11. **Late event:** gửi part sau complete/expiry, xác định nó được drop/quarantine/reopen có kiểm soát.
12. **DB transaction:** làm output handler throw sau khi ghi DB, xác minh rollback/retry và kết quả outbox.
13. **Outbox:** simulate crash sau group release trước network send; dùng outbox để không mất output.
14. **Inbox:** simulate duplicate redelivery sau commit; xác minh receiver không tạo side effect hai lần.
15. **Schema migration:** persist message với version cũ, khởi động code version mới và thử decode.
16. **Observability:** đo pending group count, oldest age, completion rate, lock wait p95.
17. **Scaling:** so sánh throughput khi tăng stateless workers và khi tăng stateful consumers với một hot key.
18. **Runbook:** viết kế hoạch pause-drain-resume cho stateful stage có 100 pending groups.
19. **Control Bus:** stop/start endpoint đúng ID và kiểm tra group store vẫn bền vững, không dùng lifecycle state thay durable outcome.
20. **Design review:** giải thích vì sao message history, errorChannel và retry advice không thay thế workflow state store.

### Câu hỏi tự kiểm tra

- Một handler không có mutable field có luôn là thuần/stateless theo nghiệp vụ không?
- Vì sao `QueueChannel` làm toàn pipeline có state dù transformer không giữ state?
- Aggregator cần correlation, release, expiry và message store để làm gì?
- Tại sao `MessageGroupStore` khác `MetadataStore`?
- Vì sao `group.size()==3` không đúng khi có duplicate redelivery?
- `expireGroupsUponCompletion(true)` có tự chặn mọi late events không?
- Multi-node shared store có cần distributed locking không?
- Tại sao tăng threads không giải quyết một hot correlation key?
- Retry sau DB commit nhưng trước broker ack có thể gây duplicate như thế nào?
- Vì sao readback qua restart là bắt buộc trước khi gọi flow durable?
- Thế nào là stateless island và stateful island, và boundary tốt phụ thuộc vào yếu tố nào?

## 31. Checklist trước production

- Đã định nghĩa rõ state ownership và logical correlation key cho mỗi workflow.
- Stateless handlers không giữ mutable per-workflow data giữa invocations nếu không có contract.
- Stateful components có store, lock, transaction, timeout và release strategy rõ ràng.
- Có late/duplicate policy và idempotency key ổn định qua retries/replay.
- Store durability/serializer/version migration được kiểm thử qua restart.
- Mọi async channel/broker boundary đều có ack/retry/error contract.
- Không dùng in-memory queue/group cho dữ liệu cần sống qua process restart.
- Có bounded capacity cho queue, state groups, executors và error flow.
- Group release và output side effect có recovery/outbox hoặc equivalent guarantee.
- Multi-node locking/key partitioning được kiểm chứng với fault injection.
- Correlation, sequence, event ID, trace ID đi qua boundary đúng header mapping.
- Observability thể hiện group count, age, expired/duplicate và completion rate.
- Scale stateless và stateful dựa trên điểm nghẽn thật, không chỉ số worker.
- Có runbook pause/drain/restart/replay, retention và incident response.
- Test unit, integration, multi-node/crash recovery phân biệt rõ.
- STEP 4 chỉ author nội dung; chưa chạy build/QA học thuật STEP 6.

## 32. Tài liệu tham khảo chính thức

- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): lưu messages, message groups và persistence.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release, group timeout và expiry.
- [Spring Integration — Resequencer](https://docs.spring.io/spring-integration/reference/resequencer.html): ordering và resequencing state.
- [Spring Integration — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): idempotency interceptor và metadata.
- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): metadata persistence.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): DirectChannel, ExecutorChannel, QueueChannel.
- [Spring Integration — Polling Consumer](https://docs.spring.io/spring-integration/reference/polling-consumer.html): poller và transaction boundary.
- [Spring Integration — Lock Registry](https://docs.spring.io/spring-integration/reference/distributed-locks.html): concurrency và distributed lock.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): xây IntegrationFlow theo Java DSL.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel, recovery.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): tracked hops và correlation support.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): Micrometer Observation và integration management.
- [Spring Integration — Dynamic Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): registration/lifecycle.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transactions và rollback.
