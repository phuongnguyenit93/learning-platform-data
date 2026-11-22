# Phiên bản khóa lạc quan và chuyển lỗi lưu trữ thành kết quả phù hợp

Trong Domain-Driven Design (DDD), Aggregate Root bảo vệ các bất biến nghiệp vụ, còn Repository và tầng persistence chịu trách nhiệm lưu Aggregate một cách nhất quán. Khi nhiều request cùng đọc và cập nhật một Aggregate, chỉ kiểm tra quy tắc trong bộ nhớ là chưa đủ: hai request có thể cùng dựa trên một snapshot cũ rồi ghi đè thay đổi của nhau.

**Optimistic locking (khóa lạc quan)** phát hiện tình huống đó bằng một giá trị phiên bản (version). Khi ghi, hệ thống chỉ chấp nhận cập nhật nếu version trong cơ sở dữ liệu vẫn là version mà request đã đọc. Nếu có cập nhật cạnh tranh, thao tác thất bại và ứng dụng phải quyết định đọc lại, thử lại hoặc trả về kết quả xung đột. Lỗi từ ORM và database cần được chuyển thành kết quả phù hợp ở application boundary; không nên để người dùng hoặc consumer phụ thuộc vào exception, SQL hay tên bảng.

## 1. Vì sao cần kiểm soát cập nhật đồng thời?

Giả sử một Aggregate `Inventory` đang có 10 sản phẩm khả dụng. Hai request cùng đọc số lượng 10:

- Request A muốn giữ 7 sản phẩm.
- Request B muốn giữ 6 sản phẩm.

Cả hai đều kiểm tra thành công trên dữ liệu đã đọc. Nếu hệ thống ghi đè số lượng còn lại dựa trên snapshot cũ, có thể mất một cập nhật hoặc chấp nhận nhiều lượt giữ hàng hơn số lượng thực tế.

Đây là vấn đề **lost update** hoặc race condition. Transaction giúp nhóm thao tác thành một đơn vị commit/rollback, nhưng mức isolation và cách ghi quyết định các thao tác đọc-sửa-ghi cạnh tranh có an toàn hay không.

Optimistic locking phù hợp khi xung đột có thể xảy ra nhưng không thường xuyên đến mức phải khóa trước mọi lần đọc. Hệ thống cho phép nhiều request đọc cùng lúc và phát hiện xung đột ở thời điểm ghi.

## 2. Version hoạt động như thế nào?

Mỗi bản ghi hoặc Aggregate có một version. Khi được nạp, ứng dụng giữ version đã đọc. Khi lưu, ORM tạo câu lệnh cập nhật có điều kiện theo ID và version cũ, đồng thời tăng version mới.

Ví dụ, dữ liệu ban đầu:

| id | available_quantity | version |
| --- | ---: | ---: |
| `INV-01` | 10 | 4 |

Hai transaction cùng đọc version `4`. Transaction A cập nhật thành công, giảm tồn còn 3 và tăng version thành `5`. Transaction B vẫn đang giữ version `4`, nên câu lệnh cập nhật của nó không còn khớp bản ghi hiện hành và bị từ chối.

```mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as Transaction B
    participant DB as Database
    A->>DB: Read quantity=10, version=4
    B->>DB: Read quantity=10, version=4
    A->>A: reserve(7)
    B->>B: reserve(6)
    A->>DB: UPDATE ... WHERE version=4
    DB-->>A: 1 row updated, version=5
    B->>DB: UPDATE ... WHERE version=4
    DB-->>B: 0 rows updated
    Note over B: Optimistic lock conflict; transaction rolls back
```

Ý nghĩa của version là phát hiện dữ liệu đã thay đổi kể từ lúc đọc. Nó không tự quyết định request B nên được chấp nhận, thử lại hay báo xung đột; đó là quyết định của application layer dựa trên ngữ nghĩa command.

## 3. Sử dụng `@Version` trong JPA

JPA hỗ trợ optimistic locking bằng annotation `@Version`. Thuộc tính version có thể là kiểu số hoặc kiểu thời gian được provider hỗ trợ. Kiểu số thường dễ theo dõi và tránh phụ thuộc độ chính xác timestamp.

