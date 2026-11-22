# Giữ giao dịch mở trong lúc gọi mạng hoặc chờ tương tác

Một transaction database được thiết kế để gom các thay đổi dữ liệu liên quan thành một đơn vị nguyên tử: hoặc tất cả commit, hoặc tất cả rollback. Một lỗi thiết kế phổ biến là mở transaction, cập nhật dữ liệu rồi giữ transaction trong khi ứng dụng gọi HTTP, chờ message broker, gọi dịch vụ thanh toán hoặc chờ người dùng xác nhận. Những hoạt động này có thời gian hoàn tất khó dự đoán và không nằm dưới quyền điều khiển của transaction database thông thường.

Giữ transaction mở trong lúc chờ bên ngoài làm connection và tài nguyên giao dịch bị chiếm dụng lâu hơn cần thiết. Nếu transaction đã lấy khóa, các giao dịch khác có thể bị chặn. Nếu request mạng timeout, database rollback cũng không thể tự hoàn tác tác động mà dịch vụ bên ngoài đã thực hiện. Nếu ứng dụng chờ người dùng nhập liệu, transaction có thể tồn tại hàng chục giây hoặc vài phút dù database không làm việc hữu ích.

Nguyên tắc thiết kế là **giữ transaction ngắn và chỉ bao quanh các thao tác database cần cùng commit**. Hãy hoàn tất transaction trước khi chờ mạng hoặc tương tác người dùng; nếu quy trình cần nhiều bước, lưu trạng thái trung gian và tiếp tục bằng transaction mới, outbox hoặc Saga.

## 1. Vì sao transaction nên ngắn?

Khi transaction bắt đầu, transaction manager có thể lấy connection ngay hoặc lấy connection khi câu SQL đầu tiên được thực thi, tùy framework và cấu hình. Sau khi tài nguyên database được sử dụng, transaction có thể giữ:

- Connection từ connection pool.
- Khóa hàng, khóa trang, khóa bảng, khóa chỉ mục hoặc khóa phạm vi tùy câu lệnh và isolation level.
- Snapshot hoặc thông tin phiên bản dữ liệu cần giữ để bảo đảm ngữ nghĩa đọc.
- Transaction log, undo record hoặc version record cần thiết cho rollback và phục hồi.
- Trạng thái transaction trong transaction manager, driver và database session.

Một transaction chỉ chạy SQL trong 20 ms nhưng chờ HTTP trong 5 giây vẫn có thể giữ connection và các khóa đã lấy trong gần 5 giây. Thời gian chờ không làm transaction tự giải phóng tài nguyên.

Ví dụ:

```text
BEGIN
  UPDATE account ...             20 ms, lấy khóa
  gọi Payment API                5 giây, vẫn giữ transaction
  UPDATE payment_record ...      15 ms
COMMIT

Tổng thời gian transaction: khoảng 5 giây
Thời gian thực sự chạy SQL: khoảng 35 ms
```

Khoảng chờ 5 giây có thể khiến các giao dịch khác cần cùng hàng phải đợi. Một connection cũng bị giữ khỏi pool trong toàn bộ khoảng đó, làm giảm số connection còn sẵn sàng phục vụ request khác.

## 2. Gọi mạng trong transaction tạo ra những rủi ro gì?

Một lời gọi mạng có thể gặp nhiều trạng thái mà ứng dụng không dự đoán chính xác:

- Dịch vụ đích phản hồi nhanh, chậm hoặc không phản hồi.
- DNS, TCP, TLS hoặc quá trình xác thực gặp lỗi.
- Dịch vụ đích xử lý thành công nhưng phản hồi bị mất trên đường về.
- Dịch vụ đích trả lỗi tạm thời, lỗi nghiệp vụ hoặc giới hạn tốc độ.
- Client timeout và ngừng chờ trong khi server đích vẫn tiếp tục xử lý.
- Retry tạo ra một yêu cầu thứ hai trong khi kết quả của yêu cầu đầu chưa rõ.

