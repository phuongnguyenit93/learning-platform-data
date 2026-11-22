# Khi nào cần giao dịch phân tán hoặc thao tác bù

Một transaction cục bộ trong cơ sở dữ liệu có thể bảo đảm nhiều thay đổi được commit hoặc rollback cùng nhau khi chúng nằm trong phạm vi một transaction manager và các tài nguyên tham gia được hỗ trợ. Nhưng một quy trình nghiệp vụ thực tế thường đi qua nhiều hệ thống: tạo đơn hàng trong database, giữ hàng ở dịch vụ kho, thu tiền qua cổng thanh toán, phát sự kiện lên message broker rồi yêu cầu đơn vị vận chuyển nhận kiện.

Không có một transaction JDBC thông thường nào tự động bao trùm tất cả các bước đó. Nếu database commit nhưng lời gọi thanh toán thất bại, hoặc thanh toán thành công nhưng ứng dụng mất kết nối trước khi ghi nhận kết quả, hệ thống có thể rơi vào trạng thái chỉ hoàn thành một phần.

Có hai hướng thiết kế chính:

- **Giao dịch phân tán** (*distributed transaction*): phối hợp nhiều resource manager để các tài nguyên cùng commit hoặc cùng rollback theo một giao thức như Two-Phase Commit (2PC), thường qua XA/JTA.
- **Quy trình nhiều transaction cục bộ với thao tác bù** (*Saga/compensation*): mỗi dịch vụ commit dữ liệu của mình; nếu bước sau thất bại, hệ thống chạy các hành động nghiệp vụ ngược lại để đưa quy trình về một trạng thái chấp nhận được.

Giao dịch phân tán phù hợp khi cần tính nguyên tử mạnh giữa các tài nguyên có hỗ trợ giao thức chung và chấp nhận chi phí điều phối. Saga phù hợp khi quy trình kéo dài qua dịch vụ độc lập, có thể chấp nhận trạng thái trung gian và có cách bù nghiệp vụ cho các bước đã hoàn thành. Thao tác bù không phải rollback database: nó là một hành động mới, có ý nghĩa nghiệp vụ, được commit riêng.

## 1. Khi nào transaction cục bộ là đủ?

Nếu toàn bộ thay đổi nằm trong một database transaction được quản lý bởi cùng transaction manager, thường không cần distributed transaction.

Ví dụ, tạo đơn hàng và các dòng chi tiết trong cùng một database:

```sql
BEGIN;

INSERT INTO orders (id, customer_id, status)
VALUES (9001, 42, 'PENDING');

INSERT INTO order_item (order_id, product_id, quantity)
VALUES
    (9001, 100, 2),
    (9001, 200, 1);

COMMIT;
```

Nếu một câu lệnh thất bại trước commit, ứng dụng có thể rollback và cả đơn hàng lẫn các dòng chi tiết đều không được xác nhận. Nhiều bảng trong cùng database không tự động có nghĩa là giao dịch phân tán.

Một transaction cục bộ cũng có thể làm việc với nhiều bảng hoặc nhiều schema nếu chúng nằm trong cùng resource và transaction manager. Ngược lại, hai database connection được quản lý bởi hai resource manager độc lập có thể cần cơ chế phối hợp nếu nghiệp vụ yêu cầu atomic commit giữa chúng.

Các tình huống thường vượt khỏi transaction cục bộ:

- Một service ghi vào database riêng, sau đó service khác ghi vào database khác.
- Một ứng dụng cần phối hợp database và message broker như hai tài nguyên phải commit nguyên tử.
- Quy trình cần cập nhật nhiều resource manager độc lập, ví dụ hai database hoặc database và JMS provider.
- Một thao tác gọi dịch vụ bên ngoài tạo tác động không thể rollback bằng transaction local, chẳng hạn thu tiền, đặt chỗ hoặc phát hành vận đơn.

Điểm cần xác định không chỉ là “có bao nhiêu database”, mà là **những thay đổi nào phải cùng được xác nhận như một đơn vị** và các tài nguyên đó có tham gia được cùng giao thức transaction hay không.

## 2. Giao dịch phân tán và Two-Phase Commit

Two-Phase Commit (2PC) là giao thức điều phối để nhiều participant cùng quyết định commit hoặc rollback một giao dịch phân tán. Một coordinator quản lý quá trình; các participant là resource manager có khả năng chuẩn bị và hoàn tất transaction theo giao thức.

2PC có hai giai đoạn:

