# Mô tả timing

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, một application event có thể được phát trong transaction, được giao cho một hoặc nhiều listener, xử lý đồng bộ hoặc bất đồng bộ, rồi tiếp tục tạo ra event khác hoặc message gửi ra broker. Khi viết tài liệu cho event, chỉ mô tả tên và payload là chưa đủ. Người đọc cần biết **khi nào event được phát, listener bắt đầu lúc nào, kết quả được xem là hoàn tất ở mốc nào và những độ trễ nào có thể xảy ra**.

Mô tả timing là hợp đồng vận hành của event. Nó giúp producer biết thời điểm được phép công bố sự thật nghiệp vụ, consumer hiểu khi nào có thể quan sát dữ liệu, tester chọn đúng điểm đồng bộ và operator phân biệt xử lý chậm với lỗi. Tài liệu cần nêu rõ điều gì được bảo đảm bởi transaction/framework và điều gì chỉ là hành vi thường thấy dưới tải bình thường.

## 1. Vì sao cần mô tả timing?

Hai event có cùng payload vẫn có thể mang semantics thời gian khác nhau.

Ví dụ, `OrderConfirmed` có thể được publish ngay khi domain method chuyển trạng thái, trong khi transaction vẫn chưa commit. Một listener đồng bộ có thể chạy ngay trong thread gọi publisher. Một listener khác dùng `@TransactionalEventListener` chỉ chạy sau commit. Một listener bất đồng bộ có thể được đưa vào executor và bắt đầu muộn hơn nữa.

Nếu tài liệu chỉ ghi “khi đơn hàng được xác nhận, event được phát”, consumer có thể hiểu nhầm rằng:

- Dữ liệu đơn hàng đã commit và có thể đọc từ mọi query path.
- Tất cả listener đã hoàn tất trước khi API trả về.
- Event luôn được xử lý theo đúng thứ tự phát.
- Một lần publish đồng nghĩa với message đã được broker lưu bền vững.
- Timeout ở caller có nghĩa listener đã bị hủy.

Những giả định này không tự động đúng. Timing contract phải mô tả ranh giới transaction, chế độ listener, điều kiện bắt đầu, mốc hoàn tất và giới hạn về thứ tự/độ trễ.

## 2. Phân biệt các mốc thời gian

Một luồng event có nhiều mốc khác nhau. Dùng tên nhất quán giúp tránh việc các nhóm gọi chung tất cả là “event time”.

| Mốc | Ý nghĩa |
|---|---|
| `occurredAt` | Thời điểm sự thật nghiệp vụ xảy ra theo domain |
| `publishedAt` | Thời điểm producer gửi event vào application event mechanism |
| `transactionCommittedAt` | Thời điểm transaction sở hữu thay đổi nghiệp vụ commit |
| `listenerStartedAt` | Thời điểm một listener bắt đầu xử lý |
| `listenerCompletedAt` | Thời điểm listener hoàn tất phần việc của nó |
| `externalizedAt` | Thời điểm event được adapter đưa sang cơ chế externalization |
| `brokerAcceptedAt` | Thời điểm broker xác nhận nhận message, nếu transport cung cấp mốc này |
| `consumerReceivedAt` | Thời điểm consumer bên ngoài nhận message |
| `effectCommittedAt` | Thời điểm tác dụng phụ của consumer commit vào nguồn dữ liệu sở hữu |

Không phải mọi hệ thống đều lưu tất cả các timestamp này. Tài liệu chỉ nên cam kết những mốc có thể quan sát hoặc bảo đảm. Với listener nội bộ, `brokerAcceptedAt` không áp dụng. Với publisher dùng broker adapter, `publishedAt` cũng không chứng minh broker đã nhận message.

Một event có thể xảy ra tại thời điểm T1, được publish tại T2, transaction commit tại T3, listener bắt đầu tại T4 và hoàn tất tại T5. Tùy thiết kế, T2 có thể trước T3 nhưng listener chỉ được phép chạy sau T3; hoặc listener đồng bộ có thể chạy ngay trong lời gọi publish trước khi transaction commit. Cần mô tả đúng cấu hình thực tế.

## 3. Timing của publish không đồng nghĩa timing của xử lý

Lời gọi `ApplicationEventPublisher.publishEvent(...)` chuyển event đến application event multicaster. Với cấu hình mặc định thông thường của Spring, listener được gọi đồng bộ trong thread phát event. Nếu multicaster được cấu hình task executor hoặc listener được đánh dấu bất đồng bộ, việc xử lý có thể diễn ra trên thread khác.

