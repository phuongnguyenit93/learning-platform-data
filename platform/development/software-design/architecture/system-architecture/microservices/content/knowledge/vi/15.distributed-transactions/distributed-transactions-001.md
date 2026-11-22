# Vì sao giao dịch ACID cục bộ không bao phủ nhiều dịch vụ

## Mục tiêu bài học

Trong một ứng dụng đơn thể sử dụng một database, nhà phát triển quen với việc đặt nhiều câu lệnh SQL trong cùng một giao dịch: nếu tất cả thành công thì COMMIT; nếu một câu lệnh thất bại thì ROLLBACK. Tính chất ACID của database giúp những thay đổi thuộc phạm vi giao dịch đó có hành vi nhất quán và có thể dự đoán được.

Khi tách hệ thống thành Microservices, một luồng nghiệp vụ thường trải qua nhiều service, nhiều cơ sở dữ liệu và cả những hệ thống bên ngoài như cổng thanh toán, nhà vận chuyển hoặc email provider. Mỗi service có thể thực hiện giao dịch ACID trên database của riêng mình, nhưng **COMMIT của Order Service không làm Payment Service hoặc Inventory Service tự động COMMIT cùng; ROLLBACK của Order Service cũng không hoàn tác những side effect mà dịch vụ khác đã thực hiện**.

Đây là vấn đề trung tâm của **giao dịch phân tán**: đảm bảo các bất biến nghiệp vụ trong khi nhiều hệ thống độc lập có thể lỗi, chậm, không nhận được thông báo hoặc phản hồi không đúng thứ tự.

Sau bài học, bạn có thể:
- Giải thích chính xác ACID bảo đảm điều gì và trong phạm vi nào.
- Phân biệt local transaction, distributed transaction, distributed workflow và eventual consistency.
- Phân tích những khoảng lỗi giữa COMMIT database và lời gọi API hoặc publish event.
- Hiểu vì sao đặt @Transactional trong Spring Boot không tạo transaction xuyên Microservices.
- So sánh Saga, transactional outbox, idempotency, reconciliation và 2-phase commit (2PC).
- Xây dựng state machine cho quy trình đặt hàng, giữ tồn kho và thanh toán.
- Kiểm thử những lỗi mà happy-path integration test thường bỏ sót.

## 1. ACID là gì?

ACID là bốn thuộc tính quen thuộc của giao dịch cơ sở dữ liệu:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Atomicity | Trong một giao dịch, các thay đổi được commit hoặc rollback theo đơn vị giao dịch | Trừ tiền và tăng số dư ở hai tài khoản trong cùng DB |
| Consistency | Giao dịch chuyển database từ trạng thái hợp lệ sang trạng thái hợp lệ theo các ràng buộc đã thiết kế | UNIQUE, FOREIGN KEY, CHECK, logic nghiệp vụ trong transaction |
| Isolation | Giao dịch đồng thời được cách ly theo mức isolation và cơ chế database hỗ trợ | Tránh các dạng tranh chấp không được phép |
| Durability | Dữ liệu đã commit được lưu bền vững theo cam kết của database | Restart không làm mất transaction đã được xác nhận |

ACID không có nghĩa database tự hiểu mọi quy tắc nghiệp vụ. Nếu ứng dụng không khai báo và kiểm tra một invariant, database không thể đoán ra invariant đó. Isolation cũng có các mức khác nhau, như READ COMMITTED, REPEATABLE READ hoặc SERIALIZABLE, với khả năng xuất hiện anomaly khác nhau.

Quan trọng hơn, **ACID có phạm vi**: thường là một transaction được database/transaction manager cụ thể quản lý. Một câu lệnh COMMIT trong Order DB không phát tín hiệu thần kỳ đến Inventory DB, Kafka hay một PSP để tất cả cùng commit.

### 1.1. Local transaction hoạt động tốt khi cùng nguồn dữ liệu

Ví dụ chuyển tiền trong một database:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 'A';

UPDATE accounts
SET balance = balance + 100
WHERE id = 'B';

INSERT INTO ledger_entries(id, description)
VALUES ('tx-100', 'Transfer 100 from A to B');

COMMIT;
~~~

SQL chỉ minh họa; hệ thống thực tế còn cần kiểm tra số dư, khóa/điều kiện cập nhật, loại tiền, ledger invariants và xử lý concurrency. Nhưng cả ba thao tác ở cùng database có thể nằm dưới một transaction manager và một COMMIT.

Nếu có lỗi trước commit, transaction có thể rollback toàn bộ các thay đổi cục bộ. Nếu commit được xác nhận, durability giúp lưu lại kết quả theo bảo đảm của database.

### 1.2. Local consistency không đồng nghĩa global consistency

Một database Orders có thể luôn nhất quán theo các constraint của nó: mọi Order có trạng thái hợp lệ và tổng tiền không âm. Một database Payments có thể cũng nhất quán: mọi Payment có identifier duy nhất và trạng thái nằm trong tập cho phép.

Tuy vậy, toàn hệ thống vẫn có thể có:

~~~text
Orders DB:    order-471 = CONFIRMED
Payments DB:  payment-471 = REJECTED
Inventory DB: reservation-471 = NOT_FOUND
~~~

Cả ba database có thể không vi phạm constraint cục bộ nào, nhưng invariant nghiệp vụ “đơn CONFIRMED phải có tiền và tồn kho đã được giữ” đã bị vi phạm.

Bài toán phân tán xuất hiện ở **mối quan hệ giữa các nguồn sự thật độc lập**, không nhất thiết do từng database thiếu ACID.

## 2. Ví dụ checkout xuyên ba dịch vụ

Giả sử một luồng thanh toán cần:

1. Order Service tạo đơn chờ xử lý.
2. Inventory Service giữ tồn kho.
3. Payment Service authorize tiền qua PSP.
4. Order Service xác nhận đơn.

~~~text
Client
  |
  v
Order Service ----> Orders DB
  |
  +-------------> Inventory Service ----> Inventory DB
  |
  +-------------> Payment Service ------> Payments DB
                              |
                              v
                         External PSP
~~~

Các bước cục bộ:

~~~text
Order transaction:
    INSERT Order(PENDING)
    COMMIT

Inventory transaction:
    Reserve SKU for order
    COMMIT

Payment transaction:
    INSERT Payment(PENDING)
    COMMIT
    Call PSP
    UPDATE Payment(AUTHORIZED)
    COMMIT

Order transaction:
    UPDATE Order(CONFIRMED)
    COMMIT
~~~

Đây là **nhiều local transactions**, không phải một transaction ACID toàn cục.

### 2.1. Sự cố sau khi Inventory COMMIT

~~~text
Order              Inventory             Payment
  |                    |                     |
  | -- Reserve ------> |                     |
  |                    | COMMIT reservation  |
  | <--- RESERVED ---- |                     |
  |                                          |
  | ------------ Authorize ----------------> |
  |                                          | PSP REJECTED
  | <------------ REJECTED ------------------ |
  |
  ? Reservation đã commit; làm sao rollback?
~~~

Order không thể gọi ROLLBACK trên connection của chính nó để xóa reservation ở Inventory. Nó cần gửi một **hành động nghiệp vụ khác**, như ReleaseReservation, do Inventory thực hiện theo quy tắc riêng.

### 2.2. Sự cố sau khi PSP đã authorize

