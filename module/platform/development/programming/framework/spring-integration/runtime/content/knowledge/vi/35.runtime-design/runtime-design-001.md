# Đặt thread boundary có chủ đích trong Spring Integration Runtime

## Mục tiêu bài học

Trong module **SPRING_INTEGRATION_RUNTIME**, message được nhận từ inbound adapter, đi qua **channel, endpoint, consumer, poller và executor**, rồi có thể được ghi vào DB, MessageStore, broker hoặc gửi tới external API. Một quyết định tưởng đơn giản như đổi **DirectChannel** thành **ExecutorChannel** có thể làm thay đổi hoàn toàn **thread chạy handler, phạm vi transaction, đường truyền exception, thứ tự xử lý và thời điểm nguồn xác nhận message**.

**Thread boundary** là ranh giới nơi công việc **không còn tiếp tục trong cùng thread/call stack của phía gửi** mà được giao cho một thread hoặc cơ chế thực thi khác. Trong Spring Integration, ranh giới này thường được tạo bởi **ExecutorChannel, QueueChannel với polling consumer, PublishSubscribeChannel có executor**, hoặc các adapter/gateway có hành vi bất đồng bộ.

Mục tiêu của bài là học cách **đặt thread boundary có chủ đích**, thay vì thêm executor chỉ với kỳ vọng “flow sẽ nhanh hơn”.

Sau bài học, bạn có thể:

1. Giải thích **thread boundary**, **transaction boundary** và **durability/ack boundary** là ba khái niệm có liên hệ nhưng không đồng nhất.
2. So sánh **DirectChannel, ExecutorChannel, QueueChannel, PublishSubscribeChannel** theo thread, blocking, backpressure, ordering và error handling.
3. Chọn **vị trí handoff** phù hợp với SLA và yêu cầu không mất message.
4. Hiểu vì sao Spring transaction và nhiều **ThreadLocal** không tự chuyển từ sender sang worker thread.
5. Thiết kế **executor pool, bounded queue, rejection policy, retry và timeout** không tạo overload hoặc mất việc âm thầm.
6. Giữ **correlationId, eventId, tracing context** và kiểm thử ordering/idempotency khi xử lý song song.
7. Thực hành Java DSL với ranh giới đồng bộ–bất đồng bộ có ID tường minh, quan sát và test được.
8. Chẩn đoán các sự cố runtime: **send() trả true nhưng handler chưa chạy, mất exception, transaction không rollback, duplicate sau restart, pool đầy và message mất sau shutdown**.

> **Nguyên tắc thiết kế:** Chỉ tạo thread boundary khi bạn trả lời được: **ai sở hữu message sau handoff, nó được lưu ở đâu, ai ack nguồn, lỗi đến đâu, khi quá tải thì làm gì và restart có phục hồi được không?**

## 1. Thread boundary thực chất là gì?

Một flow đồng bộ:

~~~mermaid
sequenceDiagram
    participant S as Sender thread
    participant C as DirectChannel
    participant H as Handler
    participant D as Database
    S->>C: send(M)
    C->>H: handle(M) cùng thread
    H->>D: update/commit theo transaction
    D-->>H: Result
    H-->>C: return
    C-->>S: send returns
~~~

Một flow chuyển sang executor:

~~~mermaid
sequenceDiagram
    participant S as Sender thread
    participant C as ExecutorChannel
    participant Q as Executor work queue
    participant W as Worker thread
    participant D as Database
    S->>C: send(M)
    C->>Q: submit handler task
    C-->>S: send may return
    Note over S,W: Sender có thể kết thúc trước business effect
    Q->>W: execute task
    W->>D: update/commit trong worker context
    D-->>W: Result
~~~

Với **DirectChannel**, handler được gọi đồng bộ trên thread gửi. Với **ExecutorChannel**, việc dispatch được giao cho **TaskExecutor**, nên handler **có thể** chạy sau đó trong worker thread; sender thường quay về sớm hơn.

Từ đây nảy sinh ba loại ranh giới:

| Ranh giới | Câu hỏi cốt lõi | Ví dụ |
| --- | --- | --- |
| **Thread boundary** | Handler có còn ở cùng thread với sender? | ExecutorChannel dispatch sang worker |
| **Transaction boundary** | Một transaction có bao trùm cả producer và consumer không? | Transaction tại inbound poller không tự đi qua executor |
| **Durability / ack boundary** | Message đã được lưu/ack bền vững trước khi sender trả về chưa? | Enqueue vào executor RAM khác với commit vào JDBC message store |

**Một thread boundary không tự tạo một durable queue.** Ngược lại, một persistent QueueChannel có thể tạo durable handoff nhưng vẫn cần transaction đúng cách để tránh mất message khi đã dequeue.

### Cần phân biệt concurrency với asynchronous handoff

Một flow có thể có nhiều **concurrent sender threads** nhưng mỗi sender vẫn dùng DirectChannel và gọi handler đồng bộ trong thread của chính nó. Vì thế:

~~~text
Thread kafka-consumer-1 → DirectChannel → Handler A
Thread kafka-consumer-2 → DirectChannel → Handler A
~~~

**DirectChannel không có nghĩa chỉ có một thread trên toàn ứng dụng.** Nó chỉ không tự tạo ranh giới thread mới giữa send và handler. Shared state của handler **vẫn phải thread-safe** nếu nhiều adapter/producer cùng gọi.

Ngược lại, một ExecutorChannel dùng executor một worker có thể tạo **asynchronous handoff** mà không đạt parallelism lớn; thông lượng vẫn bị giới hạn bởi worker duy nhất.

## 2. So sánh các channel theo hợp đồng runtime

| Channel/cách dispatch | Handler chạy ở đâu? | send() có đợi handler? | Transaction sender có tự bao trùm handler? | Message chờ được lưu ở đâu? |
| --- | --- | --- | --- | --- |
| **DirectChannel** | Thường cùng sender thread | **Có**, khi handler đồng bộ | Có thể cùng transaction đang active trên thread | Không tạo queue riêng |
| **ExecutorChannel** | TaskExecutor, thường worker thread | **Thường không**; có ngoại lệ rejection policy | **Không bảo đảm**, thường không | Executor queue/task memory theo implementation |
| **QueueChannel + polling consumer** | Thread thực hiện poll/handler | **Không**; sender chỉ enqueue | Transaction sender không tự tiếp nối | Queue in-memory hoặc ChannelMessageStore persistent |
| **PublishSubscribeChannel không executor** | Các subscriber chạy theo sender thread, theo dispatcher | Thường có | Có thể cùng thread, tùy handler | Không tạo queue task riêng |
| **PublishSubscribeChannel có executor** | Có thể nhiều worker threads | Thường không đợi mọi subscriber | Không tự bao trùm các nhánh async | Executor/task queues |
| **Adapter tự chạy async / reactive boundary** | Theo adapter/scheduler/reactive execution | Tùy API/flow | Không mặc định | Tùy transport/buffer/subscription |

**Không suy luận từ tên method hay tên channel.** Ví dụ **PublishSubscribeChannel** mặc định phát cho subscriber trong **sender thread** khi không có executor. Ngược lại, một **DirectChannel có nhiều producer threads** vẫn xử lý đồng thời.

**ExecutorChannel có ngoại lệ quan trọng:** Một TaskExecutor dùng **CallerRunsPolicy** có thể thực thi task **ngay trên sender thread khi pool/queue đầy**. Vì việc đó chỉ xảy ra theo tình trạng tải, **không bao giờ dựa vào CallerRunsPolicy để giả định có chung transaction giữa sender và handler**.

### Thread boundary không đồng nghĩa fan-out

- **DirectChannel** và **ExecutorChannel** là point-to-point dispatch: khi nhiều subscriber, dispatcher có thể chọn một handler theo load balancing/failover.
- **PublishSubscribeChannel** dùng cho fan-out đến nhiều subscriber. Khi có executor, nhánh subscriber có thể chạy song song và lỗi của một nhánh phải được xử lý theo hợp đồng async.
- **QueueChannel** là hàng đợi để polling consumer lấy message, không tự động broadcast tới mọi consumer.

Đừng thêm một subscriber debug vào DirectChannel và nghĩ mọi message sẽ tới cả business handler và debug handler. Khi cần quan sát, dùng **WireTap** hoặc một cấu trúc được thiết kế rõ.

## 3. Khi nào nên tạo ranh giới thread?

Thread boundary có ích khi **chi phí và thời điểm xử lý downstream khác biệt đáng kể với công việc trước boundary**.

**Ví dụ phù hợp:**

- Giữ listener nhận message khỏi phải chờ một tác vụ CPU/HTTP/DB chậm, **nếu nguồn đã có cơ chế durable handoff/ack phù hợp**.
- Cách ly một loại công việc blocking I/O khỏi thread nhận request hoặc thread poll của nguồn.
- Tạo **pool riêng** cho một loại workload để không làm nghẽn toàn bộ application.
- Điều tiết concurrency: chỉ cho 8 request cùng lúc vào một downstream có capacity hữu hạn.
- Dùng queue persistent để cân bằng tốc độ producer/consumer khác nhau và cho phép replay sau restart.
- Phân tách nhiều nhánh xử lý độc lập, có error policy và SLA riêng.

**Ví dụ không nên thêm executor chỉ để “tăng tốc”:**

