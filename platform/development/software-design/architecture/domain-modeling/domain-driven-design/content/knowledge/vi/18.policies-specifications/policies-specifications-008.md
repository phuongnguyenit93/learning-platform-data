# Giới hạn việc xây dựng bộ máy quy tắc khi nhu cầu còn đơn giản

Trong Domain-Driven Design (DDD), **Policy** và **Specification** giúp diễn đạt các quy tắc nghiệp vụ một cách rõ ràng, có thể kiểm thử và tái sử dụng. Tuy nhiên, không phải mọi điều kiện đều cần một lớp Policy, một Specification riêng, bộ kết hợp AND/OR, DSL hay một rule engine. Khi nhu cầu chỉ có vài điều kiện ổn định và chỉ được dùng ở một nơi, một phương thức với câu lệnh if hoặc switch thường là cách thiết kế dễ hiểu nhất.

Điều quan trọng là chọn mức cấu trúc tương xứng với độ phức tạp thực tế. Bắt đầu bằng quy tắc trực tiếp không có nghĩa là xem nhẹ thiết kế. Đó là cách giữ cho mô hình đơn giản khi chưa có lý do để trừu tượng hóa. Khi quy tắc bắt đầu thay đổi thường xuyên, được dùng ở nhiều nơi, có nhiều biến thể hoặc cần cấu hình và giải thích độc lập, nhóm có thể tách dần thành Policy, Specification hoặc một cơ chế quản lý quy tắc chuyên biệt.

## 1. Vì sao cần giới hạn bộ máy quy tắc?

Một bộ máy quy tắc có thể bao gồm nhiều lớp Policy, Specification, interface, factory, registry, rule evaluator, cấu hình và cơ chế kết hợp điều kiện. Những thành phần này hữu ích khi miền nghiệp vụ thực sự có nhiều quy tắc và biến thể. Nhưng nếu nhu cầu còn nhỏ, chúng có thể tạo ra chi phí lớn hơn giá trị nhận được.

Ví dụ, một ứng dụng hiện chỉ cho phép hủy đơn hàng khi đơn còn ở trạng thái DRAFT hoặc CONFIRMED. Nếu tạo riêng:

- CancellationPolicy interface.
- DefaultCancellationPolicy.
- OrderCanBeCancelledSpecification.
- SpecificationEvaluator.
- RuleRegistry.
- RuleFactory.

chỉ để kiểm tra hai trạng thái, người đọc phải lần qua nhiều lớp mới hiểu được một điều kiện đơn giản. Việc thêm abstraction không làm quy tắc rõ hơn nếu tên và cấu trúc không đem lại ý nghĩa mới.

Giới hạn bộ máy quy tắc giúp:

- **Giảm số khái niệm phải học:** nhóm tập trung vào quy tắc nghiệp vụ thay vì framework nội bộ.
- **Giữ luồng xử lý dễ đọc:** người đọc nhìn thấy điều kiện và kết quả tại nơi quyết định.
- **Tránh abstraction chưa có nhu cầu:** không phải duy trì interface, factory và cấu hình chỉ phục vụ một trường hợp.
- **Giảm chi phí kiểm thử:** quy tắc đơn giản có thể được kiểm tra trực tiếp.
- **Tránh tạo ngôn ngữ giả:** không biến một vài điều kiện thành DSL phức tạp mà chuyên gia nghiệp vụ không sử dụng.
- **Giữ đường tiến hóa rõ ràng:** khi độ phức tạp tăng, có thể tách quy tắc theo từng bước thay vì thiết kế sẵn một nền tảng tổng quát.

Mục tiêu không phải loại bỏ Policy hoặc Specification. Mục tiêu là chỉ dùng chúng khi chúng làm cho mô hình dễ hiểu, dễ thay đổi hoặc dễ kiểm chứng hơn.

## 2. Bắt đầu bằng quy tắc trực tiếp

Khi một quy tắc có ít điều kiện, ổn định, chỉ thuộc một đối tượng và chỉ được dùng tại một điểm, hãy đặt nó gần hành vi chịu trách nhiệm.

Ví dụ, một đơn hàng chỉ được hủy khi chưa giao:

~~~java
public void cancel(CancellationReason reason) {
    if (status != OrderStatus.DRAFT
            && status != OrderStatus.CONFIRMED) {
        throw new IllegalStateException("This order cannot be cancelled");
    }

    this.cancellationReason = Objects.requireNonNull(reason);
    this.status = OrderStatus.CANCELLED;
}
~~~

