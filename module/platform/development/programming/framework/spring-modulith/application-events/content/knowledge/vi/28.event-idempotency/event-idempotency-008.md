# Idempotency theo nghiệp vụ trong Spring Modulith

Trong hệ thống xử lý bằng application event, một listener có thể nhận cùng một event nhiều lần. Việc giao lại có thể xảy ra khi listener thất bại, ứng dụng khởi động lại hoặc broker không nhận được acknowledgement dù message đã tới nơi. Nếu listener thực hiện một hành động cộng dồn như trừ tồn kho, ghi nhận thanh toán hoặc tạo vận đơn, lần xử lý lặp có thể tạo ra kết quả nghiệp vụ sai.

**Idempotency theo nghiệp vụ** bảo đảm một hành động logic chỉ tạo ra một kết quả nghiệp vụ tương ứng, dù hệ thống nhận cùng yêu cầu hoặc event nhiều lần. Cần xác định hành động nào được xem là cùng một hành động, phạm vi của định danh chống lặp và nơi lưu dấu vết đã xử lý. Trong Spring Modulith, cách làm này bổ sung cho Event Publication Registry và cơ chế retry: registry theo dõi việc giao event, còn idempotency bảo vệ dữ liệu và side effect mà listener thực hiện.

## 1. Idempotency có nghĩa gì trong nghiệp vụ?

Một thao tác là idempotent nếu thực hiện một lần hay lặp lại nhiều lần đều dẫn tới cùng trạng thái nghiệp vụ cuối cùng. Có thể diễn đạt bằng hàm chuyển trạng thái (f):

\[
f(f(s, x), x) = f(s, x)
\]

Trong đó `s` là trạng thái hiện tại và `x` là cùng một yêu cầu nghiệp vụ. Khi áp dụng cùng `x` lần thứ hai, trạng thái không thay đổi thêm.

Ví dụ:

- Đặt trạng thái đơn hàng thành `CANCELLED` có thể idempotent nếu lần gọi sau không tạo thêm tác động.
- Ghi nhận “đã nhận thanh toán với mã giao dịch T” có thể idempotent nếu mã giao dịch T chỉ được áp dụng một lần.
- Trừ thêm 2 sản phẩm khỏi tồn kho mỗi lần nhận `OrderPlaced` là không idempotent nếu event bị giao lặp.
- Gửi email xác nhận mỗi lần listener chạy là không idempotent nếu người nhận chỉ nên nhận một email cho một hành động.

Idempotency là thuộc tính của hành động và quy tắc nghiệp vụ, không chỉ là một kỹ thuật lưu `eventId`. Cần trả lời chính xác câu hỏi: hai lần nhận này có đại diện cho cùng một hành động mà khách hàng hoặc nghiệp vụ chỉ muốn thực hiện một lần hay không?

## 2. Vì sao event có thể được xử lý nhiều lần?

Trong hệ thống phân tán, producer, registry, broker và consumer không chia sẻ một transaction duy nhất. Có thể xảy ra tình huống:

1. Listener nhận `PaymentRequested`.
2. Listener gọi dịch vụ thanh toán và dịch vụ đã ghi nhận giao dịch.
3. Ứng dụng dừng trước khi Event Publication Registry ghi nhận listener hoàn tất.
4. Sau khi ứng dụng khởi động lại, publication còn dang dở được giao lại.
5. Listener gọi dịch vụ thanh toán lần nữa.

Một trường hợp tương tự xảy ra khi broker đã nhận message nhưng acknowledgement bị mất. Producer có thể gửi lại vì không biết chắc lần gửi đầu đã thành công hay chưa. Với AMQP, consumer có thể nhận lại message chưa được acknowledge; với Kafka, record có thể được đọc lại khi offset chưa commit hoặc consumer rebalance.

Spring Modulith Event Publication Registry theo dõi publication theo listener và hỗ trợ phát hiện, phục hồi những publication chưa hoàn tất. Cơ chế này giúp tăng độ tin cậy của giao event, nhưng không thể tạo một transaction nguyên tử bao trùm database của ứng dụng, broker và mọi hệ thống ngoài. Vì vậy, không nên suy ra rằng listener chỉ chạy đúng một lần.

