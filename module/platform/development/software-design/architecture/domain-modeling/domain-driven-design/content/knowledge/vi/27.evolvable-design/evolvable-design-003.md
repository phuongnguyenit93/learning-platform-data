# Tiền điều kiện, hậu điều kiện và bất biến có thể kiểm chứng

Trong Domain-Driven Design (DDD), một mô hình miền tốt phải làm rõ hành vi nào được phép, điều gì phải đúng trước khi hành vi bắt đầu và điều gì được bảo đảm sau khi hành vi hoàn tất. Những cam kết này giúp đội ngũ thay đổi phần mềm mà vẫn giữ được quy tắc nghiệp vụ.

**Design by Contract (DbC)** diễn đạt hành vi bằng ba khái niệm: tiền điều kiện (precondition), hậu điều kiện (postcondition) và bất biến (invariant). Tiền điều kiện mô tả những gì phải đúng trước khi gọi một hành vi. Hậu điều kiện mô tả điều được bảo đảm nếu hành vi hoàn tất thành công. Bất biến mô tả trạng thái luôn phải hợp lệ tại các ranh giới công khai của một đối tượng hoặc Aggregate.

Trong DDD, các hợp đồng này có thể được diễn đạt bằng Value Object, phương thức của Entity/Aggregate, application use case, validation, database constraint và automated test. Mục tiêu là biến quy tắc thành điều có thể đọc, thực thi và kiểm chứng, để một thay đổi trong tương lai không vô tình phá vỡ hành vi đã được thống nhất với chuyên gia nghiệp vụ.

## 1. Design by Contract là gì?

Design by Contract xem một thao tác phần mềm như một thỏa thuận giữa bên gọi và bên thực hiện:

- Bên gọi phải đáp ứng các điều kiện đầu vào đã cam kết.
- Bên thực hiện phải duy trì các invariant và cung cấp kết quả đúng như cam kết khi thao tác thành công.
- Nếu điều kiện không được đáp ứng, thao tác phải từ chối theo cách đã định nghĩa.

Một hợp đồng có thể được biểu diễn bằng ký hiệu Hoare:

\[
\{P\}\ C\ \{Q\}
\]

Trong đó:

- \(P\) là precondition: điều kiện phải đúng trước khi chạy.
- \(C\) là command hoặc hành vi được thực hiện.
- \(Q\) là postcondition: điều kiện phải đúng sau khi hành vi hoàn tất thành công.

Ví dụ, hành vi rút tiền:

\[
\{amount > 0 \land balance \ge amount\}
\ \operatorname{withdraw}(amount)\
\{balance' = balance - amount\}
\]

Hợp đồng nói rằng số tiền rút phải dương và số dư đủ trước khi thực hiện. Nếu rút thành công, số dư mới bằng số dư cũ trừ số tiền rút.

Ký hiệu trên mô tả ý nghĩa logic. Trong code thực tế, cần xác định cả lỗi, side effect, concurrency và điều kiện nào được bảo đảm khi thao tác thất bại.

### Hợp đồng giúp đội ngũ làm rõ điều gì?

Một hợp đồng tốt trả lời được:

- Ai chịu trách nhiệm cung cấp dữ liệu hợp lệ?
- Hành vi nào được phép ở trạng thái hiện tại?
- Trạng thái nào phải luôn hợp lệ?
- Khi thành công, hệ thống bảo đảm điều gì?
- Khi thất bại, state có được giữ nguyên không?
- Những thành phần nào có thể thay đổi?
- Làm thế nào kiểm thử được cam kết đó?

Hợp đồng không chỉ là comment hoặc tài liệu. Những điều kiện quan trọng cần được thực thi trong code và kiểm chứng bằng test hoặc constraint phù hợp.

## 2. Phân biệt Precondition, Postcondition và Invariant

Ba khái niệm có liên quan nhưng không thay thế nhau.

| Khái niệm | Câu hỏi | Thời điểm | Ví dụ |
|---|---|---|---|
| Precondition | Điều gì phải đúng để bắt đầu hành vi? | Trước thao tác | Số lượng giữ chỗ phải dương |
| Postcondition | Điều gì được bảo đảm sau khi thành công? | Sau thao tác | Số lượng đã giữ tăng đúng lượng yêu cầu |
| Invariant | Trạng thái nào luôn phải hợp lệ? | Trước và sau mọi thao tác công khai | Tồn kho khả dụng không âm |

Ví dụ với Aggregate Inventory:

- Precondition của reserve(quantity): quantity lớn hơn 0 và số lượng khả dụng đủ.
- Postcondition khi thành công: reserved tăng quantity, available giảm quantity.
- Invariant: onHand không âm, reserved không âm và reserved không vượt onHand.

Một precondition có thể kiểm tra một invariant trước khi hành vi chạy. Postcondition có thể chứng minh một invariant vẫn được giữ sau khi chạy. Nhưng mỗi loại trả lời một câu hỏi khác nhau.

### Invariant không phải điều kiện chỉ kiểm tra khi tạo object

Invariant phải đúng trong toàn bộ vòng đời của đối tượng tại các ranh giới công khai. Nếu chỉ kiểm tra trong constructor mà các phương thức sau đó có thể phá vỡ trạng thái, invariant chưa được bảo vệ.

### Postcondition chỉ áp dụng khi hành vi thành công

Nếu một command bị từ chối vì không đủ tồn kho, postcondition của nhánh thành công không áp dụng. Hợp đồng cần mô tả rõ kết quả thất bại, chẳng hạn state không đổi và không phát event StockReserved.

## 3. Precondition: điều kiện để hành vi được phép bắt đầu

Precondition xác định yêu cầu tối thiểu để một hành vi có ý nghĩa và có thể được thực hiện an toàn.

Ví dụ:

- Order.confirm() yêu cầu đơn còn ở trạng thái Draft và có ít nhất một dòng hàng.
- Payment.capture(amount) yêu cầu payment đã được authorize và amount nằm trong giới hạn được phép capture.
- Inventory.reserve(quantity) yêu cầu quantity dương và còn đủ hàng.
- Membership.upgrade(tier) yêu cầu tier mới cao hơn tier hiện tại và khách hàng đáp ứng điều kiện nâng hạng.

Precondition có thể gồm:

1. Điều kiện về kiểu và cấu trúc dữ liệu.
2. Điều kiện về giá trị.
3. Điều kiện về trạng thái hiện tại.
4. Điều kiện về quyền thực hiện.
5. Điều kiện về tài nguyên hoặc dữ liệu liên quan.
6. Điều kiện về thời gian hoặc phiên bản.

Không phải mọi precondition đều thuộc cùng một layer. Ví dụ, JSON có đúng kiểu là trách nhiệm API adapter; Order có thể được xác nhận hay không là trách nhiệm domain; actor có quyền trên order hay không thường được kiểm tra ở application/security layer.

### Kiểm tra precondition tại nơi có thẩm quyền

Giả sử một endpoint kiểm tra đơn đang ở trạng thái Draft trước khi gọi handler:

    if (order.status() == DRAFT) {
        handler.confirm(orderId);
    }

Kiểm tra này có thể hữu ích để trả phản hồi sớm, nhưng không đủ để bảo vệ quy tắc. Trạng thái có thể thay đổi sau lần đọc, và một use case khác có thể gọi Aggregate mà không đi qua endpoint này.

Aggregate vẫn phải tự kiểm tra điều kiện khi thực thi:

    order.confirm();

Domain behavior phải bảo vệ precondition có ý nghĩa nghiệp vụ. Kiểm tra ở API chỉ là lớp phản hồi sớm, không phải nguồn bảo vệ cuối cùng.

## 4. Postcondition: cam kết sau khi hành vi hoàn tất

Postcondition mô tả điều mà bên gọi có thể tin cậy sau khi hành vi trả về thành công.

Ví dụ với Order.confirm():

- Trạng thái đơn chuyển từ Draft sang Confirmed.
- Thời điểm xác nhận được ghi nhận.
- Mọi dòng hàng cần thiết vẫn thuộc đơn.
- Event OrderConfirmed được ghi nhận để phát sau commit.

Ví dụ với Inventory.reserve(quantity):

- reserved tăng đúng quantity.
- available giảm đúng quantity.
- Reservation mới có identity.
- Tổng lượng giữ chỗ không vượt lượng tồn thực tế.

Một postcondition tốt không chỉ nói “method trả về true”. Nó nói kết quả nghiệp vụ nào được bảo đảm.

### Postcondition và frame condition

Ngoài điều gì thay đổi, hợp đồng có thể mô tả điều gì không được thay đổi. Trong DbC, phần này thường được gọi là frame condition.

Ví dụ, khi đổi địa chỉ giao hàng:

- deliveryAddress phải bằng địa chỉ mới.
- orderId, customerId và các dòng hàng không đổi.
- Tổng tiền không đổi nếu phí giao hàng không phụ thuộc địa chỉ.
- Trạng thái đơn vẫn được giữ nguyên nếu nghiệp vụ cho phép đổi địa chỉ ở trạng thái hiện tại.

Frame condition giúp ngăn một refactor vô tình thay đổi dữ liệu ngoài phạm vi use case.

### Hành vi thất bại cũng cần hợp đồng

Ví dụ reserve(quantity) có thể trả về InsufficientStock. Hợp đồng nên nói rõ:

- Không tạo reservation.
- onHand và reserved không đổi.
- Không phát event thành công.
- Kết quả lỗi chứa thông tin đủ để application xử lý.

Điều này quan trọng với thao tác có side effect hoặc nhiều bước.

## 5. Invariant: trạng thái luôn phải hợp lệ

Invariant là quy tắc mà đối tượng hoặc Aggregate phải duy trì. Nó giới hạn những state có thể tồn tại ở ranh giới công khai.

Ví dụ:

- Số lượng của một OrderLine phải lớn hơn 0.
- Tổng tiền của Order không được âm.
- Tổng số lượng đã giữ không được vượt số lượng tồn.
- Một Payment đã Captured không thể quay về Authorized.
- Một Invoice đã Issued không thể bị xóa như một draft.
- Một tài khoản đã đóng không thể tiếp tục ghi nhận giao dịch mới.

Invariant có thể ở nhiều phạm vi:

| Phạm vi | Ví dụ | Cơ chế bảo vệ |
|---|---|---|
| Value Object | Quantity luôn dương | Constructor/factory |
| Entity | Email hoặc identity không bị thay đổi tùy tiện | Encapsulation và behavior |
| Aggregate | Order không xác nhận khi chưa có dòng hàng | Aggregate Root |
| Bounded Context | Mã hóa đơn là duy nhất | Domain policy và database unique constraint |
| Hệ thống phân tán | Không giữ hàng vượt tồn kho | Context sở hữu Inventory, transaction và concurrency control |

### Invariant cần được bảo vệ ở mọi đường thay đổi

Nếu một Aggregate có nhiều phương thức công khai, mỗi phương thức có khả năng thay đổi state đều phải duy trì invariant. Không nên dựa vào một application handler duy nhất để giữ quy tắc nếu còn đường ghi khác.

### Invariant có thể phụ thuộc vào dữ liệu ngoài

Một số quy tắc cần thông tin do context khác sở hữu, ví dụ hạn mức tín dụng hoặc tồn kho. Aggregate không nên tự gọi network để lấy dữ liệu. Application có thể lấy thông tin qua port, sau đó gọi domain behavior với dữ kiện cần thiết. Nếu dữ liệu có thể thay đổi đồng thời, context sở hữu phải bảo vệ quyết định cuối cùng.

## 6. Đặt hợp đồng ở đúng nơi trong DDD

Một quy tắc cần được đặt ở layer có đủ thông tin và quyền kiểm soát để bảo vệ nó.

### Value Object

Value Object bảo vệ invariant nội tại của một giá trị.

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero"
            );
        }
    }
}
~~~

