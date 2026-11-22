# Thiết kế ranh giới giao dịch cho tạo đơn, sửa đơn và hủy đơn

## 1. Vì sao transaction boundary quan trọng trong vòng đời đơn hàng?

Tạo, sửa và hủy đơn hàng thường trông giống những thao tác CRUD đơn giản. Tuy nhiên, một đơn hàng có thể liên quan tới nhiều dữ liệu cần nhất quán cùng lúc:

- Thông tin người mua và địa chỉ giao hàng được chụp tại thời điểm đặt hàng.
- Các dòng sản phẩm, số lượng, giá bán và chiết khấu.
- Tổng tiền, thuế, phí vận chuyển và tiền tệ.
- Tồn kho hoặc reservation cho từng SKU.
- Trạng thái đơn hàng và lịch sử thay đổi trạng thái.
- Mã khuyến mãi, hạn mức sử dụng hoặc điểm thưởng.
- Payment intent, khoản thanh toán và refund.
- Sự kiện gửi email, tạo vận đơn hoặc thông báo cho hệ thống khác.

Nếu mỗi repository method tự mở transaction riêng, một thao tác nghiệp vụ có thể bị chia thành nhiều phần commit độc lập. Ví dụ, hệ thống ghi order thành công, trừ tồn kho thất bại, rồi trả lỗi cho người dùng. Database lúc này chứa một đơn hàng không có hàng được giữ.

Ngược lại, nếu đặt một transaction quá rộng bao quanh cả database, gọi payment gateway, gửi email và chờ shipping API, transaction có thể giữ connection/locks trong thời gian dài. Khi mạng chậm, database connection bị chiếm dụng và những requests khác bị ảnh hưởng.

Thiết kế đúng cần trả lời hai câu hỏi:

1. **Những thay đổi dữ liệu nào phải thành công hoặc thất bại cùng nhau trong một database?**
2. **Những công việc nào nằm ngoài transaction đó và cần cơ chế phối hợp riêng?**

Bài học thuộc chương **Thực hành tổng hợp** trong module *Data Persistence Relational Access ORM Hibernate*. Trọng tâm là thiết kế transaction boundary cho ba use cases tạo đơn, sửa đơn và hủy đơn trong ứng dụng Java/Spring Data JPA/Hibernate.

### 1.1. Mục tiêu

Sau bài học, bạn có thể:

1. Xác định transaction boundary theo use case và business invariants.
2. Tổ chức service/application layer để mỗi thao tác nghiệp vụ có một transaction rõ ràng.
3. Phân biệt transaction của database với workflow liên hệ nhiều hệ thống.
4. Thiết kế tạo đơn có kiểm tra giá, tồn kho, tổng tiền và trạng thái nhất quán.
5. Thiết kế sửa đơn có kiểm soát thay đổi dòng hàng và tính lại tổng.
6. Thiết kế hủy đơn với hoàn tồn kho, giải phóng reservation và xử lý payment/refund.
7. Sử dụng Spring `@Transactional`, propagation, isolation, rollback rules và optimistic locking đúng cách.
8. Ngăn duplicate requests, lost updates và overselling.
9. Dùng outbox/saga cho side effects bên ngoài database.
10. Viết integration tests để chứng minh transaction commit/rollback và concurrency behavior.

## 2. Transaction boundary bắt đầu từ use case

### 2.1. Transaction không nên được đặt tùy tiện ở từng repository method

Ví dụ repository tự quản lý transaction:

~~~java
public void saveOrder(Order order) {
    transactionTemplate.execute(status -> {
        entityManager.persist(order);
        return null;
    });
}
~~~

Nếu service sau đó gọi thêm repository để reserve inventory, mỗi repository có thể commit riêng. Một use case tạo đơn không còn là một đơn vị nguyên tử.

Với Spring Data JPA, repository methods thường đã có transaction behavior mặc định phù hợp với loại method, nhưng service layer nên định nghĩa transaction bao quanh toàn bộ use case cần nhất quán.

Ví dụ:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    @Transactional
    public OrderId placeOrder(PlaceOrderCommand command) {
        // Validate và load dữ liệu cần thiết.
        // Reserve stock.
        // Tạo order và order lines.
        // Persist mọi thay đổi trong cùng transaction.
        return null;
    }
}
~~~

Repository tham gia transaction hiện tại theo propagation mặc định `REQUIRED`. Khi method service hoàn tất bình thường, transaction commit; nếu exception phù hợp được ném ra, transaction rollback.

### 2.2. Một transaction nên bảo vệ một business invariant

Ví dụ invariant khi tạo đơn:

- Đơn phải có ít nhất một dòng hàng.
- Mỗi dòng có số lượng dương.
- Giá được dùng để tính tổng phải là giá đã được xác nhận tại thời điểm đặt.
- Tổng tiền phải bằng tổng các thành phần hợp lệ.
- Không được reserve quá số lượng có thể bán.
- Nếu đơn ở trạng thái `CONFIRMED`, reservation tương ứng phải tồn tại.
- Order và order lines phải được lưu cùng nhau.

Nếu các dữ liệu này nằm trong cùng database và phải thay đổi nguyên tử, một transaction service-level thường là ranh giới phù hợp.

### 2.3. Không phải mọi thứ trong một use case đều nằm trong một DB transaction

Ví dụ đặt hàng có thể cần:
- Ghi order.
- Reserve stock.
- Ghi outbox event.
- Yêu cầu payment gateway authorize.
- Gửi email.
- Tạo shipping label.

Ba thao tác đầu có thể nằm trong một database transaction. Payment gateway, email và shipping service là hệ thống bên ngoài; không thể rollback chúng bằng cách rollback JDBC transaction.

Một transaction boundary rõ ràng thường **commit trạng thái và ý định cần thực hiện**, sau đó worker xử lý các side effects ngoài DB theo cơ chế retry/idempotency.

### 2.4. Sơ đồ tổng quan

~~~text
HTTP request
    |
    v
OrderApplicationService
    |
    | @Transactional
    v
+----------------------------------+
| Database transaction             |
|                                  |
|  validate current state          |
|  reserve inventory               |
|  create/update/cancel order      |
|  update totals/status/version    |
|  write audit/outbox records      |
|                                  |
+----------------------------------+
    |
    v
Commit
    |
    v
Outbox worker / workflow coordinator
    |
    +--> payment provider
    +--> shipping service
    +--> email/notification
~~~

Transaction database chỉ bảo đảm tính nguyên tử cho những writes nằm trong transaction manager/database đó.

## 3. Mô hình domain tối thiểu cho order

### 3.1. Order và OrderLine

Một order có thể chứa:

~~~text
Order
  id
  customerId
  status
  currency
  subtotal
  discountTotal
  taxTotal
  shippingFee
  grandTotal
  shippingAddressSnapshot
  version
  createdAt
  updatedAt
  lines[]
      productId
      sku
      productNameSnapshot
      unitPrice
      quantity
      lineTotal
~~~

Các snapshot như tên sản phẩm, giá, địa chỉ giúp order lịch sử phản ánh thông tin tại thời điểm đặt. Nếu chỉ giữ product ID rồi luôn join catalog hiện tại, đơn hàng cũ có thể hiển thị tên/giá mới sau khi catalog thay đổi.

### 3.2. Inventory và reservation

Inventory có thể được quản lý bởi một aggregate/service riêng:

~~~text
InventoryItem
  sku
  availableQuantity
  reservedQuantity
  version

InventoryReservation
  id
  orderId
  sku
  quantity
  status
  expiresAt
~~~

Nếu order và inventory cùng một relational database, có thể cập nhật chúng trong cùng transaction. Nếu inventory nằm trong service/database riêng, không thể dùng một JPA transaction để bảo đảm atomicity xuyên hai databases; cần reservation workflow/saga.

### 3.3. Payment không đồng nhất với Order status

Payment có lifecycle riêng:

~~~text
Payment
  id
  orderId
  providerReference
  status
  authorizedAmount
  capturedAmount
  refundedAmount
  idempotencyKey
~~~

Một order `CANCELLED` không tự động có nghĩa payment đã refund. Có thể order được hủy trước khi thanh toán, payment đang authorize, payment đã capture hoặc refund đang pending.

Hãy model các trạng thái tách biệt và biểu diễn quá trình phối hợp bằng workflow.

### 3.4. Invariants cần ghi thành quy tắc

Ví dụ:
- `quantity > 0`.
- `unitPrice >= 0`.
- `grandTotal = subtotal - discountTotal + taxTotal + shippingFee`.
- Không cho sửa order đã shipped/delivered.
- Không cho cancel order đã hoàn tất nếu business không có quy trình return/refund riêng.
- Một reservation chỉ được release một lần.
- Một payment capture/refund không được thực hiện trùng do retry.
- Mỗi order có version tăng khi aggregate thay đổi.