Đây là cách thể hiện tốt nếu quy tắc hủy thuộc vòng đời của Order và không có nhiều biến thể. Aggregate Root bảo vệ trạng thái; caller không thể bỏ qua điều kiện bằng cách tự đặt status.

### 2.1. Điều kiện đơn giản không phải thiết kế kém

Một số dấu hiệu cho thấy điều kiện trực tiếp là đủ:

- Quy tắc có một hoặc vài điều kiện dễ đọc.
- Quy tắc chỉ thuộc một Entity, Aggregate hoặc Domain Service.
- Chỉ có một cách áp dụng trong phạm vi hiện tại.
- Quy tắc ít thay đổi và không cần người dùng nghiệp vụ cấu hình.
- Không cần kết hợp động nhiều điều kiện.
- Không cần giải thích chi tiết vì sao từng điều kiện đúng hoặc sai ngoài thông báo phù hợp.

Ví dụ:

~~~java
public boolean canConfirm() {
    return status == OrderStatus.DRAFT && !lines.isEmpty();
}
~~~

Nếu đây là điều kiện duy nhất để xác nhận đơn và nó chỉ có ý nghĩa trong Order, một phương thức như trên có thể đủ. Không cần tạo Specification chỉ vì điều kiện có thể viết dưới dạng một biểu thức boolean.

### 2.2. Giữ quy tắc ở đúng chủ sở hữu

Đơn giản không có nghĩa đặt mọi điều kiện vào controller hoặc Application Service. Nếu điều kiện bảo vệ bất biến của Aggregate, hãy giữ nó trong Aggregate Root. Nếu quy tắc thuộc một Value Object, đặt nó trong Value Object. Nếu là chính sách liên quan nhiều khái niệm mà không thuộc tự nhiên về một đối tượng, cân nhắc Domain Service.

Ví dụ, quy tắc đơn hàng phải có ít nhất một dòng trước khi xác nhận thuộc Order. Quy tắc tính phí giao hàng theo khu vực và phương thức vận chuyển có thể thuộc một ShippingCostPolicy hoặc Domain Service khi nó không thuộc riêng một đối tượng.

## 3. Phân biệt Policy, Specification và Rule Engine

Ba khái niệm có liên quan đến quy tắc nhưng giải quyết các nhu cầu khác nhau. Hiểu rõ sự khác biệt giúp tránh tạo một bộ máy quá mức cần thiết.

| Khái niệm | Câu hỏi nó trả lời | Hình thức thường gặp |
| --- | --- | --- |
| Policy | Theo chính sách nào thì hành động hoặc quyết định được thực hiện? | Một quy tắc hoặc chiến lược có tên, có thể trả về kết quả hoặc hành động. |
| Specification | Đối tượng hoặc tình huống này có thỏa một điều kiện hay không? | Một predicate có thể kiểm tra, kết hợp hoặc tái sử dụng. |
| Rule Engine | Làm thế nào để quản lý và đánh giá một tập quy tắc có thể thay đổi độc lập với mã ứng dụng? | Bộ đánh giá quy tắc, cấu hình, thứ tự ưu tiên, điều kiện và hành động. |

### 3.1. Policy diễn đạt cách ra quyết định

Policy thường mô tả một chính sách nghiệp vụ, chẳng hạn:

- Chính sách hủy đơn.
- Chính sách tính phí vận chuyển.
- Chính sách phê duyệt tín dụng.
- Chính sách phân bổ tồn kho.
- Chính sách áp dụng chiết khấu.

Một Policy có thể đơn giản là một phương thức trong Entity hoặc Domain Service. Chỉ khi chính sách cần có danh tính, biến thể, cấu hình hoặc được dùng độc lập thì mới cần một abstraction riêng.

### 3.2. Specification diễn đạt điều kiện

Specification thường trả lời câu hỏi một đối tượng có thỏa điều kiện hay không. Ví dụ:

- Đơn có đủ điều kiện hủy không?
- Khách hàng có đủ điều kiện nhận ưu đãi không?
- Sản phẩm có thể được bán trong khu vực này không?
- Yêu cầu có nằm trong hạn mức phê duyệt không?

Specification hữu ích khi predicate có ý nghĩa độc lập, được tái sử dụng hoặc cần kết hợp với các predicate khác. Nếu điều kiện chỉ được kiểm tra một lần và rất ngắn, một if có thể rõ ràng hơn.

### 3.3. Rule Engine dành cho tập quy tắc phức tạp

Rule Engine phù hợp khi tổ chức cần quản lý nhiều quy tắc có thể thay đổi độc lập với chu kỳ phát hành phần mềm, ví dụ:

