# Tái cấu trúc mô hình khi xuất hiện quy tắc thay đổi hoặc tình huống ngoại lệ

Một mô hình Domain-Driven Design không phải bản chụp cố định của nghiệp vụ. Nó là cách diễn đạt hiện tại về các khái niệm, quy tắc, trách nhiệm và ranh giới mà đội phát triển cùng chuyên gia nghiệp vụ đã hiểu. Khi một quy tắc thay đổi hoặc một ngoại lệ quan trọng xuất hiện, câu hỏi cần đặt ra không chỉ là thêm một nhánh điều kiện. Cần xem sự thay đổi đang cho thấy mô hình hiện tại đã đặt sai khái niệm, sai quyền sở hữu, sai ranh giới nhất quán hay chưa.

Trong Domain-Driven Design, strategic design và tactical design liên kết ở điểm này. Bounded Context cho biết mô hình nào chịu trách nhiệm cho một ngôn ngữ và năng lực nghiệp vụ; Aggregate bảo vệ những bất biến cần được giữ cùng nhau; Entity và Value Object diễn đạt trạng thái có ý nghĩa; Policy hoặc Specification diễn đạt quy tắc có thể thay đổi; Domain Event ghi nhận sự kiện đã xảy ra; Application Service điều phối use case; Repository cung cấp điểm truy cập tới Aggregate; lớp tích hợp dịch mô hình giữa các context.

Bài này dùng một tình huống xuyên suốt để thực hành cách nhận diện tín hiệu, xác định chủ sở hữu của quy tắc, chọn điểm tái cấu trúc và kiểm chứng mô hình sau thay đổi.

## 1. Khi nào một thay đổi nghiệp vụ là tín hiệu tái cấu trúc

Không phải mọi yêu cầu mới đều đòi hỏi đổi mô hình. Một số thay đổi chỉ là thêm dữ liệu hoặc thay đổi cách hiển thị. Tái cấu trúc trở nên cần thiết khi quy tắc mới làm lộ ra một khái niệm đang bị ẩn hoặc một trách nhiệm đang nằm sai chỗ.

Các tín hiệu thường gặp:

| Tín hiệu | Câu hỏi mô hình cần đặt ra | Hướng xem xét đầu tiên |
|---|---|---|
| Cùng một quy tắc xuất hiện ở nhiều service | Ai thực sự sở hữu quy tắc? | Entity, Aggregate hoặc Domain Policy |
| Nhiều primitive truyền cùng nhau | Chúng có một ý nghĩa nghiệp vụ riêng không? | Value Object |
| Một thao tác phải cập nhật nhiều object để giữ một bất biến | Các object này có thật sự phải nhất quán tức thời không? | Aggregate boundary |
| Một Aggregate ngày càng có nhiều nhánh ngoại lệ | Có policy hoặc concept mới bị ẩn không? | Policy, Specification hoặc sub-concept |
| Controller/Application Service chứa nhiều if nghiệp vụ | Ai sở hữu quyết định này? | Đưa behavior về domain model |
| Quy tắc phụ thuộc vào context khác | Có đang làm rò rỉ mô hình giữa các context không? | Domain Event, ACL hoặc Application Process |
| Một quy tắc thay đổi thường xuyên trong khi phần còn lại ổn định | Phần biến đổi có cần tách khỏi phần ổn định không? | Policy/Strategy |
| Một ngoại lệ lặp lại nhiều lần | Ngoại lệ có phải một trạng thái hoặc workflow hợp lệ không? | State, Policy hoặc Process |
| Cùng tên nhưng hai đội hiểu khác nhau | Có phải đang dùng shared model không phù hợp? | Bounded Context |
| Transaction ngày càng rộng | Ranh giới nhất quán có đang quá lớn không? | Aggregate boundary |
| Một thay đổi nhỏ phải sửa nhiều context | Coupling đang nằm ở đâu? | Context Map và contract |

Một quy tắc tốt để bắt đầu là mô tả nó bằng một câu hoàn chỉnh trong ngôn ngữ nghiệp vụ:

> Khi điều kiện X xảy ra, chủ thể Y được phép hoặc phải thực hiện hành động Z, với điều kiện bất biến Q vẫn đúng.

Nếu không thể nói câu này rõ ràng, việc sửa code thường sẽ đi trước việc hiểu mô hình.

## 2. Phân biệt thay đổi dữ liệu với thay đổi mô hình

Giả sử yêu cầu chỉ thêm customerNote để hiển thị cho nhân viên. Đây có thể chỉ là thay đổi thuộc tính.

Ngược lại, nếu yêu cầu là:

> Đơn đã thanh toán chỉ được thay địa chỉ giao hàng trước khi kho bắt đầu đóng gói.

Quy tắc này có ít nhất ba khái niệm:

- trạng thái của Order;
- trạng thái của Fulfillment;
- điều kiện cho phép thay đổi Delivery Address.

Nếu đặt toàn bộ điều kiện vào một setter như setDeliveryAddress, mô hình khó cho biết tại sao thao tác được phép hoặc bị từ chối. Quy tắc có ý nghĩa hơn khi được diễn đạt thành behavior.

Ví dụ Java:

    public void changeDeliveryAddress(
        DeliveryAddress newAddress,
        FulfillmentStatus fulfillmentStatus
    ) {
        if (status.isPaid() && !fulfillmentStatus.isPackingStarted()) {
            this.deliveryAddress = newAddress;
            return;
        }

        if (!status.isPaid()) {
            this.deliveryAddress = newAddress;
            return;
        }

        throw new DomainRuleViolation(
            "Delivery address can no longer be changed"
        );
    }

Ví dụ này vẫn còn một vấn đề: Order đang biết trực tiếp về FulfillmentStatus. Nếu Fulfillment thuộc một Bounded Context khác, việc truyền object hoặc trạng thái của context kia vào Aggregate có thể làm mô hình bị kéo qua ranh giới.

Đây là lúc cần phân biệt hai câu hỏi:

1. Quy tắc có phải invariant của Order không?
2. Dữ liệu cần để quyết định có thuộc cùng consistency boundary không?

Nếu câu trả lời cho câu thứ hai là không, không nên vội mở rộng Aggregate chỉ để làm cho một use case thuận tiện.

## 3. Tình huống thực hành: Order thay đổi khi xuất hiện ngoại lệ

Giả sử một hệ thống bán hàng có các context:

    Customer
        |
        v
    Ordering -----> Payment
        |
        +---------> Inventory
        |
        +---------> Fulfillment

Trong Ordering Context, mô hình ban đầu có:

    Order
     ├── OrderId
     ├── CustomerId
     ├── OrderLines
     ├── OrderStatus
     ├── TotalMoney
     └── ShippingAddress

Các quy tắc ban đầu:

1. Order phải có ít nhất một dòng hàng khi được submit.
2. Số lượng mỗi dòng phải lớn hơn 0.
3. Order đã cancelled không thể submit.
4. Tổng tiền không được âm.
5. Order đã submitted không được thêm hoặc xoá dòng.

Mô hình này có thể đủ cho giai đoạn đầu.

Sau đó nghiệp vụ bổ sung:

1. Khách VIP được sửa một số thông tin sau khi submit.
2. Một số mặt hàng cần giữ chỗ theo lô hàng.
3. Nếu kho không đủ một mặt hàng, Order có thể chuyển sang WAITING_STOCK.
4. Một số Order được phép giao một phần.
5. Nhân viên có thể phát hành hoàn tiền trong một trường hợp ngoại lệ.
6. Một chiến dịch khuyến mại có điều kiện thay đổi theo từng mùa.

Sáu yêu cầu này không cùng loại. Nếu tất cả được đưa vào Order, Aggregate sẽ trở thành nơi chứa mọi khái niệm của hệ thống.

Điểm quan trọng là không hỏi "làm thế nào để nhét tất cả vào Order". Hãy hỏi "khái niệm mới nào đang xuất hiện?"

| Quy tắc mới | Khái niệm có thể cần xuất hiện |
|---|---|
| VIP được sửa sau submit | Customer Segment hoặc Order Change Policy |
| Giữ chỗ theo lô | Stock Reservation trong Inventory |
| Chờ hàng | Order lifecycle / fulfillment process |
| Giao một phần | Fulfillment / Shipment |
| Hoàn tiền ngoại lệ | Refund Policy hoặc Payment workflow |
| Khuyến mại thay đổi theo mùa | Pricing/Promotion Policy |

Đây là khác biệt giữa thêm điều kiện và tái cấu trúc mô hình.

## 4. Bắt đầu từ Ubiquitous Language

Trước khi sửa class, hãy xác định câu chữ mà chuyên gia nghiệp vụ dùng để mô tả tình huống.

Ví dụ, nhóm có thể nói:

> Order submitted rồi vẫn có thể thay đổi địa chỉ nếu kho chưa bắt đầu đóng gói.

Sau khi thảo luận, nhóm nhận ra "submitted" và "packing started" thuộc hai vòng đời khác nhau. Khi đó có thể thống nhất:

- Ordering quyết định Order có đang cho phép chỉnh sửa hay không.
- Fulfillment quyết định đơn đã bắt đầu đóng gói hay chưa.
- Hai context trao đổi một fact hoặc một trạng thái được công bố theo contract.

Tên gọi trong code nên phản ánh quyết định này.

Một API như updateAnything che giấu ngôn ngữ nghiệp vụ.

API như sau cho thấy behavior:

    order.changeDeliveryAddress(address);
    order.submit();
    order.cancel(reason);

Nếu rule thay đổi thành:

> Sau khi đóng gói bắt đầu, chỉ nhân viên có quyền đặc biệt mới được đổi địa chỉ.

thì mô hình có thể cần thêm một khái niệm về authorization hoặc policy. Đừng tự động biến quyền đặc biệt thành một boolean như forceChange nếu boolean đó không có ý nghĩa trong ngôn ngữ nghiệp vụ.

## 5. Xác định loại quy tắc trước khi chọn nơi sửa

Một quy tắc có thể thuộc nhiều loại. Phân loại giúp tránh việc đặt mọi logic vào Entity hoặc Application Service.

### 5.1. Invariant của Value Object

Nếu quy tắc chỉ phụ thuộc vào giá trị của chính nó, Value Object thường là nơi phù hợp.

Ví dụ:

    public record Money(BigDecimal amount, Currency currency) {

        public Money {
            if (amount == null || currency == null) {
                throw new IllegalArgumentException("Money is incomplete");
            }
            if (amount.scale() > 2) {
                throw new IllegalArgumentException("Money has too many decimals");
            }
        }

        public Money add(Money other) {
            requireSameCurrency(other);
            return new Money(amount.add(other.amount), currency);
        }

        private void requireSameCurrency(Money other) {
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currency mismatch");
            }
        }
    }

Nếu rule "địa chỉ giao hàng phải có quốc gia và mã bưu chính hợp lệ" chỉ phụ thuộc vào Address, đừng đặt nó vào Order.

### 5.2. Invariant của Entity

Nếu quy tắc phụ thuộc vào identity và lifecycle của một Entity, behavior nên nằm gần Entity.

    public void cancel(CancellationReason reason) {
        if (!status.canCancel()) {
            throw new DomainRuleViolation("Order cannot be cancelled");
        }

        status = OrderStatus.CANCELLED;
        cancellationReason = reason;
    }

### 5.3. Invariant của Aggregate

Nếu nhiều object phải thay đổi cùng nhau để đảm bảo một quy tắc tức thời, Aggregate boundary cần bao phủ chúng.

Ví dụ:

> Tổng phân bổ của các dòng Reservation không được vượt quá số lượng đã đặt.

Nếu Reservation và các allocation nằm trong cùng consistency boundary, root phải bảo vệ invariant đó.

### 5.4. Policy hoặc Specification

