# Idempotent handler

*Thiết kế event handler an toàn khi một application event được giao nhiều lần*

Trong một ứng dụng Spring Modulith, listener thường xử lý application event sau khi transaction nghiệp vụ của module phát đã commit. Listener có thể cập nhật read model, tạo bản ghi nghiệp vụ hoặc gọi một hệ thống khác. Tuy nhiên, khi có timeout, restart, retry hay resubmission, cùng một event có thể đến listener nhiều lần.

**Idempotent handler** là event handler có thể nhận lại cùng một event mà kết quả nghiệp vụ cuối cùng vẫn tương đương với việc xử lý event đó một lần. Đây là đặc tính quan trọng khi xây dựng giao sự kiện đáng tin cậy: publisher và listener có thể retry, còn consumer bảo vệ dữ liệu và side effect khỏi bị nhân đôi.

Idempotency không có nghĩa là bỏ qua mọi event trùng nội dung. Hai event khác nhau có thể cùng mô tả một aggregate nhưng đại diện cho hai thay đổi hợp lệ. Handler cần nhận diện đúng lần phát event bằng định danh ổn định và lưu dấu xử lý theo phạm vi consumer.

## 1. Vì sao một event có thể được giao nhiều lần?

Trong hệ thống bất đồng bộ, việc gửi message và ghi nhận kết quả thường không nằm trong cùng một transaction xuyên suốt. Một số tình huống phổ biến:

- Listener đã cập nhật dữ liệu nhưng tiến trình dừng trước khi publication được ghi nhận hoàn tất.
- Broker đã nhận message nhưng producer bị timeout trước khi nhận confirm và gửi lại.
- Consumer xử lý xong nhưng mất kết nối trước khi acknowledgement được broker ghi nhận.
- Spring Modulith resubmit publication còn chưa hoàn tất sau khi nguyên nhân lỗi được khắc phục.
- Consumer khởi động lại hoặc đọc lại message do offset chưa được commit.

Ví dụ, listener nhận `PaymentCaptured` và ghi nhận khoản thanh toán. Transaction cơ sở dữ liệu đã commit, nhưng ứng dụng dừng trước khi publication registry cập nhật trạng thái hoàn tất. Khi publication được gửi lại, listener có thể được gọi lần nữa. Nếu handler cứ cộng số tiền vào tổng thanh toán, đơn hàng sẽ bị ghi nhận hai lần.

Vì vậy, không nên giả định một event chỉ được giao đúng một lần. Thiết kế thực tế thường chấp nhận khả năng giao ít nhất một lần và làm cho consumer chịu được việc nhận trùng.

## 2. Idempotency key phải đại diện cho một lần phát event

Để nhận diện bản giao lại, event cần có một định danh ổn định, chẳng hạn `eventId`:

```java
import java.time.Instant;
import java.util.UUID;

public record PaymentCaptured(
    UUID eventId,
    UUID paymentId,
    UUID orderId,
    long amountInCents,
    Instant occurredAt
) {}
```

`eventId` được tạo tại nơi phát event và được giữ nguyên qua mọi lần retry, serialize, publish lại hoặc resubmit. Handler không được tạo một ID mới mỗi lần nhận message, vì như vậy cùng một event sẽ trông giống event mới.

Phân biệt các loại định danh:

| Định danh | Ý nghĩa | Dùng làm khóa chống trùng? |
|---|---|---|
| `eventId` | Một lần phát event cụ thể | Thường là lựa chọn phù hợp nhất |
| `aggregateId` | Aggregate mà event nói đến | Không đủ, vì một aggregate có nhiều event hợp lệ |
| `paymentId` hoặc `orderId` | Định danh đối tượng nghiệp vụ | Chỉ dùng khi quy tắc nghiệp vụ xác định một hành động duy nhất cho đối tượng đó |
| `correlationId` | Nhóm các message thuộc cùng một luồng nghiệp vụ | Không, vì một luồng có thể chứa nhiều event khác nhau |

Ví dụ, một đơn hàng có thể nhận `OrderPlaced`, `OrderPaid` và `OrderShipped`. Dùng `orderId` làm khóa duy nhất sẽ khiến handler nhầm các event khác nhau là duplicate. `eventId` phân biệt từng lần phát, còn `orderId` giúp kiểm tra thứ tự và trạng thái aggregate.

Nếu cùng một yêu cầu nghiệp vụ có thể được gửi lại từ API và tạo ra nhiều event ID khác nhau, cần thêm khóa idempotency ở biên nhận lệnh, ví dụ `requestId` do client gửi. Đây là lớp bảo vệ khác với deduplication event ở consumer.

## 3. Inbox pattern: lưu dấu event đã xử lý

