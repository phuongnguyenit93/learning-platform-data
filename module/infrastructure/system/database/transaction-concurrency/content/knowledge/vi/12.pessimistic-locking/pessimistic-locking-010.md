# Tránh giữ khóa trong lúc chờ người dùng, mạng hoặc dịch vụ ngoài

Transaction nên giữ khóa trong khoảng thời gian ngắn cần thiết để đọc, kiểm tra và ghi dữ liệu. Nếu transaction mở trong lúc ứng dụng chờ người dùng suy nghĩ, chờ mạng phản hồi hoặc chờ một dịch vụ bên ngoài, các khóa có thể tiếp tục tồn tại dù database không làm thêm công việc hữu ích. Những transaction khác phải chờ, kết nối database bị chiếm dụng và khả năng deadlock hoặc timeout tăng lên.

Nguyên tắc quan trọng là **không kéo dài transaction qua một khoảng chờ nằm ngoài quyền kiểm soát của database**. Hãy hoàn tất một bước ghi nhất quán rồi COMMIT, thực hiện việc chờ ở ngoài transaction, sau đó mở transaction mới để xác nhận và lưu kết quả. Khi cần bảo vệ dữ liệu trong khoảng chờ, dùng version, trạng thái nghiệp vụ, reservation có thời hạn hoặc một quy trình xử lý bền vững.

## 1. Vì sao thời gian chờ làm khóa trở thành vấn đề?

Khóa (lock) cho phép database phối hợp những transaction đang đọc và ghi cùng tài nguyên. Một transaction cập nhật bản ghi thường cần khóa để bảo vệ thay đổi khỏi các thao tác xung đột. Trong nhiều hệ quản trị, khóa ghi được giữ đến khi transaction COMMIT hoặc ROLLBACK.

Giả sử một request thực hiện các bước:

1. Mở transaction.
2. Đọc và khóa một đơn hàng.
3. Gọi dịch vụ thanh toán qua HTTP.
4. Chờ dịch vụ thanh toán phản hồi.
5. Cập nhật trạng thái đơn hàng.
6. COMMIT.

Trong thời gian bước 3 và 4 diễn ra, database không thể tự giải phóng khóa mà transaction vẫn cần để bảo vệ tính nhất quán. Một request mạng bình thường có thể mất vài trăm mili giây; khi dịch vụ chậm hoặc retry, thời gian có thể tăng lên nhiều giây. Nếu người dùng phải xác nhận, thời gian chờ có thể lên đến vài phút.

~~~text
Một transaction kéo dài qua dịch vụ ngoài

Database transaction T1
+-------------------------------------------------------------+
| BEGIN                                                       |
| SELECT ... FOR UPDATE                                      |
|                                                             |
| Giữ khóa                                                     |
|          Gọi Payment API                                    |
|          Chờ mạng / timeout / retry                         |
|          <-------------------------                         |
|                                                             |
| UPDATE Order                                                |
| COMMIT                                                      |
+-------------------------------------------------------------+
        |
        +---- Transaction khác muốn cập nhật cùng dữ liệu
              phải chờ T1 kết thúc
~~~

Thời gian giữ khóa lúc này bao gồm cả thời gian ứng dụng không tương tác với database. Đây là chi phí không cần thiết đối với các transaction cạnh tranh.

### Các hậu quả thường gặp

**Blocking kéo dài.** Transaction khác có thể phải chờ khóa trên cùng dòng, trang, phạm vi chỉ mục hoặc bảng. Một truy vấn ngắn có thể bị kéo dài chỉ vì transaction giữ khóa đang đợi HTTP response.

**Giảm throughput.** Database xử lý được ít transaction hoàn tất hơn trong một đơn vị thời gian. Khi request đồng thời tăng, hàng đợi chờ khóa cũng tăng.

**Tăng độ trễ dây chuyền.** Request bị chặn có thể tiếp tục giữ tài nguyên ở tầng ứng dụng, chiếm worker thread và kết nối từ connection pool. Các request sau đó phải chờ cả database lẫn ứng dụng.

**Tăng nguy cơ deadlock.** Transaction càng kéo dài thì càng có nhiều cơ hội chồng lấn với transaction khác và giữ các khóa theo thứ tự khác nhau. Chờ lâu không tự động tạo deadlock, nhưng kéo dài cửa sổ mà chu trình chờ có thể hình thành.