Nếu rule là một chính sách có thể thay đổi độc lập, hãy làm cho nó thành concept rõ ràng.

    public interface OrderChangePolicy {
        boolean canChangeAddress(
            Order order,
            ChangeContext context
        );
    }

Một implementation có thể là:

    public final class VipOrderChangePolicy
        implements OrderChangePolicy {

        @Override
        public boolean canChangeAddress(
            Order order,
            ChangeContext context
        ) {
            return order.customerSegment().isVip()
                && !context.fulfillment().packingStarted();
        }
    }

Tên VipOrderChangePolicy giúp cuộc thảo luận tập trung vào chính sách thay vì một chuỗi điều kiện.

Specification phù hợp khi cần diễn đạt một điều kiện có thể kiểm tra, kết hợp hoặc tái sử dụng:

    public interface Specification<T> {
        boolean isSatisfiedBy(T candidate);
    }

Có thể mô tả:

    EligibleForAddressChange
        = IsVip
          AND IsNotPacked
          AND HasAllowedAddress

Không nên tạo Specification cho mọi if. Chỉ tách khi rule có ý nghĩa nghiệp vụ, được tái sử dụng hoặc cần được đặt tên để làm rõ mô hình.

### 5.5. Domain Service

Nếu một quyết định nghiệp vụ thực sự cần nhiều object hoặc nguồn thông tin mà không có một Entity nào sở hữu tự nhiên, Domain Service có thể phù hợp.

Domain Service không nên trở thành "nơi chứa mọi logic vì service tiện hơn".

Một dấu hiệu tốt là tên service mang một động từ hoặc khái niệm nghiệp vụ cụ thể:

    public final class ShipmentAllocationService {

        public Allocation allocate(
            Order order,
            AvailableStock stock,
            AllocationPolicy policy
        ) {
            // domain decision
        }
    }

### 5.6. Application Service

Application Service điều phối:

    Load Aggregate
        ↓
    Invoke domain behavior
        ↓
    Save Aggregate
        ↓
    Publish resulting events

Nó có thể kiểm soát transaction, authorization và orchestration, nhưng không nên là nơi tập trung các quy tắc thuộc domain.

## 6. Ngoại lệ không phải lúc nào cũng là edge case

Một ngoại lệ có thể chỉ xảy ra 1% thời gian nhưng vẫn là khái niệm quan trọng.

Ví dụ:

> Order thông thường không được thay địa chỉ sau khi thanh toán, nhưng khách hàng có thể yêu cầu thay đổi nếu giao dịch đang ở trạng thái chưa capture.

Nếu đội gọi đây là "special case", code dễ thành:

    if (paid) {
        if (specialCase) {
            // ...
        } else {
            // ...
        }
    }

Nếu ngoại lệ có tên trong nghiệp vụ, hãy đặt tên cho nó.

Có thể xuất hiện:

    PaymentStatus
        ├── AUTHORIZED
        ├── CAPTURED
        ├── FAILED
        └── REFUND_PENDING

và policy:

    AddressChangePolicy
        ├── NormalOrderAddressChange
        └── AuthorizedPaymentAddressChange

Điều này làm cho ngoại lệ trở thành một phần có thể kiểm chứng của mô hình.

### 6.1. Phân biệt các loại "ngoại lệ"

| Loại | Ý nghĩa | Cách mô hình hóa |
|---|---|---|
| Business rejection | Yêu cầu không hợp lệ theo rule | Domain error/exception hoặc Result |
| State transition | Hành động chỉ hợp lệ ở một trạng thái | Explicit lifecycle |
| External failure | Hệ thống khác lỗi | Integration error/retry/process |
| Exceptional workflow | Một quy trình nghiệp vụ hợp lệ nhưng khác luồng chính | Policy/Process/Command |
| Concurrency conflict | Hai thao tác cùng tranh chấp state | Optimistic concurrency/locking |
| Unknown outcome | Không biết hệ thống ngoài đã xử lý chưa | Idempotency/reconciliation |

Gộp tất cả thành RuntimeException("Something went wrong") làm mất thông tin của domain.

## 7. Khi quy tắc thay đổi, hãy kiểm tra Aggregate boundary

Aggregate không phải nhóm object chỉ vì chúng có quan hệ với nhau. Nó là ranh giới trong đó những invariant cần được bảo vệ cùng nhau có thể được kiểm tra một cách nhất quán.

Giả sử ban đầu:

    Order
     ├── OrderLine
     └── Discount

Sau khi có rule:

> Mỗi Order chỉ được áp dụng một Promotion đang hoạt động.

Nếu Promotion chỉ cần được tra cứu và quyết định mức giảm, không nhất thiết phải đưa toàn bộ Promotion Aggregate vào Order.

Có thể dùng:

    Order
     ├── OrderLine
     └── AppliedPromotionId

    Promotion
     └── PromotionId

Order giữ identity của Promotion thay vì giữ object graph của Promotion.

Ngược lại, nếu rule là:

> Khi thêm OrderLine, số lượng line và tổng giá trị phải được cập nhật cùng transaction.

thì OrderLine có lý do mạnh để nằm trong Order Aggregate.

Một câu hỏi hữu ích:

> Nếu trạng thái A thay đổi mà trạng thái B tạm thời sai, nghiệp vụ có chấp nhận trạng thái đó không?

Nếu không chấp nhận, hãy xem A và B có cần cùng consistency boundary hay không.

Nếu chấp nhận, đừng mở Aggregate chỉ để tránh mọi eventual inconsistency.

## 8. Aggregate quá lớn cũng là một tín hiệu tái cấu trúc

Quy tắc mới đôi khi khiến đội mở rộng Aggregate liên tục:

    Order
     ├── Customer
     ├── Payment
     ├── Inventory
     ├── Shipment
     ├── Promotion
     ├── Invoice
     └── Notification

Object graph này có thể phản ánh quan hệ trong đời thực, nhưng không nhất thiết phản ánh consistency boundary.

Hậu quả:

- transaction lớn;
- nhiều dữ liệu phải load;
- lock hoặc optimistic conflict tăng;
- thay đổi một khái niệm kéo theo nhiều code;
- test khó cô lập;
- ownership không rõ.

Một hướng refactor thường là giữ các Aggregate riêng:

    Order Aggregate
        |
        +-- PaymentId --------> Payment Aggregate
        |
        +-- ReservationId ---> Inventory Aggregate
        |
        +-- ShipmentId ------> Shipment Aggregate
        |
        +-- PromotionId -----> Promotion Aggregate

Sau đó phối hợp bằng command, event hoặc process tùy semantics.

## 9. Một transaction muốn sửa nhiều Aggregate: đừng vội mở rộng

Khi một use case nói:

> Khi Order được submit, đồng thời phải tạo Reservation và Payment.

đây là một yêu cầu orchestration. Nó chưa chứng minh rằng Order, Reservation và Payment phải là một Aggregate.

Hãy hỏi:

1. Có invariant nào yêu cầu cả ba thay đổi atomically không?
2. Nếu Payment thành công nhưng Reservation thất bại thì nghiệp vụ xử lý thế nào?
3. Có trạng thái trung gian hợp lệ không?
4. Có thể retry không?
5. Có compensation không?
6. Context nào sở hữu từng state?

Nếu trạng thái trung gian được chấp nhận:

    Order SUBMITTED
        ↓
    Reservation PENDING
        ↓
    Payment PENDING
        ↓
    Order CONFIRMED

thì process có thể phù hợp hơn một transaction khổng lồ.

Nếu một rule thật sự yêu cầu:

> Không bao giờ được phát hành OrderConfirmed nếu Order chưa có ít nhất một Reservation đã giữ chỗ.

thì cần xác định nơi nào sở hữu invariant đó. Có thể đó là policy/process ở mức workflow, hoặc có thể model hiện tại đang thiếu một Aggregate mới. Câu trả lời phải đến từ nghiệp vụ, không phải từ việc ORM có thể join được bao nhiêu bảng.

## 10. Tái cấu trúc khi quy tắc thay đổi thường xuyên

Một dấu hiệu quan trọng là phần thay đổi thường xuyên bị trộn với phần ổn định.

Ví dụ phần ổn định:

    Order
        submit()
        cancel()

Phần biến đổi:

    discount rules
    eligibility rules
    delivery rules
    pricing rules

Nếu mỗi lần khuyến mại thay đổi đều phải sửa Order, có thể tách policy:

    public interface DiscountPolicy {
        Discount calculate(
            Order order,
            PricingContext context
        );
    }

Order giữ behavior ổn định:

    public void applyDiscount(Discount discount) {
        if (!status.canApplyDiscount()) {
            throw new DomainRuleViolation(
                "Discount cannot be applied"
            );
        }

        this.discount = discount;
    }

Policy chịu trách nhiệm tính toán:

    public final class SeasonalDiscountPolicy
        implements DiscountPolicy {

        @Override
        public Discount calculate(
            Order order,
            PricingContext context
        ) {
            if (!context.season().hasPromotion()) {
                return Discount.none();
            }

            if (!order.customerSegment().isEligible()) {
                return Discount.none();
            }

            return Discount.percent(
                context.season().discountPercent()
            );
        }
    }

Boundary quan trọng là policy quyết định mức giảm, còn Order quyết định discount có được áp dụng vào lifecycle của nó hay không.

## 11. Khi một ngoại lệ làm lộ ra trạng thái mới

Một ngoại lệ có thể cho thấy state machine hiện tại không đủ.

Ban đầu:

    DRAFT → SUBMITTED → CANCELLED

Sau đó xuất hiện:

> Order đã submitted nhưng kho chưa đủ hàng; khách có thể chờ hoặc huỷ.

Mô hình có thể cần:

    DRAFT
      ↓
    SUBMITTED
      ↓
    WAITING_STOCK
      ↓
    READY_TO_FULFILL
      ↓
    FULFILLED

và từ WAITING_STOCK có thể:

    WAITING_STOCK → CANCELLED

Không nên giấu state mới bằng cờ:

    boolean waitingForStock;

nếu state đó ảnh hưởng đến các hành vi khác.

Một enum có tên rõ ràng có thể đủ:

    public enum OrderStatus {
        DRAFT,
        SUBMITTED,
        WAITING_STOCK,
        READY_TO_FULFILL,
        FULFILLED,
        CANCELLED
    }

Nhưng nếu mỗi state có rất nhiều behavior riêng, có thể cần một model lifecycle rõ hơn. Đừng áp dụng State Pattern chỉ vì enum có nhiều giá trị; hãy để độ phức tạp của behavior dẫn dắt quyết định.

## 12. Domain Event khi thay đổi tạo ra hậu quả ở context khác

Khi một rule mới nói:

> Sau khi Order được confirmed, Fulfillment phải bắt đầu.

Ordering không nhất thiết phải gọi trực tiếp mọi hành vi của Fulfillment.

Order có thể phát ra:

    public record OrderConfirmed(
        OrderId orderId,
        CustomerId customerId
    ) {}

Application layer hoặc event publisher xử lý việc công bố event.

Fulfillment nhận fact:

    OrderConfirmed
        ↓
    Create Fulfillment

Điều này có ý nghĩa khi các context có lifecycle và consistency boundary riêng.

Một Domain Event nên diễn tả fact đã xảy ra:

    OrderConfirmed
    PaymentCaptured
    ReservationReleased
    ShipmentDispatched

tránh đặt event như command:

    ConfirmOrder
    CapturePayment
    StartShipment

Command là yêu cầu thực hiện hành động; event là thông tin hành động đã xảy ra.

### 12.1. Khi event không đủ

Nếu nghiệp vụ yêu cầu kết quả ngay lập tức:

> Không được xác nhận Order nếu kho không thể giữ chỗ.

thì gửi event bất đồng bộ rồi xác nhận Order trước có thể tạo ra trạng thái sai.

