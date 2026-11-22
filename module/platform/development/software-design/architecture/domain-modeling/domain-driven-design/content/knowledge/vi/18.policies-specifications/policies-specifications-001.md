# Chính sách nghiệp vụ: quy tắc ra quyết định có tên rõ ràng

Trong Domain-Driven Design (DDD), nhiều hành vi nghiệp vụ không chỉ là một phép kiểm tra đơn giản trên entity. Doanh nghiệp có thể có chính sách xác định mức chiết khấu, điều kiện duyệt tín dụng, thứ tự ưu tiên xử lý đơn, cách chọn phương thức giao hàng hoặc điều kiện được hoàn phí. Các quyết định này thường phụ thuộc vào nhiều dữ liệu và có thể thay đổi theo chiến lược, thời điểm hoặc loại khách hàng.

**Business Policy (chính sách nghiệp vụ)** là một quy tắc ra quyết định có ý nghĩa trong domain, được đặt tên và mô hình hóa rõ ràng. Thay vì để nhiều service tự viết các nhánh `if/else` tương tự, nhóm gom quyết định vào một abstraction có ngôn ngữ nghiệp vụ, đầu vào và kết quả dễ hiểu. Application hoặc aggregate sử dụng policy để ra quyết định; domain vẫn bảo vệ các invariant không được phép vi phạm.

Chính sách có thể được biểu diễn bằng một object, domain service hoặc một tập quy tắc có thể kết hợp. Không phải mọi điều kiện đều cần một class riêng. Chỉ tách policy khi tên gọi, khả năng thay đổi, mức độ phức tạp hoặc việc tái sử dụng làm cho nó trở thành một khái niệm nghiệp vụ đáng được quản lý.

## 1. Chính sách nghiệp vụ là gì?

Một chính sách nghiệp vụ mô tả cách tổ chức đưa ra quyết định trong một tình huống nhất định. Nó trả lời câu hỏi: **với bối cảnh và dữ liệu này, doanh nghiệp nên cho phép, từ chối, chọn hoặc tính điều gì?**

Ví dụ:

- Khách hàng thuộc hạng Gold được áp dụng mức chiết khấu nào?
- Đơn hàng có đủ điều kiện giao miễn phí không?
- Một hồ sơ vay có đáp ứng điều kiện duyệt tự động không?
- Khi tồn kho khan hiếm, đơn nào được ưu tiên phân bổ trước?
- Khách hàng được hoàn bao nhiêu khi hủy dịch vụ ở một thời điểm cụ thể?
- Giao dịch nào cần chuyển sang kiểm tra thủ công?

Những câu hỏi này không nhất thiết thuộc về một entity duy nhất. Chúng có thể cần kết hợp thông tin khách hàng, sản phẩm, đơn hàng, thời điểm, hợp đồng hoặc chính sách đang có hiệu lực.

### 1.1. Đặc điểm của một policy tốt

Một policy có ý nghĩa nghiệp vụ thường có các đặc điểm:

- **Có tên diễn đạt quyết định:** ví dụ `ShippingEligibilityPolicy`, `CreditApprovalPolicy`, `DiscountPolicy`.
- **Có phạm vi áp dụng:** cho biết loại nghiệp vụ, khách hàng, sản phẩm hoặc tình huống nào.
- **Có đầu vào rõ:** chỉ nhận dữ liệu cần thiết để ra quyết định.
- **Có kết quả rõ:** trả quyết định, mức tính toán hoặc lý do từ chối.
- **Có người sở hữu nghiệp vụ:** domain expert hoặc vai trò có thẩm quyền giải thích và xác nhận quy tắc.
- **Có thể thay đổi có kiểm soát:** khi chính sách đổi, nhóm biết nơi cập nhật, phiên bản nào có hiệu lực và các ca kiểm thử cần điều chỉnh.

Không phải policy nào cũng cần thay thế được bằng nhiều implementation. Một quy tắc đơn giản và ổn định có thể được biểu diễn trực tiếp trong aggregate. Policy abstraction hữu ích khi quyết định có bản sắc riêng hoặc có khả năng biến đổi độc lập.

## 2. Vì sao cần đặt tên và mô hình hóa policy?

Giả sử nhiều use case cần xác định chiết khấu cho khách hàng. Ban đầu, mỗi service có thể tự viết:

```java
if (customer.isGold()) {
    discount = total.multiply(new BigDecimal("0.10"));
} else if (customer.isSilver()) {
    discount = total.multiply(new BigDecimal("0.05"));
} else {
    discount = BigDecimal.ZERO;
}
```

Sau một thời gian, quy tắc được sao chép trong checkout, báo giá, xử lý đơn hàng và chương trình chăm sóc khách hàng. Một nơi thêm ngoại lệ cho sản phẩm khuyến mãi, nơi khác quên cập nhật. Hệ thống đưa ra các quyết định khác nhau cho cùng một khách hàng và cùng một tình huống.

Khi mô hình hóa thành `CustomerDiscountPolicy`, nhóm có thể:

- Dùng chung một định nghĩa quyết định trong những use case có cùng ngữ nghĩa.
- Đặt tên để domain expert và developer cùng thảo luận.
- Kiểm thử các mức hạng, ngoại lệ và ranh giới số tiền một cách tập trung.
- Thay đổi chính sách mà không phải tìm và sửa các nhánh điều kiện rải rác.
- Ghi nhận lý do quyết định để giải thích cho người dùng hoặc bộ phận vận hành.

### 2.1. Policy làm cho quy tắc trở nên có thể thảo luận

Một đoạn điều kiện kỹ thuật như `if (score >= 720 && debtRatio < 0.4)` không tự nói lên mục đích nghiệp vụ. Một policy có tên `AutomaticCreditApprovalPolicy` cho biết đây là quyết định duyệt tín dụng tự động. Nhóm có thể thảo luận ai được áp dụng, dữ liệu nào có thẩm quyền, ngưỡng nào được phép thay đổi và trường hợp nào cần chuyển sang chuyên viên.

Tên policy nên dùng ngôn ngữ mà domain expert nhận ra. Tránh tên chung như `RuleManager`, `BusinessHelper` hoặc `CommonValidator` nếu chúng không nói rõ quyết định nào đang được mô hình hóa.

## 3. Phân biệt Policy, Invariant, Specification và Validation

Các khái niệm này có liên hệ nhưng giải quyết những câu hỏi khác nhau. Phân biệt chúng giúp tránh đặt sai trách nhiệm.

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Invariant** | Điều gì luôn phải đúng để trạng thái domain hợp lệ? | Số lượng tồn kho khả dụng không được âm |
| **Policy** | Trong bối cảnh này, quyết định nghiệp vụ nào được đưa ra? | Khách hàng Gold được giảm 10% cho nhóm sản phẩm đủ điều kiện |
| **Specification** | Đối tượng có thỏa một điều kiện xác định hay không? | Khách hàng có đủ điều kiện mua trả góp không? |
| **Input validation** | Dữ liệu đầu vào có đúng định dạng và giới hạn cơ bản không? | Email đúng định dạng, page size không âm |
| **Authorization** | Actor hiện tại có quyền thực hiện hành động không? | Nhân viên có quyền phê duyệt hồ sơ này không? |

### 3.1. Policy và invariant

Invariant bảo vệ tính hợp lệ của trạng thái. Nó không nên bị bỏ qua chỉ vì policy thay đổi. Policy có thể quyết định mức chiết khấu hoặc điều kiện ưu tiên, nhưng aggregate vẫn phải bảo vệ invariant như tổng tiền không âm hoặc trạng thái đơn chuyển tiếp hợp lệ.

Ví dụ, policy quyết định khách hàng được giảm 10% hay 5%. Aggregate `Order` vẫn phải bảo đảm chiết khấu không vượt tổng giá trị hàng hóa theo quy tắc của đơn. Policy cung cấp quyết định; aggregate kiểm tra và áp dụng quyết định đó sao cho trạng thái cuối hợp lệ.

### 3.2. Policy và Specification

Specification thường biểu diễn một predicate: một đối tượng hoặc tập dữ liệu có thỏa điều kiện hay không. Ví dụ `EligibleForInstallmentSpecification` có thể trả về `true/false`.

Policy thường có phạm vi rộng hơn: nó có thể chọn một trong nhiều kết quả, tính mức áp dụng, quyết định bước tiếp theo hoặc trả về lý do. Một policy có thể sử dụng một hoặc nhiều specification làm điều kiện.

Ví dụ:

```java
boolean eligible = eligibleForInstallment.isSatisfiedBy(application);
```

so với:

```java
CreditDecision decision = creditApprovalPolicy.decide(application);
```

`CreditDecision` có thể là `APPROVE`, `REJECT` hoặc `MANUAL_REVIEW`, kèm mã lý do và hạn mức đề xuất. Dùng specification khi câu hỏi là “có thỏa điều kiện không”; dùng policy khi cần diễn đạt một quyết định nghiệp vụ có kết quả rõ ràng hơn.

### 3.3. Policy và validation

Validation thường kiểm tra tính đúng đắn cơ bản của dữ liệu nhận vào, ví dụ trường bắt buộc, định dạng ngày hoặc số lượng phải lớn hơn 0. Policy sử dụng dữ liệu hợp lệ để đưa ra quyết định nghiệp vụ.

Ví dụ, `quantity = -1` là input không hợp lệ. Một đơn có số lượng hợp lệ nhưng vượt giới hạn mua tối đa theo chương trình là quyết định nghiệp vụ của `PurchaseLimitPolicy`.

## 4. Đặt policy ở đúng nơi trong mô hình

Không phải mọi policy đều phải nằm trong domain layer. Vị trí phụ thuộc vào bản chất của quyết định.

### 4.1. Domain policy

Nếu quy tắc thể hiện kiến thức nghiệp vụ và có thể diễn đạt độc lập với giao thức hoặc framework, nó thuộc domain. Policy có thể là một domain service hoặc một object có interface rõ ràng.

Ví dụ: chính sách tính chiết khấu theo hạng khách hàng và loại sản phẩm; chính sách đủ điều kiện hoàn phí; chính sách xác định mức hạn mức tín dụng ban đầu.