~~~text
Order                 Payment                  PSP
  |                      |                      |
  | -- Authorize ------> |                      |
  |                      | -- Authorize ------> |
  |                      |                      | Approved
  |                      | <--- response lost X |
  | <----- timeout ----- X                      |
  |
  ? PSP đã giữ tiền, nhưng Order không biết.
~~~

Nếu Order coi timeout là thất bại rồi tạo payment mới, hệ thống có thể authorize hai lần. Nếu tự hủy đơn ngay, PSP vẫn có thể giữ tiền. Local ACID ở Order không thể giải quyết việc **mất thông tin về trạng thái của một side effect bên ngoài**.

### 2.3. Sự cố giữa database COMMIT và publish event

~~~text
Order Service
  |
  +-- INSERT Order(PENDING)
  +-- COMMIT Orders DB
  +-- Crash
  X-- Publish OrderCreated to Kafka
~~~

Database có Order, nhưng các consumer không biết sự kiện tồn tại. Nếu đổi thứ tự publish trước commit, event có thể được consumer xử lý dù database transaction sau đó rollback.

Đây là **dual-write problem**: ghi vào DB và phát một thông điệp là hai side effects độc lập, không tự nằm trong một transaction ACID chung.

## 3. Vì sao @Transactional trong Spring Boot không đủ?

Spring hỗ trợ transaction management qua các transaction manager. Một service có thể khai báo:

~~~java
@Service
public final class CheckoutService {
    private final OrderRepository orderRepository;
    private final InventoryClient inventoryClient;
    private final PaymentClient paymentClient;

    @Transactional
    public void checkout(CheckoutCommand command) {
        Order order = orderRepository.save(
            Order.pending(command.orderId()));

        inventoryClient.reserve(order.id(), command.items());
        paymentClient.authorize(order.id(), command.amount());

        order.confirm();
    }
}
~~~

Nhiều người lầm tưởng: nếu authorize thất bại, Spring rollback toàn bộ, bao gồm reservation đã được Inventory ghi. **Không phải vậy.**

Trong một cấu hình JPA/SQL thông thường, @Transactional quản lý giao dịch của Order Service với Orders DB. Lời gọi HTTP đến Inventory và Payment không tham gia transaction đó. Các service kia có connection, transaction manager và commit của riêng họ.

Khi PaymentClient ném exception:
- Order transaction có thể rollback, tùy exception/rollback rule.
- Inventory transaction **có thể đã commit**.
- PSP **có thể đã authorize**.
- Không có cơ chế mặc định để Spring gửi rollback có hiệu lực đến các hệ thống kia.

### 3.1. Kéo dài transaction qua HTTP còn có rủi ro khác

Khi giữ @Transactional mở trong suốt các lời gọi mạng:
- Database connection có thể bị giữ lâu.
- Row locks hoặc snapshot có thể tồn tại tới lúc HTTP call xong.
- Một downstream chậm khiến transaction dài và tăng contention.
- Caller timeout không nhất thiết dừng downstream.
- Deadlock hoặc pool exhaustion trở nên dễ xuất hiện hơn.

Một nguyên tắc thực tế là **giữ local transaction ngắn**, tập trung vào thao tác database của service; tách điều phối workflow và các I/O bên ngoài ra khỏi critical transaction khi thiết kế cho phép.

### 3.2. Một local transaction vẫn hữu ích

Không nên kết luận “Microservices không dùng transaction”. Mỗi service vẫn cần ACID để bảo vệ dữ liệu mà nó sở hữu.

Inventory có thể dùng transaction để:
- Kiểm tra và giảm available stock theo cách concurrency-safe.
- Ghi reservation có khóa nghiệp vụ duy nhất.
- Ghi event intent vào outbox.
- Commit tất cả thay đổi cục bộ cùng nhau.

Saga hoặc workflow không thay ACID cục bộ; chúng **dựa vào các local transactions tin cậy** để tạo thành quy trình dài.

## 4. Điều gì xảy ra khi có nhiều database?

Giả sử Order Service dùng PostgreSQL, Inventory Service dùng MySQL và Payments dùng một API của PSP. Mỗi hệ thống quản lý commit log, lock, transaction ID và failure recovery của riêng mình.

~~~text
Transaction Manager A                Orders DB
        |                               |
        +-- BEGIN / UPDATE / COMMIT ---> |

Transaction Manager B                Inventory DB
        |                               |
        +-- BEGIN / UPDATE / COMMIT ---> |

External PSP
        |
        +-- Business API transaction (không có SQL rollback chung)
~~~

Không có một transaction manager cục bộ nào có quyền điều khiển toàn bộ ba hệ thống. Dù mọi service đều dùng cùng một loại database, việc có **nhiều database/connection/owner độc lập** vẫn tạo ranh giới transaction.

Thậm chí một service có hai DataSource cũng không tự có atomic commit trên cả hai chỉ vì một method được annotation @Transactional. Phải biết transaction manager nào được chọn và resource nào thực sự tham gia.

### 4.1. Phạm vi transaction phải được mô tả rõ

Khi xem một đoạn code có @Transactional, hãy hỏi:
1. Transaction manager nào được dùng?
2. Resource nào nằm trong transaction này?
3. Commit thực hiện ở thời điểm nào?
4. Có HTTP, broker, email hoặc PSP call nào bên trong?
5. Nếu JVM chết ngay sau commit thì còn side effect nào chưa thực hiện?
6. Nếu downstream thành công nhưng response mất thì xác minh thế nào?
7. Các local invariants và global invariants được bảo vệ ở đâu?

Nếu không trả lời được các câu trên, annotation không phải chứng cứ tính đúng xuyên dịch vụ.

## 5. ACID không tự cung cấp atomicity xuyên mạng

Trong một transaction local, database có khả năng kiểm soát và khôi phục trạng thái của các resource nó quản lý. Trong môi trường phân tán, các bên có thể:
- Mất kết nối với nhau.
- Có clock và lịch xử lý khác nhau.
- Commit rồi crash trước khi gửi xác nhận.
- Nhận cùng request nhiều lần.
- Xử lý message trễ hoặc đảo thứ tự.
- Có thời điểm restart và replay khác nhau.

Một coordinator có thể gửi một lệnh, nhưng **không thể suy ra tình trạng side effect chỉ từ timeout**.

Ví dụ:

~~~text
t0 Order gửi reserve(order-471)
t1 Inventory nhận request
t2 Inventory commit reservation
t3 Response RESERVED bị mất
t4 Order timeout

Quan sát ở Order: chưa xác định.
Sự thật ở Inventory: reservation đã tồn tại.
~~~

Đây không phải lỗi của ACID cục bộ: Inventory thực hiện transaction đúng. Vấn đề là hai service **không có một kết luận giao dịch chung trong một bước commit duy nhất**.

## 6. Atomicity của dữ liệu và atomicity của workflow là hai chuyện

Hãy phân biệt:

**Local data atomicity:** Trong Inventory DB, giảm available và ghi Reservation cùng thành công hoặc cùng rollback.

**Global workflow consistency:** Nếu Payment bị từ chối, cuối cùng không còn reservation gây khóa hàng vô ích và Order không được coi là CONFIRMED.

Workflow consistency có thể đòi một chuỗi thao tác có trạng thái trung gian:

~~~text
Order PENDING
      |
      v
Inventory RESERVED
      |
      v
Payment REJECTED
      |
      v
Release inventory
      |
      v
Order CANCELLED
~~~

Trong khoảng giữa Payment REJECTED và Release thành công, hệ thống có thể có một trạng thái chưa hoàn chỉnh. Điều này có thể được chấp nhận nếu quy tắc nghiệp vụ, deadline, retry và observability được thiết kế rõ.

