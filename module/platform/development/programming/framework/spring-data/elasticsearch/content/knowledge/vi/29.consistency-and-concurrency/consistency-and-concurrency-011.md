# Phối hợp nhiều thao tác nghiệp vụ và cơ chế bù trừ

Một nghiệp vụ trong ứng dụng thường không chỉ ghi một document Elasticsearch. Ví dụ tạo đơn hàng có thể cần tạo order, giữ tồn kho, thu tiền, cập nhật trạng thái giao dịch và đưa dữ liệu sang index tìm kiếm. Mỗi bước có thể thành công hoặc thất bại ở một thời điểm khác nhau. Nếu bước thứ ba lỗi sau khi hai bước đầu đã hoàn tất, ứng dụng phải biết tiếp tục, thử lại hay thực hiện hành động bù trừ.

Spring Data Elasticsearch cung cấp repository và `ElasticsearchOperations` để đọc ghi document, nhưng không biến một chuỗi thao tác trên nhiều document, nhiều index hoặc nhiều hệ thống thành một transaction nghiệp vụ duy nhất. Elasticsearch bảo đảm tính nguyên tử ở phạm vi thao tác document phù hợp, còn Bulk API có thể trả kết quả thành công/thất bại riêng cho từng item. Khi phối hợp nhiều bước, ứng dụng cần thiết kế ranh giới nhất quán, trạng thái workflow, idempotency, retry và compensation.

Các ý chính:

- Xác định hệ thống nào là nguồn dữ liệu có thẩm quyền (source of truth).
- Chia workflow thành các bước có kết quả và trạng thái rõ ràng.
- Dùng transaction cục bộ cho dữ liệu thuộc cùng một transactional resource.
- Dùng outbox để phát sự kiện bền vững từ database sang Elasticsearch.
- Dùng Saga khi một nghiệp vụ trải qua nhiều bước hoặc nhiều dịch vụ.
- Thiết kế hành động bù trừ theo ý nghĩa nghiệp vụ, không giả định có thể rollback mọi thứ.
- Làm cho mỗi bước và mỗi compensation có thể chạy lại an toàn.
- Dùng version/concurrency control để tránh bù trừ ghi đè thay đổi mới hơn.

## 1. Một nghiệp vụ nhiều bước có thể thất bại như thế nào?

Giả sử khách hàng đặt hàng. Hệ thống cần:

1. Tạo đơn hàng ở trạng thái chờ xử lý.
2. Giữ số lượng hàng trong kho.
3. Thu tiền hoặc xác nhận thanh toán.
4. Chuyển đơn hàng sang trạng thái đã xác nhận.
5. Cập nhật index Elasticsearch để trang tìm kiếm và trang quản trị nhìn thấy đơn hàng.

Luồng thành công:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Capture payment
    |
    v
Confirm order
    |
    v
Publish event / update Elasticsearch
    |
    v
Workflow completed
~~~

Nhưng có thể xảy ra:

- Order đã được tạo, nhưng inventory service timeout.
- Inventory đã giữ hàng, nhưng payment bị từ chối.
- Payment đã thu tiền, nhưng database không cập nhật được order.
- Order đã xác nhận trong database, nhưng Elasticsearch đang unavailable.
- Elasticsearch đã nhận event, nhưng publisher không nhận được acknowledgement và gửi lại.
- Một bước timeout ở client trong khi server đã thực hiện thành công.

Nếu chỉ gọi tuần tự các service rồi ném exception khi có lỗi, ứng dụng có thể để lại trạng thái dở dang: tiền đã thu nhưng đơn hàng chưa xác nhận; tồn kho đã giữ nhưng đơn hàng đã bị hủy; hoặc database đúng nhưng search index chưa cập nhật.

## 2. Hiểu đúng ranh giới transaction của Elasticsearch

Trước khi thiết kế workflow, cần biết thao tác nào có thể được xem là nguyên tử và thao tác nào không.

### 2.1. Atomicity ở cấp document

Một thao tác index hoặc update trên một document được Elasticsearch xử lý như một thao tác ghi ở phạm vi document. Người đọc không nhìn thấy một nửa source của document đang được thay thế.

Điều đó không có nghĩa một chuỗi nhiều request có thể được rollback như một database transaction. Ví dụ:

~~~http
PUT /orders/_doc/100
PUT /customers/_doc/42
PUT /payments/_doc/pay-100
~~~

Nếu request đầu và thứ hai thành công nhưng request thứ ba thất bại, hai document đã ghi vẫn tồn tại. Elasticsearch không tự động undo các request trước.

### 2.2. Bulk API không phải transaction

Bulk API giảm overhead khi ghi nhiều document, nhưng mỗi item có kết quả riêng. Một bulk response có thể chứa cả item thành công và item thất bại.