Các invariants nên được bảo vệ ở nhiều lớp phù hợp:
- Domain validation cho business rules.
- Database constraints cho invariant có thể diễn đạt bằng schema.
- Transaction để nhóm writes nguyên tử.
- Concurrency control để ngăn hai requests cùng phá invariant.

## 4. Chọn phạm vi aggregate và transaction

### 4.1. Aggregate boundary không phải lúc nào cũng là transaction boundary

DDD thường yêu cầu một aggregate bảo vệ invariants bên trong aggregate. Trong một relational database, một use case có thể cần cập nhật nhiều aggregates trong cùng transaction nếu business invariant yêu cầu tính nguyên tử và phạm vi đó có thể kiểm soát.

Ví dụ tạo order và reserve inventory cùng database:
- Nếu order chỉ được coi là accepted khi stock đã reserve, cùng transaction có thể phù hợp.
- Nếu inventory được quản lý bởi service riêng, dùng reservation saga thay vì giả vờ có transaction phân tán.

Đừng đưa mọi bảng có liên quan vào một aggregate lớn chỉ để có một transaction. Cân nhắc contention, ownership và lifecycle.

### 4.2. Transaction boundary theo use case

| Use case | Trong database transaction | Sau commit / workflow |
|---|---|---|
| Tạo đơn | Validate state; reserve stock; tạo order/lines; ghi outbox | Payment authorization, notification, shipping |
| Sửa đơn | Kiểm tra version/status; cập nhật lines; điều chỉnh reservation; tính lại totals; ghi outbox | Đồng bộ catalog/search hoặc thông báo nếu cần |
| Hủy đơn | Kiểm tra cancel policy; đổi trạng thái; release reservation; ghi refund request/outbox | Gọi payment refund, gửi thông báo, xử lý carrier |
| Payment callback | Verify event; cập nhật payment/order state; ghi outbox | Gửi event/notification tiếp theo |
| Retry workflow | Claim task/outbox; cập nhật trạng thái xử lý có lease | Gọi provider idempotently |

Đây là điểm bắt đầu. Nếu business và data ownership khác, tách thành các local transactions và saga.

### 4.3. Đặt transaction ở application service

Một use case thường là public method của application service:

~~~java
@Transactional
public OrderId placeOrder(PlaceOrderCommand command) {
    // Orchestrate repositories và domain logic.
}
~~~

Method service diễn tả rõ transaction scope. Domain entity không tự mở transaction; repository không commit độc lập giữa một workflow; controller không nên giữ transaction trong suốt thời gian serialize response hoặc chờ remote calls.

### 4.4. Một use case, một transaction ngắn

Transaction nên:
- Bắt đầu khi đã có input cần thiết.
- Load/lock state cần thiết.
- Thực hiện business decision.
- Ghi các thay đổi liên quan.
- Commit càng sớm càng tốt.

Không giữ transaction mở trong khi:
- Chờ người dùng xác nhận OTP.
- Gọi payment/shipping API qua network.
- Gửi email.
- Chờ message broker response.
- Upload file lớn.
- Chạy batch hàng trăm nghìn rows.

## 5. Thiết kế transaction cho tạo đơn

Tạo đơn cần kiểm tra giá, tồn kho và dữ liệu người mua trong một snapshot nhất quán theo business policy.

### 5.1. Input là command, không phải entity client gửi lên

Không nhận một entity `Order` đầy đủ từ HTTP body rồi persist trực tiếp. Client có thể gửi:
- Giá giả.
- Tổng tiền giả.
- Trạng thái `PAID`.
- Customer ID của người khác.
- Reservation IDs không thuộc order.
- Các fields server phải kiểm soát.

Dùng command chỉ chứa dữ liệu người dùng được phép yêu cầu:

~~~java
public record PlaceOrderCommand(
    UUID customerId,
    List<OrderLineRequest> lines,
    String shippingAddressId,
    String idempotencyKey
) {}

public record OrderLineRequest(
    String sku,
    int quantity
) {}
~~~

Server tự xác thực customer, tải giá/coupon/shipping policy và tính totals.

### 5.2. Flow tạo đơn trong cùng database

Một flow tham khảo:

1. Kiểm tra idempotency key và xác định request đã xử lý chưa.
2. Xác thực customer và địa chỉ.
3. Kiểm tra command có lines hợp lệ, quantity dương.
4. Load catalog/pricing data theo policy.
5. Tính subtotal, discount, tax, shipping fee và total bằng decimal/currency rules.
6. Reserve inventory bằng atomic update hoặc row lock.
7. Tạo order với status thích hợp, ví dụ `PENDING_PAYMENT`.
8. Tạo order lines với snapshot giá/tên/SKU.
9. Ghi reservation records.
10. Ghi outbox event `OrderPlaced`/`PaymentAuthorizationRequested`.
11. Commit.
12. Workflow worker gọi payment provider và cập nhật kết quả qua một transaction mới.

Bước 6–10 cần nằm trong một DB transaction nếu các bảng cùng database và business yêu cầu nguyên tử.

### 5.3. Atomic inventory update

Tránh pattern không an toàn:

~~~java
InventoryItem item = repository.findBySku(sku).orElseThrow();

if (item.getAvailableQuantity() >= quantity) {
    item.setAvailableQuantity(item.getAvailableQuantity() - quantity);
}
~~~

Hai transactions có thể cùng đọc available = 1, cùng thấy đủ hàng rồi cùng trừ. Nếu không có lock/version/atomic condition, hệ thống có thể oversell.

Có thể dùng conditional update:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity,
    reserved_quantity = reserved_quantity + :quantity
WHERE sku = :sku
  AND available_quantity >= :quantity;
~~~

Kiểm tra affected row count:
- `1`: reserve thành công.
- `0`: SKU không tồn tại hoặc không còn đủ hàng; xác định lỗi phù hợp.

Câu lệnh là một thao tác nguyên tử ở database. Cần cân nhắc row count, isolation, constraints và database dialect.

### 5.4. Repository method cho atomic reservation

~~~java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, String> {

    @Modifying
    @Query("""
        update InventoryItem i
           set i.availableQuantity = i.availableQuantity - :quantity,
               i.reservedQuantity = i.reservedQuantity + :quantity
         where i.sku = :sku
           and i.availableQuantity >= :quantity
        """)
    int reserve(
        @Param("sku") String sku,
        @Param("quantity") int quantity
    );
}
~~~

Bulk JPQL update bypasses normal managed-entity dirty checking/callbacks và có thể làm persistence context stale. Nếu cùng transaction đã load `InventoryItem`, cần refresh/clear có chủ đích hoặc tránh giữ managed instance cũ. Không trộn bulk update với stale entity state rồi tiếp tục flush một cách tùy tiện.

### 5.5. Tạo order trong service

Ví dụ rút gọn:

~~~java
@Service
@RequiredArgsConstructor
public class OrderApplicationService {

    private final CustomerRepository customers;
    private final PricingService pricing;
    private final InventoryRepository inventory;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public OrderId placeOrder(PlaceOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(CustomerNotFoundException::new);

        validateAddress(customer, command.shippingAddressId());

        PricedOrder priced = pricing.price(command, customer);

        for (PricedLine line : priced.lines()) {
            int changed = inventory.reserve(
                line.sku(), line.quantity()
            );

            if (changed != 1) {
                throw new InsufficientStockException(line.sku());
            }
        }

        Order order = Order.pendingPayment(
            customer.getId(),
            priced,
            customer.snapshotAddress(command.shippingAddressId())
        );

        orders.save(order);
        outbox.save(OutboxEvent.orderPlaced(order));

        return order.getId();
    }
}
~~~

Đây là pseudocode theo domain model riêng của ứng dụng. Giá cần được tính bằng server-side pricing rules; `PricingService` không nên gọi remote service lâu trong transaction nếu có thể lấy snapshot trước hoặc dùng local data. Nếu giá cần xác nhận với một pricing service bên ngoài, thiết kế quote/expiry hoặc workflow riêng.

### 5.6. Khi một SKU xuất hiện nhiều lần

Nếu command có hai lines cùng SKU, reserve từng line vẫn có thể đúng nhưng có thể gây nhiều updates/locks. Có thể:
- Gộp quantities theo SKU trước khi reserve.
- Sort SKU keys nhất quán để giảm deadlock khi nhiều orders reserve nhiều products.
- Giữ order lines riêng nếu business cần phân biệt options/discounts.
- Đảm bảo tổng quantity dùng cho reservation bằng tổng quantities của lines.

### 5.7. Tính tiền và rounding

Không dùng `double`/`float` cho tiền. Dùng `BigDecimal` hoặc money type có currency và rounding policy rõ ràng.

~~~java
BigDecimal lineTotal = unitPrice
    .multiply(BigDecimal.valueOf(quantity))
    .setScale(2, RoundingMode.HALF_UP);
~~~

Tuy nhiên rounding thường cần quy tắc rõ theo currency và tax law:
- Round từng line hay chỉ round invoice total?
- Discount áp trước hay sau tax?
- Giá đã bao gồm VAT hay chưa?
- Phí vận chuyển có taxable không?
- Currency có 0, 2 hoặc 3 decimal places?