## 3. Phân biệt các định danh

Một thiết kế idempotency tốt không dùng một mã cho mọi mục đích. Ít nhất cần phân biệt:

| Định danh | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `eventId` | Đây là lần phát hành event nào? | UUID của `PaymentRequested` |
| `publicationId` | Đây là lần giao event tới listener nào? | Publication của listener `payment-handler` |
| `businessOperationId` | Đây là hành động nghiệp vụ logic nào? | Lần thanh toán thứ hai của đơn hàng `ORD-42` |
| `correlationId` | Những message nào thuộc cùng một luồng xử lý? | ID của workflow thanh toán |
| `aggregateId` | Đối tượng nghiệp vụ nào đang được thay đổi? | `orderId` hoặc `paymentId` |

`eventId` hữu ích để nhận diện việc giao lặp cùng một event. Tuy nhiên, nếu producer tạo một event mới với `eventId` mới cho cùng một hành động nghiệp vụ, kiểm tra `eventId` sẽ không phát hiện được hai event đó là cùng một thao tác. Khi cần bảo vệ một hành động logic qua nhiều lần phát event, hãy dùng `businessOperationId` hoặc một khóa nghiệp vụ ổn định.

Ví dụ, khách hàng nhấn nút thanh toán hai lần do giao diện phản hồi chậm. Hai request có thể tạo hai event khác `eventId`, nhưng cùng đại diện cho một lần thanh toán đã được xác định bởi `paymentAttemptId`. Hệ thống thanh toán cần nhận diện khóa của lần thanh toán đó thay vì chỉ dựa trên UUID của message.

## 4. Xác định khóa idempotency theo nghiệp vụ

Khóa idempotency phải xác định đúng một hành động logic trong phạm vi nghiệp vụ. Khóa quá rộng có thể chặn một hành động hợp lệ; khóa quá hẹp không ngăn được thao tác trùng.

Một số ví dụ:

| Hành động | Khóa có thể dùng | Điều cần tránh |
| --- | --- | --- |
| Thu tiền cho một lần thanh toán | `paymentAttemptId` | Chỉ dùng `orderId` nếu đơn hàng có thể thanh toán nhiều lần hoặc chia đợt |
| Giữ hàng cho một lần checkout | `reservationId` hoặc `checkoutId` | Dùng mã sản phẩm vì nhiều đơn hàng có thể cùng giữ một sản phẩm |
| Tạo vận đơn cho một lần giao | `fulfillmentId` | Dùng `orderId` nếu một đơn có nhiều kiện hoặc nhiều lần giao |
| Áp dụng một event vào projection | `consumerName + eventId` hoặc stream position | Chỉ dùng timestamp |
| Ghi nhận một hóa đơn | `invoiceRequestId` hoặc khóa duy nhất theo quy tắc phát hành | Dùng mã khách hàng nếu khách có nhiều hóa đơn |

Khóa thường cần kết hợp loại hành động và phạm vi sở hữu. Ví dụ `payment:{paymentAttemptId}` hoặc cặp cột `(consumer_name, event_id)`. Có thể lưu các thành phần trong các cột riêng để tạo unique constraint và truy vấn thuận tiện hơn thay vì ghép chuỗi tùy ý.

### Khóa phải ổn định qua retry

Khóa được tạo khi hệ thống xác định hành động nghiệp vụ lần đầu và phải được giữ lại khi retry. Không tạo UUID mới ở mỗi lần gọi lại nếu các lần gọi đó cùng đại diện cho một hành động logic.

Ngược lại, một hành động mới có chủ đích cần có khóa mới. Ví dụ, khách hàng thử thanh toán lại sau khi lần trước bị từ chối và đã chọn phương thức thanh toán khác có thể là một payment attempt mới. Quy tắc nghiệp vụ cần phân biệt retry kỹ thuật của cùng attempt với việc tạo attempt mới.

### Không dùng payload làm khóa duy nhất một cách tùy tiện