Điều quan trọng:

- Publish event là hành động công bố event cho cơ chế trong ứng dụng.
- Listener bắt đầu xử lý là một mốc riêng.
- Listener hoàn tất là một mốc khác.
- Hoàn tất listener không đồng nghĩa tất cả consumer hoặc hệ thống downstream đã hoàn tất.

Ví dụ, nếu `OrderConfirmed` có ba listener, publisher có thể chỉ cần phát event; các listener có thể hoàn tất ở những thời điểm khác nhau. Tài liệu nên mô tả timing theo từng listener khi chúng có yêu cầu khác nhau.

Không viết “publish xong là mọi module đã cập nhật”. Hãy ghi cụ thể listener nào chạy đồng bộ, listener nào chạy sau commit, listener nào bất đồng bộ và điều kiện để kết quả có thể đọc được.

## 4. Listener đồng bộ

Với listener đồng bộ, listener được gọi trong luồng thực thi của publisher theo cơ chế multicaster mặc định. Lời gọi publish có thể chưa trả về cho đến khi listener hoàn tất.

Ví dụ:

~~~java
@Component
class OrderAuditListener {

    @EventListener
    void on(OrderConfirmed event) {
        auditLog.record(event.orderId(), event.occurredAt());
    }
}
~~~

Trong cấu hình mặc định, listener này chạy đồng bộ với lời gọi publish. Điều đó có nghĩa thời gian xử lý listener có thể cộng vào latency của command/request phát event.

Tuy nhiên, timing thực tế còn phụ thuộc multicaster, transaction và các cấu hình async. Nếu ứng dụng cấu hình executor chung cho application event multicaster, listener có thể không còn chạy trên thread gọi publisher. Tài liệu cần nêu cấu hình đang dùng thay vì suy luận chỉ từ annotation.

Khi listener đồng bộ ném exception, exception có thể lan về caller và ảnh hưởng luồng publish/transaction theo cấu hình. Đây là một khác biệt quan trọng so với listener chạy bất đồng bộ hoặc listener sau commit.

## 5. Listener sau commit với @TransactionalEventListener

`@TransactionalEventListener` gắn listener với một phase của transaction. Phase mặc định là `AFTER_COMMIT`, nghĩa là listener chỉ được gọi sau khi transaction liên quan commit thành công.

Các phase thường gặp:

| Phase | Thời điểm |
|---|---|
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi commit thành công |
| `AFTER_ROLLBACK` | Sau khi transaction rollback |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback |

Ví dụ:

~~~java
@Component
class OrderProjectionListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        // Update a projection after the order transaction commits.
    }
}
~~~

Nếu không có transaction đang hoạt động, transactional listener thường không được gọi. Thuộc tính `fallbackExecution = true` có thể cho phép listener chạy trong trường hợp đó, nhưng thay đổi semantics và cần được dùng có chủ đích.

Với `AFTER_COMMIT`, transaction nghiệp vụ đã commit trước khi listener chạy. Nếu listener thất bại, không thể rollback transaction gốc. Tác dụng phụ của listener cần transaction riêng và cơ chế phục hồi phù hợp.

Một điểm dễ nhầm: tài nguyên transaction có thể vẫn được gắn trong quá trình callback sau commit, nhưng thay đổi ghi thêm vào cùng transaction đã commit sẽ không được commit lần nữa. Nếu listener cần ghi database, hãy dùng transaction mới phù hợp, chẳng hạn propagation `REQUIRES_NEW`, hoặc một cơ chế persistence riêng.

## 6. @ApplicationModuleListener trong Spring Modulith

Spring Modulith cung cấp `@ApplicationModuleListener` để diễn đạt listener module thường cần xử lý bất đồng bộ sau commit. Annotation này được thiết kế như một composed annotation kết hợp semantics async, transactional event listener sau commit và transaction riêng cho phần xử lý listener.

Ví dụ:

~~~java
@Component
class InventoryListener {

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // Reserve inventory in the Inventory module.
    }
}
~~~

Cách dùng này giúp thể hiện ý định rõ: module phản ứng với event sau khi transaction phát event commit, và xử lý listener có transaction riêng. Chi tiết annotation composition và cấu hình executor cần được xác nhận theo phiên bản Spring Modulith đang sử dụng.