```java
@Entity
@Table(name = "inventory")
public class Inventory {
    @Id
    private UUID id;

    @Version
    private long version;

    @Column(nullable = false)
    private int availableQuantity;

    protected Inventory() {
        // Dành cho JPA.
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new InvalidQuantity(quantity);
        }
        if (availableQuantity < quantity) {
            throw new InsufficientInventory();
        }
        availableQuantity -= quantity;
    }

    public long version() {
        return version;
    }
}
```

Ở ví dụ này, `Inventory` vừa là Aggregate Root vừa là JPA entity để minh họa ngắn gọn. Một thiết kế tách domain model và persistence model vẫn dùng được cùng cơ chế: adapter lưu trữ quản lý version và chuyển xung đột ORM thành kết quả ở ranh giới repository/application.

Khi entity được quản lý trong persistence context, JPA provider theo dõi thay đổi và kiểm tra version khi cập nhật. Với entity detached hoặc thao tác merge, provider vẫn phải bảo vệ version theo quy tắc JPA; ứng dụng cần hiểu lifecycle entity và không tự gán version như một trường dữ liệu thông thường.

## 4. Câu lệnh cập nhật có điều kiện

Một câu lệnh SQL tương đương thường có dạng:

```sql
UPDATE inventory
SET available_quantity = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
```

Nếu không có transaction khác cập nhật version, một hàng được thay đổi. Nếu version đã tăng, không hàng nào khớp điều kiện. ORM nhận biết số hàng bị cập nhật không như mong đợi và ném lỗi optimistic locking.

Ứng dụng không nên tự viết lại version vào câu lệnh cập nhật thông thường hoặc bỏ điều kiện version để “cho qua” lỗi. Làm như vậy sẽ vô hiệu hóa cơ chế phát hiện lost update.

## 5. Xung đột có thể xuất hiện ở flush hoặc commit

Một điểm dễ bỏ sót là lệnh `save()` hoặc lời gọi phương thức repository không nhất thiết là thời điểm database thực hiện câu lệnh `UPDATE`.

Với JPA, thay đổi có thể được giữ trong persistence context và chỉ đồng bộ xuống database khi:

- Ứng dụng gọi `EntityManager.flush()`.
- Một truy vấn cần flush theo flush mode.
- Transaction commit và provider thực hiện flush tự động.

Vì vậy, một phương thức service có thể chạy hết phần thân mà chưa phát hiện xung đột. Lỗi chỉ xuất hiện khi transaction interceptor commit sau khi phương thức trả về.

```java
@Transactional
public void updateInventory(InventoryId id, int quantity) {
    Inventory inventory = repository.findById(id.value())
        .orElseThrow(() -> new InventoryNotFound(id));

    inventory.reserve(quantity);
    // Optimistic lock có thể chỉ được phát hiện lúc flush/commit.
}
```

Nếu bắt exception bên trong phương thức trên, có thể không bắt được lỗi xảy ra sau khi phương thức trả về. Cần đặt việc chuyển lỗi ở ranh giới bao quanh toàn bộ transaction, nơi commit đã hoàn tất hoặc thất bại.

## 6. Phân biệt xung đột version với lỗi nghiệp vụ

Hai loại lỗi có ý nghĩa khác nhau:

- **Lỗi nghiệp vụ:** tại trạng thái đã đọc, hành động không được phép. Ví dụ số lượng yêu cầu lớn hơn tồn kho, đơn đã hủy hoặc người dùng không đủ quyền.
- **Xung đột đồng thời:** hành động có vẻ hợp lệ trên snapshot đã đọc, nhưng một transaction khác đã thay đổi dữ liệu trước khi ghi.

Ví dụ, nếu `availableQuantity` là 2 và command yêu cầu giữ 5, `Inventory.reserve()` nên phát sinh kết quả nghiệp vụ `InsufficientInventory`. Nếu số lượng là 10 khi đọc nhưng transaction khác đã giảm xuống 2 trước khi lưu, optimistic locking phát hiện xung đột. Ứng dụng có thể nạp lại và đánh giá lại; lần đánh giá mới sẽ kết luận không đủ hàng.

Không nên biến mọi lỗi optimistic lock thành `InsufficientInventory`. Có thể nguyên nhân là một thuộc tính khác đã thay đổi hoặc request chỉ cần được thử lại. Hãy đọc lại trạng thái và áp dụng quy tắc miền để xác định kết quả.