**Eventual consistency** nghĩa là các phần của hệ thống có thể tạm thời khác nhau rồi hội tụ theo cơ chế xác định; nó không có nghĩa “cứ để sai rồi tự khắc đúng”.

## 7. Các mô hình bảo đảm khi có nhiều dịch vụ

| Mô hình | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Một local DB transaction | ACID mạnh trong phạm vi một DB | Không bao phủ API và DB bên ngoài |
| Distributed transaction / 2PC | Có thể phối hợp atomic commit giữa resource hỗ trợ | Coupling, availability và vận hành phức tạp |
| Saga | Ghép local transactions và compensations | Không tạo rollback ACID tức thời toàn cục |
| Transactional outbox | Ghi domain state + event intent atomically trong một DB | Publish có thể trùng; không commit với PSP |
| Inbox/idempotent consumer | Hạn chế side effect trùng khi message redelivery | Cần unique keys và state transitions đúng |
| Reconciliation | Tìm trạng thái thật khi response mơ hồ | Không đảm bảo kết quả tức thì |
| TCC (Try-Confirm-Cancel) | Dùng reservation tường minh trước confirm | Yêu cầu tất cả participant hỗ trợ protocol |
| Workflow orchestrator | Có owner, timeline và state machine bền | Phải thiết kế recovery, idempotency, compensation |

Không tồn tại lựa chọn tự động tốt nhất cho mọi bài toán. Quyết định phụ thuộc mức nhất quán cần thiết, latency, khả năng hợp tác của participant, số lượng dịch vụ và chấp nhận trạng thái trung gian.

## 8. Two-Phase Commit (2PC) giải quyết được gì?

2PC là một protocol phối hợp commit giữa nhiều resource managers có hỗ trợ.

Đơn giản hóa:

~~~text
Phase 1: PREPARE
Coordinator -> DB A: prepare
Coordinator -> DB B: prepare
Participants vote YES/NO; resources may be locked

Phase 2: COMMIT or ABORT
Coordinator -> DB A: commit or rollback
Coordinator -> DB B: commit or rollback
~~~

Nếu tất cả participants chuẩn bị thành công, coordinator quyết định commit. Nếu có participant không chuẩn bị được, coordinator có thể yêu cầu abort.

### 8.1. Vì sao không mặc định dùng 2PC cho mọi Microservice?

- Không phải mọi hệ thống hỗ trợ cùng một distributed transaction protocol.
- HTTP API, email và nhiều PSP không phải XA resource tham gia prepare/commit.
- Participants có thể cần giữ locks/resource trong giai đoạn chuẩn bị.
- Coordinator failure và network partition tạo trạng thái in-doubt/phụ thuộc recovery.
- Tăng coupling giữa availability của các participants.
- Khó vượt qua ranh giới team, cloud, vendor và geographic region.
- Vận hành, monitoring và transaction timeout phức tạp.

2PC không “bất khả thi” trong mọi trường hợp. Nó có thể phù hợp với những resource XA tương thích trong phạm vi kiểm soát, với yêu cầu atomicity cao và chấp nhận đánh đổi. Nhưng nó không phải cơ chế mặc định của @Transactional khi gọi nhiều Microservices qua HTTP.

### 8.2. XA/JTA là công cụ cụ thể, không phải phép màu

JTA/XA có thể phối hợp resource được hỗ trợ; cần cấu hình transaction manager, XA drivers, recovery log và xử lý failure states. Nếu một participant là PSP hoặc dịch vụ REST không triển khai protocol này, nó không tự tham gia giao dịch.

Dù có 2PC cho hai database, **hành vi bên ngoài protocol** như email gửi đi vẫn không thể rollback nguyên trạng chỉ bằng một COMMIT/ABORT.

## 9. Saga: nhiều local transactions thành một workflow

Saga là cách tổ chức một chuỗi local transactions, mỗi bước có action và khi cần có **compensating action** để xử lý tác động của bước trước.

Một quy trình ví dụ:

~~~text
T1: CreateOrder(PENDING)
          |
          v
T2: ReserveInventory
          |
          v
T3: AuthorizePayment
          |
          v
T4: ConfirmOrder

Nếu T3 bị REJECTED:
  C2: ReleaseInventory
  C1: CancelOrder
~~~

Mỗi T hoặc C là một thao tác nghiệp vụ tại service sở hữu dữ liệu; nó có thể được bảo vệ bởi local ACID và một business operation identity.

### 9.1. Compensation không phải SQL rollback

Refund không phải undo một giao dịch capture theo nghĩa xóa sạch lịch sử. ReleaseInventory không phải ROLLBACK transaction ReserveInventory đã COMMIT. Compensation là **một nghiệp vụ mới**:
- Có thể thất bại.
- Có thể bị retry.
- Có thể cần phê duyệt.
- Có thể không khôi phục chính xác trạng thái ban đầu.
- Có thể bị hạn chế theo thời gian hoặc policy.

Ví dụ một email đã gửi không thể bị “gỡ khỏi hộp thư” bằng compensation. Một chuyến hàng đã rời kho có thể không thể hủy ngay. Saga cần xác định bước nào có thể bù trừ và bước nào là điểm không thể hoàn tác tự động.

### 9.2. Giao dịch định kỳ khác transaction ACID

Saga có thể duy trì invariants cuối cùng và giới hạn trạng thái trung gian, nhưng không đảm bảo toàn hệ thống nhìn thấy một snapshot toàn cục atomic tại mọi thời điểm. Người dùng có thể nhìn thấy Order PENDING và Payment AUTHORIZED trong một khoảng ngắn trước khi Order CONFIRMED.

Do đó nên thiết kế status và UX phản ánh thực tế, không che giấu trạng thái trung gian bằng việc báo thành công quá sớm.

## 10. Saga orchestration và choreography

### Orchestration

Một coordinator quyết định bước tiếp theo:

~~~text
Checkout Coordinator
   |
   +--> Order: create pending
   +--> Inventory: reserve
   +--> Payment: authorize
   +--> Order: confirm
   |
   +--> Nếu thất bại:
         Inventory: release
         Order: cancel
~~~

Ưu điểm:
- Workflow có owner rõ.
- Dễ nhìn trạng thái từng bước.
- Dễ quyết định timeout, retry và compensation theo một chính sách.

Nhược điểm:
- Coordinator có thể thành thành phần phức tạp.
- Cần lưu bền state, xử lý restart, duplicate replies và version workflows.
- Nếu nhét mọi business rule vào coordinator, có nguy cơ coupling giữa các domain.

### Choreography

Các service phản ứng theo event:

~~~text
OrderCreated
     |
     v
Inventory reserves -> InventoryReserved
     |
     v
Payment authorizes -> PaymentAuthorized
     |
     v
Order confirms
~~~

Ưu điểm:
- Service phản ứng theo hợp đồng sự kiện.
- Không cần một central workflow service cho mọi bước.
- Có thể giảm coupling điều phối trực tiếp.

Nhược điểm:
- Khó thấy toàn bộ workflow nếu phân tán logic quá nhiều nơi.
- Lỗi event, thứ tự và retries có thể tạo trạng thái khó debug.
- Cần quy tắc rõ về owner, deadlines, timeouts và compensation.

Cả hai cách đều phải xử lý idempotency, event publication, recovery và các business invariants. Chuyển từ HTTP sang Kafka **không tự biến workflow thành transaction ACID**.

