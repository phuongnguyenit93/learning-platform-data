# Trạng thái trung gian và những bất biến không thể giữ tức thời

## 1. Bối cảnh: tại sao một nghiệp vụ không còn hoàn thành trong một transaction?

Trong một ứng dụng đơn khối, việc tạo đơn hàng, giữ tồn kho và ghi nhận thanh toán đôi khi được triển khai cùng một cơ sở dữ liệu. Transaction cục bộ có thể thực hiện nhiều thay đổi rồi COMMIT hoặc ROLLBACK theo cơ chế ACID của database.

Trong kiến trúc microservices, các năng lực có chủ sở hữu dữ liệu độc lập:

    Client
       |
       v
    Order Service --------> Inventory Service
          |
          +--------------> Payment Service
          |
          +--------------> Shipping Service

Order sở hữu vòng đời đơn. Inventory quyết định có thể giữ hàng không. Payment xác nhận khoản thu. Shipping quyết định trạng thái vận chuyển. Một transaction của Order **không tự động** bao trùm database Inventory, Payment và nhà cung cấp thanh toán bên ngoài.

Giả sử Inventory giữ hàng thành công, nhưng Payment đang chờ phản hồi từ cổng thanh toán. Hệ thống không thể hợp lý kết luận ngay rằng toàn bộ đơn hàng đã hoàn tất, cũng không nên xóa sự thật “hàng đã được giữ”. Nó cần trạng thái **đang xử lý, chờ xác minh hoặc cần bù trừ**.

**Trạng thái trung gian (intermediate states)** là những trạng thái có ý nghĩa nghiệp vụ trong quá trình phối hợp nhiều transaction cục bộ. Chúng không đồng nghĩa dữ liệu hỏng. Một hệ phân tán đúng phải mô tả rõ điều gì được phép tạm thời chưa đồng bộ, điều gì tuyệt đối không được vi phạm và cách đảm bảo quy trình cuối cùng đi đến kết quả hợp lệ.

### Mục tiêu học tập

Sau bài này, người học có thể:
1. Phân biệt bất biến cục bộ cần giữ ngay với điều kiện toàn quy trình có thể đạt sau.
2. Thiết kế state machine công khai các trạng thái PENDING, RESERVED, CONFIRMING, COMPENSATING, FAILED và NEEDS_RECONCILIATION.
3. Hiểu vì sao Saga, reservation, TCC, outbox, idempotency và đối soát giải quyết những bài toán khác nhau.
4. Nhận diện kết quả **chưa xác định** khi timeout: caller không biết receiver đã commit hay chưa.
5. Định nghĩa trách nhiệm từng service và tránh dùng trạng thái tổng hợp cũ để ra quyết định phá vỡ bất biến.
6. Xác định giới hạn của bù trừ, đặc biệt với thanh toán, email, hàng đã giao hoặc hiệu lực bên ngoài.
7. Thiết kế hành vi API, UX, monitoring và phép thử lỗi phù hợp với giao dịch phân tán.

---

## 2. Phân biệt tính đúng đắn tức thời và sự hội tụ của quy trình

Một **bất biến (invariant)** là điều kiện phải được giữ đúng trong một phạm vi và tại những thời điểm đã định nghĩa. Không thể nói “eventual consistency nên bất biến nào cũng có thể sai một lúc”. Trước tiên phải phân loại bất biến theo hậu quả và nguồn có thẩm quyền.

### 2.1. Bất biến cục bộ cần giữ ngay

Các ví dụ:
- Inventory không cấp reservation đang hiệu lực vượt số lượng có thể phân bổ theo chính sách.
- Payment không hoàn nhiều hơn số tiền có thể hoàn của giao dịch nguồn.
- Một seatId không thể đồng thời thuộc hai reservation active nếu chính sách độc quyền chỗ.
- Order không chuyển trực tiếp từ CANCELLED sang CONFIRMED khi state machine cấm.
- Một operation idempotent không tạo thêm tác dụng phụ chỉ vì caller thử lại cùng yêu cầu.
- Một người dùng không được thực thi command lên tài nguyên không thuộc quyền.

Những điều này cần được kiểm tra tại **service sở hữu quyết định**, gắn với transaction cục bộ, phép cập nhật nguyên tử, unique constraint, lock hoặc điều khiển đồng thời phù hợp.

Không nên xem sự vi phạm của những điều kiện này là “tạm chấp nhận được vì sau đó saga sẽ sửa”. Nếu đã cấp hai vé cho cùng một ghế và cùng có hiệu lực, việc hoàn tiền cho một người sau đó không làm sự kiện bán trùng trở thành đúng.

### 2.2. Điều kiện toàn quy trình có thể đang chờ

Những điều kiện như:
- “Một đơn CONFIRMED phải có bằng chứng giữ hàng và thanh toán phù hợp.”
- “Một đơn bị hủy cuối cùng phải giải phóng reservation còn được giải phóng.”
- “Một khoản thanh toán thành công cần được phản ánh trong đơn và thông báo cho khách.”
- “Một quy trình hoàn tiền cần đồng bộ trạng thái Order, Payment và phần báo cáo.”
- “Một hàng đã xuất kho cần được cập nhật trạng thái Shipping và Order.”

Chúng có thể cần nhiều bước, qua message/HTTP và thời gian không xác định. Hệ thống phải giữ điều kiện **chưa hoàn tất** dưới trạng thái rõ, không giả vờ đã đạt ngay.

Ví dụ Order=PENDING_PAYMENT trong khi Inventory=RESERVED không phải tự thân là lỗi. Nó là một tổ hợp hợp lệ nếu có thời hạn reservation, retry, đối soát và đường kết thúc được định nghĩa.

### 2.3. Safety và liveness

Hai thuộc tính có ích:
- **Safety:** Không bao giờ xảy ra điều bị cấm. Ví dụ không xác nhận đơn thiếu một khoản thu có hiệu lực, không giữ âm tồn kho.
- **Liveness:** Công việc hợp lệ cuối cùng có thể tiếp tục, hoàn tất hoặc đi tới một trạng thái kết thúc có thể xử lý.

Một hệ có thể bảo vệ safety bằng cách giữ tất cả đơn ở PENDING vĩnh viễn, nhưng thất bại về liveness. Ngược lại, nếu xác nhận mọi đơn ngay để đạt tốc độ, hệ có thể vi phạm safety.

Thiết kế tốt cần **cả hai**: bảo vệ điều không được sai và có cơ chế giúp trạng thái trung gian không kẹt vô hạn.

### 2.4. Phát biểu bất biến với phạm vi thời gian

Câu mơ hồ: “Order luôn phải có payment.”

Câu rõ hơn:
- “Order ở trạng thái CONFIRMED phải có một paymentAttempt được Payment xác nhận CAPTURED với số tiền/đơn vị và phạm vi phù hợp.”
- “Order PENDING_PAYMENT có thể chưa có khoản thu; nó không được phát OrderConfirmed.”
- “Nếu Payment đã thu nhưng Order bị hủy, workflow phải tạo nghĩa vụ xử lý hoàn/đối soát theo chính sách; không được xóa lịch sử khoản thu.”

Thời điểm và trạng thái trong mệnh đề quyết định một “trạng thái trung gian” là hợp lệ hay vi phạm.

---

## 3. Vì sao transaction cục bộ không thể bảo đảm mọi điều tức thời?

Mỗi service có một transaction riêng:

    Order DB:    create order=PENDING       -> COMMIT
    Inventory DB: reserve stock            -> COMMIT
    Payment DB: record charge              -> COMMIT
    Order DB:    set order=CONFIRMED        -> COMMIT

Giữa các lần COMMIT:
- Mạng có thể lỗi.
- Service có thể crash.
- Message có thể chậm, lặp hoặc sai thứ tự.
- Một database có thể unavailable trong khi database khác vẫn chạy.
- Provider thanh toán có thể chấp nhận lệnh nhưng không gửi kịp response.
- Một người dùng có thể gửi CancelOrder đồng thời với sự kiện PaymentCaptured.

Không có một thời điểm COMMIT đơn giản mà tất cả database, message broker và provider ngoài cùng đảo chiều nguyên tử theo mặc định.

### 3.1. Hai điều không nên suy ra

**Sai lầm A:** “Mỗi service có transaction ACID thì tổng thể cũng ACID.”

Không. ACID của Order không làm một câu lệnh ở Payment DB rollback khi Order rollback.

**Sai lầm B:** “Đã dùng microservices thì tất cả dữ liệu đều phải eventual.”

Không. Bất biến cứng trong từng nguồn sở hữu vẫn phải được giữ bằng cơ chế đồng thời và transaction đủ mạnh. Chỉ những điều kiện toàn quy trình được thiết kế chấp nhận khoảng cách thời gian mới hội tụ sau.

### 3.2. Một ví dụ trạng thái không nhất quán nhưng hợp lệ

Ở một thời điểm:

    Order       = PENDING_PAYMENT
    Inventory   = RESERVED (reservationId=res-77)
    Payment     = PROCESSING (paymentAttemptId=pay-88)
    Notification = NOT_SENT

Nếu hợp đồng cho phép chờ thanh toán tối đa một khoảng, đây là tổ hợp hợp lệ. Hệ thống không nên dán nhãn “Order CONFIRMED” hoặc “Đã thanh toán” chỉ để che trạng thái trung gian.

Nếu quá thời hạn và kết quả Payment vẫn không chắc chắn, quy trình có thể chuyển NEEDS_RECONCILIATION, không nên kết luận PaymentFailed khi chưa có chứng cứ.

---

## 4. Phân loại bất biến để thiết kế đường xử lý

