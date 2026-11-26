# Strong consistency

Strong consistency bảo đảm các lần đọc quan sát được trạng thái dữ liệu đã commit theo một thứ tự nhất quán. Trong một ứng dụng Spring Modulith, điều này thường có nghĩa là mọi thay đổi cần cùng đúng tại một thời điểm được thực hiện trong cùng transaction cơ sở dữ liệu: hoặc tất cả cùng commit, hoặc tất cả cùng rollback.

Application events giúp các module giao tiếp qua hợp đồng sự kiện, nhưng bản thân việc phát event không tạo ra strong consistency. Kết quả phụ thuộc vào cách listener được gọi, transaction phase, transaction manager và nơi lưu dữ liệu. Listener bất đồng bộ sau commit phù hợp với eventual consistency; nếu nghiệp vụ yêu cầu strong consistency, các thay đổi liên quan phải tham gia cùng ranh giới transaction đồng bộ.

## 1. Strong consistency là gì?

Strong consistency yêu cầu một thao tác đọc sau khi transaction ghi đã commit phải quan sát được trạng thái mới nhất theo thứ tự commit được bảo đảm. Trong một transaction ACID, các thay đổi liên quan được nhìn như một đơn vị nguyên tử.

Ví dụ, khi xác nhận đơn hàng, nghiệp vụ có thể yêu cầu:

- đơn hàng chuyển sang `CONFIRMED`;
- khoản giữ tồn kho được tạo;
- hạn mức hoặc trạng thái thanh toán được cập nhật;
- một read model quan trọng được cập nhật để các truy vấn tiếp theo thấy trạng thái nhất quán.

Nếu các thay đổi này thuộc cùng một transaction database, người đọc sau commit sẽ thấy toàn bộ trạng thái mới. Nếu một bước thất bại trước commit, mọi thay đổi trong transaction được rollback.

| Thuộc tính | Ý nghĩa trong trường hợp này |
| --- | --- |
| Atomicity | Các thay đổi thuộc transaction cùng commit hoặc cùng rollback. |
| Consistency | Ràng buộc và invariant nghiệp vụ được giữ trước và sau commit. |
| Isolation | Transaction đồng thời không quan sát trạng thái trung gian theo isolation level đã chọn. |
| Durability | Sau khi commit thành công, dữ liệu được lưu bền vững theo bảo đảm của database. |

Strong consistency không có nghĩa mọi truy vấn trong mọi hệ thống đều tự động đọc cùng một snapshot toàn cục. Cần xác định rõ phạm vi: một database, một transaction, một aggregate hay nhiều dịch vụ phân tán. Mức isolation của database cũng ảnh hưởng đến những gì transaction đồng thời có thể quan sát.

## 2. Phân biệt strong consistency và eventual consistency

Với eventual consistency, module nguồn commit trước, rồi projection hoặc listener bất đồng bộ cập nhật sau. Trong khoảng thời gian giữa hai bước, read model có thể còn dữ liệu cũ. Với strong consistency trong cùng database, mọi thay đổi cần nhất quán được commit trong một transaction trước khi request trả thành công.

| Tiêu chí | Strong consistency | Eventual consistency |
| --- | --- | --- |
| Thời điểm cập nhật | Trong cùng transaction hoặc cơ chế đồng bộ có bảo đảm tương đương. | Sau commit, qua listener, queue hoặc worker. |
| Kết quả khi một bước thất bại | Transaction chung rollback toàn bộ thay đổi thuộc phạm vi đó. | Write model có thể đã commit trong khi projection còn chờ retry. |
| Độ trễ đọc sau ghi | Trạng thái mới có hiệu lực sau commit trong phạm vi consistency đã chọn. | Có khoảng trễ trước khi read model bắt kịp. |
| Coupling | Các bước cần đồng bộ và phụ thuộc khả dụng của nhau. | Các module tách rời hơn về thời gian chạy. |
| Khả năng mở rộng | Bị giới hạn bởi transaction, lock và tài nguyên chung. | Có thể scale consumer/projection độc lập, đổi lại cần xử lý lag và duplicate. |
| Tình huống phù hợp | Invariant cần đúng ngay khi thao tác hoàn tất. | Dashboard, tìm kiếm, báo cáo hoặc thông báo có thể trễ trong giới hạn. |