- Handler rất ngắn và nhẹ; overhead scheduling/queue có thể lớn hơn lợi ích.
- Inbound adapter đã sử dụng thread pool riêng và concurrency đã đủ.
- Business transaction phải commit hoặc rollback **trước khi nguồn ack** mà chưa có durable handoff độc lập.
- Gateway synchronous cần kết quả ngay và vẫn đợi reply; đổi sang executor có thể chỉ dời chỗ chờ, làm khó timeout/correlation.
- Flow có yêu cầu thứ tự tuyệt đối nhưng executor nhiều worker làm đảo thứ tự.

### Một sơ đồ quyết định nhanh

~~~mermaid
flowchart TD
    A["Muốn đặt thread boundary?"] --> B{"Handler chậm hoặc cần isolation?"}
    B -- "Không" --> SYNC["Ưu tiên DirectChannel + giới hạn concurrency ở nguồn"]
    B -- "Có" --> C{"Nguồn có thể ack trước khi handler hoàn tất?"}
    C -- "Không" --> D{"Có durable handoff/transaction phù hợp?"}
    D -- "Không" --> KEEP["Giữ xử lý đồng bộ hoặc thiết kế durable inbox/queue trước"]
    D -- "Có" --> ASYNC["Tách worker sau durable commit"]
    C -- "Có, chấp nhận semantics" --> E{"Tải vượt năng lực thì xử lý thế nào?"}
    E -- "Có bounded queue/reject/backpressure" --> ASYNC
    E -- "Chưa có" --> PLAN["Thiết kế capacity và recovery trước"]
    ASYNC --> TEST["Test timeout, restart, redelivery, ordering và metrics"]
~~~

**Câu hỏi cốt lõi không phải “có bao nhiêu thread?” mà là “trách nhiệm xử lý message đã được bàn giao an toàn chưa?”**

## 4. DirectChannel: đường đồng bộ và transaction continuity

Với **DirectChannel**, việc handler được gọi trên cùng thread giúp một transaction thread-bound có thể bao trùm nhiều bước.

~~~text
Kafka/JMS listener thread (tùy adapter/transaction)
    → DirectChannel
    → validate
    → businessHandler
    → DB update/commit
    → return hoặc throw
    → adapter quyết định ack/nack theo hợp đồng
~~~

Ưu điểm:

- Exception có thể truyền ngược tới sender và ảnh hưởng rollback/error handling của nguồn theo adapter.
- Không tạo executor queue in-memory khó quan sát.
- Gọi đồng bộ giúp caller biết handler đã **return/throw** trước khi send() hoàn tất.
- Dễ reasoning về transaction **nếu** transaction manager và resource đúng.

Nhược điểm:

- Một handler chậm giữ thread của sender lâu.
- Nhiều sender threads cùng truy cập handler; handler có state vẫn cần thread safety.
- Backpressure có thể lan ngược lên listener, HTTP gateway hoặc polling endpoint.
- Nếu sau handler có API bên ngoài, transaction DB không làm API đó atomic với DB.

### Transaction cùng thread không có nghĩa mọi side effect atomic

~~~java
@Transactional
public void handle(OrderCommand command) {
    orderRepository.save(command.order());
    paymentProvider.charge(command.paymentId());
}
~~~

Trong ví dụ, **@Transactional** có thể quản lý transaction DB; nó không làm HTTP payment **rollback** khi transaction DB rollback, và cũng không đảm bảo broker ack nằm trong cùng transaction. Cần **idempotency key, inbox/outbox hoặc reconciliation** nếu có external side effect.

**Tương tự:** Nếu annotation **@Transactional** được gọi bằng self-invocation mà proxy advice không được áp dụng, điều bạn tưởng là một transaction chung có thể không tồn tại. Test transaction active/commit thật thay vì suy đoán theo vị trí annotation.

## 5. ExecutorChannel: nhanh ở bước handoff, không chắc nhanh end-to-end

**ExecutorChannel** gửi một task tới **TaskExecutor** để dispatch message cho subscriber. Nếu executor còn capacity, send() thường trả sớm. Nhưng thời gian hoàn tất **nghiệp vụ** còn bao gồm queue wait và thời gian handler.

~~~text
T0   send(message) bắt đầu
T1   task được executor nhận
T2   send() trả: ~3 ms
T3   task bắt đầu chạy sau chờ queue: ~500 ms
T4   handler làm DB/HTTP: ~250 ms
T5   business effect hoàn tất: ~753 ms sau T0
~~~

**Dispatch latency 3 ms không phải business latency 753 ms.**

### Hai điểm thất bại khác nhau

1. **Handoff thất bại:** Pool shutdown hoặc queue quá tải, executor từ chối task. Lỗi có thể xuất hiện ngay tại send() tùy implementation và rejection policy.
2. **Handoff thành công nhưng handler thất bại:** Worker ném exception **sau khi send() đã return**. Lỗi không tự quay về sender thread; phải có error flow/recovery.

**Nguy cơ quan trọng:** Executor queue mặc định thường chỉ ở bộ nhớ JVM. Một task đã được gửi vào executor nhưng **chưa chạy** có thể biến mất khi process bị kill. Nếu inbound source đã ack ở thời điểm handoff, có thể **mất việc** dù message ban đầu được nhận thành công.

### CallerRunsPolicy có phải giải pháp “an toàn”?

Nếu executor dùng CallerRunsPolicy, khi pool bão hòa, thread gửi có thể trực tiếp thực thi handler. Nó tạo backpressure đơn giản, nhưng làm execution mode **phụ thuộc vào tải**:

~~~text
Khi bình thường: sender → worker thread
Khi queue đầy:  sender → chính sender thread
~~~

Không thiết kế transaction, security context hay error handling dựa trên việc **một số message bất ngờ chạy ở sender thread**. Nếu workload bắt buộc cùng transaction, dùng DirectChannel hoặc transaction boundary rõ ràng. Nếu muốn async nhất quán, chọn rejection policy/backpressure có hợp đồng rõ.

## 6. QueueChannel: thread boundary nằm ở polling consumer

**QueueChannel** là PollableChannel. Sender gửi message vào queue; một **PollingConsumer** thực hiện receive() và gọi handler, thường trên thread thuộc TaskScheduler/poller hoặc một TaskExecutor được cấu hình cho poller.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant Q as QueueChannel
    participant P as Poller thread
    participant H as Handler
    S->>Q: send message
    Q-->>S: send accepted
    Note over S,P: Producer và consumer không cùng call stack
    P->>Q: receive()
    Q-->>P: message
    P->>H: handle()
    H-->>P: success/error
~~~

**Không có transaction tự động kéo dài từ sender sang poller.** Tuy nhiên một **poller** có thể **mở transaction mới trên consumer thread**, bao cả việc receive từ một store transactional và xử lý handler đồng bộ. Đây là cách tạo ranh giới transaction có ý nghĩa ở phía nhận.

### In-memory vs persistent QueueChannel

| Backing | Qua JVM restart? | Vấn đề thiết kế |
| --- | --- | --- |
| **QueueChannel mặc định** | Không, state nằm trong JVM | Cần nguồn có khả năng replay hoặc chấp nhận mất message |
| **Bounded in-memory QueueChannel** | Không | Có giới hạn capacity nhưng không tạo durability |
| **JDBC ChannelMessageStore** | Có thể giữ message đã commit | Cần transaction, schema, serializer, groupId/region ổn định |
| **Backend persistent khác** | Phụ thuộc implementation và durability | Phải kiểm tra receive/remove/recovery semantics |

### Poller transaction không tự bao trùm worker được handoff tiếp

~~~text
Transaction A trên poller thread:
    QueueChannel.receive()  [remove pending]
    ExecutorChannel.send()  [enqueue vào task queue RAM]
    COMMIT A

Worker thread:
    BusinessHandler.handle()
    process bị kill trước khi hoàn tất
~~~

Nếu message đã được remove bền vững khỏi QueueChannel sau COMMIT A và task của worker chỉ còn trong RAM, restart có thể **không còn message nào để replay**. Vì vậy hãy đặt **durable handoff ở ranh giới cần thiết**, không chỉ thêm một JDBC store “ở đâu đó” trong flow.

### Poller cần được cấu hình riêng

Một PollableChannel không tự tiêu thụ message. Endpoint đọc từ QueueChannel cần **poller trigger**; maxMessagesPerPoll, receiveTimeout, advice chain và transaction quyết định lịch chạy, batch size và ranh giới xử lý.

~~~xml
<int:service-activator input-channel="ordersQueue"
                       ref="orderHandler"
                       method="handle">
    <int:poller fixed-delay="200" max-messages-per-poll="5">
        <int:transactional
                transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

Đây là fragment XML; cần namespace, channel và các bean được định nghĩa đầy đủ. Nếu handler downstream dùng ExecutorChannel, transaction ở poller **không tự đi qua ranh giới đó**.

## 7. PublishSubscribeChannel và fan-out bất đồng bộ

Một **PublishSubscribeChannel** có thể phát message cho nhiều subscribers:

~~~mermaid
flowchart LR
    I["OrderAccepted"] --> P["PublishSubscribeChannel"]
    P --> A["Audit handler"]
    P --> B["Notification handler"]
    P --> C["Analytics handler"]
~~~

Khi **không có executor**, subscriber thường chạy đồng bộ trong sender thread. Một handler chậm có thể giữ sender và ảnh hưởng nhánh khác.

Khi dùng **PublishSubscribeChannel(executor)**, việc dispatch có thể chạy bất đồng bộ, thậm chí song song. Lợi ích là các nhánh tách thời gian thực thi; rủi ro là:

- Exception không tự truyền về sender khi dispatch async.
- Không được mặc định toàn bộ nhánh đã hoàn tất khi send() trả.
- Transaction sender không tự bao trùm transaction của từng nhánh.
- Thứ tự finish của các subscriber có thể khác thứ tự gửi.
- **Thành công của nhánh Audit không tự bảo đảm nhánh Notification thành công**.
- Nếu event phải được xử lý bền vững ở mỗi nhánh, cần **durable fan-out** hoặc outbox/broker/consumer riêng.

### Tương quan message khi các nhánh cần join

Nếu sau fan-out có aggregator/resequencer, các nhánh cần correlation/sequence metadata phù hợp. Spring Integration có khả năng **applySequence** cho PublishSubscribeChannel; cần hiểu nó tạo sequence headers như thế nào và cách release group khi một nhánh lỗi.

**Không tự dùng correlationId làm idempotency key:** Một order có thể sinh nhiều event hợp lệ trong cùng workflow; eventId/operationId phải định danh một tác dụng nghiệp vụ cụ thể.

## 8. Ba cách thiết kế thread boundary cho luồng đơn hàng

Giả sử ứng dụng nhận **OrderSubmitted** từ broker, kiểm tra dữ liệu, ghi trạng thái vào PostgreSQL và gọi một external service. Ba thiết kế trông giống nhau về chức năng nhưng có hợp đồng reliability khác nhau.

### Phương án A — Đồng bộ đến khi xử lý business hoàn tất

~~~mermaid
flowchart LR
    B["Broker consumer"] --> D["DirectChannel"]
    D --> V["Validate"]
    V --> H["Transactional business handler"]
    H --> DB[("PostgreSQL")]
    H --> ACK["Adapter ack sau xử lý<br/>theo hợp đồng nguồn"]
~~~

**Phù hợp khi** latency xử lý đáp ứng yêu cầu của consumer, muốn lỗi truyền ngược để adapter quyết định rollback/nack và không cần thêm async queue. Thông lượng vẫn có thể tăng bằng **concurrent broker consumers**, dù mỗi delivery đi qua handler đồng bộ.

**Cẩn trọng:** HTTP side effect vẫn không thuộc cùng DB transaction. Một adapter cụ thể có thể ack ở thời điểm khác; phải kiểm tra container/ack mode, không suy ra tự động từ DirectChannel.

### Phương án B — Durable inbox/outbox rồi mới handoff async

~~~mermaid
flowchart LR
    B["Broker consumer"] --> I["Validate + durable inbox/write"]
    I --> DB[("DB COMMIT")]
    DB --> ACK["ACK nguồn theo policy"]
    DB --> W["Durable work rows / outbox"]
    W --> P["Worker poller"]
    P --> H["Async business processing"]
    H --> E["External API / outbound"]
~~~

**Phù hợp khi** không muốn giữ broker thread chờ xử lý chậm, nhưng không thể mất việc sau crash. Nguồn chỉ được xác nhận thành công **sau khi durable handoff đã được commit theo hợp đồng**. Worker có thể restart và đọc lại công việc chưa hoàn tất.

**Cẩn trọng:** “Ghi inbox” phải đại diện cho một công việc có thể **được worker tiếp tục**; không đánh dấu DONE rồi bỏ qua nếu downstream effect chưa xảy ra. Dùng state machine PENDING/PROCESSING/COMPLETED/UNKNOWN, lease/reclaim khi worker chết, unique key và idempotency.

### Phương án C — ExecutorChannel trực tiếp sau inbound

~~~mermaid
flowchart LR
    B["Broker consumer"] --> V["Validate"]
    V --> E["ExecutorChannel"]
    E --> Q["Executor queue<br/>in-memory"]
    Q --> H["Worker handler"]
    H --> DB[("DB")]
~~~

**Phù hợp khi** cần isolation/parallelism và có **hợp đồng chấp nhận rủi ro** hoặc nguồn/handoff được phối hợp sao cho mất task trong RAM không làm mất nghiệp vụ. Nó **không tự an toàn** cho at-least-once business processing khi nguồn ack ngay sau send().

**Cảnh báo:** Đừng chọn C chỉ vì benchmark send() “nhanh hơn”. Nếu process bị kill sau khi sender nhận success nhưng trước khi worker chạy, message có thể biến mất khỏi executor queue.

### So sánh kiến trúc

| Tiêu chí | A: Sync | B: Durable async | C: In-memory async |
| --- | --- | --- | --- |
| Handler blocking sender | Có | Chỉ giai đoạn durable write | Thường không |
| Độ bền việc chưa xử lý | Phụ thuộc nguồn và ack | Có thể bảo đảm qua durable state đã commit | Không do ExecutorChannel tự cung cấp |
| Transaction ingress→handler | Có thể chung khi cùng thread/resource | Cố ý tách transaction | Không tự chung |
| Retry/recovery | Adapter + handler policy | Durable worker retry + idempotency | Worker error flow; nếu crash cần nguồn khác replay |
| Độ phức tạp | Thấp hơn | Cao hơn | Dễ tạo nhưng dễ giấu lỗi |
| Khi scale nhiều replica | Consumer concurrency/partition | Shared work store/broker/lease | Task queue thuộc từng JVM |

## 9. Java DSL: tạo ranh giới thread có tên, pool và giới hạn rõ ràng

Ví dụ sau minh họa một flow **cố ý đặt ExecutorChannel sau bước validate**, với **pool hữu hạn** và một business handler có transaction **riêng trên worker thread**.

### Định nghĩa channel và executor

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
class OrderRuntimeFlowConfiguration {