## 11. Thiết kế state machine cho checkout

Một Order có thể có các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| CREATED | Đơn mới được tiếp nhận |
| PENDING_INVENTORY | Chờ giữ tồn |
| PENDING_PAYMENT | Đã giữ tồn, chờ xác minh thanh toán |
| CONFIRMED | Có chứng cứ các điều kiện bắt buộc đã thỏa |
| CANCELLING | Đang giải phóng tài nguyên/bù trừ |
| CANCELLED | Đã hoàn thành luồng hủy theo quy tắc |
| NEEDS_RECONCILIATION | Có outcome chưa xác định |
| MANUAL_REVIEW | Không thể tự động kết luận |

Một invariant:

~~~text
Order.CONFIRMED
  implies InventoryReservation = RESERVED
  and PaymentAuthorization = AUTHORIZED
~~~

Invariant này phải được bảo vệ bằng điều kiện chuyển trạng thái, không chỉ bằng “hai lời gọi HTTP đều trả 200” vì response có thể đến muộn, trùng hoặc mất.

### 11.1. Không cố làm mọi trạng thái đồng bộ tức thời

Khi Payment đã AUTHORIZED nhưng response mất, Order có thể còn PENDING_PAYMENT hoặc NEEDS_RECONCILIATION. Đây là trạng thái đúng hơn so với báo REJECTED, tạo payment mới hoặc CONFIRMED khi chưa có bằng chứng.

Có thể đưa ra thông điệp cho client:
- “Đang xử lý thanh toán, vui lòng kiểm tra lại.”
- Trả operation ID để hỏi trạng thái.
- Tránh buộc client click lại một command không idempotent.

## 12. Transactional outbox và khoảng trống DB–Broker

Một thiết kế thường gặp:

~~~java
@Transactional
public void createOrder(CreateOrderCommand cmd) {
    orderRepository.save(Order.pending(cmd.orderId()));
    kafkaTemplate.send("orders", new OrderCreated(cmd.orderId()));
}
~~~

Có hai vấn đề:
1. Nếu database commit nhưng message chưa được broker xác nhận, event có thể bị mất.
2. Nếu broker nhận event nhưng DB transaction sau đó rollback, consumer có thể xử lý một Order không tồn tại.

Một transaction annotation không tự commit nguyên tử với broker trừ khi có protocol/guarantee cụ thể được triển khai; các cơ chế “synchronize” transaction với broker thường vẫn cần hiểu failure windows, không nên suy ra atomic end-to-end.

### 12.1. Outbox

Trong cùng một local DB transaction, ghi domain state và ý định phát event:

~~~sql
BEGIN;

INSERT INTO orders (id, status)
VALUES ('order-471', 'PENDING');

INSERT INTO outbox_events (
  event_id, aggregate_id, event_type, payload, status
) VALUES (
  'evt-471', 'order-471', 'OrderCreated',
  '{"orderId":"order-471"}', 'NEW'
);

COMMIT;
~~~

Một relay hoặc CDC lấy outbox records rồi publish:

~~~text
Orders DB
  |
  +--- orders table
  |
  +--- outbox table
           |
           v
      Outbox relay
           |
           v
          Broker
           |
           v
      Downstream consumers
~~~

Sau commit, nếu process crash, outbox record vẫn tồn tại để relay phục hồi. Đây là điểm mạnh của outbox.

### 12.2. Outbox không có nghĩa message đến chính xác một lần

Relay có thể publish xong rồi crash trước khi đánh dấu đã gửi. Sau restart, cùng event có thể được phát lại.

Do đó consumer phải idempotent:
- Dùng eventId hoặc business operationId.
- Ghi inbox/dedup record có unique constraint.
- Bảo vệ trạng thái nghiệp vụ trong local transaction.
- Chịu được event đến muộn, trùng và đảo thứ tự theo contract.

Outbox bảo vệ **không bỏ mất ý định phát event sau local commit**, chứ không làm các dịch vụ downstream commit chung một transaction.

## 13. Inbox và idempotent consumer

Giả sử Inventory nhận OrderCreated hai lần vì broker redelivery.

Nếu handler chỉ làm:

~~~text
on OrderCreated:
  available_stock -= qty
  insert reservation
~~~

thì hai lần nhận có thể giảm tồn hai lần. Handler phải được định danh theo một ý định nghiệp vụ, ví dụ reservationKey = orderId + sku + purpose.

Một cấu trúc bảng:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE reservations (
    reservation_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    UNIQUE (order_id, sku)
);
~~~

Handler cần xử lý duplicate cùng một transaction cục bộ:
1. Claim event ID hoặc reservation key bằng unique constraint.
2. Kiểm tra stock và điều kiện nghiệp vụ.
3. Ghi reservation và cập nhật tồn.
4. Commit.
5. Ack message sau khi local commit theo semantics broker.

Nếu consumer crash sau commit trước ack, broker có thể gửi lại; unique constraint và state machine ngăn side effect lặp.

### 13.1. EventId không thay thế business idempotency

Hai eventIds khác nhau có thể cùng biểu diễn một business intent nếu upstream retry sai. Vì thế nên bảo vệ cả:
- Deduplicate message theo eventId.
- Deduplicate nghiệp vụ theo orderId/reservation purpose.
- Chống thay đổi payload của cùng identity ngoài ý muốn.

Các ràng buộc phải phù hợp domain, không tự giả định mỗi order chỉ có một SKU hoặc một reservation nếu nghiệp vụ cho phép nhiều dòng.

## 14. Idempotency cho API đồng bộ

Nếu Order gọi Payment và nhận timeout, Payment có thể đã authorize. Retry phải dùng **cùng operation identity** nếu contract cho phép.

~~~http
POST /payment-authorizations
Idempotency-Key: order-471-authorize-v1
Content-Type: application/json

{
  "orderId":"order-471",
  "amountMinor":159900,
  "currency":"VND"
}
~~~

Payment service cần:
- Scope key theo tenant/merchant và operation.
- Lưu request fingerprint để phát hiện key reuse khác payload.
- Claim key atomically; concurrent requests cùng key chỉ có một side effect.
- Trả kết quả đã lưu hoặc PENDING cho retry.
- Có endpoint query status theo key/operation ID.
- Dùng stable reference khi gọi PSP nếu provider hỗ trợ.
- Có retention và unique business constraint đủ lâu.

Không tạo key mới cho mỗi retry. Không coi timeout là kết quả REJECTED.

### 14.1. Unknown outcome là trạng thái thật

~~~text
Request sent
   |
   +-- Response success ------------> SUCCEEDED
   +-- Business rejection ----------> REJECTED
   +-- Timeout / reset -------------> UNKNOWN
                                         |
                                         v
                                    RECONCILING
                                     /  |   \
                                    v   v    v
                               SUCCEEDED REJECTED UNRESOLVED
~~~

Nếu PSP query trả NOT_FOUND từ một hệ thống eventually consistent, chưa chắc có thể kết luận giao dịch không xảy ra. Cần hiểu provider contract, webhook, merchant reference và audit/reconciliation.

## 15. Reconciliation giải quyết trạng thái chưa xác định

Reconciliation là quy trình đối chiếu các nguồn dữ liệu có thẩm quyền để biết side effect đã xảy ra hay chưa và đưa hệ thống về trạng thái hợp lệ.