Ví dụ:

~~~text
Bulk request
  item 1 -> success
  item 2 -> version conflict
  item 3 -> success
  item 4 -> mapping error
~~~

Ứng dụng phải đọc kết quả từng item, xác định item nào đã được áp dụng và xử lý riêng lỗi. Không được giả định một item lỗi sẽ làm các item khác tự rollback.

### 2.3. Không có transaction xuyên nhiều hệ thống

Một nghiệp vụ có thể kết hợp database quan hệ, Elasticsearch, payment gateway, inventory service, message broker và dịch vụ gửi email hoặc thông báo.

`@Transactional` thông thường quản lý transaction của transactional resource được cấu hình trong Spring, ví dụ JPA transaction manager. Nó không tự biến lời gọi Elasticsearch, HTTP request đến payment gateway và publish message thành một transaction ACID chung.

Ngay cả khi có nhiều transaction manager, không nên giả định chúng tạo ra distributed atomic commit. Muốn phối hợp các hệ thống độc lập, cần một giao thức phân tán được hỗ trợ rõ ràng hoặc một mô hình eventual consistency như Saga và Outbox.

### 2.4. Vai trò của Spring Data Elasticsearch

`ElasticsearchRepository` và `ElasticsearchOperations` cung cấp abstraction cho thao tác document:

- `save` để ghi entity.
- `delete` để xóa document.
- `get` hoặc `search` để đọc.
- Bulk operations để xử lý nhiều item.
- Version metadata để phát hiện cập nhật đồng thời.

Các abstraction này không tự quản lý vòng đời một nghiệp vụ kéo dài qua nhiều hệ thống. Workflow, retry, compensation và lưu trạng thái tiến trình thuộc trách nhiệm của tầng application hoặc một workflow engine.

## 3. Chọn source of truth trước khi phối hợp thao tác

Một thiết kế quan trọng là xác định dữ liệu gốc nằm ở đâu.

Trong nhiều hệ thống, database quan hệ giữ order, payment state và inventory ledger; Elasticsearch là read model phục vụ tìm kiếm. Khi đó:

- Database là nguồn có thẩm quyền cho trạng thái nghiệp vụ.
- Elasticsearch là projection có thể tái tạo từ event hoặc database.
- Nếu index Elasticsearch chậm cập nhật, nghiệp vụ vẫn có thể đúng.
- Nếu document trong Elasticsearch sai hoặc bị mất, có thể xây lại projection.

Luồng phù hợp:

~~~text
Command / API
     |
     v
Business database transaction
     |
     +--> Update order state
     |
     +--> Insert outbox event
              |
              v
       Outbox publisher
              |
              v
        Event consumer
              |
              v
      Elasticsearch projection
~~~

Không nên dùng kết quả Search trong Elasticsearch làm căn cứ duy nhất để quyết định các thao tác tài chính hoặc tồn kho nếu nguồn dữ liệu có thẩm quyền nằm ở database khác. Search index có thể trễ do refresh, event delivery hoặc retry.

Nếu ứng dụng dùng Elasticsearch làm kho dữ liệu chính, vẫn phải xác định rõ transaction boundary. Một document có thể được cập nhật nguyên tử, nhưng chuỗi cập nhật nhiều document cần workflow có trạng thái và xử lý lỗi riêng.

## 4. Các chiến lược phối hợp workflow

Có ba nhóm cách tiếp cận thường gặp.

| Chiến lược | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Local transaction | Gom thay đổi vào một transaction của cùng resource | Các bước cùng một database/resource manager |
| Saga orchestration | Một coordinator điều khiển từng bước và compensation | Nghiệp vụ nhiều bước, cần trạng thái trung tâm |
| Saga choreography | Các dịch vụ phát và nhận event để tiến trình tiếp tục | Các dịch vụ tương đối độc lập, event flow rõ |

Outbox thường kết hợp với local transaction và Saga để đảm bảo sự kiện được phát bền vững.

### 4.1. Local transaction

Nếu tạo order và ghi outbox event trong cùng database, thực hiện cả hai trong một `@Transactional` method:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(
            Order.pending(command)
    );

    outboxRepository.save(
            OutboxEvent.orderCreated(order)
    );

    return order;
}
~~~

Nếu insert outbox thất bại, transaction rollback cả order. Nếu commit thành công, cả order và event cùng tồn tại trong database. Publisher đọc outbox sau đó và chuyển event tới consumer.

Đây là transaction cục bộ của database. Elasticsearch chưa được cập nhật trong transaction đó; việc cập nhật index diễn ra bất đồng bộ.

### 4.2. Saga orchestration