1. **Prepare phase:** coordinator yêu cầu mọi participant chuẩn bị commit. Mỗi participant kiểm tra khả năng hoàn tất, ghi thông tin cần thiết vào log bền vững và trả lời `PREPARED` hoặc `ABORT`.
2. **Commit phase:** nếu tất cả participant trả lời `PREPARED`, coordinator quyết định commit và thông báo cho các participant. Nếu một participant không thể chuẩn bị, coordinator quyết định abort/rollback theo giao thức.

```text
                 Coordinator
                      |
          PREPARE ----+------------------+
             |                           |
             v                           v
        Database A                  Database B
        prepare, giữ                prepare, giữ
        trạng thái                   trạng thái
             |                           |
       PREPARED                      PREPARED
             +-------------+-------------+
                           |
                    COMMIT decision
                           |
              +------------+------------+
              v                         v
          COMMIT A                  COMMIT B
```

Nếu một participant trả lời không thể prepare, coordinator phát quyết định abort. Nếu coordinator hoặc mạng gặp sự cố sau khi participant đã prepare nhưng trước khi nhận quyết định cuối, participant có thể ở trạng thái *in-doubt* và phải giữ trạng thái khóa/tài nguyên cần thiết cho đến khi khôi phục được quyết định.

2PC cung cấp phối hợp atomic commit giữa các participant hỗ trợ giao thức. Nó không có nghĩa mọi dịch vụ HTTP bất kỳ đều có thể tham gia. Một REST API thu tiền hoặc một nhà cung cấp bên ngoài thường không tham gia XA/JTA chỉ vì ứng dụng gọi API trong một phương thức `@Transactional`.

## 3. XA/JTA trong ứng dụng Java

Trong Java enterprise, XA và Jakarta Transactions/JTA có thể phối hợp nhiều resource manager hỗ trợ XA. Transaction manager đóng vai trò coordinator; các XA resource tham gia prepare/commit.

Ví dụ về phạm vi có thể phối hợp:

- Một XA datasource cho database.
- Một XA connection factory cho JMS provider.
- Một transaction manager hỗ trợ enlist các resource và điều phối commit.

Đoạn mã dưới đây chỉ minh họa ranh giới khai báo, không phải cấu hình XA hoàn chỉnh:

```java
@Transactional
public void createOrderAndPublishMessage(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("order.created", order.getId());
}
```

Đoạn mã chỉ có thể được phối hợp theo XA nếu cả database và JMS resource được cấu hình XA, được enlist vào cùng JTA transaction và transaction manager hỗ trợ đúng giao thức. Nếu `jmsTemplate` dùng connection factory không XA hoặc transaction manager không quản lý resource đó, hai thao tác không tự động atomic với nhau.

### Ưu điểm và chi phí của 2PC

| Khía cạnh | Đặc điểm |
|---|---|
| Tính nguyên tử | Các participant tuân thủ giao thức cùng theo quyết định commit/abort |
| Điều kiện | Mọi resource cần phối hợp phải hỗ trợ và được enlist đúng cách |
| Khóa và tài nguyên | Participant có thể giữ khóa/tài nguyên sau prepare cho đến quyết định cuối |
| Độ trễ | Có thêm lượt trao đổi mạng và ghi log bền vững |
| Khả năng phục hồi | Cần coordinator log và quy trình xử lý transaction in-doubt |
| Khả năng mở rộng | Có thể tạo áp lực lên resource manager khi transaction nhiều hoặc kéo dài |
| Dịch vụ bên ngoài | API HTTP thông thường không tự tham gia XA |

2PC thường phù hợp với quy trình ngắn, các resource manager có hỗ trợ XA đáng tin cậy và yêu cầu atomic commit mạnh. Nó kém phù hợp với workflow kéo dài nhiều phút, nhiều giờ hoặc đi qua nhiều dịch vụ không hỗ trợ XA.

## 4. Transaction in-doubt và phục hồi coordinator

Sau giai đoạn prepare, participant có thể đã ghi trạng thái `PREPARED` và giữ các tài nguyên liên quan. Nếu coordinator bị dừng trước khi gửi quyết định cuối, participant không thể tự ý commit hoặc rollback vì có thể làm các participant khác không đồng nhất.

```text
Coordinator gửi PREPARE
Database A -> PREPARED
Database B -> PREPARED
Coordinator ghi quyết định COMMIT
Coordinator bị dừng trước khi gửi thông báo cho B

Database A có thể nhận COMMIT.
Database B vẫn ở trạng thái in-doubt cho đến khi lấy được quyết định.
```