    @Bean("ordersInput")
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean("ordersWorkerExecutor")
    ThreadPoolTaskExecutor ordersWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("orders-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean("ordersAsync")
    MessageChannel ordersAsync(ThreadPoolTaskExecutor ordersWorkerExecutor) {
        return new ExecutorChannel(ordersWorkerExecutor);
    }

    @Bean
    IntegrationFlow orderFlow(OrderValidator validator,
                              OrderProcessor processor) {
        return IntegrationFlow.from("ordersInput")
                .transform(validator, "validate")
                .channel("ordersAsync")
                .handle(processor, "process")
                .get();
    }
}
~~~

Các beans **OrderValidator** và **OrderProcessor** phải được đăng ký trong context; ví dụ triển khai ở phần dưới. ThreadPoolTaskExecutor do Spring quản lý sẽ có lifecycle phù hợp với bean; nếu tự khởi tạo ngoài container, phải quản lý initialize/shutdown.

**Những quyết định có chủ đích trong ví dụ:**

1. **ordersInput** là DirectChannel; validate chạy trong sender thread.
2. **ordersAsync** là ExecutorChannel, tạo điểm handoff tường minh với tên rõ ràng.
3. **ordersWorkerExecutor** dành riêng cho order flow, tránh tranh capacity với các flow khác.
4. **Core=4, max=8, queue=100** là tham số minh họa, không phải giá trị production mặc định. Với ThreadPoolExecutor, maxPoolSize thường chỉ được dùng mạnh hơn **khi queue đã đầy**, không phải lúc nào cũng chạy 8 worker ngay.
5. **AbortPolicy** từ chối task khi quá tải: lỗi handoff cần được xử lý tại sender/adapter, không nuốt rồi ack thành công.
6. **Bản thân executor queue vẫn ở RAM**. Đây là flow minh họa async thread boundary, **không phải thiết kế durable processing đầy đủ**.

### DTO, validator và handler

~~~java
record OrderCommand(String eventId, String orderId, long amountMinor) {}
record ValidatedOrder(String eventId, String orderId, long amountMinor) {}

class OrderValidator {
    public ValidatedOrder validate(OrderCommand input) {
        if (input.eventId() == null || input.eventId().isBlank()
                || input.orderId() == null || input.orderId().isBlank()
                || input.amountMinor() <= 0) {
            throw new IllegalArgumentException("Invalid order command");
        }
        return new ValidatedOrder(
                input.eventId(), input.orderId(), input.amountMinor());
    }
}

// Bean do Spring quản lý, được gọi qua endpoint/proxy thích hợp.
class OrderProcessor {
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    OrderProcessor(org.springframework.jdbc.core.JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @org.springframework.transaction.annotation.Transactional
    public void process(ValidatedOrder order) {
        jdbc.update(
                "UPDATE orders SET status='ACCEPTED' WHERE order_id=?",
                order.orderId());
    }
}
~~~

Trong ứng dụng thật:

- Đăng ký OrderValidator và OrderProcessor làm Spring beans; JdbcTemplate/DataSource phải được cấu hình.
- Handler process() chạy trong **worker thread** khi ExecutorChannel dispatch async. Nếu **@Transactional proxy** áp dụng đúng, nó mở transaction tại worker.
- Transaction của handler **không đồng nhất** với transaction của sender/inbound adapter. Lỗi process() có thể xuất hiện sau khi sender đã trả success.
- Ví dụ chưa có durable inbox, kiểm tra idempotency/event version, error flow hay trạng thái outbox; cần bổ sung trước khi dùng cho xử lý tiền/đơn hàng không chấp nhận mất.
- Bước validate nằm **trước** boundary nên lỗi dữ liệu được ném đồng bộ; lỗi DB tại process() nằm **sau** boundary và cần xử lý async.

### Cấu hình XML tương ứng cho ExecutorChannel

~~~xml
<int:channel id="ordersAsync">
    <int:dispatcher task-executor="ordersWorkerExecutor"
                    failover="false"/>
</int:channel>
~~~

Đây là fragment XML; cần bean executor và namespace integration. Khi nhiều subscribers, **failover/load balancing** có thể ảnh hưởng lựa chọn handler; nếu logic nghiệp vụ chỉ nên có một owner, tránh nhiều subscriber cùng cạnh tranh mà không có thiết kế rõ.

## 10. Transaction boundary: một giao dịch không nhảy qua thread

Spring transaction thông thường dùng **thread-bound context**. Khi:

~~~text
Sender thread                          Worker thread
BEGIN TX-A
send(M) → ExecutorChannel.submit()
COMMIT TX-A                            handle(M)
                                       BEGIN TX-B
                                       business update
                                       COMMIT / ROLLBACK TX-B
~~~

**TX-A và TX-B độc lập** trừ khi có một cơ chế phối hợp được thiết kế cụ thể. Việc handler có @Transactional không kéo nó ngược trở lại TX-A, và **TX-B rollback không rollback TX-A đã commit**.

### Vì sao điều này nguy hiểm ở inbound broker?

Nếu adapter coi **send() thành công** là đủ để commit offset/ack:

~~~text
Inbound broker delivery
    → ExecutorChannel accepts task
    → inbound ACK / offset commit
    → worker later fails before business DB commit
~~~

Khi source đã ack, nó có thể **không giao lại**. Nếu task bị kill hoặc error flow không lưu durable recovery, message có thể mất mặc dù log ingress báo đã xử lý.

**Điểm quyết định là hợp đồng cụ thể của adapter**: không phải mọi Kafka/JMS/AMQP inbound đều ack sau send theo cùng một cách. Cần kiểm chứng ack mode, transaction boundary, container lifecycle, error handler và vị trí handoff.

### Một mô hình durable inbox an toàn hơn

~~~sql
CREATE TABLE work_inbox (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Một inbound handler đồng bộ có thể:

1. Xác thực message và business eventId.
2. **INSERT** công việc theo unique key vào bảng inbox trong transaction.
3. COMMIT durable record.
4. Chỉ sau đó để adapter xác nhận nguồn theo contract.
5. Worker riêng **poll/claim** công việc PENDING từ DB và bắt đầu transaction xử lý mới.
6. Sau effect/commit, đổi state COMPLETED hoặc UNKNOWN/FAILED theo workflow; worker chết thì có lease/recovery.

**Không đánh dấu COMPLETED khi mới enqueue.** Inbox ở đây lưu một **durable obligation**: công việc phải được tiếp tục cho tới khi có outcome rõ ràng. Với external API, kết quả UNKNOWN cần reconciliation và idempotency key.

### Poller và transaction riêng của consumer

Nếu dùng JdbcChannelMessageStore-backed QueueChannel, có thể mở transaction ở **poller** để gộp dequeue + xử lý **đồng bộ trên consumer thread**. Khi handler throw dẫn đến rollback, message có thể được đọc lại. Nhưng nếu poller tiếp tục dispatch vào ExecutorChannel và commit trước khi worker chạy, lỗ hổng handoff quay lại.

**Quy tắc thực hành:** Đặt **transaction boundary** ở nơi có thể kiểm chứng một cam kết durable cụ thể. Không gọi transaction là “end-to-end” nếu tồn tại ranh giới thread hoặc external side effect nằm ngoài phạm vi quản lý.

## 11. Exception và errorChannel sau khi đổi thread

Ở đường đồng bộ:

~~~text
input.send()
  → DirectChannel
     → handler throws
  → sender có thể bắt exception
~~~

Ở đường bất đồng bộ:

~~~text
input.send()
  → ExecutorChannel
     → task accepted
  → send returns

worker executes:
  → handler throws
  → error handling in worker / ErrorMessage nếu được cấu hình
~~~

Một **MessageHandlingException** tại worker có thể không quay lại sender, kể cả khi message ban đầu được gửi qua MessagingTemplate hoặc inbound adapter. Spring Integration hỗ trợ phát **ErrorMessage** thông qua error infrastructure cho một số asynchronous endpoints; phải xác minh đường thực tế của adapter/channel/version.

### Không mặc định global errorChannel nhận mọi lỗi

Các trường hợp có thể khác nhau:

| Vị trí | Đường lỗi cần kiểm chứng |
| --- | --- |
| DirectChannel handler | Exception thường truyền ngược người gọi |
| ExecutorChannel handler | Error handler/task context, ErrorMessage nếu có publisher phù hợp |
| QueueChannel polling consumer | Poller error channel, scheduler và advice |
| PublishSubscribeChannel có executor | Error handler cho async subscribers |
| Inbound broker adapter | Listener/container error handling và ack/nack policy |
| Outbound gateway | Exception của client có thể được bọc; nếu async cần error flow |

Nếu một ErrorMessage đã được log, **chưa chắc** message gốc sẽ được broker giao lại. Recovery callback có thể đã xử lý exception hoặc sender đã ack trước khi error xảy ra.

### Giữ failedMessage và correlation

Một error consumer nên cố truy **MessagingException.failedMessage** hoặc **ErrorMessage.originalMessage** nếu có, rồi ghi **eventId/operationId/correlationId** ổn định.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

class OrderErrorInspector {
    void inspect(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (cause instanceof MessagingException messaging
                && messaging.getFailedMessage() != null) {
            original = messaging.getFailedMessage();
        }

        String eventId = original == null
                ? "unknown"
                : String.valueOf(original.getHeaders().get("eventId"));

        System.out.println("eventId=" + eventId
                + ", errorType=" + cause.getClass().getSimpleName());
    }
}
~~~

Đây là minh họa chẩn đoán, **không log raw payload hoặc secrets** và không giả định failed/original message luôn có. Exception ở source trước khi tạo Spring Message có thể không chứa failedMessage.

### Error handling phải có kết cục bền vững

Khi xử lý lỗi sau async handoff:

- Transient: retry có **budget + backoff/jitter** theo retry owner.
- Permanent: quarantine/DLQ bền vững, không thử vô hạn.
- Outcome external chưa chắc chắn: ghi **UNKNOWN_OUTCOME**, dùng provider query/idempotency.
- Đã xử lý: xác nhận delivery hoặc ghi state COMPLETED theo contract.

**Đừng để error handler chỉ log rồi kết thúc** nếu nguồn đã ack nhưng worker chưa có kết quả nghiệp vụ: sẽ có “đã nhận nhưng không xử lý” mà không còn nơi replay.

## 12. ThreadLocal, MDC, SecurityContext và tracing khi handoff

Nhiều thành phần Java/Spring giữ thông tin trong **ThreadLocal**, tức là dữ liệu gắn với **thread hiện tại**, không mặc định nằm trong message:

- **TransactionSynchronizationManager** chứa một phần transaction synchronization/resource context.
- **org.slf4j.MDC** thường giữ traceId, correlationId hoặc các trường log.
- **SecurityContextHolder** theo chế độ cấu hình mặc định thường dùng thread-local context.
- **RequestContextHolder** có thể gắn request attributes với thread xử lý HTTP.
- Các thư viện tracing/observation có context holder và propagation mechanism riêng.

Khi chuyển từ sender thread sang worker:

~~~text
sender thread:
  MDC(traceId=A)
  SecurityContext(user=X)
  DB transaction TX-A
  → ExecutorChannel.send(M)

worker thread:
  MDC(?) không tự bảo đảm = A
  SecurityContext(?) không tự bảo đảm = X
  TransactionSynchronizationManager(?) không còn TX-A
~~~

**Message headers khác ThreadLocal.** Một header eventId hoặc correlationId có thể đi theo message nếu transformer/adapter giữ nó, nhưng MDC/trace context không tự được chuyển chỉ vì header tồn tại.

### Propagate metadata, không propagate transaction

Một thực hành an toàn:

1. Đưa **eventId, correlationId, operationId, tenant/authorization context cần thiết** vào message theo một hợp đồng dữ liệu đã kiểm tra.
2. Ở worker, khôi phục **logging/tracing context** bằng cơ chế context propagation được framework/tracing library hỗ trợ.
3. **Mở transaction mới** với transaction manager phù hợp bên trong worker.
4. Không chuyển một **JDBC Connection, EntityManager, transaction object, RequestAttributes live** xuyên thread bằng cách copy ThreadLocal tùy tiện.
5. Nếu cần ủy quyền trên worker, dùng thông tin **đã xác thực và được ủy quyền qua một đường tin cậy**, không tin header roles do producer không được kiểm soát gửi lên.
6. Dọn context sau khi worker hoàn thành để thread trong pool không mang thông tin của message trước.

### Ví dụ TaskDecorator cho MDC

Với ứng dụng dùng SLF4J MDC, một **TaskDecorator** có thể giúp sao chép diagnostic context tại lúc submit task:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Trong cấu hình ThreadPoolTaskExecutor:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

Đây là ví dụ cho **MDC log context**, **không phải** giải pháp tổng quát để sao chép observation context, SecurityContext hay transaction. Với Micrometer Observation/Tracing, nên ưu tiên **context-propagation integration được hỗ trợ** theo bộ phiên bản đang dùng và test trace/span xuyên ranh giới thực tế.

**Cảnh báo:** MDC có thể chứa dữ liệu nhạy cảm, còn việc capture context trên hàng đợi lớn giữ thêm đối tượng trong bộ nhớ. Hạn chế field cần truyền, dọn sạch sau task, không gắn eventId/traceId thành high-cardinality metric tags.

## 13. Correlation, ordering và song song theo khóa nghiệp vụ

Khi dùng nhiều workers, **thứ tự bắt đầu** và **thứ tự hoàn tất** không nhất thiết bằng thứ tự message được gửi:

~~~text
Input:  order O-42 version 1, version 2, version 3

Worker 1 xử lý v1: HTTP 900 ms
Worker 2 xử lý v2: DB 100 ms
Worker 3 xử lý v3: DB 120 ms

Output theo completion: v2, v3, v1
~~~

Nếu handler cuối ghi đè trạng thái order, version 1 hoàn tất sau có thể **ghi lùi** dữ liệu. Đây không chỉ là vấn đề hiệu năng; nó có thể là lỗi tính đúng đắn nghiệp vụ.

### Ba chiến lược tùy hợp đồng

**1. Không cần ordering**

Các event độc lập và side effect idempotent. Dùng worker pool nhiều thread, nhưng thiết kế duplicate/consistency riêng.

**2. Cần ordering theo business key**

Đảm bảo **cùng orderId** được xử lý tuần tự, nhưng **orderId khác nhau** có thể chạy song song. Có thể dùng:

- Broker partitioning theo orderId và một consumer xử lý tuần tự theo partition **khi ack và handoff semantics phù hợp**.
- Một **partitioned/serial executor** theo key, với bounded queues và phân phối hot keys.
- **PartitionedChannel** ở những phiên bản Spring Integration có hỗ trợ, với hàm chọn partition key được thiết kế cẩn thận.
- DB **optimistic locking/version check**, thậm chí khi có ordering, để ngăn stale update do retry/replay.

**3. Cần thứ tự tổng thể**

Giới hạn concurrency, dùng một thứ tự nguồn đáng tin cậy hoặc **resequencer**; đánh đổi throughput và tăng rủi ro head-of-line blocking. Đừng tự giả định QueueChannel + nhiều consumers giữ một thứ tự hoàn tất toàn cục.

### Correlation khác ordering và idempotency

| Khái niệm | Dùng để làm gì? | Có thể thay nhau không? |
| --- | --- | --- |
| **correlationId** | Gắn các phần của một workflow/message group | Không mặc định là dedup key |
| **sequenceNumber/sequenceSize** | Giúp splitter/aggregator/resequencer quản lý các phần và thứ tự | Không bảo đảm worker chạy xong theo thứ tự |
| **eventId** | Định danh một event nguồn cụ thể | Có thể phù hợp dedup cho event, tùy hợp đồng |
| **operationId/paymentId** | Định danh một side effect nghiệp vụ | Thường là idempotency key phù hợp cho side effect |
| **business version** | Ngăn cập nhật cũ ghi đè state mới | Không thay thế lưu message hoặc retry policy |

### Hot key và phân vùng

Nếu 50% message cùng orderId/tenant key, “partition theo key” có thể biến một partition thành bottleneck. Cần đo throughput theo shard, queue wait, xử lý công việc nặng khác thường và phương án scale mà không phá ordering guarantee.

## 14. Retry và timeout phải theo từng ranh giới

Thêm executor làm xuất hiện **nhiều deadline**:

~~~text
Inbound broker visibility / ack deadline
    ├─ thời gian đợi TaskExecutor queue
    ├─ worker execution timeout
    ├─ DB transaction timeout
    ├─ outbound HTTP request timeout
    ├─ RetryAdvice backoff / attempts
    └─ gateway reply timeout (nếu request-reply)
~~~

**Timeout của send()** khác **timeout hoàn tất business effect**. Ví dụ TaskExecutor queue có thể nhận task ngay nhưng giữ 40 giây trước khi worker xử lý. Một gateway chờ reply 10 giây có thể timeout dù task cuối cùng vẫn chạy và tạo side effect sau đó.

### Retry amplification khi nhiều lớp độc lập

~~~text
Broker redelivery: 3 deliveries
Handler retry advice: 4 attempts / delivery
HTTP client retry: 2 calls / handler attempt

Tối đa 3 × 4 × 2 = 24 HTTP calls
cho cùng một operationId.
~~~

Khi đặt thread boundary, xác định **retry owner** và ai thực hiện **durable recovery**:

- **Trước boundary:** Validation và durable write thất bại thì nguồn có thể cần retry/redeliver.
- **Sau boundary:** Worker error phải có đường xử lý độc lập; không giả định lỗi tự quay về sender.
- **Sau external effect:** Outcome có thể chưa biết, cần stable idempotencyKey và reconciliation, không chỉ RetryTemplate.
- **Hết attempts:** Đưa sang DLQ/quarantine/retry journal **bền vững** trước khi ack cuối nếu nghiệp vụ yêu cầu không mất.

### Deadline đầu cuối

Không đặt gateway timeout 5 giây trong khi downstream worker queue thường chờ 8 giây mà không có quyết định thiết kế rõ. Nếu gateway hết hạn, caller có thể gửi lại **cùng operation** và gây duplicate.

Một chính sách tốt phải định nghĩa:

1. **Enqueue accepted** có nghĩa gì với caller?
2. Khi timeout, công việc có bị cancel thật hay vẫn chạy?
3. Nếu caller retry, có dùng **cùng operationId** không?
4. Có cơ chế query status theo operationId không?
5. Sau restart, worker mới có tiếp tục công việc đã accepted không?

**Interrupt không phải rollback từ xa.** Một HTTP request đã tới provider có thể vẫn thực thi dù thread Java bị interrupt/hủy Future.

## 15. Messaging Gateway: async channel vẫn có thể khiến caller phải chờ

Một **messaging gateway** thường mang mô hình request–reply:

~~~mermaid
sequenceDiagram
    participant C as REST caller
    participant G as MessagingGateway
    participant E as ExecutorChannel
    participant W as Worker
    C->>G: submit(Order)
    G->>E: requestMessage + replyChannel
    E-->>G: handoff accepted
    Note over G: Gateway vẫn chờ reply
    E->>W: xử lý bất đồng bộ
    W-->>G: reply khi hoàn tất
    G-->>C: business response
~~~

**Lợi ích:** Tách thread của handler khỏi caller khi cần isolation; có thể cho nhiều worker thực thi.

**Giới hạn:** Nếu gateway vẫn chờ một reply đồng bộ, **request thread vẫn có thể bị block** cho tới khi reply/timeout. Việc đặt ExecutorChannel ở giữa **không tự tạo API bất đồng bộ**.

Nếu nghiệp vụ mất hàng phút:

- Trả **202 Accepted** sau khi một durable command đã commit (nếu API/contract chọn mô hình này).
- Cung cấp **operationId** cho endpoint query status hoặc callback/event.
- Dùng durable worker/outbox và idempotency thay vì chỉ một Future trong JVM.
- Quy định timeout/retry của client để không tạo nhiều business operations.

### Reply channel và header sau restart

Một TemporaryReplyChannel hoặc object reply channel trong message có thể chỉ sống trong một JVM. Nếu message được lưu trong persistent QueueChannel rồi worker xử lý sau restart, **replyChannel/errorChannel chứa object không nhất thiết deserialize/resolve được**. Cần thiết kế reply correlation qua **persistent business state**, tên channel được resolver hỗ trợ hoặc một reply transport durable.

**Không nên coi việc gửi Spring Message có replyChannel header là cam kết request-reply bền vững qua nhiều process.**

## 16. Executor sizing, capacity và backpressure

Nên coi một executor riêng như một **nguồn tài nguyên có ngân sách**, không phải “một cách biến mọi tác vụ thành async”.

### Các tham số cần tính cùng nhau

| Tham số | Ảnh hưởng | Rủi ro nếu tùy tiện |
| --- | --- | --- |
| **corePoolSize** | Số worker nền có thể được duy trì | Quá nhỏ gây queue wait lớn |
| **maxPoolSize** | Giới hạn thread khi cần mở rộng | Quá lớn gây context switching/DB overload |
| **queueCapacity** | Số task chờ khi worker bận | Quá lớn che giấu latency và chiếm heap |
| **rejection policy** | Hành vi khi pool/queue đầy | Abort tạo error; CallerRuns đổi thread; silent discard nguy hiểm |
| **threadNamePrefix** | Chẩn đoán thread dump/log | Không có prefix khó gắn lỗi với flow |
| **taskDecorator/context propagation** | Giữ tracing/MDC khi handoff | Sai có thể rò thông tin giữa tasks |
| **shutdown policy** | Đợi task hay hủy khi đóng process | Không thể đảm bảo durability của task memory |
| **downstream concurrency limit** | Số HTTP/DB calls đang hoạt động | Pool lớn hơn DB connection pool có thể làm tải tệ hơn |

### Một quy tắc sizing sơ bộ

Theo Little's Law trong điều kiện ổn định:

\[
L \approx \lambda W
\]

với:

- **L**: số công việc trung bình đang ở trong hệ (queued + in-flight).
- **λ**: thông lượng hoàn tất trung bình (operations/giây).
- **W**: thời gian ở trong hệ trung bình (giây).

Ví dụ khi **λ = 40 operations/s** và **W = 0,5 s**, hệ có trung bình khoảng **20 operations** đang chờ hoặc chạy. Đây chỉ là **ước lượng capacity trung bình**, không phải công thức tự chọn maxPoolSize cho mọi loại công việc. Cần tính P95/P99, variance, retry và DB/HTTP constraints.

### Pool 4–8 threads và queue 100 không đồng nghĩa latency thấp

Nếu mỗi HTTP call chậm từ 100 ms lên 3 giây:

~~~text
worker occupancy tăng mạnh
→ queue bị lấp
→ queue wait p95 tăng
→ caller timeout / retry
→ ingress rate tăng thêm
→ task rejection / retry storm
~~~

Chỉ tăng queueCapacity lên 10.000 có thể khiến send() vẫn nhanh trong khi mỗi message chờ hàng phút. **Backpressure phải sớm và rõ**: giới hạn nguồn nhận, giảm concurrency, kiểm soát retry, có rate limit/circuit breaker và cân nhắc durable buffering.

### Rejection policy là quyết định nghiệp vụ

- **AbortPolicy:** Làm lộ tình trạng quá tải cho sender ngay ở handoff. Sender/adapter phải xử lý lỗi đúng, không ack thành công giả.
- **CallerRunsPolicy:** Có thể đẩy workload sang sender thread, tạo backpressure, nhưng thay đổi bối cảnh transaction/error/thread theo tải.
- **DiscardPolicy/DiscardOldestPolicy:** Có thể bỏ task âm thầm; không phù hợp với nghiệp vụ **không cho phép mất message** nếu thiếu cơ chế bù/khôi phục rõ ràng.
- **Unbounded queue:** Không có giới hạn cứng cho pending work, tăng nguy cơ memory pressure và độ trễ khó kiểm soát.

Một executor pool cho mọi flow có thể tạo **noisy-neighbor failure**: HTTP notification chậm làm nghẽn payment/fulfillment. Nếu SLA và failure domain khác nhau, dùng pool/queue riêng **với capacity limit và monitoring riêng**.

## 17. Shutdown và restart: boundary nào có thể mất việc?

Graceful shutdown thường theo thứ tự ngừng ingress, xử lý in-flight, dừng consumer/executor và đóng resource. Nhưng một task nằm trong executor queue **không có hợp đồng durability** chỉ vì Spring đã nhận task.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant S as Sender
    participant E as ExecutorChannel
    participant W as Worker
    B->>S: Deliver EV-42
    S->>E: send(EV-42)
    E-->>S: accepted
    S-->>B: ACK nguồn (theo một số cấu hình)
    Note over E: Task đang chờ trong queue RAM
    Note over E,W: JVM bị kill trước khi W bắt đầu
    B-->>S: Có thể không redeliver nếu đã ACK
~~~

**Quan sát rủi ro:** Handler không ném exception vì **nó chưa từng chạy**. ErrorChannel cũng có thể không nhận lỗi; chỉ còn metric/trace của handoff và việc thiếu durable result.

### Shutdown có chủ đích

1. **Dừng ingress** theo tất cả sources/instances cần kiểm soát.
2. Giữ worker/executor còn hoạt động để drain task đang có **trong budget**.
3. Quan sát **QueueChannel depth, executor queued, active/in-flight, broker unacked, transaction/DB commit, retry/outbox pending**.
4. Nếu hết shutdown budget, chỉ tuyên bố an toàn khi phần việc còn lại **được lưu bền vững hoặc nguồn sẽ replay** theo contract.
5. Khởi động worker mới và kiểm chứng replay/idempotency, không mặc định task RAM còn tồn tại.

**Spring Boot lifecycle timeout**, **Spring Integration orderly shutdown** và **Kubernetes termination grace** có những đồng hồ khác nhau. Đừng đặt các timeout bằng nhau rồi nghĩ hệ thống có đủ thời gian cho cả preStop, drain và resource cleanup.

### Không dùng lifecycle để chữa lỗ hổng durability

Ví dụ cấu hình **setWaitForTasksToCompleteOnShutdown(true)** và awaitTermination có thể cải thiện graceful shutdown, nhưng **SIGKILL, node failure, OOM, mất điện hoặc grace period hết** vẫn có thể cắt task. **Durable handoff và business idempotency** là thiết kế độc lập, không thể thay bằng “cố đợi thêm”.

## 18. Observability: đo đúng hai phía của thread boundary

Khi thêm ExecutorChannel, việc đánh giá hiệu năng bằng một Timer quanh send() có thể gây hiểu lầm. Cần tách **hơi thở của producer**, **độ trễ tại ranh giới** và **thời gian thực thi consumer**.

~~~mermaid
flowchart LR
    P["Producer"] -->|dispatch timer| EC["ExecutorChannel"]
    EC -->|queue wait timer| W["Worker starts"]
    W -->|handler timer| H["Business handler"]
    H --> D[("DB / external API")]
    EC -. "queue depth / rejects" .-> M["Monitoring"]
    W -. "active / in-flight" .-> M
    H -. "success/error" .-> M
~~~

| Metric / log | Bắt đầu → kết thúc | Điều chẩn đoán |
| --- | --- | --- |
| **orders.dispatch.duration** | Trước send() → send() trả/throw | Handoff vào channel/executor nhanh hay bị block? |
| **orders.executor.wait.duration** | Task thực sự enqueue → handler bắt đầu | Worker pool có quá tải không? |
| **orders.handler.duration** | Handler bắt đầu → return/throw | Nghiệp vụ/DB/HTTP chậm bao nhiêu? |
| **orders.business.e2e.duration** | Operation được chấp nhận → trạng thái business cuối | SLA thực, có thể qua retry/restart |
| **orders.executor.queued** | Số task đang chờ | Task đã rời QueueChannel chưa chắc đã bắt đầu |
| **orders.executor.active** | Số task đang chạy | Mức sử dụng pool |
| **orders.executor.rejected** | Task handoff bị từ chối | Backpressure cần được xử lý |
| **orders.handler.failed** | Handler attempt throw | Thất bại của attempt, không phải operation cuối |
| **orders.operation.completed** | Operation được xác nhận hoàn tất | Nguồn sự thật cần phù hợp với DB commit/idempotency |
| **orders.durable.pending** | Work đã commit nhưng chưa hoàn tất | Khả năng phục hồi sau restart |
| **orders.error.recovered** | Recovery durable hoàn tất | DLQ/quarantine/outbox đã ghi thành công? |

Các tên metrics trên là **ví dụ ứng dụng tự đặt**, không phải danh sách metric framework luôn tạo sẵn. Kiểm tra built-in Micrometer/Observation của phiên bản Spring Integration đang chạy để tránh đo trùng cùng một stage.

### Tính queue wait phải chọn clock đúng

Nếu producer và worker ở **cùng JVM**, một đoạn thời gian có thể được đo bằng monotonic clock phù hợp. Nếu message đã được lưu persistent/broker và tiêu thụ **sau restart hoặc ở host khác**, không thể lấy System.nanoTime() từ JVM cũ trừ cho System.nanoTime() của JVM mới. Khi đó cần timestamp có format và time synchronization rõ, cùng chính sách xử lý clock skew.

**Không thêm eventId, orderId, traceId, timestamp hoặc messageId làm metric tags**. Những giá trị gần như duy nhất tạo cardinality rất cao. Đưa chúng vào **structured logs/traces** có giới hạn truy cập; metrics dùng flow, endpoint, outcome, worker pool, error category từ tập hữu hạn.

### Dấu hiệu của một boundary đặt sai

~~~text
Ingress throughput = 500 msg/s
ExecutorChannel send p95 = 2 ms
Executor queue wait p95 = 45 s
Handler p95 = 1.2 s
Rejected tasks = tăng
Gateway timeouts = tăng
~~~

Nếu chỉ nhìn send p95, tưởng hệ thống rất nhanh. Thực tế source đang giao công việc nhanh hơn downstream xử lý, timeout và retry có thể tiếp tục phóng đại tải.

## 19. JUnit: kiểm chứng đồng bộ và bất đồng bộ

### Test 1 — DirectChannel chạy handler trong thread gọi send()

Test này dùng channel thật của Spring Integration:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.MessageBuilder;

class ChannelThreadBoundaryTest {

    @Test
    void directChannelInvokesHandlerOnCallerThread() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<String> handlerThread = new AtomicReference<>();

        channel.subscribe(message ->
                handlerThread.set(Thread.currentThread().getName()));

        String callerThread = Thread.currentThread().getName();
        assertTrue(channel.send(
                MessageBuilder.withPayload("EV-42").build()));

        assertEquals(callerThread, handlerThread.get());
    }
}
~~~

**Điều chứng minh:** Khi gửi tới DirectChannel, subscriber đồng bộ được gọi trong sender thread. Test không chứng minh cả hệ thống chỉ có một thread; nhiều sender đồng thời vẫn có thể gọi cùng handler.

### Test 2 — ExecutorChannel chuyển xử lý sang worker

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class ExecutorBoundaryTest {

    @Test
    void executorChannelRunsHandlerOnWorkerThread() throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("test-order-worker-");
        executor.afterPropertiesSet();

        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            CountDownLatch processed = new CountDownLatch(1);
            AtomicReference<String> handlerThread = new AtomicReference<>();

            channel.subscribe(message -> {
                handlerThread.set(Thread.currentThread().getName());
                processed.countDown();
            });

            String senderThread = Thread.currentThread().getName();
            assertTrue(channel.send(
                    MessageBuilder.withPayload("EV-42").build()));

            assertTrue(processed.await(2, TimeUnit.SECONDS));
            assertNotEquals(senderThread, handlerThread.get());
            assertTrue(handlerThread.get().startsWith(
                    "test-order-worker-"));
        } finally {
            executor.shutdown();
        }
    }
}
~~~