Có thể cần command đồng bộ:

    SubmitOrder
        ↓
    Inventory.reserve(...)
        ↓
    ReservationAccepted
        ↓
    Order.confirm()

Hoặc một workflow có trạng thái:

    Order.SUBMITTED
        ↓
    ReservationRequested
        ↓
    WAITING_STOCK
        ↓
    ReservationConfirmed
        ↓
    Order.CONFIRMED

Lựa chọn phụ thuộc vào consistency requirement, failure semantics và ngôn ngữ nghiệp vụ.

## 13. Khi thay đổi làm lộ ra Bounded Context mới

Một dấu hiệu mạnh là cùng một khái niệm bắt đầu có hai ý nghĩa.

Ví dụ Order trong Ordering có thể là:

    Order
    - customer intent
    - lines
    - price
    - cancellation

Trong Fulfillment lại là:

    FulfillmentOrder
    - warehouse assignment
    - package
    - picking
    - shipment

Nếu hai model liên tục cần truy cập field của nhau, context đang bị trộn.

Thay vì chia theo bảng, hãy chia theo model và ownership:

    Ordering Context
        Order
        OrderLine
            |
            | OrderConfirmed
            v
    Fulfillment Context
        FulfillmentOrder
        Package

Ordering không cần biết cấu trúc Package. Fulfillment không cần dùng Entity Order của Ordering làm model nội bộ.

## 14. Translation boundary khi mô hình ngoài không khớp

Giả sử Payment Provider trả:

    status = "captured"
    amount = 120000
    currency = "VND"
    risk_score = 12

Ordering không nên bắt đầu dùng trực tiếp các class của provider trong domain model.

Tạo adapter:

    public final class PaymentGatewayAdapter {

        public PaymentResult toDomain(
            PaymentProviderResponse response
        ) {
            return switch (response.status()) {
                case "captured" -> PaymentResult.captured(
                    Money.of(
                        response.amount(),
                        response.currency()
                    )
                );
                case "failed" -> PaymentResult.failed();
                default -> PaymentResult.pending();
            };
        }
    }

Nếu provider đổi captured thành succeeded, thay đổi được giới hạn ở translation boundary.

Đây cũng là cách bảo vệ Ubiquitous Language của context khỏi vocabulary của hệ thống ngoài.

## 15. Tái cấu trúc Repository khi model đã thay đổi

Khi Aggregate boundary thay đổi, Repository cũng cần được xem lại.

Repository nên diễn đạt nhu cầu của domain:

    public interface OrderRepository {
        Optional<Order> findById(OrderId id);
        void save(Order order);
    }

Nếu sau refactor repository có:

    findAllByCustomerAndStatusAndWarehouseAndPaymentStateAnd...

thì có thể persistence query đang trở thành nơi điều khiển domain behavior.

Các truy vấn đọc chuyên biệt có thể dùng read model hoặc query service riêng nếu use case không cần load Aggregate để thay đổi state.

Ví dụ:

    public interface OrderReadModel {
        OrderSummary findSummary(OrderId orderId);
    }

Không phải mọi truy vấn đều cần đi qua Aggregate. Nhưng mọi thay đổi cần bảo vệ invariant phải đi qua boundary phù hợp.

## 16. Tái cấu trúc persistence khi ngoại lệ làm lộ model

Một lỗi phổ biến là thêm cột để giải quyết mọi ngoại lệ:

    is_special_case
    is_vip_override
    is_manual_override
    is_stock_exception
    is_force_change

Sau vài lần thay đổi, domain model chỉ còn một tập boolean.

Một boolean chỉ phù hợp khi nó thực sự là một khái niệm boolean trong nghiệp vụ. Nếu nhiều cờ biểu diễn các trạng thái hoặc policy khác nhau, hãy tìm concept.

Ví dụ:

    manualOverride = true

có thể cần thành:

    ChangeAuthorization
    - grantedBy
    - reason
    - grantedAt
    - scope

Lúc đó dữ liệu có thể được kiểm tra và giải thích.

Persistence schema là cách lưu model, không phải lý do để model giữ nguyên hình dạng của bảng.

## 17. Tái cấu trúc theo từng bước nhỏ

Khi code hiện tại đã chạy production, không nên bắt đầu bằng việc viết lại toàn bộ domain.

Một trình tự an toàn:

    1. Ghi nhận rule mới bằng Ubiquitous Language
            ↓
    2. Viết scenario hiện tại và scenario mới
            ↓
    3. Xác định invariant / policy / lifecycle
            ↓
    4. Xác định owner hiện tại
            ↓
    5. Tìm nơi rule đang bị phân tán
            ↓
    6. Viết test mô tả behavior cần giữ
            ↓
    7. Tách concept mới
            ↓
    8. Chuyển behavior về owner
            ↓
    9. Cập nhật boundary / contract nếu cần
            ↓
    10. Di chuyển persistence và integration
            ↓
    11. Xoá đường code cũ
            ↓
    12. Kiểm tra lại scenario và invariants

Mỗi bước nên giữ hệ thống ở trạng thái có thể kiểm tra.

Nếu một refactor chỉ thay đổi cấu trúc code, behavior observable cần được giữ. Nếu yêu cầu nghiệp vụ cũng thay đổi, test phải phản ánh behavior mới và review cần phân biệt phần nào là refactor, phần nào là business change.

## 18. Chiến lược chuyển đổi từ model cũ sang model mới

Khi context lớn, có thể chuyển từng concept.

Ví dụ Order cũ có:

    public void changeAddress(Address address) {
        if (status == SUBMITTED && !specialCase) {
            throw new DomainRuleViolation(...);
        }
        this.address = address;
    }

Bước đầu:

    public void changeAddress(
        Address address,
        AddressChangePolicy policy
    ) {
        policy.check(this);
        this.address = address;
    }

Sau đó policy có thể trở thành dependency domain rõ ràng hoặc một concept được chọn bởi application layer.

Trong quá trình chuyển đổi, cần tránh giữ cả hai đường logic mà không có kế hoạch xoá đường cũ. Nếu legacy rule và new policy cùng chạy nhưng có thể cho kết quả khác nhau, hệ thống sẽ có hai nguồn sự thật.