Ví dụ Payment Service không nhận PSP response:
1. Ghi Payment UNKNOWN với operation ID cố định.
2. Gửi query trạng thái tới PSP theo merchant reference.
3. Xử lý webhook có chữ ký và chống replay.
4. Nếu PSP xác nhận AUTHORIZED, ghi kết quả có thẩm quyền.
5. Nếu PSP xác nhận DECLINED, ghi business rejection.
6. Nếu vẫn UNKNOWN, đặt lịch retry inquiry có backoff.
7. Quá giới hạn tự động, tạo manual review và audit trail.

Không phải mọi lỗi phân tán đều được giải quyết chỉ bằng retry. Nếu một khoản tiền đã được thu nhưng DB nội bộ chưa ghi kết quả, retry command capture có thể thu lần hai. **Cần biết mình đang retry việc tra cứu hay retry một side effect**.

### 15.1. Compensation cũng có thể UNKNOWN

Order yêu cầu Inventory ReleaseReservation rồi timeout. Inventory có thể đã release thành công. Nếu coordinator gửi một lệnh release khác không idempotent, available stock có thể bị tăng hai lần.

Vì vậy compensating action cũng cần:
- Operation identity.
- Business state guard.
- Idempotency.
- Status query và reconciliation.
- Retry budget, deadline và monitoring.

## 16. TCC: Try–Confirm–Cancel

TCC chia nghiệp vụ thành ba giai đoạn được participant hỗ trợ:

- **Try:** giữ tài nguyên theo một reservation có TTL hoặc điều kiện.
- **Confirm:** xác nhận sử dụng tài nguyên đã giữ.
- **Cancel:** giải phóng reservation.

~~~text
Order Coordinator
   |
   +-- Inventory.TryReserve(orderId, qty)
   +-- Payment.TryAuthorize(orderId, amount)
   |
   +-- If all eligible:
   |      Inventory.Confirm
   |      Payment.Confirm
   |
   +-- If failed:
          Inventory.Cancel
          Payment.Cancel/void
~~~

TCC giúp biểu diễn tài nguyên đã giữ và quyết định cuối rõ ràng trong những domain hỗ trợ. Nhưng:
- Không phải PSP hay external system nào có Try/Confirm/Cancel phù hợp.
- Confirm hoặc Cancel có thể timeout.
- Reservation TTL có thể hết hạn giữa các bước.
- Cần quản lý duplicate, concurrency và recovery.
- Vẫn không phải một transaction SQL ACID toàn cục.

TCC phù hợp với nghiệp vụ có khái niệm “hold/reserve/confirm” rõ, không phải giải pháp dùng tự động cho mọi service.

## 17. Bất biến nghiệp vụ và biên nhất quán

Không phải mọi dữ liệu cần global strong consistency. Cần phân loại các invariant.

### 17.1. Invariants nên giữ trong cùng một owner/local transaction

Ví dụ:
- Tổng số đơn vị reserved không được vượt inventory có sẵn.
- Một payment operation ID không được capture hai lần.
- Một order state transition phải tuân thủ quy tắc hợp lệ.
- Một ledger entry phải có khóa duy nhất và cân đối theo nghiệp vụ.

Đưa các quyết định đòi atomicity mạnh vào service sở hữu dữ liệu và local database transaction của nó khi khả thi.

### 17.2. Invariants có thể kiểm tra xuyên workflow

Ví dụ:
- Order chỉ CONFIRMED sau khi có bằng chứng InventoryReserved và PaymentAuthorized.
- Nếu PaymentRejected, cuối cùng reservation phải được release hoặc xử lý thủ công.
- Nếu OrderCancelled sau authorize, tiền giữ phải được void theo policy.
- Các projections có thể chậm cập nhật nhưng không làm sai quyết định quan trọng.

Điểm quan trọng là định nghĩa **khi nào** invariant phải đúng: trước khi trả success, cuối cùng trong deadline, hay tại mọi thời điểm. Một hệ thống không thể kiểm thử điều “eventually” nếu không xác định timeout và dấu hiệu hoàn tất.

## 18. Isolation và các race xuyên dịch vụ

Ngay cả khi từng service có local ACID, các cuộc đua phân tán vẫn có thể xảy ra.

Ví dụ:
- Hai Checkout attempts cho cùng cart.
- PaymentAuthorized event đến sau OrderCancelled.
- InventoryReserved event được replay sau một lần cancel.
- Customer thay địa chỉ trong khi Shipping tạo vận đơn.

Một Order state machine cần guard:

~~~text
PENDING_PAYMENT + PaymentAuthorized -> CONFIRMED
CANCELLED + PaymentAuthorized       -> handle late payment/void
CONFIRMED + duplicate PaymentAuthorized -> no-op
~~~

State transition nên được thực hiện atomic theo version hoặc điều kiện trạng thái:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = :id
  AND status = 'PENDING_PAYMENT'
  AND version = :expected_version;
~~~

Nếu updated row count = 0, không được kết luận tự động operation đã thất bại; cần đọc trạng thái mới rồi quyết định idempotent/no-op/reconciliation theo contract.

**Saga không tự giải quyết race**. Cần domain state guards, versioning, idempotency và event ordering strategy.

## 19. Ví dụ Spring Boot: tách local transaction khỏi điều phối

Một thiết kế port-oriented:

~~~java
public record CheckoutCommand(
    String orderId,
    String customerId,
    long totalMinor
) {}

public enum CheckoutState {
    PENDING_INVENTORY,
    PENDING_PAYMENT,
    CONFIRMED,
    CANCELLING,
    CANCELLED,
    NEEDS_RECONCILIATION
}

public interface InventoryPort {
    ReservationResult reserve(
        String operationId, String orderId);
    ReservationResult getStatus(String operationId);
    void release(String releaseOperationId, String reservationId);
}

public interface PaymentPort {
    PaymentResult authorize(
        String operationId, String orderId, long amountMinor);
    PaymentResult getStatus(String operationId);
}
~~~

Order Service có thể dùng local transaction để lưu state và event/outbox:

~~~java
@Service
public class OrderStateService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderStateService(
        OrderRepository orders,
        OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void createPending(CheckoutCommand cmd) {
        Order order = Order.pending(
            cmd.orderId(), cmd.customerId(), cmd.totalMinor());
        orders.save(order);
        outbox.save(OutboxEvent.orderCreated(order.id()));
    }

    @Transactional
    public void markInventoryReserved(
            String orderId, String reservationId) {
        Order order = orders.findByIdForUpdate(orderId);
        if (order.isAlreadyInventoryReserved(reservationId)) {
            return;
        }
        order.onInventoryReserved(reservationId);
        outbox.save(OutboxEvent.inventoryStateChanged(orderId));
    }
}
~~~

Đây là ví dụ định hướng kiến trúc, không phải source code hoàn chỉnh để chạy ngay. Order, repositories, DTOs, event factory và phương thức khóa cần được hiện thực theo domain. Quan trọng là local transaction **chỉ quản lý những thay đổi do Order Service sở hữu**.

### 19.1. Coordinator làm việc ngoài transaction dài

Một coordinator hoặc durable workflow engine có thể:
1. Ghi ý định checkout theo operation ID.
2. Gửi lệnh ReserveInventory có idempotency key ổn định.
3. Chờ hoặc tra cứu reservation status.
4. Nếu RESERVED, gửi AuthorizePayment với identity riêng.
5. Khi AUTHORIZED, chuyển Order sang CONFIRMED trong local transaction.
6. Nếu REJECTED, điều phối ReleaseInventory rồi CANCELLED.
7. Nếu UNKNOWN, lưu trạng thái và thực hiện reconciliation.

