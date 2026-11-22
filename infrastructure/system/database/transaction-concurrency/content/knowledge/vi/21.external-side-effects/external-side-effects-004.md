# Chuyển sự kiện từ outbox và xử lý giao nhận lặp

Transactional outbox giúp ứng dụng lưu thay đổi nghiệp vụ và ý định phát sự kiện trong cùng một database transaction. Sau khi transaction commit, một tiến trình relay đọc các bản ghi outbox và chuyển chúng tới message broker hoặc hệ thống nhận. Cách làm này tránh khoảng trống dual-write giữa database và broker, nhưng không làm cho việc giao nhận trở thành exactly-once một cách tự động.

Relay có thể gửi một sự kiện thành công rồi gặp sự cố trước khi đánh dấu bản ghi outbox đã gửi. Khi chạy lại, nó sẽ gửi cùng sự kiện lần nữa. Consumer vì thế phải chấp nhận **at-least-once delivery** và xử lý duplicate một cách an toàn.

Thiết kế hoàn chỉnh cần phối hợp ba phần: ghi outbox cùng transaction nghiệp vụ, chuyển sự kiện với cơ chế claim/retry có thể phục hồi, và xử lý sự kiện ở consumer bằng idempotency hoặc inbox/deduplication. Mỗi phần có ranh giới commit riêng và cần xác định rõ điều gì xảy ra khi tiến trình dừng giữa hai bước.

## 1. Outbox giải quyết vấn đề dual-write như thế nào?

Một use case thường phải thay đổi dữ liệu trong database và thông báo cho hệ thống khác. Ví dụ, khi xác nhận đơn hàng, ứng dụng cần:

1. Cập nhật trạng thái order thành **CONFIRMED**.
2. Gửi sự kiện **OrderConfirmed** tới broker để inventory, shipping hoặc notification service xử lý.

Nếu ghi database rồi publish message bằng hai thao tác độc lập, có hai cửa sổ lỗi:

- Database commit thành công nhưng ứng dụng chết trước khi publish. Hệ thống khác không nhận được sự kiện.
- Publish thành công nhưng database rollback hoặc commit thất bại. Consumer nhận một sự kiện mô tả thay đổi chưa tồn tại.

Hai thao tác không nằm trong cùng một transaction ACID. Transaction database thông thường không thể tự rollback một message đã được broker chấp nhận.

Transactional outbox ghi sự kiện vào một bảng thuộc cùng database với dữ liệu nghiệp vụ:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'PENDING';

INSERT INTO outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    created_at
)
VALUES (
    :event_id,
    'Order',
    :order_id,
    'OrderConfirmed',
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Nếu transaction commit, cả trạng thái order và bản ghi outbox cùng tồn tại. Nếu rollback, cả hai cùng không được commit. Relay có thể đọc outbox sau đó và publish sự kiện.

Outbox bảo đảm **ý định phát sự kiện được lưu cùng thay đổi nghiệp vụ**. Nó không bảo đảm broker đã nhận sự kiện ngay tại thời điểm commit, cũng không bảo đảm message chỉ được giao đúng một lần.

## 2. Mô hình dữ liệu outbox

Một bảng outbox cần đủ thông tin để relay có thể nhận diện, giao, retry và chẩn đoán từng sự kiện. Ví dụ:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(200) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by VARCHAR(200),
    locked_until TIMESTAMPTZ,
    claim_token UUID,
    last_error TEXT
);
~~~

Ý nghĩa các trường:

| Trường | Mục đích |
|---|---|
| **event_id** | Định danh ổn định của một sự kiện; dùng làm khóa deduplication ở consumer |
| **aggregate_type**, **aggregate_id** | Cho biết sự kiện thuộc aggregate nghiệp vụ nào |
| **aggregate_version** | Phiên bản hoặc số thứ tự sự kiện trong aggregate, nếu nghiệp vụ cần thứ tự |
| **event_type** | Loại sự kiện để consumer định tuyến và xử lý |
| **payload** | Dữ liệu sự kiện đã được chụp tại thời điểm transaction tạo outbox |
| **created_at** | Thời điểm bản ghi outbox được tạo |
| **published_at** | Thời điểm relay ghi nhận broker đã xác nhận nhận message |
| **attempts** | Số lần relay đã thử gửi |
| **available_at** | Thời điểm sớm nhất được phép thử lại |
| **locked_by**, **locked_until** | Thông tin claim/lease để nhiều relay làm việc song song |
| **last_error** | Lỗi gần nhất phục vụ vận hành |

Có thể bổ sung **schema_version**, **correlation_id**, **causation_id**, **trace_id**, **partition_key**, **tenant_id** hoặc **dead_lettered_at** tùy nhu cầu. Không nên đưa dữ liệu bí mật hoặc thông tin không cần thiết vào payload sự kiện.

**event_id** phải được tạo một lần và giữ nguyên qua các lần retry. Nếu mỗi lần relay gửi lại tạo event id mới, consumer sẽ xem các bản gửi lặp là các sự kiện khác nhau và deduplication không còn tác dụng.

### Sự kiện nên bất biến sau khi được tạo

Sau khi transaction nghiệp vụ commit, nội dung sự kiện nên được xem là immutable. Relay không nên dựng lại payload bằng cách đọc trạng thái hiện tại của aggregate rồi thay nội dung sự kiện cũ. Trạng thái hiện tại có thể đã thay đổi nhiều lần kể từ lúc sự kiện được tạo.