- Nhiều nhóm nghiệp vụ tự quản lý quy tắc trong phạm vi được kiểm soát.
- Quy tắc có hiệu lực theo thời gian, vùng, sản phẩm hoặc nhóm khách hàng.
- Có thứ tự ưu tiên, xung đột hoặc kết hợp nhiều điều kiện và hành động.
- Cần lưu phiên bản, người thay đổi, lý do và lịch sử đánh giá.
- Cần giải thích vì sao một quyết định được đưa ra.
- Số lượng quy tắc và biến thể vượt quá khả năng quản lý bằng mã nguồn thông thường.

Rule Engine cũng có chi phí: ngôn ngữ cấu hình, xác thực, versioning, kiểm thử, quan sát, bảo mật và xử lý xung đột. Không nên đưa một rule engine vào hệ thống chỉ vì có vài câu if.

## 4. Ví dụ: kiểm tra điều kiện hủy đơn

Giả sử chính sách hiện tại rất đơn giản:

- Đơn DRAFT có thể hủy.
- Đơn CONFIRMED có thể hủy nếu chưa bàn giao vận chuyển.
- Đơn SHIPPED hoặc DELIVERED không thể hủy theo luồng này.

### 4.1. Phiên bản đơn giản

~~~java
public final class Order {
    private OrderStatus status;
    private ShipmentId shipmentId;

    public void cancel(CancellationReason reason) {
        boolean canCancel =
                status == OrderStatus.DRAFT
                || (status == OrderStatus.CONFIRMED && shipmentId == null);

        if (!canCancel) {
            throw new IllegalStateException("Order cannot be cancelled");
        }

        status = OrderStatus.CANCELLED;
    }
}
~~~

Đây là lựa chọn hợp lý nếu chính sách ổn định và chỉ Order sử dụng. Không cần thêm interface hoặc bộ đánh giá điều kiện.

### 4.2. Khi nào nên tách thành Policy?

Giả sử quy tắc bắt đầu thay đổi:

- Hàng đặt trước có thời hạn hủy khác hàng có sẵn.
- Đơn thanh toán bằng tiền mặt có thể hủy sau xác nhận trong một số điều kiện.
- Đơn doanh nghiệp cần người quản lý phê duyệt.
- Một số kênh bán có chính sách riêng.
- Các chính sách được thay đổi theo hợp đồng hoặc khu vực.

Nếu các biến thể này trở thành những chính sách nghiệp vụ có tên và được quản lý riêng, có thể tách:

~~~java
public interface OrderCancellationPolicy {
    CancellationDecision evaluate(OrderCancellationContext context);
}
~~~

~~~java
public record CancellationDecision(
        boolean allowed,
        String reasonCode
) {}
~~~

Application hoặc Domain Service có thể chọn policy phù hợp theo loại đơn và ngữ cảnh. Order vẫn phải kiểm soát các bất biến nội bộ khi thực hiện hành vi cancel.

Không nên đưa việc chọn policy vào Order nếu nó buộc Aggregate phải biết cấu hình hệ thống, kênh bán hoặc cơ chế triển khai. Hãy xác định đâu là dữ liệu miền và đâu là quyết định điều phối.

### 4.3. Không chuyển hết trách nhiệm sang Policy

Policy đánh giá điều kiện có thể hủy, nhưng Aggregate vẫn bảo vệ trạng thái và thay đổi của nó. Một thiết kế không tốt là để Policy tự đặt status hoặc sửa các thuộc tính private của Order thông qua các setter công khai.

Luồng có thể là:

1. Application tải Order và dữ liệu cần thiết.
2. Policy đánh giá điều kiện theo chính sách.
3. Nếu được phép, Application gọi order.cancel(reason).
4. Order kiểm tra bất biến của chính nó và chuyển trạng thái.
5. Application lưu Aggregate.

Nếu điều kiện được đánh giá phụ thuộc trực tiếp vào trạng thái nội bộ của Order, có thể truyền một context bất biến được tạo từ Aggregate hoặc để Aggregate thực hiện phần kiểm tra thuộc quyền sở hữu của nó. Tránh duy trì hai nguồn sự thật có thể lệch nhau.

## 5. Ví dụ: Specification chỉ khi predicate có giá trị độc lập

Giả sử một cửa hàng có điều kiện khách hàng được hưởng ưu đãi:

- Tài khoản đang hoạt động.
- Khách đã xác minh email.
- Tổng chi tiêu trong 12 tháng đạt ngưỡng.

Nếu điều kiện chỉ được dùng ở một nơi, có thể viết:

~~~java
public boolean isEligibleForLoyaltyBenefit(Customer customer) {
    return customer.isActive()
            && customer.emailVerified()
            && customer.spendInLast12Months()
                    .isAtLeast(new Money(new BigDecimal("10000000"), "VND"));
}
~~~

Nếu điều kiện này được sử dụng ở nhiều use case, có thể có ý nghĩa độc lập và cần kết hợp với các điều kiện khác, một Specification sẽ hữu ích:

~~~java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}
~~~

~~~java
public final class EligibleForLoyaltyBenefit
        implements Specification<Customer> {

    private final Money minimumSpend;

    public EligibleForLoyaltyBenefit(Money minimumSpend) {
        this.minimumSpend = minimumSpend;
    }

    @Override
    public boolean isSatisfiedBy(Customer customer) {
        return customer.isActive()
                && customer.emailVerified()
                && customer.spendInLast12Months().isAtLeast(minimumSpend);
    }
}
~~~

Specification này có tên miền rõ ràng và có thể được kiểm thử độc lập. Tuy nhiên, việc tạo interface Specification tổng quát chỉ có ích khi có nhiều specification thực sự cần cùng một hợp đồng.

### 5.1. Kết hợp Specification

Khi nhiều điều kiện có thể được kết hợp theo nhu cầu, có thể bổ sung các phép AND, OR và NOT:

~~~java
public final class AndSpecification<T> implements Specification<T> {
    private final Specification<T> left;
    private final Specification<T> right;

    public AndSpecification(
            Specification<T> left,
            Specification<T> right
    ) {
        this.left = left;
        this.right = right;
    }

    @Override
    public boolean isSatisfiedBy(T candidate) {
        return left.isSatisfiedBy(candidate)
                && right.isSatisfiedBy(candidate);
    }
}
~~~

Đây là một ví dụ về Composite Specification. Chỉ nên thêm cơ chế kết hợp khi nhóm thực sự có các điều kiện độc lập cần tái sử dụng hoặc ghép theo nhiều cách. Nếu chỉ có một predicate ba điều kiện, lớp kết hợp sẽ làm tăng số lượng kiểu mà không tạo thêm giá trị.

### 5.2. Specification dùng cho truy vấn và kiểm tra đối tượng

Một số cách triển khai Specification dùng cùng một khái niệm cho cả:

- Kiểm tra một đối tượng đã tải trong bộ nhớ.
- Chuyển điều kiện thành truy vấn để tìm đối tượng trong cơ sở dữ liệu.

Hai mục tiêu này có thể khác nhau đáng kể. Không nên giả định mọi Specification đều có thể chuyển thành SQL hoặc biểu thức ORM. Nếu cần truy vấn, có thể dùng query object hoặc query service riêng; nếu chỉ kiểm tra quy tắc miền, predicate trong bộ nhớ thường đủ.

## 6. Dấu hiệu cho thấy abstraction đã đến lúc cần thiết

Không có một con số cố định về số điều kiện hoặc số dòng code để quyết định khi nào phải tách Policy hay Specification. Hãy quan sát chi phí thay đổi và mức độ khó hiểu.

| Tín hiệu | Có thể cần | Lý do |
| --- | --- | --- |
| Cùng một quy tắc được sao chép ở nhiều nơi | Phương thức miền hoặc Policy dùng chung | Tránh các nơi diễn giải khác nhau. |
| Quy tắc có nhiều biến thể được gọi tên trong nghiệp vụ | Policy hoặc Strategy | Mỗi biến thể có thể được hiểu và kiểm thử riêng. |
| Predicate được tái sử dụng và kết hợp | Specification | Điều kiện có ý nghĩa độc lập. |
| Quy tắc thay đổi thường xuyên theo thời gian hoặc khu vực | Policy có dữ liệu cấu hình hoặc phiên bản | Tách chính sách khỏi logic ổn định. |
| Người không phát hành code cần chỉnh quy tắc | Cấu hình hoặc Rule Engine có kiểm soát | Thay đổi được quản trị theo quy trình riêng. |
| Cần giải thích và lưu lịch sử quyết định | Decision result, audit hoặc Rule Engine | Có thể truy vết quy tắc và dữ liệu đầu vào. |
| Có thứ tự ưu tiên và xung đột giữa nhiều quy tắc | Bộ đánh giá chuyên biệt | Cần định nghĩa rõ cách giải quyết xung đột. |

Một dấu hiệu đơn lẻ chưa đủ để chọn Rule Engine. Ví dụ, một ngưỡng có thể thay đổi theo cấu hình không nhất thiết cần rule engine; một bảng cấu hình được xác thực và có ngày hiệu lực có thể đủ.

