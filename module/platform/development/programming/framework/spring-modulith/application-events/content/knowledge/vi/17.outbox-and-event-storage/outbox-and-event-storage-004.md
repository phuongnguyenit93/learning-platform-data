# Đọc event từ outbox

Outbox là nơi ứng dụng lưu bền vững các sự kiện cần chuyển tiếp sau khi một giao dịch nghiệp vụ hoàn tất. Thành phần đọc outbox lấy những bản ghi đang chờ, chuyển chúng đến đích nhận, rồi cập nhật trạng thái để hệ thống biết sự kiện nào đã được xử lý. Cách làm này giúp ứng dụng không mất sự kiện khi tiến trình dừng giữa lúc ghi dữ liệu nghiệp vụ và lúc gửi thông điệp.

Trong Spring Modulith cần phân biệt **outbox do ứng dụng tự xây dựng** với **Event Publication Registry**. Outbox thường phục vụ việc chuyển sự kiện qua ranh giới tiến trình, chẳng hạn từ cơ sở dữ liệu sang message broker. Event Publication Registry theo dõi việc giao một application event đến từng transactional event listener trong ứng dụng. Registry cung cấp khả năng lưu lại publication chưa hoàn tất và gửi lại khi cần; nó có thể đáp ứng nhu cầu giao sự kiện bền vững giữa các module mà không cần tự truy vấn bảng lưu trữ nội bộ. Hai cơ chế có ý tưởng gần nhau nhưng khác mục tiêu và giao kèo vận hành.

## 1. Outbox lưu điều gì?

Khi một use case thay đổi trạng thái nghiệp vụ và phát sinh sự kiện, ứng dụng ghi cả hai thay đổi trong cùng một transaction:

1. Lưu trạng thái nghiệp vụ, ví dụ đơn hàng chuyển sang `CONFIRMED`.
2. Thêm một bản ghi outbox mô tả sự kiện `OrderConfirmed`.
3. Commit transaction.

Nếu transaction rollback, cả thay đổi nghiệp vụ lẫn bản ghi outbox đều không tồn tại. Nếu commit thành công nhưng ứng dụng dừng trước khi gửi sự kiện, bản ghi outbox vẫn còn để relay đọc lại sau khi khởi động.

Một bản ghi outbox thường có các thông tin sau. Tên cột và kiểu dữ liệu cụ thể phụ thuộc cơ sở dữ liệu và thiết kế của ứng dụng.

| Trường | Ý nghĩa |
| --- | --- |
| `event_id` | Định danh duy nhất, ổn định của sự kiện; dùng để phát hiện bản tin trùng. |
| `aggregate_type`, `aggregate_id` | Loại và định danh đối tượng nghiệp vụ tạo ra sự kiện. |
| `event_type` | Tên loại sự kiện theo hợp đồng đã công bố. |
| `payload` | Nội dung sự kiện ở định dạng trao đổi như JSON. |
| `schema_version` | Phiên bản cấu trúc payload để hỗ trợ thay đổi hợp đồng. |
| `occurred_at` | Thời điểm sự kiện xảy ra trong nghiệp vụ. |
| `status` | Trạng thái chuyển tiếp, ví dụ `PENDING`, `PROCESSING`, `PUBLISHED` hoặc `FAILED`. |
| `attempts`, `next_attempt_at` | Số lần thử và thời điểm sớm nhất được phép thử lại. |
| `published_at`, `last_error` | Thời điểm gửi thành công và thông tin lỗi gần nhất nếu có. |

`event_id` nên được tạo một lần và giữ nguyên qua mọi lần retry. Payload nên mô tả sự kiện đã xảy ra, chẳng hạn `OrderConfirmed`, thay vì chỉ mô tả một lệnh như `ConfirmOrder`. Không nên lưu đối tượng Java bằng cơ chế tuần tự hóa phụ thuộc lớp hoặc phiên bản runtime; một định dạng có hợp đồng rõ ràng giúp consumer đọc được dữ liệu sau khi ứng dụng nâng cấp. Chỉ đưa vào payload những dữ liệu consumer thực sự cần và áp dụng quy tắc bảo vệ dữ liệu nhạy cảm.