Khi khởi động lại, transaction manager dùng log bền vững để khôi phục quyết định và tiếp tục thông báo cho participant. Người vận hành cần biết cách kiểm tra và xử lý giao dịch in-doubt theo đúng database và transaction manager. Không nên tự ý xóa trạng thái prepared hoặc rollback thủ công một participant mà không xác định quyết định của coordinator.

Một transaction XA bị treo có thể giữ khóa và ảnh hưởng các transaction khác. Vì vậy, nếu dùng XA, cần giám sát thời gian transaction, số lượng prepared/in-doubt, trạng thái coordinator và khả năng phục hồi của từng resource manager.

## 5. Vì sao nhiều hệ thống chọn Saga?

Trong kiến trúc microservices, mỗi dịch vụ thường sở hữu database riêng. Một đơn hàng có thể cần đi qua dịch vụ đơn hàng, kho, thanh toán và vận chuyển. Các dịch vụ này thường không chia sẻ connection hoặc transaction manager và không tham gia cùng một XA transaction.

Thay vì giữ một distributed transaction mở xuyên suốt các lời gọi mạng, Saga chia workflow thành nhiều **local transaction**. Mỗi bước commit độc lập và phát ra kết quả/sự kiện để bước tiếp theo thực hiện.

Ví dụ quy trình đặt hàng:

1. Order Service tạo đơn ở trạng thái `PENDING`.
2. Inventory Service giữ hàng và commit reservation.
3. Payment Service thu tiền hoặc xác thực thanh toán và commit trạng thái thanh toán.
4. Shipping Service tạo yêu cầu vận chuyển.
5. Order Service chuyển đơn sang `CONFIRMED`.

Nếu thanh toán thất bại sau khi kho đã giữ hàng, hệ thống cần gọi thao tác bù để giải phóng reservation. Nếu tạo vận đơn thất bại sau khi đã thu tiền, nghiệp vụ có thể yêu cầu hoàn tiền và giải phóng hàng.

```text
T1: Tạo đơn PENDING
       |
       v
T2: Giữ hàng (Inventory)
       |
       v
T3: Thu tiền (Payment)
       |
       v
T4: Tạo vận đơn (Shipping)
       |
       v
T5: Đơn CONFIRMED

Nếu T3 thất bại:
  C2: Hủy reservation, trả hàng về kho
  C1: Đơn chuyển sang CANCELLED/FAILED
```

Saga không giữ tất cả database transaction mở cùng lúc. Mỗi service commit local transaction rồi mới tiến tới bước sau. Khi có lỗi, hệ thống chạy các hành động bù cho những bước đã commit và có thể cần retry thao tác bù nếu dịch vụ tạm thời không sẵn sàng.

## 6. Thao tác bù là gì?

Thao tác bù (*compensating action*) là một hành động nghiệp vụ mới nhằm đảo ngược hoặc giảm tác động của một bước đã hoàn thành trước đó.

Ví dụ:

| Bước đã hoàn thành | Thao tác bù có thể dùng |
|---|---|
| Giữ 2 sản phẩm trong kho | Hủy reservation và cộng lại số lượng có thể bán |
| Thu tiền khách hàng | Tạo yêu cầu hoàn tiền |
| Tạo vận đơn | Hủy vận đơn nếu hãng vận chuyển còn cho phép |
| Cộng điểm thưởng | Ghi giao dịch điều chỉnh trừ điểm |
| Đặt chỗ | Hủy booking và giải phóng chỗ |
| Gửi thông báo | Gửi thông báo đính chính nếu nghiệp vụ cho phép |

Compensation không phải là rollback lịch sử. Ví dụ, nếu đã thu tiền 1.000.000 đồng rồi hoàn lại 1.000.000 đồng, hệ thống vẫn lưu hai sự kiện: đã thu tiền và đã hoàn tiền. Số dư ròng có thể trở về ban đầu, nhưng audit trail vẫn phản ánh những gì đã xảy ra.

Một số tác động không thể đảo ngược hoàn toàn:

- Email hoặc thông báo đã gửi không thể thu hồi khỏi hộp thư người nhận.
- Hàng đã giao có thể cần quy trình trả hàng, không thể biến việc giao hàng thành chưa từng xảy ra.
- Một khoản thanh toán đã capture có thể cần refund, có thời gian xử lý và phí riêng.
- Dữ liệu đã được bên ngoài đọc hoặc sử dụng không thể được “quên” bằng rollback.