## 19. Test là công cụ phát hiện model sai

Test không chỉ xác nhận implementation. Trong DDD, test scenario giúp kiểm tra mô hình có diễn đạt đúng quy tắc hay không.

### 19.1. Test invariant

    @Test
    void cannotCancelFulfilledOrder() {
        Order order = anOrder()
            .withStatus(OrderStatus.FULFILLED)
            .build();

        assertThrows(
            DomainRuleViolation.class,
            () -> order.cancel(
                CancellationReason.customerRequest()
            )
        );
    }

Tên test dùng ngôn ngữ nghiệp vụ.

### 19.2. Test ngoại lệ hợp lệ

    @Test
    void vipOrderMayChangeAddressBeforePacking() {
        Order order = aSubmittedVipOrder();
        ChangeContext context = beforePacking();

        order.changeDeliveryAddress(
            newAddress(),
            context
        );

        assertThat(order.deliveryAddress())
            .isEqualTo(newAddress());
    }

### 19.3. Test state transition

    @Test
    void orderWaitsForStockWhenReservationIsIncomplete() {
        Order order = submittedOrder();

        order.markWaitingForStock();

        assertThat(order.status())
            .isEqualTo(OrderStatus.WAITING_STOCK);
    }

### 19.4. Test context translation

Nếu Fulfillment nhận OrderConfirmed, test translation phải xác nhận chỉ contract cần thiết được đưa vào model.

    @Test
    void orderConfirmedCreatesFulfillmentRequest() {
        OrderConfirmed event =
            new OrderConfirmed(orderId, customerId);

        FulfillmentCommand command =
            translator.translate(event);

        assertThat(command.orderId())
            .isEqualTo(orderId);
    }

Không cần assert mọi field nội bộ của Ordering.

## 20. Concurrency cũng có thể làm lộ Aggregate boundary

Giả sử hai nhân viên cùng sửa Order.

Request A:

    quantity 2 → quantity 5

Request B:

    apply promotion

Nếu cả hai thay đổi cùng một Aggregate và rule phụ thuộc vào tổng quantity, version check có thể cần được bảo vệ.

Ví dụ optimistic locking:

    @Entity
    class OrderRecord {

        @Version
        private long version;
    }

Nếu conflict thường xuyên, đó có thể là tín hiệu Aggregate quá lớn hoặc use case đang gom các thay đổi không cần cùng consistency boundary.

Không nên tăng retry vô hạn để che một boundary sai.

## 21. Khi quy tắc thay đổi liên tục, hãy xem lại ownership

Một thay đổi lặp lại nhiều lần ở cùng một class có thể cho thấy class đó đang sở hữu một concept mà nó không nên sở hữu.

Ví dụ:

    Order
        ├── calculateTax()
        ├── calculateShipping()
        ├── calculateDiscount()
        ├── checkCredit()
        ├── allocateStock()
        └── chooseWarehouse()

Order có thể đang trở thành trung tâm của toàn bộ business process.

Có thể tách:

    Ordering
        └── Order

    Pricing
        └── PricingPolicy

    Shipping
        └── ShippingPolicy

    Credit
        └── CreditPolicy

    Inventory
        └── Reservation

    Fulfillment
        └── WarehouseAllocation

Mỗi context hoặc concept giữ phần logic mà nó có quyền quyết định.

## 22. Decision table cho lựa chọn tái cấu trúc

| Câu hỏi | Nếu có | Nếu không |
|---|---|---|
| Quy tắc chỉ phụ thuộc vào một giá trị? | Value Object | Xem tiếp |
| Quy tắc thuộc lifecycle của một Entity? | Entity behavior | Xem tiếp |
| Nhiều object phải nhất quán cùng transaction? | Aggregate boundary | Xem tiếp |
| Quy tắc có thể thay đổi độc lập? | Policy/Specification | Xem tiếp |
| Quyết định cần nhiều domain concept nhưng không có owner tự nhiên? | Domain Service | Xem tiếp |
| Chỉ điều phối nhiều bước? | Application Service/Process | Xem tiếp |
| Hậu quả thuộc context khác? | Event/Command/Process | Xem tiếp |
| Mô hình ngoài không khớp local language? | Translation/ACL | Xem tiếp |
| Query chỉ phục vụ đọc? | Read model/Query Service | Xem tiếp |
| Nhiều rule liên quan tới cùng lifecycle? | Xem state/workflow | Xem tiếp |

Bảng này là heuristic, không phải thuật toán. Một rule có thể liên quan nhiều pattern và cần quyết định dựa trên ngữ cảnh.

## 23. Một ví dụ refactor từ procedural code

Code ban đầu:

    public void submit(OrderDto dto) {
        if (dto.lines().isEmpty()) {
            throw new IllegalStateException("No lines");
        }

        if (dto.total().signum() < 0) {
            throw new IllegalStateException("Negative total");
        }

        if (dto.customerVip() && dto.discount() == null) {
            dto = applyVipDiscount(dto);
        }

        if (inventoryService.available(dto.lines())) {
            orderRepository.markSubmitted(dto.id());
            inventoryService.reserve(dto.lines());
            paymentService.capture(dto.payment());
            notificationService.sendSubmitted(dto.customerId());
        } else {
            orderRepository.markWaitingStock(dto.id());
        }
    }

Có nhiều loại logic bị trộn:

- validation của Order;
- discount policy;
- inventory decision;
- lifecycle;
- payment;
- notification;
- persistence.

Bước đầu, giữ behavior nhưng tách use case:

    public void submit(SubmitOrder command) {
        Order order = orderRepository.get(command.orderId());

        order.submit();

        orderRepository.save(order);
    }

