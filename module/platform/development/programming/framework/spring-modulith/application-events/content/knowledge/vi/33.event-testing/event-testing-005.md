# Kiểm thử thứ tự

## Mục tiêu

Một module Spring Modulith có thể phát nhiều application event trong cùng transaction, và nhiều listener có thể xử lý các event đó bất đồng bộ. Khi hệ thống chạy đồng thời, thứ tự phát event, thứ tự listener được gọi và thứ tự listener hoàn tất có thể khác nhau. Retry, transaction rollback, resubmission và broker partition cũng ảnh hưởng tới thứ tự quan sát được.

**Kiểm thử thứ tự** xác minh các event và listener tuân thủ đúng trình tự mà nghiệp vụ yêu cầu. Bài kiểm thử cần làm rõ phần nào bắt buộc tuần tự, phần nào được phép chạy song song và cách hệ thống phát hiện event đến trễ, trùng hoặc sai thứ tự.

Sau bài học, bạn có thể:

- Phân biệt publication order, invocation order và completion order.
- Hiểu tác động của `@Order`, `@ApplicationModuleListener` và xử lý sau commit.
- Kiểm thử thứ tự event theo aggregate bằng sequence/version.
- Phát hiện việc async listener hoàn tất sai thứ tự.
- Kiểm thử retry, duplicate, resubmission và transaction rollback.
- Thiết kế test đồng thời ổn định mà không phụ thuộc `Thread.sleep()`.

## 1. Có nhiều loại thứ tự

Khi nói một event phải được xử lý “đúng thứ tự”, trước hết cần xác định đang nói tới mốc nào:

| Loại thứ tự | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Publication order | Thứ tự publisher phát event. | `OrderPlaced` được publish trước `PaymentRequested`. |
| Listener invocation order | Thứ tự framework gọi các listener. | Listener có `@Order(10)` được gọi trước listener `@Order(20)`. |
| Processing/completion order | Thứ tự listener thực sự hoàn tất công việc. | Listener A commit trước listener B. |
| Business sequence | Trình tự thay đổi trạng thái của một aggregate. | `OrderCreated` version 1, `OrderPaid` version 2, `OrderShipped` version 3. |
| Delivery order | Thứ tự message consumer nhận từ transport. | Kafka giữ thứ tự trong cùng partition. |

Các loại thứ tự này không tự động tương đương. Publisher có thể phát A rồi B, nhưng nếu hai listener chạy trên executor nhiều thread thì B có thể hoàn tất trước A. Broker có thể giữ thứ tự trong một partition nhưng consumer xử lý bất đồng bộ khiến side effect vẫn hoàn tất sai thứ tự.

Hãy viết yêu cầu theo cách kiểm chứng được, ví dụ: “Với cùng `orderId`, projection chỉ áp dụng aggregate version tăng dần; event của các order khác nhau được phép xử lý song song.” Đây là yêu cầu rõ hơn câu “event phải chạy đúng thứ tự”.

## 2. Thứ tự trong Spring application events

### Listener đồng bộ và `@Order`

Với event multicaster đồng bộ mặc định, listener được gọi trong thread publish event. `@Order` hoặc `Ordered` có thể xác định thứ tự gọi giữa các listener được đăng ký cho cùng event. Giá trị order nhỏ hơn có độ ưu tiên gọi trước.

Ví dụ:

```java
@Component
class OrderAuditListener {

    @EventListener
    @Order(10)
    void recordAudit(OrderPlaced event) {
        // Ghi nhận audit trước listener có order lớn hơn.
    }
}

@Component
class OrderMetricsListener {

    @EventListener
    @Order(20)
    void updateMetrics(OrderPlaced event) {
        // Được gọi sau listener order 10 trong dispatch đồng bộ.
    }
}
```

`@Order` điều khiển thứ tự gọi listener trong quá trình dispatch. Nó không tạo transaction chung, không bảo đảm listener trước đã commit một transaction riêng và không điều khiển thứ tự giữa các event khác nhau.

### Listener bất đồng bộ