Do đó, compensation thường tạo ra trạng thái nghiệp vụ mới, chẳng hạn `REFUND_PENDING`, `CANCEL_REQUESTED` hoặc `RETURN_IN_PROGRESS`, thay vì khôi phục byte-for-byte trạng thái ban đầu.

## 7. Saga orchestration và choreography

Có hai cách tổ chức phổ biến.

### Orchestration: có bộ điều phối trung tâm

Một Saga orchestrator biết workflow đang ở bước nào, gọi service tiếp theo và quyết định hành động bù khi có lỗi.

```text
             Order Saga Orchestrator
               /        |        \
              v         v         v
         Inventory   Payment   Shipping
           reserve    charge     create
              |         |          |
              +---------+----------+
                        |
                 theo dõi trạng thái
```

Ưu điểm:

- Luồng nghiệp vụ và thứ tự các bước được nhìn thấy ở một nơi.
- Dễ biểu diễn điều kiện, timeout, retry và compensation.
- Có thể truy vấn trạng thái Saga để biết đang dừng ở bước nào.

Chi phí:

- Orchestrator trở thành thành phần cần vận hành và mở rộng.
- Cần tránh đưa quá nhiều logic nghiệp vụ của service con vào orchestrator.
- Phải bảo đảm lệnh gửi tới service và trạng thái Saga được ghi nhận bền vững.

### Choreography: các service phản ứng với sự kiện

Không có một bộ điều phối gọi trực tiếp từng bước. Mỗi service phát sự kiện sau local transaction; service khác nhận sự kiện và thực hiện bước tiếp theo.

```text
OrderCreated
     |
     v
Inventory Service -> InventoryReserved
                            |
                            v
                    Payment Service
                            |
                  PaymentSucceeded
                            |
                            v
                    Shipping Service
```

Nếu thanh toán thất bại, Payment Service phát `PaymentFailed`; Inventory Service nhận sự kiện và hủy reservation; Order Service cập nhật trạng thái đơn.

Ưu điểm:

- Các service ít phụ thuộc trực tiếp vào API điều phối trung tâm.
- Có thể mở rộng theo sự kiện và tách trách nhiệm theo domain.
- Dễ thêm consumer mới khi sự kiện có hợp đồng ổn định.

Chi phí:

- Luồng workflow phân tán qua nhiều consumer và topic, khó theo dõi nếu thiếu correlation ID.
- Quan hệ phụ thuộc và vòng lặp sự kiện có thể khó hiểu.
- Cần xử lý message duplicate, message đến trễ hoặc sai thứ tự.
- Khó biết toàn bộ Saga đang ở trạng thái nào nếu không có nơi tổng hợp trạng thái.

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Điều phối | Một thành phần điều phối | Các service phản ứng với sự kiện |
| Theo dõi workflow | Trạng thái tập trung hơn | Cần correlation và tổng hợp sự kiện |
| Phụ thuộc | Orchestrator gọi các service | Service phụ thuộc hợp đồng sự kiện |
| Phù hợp | Workflow nhiều nhánh, điều kiện và compensation rõ | Luồng sự kiện đơn giản, các domain ít phụ thuộc trực tiếp |
| Rủi ro | Orchestrator thành nút quan trọng | Luồng sự kiện khó lần theo và dễ phát sinh coupling ngầm |

## 8. Ví dụ Saga đặt hàng với thao tác bù

Giả sử quy trình có ba local transaction:

- `T1`: tạo đơn hàng `PENDING`.
- `T2`: Inventory giữ hàng.
- `T3`: Payment thu tiền.
- `T4`: Shipping tạo vận đơn và Order chuyển sang `CONFIRMED`.

Các thao tác bù:

- `C2`: hủy reservation của Inventory.
- `C3`: hoàn tiền qua Payment.
- `C4`: hủy vận đơn nếu đã tạo và còn được phép.

Nếu `T3` thất bại sau khi `T2` thành công:

```text
T1 CreateOrder(PENDING)       COMMIT
        |
        v
T2 ReserveInventory           COMMIT
        |
        v
T3 ChargePayment              FAIL
        |
        v
C2 ReleaseInventory          COMMIT
        |
        v
T1 UpdateOrder(CANCELLED)    COMMIT
```

Mỗi bước có transaction riêng. Nếu `C2` thất bại do Inventory Service tạm ngừng, Saga không nên quên việc cần bù. Nó cần ghi trạng thái `COMPENSATION_PENDING`, retry có giới hạn hoặc chuyển sang hàng đợi xử lý lỗi để tiếp tục sau.