Một coordinator điều khiển các bước theo thứ tự. Mỗi bước có lệnh thực hiện (forward action), kết quả hoặc receipt cần lưu, điều kiện thành công/thất bại, hành động bù trừ (compensation) và chính sách retry/timeout.

Ví dụ:

~~~text
Saga: PlaceOrder
    |
    v
Create pending order
    |
    v
Reserve inventory
    |
    v
Capture payment
    |
    v
Confirm order
    |
    v
Publish OrderConfirmed

Nếu Capture payment thất bại:
    Release inventory
    Cancel pending order
~~~

Coordinator biết workflow đang ở bước nào và có thể tiếp tục sau khi process restart. Không nên chỉ giữ trạng thái trong biến local hoặc một chuỗi try/catch trong bộ nhớ nếu nghiệp vụ cần phục hồi sau crash.

### 4.3. Saga choreography

Trong choreography, mỗi dịch vụ hoàn thành công việc của mình rồi phát event để dịch vụ tiếp theo phản ứng:

~~~text
OrderCreated
    |
    v
Inventory service
    |
    +--> InventoryReserved
    |
    +--> InventoryReservationFailed

InventoryReserved
    |
    v
Payment service
    |
    +--> PaymentCaptured
    |
    +--> PaymentFailed
~~~

Choreography giảm sự phụ thuộc vào một coordinator trung tâm nhưng có thể làm luồng nghiệp vụ khó quan sát khi có nhiều event và nhánh compensation. Cần correlation ID, event schema ổn định, idempotent consumer và nơi theo dõi trạng thái saga.

Chọn orchestration nếu workflow có nhiều bước tuần tự, timeout và compensation phức tạp. Chọn choreography khi các dịch vụ phản ứng độc lập với event và luồng tổng thể không cần một coordinator điều khiển chi tiết.

## 5. Compensation là gì?

Compensation là một hành động nghiệp vụ mới nhằm giảm hoặc đảo ngược tác động của bước đã hoàn thành trước đó.

| Forward action | Compensation |
|---|---|
| Giữ tồn kho | Giải phóng reservation |
| Thu tiền | Hoàn tiền |
| Tạo order pending | Hủy order pending |
| Gán chỗ ngồi | Bỏ giữ chỗ |
| Tạo shipment label | Hủy label nếu hãng vận chuyển cho phép |
| Gửi thông báo | Gửi thông báo đính chính; không thể thu hồi email đã gửi |

Compensation không phải rollback vật lý của transaction ban đầu. Nó có thể thất bại và cần retry, không khôi phục trạng thái chính xác như trước, tạo thêm event/audit record hoặc bị giới hạn bởi chính sách nghiệp vụ và hệ thống bên ngoài. Một số tác động không thể đảo ngược hoàn toàn.

Ví dụ hoàn tiền không xóa sự kiện đã thu tiền; nó tạo một giao dịch hoàn tiền mới liên kết với giao dịch gốc. Gửi email đính chính không làm email đầu tiên biến mất khỏi hộp thư người nhận.

### 5.1. Compensation cần biết kết quả của bước gốc

Không nên gọi `releaseInventory(orderId)` một cách mù quáng nếu chưa biết reservation nào được tạo. Hãy lưu receipt:

~~~java
public record InventoryReservation(
        String reservationId,
        String orderId,
        String sku,
        int quantity
) {
}
~~~

Khi bù trừ, dùng reservation ID cụ thể. Tương tự, refund cần payment transaction ID và số tiền thực tế đã capture. Compensation phải nhắm đúng tác động của saga đó.

### 5.2. Compensation không luôn là phép đảo ngược toán học

Nếu tồn kho đã được reserve, release reservation thường là hành động bù phù hợp. Nhưng nếu hàng đã được đóng gói hoặc giao cho hãng vận chuyển, release reservation có thể sai; nghiệp vụ có thể cần return, cancel shipment hoặc xử lý ngoại lệ.

Vì vậy, compensation phải được thiết kế theo trạng thái hiện tại và quy tắc domain, không chỉ gọi một method có tên đối nghịch.

## 6. Thiết kế trạng thái Saga có thể phục hồi

Một saga cần lưu trạng thái bền vững. Ví dụ:

~~~java
public enum SagaStatus {
    STARTED,
    INVENTORY_RESERVED,
    PAYMENT_CAPTURED,
    ORDER_CONFIRMED,
    COMPENSATING,
    COMPENSATION_PENDING,
    COMPENSATED,
    FAILED
}
~~~

Một bản ghi saga có thể chứa:

~~~java
public class OrderSaga {
    private String sagaId;
    private String orderId;
    private SagaStatus status;
    private String inventoryReservationId;
    private String paymentTransactionId;
    private int retryCount;
    private Instant createdAt;
    private Instant updatedAt;
    private String lastError;
}
~~~

