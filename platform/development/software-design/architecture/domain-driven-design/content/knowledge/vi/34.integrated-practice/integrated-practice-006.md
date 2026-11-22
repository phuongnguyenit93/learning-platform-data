# Kiểm chứng cạnh tranh cập nhật và xung đột nghiệp vụ

Trong Domain-Driven Design, cạnh tranh cập nhật và xung đột nghiệp vụ xuất hiện khi nhiều tác nhân cùng tác động lên một mô hình trong khoảng thời gian gần nhau. Hai vấn đề có liên quan nhưng cần được nhận diện bằng hai ngôn ngữ khác nhau: **cạnh tranh cập nhật** là vấn đề đồng thời và tính toàn vẹn của lần ghi; **xung đột nghiệp vụ** là việc trạng thái mới không còn thỏa quy tắc nghiệp vụ tại thời điểm xử lý.

Bài thực hành này đặt hai vấn đề trong cùng một quy trình. Mục tiêu là xây dựng mô hình miền có ranh giới nhất quán rõ ràng, phát hiện thay đổi đồng thời ở điểm ghi, biểu diễn từ chối nghiệp vụ bằng ngôn ngữ miền và kiểm chứng bằng test có thể tái hiện. Trong module Domain-Driven Design, cách tiếp cận này nối tactical design với cách triển khai thực tế: Entity và Aggregate xác định trạng thái nào phải nhất quán cùng nhau; Repository kiểm soát việc lưu; Application Service điều phối use case; Domain Event công bố kết quả sau khi thay đổi hợp lệ.

## 1. Bắt đầu từ một tình huống có hai người cùng cập nhật

Giả sử có Aggregate `Order` với các trạng thái `DRAFT`, `CONFIRMED` và `CANCELLED`. Hai nhân viên cùng mở một đơn hàng đang ở phiên bản 7.

Người A xác nhận đơn hàng. Người B đồng thời hủy đơn hàng.

Nếu cả hai đọc phiên bản 7 rồi ghi toàn bộ bản ghi mà không có kiểm chứng cạnh tranh, lần ghi sau có thể vô tình ghi đè kết quả của lần ghi trước. Đây là **lost update**.

Nếu hệ thống có kiểm soát phiên bản, lần ghi đầu tiên chuyển phiên bản 7 thành 8. Lần ghi thứ hai vẫn gửi `expectedVersion=7`, nên hệ thống phát hiện dữ liệu đã thay đổi. Đây là **concurrency conflict**.

Nhưng sau khi phát hiện phiên bản mới, hệ thống còn phải hỏi một câu khác: thao tác của người B có còn hợp lệ theo nghiệp vụ không? Nếu đơn hàng đã được xác nhận, quy tắc có thể cấm hủy sau khi giao cho vận chuyển. Khi đó kết quả là **business conflict** hoặc **business rule violation**, chứ không chỉ là lỗi kỹ thuật về phiên bản.

| Tình huống | Câu hỏi cần trả lời | Loại vấn đề |
|---|---|---|
| Hai request cùng đọc version 7 | Lần ghi nào được phép thành công? | Cạnh tranh cập nhật |
| Request gửi version 7 nhưng DB đã ở version 8 | Dữ liệu có bị ghi đè không? | Concurrency conflict |
| Đơn hàng đã xác nhận nên không được hủy | Hành động còn hợp lệ theo miền không? | Xung đột nghiệp vụ |
| Hai người cùng dùng một mã giảm giá cuối cùng | Quy tắc số lượng còn lại được giữ thế nào? | Cạnh tranh + invariant |
| Hai request tạo cùng mã định danh duy nhất | Ai được tạo? | Constraint + cạnh tranh |
| Context khác đã thay đổi nhưng read model chưa kịp nhận event | Quyết định có thể dựa trên dữ liệu nào? | Nhất quán liên context |

Một hệ thống DDD tốt không cố biến tất cả các trường hợp thành một lỗi chung. Mỗi loại xung đột cần được biểu diễn ở lớp phù hợp để người gọi có thể xử lý đúng.

## 2. Phân biệt stale read, lost update và business conflict

Ba khái niệm thường bị trộn lẫn.

**Stale read** xảy ra khi một tác nhân đang cầm một biểu diễn cũ của Aggregate. Dữ liệu cũ tự nó chưa phải lỗi; nó chỉ trở thành vấn đề khi tác nhân dùng dữ liệu đó để đưa ra một thay đổi cần kiểm chứng.

**Lost update** xảy ra khi một lần ghi dựa trên trạng thái cũ ghi đè thay đổi đã được chấp nhận bởi tác nhân khác. Đây là lỗi toàn vẹn dữ liệu nếu hệ thống không kiểm soát cạnh tranh.

**Business conflict** xảy ra khi hành động có thể được thực hiện về mặt kỹ thuật nhưng không còn hợp lệ theo quy tắc miền.

Ví dụ:

- A và B cùng đọc `quantity=1`.
- A mua sản phẩm và ghi `quantity=0`.
- B cũng ghi `quantity=0`.

Nếu chỉ nhìn giá trị cuối cùng, hệ thống có thể không thấy dữ liệu bất thường. Nhưng hai lần bán đã cùng tiêu thụ một đơn vị tồn kho. Đây là lỗi về invariant, dù cột `quantity` vẫn có một giá trị hợp lệ.

Vì vậy, kiểm chứng cạnh tranh phải bảo vệ **sự chuyển đổi trạng thái**, không chỉ kiểm tra dữ liệu cuối cùng có trông hợp lệ hay không.

## 3. Aggregate là ranh giới nhất quán của quyết định