Database transaction không điều khiển được vòng đời của lời gọi HTTP thông thường. Nếu HTTP call đã thu tiền thành công rồi ứng dụng nhận timeout, lệnh `ROLLBACK` chỉ hoàn tác thay đổi thuộc database transaction hiện tại. Nó không thể tự hoàn tiền ở cổng thanh toán.

### Timeline: database rollback nhưng tác động bên ngoài vẫn còn

```text
Ứng dụng / Database                 Payment Service
----------------------------------------------------------------
BEGIN
UPDATE orders -> PAYMENT_PENDING
                                    nhận yêu cầu charge
                                    charge thành công
                                    trả kết quả
Ứng dụng gặp lỗi trước COMMIT
ROLLBACK

Database: thay đổi đơn hàng bị rollback
Payment: khoản charge vẫn tồn tại
```

Hệ thống có thể rơi vào trạng thái không khớp: khách hàng đã bị thu tiền nhưng đơn hàng vẫn ở trạng thái cũ. Đây không phải lỗi mà transaction database có thể tự giải quyết.

### Timeline: timeout nhưng kết quả remote không rõ

```text
Ứng dụng                         Dịch vụ bên ngoài
--------------------------------------------------------------
Gửi POST /payments
                                 nhận request
                                 xử lý và commit thanh toán
                                 gửi response
Client timeout trước khi nhận response
```

Ứng dụng không thể kết luận thanh toán thất bại chỉ vì client timeout. Nếu gửi lại bằng một yêu cầu mới, khách hàng có thể bị charge hai lần. Cần idempotency key ổn định và cơ chế tra cứu trạng thái giao dịch.

## 3. Giữ khóa trong lúc chờ làm tăng lock contention

Giả sử transaction T1 cập nhật trạng thái đơn hàng rồi gọi dịch vụ vận chuyển trong khi vẫn mở transaction. T2 cần cập nhật cùng đơn hàng hoặc đọc bằng chế độ cần khóa tương thích không được cấp ngay.

```text
T1                                      T2
----------------------------------------------------------------
BEGIN
UPDATE orders, giữ khóa
Gọi Shipping API
  (chờ 4 giây)                          BEGIN
                                        UPDATE orders
                                        Chờ khóa của T1
Shipping API trả kết quả
UPDATE orders
COMMIT
                                        Được cấp khóa, tiếp tục
```

Trong lúc T1 chờ mạng, T2 không thể tiến lên. Nếu có nhiều request cùng làm việc này, hàng đợi lock wait tăng, thời gian phản hồi p95/p99 tăng và connection pool có thể cạn.

Tình trạng có thể nghiêm trọng hơn nếu transaction giữ nhiều khóa theo các thứ tự khác nhau. Một giao dịch chờ dịch vụ bên ngoài trong khi giữ khóa A; giao dịch khác giữ khóa B và cần A; giao dịch đầu lại cần B sau khi remote call hoàn tất. Các phụ thuộc đó có thể tạo deadlock.

Không phải mọi transaction mở lâu đều tạo lock wait. Một transaction chỉ đọc hoặc chưa lấy khóa xung đột có thể không chặn writer theo cách đó. Tuy nhiên, transaction dài vẫn có chi phí về connection, snapshot, version retention và vận hành; cần đánh giá theo loại thao tác và isolation level.

## 4. Connection pool bị chiếm dụng dù database không bận

Connection pool có số lượng connection hữu hạn. Nếu mỗi request giữ một connection trong lúc chờ HTTP, số request đồng thời có thể nhanh chóng chiếm hết pool.

Ví dụ pool có 20 connection:

| Tình huống | Connection đang bị giữ | Connection còn trống |
|---|---:|---:|
| 5 request chạy SQL ngắn | 5 | 15 |
| 20 request đều chờ API bên ngoài trong transaction | 20 | 0 |
| Request thứ 21 cần query nhanh | Phải chờ pool | 0 |