Không giữ một database transaction mở xuyên tất cả HTTP calls. Coordinator cần lưu state bền, timers và retries; nếu nó restart giữa các bước, có thể tiếp tục từ checkpoint mà không tạo side effect trùng.

### 19.2. @Transactional ở Inventory chỉ bảo vệ Inventory

~~~java
@Service
public class ReserveInventoryUseCase {
    private final StockRepository stock;
    private final ReservationRepository reservations;
    private final OutboxRepository outbox;

    @Transactional
    public ReservationResult reserve(ReserveCommand cmd) {
        Reservation existing =
            reservations.findByBusinessKey(cmd.operationId());

        if (existing != null) {
            return ReservationResult.from(existing);
        }

        boolean ok = stock.tryReserveAtomically(
            cmd.sku(), cmd.quantity());

        if (!ok) {
            return ReservationResult.rejected("OUT_OF_STOCK");
        }

        Reservation reservation =
            reservations.save(Reservation.reserved(cmd));
        outbox.save(OutboxEvent.reservationCreated(reservation));
        return ReservationResult.reserved(reservation.id());
    }
}
~~~

Code minh họa logic cơ bản. Kiểm tra existing rồi insert phải được bảo vệ bằng unique constraint/atomic claim để chống hai requests đồng thời. tryReserveAtomically cần đảm bảo không oversell dưới concurrency; không chỉ đọc available rồi update không khóa.

Hệ thống thực tế cũng cần xử lý quantity, multi-SKU reservation, rollback khi insert thất bại và business key scope phù hợp.

## 20. Vì sao HTTP timeout không nói transaction đã rollback?

Một remote service có thể đã COMMIT rồi mới gửi response:

~~~text
Order client                  Inventory server
    |                                |
    |--- reserve ------------------> |
    |                                | BEGIN
    |                                | UPDATE stock
    |                                | INSERT reservation
    |                                | COMMIT
    | <------ response lost --- X    |
    |                                |
    | Timeout                        |
~~~

Order chỉ biết nó không nhận response. Nó không biết:
- Request chưa đến.
- Server đã commit.
- Server đang xử lý.
- Response gửi rồi bị mất.

Lúc này trạng thái kết quả đúng là UNKNOWN, không phải FAILED. Một endpoint query status theo operation ID có thể giúp:

~~~http
GET /reservations/by-operation/order-471-reserve-v1
~~~

Nếu trả RESERVED có thẩm quyền, Order có thể đi tiếp. Nếu NOT_FOUND, cần hiểu consistency/retention của endpoint; 404 từ replica chậm không luôn chứng minh side effect chưa từng xảy ra.

## 21. Event delivery và event ordering

Một hệ thống có broker có thể cung cấp:
- At-most-once delivery trong một số cấu hình.
- At-least-once delivery khá phổ biến.
- Các cơ chế exactly-once trong phạm vi broker/stream processing cụ thể.

Không nên diễn giải “exactly-once” của broker thành **exactly-once business side effect xuyên database, HTTP và PSP**. Consumer vẫn cần dedup và business constraints.

### 21.1. Event trùng

Một OrderCreated có thể đến hai lần. Inventory phải dựa vào reservation business key để không trừ stock lần hai.

### 21.2. Event đến muộn

PaymentAuthorized tới sau OrderCancelled. Order cần transition rule xử lý late payment và có thể kích hoạt void/reconciliation, không tự mở lại Order nếu business không cho phép.

### 21.3. Event đảo thứ tự

OrderUpdated version 7 có thể được consume trước version 6 do partitioning hoặc retry. Cần version/sequence và chính sách xử lý:
- Bỏ qua event cũ.
- Đợi/retry event thiếu.
- Rebuild projection từ authoritative source.
- Dùng per-key ordering nếu broker hỗ trợ và phù hợp.

Không dựa vào timestamp wall-clock giữa nhiều service như một thứ tự toàn cục tuyệt đối nếu không có cơ chế hỗ trợ.

## 22. Ranh giới dữ liệu và quyền sở hữu

Nếu Ordering và Inventory cùng ghi vào một database/tập bảng, chúng có thể tạo một số transaction chung ở cấp kỹ thuật, nhưng điều đó làm mất đi ranh giới ownership và deploy independence.

Microservices thường ưu tiên:
- Mỗi service sở hữu dữ liệu và business invariants của mình.
- Service khác trao đổi qua API hoặc integration event có contract.
- Read models/projections được xây riêng cho nhu cầu truy vấn.
- Không dựa vào JOIN/FK xuyên service để cam kết global atomicity.
- Không dùng một shared DB transaction để che giấu coupling nghiệp vụ dài.

Điều này là một **đánh đổi kiến trúc**. Nếu một invariant thật sự cần transaction atomic mạnh và nhiều bước gắn chặt không thể bù trừ, có thể nên giữ chúng trong cùng bounded context/service/database thay vì tách nhỏ chỉ để có nhiều Microservices.

## 23. Khi nào không nên tách một giao dịch ra nhiều dịch vụ?

Một dấu hiệu boundary được chia sai là hai khả năng nghiệp vụ phải:
- Commit hoặc rollback đồng thời ở mọi request.
- Giữ khóa chung để duy trì invariant.
- Luôn deploy và kiểm thử như một đơn vị.
- Liên tục gọi đồng bộ qua lại trong một transaction nghiệp vụ nhỏ.
- Không có compensation hợp lệ hoặc thời gian hội tụ chấp nhận được.

Ví dụ một quy tắc ledger yêu cầu các bút toán debit/credit cân đối **ngay trong một transaction**. Một Ledger Service sở hữu toàn bộ invariant và dùng local ACID có thể phù hợp hơn việc chia debit và credit thành hai service gọi nhau qua HTTP.

Tách service theo ownership/bounded context và yêu cầu nhất quán, không tách theo tên bảng hoặc số lượng class.

## 24. Bù trừ và các giao dịch không thể đảo ngược

Không phải step nào cũng có compensation đơn giản.

| Side effect | Compensation thường thấy | Giới hạn |
| --- | --- | --- |
| Giữ tồn kho | Release reservation | Hàng có thể hết hạn, cần idempotency |
| Authorize tiền | Void authorization | PSP có policy/thời gian riêng |
| Capture tiền | Refund | Có phí, thời gian và audit, không giống rollback |
| Tạo shipment label | Cancel label | Không thể nếu hàng đã bàn giao |
| Gửi email | Gửi email đính chính | Không thu hồi email đã đọc |
| Ghi audit | Ghi correction entry | Không xóa lịch sử đã công bố |

Cần xác định **pivot transaction**: bước sau đó khó hoặc không thể hoàn tác, ví dụ hàng đã giao cho vận chuyển. Trước pivot, nhiều hành động có thể dùng reservation/cancel. Sau pivot, quy trình có thể cần nghiệp vụ bù trừ khác, manual intervention hoặc refund.

### 24.1. Không giấu partial failure

Nếu refund hoặc release thất bại, đừng báo workflow đã CANCELLED hoàn toàn nếu vẫn còn tài nguyên chưa được giải phóng. Có thể dùng trạng thái CANCELLING, COMPENSATION_PENDING hoặc MANUAL_REVIEW và đưa vào monitoring.

Tính đúng đôi khi là **nhận diện và quản lý trạng thái chưa hoàn tất một cách rõ ràng**, không phải giả vờ toàn bộ bước đều đã rollback.