**Tăng nguy cơ timeout và retry trùng lặp.** Ứng dụng có thể timeout khi chờ database hoặc dịch vụ ngoài. Nếu không phân biệt timeout của request với kết quả nghiệp vụ, việc retry có thể tạo thao tác trùng lặp.

**Tốn kết nối và bộ nhớ.** Transaction đang mở thường giữ một kết nối database hoặc ít nhất một phần tài nguyên phiên làm việc. Snapshot/undo version cũng có thể phải được giữ lâu hơn tùy DBMS và isolation level.

## 2. Không giữ transaction trong lúc chờ người dùng

Một lỗi thiết kế thường gặp là mở transaction khi người dùng bắt đầu chỉnh sửa biểu mẫu, khóa dòng dữ liệu rồi giữ transaction cho đến khi người dùng nhấn Save.

Ví dụ không nên dùng:

~~~sql
BEGIN TRANSACTION;

SELECT *
FROM dbo.Product WITH (UPDLOCK, HOLDLOCK)
WHERE ProductId = 42;

-- Ứng dụng trả dữ liệu về trình duyệt.
-- Người dùng suy nghĩ, chỉnh sửa biểu mẫu hoặc rời khỏi màn hình.
-- Transaction và khóa vẫn còn mở.

UPDATE dbo.Product
SET Price = 120000
WHERE ProductId = 42;

COMMIT TRANSACTION;
~~~

Người dùng có thể mất vài phút để nhập liệu, chuyển tab hoặc mất kết nối. Database không cần phải giữ khóa trong toàn bộ khoảng thời gian đó.

### 2.1. Dùng optimistic concurrency với version

Một cách phổ biến là đọc dữ liệu và version trong một thao tác ngắn, kết thúc transaction, rồi gửi version cùng dữ liệu khi người dùng lưu.

Ví dụ bảng Product có cột Version:

~~~sql
SELECT ProductId, Price, Version
FROM dbo.Product
WHERE ProductId = 42;
~~~

Giả sử ứng dụng nhận được:

~~~text
ProductId = 42
Price     = 100000
Version   = 7
~~~

Người dùng chỉnh sửa Price trong khi không có transaction database nào được giữ. Khi người dùng nhấn Save, ứng dụng chỉ cập nhật nếu version vẫn bằng 7:

~~~sql
UPDATE dbo.Product
SET Price = @newPrice,
    Version = Version + 1
WHERE ProductId = @productId
  AND Version = @versionRead;
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng:

- Một dòng được cập nhật: version khớp; thay đổi đã được áp dụng.
- Không có dòng được cập nhật: dữ liệu đã bị xóa hoặc người khác đã cập nhật trước đó. Ứng dụng cần tải lại dữ liệu, thông báo xung đột hoặc thực hiện chính sách merge phù hợp.

Cập nhật dữ liệu và tăng version phải nằm trong cùng một câu UPDATE. Nhờ đó, hai request cùng gửi version 7 không thể cùng ghi thành công: request đầu tiên tăng version lên 8, request thứ hai không còn khớp điều kiện.

Với SQL Server, có thể dùng kiểu dữ liệu rowversion thay cho số nguyên tự tăng. Ứng dụng lưu giá trị nhị phân đã đọc và đưa nó vào điều kiện WHERE khi cập nhật.

### 2.2. Version giải quyết điều gì và không giải quyết điều gì?

Version check bảo vệ bản ghi được cập nhật khỏi việc ghi đè một phiên bản cũ. Nó phù hợp với biểu mẫu chỉnh sửa, cấu hình, hồ sơ và các thao tác có khoảng thời gian người dùng suy nghĩ.

Nếu quyết định nghiệp vụ phụ thuộc vào nhiều dòng, một version duy nhất có thể chưa đủ. Ví dụ, người dùng chỉ được nghỉ khi còn ít nhất một nhân viên khác trực. Hai request có thể đọc cùng số nhân viên rồi cập nhật hai dòng khác nhau. Khi đó cần bảo vệ invariant bằng SERIALIZABLE, guard row, constraint phù hợp hoặc cập nhật nguyên tử trên một dòng tổng hợp.