## 7. Tiến hóa từng bước thay vì xây bộ máy từ đầu

Một cách tiếp cận an toàn là bắt đầu với quy tắc trực tiếp và nâng cấp khi có bằng chứng về độ phức tạp.

### Giai đoạn 1: Quy tắc cục bộ

Đặt điều kiện trong phương thức của Entity, Value Object hoặc Domain Service sở hữu nó. Dùng tên phương thức rõ và kiểm thử các trường hợp chính.

Ví dụ: Order kiểm tra trạng thái hiện tại trước khi cho phép hủy.

### Giai đoạn 2: Trích xuất phương thức có tên

Khi điều kiện dài hoặc khó đọc, tách thành phương thức private hoặc phương thức truy vấn có tên miền:

~~~java
private boolean canBeCancelledBeforeShipment() {
    return status == OrderStatus.DRAFT
            || (status == OrderStatus.CONFIRMED && shipmentId == null);
}
~~~

Đây vẫn là cách đơn giản, không cần tạo một abstraction riêng.

### Giai đoạn 3: Tách Policy hoặc Specification

Khi quy tắc được tái sử dụng, có nhiều biến thể hoặc cần kiểm thử và quản lý độc lập, chuyển nó thành một Policy hoặc Specification có tên rõ ràng. Chỉ trích xuất phần quy tắc thực sự có ý nghĩa chung; không tạo framework tổng quát trước khi cần.

### Giai đoạn 4: Đưa dữ liệu chính sách ra cấu hình

Nếu chỉ các tham số như ngưỡng, tỷ lệ hoặc thời hạn thay đổi, có thể lưu chúng trong cấu hình có kiểu, kiểm tra hợp lệ và có hiệu lực rõ ràng. Không cần chuyển toàn bộ logic sang một ngôn ngữ quy tắc.

Ví dụ:

~~~java
public record LoyaltyPolicyConfig(
        Money minimumAnnualSpend,
        BigDecimal discountRate,
        LocalDate effectiveFrom,
        LocalDate effectiveUntil
) {}
~~~

Cần xác định phiên bản cấu hình được dùng cho từng quyết định để tránh cùng một giao dịch bị tính lại theo chính sách mới ngoài ý muốn.

### Giai đoạn 5: Rule Engine khi quản trị quy tắc trở thành yêu cầu

Chỉ cân nhắc Rule Engine khi tổ chức thực sự cần:

- Nhiều quy tắc do các vai trò nghiệp vụ quản lý.
- Thay đổi quy tắc độc lập với chu kỳ triển khai.
- Phiên bản, ngày hiệu lực và lịch sử thay đổi.
- Thứ tự ưu tiên hoặc giải quyết xung đột.
- Giải thích kết quả và truy vết quy tắc đã áp dụng.
- Kiểm thử, phê duyệt và triển khai cấu hình an toàn.

Đây là một năng lực sản phẩm và vận hành, không chỉ là thêm một thư viện.

~~~mermaid
flowchart TD
    A[Phát sinh quy tắc nghiệp vụ] --> B{Quy tắc đơn giản và cục bộ?}
    B -->|Có| C[Giữ điều kiện trong Entity hoặc Domain Service]
    B -->|Không| D{Có ý nghĩa độc lập hoặc được tái sử dụng?}
    D -->|Có| E[Tách Policy hoặc Specification]
    D -->|Không| F[Làm rõ lại trách nhiệm và dữ liệu]
    E --> G{Chỉ tham số thay đổi?}
    G -->|Có| H[Đưa tham số vào cấu hình có kiểm soát]
    G -->|Không| I{Cần quản trị nhiều quy tắc độc lập?}
    I -->|Không| J[Giữ Policy/Specification trong code]
    I -->|Có| K[Đánh giá Rule Engine và quy trình quản trị]
~~~

## 8. Cấu hình không đồng nghĩa với Rule Engine

Một lỗi phổ biến là xem mọi quy tắc có thể thay đổi là cần một rule engine. Thực tế có nhiều mức giải pháp:

| Nhu cầu | Giải pháp thường đủ |
| --- | --- |
| Một ngưỡng cố định trong chính sách | Hằng số có tên trong Domain. |
| Ngưỡng thay đổi theo môi trường | Configuration có kiểu và validation. |
| Tỷ lệ thay đổi theo thời gian | Bảng chính sách có effective date và version. |
| Chọn một trong vài chiến lược đã biết | Strategy hoặc Policy implementation. |
| Kết hợp nhiều predicate có ý nghĩa độc lập | Specification và composition vừa đủ. |
| Người dùng nghiệp vụ tự tạo điều kiện và hành động phức tạp | Rule Engine có quản trị, kiểm thử và audit. |