Các field này là ví dụ domain; tên và cấu trúc cần phù hợp với ứng dụng. Quan trọng là coordinator có thể biết saga nào đang chạy, bước nào đã hoàn thành, receipt nào cần dùng khi compensation, lỗi gần nhất là gì, bước nào có thể retry và bước bù trừ nào còn pending.

Nếu dùng Elasticsearch để lưu saga state, phải cân nhắc kỹ yêu cầu durability, concurrency và truy vấn phục hồi. Với trạng thái điều phối quan trọng, database giao dịch thường thuận lợi hơn vì cần cập nhật trạng thái và outbox một cách nguyên tử. Elasticsearch có thể là read model cho dashboard saga.

## 7. Coordinator: tách forward action và compensation

Có thể mô hình hóa từng bước bằng một abstraction:

~~~java
public interface SagaStep<C, R> {

    R execute(C context);

    void compensate(C context, R result);
}
~~~

`context` chứa saga ID, order ID, idempotency key và kết quả từ các bước trước. `result` lưu receipt cần thiết cho compensation.

Ví dụ interface cho các dịch vụ:

~~~java
public interface InventoryService {
    InventoryReservation reserve(
            String orderId,
            String sku,
            int quantity,
            String idempotencyKey
    );

    void release(
            String reservationId,
            String idempotencyKey
    );
}

public interface PaymentService {
    PaymentReceipt capture(
            String orderId,
            long amountMinorUnits,
            String currency,
            String idempotencyKey
    );

    void refund(
            String paymentTransactionId,
            String idempotencyKey
    );
}
~~~

Một coordinator đơn giản có thể thể hiện thứ tự:

~~~java
public void placeOrder(OrderCommand command) {
    OrderSaga saga = sagaStore.start(command);
    InventoryReservation reservation = null;
    PaymentReceipt payment = null;

    try {
        reservation = inventoryService.reserve(
                command.orderId(),
                command.sku(),
                command.quantity(),
                saga.id() + ":reserve"
        );
        sagaStore.markInventoryReserved(saga.id(), reservation);

        payment = paymentService.capture(
                command.orderId(),
                command.amountMinorUnits(),
                command.currency(),
                saga.id() + ":capture"
        );
        sagaStore.markPaymentCaptured(saga.id(), payment);

        orderService.confirm(command.orderId());
        sagaStore.complete(saga.id());
    } catch (RuntimeException failure) {
        compensate(saga, reservation, payment, failure);
        throw failure;
    }
}
~~~

Đây là pseudocode để giải thích luồng. Trong production, không nên giữ toàn bộ workflow chỉ trong stack của một request. Mỗi bước và kết quả phải được lưu bền vững trước khi chuyển bước tiếp theo; worker có thể tiếp tục workflow sau restart. Cũng cần phân biệt timeout không rõ kết quả với lỗi chắc chắn chưa thực hiện.

## 8. Thực hiện compensation theo thứ tự ngược

Nếu workflow đã reserve inventory rồi capture payment, khi phải hủy thường cần refund payment trước và release inventory sau:

~~~java
private void compensate(
        OrderSaga saga,
        InventoryReservation reservation,
        PaymentReceipt payment,
        RuntimeException cause
) {
    sagaStore.markCompensating(saga.id(), cause);

    if (payment != null) {
        try {
            paymentService.refund(
                    payment.transactionId(),
                    saga.id() + ":refund"
            );
            sagaStore.markPaymentRefunded(saga.id());
        } catch (RuntimeException refundFailure) {
            sagaStore.markCompensationPending(
                    saga.id(),
                    "PAYMENT_REFUND",
                    refundFailure.getMessage()
            );
            return;
        }
    }

    if (reservation != null) {
        try {
            inventoryService.release(
                    reservation.reservationId(),
                    saga.id() + ":release"
            );
            sagaStore.markInventoryReleased(saga.id());
        } catch (RuntimeException releaseFailure) {
            sagaStore.markCompensationPending(
                    saga.id(),
                    "INVENTORY_RELEASE",
                    releaseFailure.getMessage()
            );
            return;
        }
    }

    orderService.cancelPending(saga.orderId());
    sagaStore.markCompensated(saga.id());
}
~~~

Đoạn code minh họa cách biểu diễn. Một coordinator bền vững cần lưu từng trạng thái compensation riêng để retry chính xác bước đang lỗi, không bắt đầu lại compensation từ đầu một cách mù quáng. Nếu refund thất bại, không được đánh dấu saga đã compensated. Có thể cần tiếp tục retry refund trước khi release inventory hoặc áp dụng quy tắc nghiệp vụ khác.