Hash payload có thể giúp nhận diện hai request có nội dung giống nhau, nhưng hai hành động hợp lệ đôi khi có payload giống hệt. Ví dụ, khách hàng mua hai lần cùng một sản phẩm với cùng số lượng. Nếu hash nội dung được dùng làm khóa duy nhất, lần mua thứ hai có thể bị chặn nhầm.

Payload fingerprint hữu ích để kiểm tra một idempotency key có bị tái sử dụng với nội dung khác hay không. Nó thường nên là dữ liệu kiểm tra đi kèm khóa, không tự động thay thế định danh hành động.

## 5. Idempotent consumer với Inbox pattern

Với consumer nhận event, một cách phổ biến là lưu dấu vết event đã xử lý trong bảng inbox hoặc `processed_event`. Khóa duy nhất thường gồm tên consumer và `eventId`, vì cùng một event có thể được nhiều consumer độc lập xử lý.

Ví dụ schema:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Đây là schema minh họa; kiểu UUID và kiểu thời gian cần điều chỉnh theo database. Unique constraint là phần quan trọng: nó bảo vệ trước hai instance cùng nhận một event gần như đồng thời.

Luồng xử lý nên thực hiện việc ghi nhận event và thay đổi dữ liệu nghiệp vụ trong cùng transaction:

1. Consumer nhận event.
2. Thử tạo bản ghi inbox với khóa `(consumer_name, event_id)`.
3. Nếu bản ghi đã tồn tại, coi đây là lần giao lặp và kết thúc mà không áp dụng lại nghiệp vụ.
4. Nếu tạo bản ghi mới thành công, thực hiện thay đổi read model hoặc dữ liệu nghiệp vụ.
5. Commit cả bản ghi inbox và thay đổi nghiệp vụ cùng nhau.

Ví dụ abstraction Java:

```java
@Service
class InventoryEventHandler {

    private final ProcessedEventRepository processedEvents;
    private final InventoryRepository inventory;

    InventoryEventHandler(
            ProcessedEventRepository processedEvents,
            InventoryRepository inventory
    ) {
        this.processedEvents = processedEvents;
        this.inventory = inventory;
    }

    @Transactional
    public void on(OrderPlaced event) {
        boolean firstDelivery = processedEvents.tryRegister(
                "inventory-handler", event.eventId()
        );

        if (!firstDelivery) {
            return;
        }

        inventory.reserve(event.orderId(), event.items());
    }
}
```

`tryRegister` là abstraction do ứng dụng triển khai. Nó cần dựa vào thao tác insert nguyên tử được bảo vệ bằng unique constraint, không chỉ thực hiện `SELECT` rồi `INSERT` trong hai bước không khóa. Tùy database, có thể dùng câu lệnh kiểu `INSERT ... ON CONFLICT DO NOTHING` hoặc cơ chế tương đương để trả về việc bản ghi có được tạo hay không.

Nếu cập nhật tồn kho thất bại, transaction phải rollback cả bản ghi inbox. Khi event được giao lại, consumer có thể thử lại. Nếu ghi inbox đã commit trước rồi mới cập nhật tồn kho ở transaction khác, một lỗi giữa hai bước có thể khiến event bị coi là đã xử lý trong khi nghiệp vụ chưa hoàn tất.

## 6. Idempotency theo hành động nghiệp vụ

Inbox theo `eventId` giải quyết việc cùng một event được giao lại. Nhưng có trường hợp hai event khác nhau cùng yêu cầu một hành động nghiệp vụ. Khi đó cần ràng buộc trên khóa nghiệp vụ.

Ví dụ, một đơn hàng có thể phát hai event `PaymentRequested` khác `eventId` do hai request được gửi gần như đồng thời. Nếu cả hai cùng mang `paymentAttemptId` giống nhau, chỉ một lần thu tiền được phép được tạo.

```sql
CREATE TABLE payment_operation (
    payment_attempt_id VARCHAR(100) PRIMARY KEY,
    order_id            VARCHAR(100) NOT NULL,
    amount              DECIMAL(19, 2) NOT NULL,
    currency            CHAR(3) NOT NULL,
    status              VARCHAR(30) NOT NULL,
    provider_reference  VARCHAR(150),
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);
```