## 2. Luồng đọc và chuyển tiếp

Một relay đọc outbox thường thực hiện bốn bước:

1. **Claim bản ghi:** chọn một nhóm sự kiện đến hạn và đánh dấu chúng thuộc quyền xử lý của worker hiện tại.
2. **Chuyển tiếp:** gửi payload đến broker hoặc adapter đích bằng `event_id` làm message key hoặc idempotency key khi giao thức hỗ trợ.
3. **Xác nhận:** chỉ đánh dấu `PUBLISHED` sau khi đích nhận xác nhận gửi thành công.
4. **Lên lịch thử lại:** nếu gặp lỗi tạm thời, lưu số lần thử và thời điểm retry tiếp theo; nếu lỗi không thể khắc phục tự động, chuyển sang trạng thái cần can thiệp.

Việc claim phải tránh để nhiều worker xử lý cùng một bản ghi đồng thời. Với cơ sở dữ liệu hỗ trợ khóa hàng, có thể dùng `SELECT ... FOR UPDATE SKIP LOCKED` trong một transaction ngắn. Một cách triển khai khác là cập nhật trạng thái có điều kiện và kiểm tra số hàng được cập nhật. Cú pháp chính xác tùy hệ quản trị cơ sở dữ liệu.

Ví dụ SQL dưới đây minh họa ý tưởng claim theo lô; cần điều chỉnh cú pháp và chiến lược khóa theo cơ sở dữ liệu thực tế:

```sql
BEGIN;

SELECT event_id
FROM outbox_event
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at, event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Cập nhật các event_id vừa chọn thành PROCESSING,
-- đồng thời ghi worker_id và thời hạn lease.

COMMIT;
```

Worker nên giữ transaction claim ngắn và thực hiện lời gọi mạng sau khi transaction đã commit. Nếu giữ khóa cơ sở dữ liệu trong suốt thời gian chờ broker, một broker chậm có thể làm tăng thời gian khóa, gây nghẽn các giao dịch ghi và giảm khả năng xử lý song song.

Trạng thái `PROCESSING` cần có lease hoặc thời hạn sở hữu. Nếu worker bị dừng đột ngột, một tiến trình phục hồi có thể đưa bản ghi có lease hết hạn trở lại hàng đợi. Nếu không có cơ chế này, bản ghi bị claim có thể mắc kẹt vô thời hạn.

## 3. Ghi sự kiện cùng transaction nghiệp vụ

Ví dụ sau mô tả một use case ghi đơn hàng và sự kiện outbox trong cùng transaction. `OutboxRepository` là thành phần do ứng dụng định nghĩa; chi tiết lưu trữ không phụ thuộc vào API của Spring Modulith.

```java
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
```

```java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public ConfirmOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();
        orders.save(order);

        OrderConfirmed event = new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                Instant.now()
        );

        outbox.append(OutboxRecord.pending(
                event.eventId(),
                "OrderConfirmed",
                1,
                event.orderId(),
                event
        ));
    }
}
```

Ví dụ giả định `orders` và `outbox` cùng tham gia một transaction manager và cùng một transaction cơ sở dữ liệu. Nếu ghi hai nơi không có chung ranh giới transaction, bảo đảm nguyên tử của outbox không còn đúng; khi đó cần một thiết kế phối hợp khác.

Relay có thể được gọi định kỳ bằng scheduler hoặc chạy liên tục theo cơ chế polling. Nên tách phần lấy bản ghi khỏi phần chuyển tiếp để dễ thay adapter đích và kiểm thử:

```java
public interface OutboxDispatcher {
    void dispatch(OutboxRecord record);
}
```