Không dùng version check để thay thế việc thiết kế quy tắc đồng thời cho toàn bộ nghiệp vụ.

## 3. Không giữ khóa trong lúc gọi mạng hoặc dịch vụ ngoài

Các thao tác sau thường không thuộc transaction database:

- Gọi REST API, GraphQL, SOAP hoặc RPC.
- Gửi yêu cầu đến cổng thanh toán.
- Gọi dịch vụ gửi email, SMS hoặc thông báo.
- Chờ message broker, queue hoặc một worker khác.
- Đọc tệp từ hệ thống lưu trữ từ xa.
- Chờ dịch vụ xác thực, định danh hoặc phê duyệt.
- Chờ người dùng xác nhận một bước nghiệp vụ.

Các thao tác này có độ trễ và lỗi nằm ngoài quyền kiểm soát của database. Nếu thực hiện chúng trong khi đang giữ khóa, thời gian sống của khóa phụ thuộc vào mạng và dịch vụ bên ngoài.

### 3.1. Ví dụ gọi cổng thanh toán

Thiết kế rủi ro:

~~~text
BEGIN
  Khóa Order
  Kiểm tra số tiền
  Gọi Payment Provider
  Chờ phản hồi
  Nếu thành công: cập nhật PAID
COMMIT
~~~

Nếu cổng thanh toán mất 8 giây để phản hồi, khóa có thể bị giữ trong phần lớn 8 giây đó. Nếu dịch vụ timeout và ứng dụng thử lại ba lần bên trong transaction, thời gian giữ khóa còn dài hơn.

Một timeout cũng không chứng minh thanh toán thất bại. Provider có thể đã xử lý thanh toán nhưng response bị mất trên đường truyền. Nếu ứng dụng gọi lại bằng một yêu cầu mới, khách hàng có thể bị tính tiền hai lần.

Thiết kế tốt hơn là tách công việc thành các bước có trạng thái rõ ràng.

~~~text
Transaction A — ghi ý định thanh toán
  BEGIN
    Kiểm tra Order
    Tạo PaymentAttempt với trạng thái PENDING
    Lưu idempotency key
    Ghi sự kiện cần gửi (outbox)
  COMMIT

Bên ngoài transaction
  Worker đọc outbox
  Gọi Payment Provider bằng idempotency key
  Nhận kết quả hoặc kiểm tra trạng thái giao dịch

Transaction B — ghi kết quả
  BEGIN
    Đọc PaymentAttempt
    Kiểm tra trạng thái và attempt id
    Cập nhật kết quả có điều kiện
    Cập nhật Order nếu phù hợp
  COMMIT
~~~

Database chỉ giữ khóa trong hai đoạn ghi ngắn. Khoảng thời gian gọi provider diễn ra khi không có transaction database nào bị giữ mở vì request đó.

### 3.2. Idempotency key và kết quả không xác định

Khi gọi dịch vụ ngoài, ứng dụng nên tạo một idempotency key ổn định cho một lần thử nghiệp vụ, chẳng hạn một PaymentAttemptId. Nếu request timeout, lần retry phải dùng lại cùng key theo hợp đồng của provider.

Quy trình xử lý timeout:

1. Không tự kết luận provider đã thất bại.
2. Kiểm tra trạng thái PaymentAttempt trong database.
3. Nếu provider hỗ trợ truy vấn theo idempotency key hoặc mã giao dịch, hỏi lại trạng thái.
4. Nếu cần retry, gửi lại cùng idempotency key để provider có thể nhận diện yêu cầu trùng.
5. Ghi kết quả vào database bằng một transaction mới và điều kiện trạng thái phù hợp.

Idempotency key không tự bảo đảm mọi dịch vụ ngoài đều hỗ trợ chống trùng. Cần hiểu chính sách lưu key, thời hạn hiệu lực, cách xử lý request đồng thời và cách tra cứu kết quả của dịch vụ đang tích hợp.

### 3.3. Dùng Transactional Outbox khi cần giao sự kiện sau COMMIT

Nếu một thay đổi database phải kéo theo một message hoặc lệnh gọi dịch vụ ngoài, có một khoảng trống giữa hai hệ thống:

- Gửi message trước COMMIT: message có thể được xử lý dù transaction database sau đó rollback.
- COMMIT trước rồi mới gửi message: ứng dụng có thể dừng sau COMMIT nhưng trước khi gửi, khiến sự kiện bị mất.