`@ApplicationModuleListener` được thiết kế cho xử lý module listener bất đồng bộ và sau commit. Framework có thể gửi các lần xử lý tới executor. Ngay cả khi việc dispatch/submission xảy ra theo một thứ tự, các task vẫn có thể chạy đồng thời và hoàn tất theo thứ tự khác nhau.

Ví dụ publisher phát hai event:

```java
@Transactional
public void confirmOrder(UUID orderId) {
    events.publishEvent(new OrderConfirmed(orderId, 1));
    events.publishEvent(new InvoiceRequested(orderId, 2));
}
```

Nếu hai listener xử lý bất đồng bộ, không nên suy luận rằng listener `OrderConfirmed` chắc chắn hoàn tất trước listener `InvoiceRequested`. Muốn có quan hệ phụ thuộc, hãy biểu diễn quan hệ đó trong quy trình: listener hoàn tất bước trước rồi mới phát event/command tiếp theo, hoặc dùng process manager điều phối.

### Thứ tự gọi không phải thứ tự hoàn tất

Ngay cả khi framework gọi listener A trước B, A có thể bắt đầu một task async rồi trả về nhanh, trong khi B hoàn tất công việc ngay. Vì vậy, test chỉ ghi lại thứ tự method được gọi có thể không chứng minh được thứ tự side effect hoặc commit.

Khi nghiệp vụ yêu cầu “A hoàn tất rồi mới B bắt đầu”, cần kiểm thử mốc hoàn tất thực tế, ví dụ commit của transaction hoặc bản ghi kết quả, thay vì chỉ kiểm tra thứ tự invocation.

## 3. Thứ tự sau commit và transaction boundary

`@TransactionalEventListener` mặc định xử lý ở phase `AFTER_COMMIT`. `@ApplicationModuleListener` kết hợp mô hình listener module với xử lý bất đồng bộ và transaction riêng theo cấu hình/semantics của Spring Modulith. Vì vậy, listener không nên được kỳ vọng chạy trước khi transaction publisher commit.

Các trường hợp cần kiểm thử:

- Transaction publisher commit: listener được phép xử lý event.
- Transaction publisher rollback: listener ở `AFTER_COMMIT` không được xử lý event đó.
- Listener chạy sau commit: dữ liệu đã commit của publisher có thể được đọc theo transaction mới.
- Listener thất bại: publication có thể còn incomplete và được retry/resubmit theo cơ chế đã cấu hình.

Một test có `@Transactional` và rollback mặc định ở cuối method có thể không kích hoạt listener sau commit. Để kiểm tra đúng lifecycle, hãy commit transaction rõ ràng hoặc dùng một transaction boundary độc lập trong test.

Ví dụ kiểm tra listener không chạy khi transaction rollback:

```java
@Test
void doesNotHandleEventWhenPublishingTransactionRollsBack() {
    transactionTemplate.executeWithoutResult(status -> {
        orderService.publishOrderPlaced(orderId);
        status.setRollbackOnly();
    });

    verify(orderListener, never()).on(any(OrderPlaced.class));
}
```

Đây là skeleton minh họa. Nếu listener là async, cần xác minh không có invocation sau khi transaction rollback và đồng thời kiểm tra publication state theo cấu hình registry. Không dùng một assertion tức thời nếu test environment có executor chạy nền; hãy dùng probe hoặc điều kiện chờ có timeout phù hợp.

## 4. Kiểm thử thứ tự event theo aggregate

Thứ tự thường quan trọng trong phạm vi một aggregate, không nhất thiết trên toàn hệ thống. Ví dụ một đơn hàng có các thay đổi version 1, 2, 3; các đơn hàng khác nhau có thể được xử lý song song.

Đưa sequence/version vào event contract:

```java
public record OrderStatusChanged(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        String newStatus,
        Instant occurredAt) {}
```

Projection hoặc listener có thể giữ version cuối đã áp dụng. Khi nhận event:

- `incomingVersion == currentVersion + 1`: áp dụng nếu event là delta cần đủ thứ tự.
- `incomingVersion <= currentVersion`: event trùng hoặc cũ; deduplicate/ignore theo policy.
- `incomingVersion > currentVersion + 1`: phát hiện gap; chờ event thiếu, retry hoặc tải lại snapshot authoritative.