Không phải mọi dữ liệu đều cần strong consistency. Hãy áp dụng nó cho invariant thực sự cần được bảo vệ, ví dụ không cho phép xác nhận đơn nếu không giữ được tồn kho. Với dashboard hoặc báo cáo tổng hợp, eventual consistency thường đơn giản và có khả năng mở rộng tốt hơn.

## 3. Strong consistency trong ranh giới một transaction

Spring Modulith không thay thế transaction manager của Spring. Nếu các module dùng cùng database và cùng transaction manager, một use case có thể gọi API công khai của module khác trong cùng transaction. Những thao tác database tham gia transaction đó sẽ cùng commit hoặc rollback.

Ví dụ, module Order điều phối use case xác nhận đơn. Module Inventory công bố một API nghiệp vụ để giữ tồn kho:

```java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;
    private final InventoryManagement inventory;

    public ConfirmOrderService(
            OrderRepository orders,
            InventoryManagement inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        inventory.reserve(order.id(), order.lines());
        order.confirm();
        orders.save(order);
    }
}
```

```java
public interface InventoryManagement {
    void reserve(UUID orderId, List<OrderLine> lines);
}
```

```java
@Service
public class InventoryManagementImpl implements InventoryManagement {

    private final StockRepository stock;
    private final ReservationRepository reservations;

    public InventoryManagementImpl(
            StockRepository stock,
            ReservationRepository reservations) {
        this.stock = stock;
        this.reservations = reservations;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(UUID orderId, List<OrderLine> lines) {
        for (OrderLine line : lines) {
            StockItem item = stock.findForUpdate(line.productId())
                    .orElseThrow(() -> new ProductNotFoundException(line.productId()));

            item.reserve(line.quantity());
            stock.save(item);
        }

        reservations.save(Reservation.forOrder(orderId, lines));
    }
}
```

Với `Propagation.REQUIRED`, lời gọi từ `ConfirmOrderService` tham gia transaction hiện tại nếu transaction đó đang hoạt động. Nếu thiếu hàng và `reserve` ném exception, thay đổi tồn kho, reservation và trạng thái đơn hàng đều rollback, với điều kiện chúng dùng cùng transaction manager và cùng tài nguyên transaction.

Đây là lời gọi đồng bộ qua API công khai của module. Nó vẫn giữ ranh giới module: Order gọi một hợp đồng nghiệp vụ được Inventory công bố, không truy cập repository hoặc package nội bộ của Inventory.

## 4. Dùng application event đồng bộ khi cần invariant chung

Nếu muốn giao tiếp theo kiểu event mà vẫn giữ thay đổi trong cùng transaction, có thể dùng listener đồng bộ. Một `@EventListener` thông thường được gọi ngay trong luồng phát event. Nếu publisher phát event bên trong một phương thức `@Transactional`, các thao tác database của listener có thể tham gia transaction hiện tại khi dùng cùng transaction manager và propagation mặc định `REQUIRED`.

```java
public record OrderConfirmationRequested(
        UUID orderId,
        List<OrderLine> lines
) {}
```

```java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public ConfirmOrderService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        events.publishEvent(new OrderConfirmationRequested(
                order.id(),
                order.lines()
        ));

        order.confirm();
        orders.save(order);
    }
}
```

```java
@Component
public class ReserveInventoryOnOrderConfirmation {

    private final InventoryManagement inventory;

    public ReserveInventoryOnOrderConfirmation(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    @EventListener
    public void on(OrderConfirmationRequested event) {
        inventory.reserve(event.orderId(), event.lines());
    }
}
```