Khóa chính `payment_attempt_id` đảm bảo một attempt không được tạo thành nhiều operation record. Trước khi xử lý, ứng dụng cần xác minh các thuộc tính của request trùng với operation đã có. Nếu cùng khóa nhưng số tiền hoặc currency khác, đây là xung đột nghiệp vụ cần báo lỗi, không được âm thầm trả kết quả cũ.

Các trạng thái như `PENDING`, `SUCCEEDED`, `DECLINED` và `UNKNOWN` giúp phân biệt kết quả. `UNKNOWN` có thể cần khi lời gọi provider timeout và chưa xác định provider đã thu tiền hay chưa. Không được tự động coi timeout là thất bại chắc chắn rồi tạo một attempt mới mà chưa đối soát.

## 7. Kết hợp với Spring Modulith listener

Spring Modulith giúp publisher và listener giao tiếp qua application event. Ví dụ publisher phát event trong transaction nghiệp vụ:

```java
public record PaymentRequested(
        UUID eventId,
        UUID orderId,
        UUID paymentAttemptId,
        BigDecimal amount,
        String currency
) {}
```

```java
@Service
class CheckoutService {

    private final ApplicationEventPublisher events;

    CheckoutService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void requestPayment(
            UUID orderId,
            UUID paymentAttemptId,
            BigDecimal amount,
            String currency
    ) {
        events.publishEvent(new PaymentRequested(
                UUID.randomUUID(),
                orderId,
                paymentAttemptId,
                amount,
                currency
        ));
    }
}
```

Listener có thể dùng `@ApplicationModuleListener` để xử lý event theo cơ chế listener của Spring Modulith:

```java
@Component
class PaymentRequestedListener {

    private final PaymentApplicationService payments;

    PaymentRequestedListener(PaymentApplicationService payments) {
        this.payments = payments;
    }

    @ApplicationModuleListener
    void on(PaymentRequested event) {
        payments.process(event);
    }
}
```

Trong `PaymentApplicationService`, hãy dùng `paymentAttemptId` để bảo vệ hành động thu tiền. `eventId` vẫn được dùng để ghi nhận lần giao event trong inbox. Hai khóa giải quyết hai trường hợp khác nhau: một event bị giao lại và nhiều event cùng đại diện cho một payment attempt.

Event Publication Registry theo dõi publication tới listener. Nếu listener ném exception, publication có thể còn dang dở và được phục hồi theo cấu hình. Nếu listener đã hoàn thành tác động nghiệp vụ nhưng tiến trình dừng trước khi registry ghi nhận hoàn tất, listener có thể được gọi lại. Inbox và khóa nghiệp vụ giúp lần gọi lại không tạo thêm khoản thu hoặc thay đổi dữ liệu ngoài ý muốn.

## 8. Side effect bên ngoài và giới hạn của transaction database

Transaction database không thể tự bảo đảm tính nguyên tử cho một lời gọi HTTP tới cổng thanh toán, gửi email hoặc API vận chuyển. Có thể xảy ra:

- Provider đã thực hiện thao tác nhưng ứng dụng timeout trước khi nhận response.
- Ứng dụng nhận response thành công nhưng dừng trước khi lưu trạng thái vào database.
- Database commit nhưng request tới provider chưa được gửi.

Không nên giữ một transaction database mở trong thời gian dài để chờ hệ thống ngoài rồi giả định hai hệ thống sẽ cùng commit hoặc rollback. Cần dùng cơ chế idempotency của provider, lưu trạng thái operation và có quy trình đối soát.

### Gửi idempotency key tới provider

Nếu provider hỗ trợ idempotency key, hãy gửi khóa ổn định của business operation, ví dụ `paymentAttemptId`. Khi request được gửi lại với cùng khóa và cùng nội dung, provider có thể trả về kết quả của thao tác trước thay vì thực hiện thu tiền lần nữa. Cần đọc rõ thời gian lưu khóa, phạm vi áp dụng và cách provider xử lý cùng key nhưng payload khác nhau.

