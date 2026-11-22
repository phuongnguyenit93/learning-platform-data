# Đưa ràng buộc, quy trình và chính sách thành khái niệm rõ ràng

Một mô hình miền sâu không chỉ có nhiều entity, value object hay service. Nó diễn đạt được cách doanh nghiệp thực sự hoạt động: điều gì phải luôn đúng, một quyết định được đưa ra theo chính sách nào, quy trình đi qua những bước nào và vì sao một hành động được phép hoặc bị từ chối. Những kiến thức này thường tồn tại rải rác trong lời nói của chuyên gia, tài liệu vận hành, bảng tính, điều kiện trong mã nguồn và kinh nghiệm của nhân viên. Nhiệm vụ của Domain-Driven Design (DDD) là khám phá, đặt tên và đưa chúng vào mô hình theo cách có thể trao đổi, kiểm thử và thay đổi.

Khi các quy tắc chỉ tồn tại dưới dạng nhánh điều kiện hoặc ghi chú không chính thức, mô hình thường nông: class có dữ liệu nhưng hành vi quan trọng nằm ở service tổng quát, controller hoặc các đoạn code không liên quan. Một mô hình sâu làm cho những khái niệm quan trọng trở nên tường minh. Ràng buộc có thể được biểu diễn bằng invariant hoặc specification; chính sách có thể thành policy object; quy trình có thể thành state transition hoặc process; hành vi liên quan nhiều khái niệm có thể thuộc domain service. Những khái niệm đó giúp mã nguồn nói cùng ngôn ngữ với nghiệp vụ.

Tuy nhiên, không phải mọi điều kiện đều cần một class riêng. Mục tiêu không phải tăng số lượng abstraction mà là làm rõ hiểu biết nghiệp vụ và đặt trách nhiệm đúng chỗ. Bài học này trình bày cách khám phá quy tắc ẩn, biến chúng thành khái niệm miền, kết nối chúng với entity, value object, aggregate, service và process, rồi kiểm tra xem mô hình có thực sự sâu hơn hay chỉ phức tạp hơn.

## 1. Mô hình sâu là gì?

**Deep domain model (mô hình miền sâu)** là mô hình thể hiện được những quy tắc, quyết định và cấu trúc quan trọng của nghiệp vụ bằng các khái niệm có ý nghĩa. Khi mô hình đủ sâu, người đọc có thể hiểu vì sao một hành động hợp lệ, vì sao một trạng thái bị từ chối và chính sách nào tạo ra kết quả.

Một mô hình nông thường có những dấu hiệu:

- Entity chủ yếu chứa getter/setter và dữ liệu.
- Quy tắc nghiệp vụ nằm rải rác trong controller, application service hoặc các hàm tiện ích.
- Nhiều đoạn điều kiện lặp lại để kiểm tra cùng một chính sách.
- Trạng thái được thay đổi trực tiếp mà không có hành vi diễn đạt ý nghĩa.
- Tên class và method thiên về kỹ thuật như Manager, Processor, Helper hoặc UpdateStatus.
- Chuyên gia nghiệp vụ phải giải thích bằng lời những quy tắc mà mã nguồn không thể hiện.

Một mô hình sâu có thể có:

- Entity và aggregate bảo vệ invariant.
- Value object thể hiện khái niệm và ràng buộc giá trị.
- Specification diễn đạt điều kiện có thể kiểm tra.
- Policy diễn đạt quy tắc quyết định hoặc cách xử lý.
- Domain service biểu diễn hành vi không thuộc tự nhiên về một entity cụ thể.
- State machine hoặc process mô tả vòng đời nhiều bước.
- Domain event ghi nhận fact có ý nghĩa.

Đây không phải danh sách thành phần bắt buộc. Mô hình sâu được đánh giá bằng khả năng diễn đạt và bảo vệ nghiệp vụ, không bằng số lượng pattern đã sử dụng.

### 1.1. Độ sâu đến từ hiểu biết, không đến từ cấu trúc class

Một class có hàng chục phương thức chưa chắc tạo thành mô hình sâu nếu tên và hành vi không phản ánh nghiệp vụ. Ngược lại, một aggregate nhỏ với vài hành vi có tên chính xác, invariant rõ và các policy được đặt đúng chỗ có thể là một mô hình rất tốt.

Độ sâu xuất hiện khi nhóm phát hiện được một khái niệm trước đây bị ẩn, hiểu rõ nó và đưa nó vào thiết kế. Ví dụ, thay vì chỉ có điều kiện “khách phải có lịch sử thanh toán tốt”, nhóm khám phá ra khái niệm **CreditStanding (mức độ tín nhiệm)**, các yếu tố tạo nên nó và chính sách sử dụng kết quả đánh giá. Mô hình có thêm một khái niệm nghiệp vụ hữu ích, không chỉ thêm một lớp bao quanh boolean.

## 2. Tìm kiến thức đang ẩn trong nghiệp vụ

Một mô hình miền không nên được thiết kế chỉ bằng cách nhìn vào database hoặc yêu cầu giao diện. Những nguồn đó cho biết hệ thống đang lưu gì và người dùng đang thao tác ra sao, nhưng không nhất thiết giải thích quy tắc phía sau.

Nhóm có thể khám phá kiến thức từ:

- Phỏng vấn chuyên gia nghiệp vụ và người trực tiếp vận hành.
- Theo dõi một quy trình thực tế từ đầu đến cuối.
- Phân tích các trường hợp ngoại lệ và những lần quy trình thất bại.
- Xem bảng tính, biểu mẫu, hợp đồng và quy định đang được sử dụng.
- Quan sát cách nhân viên đưa ra quyết định khi dữ liệu không đầy đủ.
- Phân tích ticket hỗ trợ, khiếu nại và các tình huống phải xử lý thủ công.
- Đọc mã nguồn hiện tại để tìm điều kiện lặp lại, nhưng không coi code cũ là nguồn chân lý nghiệp vụ.

### 2.1. Hỏi về lý do, không chỉ hỏi về thao tác

Nếu chuyên gia nói “nhân viên bấm nút duyệt”, hãy hỏi:

- Điều kiện nào khiến hồ sơ được duyệt?
- Ai có quyền duyệt?
- Có giới hạn số tiền hoặc loại khách hàng không?
- Có trường hợp cần hai người phê duyệt không?
- Điều gì xảy ra nếu dữ liệu thay đổi trong lúc chờ duyệt?
- Nếu hồ sơ bị từ chối, người yêu cầu có thể bổ sung và gửi lại không?

Các câu hỏi này có thể làm lộ ra nhiều khái niệm: CreditApprovalPolicy, ApprovalLimit, AuthorizedApprover, PendingReview, Rejected và Resubmission. Chúng giúp nhóm hiểu rằng “duyệt” không chỉ là cập nhật một cột boolean.

### 2.2. Tìm quy tắc qua trường hợp ngoại lệ

Các trường hợp bình thường thường dễ mô tả bằng một câu. Trường hợp ngoại lệ giúp bộc lộ ranh giới của quy tắc:

- Đơn hàng đạt ngưỡng miễn phí giao hàng nhưng địa chỉ nằm ngoài vùng phục vụ.
- Khách hàng đủ hạn mức nhưng đang có khoản nợ quá hạn.
- Hợp đồng còn hiệu lực nhưng một điều kiện bắt buộc đã bị thu hồi.
- Thanh toán được chấp thuận nhưng phản hồi đến sau khi đơn đã bị hủy.
- Một nhân viên có quyền duyệt nhưng chính họ là người tạo hồ sơ.

Hãy ghi lại cả quy tắc, lý do và kết quả mong muốn. Không vội biến mọi ngoại lệ thành một nhánh code; trước tiên xác định chúng thuộc cùng một khái niệm hay là những quy tắc độc lập.

### 2.3. Dùng ví dụ cụ thể để kiểm chứng cách hiểu

Thay vì hỏi chung “chính sách giảm giá hoạt động thế nào?”, hãy đưa các trường hợp cụ thể và cùng chuyên gia tính kết quả. Ví dụ:

| Phân khúc khách hàng | Tổng đơn | Khu vực | Mã khuyến mại | Kết quả cần xác định |
| --- | ---: | --- | --- | --- |
| Thành viên | 1.200.000 VND | Nội thành | Không | Có miễn phí giao hàng không? |
| Thành viên | 700.000 VND | Nội thành | Có | Có đạt ngưỡng không? |
| Khách thường | 1.500.000 VND | Vùng xa | Có | Có được áp dụng ưu đãi không? |
| Thành viên | 1.500.000 VND | Vùng không hỗ trợ | Có | Điều kiện nào được ưu tiên? |

Những ví dụ này giúp phát hiện điều kiện thiếu, xung đột hoặc thứ tự áp dụng chưa được thống nhất.

## 3. Phân loại kiến thức: ràng buộc, chính sách và quy trình

Một cách hữu ích để làm rõ mô hình là phân loại các phát biểu nghiệp vụ. Ba nhóm thường gặp là:

**Ràng buộc (constraint/invariant):** điều kiện phải luôn đúng hoặc phải đúng tại một điểm kiểm tra cụ thể. Ví dụ, số lượng đặt phải dương; tổng tiền không âm; một đơn đã giao không thể quay về trạng thái nháp.

**Chính sách (policy):** quy tắc quyết định hành động hoặc kết quả dựa trên bối cảnh. Ví dụ, khách hàng thành viên được giảm giá theo phân khúc; hồ sơ có mức rủi ro cao cần phê duyệt bổ sung.

**Quy trình (process/workflow):** chuỗi hành động và trạng thái theo thời gian, thường có nhiều bước, người tham gia hoặc hệ thống tham gia. Ví dụ, mở tài khoản cần xác minh danh tính, thẩm định, phê duyệt và kích hoạt.

| Nhóm kiến thức | Câu hỏi nhận diện | Cách biểu diễn có thể phù hợp |
| --- | --- | --- |
| Ràng buộc | Điều gì không được phép sai? | Invariant, validation miền, value object, database constraint |
| Chính sách | Theo quy tắc nào ta chọn kết quả/hành động? | Policy, specification, domain service |
| Quy trình | Việc gì xảy ra trước/sau và trạng thái đang ở đâu? | State transition, process manager, saga |
| Fact đã xảy ra | Sự kiện nghiệp vụ nào đã hoàn tất? | Domain event |

Một phát biểu có thể thuộc nhiều nhóm. Ví dụ, “không được giao đơn khi chưa thanh toán” vừa là invariant của quy trình fulfillment, vừa là điều kiện trong policy cho phép tạo shipment. Nhóm cần xác định nơi sở hữu quy tắc và thời điểm kiểm tra.

## 4. Biến ràng buộc thành invariant rõ ràng

**Invariant** là quy tắc phải luôn được bảo vệ trong phạm vi mô hình hoặc transaction mà nó thuộc về. Invariant không nên chỉ là một câu chú thích; nó cần được thực thi tại điểm mà trạng thái có thể thay đổi.

Ví dụ trong đơn hàng:

- Mỗi dòng hàng phải có số lượng lớn hơn 0.
- Tổng tiền phải được tính từ các dòng hàng và quy tắc giá đã áp dụng.
- Đơn đã xác nhận không được sửa tùy tiện các dòng hàng.
- Đơn không thể được giao nếu chưa đáp ứng điều kiện fulfillment.

### 4.1. Xác định phạm vi của invariant

Hãy hỏi quy tắc cần bảo vệ những đối tượng nào và có cần đúng ngay lập tức không. Nếu invariant nằm trong một aggregate, aggregate root thường là nơi phù hợp để bảo vệ. Nếu invariant liên quan nhiều aggregate hoặc nhiều bounded context, có thể cần cơ chế điều phối, transaction hoặc consistency khác.

Ví dụ, “một đơn không có dòng hàng rỗng” có thể được bảo vệ bên trong Order aggregate. Nhưng “tổng số lượng được giữ không vượt tồn kho toàn kho” có thể liên quan nhiều đơn và một aggregate Inventory; nó cần được bảo vệ tại context sở hữu tồn kho, không chỉ bằng việc kiểm tra trong Order.