Ví dụ trạng thái tổng thể:

| Trạng thái Saga | Ý nghĩa |
|---|---|
| `STARTED` | Đã nhận yêu cầu và tạo workflow |
| `RESERVING_INVENTORY` | Đang giữ hàng |
| `CHARGING_PAYMENT` | Đang thanh toán |
| `CREATING_SHIPMENT` | Đang tạo vận đơn |
| `COMPLETED` | Các bước cần thiết đã hoàn tất |
| `COMPENSATING` | Đang chạy các hành động bù |
| `COMPENSATION_PENDING` | Có bước bù chưa hoàn tất và cần retry |
| `COMPENSATED` | Các bước bù cần thiết đã hoàn tất |
| `MANUAL_REVIEW` | Cần người vận hành xử lý |

Không phải mọi Saga cần đúng các trạng thái này. Quan trọng là mô hình hóa rõ bước đang thực hiện, bước đã commit, bước cần bù và kết quả cuối.

## 9. Compensation phải có tính lũy đẳng

Một thao tác bù cũng có thể bị gửi nhiều lần. Ví dụ orchestrator gửi lệnh hoàn tiền, Payment Service thực hiện thành công nhưng phản hồi bị mất. Orchestrator không biết đã hoàn tiền hay chưa và gửi lại lệnh. Nếu mỗi lần gọi tạo một refund mới, khách hàng có thể được hoàn tiền hai lần.

Vì vậy, mỗi bước và mỗi compensation nên có một định danh nghiệp vụ ổn định:

- `saga_id`: định danh toàn workflow.
- `step_id`: định danh bước cụ thể.
- `compensation_id`: định danh thao tác bù.
- `idempotency_key`: khóa chống lặp cho cùng một tác động nghiệp vụ.
- `correlation_id`: liên kết log, trace và message của toàn quy trình.

Ví dụ:

```text
Saga: order-9001
Payment operation: charge-order-9001
Compensation: refund-order-9001

Lần gọi refund thứ nhất -> Payment tạo refund, phản hồi bị mất
Lần gọi refund thứ hai -> cùng idempotency key
Payment nhận diện refund đã tồn tại và trả kết quả cũ
```

Idempotency record cần được ghi nguyên tử cùng với tác động nghiệp vụ trong service sở hữu tác động đó. Không chỉ lưu idempotency key ở orchestrator rồi giả định service đích sẽ tự chống trùng.

## 10. Transactional Outbox: giải quyết dual-write giữa database và message broker

Một service thường cần vừa cập nhật database vừa phát message. Nếu thực hiện hai hành động riêng:

```text
UPDATE orders SET status = 'CONFIRMED';
COMMIT;
PUBLISH OrderConfirmed;
```

Có hai cửa sổ lỗi:

- Database commit thành công nhưng process chết trước khi publish: message bị mất.
- Publish thành công nhưng database rollback: consumer nhận một sự kiện về thay đổi chưa được commit.

Transactional outbox giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và outbox event trong cùng local transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = 9001;

INSERT INTO outbox_event (
    event_id, aggregate_type, aggregate_id, event_type, payload, created_at
)
VALUES (
    'evt-9001-confirmed', 'Order', '9001',
    'OrderConfirmed', '{"orderId":9001}', CURRENT_TIMESTAMP
);

COMMIT;
```

Sau commit, một relay/worker đọc outbox và publish message lên broker. Nếu relay chết sau khi publish nhưng trước khi đánh dấu event đã gửi, nó có thể publish lại. Vì vậy outbox thường bảo đảm khả năng phát ít nhất một lần (*at-least-once*); consumer phải deduplicate hoặc xử lý lũy đẳng.

Outbox không biến database và broker thành một XA transaction. Nó bảo đảm rằng thay đổi database và **ý định phát sự kiện** được lưu nguyên tử trong cùng database transaction. Việc chuyển event sang broker diễn ra sau đó và có thể lặp.

## 11. Inbox/deduplication ở consumer

Consumer có thể nhận cùng một message nhiều lần do broker redelivery, relay retry hoặc mất acknowledgment. Một inbox table giúp ghi nhận event đã xử lý.

```sql
CREATE TABLE inbox_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer xử lý event và ghi inbox record trong cùng transaction với thay đổi nghiệp vụ:

```sql
BEGIN;

INSERT INTO inbox_event (consumer_name, event_id, received_at)
VALUES ('inventory-service', 'evt-9001-confirmed', CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;

-- Ứng dụng kiểm tra số hàng được insert.
-- Nếu event đã có, bỏ qua xử lý nghiệp vụ.
-- Nếu mới, cập nhật inventory trong cùng transaction.

COMMIT;
```