| Nhóm | Ví dụ | Khi phải đúng | Cơ chế thường dùng |
|---|---|---|---|
| Bất biến cục bộ cứng | Stock available không âm; một seat chỉ giữ một lần | Tại commit ở owner | Atomic conditional update, unique, lock, transaction |
| Bất biến chuyển trạng thái | Không CONFIRM đơn đã CANCELLED | Khi nhận mỗi command/event | State machine, version/CAS |
| Bất biến quyền truy cập | Caller được phép hoàn khoản thu này | Tại lúc quyết định | AuthN/AuthZ tại owner và tenant-scope |
| Bất biến giá trị tiền | Refund không vượt khoản được hoàn | Tại Payment commit | Ledger/transaction/constraint |
| Điều kiện toàn quy trình | Order CONFIRMED cần xác nhận stock và payment | Trước khi Order xác nhận | Saga, chứng cứ có thẩm quyền, state machine |
| Nghĩa vụ phải hoàn tất sau | Đơn hủy cần release stock | Sau hủy theo SLO và policy | Outbox, retry, compensation, reconciliation |
| Projection consistency | Dashboard Order phản ánh PaymentCaptured | Trong độ trễ chấp nhận | Event consumer, version, monitoring |
| Mục tiêu vận hành | Email gửi trong thời hạn quy định | Theo SLO/điều khoản | Queue, retry, alert, hỗ trợ thủ công |

Hai ràng buộc có thể liên quan cùng một object nhưng có độ nghiêm trọng khác. Ví dụ “không hoàn quá số tiền được phép” là bất biến cứng ở Payment, còn “Order hiển thị đã hoàn tiền trong vòng vài giây” là yêu cầu hội tụ của read model.

### 4.1. Ranh giới aggregate và transaction

Aggregate trong thiết kế miền thường là phạm vi mà những bất biến cần đúng tức thời có thể được cưỡng chế trong một transaction cục bộ. Không phải cứ hai bảng có foreign key thì cần chung aggregate, và không phải cứ hai nghiệp vụ dùng chung customerId là phải chung transaction.

Nếu một quy tắc quan trọng thực sự không thể giữ khi tách dữ liệu sang hai service, hãy cân nhắc lại ranh giới ownership trước khi áp dụng saga. Đôi khi **đặt những trường cần commit nguyên tử trong cùng một service** là lựa chọn đúng hơn là tạo quy trình phân tán phức tạp.

### 4.2. Viết điều kiện bằng lời cụ thể

Thay vì “đơn phải nhất quán” hãy viết:
- Mọi lần giảm available phải có reservationId duy nhất.
- Không một OrderConfirmed nào được phát khi Payment chưa xác nhận khoản thu liên quan.
- Reservation hết hạn không tự được coi là đã release thành công khi chưa được Inventory xác nhận.
- PaymentCaptured tới muộn sau CancelOrder không được tự chuyển Order từ CANCELLED sang CONFIRMED.
- Sau một khoảng tối đa có thể chấp nhận, mọi operation pending quá hạn phải được giám sát/đối soát.

Một điều kiện cụ thể giúp lựa chọn cơ chế và xây test đúng.

## 5. State machine: trạng thái trung gian phải là trạng thái chính thức

Một sơ đồ tổng quát cho Order:

    DRAFT
      |
      | SubmitOrder
      v
    PENDING_STOCK
      |                     \
      | Reserved             \ Rejected
      v                       v
    PENDING_PAYMENT          REJECTED
      |        \
      |         \ Payment unknown/timeout
      |          v
      |     VERIFYING_PAYMENT
      |         |       \
      | Captured|        \ Business policy expires
      v         |         v
    CONFIRMED <-+      COMPENSATING
      |                      |
      |                      +--> CANCELLED
      |                      |
      |                      +--> REVIEW_REQUIRED
      v
    FULFILLING -> COMPLETED

Đây là mô hình minh họa. Một hệ có thể cần thêm PAYMENT_DECLINED, RESERVATION_EXPIRED, REFUND_PENDING hoặc PARTIALLY_FULFILLED. Không nên biến mọi luồng thành một enum khổng lồ nếu các trạng thái thuộc aggregate/owner khác nhau.

### 5.1. Ý nghĩa của các trạng thái

**PENDING_STOCK:** Order đã nhận intent bền vững nhưng chưa có kết quả giữ hàng có thẩm quyền. Không hứa với người dùng rằng hàng chắc chắn đã được giữ.

**PENDING_PAYMENT:** Đã đạt điều kiện giữ hàng theo chính sách, Payment chưa xác nhận kết quả cuối. Không gắn nhãn “đã thanh toán”.

**VERIFYING_PAYMENT:** Có lệnh Payment với kết quả chưa quan sát được do timeout, mất mạng hoặc provider xử lý trễ. Không tự retry bằng một khóa mới.

**CONFIRMED:** Các bằng chứng bắt buộc đã được xác minh, Order commit chuyển trạng thái hợp lệ. Từ đây có thể phát sự kiện OrderConfirmed.

**COMPENSATING:** Một hoặc nhiều bước đã có hiệu lực và đang cần hành động bù trừ. Không đồng nghĩa rollback đã hoàn tất.

**CANCELLED:** Đơn đã được hủy theo ý nghĩa của Order. Có thể vẫn tồn tại một nghĩa vụ hoàn tiền nếu quy trình đã đi tới điểm không thể đảo ngược ngay; không trộn nghĩa này nếu nghiệp vụ đòi “hoàn tiền xong” mới được xem là fully cancelled.

**REVIEW_REQUIRED:** Hệ chưa thể tự kết luận hoặc khôi phục an toàn; cần đối soát/manual handling. Đây là trạng thái vận hành có ý nghĩa nếu được quản lý, không phải chỗ đẩy lỗi cho người dùng rồi bỏ quên.

### 5.2. Đừng tạo trạng thái từ response network

HTTP 200 hoặc 202 không tự động nói nghiệp vụ đã hoàn tất. 202 chỉ là yêu cầu đã được nhận theo hợp đồng; HTTP 504 nghĩa gateway không nhận response kịp thời, không nghĩa PaymentFailed.

Trạng thái Order được xác định bằng **ngữ nghĩa kết quả** từ owner và state machine Order, không bởi việc socket có đóng hay không.

---

## 6. Saga: phối hợp nhiều transaction cục bộ

Saga là mô hình phối hợp một chuỗi transaction cục bộ với các bước tiến và khả năng bù trừ/khôi phục khi có lỗi. Nó có thể được tổ chức theo:
- **Orchestration:** Một coordinator theo dõi trạng thái và phát command cho từng service.
- **Choreography:** Các service phản ứng theo event, không có một coordinator trung tâm duy nhất.

### 6.1. Saga orchestration mẫu

    OrderSaga
       |
       +-- ReserveStock(orderId, requestKey) -> Inventory
       |       | RESERVATION_CREATED / REJECTED / UNKNOWN
       |
       +-- ChargePayment(orderId, requestKey) -> Payment
       |       | CAPTURED / DECLINED / UNKNOWN
       |
       +-- ConfirmOrder(orderId) -> Order
       |
       +-- Publish OrderConfirmed
       |
       +-- Nếu lỗi: ReleaseStock / Refund theo nghĩa vụ

Coordinator phải lưu trạng thái bền vững hoặc có thể tái tạo từ sự kiện; không được chỉ giữ toàn bộ tiến độ trong RAM rồi mất hết khi process crash.

### 6.2. Choreography mẫu

    OrderSubmitted
        |
        v
    Inventory -> StockReserved / StockRejected
        |
        v
    Payment -> PaymentCaptured / PaymentDeclined
        |
        v
    Order -> OrderConfirmed / OrderRejected

Cách này giảm điều phối tập trung, nhưng khi có nhiều nhánh, dễ khó nhìn thấy “ai chịu trách nhiệm cuối cùng” và nguy cơ vòng lặp sự kiện. Cần event contracts, correlation IDs, state machines và quan sát end-to-end.

### 6.3. Saga không tạo ACID toàn cục

Mỗi bước có transaction riêng. Nếu Payment đã thu tiền và ReserveStock thất bại, bù trừ có thể là RefundPayment. Refund là **một giao dịch mới**, không phải một ROLLBACK tự động của lần thu đầu.

Một khoản refund có thể bị provider từ chối tạm thời, mất phí hoặc hoàn về sau; hệ thống cần lưu nghĩa vụ và tiếp tục xử lý. Không thể chỉ chạy “ngược” một phương thức Java rồi coi toàn saga chưa từng xảy ra.

### 6.4. Chọn orchestration hay choreography

Orchestration hữu ích khi:
- Có trình tự nghiệp vụ rõ và nhiều nhánh lỗi.
- Cần theo dõi một operation tổng thể và deadline.
- Cần chính sách bù trừ phức tạp.
- Tác vụ cần hỗ trợ thủ công, audit và replay có kiểm soát.

Choreography phù hợp khi:
- Các phản ứng độc lập, ít bước và ít tương tác ngược.
- Event là sự thật nghiệp vụ tự nhiên.
- Ownership của từng phản ứng rõ ràng.
- Có công cụ quan sát và xử lý duplicate/order.

Không chọn chỉ theo số service. Quan trọng là mức độ phụ thuộc, quyền ra quyết định và khả năng khôi phục.

---

## 7. Reservation và escrow: tránh vi phạm bất biến cứng trong khi chờ

Một câu hỏi khó: Nếu chưa thu tiền, có nên giảm tồn kho ngay không?

Nếu Inventory chỉ đọc available qua GET rồi Order tự quyết định “còn hàng”, hai người dùng có thể mua quá số lượng. Hệ thống cần **quyền giữ hàng có hiệu lực**, không chỉ một bản đọc.

### 7.1. Reservation là trạng thái nghiệp vụ

Một mô hình tồn kho:

    available = 10
    reserved  = 0

Order A yêu cầu giữ 3:

    available = 7
    reserved  = 3
    Reservation(res-A, qty=3, state=ACTIVE, expiresAt=...)

Order B đồng thời yêu cầu giữ 8 thì Inventory từ chối nếu available chỉ còn 7. Đây là quyết định nguyên tử ở service sở hữu.

Reservation cho phép Order ở trạng thái PENDING_PAYMENT trong khi **bất biến không giữ vượt tồn kho vẫn đúng**.

### 7.2. Atomic conditional update

Ví dụ SQL mang tính minh họa:

~~~sql
UPDATE inventory_stock
SET available = available - :qty,
    reserved  = reserved + :qty,
    version   = version + 1
WHERE tenant_id = :tenantId
  AND sku = :sku
  AND available >= :qty;
~~~