Aggregate là một trong những cơ chế quan trọng để giới hạn phạm vi mà một quyết định nghiệp vụ phải nhất quán ngay lập tức.

Ví dụ, nếu `Order` cần bảo đảm:

- chỉ đơn hàng ở `DRAFT` mới được xác nhận;
- tổng tiền phải khớp với các dòng hàng;
- một đơn hàng chỉ có một lần chuyển sang `CONFIRMED`;
- khi xác nhận phải phát ra `OrderConfirmed`;

thì các quy tắc này nên được kiểm tra trong Aggregate `Order`.

Một Aggregate nhỏ giúp mỗi lần ghi có phạm vi rõ ràng. Một Aggregate quá lớn làm tăng cạnh tranh vì nhiều thao tác không liên quan phải tranh cùng một version. Một Aggregate quá nhỏ lại đẩy invariant sang nhiều transaction hoặc nhiều context và khiến việc kiểm chứng khó hơn.

Có thể dùng câu hỏi sau khi xác định ranh giới:

1. Quy tắc nào phải đúng ngay sau một lần commit?
2. Những trạng thái nào phải được kiểm tra cùng nhau?
3. Ai là chủ sở hữu của quyết định?
4. Nếu hai command xảy ra đồng thời, Aggregate nào phải quyết định command thắng?
5. Phần nào có thể nhất quán cuối cùng qua Domain Event?

Ranh giới Aggregate nên xuất phát từ invariant và hành vi nghiệp vụ, sau đó mới chọn cơ chế khóa hoặc version phù hợp.

## 4. Optimistic concurrency control bằng version

Với nhiều hệ thống nghiệp vụ, optimistic concurrency control là lựa chọn thực tế khi cạnh tranh xảy ra nhưng không phải lúc nào cũng cao.

Mỗi Aggregate có một version. Khi client đọc Aggregate ở version 7, command giữ lại kỳ vọng rằng lần ghi đang thao tác trên version 7.

Quy trình cơ bản:

1. Đọc Aggregate và version hiện tại.
2. Xây dựng command từ ý định của người dùng.
3. Load Aggregate theo identity.
4. Kiểm tra command trong Aggregate.
5. Lưu Aggregate với điều kiện version vẫn bằng version đã đọc.
6. Nếu điều kiện đúng, thay đổi được commit và version tăng.
7. Nếu điều kiện sai, trả về concurrency conflict.
8. Chỉ sau khi commit thành công mới công bố Domain Event ra bên ngoài.

Có thể hình dung điều kiện ghi như sau:

```text
UPDATE orders
SET state = :newState,
    version = version + 1
WHERE id = :orderId
  AND version = :expectedVersion
```

Nếu số dòng bị ảnh hưởng là 1, lần ghi đã thắng.

Nếu số dòng bị ảnh hưởng là 0, Aggregate đã thay đổi kể từ lúc đọc. Adapter persistence phải báo concurrency conflict thay vì tiếp tục ghi đè.

Điểm quan trọng là `version` không phải một quy tắc nghiệp vụ. Nó là cơ chế kỹ thuật để bảo vệ việc áp dụng một quyết định nghiệp vụ lên đúng phiên bản mà quyết định đó đã quan sát.

## 5. Đưa expected version vào Repository

Application Service có thể điều phối use case, nhưng Repository nên che giấu chi tiết persistence.

Một hợp đồng đơn giản có thể là:

~~~java
public interface OrderRepository {
    Order get(OrderId id);

    void save(Order order, long expectedVersion);
}
~~~

Aggregate giữ version mà nó đã được load:

~~~java
public final class Order {
    private final OrderId id;
    private OrderState state;
    private long version;

    public Order(OrderId id, OrderState state, long version) {
        this.id = id;
        this.state = state;
        this.version = version;
    }

    public void confirm() {
        if (state != OrderState.DRAFT) {
            throw new OrderBusinessConflict(
                "Chỉ đơn hàng ở trạng thái DRAFT mới được xác nhận"
            );
        }

        state = OrderState.CONFIRMED;
    }

    public OrderId id() {
        return id;
    }

    public long version() {
        return version;
    }

    public OrderState state() {
        return state;
    }
}
~~~

Repository adapter có thể thực hiện kiểm tra version ở tầng persistence:

~~~java
public final class JdbcOrderRepository implements OrderRepository {
    private final OrderStore store;

    @Override
    public Order get(OrderId id) {
        return store.findById(id);
    }

    @Override
    public void save(Order order, long expectedVersion) {
        int updated = store.updateWithExpectedVersion(
            order.id(),
            order.state(),
            expectedVersion
        );

        if (updated == 0) {
            throw new ConcurrentAggregateUpdate(
                "Order đã được thay đổi bởi transaction khác"
            );
        }
    }
}
~~~

Trong ví dụ này, `ConcurrentAggregateUpdate` không phải lỗi nghiệp vụ. Nó cho application layer biết rằng command được xây dựng trên một phiên bản đã cũ.

Nếu dùng JPA, `@Version` có thể cung cấp cơ chế optimistic locking ở persistence adapter. Domain model vẫn nên giữ ngôn ngữ nghiệp vụ của mình, còn mapping `@Version` thuộc về mô hình persistence khi kiến trúc cho phép tách hai mô hình.

## 6. Command nên biểu diễn ý định, không mang theo một bản Aggregate hoàn chỉnh

Một API dễ gây nhầm lẫn là nhận toàn bộ trạng thái Aggregate từ client rồi ghi lại. Cách này làm tăng nguy cơ lost update vì client có thể gửi lại dữ liệu đã cũ.