Không nên diễn giải `@ApplicationModuleListener` là “listener chắc chắn chạy ngay sau commit”. Async chỉ có nghĩa công việc được giao cho executor; thời điểm thread thực sự bắt đầu còn phụ thuộc tải, queue, thread pool và scheduling. Listener có thể bắt đầu muộn hơn đáng kể khi executor quá tải.

Khi tài liệu event có listener dùng annotation này, hãy ghi “được lên lịch sau commit” và mô tả SLO/độ trễ quan sát được nếu có. Tránh hứa một khoảng thời gian cố định nếu không có bảo đảm vận hành tương ứng.

## 7. Listener bất đồng bộ và executor queue

Khi listener chạy bất đồng bộ, việc publish event và việc thực thi listener tách thành hai hoạt động. Sau khi event được gửi đến executor, publisher có thể tiếp tục công việc của mình trong khi listener còn đang chờ thread.

Thời gian listener bắt đầu phụ thuộc vào:

- Số thread đang hoạt động.
- Số task đang chờ trong executor queue.
- Thời gian xử lý của các listener khác dùng chung executor.
- Thread pool size và queue capacity.
- Chính sách rejection khi executor đầy.
- CPU, GC và tài nguyên downstream.
- Cách ứng dụng shutdown hoặc restart.

Tài liệu cần nói rõ listener dùng executor nào, có chia sẻ với các tác vụ khác không, concurrency dự kiến và cách xử lý khi queue đầy nếu những yếu tố đó ảnh hưởng tới hợp đồng.

Không dùng từ “immediate” cho listener async nếu chưa có cam kết về scheduling. “Được lên lịch sau commit” mô tả chính xác hơn mốc bắt đầu.

## 8. Timing của Event Publication Registry

Event Publication Registry theo dõi publication đến từng listener trong ứng dụng. Registry có thể ghi nhận publication khi event được publish và đánh dấu publication hoàn tất khi listener tương ứng xử lý thành công theo semantics của implementation.

Các mốc cần phân biệt:

1. Event được phát.
2. Publication được ghi nhận cho listener.
3. Listener được gọi hoặc task được lên lịch.
4. Listener hoàn tất.
5. Registry ghi nhận publication hoàn tất.

Publication record chưa hoàn tất có thể phản ánh listener chưa chạy, đang chạy, đã lỗi hoặc ứng dụng dừng trước khi trạng thái hoàn tất được lưu. Trạng thái cụ thể và khả năng resubmit phụ thuộc implementation và phiên bản.

Registry không phải đồng hồ đo toàn bộ quy trình nghiệp vụ. Publication của Inventory hoàn tất không có nghĩa Notification và Analytics đã hoàn tất. Registry cũng không mặc nhiên theo dõi mọi consumer ngoài broker hoặc projection downstream.

Khi viết timing contract, chỉ dùng Registry để cam kết những mốc mà API/implementation đang dùng thực sự cung cấp. Nếu cần đo listener start/completion latency, có thể bổ sung instrumentation tại listener.

## 9. Timing của externalization và broker

Nếu event được externalize, có thêm các chặng sau listener nội bộ hoặc adapter: chuyển đổi payload, serialize, gửi message, broker confirm và consumer nhận. Các chặng này có timing riêng.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant C as Command
    participant O as Orders
    participant T as Database
    participant R as Publication Registry
    participant L as Internal Listener
    participant A as Broker Adapter
    participant B as Broker
    participant X as External Consumer

    C->>O: Confirm order
    O->>T: Update order and commit
    O->>R: Record publication
    R->>L: Schedule listener after commit
    R->>A: Externalize event
    L->>L: Process event
    L->>R: Mark listener publication complete
    A->>B: Publish message
    B-->>A: Broker confirmation
    B->>X: Deliver message
~~~

Sơ đồ chỉ minh họa các mốc khái niệm. Thứ tự chính xác giữa listener nội bộ và externalization phụ thuộc adapter/cấu hình. Không giả định broker confirm xảy ra cùng transaction với database hoặc cùng thời điểm listener nội bộ hoàn tất.

Tài liệu nên chỉ rõ:
- Adapter nào externalize event.
- Message được gửi sau commit hay theo cơ chế khác.
- Có publisher confirm hay không.
- Delivery semantics và khả năng redelivery.
- Consumer acknowledgment được thực hiện ở mốc nào.
- Có retry, backoff hoặc DLQ không.

## 10. occurredAt, publishedAt và committedAt

Timestamp trong payload cần có ý nghĩa ổn định. Thông thường:

- `occurredAt` biểu đạt thời điểm nghiệp vụ xảy ra.
- `publishedAt` biểu đạt thời điểm producer phát event.
- `committedAt` biểu đạt thời điểm transaction commit nếu hệ thống có thể ghi nhận mốc đó đáng tin cậy.

Không đặt `occurredAt` bằng thời điểm listener nhận event. Listener có thể nhận muộn do async scheduling, retry hoặc broker lag. Cũng không nên tự gọi `publishedAt` là commit time nếu timestamp được tạo trước khi transaction commit.

Ví dụ event:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    long aggregateVersion
) {}
~~~

Event payload nên chứa timestamp nghiệp vụ cần cho consumer. Các mốc quan sát như listenerStartedAt hoặc listenerCompletedAt thường phù hợp hơn ở log/trace/metrics thay vì đưa vào domain event, vì chúng mô tả quá trình xử lý của một consumer cụ thể.

Nếu cần commit timestamp chính xác, hãy xác định cách lấy từ transaction/database hoặc ghi một mốc sau commit theo thiết kế. Không giả định `Instant.now()` trước khi commit chính là thời điểm commit.

## 11. Đồng hồ hệ thống và clock skew

Timestamp wall-clock giữa nhiều máy có thể lệch nhau. Nếu producer và consumer dùng đồng hồ không đồng bộ, phép trừ `consumerReceivedAt - publishedAt` có thể âm hoặc sai lệch.

Một số nguyên tắc:

- Dùng UTC và `Instant` cho timestamp được trao đổi giữa hệ thống.
- Đồng bộ đồng hồ máy bằng cơ chế hạ tầng phù hợp.
- Ghi rõ nguồn tạo timestamp.
- Dùng monotonic clock để đo duration trong cùng tiến trình khi công cụ hỗ trợ.
- Không dùng timestamp đơn lẻ làm bằng chứng thứ tự tuyệt đối giữa các service.
- Dùng aggregate sequence/version khi cần xác định thứ tự nghiệp vụ.

`System.nanoTime()` phù hợp để đo khoảng thời gian trong một JVM; không dùng giá trị này như timestamp gửi qua broker vì nó không có epoch chung giữa các máy. Với distributed tracing, dùng timestamp và span duration do tracing SDK/collector quản lý, đồng thời lưu ý clock skew.

## 12. Timing không đồng nghĩa với ordering

Event xảy ra trước có thể được xử lý sau event xảy ra muộn hơn nếu listener bất đồng bộ, retry hoặc broker partitioning làm thay đổi thứ tự quan sát.

Ví dụ, `OrderConfirmed` được phát trước `OrderShipped`, nhưng listener xử lý OrderConfirmed bị retry trong khi OrderShipped được xử lý nhanh. Consumer có thể nhìn thấy OrderShipped trước.

Nếu thứ tự nghiệp vụ quan trọng:
- Gắn aggregate version hoặc sequence vào event.
- Xác định phạm vi ordering, thường theo aggregate ID.
- Kiểm tra state transition trước khi áp dụng event.
- Lưu event đến sớm nếu cần chờ sequence trước.
- Không dùng occurredAt thay cho sequence nếu đồng hồ có thể lệch.

Tài liệu event cần ghi rõ có bảo đảm ordering hay không, bảo đảm ở phạm vi nào và consumer cần xử lý event out-of-order ra sao.

## 13. Retry ảnh hưởng timing như thế nào?

Retry làm thay đổi thời điểm listener hoàn tất. Một event có thể được nhận, xử lý một phần, thất bại, chờ backoff rồi được giao lại. Thời gian từ publish đến hoàn tất khi đó gồm cả thời gian chờ và các lần xử lý.

Mô tả retry cần có:
- Điều kiện lỗi nào được retry.
- Số lần retry hoặc giới hạn thời gian.
- Backoff và jitter.
- Thời điểm chuyển sang dead-letter/manual review.
- Cách giữ event ID và correlation ID qua retry.
- Idempotency của listener và tác dụng phụ.
- Cách operator resubmit publication hoặc message.

Không cam kết “listener xử lý trong 2 giây” nếu retry policy cho phép chờ nhiều phút. Có thể mô tả latency bình thường riêng với thời gian phục hồi khi lỗi.

## 14. Timing và transaction boundary

Tài liệu phải nói rõ event được phát bên trong transaction nào và listener quan sát trạng thái dữ liệu ở thời điểm nào.

Ví dụ với `@TransactionalEventListener(AFTER_COMMIT)`:

1. Application service bắt đầu transaction.
2. Aggregate được cập nhật.
3. Event được publish trong transaction.
4. Transaction commit.
5. Listener được kích hoạt sau commit.
6. Listener dùng transaction riêng nếu cần ghi dữ liệu.
7. Listener hoàn tất và publication được ghi nhận.

Nếu transaction rollback, listener AFTER_COMMIT không chạy theo semantics thông thường. Nếu không có transaction, transactional listener không chạy trừ khi bật fallback execution.

Không nên viết event “được phát sau commit” nếu code thực tế gọi `publishEvent` trước commit. Hãy viết chính xác: “Event được publish trong transaction; listener AFTER_COMMIT chỉ được gọi sau khi transaction commit thành công.”

## 15. Timing trong API và trải nghiệm người dùng

API trả về sau khi command commit không nhất thiết phải chờ mọi listener hoàn tất. Nếu downstream được xử lý bất đồng bộ, response nên thể hiện trạng thái đã commit và các công việc tiếp theo còn đang chạy.

Ví dụ:
- `OrderConfirmed` đã commit: API có thể trả trạng thái CONFIRMED.
- Search projection chưa cập nhật: màn hình tìm kiếm có thể tạm thời chưa thấy đơn.
- Notification chưa gửi: thông báo sẽ được gửi sau.
- Inventory chưa xác nhận: nếu giữ hàng là điều kiện quyết định thành công, quy trình cần trạng thái pending hoặc workflow có phản hồi riêng.

Tài liệu cần phân biệt:
- Command được chấp nhận.
- Thay đổi domain đã commit.
- Listener đã hoàn tất.
- Downstream projection đã đồng bộ.
- Quy trình nhiều bước đã hoàn tất.

Nếu API trả 202 Accepted cho một process bất đồng bộ, mô tả resource/status endpoint và cách client kiểm tra tiến trình. Không gọi một request là “hoàn tất” nếu nó chỉ mới được xếp vào queue.

## 16. Viết timing contract cho từng event

Một tài liệu event hữu ích có thể dùng cấu trúc thống nhất:

| Mục | Nội dung cần ghi |
|---|---|
| Trigger | Hành động hoặc domain transition tạo event |
| Publish point | Code/transaction boundary nơi event được publish |
| Transaction phase | Trong transaction, BEFORE_COMMIT, AFTER_COMMIT hay ngoài transaction |
| Listener mode | Đồng bộ, async executor hay broker consumer |
| Start condition | Điều kiện để listener bắt đầu |
| Completion condition | Khi nào listener được xem là hoàn tất |
| Ordering | Có sequence/order guarantee ở phạm vi nào |
| Retry | Số lần, backoff và dead-letter behavior |
| Expected latency | SLO hoặc phân vị quan sát được, nếu có |
| Failure behavior | Điều gì xảy ra nếu listener lỗi hoặc process restart |
| Read visibility | Khi nào dữ liệu mới có thể đọc từ query path |
| Correlation | Event ID, correlation ID và business key |

Không điền một giá trị giả định vào mọi event. Nếu chưa có SLO, ghi “không có hard real-time guarantee; thời gian xử lý phụ thuộc executor và tải” thay vì tự tạo con số.

## 17. Ví dụ tài liệu timing cho OrderConfirmed

Một mô tả mẫu:

**Trigger:** Orders chuyển aggregate từ PAID sang CONFIRMED sau khi domain invariant được thỏa mãn.

**Publish point:** Application service gọi `ApplicationEventPublisher.publishEvent` bên trong transaction cập nhật Order.

**Transaction phase:** Event được publish trong transaction; các listener dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc `@ApplicationModuleListener` chỉ bắt đầu sau commit theo cấu hình tương ứng.

**Listener:**
- InventoryListener: async sau commit; hoàn tất khi reservation được ghi nhận hoặc xử lý thất bại theo policy.
- NotificationListener: async sau commit; hoàn tất khi yêu cầu gửi notification được chấp nhận bởi adapter.
- AnalyticsListener: async sau commit; hoàn tất khi projection được cập nhật.

**Ordering:** Không có ordering toàn cục giữa ba listener. Event mang orderId và aggregateVersion để consumer phát hiện trạng thái cũ hoặc event đến sai thứ tự.

**Retry:** Lỗi tạm thời được retry theo policy của từng listener/adapter; listener phải idempotent.

**Visibility:** Orders có trạng thái CONFIRMED sau commit. Projection Inventory, Notification và Analytics cập nhật theo thời gian riêng, không được coi là đồng bộ cùng lúc.