Lưu snapshot giá/discount/tax rates đã áp dụng. Không tính lại order cũ theo catalog/price hiện tại khi người dùng xem lịch sử.

### 5.8. Idempotency cho create order

Client có thể retry do timeout dù server đã commit. Nếu không có idempotency, retry có thể tạo hai orders và reserve stock hai lần.

Một thiết kế:
- Client gửi idempotency key ổn định cho một logical request.
- Database có unique constraint trên `(customer_id, idempotency_key)`.
- Trong transaction, tạo record/request mapping cùng order.
- Nếu key đã tồn tại, trả kết quả của request đã xử lý.
- Nếu concurrent requests cùng key, unique constraint chọn một winner; loser đọc kết quả đã commit và trả cùng response.

Idempotency key cần được scope theo customer/tenant và có retention policy. Không chỉ kiểm tra bằng SELECT trước INSERT vì hai requests đồng thời vẫn có thể cùng thấy key chưa tồn tại.

## 6. Thiết kế transaction cho sửa đơn

Sửa đơn thường phức tạp hơn một UPDATE vì phải giữ nhất quán giữa order lines, totals, inventory reservation và trạng thái workflow.

### 6.1. Xác định đơn có còn được sửa không

Trước khi cập nhật:
- Order có thuộc customer/tenant hiện tại không?
- Status có cho phép sửa không?
- Đơn đã payment capture chưa?
- Đã pick/pack/shipped chưa?
- Có promotion/quote đã hết hạn không?
- Có reservation nào sắp hết hạn không?
- Version của client có còn mới không?

Không cho phép sửa tùy tiện dựa trên việc entity có thể được load.

### 6.2. Sửa order lines cần tính delta inventory

Giả sử order hiện tại có:
- SKU-A quantity 2.
- SKU-B quantity 1.

User sửa thành:
- SKU-A quantity 3.
- SKU-B quantity 1.
- SKU-C quantity 2.

Delta:
- SKU-A: reserve thêm 1.
- SKU-B: không đổi.
- SKU-C: reserve thêm 2.

Nếu user giảm SKU-A từ 2 xuống 1, release 1 reservation. Không release rồi reserve lại toàn bộ nếu không cần thiết, vì làm tăng lock contention và có thể khiến order mất hàng trong lúc update.

### 6.3. Tính delta từ old state và requested state

Ví dụ:

~~~java
Map<String, Integer> oldQuantities = aggregateBySku(order.getLines());
Map<String, Integer> newQuantities = command.quantitiesBySku();

Set<String> allSkus = union(oldQuantities.keySet(), newQuantities.keySet());

for (String sku : sorted(allSkus)) {
    int oldQty = oldQuantities.getOrDefault(sku, 0);
    int newQty = newQuantities.getOrDefault(sku, 0);
    int delta = newQty - oldQty;

    if (delta > 0) {
        reserveAdditional(sku, delta);
    } else if (delta < 0) {
        releaseReservation(sku, -delta);
    }
}
~~~

Đây là logic khái niệm. Cần xử lý SKU option/warehouse/lot/bundle riêng nếu reservation key không chỉ là SKU.

### 6.4. Thứ tự locks nhất quán

Khi sửa nhiều SKU, hai transactions có thể lock SKU theo thứ tự khác nhau và deadlock.

Ví dụ:
- T1 lock A rồi chờ B.
- T2 lock B rồi chờ A.

Một cách giảm rủi ro là sort các inventory keys theo thứ tự ổn định trước khi lock/update. Điều này không loại bỏ mọi deadlock nhưng giúp giảm vòng chờ do thứ tự truy cập không nhất quán.

### 6.5. Tính lại totals từ authoritative inputs

Không nhận `subtotal`, `taxTotal`, `grandTotal` từ client. Service tính lại từ:
- Giá hiện tại hoặc quote được bảo đảm.
- Quantities mới.
- Discount eligibility.
- Tax rules.
- Shipping method/address.
- Currency/rounding policy.

Nếu giá đã thay đổi kể từ lúc tạo đơn, business cần chọn:
- Giữ giá đã quote nếu còn hiệu lực.
- Yêu cầu user chấp nhận giá mới.
- Từ chối edit và yêu cầu tạo order mới.
- Recalculate theo policy của hợp đồng.

### 6.6. Cập nhật aggregate trong một transaction

~~~java
@Transactional
public void amendOrder(
        OrderId orderId,
        AmendOrderCommand command) {

    Order order = orders.findByIdForUpdate(orderId)
        .orElseThrow(OrderNotFoundException::new);

    order.assertEditable();

    Map<String, Integer> oldQty = order.quantitiesBySku();
    Map<String, Integer> newQty = command.quantitiesBySku();

    adjustReservations(oldQty, newQty);

    PricedOrder newPrice = pricing.reprice(command, order);

    order.replaceLines(newPrice.lines());
    order.updateTotals(newPrice.totals());
    order.recordAmendment(command.actorId());

    outbox.save(OutboxEvent.orderAmended(order));
}
~~~

`findByIdForUpdate` có thể được triển khai bằng `PESSIMISTIC_WRITE`, hoặc dùng optimistic locking theo business contention. Nếu `adjustReservations` fail, exception phải làm rollback toàn bộ order lines/totals/outbox changes trong transaction.

### 6.7. Sửa đơn đã payment authorized/captured

Nếu order đã authorize/capture:
- Thay đổi tổng tiền có thể cần payment authorization bổ sung hoặc void/re-authorize.
- Giảm tổng tiền có thể cần partial refund.
- Thay đổi địa chỉ có thể cần update carrier/shipping label.
- Thay đổi items có thể ảnh hưởng fulfillment đã bắt đầu.

Đừng thực hiện payment gateway call giữa một transaction đang giữ locks. Ghi yêu cầu điều chỉnh vào workflow/outbox; cập nhật trạng thái theo kết quả provider ở transaction riêng. Nếu business không hỗ trợ amend sau payment, từ chối rõ và yêu cầu cancel/recreate.

## 7. Thiết kế transaction cho hủy đơn

### 7.1. Hủy đơn là một state transition

Không coi cancel chỉ là:

~~~java
order.setStatus(OrderStatus.CANCELLED);
~~~

Hủy đơn có thể yêu cầu:
- Kiểm tra trạng thái hiện tại có được cancel không.
- Đảm bảo chưa giao hoặc chưa có policy return khác.
- Release inventory reservation.
- Release coupon/promotion usage nếu policy cho phép.
- Ghi cancel reason/actor/time.
- Tạo refund request nếu payment đã capture.
- Gửi notification.
- Thông báo shipping/fulfillment nếu đã gửi lệnh.
- Lưu audit event.

Những thay đổi nội bộ cùng database có thể commit cùng nhau. Refund/shipping là side effects ngoài DB.

### 7.2. State machine ví dụ

~~~text
PENDING_PAYMENT
   | payment authorized
   v
CONFIRMED
   | accepted by fulfillment
   v
PROCESSING
   | shipped
   v
SHIPPED
   | delivered
   v
DELIVERED

PENDING_PAYMENT / CONFIRMED / PROCESSING
   |
   | cancel allowed by policy
   v
CANCEL_PENDING_EXTERNAL
   |
   +--> reservation released
   +--> refund requested if required
   |
   v
CANCELLED
~~~

State machine thực tế có thể khác. Ví dụ có thể đánh dấu order `CANCELLED` ngay khi yêu cầu cancel được chấp nhận, trong khi refund là trạng thái riêng `REFUND_PENDING`. Hoặc order ở `CANCEL_PENDING` cho tới khi carrier/payment provider xác nhận. Hãy định nghĩa rõ ý nghĩa status để UI/operations không hiểu nhầm.

### 7.3. Cancel transaction trong cùng database

~~~java
@Transactional
public void requestCancellation(
        OrderId orderId,
        CancelOrderCommand command) {

    Order order = orders.findByIdForUpdate(orderId)
        .orElseThrow(OrderNotFoundException::new);

    order.assertCancellationAllowed();

    releaseAllActiveReservations(order.getId());

    order.markCancellationRequested(
        command.reason(),
        command.actorId()
    );

    if (payments.requiresRefund(order)) {
        outbox.save(OutboxEvent.refundRequested(order));
    }

    outbox.save(OutboxEvent.orderCancellationRequested(order));
}
~~~

Ở đây:
- Reservation release và order state thay đổi trong cùng transaction.
- Outbox event chỉ được publish sau khi DB commit thông qua worker.
- Payment provider không được gọi trực tiếp trong transaction này.

### 7.4. Release reservation phải idempotent

Nếu một cancellation request bị retry, inventory không được cộng lại hai lần.