Sau khi tạo thành công, mọi Quantity đều có giá trị dương. Các domain method có thể dựa vào cam kết đó mà không phải lặp lại kiểm tra.

### Entity

Entity bảo vệ identity và các chuyển đổi hợp lệ trong vòng đời của nó.

Ví dụ, Payment có thể cho phép authorize khi đang Pending và capture khi đang Authorized. Không nên cho phép code bên ngoài gán trực tiếp status.

### Aggregate Root

Aggregate Root bảo vệ invariant cần nhất quán trong Aggregate boundary. Nó là cổng thay đổi state của các entity con.

Ví dụ, Order quyết định có thể thêm dòng hàng, xác nhận hoặc hủy đơn hay không. Application gọi hành vi root thay vì sửa trực tiếp OrderLine rồi tự cập nhật tổng tiền.

### Application Layer

Application Layer kiểm tra và phối hợp các điều kiện của use case:

- Actor có quyền thực hiện không?
- Tài nguyên có tồn tại không?
- Dữ liệu tham chiếu đã được tải chưa?
- Transaction boundary và expected version là gì?
- Sau commit cần trả kết quả nào?

Application không nên thay thế invariant của Aggregate bằng các câu lệnh điều kiện rải rác.

### Infrastructure và database

Database constraint bảo vệ những điều kiện cần đúng ngay cả khi có nhiều instance hoặc nhiều tiến trình ghi đồng thời:

- Unique constraint.
- Foreign key.
- Check constraint.
- Optimistic version.
- Atomic conditional update.

Các constraint này bổ sung cho domain model, không thay thế việc diễn đạt quy tắc bằng ngôn ngữ nghiệp vụ.

## 7. Ví dụ: hợp đồng của Aggregate Inventory

Giả sử Inventory quản lý số lượng hàng tại một kho. Mô hình có:

- onHand: số lượng thực có trong kho.
- reserved: số lượng đã giữ cho các đơn.
- available: số lượng có thể tiếp tục giữ.

Các invariant:

\[
onHand \ge 0
\]

\[
reserved \ge 0
\]

\[
reserved \le onHand
\]

\[
available = onHand - reserved
\]

Precondition của reserve(quantity):

\[
quantity > 0 \land quantity \le available
\]

Postcondition khi thành công:

\[
reserved' = reserved + quantity
\]

\[
available' = available - quantity
\]

Frame condition:

- onHand không đổi.
- productId và warehouseId không đổi.
- Các reservation đã tồn tại không bị thay đổi.

### Triển khai domain model

~~~java
public final class Inventory {
    private final ProductId productId;
    private final WarehouseId warehouseId;
    private int onHand;
    private int reserved;

    public Inventory(
            ProductId productId,
            WarehouseId warehouseId,
            int onHand,
            int reserved
    ) {
        this.productId = Objects.requireNonNull(productId);
        this.warehouseId = Objects.requireNonNull(warehouseId);

        if (onHand < 0 || reserved < 0 || reserved > onHand) {
            throw new IllegalArgumentException(
                    "Invalid inventory state"
            );
        }

        this.onHand = onHand;
        this.reserved = reserved;
    }