Cú pháp `ON CONFLICT DO NOTHING` là ví dụ PostgreSQL; database khác có cú pháp tương đương. Điều quan trọng là deduplication record và thay đổi nghiệp vụ phải commit cùng nhau. Nếu inbox ghi trước rồi transaction nghiệp vụ rollback, lần giao lại sau có thể bị bỏ qua dù công việc chưa được thực hiện.

## 12. Compensation không phải lúc nào cũng là phép đảo ngược chính xác

Một thao tác bù cần phản ánh nghiệp vụ, không chỉ đảo ngược phép toán dữ liệu.

Ví dụ, một reservation giữ 2 sản phẩm. Trong thời gian đó, giá bán hoặc số lượng có thể đã thay đổi. Hủy reservation nên giải phóng đúng lượng đã giữ theo reservation ID, không đơn giản cộng 2 vào một cột hiện tại mà bỏ qua trạng thái reservation.

Với thanh toán:

- Nếu chỉ authorization, có thể void authorization.
- Nếu đã capture, thường cần refund.
- Refund có thể mất thời gian, có phí hoặc thất bại; trạng thái cần theo dõi riêng.

Với vận chuyển:

- Nếu vận đơn chưa được lấy hàng, có thể hủy.
- Nếu kiện đã bàn giao cho hãng vận chuyển, cần quy trình return hoặc intercept thay vì giả định hủy tức thời.

Do đó, compensation cần biết trạng thái hiện tại của tác động gốc và có thể có nhiều kết quả như `COMPENSATED`, `COMPENSATION_PENDING`, `COMPENSATION_FAILED` hoặc `MANUAL_REVIEW`.

## 13. Thứ tự compensation và dependency giữa các bước

Nếu Saga có nhiều bước đã commit, compensation thường được chạy theo thứ tự ngược của các bước phụ thuộc. Tuy nhiên, không phải lúc nào cũng có thể chỉ đảo ngược thứ tự máy móc; phải dựa vào quan hệ nghiệp vụ.

Ví dụ:

```text
T1: Reserve inventory
T2: Charge payment
T3: Create shipment

Nếu T3 thất bại:
  C2: Refund/void payment
  C1: Release inventory
```

Nếu vận đơn đã được tạo một phần, trước khi hoàn tiền và giải phóng hàng có thể cần yêu cầu hủy vận đơn. Một compensation có thể phụ thuộc kết quả của compensation khác.

Orchestrator cần lưu tiến độ compensation sau mỗi bước. Nếu process restart, nó phải biết bước nào đã bù thành công, bước nào còn pending để tiếp tục mà không lặp tác động ngoài ý muốn.

## 14. Lỗi trong lúc compensation

Thao tác bù cũng là một lời gọi có thể timeout, deadlock hoặc mất kết nối. Vì vậy, compensation cần:

- Retry với backoff và giới hạn số lần thử.
- Idempotency key ổn định cho cùng compensation.
- Trạng thái riêng để phân biệt chưa chạy, đang chạy, thành công và thất bại.
- Timeout và deadline phù hợp.
- Correlation ID để truy vết với bước gốc.
- Hàng đợi lỗi hoặc quy trình manual review khi không thể tự phục hồi.
- Cảnh báo khi compensation pending quá lâu.

Không nên đánh dấu Saga `COMPENSATED` chỉ vì đã gửi lệnh bù. Phải có bằng chứng bước bù đã hoàn tất hoặc trạng thái được nghiệp vụ chấp nhận.

## 15. So sánh distributed transaction và Saga

| Tiêu chí | Distributed transaction / 2PC | Saga với compensation |
|---|---|---|
| Mô hình | Nhiều participant cùng một distributed commit | Chuỗi local transaction độc lập |
| Tính nguyên tử | Atomic commit nếu mọi participant tuân thủ giao thức | Không có rollback toàn cục tức thời; dùng compensation để phục hồi nghiệp vụ |
| Trạng thái trung gian | Thường bị che khỏi kết quả commit cuối; participant có thể bị giữ prepared | Có trạng thái trung gian được commit và quan sát |
| Khóa/tài nguyên | Có thể giữ tài nguyên trong prepare | Mỗi local transaction ngắn, không giữ khóa xuyên workflow |
| Yêu cầu hạ tầng | XA/JTA hoặc giao thức distributed commit tương thích | Message/event, state machine/orchestrator hoặc choreography |
| Dịch vụ HTTP bên ngoài | Thường không tham gia trực tiếp | Có thể tích hợp qua API và compensation/idempotency |
| Phục hồi | Coordinator log, participant recovery, in-doubt transaction | Retry step/compensation, replay event, reconciliation |
| Phù hợp | Atomic commit mạnh giữa resource hỗ trợ | Workflow dài, microservices, eventual consistency chấp nhận được |
| Độ phức tạp chính | Cấu hình XA, vận hành coordinator và prepared transaction | Thiết kế state machine, compensation và idempotency |

