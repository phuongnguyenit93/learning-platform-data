# Chọn đối tượng chính sách hoặc chiến lược thay cho nhánh điều kiện rải rác

Trong một miền nghiệp vụ, cùng một hành động có thể được thực hiện theo nhiều quy tắc khác nhau. Phí giao hàng thay đổi theo phương thức vận chuyển và khu vực; mức chiết khấu thay đổi theo phân khúc khách hàng; điều kiện phê duyệt tín dụng thay đổi theo loại hồ sơ; cách tính phí có thể phụ thuộc vào hợp đồng hoặc thời điểm áp dụng.

Khi các khác biệt này được triển khai bằng nhiều nhánh `if/else` hoặc `switch` ở nhiều nơi, quy tắc nghiệp vụ dễ bị lặp lại và khó kiểm soát. Một thay đổi chính sách có thể đòi hỏi sửa nhiều lớp, trong khi mỗi nơi có nguy cơ áp dụng một phiên bản quy tắc khác nhau. Domain-Driven Design (DDD) khuyến khích diễn đạt quy tắc bằng ngôn ngữ nghiệp vụ và đặt trách nhiệm vào đúng mô hình. Trong trường hợp có nhiều cách thực hiện cùng một hoạt động, nhóm có thể mô hình hóa chúng bằng **policy object (đối tượng chính sách)** hoặc **strategy (chiến lược)**.

Ý tưởng là đóng gói một quy tắc hoặc cách thực hiện có thể thay đổi sau một hợp đồng rõ ràng. Thành phần sử dụng chỉ biết nó cần một hành vi như tính phí, đánh giá điều kiện hoặc xác định mức chiết khấu; nó không cần chứa toàn bộ nhánh điều kiện để chọn từng cách làm. Bài học này giải thích khi nào nên tạo policy/strategy, cách đặt tên và chọn đối tượng phù hợp, cách kết hợp nhiều chính sách, và cách kiểm thử chúng mà vẫn giữ thiết kế đơn giản.

## 1. Vấn đề của nhánh điều kiện rải rác

Hãy xem một ứng dụng giao hàng có ba phương thức: giao tiêu chuẩn, giao nhanh và giao trong ngày. Ban đầu, nhóm viết điều kiện trong một service:

```java
public Money calculateShippingFee(Shipment shipment) {
    if (shipment.method() == ShippingMethod.STANDARD) {
        return standardRate(shipment);
    } else if (shipment.method() == ShippingMethod.EXPRESS) {
        return expressRate(shipment);
    } else if (shipment.method() == ShippingMethod.SAME_DAY) {
        return sameDayRate(shipment);
    }

    throw new IllegalArgumentException("Unsupported method");
}
```

Một nhánh nhỏ như vậy có thể hoàn toàn hợp lý. Vấn đề xuất hiện khi cùng điều kiện được sao chép sang nhiều nơi:

- Màn hình báo giá có một `switch` để hiển thị phí.
- Application service có một `if` để tính phí khi tạo đơn.
- Tác vụ nền có một `switch` khác khi tạo vận đơn.
- Báo cáo có một công thức riêng để tính lại phí.
- Một chương trình khuyến mại bổ sung điều kiện đặc biệt cho giao nhanh.

Khi chính sách giao nhanh thay đổi, nhóm phải tìm và sửa tất cả các nhánh. Nếu một nơi bị bỏ sót, cùng một đơn hàng có thể được báo giá một mức nhưng lúc xác nhận lại tính mức khác.

Những dấu hiệu thường cho thấy conditional logic đã trở thành vấn đề:

- Cùng một điều kiện phân loại xuất hiện ở nhiều lớp hoặc nhiều bounded context.
- Thêm một biến thể mới buộc phải sửa nhiều `if/else` hoặc `switch` không liên quan.
- Một phương thức chứa nhiều nhánh và mỗi nhánh thực hiện một thuật toán khác nhau.
- Các quy tắc nghiệp vụ được diễn đạt bằng mã loại, cờ boolean hoặc tên kỹ thuật khó hiểu.
- Kiểm thử một biến thể cần khởi tạo nhiều dữ liệu và phụ thuộc không liên quan.
- Các nhánh thay đổi với tần suất hoặc người chịu trách nhiệm khác nhau.

Không phải mọi nhánh điều kiện đều xấu. Một điều kiện ngắn, ổn định và chỉ xuất hiện ở một nơi có thể là cách biểu diễn rõ ràng nhất. Cần phân biệt nhánh đơn giản với một tập hợp chính sách có nhiều biến thể và lý do thay đổi độc lập.

## 2. Policy và Strategy là gì?

Hai khái niệm này thường được dùng gần nhau, nhưng có trọng tâm khác nhau.

**Policy (chính sách)** diễn đạt quy tắc hoặc quyết định nghiệp vụ: điều gì được phép, điều kiện nào áp dụng, cách xác định một kết quả theo chính sách của tổ chức. Ví dụ: chính sách miễn phí vận chuyển cho khách hàng thành viên khi đơn đạt ngưỡng nhất định.