Không phải mọi API đều hỗ trợ idempotency key. Nếu provider không hỗ trợ, ứng dụng cần cơ chế kiểm tra trạng thái giao dịch theo merchant reference, đối soát giao dịch hoặc một quy trình nghiệp vụ bù trừ phù hợp. Không thể tự tạo exactly-once cho một hệ thống ngoài chỉ bằng cách lưu event ID trong database nội bộ.

### Outbox và workflow

Nếu cần phát một yêu cầu tích hợp sau khi transaction nghiệp vụ commit, Transactional Outbox có thể lưu yêu cầu gửi trong cùng transaction với thay đổi dữ liệu. Một worker gửi outbox record tới provider hoặc broker và đánh dấu kết quả. Việc gửi có thể lặp khi acknowledgement không rõ, vì vậy vẫn cần idempotency ở đích nhận.

Với quy trình nhiều bước như thanh toán, giữ hàng và giao vận, có thể dùng saga/process manager để theo dõi trạng thái, timeout, retry và hành động bù trừ. Idempotency bảo vệ từng bước; saga điều phối vòng đời của toàn quy trình. Hai cơ chế bổ trợ nhau.

## 9. Xử lý cùng khóa nhưng payload khác nhau

Một idempotency key chỉ có ý nghĩa nếu được gắn với nội dung và ngữ cảnh xác định. Nếu request thứ hai dùng lại khóa đã có nhưng số tiền, currency, order hoặc loại thao tác khác, hệ thống cần phát hiện xung đột.

Một record idempotency có thể lưu:

- Khóa nghiệp vụ và loại operation.
- Chủ thể hoặc tenant sở hữu operation.
- Fingerprint của các trường request có ý nghĩa.
- Trạng thái xử lý và kết quả đã xác định.
- Thời điểm tạo, hoàn tất và thời hạn lưu.

Khi nhận lại cùng khóa:

1. Nếu fingerprint khớp và operation đã hoàn tất, trả lại kết quả đã lưu hoặc bỏ qua event trùng.
2. Nếu fingerprint khớp nhưng operation đang xử lý, chờ, trả trạng thái đang xử lý hoặc để cơ chế retry thử lại theo chính sách.
3. Nếu fingerprint khác, trả lỗi xung đột và ghi log có kiểm soát.
4. Nếu operation trước thất bại, quyết định theo state machine liệu có thể retry cùng operation hay phải tạo attempt mới.

Không lưu toàn bộ payload nhạy cảm chỉ để so sánh. Có thể tạo fingerprint từ các trường nghiệp vụ đã chuẩn hóa và bảo vệ dữ liệu theo chính sách bảo mật của hệ thống.

## 10. Trạng thái idempotency và xử lý đồng thời

Trong hệ thống có nhiều instance, hai request cùng khóa có thể đến đồng thời. Việc kiểm tra “đã tồn tại chưa?” rồi mới insert không đủ an toàn nếu hai transaction cùng đọc thấy chưa tồn tại.

Hãy dùng unique constraint hoặc thao tác insert nguyên tử để chỉ một transaction giành quyền tạo operation. Transaction còn lại cần đọc trạng thái hiện tại và quyết định trả kết quả đã có, chờ operation hoặc báo xung đột.

Một state machine đơn giản có thể gồm:

```text
ABSENT
  |
  | tạo operation với idempotency key
  v
IN_PROGRESS
  |                 \
  | thành công       \ lỗi có thể retry
  v                   v
COMPLETED          RETRYABLE_FAILURE
  |                   |
  | request lặp       | retry cùng operation
  v                   v
trả kết quả cũ       IN_PROGRESS

Lỗi không thể tự phục hồi có thể chuyển sang FAILED hoặc NEEDS_REVIEW.
```

Không nên để record `IN_PROGRESS` tồn tại vô hạn. Cần lưu thời điểm bắt đầu, lease/timeout hoặc cơ chế phát hiện operation bị bỏ dở. Tuy nhiên, timeout không phải bằng chứng side effect bên ngoài chưa xảy ra; trước khi chạy lại thao tác, phải kiểm tra trạng thái provider hoặc dùng cùng idempotency key ở provider.