Thay vào đó, command nên biểu diễn ý định:

~~~java
public record ConfirmOrder(
    OrderId orderId,
    long expectedVersion
) {}
~~~

Application Service:

~~~java
public final class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final DomainEventPublisher events;

    public void handle(ConfirmOrder command) {
        Order order = orders.get(command.orderId());

        order.confirm();

        orders.save(order, command.expectedVersion());

        events.publish(new OrderConfirmed(order.id()));
    }
}
~~~

Trong triển khai thực tế, việc phát event phải gắn với transaction hoặc transactional outbox để tránh trạng thái đã commit nhưng event bị mất. Mẫu cụ thể phụ thuộc hạ tầng, nhưng nguyên tắc DDD vẫn giữ nguyên: chỉ công bố kết quả đã được Aggregate chấp nhận và persistence đã xác nhận.

Có thể để Repository lấy expected version từ Aggregate đã load thay vì command. Khi đó cần bảo đảm request đã kiểm chứng rằng client đang thao tác trên version mong muốn. Cách chọn API là quyết định kiến trúc; điều cần giữ là không để persistence âm thầm ghi đè một phiên bản khác.

## 7. HTTP API có thể dùng ETag để mang phiên bản

Nếu UI đọc một đơn hàng rồi gửi command sau đó, HTTP có thể truyền version bằng ETag.

Ví dụ:

~~~text
GET /orders/42

ETag: "order-42-v7"
~~~

Khi người dùng xác nhận:

~~~text
POST /orders/42/confirmation

If-Match: "order-42-v7"
~~~

Nếu version đã thành 8, API có thể trả `412 Precondition Failed` vì precondition của client không còn đúng.

Một API khác có thể dùng `409 Conflict` để biểu diễn concurrency conflict ở mức nghiệp vụ ứng dụng. Điều quan trọng là contract phải nhất quán và client biết có thể làm gì tiếp theo.

Có thể phân biệt:

| HTTP | Ý nghĩa thường gặp |
|---|---|
| 400 | Command không hợp lệ về cấu trúc |
| 404 | Aggregate không tồn tại |
| 409 | Xung đột trạng thái hoặc concurrency cần xử lý |
| 412 | Precondition như If-Match không còn đúng |
| 422 | Dữ liệu hợp lệ về cú pháp nhưng không đáp ứng rule nghiệp vụ, nếu API chọn semantics này |

Không nên để client đoán loại lỗi từ message tự do. Nên có error code ổn định.

Ví dụ:

~~~json
{
  "code": "CONCURRENT_UPDATE",
  "message": "Đơn hàng đã thay đổi. Hãy tải lại trước khi xác nhận.",
  "resource": "Order",
  "resourceId": "42"
}
~~~

Với business conflict:

~~~json
{
  "code": "ORDER_ALREADY_CONFIRMED",
  "message": "Đơn hàng đã được xác nhận và không thể chuyển lại trạng thái.",
  "resource": "Order",
  "resourceId": "42"
}
~~~

## 8. Concurrency conflict và business conflict phải có đường xử lý riêng

Giả sử người dùng gửi `ConfirmOrder` với version 7.

### Trường hợp A: version đã thành 8

Persistence từ chối update vì `expectedVersion=7`.

Kết quả:

~~~text
CONCURRENT_UPDATE
~~~

Client nên đọc lại trạng thái mới và yêu cầu người dùng quyết định lại nếu thao tác không thể tự động hợp nhất.

### Trường hợp B: version vẫn là 7 nhưng trạng thái đã không cho phép xác nhận

Aggregate có thể từ chối:

~~~text
ORDER_CANNOT_BE_CONFIRMED
~~~

Đây là business conflict.

### Trường hợp C: version đã thành 8 và trạng thái mới cũng không cho phép xác nhận

Hai điều kiện đều có thể xuất hiện, nhưng nếu persistence chỉ phát hiện version trước khi Aggregate được áp dụng trên trạng thái mới, application layer cần quyết định chiến lược.

Một chiến lược an toàn là không tự động retry command nghiệp vụ khi có concurrency conflict. Có thể load lại Aggregate và cho người dùng hoặc policy nghiệp vụ quyết định có chạy lại ý định hay không.

Điểm này rất quan trọng: **retry một command không phải lúc nào cũng an toàn**.

Ví dụ `IncreaseQuantity(1)` có thể có nghĩa tương đối rõ ràng sau khi reload. Nhưng `SetPrice(100)` có thể ghi đè quyết định giá mới của người khác. `ConfirmOrder` có thể trở nên vô nghĩa sau khi đơn hàng đã bị hủy.

## 9. Không dùng pre-check đơn độc để bảo vệ invariant

Một lỗi phổ biến là kiểm tra điều kiện trước khi ghi:

~~~text
if remainingSeats > 0
    create reservation
~~~

Hai request có thể cùng đọc `remainingSeats = 1`.

Cả hai đều thấy điều kiện đúng.

Cả hai cùng tạo reservation.

Pre-check đã đúng tại thời điểm đọc nhưng sai tại thời điểm commit.

Invariant phải được bảo vệ ở ranh giới ghi.

Có ba cách phổ biến:

1. Gộp trạng thái và hành vi vào một Aggregate có optimistic concurrency.
2. Dùng constraint hoặc atomic update ở persistence boundary.
3. Dùng locking phù hợp nếu invariant yêu cầu cơ chế khóa chặt hơn.

Ví dụ atomic update:

~~~text
UPDATE inventory
SET remaining = remaining - 1
WHERE sku = :sku
  AND remaining > 0
~~~