**Strategy (chiến lược)** là một cách triển khai có thể thay thế cho một hành vi hoặc thuật toán. Các strategy cùng tuân theo một hợp đồng nhưng có cách thực hiện khác nhau. Ví dụ: chiến lược tính phí giao hàng theo trọng lượng, theo vùng hoặc theo mức giá cố định.

Trong thiết kế hướng đối tượng, Strategy Pattern là mẫu thiết kế cho phép đóng gói các thuật toán có thể thay thế và lựa chọn thuật toán phù hợp khi chạy. Trong DDD, một policy object có thể được triển khai bằng cấu trúc strategy nếu chính sách có nhiều biến thể. Hai thuật ngữ có thể giao nhau, nhưng không phải mọi strategy đều là chính sách nghiệp vụ và không phải mọi policy đều cần nhiều strategy.

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Policy | Quy tắc hoặc quyết định nào đang chi phối nghiệp vụ? | Khách hàng thành viên được miễn phí giao hàng khi đơn đạt điều kiện |
| Strategy | Có những cách thực hiện nào có thể thay thế nhau? | Tính phí theo trọng lượng, khoảng cách hoặc mức cố định |
| Strategy Pattern | Làm sao tách các thuật toán thay thế khỏi nơi sử dụng? | `ShippingFeeStrategy` với nhiều implementation |
| Specification | Một đối tượng có thỏa một điều kiện nghiệp vụ không? | Đơn hàng có đủ điều kiện miễn phí vận chuyển không? |

Trong một số hệ thống, policy có thể được diễn đạt bằng một strategy; specification có thể là thành phần mà policy sử dụng để kiểm tra điều kiện. Nhóm nên chọn cách biểu diễn theo ngữ nghĩa miền, không cần ép mọi khái niệm vào một tên mẫu thiết kế.

## 3. Khi nào nên thay nhánh điều kiện bằng policy hoặc strategy?

Policy/strategy phù hợp khi có một hoạt động ổn định về mục đích nhưng có nhiều cách thực hiện hoặc nhiều bộ quy tắc có thể thay đổi độc lập.

Ví dụ:

- Tính phí vận chuyển theo phương thức hoặc khu vực.
- Tính chiết khấu theo phân khúc khách hàng.
- Tính thuế theo loại giao dịch và khu vực pháp lý.
- Đánh giá hồ sơ tín dụng theo loại khách hàng hoặc sản phẩm tín dụng.
- Phân bổ khoản thanh toán theo các quy tắc khác nhau.
- Xác định thời hạn bảo hành theo loại sản phẩm và hợp đồng.
- Chọn phương thức xử lý đơn theo loại kênh bán hàng.

Trước khi tạo đối tượng riêng, hãy kiểm tra các điều kiện:

1. Có một hành vi nghiệp vụ chung mà các biến thể cùng thực hiện không?
2. Những biến thể có thuật toán hoặc quy tắc khác nhau đủ rõ để tách không?
3. Các biến thể có thể thay thế nhau qua cùng một hợp đồng không?
4. Việc thêm hoặc thay đổi một biến thể có nên ảnh hưởng đến nơi sử dụng không?
5. Tên của policy/strategy có thể diễn đạt tự nhiên bằng ngôn ngữ nghiệp vụ không?

Nếu câu trả lời chủ yếu là có, một abstraction có thể hữu ích. Nếu chỉ có hai nhánh nhỏ, ít thay đổi và rất dễ đọc, một `if/else` đơn giản có thể tốt hơn.

## 4. Nhận diện điểm biến thiên trong quy tắc

Trước khi thiết kế interface, cần xác định chính xác điều gì thay đổi. Đừng bắt đầu bằng việc tạo một interface chung rồi cố tìm những lớp để triển khai nó.

Ví dụ với tính phí vận chuyển, các yếu tố có thể gồm:

- Phương thức vận chuyển: tiêu chuẩn, nhanh, trong ngày.
- Khu vực: nội thành, ngoại thành, vùng xa.
- Khối lượng hoặc kích thước kiện hàng.
- Khoảng cách hoặc vùng phục vụ.
- Loại hợp đồng của khách hàng.
- Thời điểm đặt và khung giờ giao.

Những yếu tố này không nhất thiết tương ứng với một strategy riêng. Có thể phương thức vận chuyển quyết định thuật toán, còn khu vực và khối lượng là dữ liệu đầu vào của thuật toán. Nếu tạo một lớp cho mọi tổ hợp, số lượng implementation sẽ tăng rất nhanh.

Hãy phân biệt:

- **Biến thể thuật toán:** cách tính thực sự khác nhau và có thể thay thế nhau.
- **Tham số của cùng thuật toán:** dữ liệu đầu vào thay đổi nhưng cách tính vẫn giống nhau.
- **Điều kiện áp dụng:** quy tắc xác định policy nào được dùng.
- **Điều kiện hợp lệ:** ràng buộc phải đúng trước khi hành vi được thực hiện.