## 7. Cập nhật cạnh tranh và dữ liệu cũ từ giao diện

Optimistic locking trong transaction bảo vệ khoảng thời gian từ lúc server nạp Aggregate đến lúc ghi. Nhưng một trường hợp khác xảy ra khi người dùng mở biểu mẫu, giữ dữ liệu trong vài phút rồi gửi lại sau khi người khác đã cập nhật.

Nếu handler chỉ nạp phiên bản mới nhất tại thời điểm nhận request rồi ghi toàn bộ giá trị cũ từ biểu mẫu, `@Version` có thể không phát hiện người dùng đang gửi dữ liệu dựa trên một snapshot cũ: server đã đọc version mới.

Với thao tác cập nhật dựa trên dữ liệu người dùng đã xem, command nên mang `expectedVersion` hoặc ETag đã đọc:

```java
public record ChangeShippingAddress(
    OrderId orderId,
    long expectedVersion,
    ShippingAddress newAddress
) {}
```

Application service so sánh version mong đợi với version hiện hành trước khi áp dụng thay đổi. Nếu không khớp, trả kết quả stale-data để người dùng tải lại hoặc hợp nhất thay đổi. Sau bước kiểm tra đó, `@Version` vẫn cần thiết để bảo vệ khoảng thời gian từ lần nạp hiện tại đến lúc ghi.

Hai lớp bảo vệ giải quyết hai khoảng thời gian khác nhau:

1. `expectedVersion` bảo vệ ý định dựa trên snapshot mà client đã xem.
2. JPA `@Version` bảo vệ cập nhật đồng thời giữa lúc server nạp và lưu Aggregate.

## 8. Optimistic locking với Aggregate có Entity con

Nếu một bất biến trải qua nhiều đối tượng bên trong Aggregate, tất cả thay đổi có thể ảnh hưởng đến bất biến đó phải được bao phủ bởi cơ chế concurrency phù hợp.

Ví dụ, `Order` là Aggregate Root và chứa nhiều `OrderLine`. Hai transaction có thể cùng sửa các dòng khác nhau nhưng cùng ảnh hưởng đến tổng tiền hoặc giới hạn số dòng. Nếu chỉ version hóa một bảng con hoặc chỉ kiểm tra version của root mà thao tác ghi không làm version root thay đổi, hệ thống có thể bỏ sót một số xung đột.

Với JPA, không nên giả định mọi thay đổi ở collection hoặc Entity con đều tự động tăng version của Root theo cách bạn mong muốn. Hành vi còn phụ thuộc mapping, ownership và provider. Hãy kiểm tra mapping thực tế và cân nhắc khóa tăng version của Root khi thao tác thay đổi một bất biến cấp Aggregate, ví dụ:

```java
entityManager.lock(orderEntity, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

`OPTIMISTIC_FORCE_INCREMENT` yêu cầu tăng version của entity được khóa. Có thể dùng cách này khi cần mọi thay đổi liên quan đến Aggregate đều cạnh tranh trên cùng một version token. Với các mô hình khác, có thể version hóa đúng các bản ghi tham gia hoặc chọn ranh giới Aggregate phù hợp hơn.

## 9. Khi nào nên thử lại?

Retry phù hợp với command có ngữ nghĩa cho phép đánh giá lại trên trạng thái mới. Ví dụ, “giữ 1 sản phẩm nếu còn hàng” có thể được thử lại sau khi đọc lại tồn kho.

Retry thường không phù hợp khi:

- Người dùng đang sửa một biểu mẫu dựa trên version cũ và cần xem lại dữ liệu mới.
- Quy tắc nghiệp vụ đã từ chối command.
- Lệnh có side effect không idempotent như thu tiền hoặc gửi email mà chưa có cơ chế bảo vệ.
- Xung đột liên tục cho thấy thiết kế đang có điểm nóng hoặc Aggregate quá tranh chấp.

Một chính sách retry an toàn nên có giới hạn số lần, khoảng chờ có jitter khi cần, và luôn chạy lại toàn bộ bước đọc cùng kiểm tra nghiệp vụ trong transaction mới. Không retry trên persistence context hoặc transaction đã rollback.

## 10. Ví dụ retry bằng `TransactionTemplate`

Với Spring, `TransactionTemplate.execute()` bao quanh cả phần thực thi và commit transaction. Khi optimistic locking xảy ra ở commit, exception được ném ra ngoài lời gọi `execute()`, nơi vòng retry có thể bắt được.

```java
public final class ReserveInventoryHandler {
    private static final int MAX_ATTEMPTS = 3;