Điều kiện quan trọng:
- qty phải là số dương hợp lệ.
- Kiểm tra affected rows.
- Tạo reservation và cập nhật stock trong cùng transaction cục bộ.
- Có unique constraint/idempotency để cùng một intent không giữ hai lần.
- Release phải chuyển state một lần, không chỉ cộng stock khi nhận event bất kỳ.
- Transaction/isolation và phạm vi khóa phải được kiểm chứng trên datastore thực tế.

Một câu SQL như vậy giúp bảo vệ điều kiện số lượng tại điểm ghi. Với nhiều dòng stock, seat cụ thể hoặc nhiều warehouse, cần thiết kế khác phù hợp để đảm bảo bất biến.

### 7.3. Reservation có thời hạn

Một reservation nên có:
- reservationId.
- Order/requestId liên hệ.
- Chủ thể hoặc tenant scope.
- Số lượng hoặc seat.
- expiresAt theo chính sách và nguồn thời gian đáng tin.
- Trạng thái ACTIVE, COMMITTED, RELEASED, EXPIRED hoặc tương đương.
- Version để ngăn command cạnh tranh.

Nếu Order không hoàn tất trong thời hạn, Inventory có thể hết hạn reservation và trả lượng hàng theo quy tắc. Tuy nhiên “đến đúng mốc expiresAt” không đồng nghĩa một cron job đã cập nhật dữ liệu ngay trong microsecond ấy; cần phân biệt **quyền sử dụng đã hết hạn theo policy** với việc cleanup vật lý đã chạy.

### 7.4. Expire cạnh tranh với Commit

Giả sử CommitReservation và ExpireReservation chạy đồng thời. Nếu cả hai chỉ đọc ACTIVE rồi cập nhật mù, có thể vừa coi hàng đã bán vừa trả hàng vào available.

Giải pháp có thể dùng state transition có điều kiện:

~~~sql
UPDATE reservations
SET state = 'COMMITTED',
    version = version + 1
WHERE reservation_id = :reservationId
  AND state = 'ACTIVE'
  AND expires_at > :decisionTime;
~~~

Lệnh Expire cũng chỉ chuyển ACTIVE sang EXPIRED khi đủ điều kiện. Chúng phải tranh chấp một trạng thái có thẩm quyền sao cho **tối đa một chuyển trạng thái có hiệu lực**. Các thay đổi stock hoặc allocations liên quan phải cùng transaction phù hợp.

### 7.5. Escrow/quota partitioning

Trong một số hệ phân tán lớn, có thể phân bổ trước quyền cấp phát theo từng shard/zone, ví dụ vùng A được phép cấp tối đa 40 trong tổng 100 ghế, vùng B 60. Mỗi vùng bảo vệ quota cục bộ để tránh yêu cầu đồng bộ toàn cục trên mọi thao tác.

Đây là hình thức giới hạn quyền quyết định để giữ bất biến toàn cục qua **phân bổ quyền có giới hạn**, nhưng có đánh đổi: vùng A có thể hết quota dù vùng B còn. Chuyển quota phải được điều phối cẩn thận, tránh cấp trùng trong partition.

---

## 8. Try–Confirm–Cancel (TCC) và saga bù trừ

TCC thường diễn tả:
1. **Try:** Dành trước hoặc khóa logic tài nguyên, chưa tạo hiệu lực cuối.
2. **Confirm:** Xác nhận tài nguyên đã dành khi điều kiện hoàn tất.
3. **Cancel:** Giải phóng khi quy trình không tiếp tục.

Ví dụ giữ chỗ:

    TryReserveSeat   -> Reservation ACTIVE
    ConfirmSeat      -> Reservation COMMITTED
    CancelSeat       -> Reservation RELEASED

TCC phù hợp khi tài nguyên có thể được **dành trước an toàn** và có bước xác nhận/hủy được service sở hữu cung cấp. Nó đòi:
- Idempotent Try/Confirm/Cancel.
- Kiểm soát expiry và race.
- Mỗi bước có ID ổn định.
- Xử lý timeout/unknown outcome.
- Khả năng tìm và phục hồi các Try bị treo.

Không phải mọi side effect đều hỗ trợ TCC. Gửi email, xuất hàng hoặc thu tiền qua provider có thể không có bước Try/Cancel tương đương rollback. Khi đó dùng saga, trạng thái và bù trừ phù hợp với hành vi thực tế.

### 8.1. Đừng đánh đồng “Cancel” và “Hoàn tác tuyệt đối”

Một đơn được hủy sau khi đã gửi hàng có thể cần quy trình trả hàng. Một khoản tiền đã chuyển đi có thể cần giao dịch hoàn tiền mới. Một email đã gửi không thể được “unsend” bằng message mới.

Hợp đồng bù trừ phải nói rõ **kết quả kinh doanh** mà nó khôi phục, những tác động không thể thu hồi và thời gian có thể chờ.

---

## 9. Payment: kết quả không xác định không phải thất bại

Thanh toán là ví dụ điển hình vì caller có thể timeout sau khi provider đã thực hiện side effect.

Timeline:

    T0       Order gửi ChargePayment(order=123, key=K)
    T0+100   Payment ghi attempt=PENDING
    T0+250   Payment gọi provider với khóa chống trùng
    T0+800   Order timeout, ngừng chờ
    T0+1200  Provider thu tiền thành công
    T0+1300  Payment commit CAPTURED
    T0+1350  Payment gửi kết quả nhưng response bị mất

Từ Order: timeout. Từ Payment: CAPTURED. Cả hai có thể đúng từ góc nhìn quan sát.

**Không được tự chuyển Order sang PAYMENT_FAILED khi timeout.** Cần:
- paymentAttemptId/operationId bền vững.
- Idempotency key ổn định cho cùng ý định thu tiền.
- API tra cứu trạng thái hoặc sự kiện PaymentCaptured/PaymentDeclined.
- Trạng thái VERIFYING_PAYMENT hoặc NEEDS_RECONCILIATION ở Order.
- Cơ chế đối soát với provider khi Payment chưa thể kết luận.

### 9.1. Authorize, capture, void, refund

Một số provider hỗ trợ tách:
- **Authorize:** Đặt quyền giữ một khoản tiền theo chính sách.
- **Capture:** Thu hoặc chốt khoản thanh toán.
- **Void:** Hủy authorization chưa capture khi còn có thể.
- **Refund:** Tạo giao dịch hoàn sau khi đã capture.

Các bước và hiệu lực thật sự phụ thuộc provider, loại phương thức thanh toán và khu vực. Không xem cancel HTTP tương đương void/refund, cũng không mô phỏng rollback đơn giản nếu provider không hỗ trợ.

### 9.2. Bất biến của Payment phải giữ ngay

Ví dụ:
- Một cùng-intent charge không được tạo hai hiệu lực thu độc lập theo phạm vi idempotency.
- Tổng refund được chấp nhận không vượt số tiền hợp lệ để hoàn.
- Một khoản capture không được chuyển trạng thái tùy ý trái contract.
- Chỉ caller có quyền mới được yêu cầu hoàn tiền.
- Ledger và operation history phải được ghi theo mô hình chính xác.

Trong khi đó việc Order UI cập nhật trạng thái trả tiền sau PaymentCaptured có thể trễ theo hợp đồng. Đó là tính nhất quán cuối cùng của projection, không phải cho phép Payment ghi ledger sai.

### 9.3. Lưu nghĩa vụ hoàn tiền thay vì quên lỗi

Nếu Order bị hủy nhưng một PaymentCaptured đến muộn, hệ thống có thể:
1. Xác nhận PaymentCaptured thuộc đúng paymentAttempt/order.
2. Giữ Order ở trạng thái không cho CONFIRM từ CANCELLED.
3. Ghi nghĩa vụ RefundRequired hoặc đặt trạng thái REFUND_PENDING.
4. Gửi RefundPayment idempotent theo hợp đồng.
5. Theo dõi đến khi refund được owner xác nhận.
6. Nếu thất bại kéo dài, mở RECONCILIATION/REVIEW_REQUIRED.

Không xóa Order hay Payment log để giả vờ mọi bước đã rollback.

---

## 10. Trạng thái trung gian cần có owner

Một lỗi phổ biến là mọi service đều có trường “status” và tự diễn giải trạng thái tổng thể:

    Order.status = PAID
    Payment.status = CAPTURED
    Inventory.status = RESERVED
    Shipping.status = PENDING

Câu hỏi “ai quyết định một đơn đã hoàn tất?” phải có câu trả lời rõ. Payment sở hữu hiệu lực thanh toán; Inventory sở hữu reservation; Shipping sở hữu vận chuyển; Order sở hữu trạng thái vòng đời đơn.

### 10.1. Event là bằng chứng, không phải quyền sở hữu chéo

Order nhận PaymentCaptured từ Payment. Order có thể dùng thông tin làm bằng chứng cho state transition của mình, nhưng:
- Không được tự sửa Payment.status.
- Phải kiểm tra event thuộc đúng paymentAttempt và amount/currency nếu cần.
- Phải kiểm tra Order hiện có trạng thái cho phép chuyển.
- Không dùng một event cũ để đảo ngược CANCELLED.
- Phải chịu được event gửi lại.

Tương tự, Payment không nên chuyển Order sang CONFIRMED bằng cách UPDATE database Order chỉ vì nó đã capture tiền.

### 10.2. Khoảng trễ giữa sự thật và projection

Một dashboard có thể hiển thị:

    Payment authoritative status = CAPTURED
    Order read model status = PENDING_PAYMENT

trong vài giây do consumer lag. Nếu hệ thống công bố điều này, trạng thái hiển thị chậm là bình thường. Nhưng một command nghiệp vụ quan trọng không nên dùng read model cũ làm căn cứ duy nhất để xác nhận một bất biến cứng.

### 10.3. “PENDING” cần phân loại cụ thể

Một enum PENDING quá tổng quát sẽ khiến vận hành không biết:
- Chưa gửi command?
- Đã gửi nhưng chờ kết quả?
- Đã commit cục bộ, chờ publish?
- Đang chờ một sự kiện?
- Đã quá hạn và cần đối soát?
- Đang bù trừ?

Nên dùng trạng thái và metadata đủ rõ để xử lý. Trạng thái ở API có thể giản lược cho người dùng, còn trạng thái nội bộ chi tiết hơn, nhưng ánh xạ phải nhất quán.

