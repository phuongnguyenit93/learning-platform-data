# Idempotency theo consumer

Idempotency theo consumer là khả năng một consumer nhận và xử lý cùng một event nhiều lần nhưng chỉ tạo ra một kết quả nghiệp vụ có hiệu lực. Đây là yêu cầu quan trọng trong hệ thống event-driven vì giao nhận thường theo kiểu *at-least-once*: broker, listener hoặc cơ chế phục hồi có thể gửi lại message khi timeout, mất acknowledgement hay tiến trình dừng giữa chừng.

Trong Spring Modulith, application event giúp các module giao tiếp qua hợp đồng ổn định. `@ApplicationModuleListener` xử lý event bất đồng bộ sau commit; Event Publication Registry theo dõi trạng thái giao publication đến listener. Registry hỗ trợ phát hiện và phục hồi publication chưa hoàn tất, nhưng consumer vẫn phải chịu được việc được gọi lại. Idempotency bảo vệ tác động nghiệp vụ khi một publication được thực thi lặp.

## 1. Vì sao consumer phải idempotent?

Giả sử module Order phát `OrderConfirmed` và listener Inventory giữ tồn kho. Listener cập nhật database thành công, nhưng tiến trình dừng trước khi hệ thống ghi nhận publication hoàn tất. Khi publication được gửi lại, listener có thể chạy lần nữa. Nếu mỗi lần chạy đều trừ tồn kho, cùng một đơn hàng sẽ giữ hàng hai lần.

Các tình huống tạo ra lần giao lặp thường gặp:

- Listener đã commit database nhưng process dừng trước khi xác nhận hoàn tất.
- Consumer đã xử lý message nhưng acknowledgement hoặc offset commit bị timeout.
- Broker không nhận được acknowledgement và redeliver message.
- Event Publication Registry phục hồi publication chưa hoàn tất sau khi ứng dụng khởi động lại.
- Người vận hành replay message để khắc phục sự cố hoặc dựng lại dữ liệu.
- Retry ở nhiều tầng khiến cùng một event đến handler nhiều lần.

Với xử lý at-least-once, duplicate là khả năng bình thường. Không nên dựa vào giả định “mỗi event chỉ đến một lần”. Consumer cần bảo đảm lần xử lý thứ hai không lặp tác động đã commit ở lần đầu.

## 2. Idempotency nghĩa là gì?

Một thao tác `f` là idempotent nếu áp dụng cùng một đầu vào nhiều lần cho cùng trạng thái vẫn cho kết quả như áp dụng một lần:

\[
f(f(s, e), e) = f(s, e)
\]

Trong đó `s` là trạng thái hiện tại và `e` là event. Ví dụ, đặt trạng thái projection thành `CONFIRMED` theo snapshot có thể idempotent. Ngược lại, câu lệnh “tăng tổng tiền thêm 100” không idempotent nếu chạy hai lần.

| Cách xử lý | Khi nhận lại cùng event | Idempotent? |
| --- | --- | --- |
| `status = 'CONFIRMED'` theo snapshot | Gán lại cùng trạng thái | Thường có, nếu không tạo side effect khác |
| `available = available - quantity` | Trừ tồn kho lần nữa | Không |
| `INSERT` reservation không có khóa chống trùng | Tạo thêm reservation | Không |
| Upsert theo `event_id` hoặc khóa nghiệp vụ duy nhất | Bản ghi đã tồn tại được nhận diện | Có, nếu các thay đổi liên quan cùng transaction |
| Ghi inbox rồi cập nhật nghiệp vụ trong cùng transaction | Event lặp không chạy lại tác động | Có trong phạm vi transaction đó |

Idempotency khác với deduplication đơn thuần. Deduplication phát hiện message trùng; idempotency bảo đảm kết quả nghiệp vụ không thay đổi ngoài ý muốn khi message được xử lý lại. Một handler có thể dùng cả hai: inbox để nhận diện event đã xử lý và thao tác nghiệp vụ idempotent như lớp bảo vệ bổ sung.