### 4.2. Đặt hành vi tại đối tượng sở hữu invariant

Ví dụ, thay vì cho application service tự sửa status:

~~~java
public void confirm(Order order) {
    if (order.getLines().isEmpty()) {
        throw new IllegalStateException("Order is empty");
    }
    order.setStatus(OrderStatus.CONFIRMED);
}
~~~

hãy để aggregate diễn đạt hành vi:

~~~java
public final class Order {
    private OrderStatus status;
    private final List<OrderLine> lines;

    public void confirm() {
        if (status != OrderStatus.SUBMITTED) {
            throw new OrderCannotBeConfirmedException(status);
        }
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeConfirmedException();
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Ví dụ cho thấy quy tắc xác nhận nằm cạnh trạng thái mà nó bảo vệ. Trong hệ thống thật, cần thêm các điều kiện như giá đã được chốt, quyền xác nhận hoặc kết quả giữ hàng tùy nghiệp vụ.

### 4.3. Phân biệt invariant và validation đầu vào

Không phải mọi validation đều là invariant:

- Kiểm tra chuỗi có đúng định dạng email là validation cấu trúc.
- Kiểm tra một đơn đã xác nhận không thể sửa giá là invariant/vòng đời.
- Kiểm tra actor có quyền thực hiện command là authorization.
- Kiểm tra mã khuyến mại còn hiệu lực là quy tắc nghiệp vụ hoặc policy.

Các loại kiểm tra có thể xuất hiện ở nhiều tầng, nhưng phải phân biệt trách nhiệm. Validation ở API không thay thế invariant trong domain model.

## 5. Đưa khái niệm miền vào value object và entity

Một số ràng buộc có thể được làm rõ bằng value object. Ví dụ, thay vì dùng một số nguyên cho số lượng và hy vọng mọi caller đều kiểm tra số dương, nhóm có thể tạo Quantity đảm bảo giá trị hợp lệ ngay khi khởi tạo.

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero");
        }
    }
}
~~~

Khi đó, các hành vi nhận Quantity có thể dựa trên điều kiện cơ bản này. Value object giúp gom quy tắc giá trị và tránh lặp validation.

Một khái niệm khác có identity và vòng đời riêng có thể là entity. Ví dụ, CreditApplication có trạng thái, người yêu cầu, thời điểm gửi, các lần đánh giá và quyết định phê duyệt. Nó không chỉ là một record chứa vài trường.

### 5.1. Tên phải phản ánh khái niệm thực

Nếu chuyên gia dùng từ “hạn mức khả dụng”, có thể mô hình hóa AvailableCreditLimit thay vì một biến double tên remaining. Nếu nghiệp vụ phân biệt “ngày hiệu lực” với “ngày tạo bản ghi”, nên dùng các kiểu có tên khác nhau để tránh trộn semantics.

Không cần tạo value object cho mọi kiểu dữ liệu. Hãy tạo khi khái niệm có quy tắc, đơn vị, định dạng hoặc ý nghĩa riêng đủ quan trọng.

## 6. Đưa điều kiện thành Specification

**Specification (đặc tả)** diễn đạt một điều kiện có thể đánh giá trên một đối tượng hoặc ngữ cảnh. Nó trả lời câu hỏi “đối tượng này có thỏa điều kiện không?”.

Ví dụ:

- Đơn có đủ điều kiện miễn phí vận chuyển không?
- Hồ sơ có đủ điều kiện được phê duyệt tự động không?
- Hợp đồng có còn hiệu lực tại ngày giao dịch không?
- Khách hàng có được phép mua chịu không?

Một specification có thể giúp đặt tên cho điều kiện phức tạp và tái sử dụng nó ở nhiều nơi có cùng semantics.

~~~java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}

public final class EligibleForFreeShipping
        implements Specification<ShippingContext> {

    private final Money minimumOrderTotal;

    public EligibleForFreeShipping(Money minimumOrderTotal) {
        this.minimumOrderTotal = minimumOrderTotal;
    }

    @Override
    public boolean isSatisfiedBy(ShippingContext context) {
        return context.buyerSegment() == BuyerSegment.MEMBER
                && context.orderTotal().isAtLeast(minimumOrderTotal)
                && context.deliveryZone().supportsFreeShipping();
    }
}
~~~

Tên EligibleForFreeShipping diễn đạt một điều kiện nghiệp vụ. Người đọc có thể hiểu ý nghĩa mà không phải giải mã ba phép so sánh.

### 6.1. Kết hợp specification

Các điều kiện có thể được kết hợp theo AND, OR hoặc NOT. Ví dụ, khách đủ điều kiện khi là thành viên và đơn đạt ngưỡng, hoặc có một hợp đồng doanh nghiệp cho phép miễn phí:

~~~text
(IsMember AND OrderTotalReachedThreshold)
OR
(HasFreeShippingContract)
~~~

Có thể tạo các specification kết hợp, nhưng chỉ nên làm khi việc kết hợp có ý nghĩa và được dùng lại hoặc cần diễn đạt rõ. Với một điều kiện đơn giản chỉ xuất hiện một lần, biểu thức trực tiếp thường dễ đọc hơn.

### 6.2. Specification khác validation

Specification thường diễn đạt điều kiện miền có thể đánh giá trong nhiều bối cảnh. Validation có thể chỉ kiểm tra định dạng hoặc tính đầy đủ của dữ liệu đầu vào. Ví dụ, “mã bưu chính có đúng định dạng” khác với “địa chỉ thuộc vùng mà dịch vụ giao hàng hỗ trợ”.

## 7. Đưa quyết định thành Policy

Specification cho biết một điều kiện có được thỏa mãn không; policy thường quyết định hành động hoặc kết quả cần áp dụng dựa trên một hay nhiều điều kiện.

Ví dụ, CreditApprovalPolicy có thể quyết định:

- Hồ sơ được phê duyệt tự động.
- Hồ sơ cần chuyên viên thẩm định.
- Hồ sơ cần phê duyệt cấp cao hơn.
- Hồ sơ bị từ chối vì không đáp ứng điều kiện tối thiểu.