Một cách:
- Reservation có status `ACTIVE`, `RELEASED`, `CONSUMED`, `EXPIRED`.
- Chỉ chuyển `ACTIVE -> RELEASED` một lần.
- Cộng available quantity chỉ khi transition thành công.
- Dùng conditional update/row lock và unique/reference constraint phù hợp.

Ví dụ:

~~~sql
UPDATE inventory_reservations
SET status = 'RELEASED',
    released_at = CURRENT_TIMESTAMP
WHERE id = :reservationId
  AND status = 'ACTIVE';
~~~

Chỉ nếu affected row count là 1 mới cộng lại stock. Hai cancellation retries cùng reservation sẽ không cộng stock hai lần nếu transition và stock update nằm trong cùng transaction.

### 7.5. Hủy sau khi hàng đã shipped

Khi hàng đã shipped, release reservation thường không đúng vì hàng đã rời kho. Business flow có thể cần:
- Hủy giao hàng nếu carrier còn cho phép.
- Tạo return authorization.
- Khi hàng quay về và được kiểm tra, restock.
- Refund theo policy.
- Lưu trạng thái return/refund riêng.

Không cộng stock ngay khi nhận yêu cầu hủy nếu hàng đang ở carrier/customer.

### 7.6. Hủy khi payment đang xử lý

Nếu payment authorization đang pending, cancellation và provider callback có thể đến đồng thời. Cần:
- Correlate provider event bằng payment intent/reference.
- Xác định transition hợp lệ từ trạng thái hiện tại.
- Idempotently void authorization nếu cần.
- Không đánh dấu refund hoàn tất chỉ vì đã gửi request.
- Xử lý callback đến muộn bằng state machine/version checks.

Order status và payment status nên là hai state machines có quan hệ được định nghĩa.

## 8. Spring @Transactional: cách áp dụng đúng

### 8.1. Đặt annotation ở service boundary

~~~java
@Service
public class OrderApplicationService {

    @Transactional
    public OrderId placeOrder(PlaceOrderCommand command) {
        // Use case.
    }

    @Transactional
    public void amendOrder(AmendOrderCommand command) {
        // Use case.
    }

    @Transactional
    public void cancelOrder(CancelOrderCommand command) {
        // Use case.
    }
}
~~~

Spring transaction thường được quản lý qua proxy. Khi method được gọi qua proxy, interceptor mở/join transaction, sau đó commit hoặc rollback dựa trên kết quả.

### 8.2. Self-invocation không đi qua proxy

Ví dụ:

~~~java
@Service
public class OrderService {

    public void process() {
        placeOrder(); // gọi nội bộ trong cùng object
    }

    @Transactional
    public void placeOrder() {
        // ...
    }
}
~~~

Trong proxy-based transaction management mặc định, lời gọi nội bộ `this.placeOrder()` không đi qua proxy nên annotation trên method được gọi có thể không được áp dụng như kỳ vọng.

Giải pháp:
- Gọi transactional method qua một Spring bean khác.
- Đặt transaction ở method entry point được gọi từ bên ngoài.
- Dùng `TransactionTemplate` khi cần boundary lập trình.
- Không dựa vào self-invocation để tạo transaction lồng.

### 8.3. Visibility và proxy type

Các giới hạn proxy có thể phụ thuộc proxy mode (JDK interface proxy hay class-based proxy), Spring version và method visibility. Hãy đặt transaction ở public application service methods theo convention rõ ràng và kiểm tra cấu hình. Không coi mọi annotation ở mọi private/internal method đều được interceptor áp dụng.

### 8.4. Propagation REQUIRED

Mặc định `@Transactional` thường dùng `Propagation.REQUIRED`:
- Nếu chưa có transaction, mở transaction mới.
- Nếu đã có transaction, tham gia transaction hiện tại.

Đây thường là lựa chọn đúng cho repository/service calls cùng một use case.

~~~java
@Transactional
public void placeOrder(...) {
    inventoryService.reserve(...); // REQUIRED tham gia transaction
    orderRepository.save(...);
}
~~~

Nếu `reserve` ném runtime exception, transaction chung có thể rollback.

### 8.5. REQUIRES_NEW cần lý do rõ

`Propagation.REQUIRES_NEW` tạm suspend transaction hiện tại và mở transaction độc lập. Nó có thể hữu ích cho audit/telemetry mà business yêu cầu commit riêng, nhưng tạo rủi ro nếu dùng cho dữ liệu nghiệp vụ cốt lõi.

Ví dụ không nên:
- Order insert ở transaction ngoài.
- Inventory reservation chạy `REQUIRES_NEW` và commit.
- Order insert sau đó fail.
- Stock vẫn bị giữ cho order không tồn tại.

Đây là partial commit. Với order và reservation cùng database cần atomicity, hãy để chúng tham gia cùng transaction `REQUIRED`.

### 8.6. NESTED không đồng nghĩa distributed transaction

`NESTED` thường dựa trên savepoints nếu transaction manager/resource hỗ trợ. Nó có thể rollback một phần công việc về savepoint trong transaction hiện tại, nhưng outer transaction vẫn có quyền rollback toàn bộ.

Không dùng `NESTED` để phối hợp payment provider, message broker hay database khác. Savepoint chỉ điều khiển transaction resource hỗ trợ nó.

### 8.7. Read-only transaction

Query service:

~~~java
@Transactional(readOnly = true)
public OrderView getOrder(OrderId id) {
    // Load and map read model.
}
~~~

`readOnly=true` là hint cho transaction manager/provider/connection; mức enforcement tùy platform. Không dùng nó làm authorization hoặc bảo đảm tuyệt đối rằng không thể ghi. Đọc order trong transaction read-only giúp thể hiện intent và có thể tối ưu flush behavior.

### 8.8. Transaction timeout

Có thể đặt timeout cho transaction:

~~~java
@Transactional(timeout = 5)
public void amendOrder(...) {
    // Short database work.
}
~~~

Timeout semantics tùy transaction manager/provider/driver. Nó không tự hủy một HTTP call bên ngoài hoặc mọi câu SQL đang chạy ngay lập tức. Cấu hình query timeout/lock timeout/network timeout riêng nếu cần.

## 9. Rollback rules và exception handling

### 9.1. Runtime exception mặc định

Spring transaction mặc định thường rollback khi method ném `RuntimeException` hoặc `Error`. Checked exceptions mặc định không nhất thiết trigger rollback.

Ví dụ:

~~~java
@Transactional
public void placeOrder(...) throws PricingException {
    // PricingException là checked exception.
}
~~~

Nếu `PricingException` phải rollback transaction:

~~~java
@Transactional(rollbackFor = PricingException.class)
public void placeOrder(...) throws PricingException {
    // ...
}
~~~

Có thể dùng `noRollbackFor` cho exception đặc biệt, nhưng chỉ khi business thực sự muốn commit phần thay đổi trước exception đó.

### 9.2. Không nuốt exception rồi trả lỗi bình thường

Ví dụ nguy hiểm:

~~~java
@Transactional
public Result placeOrder(...) {
    try {
        inventory.reserve(...);
    } catch (InsufficientStockException ex) {
        return Result.failed("Out of stock");
    }

    orders.save(...);
    return Result.success();
}
~~~

Nếu exception bị catch và không đánh dấu rollback-only, transaction có thể commit các thay đổi đã thực hiện trước đó. Nếu business muốn thất bại toàn bộ, hãy để exception thoát khỏi transactional method hoặc chủ động đánh dấu rollback-only.

Một lựa chọn là trả failure trước khi có writes, hoặc dùng domain result và không thực hiện bất kỳ mutation nào khi validation fail.

### 9.3. Checked exception và wrapping

Có thể chuyển lỗi thành runtime domain exception:

~~~java
catch (PricingException ex) {
    throw new OrderPricingFailedException(ex);
}
~~~

Hoặc khai báo `rollbackFor`. Hãy giữ exception type đủ ý nghĩa cho application layer và log root cause phù hợp.

### 9.4. Transaction đã rollback-only

Một inner component có thể đánh dấu transaction rollback-only. Outer method catch exception rồi tiếp tục; lúc commit Spring có thể ném `UnexpectedRollbackException`.

Đừng giả định catch exception có nghĩa transaction vẫn commit được. Nếu một operation làm transaction rollback-only, toàn bộ transaction hiện tại không thể trở lại trạng thái commit bình thường.

### 9.5. Database constraint violation thường xảy ra lúc flush/commit

Hibernate có thể trì hoãn SQL cho tới flush. Một `save()` thành công chưa có nghĩa database đã chấp nhận row. Constraint violation có thể xuất hiện khi:
- Gọi `flush()`.
- Query trigger auto-flush.
- Transaction commit.

Nếu cần bắt lỗi constraint trong một boundary cụ thể, hãy flush có chủ đích, nhưng sau persistence exception transaction có thể đã rollback-only. Không tiếp tục dùng persistence context bị lỗi như thể chưa có gì xảy ra.

## 10. Concurrency control: optimistic và pessimistic locking

### 10.1. Optimistic locking với @Version