    public int available() {
        return onHand - reserved;
    }

    public int onHand() {
        return onHand;
    }

    public int reserved() {
        return reserved;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (quantity > available()) {
            throw new InsufficientStock();
        }

        reserved += quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (quantity > reserved) {
            throw new IllegalStateException(
                    "Cannot release more than reserved"
            );
        }

        reserved -= quantity;
    }
}
~~~

Constructor bảo vệ invariant ban đầu. Các behavior công khai bảo vệ precondition và giữ invariant sau mỗi thay đổi.

Trong ví dụ đơn giản, reserved += quantity không thể vượt onHand vì precondition đã kiểm tra quantity <= available(). Với hệ thống thật, cần bổ sung identity và lifecycle của Reservation, persistence, transaction và concurrency control.

### Kiểm chứng postcondition

Sau khi reserve(3) thành công:

- reserved mới bằng reserved cũ cộng 3.
- available mới bằng available cũ trừ 3.
- onHand không đổi.
- Invariant vẫn đúng.

Nếu reserve(3) thất bại do thiếu hàng, state phải không thay đổi.

## 8. Precondition của command và authorization

Không phải mọi điều kiện đầu vào đều là domain invariant. Một use case có thể yêu cầu actor phải có quyền thao tác trên tài nguyên.

Ví dụ CancelOrderCommand có thể cần:

- Order ID hợp lệ.
- Actor đã xác thực.
- Actor có quyền hủy đơn của customer đó.
- Đơn chưa được giao.
- Lý do hủy đáp ứng policy.

Phân loại:

- Order ID có cấu trúc hợp lệ: boundary hoặc Value Object.
- Actor đã xác thực: authentication layer.
- Actor có quyền hủy order: application authorization policy.
- Đơn có thể hủy ở trạng thái hiện tại: domain behavior.
- Lý do hủy là bắt buộc theo chính sách: application/domain tùy ownership.

Không nên gom mọi điều kiện vào một method validate() khổng lồ. Hãy đặt từng điều kiện ở nơi chịu trách nhiệm và đảm bảo use case không thể bỏ qua các kiểm tra có ý nghĩa bảo mật hoặc nghiệp vụ.

## 9. Hợp đồng cho state transition

Một Entity hoặc Aggregate thường có state machine. Hợp đồng của từng hành vi cần xác định trạng thái nguồn, trạng thái đích và điều kiện chuyển đổi.

Ví dụ Order:

    DRAFT
      | confirm
      v
    CONFIRMED
      | ship
      v
    SHIPPED
      | deliver
      v
    DELIVERED

Một số chuyển đổi có thể bị từ chối:

    DRAFT -> DELIVERED
    CANCELLED -> SHIPPED
    DELIVERED -> CANCELLED

Bảng hợp đồng:

| Hành vi | Precondition | Postcondition |
|---|---|---|
| confirm() | Draft, có ít nhất một line, dữ liệu giá đã chốt | Confirmed, có confirmedAt |
| ship() | Confirmed, fulfillment đã sẵn sàng | Shipped, có shippedAt |
| deliver() | Shipped, có bằng chứng giao hàng hợp lệ | Delivered, có deliveredAt |
| cancel(reason) | Chưa Shipped hoặc Delivered, lý do hợp lệ | Cancelled, lưu reason và cancelledAt |

Aggregate phải kiểm soát các chuyển đổi này. Không nên expose setter cho status để caller tự quyết định trạng thái đích.

### State transition có thể phát Domain Event

Nếu confirm() thành công, Aggregate có thể ghi nhận OrderConfirmed. Event chỉ được publish sau khi transaction lưu Aggregate commit, thường qua outbox nếu cần bảo đảm không mất thông điệp.

Postcondition của domain method có thể là event đã được ghi nhận trong Aggregate; postcondition của use case có thể bao gồm event được lưu bền vững cùng thay đổi. Hai cam kết này thuộc hai phạm vi khác nhau.

## 10. Hợp đồng và lỗi nghiệp vụ

Khi precondition không được đáp ứng, hệ thống cần một cách từ chối rõ ràng.

Có thể dùng exception có ý nghĩa domain:

~~~java
if (quantity > available()) {
    throw new InsufficientStock();
}
~~~

Hoặc trả về kiểu kết quả:

~~~java
public sealed interface ReserveResult {
    record Reserved(ReservationId id) implements ReserveResult {}
    record Rejected(ReservationFailure reason) implements ReserveResult {}
}
~~~

Chọn exception hay Result tùy convention và semantics của ứng dụng. Điều quan trọng là:

- Business rejection không bị nhầm với lỗi hạ tầng.
- Caller biết hành vi đã thành công hay bị từ chối.
- State không bị thay đổi một phần ngoài hợp đồng.
- Không trả stack trace hoặc chi tiết nội bộ ra API.
- Các lỗi quan trọng có mã ổn định để client và vận hành xử lý.