Ví dụ, nếu tỷ lệ chiết khấu GOLD thay đổi từ 7% thành 8%, một cấu hình có phiên bản có thể đáp ứng. Nếu người dùng nghiệp vụ cần tự tạo các luật như “khách thuộc khu vực A, mua nhóm sản phẩm B, tổng tiền trong khoảng C, trừ D nếu điều kiện E đúng, trừ F nếu điều kiện G đúng”, với thứ tự và ngày hiệu lực khác nhau, nhu cầu đã tiến gần một rule engine.

### 8.1. Cấu hình phải được xác thực

Ngay cả cấu hình đơn giản cũng cần kiểm tra:

- Giá trị có nằm trong phạm vi hợp lệ không?
- Ngày bắt đầu có trước ngày kết thúc không?
- Có khoảng thời gian hiệu lực bị chồng lấn không?
- Đơn vị tiền tệ hoặc đơn vị đo có nhất quán không?
- Khi thiếu cấu hình thì hệ thống dùng giá trị mặc định hay từ chối?
- Quyết định đang xử lý có dùng cùng một phiên bản chính sách không?

Không nên đọc cấu hình tùy ý ở mọi nơi rồi để mỗi lớp tự hiểu ý nghĩa. Hãy chuyển cấu hình thành một đối tượng có kiểu và giao nó cho thành phần chịu trách nhiệm áp dụng chính sách.

## 9. Quản lý nhiều biến thể mà không xây framework quá sớm

Khi có một vài biến thể rõ ràng, Strategy/Policy có thể đủ. Ví dụ:

~~~java
public interface ShippingCostPolicy {
    Money calculate(Shipment shipment, Destination destination);
}
~~~

~~~java
public final class FlatRateShippingPolicy implements ShippingCostPolicy {
    private final Money rate;

    public FlatRateShippingPolicy(Money rate) {
        this.rate = rate;
    }

    @Override
    public Money calculate(Shipment shipment, Destination destination) {
        return rate;
    }
}
~~~

~~~java
public final class WeightBasedShippingPolicy implements ShippingCostPolicy {
    private final Money pricePerKilogram;

    public WeightBasedShippingPolicy(Money pricePerKilogram) {
        this.pricePerKilogram = pricePerKilogram;
    }

    @Override
    public Money calculate(Shipment shipment, Destination destination) {
        return pricePerKilogram.multiply(shipment.totalWeightInKilograms());
    }
}
~~~

Hai implementation được gọi tên theo chính sách cụ thể. Application hoặc một factory đơn giản có thể chọn implementation theo loại dịch vụ. Chưa cần registry động, rule parser hoặc DSL nếu số biến thể ít và được kiểm soát bởi code.

Khi số biến thể tăng, trước tiên hãy tìm xem chúng thực sự khác nhau ở đâu. Có thể chúng chỉ khác tham số, có thể chúng là các chính sách độc lập, hoặc có thể nhiều điều kiện đang bị trộn trong cùng một chính sách. Chọn cấu trúc nhỏ nhất phản ánh được sự khác biệt đó.

## 10. Tránh lạm dụng Specification

Specification là một mẫu hữu ích nhưng có thể bị dùng quá mức:

### 10.1. Một if đơn giản bị bọc qua nhiều lớp

Nếu cần đi qua một factory, interface, implementation và evaluator chỉ để kiểm tra một điều kiện, abstraction có thể không đáng giá. Hãy giữ biểu thức tại nơi có ý nghĩa.

### 10.2. Mọi predicate đều trở thành Specification

Không phải mọi phương thức boolean đều cần một lớp riêng. Một điều kiện nội bộ chỉ dùng một lần có thể là phương thức private hoặc getter có tên rõ.

### 10.3. Specification biết quá nhiều về hạ tầng

Một Specification miền không nên phụ thuộc EntityManager, SQL hoặc HTTP. Nếu cần kiểm tra dữ liệu bên ngoài, Application tải dữ liệu trước hoặc dùng một abstraction phù hợp; đừng biến Specification thành nơi thực hiện truy vấn tùy tiện.

### 10.4. Kết hợp điều kiện mà không rõ ý nghĩa