Transactional Outbox giải quyết khoảng trống này bằng cách lưu thay đổi nghiệp vụ và sự kiện cần gửi trong **cùng một transaction database**.

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Orders
SET Status = 'PAYMENT_PENDING'
WHERE OrderId = @orderId
  AND Status = 'CREATED';

INSERT INTO dbo.Outbox
    (EventId, EventType, AggregateId, Payload, CreatedAt)
VALUES
    (@eventId, 'PaymentRequested', @orderId, @payload, SYSUTCDATETIME());

COMMIT TRANSACTION;
~~~

Sau COMMIT, một publisher/worker riêng đọc các dòng Outbox chưa gửi và chuyển message đến broker hoặc dịch vụ ngoài. Worker không cần giữ transaction database trong lúc chờ mạng:

1. Claim một nhóm sự kiện trong transaction ngắn.
2. COMMIT việc claim hoặc lưu lease.
3. Gửi message ngoài transaction.
4. Mở transaction ngắn khác để đánh dấu đã gửi nếu kết quả thành công.

Nếu publisher gửi thành công nhưng bị dừng trước khi đánh dấu đã gửi, sự kiện có thể được gửi lại. Vì vậy, consumer cần xử lý idempotent theo EventId hoặc một khóa nghiệp vụ ổn định. Outbox thường bảo đảm khả năng phát lại và giao ít nhất một lần; nó không tự tạo ra exactly-once end-to-end.

Không giữ khóa trên dòng Outbox trong suốt lúc gọi broker. Dùng trạng thái claim, lease hết hạn hoặc cơ chế worker phù hợp để một worker khác có thể tiếp tục khi worker hiện tại gặp sự cố.

## 4. Tách transaction khỏi lời gọi dịch vụ trong Spring

Một phương thức Spring có @Transactional bao quanh cả phần thân phương thức. Nếu phương thức đọc dữ liệu, gọi HTTP client rồi cập nhật database, transaction thường vẫn mở trong toàn bộ lời gọi HTTP.

Ví dụ rủi ro:

~~~java
@Service
public class OrderService {

    @Transactional
    public void pay(Long orderId) {
        Order order = orderRepository.findForUpdate(orderId);

        PaymentResult result =
            paymentClient.charge(order.getAmount());

        order.markPaid(result.transactionId());
    }
}
~~~

Ngay cả khi đoạn Java không chạy SQL trong lúc chờ HTTP, transaction vẫn đang mở. Các khóa đã lấy có thể còn được giữ và connection pool có thể tiếp tục bị chiếm dụng.

### 4.1. Đưa phần ghi vào các phương thức transaction ngắn

Có thể tổ chức một service điều phối không mang @Transactional ở cấp phương thức. Nó gọi các thao tác database riêng biệt, còn lời gọi mạng diễn ra giữa hai transaction:

~~~java
@Service
public class PaymentCoordinator {

    private final PaymentTransactionService transactions;
    private final PaymentGateway paymentGateway;

    public PaymentCoordinator(
            PaymentTransactionService transactions,
            PaymentGateway paymentGateway) {
        this.transactions = transactions;
        this.paymentGateway = paymentGateway;
    }

    public void processPayment(Long orderId) {
        PaymentCommand command =
            transactions.createPaymentAttempt(orderId);

        PaymentResult result = paymentGateway.charge(
            command.amount(),
            command.idempotencyKey()
        );

        transactions.recordPaymentResult(
            command.attemptId(),
            result
        );
    }
}
~~~

Service database:

~~~java
@Service
public class PaymentTransactionService {

    @Transactional
    public PaymentCommand createPaymentAttempt(Long orderId) {
        // Kiểm tra trạng thái Order.
        // Tạo PaymentAttempt PENDING và idempotency key.
        // Ghi outbox nếu quy trình dùng worker.
        // Trả command sau khi transaction COMMIT.
    }

    @Transactional
    public void recordPaymentResult(
            Long attemptId,
            PaymentResult result) {
        // Đọc attempt.
        // Kiểm tra attempt còn ở trạng thái hợp lệ.
        // Ghi kết quả bằng điều kiện trạng thái/version.
        // Cập nhật Order trong cùng transaction.
    }
}
~~~