Một postcondition của nhánh rejected có thể là state không đổi. Nếu thao tác có thể thực hiện một số bước trước khi thất bại, cần transaction hoặc thiết kế workflow để bảo đảm kết quả đúng như cam kết.

## 11. Hợp đồng giữa Application Service và Repository

Repository cũng có contract, không chỉ là một API truy cập dữ liệu.

Ví dụ:

findById(id):

- Nếu tìm thấy, trả về Aggregate tương ứng với identity.
- Nếu không có, trả về empty hoặc một lỗi đã quy ước.
- Không trả về Aggregate thuộc identity khác.

save(aggregate):

- Lưu state của Aggregate theo identity.
- Tuân thủ optimistic version nếu có.
- Thay đổi được commit trong transaction của use case.
- Nếu conflict, trả lỗi concurrency rõ ràng.
- Không âm thầm ghi đè state mới hơn.

Một contract quan trọng là semantics của save() không nên bị hiểu nhầm là dữ liệu đã commit nếu ORM mới chỉ flush. Application cần biết khi nào transaction hoàn tất để công bố kết quả hoặc phát event.

### Repository contract test

Nếu có nhiều implementation, ví dụ in-memory repository và SQL repository, contract test có thể xác nhận cả hai tuân thủ cùng semantics:

- Save rồi load trả lại Aggregate tương đương.
- Không tìm thấy trả đúng kết quả.
- Version conflict không ghi đè dữ liệu.
- Query không làm lộ Aggregate khác.
- Transaction rollback không để lại thay đổi đã thất bại.

Contract test giúp thay implementation persistence mà không làm thay đổi hành vi được application kỳ vọng.

## 12. Hợp đồng ở ranh giới API

API request có thể được kiểm tra trước khi tạo Command:

- Field bắt buộc có mặt.
- Chuỗi có độ dài hợp lệ.
- Kiểu dữ liệu đúng.
- Số lượng dương.
- Header và version đúng format.

Nhưng validation ở API không phải hợp đồng cuối cùng của domain. Client có thể bỏ qua validation, request có thể đến từ message consumer hoặc batch job, và state có thể thay đổi sau khi request được kiểm tra.

Một luồng phù hợp:

    HTTP DTO
       |
       v
    Structural validation
       |
       v
    Command
       |
       v
    Application authorization
       |
       v
    Aggregate precondition + invariant
       |
       v
    Persistence constraint / concurrency
       |
       v
    Application result
       |
       v
    HTTP response

Mỗi lớp bảo vệ một loại hợp đồng. Không nên lặp cùng một quy tắc ở mọi nơi nếu không có lý do, nhưng điều kiện có thẩm quyền phải được bảo vệ tại nơi có thể kiểm soát nó.

## 13. Hậu điều kiện với transaction và side effect

Postcondition cần phân biệt kết quả trong bộ nhớ với kết quả đã được commit.

Ví dụ, application gọi:

    order.confirm();
    orders.save(order);

Sau khi save() trả về, transaction có thể chưa commit. Nếu commit thất bại, không thể tuyên bố use case đã thành công.

Với side effect ngoài database như gửi email hoặc publish message, postcondition cũng cần xác định thời điểm:

- Domain method ghi nhận event.
- Transaction lưu Aggregate và outbox record.
- Database commit thành công.
- Publisher gửi event.
- Consumer xử lý event.

Một use case có thể bảo đảm “đã ghi nhận yêu cầu gửi thông báo” sau commit, nhưng không thể bảo đảm email đã đến inbox người nhận chỉ vì outbox record được commit.

Hãy mô tả chính xác mức cam kết của từng bước. Điều này đặc biệt quan trọng với payment, shipping, notification và workflow nhiều context.

## 14. Invariant và concurrency

Một precondition có thể đúng khi đọc state nhưng không còn đúng khi ghi.

Ví dụ, Inventory có 5 đơn vị khả dụng. Hai request cùng đọc số lượng 5 và mỗi request muốn giữ 4. Nếu cả hai cùng kiểm tra trong bộ nhớ rồi ghi, tổng lượng giữ có thể vượt tồn.

Vì vậy, invariant cần được bảo vệ tại thời điểm commit bằng cơ chế phù hợp:

- Optimistic locking với version.
- Pessimistic locking trên tài nguyên cần bảo vệ.
- Atomic conditional update.
- Unique/check constraint.
- Serialize command theo identity.
- Transaction isolation phù hợp.

Ví dụ một conditional update:

~~~sql
UPDATE inventory
SET reserved = reserved + :quantity,
    version = version + 1
WHERE product_id = :productId
  AND warehouse_id = :warehouseId
  AND on_hand - reserved >= :quantity
  AND version = :expectedVersion;
~~~

Nếu số dòng được cập nhật bằng 0, điều kiện không còn đúng hoặc version đã thay đổi. Application phải nạp state mới và quyết định lại, hoặc trả conflict.