Trong ví dụ, listener đồng bộ chạy ngay trong lời gọi `publishEvent`. Nếu `inventory.reserve` thất bại và exception được truyền ra ngoài, transaction `confirm` có thể rollback. Hãy dùng event mang ý nghĩa phù hợp: `OrderConfirmationRequested` biểu diễn yêu cầu điều phối trong transaction; `OrderConfirmed` nên biểu diễn sự kiện chỉ được công bố sau khi đơn hàng đã thực sự xác nhận.

`@EventListener` không tự tạo transaction mới. Nó chạy trong thread gọi event. Các thao tác database của listener chỉ cùng transaction nếu có transaction đang hoạt động và propagation/resource phù hợp. Nếu listener bắt exception rồi nuốt lỗi, publisher có thể tiếp tục commit dù invariant chưa được đáp ứng.

## 5. Transaction-bound listener với BEFORE_COMMIT

Spring hỗ trợ `@TransactionalEventListener` để gắn listener với phase của transaction. Mặc định phase là `AFTER_COMMIT`, nhưng có thể chọn `BEFORE_COMMIT` nếu listener cần thực hiện thay đổi đồng bộ trước khi transaction commit.

```java
@Component
public class UpdateOrderReadModel {

    private final OrderSummaryRepository summaries;

    public UpdateOrderReadModel(OrderSummaryRepository summaries) {
        this.summaries = summaries;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void on(OrderConfirmationRequested event) {
        summaries.markConfirmed(event.orderId());
    }
}
```

Listener `BEFORE_COMMIT` được gọi khi transaction nguồn sắp commit. Nếu listener thực hiện database write trên cùng transaction manager và không chuyển sang transaction độc lập, thay đổi projection có thể được commit cùng transaction nguồn. Nếu listener ném exception, transaction có thể rollback.

Một số lưu ý quan trọng:

- `BEFORE_COMMIT` không đồng nghĩa với `AFTER_COMMIT`; không dùng nó để gửi email hoặc gọi dịch vụ ngoài như thể commit đã chắc chắn xảy ra.
- Không đặt `@Async` cho listener nếu invariant cần được kiểm tra đồng bộ trước commit.
- Không dùng `REQUIRES_NEW` cho thay đổi cần rollback cùng transaction nguồn.
- Listener chỉ được kích hoạt khi có transaction phù hợp, trừ khi bật `fallbackExecution`; hãy cân nhắc kỹ nếu event có thể được phát ngoài transaction.
- Nếu listener ghi vào database khác hoặc dùng transaction manager khác, không có atomicity chung mặc định.

`@ApplicationModuleListener` được thiết kế cho giao tiếp module bất đồng bộ sau commit với transaction listener riêng theo semantics Spring Modulith. Vì vậy, không thay `@ApplicationModuleListener` vào vị trí của listener đồng bộ khi yêu cầu là tất cả thay đổi phải commit cùng nhau.

## 6. Đưa read model vào cùng transaction khi thật sự cần

Một read model quan trọng có thể được cập nhật đồng bộ trước commit để truy vấn ngay sau commit thấy trạng thái mới. Điều này phù hợp khi projection nằm trong cùng database và có chi phí cập nhật nhỏ, ổn định.

```java
@Component
public class SynchronousOrderProjection {

    private final OrderSummaryRepository summaries;

    public SynchronousOrderProjection(OrderSummaryRepository summaries) {
        this.summaries = summaries;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void on(OrderConfirmed event) {
        summaries.upsert(
                event.orderId(),
                event.orderVersion(),
                event.status(),
                event.totalAmount()
        );
    }
}
```

Khi publisher và projection cùng tham gia một transaction, sau commit cả write model và read model cùng có trạng thái mới. Nếu projection update thất bại và exception làm transaction rollback, thay đổi nghiệp vụ nguồn cũng rollback.