Thứ tự bù trừ thường đi ngược thứ tự forward, nhưng không phải lúc nào cũng đảo ngược cơ học. Thứ tự phải theo dependency và an toàn nghiệp vụ.

## 9. Timeout không đồng nghĩa thao tác thất bại

Đây là một trong những lỗi nguy hiểm nhất khi phối hợp nhiều hệ thống.

Ví dụ:

1. Ứng dụng gửi yêu cầu capture payment.
2. Payment gateway thực hiện capture thành công.
3. Response bị mất hoặc về muộn.
4. Ứng dụng timeout và nghĩ rằng payment thất bại.
5. Saga chạy compensation hoặc retry.

Nếu retry capture mà không có idempotency key, khách hàng có thể bị thu tiền hai lần. Nếu compensation refund khi chưa biết capture có thành công không, có thể refund sai hoặc tạo lỗi đối soát.

Với timeout có kết quả không rõ:

- Query trạng thái giao dịch bằng idempotency key hoặc transaction reference.
- Retry cùng idempotency key nếu API bên ngoài hỗ trợ.
- Lưu trạng thái UNKNOWN/PENDING_CONFIRMATION thay vì kết luận thất bại ngay.
- Chỉ chạy compensation sau khi xác định forward action đã có hiệu lực.

## 10. Idempotency cho forward action và compensation

Một bước idempotent có thể được gọi nhiều lần mà kết quả nghiệp vụ không bị nhân đôi.

Mỗi hành động nên có key ổn định theo saga và bước:

~~~text
saga-8f2:reserve
saga-8f2:capture
saga-8f2:refund
saga-8f2:release
~~~

Service đích cần lưu key và kết quả đã xử lý. Khi nhận lại cùng key, nó trả kết quả cũ hoặc xác nhận thao tác đã hoàn tất thay vì thực hiện lại tác động.

Idempotency cần áp dụng cho cả reserve inventory, capture payment, refund, release reservation, publish/consume event và ghi projection Elasticsearch.

Không chỉ dựa vào việc HTTP method là PUT hay DELETE để kết luận operation idempotent. Ví dụ một script tăng counter mỗi lần chạy là không idempotent nếu request bị gửi lại.

## 11. Ghi Elasticsearch như một projection bằng Outbox

Giả sử order database là nguồn dữ liệu có thẩm quyền, còn Elasticsearch phục vụ tìm kiếm. Khi order được xác nhận, cần cập nhật order và tạo event trong cùng database transaction:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    outboxRepository.save(
            OutboxEvent.of(
                    "OrderConfirmed",
                    order.getId(),
                    order.getVersion(),
                    serialize(order)
            )
    );
}
~~~

Sau khi transaction commit, publisher đọc outbox và gửi event tới broker hoặc consumer. Consumer cập nhật Elasticsearch:

~~~java
public void onOrderConfirmed(OrderConfirmed event) {
    OrderDocument document = OrderDocument.from(event);
    elasticsearchOperations.save(document);
}
~~~

Ví dụ này là skeleton; cần bổ sung ack, retry, event schema, deduplication và xử lý version/order. Ưu điểm quan trọng là order update và outbox insert nằm trong cùng transaction database. Nếu process chết sau commit nhưng trước khi publish, event vẫn nằm trong outbox để publisher gửi lại.

### 11.1. Vì sao không chỉ dùng @TransactionalEventListener?

`@TransactionalEventListener(phase = AFTER_COMMIT)` có thể chạy sau khi transaction commit, hữu ích cho tác vụ nội bộ không cần delivery bền vững. Nhưng nếu process chết sau commit và trước khi listener xử lý, event trong bộ nhớ có thể bị mất.

Outbox giải quyết khoảng trống đó bằng cách ghi event vào database cùng transaction với dữ liệu nghiệp vụ. Publisher có thể tiếp tục sau restart.

### 11.2. At-least-once delivery và consumer idempotent

Outbox publisher thường có thể gửi lại event nếu không nhận được acknowledgement. Vì vậy consumer nên giả định event có thể đến nhiều lần.

Một consumer có thể lưu `eventId` đã xử lý trong inbox/deduplication table. Nếu event đã được áp dụng, bỏ qua lần lặp. Với Elasticsearch projection, dùng document ID ổn định và event version để tránh tạo duplicate document hoặc áp dụng event cũ sau event mới.

## 12. Ghi projection Elasticsearch theo thứ tự và version

Một rủi ro của event delivery là event có thể đến không theo thứ tự:

~~~text
OrderUpdated version 12
OrderUpdated version 11
~~~

Nếu consumer áp dụng version 11 sau version 12 bằng một thao tác ghi thay thế, projection có thể bị lùi về trạng thái cũ.