Một biểu thức AND/OR phức tạp có thể hợp lệ về mặt kỹ thuật nhưng khó hiểu với nghiệp vụ. Hãy đặt tên cho nhóm điều kiện có ý nghĩa, chẳng hạn EligibleForPremiumShipping, thay vì để người đọc giải mã một cây boolean sâu.

### 10.5. Trộn Specification dùng trong bộ nhớ với truy vấn database

Một predicate Java không nhất thiết chuyển được thành SQL. Nếu có nhu cầu truy vấn phức tạp, hãy thiết kế query model riêng thay vì hứa rằng mọi Specification đều có thể chạy ở mọi nơi.

## 11. Kiểm thử quy tắc ở mức phù hợp

Mức abstraction càng cao không tự động làm kiểm thử tốt hơn. Kiểm thử cần tập trung vào hành vi nghiệp vụ và các trường hợp biên.

Với điều kiện đơn giản:

- Kiểm tra trạng thái được phép.
- Kiểm tra trạng thái bị từ chối.
- Kiểm tra trạng thái không thay đổi khi hành động thất bại.

Với Policy:

- Kiểm tra từng biến thể chính sách.
- Kiểm tra ngưỡng, ngoại lệ và kết quả.
- Kiểm tra phiên bản hoặc thời điểm hiệu lực nếu có.

Với Specification:

- Kiểm tra predicate đúng và sai.
- Kiểm tra phép AND/OR/NOT nếu thực sự được dùng.
- Kiểm tra các trường hợp biên và dữ liệu thiếu.

Với Rule Engine:

- Kiểm tra từng rule và bộ quy tắc kết hợp.
- Kiểm tra thứ tự ưu tiên, xung đột và trường hợp không có rule phù hợp.
- Kiểm tra phiên bản, phê duyệt và rollback cấu hình.
- Kiểm tra khả năng giải thích vì sao một kết quả được chọn.
- Kiểm tra hiệu năng và giới hạn tài nguyên khi tập quy tắc lớn.

Ví dụ JUnit cho quy tắc hủy đơn trực tiếp:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class OrderCancellationTest {
    @Test
    void draftOrderCanBeCancelled() {
        Order order = Order.draft(new OrderId("ORD-1"));

        order.cancel(new CancellationReason("Customer request"));

        assertEquals(OrderStatus.CANCELLED, order.status());
    }

    @Test
    void shippedOrderCannotBeCancelled() {
        Order order = Order.shipped(
                new OrderId("ORD-2"),
                new ShipmentId("SHP-1")
        );

        assertThrows(
                IllegalStateException.class,
                () -> order.cancel(new CancellationReason("Customer request"))
        );
        assertEquals(OrderStatus.SHIPPED, order.status());
    }
}
~~~

Các factory và kiểu dữ liệu trong ví dụ được giả định thuộc mô hình Order. Điều quan trọng là kiểm thử thể hiện được chính sách được xác nhận, không phụ thuộc việc quy tắc được viết trong if hay trong một lớp Specification.

## 12. Những sai lầm thường gặp

### 12.1. Xây Rule Engine trước khi có nhu cầu

Một vài điều kiện ổn định không cần hệ thống quản lý rule, DSL hoặc giao diện cấu hình. Hãy bắt đầu từ mã miền đơn giản và quan sát chi phí thay đổi.

### 12.2. Trừu tượng hóa chỉ để tránh if/else

If/else không phải vấn đề tự thân. Nếu điều kiện ngắn, có tên rõ và thuộc đúng nơi, nó có thể là biểu đạt tốt nhất của quy tắc.

### 12.3. Đưa quy tắc vào cấu hình mà không có quản trị

Cho phép sửa ngưỡng hoặc điều kiện trực tiếp trong database mà không có validation, version, quyền và audit có thể tạo rủi ro lớn hơn việc giữ quy tắc trong code.

### 12.4. Tạo một Policy chung cho nhiều quy tắc không liên quan

Một lớp BusinessPolicy với hàng chục phương thức không tạo ra mô hình rõ ràng. Hãy nhóm theo khái niệm nghiệp vụ có ý nghĩa.

### 12.5. Nhầm Policy với Specification

Policy thường diễn đạt cách ra quyết định hoặc hành vi theo chính sách; Specification thường diễn đạt một điều kiện. Có thể dùng cả hai cùng nhau, nhưng không cần ép mọi quy tắc vào một mẫu.

### 12.6. Để Application Service sở hữu mọi điều kiện miền

Khi điều kiện bảo vệ bất biến của Aggregate, nó cần được kiểm tra tại Aggregate. Application có thể phối hợp dữ liệu và chọn policy, nhưng không nên là nơi duy nhất bảo vệ trạng thái.