Database có thể vẫn còn CPU và I/O, nhưng ứng dụng không lấy được connection để gửi truy vấn mới. Tăng pool size có thể trì hoãn triệu chứng nhưng không giải quyết nguyên nhân; nếu database có giới hạn session hoặc tải cao, tăng pool còn làm tình trạng tệ hơn.

Hãy theo dõi:

- `active`, `idle`, `pending` và `max` của pool.
- Thời gian acquire connection và thời gian giữ connection.
- Thời gian transaction từ lúc bắt đầu đến commit/rollback.
- Thời gian gọi HTTP hoặc message broker nằm bên trong transaction.
- Stack trace của connection bị giữ lâu nếu pool hỗ trợ leak detection.

## 5. Chờ người dùng trong transaction còn nguy hiểm hơn

Thời gian phản hồi của con người không có giới hạn ổn định. Một biểu mẫu có thể được mở trong vài phút; người dùng có thể đọc lại thông tin, chuyển tab, hỏi người khác hoặc bỏ dở.

Không nên thực hiện quy trình sau:

```text
BEGIN
  SELECT account FOR UPDATE
  hiển thị dữ liệu cho người dùng
  chờ người dùng xác nhận
  UPDATE account
COMMIT
```

Transaction và khóa có thể tồn tại trong suốt thời gian người dùng suy nghĩ. Các request khác bị chặn, connection pool bị chiếm dụng và database giữ snapshot/transaction lâu hơn cần thiết.

Thay vào đó, hãy tách thành hai request hoặc hai giai đoạn:

1. Đọc dữ liệu và trả về cho giao diện, không giữ transaction sau khi response hoàn tất.
2. Khi người dùng xác nhận, mở transaction mới, kiểm tra dữ liệu còn hợp lệ và thực hiện cập nhật.

Vì dữ liệu có thể thay đổi giữa hai giai đoạn, cần kiểm tra phiên bản hoặc điều kiện nghiệp vụ khi lưu. Optimistic locking là lựa chọn phổ biến cho biểu mẫu chỉnh sửa kéo dài.

## 6. Ví dụ sai trong Spring: gọi REST API bên trong @Transactional

Đoạn mã sau giữ transaction database trong suốt thời gian gọi Payment API:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final PaymentClient paymentClient;
    private final PaymentRecordRepository paymentRecords;

    @Transactional
    public void checkout(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.markPaymentPending();

        // Network call chạy trong transaction đang mở.
        PaymentResult result = paymentClient.charge(
            order.getCustomerId(),
            order.getTotalAmount()
        );

        paymentRecords.save(PaymentRecord.from(order, result));
        order.markPaid(result.paymentId());
    }
}
```

Vấn đề của đoạn mã:

- Connection và các khóa đã lấy có thể bị giữ trong lúc `paymentClient.charge` chờ mạng.
- Nếu Payment API thành công nhưng `paymentRecords.save` hoặc commit database thất bại, khoản thanh toán không được hoàn tác tự động.
- Nếu client timeout nhưng Payment API đã xử lý, retry có thể charge lần nữa.
- Nếu API chậm, các request checkout khác có thể chờ connection hoặc khóa lâu.
- Transaction timeout ở database không tự hủy hay bù tác động ở Payment API.

`@Transactional` chỉ quản lý các resource được transaction manager hiện tại hỗ trợ. Nó không biến REST call thành participant trong cùng database transaction.

## 7. Tách orchestration khỏi các transaction cục bộ

Một cách tổ chức đơn giản hơn là để lớp orchestration không giữ transaction xuyên suốt. Mỗi service chuyên trách thực hiện một transaction ngắn; lời gọi mạng nằm giữa các transaction đó.

```java
@Service
public class CheckoutApplicationService {
    private final OrderTransactionService orderTransactions;
    private final PaymentClient paymentClient;