```java
@Component
public class OutboxRelay {

    private final OutboxRepository outbox;
    private final OutboxDispatcher dispatcher;

    public OutboxRelay(
            OutboxRepository outbox,
            OutboxDispatcher dispatcher) {
        this.outbox = outbox;
        this.dispatcher = dispatcher;
    }

    public void publishBatch() {
        List<OutboxRecord> batch = outbox.claimBatch(100);

        for (OutboxRecord record : batch) {
            try {
                dispatcher.dispatch(record);
                outbox.markPublished(record.eventId(), Instant.now());
            } catch (TransientDispatchException exception) {
                outbox.scheduleRetry(
                        record.eventId(),
                        exception.getMessage(),
                        Instant.now()
                );
            }
        }
    }
}
```

Đây là khung minh họa: `claimBatch`, `markPublished` và `scheduleRetry` phải được triển khai với transaction, lease, bộ đếm retry và chính sách lỗi phù hợp. Trong hệ thống thực, không nên bắt mọi exception rồi retry vô hạn. Lỗi tạm thời như timeout có thể thử lại; lỗi hợp đồng như payload không hợp lệ cần được đưa vào luồng xử lý lỗi có chủ đích.

## 4. Đọc publication trong Spring Modulith

Với application event được giao đến các module trong cùng ứng dụng, Spring Modulith cung cấp Event Publication Registry. Registry theo dõi publication theo từng listener đủ điều kiện, lưu trạng thái publication và ghi nhận khi listener hoàn tất. Nhờ vậy, nếu listener lỗi hoặc tiến trình dừng trước khi publication được đánh dấu hoàn tất, publication chưa hoàn tất có thể được phát hiện và gửi lại theo cấu hình, phiên bản và chính sách vận hành của ứng dụng.

Một listener trong module có thể khai báo bằng `@ApplicationModuleListener`:

```java
@Component
public class InventoryEventListener {

    private final InventoryService inventory;

    public InventoryEventListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        inventory.reserveFor(event.orderId());
    }
}
```

`@ApplicationModuleListener` là lựa chọn phù hợp cho listener theo mô hình Spring Modulith; annotation này thiết lập cách xử lý bất đồng bộ và transaction cho listener theo cơ chế của framework. Cần bảo đảm listener có thể được chạy lại an toàn vì lỗi sau khi thực hiện một phần công việc có thể khiến publication được gửi lại.

Khi cần kiểm tra publication chưa hoàn tất, có thể dùng API `EventPublicationRegistry` thay vì phụ thuộc trực tiếp vào cấu trúc bảng của adapter lưu trữ:

```java
@Component
public class PublicationInspector {

    private final EventPublicationRegistry registry;

    public PublicationInspector(EventPublicationRegistry registry) {
        this.registry = registry;
    }

    public Collection<EventPublication> findIncomplete() {
        return registry.findIncompletePublications();
    }
}
```

Đoạn mã trên minh họa cách lấy danh sách publication chưa hoàn tất. Cách đọc chi tiết thuộc tính, lọc, resubmit và cấu hình lưu trữ cần theo API của phiên bản Spring Modulith mà ứng dụng đang sử dụng. Không nên cập nhật trực tiếp bản ghi registry bằng SQL để ép hoàn tất hoặc xóa lỗi; thao tác đó có thể làm mất khả năng khôi phục và bỏ qua quy tắc của framework.

Registry và outbox tùy biến giải quyết hai phạm vi khác nhau:

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Giao application event đến transactional listener giữa các module trong cùng ứng dụng | Dùng Spring Modulith Event Publication Registry và listener theo convention của framework. |
| Chuyển sự kiện từ database sang broker hoặc hệ thống bên ngoài | Dùng outbox và relay, hoặc một tích hợp chuyên biệt có cùng bảo đảm nguyên tử. |
| Kiểm tra publication nội bộ còn dang dở | Dùng API registry và công cụ quan sát được cấu hình cho ứng dụng. |
| Đọc, claim, phân phối và quản lý vòng đời message theo hợp đồng riêng | Dùng repository/relay outbox do ứng dụng sở hữu. |