**Điều chứng minh:** Trong fixture có executor riêng và không có CallerRunsPolicy, handler có thể được dispatch tới worker thread. Không nên kết luận từ một test này rằng mọi ExecutorChannel luôn chạy ở thread khác trong mọi cấu hình; caller-runs/rejection policy tạo ngoại lệ.

### Test 3 — Lỗi đồng bộ tới sender, lỗi async cần quan sát ở worker

Với DirectChannel:

~~~java
DirectChannel channel = new DirectChannel();
channel.subscribe(message -> {
    throw new IllegalStateException("business failure");
});

assertThrows(RuntimeException.class, () ->
        channel.send(
                MessageBuilder.withPayload("EV-43").build()));
~~~

Đây là fragment kiểm tra exception không được bắt trong đường đồng bộ; Spring Integration có thể bọc nguyên nhân vào MessagingException. Với ExecutorChannel, **không dùng lại assertion assertThrows(send())** để kiểm tra lỗi handler đến muộn. Cần tạo **integration test error flow**:

1. Cấu hình ExecutorChannel có consumer thật.
2. Handler ném lỗi trên worker thread.
3. Cấu hình đúng errorChannel/error publisher của endpoint.
4. Dùng QueueChannel test để nhận ErrorMessage với timeout hữu hạn.
5. Assert exception cause, failed/original message nếu có, correlationId/eventId và recovery outcome.
6. Xác minh sender có thể return trước khi worker báo lỗi, nhưng application vẫn có durable recovery nếu nghiệp vụ yêu cầu.