Không phải mọi event đều cần liên tục không có gap. Nếu event mang snapshot đầy đủ, version mới hơn có thể thay thế snapshot cũ. Nếu event là delta như “tăng số lượng thêm 2”, bỏ qua version ở giữa có thể làm sai kết quả.

### Ví dụ kiểm tra sequence

```java
@Test
void appliesEventsInAggregateVersionOrder() {
    handler.on(event(orderId, 1, "CREATED"));
    handler.on(event(orderId, 2, "PAID"));
    handler.on(event(orderId, 3, "SHIPPED"));

    OrderProjection result = repository.findById(orderId).orElseThrow();

    assertThat(result.version()).isEqualTo(3);
    assertThat(result.status()).isEqualTo("SHIPPED");
}
```

Test này kiểm tra chuỗi tuần tự trong một thread. Cần thêm test event đến sai thứ tự và test nhiều worker cạnh tranh để chứng minh cơ chế version/locking hoạt động khi có concurrency.

## 5. Kiểm thử thứ tự listener bằng probe

Với listener async, nên ghi lại các mốc quan sát được bằng probe thread-safe. Không dùng một `ArrayList` không đồng bộ để nhận kết quả từ nhiều thread.

Ví dụ probe:

```java
final class EventOrderProbe {

    private final Queue<String> completed = new ConcurrentLinkedQueue<>();
    private final CountDownLatch expected;

    EventOrderProbe(int expectedEvents) {
        this.expected = new CountDownLatch(expectedEvents);
    }

    void completed(String eventName) {
        completed.add(eventName);
        expected.countDown();
    }

    boolean await(Duration timeout) throws InterruptedException {
        return expected.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    List<String> result() {
        return List.copyOf(completed);
    }
}
```

Trong test:

```java
@Test
void observesCompletionOrderOfAsyncListeners() throws Exception {
    publisher.publish(eventA);
    publisher.publish(eventB);

    assertThat(probe.await(Duration.ofSeconds(5))).isTrue();
    assertThat(probe.result()).containsExactly("A", "B");
}
```

Assertion `A` trước `B` chỉ hợp lệ nếu hệ thống có cơ chế đảm bảo thứ tự hoàn tất. Nếu listener được phép chạy song song, test phải kiểm tra các invariant phù hợp thay vì ép một thứ tự ngẫu nhiên. Ví dụ, kiểm tra cả A và B đều hoàn tất, mỗi event chỉ được áp dụng một lần và trạng thái cuối có version đúng.

Probe cần được reset giữa các test hoặc tạo mới theo test context. Không dùng biến static chia sẻ giữa các test chạy song song.

## 6. Chứng minh async có thể hoàn tất sai thứ tự

Một test có thể dùng latch để cố ý giữ event A trong khi event B hoàn tất trước. Cách này giúp chứng minh hệ thống không được giả định completion order chỉ dựa trên publication order.

```java
@Component
class ConcurrentOrderListener {

    private final CountDownLatch releaseA;
    private final EventOrderProbe probe;

    ConcurrentOrderListener(CountDownLatch releaseA, EventOrderProbe probe) {
        this.releaseA = releaseA;
        this.probe = probe;
    }

    @ApplicationModuleListener
    void on(EventA event) throws InterruptedException {
        releaseA.await(5, TimeUnit.SECONDS);
        probe.completed("A");
    }

    @ApplicationModuleListener
    void on(EventB event) {
        probe.completed("B");
        releaseA.countDown();
    }
}
```

Đây là ví dụ test fixture, không phải mẫu production listener. Trong test thực tế, tạo latch/probe theo từng test và bảo đảm luôn giải phóng latch ở `finally` để không làm treo executor. Có thể dùng executor test được kiểm soát hoặc `CountDownLatch` để buộc một lịch thực thi cụ thể.

Nếu B hoàn tất trước A, điều đó không nhất thiết là lỗi framework. Nó cho thấy hai listener async độc lập không tạo thành một chuỗi tuần tự. Nếu nghiệp vụ cần A trước B, phải mô hình hóa quan hệ phụ thuộc.