Trong Order:

    public void submit() {
        if (lines.isEmpty()) {
            throw new DomainRuleViolation(
                "Order needs at least one line"
            );
        }

        if (total().isNegative()) {
            throw new DomainRuleViolation(
                "Order total cannot be negative"
            );
        }

        if (!status.canSubmit()) {
            throw new DomainRuleViolation(
                "Order cannot be submitted"
            );
        }

        status = OrderStatus.SUBMITTED;
        record(new OrderSubmitted(id));
    }

Application layer có thể phối hợp:

    Order.submit()
       ↓
    OrderSubmitted
       ↓
    Reservation process
       ↓
    Payment process
       ↓
    Fulfillment

Khi đó mỗi rule có owner rõ hơn.

## 24. Khi nào nên gộp lại thay vì tách thêm

Tái cấu trúc không có nghĩa là tạo thêm class cho mọi rule.

Nếu hai concept:

- luôn thay đổi cùng nhau;
- có cùng owner;
- cùng transaction;
- cùng language;
- không có lý do tồn tại độc lập;

thì tách chúng có thể chỉ làm tăng ceremony.

Ví dụ OrderLine và LineQuantity có thể cùng nằm trong Order Aggregate. Không cần tạo context riêng chỉ vì mỗi class có tên khác nhau.

Một mô hình tốt là mô hình giải thích được behavior với số lượng concept vừa đủ.

## 25. Khi nào thay đổi là dấu hiệu cần chia context

Có thể cân nhắc Bounded Context mới khi:

1. Hai nhóm dùng cùng một thuật ngữ nhưng định nghĩa khác nhau.
2. Một model thay đổi vì yêu cầu của context khác.
3. Một team cần truy cập internals của model để hoàn thành use case.
4. Contract giữa hai phần ngày càng giống shared database schema.
5. Một thay đổi nghiệp vụ buộc nhiều module sửa cùng một Entity.
6. Ownership của một quy tắc không rõ.
7. Lifecycle của concept khác nhau rõ rệt.
8. Tốc độ thay đổi của hai phần rất khác nhau.

Ví dụ:

    Order trong Ordering
        - submitted
        - cancelled
        - priced

    Order trong Fulfillment
        - picked
        - packed
        - shipped

Hai lifecycle khác nhau là tín hiệu mạnh để có local model riêng.

## 26. Context Map sau khi tái cấu trúc

Sau khi tách context, ghi lại quan hệ:

    Ordering
        |
        | OrderConfirmed
        v
    Fulfillment

    Ordering
        |
        | PaymentRequest
        v
    Payment

    Payment
        |
        | PaymentCaptured
        v
    Ordering

    Inventory
        |
        | ReservationConfirmed
        v
    Ordering

    Fulfillment
        |
        | ShipmentDispatched
        v
    Ordering

Mỗi mũi tên nên có ý nghĩa:

- ai phát hành contract;
- ai tiêu thụ;
- event hay command;
- đồng bộ hay bất đồng bộ;
- failure được xử lý thế nào;
- vocabulary nào được dịch.

Nếu chỉ vẽ mũi tên mà không biết ai sở hữu meaning, context map chưa đủ hữu ích.

## 27. Ghi quyết định để tránh quay lại mô hình cũ

Một refactor quan trọng nên để lại decision record ngắn:

    Decision:
    Order không giữ Payment object.

    Reason:
    Payment có lifecycle và consistency boundary riêng.

    Consequence:
    Ordering chỉ giữ PaymentId và nhận Payment facts
    qua integration contract.

    Trade-off:
    Cần xử lý eventual consistency và reconciliation.

    Revisit when:
    Business yêu cầu invariant mới bắt buộc Payment và
    Order phải nhất quán tức thời.

Điều này giúp team hiểu vì sao model có vẻ "không giống database relationship".

## 28. Các anti-pattern khi xử lý quy tắc mới

### 28.1. Thêm một boolean cho mỗi ngoại lệ

    boolean vip;
    boolean manual;
    boolean force;
    boolean special;
    boolean override;

Nếu nhiều cờ cùng ảnh hưởng một quyết định, tìm concept thay vì tiếp tục thêm cờ.

### 28.2. Đưa toàn bộ rule vào Application Service

    if (...) { ... }
    if (...) { ... }
    if (...) { ... }

Service trở thành domain model ẩn.

### 28.3. Mở rộng Aggregate vì một use case

Một use case cần dữ liệu từ Customer không có nghĩa Customer phải nằm trong Order Aggregate.

### 28.4. Dùng event để thay invariant đồng bộ

Eventual consistency không phù hợp với invariant cần bảo vệ trước khi command hoàn tất.

### 28.5. Chia context theo bảng

Một bảng là cấu trúc persistence. Bounded Context là ranh giới của model và language.

### 28.6. Tách class trước khi đặt tên concept

Nếu không giải thích được concept bằng ngôn ngữ nghiệp vụ, class mới có thể chỉ là technical abstraction.

### 28.7. Giữ cả legacy rule và new rule vô thời hạn

Hai nguồn quyết định tạo ra kết quả khác nhau sẽ khiến hệ thống khó dự đoán. Refactor theo bước nhỏ nhưng phải có điểm kết thúc.

### 28.8. Dùng inheritance để biểu diễn mọi ngoại lệ

Nhiều subclass VipOrder, SpecialOrder, ManualOrder, LegacyOrder có thể tạo một taxonomy khó kiểm soát. Policy hoặc state thường diễn đạt tốt hơn nếu khác biệt chỉ nằm ở rule.

## 29. Quy trình thực hành với một quy tắc mới

Có thể dùng quy trình sau trong một buổi modeling:

### Bước 1: Ghi nguyên văn quy tắc

Ví dụ:

> Order đã thanh toán chỉ được đổi địa chỉ nếu chưa bắt đầu đóng gói.

### Bước 2: Hỏi các thuật ngữ

- "đã thanh toán" nghĩa là captured hay authorized?
- "bắt đầu đóng gói" là thời điểm nào?
- ai quyết định trạng thái đó?
- đổi địa chỉ có ảnh hưởng shipping label không?

### Bước 3: Xác định invariant

    Nếu Order không đủ điều kiện thì
    ChangeDeliveryAddress phải bị từ chối.