Ví dụ, **OrderConfirmed** cần phản ánh dữ liệu tại thời điểm order được xác nhận. Nếu relay đọc order sau đó khi order đã **SHIPPED**, nó không nên biến payload của **OrderConfirmed** thành dữ liệu của trạng thái mới.

Nếu cần sửa nội dung hoặc schema, phát một sự kiện mới theo hợp đồng mới; không âm thầm thay đổi sự kiện đã commit.

## 3. Ghi outbox trong cùng transaction nghiệp vụ

Điểm quan trọng nhất là thao tác INSERT vào outbox phải tham gia đúng transaction với thay đổi nghiệp vụ.

Ví dụ Spring:

~~~java
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
    public void confirm(long orderId) {
        Order order = orders.confirm(orderId);

        OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            order.id(),
            order.version(),
            order.total()
        );

        outbox.insert(event);
    }
}
~~~

Repository outbox dùng cùng transaction manager và database connection/transaction với repository order. Nếu **outbox.insert** thất bại, transaction cần rollback thay đổi order. Nếu cập nhật order thất bại, không được để lại outbox event đã commit riêng.

Không đặt **REQUIRES_NEW** cho thao tác ghi outbox nếu mục tiêu là nguyên tử cùng transaction nghiệp vụ. Một transaction độc lập có thể commit event trong khi order rollback.

Cũng không gọi broker trực tiếp bên trong transaction này. Nếu broker chậm, transaction sẽ giữ connection và có thể giữ khóa lâu. Nếu publish thành công nhưng database commit thất bại, dual-write vẫn xảy ra.

## 4. Outbox relay có nhiệm vụ gì?

Relay là tiến trình đọc các outbox event chưa giao, gửi chúng đến broker, chờ xác nhận, rồi cập nhật trạng thái giao nhận.

Một vòng xử lý khái quát:

~~~text
Outbox table
    |
    v
Claim một batch sự kiện
    |
    v
Commit claim/lease
    |
    v
Publish tới broker
    |
    v
Chờ broker ACK
    |
    v
Đánh dấu published
    |
    v
Lặp lại với batch tiếp theo
~~~

Relay có thể chạy như:

- Một background worker trong ứng dụng.
- Một service độc lập có nhiều instance.
- Một job polling theo chu kỳ.
- Một connector đọc transaction log như CDC.
- Một thư viện outbox tích hợp với message broker.

Dù triển khai theo cách nào, relay phải xử lý được việc process chết, lease hết hạn, broker timeout, publish thành công nhưng cập nhật database thất bại và nhiều worker cùng tranh chấp một batch.

## 5. Polling relay: claim batch an toàn

Cách đơn giản là polling bảng outbox theo chu kỳ. Một relay tìm các sự kiện chưa publish và đến thời điểm có thể gửi.

Nếu nhiều relay chạy song song, chúng không được cùng claim một event tại cùng thời điểm theo cách gây xử lý không kiểm soát. Có thể dùng row lock và **SKIP LOCKED** trong PostgreSQL để mỗi worker lấy các hàng khác nhau.

Ví dụ claim một batch và đặt lease:

~~~sql
BEGIN;