### 4.2. Application policy

Một số quyết định điều phối cách use case được thực hiện, nhưng không phải quy tắc cốt lõi của domain. Ví dụ chọn một nhà cung cấp tích hợp theo độ sẵn sàng kỹ thuật, quyết định gọi service nào trước hoặc chọn cách retry. Những quyết định này có thể thuộc application/infrastructure policy.

Hãy tránh đặt mọi cấu hình kỹ thuật vào domain chỉ vì chúng có từ “policy”. Chính sách retry HTTP hoặc circuit breaker là chính sách vận hành kỹ thuật, không phải business policy.

### 4.3. Quy tắc thuộc về aggregate

Nếu điều kiện gắn chặt với trạng thái nội tại của một aggregate và không cần phối hợp kiến thức bên ngoài, đặt nó trong hành vi của aggregate thường rõ ràng hơn.

Ví dụ, `Order.cancel()` kiểm tra đơn có đang ở trạng thái cho phép hủy không. Nếu điều kiện hủy còn phụ thuộc thời điểm, loại hợp đồng, lịch sử thanh toán và chính sách hoàn tiền, một policy riêng có thể quyết định quyền hủy; aggregate vẫn thực thi chuyển trạng thái hợp lệ.

### 4.4. Bảng định hướng vị trí

| Câu hỏi | Vị trí thường phù hợp |
|---|---|
| Đơn có thể chuyển từ `SHIPPED` sang `CANCELLED` không? | Aggregate `Order` |
| Khách hàng được giảm bao nhiêu theo chương trình hiện hành? | Domain policy |
| Hồ sơ vay nên được duyệt, từ chối hay chuyển kiểm tra thủ công? | Domain policy / domain service |
| Request có trường bắt buộc và đúng định dạng không? | Inbound adapter / validation boundary |
| Actor có quyền phê duyệt hồ sơ không? | Authorization/application security policy |
| Nên retry HTTP call tối đa bao nhiêu lần? | Infrastructure/resilience policy |
| Dùng nhà cung cấp thanh toán nào theo cấu hình vận hành? | Application/infrastructure policy, trừ khi lựa chọn là quy tắc sản phẩm |

Ranh giới cụ thể có thể khác theo mô hình. Hãy hỏi quyết định đó có ý nghĩa nghiệp vụ gì và ai chịu trách nhiệm xác nhận nó.

## 5. Mô hình hóa policy bằng interface và kết quả quyết định

Khi một policy có thể có nhiều implementation hoặc cần được thay đổi độc lập, có thể định nghĩa interface.

Ví dụ chính sách chiết khấu:

```java
public interface DiscountPolicy {
    DiscountDecision decide(DiscountContext context);
}
```

Đầu vào `DiscountContext` chứa dữ liệu cần thiết:

```java
public record DiscountContext(
    CustomerTier customerTier,
    List<OrderLineSnapshot> lines,
    Money subtotal,
    Instant decisionTime,
    SalesChannel salesChannel
) {}
```

Kết quả nên diễn đạt quyết định nghiệp vụ, không chỉ là một số thập phân không có ngữ cảnh:

```java
public record DiscountDecision(
    Money amount,
    String policyCode,
    String reasonCode
) {}
```

Một implementation:

```java
public final class TieredDiscountPolicy implements DiscountPolicy {
    @Override
    public DiscountDecision decide(DiscountContext context) {
        BigDecimal rate = switch (context.customerTier()) {
            case GOLD -> new BigDecimal("0.10");
            case SILVER -> new BigDecimal("0.05");
            case STANDARD -> BigDecimal.ZERO;
        };

        Money amount = context.subtotal().multiply(rate);
        return new DiscountDecision(
            amount,
            "TIERED_DISCOUNT_V1",
            "CUSTOMER_TIER_" + context.customerTier()
        );
    }
}
```

Ví dụ đã lược bỏ quy tắc làm tròn, giới hạn tối đa và loại sản phẩm bị loại trừ. Hệ thống thực tế phải định nghĩa các điều kiện này bằng nghiệp vụ và dùng kiểu tiền tệ có currency rõ ràng.

### 5.1. Vì sao trả Decision object?

Một quyết định nghiệp vụ thường cần giải thích được. Thay vì chỉ trả `true/false` hoặc `10`, decision object có thể chứa:

- Kết quả: được phép, từ chối, cần duyệt thủ công hoặc mức được áp dụng.
- Mã policy và phiên bản đã dùng.
- Mã lý do để audit hoặc giải thích.
- Các điều kiện còn thiếu hoặc bước tiếp theo.
- Thời điểm quyết định và dữ liệu tham chiếu nếu cần lưu lịch sử.

Không nên đưa toàn bộ dữ liệu nhạy cảm vào decision hoặc log. Chỉ lưu thông tin cần thiết cho khả năng giải thích, audit và tuân thủ.

### 5.2. Policy nên thuần và xác định được