### 12.7. Để Policy tự sửa Aggregate

Policy nên trả về quyết định hoặc kết quả nghiệp vụ. Aggregate vẫn kiểm soát thay đổi trạng thái thông qua hành vi của chính nó.

### 12.8. Không xác định ai sở hữu chính sách

Một quy tắc có thể liên quan đến nhiều Bounded Context. Cần xác định Context nào sở hữu ý nghĩa và quyết định; không tạo một thư viện quy tắc dùng chung làm mờ ranh giới ngôn ngữ.

## 13. Quy trình quyết định mức độ thiết kế

Khi gặp một quy tắc mới, nhóm có thể dùng các câu hỏi sau:

1. Quy tắc này thuộc Aggregate hoặc Value Object nào?
2. Có phải một điều kiện ngắn, ổn định và chỉ dùng ở một nơi không?
3. Nếu điều kiện dài, có thể đặt tên cho một phương thức để làm rõ ý nghĩa không?
4. Quy tắc có được tái sử dụng hoặc có nhiều biến thể nghiệp vụ được gọi tên không?
5. Nó là một quyết định theo Policy hay một predicate phù hợp với Specification?
6. Chỉ tham số thay đổi hay cả logic và cấu trúc quy tắc thay đổi?
7. Ai cần thay đổi quy tắc: đội phát triển hay người dùng nghiệp vụ?
8. Có cần version, ngày hiệu lực, audit, giải thích và phê duyệt không?
9. Chi phí vận hành Rule Engine có nhỏ hơn lợi ích mà tổ chức nhận được không?

Kết quả có thể là:

- Giữ if/else hoặc switch trong mô hình.
- Trích xuất một phương thức có tên rõ.
- Tách một Policy hoặc Domain Service.
- Tạo Specification khi predicate có ý nghĩa độc lập.
- Dùng cấu hình có kiểu và version.
- Chọn Rule Engine khi quản trị quy tắc đã trở thành một yêu cầu thực sự.

Không cần đi qua tất cả các mức. Hãy chọn mức đơn giản nhất đáp ứng nhu cầu hiện tại mà vẫn giữ đường tiến hóa hợp lý.

## 14. Checklist giới hạn bộ máy quy tắc

- [ ] Quy tắc được đặt tại đúng chủ sở hữu nghiệp vụ.
- [ ] Một điều kiện đơn giản không bị bọc qua nhiều lớp không cần thiết.
- [ ] If/else hoặc switch được dùng khi chúng là biểu đạt dễ hiểu nhất.
- [ ] Policy chỉ được tách khi có chính sách hoặc biến thể có ý nghĩa độc lập.
- [ ] Specification chỉ được tách khi predicate có giá trị tái sử dụng hoặc kết hợp.
- [ ] Rule Engine chỉ được cân nhắc khi có nhu cầu quản trị quy tắc độc lập.
- [ ] Cấu hình có kiểu, validation, version và thời điểm hiệu lực khi cần.
- [ ] Aggregate vẫn bảo vệ các bất biến của nó.
- [ ] Quy tắc có kiểm thử cho trường hợp đúng, sai và biên.
- [ ] Có thể giải thích vì sao một quyết định được đưa ra ở mức phù hợp.
- [ ] Chi phí vận hành abstraction không vượt giá trị mà nó mang lại.
- [ ] Có thể tách dần khi quy tắc thực sự trở nên phức tạp.

## 15. Kết luận

DDD cung cấp Policy và Specification để mô hình hóa quy tắc nghiệp vụ, nhưng không yêu cầu mọi điều kiện phải trở thành một đối tượng hoặc một phần của bộ máy quy tắc. Khi quy tắc còn ngắn, ổn định và thuộc một Aggregate, một phương thức trực tiếp thường là lựa chọn rõ ràng. Khi chính sách có biến thể, được tái sử dụng hoặc cần quản lý độc lập, có thể tách Policy hoặc Specification. Cấu hình có kiểu đủ cho nhiều trường hợp chỉ thay đổi tham số; Rule Engine chỉ phù hợp khi tổ chức cần quản trị một tập quy tắc phức tạp theo quy trình riêng.

Hãy để độ phức tạp nghiệp vụ dẫn dắt mức độ trừu tượng. Bắt đầu đơn giản, đặt quy tắc đúng nơi, kiểm thử hành vi và chỉ nâng cấp cấu trúc khi có tín hiệu cụ thể. Cách tiếp cận này giữ cho mô hình dễ đọc hôm nay mà vẫn có khả năng tiến hóa khi nhu cầu thay đổi.