Không nên chỉ kiểm tra precondition trong Java rồi cho rằng database sẽ giữ invariant khi có nhiều request đồng thời.

## 15. Invariant qua nhiều Aggregate và Bounded Context

Một invariant nằm trong một Aggregate có thể được bảo vệ bằng behavior của root và transaction local. Nhưng một số quy tắc liên quan nhiều Aggregate hoặc nhiều context.

Ví dụ:

- Một customer không được có quá 3 reservation đang hoạt động.
- Tổng chi tiêu trong kỳ không vượt hạn mức tín dụng.
- Một mã coupon chỉ được sử dụng tối đa N lần.
- Một ghế trong chuyến bay không được bán cho hai booking.

Cần xác định nơi sở hữu quyết định và cách bảo vệ cạnh tranh. Có thể dùng một Aggregate chuyên trách quota/reservation, atomic counter, unique constraint hoặc transaction phù hợp.

Khi quy tắc trải qua nhiều bounded context, không nên giả định một transaction phân tán sẽ giữ invariant toàn cục tức thời. Có thể cần reservation, workflow, saga và trạng thái trung gian.

Hợp đồng của một use case phân tán nên nói rõ:

- Khi nào yêu cầu được chấp nhận.
- Khi nào kết quả chỉ đang chờ.
- Điều kiện nào đánh dấu hoàn tất.
- Nếu một bước thất bại, có compensation nào.
- Khi nào người dùng cần thử lại hoặc xử lý thủ công.

## 16. Hợp đồng có thể kiểm chứng bằng automated test

Một hợp đồng chỉ hữu ích khi có cách xác nhận nó vẫn đúng sau thay đổi code.

Các lớp test có thể gồm:

| Loại test | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test Value Object | Kiểm tra invariant nội tại | Quantity không nhận số âm |
| Unit test Aggregate | Kiểm tra precondition/postcondition/invariant | Order không confirm khi không có line |
| Property-based test | Kiểm tra quy tắc trên nhiều dữ liệu | Tổng reserved không vượt onHand |
| State transition test | Kiểm tra hành vi theo state | Delivered không thể cancel |
| Repository contract test | Kiểm tra semantics persistence | Optimistic conflict không ghi đè |
| Integration test | Kiểm tra transaction và database constraint | Hai request cạnh tranh không vượt quota |
| API contract test | Kiểm tra input/output contract | Invalid request trả lỗi ổn định |

### Unit test cho Inventory

~~~java
class InventoryTest {
    @Test
    void reserveReducesAvailableAndIncreasesReserved() {
        Inventory inventory = new Inventory(
                new ProductId("P-1"),
                new WarehouseId("W-1"),
                10,
                2
        );

        inventory.reserve(3);

        assertEquals(5, inventory.available());
    }

    @Test
    void cannotReserveMoreThanAvailable() {
        Inventory inventory = new Inventory(
                new ProductId("P-1"),
                new WarehouseId("W-1"),
                10,
                8
        );

        assertThrows(
                InsufficientStock.class,
                () -> inventory.reserve(3)
        );

        assertEquals(2, inventory.available());
    }
}
~~~

Test thứ hai kiểm tra cả kết quả từ chối lẫn postcondition thất bại: available vẫn là 2 sau khi reserve bị từ chối.

### Kiểm tra invariant sau mỗi hành vi

Có thể tạo helper trong test:

~~~java
private void assertInventoryInvariant(Inventory inventory) {
    assertTrue(inventory.onHand() >= 0);
    assertTrue(inventory.reserved() >= 0);
    assertTrue(inventory.reserved() <= inventory.onHand());
    assertEquals(
            inventory.onHand() - inventory.reserved(),
            inventory.available()
    );
}
~~~

Nếu cần, expose các accessor chỉ đọc phù hợp. Không mở setter chỉ để test có thể sửa state tùy ý.

## 17. Property-based testing cho invariant

Unit test thường kiểm tra một số ví dụ cụ thể. Property-based testing tạo nhiều input để kiểm tra một tính chất tổng quát.

Ví dụ property:

- Với mọi onHand >= 0 và 0 <= reserved <= onHand, available() luôn bằng onHand - reserved.
- Với mọi quantity > available, reserve(quantity) bị từ chối và state không đổi.
- Với mọi quantity hợp lệ, sau reserve, reserved' <= onHand.
- Sau reserve rồi release cùng một quantity, state trở về giá trị ban đầu nếu không có thao tác xen giữa.

Có thể dùng thư viện như jqwik hoặc QuickTheories trong Java. Ý tưởng không phụ thuộc thư viện cụ thể.

Property test hữu ích khi:

- Có nhiều biên số học.
- Nhiều chuỗi hành vi có thể xảy ra.
- Invariant liên quan đến nhiều field.
- Muốn tìm các tổ hợp input mà ví dụ thủ công chưa bao phủ.