Không nên biến mọi projection thành đồng bộ. Projection dashboard, tìm kiếm hoặc báo cáo thường có thể chấp nhận eventual consistency. Cập nhật đồng bộ làm tăng thời gian giữ transaction, tăng lock contention và khiến command phụ thuộc vào hiệu năng của mọi listener tham gia.

## 7. Điều kiện để strong consistency thực sự có hiệu lực

Việc dùng annotation `@Transactional` ở nhiều nơi chưa đủ để bảo đảm một transaction chung. Cần xác minh các điều kiện sau:

1. **Cùng transaction manager:** các repository tham gia đúng transaction manager được dùng bởi use case.
2. **Cùng transactional resource:** các thay đổi cần atomicity cùng tham gia một database transaction hoặc một cơ chế phân tán được cấu hình rõ.
3. **Propagation phù hợp:** listener/service dùng `REQUIRED` khi cần tham gia transaction hiện tại; tránh `REQUIRES_NEW` cho thay đổi cần rollback chung.
4. **Không tách luồng:** listener cần đồng bộ không chạy trên executor khác hoặc thread khác.
5. **Exception được truyền đúng:** lỗi vi phạm invariant phải làm transaction thất bại; không nuốt exception rồi commit.
6. **Rollback rule phù hợp:** kiểm tra loại exception và rollback rules của Spring transaction. Mặc định, runtime exception và error thường làm rollback; checked exception cần cấu hình nếu cũng phải rollback.
7. **Isolation phù hợp:** chọn isolation level và locking strategy để bảo vệ invariant trước các transaction cạnh tranh.

Ví dụ, `@Transactional(propagation = Propagation.REQUIRES_NEW)` trên listener sẽ tạo transaction độc lập. Nếu listener commit thành công rồi transaction nguồn rollback, thay đổi listener vẫn tồn tại. Đây không còn là atomicity chung.

Tương tự, gọi một REST API hoặc gửi message Kafka trong listener đồng bộ không khiến side effect từ xa rollback khi database transaction nguồn rollback. Lời gọi mạng có thể đã thành công ở hệ thống kia. Đối với side effect bên ngoài, dùng outbox, idempotency và quy trình bù trừ thay vì giả định transaction database có thể rollback nó.

## 8. Bảo vệ invariant khi có transaction đồng thời

Strong consistency còn phụ thuộc cách xử lý cạnh tranh. Hai transaction có thể cùng đọc một giá trị rồi cùng quyết định cập nhật, dẫn đến lost update hoặc vượt hạn mức nếu chỉ dựa vào kiểm tra trong Java.

Ví dụ, còn một sản phẩm trong kho và hai đơn hàng đồng thời yêu cầu giữ một sản phẩm. Nếu cả hai transaction cùng đọc `available = 1` trước khi cập nhật, cả hai có thể cùng nghĩ rằng còn hàng.

Có thể bảo vệ bằng pessimistic locking:

```java
public interface StockRepository extends JpaRepository<StockItem, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from StockItem s where s.productId = :productId")
    Optional<StockItem> findForUpdate(UUID productId);
}
```

Hoặc dùng optimistic locking với `@Version`:

```java
@Entity
public class StockItem {

    @Id
    private UUID productId;

    private int available;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (available < quantity) {
            throw new InsufficientStockException(productId);
        }

        available -= quantity;
    }
}
```

Khi hai transaction cùng sửa một version, transaction cập nhật sau có thể nhận optimistic locking failure và cần xử lý retry ở cấp use case. Pessimistic locking giảm xung đột bằng cách khóa hàng nhưng có thể làm tăng thời gian chờ và deadlock. Chọn chiến lược dựa trên mức cạnh tranh và invariant cần bảo vệ.

Với invariant có thể biểu diễn bằng constraint database, hãy dùng unique constraint, check constraint hoặc foreign key làm lớp bảo vệ cuối cùng. Kiểm tra ở application layer giúp trả thông báo nghiệp vụ rõ ràng; constraint database bảo vệ trước race condition và các đường ghi khác.