Các cách bảo vệ:

- Đưa aggregate version vào event.
- Bỏ qua event có version không mới hơn version đã áp dụng.
- Dùng optimistic concurrency hoặc external versioning phù hợp với API.
- Đảm bảo consumer serialize event theo aggregate key nếu broker hỗ trợ partition ordering.

Với Spring Data Elasticsearch, entity có thể khai báo `@Version` để dùng optimistic locking trong các thao tác save/update được hỗ trợ. Khi xảy ra version conflict, đọc lại trạng thái mới nhất và quyết định có thể áp dụng event hay cần bỏ qua.

Nếu dùng low-level Elasticsearch client, có thể dùng `if_seq_no` và `if_primary_term` để bảo vệ thao tác dựa trên phiên bản document đã đọc. Không tự tăng hoặc giả định sequence number; lấy giá trị từ response/get result theo API đang dùng.

### 12.1. Ghi projection theo trạng thái tuyệt đối

Với read model, thường an toàn hơn khi event mang trạng thái mới đầy đủ hoặc đủ dữ liệu để tạo projection:

~~~java
OrderDocument document = new OrderDocument(
        event.orderId(),
        event.aggregateVersion(),
        event.status(),
        event.totalAmount(),
        event.customerName()
);

elasticsearchOperations.save(document);
~~~

Ghi trạng thái tuyệt đối theo version dễ xử lý duplicate hơn một script kiểu “tăng số lượng lên 1” hoặc “cộng thêm tiền”. Nếu event chỉ là delta, consumer cần sequence/version và cơ chế deduplication chắc chắn để không áp dụng cùng delta hai lần.

## 13. Compensation cho thao tác Elasticsearch nhiều document

Nếu một workflow thật sự cần thay đổi nhiều document Elasticsearch, đừng xem Bulk API là transaction. Hãy lưu danh sách item và trạng thái riêng:

~~~text
Operation group G-100
  doc A -> APPLIED
  doc B -> FAILED
  doc C -> APPLIED
  doc D -> NOT_ATTEMPTED
~~~

Nếu nghiệp vụ yêu cầu bù trừ, chỉ bù các item đã được áp dụng thành công và còn đủ điều kiện bù. Không chạy compensation cho item thất bại hoặc chưa gửi.

### 13.1. Lưu before-image hoặc business receipt

Để khôi phục một document, ứng dụng có thể cần lưu:

- ID document.
- Trạng thái trước khi thay đổi (before-image) hoặc thông tin đủ để tạo hành động bù.
- Version trước/sau.
- Saga ID và operation ID.
- Trạng thái thao tác.

Không phải lúc nào cũng cần lưu toàn bộ source document. Nếu document lớn, có thể lưu một business receipt tối thiểu hoặc event thể hiện thay đổi.

### 13.2. Không restore before-image một cách mù quáng

Giả sử workflow A đổi trạng thái order từ PENDING sang PROCESSING. Trong lúc đó workflow B cập nhật địa chỉ giao hàng. Nếu workflow A thất bại và restore toàn bộ before-image, thay đổi địa chỉ của B có thể bị mất.

Compensation nên cập nhật đúng field mà workflow sở hữu và dùng version/condition để kiểm tra document chưa bị thay đổi bởi tác nhân khác. Nếu version đã đổi, cần đọc lại và đưa ra quyết định nghiệp vụ, không overwrite toàn bộ source.

## 14. Bulk response: chỉ xử lý item thực sự thành công

Khi dùng Elasticsearch Java Client, Bulk API trả item response tương ứng với từng operation. Cần duyệt từng item để phân loại:

~~~java
BulkResponse response = elasticsearchClient.bulk(request);

for (BulkResponseItem item : response.items()) {
    if (item.error() == null) {
        operationStore.markApplied(item.id());
    } else if (isRetryable(item.status(), item.error())) {
        operationStore.markRetryable(
                item.id(),
                item.error().reason()
        );
    } else {
        operationStore.markFailed(
                item.id(),
                item.error().reason()
        );
    }
}
~~~

Tên kiểu và getter có thể thay đổi theo phiên bản Elasticsearch Java Client. Ý nghĩa cần giữ là kiểm tra lỗi ở từng item, không chỉ nhìn cờ `errors` tổng quát.

Phân loại lỗi:

- Mapping/validation error thường cần sửa dữ liệu hoặc mapping; retry y nguyên thường không giúp.
- Version conflict có thể cần đọc lại và áp dụng logic nghiệp vụ.
- Rejected execution hoặc lỗi tạm thời có thể retry với backoff.
- Timeout có thể không rõ item đã được áp dụng hay chưa; cần kiểm tra trạng thái hoặc dùng idempotent operation.