## 11. Idempotency cho projection và phép cập nhật read model

Projection thường nhận event theo thời gian và cập nhật read model. Một số phép cập nhật có tính idempotent tự nhiên, số khác thì không.

| Kiểu cập nhật | Ví dụ | Rủi ro khi lặp | Cách bảo vệ |
| --- | --- | --- | --- |
| Gán trạng thái tuyệt đối | `status = PAID` | Thường không đổi kết quả nếu cùng event | Kiểm tra version hoặc event ID để tránh ghi đè event mới hơn |
| Cộng dồn | `total += amount` | Giá trị tăng nhiều lần | Inbox hoặc sequence checkpoint |
| Tạo bản ghi | Insert hóa đơn | Có thể tạo bản ghi trùng | Unique business key và xử lý conflict |
| Chuyển trạng thái | `PENDING -> PAID` | Có thể lặp side effect khi transition chạy lại | State transition có điều kiện và ghi nhận operation |
| Gửi thông báo | Gửi email/SMS | Người dùng nhận nhiều lần | Notification key, outbox và provider key nếu có |

Với event mang trạng thái tuyệt đối, cần chú ý event cũ đến sau có thể ghi đè trạng thái mới. Ví dụ `OrderShipped` tới trước `OrderPaid` do xử lý bất đồng bộ; việc gán trạng thái `PAID` sau đó có thể làm lùi trạng thái. Hãy dùng aggregate version, sequence hoặc state transition có điều kiện để từ chối event cũ.

Với event mang delta như `QuantityIncreased(+2)`, không thể chỉ kiểm tra giá trị hiện tại để biết delta đã được áp dụng chưa. Cần event ID, business operation ID hoặc sequence để nhận diện lần áp dụng.

## 12. Thời hạn lưu idempotency record

Idempotency chỉ có tác dụng khi dấu vết chống lặp còn tồn tại. Nếu xóa record quá sớm, một message cũ được phát lại hoặc một request retry muộn có thể thực hiện hành động lần nữa.

Thời hạn lưu cần dựa trên:

- Thời gian retry tối đa của client và broker.
- Retention của topic/queue hoặc event store.
- Khoảng thời gian có thể replay publication hoặc rebuild projection.
- Thời gian đối soát của provider ngoài.
- Quy định nghiệp vụ và pháp lý về lịch sử giao dịch.

Với thao tác tài chính, lịch sử giao dịch và khóa business operation có thể cần được giữ lâu hơn thời gian cache idempotency của API. Có thể tách dữ liệu kết quả nghiệp vụ lâu dài khỏi bảng inbox ngắn hạn. Không xóa lịch sử giao dịch chỉ vì đã hết thời hạn retry message.

Khi dọn inbox, cần xác định chắc chắn không còn nguồn nào có thể giao lại event cũ trong phạm vi đó. Nếu nguồn có thể replay toàn bộ lịch sử, phải có chiến lược rebuild sử dụng generation riêng hoặc một kho dedup đủ dài để không làm sai dữ liệu hiện tại.

## 13. Idempotency key cho API và command

Idempotency theo nghiệp vụ thường bắt đầu ngay tại ranh giới nhận command. Ví dụ API tạo thanh toán có thể nhận header `Idempotency-Key`. Server lưu key cùng chủ thể, fingerprint request và kết quả.

Quy tắc API thường gồm:

- Cùng key, cùng nội dung và đã hoàn tất: trả lại kết quả đã lưu.
- Cùng key, cùng nội dung nhưng đang xử lý: trả trạng thái phù hợp hoặc cho client retry sau.
- Cùng key nhưng nội dung khác: trả lỗi conflict theo hợp đồng API.
- Key mới: tạo operation mới theo quy tắc nghiệp vụ.