Không nên chỉ viết property phản ánh đúng implementation. Hãy diễn đạt property từ quy tắc nghiệp vụ và kiểm tra nó độc lập.

## 18. Model-based testing cho state machine

Với Aggregate có nhiều trạng thái, có thể mô hình hóa tập hành vi hợp lệ và bất hợp lệ.

Ví dụ Order:

| State hiện tại | Command | Kết quả |
|---|---|---|
| Draft | Confirm | Confirmed nếu có line |
| Draft | Ship | Rejected |
| Confirmed | Ship | Shipped nếu fulfillment sẵn sàng |
| Shipped | Deliver | Delivered khi có bằng chứng |
| Delivered | Cancel | Rejected |
| Cancelled | Confirm | Rejected |

Model-based test có thể sinh chuỗi command và so sánh state thực tế với model kỳ vọng. Điều này giúp phát hiện lỗi chỉ xuất hiện sau một chuỗi hành vi dài.

Một test đơn lẻ deliveredOrderCannotBeCancelled chưa đủ nếu có đường chuyển trạng thái khác khiến order rơi vào state không hợp lệ trước đó.

## 19. Contract test và kiểm thử ở nhiều implementation

Khi application có nhiều adapter, ví dụ REST API, message consumer và batch import, tất cả đều cần tuân thủ cùng application/domain contract.

Một command có thể đến từ nhiều nguồn:

    REST API --------\
    Message Consumer --+--> Application Command --> Domain
    Batch Import -----/

Không nên chỉ kiểm tra precondition trong controller. Handler và Aggregate cần bảo vệ điều kiện nghiệp vụ bất kể nguồn gọi.

Contract test có thể xác minh:

- Adapter map đúng dữ liệu vào command.
- Actor/context được truyền đúng.
- Business rejection không bị chuyển thành success.
- Retry không tạo side effect trùng.
- Version conflict được trả đúng.
- Postcondition được giữ sau commit.

## 20. Đừng dùng assert như cơ chế bảo vệ nghiệp vụ duy nhất

Trong Java, assert có thể bị tắt khi chạy nếu JVM không bật assertions. Vì vậy không nên dùng nó để bảo vệ input hoặc invariant quan trọng trong production.

Ví dụ:

    assert quantity > 0;

Nếu assertions bị tắt, điều kiện này không bảo vệ hệ thống.

Dùng validation rõ ràng:

    if (quantity <= 0) {
        throw new InvalidQuantity(quantity);
    }

Assertion vẫn hữu ích cho giả định nội bộ hoặc kiểm tra trong môi trường phát triển, nhưng business contract phải được thực thi bằng logic luôn hoạt động, Value Object, Aggregate và database constraint phù hợp.

## 21. Tránh hợp đồng quá yếu hoặc quá chặt

Một hợp đồng quá yếu không bảo vệ được quy tắc. Một hợp đồng quá chặt có thể ngăn thay đổi hợp lệ trong tương lai.

### Quá yếu

- Cho phép setter sửa status bất kỳ.
- Chỉ kiểm tra dữ liệu ở UI.
- Không kiểm tra concurrency.
- Không xác định state sau khi command thất bại.
- Không có test cho invariant.

### Quá chặt

- Tạo precondition cho mọi chi tiết triển khai không thuộc nghiệp vụ.
- Bắt caller cung cấp field mà hệ thống có thể xác định an toàn.
- Đóng cứng enum hoặc trạng thái khiến mở rộng hợp lệ trở nên khó khăn.
- Đưa giả định về database hoặc framework vào domain contract.
- Bắt buộc thứ tự gọi method không có ý nghĩa nghiệp vụ.

Hợp đồng nên bảo vệ điều quan trọng đối với domain, đồng thời cho phép thay đổi implementation khi hành vi quan sát được vẫn đúng.

## 22. Hợp đồng và khả năng tương thích khi tiến hóa mô hình

Khi thay đổi một Aggregate hoặc API, cần xác định hợp đồng cũ có còn được giữ không.

Ví dụ, một phiên bản mới của Order bổ sung trạng thái ON_HOLD. Điều này có thể ảnh hưởng:

- Những command nào được phép ở trạng thái mới.
- Query và response DTO.
- Event consumer.
- Báo cáo.
- Workflow.
- Test state transition.

Một thay đổi có thể giữ nguyên precondition cho confirm() nhưng thay đổi postcondition hoặc frame condition. Khi đó cần xem đây có phải breaking change đối với caller hay consumer không.

Một số kỹ thuật hỗ trợ tiến hóa:

- Characterization test ghi lại hành vi hiện tại trước refactor.
- Contract test cho API và integration event.
- Versioning event/schema.
- Migration có kiểm soát.
- Feature flag khi chuyển đổi hành vi.
- Deprecation period cho contract bên ngoài.

Không nên thay đổi ý nghĩa của một postcondition mà không cập nhật bên gọi và hợp đồng tích hợp liên quan.

## 23. Ghi nhận và quan sát vi phạm hợp đồng