Order entity:

~~~java
@Entity
public class Order {

    @Id
    private UUID id;

    @Version
    private long version;

    // ...
}
~~~

Khi update, Hibernate dùng version trong predicate tương đương:

~~~sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Nếu row count bằng 0, một transaction khác đã thay đổi version hoặc row không còn phù hợp; Hibernate ném optimistic locking exception theo provider integration.

Phù hợp khi:
- Xung đột hiếm.
- Muốn tránh giữ lock trong lúc user chỉnh form.
- Có thể yêu cầu client reload/retry khi version conflict.

### 10.2. Version trong HTTP command

Client có thể gửi version đã đọc:

~~~java
public record AmendOrderCommand(
    UUID orderId,
    long expectedVersion,
    List<OrderLineRequest> lines
) {}
~~~

Service kiểm tra version/state trước mutation. `@Version` ở entity vẫn là lớp bảo vệ cuối cùng khi hai transactions cùng load một version. Có thể expose version qua ETag/If-Match để HTTP API hỗ trợ optimistic concurrency.

### 10.3. Pessimistic locking

Spring Data JPA có thể khai báo lock:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findByIdForUpdate(UUID id);
}
~~~

Lock row giúp serialize các mutations cạnh tranh trên cùng order, ví dụ amend và cancel. Lock được giữ đến transaction completion theo database/provider semantics.

Dùng khi:
- Conflict thường xuyên.
- Mutation cần đọc-modify-write tuần tự.
- Business cần quyết định dựa trên state mới nhất.
- Critical section ngắn.

Không giữ pessimistic lock trong lúc gọi remote service hoặc chờ user.

### 10.4. Lock inventory theo thứ tự ổn định

Nếu một order cần nhiều SKU, lock/update inventory rows theo thứ tự SKU/warehouse cố định. Điều này giảm deadlocks do thứ tự lock khác nhau.

Vẫn phải xử lý deadlock/serialization failure có thể xảy ra do các transactions khác hoặc execution plans. Retry transaction có giới hạn và chỉ khi use case idempotent.

### 10.5. Isolation level

Isolation ảnh hưởng cách transactions nhìn thấy writes của nhau:

- `READ_COMMITTED`: mỗi statement thường thấy dữ liệu đã commit trước statement đó, tùy DB.
- `REPEATABLE_READ`: transaction giữ snapshot/read stability theo database semantics.
- `SERIALIZABLE`: database cố thực thi như thể transactions chạy tuần tự; có thể abort một transaction khi phát hiện serialization conflict.

Không giả định cùng tên isolation có semantics giống nhau giữa mọi database. Ví dụ PostgreSQL và MySQL InnoDB có khác biệt về snapshot, locking reads và phantom handling.

Đừng nâng mọi order transaction lên SERIALIZABLE chỉ để tránh oversell. Conditional inventory update, unique constraints, versioning hoặc row locks thường là cách cụ thể hơn. Chọn isolation theo invariant và đo contention.

## 11. Idempotency và duplicate requests

### 11.1. Vì sao request có thể chạy nhiều lần?

- Client timeout sau khi server commit nhưng trước khi nhận response.
- API gateway retry.
- Mobile app gửi lại do mất mạng.
- User double-click.
- Message broker redelivery.
- Worker crash sau khi gọi provider nhưng trước khi ghi nhận kết quả.

HTTP POST không tự động exactly-once. Một transaction ACID không ngăn cùng một business command được gửi lại ở transaction khác.

### 11.2. Idempotency key cho create

Database unique constraint là cơ chế bảo vệ cuối cùng:

~~~sql
CREATE UNIQUE INDEX ux_order_customer_idempotency
ON orders (customer_id, idempotency_key);
~~~

Khi request cùng key được gửi lại:
- Nếu order đã commit, trả order hiện tại.
- Nếu request đầu đang xử lý, request thứ hai có thể chờ unique conflict rồi đọc kết quả.
- Nếu request đầu rollback, request thứ hai có thể trở thành request tạo thành công.

Cần lưu payload hash hoặc request fingerprint để cùng key nhưng body khác bị từ chối, tránh reuse key cho một ý định khác.

### 11.3. Idempotency cho cancel

Hủy đơn có thể được gọi nhiều lần:
- Nếu order đã cancelled theo cùng policy, trả kết quả đã có.
- Không release reservation lần thứ hai.
- Không tạo refund request mới mỗi lần retry.
- Dùng unique business key cho refund request, ví dụ order/payment/refund operation ID.

### 11.4. Idempotency cho consumer

Outbox/message consumer nên ghi `event_id` hoặc inbox record có unique constraint. Khi nhận lại event:
- Nếu đã xử lý, không lặp side effect.
- Nếu chưa xử lý, cập nhật business state và inbox marker trong cùng local transaction.
- Nếu provider call có thể retry, dùng provider idempotency key/correlation ID.

Không dựa vào broker delivery mode để tuyên bố nghiệp vụ exactly-once.

## 12. Outbox pattern: commit state và event cùng nhau

### 12.1. Dual-write problem

Nếu code làm:

~~~java
@Transactional
public void placeOrder(...) {
    orderRepository.save(order);
    messageBroker.publish(new OrderPlaced(order.getId()));
}
~~~

Có hai failure windows:
1. DB commit thành công, publish message thất bại → order tồn tại nhưng worker không biết.
2. Publish thành công, DB commit thất bại → worker nhận event cho order không tồn tại.

Đây là dual-write problem giữa hai systems.

### 12.2. Ghi outbox trong cùng transaction

Bảng outbox:

~~~text
outbox_event
  event_id
  aggregate_type
  aggregate_id
  event_type
  payload
  occurred_at
  published_at
  attempts
  status
~~~

Trong transaction tạo order:

~~~java
orders.save(order);
outbox.save(OutboxEvent.orderPlaced(order));
~~~

Cả order và outbox record commit hoặc rollback cùng nhau vì cùng database transaction.

### 12.3. Worker publish sau commit

Worker:
1. Claim một nhóm unpublished events.
2. Publish tới broker/provider.
3. Đánh dấu published sau khi publish thành công.
4. Retry nếu lỗi.
5. Có cơ chế tránh nhiều workers claim cùng event, ví dụ lease/row locking hoặc SKIP LOCKED tùy DB.

Nếu publish thành công nhưng worker crash trước khi đánh dấu published, event có thể được publish lại. Consumer phải idempotent.

### 12.4. Không giữ transaction DB mở trong lúc publish lâu

Có thể claim event trong transaction ngắn rồi commit lease, publish bên ngoài transaction, sau đó cập nhật kết quả bằng transaction mới. Điều này giảm thời gian lock và connection usage.

Cần lease expiry/visibility timeout để event được xử lý lại nếu worker chết sau khi claim.

## 13. Payment, shipping và saga

### 13.1. Vì sao không gọi payment gateway trong @Transactional?

Ví dụ:

~~~java
@Transactional
public void placeOrder(...) {
    inventory.reserve(...);
    orders.save(order);
    paymentGateway.authorize(...); // network call
}
~~~

Nếu provider mất 8 giây:
- DB transaction giữ connection/locks trong 8 giây.
- Pool có thể cạn khi tải tăng.
- Provider timeout nhưng kết quả authorize có thể không rõ.
- DB rollback không thể undo payment authorization đã thành công.
- Retry request có thể authorize hai lần nếu provider không nhận idempotency key.

Tách payment ra workflow sau commit. Database transaction ghi PENDING_PAYMENT và outbox event; worker gọi provider bằng idempotency key. Callback/result cập nhật trạng thái bằng transaction riêng.

### 13.2. Saga cho workflow nhiều hệ thống

Saga là chuỗi local transactions, mỗi bước commit tại hệ thống sở hữu dữ liệu. Khi bước sau thất bại, workflow thực hiện compensating action phù hợp thay vì rollback xuyên mọi systems.

Ví dụ:
1. Tạo order ở trạng thái PENDING_PAYMENT, reserve stock, ghi outbox.
2. Payment service authorize.
3. Nếu authorize thành công, cập nhật payment và order sang CONFIRMED.
4. Fulfillment service nhận lệnh xử lý.
5. Nếu authorize thất bại, cancellation workflow release reservation.
6. Nếu fulfillment thất bại sau capture, workflow có thể yêu cầu refund.

Sơ đồ:

~~~text
Create order + reserve stock
          |
          v
Request payment authorization
       /       \
   success      failure
     |             |
     v             v
Confirm order   Cancel order
     |             |
     v             v
Start fulfillment  Release reservation
~~~

### 13.3. Compensation không phải rollback

Ví dụ payment capture đã thành công. Không thể rollback provider ledger bằng JDBC rollback. Có thể tạo refund transaction mới. Refund là business operation riêng, có thể fail, pending hoặc cần retry.

Compensation cần:
- Correlation với operation gốc.
- Idempotency key riêng.
- State machine.
- Retry/backoff.
- Manual intervention khi không thể tự hoàn tất.
- Audit trail.