Ví dụ, `ExpressShippingStrategy` và `StandardShippingStrategy` có thể là hai cách tính khác nhau. `destinationZone` và `weight` có thể chỉ là dữ liệu mà cả hai strategy cùng nhận. Còn quy tắc “không hỗ trợ giao trong ngày tại vùng xa” có thể được mô hình hóa bằng một specification hoặc policy kiểm tra khả năng phục vụ.

## 5. Định nghĩa hợp đồng policy hoặc strategy

Hợp đồng nên mô tả hành vi cần thiết ở mức nghiệp vụ, không để lộ cách triển khai. Một hợp đồng tốt có đầu vào rõ, kết quả có ý nghĩa và điều kiện lỗi được xác định.

Ví dụ:

```java
public interface ShippingFeePolicy {
    Money calculateFee(ShippingQuoteInput input);
}

public record ShippingQuoteInput(
        ShippingMethod method,
        DeliveryZone zone,
        Weight weight,
        Money declaredValue
) {}
```

Tên `ShippingFeePolicy` cho biết đây là quy tắc phí vận chuyển. Phương thức `calculateFee` nói rõ hành động. `ShippingQuoteInput` gom dữ liệu liên quan thành một kiểu có ý nghĩa thay vì truyền nhiều tham số rời rạc.

Nếu các cách tính có bản chất thuật toán và không chứa quyết định chính sách, tên `ShippingFeeStrategy` cũng có thể phù hợp. Quan trọng là nhóm thống nhất ngữ nghĩa và sử dụng tên nhất quán trong bounded context.

### 5.1. Trả về kiểu miền

Không nên trả về `double` hoặc một con số không có đơn vị nếu kết quả là tiền. `Money` thể hiện số tiền và tiền tệ. Với kết quả phức tạp, có thể dùng `ShippingFeeQuote` chứa phí, thời gian dự kiến và điều kiện áp dụng.

```java
public record ShippingFeeQuote(
        Money fee,
        DeliveryWindow deliveryWindow,
        String appliedPolicyCode
) {}
```

Chỉ thêm `appliedPolicyCode` nếu mã chính sách có ý nghĩa cho đối soát hoặc giải thích quyết định. Không đưa mã cấu hình nội bộ vào domain result chỉ vì tiện debug.

### 5.2. Giữ hợp đồng ổn định

Nếu mỗi implementation yêu cầu một tập dữ liệu hoàn toàn khác nhau, interface có thể đang quá chung hoặc đầu vào chưa được mô hình hóa đúng. Hãy xác định phần dữ liệu chung thực sự cần cho quyết định và phần nào chỉ thuộc một biến thể. Có thể dùng value object chuyên biệt hoặc tách các use case nếu hành vi thực ra không cùng một khái niệm.

## 6. Ví dụ Java: nhiều chiến lược tính phí vận chuyển

Giả sử cửa hàng có hai cách tính phí:

- Giao tiêu chuẩn tính phí theo vùng và khối lượng.
- Giao nhanh tính thêm phụ phí theo thời gian phục vụ.

Ta có thể tách hai thuật toán khỏi application service.

```java
public interface ShippingFeeStrategy {
    ShippingMethod method();

    Money calculate(ShippingQuoteInput input);
}

public final class StandardShippingFeeStrategy
        implements ShippingFeeStrategy {

    @Override
    public ShippingMethod method() {
        return ShippingMethod.STANDARD;
    }

    @Override
    public Money calculate(ShippingQuoteInput input) {
        Money zoneFee = input.zone().standardFee();
        Money weightFee = input.weight().multiplyRate(
                input.zone().feePerKilogram()
        );
        return zoneFee.add(weightFee);
    }
}

public final class ExpressShippingFeeStrategy
        implements ShippingFeeStrategy {

    @Override
    public ShippingMethod method() {
        return ShippingMethod.EXPRESS;
    }

    @Override
    public Money calculate(ShippingQuoteInput input) {
        Money baseFee = input.zone().expressBaseFee();
        Money weightFee = input.weight().multiplyRate(
                input.zone().expressFeePerKilogram()
        );
        return baseFee.add(weightFee).add(input.zone().expressSurcharge());
    }
}
```

Các kiểu `Money`, `Weight`, `DeliveryZone` và `ShippingMethod` cần được định nghĩa theo mô hình thực tế. Đoạn mã minh họa cấu trúc thay thế thuật toán; công thức và quy tắc giá phải được xác nhận với chuyên gia nghiệp vụ.

### 6.1. Chọn strategy tại một điểm

Không nên lặp `switch` ở mọi nơi để chọn strategy. Có thể tạo một resolver hoặc registry tập trung:

```java
public final class ShippingFeeStrategyRegistry {
    private final Map<ShippingMethod, ShippingFeeStrategy> strategies;

    public ShippingFeeStrategyRegistry(
            List<ShippingFeeStrategy> availableStrategies
    ) {
        this.strategies = availableStrategies.stream()
                .collect(Collectors.toUnmodifiableMap(
                        ShippingFeeStrategy::method,
                        Function.identity()
                ));
    }

    public ShippingFeeStrategy get(ShippingMethod method) {
        ShippingFeeStrategy strategy = strategies.get(method);
        if (strategy == null) {
            throw new UnsupportedShippingMethodException(method);
        }
        return strategy;
    }
}
```

Registry chịu trách nhiệm ánh xạ loại phương thức sang implementation. Nếu hai strategy đăng ký cùng một `ShippingMethod`, việc tạo map sẽ thất bại thay vì âm thầm chọn một implementation. Trong ứng dụng thực tế, có thể kiểm tra đầy đủ tập strategy được hỗ trợ ngay khi khởi động.

### 6.2. Nơi sử dụng không cần biết từng thuật toán

```java
public final class ShippingQuoteService {
    private final ShippingFeeStrategyRegistry strategies;

    public ShippingQuoteService(ShippingFeeStrategyRegistry strategies) {
        this.strategies = strategies;
    }

    public Money quote(ShippingQuoteInput input) {
        ShippingFeeStrategy strategy = strategies.get(input.method());
        return strategy.calculate(input);
    }
}
```

Khi thêm một phương thức vận chuyển mới, nhóm bổ sung implementation và đăng ký nó. `ShippingQuoteService` không cần thêm một nhánh cho từng thuật toán. Nếu chính sách lựa chọn phức tạp hơn một enum đơn giản, việc chọn strategy có thể được đưa vào một policy riêng.

## 7. Ví dụ Java: policy quyết định điều kiện miễn phí vận chuyển

Không phải policy nào cũng là thuật toán tính toán. Một policy có thể đưa ra quyết định có/không dựa trên nhiều dữ kiện nghiệp vụ.

Ví dụ, miễn phí vận chuyển khi khách hàng là thành viên, tổng tiền hàng đạt ngưỡng và địa chỉ thuộc vùng được hỗ trợ.

```java
public interface FreeShippingPolicy {
    boolean isEligible(FreeShippingContext context);
}

public record FreeShippingContext(
        BuyerSegment buyerSegment,
        Money merchandiseTotal,
        DeliveryZone deliveryZone
) {}

public final class MemberFreeShippingPolicy
        implements FreeShippingPolicy {

    private final Money minimumOrderTotal;

    public MemberFreeShippingPolicy(Money minimumOrderTotal) {
        this.minimumOrderTotal = minimumOrderTotal;
    }

    @Override
    public boolean isEligible(FreeShippingContext context) {
        return context.buyerSegment() == BuyerSegment.MEMBER
                && context.merchandiseTotal().isAtLeast(minimumOrderTotal)
                && context.deliveryZone().supportsFreeShipping();
    }
}
```

Tên `MemberFreeShippingPolicy` cho biết chính sách áp dụng cho thành viên. Kết quả boolean phù hợp nếu caller chỉ cần biết có đủ điều kiện hay không. Nếu cần giải thích vì sao đủ hoặc không đủ điều kiện, nên trả về một kiểu kết quả miền như `FreeShippingAssessment` chứa quyết định và lý do.

### 7.1. Phân biệt policy quyết định với strategy tính toán

Trong ví dụ này:

- `FreeShippingPolicy` quyết định có được miễn phí hay không.
- `ShippingFeeStrategy` tính phí khi không được miễn phí.

Hai thành phần có thể được phối hợp trong một domain service định giá vận chuyển. Việc phân tách giúp tên và trách nhiệm rõ ràng.

## 8. Chọn policy: resolver, factory hay registry?

Khi có nhiều implementation, ứng dụng cần một cách chọn đúng đối tượng. Có thể dùng factory, resolver hoặc registry tùy mức độ phức tạp.

| Cơ chế | Phù hợp khi | Ví dụ |
| --- | --- | --- |
| Factory | Việc tạo implementation cần logic hoặc tham số khởi tạo | Tạo policy theo loại hợp đồng và cấu hình |
| Resolver | Cần quyết định policy nào áp dụng dựa trên dữ liệu nghiệp vụ | Chọn chính sách giá theo vùng và phân khúc |
| Registry | Các implementation đã được tạo sẵn và cần tra cứu theo key | Lấy strategy theo `ShippingMethod` |
| Dependency Injection | Implementation được cấu hình khi khởi động ứng dụng | Spring inject danh sách `ShippingFeeStrategy` |

Nếu việc chọn policy phụ thuộc vào quy tắc nghiệp vụ phức tạp, không nên giấu nó trong một `Map` hoặc factory thuần kỹ thuật. Có thể mô hình hóa nó thành `ShippingPolicySelection` hoặc một policy có tên cụ thể, rồi kiểm thử các điều kiện chọn.