Key cần được scope theo tenant hoặc user khi nghiệp vụ yêu cầu. Nếu chỉ dùng chuỗi key toàn cục mà không kiểm tra chủ thể, hai khách hàng có thể vô tình hoặc cố ý đụng cùng key. Không dùng idempotency key như một bí mật xác thực; vẫn phải kiểm tra quyền truy cập operation.

Server nên lưu kết quả đã xác định, chẳng hạn operation ID, trạng thái và response cần thiết. Không nhất thiết lưu toàn bộ HTTP response chứa token hoặc dữ liệu nhạy cảm. Cần quy định rõ client được retry trong bao lâu và server giữ key trong bao lâu.

## 14. Bảo mật và quyền sở hữu dữ liệu

Idempotency record có thể chứa định danh đơn hàng, khách hàng, giao dịch hoặc fingerprint request. Cần bảo vệ dữ liệu này như dữ liệu nghiệp vụ:

- Chỉ cho phép module sở hữu operation tạo và cập nhật record tương ứng.
- Đặt unique constraint ở database để bảo vệ invariant ngay cả khi có nhiều instance.
- Scope khóa theo tenant hoặc chủ thể khi cần.
- Không ghi token, thông tin thanh toán nhạy cảm hoặc payload đầy đủ vào log.
- Giới hạn quyền truy cập bảng inbox và operation record.
- Có retention và audit phù hợp cho thao tác quan trọng.
- Tránh để consumer tự ý sửa trạng thái operation thuộc module khác; trao đổi qua event hoặc API được công bố.

Idempotency là một invariant nghiệp vụ. Nên đặt ràng buộc tại nơi sở hữu dữ liệu hoặc side effect, thay vì dựa hoàn toàn vào một lớp cache chung mà mọi module đều có thể ghi.

## 15. Kiểm thử idempotency

Kiểm thử cần xác nhận kết quả nghiệp vụ cuối cùng khi cùng hành động được gửi hoặc giao nhiều lần, bao gồm cả trường hợp đồng thời và lỗi giữa chừng.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Cùng event ID được giao hai lần | Listener chỉ áp dụng thay đổi nghiệp vụ một lần |
| Event ID khác nhưng business operation ID giống nhau | Hành động nghiệp vụ chỉ được thực hiện một lần |
| Cùng key, cùng payload đồng thời | Unique constraint chỉ cho một operation thắng; request còn lại đọc trạng thái phù hợp |
| Cùng key, payload khác | Hệ thống báo xung đột, không trả nhầm kết quả |
| Lỗi trước khi commit database | Inbox và thay đổi nghiệp vụ cùng rollback |
| Lỗi sau side effect ngoài nhưng trước khi lưu kết quả | Retry dùng cùng provider key hoặc quy trình đối soát, không tạo side effect mới |
| Listener hoàn tất nhưng registry chưa đánh dấu publication | Redelivery không lặp tác động nghiệp vụ |
| Event cũ đến sau event mới | Version/state transition ngăn read model lùi trạng thái |
| Hết thời hạn lưu record | Chính sách retention không cho phép replay ngoài dự kiến gây lặp |
| Hai instance xử lý đồng thời | Lock/unique constraint bảo vệ invariant |

Với database, nên có integration test để xác nhận unique constraint và transaction rollback thật. Với provider ngoài, có thể dùng sandbox hoặc test double có hỗ trợ idempotency key để mô phỏng timeout sau khi provider đã ghi nhận request. Test chỉ mock một phương thức `exists()` không chứng minh được khả năng chống race condition.

## 16. Quan sát và vận hành

Idempotency giúp hệ thống an toàn hơn khi retry, nhưng cần quan sát để phát hiện key bất thường hoặc operation bị treo.

Các tín hiệu hữu ích:

- Số lần event/request trùng được bỏ qua theo consumer và operation type.
- Số lần cùng key nhưng fingerprint khác nhau.
- Số operation ở trạng thái `IN_PROGRESS` quá thời hạn.
- Số operation `UNKNOWN` cần đối soát với provider.
- Tỷ lệ retry, duplicate delivery và lỗi unique constraint.
- Tuổi của inbox record chưa hoàn tất hoặc operation lâu nhất.
- Số side effect được provider xác nhận theo idempotency key.