### 13.4. Chọn orchestration hay choreography

- **Orchestration:** một workflow coordinator theo dõi trạng thái và gọi các bước tiếp theo. Dễ nhìn toàn bộ order process, nhưng coordinator cần bền vững và không chứa business state chỉ trong memory.
- **Choreography:** các services phát/nhận events và tự phản ứng. Giảm central coordinator nhưng flow có thể khó quan sát và dễ tạo vòng event.

Với order/payment/inventory phức tạp, orchestration thường giúp vận hành và support dễ hơn. Dù chọn cách nào, mỗi service vẫn có local transaction boundary và idempotent handlers.

## 14. Transactional events và after-commit behavior

### 14.1. Spring @TransactionalEventListener

Spring có thể đăng ký listener theo transaction phase:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        // Trigger notification after commit.
    }
}
~~~

Listener chỉ được xử lý ở phase tương ứng khi có transaction. Nếu cần behavior khi không có transaction, xem fallbackExecution và quyết định rõ.

### 14.2. AFTER_COMMIT không thay thế outbox

Nếu process chết sau DB commit nhưng trước khi listener gửi email/publish event, event có thể mất. @TransactionalEventListener(AFTER_COMMIT) hữu ích cho local in-process behavior, nhưng không bảo đảm durable delivery qua process crash.

Nếu event phải được giao bền vững, ghi outbox record trong transaction và xử lý bằng worker.

### 14.3. AFTER_ROLLBACK và AFTER_COMPLETION

Các phases khác có thể phục vụ cleanup/telemetry:
- AFTER_ROLLBACK: phản ứng sau rollback.
- AFTER_COMPLETION: chạy sau khi transaction hoàn tất dù commit hay rollback.

Không thực hiện business side effects không thể đảo ngược trong callback chỉ vì nó chạy ở một phase. Xử lý exception ở after-commit cũng không thể rollback transaction đã commit.

## 15. Audit trail và lịch sử trạng thái

### 15.1. Audit record nên cùng transaction với business mutation

Khi sửa/hủy order, nếu audit là requirement, ghi audit row cùng transaction:

~~~java
order.cancel(actorId, reason);
auditRepository.save(
    OrderAuditEntry.cancelled(order.getId(), actorId, reason)
);
~~~

Nếu order update commit nhưng audit write fail, hệ thống mất lịch sử cần thiết. Cùng transaction giúp cả hai cùng thành công/thất bại.

### 15.2. Lưu actor, reason và before/after phù hợp

Audit event có thể chứa:
- Order ID.
- Actor/user/service identity.
- Operation.
- Reason.
- Timestamp.
- Previous/new status.
- Version.
- Correlation/request ID.
- Những fields cần thiết để tái dựng quyết định.

Không lưu thông tin nhạy cảm không cần thiết trong payload/log. Xác định retention, access control và redaction policy.

### 15.3. Audit table khác log ứng dụng

Log phục vụ chẩn đoán có thể bị rotate, sampling hoặc thiếu transactional guarantee. Audit record nghiệp vụ cần schema/retention/access policy và được commit cùng business state nếu yêu cầu tính toàn vẹn.

## 16. Những lỗi thường gặp khi đặt transaction boundary

### 16.1. Transaction quá nhỏ

Mỗi repository save commit riêng:
- Order được lưu.
- Reservation fail.
- Order vẫn tồn tại ở trạng thái không hợp lệ.

Giải pháp: transaction bao quanh use case và các local writes cần nguyên tử.

### 16.2. Transaction quá lớn

Một method bao quanh:
- Query catalog.
- Wait for payment.
- Upload document.
- Send email.
- Call shipping API.
- Update database.

Giải pháp: giữ transaction ngắn, ghi workflow/outbox state rồi xử lý external work ngoài transaction.

### 16.3. REQUIRES_NEW cho một phần business core

Reservation commit riêng nhưng order transaction rollback. Giải pháp: để core database mutations tham gia cùng transaction hoặc chuyển sang saga nếu ownership khác database.

### 16.4. Catch exception và tiếp tục commit

Một bước inventory fail nhưng service catch rồi vẫn save order. Giải pháp: không tiếp tục khi invariant không còn đúng; ném exception/rollback hoặc trả validation result trước mọi writes.

### 16.5. Dựa vào save() để chắc chắn DB đã ghi

Hibernate có thể defer SQL đến flush/commit. Constraint violation có thể xuất hiện muộn. Giải pháp: hiểu flush timing, flush có chủ đích khi cần, và không dùng persistence context sau persistence exception như trạng thái bình thường.

### 16.6. Dùng readOnly=true cho method có writes

Read-only là hint và behavior tùy platform. Nếu use case cần thay đổi order/reservation, dùng transaction write rõ ràng; không dựa vào việc provider tình cờ vẫn flush.

### 16.7. Để controller mở transaction

Controller có thể serialize response hoặc thực hiện các bước chậm sau service call. Giải pháp: application service sở hữu transaction và trả DTO/ID sau khi transaction hoàn tất.

### 16.8. Gọi method @Transactional qua self-invocation

Lời gọi nội bộ có thể bỏ qua proxy. Giải pháp: đặt boundary ở method entry qua Spring bean hoặc dùng TransactionTemplate.

### 16.9. Không xử lý concurrent amend và cancel

Hai requests cùng load order CONFIRMED, một amend lines và một cancel. Không có lock/version, cả hai có thể commit state mâu thuẫn hoặc một request ghi đè request kia.

Giải pháp: state transition có điều kiện, optimistic version hoặc pessimistic lock; test hai requests cạnh tranh.

### 16.10. Release inventory nhiều lần

Cancellation retry cộng available stock lần thứ hai. Giải pháp: reservation state transition có điều kiện và cộng stock chỉ khi transition ACTIVE -> RELEASED thành công trong cùng transaction.

## 17. Ví dụ thiết kế service theo ba use cases

### 17.1. Application service

~~~java
@Service
@RequiredArgsConstructor
public class OrderApplicationService {

    private final OrderRepository orders;
    private final InventoryService inventory;
    private final PricingService pricing;
    private final OutboxRepository outbox;
    private final OrderAuditRepository audit;

    @Transactional
    public OrderId create(PlaceOrderCommand command) {
        // Validate command, idempotency, customer and address.
        // Price items.
        // Reserve stock.
        // Persist order + lines.
        // Persist audit/outbox.
        return null;
    }

    @Transactional
    public void amend(AmendOrderCommand command) {
        // Load order with lock/version.
        // Verify editable state.
        // Compute inventory deltas.
        // Reprice and replace lines/totals.
        // Persist audit/outbox.
    }

    @Transactional
    public void cancel(CancelOrderCommand command) {
        // Load order with lock/version.
        // Verify cancellation policy.
        // Release active reservations once.
        // Transition order and write audit/outbox.
    }
}
~~~

Các method là entry points cho application use cases. Helper methods trong cùng class không tự tạo transaction mới; chúng chạy trong transaction đã được proxy mở cho public method.

### 17.2. Domain methods giữ state transitions

Thay vì service tự gán status ở nhiều nơi:

~~~java
public void confirm() {
    if (status != OrderStatus.PENDING_PAYMENT) {
        throw new InvalidOrderTransitionException(status);
    }
    status = OrderStatus.CONFIRMED;
}

public void requestCancellation(
        String reason,
        UUID actorId) {

    if (!status.canBeCancelled()) {
        throw new OrderCannotBeCancelledException(status);
    }

    status = OrderStatus.CANCEL_PENDING;
    this.cancellationReason = reason;
    this.cancelledBy = actorId;
}
~~~

Domain method bảo vệ state machine. Transaction đảm bảo các state changes liên quan được lưu nguyên tử; nó không thay thế validation domain.

### 17.3. Repository lock method

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findForUpdate(@Param("id") UUID id);
}
~~~

Nếu dùng optimistic locking thay vì pessimistic, load entity bình thường và dựa vào @Version; map conflict thành response phù hợp, ví dụ HTTP 409.

### 17.4. Không trả managed entity ra ngoài transaction

Sau khi service commit, trả:
- Order ID.
- DTO snapshot.
- Read model query riêng.

Không trả entity managed để controller tiếp tục truy cập lazy collections sau khi transaction kết thúc. Điều đó có thể gây LazyInitializationException hoặc vô tình phát thêm queries ngoài transaction boundary.

## 18. Kiểm thử transaction boundaries

### 18.1. Test rollback khi inventory không đủ

Scenario:
1. Inventory có 1 unit.
2. Command yêu cầu 2 units.
3. Create order thất bại.
4. Assert không có order.
5. Assert inventory không thay đổi.
6. Assert không có outbox event.

Test nên chạy với database thật khi cần xác nhận atomic updates/locking/dialect. Nếu chỉ test domain validation, unit test có thể đủ.

### 18.2. Test commit đầy đủ