Ví dụ:

```java
public final class ShippingPolicyResolver {
    private final List<ShippingFeePolicy> policies;

    public ShippingPolicyResolver(List<ShippingFeePolicy> policies) {
        this.policies = List.copyOf(policies);
    }

    public ShippingFeePolicy resolve(ShippingContext context) {
        return policies.stream()
                .filter(policy -> policy.supports(context))
                .findFirst()
                .orElseThrow(() -> new NoApplicableShippingPolicyException());
    }
}
```

Đoạn mã trên giả định thứ tự policy đã được xác định và `supports` không gây side effect. Nếu nhiều policy cùng thỏa điều kiện, `findFirst()` có thể tạo ra kết quả phụ thuộc thứ tự đăng ký. Trong nghiệp vụ có ưu tiên, nhóm cần mô hình hóa priority rõ ràng hoặc từ chối cấu hình mơ hồ thay vì dựa vào thứ tự ngầm.

## 9. Kết hợp nhiều policy

Một nghiệp vụ có thể áp dụng nhiều quy tắc đồng thời. Ví dụ, giá đơn hàng có thể gồm giá cơ bản, chiết khấu thành viên, mã khuyến mại và giới hạn giảm giá tối đa. Không nên giả định rằng tất cả các policy đều có thể cộng dồn theo cùng một cách.

Có một số cách kết hợp thường gặp:

### 9.1. Chuỗi xử lý (pipeline)

Các policy được áp dụng theo một thứ tự có ý nghĩa. Ví dụ:

1. Tính giá cơ bản.
2. Áp dụng chiết khấu theo phân khúc.
3. Áp dụng khuyến mại theo mã.
4. Áp dụng giới hạn giảm giá tối đa.
5. Tính thuế và tổng tiền theo chính sách.

Thứ tự có thể ảnh hưởng kết quả. Nếu thuế được tính trước hoặc sau chiết khấu, số tiền có thể khác. Quy tắc này cần được xác nhận và mô hình hóa rõ.

### 9.2. Chính sách ưu tiên (priority)

Nếu nhiều policy có thể áp dụng nhưng chỉ một policy được chọn, cần xác định thứ tự ưu tiên. Ví dụ, chính sách hợp đồng riêng có thể ưu tiên hơn chính sách công khai. Không nên dựa vào thứ tự của danh sách class do framework inject nếu thứ tự đó chưa được định nghĩa như một quy tắc.

### 9.3. Chính sách kết hợp (composite)

Một policy tổng hợp có thể gọi nhiều policy con theo quy tắc đã xác định. Ví dụ, `OrderDiscountPolicy` kết hợp chiết khấu thành viên và khuyến mại theo mùa, nhưng phải kiểm tra giới hạn tổng mức giảm.

### 9.4. Chính sách loại trừ lẫn nhau

Một số chương trình khuyến mại không được cộng dồn. Khi đó, policy cần xác định quy tắc chọn ưu đãi tốt nhất, ưu tiên hợp đồng hoặc từ chối áp dụng đồng thời. Đây là quyết định nghiệp vụ, không chỉ là chi tiết vòng lặp.

Trước khi xây dựng composite, hãy ghi rõ các quy tắc: áp dụng tất cả hay chỉ một, thứ tự nào, có giới hạn nào, cách xử lý khi một policy không hợp lệ và ai có quyền quyết định.

## 10. Policy và Specification phối hợp như thế nào?

**Specification (đặc tả)** thường biểu diễn một điều kiện có thể kiểm tra trên một đối tượng hoặc ngữ cảnh. Nó trả lời câu hỏi “đối tượng này có thỏa điều kiện không?”.

Ví dụ:

- Đơn hàng có đạt ngưỡng miễn phí vận chuyển không?
- Khách hàng có thuộc phân khúc được hưởng chiết khấu không?
- Hợp đồng có đang trong thời hạn hiệu lực không?

Policy thường diễn đạt quy tắc quyết định hoặc cách xử lý khi các điều kiện được thỏa. Specification có thể là thành phần bên trong policy.

```java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}

public final class MinimumOrderTotalSpecification
        implements Specification<OrderPricingContext> {

    private final Money minimum;

    public MinimumOrderTotalSpecification(Money minimum) {
        this.minimum = minimum;
    }

    @Override
    public boolean isSatisfiedBy(OrderPricingContext context) {
        return context.total().isAtLeast(minimum);
    }
}
```

Một policy có thể dùng nhiều specification:

```java
public final class MemberFreeShippingPolicy {
    private final Specification<OrderPricingContext> minimumTotal;
    private final Specification<OrderPricingContext> memberOnly;
    private final Specification<OrderPricingContext> supportedZone;

    public boolean isEligible(OrderPricingContext context) {
        return minimumTotal.isSatisfiedBy(context)
                && memberOnly.isSatisfiedBy(context)
                && supportedZone.isSatisfiedBy(context);
    }
}
```