Nếu số dòng cập nhật là 0, request không thể lấy thêm một đơn vị. Đây là cơ chế persistence bảo vệ invariant kỹ thuật.

Nếu quy tắc phức tạp hơn, cần xem lại Aggregate boundary thay vì thêm nhiều câu query kiểm tra rời rạc.

## 10. Unique constraint là một phần của chiến lược chống cạnh tranh

Giả sử nghiệp vụ yêu cầu `email` hoặc `externalReference` là duy nhất.

Kiểm tra:

~~~text
SELECT COUNT(*) FROM customers WHERE email = :email
~~~

rồi mới insert vẫn có race condition.

Hai transaction đều có thể thấy chưa tồn tại.

Cách an toàn hơn là có unique constraint ở database và chuyển lỗi constraint thành error code có ý nghĩa ở adapter.

~~~text
CREATE UNIQUE INDEX ux_customer_email
ON customer(email)
~~~

Trong DDD, database constraint không thay thế domain model. Nó là hàng rào cuối cùng cho một invariant mà persistence có thể bảo vệ trực tiếp.

Quy tắc phân lớp có thể là:

| Quy tắc | Nơi kiểm tra chính |
|---|---|
| Trạng thái Order cho phép confirm | Aggregate |
| Tổng tiền không âm | Value Object/Aggregate |
| ID duy nhất trong toàn database | Persistence constraint |
| Một reservation chỉ thuộc một order | Aggregate hoặc persistence tùy ownership |
| Không vượt credit limit | Aggregate hoặc Domain Service có dữ liệu cần thiết |
| Không đặt cùng slot khi đã có booking | Aggregate/persistence tùy mô hình |
| Trạng thái của context khác đã thay đổi | Integration policy/read model/process |

## 11. Pessimistic locking chỉ phù hợp khi contention và chi phí retry đáng kể

Optimistic concurrency phù hợp khi các transaction thường không đụng nhau.

Nếu một tài nguyên có contention rất cao, retry liên tục có thể tốn hơn việc giữ lock trong khoảng thời gian ngắn.

Pessimistic locking có thể dùng:

~~~text
SELECT ...
FROM inventory
WHERE sku = :sku
FOR UPDATE
~~~

Transaction giữ lock cho đến khi commit hoặc rollback.

Ưu điểm:

- Quyết định tuần tự rõ hơn ở vùng contention.
- Giảm số lần transaction thất bại do cạnh tranh.
- Hữu ích cho một số tài nguyên có số lượng nhỏ và tranh chấp cao.

Chi phí:

- Lock lâu làm giảm throughput.
- Deadlock có thể xảy ra.
- Transaction giữ lock trong thời gian dài làm hệ thống dễ nghẽn.
- Không phù hợp khi transaction phải chờ network hoặc gọi dịch vụ ngoài.

Không nên giữ database lock trong lúc gọi API từ context khác. Nếu use case cần phối hợp nhiều context, nên xem xét process manager, Saga hoặc cơ chế eventual consistency thay vì kéo dài transaction.

## 12. Đừng dùng distributed lock để che một Aggregate boundary chưa rõ

Khi nhiều service cùng sửa một tài nguyên, phản xạ phổ biến là thêm distributed lock.

Lock có thể hữu ích trong một số hạ tầng, nhưng nó không tự trả lời câu hỏi nghiệp vụ:

> Ai là chủ sở hữu của invariant?

Nếu `Order`, `Inventory` và `Payment` đều cần cùng một lock để một thao tác hoàn thành, có thể Aggregate boundary hoặc ranh giới bounded context đang chưa được mô hình hóa rõ.

Ví dụ:

- Sales sở hữu quyết định order.
- Inventory sở hữu available stock.
- Payment sở hữu authorization.

Một `ConfirmOrder` có thể phát event hoặc command để các context xử lý theo trách nhiệm riêng. Nếu nghiệp vụ yêu cầu rollback toàn bộ theo một transaction phân tán, cần chứng minh đó thực sự là invariant tức thời thay vì một quy trình có thể đạt kết quả cuối cùng.

Distributed lock nên là lựa chọn có chủ đích, không phải cách thay thế cho mô hình miền.

## 13. Business conflict nên xuất hiện trong ngôn ngữ của miền

Không nên trả về một lỗi chung như:

~~~text
IllegalStateException
~~~

rồi bắt UI đoán ý nghĩa.

Có thể định nghĩa lỗi miền:

~~~java
public final class OrderBusinessConflict extends RuntimeException {
    public OrderBusinessConflict(String message) {
        super(message);
    }
}
~~~

Các loại conflict có thể có code ổn định:

| Code | Ý nghĩa |
|---|---|
| `ORDER_ALREADY_CONFIRMED` | Order đã xác nhận |
| `ORDER_ALREADY_CANCELLED` | Order đã hủy |
| `ORDER_CANNOT_BE_CONFIRMED` | Trạng thái hiện tại không cho phép xác nhận |
| `CREDIT_LIMIT_EXCEEDED` | Không đủ hạn mức |
| `RESERVATION_UNAVAILABLE` | Tài nguyên không còn |
| `PROMOTION_EXHAUSTED` | Khuyến mại đã hết quota |
| `CONCURRENT_UPDATE` | Aggregate đã thay đổi từ version được quan sát |

Điều này tạo ra Ubiquitous Language cho cả code, API và test.

## 14. Retry phải dựa trên tính chất của command

Không phải concurrency conflict nào cũng nên retry tự động.

Có thể phân loại:

| Command | Retry tự động sau reload | Lý do |
|---|---|---|
| `IncrementCounter(1)` | Có thể | Ý định vẫn có thể giữ nguyên |
| `AddLine(product, quantity)` | Có thể, nếu policy cho phép | Ý định tương đối độc lập |
| `ConfirmOrder` | Thường không | Trạng thái mới có thể thay đổi quyết định |
| `SetPrice(100)` | Thường không | Có nguy cơ ghi đè quyết định mới |
| `CancelOrder` | Phụ thuộc rule | Có thể không còn hợp lệ |
| `ReserveSlot(slotId)` | Không nên tự động | Slot có thể đã được người khác giữ |

Nếu retry, cần giới hạn số lần và tránh lặp side effect.

Một flow an toàn:

~~~text
read version 7
        |
        v
apply command
        |
        v
save expectedVersion=7
        |
   +----+----+
   |         |
 success   conflict
   |         |
   v         v
commit     reload
event      evaluate policy
              |
        +-----+------+
        |            |
      retry        reject
~~~

Retry chỉ nên là policy của application layer. Aggregate vẫn phải thực thi rule mỗi lần command được áp dụng.

## 15. Idempotency và concurrency giải quyết hai vấn đề khác nhau

Idempotency giúp xử lý việc cùng một command được gửi nhiều lần.

Concurrency control giúp ngăn hai thay đổi hợp lệ dựa trên cùng một phiên bản ghi đè nhau.

Ví dụ client gửi:

~~~text
POST /payments
Idempotency-Key: pay-7f31
~~~

Request timeout khiến client gửi lại cùng key.

Nếu server đã xử lý request đầu tiên, request thứ hai nên trả lại kết quả đã lưu hoặc một kết quả tương đương theo contract.

Nhưng nếu hai người dùng thực sự gửi hai command khác nhau, hai idempotency key khác nhau không giải quyết concurrency.

Vì vậy một use case thanh toán có thể cần cả:

- idempotency key ở application/API boundary;
- optimistic concurrency trên Payment Aggregate;
- unique constraint cho provider transaction ID;
- business rule ngăn capture vượt authorization.

## 16. Kiểm chứng xung đột trong Aggregate

Test đơn vị nên chứng minh invariant và chuyển trạng thái.

Ví dụ:

~~~java
class OrderTest {

    @Test
    void cannot_confirm_cancelled_order() {
        Order order = Order.cancelled(
            new OrderId("42"),
            7
        );

        assertThatThrownBy(order::confirm)
            .isInstanceOf(OrderBusinessConflict.class)
            .hasMessageContaining("không được xác nhận");
    }

    @Test
    void confirmation_changes_state() {
        Order order = Order.draft(
            new OrderId("42"),
            7
        );

        order.confirm();

        assertThat(order.state())
            .isEqualTo(OrderState.CONFIRMED);
    }
}
~~~

Test này không kiểm tra database. Nó chứng minh rule thuộc về Aggregate.

## 17. Kiểm chứng optimistic concurrency ở Repository adapter

Test integration nên chứng minh hai transaction cùng version không thể cùng commit.

Có thể mô phỏng:

~~~java
@Test
void second_update_with_stale_version_is_rejected() {
    Order first = repository.get(new OrderId("42"));
    Order second = repository.get(new OrderId("42"));

    first.confirm();
    repository.save(first, 7);

    second.cancel();

    assertThatThrownBy(() -> repository.save(second, 7))
        .isInstanceOf(ConcurrentAggregateUpdate.class);
}
~~~

Test này cần persistence thật hoặc adapter test phù hợp để chứng minh điều kiện `WHERE version = expectedVersion` thực sự được thực thi.

Nếu chỉ mock Repository rồi cấu hình mock ném exception, test không chứng minh cơ chế concurrency ở database.

## 18. Kiểm chứng business conflict sau khi reload

Một test quan trọng là không tự động coi reload là đủ để thành công.

Ví dụ:

~~~java
@Test
void reload_after_concurrency_conflict_can_reveal_business_conflict() {
    Order first = repository.get(new OrderId("42"));
    Order second = repository.get(new OrderId("42"));

    first.confirm();
    repository.save(first, 7);

    assertThatThrownBy(() -> repository.save(second, 7))
        .isInstanceOf(ConcurrentAggregateUpdate.class);

    Order latest = repository.get(new OrderId("42"));

    assertThatThrownBy(latest::confirm)
        .isInstanceOf(OrderBusinessConflict.class);
}
~~~

Trong thực tế, nếu `second` là command `CancelOrder`, kết quả reload có thể khác. Chính sách retry phải dựa trên **ý định** và trạng thái mới.

## 19. Dùng test cạnh tranh có hai transaction thay vì chỉ gọi tuần tự

Một test tốt hơn có thể tạo hai transaction chạy đồng thời.

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);

Future<?> first = executor.submit(() ->
    confirm(orderId, 7)
);

Future<?> second = executor.submit(() ->
    cancel(orderId, 7)
);

List<Result> results = List.of(
    getResult(first),
    getResult(second)
);

assertThat(results)
    .filteredOn(Result::isSuccess)
    .hasSize(1);

assertThat(results)
    .filteredOn(Result::isConcurrencyConflict)
    .hasSize(1);
~~~

Cần kiểm soát test để không phụ thuộc timing ngẫu nhiên quá mức. Mục tiêu là tạo một barrier rõ ràng: cả hai transaction đọc cùng version trước khi cho phép ghi.

Mẫu test có thể dùng latch:

~~~java
CountDownLatch loaded = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);
~~~

Mỗi worker báo đã load version 7, sau đó cùng được release. Test trở nên có ý nghĩa hơn vì nó cố ý tái hiện race condition.