    public void checkout(long orderId) {
        // Method trả về sau khi transaction tạo trạng thái chờ đã commit.
        PaymentRequest request = orderTransactions.preparePayment(orderId);

        // Không có transaction database của preparePayment đang mở ở đây.
        PaymentResult result = paymentClient.charge(
            request.customerId(),
            request.amount(),
            request.idempotencyKey()
        );

        // Mở transaction mới để ghi kết quả.
        orderTransactions.recordPaymentResult(orderId, result);
    }
}

@Service
public class OrderTransactionService {
    private final OrderRepository orders;

    @Transactional
    public PaymentRequest preparePayment(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.markPaymentPending();
        return PaymentRequest.from(order);
    }

    @Transactional
    public void recordPaymentResult(long orderId, PaymentResult result) {
        Order order = orders.findById(orderId).orElseThrow();
        order.applyPaymentResult(result);
    }
}
```

Ở đây `CheckoutApplicationService` điều phối quy trình. `preparePayment` và `recordPaymentResult` là hai transaction riêng. Sau khi `preparePayment` trả về qua Spring proxy, transaction đầu đã hoàn tất trước khi ứng dụng gọi mạng.

Ví dụ giả định các phương thức transaction được gọi qua Spring proxy từ bean khác. Trong proxy mode, self-invocation như `this.preparePayment()` có thể bỏ qua transaction advice. Nếu cần ranh giới tường minh, có thể dùng `TransactionTemplate`.

Nếu Payment API trả lỗi hoặc timeout, đơn hàng vẫn ở trạng thái trung gian `PAYMENT_PENDING`. Một worker có thể retry cùng idempotency key hoặc tra cứu kết quả. Khi xác định thất bại cuối cùng, một transaction mới cập nhật đơn thành `PAYMENT_FAILED` hoặc bắt đầu compensation theo nghiệp vụ.

## 8. Tránh khoảng trống dual-write bằng Transactional Outbox

Nếu sau khi ghi database cần phát một sự kiện hoặc yêu cầu worker gọi dịch vụ bên ngoài, không nên làm hai thao tác độc lập theo thứ tự:

```text
UPDATE orders ...
COMMIT
PUBLISH OrderPaymentRequested
```

Nếu process chết sau commit nhưng trước publish, sự kiện bị mất. Nếu publish trước commit rồi transaction rollback, consumer nhận một sự kiện về thay đổi chưa được xác nhận.

Transactional Outbox ghi thay đổi nghiệp vụ và sự kiện cần phát trong cùng local transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'PAYMENT_PENDING'
WHERE id = 9001;

INSERT INTO outbox_event
    (event_id, aggregate_id, event_type, payload, created_at)
VALUES
    ('evt-payment-9001', 9001, 'PaymentRequested',
     '{"orderId":9001}', CURRENT_TIMESTAMP);

COMMIT;
```

Sau commit, relay đọc outbox và phát message. Worker nhận message, gọi Payment API ngoài transaction database, rồi mở transaction riêng để ghi kết quả.

```text
Local transaction
  cập nhật order -> PAYMENT_PENDING
  ghi outbox event
COMMIT
      |
      v
Outbox relay publish event
      |
      v
Payment worker nhận event
      |
      +-- gọi Payment API ngoài transaction
      |
      v
Local transaction ghi kết quả
```

Relay có thể publish lặp nếu chết sau khi publish nhưng trước khi đánh dấu event đã gửi. Vì vậy, consumer và Payment API cần xử lý idempotency. Outbox bảo đảm thay đổi database và ý định phát sự kiện được lưu nguyên tử; nó không tạo một transaction XA giữa database và broker.

## 9. Sau commit callback: hữu ích nhưng không bảo đảm bền vững

Spring có thể chạy listener sau khi transaction commit thành công:

```java
@Component
public class OrderEventListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        // Chạy sau khi transaction phát event đã commit.
        notificationClient.notifyOrderCreated(event.orderId());
    }
}
```