Đây là cách minh họa sự phối hợp, không phải yêu cầu mỗi điều kiện đều phải có một class riêng. Nếu điều kiện đơn giản và chỉ dùng một lần, biểu thức trực tiếp trong policy có thể dễ đọc hơn.

## 11. Đặt policy ở đúng bounded context và đúng tầng

Một policy nghiệp vụ cần thuộc về bounded context sở hữu quy tắc. Chính sách giá bán không nên bị đặt trong context kho chỉ vì kho cũng cần biết giá để tính giá trị tồn kho. Context khác có thể nhận một kết quả hoặc hợp đồng phù hợp thay vì dùng chung toàn bộ policy nội bộ.

Trong kiến trúc ứng dụng, cần phân biệt:

- **Domain policy:** quy tắc nghiệp vụ, ví dụ `CreditApprovalPolicy`.
- **Application selection/orchestration:** chọn và gọi policy trong một use case, ví dụ application service tải hồ sơ rồi yêu cầu đánh giá.
- **Infrastructure configuration:** đọc tham số, kết nối nguồn dữ liệu hoặc cấu hình implementation.

Không nên để domain policy tự đọc file cấu hình, gọi HTTP hoặc truy cập database cụ thể. Nếu quy tắc cần dữ liệu ngoài, application layer có thể lấy dữ liệu qua port rồi truyền snapshot phù hợp vào policy; hoặc domain model sử dụng một abstraction có ý nghĩa miền khi điều đó thật sự cần thiết.

### 11.1. Chính sách thay đổi theo thời gian

Một số chính sách có hiệu lực theo ngày, hợp đồng hoặc phiên bản. Khi đó, kết quả cần được gắn với thời điểm và phiên bản chính sách đã áp dụng. Ví dụ, đơn hàng đã xác nhận cần giữ snapshot giá hoặc policy reference để giải thích kết quả lịch sử sau khi bảng giá thay đổi.

Không nên tính lại lịch sử bằng policy hiện tại nếu nghiệp vụ yêu cầu giữ đúng điều kiện tại thời điểm giao dịch. Có thể cần `effectiveFrom`, `effectiveTo`, `policyVersion` hoặc snapshot của các tham số liên quan.

### 11.2. Không để mọi quy tắc thành cấu hình động

Một số quy tắc là phần cốt lõi của nghiệp vụ và cần được thể hiện rõ trong code cùng kiểm thử. Đưa mọi thứ vào bảng cấu hình hoặc expression động có thể làm mất khả năng kiểm soát, khó review và khó xác định ai có quyền thay đổi chính sách.

Chỉ đưa các giá trị thực sự cần điều chỉnh bởi người vận hành hoặc theo thời gian vào cấu hình. Những thay đổi làm đổi semantics nên có quy trình quản trị, versioning và audit phù hợp.

## 12. Kiểm thử policy và strategy

Việc tách policy/strategy giúp kiểm thử từng quy tắc độc lập. Mỗi implementation nên có bộ ví dụ thể hiện điều kiện áp dụng, kết quả mong đợi và trường hợp biên.

### 12.1. Kiểm thử từng strategy

Ví dụ với `StandardShippingFeeStrategy`, kiểm thử:

- Phí cơ bản tại từng vùng.
- Khối lượng bằng 0 hoặc không hợp lệ.
- Đơn vị đo và cách làm tròn.
- Tiền tệ không tương thích.
- Trường hợp vượt ngưỡng khối lượng.

Với `ExpressShippingFeeStrategy`, bổ sung kiểm thử phụ phí và vùng không hỗ trợ giao nhanh.

### 12.2. Kiểm thử policy lựa chọn

Resolver cần được kiểm thử với:

- Chỉ một policy phù hợp.
- Không có policy phù hợp.
- Nhiều policy cùng phù hợp.
- Quy tắc ưu tiên hoặc loại trừ.
- Chính sách hết hiệu lực tại thời điểm yêu cầu.

Nếu nhiều policy cùng thỏa nhưng hệ thống cần một kết quả duy nhất, test nên xác nhận rõ policy được chọn hoặc cấu hình bị từ chối.

### 12.3. Kiểm thử bằng ví dụ nghiệp vụ

Chuyên gia và nhóm phát triển có thể cùng lập bảng quyết định:

| Phân khúc | Tổng đơn đạt ngưỡng | Vùng hỗ trợ | Kết quả miễn phí |
| --- | --- | --- | --- |
| Thành viên | Có | Có | Có |
| Thành viên | Không | Có | Không |
| Thành viên | Có | Không | Không |
| Khách thường | Có | Có | Không |

Bảng này giúp xác nhận quy tắc trước khi viết code và có thể chuyển thành test case. Nếu còn điều kiện khác như loại sản phẩm hoặc thời hạn chương trình, cần bổ sung vào bảng.