Đây là cấu trúc minh họa. Trong ứng dụng thật, cần xử lý lỗi provider, timeout không xác định, retry, callback đến muộn và sự kiện trùng. Nếu dùng Outbox để xử lý bất đồng bộ, worker sẽ đảm nhiệm lời gọi provider và ghi kết quả theo cùng nguyên tắc.

Các phương thức transaction nên được gọi qua Spring bean/proxy phù hợp để transaction interceptor hoạt động. Một lời gọi nội bộ trong cùng đối tượng có thể không đi qua proxy trong cấu hình proxy mặc định. Hãy kiểm tra ranh giới transaction thực tế thay vì chỉ nhìn vị trí annotation.

Không dùng propagation REQUIRES_NEW để bọc riêng lời gọi HTTP. REQUIRES_NEW tạo một transaction mới; nếu transaction đó bao trùm lời gọi mạng thì nó vẫn giữ transaction và tài nguyên trong lúc chờ.

## 5. Chờ phê duyệt hoặc thao tác nhiều bước: dùng trạng thái nghiệp vụ

Một quy trình có thể cần nhiều giờ hoặc nhiều ngày:

- Đơn hàng chờ người quản lý duyệt.
- Hồ sơ chờ người dùng bổ sung giấy tờ.
- Yêu cầu hoàn tiền chờ nhà cung cấp xác nhận.
- Đặt lịch chờ người dùng chọn khung giờ.
- Tài khoản chờ xác minh danh tính.

Không nên mở transaction rồi khóa bản ghi cho đến khi người dùng hoặc bên ngoài hoàn tất. Hãy lưu trạng thái trung gian để database thể hiện tiến trình.

Ví dụ vòng đời đơn hàng:

~~~text
CREATED
   |
   v
PENDING_APPROVAL
   |
   +---- người duyệt chấp nhận ----> APPROVED
   |
   +---- người duyệt từ chối ------> REJECTED
   |
   +---- quá hạn -----------------> EXPIRED
~~~

Mỗi lần chuyển trạng thái là một transaction ngắn:

~~~sql
UPDATE dbo.Orders
SET Status = 'APPROVED',
    ApprovedBy = @userId,
    ApprovedAt = SYSUTCDATETIME(),
    Version = Version + 1
WHERE OrderId = @orderId
  AND Status = 'PENDING_APPROVAL'
  AND Version = @versionRead;
~~~

Nếu không có dòng nào được cập nhật, trạng thái đã đổi, phiên bản đã cũ hoặc người dùng khác đã xử lý yêu cầu. Ứng dụng đọc lại trạng thái hiện hành và trả thông báo phù hợp.

Cách này cho phép nhiều request cùng nhìn thấy trạng thái PENDING_APPROVAL mà không phải giữ khóa suốt thời gian chờ người duyệt.

### 5.1. Dùng lease hoặc thời hạn cho tài nguyên tạm giữ

Có những nghiệp vụ cần giữ chỗ trong khi chờ người dùng hoặc dịch vụ ngoài, ví dụ:

- Giữ một ghế trong thời gian người dùng nhập thông tin thanh toán.
- Giữ số lượng hàng trong lúc chờ cổng thanh toán.
- Giữ một slot lịch hẹn trong vài phút.

Đây là lúc cần **reservation có thời hạn (lease)** thay vì giữ transaction và khóa liên tục.

Một transaction ngắn có thể:

1. Kiểm tra số lượng hoặc slot còn trống.
2. Giảm số lượng khả dụng hoặc đánh dấu reservation.
3. Ghi ReservationId, trạng thái HELD và thời điểm hết hạn.
4. COMMIT.

Ví dụ trừ số lượng khả dụng và tạo reservation trong cùng transaction:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Inventory
SET AvailableQuantity = AvailableQuantity - @quantity
WHERE ProductId = @productId
  AND AvailableQuantity >= @quantity;

IF @@ROWCOUNT = 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50002, 'Insufficient inventory.', 1;
END;

INSERT INTO dbo.InventoryReservation
    (ReservationId, ProductId, Quantity, Status, ExpiresAt)
VALUES
    (@reservationId, @productId, @quantity, 'HELD',
     DATEADD(minute, 10, SYSUTCDATETIME()));