---

## 11. Transactional outbox: giữ một sự thật cục bộ cùng ý định phát sự kiện

Một lỗi dual write:

    1. Order COMMIT status=CONFIRMED trong DB
    2. Order publish OrderConfirmed lên broker

Nếu service crash giữa hai bước, trạng thái đã thay đổi nhưng sự kiện có thể không được gửi.

Đảo thành publish trước COMMIT lại có nguy cơ consumer hành động trên một event mà DB cuối cùng rollback.

**Transactional outbox**:
1. Trong cùng transaction cục bộ, cập nhật Order và chèn outbox record.
2. Commit.
3. Một publisher đọc outbox, gửi event rồi đánh dấu đã gửi.
4. Consumer xử lý event idempotent vì publisher có thể phát trùng.

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE tenant_id = :tenantId
  AND order_id = :orderId
  AND status = 'PENDING_PAYMENT'
  AND version = :expectedVersion;

-- Chỉ ghi outbox nếu phép chuyển trạng thái ở trên thành công.
INSERT INTO outbox (
  event_id, aggregate_id, event_type, payload, created_at
) VALUES (
  :eventId, :orderId, 'OrderConfirmed', :payload, CURRENT_TIMESTAMP
);

COMMIT;
~~~

Đây là SQL minh họa. Logic thực tế phải kiểm tra số dòng UPDATE, bảo vệ event ID duy nhất và rollback toàn transaction nếu chuyển trạng thái không hợp lệ.

### 11.1. Outbox không tạo transaction xuyên service

Order cập nhật DB và outbox nguyên tử ở Order. Nó không làm Payment, Inventory và Notification commit đồng thời. Các consumer cần thiết kế cho at-least-once delivery, duplicate, ordering, lag và replay.

### 11.2. Event tới muộn là trường hợp bình thường

Nếu OrderConfirmed được phát rồi Notification offline 10 phút, email có thể gửi sau. Trạng thái tổng thể lúc đó có thể là Order=CONFIRMED, Notification=PENDING. Quy trình không nhất thiết sai; nhưng nếu có yêu cầu gửi email trong hai phút, hệ đã vi phạm SLO và cần alert/khôi phục.

**SLO hội tụ phải được đo**, không chỉ ghi trên sơ đồ rằng “eventual”.

---

## 12. Idempotency: retry không tạo thêm hiệu ứng

Trong mạng phân tán, timeouts, broker redelivery và worker crash là tình huống bình thường. Một command có tác dụng phụ cần danh tính ý định bền vững.

Ví dụ:

    CreateOrder:     idempotencyKey=checkout-123
    ReserveStock:    idempotencyKey=reserve-order-123
    ChargePayment:   idempotencyKey=charge-order-123-attempt-1
    ReleaseStock:    idempotencyKey=release-reservation-777
    RefundPayment:   idempotencyKey=refund-payment-888-reason-X

Một retry của **cùng một ý định** nên dùng lại key tương ứng. Nếu mỗi lần timeout tạo key mới, hệ thống có thể giữ hàng, thu tiền hoặc hoàn tiền nhiều lần.

### 12.1. Một idempotency record

Một bảng minh họa:

~~~sql
CREATE TABLE idempotency_request (
    tenant_id        VARCHAR(64) NOT NULL,
    operation_type   VARCHAR(64) NOT NULL,
    request_key      VARCHAR(128) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    operation_id     VARCHAR(128) NOT NULL,
    status           VARCHAR(32) NOT NULL,
    PRIMARY KEY (tenant_id, operation_type, request_key)
);
~~~

Khi nhận lại cùng key/cùng payload, service trả trạng thái đã ghi hoặc tiến trình đang chạy. Cùng key nhưng payload khác phải xử lý conflict theo hợp đồng.

**Đừng chỉ SELECT trước rồi INSERT không có uniqueness.** Hai request song song có thể đều đọc “chưa tồn tại” và cùng gây effect. Datastore cần constraint/transaction/locking bảo vệ tính duy nhất.

### 12.2. Idempotent consumer

Với event:

~~~text
receive Event X
begin transaction
  if Event X already processed:
      commit
      ACK
      return

  validate aggregate version and business transition
  apply local state change
  insert processed_event(eventId)
commit
ACK
~~~

Cần unique constraint và transaction để chống hai consumer xử lý song song. Nếu effect là gọi provider ngoài DB, cần thêm idempotency tại provider hoặc cơ chế đối soát, vì transaction cục bộ không bao gồm lời gọi mạng.

### 12.3. At-least-once không đồng nghĩa xử lý nghiệp vụ hai lần

Broker có thể giao một event nhiều lần. Consumer phải chịu được điều đó. “Exactly once” của một nền tảng có thể chỉ bao phủ một số bước trong cùng hệ, không tự bảo đảm email hoặc khoản charge bên ngoài tuyệt đối chỉ được thực hiện một lần.

---

## 13. Ordering, version và stale events

Một quy trình phân tán có thể nhận:

    PaymentCaptured(paymentAttempt=A, version=8)
    PaymentPending(paymentAttempt=A, version=7)

Nếu consumer cập nhật mù theo thứ tự nhận, projection có thể lùi từ CAPTURED về PENDING.

### 13.1. Version guard

Với event mang snapshot trạng thái đủ nghĩa:

~~~sql
UPDATE payment_projection
SET status = :newStatus,
    source_version = :incomingVersion
WHERE payment_attempt_id = :attemptId
  AND source_version < :incomingVersion;
~~~

Một consumer cần thiết kế xử lý khi row chưa tồn tại, duplicate, version gap và tombstone. Nếu event là **delta** (ví dụ điểm cộng 10), việc bỏ qua phiên bản thiếu có thể làm sai tổng; cần replay/chờ theo contract.

### 13.2. Không dùng timestamp nhận để quyết định thứ tự nghiệp vụ

Một event có occurredAt sớm hơn nhưng đi qua mạng chậm có thể tới sau. Clock các máy có thể lệch. Thứ tự theo thời gian nhận không thay thế aggregate version hoặc một sequence có thẩm quyền trong phạm vi cần.

### 13.3. Sự kiện đến sau khi terminal state

Order đã CANCELLED, rồi StockReserved đến muộn. Order không nên chuyển sang PENDING_PAYMENT chỉ vì nhận event. Nó phải:
1. Xác định event thuộc saga/attempt nào.
2. Kiểm tra state machine hiện tại.
3. Nếu reservation còn hiệu lực, tạo nghĩa vụ release theo chính sách.
4. Không thay đổi terminal state một cách mù quáng.
5. Ghi metric/audit để phát hiện thường xuyên xảy ra race.

Sự kiện đến trễ không bị bỏ qua hoàn toàn nếu nó mang bằng chứng về một tác động cần bù trừ.

---

## 14. Compensation: hoàn tác nghiệp vụ không phải rollback kỹ thuật

Một compensation là một hành động nghiệp vụ mới được thực hiện để xử lý tác động của bước trước.

Ví dụ:
- ReserveStock được bù bằng ReleaseReservation.
- ChargePayment được bù bằng RefundPayment hoặc VoidAuthorization, tùy trạng thái.
- CreateShipmentLabel có thể được bù bằng CancelLabel nếu nhà vận chuyển cho phép.
- CreateAccount có thể được xử lý bằng DeactivateAccount theo policy.

### 14.1. Ba loại tác động

**Có thể đảo ngược gần tương đương:** Một reservation ACTIVE chưa sử dụng có thể release và trả lại available.

**Có thể bù nhưng không khôi phục nguyên trạng:** Thanh toán đã capture có thể refund, nhưng có độ trễ, phí, rủi ro và lịch sử hai giao dịch thay vì một giao dịch chưa từng xảy ra.

**Không thể thu hồi đầy đủ:** Email đã tới người nhận, hàng đã được giao hoặc thông tin đã được bên thứ ba xử lý. Có thể thực hiện một hành động sửa chữa, nhưng không thể bảo đảm thế giới trở về đúng thời điểm trước.

Đối với các bước không thể đảo ngược, quy trình nên cân nhắc thực hiện chúng **sau khi** đã đủ điều kiện và ghi nhận rõ mốc không thể hủy.

### 14.2. Compensation cần idempotency

Nếu ReleaseStock chạy lần hai và cộng available thêm lần nữa, hệ thống có thể bán vượt tồn kho sau đó. Inventory phải kiểm soát:

    ACTIVE -> RELEASED : +qty available một lần
    RELEASED -> RELEASED : không tăng thêm
    COMMITTED -> RELEASED : bị từ chối hoặc theo quy tắc khác

Đừng cho coordinator gửi raw UPDATE inventory_stock SET available=available+qty. Nó chỉ được yêu cầu owner thực hiện command có ý nghĩa.

### 14.3. Compensation cũng có thể thất bại

Một refund gặp network partition hoặc provider rate limit. Saga không thể coi toàn bộ quy trình “đã rollback” khi lệnh hoàn tiền chỉ mới được gửi.

Cần trạng thái:

    REFUND_REQUIRED
        |
        v
    REFUND_PENDING
       / \
      /   \
 REFUNDED  NEEDS_RECONCILIATION

Theo dõi retry có giới hạn, deadline riêng, idempotency, đối soát và hỗ trợ thủ công. Khi không thể bù tự động, phải có owner và nghĩa vụ không được quên.

---

## 15. Timeout và kết quả chưa xác định

Timeout là kết luận của bên gọi rằng chưa có phản hồi đúng thời hạn. Nó không chứng minh bên nhận chưa xử lý hoặc đã rollback.

Một lần POST /payments có thể rơi vào các trạng thái:
- Chưa gửi request thành công.
- Đã gửi nhưng receiver chưa đọc.
- Receiver đã ghi attempt=PENDING.
- Provider đã capture nhưng Payment chưa nhận phản hồi.
- Payment đã commit CAPTURED nhưng response bị mất.
- Order đã hủy trong khi Payment vẫn xử lý.

### 15.1. UNKNOWN khác FAILED

**FAILED/DECLINED** cần có bằng chứng có thẩm quyền rằng operation bị từ chối hoặc không thể có hiệu lực theo contract.