Một số vi phạm cần bị từ chối ngay; một số sai lệch dữ liệu lịch sử cần được ghi nhận để điều tra.

Ví dụ:

- Quantity âm: từ chối command.
- Order không được phép cancel: trả business rejection.
- Optimistic version conflict: trả conflict để reload hoặc retry có kiểm soát.
- Database constraint vi phạm: ghi log kỹ thuật và ánh xạ lỗi phù hợp.
- Dữ liệu legacy không thỏa invariant mới: quarantine hoặc chạy migration/reconciliation.

Không nên log toàn bộ payload nhạy cảm. Log cần có Aggregate ID, command type, correlation ID, version và reason code khi phù hợp.

Metric hữu ích:

- Số lần business precondition bị từ chối theo reason code.
- Số optimistic conflict.
- Số invariant violation từ dữ liệu persistence.
- Số message bị quarantine.
- Số lần retry thất bại.
- Số lỗi contract theo API version.

Các metric này giúp nhận ra hợp đồng đang bị vi phạm thường xuyên do UI, tích hợp hoặc quy trình nghiệp vụ chưa phù hợp.

## 24. Quy trình thiết kế hợp đồng cho một hành vi

Khi thêm hoặc thay đổi behavior trong domain model, có thể làm theo các bước:

1. **Mô tả ý định:** hành vi nghiệp vụ nào cần được hỗ trợ?
2. **Xác định trạng thái đầu:** object/Aggregate đang ở state nào?
3. **Liệt kê precondition:** điều kiện nào phải đúng trước khi chạy?
4. **Xác định authority:** layer hoặc context nào có thể xác minh từng điều kiện?
5. **Liệt kê invariant:** state nào phải luôn hợp lệ?
6. **Mô tả postcondition:** điều gì được bảo đảm khi thành công?
7. **Mô tả failure contract:** khi bị từ chối, state và side effect ra sao?
8. **Mô tả frame condition:** dữ liệu nào không được thay đổi?
9. **Xác định concurrency:** điều kiện nào cần được kiểm tra nguyên tử tại thời điểm ghi?
10. **Viết executable test:** unit, property, state transition, repository và integration test phù hợp.
11. **Rà caller:** mọi adapter/use case có còn đáp ứng hợp đồng không?
12. **Theo dõi tiến hóa:** thay đổi nào là breaking change và cần migration/versioning?

## 25. Checklist tiền điều kiện, hậu điều kiện và bất biến

Trước khi hoàn thiện một behavior, hãy kiểm tra:

- Precondition đã được viết rõ bằng ngôn ngữ nghiệp vụ chưa?
- Mỗi điều kiện được kiểm tra ở đúng layer có thẩm quyền chưa?
- Aggregate có tự bảo vệ precondition quan trọng không?
- Invariant có được bảo vệ ở mọi đường thay đổi state không?
- Value Object có ngăn tạo giá trị không hợp lệ không?
- Postcondition mô tả kết quả cụ thể khi thành công chưa?
- Failure contract có xác định state và side effect không?
- Frame condition có nói rõ dữ liệu không được thay đổi không?
- State transition có được kiểm soát qua behavior thay vì setter không?
- Database constraint có bảo vệ uniqueness và concurrency cần thiết không?
- Có race condition giữa kiểm tra và ghi không?
- Repository contract có semantics rõ về save, commit và version không?
- API/message adapter có cùng tuân thủ application contract không?
- Có unit test cho precondition, postcondition và invariant không?
- Có property-based hoặc model-based test khi quy tắc đủ phức tạp không?
- Có kiểm tra khả năng tương thích khi thay đổi contract không?
- Vi phạm có reason code, log và metric phù hợp không?

## 26. Kết luận

Tiền điều kiện, hậu điều kiện và bất biến là cách diễn đạt hợp đồng của một hành vi. Precondition xác định điều kiện để bắt đầu; postcondition mô tả kết quả được bảo đảm khi thành công; invariant xác định trạng thái luôn phải hợp lệ. Khi được đặt đúng phạm vi trong Value Object, Entity, Aggregate, Application Layer và persistence, chúng làm rõ trách nhiệm và ngăn state không hợp lệ lan vào hệ thống.

Trong DDD, Aggregate Root phải bảo vệ invariant của Aggregate; Application Layer điều phối điều kiện của use case; Repository và database hỗ trợ tính nhất quán khi lưu; automated tests kiểm chứng các cam kết qua nhiều tình huống. Với hệ thống có concurrency hoặc nhiều Bounded Context, cần kiểm tra hợp đồng tại thời điểm ghi và xác định rõ kết quả bất đồng bộ.

Một hợp đồng tốt vừa đủ chặt để bảo vệ quy tắc nghiệp vụ, vừa đủ rõ để đội ngũ có thể thay đổi implementation mà không làm đổi hành vi đã cam kết. Khi các điều kiện trở thành executable contracts và test có ý nghĩa, thiết kế sẽ dễ tiến hóa hơn mà vẫn giữ được tính đúng đắn của mô hình miền.