COMMIT TRANSACTION;
~~~

Sau COMMIT, người dùng có thể tiếp tục thanh toán mà không giữ khóa database. Nếu thanh toán thành công, một transaction ngắn chuyển reservation từ HELD sang CONFIRMED. Nếu thất bại hoặc hết hạn, một transaction khác giải phóng số lượng.

Cần bảo đảm thao tác giải phóng là idempotent: chỉ cộng lại số lượng nếu reservation thực sự chuyển từ HELD sang EXPIRED hoặc RELEASED. Nếu hai worker cùng xử lý hết hạn, chỉ một worker được phép chuyển trạng thái thành công.

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.InventoryReservation
SET Status = 'EXPIRED'
WHERE ReservationId = @reservationId
  AND Status = 'HELD'
  AND ExpiresAt <= SYSUTCDATETIME();

IF @@ROWCOUNT = 1
BEGIN
    UPDATE dbo.Inventory
    SET AvailableQuantity = AvailableQuantity + @quantity
    WHERE ProductId = @productId;
END;

COMMIT TRANSACTION;
~~~

Trong ví dụ, thông tin quantity và productId cần được lấy từ reservation đã xác định trong cùng transaction hoặc được kiểm tra bằng khóa/điều kiện phù hợp. Không nhận các giá trị hoàn trả tùy ý từ client. Thời gian hết hạn nên dựa trên đồng hồ database hoặc một nguồn thời gian thống nhất để tránh lệch đồng hồ giữa các application instance.

Lease có thể hết hạn khi dịch vụ ngoài đã xử lý thành công nhưng callback đến muộn. Vì vậy, cần quy định rõ thứ tự ưu tiên giữa CONFIRMED và EXPIRED, kiểm tra trạng thái provider và thiết kế bù trừ nếu đã thu tiền nhưng reservation không còn hiệu lực.

## 6. Chọn chiến lược theo loại thời gian chờ

| Tình huống | Thiết kế phù hợp | Điều cần bảo vệ |
|---|---|---|
| Người dùng mở biểu mẫu và lưu sau vài phút | Đọc không khóa dài, gửi version khi Save | Không ghi đè phiên bản mới hơn |
| Gọi API thanh toán hoặc dịch vụ ngoài | PaymentAttempt, idempotency key, transaction ngắn trước và sau lời gọi | Không giữ khóa khi chờ; xử lý timeout không xác định |
| Gửi message sau khi ghi database | Transactional Outbox và consumer idempotent | Không mất sự kiện giữa COMMIT và publish |
| Chờ phê duyệt nhiều bước | Trạng thái PENDING/APPROVED/REJECTED và chuyển trạng thái có điều kiện | Không xử lý hai lần hoặc chuyển trạng thái sai |
| Giữ ghế, hàng hoặc slot trong thời gian ngắn | Reservation có lease và thời hạn hết hạn | Giải phóng tài nguyên đúng một lần |
| Tác vụ dài gồm nhiều dịch vụ | Saga hoặc workflow bền vững | Có retry, timeout và hành động bù trừ |

Không có một mẫu duy nhất phù hợp với mọi nghiệp vụ. Hãy chọn dựa trên điều kiện cần giữ nhất quán, thời gian chờ dự kiến, khả năng retry và cách xử lý khi một bước đã thành công nhưng bước kế tiếp thất bại.

## 7. Saga và hành động bù trừ cho quy trình dài

Khi một quy trình đi qua nhiều dịch vụ hoặc nhiều transaction, không thể luôn gộp tất cả thành một transaction database. Một hướng thiết kế là Saga: chia quy trình thành các bước cục bộ, mỗi bước commit độc lập và có hành động bù trừ nếu bước sau thất bại.

Ví dụ đặt hàng:

~~~text
1. Tạo Order PENDING
       |
       v
2. Giữ Inventory
       |
       v
3. Thu tiền
       |
       v
4. Xác nhận Order
~~~

Nếu bước thu tiền thất bại, workflow có thể giải phóng inventory reservation và chuyển Order sang PAYMENT_FAILED. Nếu provider đã thu tiền nhưng phản hồi bị mất, workflow phải truy vấn trạng thái giao dịch bằng idempotency key trước khi quyết định retry hoặc hoàn tiền.