**UNKNOWN/VERIFYING** nghĩa caller chưa có thông tin đủ để kết luận. Đây là trạng thái trung gian hợp lệ của một hệ phân tán, không phải ngoại lệ cần che bằng thành công hoặc thất bại giả.

### 15.2. API status query

Một API thích hợp cho operation dài:

~~~http
POST /payments/operations
Idempotency-Key: charge-order-123-attempt-1
Content-Type: application/json

{
  "orderId": "ord-123",
  "amountMinor": 500000,
  "currency": "VND"
}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /payments/operations/payop-456
Content-Type: application/json

{
  "operationId": "payop-456",
  "status": "PROCESSING"
}
~~~

Caller có thể GET operationId hoặc nhận sự kiện kết quả. Nếu response POST bị mất, có thể tra bằng idempotency key theo hợp đồng. Không tạo charge mới chỉ vì không nhận phản hồi 202.

### 15.3. Deadline của HTTP và vòng đời nghiệp vụ

HTTP có thể có deadline 2 giây, Payment workflow có thời gian xác minh dài hơn. Nếu kết quả không thể có trong 2 giây một cách tin cậy, có thể ghi nhận intent bền vững và trả 202 với operationId, thay vì giữ thread/connection chờ provider trong nhiều phút.

Đổi sang async không tự làm giao dịch đúng: vẫn cần state machine, idempotency, outbox và cơ chế dừng/bù trừ.

---

## 16. Huỷ và hết hạn khi đang có bước chưa kết thúc

Giả sử đơn hàng chỉ chờ thanh toán 10 phút. Hết 10 phút, Order có thể muốn hủy. Nhưng PaymentAttempt đã được gửi tới provider ở phút thứ 9:59 và đang chờ kết quả.

Nếu Order tự kết luận Payment chưa thu vì chưa thấy event, rồi hoàn tất CANCELLED và giải phóng hàng, một PaymentCaptured đến sau có thể tạo nghĩa vụ refund.

Một thiết kế:
1. Deadline của Order kích hoạt yêu cầu hết hạn.
2. Order chuyển sang CANCELLING/VERIFYING_PAYMENT nếu còn attempt chưa rõ.
3. Inventory được yêu cầu release reservation theo policy; có thể xảy ra race với confirm.
4. Payment tra provider hoặc kết luận trạng thái có thẩm quyền.
5. Nếu capture chưa xảy ra và có thể void an toàn, thực hiện.
6. Nếu đã capture, ghi refund obligation.
7. Order đi tới terminal state cùng metadata về nghĩa vụ còn tồn tại, hoặc giữ trạng thái trung gian đến khi điều kiện hoàn tất theo policy.

### 16.1. Hết hạn không phải một phép ghi tức thời toàn hệ

expiresAt có thể xác định khi quyền reservation hết hiệu lực theo policy. Nhưng cleanup vật lý, thông báo tới consumer và cập nhật projection có thể diễn ra sau.

Vì vậy không nên dùng “đã qua thời điểm” để tự cộng hàng về available ở service Order. Inventory sở hữu trạng thái reservation và quyết định release/expire có điều kiện.

### 16.2. Cancel cạnh tranh với confirm

Một lệnh ConfirmOrder và CancelOrder chạy đồng thời. Để tránh cả hai cùng thành công, Order cần state machine và cập nhật có điều kiện/version:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = :orderId
  AND status = 'PENDING_PAYMENT'
  AND version = :expectedVersion;
~~~

Nếu 0 row, command phải đọc lại/xử lý conflict; không được phát OrderConfirmed như đã thành công. Tương tự, lệnh Cancel phải bảo vệ chuyển trạng thái của mình.

---

## 17. Thiết kế Java/Spring: transaction cục bộ của Order

Ví dụ mã giả minh họa trách nhiệm của Order Service:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final OperationRepository operations;

    @Transactional
    public OrderId submit(SubmitOrderCommand command) {
        // Kiểm tra caller/tenant, payload và request key.
        // Unique constraint chống hai Submit đồng thời cùng intent.
        Operation op = operations.getOrCreate(command.requestKey());

        if (op.hasOrder()) {
            return op.orderId();
        }

        Order order = Order.pendingStock(command);
        orders.insert(order);
        operations.attachOrder(op.id(), order.id());

        outbox.append(CommandEnvelope.reserveStock(
            order.id(), command.requestKey()
        ));

        return order.id();
    }

    @Transactional
    public void onStockReserved(StockReservedEvent event) {
        Order order = orders.lockById(event.orderId());

        if (order.isCancelled()) {
            outbox.append(CommandEnvelope.releaseStock(
                event.reservationId(),
                "release-" + event.reservationId()
            ));
            return;
        }

        order.recordReservation(event.reservationId());
        order.transitionToPendingPayment();
        orders.save(order);

        outbox.append(CommandEnvelope.chargePayment(
            order.id(), order.paymentIntentKey()
        ));
    }
}
~~~

Đây là **mã giả định hướng kiến trúc**, chưa đủ import, transaction isolation, unique constraints, event dedup, version guard, retry logic hoặc xử lý errors để chạy production.

Điểm cần học:
- Order lưu tiến độ saga trong DB cục bộ.
- Outbox ghi command/event cần gửi trong transaction.
- Inventory và Payment vẫn tự quyết định nghiệp vụ của họ.
- Nếu StockReserved tới sau khi Order hủy, Order không tự chuyển lại PENDING; nó tạo nghĩa vụ release.
- Không gọi network tới Payment bên trong transaction Order đang giữ khóa dài.
- Phải bổ sung eventId dedup, optimistic/pessimistic concurrency và authorization.

### 17.1. Tách domain decision khỏi transport

Controller HTTP có thể gọi SubmitOrder, nhưng transition logic nên nằm trong module nghiệp vụ được kiểm thử. Một listener Kafka cũng dùng cùng transition rules, không bypass business invariants chỉ vì sự kiện đến từ broker.

### 17.2. Không dùng @Transactional như transaction xuyên microservices

@Transactional trong Spring áp dụng theo transaction manager/resource được cấu hình; nó không tự làm HTTP call tới Payment và update Inventory cùng commit với Order. Có các công nghệ transaction phân tán riêng, nhưng cần thiết kế rõ participant, coordinator và hạn chế; không xuất hiện tự động từ annotation.

### 17.3. Domain state machine

Ví dụ:

~~~java
enum OrderStatus {
    PENDING_STOCK,
    PENDING_PAYMENT,
    VERIFYING_PAYMENT,
    CONFIRMED,
    COMPENSATING,
    CANCELLED,
    REVIEW_REQUIRED
}

void confirm(PaymentEvidence evidence, InventoryEvidence reservation) {
    if (status != OrderStatus.PENDING_PAYMENT &&
        status != OrderStatus.VERIFYING_PAYMENT) {
        throw new InvalidTransitionException(status);
    }

    if (!evidence.capturedFor(this.id, this.amount, this.currency)) {
        throw new MissingPaymentEvidenceException();
    }

    if (!reservation.validFor(this.id)) {
        throw new InvalidReservationException();
    }

    this.status = OrderStatus.CONFIRMED;
}
~~~

Tất cả evidence cần được xác minh theo hợp đồng/nguồn thẩm quyền và phiên bản, không tự tin vào chuỗi status tùy ý từ client. Việc transition vào DB vẫn cần concurrency control.

---

## 18. Một bảng theo dõi tiến độ saga

Một coordinator cần lưu tiến độ bền vững, không chỉ một biến Boolean trong RAM.

Ví dụ bảng logic:

| Trường | Ý nghĩa |
|---|---|
| saga_id | Định danh quy trình |
| order_id | Aggregate chính |
| current_step | Bước hoặc giai đoạn hiện tại |
| workflow_status | RUNNING / COMPENSATING / COMPLETED / REVIEW_REQUIRED |
| stock_operation_id | Intent/operation tại Inventory |
| payment_operation_id | Intent/operation tại Payment |
| reservation_id | Quyền giữ hàng đã được owner xác nhận |
| attempt_count | Số lần thử theo policy |
| next_retry_at | Thời điểm tiếp tục nếu an toàn |
| deadline_at | Mốc xử lý hoặc đối soát |
| last_error_category | Loại lỗi, không phải kết luận chưa có effect |
| version | Concurrency guard |
| updated_at | Phục vụ quan sát |

Các bước thay đổi state và tạo command outbox nên được transaction cục bộ bảo vệ. Nếu worker crash, một worker khác có thể tiếp tục từ bản ghi và command IDs đã lưu.

### 18.1. Phân biệt “đã gửi” và “đã được chấp nhận”

Một command outbox được publish không đồng nghĩa Inventory đã giữ hàng. Một message được broker ACK không đồng nghĩa Payment đã capture. Coordinator nên ghi các mốc riêng:
- COMMAND_RECORDED.
- COMMAND_DISPATCHED.
- ACCEPTED_FOR_PROCESSING.
- BUSINESS_SUCCEEDED.
- BUSINESS_REJECTED.
- OUTCOME_UNKNOWN.

Trộn các mốc dẫn tới “đã gửi thì xem như thành công”.

### 18.2. Avoid busy polling

Nếu tất cả sagas pending đều GET Payment mỗi 50 ms, một provider chậm có thể bị flood. Dùng retry schedule có backoff/jitter, event-driven completion khi có thể, maximum attempts và ngân sách rate limit.

---

## 19. Cửa sổ nhất quán và giới hạn chờ

Không phải mọi eventual consistency đều giống nhau. Cần định nghĩa:

**Cửa sổ hội tụ kỳ vọng:** Sau event PaymentCaptured, Order read model thường cập nhật trong bao lâu?

**Giới hạn nghiệp vụ:** Một order chờ stock được phép pending tối đa bao lâu? Reservation có thể giữ chỗ bao lâu?

**Ngưỡng cảnh báo:** Khi pending age vượt mốc nào thì cần điều tra?

**Thời hạn pháp lý/operational:** Có nghĩa vụ hoàn tiền hoặc trả hàng phải giải quyết trong khoảng nào theo chính sách?

### 19.1. Thời hạn không đồng nghĩa SLA tuyệt đối