~~~java
public enum CreditDecision {
    AUTO_APPROVED,
    MANUAL_REVIEW,
    SENIOR_APPROVAL_REQUIRED,
    REJECTED
}

public record CreditAssessment(
        CreditDecision decision,
        String reasonCode
) {}

public interface CreditApprovalPolicy {
    CreditAssessment assess(CreditApplicationFacts facts);
}
~~~

Policy có thể trả về kiểu kết quả miền thay vì boolean. Điều này giúp giải thích quyết định và hỗ trợ application layer điều phối bước tiếp theo.

### 7.1. Tách dữ liệu đầu vào khỏi policy

Policy nên nhận những dữ kiện cần thiết để ra quyết định. Không nên để policy tự tải entity từ database hoặc gọi API bên ngoài cụ thể. Application service có thể thu thập dữ liệu qua repository/port rồi truyền một snapshot phù hợp.

### 7.2. Policy có thể thay đổi theo thời gian

Nếu quyết định phụ thuộc vào chính sách có hiệu lực theo ngày hoặc hợp đồng, cần xác định thời điểm áp dụng và phiên bản. Một hồ sơ được đánh giá theo chính sách ngày gửi không nên bị diễn giải lại bằng chính sách mới nếu nghiệp vụ yêu cầu giữ kết quả cũ.

Có thể lưu policy version, effective date hoặc snapshot dữ liệu đầu vào cần thiết để giải thích quyết định sau này.

## 8. Đưa hành vi liên quan nhiều đối tượng thành Domain Service

Khi một hoạt động nghiệp vụ có ý nghĩa nhưng không thuộc tự nhiên về một entity hoặc value object cụ thể, domain service có thể là nơi phù hợp.

Ví dụ, định giá một đơn hàng có thể phụ thuộc:

- Phân khúc người mua.
- Các dòng hàng và số lượng.
- Bảng giá có hiệu lực.
- Chương trình khuyến mại.
- Giới hạn chiết khấu.

Không có entity đơn lẻ nào sở hữu toàn bộ hoạt động này. Một OrderPricingService có thể nhận dữ liệu miền, áp dụng policy và trả về PriceQuote.

~~~java
public final class OrderPricingService {
    private final DiscountPolicy discountPolicy;

    public OrderPricingService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    public PriceQuote calculate(OrderPricingFacts facts) {
        Money subtotal = facts.lines().stream()
                .map(OrderLinePricing::lineTotal)
                .reduce(Money.zero(facts.currency()), Money::add);

        Money discount = discountPolicy.calculate(facts, subtotal);
        return new PriceQuote(subtotal, discount, subtotal.subtract(discount));
    }
}
~~~

Domain service biểu diễn hoạt động miền; policy biểu diễn quy tắc quyết định được sử dụng trong hoạt động đó. Không phải mọi policy đều cần domain service bao quanh, và không phải mọi domain service đều cần policy object.

## 9. Đưa quy trình thành state transition rõ ràng

Một quy trình nghiệp vụ thường được mô tả bằng chuỗi bước: tạo, gửi, thẩm định, phê duyệt, kích hoạt. Nếu mã chỉ có một trường status được cập nhật tùy tiện, vòng đời có thể không rõ và các chuyển trạng thái bất hợp lệ dễ lọt qua.

Hãy mô hình hóa:

- Các trạng thái có ý nghĩa.
- Sự kiện hoặc command kích hoạt chuyển trạng thái.
- Điều kiện để chuyển.
- Actor hoặc vai trò được phép thực hiện.
- Tác động của chuyển trạng thái.
- Những trạng thái kết thúc và khả năng gửi lại.

Ví dụ vòng đời CreditApplication:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Submitted: SubmitApplication
    Submitted --> UnderReview: StartReview
    UnderReview --> Approved: Approve
    UnderReview --> Rejected: Reject
    UnderReview --> MoreInformationRequired: RequestInformation
    MoreInformationRequired --> Submitted: Resubmit
    Approved --> Activated: ActivateCredit
    Rejected --> [*]
    Activated --> [*]
~~~

Sơ đồ là ví dụ minh họa. Trạng thái thực tế cần phản ánh quy trình và quyền hạn của tổ chức. Ví dụ, có thể cần trạng thái Suspended hoặc Withdrawn nếu nghiệp vụ có các trường hợp đó.

### 9.1. Chuyển trạng thái phải có tên hành vi

Thay vì cho phép setter status, hãy cung cấp các hành vi như submit(), approve(), reject(), requestMoreInformation() hoặc activate(). Mỗi hành vi kiểm tra trạng thái hiện tại và điều kiện cần thiết.

### 9.2. State machine không phải lúc nào cũng là một framework

Một entity có thể kiểm tra trạng thái trong các phương thức riêng. Chỉ cần thư viện state machine khi số trạng thái/chuyển đổi đủ phức tạp, cần cấu hình hoặc cần công cụ hỗ trợ. Mục tiêu là làm rõ vòng đời, không phải đưa thêm framework.

## 10. Phân biệt quy trình nội bộ với tiến trình liên ngữ cảnh

Một quy trình có thể nằm trọn trong một aggregate hoặc một bounded context. Khi đó, state transition và application service có thể đủ.

Nếu quy trình kéo dài qua nhiều bounded context, có thời gian chờ, retry, timeout hoặc compensation, có thể cần Process Manager/Saga. Process Manager lưu trạng thái điều phối và gửi command đến participant; mỗi participant vẫn bảo vệ invariant của mình.

Ví dụ mở tài khoản:

1. Identity xác minh danh tính.
2. Risk đánh giá mức rủi ro.
3. Credit phê duyệt hạn mức.
4. Account tạo tài khoản.
5. Notification gửi thông báo.

Process Manager theo dõi tiến trình và điều phối bước tiếp theo. Nó không tự sửa database của Identity, Risk hoặc Credit.

Không nên dùng Process Manager cho một quy trình ngắn chỉ có một transaction. Chọn cơ chế dựa trên phạm vi và độ phức tạp thực tế.

## 11. Đưa sự kiện đã xảy ra thành Domain Event