Nếu cùng một input và cùng phiên bản policy mà kết quả thay đổi tùy thời gian hệ thống, random hoặc trạng thái ẩn, việc kiểm thử và giải thích sẽ khó khăn. Khi thời gian là yếu tố nghiệp vụ, truyền `decisionTime` vào context. Khi cần random hoặc dữ liệu ngoài, mô hình hóa dependency và ghi nhận kết quả đầu vào đã dùng.

Một policy thuần thường không tự truy cập database hoặc gọi HTTP. Application chuẩn bị dữ liệu cần thiết rồi truyền vào. Nếu policy thực sự cần một dịch vụ domain-facing, hãy định nghĩa abstraction phù hợp và làm rõ tác động của nó đến transaction, độ trễ và khả năng kiểm thử.

## 6. Ví dụ 1: chính sách chiết khấu

Một cửa hàng có chương trình thành viên. Mức chiết khấu phụ thuộc vào hạng khách hàng và nhóm sản phẩm. Một số sản phẩm đang khuyến mãi không được cộng thêm chiết khấu thành viên.

### 6.1. Xác định quy tắc

Giả sử chính sách minh họa:

| Hạng khách hàng | Mức giảm trên sản phẩm đủ điều kiện |
|---|---:|
| Standard | 0% |
| Silver | 5% |
| Gold | 10% |

Ngoại lệ: sản phẩm có `promotionType = EXCLUSIVE` không được áp dụng thêm chiết khấu thành viên. Chiết khấu được tính theo từng dòng hàng đủ điều kiện, sau đó cộng lại.

### 6.2. Cài đặt policy

```java
public final class MemberDiscountPolicy implements DiscountPolicy {
    @Override
    public DiscountDecision decide(DiscountContext context) {
        BigDecimal rate = rateFor(context.customerTier());

        Money discount = context.lines().stream()
            .filter(line -> !line.exclusivePromotion())
            .map(line -> line.lineTotal().multiply(rate))
            .reduce(Money.zero(context.subtotal().currency()), Money::add);

        return new DiscountDecision(
            discount,
            "MEMBER_DISCOUNT_V1",
            "TIER_" + context.customerTier()
        );
    }

    private BigDecimal rateFor(CustomerTier tier) {
        return switch (tier) {
            case GOLD -> new BigDecimal("0.10");
            case SILVER -> new BigDecimal("0.05");
            case STANDARD -> BigDecimal.ZERO;
        };
    }
}
```

### 6.3. Áp dụng quyết định vào aggregate

Policy đưa ra mức giảm; `Order` chịu trách nhiệm áp dụng kết quả và bảo vệ invariant của đơn:

```java
public void applyDiscount(DiscountDecision decision) {
    if (status != OrderStatus.DRAFT) {
        throw new OrderCannotBeChangedException(id);
    }
    if (decision.amount().isNegative() || decision.amount().isGreaterThan(subtotal)) {
        throw new InvalidDiscountException(decision.amount());
    }
    this.discount = decision.amount();
    this.discountPolicyCode = decision.policyCode();
}
```

Việc tách này giữ đúng hai trách nhiệm: policy xác định mức được hưởng; aggregate kiểm tra việc áp dụng không phá vỡ trạng thái hợp lệ của đơn. Nếu aggregate chỉ cho phép tính lại chiết khấu ở trạng thái `DRAFT`, quy tắc đó vẫn được bảo vệ dù caller nào sử dụng policy.

## 7. Ví dụ 2: chính sách duyệt tín dụng

Một tổ chức tài chính nhận hồ sơ cấp hạn mức. Quyết định có thể là:

- `APPROVE`: đáp ứng điều kiện duyệt tự động.
- `REJECT`: vi phạm điều kiện từ chối rõ ràng.
- `MANUAL_REVIEW`: cần chuyên viên đánh giá thêm.

Không nên biểu diễn tất cả bằng boolean, vì `false` có thể có nghĩa là bị từ chối hoặc chỉ là chưa đủ dữ liệu.

### 7.1. Định nghĩa decision

```java
public enum CreditDecisionType {
    APPROVE,
    REJECT,
    MANUAL_REVIEW
}

public record CreditDecision(
    CreditDecisionType type,
    Money proposedLimit,
    List<String> reasonCodes,
    String policyVersion
) {}
```

### 7.2. Policy

```java
public interface CreditApprovalPolicy {
    CreditDecision decide(CreditApplicationSnapshot application);
}

public final class StandardCreditApprovalPolicy implements CreditApprovalPolicy {
    @Override
    public CreditDecision decide(CreditApplicationSnapshot application) {
        if (application.isIdentityUnverified()) {
            return manualReview("IDENTITY_REVIEW_REQUIRED");
        }
        if (application.hasFraudAlert()) {
            return reject("FRAUD_ALERT");
        }
        if (application.debtToIncomeRatio().compareTo(new BigDecimal("0.45")) > 0) {
            return reject("DEBT_RATIO_TOO_HIGH");
        }
        if (application.creditScore() < 680) {
            return manualReview("CREDIT_SCORE_REVIEW");
        }
        return approve(application.requestedLimit());
    }

    private CreditDecision reject(String reason) {
        return new CreditDecision(CreditDecisionType.REJECT, null,
            List.of(reason), "STANDARD_CREDIT_V1");
    }

    private CreditDecision manualReview(String reason) {
        return new CreditDecision(CreditDecisionType.MANUAL_REVIEW, null,
            List.of(reason), "STANDARD_CREDIT_V1");
    }

    private CreditDecision approve(Money limit) {
        return new CreditDecision(CreditDecisionType.APPROVE, limit,
            List.of("AUTOMATIC_APPROVAL"), "STANDARD_CREDIT_V1");
    }
}
```