Không mặc định một ErrorMessage sẽ tự xuất hiện ở global errorChannel nếu test không thiết lập error handling tương ứng.

### Test 4 — Kiểm tra transaction không đi cùng worker

Một integration test có thể dùng **TransactionTemplate** quanh send từ sender và một handler được Spring quản lý bên worker để quan sát:

~~~text
Sender thread:
    TransactionSynchronizationManager.isActualTransactionActive() = true
    → ExecutorChannel.send()

Worker thread:
    before its own @Transactional method:
        no inherited TX-A
    inside handler's @Transactional proxy:
        active TX-B
~~~

Test phải sử dụng **DataSource/PlatformTransactionManager thật**, gọi qua bean proxy, dùng CountDownLatch để kiểm soát thời điểm. Không gọi method handler trực tiếp rồi kết luận Spring AOP transaction đã hoạt động; cũng không chạy toàn test trong một test-managed transaction rồi suy rằng worker dùng cùng transaction đó.

**Assertion đúng:** TX-B có thể commit hoặc rollback độc lập với TX-A. Khi handler ném exception sau handoff, TX-A đã commit thì không tự rollback theo TX-B.

## 20. Test bão hòa executor và mất việc tại async handoff

Một test công suất cần chứng minh behavior khi **pool và queue đã đầy**, không chỉ happy path.