## 25. Designing timeouts, retries và deadlines

Mỗi bước của saga cần có:
- Stable operation ID.
- Per-call timeout.
- Retry policy phù hợp ngữ nghĩa.
- Tổng deadline của workflow hoặc business SLA.
- Backoff và jitter.
- Maximum attempts.
- Status query/reconciliation.
- Dead-letter/manual review khi không thể tự phục hồi.

Không nên đặt mọi bước có timeout 30 giây rồi giữ transaction cục bộ mở trong suốt. Chia riêng **thời gian chờ phản hồi** và **thời gian cho phép nghiệp vụ hoàn tất**.

Ví dụ:
- HTTP request checkout có thể trả 202 PENDING sau một thời gian ngắn.
- Payment reconciliation có thể tiếp tục sau đó.
- UI dùng GET /checkout-operations/{id} để kiểm tra.
- Nếu phát hiện AUTHORIZED muộn, hệ thống hoàn tất hoặc void theo trạng thái Order và policy.

### 25.1. Retry amplification

Nếu client, gateway, Order và Payment cùng retry ba lần, tải tới PSP có thể nhân lên nhiều lần. Cần một chủ thể chịu trách nhiệm retry, truyền deadline, có retry budget, rate limit và circuit breaker ở nơi phù hợp.

Circuit breaker giảm tải đến downstream lỗi, nhưng không xác nhận kết quả của command đã gửi trước đó.

## 26. Cấu trúc một durable workflow record

Một coordinator có thể lưu:

~~~text
checkout_operations(
    operation_id,
    order_id,
    state,
    inventory_operation_id,
    reservation_id,
    payment_operation_id,
    payment_id,
    attempt_count,
    last_error,
    next_retry_at,
    deadline_at,
    version,
    created_at,
    updated_at
)
~~~

Những điều cần bảo vệ:
- Một operation ID không bị dùng lại cho ý định khác.
- Mọi state transition atomic theo version hoặc row lock.
- Không mất tiến độ sau restart.
- Tạo command/outbox cùng transaction với thay đổi state.
- Có owner/timer để xử lý các operation bị treo.
- Ghi đủ reference để query upstream/downstream khi outcome UNKNOWN.
- Không lưu secrets hoặc PII không cần thiết.

Nếu mọi bước chỉ nằm trong memory của một HTTP controller, khi process crash sẽ mất bối cảnh phục hồi.

## 27. Bảo mật và tính đúng nghiệp vụ

Giao dịch phân tán còn liên quan quyền truy cập:
- Mỗi lệnh phải xác thực service identity/caller phù hợp.
- Idempotency key được scope theo tenant/merchant và operation.
- Không chỉ dựa vào việc có key để cho truy vấn payment của tenant khác.
- Internal events không được tin tuyệt đối nếu thiếu authentication/authorization và provenance.
- Dữ liệu tài chính cần audit trail, đối soát amounts/currencies và immutable references.
- Không log card number, credentials hoặc dữ liệu cá nhân không cần thiết.
- Compensation chỉ thực hiện khi trạng thái và quyền nghiệp vụ cho phép.

Một state machine đúng về concurrency nhưng thiếu authorization vẫn có thể tạo giao dịch sai.

## 28. Observability cho các bước phân tán

Nên lưu và truyền:
- Global checkoutOperationId.
- OrderId và các business resource IDs.
- Inventory reservationOperationId.
- Payment operationId và PSP merchant reference.
- Event ID, causation ID và correlation ID.
- Trace ID cho mỗi attempt.
- Current workflow state và version.
- Retry count, last observed error, deadline và nextReconcileAt.

Các metrics:
- Số saga PENDING/UNKNOWN và thời gian treo.
- Tỷ lệ hoàn tất, cancel, compensation và manual review.
- Số duplicate commands/events bị ngăn.
- Tỷ lệ timeout theo dependency.
- Thời gian từ OrderCreated đến CONFIRMED/CANCELLED.
- Outbox backlog và thời gian publish.
- Inbox dedup rate, DLQ count, consumer lag.
- Bất biến nghiệp vụ bị vi phạm, như order confirmed thiếu payment hoặc double reservation.

Không gắn mỗi order ID làm metric label vì có thể tăng cardinality rất lớn. Logs/traces/audit có thể chứa IDs theo chính sách quyền và retention phù hợp.

## 29. Kiểm thử lỗi theo thời điểm

Một hệ thống phân tán cần fault injection đúng những điểm khó.

### Case 1 — Order DB commit, process crash trước publish

Kỳ vọng: outbox giữ event intent, relay phục hồi; Inventory nhận lệnh sau restart.

### Case 2 — Inventory commit, response mất

Kỳ vọng: Order giữ UNKNOWN, query reservation hoặc retry cùng idempotency key; không giảm stock lần hai.

### Case 3 — Payment PSP approve, response mất

Kỳ vọng: Payment reconcile theo stable reference; Order không tạo payment mới hoặc báo REJECTED sai.

### Case 4 — Broker redeliver OrderCreated

Kỳ vọng: Inbox và unique reservation business key không tạo duplicate.

### Case 5 — PaymentRejected nhưng ReleaseInventory timeout

Kỳ vọng: coordinator giữ COMPENSATION_PENDING/UNKNOWN, query release status, không tăng tồn hai lần.

### Case 6 — PaymentAuthorized event đến sau OrderCancelled

Kỳ vọng: state transition từ CANCELLED có guard; xử lý late authorization qua void/reconciliation theo policy, không tự CONFIRMED.

### Case 7 — Coordinator restart giữa các bước

Kỳ vọng: durable workflow state và timers giúp tiếp tục đúng checkpoint, không gửi business intent mới.

### Case 8 — Hai checkout requests cùng order ID

Kỳ vọng: operation uniqueness và atomic claim ngăn hai workflows độc lập cùng tạo payment/reservation.

### Case 9 — One downstream outage

Kỳ vọng: timeouts, circuit breaker và retry budget ngăn toàn hệ thống bị treo; workflow có owner phục hồi.

### Case 10 — Backlog event và replay

Kỳ vọng: consumer idempotency, version handling và reconciliation đưa projection về trạng thái phù hợp.

### Case 11 — Manual review

Kỳ vọng: những giao dịch không rõ PSP result vượt deadline được phát hiện, lưu audit và không biến mất khỏi hệ thống.

### Case 12 — Rollback release

Kỳ vọng: code cũ và mới đều hiểu những workflow states/events tồn tại trong giai đoạn chuyển tiếp, không làm kẹt các saga đã chạy.

Đánh giá theo **business invariants** chứ không chỉ HTTP status: không có hai payment captures cho một intent, không oversell, không xác nhận đơn thiếu chứng cứ, không mất compensation và không có workflow UNKNOWN bị quên.

## 30. Các hiểu lầm thường gặp

**“Có @Transactional thì mọi lời gọi trong method đều rollback.”** Không đúng. Nó thường bảo vệ các resource của transaction manager cục bộ, không bao phủ HTTP calls hay PSP.

**“Mọi service đều ACID nên toàn hệ thống cũng ACID.”** Không đúng. Global invariants có thể bị vi phạm trong khi từng DB cục bộ nhất quán.

**“Chỉ cần gọi API theo đúng thứ tự.”** Không đủ. Mạng có thể timeout, response mất và process crash giữa các lần gọi.

**“Đổi sang Kafka thì trở thành atomic.”** Không đúng. Message delivery, DB commit và side effects bên ngoài vẫn có failure windows.