Một cách triển khai phổ biến là tạo bảng inbox hoặc `processed_event` để ghi nhận event đã được consumer áp dụng. Khóa chính nên gồm tên consumer và event ID, vì nhiều consumer độc lập có thể cần xử lý cùng một event.

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Khi handler nhận event, nó thực hiện hai việc trong cùng transaction:

1. Ghi nhận quyền xử lý event ID vào inbox bằng thao tác insert nguyên tử.
2. Nếu insert thành công, cập nhật read model hoặc dữ liệu nghiệp vụ.

Nếu event ID đã tồn tại cho consumer đó, handler kết thúc mà không lặp lại side effect. Nếu cập nhật projection thất bại, transaction rollback cả dữ liệu projection lẫn dấu inbox, cho phép lần giao lại xử lý tiếp.

Ví dụ service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PaymentProjectionHandler {

    private static final String CONSUMER = "payment-projection";

    private final ProcessedEventInbox inbox;
    private final PaymentReadModel readModel;

    PaymentProjectionHandler(
            ProcessedEventInbox inbox,
            PaymentReadModel readModel) {
        this.inbox = inbox;
        this.readModel = readModel;
    }

    @Transactional
    public void handle(PaymentCaptured event) {
        boolean firstDelivery = inbox.claim(CONSUMER, event.eventId());
        if (!firstDelivery) {
            return;
        }

        readModel.markCaptured(
            event.paymentId(),
            event.orderId(),
            event.amountInCents(),
            event.occurredAt()
        );
    }
}
```

`ProcessedEventInbox.claim` là abstraction của ứng dụng. Phần triển khai cần dùng một thao tác insert nguyên tử được bảo vệ bởi unique constraint, ví dụ `INSERT ... ON CONFLICT DO NOTHING` trên PostgreSQL hoặc cú pháp tương đương của hệ quản trị đang dùng. Không chỉ dùng `existsById()` rồi `save()` như hai thao tác tách rời: hai worker có thể cùng kiểm tra thấy chưa tồn tại và cùng thực hiện side effect.

Inbox và read model phải tham gia cùng transaction cơ sở dữ liệu. Nếu inbox nằm ở một database khác với projection, việc ghi hai nơi không còn nguyên tử; khi đó cần thiết kế quy trình phối hợp riêng.

## 4. Kết hợp với listener của Spring Modulith

Với listener xử lý event sau commit, có thể dùng `@ApplicationModuleListener`:

```java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class PaymentProjectionListener {

    private final PaymentProjectionHandler handler;

    PaymentProjectionListener(PaymentProjectionHandler handler) {
        this.handler = handler;
    }

    @ApplicationModuleListener
    void on(PaymentCaptured event) {
        handler.handle(event);
    }
}
```

`@ApplicationModuleListener` là lựa chọn thường dùng cho listener bất đồng bộ được xử lý sau khi transaction publisher commit và trong transaction riêng. Khi handler ném exception, cơ chế xử lý publication có thể giữ trạng thái chưa hoàn tất để retry hoặc resubmit theo cấu hình. Nếu handler bắt exception rồi bỏ qua, framework có thể xem lần gọi là thành công; chỉ bắt lỗi khi đã xử lý được hoặc đã chuyển nó sang một trạng thái được theo dõi rõ ràng.

Spring Modulith event publication registry theo dõi việc giao publication cho từng listener. Registry hỗ trợ phát hiện publication chưa hoàn tất và phục hồi việc giao. Nó không tự động làm cho side effect trong handler idempotent. Inbox vẫn cần thiết để bảo vệ read model hoặc thao tác nghiệp vụ khi cùng event được gọi lại.

## 5. Xử lý duplicate đồng thời

Kiểm tra duplicate chỉ bằng câu lệnh đọc trước khi ghi không an toàn khi có nhiều worker. Hai worker có thể cùng đọc trạng thái “chưa xử lý”, sau đó cùng cập nhật projection. Unique constraint trên `(consumer_name, event_id)` là lớp bảo vệ cuối cùng ở database.

Thiết kế thao tác `claim` sao cho chỉ một transaction có thể nhận quyền xử lý event ID. Các transaction cạnh tranh phải chờ hoặc nhận kết quả insert không thành công theo semantics của database. Sau khi claim thành công, handler cập nhật read model trong cùng transaction. Nếu transaction rollback, claim cũng rollback; worker khác hoặc lần retry tiếp theo có thể xử lý lại.

Nếu dùng JPA và để unique constraint phát sinh exception, cần chú ý transaction có thể đã bị đánh dấu rollback-only. Không nên bắt `DataIntegrityViolationException` bên trong cùng transaction rồi tiếp tục cập nhật projection. Hãy dùng thao tác insert-if-absent có kết quả rõ ràng hoặc xử lý xung đột ở ranh giới transaction thích hợp.

## 6. Idempotency với side effect bên ngoài

Inbox pattern bảo vệ tốt khi inbox và dữ liệu được cập nhật nằm trong cùng database transaction. Nó không thể tạo transaction nguyên tử với dịch vụ bên ngoài như cổng thanh toán, email provider hoặc API vận chuyển.

Ví dụ handler gọi API hoàn tiền:

```java
paymentGateway.refund(
    paymentId,
    amount,
    event.eventId().toString()
);
```

Nếu API đích hỗ trợ idempotency key, truyền `eventId` ổn định để hệ thống đích nhận biết các lần gọi lại là cùng một yêu cầu. Cần xác minh nhà cung cấp giữ key trong bao lâu, phạm vi key là gì và phản hồi khi nhận lại key cũ ra sao.

Nếu dịch vụ đích không hỗ trợ idempotency, không thể bảo đảm chỉ gọi một lần bằng cách đánh dấu inbox trước hoặc sau lời gọi:

- Ghi inbox trước rồi gọi API: nếu ứng dụng dừng trước lời gọi, event bị xem là đã xử lý dù side effect chưa xảy ra.
- Gọi API trước rồi ghi inbox: nếu API thành công nhưng ứng dụng dừng trước khi ghi inbox, lần retry có thể gọi API lần nữa.

Các lựa chọn gồm dùng API đích có khóa idempotency, tạo bảng command/outbox để điều phối yêu cầu gửi đi, lưu trạng thái từng bước và đối soát kết quả không rõ ràng. Với side effect quan trọng như thu tiền hoặc hoàn tiền, cần có khả năng tra cứu trạng thái theo request ID trước khi quyết định gọi lại.

## 7. Idempotent update và kiểm tra version

Không phải mọi handler đều cần bảng inbox. Một số phép cập nhật có thể tự idempotent nếu cùng một event tạo ra cùng trạng thái cuối cùng.

Ví dụ, thay vì tăng bộ đếm mỗi lần nhận `OrderCompleted`, có thể cập nhật trạng thái theo version:

```sql
UPDATE order_read_model
SET status = 'COMPLETED', version = :eventVersion
WHERE order_id = :orderId
  AND version < :eventVersion;