## 15. Optimistic concurrency khi compensation

Compensation cũng là một thao tác ghi và có thể xung đột với cập nhật đồng thời. Không nên cho rằng vì saga đang rollback nên nó có quyền ghi đè mọi thay đổi.

Ví dụ document có version 7 khi saga cập nhật. Một người dùng khác cập nhật thành version 8. Sau đó saga muốn compensation:

~~~text
Saga write: version 7 -> 8
Other writer: version 8 -> 9
Saga compensation attempts based on version 8
       |
       v
Version conflict
~~~

Conflict cho biết trạng thái đã thay đổi kể từ khi saga thực hiện bước gốc. Coordinator cần:

1. Đọc document hiện tại.
2. Kiểm tra field mà saga đã thay đổi còn giữ giá trị do saga đặt hay không.
3. Xác định có thể đảo ngược field đó mà không ảnh hưởng thay đổi khác.
4. Ghi compensation với concurrency condition mới nếu nghiệp vụ cho phép.
5. Nếu không an toàn, chuyển sang trạng thái cần xử lý thủ công hoặc forward recovery.

Không retry vô hạn cùng một payload/version cũ. Với version conflict, retry phải dựa trên trạng thái mới và quyết định nghiệp vụ mới.

## 16. Retry, backoff và phân loại lỗi

Không phải lỗi nào cũng cần compensation ngay. Trước hết cần phân biệt lỗi tạm thời, lỗi vĩnh viễn và kết quả không rõ.

| Loại kết quả | Hành động thường dùng |
|---|---|
| Success | Lưu receipt và chuyển bước tiếp theo |
| Validation/mapping error | Dừng forward flow, sửa dữ liệu hoặc bắt đầu compensation nếu bước trước đã có tác động |
| Version conflict | Đọc lại, đánh giá lại và quyết định retry |
| Throttling/rejected execution | Retry có backoff và giới hạn |
| Network timeout | Xác minh kết quả bằng operation ID trước khi retry/compensate |
| Service unavailable | Retry có giới hạn, sau đó chuyển pending hoặc compensation |
| Compensation thất bại | Lưu trạng thái compensation pending và retry riêng |

Backoff có thể dùng exponential delay kèm jitter để tránh nhiều worker retry cùng lúc. Cần có giới hạn số lần thử, thời gian tối đa và cơ chế dead-letter/manual intervention.

Không giữ một HTTP request đồng bộ mở trong nhiều phút để chờ toàn bộ Saga hoàn tất. Có thể trả về trạng thái PENDING cùng operation ID, rồi client truy vấn trạng thái hoặc nhận callback/event khi workflow kết thúc.

## 17. Trạng thái workflow và quan sát vận hành

Workflow cần quan sát được từ log và metrics. Mỗi log/trace nên mang sagaId, operationId, orderId hoặc business key, stepName, attempt, outcome, compensationStatus và correlationId/trace ID.

Metrics nên dùng tag có cardinality thấp như step name, outcome và loại workflow. Không dùng order ID, customer ID hoặc saga ID làm tag metrics vì sẽ tạo quá nhiều time series.

Dashboard nên thể hiện:

- Số saga đang chạy.
- Số saga pending lâu hơn ngưỡng.
- Số compensation đang chờ.
- Retry rate theo step.
- Số event outbox chưa publish.
- Độ trễ từ database commit đến Elasticsearch projection.
- Số version conflict và bulk item failure.

Một workflow ở trạng thái COMPENSATION_PENDING không phải là workflow đã hoàn tất. Cần alert và quy trình vận hành để xử lý.

## 18. Khi Elasticsearch cập nhật chậm, có nên bù trừ payment không?

Nếu Elasticsearch chỉ là read model, câu trả lời thường là không. Khi order đã được xác nhận trong database và outbox event đã commit, việc index chậm là vấn đề đồng bộ projection, không phải lý do để refund khách hàng hoặc release inventory.

Luồng nên là:

1. Transaction database xác nhận order và ghi outbox.
2. Publisher gửi event.
3. Consumer thử ghi Elasticsearch.
4. Nếu lỗi tạm thời, retry.
5. Nếu mapping hoặc dữ liệu sai, đưa event vào dead-letter/repair flow.
6. Khi sửa xong, replay event hoặc rebuild projection.

Compensation payment/inventory chỉ nên được kích hoạt khi điều kiện nghiệp vụ của Saga yêu cầu hủy order, ví dụ payment bị từ chối hoặc reservation không thể hoàn tất. Không gắn compensation tài chính với mọi lỗi kỹ thuật ở read model.

## 19. Kiểm thử Saga và compensation

Một workflow nhiều bước cần test cả luồng thành công và failure injection.

### 19.1. Happy path