## 20. Sequence Diagram cho optimistic concurrency

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant API as Application
    participant DB as Order Repository

    A->>API: ConfirmOrder(order=42, expectedVersion=7)
    B->>API: CancelOrder(order=42, expectedVersion=7)

    API->>DB: Load Order 42 version 7
    DB-->>API: Order version 7

    API->>DB: Load Order 42 version 7
    DB-->>API: Order version 7

    API->>DB: Save Confirm, expectedVersion=7
    DB-->>API: Success, version=8

    API->>DB: Save Cancel, expectedVersion=7
    DB-->>API: 0 rows updated

    API-->>B: CONCURRENT_UPDATE
    API-->>A: OrderConfirmed
~~~

Sơ đồ cho thấy conflict được phát hiện tại điểm ghi. Không cần dự đoán trước request nào sẽ thắng; database hoặc persistence mechanism xác định transaction đầu tiên commit thành công.

## 21. Khi nhiều Aggregate cùng tham gia một use case

Một use case có thể chạm nhiều Aggregate:

~~~text
PlaceOrder
  |
  +-- Order
  +-- Inventory
  +-- CustomerCredit
~~~

Không nên vì vậy mà gom tất cả thành một Aggregate lớn chỉ để tránh concurrency conflict.

Nếu Order phải xác nhận ngay khi:

- Inventory có đủ hàng;
- Credit còn hạn mức;
- Payment được authorize;

thì cần xác định phần nào là invariant tức thời của một Aggregate và phần nào là workflow giữa các context.

Một hướng có thể là:

~~~mermaid
flowchart LR
    C[Confirm Order] --> O[Order Aggregate]
    O --> E[OrderConfirmed]
    E --> I[Inventory]
    E --> P[Payment]
    I --> IE[InventoryReserved]
    P --> PE[PaymentAuthorized]
    IE --> W[Process Policy]
    PE --> W
    W --> F[Order Fulfillment Ready]
~~~

Ở đây, các context có thể đạt trạng thái cuối cùng theo event. Nếu một bước thất bại, policy có thể thực hiện compensation phù hợp.

Điều này khác với việc dùng concurrency lock để ép ba Aggregate trở thành một transaction lớn.

## 22. Business conflict giữa các Bounded Context cần có contract riêng

Ví dụ Sales gửi yêu cầu giữ hàng cho Inventory.

Sales có thể biết:

~~~text
OrderConfirmed
~~~

Inventory có thể trả:

~~~text
ReservationRejected
reason=OUT_OF_STOCK
~~~

Sales không nên đọc trực tiếp trạng thái nội bộ của Inventory rồi tự quyết định thay Inventory.

Contract nên dùng language ổn định của integration:

~~~json
{
  "type": "ReservationRejected",
  "reservationId": "R-42",
  "orderId": "O-42",
  "reason": "OUT_OF_STOCK"
}
~~~

Sau đó Sales áp dụng policy riêng:

~~~text
ReservationRejected
        |
        v
Order = WaitingForInventoryFailure
        |
        v
Notify customer / cancel / manual review
~~~

Xung đột của Inventory không biến thành exception xuyên context. Nó trở thành một kết quả nghiệp vụ được contract hóa.

## 23. Cross-context consistency không thể giải quyết bằng một version duy nhất

Mỗi Aggregate có thể có version riêng.

Ví dụ:

~~~text
Order version = 12
InventoryReservation version = 4
PaymentAuthorization version = 9
~~~

Không có lý do để coi ba số này là một version toàn hệ thống.

Nếu cần theo dõi tiến trình của một workflow, có thể dùng process state:

~~~text
OrderFulfillmentProcess
    orderId
    reservationStatus
    paymentStatus
    fulfillmentStatus
~~~

Process state biểu diễn tiến trình nghiệp vụ, còn version của từng Aggregate bảo vệ cạnh tranh ở ranh giới của Aggregate đó.

Đây là hai khái niệm khác nhau và nên được đặt tên khác nhau trong code.

## 24. Đừng coi version là thứ người dùng phải hiểu

Version là cơ chế kiểm soát cạnh tranh.

UI có thể hiển thị:

~~~text
"Đơn hàng đã được cập nhật bởi một người khác. Hãy tải lại để xem thay đổi."
~~~

Không cần hiển thị:

~~~text
"ExpectedVersion 7 không khớp ActualVersion 8"
~~~

Tuy nhiên log và telemetry nên giữ thông tin kỹ thuật:

~~~text
resource=Order
id=42
expectedVersion=7
actualVersion=8
command=ConfirmOrder
correlationId=...
~~~

Điều này giúp điều tra contention mà không làm lộ chi tiết persistence vào domain language của người dùng.

## 25. Theo dõi contention để phát hiện Aggregate boundary có vấn đề

Concurrency conflict tăng cao có thể là tín hiệu mô hình cần xem lại.

Các metric hữu ích:

| Metric | Câu hỏi |
|---|---|
| Concurrency conflicts / Aggregate | Aggregate nào bị tranh chấp nhiều? |
| Retry rate | Policy retry có quá mạnh? |
| Business conflict rate | Rule nào thường xuyên từ chối? |
| Transaction duration | Transaction có giữ tài nguyên quá lâu? |
| Lock wait | Pessimistic lock có gây nghẽn? |
| Unique constraint violation | Có race condition hoặc UX gây lặp? |
| Event processing delay | Cross-context state có quá stale? |

Nếu một Aggregate rất lớn có conflict rate cao, có thể nhiều use case không thực sự cần cùng một transaction boundary.

Nếu conflict rate thấp nhưng business conflict cao, vấn đề có thể nằm ở workflow hoặc UX.