**“Outbox đảm bảo exactly-once delivery.”** Không nhất thiết. Relay có thể publish trùng; consumer cần idempotency.

**“Saga rollback mọi thứ như SQL transaction.”** Không đúng. Compensation là business action riêng, có thể thất bại và không đảo ngược hoàn toàn.

**“Retry timeout chắc chắn an toàn.”** Không đúng với command có side effect nếu thiếu stable key, unique constraint hoặc status query.

**“2PC luôn là giải pháp tốt nhất.”** Không hẳn; phải có participants hỗ trợ và chấp nhận trade-offs về coupling, lock, recovery và availability.

**“Eventual consistency nghĩa là không cần quy tắc.”** Ngược lại, cần định nghĩa thời điểm hội tụ, invariant và cách phục hồi.

**“Một global trace ID đủ ngăn duplicate.”** Trace ID giúp quan sát, nhưng không thay business operation ID, idempotency và unique constraint.

**“Compensation thất bại thì cứ báo CANCELLED.”** Có thể che giấu tài nguyên chưa được release. Phải theo dõi trạng thái bù trừ chưa hoàn tất.

**“Chia nhỏ service luôn tốt hơn.”** Nếu invariant cần ACID mạnh và không thể chia workflow, giữ bước đó trong một owner/service có thể đúng hơn.

## 31. Checklist kiến trúc

Trước khi triển khai một workflow xuyên nhiều service:

- [ ] Những service nào sở hữu dữ liệu và business invariants?
- [ ] Các local transactions nằm ở đâu và commit khi nào?
- [ ] Có bất kỳ HTTP/broker/PSP side effect nào ngoài local transaction?
- [ ] Global invariant cần đúng tức thời hay sau một khoảng thời gian?
- [ ] Nếu cần strong atomicity, có nên giữ invariant trong một service?
- [ ] Có cần distributed transaction/2PC, Saga hay TCC? Vì sao?
- [ ] Saga có owner, durable state, deadlines và retry budget?
- [ ] Mỗi command có stable operation ID và idempotency semantics?
- [ ] Local business action và outbox intent có cùng DB transaction?
- [ ] Consumer xử lý event trùng, muộn và đảo thứ tự?
- [ ] Có status inquiry/reconciliation cho mọi external side effect quan trọng?
- [ ] Mỗi compensation có identity, retry/reconcile và trạng thái riêng?
- [ ] Có bảo vệ race và state transitions bằng unique constraints/version?
- [ ] Có phương án khi process crash sau commit nhưng trước response/publish?
- [ ] Không giữ long-running local DB transaction xuyên network calls?
- [ ] Có metric, alert và manual review cho workflow treo?
- [ ] Các trạng thái PENDING/UNKNOWN được phản ánh đúng trong API/UI?
- [ ] Đã fault-inject ở từng điểm giữa local commits và messages?
- [ ] Các phiên bản app/event tương thích khi rolling deployment?
- [ ] Có audit và authorization phù hợp với dữ liệu giao dịch?

## 32. Bài tập thực hành

### Bài tập 1 — Local rollback và tồn kho

Order Service mở @Transactional, gọi Inventory.reserve thành công rồi Payment.authorize trả REJECTED. Order transaction rollback.

**Câu hỏi:** Inventory reservation có tự rollback không? Cần làm gì?

**Gợi ý:** Không. Inventory đã commit trong DB riêng. Order cần điều phối ReleaseReservation có idempotency và xác nhận trạng thái bù trừ.

### Bài tập 2 — Mất response sau khi PSP approve

Payment Service gọi PSP, PSP approve nhưng response bị mất.

**Câu hỏi:** Có thể coi Payment FAILED và authorize một intent mới không?

**Gợi ý:** Không. Lưu UNKNOWN, query PSP bằng stable reference, xử lý webhook, giữ idempotency key cũ và reconcile trước khi side effect mới.

### Bài tập 3 — DB commit rồi Kafka chưa publish

Order đã được lưu trong DB, process crash trước khi gửi OrderCreated.

**Câu hỏi:** Vì sao @Transactional không cứu được? Dùng gì?

**Gợi ý:** DB và broker là hai resource độc lập. Transactional outbox lưu event intent cùng local commit; relay publish sau đó, consumer idempotent.

### Bài tập 4 — Duplicate event

Inventory nhận OrderCreated hai lần do broker redelivery.

**Câu hỏi:** Làm sao không giữ stock hai lần?

**Gợi ý:** Inbox/dedup eventId, reservation business key có unique constraint và local transaction atomic.

### Bài tập 5 — Event đến muộn

Order đã CANCELLED; một PaymentAuthorized event cũ tới sau.

**Câu hỏi:** Có được chuyển Order sang CONFIRMED không?

**Gợi ý:** Không tự động. State machine cần guard, reconcile/void payment theo policy và audit late event.

### Bài tập 6 — Đánh đổi 2PC

Ba hệ thống gồm Orders PostgreSQL, Inventory MySQL và một PSP REST. Team muốn dùng XA/2PC cho cả ba.

**Câu hỏi:** Giải pháp này có bao phủ PSP không?

**Gợi ý:** Chỉ nếu PSP thật sự là participant hỗ trợ protocol phù hợp; một API REST thanh toán thông thường không tự tham gia prepare/commit. Cân nhắc Saga/TCC/reconciliation.

### Bài tập 7 — Ranh giới service

Một luồng chuyển khoản đòi debit và credit cân đối ngay, không thể để một bên commit rồi chờ phút sau bù trừ.

**Câu hỏi:** Có nên tách debit/credit thành hai services và dùng saga không?

**Gợi ý:** Xem lại bounded context; có thể giữ ledger postings trong cùng service/database transaction để bảo vệ invariant mạnh, rồi phát integration events cho các domain khác.

### Bài tập 8 — Compensation timeout

Sau khi PaymentRejected, coordinator gửi ReleaseReservation và timeout. Inventory có thể đã release.

**Câu hỏi:** Bước tiếp theo là gì?

**Gợi ý:** Giữ compensation UNKNOWN, query status theo release operation ID hoặc retry idempotent cùng key; không cộng stock lần nữa.

## 33. Kết luận

ACID là nền tảng mạnh của giao dịch database cục bộ, nhưng **phạm vi của ACID không tự mở rộng qua các ranh giới service, database, broker và hệ thống bên thứ ba**. Nhiều local COMMIT có thể thành công hoặc thất bại ở các thời điểm khác nhau; một lời gọi mạng mất response không xác định được kết quả nghiệp vụ; rollback ở một nơi không hoàn tác side effect đã commit ở nơi khác.

Thiết kế giao dịch phân tán cần bắt đầu từ **business invariants và quyền sở hữu dữ liệu**, rồi chọn cơ chế phù hợp: giữ invariant mạnh trong một local transaction khi có thể; dùng Saga/TCC cho workflow nhiều bước; dùng transactional outbox để không mất event intent; dùng idempotency/inbox để chống trùng; dùng reconciliation và compensation để phục hồi sau lỗi; và theo dõi trạng thái UNKNOWN cho tới khi có kết luận.

Nguyên tắc cốt lõi: **một transaction local đáng tin là viên gạch xây nên workflow phân tán, không phải lời hứa rằng cả workflow sẽ atomic.** Hãy thiết kế trạng thái trung gian, đường phục hồi và bằng chứng nhất quán thay vì kỳ vọng @Transactional có thể điều khiển tất cả Microservices.