Saga không cung cấp rollback nguyên tử xuyên suốt mọi dịch vụ. Hành động bù trừ là một thao tác nghiệp vụ mới, có thể thất bại và cũng cần retry. Vì vậy, mỗi bước phải có trạng thái bền vững, mã định danh ổn định và cách xử lý sự kiện trùng.

## 8. Các kỹ thuật không nên dùng để che giấu transaction quá dài

### 8.1. Chỉ tăng timeout

Tăng command timeout, HTTP timeout hoặc lock timeout có thể làm request chờ lâu hơn. Nó không giảm thời gian giữ khóa. Nếu transaction mở trong lúc chờ dịch vụ ngoài, tăng timeout còn có thể làm blocking kéo dài hơn.

Timeout nên được đặt để giới hạn thời gian chờ của từng lời gọi bên ngoài, nhưng transaction vẫn cần kết thúc trước khi bắt đầu khoảng chờ đó.

### 8.2. Dùng lock hint để ép khóa hẹp hơn

ROWLOCK, UPDLOCK, HOLDLOCK hoặc các hint tương tự có ngữ nghĩa phụ thuộc DBMS và isolation level. Chúng không biến một transaction kéo dài qua HTTP thành transaction ngắn.

- ROWLOCK không phải cam kết rằng hệ quản trị sẽ không escalation.
- UPDLOCK có thể giữ khóa cập nhật lâu hơn nếu transaction chưa kết thúc.
- HOLDLOCK có thể mở rộng thời gian bảo vệ đến hết transaction.
- NOWAIT chỉ thay đổi cách xử lý khi khóa không lấy được; nó không làm lời gọi mạng nhanh hơn.
- SKIP LOCKED phù hợp với một số hàng đợi worker, nhưng có thể bỏ qua bản ghi đang bị giữ và cần thiết kế xử lý công bằng, retry.

Chọn lock hint chỉ khi đã hiểu chính xác ngữ nghĩa cần thiết. Đừng dùng chúng để bù cho ranh giới transaction sai.

### 8.3. Chia nhỏ câu SQL nhưng vẫn giữ transaction mở

Một vòng lặp gồm nhiều UPDATE nhỏ vẫn có thể giữ tất cả khóa đến cuối nếu toàn bộ vòng lặp nằm trong cùng một transaction. Muốn giải phóng khóa giữa các batch, mỗi batch phải có ranh giới COMMIT riêng và nghiệp vụ phải chấp nhận xử lý từng phần.

### 8.4. Dùng transaction phân tán chỉ để giữ một thao tác HTTP

Distributed transaction hoặc XA có thể phối hợp một số tài nguyên hỗ trợ giao thức tương ứng, nhưng không phải mọi REST API, payment gateway hoặc dịch vụ SaaS đều tham gia được. Nó cũng làm tăng độ phức tạp vận hành và không phải cách mặc định để biến một quy trình mạng dài thành thao tác nguyên tử.

Với dịch vụ ngoài không hỗ trợ transaction chung, hãy dùng trạng thái bền vững, idempotency, outbox và saga phù hợp.

## 9. Chẩn đoán transaction giữ khóa quá lâu

Khi có blocking bất thường, cần tìm transaction giữ khóa lâu nhất và xác định nó đang chờ điều gì.

Các câu hỏi hữu ích:

1. Transaction bắt đầu lúc nào và đã mở bao lâu?
2. Session đang giữ những khóa nào?
3. Session đó có đang chờ HTTP, RPC, message broker hoặc thao tác người dùng không?
4. Connection pool có nhiều connection đang ở trạng thái transaction mở không?
5. Có nhiều request bị chặn theo cùng một blocker không?
6. Timeout hoặc retry có làm transaction tồn tại lâu hơn không?

### 9.1. PostgreSQL: xem transaction mở lâu

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Cần chú ý transaction ở trạng thái idle in transaction: ứng dụng đã gửi câu lệnh và đang giữ transaction mở nhưng hiện không chạy SQL. Một session idle in transaction lâu có thể vẫn giữ khóa và snapshot cần thiết.

### 9.2. SQL Server: xem request đang bị chặn