## 13. Khi nào không nên dùng Policy/Strategy?

Không nên tạo abstraction chỉ để tránh mọi câu lệnh điều kiện. Các trường hợp sau thường có thể giữ đơn giản:

- Chỉ có một hoặc hai nhánh ngắn, ổn định và không lặp lại.
- Điều kiện chỉ là kiểm tra hợp lệ đơn giản, không phải một quy tắc có ý nghĩa riêng.
- Các nhánh không cùng một hành vi và không thể thay thế qua một hợp đồng chung.
- Việc tạo interface và nhiều class khiến người đọc phải đi qua nhiều file để hiểu một quy tắc nhỏ.
- Biến thể không có khả năng thay đổi độc lập và không có nhu cầu kiểm thử riêng.

Ví dụ, kiểm tra `quantity > 0` trong value object không cần một `PositiveQuantityPolicy` nếu điều kiện chỉ có một nghĩa đơn giản và ổn định.

Một `switch` trên enum trạng thái cũng có thể là cách phù hợp nếu nó thể hiện một state machine rõ ràng, có đầy đủ các trạng thái và hành vi. Không nên thay mọi state transition bằng một nhóm strategy rời rạc nếu điều đó làm mất khả năng nhìn thấy toàn bộ vòng đời.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Tạo strategy cho mọi nhánh `if` | Quá nhiều lớp và khó lần theo luồng đơn giản | Chỉ tách khi có biến thể và lý do thay đổi rõ |
| Đặt tên `DefaultStrategy` hoặc `Processor` | Không diễn đạt quy tắc nghiệp vụ | Dùng tên mô tả chính sách hoặc cách tính cụ thể |
| Dùng một interface quá chung | Implementation cần nhiều tham số không liên quan hoặc phải kiểm tra kiểu | Xác định đúng hành vi và dữ liệu chung |
| Chọn strategy bằng `switch` ở nhiều nơi | Quy tắc lựa chọn tiếp tục bị phân tán | Tập trung việc tra cứu hoặc quyết định tại resolver/registry |
| Dựa vào thứ tự đăng ký ngầm | Kết quả thay đổi khi thứ tự DI hoặc cấu hình đổi | Mô hình hóa priority rõ hoặc từ chối trường hợp mơ hồ |
| Trộn policy với gọi API và persistence | Quy tắc miền phụ thuộc hạ tầng | Tách domain decision khỏi application orchestration và adapter |
| Cộng dồn mọi policy mà không định nghĩa thứ tự | Kết quả tính toán sai hoặc khó giải thích | Xác định pipeline, priority và quy tắc loại trừ |
| Đưa mọi tham số vào cấu hình động | Khó review và kiểm soát thay đổi chính sách | Phân biệt code rule với tham số cấu hình có quản trị |
| Không lưu phiên bản chính sách đã áp dụng | Không giải thích được kết quả lịch sử | Lưu policy version hoặc snapshot cần thiết |
| Nhầm Policy, Strategy và Specification | Mô hình dùng sai tên và trách nhiệm | Phân biệt quyết định, thuật toán và điều kiện |

## 15. Quy trình chuyển nhánh điều kiện thành policy/strategy

Khi thấy nhiều nhánh điều kiện trong mã nguồn hoặc trong thiết kế mới, nhóm có thể làm theo các bước sau.

### Bước 1: Thu thập các nhánh hiện có

Ghi lại điều kiện, hành vi và kết quả của từng nhánh. Tìm những nơi khác đang lặp lại cùng một quy tắc. Đừng tách lớp trước khi hiểu toàn bộ hành vi.

### Bước 2: Xác định hoạt động chung

Diễn đạt bằng một câu nghiệp vụ, chẳng hạn “tính phí giao hàng cho một yêu cầu giao nhận” hoặc “đánh giá điều kiện tín dụng của người mua”. Nếu không có một hoạt động chung, có thể các nhánh đang thuộc những use case khác nhau.

### Bước 3: Tách biến thể khỏi tham số

Xác định phần nào là thuật toán khác nhau, phần nào chỉ là dữ liệu đầu vào, điều kiện áp dụng hoặc validation. Tránh tạo implementation cho từng tổ hợp tham số.

### Bước 4: Chọn khái niệm đúng

Quyết định đây là policy, strategy, specification hay hành vi của entity/value object. Chọn tên theo Ubiquitous Language và bounded context.

### Bước 5: Định nghĩa hợp đồng nhỏ và có ý nghĩa

Chọn đầu vào, kết quả và lỗi nghiệp vụ cần thiết. Dùng value object hoặc result type để thể hiện đơn vị và ý nghĩa, tránh truyền một danh sách tham số kỹ thuật khó hiểu.

### Bước 6: Tách implementation và điểm lựa chọn