Các ngưỡng và quy tắc ở đây chỉ minh họa cách tổ chức code; chúng không phải khuyến nghị tín dụng. Trong hệ thống thực tế, chính sách phải được phê duyệt bởi người có thẩm quyền, có nguồn dữ liệu xác định, xử lý trường hợp thiếu dữ liệu và tuân thủ quy định liên quan.

### 7.3. Application điều phối quyết định

Application service tải hồ sơ và dữ liệu cần thiết, gọi policy, sau đó thực hiện hành vi tương ứng:

```java
CreditDecision decision = approvalPolicy.decide(application.snapshot());

switch (decision.type()) {
    case APPROVE -> application.approve(decision.proposedLimit(), decision.policyVersion());
    case REJECT -> application.reject(decision.reasonCodes(), decision.policyVersion());
    case MANUAL_REVIEW -> application.requestManualReview(decision.reasonCodes());
}

applicationRepository.save(application);
```

Policy không tự lưu hồ sơ và không gửi email. Nó đưa ra quyết định. Application điều phối workflow; aggregate kiểm tra chuyển trạng thái hợp lệ và lưu lại kết quả quyết định.

## 8. Ví dụ 3: chính sách lựa chọn phương thức giao hàng

Một đơn hàng có thể giao tiêu chuẩn, giao nhanh hoặc nhận tại cửa hàng. Việc lựa chọn phụ thuộc khu vực, kích thước kiện, thời gian cam kết, giá trị đơn và năng lực của đơn vị vận chuyển.

Thay vì đặt nhiều nhánh điều kiện trong checkout, có thể tạo `ShippingMethodPolicy`:

```java
public interface ShippingMethodPolicy {
    ShippingDecision decide(ShippingContext context);
}

public record ShippingDecision(
    ShippingMethod method,
    Money fee,
    Instant estimatedDelivery,
    String reasonCode
) {}
```

Một implementation có thể:

1. Loại phương thức không phục vụ khu vực giao.
2. Loại phương thức không đáp ứng kích thước hoặc trọng lượng.
3. Tính phí theo chính sách.
4. Chọn phương thức đáp ứng cam kết thời gian và ưu tiên chi phí.
5. Trả lý do nếu không có phương thức phù hợp.

Nếu dữ liệu năng lực vận chuyển đến từ nhà cung cấp bên ngoài, application hoặc adapter tải snapshot năng lực trước khi gọi policy. Không nên để policy domain gọi trực tiếp API hãng vận chuyển trong lúc đang tính quyết định.

## 9. Kết hợp nhiều policy

Một quyết định lớn có thể cần nhiều policy nhỏ. Ví dụ xác định giá cuối cùng có thể cần:

- `BasePricePolicy`: giá cơ sở theo sản phẩm và kênh bán.
- `CustomerDiscountPolicy`: mức giảm theo hạng khách hàng.
- `PromotionEligibilityPolicy`: xác định sản phẩm hoặc đơn đủ điều kiện khuyến mãi.
- `ShippingFeePolicy`: tính phí giao hàng.
- `TaxPolicy`: tính thuế theo khu vực và loại hàng.

Không nên tạo một `PricingPolicy` khổng lồ chứa mọi điều kiện nếu các phần có chủ sở hữu, chu kỳ thay đổi hoặc ý nghĩa khác nhau. Tuy nhiên, nếu các quy tắc luôn thay đổi cùng nhau và chỉ có một quyết định thống nhất, một policy tổng hợp có thể hợp lý.

### 9.1. Policy composition

Một policy có thể sử dụng policy khác qua abstraction:

```java
public final class CheckoutPricingPolicy {
    private final BasePricePolicy basePricePolicy;
    private final DiscountPolicy discountPolicy;
    private final TaxPolicy taxPolicy;

    public CheckoutPricingPolicy(BasePricePolicy basePricePolicy,
                                 DiscountPolicy discountPolicy,
                                 TaxPolicy taxPolicy) {
        this.basePricePolicy = basePricePolicy;
        this.discountPolicy = discountPolicy;
        this.taxPolicy = taxPolicy;
    }

    public PriceBreakdown calculate(CheckoutContext context) {
        Money subtotal = basePricePolicy.calculate(context);
        DiscountDecision discount = discountPolicy.decide(
            context.toDiscountContext(subtotal));
        Money taxableAmount = subtotal.subtract(discount.amount());
        Money tax = taxPolicy.calculate(taxableAmount, context.taxContext());

        return new PriceBreakdown(subtotal, discount.amount(), tax,
            taxableAmount.add(tax));
    }
}
```