Không có lựa chọn nào miễn phí. 2PC tăng phối hợp ở tầng transaction manager; Saga chuyển độ phức tạp sang logic nghiệp vụ, trạng thái workflow và phục hồi.

## 16. Chọn giải pháp theo yêu cầu nghiệp vụ

Hãy bắt đầu bằng các câu hỏi:

1. **Các thay đổi có nằm trong một local transaction không?** Nếu có, dùng transaction cục bộ.
2. **Các resource manager có hỗ trợ XA/JTA và có thể enlist cùng coordinator không?** Nếu không, 2PC không phải lựa chọn thực tế.
3. **Nghiệp vụ có cần mọi resource commit nguyên tử tại cùng thời điểm không?** Nếu có và hạ tầng hỗ trợ, cân nhắc distributed transaction.
4. **Có thể chấp nhận trạng thái trung gian như `PENDING`, `RESERVED` hoặc `PAYMENT_PENDING` không?** Nếu có, Saga thường phù hợp.
5. **Mỗi bước đã commit có hành động bù nghiệp vụ không?** Nếu không thể đảo ngược, cần thay đổi trình tự hoặc chấp nhận trạng thái cần xử lý thủ công.
6. **Compensation có lũy đẳng và có thể retry không?** Nếu không, cần thiết kế cơ chế chống trùng và đối soát trước khi tự động hóa.
7. **Làm thế nào biết workflow đã hoàn tất?** Cần state machine, event correlation và giám sát bước pending.

| Tình huống | Hướng phù hợp để xem xét |
|---|---|
| Nhiều bảng trong cùng database | Local transaction |
| Database và JMS broker đều hỗ trợ XA, cần atomic commit | JTA/XA 2PC |
| Nhiều microservice sở hữu database riêng | Saga, outbox/inbox và idempotency |
| Gọi cổng thanh toán hoặc hãng vận chuyển qua HTTP | Workflow/Saga với trạng thái và compensation |
| Không thể bù một tác động đã xảy ra | Authorization/reservation trước, commit tác động không thể đảo ngược ở bước cuối có kiểm soát, hoặc manual review |
| Chỉ cần phát thông báo sau khi database commit | Transactional outbox nếu không được phép mất event |

## 17. Các lỗi thiết kế thường gặp

- **Gọi API ngoài trong transaction database dài:** giữ connection/khóa trong khi chờ mạng và không thể rollback tác động đã xảy ra ở dịch vụ ngoài.
- **Cho rằng `@Transactional` bao trùm REST call:** annotation chỉ quản lý resource được transaction manager hỗ trợ; HTTP service không tự tham gia transaction.
- **Ghi database rồi publish message riêng:** tạo dual-write window có thể mất hoặc phát event sai.
- **Retry mà không idempotency:** có thể thu tiền, tạo booking hoặc gửi thông báo nhiều lần.
- **Coi compensation là rollback:** compensation là hành động nghiệp vụ mới, có thể thất bại hoặc không khôi phục chính xác trạng thái ban đầu.
- **Không lưu trạng thái Saga:** khi process restart, hệ thống không biết bước nào đã commit hoặc đã bù.
- **Đánh dấu hoàn tất khi mới gửi yêu cầu bù:** gửi thành công không có nghĩa dịch vụ đích đã hoàn tất compensation.
- **Không xử lý message duplicate hoặc sai thứ tự:** consumer có thể áp dụng cùng sự kiện nhiều lần hoặc áp dụng sự kiện cũ lên trạng thái mới.
- **Không có manual recovery:** một số tác động không thể tự bù và cần người vận hành giải quyết.

## 18. Quan sát và vận hành workflow phân tán

Một Saga cần được quan sát như một operation kéo dài, không chỉ là các log rời rạc của từng service. Nên lưu:

- `saga_id` và business operation ID ổn định.
- Trạng thái hiện tại, bước hiện tại và phiên bản định nghĩa workflow.
- Các bước đã hoàn thành, các bước đang chạy và các compensation còn pending.
- `event_id`, `correlation_id`, `trace_id` và idempotency key.
- Thời điểm bắt đầu/kết thúc từng bước, số lần retry và nguyên nhân lỗi.
- Deadline tổng, thời gian chờ từng service và thời điểm compensation được lên lịch.
- Kết quả cuối: `COMPLETED`, `COMPENSATED`, `MANUAL_REVIEW` hoặc trạng thái tương đương.

Metrics hữu ích gồm số Saga đang chạy, số Saga quá hạn, số compensation pending, tỷ lệ Saga hoàn tất, tỷ lệ bù thất bại, thời gian hoàn tất p95/p99 và số operation cần manual review. Tránh dùng `saga_id` làm nhãn metric có cardinality cao; dùng nó trong log và trace.

Nên có màn hình hoặc công cụ vận hành để tra cứu một Saga theo business ID, xem lịch sử bước, retry compensation khi an toàn và ghi lại thao tác can thiệp thủ công. Mọi thao tác thủ công cần audit rõ ai thực hiện, lúc nào và vì sao.

## 19. Quy trình thiết kế một workflow có compensation

1. **Vẽ các bước nghiệp vụ:** xác định service sở hữu dữ liệu và local transaction của từng bước.
2. **Xác định điểm commit:** biết chính xác khi nào mỗi bước đã tạo tác động không còn rollback được bằng transaction trước.
3. **Định nghĩa trạng thái trung gian:** ví dụ `PENDING`, `RESERVED`, `AUTHORIZED`, `CONFIRMED`.
4. **Định nghĩa compensation:** mỗi bước cần biết hành động bù, điều kiện thực hiện và kết quả có thể xảy ra.
5. **Thiết kế idempotency:** cùng một step hoặc compensation được gửi lại phải không tạo tác động lặp.
6. **Lưu state bền vững:** cập nhật trạng thái Saga và ghi lệnh/event cần phát bằng outbox trong local transaction.
7. **Xử lý duplicate và ordering:** dùng inbox/deduplication, version hoặc sequence cho event.
8. **Thiết kế retry và deadline:** phân loại lỗi tạm thời/vĩnh viễn, backoff, giới hạn lần thử và timeout.
9. **Thiết kế phục hồi:** xử lý process restart, message bị mất, compensation pending và kết quả không rõ.
10. **Chuẩn bị manual review:** xác định trường hợp không thể tự động bù và cung cấp quy trình vận hành có audit.

## 20. Những điểm cần nhớ

- Transaction cục bộ đủ khi các thay đổi thuộc cùng transaction manager và resource được quản lý chung; nhiều bảng trong một database không tự động cần distributed transaction.
- Distributed transaction/2PC phối hợp commit giữa các participant hỗ trợ giao thức, thường qua XA/JTA.
- 2PC có chi phí round-trip, log bền vững, khóa/tài nguyên được giữ trong prepare và xử lý transaction in-doubt.
- Một lời gọi HTTP thông thường không tự tham gia XA chỉ vì được gọi từ phương thức `@Transactional`.
- Saga chia workflow thành các local transaction; mỗi bước commit độc lập và trạng thái trung gian có thể được quan sát.
- Compensation là hành động nghiệp vụ mới, không phải rollback lịch sử; nó có thể thất bại và cần retry.
- Compensation cần idempotency, trạng thái bền vững và quy trình phục hồi.
- Transactional outbox lưu thay đổi nghiệp vụ và ý định phát event trong cùng local transaction; relay có thể phát lặp nên consumer cần deduplicate.
- Inbox record và thay đổi nghiệp vụ của consumer cần commit cùng transaction.
- Chọn orchestration hoặc choreography theo độ phức tạp workflow và nhu cầu quan sát.
- Tác động không thể đảo ngược cần reservation/authorization, trạng thái chờ hoặc manual review thay vì giả định có thể bù hoàn toàn.

Hãy dùng transaction cục bộ khi có thể giữ toàn bộ thay đổi trong một resource manager. Chỉ chọn distributed transaction khi atomic commit thực sự cần thiết và hạ tầng hỗ trợ giao thức phù hợp. Với workflow qua nhiều dịch vụ độc lập, thiết kế Saga cùng outbox/inbox, idempotency và thao tác bù để hệ thống có thể phục hồi sau lỗi mà vẫn giữ được lịch sử nghiệp vụ rõ ràng.