Khi một hành vi có ý nghĩa nghiệp vụ hoàn tất, domain event có thể ghi nhận fact đó. Ví dụ:

- CreditApplicationSubmitted.
- CreditAssessmentCompleted.
- CreditApplicationApproved.
- CreditLimitActivated.

Event giúp các phần khác phản ứng mà không cần truy cập trực tiếp vào aggregate nguồn. Nó cũng làm rõ những mốc quan trọng trong vòng đời.

Event cần được đặt tên theo sự việc đã xảy ra, có dữ liệu đủ để diễn giải và giữ tính bất biến sau khi ghi nhận. Nếu kết quả thay đổi, ghi một event điều chỉnh mới thay vì sửa event cũ.

Không phải mọi thay đổi field đều cần domain event. Chỉ tạo event khi sự việc có ý nghĩa với nghiệp vụ hoặc thành phần khác.

## 12. Ví dụ xuyên suốt: mô hình đánh giá tín dụng

Giả sử một doanh nghiệp cho khách hàng mua chịu. Hệ thống ban đầu có một service:

~~~java
public boolean canBuyOnCredit(Customer customer, BigDecimal amount) {
    if (customer.getDebt().compareTo(customer.getLimit()) >= 0) {
        return false;
    }
    if (customer.getOverdueDays() > 30) {
        return false;
    }
    if (amount.compareTo(new BigDecimal("50000000")) > 0
            && !customer.isVip()) {
        return false;
    }
    return true;
}
~~~

Đoạn code chứa nhiều quy tắc nhưng không cho biết:

- Hạn mức còn lại được tính thế nào.
- Khoản nợ quá hạn có bao gồm khoản đang tranh chấp không.
- Ngưỡng 50 triệu áp dụng theo loại tiền nào và có thay đổi theo hợp đồng không.
- Khách VIP được định nghĩa ra sao.
- Khi không đủ điều kiện, cần từ chối hay chuyển thẩm định thủ công.
- Quyết định có hiệu lực tại thời điểm nào.

Qua trao đổi với chuyên gia, nhóm khám phá các khái niệm:

- CreditProfile: hồ sơ tín dụng của khách.
- CreditExposure: tổng nghĩa vụ tín dụng đang được tính.
- AvailableCreditLimit: hạn mức còn khả dụng.
- OverdueAccount: khoản nợ quá hạn theo định nghĩa kế toán.
- CreditStanding: mức độ tín nhiệm.
- CreditApprovalPolicy: chính sách quyết định.
- CreditAssessment: kết quả đánh giá kèm lý do.
- CreditApplication: hồ sơ xin mua chịu có vòng đời riêng.

Mô hình có thể được tổ chức như sau:

~~~mermaid
classDiagram
    class CreditApplication {
        +submit()
        +approve()
        +reject()
        +requestMoreInformation()
    }
    class CreditProfile {
        +customerId
        +creditStanding
    }
    class AvailableCreditLimit {
        +amount
        +currency
    }
    class CreditApprovalPolicy {
        +assess(facts)
    }
    class CreditAssessment {
        +decision
        +reasonCode
    }
    CreditApplication --> CreditProfile
    CreditProfile --> AvailableCreditLimit
    CreditApprovalPolicy --> CreditAssessment
~~~

Sơ đồ chỉ nêu các khái niệm chính, không phải toàn bộ class diagram. Quan hệ và aggregate boundary cần được xác nhận theo cách dữ liệu được sở hữu và thay đổi.

### 12.1. Value object diễn đạt hạn mức

~~~java
public record AvailableCreditLimit(Money value) {
    public AvailableCreditLimit {
        Objects.requireNonNull(value);
        if (value.isNegative()) {
            throw new IllegalArgumentException(
                    "Available credit limit cannot be negative");
        }
    }
}
~~~

Kiểu này diễn đạt một khái niệm cụ thể và bảo vệ điều kiện cơ bản. Quy tắc tính hạn mức khả dụng có thể cần một domain service hoặc policy tùy dữ liệu tham gia.

### 12.2. Policy trả về quyết định có lý do

~~~java
public final class CreditApprovalPolicy {
    public CreditAssessment assess(CreditFacts facts) {
        if (facts.hasDisqualifyingOverdueDebt()) {
            return CreditAssessment.rejected("OVERDUE_DEBT");
        }

        if (facts.availableLimit().isLessThan(facts.requestedAmount())) {
            return CreditAssessment.rejected("LIMIT_EXCEEDED");
        }

        if (facts.requiresSeniorApproval()) {
            return CreditAssessment.manualReview("HIGH_VALUE_REQUEST");
        }

        return CreditAssessment.autoApproved();
    }
}
~~~

Đây là minh họa về cấu trúc, không phải một chính sách tín dụng có thể dùng ngay. Điều kiện thực tế, ngưỡng và thứ tự ưu tiên phải được xác nhận với chuyên gia và có version nếu thay đổi theo thời gian.

### 12.3. Aggregate quản lý vòng đời hồ sơ

CreditApplication có thể kiểm tra trạng thái trước khi chấp nhận quyết định:

~~~java
public void approve(CreditAssessment assessment, ActorId approver) {
    if (status != CreditApplicationStatus.UNDER_REVIEW) {
        throw new InvalidCreditApplicationTransition(status);
    }
    if (!assessment.isApprovable()) {
        throw new CreditAssessmentNotApprovableException();
    }
    this.decision = CreditDecision.APPROVED;
    this.approvedBy = approver;
    this.status = CreditApplicationStatus.APPROVED;
    recordEvent(new CreditApplicationApproved(id, approver));
}
~~~

Policy đánh giá điều kiện; aggregate bảo vệ vòng đời và invariant của hồ sơ. Application service điều phối việc tải dữ liệu, gọi policy và lưu aggregate. Mỗi khái niệm có trách nhiệm riêng.

## 13. Đưa quy tắc vào đúng nơi

Một trong những quyết định khó nhất khi làm mô hình sâu là chọn nơi đặt mỗi quy tắc. Có thể dùng bảng gợi ý:

| Loại trách nhiệm | Câu hỏi | Nơi thường phù hợp |
| --- | --- | --- |
| Quy tắc giá trị cơ bản | Giá trị này có hợp lệ tự thân không? | Value object |
| Quy tắc thay đổi trạng thái | Đối tượng này có được phép chuyển trạng thái không? | Entity/aggregate |
| Invariant trong aggregate | Những object nào phải nhất quán cùng nhau? | Aggregate root |
| Điều kiện có thể tái sử dụng | Ứng viên có thỏa điều kiện không? | Specification |
| Quy tắc quyết định | Chính sách nào tạo ra quyết định? | Policy/domain service |
| Hành vi không thuộc một entity | Hoạt động này liên quan nhiều khái niệm nào? | Domain service |
| Điều phối use case | Tải dữ liệu, gọi domain behavior, quản lý transaction ra sao? | Application service |
| Tiến trình dài hạn | Bước nào tiếp theo, đang chờ ai, timeout thế nào? | Process Manager/Saga |
| Tích hợp kỹ thuật | Gửi HTTP, message hoặc lưu file ra sao? | Infrastructure adapter |

Đây là hướng dẫn, không phải luật cứng. Một policy có thể được triển khai như specification kết hợp; một domain service có thể sử dụng value object; một aggregate có thể ghi nhận domain event.

## 14. Tách chính sách khỏi dữ liệu cấu hình

Không phải mọi chính sách đều nên được mã hóa thành các con số cố định trong code. Một số tham số như ngưỡng giảm giá, thời hạn ưu đãi hoặc hạn mức theo phân khúc có thể cần thay đổi theo thời gian.

Nhóm cần phân biệt:

- **Quy tắc:** cách các yếu tố được kết hợp để đưa ra quyết định.
- **Tham số:** giá trị được quy tắc sử dụng, như ngưỡng 10% hoặc 30 ngày.
- **Phiên bản chính sách:** tập quy tắc/tham số có hiệu lực trong một khoảng thời gian.
- **Quyền thay đổi:** ai được sửa tham số và quy trình phê duyệt thay đổi.

Một policy có thể nhận các tham số từ cấu hình đã được kiểm tra:

~~~java
public record CreditPolicyTerms(
        Money maximumAutoApprovalAmount,
        int maximumOverdueDays,
        LocalDate effectiveFrom,
        LocalDate effectiveTo,
        String version
) {}
~~~

Không nên biến toàn bộ quy tắc thành một chuỗi biểu thức động trong database nếu không có nhu cầu rõ ràng về rule engine. Quy tắc cốt lõi cần review, version, kiểm thử và audit. Cấu hình động cũng cần kiểm tra tính hợp lệ trước khi được sử dụng.

## 15. Làm cho mô hình có thể giải thích được

Một quyết định nghiệp vụ thường cần trả lời “vì sao?”. Nếu policy chỉ trả boolean, hệ thống có thể biết quyết định nhưng không giải thích được.

Thay vì:

~~~java
boolean approved = policy.isEligible(facts);
~~~

có thể trả về kết quả:

~~~java
public record PolicyDecision(
        DecisionOutcome outcome,
        List<DecisionReason> reasons,
        String policyVersion
) {}
~~~

Kết quả này có thể giúp:

- Hiển thị lý do từ chối cho người dùng hoặc nhân viên.
- Hỗ trợ xử lý khiếu nại.
- Ghi audit.
- So sánh kết quả giữa các phiên bản chính sách.
- Kiểm thử các trường hợp biên.

Chỉ nên lưu các lý do thực sự cần thiết và không tiết lộ thông tin nội bộ hoặc dữ liệu nhạy cảm không phù hợp cho người nhận.

## 16. Knowledge crunching và cải tiến mô hình liên tục

**Knowledge crunching** là quá trình nhóm phát triển và chuyên gia cùng khám phá, kiểm tra và tinh chỉnh hiểu biết về miền. Mô hình không nên được xem là bản thiết kế cố định được tạo một lần rồi chỉ triển khai.

Một vòng lặp thường gồm:

1. Chọn một quy trình hoặc vấn đề nghiệp vụ cụ thể.
2. Thu thập ví dụ thực tế và các trường hợp ngoại lệ.
3. Xác định thuật ngữ, ràng buộc, quyết định và trạng thái.
4. Đề xuất mô hình và đặt tên cho khái niệm.
5. Thảo luận với chuyên gia để xác nhận hoặc bác bỏ cách hiểu.
6. Viết test thể hiện quy tắc đã thống nhất.
7. Triển khai mô hình và quan sát khi vận hành.
8. Cập nhật mô hình khi phát hiện kiến thức mới.

### 16.1. Dùng event storming để khám phá quy trình

Event storming có thể giúp nhóm nhìn thấy các domain event, command, actor, policy và hệ thống liên quan. Từ chuỗi event, nhóm có thể phát hiện:

- Bước nào tạo ra một fact nghiệp vụ.
- Quyết định nào kích hoạt bước tiếp theo.
- Ai chịu trách nhiệm hành động.
- Điều kiện nào khiến luồng rẽ nhánh.
- Aggregate hoặc bounded context nào sở hữu dữ liệu.

Event storming là công cụ khám phá và trao đổi; nó không tự động tạo ra domain model đúng. Những phát hiện cần được kiểm tra lại với chuyên gia và hiện thực hóa thành khái niệm phù hợp.

### 16.2. Tìm khái niệm qua ngôn ngữ của chuyên gia

Khi chuyên gia dùng một danh từ lặp lại có ý nghĩa riêng, hãy kiểm tra xem đó có phải khái niệm miền chưa được mô hình hóa. Ví dụ: “hạn mức khả dụng”, “ngày chốt công nợ”, “lần thẩm định”, “đợt giao hàng”, “mức tín nhiệm”.

Khi chuyên gia dùng một động từ quan trọng, hãy kiểm tra xem nó có tương ứng với hành vi rõ: “đối soát”, “phân bổ”, “gia hạn”, “thu hồi”, “tạm khóa”, “chuyển cấp phê duyệt”.

Không phải danh từ nào cũng cần class và không phải động từ nào cũng cần service. Mục tiêu là tìm các khái niệm có quy tắc, identity, vòng đời hoặc ý nghĩa trao đổi riêng.