    private final TransactionTemplate transactionTemplate;
    private final InventoryRepository repository;

    public ReserveInventoryHandler(
        TransactionTemplate transactionTemplate,
        InventoryRepository repository
    ) {
        this.transactionTemplate = transactionTemplate;
        this.repository = repository;
    }

    public ReservationResult handle(ReserveInventory command) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                return transactionTemplate.execute(status -> {
                    Inventory inventory = repository.findById(command.inventoryId())
                        .orElseThrow(() -> new InventoryNotFound(command.inventoryId()));

                    inventory.reserve(command.quantity());
                    return new ReservationResult.Accepted(command.inventoryId());
                });
            } catch (OptimisticLockingFailureException conflict) {
                if (attempt == MAX_ATTEMPTS) {
                    return new ReservationResult.Conflict();
                }
                pauseBeforeRetry(attempt);
            }
        }
        throw new IllegalStateException("Unreachable retry state");
    }
}
```

Đây là ví dụ theo Spring và giả định repository trả về entity đang được quản lý trong transaction. `pauseBeforeRetry()` là helper minh họa cho backoff có giới hạn; phần cài đặt phụ thuộc chính sách retry của ứng dụng. `TransactionTemplate.execute()` hoàn tất commit trước khi trả kết quả, nên exception concurrency ở flush/commit được bắt bên ngoài transaction. Mỗi vòng lặp tạo một transaction mới và nạp lại dữ liệu mới.

Không nên đặt vòng retry bên trong cùng một phương thức `@Transactional` rồi tiếp tục dùng entity đã bị lỗi. Sau optimistic lock exception, transaction hiện tại thường đã rollback hoặc bị đánh dấu rollback-only; persistence context không còn phù hợp để tiếp tục xử lý.

Ví dụ trên chỉ retry lỗi optimistic lock. Deadlock hoặc serialization failure có thể được retry trong một chính sách riêng nếu hệ quản trị và ngữ nghĩa command cho phép. Lỗi nghiệp vụ như `InsufficientInventory` không nên bị retry tự động.

## 11. Chuyển lỗi persistence thành kết quả ở application boundary

Domain model không nên phụ thuộc vào `OptimisticLockException`, `ConstraintViolationException` hoặc exception cụ thể của Hibernate. Những lỗi này thuộc persistence. Application layer cần chuyển chúng thành kết quả có ý nghĩa đối với caller.

Một hợp đồng kết quả có thể dùng sealed interface hoặc kiểu kết quả tương đương:

```java
public sealed interface ReservationResult {
    record Accepted(InventoryId inventoryId) implements ReservationResult {}
    record Rejected(String reason) implements ReservationResult {}
    record Conflict() implements ReservationResult {}
    record TemporarilyUnavailable() implements ReservationResult {}
}
```

Ví dụ ánh xạ:

| Lỗi hoặc tình huống | Ý nghĩa ở application | Kết quả phù hợp |
| --- | --- | --- |
| Không tìm thấy Aggregate | Đối tượng không tồn tại trong phạm vi yêu cầu | `NotFound` hoặc kết quả tương đương |
| Domain rule từ chối | Hành động không hợp lệ theo nghiệp vụ | `Rejected` với mã lý do ổn định |
| Optimistic lock conflict | Dữ liệu đã thay đổi kể từ snapshot | `Conflict` hoặc thử lại có giới hạn |
| Stale `expectedVersion` | Client đang sửa dữ liệu cũ | Yêu cầu tải lại/hợp nhất |
| Unique constraint đã biết | Một giá trị nghiệp vụ duy nhất đã được dùng | `AlreadyExists` hoặc `Conflict` |
| Database tạm thời không sẵn sàng | Không thể hoàn tất thao tác do hạ tầng | `TemporarilyUnavailable` |
| Kết quả commit không xác định | Client không biết thao tác đã được commit hay chưa | Tra cứu bằng idempotency key hoặc command ID |

Không nên chuyển mọi `DataIntegrityViolationException` thành `AlreadyExists`. Nó có thể là lỗi foreign key, check constraint, not-null hoặc unique constraint. Chỉ ánh xạ khi xác định được constraint và ngữ nghĩa nghiệp vụ tương ứng.

## 12. Đặt việc chuyển lỗi đúng ranh giới transaction

Do lỗi có thể phát sinh khi flush hoặc commit, nơi chuyển đổi lỗi cần bao quanh toàn bộ transaction. Có thể dùng:

- `TransactionTemplate` và `try/catch` bên ngoài `execute()`.
- Một application facade không có `@Transactional` gọi một bean khác có `@Transactional`, rồi bắt exception sau khi proxy kết thúc transaction.
- Một transaction manager hoặc adapter chuyên trách chuyển exception persistence sang kiểu lỗi ứng dụng.

Ví dụ tách bean:

```java
@Service
public class UpdateOrderTransaction {
    private final OrderRepository repository;