## 9. Strong consistency qua nhiều module và nhiều database

Spring Modulith giúp tổ chức module trong cùng ứng dụng, nhưng không tự tạo distributed transaction. Nếu các module dùng cùng database và cùng transaction manager, có thể duy trì atomicity qua API công khai hoặc listener đồng bộ. Nếu mỗi module có database riêng, một transaction Spring thông thường không thể commit nguyên tử trên tất cả database.

| Kiến trúc | Mức bảo đảm khả thi |
| --- | --- |
| Nhiều module, cùng database và transaction manager | Có thể dùng một ACID transaction cho các thay đổi liên quan. |
| Nhiều module, nhiều datasource nhưng cùng một distributed transaction manager được cấu hình | Có thể dùng 2PC/JTA nếu mọi resource và hệ thống hỗ trợ; cần chấp nhận chi phí vận hành và giới hạn khả dụng. |
| Nhiều service hoặc database độc lập, giao tiếp qua event/broker | Thường dùng eventual consistency, saga/process manager và compensation. |
| Database + HTTP API hoặc broker bên ngoài | Không có atomicity chung mặc định; dùng outbox, idempotency và retry/bù trừ. |

Two-phase commit (2PC) có thể phối hợp các resource hỗ trợ XA để commit hoặc rollback như một đơn vị phân tán. Tuy nhiên, 2PC tăng độ phức tạp, có thể giữ resource ở trạng thái prepared trong lúc coordinator gặp sự cố và làm giảm khả năng chịu lỗi. Chỉ dùng khi hạ tầng, database, driver và yêu cầu vận hành thực sự hỗ trợ.

Với hệ thống phân tán, thường tốt hơn khi xác định invariant nào phải được kiểm tra ngay trong một service sở hữu dữ liệu, còn quy trình nhiều bước được mô hình hóa bằng saga. Saga không tạo strong consistency toàn cục; nó cung cấp tiến trình có trạng thái, retry và compensation để hệ thống hội tụ về kết quả nghiệp vụ hợp lệ.

## 10. Vai trò của Event Publication Registry

Event Publication Registry theo dõi publication đến transactional listener của Spring Modulith và lưu trạng thái hoàn tất. Registry hữu ích để phát hiện publication chưa hoàn tất, hỗ trợ quan sát và phục hồi theo cấu hình persistence.

Registry không tự biến một listener bất đồng bộ thành strong consistency. Với `@ApplicationModuleListener`, listener được chạy sau commit trong transaction riêng; command nguồn có thể commit trước khi listener hoàn tất. Đó là eventual consistency dù publication được lưu bền vững và có thể retry.

Nếu cần một listener đồng bộ trong transaction nguồn, hãy chọn cơ chế listener và transaction phase phù hợp, sau đó xác minh publication tracking có bao phủ listener đó trong phiên bản Spring Modulith đang dùng. Không dựa vào bảng nội bộ của registry hoặc cập nhật SQL trực tiếp để ép publication hoàn tất.

Phân biệt rõ ba kết quả:

- **Command committed:** transaction nghiệp vụ nguồn đã commit.
- **Synchronous invariant satisfied:** các thay đổi đồng bộ cần thiết đã tham gia transaction và cùng commit.
- **Async publication completed:** listener bất đồng bộ đã hoàn tất sau commit.

Ba kết quả có thể xảy ra ở các thời điểm khác nhau. API nên phản ánh đúng mốc mà nó cam kết với người gọi.

## 11. Kiểm thử strong consistency

Kiểm thử cần xác nhận cả trạng thái commit và rollback, đặc biệt khi listener tham gia cùng transaction:

1. Khi tất cả module xử lý thành công, write model, reservation và read model cùng commit.
2. Khi listener đồng bộ ném exception, transaction nguồn rollback và không để lại thay đổi một phần.
3. Khi checked exception phải rollback, cấu hình rollback rule thực hiện đúng.
4. Khi listener vô tình dùng `REQUIRES_NEW`, kiểm thử phát hiện dữ liệu listener vẫn commit dù transaction nguồn rollback.
5. Khi hai transaction đồng thời giữ sản phẩm cuối cùng, chỉ một transaction thành công.
6. Unique/check constraint bảo vệ invariant khi có race condition.
7. Truy vấn sau commit thấy trạng thái nhất quán trong phạm vi database và isolation đã chọn.
8. Listener `@ApplicationModuleListener` được kiểm thử riêng với kỳ vọng eventual consistency, retry và publication incomplete.
9. Side effect ngoài database được kiểm thử với outbox/idempotency hoặc compensation phù hợp.

Kiểm thử tích hợp với database thật hoặc Testcontainers giúp xác minh transaction manager, locking, isolation, unique constraint và rollback. Mock repository đơn thuần không chứng minh các thao tác thực sự cùng transaction. Với Spring Modulith, `@ApplicationModuleTest` và Scenario API có thể hỗ trợ kiểm tra giao event; cần phân biệt test listener đồng bộ trong transaction với listener bất đồng bộ sau commit.

## 12. Quan sát và vận hành

Strong consistency không loại bỏ nhu cầu quan sát. Các chỉ số hữu ích gồm:

- transaction duration và tỷ lệ rollback;
- lock wait time, deadlock và optimistic locking failure;
- constraint violation theo use case;
- connection pool utilization và transaction timeout;
- publication incomplete và async listener lag cho các luồng eventual consistency;
- tỷ lệ retry và thời gian xử lý listener.

Log nên có correlation ID, aggregate ID, event ID và tên module/listener. Không ghi payload nhạy cảm hoặc toàn bộ dữ liệu nghiệp vụ nếu không cần. Khi điều tra, đối chiếu transaction ID, commit/rollback outcome và publication state để xác định lỗi xảy ra trong transaction nguồn hay ở chặng async sau commit.

Transaction đồng bộ quá dài có thể giữ lock lâu, giảm throughput và tạo deadlock. Tránh gọi dịch vụ mạng trong transaction cần strong consistency. Giữ transaction ngắn, truy cập tài nguyên theo thứ tự nhất quán và đặt timeout hợp lý.

## 13. Checklist lựa chọn strong consistency

- [ ] Đã xác định invariant nghiệp vụ nào bắt buộc đúng ngay khi command trả thành công.
- [ ] Các thay đổi cần atomicity dùng cùng transaction manager và transactional resource.
- [ ] Listener đồng bộ hoặc `BEFORE_COMMIT` được chọn đúng phase khi cần tham gia transaction nguồn.
- [ ] Không dùng `@ApplicationModuleListener` cho bước phải hoàn tất trước commit.
- [ ] Propagation, rollback rules và isolation level được cấu hình có chủ đích.
- [ ] Có locking hoặc constraint database để bảo vệ cạnh tranh cập nhật.
- [ ] Không giả định HTTP, Kafka hoặc database khác tự tham gia transaction hiện tại.
- [ ] Luồng phân tán được thiết kế bằng outbox, saga, idempotency và compensation khi phù hợp.
- [ ] Kiểm thử cả commit, rollback, race condition và publication bất đồng bộ.
- [ ] Transaction duration, lock wait, rollback và async lag được quan sát.

Strong consistency phù hợp với invariant cần được bảo vệ ngay khi một thao tác hoàn tất. Trong Spring Modulith, có thể đạt điều đó khi các module phối hợp qua API công khai hoặc event listener đồng bộ cùng tham gia một transaction database. `@ApplicationModuleListener` và Event Publication Registry hỗ trợ giao event bất đồng bộ đáng tin cậy, nhưng tạo ra eventual consistency giữa write model và projection. Chọn đúng ranh giới transaction cho từng yêu cầu giúp giữ dữ liệu nhất quán mà vẫn duy trì ranh giới module rõ ràng.