Thứ tự áp dụng policy là một quy tắc nghiệp vụ quan trọng. Ví dụ tính thuế trước hay sau chiết khấu phụ thuộc quy định và loại giao dịch. Hãy ghi rõ thứ tự, làm rõ currency/rounding và kiểm thử các trường hợp biên.

### 9.2. Kết hợp bằng điều kiện và ưu tiên

Một quyết định có thể cần nhiều specification:

```java
boolean eligible = activeCustomer
    .and(notBlocked)
    .and(productAvailable)
    .isSatisfiedBy(context);
```

Nếu nhiều rule có thể cho kết quả xung đột, cần một chính sách ưu tiên rõ ràng: rule nào thắng, có cho phép ngoại lệ không, và ai được quyền override. Không nên để thứ tự duyệt collection hoặc thứ tự đăng ký bean ngẫu nhiên quyết định nghiệp vụ.

## 10. Policy có thể thay đổi theo thời gian

Nhiều chính sách có ngày hiệu lực, ngày hết hiệu lực hoặc phiên bản. Ví dụ chương trình khuyến mãi thay đổi theo mùa; lãi suất hoặc điều kiện tín dụng thay đổi theo quyết định đã phê duyệt; phí giao hàng thay đổi theo vùng.

Đừng chỉ lưu kết quả cuối nếu doanh nghiệp cần giải thích tại sao quyết định được đưa ra. Có thể lưu:

- `policyCode` và `policyVersion`.
- `decidedAt` hoặc thời điểm nghiệp vụ được dùng để chọn chính sách.
- Các input quan trọng hoặc snapshot cần thiết để audit.
- `decisionType`, `reasonCodes` và giá trị được áp dụng.
- Người hoặc hệ thống đã phê duyệt phiên bản chính sách.

### 10.1. Chọn policy theo effective date

Nếu một chính sách có hiệu lực từ một thời điểm cụ thể, application có thể chọn policy version phù hợp với `decisionTime`. Việc chọn phiên bản là một quy tắc có thể được mô hình hóa bằng `PolicyRegistry` hoặc policy selector.

```java
public interface DiscountPolicyProvider {
    DiscountPolicy policyEffectiveAt(Instant decisionTime);
}
```

Không nên dùng `LocalDate.now()` trực tiếp bên trong policy nếu thời điểm quyết định cần được tái hiện. Truyền `decisionTime` vào rõ ràng để kiểm thử và audit.

### 10.2. Không tự động áp dụng policy mới cho quyết định cũ

Một đơn hàng đã được báo giá theo phiên bản `DISCOUNT_V2` có thể cần giữ nguyên mức giá đã cam kết. Nếu khi đọc lại đơn, hệ thống tính lại bằng `DISCOUNT_V3`, kết quả có thể thay đổi và phá vỡ cam kết với khách hàng.

Hãy phân biệt:

- **Tính quyết định mới:** dùng policy đang có hiệu lực theo thời điểm và ngữ cảnh mới.
- **Tái hiện quyết định cũ:** dùng snapshot/version và dữ liệu đã ghi nhận lúc quyết định được đưa ra.
- **Điều chỉnh quyết định:** là một hành vi nghiệp vụ mới, có quyền, lý do và audit tương ứng.

### 10.3. Policy cấu hình từ dữ liệu

Ngưỡng hoặc bảng tỷ lệ có thể được lưu trong database/configuration store để người có thẩm quyền thay đổi mà không phát hành code. Tuy nhiên, cấu hình đó vẫn là chính sách nghiệp vụ và cần:

- Schema và validation rõ ràng.
- Quy trình phê duyệt và quyền chỉnh sửa.
- Version và effective date.
- Kiểm tra tính nhất quán trước khi kích hoạt.
- Audit log cho thay đổi.
- Cơ chế cache/invalidation có kiểm soát.
- Khả năng rollback về phiên bản trước.

Không nên biến mọi điều kiện thành cấu hình động. Các quy tắc phức tạp cần code, test và review vẫn có thể an toàn hơn khi được triển khai dưới dạng implementation có phiên bản.

## 11. Policy, Strategy Pattern và Domain Service

Policy có thể được triển khai bằng Strategy Pattern, nhưng hai khái niệm không đồng nghĩa.

- **Policy** là khái niệm nghiệp vụ: quy tắc ra quyết định nào đang được áp dụng?
- **Strategy Pattern** là kỹ thuật tổ chức code: thay một thuật toán/implementation bằng một implementation khác qua abstraction.
- **Domain Service** là nơi đặt hành vi nghiệp vụ không thuộc tự nhiên về một entity hoặc value object cụ thể.

Một `DiscountPolicy` có thể được cài đặt bằng Strategy Pattern và cũng có thể là domain service. Nhưng không phải strategy kỹ thuật nào cũng là business policy; ví dụ chiến lược chọn connection pool không phải chính sách nghiệp vụ.

Không cần tạo interface nếu chỉ có một quy tắc nhỏ, ổn định và không có lý do thay thế. Khi cần nhiều implementation, lựa chọn theo tenant, quốc gia, sản phẩm hoặc effective date, abstraction trở nên hữu ích hơn.

## 12. Policy và quyền quyết định