Metric giúp phân biệt hai nguyên nhân.

## 26. Một quy trình kiểm chứng từ command đến persistence

Có thể dùng quy trình sau cho mỗi use case có nguy cơ cạnh tranh:

### Bước 1: Viết invariant

Ví dụ:

~~~text
Một Order chỉ được Confirm một lần.
Order đã Cancelled không thể Confirm.
~~~

### Bước 2: Xác định Aggregate owner

~~~text
Order Aggregate
~~~

### Bước 3: Xác định command

~~~text
ConfirmOrder(orderId, expectedVersion)
~~~

### Bước 4: Kiểm tra domain rule

Aggregate quyết định command có hợp lệ trên trạng thái đã load không.

### Bước 5: Kiểm tra concurrency

Repository lưu với expected version.

### Bước 6: Kiểm tra persistence constraint

Nếu có unique invariant mà database có thể bảo vệ, tạo constraint.

### Bước 7: Commit và phát event

Chỉ publish kết quả sau khi thay đổi đã được persistence xác nhận.

### Bước 8: Kiểm tra failure path

Test ít nhất:

- stale version;
- invalid state;
- duplicate request;
- unique constraint race;
- retry;
- cross-context rejection nếu use case có integration.

## 27. Bảng quyết định cho một use case

| Điều kiện | Hành động |
|---|---|
| Aggregate không tồn tại | Trả Not Found |
| Version đúng + command hợp lệ | Commit |
| Version sai | Concurrency Conflict |
| Version đúng + business rule sai | Business Conflict |
| Unique constraint thất bại | Chuyển thành conflict có code ổn định |
| Timeout sau commit nhưng trước response | Dùng idempotency hoặc query trạng thái |
| Event publish lỗi sau commit | Dùng outbox hoặc cơ chế reliable publication |
| Context khác từ chối | Chuyển thành process state/event theo contract |
| Retry command có thể đổi ý nghĩa | Không auto-retry; yêu cầu quyết định mới |

## 28. Ví dụ hoàn chỉnh: Confirm Order

Một handler có thể có cấu trúc:

~~~java
public final class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final Outbox outbox;

    public ConfirmOrderResult handle(ConfirmOrder command) {
        Order order = orders.get(command.orderId());

        order.confirm();

        orders.save(
            order,
            command.expectedVersion()
        );

        outbox.appendAll(order.pullDomainEvents());

        return ConfirmOrderResult.success(
            order.id(),
            order.version()
        );
    }
}
~~~

Persistence adapter thực hiện optimistic check:

~~~java
public int updateWithExpectedVersion(
    Order order,
    long expectedVersion
) {
    return jdbc.update("""
        UPDATE orders
        SET state = ?, version = version + 1
        WHERE id = ?
          AND version = ?
        """,
        order.state().name(),
        order.id().value(),
        expectedVersion
    );
}
~~~

Nếu kết quả là 0:

~~~java
throw new ConcurrentAggregateUpdate(
    order.id(),
    expectedVersion
);
~~~

Nếu kết quả là 1:

~~~text
Order state changed
version incremented
domain event stored
transaction committed
~~~

Cách này làm cho điểm kiểm chứng cạnh tranh trở nên rõ ràng và có thể kiểm thử.

## 29. Tránh giữ transaction qua network

Một flow nguy hiểm là:

~~~text
BEGIN DB TRANSACTION
    load Order
    lock Order
    call Payment API
    wait
    call Inventory API
    wait
    update Order
COMMIT
~~~

Transaction database có thể giữ lock trong toàn bộ thời gian network.

Nếu Payment hoặc Inventory chậm, contention tăng.

Một cách khác là chia workflow:

~~~text
ConfirmOrder
    |
    v
Order -> PendingFulfillment
    |
    +--> Payment command
    |
    +--> Inventory command
    |
    v
Domain Events
    |
    v
Process Policy
    |
    v
Order -> Confirmed / Failed
~~~

Thiết kế chính xác phụ thuộc yêu cầu nghiệp vụ. Nếu thực sự cần atomicity ngay lập tức, phải chứng minh các thay đổi thuộc cùng một consistency boundary và chấp nhận chi phí transaction tương ứng.

## 30. Những sai lầm thường gặp

### 30.1 Chỉ kiểm tra version ở UI

UI có thể gửi version, nhưng persistence vẫn phải bảo vệ điều kiện ghi. Client không đáng tin cậy để bảo đảm concurrency.

### 30.2 Chỉ đọc rồi ghi toàn bộ row

Cách này dễ tạo lost update nếu không có version hoặc atomic condition.

### 30.3 Tự retry mọi conflict

Retry có thể biến một quyết định cũ thành một quyết định mới mà người dùng chưa từng chấp thuận.

### 30.4 Dùng exception kỹ thuật làm Ubiquitous Language

`OptimisticLockException` có ý nghĩa với persistence adapter. `CONCURRENT_UPDATE` là contract phù hợp hơn cho application/API.

### 30.5 Gộp mọi Aggregate vào một transaction

Điều này làm Aggregate lớn hơn và tăng contention chỉ để né một vấn đề workflow.

### 30.6 Kiểm tra unique bằng SELECT rồi INSERT

Race condition vẫn xảy ra. Nếu database có thể bảo vệ uniqueness, cần unique constraint.

### 30.7 Giữ lock trong lúc gọi service ngoài

Lock lâu tạo contention và có thể gây deadlock hoặc giảm throughput.

### 30.8 Không test hai transaction thực sự

Test đơn vị có thể chứng minh domain rule nhưng không chứng minh database có ngăn lost update.

### 30.9 Không có idempotency cho request dễ retry