Khi create thành công, assert trong transaction/context mới:
- Order tồn tại.
- Lines đúng.
- Totals đúng.
- Reservation đúng.
- Outbox record tồn tại.
- Audit record tồn tại.

Đừng chỉ assert object state trước flush vì entity có thể mới chỉ nằm trong persistence context.

### 18.3. Test rollback sau một bước đã mutate

Đặt test fail sau khi reservation thành công nhưng trước khi order hoàn tất. Khi transaction rollback:
- Reservation phải trở lại trạng thái ban đầu.
- Available/reserved quantity phải đúng.
- Order/lines không tồn tại.
- Outbox/audit không tồn tại.

Đây là bằng chứng trực tiếp cho boundary.

### 18.4. Test amend concurrent với cancel

Dùng hai threads/transactions:
- T1 bắt đầu amend và load order version V.
- T2 bắt đầu cancel cùng order.
- Đồng bộ thời điểm cạnh tranh.
- Commit một operation.
- Operation còn lại phải bị serialize hoặc fail version/state check.
- Final state phải hợp lệ, không có inventory delta sai.

Mỗi thread cần transaction và persistence context riêng; không chia sẻ EntityManager.

### 18.5. Test idempotency

Gửi cùng create command/key hai lần, kể cả đồng thời:
- Chỉ có một order.
- Chỉ reserve stock một lần.
- Cả hai callers nhận cùng order identity hoặc kết quả nhất quán.
- Chỉ có một logical event/payment authorization request.

Lặp cancel:
- Reservation chỉ release một lần.
- Refund request không duplicate.
- Status không chuyển lùi.

### 18.6. Test outbox crash window

Giả lập:
- Order/outbox commit thành công.
- Worker publish thành công.
- Worker crash trước khi đánh dấu published.
- Worker retry và publish lại.
- Consumer idempotency bảo đảm chỉ một business effect.

Test này chứng minh hệ thống chịu được at-least-once delivery.

### 18.7. Cẩn thận với @Transactional trên test method

Spring test transaction thường rollback sau mỗi test method. Điều này tiện cho fixture, nhưng có thể che:
- Commit-time constraints.
- After-commit listeners.
- Worker thread visibility.
- Independent transaction behavior.

Concurrency/outbox tests thường cần transaction boundaries rõ và có thể không annotate test method @Transactional. Commit fixture trước khi worker/connection khác đọc.

## 19. Transaction boundary khi các service dùng database riêng

Nếu Order Service, Inventory Service và Payment Service sở hữu database riêng:
- JPA transaction của Order Service chỉ commit dữ liệu Order DB.
- Inventory reservation là local transaction của Inventory Service.
- Payment authorization là local operation của Payment Service/provider.
- Không có một @Transactional duy nhất làm tất cả rollback nguyên tử.

Dùng saga:
1. Order tạo PENDING và phát ReserveInventory.
2. Inventory tạo reservation hoặc trả InsufficientStock.
3. Nếu reserve thành công, Order workflow yêu cầu authorize payment.
4. Nếu payment fail, workflow yêu cầu release reservation và cancel order.
5. Nếu payment success, order được confirm.
6. Mỗi message có event ID/idempotency key; mỗi participant ghi inbox/outbox theo local transaction.

Cần state machine cho saga, timeout, retry, compensation và manual repair. Không dùng XA/distributed transaction một cách mặc định; chỉ cân nhắc khi toàn bộ resources/operational environment hỗ trợ và trade-off phù hợp.

## 20. Troubleshooting transaction trong order workflows

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Order tồn tại nhưng inventory chưa reserve | Repository transactions commit riêng hoặc reservation ở service khác fail | Xác định transaction manager/database ownership; kiểm tra atomic boundary |
| Stock bị trừ nhưng order không tồn tại | Reservation dùng REQUIRES_NEW hoặc database khác | Kiểm tra propagation; dùng cùng transaction hoặc saga compensation |
| Hai orders oversell cùng SKU | Read-check-write không atomic | Conditional UPDATE, lock/version, DB constraint |
| Hai orders cùng idempotency key | Chỉ SELECT trước INSERT, thiếu unique constraint | Unique key + xử lý conflict/read existing result |
| Amend ghi đè thay đổi khác | Lost update, thiếu @Version/lock | Optimistic/pessimistic locking và HTTP version |
| Cancel và amend cùng thành công không hợp lệ | State transition không được serialize | Conditional state update, lock/version, invariant tests |
| Reservation được cộng lại hai lần | Cancel/retry không idempotent | Reservation state transition conditional trong transaction |
| Transaction không rollback khi checked exception | Default rollback rules | rollbackFor hoặc wrap thành runtime domain exception |
| Exception bị catch nhưng dữ liệu vẫn commit | Method kết thúc bình thường và transaction chưa rollback-only | Rethrow/mark rollback-only; không nuốt business failure |
| UnexpectedRollbackException | Inner operation đánh dấu rollback-only, outer catch rồi tiếp tục | Tìm rollback-only marker và propagation path |
| @Transactional không có hiệu lực | Self-invocation hoặc method không qua proxy | Kiểm tra bean boundary/proxy mode |
| LazyInitializationException ở controller | Entity trả ra ngoài transaction và lazy relation truy cập sau | Map DTO trong service/read transaction |
| Constraint violation xuất hiện ở commit | SQL bị defer tới flush/commit | Flush có chủ đích, xử lý transaction đã rollback-only |
| Connection pool cạn khi payment chậm | Network call nằm trong DB transaction | Outbox/worker, transaction ngắn |
| Payment thành công nhưng order vẫn pending | Provider response/callback bị mất hoặc update fail | Reconcile provider, idempotent callback, durable workflow |
| Order đã cancel nhưng refund pending | External refund là async | Model payment/refund state riêng, retry và operations dashboard |
| Event mất sau DB commit | Publish message trực tiếp trước/sau commit không durable | Transactional outbox |
| Event được publish hai lần | Worker crash sau publish trước mark-published | Consumer inbox/idempotency |
| Deadlock khi sửa nhiều SKU | Lock order khác nhau | Sort keys, giữ transaction ngắn, bounded retry |
| Test rollback không kiểm tra after-commit | Test transaction bị rollback | Test commit thật và worker/connection riêng |
| Bulk JPQL update làm entity stale | Bulk update bypass persistence context synchronization | Clear/refresh hoặc tránh giữ entity managed |
| Hủy đơn shipped làm tăng tồn kho | Release reservation sai lifecycle | Return/inspection/restock workflow riêng |
| Tổng tiền lệch với lines | Nhận total từ client hoặc tính rounding không thống nhất | Server-side pricing snapshot và currency policy |

## 21. Bài tập thực hành

### Bài 1 — Chọn transaction boundary

Tạo order cần insert order, order lines và reserve stock trong cùng database.

**Hỏi:** Nên đặt transaction ở đâu?

**Đáp án:** Ở application service method cho use case create; repository calls tham gia cùng transaction.

### Bài 2 — Payment gateway

Payment authorize mất 10 giây và nằm trong method @Transactional.

**Hỏi:** Rủi ro?

**Đáp án:** Giữ DB connection/locks trong thời gian network call; rollback DB cũng không undo payment provider. Dùng outbox/workflow sau commit.

### Bài 3 — Stock race

Hai requests cùng đọc available quantity = 1 và mỗi request cần 1.

**Hỏi:** Read-check-write có đủ không?

**Đáp án:** Không. Dùng conditional UPDATE/lock/version và kiểm tra affected row count.

### Bài 4 — Reservation fail

Stock reserve thành công một SKU nhưng SKU thứ hai thiếu hàng.

**Hỏi:** Kết quả mong muốn nếu cùng DB transaction?

**Đáp án:** Toàn bộ reservation/order/outbox writes rollback; không để order một phần.

### Bài 5 — REQUIRES_NEW

Inventory reserve commit độc lập rồi order insert fail.

**Hỏi:** Vấn đề?

**Đáp án:** Stock bị giữ cho order không tồn tại. Core writes cùng DB nên tham gia transaction REQUIRED.

### Bài 6 — Duplicate POST

Client timeout và gửi lại create request.

**Hỏi:** Transaction ACID có ngăn tạo order thứ hai không?

**Đáp án:** Không. Cần idempotency key và unique constraint trong database.

### Bài 7 — Amend quantity

Order có SKU-A quantity 2, user đổi thành 5.

**Hỏi:** Inventory cần thay đổi bao nhiêu?

**Đáp án:** Reserve thêm delta 3, đồng thời cập nhật lines/totals trong transaction.

### Bài 8 — Reduce quantity

Order có SKU-A quantity 5, user đổi thành 2.

**Hỏi:** Có nên release toàn bộ 5 rồi reserve lại 2?

**Đáp án:** Thường không cần; release delta 3 để giảm contention và nguy cơ mất hàng.

### Bài 9 — Amend giá

Client gửi grandTotal=1.