Chính sách nghiệp vụ thường gắn với thẩm quyền. Không phải mọi người dùng hoặc service đều được quyền chọn hay thay đổi policy.

Hãy làm rõ:

- Ai sở hữu và phê duyệt policy?
- Ai được phép yêu cầu đánh giá policy?
- Ai có quyền override kết quả và trong điều kiện nào?
- Override có cần lý do, người phê duyệt thứ hai hoặc audit không?
- Policy version nào được áp dụng cho mỗi loại giao dịch?
- Khi dữ liệu đầu vào thiếu hoặc không đáng tin cậy, hệ thống từ chối hay chuyển kiểm tra thủ công?

Đừng nhầm quyền override với việc bỏ qua invariant. Người có quyền có thể phê duyệt một ngoại lệ được nghiệp vụ cho phép, nhưng trạng thái aggregate vẫn phải hợp lệ theo mô hình. Nếu ngoại lệ là một trường hợp chính thức, hãy mô hình hóa nó thành hành vi và trạng thái có tên.

## 13. Kiểm thử policy

Policy thường là nơi tập trung nhiều nhánh quyết định, vì vậy cần test theo bảng tình huống và các ranh giới giá trị.

### 13.1. Unit test theo ví dụ nghiệp vụ

Với `MemberDiscountPolicy`, test có thể bao gồm:

| Hạng khách hàng | Sản phẩm | Kết quả kỳ vọng |
|---|---|---:|
| Standard | Đủ điều kiện | 0% |
| Silver | Đủ điều kiện | 5% |
| Gold | Đủ điều kiện | 10% |
| Gold | Khuyến mãi độc quyền | 0% trên dòng đó |
| Gold | Có cả dòng đủ điều kiện và dòng độc quyền | Chỉ giảm trên dòng đủ điều kiện |

Ví dụ:

```java
class MemberDiscountPolicyTest {
    private final DiscountPolicy policy = new MemberDiscountPolicy();

    @Test
    void goldCustomerGetsTenPercentOnEligibleLines() {
        DiscountContext context = context(
            CustomerTier.GOLD,
            List.of(eligibleLine("100.00"), exclusiveLine("50.00")),
            Money.of("150.00", "USD")
        );

        DiscountDecision decision = policy.decide(context);

        assertEquals(Money.of("10.00", "USD"), decision.amount());
        assertEquals("MEMBER_DISCOUNT_V1", decision.policyCode());
    }
}
```

### 13.2. Test ranh giới và tính tiền

Với policy tài chính hoặc chiết khấu, cần xác định và test:

- Ngưỡng đúng bằng mức tối thiểu/tối đa.
- Giá trị ngay dưới và ngay trên ngưỡng.
- Làm tròn ở từng dòng hay sau khi cộng tổng.
- Currency khác nhau hoặc thiếu tỷ giá.
- Ngày bắt đầu và kết thúc hiệu lực.
- Sản phẩm hoặc khách hàng thuộc nhiều nhóm điều kiện.
- Dữ liệu thiếu, cũ hoặc không đáng tin cậy.
- Hai rule cùng áp dụng hoặc có kết quả xung đột.

### 13.3. Test policy version và khả năng giải thích

Với policy có phiên bản, kiểm tra rằng cùng input và cùng version cho kết quả xác định; thời điểm nằm trước/sau effective date chọn đúng version; decision lưu đúng `policyCode`, `policyVersion` và `reasonCodes`.

Nếu policy phụ thuộc dữ liệu ngoài, test riêng adapter lấy dữ liệu và test policy bằng snapshot đã chuẩn bị. Không cần khởi động database hoặc HTTP server chỉ để kiểm tra logic quyết định thuần.

## 14. Sai lầm thường gặp

**Đặt tên policy quá chung.** `BusinessRules` hoặc `PolicyManager` không giúp người đọc hiểu quyết định nào đang được mô hình hóa. Dùng tên thể hiện nghiệp vụ cụ thể.

**Đưa mọi điều kiện vào một policy lớn.** Khi các quy tắc có chủ sở hữu và chu kỳ thay đổi khác nhau, một policy khổng lồ sẽ khó kiểm thử và khó giải thích. Tách theo ý nghĩa nghiệp vụ, không tách theo từng dòng `if`.

**Nhầm policy với invariant.** Policy có thể thay đổi theo thời gian; invariant bảo vệ trạng thái hợp lệ. Không cho phép thay policy làm aggregate vi phạm invariant.

**Nhầm policy với specification.** Specification thường trả lời một predicate; policy có thể tạo quyết định nhiều trạng thái hoặc tính giá trị. Chọn abstraction theo kết quả cần diễn đạt.

**Đặt logic nghiệp vụ trong controller.** Nhiều adapter có thể gọi cùng use case. Quy tắc ra quyết định nên nằm trong domain/application boundary phù hợp, không gắn với HTTP.

**Để policy gọi database hoặc HTTP client trực tiếp.** Điều này làm quyết định khó kiểm thử, tăng coupling và có thể giữ transaction quá lâu. Chuẩn bị input qua application hoặc port rõ ràng.