### Bước 4: Xác định owner

- Payment sở hữu payment state.
- Fulfillment sở hữu packing state.
- Ordering sở hữu Order lifecycle.

### Bước 5: Xác định consistency

Nếu cả ba state không cần transaction chung, không gộp Aggregate chỉ để tránh eventual consistency.

### Bước 6: Chọn integration

    PaymentCaptured
    PackingStarted
    OrderAddressChangeRequested

hoặc command/query phù hợp với semantics.

### Bước 7: Cập nhật test

Test cả:

- happy path;
- rejection;
- state transition;
- concurrent update;
- integration translation;
- retry/idempotency nếu có.

### Bước 8: Xóa đường code cũ

Sau khi behavior mới đã ổn định, loại bỏ helper, boolean và branch cũ.

## 30. Checklist đánh giá một mô hình sau thay đổi

### Ngôn ngữ

- [ ] Quy tắc mới được diễn đạt bằng Ubiquitous Language.
- [ ] Tên class và method phản ánh khái niệm nghiệp vụ.
- [ ] Ngoại lệ quan trọng có tên thay vì chỉ là boolean.

### Ownership

- [ ] Mỗi invariant có owner rõ.
- [ ] Aggregate Root bảo vệ invariant của boundary.
- [ ] Context không sửa internals của context khác.
- [ ] Repository phục vụ Aggregate hoặc read model phù hợp.

### Consistency

- [ ] Biết invariant nào cần strong consistency.
- [ ] Biết invariant nào có thể eventual consistency.
- [ ] Không mở rộng transaction chỉ vì convenience.
- [ ] Concurrency behavior được xác định.

### Strategic design

- [ ] Bounded Context được xác định bằng language và model.
- [ ] Context relationship có contract rõ.
- [ ] Foreign model được dịch khi cần.
- [ ] Không dùng shared model chỉ để giảm công mapping.

### Tactical design

- [ ] Value Object được dùng cho concept không có identity riêng.
- [ ] Entity giữ behavior liên quan identity/lifecycle.
- [ ] Aggregate boundary dựa trên invariant.
- [ ] Policy/Specification chỉ được tách khi có ý nghĩa.
- [ ] Domain Event mô tả fact đã xảy ra.

### Integration

- [ ] Event không được dùng thay invariant đồng bộ.
- [ ] Command và Event được phân biệt.
- [ ] Retry và idempotency được xem xét cho operation có thể lặp.
- [ ] Failure semantics của context khác được xác định.

### Persistence

- [ ] Schema không quyết định trực tiếp domain boundary.
- [ ] ORM relationship không kéo object graph vượt Aggregate.
- [ ] Query đọc chuyên biệt không buộc phải load Aggregate.
- [ ] Migration được thực hiện theo từng bước.

### Testing

- [ ] Invariant được test trực tiếp.
- [ ] Invalid transition được test.
- [ ] Ngoại lệ hợp lệ được test.
- [ ] Translation giữa context được test.
- [ ] Concurrency hoặc integration failure được test khi có liên quan.

## 31. Một mẫu before / after để review

### Before

    OrderService
        ├── validate order
        ├── calculate discount
        ├── inspect payment
        ├── inspect inventory
        ├── update order
        ├── update payment
        ├── update inventory
        └── send notification

### After

    Ordering Context
        ├── Order
        │   ├── submit()
        │   ├── cancel()
        │   └── changeDeliveryAddress()
        ├── OrderChangePolicy
        └── OrderRepository

    Payment Context
        ├── Payment
        └── PaymentApplicationService

    Inventory Context
        ├── Reservation
        └── ReservationApplicationService

    Fulfillment Context
        ├── FulfillmentOrder
        └── FulfillmentApplicationService

    Integration
        ├── OrderSubmitted
        ├── PaymentCaptured
        ├── ReservationConfirmed
        └── ShipmentDispatched

Điểm quan trọng của after không phải số lượng class tăng lên. Giá trị nằm ở việc mỗi quyết định có nơi sở hữu rõ hơn.

## 32. Khi nào dừng tái cấu trúc

Một refactor nên dừng khi:

- quy tắc mới có một owner rõ;
- Aggregate bảo vệ được invariant cần thiết;
- context boundary không còn bị kéo qua bởi foreign model;
- application layer chủ yếu điều phối;
- test mô tả được behavior;
- đường code cũ đã được loại bỏ;
- thay đổi tiếp theo có thể diễn đạt bằng ngôn ngữ nghiệp vụ.

Không cần tiếp tục tách chỉ để đạt một kiến trúc "đẹp" hơn.

Một mô hình có thể còn đơn giản và vẫn tốt nếu nó làm rõ những quyết định quan trọng.

## 33. Tư duy cần giữ khi mô hình tiếp tục tiến hóa

Mỗi quy tắc mới là một cơ hội kiểm tra giả thuyết của mô hình hiện tại.

Nếu quy tắc mới chỉ thêm behavior vào đúng owner, mô hình đang hấp thụ thay đổi tốt.

Nếu một quy tắc buộc sửa nhiều service, nhiều bảng và nhiều context cùng lúc, hãy tìm coupling.

Nếu một ngoại lệ lặp lại, hãy hỏi liệu đó có phải một concept bị ẩn.

Nếu Aggregate phình to vì nhiều use case, hãy xem lại invariant và consistency boundary.

Nếu một context cần hiểu quá nhiều chi tiết của context khác, hãy xem lại Context Map và translation boundary.

Nếu policy thay đổi liên tục nhưng domain object ổn định, hãy tách phần biến đổi thành policy rõ ràng.

Nếu state mới xuất hiện và ảnh hưởng đến nhiều hành vi, hãy biểu diễn lifecycle thay vì thêm một cờ rời rạc.

Mục tiêu của tái cấu trúc DDD là làm cho mô hình dễ giải thích hơn bằng ngôn ngữ nghiệp vụ và dễ thay đổi hơn khi hiểu biết nghiệp vụ sâu thêm.