Timeout có thể khiến client gửi lại command và tạo side effect kép.

### 30.10 Để context khác quyết định invariant của context sở hữu

Sales không nên tự suy diễn nội bộ Inventory. Integration contract phải trả về kết quả mà context sở hữu cho phép công bố.

## 31. Checklist review

### Domain model

- [ ] Invariant đã được viết bằng ngôn ngữ nghiệp vụ chưa?
- [ ] Aggregate owner của invariant đã rõ chưa?
- [ ] Business conflict có error code ổn định chưa?
- [ ] Command biểu diễn ý định thay vì bản Aggregate hoàn chỉnh chưa?

### Concurrency

- [ ] Aggregate có version hoặc cơ chế tương đương chưa?
- [ ] Save có kiểm tra expected version tại điểm ghi chưa?
- [ ] Lost update có test không?
- [ ] Retry policy có được định nghĩa cho từng command chưa?
- [ ] Có cần idempotency không?

### Persistence

- [ ] Unique invariant có database constraint nếu phù hợp chưa?
- [ ] Adapter có chuyển persistence conflict thành contract phù hợp chưa?
- [ ] Có test integration chứng minh atomic update/optimistic lock chưa?
- [ ] Transaction có giữ lock qua network không?

### Cross-context

- [ ] Mỗi context có owner rõ ràng cho invariant chưa?
- [ ] Integration contract có language ổn định không?
- [ ] Eventual consistency có được mô hình hóa như process state không?
- [ ] Failure/compensation path đã được kiểm thử chưa?

### API và vận hành

- [ ] HTTP status và error code có nhất quán không?
- [ ] UI có hướng dẫn người dùng xử lý stale data không?
- [ ] Log có correlation ID và expected/actual version khi cần không?
- [ ] Có metric về concurrency conflict và business conflict không?

## 32. Cách chọn cơ chế theo loại xung đột

Có thể dùng bảng sau như một điểm khởi đầu:

| Vấn đề | Cơ chế ưu tiên |
|---|---|
| Hai command cùng sửa một Aggregate | Optimistic concurrency |
| Một tài nguyên cực kỳ tranh chấp | Cân nhắc pessimistic locking |
| Giá trị duy nhất | Database unique constraint |
| Request có thể được gửi lại | Idempotency |
| Workflow nhiều context | Domain Event + process policy |
| Invariant trong cùng Aggregate | Aggregate method |
| Invariant cần dữ liệu nhiều Aggregate | Xem lại boundary hoặc dùng Domain Service/process |
| Side effect sau commit | Outbox hoặc reliable publication |
| Dữ liệu đọc có thể stale | Version/ETag + policy xử lý stale state |

Không có một cơ chế duy nhất giải quyết mọi dạng cạnh tranh. Mỗi cơ chế phải gắn với invariant hoặc failure mode mà nó bảo vệ.

## 33. Bài tập thực hành

Hãy thiết kế use case `ReserveSeat` cho một hệ thống đặt chỗ.

Giả định:

- Một `Seat` chỉ có thể được giữ bởi một reservation đang hoạt động.
- Hai người dùng có thể cùng nhìn thấy ghế còn trống.
- Reservation hết hạn sau một khoảng thời gian.
- Request có thể được gửi lại vì timeout.
- Booking và Payment nằm ở các Bounded Context khác nhau.

Hãy trả lời:

1. Aggregate nào sở hữu invariant ghế không được giữ hai lần?
2. Version được đặt ở đâu?
3. Command có những field nào?
4. Điều gì xảy ra khi expected version cũ?
5. Unique constraint có cần không?
6. Idempotency key bảo vệ điều gì?
7. Payment thất bại sau khi seat đã được giữ thì workflow xử lý thế nào?
8. Test nào chứng minh hai request đồng thời không cùng thắng?
9. Error code nào biểu diễn `SEAT_ALREADY_RESERVED`?
10. Có nên giữ database lock trong lúc gọi Payment không?

Một lời giải tốt phải giải thích **vì sao** cơ chế được chọn, không chỉ liệt kê công nghệ.

## 34. Một mẫu mental model để review thay đổi

Khi review một command có nguy cơ cạnh tranh, đi theo chuỗi:

~~~text
Ý định người dùng
      |
      v
Command
      |
      v
Aggregate owner
      |
      v
Business invariant
      |
      v
State transition
      |
      v
Expected version
      |
      v
Atomic persistence check
      |
      v
Commit
      |
      v
Domain Event
      |
      v
Cross-context policy
~~~

Nếu một bước không có câu trả lời rõ ràng, đó là dấu hiệu cần làm rõ mô hình trước khi thêm cơ chế lock hoặc retry.

## Kết luận

Kiểm chứng cạnh tranh cập nhật trong DDD bắt đầu từ việc xác định **quyết định nào cần nhất quán** và **Aggregate nào sở hữu quyết định đó**. Optimistic concurrency với version bảo vệ việc một command không ghi đè phiên bản mà nó chưa quan sát. Business conflict lại cần được Aggregate biểu diễn bằng ngôn ngữ nghiệp vụ.

Khi hai vấn đề được tách rõ, persistence có thể tập trung vào tính toàn vẹn của lần ghi, domain model tập trung vào invariant, application layer quyết định retry và idempotency, còn integration layer quản lý những kết quả diễn ra giữa các Bounded Context.

Một hệ thống được thiết kế tốt sẽ không cố loại bỏ mọi cạnh tranh. Nó làm cho cạnh tranh có thể phát hiện, có thể kiểm chứng và có đường xử lý rõ ràng đối với từng loại xung đột.