WITH picked AS (
    SELECT event_id
    FROM outbox_events
    WHERE published_at IS NULL
      AND available_at <= CURRENT_TIMESTAMP
      AND (
          locked_until IS NULL
          OR locked_until < CURRENT_TIMESTAMP
      )
    ORDER BY created_at, event_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events AS o
SET locked_by = :worker_id,
    locked_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    claim_token = :claim_token,
    attempts = attempts + 1
FROM picked
WHERE o.event_id = picked.event_id
RETURNING o.*;

COMMIT;
~~~

Đây là ví dụ theo cú pháp PostgreSQL. **SKIP LOCKED** cho phép worker bỏ qua các hàng đang được worker khác khóa thay vì chờ chúng. Hệ quản trị khác có locking hint hoặc API claim riêng; cần dùng đúng cú pháp và ngữ nghĩa của DBMS.

Sau khi claim, relay đã có danh sách sự kiện và lease. Nó nên commit transaction claim trước khi gọi broker. Nhờ đó, transaction database không giữ row lock trong suốt thời gian network call.

### Vì sao cần lease?

Nếu worker chết sau khi claim, hàng vẫn có **locked_by** và **locked_until**. Khi lease hết hạn, worker khác có thể claim lại.

Lease cần đủ dài cho thời gian xử lý thông thường nhưng không quá dài đến mức sự kiện bị kẹt lâu sau khi worker chết. Nếu publish có thể kéo dài, worker cần gia hạn lease bằng thao tác có điều kiện hoặc chia batch nhỏ hơn.

Lease không bảo đảm tuyệt đối chỉ có một worker đang publish. Một worker có thể bị pause lâu, lease hết hạn, worker khác claim lại, rồi worker cũ tiếp tục chạy. Cả hai có thể publish cùng event. Đây là một lý do consumer vẫn phải deduplicate.

### Dùng claim token để tránh worker cũ ghi đè trạng thái mới

Ngoài **locked_by**, có thể tạo một claim token duy nhất cho mỗi lần claim. Khi worker hoàn tất, chỉ cho phép nó cập nhật nếu token vẫn đúng:

~~~sql
UPDATE outbox_events
SET published_at = CURRENT_TIMESTAMP,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE event_id = :event_id
  AND claim_token = :claim_token
  AND published_at IS NULL;
~~~

Claim token là fencing check cho thao tác cập nhật trạng thái outbox. Nó ngăn worker cũ đánh dấu hoàn tất sau khi quyền claim đã chuyển sang worker khác. Nó không thể thu hồi message mà worker cũ đã gửi tới broker, nên duplicate delivery vẫn có thể xảy ra.

## 6. Thứ tự publish và đánh dấu published

Relay phải chọn thứ tự giữa publish message và cập nhật **published_at**. Có hai khả năng:

**Đánh dấu trước rồi publish**

~~~text
UPDATE outbox: published = true
        |
        v
Process chết trước khi gửi broker
        |
        v
Sự kiện bị mất khỏi hàng chờ
~~~

Cách này có thể làm mất sự kiện vì database đã ghi nhận hoàn tất trong khi broker chưa nhận.

**Publish trước, nhận ACK rồi đánh dấu**

~~~text
Publish tới broker
        |
        v
Broker xác nhận nhận message
        |
        v
UPDATE outbox: published_at = now()
~~~

Cách này tránh đánh dấu đã gửi trước khi broker xác nhận. Nhưng có một cửa sổ duplicate:

~~~text
Broker đã nhận message
        |
        v
Process chết trước UPDATE published_at
        |
        v
Lease hết hạn, relay khác claim lại
        |
        v
Message được publish lần nữa
~~~

Đây là hành vi at-least-once. Relay ưu tiên không mất sự kiện; đổi lại, nó có thể giao lặp. Consumer phải có cơ chế idempotency.

### ACK cần có nghĩa gì?

ACK từ broker chỉ hữu ích nếu nó phản ánh mức độ xác nhận mà ứng dụng yêu cầu. Tùy broker, cấu hình durability, replication, producer confirmation và chính sách lưu message có thể khác nhau.

Không nên đánh dấu outbox published chỉ vì thư viện client đã nhận dữ liệu vào buffer cục bộ. Relay cần chờ kết quả xác nhận từ broker theo cấu hình đã chọn.

Nếu broker trả timeout, kết quả có thể không xác định: broker có thể đã nhận message nhưng ACK bị mất trên đường về. Relay nên xem đây là tình huống có khả năng duplicate và retry với cùng **event_id**.

## 7. Vì sao outbox thường cung cấp at-least-once delivery?

Outbox relay không thể atomically commit một thay đổi trong database và một ACK của broker nếu không dùng một distributed transaction có phối hợp giữa hai resource manager.

Trong mô hình phổ biến, hai bước:

1. Broker nhận message và xác nhận.
2. Database đánh dấu outbox event đã publish.

không nằm trong cùng một transaction nguyên tử. Process có thể dừng giữa hai bước.

Vì thế, relay thường cung cấp at-least-once: một event đã commit sẽ tiếp tục được thử gửi cho đến khi có xác nhận hoặc được chuyển sang trạng thái xử lý lỗi theo chính sách. Một event có thể xuất hiện nhiều lần ở broker.

| Sự cố | Trạng thái outbox | Trạng thái broker | Hệ quả |
|---|---|---|---|
| Process chết trước publish | Chưa published | Chưa nhận | Lease hết hạn, worker khác gửi |
| Publish thất bại rõ ràng | Chưa published | Chưa nhận theo ACK | Retry sau backoff |
| Broker nhận nhưng ACK bị mất | Chưa published | Có thể đã nhận | Retry có thể tạo duplicate |
| Broker ACK, process chết trước update | Chưa published | Đã nhận | Worker khác có thể gửi duplicate |
| ACK và update published thành công | Published | Đã nhận theo ACK | Không cần relay gửi lại bình thường |

Không nên mô tả outbox relay là exactly-once chỉ vì mỗi row có một **event_id** duy nhất hoặc vì broker có producer idempotence. Event id hỗ trợ deduplication; nó không làm hai hệ thống commit chung một thao tác.

## 8. Consumer phải xử lý duplicate một cách idempotent

Một consumer nhận cùng event nhiều lần cần bảo đảm hiệu ứng nghiệp vụ chỉ được áp dụng một lần trong phạm vi mà nó kiểm soát.

Ví dụ consumer nhận **PaymentRequested** và tạo yêu cầu thanh toán trong database của mình. Có thể tạo bảng inbox:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(200) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa chính kết hợp **consumer_name** và **event_id** cho phép nhiều consumer độc lập xử lý cùng một event. Mỗi consumer chỉ ghi nhận event một lần.

### Ghi inbox và thay đổi nghiệp vụ trong cùng transaction

Ví dụ PostgreSQL:

~~~sql
BEGIN;

INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('billing-projection', :event_id)
ON CONFLICT DO NOTHING
RETURNING event_id;
~~~

Nếu INSERT trả về một hàng, đây là lần đầu consumer xử lý event. Trong cùng transaction, áp dụng thay đổi nghiệp vụ:

~~~sql
UPDATE billing_projection
SET payment_requested_count = payment_requested_count + 1
WHERE order_id = :order_id;

COMMIT;
~~~

Nếu INSERT không trả về hàng nào, event đã được ghi nhận trước đó. Consumer bỏ qua phần áp dụng nghiệp vụ và kết thúc xử lý duplicate.

Trong code thực tế, nhánh kiểm tra kết quả INSERT và UPDATE phải nằm trong cùng transaction và cùng consumer handler. Không được commit inbox trước rồi mới cập nhật dữ liệu nghiệp vụ bằng transaction khác. Nếu process chết sau khi commit inbox nhưng trước khi cập nhật projection, lần giao tiếp theo sẽ bị coi là duplicate và bỏ qua; thay đổi nghiệp vụ sẽ bị mất.

Ngược lại, nếu cập nhật projection trước rồi ghi inbox ở transaction khác, process có thể chết giữa hai bước và lần giao tiếp lại sẽ áp dụng hiệu ứng lần thứ hai.

**Inbox/dedup record và hiệu ứng database phải commit hoặc rollback cùng nhau.**

## 9. Xử lý hai bản duplicate đến đồng thời

Hai worker có thể cùng nhận event_id giống nhau. PRIMARY KEY/UNIQUE trên **(consumer_name, event_id)** là điểm phân xử cuối cùng.

Một transaction INSERT thành công. Transaction còn lại sẽ chờ kết quả xung đột khóa duy nhất và sau khi transaction đầu commit, nó không thể tạo một bản ghi inbox thứ hai. Consumer thứ hai thấy không có hàng mới được chèn và bỏ qua hiệu ứng nghiệp vụ.

Không dựa vào một câu SELECT kiểm tra trước rồi mới INSERT; hai worker có thể cùng SELECT thấy chưa có record. Dùng UNIQUE constraint và thao tác INSERT nguyên tử để giải quyết cuộc đua.

## 10. ACK message chỉ sau khi hiệu ứng consumer đã commit

Với broker hỗ trợ ACK thủ công, thứ tự xử lý consumer cần là:

~~~text
Nhận message
     |
     v
BEGIN database transaction
     |
     v
INSERT inbox / dedup record
     |
     v
Áp dụng thay đổi nghiệp vụ nếu event mới
     |
     v
COMMIT
     |
     v
ACK message với broker
~~~

Nếu process chết trước commit, transaction database rollback và message chưa ACK sẽ được giao lại. Consumer có thể thử lại.

Nếu database commit thành công nhưng process chết trước ACK, broker có thể giao message lại. Inbox nhận ra **event_id** đã xử lý và consumer bỏ qua hiệu ứng nghiệp vụ, sau đó ACK bản giao lặp.

Nếu ACK trước khi database commit, broker có thể xóa message khỏi hàng đợi rồi process chết trước commit. Khi đó message không được giao lại và thay đổi nghiệp vụ bị mất.

Vì vậy, với consumer lưu hiệu ứng vào database cục bộ, hãy commit transaction trước rồi mới ACK broker. Chấp nhận khả năng duplicate và xử lý bằng inbox.

Cơ chế ACK, offset commit và visibility timeout khác nhau giữa broker. Với Kafka, consumer thường commit offset sau khi transaction database hoàn tất; với queue broker, ACK xác nhận message cụ thể. Cần hiểu đúng semantics của broker đang dùng.

## 11. Inbox/deduplication không bao phủ side effect bên ngoài

Giả sử consumer nhận **PaymentRequested**, ghi inbox vào database, rồi gọi cổng thanh toán qua HTTP. Nếu provider thu tiền thành công nhưng consumer timeout trước khi lưu kết quả, lần giao lại có thể gọi thanh toán lần nữa.

Database transaction của consumer không thể rollback giao dịch đã được provider thực hiện. Inbox chỉ bảo vệ các thay đổi nằm trong transaction database của consumer.

Có thể kết hợp:

- Idempotency key gửi tới payment provider, thường lấy từ **event_id** hoặc một operation id ổn định.
- Lưu trạng thái yêu cầu và kết quả provider trong database.
- Dùng outbox phía consumer để ghi ý định gọi dịch vụ ngoài trong cùng transaction với inbox và thay đổi nội bộ.
- Dùng reconciliation để đối chiếu trạng thái nếu provider trả kết quả không xác định.

Ví dụ luồng consumer:

~~~text
Nhận PaymentRequested
        |
        v
Transaction consumer:
  ghi inbox
  tạo payment_attempt PENDING
  ghi PaymentCommand vào outbox
  COMMIT
        |
        v
Payment relay gọi provider với idempotency key
        |
        v
Nhận kết quả provider
        |
        v
Transaction consumer:
  cập nhật payment status
  ghi PaymentCompleted/PaymentFailed vào outbox
  COMMIT
~~~

Consumer có thể nhận event lặp mà không tạo nhiều payment_attempt. Relay payment có thể gọi provider lại với cùng idempotency key. Nếu provider hỗ trợ idempotency đúng phạm vi, các lần gọi lặp có thể trả lại cùng kết quả thay vì tạo giao dịch mới.

Nếu provider không hỗ trợ idempotency, cần một giao thức truy vấn trạng thái hoặc đối soát trước khi quyết định gửi lại một thao tác có thể thu tiền.

## 12. Ordering: giao nhận lặp và sai thứ tự là hai vấn đề khác nhau

Outbox có thể chứa nhiều event của cùng một aggregate. Ví dụ:

~~~text
OrderCreated   version 1
OrderPaid      version 2
OrderShipped   version 3
~~~

Nếu nhiều relay claim các row song song, event version 3 có thể được publish trước version 2. Broker cũng có thể chỉ bảo đảm thứ tự trong một partition, không phải toàn bộ topic hoặc toàn hệ thống.

Nếu consumer yêu cầu thứ tự theo aggregate, cần thiết kế rõ:

- Gắn **aggregate_id** làm partition key để các event cùng aggregate đi vào cùng partition.
- Gắn **aggregate_version** hoặc sequence để phát hiện thiếu, lặp hoặc đến sai thứ tự.
- Giới hạn relay chỉ publish event kế tiếp của một aggregate khi event trước đã được ACK.
- Hoặc cho consumer buffer/retry event đến sớm khi còn thiếu version trước.

### Chỉ publish event đầu tiên chưa hoàn tất của mỗi aggregate

Một chiến lược polling có thể chỉ claim event nếu không còn event cũ hơn chưa published của cùng aggregate. Pseudocode SQL minh họa:

~~~sql
SELECT e.event_id
FROM outbox_events e
WHERE e.published_at IS NULL
  AND e.available_at <= CURRENT_TIMESTAMP
  AND NOT EXISTS (
      SELECT 1
      FROM outbox_events older
      WHERE older.aggregate_type = e.aggregate_type
        AND older.aggregate_id = e.aggregate_id
        AND older.aggregate_version < e.aggregate_version
        AND older.published_at IS NULL
  )
ORDER BY e.created_at, e.event_id
FOR UPDATE SKIP LOCKED;
~~~

Đây là ý tưởng, không phải câu SQL hoàn chỉnh cho mọi DBMS. Cần xử lý event không có version, claim/lease, index và trạng thái dead-letter. Nếu event trước bị kẹt hoặc chuyển DLQ, hệ thống phải quyết định có chặn event sau hay cho phép bỏ qua theo chính sách nghiệp vụ.

Thứ tự publish cũng không tự bảo đảm thứ tự hoàn tất ở consumer nếu consumer chạy song song. Nếu thứ tự nghiệp vụ quan trọng, consumer cần kiểm tra version trước khi áp dụng.

### Consumer kiểm tra version

Giả sử projection hiện đang ở version 7 và nhận event version 9. Có thể event version 8 chưa được xử lý. Consumer nên giữ event lại hoặc retry theo chính sách thay vì áp dụng version 9 một cách mù quáng.

Nếu nhận version 7 lần nữa, có thể đó là duplicate hoặc event cũ; deduplication theo **event_id** và kiểm tra **aggregate_version** giúp quyết định bỏ qua an toàn.

Không dùng timestamp để thay version nếu cần thứ tự nghiêm ngặt. Timestamp có thể trùng hoặc lệch giữa node.

## 13. Retry relay và xử lý sự kiện lỗi

Relay cần phân loại lỗi để quyết định thử lại hay chuyển sự kiện sang trạng thái cần can thiệp.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Broker unavailable, connection reset, timeout | Retry với exponential backoff và jitter |
| Throttling | Broker hoặc gateway giới hạn tải | Tuân thủ thời gian chờ nếu có, giảm tốc độ gửi |
| Lỗi xác thực/cấu hình | Credential hết hạn, topic không tồn tại | Báo động và sửa cấu hình; không retry nhanh vô hạn |
| Lỗi payload/schema | Payload không hợp lệ, schema không tương thích | Cách ly sự kiện, điều tra và sửa theo quy trình |
| Lỗi vĩnh viễn theo hợp đồng | Topic bị xóa hoặc event type không được hỗ trợ | Chuyển trạng thái lỗi/parking và báo động |

Một chính sách retry có thể dùng:

\[
delay_n = \min(delay_{max}, delay_0 \times 2^{n-1})
\]

và thêm jitter để nhiều relay không cùng retry một thời điểm. Cần giới hạn số lần thử hoặc tổng thời gian, nhưng không xóa sự kiện âm thầm khi đạt giới hạn.

### Dead-letter hoặc parked event

Khi một event không thể gửi sau nhiều lần thử, có thể chuyển nó sang trạng thái **DEAD** hoặc một bảng dead-letter/parking riêng. Lưu lại:

- event_id và aggregate id.
- Payload nguyên bản.
- Số lần thử.
- Lỗi cuối cùng và thời điểm.
- Lý do chuyển trạng thái.
- Người hoặc quy trình xử lý thủ công.
- Trạng thái replay.

Dead-letter không có nghĩa sự kiện không còn quan trọng. Nếu event đại diện cho một thay đổi nghiệp vụ đã commit, việc bỏ qua có thể làm hệ thống downstream lệch dữ liệu. Cần cảnh báo, quy trình sửa và replay hoặc reconciliation.

### Poison event

Poison event là message luôn gây lỗi ở relay hoặc consumer, chẳng hạn payload hỏng, schema không hỗ trợ hoặc một bug xử lý. Retry liên tục không sửa được lỗi này và có thể chặn cả partition nếu thứ tự là bắt buộc.

Cần giới hạn retry, cô lập event lỗi và quyết định rõ có cho phép event sau tiếp tục hay không. Nếu thứ tự aggregate quan trọng, việc bỏ qua một event cần có quyết định nghiệp vụ hoặc sự kiện sửa trạng thái; không tự ý bỏ qua chỉ để tăng throughput.

## 14. CDC relay khác polling relay ra sao?

Thay vì truy vấn bảng outbox liên tục, có thể dùng Change Data Capture (CDC) đọc transaction log của database. Connector theo dõi các INSERT vào outbox đã commit rồi chuyển thành message.

Ví dụ, CDC connector có thể đọc:

- PostgreSQL logical decoding/WAL.
- MySQL binlog.
- SQL Server transaction log thông qua cơ chế CDC/change capture phù hợp.
- Oracle redo log qua công cụ CDC tương ứng.

Luồng tổng quát:

~~~text
Business transaction
       |
       v
INSERT outbox + commit
       |
       v
Database transaction log
       |
       v
CDC connector đọc thay đổi đã commit
       |
       v
Broker topic
       |
       v
Consumer
~~~

Ưu điểm:

- Không phải polling liên tục bảng outbox.
- Có thể giảm truy vấn quét và cập nhật trạng thái published trên từng row.
- Có thể tận dụng thứ tự log trong phạm vi mà DBMS/connector cung cấp.
- Phù hợp với luồng event lớn và hệ thống đã vận hành CDC.

Giới hạn:

- Phải vận hành connector, checkpoint/offset và schema history.
- Transaction log retention phải đủ dài nếu connector ngừng hoạt động.
- Connector có thể publish message rồi chết trước khi checkpoint offset; khi khởi động lại có thể publish duplicate.
- Xóa/cleanup outbox cần phối hợp với checkpoint và retention.
- CDC không loại bỏ nhu cầu consumer idempotency.
- Thứ tự toàn cục hoặc thứ tự theo aggregate cần hiểu theo connector, partitioning và broker.

### Checkpoint và cửa sổ duplicate

CDC cũng có hai thao tác độc lập: publish message và lưu checkpoint đã đọc tới đâu. Nếu checkpoint trước khi broker nhận message, có thể mất event. Nếu broker nhận rồi nhưng checkpoint chưa được lưu, connector có thể đọc lại và publish duplicate.

Vì vậy, CDC outbox vẫn thường cung cấp at-least-once nếu không có một cơ chế transaction xuyên suốt broker và nguồn log. Consumer cần deduplication như với polling relay.

## 15. Polling hay CDC?

| Tiêu chí | Polling relay | CDC relay |
|---|---|---|
| Độ phức tạp ban đầu | Thường đơn giản hơn | Cần connector và cấu hình log |
| Cách phát hiện event | Query bảng outbox | Đọc transaction log |
| Tải lên database | Polling query và update trạng thái | Đọc log; phụ thuộc connector |
| Độ trễ | Phụ thuộc chu kỳ polling và batch | Có thể gần thời gian thực |
| Claim song song | Cần lock/lease hoặc phân vùng claim | Connector/partition/offset điều phối |
| Duplicate | Có ở publish-ack-mark window | Có ở publish-checkpoint window |
| Cleanup | Có thể xóa row sau retention | Phải phối hợp log checkpoint và retention |
| Vận hành | Theo dõi query, lease, backlog | Theo dõi connector, offset lag, log retention |
| Phù hợp | Lưu lượng vừa phải, muốn ít thành phần | Lưu lượng lớn hoặc đã có nền tảng CDC |

Không có lựa chọn đúng cho mọi hệ thống. Polling thường dễ bắt đầu và dễ kiểm soát. CDC có lợi khi cần luồng thay đổi liên tục và đã có khả năng vận hành transaction log connector. Cả hai vẫn cần event id ổn định, consumer idempotency và giám sát backlog.

## 16. Broker producer idempotence có thay thế consumer deduplication không?

Một số broker cung cấp producer idempotence hoặc transaction để giảm duplicate do retry ở phía producer. Ví dụ Kafka producer idempotence có thể loại bỏ một số bản ghi trùng phát sinh từ retry trong phạm vi producer session/producer identity và cấu hình tương ứng.

Nhưng cần phân biệt:

- Producer idempotence không tự deduplicate hai lần relay độc lập cùng đọc một outbox event.
- Producer restart hoặc producer identity thay đổi có thể ảnh hưởng phạm vi bảo đảm.
- Broker transaction có thể atomically ghi nhiều message hoặc phối hợp offset trong một số luồng Kafka, nhưng không tự bao trùm một database transaction bên ngoài.
- Consumer có thể nhận lại message sau khi xử lý xong nhưng offset chưa commit.
- Hiệu ứng ghi sang database hoặc gọi HTTP bên ngoài vẫn cần idempotency.

Vì vậy, producer idempotence là lớp bảo vệ hữu ích nhưng không thay thế inbox/deduplication ở consumer. Hãy mô tả chính xác phạm vi bảo đảm của broker thay vì gọi toàn hệ thống là exactly-once.

## 17. Schema event, version và tương thích

Outbox là nơi lưu payload sẽ được giao sau commit. Relay có thể chạy chậm hơn nhiều so với transaction tạo event, vì vậy payload cần có hợp đồng ổn định.

Nên cân nhắc:

- **event_type** định danh rõ loại sự kiện.
- **schema_version** cho biết cấu trúc payload.
- **event_id** ổn định qua mọi lần gửi lại.
- **aggregate_id** và **aggregate_version** để xử lý thứ tự.
- Thời điểm xảy ra nghiệp vụ tách biệt với thời điểm relay publish.
- Trường correlation/causation để theo dõi chuỗi xử lý.
- Chính sách tương thích khi thêm, bỏ hoặc đổi tên trường.

Consumer nên bỏ qua field bổ sung không ảnh hưởng hợp đồng hoặc xử lý schema version rõ ràng. Không nên tái sử dụng cùng event type cho một payload có ý nghĩa hoàn toàn khác.

Nếu cần sửa một sự kiện đã publish, hãy phát event hiệu chỉnh hoặc command mới có liên kết với event trước. Không chỉnh sửa bản ghi đã gửi rồi kỳ vọng các consumer cũ tự nhận ra nội dung đã đổi.

## 18. Retention và dọn dẹp outbox

Outbox có thể tăng không giới hạn nếu relay chỉ đánh dấu published nhưng không có chính sách retention.

Có thể giữ các event đã gửi trong một khoảng thời gian để phục vụ audit, điều tra và replay. Sau đó, job cleanup xóa hoặc archive các bản ghi cũ.

Trước khi cleanup, xác định:

- Broker đã xác nhận event theo mức durability yêu cầu chưa?
- Consumer có cần khả năng replay từ outbox không?
- CDC connector đã checkpoint vượt qua bản ghi chưa?
- Có yêu cầu audit hoặc đối soát không?
- Có consumer chậm cần event cũ không?
- Deduplication record ở consumer được giữ bao lâu?
- Có thể phục hồi từ backup mà không gửi lại event đã xử lý không?

Retention của inbox cũng quan trọng. Nếu xóa deduplication record trong khi broker vẫn có thể replay event cũ, event đó có thể được áp dụng lại. Thời hạn inbox nên dài ít nhất bằng khoảng thời gian hệ thống cho phép replay hoặc redelivery, cộng thêm biên an toàn theo nghiệp vụ.

Nếu cần replay vô thời hạn, cần lưu dấu idempotency bền vững hơn hoặc thiết kế thao tác consumer có thể tái áp dụng an toàn.

## 19. Observability: theo dõi từ outbox đến consumer

Một event có thể đi qua nhiều thành phần. Chỉ đo số row **published_at IS NULL** là chưa đủ để biết nó đang bị kẹt ở đâu.

### Metrics phía relay

Theo dõi:

- Số event chưa publish.
- Tuổi của event chưa publish lâu nhất.
- Outbox backlog theo tenant hoặc event type.
- Số event được claim mỗi batch.
- Số lần publish thành công/thất bại.
- Số lease hết hạn và claim lại.
- Số event chuyển dead-letter.
- Thời gian từ **created_at** đến broker ACK.
- Tỷ lệ duplicate ước tính nếu có telemetry phù hợp.

### Metrics phía broker/consumer

Theo dõi:

- Producer send latency và ACK failures.
- Consumer lag hoặc queue depth.
- Số message redelivery.
- Số event bị deduplicate.
- Số lần consumer retry.
- Thời gian xử lý event.
- Số poison event và DLQ depth.
- Tỷ lệ lỗi theo event type/schema version.

### Correlation

Gắn **event_id**, **aggregate_id**, **correlation_id** và **causation_id** vào log/trace. Khi điều tra một order, có thể lần theo:

~~~text
Order transaction
   -> outbox event_id
   -> relay attempt
   -> broker message
   -> consumer inbox record
   -> downstream transaction
~~~

Không ghi payload nhạy cảm đầy đủ vào log chỉ để debug. Dùng id và metadata đủ để truy vết, rồi truy cập dữ liệu có kiểm soát khi cần.

## 20. Kiểm thử các cửa sổ lỗi quan trọng

Một bài kiểm thử outbox phải mô phỏng process dừng ở các thời điểm khác nhau, không chỉ kiểm tra happy path.

| Điểm dừng giả lập | Kết quả cần xác nhận |
|---|---|
| Trước commit transaction nghiệp vụ | Không có business change và không có outbox event đã commit |
| Sau commit, trước relay claim | Event còn trong outbox và worker sau có thể claim |
| Sau claim, trước publish | Lease hết hạn và worker khác claim lại |
| Broker nhận message, ACK bị mất | Relay có thể gửi lại cùng event_id; consumer dedup |
| Broker ACK, process chết trước **published_at** | Event có thể được gửi lặp; không mất hiệu ứng nghiệp vụ |
| **published_at** đã commit | Relay bình thường không gửi lại event |
| Consumer chết trước transaction commit | Inbox và business effect rollback; broker redeliver |
| Consumer commit, chết trước ACK | Broker redeliver; inbox nhận duplicate và bỏ qua effect |
| Hai consumer worker nhận cùng event | UNIQUE inbox chỉ cho một transaction áp dụng effect |
| Event poison | Được retry có giới hạn, cách ly và cảnh báo |
| Event đến sai thứ tự | Version/order policy phát hiện gap hoặc event cũ |
| CDC connector dừng lâu | Offset/log retention đủ để tiếp tục; có thể có duplicate nhưng không mất event |

Dùng fault injection hoặc test harness có thể dừng process sau các bước publish/commit/ack. Không dựa vào **sleep** cố định để tạo race; dùng barrier hoặc hook test để điều khiển thời điểm.

### Kiểm tra duplicate song song

Tạo hai consumer connection cùng nhận một event_id và cùng cố INSERT inbox. Xác nhận:

- Chỉ một transaction tạo được inbox record.
- Chỉ transaction thắng thực hiện business effect.
- Transaction còn lại xác định đây là duplicate.
- Nếu transaction thắng rollback, transaction còn lại có thể tiếp tục xử lý theo kết quả UNIQUE conflict.
- Không có trường hợp inbox commit nhưng business effect không commit cùng.

## 21. Quy trình replay và sửa sự kiện lỗi

Khi một event vào DLQ hoặc trạng thái parked, cần quy trình vận hành rõ ràng:

1. Xác định event_id, aggregate, event type và schema version.
2. Tìm lỗi đầu tiên và số lần retry.
3. Xác định lỗi thuộc payload, cấu hình, broker hay consumer.
4. Sửa nguyên nhân gốc trước khi replay.
5. Replay với cùng event_id nếu đó vẫn là cùng một sự kiện gốc.
6. Đảm bảo consumer deduplication record và trạng thái hiện tại cho phép replay an toàn.
7. Theo dõi kết quả downstream và đối soát dữ liệu.

Nếu consumer đã áp dụng event nhưng ACK bị mất, inbox sẽ nhận diện event_id cũ và bỏ qua. Nếu operator tạo event_id mới cho cùng payload để “thử lại”, consumer có thể áp dụng hiệu ứng lần thứ hai.

Nếu cần sửa dữ liệu đã xử lý, hãy tạo một command hoặc compensating event mới với định danh mới và quan hệ causation rõ ràng. Không xóa inbox record để ép cùng event chạy lại trừ khi đã chứng minh an toàn và có quy trình kiểm soát.

## 22. Các lỗi thiết kế thường gặp

### Đánh dấu published trước khi broker ACK

Process có thể chết trước khi gửi. Outbox mất dấu sự kiện cần giao và downstream không bao giờ nhận được.

### Publish rồi không deduplicate

Relay có thể gửi lặp sau khi ACK thành công nhưng database chưa kịp cập nhật. Consumer có thể cộng tiền, tạo đơn hoặc gửi thông báo hai lần.

### Tạo event_id mới mỗi lần retry

Consumer không thể nhận diện các bản giao cùng một sự kiện. ID phải được tạo khi ghi outbox và giữ nguyên.

### Commit inbox riêng trước business effect

Process có thể chết sau khi inbox commit nhưng trước khi thay đổi nghiệp vụ. Lần redelivery bị bỏ qua dù effect chưa được áp dụng. Hai thao tác phải cùng transaction.

### ACK broker trước database commit

Message có thể bị broker xóa trước khi consumer lưu effect. Nếu process chết, dữ liệu downstream bị mất.

### Giữ transaction mở trong lúc publish

Network call kéo dài làm transaction giữ connection/lock lâu và tăng contention. Claim batch trong transaction ngắn, commit rồi publish ngoài transaction.

### Lease hết hạn nhưng worker cũ vẫn chạy

Hai worker có thể publish cùng event. Lease và fencing token bảo vệ trạng thái claim; consumer idempotency vẫn cần thiết để bảo vệ effect.

### Xóa outbox hoặc inbox quá sớm

Event có thể không còn nguồn replay, hoặc duplicate cũ được áp dụng lại sau khi dedup record bị xóa. Retention phải khớp với khả năng redelivery, replay và audit.

### Gọi hệ thống ngoài mà không có idempotency

Inbox không thể rollback một thanh toán hoặc email đã được provider xử lý. Dùng idempotency key của provider, outbox tiếp theo và reconciliation.

## 23. Quy trình thiết kế outbox relay và consumer

1. **Ghi event cùng thay đổi nghiệp vụ**: INSERT outbox trong cùng database transaction.
2. **Tạo event_id ổn định**: giữ nguyên ID và payload qua mọi lần retry.
3. **Chọn relay**: polling với claim/lease hoặc CDC theo khả năng vận hành.
4. **Claim ngắn**: lấy batch, đặt lease/fencing token rồi commit trước network call.
5. **Publish và chờ ACK**: chỉ đánh dấu published sau xác nhận phù hợp từ broker.
6. **Chấp nhận at-least-once**: thiết kế để event có thể giao lặp.
7. **Deduplicate tại consumer**: UNIQUE inbox key và business effect trong cùng transaction.
8. **ACK sau commit**: nếu process chết trước ACK, redelivery phải an toàn.
9. **Bảo vệ side effect ngoài DB**: idempotency key, consumer outbox hoặc saga.
10. **Quản lý ordering**: partition key, aggregate version và chính sách xử lý gap.
11. **Retry có giới hạn**: backoff/jitter, DLQ hoặc parking, cảnh báo poison event.
12. **Retention và replay**: giữ outbox/inbox đủ lâu, có quy trình replay không tạo hiệu ứng trùng.
13. **Quan sát end-to-end**: event age, backlog, publish ACK, duplicate, consumer lag và DLQ.
14. **Kiểm thử fault window**: dừng process tại các điểm commit/publish/ACK để chứng minh không mất event và duplicate không lặp effect.

Outbox bảo đảm thay đổi nghiệp vụ và ý định phát sự kiện cùng commit trong database. Relay chuyển ý định đó tới broker bằng cơ chế có thể phục hồi, nhưng cửa sổ giữa broker ACK và cập nhật trạng thái outbox khiến giao nhận lặp là điều bình thường. Consumer cần ghi nhận event_id và áp dụng hiệu ứng database trong cùng transaction, rồi mới ACK broker. Khi kết hợp idempotency cho side effect bên ngoài, ordering theo aggregate, retry có giới hạn và quan sát end-to-end, hệ thống có thể xử lý duplicate an toàn mà vẫn tránh mất sự kiện đã commit.