## 7. Cách thiết kế khi thứ tự thực sự bắt buộc

Có một số cách phổ biến, tùy phạm vi cần tuần tự:

### Chained event

Listener xử lý bước A trong transaction của nó. Sau khi thay đổi được commit, listener phát event B mô tả kết quả của A. B chỉ được phát khi A thành công. Cách này thể hiện quan hệ phụ thuộc bằng event flow thay vì trông chờ thứ tự giữa hai listener độc lập.

```java
@Component
class InventoryListener {

    private final InventoryService inventory;
    private final ApplicationEventPublisher events;

    InventoryListener(InventoryService inventory, ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    @ApplicationModuleListener
    @Transactional
    void reserve(OrderPlaced event) {
        Reservation reservation = inventory.reserve(event.orderId());
        events.publishEvent(new InventoryReserved(
                event.orderId(), reservation.id(), event.aggregateVersion()));
    }
}
```

Ví dụ cần được điều chỉnh theo transaction boundary thực tế. Event tiếp theo nên chỉ được xem là kết quả đã phát bền vững khi publication được ghi nhận trong transaction phù hợp; với side effect ra ngoài process, cân nhắc outbox. Không phát event thành công trước khi bước A đã hoàn tất theo định nghĩa nghiệp vụ.

### Process manager/orchestration

Với quy trình nhiều bước, process manager lưu trạng thái hiện tại và chỉ gửi command tiếp theo khi nhận kết quả hợp lệ của bước trước. Nó có thể kiểm tra `sagaId`, step, version và event ID để từ chối message trùng hoặc đến sai thứ tự.

### Partition theo aggregate

Với Kafka, dùng aggregate ID làm message key để các event của cùng aggregate thường đi vào cùng partition và được broker lưu theo thứ tự trong partition. Điều này không tự bảo đảm listener hoàn tất tuần tự nếu consumer tiếp tục dispatch nhiều task async. Consumer phải giữ thứ tự xử lý hoặc dùng cơ chế serial per key.

### Serial executor theo key

Một chiến lược là tuần tự hóa công việc theo aggregate ID nhưng cho phép các aggregate khác nhau chạy song song. Ví dụ, mỗi key có một hàng đợi/worker tuần tự; cần giới hạn số key hoạt động và dọn worker rỗng để tránh rò rỉ bộ nhớ.

### Optimistic locking và version check

Database update có điều kiện theo version giúp ngăn event cũ ghi đè trạng thái mới. Nếu update không thành công vì version không khớp, handler phải phân biệt duplicate, stale event và gap; không chỉ retry mù quáng.

## 8. Retry, duplicate và Event Publication Registry

Thứ tự có thể thay đổi khi listener thất bại và được retry. Ví dụ event version 2 thất bại, version 3 đã được xử lý, sau đó version 2 được resubmit. Nếu handler không kiểm tra version, event cũ có thể ghi đè dữ liệu mới.

Spring Modulith Event Publication Registry theo dõi publication tới listener và trạng thái hoàn tất. Publication chưa hoàn tất có thể được resubmit theo cơ chế ứng dụng cấu hình. Registry giúp khôi phục việc giao event, nhưng không tự bảo đảm thứ tự nghiệp vụ giữa nhiều publication.

Khi kiểm thử retry/resubmission, cần xác minh:

- Publication của listener lỗi vẫn được nhận diện là chưa hoàn tất theo policy.
- Khi resubmit, handler không lặp side effect đã commit.
- Event cũ không ghi đè version mới hơn.
- Một publication thành công không bị hiểu nhầm là toàn bộ saga/aggregate đã hoàn tất.
- Nếu failure handler hoặc registry storage gặp lỗi, event không bị đánh dấu hoàn tất sai.

### Inbox và idempotency

Ghi `eventId` đã xử lý trong cùng transaction với thay đổi nghiệp vụ/projection. Unique constraint trên `(listenerId, eventId)` hoặc `(consumerName, messageId)` giúp ngăn duplicate khi nhiều worker cùng nhận một event.