Log nên có `eventId`, `businessOperationId`, consumer name, aggregate ID, correlation ID và trạng thái operation. Không dùng ID riêng lẻ làm nhãn metric có cardinality cao; hãy nhóm theo loại operation, consumer hoặc nguyên nhân. Với thao tác tài chính, cần audit được ai hoặc luồng nào tạo operation và trạng thái thay đổi ra sao.

Khi operation ở trạng thái `UNKNOWN`, người vận hành cần đối chiếu provider reference, giao dịch bên ngoài và trạng thái nội bộ trước khi cho phép retry. Không chuyển tất cả operation timeout thành `FAILED` nếu chưa biết side effect đã xảy ra hay chưa.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dùng `eventId` cho mọi nghiệp vụ | Hai event khác ID nhưng cùng hành động vẫn tạo side effect trùng | Bổ sung business operation key |
| Tạo idempotency key mới ở mỗi retry | Hệ thống coi retry là hành động mới | Giữ key ổn định trong toàn bộ vòng đời attempt |
| Dùng `orderId` cho mọi lần thanh toán | Chặn nhầm thanh toán hợp lệ tiếp theo | Dùng `paymentAttemptId` hoặc khóa đúng phạm vi |
| Chỉ `SELECT` trước khi `INSERT` | Hai instance có thể cùng vượt qua kiểm tra | Unique constraint và insert nguyên tử |
| Commit inbox trước thay đổi nghiệp vụ | Event có thể bị coi là đã xử lý dù nghiệp vụ chưa hoàn tất | Cùng transaction |
| Gọi provider không có idempotency key | Timeout có thể dẫn tới thu tiền hoặc tạo đơn trùng | Dùng key của provider hoặc đối soát |
| Coi timeout là thất bại chắc chắn | Tạo attempt mới khi thao tác cũ đã thành công | Dùng trạng thái `UNKNOWN` và kiểm tra kết quả |
| Xóa inbox quá sớm | Event cũ được replay có thể tạo tác động lại | Retention theo thời gian replay thực tế |
| Cho rằng registry bảo đảm exactly-once | Side effect vẫn có thể lặp ở ranh giới ngoài | Idempotency tại nơi thực hiện nghiệp vụ |
| Chỉ kiểm thử một lần xử lý thành công | Không phát hiện duplicate, concurrency hoặc crash window | Kiểm thử lặp, đồng thời và lỗi giữa chừng |

## 18. Quy trình áp dụng trong một module

Khi triển khai idempotency cho một luồng application event, hãy thực hiện theo thứ tự:

1. Xác định hành động nghiệp vụ nào chỉ được tạo hiệu lực một lần.
2. Phân biệt `eventId`, publication ID, aggregate ID và business operation ID.
3. Chọn khóa idempotency đúng phạm vi, ổn định qua retry và có thể phân biệt một hành động mới.
4. Đặt unique constraint hoặc cơ chế lưu operation tại module sở hữu invariant.
5. Với consumer, ghi inbox và thay đổi dữ liệu nội bộ trong cùng transaction.
6. Với side effect ngoài, dùng idempotency key của provider, outbox hoặc workflow đối soát.
7. Xử lý trạng thái đang chạy, thành công, thất bại có thể retry và kết quả chưa xác định.
8. Xác định retention đủ dài so với retry, replay và quy trình đối soát.
9. Kiểm thử duplicate event, duplicate business command, payload conflict, concurrency và crash window.
10. Theo dõi duplicate suppression, operation bị treo và kết quả chưa xác định trong vận hành.

Idempotency theo nghiệp vụ giúp một hành động giữ đúng ý nghĩa dù event hoặc request được giao lại nhiều lần. Khi khóa phản ánh đúng hành động logic, dữ liệu chống lặp được lưu bền vững, thay đổi nội bộ cùng commit nguyên tử và side effect ngoài có cơ chế xác nhận phù hợp, Spring Modulith có thể phục hồi publication mà không làm nhân đôi kết quả nghiệp vụ.