Ví dụ “95% event được áp dụng dưới 5 giây” là một SLO có điều kiện, không có nghĩa mọi event chắc chắn hội tụ đúng 5 giây. Một bước có nghĩa vụ không thể bỏ cần cách đối soát khi vượt mục tiêu.

### 19.2. Bounded inconsistency

Có thể đặt giới hạn theo:
- **Thời gian:** Chờ trạng thái trung gian không vượt ngưỡng cảnh báo.
- **Số lượng:** Tối đa N reservation pending.
- **Giá trị:** Tổng giá trị tiền ở trạng thái chưa xác minh không vượt risk limit.
- **Tài nguyên:** Quota hàng được giữ không vượt giới hạn.
- **Phạm vi:** Chỉ một subset chức năng được phép đọc dữ liệu stale.

Những ngưỡng này làm rủi ro có thể quản trị thay vì chỉ nói “cuối cùng sẽ nhất quán”.

### 19.3. Khi nào phải dùng sự phối hợp mạnh hơn?

Nếu một bất biến không thể chấp nhận sai dù chỉ một khoảng rất ngắn, và không thể biểu diễn bằng reservation/quota tại một owner, các lựa chọn gồm:
- Đưa dữ liệu và quyết định vào cùng transaction boundary.
- Dùng lock/serializable transaction trong nguồn có thẩm quyền.
- Dùng phân bổ quyền/quota trước để giảm phối hợp runtime.
- Dùng protocol điều phối commit mạnh hơn khi mọi participant thực sự hỗ trợ và đánh đổi về availability là chấp nhận được.
- Thay đổi quy trình nghiệp vụ để trạng thái trung gian hợp lệ.

Không nên giữ ranh giới microservices hiện tại bằng mọi giá nếu ranh giới ấy khiến bất biến cứng không thể bảo vệ.

---

## 20. 2PC và Saga: chọn đúng bài toán

**Two-Phase Commit (2PC)** là một mô hình điều phối transaction phân tán khi các tài nguyên hỗ trợ chuẩn bị và commit theo giao thức. Một coordinator có thể yêu cầu participants PREPARE, sau đó quyết định COMMIT hoặc ROLLBACK.

Điểm cần hiểu:
- 2PC có chi phí điều phối và có thể giữ khóa/tài nguyên trong thời gian chờ.
- Khi coordinator hoặc mạng lỗi, một số participant có thể bị chặn chờ quyết định.
- Nhiều API HTTP và nhà cung cấp thanh toán không hỗ trợ XA/2PC.
- 2PC không tự làm vấn đề latency, availability và business side effects biến mất.

**Saga** cho phép các transaction cục bộ commit rồi dùng bù trừ khi cần. Đổi lại, các trạng thái trung gian được công nhận, và một compensation không nhất thiết hoàn tác chính xác mọi hiệu lực.

| Tiêu chí | 2PC | Saga |
|---|---|---|
| Phạm vi | Participant hỗ trợ protocol transaction | Các bước nghiệp vụ với transaction cục bộ |
| Trạng thái giữa các bước | Cố gắng điều phối commit nguyên tử trong phạm vi participant | Có trạng thái đã commit một phần |
| Cơ chế lỗi | Điều phối commit/rollback ở giao thức | Retry, compensation, reconciliation |
| Chi phí | Locking, coordinator, blocking risk | State machine, nghiệp vụ bù trừ, phức tạp quan sát |
| External provider | Thường khó hoặc không hỗ trợ | Có thể mô hình bằng operations/compensation |
| Độ đúng | Trong giới hạn giao thức và participants | Phụ thuộc bất biến tại owner và protocol nghiệp vụ |

Không phải “Saga tốt hơn 2PC mọi lúc” hoặc “2PC luôn sai trong microservices”. Cần hiểu giao dịch và participant thực tế. Nhiều quy trình kinh doanh với hệ ngoài cần saga hoặc state machine vì không tồn tại rollback ACID toàn hệ.

---

## 21. UX: trạng thái trung gian phải được giải thích đúng

Người dùng không nên bị buộc hiểu cụm từ “eventual consistency”, nhưng giao diện cần thể hiện đúng sự thật.

Ví dụ:
- “Đang xác nhận đặt chỗ” khi reservation chưa được xác nhận.
- “Đang xử lý thanh toán” khi Payment có operation PENDING.
- “Thanh toán đã được ghi nhận, đang xác nhận đơn” nếu bằng chứng Payment đã có nhưng Order chưa hoàn tất bước tiếp.
- “Yêu cầu hủy đã được nhận, đang xử lý hoàn tiền” khi refund chưa có kết quả cuối.
- “Cần kiểm tra thêm” nếu đối soát chưa kết luận; kèm hướng dẫn và mã giao dịch.

Tránh:
- Hiển thị “Đặt hàng thành công” chỉ vì nhận HTTP 202.
- Hiển thị “Thanh toán thất bại” chỉ vì timeout.
- Cho người dùng liên tục nhấn nút thanh toán tạo paymentAttempt/key mới khi operation cũ chưa biết kết quả.
- Xóa hết lịch sử trạng thái trung gian khiến support không biết tiến trình đang ở đâu.

### 21.1. API trạng thái và polling

Một API có thể trả:

~~~http
GET /orders/ord-123/status
~~~

~~~json
{
  "orderId": "ord-123",
  "status": "VERIFYING_PAYMENT",
  "statusVersion": 7,
  "lastUpdatedAt": "2026-11-12T10:02:00Z",
  "operationId": "checkout-op-77",
  "nextAction": "WAIT"
}
~~~

Cần nêu source of truth và độ trễ có thể có của endpoint. Nếu API đọc projection, statusVersion/sourceVersion giúp consumer nhận biết cập nhật khi thích hợp.

### 21.2. Disable nút không thay thế idempotency

UI có thể vô hiệu hóa nút Submit sau lần nhấn đầu, nhưng người dùng có thể refresh, mở tab thứ hai hoặc gửi request trực tiếp. Service sở hữu vẫn phải chống tạo tác động trùng.

### 21.3. Cách hiển thị sau khi quá hạn

Khi quá hạn nhưng chưa biết Payment kết quả, có thể thông báo “Đang xác minh giao dịch, vui lòng không thử thanh toán lần nữa cho cùng đơn” nếu điều đó phù hợp. Hệ thống phải cung cấp support/operation ID và thời hạn cập nhật theo chính sách, không chỉ hiển thị spinner vô hạn.

---

## 22. Sự cố điển hình và ma trận hành động

| Sự cố | Điều có thể đã xảy ra | Điều không nên làm | Hướng xử lý |
|---|---|---|---|
| Inventory timeout | Reservation có thể đã commit | Gửi Reserve mới với key khác | Tra reservation/key; retry idempotent |
| Payment timeout | Provider có thể đã thu | Kết luận thất bại, thu lại ngay | VERIFYING, status query, reconciliation |
| Order crash sau commit | Order tồn tại, event chưa publish | Giả định chưa có order | Outbox và idempotent retry |
| Broker giao event trùng | Consumer thấy cùng sự thật hai lần | Tạo hai shipment hoặc hai email không kiểm soát | Dedupe/eventId, business idempotency |
| PaymentCaptured tới sau CancelOrder | Khoản thu có thể hiệu lực | Tự CONFIRM đơn đã hủy | Ghi nghĩa vụ refund/đối soát |
| ReleaseStock timeout | Hàng có thể đã release | Cộng stock trực tiếp ở Order | Tra trạng thái ở Inventory, retry cùng key |
| Reservation expire cùng lúc Confirm | Race tại Inventory | Hai transition đều thành công | State CAS/transaction/lock |
| Consumer nhận event out of order | Projection có thể lùi | Ghi đè theo arrival time | Version guard, replay/gap handling |
| Refund provider unavailable | Nghĩa vụ hoàn vẫn còn | Đánh dấu REFUNDED dù chưa có kết quả | REFUND_PENDING, retry/đối soát |
| Message nằm DLQ | Một bước chưa được áp dụng | Xóa DLQ cho dashboard xanh | Điều tra, replay có kiểm soát |
| Tất cả workers restart | Sagas pending còn trong DB | Mất state trong RAM | Durable state, leases/claiming |
| Customer cancel nhiều lần | Nhiều yêu cầu cùng intent | Phát nhiều compensation khác nhau | Idempotency và state machine |

### 22.1. Retry phải có ranh giới

Retry an toàn cần:
- Đúng loại lỗi có thể retry.
- Idempotency key ổn định.
- Exponential backoff/jitter và giới hạn lần thử.
- Không reset deadline tổng thể vô hạn.
- Tôn trọng rate limit/downstream capacity.
- Không retry command không thể chống trùng khi kết quả chưa biết.
- Có đường chuyển sang reconciliation/manual review khi vượt ngưỡng.

Một gateway, service, workflow engine và SDK provider cùng retry độc lập có thể gây retry storm. Cần chọn tầng có ngữ nghĩa phù hợp chịu trách nhiệm.

---

## 23. Monitoring và điều hành các trạng thái trung gian

Nếu hệ thống chỉ đếm HTTP 500 và CPU, một saga có thể kẹt 24 giờ mà không có lỗi rõ ở request.

Những chỉ số nên đo:

| Chỉ số | Tại sao quan trọng |
|---|---|
| Saga instances theo trạng thái | Có bao nhiêu đang PENDING, VERIFYING, COMPENSATING? |
| Pending age p50/p95/p99 và max | Có quy trình nào kẹt vượt giới hạn? |
| Time-to-terminal-state | Mất bao lâu để hoàn tất/hủy? |
| Compensation requested/completed/failed | Bù trừ có thực sự thành công? |
| Payment UNKNOWN outcome count | Mức rủi ro tài chính chưa đối soát |
| Payment reconciliation backlog và age | Công việc còn chờ nhà cung cấp |
| Inventory reservation active/expired/committed | Có hàng bị giữ không được giải phóng? |
| Duplicate commands/events | Tần suất replay và retry |
| Idempotency hits/conflicts | Chống trùng hoạt động và key bị dùng sai |
| Outbox backlog và oldest age | Có event không được publish? |
| Consumer lag, DLQ size và replay failures | Có projection/step bị trễ hoặc mất? |
| Optimistic lock/serialization conflicts | Race và contention |
| Deadlines exceeded by step | Bước nào thường vượt ngân sách? |
| Terminal state mismatch count | Chuyển trạng thái sai hoặc bằng chứng không phù hợp |
| Sum of pending monetary value | Tổng phơi nhiễm tiền đang chưa kết luận |
| Manual-review queue | Khả năng xử lý các trường hợp không tự khôi phục |
| User-visible status lag | Trải nghiệm người dùng chờ cập nhật bao lâu |