Nếu cần cả hai luồng, hãy xác định rõ ranh giới: application event nào được giao nội bộ, sự kiện nào được ghi thành message tích hợp để gửi ra ngoài, và thành phần nào chịu trách nhiệm retry ở mỗi chặng. Tránh để cả listener và relay cùng gửi một sự kiện ra cùng đích mà không có quy tắc chống trùng.

## 5. Truy vấn để vận hành và chẩn đoán

Với outbox tùy biến, một truy vấn chỉ đọc có thể giúp kiểm tra hàng đợi:

```sql
SELECT event_id,
       event_type,
       aggregate_id,
       status,
       attempts,
       next_attempt_at,
       created_at,
       published_at,
       last_error
FROM outbox_event
WHERE status IN ('PENDING', 'PROCESSING', 'FAILED')
ORDER BY created_at, event_id;
```

Truy vấn này là ví dụ cho schema outbox tự thiết kế, không phải cam kết về tên bảng hoặc cột của Event Publication Registry. Khi sử dụng adapter của Spring Modulith, hãy xem tài liệu của đúng adapter và phiên bản để biết cách quan sát dữ liệu. Không dùng câu lệnh cập nhật/xóa trực tiếp để thay thế API quản lý publication.

Các chỉ số vận hành hữu ích gồm:

- Số lượng event `PENDING`, `PROCESSING` và `FAILED`.
- Tuổi của event chờ lâu nhất, vì số lượng nhỏ vẫn có thể che giấu một event bị kẹt.
- Tốc độ đọc, tốc độ publish thành công và độ trễ từ `occurred_at` đến `published_at`.
- Số lần retry, tỷ lệ lỗi theo event type và số event chuyển sang dead-letter.
- Số lease hết hạn hoặc số lần worker phải claim lại bản ghi.

Log nên có `event_id`, `aggregate_id`, `event_type`, worker, lần thử và correlation/trace id. Không ghi toàn bộ payload nếu payload chứa dữ liệu nhạy cảm hoặc có dung lượng lớn.

## 6. Bảo đảm xử lý đúng khi có lỗi

Outbox thường cung cấp giao nhận **ít nhất một lần**. Một tình huống phổ biến là relay gửi message thành công, nhưng tiến trình dừng trước khi cập nhật `PUBLISHED`. Khi chạy lại, relay gửi cùng message thêm lần nữa. Không thể giả định chỉ có một lần gửi nếu việc gửi đến broker và cập nhật database không nằm trong cùng một giao dịch nguyên tử.

Consumer vì vậy cần idempotent. Một cách làm là lưu `event_id` đã xử lý trong bảng inbox có ràng buộc unique, đồng thời thực hiện thay đổi nghiệp vụ và ghi nhận inbox trong cùng transaction:

```java
@Transactional
public void handle(OrderConfirmed event) {
    if (inboxRepository.existsByEventId(event.eventId())) {
        return;
    }

    inventory.reserveFor(event.orderId());
    inboxRepository.record(event.eventId());
}
```

Trong triển khai thực tế, cần bảo đảm việc kiểm tra và ghi inbox không tạo race condition giữa hai consumer đồng thời; ràng buộc unique ở database là lớp bảo vệ quan trọng. Nếu xử lý nghiệp vụ thất bại, transaction phải rollback cả thay đổi nghiệp vụ lẫn bản ghi inbox để lần giao lại có thể thử lại.

Các nguyên tắc vận hành khác:

- **Retry có giới hạn:** dùng exponential backoff và jitter để tránh nhiều worker retry cùng lúc. Phân loại lỗi tạm thời và lỗi không thể tự khắc phục.
- **Dead-letter và redrive:** lưu thông tin lỗi đủ để điều tra; cho phép sửa nguyên nhân rồi gửi lại có kiểm soát. Không âm thầm bỏ event lỗi.
- **Thứ tự:** nếu thứ tự theo aggregate quan trọng, lưu sequence/version trên aggregate và chỉ cho phép xử lý đúng thứ tự trong từng aggregate. `ORDER BY created_at` kết hợp nhiều worker không tự bảo đảm thứ tự hoàn tất.
- **Lease:** đặt thời hạn xử lý và cơ chế thu hồi lease hết hạn để worker chết không giữ event mãi mãi.
- **Batch:** chọn kích thước lô phù hợp với giới hạn broker, dung lượng payload và thời gian xử lý; lô quá lớn làm tăng thời gian giữ tài nguyên và khó phục hồi.
- **Retention:** xác định thời gian giữ event đã publish, cách dọn dữ liệu và yêu cầu lưu vết. Không xóa bản ghi đang chờ hoặc đang được điều tra.
- **Hợp đồng payload:** có `schema_version`, quy tắc tương thích ngược và chiến lược xử lý event type không còn được hỗ trợ.

## 7. Kiểm thử luồng đọc outbox

Các kiểm thử nên tập trung vào ranh giới transaction và tình huống lỗi có thể làm mất hoặc gửi lặp sự kiện:

1. Khi use case commit, trạng thái nghiệp vụ và outbox record cùng tồn tại.
2. Khi use case rollback, không có outbox record cho thay đổi chưa commit.
3. Hai worker đọc đồng thời không claim cùng một record trong cùng lease.
4. Khi đích nhận xác nhận thành công, record chuyển sang `PUBLISHED`.
5. Khi đích timeout hoặc worker dừng sau khi gửi, record có thể được retry và consumer không tạo tác dụng phụ trùng.
6. Khi lease hết hạn, record có thể được worker khác tiếp nhận.
7. Khi payload sai schema hoặc lỗi không thể retry, record đi vào trạng thái xử lý lỗi có thể quan sát.
8. Với Spring Modulith, kiểm tra listener hoàn tất được registry ghi nhận và publication chưa hoàn tất có thể được khôi phục theo cấu hình ứng dụng.

Kiểm thử tích hợp với cơ sở dữ liệu thật hoặc Testcontainers hữu ích cho phần khóa hàng, transaction và truy vấn claim vì các hành vi này có thể khác giữa database. Kiểm thử đơn vị vẫn phù hợp để xác minh chính sách retry, phân loại lỗi và ánh xạ payload.

## 8. Checklist khi triển khai

- [ ] Ghi business state và outbox record trong cùng transaction.
- [ ] Mỗi event có ID ổn định, event type rõ ràng và phiên bản payload.
- [ ] Claim có khóa hoặc cập nhật có điều kiện để tránh worker tranh chấp.
- [ ] Transaction claim ngắn; gửi ra ngoài sau khi commit claim.
- [ ] Có lease để thu hồi record bị bỏ dở.
- [ ] Chỉ xác nhận publish sau khi đích nhận phản hồi thành công.
- [ ] Consumer xử lý idempotent bằng event ID và ràng buộc lưu trữ phù hợp.
- [ ] Có retry, dead-letter, redrive và log phục vụ điều tra.
- [ ] Có chỉ số về backlog, tuổi event, độ trễ và lỗi.
- [ ] Đã xác định rõ phần việc của outbox tùy biến và Event Publication Registry của Spring Modulith.

Đọc event từ outbox là một quy trình có trạng thái: chọn đúng bản ghi, claim an toàn, chuyển tiếp, xác nhận và phục hồi khi lỗi. Khi kết hợp ranh giới transaction rõ ràng, consumer idempotent và quan sát backlog, ứng dụng có thể giao sự kiện đáng tin cậy hơn mà vẫn giữ các module phụ thuộc vào hợp đồng sự kiện thay vì phụ thuộc trực tiếp vào chi tiết triển khai của nhau.