Đưa các biến thể vào implementation riêng. Tập trung việc lựa chọn tại factory, resolver hoặc registry. Nếu lựa chọn phụ thuộc quy tắc nghiệp vụ, mô hình hóa quyết định đó rõ ràng.

### Bước 7: Xác định cách kết hợp

Nếu nhiều policy có thể cùng áp dụng, quy định thứ tự, ưu tiên, loại trừ và giới hạn. Không dựa vào thứ tự collection hoặc thứ tự khởi tạo không được kiểm soát.

### Bước 8: Kiểm thử từng biến thể và toàn bộ lựa chọn

Viết test cho implementation, resolver, trường hợp không có hoặc có nhiều policy phù hợp và các tình huống biên. Dùng bảng quyết định từ chuyên gia để xác nhận kết quả.

### Bước 9: Đánh giá lại độ phức tạp

Sau khi refactor, kiểm tra xem việc thêm biến thể có còn buộc sửa nơi sử dụng không, số class có hợp lý không và người đọc có hiểu được luồng không. Nếu abstraction làm mã khó đọc hơn mà không giảm thay đổi lan truyền, hãy cân nhắc cách đơn giản hơn.

## 16. Nguyên tắc thực hành

Khi lựa chọn policy object hoặc strategy thay cho nhánh điều kiện, nhóm nên nhớ:

- **Bắt đầu từ quy tắc nghiệp vụ.** Hiểu điều gì thay đổi trước khi tạo interface.
- **Phân biệt Policy, Strategy và Specification.** Quyết định nghiệp vụ, thuật toán thay thế và điều kiện kiểm tra có vai trò khác nhau.
- **Tách biến thể thật khỏi tham số.** Không tạo class cho mọi tổ hợp dữ liệu.
- **Đặt tên bằng Ubiquitous Language.** Tên cần nói rõ hoạt động và phạm vi trong bounded context.
- **Dùng hợp đồng có ý nghĩa.** Đầu vào và kết quả nên là kiểu miền, có đơn vị và semantics rõ.
- **Tập trung điểm lựa chọn.** Dùng resolver, factory hoặc registry phù hợp; tránh lặp `switch` ở nhiều nơi.
- **Định nghĩa rõ priority và composition.** Không dựa vào thứ tự ngầm khi nhiều policy cùng thỏa.
- **Giữ policy ở đúng tầng.** Quy tắc miền không tự gọi framework, database hoặc API bên ngoài.
- **Kiểm thử từng biến thể và quyết định lựa chọn.** Dùng ví dụ nghiệp vụ và bảng quyết định.
- **Không lạm dụng abstraction.** Một nhánh nhỏ, ổn định có thể rõ ràng hơn nhiều lớp strategy.
- **Lưu dấu vết chính sách khi cần.** Kết quả lịch sử cần giải thích được theo policy hoặc phiên bản đã áp dụng.

Policy object và Strategy Pattern giúp biến các nhánh điều kiện có nhiều biến thể thành những hành vi có tên, hợp đồng và trách nhiệm rõ ràng. Khi điểm biến thiên được xác định đúng, nơi sử dụng chỉ cần yêu cầu một hoạt động nghiệp vụ; việc lựa chọn và thực hiện từng chính sách được quản lý ở một ranh giới có chủ đích. Cách làm này giảm logic lặp lại, giúp kiểm thử từng quy tắc và giữ cho mô hình phản ánh ngôn ngữ của miền, đồng thời vẫn cần sự tiết chế để không biến mọi điều kiện đơn giản thành một hệ thống class phức tạp.

## 17. Câu hỏi tự kiểm tra

1. Vì sao nhánh điều kiện rải rác có thể khiến cùng một chính sách được áp dụng khác nhau ở các nơi?
2. Phân biệt Policy, Strategy Pattern và Specification bằng ví dụ tính phí vận chuyển.
3. Những dấu hiệu nào cho thấy một tập hợp `if/else` đã trở thành điểm biến thiên cần tách?
4. Vì sao cần phân biệt biến thể thuật toán với tham số đầu vào và điều kiện áp dụng?
5. Một hợp đồng `ShippingFeeStrategy` nên thể hiện những thông tin nào?
6. Registry, factory và resolver khác nhau như thế nào khi chọn implementation?
7. Rủi ro của việc dùng `findFirst()` theo thứ tự đăng ký ngầm là gì?
8. Khi nhiều policy cùng áp dụng, nhóm cần định nghĩa những quy tắc kết hợp nào?
9. Vì sao domain policy không nên tự gọi HTTP client hoặc truy cập database cụ thể?
10. Khi nào nên giữ `if/else` hoặc `switch` thay vì tạo policy/strategy object?
11. Làm thế nào để kiểm thử trường hợp không có hoặc có nhiều policy phù hợp?
12. Hãy chọn một nhánh điều kiện trong miền nghiệp vụ của bạn, xác định biến thể, đề xuất tên policy/strategy, hợp đồng đầu vào/đầu ra và cách lựa chọn implementation.