### 23.1. Những cảnh báo thiết thực

- Có Order ở VERIFYING_PAYMENT quá ngưỡng.
- Một reservation ACTIVE quá hạn mà Inventory chưa xử lý theo policy.
- Số refund obligations chưa hoàn tất tăng.
- Outbox oldest age vượt giới hạn.
- Bất biến cứng phát hiện vi phạm như available âm hoặc duplicate seat allocation (ưu tiên cao).
- Không còn worker/coordinator xử lý saga.
- Reconciliation backlog vượt năng lực xử lý.
- Một phần trăm bất thường PaymentCaptured tới sau CancelOrder.

Không xem mọi trạng thái PENDING là sự cố; đó là trạng thái bình thường trong giới hạn cho phép. Cần alert theo **tuổi, giá trị, tốc độ và tác động**.

### 23.2. Trace end-to-end

Các service có thể dùng correlationId, sagaId, orderId, reservationId và paymentAttemptId. Chúng phục vụ mục đích khác nhau:
- correlationId giúp liên kết trace/log.
- sagaId theo dõi tiến trình.
- orderId nhận diện đơn.
- reservationId là ID thuộc Inventory.
- paymentAttemptId là ID thuộc Payment.
- eventId nhận diện một sự kiện.
- idempotency key nhận diện cùng intent.

Không dùng trace ID thay idempotency key mới mỗi lần retry; làm vậy có thể phá chống trùng.

---

## 24. Đối soát: một trạng thái chưa biết cần được kết luận

**Reconciliation** là quy trình so sánh tình trạng theo nguồn có thẩm quyền, phát hiện thiếu/chênh và đưa vào hướng khôi phục phù hợp.

Một job đối soát Payment có thể:
1. Tìm paymentAttempt PENDING/UNKNOWN quá thời hạn.
2. Truy vấn provider bằng providerOperationId/idempotency key.
3. Kiểm tra kết quả nhận được theo hợp đồng.
4. Nếu CAPTURED, ghi trạng thái và event có thẩm quyền.
5. Nếu xác nhận DECLINED/NOT_EXECUTED an toàn, cập nhật tương ứng.
6. Nếu vẫn không thể biết, giữ NEEDS_RECONCILIATION và lên lịch tiếp/handoff.
7. Không phát Charge mới vô điều kiện để “thử xem”.
8. Audit từng lần đối soát và kết quả.

### 24.1. Đối soát không được làm sai nguồn

Order không nên tự sửa Payment database khi thấy provider transaction. Nếu việc đối soát là nhiệm vụ của Payment, Order chỉ yêu cầu tra/nhận kết quả từ Payment; Payment kiểm chứng với provider và công bố trạng thái.

### 24.2. Kiểm tra nghĩa vụ tồn đọng

Một saga đã terminal CANCELLED có thể còn RefundRequired chưa hoàn tất. Tùy định nghĩa trạng thái:
- Hoặc Order giữ REFUND_PENDING đến khi hoàn tiền xong.
- Hoặc Order=CANCELLED nhưng có một RefundOperation độc lập còn PENDING, được theo dõi bắt buộc.

Cả hai có thể hợp lệ nếu **contract không đánh đồng cancelled với refunded** và dashboard không bỏ qua nghĩa vụ tồn đọng.

### 24.3. Manual intervention phải an toàn

Khi nhân viên hỗ trợ can thiệp, cần:
- Phân quyền và audit.
- Hiển thị nguồn chứng cứ.
- Không cho ghi đè tùy ý các bất biến cứng.
- Idempotency cho thao tác thủ công.
- Trạng thái và lý do quyết định được lưu.
- Có thể tiếp tục tự động sau can thiệp mà không tạo tác dụng phụ trùng.

Một nút “Force success” không kiểm tra Payment evidence là rủi ro nghiêm trọng.

---

## 25. Kiểm thử: chứng minh hệ vẫn đúng khi một bước bị lỗi

Unit test một saga đi theo happy path không đủ. Cần kiểm thử sự xen kẽ và khôi phục của các transaction cục bộ.

### 25.1. Ma trận kiểm thử lỗi

1. Inventory reserve thành công nhưng response mất.
2. Inventory reserve thành công rồi Order crash trước khi lưu kết quả.
3. Payment provider capture thành công, HTTP timeout.
4. Order nhận PaymentCaptured sau khi bị Cancelled.
5. Hai ConfirmOrder/CancelOrder chạy đồng thời.
6. Reservation expires cùng lúc ConfirmReservation.
7. Message broker redelivers StockReserved ba lần.
8. PaymentCaptured version mới tới trước version cũ.
9. Publisher outbox crash sau publish trước mark-sent.
10. Consumer commit local state rồi crash trước ACK.
11. Refund command gửi hai lần cùng key.
12. Broker outage kéo dài trong khi DB vẫn hoạt động.
13. Saga coordinator restart giữa COMPENSATING.
14. Nhiều worker cùng lấy một saga đang pending.
15. Manual review hoàn tất đúng lúc job retry chạy lại.
16. Read model hiển thị dữ liệu cũ khi user gửi command mới.
17. Payment amount/currency trong event không khớp order.
18. Dependency phục hồi sau khi deadline nghiệp vụ đã hết.
19. Job đối soát phát hiện provider outcome mâu thuẫn trạng thái local.
20. Hàng nghìn sagas pending gây cạn connection/queue.

### 25.2. Các bất biến để assert

Không chỉ assert status code 200:
- Stock available không âm trong mô hình không cho vượt.
- Cùng reservation không release hai lần có effect.
- Cùng payment intent tạo tối đa một charge hiệu lực theo chính sách.
- Order CONFIRMED luôn có bằng chứng Inventory và Payment đúng liên kết.
- Order terminal không bị event cũ kéo lùi trạng thái.
- Refund total không vượt khoản có thể hoàn.
- Không có nghĩa vụ bù trừ bị mất sau crash.
- Idempotent retry trả trạng thái nhất quán.
- Mọi operation quá hạn có khả năng được phát hiện, giám sát và xử lý.

### 25.3. Kiểm thử tích hợp với datastore thật

Các đặc tính transaction isolation, unique constraint và locking khác nhau giữa DB engines. Không nên chỉ dùng mock repository để kết luận hai yêu cầu đồng thời sẽ an toàn.

Với Inventory, chạy hai transaction giữ ghế cuối. Kỳ vọng chỉ một thắng theo nguồn có thẩm quyền. Với Order, thử Confirm/Cancel đồng thời và kiểm tra version/status/side effects.

### 25.4. Fault injection có kiểm soát

Có thể giả lập network partition, delay headers/body, drop response sau commit, crash worker, tạm dừng broker và làm lệch thời điểm event tới. Với Payment, dùng sandbox/provider giả, không gây giao dịch tiền thật.

Một test có giá trị là “Order timeout sau Payment commit”:
- Payment đã ghi CAPTURED.
- Order nhận timeout và chuyển VERIFYING_PAYMENT.
- Retry cùng key không tạo charge thứ hai.
- Sự kiện hoặc status query đưa Order tới trạng thái đúng.
- Nếu Order đã CANCELLED, workflow tạo refund obligation có theo dõi.
- Không có đơn được CONFIRMED trái điều kiện.

### 25.5. Model-based testing

Với state machine quan trọng, có thể sinh nhiều chuỗi sự kiện/command khác nhau:
- StockReserved.
- PaymentCaptured.
- CancelRequested.
- ReservationExpired.
- Retry.
- WorkerCrash.
- PaymentStatusUnknown.

Kiểm tra mỗi trạng thái chuyển đều hợp lệ và những bất biến cứng không bị vi phạm. Cách này hữu ích để tìm race khó thấy trong happy path.

---

## 26. Những hiểu lầm phổ biến

**“Trạng thái trung gian nghĩa là dữ liệu đang sai.”** Không. Nó có thể là một trạng thái hợp lệ được công bố và quản lý.

**“Eventual consistency cho phép mọi bất biến sai tạm.”** Sai. Những điều kiện không được vi phạm phải bảo vệ ngay tại owner hoặc thiết kế bằng quyền/reservation phù hợp.

**“Mỗi service có transaction thì toàn saga atomic.”** Sai. Mỗi transaction chỉ bao phủ phạm vi tài nguyên được quản lý.

**“Saga rollback mọi thứ nếu lỗi.”** Sai. Compensation là thao tác nghiệp vụ mới; không phải mọi tác động đều đảo ngược được.

**“Payment timeout tức là chưa thu tiền.”** Sai. Có thể đã capture nhưng response bị mất.

**“HTTP 202 nghĩa là đã hoàn tất.”** Sai. Thường là đã nhận yêu cầu theo hợp đồng, còn kết quả sau.

**“Broker gửi đúng một lần nên consumer không cần idempotency.”** Không nên giả định. Nhiều hệ có redelivery và scope bảo đảm khác nhau.

**“Cứ nhận event cuối cùng là đúng.”** Sai. Event có thể sai thứ tự hoặc tới muộn sau terminal state.

**“Tạo key mới khi retry để tránh trùng request ID.”** Ngược lại, điều đó có thể tạo tác dụng phụ mới.

**“Chỉ cần một boolean orderPaid.”** Không đủ cho PROCESSING, CAPTURED, REFUNDED, UNKNOWN và những nghĩa vụ còn lại.

**“Bù trừ xong bằng cách xóa record.”** Sai. Cần audit, nguồn sự thật và bằng chứng trạng thái.

**“Chỉ cần @Transactional cho phương thức coordinator.”** Không tạo transaction ACID xuyên HTTP và các DB riêng.

**“Giữ mọi thứ trong một transaction dài có lock sẽ đơn giản.”** Có thể gây blocking, timeout và không hỗ trợ provider ngoài.