Idempotency xử lý duplicate; version/sequence xử lý thứ tự. Hai cơ chế bổ sung nhau nhưng không thay thế nhau. Một event ID mới có thể vẫn là event cũ về business version; ngược lại, một event bị giao trùng có cùng ID nhưng không được phép tạo side effect lần thứ hai.

## 9. Kiểm thử thứ tự khi dùng Kafka hoặc broker

Khi application event được externalize, cần kiểm tra cả thứ tự broker delivery và thứ tự consumer completion.

Với Kafka:

- Các record cùng key thường được ghi vào cùng partition; thứ tự được giữ trong partition.
- Consumer group phân chia partition giữa các consumer; một partition tại một thời điểm chỉ được gán cho một consumer trong group.
- Nếu consumer xử lý record tuần tự trong partition, completion order có thể giữ theo thứ tự nhận.
- Nếu consumer dispatch record sang thread pool và không chờ completion trước khi commit offset, side effect có thể hoàn tất sai thứ tự.
- Rebalance, retry topic và dead-letter flow có thể làm event được xử lý ở thời điểm khác hoặc luồng khác.

Với RabbitMQ, thứ tự phụ thuộc queue, consumer count, prefetch, redelivery và cách consumer xử lý đồng thời. Nhiều consumer hoặc requeue có thể làm thứ tự completion khác thứ tự enqueue.

Integration test nên dùng broker/container phù hợp với transport thực tế và kiểm tra:

1. Key/routing đưa các event cùng aggregate tới đúng partition/queue.
2. Consumer nhận message theo thứ tự mong đợi.
3. Xử lý async không phá vỡ invariant version.
4. Redelivery/retry không lặp side effect.
5. Rebalance/restart không làm mất hoặc áp dụng sai event.

Không suy luận rằng broker đảm bảo end-to-end business ordering chỉ vì nó giữ thứ tự lưu message.

## 10. Viết test ổn định, tránh race condition

Các test về async/order thường dễ flaky nếu phụ thuộc thời gian máy hoặc tốc độ CI.

Nên:

- Dùng `CountDownLatch`, `CompletableFuture`, Awaitility hoặc probe có timeout để chờ điều kiện cụ thể.
- Dùng executor được kiểm soát trong test khi cần tạo một lịch thực thi xác định.
- Ghi nhận completion/commit thay vì chỉ ghi nhận method được gọi.
- Dùng ID riêng cho mỗi test và không chia sẻ static mutable state.
- Đặt timeout đủ lớn cho CI nhưng đủ ngắn để test lỗi không treo.
- Luôn giải phóng latch, đóng executor và dọn dữ liệu trong `finally`/lifecycle hook.
- Kiểm thử cả happy path, duplicate, out-of-order và retry.

Tránh:

- `Thread.sleep(1000)` rồi giả định listener đã hoàn tất.
- Assert thứ tự của các listener async độc lập khi hệ thống không cam kết thứ tự đó.
- Dùng `HashSet` hoặc collection không thread-safe để thu thập kết quả đồng thời.
- Chạy test phụ thuộc cùng database row mà không cô lập dữ liệu.
- Để test chỉ pass khi chạy riêng nhưng thất bại khi chạy song song.

### Ví dụ dùng Awaitility

```java
@Test
void eventuallyProcessesAllExpectedEvents() {
    publisher.publish(eventA);
    publisher.publish(eventB);

    await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
        assertThat(probe.completedEventIds())
                .containsExactlyInAnyOrder(eventA.eventId(), eventB.eventId());
    });
}
```

Ví dụ này phù hợp khi hai event được phép hoàn tất theo bất kỳ thứ tự nào. Nếu thứ tự là yêu cầu nghiệp vụ, thay assertion bằng kiểm tra sequence/version hoặc một invariant chứng minh bước trước đã commit trước bước sau.

## 11. Ma trận kiểm thử thứ tự