    public UpdateOrderTransaction(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void execute(ChangeOrder command) {
        Order order = repository.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFound(command.orderId()));
        order.apply(command);
    }
}

@Service
public class UpdateOrderHandler {
    private final UpdateOrderTransaction transaction;

    public UpdateOrderHandler(UpdateOrderTransaction transaction) {
        this.transaction = transaction;
    }

    public UpdateOrderResult handle(ChangeOrder command) {
        try {
            transaction.execute(command);
            return UpdateOrderResult.updated();
        } catch (OptimisticLockingFailureException conflict) {
            return UpdateOrderResult.conflict();
        }
    }
}
```

Hai class tách riêng để lời gọi đi qua transaction proxy của Spring. Nếu tự gọi `this.execute()` trong cùng bean, proxy có thể bị bỏ qua tùy cơ chế proxy-based transaction management. Trong thực tế, cần đặt transaction boundary rõ ràng và bảo đảm exception được bắt sau khi commit/rollback hoàn tất.

## 13. Ánh xạ kết quả ứng dụng sang HTTP/API

Application result không nên chứa mã HTTP hoặc chi tiết ORM. API adapter chuyển kết quả ứng dụng sang giao thức phù hợp.

Ví dụ thường gặp:

| Kết quả ứng dụng | HTTP có thể dùng | Caller nên làm gì |
| --- | ---: | --- |
| Updated | `200` hoặc `204` | Hiển thị thành công |
| Not found | `404` | Kiểm tra định danh hoặc điều hướng |
| Business rejection | `409` hoặc `422` tùy ngữ nghĩa API | Hiển thị lý do và yêu cầu hành động phù hợp |
| Concurrency conflict | `409` | Tải lại hoặc hợp nhất thay đổi |
| `If-Match` không còn đúng | `412` | Lấy representation mới rồi gửi lại có điều kiện |
| Temporary infrastructure failure | `503` | Thử lại sau theo chính sách client |

Nếu API dùng HTTP conditional request, ETag có thể đại diện version. Client gửi `If-Match` khi cập nhật; nếu representation đã thay đổi, server trả `412 Precondition Failed`. Nếu không dùng precondition header, `409 Conflict` thường là cách diễn đạt xung đột cập nhật ở cấp tài nguyên.

Đây là cách ánh xạ tham khảo, không phải quy tắc cố định cho mọi API. Hợp đồng API cần thống nhất mã lỗi, cấu trúc lỗi và khả năng retry.

## 14. Phân biệt lỗi tạm thời và kết quả commit không xác định

Không phải mọi lỗi kết nối đều có nghĩa transaction chưa commit. Ví dụ, database có thể đã commit nhưng kết nối bị ngắt trước khi client nhận được phản hồi. Khi đó, caller không biết thao tác thành công hay thất bại.

Với các command có hậu quả quan trọng, nên dùng `commandId` hoặc idempotency key duy nhất. Server lưu trạng thái xử lý của key trong cùng cơ chế nhất quán phù hợp. Khi client gửi lại cùng key, server có thể trả kết quả đã ghi nhận thay vì thực hiện side effect lần nữa.

Một luồng điển hình:

1. Client gửi command kèm idempotency key.
2. Application kiểm tra key đã được xử lý chưa.
3. Trong transaction, cập nhật Aggregate và lưu kết quả command/outbox phù hợp.
4. Nếu client timeout, nó gửi lại cùng key.
5. Server tra cứu kết quả đã lưu và trả lại mà không lặp thao tác.

Không nên retry một lệnh thu tiền, phát hành hóa đơn hoặc gửi thanh toán chỉ vì client nhận timeout. Trước tiên cần tra cứu kết quả theo key hoặc mã giao dịch. Với tích hợp bên ngoài, transactional outbox và cơ chế idempotency của consumer/provider giúp xử lý message lặp an toàn.

## 15. Version và Domain Event

Khi Aggregate thay đổi và phát sinh Domain Event, việc lưu trạng thái mới và event cần được phối hợp nhất quán. Nếu lưu Aggregate thành công nhưng publish event thất bại, consumer không biết thay đổi đã xảy ra. Nếu publish event trước rồi transaction rollback, consumer nhận một sự thật chưa được commit.

Transactional outbox thường giải quyết vấn đề này bằng cách lưu thay đổi Aggregate và bản ghi outbox trong cùng transaction. Một publisher riêng đọc outbox và gửi message. Event có thể được gửi nhiều lần, vì vậy consumer cần idempotency.

Version của Aggregate cũng hữu ích cho event ordering. Event có thể mang `aggregateId` và `aggregateVersion` để consumer nhận biết event trùng, cũ hoặc đến sai thứ tự. Timestamp một mình không đủ để bảo đảm thứ tự nhân quả trên nhiều máy.

Nếu một thay đổi chỉ nằm ở Entity con, cần bảo đảm version dùng để bảo vệ Aggregate và thứ tự event được tăng theo quy tắc nhất quán. Đừng giả định mọi ORM tự động tăng version Root cho mọi thay đổi collection; hãy kiểm tra mapping và provider.

## 16. Optimistic Locking không bảo vệ mọi loại bất biến

Version của một Aggregate chỉ phát hiện cập nhật cạnh tranh trên tài nguyên được version hóa. Nó không tự bảo vệ:

- Một bất biến trải qua nhiều Aggregate khác nhau.
- Hai bản ghi độc lập không cùng được cập nhật qua một version token.
- Một thao tác ghi đi vòng qua repository và bỏ qua cơ chế version.
- Các side effect bên ngoài database như gọi cổng thanh toán hoặc gửi email.
- Một client gửi dữ liệu cũ nhưng server chỉ nạp version mới và không so sánh `expectedVersion`.

Với bất biến vượt qua nhiều Aggregate, cần xem xét một Aggregate sở hữu quy tắc, một thao tác conditional update, reservation, lock phù hợp hoặc quy trình điều phối có bù trừ. Không nên chỉ thêm `@Version` vào một entity rồi giả định toàn bộ hệ thống đã an toàn.

## 17. Những lỗi thường gặp

**Cho rằng `@Transactional` tự ngăn lost update.** Transaction không tự bảo đảm chuỗi đọc-sửa-ghi an toàn. Cần version, lock, conditional update hoặc isolation phù hợp.

**Bắt lỗi trong thân phương thức trước khi commit.** Optimistic lock có thể chỉ xuất hiện khi transaction interceptor flush/commit. Hãy chuyển lỗi ở ranh giới bao quanh transaction.

**Retry trong transaction đã rollback.** Persistence context có thể không còn dùng được. Mỗi lần retry phải dùng transaction mới và nạp Aggregate mới.

**Retry mọi loại lỗi.** Lỗi nghiệp vụ không tự biến mất khi thử lại. Chỉ retry lỗi concurrency/tạm thời phù hợp với ngữ nghĩa command và có giới hạn.

**Không phân biệt stale client với conflict lúc ghi.** `@Version` không thay thế `expectedVersion` hoặc ETag khi thao tác dựa trên snapshot người dùng đã xem từ trước.

**Chuyển mọi database exception thành conflict.** Lỗi dữ liệu, timeout, lỗi kết nối và vi phạm constraint có ý nghĩa khác nhau. Cần phân loại theo nguyên nhân và constraint đã biết.

**Để ORM exception lọt vào domain model hoặc API.** Domain model nên dùng quy tắc và kết quả nghiệp vụ; adapter/application chuyển lỗi persistence thành hợp đồng ổn định.

**Bỏ qua thay đổi Entity con.** Cần xác nhận version token thực sự bao phủ mọi thay đổi liên quan đến bất biến Aggregate.

**Retry side effect không idempotent.** Timeout không chứng minh thao tác chưa xảy ra. Dùng idempotency key và cơ chế tra cứu kết quả.

## 18. Quy trình thiết kế và xử lý optimistic locking

1. **Xác định bất biến cần bảo vệ:** chọn Aggregate và dữ liệu có thể bị cập nhật cạnh tranh.
2. **Đặt version đúng nơi:** version hóa Root hoặc tài nguyên sở hữu bất biến; bảo đảm thay đổi Entity con liên quan cũng được bao phủ.
3. **Nạp và thay đổi qua Root:** kiểm tra quy tắc nghiệp vụ trước khi thay đổi trong bộ nhớ.
4. **Lưu trong transaction:** để ORM hoặc repository kiểm tra version khi flush/commit.
5. **Đặt exception boundary bên ngoài transaction:** bắt lỗi sau khi commit/rollback hoàn tất.
6. **Phân loại lỗi:** tách business rejection, optimistic conflict, stale client, constraint violation và infrastructure failure.
7. **Quyết định retry:** chỉ retry command phù hợp; mỗi lần dùng transaction mới, nạp lại và đánh giá lại.
8. **Bảo vệ lệnh lặp:** dùng idempotency key cho command và side effect có thể được gửi lại.
9. **Trả kết quả ổn định:** application result không chứa exception ORM; API adapter ánh xạ sang HTTP hoặc message contract.
10. **Kiểm thử cạnh tranh:** xác nhận một trong hai cập nhật xung đột thất bại, dữ liệu không mất và kết quả trả về có ý nghĩa.

## 19. Checklist rà soát

- Aggregate nào sở hữu bất biến đang được bảo vệ?
- Version có được kiểm tra trong câu lệnh ghi không?
- Mọi thay đổi liên quan đến bất biến có làm thay đổi version token phù hợp không?
- Có phân biệt stale client với xung đột trong transaction không?
- Lỗi flush/commit có được bắt ở đúng transaction boundary không?
- Retry có bắt đầu transaction mới và đọc lại dữ liệu không?
- Có giới hạn retry và phân biệt lỗi nghiệp vụ với lỗi tạm thời không?
- Database constraint có bảo vệ các điều kiện dữ liệu quan trọng ở tầng cuối không?
- Application result có ổn định và không để lộ SQL/ORM exception không?
- API có mã lỗi và hướng xử lý phù hợp cho conflict/precondition failure không?
- Command có side effect có idempotency key hoặc cơ chế tra cứu kết quả không?
- Domain Event và outbox có được lưu nhất quán cùng thay đổi Aggregate không?

## 20. Nguyên tắc cần ghi nhớ

Optimistic locking dùng version để phát hiện một Aggregate đã bị thay đổi kể từ lúc được đọc. JPA `@Version` thường thực hiện điều này bằng câu lệnh cập nhật có điều kiện; xung đột có thể chỉ xuất hiện ở flush hoặc commit. Với thao tác dựa trên dữ liệu người dùng đã xem, cần thêm `expectedVersion` hoặc ETag để phát hiện snapshot cũ trước khi áp dụng thay đổi.

Khi persistence phát sinh lỗi, hãy chuyển nó thành kết quả phù hợp ở application boundary: lỗi nghiệp vụ được giải thích theo quy tắc miền, xung đột đồng thời có thể được thử lại hoặc yêu cầu tải lại, lỗi hạ tầng được xử lý như tình trạng tạm thời, và kết quả commit không xác định cần idempotency/tra cứu. Retry phải dùng transaction mới và đánh giá lại trên dữ liệu mới. Cách thiết kế này bảo vệ tính nhất quán của Aggregate mà vẫn giữ hợp đồng ứng dụng rõ ràng, ổn định.