```

Lệnh chỉ áp dụng trạng thái nếu event có version mới hơn. Event cũ được giao lại không thể ghi đè trạng thái mới hơn. Tuy nhiên, cách này chỉ đúng khi `eventVersion` có thứ tự rõ ràng và phép cập nhật được xác định theo trạng thái mong muốn.

Với phép cộng dồn như tổng doanh thu, việc cộng `amount` mỗi lần không idempotent. Cần lưu event ID đã áp dụng hoặc thiết kế projection tính lại từ các giao dịch có định danh duy nhất. Idempotency cũng không tự giải quyết event đến sai thứ tự; dùng sequence/version để phát hiện gap hoặc stale event.

## 8. Phạm vi và thời gian lưu dấu idempotency

Khóa inbox cần có phạm vi consumer. `payment-projection` và `customer-history-projection` có thể cùng xử lý `PaymentCaptured`; dấu xử lý của consumer này không được chặn consumer kia.

Thời gian giữ dấu inbox phải dài ít nhất bằng khoảng thời gian hệ thống cho phép retry, resubmit hoặc replay event. Nếu broker giữ message 30 ngày nhưng inbox chỉ giữ 7 ngày, một replay sau ngày thứ 8 có thể áp dụng side effect lần nữa. Với các thao tác tài chính hoặc tác động không thể đảo ngược, dấu idempotency có thể cần lưu lâu dài cùng hồ sơ kiểm toán.

Nếu cần dọn inbox, hãy xác định:

- Thời hạn retention tối đa của broker hoặc nguồn event.
- Khoảng thời gian retry/resubmit có thể xảy ra.
- Có quy trình replay lịch sử hay rebuild projection không.
- Consumer có thể được triển khai lại từ snapshot cũ hay không.
- Dấu xử lý có cần phục vụ kiểm toán hoặc đối soát nghiệp vụ không.

Không xóa dấu inbox chỉ dựa trên tuổi bản ghi nếu vẫn có khả năng message tương ứng được phát lại.

## 9. Retry, lỗi vĩnh viễn và resubmission

Idempotency cho phép retry an toàn hơn, nhưng không thay thế chính sách retry. Cần phân loại lỗi:

- **Lỗi tạm thời:** timeout, mất kết nối hoặc dịch vụ phụ thuộc tạm ngừng. Có thể retry với backoff, jitter và giới hạn số lần.
- **Lỗi dữ liệu/hợp đồng:** thiếu trường bắt buộc, schema không tương thích hoặc event sai định dạng. Cần sửa dữ liệu hoặc hỗ trợ version trước khi xử lý lại.
- **Lỗi nghiệp vụ:** trạng thái aggregate không cho phép hành động. Cần chuyển sang xử lý nghiệp vụ hoặc đối soát, không retry vô hạn.

Với Spring Modulith, publication chưa hoàn tất có thể được resubmit sau khi khắc phục nguyên nhân. Trước khi resubmit, xác định listener nào lỗi và xác nhận handler có thể nhận lại event an toàn. Nếu một phần side effect đã xảy ra trước lỗi, cần kiểm tra inbox hoặc trạng thái ở hệ thống đích để không lặp tác động.

Không bắt exception rồi đánh dấu event thành công chỉ để tránh retry. Cách đó làm publication registry mất dấu công việc chưa hoàn tất và khiến read model có thể bị thiếu dữ liệu.

## 10. Quan sát idempotent handler

Handler nên phát ra metadata đủ để điều tra mà không ghi toàn bộ payload nhạy cảm. Các chỉ số hữu ích gồm:

- Số event nhận được, số event bị bỏ qua vì duplicate và tỷ lệ duplicate theo consumer.
- Số lần xử lý thành công, lỗi, retry và publication chưa hoàn tất.
- Số xung đột unique constraint khi nhiều worker cùng nhận một event.
- Thời gian xử lý, độ trễ từ `occurredAt` đến lúc hoàn tất và số event quá hạn.
- Kết quả gọi API ngoài, số lần dùng lại idempotency key và các request cần đối soát.

Log nên có `consumerName`, `eventId`, `aggregateId`, `eventType`, correlation ID và nguyên nhân retry. Không log token, dữ liệu thanh toán hoặc toàn bộ payload nếu không cần thiết. Cảnh báo khi duplicate tăng bất thường, inbox tăng nhanh hoặc một event bị retry kéo dài.

## 11. Kiểm thử idempotent handler

Kiểm thử phải chứng minh cả kết quả dữ liệu và hành vi khi xử lý trùng. Các tình huống nên có:

1. **Giao một lần:** event mới được áp dụng và có dấu inbox.
2. **Giao lại tuần tự:** cùng event ID đến lần hai không tạo thêm side effect.
3. **Giao đồng thời:** hai worker xử lý cùng event ID chỉ có một worker thực hiện cập nhật nghiệp vụ.
4. **Rollback:** nếu cập nhật projection thất bại, dấu inbox và thay đổi projection cùng rollback để lần retry có thể xử lý.
5. **Event khác cùng aggregate:** hai event ID khác nhau của cùng aggregate đều được xử lý theo thứ tự nghiệp vụ.
6. **Event cũ:** version thấp hơn không ghi đè read model mới hơn.
7. **API ngoài:** timeout sau khi dịch vụ đích đã thành công không làm side effect bị lặp khi dùng idempotency key.
8. **Retention:** replay sau khoảng thời gian được hỗ trợ vẫn được nhận diện duplicate.
9. **Publication retry:** listener ném lỗi, publication chưa hoàn tất và resubmit không nhân đôi tác động đã commit.

Với kiểm thử đồng thời, dùng database có unique constraint và transaction thật tương tự môi trường chạy. Mock repository không chứng minh được race condition đã được ngăn chặn. Với API ngoài, mô phỏng cả tình huống timeout sau khi hệ thống đích đã thực hiện side effect.

## 12. Những điểm cần nhớ

- Event có thể được giao lại do timeout, restart, retry, acknowledgement hoặc resubmission.
- Dùng `eventId` ổn định để nhận diện một lần phát; không dùng riêng aggregate ID hoặc correlation ID làm khóa chống trùng.
- Inbox với unique constraint theo consumer và event ID giúp chống xử lý trùng trong cùng transaction với read model.
- `@ApplicationModuleListener` và event publication registry hỗ trợ giao, theo dõi và phục hồi listener; handler vẫn phải tự bảo đảm idempotency.
- Side effect bên ngoài cần idempotency key ở hệ thống đích hoặc quy trình trạng thái và đối soát riêng.
- Giữ dấu idempotency đủ lâu cho retry và replay; kiểm thử cả giao trùng tuần tự, đồng thời và lỗi giữa chừng.

Khi event handler dùng định danh ổn định, ghi dấu xử lý nguyên tử với dữ liệu nghiệp vụ và phối hợp retry có kiểm soát, ứng dụng Spring Modulith có thể chịu được việc giao event nhiều lần mà không nhân đôi side effect. Đây là nền tảng để publisher, listener và event publication registry cùng tạo nên giao tiếp module đáng tin cậy.