**Dùng thời gian hệ thống ẩn.** Gọi `now()` bên trong policy làm kết quả khó tái hiện. Truyền thời điểm quyết định vào context.

**Không lưu phiên bản policy.** Khi chính sách thay đổi, hệ thống không thể giải thích vì sao giao dịch cũ có kết quả đó. Lưu version và các thông tin cần thiết theo yêu cầu audit.

**Để thứ tự thực thi quyết định ưu tiên.** Khi nhiều rule cùng khớp, phải có quy tắc ưu tiên rõ thay vì phụ thuộc thứ tự collection hoặc cấu hình bean.

**Tạo abstraction không có lý do.** Nếu chỉ có một phép tính nhỏ, ổn định và không có ý nghĩa riêng, một phương thức trong domain object có thể dễ hiểu hơn một interface và nhiều class.

## 15. Quy trình thiết kế business policy

1. **Tìm quyết định cần mô hình hóa.** Bắt đầu từ câu hỏi nghiệp vụ lặp lại hoặc có nhiều nhánh và ngoại lệ.
2. **Trao đổi với domain expert.** Xác định thuật ngữ, mục tiêu, thẩm quyền, trường hợp thường gặp và ngoại lệ.
3. **Phân biệt với invariant và validation.** Ghi rõ điều gì là quyết định có thể thay đổi và điều gì luôn phải đúng.
4. **Đặt tên policy.** Dùng ngôn ngữ domain, phản ánh quyết định cụ thể.
5. **Xác định input và output.** Dùng context rõ ràng và decision object có lý do khi cần.
6. **Chọn vị trí.** Domain policy, aggregate behavior, application policy hoặc infrastructure policy theo bản chất quy tắc.
7. **Xác định nguồn dữ liệu.** Làm rõ dữ liệu nào do caller cung cấp, dữ liệu nào cần tải qua port và thời điểm dữ liệu có hiệu lực.
8. **Xác định version và quyền thay đổi.** Ghi người phê duyệt, effective date, audit và rollback nếu chính sách thay đổi.
9. **Viết test theo bảng tình huống.** Bao gồm ranh giới, ngoại lệ, xung đột rule và lý do quyết định.
10. **Tích hợp vào use case.** Application điều phối policy và aggregate thực thi chuyển đổi trạng thái hợp lệ.

## 16. Checklist đánh giá

Trước khi hoàn tất một policy, hãy kiểm tra:

- Policy có tên thể hiện quyết định nghiệp vụ rõ ràng không?
- Domain expert có xác nhận mục tiêu, phạm vi và thuật ngữ không?
- Đã phân biệt policy với invariant, specification, validation và authorization chưa?
- Input có đủ và có nguồn dữ liệu đáng tin cậy không?
- Output có diễn đạt rõ quyết định và lý do cần thiết không?
- Aggregate có tiếp tục bảo vệ invariant khi áp dụng quyết định không?
- Policy có phụ thuộc trực tiếp framework, database hoặc HTTP không?
- Thời gian và phiên bản policy có được xác định rõ không?
- Các rule xung đột có thứ tự ưu tiên hoặc cách giải quyết rõ không?
- Ai có quyền thay đổi hoặc override policy đã được xác định chưa?
- Có audit đủ để giải thích quyết định lịch sử không?
- Unit test bao phủ các ngưỡng, ngoại lệ và effective date chưa?
- Có thật sự cần interface hoặc factory cho policy không?

## 17. Câu hỏi tự kiểm tra

1. Business Policy là gì và vì sao nên đặt tên cho một quy tắc ra quyết định?
2. Phân biệt policy với invariant trong một aggregate.
3. Khi nào nên dùng Specification thay vì Policy?
4. Vì sao validation đầu vào không thay thế được kiểm tra điều kiện nghiệp vụ?
5. Một policy nên nhận dữ liệu đầu vào và trả kết quả theo hình thức nào để dễ giải thích?
6. Khi nào quy tắc nên nằm trong aggregate thay vì một domain policy riêng?
7. Vì sao không nên để policy domain tự gọi database hoặc HTTP service?
8. Tại sao thời điểm quyết định và policy version quan trọng khi chính sách thay đổi?
9. Phân biệt Business Policy với Strategy Pattern và application/infrastructure policy.
10. Làm thế nào kiểm thử các ngưỡng, ngoại lệ và thứ tự ưu tiên của nhiều rule?

## Kết luận

Business Policy giúp mô hình hóa những quy tắc ra quyết định có ý nghĩa nghiệp vụ thành các khái niệm có tên, phạm vi, đầu vào và kết quả rõ ràng. Policy có thể tính toán, lựa chọn hoặc đưa ra quyết định nhiều trạng thái; specification thường kiểm tra một điều kiện; aggregate tiếp tục bảo vệ invariant khi áp dụng kết quả. Đặt policy đúng lớp, cung cấp dữ liệu minh bạch, quản lý phiên bản và kiểm thử theo tình huống giúp đội phát triển thay đổi quy tắc có kiểm soát, đồng thời giữ cho chuyên gia nghiệp vụ và kỹ sư cùng hiểu quyết định mà hệ thống đang thực hiện.