Cách này tránh gọi notification service khi transaction cha còn mở. Nếu transaction rollback, listener ở phase `AFTER_COMMIT` không chạy.

Tuy nhiên, callback sau commit thường chỉ là cơ chế dispatch trong process. Nếu process chết sau commit nhưng trước khi callback hoàn tất, sự kiện có thể không được xử lý. Nếu việc phát sự kiện phải bền vững, dùng outbox. Callback sau commit phù hợp với tác vụ best-effort hoặc để đánh thức một worker có dữ liệu bền vững đang chờ xử lý.

Nếu listener cần ghi database, hãy mở transaction phù hợp trong listener/service được gọi. Transaction gốc đã kết thúc; không giả định nó vẫn có thể được tham gia.

## 10. Chờ người dùng: dùng optimistic locking

Với biểu mẫu chỉnh sửa, hãy trả về version cùng dữ liệu. Khi người dùng gửi thay đổi, câu lệnh cập nhật chỉ thành công nếu version chưa thay đổi.

Ví dụ bảng:

```sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    address VARCHAR(300),
    version BIGINT NOT NULL DEFAULT 0
);
```

Khi tải biểu mẫu:

```sql
SELECT id, display_name, address, version
FROM customer_profile
WHERE id = 42;
```

Giả sử giao diện nhận `version = 7`. Khi người dùng lưu, mở transaction ngắn và cập nhật có điều kiện:

```sql
UPDATE customer_profile
SET display_name = :display_name,
    address = :address,
    version = version + 1
WHERE id = 42
  AND version = 7;
```

- Nếu ảnh hưởng một hàng, lưu thành công.
- Nếu ảnh hưởng không hàng nào, dữ liệu đã bị thay đổi hoặc bản ghi không còn tồn tại. Ứng dụng tải lại dữ liệu và yêu cầu người dùng xem xét xung đột.

Không giữ `SELECT ... FOR UPDATE` trong lúc người dùng đang mở biểu mẫu. Optimistic check chuyển thời gian chờ từ database sang bước xác nhận khi lưu, không giữ connection hoặc khóa suốt thời gian người dùng suy nghĩ.

Trong JPA, có thể dùng `@Version` để ORM tạo điều kiện kiểm tra phiên bản và báo `OptimisticLockException` khi phát hiện xung đột:

```java
@Entity
public class CustomerProfile {
    @Id
    private Long id;

    @Version
    private long version;

    private String displayName;
    private String address;
}
```

Ứng dụng cần xử lý optimistic lock conflict ở ranh giới transaction và phản hồi phù hợp cho người dùng; không tự động ghi đè dữ liệu mới bằng toàn bộ biểu mẫu cũ.

## 11. Tác vụ dài nên dùng trạng thái và worker, không dùng transaction kéo dài

Một quy trình có thể mất nhiều giây hoặc nhiều phút nên được mô hình hóa thành trạng thái bền vững:

```text
PENDING
   |
   v
RUNNING
   |
   +-- thành công --> SUCCEEDED
   |
   +-- lỗi tạm thời --> RETRY_WAIT --> RUNNING
   |
   +-- lỗi vĩnh viễn --> FAILED
   |
   +-- kết quả bên ngoài chưa rõ --> RECONCILIATION_REQUIRED
```

Transaction database chỉ được dùng để chuyển trạng thái và ghi nhận kết quả ngắn. Worker thực hiện phần công việc bên ngoài sau khi transaction claim đã commit. Nếu worker chết, lease hoặc job scheduler có thể đưa công việc trở lại hàng đợi.

Với quy trình qua nhiều dịch vụ, mỗi bước có local transaction và trạng thái riêng. Nếu bước sau thất bại sau khi bước trước đã commit, Saga chạy thao tác bù hoặc chuyển sang manual review. Không giữ một transaction database mở xuyên toàn bộ workflow.

## 12. Không đợi Future trong khi vẫn giữ khóa

Một biến thể khác của anti-pattern là submit công việc bất đồng bộ rồi gọi `get()` hoặc `join()` trong khi transaction cha vẫn mở:

```java
@Transactional
public void updateOrder(long orderId) {
    orderRepository.updateStatus(orderId, "PROCESSING");

    CompletableFuture<Void> future = CompletableFuture.runAsync(
        () -> auditService.write(orderId), executor
    );

    future.join(); // Caller vẫn giữ transaction trong lúc chờ.
}
```

Worker có thể cần đọc hoặc cập nhật cùng hàng mà transaction cha đang khóa. Caller chờ worker; worker lại chờ caller nhả khóa. Tình huống này có thể tạo blocking cycle hoặc timeout dù không có hai câu SQL trong cùng thread.

Ngay cả khi worker không cần khóa của caller, việc `join()` vẫn giữ transaction và connection trong suốt thời gian worker thực hiện. Nếu kết quả async không cần thiết cho commit hiện tại, hãy phát công việc sau commit qua outbox hoặc callback phù hợp. Nếu kết quả phải thuộc cùng atomic unit, thực hiện thao tác database đồng bộ trong cùng transaction thay vì tách sang thread độc lập.

## 13. Nếu buộc phải gọi mạng trong một quy trình có transaction?

Có trường hợp nghiệp vụ cần kiểm tra hoặc đặt chỗ từ dịch vụ ngoài trước khi xác nhận database. Khi đó, hãy thiết kế các bước rõ ràng thay vì giữ transaction database mở để chờ.

Một số hướng:

- **Đọc trước, xác minh sau:** lấy dữ liệu cần thiết trong transaction đọc ngắn, commit, gọi dịch vụ ngoài, sau đó mở transaction mới và kiểm tra lại điều kiện trước khi ghi. Cần xử lý thay đổi đồng thời giữa hai giai đoạn.
- **Reservation/lease:** tạo một reservation có thời hạn trong database, commit, gọi dịch vụ ngoài; nếu hết hạn hoặc thất bại thì giải phóng reservation bằng transaction mới.
- **Authorization rồi capture:** với thanh toán, nếu cổng hỗ trợ, có thể authorize trước rồi chỉ capture sau khi các điều kiện nội bộ đã sẵn sàng; nếu thất bại, void authorization. Đây là quy trình nghiệp vụ, không phải rollback SQL.
- **Saga:** ghi trạng thái từng bước và chạy compensation khi cần.
- **Distributed transaction:** chỉ cân nhắc khi mọi resource thực sự hỗ trợ XA/JTA hoặc giao thức distributed commit và yêu cầu atomic commit đủ mạnh để chấp nhận chi phí. REST API thông thường không tự tham gia 2PC.

Không nên biến timeout dài hoặc connection pool lớn thành cách giữ transaction trong lúc chờ. Nếu nghiệp vụ không thể chấp nhận trạng thái trung gian, hãy xem xét lại giao thức giữa các hệ thống hoặc dùng một resource manager có hỗ trợ transaction chung.

## 14. Timeout và retry cho lời gọi bên ngoài

Khi lời gọi mạng nằm ngoài transaction database, nó vẫn cần giới hạn thời gian và chính sách retry:

- Đặt connect timeout, response/read timeout và deadline tổng cho request.
- Giới hạn số lần retry và dùng exponential backoff kèm jitter.
- Chỉ retry lỗi được xem là tạm thời; không retry lỗi nghiệp vụ hoặc dữ liệu không hợp lệ.
- Dùng idempotency key ổn định cho cùng một operation qua mọi lần thử.
- Nếu timeout khiến kết quả không rõ, tra cứu trạng thái theo idempotency key hoặc business reference trước khi gửi yêu cầu mới.
- Ghi attempt, error category, thời gian, correlation ID và final outcome.
- Không retry vô hạn; chuyển sang hàng đợi lỗi hoặc reconciliation khi hết ngân sách.

Ví dụ:

```text
Payment request với idempotency key = order-9001-charge
       |
       +-- response thành công --> ghi kết quả trong transaction mới
       |
       +-- lỗi tạm thời rõ ràng --> retry cùng key sau backoff
       |
       +-- timeout, kết quả không rõ
               |
               +-- query trạng thái theo key
                       |
                       +-- đã charge --> ghi nhận thành công
                       +-- chưa charge --> retry cùng key
                       +-- chưa xác định --> reconciliation
```

## 15. Quan sát transaction bị mở quá lâu

Để tìm anti-pattern này trong hệ thống, theo dõi:

- Transaction age: thời gian từ lúc bắt đầu đến commit/rollback.
- Thời gian connection được giữ từ pool.
- Thời gian HTTP/RPC call và liệu span đó nằm bên trong transaction span hay không.
- Session `idle in transaction` hoặc transaction mở nhưng không chạy statement.
- Lock wait duration, blocking chain và số waiter trên blocker.
- Connection pool `active`, `pending`, `acquire time` và `usage time`.
- Tỷ lệ transaction timeout, lock timeout và deadlock.
- Số request đang chờ user interaction trong khi connection/transaction vẫn mở.

Trong PostgreSQL, `pg_stat_activity` có thể cho biết `xact_start`, `state` và `state = 'idle in transaction'`. Trong SQL Server, có thể xem transaction age qua các DMV về transaction/session. Ở tầng ứng dụng, tracing nên có span riêng cho database transaction và remote call để thấy remote call có kéo dài transaction hay không.

Một transaction dài không tự động là lỗi; batch lớn có thể cần thời gian. Hãy xem thời gian giữ khóa, connection, snapshot và ảnh hưởng tới workload khác, rồi xác định có thể chia nhỏ hoặc chuyển công việc ra ngoài transaction không.

## 16. Kiểm thử tình huống chờ mạng hoặc người dùng

Có thể kiểm thử anti-pattern bằng cách làm cho remote call chậm có kiểm soát trong môi trường thử nghiệm:

1. Tạo một transaction cập nhật hàng và giữ transaction mở.
2. Chèn một HTTP call giả lập có độ trễ vài giây.
3. Từ session khác, thử cập nhật cùng hàng.
4. Quan sát lock wait, transaction age, connection pool active và request latency.
5. Chuyển HTTP call ra ngoài transaction, chạy lại và so sánh.

Với biểu mẫu người dùng, mô phỏng khoảng thời gian giữa GET và POST bằng hai request độc lập. Cập nhật bằng version cũ sau khi một request khác đã thay đổi dữ liệu; ứng dụng cần trả conflict thay vì giữ khóa trong suốt khoảng thời gian người dùng suy nghĩ.

Kiểm thử cả các trường hợp lỗi:

- Remote call trả lỗi trước khi tạo tác động.
- Remote call thành công nhưng response bị mất.
- Database commit thất bại sau remote success.
- Worker chết sau khi nhận message nhưng trước khi ghi kết quả.
- Cùng một event hoặc request được giao lại nhiều lần.
- Người dùng gửi lại form với version cũ.

## 17. Các lỗi thiết kế thường gặp

- **Mở transaction trước khi gọi HTTP:** connection và khóa có thể bị giữ trong suốt thời gian mạng chậm.
- **Chờ người dùng xác nhận trong transaction:** thời gian suy nghĩ của người dùng làm transaction tồn tại không giới hạn thực tế.
- **Tin rằng rollback database hoàn tác REST call:** remote side effect cần compensation hoặc quy trình nghiệp vụ riêng.
- **Gọi async rồi `join()` trong transaction:** caller vẫn giữ connection/khóa trong lúc chờ worker.
- **Phát message trước commit:** consumer có thể xử lý dữ liệu chưa được xác nhận.
- **Phát message sau commit mà không outbox:** process có thể chết giữa commit và publish.
- **Retry bằng idempotency key mới:** dịch vụ đích có thể coi mỗi lần thử là một operation mới.
- **Tách transaction nhưng không kiểm tra trạng thái:** dữ liệu có thể thay đổi giữa các giai đoạn và kết quả cũ không còn hợp lệ.
- **Dùng callback after-commit như cơ chế bền vững:** process crash có thể làm mất công việc chưa được dispatch.
- **Giữ transaction để có cảm giác workflow nguyên tử:** transaction local không bao trùm dịch vụ ngoài nếu chúng không tham gia giao thức transaction chung.