Xác nhận order được tạo, inventory reservation được tạo, payment được capture đúng một lần, order chuyển sang confirmed, outbox event được tạo, Elasticsearch projection được cập nhật và saga kết thúc ở trạng thái completed.

### 19.2. Payment thất bại sau khi reserve inventory

Giả lập inventory reserve thành công và payment bị từ chối:

- Reservation được release đúng một lần.
- Order được hủy theo quy tắc nghiệp vụ.
- Không có payment capture thành công.
- Saga lưu trạng thái compensated.

### 19.3. Compensation thất bại

Giả lập refund hoặc release thất bại:

- Saga không được đánh dấu completed/compensated.
- Bước compensation lỗi được lưu riêng.
- Retry chỉ chạy bước còn pending.
- Idempotency key giữ nguyên qua retry.
- Alert hoặc cơ chế vận hành nhận biết saga bị kẹt.

### 19.4. Timeout với kết quả không rõ

Giả lập service thực hiện thành công nhưng client timeout:

- Coordinator không lập tức giả định thao tác chưa xảy ra.
- Truy vấn theo idempotency key/operation reference.
- Retry cùng key không tạo tác động lặp.
- Compensation chỉ chạy sau khi biết chính xác forward action đã có hiệu lực.

### 19.5. Elasticsearch unavailable

Nếu database và outbox đã commit nhưng Elasticsearch dừng:

- Order vẫn giữ trạng thái nghiệp vụ đúng trong database.
- Outbox event còn tồn tại.
- Publisher/consumer retry sau khi Elasticsearch phục hồi.
- Không refund hoặc cancel order chỉ vì projection chưa cập nhật.

### 19.6. Version conflict trong compensation

Giả lập một writer khác cập nhật document sau forward action:

- Compensation dùng concurrency control và nhận conflict.
- Không overwrite dữ liệu mới hơn.
- Coordinator đọc lại và đánh giá field cần bù.
- Nếu không thể bù an toàn, chuyển trạng thái manual/forward recovery.

## 20. Checklist thiết kế phối hợp nhiều thao tác

- [ ] Xác định source of truth cho từng aggregate.
- [ ] Xác định thao tác nào nằm trong cùng local transaction.
- [ ] Không giả định @Transactional bao phủ Elasticsearch và dịch vụ HTTP.
- [ ] Không xem Bulk API là transaction all-or-nothing.
- [ ] Chia workflow thành các bước có trạng thái và receipt.
- [ ] Chọn Saga orchestration hoặc choreography.
- [ ] Định nghĩa compensation theo nghiệp vụ.
- [ ] Lưu saga state bền vững để phục hồi sau restart.
- [ ] Dùng idempotency key ổn định cho forward và compensation.
- [ ] Phân biệt lỗi chắc chắn thất bại với timeout có kết quả không rõ.
- [ ] Dùng Outbox cho event cần phát bền vững sau database commit.
- [ ] Làm consumer idempotent và xử lý event đến trùng/thứ tự sai.
- [ ] Dùng version/concurrency control khi cập nhật hoặc bù trừ document.
- [ ] Kiểm tra kết quả từng item trong Bulk response.
- [ ] Theo dõi compensation pending, retry và outbox backlog.
- [ ] Test failure injection, retry, timeout, duplicate event và version conflict.

## 21. Kết luận

Phối hợp nhiều thao tác nghiệp vụ cần một workflow có trạng thái rõ ràng. Elasticsearch cung cấp thao tác document và Bulk API, nhưng không cung cấp một transaction ACID chung cho chuỗi cập nhật nhiều document hoặc nhiều hệ thống. @Transactional của Spring chỉ quản lý resource transaction đã cấu hình; nó không tự rollback payment, inventory hoặc Elasticsearch khi một bước khác thất bại.

Với dữ liệu nghiệp vụ nằm trong database và Elasticsearch là read model, hãy ghi thay đổi nghiệp vụ cùng outbox event trong một local transaction, rồi cập nhật index bằng consumer idempotent. Nếu nghiệp vụ trải qua nhiều dịch vụ, dùng Saga orchestration hoặc choreography để theo dõi từng bước, lưu receipt và thực hiện compensation khi cần.

Compensation là hành động nghiệp vụ mới, có thể thất bại và cần retry. Nó phải idempotent, nhắm đúng tác động của saga và tôn trọng optimistic concurrency để không ghi đè thay đổi mới hơn. Khi timeout chưa rõ kết quả, hãy xác minh bằng operation ID/idempotency key trước khi retry hoặc bù trừ. Một workflow tốt có thể tiếp tục, bù trừ hoặc chuyển sang xử lý thủ công mà không làm mất dấu trạng thái nghiệp vụ.