## 17. Kiểm thử để củng cố mô hình

Một khái niệm chỉ thực sự hữu ích khi nhóm có thể kiểm tra hành vi của nó. Test không chỉ xác nhận code chạy mà còn ghi lại cách hiểu nghiệp vụ.

### 17.1. Test invariant

Ví dụ:

- Không thể xác nhận đơn rỗng.
- Không thể thêm dòng hàng vào đơn đã giao.
- Hạn mức khả dụng không âm.
- Không thể phê duyệt hồ sơ đã bị từ chối.

### 17.2. Test specification và policy

Dùng bảng quyết định để kiểm tra từng điều kiện và kết quả. Bao gồm trường hợp đúng, sai, biên và xung đột giữa các chính sách.

### 17.3. Test state transition

Kiểm tra mọi chuyển trạng thái được phép và từ chối chuyển trạng thái không hợp lệ. Nếu có nhiều actor, kiểm tra quyền tương ứng.

### 17.4. Test process

Nếu quy trình kéo dài qua nhiều context, kiểm tra happy path, timeout, retry, event trùng, event đến muộn và compensation.

### 17.5. Test bằng ngôn ngữ miền

Tên test nên mô tả tình huống nghiệp vụ, ví dụ:

- shouldRejectCreditApplicationWhenOverdueDebtExceedsPolicy
- shouldRequireSeniorApprovalForHighValueRequest
- shouldNotConfirmAnEmptyOrder
- shouldReleaseReservationWhenPaymentIsDeclined

Tên test như test1 hoặc checkStatus không giúp lưu giữ kiến thức miền.

## 18. Tránh over-modeling và abstraction không có ý nghĩa

Làm mô hình sâu không đồng nghĩa tạo một class cho mỗi câu trong tài liệu nghiệp vụ. Một mô hình quá trừu tượng có thể khó hiểu hơn mã điều kiện ban đầu.

Các dấu hiệu over-modeling:

- Một điều kiện đơn giản chỉ dùng một lần nhưng có nhiều interface và implementation.
- Class chỉ chuyển tiếp một lời gọi mà không thêm ý nghĩa hoặc bảo vệ quy tắc.
- Tên abstraction không được chuyên gia nhận ra.
- Mỗi trường dữ liệu đều được bọc trong một object dù không có semantics riêng.
- Thay đổi một quy tắc nhỏ đòi hỏi sửa quá nhiều lớp.
- Người đọc phải đi qua nhiều file để hiểu một quyết định đơn giản.

### 18.1. Giữ điều kiện đơn giản khi nó thực sự đơn giản

Nếu một quy tắc là “số lượng phải lớn hơn 0” và chỉ có một cách hiểu, một validation trong Quantity có thể đủ. Không cần PositiveQuantityPolicy, QuantityEligibilitySpecification và QuantityValidationManager cùng tồn tại.

### 18.2. Tách khi có ý nghĩa và lý do thay đổi riêng

Nếu chính sách miễn phí vận chuyển có nhiều điều kiện, có thể được thay đổi bởi bộ phận vận hành, cần giải thích kết quả và có nhiều phiên bản theo thời gian, policy object có giá trị. Nếu chỉ là một điều kiện ổn định và đơn giản, biểu thức trong domain method có thể tốt hơn.

### 18.3. Đánh giá bằng khả năng thay đổi

Hãy hỏi: khi nghiệp vụ thay đổi, nhóm có thể xác định đúng nơi sửa không? Có test nào mô tả quy tắc không? Thay đổi có lan sang các phần không liên quan không? Nếu câu trả lời tốt hơn sau khi mô hình hóa, abstraction có giá trị.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ mô hình hóa danh từ từ database | Bỏ sót quy tắc và quyết định nghiệp vụ | Khám phá hành vi, ngoại lệ và lý do |
| Để quy tắc rải rác trong controller/service | Quy tắc lặp và dễ mâu thuẫn | Đặt invariant, policy và hành vi vào đúng khái niệm |
| Dùng boolean cho quyết định phức tạp | Không giải thích được lý do và nhánh tiếp theo | Trả về result type có outcome/reason |
| Đặt mọi quy tắc vào một DomainService | Service trở thành nơi chứa mọi logic | Phân loại invariant, policy, specification và hành vi entity |
| Biến mọi điều kiện thành Specification | Quá nhiều abstraction và khó đọc | Chỉ tách khi điều kiện có ý nghĩa riêng hoặc được tái sử dụng |
| Dùng setter để thay đổi trạng thái | Bỏ qua transition và invariant | Cung cấp hành vi như approve, cancel, activate |
| Đưa quy tắc miền vào mapper hoặc DTO validation | Luồng khác có thể bỏ qua quy tắc | Bảo vệ invariant trong domain model |
| Trộn tham số với quy tắc chính sách | Không biết thay đổi nào cần review/version | Tách policy logic, terms và effective period |
| Không lưu phiên bản chính sách đã áp dụng | Không giải thích được quyết định lịch sử | Lưu policy version hoặc snapshot cần thiết |
| Dùng Process Manager cho quy trình ngắn | Tăng độ phức tạp không cần thiết | Chọn theo nhu cầu điều phối dài hạn |
| Tạo nhiều class chỉ để áp dụng pattern | Mô hình phức tạp hơn nghiệp vụ | Giữ abstraction nhỏ và có ý nghĩa |
| Không xác nhận thuật ngữ với chuyên gia | Tên code không phản ánh ngôn ngữ chung | Review mô hình bằng ví dụ và câu hỏi nghiệp vụ |

## 20. Quy trình đưa ràng buộc, quy trình và chính sách vào mô hình

Nhóm có thể sử dụng trình tự sau khi phát triển một phần domain model:

### Bước 1: Chọn một quyết định hoặc quy trình quan trọng

Chọn tình huống thường xuyên, có nhiều ngoại lệ hoặc gây lỗi nếu xử lý sai. Không cố mô hình hóa toàn bộ miền trong một lần.

### Bước 2: Thu thập ví dụ thực tế