**Hỏi:** Có dùng giá trị này không?

**Đáp án:** Không. Server tính lại từ authoritative pricing/tax/discount rules và lưu snapshot.

### Bài 10 — Order đã shipped

User gọi cancel.

**Hỏi:** Có release stock ngay không?

**Đáp án:** Không. Hàng đã rời kho; cần carrier cancellation hoặc return/inspection/restock workflow.

### Bài 11 — Cancel retry

Hai requests cancel cùng reservation chạy đồng thời.

**Hỏi:** Làm sao tránh cộng stock hai lần?

**Đáp án:** Conditional transition ACTIVE -> RELEASED; chỉ transaction thắng transition mới cộng available quantity.

### Bài 12 — Optimistic lock

Hai users cùng load order version 7 và sửa.

**Hỏi:** Ai commit?

**Đáp án:** Một transaction cập nhật version trước; transaction còn lại nhận optimistic lock conflict và phải reload/reconcile.

### Bài 13 — Pessimistic lock

Amend và cancel thường xuyên cạnh tranh cùng một order.

**Hỏi:** Có thể dùng gì?

**Đáp án:** PESSIMISTIC_WRITE trong transaction ngắn, sau khi đánh giá lock contention và timeout.

### Bài 14 — Checked exception

Pricing service ném checked PricingException sau một write.

**Hỏi:** Spring có mặc định rollback không?

**Đáp án:** Không nhất thiết. Dùng rollbackFor hoặc wrap thành runtime exception nếu business yêu cầu rollback.

### Bài 15 — Catch exception

Service catch InsufficientStockException rồi return failure.

**Hỏi:** Transaction có chắc rollback không?

**Đáp án:** Không. Nếu exception bị nuốt và transaction chưa rollback-only, các writes trước đó có thể commit.

### Bài 16 — Self-invocation

Một method trong bean gọi method @Transactional khác của chính bean.

**Hỏi:** Proxy transaction có chắc được kích hoạt?

**Đáp án:** Không trong proxy-based mode mặc định; lời gọi nội bộ không đi qua proxy.

### Bài 17 — Flush

repository.save(order) không ném lỗi.

**Hỏi:** Có chắc unique constraint đã được kiểm tra?

**Đáp án:** Không. SQL có thể chạy lúc flush/commit; constraint violation có thể xuất hiện muộn.

### Bài 18 — Outbox

Order commit thành công nhưng broker publish fail.

**Hỏi:** Làm sao tránh mất event?

**Đáp án:** Ghi outbox row cùng transaction order; worker retry publish sau commit.

### Bài 19 — Duplicate event

Worker publish event rồi crash trước khi đánh dấu published.

**Hỏi:** Có thể event đến consumer hai lần không?

**Đáp án:** Có. Consumer cần inbox/event ID hoặc idempotent business operation.

### Bài 20 — Refund

Payment capture đã thành công, cancel order sau đó.

**Hỏi:** JDBC rollback có hoàn tiền không?

**Đáp án:** Không. Cần refund operation riêng, idempotency, status và reconciliation.

### Bài 21 — Multi-database

Inventory nằm trong database khác order.

**Hỏi:** Một @Transactional local có atomic cả hai không?

**Đáp án:** Không. Dùng saga/reservation protocol hoặc distributed transaction nếu infrastructure/business thực sự chấp nhận.

### Bài 22 — Test transaction

Test method có @Transactional và rollback cuối test.

**Hỏi:** Có chứng minh worker thread nhìn thấy fixture đã commit không?

**Đáp án:** Không. Fixture có thể chưa commit; cần transaction boundary/commit rõ và connection khác.

### Bài 23 — Bulk JPQL

Service bulk-update inventory rồi đọc lại managed entity đã load trước đó.

**Hỏi:** Có thể đọc state cũ không?

**Đáp án:** Có. Bulk update không tự đồng bộ persistence context; refresh/clear hoặc thiết kế lại access.

### Bài 24 — Transaction quá dài

Một transaction giữ pessimistic lock trong khi upload file.

**Hỏi:** Cách sửa?

**Đáp án:** Upload/validate file ngoài transaction; transaction chỉ ghi state/reference cần thiết sau khi file đã sẵn sàng.

## 22. Checklist thiết kế transaction cho order

Trước khi triển khai một use case, xác định:

1. Use case bắt đầu và kết thúc ở application service method nào?
2. Business invariants nào phải được bảo vệ?
3. Những tables/aggregates nào cùng một database?
4. Writes nào phải commit/rollback cùng nhau?
5. Có external API/message/email nào cần chạy sau commit không?
6. Có outbox/inbox hoặc saga state cần lưu không?
7. Request có idempotency key không?
8. Concurrent create/amend/cancel được xử lý bằng conditional update, version hay lock nào?
9. Inventory delta có được tính từ old/new state đúng không?
10. Reservation có thể release/consume/expire đúng một lần không?
11. Order/payment/fulfillment status có state machines riêng không?
12. Money calculation dùng decimal/currency/rounding policy nào?
13. Rollback rules có bao phủ checked exceptions không?
14. Có self-invocation hoặc REQUIRES_NEW nguy hiểm không?
15. Transaction có giữ connection trong lúc network/file/user wait không?
16. Flush/commit failure được xử lý ở boundary nào?
17. Audit/outbox rows có cùng transaction với business mutation không?
18. Optimistic/pessimistic locking có timeout/retry policy không?
19. Tests có chứng minh rollback/commit/concurrency/idempotency không?
20. Khi workflow external thất bại, compensation/manual recovery ra sao?

## 23. Tổng kết

### 23.1. Ranh giới cho ba use cases

| Use case | Transaction database chính | Workflow ngoài transaction |
|---|---|---|
| Tạo đơn | Validate, reserve stock, create order/lines, calculate totals, audit/outbox | Payment authorization, notification, fulfillment |
| Sửa đơn | Lock/version check, adjust reservation deltas, replace lines/totals, audit/outbox | Payment adjustment, shipping update, downstream sync |
| Hủy đơn | State transition, release active reservations once, audit/refund request outbox | Refund, carrier cancellation, email, return/restock |

### 23.2. Năm nguyên tắc

1. **Đặt transaction theo use case và invariants.** Những writes cùng database phải thành công hoặc thất bại cùng nhau nằm trong một local transaction.
2. **Giữ transaction ngắn.** Không giữ JDBC connection/locks khi chờ payment, shipping, email hoặc người dùng.
3. **Bảo vệ concurrency ở database.** Dùng conditional updates, constraints, @Version hoặc pessimistic locks theo use case.
4. **Làm side effects có thể retry.** Outbox/inbox, idempotency keys và state machines xử lý duplicate delivery và process crashes.
5. **Tách trạng thái order, inventory và payment.** Cancel order không đồng nghĩa refund đã hoàn tất hoặc hàng đã quay lại kho.

### 23.3. Sơ đồ quyết định

~~~text
Một use case cần thay đổi dữ liệu?
              |
              v
Các writes cùng một database?
       /                    \
     Có                      Không
     |                        |
     v                        v
Có invariant cần atomic?   Local transactions
     |                    + saga/workflow
     v
Đặt @Transactional ở
application service
     |
     v
Có gọi hệ thống ngoài?
     /              \
   Không             Có
    |                 |
    v                 v
Commit DB       Ghi outbox/state
                trong transaction
                     |
                     v
                Worker gọi ngoài
                     |
                     v
             Retry/idempotency/
             compensation/reconcile
~~~

Câu hỏi thiết kế hữu ích nhất là:

> “Nếu process dừng ngay sau mỗi bước, dữ liệu nào đã commit, hệ thống nào đã nhận side effect, và retry tiếp theo có tạo ra kết quả trùng hoặc trạng thái không hợp lệ không?”

Khi trả lời được câu hỏi này cho create, amend và cancel, transaction boundary đã gắn với hành vi nghiệp vụ và failure modes thực tế.

## Tài liệu chính thức

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — @Transactional, proxy và transaction attributes.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html) — REQUIRED, REQUIRES_NEW và NESTED.
- [Spring Framework — Transaction Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — @TransactionalEventListener và transaction phases.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repository transactions, locking và query methods.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — persistence context, flush, optimistic/pessimistic locking.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — entity lifecycle, transactions, locking và persistence context contracts.
- [PostgreSQL Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — isolation semantics.
- [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row/table locks và deadlocks.
- [PostgreSQL UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — conditional update và affected rows.
- [AWS Prescriptive Guidance — Saga Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga.html) — local transactions và compensating actions.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html) — giải quyết dual-write giữa database và message broker.

> Các snippets là ví dụ thiết kế, cần điều chỉnh theo aggregate, database, transaction manager và Spring/Hibernate version của dự án. Một transaction ACID chỉ bao phủ resource do transaction manager quản lý; nó không rollback payment provider, broker hoặc service database khác. Test concurrency và lock behavior trên database engine thực tế trước khi dựa vào semantics cụ thể.