Mô tả này giúp consumer hiểu chính xác họ có thể dựa vào điều gì và phần nào cần chờ hoặc đối soát.

## 18. Kiểm thử timing contract

Test cần xác minh mốc thời gian và điều kiện kích hoạt, không nên dựa vào sleep cố định.

Các trường hợp nên kiểm tra:
- Listener đồng bộ được gọi trong lời gọi publish theo cấu hình mặc định.
- Listener AFTER_COMMIT chỉ chạy khi transaction commit.
- Listener AFTER_COMMIT không chạy khi transaction rollback.
- Async listener được kích hoạt sau commit và test chờ outcome bằng điều kiện có timeout.
- Event không xuất hiện khi transaction không commit.
- Publication registry ghi nhận trạng thái theo listener.
- Retry/resubmit không gây side effect kép.
- Event đến muộn hoặc sai thứ tự được xử lý theo contract.
- API response không tuyên bố downstream hoàn tất khi listener còn chạy.
- Timestamp dùng UTC và duration đo đúng phạm vi.

Với Spring Modulith Scenario API, dùng điều kiện chờ event hoặc state change cùng timeout rõ ràng. Timeout của test giới hạn thời gian quan sát; nó không hủy listener hoặc rollback transaction đã commit. Dùng ID riêng cho mỗi test và cleanup dữ liệu để event đến muộn không ảnh hưởng test khác.

## 19. Những lỗi thường gặp khi mô tả timing

**Gọi publish là hoàn tất.** Publish chỉ gửi event đến cơ chế application event; listener có thể chưa bắt đầu.

**Không ghi transaction phase.** Consumer giả định dữ liệu đã commit trong khi listener thực tế chạy trước commit.

**Gọi async là tức thời.** Executor có queue và scheduling delay.

**Dùng một latency cho mọi listener.** Mỗi listener có dependency và SLO khác nhau.

**Nhầm publication complete với business process complete.** Registry theo dõi listener publication, không phải toàn bộ saga hoặc downstream.

**Dùng timestamp làm thứ tự.** Clock skew và retry có thể làm event đến sai thứ tự.

**Không nói rõ retry.** Một listener có thể hoàn tất sau nhiều lần thử và thời gian chờ.

**Không mô tả late event.** Listener vẫn có thể chạy sau khi request hoặc test timeout.

**Hứa hard real-time không có cơ chế bảo đảm.** Một con số trung bình không phải SLA.

## 20. Checklist mô tả timing

- [ ] Trigger nghiệp vụ tạo event được mô tả rõ.
- [ ] Publish point và transaction boundary được ghi chính xác.
- [ ] Phân biệt publish, listener start và listener completion.
- [ ] Ghi rõ listener đồng bộ, AFTER_COMMIT hay async.
- [ ] Nêu executor hoặc cơ chế scheduling có ảnh hưởng đến timing.
- [ ] Xác định điều kiện hoàn tất của từng listener.
- [ ] Phân biệt listener completion với downstream/business completion.
- [ ] Ghi rõ ordering guarantee và aggregate sequence/version.
- [ ] Mô tả retry, backoff, redelivery và DLQ.
- [ ] Phân biệt occurredAt, publishedAt và processing timestamps.
- [ ] Timestamp dùng UTC; duration đo bằng monotonic clock khi phù hợp.
- [ ] Ghi SLO/latency dựa trên số liệu, không tự đặt cam kết.
- [ ] Mô tả read visibility và read-after-write.
- [ ] Có test commit/rollback, async, timeout và event đến muộn.
- [ ] Có event ID/correlation ID để truy vết.

## 21. Nguyên tắc mô tả timing

Mô tả timing cần làm rõ event được publish ở đâu trong transaction, listener bắt đầu theo cơ chế nào, khi nào listener hoàn tất và dữ liệu trở nên có thể đọc. Với Spring Modulith, phân biệt listener đồng bộ, `@TransactionalEventListener`, `@ApplicationModuleListener`, Event Publication Registry và externalization; mỗi thành phần có ranh giới thời gian riêng.

Dùng timestamp có semantics rõ, không suy luận thứ tự từ đồng hồ và không cam kết độ trễ khi chưa có SLO hoặc cơ chế bảo đảm. Khi timing contract được viết theo từng listener, kèm retry, ordering, visibility và failure behavior, producer, consumer, tester và operator có thể phối hợp chính xác trong một hệ thống event bất đồng bộ.