**“Mọi PENDING quá 10 giây là lỗi.”** Không nhất thiết. Cần ngưỡng theo workflow, SLO và rủi ro.

**“Một khi Order=CANCELLED thì không còn bất kỳ nghĩa vụ nào.”** Có thể vẫn cần refund/release/đối soát, tùy ngữ nghĩa terminal state.

**“Read model stale có thể dùng để quyết định giữ hàng.”** Không nếu bất biến không cho vượt quota; dùng owner hoặc reservation hợp lệ.

---

## 27. Quy trình thiết kế giao dịch phân tán

### Bước 1 — Liệt kê những sự thật cần giữ ngay

Viết mỗi bất biến cứng thành mệnh đề đo/kiểm thử được. Xác định service sở hữu và cơ chế transaction bảo vệ.

### Bước 2 — Liệt kê điều kiện có thể hội tụ

Ví dụ báo cáo cần phản ánh PaymentCaptured hoặc đơn bị hủy cuối cùng cần ReleaseReservation. Định nghĩa thời hạn kỳ vọng và cách đo, không dùng chữ “eventual” vô hạn.

### Bước 3 — Vẽ trạng thái trung gian

Tên trạng thái phải thể hiện điều hệ thống thật sự biết: PENDING_STOCK, VERIFYING_PAYMENT, REFUND_PENDING, REVIEW_REQUIRED. Tránh trạng thái SUCCESS khi chỉ ghi nhận command.

### Bước 4 — Chọn nguồn chứng cứ

Xác định ở đâu có thể biết một reservation hoặc charge đã có hiệu lực, ID tra cứu và kết quả nào đáng tin. Không dùng cache/projection cũ làm quyết định cuối cho bất biến cứng.

### Bước 5 — Thiết kế các command theo owner

ReserveStock/ReleaseReservation thuộc Inventory; Charge/Refund thuộc Payment; Confirm/CancelOrder thuộc Order. Mỗi command cần authorization, idempotency và transition guard.

### Bước 6 — Chọn cách điều phối

Orchestration hoặc choreography theo sự phức tạp và yêu cầu quan sát. Lưu tiến độ bền vững, có thể tiếp tục sau crash.

### Bước 7 — Thiết kế compensation và giới hạn

Với mỗi bước đã commit, nếu quy trình không thành, có thể làm gì? Nếu không thể hoàn tác, phương án sửa chữa là gì, ai chịu trách nhiệm và thời gian nào?

### Bước 8 — Thiết kế transport resilience

Outbox/inbox, duplicate handling, ordering, retry policy, DLQ, deadline, trạng thái unknown outcome và giới hạn quá tải.

### Bước 9 — Thiết kế trải nghiệm và API

Người dùng thấy trạng thái nào, có thể gửi lại không, dùng operationId nào, bao giờ được hỗ trợ? Không hiển thị kết quả chưa được owner xác nhận.

### Bước 10 — Kiểm thử và quan sát

Test race, crash, duplicate, timeout trước/sau commit, compensation thất bại và đối soát. Đặt metric cho tuổi pending, nghĩa vụ tồn đọng và bất biến cứng.

---

## 28. Bài thực hành: đặt vé với thanh toán và hoàn tiền

Một nền tảng bán vé có:
- **TicketInventory:** Sở hữu số ghế khả dụng và reservation.
- **Checkout:** Sở hữu phiên giao dịch mua vé và trạng thái đơn.
- **Payment:** Sở hữu paymentAttempt và refundOperation.
- **TicketIssuer:** Chỉ phát vé khi đã có đủ bằng chứng.
- **Notification:** Gửi email sau khi có kết quả.

Giả định:
- Sự kiện có 100 ghế; đã giữ/bán 99 ghế.
- Hai người cùng yêu cầu ghế cuối.
- Một trong hai request ReserveSeat thành công nhưng phản hồi bị mất.
- Cổng thanh toán capture thành công sau khi Checkout hết timeout.
- User có thể nhấn Cancel trong lúc Payment đang PROCESSING.
- Broker có thể phát lại PaymentCaptured.
- Reservation có TTL 10 phút.
- Một RefundOperation có thể mất vài giờ để provider kết luận.
- Read model cập nhật trễ vài giây.

### Yêu cầu

1. Viết tối thiểu bốn bất biến cứng và bốn điều kiện hội tụ có thời hạn. Nêu service sở hữu.
2. Giải thích vì sao TicketInventory phải kiểm tra và cấp ghế nguyên tử thay vì Checkout đọc available rồi tự trừ.
3. Xây state machine cho Checkout với các trạng thái PENDING_SEAT, PENDING_PAYMENT, VERIFYING_PAYMENT, CONFIRMED, CANCELLING, REFUND_PENDING, CANCELLED và REVIEW_REQUIRED.
4. Thiết kế ReserveSeat command, reservationId, expiration policy và idempotency key cho mỗi intent.
5. Nêu cách tránh hai người cùng giữ ghế cuối khi request đến đồng thời.
6. Phân tích race khi ConfirmSeat và ExpireSeat đến gần cùng thời điểm.
7. Khi ReserveSeat timeout nhưng đã commit, Checkout phải làm gì trước khi gửi lệnh giữ tiếp?
8. Khi PaymentCaptured đến sau CancelRequested, làm sao bảo vệ Order state và tạo nghĩa vụ RefundRequired?
9. Khi broker phát lại PaymentCaptured ba lần, những unique keys/version nào cần kiểm tra?
10. Giải thích vì sao refund là compensation chứ không phải rollback của charge.
11. Nếu provider refund lỗi 2 giờ, người dùng nên thấy trạng thái nào và vận hành cần metric gì?
12. Viết ba integration tests: tranh ghế cuối, timeout sau Payment commit, cancel/confirm race.
13. Thiết kế dashboard theo dõi pending age, refund obligations và outbox lag.
14. Đề xuất cách xử lý nếu TicketIssuer đã phát vé trước khi Checkout phát hiện một payment outcome sai.
15. Viết ADR ngắn cho quyết định chọn saga hay TCC/reservation trong trường hợp này.

### Gợi ý tư duy

TicketInventory phải giữ bất biến “không cấp ghế vượt quota” ngay tại điểm ghi. Checkout được phép chờ Payment và có trạng thái trung gian rõ; nó không được CONFIRM khi thiếu bằng chứng thanh toán. Payment timeout cần VERIFYING_PAYMENT và status query/idempotency, không được mặc định FAILED.

Khi Payment đã capture nhưng Checkout bị hủy, refund là nghĩa vụ nghiệp vụ mới và có thể chưa hoàn tất. Nếu refund đang chờ, cần phản ánh đúng với khách và hệ hỗ trợ, thay vì ghi “đã hoàn tiền” ngay. Những event trùng hoặc đến trễ phải được xử lý theo version, attempt ID và state machine.

---

## 29. Mẫu ADR: bất biến và trạng thái trung gian

~~~text
ADR: Giao dịch phân tán cho <business process>

Mục tiêu nghiệp vụ và rủi ro:
Các service và chủ sở hữu dữ liệu:
Bất biến cục bộ bắt buộc giữ tức thời:
Điều kiện toàn quy trình cho phép hội tụ:
Những điều kiện không thể tạm vi phạm:
Cửa sổ hội tụ/SLO và giới hạn pending:

State machine:
  Trạng thái trung gian:
  Trạng thái kết thúc:
  Trạng thái unknown/reconciliation:
  Chuyển trạng thái bị cấm:

Commands và evidence:
  Operation IDs, idempotency keys:
  API/events có thẩm quyền:
  Authorization/tenant scope:
  Version, ordering và duplicate handling:

Consistency controls:
  Transaction cục bộ/aggregate:
  Unique/conditional update/lock:
  Reservation/quota/TTL:
  TCC/Saga/2PC: phương án được chọn và đánh đổi:

Failure recovery:
  Timeout trước/sau commit:
  Retry/backoff/maximum attempts:
  Outbox/inbox:
  Compensation và giới hạn hoàn tác:
  Manual review và reconciliation:
  Tác động không thể đảo ngược:

UX:
  Status API và thông điệp cho người dùng:
  Cancellation policy:
  Support/audit:

Observability:
  Pending age, stuck operations:
  Outbox/DLQ/reconciliation:
  Monetary/risk exposure:
  Alert và runbook:

Tests:
  Concurrent updates:
  Network partition, crash, duplicate:
  Late event/terminal state:
  Compensation failure:

Owner, decision date, rủi ro còn lại và điều kiện review:
~~~

## 30. Ghi nhớ

1. **Trạng thái trung gian là một phần hợp lệ của mô hình nghiệp vụ phân tán** khi được định nghĩa rõ và có đường kết thúc/khôi phục.
2. **Bất biến cứng không được phép sai chỉ vì dùng eventual consistency.** Chúng cần được bảo vệ tại owner qua transaction và concurrency control.
3. **Điều kiện toàn quy trình có thể hội tụ sau**, nhưng phải có giới hạn, SLO, trạng thái và cơ chế đối soát.
4. **Saga điều phối các transaction cục bộ**, không tạo ACID toàn cục; compensation có thể không đảo ngược hoàn toàn side effect.
5. **Reservation/TCC** giúp giữ tài nguyên trước khi chốt mà không vi phạm quota, nhưng phải xử lý expiry, confirm/cancel race và retry.
6. **Timeout không đồng nghĩa thất bại**: một khoản tiền có thể đã thu hoặc reservation có thể đã commit; cần unknown outcome và status query.
7. **Outbox, idempotency và event version** là những cơ chế bổ trợ để không mất event, không nhân đôi effect và không lùi state vì thông điệp trễ.
8. **Trạng thái Order không phải trạng thái Payment/Inventory.** Mỗi service chỉ khẳng định điều nó sở hữu và consumer dùng bằng chứng đúng phiên bản.
9. **Compensation cần được theo dõi đến kết quả**, kể cả khi phải chuyển sang review thủ công; không xóa nghĩa vụ chỉ để kết thúc saga.
10. **Thiết kế đúng phải chứng minh safety và liveness dưới lỗi mạng, crash, retry và concurrency**, đồng thời giải thích trung thực trạng thái cho người dùng.