## 18. Quy trình thiết kế an toàn

1. **Xác định phần cần atomic:** liệt kê chính xác các thay đổi database phải cùng commit hoặc rollback.
2. **Đặt ranh giới transaction nhỏ:** chỉ bao quanh các thao tác database cần thiết.
3. **Đưa mạng ra ngoài:** gọi HTTP, RPC, broker và dịch vụ ngoài sau khi transaction đã kết thúc.
4. **Không giữ transaction qua tương tác người dùng:** đọc dữ liệu, trả response, rồi mở transaction mới khi người dùng xác nhận.
5. **Bảo vệ dữ liệu thay đổi giữa các bước:** dùng version check, điều kiện cập nhật, reservation hoặc constraint.
6. **Lưu trạng thái trung gian:** ví dụ `PENDING`, `PAYMENT_PENDING`, `PROCESSING` để có thể tiếp tục hoặc phục hồi.
7. **Dùng outbox/inbox cho message:** bảo đảm ý định phát event được lưu cùng dữ liệu và consumer xử lý duplicate an toàn.
8. **Dùng Saga khi workflow nhiều dịch vụ:** định nghĩa local transaction, compensation và trạng thái pending/manual review.
9. **Đặt timeout và idempotency:** kiểm soát thời gian gọi mạng và tránh tác động trùng khi retry.
10. **Quan sát transaction age và connection usage:** xác nhận transaction không còn bao trùm khoảng chờ ngoài ý muốn.

## 19. Những điểm cần nhớ

- Transaction nên bao quanh các thay đổi database cần cùng commit, không bao trùm thời gian gọi mạng hoặc chờ con người.
- Transaction dài có thể giữ connection, khóa, snapshot và tài nguyên log/version; tác động thực tế phụ thuộc database và isolation level.
- HTTP timeout không chứng minh dịch vụ đích chưa thực hiện tác động; rollback database không hoàn tác được remote side effect.
- Giữ transaction khi gọi mạng có thể làm tăng lock contention, deadlock, connection pool exhaustion và tail latency.
- Tách orchestration khỏi transaction cục bộ: transaction ngắn trước, gọi mạng ngoài transaction, transaction ngắn sau để ghi kết quả.
- Với biểu mẫu kéo dài, dùng optimistic locking/version check thay vì giữ `SELECT FOR UPDATE` trong lúc chờ người dùng.
- Dùng outbox để lưu ý định phát message cùng transaction; callback after-commit đơn thuần không bảo đảm bền vững khi process crash.
- Với workflow nhiều dịch vụ, dùng Saga và compensation; mỗi bước commit riêng và có trạng thái phục hồi.
- Dùng idempotency key ổn định, retry có giới hạn và reconciliation cho kết quả remote không rõ.
- Theo dõi transaction age, connection usage, remote-call span, lock wait và pool pending để phát hiện transaction bị giữ qua thời gian chờ.

Một transaction database không nên trở thành chiếc khung bao quanh toàn bộ thời gian một quy trình nghiệp vụ diễn ra. Hãy để database commit nhanh phần dữ liệu nó sở hữu, sau đó phối hợp các bước bên ngoài bằng trạng thái bền vững, outbox, worker hoặc Saga. Với tương tác người dùng, đọc trước và xác nhận lại bằng version khi lưu. Cách tổ chức này giảm thời gian giữ khóa và connection, đồng thời làm rõ cách phục hồi khi mạng, dịch vụ ngoài hoặc người dùng không phản hồi như mong đợi.