Ghi lại trường hợp bình thường, trường hợp biên, trường hợp bị từ chối và cách nhân viên xử lý thủ công. Xác nhận ví dụ với chuyên gia.

### Bước 3: Tìm danh từ và động từ có ý nghĩa

Đánh dấu khái niệm, hành vi, trạng thái và quyết định. Đối chiếu với Ubiquitous Language của bounded context.

### Bước 4: Phân loại kiến thức

Xác định đâu là invariant, validation, specification, policy, process, domain service và fact/event. Ghi rõ phạm vi và chủ sở hữu.

### Bước 5: Chọn nơi đặt trách nhiệm

Đặt quy tắc giá trị trong value object, invariant trong aggregate, điều kiện có thể đánh giá trong specification, quyết định trong policy và điều phối use case ở application layer.

### Bước 6: Mô hình hóa trạng thái và chuyển đổi

Nếu có vòng đời, định nghĩa trạng thái, hành vi chuyển trạng thái, actor, điều kiện và trạng thái kết thúc. Nếu quy trình liên context và dài hạn, đánh giá nhu cầu Process Manager.

### Bước 7: Đặt tên và kiểm tra ngôn ngữ

Đọc tên class/method như một câu nghiệp vụ. Hỏi chuyên gia xem tên có diễn đạt đúng khái niệm và kết quả không.

### Bước 8: Viết test theo ví dụ

Chuyển bảng quyết định và tình huống thành test. Bao gồm cả điều kiện không hợp lệ và các trường hợp xung đột.

### Bước 9: Triển khai và quan sát

Đưa mô hình vào use case, theo dõi các trường hợp bị từ chối, quy trình phải xử lý thủ công và sai lệch giữa kỳ vọng với vận hành.

### Bước 10: Tinh chỉnh khi có kiến thức mới

Khi phát hiện thuật ngữ hoặc quy tắc mới, cập nhật mô hình, test và tài liệu. Không giữ abstraction chỉ vì đã tốn công viết; mô hình phải tiếp tục phục vụ hiểu biết hiện tại.

## 21. Nguyên tắc thực hành

Khi đưa ràng buộc, quy trình và chính sách thành khái niệm rõ ràng, nhóm nên nhớ:

- **Khám phá nghiệp vụ trước khi thiết kế class.** Hỏi lý do, ngoại lệ và cách quyết định.
- **Phân loại đúng loại kiến thức.** Ràng buộc, policy, specification và process có mục đích khác nhau.
- **Đặt invariant cạnh trạng thái nó bảo vệ.** Aggregate root kiểm soát thay đổi trong aggregate.
- **Dùng value object cho khái niệm giá trị có quy tắc.** Đừng để số hoặc chuỗi chung chung mang quá nhiều ý nghĩa.
- **Dùng specification cho điều kiện có tên.** Tách khi điều kiện có semantics riêng hoặc cần tái sử dụng.
- **Dùng policy cho quyết định nghiệp vụ.** Trả kết quả có lý do khi cần giải thích.
- **Dùng domain service cho hành vi không thuộc tự nhiên về một entity.** Giữ trách nhiệm tập trung và dùng kiểu miền.
- **Mô hình hóa vòng đời bằng hành vi.** Tránh thay đổi status tùy tiện qua setter.
- **Chỉ dùng Process Manager cho điều phối dài hạn.** Không thêm nó cho một luồng đơn giản.
- **Ghi nhận fact bằng domain event khi có ý nghĩa.** Không biến mọi thay đổi kỹ thuật thành event.
- **Lưu phiên bản chính sách khi cần giải thích lịch sử.** Quyết định cũ phải được hiểu theo quy tắc đã áp dụng.
- **Kiểm thử bằng ví dụ nghiệp vụ.** Test là nơi lưu giữ cách hiểu đã thống nhất.
- **Tránh over-modeling.** Abstraction phải làm rõ nghiệp vụ hoặc giảm thay đổi lan truyền.
- **Tinh chỉnh liên tục.** Mô hình là kết quả của quá trình học hỏi, không phải bản thiết kế bất biến.

Một mô hình miền sâu đưa những quy tắc từng nằm trong lời nói, bảng tính và nhánh điều kiện thành các khái niệm có tên và trách nhiệm rõ. Invariant bảo vệ trạng thái, specification diễn đạt điều kiện, policy giải thích quyết định, state transition làm rõ vòng đời và process điều phối các bước dài hạn. Khi các khái niệm này được khám phá cùng chuyên gia, đặt đúng ranh giới và kiểm thử bằng ví dụ thực tế, domain model trở thành cách diễn đạt nghiệp vụ có thể phát triển cùng hiểu biết của tổ chức.

## 22. Câu hỏi tự kiểm tra

1. Mô hình miền sâu khác mô hình nông ở khả năng diễn đạt và bảo vệ nghiệp vụ như thế nào?
2. Vì sao không thể chỉ nhìn database schema để khám phá domain model?
3. Những câu hỏi nào giúp phát hiện quy tắc ẩn trong một quy trình phê duyệt?
4. Phân biệt invariant, specification, policy và process bằng ví dụ tín dụng.
5. Vì sao invariant cần được bảo vệ tại aggregate root thay vì chỉ kiểm tra trong controller?
6. Khi nào một khái niệm nên trở thành value object hoặc entity?
7. Specification khác policy như thế nào? Một policy có thể sử dụng nhiều specification ra sao?
8. Khi nào nên dùng domain service cho một hoạt động nghiệp vụ?
9. State transition giúp ngăn việc thay đổi trạng thái bất hợp lệ như thế nào?
10. Khi nào một quy trình cần Process Manager thay vì application service hoặc event handler đơn giản?
11. Vì sao một quyết định policy có thể cần lưu reason code, version và thời điểm áp dụng?
12. Knowledge crunching và event storming hỗ trợ quá trình phát triển mô hình như thế nào?
13. Những dấu hiệu nào cho thấy nhóm đang over-modeling?
14. Hãy chọn một quy trình trong miền nghiệp vụ của bạn, xác định ràng buộc, chính sách, trạng thái, domain event và các khái niệm cần đưa vào mô hình.