~~~sql
SELECT
    session_id,
    blocking_session_id,
    status,
    wait_type,
    wait_time,
    wait_resource,
    command
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Kết quả cho biết session đang chờ và session chặn trực tiếp tại thời điểm truy vấn. Cần kết hợp với thông tin transaction đang mở, SQL đang chạy gần nhất và log ứng dụng để biết blocker có đang chờ dịch vụ ngoài hay không.

### 9.3. Theo dõi cả tầng ứng dụng

Chỉ xem DMV hoặc log database có thể chưa đủ. Nên ghi nhận:

- Thời điểm bắt đầu/kết thúc transaction.
- Thời gian từng lời gọi HTTP/RPC.
- Transaction hoặc request correlation id.
- Connection pool active/idle/pending.
- Số lần timeout, retry và kết quả không xác định.
- Số lượng transaction idle in transaction.
- Lock wait duration và blocking chain.

Dùng correlation id để ghép request ứng dụng với session database, nhưng không ghi token, mật khẩu, dữ liệu thanh toán nhạy cảm hoặc toàn bộ payload cá nhân vào log.

## 10. Quy trình thiết kế transaction ngắn

Khi thiết kế một thao tác có thể phải chờ người dùng hoặc dịch vụ ngoài, hãy tách nó thành các bước sau:

1. **Xác định dữ liệu cần bảo vệ.** Liệt kê các dòng, invariant và trạng thái nghiệp vụ cần kiểm tra.
2. **Mở transaction ngắn.** Đọc, kiểm tra và ghi trạng thái cần thiết; dùng version hoặc điều kiện cập nhật để phát hiện dữ liệu đã thay đổi.
3. **COMMIT trước khi chờ.** Giải phóng khóa và trả connection về pool theo vòng đời transaction.
4. **Thực hiện công việc bên ngoài.** Gọi dịch vụ, chờ người dùng, publish message hoặc xử lý tệp với timeout và idempotency phù hợp.
5. **Mở transaction mới để hoàn tất.** Đọc trạng thái hiện tại, kiểm tra attempt/version và ghi kết quả bằng chuyển trạng thái có điều kiện.
6. **Xử lý thất bại có thể phục hồi.** Retry, outbox, lease hoặc hành động bù trừ tùy loại nghiệp vụ.

Không phải mọi thao tác đều cần đủ sáu bước. Điểm cốt lõi là không giữ transaction mở chỉ để bảo toàn một giả định trong lúc chờ. Hãy lưu giả định đó thành version, trạng thái hoặc reservation mà database có thể kiểm tra lại khi công việc tiếp tục.

## 11. Những nguyên tắc cần ghi nhớ

- Khóa ghi thường được giữ đến COMMIT hoặc ROLLBACK; thời gian chờ bên ngoài có thể kéo dài thời gian giữ khóa.
- Không giữ transaction trong lúc người dùng suy nghĩ, nhập biểu mẫu hoặc chờ phê duyệt.
- Không gọi HTTP/RPC, payment gateway, email service hoặc message broker khi đang giữ khóa database.
- Dùng optimistic concurrency và version check khi người dùng gửi thay đổi sau một khoảng thời gian.
- Dùng trạng thái nghiệp vụ, idempotency key và transaction ngắn trước/sau lời gọi dịch vụ ngoài.
- Dùng Transactional Outbox khi cần bảo đảm sự kiện được lưu cùng thay đổi database; consumer vẫn phải xử lý message trùng.
- Dùng reservation có thời hạn khi cần giữ tài nguyên tạm thời mà không giữ transaction mở.
- Dùng Saga và hành động bù trừ cho quy trình dài đi qua nhiều dịch vụ.
- Tăng timeout hoặc đổi lock hint không sửa được transaction boundary quá dài.
- Theo dõi transaction age, blocking chain, idle-in-transaction và thời gian lời gọi bên ngoài để tìm nguyên nhân.

Database nên bảo vệ một thay đổi trong khoảng thời gian cần thiết để thực hiện và xác nhận nó. Khi ứng dụng phải chờ một người hoặc một hệ thống khác, hãy kết thúc transaction, lưu trạng thái đủ để tiếp tục an toàn rồi mở transaction mới khi có kết quả. Cách tổ chức này giúp giảm blocking, giữ connection pool khỏe mạnh và làm cho timeout, retry cũng như xử lý sự cố dễ kiểm soát hơn.