### Test với worker bị chặn có chủ đích

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class ExecutorRejectionTest {

    @Test
    void boundedExecutorRejectsAtCapacity() throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(0);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.afterPropertiesSet();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            channel.subscribe(message -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            assertTrue(channel.send(
                    MessageBuilder.withPayload("EV-A").build()));
            assertTrue(started.await(2, TimeUnit.SECONDS));

            // Worker đang bận, executor không có pending queue.
            assertThrows(RuntimeException.class, () ->
                    channel.send(
                            MessageBuilder.withPayload("EV-B")
                                    .build()));
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Test dùng **AbortPolicy** và queueCapacity=0 để có điều kiện rejection rõ. Nếu dùng CallerRunsPolicy, message thứ hai có thể chạy trên sender thread thay vì throw; bài test phải điều chỉnh theo hợp đồng được chọn.

**Đừng tự gọi handler lỗi là “message đã retry”.** Khi handoff bị reject, cần xem nơi bắt exception ở sender, adapter acknowledgement và durable recovery. Trong production, một adapter có thể rollback/redeliver khi send thất bại; nhưng chỉ đúng theo cấu hình nguồn và transaction cụ thể.

### Hard crash test cho sự mất việc sau ACK

Một integration test đáng giá hơn unit test:

1. Dùng broker hoặc nguồn test có **ack policy xác định**.
2. Gửi event EV-42, chèn điểm kiểm soát ngay sau **executor nhận task** nhưng trước khi worker thực hiện.
3. Xác minh nguồn đã hoặc chưa ACK; nếu đã ACK, hãy **kill process**.
4. Khởi động lại process cùng broker/DB store.
5. Kiểm tra EV-42 có được replay và business effect cuối có đúng không.

Nếu source đã ACK mà task chỉ tồn tại trong executor RAM, test có thể phơi bày **không có cơ chế replay**. Khi đó phải sửa **durable handoff/ack boundary**, không sửa test để bỏ qua sự cố.

### Test ordering và correlation

Với hai events cùng orderId và worker pool >1:

- Dùng latch làm worker xử lý **version 1 chậm hơn version 2**.
- Xác minh output có thể đến lệch thứ tự nếu không thiết kế ordering.
- Nếu business yêu cầu cùng order phải tuần tự, thêm partition-by-key hoặc DB optimistic locking/version check.
- Assert **eventId/operationId ổn định** xuyên retry và **correlationId** được giữ trong logs/traces.
- Kiểm tra aggregator/resequencer không coi **group size** đơn thuần là số loại event duy nhất.

## 21. Bảng kiểm quyết định đặt boundary tại đâu

| Yêu cầu | Cách tiếp cận ưu tiên | Điều phải kiểm chứng |
| --- | --- | --- |
| Xử lý rất nhanh, cần exception truyền về nguồn | DirectChannel | Transaction scope và source ack |
| Cần async isolation, chấp nhận in-memory task risk có kiểm soát | ExecutorChannel + bounded executor | Rejection, context/error propagation, shutdown |
| Nguồn nhanh hơn consumer, cần buffering | QueueChannel + poller | Queue capacity, backing store, recovery |
| Work phải sống qua restart | Durable inbox/outbox hoặc persistent MessageStore/broker | Atomic durable handoff, ack/rollback và idempotency |
| DB update phải rollback với dequeue | Transactional poller + same DB resource | Không đặt ExecutorChannel giữa receive và commit |
| Fan-out nhiều subscriber không cùng SLA | PublishSubscribeChannel hoặc durable multi-consumer transport | Lỗi/commit từng nhánh, replay và ordering |
| Synchronous gateway cần reply | DirectChannel hoặc async với deadline rõ | Reply correlation, timeout, late result, duplicate |
| Cần xử lý tuần tự theo orderId | Partition-by-key hoặc version control | Hot keys, order guarantee, crash/restart |
| Downstream dễ quá tải | Isolated bounded pool + backpressure | Queue wait, rejection, retry budget |
| Long-running external API | Durable command + status query | Timeout không tự cancel effect, unknown outcome |
| Nhiều replica | Shared durable state/partitioning và coordination | Không dựa vào RAM/JVM lock cho toàn cluster |

## 22. Anti-pattern: những lỗi kiến trúc khi tạo boundary “cho nhanh”

### Anti-pattern 1 — Đổi DirectChannel thành ExecutorChannel mà không xem ACK

~~~text
Inbound adapter
  → ExecutorChannel.accept()
  → nguồn ACK
  → worker mới xử lý business
~~~

Khi process chết ở giữa, nguồn có thể không redeliver và task chỉ có trong RAM. **Khắc phục:** xác nhận ack boundary của adapter, durable handoff hoặc giữ đồng bộ đến khi công việc được lưu bền vững.

### Anti-pattern 2 — Đặt transaction ở sender, kỳ vọng worker dùng chung

~~~text
@Transactional service
  → async channel
     → worker updates DB
  → sender commits
~~~

Spring transaction thông thường là **thread-bound**, không tự chuyển sang worker. **Khắc phục:** thiết kế transaction của từng stage trên thread tương ứng; nếu cần atomic guarantee, không cắt transaction bằng async handoff không phối hợp.

### Anti-pattern 3 — Dùng queue không giới hạn thay cho backpressure

Queue lớn có thể giữ send() nhanh trong nhiều phút nhưng tạo P99 queue wait cực cao, tăng heap và làm client timeout rồi retry. **Khắc phục:** bounded capacity, rejection có ý nghĩa, rate limit, load shedding có chủ đích hoặc durable buffering đúng yêu cầu.

### Anti-pattern 4 — Dùng CallerRunsPolicy như một bảo đảm về transaction

Khi tải thường, worker thread; khi overload, sender thread. **Khắc phục:** không dựa vào behavior ngẫu nhiên theo tải để xác định transaction/security/error semantics; có error/backpressure policy độc lập.

### Anti-pattern 5 — Quên propagation của context

Log worker thiếu traceId/correlationId hoặc tệ hơn là giữ MDC của message trước trong pool thread. **Khắc phục:** propagation được hỗ trợ, làm sạch ThreadLocal trong finally, truyền business keys qua headers/payload đáng tin cậy.

### Anti-pattern 6 — Giữ thứ tự “bằng niềm tin”

Nhiều workers xử lý cùng orderId mà không có partition/version check. **Khắc phục:** ordering theo business key, version guard, kiểm thử completion out-of-order và retry.

### Anti-pattern 7 — Một executor dùng cho mọi nhánh

Email/analytics chậm giữ hết worker; payment quan trọng không còn slot, thậm chí control plane bị nghẽn. **Khắc phục:** cách ly pool theo SLA/failure domain, đo capacity và giới hạn từng loại công việc.

### Anti-pattern 8 — Dùng @Async/Future nhưng vẫn chờ kết quả ngay

Caller tạo một Future rồi gọi get() ngay, vẫn block mà còn phải quản lý timeout/context/error ở ranh giới mới. **Khắc phục:** nếu cần synchronous result và latency ngắn, có thể giữ DirectChannel; nếu thực sự async, dùng durable command + operation status thay vì một Future chỉ sống trong JVM.

### Anti-pattern 9 — Bắt exception rồi return thành công để tránh đỏ log

Handler bắt lỗi, ghi log và trả bình thường khiến upstream có thể ack message, mất cơ hội replay. **Khắc phục:** phân loại lỗi, propagate/rollback khi cần và lưu durable recovery/DLQ trước khi báo hoàn tất.

### Anti-pattern 10 — Stop ingress và consumer cùng lúc, kỳ vọng queue tự drain

Backlog trong QueueChannel vẫn còn khi consumer bị stop. **Khắc phục:** quiesce inbound trước, giữ poller/worker đến khi đạt điều kiện hoặc budget; nếu còn pending, cần durable recovery sau restart.

## 23. Bài thực hành thiết kế: đặt boundary cho dịch vụ Order Fulfillment

**Bài toán:** Một service nhận khoảng **300 OrderSubmitted events/giây** từ broker, kiểm tra dữ liệu, ghi PostgreSQL và gọi inventory/payment providers. Một số request mất 2–5 giây. Service có bốn replica và phải:

- Không mất operation đã được ACK là accepted.
- Không thu tiền/giảm tồn kho hai lần khi có retry/redelivery.
- Trả phản hồi tiếp nhận trong thời gian ngắn, không đợi payment hoàn tất.
- Giữ thứ tự cập nhật trạng thái **theo orderId**, không bắt buộc toàn cục.
- Giới hạn số request đồng thời tới downstream.
- Khôi phục sau deploy, SIGTERM và crash bất thường.
- Có error flow, DLQ/quarantine, metrics và correlation đủ để điều tra.

### Bước 1 — Chọn hợp đồng với producer

Định nghĩa **eventId**, **orderId**, **operationId**, schema version và yêu cầu delivery. Broker có thể giao lại event; mọi business effect phải idempotent.

**Không** xác nhận “accepted” chỉ vì một ExecutorChannel in-memory đã nhận task.

### Bước 2 — Durable handoff trước boundary

~~~mermaid
flowchart TD
    B["Broker event"] --> V["Validate + preserve IDs"]
    V --> TX["Transactional Inbox / work table"]
    TX --> DB[("PostgreSQL COMMIT")]
    DB --> ACK["Broker ACK theo adapter contract"]
    DB --> W["Durable work queue / worker poller"]
    W --> K{"Partition/orderId"}
    K --> P1["Worker partition 1"]
    K --> P2["Worker partition 2"]
    K --> P3["Worker partition N"]
    P1 --> EXT["Payment / inventory APIs"]
    P2 --> EXT
    P3 --> EXT
    EXT --> OUT[("Business state + outbox")]
    OUT --> PUB["Outbox publisher"]
~~~

Chỉ khi durable work row đã được commit thì adapter mới được phép xem handoff là thành công theo policy được chọn. Với hai deliveries cùng eventId, **unique constraint** bảo đảm chỉ một logical work item.

### Bước 3 — Xử lý riêng theo partition/orderId

Worker lấy công việc từ durable store, đảm bảo:

- Cùng **orderId** không cập nhật trái thứ tự đã cam kết.
- OrderId khác nhau có thể chạy song song.
- Khi worker chết, lease/pending work có cơ chế reclaim.
- Dùng optimistic version/unique business operation key để bảo vệ khi replay.

### Bước 4 — Giới hạn external concurrency

Đặt riêng pool hoặc rate limiter cho payment và inventory. Các API có timeouts và idempotency keys; có response UNKNOWN thì reconciliation, không retry mù.

Nếu queue quá tải, hệ thống có thể **giữ durable pending**, giảm ingress hoặc trả backpressure cho nguồn theo hợp đồng. Không để một executor RAM phình vô hạn.

### Bước 5 — Chọn error flow sau boundary

| Tình huống | Recovery phù hợp |
| --- | --- |
| Invalid payload / thiếu eventId | Quarantine ngay, không retry vô hạn |
| DB tạm hết connection | Retry/backoff có giới hạn, để pending durable |
| Payment provider read timeout | UNKNOWN_OUTCOME, query provider/idempotency |
| Worker process crash | Reclaim durable work sau lease timeout |
| Publish outbox thành công nhưng crash trước mark sent | Có thể publish lại; downstream idempotent |
| Consumer duplicate eventId | Inbox nhận ra logical work đã có, không thực hiện lại side effect |

### Bước 6 — Định nghĩa quan sát

Tối thiểu có ingress rate, durable pending age, queue wait p95, worker duration p95, active/rejected, retry attempts, duplicate suppressed, business completion, reconciliation UNKNOWN và per-order latency. Traces/log giữ eventId/orderId/operationId, nhưng metrics không dùng các IDs này làm high-cardinality tags.

### Bước 7 — Kịch bản test bắt buộc

1. Gửi một event hợp lệ; xác nhận **inbox commit trước source ACK**.
2. Gửi hai deliveries cùng eventId; chỉ một business operation có tác dụng.
3. Kill worker khi work pending; worker mới reclaim và hoàn tất.
4. Kill sau payment side effect nhưng trước ghi CONFIRMED; reconciliation không charge thêm.
5. Giữ hai event cùng orderId cho kết thúc lệch; business version/order vẫn đúng.
6. Lấp đầy executor/worker capacity; hệ thống giữ backpressure và recovery rõ ràng.
7. Shutdown một replica; các replica khác xử lý tiếp mà không mất/nhân đôi side effect.
8. Cố tình làm ErrorMessage thiếu failedMessage; hệ thống vẫn ghi đủ source/request metadata có sẵn để điều tra.

## 24. Checklist trước khi đưa một thread boundary vào production

- Đã xác định rõ **vị trí thread boundary** và lý do cần nó, thay vì chỉ muốn send() trả nhanh?
- Đã phân biệt **producer thread, poller thread, executor worker thread** và adapter callback thread?
- Nếu source còn transaction active, đã ghi nhận thread boundary có làm **mất khả năng chia sẻ transaction** không?
- Có biết **khi nào source ACK/commit offset** so với khi downstream business effect commit?
- Nếu ACK trước worker, có **durable inbox/queue/broker handoff** được commit trước đó?
- Nếu dùng QueueChannel, store là **in-memory hay persistent**, và poller có transaction phù hợp với dequeue?
- Nếu dùng persistent queue, đã kiểm tra **groupId, region, serializer, schema, restart**?
- Không có lỗ hổng **dequeue đã commit → task chỉ còn trong executor RAM**?
- Executor có **bounded queue, max concurrency và rejection policy** rõ ràng?
- CallerRunsPolicy nếu được dùng có được xem là **backpressure behavior**, không phải transaction contract?
- Có tách pool cho workload khác SLA/failure domain để tránh noisy-neighbor?
- Có đo **dispatch latency, queue wait, handler duration và business end-to-end latency** riêng?
- Có quan sát **active workers, executor queued/rejected, pending durable, unacked và in-flight**?
- Có truyền **eventId/operationId/correlationId** ổn định qua các transformer/adapters?
- Có propagation và cleanup cho **MDC/tracing/security context** được kiểm chứng, không chuyển transaction object qua thread?
- Khi nhiều worker, có chấp nhận out-of-order hoặc dùng **partition-by-key/version guard**?
- Gateway cần reply có timeout/late-result/idempotency rõ ràng?
- Có phân biệt **handler attempt, delivery và business operation**, không đếm lẫn khi retry?
- ErrorChannel/recovery sau async handoff có thật sự được cấu hình và test, không chỉ log rồi bỏ?
- Retry có budget/backoff; external side effect UNKNOWN có reconciliation?
- Có test **DirectChannel same-thread**, **ExecutorChannel worker thread**, overload/rejection, error flow, transaction boundary?
- Có hard crash/restart test cho task pending và durable handoff trước ACK?
- Runbook shutdown có quiesce ingress, drain trong budget và phục hồi durable pending không?

## Kết luận

**Đặt thread boundary có chủ đích** là một quyết định **kiến trúc xử lý message**, không chỉ là tinh chỉnh hiệu năng. Trong Spring Integration Runtime, **DirectChannel** duy trì call stack đồng bộ; **ExecutorChannel** tách dispatch qua TaskExecutor; **QueueChannel** đưa message vào một hàng đợi để poller lấy ra; **PublishSubscribeChannel** có thể tạo các nhánh song song khi được cấu hình executor.

Mỗi ranh giới làm thay đổi **transaction continuity, error propagation, reply semantics, ordering, context propagation, backpressure và shutdown recovery**. Một message được enqueue thành công vào **RAM** chưa chắc đã được xử lý, ghi bền vững hay có thể replay; một handler chạy trên worker không thể tự rollback transaction đã commit trên sender.

Thiết kế vững chắc nên trả lời được sáu câu hỏi: **Ai sở hữu message? Handoff đã durable chưa? Ai ACK nguồn? Lỗi được xử lý ở đâu? Khi quá tải thì quyết định gì? Khi process chết thì ai sẽ tiếp tục?** Khi những câu hỏi đó có câu trả lời rõ và được kiểm thử bằng concurrency, fault injection và restart, thread boundary mới thực sự giúp scale mà không làm suy yếu tính đúng đắn của flow.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Orderly Shutdown](https://docs.spring.io/spring-integration/reference/shutdown.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Micrometer Reference — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