## 3. Định danh event và phạm vi consumer

Consumer cần một định danh ổn định để nhận ra cùng một event qua các lần giao lại. Publisher tạo `event_id` một lần khi sự kiện nghiệp vụ được hình thành. Retry, redelivery và replay cùng một sự kiện phải giữ nguyên ID đó.

Ví dụ:

```java
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        long orderVersion,
        BigDecimal totalAmount,
        Instant occurredAt
) {}
```

Không dùng offset Kafka làm event ID toàn cục. Offset chỉ có ý nghĩa trong một partition của topic; khi republish hoặc chuyển message sang topic khác, offset thay đổi. Có thể giữ `event_id` trong payload hoặc message header và dùng nó xuyên suốt các chặng.

Khóa idempotency thường là cặp `(consumer_name, event_id)`, bởi vì hai consumer khác nhau có thể cần xử lý cùng một event cho hai mục đích độc lập. Ví dụ Inventory giữ hàng và Billing tạo hóa đơn; việc Inventory đã xử lý không có nghĩa Billing được bỏ qua.

Nếu hệ thống có nhiều tenant hoặc một consumer có nhiều projection độc lập, đưa tenant/projection vào phạm vi khóa khi cần. Định danh phải phản ánh chính xác đơn vị công việc cần chống trùng.

## 4. Inbox pattern: ghi nhận event đã xử lý

Inbox là bảng lưu các event mà một consumer đã áp dụng thành công. Khóa duy nhất ngăn cùng consumer áp dụng cùng event nhiều lần.

Ví dụ schema SQL:

```sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(150) NOT NULL,
    event_id       UUID NOT NULL,
    event_type     VARCHAR(200) NOT NULL,
    aggregate_id   VARCHAR(200),
    payload_hash   VARCHAR(128),
    processed_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

`consumer_name` xác định handler hoặc projection sở hữu lần xử lý. `event_id` là ID ổn định do publisher tạo. `payload_hash` là tùy chọn nhưng hữu ích để phát hiện trường hợp cùng một ID lại đi kèm payload khác nhau. Không lưu toàn bộ payload nếu consumer không cần hoặc payload có dữ liệu nhạy cảm.

Khi xử lý event, consumer thực hiện ba việc trong cùng một transaction database:

1. Thử insert khóa `(consumer_name, event_id)` vào inbox.
2. Nếu insert thành công, áp dụng thay đổi nghiệp vụ.
3. Commit inbox record và thay đổi nghiệp vụ cùng nhau.

Nếu khóa đã tồn tại, event đã được xử lý thành công trước đó; handler có thể kết thúc mà không lặp tác động. Nếu bước nghiệp vụ thất bại, transaction rollback cả inbox record, để lần giao lại có thể thử lại.

## 5. Triển khai inbox nguyên tử

Không nên chỉ gọi `existsByEventId()` rồi mới insert. Hai consumer xử lý đồng thời có thể cùng thấy event chưa tồn tại, sau đó cả hai cùng thực hiện tác động nghiệp vụ. Ràng buộc unique ở database phải là cơ chế quyết định cuối cùng.

Với PostgreSQL, có thể dùng `INSERT ... ON CONFLICT DO NOTHING`:

```sql
INSERT INTO consumer_inbox (
    consumer_name,
    event_id,
    event_type,
    aggregate_id,
    processed_at
)
VALUES (
    :consumer_name,
    :event_id,
    :event_type,
    :aggregate_id,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
```

Repository cần trả về số hàng được insert. Nếu là `1`, consumer mới nhận event; nếu là `0`, event đã được ghi nhận. Cú pháp cụ thể phụ thuộc database; dùng thao tác insert có điều kiện hoặc unique constraint tương đương ở hệ quản trị khác.

Ví dụ service xử lý:

```java
@Service
public class InventoryEventHandler {

    private static final String CONSUMER = "inventory.order-confirmed";

    private final InboxRepository inbox;
    private final InventoryService inventory;

    public InventoryEventHandler(
            InboxRepository inbox,
            InventoryService inventory) {
        this.inbox = inbox;
        this.inventory = inventory;
    }

    @Transactional
    public void handle(OrderConfirmed event) {
        boolean firstDelivery = inbox.insertIfAbsent(
                CONSUMER,
                event.eventId(),
                "OrderConfirmed",
                event.orderId().toString()
        );

        if (!firstDelivery) {
            return;
        }

        inventory.reserveFor(event.orderId(), event.totalAmount());
    }
}
```

`insertIfAbsent` phải thực hiện insert nguyên tử và nằm trong cùng transaction với `reserveFor`. Nếu `reserveFor` ném exception, inbox record cũng rollback. Nếu transaction commit, cả dấu vết đã xử lý và reservation cùng tồn tại.

Listener Spring Modulith có thể gọi service này:

```java
@Component
public class InventoryProjectionListener {

    private final InventoryEventHandler handler;

    public InventoryProjectionListener(InventoryEventHandler handler) {
        this.handler = handler;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        handler.handle(event);
    }
}
```

`@ApplicationModuleListener` giao event bất đồng bộ sau commit theo cơ chế Spring Modulith. Transaction của `InventoryEventHandler` bảo vệ inbox và thay đổi Inventory. Nếu publication được giao lại, khóa inbox khiến handler bỏ qua tác động đã commit.

## 6. Vì sao inbox và nghiệp vụ phải cùng transaction?

Hai thứ tự ghi sai thường tạo ra lỗi mất dữ liệu.

**Ghi inbox trước, nghiệp vụ sau, nhưng dùng hai transaction độc lập:**

1. Inbox commit `event_id`.
2. Cập nhật tồn kho thất bại.
3. Event được giao lại.
4. Inbox báo event đã tồn tại, handler bỏ qua.
5. Tồn kho chưa từng được cập nhật nhưng event không còn được xử lý.

**Ghi nghiệp vụ trước, inbox sau, nhưng dùng hai transaction độc lập:**

1. Tồn kho được cập nhật và commit.
2. Tiến trình dừng trước khi ghi inbox.
3. Event được giao lại.
4. Tồn kho bị cập nhật lần thứ hai.

Giải pháp là ghi inbox và nghiệp vụ trong cùng một transaction database. Khi commit, cả hai cùng tồn tại; khi rollback, cả hai cùng không tồn tại.

Điều này yêu cầu hai thao tác cùng tham gia một transaction manager và transactional resource. Nếu inbox nằm ở database khác hoặc handler dùng `REQUIRES_NEW` cho inbox, atomicity chung không còn được bảo đảm.

## 7. Xử lý duplicate đồng thời

Một event có thể được giao đồng thời cho hai thread do retry, redelivery hoặc nhiều worker. Unique constraint trên `(consumer_name, event_id)` khiến chỉ một transaction insert thành công. Transaction còn lại phải chờ kết quả xung đột theo cơ chế database, rồi nhận biết rằng event đã được ghi nhận.

Không nên xử lý lỗi unique constraint bằng cách tiếp tục chạy nghiệp vụ. Nếu insert thất bại vì khóa đã tồn tại, handler cần kết thúc như duplicate. Nếu lỗi database thuộc loại khác, cần để transaction thất bại để retry hoặc báo lỗi.

Với database không có cú pháp `ON CONFLICT`, có thể dùng insert và bắt lỗi unique constraint ở ranh giới phù hợp, hoặc dùng câu lệnh merge/upsert có semantics nguyên tử. Cần kiểm thử concurrency với database thực tế vì hành vi lock và isolation có thể khác giữa hệ quản trị.

Nếu hai event khác nhau cùng cập nhật một aggregate, inbox không tự bảo đảm thứ tự. Cần thêm aggregate version hoặc sequence để ngăn event cũ ghi đè trạng thái mới.

## 8. Idempotency bằng trạng thái và version

Không phải handler nào cũng cần inbox riêng. Với event mang snapshot đầy đủ, projection có thể dùng aggregate version để chỉ áp dụng snapshot mới hơn:

```sql
UPDATE order_summary
SET status = :status,
    total_amount = :total_amount,
    source_version = :event_version,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id
  AND source_version < :event_version;
```

Nếu update không ảnh hưởng hàng nào, có thể là event cũ hoặc duplicate. Cần phân biệt hai trường hợp nếu việc chẩn đoán quan trọng. Khi event chứa delta như “tăng số lượng thêm 1”, version đơn lẻ không đủ để bỏ qua mọi event cũ mà không mất thay đổi; cần phát hiện sequence gap hoặc dùng inbox theo event ID.

| Dạng event | Cách idempotency phù hợp |
| --- | --- |
| Snapshot trạng thái mới nhất | Upsert có điều kiện theo aggregate version. |
| Delta/tác động cộng dồn | Inbox theo event ID, áp dụng delta cùng transaction. |
| Lệnh tạo tài nguyên với khóa nghiệp vụ | Unique constraint theo business key và xử lý kết quả đã tồn tại. |
| Event có nhiều side effect | Inbox cùng transaction cho side effect nội bộ; outbox hoặc idempotency key cho side effect ngoài. |

## 9. Idempotency cho side effect ngoài database

Inbox chỉ bảo vệ các thay đổi nằm trong transaction database của consumer. Nó không thể rollback một lời gọi HTTP đã thành công, một email đã gửi hoặc một message đã được publish ra broker khác.

Ví dụ handler cập nhật tồn kho rồi gọi payment gateway. Nếu gateway xử lý thanh toán nhưng response bị timeout, consumer không biết giao dịch đã thành công hay chưa. Retry có thể tạo khoản thanh toán thứ hai.

Các cách xử lý:

- Gửi idempotency key ổn định tới API downstream nếu dịch vụ đó hỗ trợ.
- Ghi yêu cầu gửi tiếp vào outbox trong cùng transaction với thay đổi nội bộ.
- Dùng một worker riêng đọc outbox, gửi side effect và retry với cùng operation ID.
- Lưu trạng thái kết quả và đối soát với hệ thống ngoài khi response không xác định.

Ví dụ key cho thao tác thanh toán có thể là `billing.capture:<eventId>`. Cùng một event được retry phải gửi cùng key. Nếu một event tạo nhiều thao tác khác nhau, thêm tên operation để các key không va chạm.

Nếu hệ thống đích không hỗ trợ idempotency và không cung cấp API tra cứu kết quả, không thể khẳng định side effect đó chỉ xảy ra một lần trong mọi tình huống timeout. Cần thiết kế đối soát hoặc quy trình xử lý trạng thái không xác định.

## 10. Idempotency với Kafka consumer

Kafka consumer thường dùng at-least-once bằng cách xử lý record, commit database rồi mới commit offset. Nếu process dừng sau database commit nhưng trước offset commit, Kafka đọc lại record từ offset cũ.

Inbox giúp xử lý trường hợp này:

1. Consumer nhận record chứa `event_id`.
2. Transaction database insert inbox và cập nhật nghiệp vụ.
3. Transaction commit.
4. Consumer commit offset.
5. Nếu process dừng giữa bước 3 và 4, record được giao lại nhưng inbox nhận diện duplicate.

Không nên commit offset trước database transaction nếu yêu cầu không được mất tác động nghiệp vụ. Cũng không nên xem offset là event ID: cùng event có thể được publish lại ở offset khác, và event ID mới là khóa idempotency xuyên suốt.

Với Spring Kafka, acknowledgement mode và error handler quyết định thời điểm commit offset. Cần cấu hình rõ `enable.auto.commit`, `AckMode` và retry/DLT theo phiên bản Spring Kafka. Inbox vẫn cần thiết ngay cả khi dùng producer idempotence hoặc Kafka transaction nếu side effect nằm trong database ngoài Kafka transaction.

## 11. Vai trò của Event Publication Registry trong Spring Modulith

Event Publication Registry theo dõi publication đến transactional listener. Khi listener hoàn tất, registry ghi nhận publication đã hoàn thành; nếu listener lỗi hoặc tiến trình dừng trước khi hoàn tất, publication có thể được phát hiện và phục hồi theo cấu hình persistence và cơ chế của phiên bản Spring Modulith.

Registry và inbox giải quyết hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi |
| --- | --- |
| Event Publication Registry | Publication đã được giao và listener đã hoàn tất chưa? Publication nào còn dang dở? |
| Consumer inbox | Consumer này đã áp dụng tác động nghiệp vụ của event ID này chưa? |

Registry không thay thế inbox. Registry quản lý trạng thái giao publication; inbox bảo vệ tác động nghiệp vụ của consumer. Listener có thể đã cập nhật database nhưng chưa được registry ghi nhận hoàn tất do sự cố ở ranh giới xử lý. Khi publication được gửi lại, inbox ngăn cập nhật lặp.

Không cập nhật trực tiếp bảng nội bộ của registry để ép publication hoàn tất hoặc xóa trạng thái lỗi. Dùng API và cơ chế vận hành công khai của phiên bản Spring Modulith đang dùng. Nếu listener bắt exception rồi trả về bình thường, framework có thể xem listener đã hoàn tất; chỉ nuốt lỗi khi nghiệp vụ đã xử lý lỗi thành một kết quả hợp lệ.

## 12. Retention, replay và rebuild

Inbox record phải được giữ đủ lâu để bao phủ thời gian message có thể được giao lại hoặc replay. Nếu xóa inbox quá sớm, một event cũ được redrive có thể tạo tác động lần nữa.

Khi xác định retention, cân nhắc:

- retention của Kafka topic hoặc broker;
- thời hạn retry và DLQ;
- khoảng thời gian người vận hành có thể replay;
- chính sách phục hồi sau backup/restore;
- yêu cầu audit và lưu trữ nghiệp vụ.

Nếu cần replay toàn bộ event để dựng lại một projection, có thể tạo một consumer/projection identity mới để có inbox namespace riêng. Không xóa inbox đang dùng chỉ để buộc consumer xử lý lại, vì thao tác đó có thể làm lặp side effect nghiệp vụ. Rebuild nên dùng read model riêng, watermark/version và quy trình đối soát.

Với dữ liệu cần retention vô thời hạn nhưng inbox table quá lớn, có thể lưu tombstone hoặc khóa đã xử lý trong kho phù hợp, phân vùng theo thời gian, hoặc lưu checkpoint/version tổng hợp. Việc dọn dữ liệu phải giữ được bảo đảm chống trùng trong toàn bộ replay window.

## 13. Payload conflict và idempotency key sai

Một lỗi nguy hiểm là publisher phát hai payload khác nhau nhưng dùng cùng `event_id`. Nếu consumer chỉ thấy khóa đã tồn tại rồi bỏ qua, lỗi hợp đồng có thể bị che giấu.

Có thể lưu `event_type`, `aggregate_id` và hash payload trong inbox. Khi gặp lại cùng ID:

- Nếu event type và hash giống nhau, đó là duplicate bình thường.
- Nếu ID giống nhưng hash khác, ghi nhận conflict và đưa vào luồng điều tra.
- Không tự ghi đè inbox hoặc chạy payload mới dưới cùng ID.

Hash chỉ nên tính trên biểu diễn payload canonical, ổn định giữa các lần serialize. Nếu JSON field order hoặc format timestamp thay đổi, hash byte thô có thể khác dù dữ liệu logic tương đương. Có thể so sánh các trường định danh/hợp đồng quan trọng thay vì phụ thuộc serialization tùy ý.

## 14. Kiểm thử idempotency theo consumer

Kiểm thử nên bao gồm cả duplicate tuần tự, duplicate đồng thời và sự cố giữa các commit:

1. Gửi cùng event hai lần; thay đổi nghiệp vụ chỉ xảy ra một lần.
2. Gửi cùng event đồng thời từ hai worker; unique constraint chỉ cho một transaction áp dụng.
3. Làm handler thất bại sau khi insert inbox nhưng trước commit; cả inbox và nghiệp vụ rollback.
4. Commit database rồi mô phỏng process dừng trước acknowledgement/offset commit; lần giao lại không lặp side effect.
5. Hai consumer khác nhau nhận cùng event; mỗi consumer có thể xử lý một lần độc lập.
6. Event cũ đến sau event mới; version hoặc sequence ngăn projection bị lùi trạng thái.
7. Cùng event ID nhưng payload khác; hệ thống phát hiện conflict.
8. Retry và replay sau thời gian dài; inbox retention vẫn bảo vệ tác động.
9. Side effect ngoài database được gửi lại với cùng idempotency key hoặc được đối soát.
10. Event Publication Registry resubmit publication incomplete; handler không lặp tác động đã commit.

Kiểm thử concurrency và transaction nên dùng database thật hoặc Testcontainers. Mock repository không thể chứng minh unique constraint, isolation và rollback hoạt động đúng. Với Kafka, kiểm tra offset group sau khi xử lý, sau lỗi và sau rebalance.

## 15. Quan sát và vận hành

Các chỉ số hữu ích gồm:

- số event duplicate được inbox nhận diện theo consumer;
- số conflict khi cùng event ID có payload khác;
- tỷ lệ xử lý thành công lần đầu và sau retry;
- số publication incomplete và tuổi publication lâu nhất;
- số message trong retry/DLT và thời gian chờ replay;
- độ trễ từ event phát sinh đến khi consumer commit;
- số lỗi unique constraint bất thường và lỗi transaction.

Log nên chứa `consumer_name`, `event_id`, event type, aggregate ID, attempt, correlation/trace ID và kết quả `FIRST_DELIVERY`, `DUPLICATE` hoặc `CONFLICT`. Không dùng event ID làm metric label có cardinality cao; dùng nó trong log và trace để truy vết. Không ghi toàn bộ payload nhạy cảm.

Khi điều tra một event bị lặp, đối chiếu inbox, trạng thái nghiệp vụ, publication registry và acknowledgement/offset của broker. Việc này giúp xác định consumer đã commit tác động hay chưa và lần giao lại xuất phát từ chặng nào.

## 16. Checklist triển khai

- [ ] Event có ID ổn định được giữ nguyên qua retry, redelivery và replay.
- [ ] Idempotency key có phạm vi consumer rõ ràng.
- [ ] Inbox có unique constraint theo consumer và event ID.
- [ ] Ghi inbox và thay đổi nghiệp vụ trong cùng transaction database.
- [ ] Không dùng `exists` rồi `insert` như cơ chế chống trùng duy nhất.
- [ ] Duplicate đồng thời được xử lý an toàn.
- [ ] Có version/sequence để xử lý event cũ hoặc sai thứ tự khi cần.
- [ ] Side effect ngoài database có idempotency key hoặc outbox riêng.
- [ ] Event Publication Registry được phân biệt với consumer inbox.
- [ ] Retention inbox bao phủ retry, DLQ và replay window.
- [ ] Có kiểm thử rollback, crash window, duplicate đồng thời và payload conflict.
- [ ] Có metric, log và quy trình điều tra duplicate.

Idempotency theo consumer là lớp bảo vệ cần thiết khi event có thể được giao nhiều lần. Trong Spring Modulith, Event Publication Registry hỗ trợ theo dõi và phục hồi publication; consumer inbox cùng unique constraint bảo vệ tác động nghiệp vụ trong transaction. Khi event ID ổn định, inbox được ghi nguyên tử cùng nghiệp vụ và side effect ngoài database có cơ chế riêng, hệ thống có thể retry và replay mà không tạo tác động trùng ngoài ý muốn.