| Kịch bản | Kỳ vọng |
| --- | --- |
| Hai listener đồng bộ có `@Order` khác nhau | Invocation order theo cấu hình order. |
| Hai listener async độc lập | Không giả định completion order; cả hai phải hoàn tất đúng trách nhiệm. |
| Event phát trong transaction commit | Listener after-commit được kích hoạt. |
| Transaction publish rollback | Listener after-commit không xử lý event đã rollback. |
| Cùng aggregate version 1, 2, 3 | Projection/handler đạt version 3 và không áp dụng sai thứ tự. |
| Version 3 đến trước version 2 | Handler phát hiện gap hoặc áp dụng snapshot theo policy. |
| Event version cũ đến muộn | Không ghi đè trạng thái version mới. |
| Cùng event ID được giao hai lần | Side effect chỉ xảy ra một lần. |
| Event trước thất bại rồi retry | Event sau không làm hỏng invariant trong lúc chờ retry. |
| Publication được resubmit sau restart | Handler tiếp tục an toàn và không lặp side effect. |
| Kafka cùng key | Record cùng aggregate giữ thứ tự trong partition; consumer completion được kiểm tra riêng. |
| Nhiều aggregate chạy song song | Thứ tự trong từng aggregate được giữ; các aggregate khác nhau có thể xen kẽ. |

## 12. Những lỗi kiểm thử thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `@Order` với thứ tự hoàn tất async | Test pass nhưng side effect vẫn chạy sai thứ tự. | Đo completion/commit; tuần tự hóa khi cần. |
| Dùng `Thread.sleep()` | Test phụ thuộc tốc độ máy và dễ flaky. | Chờ condition bằng latch/future/Awaitility. |
| Chỉ test publication order | Không phát hiện listener hoàn tất sai thứ tự. | Kiểm tra side effect và aggregate version. |
| Không test rollback | Listener có thể xử lý event của transaction không commit trong test sai cấu hình. | Test transaction commit/rollback rõ ràng. |
| Không test retry và duplicate | Side effect bị lặp khi registry resubmit. | Inbox/idempotency và failure injection. |
| Ép mọi event chạy tuần tự | Giảm concurrency không cần thiết và che giấu yêu cầu thật. | Chỉ tuần tự trong phạm vi aggregate/flow cần thiết. |
| Giả định Kafka partition đảm bảo mọi completion order | Consumer async vẫn có thể hoàn tất ngược thứ tự. | Kiểm soát consumer dispatch/processing theo key. |
| Dùng timestamp thay sequence | Clock skew làm sai thứ tự. | Dùng aggregate version/sequence từ nguồn. |

## 13. Quy trình áp dụng

Khi kiểm thử thứ tự application events trong Spring Modulith:

1. Viết rõ thứ tự cần bảo đảm: publication, invocation, completion hay business sequence.
2. Xác định phạm vi tuần tự: toàn hệ thống, từng listener, từng aggregate hay từng process.
3. Phân biệt listener đồng bộ, `@Order` và listener async/after-commit.
4. Đưa event ID, aggregate ID và sequence/version vào event contract khi cần.
5. Thiết kế chained event, process manager, serial-per-key hoặc version check nếu nghiệp vụ cần thứ tự.
6. Viết probe thread-safe để quan sát invocation, completion và commit.
7. Kiểm thử commit/rollback, duplicate, retry, resubmission và event đến sai thứ tự.
8. Với broker, kiểm tra key/partition/queue cùng consumer concurrency và completion order.
9. Dùng latch/future/Awaitility thay cho sleep; cô lập dữ liệu và dọn executor sau test.
10. Theo dõi publication incomplete, event age, sequence gap và lỗi optimistic locking trong vận hành.

Kiểm thử thứ tự không nhằm ép toàn bộ event chạy tuần tự. Mục tiêu là chứng minh những quan hệ nghiệp vụ bắt buộc được giữ, đồng thời cho phép các event độc lập chạy song song. Khi tách rõ invocation và completion, dùng sequence/version và kiểm thử retry/duplicate có kiểm soát, ứng dụng Spring Modulith có thể duy trì tính đúng đắn của quy trình event mà vẫn tận dụng được xử lý bất đồng bộ.
